#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

import { apiDir, findPythonLauncher, repoRoot, runCommand, runNpmCommand, webDir } from "./common.mjs";

const target = process.argv[2] ?? "all";

if (target === "-h" || target === "--help") {
  console.log("Usage: node scripts/setup.mjs [all|web|api]");
  process.exit(0);
}

if (!["all", "web", "api"].includes(target)) {
  console.error("Usage: node scripts/setup.mjs [all|web|api]");
  process.exit(1);
}

function setupWeb() {
  console.log("[trustlayer] installing web dependencies...");
  return runNpmCommand(["install"], { cwd: webDir });
}

function resolveApiVenvPython() {
  const windowsPython = path.join(apiDir, ".venv", "Scripts", "python.exe");
  const unixPython = path.join(apiDir, ".venv", "bin", "python");

  if (fs.existsSync(windowsPython)) {
    return windowsPython;
  }

  if (fs.existsSync(unixPython)) {
    return unixPython;
  }

  return null;
}

function setupApi() {
  const launcher = findPythonLauncher();
  const venvPython = resolveApiVenvPython();

  if (!venvPython) {
    console.log("[trustlayer] creating apps/api/.venv...");
    const createVenvExitCode = runCommand(launcher.command, [...launcher.prefixArgs, "-m", "venv", ".venv"], {
      cwd: apiDir,
    });

    if (createVenvExitCode !== 0) {
      return createVenvExitCode;
    }
  }

  const apiPython = resolveApiVenvPython();
  if (!apiPython) {
    console.error("[trustlayer] could not locate the API virtualenv python.");
    return 1;
  }

  console.log("[trustlayer] installing api dependencies...");
  const pipExitCode = runCommand(apiPython, ["-m", "pip", "install", "--upgrade", "pip"], {
    cwd: apiDir,
  });
  if (pipExitCode !== 0) {
    return pipExitCode;
  }

  return runCommand(apiPython, ["-m", "pip", "install", "-e", "."], {
    cwd: apiDir,
  });
}

let exitCode = 0;

if (target === "all" || target === "web") {
  exitCode = setupWeb();
}

if (exitCode === 0 && (target === "all" || target === "api")) {
  exitCode = setupApi();
}

if (exitCode === 0) {
  console.log(`[trustlayer] setup complete in ${repoRoot}`);
}

process.exit(exitCode);
