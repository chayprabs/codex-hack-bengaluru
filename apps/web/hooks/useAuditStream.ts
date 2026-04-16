"use client";

import { useEffect, useRef, useState } from "react";

import { getAuditStreamUrl } from "@/lib/api";
import type {
  AgentStatusEvent,
  Audit,
  AuditCompleteEvent,
  AuditStreamConnectionState,
  FindingEvent,
  ScoreUpdateEvent,
} from "@/lib/types";

type UseAuditStreamOptions = {
  auditId: string;
  initialAudit: Audit;
  reconnectDelayMs?: number;
};

type UseAuditStreamResult = {
  audit: Audit;
  latestScoreUpdate: ScoreUpdateEvent | null;
  completionEvent: AuditCompleteEvent | null;
  connectionState: AuditStreamConnectionState;
  streamError: string | null;
};

const DEFAULT_RECONNECT_DELAY_MS = 3_000;

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

function mergeAgentStatus(audit: Audit, event: AgentStatusEvent) {
  const nextAgent = {
    name: event.name,
    status: event.status,
    message: event.message,
    updated_at: event.updated_at,
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

function mergeFinding(audit: Audit, event: FindingEvent) {
  if (audit.findings.some((finding) => finding.id === event.id)) {
    return {
      ...audit,
      updated_at: keepLatestTimestamp(audit.updated_at, event.created_at),
    };
  }

  return {
    ...audit,
    findings: [
      ...audit.findings,
      {
        id: event.id,
        severity: event.severity,
        title: event.title,
        summary: event.summary,
        file_path: event.file_path,
        line: event.line,
        created_at: event.created_at,
      },
    ],
    updated_at: keepLatestTimestamp(audit.updated_at, event.created_at),
  };
}

function mergeScoreUpdate(audit: Audit, event: ScoreUpdateEvent) {
  return {
    ...audit,
    score: event.score,
    updated_at: keepLatestTimestamp(audit.updated_at, event.updated_at),
  };
}

function mergeAuditComplete(audit: Audit, event: AuditCompleteEvent) {
  return {
    ...audit,
    status: event.status,
    repo_url: event.repo_url || audit.repo_url,
    score: event.score,
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
    updated_at: audit.updated_at,
    finding_count: audit.findings.length,
    message: null,
  };
}

export function useAuditStream({
  auditId,
  initialAudit,
  reconnectDelayMs = DEFAULT_RECONNECT_DELAY_MS,
}: UseAuditStreamOptions): UseAuditStreamResult {
  const [audit, setAudit] = useState(initialAudit);
  const [latestScoreUpdate, setLatestScoreUpdate] = useState<ScoreUpdateEvent | null>(null);
  const [completionEvent, setCompletionEvent] = useState<AuditCompleteEvent | null>(() => toCompletionEvent(initialAudit));
  const [connectionState, setConnectionState] = useState<AuditStreamConnectionState>(
    initialAudit.status === "completed" || initialAudit.status === "failed" ? "closed" : "connecting",
  );
  const [streamError, setStreamError] = useState<string | null>(null);

  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setAudit(initialAudit);
    setLatestScoreUpdate(null);
    setCompletionEvent(toCompletionEvent(initialAudit));
    setStreamError(null);
    setConnectionState(initialAudit.status === "completed" || initialAudit.status === "failed" ? "closed" : "connecting");
  }, [initialAudit]);

  useEffect(() => {
    if (initialAudit.status === "completed" || initialAudit.status === "failed") {
      return;
    }

    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      setConnectionState("closed");
      setStreamError("Live updates are not supported in this browser.");
      return;
    }

    let disposed = false;
    let source: EventSource | null = null;

    const clearReconnectTimer = () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    const closeSource = () => {
      if (source) {
        source.close();
        source = null;
      }
    };

    const scheduleReconnect = () => {
      if (disposed) {
        return;
      }

      clearReconnectTimer();
      setConnectionState("reconnecting");

      reconnectTimerRef.current = setTimeout(() => {
        connect();
      }, reconnectDelayMs);
    };

    const connect = () => {
      if (disposed) {
        return;
      }

      clearReconnectTimer();
      closeSource();
      setConnectionState((current) => (current === "live" ? "reconnecting" : "connecting"));

      const nextSource = new EventSource(getAuditStreamUrl(auditId));
      source = nextSource;

      nextSource.onopen = () => {
        if (disposed) {
          return;
        }

        setConnectionState("live");
        setStreamError(null);
      };

      nextSource.addEventListener("agent_status", (event) => {
        const payload = parseEventData<AgentStatusEvent>(event as MessageEvent<string>);
        if (!payload || payload.audit_id !== auditId) {
          return;
        }

        setAudit((current) => mergeAgentStatus(current, payload));
      });

      nextSource.addEventListener("finding", (event) => {
        const payload = parseEventData<FindingEvent>(event as MessageEvent<string>);
        if (!payload || payload.audit_id !== auditId) {
          return;
        }

        setAudit((current) => mergeFinding(current, payload));
      });

      nextSource.addEventListener("score_update", (event) => {
        const payload = parseEventData<ScoreUpdateEvent>(event as MessageEvent<string>);
        if (!payload || payload.audit_id !== auditId) {
          return;
        }

        setLatestScoreUpdate(payload);
        setAudit((current) => mergeScoreUpdate(current, payload));
      });

      nextSource.addEventListener("audit_complete", (event) => {
        const payload = parseEventData<AuditCompleteEvent>(event as MessageEvent<string>);
        if (!payload || payload.audit_id !== auditId) {
          return;
        }

        setCompletionEvent(payload);
        setAudit((current) => mergeAuditComplete(current, payload));
        setConnectionState("closed");
        setStreamError(null);
        clearReconnectTimer();
        closeSource();
      });

      nextSource.onerror = () => {
        if (disposed) {
          return;
        }

        closeSource();
        setStreamError("Live updates disconnected. Reconnecting to the audit stream.");
        scheduleReconnect();
      };
    };

    connect();

    return () => {
      disposed = true;
      clearReconnectTimer();
      closeSource();
    };
  }, [auditId, initialAudit.status, reconnectDelayMs]);

  return {
    audit,
    latestScoreUpdate,
    completionEvent,
    connectionState,
    streamError,
  };
}
