import type { CoverageBand } from "@/lib/types";

export type CoverageTone = "neutral" | "info" | "success" | "warning" | "danger";

const EXPLICIT_AUDIT_LABELS: Record<string, string> = {
  "api routes": "API routes",
  "auth / session": "Auth / Session",
  "database / schema": "Database / Schema",
  "frontend runtime": "Frontend Runtime",
  "secrets / environment": "Secrets / Environment",
  "nextjs": "Next.js",
  "fastapi": "FastAPI",
  "nestjs": "NestJS",
  "sqlalchemy": "SQLAlchemy",
  "github actions": "GitHub Actions",
  "repo mapper": "Repo mapper",
  "api contract": "API contract",
  "input validation": "Input validation",
  "build type lint": "Build type lint",
  "buildbreak": "Build break",
  "authz": "Authz",
};

export function toneFromCoverageBand(band: CoverageBand | null | undefined): CoverageTone {
  switch (band) {
    case "deep":
      return "success";
    case "broad":
      return "info";
    case "targeted":
    case "limited":
    case "minimal":
      return "warning";
    default:
      return "neutral";
  }
}

export function unsupportedScopeCount(
  unsupportedAreas: readonly string[] = [],
  unsupportedTechnologies: readonly string[] = [],
): number {
  return unsupportedAreas.length + unsupportedTechnologies.length;
}

export function formatAuditLabel(value: string): string {
  const normalized = value.trim().replace(/[_-]+/g, " ");
  if (!normalized) {
    return normalized;
  }

  const explicit = EXPLICIT_AUDIT_LABELS[normalized.toLowerCase()];
  if (explicit) {
    return explicit;
  }

  return normalized
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
