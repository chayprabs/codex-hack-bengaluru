"use client";

import { useMemo, useState } from "react";

import type { FindingStory } from "@/lib/auditStory";
import { formatAuditLabel, unsupportedScopeCount } from "@/lib/coveragePresentation";
import { buildFindingBuckets } from "@/lib/findingBuckets";
import type { Audit } from "@/lib/types";
import { formatDateTime, formatScore } from "@/lib/format";
import { cn, repoLabelFromUrl, titleCase } from "@/lib/utils";
import {
  describeFindingConfidence,
  describeFindingProofType,
  describeFindingVerificationState,
  describeReplayReadiness,
  formatFindingConfidenceBadgeLabel,
  formatFindingProofBadgeLabel,
  formatFindingVerificationBadgeLabel,
  formatReplayReadinessBadgeLabel,
  StatusBadge,
} from "@/components/StatusBadge";

type EvidenceBundleCardProps = {
  audit: Audit;
  stories?: Record<string, FindingStory>;
  className?: string;
};

function dedupeStrings(values: Array<string | null | undefined>) {
  return [...new Set(values.map((value) => value?.trim()).filter(Boolean) as string[])];
}

function summarizeList(items: string[], emptyLabel = "None") {
  return items.length ? items.join(", ") : emptyLabel;
}

function cleanText(value: string | null | undefined) {
  const normalized = value?.trim();
  return normalized ? normalized : null;
}

function sameText(left: string | null | undefined, right: string | null | undefined) {
  return cleanText(left)?.toLowerCase() === cleanText(right)?.toLowerCase();
}

function verificationSummary(audit: Audit) {
  const verifier = audit.agents.find((agent) => agent.name.toLowerCase() === "verifier");
  const verifiedFindings = audit.findings.filter((finding) => finding.verification_state === "verified").length;
  const unresolvedFindings = audit.findings.length - verifiedFindings;

  if (verifier?.status === "completed") {
    if (!audit.findings.length) {
      return "Review completed and the report closed without persisted findings.";
    }

    if (verifiedFindings > 0) {
      return `Review completed. ${verifiedFindings} finding${verifiedFindings === 1 ? " was" : "s were"} individually reviewed and ${unresolvedFindings} remained unreviewed or manual-review only.`;
    }

    return "Review completed, but no finding was individually reviewed.";
  }

  if (verifier?.status === "failed") {
    return "Review failed before clean finding-level closeout was published.";
  }

  if (verifier?.status === "running") {
    return "Review was still running when this bundle was generated.";
  }

  if (audit.status === "completed") {
    return "The audit completed, but no explicit review closeout was published.";
  }

  return "No final review closeout was published.";
}

function findingVerificationLabel(finding: Audit["findings"][number], audit: Audit) {
  if (finding.verification_state) {
    return formatFindingVerificationBadgeLabel(finding.verification_state);
  }

  const verifier = audit.agents.find((agent) => agent.name.toLowerCase() === "verifier");
  if (verifier?.status === "completed") {
    return "Not verifier-reviewed";
  }

  if (verifier?.status === "running") {
    return "Verifier running";
  }

  if (audit.status === "failed") {
    return "Verification did not close";
  }

  return "Not verifier-reviewed";
}

function buildFindingAnchor(finding: Audit["findings"][number], story?: FindingStory) {
  const files = dedupeStrings([...(finding.files ?? []), finding.file_path ?? null]);
  const lineHints = dedupeStrings([...(finding.line_hints ?? []), finding.line ? String(finding.line) : null]);

  if (story?.evidenceLabel) {
    return story.evidenceLabel;
  }

  if (files.length && lineHints.length) {
    return `${files[0]}:${lineHints[0]}`;
  }

  if (files.length) {
    return files[0];
  }

  return "No explicit code location published";
}

function buildFindingEvidence(finding: Audit["findings"][number], story?: FindingStory) {
  const impactSummary = cleanText(finding.impact_summary);
  const candidates = [
    cleanText(finding.evidence_snippet),
    cleanText(finding.technical_summary),
    cleanText(finding.summary),
    cleanText(story?.currentLabel),
  ].filter((value): value is string => Boolean(value));

  return (
    candidates.find((candidate) => !sameText(candidate, impactSummary)) ??
    "Evidence was published, but no short note was attached."
  );
}

