import type { Audit } from "@/lib/types";
import { formatScore } from "@/lib/format";
import { formatAuditLabel, toneFromCoverageBand } from "@/lib/coveragePresentation";
import { cn, titleCase } from "@/lib/utils";
import { StatusBadge, type StatusBadgeTone } from "@/components/StatusBadge";

type CoveragePanelProps = {
  audit?: Audit | null;
  className?: string;
};

type CoverageSurfaceDefinition = {
  key: "API routes" | "Auth / Session" | "Database / Schema" | "Webhooks";
  label: string;
  detail: string;
};

type CoverageSurfaceState = {
  label: string;
  tone: StatusBadgeTone;
  detail: string;
};

const SURFACE_DEFINITIONS: CoverageSurfaceDefinition[] = [
  { key: "API routes", label: "routes", detail: "HTTP entrypoints" },
  { key: "Auth / Session", label: "auth/session", detail: "Identity edges" },
  { key: "Database / Schema", label: "database", detail: "Data model surface" },
  { key: "Webhooks", label: "webhooks", detail: "Inbound callbacks" },
];

function resolveList(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter(Boolean);
}

function resolveNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function resolveText(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function surfaceState(
  key: CoverageSurfaceDefinition["key"],
  {
    supportedAreas,
    partialAreas,
    unsupportedAreas,
    manualReviewAreas,
    hasSignals,
  }: {
    supportedAreas: string[];
    partialAreas: string[];
    unsupportedAreas: string[];
    manualReviewAreas: string[];
    hasSignals: boolean;
  },
): CoverageSurfaceState {
  if (manualReviewAreas.includes(key)) {
    return {
      label: "Needs manual review",
      tone: "info",
      detail: "Mapped, but this surface still needs a human pass before the result is treated as settled.",
    };
  }

  if (supportedAreas.includes(key)) {
    return {
      label: "Supported",
      tone: "success",
      detail: "Mapped and exercised by specialist checks.",
    };
  }

  if (partialAreas.includes(key)) {
    return {
      label: "Partially supported",
      tone: "warning",
      detail: "Mapped, but only part of the surface was checked.",
    };
  }

  if (unsupportedAreas.includes(key)) {
    return {
      label: "Unsupported",
      tone: "neutral",
      detail: "Mapped, but this surface sits outside the current automated support path for this run.",
    };
  }

  if (hasSignals) {
    return {
      label: "Not found",
      tone: "neutral",
      detail: "The repo map did not expose this surface.",
    };
  }

  return {
    label: "Waiting",
    tone: "neutral",
    detail: "Surface mapping starts after repository intake.",
  };
}

function TagCloud({
  title,
  items,
  tone,
  emptyLabel,
}: Readonly<{
  title: string;
  items: string[];
  tone: StatusBadgeTone;
  emptyLabel: string;
}>) {
  return (
    <div className="rounded-[1.25rem] border border-slate-200 bg-white/82 px-4 py-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{title}</p>
        <StatusBadge tone={tone} mono>
          {items.length}
        </StatusBadge>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {items.length ? (
          items.map((item) => (
            <StatusBadge key={`${title}-${item}`} tone={tone} size="sm">
              {item}
            </StatusBadge>
          ))
        ) : (
          <span className="rounded-full border border-dashed border-slate-300 px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            {emptyLabel}
          </span>
        )}
      </div>
    </div>
  );
}

function CheckSummary({
  title,
  description,
  items,
  tone,
  emptyLabel,
}: Readonly<{
  title: string;
  description: string;
  items: string[];
  tone: StatusBadgeTone;
  emptyLabel: string;
}>) {
  return (
    <article
      className={cn(
        "rounded-[1.25rem] border px-4 py-4",
        tone === "danger"
          ? "border-rose-200 bg-rose-50/70"
          : tone === "warning"
            ? "border-amber-200 bg-amber-50/75"
            : "border-slate-200 bg-slate-50/85",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{title}</p>
        <StatusBadge tone={tone} mono>
          {items.length}
        </StatusBadge>
      </div>

      <p className="mt-3 text-sm leading-6 text-slate-700">{description}</p>

      <div className="mt-4 flex flex-wrap gap-2">
        {items.length ? (
          items.map((item) => (
            <span
              key={`${title}-${item}`}
              className="rounded-full border border-white/80 bg-white/85 px-3 py-1 font-mono text-[11px] font-semibold tracking-[0.04em] text-slate-700"
            >
              {formatAuditLabel(item)}
            </span>
          ))
        ) : (
          <span className="rounded-full border border-dashed border-slate-300 px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            {emptyLabel}
          </span>
        )}
      </div>
    </article>
  );
}

export function CoveragePanel({ audit, className }: Readonly<CoveragePanelProps>) {
  const supportedAreas = resolveList(audit?.supported_areas);
  const partialAreas = resolveList(audit?.partially_supported_areas);
  const unsupportedAreas = resolveList(audit?.unsupported_areas);
  const manualReviewAreas = resolveList(audit?.needs_manual_review_areas);
  const unsupportedTechnologies = resolveList(audit?.unsupported_technologies);
  const frameworksDetected = resolveList(audit?.frameworks_detected);
  const checksRun = resolveList(audit?.checks_run);
  const checksSkipped = resolveList(audit?.checks_skipped);
  const scannedFilesCount = resolveNumber(audit?.scanned_files_count);
  const skippedFilesCount = resolveNumber(audit?.skipped_files_count);
  const coveragePercent = resolveNumber(audit?.coverage_percent) ?? resolveNumber(audit?.coverage);
  const coverageBand = audit?.coverage_band;
  const coverageSummary = resolveText(audit?.coverage_summary);
  const confidenceLimited = Boolean(audit?.confidence_limited);

  const hasSignals =
    scannedFilesCount !== null ||
    skippedFilesCount !== null ||
    frameworksDetected.length > 0 ||
    supportedAreas.length > 0 ||
    partialAreas.length > 0 ||
    unsupportedAreas.length > 0 ||
    manualReviewAreas.length > 0 ||
    unsupportedTechnologies.length > 0 ||
    checksRun.length > 0 ||
    checksSkipped.length > 0;

  const frameworkSummary = frameworksDetected.length
    ? frameworksDetected.join(", ")
    : hasSignals
      ? "No framework signal was mapped for this repo."
      : "Framework detection will appear after repo mapping completes.";
  const unsupportedTechnologySummary = unsupportedTechnologies.length
    ? unsupportedTechnologies.join(", ")
    : hasSignals
      ? "No unsupported tech signal was reported in this run."
      : "Unsupported-tech signals appear after repo mapping completes.";

  const checkedDescription = checksRun.length
    ? "Checks that actually ran in this audit."
    : hasSignals
      ? "No checks have completed yet."
      : "Checks will appear here once the audit starts.";

  const skippedDescription = checksSkipped.length
    ? "Checks skipped or out of scope in this run."
    : hasSignals
      ? "No skipped checks were reported."
      : "Skipped checks will appear here if the audit has to defer scope.";

  return (
    <section
      className={cn(
        "rounded-[1.75rem] border border-slate-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.97),rgba(248,250,252,0.94))] p-5 shadow-sm sm:p-6",
        className,
      )}
      aria-label="Coverage panel"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Coverage map</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-slate-950">What was checked</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {coverageSummary || "What the audit reached, what it skipped, and where human review is still needed."}
          </p>
        </div>

        <div className="rounded-[1.25rem] border border-slate-200 bg-white/88 px-4 py-4 text-right">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Coverage</p>
          <p className="mt-3 font-mono text-4xl font-semibold tracking-[-0.05em] text-slate-950">
            {coveragePercent === null ? "N/A" : `${formatScore(coveragePercent)}%`}
          </p>
          <div className="mt-3 flex justify-end">
            <StatusBadge tone={toneFromCoverageBand(coverageBand)} mono>
              {coverageBand ? titleCase(coverageBand) : "Pending"}
            </StatusBadge>
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <div className="rounded-[1.25rem] border border-slate-200 bg-white/82 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Files scanned</p>
          <p className="mt-3 font-mono text-2xl font-semibold tracking-[-0.03em] text-slate-950">
            {scannedFilesCount === null ? "Waiting" : formatScore(scannedFilesCount)}
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {skippedFilesCount && skippedFilesCount > 0
              ? `${formatScore(skippedFilesCount)} file${skippedFilesCount === 1 ? "" : "s"} skipped by scan limits or heuristics.`
              : hasSignals
                ? "No skipped files were reported in this snapshot."
                : "File scan counts appear after repository intake finishes."}
          </p>
        </div>

        <div className="rounded-[1.25rem] border border-slate-200 bg-white/82 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Frameworks</p>
          <p className="mt-3 font-mono text-2xl font-semibold tracking-[-0.03em] text-slate-950">
            {frameworksDetected.length ? frameworksDetected.length : hasSignals ? "0" : "Waiting"}
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-600">{frameworkSummary}</p>
        </div>

        <div
          className={cn(
            "rounded-[1.25rem] border px-4 py-4",
            confidenceLimited ? "border-amber-200 bg-amber-50/80" : "border-slate-200 bg-white/82",
          )}
        >
          <p className={cn("text-xs font-semibold uppercase tracking-[0.18em]", confidenceLimited ? "text-amber-700" : "text-slate-500")}>
            Score support
          </p>
          <p className="mt-3 font-mono text-2xl font-semibold tracking-[-0.03em] text-slate-950">
            {checksRun.length + checksSkipped.length > 0 ? `${checksRun.length}/${checksRun.length + checksSkipped.length}` : "Waiting"}
          </p>
          <p className={cn("mt-2 text-sm leading-6", confidenceLimited ? "text-amber-900" : "text-slate-600")}>
            {confidenceLimited
              ? manualReviewAreas.length || unsupportedTechnologies.length
                ? "Some areas stayed unsupported or manual-only, so treat the score as a first read."
                : "Coverage is still partial, so treat the score as a first read."
              : "Coverage is strong enough to support the current score inside the audited scope."}
          </p>
        </div>
      </div>

      <div className="mt-6 rounded-[1.25rem] border border-slate-200 bg-white/78 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Frameworks detected</p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
              Repo signals that shaped which checks ran.
              </p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {frameworksDetected.length ? (
            frameworksDetected.map((framework) => (
              <span
                key={framework}
                className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 font-mono text-[11px] font-semibold tracking-[0.04em] text-slate-700"
              >
                {framework}
              </span>
            ))
          ) : (
            <span className="rounded-full border border-dashed border-slate-300 px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              Awaiting repo map
            </span>
          )}
        </div>

        <div className="mt-5 border-t border-slate-200 pt-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Unsupported tech</p>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {unsupportedTechnologySummary}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {unsupportedTechnologies.length ? (
              unsupportedTechnologies.map((technology) => (
                <StatusBadge key={technology} tone="warning" mono size="sm">
                  Unsupported {technology}
                </StatusBadge>
              ))
            ) : (
              <span className="rounded-full border border-dashed border-slate-300 px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                None reported
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        {SURFACE_DEFINITIONS.map((surface) => {
          const state = surfaceState(surface.key, {
            supportedAreas,
            partialAreas,
            unsupportedAreas,
            manualReviewAreas,
            hasSignals,
          });

          return (
            <article key={surface.key} className="rounded-[1.25rem] border border-slate-200 bg-white/84 px-4 py-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">{surface.label}</p>
                  <p className="mt-2 text-sm font-semibold tracking-[-0.02em] text-slate-950">{state.label}</p>
                </div>
                <StatusBadge tone={state.tone} mono>
                  {state.label}
                </StatusBadge>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">{surface.detail}</p>
              <p className="mt-2 text-sm leading-6 text-slate-600">{state.detail}</p>
            </article>
          );
        })}
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <div className="space-y-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Area tags</p>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Keep supported, partial, unsupported, and manual-only scope visible.
            </p>
          </div>

          <TagCloud title="Supported" items={supportedAreas} tone="success" emptyLabel="None yet" />
          <TagCloud title="Partially supported" items={partialAreas} tone="warning" emptyLabel="None" />
          <TagCloud title="Unsupported" items={unsupportedAreas} tone="neutral" emptyLabel="None" />
          <TagCloud title="Needs manual review" items={manualReviewAreas} tone="info" emptyLabel="None" />
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <CheckSummary
            title="Checks run"
            description={checkedDescription}
            items={checksRun}
            tone="info"
            emptyLabel="No checks yet"
          />
          <CheckSummary
            title="Checks skipped"
            description={skippedDescription}
            items={checksSkipped}
            tone={checksSkipped.length ? "warning" : "neutral"}
            emptyLabel="Nothing skipped"
          />
        </div>
      </div>
    </section>
  );
}
