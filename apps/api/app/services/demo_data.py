from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from ..models import (
    AgentStatus,
    Audit,
    DemoFindingPreview,
    DemoProfileSummary,
    DemoSetupResponse,
    utc_now,
)
from .audit_simulation import (
    AuditLifecycleStep,
    ScoreUpdateSpec,
    SimulatedFindingSpec,
    materialize_lifecycle,
)


@dataclass(frozen=True, slots=True)
class DemoAuditProfile:
    key: str
    label: str
    repo_url: str
    summary: str
    recommended_use: str
    focus_areas: tuple[str, ...]
    match_tokens: tuple[str, ...]
    seed_minutes_ago: int | None
    steps: tuple[AuditLifecycleStep, ...]


def build_demo_profiles(primary_demo_repo_url: str) -> tuple[DemoAuditProfile, ...]:
    return (
        DemoAuditProfile(
            key="trustlayer-flagship",
            label="Acme subscriptions platform",
            repo_url=primary_demo_repo_url,
            summary="Flagship seeded story with release-secret leakage, unsigned billing webhooks, tenant export IDOR, and unsafe runtime drift.",
            recommended_use="Default live-demo path when you want the clearest score motion and strongest final report.",
            focus_areas=("Secrets", "Webhook trust", "Authz / IDOR", "Release safety", "Frontend runtime"),
            match_tokens=(),
            seed_minutes_ago=None,
            steps=tuple(_build_flagship_steps()),
        ),
        DemoAuditProfile(
            key="billing-webhooks",
            label="Billing webhooks",
            repo_url="https://github.com/trustlayer-demo/acme-billing-hooks",
            summary="Revenue-path replay focused on payout signatures, mirrored webhook secrets, and release trust around payment callbacks.",
            recommended_use="Best backup when the audience wants a tighter payments or webhook story than a live repo provides.",
            focus_areas=("Billing callbacks", "Secrets", "Webhook trust", "Release safety"),
            match_tokens=("billing", "webhook", "stripe", "payment", "hooks"),
            seed_minutes_ago=96,
            steps=tuple(_build_billing_webhooks_steps()),
        ),
        DemoAuditProfile(
            key="tenant-portal",
            label="Tenant portal",
            repo_url="https://github.com/trustlayer-demo/workspace-portal",
            summary="Tenant-isolation replay with customer-document IDOR and a preview runtime that trusts unbounded postMessage origins.",
            recommended_use="Best backup when you need a multi-tenant data exposure story instead of infra or billing risk.",
            focus_areas=("Authz / IDOR", "Tenant boundaries", "Preview runtime"),
            match_tokens=("tenant", "portal", "auth", "workspace", "account", "idor"),
            seed_minutes_ago=58,
            steps=tuple(_build_tenant_portal_steps()),
        ),
        DemoAuditProfile(
            key="ui-release-monitor",
            label="UI release monitor",
            repo_url="https://github.com/trustlayer-demo/ui-release-monitor",
            summary="Frontend-platform replay centered on release-gate bypasses and a vulnerable shared markdown runtime dependency.",
            recommended_use="Best backup when the room is more interested in CI, dependency hygiene, or frontend trust than backend exploits.",
            focus_areas=("Release safety", "Dependencies", "Frontend runtime"),
            match_tokens=("frontend", "ui", "web", "dashboard", "monorepo", "design-system"),
            seed_minutes_ago=24,
            steps=tuple(_build_ui_release_steps()),
        ),
        DemoAuditProfile(
            key="ops-runner-console",
            label="Ops runner console",
            repo_url="https://github.com/trustlayer-demo/ops-runner-console",
            summary="Execution-boundary replay showing host credential inheritance and workspace cleanup gaps inside a repo-owned runner.",
            recommended_use="Best backup when you need a sharper critical-risk story or a more infrastructure-flavored close.",
            focus_areas=("Secrets", "Runner sandbox", "Cleanup behavior", "Infrastructure"),
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


def get_demo_profile_by_key(
    profile_key: str | None,
    *,
    primary_demo_repo_url: str,
) -> DemoAuditProfile | None:
    profiles = build_demo_profiles(primary_demo_repo_url)
    if profile_key is None:
        return profiles[0]

    normalized_key = profile_key.strip().lower()
    if not normalized_key:
        return profiles[0]

    for profile in profiles:
        if profile.key == normalized_key:
            return profile

    return None


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


def build_demo_setup(primary_demo_repo_url: str) -> DemoSetupResponse:
    profiles = build_demo_profiles(primary_demo_repo_url)
    return DemoSetupResponse(
        primary_demo_repo_url=primary_demo_repo_url,
        stream_backup_summary=(
            "If the live SSE stream hiccups, the audit room automatically switches to replay sync and keeps polling fresh snapshots so the story can continue."
        ),
        boring_repo_backup_summary=(
            "If a real repo stays quiet, jump into one of the seeded backup stories below. Each one keeps coherent findings, visible score motion, and a strong final report."
        ),
        profiles=[_build_demo_profile_summary(profile) for profile in profiles],
    )


def _build_demo_profile_summary(profile: DemoAuditProfile) -> DemoProfileSummary:
    score_journey = _journey_values(profile.steps, kind="score", baseline=100)
    coverage_journey = _journey_values(profile.steps, kind="coverage", baseline=12)
    preview_findings = [
        DemoFindingPreview(severity=step.finding.severity, title=step.finding.title)
        for step in profile.steps
        if step.finding is not None
    ]
    completion_message = next(
        (step.completion_message for step in reversed(profile.steps) if step.completion_message),
        None,
    )

    return DemoProfileSummary(
        key=profile.key,
        label=profile.label,
        repo_url=profile.repo_url,
        is_flagship=profile.seed_minutes_ago is None,
        summary=profile.summary,
        recommended_use=profile.recommended_use,
        focus_areas=list(profile.focus_areas),
        score_journey=score_journey,
        coverage_journey=coverage_journey,
        preview_findings=preview_findings,
        finding_count=len(preview_findings),
        final_score=score_journey[-1] if score_journey else 100,
        final_coverage=coverage_journey[-1] if coverage_journey else 12,
        completion_message=completion_message,
    )


def _journey_values(
    steps: tuple[AuditLifecycleStep, ...],
    *,
    kind: str,
    baseline: int,
) -> list[int]:
    journey = [baseline]

    for step in steps:
        score_update = step.score_update
        if score_update is None:
            continue

        if kind == "score":
            next_value = score_update.score
        else:
            if score_update.coverage is None:
                continue
            next_value = score_update.coverage

        if journey[-1] != next_value:
            journey.append(next_value)

    return journey


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
                agent_name="scanner",
                check_name="secrets",
                impact_summary="Release automation still depends on a long-lived preview token pattern that weakens secret rotation and makes copy-paste reuse likely.",
                evidence_snippet="env: PREVIEW_DEPLOY_TOKEN: ${{ secrets.PREVIEW_DEPLOY_TOKEN }}",
                suggested_patch="Move preview deploys onto short-lived environment-scoped credentials and remove long-lived token references from checked-in workflow examples.",
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
                agent_name="scanner",
                check_name="webhook_signature",
                impact_summary="Billing state can be influenced before the callback signature is verified, which leaves subscription and invoice flows open to forged webhook traffic.",
                evidence_snippet="process_billing_event(body) executes before verify_signature(signature, body)",
                confidence="high",
                proof_type="runtime_check",
                suggested_patch="Reject missing or invalid signatures before parsing the payload or mutating billing state, then replay the callback path under verifier control.",
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
                agent_name="scanner",
                check_name="authz_idor",
                impact_summary="The export path authenticates the session but still trusts caller-supplied workspace scope, leaving a tenant-boundary gap on invoice exports.",
                evidence_snippet='workspace = load_workspace(request.query_params["workspace_id"])',
                suggested_patch="Resolve the workspace from the authenticated session or re-check membership before loading or exporting invoice data.",
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
                agent_name="verifier",
                check_name="build_type_lint",
                impact_summary="The hotfix path can ship around the quality gates that are supposed to catch broken guards before release.",
                evidence_snippet="if: github.event.inputs.skip_checks == 'true'",
                proof_type="manual_review_recommendation",
                suggested_patch="Reinstate blocking typecheck and lint gates before packaging hotfix artifacts, even for emergency releases.",
                verification_state="manual_review",
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
                agent_name="verifier",
                check_name="dependency_runtime",
                impact_summary="The preview runtime still permits a markdown renderer range with a script-injection advisory, keeping the room out of green even after the main app findings are mapped.",
                evidence_snippet='"markdown-renderer": "^3.4.0"',
                suggested_patch="Pin the markdown renderer to the patched range, rebuild the preview surface, and rerun verification before trusting the final TrustScore.",
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
    return [
        AuditLifecycleStep(
            delay_seconds=0.16,
            audit_status="running",
            agent_name="planner",
            agent_status="running",
            agent_message="Indexing workspace packages, release jobs, and shared frontend runtime code.",
            score_update=_demo_score_update(
                score=97,
                coverage=29,
                reason="UI platform intake mapped the release path and shared runtime dependencies.",
                coverage_detail="The monorepo release surface is mapped, but build and dependency evidence is still shallow.",
                partially_supported_areas=("Configuration", "Dependencies", "Frontend Runtime"),
                unsupported_areas=("API routes", "Auth / Session", "Database / Schema", "Webhooks", "Secrets / Environment", "Infrastructure"),
                scanned_files_count=147,
                skipped_files_count=9,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper",),
                checks_skipped=("planner", "build_type_lint", "dependency", "typelint"),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.2,
            agent_name="planner",
            agent_status="completed",
            agent_message="Planner prioritized CI quality gates and vulnerable frontend dependency ranges.",
            score_update=_demo_score_update(
                score=95,
                coverage=41,
                reason="Planner narrowed the UI audit to release gating and dependency trust.",
                coverage_detail="Release jobs and runtime dependencies are in scope. App-level server routes were not part of this replay.",
                partially_supported_areas=("Configuration", "Dependencies", "Frontend Runtime", "Infrastructure"),
                unsupported_areas=("API routes", "Auth / Session", "Database / Schema", "Webhooks", "Secrets / Environment"),
                scanned_files_count=147,
                skipped_files_count=9,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner"),
                checks_skipped=("build_type_lint", "dependency", "typelint"),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.2,
            agent_name="scanner",
            agent_status="running",
            agent_message="Scanner is checking build gates, type safety, and shared markdown runtime risk.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.28,
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
            score_update=_demo_score_update(
                score=83,
                coverage=61,
                reason="CI no longer blocks patch releases on the checks that should keep runtime regressions out.",
                coverage_detail="Release-gate evidence is anchored. Dependency review is still the bigger remaining confidence gap.",
                supported_areas=("Configuration", "Infrastructure"),
                partially_supported_areas=("Dependencies", "Frontend Runtime"),
                unsupported_areas=("API routes", "Auth / Session", "Database / Schema", "Webhooks", "Secrets / Environment"),
                scanned_files_count=147,
                skipped_files_count=9,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner", "build_type_lint", "typelint"),
                checks_skipped=("dependency",),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.28,
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
            score_update=_demo_score_update(
                score=71,
                coverage=84,
                reason="The dependency issue kept the UI platform score below green even after build checks were mapped.",
                coverage_detail="The UI release story is ready for handoff across CI, dependency, and frontend runtime surfaces. Server-side app coverage was intentionally out of scope.",
                supported_areas=("Configuration", "Dependencies", "Frontend Runtime", "Infrastructure"),
                partially_supported_areas=("Secrets / Environment",),
                unsupported_areas=("API routes", "Auth / Session", "Database / Schema", "Webhooks"),
                scanned_files_count=147,
                skipped_files_count=9,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner", "build_type_lint", "typelint", "dependency"),
                confidence_limited=False,
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.16,
            audit_status="completed",
            agent_name="verifier",
            agent_status="completed",
            agent_message="Verifier confirmed the UI release and runtime dependency findings.",
            completion_message=(
                "TrustLayer closed the UI release report with verified gaps in release gating and markdown dependency hygiene. Restore blocking checks and upgrade the shared renderer before the next patch train."
            ),
        ),
    ]


def _build_ops_runner_steps() -> list[AuditLifecycleStep]:
    frameworks = ("python", "docker", "github_actions")
    return [
        AuditLifecycleStep(
            delay_seconds=0.15,
            audit_status="running",
            agent_name="planner",
            agent_status="running",
            agent_message="Mapping runner bootstrap, workspace cleanup, and repo-owned command wrappers.",
            score_update=_demo_score_update(
                score=95,
                coverage=26,
                reason="Runner intake mapped the execution surface and high-risk bootstrap paths.",
                coverage_detail="Execution surfaces are mapped, but command and credential handling are still only partially verified.",
                partially_supported_areas=("Secrets / Environment", "Configuration", "Infrastructure"),
                unsupported_areas=("API routes", "Auth / Session", "Database / Schema", "Webhooks", "Dependencies", "Frontend Runtime"),
                scanned_files_count=89,
                skipped_files_count=3,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper",),
                checks_skipped=("planner", "secrets", "buildbreak"),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.18,
            agent_name="planner",
            agent_status="completed",
            agent_message="Planner focused the run on credential inheritance and cleanup behavior after command failure.",
            score_update=_demo_score_update(
                score=92,
                coverage=38,
                reason="Planner narrowed the runner audit to the highest-risk command surfaces.",
                coverage_detail="Bootstrap and cleanup checks are queued. Broader dependency and auth coverage was not part of this replay.",
                partially_supported_areas=("Secrets / Environment", "Configuration", "Infrastructure"),
                unsupported_areas=("API routes", "Auth / Session", "Database / Schema", "Webhooks", "Dependencies", "Frontend Runtime"),
                scanned_files_count=89,
                skipped_files_count=3,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner"),
                checks_skipped=("secrets", "buildbreak"),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.18,
            agent_name="scanner",
            agent_status="running",
            agent_message="Scanner is replaying repo-owned command wrappers and crash-path cleanup behavior.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.24,
            finding=SimulatedFindingSpec(
                severity="critical",
                title="Runner bootstrap inherits host cloud credentials into repo-owned scripts",
                summary=(
                    "The bootstrap path shells into a repo-owned wrapper while preserving ambient cloud credentials, "
                    "which turns a compromised repository into a plausible credential-execution bridge."
                ),
                file_path="runner/bootstrap.sh",
                line=31,
            ),
            score_update=_demo_score_update(
                score=58,
                coverage=57,
                reason="Credential inheritance turned the runner bootstrap into a critical trust boundary failure.",
                coverage_detail="Execution bootstrap is evidence-backed, but cleanup and broader hardening checks are still partial.",
                supported_areas=("Secrets / Environment", "Configuration"),
                partially_supported_areas=("Infrastructure",),
                unsupported_areas=("API routes", "Auth / Session", "Database / Schema", "Webhooks", "Dependencies", "Frontend Runtime"),
                scanned_files_count=89,
                skipped_files_count=3,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner", "secrets"),
                checks_skipped=("buildbreak",),
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.24,
            finding=SimulatedFindingSpec(
                severity="high",
                title="Workspace cleanup skips nested temp dirs after command failure",
                summary=(
                    "Cleanup only removes the top-level temp directory on failure, leaving nested artifacts and "
                    "captured command output behind for later runs to inspect."
                ),
                file_path="runner/workspace.py",
                line=117,
            ),
            score_update=_demo_score_update(
                score=47,
                coverage=79,
                reason="Cleanup failures kept residual workspace data in scope after runner commands crashed.",
                coverage_detail="Runner trust boundaries are strong enough for handoff, but broad repo and dependency coverage stayed intentionally limited in this seeded demo.",
                supported_areas=("Secrets / Environment", "Configuration", "Infrastructure"),
                partially_supported_areas=("Dependencies",),
                unsupported_areas=("API routes", "Auth / Session", "Database / Schema", "Webhooks", "Frontend Runtime"),
                scanned_files_count=89,
                skipped_files_count=3,
                frameworks_detected=frameworks,
                checks_run=("repo_mapper", "planner", "secrets", "buildbreak"),
                confidence_limited=True,
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.16,
            audit_status="completed",
            agent_name="verifier",
            agent_status="completed",
            agent_message="Verifier closed the runner report with critical execution-boundary findings.",
            completion_message=(
                "TrustLayer closed the runner report with critical credential-inheritance risk in bootstrap and leftover workspace artifacts after failed commands. Isolate execution credentials before trusting repo-owned wrappers."
            ),
        ),
    ]
