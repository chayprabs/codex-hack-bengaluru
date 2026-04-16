export type AuditState = "queued" | "running" | "completed" | "failed";
export type AgentState = AuditState;
export type FindingSeverity = "low" | "medium" | "high" | "critical";
export type FindingConfidence = "low" | "medium" | "high";
export type FindingProofType =
  | "deterministic_pattern"
  | "runtime_check"
  | "exploit_succeeded"
  | "manual_review_recommendation";
export type FindingVerificationState = "unverified" | "in_review" | "verified" | "manual_review" | "failed";
export type ReplayRecordReadiness = "regression_ready" | "needs_manual_followup";
export type CoverageBand = "minimal" | "limited" | "targeted" | "broad" | "deep";
export type AuditMode = "fast" | "deep";
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
  summary?: string | null;
  technical_summary?: string | null;
  file_path?: string | null;
  line?: number | null;
  agent_name: string | null;
  check_name: string | null;
  files: string[];
  line_hints: string[];
  impact_summary: string;
  evidence_snippet: string | null;
  confidence: FindingConfidence;
  proof_type: FindingProofType;
  suggested_patch: string | null;
  verification_state: FindingVerificationState;
  created_at: string;
};

export type ReplayRecord = {
  id: string;
  finding_id: string | null;
  title: string;
  finding_type: string;
  file_targets: string[];
  confidence: FindingConfidence;
  proof_type: FindingProofType;
  verification_state: FindingVerificationState;
  proof_summary: string;
  verification_summary: string;
  suggested_regression_test: string;
  generated_artifact_path: string | null;
  readiness: ReplayRecordReadiness;
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
  audit_mode: AuditMode;
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
  needs_manual_review_areas: string[];
  unsupported_technologies: string[];
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
  replay_records: ReplayRecord[];
};

export type CreateAuditRequest = {
  repo_url: string;
  audit_mode?: AuditMode;
};

export type WallEntry = {
  audit_id: string;
  finding_id: string;
  repo_url: string;
  title: string;
  severity: FindingSeverity;
  agent_name: string | null;
  check_name: string | null;
  impact_summary: string;
  confidence: FindingConfidence;
  proof_type: FindingProofType;
  verification_state: FindingVerificationState;
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

export type DemoFindingPreview = {
  severity: FindingSeverity;
  title: string;
};

export type DemoProfileSummary = {
  key: string;
  label: string;
  repo_url: string;
  is_flagship: boolean;
  summary: string;
  recommended_use: string;
  focus_areas: string[];
  score_journey: number[];
  coverage_journey: number[];
  preview_findings: DemoFindingPreview[];
  finding_count: number;
  final_score: number;
  final_coverage: number;
  completion_message: string | null;
};

export type DemoSetupResponse = {
  primary_demo_repo_url: string;
  stream_backup_summary: string;
  boring_repo_backup_summary: string;
  profiles: DemoProfileSummary[];
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
  needs_manual_review_areas: string[];
  unsupported_technologies: string[];
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
  needs_manual_review_areas: string[];
  unsupported_technologies: string[];
  scanned_files_count: number;
  skipped_files_count: number;
  frameworks_detected: string[];
  checks_run: string[];
  checks_skipped: string[];
  replay_records: ReplayRecord[];
  updated_at: string;
  finding_count: number;
  message?: string | null;
};

export type AuditStreamEventName = "agent_status" | "agent_trace" | "finding" | "score_update" | "audit_complete";

export type AuditStreamConnectionState = "connecting" | "live" | "polling" | "reconnecting" | "closed";
