import {
  DEFAULT_API_BASE_URL,
  DEFAULT_NETWORK_ERROR_MESSAGE,
  DEFAULT_REQUEST_ERROR_MESSAGE,
} from "@/lib/constants";
import type {
  Audit,
  AuditMode,
  CreateAuditRequest,
  DemoSetupResponse,
  Finding,
  HealthCheckResponse,
  ReplayRecord,
  WallEntry,
} from "@/lib/types";

export type {
  AgentStatusEvent,
  AgentState,
  AgentStatus,
  Audit,
  AuditCompleteEvent,
  AuditMode,
  AuditStreamConnectionState,
  AuditStreamEventName,
  AuditState,
  CreateAuditRequest,
  DatabaseHealth,
  DemoFindingPreview,
  DemoProfileSummary,
  DemoSetupResponse,
  FindingConfidence,
  Finding,
  FindingEvent,
  FindingProofType,
  FindingSeverity,
  FindingVerificationState,
  HealthCheckResponse,
  ReplayRecord,
  ReplayRecordReadiness,
  ScoreUpdateEvent,
  WallEntry,
} from "@/lib/types";

type ErrorPayload =
  | {
      detail?:
        | string
        | Array<{
            loc?: Array<string | number>;
            msg?: string;
            type?: string;
          }>;
      message?: string;
      [key: string]: unknown;
    }
  | string
  | null;

export class APIError extends Error {
  status: number | null;
  payload: ErrorPayload;
  isNetworkError: boolean;

  constructor(
    message: string,
    options: {
      status?: number | null;
      payload?: ErrorPayload;
      isNetworkError?: boolean;
    } = {},
  ) {
    super(message);
    this.name = "APIError";
    this.status = options.status ?? null;
    this.payload = options.payload ?? null;
    this.isNetworkError = options.isNetworkError ?? false;
  }
}

export function getApiBaseUrl() {
  const rawBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  return rawBaseUrl ? rawBaseUrl.replace(/\/+$/, "") : DEFAULT_API_BASE_URL;
}

