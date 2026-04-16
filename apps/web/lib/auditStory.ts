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
      label: "Review blocked",
      detail: "Review did not close cleanly for this finding.",
      status: "failed",
      tone: "danger",
      timestamp: audit.updated_at,
    };
  }

  if (finding.verification_state === "manual_review") {
    return {
      id: "verification",
      label: "Needs manual review",
      detail: "Automation handed this finding to a human instead of closing review.",
      status: "pending",
      tone: "warning",
      timestamp: verifier?.updated_at ?? audit.updated_at,
    };
  }

  if (finding.verification_state === "verified") {
    return {
      id: "verification",
      label: "Reviewed",
      detail: "A reviewer checked this finding and kept it in scope. This does not confirm a fix.",
      status: "complete",
      tone: "success",
      timestamp: verifier?.updated_at ?? audit.updated_at,
    };
  }

  if (finding.verification_state === "in_review") {
    return {
      id: "verification",
      label: "Review running",
      detail: "Review is still running for this finding.",
      status: "active",
      tone: "info",
      timestamp: verifier?.updated_at ?? audit.updated_at,
    };
  }

  if (audit.status === "failed" || verifier?.status === "failed") {
    return {
      id: "verification",
      label: "Review blocked",
      detail: "The audit ended before this finding received finding-level review.",
      status: "failed",
      tone: "danger",
      timestamp: audit.updated_at,
    };
  }

  if (verifier?.status === "completed") {
    return {
      id: "verification",
      label: "Review finished",
      detail: "Review finished for the audit, but this finding was not individually reviewed.",
      status: "pending",
      tone: "warning",
      timestamp: verifier.updated_at,
    };
  }

  if (verifier?.status === "running") {
    return {
      id: "verification",
      label: "Review running",
      detail: "Review is testing impact and score consequences now.",
      status: "active",
      tone: "info",
      timestamp: verifier.updated_at,
    };
  }

  return {
    id: "verification",
    label: "Review queued",
    detail: "This finding is waiting for review.",
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
      trace: agent.trace ?? null,
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

  const scoreEvents: AuditActivityEvent[] = [
    {
      key: createActivityKey("score_update", [audit.id, audit.updated_at, audit.score, audit.coverage]),
      kind: "score_update",
      occurredAt: audit.updated_at,
      payload: {
        audit_id: audit.id,
        score: audit.score,
        previous_score: audit.score_baseline,
        delta: audit.score - audit.score_baseline,
        coverage: audit.coverage,
        coverage_percent: audit.coverage_percent,
        previous_coverage: audit.coverage_baseline,
        coverage_delta: audit.coverage - audit.coverage_baseline,
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
        reason: describeAuditScoreSnapshot(audit),
        updated_at: audit.updated_at,
      },
    },
  ];

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

  return sortByOccurredAt([...agentEvents, ...findingEvents, ...scoreEvents, ...completionEvents]);
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
      label: "Finding opened",
      detail: `Scanner logged a ${finding.severity} issue.`,
      status: "complete",
      tone: toneFromSeverity(finding.severity),
      timestamp: finding.created_at,
    },
    {
      id: "confirmed",
      label: "Evidence attached",
      detail:
        verificationStage.status === "complete"
          ? `Evidence is anchored at ${evidenceLabel} and included in the final report.`
          : scanner?.status === "completed" || hasFindingLocation(finding)
            ? `Evidence is anchored at ${evidenceLabel}. Review is still pending.`
            : "Evidence is still being attached.",
      status: verificationStage.status === "complete" ? "complete" : scanner?.status === "running" ? "active" : "active",
      tone: verificationStage.status === "complete" ? "warning" : "warning",
      timestamp: scanner?.updated_at ?? finding.created_at,
    },
    {
      id: "patch",
      label: "Fix drafted",
      detail: patchSuggestion,
      status: audit.status === "failed" ? "failed" : "complete",
      tone: audit.status === "failed" ? "danger" : "warning",
      timestamp: audit.status === "failed" ? audit.updated_at : finding.created_at,
    },
    verificationStage,
  ];

  const currentLabel =
    verificationStage.status === "active"
      ? "Review in progress"
      : finding.verification_state === "verified"
        ? "Reviewed"
        : finding.verification_state === "manual_review"
          ? "Needs manual review"
          : verificationStage.status === "complete"
            ? "Ready to fix"
            : verificationStage.status === "failed"
              ? "Review blocked"
              : "Waiting for review";

  return {
    headline: isHighImpact ? "Major issue" : "Finding in review",
    currentLabel,
    statusLabel: currentStageLabel(stages),
    impactLabel: isHighImpact ? "High impact" : "Supporting risk",
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
      "Safe trace from the backend. It shows tools, evidence, and review steps without raw reasoning.",
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
        ? `Opened ${anchoredFinding.files[0]} after scope narrowed to this boundary.`
        : planner?.status === "completed" || agent.status !== "queued"
          ? "Opened scoped files before promoting a candidate into the feed."
          : "Waiting for scope before opening candidate files.",
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
        ? `Search narrowed ${audit.findings.length} finding candidate${audit.findings.length === 1 ? "" : "s"} across the repo.`
        : agent.status === "running"
          ? "Scanner is searching boundary checks, runtime handlers, and config paths."
          : agent.status === "completed"
            ? "Search completed without promoting a persisted finding."
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
        ? `${leadFinding.title} was the strongest lead and entered the findings feed.`
        : agent.status === "running"
          ? "Scanner is still evaluating leads before promoting one into the findings feed."
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
        ? `Evidence attached at ${findingLocationLabel(anchoredFinding)}.`
        : leadFinding
          ? "The finding is published, but file-level anchors are still being attached."
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
          ? "Review blocked"
          : verificationStepStatus === "completed"
            ? "Review complete"
            : verifier?.status === "completed"
              ? "Review finished"
              : verifier?.status === "running"
                ? "Review running"
                : "Review queued",
      detail:
        verificationStepStatus === "completed"
          ? "Review kept the strongest lead in scope."
          : verifier?.status === "completed"
            ? "Review finished for the audit, but this lead was not individually reviewed."
            : verificationStepStatus === "active"
              ? "Review is testing the recorded evidence and score impact now."
              : verificationStepStatus === "failed"
                ? "Review stopped before this lead could be cleanly closed."
                : "Waiting for review.",
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

function buildPlannerTrace(agent: AgentStatus, audit: Audit, events: AuditActivityEvent[]): AgentOperationalTrace {
  const plannerEvents = agentStatusEvents(events, agent.name);
  const scanner = latestAgent(audit, "scanner");
  const trackedAreas = [...audit.supported_areas, ...audit.partially_supported_areas];
  const scopedAt = plannerEvents[0]?.occurredAt ?? (agent.status !== "queued" ? agent.updated_at : null);
  const handoffAt = scanner?.updated_at ?? (agent.status === "completed" ? agent.updated_at : null);
  const plannerSource: AgentTraceSource =
    plannerEvents.length ||
    agent.status !== "queued" ||
    audit.frameworks_detected.length > 0 ||
    audit.scanned_files_count > 0
      ? "derived"
      : "placeholder";

  const steps: AgentTraceStep[] = [
    {
      id: createActivityKey("trace", [agent.name, "scope_loaded", scopedAt ?? audit.id]),
      kind: "scope_loaded",
      title: "Loaded repo scope",
      detail:
        audit.frameworks_detected.length > 0
          ? `Planner loaded repo scope from ${audit.frameworks_detected.length} detected framework signal${audit.frameworks_detected.length === 1 ? "" : "s"} and ${audit.scanned_files_count || 0} scanned file${audit.scanned_files_count === 1 ? "" : "s"}.`
          : agent.status === "queued"
            ? "Waiting for repo intake and mapper output before loading audit scope."
            : "Planner loaded the initial repo scope and began shaping the attack surface.",
      status:
        agent.status === "failed"
          ? "failed"
          : agent.status === "queued"
            ? "pending"
            : "completed",
      timestamp: scopedAt,
      tool: "Repo mapper",
      location: audit.frameworks_detected.length ? audit.frameworks_detected.join(", ") : null,
    },
    {
      id: createActivityKey("trace", [agent.name, "search_code", agent.updated_at, trackedAreas.length]),
      kind: "search_code",
      title: "Mapped attack surface",
      detail:
        trackedAreas.length > 0
          ? `Planner turned the repo map into ${trackedAreas.length} tracked surface${trackedAreas.length === 1 ? "" : "s"} across ${trackedAreas.slice(0, 3).join(", ")}${trackedAreas.length > 3 ? ", and more" : ""}.`
          : agent.status === "running"
            ? "Planner is still converting the repo map into concrete lanes and likely exploit surfaces."
            : agent.status === "completed"
              ? "Planner finished the repo map handoff without publishing named surfaces in this snapshot."
              : "Attack-surface mapping starts once repo scope is available.",
      status:
        agent.status === "completed"
          ? "completed"
          : agent.status === "running"
            ? "active"
            : agent.status === "failed"
              ? "failed"
              : "pending",
      timestamp: agent.updated_at,
      tool: "Planner",
      location: trackedAreas.length ? trackedAreas.slice(0, 3).join(", ") : null,
    },
    {
      id: createActivityKey("trace", [agent.name, "candidate_found", audit.checks_run.length, audit.checks_skipped.length]),
      kind: "candidate_found",
      title: "Prioritized specialist lanes",
      detail:
        audit.checks_run.length > 0 || audit.checks_skipped.length > 0
          ? `Planner handed off ${audit.checks_run.length} planned check${audit.checks_run.length === 1 ? "" : "s"} with ${audit.checks_skipped.length} deferred lane${audit.checks_skipped.length === 1 ? "" : "s"}.`
          : scanner?.status === "running" || scanner?.status === "completed"
            ? "Planner handoff completed and the scanner lane is already consuming the scoped plan."
            : agent.status === "completed"
              ? "Planner handoff is complete and scanner work can begin."
              : "Specialist prioritization is still pending.",
      status:
        agent.status === "completed" || scanner?.status === "running" || scanner?.status === "completed"
          ? "completed"
          : agent.status === "running"
            ? "active"
            : agent.status === "failed"
              ? "failed"
              : "pending",
      timestamp: handoffAt ?? agent.updated_at,
      tool: "Lane planner",
      location: audit.checks_run.length ? audit.checks_run.slice(0, 3).join(", ") : null,
    },
    {
      id: createActivityKey("trace", [agent.name, "note", scanner?.status ?? agent.status, audit.updated_at]),
      kind: "note",
      title:
        agent.status === "failed"
          ? "Planner handoff failed"
          : agent.status === "completed"
            ? "Scanner handoff published"
            : agent.status === "running"
              ? "Planner handoff forming"
              : "Planner queued",
      detail:
        agent.status === "completed"
          ? scanner?.status === "running" || scanner?.status === "completed"
            ? "Planner completed the scope handoff and downstream discovery is already in motion."
            : "Planner completed its handoff and queued the scanner lane."
          : agent.status === "failed"
            ? "Planner did not complete cleanly, so downstream coverage should be treated as partial."
            : agent.status === "running"
              ? "Planner is still shaping the handoff the scanner and verifier will follow."
              : "Planner has not published a handoff yet.",
      status:
        agent.status === "completed"
          ? "completed"
          : agent.status === "failed"
            ? "failed"
            : agent.status === "running"
              ? "active"
              : "pending",
      timestamp: handoffAt ?? agent.updated_at,
      tool: "Planner note",
      location: scanner?.status ? `scanner:${scanner.status}` : null,
    },
  ];

  return {
    agentName: agent.name,
    headline: "Planner operational trace",
    description:
      plannerSource === "placeholder"
        ? "Backend trace packets are not available yet, so this panel synthesizes safe planning milestones from repo coverage, lane status, and handoff state."
        : "This trace is synthesized from safe planning signals such as repo mapping, lane selection, and scanner handoff without exposing raw reasoning.",
    source: plannerSource,
    updatedAt: latestTraceTimestamp(steps, agent.updated_at),
    steps,
  };
}

function buildVerifierTrace(agent: AgentStatus, audit: Audit, events: AuditActivityEvent[]): AgentOperationalTrace {
  const verifierEvents = agentStatusEvents(events, agent.name);
  const prioritizedFindings = priorityFindings(audit.findings);
  const strongestFinding = prioritizedFindings[0] ?? null;
  const verifiedFindings = audit.findings.filter((finding) => finding.verification_state === "verified").length;
  const replayReadyCount = audit.replay_records.filter((record) => record.readiness === "regression_ready").length;
  const reviewStartedAt = verifierEvents[0]?.occurredAt ?? (agent.status !== "queued" ? agent.updated_at : null);
  const finalAt = audit.status === "completed" || audit.status === "failed" ? audit.updated_at : agent.updated_at;
  const verifierSource: AgentTraceSource =
    verifierEvents.length || audit.findings.length > 0 || audit.status !== "queued" ? "derived" : "placeholder";

  const verificationStatus: AgentTraceStepStatus =
    audit.status === "failed" || agent.status === "failed"
      ? "failed"
      : verifiedFindings > 0 || (agent.status === "completed" && audit.findings.length === 0)
        ? "completed"
        : agent.status === "running"
          ? "active"
          : "pending";

  const steps: AgentTraceStep[] = [
    {
      id: createActivityKey("trace", [agent.name, "scope_loaded", reviewStartedAt ?? audit.id, audit.findings.length]),
      kind: "scope_loaded",
      title: "Loaded evidence bundle",
      detail:
        strongestFinding
          ? `Verifier loaded ${audit.findings.length} finding${audit.findings.length === 1 ? "" : "s"} and prioritized ${strongestFinding.title} for closeout review.`
          : agent.status === "queued"
            ? "Waiting for findings or a final score snapshot before verification begins."
            : "Verifier loaded the current report state and is preparing closeout.",
      status:
        agent.status === "failed"
          ? "failed"
          : agent.status === "queued"
            ? "pending"
            : "completed",
      timestamp: reviewStartedAt,
      tool: "Verifier intake",
      location: strongestFinding ? findingLocationLabel(strongestFinding) : null,
      finding_id: strongestFinding?.id ?? null,
    },
    {
      id: createActivityKey("trace", [agent.name, "verification", strongestFinding?.id ?? agent.updated_at]),
      kind: "verification",
      title:
        verificationStatus === "failed"
          ? "Verification did not close"
          : verificationStatus === "completed"
            ? "Verified score impact"
            : agent.status === "running"
              ? "Verification running"
              : "Verification queued",
      detail:
        verificationStatus === "completed"
          ? strongestFinding
            ? `${verifiedFindings} finding${verifiedFindings === 1 ? "" : "s"} were individually verifier-reviewed and the strongest evidence stayed in scope.`
            : "Verifier closed the report without persisted findings."
          : verificationStatus === "failed"
            ? "Verification halted before the report could be closed with clean caveats."
            : agent.status === "running"
              ? "Verifier is checking the strongest finding, the score driver, and whether the evidence package is strong enough for handoff."
              : "Verification will begin after scanner evidence settles.",
      status: verificationStatus,
      timestamp: agent.updated_at,
      tool: "Verification",
      location: strongestFinding ? findingLocationLabel(strongestFinding) : null,
      finding_id: strongestFinding?.id ?? null,
    },
    {
      id: createActivityKey("trace", [agent.name, "patch_proposed", strongestFinding?.id ?? finalAt]),
      kind: "patch_proposed",
      title: "Confirmed remediation handoff",
      detail:
        strongestFinding
          ? patchSuggestionForFinding(strongestFinding)
          : "Remediation guidance will be confirmed after a reportable finding lands.",
      status:
        strongestFinding
          ? audit.status === "failed"
            ? "failed"
            : "completed"
          : agent.status === "running"
            ? "active"
            : agent.status === "failed"
              ? "failed"
              : "pending",
      timestamp: strongestFinding?.created_at ?? finalAt,
      tool: "Patch handoff",
      location: strongestFinding ? findingLocationLabel(strongestFinding) : null,
      finding_id: strongestFinding?.id ?? null,
    },
    {
      id: createActivityKey("trace", [agent.name, "note", audit.status, replayReadyCount, finalAt]),
      kind: "note",
      title:
        audit.status === "completed"
          ? "Locked final report"
          : audit.status === "failed"
            ? "Closed with follow-up required"
            : agent.status === "running"
              ? "Final report still open"
              : "Awaiting closeout",
      detail:
        audit.status === "completed"
          ? `Final TrustScore ${audit.score}/100 with ${replayReadyCount} replay-ready artifact${replayReadyCount === 1 ? "" : "s"} staged for remediation handoff.`
          : audit.status === "failed"
            ? "The report closed early, so the final score and findings still need manual follow-up."
            : "Verifier is still deciding whether the report can be locked for handoff.",
      status:
        audit.status === "completed"
          ? "completed"
          : audit.status === "failed"
            ? "failed"
            : agent.status === "running"
              ? "active"
              : "pending",
      timestamp: finalAt,
      tool: "Final report",
      location: `TrustScore ${audit.score}/100, Coverage ${audit.coverage}/100`,
    },
  ];

  return {
    agentName: agent.name,
    headline: "Verifier operational trace",
    description:
      verifierSource === "placeholder"
        ? "Backend trace packets are not available yet, so this panel synthesizes safe verification milestones from findings, score state, and final report handoff."
        : "This trace is synthesized from safe verification signals such as evidence review, score lock, and replay handoff without exposing raw reasoning.",
    source: verifierSource,
    updatedAt: latestTraceTimestamp(steps, agent.updated_at),
    steps,
  };
}

export function canShowAgentTrace(agent: AgentStatus) {
  const normalizedName = normalizeAgentName(agent.name);
  return Boolean(agent.trace?.steps?.length) || ["planner", "scanner", "verifier"].includes(normalizedName);
}

export function buildAgentOperationalTrace(
  agent: AgentStatus,
  audit: Audit,
  events: AuditActivityEvent[],
): AgentOperationalTrace | null {
  if (agent.trace?.steps?.length) {
    return normalizeBackendTrace(agent, agent.trace);
  }

  const normalizedName = normalizeAgentName(agent.name);

  if (normalizedName === "planner") {
    return buildPlannerTrace(agent, audit, events);
  }

  if (normalizedName === "scanner") {
    return buildScannerTrace(agent, audit, events);
  }

  if (normalizedName === "verifier") {
    return buildVerifierTrace(agent, audit, events);
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
        label: "Scope set",
        detail: "Planner sets what the scanner and reviewer should chase first.",
        status: agent.status === "completed" ? "complete" : agent.status === "running" ? "active" : agent.status === "failed" ? "failed" : "pending",
        tone: agent.status === "failed" ? "danger" : agent.status === "completed" ? "success" : "info",
        timestamp: agent.updated_at,
      },
      {
        id: "handoff",
        label: "Scan ready",
        detail: "Scope is ready for discovery and fix planning.",
        status: agent.status === "completed" ? "complete" : agent.status === "failed" ? "failed" : "pending",
        tone: agent.status === "failed" ? "danger" : agent.status === "completed" ? "success" : "neutral",
        timestamp: agent.status === "completed" ? agent.updated_at : null,
      },
    ];

    return {
      roleLabel: "Planner",
      missionLabel: "Maps the repo and sets scan priority.",
      impactLabel: `${majorFindingCount(audit)} major issues downstream`,
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
        detail: "Scanner is walking config, runtime, and boundary code paths.",
        status: agent.status === "queued" ? "pending" : "complete",
        tone: agent.status === "queued" ? "neutral" : "danger",
        timestamp: agent.updated_at,
      },
      {
        id: "anchors",
        label: "Evidence attached",
        detail: findingsCount ? `${findingsCount} findings now carry file-level anchors.` : "No anchored findings yet.",
        status: findingsCount ? "complete" : agent.status === "running" ? "active" : "pending",
        tone: findingsCount ? "warning" : "info",
        timestamp: findingsCount ? audit.findings[audit.findings.length - 1]?.created_at ?? agent.updated_at : agent.updated_at,
      },
      {
        id: "handoff",
        label: "Review ready",
        detail: "Confirmed leads move into final review.",
        status: agent.status === "completed" ? "complete" : agent.status === "failed" ? "failed" : "pending",
        tone: agent.status === "failed" ? "danger" : agent.status === "completed" ? "success" : "neutral",
        timestamp: agent.status === "completed" ? agent.updated_at : null,
      },
    ];

    return {
      roleLabel: "Scanner",
      missionLabel: "Turns suspicious code into findings with evidence.",
      impactLabel: `${findingsCount} findings logged`,
      statusLabel: currentStageLabel(stages),
      isLive: agent.status === "running",
      stages,
    };
  }

  const verifier = latestAgent(audit, "verifier");
  const verifiedFindingCount = audit.findings.filter((finding) => finding.verification_state === "verified").length;
  const stages: StoryStage[] = [
    {
      id: "review",
      label: "Evidence review",
      detail: "Verifier checks whether the strongest findings hold up.",
      status: verifier?.status === "completed" ? "complete" : verifier?.status === "running" ? "active" : verifier?.status === "failed" ? "failed" : "pending",
      tone: verifier?.status === "failed" ? "danger" : verifier?.status === "completed" ? "success" : verifier?.status === "running" ? "info" : "neutral",
      timestamp: verifier?.updated_at ?? agent.updated_at,
    },
    {
      id: "score",
      label: "Score locked",
      detail: "Score changes are tied to reviewed evidence, not scan noise.",
      status: audit.status === "completed" ? "complete" : audit.status === "failed" ? "failed" : verifier?.status === "running" ? "active" : "pending",
      tone: audit.status === "failed" ? "danger" : audit.status === "completed" ? "success" : verifier?.status === "running" ? "info" : "neutral",
      timestamp: audit.status === "completed" || audit.status === "failed" ? audit.updated_at : verifier?.updated_at ?? null,
    },
    {
      id: "closure",
      label: audit.status === "failed" ? "Review blocked" : "Review finished",
      detail:
        audit.status === "completed"
          ? verifiedFindingCount > 0
            ? `Review closed with ${verifiedFindingCount} individually reviewed finding${verifiedFindingCount === 1 ? "" : "s"}.`
            : "Review closed, but no finding was individually reviewed."
          : audit.status === "failed"
            ? "The report closed early and needs manual follow-up."
            : "Waiting for the report to close.",
      status: audit.status === "completed" ? "complete" : audit.status === "failed" ? "failed" : "pending",
      tone: audit.status === "completed" ? "success" : audit.status === "failed" ? "danger" : "neutral",
      timestamp: audit.status === "completed" || audit.status === "failed" ? audit.updated_at : null,
    },
  ];

  return {
    roleLabel: "Verifier",
    missionLabel: "Reviews the strongest findings and closes the report with clear caveats.",
    impactLabel: audit.status === "completed" ? "Report closed" : `${majorFindingCount(audit)} major issues under review`,
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
      label: "Findings found",
      detail: audit.findings.length
        ? `${audit.findings.length} findings surfaced in this audit.`
        : "Scanner has not surfaced findings yet.",
      status: audit.findings.length ? "complete" : scanner?.status === "running" ? "active" : planner?.status === "completed" ? "pending" : "pending",
      tone: audit.findings.length ? "danger" : scanner?.status === "running" ? "info" : "neutral",
      timestamp: audit.findings[0]?.created_at ?? scanner?.updated_at ?? null,
    },
    {
      id: "confirm",
      label: "Evidence ready",
      detail:
        verifier?.status === "completed"
          ? verifiedFindingCount > 0
            ? `${verifiedFindingCount} finding${verifiedFindingCount === 1 ? "" : "s"} were individually reviewed.`
            : "Evidence was captured, but no finding was individually reviewed."
          : verifier?.status === "running"
            ? "Review is confirming impact and filtering noise."
            : audit.findings.length
              ? "Evidence anchors are in place and waiting for review."
              : "No evidence package yet.",
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
      label: "Fixes drafted",
      detail:
        audit.findings.length
          ? `${audit.findings.length} fix paths were drafted from the finding patterns.`
          : "Fix planning begins once a finding lands.",
      status: audit.status === "failed" ? "failed" : audit.findings.length ? "complete" : "pending",
      tone: audit.status === "failed" ? "danger" : audit.findings.length ? "warning" : "neutral",
      timestamp: audit.findings[0]?.created_at ?? null,
    },
    {
      id: "verify",
      label: audit.status === "failed" ? "Review blocked" : "Review complete",
      detail:
        audit.status === "completed"
          ? verifiedFindingCount > 0
            ? `${verifiedFindingCount} finding${verifiedFindingCount === 1 ? "" : "s"} were reviewed and ${unresolvedFindingCount} remained unresolved or manual-review only.`
            : "The report is closed, but remaining findings still need finding-level review."
          : audit.status === "failed"
            ? "Review closed early and needs manual follow-up."
            : verifier?.status === "running"
              ? "Review is active and the audit is still moving."
              : "Waiting for final review.",
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
      ? "Audit complete with clear review state"
      : majorFindings
        ? `${majorFindings} major issue${majorFindings === 1 ? "" : "s"} under review`
        : audit.findings.length
          ? "Findings are being reviewed"
          : "Scanning repo";
    const detail =
      audit.status === "completed"
        ? checkCount || supportedAreaCount
          ? `${checkCount} checks ran across ${supportedAreaCount} supported area${supportedAreaCount === 1 ? "" : "s"}. ${
              unresolvedAreaCount > 0
                ? `${unresolvedAreaCount} area${unresolvedAreaCount === 1 ? "" : "s"} remained partial or out of scope.`
                : verifiedFindingCount > 0
                  ? "The report is ready for remediation handoff."
                  : "The report closed without finding-level review."
            }`
          : "The report is ready to review."
        : verifier?.status === "running"
          ? "The verifier is reviewing the strongest findings now."
          : scanner?.status === "running"
          ? "The scanner is still turning suspicious code into evidence."
          : "Waiting for the next update.";

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
          label: isHighImpact ? "Major issue found" : "Issue found",
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
              ? "Score dropped"
              : update.delta !== null && update.delta > 0
                ? "Score improved"
                : "Score unchanged",
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
          label: audit.status === "failed" ? "Report ended early" : "Report ready",
          detail:
            event.payload.message ??
            (audit.status === "failed"
              ? "Review stalled before the report could close cleanly."
              : "The report closed and is ready to share."),
          timestamp: event.occurredAt,
          tone: completionTone,
          highlight: isRecentTimestamp(event.occurredAt),
          lane: "verifier",
        };
      }

      return {
        id: event.key,
        label: `${event.payload.name} updated`,
        detail: event.payload.message || `${event.payload.name} posted a new update.`,
        timestamp: event.occurredAt,
        tone: toneFromAgentState(event.payload.status),
        highlight: isRecentTimestamp(event.occurredAt),
        lane: event.payload.name,
      };
    });

  const transportMoment: StoryMoment = {
    id: `transport:${transportLabel}:${audit.updated_at}`,
    label: "Heartbeat",
    detail: `${transportLabel} is keeping the room current.`,
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
          ? "Current score"
          : event.delta !== null && event.delta < 0
            ? "Risk increased"
            : event.delta !== null && event.delta > 0
              ? "Risk reduced"
              : "Score unchanged",
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
      label: completionEvent.status === "failed" ? "Review blocked" : "Score locked",
      detail:
        completionEvent.message ??
        (completionEvent.status === "failed"
          ? "The report ended before a clean review closeout."
          : "The report closed and the score is ready for handoff."),
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
