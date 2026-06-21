# Local Deploy MCP Coherence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `deploy-local-testing.ps1` release-mode produce and verify the runtime it actually ships — `rook` current in the release venv's site-packages, empty `PYTHONPATH`, `rhino_2d_to_3d_*` tools present — and stop bootstrapping `post_install.py` with the venv it recreates.

**Architecture:** Four edits, all in `scripts/deploy-local-testing.ps1`, release-mode only: (1) exclude the release venv from the post_install bootstrap interpreter, (2) reinstall the synced source into the release venv after the wheelhouse step, (3) drop the release source-PYTHONPATH shadow, (4) verify the real (site-packages, empty-PYTHONPATH) import path including the reconstruction tools. Dev modes and the shared installer are untouched.

**Tech Stack:** Windows PowerShell 5/7 script; Python 3.11 release venv; pip offline install; the rook MCP server (`rook.server.list_tools`).

## Global Constraints

- Edit **only** `scripts/deploy-local-testing.ps1`. Do NOT touch `installer/python_runtime_install.py`, `post_install.py`, the wheelhouse/lock validation, release installer packaging, or dev runtime modes (`-UseRepoVenv` / `-DevPythonRuntime` / the dev RuntimeContract).
- All behavior changes are **release-mode only** (`$RuntimeContract.IsDev -eq $false`). Dev keeps source-`PYTHONPATH` import.
- Reinstall step (#2) runs **after** `Sync-AppPayload` (source present in `…\app\mcp_server`) and **after** `Invoke-PostInstallConfig` (release venv exists). Ordering is load-bearing.
- Reinstall is `pip install --force-reinstall --no-deps --no-build-isolation --no-index "<InstallRoot>\mcp_server"`. **No fallback.** On failure throw verbatim:
  `Failed to install current mcp_server source into release venv. Local deploy must not fall back to PYTHONPATH=mcp_server\src; rebuild/fix the local Python packaging inputs.`
- Bootstrap exclusion compares **normalized, resolved, case-insensitive** paths (not naive string compare).
- Verification asserts **`rook.server.__file__`** under `…\venv\Lib\site-packages\rook` (the decisive proof) in addition to `rook.__file__`, plus `rhino_2d_to_3d_models` in `list_tools()`.
- No new dependencies. No C#/native/MCP-tool code.

**Key paths (defined at top of the script):**
- `$RuntimeRoot = %LOCALAPPDATA%\Rook`
- `$InstallRoot = %LOCALAPPDATA%\Rook\app`
- `$VenvPython  = $RuntimeRoot\venv\Scripts\python.exe` (the release venv interpreter)
- Release venv site-packages: `$RuntimeRoot\venv\Lib\site-packages\rook`
- Release source (pyproject root): `$InstallRoot\mcp_server`

**Reference:** spec at `docs/superpowers/specs/2026-06-21-deploy-local-mcp-coherence-design.md`.

---

## File Structure

- **Modify only** `scripts/deploy-local-testing.ps1`:
  - `Resolve-BootstrapPython` (≈183–217) — exclude `$VenvPython` (Task 1).
  - New `Install-ReleaseSourceIntoVenv` function + its call in the release branch (≈1182–1184) (Task 2).
  - `Resolve-DeployRuntimeContract` release block (≈295–296) — `$releasePythonPathEntries = @()` (Task 3).
  - `Test-EffectiveRuntime` (≈651–720) — release branch verification (Task 4).

Every task ends by confirming the whole script still parses, and commits. Task 5 is the end-to-end deploy validation.

**Parser check used after every edit** (cheap guard against syntax breakage). Run these lines directly in `pwsh` (not nested inside `-Command "…"`, to avoid quoting issues):
```powershell
$tokens = $null; $errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path scripts/deploy-local-testing.ps1).Path, [ref]$tokens, [ref]$errors) | Out-Null
if ($errors) { $errors | ForEach-Object { $_.Message }; 'PARSE FAILED' } else { 'PARSE OK' }
```
Expected: `PARSE OK`.

---

### Task 1: Exclude the release venv from the post_install bootstrap interpreter

**Files:**
- Modify: `scripts/deploy-local-testing.ps1` — `Resolve-BootstrapPython` (≈183–217)

**Interfaces:**
- Consumes: script-scoped `$VenvPython`.
- Produces: `Resolve-BootstrapPython` returns a resolved interpreter path that is **never** the release venv python; throws if none found.

- [ ] **Step 1: Replace the function body**

Find:
```powershell
function Resolve-BootstrapPython {
    $candidates = @()
    if (Test-Path $VenvPython) {
        $candidates += $VenvPython
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand -and $pythonCommand.Source -notlike '*WindowsApps*') {
        $candidates += $pythonCommand.Source
    }

    try {
        $pyOutput = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $pyOutput -and (Test-Path $pyOutput.Trim())) {
            $candidates += $pyOutput.Trim()
        }
    } catch { }

    $localAppData = [Environment]::GetFolderPath('LocalApplicationData')
    foreach ($minor in 14, 13, 12, 11, 10) {
        $candidate = Join-Path $localAppData "Programs\Python\Python3$minor\python.exe"
        if (Test-Path $candidate) {
            $candidates += $candidate
        }
    }

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }

    throw "Python 3.10+ was not found."
}
```

Replace with:
```powershell
function Resolve-BootstrapPython {
    # post_install.py recreates the rook release venv (shutil.rmtree in
    # _create_venv) whenever the runtime payload/lock changes. It must NOT be
    # bootstrapped with that same venv's interpreter, or it deletes the running
    # process mid-run -> silent exit 1, no traceback. Exclude $VenvPython by
    # normalized, resolved, case-insensitive path. Prefer system/bundled Python.
    $venvNormalized = $null
    if (Test-Path $VenvPython) {
        $venvNormalized = (Resolve-Path $VenvPython).Path.Replace('\', '/').ToLowerInvariant()
    }

    $candidates = @()

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand -and $pythonCommand.Source -notlike '*WindowsApps*') {
        $candidates += $pythonCommand.Source
    }

    try {
        $pyOutput = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $pyOutput -and (Test-Path $pyOutput.Trim())) {
            $candidates += $pyOutput.Trim()
        }
    } catch { }

    $localAppData = [Environment]::GetFolderPath('LocalApplicationData')
    foreach ($minor in 14, 13, 12, 11, 10) {
        $candidate = Join-Path $localAppData "Programs\Python\Python3$minor\python.exe"
        if (Test-Path $candidate) {
            $candidates += $candidate
        }
    }

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $resolved = (Resolve-Path $candidate).Path
            if ($venvNormalized -and ($resolved.Replace('\', '/').ToLowerInvariant() -eq $venvNormalized)) {
                continue  # never bootstrap with the venv post_install recreates
            }
            return $resolved
        }
    }

    throw "Python 3.10+ was not found for the post_install bootstrap (the release venv at $VenvPython is intentionally excluded because post_install recreates it; install a system Python 3.10+ or ensure 'py -3' resolves)."
}
```

- [ ] **Step 2: Confirm the script still parses**

Run the parser check (see File Structure).
Expected: `PARSE OK`.

- [ ] **Step 3: Confirm the exclusion logic by inspection**

The function can't be unit-tested in isolation (dot-sourcing the script executes the whole deploy), so confirm by reading the edited function: (a) `$candidates` no longer seeds `$VenvPython`, and (b) the return loop `continue`s when a candidate's normalized resolved path equals `$venvNormalized`. The runtime proof is Task 5, where the deploy log shows the chosen post_install bootstrap interpreter is **not** `…\Rook\venv\Scripts\python.exe`.

- [ ] **Step 4: Commit**

```bash
git add scripts/deploy-local-testing.ps1
git commit -m "fix(deploy): never bootstrap post_install with the release venv it recreates"
```

---

### Task 2: Mirror synced source into the release venv site-packages after post_install

**Why a directory mirror, not `pip install`:** `mcp_server/pyproject.toml` declares
the **hatchling** build backend, which the release venv does not carry. A
`pip install --no-build-isolation --no-index <source>` would therefore fail (no
backend, and offline can't fetch one). A directory mirror of the package is
deterministic, fully offline, and avoids build-backend/wheelhouse churn. Only the
`rook` package dir is mirrored; the wheelhouse `rook-*.dist-info` sibling is left
intact for metadata. Reuses the existing `Sync-Directory` (`robocopy /MIR`, which
excludes `__pycache__`/`*.pyc` and purges stale dest files).

**Files:**
- Modify: `scripts/deploy-local-testing.ps1` — add `Install-ReleaseSourceIntoVenv` (immediately after `Invoke-PostInstallConfig`); call it in the release branch of the main flow.

**Interfaces:**
- Consumes: script-scoped `$InstallRoot`, `$VenvPython`; helper `Sync-Directory`.
- Produces: `Install-ReleaseSourceIntoVenv` — mirrors `<InstallRoot>\mcp_server\src\rook` into `<venvRoot>\Lib\site-packages\rook` so the importable `rook` matches the synced source; throws clear preconditions if source/venv are missing.

- [ ] **Step 1: Add the function** (immediately after `Invoke-PostInstallConfig`)

```powershell
function Install-ReleaseSourceIntoVenv {
    # Local-deploy coherence: make the release venv's importable `rook` match the
    # just-synced source. Invoke-PostInstallConfig installs an older rook wheel
    # from the bundled wheelhouse, and the local deploy never rebuilds it, so
    # site-packages can lag the synced source (e.g. miss the rhino_2d_to_3d_*
    # tools). The real release MCP config runs with empty PYTHONPATH and imports
    # from site-packages, so site-packages must hold the current source.
    #
    # We MIRROR the package directory rather than pip-building from source:
    # mcp_server declares the hatchling build backend, which the release venv
    # does not carry, so `pip install --no-build-isolation --no-index` from
    # source would fail. A directory mirror is deterministic and fully offline.
    # Only the `rook` package dir is mirrored; the wheelhouse `rook-*.dist-info`
    # sibling is left intact for metadata. /MIR removes stale modules in the dest.
    $sourceRook = Join-Path $InstallRoot 'mcp_server\src\rook'
    $venvRoot = Split-Path -Parent (Split-Path -Parent $VenvPython)
    $destRook = Join-Path $venvRoot 'Lib\site-packages\rook'

    if (-not (Test-Path (Join-Path $sourceRook 'server.py'))) {
        throw "Release source mirror: rook package not found at $sourceRook (Sync-AppPayload must run first)."
    }
    if (-not (Test-Path $VenvPython)) {
        throw "Release source mirror: release venv python not found at $VenvPython (Invoke-PostInstallConfig must run first)."
    }

    Write-Host "Mirroring current rook source into the release venv site-packages (offline; robocopy /MIR)..."
    Write-Host "  source: $sourceRook"
    Write-Host "  dest:   $destRook"
    Sync-Directory $sourceRook $destRook
}
```

- [ ] **Step 2: Call it in the release branch**

Find:
```powershell
    Write-Step "Refresh MCP, Chirp, and config installs"
    Invoke-PostInstallConfig
    Write-ChatServiceManifests -Contract $RuntimeContract
```

Replace with:
```powershell
    Write-Step "Refresh MCP, Chirp, and config installs"
    Invoke-PostInstallConfig
    Write-Step "Mirror current source into release venv site-packages"
    Install-ReleaseSourceIntoVenv
    Write-ChatServiceManifests -Contract $RuntimeContract
```

(This block is the `else` of `if ($RuntimeContract.IsDev)`, so it is release-only by construction. `Sync-AppPayload` already ran at the "Sync installed AppData runtime payload" step above, so the source precondition holds.)

- [ ] **Step 3: Confirm the script still parses**

Run the parser check. Expected: `PARSE OK`.

- [ ] **Step 4: Dry-run the mirror (no changes)**

Prove the paths resolve and `/MIR` is sane against the live install (list-only):
```powershell
$src = "C:\Users\aryan\AppData\Local\Rook\app\mcp_server\src\rook"
$dst = "C:\Users\aryan\AppData\Local\Rook\venv\Lib\site-packages\rook"
& robocopy $src $dst /MIR /L /NJH /NJS /NP /XD __pycache__ /XF *.pyc | Out-Null
"robocopy /L exit: $LASTEXITCODE (0-7 = success)"
```
Expected: exit ≤ 7.

- [ ] **Step 5: Commit**

```bash
git add scripts/deploy-local-testing.ps1
git commit -m "fix(deploy): mirror rook source into release venv site-packages (hatchling-free, offline)"
```

---

### Task 3: Drop the release source-PYTHONPATH shadow

**Files:**
- Modify: `scripts/deploy-local-testing.ps1` — `Resolve-DeployRuntimeContract` release block (≈295–296)

**Interfaces:**
- Consumes: nothing new.
- Produces: the release RuntimeContract's `PythonPathEntries` is empty (`@()`), so its `Environment.PYTHONPATH` and the chat manifest's release `PYTHONPATH` are `''`, matching the written MCP config. Dev's `PythonPathEntries` is unchanged.

- [ ] **Step 1: Empty the release entries**

Find:
```powershell
    $releaseWorkingDirectory = Join-Path $InstallRoot 'mcp_server'
    $releasePythonPathEntries = @((Join-Path $InstallRoot 'mcp_server\src'))
```

Replace with:
```powershell
    $releaseWorkingDirectory = Join-Path $InstallRoot 'mcp_server'
    # Release imports rook from site-packages (Install-ReleaseSourceIntoVenv keeps
    # it current). Empty PYTHONPATH matches the written MCP config
    # (build_release_mcp_env sets PYTHONPATH="") and removes the source-tree
    # shadow that previously masked stale-wheel drift during verification.
    $releasePythonPathEntries = @()
```

- [ ] **Step 2: Confirm the script still parses**

Run the parser check. Expected: `PARSE OK`.

- [ ] **Step 3: Static anti-regression guard (no release `mcp_server\src` shadow)**

The important future failure is someone reintroducing the source shadow in release mode. Assert it's gone:
```
rg -n "releasePythonPathEntries\s*=" scripts/deploy-local-testing.ps1
rg -n "mcp_server.src" scripts/deploy-local-testing.ps1
```
Expected: the only `$releasePythonPathEntries =` assignment is `= @()`; and `mcp_server\src` / `mcp_server/src` appears **only** on the dev path (`$devSrcDir` / `$devPythonPathEntries`), never associated with `release`/`$releasePythonPathEntries`. If `mcp_server\src` ever appears in the release block again, this guard fails.

- [ ] **Step 4: Commit**

```bash
git add scripts/deploy-local-testing.ps1
git commit -m "fix(deploy): release PythonPathEntries empty to match the shipped empty-PYTHONPATH MCP config"
```

---

### Task 4: Verify the real path — site-packages, empty PYTHONPATH, reconstruction tools

**Files:**
- Modify: `scripts/deploy-local-testing.ps1` — `Test-EffectiveRuntime` (≈651–720)

**Interfaces:**
- Consumes: `$Contract.IsDev`, `$Contract.PythonPath`, `$Contract.WorkingDirectory`, `$Contract.PythonPathEntries` (release now empty → empty `PYTHONPATH`).
- Produces: in release mode, fails the deploy unless `rook.__file__` AND `rook.server.__file__` resolve under `…\venv\Lib\site-packages\rook` and `list_tools()` advertises the `rhino_2d_to_3d_*` family. Dev verification unchanged.

- [ ] **Step 1: Compute the expected prefix by mode and extend the check script**

Find this block inside `Test-EffectiveRuntime` (the `$expectedRookPrefix` assignment through the end of the here-string):
```powershell
        $expectedRookPrefix = Join-Path $Contract.WorkingDirectory 'src\rook'
        $check = @"
import json
from rook.runtime_paths import resolve_runtime_paths
import rook
paths = resolve_runtime_paths()
payload = {
    "rook_file": rook.__file__,
    "mode": paths.mode,
    "install_root": str(paths.install_root),
    "data_root": str(paths.data_root),
    "mcp_server_dir": str(paths.mcp_server_dir),
}
print(json.dumps(payload, sort_keys=True))
if paths.mode != "$($Contract.Mode)":
    raise SystemExit("ROOK_MODE did not resolve to $($Contract.Mode)")
if str(paths.install_root).replace("\\", "/").lower() != r"$($Contract.InstallRoot.Replace('\','/').ToLowerInvariant())":
    raise SystemExit("ROOK_INSTALL_ROOT mismatch")
if str(paths.data_root).replace("\\", "/").lower() != r"$($Contract.DataRoot.Replace('\','/').ToLowerInvariant())":
    raise SystemExit("ROOK_DATA_DIR mismatch")
expected_rook_prefix = r"$($expectedRookPrefix.Replace('\','/').ToLowerInvariant())"
actual_rook_file = str(rook.__file__).replace("\\", "/").lower()
if not actual_rook_file.startswith(expected_rook_prefix):
    raise SystemExit(f"rook imported from stale location: {rook.__file__}")
"@
```

Replace with:
```powershell
        if ($Contract.IsDev) {
            $expectedRookPrefix = Join-Path $Contract.WorkingDirectory 'src\rook'
        } else {
            # Release venv site-packages: <PythonPath>\..\..\Lib\site-packages\rook
            $venvRoot = Split-Path -Parent (Split-Path -Parent $Contract.PythonPath)
            $expectedRookPrefix = Join-Path $venvRoot 'Lib\site-packages\rook'
        }
        $requireTools = if ($Contract.IsDev) { 'False' } else { 'True' }
        $check = @"
import json
from rook.runtime_paths import resolve_runtime_paths
import rook
import rook.server
paths = resolve_runtime_paths()
payload = {
    "rook_file": rook.__file__,
    "rook_server_file": rook.server.__file__,
    "mode": paths.mode,
    "install_root": str(paths.install_root),
    "data_root": str(paths.data_root),
    "mcp_server_dir": str(paths.mcp_server_dir),
}
print(json.dumps(payload, sort_keys=True))
if paths.mode != "$($Contract.Mode)":
    raise SystemExit("ROOK_MODE did not resolve to $($Contract.Mode)")
if str(paths.install_root).replace("\\", "/").lower() != r"$($Contract.InstallRoot.Replace('\','/').ToLowerInvariant())":
    raise SystemExit("ROOK_INSTALL_ROOT mismatch")
if str(paths.data_root).replace("\\", "/").lower() != r"$($Contract.DataRoot.Replace('\','/').ToLowerInvariant())":
    raise SystemExit("ROOK_DATA_DIR mismatch")
expected_rook_prefix = r"$($expectedRookPrefix.Replace('\','/').ToLowerInvariant())"
actual_rook_file = str(rook.__file__).replace("\\", "/").lower()
actual_server_file = str(rook.server.__file__).replace("\\", "/").lower()
if not actual_rook_file.startswith(expected_rook_prefix):
    raise SystemExit(f"rook imported from stale location: {rook.__file__}")
if not actual_server_file.startswith(expected_rook_prefix):
    raise SystemExit(f"rook.server imported from stale location: {rook.server.__file__}")
if $($requireTools):
    import asyncio
    from rook.server import list_tools
    names = {t.name for t in asyncio.run(list_tools())}
    required = {
        "rhino_2d_to_3d_models",
        "rhino_2d_to_3d_submit",
        "rhino_2d_to_3d_status",
        "rhino_2d_to_3d_result",
        "rhino_2d_to_3d_import",
    }
    missing = sorted(required - names)
    if missing:
        raise SystemExit(f"release MCP missing reconstruction tools: {missing}")
"@
```

Notes:
- `$($requireTools)` interpolates to literal `True`/`False`, so the Python becomes `if True:` (release) or `if False:` (dev). Dev never imports the tool list.
- In release the env's `PYTHONPATH` is already empty (Task 3 → `PythonPathEntries = @()` → the existing `$env:PYTHONPATH = (@($Contract.PythonPathEntries) -join …)` yields `''`). No other change to the env-setup block.
- `rook.server.__file__` is the decisive assertion: the original failure was a stale `rook\server.py`.

- [ ] **Step 2: Confirm the script still parses**

Run the parser check. Expected: `PARSE OK`.

- [ ] **Step 3: Prove the new release check passes on the current good install**

The installed release venv was already corrected to current source, so the exact embedded Python check must pass with empty `PYTHONPATH`. Run:
```
$env:PYTHONPATH=""; & "C:\Users\aryan\AppData\Local\Rook\venv\Scripts\python.exe" -c "import asyncio, rook, rook.server; from rook.server import list_tools; names={t.name for t in asyncio.run(list_tools())}; req={'rhino_2d_to_3d_models','rhino_2d_to_3d_submit','rhino_2d_to_3d_status','rhino_2d_to_3d_result','rhino_2d_to_3d_import'}; miss=sorted(req-names); print('rook.server:', rook.server.__file__); print('missing:', miss); raise SystemExit(1 if (miss or 'site-packages' not in rook.server.__file__.replace(chr(92),'/').lower()) else 0)"
```
Expected: prints `rook.server: …\site-packages\rook\server.py`, `missing: []`, exit 0.
(If exit 1, the installed venv is stale or the tools aren't advertised — that is exactly the failure this guard is meant to catch; do not weaken the assertion.)

- [ ] **Step 4: Commit**

```bash
git add scripts/deploy-local-testing.ps1
git commit -m "fix(deploy): verify release runtime from site-packages with empty PYTHONPATH incl rhino_2d_to_3d tools"
```

---

### Task 5: End-to-end local release deploy validation

**Files:** none — validation only.

This is the load-bearing integration proof. It needs Rhino closed and all `python -m rook` stopped (the deploy refuses otherwise). Run by the user/executor who controls those processes; the agent must not silently kill the session's own MCP without intent.

- [ ] **Step 1: Stop blockers, run the deploy**

Ensure Rhino is closed and stop `python -m rook` processes. Ensure the VS Installer dir is on PATH (the native build batch calls bare `vswhere.exe`). Then:
```
cd C:\Users\aryan\source\repos\Rook\.worktrees\deploy-coherence
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -Configuration Release
```

- [ ] **Step 2: Confirm the four behaviors in the log**

Expected, in order:
1. The post_install bootstrap interpreter is **not** `…\Rook\venv\Scripts\python.exe` (Task 1) — post_install completes (no silent exit 1).
2. `Reinstall current source into release venv` step runs and the pip install succeeds (Task 2).
3. `Verify effective runtime` passes with the release check — no "stale location" / "missing reconstruction tools" SystemExit (Tasks 3+4).
4. No `post_install.py config refresh failed` and no unhandled exit 1.

- [ ] **Step 3: Independent confirmation (empty PYTHONPATH, from site-packages, tools listed)**

Run the Task 4 Step 3 one-liner again post-deploy. Expected: `rook.server: …\site-packages\rook\server.py`, `missing: []`, exit 0.

- [ ] **Step 4: No commit** — validation only. The branch is ready for PR after this.

---

## Notes for the PR

- Open a ready (non-draft) PR into `main`; preserve commit history (no squash unless approved); do not merge locally without review.
- This touches only the local dev deploy script; no MCP parity / C# suite runs apply. The proof is the Task 5 deploy + the empty-PYTHONPATH site-packages tool check.
- Expected commits: spec (2) → Task 1 → Task 2 → Task 3 → Task 4.
