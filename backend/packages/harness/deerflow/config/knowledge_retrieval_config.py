"""Configuration for knowledge-base retrieval and optional embeddings."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeEmbeddingConfig(BaseModel):
    """Provider-neutral LangChain embedding configuration."""

    enabled: bool = False
    use: str = "langchain_openai:OpenAIEmbeddings"
    model: str | None = None
    batch_size: int = Field(default=32, ge=1, le=256)
    dimensions: int | None = Field(default=None, ge=1)
    model_config = ConfigDict(extra="allow")

    def provider_kwargs(self) -> dict[str, Any]:
        values = self.model_dump(exclude={"enabled", "use", "batch_size"}, exclude_none=True)
        return values


class KnowledgeQualityConfig(BaseModel):
    """Thresholds for the post-build knowledge quality gate."""

    enabled: bool = True
    minimum_body_coverage: float = Field(default=0.98, ge=0.0, le=1.0)
    minimum_leaf_chunk_chars: int = Field(default=80, ge=1, le=10_000)
    maximum_chunk_chars: int = Field(default=3_600, ge=100, le=100_000)
    max_reported_issues: int = Field(default=200, ge=1, le=2_000)


class KnowledgeRetrievalConfig(BaseModel):
    """Knowledge search behavior shared by indexing and online retrieval."""

    default_search_mode: Literal["hybrid", "keyword", "semantic"] = "hybrid"
    content_max_chars: int = Field(default=100_000, ge=1_000, le=1_000_000)
    semantic_min_similarity: float = Field(default=0.08, ge=0.0, le=1.0)
    embedding: KnowledgeEmbeddingConfig = Field(default_factory=KnowledgeEmbeddingConfig)
    quality: KnowledgeQualityConfig = Field(default_factory=KnowledgeQualityConfig)
