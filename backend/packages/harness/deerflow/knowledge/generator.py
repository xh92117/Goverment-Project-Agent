"""Build LLM-Wiki index entries from a folder-based knowledge base."""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from deerflow.knowledge.extractors import extract_text_with_metadata
from deerflow.knowledge.schemas import (
    KnowledgeIndexBuildRequest,
    KnowledgeIndexBuildResponse,
    KnowledgeIndexEntry,
    KnowledgeIndexEntryCreate,
    KnowledgeIndexSection,
)
from deerflow.knowledge.sqlite_index import sqlite_knowledge_index_path
from deerflow.knowledge.storage import (
    _knowledge_root_path,
    backup_knowledge_index,
    get_knowledge_storage,
)
from deerflow.utils.time import now_iso

_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_ZH_SECTION_HEADING_RE = re.compile(r"^（[一二三四五六七八九十]+）")
_DECIMAL_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)+)\s+")
_SIMPLE_DOT_HEADING_RE = re.compile(r"^\d+\.\S+")
_TOP_NUMBER_HEADING_RE = re.compile(r"^\d+[．、]\s*")
_SUPPORTED_TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".docx", ".pdf", ".xlsx", ".xls", ".csv", ".tsv"}
_SOURCE_FORMAT_PRIORITY = {
    ".pdf": 50,
    ".docx": 40,
    ".xlsx": 35,
    ".xls": 35,
    ".md": 30,
    ".markdown": 30,
    ".csv": 25,
    ".tsv": 25,
    ".txt": 20,
}
_INDEXER_VERSION = "2"
_CATEGORY_ALIASES = {
    "policy_guides": "政策指南",
    "templates": "申报书模板",
    "historical": "历史申报书",
    "achievements": "团队成果",
    "foundations": "已有研究基础",
    "budget_rules": "预算依据",
    "application_templates": "申报书模板",
    "historical_proposals": "历史申报书",
    "research_foundations": "已有研究基础",
    "team_achievements": "团队成果",
    "literature_materials": "国内外研究现状",
}
_SOURCE_FILE_WARNING_THRESHOLD = 300
_INDEX_ENTRY_WARNING_THRESHOLD = 1000
_INDEX_JSON_BYTES_WARNING_THRESHOLD = 5 * 1024 * 1024
_BUILD_SECONDS_WARNING_THRESHOLD = 60.0
_TARGET_CHUNK_CHARS = 1800
_MAX_CHUNK_CHARS = 3200
_MIN_CHUNK_CHARS = 300
_MAX_PARENT_SUMMARY_CHARS = 900
_GENERIC_TITLES = {"报告正文", "正文", "申报书", "项目申报书"}
_LOW_VALUE_EXACT_HEADINGS = {
    "封面",
    "研究报告",
    "报告名称",
    "主持单位",
    "编制单位",
    "编制时间",
    "目录",
    "插图清单",
    "附图清单",
    "附表清单",
    "表格清单",
    "图目录",
    "表目录",
}
_LOW_VALUE_HEADING_MARKERS = (
    "插图清单",
    "附图清单",
    "附表清单",
    "表格清单",
    "图目录",
    "表目录",
)
_SHORT_BLOCK_KEEP_MARKERS = (
    "申报条件",
    "申报要求",
    "申请条件",
    "国内外研究现状",
    "国内研究现状",
    "国外研究现状",
    "研究现状",
    "研究内容",
    "研究目标",
    "技术方案",
    "研究方案",
    "实施方案",
    "技术路线",
    "创新",
    "研究基础",
    "工作基础",
    "团队成果",
    "预期成果",
    "预算",
    "经费",
    "管理办法",
    "评审规则",
    "资助办法",
)
_GENERATED_CHUNKS_DIR = "申报书章节分块"
_LEGACY_GENERATED_CHUNKS_DIRS = {"按申报章节"}
_IGNORED_SCAN_PARTS = {"_incoming", ".assets", _GENERATED_CHUNKS_DIR, ".index_versions", *_LEGACY_GENERATED_CHUNKS_DIRS}
_TOC_DOT_LEADER_RE = re.compile(r".{2,}(?:\.{2,}|…{2,}|·{2,}|-{2,})\s*\d+\s*$")
_TOC_NUMBERED_PAGE_RE = re.compile(r"^\d+(?:\.\d+)*\s+\S.{2,}\s+\d+\s*$")
_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_AUTHORITY_RE = re.compile(
    r"([\u4e00-\u9fff]{2,30}(?:人民政府|自然科学基金委员会|基金委员会|科学技术厅|科技厅|科技局|"
    r"发展和改革委员会|财政厅|工业和信息化厅|教育厅))"
)

_PROPOSAL_SECTION_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("domestic_foreign_status", "国内外研究现状", ("国内外研究现状", "国内研究现状", "国外研究现状", "研究现状", "发展动态", "发展趋势")),
    ("research_content", "主要研究内容", ("研究内容", "研究目标", "拟解决的关键科学问题", "关键科学问题", "研究任务")),
    ("technical_solution", "技术方案", ("技术方案", "实施方案", "研究方案", "试验方案", "验证方案")),
    ("technical_route", "技术路线", ("技术路线", "路线图", "技术路径")),
    ("innovation_points", "创新点", ("创新点", "创新之处", "特色与创新")),
    ("research_basis", "已有研究基础", ("研究基础", "工作基础", "前期基础", "已有基础")),
    ("expected_outputs", "预期成果", ("预期成果", "考核指标", "成果形式")),
    ("team_achievements", "团队成果", ("团队成果", "论文", "专利", "软著", "获奖", "代表性成果")),
    ("budget_basis", "预算依据", ("预算", "经费", "预算说明", "经费预算")),
    ("application_requirements", "申报条件与要求", ("申报条件", "申报要求", "申请条件", "申报资格", "申报对象")),
    ("references", "参考文献与标准", ("参考文献", "标准", "规范", "指南", "管理办法")),
    ("background_significance", "立项依据与研究意义", ("立项依据", "研究意义", "背景", "科学意义", "应用前景")),
)


def _infer_document_type(category: str, title: str, relative_path: str) -> str | None:
    text = f"{category} {title} {relative_path}".casefold()
    rules = (
        ("application_notice", ("申报通知", "组织申报", "征集通知", "通知")),
        ("application_guide", ("申报指南", "项目指南", "指南")),
        ("application_template", ("申报书模板", "申请书模板", "填报模板", "模板")),
        ("budget_rule", ("预算依据", "预算规则", "经费管理", "资金管理", "预算")),
        ("management_rule", ("管理办法", "实施细则", "管理规定")),
        ("historical_proposal", ("历史申报书", "申报案例", "申请书")),
        ("team_achievement", ("团队成果", "专利", "论文", "获奖")),
        ("research_foundation", ("已有研究基础", "研究基础", "前期基础")),
    )
    for document_type, markers in rules:
        if any(marker.casefold() in text for marker in markers):
            return document_type
    return None


