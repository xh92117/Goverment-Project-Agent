"""Optional real-embedding boundary for knowledge retrieval.

The local feature-hash vector remains an offline fallback.  When configured,
any LangChain-compatible Embeddings implementation can replace it without
coupling the knowledge package to one provider.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import threading
from typing import Any

from deerflow.config import get_app_config

logger = logging.getLogger(__name__)

LOCAL_HASH_SIGNATURE = "local-feature-hash-v1"
_provider_lock = threading.Lock()
_provider_cache: dict[str, Any] = {}


def _embedding_config():
    return get_app_config().knowledge_retrieval.embedding


def configured_embedding_signature() -> str:
    config = _embedding_config()
    if not config.enabled:
        return LOCAL_HASH_SIGNATURE
    public_config = {key: value for key, value in config.provider_kwargs().items() if key not in {"api_key", "token"}}
    digest = hashlib.sha256(json.dumps(public_config, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return f"{config.use}:{digest}"


def _provider() -> Any:
    config = _embedding_config()
    if not config.enabled:
        return None
    signature = configured_embedding_signature()
    with _provider_lock:
        cached = _provider_cache.get(signature)
        if cached is not None:
            return cached
        module_name, separator, class_name = config.use.partition(":")
        if not separator or not module_name or not class_name:
            raise ValueError("knowledge_retrieval.embedding.use must use the 'module:Class' format.")
        provider_class = getattr(importlib.import_module(module_name), class_name)
        provider = provider_class(**config.provider_kwargs())
        if not callable(getattr(provider, "embed_documents", None)) or not callable(getattr(provider, "embed_query", None)):
            raise TypeError(f"{config.use} is not a LangChain-compatible Embeddings provider.")
        _provider_cache[signature] = provider
        return provider


def embed_documents_with_signature(texts: list[str]) -> tuple[list[list[float]], str]:
    """Embed documents in batches, falling back to deterministic local vectors."""

    config = _embedding_config()
    if config.enabled:
        try:
            provider = _provider()
            vectors: list[list[float]] = []
            for start in range(0, len(texts), config.batch_size):
                batch = provider.embed_documents(texts[start : start + config.batch_size])
                vectors.extend([list(map(float, vector)) for vector in batch])
            if len(vectors) != len(texts):
                raise ValueError("Embedding provider returned an unexpected vector count.")
            dimensions = {len(vector) for vector in vectors}
            if vectors and (0 in dimensions or len(dimensions) != 1):
                raise ValueError("Embedding provider returned empty or inconsistent vector dimensions.")
            return vectors, configured_embedding_signature()
        except Exception:
            logger.warning("Knowledge embedding provider failed; using the offline feature-hash fallback.", exc_info=True)

    return embed_texts_locally(texts), LOCAL_HASH_SIGNATURE


def embed_texts_locally(texts: list[str]) -> list[list[float]]:
    """Create deterministic offline vectors without touching a configured provider."""

    from deerflow.knowledge.vector_search import embed_text

    return [embed_text(text) for text in texts]


def embed_query_for_signature(text: str, signature: str) -> list[float] | None:
    """Embed a query only when it matches the vectors stored in the sidecar."""

    if signature == LOCAL_HASH_SIGNATURE:
        from deerflow.knowledge.vector_search import embed_text

        return embed_text(text)
    if signature != configured_embedding_signature():
        logger.warning("Knowledge embedding configuration changed; rebuild the knowledge index before semantic search.")
        return None
    try:
        return list(map(float, _provider().embed_query(text)))
    except Exception:
        logger.warning("Knowledge query embedding failed; semantic candidates are unavailable for this query.", exc_info=True)
        return None
