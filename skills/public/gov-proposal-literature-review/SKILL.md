---
name: gov-proposal-literature-review
description: Use this skill when writing literature reviews, domestic and international research status, technology trend analysis, research gaps, or existing technology foundations for government research project declarations using a knowledge base.
allowed-tools:
  - ls
  - read_file
  - glob
  - grep
  - web_search
  - web_fetch
  - web_extract
  - knowledge_search_index
  - knowledge_read_file
  - knowledge_search_evidence
  - knowledge_read_evidence
  - knowledge_list_images
  - knowledge_incremental_update
  - proposal_save_markdown
  - present_files
  - view_image
  - ask_clarification
  - write_todos
  - task
  - update_agent
---

# Government Project Literature Review

## Purpose

This skill guides the agent to write declaration-oriented literature reviews.
The goal is not to produce an academic survey for its own sake, but to support
why the proposed project is necessary, feasible, and innovative.

## Knowledge Retrieval Plan

Use the LLM-Wiki index layer first. Do not directly scan all source files.

1. Call `knowledge_search_index` with the topic keywords plus the target
   chapter "国内外研究现状" or "literature review".
2. Filter index entries by category, applicable chapter, domain, and project
   type when those fields are known.
3. Call `knowledge_read_file` only for the source files and headings named by
   the best index entries.
4. Use the retrieved source sections as writing references.
5. If the index does not contain a suitable entry, report the missing index and
   suggest adding files to `_incoming` and running `knowledge_incremental_update`.

Retrieve and separate the following source types through index entries:

1. Papers, patents, standards, and technical reports from the literature
   knowledge base.
2. Existing research foundation and prior achievements from the applicant.
3. Historical applications with similar background or research status sections.
4. Policy guides that explain strategic demand or industry needs.
5. Known domestic and international technology routes.

When external web search is used, cite every claim that depends on external
information. Prefer indexed knowledge-base documents when available.

## Recommended Section Structure

Write the review in this order:

1. Research background and practical demand.
2. International research status.
3. Domestic research status.
4. Existing technology foundation and representative achievements.
5. Main limitations of current research or technology.
6. Research gap and project entry point.
7. Relationship between the proposed project and the applicant's foundation.
8. References or source list.

## Writing Rules

- Write for a project declaration reviewer, not for a journal reviewer.
- Connect literature findings to the proposed project direction.
- Summarize trends and gaps instead of listing papers mechanically.
- Distinguish "what is known", "what is insufficient", and "what this project
  will solve".
- Use cautious wording for claims that are inferred from sources.
- Preserve source traceability for important claims.
- Record which index entry, file path, and heading were used.
- Do not describe the applicant's internal research foundation as external
  domestic or international research status. Keep applicant foundation in a
  separate subsection.

## Output Requirements

Each generated review should include:

- A concise summary paragraph.
- Domestic and international status subsections.
- A gap analysis subsection.
- A "project necessity" transition paragraph.
- A source table or citation list with document title, source type, year, and
  knowledge-base identifier when available.
- Knowledge-base citations in the form `【知识库：title | file_path#anchor】`
  for major claims.
- Web citations for current external facts if web search was used.

After generating a review draft, call `proposal_save_markdown` with
section_name `国内外研究现状` so the Markdown draft is saved in the proposal
workspace and displayed in the front-end Artifacts panel.

## Quality Checks

Before finalizing, verify:

- The review supports the selected topic and project title.
- Domestic and international content is balanced where possible.
- The project gap is specific enough to justify research tasks.
- Applicant research foundation is not mixed up with external literature.
- Claims based on external facts have citations or source references.
- Each main paragraph is traceable to either retrieved evidence or an explicit
  inference.
