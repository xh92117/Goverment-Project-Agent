import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.gateway.docx_export import build_conversation_docx, docx_media_type

router = APIRouter(prefix="/api/exports", tags=["exports"])


class ExportMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(default="")


class ConversationDocxRequest(BaseModel):
    title: str = Field(default="申报对话")
    messages: list[ExportMessage] = Field(default_factory=list)


@dataclass(frozen=True)
class ParagraphSpec:
    text: str
    kind: Literal["body", "h1", "h2", "h3", "table_caption", "figure_caption"]


_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_TABLE_CAPTION_RE = re.compile(r"^\s*表\s*[\d一二三四五六七八九十]+[\s：:、.．].+")
_FIGURE_CAPTION_RE = re.compile(r"^\s*图\s*[\d一二三四五六七八九十]+[\s：:、.．].+")


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


def _strip_markdown_inline(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_`~]+", "", text)
    return text.strip()


def _paragraphs_from_markdown(text: str) -> list[ParagraphSpec]:
    result: list[ParagraphSpec] = []
    in_code = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not line.strip():
            continue
        if in_code:
            result.append(ParagraphSpec(line, "body"))
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            result.append(ParagraphSpec(_strip_markdown_inline(heading.group(2)), f"h{level}"))  # type: ignore[arg-type]
            continue
        cleaned = _strip_markdown_inline(line)
        if not cleaned:
            continue
        if _TABLE_CAPTION_RE.match(cleaned):
            result.append(ParagraphSpec(cleaned, "table_caption"))
        elif _FIGURE_CAPTION_RE.match(cleaned):
            result.append(ParagraphSpec(cleaned, "figure_caption"))
        elif not re.match(r"^\s*\|[-:|\s]+\|\s*$", line):
            result.append(ParagraphSpec(cleaned, "body"))
    return result


def _run(text: str, *, size: int, font: str, bold: bool = False) -> str:
    bold_xml = "<w:b/>" if bold else ""
    east_asia = _escape(font)
    return (
        "<w:r><w:rPr>"
        f'<w:rFonts w:ascii="{east_asia}" w:hAnsi="{east_asia}" w:eastAsia="{east_asia}" w:cs="{east_asia}"/>'
        f"{bold_xml}<w:sz w:val=\"{size}\"/><w:szCs w:val=\"{size}\"/>"
        f"</w:rPr><w:t xml:space=\"preserve\">{_escape(text)}</w:t></w:r>"
    )


def _paragraph(spec: ParagraphSpec) -> str:
    if spec.kind == "h1":
        props = '<w:spacing w:line="360" w:lineRule="auto" w:after="360"/>'
        return f"<w:p><w:pPr>{props}</w:pPr>{_run(spec.text, size=32, font='黑体')}</w:p>"
    if spec.kind in {"h2", "h3"}:
        props = '<w:spacing w:line="360" w:lineRule="auto" w:after="360"/>'
        return f"<w:p><w:pPr>{props}</w:pPr>{_run(spec.text, size=32, font='仿宋', bold=True)}</w:p>"
    if spec.kind == "table_caption":
        props = '<w:jc w:val="center"/><w:spacing w:line="240" w:lineRule="auto" w:before="240"/>'
        return f"<w:p><w:pPr>{props}</w:pPr>{_run(spec.text, size=21, font='仿宋', bold=True)}</w:p>"
    if spec.kind == "figure_caption":
        props = '<w:jc w:val="center"/><w:spacing w:line="240" w:lineRule="auto" w:after="240"/>'
        return f"<w:p><w:pPr>{props}</w:pPr>{_run(spec.text, size=21, font='仿宋', bold=True)}</w:p>"
    props = '<w:spacing w:line="360" w:lineRule="auto"/><w:ind w:firstLine="480"/>'
    return f"<w:p><w:pPr>{props}</w:pPr>{_run(spec.text, size=24, font='仿宋')}</w:p>"


def _document_xml(paragraphs: list[ParagraphSpec]) -> str:
    body = "".join(_paragraph(item) for item in paragraphs)
    sect = (
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>'
        "</w:sectPr>"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}{sect}</w:body></w:document>"
    )


def _content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )


def _rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )


def _document_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
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


def _build_docx(title: str, messages: list[ExportMessage]) -> bytes:
    return build_conversation_docx(title, messages)


@router.post("/conversation.docx")
async def export_conversation_docx(request: ConversationDocxRequest) -> Response:
    data = _build_docx(request.title, request.messages)
    filename = re.sub(r'[\\/:*?"<>|]+', "_", request.title or "conversation")[:80] or "conversation"
    encoded_filename = quote(f"{filename}.docx")
    return Response(
        content=data,
        media_type=docx_media_type(),
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )
