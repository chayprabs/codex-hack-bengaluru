import type { Audit, Finding, ScoreUpdateEvent } from "@/lib/types";

const FINDING_SEVERITY_RANK: Record<Finding["severity"], number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
};

function cleanText(value: string | null | undefined) {
  if (!value) {
    return null;
  }

  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length ? normalized : null;
}

function ensureSentence(value: string) {
  return /[.!?]$/.test(value) ? value : `${value}.`;
}

function reasonClause(value: string) {
  const trimmed = value.replace(/[.!?]+$/, "").trim();
  if (!trimmed.length) {
    return "risk stayed in scope";
  }

  const [firstWord, ...rest] = trimmed.split(" ");
  if (!rest.length) {
    return firstWord.toLowerCase();
  }

  if (/^[A-Z0-9]{2,}$/.test(firstWord)) {
    return trimmed;
  }

  return `${firstWord.toLowerCase()} ${rest.join(" ")}`.trim();
}

function strongestFinding(findings: Finding[]) {
  return [...findings].sort((left, right) => FINDING_SEVERITY_RANK[right.severity] - FINDING_SEVERITY_RANK[left.severity])[0] ?? null;
}

function hasNarrativePrefix(value: string) {
  return /^(score|coverage|trustscore)\b/i.test(value);
}

export function describeScoreUpdate(
  update: Pick<ScoreUpdateEvent, "reason" | "delta" | "coverage_delta" | "confidence_limited" | "coverage" | "coverage_band">,
) {
  const reason = cleanText(update.reason);
  if (reason) {
    if (hasNarrativePrefix(reason)) {
      return ensureSentence(reason);
    }

    const clause = reasonClause(reason);
    if ((update.delta ?? 0) < 0) {
      return `Score dropped because ${clause}.`;
    }
    if ((update.delta ?? 0) > 0) {
      return `Score improved after ${clause}.`;
    }
    if ((update.coverage_delta ?? 0) < 0 || update.confidence_limited) {
      return `Coverage reduced confidence because ${clause}.`;
    }
    if ((update.coverage_delta ?? 0) > 0) {
      return `Coverage improved because ${clause}.`;
    }

    return ensureSentence(reason);
  }

  if ((update.delta ?? 0) < 0) {
    return "Score dropped after a new audit signal landed.";
  }
  if ((update.delta ?? 0) > 0) {
    return "Score improved after a clean verification step landed.";
  }
  if ((update.coverage_delta ?? 0) !== 0 || update.confidence_limited) {
    return `Coverage settled at ${update.coverage}/100 (${update.coverage_band}).`;
  }
  return "The score changed after a new audit event.";
}

export function describeAuditScoreSnapshot(
  audit: Pick<
    Audit,
    | "status"
    | "findings"
    | "confidence_limited"
    | "unsupported_areas"
    | "needs_manual_review_areas"
    | "unsupported_technologies"
    | "checks_skipped"
  >,
) {
  const finding = strongestFinding(audit.findings);
  if (finding) {
    const source = cleanText(finding.impact_summary) ?? cleanText(finding.title) ?? "a persisted finding stayed in scope";
    return `Score stayed lower because ${reasonClause(source)}.`;
  }

  if (
    audit.confidence_limited ||
    audit.unsupported_areas.length > 0 ||
    audit.needs_manual_review_areas.length > 0 ||
    audit.unsupported_technologies.length > 0 ||
    audit.checks_skipped.length > 0
  ) {
    return "Coverage reduced confidence because part of the repo stayed unsupported or manual-review only.";
  }

  if (audit.status === "completed") {
    return "Score held after verifier closeout found no persisted findings in the audited scope.";
  }

  return "Coverage is still expanding while planner, scanner, and verifier settle.";
}
