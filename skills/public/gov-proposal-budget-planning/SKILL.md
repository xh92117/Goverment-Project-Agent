---
name: gov-proposal-budget-planning
description: Use this skill when preparing project budgets, budget tables, budget explanations, fund allocation logic, cost estimates, or budget compliance checks for government research project declarations.
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

# Government Project Budget Planning

## Purpose

This skill guides budget drafting and review for government research project
declarations. It relies on the budget rules knowledge base, project templates,
historical budgets, and the generated research task plan.

## Knowledge Retrieval Plan

Use `knowledge_search_index` first, then `knowledge_read_file` for the matched
budget rules, budget templates, and historical budget examples. If the budget
knowledge base is stale, ask the user to add materials to `_incoming` and run
`knowledge_incremental_update`.

Retrieve:

1. Budget management rules for the target project type and year.
2. Budget template and required budget categories.
3. Historical budgets for similar projects.
4. Research tasks, implementation plan, expected outcomes, and schedule.
5. Team and collaboration structure, if personnel or outsourcing costs are
   involved.

## Common Budget Categories

Adapt categories to the matched template. Common categories include:

- Equipment cost.
- Material cost.
- Testing, assay, processing, or computing service cost.
- Fuel and power cost.
- Travel, conference, and international cooperation cost.
- Publication, documentation, information, and intellectual property cost.
- Labor cost.
- Expert consultation cost.
- Outsourced or cooperative research cost.
- Indirect cost or management cost.
- Other costs allowed by the guide.

## Output Structure

Produce:

1. Budget summary table.
2. Budget by research task or work package.
3. Budget explanation for each category.
4. Measurement basis and assumptions.
5. Compliance checks against budget rules.
6. Risk notes and adjustment suggestions.
7. Formula/check table showing category totals, overall total, and any ratio
   limits from retrieved rules.

After producing a reusable budget draft, call `proposal_save_markdown` with
section_name `预算编制` so the Markdown budget explanation is saved in the
proposal workspace and visible in the front-end Artifacts panel.

## Budget Explanation Rules

- Every cost should map to a research task or deliverable.
- Avoid vague explanations such as "for project implementation".
- Use measurable bases where possible, such as quantity, unit price, duration,
  number of people, number of tests, or number of meetings.
- If rules are unavailable, clearly state assumptions and mark them for manual
  review.
- Never invent a mandatory rule. Distinguish retrieved rules from inferred
  planning assumptions.
- Cite budget rules, templates, and historical budget examples as
  `【知识库：title | file_path#anchor】` when available.

## Quality Checks

Before finalizing, verify:

- Category totals equal the overall budget.
- Costs are consistent with the implementation plan.
- Restricted categories comply with the relevant rule set.
- Large costs have enough justification.
- Budget wording is suitable for a formal declaration document.
- The sum of task budgets equals the sum of category budgets and the stated
  total budget.
- Unknown or missing rules are explicitly marked for manual review instead of
  being inferred as mandatory policy.
