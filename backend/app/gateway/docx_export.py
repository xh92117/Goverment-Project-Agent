"""DOCX export helpers for proposal drafts and conversations."""

from __future__ import annotations

import html
import io
import math
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote

from deerflow.knowledge import get_knowledge_asset, get_knowledge_evidence, resolve_asset_file
from deerflow.runtime.user_context import get_effective_user_id

try:  # Pillow is already present in the app environment, but DOCX export can run without it.
    from PIL import Image
except Exception:  # pragma: no cover - optional runtime dependency
    Image = None  # type: ignore[assignment]


ParagraphKind = Literal[
    "body",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "bullet",
    "numbered",
    "table_caption",
    "figure_caption",
    "image_placeholder",
]


@dataclass(frozen=True)
class ParagraphBlock:
    text: str
    kind: ParagraphKind


@dataclass(frozen=True)
class TableBlock:
    rows: list[list[str]]


@dataclass(frozen=True)
class ImageBlock:
    alt: str
    target: str


@dataclass(frozen=True)
class EquationBlock:
    latex: str


@dataclass(frozen=True)
class DocxImage:
    rid: str
    filename: str
    data: bytes
    extension: str
    width_emu: int
    height_emu: int
    description: str


MarkdownBlock = ParagraphBlock | TableBlock | ImageBlock | EquationBlock

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_LIST_ITEM_RE = re.compile(r"^\s{0,3}(?:(?P<bullet>[-+*])|(?P<number>\d{1,3})[.)])\s+(?P<text>.+?)\s*$")
_TABLE_CAPTION_RE = re.compile(r"^\s*表\s*[\d一二三四五六七八九十]+[\s：:、.．].+")
_FIGURE_CAPTION_RE = re.compile(r"^\s*图\s*[\d一二三四五六七八九十]+[\s：:、.．].+")
_IMAGE_ONLY_RE = re.compile(r"^!\[([^\]]*)\]\((.+?)\)\s*$")
_EVIDENCE_CITATION_RE = re.compile(r"(?<![A-Za-z0-9_])evidence:(evd_[A-Za-z0-9_-]+)", re.IGNORECASE)
_EVIDENCE_CITATION_SEGMENT_RE = re.compile(
    r"\s*\|\s*evidence:evd_[A-Za-z0-9_-]+|(?<![A-Za-z0-9_])evidence:evd_[A-Za-z0-9_-]+",
    re.IGNORECASE,
)
_EVIDENCE_ID_RE = re.compile(r"evd_[A-Za-z0-9_-]+", re.IGNORECASE)
_INLINE_MATH_RE = re.compile(r"(\$[^$\n]+\$|\\\(.+?\\\))")
_INLINE_MARKDOWN_RE = re.compile(
    r"(!\[([^\]]*)\]\([^)]+\)|\[([^\]]+)\]\([^)]+\)|`([^`\n]+)`|"
    r"\*\*([^*\n]+)\*\*|__([^_\n]+)__|\*([^*\n]+)\*|_([^_\n]+)_|~~([^~\n]+)~~)"
)
_HORIZONTAL_RULE_RE = re.compile(r"^\s*(?:[-*_]\s*){3,}$")
_HEADING_NUMBER_RE = re.compile(
    r"^\s*(?:"
    r"\d+(?:\.\d+)*[.)]?\s+|"
    r"\d{1,3}[\u3001\u3002\uff0c\uff1a\uff09]\s*|"
    r"[\uff08(]?\s*[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e]+"
    r"[\uff09)\u3001\u3002\uff0c\uff1a]\s*|"
    r"\u7b2c[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e]+"
    r"[\u7ae0\u8282\u6761\u90e8\u5206]\s*"
    r")"
)
_URL_RE = re.compile(r"^(?:https?|data):", re.IGNORECASE)

_DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_EMU_PER_INCH = 914400
_DEFAULT_DPI = 96
_MAX_IMAGE_WIDTH_INCH = 5.8
_FONT_BODY_EAST_ASIA = "仿宋"
_FONT_BODY_ASCII = "Times New Roman"
_FONT_HEADING_EAST_ASIA = "黑体"
_FONT_CODE_ASCII = "Consolas"
_BODY_SIZE = 24
_CAPTION_SIZE = 21
_TABLE_SIZE = 21
_TABLE_WIDTH_DXA = 9360
_TABLE_INDENT_DXA = 120
_TABLE_CELL_MARGIN_TOP = 80
_TABLE_CELL_MARGIN_BOTTOM = 80
_TABLE_CELL_MARGIN_START = 120
_TABLE_CELL_MARGIN_END = 120
_HEADING_SIZES = {1: 32, 2: 30, 3: 28, 4: 26, 5: 24, 6: 24}
_HEADING_SPACING = {
    1: (240, 160),
    2: (200, 120),
    3: (160, 80),
    4: (120, 60),
    5: (100, 40),
    6: (80, 40),
}
_LATEX_SYMBOLS = {
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\delta": "δ",
    r"\Delta": "Δ",
    r"\eta": "η",
    r"\lambda": "λ",
    r"\mu": "μ",
    r"\omega": "ω",
    r"\Omega": "Ω",
    r"\times": "×",
    r"\cdot": "·",
    r"\leq": "≤",
    r"\geq": "≥",
    r"\neq": "≠",
    r"\approx": "≈",
    r"\pm": "±",
}


