import type { ScoreMoment } from "@/lib/auditStory";
import type { CoverageBand, ScoreUpdateEvent } from "@/lib/types";
import { formatDateTime, formatRelativeTime, formatScore, formatScoreDelta } from "@/lib/format";
import { formatAuditLabel, toneFromCoverageBand, unsupportedScopeCount } from "@/lib/coveragePresentation";
import { describeScoreUpdate } from "@/lib/scoreNarrative";
import { cn, titleCase } from "@/lib/utils";
import { StatusBadge } from "@/components/StatusBadge";

type TrustScoreProps = {
  score?: number | null;
  scoreBaseline?: number | null;
  previousScore?: number | null;
  delta?: number | null;
  coverage?: number | null;
  coverageBaseline?: number | null;
  previousCoverage?: number | null;
  coverageDelta?: number | null;
  coverageBand?: CoverageBand | null;
  coverageSummary?: string | null;
  confidenceLimited?: boolean;
  supportedAreas?: string[];
  partiallySupportedAreas?: string[];
  unsupportedAreas?: string[];
  needsManualReviewAreas?: string[];
  unsupportedTechnologies?: string[];
  scannedFilesCount?: number | null;
  skippedFilesCount?: number | null;
  frameworksDetected?: string[];
  checksRun?: string[];
  checksSkipped?: string[];
  label?: string | null;
  updatedAt?: string | null;
  event?: ScoreUpdateEvent | null;
  moments?: ScoreMoment[];
  isLoading?: boolean;
  min?: number;
  max?: number;
  className?: string;
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function toneFromScore(score: number, max: number) {
  const ratio = max > 0 ? score / max : 0;

  if (ratio >= 0.8) {
    return "success";
  }

  if (ratio >= 0.6) {
    return "warning";
  }

  return "danger";
}

function momentToneClasses(tone: ScoreMoment["tone"]) {
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

function scoreFillClasses(tone: ReturnType<typeof toneFromScore>) {
  if (tone === "success") {
    return "bg-[linear-gradient(90deg,rgba(248,113,113,0.72),rgba(245,158,11,0.72),rgba(16,185,129,0.82))]";
  }

  if (tone === "warning") {
    return "bg-[linear-gradient(90deg,rgba(251,113,133,0.78),rgba(245,158,11,0.84))]";
  }

  return "bg-[linear-gradient(90deg,rgba(251,113,133,0.86),rgba(244,63,94,0.92))]";
}

function coverageFillClasses(band: CoverageBand | null | undefined) {
  switch (band) {
    case "deep":
      return "bg-[linear-gradient(90deg,rgba(34,197,94,0.8),rgba(16,185,129,0.9))]";
    case "broad":
      return "bg-[linear-gradient(90deg,rgba(14,165,233,0.72),rgba(6,182,212,0.82))]";
    case "targeted":
      return "bg-[linear-gradient(90deg,rgba(245,158,11,0.74),rgba(251,191,36,0.84))]";
    case "limited":
    case "minimal":
      return "bg-[linear-gradient(90deg,rgba(251,113,133,0.8),rgba(239,68,68,0.9))]";
    default:
      return "bg-slate-400";
  }
}

function summarizeList(values: string[], limit = 3) {
  if (!values.length) {
    return "None";
  }

  const visible = values.slice(0, limit).map(formatAuditLabel);
  const hiddenCount = values.length - visible.length;
  return hiddenCount > 0 ? `${visible.join(", ")} +${hiddenCount} more` : visible.join(", ");
}

function TransitionValue({
  before,
  after,
  fallbackLabel = "N/A",
}: Readonly<{ before: number | null; after: number | null; fallbackLabel?: string }>) {
  if (after === null) {
    return <span>{fallbackLabel}</span>;
  }

  if (before === null || before === after) {
    return <span>{formatScore(after)}</span>;
  }

  return (
    <span className="inline-flex items-center gap-2">
      <span>{formatScore(before)}</span>
      <span className="text-slate-400">-&gt;</span>
      <span>{formatScore(after)}</span>
    </span>
  );
}

function TrustScoreSkeleton() {
  return (
    <div className="space-y-4" aria-hidden="true">
      <div className="h-4 w-32 animate-pulse rounded-full bg-slate-200" />
      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="h-72 animate-pulse rounded-[1.5rem] bg-slate-100" />
        <div className="h-72 animate-pulse rounded-[1.5rem] bg-slate-100" />
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        <div className="h-28 animate-pulse rounded-[1.25rem] bg-slate-100" />
        <div className="h-28 animate-pulse rounded-[1.25rem] bg-slate-100" />
      </div>
    </div>
  );
}

export function TrustScore({
  score,
  scoreBaseline,
  previousScore,
  delta,
  coverage,
  coverageBaseline,
  previousCoverage,
  coverageDelta,
  coverageBand,
  coverageSummary,
  confidenceLimited,
  supportedAreas = [],
  partiallySupportedAreas = [],
  unsupportedAreas = [],
  needsManualReviewAreas = [],
  unsupportedTechnologies = [],
  scannedFilesCount,
  skippedFilesCount,
  frameworksDetected = [],
  checksRun = [],
  checksSkipped = [],
  label,
  updatedAt,
  event,
  moments = [],
  isLoading = false,
  min = 0,
  max = 100,
  className,
}: Readonly<TrustScoreProps>) {
  const resolvedScore = event?.score ?? score ?? null;
  const resolvedCoverage = event?.coverage ?? coverage ?? null;
  const resolvedPreviousScore = event?.previous_score ?? previousScore ?? null;
  const resolvedPreviousCoverage = event?.previous_coverage ?? previousCoverage ?? null;
  const resolvedLabel = label ?? event?.reason ?? "TrustScore";
  const resolvedUpdatedAt = updatedAt ?? event?.updated_at ?? null;
  const resolvedDelta =
    event?.delta ?? delta ?? (resolvedScore !== null && resolvedPreviousScore !== null ? resolvedScore - resolvedPreviousScore : null);
  const resolvedCoverageDelta =
    event?.coverage_delta ??
    coverageDelta ??
    (resolvedCoverage !== null && resolvedPreviousCoverage !== null ? resolvedCoverage - resolvedPreviousCoverage : null);
  const resolvedCoverageBand = event?.coverage_band ?? coverageBand ?? null;
  const resolvedCoverageSummary = event?.coverage_summary ?? coverageSummary ?? null;
  const resolvedConfidenceLimited = event?.confidence_limited ?? confidenceLimited ?? false;
  const meaningfulMoment =
    moments.find((moment) => (moment.delta ?? 0) !== 0 || (moment.coverageDelta ?? 0) !== 0) ?? moments[0] ?? null;
  const resolvedScoreReason =
    event && (((event.delta ?? 0) !== 0) || ((event.coverage_delta ?? 0) !== 0))
      ? describeScoreUpdate(event)
      : meaningfulMoment?.detail ?? (event ? describeScoreUpdate(event) : null);
  const footprintSupportedAreas = event?.supported_areas ?? supportedAreas;
  const footprintPartiallySupportedAreas = event?.partially_supported_areas ?? partiallySupportedAreas;
  const footprintUnsupportedAreas = event?.unsupported_areas ?? unsupportedAreas;
  const footprintNeedsManualReviewAreas = event?.needs_manual_review_areas ?? needsManualReviewAreas;
  const footprintUnsupportedTechnologies = event?.unsupported_technologies ?? unsupportedTechnologies;
  const footprintUnsupportedCount = unsupportedScopeCount(footprintUnsupportedAreas, footprintUnsupportedTechnologies);
  const footprintScannedFilesCount = event?.scanned_files_count ?? scannedFilesCount ?? 0;
  const footprintSkippedFilesCount = event?.skipped_files_count ?? skippedFilesCount ?? 0;
  const footprintFrameworksDetected = event?.frameworks_detected ?? frameworksDetected;
  const footprintChecksRun = event?.checks_run ?? checksRun;
  const footprintChecksSkipped = event?.checks_skipped ?? checksSkipped;
  const hasCoverageFootprint =
    footprintScannedFilesCount > 0 ||
    footprintSkippedFilesCount > 0 ||
    footprintFrameworksDetected.length > 0 ||
    footprintChecksRun.length > 0 ||
    footprintChecksSkipped.length > 0 ||
    footprintSupportedAreas.length > 0 ||
    footprintPartiallySupportedAreas.length > 0 ||
    footprintUnsupportedAreas.length > 0 ||
    footprintNeedsManualReviewAreas.length > 0 ||
    footprintUnsupportedTechnologies.length > 0;

  if (isLoading) {
    return (
      <section className={cn("rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6", className)}>
        <TrustScoreSkeleton />
      </section>
    );
  }

  const numericScore = resolvedScore ?? 0;
  const scorePercentage = max > min ? ((clamp(numericScore, min, max) - min) / (max - min)) * 100 : 0;
  const scoreTone = toneFromScore(clamp(numericScore, min, max), max);
  const numericCoverage = resolvedCoverage ?? 0;
  const coveragePercentage = max > min ? ((clamp(numericCoverage, min, max) - min) / (max - min)) * 100 : 0;
  const coverageTone = toneFromCoverageBand(resolvedCoverageBand);
  const comparisonScoreBaseline = scoreBaseline ?? 100;
  const comparisonCoverageBaseline = coverageBaseline ?? 12;
  const showScoreComparison = resolvedScore !== null && comparisonScoreBaseline !== resolvedScore;
  const showCoverageComparison = resolvedCoverage !== null && comparisonCoverageBaseline !== resolvedCoverage;

  return (
    <section
      className={cn(
        "rounded-[1.75rem] border border-slate-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.97),rgba(248,250,252,0.95))] p-5 shadow-sm sm:p-6",
        className,
      )}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">TrustScore</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
            {resolvedLabel === "TrustScore" ? "TrustScore and Coverage" : `${resolvedLabel} and Coverage`}
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            TrustScore tells you how risky the repo looks. Coverage tells you how much of that call is backed by real review.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge tone={scoreTone} mono>
            TrustScore {resolvedScore === null ? "N/A" : `${formatScore(numericScore)}/100`}
          </StatusBadge>
          <StatusBadge tone={coverageTone} mono>
            Coverage {resolvedCoverage === null ? "N/A" : `${formatScore(numericCoverage)}/100`}
          </StatusBadge>
        </div>
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-[1.12fr_0.88fr]">
        <article
          className={cn(
            "rounded-[1.5rem] border border-slate-200 bg-[linear-gradient(135deg,rgba(255,255,255,0.98),rgba(248,250,252,0.92))] p-5",
            event && "story-card-live",
          )}
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">TrustScore</p>
              <p className="mt-4 font-mono text-6xl font-semibold tracking-[-0.05em] text-slate-950">
                {resolvedScore === null ? "N/A" : formatScore(numericScore)}
              </p>
            </div>
            <StatusBadge tone={scoreTone} mono>
              {resolvedScore === null ? "Unavailable" : `${formatScore(numericScore)}/100`}
            </StatusBadge>
          </div>

          <p className="mt-4 text-sm leading-6 text-slate-600">
            This score moves when risk meaningfully changes.
          </p>

          <div className="mt-5">
            <div
              className="h-3 overflow-hidden rounded-full bg-slate-100"
              role="meter"
              aria-label="Trust score"
              aria-valuemin={min}
              aria-valuemax={max}
              aria-valuenow={resolvedScore ?? undefined}
            >
              <div
                className={cn("h-full rounded-full transition-[width] duration-700", scoreFillClasses(scoreTone))}
                style={{ width: `${scorePercentage}%` }}
              />
            </div>
          </div>

          <dl className="mt-5 grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-white/80 px-4 py-3">
              <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Before -&gt; After</dt>
              <dd className="mt-2 font-mono text-base font-semibold text-slate-950">
                {showScoreComparison ? (
                  <TransitionValue before={comparisonScoreBaseline} after={resolvedScore} />
                ) : (
                  <span>{resolvedScore === null ? "N/A" : formatScore(numericScore)}</span>
                )}
              </dd>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white/80 px-4 py-3">
              <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Latest shift</dt>
              <dd className="mt-2 font-mono text-base font-semibold text-slate-950">
                {resolvedDelta === null ? "N/A" : formatScoreDelta(resolvedDelta)}
              </dd>
            </div>
          </dl>

          {resolvedScoreReason ? (
            <div className="mt-5 rounded-[1.25rem] border border-slate-200 bg-slate-50/90 px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Latest explanation</p>
              <p className="mt-3 text-sm leading-6 text-slate-700">{resolvedScoreReason}</p>
            </div>
          ) : null}
        </article>

        <article className="rounded-[1.5rem] border border-slate-200 bg-white/85 p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Coverage</p>
              <p className="mt-4 font-mono text-5xl font-semibold tracking-[-0.05em] text-slate-950">
                {resolvedCoverage === null ? "N/A" : formatScore(numericCoverage)}
              </p>
            </div>
            <StatusBadge tone={coverageTone} mono>
              {resolvedCoverageBand ? titleCase(resolvedCoverageBand) : "Pending"}
            </StatusBadge>
          </div>

          <p className="mt-4 text-sm leading-6 text-slate-600">
            Coverage shows how much of the repo was actually checked and reviewed.
          </p>

          <div className="mt-5">
            <div
              className="h-3 overflow-hidden rounded-full bg-slate-100"
              role="meter"
              aria-label="Coverage"
              aria-valuemin={min}
              aria-valuemax={max}
              aria-valuenow={resolvedCoverage ?? undefined}
            >
              <div
                className={cn("h-full rounded-full transition-[width] duration-700", coverageFillClasses(resolvedCoverageBand))}
                style={{ width: `${coveragePercentage}%` }}
              />
            </div>
          </div>

          <dl className="mt-5 grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
              <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Before -&gt; After</dt>
              <dd className="mt-2 font-mono text-base font-semibold text-slate-950">
                {showCoverageComparison ? (
                  <TransitionValue before={comparisonCoverageBaseline} after={resolvedCoverage} />
                ) : (
                  <span>{resolvedCoverage === null ? "N/A" : formatScore(numericCoverage)}</span>
                )}
              </dd>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
              <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Latest shift</dt>
              <dd className="mt-2 font-mono text-base font-semibold text-slate-950">
                {resolvedCoverageDelta === null ? "N/A" : formatScoreDelta(resolvedCoverageDelta)}
              </dd>
            </div>
          </dl>

          <div
            className={cn(
              "mt-5 rounded-[1.25rem] border px-4 py-4",
              resolvedConfidenceLimited ? "border-amber-200 bg-amber-50/90" : "border-slate-200 bg-slate-50/90",
            )}
          >
            <p
              className={cn(
                "text-xs font-semibold uppercase tracking-[0.18em]",
                resolvedConfidenceLimited ? "text-amber-700" : "text-slate-500",
              )}
            >
              {resolvedConfidenceLimited ? "Limited by scope" : "Score support"}
            </p>
            <p className={cn("mt-3 text-sm leading-6", resolvedConfidenceLimited ? "text-amber-900" : "text-slate-700")}>
              {resolvedCoverageSummary ??
                "Coverage rises as the scan expands and findings are reviewed."}
            </p>
          </div>
        </article>
      </div>

      <dl className="mt-6 grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Updated</dt>
          <dd className="mt-2 font-mono text-base font-semibold text-slate-950">
            {resolvedUpdatedAt ? formatDateTime(resolvedUpdatedAt) : "Unknown"}
          </dd>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Live status</dt>
          <dd className="mt-2 font-mono text-base font-semibold text-slate-950">
            {resolvedUpdatedAt ? formatRelativeTime(resolvedUpdatedAt) : "Unknown"}
          </dd>
        </div>
      </dl>

      {hasCoverageFootprint ? (
        <div className="mt-6 rounded-[1.25rem] border border-slate-200 bg-white/82 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">What was checked</p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Quick proof of what this score is based on.
              </p>
            </div>
          </div>

          <div className="mt-4 grid gap-3 xl:grid-cols-2">
            <div className="rounded-[1.25rem] border border-slate-200 bg-slate-50 px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Execution</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Files</p>
                  <p className="mt-2 font-mono text-base font-semibold text-slate-950">{footprintScannedFilesCount}</p>
                  <p className="mt-1 text-sm text-slate-600">
                    {footprintSkippedFilesCount > 0 ? `${footprintSkippedFilesCount} skipped` : "No skipped files recorded"}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Checks run</p>
                  <p className="mt-2 font-mono text-base font-semibold text-slate-950">{footprintChecksRun.length}</p>
                  <p className="mt-1 text-sm text-slate-600">
                    {footprintChecksSkipped.length > 0 ? `${footprintChecksSkipped.length} skipped` : "No skipped checks recorded"}
                  </p>
                </div>
              </div>
              <p className="mt-4 text-sm leading-6 text-slate-600">
                {footprintChecksRun.length > 0 ? summarizeList(footprintChecksRun) : "No named checks yet."}
              </p>
            </div>

            <div className="rounded-[1.25rem] border border-slate-200 bg-slate-50 px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Scope</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Frameworks</p>
                  <p className="mt-2 font-mono text-base font-semibold text-slate-950">{footprintFrameworksDetected.length}</p>
                  <p className="mt-1 text-sm text-slate-600">{summarizeList(footprintFrameworksDetected)}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Supported areas</p>
                  <p className="mt-2 font-mono text-base font-semibold text-slate-950">{footprintSupportedAreas.length}</p>
                  <p className="mt-1 text-sm text-slate-600">{summarizeList(footprintSupportedAreas)}</p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <StatusBadge tone="success" mono size="sm">
                  Supported {footprintSupportedAreas.length}
                </StatusBadge>
                <StatusBadge tone="warning" mono size="sm">
                  Partially supported {footprintPartiallySupportedAreas.length}
                </StatusBadge>
                <StatusBadge tone="neutral" mono size="sm">
                  Unsupported {footprintUnsupportedCount}
                </StatusBadge>
                <StatusBadge tone="info" mono size="sm">
                  Needs manual review {footprintNeedsManualReviewAreas.length}
                </StatusBadge>
              </div>
              {(footprintPartiallySupportedAreas.length > 0 ||
                footprintUnsupportedAreas.length > 0 ||
                footprintNeedsManualReviewAreas.length > 0 ||
                footprintUnsupportedTechnologies.length > 0) ? (
                <div className="mt-4 space-y-2 text-sm leading-6 text-slate-600">
                  {footprintPartiallySupportedAreas.length > 0 ? (
                    <p>Partially supported: {summarizeList(footprintPartiallySupportedAreas)}.</p>
                  ) : null}
                  {footprintUnsupportedAreas.length > 0 ? (
                    <p>Unsupported: {summarizeList(footprintUnsupportedAreas)}.</p>
                  ) : null}
                  {footprintUnsupportedTechnologies.length > 0 ? (
                    <p>Unsupported tech: {summarizeList(footprintUnsupportedTechnologies)}.</p>
                  ) : null}
                  {footprintNeedsManualReviewAreas.length > 0 ? (
                    <p>Needs manual review: {summarizeList(footprintNeedsManualReviewAreas)}.</p>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {moments.length > 0 ? (
        <div className="mt-6 rounded-[1.25rem] border border-slate-200 bg-white/80 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Score updates</p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Each update explains why the score moved.
              </p>
            </div>
          </div>

          <div className="mt-4 grid gap-3 xl:grid-cols-2">
            {moments.slice(0, 4).map((moment) => (
              <article
                key={moment.id}
                className={cn(
                  "rounded-[1.25rem] border px-4 py-4 transition-transform",
                  momentToneClasses(moment.tone),
                  moment.highlight && "story-card-live",
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{moment.label}</p>
                  <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-slate-500">
                    {formatRelativeTime(moment.updatedAt)}
                  </p>
                </div>

                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-2xl border border-white/70 bg-white/70 px-3 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">TrustScore</p>
                    <p className="mt-2 font-mono text-base font-semibold text-slate-950">
                      <TransitionValue before={moment.previousScore} after={moment.score} />
                    </p>
                  </div>
                  <div className="rounded-2xl border border-white/70 bg-white/70 px-3 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Coverage</p>
                    <p className="mt-2 font-mono text-base font-semibold text-slate-950">
                      <TransitionValue before={moment.previousCoverage} after={moment.coverage} />
                    </p>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {moment.delta !== null ? (
                    <span className="rounded-full border border-slate-200 bg-white/80 px-3 py-1 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-slate-700">
                      Score {formatScoreDelta(moment.delta)}
                    </span>
                  ) : null}
                  {moment.coverageDelta !== null ? (
                    <span className="rounded-full border border-slate-200 bg-white/80 px-3 py-1 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-slate-700">
                      Coverage {formatScoreDelta(moment.coverageDelta)}
                    </span>
                  ) : null}
                  <StatusBadge tone={toneFromCoverageBand(moment.coverageBand)} mono>
                    {titleCase(moment.coverageBand)}
                  </StatusBadge>
                </div>

                <p className="mt-3 text-sm leading-6 text-slate-600">{moment.detail}</p>
                {moment.confidenceLimited ? (
                  <p className="mt-2 text-sm font-medium text-amber-800">Coverage was still limited here, so this was not a final call.</p>
                ) : null}
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
