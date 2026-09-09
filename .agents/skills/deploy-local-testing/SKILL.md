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

Full deploy builds the optional RookBIM module so the installed net48
Rhino.Inside/Revit payload receives the current `RookBim.dll`. That build
requires Revit API assemblies. If Revit is not installed under the default
`%ProgramFiles%\Autodesk\Revit 2024`, pass `-RevitInstallDir`.

Useful variants:

```powershell
# C#/embedded UI iteration on an existing installation; Rhino must be closed.
# Builds Rook only, without restore, then verifies/copies the companion bytes.
pwsh -NoProfile -File scripts\deploy-local-testing.ps1 -ManagedOnly

# Full deploy with a non-default Revit API location for RookBIM.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -RevitInstallDir "C:\Program Files\Autodesk\Revit 2025"

# Sync MCP/AppData payload only; allowed while Rhino/MCP are running.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning

# Rebuild/copy/register only the native Rhino plugin; leaves MCP/Chirp/config untouched.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -NativeOnly

# Fast native route iteration after a successful native build; still requires Rhino closed.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -NativeOnly -SkipBuild

# Copy existing build outputs without rebuilding.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -SkipBuild

# Dev chat/runtime iteration: use the repo MCP venv and write dev manifests.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -UseRepoVenv

# Enable checkout-backed Python iteration without building any plugins.
# Close Rhino/Rook MCP normally first; no AllowRunning or live-smoke bypass.
pwsh -NoProfile -File scripts\deploy-local-testing.ps1 -PayloadOnly -UseRepoVenv

# Dev chat/runtime iteration with an explicit venv path.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -DevPythonRuntime "C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe"

# After a full deploy and Rhino restart, verify live Rhino, Grasshopper, and Chirp.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning -LiveSmoke

# Dev runtime live smoke after a -UseRepoVenv deploy and Rhino/Grasshopper restart.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning -UseRepoVenv -LiveSmoke
```

## Rules

- `-ManagedOnly` builds only Rook (all three target frameworks), suppresses automatic MSBuild deployment, and replaces only `Rook.rhp` plus available `Rook.pdb` files. `-SkipBuild` uses existing outputs. It checks Rhino before building and again before copying; it does not check or terminate MCP processes.
- Managed-only requires a prior complete installation and byte-identical supporting DLLs, runtime assets and dependency metadata. Dependency changes require the full workflow; there is no fallback. Native, BIM, Python, Prime, Chirp, client configuration, chat manifests and registration remain untouched. Use it only for C#/embedded-resource changes compatible with the installed Python/native contracts.
- Managed-only reports built-to-installed SHA-256 comparisons, not a new whole-product identity or release qualification. It cannot be combined with other deployment/runtime/live-smoke modes. Obtain deployment approval and close Rhino normally before execution.
- Default deploy must fail if Rhino or `python -m rook` is running.
- Default deploy intentionally requires Revit API assemblies for the RookBIM build; Rhino-only native iteration should use `-NativeOnly`, and payload-only sync after a previous build should use `-PayloadOnly -AllowRunning`.
- `-NativeOnly` must fail if Rhino is running, but must not inspect, kill, block on, sync, or reconfigure running `python -m rook` MCP processes.
- `-NativeOnly` is for native route/plugin iteration only: it copies/registers the native payload and preserves existing companion/MCP paths from a prior full deploy.
- `-UseRepoVenv` and `-DevPythonRuntime` are explicit dev-runtime modes; they must never be inferred from a missing release private runtime.
- For Python-only iteration, use `-PayloadOnly -UseRepoVenv` once to point the panel at this checkout's existing Python environment and `mcp_server/src`. Working directory and project root stay in the checkout; `ROOK_INSTALL_ROOT`, Prime's `current.json`/runtimes, persistent ACP data and installed Chirp remain at their installed locations. No Prime copy or rebuild is needed.
- That dev setup still runs the existing AppData/Chirp source sync and writes chat manifests, but skips plugin builds/copies, sealed wheelhouse admission, release Python recreation and release client-config refresh. It does not install missing Python dependencies. Thereafter Python-only edits need a new chat-service process (close/reopen Rhino normally), not another deployment. Dependency changes still need explicit environment maintenance.
- Dev mode is local testing, not qualification of the installed release Python bytes. External MCP client configurations are not switched to the dev interpreter by this command. Keep the installed runtime and preserved qualification evidence unchanged; do not claim that checkout-backed testing requalifies the release.
- Release deploy without a dev-runtime flag still runs `post_install.py` and must fail loudly when the bundled release Python runtime is missing.
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
