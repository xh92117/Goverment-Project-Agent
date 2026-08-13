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

- Knowledge retrieval defaults to embedding-free weighted lexical search with query variants and authority/document/year/date filters. Golden retrieval cases also measure forbidden-source contamination.
- Declaration memory is isolated at `users/{user_id}/projects/{project_id}/memory.json`. Runs without `project_id` do not read or update declaration memory. Automatic extraction creates only `workingAssumptions`; it cannot create `confirmedFacts`. Dream-memory distillation is intentionally disabled.
- Government subagents are heterogeneous capability experts. Project/applicant scope is propagated into each task, expert ownership and exclusions are enforced by a shared contract, the writer cannot browse for new facts, and the independent compliance critic is read-only and uses a different configured model.

## Documentation

See `../docs/README_AGENT_BASE.md` and `../docs/AGENT_BASE_CLEANUP_MANIFEST.md` for
the refactor scope and cleanup decisions.
