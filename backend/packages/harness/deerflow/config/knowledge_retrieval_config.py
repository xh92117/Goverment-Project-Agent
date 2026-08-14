"""Configuration for knowledge-base retrieval and optional embeddings."""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class KnowledgeChunkingConfig(BaseModel):
    """Model-assisted semantic chunk planning with deterministic fallback."""

    enabled: bool = True
    minimum_section_chars: int = Field(default=300, ge=1, le=100_000)
    minimum_chunk_chars: int = Field(default=500, ge=1, le=20_000)
    target_chunk_chars: int = Field(default=1_600, ge=50, le=50_000)
    maximum_chunk_chars: int = Field(default=3_200, ge=100, le=100_000)
    unit_max_chars: int = Field(default=600, ge=50, le=10_000)
    max_prompt_chars: int = Field(default=24_000, ge=4_000, le=200_000)
    max_sections_per_call: int = Field(default=8, ge=1, le=50)
    max_call_attempts: int = Field(default=2, ge=1, le=5)
    circuit_breaker_failures: int = Field(default=3, ge=1, le=20)

    @model_validator(mode="after")
    def validate_thresholds(self) -> Self:
        if self.minimum_chunk_chars > self.target_chunk_chars:
            raise ValueError("minimum_chunk_chars must not exceed target_chunk_chars")
        if self.target_chunk_chars > self.maximum_chunk_chars:
            raise ValueError("target_chunk_chars must not exceed maximum_chunk_chars")
        if self.unit_max_chars > self.maximum_chunk_chars:
            raise ValueError("unit_max_chars must not exceed maximum_chunk_chars")
        return self


class KnowledgeEmbeddingConfig(BaseModel):
    """Provider-neutral LangChain embedding configuration."""

    enabled: bool = False
    use: str = "langchain_openai:OpenAIEmbeddings"
    model: str | None = None
    batch_size: int = Field(default=32, ge=1, le=256)
    max_input_chars: int = Field(default=8_000, ge=256, le=100_000)
    dimensions: int | None = Field(default=None, ge=1)
    model_config = ConfigDict(extra="allow")

    def provider_kwargs(self) -> dict[str, Any]:
        values = self.model_dump(exclude={"enabled", "use", "batch_size", "max_input_chars"}, exclude_none=True)
        return values


class KnowledgeQualityConfig(BaseModel):
    """Thresholds for the post-build knowledge quality gate."""

    enabled: bool = True
    minimum_body_coverage: float = Field(default=0.98, ge=0.0, le=1.0)
    critical_leaf_chunk_chars: int = Field(default=120, ge=1, le=10_000)
    minimum_leaf_chunk_chars: int = Field(default=500, ge=1, le=10_000)
    maximum_short_chunk_ratio: float = Field(default=0.05, ge=0.0, le=1.0)
    maximum_chunk_chars: int = Field(default=3_600, ge=100, le=100_000)
    max_reported_issues: int = Field(default=200, ge=1, le=2_000)

    @model_validator(mode="after")
    def validate_thresholds(self) -> Self:
        if self.critical_leaf_chunk_chars > self.minimum_leaf_chunk_chars:
            raise ValueError("critical_leaf_chunk_chars must not exceed minimum_leaf_chunk_chars")
        return self


class KnowledgeRetrievalConfig(BaseModel):
    """Knowledge search behavior shared by indexing and online retrieval."""

    default_search_mode: Literal["hybrid", "keyword", "semantic"] = "hybrid"
    content_max_chars: int = Field(default=100_000, ge=1_000, le=1_000_000)
    semantic_min_similarity: float = Field(default=0.08, ge=0.0, le=1.0)
    chunking: KnowledgeChunkingConfig = Field(default_factory=KnowledgeChunkingConfig)
    embedding: KnowledgeEmbeddingConfig = Field(default_factory=KnowledgeEmbeddingConfig)
    quality: KnowledgeQualityConfig = Field(default_factory=KnowledgeQualityConfig)
