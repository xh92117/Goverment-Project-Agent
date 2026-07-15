# Government Project Declaration Agent Frontend

The frontend is a Next.js workspace for the government research project
declaration agent. It focuses on proposal preparation workflows: topic planning,
knowledge-base assisted writing, proposal draft management, model configuration,
artifacts, memory, uploads, and settings.

## Tech Stack

- **Framework**: Next.js 16 with App Router
- **UI**: React 19, Tailwind CSS 4, Shadcn UI, MagicUI, and React Bits
- **AI Integration**: LangGraph SDK and Vercel AI Elements
- **State**: TanStack Query and React hooks

## Quick Start

### Prerequisites

- Node.js 22+
- pnpm 10.26.2+

### Installation

```bash
pnpm install
```

### Development

```bash
pnpm dev
```

The project-level startup script serves the frontend at
`http://127.0.0.1:9527`.

### Build And Test

```bash
pnpm typecheck
pnpm lint
pnpm test
pnpm build
```

For E2E tests, install the browser once, then run Playwright:

```bash
pnpm exec playwright install chromium
pnpm test:e2e
```

## Routes

```text
/workspace                                                   # Redirects to the declaration assistant
/workspace/agents/government-project-declaration/chats/new   # New proposal-assistant chat
/workspace/agents/government-project-declaration/chats/[id]  # Proposal-assistant chat thread
/workspace/knowledge                                         # LLM-Wiki knowledge base management
/workspace/proposal-drafts                                   # Markdown proposal draft management
/workspace/settings                                          # Models, tools, skills, memory, and preferences
/login, /setup                                               # Optional local-auth flow
```

## Configuration

For local split-origin development, the root `start_web_agent.py` script sets
the usual frontend and backend URLs. Manual overrides can still be supplied:

```bash
NEXT_PUBLIC_BACKEND_BASE_URL="http://127.0.0.1:10086"
NEXT_PUBLIC_LANGGRAPH_BASE_URL="http://127.0.0.1:9527/api/langgraph"
NEXT_PUBLIC_ENABLE_LOCAL_AUTH="false"
```

Set `NEXT_PUBLIC_ENABLE_LOCAL_AUTH=true` only when the backend also enables
`GATEWAY_ENABLE_LOCAL_AUTH=true`.

## Project Structure

```text
tests/
  e2e/                    # Playwright tests with mocked backend
  e2e-real-backend/       # Playwright tests against a real backend
  unit/                   # Vitest unit tests
src/
  app/                    # Next.js App Router pages
    api/                  # Frontend API proxy routes
    workspace/            # Government declaration workspace pages
    (auth)/               # Optional login/setup routes
  components/
    government/           # Government proposal shell and domain UI
    ui/                   # Reusable UI primitives
    workspace/            # Shared chat, message, artifact, and sidebar components
    ai-elements/          # AI message and composer elements
  core/                   # API clients, domain types, hooks, settings
  hooks/                  # Shared React hooks
  lib/                    # Shared utilities
  styles/                 # Global styles
```

## Scripts

| Command             | Description                    |
| ------------------- | ------------------------------ |
| `pnpm dev`          | Start development server       |
| `pnpm build`        | Build for production           |
| `pnpm start`        | Start production server        |
| `pnpm test`         | Run unit tests with Vitest     |
| `pnpm test:e2e`     | Run E2E tests with Playwright  |
| `pnpm format`       | Check formatting with Prettier |
| `pnpm format:write` | Apply formatting with Prettier |
| `pnpm lint`         | Run ESLint                     |
| `pnpm lint:fix`     | Fix ESLint issues              |
| `pnpm typecheck`    | Run TypeScript type checking   |
| `pnpm check`        | Run lint and typecheck         |

## Development Notes

- The default entry is the government declaration assistant, not the generic
  base chat route.
- Knowledge-base content is managed through the workspace knowledge area and
  LLM-Wiki index files.
- Proposal drafts are stored as Markdown artifacts and surfaced in the draft
  management page.

## License

MIT License. See [LICENSE](../LICENSE) for details.
