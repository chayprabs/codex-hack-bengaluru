import type { Audit, AuditCompleteEvent, FindingSeverity, ScoreUpdateEvent } from "@/lib/types";
import { formatScoreDelta } from "@/lib/format";
import { formatAuditLabel, unsupportedScopeCount } from "@/lib/coveragePresentation";
import { describeAuditScoreSnapshot, describeScoreUpdate } from "@/lib/scoreNarrative";
import { cn } from "@/lib/utils";
import { StatusBadge, type StatusBadgeTone } from "@/components/StatusBadge";

type FinalReportSummaryCardProps = {
  audit: Audit;
  completionEvent: AuditCompleteEvent | null;
  scoreHistory: ScoreUpdateEvent[];
  className?: string;
};

type MergeGuidance = {
  answer: string;
  headline: string;
  detail: string;
  tone: StatusBadgeTone;
};

type ScoreDriver = {
  delta: number;
  detail: string;
};

type AnswerCard = {
  label: string;
  badgeLabel: string;
  tone: StatusBadgeTone;
  detail: string;
};

function pluralize(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

function createSeverityCounts(audit: Audit) {
  return audit.findings.reduce<Record<FindingSeverity, number>>(
    (counts, finding) => {
      counts[finding.severity] += 1;
      return counts;
    },
    { low: 0, medium: 0, high: 0, critical: 0 },
  );
}

function summarizeList(items: string[], limit = 3) {
  if (!items.length) {
    return "None";
  }

  const visible = items.slice(0, limit).map(formatAuditLabel);
  const hidden = items.length - visible.length;
  return hidden > 0 ? `${visible.join(", ")} +${hidden} more` : visible.join(", ");
}

function buildMergeGuidance({
  audit,
  criticalIssuesRemaining,
  highIssuesRemaining,
  unresolvedFindings,
  verifiedFindings,
  unsupportedAreas,
  unsupportedTechnologies,
  needsManualReviewAreas,
  skippedChecks,
}: {
  audit: Audit;
  criticalIssuesRemaining: number;
  highIssuesRemaining: number;
  unresolvedFindings: number;
  verifiedFindings: number;
  unsupportedAreas: number;
  unsupportedTechnologies: number;
  needsManualReviewAreas: number;
  skippedChecks: number;
}): MergeGuidance {
  if (audit.status === "failed") {
    return {
      answer: "No",
      headline: "Do not ship from this run",
      detail: "The audit ended before clean closeout, so this score is not enough to make a release call.",
      tone: "danger",
    };
  }

  if (criticalIssuesRemaining > 0) {
    return {
      answer: "No",
      headline: "Critical issues are still open",
      detail: `${pluralize(criticalIssuesRemaining, "critical issue")} still appear in the final report.`,
      tone: "danger",
    };
  }

  if (unresolvedFindings > 0) {
    return {
      answer: "No",
      headline: "Review is still incomplete",
      detail: `${pluralize(unresolvedFindings, "finding")} are still unreviewed or manual-review only.`,
      tone: "danger",
    };
  }

  if (audit.confidence_limited) {
    return {
      answer: "Not from this run alone",
      headline: "Scope is too thin for a ship call",
      detail: `Coverage stayed ${audit.coverage_band}, so this score should be treated as a first read until more of the repo is checked.`,
      tone: "warning",
    };
  }

  if (audit.findings.length > 0 || highIssuesRemaining > 0) {
    return {
      answer: "Not yet",
      headline: "Findings still need fixes",
      detail: `${pluralize(audit.findings.length, "finding")} remain in the final report, including ${pluralize(verifiedFindings, "finding")} that were explicitly reviewed.`,
      tone: "warning",
    };
  }

  if (unsupportedAreas > 0 || unsupportedTechnologies > 0 || needsManualReviewAreas > 0 || skippedChecks > 0) {
    const detailParts = [
      unsupportedAreas > 0 ? pluralize(unsupportedAreas, "unsupported area") : null,
      unsupportedTechnologies > 0 ? pluralize(unsupportedTechnologies, "unsupported technology") : null,
      needsManualReviewAreas + skippedChecks > 0
        ? pluralize(needsManualReviewAreas + skippedChecks, "manual-review follow-up")
        : null,
    ].filter((value): value is string => Boolean(value));
    return {
      answer: "Manual review first",
      headline: "Out-of-scope areas still need follow-up",
      detail: `${detailParts.join(", ")} are still outside automated coverage.`,
      tone: "warning",
    };
  }

  return {
    answer: "Yes, in audited scope",
    headline: "No blockers found in audited scope",
    detail: "The audit finished without persisted findings, unsupported surfaces, or limited-scope warnings.",
    tone: "success",
  };
}

function buildWhatWasVerified({
  audit,
  completionEvent,
  verifiedFindings,
  unresolvedFindings,
  replayRecordCount,
}: {
  audit: Audit;
  completionEvent: AuditCompleteEvent | null;
  verifiedFindings: number;
  unresolvedFindings: number;
  replayRecordCount: number;
}) {
  if (audit.status !== "completed") {
    return `Only partial review closed. ${pluralize(audit.checks_run.length, "check")} ran across ${pluralize(audit.supported_areas.length, "supported area")}, but the audit did not finish cleanly.`;
  }

  if (verifiedFindings > 0) {
    const replaySuffix =
      replayRecordCount > 0 ? ` ${pluralize(replayRecordCount, "retest draft")} were staged for handoff.` : "";
    const unresolvedSuffix =
      unresolvedFindings > 0
        ? ` ${pluralize(unresolvedFindings, "additional finding")} remained unverified or manual-review only.`
        : "";
    return `${pluralize(verifiedFindings, "finding")} were individually reviewed and kept in scope. ${pluralize(audit.checks_run.length, "check")} ran across ${pluralize(audit.supported_areas.length, "supported area")}.${replaySuffix}${unresolvedSuffix}`;
  }

  if (completionEvent?.finding_count === 0 || audit.findings.length === 0) {
    return `${pluralize(audit.checks_run.length, "check")} ran and review closed without persisted findings in this report.`;
  }

  return "Review finished, but no finding was individually reviewed. Remaining findings should be treated as unreviewed or manual-review signals.";
}

function buildManualReviewSummary({
  audit,
  unresolvedFindings,
  verifiedFindings,
  criticalIssuesRemaining,
  needsManualReviewAreas,
}: {
  audit: Audit;
  unresolvedFindings: number;
  verifiedFindings: number;
  criticalIssuesRemaining: number;
  needsManualReviewAreas: number;
}) {
  const items: string[] = [];

  if (criticalIssuesRemaining > 0) {
    items.push(`${pluralize(criticalIssuesRemaining, "critical issue")} remain open`);
  }

  if (verifiedFindings > 0) {
    items.push(`${pluralize(verifiedFindings, "reviewed finding")} remain in the report and still need remediation work`);
  }

  if (unresolvedFindings > 0) {
    items.push(`${pluralize(unresolvedFindings, "finding")} still lack per-finding verifier review`);
  }

  if (audit.checks_skipped.length > 0) {
    items.push(`${pluralize(audit.checks_skipped.length, "check")} were skipped`);
  }

  if (needsManualReviewAreas > 0) {
    items.push(`needs manual review: ${summarizeList(audit.needs_manual_review_areas)}`);
  }

  if (audit.confidence_limited) {
    items.push(`coverage stayed ${audit.coverage_band}, so scope is still limited`);
  }

  if (!items.length) {
    return "No additional manual-review blockers were called out by the current audit signals.";
  }

  return items.join(". ") + ".";
}

function buildUnsupportedSummary(audit: Audit) {
  if (audit.unsupported_areas.length > 0 || audit.unsupported_technologies.length > 0) {
    const parts: string[] = [];
    if (audit.unsupported_areas.length > 0) {
      parts.push(`Unsupported areas: ${summarizeList(audit.unsupported_areas)}`);
    }
    if (audit.unsupported_technologies.length > 0) {
      parts.push(`Unsupported tech: ${summarizeList(audit.unsupported_technologies)}`);
    }
    return parts.join(". ") + ".";
  }

  if (audit.checks_skipped.length > 0) {
    return `No explicit unsupported surface tags, but ${pluralize(audit.checks_skipped.length, "check")} were skipped: ${summarizeList(audit.checks_skipped)}.`;
  }

  return "No unsupported areas were reported in this run.";
}

function buildRegressionReadySummary({
  replayRecordCount,
  regressionReadyCount,
  manualReplayCount,
}: {
  replayRecordCount: number;
  regressionReadyCount: number;
  manualReplayCount: number;
}) {
  if (!replayRecordCount) {
    return "No retest drafts were generated yet. These only appear for reviewed or especially important findings.";
  }

  if (manualReplayCount > 0) {
    return `${pluralize(regressionReadyCount, "draft")} are ready for handoff and ${pluralize(manualReplayCount, "draft")} still need manual follow-up. These are guidance artifacts, not executed tests yet.`;
  }

  return `${pluralize(regressionReadyCount, "draft")} are ready for handoff. These are guidance artifacts, not executed tests yet.`;
}

function buildScoreDriver(audit: Audit, scoreHistory: ScoreUpdateEvent[]): ScoreDriver {
  const strongestHistoryEvent = [...scoreHistory]
    .filter((event): event is ScoreUpdateEvent & { delta: number } => event.delta !== null && event.delta !== 0)
    .sort((left, right) => Math.abs(right.delta) - Math.abs(left.delta))[0];

  if (strongestHistoryEvent) {
    return {
      delta: strongestHistoryEvent.delta,
      detail: describeScoreUpdate(strongestHistoryEvent),
    };
  }

  const latestHistoryEvent = [...scoreHistory].sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at))[0];
  if (latestHistoryEvent) {
    return {
      delta: latestHistoryEvent.delta ?? 0,
      detail: describeScoreUpdate(latestHistoryEvent),
    };
  }

  const fallbackDelta = audit.score - audit.score_baseline;
  return {
    delta: fallbackDelta,
    detail: describeAuditScoreSnapshot(audit),
  };
}

