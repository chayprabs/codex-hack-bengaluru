import type {
  AgentStatus,
  Audit,
  AuditMode,
  CoverageBand,
  DemoFindingPreview,
  DemoProfileSummary,
  DemoSetupResponse,
  Finding,
  FindingConfidence,
  FindingProofType,
  FindingSeverity,
  FindingVerificationState,
  ReplayRecord,
  ReplayRecordReadiness,
  WallEntry,
} from "@/lib/types";

export const FLAGSHIP_DEMO_AUDIT_ID = "demo";
export const LOCAL_PREVIEW_AUDIT_ID = "local-preview";

type LocalFindingSeed = {
  severity: FindingSeverity;
  title: string;
  impactSummary: string;
  technicalSummary: string;
  filePath: string;
  line: number;
  agentName: string;
  checkName: string;
  confidence: FindingConfidence;
  proofType: FindingProofType;
  verificationState: FindingVerificationState;
  evidenceSnippet: string;
  suggestedPatch: string;
};

type LocalProfileSeed = {
  key: string;
  label: string;
  repoUrl: string;
  summary: string;
  recommendedUse: string;
  focusAreas: string[];
  matchTokens: string[];
  scoreJourney: number[];
  coverageJourney: number[];
  completionMessage: string;
  supportedAreas: string[];
  partiallySupportedAreas: string[];
  unsupportedAreas: string[];
  needsManualReviewAreas: string[];
  unsupportedTechnologies: string[];
  frameworksDetected: string[];
  checksRun: string[];
  checksSkipped: string[];
  scannedFilesCount: number;
  skippedFilesCount: number;
  confidenceLimited?: boolean;
  findings: LocalFindingSeed[];
};

