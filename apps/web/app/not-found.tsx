import Link from "next/link";

import { DemoLaunchButton } from "@/components/DemoLaunchButton";
import { EmptyState } from "@/components/EmptyState";
import { PageShell, pageActionClassName } from "@/components/PageShell";

export default function NotFound() {
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
      <EmptyState
        eyebrow="Route not found"
        title="This page does not exist in the audit workspace"
        description="The route you opened is not available in this build. Start another audit, or jump into the flagship demo room for the strongest walkthrough."
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
    </PageShell>
  );
}
