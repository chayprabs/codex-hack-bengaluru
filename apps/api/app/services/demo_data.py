from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from ..models import AgentStatus, Audit, utc_now
from .audit_simulation import (
    AuditLifecycleStep,
    ScoreUpdateSpec,
    SimulatedFindingSpec,
    materialize_lifecycle,
)


@dataclass(frozen=True, slots=True)
class DemoAuditProfile:
    key: str
    repo_url: str
    match_tokens: tuple[str, ...]
    seed_minutes_ago: int | None
    steps: tuple[AuditLifecycleStep, ...]


def build_demo_profiles(primary_demo_repo_url: str) -> tuple[DemoAuditProfile, ...]:
    return (
        DemoAuditProfile(
            key="trustlayer-flagship",
            repo_url=primary_demo_repo_url,
            match_tokens=(),
            seed_minutes_ago=None,
            steps=tuple(_build_flagship_steps()),
        ),
        DemoAuditProfile(
            key="billing-webhooks",
            repo_url="https://github.com/trustlayer-demo/acme-billing-hooks",
            match_tokens=("billing", "webhook", "stripe", "payment", "hooks"),
            seed_minutes_ago=96,
            steps=tuple(_build_billing_webhooks_steps()),
        ),
        DemoAuditProfile(
            key="tenant-portal",
            repo_url="https://github.com/trustlayer-demo/workspace-portal",
            match_tokens=("tenant", "portal", "auth", "workspace", "account", "idor"),
            seed_minutes_ago=58,
            steps=tuple(_build_tenant_portal_steps()),
        ),
        DemoAuditProfile(
            key="ui-release-monitor",
            repo_url="https://github.com/trustlayer-demo/ui-release-monitor",
            match_tokens=("frontend", "ui", "web", "dashboard", "monorepo", "design-system"),
            seed_minutes_ago=24,
            steps=tuple(_build_ui_release_steps()),
        ),
    )


def select_demo_profile(
    repo_url: str,
    *,
    primary_demo_repo_url: str,
) -> DemoAuditProfile:
    profiles = build_demo_profiles(primary_demo_repo_url)
    normalized_repo_url = repo_url.strip().lower()

    for profile in profiles:
        if normalized_repo_url == profile.repo_url.lower():
            return profile

    for profile in profiles[1:]:
        if any(token in normalized_repo_url for token in profile.match_tokens):
            return profile

    return profiles[0]


def build_demo_lifecycle_steps(audit: Audit, *, primary_demo_repo_url: str) -> list[AuditLifecycleStep]:
    profile = select_demo_profile(
        audit.repo_url,
        primary_demo_repo_url=primary_demo_repo_url,
    )
    return list(profile.steps)


def build_seed_demo_audits(
    *,
    primary_demo_repo_url: str,
    initial_agents: list[AgentStatus],
) -> list[Audit]:
    seeded_audits: list[Audit] = []
    now = utc_now()

    for profile in build_demo_profiles(primary_demo_repo_url):
        if profile.seed_minutes_ago is None:
            continue

        started_at = now - timedelta(minutes=profile.seed_minutes_ago)
        queued_audit = Audit(
            id=str(uuid5(NAMESPACE_URL, f"trustlayer-demo:{profile.key}")),
            repo_url=profile.repo_url,
            status="queued",
            score=100,
            created_at=started_at,
            updated_at=started_at,
            agents=[
                agent.model_copy(
                    update={
                        "status": "queued",
                        "message": "Waiting to start.",
                        "updated_at": started_at,
                    }
                )
                for agent in initial_agents
            ],
            findings=[],
        )
        seeded_audits.append(
            materialize_lifecycle(
                queued_audit,
                list(profile.steps),
                started_at=started_at,
            )
        )

    return seeded_audits


