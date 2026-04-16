import type { AuditState, FindingSeverity } from "@/lib/types";

export function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export function isGithubRepoUrl(value: string) {
  try {
    const url = new URL(value);
    return (
      (url.protocol === "http:" || url.protocol === "https:") &&
      url.hostname.includes("github.com") &&
      url.pathname.split("/").filter(Boolean).length >= 2
    );
  } catch {
    return false;
  }
}

export function titleCase(value: string) {
  return value
    .replace(/[_-]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function shortId(value: string, length = 8) {
  return value.slice(0, length);
}

export function repoLabelFromUrl(repoUrl: string) {
  try {
    const url = new URL(repoUrl);
    const parts = url.pathname.split("/").filter(Boolean);
    return parts.slice(0, 2).join("/") || repoUrl;
  } catch {
    return repoUrl;
  }
}

export function isTerminalAuditStatus(status: AuditState) {
  return status === "completed" || status === "failed";
}

export function formatSeverityLabel(value: FindingSeverity) {
  return titleCase(value);
}
