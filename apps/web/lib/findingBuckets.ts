import type { Finding, FindingSeverity } from "@/lib/types";

export type FindingBucketId =
  | "secrets_credentials"
  | "auth_access"
  | "webhook_integrations"
  | "unsafe_generated_code"
  | "dependency_setup"
  | "frontend_exposure";

export type FindingBucket = {
  id: FindingBucketId;
  label: string;
  quickTake: string;
  fixHint: string;
  count: number;
  majorCount: number;
  highestSeverity: FindingSeverity | null;
  examples: string[];
  findings: Finding[];
};

type FindingBucketDefinition = {
  id: FindingBucketId;
  label: string;
  quickTake: string;
  fixHint: string;
};

const BUCKET_DEFINITIONS: readonly FindingBucketDefinition[] = [
  {
    id: "secrets_credentials",
    label: "Secrets and credentials",
    quickTake: "Exposed keys can turn a code bug into real account or infrastructure access.",
    fixHint: "Rotate real values first, then move secrets out of code, prompts, and client bundles.",
  },
  {
    id: "auth_access",
    label: "Auth and access control",
    quickTake: "If identity or ownership checks drift, users can cross tenant lines fast.",
    fixHint: "Start with session assumptions, object lookups, and any allow-all policy code.",
  },
  {
    id: "webhook_integrations",
    label: "Webhook and external integrations",
    quickTake: "Outside systems should not change state until the sender is proven.",
    fixHint: "Verify signatures first, then handle idempotency and replay safety.",
  },
  {
    id: "unsafe_generated_code",
    label: "Unsafe generated code patterns",
    quickTake: "Risky shortcuts in code or agent rules can turn input into execution or unsafe state changes.",
    fixHint: "Search for eval-like execution, raw SQL, unsafe parsing, and security-bypass guidance.",
  },
  {
    id: "dependency_setup",
    label: "Dependency and setup risks",
    quickTake: "Build and install paths can import risk before the app even boots.",
    fixHint: "Lock versions, review install hooks, and keep build, lint, and type gates honest.",
  },
  {
    id: "frontend_exposure",
    label: "Frontend exposure risks",
    quickTake: "Anything shipped to the browser should be treated as public and abusable.",
    fixHint: "Strip client secrets, tighten browser-facing config, and remove unsafe HTML paths.",
  },
];

const SEVERITY_ORDER: Record<FindingSeverity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

function bucketForFinding(finding: Finding): FindingBucketId {
  const agentName = finding.agent_name?.toLowerCase() ?? "";
  const checkName = finding.check_name?.toLowerCase() ?? "";
  const haystack = [
    agentName,
    checkName,
    finding.title,
    finding.impact_summary,
    finding.technical_summary,
    finding.summary,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  if (
    agentName === "secrets" ||
    /(secret|credential|token|api key|access key|service role|service-role|webhook secret|bearer)/.test(haystack)
  ) {
    return "secrets_credentials";
  }

  if (
    agentName === "auth" ||
    agentName === "authz" ||
    /(auth|authorization|access control|idor|session|jwt|ownership|permission|allow-all|allow all)/.test(haystack)
  ) {
    return "auth_access";
  }

  if (
    agentName === "webhook" ||
    /(webhook|signature verification|signature|callback|idempotency|stripe|provider event|forged event)/.test(haystack)
  ) {
    return "webhook_integrations";
  }

  if (
    agentName === "dependency" ||
    agentName === "build_type_lint" ||
    agentName === "buildbreak" ||
    agentName === "typelint" ||
    /(dependency|lockfile|package manager|install script|build script|lint|typecheck|compile|env example|manifest|supply-chain|supply chain)/.test(
      haystack,
    )
  ) {
    return "dependency_setup";
  }

  if (
    agentName === "frontend_runtime" ||
    agentName === "config_headers_cors" ||
    /(frontend|browser|client-side|client side|site visitor|xss|dangerouslysetinnerhtml|innerhtml|cors|security headers|token storage|public env)/.test(
      haystack,
    )
  ) {
    return "frontend_exposure";
  }

  return "unsafe_generated_code";
}

function dedupeExamples(findings: Finding[]) {
  const examples: string[] = [];
  const seen = new Set<string>();

  for (const finding of findings) {
    const text = (finding.impact_summary || finding.title || "").trim();
    if (!text || seen.has(text)) {
      continue;
    }
    seen.add(text);
    examples.push(text);
    if (examples.length >= 2) {
      break;
    }
  }

  return examples;
}

function sortFindings(findings: Finding[]) {
  return [...findings].sort((left, right) => {
    const severityDelta = SEVERITY_ORDER[left.severity] - SEVERITY_ORDER[right.severity];
    if (severityDelta !== 0) {
      return severityDelta;
    }

    return Date.parse(right.created_at) - Date.parse(left.created_at);
  });
}

function highestSeverity(findings: Finding[]): FindingSeverity | null {
  const sorted = sortFindings(findings);
  return sorted[0]?.severity ?? null;
}

export function buildFindingBuckets(findings: Finding[]): FindingBucket[] {
  const grouped = new Map<FindingBucketId, Finding[]>();

  for (const definition of BUCKET_DEFINITIONS) {
    grouped.set(definition.id, []);
  }

  for (const finding of findings) {
    grouped.get(bucketForFinding(finding))?.push(finding);
  }

  return BUCKET_DEFINITIONS.map((definition) => {
    const bucketFindings = sortFindings(grouped.get(definition.id) ?? []);
    return {
      ...definition,
      count: bucketFindings.length,
      majorCount: bucketFindings.filter((finding) => finding.severity === "high" || finding.severity === "critical").length,
      highestSeverity: highestSeverity(bucketFindings),
      examples: dedupeExamples(bucketFindings),
      findings: bucketFindings,
    };
  });
}

export function summarizeQuietBuckets(buckets: FindingBucket[]) {
  return buckets.filter((bucket) => bucket.count === 0).map((bucket) => bucket.label);
}
