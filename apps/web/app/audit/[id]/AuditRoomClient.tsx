"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import {
  buildAgentOperationalTrace,
  buildAgentLaneStory,
  buildAttackStorySummary,
  buildFindingStory,
  buildScoreMoments,
  buildStoryMoments,
  canShowAgentTrace,
} from "@/lib/auditStory";
import type { Audit, AuditCompleteEvent, FindingSeverity, ScoreUpdateEvent } from "@/lib/types";
import { formatDateTime, formatScore } from "@/lib/format";
import { titleCase } from "@/lib/utils";
import { useAuditStream } from "@/hooks/useAuditStream";
import { AgentCard } from "@/components/AgentCard";
import { AgentTracePanel } from "@/components/AgentTracePanel";
import { AuditHeader } from "@/components/AuditHeader";
import { AuditStatusBar } from "@/components/AuditStatusBar";
import { CoveragePanel } from "@/components/CoveragePanel";
import { EvidenceBundleCard } from "@/components/EvidenceBundleCard";
import { EmptyState } from "@/components/EmptyState";
import { FinalReportSummaryCard } from "@/components/FinalReportSummaryCard";
import { FindingBucketSummary } from "@/components/FindingBucketSummary";
import { FindingFeed } from "@/components/FindingFeed";
import { PageShell, pageActionClassName } from "@/components/PageShell";
import { StatusBadge, formatSeverityBadgeLabel, toneFromAuditStatus, toneFromSeverity } from "@/components/StatusBadge";
import { TrustScore } from "@/components/TrustScore";

function createSeverityCounts(audit: Audit) {
  return audit.findings.reduce<Record<FindingSeverity, number>>(
    (counts, finding) => {
      counts[finding.severity] += 1;
      return counts;
    },
    { low: 0, medium: 0, high: 0, critical: 0 },
  );
}

function getHighestSeverity(counts: Record<FindingSeverity, number>) {
  const orderedSeverities: FindingSeverity[] = ["critical", "high", "medium", "low"];
  return orderedSeverities.find((severity) => counts[severity] > 0) ?? null;
}

function transportLabel(connectionState: ReturnType<typeof useAuditStream>["connectionState"], status: Audit["status"]) {
  if (connectionState === "live") {
    return "Live stream";
  }

  if (connectionState === "polling") {
    return "Sync mode";
  }

  if (connectionState === "reconnecting") {
    return "Reconnecting";
  }

  if (connectionState === "connecting") {
    return "Connecting";
  }

  return status === "completed" || status === "failed" ? "Final snapshot" : "Waiting";
}

