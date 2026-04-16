"use client";

import { useEffect } from "react";
import Link from "next/link";

import { ErrorState } from "@/components/ErrorState";
import { PageShell, pageActionClassName } from "@/components/PageShell";

type GlobalErrorProps = Readonly<{
  error: Error & { digest?: string };
  reset: () => void;
}>;

export default function GlobalError({ error, reset }: GlobalErrorProps) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <PageShell
      maxWidth="5xl"
      actions={
        <Link href="/" className={pageActionClassName}>
          Back to audits
        </Link>
      }
    >
      <ErrorState
        title="Route failed to render"
        description="The app hit an unexpected rendering error. Retry the route, or jump back to the stable demo and wall paths."
        message={error.message}
        action={
          <div className="flex flex-wrap gap-3">
            <button type="button" onClick={reset} className={pageActionClassName}>
              Retry route
            </button>
            <Link href="/audit/demo" className={pageActionClassName}>
              Open demo room
            </Link>
            <Link href="/wall" className={pageActionClassName}>
              Open wall
            </Link>
          </div>
        }
      />
    </PageShell>
  );
}
