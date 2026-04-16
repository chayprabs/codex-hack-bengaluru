import type {
  AgentStatus,
  AgentStatusEvent,
  AgentTrace,
  AgentTraceSource,
  AgentTraceStep,
  AgentTraceStepStatus,
  Audit,
  AuditCompleteEvent,
  Finding,
  FindingEvent,
  FindingSeverity,
  ScoreUpdateEvent,
} from "@/lib/types";
import { describeAuditScoreSnapshot, describeScoreUpdate } from "@/lib/scoreNarrative";

export type AuditActivityEvent =
  | {
      key: string;
      kind: "agent_status";
      occurredAt: string;
      payload: AgentStatusEvent;
    }
  | {
      key: string;
      kind: "finding";
      occurredAt: string;
      payload: FindingEvent;
    }
  | {
      key: string;
      kind: "score_update";
      occurredAt: string;
      payload: ScoreUpdateEvent;
    }
  | {
      key: string;
      kind: "audit_complete";
      occurredAt: string;
      payload: AuditCompleteEvent;
    };

export type StoryStageStatus = "complete" | "active" | "pending" | "failed";
export type StoryStageTone = "neutral" | "danger" | "warning" | "success" | "info";

export type StoryStage = {
  id: string;
  label: string;
  detail: string;
  status: StoryStageStatus;
  tone: StoryStageTone;
  timestamp?: string | null;
};

export type StoryMomentTone = "neutral" | "danger" | "warning" | "success" | "info";

export type StoryMoment = {
  id: string;
  label: string;
  detail: string;
  timestamp: string;
  tone: StoryMomentTone;
  highlight?: boolean;
  lane?: string | null;
};

export type FindingStory = {
  headline: string;
  currentLabel: string;
  statusLabel: string;
  impactLabel: string;
  evidenceLabel: string;
  suggestedPatch: string;
  isHighImpact: boolean;
  isRecent: boolean;
  stages: StoryStage[];
};

export type AgentLaneStory = {
  roleLabel: string;
  missionLabel: string;
  impactLabel: string;
  statusLabel: string;
  isLive: boolean;
  stages: StoryStage[];
};

export type AgentOperationalTrace = {
  agentName: string;
  headline: string;
  description: string;
  source: AgentTraceSource;
  updatedAt: string;
  steps: AgentTraceStep[];
};

export type AttackStorySummary = {
  phaseLabel: string;
  headline: string;
  detail: string;
  stages: StoryStage[];
};

export type ScoreMoment = {
  id: string;
  label: string;
  detail: string;
  score: number;
  previousScore: number | null;
  delta: number | null;
  coverage: number;
  previousCoverage: number | null;
  coverageDelta: number | null;
  coverageBand: Audit["coverage_band"];
  confidenceLimited: boolean;
  updatedAt: string;
  tone: StoryMomentTone;
  highlight?: boolean;
};

const HIGH_IMPACT_SEVERITIES: FindingSeverity[] = ["critical", "high"];
const RECENT_WINDOW_MS = 90_000;

