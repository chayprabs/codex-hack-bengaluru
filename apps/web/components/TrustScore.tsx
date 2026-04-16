import type { ScoreUpdateEvent } from "@/lib/types";
import { formatDateTime, formatScore, formatScoreDelta } from "@/lib/format";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/StatusBadge";

type TrustScoreProps = {
  score?: number | null;
  previousScore?: number | null;
  delta?: number | null;
  label?: string | null;
  updatedAt?: string | null;
  event?: ScoreUpdateEvent | null;
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

function TrustScoreSkeleton() {
  return (
    <div className="space-y-4" aria-hidden="true">
      <div className="h-4 w-28 animate-pulse rounded-full bg-slate-200" />
      <div className="h-14 w-32 animate-pulse rounded-2xl bg-slate-100" />
      <div className="h-3 w-full animate-pulse rounded-full bg-slate-100" />
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="h-14 animate-pulse rounded-2xl bg-slate-100" />
        <div className="h-14 animate-pulse rounded-2xl bg-slate-100" />
      </div>
    </div>
  );
}

export function TrustScore({
  score,
  previousScore,
  delta,
  label,
  updatedAt,
  event,
  isLoading = false,
  min = 0,
  max = 100,
  className,
}: Readonly<TrustScoreProps>) {
  const resolvedScore = event?.score ?? score ?? null;
  const resolvedPreviousScore = event?.previous_score ?? previousScore ?? null;
  const resolvedLabel = event?.label ?? label ?? "Trust score";
  const resolvedUpdatedAt = event?.created_at ?? updatedAt ?? null;
  const resolvedDelta =
    event?.delta ?? delta ?? (resolvedScore !== null && resolvedPreviousScore !== null ? resolvedScore - resolvedPreviousScore : null);

  if (isLoading) {
    return (
      <section className={cn("rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6", className)}>
        <TrustScoreSkeleton />
      </section>
    );
  }

  const numericScore = resolvedScore ?? 0;
  const percentage = max > min ? ((clamp(numericScore, min, max) - min) / (max - min)) * 100 : 0;
  const tone = toneFromScore(clamp(numericScore, min, max), max);

  return (
    <section className={cn("rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6", className)}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Score</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">{resolvedLabel}</h2>
        </div>
        <StatusBadge tone={tone} mono>
          {resolvedScore === null ? "Unavailable" : `${formatScore(numericScore)}/${formatScore(max)}`}
        </StatusBadge>
      </div>

      <div className="mt-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="font-mono text-5xl font-semibold tracking-[-0.04em] text-slate-950">
            {resolvedScore === null ? "N/A" : formatScore(numericScore)}
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Confidence-style summary for the latest audit snapshot.
          </p>
        </div>

        {resolvedDelta !== null ? (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Delta</p>
            <p className="mt-2 font-mono text-lg font-semibold text-slate-950">{formatScoreDelta(resolvedDelta)}</p>
          </div>
        ) : null}
      </div>

      <div className="mt-6">
        <div
          className="h-3 overflow-hidden rounded-full bg-slate-100"
          role="meter"
          aria-label="Trust score"
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={resolvedScore ?? undefined}
        >
          <div
            className={cn(
              "h-full rounded-full transition-[width]",
              tone === "success" && "bg-emerald-500/70",
              tone === "warning" && "bg-amber-500/70",
              tone === "danger" && "bg-rose-500/70",
            )}
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>

      <dl className="mt-6 grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Previous</dt>
          <dd className="mt-2 font-mono text-base font-semibold text-slate-950">
            {resolvedPreviousScore === null ? "N/A" : formatScore(resolvedPreviousScore)}
          </dd>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Updated</dt>
          <dd className="mt-2 font-mono text-base font-semibold text-slate-950">
            {resolvedUpdatedAt ? formatDateTime(resolvedUpdatedAt) : "Unknown"}
          </dd>
        </div>
      </dl>
    </section>
  );
}
