# Frontend UI

Modern copilot interface for the self-hosted search engine. The app is built with Next.js (App Router), Tailwind CSS 4, and shadcn/ui.

## Prerequisites

- Node.js 18+ (Node 20+ recommended for React 19 support)
- npm (bundled with Node)
- Python environment for the backend (see repository root instructions)

Install JS dependencies once:

```bash
cd frontend
npm install
```

## Development workflow

The recommended way to launch the full stack is:

```bash
make dev
```

`make dev` spins up the Flask backend and the Next.js dev server together. Key environment knobs:

- `UI_PORT` / `FLASK_RUN_PORT` – backend port (default `5000`)
- `FRONTEND_PORT` – Next.js port (default `3100`)
- `NEXT_PUBLIC_API_BASE_URL` – API base URL; defaults to `http://127.0.0.1:${UI_PORT}` for dev

During development the frontend proxies API calls via `NEXT_PUBLIC_API_BASE_URL`, so ensure the backend is reachable at that address.

You can still run the frontend independently if needed:

```bash
npm run dev -- --port 3100
```

Remember to export `NEXT_PUBLIC_API_BASE_URL` when running standalone.

## Available scripts

```bash
npm run dev        # start Next.js dev server
npm run build      # production build
npm run start      # serve the production build
npm run lint       # ESLint (includes TypeScript checks)
```

> The dev UI listens on `http://localhost:3100` (or `http://127.0.0.1:3100`). Both hosts are pre-whitelisted via `allowedDevOrigins` in `next.config.mjs`, eliminating the usual cross-origin warning banner.

## Environment variables

- `NEXT_PUBLIC_API_BASE_URL`: Absolute base URL for backend requests. Leave blank when the SPA is served by Flask in production.

## Production build

For a production bundle:

```bash
npm run build
npm run start -- --hostname 0.0.0.0 --port 3100
```

Set `NEXT_PUBLIC_API_BASE_URL` to the live backend URL before building if the API lives on a different origin.

## Features snapshot

- Unified omnibox workflow: keyword queries call `/api/search` and render side-by-side results with quick "Ask agent" escalation into chat.
- Split pane layout with in-app browser preview, omnibox, and copilot chat
- Streaming chat responses from `/api/chat` with inline action cards (crawl, index, seeds)
- Drag & drop URLs into the crawl queue and highlight capture with manual approvals
- Live job log polling from `/api/jobs/:id/status` surfaced in the Agent Log & Job Status widgets
- Model picker wired to `/api/llm/status` + `/api/llm/models`

## Crawl queue workflow

The Crawl Manager widget now persists entries through the seed registry API:

1. On mount the component calls `GET /api/seeds` to hydrate the queue from `seeds/registry.yaml`.
2. Adding, updating, or removing an entry issues `POST`/`PUT`/`DELETE` requests that require the latest `revision` hash. The backend returns the refreshed queue on every success.
3. If the revision mismatches (another client wrote first) the API responds with `409 Conflict`; the UI automatically reloads and surfaces an error banner so users can retry safely.

Agent-approved crawl actions also persist new seeds through the same API helpers so manual edits and automated approvals stay in sync.

For backend configuration and deeper agent controls, see the repository root `README`.

## Search and chat interplay

The omnibox now routes non-URL submissions through the local semantic index:

1. Press Enter on a keyword and the UI issues `GET /api/search?q=...` via the new `searchIndex` helper.
2. Results, confidence, and crawl status appear in the Search panel beside the preview.
3. Use the **Ask agent** button to send the same query to `/api/chat` when you need reasoning or follow-up actions.
4. If the search triggers a focused crawl, progress is reflected both in the panel and the Agent Ops tab.

Paste an absolute URL at any time to jump directly into the preview pane without triggering search.

## Workspace browsing & crawling

- External URLs now open inside the dedicated `/workspace` route. The preview header mirrors the omnibox history controls and exposes a **Crawl domain** shortcut.
- Loading a page triggers a background call to `/api/extract?url=...`; the response auto-populates the Page context panel so chat immediately has server-side context (text plus optional screenshot).
- Selecting **Crawl domain** posts `{ urls: [url], scope: "domain" }` to `/api/seeds`, then forces `/api/refresh` with `use_llm:false`. Progress is surfaced by polling `/api/index/stats` until the indexed document count increases.
- The Local Search input stays disabled until `/api/index/stats` reports at least one document. When enabled it first attempts `GET /api/search?q=...` and gracefully falls back to `POST /api/search` for compatibility with older servers.
