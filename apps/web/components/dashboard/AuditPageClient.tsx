"use client";

import Link from "next/link";

import type { AgentStatus, AuditState, FindingSeverity } from "@/lib/api";
import { useAuditMonitor } from "@/lib/use-audit-monitor";
import {
  buttonClassName,
  Card,
  DashboardPage,
  LoadingState,
  MetricCard,
  MetricGrid,
  SectionHeader,
  StatePanel,
  StatusPill,
} from "@/components/dashboard/ui";
import {
  formatDateTime,
  formatRelativeTime,
  formatSeverityLabel,
  repoLabelFromUrl,
  shortId,
  titleCase,
} from "@/lib/utils";

const auditStatusTone: Record<AuditState, "neutral" | "info" | "success" | "danger"> = {
  queued: "neutral",
  running: "info",
  completed: "success",
  failed: "danger",
};

const severityTone: Record<FindingSeverity, "neutral" | "warning" | "danger" | "critical"> = {
  low: "neutral",
  medium: "warning",
  high: "danger",
  critical: "critical",
};

const agentStatusTone = auditStatusTone;

function transportLabel(transport: "connecting" | "polling" | "sse") {
  if (transport === "connecting") {
    return "Connecting stream";
  }

  if (transport === "sse") {
    return "Live SSE";
  }

  return "Snapshot polling";
}

function FindingsEmptyState({
  isFailed,
  isRunning,
}: Readonly<{ isFailed: boolean; isRunning: boolean }>) {
  const title = isFailed ? "Audit failed before findings landed" : "No findings yet";
  const description = isFailed
    ? "The audit stopped before TrustLayer could persist any findings."
    : isRunning
      ? "The agents are still working. Findings will appear here as soon as the API starts returning them."
      : "This audit has not reported any findings yet.";

  return <StatePanel title={title} description={description} tone={isFailed ? "danger" : "neutral"} />;
}

function AgentLane({ agent }: Readonly<{ agent: AgentStatus }>) {
  return (
    <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50/90 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-slate-950">{titleCase(agent.name)}</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">{agent.message}</p>
        </div>
        <StatusPill tone={agentStatusTone[agent.status]}>{titleCase(agent.status)}</StatusPill>
      </div>
      <p className="mt-3 text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
        Updated {formatRelativeTime(agent.updated_at)}
      </p>
    </div>
  );
}

