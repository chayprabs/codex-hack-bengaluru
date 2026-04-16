export type AuditState = "queued" | "running" | "completed" | "failed";
export type AgentState = AuditState;
export type FindingSeverity = "low" | "medium" | "high" | "critical";
export type CoverageBand = "minimal" | "limited" | "targeted" | "broad" | "deep";
export type AgentTraceSource = "backend" | "derived" | "placeholder";
export type AgentTraceStepStatus = "completed" | "active" | "pending" | "failed";
export type AgentTraceStepKind =
  | "scope_loaded"
  | "read_file"
  | "search_code"
  | "candidate_found"
  | "evidence_recorded"
  | "patch_proposed"
  | "verification"
  | "note";

export type Finding = {
  id: string;
  severity: FindingSeverity;
  title: string;
  summary: string;
  file_path: string | null;
  line: number | null;
  created_at: string;
};

export type AgentTraceStep = {
  id: string;
  kind: AgentTraceStepKind;
  title: string;
  detail: string;
  status: AgentTraceStepStatus;
  timestamp: string | null;
  tool?: string | null;
  location?: string | null;
  finding_id?: string | null;
};

export type AgentTrace = {
  agent_name: string;
  source: AgentTraceSource;
  updated_at: string;
  headline?: string | null;
  summary?: string | null;
  steps: AgentTraceStep[];
};

export type AgentStatus = {
  name: string;
  status: AgentState;
  message: string;
  updated_at: string;
  trace?: AgentTrace | null;
};

export type Audit = {
  id: string;
  repo_url: string;
  status: AuditState;
  score: number;
  score_baseline: number;
  coverage: number;
  coverage_percent: number;
  coverage_baseline: number;
  coverage_band: CoverageBand;
  coverage_summary: string;
  confidence_limited: boolean;
  supported_areas: string[];
  partially_supported_areas: string[];
  unsupported_areas: string[];
  scanned_files_count: number;
  skipped_files_count: number;
  frameworks_detected: string[];
  checks_run: string[];
  checks_skipped: string[];
  completion_message: string | null;
  created_at: string;
  updated_at: string;
  agents: AgentStatus[];
  findings: Finding[];
};

export type CreateAuditRequest = {
  repo_url: string;
};

export type WallEntry = {
  audit_id: string;
  repo_url: string;
  title: string;
  severity: FindingSeverity;
  created_at: string;
};

export type DatabaseHealth = {
  driver: "memory" | "sqlite";
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
  coverage: number;
  coverage_percent: number;
  previous_coverage: number | null;
  coverage_delta: number | null;
  coverage_band: CoverageBand;
  coverage_summary?: string | null;
  confidence_limited: boolean;
  supported_areas: string[];
  partially_supported_areas: string[];
  unsupported_areas: string[];
  scanned_files_count: number;
  skipped_files_count: number;
  frameworks_detected: string[];
  checks_run: string[];
  checks_skipped: string[];
  reason?: string | null;
  updated_at: string;
};

export type AgentStatusEvent = AgentStatus & {
  audit_id: string;
};

export type AgentTraceEvent = AgentTrace & {
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
  coverage: number;
  coverage_percent: number;
  coverage_band: CoverageBand;
  coverage_summary?: string | null;
  confidence_limited: boolean;
  supported_areas: string[];
  partially_supported_areas: string[];
  unsupported_areas: string[];
  scanned_files_count: number;
  skipped_files_count: number;
  frameworks_detected: string[];
  checks_run: string[];
  checks_skipped: string[];
  updated_at: string;
  finding_count: number;
  message?: string | null;
};

export type AuditStreamEventName = "agent_status" | "agent_trace" | "finding" | "score_update" | "audit_complete";

export type AuditStreamConnectionState = "connecting" | "live" | "polling" | "reconnecting" | "closed";
