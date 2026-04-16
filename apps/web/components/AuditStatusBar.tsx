import type { AgentStatus, AuditState } from "@/lib/types";
import type { AttackStorySummary, StoryMoment } from "@/lib/auditStory";
import { formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { StoryStageRail } from "@/components/StoryStageRail";
import { StatusBadge, formatStatusLabel, toneFromAuditStatus } from "@/components/StatusBadge";

type AuditStatusBarProps = {
  status: AuditState;
  agents?: AgentStatus[];
  findingsCount?: number;
  highImpactCount?: number;
  transportLabel?: string;
  updatedAt?: string;
  isRefreshing?: boolean;
  isLoading?: boolean;
  story?: AttackStorySummary;
  moments?: StoryMoment[];
  className?: string;
};

function AuditStatusBarSkeleton() {
  return (
    <div className="space-y-4" aria-hidden="true">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((item) => (
          <div key={item} className="rounded-2xl border border-slate-200 bg-white/80 p-4">
            <div className="h-4 w-24 animate-pulse rounded-full bg-slate-200" />
            <div className="mt-4 h-7 w-36 animate-pulse rounded-full bg-slate-100" />
            <div className="mt-3 h-4 w-40 animate-pulse rounded-full bg-slate-100" />
          </div>
        ))}
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((item) => (
          <div key={item} className="h-28 animate-pulse rounded-[1.25rem] border border-slate-200 bg-slate-50/80" />
        ))}
      </div>
    </div>
  );
}

function toneClasses(tone: StoryMoment["tone"]) {
  switch (tone) {
    case "danger":
      return "border-rose-200 bg-rose-50/85";
    case "warning":
      return "border-amber-200 bg-amber-50/85";
    case "success":
      return "border-emerald-200 bg-emerald-50/90";
    case "info":
      return "border-cyan-200 bg-cyan-50/90";
    default:
      return "border-slate-200 bg-white/85";
  }
}

export function AuditStatusBar({
  status,
  agents = [],
  findingsCount,
  highImpactCount = 0,
  transportLabel = "Snapshot polling",
  updatedAt,
  isRefreshing = false,
  isLoading = false,
  story,
  moments = [],
  className,
}: Readonly<AuditStatusBarProps>) {
  if (isLoading) {
    return (
      <section
        className={cn(
          "rounded-[1.75rem] border border-slate-200 bg-[linear-gradient(135deg,rgba(255,255,255,0.95),rgba(248,250,252,0.92))] p-5 shadow-sm sm:p-6",
          className,
        )}
      >
        <AuditStatusBarSkeleton />
      </section>
    );
  }

  if (!story) {
    return null;
  }

  const completedAgents = agents.filter((agent) => agent.status === "completed").length;
  const runningAgents = agents.filter((agent) => agent.status === "running").length;
  const failedAgents = agents.filter((agent) => agent.status === "failed").length;

  const summaryItems = [
    {
      label: "Attack story",
      value: story.phaseLabel,
      detail: story.detail,
      tone: "border-slate-200 bg-white/85",
    },
    {
      label: "Major findings",
      value: `${highImpactCount}`,
      detail: highImpactCount ? "High-impact lanes now carry red-to-green response steps." : "No major findings have landed yet.",
      tone: highImpactCount ? "border-rose-200 bg-rose-50/85" : "border-slate-200 bg-white/85",
    },
    {
      label: "Agent flow",
      value: `${completedAgents}/${agents.length || 0}`,
      detail:
        runningAgents > 0
          ? `${runningAgents} lane${runningAgents === 1 ? "" : "s"} live now`
          : failedAgents > 0
            ? `${failedAgents} lane${failedAgents === 1 ? "" : "s"} blocked`
            : "All visible lanes are waiting or closed",
      tone: runningAgents > 0 ? "border-cyan-200 bg-cyan-50/85" : failedAgents > 0 ? "border-rose-200 bg-rose-50/85" : "border-slate-200 bg-white/85",
    },
    {
      label: "Transport",
      value: transportLabel,
      detail: isRefreshing ? "Refreshing and reconnecting live context." : updatedAt ? `Updated ${formatRelativeTime(updatedAt)}` : "Waiting for the first event.",
      tone: isRefreshing ? "border-cyan-200 bg-cyan-50/85" : "border-slate-200 bg-white/85",
    },
  ];

  return (
    <section
      className={cn(
        "relative overflow-hidden rounded-[1.75rem] border border-slate-200 bg-[linear-gradient(135deg,rgba(255,255,255,0.98),rgba(248,250,252,0.94))] p-5 shadow-sm sm:p-6",
        className,
      )}
      aria-label="Audit status overview"
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-28 bg-[radial-gradient(circle_at_top_left,rgba(244,63,94,0.12),transparent_38%),radial-gradient(circle_at_top_right,rgba(16,185,129,0.12),transparent_36%)]" />

      <div className="relative">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="max-w-4xl">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Attack story</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">{story.headline}</h2>
            <p className="mt-3 text-sm leading-6 text-slate-600 sm:text-base">{story.detail}</p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge tone={toneFromAuditStatus(status)} mono>
              {formatStatusLabel(status)}
            </StatusBadge>
            <StatusBadge tone={isRefreshing ? "info" : "neutral"} mono>
              {transportLabel}
            </StatusBadge>
            <StatusBadge tone={highImpactCount > 0 ? "danger" : "neutral"} mono>
              {highImpactCount} major
            </StatusBadge>
          </div>
        </div>

        <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {summaryItems.map((item) => (
            <div key={item.label} className={cn("rounded-2xl border px-4 py-4", item.tone)}>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{item.label}</p>
              <p className="mt-3 text-lg font-semibold tracking-[-0.02em] text-slate-950">{item.value}</p>
              <p className="mt-2 text-sm leading-6 text-slate-600">{item.detail}</p>
            </div>
          ))}
        </div>

        <div className="mt-6 rounded-[1.5rem] border border-slate-200 bg-white/70 p-4 sm:p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Story rail</p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Major findings move from discovery into evidence, patch planning, and verification closeout.
              </p>
            </div>
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-slate-500">
              {findingsCount ?? 0} finding{findingsCount === 1 ? "" : "s"} in room
            </p>
          </div>
          <StoryStageRail stages={story.stages} className="mt-5" />
        </div>

        {moments.length > 0 ? (
          <div className="mt-6">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Live flow</p>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Recent events are ordered like an incident story instead of a flat activity log.
                </p>
              </div>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {moments.slice(0, 4).map((moment) => (
                <article
                  key={moment.id}
                  className={cn(
                    "rounded-[1.25rem] border px-4 py-4 transition-transform",
                    toneClasses(moment.tone),
                    moment.highlight && "story-card-live",
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                      {moment.lane ?? "story"}
                    </p>
                    <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-slate-500">
                      {formatRelativeTime(moment.timestamp)}
                    </p>
                  </div>
                  <h3 className="mt-3 text-sm font-semibold tracking-[-0.02em] text-slate-950">{moment.label}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{moment.detail}</p>
                </article>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