def _infer_document_metadata(
    *,
    category: str,
    title: str,
    relative_path: str,
    content: str,
) -> tuple[str | None, str | None, int | None]:
    header = f"{title}\n{relative_path}\n{content[:3000]}"
    authority_match = _AUTHORITY_RE.search(header)
    year_match = _YEAR_RE.search(f"{title}\n{relative_path}\n{content[:1200]}")
    return (
        authority_match.group(1) if authority_match else None,
        _infer_document_type(category, title, relative_path),
        int(year_match.group(1)) if year_match else None,
    )


_TECHNICAL_TERM_PATTERNS: tuple[str, ...] = (
    "Hertz",
    "Vesic",
    "落球",
    "路基",
    "填方材料",
    "压实度",
    "回弹模量",
    "变形模量",
    "动回弹模量",
    "连续压实",
    "弯沉",
    "载荷板",
    "瑞雷波",
    "岩土",
    "质量评估",
    "现场检测",
)

_METHOD_PATTERNS: tuple[str, ...] = (
    "理论建模",
    "现场检测",
    "试验验证",
    "对比验证",
    "数值模拟",
    "算法",
    "模型",
    "装备",
    "评估方法",
    "检测技术",
)

_RESEARCH_OBJECT_PATTERNS: tuple[str, ...] = (
    "路基",
    "填方材料",
    "岩土材料",
    "路面",
    "施工质量",
    "公路",
    "铁路",
)

_NOISY_KEYWORDS = {
    "image",
    "images",
    "jpg",
    "jpeg",
    "png",
    "details",
    "summary",
    "natural_image",
    "text_image",
    "flowchart",
    "mermaid",
    "close",
    "with",
    "visible",
    "text",
    "symbols",
    "mathrm",
    "mathbf",
    "begin",
    "end",
}

_ALLOWED_ASCII_KEYWORDS = {
    "hertz",
    "vesic",
    "abaqus",
    "python",
    "pycharm",
    "ann",
    "ict",
    "fwd",
    "k30",
    "vcv",
    "cev",
    "thornton",
}


@dataclass(frozen=True)
class _StructuredHeadingBlock:
    level: int
    heading: str
    block: str
    own_content: str
    heading_path: tuple[str, ...]
    child_headings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_children(self) -> bool:
        return bool(self.child_headings)


@dataclass(frozen=True)
class _SemanticChunkCandidate:
    level: int
    heading: str
    content: str
    proposal_sections: tuple[str, ...]
    chunk_kind: str
    content_role: str
    heading_path: tuple[str, ...]
    chunk_order: int
    source_anchor: str


def _resolve_folder(folder_path: str, *, user_id: str | None = None) -> Path:
    raw = Path(folder_path)
    if raw.is_absolute():
        raise ValueError("folder_path must be relative to the knowledge-base root.")
    root = _knowledge_root_path(user_id=user_id)
    resolved = (root / raw).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError("Access denied: path traversal detected.") from None
    return resolved


def _relative_to_root(path: Path, *, user_id: str | None = None) -> str:
    root = _knowledge_root_path(user_id=user_id)
    return path.resolve().relative_to(root).as_posix()


def _iter_source_files(folder: Path, request: KnowledgeIndexBuildRequest) -> list[Path]:
    extensions = {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in request.include_extensions}
    if not extensions:
        extensions = _SUPPORTED_TEXT_EXTENSIONS

    pattern = "**/*" if request.recursive else "*"
    files = [
        path
        for path in folder.glob(pattern)
        if path.is_file()
        and path.suffix.lower() in extensions
        and not any(part.startswith(".") for part in path.relative_to(folder).parts)
        and not any(part in _IGNORED_SCAN_PARTS for part in path.relative_to(folder).parts)
        and not path.name.lower().endswith(".mineru.md")
        and path.relative_to(folder).as_posix().lower() != "readme.md"
    ]
    files.sort(key=lambda path: path.as_posix())
    return files[: request.max_files]


def _deduplicate_source_files(files: list[Path], folder: Path) -> tuple[list[Path], list[Path]]:
    """Prefer the best source format for the same file stem in the same folder."""

    selected_by_key: dict[tuple[str, str], Path] = {}
    duplicates: list[Path] = []
    for path in files:
        relative_parent = path.parent.resolve().relative_to(folder.resolve()).as_posix()
        key = (relative_parent, path.stem.casefold())
        current = selected_by_key.get(key)
        if current is None:
            selected_by_key[key] = path
            continue

        current_priority = _SOURCE_FORMAT_PRIORITY.get(current.suffix.lower(), 0)
        next_priority = _SOURCE_FORMAT_PRIORITY.get(path.suffix.lower(), 0)
        if next_priority > current_priority:
            duplicates.append(current)
            selected_by_key[key] = path
        else:
            duplicates.append(path)

    selected = sorted(selected_by_key.values(), key=lambda path: path.as_posix())
    duplicates.sort(key=lambda path: path.as_posix())
    return selected, duplicates


