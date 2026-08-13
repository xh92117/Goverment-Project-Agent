# Agent Base Configuration

The main configuration file is `config.yaml` in the project root. Start from
`config.example.yaml` or the split examples under `configs/`.

## Core Sections

- `models`: available LLM providers.
- `sandbox`: local or container-backed execution provider.
- `tools` and `tool_groups`: runtime tools exposed to the agent.
- `subagents`: subagent runtime controls.
- `memory`: memory storage and injection settings.
- `extensions`: MCP servers and skills state.
- `database`: persistence backend for runtime metadata.
- `channels`: retained IM channel integrations.

## Runtime Paths

New deployments should use:

```bash
AGENT_BASE_PROJECT_ROOT=/path/to/project
AGENT_BASE_HOME=/path/to/project/.agent-base
AGENT_BASE_CONFIG_PATH=/path/to/project/config.yaml
AGENT_BASE_EXTENSIONS_CONFIG_PATH=/path/to/project/extensions_config.json
AGENT_BASE_SKILLS_PATH=/path/to/project/skills
AGENT_BASE_DB_PATH=/path/to/project/.agent-base/agent_base.db
AGENT_BASE_HOST_BASE_DIR=/path/to/project/.agent-base
AGENT_BASE_HOST_SKILLS_PATH=/path/to/project/skills
AGENT_BASE_DOCKER_SOCKET=/var/run/docker.sock
```

Existing `.deer-flow` directories and `DEER_FLOW_*` variables are still read as
legacy compatibility inputs.

Set the same `AGENT_BASE_HOME`/`AGENT_BASE_HOST_BASE_DIR` values for the launcher,
direct Uvicorn commands, tests, and maintenance scripts. Otherwise a source-tree
`.agent-base` can silently shadow the external runtime directory.

## Subagents and Execution Modes

`subagents.enabled` is the global authorization switch. A run may disable
delegation, but neither a client nor the `deep` execution mode can enable it when
the global switch is false. Unknown fields in the root, per-agent override, and
custom-agent subagent schemas are rejected.

`execution_modes.<mode>.recursion_limit` and
`execution_modes.<mode>.max_concurrent_subagents` are server-enforced run limits.
The latter limits `task` calls in one lead-agent response. The independent
`subagents.max_process_concurrent_subagents` value limits executing subagents
across all users and runs in one process. `subagents.tool_call_limits` applies
hard per-delegated-task tool budgets; loop detection remains active for other
repetitive patterns.

## Sandbox

`allow_host_bash` is `false` by default. Prefer a container sandbox for any
workflow that needs shell execution. The default sandbox container prefix is
`agent-base-sandbox`.

## Channels

The base retains Web, DingTalk, WeChat, WeCom, and Feishu channel surfaces.
Install channel dependencies only when needed:

```bash
uv sync --extra channels
```

## Auth

Local username/password auth is optional:

```bash
GATEWAY_ENABLE_LOCAL_AUTH=true
NEXT_PUBLIC_ENABLE_LOCAL_AUTH=true
```

When disabled, the gateway runs with the neutral anonymous base user context.
