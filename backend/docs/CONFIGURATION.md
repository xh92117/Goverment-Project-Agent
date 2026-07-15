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