export function AuditPageClient({ auditId }: Readonly<{ auditId: string }>) {
  const { audit, error, errorStatus, isRefreshing, refresh, status, transport } = useAuditMonitor(auditId);

  if (status === "loading" && !audit) {
    return (
      <DashboardPage
        eyebrow="Audit room"
        title="Loading audit room"
        description="Fetching the current repo snapshot, agent status, and findings."
      >
        <LoadingState
          title="Building the audit view"
          description="TrustLayer is pulling the latest frontend-safe snapshot from the API."
        />
      </DashboardPage>
    );
  }

  if (!audit) {
    const title = errorStatus === 404 ? "Audit not found" : "Audit room unavailable";
    const description =
      errorStatus === 404
        ? "This audit id does not exist in the current API store. Create a new audit from the landing page."
        : error || "We could not load the audit right now.";

    return (
      <DashboardPage
        eyebrow="Audit room"
        title={title}
        description="The page is wired, but the current audit snapshot could not be loaded."
      >
        <StatePanel
          title={title}
          description={description}
          tone={errorStatus === 404 ? "warning" : "danger"}
          action={
            <>
              <button className={buttonClassName("primary")} type="button" onClick={refresh}>
                Retry
              </button>
              <Link href="/" className={buttonClassName()}>
                Back to landing page
              </Link>
            </>
          }
        />
      </DashboardPage>
    );
  }

  const findingsCount = audit.findings.length;
  const activeAgents = audit.agents.filter((agent) => agent.status === "running").length;

  return (
    <DashboardPage
      eyebrow="Audit room"
      title={repoLabelFromUrl(audit.repo_url)}
      description={`Audit ${shortId(audit.id)} is wired to a typed client and ready to swap from polling to SSE when the backend stream starts sending events.`}
      actions={
        <>
          <button className={buttonClassName("primary")} type="button" onClick={refresh}>
            {isRefreshing ? "Refreshing..." : "Refresh now"}
          </button>
          <Link href="/wall" className={buttonClassName()}>
            View shame wall
          </Link>
        </>
      }
    >
      <MetricGrid>
        <MetricCard
          label="Audit status"
          value={titleCase(audit.status)}
          detail={`Updated ${formatRelativeTime(audit.updated_at)}`}
        />
        <MetricCard
          label="Live transport"
          value={transportLabel(transport)}
          detail="Automatically falls back to polling while the stream endpoint is still a scaffold."
        />
        <MetricCard
          label="Findings"
          value={String(findingsCount)}
          detail={findingsCount ? "Reported issues in the current snapshot." : "No findings have landed yet."}
        />
        <MetricCard
          label="Active lanes"
          value={`${activeAgents}/${audit.agents.length}`}
          detail="Planner, scanner, and verifier progress at a glance."
        />
      </MetricGrid>

      {error ? (
        <StatePanel
          title="Background refresh degraded"
          description={`${error} The latest good snapshot is still shown below.`}
          tone="warning"
          action={
            <button className={buttonClassName("primary")} type="button" onClick={refresh}>
              Try again
            </button>
          }
        />
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <Card className="space-y-6">
          <SectionHeader
            title="Findings feed"
            description="Current issues returned by the API for this audit id."
            actions={<StatusPill tone={auditStatusTone[audit.status]}>{titleCase(audit.status)}</StatusPill>}
          />

          {audit.findings.length ? (
            <div className="space-y-4">
              {audit.findings.map((finding) => (
                <article key={finding.id} className="rounded-[1.5rem] border border-slate-200 bg-slate-50/90 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h3 className="text-lg font-semibold text-slate-950">{finding.title}</h3>
                      <p className="mt-2 text-sm leading-6 text-slate-600">{finding.summary}</p>
                    </div>
                    <StatusPill tone={severityTone[finding.severity]}>
                      {formatSeverityLabel(finding.severity)}
                    </StatusPill>
                  </div>

                  <div className="mt-4 flex flex-wrap gap-3 text-sm text-slate-500">
                    <span className="rounded-full bg-white px-3 py-1 font-medium">
                      {finding.file_path ? `${finding.file_path}${finding.line ? `:${finding.line}` : ""}` : "No file path"}
                    </span>
                    <span className="rounded-full bg-white px-3 py-1 font-medium">
                      Logged {formatDateTime(finding.created_at)}
                    </span>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <FindingsEmptyState isFailed={audit.status === "failed"} isRunning={audit.status === "running"} />
          )}
        </Card>

        <div className="space-y-6">
          <Card className="space-y-6">
            <SectionHeader
              title="Audit metadata"
              description="Repo, timestamps, and wire-up state for this frontend view."
            />

            <div className="space-y-4 text-sm leading-6 text-slate-600">
              <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50/90 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Repository</p>
                <p className="mt-2 break-all text-base font-semibold text-slate-950">{audit.repo_url}</p>
              </div>
              <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50/90 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Created</p>
                <p className="mt-2 text-base font-semibold text-slate-950">{formatDateTime(audit.created_at)}</p>
              </div>
              <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50/90 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Last updated</p>
                <p className="mt-2 text-base font-semibold text-slate-950">{formatDateTime(audit.updated_at)}</p>
              </div>
              <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50/90 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Audit id</p>
                <p className="mt-2 break-all text-base font-semibold text-slate-950">{audit.id}</p>
              </div>
            </div>
          </Card>

          <Card className="space-y-6">
            <SectionHeader
              title="Agent lanes"
              description="The dashboard is ready for live lane updates once SSE events carry agent progress."
            />
            <div className="space-y-4">
              {audit.agents.map((agent) => (
                <AgentLane key={agent.name} agent={agent} />
              ))}
            </div>
          </Card>
        </div>
      </div>
    </DashboardPage>
  );
}
