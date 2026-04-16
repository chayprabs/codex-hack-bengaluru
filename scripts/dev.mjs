#!/usr/bin/env node

import { runPythonScript } from "./common.mjs";

const exitCode = runPythonScript("dev.py", process.argv.slice(2));
process.exit(exitCode);
