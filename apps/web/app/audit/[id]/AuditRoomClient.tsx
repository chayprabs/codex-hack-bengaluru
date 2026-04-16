"use client";

import Link from "next/link";

import type { Audit, AuditCompleteEvent, FindingSeverity } from "@/lib/types";
import { formatDateTime } from "@/lib/format";
import { useAuditStream } from "@/hooks/useAuditStream";
import { AgentCard } from "@/components/AgentCard";
import { AuditHeader } from "@/components/AuditHeader";
import { AuditStatusBar } from "@/components/AuditStatusBar";
import { EmptyState } from "@/components/EmptyState";
import { FindingFeed } from "@/components/FindingFeed";
import { StatusBadge, formatSeverityBadgeLabel, toneFromAuditStatus, toneFromSeverity } from "@/components/StatusBadge";
import { TrustScore } from "@/components/TrustScore";

const pageActionClassName =
  "inline-flex min-h-10 items-center rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 transition hover:border-slate-300 hover:bg-slate-50 focus:outline-none focus:ring-4 focus:ring-slate-200";

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
  const title = audit.status === "completed" ? "Audit complete" : "Audit finished with failures";
  const description =
    audit.status === "completed"
      ? totalFindings
        ? `The audit finished with ${totalFindings} recorded findings. Review the final snapshot before trusting the repository.`
        : "The audit finished without recorded findings in the current snapshot."
      : completionEvent?.message
        ? completionEvent.message
        : "The audit reached a failed terminal state. Review lane output and findings before relying on the result.";

  return (
    <section className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Terminal summary</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">{title}</h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600 sm:text-base">{description}</p>
        </div>
        <StatusBadge tone={toneFromAuditStatus(audit.status)} mono>
          {audit.status}
        </StatusBadge>
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
  const { audit, completionEvent, connectionState, latestScoreUpdate, streamError } = useAuditStream({
    auditId: initialAudit.id,
    initialAudit,
  });

  const hasTerminalState = audit.status === "completed" || audit.status === "failed";
  const findingsEmptyDescription =
    audit.status === "completed"
      ? "The audit completed without persisted findings."
      : audit.status === "failed"
        ? "The audit ended before any findings were persisted."
        : "Findings will appear here as the backend emits them.";

  return (
    <main className="min-h-screen bg-transparent">
      <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-6 flex flex-wrap gap-3">
          <Link href="/" className={pageActionClassName}>
            New audit
          </Link>
          <Link href="/wall" className={pageActionClassName}>
            View shame wall
          </Link>
        </div>

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
            transportLabel={transportLabel(connectionState, audit.status)}
            updatedAt={audit.updated_at}
            isRefreshing={connectionState === "connecting" || connectionState === "reconnecting"}
          />

          {streamError && connectionState === "reconnecting" ? (
            <section className="rounded-[1.5rem] border border-amber-200 bg-amber-50/80 p-4 text-amber-900">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-700">Live updates</p>
                  <p className="mt-2 text-sm leading-6">{streamError}</p>
                </div>
                <StatusBadge tone="warning" mono>
                  Reconnecting
                </StatusBadge>
              </div>
            </section>
          ) : null}

          {hasTerminalState ? <CompletedStateSummary audit={audit} completionEvent={completionEvent} /> : null}

          <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
            <TrustScore
              score={audit.score}
              previousScore={latestScoreUpdate?.previous_score ?? null}
              delta={latestScoreUpdate?.delta ?? null}
              updatedAt={latestScoreUpdate?.updated_at ?? audit.updated_at}
              label="Trust score"
            />

            <section className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Agents</p>
                  <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">Audit lanes</h2>
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    Planner, scanner, and verifier status for the current audit snapshot.
                  </p>
                </div>
                <StatusBadge mono>{audit.agents.length} lanes</StatusBadge>
              </div>

              <div className="mt-6">
                {audit.agents.length ? (
                  <div className="grid gap-4 md:grid-cols-2">
                    {audit.agents.map((agent) => (
                      <AgentCard key={agent.name} agent={agent} />
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
            title="Finding feed"
            description="Latest issues returned by the backend for this audit id."
            emptyTitle="No findings recorded"
            emptyDescription={findingsEmptyDescription}
          />
        </div>
      </section>
    </main>
  );
}
