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
            New audit
          </Link>
          <Link href="/wall" className={pageActionClassName}>
            View wall
          </Link>
        </>
      }
    >
      <EmptyState
        eyebrow="Route not found"
        title="This page is not available"
        description="The route you opened is not part of this build. Start a new audit or open the demo."
        action={
          <div className="flex flex-wrap gap-3">
            <DemoLaunchButton />
            <Link href="/" className={pageActionClassName}>
              Back to home
            </Link>
            <Link href="/wall" className={pageActionClassName}>
              View wall
            </Link>
          </div>
        }
      />
    </PageShell>
  );
}
