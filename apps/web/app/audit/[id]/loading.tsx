import Link from "next/link";

import { AgentCard } from "@/components/AgentCard";
import { AuditHeader } from "@/components/AuditHeader";
import { AuditStatusBar } from "@/components/AuditStatusBar";
import { FindingFeed } from "@/components/FindingFeed";
import { PageShell, pageActionClassName } from "@/components/PageShell";
import { TrustScore } from "@/components/TrustScore";

export default function Loading() {
  return (
    <PageShell
      actions={
        <>
          <Link href="/" className={pageActionClassName}>
            New audit
          </Link>
          <Link href="/wall" className={pageActionClassName}>
            View shame wall
          </Link>
        </>
      }
    >
      <AuditHeader auditId="loading" repoUrl="Loading repository..." findingsCount={0} isLoading />

      <AuditStatusBar status="queued" agents={[]} findingsCount={0} transportLabel="Loading" isLoading />

      <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <TrustScore isLoading />

        <section className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Agents</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">Audit lanes</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Loading the latest planner, scanner, and verifier status.
            </p>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <AgentCard isLoading />
            <AgentCard isLoading />
            <AgentCard isLoading />
          </div>
        </section>
      </div>

      <FindingFeed
        isLoading
        title="Finding feed"
        description="Loading findings and evidence from the latest audit snapshot."
      />
    </PageShell>
  );
}
