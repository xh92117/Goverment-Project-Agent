# Task Tool Improvements

## Overview

The task tool has been improved to eliminate wasteful LLM polling. Previously, when using background tasks, the LLM had to repeatedly call `task_status` to poll for completion, causing unnecessary API requests.

## Changes Made

### 1. Removed `run_in_background` Parameter

The `run_in_background` parameter has been removed from the `task` tool. All subagent tasks now run asynchronously by default, but the tool handles completion automatically.

**Before:**
```python
# LLM had to manage polling
task_id = task(
    subagent_type="bash",
    prompt="Run tests",
    description="Run tests",
    run_in_background=True
)
# Then LLM had to poll repeatedly:
while True:
    status = task_status(task_id)
    if completed:
        break
```

**After:**
```python
# Tool blocks until complete, polling happens in backend
result = task(
    subagent_type="bash",
    prompt="Run tests",
    description="Run tests"
)
# Result is available immediately after the call returns
```

### 2. Backend Polling

The `task_tool` now:
- Starts the subagent task asynchronously
- Polls for completion in the backend (every 2 seconds)
- Blocks the tool call until completion
- Returns the final result directly

This means:
- ✅ LLM makes only ONE tool call
- ✅ No wasteful LLM polling requests
- ✅ Backend handles all status checking
- ✅ Timeout protection (5 minutes max)

### 3. Removed `task_status` from LLM Tools

The `task_status_tool` is no longer exposed to the LLM. It's kept in the codebase for potential internal/debugging use, but the LLM cannot call it.

### 4. Updated Documentation

- Updated `SUBAGENT_SECTION` in `prompt.py` to remove all references to background tasks and polling
- Simplified usage examples
- Made it clear that the tool automatically waits for completion

## Implementation Details

### Polling Logic

Located in `packages/harness/deerflow/tools/builtins/task_tool.py`:

```python
# Start background execution
task_id = executor.execute_async(prompt)

# Poll for task completion in backend
while True:
    result = get_background_task_result(task_id)

    # Check if task completed or failed
    if result.status == SubagentStatus.COMPLETED:
        return f"[Subagent: {subagent_type}]\n\n{result.result}"
    elif result.status == SubagentStatus.FAILED:
        return f"[Subagent: {subagent_type}] Task failed: {result.error}"

    # Wait before next poll
    time.sleep(2)

    # Timeout protection (5 minutes)
    if poll_count > 150:
        return "Task timed out after 5 minutes"
```

### Execution Timeout

In addition to polling timeout, subagent execution now has a built-in timeout mechanism:

**Configuration** (`packages/harness/deerflow/subagents/config.py`):
```python
@dataclass
class SubagentConfig:
    # ...
    timeout_seconds: int = 900  # 15 minutes default
```

**Execution Architecture**:

The scheduler pool has six host workers, matching the supported configuration
ceiling. Before a task changes from `PENDING` to `RUNNING`, a process-wide
capacity gate acquires one of the configured execution slots (four by default).
Actual agent coroutines run on one persistent isolated asyncio loop.

**How it works**:
```python
# In execute_async():
_scheduler_pool.submit(run_task)  # Submit orchestration task

# In run_task():
_process_capacity_gate.acquire(process_limit, cancel_event)
future = _submit_to_isolated_loop_in_context(context, execute_coroutine)
exec_result = future.result(timeout=timeout_seconds)
```

**Benefits**:
- ✅ Per-response and process-wide concurrency are independent
- ✅ No per-task event-loop or execution-pool creation
- ✅ Timeout enforcement at the right level
- ✅ Better resource utilization

**Two-Level Timeout Protection**:
1. **Execution Timeout**: each subagent uses its resolved configurable timeout
2. **Polling Timeout**: polling uses the resolved execution timeout plus a 60-second buffer

This ensures that even if subagent execution hangs, the system won't wait indefinitely.

### Benefits

1. **Reduced API Costs**: No more repeated LLM requests for polling
2. **Simpler UX**: LLM doesn't need to manage polling logic
3. **Better Reliability**: Backend handles all status checking consistently
4. **Timeout Protection**: Two-level timeout prevents infinite waiting (execution + polling)

## Testing

To verify the changes work correctly:

1. Start a subagent task that takes a few seconds
2. Verify the tool call blocks until completion
3. Verify the result is returned directly
4. Verify no `task_status` calls are made

Example test scenario:
```python
# This should block for ~10 seconds then return result
result = task(
    subagent_type="bash",
    prompt="sleep 10 && echo 'Done'",
    description="Test task"
)
# result should contain "Done"
```

## Migration Notes

For users/code that previously used `run_in_background=True`:
- Simply remove the parameter
- Remove any polling logic
- The tool will automatically wait for completion

No other changes needed - the API is backward compatible (minus the removed parameter).
