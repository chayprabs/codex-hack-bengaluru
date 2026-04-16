import type { ReactNode } from "react";
import Link from "next/link";

import { cn } from "@/lib/utils";

type PageShellProps = {
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
  contentClassName?: string;
  maxWidth?: "4xl" | "5xl" | "7xl";
};

export const pageActionClassName =
  "inline-flex min-h-10 items-center rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 transition hover:border-slate-300 hover:bg-slate-50 focus:outline-none focus:ring-4 focus:ring-slate-200";

function widthClassName(maxWidth: NonNullable<PageShellProps["maxWidth"]>) {
  switch (maxWidth) {
    case "4xl":
      return "max-w-4xl";
    case "5xl":
      return "max-w-5xl";
    default:
      return "max-w-7xl";
  }
}

export function PageShell({
  children,
  actions,
  className,
  contentClassName,
  maxWidth = "7xl",
}: Readonly<PageShellProps>) {
  return (
    <main className={cn("relative min-h-screen overflow-hidden bg-transparent", className)}>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[24rem] bg-hero-grid bg-[size:40px_40px] opacity-[0.18]" />
      <div className="pointer-events-none absolute left-[-8rem] top-10 h-64 w-64 rounded-full bg-signal/12 blur-3xl" />
      <div className="pointer-events-none absolute right-[-6rem] top-8 h-60 w-60 rounded-full bg-slate-300/25 blur-3xl" />

      <section
        className={cn(
          "relative z-10 mx-auto flex min-h-screen w-full flex-col px-6 pb-16 pt-8 sm:px-10 lg:px-12",
          widthClassName(maxWidth),
          contentClassName,
        )}
      >
        <header className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <Link
            href="/"
            className="inline-flex w-fit items-center gap-3 rounded-full border border-slate-200/90 bg-white/90 px-4 py-2 text-sm font-medium text-slate-700 shadow-sm backdrop-blur"
          >
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-signal shadow-[0_0_0_6px_rgba(94,234,212,0.12)]" />
            TrustLayer
          </Link>

          {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
        </header>

        <div className="space-y-6">{children}</div>
      </section>
    </main>
  );
}
