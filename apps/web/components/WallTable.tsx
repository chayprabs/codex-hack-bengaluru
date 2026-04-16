import type { ReactNode } from "react";
import Link from "next/link";

import type { WallEntry } from "@/lib/types";
import { formatDateTime, formatRelativeTime } from "@/lib/format";
import { cn, formatSeverityLabel, repoLabelFromUrl, shortId } from "@/lib/utils";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { StatusBadge, toneFromSeverity } from "@/components/StatusBadge";

type WallTableProps = {
  entries?: WallEntry[];
  isLoading?: boolean;
  errorMessage?: string | null;
  title?: string;
  description?: string;
  emptyTitle?: string;
  emptyDescription?: string;
  getAuditHref?: (entry: WallEntry) => string | null | undefined;
  renderActions?: (entry: WallEntry) => ReactNode;
  className?: string;
};

function WallTableSkeleton() {
  return (
    <div className="space-y-3" aria-hidden="true">
      {[0, 1, 2, 3].map((item) => (
        <div key={item} className="rounded-[1.5rem] border border-slate-200 bg-slate-50/80 p-4">
          <div className="grid gap-3 md:grid-cols-[1.1fr_0.7fr_0.5fr_0.6fr]">
            <div className="h-5 w-52 animate-pulse rounded-full bg-slate-200" />
            <div className="h-5 w-32 animate-pulse rounded-full bg-slate-100" />
            <div className="h-5 w-20 animate-pulse rounded-full bg-slate-100" />
            <div className="h-5 w-28 animate-pulse rounded-full bg-slate-100" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function WallTable({
  entries = [],
  isLoading = false,
  errorMessage,
  title = "Shame wall",
  description = "Latest surfaced findings across audits.",
  emptyTitle = "The wall is empty",
  emptyDescription = "Findings will appear here once audits start reporting issues.",
  getAuditHref,
  renderActions,
  className,
}: Readonly<WallTableProps>) {
  const hasActions = Boolean(getAuditHref || renderActions);

  return (
    <section className={cn("rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6", className)}>
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Wall</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">{title}</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
      </div>

      <div className="mt-6">
        {isLoading ? <WallTableSkeleton /> : null}

        {!isLoading && errorMessage ? (
          <ErrorState
            compact
            title="Wall data unavailable"
            description="The findings leaderboard could not be loaded."
            message={errorMessage}
          />
        ) : null}

        {!isLoading && !errorMessage && entries.length === 0 ? (
          <EmptyState compact title={emptyTitle} description={emptyDescription} />
        ) : null}

        {!isLoading && !errorMessage && entries.length > 0 ? (
          <>
            <div className="md:hidden">
              <ul className="space-y-3" aria-label="Wall entries">
                {entries.map((entry) => {
                  const href = getAuditHref?.(entry);

                  return (
                    <li key={`${entry.audit_id}-${entry.title}-${entry.created_at}`}>
                      <article className="rounded-[1.5rem] border border-slate-200 bg-slate-50/85 p-4">
                        <div className="flex flex-wrap items-center gap-3">
                          <StatusBadge tone={toneFromSeverity(entry.severity)}>
                            {formatSeverityLabel(entry.severity)}
                          </StatusBadge>
                          <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600">
                            <span className="font-mono">{shortId(entry.audit_id, 10)}</span>
                          </span>
                        </div>

                        <h3 className="mt-4 text-lg font-semibold text-slate-950">{entry.title}</h3>
                        <dl className="mt-4 space-y-2 text-sm text-slate-600">
                          <div>
                            <dt className="font-semibold text-slate-500">Repository</dt>
                            <dd className="mt-1 font-mono text-slate-900">{repoLabelFromUrl(entry.repo_url)}</dd>
                          </div>
                          <div>
                            <dt className="font-semibold text-slate-500">Logged</dt>
                            <dd className="mt-1 font-mono text-slate-900">{formatDateTime(entry.created_at)}</dd>
                          </div>
                        </dl>

                        {href || renderActions ? (
                          <div className="mt-5 flex flex-wrap gap-3">
                            {href ? (
                              <Link
                                href={href}
                                className="inline-flex min-h-10 items-center rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 transition hover:border-slate-300 hover:bg-slate-100"
                              >
                                Open audit
                              </Link>
                            ) : null}
                            {renderActions?.(entry)}
                          </div>
                        ) : null}
                      </article>
                    </li>
                  );
                })}
              </ul>
            </div>

            <div className="hidden overflow-hidden rounded-[1.5rem] border border-slate-200 md:block">
              <table className="min-w-full border-collapse">
                <caption className="sr-only">Latest findings across audits</caption>
                <thead className="bg-slate-50/90">
                  <tr className="text-left">
                    <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                      Finding
                    </th>
                    <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                      Repository
                    </th>
                    <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                      Audit
                    </th>
                    <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                      Logged
                    </th>
                    {hasActions ? (
                      <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                        Actions
                      </th>
                    ) : null}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {entries.map((entry) => {
                    const href = getAuditHref?.(entry);

                    return (
                      <tr key={`${entry.audit_id}-${entry.title}-${entry.created_at}`} className="align-top">
                        <td className="px-4 py-4">
                          <div className="flex flex-wrap items-center gap-3">
                            <StatusBadge tone={toneFromSeverity(entry.severity)}>
                              {formatSeverityLabel(entry.severity)}
                            </StatusBadge>
                            <div>
                              <p className="font-semibold text-slate-950">{entry.title}</p>
                              <p className="mt-1 text-sm text-slate-500">
                                Surfaced {formatRelativeTime(entry.created_at)}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-4 font-mono text-sm text-slate-700">{repoLabelFromUrl(entry.repo_url)}</td>
                        <td className="px-4 py-4 font-mono text-sm text-slate-700">{shortId(entry.audit_id, 10)}</td>
                        <td className="px-4 py-4 font-mono text-sm text-slate-700">{formatDateTime(entry.created_at)}</td>
                        {hasActions ? (
                          <td className="px-4 py-4">
                            <div className="flex flex-wrap gap-3">
                              {href ? (
                                <Link
                                  href={href}
                                  className="inline-flex min-h-10 items-center rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-semibold text-slate-800 transition hover:border-slate-300 hover:bg-slate-100"
                                >
                                  Open audit
                                </Link>
                              ) : null}
                              {renderActions?.(entry)}
                            </div>
                          </td>
                        ) : null}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </div>
    </section>
  );
}
