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
            ],
        )

        final_audit = snapshots[-1]
        self.assertEqual(len(final_audit.findings), 2)
        self.assertEqual([finding.title for finding in final_audit.findings], [
            "Unsigned webhook path",
            "Tenant export lacks ownership check",
        ])
        self.assertEqual(
            [(finding.file_path, finding.line) for finding in final_audit.findings],
            [
                ("app/routes/webhooks.py", 24),
                ("app/routes/exports.py", 88),
            ],
        )

        self.assertEqual(len(self.events.findings), 2)
        score_payloads = [payload for _, payload in self.events.score_updates]
        self.assertEqual([payload.score for payload in score_payloads], [96, 84, 74])
        self.assertEqual([payload.previous_score for payload in score_payloads], [100, 96, 84])
        self.assertEqual([payload.delta for payload in score_payloads], [-4, -12, -10])
        self.assertTrue(all(0 <= payload.score <= 100 for payload in score_payloads))
        self.assertTrue(all(payload.reason for payload in score_payloads))

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
                "updated_at",
                "finding_count",
                "message",
            },
        )
        self.assertEqual(body["audit_id"], audit.id)
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["score"], final_audit.score)
        self.assertEqual(body["finding_count"], len(final_audit.findings))
        self.assertIsNone(body["message"])

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