def _file_fingerprint(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    stat = path.stat()
    return {
        "source_sha256": digest.hexdigest(),
        "source_mtime_ns": stat.st_mtime_ns,
        "source_size": stat.st_size,
        "indexer_version": _INDEXER_VERSION,
    }


def _source_metadata_matches(entry: KnowledgeIndexEntry, fingerprint: dict[str, object]) -> bool:
    metadata = entry.metadata or {}
    return all(metadata.get(key) == value for key, value in fingerprint.items())


def _entries_for_source(entries: list[KnowledgeIndexEntry], source_relative_path: str) -> list[KnowledgeIndexEntry]:
    return [entry for entry in entries if _source_file_for_entry(entry) == source_relative_path or entry.file_path == source_relative_path or entry.source_file_path == source_relative_path]


def _source_entries_complete(root: Path, entries: list[KnowledgeIndexEntry]) -> bool:
    if not entries:
        return False
    for entry in entries:
        if entry.file_path.startswith(f"{_GENERATED_CHUNKS_DIR}/") and not (root / entry.file_path).exists():
            return False
        if entry.chunk_file_path and not (root / entry.chunk_file_path).exists():
            return False
    return True


def _extract_headings(content: str) -> list[tuple[int, str]]:
    headings: list[tuple[int, str]] = []
    for line in content.splitlines():
        match = _MARKDOWN_HEADING_RE.match(line)
        if match:
            heading = match.group(2).strip()
            headings.append((_infer_heading_level(heading, len(match.group(1))), heading))
    return headings


def _infer_heading_level(heading: str, markdown_level: int) -> int:
    if _ZH_SECTION_HEADING_RE.match(heading):
        return 1
    decimal = _DECIMAL_HEADING_RE.match(heading)
    if decimal:
        return min(decimal.group(1).count(".") + 1, 6)
    if _SIMPLE_DOT_HEADING_RE.match(heading):
        return max(markdown_level + 1, 3)
    if _TOP_NUMBER_HEADING_RE.match(heading):
        return 1
    return markdown_level


def _extract_heading_blocks(content: str) -> list[tuple[int, str, str]]:
    """Return markdown heading blocks as (level, heading, content)."""

    lines = content.splitlines()
    headings: list[tuple[int, str, int]] = []
    for index, line in enumerate(lines):
        match = _MARKDOWN_HEADING_RE.match(line)
        if match:
            heading = match.group(2).strip()
            headings.append((_infer_heading_level(heading, len(match.group(1))), heading, index))

    blocks: list[tuple[int, str, str]] = []
    for offset, (level, heading, start) in enumerate(headings):
        end = len(lines)
        for next_level, _, next_start in headings[offset + 1 :]:
            if next_level <= level:
                end = next_start
                break
        block = "\n".join(lines[start:end]).strip()
        if block:
            blocks.append((level, heading, block))
    return blocks


def _structured_heading_blocks(content: str) -> list[_StructuredHeadingBlock]:
    lines = content.splitlines()
    headings: list[tuple[int, str, int, tuple[str, ...]]] = []
    stack: list[tuple[int, str]] = []

    for index, line in enumerate(lines):
        match = _MARKDOWN_HEADING_RE.match(line)
        if not match:
            continue
        heading = match.group(2).strip()
        level = _infer_heading_level(heading, len(match.group(1)))
        while stack and stack[-1][0] >= level:
            stack.pop()
        heading_path = tuple([item[1] for item in stack] + [heading])
        headings.append((level, heading, index, heading_path))
        stack.append((level, heading))

    blocks: list[_StructuredHeadingBlock] = []
    for offset, (level, heading, start, heading_path) in enumerate(headings):
        end = len(lines)
        first_child_start: int | None = None
        child_headings: list[str] = []
        for next_level, next_heading, next_start, _ in headings[offset + 1 :]:
            if next_level <= level:
                end = next_start
                break
            if first_child_start is None:
                first_child_start = next_start
            if next_level == level + 1:
                child_headings.append(next_heading)

        own_end = first_child_start if first_child_start is not None else end
        block = "\n".join(lines[start:end]).strip()
        own_content = "\n".join(lines[start:own_end]).strip()
        if block:
            blocks.append(
                _StructuredHeadingBlock(
                    level=level,
                    heading=heading,
                    block=block,
                    own_content=own_content,
                    heading_path=heading_path,
                    child_headings=tuple(child_headings),
                )
            )
    return blocks


def _proposal_label_for_key(key: str) -> str | None:
    for rule_key, label, _ in _PROPOSAL_SECTION_RULES:
        if rule_key == key:
            return label
    return None


def _proposal_key_for_value(value: str) -> str | None:
    for key, label, _ in _PROPOSAL_SECTION_RULES:
        if value in {key, label}:
            return key
    return None


def _add_unique(values: list[str], additions: list[str] | tuple[str, ...]) -> None:
    seen = set(values)
    for addition in additions:
        if addition and addition not in seen:
            values.append(addition)
            seen.add(addition)


def _section_pair(key: str) -> list[str]:
    label = _proposal_label_for_key(key)
    return [key, label] if label else [key]


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword and keyword.lower() in lowered for keyword in keywords)


def _infer_content_role(heading: str, content: str) -> str:
    text = f"{heading}\n{content[:1200]}"
    heading_text = heading.lower()
    if _contains_any(heading_text, ("参考", "文献", "标准", "规范", "指南", "管理办法", "reference", "standard")):
        return "reference"
    if _contains_any(text, ("预算", "经费", "budget", "funding")):
        return "budget_item"
    if _contains_any(text, ("创新", "特色", "先进性", "novelty", "innovation")):
        return "innovation"
    if _contains_any(text, ("技术路线", "路线图", "实施路径", "roadmap")):
        return "route_step"
    if _contains_any(text, ("研究目标", "目标", "objective")):
        return "objective"
    if _contains_any(text, ("研究内容", "研究任务", "关键科学问题", "research content", "task")):
        return "research_task"
    if _contains_any(text, ("研究基础", "工作基础", "前期基础", "已有基础", "foundation")):
        return "basis"
    if _contains_any(text, ("问题", "不足", "痛点", "缺陷", "gap")):
        return "problem"
    if _contains_any(text, ("背景", "意义", "应用前景", "significance", "background")):
        return "background"
    if _contains_any(
        text,
        (
            "方案",
            "实施",
            "设计",
            "方法",
            "模型",
            "系统",
            "构建",
            "对齐",
            "表征",
            "检测",
            "验证",
            "solution",
            "method",
        ),
    ):
        return "method_design"
    return "evidence"


def _primary_section_key_for(
    heading: str,
    content: str,
    detected_sections: list[str],
    inherited_sections: list[str],
) -> str | None:
    text = f"{heading}\n{content[:1200]}"
    heading_text = heading.lower()
    if _contains_any(heading_text, ("参考", "文献", "标准", "规范", "指南", "管理办法", "reference", "standard")):
        return "references"
    if _contains_any(text, ("预算", "经费", "budget", "funding")):
        return "budget_basis"
    if _contains_any(text, ("创新", "特色", "innovation", "novelty")):
        return "innovation_points"
    if _contains_any(text, ("技术路线", "路线图", "实施路径", "roadmap")):
        return "technical_route"
    if _contains_any(text, ("国内外研究现状", "研究现状", "发展趋势", "文献综述", "state of the art")):
        return "domestic_foreign_status"
    if _contains_any(text, ("研究目标", "研究内容", "研究任务", "关键科学问题", "research content")):
        return "research_content"
    if _contains_any(text, ("申报条件", "申报要求", "申请资格", "eligibility")):
        return "application_requirements"
    if _contains_any(text, ("预期成果", "考核指标", "成果形式", "deliverable")):
        return "expected_outputs"
    if _contains_any(text, ("团队成果", "论文", "专利", "软著", "获奖", "publication", "patent")):
        return "team_achievements"
    if _contains_any(text, ("研究基础", "工作基础", "前期基础", "已有基础", "foundation")):
        return "research_basis"
    if _contains_any(
        text,
        (
            "技术方案",
            "研究方案",
            "实施方案",
            "实验方案",
            "试验方案",
            "设计",
            "方法",
            "模型",
            "系统",
            "构建",
            "对齐",
            "表征",
            "检测",
            "验证",
            "solution",
            "method",
        ),
    ):
        return "technical_solution"
    if _contains_any(text, ("立项依据", "研究意义", "背景", "应用前景", "significance", "background")):
        return "background_significance"

    for section in [*detected_sections, *inherited_sections]:
        key = _proposal_key_for_value(section)
        if key:
            return key
    return None


