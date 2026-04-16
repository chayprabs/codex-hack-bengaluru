import {
  DEFAULT_API_BASE_URL,
  DEFAULT_NETWORK_ERROR_MESSAGE,
  DEFAULT_REQUEST_ERROR_MESSAGE,
} from "@/lib/constants";
import type {
  Audit,
  AuditStreamStatus,
  CreateAuditRequest,
  HealthCheckResponse,
  WallEntry,
} from "@/lib/types";

export type {
  AgentStatusEvent,
  AgentState,
  AgentStatus,
  Audit,
  AuditCompleteEvent,
  AuditStreamConnectionState,
  AuditStreamEventName,
  AuditState,
  AuditStreamStatus,
  CreateAuditRequest,
  DatabaseHealth,
  Finding,
  FindingEvent,
  FindingSeverity,
  HealthCheckResponse,
  ScoreUpdateEvent,
  WallEntry,
} from "@/lib/types";

type ErrorPayload =
  | {
      detail?: string;
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

export function createAudit(repoUrl: string) {
  const payload: CreateAuditRequest = { repo_url: repoUrl };

  return request<Audit>("/audits", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createDemoAudit() {
  return request<Audit>("/demo-audit", {
    method: "POST",
  });
}

export function getAudit(auditId: string) {
  return request<Audit>(`/audits/${encodeURIComponent(auditId)}`);
}

export function getAuditStreamStatus(auditId: string) {
  return request<AuditStreamStatus>(`/audits/${encodeURIComponent(auditId)}/stream`);
}

export function getAuditStreamUrl(auditId: string) {
  return buildApiUrl(`/audits/${encodeURIComponent(auditId)}/stream`);
}

export function getWall() {
  return request<WallEntry[]>("/wall");
}

export const apiClient = {
  getHealth,
  createAudit,
  createDemoAudit,
  getAudit,
  getAuditStreamStatus,
  getAuditStreamHandshake: getAuditStreamStatus,
  getAuditStreamUrl,
  getWall,
};
