# TrustLayer

TrustLayer is a hackathon monorepo for a repo-audit experience: a Next.js frontend for launching and watching audits, and a FastAPI backend that serves audit data, seeded demo history, and live status updates over Server-Sent Events.

## Current Status

What works today:

- landing page to start an audit from a GitHub URL
- one-click demo audit flow
- audit room with agent lanes, findings, score updates, and live SSE refresh with polling fallback
- shame wall page backed by stored findings
- FastAPI endpoints for health, audits, demo audit creation, audit streaming, and wall data
- local SQLite persistence plus seeded demo audits on backend startup
- live audits that attempt safe repo acquisition, map/plan registered agents, and run workspace-bound execution checks when appropriate
- repo-local setup installs API dev tooling so unit tests and backend checks can run out of the box

## Repo Structure

```text
.
|-- apps/
|   |-- web/         # Next.js frontend
|   `-- api/         # FastAPI backend + Railway Dockerfile/config
|-- infra/           # extra deployment notes/helpers
|-- scripts/         # local dev runner scripts
|-- .env.example
|-- DEPLOYMENT.md
|-- package.json
`-- README.md
```

## Prerequisites

- Node.js and npm for `apps/web`
- Python 3.11+ for `apps/api`
- two terminals for local development
- optional: Vercel account for web deploys and Railway account for API deploys

## Env Setup

Copy the example files:

```powershell
Copy-Item .env.example .env
Copy-Item apps\web\.env.local.example apps\web\.env.local
Copy-Item apps\api\.env.example apps\api\.env
```

Use these minimum local values:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api
DATABASE_URL=sqlite:///./trustlayer.db
DEMO_REPO_URL=https://github.com/vercel/next.js
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
AUDIT_EXECUTION_BACKEND=auto
```

Notes:

- the web app expects `NEXT_PUBLIC_API_BASE_URL` to include the `/api` prefix
- `OPENAI_API_KEY` and `GITHUB_TOKEN` are optional for the current demo flow
- the API reads `apps/api/.env` first, then falls back to the root `.env`
- `AUDIT_EXECUTION_BACKEND` supports `auto`, `local`, or `docker`; `docker` currently degrades to the local sandbox with a surfaced fallback note

## Quick Start

From the repo root:

```powershell
npm run setup
npm run dev
```

Then open `http://localhost:3000`.

## Quick Local Commands

From the repo root:

```powershell
npm run setup
npm run dev
npm run dev:web
npm run dev:api
```

Setup helpers:

```powershell
npm run setup:web
npm run setup:api
```

If you prefer not to use npm at the repo root, use the wrapper scripts in [`scripts/`](./scripts/README.md).

## Run The Frontend

```powershell
Set-Location apps\web
npm install
npm run dev
npm run typecheck
```

Open `http://localhost:3000`.

## Run The Backend

```powershell
Set-Location apps\api
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -e .[dev]
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend tests:

```powershell
Set-Location apps\api
. .\.venv\Scripts\Activate.ps1
python -m pytest
```

Useful endpoints:

- app root: `http://127.0.0.1:8000/`
- API docs: `http://127.0.0.1:8000/docs`
- health check: `http://127.0.0.1:8000/api/health`

## Run Both Together

The simplest option is the root runner:

```powershell
npm run dev
```

That starts the API and web app together.

Manual fallback in separate terminals:

Terminal 1:

```powershell
Set-Location apps\api
. .\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
Set-Location apps\web
npm run dev
```

Then open `http://localhost:3000`.

## Trigger A Demo Audit

Two easy options:

1. In the UI, open `http://localhost:3000` and click `Try demo app`.
2. From the API directly:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/demo-audit
```

That returns an audit payload with an `id`. Open `http://localhost:3000/audit/<id>` to watch the run.

## Deploy The Web To Vercel

1. Import the repo into Vercel.
2. Set the project root to `apps/web`.
3. Framework preset should detect as `Next.js`.
4. Leave the install and build commands at their defaults unless Vercel fails to detect them.
5. Set `NEXT_PUBLIC_API_BASE_URL` to your Railway API URL with `/api` included, for example `https://your-api.up.railway.app/api`.
6. Redeploy after the Railway service is live.

## Deploy The API To Railway

1. Create a new Railway service from this repo.
2. Set the service root to `apps/api`.
3. Set the watch path to `/apps/api/**`.
4. Let Railway build from `apps/api/Dockerfile`.
5. Optional but recommended: set the Railway config file path to `/apps/api/railway.toml` so the start command and health check are pinned in code.
6. If you are using the Dockerfile, leave the dashboard start command blank. The image already starts with:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

7. Set these environment variables:

```env
DATABASE_URL=sqlite:///./trustlayer.db
DEMO_REPO_URL=https://github.com/vercel/next.js
CORS_ORIGINS=https://your-vercel-app.vercel.app
```

Optional:

- `OPENAI_API_KEY`
- `GITHUB_TOKEN`

After deploy, verify `https://<your-railway-domain>/api/health`, then point Vercel at `https://<your-railway-domain>/api`.

For the platform-by-platform monorepo setup, see [DEPLOYMENT.md](./DEPLOYMENT.md).

## Known Limitations

- demo audits are still simulated for speed, while live audits now attempt sandboxed repo acquisition and registered-agent analysis with partial-completion fallbacks
- the SSE broker is in-process, so live events are designed for single-instance hackathon deployments
- SQLite state is local to the running instance and will not be durable on Railway restarts or redeploys
- there is no auth, user isolation, or background job queue yet
