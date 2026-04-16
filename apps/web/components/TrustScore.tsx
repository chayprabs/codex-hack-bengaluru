import type { ScoreMoment } from "@/lib/auditStory";
import type { CoverageBand, ScoreUpdateEvent } from "@/lib/types";
import { formatDateTime, formatRelativeTime, formatScore, formatScoreDelta } from "@/lib/format";
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

function toneFromCoverageBand(band: CoverageBand | null | undefined) {
  switch (band) {
    case "deep":
      return "success";
    case "broad":
      return "info";
    case "targeted":
      return "warning";
    case "limited":
    case "minimal":
      return "danger";
    default:
      return "neutral";
  }
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
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Score system</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">{resolvedLabel}</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            TrustScore is the hero metric for risk posture. Coverage sits beside it to show how much real evidence and verification the score is standing on.
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
            A calibrated posture score derived from surfaced findings and final verification state, not from raw scanner volume alone.
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
              <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Live delta</dt>
              <dd className="mt-2 font-mono text-base font-semibold text-slate-950">
                {resolvedDelta === null ? "N/A" : formatScoreDelta(resolvedDelta)}
              </dd>
            </div>
          </dl>
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
            Coverage measures how much of the repository was actually acquired, scoped, executed by specialist lanes, and carried through verifier closeout.
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
              <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Latest move</dt>
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
              {resolvedConfidenceLimited ? "Confidence limited" : "Credibility signal"}
            </p>
            <p className={cn("mt-3 text-sm leading-6", resolvedConfidenceLimited ? "text-amber-900" : "text-slate-700")}>
              {resolvedCoverageSummary ??
                "Coverage will rise as the repo is acquired, specialist lanes complete, and verification closes the report."}
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

      {moments.length > 0 ? (
        <div className="mt-6 rounded-[1.25rem] border border-slate-200 bg-white/80 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Score change moments</p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Each update shows both posture and credibility so the score system feels explainable instead of arbitrary.
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
                  <p className="mt-2 text-sm font-medium text-amber-800">Coverage was still limited at this point, so confidence remained constrained.</p>
                ) : null}
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
