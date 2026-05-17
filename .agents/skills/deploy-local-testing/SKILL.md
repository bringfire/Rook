---
name: deploy-local-testing
description: Use when the user asks to build and deploy locally, deploy local testing, update installed Rook for testing, sync the AppData runtime, or verify local Rook changes against the installed Rhino/MCP runtime.
---

# Deploy Local Testing

Use the repo script as the authority. Do not hand-roll a parallel deploy recipe.

## Command

From the Rook repo root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1
```

Useful variants:

```powershell
# Sync MCP/AppData payload only; allowed while Rhino/MCP are running.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning

# Copy existing build outputs without rebuilding.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -SkipBuild

# After a full deploy and Rhino restart, verify live Rhino, Grasshopper, and Chirp.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning -LiveSmoke
```

## Rules

- Default deploy must fail if Rhino or `python -m rook` is running.
- Default deploy syncs sibling `..\Chirp` into `%LOCALAPPDATA%\Rook\app\chirp` and refreshes the Chirp editable install.
- Never overwrite `%LOCALAPPDATA%\Rook\data`, logs, `.env`, venvs, caches, or local generated artifacts.
- Repo `knowledge` is bundled seed content only and syncs to `%LOCALAPPDATA%\Rook\app\knowledge`.
- Runtime mutable knowledge remains `%LOCALAPPDATA%\Rook\data`.
- Do not claim live plugin capability unless `-LiveSmoke` passes; normal deploy verifies install paths/imports only.
- Full installer deploy is release validation, not the default local testing path.

## Reporting

Report the script result, the installed runtime path, the installed Chirp path, whether native/managed builds ran, whether Chirp was installed, whether live smoke ran, and any blocked running processes.
