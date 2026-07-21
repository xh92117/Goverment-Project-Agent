"""Built-in tools for LLM-Wiki knowledge-base access."""

from __future__ import annotations

import dataclasses
import json
from urllib.parse import quote

from langchain.tools import tool

from deerflow.knowledge import (
    KnowledgeFileReadRequest,
    KnowledgeIndexBuildRequest,
    KnowledgeIndexSearchRequest,
    KnowledgeOrganizeResponse,
    build_knowledge_index_from_folder,
    get_knowledge_evidence,
    organize_incoming_files,
    organize_options_from_config,
    read_knowledge_file_combined,
    search_knowledge_evidence,
    search_knowledge_index_entries_combined,
)
from deerflow.runtime.user_context import get_effective_user_id


def _json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _compact(value: str | None, *, limit: int = 240) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


@tool("knowledge_search_index", parse_docstring=True)
def knowledge_search_index_tool(
    query: str,
    query_variants: list[str] | None = None,
    entry_types: list[str] | None = None,
    categories: list[str] | None = None,
    applicable_chapters: list[str] | None = None,
    domains: list[str] | None = None,
    project_types: list[str] | None = None,
    authorities: list[str] | None = None,
    document_types: list[str] | None = None,
    years: list[int] | None = None,
    valid_on: str | None = None,
    applicant_ids: list[str] | None = None,
    limit: int = 10,
) -> str:
    """Search the LLM-Wiki knowledge-base index before reading source files.

    Use this tool first when answering from the knowledge base. Search by
    topic keywords plus target proposal chapter, then read the returned chunk
    file_path with knowledge_read_file before producing the final
    answer. Do not paste this tool output directly to the user.

    Args:
        query: Primary topic, title, technology keyword, or proposal chapter query.
        query_variants: Optional complementary lexical queries. Use 2-4 variants for complex searches; vary business wording instead of repeating the same query.
        entry_types: Optional index granularity filters, such as document, section, or subsection.
        categories: Optional business categories, such as 国内外研究现状, 历史申报书, 团队成果.
        applicable_chapters: Optional target proposal chapters, such as 国内外研究现状 or 技术路线.
        domains: Optional technical domains, such as 路基工程 or 人工智能.
        project_types: Optional project types, such as 科研项目申报 or 重点研发.
        authorities: Optional exact issuing authorities, such as 科技部 or 某省科学技术厅.
        document_types: Optional business document types, such as application_notice, application_guide, application_template, budget_rule, or historical_proposal.
        years: Optional applicable or publication years. Use this for year-specific policy work.
        valid_on: Optional ISO date used to exclude expired or not-yet-effective sources.
        applicant_ids: Optional applicant-owner filter for applicant-specific evidence.
        limit: Maximum number of index results to return.
    """
    response = search_knowledge_index_entries_combined(
        KnowledgeIndexSearchRequest(
            query=query,
            query_variants=query_variants or [],
            entry_types=entry_types,
            categories=categories,
            applicable_chapters=applicable_chapters,
            domains=domains,
            project_types=project_types,
            authorities=authorities,
            document_types=document_types,
            years=years,
            valid_on=valid_on,
            applicant_ids=applicant_ids,
            search_mode="keyword",
            limit=max(1, min(limit, 50)),
        ),
        user_id=get_effective_user_id(),
    )
    if not response.results:
        return "Knowledge index search found no matching entries.\nAnswer from general reasoning only if appropriate, and clearly state that no knowledge-base evidence was found."

    lines = [
        "Knowledge index search results.",
        "Use these as pointers only: call knowledge_read_file with the most relevant file_path before answering.",
        f"Query: {query}",
        "",
    ]
    for idx, result in enumerate(response.results, start=1):
        entry = result.entry
        lines.extend(
            [
                f"[{idx}] {entry.title}",
                f"file_path: {entry.file_path}",
                f"knowledge_scope: {result.scope}",
                f"category: {entry.category}",
            ]
        )
        if entry.source_anchor:
            lines.append(f"source_anchor: {entry.source_anchor}")
        if entry.source_file_path:
            lines.append(f"source_path: {entry.source_file_path}")
        if entry.domain:
            lines.append(f"domain: {entry.domain}")
        if entry.authority:
            lines.append(f"authority: {entry.authority}")
        if entry.document_type:
            lines.append(f"document_type: {entry.document_type}")
        if entry.year:
            lines.append(f"year: {entry.year}")
        if result.matched_queries:
            lines.append(f"matched_queries: {', '.join(result.matched_queries)}")
        if result.score:
            lines.append(f"score: {result.score:.2f}")
        if entry.summary:
            lines.append(f"summary: {_compact(entry.summary)}")
        if entry.proposal_sections:
            lines.append(f"proposal_sections: {', '.join(entry.proposal_sections[:6])}")
        lines.append("")

    lines.append("Final-answer rule: synthesize the relevant read excerpts in natural language and cite file_path/source_anchor; never output raw JSON or full index records.")
    return "\n".join(lines).strip()


@tool("knowledge_read_file", parse_docstring=True)
def knowledge_read_file_tool(
    file_path: str,
    anchor: str | None = None,
    max_chars: int = 12000,
    scope: str = "auto",
) -> str:
    """Read a knowledge-base source file or a specific indexed section.

    Use file_path values from knowledge_search_index results. The
    path must be relative to the knowledge-base root. This tool returns a
    source excerpt for synthesis; summarize and cite it instead of copying the
    tool wrapper text to the user.

    Args:
        file_path: Path relative to the knowledge-base root.
        anchor: Optional heading or section anchor to extract.
        max_chars: Maximum characters to return.
        scope: Source scope from search results: public, private, or auto.
    """
    response = read_knowledge_file_combined(
        KnowledgeFileReadRequest(
            file_path=file_path,
            anchor=anchor,
            max_chars=max(1, min(max_chars, 100000)),
        ),
        user_id=get_effective_user_id(),
        scope=scope,
    )
    parts = [
        "Knowledge source excerpt.",
        f"file_path: {response.file_path}",
        f"knowledge_scope: {response.scope}",
    ]
    if response.anchor:
        parts.append(f"anchor: {response.anchor}")
    if response.truncated:
        parts.append("note: excerpt truncated by max_chars")
    parts.extend(["", "content:", response.content])
    return "\n".join(parts)


