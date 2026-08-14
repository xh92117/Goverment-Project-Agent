"""Persistent process-local background jobs for knowledge-index builds."""

from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from time import time

from deerflow.knowledge.generator import build_knowledge_index_from_folder
from deerflow.knowledge.organizer import organize_incoming_files, organize_options_from_config
from deerflow.knowledge.schemas import (
    KnowledgeBuildJob,
    KnowledgeBuildJobProgress,
    KnowledgeIncrementalUpdateRequest,
    KnowledgeIndexBuildRequest,
    KnowledgeIndexBuildResponse,
)
from deerflow.knowledge.storage import _knowledge_root_path
from deerflow.utils.time import now_iso

_JOB_ID_LENGTH = 32
_STALE_LOCK_SECONDS = 6 * 60 * 60
_MAX_RETAINED_JOBS = 50
_TERMINAL_STATES = {"completed", "completed_with_warnings", "failed"}


class KnowledgeBuildJobConflictError(RuntimeError):
    """Raised when the same knowledge root already has a running build."""


class KnowledgeBuildJobManager:
    """Run blocking index builds off the request loop and persist snapshots."""

    def __init__(self, *, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="knowledge-build")
        self._lock = threading.RLock()
        self._jobs: dict[tuple[str, str], KnowledgeBuildJob] = {}
        self._futures: dict[tuple[str, str], Future[None]] = {}

    @staticmethod
    def _jobs_dir(root: Path) -> Path:
        return root / ".index" / "build_jobs"

    @classmethod
    def _job_path(cls, root: Path, job_id: str) -> Path:
        if len(job_id) != _JOB_ID_LENGTH or any(character not in "0123456789abcdef" for character in job_id):
            raise KeyError(job_id)
        return cls._jobs_dir(root) / f"{job_id}.json"

    @staticmethod
    def _lock_path(root: Path) -> Path:
        return root / ".index" / "build.lock"

    @classmethod
    def _persist(cls, root: Path, job: KnowledgeBuildJob) -> None:
        path = cls._job_path(root, job.job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temporary.write_text(job.model_dump_json(exclude_none=True), encoding="utf-8")
        temporary.replace(path)

    @classmethod
    def _read_persisted(cls, root: Path, job_id: str) -> KnowledgeBuildJob:
        path = cls._job_path(root, job_id)
        if not path.is_file():
            raise KeyError(job_id)
        return KnowledgeBuildJob.model_validate_json(path.read_text(encoding="utf-8"))

    @classmethod
    def _release_root_lock(cls, root: Path, job_id: str) -> None:
        lock_path = cls._lock_path(root)
        try:
            if lock_path.read_text(encoding="utf-8").strip() == job_id:
                lock_path.unlink(missing_ok=True)
        except OSError:
            pass

    @classmethod
    def _claim_root_lock(cls, root: Path, job_id: str) -> None:
        lock_path = cls._lock_path(root)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with lock_path.open("x", encoding="utf-8") as lock_file:
                lock_file.write(job_id)
            return
        except FileExistsError:
            pass

        stale = False
        try:
            current_job_id = lock_path.read_text(encoding="utf-8").strip()
            current = cls._read_persisted(root, current_job_id)
            stale = current.state in _TERMINAL_STATES or time() - lock_path.stat().st_mtime > _STALE_LOCK_SECONDS
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            stale = time() - lock_path.stat().st_mtime > _STALE_LOCK_SECONDS
        if not stale:
            raise KnowledgeBuildJobConflictError("A knowledge build is already running for this library.")
        lock_path.unlink(missing_ok=True)
        try:
            with lock_path.open("x", encoding="utf-8") as lock_file:
                lock_file.write(job_id)
        except FileExistsError as exc:
            raise KnowledgeBuildJobConflictError("A knowledge build is already running for this library.") from exc

    @classmethod
    def _cleanup_old_jobs(cls, root: Path) -> None:
        jobs_dir = cls._jobs_dir(root)
        if not jobs_dir.is_dir():
            return
        paths = sorted(jobs_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in paths[_MAX_RETAINED_JOBS:]:
            try:
                job = KnowledgeBuildJob.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if job.state in _TERMINAL_STATES:
                path.unlink(missing_ok=True)

    def submit(self, request: KnowledgeIndexBuildRequest, *, user_id: str | None) -> KnowledgeBuildJob:
        root = _knowledge_root_path(user_id=user_id)
        root.mkdir(parents=True, exist_ok=True)
        job_id = uuid.uuid4().hex
        self._claim_root_lock(root, job_id)
        job = KnowledgeBuildJob(
            job_id=job_id,
            operation="build",
            request=request,
            created_at=now_iso(),
            progress=KnowledgeBuildJobProgress(message="构建任务已排队。"),
        )
        key = (str(root), job_id)
        try:
            with self._lock:
                self._jobs[key] = job
                self._persist(root, job)
                self._cleanup_old_jobs(root)
                future = self._executor.submit(self._run_build, root, job_id, request, user_id)
                self._futures[key] = future
                future.add_done_callback(lambda completed, job_key=key: self._forget_future(job_key, completed))
        except Exception:
            self._release_root_lock(root, job_id)
            raise
        return job.model_copy(deep=True)

    def submit_incremental(
        self,
        request: KnowledgeIncrementalUpdateRequest,
        *,
        user_id: str | None,
    ) -> KnowledgeBuildJob:
        """Queue incoming-file organization and index building as one job."""

        root = _knowledge_root_path(user_id=user_id)
        root.mkdir(parents=True, exist_ok=True)
        job_id = uuid.uuid4().hex
        self._claim_root_lock(root, job_id)
        index_request = KnowledgeIndexBuildRequest(
            folder_path=request.folder_path,
            recursive=request.recursive,
            include_extensions=request.include_extensions,
            replace_existing=request.replace_existing,
            project_types=request.project_types,
            max_files=request.max_files,
            incremental=request.incremental,
        )
        job = KnowledgeBuildJob(
            job_id=job_id,
            operation="organize_and_build",
            request=index_request,
            created_at=now_iso(),
            progress=KnowledgeBuildJobProgress(message="整理与构建任务已排队。"),
        )
        key = (str(root), job_id)
        try:
            with self._lock:
                self._jobs[key] = job
                self._persist(root, job)
                self._cleanup_old_jobs(root)
                future = self._executor.submit(
                    self._run_incremental,
                    root,
                    job_id,
                    request,
                    index_request,
                    user_id,
                )
                self._futures[key] = future
                future.add_done_callback(lambda completed, job_key=key: self._forget_future(job_key, completed))
        except Exception:
            self._release_root_lock(root, job_id)
            raise
        return job.model_copy(deep=True)

    def _forget_future(self, key: tuple[str, str], completed: Future[None]) -> None:
        with self._lock:
            if self._futures.get(key) is completed:
                self._futures.pop(key, None)

    def _update(self, root: Path, job_id: str, **updates: object) -> KnowledgeBuildJob:
        key = (str(root), job_id)
        with self._lock:
            current = self._jobs.get(key) or self._read_persisted(root, job_id)
            updated = current.model_copy(update=updates)
            self._jobs[key] = updated
            self._persist(root, updated)
            return updated

    def _finish_build(
        self,
        root: Path,
        job_id: str,
        result: KnowledgeIndexBuildResponse,
    ) -> None:
        compact_result = result.model_copy(update={"entries": []})
        quality = result.quality_report
        completed_state = "completed_with_warnings" if result.warnings or (quality is not None and (not quality.passed or quality.warning_count > 0)) else "completed"
        total = result.scale_stats.get("index_entries_total", 0)
        self._update(
            root,
            job_id,
            state=completed_state,
            result=compact_result,
            finished_at=now_iso(),
            progress=KnowledgeBuildJobProgress(
                stage="completed",
                current=total,
                total=total,
                percent=100.0,
                message="知识库构建完成。",
            ),
        )

    def _fail_build(self, root: Path, job_id: str, exc: Exception) -> None:
        self._update(
            root,
            job_id,
            state="failed",
            error=str(exc) or exc.__class__.__name__,
            finished_at=now_iso(),
            progress=KnowledgeBuildJobProgress(stage="failed", percent=100.0, message="知识库构建失败。"),
        )

    def _build_index(
        self,
        root: Path,
        job_id: str,
        request: KnowledgeIndexBuildRequest,
        user_id: str | None,
        *,
        percent_start: float = 0.0,
        percent_span: float = 100.0,
    ) -> KnowledgeIndexBuildResponse:
        def progress(stage: str, current: int, total: int, percent: float, message: str) -> None:
            self._update(
                root,
                job_id,
                progress=KnowledgeBuildJobProgress(
                    stage=stage,
                    current=current,
                    total=total,
                    percent=min(100.0, percent_start + percent_span * percent / 100.0),
                    message=message,
                ),
            )

        return build_knowledge_index_from_folder(
            request,
            user_id=user_id,
            progress_callback=progress,
        )

    def _run_build(
        self,
        root: Path,
        job_id: str,
        request: KnowledgeIndexBuildRequest,
        user_id: str | None,
    ) -> None:
        self._update(
            root,
            job_id,
            state="running",
            started_at=now_iso(),
            progress=KnowledgeBuildJobProgress(stage="initializing", percent=0.0, message="构建任务已启动。"),
        )
        try:
            self._finish_build(root, job_id, self._build_index(root, job_id, request, user_id))
        except Exception as exc:
            self._fail_build(root, job_id, exc)
        finally:
            self._release_root_lock(root, job_id)

    def _run_incremental(
        self,
        root: Path,
        job_id: str,
        request: KnowledgeIncrementalUpdateRequest,
        index_request: KnowledgeIndexBuildRequest,
        user_id: str | None,
    ) -> None:
        self._update(
            root,
            job_id,
            state="running",
            started_at=now_iso(),
            progress=KnowledgeBuildJobProgress(stage="organizing", percent=1.0, message="正在准备待入库文件。"),
        )

        def organize_progress(current: int, total: int, percent: float, message: str) -> None:
            self._update(
                root,
                job_id,
                progress=KnowledgeBuildJobProgress(
                    stage="organizing",
                    current=current,
                    total=total,
                    percent=1.0 + 13.0 * percent / 100.0,
                    message=message,
                ),
            )

        try:
            if request.organize_incoming:
                report = organize_incoming_files(
                    organize_options_from_config(request.model_dump(mode="json")),
                    user_id=user_id,
                    progress_callback=organize_progress,
                )
                organization = asdict(report)
            else:
                organization = None
            self._update(
                root,
                job_id,
                organization=organization,
                progress=KnowledgeBuildJobProgress(
                    stage="organization_completed",
                    current=organization.get("scanned", 0) if organization else 0,
                    total=organization.get("scanned", 0) if organization else 0,
                    percent=15.0,
                    message=(f"文件整理完成：移动 {organization.get('moved', 0)} 个，开始构建索引。" if organization else "开始构建知识库索引。"),
                ),
            )
            result = self._build_index(
                root,
                job_id,
                index_request,
                user_id,
                percent_start=15.0,
                percent_span=85.0,
            )
            self._finish_build(root, job_id, result)
        except Exception as exc:
            self._fail_build(root, job_id, exc)
        finally:
            self._release_root_lock(root, job_id)

    def get(self, job_id: str, *, user_id: str | None) -> KnowledgeBuildJob:
        root = _knowledge_root_path(user_id=user_id)
        key = (str(root), job_id)
        with self._lock:
            job = self._jobs.get(key)
            if job is None:
                job = self._read_persisted(root, job_id)
        return job.model_copy(deep=True)

    def list(self, *, user_id: str | None, limit: int = 20) -> list[KnowledgeBuildJob]:
        root = _knowledge_root_path(user_id=user_id)
        jobs_dir = self._jobs_dir(root)
        if not jobs_dir.is_dir():
            return []
        paths = sorted(jobs_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        jobs: list[KnowledgeBuildJob] = []
        for path in paths[:limit]:
            try:
                jobs.append(KnowledgeBuildJob.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return jobs

    def wait(self, job_id: str, *, user_id: str | None, timeout: float = 30.0) -> KnowledgeBuildJob:
        """Wait for a job in tests or synchronous integrations."""

        root = _knowledge_root_path(user_id=user_id)
        key = (str(root), job_id)
        with self._lock:
            future = self._futures.get(key)
        if future is not None:
            future.result(timeout=timeout)
        return self.get(job_id, user_id=user_id)


_manager = KnowledgeBuildJobManager()


def get_knowledge_build_job_manager() -> KnowledgeBuildJobManager:
    return _manager
