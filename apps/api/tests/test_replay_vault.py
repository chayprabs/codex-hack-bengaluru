from __future__ import annotations

import unittest

from support import ensure_api_path

ensure_api_path()

from app.models import Finding
from app.services.replay_vault import replay_vault_service


class ReplayVaultTests(unittest.TestCase):
    def test_verified_finding_becomes_regression_ready(self) -> None:
        finding = Finding(
            id="finding-webhook",
            severity="high",
            title="Unsigned webhook path",
            check_name="webhook_signature",
            files=["app/routes/webhooks.py"],
            impact_summary="Webhook processing starts before trust is established.",
            evidence_snippet="verify_signature() is called after the event body is processed.",
            proof_type="runtime_check",
            verification_state="verified",
        )

        records = replay_vault_service.build_records("audit-1", [finding])

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].id, "replay-finding-webhook")
        self.assertEqual(records[0].readiness, "regression_ready")
        self.assertEqual(records[0].finding_type, "webhook_signature")
        self.assertEqual(records[0].confidence, "high")
        self.assertEqual(records[0].proof_type, "runtime_check")
        self.assertEqual(records[0].verification_state, "verified")
        self.assertIn("This does not mean a fix was verified", records[0].verification_summary)
        self.assertIn("rejects missing or invalid webhook signatures", records[0].suggested_regression_test)

    def test_important_manual_review_finding_stays_in_followup_state(self) -> None:
        finding = Finding(
            id="finding-bootstrap",
            severity="critical",
            title="Runner bootstrap inherits host cloud credentials",
            check_name="credential_inheritance",
            files=["runner/bootstrap.sh"],
            impact_summary="Repo-owned bootstrap code still receives ambient cloud credentials.",
            proof_type="manual_review_recommendation",
            verification_state="manual_review",
        )

        records = replay_vault_service.build_records("audit-2", [finding])

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].readiness, "needs_manual_followup")
        self.assertIn("human review", records[0].verification_summary.lower())

    def test_low_unverified_finding_is_not_added_to_replay_vault(self) -> None:
        finding = Finding(
            id="finding-low",
            severity="low",
            title="Debug header leaked build metadata",
            check_name="debug_header",
            files=["app/main.py"],
            impact_summary="A debug header disclosed build metadata.",
            verification_state="unverified",
        )

        records = replay_vault_service.build_records("audit-3", [finding])

        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
