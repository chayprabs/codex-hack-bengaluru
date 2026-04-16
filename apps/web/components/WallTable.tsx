import type { ReactNode } from "react";
import Link from "next/link";

import type { WallEntry } from "@/lib/types";
import { formatDateTime, formatRelativeTime, formatScore } from "@/lib/format";
import { cn, formatSeverityLabel, repoLabelFromUrl, shortId } from "@/lib/utils";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import {
  formatFindingConfidenceBadgeLabel,
  formatFindingProofBadgeLabel,
  formatFindingVerificationBadgeLabel,
  StatusBadge,
  toneFromFindingConfidence,
  toneFromFindingProofType,
  toneFromFindingVerificationState,
  toneFromSeverity,
  type StatusBadgeTone,
} from "@/components/StatusBadge";

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
  rankEntries?: boolean;
  getTrustScore?: (entry: WallEntry) => number | null | undefined;
  getTrustTier?: (entry: WallEntry) => { label: string; tone: StatusBadgeTone } | null | undefined;
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
  title = "Audit wall",
  description = "Recent findings across all audits.",
  emptyTitle = "No findings on the wall",
  emptyDescription = "Findings appear here as audits report issues.",
  getAuditHref,
  renderActions,
  rankEntries = false,
  getTrustScore,
  getTrustTier,
  className,
}: Readonly<WallTableProps>) {
  const hasActions = Boolean(getAuditHref || renderActions);
  const hasTrustSignals = entries.some((entry) => {
    const trustScore = getTrustScore?.(entry);
    const trustTier = getTrustTier?.(entry);

    return (trustScore !== null && trustScore !== undefined) || Boolean(trustTier);
  });

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
            title="Wall unavailable"
            description="Could not load ranked findings."
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
                {entries.map((entry, index) => {
                  const href = getAuditHref?.(entry);
                  const trustScore = getTrustScore?.(entry);
                  const trustTier = getTrustTier?.(entry);
                  const attributionLabel = [entry.agent_name, entry.check_name].filter(Boolean).join(" / ");
                  const confidenceLabel = formatFindingConfidenceBadgeLabel(entry.confidence);
                  const proofLabel = formatFindingProofBadgeLabel(entry.proof_type);
                  const verificationLabel = formatFindingVerificationBadgeLabel(entry.verification_state);

                  return (
                    <li key={entry.finding_id}>
                      <article className="rounded-[1.5rem] border border-slate-200 bg-slate-50/85 p-4">
                        <div className="flex flex-wrap items-center gap-3">
                          {rankEntries ? (
                            <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600">
                              #{index + 1}
                            </span>
                          ) : null}
                          <StatusBadge tone={toneFromSeverity(entry.severity)}>
                            {formatSeverityLabel(entry.severity)}
                          </StatusBadge>
                          {trustTier ? <StatusBadge tone={trustTier.tone}>{trustTier.label}</StatusBadge> : null}
                          <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600">
                            <span className="font-mono">{shortId(entry.audit_id, 10)}</span>
                          </span>
                        </div>

                        <h3 className="mt-4 text-lg font-semibold text-slate-950">{entry.title}</h3>
                        <p className="mt-2 text-sm leading-6 text-slate-600">{entry.impact_summary}</p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <StatusBadge size="sm" tone={toneFromFindingConfidence(entry.confidence)}>
                            {confidenceLabel}
                          </StatusBadge>
                          <StatusBadge size="sm" tone={toneFromFindingProofType(entry.proof_type)}>
                            {proofLabel}
                          </StatusBadge>
                          <StatusBadge size="sm" tone={toneFromFindingVerificationState(entry.verification_state)}>
                            {verificationLabel}
                          </StatusBadge>
                        </div>
                        {attributionLabel ? (
                          <p className="mt-2 font-mono text-xs uppercase tracking-[0.16em] text-slate-500">{attributionLabel}</p>
                        ) : null}
                        <dl
                          className={cn(
                            "mt-4 grid gap-3 text-sm text-slate-600",
                            trustScore !== null && trustScore !== undefined ? "sm:grid-cols-2" : "",
                          )}
                        >
                          {trustScore !== null && trustScore !== undefined ? (
                            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                              <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Score</dt>
                              <dd className="mt-2 font-mono text-2xl font-semibold text-slate-950">
                                {formatScore(trustScore)}
                              </dd>
                            </div>
                          ) : null}
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
                                View audit
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
                <caption className="sr-only">Recent findings across audits</caption>
                <thead className="bg-slate-50/90">
                  <tr className="text-left">
                    {rankEntries ? (
                      <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                        Rank
                      </th>
                    ) : null}
                    <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                      Finding
                    </th>
                    {hasTrustSignals ? (
                      <th scope="col" className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                        Score
                      </th>
                    ) : null}
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
                  {entries.map((entry, index) => {
                    const href = getAuditHref?.(entry);
                    const trustScore = getTrustScore?.(entry);
                    const trustTier = getTrustTier?.(entry);
                    const attributionLabel = [entry.agent_name, entry.check_name].filter(Boolean).join(" / ");
                    const confidenceLabel = formatFindingConfidenceBadgeLabel(entry.confidence);
                    const proofLabel = formatFindingProofBadgeLabel(entry.proof_type);
                    const verificationLabel = formatFindingVerificationBadgeLabel(entry.verification_state);

                    return (
                      <tr key={entry.finding_id} className="align-top">
                        {rankEntries ? (
                          <td className="px-4 py-4">
                            <span className="inline-flex h-10 min-w-10 items-center justify-center rounded-full border border-slate-200 bg-slate-50 px-3 font-mono text-sm font-semibold text-slate-700">
                              #{index + 1}
                            </span>
                          </td>
                        ) : null}
                        <td className="px-4 py-4">
                          <div className="space-y-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <StatusBadge tone={toneFromSeverity(entry.severity)}>
                                {formatSeverityLabel(entry.severity)}
                              </StatusBadge>
                              <StatusBadge size="sm" tone={toneFromFindingConfidence(entry.confidence)}>
                                {confidenceLabel}
                              </StatusBadge>
                              <StatusBadge size="sm" tone={toneFromFindingProofType(entry.proof_type)}>
                                {proofLabel}
                              </StatusBadge>
                              <StatusBadge size="sm" tone={toneFromFindingVerificationState(entry.verification_state)}>
                                {verificationLabel}
                              </StatusBadge>
                            </div>
                            <div>
                              <p className="font-semibold text-slate-950">{entry.title}</p>
                              <p className="mt-1 text-sm text-slate-500">{entry.impact_summary}</p>
                              <p className="mt-1 text-xs font-mono uppercase tracking-[0.16em] text-slate-400">
                                {attributionLabel || `Surfaced ${formatRelativeTime(entry.created_at)}`}
                              </p>
                            </div>
                          </div>
                        </td>
                        {hasTrustSignals ? (
                          <td className="px-4 py-4">
                            {trustScore !== null && trustScore !== undefined ? (
                              <div className="space-y-2">
                                <p className="font-mono text-2xl font-semibold text-slate-950">{formatScore(trustScore)}</p>
                                {trustTier ? <StatusBadge tone={trustTier.tone}>{trustTier.label}</StatusBadge> : null}
                              </div>
                            ) : (
                              <span className="font-mono text-sm text-slate-500">N/A</span>
                            )}
                          </td>
                        ) : null}
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
                                  View audit
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
