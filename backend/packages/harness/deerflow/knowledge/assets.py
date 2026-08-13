"""Binary image assets and structured evidence cards for the knowledge base.

This module deliberately stores image metadata outside ``index.json``.  Only a
small evidence pointer is added to the existing LLM-Wiki index, so legacy text
documents, chunks, and retrieval tools keep their current contract.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from deerflow.knowledge import storage as knowledge_storage
from deerflow.knowledge.evidence_extraction import (
    EvidenceExtractionError,
    VisionModelUnavailableError,
    extract_evidence_from_image,
)
from deerflow.knowledge.schemas import (
    KnowledgeAsset,
    KnowledgeEvidence,
    KnowledgeEvidencePatch,
    KnowledgeIndexEntryCreate,
    KnowledgeIndexEntryPatch,
)
from deerflow.utils.time import now_iso

_ASSETS_DIR = ".assets"
_REGISTRY_FILENAME = "registry.json"
_MAX_IMAGE_BYTES = 100 * 1024 * 1024
_THUMBNAIL_SIZE = (640, 640)
_FORMAT_TO_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "TIFF": "image/tiff",
}
_MIME_TO_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/tiff": ".tiff",
}
_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"})
_registry_lock = threading.RLock()


def _registry_path(root: Path) -> Path:
    return root / _ASSETS_DIR / _REGISTRY_FILENAME


def _empty_registry() -> dict[str, Any]:
    return {"version": "1", "assets": [], "evidence": []}


def _load_registry(root: Path) -> dict[str, Any]:
    path = _registry_path(root)
    if not path.exists():
        return _empty_registry()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_registry()
    if not isinstance(raw, dict):
        return _empty_registry()
    raw.setdefault("version", "1")
    raw.setdefault("assets", [])
    raw.setdefault("evidence", [])
    return raw


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _safe_component(value: str, *, fallback: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
    return cleaned[:96] or fallback


def _inspect_image(data: bytes) -> tuple[str, int, int]:
    if not data:
        raise ValueError("Image file is empty.")
    if len(data) > _MAX_IMAGE_BYTES:
        raise ValueError(f"Image file exceeds {_MAX_IMAGE_BYTES} bytes.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image_format = (image.format or "").upper()
            width, height = image.size
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("File content is not a supported image.") from exc
    mime_type = _FORMAT_TO_MIME.get(image_format)
    if mime_type is None:
        raise ValueError(f"Unsupported image format: {image_format or 'unknown'}.")
    return mime_type, width, height


def _write_thumbnail(data: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        image.thumbnail(_THUMBNAIL_SIZE)
        image.save(destination, format="WEBP", quality=82, method=4)


def _evidence_card_markdown(evidence: KnowledgeEvidence, asset: KnowledgeAsset) -> str:
    fields = [
        ("证据类型", evidence.evidence_type),
        ("所属申报主体", evidence.applicant_id),
        ("持有人", evidence.holder),
        ("发证单位", evidence.issuer),
        ("证书编号", evidence.certificate_no),
        ("颁发日期", evidence.issued_at),
        ("有效期开始", evidence.valid_from),
        ("有效期截止", evidence.valid_to),
        ("复核状态", evidence.verification_status),
        ("识别方式", evidence.extraction_provider),
        ("复核人", evidence.reviewed_by),
        ("复核时间", evidence.reviewed_at),
    ]
    lines = [
        f"# {evidence.title}",
        "",
        *[f"- {label}：{value}" for label, value in fields if value],
        f"- 原始文件：{asset.original_filename}",
        f"- 资产编号：{asset.asset_id}",
        "",
    ]
    if evidence.visual_summary:
        lines.extend(["## 图像摘要", "", evidence.visual_summary, ""])
    if evidence.ocr_text:
        lines.extend(["## OCR 原文", "", evidence.ocr_text, ""])
    if evidence.extraction_warnings:
        lines.extend(["## 识别提示", "", *[f"- {warning}" for warning in evidence.extraction_warnings], ""])
    if evidence.review_notes:
        lines.extend(["## 复核备注", "", evidence.review_notes, ""])
    lines.extend(["## 原始证据", "", f"![{evidence.title}](kbasset://{asset.asset_id})", ""])
    return "\n".join(lines)


def _write_evidence_card(root: Path, evidence: KnowledgeEvidence, asset: KnowledgeAsset) -> None:
    path = (root / evidence.card_file_path).resolve()
    path.relative_to(root.resolve())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_evidence_card_markdown(evidence, asset), encoding="utf-8")


def _evidence_summary(evidence: KnowledgeEvidence) -> str:
    values = [
        evidence.title,
        evidence.holder,
        evidence.issuer,
        evidence.certificate_no,
        evidence.issued_at,
        evidence.valid_to,
        evidence.visual_summary,
    ]
    return "；".join(str(value).strip() for value in values if value and str(value).strip())[:500]


def _index_evidence(evidence: KnowledgeEvidence, asset: KnowledgeAsset, *, user_id: str | None) -> None:
    indexes = knowledge_storage.get_knowledge_storage().list_indexes(user_id=user_id)
    existing = next((entry for entry in indexes if entry.evidence_id == evidence.evidence_id), None)
    keywords = list(
        dict.fromkeys(
            [
                evidence.title,
                evidence.evidence_type,
                evidence.holder or "",
                evidence.issuer or "",
                evidence.certificate_no or "",
                *evidence.keywords,
                *evidence.project_tags,
            ]
        )
    )
    keywords = [value for value in keywords if value]
    metadata = {
        "evidence_id": evidence.evidence_id,
        "asset_ids": evidence.asset_ids,
        "applicant_id": evidence.applicant_id,
        "holder": evidence.holder,
        "issuer": evidence.issuer,
        "certificate_no": evidence.certificate_no,
        "issued_at": evidence.issued_at,
        "valid_from": evidence.valid_from,
        "valid_to": evidence.valid_to,
        "verification_status": evidence.verification_status,
        "extraction_status": evidence.extraction_status,
        "extraction_provider": evidence.extraction_provider,
        "extraction_confidence": evidence.extraction_confidence,
        "reviewed_at": evidence.reviewed_at,
        "reviewed_by": evidence.reviewed_by,
        "project_tags": evidence.project_tags,
        "original_filename": asset.original_filename,
    }
    if existing is None:
        knowledge_storage.create_knowledge_index_entry(
            KnowledgeIndexEntryCreate(
                title=evidence.title,
                entry_type="evidence",
                category="图像证据",
                file_path=evidence.card_file_path,
                keywords=keywords,
                proposal_sections=evidence.applicable_chapters,
                applicable_chapters=evidence.applicable_chapters,
                evidence_type=evidence.evidence_type,
                evidence_id=evidence.evidence_id,
                asset_ids=evidence.asset_ids,
                applicant_id=evidence.applicant_id,
                verification_status=evidence.verification_status,
                valid_from=evidence.valid_from,
                valid_to=evidence.valid_to,
                source_file_path=asset.storage_path,
                summary=_evidence_summary(evidence),
                metadata=metadata,
                confidence=max(0.5, evidence.extraction_confidence),
                confidentiality_level=evidence.confidentiality_level,
            ),
            user_id=user_id,
        )
        return
    knowledge_storage.update_knowledge_index_entry(
        existing.index_id,
        KnowledgeIndexEntryPatch(
            title=evidence.title,
            keywords=keywords,
            proposal_sections=evidence.applicable_chapters,
            applicable_chapters=evidence.applicable_chapters,
            evidence_type=evidence.evidence_type,
            evidence_id=evidence.evidence_id,
            asset_ids=evidence.asset_ids,
            applicant_id=evidence.applicant_id,
            verification_status=evidence.verification_status,
            valid_from=evidence.valid_from,
            valid_to=evidence.valid_to,
            summary=_evidence_summary(evidence),
            metadata=metadata,
            confidence=max(0.5, evidence.extraction_confidence),
            confidentiality_level=evidence.confidentiality_level,
        ),
        user_id=user_id,
    )


def ingest_knowledge_image(
    data: bytes,
    *,
    filename: str,
    applicant_id: str,
    evidence_type: str = "image_evidence",
    title: str | None = None,
    confidentiality_level: str = "internal",
    user_id: str | None = None,
) -> tuple[KnowledgeAsset, KnowledgeEvidence, bool]:
    """Persist an image and create a reviewable evidence pointer in LLM-Wiki."""

    applicant_id = applicant_id.strip()
    if not applicant_id:
        raise ValueError("applicant_id is required for image evidence.")
    mime_type, width, height = _inspect_image(data)
    digest = hashlib.sha256(data).hexdigest()
    root = knowledge_storage._knowledge_root_path(user_id=user_id)
    timestamp = now_iso()

    with _registry_lock:
        registry = _load_registry(root)
        for raw_asset in registry["assets"]:
            candidate = KnowledgeAsset(**raw_asset)
            if candidate.applicant_id == applicant_id and candidate.sha256 == digest:
                linked = next(
                    (KnowledgeEvidence(**raw) for raw in registry["evidence"] if candidate.asset_id in raw.get("asset_ids", []) and (evidence_type == "image_evidence" or raw.get("evidence_type") == evidence_type)),
                    None,
                )
                if linked is not None:
                    return candidate, linked, True

        asset_id = f"ast_{uuid.uuid4().hex}"
        evidence_id = f"evd_{uuid.uuid4().hex}"
        applicant_dir = _safe_component(applicant_id, fallback="default")
        asset_dir = Path(_ASSETS_DIR) / applicant_dir / digest[:2] / asset_id
        extension = _MIME_TO_EXTENSION[mime_type]
        storage_path = (asset_dir / f"original{extension}").as_posix()
        thumbnail_path = (asset_dir / "thumbnail.webp").as_posix()
        card_file_path = (asset_dir / "evidence.md").as_posix()
        asset_title = (title or Path(filename).stem).strip() or "图像证据"
        original = root / storage_path
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(data)
        _write_thumbnail(data, root / thumbnail_path)

        asset = KnowledgeAsset(
            asset_id=asset_id,
            applicant_id=applicant_id,
            title=asset_title,
            original_filename=Path(filename).name,
            storage_path=storage_path,
            thumbnail_path=thumbnail_path,
            mime_type=mime_type,
            sha256=digest,
            byte_size=len(data),
            width=width,
            height=height,
            confidentiality_level=confidentiality_level,
            created_at=timestamp,
            updated_at=timestamp,
        )
        evidence = KnowledgeEvidence(
            evidence_id=evidence_id,
            applicant_id=applicant_id,
            asset_ids=[asset_id],
            evidence_type=evidence_type,
            title=asset_title,
            keywords=[asset_title, evidence_type],
            verification_status="needs_review",
            extraction_confidence=0.0,
            extraction_status="pending",
            extraction_warnings=["待构建索引时由支持视觉的多模态模型识别。"],
            card_file_path=card_file_path,
            confidentiality_level=confidentiality_level,
            created_at=timestamp,
            updated_at=timestamp,
        )
        _write_evidence_card(root, evidence, asset)
        registry["assets"].append(asset.model_dump(mode="json"))
        registry["evidence"].append(evidence.model_dump(mode="json"))
        _atomic_write_json(_registry_path(root), registry)
        _index_evidence(evidence, asset, user_id=user_id)
        return asset, evidence, False


def get_knowledge_asset(asset_id: str, *, applicant_id: str, user_id: str | None = None) -> KnowledgeAsset:
    root = knowledge_storage._knowledge_root_path(user_id=user_id)
    with _registry_lock:
        for raw in _load_registry(root)["assets"]:
            asset = KnowledgeAsset(**raw)
            if asset.asset_id == asset_id and asset.applicant_id == applicant_id:
                return asset
    raise KeyError(asset_id)


def get_knowledge_evidence(evidence_id: str, *, applicant_id: str, user_id: str | None = None) -> KnowledgeEvidence:
    root = knowledge_storage._knowledge_root_path(user_id=user_id)
    with _registry_lock:
        for raw in _load_registry(root)["evidence"]:
            evidence = KnowledgeEvidence(**raw)
            if evidence.evidence_id == evidence_id and evidence.applicant_id == applicant_id:
                return evidence
    raise KeyError(evidence_id)


def search_knowledge_evidence(
    *,
    query: str = "",
    applicant_id: str,
    evidence_types: list[str] | None = None,
    verification_statuses: list[str] | None = None,
    limit: int = 20,
    user_id: str | None = None,
) -> list[KnowledgeEvidence]:
    root = knowledge_storage._knowledge_root_path(user_id=user_id)
    terms = [term.casefold() for term in query.split() if term.strip()]
    matches: list[KnowledgeEvidence] = []
    with _registry_lock:
        for raw in _load_registry(root)["evidence"]:
            evidence = KnowledgeEvidence(**raw)
            if evidence.applicant_id != applicant_id:
                continue
            if evidence_types and evidence.evidence_type not in evidence_types:
                continue
            if verification_statuses and evidence.verification_status not in verification_statuses:
                continue
            searchable = " ".join(
                [
                    evidence.title,
                    evidence.evidence_type,
                    evidence.holder or "",
                    evidence.issuer or "",
                    evidence.certificate_no or "",
                    evidence.ocr_text,
                    evidence.visual_summary,
                    *evidence.keywords,
                    *evidence.project_tags,
                ]
            ).casefold()
            if terms and not all(term in searchable for term in terms):
                continue
            matches.append(evidence)
    matches.sort(key=lambda item: (item.verification_status == "human_verified", item.updated_at), reverse=True)
    return matches[: max(1, min(limit, 100))]


def list_knowledge_image_paths(
    *,
    folder_path: str = "",
    include_thumbnails: bool = False,
    limit: int = 200,
    user_id: str | None = None,
) -> tuple[list[str], bool]:
    """List image files under the current user's knowledge-base root.

    Returned paths are always relative to the knowledge-base root. This keeps
    host filesystem details private while covering both managed evidence
    assets (``.assets/.../original.*``) and images extracted beside source
    documents (for example ``report.pdf.assets/images/*.jpg``).

    Generated evidence thumbnails are omitted by default because they are
    derivatives of the original image rather than independent knowledge
    sources.
    """

    root = knowledge_storage._knowledge_root_path(user_id=user_id).resolve()
    raw_folder = Path(folder_path)
    if raw_folder.is_absolute():
        raise ValueError("folder_path must be relative to the knowledge-base root.")

    if not root.exists() and not folder_path:
        return [], False

    search_root = (root / raw_folder).resolve()
    try:
        search_root.relative_to(root)
    except ValueError:
        raise ValueError("Access denied: path traversal detected.") from None

    if not search_root.exists():
        raise FileNotFoundError(folder_path or ".")
    if not search_root.is_dir():
        raise NotADirectoryError(folder_path or ".")

    bounded_limit = max(1, min(limit, 1000))
    matches: list[str] = []
    for candidate in search_root.rglob("*"):
        if candidate.suffix.casefold() not in _IMAGE_EXTENSIONS:
            continue
        try:
            resolved = candidate.resolve()
            relative = resolved.relative_to(root)
        except (OSError, ValueError):
            # Do not follow a symlink or filesystem anomaly outside the
            # configured knowledge root.
            continue
        if not resolved.is_file():
            continue
        if not include_thumbnails and relative.name.casefold() == "thumbnail.webp" and _ASSETS_DIR in relative.parts:
            continue
        matches.append(relative.as_posix())

    matches.sort(key=lambda value: (value.casefold(), value))
    truncated = len(matches) > bounded_limit
    return matches[:bounded_limit], truncated


def update_knowledge_evidence(
    evidence_id: str,
    patch: KnowledgeEvidencePatch,
    *,
    applicant_id: str,
    user_id: str | None = None,
    extraction_status: str | None = None,
    extraction_provider: str | None = None,
    extraction_warnings: list[str] | None = None,
) -> KnowledgeEvidence:
    root = knowledge_storage._knowledge_root_path(user_id=user_id)
    with _registry_lock:
        registry = _load_registry(root)
        updated: KnowledgeEvidence | None = None
        for index, raw in enumerate(registry["evidence"]):
            current = KnowledgeEvidence(**raw)
            if current.evidence_id != evidence_id or current.applicant_id != applicant_id:
                continue
            payload = current.model_dump()
            payload.update(patch.model_dump(exclude_unset=True))
            if extraction_status is not None:
                payload["extraction_status"] = extraction_status
            if extraction_provider is not None:
                payload["extraction_provider"] = extraction_provider
            if extraction_warnings is not None:
                payload["extraction_warnings"] = extraction_warnings
            if payload.get("verification_status") == "human_verified":
                missing = validate_knowledge_evidence_for_verification(KnowledgeEvidence(**payload))
                if missing:
                    raise ValueError("Cannot verify evidence; missing required fields: " + ", ".join(missing))
                payload["reviewed_at"] = now_iso()
                payload["reviewed_by"] = user_id or "system"
            elif payload.get("verification_status") == "rejected":
                payload["reviewed_at"] = now_iso()
                payload["reviewed_by"] = user_id or "system"
            elif "verification_status" in patch.model_fields_set:
                payload["reviewed_at"] = None
                payload["reviewed_by"] = None
            payload["updated_at"] = now_iso()
            updated = KnowledgeEvidence(**payload)
            registry["evidence"][index] = updated.model_dump(mode="json")
            break
        if updated is None:
            raise KeyError(evidence_id)
        asset = get_knowledge_asset(updated.asset_ids[0], applicant_id=applicant_id, user_id=user_id)
        _write_evidence_card(root, updated, asset)
        _atomic_write_json(_registry_path(root), registry)
        _index_evidence(updated, asset, user_id=user_id)
        return updated


def validate_knowledge_evidence_for_verification(evidence: KnowledgeEvidence) -> list[str]:
    """Return stable field names that still require human completion."""

    missing: list[str] = []
    if not evidence.title.strip():
        missing.append("title")
    if not (evidence.holder or "").strip():
        missing.append("holder")
    if not (evidence.certificate_no or "").strip() and not any((value or "").strip() for value in (evidence.issuer, evidence.issued_at, evidence.valid_from, evidence.valid_to)):
        missing.append("certificate_no_or_issuer_or_date")
    return missing


def extract_pending_knowledge_evidence(*, user_id: str | None = None) -> tuple[int, list[str]]:
    """Let the configured multimodal model process pending image evidence."""

    root = knowledge_storage._knowledge_root_path(user_id=user_id)
    with _registry_lock:
        pending = [KnowledgeEvidence(**raw) for raw in _load_registry(root)["evidence"] if raw.get("extraction_status") in {None, "pending", "partial", "failed"} and raw.get("verification_status") != "human_verified"]
    if not pending:
        return 0, []

    processed = 0
    warnings: list[str] = []
    for evidence in pending:
        asset = get_knowledge_asset(evidence.asset_ids[0], applicant_id=evidence.applicant_id, user_id=user_id)
        image_path = resolve_asset_file(asset, thumbnail=False, user_id=user_id)
        try:
            extraction = extract_evidence_from_image(
                image_path.read_bytes(),
                filename=asset.original_filename,
                mime_type=asset.mime_type,
                evidence_type=evidence.evidence_type,
                title=evidence.title,
            )
        except VisionModelUnavailableError as exc:
            return processed, [f"{exc}（待识别图片 {len(pending)} 张）"]
        except EvidenceExtractionError as exc:
            message = f"图片识别失败：{asset.original_filename}；原因：{exc}"
            update_knowledge_evidence(
                evidence.evidence_id,
                KnowledgeEvidencePatch(verification_status="needs_review"),
                applicant_id=evidence.applicant_id,
                user_id=user_id,
                extraction_status="failed",
                extraction_warnings=[message],
            )
            warnings.append(message)
            continue

        extraction_warnings = list(extraction.warnings)
        if not extraction.is_knowledge_evidence:
            extraction_warnings.append("模型判断该图片可能不是申报证据，需要人工确认后才能标记为无关图片。")
            warnings.append(f"{asset.original_filename}：模型判断为非证据，需要人工确认。")
        update_knowledge_evidence(
            evidence.evidence_id,
            KnowledgeEvidencePatch(
                evidence_type=extraction.evidence_type,
                title=extraction.title,
                holder=extraction.holder,
                issuer=extraction.issuer,
                certificate_no=extraction.certificate_no,
                issued_at=extraction.issued_at,
                valid_from=extraction.valid_from,
                valid_to=extraction.valid_to,
                ocr_text=extraction.ocr_text,
                visual_summary=extraction.visual_summary,
                keywords=extraction.keywords,
                applicable_chapters=extraction.applicable_chapters,
                project_tags=extraction.project_tags,
                verification_status="needs_review",
                extraction_confidence=extraction.confidence,
            ),
            applicant_id=evidence.applicant_id,
            user_id=user_id,
            extraction_status=extraction.status,
            extraction_provider=extraction.provider,
            extraction_warnings=extraction_warnings,
        )
        processed += 1
    if processed:
        warnings.append(f"多模态模型已识别并更新 {processed} 张知识库图片。")
    return processed, warnings


def reextract_knowledge_evidence(
    evidence_id: str,
    *,
    applicant_id: str,
    user_id: str | None = None,
) -> KnowledgeEvidence:
    """Run the configured extractor again while keeping the card reviewable."""

    evidence = get_knowledge_evidence(evidence_id, applicant_id=applicant_id, user_id=user_id)
    asset = get_knowledge_asset(evidence.asset_ids[0], applicant_id=applicant_id, user_id=user_id)
    image_path = resolve_asset_file(asset, thumbnail=False, user_id=user_id)
    extraction = extract_evidence_from_image(
        image_path.read_bytes(),
        filename=asset.original_filename,
        mime_type=asset.mime_type,
        evidence_type=evidence.evidence_type,
        title=evidence.title,
    )
    return update_knowledge_evidence(
        evidence_id,
        KnowledgeEvidencePatch(
            evidence_type=extraction.evidence_type,
            title=extraction.title,
            holder=extraction.holder or evidence.holder,
            issuer=extraction.issuer or evidence.issuer,
            certificate_no=extraction.certificate_no or evidence.certificate_no,
            issued_at=extraction.issued_at or evidence.issued_at,
            valid_from=extraction.valid_from or evidence.valid_from,
            valid_to=extraction.valid_to or evidence.valid_to,
            ocr_text=extraction.ocr_text or evidence.ocr_text,
            visual_summary=extraction.visual_summary or evidence.visual_summary,
            keywords=list(dict.fromkeys([*evidence.keywords, *extraction.keywords])),
            verification_status="needs_review",
            extraction_confidence=extraction.confidence,
        ),
        applicant_id=applicant_id,
        user_id=user_id,
        extraction_status=extraction.status,
        extraction_provider=extraction.provider,
        extraction_warnings=extraction.warnings,
    )


def delete_knowledge_evidence(
    evidence_id: str,
    *,
    applicant_id: str,
    user_id: str | None = None,
) -> list[str]:
    """Delete evidence, unreferenced assets, generated cards, and index pointers."""

    root = knowledge_storage._knowledge_root_path(user_id=user_id).resolve()
    with _registry_lock:
        registry = _load_registry(root)
        target = next(
            (KnowledgeEvidence(**raw) for raw in registry["evidence"] if raw.get("evidence_id") == evidence_id and raw.get("applicant_id") == applicant_id),
            None,
        )
        if target is None:
            raise KeyError(evidence_id)

        registry["evidence"] = [raw for raw in registry["evidence"] if raw.get("evidence_id") != evidence_id]
        remaining_asset_ids = {asset_id for raw in registry["evidence"] for asset_id in raw.get("asset_ids", []) if isinstance(asset_id, str)}
        deleted_asset_ids: list[str] = []
        kept_assets: list[dict[str, Any]] = []
        for raw in registry["assets"]:
            asset = KnowledgeAsset(**raw)
            if asset.asset_id not in target.asset_ids or asset.asset_id in remaining_asset_ids:
                kept_assets.append(raw)
                continue
            asset_path = (root / asset.storage_path).resolve()
            asset_path.relative_to(root / _ASSETS_DIR)
            asset_dir = asset_path.parent
            if asset_dir.exists():
                shutil.rmtree(asset_dir)
            deleted_asset_ids.append(asset.asset_id)
        registry["assets"] = kept_assets
        _atomic_write_json(_registry_path(root), registry)

        storage = knowledge_storage.get_knowledge_storage()
        indexes = storage.list_indexes(user_id=user_id)
        storage.save_all_indexes(
            [entry for entry in indexes if entry.evidence_id != evidence_id],
            user_id=user_id,
        )
        return deleted_asset_ids


def resolve_asset_file(asset: KnowledgeAsset, *, thumbnail: bool, user_id: str | None = None) -> Path:
    root = knowledge_storage._knowledge_root_path(user_id=user_id).resolve()
    relative = asset.thumbnail_path if thumbnail else asset.storage_path
    if not relative:
        raise FileNotFoundError(asset.asset_id)
    resolved = (root / relative).resolve()
    resolved.relative_to(root)
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(asset.asset_id)
    return resolved