def _sections_with_primary(primary_key: str | None, detected_sections: list[str], inherited_sections: list[str]) -> tuple[str, ...]:
    values: list[str] = []
    if primary_key:
        _add_unique(values, _section_pair(primary_key))
    _add_unique(values, detected_sections)
    _add_unique(values, inherited_sections)
    return tuple(values[:8])


def _parent_summary_content(block: _StructuredHeadingBlock, *, max_chars: int = _MAX_PARENT_SUMMARY_CHARS) -> str:
    summary = _extract_summary(block.own_content or block.block, max_chars=max_chars)
    if not summary:
        summary = "本节为上级结构节点，主要用于组织下级证据块。"
    lines = [f"## {block.heading} 摘要", "", summary.strip()]
    if block.child_headings:
        lines.extend(["", "### 子章节"])
        lines.extend(f"- {heading}" for heading in block.child_headings[:20])
    return "\n".join(lines).strip()


def _text_units(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        paragraphs = [text.strip()] if text.strip() else []
    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= _MAX_CHUNK_CHARS:
            units.append(paragraph)
            continue
        sentences = [part.strip() for part in re.split(r"(?<=[。！？；;.!?])", paragraph) if part.strip()]
        if len(sentences) <= 1:
            units.extend(paragraph[index : index + _TARGET_CHUNK_CHARS] for index in range(0, len(paragraph), _TARGET_CHUNK_CHARS))
        else:
            units.extend(sentences)
    return units


def _split_leaf_block(heading: str, block: str) -> list[tuple[str, str]]:
    if len(block) <= _MAX_CHUNK_CHARS:
        return [(heading, block)]

    lines = block.splitlines()
    body_lines = lines[1:] if lines and _MARKDOWN_HEADING_RE.match(lines[0]) else lines
    units = _text_units("\n".join(body_lines).strip())
    parts: list[str] = []
    current: list[str] = []
    current_chars = 0
    for unit in units:
        unit_chars = len(unit)
        if current and current_chars + unit_chars > _TARGET_CHUNK_CHARS and current_chars >= _MIN_CHUNK_CHARS:
            parts.append("\n\n".join(current).strip())
            current = []
            current_chars = 0
        current.append(unit)
        current_chars += unit_chars
    if current:
        parts.append("\n\n".join(current).strip())

    split_blocks: list[tuple[str, str]] = []
    total = len(parts)
    for index, part in enumerate(parts, start=1):
        part_heading = f"{heading} 第{index}部分" if total > 1 else heading
        split_blocks.append((part_heading, f"## {part_heading}\n\n{part}".strip()))
    return split_blocks


def _body_text_chars(block: str) -> int:
    body_lines = [line.strip() for line in block.splitlines() if line.strip() and not _MARKDOWN_HEADING_RE.match(line.strip())]
    return len("\n".join(body_lines))


def _compact_heading_text(heading: str) -> str:
    return re.sub(r"\s+", "", heading).strip()


def _meaningful_body_lines(block: str) -> list[str]:
    return [line.strip() for line in block.splitlines() if line.strip() and not _MARKDOWN_HEADING_RE.match(line.strip())]


def _looks_like_toc_content(block: str) -> bool:
    lines = _meaningful_body_lines(block)
    if len(lines) < 5:
        return False
    toc_like = 0
    for line in lines[:80]:
        compact = _compact_heading_text(line)
        if _TOC_DOT_LEADER_RE.match(line) or _TOC_NUMBERED_PAGE_RE.match(line):
            toc_like += 1
        elif len(compact) <= 42 and re.search(r"\d$", compact) and re.match(r"^\d+(?:\.\d+)*", compact):
            toc_like += 1
    checked = min(len(lines), 80)
    return toc_like >= 5 and toc_like / checked >= 0.5


def _looks_like_cover_content(block: str) -> bool:
    text = "\n".join(_meaningful_body_lines(block))
    markers = ("报告名称", "主持单位", "编制单位", "编制时间")
    return sum(1 for marker in markers if marker in text) >= 2 and len(text) < 1200


def _is_low_value_front_matter(block: _StructuredHeadingBlock) -> bool:
    compact_heading = _compact_heading_text(block.heading)
    if compact_heading in _LOW_VALUE_EXACT_HEADINGS:
        return True
    if any(marker in compact_heading for marker in _LOW_VALUE_HEADING_MARKERS):
        return True
    if _looks_like_cover_content(block.block):
        return True
    if _looks_like_toc_content(block.block):
        return True
    return False


def _is_thin_leaf_block(block: _StructuredHeadingBlock) -> bool:
    if block.has_children or _body_text_chars(block.block) >= 80:
        return False
    text = f"{block.heading}\n{block.block}"
    return not any(marker in text for marker in _SHORT_BLOCK_KEEP_MARKERS)


def _build_semantic_chunk_candidates(content: str, category: str) -> list[_SemanticChunkCandidate]:
    candidates: list[_SemanticChunkCandidate] = []
    for block in _structured_heading_blocks(content):
        if block.level > 5:
            continue
        if _is_generic_wrapper_heading(block.heading):
            continue
        if _is_low_value_front_matter(block):
            continue
        if _is_thin_leaf_block(block):
            continue

        context_headings = "\n".join(block.heading_path[:-1])
        inherited_sections = _proposal_sections_for(context_headings, "") if context_headings else []
        target_text = block.own_content if block.has_children else block.block
        detected_sections = _proposal_sections_for(block.heading, target_text)
        primary_key = _primary_section_key_for(block.heading, target_text, detected_sections, inherited_sections)
        proposal_sections = _sections_with_primary(primary_key, detected_sections, inherited_sections)
        if not proposal_sections:
            continue

        if block.has_children:
            summary_heading = f"{block.heading} 摘要"
            candidates.append(
                _SemanticChunkCandidate(
                    level=block.level,
                    heading=summary_heading,
                    content=_parent_summary_content(block),
                    proposal_sections=proposal_sections,
                    chunk_kind="parent_summary",
                    content_role="section_summary",
                    heading_path=block.heading_path,
                    chunk_order=len(candidates) + 1,
                    source_anchor=block.heading,
                )
            )
            continue

        content_role = _infer_content_role(block.heading, block.block)
        keep_short_sections = {
            "application_requirements",
            "budget_basis",
            "domestic_foreign_status",
            "expected_outputs",
            "references",
            "research_content",
            "technical_route",
        }
        if _body_text_chars(block.block) < 80 and content_role in {"evidence", "problem", "method_design"} and not any(section in proposal_sections for section in keep_short_sections):
            continue
        for part_heading, part_content in _split_leaf_block(block.heading, block.block):
            candidates.append(
                _SemanticChunkCandidate(
                    level=block.level,
                    heading=part_heading,
                    content=part_content,
                    proposal_sections=proposal_sections,
                    chunk_kind="leaf_evidence",
                    content_role=content_role,
                    heading_path=block.heading_path,
                    chunk_order=len(candidates) + 1,
                    source_anchor=block.heading,
                )
            )
    return candidates


def _extract_title(path: Path, content: str) -> str:
    for level, heading in _extract_headings(content):
        if level == 1 and heading not in _GENERIC_TITLES and not heading.startswith("（") and not _TOP_NUMBER_HEADING_RE.match(heading) and not _DECIMAL_HEADING_RE.match(heading):
            return heading
    return path.stem


def _extract_summary(content: str, *, max_chars: int = 800) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if _MARKDOWN_HEADING_RE.match(stripped):
            continue
        if stripped in _GENERIC_TITLES or "参照以下提纲" in stripped:
            continue
        current.append(stripped)
    if current:
        paragraphs.append(" ".join(current))
    summary = next((paragraph for paragraph in paragraphs if paragraph), "")
    return summary[:max_chars]


def _content_preview(content: str, *, max_chars: int = 2400) -> str:
    lines: list[str] = []
    for line in content.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if not stripped or stripped in _GENERIC_TITLES or "参照以下提纲" in stripped:
            continue
        lines.append(stripped)
        if sum(len(item) for item in lines) >= max_chars:
            break
    return "\n".join(lines)[:max_chars]


def _default_category_and_domain(relative_path: str) -> tuple[str, str | None, str]:
    parts = Path(relative_path).parts
    raw_category = parts[0] if len(parts) >= 2 else "未分类"
    category = _CATEGORY_ALIASES.get(raw_category, raw_category)
    domain = parts[1] if len(parts) >= 3 else None
    folder_path = Path(relative_path).parent.as_posix()
    return category, domain, "" if folder_path == "." else folder_path


def _guess_use_for(category: str, heading: str) -> list[str]:
    values = {category}
    heading_text = heading.lower()
    if "国外" in heading or "international" in heading_text:
        values.add("国外研究现状")
        values.add("国内外研究现状")
    if "国内" in heading or "domestic" in heading_text:
        values.add("国内研究现状")
        values.add("国内外研究现状")
    if "问题" in heading or "不足" in heading or "gap" in heading_text:
        values.add("研究空白")
        values.add("立项必要性")
    if "技术路线" in heading:
        values.add("技术路线")
    if "创新" in heading:
        values.add("创新点")
    if "预算" in heading:
        values.add("项目预算")
    if "基础" in heading:
        values.add("已有研究基础")
    return sorted(values)


def _proposal_sections_for(heading: str, content: str) -> list[str]:
    text = f"{heading}\n{content}"
    sections: list[str] = []
    seen: set[str] = set()
    for key, label, keywords in _PROPOSAL_SECTION_RULES:
        if any(keyword in text for keyword in keywords):
            for value in (key, label):
                if value not in seen:
                    seen.add(value)
                    sections.append(value)
    return sections


def _is_generic_wrapper_heading(heading: str) -> bool:
    wrapper_markers = (
        "建议8000字",
        "立项依据与研究内容",
        "研究基础与工作条件",
        "其他需要说明",
    )
    return any(marker in heading for marker in wrapper_markers)


def _canonical_proposal_label(proposal_sections: list[str], fallback: str) -> str:
    if "technical_solution" in proposal_sections or "技术方案" in proposal_sections:
        return "技术方案"
    for _, label, _ in _PROPOSAL_SECTION_RULES:
        if label in proposal_sections:
            return label
    return fallback


def _compact_proposal_sections(proposal_sections: list[str], fallback: str) -> list[str]:
    label = _canonical_proposal_label(proposal_sections, fallback)
    compact: list[str] = []
    for key, rule_label, _ in _PROPOSAL_SECTION_RULES:
        if rule_label == label:
            compact.extend([key, rule_label])
            break
    if not compact:
        compact.append(label)

    for section in proposal_sections:
        if section not in compact:
            compact.append(section)
        if len(compact) >= 6:
            break
    return compact


def _collect_patterns(text: str, patterns: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for pattern in patterns:
        if pattern.lower() in text.lower() and pattern not in values:
            values.append(pattern)
    return values


def _extra_keywords(text: str, *, limit: int = 12) -> list[str]:
    candidates = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,12}", text)
    ignored = {"项目", "研究", "内容", "方法", "技术", "问题", "进行", "通过", "基于", "形成", "相关"}
    keywords: list[str] = []
    for candidate in candidates:
        lowered = candidate.lower()
        if candidate in ignored or lowered in _NOISY_KEYWORDS or (candidate.isascii() and lowered not in _ALLOWED_ASCII_KEYWORDS) or candidate.isdigit() or len(candidate) > 24 or re.fullmatch(r"[a-f0-9]{12,}", lowered):
            continue
        if candidate not in keywords:
            keywords.append(candidate)
        if len(keywords) >= limit:
            break
    return keywords


def _limited(values: list[str], limit: int) -> list[str]:
    return values[:limit]


def _safe_filename_part(value: str, *, max_chars: int = 80) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|$`{}\r\n\t]+', "_", value).strip(" ._")
    cleaned = re.sub(r"\s+", "", cleaned)
    return (cleaned or "section")[:max_chars]


def _section_topic_filename(heading: str) -> str:
    topic = heading.strip().lstrip("#").strip()
    topic = re.sub(r"^\d+\.(\d{4}\s*年)", r"\1", topic)
    if not re.match(r"^\d{4}\s*年", topic):
        topic = re.sub(r"^[（(]\s*\d+(?:\.\d+)*\s*[）)]\s*", "", topic)
        topic = re.sub(r"^\d+(?:\.\d+)*[．、.）)]?\s*", "", topic)
    topic = re.sub(r"^[（(]\s*[一二三四五六七八九十]+\s*[）)]\s*", "", topic)
    topic = re.sub(r"^[一二三四五六七八九十]+[．、.）)]\s*", "", topic)
    topic = re.sub(r"[（(].*?[）)]", "", topic)
    topic = topic.strip(" ；;：:）)")
    return f"{_safe_filename_part(topic or heading, max_chars=42)}.md"


def _chunk_file_matches_source(path: Path, source_relative_path: str) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return f"source_file: {source_relative_path}" in text[:2000]


def _chunk_file_matches_anchor(path: Path, source_relative_path: str, heading: str) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    front_matter = text[:2000]
    return f"source_file: {source_relative_path}" in front_matter and f"source_anchor: {heading}" in front_matter


def _deduplicated_chunk_path(chunk_path: Path, source_relative_path: str, heading: str) -> Path:
    if not chunk_path.exists() or _chunk_file_matches_anchor(chunk_path, source_relative_path, heading):
        return chunk_path
    for counter in range(2, 1000):
        candidate = chunk_path.with_name(f"{chunk_path.stem}_{counter}{chunk_path.suffix}")
        if not candidate.exists() or _chunk_file_matches_anchor(candidate, source_relative_path, heading):
            return candidate
    raise FileExistsError(f"Cannot find a non-conflicting chunk file name for {chunk_path}.")


def _write_section_chunk(
    *,
    root: Path,
    source_relative_path: str,
    title: str,
    heading: str,
    content: str,
    category: str,
    domain: str | None,
    proposal_sections: list[str],
    keywords: list[str],
    technical_terms: list[str],
    methods: list[str],
    research_objects: list[str],
    source_anchor: str | None = None,
    chunk_kind: str = "leaf_evidence",
    content_role: str = "evidence",
    heading_path: tuple[str, ...] = (),
    chunk_order: int = 0,
) -> str:
    label = _canonical_proposal_label(proposal_sections, category)
    project_folder = _safe_filename_part(title, max_chars=120)
    filename = _section_topic_filename(heading)
    chunk_path = root / _GENERATED_CHUNKS_DIR / label / project_folder / filename
    chunk_path.parent.mkdir(parents=True, exist_ok=True)
    anchor = source_anchor or heading
    chunk_path = _deduplicated_chunk_path(chunk_path, source_relative_path, anchor)
    primary_section = proposal_sections[0] if proposal_sections else ""
    front_matter = [
        "---",
        f"source_file: {source_relative_path}",
        f"source_anchor: {anchor}",
        f"source_title: {title}",
        f"proposal_sections: [{', '.join(proposal_sections)}]",
        f"primary_section: {primary_section}",
        f"content_role: {content_role}",
        f"chunk_kind: {chunk_kind}",
        f"chunk_order: {chunk_order}",
        f"char_count: {len(content)}",
        f"heading_path: [{', '.join(heading_path or (heading,))}]",
        f"domain: {domain or ''}",
        f"category: {category}",
        f"keywords: [{', '.join(keywords[:20])}]",
        f"technical_terms: [{', '.join(technical_terms)}]",
        f"methods: [{', '.join(methods)}]",
        f"research_objects: [{', '.join(research_objects)}]",
        "---",
        "",
    ]
    chunk_path.write_text("\n".join(front_matter) + content.strip() + "\n", encoding="utf-8")
    return chunk_path.relative_to(root).as_posix()


def _cleanup_generated_chunks_for_source(root: Path, source_relative_path: str) -> int:
    chunks_root = root / _GENERATED_CHUNKS_DIR
    if not chunks_root.exists():
        return 0
    old_prefixes = (
        f"{_safe_filename_part(Path(source_relative_path).stem)}__",
        f"*__{_safe_filename_part(Path(source_relative_path).stem)}__",
    )
    removed = 0
    for path in chunks_root.rglob("*.md"):
        if path.is_file() and _chunk_file_matches_source(path, source_relative_path):
            path.unlink()
            removed += 1
    for prefix in old_prefixes:
        for path in chunks_root.rglob(f"{prefix}*.md"):
            if path.is_file():
                path.unlink()
                removed += 1
    for directory in sorted((path for path in chunks_root.rglob("*") if path.is_dir()), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    return removed


def _cleanup_unreferenced_generated_chunks(root: Path, indexes: list[KnowledgeIndexEntry]) -> int:
    chunks_root = root / _GENERATED_CHUNKS_DIR
    if not chunks_root.exists():
        return 0
    referenced = set()
    for entry in indexes:
        chunk_path = entry.chunk_file_path
        if not chunk_path and entry.file_path.startswith(f"{_GENERATED_CHUNKS_DIR}/"):
            chunk_path = entry.file_path
        if chunk_path:
            referenced.add((root / chunk_path).resolve())
    removed = 0
    for path in chunks_root.rglob("*.md"):
        if path.resolve() not in referenced:
            path.unlink()
            removed += 1
    for directory in sorted((path for path in chunks_root.rglob("*") if path.is_dir()), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    return removed


def _build_sections(category: str, content: str) -> list[KnowledgeIndexSection]:
    sections: list[KnowledgeIndexSection] = []
    for level, heading in _extract_headings(content):
        if level > 3:
            continue
        sections.append(
            KnowledgeIndexSection(
                heading=heading,
                anchor=heading,
                use_for=_guess_use_for(category, heading),
                summary=f"文件中的“{heading}”章节，可按索引用于相关申报书章节。",
            )
        )
    return sections


def _keywords_from_path_and_title(relative_path: str, title: str, domain: str | None) -> list[str]:
    values = [title]
    for part in Path(relative_path).parts:
        suffix = Path(part).suffix.lower()
        if suffix in _SUPPORTED_TEXT_EXTENSIONS:
            values.append(part[: -len(suffix)])
        else:
            values.append(part)
    if domain:
        values.append(domain)
    keywords: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            keywords.append(cleaned)
    return keywords


def _index_entry_from_payload(
    payload: KnowledgeIndexEntryCreate,
    *,
    existing: KnowledgeIndexEntry | None = None,
) -> KnowledgeIndexEntry:
    timestamp = now_iso()
    data = payload.model_dump()
    data["file_path"] = Path(payload.file_path).as_posix()
    return KnowledgeIndexEntry(
        index_id=existing.index_id if existing else f"idx_{uuid.uuid4().hex}",
        created_at=existing.created_at if existing else timestamp,
        updated_at=timestamp,
        **data,
    )


def _source_file_for_entry(entry: KnowledgeIndexEntry) -> str:
    return entry.source_file_path or str(entry.metadata.get("source_file_path") or entry.file_path)


def _source_exists(root: Path, entry: KnowledgeIndexEntry) -> bool:
    try:
        resolved = (root / _source_file_for_entry(entry)).resolve()
        resolved.relative_to(root)
        return resolved.exists()
    except ValueError:
        return False


def _increment_count(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _count_chunk_files(root: Path) -> int:
    chunks_root = root / _GENERATED_CHUNKS_DIR
    if not chunks_root.exists():
        return 0
    return sum(1 for path in chunks_root.rglob("*.md") if path.is_file())


def _build_scale_stats(
    *,
    root: Path,
    discovered_source_files: int,
    final_indexes: list[KnowledgeIndexEntry],
    elapsed_seconds: float,
) -> dict[str, object]:
    index_path = root / "index.json"
    sqlite_index_path = sqlite_knowledge_index_path(root)
    index_json_bytes = index_path.stat().st_size if index_path.exists() else 0
    sqlite_index_bytes = sqlite_index_path.stat().st_size if sqlite_index_path.exists() else 0
    document_entries_total = sum(1 for entry in final_indexes if entry.entry_type == "document")
    section_entries_total = len(final_indexes) - document_entries_total
    return {
        "source_files_scanned": discovered_source_files,
        "index_entries_total": len(final_indexes),
        "document_entries_total": document_entries_total,
        "section_entries_total": section_entries_total,
        "chunk_files_total": _count_chunk_files(root),
        "index_json_bytes": index_json_bytes,
        "sqlite_index_enabled": sqlite_index_path.exists(),
        "sqlite_index_bytes": sqlite_index_bytes,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "thresholds": {
            "source_files_warning": _SOURCE_FILE_WARNING_THRESHOLD,
            "index_entries_warning": _INDEX_ENTRY_WARNING_THRESHOLD,
            "index_json_bytes_warning": _INDEX_JSON_BYTES_WARNING_THRESHOLD,
            "build_seconds_warning": _BUILD_SECONDS_WARNING_THRESHOLD,
        },
    }


def _scale_warnings(scale_stats: dict[str, object], *, max_files_reached: bool) -> list[str]:
    warnings: list[str] = []
    if max_files_reached:
        warnings.append("本次扫描数量达到 max_files 限制，可能还有文件未纳入索引。")
    if not scale_stats.get("sqlite_index_enabled"):
        warnings.append("SQLite 本地检索索引未生成，当前将回退到 index.json 检索。")
    if int(scale_stats.get("source_files_scanned", 0)) >= _SOURCE_FILE_WARNING_THRESHOLD:
        warnings.append("知识库源文件数量较多，当前会优先使用 SQLite FTS5 检索；建议继续观察 SQLite 索引大小和查询耗时。")
    if int(scale_stats.get("index_entries_total", 0)) >= _INDEX_ENTRY_WARNING_THRESHOLD:
        warnings.append("索引条目数量较多，已启用 SQLite 检索；前端列表仍应避免一次性加载全部条目。")
    if int(scale_stats.get("index_json_bytes", 0)) >= _INDEX_JSON_BYTES_WARNING_THRESHOLD:
        warnings.append("index.json 文件较大，建议将前端列表查询分页化，并保留 JSON 仅作备份/导出。")
    if float(scale_stats.get("elapsed_seconds", 0.0)) >= _BUILD_SECONDS_WARNING_THRESHOLD:
        warnings.append("本次索引构建耗时较长，建议记录文件 hash/mtime 并跳过未变化文件。")
    return warnings


def build_knowledge_index_from_folder(
    request: KnowledgeIndexBuildRequest,
    *,
    user_id: str | None = None,
) -> KnowledgeIndexBuildResponse:
    """Scan a knowledge-base folder and build LLM-Wiki index entries."""

    started_at = time.monotonic()
    root = _knowledge_root_path(user_id=user_id)
    folder = _resolve_folder(request.folder_path, user_id=user_id)
    if not folder.exists():
        raise FileNotFoundError(request.folder_path)
    if not folder.is_dir():
        raise ValueError("folder_path must point to a directory.")

    storage = get_knowledge_storage()
    warnings: list[str] = []
    # Images are intentionally recognized at build time, not upload time.  The
    # local import avoids coupling the text indexer's module initialization to
    # optional model providers.
    from deerflow.knowledge.assets import extract_pending_knowledge_evidence

    _, image_warnings = extract_pending_knowledge_evidence(user_id=user_id)
    warnings.extend(image_warnings)

    version_backup_path = backup_knowledge_index(user_id=user_id, reason="build_index")
    existing_indexes = storage.list_indexes(user_id=user_id)
    kept_indexes = [entry for entry in existing_indexes if _source_exists(root, entry)]
    deleted = len(existing_indexes) - len(kept_indexes)
    existing_by_file_path = {entry.file_path: entry for entry in kept_indexes}

    skipped = 0
    entries: list[KnowledgeIndexEntry] = []
    parser_counts: dict[str, int] = {}
    parse_errors: list[dict[str, str]] = []
    chunk_files_created = 0
    document_entries = 0
    section_entries = 0
    reused = 0
    discovered_source_files = _iter_source_files(folder, request)
    max_files_reached = len(discovered_source_files) >= request.max_files
    source_files, duplicate_source_files = _deduplicate_source_files(discovered_source_files, folder)
    duplicate_source_paths = [_relative_to_root(path, user_id=user_id) for path in duplicate_source_files]
    if duplicate_source_paths:
        skipped += len(duplicate_source_paths)
        duplicate_path_set = set(duplicate_source_paths)
        kept_indexes = [kept for kept in kept_indexes if _source_file_for_entry(kept) not in duplicate_path_set and kept.file_path not in duplicate_path_set]
        deleted += len(existing_indexes) - deleted - len(kept_indexes)
        for duplicate_path in duplicate_source_paths:
            _cleanup_generated_chunks_for_source(root, duplicate_path)

    for path in source_files:
        relative_path = _relative_to_root(path, user_id=user_id)
        fingerprint = _file_fingerprint(path)
        existing = existing_by_file_path.get(relative_path)
        existing_source_entries = _entries_for_source(kept_indexes, relative_path)
        if (
            request.incremental
            and request.replace_existing
            and existing is not None
            and _source_metadata_matches(existing, fingerprint)
            and _source_entries_complete(root, existing_source_entries)
            and (request.category is None or existing.category == request.category)
            and (request.domain is None or existing.domain == request.domain)
        ):
            reused += len(existing_source_entries)
            continue

        try:
            extraction = extract_text_with_metadata(path)
        except Exception as exc:
            skipped += 1
            parse_errors.append(
                {
                    "file_path": relative_path,
                    "stage": "extract",
                    "error": str(exc),
                }
            )
            warnings.append(f"解析失败，已跳过：{relative_path}；原因：{exc}")
            continue
        content = extraction.content
        _increment_count(parser_counts, extraction.parser)
        if extraction.warning:
            warnings.append(f"{relative_path}: {extraction.warning}")
        if not content.strip():
            skipped += 1
            parse_errors.append(
                {
                    "file_path": relative_path,
                    "stage": "extract",
                    "error": "empty extracted content",
                }
            )
            continue

        default_category, default_domain, folder_path = _default_category_and_domain(relative_path)
        category = request.category or (existing.category if existing and default_category == "未分类" else default_category)
        domain = request.domain or (existing.domain if existing and default_domain is None else default_domain)
        title = _extract_title(path, content)
        inferred_authority, inferred_document_type, inferred_year = _infer_document_metadata(
            category=category,
            title=title,
            relative_path=relative_path,
            content=content,
        )
        authority = inferred_authority or (existing.authority if existing else None)
        document_type = inferred_document_type or (existing.document_type if existing else None)
        year = inferred_year or (existing.year if existing else None)
        sections = _build_sections(category, content)
        applicable_chapters = sorted({use_for for section in sections for use_for in section.use_for} | {category})
        source_keywords = _keywords_from_path_and_title(relative_path, title, domain)
        technical_terms = _collect_patterns(content, _TECHNICAL_TERM_PATTERNS)
        methods = _collect_patterns(content, _METHOD_PATTERNS)
        research_objects = _collect_patterns(content, _RESEARCH_OBJECT_PATTERNS)

        payload = KnowledgeIndexEntryCreate(
            title=title,
            entry_type="document",
            category=category,
            file_path=relative_path,
            domain=domain,
            authority=authority,
            document_type=document_type,
            year=year,
            keywords=source_keywords[:8],
            technical_terms=_limited(technical_terms, 10),
            methods=_limited(methods, 8),
            research_objects=_limited(research_objects, 8),
            proposal_sections=applicable_chapters[:12],
            evidence_type="historical_proposal" if category == "历史申报书" else category,
            source_file_path=relative_path,
            project_types=request.project_types,
            metadata={
                "parser": extraction.parser,
                "parser_cache_hit": extraction.cache_hit,
                **fingerprint,
            },
            confidence=0.75,
        )

        if existing and not request.replace_existing:
            skipped += 1
            entry = existing
        else:
            entry = _index_entry_from_payload(payload, existing=existing)
        entries.append(entry)
        document_entries += 1

        if request.replace_existing:
            source_key = relative_path
            kept_indexes = [kept for kept in kept_indexes if _source_file_for_entry(kept) != source_key and kept.file_path != source_key]
            _cleanup_generated_chunks_for_source(root, source_key)

        for candidate in _build_semantic_chunk_candidates(content, category):
            proposal_sections = list(candidate.proposal_sections)
            compact_sections = _compact_proposal_sections(proposal_sections, category)
            block_keywords = _extra_keywords(f"{candidate.heading}\n{candidate.content}", limit=10)
            block_technical_terms = _collect_patterns(candidate.content, _TECHNICAL_TERM_PATTERNS)
            block_methods = _collect_patterns(candidate.content, _METHOD_PATTERNS)
            block_research_objects = _collect_patterns(candidate.content, _RESEARCH_OBJECT_PATTERNS)
            chunk_file_path = _write_section_chunk(
                root=root,
                source_relative_path=relative_path,
                title=title,
                heading=candidate.heading,
                content=candidate.content,
                category=category,
                domain=domain,
                proposal_sections=proposal_sections,
                keywords=block_keywords,
                technical_terms=block_technical_terms,
                methods=block_methods,
                research_objects=block_research_objects,
                source_anchor=candidate.source_anchor,
                chunk_kind=candidate.chunk_kind,
                content_role=candidate.content_role,
                heading_path=candidate.heading_path,
                chunk_order=candidate.chunk_order,
            )
            chunk_files_created += 1
            section_payload = KnowledgeIndexEntryCreate(
                title=_section_topic_filename(candidate.heading).removesuffix(".md"),
                entry_type="section" if candidate.level <= 2 else "subsection",
                category=category,
                file_path=chunk_file_path,
                domain=domain,
                authority=authority,
                document_type=document_type,
                year=year,
                keywords=[
                    *source_keywords,
                    *[kw for kw in block_keywords if kw not in source_keywords],
                ][:12],
                technical_terms=_limited(block_technical_terms, 10),
                methods=_limited(block_methods, 8),
                research_objects=_limited(block_research_objects, 8),
                proposal_sections=compact_sections,
                evidence_type="historical_proposal" if category == "历史申报书" else category,
                source_file_path=relative_path,
                source_anchor=candidate.source_anchor,
                summary=_extract_summary(candidate.content, max_chars=160),
                project_types=request.project_types,
                metadata={
                    "parser": extraction.parser,
                    "parser_cache_hit": extraction.cache_hit,
                    "source_file_path": relative_path,
                    **fingerprint,
                    "chunk_kind": candidate.chunk_kind,
                    "content_role": candidate.content_role,
                    "heading_path": list(candidate.heading_path),
                    "primary_section": compact_sections[0] if compact_sections else None,
                    "chunk_order": candidate.chunk_order,
                    "char_count": len(candidate.content),
                },
                confidence=0.82,
            )
            existing_chunk = existing_by_file_path.get(chunk_file_path)
            entries.append(_index_entry_from_payload(section_payload, existing=existing_chunk))
            section_entries += 1

    previous_count = len(existing_indexes)
    final_indexes = [*kept_indexes, *entries]
    storage.save_all_indexes(final_indexes, user_id=user_id)
    _cleanup_unreferenced_generated_chunks(root, final_indexes)
    elapsed_seconds = time.monotonic() - started_at
    scale_stats = _build_scale_stats(
        root=root,
        discovered_source_files=len(discovered_source_files),
        final_indexes=final_indexes,
        elapsed_seconds=elapsed_seconds,
    )
    warnings.extend(_scale_warnings(scale_stats, max_files_reached=max_files_reached))

    updated = min(previous_count - deleted, len(entries))
    created = max(0, len(entries) - updated)

    return KnowledgeIndexBuildResponse(
        root_path=str(root),
        scanned_files=len(discovered_source_files),
        created=created,
        updated=updated,
        reused=reused,
        skipped=skipped,
        deleted=deleted,
        document_entries=document_entries,
        section_entries=section_entries,
        chunk_files_created=chunk_files_created,
        deduplicated_files=duplicate_source_paths,
        version_backup_path=version_backup_path,
        parser_counts=parser_counts,
        parse_errors=parse_errors,
        warnings=warnings,
        scale_stats=scale_stats,
        entries=entries,
    )
