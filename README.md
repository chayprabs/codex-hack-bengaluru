# TrustLayer Demo Console

*A safe, deterministic monorepo built for live TrustLayer demos.*

## What This Repo Is

This repository is a medium-sized demo application built to showcase TrustLayer end to end.

- It pairs a Next.js 15 / React 19 frontend with a FastAPI backend, typed audit models, SQLite-backed demo state, and simple deployment/runtime tooling.
- It is intentionally shaped like a realistic, vibe-coded startup app rather than a toy project: clean routes, admin-style surfaces, integration-like edges, environment configuration, tests, and deployment docs.
- It is genuinely medium-sized for a demo repo: two deployable apps, a typed streaming API, a replay-vault handoff layer, a 10-specialist backend roster, seeded profiles, and a dedicated backend test suite under `apps/api/tests`.
- It contains seeded audit and demo artifacts that support deterministic security-audit storytelling where it matters. On API startup, the wall is pre-populated with seeded completed audits, and the flagship demo path launches a stable report narrative on demand.
- The seeded profile set is concrete rather than generic: `trustlayer-flagship`, `billing-webhooks`, `tenant-portal`, `ui-release-monitor`, and `ops-runner-console`.
- It is designed for live demos, agent traces, evidence bundles, score changes, replay-ready artifacts, and final reports.
- It is a safe TrustLayer demo target. It is not presented as a real intentionally exploitable production app.

## App Overview

The app is a security-audit workspace for launching repo reviews and watching the audit story unfold in real time.

Core user flows:

- Start the flagship demo from the landing page, or launch a fast or deep audit for a public GitHub repository.
- Watch planner, scanner, and verifier lanes publish status, traces, findings, score movement, and coverage updates in the audit room.
- Review the final report, replay-vault handoff records, and generated evidence bundle once the run completes.
- Open the audit wall to see seeded and recent findings ranked across audits.

Main pages:

- `/` for audit launch, demo launch, and mode selection.
- `/audit/[id]` for the live audit room, score narrative, finding feed, agent traces, evidence bundle, and final report summary.
- `/wall` for the ranked findings view across seeded and live audits.
- `/docs` on the API for backend contract inspection.

Main API routes:

- `/api/health` for health status.
- `/api/demo-setup` to expose the stable flagship demo repo, backup stories, and score journeys.
- `/api/audits` to create audits.
- `/api/demo-audit` to open the deterministic flagship room, with optional `profile_key` support for backup seeded stories.
- `/api/audits/{id}` to fetch audit state.
- `/api/audits/{id}/stream` for SSE-backed room updates with polling fallback on the frontend.
- `/api/wall` for the wall feed.

Main domain objects:

- `Audit` is the top-level run state, including score, coverage, agents, findings, and completion status.
- `Finding` carries the reported issue, evidence snippet, confidence, proof type, and patch guidance.
- `AgentStatus` and `AgentTrace` power the planner/scanner/verifier lane story.
- `ReplayRecord` turns important findings into structured replay and regression-handoff artifacts.
- `WallEntry` powers the cross-audit wall view.

Why the codebase feels realistic:

- It is split into a real web app and API, not a single mock file.
- It uses typed contracts on both sides, SSE with replay/polling fallback, local persistence, startup seeding, and deployment docs.
- The UI has dedicated components for evidence bundles, final report summaries, wall ranking, score motion, and agent traces instead of a single dashboard placeholder.
- The seeded scenarios cover plausible startup-app surfaces such as billing webhooks, tenant exports, release workflows, runner bootstrap behavior, runtime dependencies, and configuration hygiene.

## Why This Repo Is Great For TrustLayer Demos

- Medium complexity: big enough to feel credible, small enough to understand quickly.
- Clear route structure: the landing page, audit room, and wall give a clean demo arc.
- Settings, integrations, and admin-style surfaces: webhook, authz, config, dependency, release, runtime, AI-guardrail, and input-validation checks all have visible narrative value.
- Repo-mapper-friendly layout: `apps/web` and `apps/api` are cleanly separated, with obvious models, services, routes, and UI surfaces.
- Deterministic audit support: seeded profiles in the backend keep the flagship walkthrough stable and repeatable, while live-repo mode remains available for the unscripted path.
- Evidence, traces, and replay-ready artifacts: the audit room exposes lane status, traces, replay records, and downloadable handoff content.
- Strong before/after storytelling: score and coverage move in a way that makes the report feel inspectable rather than theatrical.

## What TrustLayer Is Expected To Surface

The categories below are seeded demo findings or deterministic audit scenarios where applicable. They are included to support product storytelling, not to represent live exploitable flaws.

- Secrets and credential-handling scenarios, including placeholder secret hygiene and long-lived token narrative paths surfaced by the seeded release and credential reviews.
- Access-control and object-access scenarios, including tenant or workspace scoping gaps used for deterministic object-access storytelling.
- Webhook and integration trust scenarios, especially signature-validation and callback-ordering risk in the flagship and billing-focused profiles.
- Auth and trust-boundary scenarios, where authenticated state still needs stronger ownership or boundary checks.
- Unsafe code-pattern scenarios across release flows, runtime dependencies, runner bootstrap, cleanup behavior, or repo-owned execution paths.
- Config and frontend-exposure scenarios involving runtime packages, headers, CORS-like concerns, preview surfaces, and browser-facing configuration.
- Coverage, unsupported-scope, and manual-review signals that show where the audit remains provisional instead of overstating confidence.

## Repo Structure

