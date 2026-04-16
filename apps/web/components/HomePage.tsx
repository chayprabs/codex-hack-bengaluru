"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useState, useTransition } from "react";

import { DemoRehearsalPanel } from "@/components/DemoRehearsalPanel";
import { apiClient, getApiErrorMessage } from "@/lib/api";
import type { AuditMode } from "@/lib/types";
import { cn, isGithubRepoUrl } from "@/lib/utils";

const stats = [
  { label: "Demo Launch", value: "< 10 sec", detail: "Open the demo fast and start showing findings right away." },
  { label: "Demo Paths", value: "5 seeded paths", detail: "One primary path plus four backups keeps the demo reliable." },
  { label: "Score Steps", value: "5 moves", detail: "Planner, scanner, and verifier move the score in a clear sequence." },
  { label: "Scope Guardrails", value: "No false confidence", detail: "Low coverage stays clearly marked instead of reading like a pass." },
];

const demoHighlights = [
  "Secrets",
  "Webhook trust",
  "Authz / IDOR",
  "Release safety",
  "Unsafe runtime",
];

const auditModes: Array<{
  value: AuditMode;
  label: string;
  summary: string;
  detail: string;
}> = [
  {
    value: "fast",
    label: "Fast",
    summary: "Repo map, core checks, top-risk files",
    detail: "Best for a fast first pass.",
  },
  {
    value: "deep",
    label: "Deep",
    summary: "Broader routes, more files, stronger review",
    detail: "Slower, but better for a full demo.",
  },
];

