"""Project-scoped memory for government project declaration work.

This module deliberately keeps project memory separate from the legacy user/agent
profile.  A project memory file is shared by the experts working on the same
project, but is isolated by both authenticated user and ``project_id``.
"""

from __future__ import annotations

import copy
import html
import json
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from deerflow.agents.memory.prompt import _coerce_confidence, _count_tokens
from deerflow.agents.memory.storage import utc_now_iso_z
from deerflow.config.paths import get_paths
from deerflow.runtime.user_context import DEFAULT_USER_ID

GOVERNMENT_PROJECT_AGENT_NAME = "government-project-declaration"

_SAFE_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_MAX_APPLICANT_ID_LENGTH = 128


def validate_project_id(project_id: str) -> str:
    """Validate a project id before it is used in a filesystem path."""
    normalized = str(project_id).strip()
    if not normalized or not _SAFE_PROJECT_ID_RE.fullmatch(normalized):
        raise ValueError("project_id must contain only letters, numbers, hyphens, or underscores")
    return normalized


def normalize_applicant_id(applicant_id: object) -> str:
    """Normalize the applicant identity stored as project metadata."""
    normalized = str(applicant_id or "default").strip() or "default"
    if len(normalized) > _MAX_APPLICANT_ID_LENGTH or any(char in normalized for char in ("/", "\\", "\x00")):
        raise ValueError("invalid applicant_id")
    return normalized


def create_empty_project_memory(project_id: str, applicant_id: object = "default") -> dict[str, Any]:
    """Return the canonical, non-distilled project memory structure."""
    now = utc_now_iso_z()
    return {
        "version": "1.0",
        "scope": {
            "projectId": validate_project_id(project_id),
            "applicantId": normalize_applicant_id(applicant_id),
        },
        "lastUpdated": now,
        "confirmedFacts": [],
        "workingAssumptions": [],
        "workflowState": {},
    }


class ProjectMemoryStorage:
    """Atomic JSON storage isolated by ``user_id`` and ``project_id``."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def file_path(self, project_id: str, *, user_id: str | None = None) -> Path:
        safe_project_id = validate_project_id(project_id)
        safe_user_id = str(user_id or DEFAULT_USER_ID)
        return get_paths().user_dir(safe_user_id) / "projects" / safe_project_id / "memory.json"

    def load(
        self,
        project_id: str,
        *,
        applicant_id: object = "default",
        user_id: str | None = None,
    ) -> dict[str, Any]:
        path = self.file_path(project_id, user_id=user_id)
        with self._lock:
            if not path.exists():
                return create_empty_project_memory(project_id, applicant_id)
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return create_empty_project_memory(project_id, applicant_id)

        if not isinstance(payload, dict):
            return create_empty_project_memory(project_id, applicant_id)
        normalized = create_empty_project_memory(project_id, applicant_id)
        normalized["confirmedFacts"] = _normalize_fact_list(payload.get("confirmedFacts"), status="confirmed")
        normalized["workingAssumptions"] = _normalize_fact_list(payload.get("workingAssumptions"), status="working_assumption")
        workflow = payload.get("workflowState")
        normalized["workflowState"] = copy.deepcopy(workflow) if isinstance(workflow, dict) else {}
        normalized["lastUpdated"] = str(payload.get("lastUpdated") or normalized["lastUpdated"])
        return normalized

    def save(
        self,
        memory_data: dict[str, Any],
        project_id: str,
        *,
        applicant_id: object = "default",
        user_id: str | None = None,
    ) -> bool:
        path = self.file_path(project_id, user_id=user_id)
        normalized = create_empty_project_memory(project_id, applicant_id)
        normalized["confirmedFacts"] = _normalize_fact_list(memory_data.get("confirmedFacts"), status="confirmed")
        normalized["workingAssumptions"] = _normalize_fact_list(memory_data.get("workingAssumptions"), status="working_assumption")
        workflow = memory_data.get("workflowState")
        normalized["workflowState"] = copy.deepcopy(workflow) if isinstance(workflow, dict) else {}
        normalized["lastUpdated"] = utc_now_iso_z()

        with self._lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
                temporary.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(temporary, path)
                return True
            except OSError:
                return False


def _normalize_fact_list(value: object, *, status: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        normalized_content = content.strip()
        key = normalized_content.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "id": str(item.get("id") or f"pmem_{uuid.uuid4().hex[:10]}"),
                "content": normalized_content,
                "category": str(item.get("category") or "project_constraint"),
                "status": status,
                "confidence": _coerce_confidence(item.get("confidence"), default=0.7),
                "sourceType": str(item.get("sourceType") or ("manual_confirmation" if status == "confirmed" else "conversation_extraction")),
                "source": str(item.get("source") or "unknown"),
                "createdAt": str(item.get("createdAt") or utc_now_iso_z()),
            }
        )
    return result


def format_project_memory_for_injection(memory_data: dict[str, Any], max_tokens: int = 2000) -> str:
    """Format project memory while preserving fact/assumption provenance."""
    if not isinstance(memory_data, dict):
        return ""
    scope = memory_data.get("scope") if isinstance(memory_data.get("scope"), dict) else {}
    lines = [
        "Project Memory (strictly scoped; never reuse across projects):",
        f"- Project ID: {scope.get('projectId', '')}",
        f"- Applicant ID: {scope.get('applicantId', 'default')}",
    ]

    confirmed = _normalize_fact_list(memory_data.get("confirmedFacts"), status="confirmed")
    assumptions = _normalize_fact_list(memory_data.get("workingAssumptions"), status="working_assumption")
    if confirmed:
        lines.append("Confirmed facts (may be used as facts):")
        lines.extend(f"- [{html.escape(fact['category'])}] {html.escape(fact['content'])}" for fact in confirmed)
    if assumptions:
        lines.append("Working assumptions (must be verified before final use):")
        lines.extend(f"- [{html.escape(fact['category'])}] {html.escape(fact['content'])}" for fact in assumptions)
    workflow = memory_data.get("workflowState")
    if isinstance(workflow, dict) and workflow:
        lines.append("Workflow state (not factual evidence):")
        for key, value in workflow.items():
            if isinstance(value, (str, int, float, bool)):
                lines.append(f"- {html.escape(str(key))}: {html.escape(str(value))}")

    if len(lines) <= 3:
        return ""
    result = "\n".join(lines)
    if _count_tokens(result) <= max_tokens:
        return result
    # Project memory is short by design; a conservative character fallback is
    # enough here and avoids silently promoting lower-priority assumptions.
    return result[: max(200, max_tokens * 3)] + "\n..."


_project_memory_storage: ProjectMemoryStorage | None = None
_project_memory_storage_lock = threading.Lock()


def get_project_memory_storage() -> ProjectMemoryStorage:
    global _project_memory_storage
    with _project_memory_storage_lock:
        if _project_memory_storage is None:
            _project_memory_storage = ProjectMemoryStorage()
        return _project_memory_storage