function CompletedStateSummary({
  audit,
  completionEvent,
  scoreHistory,
  findingStories,
}: Readonly<{
  audit: Audit;
  completionEvent: AuditCompleteEvent | null;
  scoreHistory: ScoreUpdateEvent[];
  findingStories: Record<string, ReturnType<typeof buildFindingStory>>;
}>) {
  const severityCounts = createSeverityCounts(audit);
  const highestSeverity = getHighestSeverity(severityCounts);
  const completedAgents = audit.agents.filter((agent) => agent.status === "completed").length;
  const failedAgents = audit.agents.filter((agent) => agent.status === "failed").length;
  const totalFindings = completionEvent?.finding_count ?? audit.findings.length;
  const title = audit.status === "completed" ? "Final report" : "Report needs review";
  const terminalMessage = completionEvent?.message ?? audit.completion_message;
  const description =
    audit.confidence_limited
      ? terminalMessage
        ? `${terminalMessage} Coverage stayed thin, so treat the score as a first call, not a final one.`
        : `Coverage stayed thin at ${audit.coverage}/100, so treat the score as a first call, not a final one.`
      : terminalMessage
      ? terminalMessage
      : audit.coverage_summary
        ? audit.coverage_summary
        : audit.status === "completed"
          ? totalFindings
            ? `The audit ended with ${totalFindings} findings. Use the final report as the decision view.`
            : "The audit finished without persisted findings."
          : "The audit ended early. Review the latest findings and agent output before relying on this run.";

  return (
    <section className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Final report</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">{title}</h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600 sm:text-base">{description}</p>
        </div>
        <StatusBadge tone={toneFromAuditStatus(audit.status)} mono>
          {titleCase(audit.status)}
        </StatusBadge>
      </div>

      {audit.confidence_limited ? (
        <div className="mt-6 rounded-[1.25rem] border border-amber-200 bg-amber-50/90 px-4 py-4 text-amber-950">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-700">Scope limited</p>
          <p className="mt-3 text-sm leading-6">
            Coverage is too thin to treat this as a final ship call. Read TrustScore as a first pass until scope expands.
          </p>
        </div>
      ) : null}

      <FinalReportSummaryCard
        audit={audit}
        completionEvent={completionEvent}
        scoreHistory={scoreHistory}
        className="mt-6"
      />

      <FindingBucketSummary audit={audit} className="mt-6" />

      <EvidenceBundleCard audit={audit} stories={findingStories} className="mt-6" />

      <div className="mt-6 grid gap-4 xl:grid-cols-2">
        <article className="rounded-[1.5rem] border border-slate-200 bg-[linear-gradient(135deg,rgba(255,255,255,0.98),rgba(248,250,252,0.94))] p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">TrustScore</p>
              <p className="mt-4 font-mono text-5xl font-semibold tracking-[-0.05em] text-slate-950">{formatScore(audit.score)}</p>
            </div>
            <StatusBadge tone="neutral" mono>
              {formatScore(audit.score)}/100
            </StatusBadge>
          </div>
          <p className="mt-4 text-sm leading-6 text-slate-600">
            Final score after the latest findings and review.
          </p>
          <div className="mt-5 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Before -&gt; After</p>
            <p className="mt-2 font-mono text-base font-semibold text-slate-950">
              {formatScore(audit.score_baseline)} -&gt; {formatScore(audit.score)}
            </p>
          </div>
        </article>

        <article className="rounded-[1.5rem] border border-slate-200 bg-white/88 p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Coverage</p>
              <p className="mt-4 font-mono text-5xl font-semibold tracking-[-0.05em] text-slate-950">{formatScore(audit.coverage)}</p>
            </div>
            <StatusBadge tone={audit.confidence_limited ? "warning" : "info"} mono>
              {titleCase(audit.coverage_band)}
            </StatusBadge>
          </div>
          <p className="mt-4 text-sm leading-6 text-slate-600">
            {audit.coverage_summary || "How much of the repo this report actually covered."}
          </p>
          <div className="mt-5 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Before -&gt; After</p>
            <p className="mt-2 font-mono text-base font-semibold text-slate-950">
              {formatScore(audit.coverage_baseline)} -&gt; {formatScore(audit.coverage)}
            </p>
          </div>
        </article>
      </div>

      <dl className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Finished at</dt>
          <dd className="mt-2 font-mono text-sm font-semibold text-slate-950">{formatDateTime(audit.updated_at)}</dd>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Highest severity</dt>
          <dd className="mt-2">
            {highestSeverity ? (
              <StatusBadge tone={toneFromSeverity(highestSeverity)}>{formatSeverityBadgeLabel(highestSeverity)}</StatusBadge>
            ) : (
              <span className="font-mono text-sm font-semibold text-slate-950">None</span>
            )}
          </dd>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Completed lanes</dt>
          <dd className="mt-2 font-mono text-sm font-semibold text-slate-950">
            {completedAgents}/{audit.agents.length}
          </dd>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Failed lanes</dt>
          <dd className="mt-2 font-mono text-sm font-semibold text-slate-950">{failedAgents}</dd>
        </div>
      </dl>
    </section>
  );
}

