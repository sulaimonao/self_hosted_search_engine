<<<<<<< ours
<<<<<<< ours
# Frontend

This directory contains the Next.js frontend for the self-hosted search engine.

## Development

To run the frontend in development mode, you'll need to have Node.js and npm installed.

### Setup

1.  **Install dependencies:**
    From the root of the repository, run the following command to install both backend and frontend dependencies:
    ```bash
    make setup
    ```

2.  **Run the development server:**
    From the root of the repository, run the following command to start both the backend and frontend development servers:
    ```bash
    make dev
    ```
    The frontend will be available at [http://localhost:3000](http://localhost:3000).

### Manual Setup

If you prefer to run the frontend separately, you can use the following commands from within the `frontend` directory:

1.  **Install dependencies:**
    ```bash
    npm install
    ```

2.  **Run the development server:**
    ```bash
    npm run dev
    ```
=======
=======
>>>>>>> theirs
# Atlas Agent Console (Frontend)

A Next.js 14 + Tailwind + shadcn/ui single-page app that provides a co-pilot console for the self-hosted search engine. The UI keeps the user in control by pairing an in-app browser with chat-driven agent actions, live job observability, and explicit approval flows.

## Features

- **Split cockpit layout** – embedded web preview on the left, chat + controls on the right.
- **Streaming chat** – bi-directional messaging with proposed actions that require approval.
- **Action cards** – approve, edit, or dismiss agent suggestions.
- **Crawl manager** – drag-and-drop URLs, scope presets, and queue management.
- **Agent log + job status** – realtime feedback streamed from backend job endpoints.
- **Model settings** – inspect available Ollama models and request changes.
- **Omnibox & command palette** – keyboard-friendly navigation (`⌘L` / `⌘K`).

## Prerequisites

- Node.js 18+
- npm 9+
- Python environment created via `make setup` at the repository root (provides backend + data dependencies).

## Installation

From the repository root:

```bash
cd frontend
npm install
```

## Running in development

The recommended flow launches backend and frontend together:

```bash
# from the repository root
make dev
```

This command will:

1. Load environment variables from `.env` (if present).
2. Run backend pre-flight checks (`bin/dev_check.py`).
3. Start the Flask backend on `http://127.0.0.1:5000` (configurable via `UI_PORT`).
4. Start the Next.js dev server on `http://127.0.0.1:3000` (configurable via `FRONTEND_PORT`).
5. Configure `NEXT_PUBLIC_BACKEND_URL` so the SPA rewrites `/api/*` calls to the Flask backend.

If you prefer to run the frontend only, use:

```bash
npm run dev
```

Ensure the backend is running separately so `/api` endpoints resolve.

## Environment variables

Create `frontend/.env.local` (optional) to override defaults:

```
# Base URL for backend API (defaults to http://127.0.0.1:5000)
NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:5000

# Override Next.js dev server port
FRONTEND_PORT=3001
```

## Production build

```bash
npm run build
npm run start
```

The production bundle still depends on backend endpoints being reachable at `NEXT_PUBLIC_BACKEND_URL`.

## Testing / linting

```bash
npm run lint
```

## Smoke test

Run `npm run build` to ensure the production build succeeds. The build step compiles TypeScript, validates Tailwind usage, and surfaces static type errors.
<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
