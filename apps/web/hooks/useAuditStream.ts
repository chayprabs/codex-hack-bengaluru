"use client";

import { useEffect, useRef, useState } from "react";

import { getApiErrorMessage, getAudit, getAuditStreamUrl } from "@/lib/api";
import {
  appendAuditActivity,
  appendScoreMoment,
  buildActivityEvent,
  buildSeededAuditActivity,
  type AuditActivityEvent,
} from "@/lib/auditStory";
import type {
  AgentStatus,
  AgentTrace,
  AgentStatusEvent,
  AgentTraceEvent,
  Audit,
  AuditCompleteEvent,
  AuditStreamConnectionState,
  FindingEvent,
  ReplayRecord,
  ScoreUpdateEvent,
} from "@/lib/types";

type UseAuditStreamOptions = {
  auditId: string;
  initialAudit: Audit;
  reconnectDelayMs?: number;
  pollIntervalMs?: number;
};

type UseAuditStreamResult = {
  audit: Audit;
  latestScoreUpdate: ScoreUpdateEvent | null;
  scoreHistory: ScoreUpdateEvent[];
  activity: AuditActivityEvent[];
  completionEvent: AuditCompleteEvent | null;
  connectionState: AuditStreamConnectionState;
  streamError: string | null;
};

const DEFAULT_RECONNECT_DELAY_MS = 3_000;
const DEFAULT_POLL_INTERVAL_MS = 5_000;

