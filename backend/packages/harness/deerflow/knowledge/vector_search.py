"""Deterministic local vector helpers for knowledge-index hybrid search."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Iterable

VECTOR_DIMENSIONS = 192
_ASCII_WORD_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z_\-]{1,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def _hash_index(term: str) -> tuple[int, float]:
    digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big", signed=False)
    sign = 1.0 if value & 1 else -1.0
    return value % VECTOR_DIMENSIONS, sign


def _cjk_ngrams(chunk: str) -> Iterable[str]:
    if len(chunk) <= 2:
        if chunk:
            yield chunk
        return
    for length in (2, 3, 4):
        if len(chunk) < length:
            continue
        for start in range(0, len(chunk) - length + 1):
            yield chunk[start : start + length]
    yield chunk


def semantic_terms(text: str) -> list[str]:
    """Return normalized terms used for deterministic semantic hashing."""

    folded = text.casefold()
    terms: list[str] = []
    terms.extend(match.group(0) for match in _ASCII_WORD_RE.finditer(folded))
    for chunk in _CJK_RE.findall(folded):
        terms.extend(_cjk_ngrams(chunk))
    return terms


def embed_text(text: str) -> list[float]:
    """Embed text into a small normalized feature-hashing vector.

    This is not a remote embedding model. It is a deterministic local semantic
    vector that gives the knowledge index a dependency-free second retrieval
    signal alongside FTS/BM25.
    """

    counts = Counter(semantic_terms(text))
    vector = [0.0] * VECTOR_DIMENSIONS
    for term, count in counts.items():
        index, sign = _hash_index(term)
        vector[index] += sign * (1.0 + math.log(count))
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    return sum(left[index] * right[index] for index in range(size))


def semantic_similarity(query: str, text: str) -> float:
    if not query.strip() or not text.strip():
        return 0.0
    return max(0.0, cosine_similarity(embed_text(query), embed_text(text)))