def build_markdown_docx(
    title: str,
    markdown: str,
    *,
    base_dir: Path | None = None,
    include_title: bool = False,
) -> bytes:
    """Build a formatted proposal DOCX from Markdown content."""

    cleaned_markdown, cited_evidence_ids = _prepare_evidence_citations(markdown)
    blocks: list[MarkdownBlock] = []
    if include_title and title.strip():
        blocks.append(ParagraphBlock(_strip_markdown_inline(title), "h1"))
    blocks.extend(_blocks_from_markdown(cleaned_markdown))
    _append_cited_evidence_images(blocks, cited_evidence_ids)
    return _build_docx_package(title or "申报书", _normalize_headings(blocks), base_dir=base_dir)


def build_conversation_docx(title: str, messages: list[Any]) -> bytes:
    """Build a formatted proposal DOCX from chat messages."""

    document_title = title or "申报对话"
    blocks: list[MarkdownBlock] = [ParagraphBlock(document_title, "h1")]
    cited_evidence_ids: list[str] = []
    for message in messages:
        content = _message_value(message, "content", "")
        if not str(content).strip():
            continue
        role = _message_value(message, "role", "assistant")
        role_title = "用户" if role == "user" else "智策助手"
        blocks.append(ParagraphBlock(role_title, "h2"))
        cleaned_content, message_evidence_ids = _prepare_evidence_citations(str(content))
        blocks.extend(_blocks_from_markdown(cleaned_content))
        cited_evidence_ids.extend(message_evidence_ids)

    _append_cited_evidence_images(blocks, list(dict.fromkeys(cited_evidence_ids)))

    return _build_docx_package(document_title, _normalize_headings(blocks), base_dir=None)


def docx_media_type() -> str:
    return _DOCX_MEDIA_TYPE


def _message_value(message: Any, key: str, default: str) -> str:
    if isinstance(message, dict):
        return str(message.get(key, default))
    return str(getattr(message, key, default))


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


def _strip_markdown_inline(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_\n]+)__", r"\1", text)
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
    text = re.sub(r"_([^_\n]+)_", r"\1", text)
    text = re.sub(r"~~([^~\n]+)~~", r"\1", text)
    return text.strip()


def _blocks_from_markdown(text: str) -> list[MarkdownBlock]:
    result: list[MarkdownBlock] = []
    lines = text.splitlines()
    in_code = False
    i = 0
    while i < len(lines):
        raw_line = lines[i]
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            i += 1
            continue
        if not stripped:
            i += 1
            continue
        if _HORIZONTAL_RULE_RE.match(stripped):
            i += 1
            continue
        if in_code:
            result.append(ParagraphBlock(line, "body"))
            i += 1
            continue

        equation, next_index = _collect_equation(lines, i)
        if equation is not None:
            result.append(EquationBlock(equation))
            i = next_index
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            kind = f"h{level}"
            result.append(ParagraphBlock(_strip_markdown_inline(heading.group(2)), kind))  # type: ignore[arg-type]
            i += 1
            continue

        image = _IMAGE_ONLY_RE.match(stripped)
        if image:
            result.append(ImageBlock(alt=_strip_markdown_inline(image.group(1)), target=image.group(2).strip()))
            i += 1
            continue

        list_item = _LIST_ITEM_RE.match(line)
        if list_item:
            kind: ParagraphKind = "bullet" if list_item.group("bullet") else "numbered"
            result.append(ParagraphBlock(list_item.group("text").strip(), kind))
            i += 1
            continue

        if _is_table_line(line):
            table_lines: list[str] = []
            while i < len(lines) and _is_table_line(lines[i]):
                table_lines.append(lines[i])
                i += 1
            rows = _parse_table_lines(table_lines)
            if rows:
                result.append(TableBlock(rows))
            continue

        cleaned = line.strip()
        if not cleaned:
            i += 1
            continue
        caption_text = _strip_markdown_inline(cleaned)
        if _TABLE_CAPTION_RE.match(caption_text):
            result.append(ParagraphBlock(caption_text, "table_caption"))
        elif _FIGURE_CAPTION_RE.match(caption_text):
            result.append(ParagraphBlock(caption_text, "figure_caption"))
        elif not re.match(r"^\s*\|[-:|\s]+\|\s*$", line):
            result.append(ParagraphBlock(cleaned, "body"))
        i += 1
    return result


