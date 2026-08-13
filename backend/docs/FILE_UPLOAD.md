# File Uploads

Agent Base exposes thread-scoped upload APIs for browser and channel clients.
Uploaded files are stored under the current runtime home and surfaced to the
agent through stable sandbox virtual paths.

## Endpoints

Upload files:

```http
POST /api/threads/{thread_id}/uploads
Content-Type: multipart/form-data
```

List uploaded files:

```http
GET /api/threads/{thread_id}/uploads/list
```

Delete a file:

```http
DELETE /api/threads/{thread_id}/uploads/{filename}
```

Read an artifact:

```http
GET /api/threads/{thread_id}/artifacts/mnt/user-data/uploads/{filename}
```

## Response Shape

```json
{
  "success": true,
  "files": [
    {
      "filename": "document.pdf",
      "size": 1234567,
      "path": ".agent-base/threads/{thread_id}/user-data/uploads/document.pdf",
      "virtual_path": "/mnt/user-data/uploads/document.pdf",
      "artifact_url": "/api/threads/{thread_id}/artifacts/mnt/user-data/uploads/document.pdf",
      "markdown_file": "document.md",
      "markdown_path": ".agent-base/threads/{thread_id}/user-data/uploads/document.md",
      "markdown_virtual_path": "/mnt/user-data/uploads/document.md",
      "markdown_artifact_url": "/api/threads/{thread_id}/artifacts/mnt/user-data/uploads/document.md"
    }
  ],
  "message": "Successfully uploaded 1 file(s)"
}
```

## Path Contract

- Host path: `.agent-base/threads/{thread_id}/user-data/uploads/...`
- Sandbox path: `/mnt/user-data/uploads/...`
- HTTP artifact URL:
  `/api/threads/{thread_id}/artifacts/mnt/user-data/uploads/...`

When user isolation is enabled, host paths live under:

```text
.agent-base/users/{user_id}/threads/{thread_id}/user-data/uploads/
```

Existing `.deer-flow` runtime homes remain readable when selected through
legacy compatibility settings, but new deployments should use `.agent-base`.

## Limits

Upload limits are controlled by `config.yaml`:

- `uploads.max_files`
- `uploads.max_file_size`
- `uploads.max_total_size`
- `uploads.auto_convert_documents`

Document conversion is disabled by default. Enable it only for trusted
deployments, since Office/PDF parsing happens on the gateway host.

## Agent Prompt Injection

Before each run, uploaded files are summarized for the agent like this:

```xml
<uploaded_files>
The following files have been uploaded and are available for use:

- document.pdf (1.2 MB)
  Path: /mnt/user-data/uploads/document.pdf
</uploaded_files>
```

Agents should use the virtual paths with file tools such as `read_file`.
