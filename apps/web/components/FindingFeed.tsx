import type { ReactNode } from "react";

import type { FindingStory } from "@/lib/auditStory";
import type { Finding } from "@/lib/types";
import { formatDateTime, formatRelativeTime } from "@/lib/format";
import { cn, formatSeverityLabel } from "@/lib/utils";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { StatusBadge, toneFromSeverity } from "@/components/StatusBadge";
import { StoryStageRail } from "@/components/StoryStageRail";

type FindingFeedProps = {
  findings?: Finding[];
  stories?: Record<string, FindingStory>;
  isLoading?: boolean;
  errorMessage?: string | null;
  title?: string;
  description?: string;
  emptyTitle?: string;
  emptyDescription?: string;
  action?: ReactNode;
  className?: string;
};

function FindingFeedSkeleton() {
  return (
    <div className="space-y-4" aria-hidden="true">
      {[0, 1, 2].map((item) => (
        <div key={item} className="rounded-[1.5rem] border border-slate-200 bg-slate-50/80 p-4">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-3">
              <div className="h-5 w-40 animate-pulse rounded-full bg-slate-200" />
              <div className="h-4 w-72 max-w-full animate-pulse rounded-full bg-slate-100" />
            </div>
            <div className="h-7 w-24 animate-pulse rounded-full bg-slate-200" />
          </div>
          <div className="mt-4 h-24 animate-pulse rounded-2xl bg-white" />
        </div>
      ))}
    </div>
  );
}

export function FindingFeed({
  findings = [],
  stories = {},
  isLoading = false,
  errorMessage,
  title = "Finding feed",
  description = "Current findings returned by the audit API.",
  emptyTitle = "No findings yet",
  emptyDescription = "Once the scan reports issues, they will appear here.",
  action,
  className,
}: Readonly<FindingFeedProps>) {
  const sortedFindings = [...findings].sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at));
  const highImpactCount = sortedFindings.filter((finding) => finding.severity === "critical" || finding.severity === "high").length;

  return (
    <section className={cn("rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6", className)}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Findings</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">{title}</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{description}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge tone={highImpactCount > 0 ? "danger" : "neutral"} mono>
            {highImpactCount} major
          </StatusBadge>
          <StatusBadge mono>{sortedFindings.length} items</StatusBadge>
          {action ? <div className="flex flex-wrap gap-3">{action}</div> : null}
        </div>
      </div>

      <div className="mt-6">
        {isLoading ? <FindingFeedSkeleton /> : null}

        {!isLoading && errorMessage ? (
          <ErrorState
            compact
            title="Findings unavailable"
            description="The findings feed could not be rendered from the latest response."
            message={errorMessage}
          />
        ) : null}

        {!isLoading && !errorMessage && findings.length === 0 ? (
          <EmptyState compact title={emptyTitle} description={emptyDescription} />
        ) : null}

        {!isLoading && !errorMessage && sortedFindings.length > 0 ? (
          <ol className="space-y-4" aria-label="Audit findings">
            {sortedFindings.map((finding, index) => {
              const story = stories[finding.id];
              const locationLabel = finding.file_path ? `${finding.file_path}${finding.line ? `:${finding.line}` : ""}` : "No file path";

              return (
                <li key={finding.id}>
                  <article
                    className={cn(
                      "overflow-hidden rounded-[1.5rem] border p-5",
                      story?.isHighImpact
                        ? "border-rose-200 bg-[linear-gradient(135deg,rgba(255,241,242,0.95),rgba(255,255,255,0.98),rgba(236,253,245,0.92))]"
                        : "border-slate-200 bg-[linear-gradient(180deg,rgba(248,250,252,0.94),rgba(255,255,255,0.98))]",
                      story?.isRecent && "story-card-live",
                    )}
                  >
                    <div className="flex flex-col gap-5 xl:grid xl:grid-cols-[minmax(0,1.05fr)_minmax(20rem,0.95fr)]">
                      <div>
                        <div className="flex flex-wrap items-center gap-3">
                          <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                            #{index + 1}
                          </span>
                          <StatusBadge tone={toneFromSeverity(finding.severity)}>{formatSeverityLabel(finding.severity)}</StatusBadge>
                          {story?.isHighImpact ? (
                            <StatusBadge tone="danger" mono>
                              major
                            </StatusBadge>
                          ) : null}
                          {story?.isRecent ? (
                            <span className="inline-flex items-center gap-2 rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-cyan-700">
                              <span className="story-pulse inline-flex h-2.5 w-2.5 rounded-full bg-cyan-500" />
                              live now
                            </span>
                          ) : null}
                        </div>

                        <div className="mt-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                            {story?.headline ?? "Finding in review"}
                          </p>
                          <h3 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-slate-950">{finding.title}</h3>
                          <p className="mt-3 text-sm leading-6 text-slate-700">
                            {finding.summary || "The backend returned a finding without a summary."}
                          </p>
                        </div>

                        <div className="mt-5 grid gap-3 sm:grid-cols-2">
                          <div className="rounded-[1.25rem] border border-slate-200 bg-white/85 px-4 py-4">
                            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Current step</p>
                            <p className="mt-3 text-sm font-semibold tracking-[-0.02em] text-slate-950">
                              {story?.currentLabel ?? "Awaiting story state"}
                            </p>
                            <p className="mt-2 text-sm leading-6 text-slate-600">
                              {story?.statusLabel ?? "The finding is still being positioned in the audit flow."}
                            </p>
                          </div>
                          <div className="rounded-[1.25rem] border border-slate-200 bg-white/85 px-4 py-4">
                            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Patch proposal</p>
                            <p className="mt-3 text-sm font-semibold tracking-[-0.02em] text-slate-950">
                              {story?.impactLabel ?? "Remediation handoff"}
                            </p>
                            <p className="mt-2 text-sm leading-6 text-slate-600">
                              {story?.suggestedPatch ?? "A remediation suggestion will appear once the story model is available."}
                            </p>
                          </div>
                        </div>
                      </div>

                      <div className="space-y-4">
                        <div className="rounded-[1.25rem] border border-slate-200 bg-white/88 p-4">
                          <div className="flex items-start justify-between gap-4">
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Evidence</p>
                              <p className="mt-3 font-mono text-sm font-semibold text-slate-950">
                                {story?.evidenceLabel ?? locationLabel}
                              </p>
                            </div>
                            <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-slate-500">
                              {formatRelativeTime(finding.created_at)}
                            </p>
                          </div>

                          <dl className="mt-4 grid gap-3 sm:grid-cols-2">
                            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                              <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Logged</dt>
                              <dd className="mt-2 font-mono text-sm font-semibold text-slate-950">{formatDateTime(finding.created_at)}</dd>
                            </div>
                            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                              <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Impact lane</dt>
                              <dd className="mt-2 font-mono text-sm font-semibold text-slate-950">
                                {story?.impactLabel ?? "Finding lane"}
                              </dd>
                            </div>
                          </dl>
                        </div>

                        {story ? (
                          <div className="rounded-[1.25rem] border border-slate-200 bg-white/88 p-4">
                            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                              <div>
                                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Attack-story flow</p>
                                <p className="mt-2 text-sm leading-6 text-slate-600">
                                  Discovery starts red, response planning stabilizes, and verification closes the lane in green when it succeeds.
                                </p>
                              </div>
                              <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-slate-500">{story.statusLabel}</p>
                            </div>
                            <StoryStageRail stages={story.stages} compact className="mt-4" />
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </article>
                </li>
              );
            })}
          </ol>
        ) : null}
      </div>
    </section>
  );
}