function toneFromSummaryCard(tone: StatusBadgeTone) {
  switch (tone) {
    case "danger":
      return "border-rose-200 bg-[linear-gradient(135deg,rgba(255,241,242,0.96),rgba(255,255,255,0.94))]";
    case "warning":
      return "border-amber-200 bg-[linear-gradient(135deg,rgba(255,251,235,0.96),rgba(255,255,255,0.94))]";
    case "success":
      return "border-emerald-200 bg-[linear-gradient(135deg,rgba(236,253,245,0.96),rgba(255,255,255,0.94))]";
    default:
      return "border-slate-200 bg-[linear-gradient(135deg,rgba(248,250,252,0.96),rgba(255,255,255,0.94))]";
  }
}

function toneFromMetricCard(tone: StatusBadgeTone) {
  switch (tone) {
    case "danger":
      return "border-rose-200 bg-rose-50/80";
    case "warning":
      return "border-amber-200 bg-amber-50/80";
    case "success":
      return "border-emerald-200 bg-emerald-50/80";
    case "info":
      return "border-cyan-200 bg-cyan-50/80";
    default:
      return "border-slate-200 bg-white/80";
  }
}

export function FinalReportSummaryCard({
  audit,
  completionEvent,
  scoreHistory,
  className,
}: Readonly<FinalReportSummaryCardProps>) {
  const severityCounts = createSeverityCounts(audit);
  const verifierCompleted =
    audit.status === "completed" &&
    audit.agents.some((agent) => agent.name.toLowerCase() === "verifier" && agent.status === "completed");
  const verifiedFindings = audit.findings.filter((finding) => finding.verification_state === "verified").length;
  const replayRecordCount = audit.replay_records.length;
  const regressionReadyCount = audit.replay_records.filter((record) => record.readiness === "regression_ready").length;
  const manualReplayCount = replayRecordCount - regressionReadyCount;
  const unresolvedFindings = audit.findings.filter((finding) => finding.verification_state !== "verified").length;
  const unsupportedAreas = audit.unsupported_areas.length;
  const unsupportedTechnologies = audit.unsupported_technologies.length;
  const unsupportedScope = unsupportedScopeCount(audit.unsupported_areas, audit.unsupported_technologies);
  const needsManualReviewAreas = audit.needs_manual_review_areas.length;
  const criticalIssuesRemaining = severityCounts.critical;
  const highIssuesRemaining = severityCounts.high;
  const mergeGuidance = buildMergeGuidance({
    audit,
    criticalIssuesRemaining,
    highIssuesRemaining,
    unresolvedFindings,
    verifiedFindings,
    unsupportedAreas,
    unsupportedTechnologies,
    needsManualReviewAreas,
    skippedChecks: audit.checks_skipped.length,
  });
  const strongestScoreDriver = buildScoreDriver(audit, scoreHistory);
  const answerCards: AnswerCard[] = [
    {
      label: "What was reviewed?",
      badgeLabel: "Review",
      tone: verifiedFindings > 0 || (verifierCompleted && audit.findings.length === 0) ? "success" : audit.status === "failed" ? "danger" : "warning",
      detail: buildWhatWasVerified({ audit, completionEvent, verifiedFindings, unresolvedFindings, replayRecordCount }),
    },
    {
      label: "What is ready to retest?",
      badgeLabel: "Retest",
      tone: regressionReadyCount > 0 ? (manualReplayCount > 0 ? "warning" : "success") : replayRecordCount > 0 ? "warning" : "neutral",
      detail: buildRegressionReadySummary({ replayRecordCount, regressionReadyCount, manualReplayCount }),
    },
    {
      label: "What still needs review?",
      badgeLabel: "Needs review",
      tone:
        unresolvedFindings > 0 ||
        audit.findings.length > 0 ||
        audit.confidence_limited ||
        criticalIssuesRemaining > 0 ||
        needsManualReviewAreas > 0
          ? "warning"
          : "neutral",
      detail: buildManualReviewSummary({ audit, unresolvedFindings, verifiedFindings, criticalIssuesRemaining, needsManualReviewAreas }),
    },
    {
      label: "What was out of scope?",
      badgeLabel: "Out of scope",
      tone: unsupportedAreas > 0 || unsupportedTechnologies > 0 || audit.checks_skipped.length > 0 ? "warning" : "neutral",
      detail: buildUnsupportedSummary(audit),
    },
    {
      label: "Biggest score driver",
      badgeLabel: "Score move",
      tone: strongestScoreDriver.delta < 0 ? "danger" : strongestScoreDriver.delta > 0 ? "success" : "neutral",
      detail:
        strongestScoreDriver.delta !== 0
          ? `${formatScoreDelta(strongestScoreDriver.delta)}. ${strongestScoreDriver.detail}`
          : strongestScoreDriver.detail,
    },
  ] as const;

  return (
    <section
      className={cn(
        "rounded-[1.75rem] border p-5 shadow-sm sm:p-6",
        toneFromSummaryCard(mergeGuidance.tone),
        className,
      )}
      aria-label="Final report summary"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Decision summary</p>
          <h3 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">{mergeGuidance.headline}</h3>
          <p className="mt-3 text-sm leading-6 text-slate-700">{mergeGuidance.detail}</p>
        </div>
        <StatusBadge tone={mergeGuidance.tone} mono className="justify-center">
          {mergeGuidance.answer}
        </StatusBadge>
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-[1.12fr_0.88fr]">
        <article className={cn("rounded-[1.5rem] border p-5", toneFromMetricCard(mergeGuidance.tone))}>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Ship call</p>
          <p className="mt-4 text-4xl font-semibold tracking-[-0.04em] text-slate-950">{mergeGuidance.answer}</p>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-700">{mergeGuidance.detail}</p>

          <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <div className="rounded-2xl border border-white/80 bg-white/82 px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Retest drafts</p>
              <p className="mt-2 font-mono text-2xl font-semibold tracking-[-0.03em] text-slate-950">{regressionReadyCount}</p>
              <p className="mt-2 text-sm leading-5 text-slate-600">
                {replayRecordCount > 0
                  ? manualReplayCount > 0
                    ? `${manualReplayCount} more drafts still need manual follow-up.`
                    : "Retest drafts are ready for handoff."
                  : "No retest drafts were generated in this report."}
              </p>
            </div>
            <div className="rounded-2xl border border-white/80 bg-white/82 px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Supported</p>
              <p className="mt-2 font-mono text-2xl font-semibold tracking-[-0.03em] text-slate-950">{audit.supported_areas.length}</p>
              <p className="mt-2 text-sm leading-5 text-slate-600">
                {audit.supported_areas.length > 0 ? summarizeList(audit.supported_areas) : "No supported surface tags were reported."}
              </p>
            </div>
            <div className="rounded-2xl border border-white/80 bg-white/82 px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Partially supported</p>
              <p className="mt-2 font-mono text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {audit.partially_supported_areas.length}
              </p>
              <p className="mt-2 text-sm leading-5 text-slate-600">
                {audit.partially_supported_areas.length > 0
                  ? summarizeList(audit.partially_supported_areas)
                  : "No partially supported surface tags were reported."}
              </p>
            </div>
            <div className="rounded-2xl border border-white/80 bg-white/82 px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Unsupported</p>
              <p className="mt-2 font-mono text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {unsupportedScope}
              </p>
              <p className="mt-2 text-sm leading-5 text-slate-600">
                {unsupportedAreas > 0 && unsupportedTechnologies > 0
                  ? `Areas: ${summarizeList(audit.unsupported_areas)}. Tech: ${summarizeList(audit.unsupported_technologies)}.`
                  : unsupportedAreas > 0
                    ? summarizeList(audit.unsupported_areas)
                    : unsupportedTechnologies > 0
                      ? `Tech: ${summarizeList(audit.unsupported_technologies)}.`
                      : "No unsupported surface tags were reported."}
              </p>
            </div>
            <div className="rounded-2xl border border-white/80 bg-white/82 px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Needs manual review</p>
              <p className="mt-2 font-mono text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {needsManualReviewAreas + audit.checks_skipped.length + unresolvedFindings}
              </p>
              <p className="mt-2 text-sm leading-5 text-slate-600">
                {needsManualReviewAreas > 0
                  ? summarizeList(audit.needs_manual_review_areas)
                  : audit.checks_skipped.length > 0
                    ? `${pluralize(audit.checks_skipped.length, "check")} were skipped in this run.`
                    : unresolvedFindings > 0
                      ? `${pluralize(unresolvedFindings, "finding")} still lack per-finding verifier review.`
                      : "No explicit manual-review tags were reported."}
              </p>
            </div>
          </div>
        </article>

        <div className="grid gap-3">
          {answerCards.map((card) => (
            <article key={card.label} className={cn("rounded-[1.25rem] border px-4 py-4", toneFromMetricCard(card.tone))}>
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{card.label}</p>
                <StatusBadge tone={card.tone} size="sm">
                  {card.badgeLabel}
                </StatusBadge>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-700">{card.detail}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
