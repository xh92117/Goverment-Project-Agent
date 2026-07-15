# Agent Base Setup

Agent Base uses `config.yaml` in the project root and writes runtime state to
`.agent-base` by default.

## Quick Setup

From the repository root:

```bash
make setup
make doctor
make dev
```

`make setup` launches the interactive wizard and writes `config.yaml`, `.env`,
and `frontend/.env` when needed.

## Manual Setup

Copy the examples and edit them:

```bash
cp config.example.yaml config.yaml
cp .env.example .env
cp frontend/.env.example frontend/.env
```

At minimum, configure one model under `models`.

## Runtime Paths

Preferred variables:

- `AGENT_BASE_PROJECT_ROOT`: project root for relative runtime paths.
- `AGENT_BASE_HOME`: runtime state directory.
- `AGENT_BASE_HOST_BASE_DIR`: host-side path for sandbox volume mounts.

Legacy `DEER_FLOW_*` variables remain supported for migration compatibility.

## Docker

Use:

```bash
make docker-start
```

Docker defaults use `agent-base` compose project/network/container names and
`.agent-base` runtime storage.
