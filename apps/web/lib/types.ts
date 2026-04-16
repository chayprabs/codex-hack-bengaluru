export type AuditState = "queued" | "running" | "completed" | "failed";
export type AgentState = AuditState;
export type FindingSeverity = "low" | "medium" | "high" | "critical";

export type Finding = {
  id: string;
  severity: FindingSeverity;
  title: string;
  summary: string;
  file_path: string | null;
  line: number | null;
  created_at: string;
};

export type AgentStatus = {
  name: string;
  status: AgentState;
  message: string;
  updated_at: string;
};

export type Audit = {
  id: string;
  repo_url: string;
  status: AuditState;
  score: number;
  created_at: string;
  updated_at: string;
  agents: AgentStatus[];
  findings: Finding[];
};

export type CreateAuditRequest = {
  repo_url: string;
};

export type AuditStreamStatus = {
  status: "not_implemented";
  message: string;
};

export type WallEntry = {
  audit_id: string;
  repo_url: string;
  title: string;
  severity: FindingSeverity;
  created_at: string;
};

export type DatabaseHealth = {
  driver: "sqlite";
  path: string;
  ready: boolean;
};

export type HealthCheckResponse = {
  status: "ok";
  service: string;
  database: DatabaseHealth;
};

export type ScoreUpdateEvent = {
  audit_id: string;
  score: number;
  previous_score: number | null;
  delta: number | null;
  reason?: string | null;
  updated_at: string;
};

export type AgentStatusEvent = AgentStatus & {
  audit_id: string;
};

export type FindingEvent = Finding & {
  audit_id: string;
};

export type AuditCompleteEvent = {
  audit_id: string;
  status: AuditState;
  repo_url: string;
  score: number;
  updated_at: string;
  finding_count: number;
  message?: string | null;
};

export type AuditStreamEventName = "agent_status" | "finding" | "score_update" | "audit_complete";

export type AuditStreamConnectionState = "connecting" | "live" | "reconnecting" | "closed";
