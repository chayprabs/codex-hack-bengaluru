import Link from "next/link";

import { PageShell, pageActionClassName } from "@/components/PageShell";
import { WallTable } from "@/components/WallTable";

function MetricCardSkeleton() {
  return (
    <div className="rounded-[1.5rem] border border-slate-200 bg-white/90 p-5 shadow-sm" aria-hidden="true">
      <div className="h-4 w-24 animate-pulse rounded-full bg-slate-200" />
      <div className="mt-4 h-10 w-28 animate-pulse rounded-2xl bg-slate-100" />
      <div className="mt-4 h-4 w-full animate-pulse rounded-full bg-slate-100" />
    </div>
  );
}

export default function Loading() {
  return (
    <PageShell
      actions={
        <Link href="/" className={pageActionClassName}>
          Back to auditing
        </Link>
      }
    >
      <section className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6" aria-hidden="true">
        <div className="h-4 w-28 animate-pulse rounded-full bg-slate-200" />
        <div className="mt-4 h-12 w-full max-w-2xl animate-pulse rounded-2xl bg-slate-100" />
        <div className="mt-4 h-5 w-full max-w-3xl animate-pulse rounded-full bg-slate-100" />
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCardSkeleton />
        <MetricCardSkeleton />
        <MetricCardSkeleton />
        <MetricCardSkeleton />
      </section>

      <section className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6" aria-hidden="true">
        <div className="h-4 w-20 animate-pulse rounded-full bg-slate-200" />
        <div className="mt-4 h-8 w-48 animate-pulse rounded-2xl bg-slate-100" />
        <div className="mt-4 h-4 w-full max-w-2xl animate-pulse rounded-full bg-slate-100" />
        <div className="mt-6 flex flex-wrap gap-3">
          {[0, 1, 2, 3, 4].map((item) => (
            <div key={item} className="h-10 w-24 animate-pulse rounded-full bg-slate-100" />
          ))}
        </div>
      </section>

      <WallTable
        isLoading
        title="Ranked findings"
        description="Loading severity-derived trust scores and audit links."
      />
    </PageShell>
  );
}