export function HomePage() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [repoUrl, setRepoUrl] = useState("");
  const [auditMode, setAuditMode] = useState<AuditMode>("fast");
  const [pendingAction, setPendingAction] = useState<"audit" | "demo" | null>(null);
  const [feedback, setFeedback] = useState<{
    tone: "neutral" | "success" | "error";
    message: string;
  }>({
    tone: "neutral",
    message: "Run the demo or paste a public GitHub repo to start a live audit.",
  });

  const trimmedUrl = repoUrl.trim();
  const isValidRepoUrl = isGithubRepoUrl(trimmedUrl);
  const isWorking = pendingAction !== null || isPending;
  const selectedMode = auditModes.find((mode) => mode.value === auditMode) ?? auditModes[0];

  async function handleAuditClick() {
    if (!trimmedUrl) {
      setFeedback({
        tone: "error",
        message: "Enter a GitHub repo URL first.",
      });
      return;
    }

    if (!isValidRepoUrl) {
      setFeedback({
        tone: "error",
        message: "Use a GitHub repo root like https://github.com/org/repo, or open the demo instead.",
      });
      return;
    }

    setPendingAction("audit");
    setFeedback({
      tone: "neutral",
      message: `Starting a ${selectedMode.label.toLowerCase()} audit for ${trimmedUrl}. Opening the room.`,
    });

    try {
      const audit = await apiClient.createAudit(trimmedUrl, auditMode);
      setFeedback({
        tone: "success",
        message: `${selectedMode.label} audit started. Opening room ${audit.id.slice(0, 8)}.`,
      });

      startTransition(() => {
        router.push(`/audit/${audit.id}`);
      });
    } catch (error) {
      setFeedback({
        tone: "error",
        message: `${getApiErrorMessage(error)} Need a reliable walkthrough? Open the demo.`,
      });
      setPendingAction(null);
    }
  }

  async function handleDemoClick() {
    setPendingAction("demo");
    setFeedback({
      tone: "neutral",
      message: "Opening the seeded demo audit.",
    });

    try {
      const audit = await apiClient.createDemoAudit();
      setFeedback({
        tone: "success",
        message: "Demo room ready. Opening now.",
      });

      startTransition(() => {
        router.push(`/audit/${audit.id}`);
      });
    } catch (error) {
      setFeedback({
        tone: "error",
        message: getApiErrorMessage(error),
      });
      setPendingAction(null);
    }
  }

  async function handleAuditSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await handleAuditClick();
  }

  return (
    <main className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[32rem] bg-hero-grid bg-[size:42px_42px] opacity-30" />
      <div className="pointer-events-none absolute left-[-8rem] top-20 h-72 w-72 rounded-full bg-signal/16 blur-3xl" />
      <div className="pointer-events-none absolute right-[-5rem] top-14 h-64 w-64 rounded-full bg-slate-300/25 blur-3xl" />

      <section className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 pb-16 pt-10 sm:px-10 lg:px-12">
        <header className="mb-16 flex items-center justify-between">
          <div className="inline-flex items-center gap-3 rounded-full border border-slate-200/90 bg-white/90 px-4 py-2 text-sm font-medium text-slate-700 shadow-sm backdrop-blur">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-signal shadow-[0_0_0_6px_rgba(94,234,212,0.14)]" />
            TrustLayer
          </div>
          <div className="hidden items-center gap-3 md:flex">
            <Link
              href="/wall"
              className="rounded-full border border-slate-200/80 bg-white/70 px-4 py-2 text-sm text-slate-700 shadow-sm backdrop-blur transition hover:-translate-y-0.5 hover:border-slate-300 hover:bg-white"
            >
              Audit wall
            </Link>
            <div className="rounded-full border border-slate-200/80 bg-white/70 px-4 py-2 text-sm text-slate-500 shadow-sm backdrop-blur">
              Live repo audits with clear evidence
            </div>
          </div>
        </header>

        <div className="grid flex-1 gap-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
          <div className="max-w-3xl">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-slate-200/90 bg-white/90 px-4 py-2 text-sm text-slate-700 shadow-sm backdrop-blur">
              <span className="font-semibold text-slate-900">Live audit room</span>
              Findings, proof, and score changes in one view
            </div>

            <h1 className="max-w-2xl text-5xl font-semibold leading-tight tracking-[-0.04em] text-ink sm:text-6xl">
              See repo risk with proof in under a minute.
            </h1>

            <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-600 sm:text-xl">
              TrustLayer scans a repo live, shows what it found, and ends with a report a team can act on.
            </p>

            <div className="mt-10 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={handleDemoClick}
                disabled={isWorking}
                className="min-h-14 rounded-2xl bg-ink px-6 text-sm font-semibold text-white transition hover:-translate-y-0.5 hover:bg-slate-900 focus:outline-none focus:ring-4 focus:ring-slate-300 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {pendingAction === "demo" ? "Opening demo..." : "Run demo"}
              </button>
              <a
                href="#live-audit-form"
                className="inline-flex min-h-14 items-center rounded-2xl border border-slate-200 bg-white px-6 text-sm font-semibold text-slate-800 transition hover:-translate-y-0.5 hover:border-slate-300 hover:bg-slate-50 focus:outline-none focus:ring-4 focus:ring-slate-200"
              >
                Scan a repo
              </a>
            </div>

            <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-600">
              Seeded demo with clear findings across secrets, webhooks, auth, and runtime risk. Final result:
              {" "}
              <span className="font-mono text-slate-900">TrustScore 100 -&gt; 57</span>
              {" "}
              and
              {" "}
              <span className="font-mono text-slate-900">Coverage 12 -&gt; 92</span>.
            </p>

            <div className="mt-10 rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm backdrop-blur sm:p-6">
              <div className="rounded-[1.5rem] border border-slate-200 bg-[linear-gradient(135deg,rgba(15,23,42,0.98),rgba(30,41,59,0.96),rgba(8,16,24,0.98))] p-5 text-white">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="max-w-2xl">
                    <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-300">Best demo path</p>
                    <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">Run the seeded walkthrough</h2>
                    <p className="mt-3 text-sm leading-6 text-slate-200">
                      Fixed data, clear score changes, and a clean final report. Best choice for a live demo.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleDemoClick}
                    disabled={isWorking}
                    className="inline-flex min-h-12 items-center justify-center rounded-2xl bg-white px-5 text-sm font-semibold text-slate-900 transition hover:-translate-y-0.5 hover:bg-slate-100 focus:outline-none focus:ring-4 focus:ring-white/20 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {pendingAction === "demo" ? "Opening demo..." : "Open demo"}
                  </button>
                </div>

                <div className="mt-5 flex flex-wrap gap-2">
                  {demoHighlights.map((item) => (
                    <span
                      key={item}
                      className="rounded-full border border-white/15 bg-white/8 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-100"
                    >
                      {item}
                    </span>
                  ))}
                </div>

                <div className="mt-5 grid gap-3 md:grid-cols-3">
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-300">Seeded repo</p>
                    <p className="mt-2 font-mono text-base font-semibold text-white">Acme subscriptions platform</p>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-300">Score</p>
                    <p className="mt-2 font-mono text-base font-semibold text-white">100 -&gt; 57</p>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-300">Coverage</p>
                    <p className="mt-2 font-mono text-base font-semibold text-white">12 -&gt; 92</p>
                  </div>
                </div>
              </div>

              <DemoRehearsalPanel />

              <form id="live-audit-form" onSubmit={handleAuditSubmit} className="mt-5 space-y-4">
                <div>
                  <label className="mb-3 block text-sm font-semibold uppercase tracking-[0.22em] text-slate-500" htmlFor="repo-url">
                    Scan a Live Repo
                  </label>
                  <p className="mb-4 text-sm leading-6 text-slate-600">
                    Use a real public repo when you want an unscripted run. Results depend on the repo and current backend support.
                  </p>
                </div>

                <div className="flex flex-col gap-4 md:flex-row">
                  <input
                    id="repo-url"
                    name="repo-url"
                    type="url"
                    inputMode="url"
                    autoComplete="off"
                    placeholder="https://github.com/your-org/your-repo"
                    value={repoUrl}
                    disabled={isWorking}
                    onChange={(event) => setRepoUrl(event.target.value)}
                    aria-invalid={feedback.tone === "error" ? true : undefined}
                    aria-describedby="repo-url-feedback"
                    className="min-h-14 flex-1 rounded-2xl border border-slate-200 bg-slate-50 px-5 text-base text-slate-900 outline-none transition focus:border-slate-400 focus:bg-white focus:ring-4 focus:ring-signal/20"
                  />

                  <div className="flex gap-3 md:w-auto">
                    <button
                      type="submit"
                      disabled={isWorking}
                      className="min-h-14 flex-1 rounded-2xl border border-slate-200 bg-white px-6 text-sm font-semibold text-slate-800 transition hover:-translate-y-0.5 hover:border-slate-300 hover:bg-slate-50 focus:outline-none focus:ring-4 focus:ring-slate-200 disabled:cursor-not-allowed disabled:opacity-60 md:flex-none"
                    >
                      {pendingAction === "audit" ? `Starting ${selectedMode.label} audit...` : `Start ${selectedMode.label} audit`}
                    </button>
                  </div>
                </div>

                <div className="rounded-[1.35rem] border border-slate-200 bg-slate-50/80 p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Audit mode</p>
                      <p className="mt-2 text-sm leading-6 text-slate-600">
                        Fast gives you a solid first read. Deep checks more files and paths before closing the report.
                      </p>
                    </div>
                    <span className="rounded-full border border-slate-200 bg-white px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-600">
                      {selectedMode.label} selected
                    </span>
                  </div>

                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    {auditModes.map((mode) => {
                      const isSelected = auditMode === mode.value;
                      return (
                        <button
                          key={mode.value}
                          type="button"
                          disabled={isWorking}
                          onClick={() => setAuditMode(mode.value)}
                          aria-pressed={isSelected}
                          className={cn(
                            "rounded-[1.25rem] border px-4 py-4 text-left transition focus:outline-none focus:ring-4 focus:ring-signal/20 disabled:cursor-not-allowed disabled:opacity-60",
                            isSelected
                              ? "border-slate-900 bg-white shadow-sm"
                              : "border-slate-200 bg-white/80 hover:-translate-y-0.5 hover:border-slate-300 hover:bg-white",
                          )}
                        >
                          <div className="flex items-center justify-between gap-3">
                            <span className="font-mono text-sm font-semibold uppercase tracking-[0.12em] text-slate-950">{mode.label}</span>
                            <span
                              className={cn(
                                "rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em]",
                                isSelected
                                  ? "border-cyan-200 bg-cyan-50 text-cyan-700"
                                  : "border-slate-200 bg-slate-50 text-slate-500",
                              )}
                            >
                              {isSelected ? "Selected" : "Available"}
                            </span>
                          </div>
                          <p className="mt-3 text-sm font-semibold tracking-[-0.02em] text-slate-950">{mode.summary}</p>
                          <p className="mt-2 text-sm leading-6 text-slate-600">{mode.detail}</p>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div
                  id="repo-url-feedback"
                  role={feedback.tone === "error" ? "alert" : "status"}
                  aria-live="polite"
                  className={cn(
                    "rounded-2xl border px-4 py-3 text-sm leading-6",
                    feedback.tone === "error" && "border-rose-200 bg-rose-50/90 text-rose-700",
                    feedback.tone === "success" && "border-emerald-200 bg-emerald-50/90 text-emerald-700",
                    feedback.tone === "neutral" && "border-slate-200/80 bg-slate-50/80 text-slate-600",
                  )}
                >
                  {feedback.message}
                </div>
              </form>
            </div>
          </div>

          <aside className="relative">
            <div className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-6 shadow-sm backdrop-blur">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-500">Preview</p>
                  <h2 className="mt-2 text-2xl font-semibold text-slate-900">Audit room preview</h2>
                </div>
                <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                  Demo-ready
                </span>
              </div>

              <div className="space-y-4">
                {[
                  ["Planner", "completed", "Mapped webhook, tenant, and release paths. Scan scope is set."],
                  ["Scanner", "running", "Collecting evidence for secrets, webhooks, IDOR, and runtime risk."],
                  ["Verifier", "queued", "Will review the strongest findings and settle the score."],
                ].map(([title, status, description]) => (
                  <div key={title} className="rounded-2xl border border-slate-200 bg-slate-50/85 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="font-mono text-base font-semibold text-slate-900">{title}</h3>
                      <span
                        className={cn(
                          "rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.14em]",
                          status === "running" && "border-cyan-200 bg-cyan-50 text-cyan-700",
                          status === "completed" && "border-emerald-200 bg-emerald-50 text-emerald-700",
                          status === "queued" && "border-slate-200 bg-white text-slate-500",
                        )}
                      >
                        {status}
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
                  </div>
                ))}
              </div>

              <div className="mt-5 rounded-2xl border border-slate-200 bg-slate-950 px-5 py-4 text-sm leading-6 text-slate-200">
                <p className="font-semibold text-white">Demo snapshot</p>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Score arc</p>
                    <p className="mt-2 font-mono text-base font-semibold text-white">TrustScore 100 -&gt; 88 -&gt; 74 -&gt; 57</p>
                    <p className="mt-2 text-slate-300">Coverage rises from 12 to 92 as findings are anchored and reviewed.</p>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Flagged paths</p>
                    <p className="mt-2 text-white">Secrets, unsigned billing webhook, workspace export IDOR, release bypass, unsafe markdown runtime.</p>
                    <p className="mt-2 text-slate-300">The demo stays predictable. Live repo scans are there when you want the unscripted path.</p>
                  </div>
                </div>
                <p className="mt-3">
                  The landing page opens a <span className="font-mono">{selectedMode.label}</span> audit room and drops straight into the live workspace.
                </p>
                <Link href="/wall" className="inline-flex font-semibold text-signal transition hover:text-white">
                  View audit wall
                </Link>
              </div>
            </div>
          </aside>
        </div>

        <section className="mt-12 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {stats.map((stat) => (
            <div
              key={stat.label}
              className="rounded-[1.5rem] border border-slate-200 bg-white/90 p-5 shadow-sm backdrop-blur"
            >
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-500">{stat.label}</p>
              <p className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-slate-950">{stat.value}</p>
              <p className="mt-3 text-sm leading-6 text-slate-600">{stat.detail}</p>
            </div>
          ))}
        </section>
      </section>
    </main>
  );
}