const LOCAL_DEMO_PROFILES: LocalProfileSeed[] = [
  {
    key: "trustlayer-flagship",
    label: "Acme subscriptions platform",
    repoUrl: "https://github.com/trustlayer-demo/acme-subscriptions-platform",
    summary:
      "Flagship seeded story with release-secret leakage, unsigned billing webhooks, tenant export IDOR, release gate drift, and unsafe markdown rendering.",
    recommendedUse:
      "Default hackathon path when you want the clearest score motion, the strongest wall entries, and a predictable final report.",
    focusAreas: ["Secrets", "Webhook trust", "Authz / IDOR", "Release safety", "Frontend runtime"],
    matchTokens: [],
    scoreJourney: [100, 98, 96, 88, 74, 67, 57],
    coverageJourney: [12, 18, 31, 46, 64, 77, 92],
    completionMessage:
      "TrustLayer closed the flagship demo with anchored findings across secrets, unsigned billing callbacks, tenant export authorization, release gates, and unsafe markdown runtime handling.",
    supportedAreas: ["API routes", "Webhooks", "Secrets / Environment", "Configuration", "Dependencies"],
    partiallySupportedAreas: ["Auth / Session", "Frontend Runtime"],
    unsupportedAreas: ["Infrastructure"],
    needsManualReviewAreas: ["Database / Schema"],
    unsupportedTechnologies: [],
    frameworksDetected: ["fastapi", "nextjs", "github_actions"],
    checksRun: ["repo_mapper", "planner", "secrets", "webhook", "authz", "dependency", "build_type_lint"],
    checksSkipped: ["infrastructure"],
    scannedFilesCount: 164,
    skippedFilesCount: 6,
    findings: [
      {
        severity: "high",
        title: "Deploy workflow references a long-lived preview token",
        impactSummary:
          "Release automation still depends on a long-lived preview token pattern that weakens secret rotation and makes copy-paste reuse likely.",
        technicalSummary:
          "A checked-in deployment workflow example still references a long-lived preview token, which keeps release secret handling brittle and easy to cargo-cult into other repos.",
        filePath: ".github/workflows/deploy-preview.yml",
        line: 22,
        agentName: "scanner",
        checkName: "secrets",
        confidence: "high",
        proofType: "deterministic_pattern",
        verificationState: "manual_review",
        evidenceSnippet: "env: PREVIEW_DEPLOY_TOKEN: ${{ secrets.PREVIEW_DEPLOY_TOKEN }}",
        suggestedPatch:
          "Move preview deploys onto short-lived environment-scoped credentials and remove long-lived token examples from checked-in workflow snippets.",
      },
      {
        severity: "high",
        title: "Billing webhook accepts unsigned events",
        impactSummary:
          "Billing state can be influenced before the callback signature is verified, leaving subscription and invoice flows open to forged webhook traffic.",
        technicalSummary:
          "The billing callback path processes event bodies before verifying the upstream signature header, so forged retries can reach state-changing code too early.",
        filePath: "apps/api/routes/webhooks.py",
        line: 48,
        agentName: "scanner",
        checkName: "webhook_signature",
        confidence: "high",
        proofType: "runtime_check",
        verificationState: "verified",
        evidenceSnippet: "process_billing_event(body) executes before verify_signature(signature, body)",
        suggestedPatch:
          "Reject missing or invalid signatures before parsing the payload or mutating billing state, then replay the callback path under verifier control.",
      },
      {
        severity: "medium",
        title: "Invoice export trusts workspace_id from the query string",
        impactSummary:
          "The export path authenticates the session but still trusts caller-supplied workspace scope, leaving a tenant-boundary gap on invoice exports.",
        technicalSummary:
          "The export handler checks for a valid session but does not re-verify workspace ownership before loading invoices, which creates an IDOR-style gap on exports.",
        filePath: "apps/api/routes/invoices.py",
        line: 91,
        agentName: "scanner",
        checkName: "authz_idor",
        confidence: "medium",
        proofType: "deterministic_pattern",
        verificationState: "verified",
        evidenceSnippet: "workspace = load_workspace(request.query_params[\"workspace_id\"])",
        suggestedPatch:
          "Resolve the workspace from the authenticated session or re-check membership before loading or exporting invoice data.",
      },
      {
        severity: "medium",
        title: "Patch releases bypass lint and typecheck",
        impactSummary:
          "Patch builds can package and publish before the quality gates that should catch broken guards or risky runtime assumptions.",
        technicalSummary:
          "The patch release workflow packages artifacts before lint and typecheck complete, which weakens the release path exactly where fast fixes are supposed to stay safe.",
        filePath: ".github/workflows/release-patch.yml",
        line: 29,
        agentName: "scanner",
        checkName: "build_type_lint",
        confidence: "medium",
        proofType: "deterministic_pattern",
        verificationState: "unverified",
        evidenceSnippet: "publish_patch runs before lint and typecheck gates settle",
        suggestedPatch:
          "Restore blocking quality gates before packaging artifacts or allowing the patch release path to publish.",
      },
      {
        severity: "medium",
        title: "Shared markdown renderer allows a vulnerable package range",
        impactSummary:
          "The shared markdown surface permits a dependency range with a client-side injection advisory, keeping preview and dashboard content riskier than the score alone suggests.",
        technicalSummary:
          "The shared frontend rendering layer allows a markdown dependency range with a known injection advisory, so preview surfaces inherit unsafe runtime behavior until the package is pinned.",
        filePath: "packages/ui/package.json",
        line: 41,
        agentName: "scanner",
        checkName: "dependency",
        confidence: "medium",
        proofType: "manual_review_recommendation",
        verificationState: "manual_review",
        evidenceSnippet: "\"markdown-renderer\": \"^3.2.0\"",
        suggestedPatch:
          "Pin the renderer to a patched range, rebuild the preview surface, and verify the markdown path before shipping the next release.",
      },
    ],
  },
  {
    key: "billing-webhooks",
    label: "Billing webhooks",
    repoUrl: "https://github.com/trustlayer-demo/acme-billing-hooks",
    summary:
      "Revenue-path replay focused on payout signatures, mirrored webhook secrets, and release trust around payment callbacks.",
    recommendedUse:
      "Best backup when the room wants a tighter payments or callback story than a general live repo provides.",
    focusAreas: ["Billing callbacks", "Secrets", "Webhook trust", "Release safety"],
    matchTokens: ["billing", "webhook", "stripe", "payment", "hooks"],
    scoreJourney: [100, 95, 82, 64, 41],
    coverageJourney: [12, 26, 48, 69, 88],
    completionMessage:
      "TrustLayer confirmed the payout callback path is not safe for forged retries. Fix signature validation, rotate mirrored secrets, and re-run the payment replay before rollout.",
    supportedAreas: ["API routes", "Webhooks", "Secrets / Environment", "Configuration"],
    partiallySupportedAreas: ["Auth / Session"],
    unsupportedAreas: ["Frontend Runtime", "Infrastructure"],
    needsManualReviewAreas: ["Database / Schema"],
    unsupportedTechnologies: [],
    frameworksDetected: ["fastapi", "stripe", "github_actions"],
    checksRun: ["repo_mapper", "planner", "secrets", "webhook", "build_type_lint"],
    checksSkipped: ["dependency"],
    scannedFilesCount: 98,
    skippedFilesCount: 2,
    findings: [
      {
        severity: "critical",
        title: "Payout retry webhook processes unsigned events",
        impactSummary:
          "Forged payout retries can reach billing-state mutations before TrustLayer sees proof of a valid provider signature.",
        technicalSummary:
          "The payout retry handler reads and mutates billing state before signature verification, which keeps the callback trust boundary in a critical state.",
        filePath: "apps/api/routes/payout_webhooks.py",
        line: 37,
        agentName: "scanner",
        checkName: "webhook_signature",
        confidence: "high",
        proofType: "runtime_check",
        verificationState: "verified",
        evidenceSnippet: "retry_payout(body) runs before validate_signature(signature, body)",
        suggestedPatch:
          "Reject missing or invalid signatures before parsing payout bodies or mutating retry state, then replay the callback with verifier control.",
      },
      {
        severity: "high",
        title: "Mirrored webhook secret remains in deploy samples",
        impactSummary:
          "Deployment samples still mirror a long-lived webhook secret, which weakens rotation and makes copy-paste leakage more likely.",
        technicalSummary:
          "A checked-in deploy sample duplicates the webhook signing secret into another environment variable, which keeps secret boundaries loose and harder to rotate safely.",
        filePath: ".github/workflows/release-payments.yml",
        line: 18,
        agentName: "scanner",
        checkName: "secrets",
        confidence: "high",
        proofType: "deterministic_pattern",
        verificationState: "manual_review",
        evidenceSnippet: "env: PAYOUT_SIGNING_SECRET: ${{ secrets.WEBHOOK_SHARED_SECRET }}",
        suggestedPatch:
          "Replace mirrored webhook secrets with environment-scoped credentials and remove long-lived secret references from checked-in samples.",
      },
      {
        severity: "medium",
        title: "Patch release path skips billing callback replay",
        impactSummary:
          "Patch builds can ship billing changes without replaying the callback regression path that should protect payout retries.",
        technicalSummary:
          "The payment patch workflow skips the callback replay step on patch releases, so regressions in signing order can ship without the strongest test path.",
        filePath: ".github/workflows/release-payments.yml",
        line: 44,
        agentName: "scanner",
        checkName: "build_type_lint",
        confidence: "medium",
        proofType: "manual_review_recommendation",
        verificationState: "unverified",
        evidenceSnippet: "if: github.event.inputs.skip_callback_replay == 'true'",
        suggestedPatch:
          "Make the callback replay mandatory for payout-path releases and fail the workflow if the replay step is skipped or unstable.",
      },
    ],
  },
  {
    key: "tenant-portal",
    label: "Tenant portal",
    repoUrl: "https://github.com/trustlayer-demo/workspace-portal",
    summary:
      "Tenant-isolation replay with customer-document IDOR and a preview runtime that trusts unbounded postMessage origins.",
    recommendedUse:
      "Best backup when you need a multi-tenant data exposure story instead of webhook or release risk.",
    focusAreas: ["Authz / IDOR", "Tenant boundaries", "Preview runtime"],
    matchTokens: ["tenant", "portal", "auth", "workspace", "account", "idor"],
    scoreJourney: [100, 96, 78, 67],
    coverageJourney: [12, 27, 62, 88],
    completionMessage:
      "TrustLayer closed the tenant-portal report with confirmed isolation gaps on customer documents and the admin preview runtime. Lock tenant ownership and trusted preview origins before shipping.",
    supportedAreas: ["API routes", "Auth / Session", "Database / Schema", "Frontend Runtime"],
    partiallySupportedAreas: ["Dependencies"],
    unsupportedAreas: ["Webhooks", "Infrastructure"],
    needsManualReviewAreas: [],
    unsupportedTechnologies: [],
    frameworksDetected: ["fastapi", "react"],
    checksRun: ["repo_mapper", "planner", "authz", "frontend_runtime"],
    checksSkipped: ["dependency"],
    scannedFilesCount: 121,
    skippedFilesCount: 5,
    findings: [
      {
        severity: "high",
        title: "Customer document endpoint trusts account_id from the URL",
        impactSummary:
          "Authenticated users can request another account's document path if the URL account_id is not re-bound to session ownership.",
        technicalSummary:
          "The document download handler uses the authenticated session but does not re-check whether the requested account_id belongs to that user, enabling IDOR on customer documents.",
        filePath: "apps/api/routes/customer_documents.py",
        line: 74,
        agentName: "scanner",
        checkName: "authz_idor",
        confidence: "high",
        proofType: "deterministic_pattern",
        verificationState: "verified",
        evidenceSnippet: "return load_document(account_id=request.path_params[\"account_id\"])",
        suggestedPatch:
          "Resolve the account from the authenticated session or re-check membership before loading or returning tenant-scoped documents.",
      },
      {
        severity: "medium",
        title: "Preview runtime accepts postMessage events from any origin",
        impactSummary:
          "The admin preview frame trusts unbounded postMessage origins, which widens the blast radius of compromised content previews.",
        technicalSummary:
          "The preview frame processes postMessage payloads without constraining origin, so the admin preview surface trusts content from any sender.",
        filePath: "apps/web/components/PreviewFrame.tsx",
        line: 33,
        agentName: "scanner",
        checkName: "frontend_runtime",
        confidence: "medium",
        proofType: "manual_review_recommendation",
        verificationState: "manual_review",
        evidenceSnippet: "window.addEventListener(\"message\", handlePreviewMessage)",
        suggestedPatch:
          "Restrict trusted origins and validate the incoming message shape before rendering or mutating preview state.",
      },
    ],
  },
  {
    key: "ui-release-monitor",
    label: "UI release monitor",
    repoUrl: "https://github.com/trustlayer-demo/ui-release-monitor",
    summary:
      "Frontend-platform replay centered on release-gate bypasses and a vulnerable shared markdown runtime dependency.",
    recommendedUse:
      "Best backup when the room is more interested in CI, dependency hygiene, or frontend trust than backend exploits.",
    focusAreas: ["Release safety", "Dependencies", "Frontend runtime"],
    matchTokens: ["frontend", "ui", "web", "dashboard", "monorepo", "design-system"],
    scoreJourney: [100, 97, 83, 71],
    coverageJourney: [12, 29, 61, 84],
    completionMessage:
      "TrustLayer closed the UI release report with verified gaps in release gating and markdown dependency hygiene. Restore blocking checks and upgrade the shared renderer before the next patch train.",
    supportedAreas: ["Configuration", "Dependencies", "Frontend Runtime", "Infrastructure"],
    partiallySupportedAreas: ["Secrets / Environment"],
    unsupportedAreas: ["API routes", "Auth / Session"],
    needsManualReviewAreas: [],
    unsupportedTechnologies: [],
    frameworksDetected: ["nextjs", "storybook", "github_actions"],
    checksRun: ["repo_mapper", "planner", "build_type_lint", "typelint", "dependency"],
    checksSkipped: [],
    scannedFilesCount: 147,
    skippedFilesCount: 9,
    findings: [
      {
        severity: "medium",
        title: "Release pipeline bypasses lint and typecheck on patch builds",
        impactSummary:
          "Patch release jobs can publish artifacts before the checks that should keep runtime regressions out of production.",
        technicalSummary:
          "Patch release jobs package and publish before lint and typecheck complete, making it easier to ship broken guards or unsafe runtime assumptions.",
        filePath: ".github/workflows/release-patch.yml",
        line: 29,
        agentName: "scanner",
        checkName: "build_type_lint",
        confidence: "medium",
        proofType: "deterministic_pattern",
        verificationState: "verified",
        evidenceSnippet: "publish_patch needs: [package] # lint and typecheck run later",
        suggestedPatch:
          "Restore blocking lint and typecheck gates before patch artifacts can publish or tag the release branch.",
      },
      {
        severity: "medium",
        title: "Shared markdown runtime depends on a vulnerable package range",
        impactSummary:
          "The shared frontend rendering layer keeps a markdown dependency range with a client-side injection advisory in scope.",
        technicalSummary:
          "The shared frontend rendering layer permits a markdown dependency range with a known client-side injection advisory, leaving dashboard preview content exposed until the package is pinned.",
        filePath: "packages/ui/package.json",
        line: 41,
        agentName: "scanner",
        checkName: "dependency",
        confidence: "medium",
        proofType: "manual_review_recommendation",
        verificationState: "manual_review",
        evidenceSnippet: "\"markdown-renderer\": \"^4.0.0\"",
        suggestedPatch:
          "Pin the renderer to a patched version, rebuild the preview surface, and re-test the markdown path before the next patch train.",
      },
    ],
  },
  {
    key: "ops-runner-console",
    label: "Ops runner console",
    repoUrl: "https://github.com/trustlayer-demo/ops-runner-console",
    summary:
      "Execution-boundary replay showing host credential inheritance and workspace cleanup gaps inside a repo-owned runner.",
    recommendedUse:
      "Best backup when you need a sharper critical-risk story or a more infrastructure-flavored close.",
    focusAreas: ["Secrets", "Runner sandbox", "Cleanup behavior", "Infrastructure"],
    matchTokens: ["runner", "ops", "sandbox", "executor", "agent", "console"],
    scoreJourney: [100, 95, 58, 47],
    coverageJourney: [12, 26, 57, 79],
    completionMessage:
      "TrustLayer closed the runner report with critical credential-inheritance risk in bootstrap and leftover workspace artifacts after failed commands. Isolate execution credentials before trusting repo-owned wrappers.",
    supportedAreas: ["Secrets / Environment", "Configuration", "Infrastructure"],
    partiallySupportedAreas: ["Dependencies"],
    unsupportedAreas: ["API routes", "Auth / Session", "Frontend Runtime"],
    needsManualReviewAreas: ["Database / Schema"],
    unsupportedTechnologies: [],
    frameworksDetected: ["python", "docker", "github_actions"],
    checksRun: ["repo_mapper", "planner", "secrets", "buildbreak"],
    checksSkipped: [],
    scannedFilesCount: 89,
    skippedFilesCount: 3,
    confidenceLimited: true,
    findings: [
      {
        severity: "critical",
        title: "Runner bootstrap inherits host cloud credentials into repo-owned scripts",
        impactSummary:
          "The bootstrap path preserves ambient cloud credentials while handing execution to a repo-owned wrapper, turning the runner into a critical trust-boundary failure.",
        technicalSummary:
          "The bootstrap path shells into a repo-owned wrapper while preserving ambient cloud credentials, which turns a compromised repository into a plausible credential-execution bridge.",
        filePath: "runner/bootstrap.sh",
        line: 31,
        agentName: "scanner",
        checkName: "secrets",
        confidence: "high",
        proofType: "deterministic_pattern",
        verificationState: "verified",
        evidenceSnippet: "exec ./repo_wrapper.sh \"$@\" # inherits AWS_* and GCP_* credentials",
        suggestedPatch:
          "Strip ambient cloud credentials before invoking repo-owned wrappers and re-issue only the minimum short-lived execution tokens needed for the task.",
      },
      {
        severity: "high",
        title: "Workspace cleanup skips nested temp dirs after command failure",
        impactSummary:
          "Failed runner commands can leave nested temp artifacts and captured command output behind for later runs to inspect.",
        technicalSummary:
          "Cleanup only removes the top-level temp directory on failure, leaving nested artifacts and captured command output behind for later runs to inspect.",
        filePath: "runner/workspace.py",
        line: 117,
        agentName: "scanner",
        checkName: "buildbreak",
        confidence: "medium",
        proofType: "manual_review_recommendation",
        verificationState: "manual_review",
        evidenceSnippet: "shutil.rmtree(temp_root, ignore_errors=True)  # nested scratch dirs persist",
        suggestedPatch:
          "Make failure-path cleanup recursive, verify nested scratch removal, and add a regression around crash-path workspace teardown.",
      },
    ],
  },
];

