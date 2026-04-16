"use client";

import { useEffect, useState } from "react";

import {
  apiClient,
  getApiErrorMessage,
  getApiErrorStatus,
  type Audit,
} from "@/lib/api";
import { isTerminalAuditStatus } from "@/lib/utils";

type AuditTransport = "connecting" | "polling" | "sse";
type LoadStatus = "loading" | "ready" | "error";

type AuditMonitorState = {
  audit: Audit | null;
  status: LoadStatus;
  error: string | null;
  errorStatus: number | null;
  transport: AuditTransport;
  isRefreshing: boolean;
  lastSyncedAt: string | null;
};

const POLL_INTERVAL_MS = 4_000;
const RETRY_INTERVAL_MS = 6_000;
const SSE_FALLBACK_TIMEOUT_MS = 2_500;

function parseAuditEventPayload(payload: string) {
  try {
    const parsed = JSON.parse(payload) as Audit | { audit?: Audit };

    if ("audit" in parsed && parsed.audit) {
      return parsed.audit;
    }

    if ("id" in parsed && "repo_url" in parsed) {
      return parsed as Audit;
    }
  } catch {
    return null;
  }

  return null;
}

export function useAuditMonitor(auditId: string) {
  const [reloadToken, setReloadToken] = useState(0);
  const [state, setState] = useState<AuditMonitorState>({
    audit: null,
    status: "loading",
    error: null,
    errorStatus: null,
    transport: "polling",
    isRefreshing: false,
    lastSyncedAt: null,
  });

  useEffect(() => {
    let disposed = false;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;
    let sseTimer: ReturnType<typeof setTimeout> | null = null;
    let source: EventSource | null = null;
    let receivedSsePayload = false;

    const applyAudit = (audit: Audit, transport?: AuditTransport) => {
      setState((current) => ({
        ...current,
        audit,
        status: "ready",
        error: null,
        errorStatus: null,
        transport: transport ?? current.transport,
        isRefreshing: false,
        lastSyncedAt: new Date().toISOString(),
      }));
    };

    const applyError = (error: unknown) => {
      setState((current) => ({
        ...current,
        status: current.audit ? "ready" : "error",
        error: getApiErrorMessage(error),
        errorStatus: getApiErrorStatus(error),
        isRefreshing: false,
      }));
    };

    const clearTimers = () => {
      if (pollTimer) {
        clearTimeout(pollTimer);
        pollTimer = null;
      }

      if (sseTimer) {
        clearTimeout(sseTimer);
        sseTimer = null;
      }
    };

    const closeSource = () => {
      if (source) {
        source.close();
        source = null;
      }

      if (sseTimer) {
        clearTimeout(sseTimer);
        sseTimer = null;
      }
    };

    const schedulePoll = (delay: number) => {
      if (disposed) {
        return;
      }

      if (pollTimer) {
        clearTimeout(pollTimer);
      }

      pollTimer = setTimeout(() => {
        void fetchAudit(true);
      }, delay);
    };

    const startSse = () => {
      if (disposed || source || typeof window === "undefined" || !("EventSource" in window)) {
        setState((current) => ({ ...current, transport: "polling" }));
        schedulePoll(POLL_INTERVAL_MS);
        return;
      }

      receivedSsePayload = false;
      setState((current) => ({ ...current, transport: "connecting" }));

      source = new EventSource(apiClient.getAuditStreamUrl(auditId));

      source.onmessage = (event) => {
        receivedSsePayload = true;
        const audit = parseAuditEventPayload(event.data);

        if (!audit) {
          return;
        }

        applyAudit(audit, "sse");

        if (isTerminalAuditStatus(audit.status)) {
          closeSource();
        }
      };

      source.onerror = () => {
        closeSource();
        setState((current) => ({ ...current, transport: "polling" }));
        schedulePoll(POLL_INTERVAL_MS);
      };

      sseTimer = setTimeout(() => {
        if (disposed || receivedSsePayload) {
          return;
        }

        closeSource();
        setState((current) => ({ ...current, transport: "polling" }));
        schedulePoll(POLL_INTERVAL_MS);
      }, SSE_FALLBACK_TIMEOUT_MS);
    };

    const fetchAudit = async (background: boolean) => {
      if (disposed) {
        return;
      }

      setState((current) => ({
        ...current,
        status: current.audit ? current.status : "loading",
        isRefreshing: background || Boolean(current.audit),
        error: background ? current.error : null,
        errorStatus: background ? current.errorStatus : null,
      }));

      try {
        const audit = await apiClient.getAudit(auditId);

        if (disposed) {
          return;
        }

        applyAudit(audit, source ? "sse" : "polling");

        if (isTerminalAuditStatus(audit.status)) {
          closeSource();
          return;
        }

        if (!source) {
          startSse();
        }

        if (!source) {
          schedulePoll(POLL_INTERVAL_MS);
        }
      } catch (error) {
        if (disposed) {
          return;
        }

        applyError(error);
        closeSource();
        setState((current) => ({ ...current, transport: "polling" }));
        schedulePoll(RETRY_INTERVAL_MS);
      }
    };

    void fetchAudit(false);

    return () => {
      disposed = true;
      closeSource();
      clearTimers();
    };
  }, [auditId, reloadToken]);

  return {
    ...state,
    refresh: () => setReloadToken((current) => current + 1),
  };
}
