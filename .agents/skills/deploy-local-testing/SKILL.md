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

# Rebuild/copy/register only the native Rhino plugin; leaves MCP/Chirp/config untouched.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -NativeOnly

# Fast native route iteration after a successful native build; still requires Rhino closed.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -NativeOnly -SkipBuild

# Copy existing build outputs without rebuilding.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -SkipBuild

# After a full deploy and Rhino restart, verify live Rhino, Grasshopper, and Chirp.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning -LiveSmoke
```

## Rules

- Default deploy must fail if Rhino or `python -m rook` is running.
- `-NativeOnly` must fail if Rhino is running, but must not inspect, kill, block on, sync, or reconfigure running `python -m rook` MCP processes.
- `-NativeOnly` is for native route/plugin iteration only: it copies/registers the native payload and preserves existing companion/MCP paths from a prior full deploy.
- Default deploy syncs sibling `..\Chirp` into `%LOCALAPPDATA%\Rook\app\chirp` and refreshes the Chirp editable install.
- Never overwrite `%LOCALAPPDATA%\Rook\data`, logs, `.env`, venvs, caches, or local generated artifacts.
- Repo `knowledge` is bundled seed content only and syncs to `%LOCALAPPDATA%\Rook\app\knowledge`.
- Runtime mutable knowledge remains `%LOCALAPPDATA%\Rook\data`.
- Do not claim live plugin capability unless `-LiveSmoke` passes; normal deploy verifies install paths/imports only.
- Full installer deploy is release validation, not the default local testing path.

## Release-Readiness Proof

For the stronger proof path, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate-local-testing-stack.ps1 -ReleaseReadiness
```

Only `scripts\validate-local-testing-stack.ps1 -ReleaseReadiness` may justify the phrase release-readiness proven. The ordinary deploy script can verify installed runtime and can run a developer-open live smoke, but it does not prove clean startup or owned-process routing.

Use `-KeepRhinoOnFailure` only when the user explicitly wants to preserve the owned Rhino process for diagnostics.

## Reporting

Report the script result, the installed runtime path, the installed Chirp path, whether native/managed builds ran, whether Chirp was installed, whether live smoke ran, and any blocked running processes.
