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
        DemoAuditProfile(
            key="ops-runner-console",
            repo_url="https://github.com/trustlayer-demo/ops-runner-console",
            match_tokens=("runner", "ops", "sandbox", "executor", "agent", "console"),
            seed_minutes_ago=12,
            steps=tuple(_build_ops_runner_steps()),
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


def _coverage_band(score: int) -> str:
    if score >= 85:
        return "deep"
    if score >= 70:
        return "broad"
    if score >= 55:
        return "targeted"
    if score >= 30:
        return "limited"
    return "minimal"


def _coverage_summary(score: int, detail: str) -> str:
    return f"Coverage is {score}/100 ({_coverage_band(score)}). {detail}"


def _demo_score_update(
    *,
    score: int,
    coverage: int,
    reason: str,
    coverage_detail: str,
    supported_areas: tuple[str, ...] = (),
    partially_supported_areas: tuple[str, ...] = (),
    unsupported_areas: tuple[str, ...] = (),
    scanned_files_count: int = 0,
    skipped_files_count: int = 0,
    frameworks_detected: tuple[str, ...] = (),
    checks_run: tuple[str, ...] = (),
    checks_skipped: tuple[str, ...] = (),
    confidence_limited: bool | None = None,
) -> ScoreUpdateSpec:
    return ScoreUpdateSpec(
        score=score,
        coverage=coverage,
        reason=reason,
        coverage_summary=_coverage_summary(coverage, coverage_detail),
        confidence_limited=coverage < 55 if confidence_limited is None else confidence_limited,
        supported_areas=supported_areas,
        partially_supported_areas=partially_supported_areas,
        unsupported_areas=unsupported_areas,
        scanned_files_count=scanned_files_count,
        skipped_files_count=skipped_files_count,
        frameworks_detected=frameworks_detected,
        checks_run=checks_run,
        checks_skipped=checks_skipped,
    )


def _build_flagship_steps() -> list[AuditLifecycleStep]:
    frameworks = ("fastapi", "nextjs", "github_actions")
    scanned_files = 164
    skipped_files = 6
    return [
        AuditLifecycleStep(
            delay_seconds=0.08,
            audit_status="running",
            agent_name="planner",
            agent_status="running",
            agent_message="Repo intake is live. Mapping API routes, billing callbacks, and release safety.",
            score_update=_demo_score_update(
                score=98,
                coverage=18,
                reason="Demo intake established the repo map and opened the first audit lanes.",
                coverage_detail="Repo intake mapped the attack surface, but specialist evidence is still assembling.",
                partially_supported_areas=("API routes", "Webhooks", "Secrets / Environment", "Configuration"),
                unsupported_areas=("Auth / Session", "Database / Schema", "Dependencies", "Frontend Runtime", "Infrastructure"),
                scanned_files_count=scanned_files,
                skipped_files_count=skipped_files,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper",),
                checks_skipped=("planner", "secrets", "webhook", "authz", "dependency", "build_type_lint"),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.14,
            agent_name="planner",
            agent_status="running",
            agent_message="Planner grouped hot zones into webhook trust, tenant exports, and release-path hygiene.",
            score_update=_demo_score_update(
                score=96,
                coverage=31,
                reason="Planner translated the repo map into concrete exploit lanes for the demo room.",
                coverage_detail="TrustLayer mapped the main app and CI surfaces. Verification is still narrow until scanner results land.",
                partially_supported_areas=("API routes", "Webhooks", "Secrets / Environment", "Configuration", "Dependencies"),
                unsupported_areas=("Auth / Session", "Database / Schema", "Frontend Runtime", "Infrastructure"),
                scanned_files_count=scanned_files,
                skipped_files_count=skipped_files,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner"),
                checks_skipped=("secrets", "webhook", "authz", "dependency", "build_type_lint"),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.12,
            agent_name="planner",
            agent_status="completed",
            agent_message="Scope locked. Scanner is moving on secrets, webhook trust, and tenant boundaries.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.12,
            agent_name="scanner",
            agent_status="running",
            agent_message="Scanner is checking secret material, callback validation, and export ownership checks.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.26,
            finding=SimulatedFindingSpec(
                severity="high",
                title="Deploy workflow references a long-lived preview token",
                summary=(
                    "A checked-in deployment example still references a long-lived preview token, "
                    "which makes copy-paste reuse likely and weakens release secret hygiene."
                ),
                file_path=".github/workflows/deploy-preview.yml",
                line=22,
            ),
            score_update=_demo_score_update(
                score=88,
                coverage=46,
                reason="The first anchored finding exposed risky release-token handling.",
                coverage_detail="Secret review is now anchored, but webhook and tenant-boundary verification still need deeper evidence.",
                supported_areas=("Secrets / Environment", "Configuration"),
                partially_supported_areas=("API routes", "Webhooks", "Auth / Session", "Dependencies", "Frontend Runtime"),
                unsupported_areas=("Database / Schema", "Infrastructure"),
                scanned_files_count=scanned_files,
                skipped_files_count=skipped_files,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner", "secrets"),
                checks_skipped=("webhook", "authz", "dependency", "build_type_lint"),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.18,
            agent_name="scanner",
            agent_status="running",
            agent_message="Scanner is replaying the billing callback path after the release-secret hit.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.3,
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
            score_update=_demo_score_update(
                score=74,
                coverage=64,
                reason="Webhook verification failed on a revenue-impacting callback surface.",
                coverage_detail="Billing callbacks are now verified as risky. Auth and frontend runtime checks are still partial.",
                supported_areas=("API routes", "Webhooks", "Secrets / Environment", "Configuration"),
                partially_supported_areas=("Auth / Session", "Dependencies", "Frontend Runtime", "Database / Schema"),
                unsupported_areas=("Infrastructure",),
                scanned_files_count=scanned_files,
                skipped_files_count=skipped_files,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner", "secrets", "webhook"),
                checks_skipped=("authz", "dependency", "build_type_lint"),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.24,
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
            score_update=_demo_score_update(
                score=67,
                coverage=77,
                reason="Tenant-boundary review confirmed an export path that trusts caller-supplied scope.",
                coverage_detail="Auth and data-access surfaces are now evidence-backed. Frontend runtime and infra review remain last-mile work.",
                supported_areas=("API routes", "Auth / Session", "Webhooks", "Secrets / Environment", "Configuration"),
                partially_supported_areas=("Dependencies", "Frontend Runtime", "Database / Schema"),
                unsupported_areas=("Infrastructure",),
                scanned_files_count=scanned_files,
                skipped_files_count=skipped_files,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner", "secrets", "webhook", "authz"),
                checks_skipped=("dependency", "build_type_lint"),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.16,
            agent_name="scanner",
            agent_status="completed",
            agent_message="Scanner anchored three reviewable findings and handed them to the verifier lane.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.14,
            agent_name="verifier",
            agent_status="running",
            agent_message="Verifier is replaying release safety and frontend dependency risk against the anchored findings.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.26,
            finding=SimulatedFindingSpec(
                severity="low",
                title="Hotfix workflow skips typecheck and lint",
                summary=(
                    "The emergency release job packages artifacts before running typecheck and eslint, "
                    "increasing the chance of shipping broken guards under pressure."
                ),
                file_path=".github/workflows/release-hotfix.yml",
                line=37,
            ),
            score_update=_demo_score_update(
                score=61,
                coverage=85,
                reason="Release verification showed the hotfix path can bypass quality gates.",
                coverage_detail="Build-safety verification is now in the report. Dependency review is the last major surface still settling.",
                supported_areas=("API routes", "Auth / Session", "Webhooks", "Secrets / Environment", "Configuration", "Database / Schema"),
                partially_supported_areas=("Dependencies", "Frontend Runtime", "Infrastructure"),
                scanned_files_count=scanned_files,
                skipped_files_count=skipped_files,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner", "secrets", "webhook", "authz", "build_type_lint"),
                checks_skipped=("dependency",),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.24,
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
            score_update=_demo_score_update(
                score=57,
                coverage=92,
                reason="Verifier locked the final score after the frontend dependency issue stayed in scope.",
                coverage_detail="TrustLayer anchored five findings across app, webhook, auth, dependency, and release surfaces. Infrastructure stayed out of scope for the demo replay.",
                supported_areas=("API routes", "Auth / Session", "Database / Schema", "Webhooks", "Secrets / Environment", "Configuration", "Dependencies", "Frontend Runtime"),
                partially_supported_areas=("Infrastructure",),
                scanned_files_count=scanned_files,
                skipped_files_count=skipped_files,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner", "secrets", "webhook", "authz", "build_type_lint", "dependency"),
                confidence_limited=False,
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.18,
            audit_status="completed",
            agent_name="verifier",
            agent_status="completed",
            agent_message="Verification complete. Demo report is ready for remediation review.",
            completion_message=(
                "TrustLayer closed the demo report with anchored findings across webhook trust, tenant exports, release safety, and frontend dependencies. Remediation should start with signed callbacks and preview-token rotation."
            ),
        ),
    ]


def _build_billing_webhooks_steps() -> list[AuditLifecycleStep]:
    frameworks = ("fastapi", "celery", "github_actions")
    return [
        AuditLifecycleStep(
            delay_seconds=0.18,
            audit_status="running",
            agent_name="planner",
            agent_status="running",
            agent_message="Tracing billing handlers, retry paths, and deploy secret handoff.",
            score_update=_demo_score_update(
                score=97,
                coverage=28,
                reason="Billing intake mapped the repo and opened webhook-focused checks.",
                coverage_detail="Repo intake mapped the payout surface, but only a narrow slice is verified so far.",
                partially_supported_areas=("API routes", "Webhooks", "Secrets / Environment"),
                unsupported_areas=("Auth / Session", "Database / Schema", "Dependencies", "Frontend Runtime", "Infrastructure", "Configuration"),
                scanned_files_count=98,
                skipped_files_count=2,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper",),
                checks_skipped=("planner", "secrets", "webhook", "build_type_lint", "dependency"),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.24,
            agent_name="planner",
            agent_status="completed",
            agent_message="Planner scoped the run to secrets, signed callbacks, and payout mutations.",
            score_update=_demo_score_update(
                score=95,
                coverage=39,
                reason="Planner narrowed the billing run into concrete callback and secret lanes.",
                coverage_detail="Billing surfaces are mapped and queued. Findings still need anchored evidence.",
                partially_supported_areas=("API routes", "Webhooks", "Secrets / Environment", "Configuration"),
                unsupported_areas=("Auth / Session", "Database / Schema", "Dependencies", "Frontend Runtime", "Infrastructure"),
                scanned_files_count=98,
                skipped_files_count=2,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner"),
                checks_skipped=("secrets", "webhook", "build_type_lint", "dependency"),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.2,
            agent_name="scanner",
            agent_status="running",
            agent_message="Scanner is checking webhook trust boundaries and release-secret exposure.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.28,
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
            score_update=_demo_score_update(
                score=82,
                coverage=59,
                reason="Secret handling on the billing path lowered the score before payout verification completed.",
                coverage_detail="Secret hygiene is evidence-backed, but payout callback verification still carries most of the remaining risk.",
                supported_areas=("Secrets / Environment", "Configuration"),
                partially_supported_areas=("API routes", "Webhooks", "Dependencies"),
                unsupported_areas=("Auth / Session", "Database / Schema", "Frontend Runtime", "Infrastructure"),
                scanned_files_count=98,
                skipped_files_count=2,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner", "secrets"),
                checks_skipped=("webhook", "build_type_lint", "dependency"),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.32,
            finding=SimulatedFindingSpec(
                severity="critical",
                title="Payout webhook skips signature validation on retry paths",
                summary=(
                    "Retry handling falls back to raw payload processing without checking the provider "
                    "signature, creating a credible forged-event path into payout state changes."
                ),
                file_path="services/webhooks/payouts.py",
                line=58,
            ),
            score_update=_demo_score_update(
                score=52,
                coverage=86,
                reason="Payout retries can be influenced by unsigned traffic, pushing the billing audit into a red state.",
                coverage_detail="Billing callback coverage is deep enough for remediation handoff. Dependency review stayed secondary in this run.",
                supported_areas=("API routes", "Webhooks", "Secrets / Environment", "Configuration"),
                partially_supported_areas=("Dependencies", "Infrastructure"),
                unsupported_areas=("Auth / Session", "Database / Schema", "Frontend Runtime"),
                scanned_files_count=98,
                skipped_files_count=2,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner", "secrets", "webhook", "build_type_lint"),
                checks_skipped=("dependency",),
                confidence_limited=False,
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.18,
            agent_name="scanner",
            agent_status="completed",
            agent_message="Billing scan complete. Verifier accepted the payout signature failure as reportable.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.16,
            audit_status="completed",
            agent_name="verifier",
            agent_status="completed",
            agent_message="Verifier finalized the billing report and left the payout path in a critical state.",
            completion_message=(
                "TrustLayer confirmed the billing trust boundary is not safe for forged retries. Fix signature validation on payout retries and rotate mirrored secrets before rollout."
            ),
        ),
    ]


def _build_tenant_portal_steps() -> list[AuditLifecycleStep]:
    frameworks = ("fastapi", "react")
    return [
        AuditLifecycleStep(
            delay_seconds=0.18,
            audit_status="running",
            agent_name="planner",
            agent_status="running",
            agent_message="Mapping tenant routes, admin previews, and document ownership checks.",
            score_update=_demo_score_update(
                score=96,
                coverage=27,
                reason="Portal intake mapped the main tenant-isolation surfaces.",
                coverage_detail="Tenant surfaces are mapped, but only the most exposed object and preview paths are in scope yet.",
                partially_supported_areas=("API routes", "Auth / Session", "Frontend Runtime"),
                unsupported_areas=("Database / Schema", "Webhooks", "Secrets / Environment", "Configuration", "Dependencies", "Infrastructure"),
                scanned_files_count=121,
                skipped_files_count=5,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper",),
                checks_skipped=("planner", "authz", "frontend_runtime", "dependency"),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.22,
            agent_name="planner",
            agent_status="completed",
            agent_message="Planner prioritized tenant ownership, admin previews, and shared object access.",
            score_update=_demo_score_update(
                score=94,
                coverage=38,
                reason="Planner narrowed the portal run to isolation and preview trust boundaries.",
                coverage_detail="The portal attack surface is partitioned. Evidence is still pending on the document and preview flows.",
                partially_supported_areas=("API routes", "Auth / Session", "Frontend Runtime", "Database / Schema"),
                unsupported_areas=("Webhooks", "Secrets / Environment", "Configuration", "Dependencies", "Infrastructure"),
                scanned_files_count=121,
                skipped_files_count=5,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner"),
                checks_skipped=("authz", "frontend_runtime", "dependency"),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.22,
            agent_name="scanner",
            agent_status="running",
            agent_message="Scanner is replaying tenant ownership checks and preview-origin boundaries.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.3,
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
            score_update=_demo_score_update(
                score=78,
                coverage=62,
                reason="Tenant isolation failed on a document path with sensitive records.",
                coverage_detail="The document surface is verified as risky. Preview-runtime evidence is still being assembled.",
                supported_areas=("API routes", "Auth / Session"),
                partially_supported_areas=("Database / Schema", "Frontend Runtime"),
                unsupported_areas=("Webhooks", "Secrets / Environment", "Configuration", "Dependencies", "Infrastructure"),
                scanned_files_count=121,
                skipped_files_count=5,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner", "authz"),
                checks_skipped=("frontend_runtime", "dependency"),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.28,
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
            score_update=_demo_score_update(
                score=67,
                coverage=88,
                reason="Frontend preview trust stayed weak after origin validation failed.",
                coverage_detail="Portal coverage is strong across auth, object access, and preview runtime. Webhooks and infra were not part of this replay.",
                supported_areas=("API routes", "Auth / Session", "Database / Schema", "Frontend Runtime"),
                partially_supported_areas=("Dependencies",),
                unsupported_areas=("Webhooks", "Secrets / Environment", "Configuration", "Infrastructure"),
                scanned_files_count=121,
                skipped_files_count=5,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner", "authz", "frontend_runtime"),
                checks_skipped=("dependency",),
                confidence_limited=False,
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.18,
            audit_status="completed",
            agent_name="verifier",
            agent_status="completed",
            agent_message="Verifier confirmed the tenant-boundary and preview-runtime issues.",
            completion_message=(
                "TrustLayer closed the tenant-portal report with confirmed isolation gaps on customer documents and the admin preview runtime. Lock tenant ownership and trusted preview origins before shipping."
            ),
        ),
    ]


def _build_ui_release_steps() -> list[AuditLifecycleStep]:
    frameworks = ("nextjs", "storybook", "github_actions")
    return []


def _build_ops_runner_steps() -> list[AuditLifecycleStep]:
    frameworks = ("python", "docker", "github_actions")
    return []