```text
.
|-- apps/
|   |-- web/
|   |   |-- app/                # Next.js routes: landing page, audit room, wall
|   |   |-- components/         # audit UI, scorecards, traces, evidence, report views
|   |   |-- hooks/              # audit stream client logic
|   |   `-- lib/                # typed API client and presentation helpers
|   `-- api/
|       |-- app/
|       |   |-- api/routes/     # /api/health, /api/audits, /api/demo-audit, /api/wall
|       |   |-- agents/         # specialist agent definitions and deterministic audit checks
|       |   |-- models/         # Audit, Finding, ReplayRecord, WallEntry
|       |   |-- sandbox/        # safe repo acquisition and execution helpers
|       |   `-- services/       # orchestration, seeded demo data, scoring, replay vault
|       `-- tests/              # lifecycle, formatting, replay, and coverage tests
|-- docs/
|   |-- demo-highlights.md
|   |-- demo-script.md
|   `-- release-checklist.md
|-- infra/                      # docker-oriented infrastructure helpers
|-- scripts/                    # setup/dev helpers and smoke tools
|-- .env.example                # shared local defaults with placeholder values only
|-- DEPLOYMENT.md
`-- package.json
```

Notes:

- The main app pages live in [`apps/web/app`](./apps/web/app), and the main UI building blocks live in [`apps/web/components`](./apps/web/components).
- API routes are defined under [`apps/api/app/api/routes`](./apps/api/app/api/routes).
- Settings, integrations, and admin-style audit surfaces are modeled primarily through [`apps/api/app/agents`](./apps/api/app/agents), including `secrets`, `auth`, `authz`, `webhook`, `dependency`, `ai_guardrails`, `config_headers_cors`, `input_validation`, `frontend_runtime`, and `build_type_lint`.
- Deterministic audit support and replay-handoff generation live in [`apps/api/app/services/demo_data.py`](./apps/api/app/services/demo_data.py) and [`apps/api/app/services/replay_vault.py`](./apps/api/app/services/replay_vault.py).
- Local smoke and runner helpers live in [`scripts`](./scripts), including [`scripts/smoke_api.py`](./scripts/smoke_api.py).

## Safe Demo Architecture

- No real secrets are included. Example values in `.env.example` and app-specific env examples are placeholders only.
- No exploit playbooks or misuse instructions are included in this repository or this README.
- The repo is built for safe demonstration, local evaluation, and product narration.
- Seeded audits, wall entries, score motion, replay records, and evidence bundles are deterministic demo-oriented artifacts where applicable.
- The most visible seeded narrative is the flagship Acme-style subscriptions story shown in the landing page and audit room, backed by explicit startup seed logic in `apps/api/app/services/demo_data.py`.
- The purpose of this codebase is to showcase the audit product and its outputs, not to act as a vulnerable deployment target.

## Local Development

```bash
npm run setup
cp .env.example .env
cp apps/web/.env.local.example apps/web/.env.local
cp apps/api/.env.example apps/api/.env
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

Notes:

- On PowerShell, replace `cp` with `Copy-Item`.
- The default env files use placeholder values only.
- The API seeds demo wall data on startup.
- The flagship demo path works without adding real provider secrets.
- The stable flagship repo path is `https://github.com/trustlayer-demo/acme-subscriptions-platform`.

## Demo Highlights

- Strongest seeded categories: secrets and credential hygiene, webhook trust, authz/object access, release safety, runtime/dependency exposure, runner-boundary behavior, and coverage/manual-review signaling.
- Stable flagship path: `https://github.com/trustlayer-demo/acme-subscriptions-platform` with a visible `100 -> 57` TrustScore arc and `12 -> 92` coverage arc.
- Backup paths: the homepage exposes seeded billing, tenant, UI-release, and runner stories if a live repo stays boring, and the audit room falls back to replay sync if SSE drops.
- Best visible areas for narration: the landing page, the `/audit/[id]` room, the `EvidenceBundleCard`, the `FinalReportSummaryCard`, and the `/wall` leaderboard.
- Best artifacts to point at live: planner/scanner/verifier lanes, SSE-backed score and coverage motion, replay-vault records, downloadable markdown handoff, and the ranked wall feed.
- Supporting docs: [Demo Highlights](./docs/demo-highlights.md), [Demo Script](./docs/demo-script.md), [Release Checklist](./docs/release-checklist.md), [Scripts](./scripts/README.md), and [Deployment Guide](./DEPLOYMENT.md).

## For Judges / Reviewers

- Start with the landing page, run the flagship demo, inspect the completed audit room, and then open the wall.
- If you want the strongest demo artifacts in code, look first at [`apps/api/app/services/demo_data.py`](./apps/api/app/services/demo_data.py), [`apps/api/app/services/replay_vault.py`](./apps/api/app/services/replay_vault.py), [`apps/web/components/EvidenceBundleCard.tsx`](./apps/web/components/EvidenceBundleCard.tsx), and [`apps/web/components/FinalReportSummaryCard.tsx`](./apps/web/components/FinalReportSummaryCard.tsx).
- If you want confidence that the demo story is intentional and repeatable, inspect [`apps/api/tests`](./apps/api/tests).
- The repo is structured this way so a reviewer can understand the product surface, the deterministic seeded narrative, and the final-report artifacts in under a minute.

## License / Disclaimer

This repository is a TrustLayer demo environment intended for safe product demonstration and technical evaluation. Seeded findings, traces, replay records, and evidence bundles are deterministic demo artifacts where applicable, and all example credential values are placeholders. A standalone `LICENSE` file is not included in this snapshot.
