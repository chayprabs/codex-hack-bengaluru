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
import type { Audit, AuditCompleteEvent, FindingSeverity } from "@/lib/types";
import { formatDateTime, formatScore } from "@/lib/format";
import { titleCase } from "@/lib/utils";
import { useAuditStream } from "@/hooks/useAuditStream";
import { AgentCard } from "@/components/AgentCard";
import { AgentTracePanel } from "@/components/AgentTracePanel";
import { AuditHeader } from "@/components/AuditHeader";
import { AuditStatusBar } from "@/components/AuditStatusBar";
import { CoveragePanel } from "@/components/CoveragePanel";
import { EmptyState } from "@/components/EmptyState";
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
    return "Snapshot sync";
  }

  if (connectionState === "reconnecting") {
    return "Reconnecting";
  }

  if (connectionState === "connecting") {
    return "Connecting";
  }

  return status === "completed" || status === "failed" ? "Stream complete" : "Stream idle";
}

function CompletedStateSummary({
  audit,
  completionEvent,
}: Readonly<{ audit: Audit; completionEvent: AuditCompleteEvent | null }>) {
  const severityCounts = createSeverityCounts(audit);
  const highestSeverity = getHighestSeverity(severityCounts);
  const completedAgents = audit.agents.filter((agent) => agent.status === "completed").length;
  const failedAgents = audit.agents.filter((agent) => agent.status === "failed").length;
  const totalFindings = completionEvent?.finding_count ?? audit.findings.length;
  const title = audit.status === "completed" ? "Final report" : "Final report with failures";
  const terminalMessage = completionEvent?.message ?? audit.completion_message;
  const description =
    audit.confidence_limited
      ? terminalMessage
        ? `${terminalMessage} Coverage stayed limited, so the score should be treated as provisional until more of the repo is verified.`
        : `Coverage stayed limited at ${audit.coverage}/100, so the score should be treated as provisional until more of the repo is verified.`
      : terminalMessage
      ? terminalMessage
      : audit.coverage_summary
        ? audit.coverage_summary
        : audit.status === "completed"
          ? totalFindings
            ? `The audit finished with ${totalFindings} recorded findings. Review the final snapshot before trusting the repository.`
            : "The audit finished without recorded findings in the current snapshot."
          : "The audit reached a failed terminal state. Review lane output and findings before relying on the result.";

  return (
    <section className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Final report</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">{title}</h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600 sm:text-base">{description}</p>
        </div>
        <StatusBadge tone={toneFromAuditStatus(audit.status)} mono>
          {audit.status}
        </StatusBadge>
      </div>

      {audit.confidence_limited ? (
        <div className="mt-6 rounded-[1.25rem] border border-amber-200 bg-amber-50/90 px-4 py-4 text-amber-950">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-700">Confidence limited</p>
          <p className="mt-3 text-sm leading-6">
            Coverage is low enough that the TrustScore should be read as directional rather than final. Extend repository access or verification before using it as a release gate.
          </p>
        </div>
      ) : null}

      <div className="mt-6 grid gap-4 xl:grid-cols-2">
        <article className="rounded-[1.5rem] border border-slate-200 bg-[linear-gradient(135deg,rgba(255,255,255,0.98),rgba(248,250,252,0.94))] p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">TrustScore</p>
              <p className="mt-4 font-mono text-5xl font-semibold tracking-[-0.05em] text-slate-950">{formatScore(audit.score)}</p>
            </div>
            <StatusBadge tone={toneFromAuditStatus(audit.status)} mono>
              {formatScore(audit.score)}/100
            </StatusBadge>
          </div>
          <p className="mt-4 text-sm leading-6 text-slate-600">
            Hero metric for the final report. It reflects the current posture after findings and verifier closeout.
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
            <StatusBadge tone={audit.confidence_limited ? "danger" : "info"} mono>
              {titleCase(audit.coverage_band)}
            </StatusBadge>
          </div>
          <p className="mt-4 text-sm leading-6 text-slate-600">{audit.coverage_summary}</p>
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
      ? "The audit completed without persisted findings."
      : audit.status === "failed"
        ? "The audit ended before any findings were persisted."
        : "Findings will appear here as the backend emits them.";

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
            View shame wall
          </Link>
        </>
      }
    >
      <div className="space-y-6">
        <AuditHeader
          auditId={audit.id}
          repoUrl={audit.repo_url || "Unknown repository"}
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
                  Live updates
                </p>
                <p className="mt-2 text-sm leading-6">{streamError}</p>
              </div>
              <StatusBadge tone={connectionState === "polling" ? "neutral" : "warning"} mono>
                {connectionState === "polling" ? "Snapshot fallback" : "Reconnecting"}
              </StatusBadge>
            </div>
          </section>
        ) : null}

        {hasTerminalState ? <CompletedStateSummary audit={audit} completionEvent={completionEvent} /> : null}

        <TrustScore
          score={audit.score}
          scoreBaseline={audit.score_baseline}
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
        />

        <div className="grid gap-6 xl:grid-cols-[0.88fr_1.12fr]">
          <CoveragePanel audit={audit} />
          <section className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Agents</p>
                <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">Audit lanes</h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Planner, scanner, and verifier now read as sequential response lanes inside the same attack story.
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
                  title="No agent lanes yet"
                  description="This audit does not currently expose planner, scanner, or verifier lane data."
                />
              )}
            </div>
          </section>
        </div>

        <FindingFeed
          findings={audit.findings}
          stories={findingStories}
          title="Finding feed"
          description="Findings are framed as live response tracks with evidence, remediation handoff, and verification state."
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
