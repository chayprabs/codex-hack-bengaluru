import Link from "next/link";

import {
  getApiErrorMessage,
  getApiErrorStatus,
  getAudit,
  type Audit,
  type FindingSeverity,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { AgentCard } from "@/components/AgentCard";
import { AuditHeader } from "@/components/AuditHeader";
import { AuditStatusBar } from "@/components/AuditStatusBar";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { FindingFeed } from "@/components/FindingFeed";
import { StatusBadge, formatSeverityBadgeLabel, toneFromAuditStatus, toneFromSeverity } from "@/components/StatusBadge";
import { TrustScore } from "@/components/TrustScore";

export const dynamic = "force-dynamic";

type AuditPageProps = {
  params: Promise<{ id: string }>;
};

const pageActionClassName =
  "inline-flex min-h-10 items-center rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 transition hover:border-slate-300 hover:bg-slate-50 focus:outline-none focus:ring-4 focus:ring-slate-200";

const severityPenalty: Record<FindingSeverity, number> = {
  low: 4,
  medium: 10,
  high: 20,
  critical: 35,
};

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

function deriveTrustScore(audit: Audit) {
  const counts = createSeverityCounts(audit);
  const penalty = Object.entries(severityPenalty).reduce((total, [severity, weight]) => {
    return total + counts[severity as FindingSeverity] * weight;
  }, 0);

  let score = Math.max(0, 100 - penalty);

  if (audit.status === "running") {
    score = Math.min(score, 90);
  }

  if (audit.status === "queued") {
    score = Math.min(score, 92);
  }

  if (audit.status === "failed") {
    score = Math.min(score, 30);
  }

  return {
    score,
    label:
      audit.status === "completed" || audit.status === "failed"
        ? "Derived trust score"
        : "Live trust estimate",
  };
}

function CompletedStateSummary({ audit }: Readonly<{ audit: Audit }>) {
  const severityCounts = createSeverityCounts(audit);
  const highestSeverity = getHighestSeverity(severityCounts);
  const completedAgents = audit.agents.filter((agent) => agent.status === "completed").length;
  const failedAgents = audit.agents.filter((agent) => agent.status === "failed").length;
  const title = audit.status === "completed" ? "Audit complete" : "Audit finished with failures";
  const description =
    audit.status === "completed"
      ? audit.findings.length
        ? `The audit finished with ${audit.findings.length} recorded findings. Review the final snapshot before trusting the repository.`
        : "The audit finished without recorded findings in the current snapshot."
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

function AuditRoom({ audit }: Readonly<{ audit: Audit }>) {
  const trustScore = deriveTrustScore(audit);
  const hasTerminalState = audit.status === "completed" || audit.status === "failed";
  const findingsEmptyDescription =
    audit.status === "completed"
      ? "The audit completed without persisted findings."
      : audit.status === "failed"
        ? "The audit ended before any findings were persisted."
        : "Findings will appear here as soon as the backend stores them.";

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
            transportLabel="On-demand fetch"
            updatedAt={audit.updated_at}
          />

          {hasTerminalState ? <CompletedStateSummary audit={audit} /> : null}

          <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
            <TrustScore score={trustScore.score} label={trustScore.label} updatedAt={audit.updated_at} />

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

export default async function AuditPage({ params }: AuditPageProps) {
  const { id } = await params;

  try {
    const audit = await getAudit(id);
    return <AuditRoom audit={audit} />;
  } catch (error) {
    const status = getApiErrorStatus(error);
    const message = getApiErrorMessage(error);

    return (
      <main className="min-h-screen bg-transparent">
        <section className="mx-auto max-w-4xl px-4 py-10 sm:px-6 lg:px-8">
          {status === 404 ? (
            <EmptyState
              title="Audit not found"
              description="The requested audit id does not exist in the current API store. Start a new audit to create a fresh room."
              action={
                <div className="flex flex-wrap gap-3">
                  <Link href="/" className={pageActionClassName}>
                    Start a new audit
                  </Link>
                  <Link href="/wall" className={pageActionClassName}>
                    Open shame wall
                  </Link>
                </div>
              }
            />
          ) : (
            <ErrorState
              title="Audit room unavailable"
              description="The audit could not be loaded from the API right now."
              message={message}
              code={status}
              action={
                <div className="flex flex-wrap gap-3">
                  <Link href="/" className={pageActionClassName}>
                    Back to landing page
                  </Link>
                  <Link href="/wall" className={pageActionClassName}>
                    Open shame wall
                  </Link>
                </div>
              }
            />
          )}
        </section>
      </main>
    );
  }
}
