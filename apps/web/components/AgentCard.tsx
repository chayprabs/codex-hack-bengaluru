import type { ReactNode } from "react";

import type { AgentStatus } from "@/lib/types";
import { formatRelativeTime } from "@/lib/format";
import { cn, titleCase } from "@/lib/utils";
import { StatusBadge, formatStatusLabel, toneFromAgentStatus } from "@/components/StatusBadge";

type AgentCardProps = {
  agent?: AgentStatus;
  isLoading?: boolean;
  action?: ReactNode;
  className?: string;
  showTimestamp?: boolean;
};

function AgentCardSkeleton() {
  return (
    <div className="space-y-4" aria-hidden="true">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-3">
          <div className="h-4 w-24 animate-pulse rounded-full bg-slate-200" />
          <div className="h-7 w-28 animate-pulse rounded-full bg-slate-100" />
        </div>
        <div className="h-8 w-24 animate-pulse rounded-full bg-slate-200" />
      </div>
      <div className="h-16 animate-pulse rounded-2xl bg-slate-100" />
      <div className="h-4 w-36 animate-pulse rounded-full bg-slate-100" />
    </div>
  );
}

export function AgentCard({
  agent,
  isLoading = false,
  action,
  className,
  showTimestamp = true,
}: Readonly<AgentCardProps>) {
  if (isLoading) {
    return (
      <article className={cn("rounded-[1.5rem] border border-slate-200 bg-white/90 p-5 shadow-sm", className)}>
        <AgentCardSkeleton />
      </article>
    );
  }

  if (!agent) {
    return null;
  }

  return (
    <article
      className={cn("flex h-full flex-col rounded-[1.5rem] border border-slate-200 bg-white/90 p-5 shadow-sm", className)}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Agent lane</p>
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              telemetry
            </span>
          </div>
          <h3 className="mt-3 font-mono text-lg font-semibold text-slate-950">{agent.name}</h3>
        </div>

        <div className="flex items-center gap-3">
          <StatusBadge tone={toneFromAgentStatus(agent.status)} mono>
            {formatStatusLabel(agent.status)}
          </StatusBadge>
          {action}
        </div>
      </div>

      <div className="mt-5 flex-1 rounded-[1.25rem] border border-slate-200 bg-slate-50/90 px-4 py-4">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Latest note</p>
        <p className="mt-3 text-sm leading-6 text-slate-700">{agent.message || "No status note has been published yet."}</p>
      </div>

      {showTimestamp ? (
        <dl className="mt-5 grid gap-3 text-sm text-slate-600 sm:grid-cols-2">
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Updated</dt>
            <dd className="mt-2 font-mono text-sm font-semibold text-slate-950">{formatRelativeTime(agent.updated_at)}</dd>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">State</dt>
            <dd className="mt-2 font-mono text-sm font-semibold text-slate-950">{titleCase(agent.status)}</dd>
          </div>
        </dl>
      ) : null}
    </article>
  );
}
