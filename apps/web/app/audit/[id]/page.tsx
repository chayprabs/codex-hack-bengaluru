import Link from "next/link";

import { DemoLaunchButton } from "@/components/DemoLaunchButton";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { PageShell, pageActionClassName } from "@/components/PageShell";
import { getApiErrorMessage, getApiErrorStatus, getAudit } from "@/lib/api";
import { AuditRoomClient } from "./AuditRoomClient";

export const dynamic = "force-dynamic";

type AuditPageProps = {
  params: Promise<{ id: string }>;
};

export default async function AuditPage({ params }: AuditPageProps) {
  const { id } = await params;

  try {
    const audit = await getAudit(id);
    return <AuditRoomClient initialAudit={audit} />;
  } catch (error) {
    const status = getApiErrorStatus(error);
    const message = getApiErrorMessage(error);

    return (
      <PageShell
        maxWidth="4xl"
        actions={
          <>
            <Link href="/" className={pageActionClassName}>
              Run another audit
            </Link>
            <Link href="/wall" className={pageActionClassName}>
              Open audit wall
            </Link>
          </>
        }
      >
        {status === 404 ? (
          <EmptyState
            title="Audit not found"
            description="The requested audit id does not exist in the current API store. Start another audit, or jump straight into the flagship demo room for a predictable walkthrough."
            action={
              <div className="flex flex-wrap gap-3">
                <DemoLaunchButton />
                <Link href="/" className={pageActionClassName}>
                  Run another audit
                </Link>
                <Link href="/wall" className={pageActionClassName}>
                  Open audit wall
                </Link>
              </div>
            }
          />
        ) : (
          <ErrorState
            title="Audit room unavailable"
            description="The audit could not be loaded from the API right now. The flagship demo room is still the safest fallback for a live walkthrough."
            message={message}
            code={status}
            action={
              <div className="flex flex-wrap gap-3">
                <DemoLaunchButton />
                <Link href="/" className={pageActionClassName}>
                  Back to landing page
                </Link>
                <Link href="/wall" className={pageActionClassName}>
                  Open audit wall
                </Link>
              </div>
            }
          />
        )}
      </PageShell>
    );
  }
}
