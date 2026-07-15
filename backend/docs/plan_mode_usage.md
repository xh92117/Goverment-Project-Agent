# Plan Mode Usage

Plan mode is an optional Agent Base capability that adds a TodoList middleware
to help the lead agent break complex requests into tracked steps.

## When To Enable It

Enable plan mode when the host application needs visible progress tracking for
long-running work, multi-step tool use, or human review checkpoints. Leave it
disabled for simple chat flows or tightly scripted automations.

## Configuration

Plan mode is controlled from `config.yaml`:

```yaml
plan_mode:
  enabled: true
```

When enabled, the lead-agent factory adds LangChain's `TodoListMiddleware`
with Agent Base prompt text that matches the default orchestration style.

## Runtime Behavior

- The middleware can create and update task lists during an agent run.
- Todo state is part of the graph state and is persisted by the configured
  checkpointer.
- The default subagent strategy is unchanged: the lead agent can still delegate
  through the `task` tool to the built-in `general-purpose` and `bash`
  subagents when those capabilities are available.
- Plan mode is advisory. It improves traceability, but it does not replace
  sandbox checks, guardrails, or Gateway authorization.

## Implementation Notes

The integration is created in the lead-agent factory under
`packages/harness/deerflow/agents/lead_agent/agent.py`. The package path still
uses `deerflow` for compatibility; new applications should prefer the
`agent_base` facade when embedding the runtime.

## Validation

For local development, verify plan mode with a request that naturally needs
multiple steps, then inspect the stream for todo-list events and final task
state. Keep tests focused on middleware registration and graph-state
persistence rather than exact model wording.
