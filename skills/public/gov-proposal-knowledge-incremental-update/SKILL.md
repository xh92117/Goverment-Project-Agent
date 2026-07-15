---
name: gov-proposal-knowledge-incremental-update
description: Use this skill when the user asks to one-click update, incrementally update, organize, classify, ingest, or rebuild the LLM-Wiki knowledge-base index for the government project declaration agent.
allowed-tools:
  - ls
  - read_file
  - glob
  - grep
  - web_search
  - web_fetch
  - web_extract
  - knowledge_search_index
  - knowledge_read_file
  - knowledge_incremental_update
  - ask_clarification
  - write_todos
  - task
---

# Government Project Knowledge Incremental Update

## Purpose

This skill lets the declaration agent organize newly added knowledge-base files
and update the LLM-Wiki index in one action. It is designed for a front-end
button or a user command such as "更新知识库", "增量更新知识库", or "建立索引".

The front-end button should preferably call the backend incremental-update API
first, then send the structured result to the agent for summary and follow-up
analysis. If the user asks the agent directly, the agent can run the same flow
through the API or the script below.

## Scope

Use the configured government-project workspace as the source of truth. The
knowledge-base root is the configured `AGENT_BASE_KNOWLEDGE_ROOT` value when it
is set; otherwise it is `knowledge_base` under the configured project
workspace. New files should be placed in `_incoming` under that knowledge-base
root. The final index file is `index.json` under the same root.

The knowledge-base root must be outside the source-code directory. Do not
create, classify, move, index, or log runtime knowledge files under the code
repository. If the effective root is inside the source-code directory, stop and
report the path isolation violation.

Only organize files inside `_incoming`. Do not reorganize existing official
folders unless the user explicitly asks for a wider maintenance operation.

## Execution Plan

1. Confirm the effective knowledge-base root and incoming folder from runtime
   configuration or tool output; do not hardcode local absolute paths.
2. Prefer the backend incremental-update API when it is available.
3. Use the one-click PowerShell script as a local fallback from the project
   root.
4. Let the organizer classify and move incoming files into official folders.
5. Let the index builder update `index.json` from the final file paths.
6. Report the result in Chinese, including moved, skipped, created, updated,
   and skipped index counts.

Fallback command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-knowledge-index.ps1 -ConfigPath .\configs\knowledge-index-build.example.json
```

Run it from the project root:

```text
D:\program flies\智能体开发\Government Project Declaration Agent
```

## API Alternative

If using the backend API is more natural for the current runtime, call:

```http
POST /api/knowledge/index/incremental-update
```

Recommended JSON body:

```json
{
  "organize_incoming": true,
  "incoming_path": "_incoming",
  "folder_path": "",
  "recursive": true,
  "replace_existing": true,
  "incremental": true,
  "dry_run": false,
  "default_category": "未分类",
  "default_domain": "通用",
  "project_types": ["科研项目申报"]
}
```

## Windows PowerShell Chinese Safety

Do not pass Chinese category, domain, or folder names directly as command-line
arguments. Use `configs/knowledge-index-build.example.json`, because it is read
as UTF-8 and avoids Chinese text being corrupted into `????`.

Do not pipe inline JSON containing Chinese through PowerShell. If a custom rule
is needed, edit or create a UTF-8 JSON config file first, then run the wrapper.

## Classification Rules

The default config classifies incoming files into folders such as:

- `申报书模板`
- `历史申报书`
- `国内外研究现状`
- `已有研究基础`
- `团队成果`
- `政策指南`
- `技术路线`
- `创新点`
- `预算依据`
- `未分类`

It also infers domains such as `路基工程`, `智能制造`, `人工智能`, or the
fallback `通用`.

## Output Requirements

After the update, tell the user:

- Where new files were read from.
- Which files were moved and their target paths.
- How many index entries were created, updated, and skipped.
- Whether `index.json` was updated successfully.
- Any unsupported files that were skipped.
- A short quality check: whether guide/template/budget/history/foundation
  categories are represented, and which categories still need source files.

If there are no files in `_incoming`, say so clearly and still report whether
the existing index was refreshed.

## Failure Handling

- If the incoming folder does not exist, explain that the user can create an
  `_incoming` folder under the configured knowledge-base root and place new
  files there.
- If PDF parsing fails because MinerU is not configured, ask the user to set
  `MINERU_API_TOKEN` as an environment variable. Never ask the user to paste the
  token into source files.
- If the script fails, summarize the important error lines and suggest the
  smallest next action.
