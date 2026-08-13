# Path Examples

Agent Base exposes three path forms for thread files.

## Host Path

Used by backend code and operational scripts:

```text
.agent-base/threads/{thread_id}/user-data/uploads/document.pdf
```

With user isolation:

```text
.agent-base/users/{user_id}/threads/{thread_id}/user-data/uploads/document.pdf
```

## Sandbox Virtual Path

Used by agents and file tools:

```text
/mnt/user-data/uploads/document.pdf
```

## HTTP Artifact URL

Used by frontend and API clients:

```text
/api/threads/{thread_id}/artifacts/mnt/user-data/uploads/document.pdf
```

## Compatibility

Existing `.deer-flow` directories remain supported when selected through
legacy environment variables or when the compatibility resolver falls back to
an existing old runtime home. New deployments should write `.agent-base`.