def _build_flagship_steps() -> list[AuditLifecycleStep]:
    return [
        AuditLifecycleStep(
            delay_seconds=0.3,
            audit_status="running",
            agent_name="planner",
            agent_status="running",
            agent_message="Indexing API routes, GitHub Actions, and environment templates.",
            score_update=ScoreUpdateSpec(
                score=97,
                reason="TrustLayer mapped the initial attack surface across app, CI, and runtime edges.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.45,
            agent_name="planner",
            agent_status="completed",
            agent_message="Scope locked around secrets, webhooks, authz, and release safety.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.35,
            agent_name="scanner",
            agent_status="running",
            agent_message="Scanning secret material, webhook trust boundaries, and tenant controls.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.55,
            finding=SimulatedFindingSpec(
                severity="high",
                title="Deploy workflow references a long-lived preview token",
                summary=(
                    "A checked-in deployment example still references a long-lived preview token, "
                    "which makes copy-paste reuse likely and weakens secret hygiene around releases."
                ),
                file_path=".github/workflows/deploy-preview.yml",
                line=22,
            ),
            score_update=ScoreUpdateSpec(
                score=86,
                reason="The secret review surfaced a high-impact deploy token exposure pattern.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.45,
            finding=SimulatedFindingSpec(
                severity="high",
                title="Billing webhook accepts unsigned events",
                summary=(
                    "The billing webhook path processes event bodies before validating the upstream "
                    "signature header, which means forged callbacks could influence subscription state."
                ),
                file_path="apps/api/routes/webhooks.py",
                line=48,
            ),
            score_update=ScoreUpdateSpec(
                score=71,
                reason="Webhook trust validation is missing on a revenue-impacting integration surface.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.45,
            finding=SimulatedFindingSpec(
                severity="medium",
                title="Invoice export trusts workspace_id from the query string",
                summary=(
                    "The export endpoint checks for a valid session but does not re-verify workspace "
                    "ownership before loading the requested invoices, leaving an IDOR-style gap."
                ),
                file_path="apps/api/routes/invoices.py",
                line=91,
            ),
            score_update=ScoreUpdateSpec(
                score=62,
                reason="Authorization review confirmed a tenant-boundary weakness on exported data.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.35,
            agent_name="scanner",
            agent_status="completed",
            agent_message="Static scan complete. Verified leads handed to the verifier lane.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.25,
            agent_name="verifier",
            agent_status="running",
            agent_message="Correlating findings with build safety and frontend runtime evidence.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.45,
            finding=SimulatedFindingSpec(
                severity="low",
                title="Hotfix workflow skips typecheck and lint",
                summary=(
                    "The emergency release job packages artifacts before running typecheck and eslint, "
                    "increasing the chance of shipping broken authz or validation logic under pressure."
                ),
                file_path=".github/workflows/release-hotfix.yml",
                line=37,
            ),
            score_update=ScoreUpdateSpec(
                score=58,
                reason="Build safety degraded because the hotfix pipeline bypasses its quality gates.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.4,
            finding=SimulatedFindingSpec(
                severity="medium",
                title="Frontend preview uses an outdated markdown renderer",
                summary=(
                    "The preview surface depends on a markdown renderer with a known script-injection "
                    "advisory, keeping the trust score lower until the runtime dependency is upgraded."
                ),
                file_path="apps/web/package.json",
                line=28,
            ),
            score_update=ScoreUpdateSpec(
                score=51,
                reason="A user-facing dependency issue kept the final trust score in a cautionary range.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.35,
            audit_status="completed",
            agent_name="verifier",
            agent_status="completed",
            agent_message="Verification complete. TrustLayer report is ready for review.",
        ),
    ]


def _build_billing_webhooks_steps() -> list[AuditLifecycleStep]:
    return [
        AuditLifecycleStep(
            delay_seconds=0.25,
            audit_status="running",
            agent_name="planner",
            agent_status="running",
            agent_message="Tracing billing flows, webhook handlers, and deploy credentials.",
            score_update=ScoreUpdateSpec(
                score=96,
                reason="Billing surfaces were mapped and prioritized for a revenue-path review.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.3,
            agent_name="planner",
            agent_status="completed",
            agent_message="Scoped the review to secrets, callbacks, and payout state mutations.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.3,
            agent_name="scanner",
            agent_status="running",
            agent_message="Checking webhook trust boundaries and secrets used by release jobs.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.35,
            finding=SimulatedFindingSpec(
                severity="medium",
                title="Staging webhook secret is mirrored into a sample env file",
                summary=(
                    "A staging webhook secret appears in a checked-in sample env template, which "
                    "encourages secret reuse and weakens rotation discipline for payment callbacks."
                ),
                file_path=".env.staging.example",
                line=6,
            ),
            score_update=ScoreUpdateSpec(
                score=82,
                reason="Secret handling on the billing path needs cleanup before broader rollout.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.4,
            finding=SimulatedFindingSpec(
                severity="high",
                title="Payout webhook skips signature validation on retry paths",
                summary=(
                    "Retry handling falls back to raw payload processing without checking the provider "
                    "signature, creating a credible forged-event path into payout state changes."
                ),
                file_path="services/webhooks/payouts.py",
                line=58,
            ),
            score_update=ScoreUpdateSpec(
                score=63,
                reason="The payout webhook can be influenced by unsigned retry traffic.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.25,
            agent_name="scanner",
            agent_status="completed",
            agent_message="Billing scan complete. Escalated webhook verification failure to verifier.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.25,
            audit_status="completed",
            agent_name="verifier",
            agent_status="completed",
            agent_message="Verifier confirmed the billing trust issues and finalized the report.",
        ),
    ]


def _build_tenant_portal_steps() -> list[AuditLifecycleStep]:
    return [
        AuditLifecycleStep(
            delay_seconds=0.2,
            audit_status="running",
            agent_name="planner",
            agent_status="running",
            agent_message="Mapping tenant routes, admin actions, and document access paths.",
            score_update=ScoreUpdateSpec(
                score=95,
                reason="Portal surface mapped across tenant-aware reads, writes, and exports.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.25,
            agent_name="planner",
            agent_status="completed",
            agent_message="Scoped review to tenant isolation, preview flows, and object ownership.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.3,
            agent_name="scanner",
            agent_status="running",
            agent_message="Testing tenant ownership checks and shared preview runtime boundaries.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.35,
            finding=SimulatedFindingSpec(
                severity="high",
                title="Customer document endpoint trusts account_id from the URL",
                summary=(
                    "The document download handler uses the authenticated session but does not "
                    "re-check whether the requested account_id belongs to that user, enabling IDOR."
                ),
                file_path="apps/api/routes/customer_documents.py",
                line=74,
            ),
            score_update=ScoreUpdateSpec(
                score=76,
                reason="Tenant isolation broke on a document access path with sensitive records.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.35,
            finding=SimulatedFindingSpec(
                severity="medium",
                title="Preview runtime accepts postMessage events from any origin",
                summary=(
                    "The admin preview frame processes postMessage payloads without constraining "
                    "origin, which can widen the blast radius of compromised content previews."
                ),
                file_path="apps/web/components/PreviewFrame.tsx",
                line=33,
            ),
            score_update=ScoreUpdateSpec(
                score=68,
                reason="Frontend runtime trust remained weaker after origin validation failed.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.25,
            agent_name="verifier",
            agent_status="completed",
            audit_status="completed",
            agent_message="Verifier confirmed the tenant-boundary and preview-runtime issues.",
        ),
    ]


def _build_ui_release_steps() -> list[AuditLifecycleStep]:
    return [
        AuditLifecycleStep(
            delay_seconds=0.2,
            audit_status="running",
            agent_name="planner",
            agent_status="running",
            agent_message="Indexing workspace packages, release jobs, and shared frontend runtime code.",
            score_update=ScoreUpdateSpec(
                score=97,
                reason="UI platform audit mapped the release path and shared runtime dependencies.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.25,
            agent_name="planner",
            agent_status="completed",
            agent_message="Prioritized CI quality gates and risky runtime dependencies for scan.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.3,
            agent_name="scanner",
            agent_status="running",
            agent_message="Checking build gates, type coverage, and user-facing dependency risk.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.35,
            finding=SimulatedFindingSpec(
                severity="medium",
                title="Release pipeline bypasses lint and typecheck on patch builds",
                summary=(
                    "Patch release jobs package and publish before lint and typecheck complete, "
                    "making it too easy to ship broken guards or unsafe runtime assumptions."
                ),
                file_path=".github/workflows/release-patch.yml",
                line=29,
            ),
            score_update=ScoreUpdateSpec(
                score=83,
                reason="Build assurance dropped because CI no longer blocks on quality gates.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.35,
            finding=SimulatedFindingSpec(
                severity="medium",
                title="Shared markdown runtime depends on a vulnerable package range",
                summary=(
                    "The shared frontend rendering layer permits a markdown dependency range with a "
                    "known client-side injection advisory, which leaves the dashboard preview surface exposed."
                ),
                file_path="packages/ui/package.json",
                line=41,
            ),
            score_update=ScoreUpdateSpec(
                score=73,
                reason="A frontend runtime dependency issue kept the UI platform score below green.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.25,
            audit_status="completed",
            agent_name="verifier",
            agent_status="completed",
            agent_message="Verifier confirmed the UI release and dependency findings.",
        ),
    ]