def _prepare_evidence_citations(markdown: str) -> tuple[str, list[str]]:
    """Collect stable evidence references and remove internal ids from visible Word text."""

    evidence_ids = list(dict.fromkeys(match.group(1) for match in _EVIDENCE_CITATION_RE.finditer(markdown)))
    cleaned = _EVIDENCE_CITATION_SEGMENT_RE.sub("", markdown)
    return cleaned, evidence_ids


def _append_cited_evidence_images(blocks: list[MarkdownBlock], evidence_ids: list[str]) -> None:
    if not evidence_ids:
        return
    embedded_ids = {
        parsed[1]
        for block in blocks
        if isinstance(block, ImageBlock)
        for parsed in [_parse_evidence_uri(block.target)]
        if parsed is not None
    }
    attachment_blocks: list[ImageBlock] = []
    for evidence_id in evidence_ids:
        if evidence_id in embedded_ids:
            continue
        target = f"evidence://default/{evidence_id}"
        if _resolve_evidence_image_path(target) is None:
            continue
        attachment_blocks.append(ImageBlock(alt="知识库图片证据", target=target))
        embedded_ids.add(evidence_id)
    if attachment_blocks:
        blocks.append(ParagraphBlock("相关证明材料", "h2"))
        blocks.extend(attachment_blocks)


def _collect_equation(lines: list[str], index: int) -> tuple[str | None, int]:
    stripped = lines[index].strip()
    if stripped.startswith("$$"):
        if stripped.endswith("$$") and len(stripped) > 4:
            return stripped[2:-2].strip(), index + 1
        parts: list[str] = []
        first = stripped[2:].strip()
        if first:
            parts.append(first)
        i = index + 1
        while i < len(lines):
            current = lines[i].strip()
            if current.endswith("$$"):
                tail = current[:-2].strip()
                if tail:
                    parts.append(tail)
                return "\n".join(parts).strip(), i + 1
            parts.append(lines[i].rstrip())
            i += 1
        return "\n".join(parts).strip(), i

    if stripped.startswith("\\["):
        if stripped.endswith("\\]") and len(stripped) > 4:
            return stripped[2:-2].strip(), index + 1
        parts = []
        first = stripped[2:].strip()
        if first:
            parts.append(first)
        i = index + 1
        while i < len(lines):
            current = lines[i].strip()
            if current.endswith("\\]"):
                tail = current[:-2].strip()
                if tail:
                    parts.append(tail)
                return "\n".join(parts).strip(), i + 1
            parts.append(lines[i].rstrip())
            i += 1
        return "\n".join(parts).strip(), i
    return None, index


def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _parse_table_lines(lines: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or _is_table_separator(cells):
            continue
        rows.append(cells)
    return rows


def _is_table_separator(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def _normalize_headings(blocks: list[MarkdownBlock]) -> list[MarkdownBlock]:
    normalized: list[MarkdownBlock] = []
    for block in blocks:
        if not isinstance(block, ParagraphBlock) or block.kind not in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            normalized.append(block)
            continue
        text = _HEADING_NUMBER_RE.sub("", block.text).strip()
        normalized.append(ParagraphBlock(text, block.kind))
    return normalized


def _build_docx_package(title: str, blocks: list[MarkdownBlock], *, base_dir: Path | None) -> bytes:
    body, images = _body_xml(blocks, base_dir=base_dir)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml(images))
        archive.writestr("_rels/.rels", _rels_xml())
        archive.writestr("word/_rels/document.xml.rels", _document_rels_xml(images))
        archive.writestr("word/document.xml", _document_xml(body))
        archive.writestr("word/styles.xml", _styles_xml())
        archive.writestr("word/numbering.xml", _numbering_xml())
        archive.writestr("docProps/core.xml", _core_xml(title))
        archive.writestr("docProps/app.xml", _app_xml())
        for image in images:
            archive.writestr(f"word/media/{image.filename}", image.data)
    return buffer.getvalue()


def _body_xml(blocks: list[MarkdownBlock], *, base_dir: Path | None) -> tuple[str, list[DocxImage]]:
    images: list[DocxImage] = []
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, ParagraphBlock):
            parts.append(_paragraph(block))
        elif isinstance(block, TableBlock):
            parts.append(_table(block))
        elif isinstance(block, EquationBlock):
            parts.append(_equation_paragraph(block.latex))
        elif isinstance(block, ImageBlock):
            image = _load_image(block, base_dir=base_dir, index=len(images) + 1)
            if image is None:
                label = block.alt or block.target
                parts.append(_paragraph(ParagraphBlock(f"[图片：{label}]", "image_placeholder")))
            else:
                images.append(image)
                parts.append(_image_paragraph(image, len(images)))
    return "".join(parts), images


