# Release Checklist

Use this as a quick pre-demo or pre-release pass.

## Local

- [ ] Env vars are set:
  `NEXT_PUBLIC_API_BASE_URL`, `DEMO_REPO_URL`, `CORS_ORIGINS`
- [ ] Backend boots locally:
  `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- [ ] Frontend boots locally:
  `npm run dev`
- [ ] `http://localhost:3000` loads and the homepage can start an audit
- [ ] The audit page loads for a new or demo audit
- [ ] Live stream updates appear on the audit page
- [ ] The wall page loads and shows findings
- [ ] The API smoke script passes:
  `python scripts/smoke_api.py`

## Deploy

- [ ] Railway API URL responds at `/api/health`
- [ ] Vercel web URL loads successfully
- [ ] Deployed homepage can start a demo audit
- [ ] Deployed audit page loads and shows stream updates
- [ ] Deployed wall page loads
- [ ] Web app points at the correct deployed API base URL
