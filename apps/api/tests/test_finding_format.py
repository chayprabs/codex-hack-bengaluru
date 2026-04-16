from __future__ import annotations

import unittest

from support import ensure_api_path

ensure_api_path()

from app.agents import AgentFinding  # noqa: E402
from app.models import Finding  # noqa: E402


class FindingFormatTests(unittest.TestCase):
    def test_agent_finding_generates_short_impact_summary_and_preserves_technical_summary(self) -> None:
        finding = AgentFinding(
            severity="high",
            title="Order route looks up records directly by id",
            summary="The route loads Order by id from the database without checking that owner_id matches the active user.",
            rule_id="idor_candidate",
            file_path="app/routes/orders.py",
            line_start=14,
        )

        self.assertEqual(
            finding.impact_summary,
            "Users may be able to access another user's record by changing an ID.",
        )
        self.assertEqual(
            finding.technical_summary,
            "The route loads Order by id from the database without checking that owner_id matches the active user.",
        )
        self.assertEqual(finding.summary, finding.technical_summary)

    def test_audit_finding_upgrade_keeps_technical_detail_separate_from_impact(self) -> None:
        finding = Finding.model_validate(
            {
                "title": "Webhook signature check is missing",
                "summary": "Webhook handler updates billing state before verifying the provider signature header.",
                "check_id": "missing_signature_verification",
                "file_path": "app/routes/webhooks.py",
                "line": 24,
            }
        )

        payload = finding.model_dump(mode="json")
        self.assertEqual(
            payload["impact_summary"],
            "A forged webhook could trigger state changes without a trusted signature.",
        )
        self.assertEqual(
            payload["technical_summary"],
            "Webhook handler updates billing state before verifying the provider signature header.",
        )
        self.assertEqual(payload["files"], ["app/routes/webhooks.py"])
        self.assertEqual(payload["line_hints"], ["24"])


if __name__ == "__main__":
    unittest.main()
