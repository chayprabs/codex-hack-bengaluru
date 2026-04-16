# Release Checklist

Use this as a quick pre-demo or pre-release pass.

## Local

- [ ] Env vars are set:
  `NEXT_PUBLIC_API_BASE_URL`, `DEMO_REPO_URL`, `CORS_ORIGINS`
- [ ] `DEMO_REPO_URL` points at the flagship seeded repo:
  `https://github.com/trustlayer-demo/acme-subscriptions-platform`
- [ ] Backend boots locally:
  `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- [ ] Frontend boots locally:
  `npm run dev`
- [ ] `http://localhost:3000` loads and the homepage can start an audit
- [ ] The homepage shows the flagship repo path plus backup seeded stories
- [ ] The audit page loads for a new or demo audit
- [ ] Live stream updates appear on the audit page
- [ ] If live events pause, the room falls back to replay sync without losing the story
- [ ] The wall page loads and shows findings
- [ ] A backup seeded story launches cleanly if the live repo is quiet
- [ ] The presenter has reviewed [`docs/demo-script.md`](./demo-script.md)
- [ ] The API smoke script passes:
  `python scripts/smoke_api.py`

## Deploy

- [ ] Railway API URL responds at `/api/health`
- [ ] Vercel web URL loads successfully
- [ ] Deployed homepage can start a demo audit
- [ ] Deployed homepage shows the flagship repo path and backup seeded stories
- [ ] Deployed audit page loads and shows stream updates
- [ ] Deployed audit page falls back to replay sync if SSE disconnects
- [ ] Deployed wall page loads
- [ ] Web app points at the correct deployed API base URL
