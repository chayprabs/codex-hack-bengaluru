from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from .base import BaseAgent
from .types import AgentContext, AgentResult, FindingConfidence, FindingSeverity
from .utils import (
    collect_text_files,
    read_text_file,
    resolve_agent_targets,
    resolve_repo_root,
    result_status_for_confidence,
    should_skip_analysis_path,
    trim_output,
)

WebhookFindingKind = Literal[
    "signature_verification_disabled",
    "missing_signature_verification",
    "missing_idempotency_review",
]

WEBHOOK_HINTS = ("webhook", "webhooks", "callback", "callbacks", "stripe", "slack", "github", "svix")
PROVIDER_MARKERS: dict[str, tuple[str, ...]] = {
    "stripe": ("stripe", "construct_event", "stripe-signature", "webhook"),
    "github": ("github", "x-hub-signature", "x-hub-signature-256", "webhook"),
    "slack": ("slack", "x-slack-signature", "signing secret", "webhook"),
    "svix": ("svix", "webhook", "verify"),
}
PROVIDER_VERIFY_MARKERS: dict[str, tuple[str, ...]] = {
    "stripe": ("construct_event", "stripe-signature"),
    "github": ("x-hub-signature", "x-hub-signature-256", "compare_digest", "hmac"),
    "slack": ("x-slack-signature", "signing secret", "signature"),
    "svix": ("svix.webhook", "webhook(", "verify("),
}
GENERIC_VERIFY_MARKERS = ("signature", "verify", "hmac", "compare_digest", "secret")
IDEMPOTENCY_MARKERS = ("event.id", "event_id", "delivery_id", "processed_events", "idempot", "dedupe", "upsert")
VERIFY_DISABLED_RE = re.compile(
    r"\b(?:verify_signature|signature_verification|skip_signature_verification)\b\s*[:=]\s*(?:false|0)\b",
    re.IGNORECASE,
)
ROUTE_MARKERS = ("@router.", "@app.", "router.", "app.", "export async function", "apirouter(")


class WebhookAgentError(ValueError):
    """Raised when the webhook agent cannot inspect the requested repo slice."""


class WebhookFinding(BaseModel):
    kind: WebhookFindingKind
    severity: FindingSeverity
    confidence: FindingConfidence
    title: str
    description: str
    file_path: str
    line_start: int | None = None
    evidence_excerpt: str = ""
    suggested_remediation: str


class WebhookReport(BaseModel):
    root_path: str
    scanned_files: int = 0
    scanned_targets: list[str] = Field(default_factory=list)
    findings: list[WebhookFinding] = Field(default_factory=list)


