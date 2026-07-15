---
name: gov-proposal-topic-planning
description: Use this skill when planning government research project topics, evaluating project directions, drafting project titles, or matching a proposed topic to policy guides, historical applications, research foundations, and team achievements from a knowledge base.
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

# Government Project Topic Planning

## Purpose

This skill helps the agent determine research directions and draft project
titles for government research project declarations. It assumes the primary
materials are already stored in a knowledge base, including application
templates, policy guides, historical applications, research foundations, and
team achievements.

## Required Inputs

Before drafting topic suggestions, identify or ask for:

- Project type, level, year, and competent authority.
- Target technical domain or strategic direction.
- Applicant organization or research team.
- Known constraints from the relevant guide.
- Whether the user wants exploratory directions or a focused title.

## Knowledge Retrieval Plan

Use the built-in knowledge-base tools instead of scanning folders manually:

1. Call `knowledge_search_index` with policy, template, historical proposal,
   research foundation, and team achievement keywords.
2. For useful hits, call `knowledge_read_file` with the returned `file_path`
   and relevant section anchor.
3. If the index appears stale or missing, suggest running
   `knowledge_incremental_update` after the user places files in `_incoming`.

Retrieve knowledge in this order:

1. Policy guides and declaration notices for the target project type.
2. Application templates and scoring/filling instructions.
3. Historical applications in the same project type or domain.
4. Existing research foundation of the applicant organization.
5. Team achievements, papers, patents, standards, awards, and prior projects.
6. Similar funded projects or known topic patterns, if available.

Prefer knowledge-base sources over ad hoc user-provided text. Realtime uploads
are supplementary only when the relevant material has not yet been ingested.

## Output Structure

When proposing directions, produce:

| Field | Description |
| --- | --- |
| Direction | Candidate research direction |
| Suggested Title | One concise project title |
| Policy Fit | Why it matches the guide or policy theme |
| Foundation Fit | Which existing research basis or team achievement supports it |
| Innovation Potential | Possible technical or application innovation |
| Feasibility | Whether the team can realistically execute it |
| Risk | Competitive, policy, data, budget, or implementation risk |
| Recommendation | Strongly recommend, recommend, reserve, or not recommended |

Also include a scoring matrix with 1-5 scores for policy fit, foundation fit,
innovation potential, feasibility, budget match, and competition risk. Explain
the top recommendation in one concise paragraph.

After producing a reusable topic-planning result, call
`proposal_save_markdown` with section_name `课题规划` so the draft is saved
under the proposal workspace and visible in the front-end Artifacts panel.

## Title Drafting Rules

- Keep titles specific, technical, and declaration-oriented.
- Avoid empty phrases such as "research on key technologies" unless followed
  by a concrete object, method, and scenario.
- Prefer this structure when suitable:
  "Research and demonstration of [key technology/method] for [application
  scenario/problem]".
- Generate multiple title styles when helpful:
  - Basic research type.
  - Applied research type.
  - Demonstration project type.
  - Soft science or policy research type.

## Quality Checks

Before finalizing, check:

- The direction is supported by knowledge-base materials.
- The title is not too broad.
- The title reflects the applicant's existing foundation.
- The direction can be expanded into research content, technical route,
  expected outcomes, and budget.
- The output clearly separates evidence from inference.
- Knowledge-base evidence is cited as `【知识库：title | file_path#anchor】`
  when title, path, and anchor are available.
- Current or year-specific policy claims are backed by official web sources
  when the knowledge base is not sufficient.
