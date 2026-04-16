import type { Audit } from "@/lib/types";
import { buildFindingBuckets, summarizeQuietBuckets } from "@/lib/findingBuckets";
import { cn, titleCase } from "@/lib/utils";
import { StatusBadge, toneFromSeverity } from "@/components/StatusBadge";

type FindingBucketSummaryProps = {
  audit: Audit;
  className?: string;
};

function pluralize(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

function bucketCardTone(severity: Audit["findings"][number]["severity"] | null) {
  switch (severity) {
    case "critical":
    case "high":
      return "border-rose-200 bg-[linear-gradient(135deg,rgba(255,241,242,0.94),rgba(255,255,255,0.98))]";
    case "medium":
      return "border-amber-200 bg-[linear-gradient(135deg,rgba(255,251,235,0.94),rgba(255,255,255,0.98))]";
    case "low":
      return "border-slate-200 bg-[linear-gradient(135deg,rgba(248,250,252,0.94),rgba(255,255,255,0.98))]";
    default:
      return "border-slate-200 bg-white/88";
  }
}

export function FindingBucketSummary({ audit, className }: Readonly<FindingBucketSummaryProps>) {
  const buckets = buildFindingBuckets(audit.findings);
  const activeBuckets = buckets.filter((bucket) => bucket.count > 0);
  const quietBuckets = summarizeQuietBuckets(buckets);

  if (!activeBuckets.length) {
    return null;
  }

  return (
    <section
      className={cn("rounded-[1.75rem] border border-slate-200 bg-white/92 p-5 shadow-sm sm:p-6", className)}
      aria-label="Risk buckets"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Risk buckets</p>
          <h3 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">Where the risk clustered</h3>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            {pluralize(activeBuckets.length, "bucket")} lit up in this run. Read left to right: the problem group, why it matters, and the first lines worth opening in the full findings list.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge mono>{pluralize(audit.findings.length, "finding")}</StatusBadge>
          <StatusBadge tone={audit.confidence_limited ? "warning" : "info"} mono>
            {titleCase(audit.coverage_band)} coverage
          </StatusBadge>
        </div>
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-2">
        {activeBuckets.map((bucket) => (
          <article key={bucket.id} className={cn("rounded-[1.5rem] border p-5", bucketCardTone(bucket.highestSeverity))}>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Bucket</p>
                <h4 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-slate-950">{bucket.label}</h4>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge mono>{pluralize(bucket.count, "finding")}</StatusBadge>
                {bucket.highestSeverity ? (
                  <StatusBadge tone={toneFromSeverity(bucket.highestSeverity)}>{titleCase(bucket.highestSeverity)}</StatusBadge>
                ) : null}
              </div>
            </div>

            <p className="mt-4 text-sm leading-6 text-slate-700">{bucket.quickTake}</p>

            <div className="mt-5 grid gap-3 lg:grid-cols-[0.95fr_1.05fr]">
              <div className="rounded-[1.25rem] border border-white/80 bg-white/82 px-4 py-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Start here</p>
                <p className="mt-2 text-sm leading-6 text-slate-700">{bucket.fixHint}</p>
              </div>

              <div className="rounded-[1.25rem] border border-white/80 bg-white/82 px-4 py-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Lead signals</p>
                <div className="mt-3 space-y-2">
                  {bucket.examples.map((example) => (
                    <p key={example} className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-700">
                      {example}
                    </p>
                  ))}
                </div>
              </div>
            </div>
          </article>
        ))}
      </div>

      {quietBuckets.length ? (
        <div className="mt-5 rounded-[1.25rem] border border-slate-200 bg-slate-50/80 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Quiet buckets</p>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            No published findings landed in: {quietBuckets.join(", ")}.
          </p>
        </div>
      ) : null}
    </section>
  );
}
