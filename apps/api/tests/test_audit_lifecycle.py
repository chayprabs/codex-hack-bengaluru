from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from uuid import uuid4
from unittest.mock import patch

from support import ensure_api_path

ensure_api_path()

from app.db import DatabaseRuntime
from app.models import Audit
from app.services.audit_runner import AuditRunner
from app.services.audit_simulation import AuditLifecycleStep, ScoreUpdateSpec, SimulatedFindingSpec


@dataclass
class PublishedEvents:
    agent_statuses: list[tuple[str, object]] = field(default_factory=list)
    findings: list[tuple[str, object]] = field(default_factory=list)
    score_updates: list[tuple[str, object]] = field(default_factory=list)
    completions: list[tuple[str, object]] = field(default_factory=list)


class AuditLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = DatabaseRuntime("memory://")
        self.repository = self.runtime.audit_repository
        self.runner = AuditRunner(repository=self.repository)
        self.events = PublishedEvents()
        self.publishers = [
            patch(
                "app.services.audit_runner.publish_agent_status",
                side_effect=lambda audit_id, payload: self.events.agent_statuses.append(
                    (audit_id, payload)
                ),
            ),
            patch(
                "app.services.audit_runner.publish_finding",
                side_effect=lambda audit_id, payload: self.events.findings.append((audit_id, payload)),
            ),
            patch(
                "app.services.audit_runner.publish_score_update",
                side_effect=lambda audit_id, payload: self.events.score_updates.append(
                    (audit_id, payload)
                ),
            ),
            patch(
                "app.services.audit_runner.publish_audit_complete",
                side_effect=lambda audit_id, payload: self.events.completions.append(
                    (audit_id, payload)
                ),
            ),
        ]

        for publisher in self.publishers:
            publisher.start()
            self.addCleanup(publisher.stop)

    def test_audit_lifecycle_transitions_through_expected_states(self) -> None:
        audit = self._seed_audit()
        snapshots = self._run_steps(
            audit.id,
            [
                AuditLifecycleStep(
                    delay_seconds=0,
                    audit_status="running",
                    agent_name="planner",
                    agent_status="running",
                    agent_message="Planning started.",
                    score_update=ScoreUpdateSpec(
                        score=96,
                        reason="Initial planning set the first baseline.",
                    ),
                ),
                AuditLifecycleStep(
                    delay_seconds=0,
                    agent_name="planner",
                    agent_status="completed",
                    agent_message="Planning complete.",
                ),
                AuditLifecycleStep(
                    delay_seconds=0,
                    agent_name="scanner",
                    agent_status="running",
                    agent_message="Scanning started.",
                ),
                AuditLifecycleStep(
                    delay_seconds=0,
                    finding=SimulatedFindingSpec(
                        severity="high",
                        title="Unsigned webhook path",
                        summary="Webhook processing starts before trust is established.",
                        file_path="app/routes/webhooks.py",
                        line=24,
                    ),
                    score_update=ScoreUpdateSpec(
                        score=84,
                        reason="A high-impact transport finding reduced the score.",
                    ),
                ),
                AuditLifecycleStep(
                    delay_seconds=0,
                    agent_name="scanner",
                    agent_status="completed",
                    agent_message="Scan complete.",
                ),
                AuditLifecycleStep(
                    delay_seconds=0,
                    agent_name="verifier",
                    agent_status="running",
                    agent_message="Verification started.",
                ),
                AuditLifecycleStep(
                    delay_seconds=0,
                    finding=SimulatedFindingSpec(
                        severity="medium",
                        title="Tenant export lacks ownership check",
                        summary="Exports trust a tenant identifier without re-checking ownership.",
                        file_path="app/routes/exports.py",
                        line=88,
                    ),
                    score_update=ScoreUpdateSpec(
                        score=74,
                        reason="Verification confirmed the tenant-boundary issue.",
                    ),
                ),
                AuditLifecycleStep(
                    delay_seconds=0,
                    audit_status="completed",
                    agent_name="verifier",
                    agent_status="completed",
                    agent_message="Verification complete.",
                ),
            ],
        )

        states = [audit.status, *[snapshot.status for snapshot in snapshots]]
        self.assertEqual(states[0], "queued")
        self.assertEqual(states[1], "running")
        self.assertTrue(all(state in {"queued", "running", "completed"} for state in states))
        self.assertEqual(states[-1], "completed")

        final_audit = snapshots[-1]
        self.assertEqual(final_audit.score, 74)
        self.assertEqual(
            {agent.name: agent.status for agent in final_audit.agents},
            {
                "planner": "completed",
                "scanner": "completed",
                "verifier": "completed",
            },
        )
        self.assertEqual([finding.verification_state for finding in final_audit.findings], ["unverified", "unverified"])
        self.assertEqual(len(final_audit.replay_records), 1)
        self.assertEqual(final_audit.replay_records[0].readiness, "needs_manual_followup")

    def test_agent_status_payloads_are_shaped_correctly(self) -> None:
        audit = self._seed_audit()
        self._run_steps(
            audit.id,
            [
                AuditLifecycleStep(
                    delay_seconds=0,
                    audit_status="running",
                    agent_name="planner",
                    agent_status="running",
                    agent_message="Planning started.",
                ),
                AuditLifecycleStep(
                    delay_seconds=0,
                    agent_name="planner",
                    agent_status="completed",
                    agent_message="Planning complete.",
                ),
                AuditLifecycleStep(
                    delay_seconds=0,
                    agent_name="verifier",
                    agent_status="completed",
                    agent_message="Verification complete.",
                ),
            ],
        )

        self.assertGreaterEqual(len(self.events.agent_statuses), 3)
        for published_audit_id, payload in self.events.agent_statuses:
            body = payload.model_dump(mode="json")
            self.assertEqual(published_audit_id, audit.id)
            self.assertEqual(set(body), {"audit_id", "name", "status", "message", "updated_at"})
            self.assertEqual(body["audit_id"], audit.id)
            self.assertIn(body["name"], {"planner", "scanner", "verifier"})
            self.assertIn(body["status"], {"queued", "running", "completed", "failed"})
            self.assertIsInstance(body["message"], str)
            self.assertTrue(body["updated_at"])

    def test_findings_are_appended_and_score_updates_are_sane(self) -> None:
        audit = self._seed_audit()
        snapshots = self._run_steps(
            audit.id,
            [
                AuditLifecycleStep(
                    delay_seconds=0,
                    audit_status="running",
                    agent_name="planner",
                    agent_status="running",
                    agent_message="Planning started.",
                    score_update=ScoreUpdateSpec(
                        score=96,
                        coverage=24,
                        reason="Initial planning set the first baseline.",
                        supported_areas=("API routes",),
                        partially_supported_areas=("Auth / Session",),
                        unsupported_areas=("Dependencies", "Infrastructure"),
                        scanned_files_count=12,
                        skipped_files_count=1,
                        frameworks_detected=("fastapi",),
                        checks_run=("repo_mapper",),
                        checks_skipped=("dependency",),
                    ),
                ),
                AuditLifecycleStep(
                    delay_seconds=0,
                    finding=SimulatedFindingSpec(
                        severity="high",
                        title="Unsigned webhook path",
                        summary="Webhook processing starts before trust is established.",
                        file_path="app/routes/webhooks.py",
                        line=24,
                    ),
                    score_update=ScoreUpdateSpec(
                        score=84,
                        coverage=58,
                        reason="A high-impact transport finding reduced the score.",
                        supported_areas=("API routes", "Webhooks"),
                        partially_supported_areas=("Auth / Session",),
                        unsupported_areas=("Dependencies", "Infrastructure"),
                        scanned_files_count=28,
                        skipped_files_count=2,
                        frameworks_detected=("fastapi", "nextjs"),
                        checks_run=("repo_mapper", "webhook"),
                        checks_skipped=("dependency",),
                    ),
                ),
                AuditLifecycleStep(
                    delay_seconds=0,
                    finding=SimulatedFindingSpec(
                        severity="medium",
                        title="Tenant export lacks ownership check",
                        summary="Exports trust a tenant identifier without re-checking ownership.",
                        file_path="app/routes/exports.py",
                        line=88,
                    ),
                    score_update=ScoreUpdateSpec(
                        score=74,
                        coverage=81,
                        reason="Verification confirmed the tenant-boundary issue.",
                        coverage_summary="Coverage is 81/100 (broad). Planner, scanner, and verifier all contributed evidence.",
                        confidence_limited=False,
                        supported_areas=("API routes", "Auth / Session", "Webhooks"),
                        partially_supported_areas=("Dependencies",),
                        unsupported_areas=("Infrastructure",),
                        scanned_files_count=42,
                        skipped_files_count=3,
                        frameworks_detected=("fastapi", "nextjs"),
                        checks_run=("repo_mapper", "webhook", "authz"),
                        checks_skipped=("build_type_lint",),
                    ),
                ),
            ],
        )

        final_audit = snapshots[-1]
        self.assertEqual(len(final_audit.findings), 2)
        self.assertEqual([finding.title for finding in final_audit.findings], [
            "Unsigned webhook path",
            "Tenant export lacks ownership check",
        ])
        self.assertEqual(
            [(finding.files, finding.line_hints) for finding in final_audit.findings],
            [
                (["app/routes/webhooks.py"], ["24"]),
                (["app/routes/exports.py"], ["88"]),
            ],
        )
        self.assertEqual(
            [(finding.impact_summary, finding.verification_state) for finding in final_audit.findings],
            [
                ("Webhook processing starts before trust is established.", "unverified"),
                ("Exports trust a tenant identifier without re-checking ownership.", "unverified"),
            ],
        )

        self.assertEqual(len(self.events.findings), 2)
        score_payloads = [payload for _, payload in self.events.score_updates]
        self.assertEqual([payload.score for payload in score_payloads], [96, 84, 74])
        self.assertEqual([payload.previous_score for payload in score_payloads], [100, 96, 84])
        self.assertEqual([payload.delta for payload in score_payloads], [-4, -12, -10])
        self.assertEqual([payload.coverage for payload in score_payloads], [24, 58, 81])
        self.assertTrue(all(0 <= payload.coverage <= 100 for payload in score_payloads))
        self.assertTrue(
            all(
                payload.coverage_band in {"minimal", "limited", "targeted", "broad", "deep"}
                for payload in score_payloads
            )
        )
        self.assertTrue(all(0 <= payload.score <= 100 for payload in score_payloads))
        self.assertTrue(all(payload.reason for payload in score_payloads))
        self.assertEqual(final_audit.coverage, 81)
        self.assertEqual(final_audit.supported_areas, ["API routes", "Auth / Session", "Webhooks"])
        self.assertEqual(final_audit.partially_supported_areas, ["Dependencies"])
        self.assertEqual(final_audit.unsupported_areas, ["Infrastructure"])
        self.assertEqual(final_audit.scanned_files_count, 42)
        self.assertEqual(final_audit.skipped_files_count, 3)
        self.assertEqual(final_audit.frameworks_detected, ["fastapi", "nextjs"])
        self.assertEqual(final_audit.checks_run, ["repo_mapper", "webhook", "authz"])
        self.assertEqual(final_audit.checks_skipped, ["build_type_lint"])
        self.assertFalse(final_audit.confidence_limited)
        self.assertEqual(final_audit.replay_records, [])

    def test_finding_events_include_short_impact_and_expanded_technical_detail(self) -> None:
        audit = self._seed_audit()
        snapshots = self._run_steps(
            audit.id,
            [
                AuditLifecycleStep(
                    delay_seconds=0,
                    audit_status="running",
                    finding=SimulatedFindingSpec(
                        severity="high",
                        title="Unsigned webhook path",
                        summary="Webhook handler marks orders as paid before verifying the provider signature header.",
                        impact_summary="A forged payment webhook could mark unpaid orders as paid.",
                        file_path="app/routes/webhooks.py",
                        line=24,
                    ),
                ),
            ],
        )

        final_audit = snapshots[-1]
        self.assertEqual(final_audit.findings[0].impact_summary, "A forged payment webhook could mark unpaid orders as paid.")
        self.assertEqual(
            final_audit.findings[0].technical_summary,
            "Webhook handler marks orders as paid before verifying the provider signature header.",
        )

        published_audit_id, payload = self.events.findings[0]
        body = payload.model_dump(mode="json")
        self.assertEqual(published_audit_id, audit.id)
        self.assertEqual(body["impact_summary"], "A forged payment webhook could mark unpaid orders as paid.")
        self.assertEqual(
            body["technical_summary"],
            "Webhook handler marks orders as paid before verifying the provider signature header.",
        )

    def test_audit_completion_payload_exists(self) -> None:
        audit = self._seed_audit()
        snapshots = self._run_steps(
            audit.id,
            [
                AuditLifecycleStep(
                    delay_seconds=0,
                    audit_status="running",
                    agent_name="planner",
                    agent_status="running",
                    agent_message="Planning started.",
                    score_update=ScoreUpdateSpec(
                        score=96,
                        reason="Initial planning set the first baseline.",
                    ),
                ),
                AuditLifecycleStep(
                    delay_seconds=0,
                    finding=SimulatedFindingSpec(
                        severity="high",
                        title="Unsigned webhook path",
                        summary="Webhook processing starts before trust is established.",
                        file_path="app/routes/webhooks.py",
                        line=24,
                    ),
                    score_update=ScoreUpdateSpec(
                        score=84,
                        reason="A high-impact transport finding reduced the score.",
                    ),
                ),
                AuditLifecycleStep(
                    delay_seconds=0,
                    audit_status="completed",
                    agent_name="verifier",
                    agent_status="completed",
                    agent_message="Verification complete.",
                    completion_message="Verification complete. Demo report ready.",
                ),
            ],
        )

        final_audit = snapshots[-1]
        self.assertEqual(len(self.events.completions), 1)
        published_audit_id, payload = self.events.completions[0]
        body = payload.model_dump(mode="json")

        self.assertEqual(published_audit_id, audit.id)
        self.assertEqual(
            set(body),
            {
                "audit_id",
                "status",
                "repo_url",
                "score",
                "coverage",
                "coverage_percent",
                "coverage_band",
                "coverage_summary",
                "confidence_limited",
                "supported_areas",
                "partially_supported_areas",
                "unsupported_areas",
                "needs_manual_review_areas",
                "unsupported_technologies",
                "scanned_files_count",
                "skipped_files_count",
                "frameworks_detected",
                "checks_run",
                "checks_skipped",
                "replay_records",
                "updated_at",
                "finding_count",
                "message",
            },
        )
        self.assertEqual(body["audit_id"], audit.id)
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["score"], final_audit.score)
        self.assertEqual(body["coverage"], final_audit.coverage)
        self.assertEqual(body["coverage_percent"], final_audit.coverage_percent)
        self.assertEqual(body["coverage_band"], final_audit.coverage_band)
        self.assertEqual(body["finding_count"], len(final_audit.findings))
        self.assertEqual(len(body["replay_records"]), 1)
        self.assertEqual(body["message"], "Verification complete. Demo report ready.")

    def _seed_audit(self) -> Audit:
        audit = Audit(
            id=str(uuid4()),
            repo_url="https://github.com/acme/example",
            status="queued",
            score=100,
            agents=self.runner.build_initial_agents(),
        )
        return self.repository.create_audit(audit)

    def _run_steps(self, audit_id: str, steps: list[AuditLifecycleStep]) -> list[Audit]:
        snapshots: list[Audit] = []
        for step in steps:
            updated = self.runner._apply_step(audit_id, step)
            self.assertIsNotNone(updated)
            snapshots.append(updated)
        return snapshots


if __name__ == "__main__":
    unittest.main()
