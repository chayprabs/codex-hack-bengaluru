# Scripts

Local development helpers live here.

- `common.mjs` is the shared Node helper for root scripts
- `dev.mjs` is the cross-platform npm entrypoint
- `dev.py` is the shared runner implementation
- `dev.ps1` is the PowerShell wrapper
- `dev.sh` is the shell wrapper
- `setup.mjs` installs local dependencies for a fresh clone

From the repo root:

- `npm run setup` installs web deps and bootstraps the API virtualenv
- `npm run setup:web` installs only web dependencies
- `npm run setup:api` bootstraps only the API virtualenv
- `npm run dev` starts web and api together
- `npm run dev:web` starts only the web app
- `npm run dev:api` starts only the api