function buildFindingTechnicalDetail(finding: Audit["findings"][number], story?: FindingStory) {
  const impactSummary = cleanText(finding.impact_summary);
  const evidenceSnippet = cleanText(finding.evidence_snippet);
  const candidates = [cleanText(finding.technical_summary), cleanText(finding.summary), cleanText(story?.statusLabel)].filter(
    (value): value is string => Boolean(value),
  );

  return (
    candidates.find((candidate) => !sameText(candidate, impactSummary) && !sameText(candidate, evidenceSnippet)) ??
    "No extra technical detail was published."
  );
}

function buildFindingPatch(finding: Audit["findings"][number], story?: FindingStory) {
  return finding.suggested_patch ?? story?.suggestedPatch ?? "Fix design still needed.";
}

function buildFindingSignalSummary(finding: Audit["findings"][number]) {
  return [
    `${formatFindingConfidenceBadgeLabel(finding.confidence)}. ${describeFindingConfidence(finding.confidence)}`,
    `${formatFindingProofBadgeLabel(finding.proof_type)}. ${describeFindingProofType(finding.proof_type)}`,
    `${formatFindingVerificationBadgeLabel(finding.verification_state)}. ${describeFindingVerificationState(finding.verification_state)}`,
  ].join(" ");
}

function buildMarkdownBundle(audit: Audit, stories: Record<string, FindingStory>) {
  const replayRecordCount = audit.replay_records.length;
  const regressionReadyCount = audit.replay_records.filter((record) => record.readiness === "regression_ready").length;
  const manualReplayCount = replayRecordCount - regressionReadyCount;
  const activeBuckets = buildFindingBuckets(audit.findings).filter((bucket) => bucket.count > 0);
  const repoLabel = repoLabelFromUrl(audit.repo_url);
  const frameworkLabels = audit.frameworks_detected.map(formatAuditLabel);
  const supportedAreas = audit.supported_areas.map(formatAuditLabel);
  const partiallySupportedAreas = audit.partially_supported_areas.map(formatAuditLabel);
  const unsupportedAreas = audit.unsupported_areas.map(formatAuditLabel);
  const needsManualReviewAreas = audit.needs_manual_review_areas.map(formatAuditLabel);
  const unsupportedTechnologies = audit.unsupported_technologies.map(formatAuditLabel);
  const checksRun = audit.checks_run.map(formatAuditLabel);
  const checksSkipped = audit.checks_skipped.map(formatAuditLabel);

  const lines: string[] = [
    "# Audit Handoff",
    "",
    `- Repo: ${audit.repo_url}`,
    `- Repo label: ${repoLabel}`,
    `- Audit ID: ${audit.id}`,
    `- Audit mode: ${titleCase(audit.audit_mode)}`,
    `- Generated: ${formatDateTime(audit.updated_at)}`,
    `- Status: ${titleCase(audit.status)}`,
    "",
    "## Score",
    "",
    `- TrustScore: ${formatScore(audit.score)}/100`,
    `- Coverage: ${formatScore(audit.coverage)}/100 (${titleCase(audit.coverage_band)})`,
    `- Scope limited: ${audit.confidence_limited ? "Yes" : "No"}`,
    `- Coverage summary: ${audit.coverage_summary}`,
    "",
    "## Scope and checks",
    "",
    `- Frameworks detected: ${summarizeList(frameworkLabels)}`,
    `- Checks run: ${summarizeList(checksRun)}`,
    `- Checks skipped: ${summarizeList(checksSkipped)}`,
    `- Supported areas: ${summarizeList(supportedAreas)}`,
    `- Partially supported areas: ${summarizeList(partiallySupportedAreas)}`,
    `- Unsupported areas: ${summarizeList(unsupportedAreas)}`,
    `- Needs manual review: ${summarizeList(needsManualReviewAreas)}`,
    `- Unsupported tech: ${summarizeList(unsupportedTechnologies)}`,
    "",
    "## Review state",
    "",
    `- Overall: ${verificationSummary(audit)}`,
    `- Completion note: ${audit.completion_message ?? "No additional completion note was published."}`,
    "",
    "## Retest drafts",
    "",
    `- Total drafts: ${replayRecordCount}`,
    `- Drafts ready: ${regressionReadyCount}`,
    `- Needs manual follow-up: ${manualReplayCount}`,
    "- Note: These are handoff drafts, not executed or CI-integrated tests yet.",
    "",
    `## Risk groups (${activeBuckets.length})`,
    "",
    `## Findings (${audit.findings.length})`,
    "",
  ];

  if (!audit.replay_records.length) {
    lines.push("- No retest drafts were generated in the current report.");
    lines.push("");
  } else {
    audit.replay_records.forEach((record, index) => {
      lines.push(`### Replay ${index + 1}. ${record.title} [${formatReplayReadinessBadgeLabel(record.readiness)}]`);
      lines.push("");
      lines.push(`- Finding type: ${record.finding_type}`);
      lines.push(
        `- Source signal: ${formatFindingConfidenceBadgeLabel(record.confidence)} / ${formatFindingProofBadgeLabel(record.proof_type)} / ${formatFindingVerificationBadgeLabel(record.verification_state)}`,
      );
      lines.push(`- Files: ${summarizeList(record.file_targets)}`);
      lines.push(`- Proof note: ${record.proof_summary}`);
      lines.push(`- Verification note: ${record.verification_summary}`);
      lines.push(`- Draft status: ${describeReplayReadiness(record.readiness)}`);
      lines.push(`- Regression draft: ${record.suggested_regression_test}`);
      lines.push(`- Artifact path: ${record.generated_artifact_path ?? "Embedded in audit payload only"}`);
      lines.push("");
    });
  }

  if (!activeBuckets.length) {
    lines.push("- No bucketed summary was generated because no findings were published.");
    lines.push("");
  } else {
    activeBuckets.forEach((bucket) => {
      lines.push(`### ${bucket.label}`);
      lines.push("");
      lines.push(`- Findings: ${bucket.count}`);
      lines.push(`- Read this as: ${bucket.quickTake}`);
      lines.push(`- Start with: ${bucket.fixHint}`);
      bucket.examples.forEach((example) => {
        lines.push(`- Signal: ${example}`);
      });
      lines.push("");
    });
  }

  if (!audit.findings.length) {
    lines.push("- No findings were published in the current report.");
  } else {
    audit.findings.forEach((finding, index) => {
      const story = stories[finding.id];
      const files = dedupeStrings([...(finding.files ?? []), finding.file_path ?? null]);
      const lineHints = dedupeStrings([...(finding.line_hints ?? []), finding.line ? String(finding.line) : null]);
      const technicalDetail = buildFindingTechnicalDetail(finding, story);

      lines.push(`### ${index + 1}. ${finding.title} [${titleCase(finding.severity)}]`);
      lines.push("");
      lines.push(`- Why it matters: ${finding.impact_summary ?? finding.title}`);
      lines.push(`- Signal strength: ${formatFindingConfidenceBadgeLabel(finding.confidence)}. ${describeFindingConfidence(finding.confidence)}`);
      lines.push(`- Proof source: ${formatFindingProofBadgeLabel(finding.proof_type)}. ${describeFindingProofType(finding.proof_type)}`);
      lines.push(`- Verifier state: ${findingVerificationLabel(finding, audit)}. ${describeFindingVerificationState(finding.verification_state)}`);
      lines.push(`- Code anchor: ${buildFindingAnchor(finding, story)}`);
      lines.push(`- What was observed: ${buildFindingEvidence(finding, story)}`);
      if (technicalDetail !== "Technical detail was not published.") {
        lines.push(`- Technical note: ${technicalDetail}`);
      }
      lines.push(`- Suggested patch: ${buildFindingPatch(finding, story)}`);
      lines.push(`- Assessment summary: ${buildFindingSignalSummary(finding)}`);
      lines.push(`- Source lane: ${finding.agent_name ? titleCase(finding.agent_name) : "Not published"}`);
      lines.push(`- Check: ${finding.check_name ? titleCase(finding.check_name) : "Not published"}`);
      if (files.length > 1) {
        lines.push(`- Additional files: ${summarizeList(files.slice(1))}`);
      }
      if (lineHints.length > 1) {
        lines.push(`- Additional line hints: ${summarizeList(lineHints.slice(1))}`);
      }
      lines.push("");
    });
  }

  return lines.join("\n");
}

