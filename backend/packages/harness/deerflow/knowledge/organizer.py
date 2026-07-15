"""Incrementally organize incoming knowledge-base files before indexing."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from deerflow.knowledge.extractors import extract_text
from deerflow.knowledge.storage import _knowledge_root_path

_DEFAULT_SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt", ".docx", ".pdf", ".xlsx", ".xls", ".csv", ".tsv"}
_MINERU_CACHE_SUFFIX = ".mineru.md"
_EXTRACTOR_METADATA_SUFFIX = ".extractor.json"
_DEFAULT_IGNORED_SUFFIXES = {_MINERU_CACHE_SUFFIX, _EXTRACTOR_METADATA_SUFFIX}
_DEFAULT_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("申报书模板", ("模板", "填报说明", "格式要求")),
    (
        "历史申报书",
        (
            "申报书",
            "申请书",
            "项目申请",
            "立项依据",
            "任务书",
            "研究方案",
            "技术方案",
            "研究内容",
            "项目名称",
            "预期成果",
        ),
    ),
    ("国内外研究现状", ("国内外研究现状", "研究现状", "国外研究", "国内研究")),
    ("已有研究基础", ("已有研究基础", "研究基础", "前期基础", "技术基础", "实验基础")),
    ("团队成果", ("团队成果", "论文", "专利", "软著", "标准", "奖励", "成果")),
    ("政策指南", ("指南", "申报通知", "通知", "管理办法", "评审规则", "资助办法")),
    ("技术路线", ("技术路线", "实施方案")),
    ("创新点", ("创新点", "创新")),
    ("预算依据", ("预算", "经费", "预算科目")),
)
_DEFAULT_DOMAIN_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "隧洞检测",
        ("隧洞", "衬砌", "爬壁机器人", "冲击回波", "地质雷达", "弹性波", "多源检测"),
    ),
    ("路基工程", ("路基", "填方", "压实", "回填", "道路", "公路")),
    ("智能制造", ("智能制造", "工业视觉", "机器视觉", "缺陷检测")),
    ("人工智能", ("人工智能", "大模型", "深度学习", "机器学习")),
)


@dataclass(frozen=True)
class KnowledgeOrganizeRule:
    """Keyword rule for classifying incoming files."""

    name: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgeOrganizeOptions:
    """Options for organizing files from an incoming folder."""

    incoming_path: str = "_incoming"
    default_category: str = "未分类"
    default_domain: str | None = "通用"
    supported_extensions: tuple[str, ...] = (".md", ".markdown", ".txt", ".docx", ".pdf", ".xlsx", ".xls", ".csv", ".tsv")
    category_rules: tuple[KnowledgeOrganizeRule, ...] = field(
        default_factory=lambda: tuple(
            KnowledgeOrganizeRule(name=name, keywords=keywords)
            for name, keywords in _DEFAULT_CATEGORY_RULES
        )
    )
    domain_rules: tuple[KnowledgeOrganizeRule, ...] = field(
        default_factory=lambda: tuple(
            KnowledgeOrganizeRule(name=name, keywords=keywords)
            for name, keywords in _DEFAULT_DOMAIN_RULES
        )
    )
    dry_run: bool = False
    preview_chars: int = 4000


@dataclass(frozen=True)
class KnowledgeOrganizedFile:
    """A single incoming file organization result."""

    source_path: str
    target_path: str | None = None
    category: str | None = None
    domain: str | None = None
    status: str = "moved"
    reason: str | None = None


@dataclass(frozen=True)
class KnowledgeOrganizeReport:
    """Summary returned after organizing incoming files."""

    root_path: str
    incoming_path: str
    dry_run: bool
    scanned: int
    moved: int
    skipped: int
    files: list[KnowledgeOrganizedFile]


def _normalize_extension(extension: str) -> str:
    extension = extension.lower().strip()
    return extension if extension.startswith(".") else f".{extension}"


def _is_mineru_cache(path: Path) -> bool:
    return path.name.lower().endswith(_MINERU_CACHE_SUFFIX)


def _source_path_for_mineru_cache(path: Path) -> Path | None:
    suffix = _MINERU_CACHE_SUFFIX
    if not path.name.lower().endswith(suffix):
        return None
    return path.with_name(path.name[: -len(suffix)])


def _is_extractor_metadata(path: Path) -> bool:
    return path.name.lower().endswith(_EXTRACTOR_METADATA_SUFFIX)


def _source_path_for_extractor_metadata(path: Path) -> Path | None:
    suffix = _EXTRACTOR_METADATA_SUFFIX
    if not path.name.lower().endswith(suffix):
        return None
    return path.with_name(path.name[: -len(suffix)])


def _mineru_cache_path(path: Path) -> Path:
    return path.with_name(f"{path.name}{_MINERU_CACHE_SUFFIX}")


def _extractor_metadata_path(path: Path) -> Path:
    return path.with_name(f"{path.name}{_EXTRACTOR_METADATA_SUFFIX}")


def _pdf_assets_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.assets")


def _resolve_relative_folder(root: Path, folder_path: str) -> Path:
    raw = Path(folder_path)
    if raw.is_absolute():
        raise ValueError("incoming_path must be relative to the knowledge-base root.")
    resolved = (root / raw).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError("Access denied: path traversal detected.") from None
    return resolved


def _relative_to_root(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _safe_folder_name(value: str | None, fallback: str) -> str:
    cleaned = (value or "").strip().replace("\\", "_").replace("/", "_").replace(":", "_")
    cleaned = cleaned.strip(". ")
    return cleaned or fallback


def _rules_from_config(config: list[dict[str, Any]] | None) -> tuple[KnowledgeOrganizeRule, ...] | None:
    if not config:
        return None
    rules: list[KnowledgeOrganizeRule] = []
    for item in config:
        name = str(item.get("name", "")).strip()
        keywords = tuple(str(keyword).strip() for keyword in item.get("keywords", []) if str(keyword).strip())
        if name and keywords:
            rules.append(KnowledgeOrganizeRule(name=name, keywords=keywords))
    return tuple(rules)


def organize_options_from_config(config: dict[str, Any]) -> KnowledgeOrganizeOptions:
    """Build organizer options from a UTF-8 JSON config object."""

    category_rules = _rules_from_config(config.get("classification_rules"))
    domain_rules = _rules_from_config(config.get("domain_rules"))
    supported_extensions = tuple(
        _normalize_extension(str(ext))
        for ext in config.get("organize_extensions", config.get("include_extensions", []))
        if str(ext).strip()
    )
    return KnowledgeOrganizeOptions(
        incoming_path=str(config.get("incoming_path", "_incoming")),
        default_category=str(config.get("default_category", "未分类")),
        default_domain=config.get("default_domain", "通用"),
        supported_extensions=supported_extensions or tuple(sorted(_DEFAULT_SUPPORTED_EXTENSIONS)),
        category_rules=category_rules
        or tuple(KnowledgeOrganizeRule(name=name, keywords=keywords) for name, keywords in _DEFAULT_CATEGORY_RULES),
        domain_rules=domain_rules
        or tuple(KnowledgeOrganizeRule(name=name, keywords=keywords) for name, keywords in _DEFAULT_DOMAIN_RULES),
        dry_run=bool(config.get("dry_run", False)),
        preview_chars=int(config.get("organize_preview_chars", 4000)),
    )


def _file_preview(path: Path, max_chars: int) -> str:
    try:
        return extract_text(path)[:max_chars]
    except Exception:
        return ""


def _match_rule(text: str, rules: tuple[KnowledgeOrganizeRule, ...], default: str | None) -> str | None:
    for rule in rules:
        if any(keyword and keyword in text for keyword in rule.keywords):
            return rule.name
    return default


def _deduplicated_target(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 1000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Cannot find a non-conflicting target name for {path}.")


def _same_file_content(left: Path, right: Path) -> bool:
    if not left.exists() or not right.exists():
        return False
    if left.stat().st_size != right.stat().st_size:
        return False
    chunk_size = 1024 * 1024
    with left.open("rb") as left_file, right.open("rb") as right_file:
        while True:
            left_chunk = left_file.read(chunk_size)
            right_chunk = right_file.read(chunk_size)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True


def _remove_sidecars(path: Path) -> None:
    for sidecar in (_mineru_cache_path(path), _extractor_metadata_path(path), _pdf_assets_path(path)):
        if sidecar.exists():
            if sidecar.is_dir():
                shutil.rmtree(sidecar)
            else:
                sidecar.unlink()


def _move_sidecar(source: Path, target: Path) -> None:
    if not source.exists():
        return
    if target.exists():
        if source.is_dir():
            shutil.rmtree(source)
        else:
            source.unlink()
        return
    shutil.move(str(source), str(target))


def organize_incoming_files(
    options: KnowledgeOrganizeOptions | None = None,
    *,
    user_id: str | None = None,
) -> KnowledgeOrganizeReport:
    """Move new files from `_incoming` into categorized knowledge-base folders."""

    options = options or KnowledgeOrganizeOptions()
    root = _knowledge_root_path(user_id=user_id)
    incoming = _resolve_relative_folder(root, options.incoming_path)
    supported_extensions = {_normalize_extension(ext) for ext in options.supported_extensions}

    files: list[KnowledgeOrganizedFile] = []
    if not incoming.exists():
        return KnowledgeOrganizeReport(
            root_path=str(root),
            incoming_path=_relative_to_root(root, incoming),
            dry_run=options.dry_run,
            scanned=0,
            moved=0,
            skipped=0,
            files=[],
        )
    if not incoming.is_dir():
        raise ValueError("incoming_path must point to a directory.")

    source_files = sorted(
        path
        for path in incoming.rglob("*")
        if path.is_file()
        and not any(part.lower().endswith(".pdf.assets") for part in path.relative_to(incoming).parts[:-1])
    )
    for source in source_files:
        if not source.exists():
            continue
        source_rel = _relative_to_root(root, source)
        if _is_mineru_cache(source):
            cache_source = _source_path_for_mineru_cache(source)
            if cache_source is not None and not cache_source.exists() and not options.dry_run:
                source.unlink()
                files.append(KnowledgeOrganizedFile(source_path=source_rel, status="skipped", reason="removed orphan cache"))
            else:
                files.append(KnowledgeOrganizedFile(source_path=source_rel, status="skipped", reason="ignored file"))
            continue
        if _is_extractor_metadata(source):
            metadata_source = _source_path_for_extractor_metadata(source)
            if metadata_source is not None and not metadata_source.exists() and not options.dry_run:
                source.unlink()
                files.append(
                    KnowledgeOrganizedFile(
                        source_path=source_rel,
                        status="skipped",
                        reason="removed orphan extractor metadata",
                    )
                )
            else:
                files.append(KnowledgeOrganizedFile(source_path=source_rel, status="skipped", reason="ignored file"))
            continue
        if source.name == "index.json":
            files.append(KnowledgeOrganizedFile(source_path=source_rel, status="skipped", reason="ignored file"))
            continue
        if source.suffix.lower() not in supported_extensions:
            files.append(KnowledgeOrganizedFile(source_path=source_rel, status="skipped", reason="unsupported extension"))
            continue

        preview = _file_preview(source, options.preview_chars)
        classification_text = f"{source.stem}\n{source_rel}\n{preview}"
        category = _safe_folder_name(
            _match_rule(classification_text, options.category_rules, options.default_category),
            "未分类",
        )
        domain = _safe_folder_name(
            _match_rule(classification_text, options.domain_rules, options.default_domain),
            "通用",
        )
        target_dir = (root / category / domain).resolve()
        try:
            target_dir.relative_to(root)
        except ValueError:
            raise ValueError("Access denied: organized target escaped knowledge-base root.") from None
        preferred_target = target_dir / source.name
        if preferred_target.exists() and _same_file_content(source, preferred_target):
            if not options.dry_run:
                source.unlink()
                _remove_sidecars(source)
            files.append(
                KnowledgeOrganizedFile(
                    source_path=source_rel,
                    target_path=_relative_to_root(root, preferred_target),
                    category=category,
                    domain=domain,
                    status="skipped",
                    reason="duplicate content",
                )
            )
            continue

        target = _deduplicated_target(preferred_target)
        target_rel = _relative_to_root(root, target)

        if not options.dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            source_cache = _mineru_cache_path(source)
            target_cache = _mineru_cache_path(target)
            source_extractor_metadata = _extractor_metadata_path(source)
            target_extractor_metadata = _extractor_metadata_path(target)
            source_pdf_assets = _pdf_assets_path(source)
            target_pdf_assets = _pdf_assets_path(target)
            shutil.move(str(source), str(target))
            _move_sidecar(source_cache, target_cache)
            _move_sidecar(source_extractor_metadata, target_extractor_metadata)
            _move_sidecar(source_pdf_assets, target_pdf_assets)
        files.append(
            KnowledgeOrganizedFile(
                source_path=source_rel,
                target_path=target_rel,
                category=category,
                domain=domain,
                status="dry_run" if options.dry_run else "moved",
            )
        )

    moved = sum(1 for item in files if item.status in {"moved", "dry_run"})
    skipped = sum(1 for item in files if item.status == "skipped")
    return KnowledgeOrganizeReport(
        root_path=str(root),
        incoming_path=_relative_to_root(root, incoming),
        dry_run=options.dry_run,
        scanned=len(source_files),
        moved=moved,
        skipped=skipped,
        files=files,
    )