def _run(
    text: str,
    *,
    size: int,
    east_asia_font: str,
    ascii_font: str | None = None,
    bold: bool = False,
    italic: bool = False,
) -> str:
    bold_xml = "<w:b/><w:bCs/>" if bold else ""
    italic_xml = "<w:i/><w:iCs/>" if italic else ""
    ascii_font = ascii_font or east_asia_font
    return (
        "<w:r><w:rPr>"
        f'<w:rFonts w:ascii="{_escape(ascii_font)}" w:hAnsi="{_escape(ascii_font)}" '
        f'w:eastAsia="{_escape(east_asia_font)}" w:cs="{_escape(ascii_font)}"/>'
        f"{bold_xml}{italic_xml}<w:sz w:val=\"{size}\"/><w:szCs w:val=\"{size}\"/>"
        f"</w:rPr><w:t xml:space=\"preserve\">{_escape(text)}</w:t></w:r>"
    )


def _math_run(latex: str) -> str:
    return (
        "<m:r><m:rPr><m:sty m:val=\"p\"/></m:rPr>"
        f"<m:t>{_escape(_cleanup_math_text(latex))}</m:t></m:r>"
    )


def _math_xml(latex: str) -> str:
    text = _prepare_latex(latex)
    pattern = re.compile(r"([A-Za-z0-9α-ωΑ-Ω]+)\s*([_^])\s*(?:\{([^{}]+)\}|([A-Za-z0-9α-ωΑ-Ω]+))")
    parts: list[str] = []
    cursor = 0
    for match in pattern.finditer(text):
        if match.start() > cursor:
            parts.append(_math_run(text[cursor:match.start()]))
        base = _cleanup_math_text(match.group(1))
        script = _cleanup_math_text(match.group(3) or match.group(4) or "")
        if base and script:
            parts.append(_math_script(base, script, subscript=match.group(2) == "_"))
        else:
            parts.append(_math_run(match.group(0)))
        cursor = match.end()
    if cursor < len(text):
        parts.append(_math_run(text[cursor:]))
    return "".join(parts) or _math_run(text)


