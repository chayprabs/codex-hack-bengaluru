import type { ReactNode } from "react";
import Link from "next/link";

import { cn } from "@/lib/utils";

type DashboardPageProps = {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
  children: ReactNode;
};

type Tone = "neutral" | "info" | "success" | "warning" | "danger" | "critical";
type ButtonTone = "primary" | "secondary";

const toneClasses: Record<Tone, string> = {
  neutral: "border-slate-200 bg-slate-100 text-slate-700",
  info: "border-cyan-200 bg-cyan-50 text-cyan-700",
  success: "border-emerald-200 bg-emerald-50 text-emerald-700",
  warning: "border-amber-200 bg-amber-50 text-amber-700",
  danger: "border-rose-200 bg-rose-50 text-rose-700",
  critical: "border-rose-300 bg-rose-100 text-rose-800",
};

export function buttonClassName(tone: ButtonTone = "secondary") {
  return cn(
    "inline-flex min-h-11 items-center justify-center rounded-2xl px-4 py-2 text-sm font-semibold transition",
    tone === "primary"
      ? "bg-ink text-white hover:-translate-y-0.5 hover:bg-slate-900 focus:outline-none focus:ring-4 focus:ring-slate-300"
      : "border border-slate-200 bg-white/80 text-slate-800 hover:-translate-y-0.5 hover:border-slate-300 hover:bg-slate-50 focus:outline-none focus:ring-4 focus:ring-slate-200",
  );
}

export function DashboardPage({
  eyebrow,
  title,
  description,
  actions,
  children,
}: DashboardPageProps) {
  return (
    <main className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[28rem] bg-hero-grid bg-[size:42px_42px] opacity-35" />
      <div className="pointer-events-none absolute left-[-6rem] top-20 h-64 w-64 rounded-full bg-signal/20 blur-3xl" />
      <div className="pointer-events-none absolute right-[-4rem] top-10 h-60 w-60 rounded-full bg-ember/18 blur-3xl" />

      <section className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 pb-16 pt-10 sm:px-10 lg:px-12">
        <header className="mb-10 flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <Link
                href="/"
                className="inline-flex items-center gap-3 rounded-full border border-slate-200/80 bg-white/80 px-4 py-2 text-sm font-medium text-slate-700 shadow-sm backdrop-blur"
              >
                <span className="inline-block h-2.5 w-2.5 rounded-full bg-signal shadow-[0_0_0_6px_rgba(94,234,212,0.14)]" />
                TrustLayer
              </Link>
              <Link href="/wall" className={buttonClassName()}>
                Shame wall
              </Link>
              <Link href="/" className={buttonClassName()}>
                New audit
              </Link>
            </div>

            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-500">{eyebrow}</p>
              <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-[-0.04em] text-ink sm:text-5xl">
                {title}
              </h1>
              <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600 sm:text-lg">{description}</p>
            </div>
          </div>

          {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
        </header>

        <div className="space-y-8">{children}</div>
      </section>
    </main>
  );
}

export function Card({
  children,
  className,
}: Readonly<{ children: ReactNode; className?: string }>) {
  return (
    <div className={cn("rounded-[2rem] border border-white/80 bg-white/80 p-6 shadow-halo backdrop-blur", className)}>
      {children}
    </div>
  );
}

export function MetricGrid({ children }: Readonly<{ children: ReactNode }>) {
  return <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{children}</div>;
}

export function MetricCard({
  label,
  value,
  detail,
}: Readonly<{ label: string; value: string; detail: string }>) {
  return (
    <div className="rounded-[1.75rem] border border-white/80 bg-white/72 p-5 shadow-sm backdrop-blur">
      <p className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-500">{label}</p>
      <p className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-slate-950">{value}</p>
      <p className="mt-3 text-sm leading-6 text-slate-600">{detail}</p>
    </div>
  );
}

export function SectionHeader({
  title,
  description,
  actions,
}: Readonly<{ title: string; description: string; actions?: ReactNode }>) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h2 className="text-2xl font-semibold tracking-[-0.03em] text-slate-950">{title}</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">{description}</p>
      </div>
      {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
    </div>
  );
}

export function StatusPill({
  tone = "neutral",
  children,
}: Readonly<{ tone?: Tone; children: ReactNode }>) {
  return (
    <span className={cn("inline-flex rounded-full border px-3 py-1 text-xs font-semibold", toneClasses[tone])}>
      {children}
    </span>
  );
}

export function StatePanel({
  title,
  description,
  tone = "neutral",
  action,
}: Readonly<{
  title: string;
  description: string;
  tone?: Tone;
  action?: ReactNode;
}>) {
  return (
    <Card className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <StatusPill tone={tone}>{title}</StatusPill>
      </div>
      <p className="max-w-2xl text-base leading-7 text-slate-600">{description}</p>
      {action ? <div className="flex flex-wrap gap-3">{action}</div> : null}
    </Card>
  );
}

export function LoadingState({
  title,
  description,
}: Readonly<{ title: string; description: string }>) {
  return (
    <Card className="space-y-5">
      <div>
        <p className="text-sm font-semibold uppercase tracking-[0.22em] text-slate-500">Loading</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">{title}</h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">{description}</p>
      </div>

      <div className="space-y-3">
        <div className="h-4 w-40 animate-pulse rounded-full bg-slate-200" />
        <div className="h-20 animate-pulse rounded-[1.5rem] bg-slate-100" />
        <div className="h-20 animate-pulse rounded-[1.5rem] bg-slate-100" />
      </div>
    </Card>
  );
}
