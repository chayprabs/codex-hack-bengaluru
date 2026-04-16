import { spawnSync } from "node:child_process";
import { platform } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptsDir = path.dirname(fileURLToPath(import.meta.url));
export const repoRoot = path.resolve(scriptsDir, "..");
export const webDir = path.join(repoRoot, "apps", "web");
export const apiDir = path.join(repoRoot, "apps", "api");

function candidateSucceeded(result) {
  return !result.error && typeof result.status === "number" && result.status === 0;
}

export function findPythonLauncher() {
  const candidates =
    platform() === "win32"
      ? [
          { command: "python", prefixArgs: [] },
          { command: "py", prefixArgs: ["-3"] },
          { command: "py", prefixArgs: [] },
        ]
      : [
          { command: "python3", prefixArgs: [] },
          { command: "python", prefixArgs: [] },
        ];

  for (const candidate of candidates) {
    const probe = spawnSync(candidate.command, [...candidate.prefixArgs, "--version"], {
      stdio: "ignore",
      cwd: repoRoot,
    });

    if (candidateSucceeded(probe)) {
      return candidate;
    }
  }

  throw new Error("Could not find Python 3.11+. Install Python first.");
}

export function findNpmCommand() {
  return "npm";
}

export function runCommand(command, args, options = {}) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
    cwd: repoRoot,
    ...options,
  });

  if (result.error) {
    throw result.error;
  }

  return typeof result.status === "number" ? result.status : 1;
}

export function runNpmCommand(args, options = {}) {
  return runCommand(findNpmCommand(), args, {
    ...options,
    shell: platform() === "win32",
  });
}

export function runPythonScript(scriptName, scriptArgs = []) {
  const python = findPythonLauncher();
  const scriptPath = path.join(scriptsDir, scriptName);
  return runCommand(python.command, [...python.prefixArgs, scriptPath, ...scriptArgs]);
}