@tool("knowledge_search_evidence", parse_docstring=True)
def knowledge_search_evidence_tool(
    query: str,
    applicant_id: str,
    evidence_types: list[str] | None = None,
    verification_statuses: list[str] | None = None,
    limit: int = 10,
) -> str:
    """Search structured image evidence owned by a specific applicant.

    Use this tool for honors, qualifications, patents, software copyrights,
    application proofs, product screenshots, site photos, and other image
    evidence. The applicant id is mandatory to prevent cross-applicant reuse.
    For declaration drafts or Word export, filter to human_verified evidence,
    then call knowledge_read_evidence and reuse its word_image_markdown value.

    Args:
        query: Evidence title, certificate number, issuer, holder, or keyword.
        applicant_id: Applicant owner whose evidence may be used.
        evidence_types: Optional evidence type filters.
        verification_statuses: Optional review states; use human_verified for declaration-ready evidence.
        limit: Maximum evidence cards to return.
    """
    results = search_knowledge_evidence(
        query=query,
        applicant_id=applicant_id,
        evidence_types=evidence_types,
        verification_statuses=verification_statuses,
        limit=max(1, min(limit, 50)),
        user_id=get_effective_user_id(),
    )
    if not results:
        return "No matching image evidence was found for this applicant."
    lines = [
        "Knowledge image evidence results.",
        "Use knowledge_read_evidence before relying on a result. Unreviewed evidence must not be stated as verified fact.",
        "",
    ]
    for index, evidence in enumerate(results, start=1):
        lines.extend(
            [
                f"[{index}] {evidence.title}",
                f"evidence_id: {evidence.evidence_id}",
                f"evidence_type: {evidence.evidence_type}",
                f"verification_status: {evidence.verification_status}",
            ]
        )
        if evidence.holder:
            lines.append(f"holder: {evidence.holder}")
        if evidence.certificate_no:
            lines.append(f"certificate_no: {evidence.certificate_no}")
        if evidence.valid_to:
            lines.append(f"valid_to: {evidence.valid_to}")
        lines.append("")
    return "\n".join(lines).strip()


@tool("knowledge_read_evidence", parse_docstring=True)
def knowledge_read_evidence_tool(evidence_id: str, applicant_id: str) -> str:
    """Read a structured image evidence card after applicant-owner validation.

    Args:
        evidence_id: Evidence id returned by knowledge_search_evidence.
        applicant_id: Applicant owner whose evidence may be used.
    """
    evidence = get_knowledge_evidence(
        evidence_id,
        applicant_id=applicant_id,
        user_id=get_effective_user_id(),
    )
    payload = evidence.model_dump(mode="json", exclude_none=True)
    payload["citation"] = f"【知识库：{evidence.title} | evidence:{evidence.evidence_id}】"
    if evidence.verification_status == "human_verified":
        applicant_path = quote(evidence.applicant_id, safe="-._~")
        image_uri = f"evidence://{applicant_path}/{evidence.evidence_id}"
        image_alt = evidence.title.replace("[", "（").replace("]", "）")
        payload["usage_rule"] = "Declaration-ready"
        payload["word_image_uri"] = image_uri
        payload["word_image_markdown"] = f"![{image_alt}]({image_uri})"
    else:
        payload["usage_rule"] = "Needs human review before factual reuse"
        payload["word_image_export"] = "Unavailable until verification_status is human_verified."
    return _json(payload)


@tool("knowledge_incremental_update", parse_docstring=True)
def knowledge_incremental_update_tool(
    incoming_path: str = "_incoming",
    folder_path: str = "",
    dry_run: bool = False,
    default_category: str = "未分类",
    default_domain: str = "通用",
) -> str:
    """Organize incoming knowledge files and update the root LLM-Wiki index.

    Use this tool when the user asks to update, incrementally update, ingest,
    classify, or rebuild the government project declaration knowledge base.
    It only organizes files from the incoming folder by default, then rebuilds
    index.json from the final source paths.

    Args:
        incoming_path: Folder relative to the knowledge-base root that contains new files.
        folder_path: Folder relative to the knowledge-base root to index after organization.
        dry_run: If true, preview file moves without changing files.
        default_category: Fallback category when no classification rule matches.
        default_domain: Fallback domain when no domain rule matches.
    """
    user_id = get_effective_user_id()
    config = {
        "incoming_path": incoming_path,
        "dry_run": dry_run,
        "default_category": default_category,
        "default_domain": default_domain,
    }
    organization = organize_incoming_files(organize_options_from_config(config), user_id=user_id)
    index_build = build_knowledge_index_from_folder(
        KnowledgeIndexBuildRequest(
            folder_path=folder_path,
            recursive=True,
            replace_existing=True,
            project_types=["科研项目申报"],
            max_files=200,
            incremental=True,
        ),
        user_id=user_id,
    )
    return _json(
        {
            "organization": KnowledgeOrganizeResponse.model_validate(dataclasses.asdict(organization)).model_dump(mode="json"),
            "index_build": index_build.model_dump(mode="json"),
        }
    )