function timestampValue(value: string | null | undefined) {
  if (!value) {
    return 0;
  }

  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function sortByOccurredAt(events: AuditActivityEvent[]) {
  return [...events].sort((left, right) => timestampValue(left.occurredAt) - timestampValue(right.occurredAt));
}

function hasActivityEvent(events: AuditActivityEvent[], key: string) {
  return events.some((event) => event.key === key);
}

function toneFromSeverity(severity: FindingSeverity): StoryStageTone {
  switch (severity) {
    case "critical":
    case "high":
      return "danger";
    case "medium":
      return "warning";
    default:
      return "neutral";
  }
}

function toneFromAgentState(status: AgentStatus["status"]): StoryMomentTone {
  switch (status) {
    case "failed":
      return "danger";
    case "completed":
      return "success";
    case "running":
      return "info";
    default:
      return "neutral";
  }
}

function toneFromScoreDelta(delta: number | null | undefined): StoryMomentTone {
  return delta !== null && delta !== undefined && delta < 0 ? "danger" : "success";
}

function createActivityKey(kind: string, parts: Array<string | number | null | undefined>) {
  return [kind, ...parts.map((part) => String(part ?? ""))].join(":");
}

function findingLocationLabel(finding: Pick<Finding, "files" | "line_hints">) {
  const filePath = finding.files[0];
  const lineHint = finding.line_hints[0];

  if (!filePath) {
    return "code anchor pending";
  }

  return `${filePath}${lineHint ? `:${lineHint}` : ""}`;
}

function hasFindingLocation(finding: Pick<Finding, "files" | "line_hints">) {
  return finding.files.length > 0 || finding.line_hints.length > 0;
}

function normalizeAgentName(value: string) {
  return value.trim().toLowerCase();
}

function severityRank(severity: FindingSeverity) {
  switch (severity) {
    case "critical":
      return 4;
    case "high":
      return 3;
    case "medium":
      return 2;
    default:
      return 1;
  }
}

function priorityFindings(findings: Finding[]) {
  return [...findings].sort((left, right) => {
    const severityDelta = severityRank(right.severity) - severityRank(left.severity);
    if (severityDelta !== 0) {
      return severityDelta;
    }

    return timestampValue(right.created_at) - timestampValue(left.created_at);
  });
}

function sortTraceSteps(steps: AgentTraceStep[]) {
  return [...steps].sort((left, right) => timestampValue(left.timestamp) - timestampValue(right.timestamp));
}

function agentStatusEvents(events: AuditActivityEvent[], agentName: string) {
  const normalizedName = normalizeAgentName(agentName);
  return sortByOccurredAt(events).filter(
    (event): event is Extract<AuditActivityEvent, { kind: "agent_status" }> =>
      event.kind === "agent_status" && normalizeAgentName(event.payload.name) === normalizedName,
  );
}

function latestTraceTimestamp(steps: AgentTraceStep[], fallback: string) {
  const latestStep = [...steps]
    .filter((step) => Boolean(step.timestamp))
    .sort((left, right) => timestampValue(right.timestamp) - timestampValue(left.timestamp))[0];

  return latestStep?.timestamp ?? fallback;
}

function latestAgent(audit: Audit, name: string) {
  return audit.agents.find((agent) => agent.name.toLowerCase() === name.toLowerCase()) ?? null;
}

function currentStageLabel(stages: StoryStage[]) {
  const active = stages.find((stage) => stage.status === "active");
  if (active) {
    return active.label;
  }

  const failed = stages.find((stage) => stage.status === "failed");
  if (failed) {
    return failed.label;
  }

  const pending = stages.find((stage) => stage.status === "pending");
  if (pending) {
    return pending.label;
  }

  return stages[stages.length - 1]?.label ?? "Story ready";
}

function majorFindingCount(audit: Audit) {
  return audit.findings.filter((finding) => HIGH_IMPACT_SEVERITIES.includes(finding.severity)).length;
}

function isRecentTimestamp(value: string | null | undefined) {
  const ts = timestampValue(value);
  if (!ts) {
    return false;
  }

  return Date.now() - ts <= RECENT_WINDOW_MS;
}

function containsAny(value: string, patterns: string[]) {
  return patterns.some((pattern) => value.includes(pattern));
}

function patchSuggestionForFinding(finding: Finding) {
  if (finding.suggested_patch) {
    return finding.suggested_patch;
  }

  const haystack = `${finding.title} ${finding.impact_summary} ${finding.files.join(" ")} ${finding.evidence_snippet ?? ""}`.toLowerCase();

  if (containsAny(haystack, ["webhook", "signature", "unsigned"])) {
    return "Validate provider signatures before parsing payloads or mutating billing state.";
  }

  if (containsAny(haystack, ["secret", "token", "credential", "env"])) {
    return "Rotate the exposed secret, remove it from checked-in examples, and gate future leakage in CI.";
  }

  if (containsAny(haystack, ["tenant", "workspace", "account_id", "workspace_id", "ownership", "idor"])) {
    return "Re-check tenant ownership server-side before loading, exporting, or mutating the requested resource.";
  }

  if (containsAny(haystack, ["markdown", "dependency", "package", "renderer", "runtime"])) {
    return "Pin the dependency to a patched range, rebuild the affected surface, and retest the user path.";
  }

  if (containsAny(haystack, ["lint", "typecheck", "workflow", "pipeline", "release", "build"])) {
    return "Restore blocking quality gates before packaging artifacts or allowing the release path to proceed.";
  }

  if (containsAny(haystack, ["postmessage", "origin"])) {
    return "Restrict trusted origins and validate the incoming message shape before processing it.";
  }

  return "Add a boundary check at the referenced path, then rerun verification before trusting the release.";
}

function findingVerificationStage(finding: Finding, audit: Audit): StoryStage {
  const verifier = latestAgent(audit, "verifier");

  if (finding.verification_state === "failed") {
    return {
      id: "verification",
      label: "Verification did not close",
      detail: "The verifier did not close this finding cleanly in the current run.",
      status: "failed",
      tone: "danger",
      timestamp: audit.updated_at,
    };
  }

  if (finding.verification_state === "manual_review") {
    return {
      id: "verification",
      label: "Manual review recommended",
      detail: "Automation left this finding for human review instead of marking it verifier-reviewed.",
      status: "pending",
      tone: "warning",
      timestamp: verifier?.updated_at ?? audit.updated_at,
    };
  }

  if (finding.verification_state === "verified") {
    return {
      id: "verification",
      label: "Verifier-reviewed",
      detail: "A verifier reviewed this finding and kept it in scope. This does not mean a fix was verified.",
      status: "complete",
      tone: "success",
      timestamp: verifier?.updated_at ?? audit.updated_at,
    };
  }

  if (finding.verification_state === "in_review") {
    return {
      id: "verification",
      label: "Verifier running",
      detail: "Verifier work is still running for this finding.",
      status: "active",
      tone: "info",
      timestamp: verifier?.updated_at ?? audit.updated_at,
    };
  }

  if (audit.status === "failed" || verifier?.status === "failed") {
    return {
      id: "verification",
      label: "Verification did not close",
      detail: "The audit ended before this finding could receive per-finding verifier closeout.",
      status: "failed",
      tone: "danger",
      timestamp: audit.updated_at,
    };
  }

  if (verifier?.status === "completed") {
    return {
      id: "verification",
      label: "Verifier lane finished",
      detail: "The verifier finished the audit, but this finding was not individually verifier-reviewed.",
      status: "pending",
      tone: "warning",
      timestamp: verifier.updated_at,
    };
  }

  if (verifier?.status === "running") {
    return {
      id: "verification",
      label: "Verifier running",
      detail: "Verifier work is testing impact and score consequences now.",
      status: "active",
      tone: "info",
      timestamp: verifier.updated_at,
    };
  }

  return {
    id: "verification",
    label: "Verification queued",
    detail: "The finding is waiting for verifier review.",
    status: "pending",
    tone: "neutral",
    timestamp: null,
  };
}

export function buildSeededAuditActivity(audit: Audit): AuditActivityEvent[] {
  const agentEvents: AuditActivityEvent[] = audit.agents.map((agent) => ({
    key: createActivityKey("agent_status", [agent.name, agent.updated_at, agent.status]),
    kind: "agent_status",
    occurredAt: agent.updated_at,
    payload: {
      audit_id: audit.id,
      name: agent.name,
      status: agent.status,
      message: agent.message,
      updated_at: agent.updated_at,
    },
  }));

  const findingEvents: AuditActivityEvent[] = audit.findings.map((finding) => ({
    key: createActivityKey("finding", [finding.id, finding.created_at]),
    kind: "finding",
    occurredAt: finding.created_at,
    payload: {
      ...finding,
      audit_id: audit.id,
    },
  }));

  const completionEvents: AuditActivityEvent[] =
    audit.status === "completed" || audit.status === "failed"
      ? [
          {
            key: createActivityKey("audit_complete", [audit.status, audit.updated_at, audit.score]),
            kind: "audit_complete",
            occurredAt: audit.updated_at,
            payload: {
              audit_id: audit.id,
              status: audit.status,
              repo_url: audit.repo_url,
              score: audit.score,
              coverage: audit.coverage,
              coverage_percent: audit.coverage_percent,
              coverage_band: audit.coverage_band,
              coverage_summary: audit.coverage_summary,
              confidence_limited: audit.confidence_limited,
              supported_areas: audit.supported_areas,
              partially_supported_areas: audit.partially_supported_areas,
              unsupported_areas: audit.unsupported_areas,
              needs_manual_review_areas: audit.needs_manual_review_areas,
              unsupported_technologies: audit.unsupported_technologies,
              scanned_files_count: audit.scanned_files_count,
              skipped_files_count: audit.skipped_files_count,
              frameworks_detected: audit.frameworks_detected,
              checks_run: audit.checks_run,
              checks_skipped: audit.checks_skipped,
              replay_records: audit.replay_records,
              updated_at: audit.updated_at,
              finding_count: audit.findings.length,
              message: audit.completion_message,
            },
          },
        ]
      : [];

  return sortByOccurredAt([...agentEvents, ...findingEvents, ...completionEvents]);
}

export function buildActivityEvent(
  event:
    | AgentStatusEvent
    | FindingEvent
    | ScoreUpdateEvent
    | AuditCompleteEvent,
  kind: AuditActivityEvent["kind"],
): AuditActivityEvent {
  switch (kind) {
    case "agent_status":
      return {
        key: createActivityKey(kind, [event.audit_id, (event as AgentStatusEvent).name, (event as AgentStatusEvent).updated_at]),
        kind,
        occurredAt: (event as AgentStatusEvent).updated_at,
        payload: event as AgentStatusEvent,
      };
    case "finding":
      return {
        key: createActivityKey(kind, [event.audit_id, (event as FindingEvent).id, (event as FindingEvent).created_at]),
        kind,
        occurredAt: (event as FindingEvent).created_at,
        payload: event as FindingEvent,
      };
    case "score_update":
      return {
        key: createActivityKey(kind, [
          event.audit_id,
          (event as ScoreUpdateEvent).updated_at,
          (event as ScoreUpdateEvent).score,
          (event as ScoreUpdateEvent).coverage,
        ]),
        kind,
        occurredAt: (event as ScoreUpdateEvent).updated_at,
        payload: event as ScoreUpdateEvent,
      };
    default:
      return {
        key: createActivityKey(kind, [event.audit_id, (event as AuditCompleteEvent).updated_at, (event as AuditCompleteEvent).status]),
        kind,
        occurredAt: (event as AuditCompleteEvent).updated_at,
        payload: event as AuditCompleteEvent,
      };
  }
}

export function appendAuditActivity(current: AuditActivityEvent[], incoming: AuditActivityEvent) {
  if (hasActivityEvent(current, incoming.key)) {
    return current;
  }

  return sortByOccurredAt([...current, incoming]);
}

export function appendScoreMoment(current: ScoreUpdateEvent[], incoming: ScoreUpdateEvent) {
  const key = createActivityKey("score_update", [incoming.audit_id, incoming.updated_at, incoming.score, incoming.coverage]);
  if (current.some((event) => createActivityKey("score_update", [event.audit_id, event.updated_at, event.score, event.coverage]) === key)) {
    return current;
  }

  return [...current, incoming].sort((left, right) => timestampValue(left.updated_at) - timestampValue(right.updated_at));
}

export function buildFindingStory(finding: Finding, audit: Audit): FindingStory {
  const scanner = latestAgent(audit, "scanner");
  const verificationStage = findingVerificationStage(finding, audit);
  const patchSuggestion = patchSuggestionForFinding(finding);
  const evidenceLabel = findingLocationLabel(finding);
  const isHighImpact = HIGH_IMPACT_SEVERITIES.includes(finding.severity);

  const stages: StoryStage[] = [
    {
      id: "discovered",
      label: "Finding published",
      detail: `Scanner surfaced a ${finding.severity} finding and opened the response lane.`,
      status: "complete",
      tone: toneFromSeverity(finding.severity),
      timestamp: finding.created_at,
    },
    {
      id: "confirmed",
      label: "Evidence captured",
      detail:
        verificationStage.status === "complete"
          ? `Evidence anchored at ${evidenceLabel} and carried into the final report after verifier review.`
          : scanner?.status === "completed" || hasFindingLocation(finding)
            ? `Evidence captured at ${evidenceLabel}. Per-finding verifier review is still pending.`
            : "Scanner flagged the path, but the evidence package is still building.",
      status: verificationStage.status === "complete" ? "complete" : scanner?.status === "running" ? "active" : "active",
      tone: verificationStage.status === "complete" ? "warning" : "warning",
      timestamp: scanner?.updated_at ?? finding.created_at,
    },
    {
      id: "patch",
      label: "Patch proposed",
      detail: patchSuggestion,
      status: audit.status === "failed" ? "failed" : "complete",
      tone: audit.status === "failed" ? "danger" : "warning",
      timestamp: audit.status === "failed" ? audit.updated_at : finding.created_at,
    },
    verificationStage,
  ];

  const currentLabel =
    verificationStage.status === "active"
      ? "Verifier review live"
      : finding.verification_state === "verified"
        ? "Verifier-reviewed finding"
        : finding.verification_state === "manual_review"
          ? "Manual review recommended"
          : verificationStage.status === "complete"
            ? "Ready for remediation handoff"
            : verificationStage.status === "failed"
              ? "Verification blocked"
              : "Needs verifier follow-up";

  return {
    headline: isHighImpact ? "Major finding in motion" : "Finding tracked through the story rail",
    currentLabel,
    statusLabel: currentStageLabel(stages),
    impactLabel: isHighImpact ? "High-impact lane" : "Supporting risk lane",
    evidenceLabel,
    suggestedPatch: patchSuggestion,
    isHighImpact,
    isRecent: isRecentTimestamp(finding.created_at),
    stages,
  };
}

function normalizeBackendTrace(agent: AgentStatus, trace: AgentTrace): AgentOperationalTrace {
  const steps = sortTraceSteps(
    trace.steps.map((step, index) => ({
      ...step,
      id: step.id || createActivityKey("trace_step", [trace.agent_name, step.kind, step.timestamp, index]),
    })),
  );

  return {
    agentName: agent.name,
    headline: trace.headline ?? `${agent.name} operational trace`,
    description:
      trace.summary ??
      "Safe operational trace emitted by the backend. Tool calls, evidence capture, and verification milestones are shown without raw reasoning.",
    source: trace.source,
    updatedAt: trace.updated_at || latestTraceTimestamp(steps, agent.updated_at),
    steps,
  };
}

function buildScannerTrace(agent: AgentStatus, audit: Audit, events: AuditActivityEvent[]): AgentOperationalTrace {
  const prioritizedFindings = priorityFindings(audit.findings);
  const leadFinding = prioritizedFindings[0] ?? null;
  const anchoredFinding = prioritizedFindings.find((finding) => hasFindingLocation(finding)) ?? leadFinding;
  const planner = latestAgent(audit, "planner");
  const verifier = latestAgent(audit, "verifier");
  const scannerEvents = agentStatusEvents(events, agent.name);
  const scanStartedAt = scannerEvents[0]?.occurredAt ?? (agent.status !== "queued" ? agent.updated_at : null);
  const searchSettledAt =
    scannerEvents.find((event) => event.payload.status === "completed")?.occurredAt ??
    (leadFinding ? leadFinding.created_at : agent.updated_at);
  const evidenceCapturedAt = anchoredFinding?.created_at ?? leadFinding?.created_at ?? null;
  const verificationStepStatus: AgentTraceStepStatus =
    audit.status === "failed" || verifier?.status === "failed"
      ? "failed"
      : leadFinding?.verification_state === "verified"
        ? "completed"
        : verifier?.status === "running"
          ? "active"
          : "pending";

  const steps: AgentTraceStep[] = [
    {
      id: createActivityKey("trace", [agent.name, "read_file", anchoredFinding?.files[0] ?? planner?.updated_at ?? agent.updated_at]),
      kind: "read_file",
      title: "Read file",
      detail: anchoredFinding?.files[0]
        ? `Opened ${anchoredFinding.files[0]} after planner scope and finding activity pointed to it as a likely boundary failure.`
        : planner?.status === "completed" || agent.status !== "queued"
          ? "Opened scoped files inside the mapped attack surface before promoting any candidate into the feed."
          : "Waiting for planner scope before opening candidate files.",
      status:
        anchoredFinding?.files[0] || planner?.status === "completed" || agent.status === "running" || agent.status === "completed"
          ? "completed"
          : agent.status === "failed"
            ? "failed"
            : "pending",
      timestamp: anchoredFinding?.created_at ?? planner?.updated_at ?? scanStartedAt,
      tool: "Read file",
      location: anchoredFinding ? findingLocationLabel(anchoredFinding) : null,
      finding_id: anchoredFinding?.id ?? null,
    },
    {
      id: createActivityKey("trace", [agent.name, "search_code", agent.updated_at, audit.findings.length]),
      kind: "search_code",
      title: "Searched code",
      detail: audit.findings.length
        ? `Pattern search narrowed ${audit.findings.length} finding candidate${audit.findings.length === 1 ? "" : "s"} across the scoped repository surface.`
        : agent.status === "running"
          ? "Scanner is searching boundary checks, runtime handlers, and configuration paths for risky patterns."
          : agent.status === "completed"
            ? "Search completed without promoting a persisted finding in the current snapshot."
            : "Search will begin once the lane leaves the queue.",
      status:
        audit.findings.length || agent.status === "completed"
          ? "completed"
          : agent.status === "running"
            ? "active"
            : agent.status === "failed"
              ? "failed"
              : "pending",
      timestamp: searchSettledAt,
      tool: "Search code",
      location: audit.scanned_files_count ? `${audit.scanned_files_count} files scanned` : null,
    },
    {
      id: createActivityKey("trace", [agent.name, "candidate_found", leadFinding?.id ?? agent.updated_at]),
      kind: "candidate_found",
      title: "Found candidate",
      detail: leadFinding
        ? `${leadFinding.title} surfaced as the strongest candidate and was promoted into the findings feed.`
        : agent.status === "running"
          ? "Scanner is still evaluating candidate paths before promoting one into the findings feed."
          : "No candidate has been promoted yet.",
      status:
        leadFinding
          ? "completed"
          : agent.status === "running"
            ? "active"
            : agent.status === "failed"
              ? "failed"
              : "pending",
      timestamp: leadFinding?.created_at ?? agent.updated_at,
      tool: "Candidate triage",
      location: leadFinding ? findingLocationLabel(leadFinding) : null,
      finding_id: leadFinding?.id ?? null,
    },
    {
      id: createActivityKey("trace", [agent.name, "evidence_recorded", anchoredFinding?.id ?? leadFinding?.id ?? agent.updated_at]),
      kind: "evidence_recorded",
      title: "Recorded evidence",
      detail: anchoredFinding && hasFindingLocation(anchoredFinding)
        ? `Evidence captured at ${findingLocationLabel(anchoredFinding)} and attached to the reportable finding.`
        : leadFinding
          ? "Finding has been published, but file-level evidence anchors are still being attached."
          : "Evidence will be recorded after a candidate is confirmed.",
      status:
        anchoredFinding && hasFindingLocation(anchoredFinding)
          ? "completed"
          : leadFinding
            ? "active"
            : agent.status === "failed"
              ? "failed"
              : "pending",
      timestamp: evidenceCapturedAt,
      tool: "Record evidence",
      location: anchoredFinding ? findingLocationLabel(anchoredFinding) : null,
      finding_id: anchoredFinding?.id ?? leadFinding?.id ?? null,
    },
    {
      id: createActivityKey("trace", [agent.name, "patch_proposed", leadFinding?.id ?? audit.updated_at]),
      kind: "patch_proposed",
      title: "Proposed patch",
      detail: leadFinding
        ? patchSuggestionForFinding(leadFinding)
        : "Patch guidance will be drafted once a candidate is confirmed and evidence is stable.",
      status:
        leadFinding
          ? audit.status === "failed"
            ? "failed"
            : "completed"
          : agent.status === "failed"
            ? "failed"
            : "pending",
      timestamp: leadFinding?.created_at ?? null,
      tool: "Patch proposal",
      location: leadFinding ? findingLocationLabel(leadFinding) : null,
      finding_id: leadFinding?.id ?? null,
    },
    {
      id: createActivityKey("trace", [agent.name, "verification", verifier?.updated_at ?? audit.updated_at]),
      kind: "verification",
      title:
        verificationStepStatus === "failed"
          ? "Verification did not close"
          : verificationStepStatus === "completed"
            ? "Verifier reviewed finding"
            : verifier?.status === "completed"
              ? "Verifier lane finished"
              : verifier?.status === "running"
                ? "Verifier running"
                : "Verification queued",
      detail:
        verificationStepStatus === "completed"
          ? "Verifier reviewed the scanner output and kept the strongest lead in scope."
          : verifier?.status === "completed"
            ? "Verifier finished the audit, but this lead was not individually verifier-reviewed."
            : verificationStepStatus === "active"
              ? "Verifier is testing the recorded evidence and score impact now."
              : verificationStepStatus === "failed"
                ? "Verification halted before the scanner lead could be cleanly closed."
                : "Verification is queued behind evidence capture and final review.",
      status: verificationStepStatus,
      timestamp: verifier?.updated_at ?? (audit.status === "completed" || audit.status === "failed" ? audit.updated_at : null),
      tool: "Verification",
      location: leadFinding ? findingLocationLabel(leadFinding) : null,
      finding_id: leadFinding?.id ?? null,
    },
  ];

  const source: AgentTraceSource =
    scannerEvents.length || audit.findings.length || audit.scanned_files_count > 0 ? "derived" : "placeholder";

  return {
    agentName: agent.name,
    headline: "Scanner operational trace",
    description:
      source === "placeholder"
        ? "Backend trace packets are not available yet, so this panel synthesizes safe operational milestones from the lane state and findings feed."
        : "This trace is synthesized from safe lane events, findings, and verification milestones. It avoids raw chain-of-thought while still showing concrete progress.",
    source,
    updatedAt: latestTraceTimestamp(steps, agent.updated_at),
    steps,
  };
}

export function canShowAgentTrace(agent: AgentStatus) {
  return Boolean(agent.trace?.steps?.length) || normalizeAgentName(agent.name) === "scanner";
}

export function buildAgentOperationalTrace(
  agent: AgentStatus,
  audit: Audit,
  events: AuditActivityEvent[],
): AgentOperationalTrace | null {
  if (agent.trace?.steps?.length) {
    return normalizeBackendTrace(agent, agent.trace);
  }

  if (normalizeAgentName(agent.name) === "scanner") {
    return buildScannerTrace(agent, audit, events);
  }

  return null;
}

export function buildAgentLaneStory(agent: AgentStatus, audit: Audit): AgentLaneStory {
  const normalizedName = agent.name.toLowerCase();

  if (normalizedName === "planner") {
    const stages: StoryStage[] = [
      {
        id: "map",
        label: "Attack surface mapped",
        detail: "Repository boundaries, workflows, and risky edges are being indexed.",
        status: agent.status === "queued" ? "pending" : "complete",
        tone: agent.status === "queued" ? "neutral" : "info",
        timestamp: agent.updated_at,
      },
      {
        id: "scope",
        label: "Hot zones scoped",
        detail: "Planner turns the audit into lanes the scanner and verifier can chase.",
        status: agent.status === "completed" ? "complete" : agent.status === "running" ? "active" : agent.status === "failed" ? "failed" : "pending",
        tone: agent.status === "failed" ? "danger" : agent.status === "completed" ? "success" : "info",
        timestamp: agent.updated_at,
      },
      {
        id: "handoff",
        label: "Scanner handoff",
        detail: "Scope is ready for exploit discovery and remediation planning.",
        status: agent.status === "completed" ? "complete" : agent.status === "failed" ? "failed" : "pending",
        tone: agent.status === "failed" ? "danger" : agent.status === "completed" ? "success" : "neutral",
        timestamp: agent.status === "completed" ? agent.updated_at : null,
      },
    ];

    return {
      roleLabel: "Command lane",
      missionLabel: "Sets the attack surface and prioritizes where evidence collection starts.",
      impactLabel: `${majorFindingCount(audit)} major findings downstream`,
      statusLabel: currentStageLabel(stages),
      isLive: agent.status === "running",
      stages,
    };
  }

  if (normalizedName === "scanner") {
    const findingsCount = audit.findings.length;
    const stages: StoryStage[] = [
      {
        id: "scan",
        label: "Discovery sweep",
        detail: "Scanner is walking configuration, runtime, and boundary code paths.",
        status: agent.status === "queued" ? "pending" : "complete",
        tone: agent.status === "queued" ? "neutral" : "danger",
        timestamp: agent.updated_at,
      },
      {
        id: "anchors",
        label: "Evidence anchored",
        detail: findingsCount ? `${findingsCount} findings now carry file-level evidence anchors.` : "No anchored findings have been emitted yet.",
        status: findingsCount ? "complete" : agent.status === "running" ? "active" : "pending",
        tone: findingsCount ? "warning" : "info",
        timestamp: findingsCount ? audit.findings[audit.findings.length - 1]?.created_at ?? agent.updated_at : agent.updated_at,
      },
      {
        id: "handoff",
        label: "Verifier handoff",
        detail: "Confirmed leads move into the final review lane.",
        status: agent.status === "completed" ? "complete" : agent.status === "failed" ? "failed" : "pending",
        tone: agent.status === "failed" ? "danger" : agent.status === "completed" ? "success" : "neutral",
        timestamp: agent.status === "completed" ? agent.updated_at : null,
      },
    ];

    return {
      roleLabel: "Discovery lane",
      missionLabel: "Turns suspicious surfaces into concrete findings with timestamps and anchors.",
      impactLabel: `${findingsCount} findings in feed`,
      statusLabel: currentStageLabel(stages),
      isLive: agent.status === "running",
      stages,
    };
  }

  const verifier = latestAgent(audit, "verifier");
  const verifiedFindingCount = audit.findings.filter((finding) => finding.verification_state === "verified").length;
  const unresolvedFindingCount = audit.findings.length - verifiedFindingCount;
  const stages: StoryStage[] = [
    {
      id: "review",
      label: "Evidence review",
      detail: "Verifier cross-checks whether surfaced findings hold up under closer scrutiny.",
      status: verifier?.status === "completed" ? "complete" : verifier?.status === "running" ? "active" : verifier?.status === "failed" ? "failed" : "pending",
      tone: verifier?.status === "failed" ? "danger" : verifier?.status === "completed" ? "success" : verifier?.status === "running" ? "info" : "neutral",
      timestamp: verifier?.updated_at ?? agent.updated_at,
    },
    {
      id: "score",
      label: "Score locked",
      detail: "Trust score changes become reviewable evidence instead of noisy scanner output.",
      status: audit.status === "completed" ? "complete" : audit.status === "failed" ? "failed" : verifier?.status === "running" ? "active" : "pending",
      tone: audit.status === "failed" ? "danger" : audit.status === "completed" ? "success" : verifier?.status === "running" ? "info" : "neutral",
      timestamp: audit.status === "completed" || audit.status === "failed" ? audit.updated_at : verifier?.updated_at ?? null,
    },
    {
      id: "closure",
      label: audit.status === "failed" ? "Verification did not close" : "Verifier lane finished",
      detail:
        audit.status === "completed"
          ? verifiedFindingCount > 0
            ? `The verifier lane closed with ${verifiedFindingCount} individually verifier-reviewed finding${verifiedFindingCount === 1 ? "" : "s"}.`
            : "The verifier lane closed, but no finding was individually verifier-reviewed."
          : audit.status === "failed"
            ? "The report closed early and needs manual follow-up."
            : "Waiting for the report to close.",
      status: audit.status === "completed" ? "complete" : audit.status === "failed" ? "failed" : "pending",
      tone: audit.status === "completed" ? "success" : audit.status === "failed" ? "danger" : "neutral",
      timestamp: audit.status === "completed" || audit.status === "failed" ? audit.updated_at : null,
    },
  ];

  return {
    roleLabel: "Verification lane",
    missionLabel: "Reviews the strongest findings and closes the report with explicit caveats about what was and was not verified.",
    impactLabel: audit.status === "completed" ? "Report closed" : `${majorFindingCount(audit)} major findings under review`,
    statusLabel: currentStageLabel(stages),
    isLive: agent.status === "running",
    stages,
  };
}

export function buildAttackStorySummary(audit: Audit): AttackStorySummary {
  const planner = latestAgent(audit, "planner");
  const scanner = latestAgent(audit, "scanner");
  const verifier = latestAgent(audit, "verifier");
  const majorFindings = majorFindingCount(audit);
  const verifiedFindingCount = audit.findings.filter((finding) => finding.verification_state === "verified").length;
  const unresolvedFindingCount = audit.findings.length - verifiedFindingCount;
  const supportedAreaCount = audit.supported_areas.length;
  const unresolvedAreaCount = audit.partially_supported_areas.length + audit.unsupported_areas.length;
  const checkCount = audit.checks_run.length;

  const stages: StoryStage[] = [
    {
      id: "discover",
      label: "Findings published",
      detail: audit.findings.length
        ? `${audit.findings.length} findings surfaced across the current audit story.`
        : "Scanner has not surfaced findings yet.",
      status: audit.findings.length ? "complete" : scanner?.status === "running" ? "active" : planner?.status === "completed" ? "pending" : "pending",
      tone: audit.findings.length ? "danger" : scanner?.status === "running" ? "info" : "neutral",
      timestamp: audit.findings[0]?.created_at ?? scanner?.updated_at ?? null,
    },
    {
      id: "confirm",
      label: "Evidence captured",
      detail:
        verifier?.status === "completed"
          ? verifiedFindingCount > 0
            ? `${verifiedFindingCount} finding${verifiedFindingCount === 1 ? "" : "s"} were individually verifier-reviewed.`
            : "Evidence was captured, but no finding was individually verifier-reviewed."
          : verifier?.status === "running"
            ? "Verifier is confirming impact and sorting signal from noise."
            : audit.findings.length
              ? "Evidence anchors are in place and waiting for verifier review."
              : "No evidence package has formed yet.",
      status:
        verifier?.status === "completed"
          ? "complete"
          : verifier?.status === "running"
            ? "active"
            : audit.findings.length
              ? "active"
              : "pending",
      tone:
        verifier?.status === "completed" ? "warning" : verifier?.status === "running" || audit.findings.length ? "warning" : "neutral",
      timestamp: verifier?.updated_at ?? audit.findings[audit.findings.length - 1]?.created_at ?? null,
    },
    {
      id: "patch",
      label: "Patch proposed",
      detail:
        audit.findings.length
          ? `${audit.findings.length} remediation paths are suggested directly from the finding patterns.`
          : "Patch planning will begin once a finding lands.",
      status: audit.status === "failed" ? "failed" : audit.findings.length ? "complete" : "pending",
      tone: audit.status === "failed" ? "danger" : audit.findings.length ? "warning" : "neutral",
      timestamp: audit.findings[0]?.created_at ?? null,
    },
    {
      id: "verify",
      label: audit.status === "failed" ? "Verification did not close" : "Verifier lane finished",
      detail:
        audit.status === "completed"
          ? verifiedFindingCount > 0
            ? `${verifiedFindingCount} finding${verifiedFindingCount === 1 ? "" : "s"} were verifier-reviewed and ${unresolvedFindingCount} remained unresolved or manual-review only.`
            : "The report is closed, but the remaining findings still need per-finding verifier review."
          : audit.status === "failed"
            ? "Verification closed early and needs manual follow-up."
            : verifier?.status === "running"
              ? "Verification is active and the story is still moving."
              : "Waiting for the final verification lane.",
      status:
        audit.status === "completed"
          ? "complete"
          : audit.status === "failed"
            ? "failed"
            : verifier?.status === "running"
              ? "active"
              : "pending",
      tone:
        audit.status === "completed" ? "success" : audit.status === "failed" ? "danger" : verifier?.status === "running" ? "info" : "neutral",
      timestamp: verifier?.updated_at ?? audit.updated_at,
    },
  ];

  const phaseLabel = currentStageLabel(stages);
  const headline =
    audit.status === "completed"
      ? "Audit story closed with explicit review state"
      : majorFindings
        ? `${majorFindings} major finding${majorFindings === 1 ? "" : "s"} moving through confirmation`
        : audit.findings.length
          ? "Findings are entering evidence review"
          : "Attack surface is still being mapped";
  const detail =
    audit.status === "completed"
      ? checkCount || supportedAreaCount
        ? `${checkCount} checks ran across ${supportedAreaCount} supported area${supportedAreaCount === 1 ? "" : "s"}. ${
            unresolvedAreaCount > 0
              ? `${unresolvedAreaCount} area${unresolvedAreaCount === 1 ? "" : "s"} remained partial or out of scope.`
              : verifiedFindingCount > 0
                ? "The report is ready for remediation handoff."
                : "The report closed without per-finding verifier review."
          }`
        : "High-impact issues now read as a contained response story instead of isolated scanner rows."
      : verifier?.status === "running"
        ? "The verifier lane is actively moving major findings from discovery into confirmed response steps."
        : scanner?.status === "running"
          ? "The scanner is still turning suspicious edges into actionable evidence."
          : "Live lanes are waiting for the next event.";

  return {
    phaseLabel,
    headline,
    detail,
    stages,
  };
}

export function buildStoryMoments(
  audit: Audit,
  events: AuditActivityEvent[],
  transportLabel: string,
): StoryMoment[] {
  const seededEvents = events.length ? events : buildSeededAuditActivity(audit);

  const moments: StoryMoment[] = [...seededEvents]
    .sort((left, right) => timestampValue(right.occurredAt) - timestampValue(left.occurredAt))
    .slice(0, 5)
    .map((event) => {
      if (event.kind === "finding") {
        const finding = event.payload;
        const isHighImpact = HIGH_IMPACT_SEVERITIES.includes(finding.severity);
        return {
          id: event.key,
          label: isHighImpact ? "Major finding published" : "Finding published",
          detail: `${finding.title} at ${findingLocationLabel(finding)}.`,
          timestamp: event.occurredAt,
          tone: isHighImpact ? "danger" : "warning",
          highlight: isRecentTimestamp(event.occurredAt),
          lane: "scanner",
        };
      }

      if (event.kind === "score_update") {
        const update = event.payload;
        return {
          id: event.key,
          label:
            update.delta !== null && update.delta < 0
              ? "TrustScore dropped"
              : update.delta !== null && update.delta > 0
                ? "TrustScore improved"
                : "TrustScore held",
          detail: describeScoreUpdate(update),
          timestamp: event.occurredAt,
          tone: toneFromScoreDelta(update.delta),
          highlight: isRecentTimestamp(event.occurredAt),
          lane: "verifier",
        };
      }

      if (event.kind === "audit_complete") {
        const completionTone: StoryMomentTone = audit.status === "failed" ? "danger" : "success";
        return {
          id: event.key,
          label: audit.status === "failed" ? "Report closed early" : "Report locked",
          detail:
            event.payload.message ??
            (audit.status === "failed"
              ? "Verification stalled before the report could close cleanly."
              : "Verification locked the response story for handoff."),
          timestamp: event.occurredAt,
          tone: completionTone,
          highlight: isRecentTimestamp(event.occurredAt),
          lane: "verifier",
        };
      }

      return {
        id: event.key,
        label: `${event.payload.name} published`,
        detail: event.payload.message || `${event.payload.name} published a new lane update.`,
        timestamp: event.occurredAt,
        tone: toneFromAgentState(event.payload.status),
        highlight: isRecentTimestamp(event.occurredAt),
        lane: event.payload.name,
      };
    });

  const transportMoment: StoryMoment = {
    id: `transport:${transportLabel}:${audit.updated_at}`,
    label: "Stream heartbeat",
    detail: `${transportLabel} is keeping the attack story current.`,
    timestamp: audit.updated_at,
    tone: "info",
    highlight: false,
    lane: "stream",
  };

  return [...moments, transportMoment].slice(0, 5);
}

export function buildScoreMoments(
  audit: Audit,
  history: ScoreUpdateEvent[],
  completionEvent: AuditCompleteEvent | null,
): ScoreMoment[] {
  const seededHistory =
    history.length > 0
      ? history
      : [
          {
            audit_id: audit.id,
            score: audit.score,
            previous_score: audit.score_baseline,
            delta: audit.score - audit.score_baseline,
            coverage: audit.coverage,
            previous_coverage: audit.coverage_baseline,
            coverage_delta: audit.coverage - audit.coverage_baseline,
            coverage_band: audit.coverage_band,
            coverage_summary: audit.coverage_summary,
            confidence_limited: audit.confidence_limited,
            reason: describeAuditScoreSnapshot(audit),
            supported_areas: audit.supported_areas,
            partially_supported_areas: audit.partially_supported_areas,
            unsupported_areas: audit.unsupported_areas,
            needs_manual_review_areas: audit.needs_manual_review_areas,
            unsupported_technologies: audit.unsupported_technologies,
            scanned_files_count: audit.scanned_files_count,
            skipped_files_count: audit.skipped_files_count,
            frameworks_detected: audit.frameworks_detected,
            checks_run: audit.checks_run,
            checks_skipped: audit.checks_skipped,
            updated_at: audit.updated_at,
          },
        ];

  const moments: ScoreMoment[] = seededHistory
    .slice()
    .sort((left, right) => timestampValue(right.updated_at) - timestampValue(left.updated_at))
    .slice(0, 4)
    .map((event, index) => ({
      id: createActivityKey("score_update", [event.audit_id, event.updated_at, event.score, index]),
      label:
        index === 0
          ? "Current TrustScore posture"
          : event.delta !== null && event.delta < 0
            ? "Risk expanded"
            : event.delta !== null && event.delta > 0
              ? "TrustScore recovered"
              : "TrustScore held",
      detail: describeScoreUpdate(event),
      score: event.score,
      previousScore: event.previous_score,
      delta: event.delta,
      coverage: event.coverage,
      previousCoverage: event.previous_coverage,
      coverageDelta: event.coverage_delta,
      coverageBand: event.coverage_band,
      confidenceLimited: event.confidence_limited,
      updatedAt: event.updated_at,
      tone: toneFromScoreDelta(event.delta),
      highlight: index === 0 || isRecentTimestamp(event.updated_at),
    }));

  if (completionEvent && !moments.some((moment) => moment.updatedAt === completionEvent.updated_at && moment.delta === 0)) {
    moments.unshift({
      id: `score_complete:${completionEvent.audit_id}:${completionEvent.updated_at}:${completionEvent.score}`,
      label: completionEvent.status === "failed" ? "Verification blocked" : "Verification locked",
      detail:
        completionEvent.message ??
        (completionEvent.status === "failed"
          ? "The report ended before a clean verification closeout."
          : "The report closed and the score is ready for remediation handoff."),
      score: completionEvent.score,
      previousScore: completionEvent.score,
      delta: 0,
      coverage: completionEvent.coverage,
      previousCoverage: completionEvent.coverage,
      coverageDelta: 0,
      coverageBand: completionEvent.coverage_band,
      confidenceLimited: completionEvent.confidence_limited,
      updatedAt: completionEvent.updated_at,
      tone: completionEvent.status === "failed" ? "danger" : "success",
      highlight: true,
    });
  }

  return moments.slice(0, 4);
}
