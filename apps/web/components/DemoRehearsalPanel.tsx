"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { apiClient, getApiErrorMessage } from "@/lib/api";
import type { DemoProfileSummary, DemoSetupResponse } from "@/lib/types";

function formatJourney(values: number[]) {
  return values.map((value) => String(value)).join(" -> ");
}

function previewFindingSummary(profile: DemoProfileSummary) {
  const preview = profile.preview_findings.slice(0, 3).map((finding) => finding.title);
  const hiddenCount = profile.preview_findings.length - preview.length;
  if (!preview.length) {
    return "No preview findings recorded yet.";
  }

  return hiddenCount > 0 ? `${preview.join("; ")} +${hiddenCount} more` : preview.join("; ");
}

function LoadingCard() {
  return (
    <div className="rounded-[1.5rem] border border-slate-200 bg-white/80 p-5">
      <div className="h-4 w-36 animate-pulse rounded-full bg-slate-200" />
      <div className="mt-4 h-8 w-60 animate-pulse rounded-full bg-slate-100" />
      <div className="mt-4 h-20 animate-pulse rounded-[1.25rem] bg-slate-100" />
    </div>
  );
}

function BackupProfileCard({
  profile,
  pendingKey,
  onOpen,
}: Readonly<{
  profile: DemoProfileSummary;
  pendingKey: string | null;
  onOpen: (profile: DemoProfileSummary) => Promise<void>;
}>) {
  const isLaunching = pendingKey === profile.key;

  return (
    <article className="rounded-[1.35rem] border border-slate-200 bg-white/92 p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Backup seeded story</p>
          <h4 className="mt-2 text-lg font-semibold tracking-[-0.02em] text-slate-950">{profile.label}</h4>
        </div>
        <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-600">
          {profile.final_score}/100
        </span>
      </div>

      <p className="mt-3 text-sm leading-6 text-slate-600">{profile.summary}</p>
      <p className="mt-3 text-sm leading-6 text-slate-700">{profile.recommended_use}</p>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Score journey</p>
          <p className="mt-2 font-mono text-sm font-semibold text-slate-950">{formatJourney(profile.score_journey)}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Coverage journey</p>
          <p className="mt-2 font-mono text-sm font-semibold text-slate-950">{formatJourney(profile.coverage_journey)}</p>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Preview findings</p>
        <p className="mt-2 text-sm leading-6 text-slate-700">{previewFindingSummary(profile)}</p>
      </div>

      <button
        type="button"
        onClick={() => void onOpen(profile)}
        disabled={Boolean(pendingKey)}
        className="mt-4 inline-flex min-h-11 items-center justify-center rounded-2xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-800 transition hover:-translate-y-0.5 hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isLaunching ? "Opening backup room..." : "Open backup room"}
      </button>
    </article>
  );
}

