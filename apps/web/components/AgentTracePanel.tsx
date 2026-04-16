"use client";

import { useEffect } from "react";

import type { AgentOperationalTrace } from "@/lib/auditStory";
import type { AgentStatus, AgentTraceSource, AgentTraceStepStatus } from "@/lib/types";
import { formatDateTime, formatRelativeTime } from "@/lib/format";
import { cn, titleCase } from "@/lib/utils";
import { StatusBadge, toneFromAgentStatus, type StatusBadgeTone } from "@/components/StatusBadge";

type AgentTracePanelProps = {
  agent: AgentStatus | null;
  trace: AgentOperationalTrace | null;
  open: boolean;
  onClose: () => void;
};

function toneFromTraceStatus(status: AgentTraceStepStatus): StatusBadgeTone {
  switch (status) {
    case "failed":
      return "danger";
    case "active":
      return "info";
    case "completed":
      return "success";
    default:
      return "neutral";
  }
}

function sourceLabel(source: AgentTraceSource) {
  switch (source) {
    case "backend":
      return "Live backend trace";
    case "derived":
      return "Synthesized trace";
    default:
      return "Placeholder trace";
  }
}

function sourceTone(source: AgentTraceSource): StatusBadgeTone {
  switch (source) {
    case "backend":
      return "success";
    case "derived":
      return "info";
    default:
      return "warning";
  }
}

function stepDotClassName(status: AgentTraceStepStatus) {
  switch (status) {
    case "failed":
      return "border-rose-300 bg-rose-500 shadow-[0_0_0_6px_rgba(244,63,94,0.12)]";
    case "active":
      return "border-cyan-300 bg-cyan-500 shadow-[0_0_0_6px_rgba(6,182,212,0.12)]";
    case "completed":
      return "border-emerald-300 bg-emerald-500 shadow-[0_0_0_6px_rgba(16,185,129,0.12)]";
    default:
      return "border-slate-300 bg-white";
  }
}

export function AgentTracePanel({ agent, trace, open, onClose }: Readonly<AgentTracePanelProps>) {
  useEffect(() => {
    if (!open) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, open]);

  if (!open || !agent || !trace) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/30 backdrop-blur-[3px]" onClick={onClose}>
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="agent-trace-title"
        className="trace-panel-enter absolute inset-y-0 right-0 flex h-full w-full max-w-2xl flex-col border-l border-slate-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,250,252,0.96))] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b border-slate-200 px-5 py-5 sm:px-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Operational trace</p>
              <h2 id="agent-trace-title" className="mt-2 font-mono text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {agent.name}
              </h2>
              <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">{trace.description}</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white text-lg text-slate-500 transition hover:border-slate-300 hover:text-slate-950"
              aria-label="Close trace panel"
            >
              ×
            </button>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <StatusBadge tone={toneFromAgentStatus(agent.status)} mono>
              {titleCase(agent.status)}
            </StatusBadge>
            <StatusBadge tone={sourceTone(trace.source)}>{sourceLabel(trace.source)}</StatusBadge>
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              {trace.steps.length} step{trace.steps.length === 1 ? "" : "s"}
            </span>
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              Updated {formatRelativeTime(trace.updatedAt)}
            </span>
          </div>
        </div>

        <div className="border-b border-slate-200 bg-slate-50/80 px-5 py-4 text-sm leading-6 text-slate-700 sm:px-6">
          <p className="font-medium text-slate-950">{trace.headline}</p>
          <p className="mt-2">
            Safe operational trace only. This panel shows file access, searches, evidence capture, patch guidance, and verification state without exposing chain-of-thought.
          </p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6">
          <ol className="space-y-5">
            {trace.steps.map((step, index) => (
              <li key={step.id} className="relative pl-10">
                {index < trace.steps.length - 1 ? (
                  <span className="absolute left-[0.875rem] top-7 h-[calc(100%+1.25rem)] w-px bg-slate-200" aria-hidden="true" />
                ) : null}
                <span
                  className={cn(
                    "absolute left-0 top-1 inline-flex h-7 w-7 items-center justify-center rounded-full border-2 transition",
                    stepDotClassName(step.status),
                    step.status === "active" && "story-card-live",
                  )}
                  aria-hidden="true"
                />

                <article className="rounded-[1.35rem] border border-slate-200 bg-white/90 p-4 shadow-sm">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{titleCase(step.kind)}</p>
                      <h3 className="mt-2 text-base font-semibold tracking-[-0.02em] text-slate-950">{step.title}</h3>
                    </div>
                    <StatusBadge tone={toneFromTraceStatus(step.status)} mono>
                      {titleCase(step.status)}
                    </StatusBadge>
                  </div>

                  <p className="mt-3 text-sm leading-6 text-slate-700">{step.detail}</p>

                  <dl className="mt-4 grid gap-3 text-sm text-slate-600 sm:grid-cols-3">
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2.5">
                      <dt className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Time</dt>
                      <dd className="mt-1 font-mono text-sm font-semibold text-slate-950">
                        {step.timestamp ? formatDateTime(step.timestamp) : "Pending"}
                      </dd>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2.5">
                      <dt className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Operation</dt>
                      <dd className="mt-1 text-sm font-semibold text-slate-950">{step.tool ?? "System event"}</dd>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2.5">
                      <dt className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Location</dt>
                      <dd className="mt-1 break-all font-mono text-sm font-semibold text-slate-950">
                        {step.location ?? "Trace-safe summary"}
                      </dd>
                    </div>
                  </dl>
                </article>
              </li>
            ))}
          </ol>
        </div>
      </aside>
    </div>
  );
}
