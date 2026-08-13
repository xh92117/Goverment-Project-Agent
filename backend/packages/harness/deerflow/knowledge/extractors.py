"""Text extraction helpers for folder-based knowledge sources."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

import httpx

logger = logging.getLogger(__name__)

_WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
_WORD_VAL = f"{{{_WORD_NS['w']}}}val"
_HEADING_STYLE_RE = re.compile(r"heading\s*(\d+)", re.IGNORECASE)
_ZH_SECTION_RE = re.compile(r"^（[一二三四五六七八九十]+）")
_DECIMAL_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)+)\s+")
_TOP_NUMBER_HEADING_RE = re.compile(r"^\d+[．、.]\s*")
_ZH_NUMBER_HEADING_RE = re.compile(r"^[一二三四五六七八九十]+[、．.]\s*")
_MINERU_TERMINAL_STATES = {"done", "failed"}
_PDF_CACHE_META_SUFFIX = ".extractor.json"
_MIN_PDF_CHARS_PER_PAGE = 50
_MAX_TABLE_ROWS = 500
_MAX_TABLE_COLUMNS = 30
_EXTRACTOR_VERSION = "2"
_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_ARCHIVE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"}


@dataclass(frozen=True)
class ExtractedText:
    """Text extracted from a knowledge source plus ingestion metadata."""

    content: str
    parser: str
    cache_hit: bool = False
    warning: str | None = None


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(".//w:t", _WORD_NS)).strip()


def _paragraph_style(paragraph: ET.Element) -> str:
    ppr = paragraph.find("w:pPr", _WORD_NS)
    if ppr is None:
        return ""
    pstyle = ppr.find("w:pStyle", _WORD_NS)
    if pstyle is None:
        return ""
    return pstyle.attrib.get(_WORD_VAL, "")


def _heading_level_from_style(style: str) -> int | None:
    match = _HEADING_STYLE_RE.search(style.replace("_", " "))
    if not match:
        return None
    return min(max(int(match.group(1)), 1), 6)


def _heading_level_from_text(text: str) -> int | None:
    if _ZH_SECTION_RE.match(text):
        return 1
    decimal = _DECIMAL_HEADING_RE.match(text)
    if decimal:
        return min(decimal.group(1).count(".") + 1, 6)
    if _TOP_NUMBER_HEADING_RE.match(text) or _ZH_NUMBER_HEADING_RE.match(text):
        return 2
    return None


def _docx_paragraph_to_markdown(text: str, style: str) -> str:
    level = _heading_level_from_style(style) or _heading_level_from_text(text)
    if level is None:
        return text
    return f"{'#' * level} {text}"


def extract_docx_text(path: Path) -> str:
    """Extract a DOCX file into Markdown-like text.

    The extractor intentionally has no third-party dependencies. It preserves
    paragraphs and turns Word heading styles or declaration-style numbered
    headings into Markdown headings so the index generator can locate sections.
    """

    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))

    lines: list[str] = []
    for paragraph in root.findall(".//w:p", _WORD_NS):
        text = _paragraph_text(paragraph)
        if not text:
            continue
        lines.append(_docx_paragraph_to_markdown(text, _paragraph_style(paragraph)))

    return "\n\n".join(lines)


def _markdown_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return text.replace("|", "\\|")


def _markdown_table(rows: list[list[object]], *, title: str) -> str:
    normalized = [
        [_markdown_cell(cell) for cell in row[:_MAX_TABLE_COLUMNS]]
        for row in rows[:_MAX_TABLE_ROWS]
        if any(str(cell or "").strip() for cell in row)
    ]
    if not normalized:
        return f"## {title}\n\n空表。"
    width = max(len(row) for row in normalized)
    normalized = [row + [""] * (width - len(row)) for row in normalized]
    header = normalized[0]
    body = normalized[1:]
    separator = ["---"] * width
    lines = [f"## {title}", "", "|" + "|".join(header) + "|", "|" + "|".join(separator) + "|"]
    lines.extend("|" + "|".join(row) + "|" for row in body)
    if len(rows) > _MAX_TABLE_ROWS:
        lines.extend(["", f"> 已截断，仅保留前 {_MAX_TABLE_ROWS} 行。"])
    return "\n".join(lines)


def extract_csv_text(path: Path) -> str:
    """Extract CSV/TSV-like files into Markdown table text."""

    raw = path.read_text(encoding="utf-8-sig", errors="ignore")
    sample = raw[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(raw), dialect))
    return f"# {path.stem}\n\n{_markdown_table(rows, title='表格内容')}"


def extract_xlsx_text(path: Path) -> str:
    """Extract an XLSX workbook into Markdown table text."""

    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("openpyxl is not installed; cannot parse XLSX knowledge files.") from exc

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sections = [f"# {path.stem}"]
        for sheet in workbook.worksheets:
            rows = [list(row) for row in sheet.iter_rows(values_only=True)]
            sections.append(_markdown_table(rows, title=f"工作表：{sheet.title}"))
        return "\n\n".join(sections)
    finally:
        workbook.close()


def extract_xls_text(path: Path) -> str:
    """Extract a legacy XLS workbook into Markdown table text."""

    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError("xlrd is not installed; cannot parse XLS knowledge files.") from exc

    workbook = xlrd.open_workbook(str(path))
    sections = [f"# {path.stem}"]
    for sheet in workbook.sheets():
        rows = [sheet.row_values(row_index) for row_index in range(sheet.nrows)]
        sections.append(_markdown_table(rows, title=f"工作表：{sheet.name}"))
    return "\n\n".join(sections)


def _mineru_token() -> str:
    token = os.getenv("MINERU_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("MINERU_API_TOKEN is not set; cannot parse PDF with MinerU.")
    return token


def _mineru_base_url() -> str:
    return os.getenv("MINERU_API_BASE_URL", "https://mineru.net").rstrip("/")


def _mineru_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "*/*",
    }


def _raise_for_mineru_error(payload: dict, *, operation: str) -> None:
    if payload.get("code") == 0:
        return
    message = payload.get("msg") or "unknown error"
    raise RuntimeError(f"MinerU {operation} failed: {message}")


def _safe_archive_reference(markdown_name: str, reference: str) -> PurePosixPath | None:
    reference = reference.strip().strip("<>")
    if not reference or "://" in reference or reference.startswith(("data:", "kbasset://", "/", "#")):
        return None
    raw = PurePosixPath(reference.replace("\\", "/"))
    candidate = PurePosixPath(markdown_name).parent / raw
    normalized_parts: list[str] = []
    for part in candidate.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not normalized_parts:
                return None
            normalized_parts.pop()
            continue
        normalized_parts.append(part)
    return PurePosixPath(*normalized_parts)


def _extract_full_markdown_from_zip(zip_bytes: bytes, *, source_path: Path | None = None) -> str:
    with ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = archive.namelist()
        preferred = next((name for name in names if name.endswith("/full.md") or name == "full.md"), None)
        if preferred is None:
            preferred = next((name for name in names if name.lower().endswith(".md")), None)
        if preferred is None:
            raise RuntimeError("MinerU result zip does not contain a markdown file.")
        markdown = archive.read(preferred).decode("utf-8", errors="ignore")
        if source_path is None:
            return markdown

        archive_names = {PurePosixPath(name): name for name in names if not name.endswith("/")}
        asset_root = source_path.with_name(f"{source_path.name}.assets")

        def replace_image(match: re.Match[str]) -> str:
            alt_text, raw_reference = match.groups()
            reference = raw_reference.strip().strip("<>")
            archive_reference = _safe_archive_reference(preferred, reference)
            if archive_reference is None or archive_reference.suffix.lower() not in _ARCHIVE_IMAGE_EXTENSIONS:
                return match.group(0)
            archive_name = archive_names.get(archive_reference)
            if archive_name is None:
                return match.group(0)
            markdown_relative = PurePosixPath(reference.replace("\\", "/"))
            if any(part == ".." for part in markdown_relative.parts):
                markdown_relative = PurePosixPath("images") / archive_reference.name
            destination = (asset_root / Path(*markdown_relative.parts)).resolve()
            try:
                destination.relative_to(asset_root.resolve())
            except ValueError:
                return match.group(0)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(archive_name))
            rewritten = (PurePosixPath(asset_root.name) / markdown_relative).as_posix()
            return f"![{alt_text}]({rewritten})"

        return _MARKDOWN_IMAGE_RE.sub(replace_image, markdown)


def _pdf_cache_meta_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + _PDF_CACHE_META_SUFFIX)


def _read_pdf_cache_metadata(path: Path) -> dict[str, str]:
    meta_path = _pdf_cache_meta_path(path)
    if not meta_path.exists():
        return {}
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_pdf_cache(path: Path, markdown: str, *, parser: str) -> None:
    cache_path = path.with_suffix(path.suffix + ".mineru.md")
    cache_path.write_text(markdown, encoding="utf-8")
    metadata = {
        "parser": parser,
        "source_file": path.name,
        "updated_at_epoch": str(time.time()),
        "extractor_version": _EXTRACTOR_VERSION,
        "asset_references": [match.group(2).strip().strip("<>") for match in _MARKDOWN_IMAGE_RE.finditer(markdown)],
    }
    _pdf_cache_meta_path(path).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def _pymupdf_output_too_sparse(text: str, file_path: Path) -> bool:
    chars = len(text.strip())
    doc = None
    pages: int | None = None
    try:
        import pymupdf

        doc = pymupdf.open(str(file_path))
        pages = len(doc)
    except Exception:
        pass
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass
    if pages is not None and pages > 0:
        return (chars / pages) < _MIN_PDF_CHARS_PER_PAGE
    return chars < 200


def _parse_pdf_with_pymupdf4llm(path: Path) -> str:
    try:
        import pymupdf4llm
    except ImportError as exc:
        raise RuntimeError("pymupdf4llm is not installed.") from exc

    try:
        markdown = pymupdf4llm.to_markdown(str(path))
    except Exception as exc:
        raise RuntimeError(f"pymupdf4llm PDF parse failed: {exc}") from exc
    if _pymupdf_output_too_sparse(markdown, path):
        raise RuntimeError("pymupdf4llm output is too sparse; PDF may be scanned or encrypted.")
    return markdown


def _parse_pdf_with_markitdown(path: Path) -> str:
    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise RuntimeError("MarkItDown is not installed.") from exc

    try:
        return MarkItDown().convert(str(path)).text_content
    except Exception as exc:
        raise RuntimeError(f"MarkItDown PDF parse failed: {exc}") from exc


def _pdf_parser_candidates() -> list[tuple[str, object]]:
    parsers: list[tuple[str, object]] = [("pdf:mineru", _parse_pdf_with_mineru)]
    parsers.extend(
        [
            ("pdf:pymupdf4llm", _parse_pdf_with_pymupdf4llm),
            ("pdf:markitdown", _parse_pdf_with_markitdown),
        ]
    )
    return parsers


def _parse_pdf_with_mineru(path: Path) -> str:
    token = _mineru_token()
    base_url = _mineru_base_url()
    model_version = os.getenv("MINERU_MODEL_VERSION", "vlm")
    language = os.getenv("MINERU_LANGUAGE", "ch")
    timeout = float(os.getenv("MINERU_TIMEOUT_SECONDS", "60"))
    poll_interval = float(os.getenv("MINERU_POLL_INTERVAL_SECONDS", "5"))
    max_wait = float(os.getenv("MINERU_MAX_WAIT_SECONDS", "900"))
    data_id = re.sub(r"[^A-Za-z0-9_.-]", "_", path.stem)[:128] or "knowledge_pdf"

    with httpx.Client(timeout=timeout) as client:
        create_payload = {
            "files": [{"name": path.name, "data_id": data_id}],
            "model_version": model_version,
            "language": language,
        }
        create_response = client.post(
            f"{base_url}/api/v4/file-urls/batch",
            headers=_mineru_headers(token),
            json=create_payload,
        )
        create_response.raise_for_status()
        create_data = create_response.json()
        _raise_for_mineru_error(create_data, operation="upload-url request")

        batch_id = create_data["data"]["batch_id"]
        upload_url = create_data["data"]["file_urls"][0]
        with path.open("rb") as source:
            upload_response = client.put(upload_url, content=source)
        upload_response.raise_for_status()

        deadline = time.monotonic() + max_wait
        result: dict | None = None
        while time.monotonic() < deadline:
            poll_response = client.get(
                f"{base_url}/api/v4/extract-results/batch/{batch_id}",
                headers=_mineru_headers(token),
            )
            poll_response.raise_for_status()
            poll_data = poll_response.json()
            _raise_for_mineru_error(poll_data, operation="result polling")
            results = poll_data.get("data", {}).get("extract_result", [])
            result = next((item for item in results if item.get("file_name") == path.name), results[0] if results else None)
            state = (result or {}).get("state")
            if state in _MINERU_TERMINAL_STATES:
                break
            time.sleep(poll_interval)

        if result is None:
            raise RuntimeError("MinerU did not return a parse result.")
        if result.get("state") != "done":
            message = result.get("err_msg") or result.get("state") or "timeout"
            raise RuntimeError(f"MinerU PDF parse failed: {message}")
        zip_url = result.get("full_zip_url")
        if not zip_url:
            raise RuntimeError("MinerU parse result did not include full_zip_url.")

        zip_response = client.get(zip_url)
        zip_response.raise_for_status()
        return _extract_full_markdown_from_zip(zip_response.content, source_path=path)


def _pdf_cache_assets_complete(cache_path: Path, markdown: str) -> bool:
    for match in _MARKDOWN_IMAGE_RE.finditer(markdown):
        reference = match.group(2).strip().strip("<>")
        if not reference or "://" in reference or reference.startswith(("data:", "kbasset://", "/", "#")):
            continue
        resolved = (cache_path.parent / reference).resolve()
        try:
            resolved.relative_to(cache_path.parent.resolve())
        except ValueError:
            return False
        if not resolved.exists() or not resolved.is_file():
            return False
    return True


def extract_pdf_text_with_metadata(path: Path) -> ExtractedText:
    """Extract a PDF to Markdown with MinerU first and local fallbacks.

    The historical cache name is kept as ``*.pdf.mineru.md`` for compatibility,
    even when the cached content came from a fallback parser.
    """

    cache_path = path.with_suffix(path.suffix + ".mineru.md")
    if cache_path.exists() and cache_path.stat().st_mtime >= path.stat().st_mtime:
        metadata = _read_pdf_cache_metadata(path)
        cached_markdown = cache_path.read_text(encoding="utf-8")
        if _pdf_cache_assets_complete(cache_path, cached_markdown):
            parser = metadata.get("parser") or "pdf:cache"
            return ExtractedText(
                content=cached_markdown,
                parser=parser,
                cache_hit=True,
            )

    failures: list[str] = []
    for parser, parse in _pdf_parser_candidates():
        try:
            markdown = parse(path)  # type: ignore[misc]
        except Exception as exc:
            failures.append(f"{parser}: {exc}")
            logger.warning("Knowledge PDF parser failed for %s via %s: %s", path.name, parser, exc)
            continue
        _write_pdf_cache(path, markdown, parser=parser)
        warning = "; ".join(failures) if failures else None
        return ExtractedText(content=markdown, parser=parser, cache_hit=False, warning=warning)

    details = "; ".join(failures) if failures else "no PDF parser configured"
    raise RuntimeError(f"Unable to parse PDF '{path.name}': {details}")


def extract_pdf_text(path: Path) -> str:
    """Extract a PDF into Markdown text."""

    return extract_pdf_text_with_metadata(path).content


def extract_text_with_metadata(path: Path) -> ExtractedText:
    """Extract text from a supported knowledge source file with metadata."""

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text_with_metadata(path)
    if suffix == ".docx":
        return ExtractedText(content=extract_docx_text(path), parser="docx:xml")
    if suffix == ".xlsx":
        return ExtractedText(content=extract_xlsx_text(path), parser="table:xlsx")
    if suffix == ".xls":
        return ExtractedText(content=extract_xls_text(path), parser="table:xls")
    if suffix in {".csv", ".tsv"}:
        return ExtractedText(content=extract_csv_text(path), parser=f"table:{suffix.removeprefix('.')}")

    try:
        return ExtractedText(content=path.read_text(encoding="utf-8"), parser=f"text:{suffix or 'plain'}")
    except UnicodeDecodeError:
        return ExtractedText(
            content=path.read_text(encoding="utf-8", errors="ignore"),
            parser=f"text:{suffix or 'plain'}:ignore-errors",
            warning="File was decoded with errors ignored.",
        )


def extract_text(path: Path) -> str:
    """Extract text from a supported knowledge source file."""

    return extract_text_with_metadata(path).content
