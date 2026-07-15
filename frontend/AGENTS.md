# Frontend Architecture

## Overview

The frontend is now the government research project declaration workspace. It
keeps the shared LangGraph-compatible chat runtime, artifacts, uploads, memory,
skills, model configuration, and settings, while the visible product surface is
centered on proposal preparation.

## Core Flow

```text
User input
  -> workspace composer
  -> thread hooks and upload handling
  -> LangGraph-compatible Gateway API
  -> streamed messages, tool calls, artifacts, todos, and token usage
  -> workspace message and artifact views
```

## Project Structure

```text
tests/
  e2e/                    # Playwright tests with mocked backend
  e2e-real-backend/       # Playwright tests against a real backend
  e2e-record/             # Record/replay coverage
  unit/                   # Vitest tests mirroring src/ layout
src/
  app/                    # Next.js App Router pages
    api/                  # API proxy routes
    workspace/            # Government declaration workspace routes
    (auth)/               # Optional local-auth login/setup routes
  components/
    ui/                   # Reusable UI primitives
    workspace/            # Workspace-specific components
    ai-elements/          # AI message/composer elements
  core/
    agents/               # Agent API and hooks used by the declaration route
    api/                  # API client and stream mode helpers
    artifacts/            # Artifact loading and previews
    auth/                 # Optional local-auth helpers
    i18n/                 # Locale detection and translations
    mcp/                  # MCP client state
    memory/               # Memory API and hooks
    messages/             # Message normalization and usage helpers
    models/               # Model API and types
    settings/             # Local settings store
    skills/               # Skills API and hooks
    threads/              # Thread API, hooks, export, token usage
    todos/                # Todo state helpers
    uploads/              # Upload validation and prompt-file mapping
    utils/                # Shared utilities
  hooks/                  # Shared React hooks
  lib/                    # Utility modules
  styles/                 # Global styles
```

## Technology Stack

- LangGraph SDK for thread creation, run streaming, and state history.
- TanStack Query for server-state caching.
- React hooks for workspace state and user interactions.
- Shadcn UI, MagicUI, React Bits, and Tailwind CSS for the UI layer.

## Ownership Notes

- `src/app/workspace/agents/government-project-declaration/chats/[thread_id]/page.tsx` owns the proposal-assistant chat flow.
- `src/app/workspace/knowledge/page.tsx` owns LLM-Wiki knowledge-base management.
- `src/app/workspace/proposal-drafts/page.tsx` owns Markdown proposal draft management.
- `src/features/projects/project-workspace-page.tsx` owns the project Word export
  modal, including the default direct-export path and the opt-in intelligent
  image-selection control. `src/features/projects/api.ts` maps that choice to
  the backend `include_images`, `applicant_id`, and `model_name` fields.
- `src/core/threads/hooks.ts` owns pre-submit upload state and thread submission.
- `src/core/api/stream-mode.ts` owns stream mode selection and fallbacks.
- `src/core/auth/*` is optional and should stay gated by local-auth flags.

## Contributing

When adding frontend agent features:

1. Follow the existing `src/core/*` domain boundaries.
2. Add TypeScript types before wiring UI state.
3. Keep optional product-layer flows behind feature flags.
4. Add unit tests under `tests/unit/` and E2E coverage for user workflows.
5. Update this file and `README.md` when routes, ownership, or commands change.

## License

This frontend is part of the Government Project Declaration Agent project.
