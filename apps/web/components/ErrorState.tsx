import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type ErrorStateProps = {
  title?: string;
  description?: string;
  message?: string | null;
  code?: number | null;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
};

export function ErrorState({
  title = "Something went wrong",
  description = "Could not load the latest audit data.",
  message,
  code,
  action,
  className,
  compact = false,
}: Readonly<ErrorStateProps>) {
  return (
    <section
      className={cn(
        "rounded-[1.5rem] border border-rose-200 bg-[linear-gradient(135deg,rgba(255,241,242,0.96),rgba(255,255,255,0.92))] text-rose-900",
        compact ? "p-5" : "p-6 sm:p-8",
        className,
      )}
      role="alert"
    >
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-rose-600">Error</p>
      <h2 className="mt-3 text-xl font-semibold tracking-[-0.03em] text-rose-950 sm:text-2xl">{title}</h2>
      <p className="mt-3 text-sm leading-6 text-rose-800 sm:text-base">{description}</p>

      {message || code !== null && code !== undefined ? (
        <dl className="mt-5 grid gap-3 rounded-2xl border border-rose-200/80 bg-white/70 p-4 text-sm">
          {code !== null && code !== undefined ? (
            <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
              <dt className="font-semibold text-rose-700">Status</dt>
              <dd className="font-mono text-rose-900">{code}</dd>
            </div>
          ) : null}
          {message ? (
            <div className="flex flex-col gap-1">
              <dt className="font-semibold text-rose-700">Details</dt>
              <dd className="font-mono text-xs leading-6 text-rose-950 sm:text-sm">{message}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}

      {action ? <div className="mt-5 flex flex-wrap gap-3">{action}</div> : null}
    </section>
  );
}
