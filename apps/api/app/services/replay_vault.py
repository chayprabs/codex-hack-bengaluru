from __future__ import annotations

from collections.abc import Sequence

from ..models import Finding, ReplayRecord


class ReplayVaultService:
    """Synthesizes lightweight replay and regression-handoff records from findings."""

    def build_records(self, audit_id: str, findings: Sequence[Finding]) -> list[ReplayRecord]:
        records: list[ReplayRecord] = []
        for finding in findings:
            if not self._should_capture(finding):
                continue
            records.append(
                ReplayRecord(
                    id=f"replay-{finding.id}",
                    finding_id=finding.id,
                    title=finding.title,
                    finding_type=finding.check_name or finding.proof_type,
                    file_targets=list(finding.files),
                    confidence=finding.confidence,
                    proof_type=finding.proof_type,
                    verification_state=finding.verification_state,
                    proof_summary=self._proof_summary(finding),
                    verification_summary=self._verification_summary(finding),
                    suggested_regression_test=self._suggested_regression_test(finding),
                    generated_artifact_path=None,
                    readiness=self._readiness(finding),
                )
            )
        return records

    @staticmethod
    def _should_capture(finding: Finding) -> bool:
        return (
            finding.verification_state == "verified"
            or finding.severity in {"high", "critical"}
            or finding.proof_type == "exploit_succeeded"
        )

    @staticmethod
    def _readiness(finding: Finding) -> str:
        return "regression_ready" if finding.verification_state == "verified" else "needs_manual_followup"

    @staticmethod
    def _confidence_label(finding: Finding) -> str:
        if finding.confidence == "low":
            return "Review lead"
        if finding.confidence == "medium":
            return "Supported signal"
        return "Strong signal"

    @staticmethod
    def _proof_label(finding: Finding) -> str:
        if finding.proof_type == "runtime_check":
            return "from a runtime check"
        if finding.proof_type == "exploit_succeeded":
            return "from a successful exploit or replay"
        if finding.proof_type == "manual_review_recommendation":
            return "from automation that recommends manual review"
        return "from a static code or config pattern"

    def _proof_summary(self, finding: Finding) -> str:
        detail = finding.evidence_snippet or finding.impact_summary or finding.title
        return f"{self._confidence_label(finding)} {self._proof_label(finding)}. {detail}"

    @staticmethod
    def _verification_summary(finding: Finding) -> str:
        if finding.verification_state == "verified":
            return "A verifier reviewed this finding and kept it in scope. This does not mean a fix was verified."
        if finding.verification_state == "manual_review":
            return "This replay draft was kept because the finding matters, but automation left it for human review."
        if finding.verification_state == "failed":
            return "The verifier did not close this finding cleanly in the current run."
        if finding.verification_state == "in_review":
            return "Verification was still running when this replay draft was generated."
        return "No per-finding verifier closeout was published for this finding in the current run."

    def _suggested_regression_test(self, finding: Finding) -> str:
        haystack = " ".join(
            [
                finding.title,
                finding.impact_summary,
                finding.evidence_snippet or "",
                " ".join(finding.files),
                finding.check_name or "",
            ]
        ).lower()

        if self._contains_any(haystack, ("webhook", "signature", "unsigned", "callback")):
            return "Add an integration replay that rejects missing or invalid webhook signatures and still accepts a valid signed payload."
        if self._contains_any(haystack, ("secret", "token", "credential", "env", "key")):
            return "Add a repo-hygiene regression that fails on checked-in literal secrets and verifies the code now reads from environment indirection."
        if self._contains_any(haystack, ("tenant", "workspace", "ownership", "account_id", "workspace_id", "idor")):
            return "Add an authorization regression that requests another tenant's resource and expects denial or an empty scoped result."
        if self._contains_any(haystack, ("cors", "header", "debug", "origin", "postmessage")):
            return "Add a configuration regression that locks production origins, security headers, and debug-style runtime flags to approved values."
        if self._contains_any(haystack, ("dependency", "package", "renderer", "markdown", "version")):
            return "Add dependency policy coverage that enforces the patched package range and a smoke test for the risky runtime path."
        if self._contains_any(haystack, ("lint", "typecheck", "workflow", "pipeline", "release", "build")):
            return "Add CI regression coverage that blocks packaging whenever lint, typecheck, or equivalent safety gates are skipped or reordered."
        if self._contains_any(haystack, ("cleanup", "temp", "artifact", "workspace")):
            return "Add a failure-path regression that leaves nested temp output behind in the old behavior and proves cleanup removes it after the fix."
        return "Add a focused regression for the vulnerable path, assert the unsafe behavior is blocked, and keep the check linked to this finding."

    @staticmethod
    def _contains_any(value: str, patterns: Sequence[str]) -> bool:
        return any(pattern in value for pattern in patterns)


replay_vault_service = ReplayVaultService()
