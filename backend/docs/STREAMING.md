# Streaming

Agent Base has two streaming paths because the consumers are different:

| Path | Consumer | Transport | Entry point |
| --- | --- | --- | --- |
| Gateway stream | Web and retained IM channels | HTTP/SSE and JSON events | Gateway `/runs/stream` runtime |
| Embedded stream | Python scripts, notebooks, tests | In-process LangGraph stream | `AgentBaseClient.stream()` construction alias over compatibility client |

The `deerflow` package path and `DeerFlowClient` class name are retained for
compatibility. New host applications should import
`agent_base.client.AgentBaseClient`, which lazily constructs the same embedded
client through a neutral Agent Base path.

## Why The Paths Stay Separate

The Gateway path serves browser and channel clients. It must serialize events,
manage HTTP lifecycle details, and use the Gateway-compatible LangGraph API
shape.

The embedded path serves local Python callers. It returns native Python objects
and keeps a synchronous call style for scripts and notebooks. Forcing this path
through HTTP would add a network dependency and change the caller contract.

## Event Mode Notes

The two paths intentionally use different stream-mode shapes at different
protocol layers:

- Gateway/channel workers use the HTTP SDK-compatible message tuple mode.
- The embedded compatibility client calls the graph directly and subscribes to
  native graph modes such as values, custom events, and message deltas.

Do not collapse these mode strings into a single shared constant. They describe
different protocol boundaries even when they carry related content.

## Delta Handling

Gateway consumers are responsible for accumulating message deltas in the
frontend or channel adapter.

The embedded compatibility client keeps its own accumulator for `chat()` so a
caller can use a simple request/response helper while `stream()` still exposes
incremental events.

## Compatibility Rules

- Keep `AgentBaseClient.stream()` and compatibility `DeerFlowClient.stream()`
  behavior aligned.
- Keep Gateway event payloads stable for the Web, DingTalk, WeChat, WeCom, and
  Feishu channels.
- Add new stream events in an additive way. Existing consumers should be able to
  ignore unknown event types.
- Test Gateway and embedded streaming separately because one path passing does
  not prove the other path is wired correctly.

## Key Files

| Area | File |
| --- | --- |
| Gateway run worker | `backend/app/runtime/runs/worker.py` |
| Channel dispatch | `backend/app/channels/manager.py` |
| Neutral embedded client alias | `backend/packages/harness/agent_base/client.py` |
| Embedded compatibility implementation | `backend/packages/harness/deerflow/client.py` |
| Frontend stream handling | `frontend/src/core/api` and workspace stream hooks |