export function DemoRehearsalPanel() {
  const router = useRouter();
  const [setup, setSetup] = useState<DemoSetupResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  useEffect(() => {
    let active = true;

    void apiClient
      .getDemoSetup()
      .then((response) => {
        if (!active) {
          return;
        }

        setSetup(response);
        setLoadError(null);
      })
      .catch((error: unknown) => {
        if (!active) {
          return;
        }

        setLoadError(getApiErrorMessage(error));
      });

    return () => {
      active = false;
    };
  }, []);

  const profiles = setup?.profiles ?? [];
  const flagship = profiles.find((profile) => profile.is_flagship) ?? profiles[0] ?? null;
  const backups = profiles.filter((profile) => !profile.is_flagship);

  async function openProfile(profile: DemoProfileSummary) {
    setLaunchError(null);
    setPendingKey(profile.key);

    try {
      const audit = await apiClient.createDemoAudit(profile.key);
      startTransition(() => {
        router.push(`/audit/${audit.id}`);
      });
    } catch (error) {
      setPendingKey(null);
      setLaunchError(getApiErrorMessage(error));
    }
  }

  return (
    <section className="mt-5 rounded-[1.5rem] border border-slate-200 bg-[linear-gradient(135deg,rgba(248,250,252,0.96),rgba(255,255,255,0.95))] p-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Demo rehearsal kit</p>
          <h3 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">Stable path, visible backups</h3>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Keep one flagship room on rails: a pinned repo path, coherent seeded findings, predictable TrustScore motion,
            and backup stories ready if a live repo stays boring.
          </p>
        </div>

        {setup ? (
          <span className="rounded-full border border-slate-200 bg-white px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-600">
            {profiles.length} seeded stories
          </span>
        ) : null}
      </div>

      {launchError ? (
        <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50/90 px-4 py-3 text-sm leading-6 text-rose-700">
          {launchError}
        </div>
      ) : null}

      {loadError ? (
        <div className="mt-5 rounded-[1.35rem] border border-amber-200 bg-amber-50/90 px-4 py-4 text-sm leading-6 text-amber-900">
          <p className="font-semibold text-amber-950">Demo setup unavailable</p>
          <p className="mt-2">{loadError}</p>
        </div>
      ) : !setup || !flagship ? (
        <div className="mt-5 grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
          <LoadingCard />
          <LoadingCard />
        </div>
      ) : (
        <>
          <article className="mt-5 rounded-[1.5rem] border border-slate-200 bg-slate-950 px-5 py-5 text-white">
            <div className="grid gap-5 xl:grid-cols-[1.08fr_0.92fr]">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Flagship room</p>
                <h4 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">{flagship.label}</h4>
                <p className="mt-3 text-sm leading-6 text-slate-300">{flagship.summary}</p>

                <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Stable repo path</p>
                  <p className="mt-2 font-mono text-sm font-semibold text-white">{setup.primary_demo_repo_url}</p>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {flagship.focus_areas.map((area) => (
                    <span
                      key={area}
                      className="rounded-full border border-white/12 bg-white/6 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-100"
                    >
                      {area}
                    </span>
                  ))}
                </div>

                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={() => void openProfile(flagship)}
                    disabled={Boolean(pendingKey)}
                    className="inline-flex min-h-12 items-center justify-center rounded-2xl bg-white px-5 text-sm font-semibold text-slate-900 transition hover:-translate-y-0.5 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {pendingKey === flagship.key ? "Opening flagship room..." : "Open flagship room"}
                  </button>
                  <span className="font-mono text-xs uppercase tracking-[0.16em] text-slate-400">
                    {flagship.finding_count} seeded findings
                  </span>
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Score journey</p>
                  <p className="mt-2 font-mono text-sm font-semibold text-white">{formatJourney(flagship.score_journey)}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Coverage journey</p>
                  <p className="mt-2 font-mono text-sm font-semibold text-white">{formatJourney(flagship.coverage_journey)}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Final report close</p>
                  <p className="mt-2 text-sm leading-6 text-slate-200">
                    {flagship.completion_message ??
                      "The seeded room closes with a clear remediation handoff instead of a vague status message."}
                  </p>
                </div>
              </div>
            </div>
          </article>

          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <article className="rounded-[1.35rem] border border-slate-200 bg-white/90 px-4 py-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">If stream updates fail</p>
              <p className="mt-3 text-sm leading-6 text-slate-700">{setup.stream_backup_summary}</p>
            </article>
            <article className="rounded-[1.35rem] border border-slate-200 bg-white/90 px-4 py-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">If a live repo is boring</p>
              <p className="mt-3 text-sm leading-6 text-slate-700">{setup.boring_repo_backup_summary}</p>
            </article>
          </div>

          {backups.length > 0 ? (
            <div className="mt-4 grid gap-4 xl:grid-cols-2">
              {backups.map((profile) => (
                <BackupProfileCard key={profile.key} profile={profile} pendingKey={pendingKey} onOpen={openProfile} />
              ))}
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
