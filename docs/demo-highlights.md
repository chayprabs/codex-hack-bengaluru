# Demo Highlights

This repo is optimized for a short, reliable TrustLayer walkthrough.

## Fast Demo Path

1. Run `npm run setup`, copy the example env files, and start the repo with `npm run dev`.
2. Open `http://localhost:3000`.
3. Click **Run flagship demo**.
4. Narrate the audit room in this order: TrustScore and Coverage, planner/scanner/verifier lanes, finding feed, final report summary, evidence bundle.
5. Finish on `/wall` to show that the seeded demo data also supports ranked cross-audit storytelling.

## Best Seeded Categories

- Secrets and credential-handling hygiene
- Webhook and third-party callback trust
- Authorization and object scoping
- Release-gate and workflow safety
- Runtime dependency and frontend exposure
- Coverage, unsupported scope, and manual-review signals

## Best Files To Inspect

- [`apps/api/app/services/demo_data.py`](../apps/api/app/services/demo_data.py) for seeded profiles and deterministic score/finding arcs
- [`apps/api/app/services/replay_vault.py`](../apps/api/app/services/replay_vault.py) for replay and regression-handoff generation
- [`apps/web/components/EvidenceBundleCard.tsx`](../apps/web/components/EvidenceBundleCard.tsx) for the downloadable developer handoff
- [`apps/web/components/FinalReportSummaryCard.tsx`](../apps/web/components/FinalReportSummaryCard.tsx) for the final report framing
- [`apps/api/tests`](../apps/api/tests) for repeatability and lifecycle coverage

## Supporting References

- [Release Checklist](./release-checklist.md)
- [Scripts README](../scripts/README.md)
- [Deployment Guide](../DEPLOYMENT.md)