class WebhookAgent(BaseAgent):
    """Static webhook heuristics over scoped callback handlers and config."""

    name = "webhook"
    description = "Looks for webhook verification gaps and weak idempotency signals in mapped webhook slices."
    repo_map_inputs = ("webhooks", "routes", "auth", "config", "env")

    def __init__(self, *, max_files: int = 50, max_findings: int = 20) -> None:
        self.max_files = max_files
        self.max_findings = max_findings

    async def run(self, context: AgentContext) -> AgentResult:
        try:
            report = self.analyze_context(context)
        except WebhookAgentError as exc:
            return self.result(status="failed", summary=str(exc))

        findings = [
            self.finding(
                title=item.title,
                summary=item.description,
                severity=item.severity,
                confidence=item.confidence,
                file_path=item.file_path,
                line_start=item.line_start,
                line_end=item.line_start,
                rule_id=item.kind,
                category=self.agent_name,
                inputs=self.repo_map_inputs,
                checks=[item.kind],
                evidence=[
                    self.evidence(
                        kind="route",
                        summary=item.title,
                        file_path=item.file_path,
                        line_start=item.line_start,
                        line_end=item.line_start,
                        excerpt=item.evidence_excerpt or None,
                    )
                ],
                patch_suggestion=self.patch_suggestion(
                    strategy=self._patch_strategy(item.kind),
                    summary=item.suggested_remediation,
                    changes=[
                        self.patch_change(
                            file_path=item.file_path,
                            summary=item.suggested_remediation,
                            action="review" if item.confidence == "low" else "edit",
                        )
                    ],
                ),
                metadata={
                    "confidence": item.confidence,
                    "evidence_excerpt": item.evidence_excerpt,
                    "suggested_remediation": item.suggested_remediation,
                    "kind": item.kind,
                },
            )
            for item in report.findings
        ]
        return self.result(
            status=result_status_for_confidence(
                [item.confidence for item in report.findings],
                has_targets=report.scanned_files > 0,
            ),
            summary=self._build_summary(report),
            findings=findings,
            metadata={"webhook_report": report.model_dump(mode="json")},
        )

    def analyze_context(self, context: AgentContext) -> WebhookReport:
        root = resolve_repo_root(context)
        targets = resolve_agent_targets(
            context,
            agent_names=("webhook",),
            repo_map_categories=("webhooks", "routes", "auth", "config"),
            repo_map_filter=lambda file: any(hint in file.path.lower() for hint in ("webhook", "callback", "stripe", "svix", "slack")),
            fallback_to_root=False,
        )
        targets = [target for target in targets if not should_skip_analysis_path(target.display_path)]
        files = collect_text_files(
            root,
            targets,
            max_files=self.max_files,
            skip_path_parts={"agents", "tests", "test", "docs", "examples", "__pycache__"},
        )
        findings: list[WebhookFinding] = []

        for relative_path, file_path in files:
            if should_skip_analysis_path(relative_path):
                continue
            text = read_text_file(file_path)
            if text is None:
                continue
            findings.extend(self._scan_file(relative_path, text))
            if len(findings) >= self.max_findings:
                findings = findings[: self.max_findings]
                break

        return WebhookReport(
            root_path=str(root),
            scanned_files=len(files),
            scanned_targets=[target.display_path for target in targets],
            findings=findings,
        )

    def _scan_file(self, relative_path: str, text: str) -> list[WebhookFinding]:
        lower_path = relative_path.lower()
        lower_text = text.lower()
        if not any(hint in lower_path or hint in lower_text for hint in ("webhook", "callback")):
            return []

        findings: list[WebhookFinding] = []
        findings.extend(
            self._line_matches(
                relative_path,
                text,
                VERIFY_DISABLED_RE,
                kind="signature_verification_disabled",
                severity="high",
                confidence="high",
                title="Webhook signature verification can be disabled",
                description="This file appears to support disabling webhook signature verification.",
                suggested_remediation="Remove signature bypass flags and always verify webhook signatures before processing payloads.",
            )
        )

        verification_finding = self._verification_review(relative_path, lower_text, text)
        if verification_finding is not None:
            findings.append(verification_finding)

        idempotency_finding = self._idempotency_review(relative_path, lower_text, text)
        if idempotency_finding is not None:
            findings.append(idempotency_finding)

        return findings[: self.max_findings]

    def _line_matches(
        self,
        relative_path: str,
        text: str,
        pattern: re.Pattern[str],
        *,
        kind: WebhookFindingKind,
        severity: FindingSeverity,
        confidence: FindingConfidence,
        title: str,
        description: str,
        suggested_remediation: str,
    ) -> list[WebhookFinding]:
        findings: list[WebhookFinding] = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            if not pattern.search(raw_line):
                continue
            findings.append(
                WebhookFinding(
                    kind=kind,
                    severity=severity,
                    confidence=confidence,
                    title=title,
                    description=description,
                    file_path=relative_path,
                    line_start=line_number,
                    evidence_excerpt=trim_output(raw_line, limit=180),
                    suggested_remediation=suggested_remediation,
                )
            )
        return findings

    def _verification_review(
        self,
        relative_path: str,
        lower_text: str,
        text: str,
    ) -> WebhookFinding | None:
        provider = self._provider_for_file(relative_path, lower_text)
        if provider is None:
            return None
        if any(marker in lower_text for marker in PROVIDER_VERIFY_MARKERS[provider]):
            return None
        if any(marker in lower_text for marker in GENERIC_VERIFY_MARKERS):
            return None

        line_number, excerpt = self._first_matching_line(text, PROVIDER_MARKERS[provider])
        return WebhookFinding(
            kind="missing_signature_verification",
            severity="medium",
            confidence="low",
            title="Webhook handler lacks an obvious signature verification step",
            description=(
                f"This file looks like a {provider} webhook handler, but static inspection did not find a clear signature verification marker."
            ),
            file_path=relative_path,
            line_start=line_number,
            evidence_excerpt=excerpt,
            suggested_remediation="Review this handler manually and ensure signatures are verified before processing events.",
        )

    def _idempotency_review(
        self,
        relative_path: str,
        lower_text: str,
        text: str,
    ) -> WebhookFinding | None:
        if not any(marker in lower_text for marker in ROUTE_MARKERS):
            return None
        if not any(hint in lower_text for hint in WEBHOOK_HINTS):
            return None
        if any(marker in lower_text for marker in IDEMPOTENCY_MARKERS):
            return None

        line_number, excerpt = self._first_matching_line(text, WEBHOOK_HINTS)
        return WebhookFinding(
            kind="missing_idempotency_review",
            severity="low",
            confidence="low",
            title="Webhook handler lacks an obvious idempotency marker",
            description=(
                "This webhook handler does not show a clear processed-event or delivery-id check. Static review should confirm duplicate delivery handling."
            ),
            file_path=relative_path,
            line_start=line_number,
            evidence_excerpt=excerpt,
            suggested_remediation="Review this handler manually and consider storing event or delivery IDs to make processing idempotent.",
        )

    def _provider_for_file(self, relative_path: str, lower_text: str) -> str | None:
        lower_path = relative_path.lower()
        for provider, markers in PROVIDER_MARKERS.items():
            if any(marker in lower_text or marker in lower_path for marker in markers):
                return provider
        return None

    def _first_matching_line(self, text: str, tokens: tuple[str, ...]) -> tuple[int | None, str]:
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            lower_line = raw_line.lower()
            if any(token in lower_line for token in tokens):
                return line_number, trim_output(raw_line, limit=180)
        return None, ""

    def _build_summary(self, report: WebhookReport) -> str:
        if report.scanned_files == 0:
            return "No scoped webhook files were available for inspection."
        if not report.findings:
            return f"Scanned {report.scanned_files} webhook-related files and found no obvious verification issues."
        return (
            f"Scanned {report.scanned_files} webhook-related files and produced {len(report.findings)} findings, "
            "keeping absence-based signals as review prompts."
        )

    def _patch_strategy(self, kind: WebhookFindingKind) -> str:
        if kind == "missing_idempotency_review":
            return "manual_review"
        return "add_guard"


async def run(context: AgentContext) -> AgentResult:
    return await WebhookAgent().run(context)
