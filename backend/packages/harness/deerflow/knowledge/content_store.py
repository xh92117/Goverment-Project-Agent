"""Content and asset helpers shared by knowledge indexing and retrieval.

The JSON index stores metadata.  Searchable bodies remain in their source or
generated chunk files and are loaded through this module so every backend uses
the same path validation and URI contract.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from deerflow.knowledge.schemas import KnowledgeIndexEntry

logger = logging.getLogger(__name__)

_KNOWLEDGE_FILE_SCHEME = "knowledge-file"
_MARKDOWN_IMAGE_RE = re.compile(r"(!\[[^\]]*\]\()([^\s)]+)([^)]*\))")
_FRONT_MATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n?", re.DOTALL)


def _path_within_root(path: Path, *, root: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        raise ValueError("Access denied: knowledge path escapes the configured root.") from None
    return resolved


def knowledge_file_uri(relative_path: str | Path) -> str:
    """Return the canonical URI for a file relative to a knowledge root."""

    raw = Path(relative_path)
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError("Knowledge file URIs require a safe relative path.")
    normalized = raw.as_posix().lstrip("/")
    if not normalized:
        raise ValueError("Knowledge file URI path cannot be empty.")
    return f"{_KNOWLEDGE_FILE_SCHEME}://{quote(normalized, safe='/')}"


def resolve_knowledge_file_uri(uri: str, *, root: Path, require_exists: bool = True) -> Path:
    """Resolve a canonical knowledge-file URI without allowing path traversal."""

    parsed = urlsplit(uri)
    if parsed.scheme != _KNOWLEDGE_FILE_SCHEME:
        raise ValueError(f"Unsupported knowledge URI scheme: {parsed.scheme or '<missing>'}.")
    # The canonical form intentionally uses the URI authority plus path so it
    # remains compact (knowledge-file://folder/file) while supporting subdirs.
    relative = unquote(f"{parsed.netloc}{parsed.path}").lstrip("/")
    if not relative:
        raise ValueError("Knowledge file URI path cannot be empty.")
    path = _path_within_root(root / Path(relative), root=root)
    if require_exists and not path.is_file():
        raise FileNotFoundError(relative)
    return path


def rewrite_markdown_asset_links(content: str, *, source_file_path: str, root: Path) -> str:
    """Rewrite valid local Markdown image links to stable knowledge-file URIs."""

    source = _path_within_root(root / source_file_path, root=root)

    def replace(match: re.Match[str]) -> str:
        target = match.group(2).strip()
        if target.startswith(("http://", "https://", "data:", f"{_KNOWLEDGE_FILE_SCHEME}://")):
            return match.group(0)
        target_without_fragment = unquote(target.split("#", 1)[0].split("?", 1)[0])
        try:
            asset = _path_within_root(source.parent / target_without_fragment, root=root)
        except ValueError:
            return match.group(0)
        if not asset.is_file():
            return match.group(0)
        relative = asset.relative_to(root.resolve()).as_posix()
        return f"{match.group(1)}{knowledge_file_uri(relative)}{match.group(3)}"

    return _MARKDOWN_IMAGE_RE.sub(replace, content)


def strip_generated_front_matter(content: str) -> str:
    """Remove generator-owned YAML-like front matter from chunk content."""

    return _FRONT_MATTER_RE.sub("", content, count=1).strip()


def load_index_entry_content(root: Path, entry: KnowledgeIndexEntry, *, max_chars: int = 100_000) -> str:
    """Load a safe, bounded body for an index entry.

    Section entries point at generated Markdown chunks.  Document entries point
    at source files, which may require the normal extractor for binary formats.
    """

    try:
        path = _path_within_root(root / entry.file_path, root=root)
    except ValueError:
        return ""
    if not path.is_file():
        return ""

    try:
        if path.suffix.lower() in {".md", ".markdown", ".txt", ".csv", ".tsv"}:
            content = path.read_text(encoding="utf-8", errors="replace")
        else:
            from deerflow.knowledge.extractors import extract_text

            content = extract_text(path)
    except Exception:
        logger.warning("Failed to load searchable knowledge content from %s.", entry.file_path, exc_info=True)
        return ""

    if entry.entry_type in {"section", "subsection"}:
        content = strip_generated_front_matter(content)
    return content[:max_chars]
