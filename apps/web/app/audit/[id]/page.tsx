import Link from "next/link";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { getApiErrorMessage, getApiErrorStatus, getAudit } from "@/lib/api";
import { AuditRoomClient } from "./AuditRoomClient";

export const dynamic = "force-dynamic";

type AuditPageProps = {
  params: Promise<{ id: string }>;
};

const pageActionClassName =
  "inline-flex min-h-10 items-center rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 transition hover:border-slate-300 hover:bg-slate-50 focus:outline-none focus:ring-4 focus:ring-slate-200";

export default async function AuditPage({ params }: AuditPageProps) {
  const { id } = await params;

  try {
    const audit = await getAudit(id);
    return <AuditRoomClient initialAudit={audit} />;
  } catch (error) {
    const status = getApiErrorStatus(error);
    const message = getApiErrorMessage(error);

    return (
      <main className="min-h-screen bg-transparent">
        <section className="mx-auto max-w-4xl px-4 py-10 sm:px-6 lg:px-8">
          {status === 404 ? (
            <EmptyState
              title="Audit not found"
              description="The requested audit id does not exist in the current API store. Start a new audit to create a fresh room."
              action={
                <div className="flex flex-wrap gap-3">
                  <Link href="/" className={pageActionClassName}>
                    Start a new audit
                  </Link>
                  <Link href="/wall" className={pageActionClassName}>
                    Open shame wall
                  </Link>
                </div>
              }
            />
          ) : (
            <ErrorState
              title="Audit room unavailable"
              description="The audit could not be loaded from the API right now."
              message={message}
              code={status}
              action={
                <div className="flex flex-wrap gap-3">
                  <Link href="/" className={pageActionClassName}>
                    Back to landing page
                  </Link>
                  <Link href="/wall" className={pageActionClassName}>
                    Open shame wall
                  </Link>
                </div>
              }
            />
          )}
        </section>
      </main>
    );
  }
}
