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

- Production Compose files use the stable `agent-base` project name and mount `config.yaml` read-write because admin model, knowledge-model, and PDF-parser settings persist selections there. Keep extensions, skills, and proxy templates read-only; ensure the host config file is writable by the deployment user before startup.
- Knowledge retrieval defaults to hybrid SQLite FTS/body search plus an offline feature-vector signal, with query variants and authority/document/year/date filters. A real LangChain-compatible embedding provider can be enabled under `knowledge_retrieval.embedding`; `max_input_chars` bounds provider input without truncating SQLite full-text search, and indexing falls back safely when the provider is unavailable. Golden retrieval cases also measure forbidden-source contamination.
- Text indexing is format-neutral after extraction: every valid document receives a searchable body, unclassified/plain text receives a generic chunk, short sibling blocks may be merged without losing source anchors, and oversized logical sections retain stable group/sequence/previous/next links. Every generated chunk also has document-order previous/next links. Repeated headings and split sections use stable unique file identities so one chunk cannot overwrite another. Local Markdown image references are rewritten to validated `knowledge-file://` URIs.
- Semantic chunking is enabled by default and uses exactly the chat model selected on the knowledge page (`knowledge_model`); the planner never hardcodes a provider or silently chooses the first configured model. It may only group contiguous original-text units, and every invalid response, missing selection, provider failure, or timeout falls back to the existing deterministic chunks without rewriting source text.
- Embedding writes are incremental: unchanged semantic-content fingerprints reuse the existing vector when the configured model signature matches. Build `scale_stats` reports the configured/actual signature, generated and reused counts, and whether the entire index fell back to offline vectors.
- Index rebuilds can run as background jobs through `/api/knowledge/index/build-jobs`. Progress and compact results are persisted below each library's `.index/build_jobs/` directory, while a per-library lock prevents concurrent writers. The executor is process-local; multi-replica deployments should replace it with a shared durable queue before expecting failover across API processes.
- Every build emits a format-neutral quality report covering searchable-body coverage, empty or abnormal chunks, duplicate bodies, duplicate chunk file paths, canonical asset references, chunk-group integrity, and document-order links. Duplicate chunk paths are hard errors because they indicate possible content overwrite. A failed quality threshold completes with warnings so the current compatibility flow remains readable; hard publish blocking requires a future staged/atomic index swap.
- Declaration memory is isolated at `users/{user_id}/projects/{project_id}/memory.json`. Runs without `project_id` do not read or update declaration memory. Automatic extraction creates only `workingAssumptions`; it cannot create `confirmedFacts`. Dream-memory distillation is intentionally disabled.
- Government subagents are heterogeneous capability experts. Project/applicant scope is propagated into each task, expert ownership and exclusions are enforced by a shared contract, the writer cannot browse for new facts, and the independent compliance critic is read-only and uses a different configured model.

## Documentation

See `../docs/README_AGENT_BASE.md` and `../docs/AGENT_BASE_CLEANUP_MANIFEST.md` for
the refactor scope and cleanup decisions.
