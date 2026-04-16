# Deployment Guide

This monorepo deploys cleanly as two separate services:

- `apps/web` on Vercel
- `apps/api` on Railway

Deploy the API first so you have the public backend URL ready for the web app.

## Vercel For `apps/web`

### Project Directory

- Create one Vercel project for this repo.
- Set the project `Root Directory` to `apps/web`.

Vercel's monorepo docs note that each deployable directory should be imported as its own project and configured with its own root directory.

### Build And Start

- Framework preset: `Next.js`
- Install command: leave the default auto-detected command, or use `npm install` if you want to override it
- Build command: leave the default auto-detected command, or use `npm run build` if you want to override it
- Start command: none; Vercel manages the Next.js runtime for this project

### Environment Variables

Set this in Vercel for Preview and Production:

```env
NEXT_PUBLIC_API_BASE_URL=https://your-api.up.railway.app/api
```

Notes:

- include the `/api` suffix because the frontend client calls API routes under that prefix
- after changing environment variables, trigger a new deployment

## Railway For `apps/api`

### Service Directory

- Create one Railway service for this repo.
- Set the service `Root Directory` to `apps/api`.

Railway's monorepo docs recommend setting a root directory per service so the deployment uses only that subdirectory.

### Build And Start

- Builder: leave the default Railpack builder
- Build command: leave blank unless you need to override auto-detection
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Why set the start command explicitly:

- Railway supports custom start commands for monorepos
- this FastAPI service does not expose a default `main.py` entrypoint that Railway would reliably auto-start on its own

### Environment Variables

Set these in Railway:

```env
DEMO_REPO_URL=https://github.com/vercel/next.js
CORS_ORIGINS=https://your-web.vercel.app
```

Optional variables:

```env
OPENAI_API_KEY=sk-your-openai-api-key
GITHUB_TOKEN=github_pat_your-github-token
DATABASE_URL=sqlite:///./trustlayer.db
```

Notes:

- for multiple frontend origins, set `CORS_ORIGINS` as a comma-separated list
- `DATABASE_URL=sqlite:///./trustlayer.db` works, but SQLite on Railway is not durable across restarts or redeploys
- if you later move to a managed database, update `DATABASE_URL` accordingly

## Monorepo Notes

- Vercel and Railway should each point to the same Git repository, but different subdirectories
- no `vercel.json`, `railway.toml`, or `railway.json` was added on purpose; dashboard settings are enough for the current setup
- if you change the public Railway URL, update `NEXT_PUBLIC_API_BASE_URL` in Vercel and redeploy the web app

## Minimal Rollout Order

1. Deploy `apps/api` to Railway.
2. Generate the public Railway domain.
3. Set `CORS_ORIGINS` on Railway to your Vercel domain.
4. Set `NEXT_PUBLIC_API_BASE_URL` on Vercel to the Railway URL plus `/api`.
5. Deploy `apps/web` to Vercel.
6. Verify `https://your-api.up.railway.app/api/health` and the web app's demo audit flow.