function minutesAgo(minutes: number) {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

function pluralize(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

function coverageBand(value: number): CoverageBand {
  if (value >= 85) {
    return "deep";
  }

  if (value >= 70) {
    return "broad";
  }

  if (value >= 55) {
    return "targeted";
  }

  if (value >= 30) {
    return "limited";
  }

  return "minimal";
}

function defaultReplayReadiness(verificationState: FindingVerificationState): ReplayRecordReadiness {
  return verificationState === "verified" ? "regression_ready" : "needs_manual_followup";
}

function demoProfileSeed(profileKey?: string) {
  if (!profileKey) {
    return LOCAL_DEMO_PROFILES[0];
  }

  return LOCAL_DEMO_PROFILES.find((profile) => profile.key === profileKey) ?? null;
}

function scoreJourney(profile: LocalProfileSeed) {
  return profile.scoreJourney.length > 0 ? profile.scoreJourney : [100];
}

function coverageJourney(profile: LocalProfileSeed) {
  return profile.coverageJourney.length > 0 ? profile.coverageJourney : [12];
}

function findingPreview(profile: LocalProfileSeed): DemoFindingPreview[] {
  return profile.findings.map((finding) => ({
    severity: finding.severity,
    title: finding.title,
  }));
}

function localProfileSummary(profile: LocalProfileSeed): DemoProfileSummary {
  const scores = scoreJourney(profile);
  const coverage = coverageJourney(profile);

  return {
    key: profile.key,
    label: profile.label,
    repo_url: profile.repoUrl,
    is_flagship: profile.key === LOCAL_DEMO_PROFILES[0]?.key,
    summary: profile.summary,
    recommended_use: profile.recommendedUse,
    focus_areas: profile.focusAreas,
    score_journey: scores,
    coverage_journey: coverage,
    preview_findings: findingPreview(profile),
    finding_count: profile.findings.length,
    final_score: scores[scores.length - 1] ?? 100,
    final_coverage: coverage[coverage.length - 1] ?? 12,
    completion_message: profile.completionMessage,
  };
}

function replayRecords(auditId: string, findings: Finding[]): ReplayRecord[] {
  return findings
    .filter((finding) => finding.severity === "critical" || finding.severity === "high")
    .slice(0, 2)
    .map((finding, index) => ({
      id: `${auditId}-replay-${index + 1}`,
      finding_id: finding.id,
      title: `${finding.title} regression handoff`,
      finding_type: "security_finding",
      file_targets: finding.files,
      confidence: finding.confidence,
      proof_type: finding.proof_type,
      verification_state: finding.verification_state,
      proof_summary: finding.technical_summary ?? finding.summary ?? finding.title,
      verification_summary:
        finding.verification_state === "verified"
          ? "Verifier kept this finding in scope and tied it to the final score."
          : "This finding still needs manual follow-up before the remediation is trusted.",
      suggested_regression_test: `Add a focused regression around ${finding.title.toLowerCase()}.`,
      generated_artifact_path: `reports/${auditId}/replay-${index + 1}.md`,
      readiness: defaultReplayReadiness(finding.verification_state),
    }));
}

function buildAuditFromProfile(
  profile: LocalProfileSeed,
  options: {
    auditId: string;
    repoUrl?: string;
    auditMode?: AuditMode;
    variant: "demo" | "preview";
  },
): Audit {
  const scores = scoreJourney(profile);
  const coverage = coverageJourney(profile);
  const finalScore = scores[scores.length - 1] ?? 100;
  const finalCoverage = coverage[coverage.length - 1] ?? 12;
  const createdAt = minutesAgo(7.5);
  const plannerAt = minutesAgo(6.5);
  const scannerAt = minutesAgo(2);
  const verifierAt = minutesAgo(0.7);
  const repoUrl = options.repoUrl ?? profile.repoUrl;
  const completionMessage =
    options.variant === "preview"
      ? `Seeded local preview: the backend live-audit path was unavailable, so this room is showing the ${profile.label} profile matched to ${repoUrl}. Treat it as a walkthrough, not a fresh scan.`
      : profile.completionMessage;

  const findings = profile.findings.map<Finding>((finding, index) => ({
    id: `${options.auditId}-finding-${index + 1}`,
    severity: finding.severity,
    title: finding.title,
    summary: finding.technicalSummary,
    technical_summary: finding.technicalSummary,
    file_path: finding.filePath,
    line: finding.line,
    agent_name: finding.agentName,
    check_name: finding.checkName,
    files: [finding.filePath],
    line_hints: [String(finding.line)],
    impact_summary: finding.impactSummary,
    evidence_snippet: finding.evidenceSnippet,
    confidence: finding.confidence,
    proof_type: finding.proofType,
    suggested_patch: finding.suggestedPatch,
    verification_state: finding.verificationState,
    created_at: minutesAgo(Math.max(0.9, 4.7 - index * 0.9)),
  }));

  const agents: AgentStatus[] = [
    {
      name: "planner",
      status: "completed",
      message:
        options.variant === "preview"
          ? `Planner matched ${repoUrl} to the ${profile.label} fallback profile so the create-audit flow still lands in a coherent room.`
          : `Planner mapped the seeded ${profile.label} story into a stable demo path.`,
      updated_at: plannerAt,
      trace: null,
    },
    {
      name: "scanner",
      status: "completed",
      message: `Scanner anchored ${pluralize(findings.length, "finding")} across ${profile.focusAreas.slice(0, 3).join(", ")}.`,
      updated_at: scannerAt,
      trace: null,
    },
    {
      name: "verifier",
      status: "completed",
      message:
        options.variant === "preview"
          ? "Verifier closed the fallback preview with explicit seeded-data caveats."
          : "Verifier closed the demo report and locked the final score for the walkthrough.",
      updated_at: verifierAt,
      trace: null,
    },
  ];

  return {
    id: options.auditId,
    repo_url: repoUrl,
    audit_mode: options.auditMode ?? "deep",
    status: "completed",
    score: finalScore,
    score_baseline: 100,
    coverage: finalCoverage,
    coverage_percent: finalCoverage,
    coverage_baseline: 12,
    coverage_band: coverageBand(finalCoverage),
    coverage_summary: `Coverage is ${finalCoverage}/100 (${coverageBand(finalCoverage)}). ${completionMessage}`,
    confidence_limited: profile.confidenceLimited ?? finalCoverage < 55,
    supported_areas: profile.supportedAreas,
    partially_supported_areas: profile.partiallySupportedAreas,
    unsupported_areas: profile.unsupportedAreas,
    needs_manual_review_areas: profile.needsManualReviewAreas,
    unsupported_technologies: profile.unsupportedTechnologies,
    scanned_files_count: profile.scannedFilesCount,
    skipped_files_count: profile.skippedFilesCount,
    frameworks_detected: profile.frameworksDetected,
    checks_run: profile.checksRun,
    checks_skipped: profile.checksSkipped,
    completion_message: completionMessage,
    created_at: createdAt,
    updated_at: verifierAt,
    agents,
    findings,
    replay_records: replayRecords(options.auditId, findings),
  };
}

export function buildDemoAuditId(profileKey?: string) {
  if (!profileKey || profileKey === LOCAL_DEMO_PROFILES[0]?.key) {
    return FLAGSHIP_DEMO_AUDIT_ID;
  }

  return `demo--${profileKey}`;
}

export function buildDemoAuditHref(profileKey?: string) {
  return `/audit/${buildDemoAuditId(profileKey)}`;
}

export function buildLocalPreviewHref(repoUrl: string, auditMode: AuditMode) {
  const params = new URLSearchParams({
    repo: repoUrl,
    auditMode,
  });

  return `/audit/${LOCAL_PREVIEW_AUDIT_ID}?${params.toString()}`;
}

export function isLocalDemoAuditId(auditId: string) {
  return auditId === FLAGSHIP_DEMO_AUDIT_ID || auditId.startsWith("demo--");
}

export function isLocalPreviewAuditId(auditId: string) {
  return auditId === LOCAL_PREVIEW_AUDIT_ID;
}

export function isLocalAuditId(auditId: string) {
  return isLocalDemoAuditId(auditId) || isLocalPreviewAuditId(auditId);
}

export function getLocalAuditNotice(auditId: string) {
  if (isLocalPreviewAuditId(auditId)) {
    return "Seeded local preview: the live backend path was unavailable, so this room is matched to the requested repo shape instead of coming from a fresh scan.";
  }

  if (isLocalDemoAuditId(auditId)) {
    return "Deterministic seeded demo room: findings, score motion, and report state are intentionally fixed so the flagship walkthrough never depends on backend timing.";
  }

  return null;
}

export function getLocalDemoSetup(): DemoSetupResponse {
  return {
    primary_demo_repo_url: LOCAL_DEMO_PROFILES[0]?.repoUrl ?? "",
    stream_backup_summary:
      "The flagship path is rendered from local seeded data, so the room still shows score motion, findings, and a final report even if live backend streaming is unavailable.",
    boring_repo_backup_summary:
      "If a real repo stays quiet or the backend cannot finish a live run, switch to the seeded backup stories below so the demo stays honest and coherent instead of breaking.",
    profiles: LOCAL_DEMO_PROFILES.map(localProfileSummary),
  };
}

export function selectLocalProfile(repoUrl: string) {
  const normalizedRepoUrl = repoUrl.trim().toLowerCase();

  const exactMatch = LOCAL_DEMO_PROFILES.find((profile) => normalizedRepoUrl === profile.repoUrl.toLowerCase());
  if (exactMatch) {
    return exactMatch;
  }

  const tokenMatch = LOCAL_DEMO_PROFILES.slice(1).find((profile) =>
    profile.matchTokens.some((token) => normalizedRepoUrl.includes(token)),
  );

  return tokenMatch ?? LOCAL_DEMO_PROFILES[0];
}

export function getLocalDemoAudit(auditId: string): Audit | null {
  if (!isLocalDemoAuditId(auditId)) {
    return null;
  }

  const profileKey = auditId === FLAGSHIP_DEMO_AUDIT_ID ? LOCAL_DEMO_PROFILES[0]?.key : auditId.replace(/^demo--/, "");
  const profile = demoProfileSeed(profileKey);

  if (!profile) {
    return null;
  }

  return buildAuditFromProfile(profile, {
    auditId,
    auditMode: "deep",
    variant: "demo",
  });
}

export function buildLocalPreviewAudit(repoUrl: string, auditMode: AuditMode): Audit {
  const profile = selectLocalProfile(repoUrl);

  return buildAuditFromProfile(profile, {
    auditId: LOCAL_PREVIEW_AUDIT_ID,
    repoUrl,
    auditMode,
    variant: "preview",
  });
}

export function getLocalWallEntries(): WallEntry[] {
  return LOCAL_DEMO_PROFILES.flatMap((profile) => {
    const auditId = buildDemoAuditId(profile.key);
    const audit = buildAuditFromProfile(profile, {
      auditId,
      auditMode: "deep",
      variant: "demo",
    });

    return audit.findings.map<WallEntry>((finding) => ({
      audit_id: auditId,
      finding_id: finding.id,
      repo_url: audit.repo_url,
      title: finding.title,
      severity: finding.severity,
      agent_name: finding.agent_name,
      check_name: finding.check_name,
      impact_summary: finding.impact_summary,
      confidence: finding.confidence,
      proof_type: finding.proof_type,
      verification_state: finding.verification_state,
      created_at: finding.created_at,
    }));
  });
}
