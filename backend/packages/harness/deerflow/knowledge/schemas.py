"""Schemas for the lightweight project declaration knowledge base."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

KnowledgeLibrary = Literal[
    "application_templates",
    "historical_proposals",
    "research_foundations",
    "team_achievements",
    "policy_guides",
    "literature_materials",
    "budget_rules",
]

ConfidentialityLevel = Literal["public", "internal", "confidential", "restricted"]
KnowledgeSearchMode = Literal["hybrid", "keyword", "semantic"]
KnowledgeScope = Literal["private", "public"]
KnowledgeVerificationStatus = Literal["needs_review", "human_verified", "rejected"]
KnowledgeExtractionStatus = Literal["pending", "partial", "completed", "failed"]


class KnowledgeAsset(BaseModel):
    """A binary image asset kept outside the text-oriented LLM-Wiki map."""

    asset_id: str
    applicant_id: str
    title: str
    original_filename: str
    storage_path: str
    thumbnail_path: str | None = None
    mime_type: str
    sha256: str
    byte_size: int
    width: int | None = None
    height: int | None = None
    source_file_path: str | None = None
    source_page: int | None = None
    source_anchor: str | None = None
    confidentiality_level: ConfidentialityLevel = "internal"
    created_at: str
    updated_at: str


class KnowledgeEvidence(BaseModel):
    """Structured, reviewable evidence derived from one or more image assets."""

    evidence_id: str
    applicant_id: str
    asset_ids: list[str] = Field(default_factory=list)
    evidence_type: str = "image_evidence"
    suggested_evidence_type: str | None = None
    title: str
    holder: str | None = None
    issuer: str | None = None
    certificate_no: str | None = None
    issued_at: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    ocr_text: str = ""
    visual_summary: str = ""
    keywords: list[str] = Field(default_factory=list)
    applicable_chapters: list[str] = Field(default_factory=list)
    project_tags: list[str] = Field(default_factory=list)
    verification_status: KnowledgeVerificationStatus = "needs_review"
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    extraction_status: KnowledgeExtractionStatus = "pending"
    extraction_provider: str | None = None
    extraction_warnings: list[str] = Field(default_factory=list)
    review_notes: str = ""
    reviewed_at: str | None = None
    reviewed_by: str | None = None
    card_file_path: str
    confidentiality_level: ConfidentialityLevel = "internal"
    created_at: str
    updated_at: str


class KnowledgeEvidencePatch(BaseModel):
    """Human-review patch for an image evidence card."""

    evidence_type: str | None = None
    title: str | None = Field(default=None, min_length=1)
    holder: str | None = None
    issuer: str | None = None
    certificate_no: str | None = None
    issued_at: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    ocr_text: str | None = None
    visual_summary: str | None = None
    keywords: list[str] | None = None
    applicable_chapters: list[str] | None = None
    project_tags: list[str] | None = None
    verification_status: KnowledgeVerificationStatus | None = None
    extraction_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    review_notes: str | None = None
    confidentiality_level: ConfidentialityLevel | None = None


class KnowledgeDocumentCreate(BaseModel):
    """Request payload for creating a knowledge-base document."""

    title: str = Field(..., min_length=1, description="Document title")
    library: KnowledgeLibrary = Field(..., description="Knowledge library")
    doc_type: str = Field(..., min_length=1, description="Document type")
    content: str = Field(default="", description="Extracted text or structured summary")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Flexible metadata fields")
    source: str | None = Field(default=None, description="Human-readable source")
    source_uri: str | None = Field(default=None, description="Source URL or file path")
    confidentiality_level: ConfidentialityLevel = Field(default="internal", description="Access and reuse level")


class KnowledgeDocumentPatch(BaseModel):
    """Patch payload for updating a knowledge-base document."""

    title: str | None = Field(default=None, min_length=1)
    library: KnowledgeLibrary | None = None
    doc_type: str | None = Field(default=None, min_length=1)
    content: str | None = None
    metadata: dict[str, Any] | None = None
    source: str | None = None
    source_uri: str | None = None
    confidentiality_level: ConfidentialityLevel | None = None


class KnowledgeDocument(BaseModel):
    """Persisted knowledge-base document."""

    document_id: str
    title: str
    library: KnowledgeLibrary
    doc_type: str
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    source_uri: str | None = None
    confidentiality_level: ConfidentialityLevel = "internal"
    created_at: str
    updated_at: str


class KnowledgeSearchRequest(BaseModel):
    """Search request for the lightweight knowledge base."""

    query: str = Field(default="", description="Keyword query")
    libraries: list[KnowledgeLibrary] | None = Field(default=None, description="Optional library filter")
    doc_types: list[str] | None = Field(default=None, description="Optional document type filter")
    metadata_filters: dict[str, Any] = Field(default_factory=dict, description="Exact-match metadata filters")
    include_restricted: bool = Field(default=False, description="Whether to include restricted documents")
    limit: int = Field(default=10, ge=1, le=100)


class KnowledgeSearchResult(BaseModel):
    """A scored knowledge-base search hit."""

    document: KnowledgeDocument
    score: float
    matched_fields: list[str] = Field(default_factory=list)
    snippet: str = ""
    scope: KnowledgeScope = "private"


class KnowledgeSearchResponse(BaseModel):
    """Search response for knowledge-base queries."""

    results: list[KnowledgeSearchResult]
    count: int


class KnowledgeIndexSection(BaseModel):
    """A section pointer inside an indexed source file."""

    heading: str = Field(..., min_length=1, description="Human-readable section heading")
    anchor: str | None = Field(default=None, description="Markdown heading or section anchor")
    use_for: list[str] = Field(default_factory=list, description="Proposal chapters or purposes this section supports")
    summary: str = Field(default="", description="Short LLM-written note about this section")


class KnowledgeIndexEntryCreate(BaseModel):
    """Request payload for creating an LLM-Wiki index entry."""

    title: str = Field(..., min_length=1, description="Index entry title")
    entry_type: str = Field(default="document", description="Index granularity: document, section, subsection, or evidence")
    category: str = Field(..., min_length=1, description="Business folder/category, such as 国内外研究现状")
    file_path: str = Field(..., min_length=1, description="Path relative to the knowledge-base root")
    folder_path: str | None = Field(default=None, description="Folder path relative to the knowledge-base root")
    domain: str | None = Field(default=None, description="Technical domain")
    authority: str | None = Field(default=None, description="Issuing authority or responsible department")
    document_type: str | None = Field(default=None, description="Business document type, such as application_guide or budget_rule")
    year: int | None = Field(default=None, ge=1900, le=2200, description="Primary applicable or publication year")
    keywords: list[str] = Field(default_factory=list)
    technical_terms: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    research_objects: list[str] = Field(default_factory=list)
    proposal_sections: list[str] = Field(default_factory=list)
    evidence_type: str | None = None
    evidence_id: str | None = None
    asset_ids: list[str] = Field(default_factory=list)
    applicant_id: str | None = None
    verification_status: KnowledgeVerificationStatus | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    source_file_path: str | None = None
    source_anchor: str | None = None
    chunk_file_path: str | None = None
    summary: str = Field(default="", description="LLM-written index summary")
    recommended_sections: list[KnowledgeIndexSection] = Field(default_factory=list)
    applicable_chapters: list[str] = Field(default_factory=list)
    project_types: list[str] = Field(default_factory=list)
    source_document_id: str | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    confidentiality_level: ConfidentialityLevel = Field(default="internal")


class KnowledgeIndexEntryPatch(BaseModel):
    """Patch payload for an LLM-Wiki index entry."""

    title: str | None = Field(default=None, min_length=1)
    entry_type: str | None = None
    category: str | None = Field(default=None, min_length=1)
    file_path: str | None = Field(default=None, min_length=1)
    folder_path: str | None = None
    domain: str | None = None
    authority: str | None = None
    document_type: str | None = None
    year: int | None = Field(default=None, ge=1900, le=2200)
    keywords: list[str] | None = None
    technical_terms: list[str] | None = None
    methods: list[str] | None = None
    research_objects: list[str] | None = None
    proposal_sections: list[str] | None = None
    evidence_type: str | None = None
    evidence_id: str | None = None
    asset_ids: list[str] | None = None
    applicant_id: str | None = None
    verification_status: KnowledgeVerificationStatus | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    source_file_path: str | None = None
    source_anchor: str | None = None
    chunk_file_path: str | None = None
    summary: str | None = None
    recommended_sections: list[KnowledgeIndexSection] | None = None
    applicable_chapters: list[str] | None = None
    project_types: list[str] | None = None
    source_document_id: str | None = None
    metadata: dict[str, Any] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    confidentiality_level: ConfidentialityLevel | None = None


class KnowledgeIndexEntry(BaseModel):
    """Persisted LLM-Wiki index entry.

    The entry is a map, not the final knowledge body. Agents search these
    entries first, then read the referenced file path and section.
    """

    index_id: str
    title: str
    entry_type: str = "document"
    category: str
    file_path: str
    folder_path: str | None = None
    domain: str | None = None
    authority: str | None = None
    document_type: str | None = None
    year: int | None = None
    keywords: list[str] = Field(default_factory=list)
    technical_terms: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    research_objects: list[str] = Field(default_factory=list)
    proposal_sections: list[str] = Field(default_factory=list)
    evidence_type: str | None = None
    evidence_id: str | None = None
    asset_ids: list[str] = Field(default_factory=list)
    applicant_id: str | None = None
    verification_status: KnowledgeVerificationStatus | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    source_file_path: str | None = None
    source_anchor: str | None = None
    chunk_file_path: str | None = None
    summary: str = ""
    recommended_sections: list[KnowledgeIndexSection] = Field(default_factory=list)
    applicable_chapters: list[str] = Field(default_factory=list)
    project_types: list[str] = Field(default_factory=list)
    source_document_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.8
    confidentiality_level: ConfidentialityLevel = "internal"
    created_at: str
    updated_at: str


class KnowledgeIndexSearchRequest(BaseModel):
    """Search request for the LLM-Wiki index layer."""

    query: str = Field(default="", description="Topic or chapter query")
    query_variants: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Complementary lexical queries produced by query planning; no embedding model is required",
    )
    entry_types: list[str] | None = Field(default=None, description="Index granularity filters, such as document or section")
    categories: list[str] | None = Field(default=None, description="Business category filters")
    applicable_chapters: list[str] | None = Field(default=None, description="Proposal chapter filters")
    domains: list[str] | None = Field(default=None, description="Technical domain filters")
    project_types: list[str] | None = Field(default=None, description="Project type filters")
    authorities: list[str] | None = Field(default=None, description="Issuing-authority filters")
    document_types: list[str] | None = Field(default=None, description="Business document-type filters")
    years: list[int] | None = Field(default=None, description="Applicable or publication year filters")
    valid_on: str | None = Field(default=None, description="ISO date used to exclude entries outside their validity window")
    applicant_ids: list[str] | None = Field(default=None, description="Applicant-owner filters for evidence entries")
    evidence_types: list[str] | None = Field(default=None, description="Evidence type filters")
    verification_statuses: list[KnowledgeVerificationStatus] | None = Field(default=None)
    metadata_filters: dict[str, Any] = Field(default_factory=dict)
    include_restricted: bool = False
    search_mode: KnowledgeSearchMode = Field(default="hybrid", description="Retrieval mode: keyword, semantic, or hybrid")
    semantic_weight: float = Field(default=12.0, ge=0.0, le=50.0, description="Semantic-vector score multiplier")
    limit: int = Field(default=10, ge=1, le=100)


class KnowledgeIndexSearchResult(BaseModel):
    """A scored LLM-Wiki index search hit."""

    entry: KnowledgeIndexEntry
    score: float
    matched_fields: list[str] = Field(default_factory=list)
    matched_queries: list[str] = Field(default_factory=list)
    scope: KnowledgeScope = Field(default="private", description="Knowledge library that produced this hit")


class KnowledgeIndexSearchResponse(BaseModel):
    """Search response for LLM-Wiki index queries."""

    results: list[KnowledgeIndexSearchResult]
    count: int


class KnowledgeFileReadRequest(BaseModel):
    """Request to read an indexed knowledge file or section."""

    file_path: str = Field(..., min_length=1, description="Path relative to knowledge-base root")
    anchor: str | None = Field(default=None, description="Optional markdown heading to extract")
    max_chars: int = Field(default=12000, ge=1, le=100000)


class KnowledgeFileReadResponse(BaseModel):
    """Response containing content read from a knowledge-base file."""

    file_path: str
    resolved_path: str
    anchor: str | None = None
    content: str
    truncated: bool = False
    scope: KnowledgeScope = "private"


class KnowledgeFileSaveRequest(BaseModel):
    """Request to save an editable knowledge-base markdown/text file."""

    file_path: str = Field(..., min_length=1, description="Path relative to knowledge-base root")
    content: str = Field(default="", description="New markdown or plain-text content")
    anchor: str | None = Field(default=None, description="Optional markdown heading to replace")


class KnowledgeFileSaveResponse(BaseModel):
    """Response after saving a knowledge-base markdown/text file."""

    file_path: str
    resolved_path: str
    anchor: str | None = None
    bytes_written: int
    saved: bool = True


class KnowledgeIndexBuildRequest(BaseModel):
    """Request to build LLM-Wiki index entries from a knowledge-base folder."""

    folder_path: str = Field(default="", description="Folder path relative to the knowledge-base root")
    recursive: bool = Field(default=True, description="Whether to scan subfolders")
    include_extensions: list[str] = Field(default_factory=lambda: [".md", ".markdown", ".txt", ".docx", ".pdf", ".xlsx", ".xls", ".csv", ".tsv"])
    replace_existing: bool = Field(default=True, description="Replace existing index entries with the same file_path")
    category: str | None = Field(default=None, description="Override category; default is the first folder name")
    domain: str | None = Field(default=None, description="Override domain; default is the second folder name")
    project_types: list[str] = Field(default_factory=list)
    max_files: int = Field(default=200, ge=1, le=5000)
    incremental: bool = Field(default=True, description="Skip unchanged source files when existing chunks are valid")


class KnowledgeIndexBuildResponse(BaseModel):
    """Response after building index entries from source files."""

    root_path: str
    scanned_files: int
    created: int
    updated: int
    reused: int = 0
    skipped: int
    deleted: int = 0
    document_entries: int = 0
    section_entries: int = 0
    chunk_files_created: int = 0
    deduplicated_files: list[str] = Field(default_factory=list)
    version_backup_path: str | None = None
    parser_counts: dict[str, int] = Field(default_factory=dict)
    parse_errors: list[dict[str, str]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    scale_stats: dict[str, Any] = Field(default_factory=dict)
    entries: list[KnowledgeIndexEntry] = Field(default_factory=list)


class KnowledgeIncomingRule(BaseModel):
    """Keyword rule for organizing incoming files."""

    name: str = Field(..., min_length=1)
    keywords: list[str] = Field(default_factory=list)


class KnowledgeIncrementalUpdateRequest(BaseModel):
    """Request for one-click incoming-file organization and index update."""

    folder_path: str = Field(default="", description="Folder path to index after organization")
    recursive: bool = True
    include_extensions: list[str] = Field(default_factory=lambda: [".md", ".markdown", ".txt", ".docx", ".pdf", ".xlsx", ".xls", ".csv", ".tsv"])
    organize_extensions: list[str] = Field(default_factory=lambda: [".md", ".markdown", ".txt", ".docx", ".pdf", ".xlsx", ".xls", ".csv", ".tsv"])
    replace_existing: bool = True
    incoming_path: str = "_incoming"
    organize_incoming: bool = True
    dry_run: bool = False
    default_category: str = "未分类"
    default_domain: str | None = "通用"
    project_types: list[str] = Field(default_factory=list)
    max_files: int = Field(default=200, ge=1, le=5000)
    incremental: bool = True
    classification_rules: list[KnowledgeIncomingRule] = Field(default_factory=list)
    domain_rules: list[KnowledgeIncomingRule] = Field(default_factory=list)


class KnowledgeOrganizedFileResult(BaseModel):
    """A single incoming file organization result for API responses."""

    source_path: str
    target_path: str | None = None
    category: str | None = None
    domain: str | None = None
    status: str
    reason: str | None = None


class KnowledgeOrganizeResponse(BaseModel):
    """Response after organizing incoming knowledge files."""

    root_path: str
    incoming_path: str
    dry_run: bool
    scanned: int
    moved: int
    skipped: int
    files: list[KnowledgeOrganizedFileResult] = Field(default_factory=list)


class KnowledgeIncrementalUpdateResponse(BaseModel):
    """Response for one-click incoming-file organization and index update."""

    organization: KnowledgeOrganizeResponse | None = None
    index_build: KnowledgeIndexBuildResponse


class KnowledgeIndexListRequest(BaseModel):
    """Paged list request for LLM-Wiki index entries."""

    category: str | None = None
    query: str = ""
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=500)


class KnowledgeIndexListResponse(BaseModel):
    """Paged list response for LLM-Wiki index entries."""

    entries: list[KnowledgeIndexEntry]
    total: int
    offset: int
    limit: int


class KnowledgeRecallEvalCase(BaseModel):
    """One expected-recall case for knowledge-index evaluation."""

    query: str = Field(..., min_length=1)
    query_variants: list[str] = Field(default_factory=list)
    entry_types: list[str] | None = None
    categories: list[str] | None = None
    applicable_chapters: list[str] | None = None
    domains: list[str] | None = None
    project_types: list[str] | None = None
    authorities: list[str] | None = None
    document_types: list[str] | None = None
    years: list[int] | None = None
    valid_on: str | None = None
    applicant_ids: list[str] | None = None
    expected_file_paths: list[str] = Field(default_factory=list)
    expected_index_ids: list[str] = Field(default_factory=list)
    expected_categories: list[str] = Field(default_factory=list)
    forbidden_file_paths: list[str] = Field(default_factory=list)


class KnowledgeRecallEvalRequest(BaseModel):
    """Evaluate recall quality over a small golden set."""

    cases: list[KnowledgeRecallEvalCase] = Field(default_factory=list)
    category: str | None = None
    limit: int = Field(default=10, ge=1, le=50)
    search_mode: KnowledgeSearchMode = "hybrid"


class KnowledgeRecallEvalCaseResult(BaseModel):
    """Recall evaluation result for one query."""

    query: str
    expected_count: int
    hit: bool
    first_rank: int | None = None
    reciprocal_rank: float = 0.0
    forbidden_hits: list[str] = Field(default_factory=list)
    top_results: list[KnowledgeIndexSearchResult] = Field(default_factory=list)


class KnowledgeRecallEvalResponse(BaseModel):
    """Aggregate recall evaluation metrics."""

    cases: list[KnowledgeRecallEvalCaseResult]
    total_cases: int
    hit_count: int
    recall_at_k: float
    mrr: float
    forbidden_hit_count: int = 0
    contamination_rate: float = 0.0