function timestampValue(value: string | null | undefined) {
  if (!value) {
    return 0;
  }

  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function keepLatestTimestamp(current: string, incoming: string | null | undefined) {
  if (!incoming) {
    return current;
  }

  return timestampValue(incoming) >= timestampValue(current) ? incoming : current;
}

function isTerminalStatus(status: Audit["status"]) {
  return status === "completed" || status === "failed";
}

function keepNewestAudit(current: Audit, incoming: Audit) {
  return timestampValue(incoming.updated_at) >= timestampValue(current.updated_at) ? incoming : current;
}

function keepStringList(current: string[], incoming: unknown) {
  if (!Array.isArray(incoming)) {
    return current;
  }

  const nextValues = incoming
    .map((item: unknown) => (typeof item === "string" ? item.trim() : ""))
    .filter(Boolean);

  return nextValues.length > 0 ? nextValues : [];
}

function keepNumber(current: number, incoming: unknown) {
  return typeof incoming === "number" && Number.isFinite(incoming) ? incoming : current;
}

function keepString(current: string, incoming: unknown) {
  return typeof incoming === "string" && incoming.trim() ? incoming : current;
}

function keepReplayRecords(current: ReplayRecord[], incoming: unknown): ReplayRecord[] {
  if (!Array.isArray(incoming)) {
    return current;
  }

  return incoming.map((record: unknown): ReplayRecord => {
    const candidate =
      typeof record === "object" && record !== null
        ? (record as Partial<ReplayRecord> & Record<string, unknown>)
        : {};

    return {
      id: typeof candidate.id === "string" ? candidate.id : "",
      finding_id: typeof candidate.finding_id === "string" ? candidate.finding_id : null,
      title: typeof candidate.title === "string" && candidate.title.trim() ? candidate.title : "Replay record",
      finding_type:
        typeof candidate.finding_type === "string" && candidate.finding_type.trim() ? candidate.finding_type : "finding",
      file_targets: Array.isArray(candidate.file_targets)
        ? candidate.file_targets.filter((item: unknown): item is string => typeof item === "string" && item.trim().length > 0)
        : [],
      confidence: candidate.confidence === "high" || candidate.confidence === "medium" ? candidate.confidence : "low",
      proof_type:
        candidate.proof_type === "runtime_check" ||
        candidate.proof_type === "exploit_succeeded" ||
        candidate.proof_type === "manual_review_recommendation"
          ? candidate.proof_type
          : "deterministic_pattern",
      verification_state:
        candidate.verification_state === "verified" ||
        candidate.verification_state === "in_review" ||
        candidate.verification_state === "manual_review" ||
        candidate.verification_state === "failed"
          ? candidate.verification_state
          : "unverified",
      proof_summary:
        typeof candidate.proof_summary === "string" && candidate.proof_summary.trim()
          ? candidate.proof_summary
          : "Proof summary pending.",
      verification_summary:
        typeof candidate.verification_summary === "string" && candidate.verification_summary.trim()
          ? candidate.verification_summary
          : "Verification summary pending.",
      suggested_regression_test:
        typeof candidate.suggested_regression_test === "string" && candidate.suggested_regression_test.trim()
          ? candidate.suggested_regression_test
          : "Add a focused regression before trusting the remediation.",
      generated_artifact_path:
        typeof candidate.generated_artifact_path === "string" && candidate.generated_artifact_path.trim()
          ? candidate.generated_artifact_path
          : null,
      readiness: candidate.readiness === "regression_ready" ? "regression_ready" : "needs_manual_followup",
    };
  });
}

function mergeSnapshotActivity(current: AuditActivityEvent[], snapshot: Audit) {
  return buildSeededAuditActivity(snapshot).reduce(
    (events, seededEvent) => appendAuditActivity(events, seededEvent),
    current,
  );
}

function mergeAgentStatus(audit: Audit, event: AgentStatusEvent): Audit {
  const existingAgent = audit.agents.find((agent) => agent.name === event.name);
  const nextAgent: AgentStatus = {
    name: event.name,
    status: event.status,
    message: event.message,
    updated_at: event.updated_at,
    trace: event.trace ?? existingAgent?.trace ?? null,
  };

  const existingIndex = audit.agents.findIndex((agent) => agent.name === event.name);
  const nextAgents = [...audit.agents];

  if (existingIndex >= 0) {
    nextAgents[existingIndex] = nextAgent;
  } else {
    nextAgents.push(nextAgent);
  }

  return {
    ...audit,
    agents: nextAgents,
    updated_at: keepLatestTimestamp(audit.updated_at, event.updated_at),
  };
}

function mergeAgentTrace(audit: Audit, event: AgentTraceEvent): Audit {
  const existingIndex = audit.agents.findIndex((agent) => agent.name === event.agent_name);
  const nextTrace: AgentTrace = {
    agent_name: event.agent_name,
    source: event.source,
    updated_at: event.updated_at,
    headline: event.headline ?? null,
    summary: event.summary ?? null,
    steps: event.steps,
  };

  if (existingIndex < 0) {
    const nextAgent: AgentStatus = {
      name: event.agent_name,
      status: "running",
      message: "Operational trace received.",
      updated_at: event.updated_at,
      trace: nextTrace,
    };

    return {
      ...audit,
      agents: [...audit.agents, nextAgent],
      updated_at: keepLatestTimestamp(audit.updated_at, event.updated_at),
    };
  }

  const nextAgents = [...audit.agents];
  const currentAgent = nextAgents[existingIndex];
  nextAgents[existingIndex] = {
    ...currentAgent,
    updated_at: keepLatestTimestamp(currentAgent.updated_at, event.updated_at),
    trace: nextTrace,
  };

  return {
    ...audit,
    agents: nextAgents,
    updated_at: keepLatestTimestamp(audit.updated_at, event.updated_at),
  };
}

function mergeFinding(audit: Audit, event: FindingEvent) {
  if (audit.findings.some((finding) => finding.id === event.id)) {
    return {
      ...audit,
      updated_at: keepLatestTimestamp(audit.updated_at, event.created_at),
    };
  }

  const technicalSummary =
    typeof event.technical_summary === "string" && event.technical_summary.trim()
      ? event.technical_summary
      : typeof event.summary === "string" && event.summary.trim()
        ? event.summary
        : event.impact_summary ?? event.title;

  return {
    ...audit,
    findings: [
      ...audit.findings,
      {
        id: event.id,
        severity: event.severity,
        title: event.title,
        summary: technicalSummary,
        technical_summary: technicalSummary,
        agent_name: event.agent_name ?? null,
        check_name: event.check_name ?? null,
        files: event.files ?? [],
        line_hints: event.line_hints ?? [],
        impact_summary: event.impact_summary ?? event.title,
        evidence_snippet: event.evidence_snippet ?? null,
        confidence: event.confidence ?? "high",
        proof_type: event.proof_type ?? "deterministic_pattern",
        suggested_patch: event.suggested_patch ?? null,
        verification_state: event.verification_state ?? "unverified",
        created_at: event.created_at,
      },
    ],
    updated_at: keepLatestTimestamp(audit.updated_at, event.created_at),
  };
}

function mergeScoreUpdate(audit: Audit, event: ScoreUpdateEvent): Audit {
  const nextCoverage = keepNumber(audit.coverage, event.coverage);

  return {
    ...audit,
    score: event.score,
    coverage: nextCoverage,
    coverage_percent: keepNumber(nextCoverage, event.coverage_percent),
    coverage_band: event.coverage_band,
    coverage_summary: keepString(audit.coverage_summary, event.coverage_summary),
    confidence_limited: event.confidence_limited,
    supported_areas: keepStringList(audit.supported_areas, event.supported_areas),
    partially_supported_areas: keepStringList(audit.partially_supported_areas, event.partially_supported_areas),
    unsupported_areas: keepStringList(audit.unsupported_areas, event.unsupported_areas),
    needs_manual_review_areas: keepStringList(audit.needs_manual_review_areas, event.needs_manual_review_areas),
    unsupported_technologies: keepStringList(audit.unsupported_technologies, event.unsupported_technologies),
    scanned_files_count: keepNumber(audit.scanned_files_count, event.scanned_files_count),
    skipped_files_count: keepNumber(audit.skipped_files_count, event.skipped_files_count),
    frameworks_detected: keepStringList(audit.frameworks_detected, event.frameworks_detected),
    checks_run: keepStringList(audit.checks_run, event.checks_run),
    checks_skipped: keepStringList(audit.checks_skipped, event.checks_skipped),
    updated_at: keepLatestTimestamp(audit.updated_at, event.updated_at),
  };
}

function mergeAuditComplete(audit: Audit, event: AuditCompleteEvent): Audit {
  const nextCoverage = keepNumber(audit.coverage, event.coverage);

  return {
    ...audit,
    status: event.status,
    repo_url: event.repo_url || audit.repo_url,
    score: event.score,
    coverage: nextCoverage,
    coverage_percent: keepNumber(nextCoverage, event.coverage_percent),
    coverage_band: event.coverage_band,
    coverage_summary: keepString(audit.coverage_summary, event.coverage_summary),
    confidence_limited: event.confidence_limited,
    supported_areas: keepStringList(audit.supported_areas, event.supported_areas),
    partially_supported_areas: keepStringList(audit.partially_supported_areas, event.partially_supported_areas),
    unsupported_areas: keepStringList(audit.unsupported_areas, event.unsupported_areas),
    needs_manual_review_areas: keepStringList(audit.needs_manual_review_areas, event.needs_manual_review_areas),
    unsupported_technologies: keepStringList(audit.unsupported_technologies, event.unsupported_technologies),
    scanned_files_count: keepNumber(audit.scanned_files_count, event.scanned_files_count),
    skipped_files_count: keepNumber(audit.skipped_files_count, event.skipped_files_count),
    frameworks_detected: keepStringList(audit.frameworks_detected, event.frameworks_detected),
    checks_run: keepStringList(audit.checks_run, event.checks_run),
    checks_skipped: keepStringList(audit.checks_skipped, event.checks_skipped),
    replay_records: keepReplayRecords(audit.replay_records, event.replay_records),
    completion_message: event.message ?? null,
    updated_at: keepLatestTimestamp(audit.updated_at, event.updated_at),
  };
}

function parseEventData<T>(event: MessageEvent<string>) {
  try {
    return JSON.parse(event.data) as T;
  } catch {
    return null;
  }
}

function toCompletionEvent(audit: Audit): AuditCompleteEvent | null {
  if (audit.status !== "completed" && audit.status !== "failed") {
    return null;
  }

  return {
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
  };
}

export function useAuditStream({
  auditId,
  initialAudit,
  reconnectDelayMs = DEFAULT_RECONNECT_DELAY_MS,
  pollIntervalMs = DEFAULT_POLL_INTERVAL_MS,
}: UseAuditStreamOptions): UseAuditStreamResult {
  const [audit, setAudit] = useState(initialAudit);
  const [latestScoreUpdate, setLatestScoreUpdate] = useState<ScoreUpdateEvent | null>(null);
  const [scoreHistory, setScoreHistory] = useState<ScoreUpdateEvent[]>([]);
  const [activity, setActivity] = useState<AuditActivityEvent[]>(() => buildSeededAuditActivity(initialAudit));
  const [completionEvent, setCompletionEvent] = useState<AuditCompleteEvent | null>(() => toCompletionEvent(initialAudit));
  const [connectionState, setConnectionState] = useState<AuditStreamConnectionState>(
    isTerminalStatus(initialAudit.status) ? "closed" : "connecting",
  );
  const [streamError, setStreamError] = useState<string | null>(null);

  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const auditRef = useRef(initialAudit);

  useEffect(() => {
    auditRef.current = initialAudit;
    setAudit(initialAudit);
    setLatestScoreUpdate(null);
    setScoreHistory([]);
    setActivity(buildSeededAuditActivity(initialAudit));
    setCompletionEvent(toCompletionEvent(initialAudit));
    setStreamError(null);
    setConnectionState(isTerminalStatus(initialAudit.status) ? "closed" : "connecting");
  }, [initialAudit]);

  useEffect(() => {
    if (isTerminalStatus(initialAudit.status)) {
      return;
    }

    let disposed = false;
    let source: EventSource | null = null;
    const canUseEventSource = typeof window !== "undefined" && typeof EventSource !== "undefined";

    const clearReconnectTimer = () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    const clearPollTimer = () => {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };

    const closeSource = () => {
      if (source) {
        source.close();
        source = null;
      }
    };

    const schedulePoll = (delay = pollIntervalMs) => {
      if (disposed) {
        return;
      }

      clearPollTimer();
      pollTimerRef.current = setTimeout(() => {
        void pollAudit();
      }, delay);
    };

    const scheduleReconnect = () => {
      if (disposed || !canUseEventSource) {
        return;
      }

      clearReconnectTimer();
      setConnectionState("reconnecting");

      reconnectTimerRef.current = setTimeout(() => {
        connect();
      }, reconnectDelayMs);
    };

    const applySnapshot = (snapshot: Audit) => {
      const previousAudit = auditRef.current;
      const nextAudit = keepNewestAudit(previousAudit, snapshot);

      auditRef.current = nextAudit;
      setAudit(nextAudit);
      setActivity((current) => mergeSnapshotActivity(current, nextAudit));

      const scoreOrCoverageChanged =
        nextAudit.score !== previousAudit.score ||
        nextAudit.coverage !== previousAudit.coverage ||
        nextAudit.coverage_band !== previousAudit.coverage_band ||
        nextAudit.coverage_summary !== previousAudit.coverage_summary ||
        nextAudit.confidence_limited !== previousAudit.confidence_limited;

      if (scoreOrCoverageChanged) {
        const snapshotScoreEvent: ScoreUpdateEvent = {
          audit_id: nextAudit.id,
          score: nextAudit.score,
          previous_score: previousAudit.score,
          delta: nextAudit.score - previousAudit.score,
          coverage: nextAudit.coverage,
          coverage_percent: nextAudit.coverage_percent,
          previous_coverage: previousAudit.coverage,
          coverage_delta: nextAudit.coverage - previousAudit.coverage,
          coverage_band: nextAudit.coverage_band,
          coverage_summary: nextAudit.coverage_summary,
          confidence_limited: nextAudit.confidence_limited,
          supported_areas: nextAudit.supported_areas,
          partially_supported_areas: nextAudit.partially_supported_areas,
          unsupported_areas: nextAudit.unsupported_areas,
          needs_manual_review_areas: nextAudit.needs_manual_review_areas,
          unsupported_technologies: nextAudit.unsupported_technologies,
          scanned_files_count: nextAudit.scanned_files_count,
          skipped_files_count: nextAudit.skipped_files_count,
          frameworks_detected: nextAudit.frameworks_detected,
          checks_run: nextAudit.checks_run,
          checks_skipped: nextAudit.checks_skipped,
          reason: "Current audit score snapshot.",
          updated_at: nextAudit.updated_at,
        };

        setLatestScoreUpdate(snapshotScoreEvent);
        setScoreHistory((current) => appendScoreMoment(current, snapshotScoreEvent));
      }

      if (isTerminalStatus(nextAudit.status)) {
        const nextCompletionEvent = toCompletionEvent(nextAudit);
        setCompletionEvent(nextCompletionEvent);
        if (nextCompletionEvent) {
          setActivity((current) => appendAuditActivity(current, buildActivityEvent(nextCompletionEvent, "audit_complete")));
        }
        setConnectionState("closed");
        setStreamError(null);
        clearReconnectTimer();
        clearPollTimer();
        closeSource();
        return;
      }

      if (!source) {
        schedulePoll();
      }
    };

    const pollAudit = async () => {
      try {
        const snapshot = await getAudit(auditId);

        if (disposed) {
          return;
        }

        applySnapshot(snapshot);
      } catch (error) {
        if (disposed) {
          return;
        }

        setStreamError(getApiErrorMessage(error));
        setConnectionState((current) => (current === "reconnecting" ? current : "polling"));
        schedulePoll();
      }
    };

    const connect = () => {
      if (disposed || !canUseEventSource) {
        return;
      }

      clearReconnectTimer();
      closeSource();
      setConnectionState((current) => (current === "reconnecting" ? current : "connecting"));

      const nextSource = new EventSource(getAuditStreamUrl(auditId));
      source = nextSource;

      nextSource.onopen = () => {
        if (disposed) {
          return;
        }

        setConnectionState("live");
        setStreamError(null);
        clearPollTimer();
      };

      nextSource.addEventListener("agent_status", (event) => {
        const payload = parseEventData<AgentStatusEvent>(event as MessageEvent<string>);
        if (!payload || payload.audit_id !== auditId) {
          return;
        }

        setActivity((current) => appendAuditActivity(current, buildActivityEvent(payload, "agent_status")));
        setAudit((current) => {
          const nextAudit = mergeAgentStatus(current, payload);
          auditRef.current = nextAudit;
          return nextAudit;
        });
      });

      nextSource.addEventListener("finding", (event) => {
        const payload = parseEventData<FindingEvent>(event as MessageEvent<string>);
        if (!payload || payload.audit_id !== auditId) {
          return;
        }

        setActivity((current) => appendAuditActivity(current, buildActivityEvent(payload, "finding")));
        setAudit((current) => {
          const nextAudit = mergeFinding(current, payload);
          auditRef.current = nextAudit;
          return nextAudit;
        });
      });

      nextSource.addEventListener("agent_trace", (event) => {
        const payload = parseEventData<AgentTraceEvent>(event as MessageEvent<string>);
        if (!payload || payload.audit_id !== auditId) {
          return;
        }

        setAudit((current) => {
          const nextAudit = mergeAgentTrace(current, payload);
          auditRef.current = nextAudit;
          return nextAudit;
        });
      });

      nextSource.addEventListener("score_update", (event) => {
        const payload = parseEventData<ScoreUpdateEvent>(event as MessageEvent<string>);
        if (!payload || payload.audit_id !== auditId) {
          return;
        }

        setLatestScoreUpdate(payload);
        setScoreHistory((current) => appendScoreMoment(current, payload));
        setActivity((current) => appendAuditActivity(current, buildActivityEvent(payload, "score_update")));
        setAudit((current) => {
          const nextAudit = mergeScoreUpdate(current, payload);
          auditRef.current = nextAudit;
          return nextAudit;
        });
      });

      nextSource.addEventListener("audit_complete", (event) => {
        const payload = parseEventData<AuditCompleteEvent>(event as MessageEvent<string>);
        if (!payload || payload.audit_id !== auditId) {
          return;
        }

        setCompletionEvent(payload);
        setActivity((current) => appendAuditActivity(current, buildActivityEvent(payload, "audit_complete")));
        setAudit((current) => {
          const nextAudit = mergeAuditComplete(current, payload);
          auditRef.current = nextAudit;
          return nextAudit;
        });
        setConnectionState("closed");
        setStreamError(null);
        clearReconnectTimer();
        clearPollTimer();
        closeSource();
      });

      nextSource.onerror = () => {
        if (disposed) {
          return;
        }

        closeSource();
        setStreamError("Live updates disconnected. Refreshing the latest snapshot while the stream reconnects.");
        schedulePoll();
        scheduleReconnect();
      };
    };

    if (!canUseEventSource) {
      setConnectionState("polling");
      setStreamError("Live updates are unavailable in this browser. Refreshing the audit snapshot instead.");
      schedulePoll();
      return () => {
        disposed = true;
        clearReconnectTimer();
        clearPollTimer();
        closeSource();
      };
    }

    connect();
    schedulePoll(pollIntervalMs);

    return () => {
      disposed = true;
      clearReconnectTimer();
      clearPollTimer();
      closeSource();
    };
  }, [auditId, initialAudit.status, pollIntervalMs, reconnectDelayMs]);

  return {
    audit,
    latestScoreUpdate,
    scoreHistory,
    activity,
    completionEvent,
    connectionState,
    streamError,
  };
}