function bundleFilename(audit: Audit) {
  const repoToken = repoLabelFromUrl(audit.repo_url).replace(/[^\w.-]+/g, "-");
  return `${repoToken || "repo"}-audit-evidence-${audit.id.slice(0, 8)}.md`;
}

export function EvidenceBundleCard({ audit, stories = {}, className }: Readonly<EvidenceBundleCardProps>) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");
  const markdownBundle = useMemo(() => buildMarkdownBundle(audit, stories), [audit, stories]);
  const preview = useMemo(() => markdownBundle.split("\n").slice(0, 40).join("\n"), [markdownBundle]);
  const replayRecordCount = audit.replay_records.length;
  const regressionReadyCount = audit.replay_records.filter((record) => record.readiness === "regression_ready").length;
  const manualReplayCount = replayRecordCount - regressionReadyCount;

  const handleDownload = () => {
    const blob = new Blob([markdownBundle], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = bundleFilename(audit);
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(markdownBundle);
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 2000);
    } catch {
      setCopyState("error");
      window.setTimeout(() => setCopyState("idle"), 2500);
    }
  };

  return (
    <section
      className={cn(
        "rounded-[1.75rem] border border-slate-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.97),rgba(248,250,252,0.94))] p-5 shadow-sm sm:p-6",
        className,
      )}
      aria-label="Evidence bundle"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Evidence bundle</p>
          <h3 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">Shareable report</h3>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Copy or download a markdown handoff with score, scope, findings, retest drafts, and open caveats.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={handleDownload}
            className="inline-flex items-center rounded-full border border-slate-200 bg-white px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-cyan-200 hover:bg-cyan-50 hover:text-cyan-700"
          >
            Download report
          </button>
          <button
            type="button"
            onClick={() => void handleCopy()}
            className="inline-flex items-center rounded-full border border-slate-200 bg-white px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
          >
            {copyState === "copied" ? "Copied" : copyState === "error" ? "Copy failed" : "Copy report"}
          </button>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        <StatusBadge mono>{audit.findings.length} findings</StatusBadge>
        <StatusBadge mono>TrustScore {formatScore(audit.score)}</StatusBadge>
        <StatusBadge mono>Coverage {formatScore(audit.coverage)}</StatusBadge>
        <StatusBadge tone={replayRecordCount > 0 ? (manualReplayCount > 0 ? "warning" : "success") : "neutral"} mono>
          {replayRecordCount > 0 ? `${regressionReadyCount}/${replayRecordCount} retest drafts ready` : "No retest drafts"}
        </StatusBadge>
        <StatusBadge mono>{audit.audit_mode} mode</StatusBadge>
        <StatusBadge tone="success" mono>
          Supported {audit.supported_areas.length}
        </StatusBadge>
        <StatusBadge tone="warning" mono>
          Partially supported {audit.partially_supported_areas.length}
        </StatusBadge>
        <StatusBadge tone="neutral" mono>
          Unsupported {unsupportedScopeCount(audit.unsupported_areas, audit.unsupported_technologies)}
        </StatusBadge>
        <StatusBadge tone="info" mono>
          Needs manual review {audit.needs_manual_review_areas.length}
        </StatusBadge>
        <StatusBadge tone={audit.confidence_limited ? "warning" : "info"} mono>
          {audit.confidence_limited ? "Limited by scope" : "Scope covered"}
        </StatusBadge>
      </div>

      <div className="mt-6 rounded-[1.25rem] border border-slate-200 bg-slate-950 px-4 py-4 text-slate-100">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Preview</p>
          <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-slate-400">{bundleFilename(audit)}</p>
        </div>
        <pre className="mt-4 overflow-x-auto whitespace-pre-wrap font-mono text-xs leading-6 text-slate-100">{preview}</pre>
      </div>

      <p className="mt-4 text-sm leading-6 text-slate-600">
        Built from the live report so you can drop it into Slack, a PR, or notes without losing what still needs review.
      </p>
    </section>
  );
}
