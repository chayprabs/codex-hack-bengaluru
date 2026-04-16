import type { ReactNode } from "react";

import type { Finding } from "@/lib/types";
import { formatDateTime } from "@/lib/format";
import { cn, formatSeverityLabel } from "@/lib/utils";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { StatusBadge, toneFromSeverity } from "@/components/StatusBadge";

type FindingFeedProps = {
  findings?: Finding[];
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
          <div className="mt-4 h-16 animate-pulse rounded-2xl bg-white" />
        </div>
      ))}
    </div>
  );
}

export function FindingFeed({
  findings = [],
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

  return (
    <section className={cn("rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6", className)}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Findings</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">{title}</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
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
            {sortedFindings.map((finding, index) => (
              <li key={finding.id}>
                <article className="rounded-[1.5rem] border border-slate-200 bg-slate-50/85 p-5">
                  <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,1fr)_15rem]">
                    <div>
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                          #{index + 1}
                        </span>
                        <StatusBadge tone={toneFromSeverity(finding.severity)}>
                          {formatSeverityLabel(finding.severity)}
                        </StatusBadge>
                      </div>
                      <h3 className="text-lg font-semibold text-slate-950">{finding.title}</h3>
                      <p className="mt-3 text-sm leading-6 text-slate-700">
                        {finding.summary || "The backend returned a finding without a summary."}
                      </p>
                    </div>

                    <dl className="grid gap-3 text-sm text-slate-600 sm:grid-cols-2 lg:grid-cols-1">
                      <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                        <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Location</dt>
                        <dd className="mt-2 font-mono text-sm font-semibold text-slate-950">
                          {finding.file_path ? `${finding.file_path}${finding.line ? `:${finding.line}` : ""}` : "No file path"}
                        </dd>
                      </div>
                      <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                        <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Logged</dt>
                        <dd className="mt-2 font-mono text-sm font-semibold text-slate-950">
                          {formatDateTime(finding.created_at)}
                        </dd>
                      </div>
                    </dl>
                  </div>
                </article>
              </li>
            ))}
          </ol>
        ) : null}
      </div>
    </section>
  );
}
