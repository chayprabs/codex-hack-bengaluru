import type { ReactNode } from "react";

import type {
  AgentState,
  AuditState,
  FindingConfidence,
  FindingProofType,
  ReplayRecordReadiness,
  FindingSeverity,
  FindingVerificationState,
} from "@/lib/types";
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

export function toneFromFindingConfidence(confidence: FindingConfidence): StatusBadgeTone {
  switch (confidence) {
    case "high":
      return "success";
    case "medium":
      return "info";
    default:
      return "warning";
  }
}

export function toneFromFindingVerificationState(state: FindingVerificationState): StatusBadgeTone {
  switch (state) {
    case "verified":
      return "success";
    case "manual_review":
      return "warning";
    case "failed":
      return "danger";
    case "in_review":
      return "info";
    default:
      return "neutral";
  }
}

export function toneFromFindingProofType(proofType: FindingProofType): StatusBadgeTone {
  switch (proofType) {
    case "runtime_check":
      return "info";
    case "exploit_succeeded":
      return "danger";
    case "manual_review_recommendation":
      return "warning";
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

export function formatFindingConfidenceBadgeLabel(value: FindingConfidence) {
  switch (value) {
    case "high":
      return "High confidence";
    case "medium":
      return "Supported";
    default:
      return "Needs review";
  }
}

export function describeFindingConfidence(value: FindingConfidence) {
  switch (value) {
    case "high":
      return "Evidence is strong enough that this issue is likely real.";
    case "medium":
      return "The signal is meaningful, but it still depends on surrounding code or runtime context.";
    default:
      return "Worth checking, but not proven yet.";
  }
}

export function formatFindingVerificationBadgeLabel(value: FindingVerificationState) {
  switch (value) {
    case "verified":
      return "Reviewed";
    case "in_review":
      return "Under review";
    case "manual_review":
      return "Manual review";
    case "failed":
      return "Review blocked";
    default:
      return "Unreviewed";
  }
}

export function describeFindingVerificationState(value: FindingVerificationState) {
  switch (value) {
    case "verified":
      return "A reviewer checked this finding and kept it in scope. This does not confirm a fix.";
    case "in_review":
      return "Review is still running for this finding.";
    case "manual_review":
      return "Automation stopped short and handed this finding to a human.";
    case "failed":
      return "Review did not finish cleanly for this finding.";
    default:
      return "No finding-level review has been published yet.";
  }
}

export function formatFindingProofBadgeLabel(value: FindingProofType) {
  switch (value) {
    case "runtime_check":
      return "Runtime evidence";
    case "exploit_succeeded":
      return "Exploit confirmed";
    case "manual_review_recommendation":
      return "Review lead";
    default:
      return "Code evidence";
  }
}

export function describeFindingProofType(value: FindingProofType) {
  switch (value) {
    case "runtime_check":
      return "Backed by runtime output or observed behavior.";
    case "exploit_succeeded":
      return "The unsafe behavior was reproduced.";
    case "manual_review_recommendation":
      return "There is enough signal to investigate, but not enough to prove exploitation.";
    default:
      return "Backed by a code or config pattern.";
  }
}

export function formatReplayReadinessBadgeLabel(value: ReplayRecordReadiness) {
  return value === "regression_ready" ? "Retest draft ready" : "Manual follow-up";
}

export function describeReplayReadiness(value: ReplayRecordReadiness) {
  return value === "regression_ready"
    ? "A retest draft is ready to hand off. It is not an executed CI test yet."
    : "A retest idea exists, but it still needs human follow-up before it should be trusted.";
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
