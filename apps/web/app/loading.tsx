import { PageShell } from "@/components/PageShell";

function LoadingCard() {
  return (
    <div className="rounded-[1.5rem] border border-slate-200 bg-white/90 p-5 shadow-sm" aria-hidden="true">
      <div className="h-4 w-28 animate-pulse rounded-full bg-slate-200" />
      <div className="mt-4 h-10 w-full max-w-md animate-pulse rounded-2xl bg-slate-100" />
      <div className="mt-4 h-4 w-full animate-pulse rounded-full bg-slate-100" />
      <div className="mt-3 h-4 w-5/6 animate-pulse rounded-full bg-slate-100" />
    </div>
  );
}

export default function Loading() {
  return (
    <PageShell>
      <section className="rounded-[1.75rem] border border-slate-200 bg-[linear-gradient(135deg,rgba(255,255,255,0.97),rgba(248,250,252,0.94))] p-5 shadow-sm sm:p-6">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Loading route</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-slate-950">Preparing the audit workspace</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
          Pulling the right landing, audit, and wall state so the demo opens without blank screens or route crashes.
        </p>
      </section>

      <div className="grid gap-4 xl:grid-cols-2">
        <LoadingCard />
        <LoadingCard />
      </div>
    </PageShell>
  );
}
