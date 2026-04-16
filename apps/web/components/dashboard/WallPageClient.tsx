"use client";

import Link from "next/link";

import type { FindingSeverity } from "@/lib/api";
import { useWallEntries } from "@/lib/use-wall-entries";
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
} from "@/lib/utils";

const severityTone: Record<FindingSeverity, "neutral" | "warning" | "danger" | "critical"> = {
  low: "neutral",
  medium: "warning",
  high: "danger",
  critical: "critical",
};

export function WallPageClient() {
  const { entries, error, refresh, status } = useWallEntries();

  if (status === "loading" && !entries.length) {
    return (
      <DashboardPage
        eyebrow="Shame wall"
        title="Loading the wall"
        description="Pulling the current findings leaderboard from the API."
      >
        <LoadingState
          title="Building the wall"
          description="The frontend is loading current findings and repo links from the typed API client."
        />
      </DashboardPage>
    );
  }

  if (status === "error") {
    return (
      <DashboardPage
        eyebrow="Shame wall"
        title="Wall unavailable"
        description="The page is wired, but the frontend could not load wall entries right now."
      >
        <StatePanel
          title="Wall fetch failed"
          description={error || "We could not load the wall feed from the API."}
          tone="danger"
          action={
            <>
              <button className={buttonClassName("primary")} type="button" onClick={refresh}>
                Retry
              </button>
              <Link href="/" className={buttonClassName()}>
                Start a new audit
              </Link>
            </>
          }
        />
      </DashboardPage>
    );
  }

  const criticalCount = entries.filter((entry) => entry.severity === "critical").length;
  const repoCount = new Set(entries.map((entry) => entry.repo_url)).size;
  const newestEntry = entries[0];

  return (
    <DashboardPage
      eyebrow="Shame wall"
      title="Latest findings across audits"
      description="A compact leaderboard of surfaced issues, linked back to each audit room."
      actions={
        <>
          <button className={buttonClassName("primary")} type="button" onClick={refresh}>
            Refresh wall
          </button>
          <Link href="/" className={buttonClassName()}>
            Start another audit
          </Link>
        </>
      }
    >
      <MetricGrid>
        <MetricCard
          label="Wall entries"
          value={String(entries.length)}
          detail={entries.length ? "Findings currently surfaced by the backend store." : "No findings yet."}
        />
        <MetricCard
          label="Critical issues"
          value={String(criticalCount)}
          detail="Highest-severity entries currently on the wall."
        />
        <MetricCard
          label="Repos affected"
          value={String(repoCount)}
          detail="Unique repositories represented on the wall."
        />
        <MetricCard
          label="Latest finding"
          value={newestEntry ? formatRelativeTime(newestEntry.created_at) : "None"}
          detail="How recently the wall was updated."
        />
      </MetricGrid>

      {!entries.length ? (
        <StatePanel
          title="Wall is empty"
          description="No findings have been recorded yet. Once audits start returning findings, they will appear here."
          tone="neutral"
          action={
            <Link href="/" className={buttonClassName("primary")}>
              Create an audit
            </Link>
          }
        />
      ) : (
        <Card className="space-y-6">
          <SectionHeader
            title="Findings leaderboard"
            description="Each entry links back to the audit room that produced it."
          />

          <div className="space-y-4">
            {entries.map((entry) => (
              <article key={`${entry.audit_id}-${entry.title}-${entry.created_at}`} className="rounded-[1.5rem] border border-slate-200 bg-slate-50/90 p-4">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-3">
                      <StatusPill tone={severityTone[entry.severity]}>
                        {formatSeverityLabel(entry.severity)}
                      </StatusPill>
                      <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                        Audit {shortId(entry.audit_id)}
                      </span>
                    </div>

                    <h2 className="mt-4 text-xl font-semibold tracking-[-0.03em] text-slate-950">{entry.title}</h2>
                    <p className="mt-2 text-sm leading-6 text-slate-600">
                      {repoLabelFromUrl(entry.repo_url)} surfaced this finding {formatRelativeTime(entry.created_at)}.
                    </p>
                  </div>

                  <div className="flex flex-wrap gap-3">
                    <Link href={`/audit/${entry.audit_id}`} className={buttonClassName("primary")}>
                      Open audit room
                    </Link>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap gap-3 text-sm text-slate-500">
                  <span className="rounded-full bg-white px-3 py-1 font-medium">{entry.repo_url}</span>
                  <span className="rounded-full bg-white px-3 py-1 font-medium">
                    Logged {formatDateTime(entry.created_at)}
                  </span>
                </div>
              </article>
            ))}
          </div>
        </Card>
      )}
    </DashboardPage>
  );
}