export function AuditRoomClient({ initialAudit }: Readonly<{ initialAudit: Audit }>) {
  const { audit, activity, completionEvent, connectionState, latestScoreUpdate, scoreHistory, streamError } = useAuditStream({
    auditId: initialAudit.id,
    initialAudit,
  });
  const [traceAgentName, setTraceAgentName] = useState<string | null>(null);

  const hasTerminalState = audit.status === "completed" || audit.status === "failed";
  const attackStory = buildAttackStorySummary(audit);
  const storyMoments = buildStoryMoments(audit, activity, transportLabel(connectionState, audit.status));
  const scoreMoments = buildScoreMoments(audit, scoreHistory, completionEvent);
  const findingStories = Object.fromEntries(audit.findings.map((finding) => [finding.id, buildFindingStory(finding, audit)]));
  const traceByAgentName = useMemo(
    () =>
      Object.fromEntries(
        audit.agents
          .map((agent) => [agent.name, buildAgentOperationalTrace(agent, audit, activity)] as const)
          .filter((entry) => Boolean(entry[1])),
      ),
    [activity, audit],
  );
  const selectedTraceAgent = traceAgentName ? audit.agents.find((agent) => agent.name === traceAgentName) ?? null : null;
  const selectedTrace = traceAgentName ? traceByAgentName[traceAgentName] ?? null : null;
  const highImpactCount = audit.findings.filter((finding) => finding.severity === "high" || finding.severity === "critical").length;
  const findingsEmptyDescription =
    audit.status === "completed"
      ? "This audit finished without persisted findings."
      : audit.status === "failed"
        ? "The audit ended before any findings were saved."
        : "Findings appear here as the scan turns code into evidence.";

  useEffect(() => {
    if (!traceAgentName) {
      return;
    }

    const currentAgent = audit.agents.find((agent) => agent.name === traceAgentName);
    if (!currentAgent || !canShowAgentTrace(currentAgent)) {
      setTraceAgentName(null);
    }
  }, [audit.agents, traceAgentName]);

  return (
    <PageShell
      actions={
        <>
          <Link href="/" className={pageActionClassName}>
            New audit
          </Link>
          <Link href="/wall" className={pageActionClassName}>
            View wall
          </Link>
        </>
      }
    >
      <div className="space-y-6">
        <AuditHeader
          auditId={audit.id}
          repoUrl={audit.repo_url || "Unknown repository"}
          auditMode={audit.audit_mode}
          status={audit.status}
          createdAt={audit.created_at}
          updatedAt={audit.updated_at}
          findingsCount={audit.findings.length}
        />

        <AuditStatusBar
          status={audit.status}
          agents={audit.agents}
          findingsCount={audit.findings.length}
          highImpactCount={highImpactCount}
          transportLabel={transportLabel(connectionState, audit.status)}
          updatedAt={audit.updated_at}
          isRefreshing={connectionState === "connecting" || connectionState === "reconnecting"}
          story={attackStory}
          moments={storyMoments}
        />

        {streamError && !hasTerminalState ? (
          <section
            className={
              connectionState === "polling"
                ? "rounded-[1.5rem] border border-slate-200 bg-slate-50/90 p-4 text-slate-900"
                : "rounded-[1.5rem] border border-amber-200 bg-amber-50/80 p-4 text-amber-900"
            }
          >
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p
                  className={
                    connectionState === "polling"
                      ? "text-xs font-semibold uppercase tracking-[0.18em] text-slate-600"
                      : "text-xs font-semibold uppercase tracking-[0.18em] text-amber-700"
                  }
                >
                  Live stream
                </p>
                <p className="mt-2 text-sm leading-6">
                  {connectionState === "polling"
                    ? "Live updates paused. The room is staying current through snapshot sync."
                    : streamError}
                </p>
              </div>
              <StatusBadge tone={connectionState === "polling" ? "neutral" : "warning"} mono>
                {connectionState === "polling" ? "Sync mode" : "Reconnecting"}
              </StatusBadge>
            </div>
          </section>
        ) : null}

        {hasTerminalState ? (
          <CompletedStateSummary
            audit={audit}
            completionEvent={completionEvent}
            scoreHistory={scoreHistory}
            findingStories={findingStories}
          />
        ) : null}

        <TrustScore
          score={audit.score}
          scoreBaseline={audit.score_baseline}
          event={latestScoreUpdate}
          previousScore={latestScoreUpdate?.previous_score ?? null}
          delta={latestScoreUpdate?.delta ?? null}
          updatedAt={latestScoreUpdate?.updated_at ?? audit.updated_at}
          label="TrustScore"
          moments={scoreMoments}
          coverage={audit.coverage_percent ?? audit.coverage}
          coverageBaseline={audit.coverage_baseline}
          previousCoverage={latestScoreUpdate?.previous_coverage ?? null}
          coverageDelta={latestScoreUpdate?.coverage_delta ?? null}
          coverageBand={audit.coverage_band}
          coverageSummary={audit.coverage_summary ?? null}
          confidenceLimited={audit.confidence_limited}
          supportedAreas={audit.supported_areas}
          partiallySupportedAreas={audit.partially_supported_areas}
          unsupportedAreas={audit.unsupported_areas}
          needsManualReviewAreas={audit.needs_manual_review_areas}
          unsupportedTechnologies={audit.unsupported_technologies}
          scannedFilesCount={audit.scanned_files_count}
          skippedFilesCount={audit.skipped_files_count}
          frameworksDetected={audit.frameworks_detected}
          checksRun={audit.checks_run}
          checksSkipped={audit.checks_skipped}
        />

        <div className="grid gap-6 xl:grid-cols-[0.88fr_1.12fr]">
          <CoveragePanel audit={audit} />
          <section className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Agents</p>
                <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">Audit lanes</h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Planner, scanner, and verifier update this room as the audit moves.
                </p>
              </div>
              <StatusBadge mono>{audit.agents.length} lanes</StatusBadge>
            </div>

            <div className="mt-6">
              {audit.agents.length ? (
                <div className="grid gap-4 md:grid-cols-2">
                  {audit.agents.map((agent) => (
                    <AgentCard
                      key={agent.name}
                      agent={agent}
                      story={buildAgentLaneStory(agent, audit)}
                      action={
                        canShowAgentTrace(agent) ? (
                          <button
                            type="button"
                            onClick={() => setTraceAgentName(agent.name)}
                            className="inline-flex items-center rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-600 transition hover:border-cyan-200 hover:bg-cyan-50 hover:text-cyan-700"
                        >
                          View trace
                        </button>
                        ) : null
                      }
                    />
                  ))}
                </div>
              ) : (
                <EmptyState
                  compact
                  title="No agent updates yet"
                  description="This audit does not expose planner, scanner, or verifier updates yet."
                />
              )}
            </div>
          </section>
        </div>

        <FindingFeed
          findings={audit.findings}
          stories={findingStories}
          title="Findings"
          description="Each finding shows why it matters, what backs it, and whether it was reviewed."
          emptyTitle="No findings recorded"
          emptyDescription={findingsEmptyDescription}
        />
      </div>

      <AgentTracePanel
        agent={selectedTraceAgent}
        trace={selectedTrace}
        open={Boolean(selectedTraceAgent && selectedTrace)}
        onClose={() => setTraceAgentName(null)}
      />
    </PageShell>
  );
}
