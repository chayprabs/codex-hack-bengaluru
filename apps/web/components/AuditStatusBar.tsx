import type { AgentStatus, AuditState } from "@/lib/types";
import { formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { StatusBadge, formatStatusLabel, toneFromAuditStatus } from "@/components/StatusBadge";

type AuditStatusBarProps = {
  status: AuditState;
  agents?: AgentStatus[];
  findingsCount?: number;
  transportLabel?: string;
  updatedAt?: string;
  isRefreshing?: boolean;
  isLoading?: boolean;
  className?: string;
};

function AuditStatusBarSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-hidden="true">
      {[0, 1, 2, 3].map((item) => (
        <div key={item} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div className="h-4 w-24 animate-pulse rounded-full bg-slate-200" />
          <div className="mt-4 h-7 w-28 animate-pulse rounded-full bg-slate-100" />
          <div className="mt-3 h-4 w-32 animate-pulse rounded-full bg-slate-100" />
        </div>
      ))}
    </div>
  );
}

export function AuditStatusBar({
  status,
  agents = [],
  findingsCount,
  transportLabel = "Snapshot polling",
  updatedAt,
  isRefreshing = false,
  isLoading = false,
  className,
}: Readonly<AuditStatusBarProps>) {
  if (isLoading) {
    return (
      <section className={cn("rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6", className)}>
        <AuditStatusBarSkeleton />
      </section>
    );
  }

  const completedAgents = agents.filter((agent) => agent.status === "completed").length;
  const runningAgents = agents.filter((agent) => agent.status === "running").length;
  const failedAgents = agents.filter((agent) => agent.status === "failed").length;

  const items = [
    {
      label: "Audit status",
      value: (
        <StatusBadge tone={toneFromAuditStatus(status)} mono>
          {formatStatusLabel(status)}
        </StatusBadge>
      ),
      detail: updatedAt ? `Updated ${formatRelativeTime(updatedAt)}` : "Waiting for first update",
    },
    {
      label: "Agent progress",
      value: (
        <span className="font-mono text-2xl font-semibold tracking-[-0.03em] text-slate-950">
          {completedAgents}/{agents.length}
        </span>
      ),
      detail:
        runningAgents > 0
          ? `${runningAgents} running now`
          : failedAgents > 0
            ? `${failedAgents} failed`
            : "No active lanes",
    },
    {
      label: "Findings",
      value: (
        <span className="font-mono text-2xl font-semibold tracking-[-0.03em] text-slate-950">
          {findingsCount ?? 0}
        </span>
      ),
      detail: findingsCount ? "Issues currently surfaced" : "No findings reported",
    },
    {
      label: "Transport",
      value: (
        <span className="font-mono text-lg font-semibold tracking-[-0.02em] text-slate-950">{transportLabel}</span>
      ),
      detail: isRefreshing ? "Refreshing latest snapshot" : "Ready for live updates",
    },
  ];

  return (
    <section
      className={cn("rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6", className)}
      aria-label="Audit status overview"
    >
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {items.map((item) => (
          <div key={item.label} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{item.label}</p>
            <div className="mt-4">{item.value}</div>
            <p className="mt-3 text-sm leading-6 text-slate-600">{item.detail}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