def _prepare_latex(latex: str) -> str:
    text = latex.strip()
    text = re.sub(r"\\(?:text|mathrm)\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"\1/\2", text)
    for source, target in _LATEX_SYMBOLS.items():
        text = text.replace(source, target)
    text = text.replace(r"\,", " ").replace(r"\ ", " ")
    return text


def _cleanup_math_text(text: str) -> str:
    cleaned = _prepare_latex(text)
    cleaned = cleaned.replace("{", "").replace("}", "")
    cleaned = re.sub(r"\\([A-Za-z]+)", r"\1", cleaned)
    return cleaned.strip()


def _math_script(base: str, script: str, *, subscript: bool) -> str:
    tag = "sSub" if subscript else "sSup"
    script_tag = "sub" if subscript else "sup"
    return (
        f"<m:{tag}><m:{tag}Pr/>"
        f"<m:e>{_math_run(base)}</m:e>"
        f"<m:{script_tag}>{_math_run(script)}</m:{script_tag}>"
        f"</m:{tag}>"
    )


def _runs_with_inline_markdown(text: str, *, size: int, east_asia_font: str, ascii_font: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in _INLINE_MATH_RE.finditer(text):
        if match.start() > cursor:
            parts.append(_runs_without_math(text[cursor:match.start()], size=size, east_asia_font=east_asia_font, ascii_font=ascii_font))
        token = match.group(0)
        latex = token[1:-1] if token.startswith("$") else token[2:-2]
        parts.append(f"<m:oMath>{_math_xml(latex)}</m:oMath>")
        cursor = match.end()
    if cursor < len(text):
        parts.append(_runs_without_math(text[cursor:], size=size, east_asia_font=east_asia_font, ascii_font=ascii_font))
    return "".join(parts)


def _runs_without_math(text: str, *, size: int, east_asia_font: str, ascii_font: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in _INLINE_MARKDOWN_RE.finditer(text):
        if match.start() > cursor:
            parts.append(_run(text[cursor:match.start()], size=size, east_asia_font=east_asia_font, ascii_font=ascii_font))
        if match.group(2) is not None:
            parts.append(_run(match.group(2), size=size, east_asia_font=east_asia_font, ascii_font=ascii_font))
        elif match.group(3) is not None:
            parts.append(_run(match.group(3), size=size, east_asia_font=east_asia_font, ascii_font=ascii_font))
        elif match.group(4) is not None:
            parts.append(_run(match.group(4), size=size, east_asia_font=east_asia_font, ascii_font="Consolas"))
        elif match.group(5) is not None:
            parts.append(_run(match.group(5), size=size, east_asia_font=east_asia_font, ascii_font=ascii_font, bold=True))
        elif match.group(6) is not None:
            parts.append(_run(match.group(6), size=size, east_asia_font=east_asia_font, ascii_font=ascii_font, bold=True))
        elif match.group(7) is not None:
            parts.append(_run(match.group(7), size=size, east_asia_font=east_asia_font, ascii_font=ascii_font, italic=True))
        elif match.group(8) is not None:
            parts.append(_run(match.group(8), size=size, east_asia_font=east_asia_font, ascii_font=ascii_font, italic=True))
        else:
            parts.append(_run(match.group(9) or "", size=size, east_asia_font=east_asia_font, ascii_font=ascii_font))
        cursor = match.end()
    if cursor < len(text):
        parts.append(_run(text[cursor:], size=size, east_asia_font=east_asia_font, ascii_font=ascii_font))
    return "".join(parts)


def _runs_with_inline_math(text: str, *, size: int, east_asia_font: str, ascii_font: str) -> str:
    return _runs_with_inline_markdown(text, size=size, east_asia_font=east_asia_font, ascii_font=ascii_font)


def _paragraph(block: ParagraphBlock) -> str:
    if block.kind in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return _heading_paragraph(block)
    if block.kind == "table_caption":
        props = '<w:jc w:val="center"/><w:spacing w:line="240" w:lineRule="auto" w:before="120"/>'
        return f"<w:p><w:pPr>{props}</w:pPr>{_run(block.text, size=_CAPTION_SIZE, east_asia_font=_FONT_HEADING_EAST_ASIA)}</w:p>"
    if block.kind == "figure_caption":
        props = '<w:jc w:val="center"/><w:spacing w:line="240" w:lineRule="auto" w:after="120"/>'
        return f"<w:p><w:pPr>{props}</w:pPr>{_run(block.text, size=_CAPTION_SIZE, east_asia_font=_FONT_HEADING_EAST_ASIA)}</w:p>"
    if block.kind == "image_placeholder":
        props = '<w:jc w:val="center"/><w:spacing w:line="240" w:lineRule="auto"/>'
        return f"<w:p><w:pPr>{props}</w:pPr>{_run(block.text, size=_CAPTION_SIZE, east_asia_font=_FONT_HEADING_EAST_ASIA)}</w:p>"

    if block.kind in {"bullet", "numbered"}:
        return _list_paragraph(block)

    props = '<w:jc w:val="both"/><w:spacing w:line="360" w:lineRule="auto"/><w:ind w:firstLine="480"/>'
    runs = _runs_with_inline_math(
        block.text,
        size=_BODY_SIZE,
        east_asia_font=_FONT_BODY_EAST_ASIA,
        ascii_font=_FONT_BODY_ASCII,
    )
    return f"<w:p><w:pPr>{props}</w:pPr>{runs}</w:p>"


def _list_paragraph(block: ParagraphBlock) -> str:
    num_id = 2 if block.kind == "bullet" else 3
    props = (
        f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num_id}"/></w:numPr>'
        '<w:spacing w:line="290" w:lineRule="auto" w:after="80"/>'
        '<w:ind w:left="540" w:hanging="280"/>'
    )
    runs = _runs_with_inline_math(
        block.text,
        size=_BODY_SIZE,
        east_asia_font=_FONT_BODY_EAST_ASIA,
        ascii_font=_FONT_BODY_ASCII,
    )
    return f"<w:p><w:pPr>{props}</w:pPr>{runs}</w:p>"


def _heading_paragraph(block: ParagraphBlock) -> str:
    level = int(block.kind[1])
    style_id = f"Heading{level}"
    ilvl = level - 1
    before, after = _HEADING_SPACING.get(level, (80, 40))
    size = _HEADING_SIZES.get(level, _BODY_SIZE)
    props = (
        f'<w:pStyle w:val="{style_id}"/>'
        f'<w:numPr><w:ilvl w:val="{ilvl}"/><w:numId w:val="1"/></w:numPr>'
        f'<w:spacing w:line="320" w:lineRule="auto" w:before="{before}" w:after="{after}"/>'
    )
    if block.kind in {"h1", "h2"}:
        run = _run(block.text, size=size, east_asia_font=_FONT_HEADING_EAST_ASIA, ascii_font=_FONT_HEADING_EAST_ASIA)
    else:
        run = _run(
            block.text,
            size=size,
            east_asia_font=_FONT_BODY_EAST_ASIA,
            ascii_font=_FONT_BODY_ASCII,
            bold=level <= 4,
        )
    return f"<w:p><w:pPr>{props}</w:pPr>{run}</w:p>"


def _table(block: TableBlock) -> str:
    if not block.rows:
        return ""
    columns = max(len(row) for row in block.rows)
    column_widths = _table_column_widths(block.rows, columns)
    grid = "".join(f'<w:gridCol w:w="{width}"/>' for width in column_widths)
    rows: list[str] = []
    for row_index, row in enumerate(block.rows):
        cells: list[str] = []
        is_header = row_index == 0
        for width, value in zip(column_widths, [*row, *([""] * (columns - len(row)))], strict=False):
            align = "center" if is_header or _is_short_table_value(value) else "left"
            paragraph_props = f'<w:jc w:val="{align}"/><w:spacing w:line="260" w:lineRule="auto"/>'
            if is_header:
                runs = _run(
                    _strip_markdown_inline(value),
                    size=_TABLE_SIZE,
                    east_asia_font=_FONT_HEADING_EAST_ASIA,
                    ascii_font=_FONT_BODY_ASCII,
                    bold=True,
                )
            else:
                runs = _runs_with_inline_math(
                    value,
                    size=_TABLE_SIZE,
                    east_asia_font=_FONT_BODY_EAST_ASIA,
                    ascii_font=_FONT_BODY_ASCII,
                )
            paragraph = f"<w:p><w:pPr>{paragraph_props}</w:pPr>{runs}</w:p>"
            fill = '<w:shd w:fill="F4F6F9"/>' if is_header else ""
            cell_props = (
                f'<w:tcW w:w="{width}" w:type="dxa"/>'
                '<w:vAlign w:val="center"/>'
                '<w:tcMar>'
                f'<w:top w:w="{_TABLE_CELL_MARGIN_TOP}" w:type="dxa"/>'
                f'<w:bottom w:w="{_TABLE_CELL_MARGIN_BOTTOM}" w:type="dxa"/>'
                f'<w:start w:w="{_TABLE_CELL_MARGIN_START}" w:type="dxa"/>'
                f'<w:end w:w="{_TABLE_CELL_MARGIN_END}" w:type="dxa"/>'
                '</w:tcMar>'
                f"{fill}"
            )
            cells.append(f"<w:tc><w:tcPr>{cell_props}</w:tcPr>{paragraph}</w:tc>")
        rows.append(f"<w:tr>{''.join(cells)}</w:tr>")

    borders = (
        '<w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="auto"/></w:tblBorders>'
    )
    props = (
        '<w:tblPr>'
        '<w:tblLayout w:type="fixed"/>'
        f'<w:tblInd w:w="{_TABLE_INDENT_DXA}" w:type="dxa"/>'
        f'<w:tblW w:w="{_TABLE_WIDTH_DXA}" w:type="dxa"/>'
        f"{borders}</w:tblPr>"
    )
    return f"<w:tbl>{props}<w:tblGrid>{grid}</w:tblGrid>{''.join(rows)}</w:tbl>"


def _table_column_widths(rows: list[list[str]], columns: int) -> list[int]:
    if columns <= 0:
        return []
    weights: list[int] = []
    for column in range(columns):
        values = [row[column] for row in rows if column < len(row)]
        max_width = max((_display_width(_strip_markdown_inline(value)) for value in values), default=1)
        weights.append(max(max_width, 4))

    minimum = 900
    available = _TABLE_WIDTH_DXA - minimum * columns
    if available <= 0:
        base = _TABLE_WIDTH_DXA // columns
        widths = [base] * columns
    else:
        total = sum(weights) or columns
        widths = [minimum + int(available * weight / total) for weight in weights]
    widths[-1] += _TABLE_WIDTH_DXA - sum(widths)
    return widths


def _display_width(text: str) -> int:
    width = 0
    for char in text:
        width += 2 if ord(char) > 127 else 1
    return width


def _is_short_table_value(text: str) -> bool:
    cleaned = _strip_markdown_inline(text).strip()
    return bool(cleaned) and _display_width(cleaned) <= 12


def _equation_paragraph(latex: str) -> str:
    return (
        "<m:oMathPara><m:oMathParaPr><m:jc m:val=\"center\"/></m:oMathParaPr>"
        f"<m:oMath>{_math_xml(latex)}</m:oMath></m:oMathPara>"
    )


def _load_image(block: ImageBlock, *, base_dir: Path | None, index: int) -> DocxImage | None:
    path = _resolve_image_path(block.target, base_dir=base_dir)
    if path is None or Image is None:
        return None
    try:
        with Image.open(path) as image:
            width, height = image.size
            dpi_value = image.info.get("dpi", (_DEFAULT_DPI, _DEFAULT_DPI))
            if isinstance(dpi_value, (tuple, list)):
                dpi_value = dpi_value[0] if dpi_value else _DEFAULT_DPI
            try:
                dpi = float(dpi_value)
            except (TypeError, ValueError):
                dpi = _DEFAULT_DPI
            if not math.isfinite(dpi) or dpi <= 0:
                dpi = _DEFAULT_DPI
            width_inch = width / dpi
            height_inch = height / dpi
            extension = path.suffix.lower().lstrip(".")
            if extension == "jpg":
                extension = "jpeg"
            if extension in {"png", "jpeg", "gif", "bmp"}:
                image_data = path.read_bytes()
            else:
                converted = image
                if converted.mode not in {"RGB", "RGBA"}:
                    converted = converted.convert("RGB")
                output = io.BytesIO()
                converted.save(output, format="PNG")
                image_data = output.getvalue()
                extension = "png"
    except Exception:
        return None
    if width_inch > _MAX_IMAGE_WIDTH_INCH:
        scale = _MAX_IMAGE_WIDTH_INCH / width_inch
        width_inch *= scale
        height_inch *= scale

    return DocxImage(
        rid=f"rIdImage{index}",
        filename=f"image{index}.{extension}",
        data=image_data,
        extension=extension,
        width_emu=max(int(width_inch * _EMU_PER_INCH), 1),
        height_emu=max(int(height_inch * _EMU_PER_INCH), 1),
        description=block.alt or path.name,
    )


def _resolve_image_path(target: str, *, base_dir: Path | None) -> Path | None:
    candidate_text = _clean_image_target(target)
    if not candidate_text:
        return None
    if candidate_text.lower().startswith("evidence://"):
        return _resolve_evidence_image_path(candidate_text)
    if _URL_RE.match(candidate_text):
        return None
    candidate_text = unquote(candidate_text)
    candidates = [candidate_text]
    if " " in candidate_text:
        candidates.append(candidate_text.split(maxsplit=1)[0])
    for item in candidates:
        path = Path(item)
        if not path.is_absolute() and base_dir is not None:
            path = base_dir / item
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved.exists() and resolved.is_file():
            return resolved
    return None


def _parse_evidence_uri(target: str) -> tuple[str, str] | None:
    value = _clean_image_target(target)
    if not value.lower().startswith("evidence://"):
        return None
    remainder = value[len("evidence://") :]
    applicant_text, separator, evidence_text = remainder.partition("/")
    if not separator or "/" in evidence_text:
        return None
    applicant_id = unquote(applicant_text).strip()
    evidence_id = unquote(evidence_text).strip()
    if (
        not applicant_id
        or len(applicant_id) > 128
        or any(character in applicant_id for character in {"/", "\\", "\x00"})
        or _EVIDENCE_ID_RE.fullmatch(evidence_id) is None
    ):
        return None
    return applicant_id, evidence_id


def _resolve_evidence_image_path(target: str) -> Path | None:
    parsed = _parse_evidence_uri(target)
    if parsed is None:
        return None
    applicant_id, evidence_id = parsed
    user_id = get_effective_user_id()
    try:
        evidence = get_knowledge_evidence(evidence_id, applicant_id=applicant_id, user_id=user_id)
        if evidence.verification_status != "human_verified" or not evidence.asset_ids:
            return None
        asset = get_knowledge_asset(evidence.asset_ids[0], applicant_id=applicant_id, user_id=user_id)
        return resolve_asset_file(asset, thumbnail=False, user_id=user_id)
    except (KeyError, FileNotFoundError, OSError, ValueError):
        return None


def _clean_image_target(target: str) -> str:
    value = target.strip()
    if value.startswith("<") and ">" in value:
        return value[1:value.index(">")].strip()
    if value.startswith(("'", '"')):
        quote_char = value[0]
        end = value.find(quote_char, 1)
        if end > 0:
            return value[1:end].strip()
    return value


def _image_paragraph(image: DocxImage, index: int) -> str:
    description = _escape(image.description)
    return (
        '<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing>'
        '<wp:inline distT="0" distB="0" distL="0" distR="0">'
        f'<wp:extent cx="{image.width_emu}" cy="{image.height_emu}"/>'
        '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        f'<wp:docPr id="{index}" name="图片 {index}" descr="{description}"/>'
        '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
        '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic><pic:nvPicPr>'
        f'<pic:cNvPr id="{index}" name="{description}"/>'
        '<pic:cNvPicPr/></pic:nvPicPr><pic:blipFill>'
        f'<a:blip r:embed="{image.rid}"/>'
        '<a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        '<pic:spPr><a:xfrm><a:off x="0" y="0"/>'
        f'<a:ext cx="{image.width_emu}" cy="{image.height_emu}"/>'
        '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        '</pic:pic></a:graphicData></a:graphic></wp:inline>'
        '</w:drawing></w:r></w:p>'
    )


def _document_xml(body: str) -> str:
    sect = (
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f"<w:body>{body}{sect}</w:body></w:document>"
    )


def _style_run_props(east_asia_font: str, size: int, *, ascii_font: str | None = None, bold: bool = False) -> str:
    ascii_font = ascii_font or east_asia_font
    bold_xml = "<w:b/><w:bCs/>" if bold else ""
    return (
        "<w:rPr>"
        f'<w:rFonts w:ascii="{_escape(ascii_font)}" w:hAnsi="{_escape(ascii_font)}" '
        f'w:eastAsia="{_escape(east_asia_font)}" w:cs="{_escape(ascii_font)}"/>'
        f'{bold_xml}<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
        "</w:rPr>"
    )


def _heading_style(style_id: str, name: str, level: int, east_asia_font: str) -> str:
    outline_level = level - 1
    size = _HEADING_SIZES.get(level, _BODY_SIZE)
    before, after = _HEADING_SPACING.get(level, (80, 40))
    ascii_font = east_asia_font if level <= 2 else _FONT_BODY_ASCII
    bold = level <= 4
    return (
        f'<w:style w:type="paragraph" w:styleId="{style_id}">'
        f'<w:name w:val="{name}"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>'
        '<w:uiPriority w:val="9"/><w:qFormat/>'
        '<w:pPr><w:keepNext/><w:keepLines/>'
        f'<w:spacing w:line="320" w:lineRule="auto" w:before="{before}" w:after="{after}"/>'
        f'<w:outlineLvl w:val="{outline_level}"/></w:pPr>'
        f"{_style_run_props(east_asia_font, size, ascii_font=ascii_font, bold=bold)}</w:style>"
    )


def _styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:docDefaults><w:rPrDefault>'
        f'{_style_run_props(_FONT_BODY_EAST_ASIA, _BODY_SIZE, ascii_font=_FONT_BODY_ASCII)}'
        '</w:rPrDefault><w:pPrDefault>'
        '<w:pPr><w:jc w:val="both"/><w:spacing w:line="360" w:lineRule="auto"/></w:pPr>'
        '</w:pPrDefault></w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:jc w:val="both"/><w:spacing w:line="360" w:lineRule="auto"/></w:pPr>'
        f'{_style_run_props(_FONT_BODY_EAST_ASIA, _BODY_SIZE, ascii_font=_FONT_BODY_ASCII)}</w:style>'
        f'{_heading_style("Heading1", "heading 1", 1, _FONT_HEADING_EAST_ASIA)}'
        f'{_heading_style("Heading2", "heading 2", 2, _FONT_HEADING_EAST_ASIA)}'
        f'{_heading_style("Heading3", "heading 3", 3, _FONT_BODY_EAST_ASIA)}'
        f'{_heading_style("Heading4", "heading 4", 4, _FONT_BODY_EAST_ASIA)}'
        f'{_heading_style("Heading5", "heading 5", 5, _FONT_BODY_EAST_ASIA)}'
        f'{_heading_style("Heading6", "heading 6", 6, _FONT_BODY_EAST_ASIA)}'
        "</w:styles>"
    )


def _numbering_xml() -> str:
    levels = []
    for ilvl, (style_id, text) in enumerate(
        (
            ("Heading1", "%1"),
            ("Heading2", "%1.%2"),
            ("Heading3", "%1.%2.%3"),
            ("Heading4", "%1.%2.%3.%4"),
            ("Heading5", "%1.%2.%3.%4.%5"),
            ("Heading6", "%1.%2.%3.%4.%5.%6"),
        )
    ):
        levels.append(
            f'<w:lvl w:ilvl="{ilvl}"><w:start w:val="1"/><w:numFmt w:val="decimal"/>'
            f'<w:pStyle w:val="{style_id}"/><w:lvlText w:val="{text}"/><w:lvlJc w:val="left"/>'
            '<w:suff w:val="space"/><w:pPr><w:ind w:left="0" w:hanging="0"/></w:pPr></w:lvl>'
        )
    bullet_numbering = (
        '<w:abstractNum w:abstractNumId="2"><w:multiLevelType w:val="hybridMultilevel"/>'
        '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/>'
        '<w:lvlText w:val="&#8226;"/><w:lvlJc w:val="left"/>'
        '<w:pPr><w:ind w:left="540" w:hanging="280"/></w:pPr></w:lvl></w:abstractNum>'
        '<w:num w:numId="2"><w:abstractNumId w:val="2"/></w:num>'
    )
    decimal_numbering = (
        '<w:abstractNum w:abstractNumId="3"><w:multiLevelType w:val="hybridMultilevel"/>'
        '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/>'
        '<w:lvlText w:val="%1."/><w:lvlJc w:val="left"/>'
        '<w:pPr><w:ind w:left="540" w:hanging="280"/></w:pPr></w:lvl></w:abstractNum>'
        '<w:num w:numId="3"><w:abstractNumId w:val="3"/></w:num>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="multilevel"/>'
        f"{''.join(levels)}</w:abstractNum>"
        '<w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num>'
        f"{bullet_numbering}"
        f"{decimal_numbering}"
        "</w:numbering>"
    )


def _content_types_xml(images: list[DocxImage]) -> str:
    image_defaults = {
        "png": "image/png",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "bmp": "image/bmp",
    }
    image_xml = "".join(
        f'<Default Extension="{extension}" ContentType="{content_type}"/>'
        for extension, content_type in image_defaults.items()
        if any(image.extension == extension for image in images)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f"{image_xml}"
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/word/numbering.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )


def _rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
        'Target="docProps/app.xml"/>'
        "</Relationships>"
    )


def _document_rels_xml(images: list[DocxImage]) -> str:
    relationships = (
        '<Relationship Id="rIdStyles" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        '<Relationship Id="rIdNumbering" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" '
        'Target="numbering.xml"/>'
    )
    relationships += "".join(
        f'<Relationship Id="{image.rid}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        f'Target="media/{image.filename}"/>'
        for image in images
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{relationships}</Relationships>"
    )


def _core_xml(title: str) -> str:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{_escape(title)}</dc:title>"
        "<dc:creator>Government Project Declaration Agent</dc:creator>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
        "</cp:coreProperties>"
    )


def _app_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>Government Project Declaration Agent</Application>"
        "</Properties>"
    )
