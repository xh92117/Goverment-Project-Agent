---
name: gov-proposal-web-research
description: Use this skill when doing web research for government research project declarations, especially current or year-specific policy notices, application guides, official announcements, deadlines, eligibility rules, funding amounts, material lists, field extraction, source verification, multi-engine search, site search, PDF search, or when web_search/web_fetch/web_extract should be used with official-source priority.
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
  - ask_clarification
  - write_todos
  - task
---

# Government Project Web Research

## Purpose

Use this skill to turn open-web search into traceable evidence for government
research project declarations. Prefer official and primary sources, keep
search loops bounded, and extract fields from source pages before answering.

For provider selection, engine templates, advanced operators, and time filters, read
`references/multi-search-engine.md` when you need to plan concrete queries.

## Retrieval Workflow

1. Define the evidence target: policy guide, application notice, deadline,
   eligibility, funding amount, material list, scoring rule, template, PDF
   attachment, standard, paper, patent, or current technical fact.
2. Check the knowledge base first when the question depends on local
   declaration materials, templates, historical proposals, applicant
   foundations, or uploaded policy documents.
3. Use `web_search` for current, latest, annual, official, deadline, or
   external evidence. Start with 2-4 focused queries instead of one broad query.
   The default hybrid providers are Serper when configured, DDGS, and
   simple_web fallback.
4. Prefer official-domain queries before general queries. Use `site:` and
   authority names when possible.
5. Fetch only exact URLs returned by `web_search` or directly provided by the
   user. Use `web_fetch` on the best official source before citing it.
6. Use `web_extract` for field-level answers such as deadline, amount,
   eligibility, material list, department, document number, and attachment URL.
7. Stop once enough primary evidence is found. If no official source appears
   within the bounded loop, state what was checked and mark uncertainty.
8. Distinguish partial provider failures from total web-search failure. If
   `web_search` returns results while one provider is skipped, timed out, or
   missing an API key, do not say the web search tool is unavailable; state the
   successful providers and any failed/skipped providers separately.

## Official-Source Priority

Rank evidence in this order:

1. Official ministry, provincial, municipal, department, fund, university, or
   platform pages.
2. Official PDF, DOC, XLS, ZIP, or attachment pages linked from an official
   notice.
3. Standards organizations, journal/patent databases, or recognized technical
   institutions for technical status evidence.
4. Reputable media or industry sources only as supplementary context.
5. SEO pages, reposts, document mirrors, and unverified summaries are fallback
   only and must not be treated as authority.

For Chinese government project work, give higher confidence to domains ending
in `.gov.cn`, government subdomains, official project-management platforms,
competent department websites, NSFC pages, standards and patent authorities,
official university pages under `.edu.cn`, research institute pages under
`.ac.cn`, and official university or research-institute pages when the project
is institution-specific.

## Query Planning

Create complementary queries, not repeated variants of the same wording:

- Official notice: authority + project type + year + notice/guide.
- Field extraction: authority + project type + field name, such as deadline,
  funding, eligibility, materials, or attachment.
- File search: add `filetype:pdf`, `filetype:doc`, `filetype:xls`, or
  `attachment` when guides or templates are likely to be files.
- Site search: add `site:domain` after identifying the competent authority.
- Exact phrase: quote project names, document numbers, or guide titles.
- Exclusion: use `-` to remove recruitment ads, training courses, mirrors, or
  unrelated regions.
- International or technical status: combine English technical terms with
  standard bodies, patents, review papers, or product/industry keywords.

For a complex research-status task, delegate parallel subagents by topic,
region, source type, or technical route, then synthesize. Do not run a long
lead-agent search loop when subagent delegation is available.

## Bounded Search Budgets

Use these default limits unless the user explicitly requests exhaustive search:

- Single current policy lookup: up to 3 `web_search`, 2 `web_fetch`, and
  3 `web_extract` calls.
- Field-level official lookup: up to 2 official-source searches and fetch the
  top official page or attachment.
- Research-status scan: 2-3 subagents, each with a small set of targeted
  searches, then synthesize.
- If all results are reposts or snippets without fetchable official pages,
  report uncertainty instead of continuing indefinitely.

## Evidence Extraction

After fetching a source, extract the fields the answer depends on:

| Field Type | Extract |
| --- | --- |
| Notice | title, authority, publish date, document number, URL |
| Application guide | project type, scope, eligibility, restrictions |
| Schedule | application start, deadline, review date, submission method |
| Funding | amount, ratio, category, indirect cost rule, matching fund rule |
| Materials | required forms, attachments, templates, seals, signatures |
| Compliance | applicant qualification, project limits, previous funding limits |
| Technical status | source type, year, method, result, limitation |

When a field is missing from the fetched source, say it is not found in that
source. Do not infer mandatory rules from snippets.

## Answer Requirements

Separate evidence types when they are mixed:

- `Official evidence`: facts from official fetched pages or attachments.
- `Knowledge-base evidence`: local indexed materials.
- `Supplementary web evidence`: non-official but useful context.
- `Inference`: reasoned synthesis based on evidence.
- `Unverified`: points needing user or manual confirmation.

Include source URLs or knowledge-base citations for factual claims. For policy,
deadline, funding, eligibility, and material-list answers, cite the official
source first. Never paste raw `web_search` JSON as the final answer.
Never summarize a partial provider diagnostic such as `SERPER_API_KEY is not
configured` or `ConnectTimeout` as "网络检索工具不可用" when other providers
returned usable results.
