import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type EmptyStateProps = {
  title: string;
  description: string;
  eyebrow?: string;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
};

export function EmptyState({
  title,
  description,
  eyebrow = "No data",
  action,
  className,
  compact = false,
}: Readonly<EmptyStateProps>) {
  return (
    <section
      className={cn(
        "rounded-[1.5rem] border border-dashed border-slate-300 bg-slate-50/90 text-slate-700",
        compact ? "p-5" : "p-6 sm:p-8",
        className,
      )}
      role="status"
      aria-live="polite"
    >
      <div className="max-w-2xl">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">{eyebrow}</p>
        <h2 className="mt-3 text-xl font-semibold tracking-[-0.03em] text-slate-950 sm:text-2xl">{title}</h2>
        <p className="mt-3 text-sm leading-6 text-slate-600 sm:text-base">{description}</p>
      </div>
      {action ? <div className="mt-5 flex flex-wrap gap-3">{action}</div> : null}
    </section>
  );
}
