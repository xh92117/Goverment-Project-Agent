# CLAUDE.md

This file provides guidance to Claude Code when working with the government
research project declaration frontend.

## Project Overview

The frontend is a Next.js 16 workspace for a LangGraph-compatible government
project declaration agent. It provides thread-based proposal-assistant
conversations, LLM-Wiki knowledge-base access, Markdown draft management,
streaming responses, artifacts, uploads, memory, model selection, skills, and
settings.

**Stack**: Next.js 16, React 19, TypeScript 5.8, Tailwind CSS 4, pnpm 10.26.2

## Commands

| Command          | Purpose                                           |
| ---------------- | ------------------------------------------------- |
| `pnpm dev`       | Dev server with Turbopack (http://localhost:3000) |
| `pnpm build`     | Production build                                  |
| `pnpm check`     | Lint + type check                                 |
| `pnpm lint`      | ESLint only                                       |
| `pnpm lint:fix`  | ESLint with auto-fix                              |
| `pnpm test`      | Run unit tests with Vitest                        |
| `pnpm test:e2e`  | Run E2E tests with Playwright                     |
| `pnpm typecheck` | TypeScript type check (`tsc --noEmit`)            |
| `pnpm start`     | Start production server                           |

Unit tests live under `tests/unit/` and mirror the `src/` layout. E2E tests live
under `tests/e2e/`; real-backend coverage lives under `tests/e2e-real-backend/`.

## Architecture

```text
Workspace UI
  -> core thread/upload hooks
  -> LangGraph-compatible Gateway API
  -> streamed messages, tool calls, artifacts, todos, and token usage
```

The frontend is a stateful workspace application. Users create proposal
assistant threads, consult the knowledge base, manage Markdown proposal drafts,
inspect artifacts, manage skills and models, and adjust local settings. Optional
local-auth screens are present but disabled by default.

## Source Layout

- `app/`: Next.js App Router pages. Main routes are `/workspace`,
  `/workspace/agents/government-project-declaration/chats/[thread_id]`,
  `/workspace/knowledge`, `/workspace/proposal-drafts`, and
  `/workspace/settings`.
- `app/(auth)/`: Optional login/setup routes gated by local-auth configuration.
- `components/ui/`: Reusable UI primitives.
- `components/ai-elements/`: AI message and composer elements.
- `components/workspace/`: Workspace-specific components.
- `core/`: Domain logic for threads, agents, API clients, artifacts, i18n,
  settings, memory, skills, uploads, MCP, models, messages, and todos.
- `hooks/`: Shared React hooks.
- `lib/`: Shared utilities such as `cn()`.
- `styles/`: Global CSS with Tailwind v4 imports and theme variables.

## Data Flow

1. User input reaches thread hooks in `core/threads/hooks.ts`.
2. Upload state and run context are normalized before submission.
3. LangGraph stream events update messages, artifacts, todos, and usage.
4. TanStack Query manages server state; localStorage stores user settings.
5. Workspace components subscribe to the normalized state and render updates.

The knowledge upload flow also accepts image evidence. Image responses carry
optional `asset_id` and `evidence_id` fields, immediately appear as
`entry_type=evidence` cards in the existing knowledge tree, and use the
evidence-specific delete endpoint so originals, thumbnails, registry records,
and index pointers are removed together. Non-image upload behavior is
unchanged.

The knowledge page intentionally has no applicant-identifier field and no
dedicated image preview/review section. Images share the normal upload control
and display “已加入图片识别队列”. Recognition runs only when the user builds
the index. Capability/provider failures arrive in `index_build.warnings` and
must remain visible in the existing upload card; do not add a separate image
workspace for these warnings.

The knowledge-page header owns the persistent image-model status entry. It
opens a top-layer accessible dialog backed by
`GET/PUT /api/settings/knowledge-image-model`; render only the vision-capable
choices returned by that API. A valid selection shows its concrete model name
with a green status dot; otherwise show `图片识别模型未配置`. Keep the header
entry as a compact, single-line pill and ensure status modifier classes remain
separate CSS tokens so its grid layout is actually applied. The same dialog
also reuses the settings provider options and model form to POST a new model
with `supports_vision=true`, then selects it through the dedicated setting API.
A build warning for missing vision capability opens the same dialog, but must
not block normal document indexing. Keep this entry in the header instead of
restoring applicant or image-preview panels.

The existing knowledge-tree toolbar conditionally exposes batch evidence review
actions, without restoring the removed image preview section. Only visible
`needs_review` evidence whose index metadata has `extraction_status=completed`
is eligible. Normal evidence can be batch-confirmed; `non_evidence_image`
entries require a separate explicit “标记无关图片” action. Always show updated
and skipped counts returned by the batch API.

## Code Style

- Use the existing `src/core/*` domain boundaries.
- Use `@/*` for imports from `src/*`.
- Prefix intentionally unused variables with `_`.
- Use `cn()` from `@/lib/utils` for conditional Tailwind classes.
- Treat `components/ui/` and `components/ai-elements/` as registry-generated
  surfaces unless a local customization is already established.

## Environment

Backend API URLs are optional in the standard `make dev` and Docker flows,
where nginx serves `/api/langgraph/*` and rewrites it to Gateway APIs.

```bash
NEXT_PUBLIC_BACKEND_BASE_URL=http://localhost:8001
NEXT_PUBLIC_LANGGRAPH_BASE_URL=http://localhost:8001/api
NEXT_PUBLIC_ENABLE_LOCAL_AUTH=false
```

Requires Node.js 22+ and pnpm 10.26.2+.
