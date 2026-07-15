---
name: gov-proposal-compliance-review
description: Use this skill when reviewing government research project declaration drafts for guide fit, template completeness, knowledge-base traceability, budget compliance, logic consistency, wording quality, and submission risk.
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
  - knowledge_incremental_update
  - proposal_save_markdown
  - ask_clarification
  - write_todos
  - task
---

# Government Project Compliance Review

## Purpose

This skill guides the agent to review a government research project declaration
draft before submission. It checks whether the draft matches the policy guide,
template requirements, knowledge-base evidence, budget rules, and internal logic.

## Knowledge Retrieval Plan

Use `knowledge_search_index` first to locate guide, template, budget rule,
foundation, team achievement, and historical proposal sources. Use
`knowledge_read_file` to inspect the exact source sections before making
findings. If expected evidence is missing, recommend running
`knowledge_incremental_update` after adding files to `_incoming`.

Retrieve:

1. Matched policy guide and declaration notice.
2. Matched application template and filling instructions.
3. Budget rules and budget template.
4. Research foundation and team achievement sources cited in the draft.
5. Historical successful applications for style and completeness comparison.

## Review Dimensions

Check the draft across these dimensions:

| Dimension | What to Check |
| --- | --- |
| Guide Fit | Direction, eligibility, keywords, expected outcomes, restrictions |
| Template Completeness | Required chapters, tables, attachments, word limits, format |
| Logic Consistency | Title, objectives, tasks, route, outcomes, indicators, budget |
| Evidence Traceability | Whether foundation, achievements, and literature claims have sources |
| Innovation Quality | Whether innovation points are concrete and defensible |
| Feasibility | Whether team, foundation, schedule, and resources support delivery |
| Budget Compliance | Category rules, totals, explanations, task-cost alignment |
| Risk | Missing material, weak basis, sensitive content, unsupported claims |
| Wording | Formality, specificity, repetition, AI-like generic wording |

## Output Structure

Produce a review report with:

1. Overall conclusion.
2. High-priority issues that may affect submission or review.
3. Medium-priority improvement suggestions.
4. Low-priority wording or formatting suggestions.
5. Missing knowledge-base evidence.
6. Budget and compliance risk list.
7. Recommended next actions.

For each issue, use this structure:

| Severity | Evidence | Risk | Actionable Revision | Suggested Wording |
| --- | --- | --- | --- | --- |

Evidence should cite the relevant guide, template, budget rule, source file,
or draft section. Use `【知识库：title | file_path#anchor】` when available.

After producing a reusable review report, call `proposal_save_markdown` with
section_name `合规审查报告` so the Markdown report is saved in the proposal
workspace and visible in the front-end Artifacts panel.

## Severity Definitions

- P0: Blocking issue. The draft may fail formal review or violate requirements.
- P1: Significant issue. It may weaken expert evaluation.
- P2: Improvement issue. It affects clarity, polish, or persuasiveness.

## Quality Checks

Before finalizing, verify:

- Findings cite the relevant guide, template, rule, or draft section.
- Suggestions are actionable, not generic.
- The review separates factual noncompliance from writing preference.
- The report identifies missing evidence instead of inventing it.
- P0/P1/P2 severity is assigned consistently, with P0 reserved for blocking
  formal submission or clear rule violations.
