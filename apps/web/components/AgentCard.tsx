import type { ReactNode } from "react";

import type { AgentLaneStory } from "@/lib/auditStory";
import type { AgentStatus } from "@/lib/types";
import { formatRelativeTime } from "@/lib/format";
import { cn, titleCase } from "@/lib/utils";
import { StoryStageRail } from "@/components/StoryStageRail";
import { StatusBadge, formatStatusLabel, toneFromAgentStatus } from "@/components/StatusBadge";

type AgentCardProps = {
  agent?: AgentStatus;
  story?: AgentLaneStory;
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
          <div className="h-7 w-40 animate-pulse rounded-full bg-slate-100" />
        </div>
        <div className="h-8 w-24 animate-pulse rounded-full bg-slate-200" />
      </div>
      <div className="h-20 animate-pulse rounded-2xl bg-slate-100" />
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="h-24 animate-pulse rounded-[1.25rem] bg-slate-100" />
        <div className="h-24 animate-pulse rounded-[1.25rem] bg-slate-100" />
      </div>
    </div>
  );
}

export function AgentCard({
  agent,
  story,
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

  if (!agent || !story) {
    return null;
  }

  return (
    <article
      className={cn(
        "flex h-full flex-col rounded-[1.5rem] border border-slate-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(248,250,252,0.92))] p-5 shadow-sm",
        className,
      )}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">{story.roleLabel}</p>
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              {story.statusLabel}
            </span>
            {story.isLive ? (
              <span className="inline-flex items-center gap-2 rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-cyan-700">
                <span className="story-pulse inline-flex h-2.5 w-2.5 rounded-full bg-cyan-500" />
                Live
              </span>
            ) : null}
          </div>
          <h3 className="mt-3 font-mono text-lg font-semibold text-slate-950">{agent.name}</h3>
          <p className="mt-3 text-sm leading-6 text-slate-600">{story.missionLabel}</p>
        </div>

        <div className="flex items-center gap-3">
          <StatusBadge tone={toneFromAgentStatus(agent.status)} mono>
            {formatStatusLabel(agent.status)}
          </StatusBadge>
          {action}
        </div>
      </div>

      <div className="mt-5 grid gap-3 xl:grid-cols-[minmax(0,1.05fr)_minmax(16rem,0.95fr)]">
        <div className="rounded-[1.25rem] border border-slate-200 bg-white/80 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Latest note</p>
          <p className="mt-3 text-sm leading-6 text-slate-700">{agent.message || "No status note has been published yet."}</p>
        </div>

        <div className="rounded-[1.25rem] border border-slate-200 bg-slate-50/90 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Downstream impact</p>
          <p className="mt-3 text-sm font-semibold tracking-[-0.02em] text-slate-950">{story.impactLabel}</p>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            This lane now reads as part of the same response sequence rather than a separate subsystem feed.
          </p>
        </div>
      </div>

      <div className="mt-5 rounded-[1.25rem] border border-slate-200 bg-white/80 p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Lane flow</p>
          <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-slate-500">{story.statusLabel}</p>
        </div>
        <StoryStageRail stages={story.stages} compact className="mt-4" />
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
