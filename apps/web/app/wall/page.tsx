import Link from "next/link";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageShell, pageActionClassName } from "@/components/PageShell";
import { StatusBadge, formatSeverityBadgeLabel, type StatusBadgeTone } from "@/components/StatusBadge";
import { WallTable } from "@/components/WallTable";
import { formatScore } from "@/lib/format";
import { getApiErrorMessage, getApiErrorStatus, getWall } from "@/lib/api";
import type { FindingSeverity, WallEntry } from "@/lib/types";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

type WallPageProps = {
  searchParams?: Promise<{
    severity?: string | string[];
  }>;
};

type SeverityFilter = "all" | FindingSeverity;

type TrustTier = {
  label: string;
  tone: StatusBadgeTone;
};

const filterChipClassName =
  "inline-flex min-h-10 items-center rounded-full border px-4 py-2 text-sm font-semibold transition focus:outline-none focus:ring-4 focus:ring-slate-200";

const severityOrder: SeverityFilter[] = ["all", "critical", "high", "medium", "low"];

const severityScoreMap: Record<FindingSeverity, number> = {
  critical: 24,
  high: 43,
  medium: 68,
  low: 86,
};

function parseSeverityFilter(raw: string | string[] | undefined): SeverityFilter {
  const value = Array.isArray(raw) ? raw[0] : raw;

  if (value === "critical" || value === "high" || value === "medium" || value === "low") {
    return value;
  }

  return "all";
}

function severityWeight(severity: FindingSeverity) {
  switch (severity) {
    case "critical":
      return 4;
    case "high":
      return 3;
    case "medium":
      return 2;
    default:
      return 1;
  }
}

function deriveTrustScore(entry: WallEntry) {
  return severityScoreMap[entry.severity];
}

function deriveTrustTier(score: number): TrustTier {
  if (score >= 80) {
    return { label: "Stable", tone: "success" };
  }

  if (score >= 60) {
    return { label: "Watch", tone: "warning" };
  }

  if (score >= 40) {
    return { label: "Fragile", tone: "danger" };
  }

  return { label: "Critical", tone: "critical" };
}

function sortEntries(entries: WallEntry[]) {
  return [...entries].sort((left, right) => {
    const severityDelta = severityWeight(right.severity) - severityWeight(left.severity);

    if (severityDelta !== 0) {
      return severityDelta;
    }

    return Date.parse(right.created_at) - Date.parse(left.created_at);
  });
}

function buildFilterHref(filter: SeverityFilter) {
  return filter === "all" ? "/wall" : `/wall?severity=${filter}`;
}

function countBySeverity(entries: WallEntry[], severity: FindingSeverity) {
  return entries.filter((entry) => entry.severity === severity).length;
}

function MetricCard({
  label,
  value,
  detail,
}: Readonly<{ label: string; value: string; detail: string }>) {
  return (
    <div className="rounded-[1.5rem] border border-slate-200 bg-white/90 p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className="mt-3 font-mono text-3xl font-semibold tracking-[-0.04em] text-slate-950">{value}</p>
      <p className="mt-3 text-sm leading-6 text-slate-600">{detail}</p>
    </div>
  );
}

export default async function WallPage({ searchParams }: WallPageProps) {
  const resolvedSearchParams = searchParams ? await searchParams : undefined;
  const selectedFilter = parseSeverityFilter(resolvedSearchParams?.severity);

  try {
    const allEntries = sortEntries(await getWall());
    const filteredEntries =
      selectedFilter === "all"
        ? allEntries
        : allEntries.filter((entry) => entry.severity === selectedFilter);
    const affectedRepos = new Set(allEntries.map((entry) => entry.repo_url)).size;
    const weakestTrustScore = allEntries.length ? Math.min(...allEntries.map(deriveTrustScore)) : null;

    return (
      <PageShell
        actions={
          <Link href="/" className={pageActionClassName}>
            Back to audits
          </Link>
        }
      >
        <header className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Audit wall</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-slate-950 sm:text-5xl">
            The highest-risk findings, ranked
          </h1>
          <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600 sm:text-lg">
            See the issues that matter most across seeded demos and live scans.
          </p>
        </header>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Findings"
            value={String(allEntries.length)}
            detail="Issues currently visible on the wall."
          />
          <MetricCard
            label="Critical"
            value={String(countBySeverity(allEntries, "critical"))}
            detail="Highest-risk findings currently ranked at the top."
          />
          <MetricCard
            label="Repos affected"
            value={String(affectedRepos)}
            detail="Unique repositories represented on the wall right now."
          />
          <MetricCard
            label="Lowest score"
            value={weakestTrustScore === null ? "N/A" : formatScore(weakestTrustScore)}
            detail="Lowest severity-derived score in the current feed."
          />
        </section>

        <section className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Filters</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">Filter by severity</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Keep the list readable during a demo.
              </p>
            </div>
            <StatusBadge mono>{filteredEntries.length} visible</StatusBadge>
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            {severityOrder.map((filter) => {
              const isActive = filter === selectedFilter;
              const label = filter === "all" ? "All" : formatSeverityBadgeLabel(filter);
              const count =
                filter === "all" ? allEntries.length : allEntries.filter((entry) => entry.severity === filter).length;

              return (
                <Link
                  key={filter}
                  href={buildFilterHref(filter)}
                  className={cn(
                    filterChipClassName,
                    isActive
                      ? "border-slate-900 bg-slate-900 text-white"
                      : "border-slate-200 bg-slate-50 text-slate-700 hover:border-slate-300 hover:bg-white",
                  )}
                  aria-current={isActive ? "page" : undefined}
                >
                  {label}
                  <span
                    className={cn(
                      "ml-2 inline-flex min-w-7 items-center justify-center rounded-full px-2 py-0.5 text-xs font-mono",
                      isActive ? "bg-white/15 text-white" : "bg-white text-slate-700",
                    )}
                  >
                    {count}
                  </span>
                </Link>
              );
            })}
          </div>
        </section>

        {allEntries.length === 0 ? (
          <EmptyState
            title="No findings yet"
            description="Start an audit and this page will begin filling with ranked findings."
            action={
              <div className="flex flex-wrap gap-3">
                <Link href="/" className={pageActionClassName}>
                  Start audit
                </Link>
              </div>
            }
          />
        ) : filteredEntries.length === 0 ? (
          <EmptyState
            title="No entries match this filter"
            description="There are findings on the wall, but none at this severity."
            action={
              <div className="flex flex-wrap gap-3">
                <Link href="/wall" className={pageActionClassName}>
                  Show all
                </Link>
                <Link href="/" className={pageActionClassName}>
                  Start audit
                </Link>
              </div>
            }
          />
        ) : (
          <WallTable
            entries={filteredEntries}
            title="Ranked findings"
            description="Scores below are estimated from severity until wall entries expose a first-class score."
            getAuditHref={(entry) => `/audit/${entry.audit_id}`}
            rankEntries
            getTrustScore={deriveTrustScore}
            getTrustTier={(entry) => deriveTrustTier(deriveTrustScore(entry))}
          />
        )}
      </PageShell>
    );
  } catch (error) {
    return (
      <PageShell
        maxWidth="5xl"
        actions={
          <Link href="/" className={pageActionClassName}>
            Back to audits
          </Link>
        }
      >
        <ErrorState
          title="Wall unavailable"
          description="Could not load the wall feed."
          message={getApiErrorMessage(error)}
          code={getApiErrorStatus(error)}
          action={
            <div className="flex flex-wrap gap-3">
              <Link href="/" className={pageActionClassName}>
                Back to audits
              </Link>
            </div>
          }
        />
      </PageShell>
    );
  }
}
