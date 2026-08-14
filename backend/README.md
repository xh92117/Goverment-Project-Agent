# Agent Base Backend

The backend contains the Agent Base gateway and harness runtime. It provides:

- LangGraph-compatible HTTP routes for web and retained IM channels.
- The default orchestrator with upstream subagent delegation strategy.
- Sandbox-backed file/workspace execution.
- Memory, skills, MCP, guardrails, tracing, and persistence hooks.
- Optional local auth, disabled by default for a neutral base runtime.

## Run Locally

From the repository root:

```bash
make setup
make doctor
make dev
```

The runtime state directory defaults to `.agent-base`. Prefer
`AGENT_BASE_HOME` and `AGENT_BASE_PROJECT_ROOT` for overrides. Legacy
`DEER_FLOW_*` variables are still accepted for migration compatibility.

## Configuration

Use the root `config.example.yaml` for the complete template, or start from the
split examples in `configs/`:

- `configs/base.example.yaml`
- `configs/subagents.example.yaml`
- `configs/tools.example.yaml`
- `configs/mcp.example.yaml`
- `configs/full.example.yaml`

## Optional Features

Channel SDKs are not part of the minimal core install. Install retained IM
channel support only when needed:

```bash
uv sync --extra channels
```

Built-in local auth remains available but is opt-in:

```bash
GATEWAY_ENABLE_LOCAL_AUTH=true
NEXT_PUBLIC_ENABLE_LOCAL_AUTH=true
```

## Government Project Runtime

- Production Compose files use the stable `agent-base` project name and mount `config.yaml` read-write because admin model, knowledge-model, and PDF-parser settings persist selections there. Dedicated Linux servers use `/srv/agent-base/data` for runtime state and `/srv/agent-base/public-knowledge` for public knowledge on both the host and Gateway side; public knowledge must never resolve below the protected `/app` source tree. Run server lifecycle and log operations through `scripts/server-compose.sh` (or `make server-*`) so paths and persisted auth secrets do not depend on one shell session. Keep extensions, skills, and proxy templates read-only; ensure the host config file is writable by the deployment user before startup.
- Conversation DOCX export accepts optional `word_format` settings for body font and size, line spacing, heading font, and heading start level, using the same validated renderer options as project-file export.
- Knowledge retrieval defaults to hybrid SQLite FTS/body search plus an offline feature-vector signal, with query variants and authority/document/year/date filters. A real LangChain-compatible embedding provider can be enabled under `knowledge_retrieval.embedding`; `max_input_chars` bounds provider input without truncating SQLite full-text search, and indexing falls back safely when the provider is unavailable. Golden retrieval cases also measure forbidden-source contamination.
- Text indexing is format-neutral after extraction: every valid document receives a searchable body, unclassified/plain text receives a generic chunk, and a final publishing pass merges undersized compatible leaf blocks and parent summaries without losing source anchors. Meaningful indivisible sections such as goals, conclusions, eligibility conditions, and references may remain short with `atomic_short=true`. Oversized logical sections retain stable group/sequence/previous/next links, and every generated chunk also has document-order previous/next links. Repeated headings and split sections use stable unique file identities so one chunk cannot overwrite another. Local Markdown image references are rewritten to validated `knowledge-file://` URIs.
- Semantic chunking is enabled by default and uses exactly the chat model selected on the knowledge page (`knowledge_model`); the planner never hardcodes a provider or silently chooses the first configured model. Numbered MinerU headings are normalized before candidate generation, and original adjacent heading boundaries reach the model before any deterministic short-block merge. The model may group only contiguous original-text units. Complete sections shorter than the normal minimum may be classified intact, while incomplete undersized ranges and all oversized, discontinuous, or incomplete plans remain invalid. Failed spans restore deterministic merging before the final publishing pass.
- Incoming-file organization scores filename/path identity, Markdown headings, and body evidence separately instead of accepting the first weak keyword hit. Specific phrases outweigh generic words such as “standard”, “result”, or “detection”. Dimensions that remain at an unresolved default are reviewed by the selected `knowledge_model` against the configured category/domain allow lists; confident rule dimensions cannot be overwritten, and invalid, low-confidence, or failed model classifications retain the rule result. Per-file organization results expose both dimension strategies and model/confidence/reason/warning metadata.
- Embedding writes are incremental: unchanged semantic-content fingerprints reuse the existing vector when the configured model signature matches. Build `scale_stats` reports the configured/actual signature, generated and reused counts, and whether the entire index fell back to offline vectors.
- Index rebuilds run as background jobs through `/api/knowledge/index/build-jobs`; the complete incoming-file organization plus rebuild flow uses `/api/knowledge/index/process-incoming-jobs`. Both return `202` immediately and persist stage, counts, percentage, organization summary, and compact results below each library's `.index/build_jobs/` directory, allowing clients to recover progress after a page refresh. A per-library lock prevents concurrent writers. The executor is process-local; multi-replica deployments should replace it with a shared durable queue before expecting failover across API processes or server restarts.
- Every build emits a format-neutral quality report covering searchable-body coverage, empty or abnormal chunks, duplicate bodies, duplicate chunk file paths, canonical asset references, chunk-group integrity, and document-order links. Defaults treat non-atomic leaf chunks below 500 characters as short, below 120 as critical when a source has multiple chunks, and report when short chunks exceed 5%. Duplicate chunk paths remain hard errors because they indicate possible content overwrite. A failed quality threshold completes with warnings so the current compatibility flow remains readable; hard publish blocking requires a future staged/atomic index swap.
- Declaration memory is isolated at `users/{user_id}/projects/{project_id}/memory.json`. Runs without `project_id` do not read or update declaration memory. Automatic extraction creates only `workingAssumptions`; it cannot create `confirmedFacts`. Dream-memory distillation is intentionally disabled.
- Government subagents are heterogeneous capability experts. Project/applicant scope is propagated into each task, expert ownership and exclusions are enforced by a shared contract, the writer cannot browse for new facts, and the independent compliance critic is read-only and uses a different configured model.

## Documentation

See `../docs/README_AGENT_BASE.md` and `../docs/AGENT_BASE_CLEANUP_MANIFEST.md` for
the refactor scope and cleanup decisions.