export function buildApiUrl(path: string) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${getApiBaseUrl()}${normalizedPath}`;
}

function readMessageFromPayload(payload: ErrorPayload) {
  if (typeof payload === "string") {
    return payload;
  }

  if (Array.isArray(payload?.detail)) {
    const messages = payload.detail
      .map((item) => {
        if (!item || typeof item.msg !== "string") {
          return null;
        }

        const location =
          Array.isArray(item.loc) && item.loc.length > 0
            ? item.loc
                .filter((part) => part !== "body")
                .map(String)
                .join(".")
            : null;

        return location ? `${location}: ${item.msg}` : item.msg;
      })
      .filter((message): message is string => Boolean(message));

    if (messages.length > 0) {
      return messages.join(" ");
    }
  }

  if (payload?.detail && typeof payload.detail === "string") {
    return payload.detail;
  }

  if (payload?.message && typeof payload.message === "string") {
    return payload.message;
  }

  return null;
}

async function parseResponseBody(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return null;
  }

  const text = await response.text();

  if (!text) {
    return null;
  }

  const contentType = response.headers.get("content-type") ?? "";

  if (!contentType.includes("application/json")) {
    return text;
  }

  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;

  try {
    response = await fetch(buildApiUrl(path), {
      ...init,
      cache: "no-store",
      headers,
    });
  } catch (error) {
    throw new APIError(getApiErrorMessage(error) || DEFAULT_NETWORK_ERROR_MESSAGE, {
      isNetworkError: true,
    });
  }

  const payload = (await parseResponseBody(response)) as ErrorPayload;

  if (!response.ok) {
    throw new APIError(readMessageFromPayload(payload) || response.statusText || DEFAULT_REQUEST_ERROR_MESSAGE, {
      status: response.status,
      payload,
    });
  }

  return payload as T;
}

function normalizeLineHint(value: string | null | undefined) {
  if (!value) {
    return null;
  }

  const match = value.match(/\d+/);
  if (!match) {
    return null;
  }

  const parsed = Number.parseInt(match[0], 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeFinding(finding: Finding): Finding {
  const files = Array.isArray(finding.files) ? finding.files.filter(Boolean) : [];
  const lineHints = Array.isArray(finding.line_hints) ? finding.line_hints.filter(Boolean) : [];
  const technicalSummary =
    typeof finding.technical_summary === "string" && finding.technical_summary.trim()
      ? finding.technical_summary
      : typeof finding.summary === "string" && finding.summary.trim()
        ? finding.summary
        : typeof finding.impact_summary === "string" && finding.impact_summary.trim()
          ? finding.impact_summary
          : finding.title;
  const summary =
    typeof finding.summary === "string" && finding.summary.trim()
      ? finding.summary
      : technicalSummary;
  const filePath =
    typeof finding.file_path === "string" && finding.file_path.trim()
      ? finding.file_path
      : files[0] ?? null;
  const line =
    typeof finding.line === "number" && Number.isFinite(finding.line)
      ? finding.line
      : normalizeLineHint(lineHints[0]);

  return {
    ...finding,
    summary,
    file_path: filePath,
    line,
    agent_name: finding.agent_name ?? null,
    check_name: finding.check_name ?? null,
    files,
    line_hints: lineHints,
    technical_summary: technicalSummary,
    impact_summary: finding.impact_summary ?? summary,
    evidence_snippet: finding.evidence_snippet ?? null,
    suggested_patch: finding.suggested_patch ?? null,
    verification_state: finding.verification_state ?? "unverified",
  };
}

function normalizeReplayRecord(record: ReplayRecord): ReplayRecord {
  return {
    ...record,
    finding_id: record.finding_id ?? null,
    finding_type: typeof record.finding_type === "string" && record.finding_type.trim() ? record.finding_type : "finding",
    file_targets: Array.isArray(record.file_targets) ? record.file_targets.filter(Boolean) : [],
    confidence: record.confidence ?? "low",
    proof_type: record.proof_type ?? "deterministic_pattern",
    verification_state: record.verification_state ?? "unverified",
    proof_summary: typeof record.proof_summary === "string" && record.proof_summary.trim() ? record.proof_summary : record.title,
    verification_summary:
      typeof record.verification_summary === "string" && record.verification_summary.trim()
        ? record.verification_summary
        : "Verification summary pending.",
    suggested_regression_test:
      typeof record.suggested_regression_test === "string" && record.suggested_regression_test.trim()
        ? record.suggested_regression_test
        : "Add a focused regression before trusting the remediation.",
    generated_artifact_path: record.generated_artifact_path ?? null,
    readiness: record.readiness ?? "needs_manual_followup",
  };
}

function normalizeWallEntry(entry: WallEntry): WallEntry {
  return {
    ...entry,
    agent_name: entry.agent_name ?? null,
    check_name: entry.check_name ?? null,
    impact_summary: entry.impact_summary ?? entry.title,
    confidence: entry.confidence ?? "high",
    proof_type: entry.proof_type ?? "deterministic_pattern",
    verification_state: entry.verification_state ?? "unverified",
  };
}

function normalizeAudit(audit: Audit): Audit {
  return {
    ...audit,
    findings: Array.isArray(audit.findings) ? audit.findings.map(normalizeFinding) : [],
    supported_areas: Array.isArray(audit.supported_areas) ? audit.supported_areas.filter(Boolean) : [],
    partially_supported_areas: Array.isArray(audit.partially_supported_areas) ? audit.partially_supported_areas.filter(Boolean) : [],
    unsupported_areas: Array.isArray(audit.unsupported_areas) ? audit.unsupported_areas.filter(Boolean) : [],
    needs_manual_review_areas: Array.isArray(audit.needs_manual_review_areas) ? audit.needs_manual_review_areas.filter(Boolean) : [],
    unsupported_technologies: Array.isArray(audit.unsupported_technologies) ? audit.unsupported_technologies.filter(Boolean) : [],
    frameworks_detected: Array.isArray(audit.frameworks_detected) ? audit.frameworks_detected.filter(Boolean) : [],
    checks_run: Array.isArray(audit.checks_run) ? audit.checks_run.filter(Boolean) : [],
    checks_skipped: Array.isArray(audit.checks_skipped) ? audit.checks_skipped.filter(Boolean) : [],
    replay_records: Array.isArray(audit.replay_records) ? audit.replay_records.map(normalizeReplayRecord) : [],
  };
}

export function getApiErrorStatus(error: unknown) {
  return error instanceof APIError ? error.status : null;
}

export function getApiErrorMessage(error: unknown) {
  if (error instanceof APIError) {
    return error.message;
  }

  if (error instanceof TypeError) {
    return DEFAULT_NETWORK_ERROR_MESSAGE;
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return DEFAULT_REQUEST_ERROR_MESSAGE;
}

export function getHealth() {
  return request<HealthCheckResponse>("/health");
}

export function createAudit(repoUrl: string, auditMode: AuditMode = "fast") {
  const payload: CreateAuditRequest = { repo_url: repoUrl, audit_mode: auditMode };

  return request<Audit>("/audits", {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(normalizeAudit);
}

export function createDemoAudit(profileKey?: string) {
  const path = profileKey ? `/demo-audit?profile_key=${encodeURIComponent(profileKey)}` : "/demo-audit";

  return request<Audit>(path, {
    method: "POST",
  }).then(normalizeAudit);
}

export function getDemoSetup() {
  return request<DemoSetupResponse>("/demo-setup");
}

export function getAudit(auditId: string) {
  return request<Audit>(`/audits/${encodeURIComponent(auditId)}`).then(normalizeAudit);
}

export function getAuditStreamUrl(auditId: string) {
  return buildApiUrl(`/audits/${encodeURIComponent(auditId)}/stream`);
}

export function getWall() {
  return request<WallEntry[]>("/wall").then((entries) =>
    Array.isArray(entries) ? entries.map(normalizeWallEntry) : [],
  );
}

export const apiClient = {
  getHealth,
  createAudit,
  createDemoAudit,
  getDemoSetup,
  getAudit,
  getAuditStreamUrl,
  getWall,
};
