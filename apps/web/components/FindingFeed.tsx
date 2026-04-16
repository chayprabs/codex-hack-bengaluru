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
  return (
    <section className={cn("rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6", className)}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Findings</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">{title}</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
        </div>
        {action ? <div className="flex flex-wrap gap-3">{action}</div> : null}
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

        {!isLoading && !errorMessage && findings.length > 0 ? (
          <ol className="space-y-4" aria-label="Audit findings">
            {findings.map((finding) => (
              <li key={finding.id}>
                <article className="rounded-[1.5rem] border border-slate-200 bg-slate-50/85 p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <h3 className="text-lg font-semibold text-slate-950">{finding.title}</h3>
                      <p className="mt-2 text-sm leading-6 text-slate-600">{finding.summary}</p>
                    </div>
                    <StatusBadge tone={toneFromSeverity(finding.severity)}>
                      {formatSeverityLabel(finding.severity)}
                    </StatusBadge>
                  </div>

                  <dl className="mt-4 flex flex-wrap gap-3 text-sm text-slate-600">
                    <div className="rounded-full border border-slate-200 bg-white px-3 py-1.5">
                      <dt className="sr-only">Location</dt>
                      <dd className="font-mono">
                        {finding.file_path ? `${finding.file_path}${finding.line ? `:${finding.line}` : ""}` : "No file path"}
                      </dd>
                    </div>
                    <div className="rounded-full border border-slate-200 bg-white px-3 py-1.5">
                      <dt className="sr-only">Logged at</dt>
                      <dd className="font-mono">{formatDateTime(finding.created_at)}</dd>
                    </div>
                  </dl>
                </article>
              </li>
            ))}
          </ol>
        ) : null}
      </div>
    </section>
  );
}
