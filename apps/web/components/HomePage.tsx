"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { apiClient, getApiErrorMessage } from "@/lib/api";
import { cn, isGithubRepoUrl } from "@/lib/utils";

const DEMO_REPO_URL = "https://github.com/vercel/next.js";

const stats = [
  { label: "Kickoff Time", value: "< 60 sec", detail: "From repo paste to visible audit room." },
  { label: "Review Tracks", value: "4 lanes", detail: "Planner, scanner, verifier, and report feed." },
  { label: "Signal Ready", value: "SSE", detail: "Prepared for live agent progress streaming." },
  { label: "Hackathon Mode", value: "Zero auth", detail: "Direct, fast setup for demos and iteration." },
];

export function HomePage() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [repoUrl, setRepoUrl] = useState("");
  const [pendingAction, setPendingAction] = useState<"audit" | "demo" | null>(null);
  const [feedback, setFeedback] = useState<{
    tone: "neutral" | "success" | "error";
    message: string;
  }>({
    tone: "neutral",
    message: "Paste a GitHub repo URL to launch an audit room backed by the current API scaffold.",
  });

  const trimmedUrl = repoUrl.trim();
  const isValidRepoUrl = isGithubRepoUrl(trimmedUrl);
  const isWorking = pendingAction !== null || isPending;

  async function handleAuditClick() {
    if (!trimmedUrl) {
      setFeedback({
        tone: "error",
        message: "Add a GitHub repository URL first so TrustLayer knows what to audit.",
      });
      return;
    }

    if (!isValidRepoUrl) {
      setFeedback({
        tone: "error",
        message: "That does not look like a GitHub repo URL yet. Try something like https://github.com/org/repo.",
      });
      return;
    }

    setPendingAction("audit");

    try {
      const audit = await apiClient.createAudit(trimmedUrl);
      setFeedback({
        tone: "success",
        message: `Audit created for ${trimmedUrl}. Opening audit room ${audit.id.slice(0, 8)} now.`,
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

  async function handleDemoClick() {
    setRepoUrl(DEMO_REPO_URL);
    setPendingAction("demo");

    try {
      const audit = await apiClient.createDemoAudit();
      setFeedback({
        tone: "success",
        message: "Demo audit created. Opening the seeded audit room now.",
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

  return (
    <main className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[32rem] bg-hero-grid bg-[size:42px_42px] opacity-40" />
      <div className="pointer-events-none absolute left-[-8rem] top-20 h-72 w-72 rounded-full bg-signal/25 blur-3xl" />
      <div className="pointer-events-none absolute right-[-5rem] top-14 h-64 w-64 rounded-full bg-ember/20 blur-3xl" />

      <section className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 pb-16 pt-10 sm:px-10 lg:px-12">
        <header className="mb-16 flex items-center justify-between">
          <div className="inline-flex items-center gap-3 rounded-full border border-slate-200/80 bg-white/80 px-4 py-2 text-sm font-medium text-slate-700 shadow-sm backdrop-blur">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-signal shadow-[0_0_0_6px_rgba(94,234,212,0.14)]" />
            TrustLayer
          </div>
          <div className="hidden items-center gap-3 md:flex">
            <Link
              href="/wall"
              className="rounded-full border border-slate-200/80 bg-white/70 px-4 py-2 text-sm text-slate-700 shadow-sm backdrop-blur transition hover:-translate-y-0.5 hover:border-slate-300 hover:bg-white"
            >
              Shame wall
            </Link>
            <div className="rounded-full border border-slate-200/80 bg-white/70 px-4 py-2 text-sm text-slate-500 shadow-sm backdrop-blur">
              Repo audits for fast-moving teams
            </div>
          </div>
        </header>

        <div className="grid flex-1 gap-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
          <div className="max-w-3xl">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-slate-200/80 bg-white/75 px-4 py-2 text-sm text-slate-700 shadow-sm backdrop-blur">
              <span className="font-semibold text-slate-900">Hackathon MVP</span>
              Live audit orchestration, clean findings, zero ceremony
            </div>

            <h1 className="max-w-2xl text-5xl font-semibold leading-tight tracking-[-0.04em] text-ink sm:text-6xl">
              Audit pull-request risk before blind trust becomes production debt.
            </h1>

            <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-600 sm:text-xl">
              TrustLayer gives teams a shared audit room for repo scans, agent progress, and findings that feel
              demo-ready on day one and extensible when the real pipeline lands.
            </p>

            <div className="mt-10 rounded-[2rem] border border-white/80 bg-white/80 p-5 shadow-halo backdrop-blur">
              <label className="mb-3 block text-sm font-semibold uppercase tracking-[0.22em] text-slate-500" htmlFor="repo-url">
                Repository URL
              </label>

              <div className="flex flex-col gap-4 md:flex-row">
                <input
                  id="repo-url"
                  type="url"
                  inputMode="url"
                  placeholder="https://github.com/your-org/your-repo"
                  value={repoUrl}
                  disabled={isWorking}
                  onChange={(event) => setRepoUrl(event.target.value)}
                  className="min-h-14 flex-1 rounded-2xl border border-slate-200 bg-slate-50 px-5 text-base text-slate-900 outline-none transition focus:border-slate-400 focus:bg-white focus:ring-4 focus:ring-signal/20"
                />

                <div className="flex gap-3 md:w-auto">
                  <button
                    type="button"
                    onClick={handleAuditClick}
                    disabled={isWorking}
                    className="min-h-14 flex-1 rounded-2xl bg-ink px-6 text-sm font-semibold text-white transition hover:-translate-y-0.5 hover:bg-slate-900 focus:outline-none focus:ring-4 focus:ring-slate-300 disabled:cursor-not-allowed disabled:opacity-60 md:flex-none"
                  >
                    {pendingAction === "audit" ? "Launching audit room..." : "Audit this repo"}
                  </button>
                  <button
                    type="button"
                    onClick={handleDemoClick}
                    disabled={isWorking}
                    className="min-h-14 flex-1 rounded-2xl border border-slate-200 bg-white px-6 text-sm font-semibold text-slate-800 transition hover:-translate-y-0.5 hover:border-slate-300 hover:bg-slate-50 focus:outline-none focus:ring-4 focus:ring-slate-200 disabled:cursor-not-allowed disabled:opacity-60 md:flex-none"
                  >
                    {pendingAction === "demo" ? "Opening demo..." : "Try demo app"}
                  </button>
                </div>
              </div>

              <div
                className={cn(
                  "mt-4 rounded-2xl border px-4 py-3 text-sm leading-6",
                  feedback.tone === "error" && "border-rose-200 bg-rose-50/90 text-rose-700",
                  feedback.tone === "success" && "border-emerald-200 bg-emerald-50/90 text-emerald-700",
                  feedback.tone === "neutral" && "border-slate-200/80 bg-slate-50/80 text-slate-600",
                )}
              >
                {feedback.message}
              </div>
            </div>
          </div>

          <aside className="relative">
            <div className="rounded-[2rem] border border-white/80 bg-white/78 p-6 shadow-halo backdrop-blur">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-500">Preview lane</p>
                  <h2 className="mt-2 text-2xl font-semibold text-slate-900">Audit room snapshot</h2>
                </div>
                <span className="rounded-full bg-signal/15 px-3 py-1 text-xs font-semibold text-slate-700">Frontend wired</span>
              </div>

              <div className="space-y-4">
                {[
                  ["Planner", "Maps audit scope and repo entry points from the live API snapshot."],
                  ["Scanner", "Shows current status now and can switch to SSE updates later."],
                  ["Verifier", "Surfaces findings and routes the team toward the audit room."],
                ].map(([title, description]) => (
                  <div key={title} className="rounded-2xl border border-slate-200 bg-slate-50/85 p-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-base font-semibold text-slate-900">{title}</h3>
                      <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-500">
                        queued
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
                  </div>
                ))}
              </div>

              <div className="mt-5 space-y-3 rounded-2xl bg-ink px-5 py-4 text-sm leading-6 text-slate-200">
                <p>The landing page now creates audits and routes into `/audit/[id]` using the typed frontend client.</p>
                <Link href="/wall" className="inline-flex font-semibold text-signal transition hover:text-white">
                  Open the shame wall
                </Link>
              </div>
            </div>
          </aside>
        </div>

        <section className="mt-12 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {stats.map((stat) => (
            <div
              key={stat.label}
              className="rounded-[1.75rem] border border-white/80 bg-white/72 p-5 shadow-sm backdrop-blur"
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
