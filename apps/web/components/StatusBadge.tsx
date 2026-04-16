import type { ReactNode } from "react";

import type { AgentState, AuditState, FindingSeverity } from "@/lib/types";
import { cn, formatSeverityLabel, titleCase } from "@/lib/utils";

export type StatusBadgeTone = "neutral" | "info" | "success" | "warning" | "danger" | "critical";
export type StatusBadgeSize = "sm" | "md";

type StatusBadgeProps = {
  children?: ReactNode;
  label?: string;
  tone?: StatusBadgeTone;
  size?: StatusBadgeSize;
  mono?: boolean;
  className?: string;
};

const toneClasses: Record<StatusBadgeTone, string> = {
  neutral: "border-slate-200 bg-slate-100 text-slate-700",
  info: "border-cyan-200 bg-cyan-50 text-cyan-700",
  success: "border-emerald-200 bg-emerald-50 text-emerald-700",
  warning: "border-amber-200 bg-amber-50 text-amber-700",
  danger: "border-rose-200 bg-rose-50 text-rose-700",
  critical: "border-rose-300 bg-rose-100 text-rose-800",
};

const sizeClasses: Record<StatusBadgeSize, string> = {
  sm: "px-2.5 py-1 text-[11px]",
  md: "px-3 py-1.5 text-xs",
};

export function toneFromAuditStatus(status: AuditState): StatusBadgeTone {
  switch (status) {
    case "running":
      return "info";
    case "completed":
      return "success";
    case "failed":
      return "danger";
    default:
      return "neutral";
  }
}

export const toneFromAgentStatus = toneFromAuditStatus;

export function toneFromSeverity(severity: FindingSeverity): StatusBadgeTone {
  switch (severity) {
    case "medium":
      return "warning";
    case "high":
      return "danger";
    case "critical":
      return "critical";
    default:
      return "neutral";
  }
}

export function formatStatusLabel(value: AuditState | AgentState) {
  return titleCase(value);
}

export function formatSeverityBadgeLabel(value: FindingSeverity) {
  return formatSeverityLabel(value);
}

export function StatusBadge({
  children,
  label,
  tone = "neutral",
  size = "md",
  mono = false,
  className,
}: Readonly<StatusBadgeProps>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border font-semibold uppercase tracking-[0.14em]",
        toneClasses[tone],
        sizeClasses[size],
        mono && "font-mono",
        className,
      )}
    >
      {children ?? label}
    </span>
  );
}
