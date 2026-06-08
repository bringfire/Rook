# Bundled Python Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a public Rook installer that ships private CPython plus an offline wheelhouse, installs Rook MCP/chat and Chirp without user Python or network dependency resolution, and validates exact runtime provenance.

**Architecture:** Add a release-only Python payload staging pipeline that packages a pinned Python NuGet runtime, non-editable Rook/Chirp wheels, two hash-locked requirements files, and a runtime manifest. Post-install creates two venvs from private Python, installs only from the bundled wheelhouse, writes install-state evidence, and generates release configs that point at the private Rook venv while preserving `CHIRP_HOME\.venv`.

**Tech Stack:** PowerShell release scripts and guard tests, Inno Setup, CPython 3.11.9 NuGet runtime, pip wheelhouse/hash mode, Python stdlib post-install helpers, pytest, Rook C# chat service manifest handling.

---

## Pre-Execution Notes

The worktree currently contains unrelated uncommitted installer timeout work:

- `installer/RookSetup.iss`
- `installer/post_install.py`
- `scripts/tests/release-installer-guards.tests.ps1`
- `mcp_server/tests/test_post_install.py`

Before executing this plan, complete Task 0 and run Tasks 1 through 12 from a clean bundled-Python worktree. Do not mix those timeout changes into the bundled Python commits unless the user explicitly asks to combine them.

The approved design spec is:

```text
docs/superpowers/specs/2026-06-08-bundled-python-installer-design.md
```

## File Structure

Create:

- `installer/python-runtime/python-runtime.json`  
  Pinned Python NuGet runtime input. Contains `schema_version`, exact Python version, ABI/platform identity, package name, and expected `.nupkg` SHA256.

- `scripts/python-runtime/stage-rook-python-runtime.ps1`  
  Downloads the pinned Python NuGet package during release build, verifies its SHA256, extracts `tools\`, verifies `python.exe`, and writes runtime staging evidence.

- `scripts/python-runtime/build-rook-python-wheelhouse.ps1`  
  Builds non-editable `rook-mcp` and `chirp` wheels, creates two hash-locked requirements files, builds one union wheelhouse, rejects source distributions, temp-installs from the wheelhouse, runs `pip check`, runs import-origin checks, records package license/provenance metadata, and writes `python-runtime-manifest.json`.

- `installer/python_runtime_install.py`  
  Stdlib-only install-time runtime manager imported by `post_install.py`. Handles private runtime discovery, venv invalidation, sanitized environment, offline pip install, `pip check`, import-origin validation, install-state writing, and command/output evidence.

- `mcp_server/tests/test_python_runtime_install.py`  
  Unit tests for `installer/python_runtime_install.py`.

- `scripts/tests/python-runtime-packaging.tests.ps1`  
  PowerShell guard tests for runtime metadata, release scripts, wheelhouse rules, manifest schema, source provenance, and sdist rejection.

Modify:

- `installer/post_install.py`  
  Replace public install dependency install flow with private runtime manager calls. Keep uninstall cleanup and existing Claude/Codex config writer behavior, but feed them private Rook venv Python and release-mode source-path policy.

- `installer/RookSetup.iss`  
  Package staged runtime, wheelhouse, lockfiles, manifest, and helper module. Remove public/full MCP/Chirp user-Python prerequisite and install-time Python discovery path.

- `mcp_server/pyproject.toml`  
  Move `pytesseract` out of default dependencies into an optional `ocr` extra.

- `src/Rook/UI/Chat/ChatServiceManager.cs`  
  Gate PATH Python fallback behind an explicit support/dev override such as `ROOK_ALLOW_USER_PYTHON_DISCOVERY=1`. Release manifest/config should remain authoritative.

- `scripts/validate-release-artifacts.ps1`  
  Require Python runtime manifest and installed smoke evidence, including private Python path/version, `rook.__file__`, `chirp.__file__`, `pip check`, config identity, no-index/local-wheelhouse evidence, and Chirp source identity.

- `scripts/tests/release-installer-guards.tests.ps1`  
  Add release guard coverage for no user-Python prerequisite, no editable installs, runtime/wheelhouse packaging, no release `PYTHONPATH` source roots, source distribution rejection, and doc synchronization.

- `.agents/skills/build-release/SKILL.md` and `.claude/skills/build-release/SKILL.md`  
  Insert the Python payload staging stage after exact release SHA checkout and before `.iss` source verification.

- `.agents/skills/build-release/references/iss-source-paths.md` and `.claude/skills/build-release/references/iss-source-paths.md`  
  Add staged Python runtime, wheelhouse, lockfiles, manifest, and helper module to the source checklist.

---

### Task 0: Prepare Clean Worktree For Bundled Python Execution

**Files:** None

- [ ] **Step 1: Confirm the current workspace contains unrelated timeout work**

Run from `C:\Users\aryan\source\repos\Rook`:

```powershell
git status --short
```

Expected: output may include only the unrelated timeout files already listed in the pre-execution notes. Do not stage those files for this plan.

- [ ] **Step 2: Create and enter a clean worktree for this plan**

Run:

```powershell
git worktree add ..\Rook-bundled-python -b codex/bundled-python-installer HEAD
cd ..\Rook-bundled-python
git status --short
```

Expected: `git status --short` prints no files. If it prints any files, stop and resolve the worktree before Task 1.

- [ ] **Step 3: Treat the clean worktree as the execution root**

All Task 1 through Task 12 commands in this plan assume the working directory is:

```text
C:\Users\aryan\source\repos\Rook-bundled-python
```

Task commits must be made from this clean worktree. The original `C:\Users\aryan\source\repos\Rook` workspace remains available for the separate timeout work.

---

### Task 1: Add Python Runtime Metadata And Stager Guards

**Files:**
- Create: `installer/python-runtime/python-runtime.json`
- Create: `scripts/tests/python-runtime-packaging.tests.ps1`

- [ ] **Step 1: Write the failing guard tests**

Create `scripts/tests/python-runtime-packaging.tests.ps1` with:

```powershell
$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$RuntimeConfigPath = Join-Path $RepoRoot 'installer\python-runtime\python-runtime.json'
$RuntimeStager = Join-Path $RepoRoot 'scripts\python-runtime\stage-rook-python-runtime.ps1'
$WheelhouseBuilder = Join-Path $RepoRoot 'scripts\python-runtime\build-rook-python-wheelhouse.ps1'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Assert-Contains {
    param([string]$Text, [string]$Expected, [string]$Message)
    Assert-True -Condition $Text.Contains($Expected) -Message $Message
}

function Test-PythonRuntimeConfigIsPinned {
    Assert-True -Condition (Test-Path $RuntimeConfigPath) -Message "Missing runtime config: $RuntimeConfigPath"
    $config = Get-Content -Path $RuntimeConfigPath -Raw | ConvertFrom-Json
    Assert-True -Condition ($config.schema_version -eq 1) -Message 'Runtime config must declare schema_version 1.'
    Assert-True -Condition ($config.python_nuget_package -eq 'python') -Message 'Runtime config must use the official python NuGet package.'
    Assert-True -Condition ($config.python_version -eq '3.11.9') -Message 'Runtime config must pin exact Python version 3.11.9 for this release.'
    Assert-True -Condition ($config.python_abi -eq 'cp311') -Message 'Runtime config must record cp311 ABI.'
    Assert-True -Condition ($config.target_platform -eq 'win_amd64') -Message 'Runtime config must target win_amd64.'
    Assert-True -Condition ($config.nupkg_sha256 -match '^[A-F0-9]{64}$') -Message 'Runtime config must contain an uppercase SHA256 for the nupkg.'
}

function Test-PythonRuntimeStagerExistsAndNeverRunsAtInstallTime {
    Assert-True -Condition (Test-Path $RuntimeStager) -Message "Missing runtime stager: $RuntimeStager"
    $content = Get-Content -Path $RuntimeStager -Raw
    Assert-Contains -Text $content -Expected 'installer\python-runtime\python-runtime.json' -Message 'Stager must read the pinned runtime config.'
    Assert-Contains -Text $content -Expected 'Get-FileHash' -Message 'Stager must verify the nupkg hash.'
    Assert-Contains -Text $content -Expected 'Expand-Archive' -Message 'Stager must extract the NuGet package.'
    Assert-Contains -Text $content -Expected 'tools\python.exe' -Message 'Stager must stage the NuGet tools python.exe layout.'
}

function Test-WheelhouseBuilderExists {
    Assert-True -Condition (Test-Path $WheelhouseBuilder) -Message "Missing wheelhouse builder: $WheelhouseBuilder"
}

Test-PythonRuntimeConfigIsPinned
Test-PythonRuntimeStagerExistsAndNeverRunsAtInstallTime
Test-WheelhouseBuilderExists

Write-Host 'Python runtime packaging guard tests passed.'
```

- [ ] **Step 2: Run the guard test and verify it fails**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\python-runtime-packaging.tests.ps1
```

Expected: FAIL because `installer\python-runtime\python-runtime.json` and the staging scripts do not exist.

- [ ] **Step 3: Add the pinned runtime metadata**

Create `installer/python-runtime/python-runtime.json`:

```json
{
  "schema_version": 1,
  "python_nuget_package": "python",
  "python_version": "3.11.9",
  "nupkg_sha256": "9283876D58C017E0E846F95B490DA3BCA0FC0A6EE1134B2870677CFB7EEC3C67",
  "target_platform": "win_amd64",
  "python_abi": "cp311",
  "expected_executable": "tools\\python.exe"
}
```

This SHA256 was verified against `https://www.nuget.org/api/v2/package/python/3.11.9` during planning.

- [ ] **Step 4: Add stager script skeleton**

Create `scripts/python-runtime/stage-rook-python-runtime.ps1`:

```powershell
param(
    [string]$RepoRoot = '',
    [string]$RuntimeConfigPath = '',
    [string]$OutputRoot = '',
    [string]$DownloadRoot = ''
)

$ErrorActionPreference = 'Stop'

function Fail {
    param([string]$Message)
    throw "Python runtime staging failed: $Message"
}

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}
if ([string]::IsNullOrWhiteSpace($RuntimeConfigPath)) {
    $RuntimeConfigPath = Join-Path $RepoRoot 'installer\python-runtime\python-runtime.json'
}
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $RepoRoot 'installer\runtime\python'
}
if ([string]::IsNullOrWhiteSpace($DownloadRoot)) {
    $DownloadRoot = Join-Path $RepoRoot 'artifacts\python-runtime'
}

if (-not (Test-Path -LiteralPath $RuntimeConfigPath -PathType Leaf)) {
    Fail "runtime config missing: $RuntimeConfigPath"
}

$config = Get-Content -LiteralPath $RuntimeConfigPath -Raw | ConvertFrom-Json
if ($config.schema_version -ne 1) { Fail 'runtime config schema_version must be 1' }
if ($config.python_nuget_package -ne 'python') { Fail 'only the official python NuGet package is supported' }
if ($config.python_version -ne '3.11.9') { Fail 'python_version must be pinned to 3.11.9 for this release' }
if ($config.nupkg_sha256 -notmatch '^[A-F0-9]{64}$') { Fail 'nupkg_sha256 must be uppercase SHA256 hex' }

New-Item -ItemType Directory -Force -Path $DownloadRoot | Out-Null
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$nupkgName = "$($config.python_nuget_package).$($config.python_version).nupkg"
$nupkgPath = Join-Path $DownloadRoot $nupkgName
$downloadUrl = "https://www.nuget.org/api/v2/package/$($config.python_nuget_package)/$($config.python_version)"

if (-not (Test-Path -LiteralPath $nupkgPath -PathType Leaf)) {
    Invoke-WebRequest -Uri $downloadUrl -OutFile $nupkgPath
}

$actualHash = (Get-FileHash -LiteralPath $nupkgPath -Algorithm SHA256).Hash.ToUpperInvariant()
if ($actualHash -ne $config.nupkg_sha256) {
    Fail "nupkg hash mismatch. Expected $($config.nupkg_sha256), actual $actualHash"
}

$extractRoot = Join-Path $DownloadRoot "extract-$($config.python_version)"
if (Test-Path -LiteralPath $extractRoot) {
    Remove-Item -LiteralPath $extractRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
Expand-Archive -LiteralPath $nupkgPath -DestinationPath $extractRoot -Force

$toolsRoot = Join-Path $extractRoot 'tools'
$pythonExe = Join-Path $toolsRoot 'python.exe'
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    Fail "NuGet tools\python.exe missing after extraction"
}

$stagedRoot = Join-Path $OutputRoot "cpython-$($config.python_version)"
if (Test-Path -LiteralPath $stagedRoot) {
    Remove-Item -LiteralPath $stagedRoot -Recurse -Force
}
Copy-Item -LiteralPath $toolsRoot -Destination $stagedRoot -Recurse

$stagedPython = Join-Path $stagedRoot 'python.exe'
$versionOutput = (& $stagedPython -V 2>&1) -join ''
if ($LASTEXITCODE -ne 0 -or $versionOutput -notmatch [regex]::Escape($config.python_version)) {
    Fail "staged python version check failed: $versionOutput"
}

$tempVenv = Join-Path $DownloadRoot 'venv-check'
if (Test-Path -LiteralPath $tempVenv) {
    Remove-Item -LiteralPath $tempVenv -Recurse -Force
}
& $stagedPython -m venv $tempVenv
if ($LASTEXITCODE -ne 0) { Fail 'python -m venv failed for staged runtime' }

$tempVenvPython = Join-Path $tempVenv 'Scripts\python.exe'
$pipOutput = (& $tempVenvPython -m pip --version 2>&1) -join ''
if ($LASTEXITCODE -ne 0 -or $pipOutput -notmatch 'pip') {
    Fail "temp venv pip check failed: $pipOutput"
}

Write-Host "Staged Python runtime: $stagedRoot"
```

- [ ] **Step 5: Add fail-closed wheelhouse builder stub**

Create `scripts/python-runtime/build-rook-python-wheelhouse.ps1`:

```powershell
param(
    [string]$Version = '1.5.10'
)

$ErrorActionPreference = 'Stop'
throw "Wheelhouse builder is not implemented yet. Execute Task 2 before using this release path. Version: $Version"
```

- [ ] **Step 6: Run guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\python-runtime-packaging.tests.ps1
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add installer\python-runtime\python-runtime.json scripts\python-runtime\stage-rook-python-runtime.ps1 scripts\python-runtime\build-rook-python-wheelhouse.ps1 scripts\tests\python-runtime-packaging.tests.ps1
git commit -m "build: add pinned python runtime staging inputs"
```

---

### Task 2: Build Wheelhouse Script With Provenance And Wheel-Only Guards

**Files:**
- Modify: `scripts/python-runtime/build-rook-python-wheelhouse.ps1`
- Modify: `scripts/tests/python-runtime-packaging.tests.ps1`

- [ ] **Step 1: Add failing guard coverage for wheelhouse rules**

Append these tests to `scripts/tests/python-runtime-packaging.tests.ps1` before the final `Write-Host`:

```powershell
function Test-WheelhouseBuilderEnforcesReleaseContracts {
    $content = Get-Content -Path $WheelhouseBuilder -Raw
    Assert-Contains -Text $content -Expected 'pip wheel' -Message 'Wheelhouse builder must build wheels, not editable installs.'
    Assert-Contains -Text $content -Expected 'pip download' -Message 'Wheelhouse builder must collect dependency wheels.'
    Assert-Contains -Text $content -Expected '--only-binary=:all:' -Message 'Wheelhouse builder must reject sdists for public wheelhouse inputs.'
    Assert-Contains -Text $content -Expected 'pip check' -Message 'Wheelhouse builder must run pip check.'
    Assert-Contains -Text $content -Expected 'pip-audit' -Message 'Wheelhouse builder must run pip-audit against temp installed venvs.'
    Assert-Contains -Text $content -Expected 'pip-audit==2.10.0' -Message 'Wheelhouse builder must pin pip-audit tooling for reproducible release gates.'
    Assert-Contains -Text $content -Expected 'packaging.tags' -Message 'Wheelhouse builder must validate wheel tags against interpreter accepted tags.'
    Assert-Contains -Text $content -Expected 'rook.__file__' -Message 'Wheelhouse builder must record rook import origin evidence.'
    Assert-Contains -Text $content -Expected 'chirp.__file__' -Message 'Wheelhouse builder must record chirp import origin evidence.'
    Assert-Contains -Text $content -Expected 'cv2' -Message 'Wheelhouse builder must run shipped vision stack import smokes.'
    Assert-Contains -Text $content -Expected 'license_provenance' -Message 'Runtime manifest must include Python and third-party package license/provenance evidence.'
    Assert-Contains -Text $content -Expected 'License-Expression' -Message 'Wheel provenance collector must inspect modern wheel license metadata.'
    Assert-Contains -Text $content -Expected 'chirp_git_sha' -Message 'Manifest must include Chirp sibling repo git SHA.'
    Assert-Contains -Text $content -Expected 'chirp_source_archive_sha256' -Message 'Manifest must include Chirp source archive hash.'
    Assert-Contains -Text $content -Expected 'python-runtime-manifest.json' -Message 'Wheelhouse builder must write the runtime manifest.'
}

Test-WheelhouseBuilderEnforcesReleaseContracts
```

- [ ] **Step 2: Run the guard test and verify it fails**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\python-runtime-packaging.tests.ps1
```

Expected: FAIL because the wheelhouse builder is still the fail-closed stub.

- [ ] **Step 3: Implement the wheelhouse builder**

Replace `scripts/python-runtime/build-rook-python-wheelhouse.ps1` with:

```powershell
param(
    [string]$Version = '1.5.10',
    [string]$RepoRoot = '',
    [string]$ChirpRoot = '',
    [string]$RuntimeRoot = '',
    [string]$OutputRoot = '',
    [string]$BuildRoot = ''
)

$ErrorActionPreference = 'Stop'

function Fail {
    param([string]$Message)
    throw "Rook Python wheelhouse build failed: $Message"
}

function Require-CleanGitRepo {
    param([string]$Root, [string]$Label)
    $head = ((& git -C $Root rev-parse HEAD 2>$null) -join '').Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-f]{40}$') {
        Fail "Could not resolve $Label git SHA"
    }
    $dirty = (& git -C $Root status --porcelain)
    if ($dirty) {
        $dirty | ForEach-Object { Write-Host $_ }
        Fail "$Label worktree is dirty"
    }
    return $head
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function New-SourceArchive {
    param([string]$Root, [string]$GitSha, [string]$OutPath)
    $parent = Split-Path -Parent $OutPath
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $tarBytes = & git -C $Root archive --format=tar $GitSha 2>$null
    if ($LASTEXITCODE -ne 0) { Fail "git archive failed for $Root" }
    [IO.File]::WriteAllBytes($OutPath, $tarBytes)
    return Get-Sha256 -Path $OutPath
}

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}
if ([string]::IsNullOrWhiteSpace($ChirpRoot)) {
    $ChirpRoot = Join-Path (Split-Path -Parent $RepoRoot) 'Chirp'
}
if ([string]::IsNullOrWhiteSpace($RuntimeRoot)) {
    $RuntimeRoot = Join-Path $RepoRoot 'installer\runtime\python\cpython-3.11.9'
}
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $RepoRoot 'installer\runtime'
}
if ([string]::IsNullOrWhiteSpace($BuildRoot)) {
    $BuildRoot = Join-Path $RepoRoot 'artifacts\python-wheelhouse'
}

$pythonExe = Join-Path $RuntimeRoot 'python.exe'
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    Fail "Private Python runtime missing. Run scripts\python-runtime\stage-rook-python-runtime.ps1 first: $pythonExe"
}
if (-not (Test-Path -LiteralPath (Join-Path $ChirpRoot 'pyproject.toml') -PathType Leaf)) {
    Fail "Chirp sibling repo missing: $ChirpRoot"
}
$runtimeConfigPath = Join-Path $RepoRoot 'installer\python-runtime\python-runtime.json'
if (-not (Test-Path -LiteralPath $runtimeConfigPath -PathType Leaf)) {
    Fail "Runtime config missing: $runtimeConfigPath"
}
$runtimeConfig = Get-Content -LiteralPath $runtimeConfigPath -Raw | ConvertFrom-Json

$rookGitSha = Require-CleanGitRepo -Root $RepoRoot -Label 'Rook'
$chirpGitSha = Require-CleanGitRepo -Root $ChirpRoot -Label 'Chirp'

if (Test-Path -LiteralPath $BuildRoot) { Remove-Item -LiteralPath $BuildRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
$wheelhouse = Join-Path $OutputRoot 'python-wheelhouse'
if (Test-Path -LiteralPath $wheelhouse) { Remove-Item -LiteralPath $wheelhouse -Recurse -Force }
New-Item -ItemType Directory -Force -Path $wheelhouse | Out-Null

$rookWheelDir = Join-Path $BuildRoot 'rook-wheel'
$chirpWheelDir = Join-Path $BuildRoot 'chirp-wheel'
New-Item -ItemType Directory -Force -Path $rookWheelDir,$chirpWheelDir | Out-Null

& $pythonExe -m pip wheel --no-deps --wheel-dir $rookWheelDir (Join-Path $RepoRoot 'mcp_server')
if ($LASTEXITCODE -ne 0) { Fail 'rook-mcp wheel build failed' }
& $pythonExe -m pip wheel --no-deps --wheel-dir $chirpWheelDir $ChirpRoot
if ($LASTEXITCODE -ne 0) { Fail 'chirp wheel build failed' }

$rookWheel = Get-ChildItem -Path $rookWheelDir -Filter 'rook_mcp-*.whl' | Select-Object -First 1
if (-not $rookWheel) { Fail 'rook-mcp wheel was not produced' }
$chirpWheel = Get-ChildItem -Path $chirpWheelDir -Filter 'chirp-*.whl' | Select-Object -First 1
if (-not $chirpWheel) { Fail 'chirp wheel was not produced' }

Copy-Item -LiteralPath $rookWheel.FullName -Destination $wheelhouse
Copy-Item -LiteralPath $chirpWheel.FullName -Destination $wheelhouse

& $pythonExe -m pip download --dest $wheelhouse --only-binary=:all: --implementation cp --python-version 3.11 --abi cp311 --platform win_amd64 $rookWheel.FullName $chirpWheel.FullName
if ($LASTEXITCODE -ne 0) { Fail 'dependency wheel download failed' }

$sdists = @(Get-ChildItem -Path $wheelhouse -Include *.tar.gz,*.zip -File -Recurse)
if ($sdists.Count -gt 0) {
    $sdists | ForEach-Object { Write-Host "Source distribution rejected: $($_.FullName)" }
    Fail 'source distributions are not allowed in the public installer wheelhouse'
}

$lockRook = Join-Path $OutputRoot 'requirements-rook-lock.txt'
$lockChirp = Join-Path $OutputRoot 'requirements-chirp-lock.txt'
$lockScript = Join-Path $BuildRoot 'generate_hash_lock.py'
@'
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

from pip._vendor.packaging import tags as packaging_tags
from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename


def run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(result.stdout + result.stderr)
    return result.stdout


def wheel_index(wheelhouse: Path) -> dict[tuple[str, str], tuple[Path, str]]:
    index: dict[tuple[str, str], tuple[Path, str]] = {}
    for wheel in sorted(wheelhouse.glob("*.whl")):
        name, version, _build, _tags = parse_wheel_filename(wheel.name)
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        index[(canonicalize_name(name), str(version))] = (wheel, digest)
    return index


def freeze_env(python: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    output = run([str(python), "-m", "pip", "freeze", "--all", "--exclude-editable"])
    for line in output.splitlines():
        if "==" not in line:
            continue
        name, version = line.split("==", 1)
        canonical = canonicalize_name(name)
        if canonical in {"pip", "setuptools", "wheel"}:
            continue
        rows.append((canonical, version))
    return sorted(rows)


def write_lock(rows: list[tuple[str, str]], index: dict[tuple[str, str], tuple[Path, str]], output: Path) -> None:
    lines = [
        "# Generated by scripts/python-runtime/build-rook-python-wheelhouse.ps1",
        "# Install with --isolated --no-index --find-links python-wheelhouse --require-hashes",
    ]
    missing: list[str] = []
    for name, version in rows:
        key = (canonicalize_name(name), version)
        if key not in index:
            missing.append(f"{name}=={version}")
            continue
        _wheel, digest = index[key]
        lines.append(f"{name}=={version} --hash=sha256:{digest}")
    if missing:
        raise SystemExit("missing wheels for locked packages: " + ", ".join(missing))
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-python", required=True)
    parser.add_argument("--wheelhouse", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()

    base_python = Path(args.base_python)
    wheelhouse = Path(args.wheelhouse)
    work_dir = Path(args.work_dir)
    venv_dir = work_dir / ("venv-" + args.package.replace("-", "_"))
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    run([str(base_python), "-m", "venv", str(venv_dir)])
    venv_python = venv_dir / "Scripts" / "python.exe"
    run([
        str(venv_python),
        "-m",
        "pip",
        "--isolated",
        "install",
        "--no-index",
        "--find-links",
        str(wheelhouse),
        args.package,
    ])
    rows = freeze_env(venv_python)
    index = wheel_index(wheelhouse)
    write_lock(rows, index, Path(args.output))
    run([
        str(venv_python),
        "-m",
        "pip",
        "--isolated",
        "install",
        "--force-reinstall",
        "--no-index",
        "--find-links",
        str(wheelhouse),
        "--require-hashes",
        "-r",
        str(Path(args.output)),
    ])
    run([str(venv_python), "-m", "pip", "check"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -LiteralPath $lockScript -Encoding UTF8

& $pythonExe $lockScript --base-python $pythonExe --wheelhouse $wheelhouse --package "rook-mcp==$Version" --output $lockRook --work-dir $BuildRoot
if ($LASTEXITCODE -ne 0) { Fail 'Rook hash lock generation failed' }
& $pythonExe $lockScript --base-python $pythonExe --wheelhouse $wheelhouse --package 'chirp==0.1.0' --output $lockChirp --work-dir $BuildRoot
if ($LASTEXITCODE -ne 0) { Fail 'Chirp hash lock generation failed' }

$verificationScript = Join-Path $BuildRoot 'verify_temp_runtime_install.py'
@'
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sysconfig
from pathlib import Path


def run(cmd: list[str], env: dict[str, str] | None = None) -> str:
    result = subprocess.run(cmd, text=True, capture_output=True, env=env)
    if result.returncode != 0:
        raise SystemExit(result.stdout + result.stderr)
    return result.stdout


def clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["PIP_NO_INDEX"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PIP_REQUIRE_VIRTUALENV"] = "1"
    return env


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-python", required=True)
    parser.add_argument("--wheelhouse", required=True)
    parser.add_argument("--lockfile", required=True)
    parser.add_argument("--venv-dir", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--vision-smoke", action="store_true")
    args = parser.parse_args()

    venv_dir = Path(args.venv_dir)
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    run([args.base_python, "-m", "venv", str(venv_dir)])

    venv_python = venv_dir / "Scripts" / "python.exe"
    env = clean_env()
    env["PIP_REQUIRE_VIRTUALENV"] = "1"
    install_output = run([
        str(venv_python),
        "-m",
        "pip",
        "--isolated",
        "install",
        "--no-index",
        "--find-links",
        args.wheelhouse,
        "--require-hashes",
        "-r",
        args.lockfile,
    ], env=env)
    if "Looking in indexes:" in install_output:
        raise SystemExit("pip used an index during offline verification")
    if "Looking in links:" not in install_output:
        raise SystemExit("pip did not report local wheelhouse links during offline verification")

    pip_check = run([str(venv_python), "-m", "pip", "check"], env=env)
    module_expr = (
        "import json, pathlib, {module}; "
        "p = pathlib.Path({module}.__file__).resolve(); "
        "print(json.dumps({{'module': '{module}', '{module}.__file__': str(p)}}))"
    ).format(module=args.module)
    import_record = json.loads(run([str(venv_python), "-c", module_expr], env=env))
    import_file = Path(import_record[f"{args.module}.__file__"]).resolve()
    site_packages = Path(run([
        str(venv_python),
        "-c",
        "import sysconfig; print(sysconfig.get_paths()['purelib'])",
    ], env=env).strip()).resolve()
    if site_packages not in import_file.parents:
        raise SystemExit(f"{args.module} imported outside site-packages: {import_file}")

    vision = {}
    if args.vision_smoke:
        vision_expr = (
            "import cv2, PIL, numpy, skimage, json; "
            "print(json.dumps({'cv2': cv2.__file__, 'PIL': PIL.__file__, "
            "'numpy': numpy.__file__, 'skimage': skimage.__file__}))"
        )
        vision = json.loads(run([str(venv_python), "-c", vision_expr], env=env))

    Path(args.output).write_text(json.dumps({
        "venv_python": str(venv_python.resolve()),
        "site_packages": str(site_packages),
        "pip_check": pip_check.strip(),
        "pip_install_no_index": True,
        "pip_install_output_sample": install_output[:2000],
        "import_record": import_record,
        "vision_imports": vision,
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -LiteralPath $verificationScript -Encoding UTF8

$rookVerification = Join-Path $BuildRoot 'verification-rook.json'
$chirpVerification = Join-Path $BuildRoot 'verification-chirp.json'
$rookTempVenv = Join-Path $BuildRoot 'verify-rook-venv'
$chirpTempVenv = Join-Path $BuildRoot 'verify-chirp-venv'

& $pythonExe $verificationScript --base-python $pythonExe --wheelhouse $wheelhouse --lockfile $lockRook --venv-dir $rookTempVenv --module rook --vision-smoke --output $rookVerification
if ($LASTEXITCODE -ne 0) { Fail 'Rook temp install verification failed' }
& $pythonExe $verificationScript --base-python $pythonExe --wheelhouse $wheelhouse --lockfile $lockChirp --venv-dir $chirpTempVenv --module chirp --output $chirpVerification
if ($LASTEXITCODE -ne 0) { Fail 'Chirp temp install verification failed' }

$auditVenv = Join-Path $BuildRoot 'pip-audit-venv'
$pipAuditPackage = 'pip-audit==2.10.0'
& $pythonExe -m venv $auditVenv
if ($LASTEXITCODE -ne 0) { Fail 'pip-audit venv creation failed' }
$auditPython = Join-Path $auditVenv 'Scripts\python.exe'
& $auditPython -m pip install $pipAuditPackage
if ($LASTEXITCODE -ne 0) { Fail 'pip-audit install failed' }
$pipAudit = Join-Path $auditVenv 'Scripts\pip-audit.exe'
$rookVerificationObject = Get-Content -LiteralPath $rookVerification -Raw | ConvertFrom-Json
$chirpVerificationObject = Get-Content -LiteralPath $chirpVerification -Raw | ConvertFrom-Json
$rookAuditJson = Join-Path $BuildRoot 'pip-audit-rook.json'
$chirpAuditJson = Join-Path $BuildRoot 'pip-audit-chirp.json'
& $pipAudit --path $rookVerificationObject.site_packages --format json --output $rookAuditJson
if ($LASTEXITCODE -ne 0) { Fail 'pip-audit failed for Rook temp venv' }
& $pipAudit --path $chirpVerificationObject.site_packages --format json --output $chirpAuditJson
if ($LASTEXITCODE -ne 0) { Fail 'pip-audit failed for Chirp temp venv' }

$wheelTagScript = Join-Path $BuildRoot 'collect_wheel_metadata.py'
@'
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pip._vendor.packaging import tags as packaging_tags
from pip._vendor.packaging.utils import parse_wheel_filename


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheelhouse", required=True)
    args = parser.parse_args()
    wheelhouse = Path(args.wheelhouse)
    accepted_tags = {str(tag) for tag in packaging_tags.sys_tags()}
    records = []
    for wheel in sorted(wheelhouse.glob("*.whl")):
        name, version, _build, wheel_tags = parse_wheel_filename(wheel.name)
        tag_strings = sorted(str(tag) for tag in wheel_tags)
        if accepted_tags.isdisjoint(tag_strings):
            raise SystemExit(f"wheel is not compatible with this interpreter tag set: {wheel.name}")
        records.append({
            "file": wheel.name,
            "project": str(name),
            "version": str(version),
            "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest().upper(),
            "tags": tag_strings,
        })
    print(json.dumps({
        "interpreter_accepted_tags_sample": sorted(accepted_tags)[:100],
        "wheels": records,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -LiteralPath $wheelTagScript -Encoding UTF8

$wheelMetadata = (& $pythonExe $wheelTagScript --wheelhouse $wheelhouse | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { Fail 'wheel tag metadata collection failed' }

$provenanceScript = Join-Path $BuildRoot 'collect_license_provenance.py'
@'
from __future__ import annotations

import argparse
import email.parser
import hashlib
import json
import zipfile
from pathlib import Path


def metadata_for_wheel(wheel: Path) -> dict:
    with zipfile.ZipFile(wheel) as archive:
        metadata_name = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
        metadata = email.parser.Parser().parsestr(archive.read(metadata_name).decode("utf-8", "replace"))
        license_files = sorted(
            name for name in archive.namelist()
            if ".dist-info/licenses/" in name.lower()
            or name.rsplit("/", 1)[-1].lower().startswith(("license", "copying", "notice"))
        )
    return {
        "wheel_file": wheel.name,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest().upper(),
        "name": metadata.get("Name", ""),
        "version": metadata.get("Version", ""),
        "summary": metadata.get("Summary", ""),
        "license": metadata.get("License", ""),
        "license_expression": metadata.get("License-Expression", ""),
        "license_files": metadata.get_all("License-File", []),
        "bundled_license_file_paths": license_files,
        "home_page": metadata.get("Home-page", ""),
        "project_urls": metadata.get_all("Project-URL", []),
        "provenance_source": "wheel dist-info/METADATA",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheelhouse", required=True)
    args = parser.parse_args()
    wheelhouse = Path(args.wheelhouse)
    wheels = [metadata_for_wheel(wheel) for wheel in sorted(wheelhouse.glob("*.whl"))]
    print(json.dumps({"schema_version": 1, "third_party_wheels": wheels}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -LiteralPath $provenanceScript -Encoding UTF8

$wheelLicenseProvenance = (& $pythonExe $provenanceScript --wheelhouse $wheelhouse | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { Fail 'wheel license provenance collection failed' }

$sourceRoot = Join-Path $BuildRoot 'source-archives'
$rookSourceArchive = Join-Path $sourceRoot "rook-$rookGitSha.tar"
$chirpSourceArchive = Join-Path $sourceRoot "chirp-$chirpGitSha.tar"
$rookSourceSha = New-SourceArchive -Root $RepoRoot -GitSha $rookGitSha -OutPath $rookSourceArchive
$chirpSourceSha = New-SourceArchive -Root $ChirpRoot -GitSha $chirpGitSha -OutPath $chirpSourceArchive

$manifest = [ordered]@{
    schema_version = 1
    generated_utc = [DateTimeOffset]::UtcNow.ToString('o')
    release_version = $Version
    rook_git_sha = $rookGitSha
    rook_source_archive_sha256 = $rookSourceSha
    chirp_git_sha = $chirpGitSha
    chirp_source_archive_sha256 = $chirpSourceSha
    python = [ordered]@{
        version = '3.11.9'
        executable = $pythonExe
        abi = 'cp311'
        platform = 'win_amd64'
    }
    license_provenance = [ordered]@{
        schema_version = 1
        python_runtime = [ordered]@{
            package = $runtimeConfig.python_nuget_package
            version = $runtimeConfig.python_version
            nupkg_sha256 = $runtimeConfig.nupkg_sha256
            source_url = "https://www.nuget.org/api/v2/package/$($runtimeConfig.python_nuget_package)/$($runtimeConfig.python_version)"
            provenance_source = 'installer\python-runtime\python-runtime.json'
            license = 'Python Software Foundation License'
        }
        third_party_wheels = $wheelLicenseProvenance.third_party_wheels
    }
    wheelhouse = [ordered]@{
        path = $wheelhouse
        accepted_tag_sample = $wheelMetadata.interpreter_accepted_tags_sample
        wheels = $wheelMetadata.wheels
    }
    lockfiles = [ordered]@{
        rook = [ordered]@{ path = $lockRook; sha256 = Get-Sha256 -Path $lockRook }
        chirp = [ordered]@{ path = $lockChirp; sha256 = Get-Sha256 -Path $lockChirp }
    }
    verification = [ordered]@{
        rook = $rookVerificationObject
        chirp = $chirpVerificationObject
        pip_audit = [ordered]@{
            tool = $pipAuditPackage
            rook = [ordered]@{ path = $rookAuditJson; sha256 = Get-Sha256 -Path $rookAuditJson }
            chirp = [ordered]@{ path = $chirpAuditJson; sha256 = Get-Sha256 -Path $chirpAuditJson }
        }
    }
}

$manifestPath = Join-Path $OutputRoot 'python-runtime-manifest.json'
$manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Host "Python runtime manifest: $manifestPath"
```

- [ ] **Step 4: Run guard test**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\python-runtime-packaging.tests.ps1
```

Expected: PASS for static guard tests.

- [ ] **Step 5: Commit**

```powershell
git add scripts\python-runtime\build-rook-python-wheelhouse.ps1 scripts\tests\python-runtime-packaging.tests.ps1
git commit -m "build: add python wheelhouse provenance guards"
```

---

### Task 3: Move OCR Dependency Out Of Default Runtime

**Files:**
- Modify: `mcp_server/pyproject.toml`
- Modify: `scripts/tests/python-runtime-packaging.tests.ps1`

- [ ] **Step 1: Add failing guard for `pytesseract`**

Append to `scripts/tests/python-runtime-packaging.tests.ps1`:

```powershell
function Test-OcrDependencyIsOptional {
    $pyprojectPath = Join-Path $RepoRoot 'mcp_server\pyproject.toml'
    $content = Get-Content -Path $pyprojectPath -Raw
    $dependenciesBlock = [regex]::Match($content, '(?s)dependencies\s*=\s*\[(.*?)\]').Groups[1].Value
    Assert-True -Condition (-not $dependenciesBlock.Contains('pytesseract')) -Message 'pytesseract must not be in default public dependencies.'
    Assert-Contains -Text $content -Expected 'ocr = [' -Message 'pyproject must expose OCR as an optional extra if pytesseract remains declared.'
    Assert-Contains -Text $content -Expected '"pytesseract>=0.3.10"' -Message 'OCR optional extra must contain pytesseract.'
}

Test-OcrDependencyIsOptional
```

- [ ] **Step 2: Run guard test and verify it fails**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\python-runtime-packaging.tests.ps1
```

Expected: FAIL because `pytesseract` is currently in default dependencies.

- [ ] **Step 3: Modify `mcp_server/pyproject.toml`**

Move:

```toml
"pytesseract>=0.3.10",
```

out of `[project].dependencies` and add an optional extra:

```toml
[project.optional-dependencies]
ocr = [
    "pytesseract>=0.3.10",
]
test = [
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "anyio",
]
```

Preserve the existing `test` extra.

- [ ] **Step 4: Run guard test**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\python-runtime-packaging.tests.ps1
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add mcp_server\pyproject.toml scripts\tests\python-runtime-packaging.tests.ps1
git commit -m "build: keep OCR out of default python runtime"
```

---

### Task 4: Add Install-Time Runtime Manager Unit Tests

**Files:**
- Create: `mcp_server/tests/test_python_runtime_install.py`
- Create: `installer/python_runtime_install.py`

- [ ] **Step 1: Write failing Python tests**

Create `mcp_server/tests/test_python_runtime_install.py`:

```python
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_runtime_install():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "installer" / "python_runtime_install.py"
    spec = importlib.util.spec_from_file_location("rook_python_runtime_install", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pip_command_is_offline_and_hash_locked(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    command = runtime.build_offline_pip_install_command(
        tmp_path / "venv" / "Scripts" / "python.exe",
        tmp_path / "wheelhouse",
        tmp_path / "requirements-rook-lock.txt",
    )

    assert command[:4] == [
        str(tmp_path / "venv" / "Scripts" / "python.exe"),
        "-m",
        "pip",
        "--isolated",
    ]
    assert "install" in command
    assert "--no-index" in command
    assert "--find-links" in command
    assert "--require-hashes" in command
    assert "--index-url" not in command
    assert "--extra-index-url" not in command


def test_sanitized_install_env_removes_python_and_pip_index_state(monkeypatch) -> None:
    runtime = load_runtime_install()
    monkeypatch.setenv("PYTHONHOME", "C:/bad")
    monkeypatch.setenv("PYTHONPATH", "C:/bad")
    monkeypatch.setenv("PIP_INDEX_URL", "https://bad.example/simple")
    monkeypatch.setenv("PIP_EXTRA_INDEX_URL", "https://bad.example/extra")

    env = runtime.build_sanitized_python_env(require_virtualenv=True)

    assert "PYTHONHOME" not in env
    assert "PYTHONPATH" not in env
    assert "PIP_INDEX_URL" not in env
    assert "PIP_EXTRA_INDEX_URL" not in env
    assert env["PIP_NO_INDEX"] == "1"
    assert env["PIP_DISABLE_PIP_VERSION_CHECK"] == "1"
    assert env["PIP_REQUIRE_VIRTUALENV"] == "1"


def test_venv_invalidates_on_python_or_lock_hash_change(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    state = {
        "schema_version": 1,
        "python": {"identity_hash": "old-python"},
        "rook": {"lockfile_sha256": "old-lock"},
    }

    assert runtime.needs_venv_recreate(state, "rook", "new-python", "old-lock")
    assert runtime.needs_venv_recreate(state, "rook", "old-python", "new-lock")
    assert not runtime.needs_venv_recreate(state, "rook", "old-python", "old-lock")


def test_import_origin_must_be_site_packages(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    site_packages = tmp_path / "venv" / "Lib" / "site-packages" / "rook" / "__init__.py"
    source_tree = tmp_path / "app" / "mcp_server" / "src" / "rook" / "__init__.py"

    assert runtime.is_site_packages_import(site_packages)
    assert not runtime.is_site_packages_import(source_tree)


def test_install_state_has_schema_version(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    path = tmp_path / "data" / "install-state.json"
    runtime.write_install_state(
        path,
        {
            "python": {"path": "C:/Rook/python/cpython-3.11.9/python.exe"},
            "rook": {"venv_path": "C:/Rook/venv"},
            "chirp": {"venv_path": "C:/Rook/app/chirp/.venv"},
        },
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["python"]["path"].endswith("python.exe")
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
python -m pytest mcp_server\tests\test_python_runtime_install.py -q
```

Expected: FAIL because `installer/python_runtime_install.py` does not exist.

- [ ] **Step 3: Add minimal runtime manager module**

Create `installer/python_runtime_install.py`:

```python
"""Install-time management for Rook's private Python runtime.

Stdlib-only. Imported by post_install.py after the installer has copied files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


SCHEMA_VERSION = 1


def build_sanitized_python_env(require_virtualenv: bool) -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "PYTHONHOME",
        "PYTHONPATH",
        "PIP_INDEX_URL",
        "PIP_EXTRA_INDEX_URL",
        "PIP_CONFIG_FILE",
    ):
        env.pop(key, None)
    env["PIP_NO_INDEX"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    if require_virtualenv:
        env["PIP_REQUIRE_VIRTUALENV"] = "1"
    else:
        env.pop("PIP_REQUIRE_VIRTUALENV", None)
    return env


def build_offline_pip_install_command(
    venv_python: Path,
    wheelhouse_dir: Path,
    requirements_lock: Path,
) -> list[str]:
    return [
        str(venv_python),
        "-m",
        "pip",
        "--isolated",
        "install",
        "--no-index",
        "--find-links",
        str(wheelhouse_dir),
        "--require-hashes",
        "-r",
        str(requirements_lock),
    ]


def assert_offline_pip_command(command: list[str]) -> None:
    forbidden = {"--index-url", "--extra-index-url", "-i"}
    missing = {"--no-index", "--find-links", "--require-hashes"} - set(command)
    if missing:
        raise ValueError(f"offline pip command missing required flags: {sorted(missing)}")
    present_forbidden = forbidden.intersection(command)
    if present_forbidden:
        raise ValueError(f"offline pip command contains network index flags: {sorted(present_forbidden)}")


def needs_venv_recreate(
    install_state: dict,
    runtime_name: str,
    python_identity_hash: str,
    lockfile_sha256: str,
) -> bool:
    if install_state.get("schema_version") != SCHEMA_VERSION:
        return True
    if install_state.get("python", {}).get("identity_hash") != python_identity_hash:
        return True
    runtime_state = install_state.get(runtime_name, {})
    return runtime_state.get("lockfile_sha256") != lockfile_sha256


def is_site_packages_import(module_file: Path) -> bool:
    normalized = str(module_file).replace("\\", "/").lower()
    return "/site-packages/" in normalized


def write_install_state(path: Path, payload: dict) -> None:
    state = {"schema_version": SCHEMA_VERSION}
    state.update(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run unit tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_python_runtime_install.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add installer\python_runtime_install.py mcp_server\tests\test_python_runtime_install.py
git commit -m "installer: add private python runtime install helpers"
```

---

### Task 5: Integrate Private Runtime Manager Into `post_install.py`

**Files:**
- Modify: `installer/post_install.py`
- Modify: `mcp_server/tests/test_python_runtime_install.py`

- [ ] **Step 1: Add failing tests for release config import policy**

Append to `mcp_server/tests/test_python_runtime_install.py`:

```python
def test_release_chat_manifest_has_no_source_pythonpath_entries(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    manifest = runtime.build_chat_service_manifest(
        mcp_server_dir=tmp_path / "app" / "mcp_server",
        rook_venv_python=tmp_path / "venv" / "Scripts" / "python.exe",
        release_mode=True,
    )

    assert manifest["pythonPath"].endswith("venv\\Scripts\\python.exe") or manifest["pythonPath"].endswith("venv/Scripts/python.exe")
    assert manifest["workingDirectory"].endswith("mcp_server")
    assert manifest["pythonPathEntries"] == []


def test_mcp_env_points_to_chirp_home_and_clears_python_paths(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    env = runtime.build_release_mcp_env(
        install_dir=tmp_path / "app",
        data_dir=tmp_path / "data",
        chirp_dir=tmp_path / "app" / "chirp",
    )

    assert env["ROOK_INSTALL_ROOT"].endswith("app")
    assert env["ROOK_DATA_DIR"].endswith("data")
    assert env["ROOK_MODE"] == "release"
    assert env["PYTHONHOME"] == ""
    assert env["PYTHONPATH"] == ""
    assert env["CHIRP_HOME"].endswith("app/chirp")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest mcp_server\tests\test_python_runtime_install.py -q
```

Expected: FAIL because `build_chat_service_manifest` and `build_release_mcp_env` are missing.

- [ ] **Step 3: Add helper functions**

Append to `installer/python_runtime_install.py`:

```python
def _slash(path: Path) -> str:
    return str(path).replace("\\", "/")


def build_release_mcp_env(install_dir: Path, data_dir: Path, chirp_dir: Path | None) -> dict[str, str]:
    env_vars = {
        "PYTHONPATH": "",
        "PYTHONHOME": "",
        "ROOK_INSTALL_ROOT": _slash(install_dir),
        "ROOK_DATA_DIR": _slash(data_dir),
        "ROOK_MODE": "release",
    }
    if chirp_dir is not None:
        env_vars["CHIRP_HOME"] = _slash(chirp_dir)
    return env_vars


def build_chat_service_manifest(
    mcp_server_dir: Path,
    rook_venv_python: Path,
    release_mode: bool,
) -> dict:
    return {
        "pythonPath": str(rook_venv_python),
        "workingDirectory": str(mcp_server_dir),
        "module": "rook.agent.chat.service_main",
        "owner": "rhino-panel",
        "pythonPathEntries": [] if release_mode else [str(mcp_server_dir / "src")],
    }
```

- [ ] **Step 4: Modify `post_install.py` to use release helpers**

In `installer/post_install.py`:

1. Import the helper:

```python
import python_runtime_install
```

2. Replace `_build_mcp_env` body with a call to:

```python
return python_runtime_install.build_release_mcp_env(install_dir, data_dir, chirp_dir)
```

3. Replace `write_chat_service_manifest` manifest construction with:

```python
manifest = python_runtime_install.build_chat_service_manifest(
    mcp_server_dir=mcp_server_dir,
    rook_venv_python=Path(python_path),
    release_mode=True,
)
```

This preserves existing config writer call sites while enforcing release no-source-path policy.

- [ ] **Step 5: Run unit tests and py_compile**

Run:

```powershell
python -m pytest mcp_server\tests\test_python_runtime_install.py -q
python -m py_compile installer\post_install.py installer\python_runtime_install.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add installer\post_install.py installer\python_runtime_install.py mcp_server\tests\test_python_runtime_install.py
git commit -m "installer: use release private python config policy"
```

---

### Task 6: Replace Public Editable Installs With Offline Wheelhouse Installs

**Files:**
- Modify: `installer/python_runtime_install.py`
- Modify: `installer/post_install.py`
- Modify: `mcp_server/tests/test_python_runtime_install.py`

- [ ] **Step 1: Add failing tests for runtime install orchestration**

Append to `mcp_server/tests/test_python_runtime_install.py`:

```python
def test_runtime_layout_uses_private_python_and_two_venvs(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")

    assert layout.private_python == tmp_path / "Rook" / "python" / "cpython-3.11.9" / "python.exe"
    assert layout.rook_venv == tmp_path / "Rook" / "venv"
    assert layout.chirp_venv == tmp_path / "Rook" / "app" / "chirp" / ".venv"
    assert layout.wheelhouse == tmp_path / "Rook" / "app" / "python-wheelhouse"


def test_pip_output_evidence_rejects_index_lookup() -> None:
    runtime = load_runtime_install()
    runtime.assert_local_wheelhouse_output("Looking in links: C:/Rook/app/python-wheelhouse\nProcessing rook_mcp.whl")

    try:
        runtime.assert_local_wheelhouse_output("Looking in indexes: https://pypi.org/simple")
    except ValueError as exc:
        assert "network index" in str(exc)
    else:
        raise AssertionError("expected network index output to be rejected")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest mcp_server\tests\test_python_runtime_install.py -q
```

Expected: FAIL because `RuntimeLayout` and `assert_local_wheelhouse_output` are missing.

- [ ] **Step 3: Implement layout and output validation**

Append to `installer/python_runtime_install.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeLayout:
    rook_root: Path
    app_dir: Path
    data_dir: Path
    private_python: Path
    rook_venv: Path
    chirp_venv: Path
    wheelhouse: Path
    rook_lock: Path
    chirp_lock: Path
    runtime_manifest: Path
    install_state: Path

    @classmethod
    def from_rook_root(cls, rook_root: Path, python_version: str) -> "RuntimeLayout":
        app_dir = rook_root / "app"
        data_dir = rook_root / "data"
        return cls(
            rook_root=rook_root,
            app_dir=app_dir,
            data_dir=data_dir,
            private_python=rook_root / "python" / f"cpython-{python_version}" / "python.exe",
            rook_venv=rook_root / "venv",
            chirp_venv=app_dir / "chirp" / ".venv",
            wheelhouse=app_dir / "python-wheelhouse",
            rook_lock=app_dir / "requirements-rook-lock.txt",
            chirp_lock=app_dir / "requirements-chirp-lock.txt",
            runtime_manifest=app_dir / "python-runtime-manifest.json",
            install_state=data_dir / "install-state.json",
        )


def assert_local_wheelhouse_output(output: str) -> None:
    if "Looking in indexes:" in output:
        raise ValueError("pip output shows network index lookup")
    if "Looking in links:" not in output and "Processing " not in output:
        raise ValueError("pip output does not prove local wheelhouse use")
```

- [ ] **Step 4: Refactor `post_install.py` install functions**

Modify `installer/post_install.py`:

1. Replace public `install_mcp_server()` editable install command with a new private-runtime path:

```python
def install_mcp_server(mcp_server_dir: Path, runtime_root: Path) -> Path | None:
    layout = python_runtime_install.RuntimeLayout.from_rook_root(runtime_root, "3.11.9")
    # create layout.rook_venv from layout.private_python, install layout.rook_lock from layout.wheelhouse
    # call _run_streaming_command with env=python_runtime_install.build_sanitized_python_env(require_virtualenv=True)
```

2. Replace Chirp editable install with the same pattern using `layout.chirp_venv` and `layout.chirp_lock`.

3. Remove `pip install -e` from release install paths.

The minimal implementation can keep `_run_streaming_command`, but the command it runs must be created by `build_offline_pip_install_command()`.

- [ ] **Step 5: Run tests and static guard**

Run:

```powershell
python -m pytest mcp_server\tests\test_python_runtime_install.py -q
python -m py_compile installer\post_install.py installer\python_runtime_install.py
Select-String -Path installer\post_install.py -Pattern 'pip", "install", "-e"|pip install -e'
```

Expected:
- pytest PASS
- py_compile PASS
- final `Select-String` returns no matches.

- [ ] **Step 6: Commit**

```powershell
git add installer\post_install.py installer\python_runtime_install.py mcp_server\tests\test_python_runtime_install.py
git commit -m "installer: install python packages from bundled wheelhouse"
```

---

### Task 7: Update Inno Setup Public Prerequisites And Payload Packaging

**Files:**
- Modify: `installer/RookSetup.iss`
- Modify: `scripts/tests/release-installer-guards.tests.ps1`

- [ ] **Step 1: Add failing installer guard tests**

Add to `scripts/tests/release-installer-guards.tests.ps1`:

```powershell
function Test-InstallerPackagesBundledPythonRuntime {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-Contains -Text $content -Expected '#define PythonRuntimeDir RepoRoot + "\installer\runtime\python\cpython-3.11.9"' -Message 'Installer must define staged private Python runtime directory.'
    Assert-Contains -Text $content -Expected '#define PythonWheelhouseDir RepoRoot + "\installer\runtime\python-wheelhouse"' -Message 'Installer must define staged wheelhouse directory.'
    Assert-Contains -Text $content -Expected 'Source: "{#PythonRuntimeDir}\*"; DestDir: "{localappdata}\Rook\python\cpython-3.11.9"' -Message 'Installer must package private Python runtime.'
    Assert-Contains -Text $content -Expected 'Source: "{#PythonWheelhouseDir}\*"; DestDir: "{app}\python-wheelhouse"' -Message 'Installer must package offline wheelhouse.'
    Assert-Contains -Text $content -Expected 'requirements-rook-lock.txt' -Message 'Installer must package Rook lockfile.'
    Assert-Contains -Text $content -Expected 'requirements-chirp-lock.txt' -Message 'Installer must package Chirp lockfile.'
    Assert-Contains -Text $content -Expected 'python-runtime-manifest.json' -Message 'Installer must package Python runtime manifest.'
    Assert-Contains -Text $content -Expected 'python_runtime_install.py' -Message 'Installer must package runtime install helper.'
}

function Test-PublicInstallerDoesNotRequireUserPython {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-NotContains -Text $content -Unexpected 'Python MCP Server (requires Python 3.10+)' -Message 'Public MCP component must not require user Python.'
    Assert-NotContains -Text $content -Unexpected 'Chirp — LLM-powered Grasshopper components (requires MCP + Python 3.10+)' -Message 'Public Chirp component must not require user Python.'
    Assert-NotContains -Text $content -Unexpected 'Python 3.10+ is required for the MCP server and Chirp but was not found.' -Message 'Installer must not block public MCP/Chirp install on user Python.'
    Assert-NotContains -Text $content -Unexpected 'Filename: "{code:GetPythonPath}"' -Message 'Post-install must not be launched through user Python discovery.'
    Assert-Contains -Text $content -Expected 'Filename: "{localappdata}\Rook\python\cpython-3.11.9\python.exe"' -Message 'Post-install must run on bundled private Python.'
}

function Test-UninstallUsesRecordedPrivatePython {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-Contains -Text $content -Expected 'python_path.txt' -Message 'Installer must record private Python path for uninstall cleanup.'
    Assert-Contains -Text $content -Expected '{localappdata}\Rook\python\cpython-3.11.9\python.exe' -Message 'Uninstall must have a deterministic private Python fallback path.'
    Assert-Contains -Text $content -Expected 'CurUninstallStepChanged' -Message 'Installer must run uninstall cleanup from the uninstall hook.'
    Assert-Contains -Text $content -Expected '--uninstall' -Message 'Uninstall cleanup must invoke post_install.py --uninstall.'
    Assert-NotContains -Text $content -Unexpected 'PythonExe := GetPythonPath()' -Message 'Uninstall must not depend on user Python discovery.'
}
```

Call all three functions near the other installer tests.

- [ ] **Step 2: Run guard test and verify it fails**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: FAIL because the `.iss` still uses user Python discovery and does not package the runtime payload.

- [ ] **Step 3: Modify `installer/RookSetup.iss`**

Add defines:

```iss
#define PythonRuntimeDir RepoRoot + "\installer\runtime\python\cpython-3.11.9"
#define PythonWheelhouseDir RepoRoot + "\installer\runtime\python-wheelhouse"
#define PythonRuntimeManifest RepoRoot + "\installer\runtime\python-runtime-manifest.json"
#define RookLockfile RepoRoot + "\installer\runtime\requirements-rook-lock.txt"
#define ChirpLockfile RepoRoot + "\installer\runtime\requirements-chirp-lock.txt"
```

Update component descriptions:

```iss
Name: "mcp"; Description: "Python MCP Server (bundled private runtime)"; Types: full custom
Name: "chirp"; Description: "Chirp — LLM-powered Grasshopper components (bundled private runtime)"; Types: full custom
```

Add file entries:

```iss
Source: "{#PythonRuntimeDir}\*"; DestDir: "{localappdata}\Rook\python\cpython-3.11.9"; Components: mcp; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#PythonWheelhouseDir}\*"; DestDir: "{app}\python-wheelhouse"; Components: mcp chirp; Flags: ignoreversion
Source: "{#PythonRuntimeManifest}"; DestDir: "{app}"; Components: mcp; Flags: ignoreversion
Source: "{#RookLockfile}"; DestDir: "{app}"; Components: mcp; Flags: ignoreversion
Source: "{#ChirpLockfile}"; DestDir: "{app}"; Components: chirp; Flags: ignoreversion
Source: "python_runtime_install.py"; DestDir: "{app}"; Flags: ignoreversion
```

Replace `[Run]` post-install line with:

```iss
Filename: "{localappdata}\Rook\python\cpython-3.11.9\python.exe"; Parameters: """{app}\post_install.py"" --install-dir ""{app}"" --runtime-root ""{localappdata}\Rook"" --mcp-server-dir ""{app}\mcp_server"" {code:GetChirpArgs} {code:GetClaudeArgs} {code:GetCodexArgs} {code:GetPluginsArgs}"; StatusMsg: "Configuring Rook private Python runtime and offline dependencies."; Components: mcp chirp claude codex; Flags: waituntilterminated; Check: BundledPythonFound
```

Add:

```iss
function BundledPythonFound(): Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Rook\python\cpython-3.11.9\python.exe'));
end;
```

Record the private Python path before post-install cleanup can need it:

```iss
procedure RecordPrivatePythonPath();
begin
  SaveStringToFile(
    ExpandConstant('{app}') + '\python_path.txt',
    ExpandConstant('{localappdata}\Rook\python\cpython-3.11.9\python.exe'),
    False);
end;
```

Call `RecordPrivatePythonPath()` from `CurStepChanged(ssPostInstall)` before the `[Run]` post-install command can be needed by later maintenance/uninstall flows.

Use the recorded path for uninstall, with deterministic private-runtime fallback:

```iss
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  PythonExe: String;
  PythonPathFile: String;
  Lines: TArrayOfString;
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    PythonExe := ExpandConstant('{localappdata}\Rook\python\cpython-3.11.9\python.exe');
    PythonPathFile := ExpandConstant('{app}') + '\python_path.txt';
    if LoadStringsFromFile(PythonPathFile, Lines) then
    begin
      if GetArrayLength(Lines) > 0 then
      begin
        PythonExe := Lines[0];
      end;
    end;

    if FileExists(PythonExe) then
    begin
      Exec(
        PythonExe,
        '"' + ExpandConstant('{app}') + '\post_install.py" --uninstall',
        '',
        SW_HIDE,
        ewWaitUntilTerminated,
        ResultCode);
    end;
  end;
end;
```

Remove the public MCP/Chirp `PythonFound` prerequisite block from `PrepareToInstall`. Public/full install and uninstall must not depend on user Python discovery. Existing user-Python discovery functions may remain only for explicitly gated dev/support paths; they must not be called by the public MCP/Chirp install or uninstall flow.

- [ ] **Step 4: Run guard test**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: PASS for the new static guards, assuming staged runtime files exist or existing built-payload tests are adjusted to not require files before Task 11.

- [ ] **Step 5: Commit**

```powershell
git add installer\RookSetup.iss scripts\tests\release-installer-guards.tests.ps1
git commit -m "installer: package bundled python runtime payload"
```

---

### Task 8: Gate Chat Service User-Python Fallback

**Files:**
- Modify: `src/Rook/UI/Chat/ChatServiceManager.cs`
- Modify: `scripts/tests/release-installer-guards.tests.ps1`

- [ ] **Step 1: Add static guard test**

Add to `scripts/tests/release-installer-guards.tests.ps1`:

```powershell
function Test-ChatServiceUserPythonFallbackIsDevOnly {
    $chatManager = Join-Path $RepoRoot 'src\Rook\UI\Chat\ChatServiceManager.cs'
    $content = Get-Content -Path $chatManager -Raw

    Assert-Contains -Text $content -Expected 'ROOK_ALLOW_USER_PYTHON_DISCOVERY' -Message 'Chat service PATH Python discovery must be gated by explicit support override.'
    Assert-Contains -Text $content -Expected 'AllowUserPythonDiscovery' -Message 'Chat manager must centralize user Python fallback policy.'
    Assert-Contains -Text $content -Expected 'DiscoverManagedVenvPython()' -Message 'Chat manager must prefer managed Rook venv.'
    Assert-NotContains -Text $content -Unexpected 'DiscoverManagedVenvPython() ?? DiscoverPython()' -Message 'Chat manager must not unconditionally fall back to PATH Python.'
}
```

Call it with the other tests.

- [ ] **Step 2: Run guard and verify it fails**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: FAIL because fallback is currently unconditional.

- [ ] **Step 3: Modify `ChatServiceManager.cs`**

Add helper:

```csharp
private static bool AllowUserPythonDiscovery()
{
    var value = Environment.GetEnvironmentVariable("ROOK_ALLOW_USER_PYTHON_DISCOVERY");
    return string.Equals(value, "1", StringComparison.Ordinal)
        || string.Equals(value, "true", StringComparison.OrdinalIgnoreCase);
}
```

Replace:

```csharp
pythonPath = DiscoverManagedVenvPython() ?? DiscoverPython();
```

with:

```csharp
pythonPath = DiscoverManagedVenvPython();
if (string.IsNullOrEmpty(pythonPath) && AllowUserPythonDiscovery())
{
    pythonPath = DiscoverPython();
}
```

If user Python fallback is disabled and managed venv is missing, return the existing manifest failure path.

- [ ] **Step 4: Run guard test**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: PASS.

- [ ] **Step 5: Build managed project**

Run:

```powershell
dotnet build src\Rook\Rook.csproj -c Release
```

Expected: exit code 0.

- [ ] **Step 6: Commit**

```powershell
git add src\Rook\UI\Chat\ChatServiceManager.cs scripts\tests\release-installer-guards.tests.ps1
git commit -m "chat: gate user python fallback for release installs"
```

---

### Task 9: Update Release Artifact Validator For Python Runtime Evidence

**Files:**
- Modify: `scripts/validate-release-artifacts.ps1`
- Modify: `scripts/tests/validate-release-artifacts.tests.ps1`

- [ ] **Step 1: Add failing validator tests**

Open `scripts/tests/validate-release-artifacts.tests.ps1` and add a test that asserts the validator script requires:

```powershell
function Test-ReleaseValidatorRequiresPythonRuntimeEvidence {
    $validator = Get-Content -Path $ReleaseArtifactValidator -Raw
    Assert-Contains -Text $validator -Expected 'python_runtime_manifest' -Message 'Release validator must require python_runtime_manifest in smoke evidence.'
    Assert-Contains -Text $validator -Expected 'install_state' -Message 'Release validator must require install_state evidence.'
    Assert-Contains -Text $validator -Expected 'private_python_path' -Message 'Smoke manifest must record private Python path.'
    Assert-Contains -Text $validator -Expected 'private_python_version' -Message 'Smoke manifest must record private Python version.'
    Assert-Contains -Text $validator -Expected 'rook_import_file' -Message 'Smoke manifest must record rook.__file__.'
    Assert-Contains -Text $validator -Expected 'chirp_import_file' -Message 'Smoke manifest must record chirp.__file__.'
    Assert-Contains -Text $validator -Expected 'pip_check' -Message 'Smoke manifest must record pip check results.'
    Assert-Contains -Text $validator -Expected 'license_provenance' -Message 'Release validator must require runtime and wheel license/provenance evidence.'
    Assert-Contains -Text $validator -Expected 'chirp_git_sha' -Message 'Release validator must require Chirp source identity.'
}
```

Call the test with the existing validation tests.

- [ ] **Step 2: Run validator tests and verify failure**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\validate-release-artifacts.tests.ps1
```

Expected: FAIL because validator does not inspect Python runtime evidence yet.

- [ ] **Step 3: Implement validator checks**

In `scripts/validate-release-artifacts.ps1`:

1. Add helper `Assert-PythonRuntimeEvidence`.
2. Require top-level smoke fields:

```powershell
python_runtime_manifest
install_state
```

3. Require and validate:

```powershell
private_python_path
private_python_version
rook_venv_path
chirp_venv_path
rook_import_file
chirp_import_file
pip_check
license_provenance
config_identity
no_index_install
chirp_git_sha
chirp_source_archive_sha256
```

4. Fail unless:

```powershell
$smokeManifest.private_python_path -match '(?i)\\Rook\\python\\cpython-3\.11\.9\\python\.exe$'
$smokeManifest.rook_import_file -match '(?i)\\Rook\\venv\\Lib\\site-packages\\rook\\'
$smokeManifest.chirp_import_file -match '(?i)\\Rook\\app\\chirp\\.venv\\Lib\\site-packages\\chirp\\'
$smokeManifest.no_index_install -eq $true
$smokeManifest.pip_check.rook.ok -eq $true
$smokeManifest.pip_check.chirp.ok -eq $true
$pythonRuntimeManifest.license_provenance.python_runtime.package -eq 'python'
$pythonRuntimeManifest.license_provenance.third_party_wheels.Count -gt 0
```

5. Add Python manifest summary into `$releaseManifest`, including `license_provenance` summary counts and Python NuGet identity.

- [ ] **Step 4: Run validator tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\validate-release-artifacts.tests.ps1
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts\validate-release-artifacts.ps1 scripts\tests\validate-release-artifacts.tests.ps1
git commit -m "release: require bundled python runtime smoke evidence"
```

---

### Task 10: Update Build-Release Docs And Source Path Checklists

**Files:**
- Modify: `.agents/skills/build-release/SKILL.md`
- Modify: `.claude/skills/build-release/SKILL.md`
- Modify: `.agents/skills/build-release/references/iss-source-paths.md`
- Modify: `.claude/skills/build-release/references/iss-source-paths.md`
- Modify: `scripts/tests/release-installer-guards.tests.ps1`

- [ ] **Step 1: Add failing guard expectations**

Extend `Test-ReleaseWorkflowDocsUseMultiRuntimeCompanionOutputs` or add:

```powershell
function Test-BuildReleaseDocsRequireBundledPythonPayload {
    $combined = @(
        Get-Content -Path $BuildReleaseSkill -Raw
        Get-Content -Path $ClaudeBuildReleaseSkill -Raw
        Get-Content -Path $IssSourcePaths -Raw
        Get-Content -Path $ClaudeIssSourcePaths -Raw
    ) -join "`n"

    Assert-Contains -Text $combined -Expected 'scripts\python-runtime\stage-rook-python-runtime.ps1' -Message 'Release docs must stage private Python runtime.'
    Assert-Contains -Text $combined -Expected 'scripts\python-runtime\build-rook-python-wheelhouse.ps1' -Message 'Release docs must build offline Python wheelhouse.'
    Assert-Contains -Text $combined -Expected 'installer\runtime\python\cpython-3.11.9\python.exe' -Message 'Source checklist must require staged private Python runtime.'
    Assert-Contains -Text $combined -Expected 'installer\runtime\python-wheelhouse' -Message 'Source checklist must require staged wheelhouse.'
    Assert-Contains -Text $combined -Expected 'installer\runtime\requirements-rook-lock.txt' -Message 'Source checklist must require Rook lockfile.'
    Assert-Contains -Text $combined -Expected 'installer\runtime\requirements-chirp-lock.txt' -Message 'Source checklist must require Chirp lockfile.'
    Assert-Contains -Text $combined -Expected 'installer\runtime\python-runtime-manifest.json' -Message 'Source checklist must require Python runtime manifest.'
}
```

Call this test.

- [ ] **Step 2: Run guard and verify failure**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: FAIL because docs/checklists are missing the Python payload stage.

- [ ] **Step 3: Update build-release skill docs**

In both `.agents/skills/build-release/SKILL.md` and `.claude/skills/build-release/SKILL.md`:

1. Insert a pipeline step after exact release SHA checkout:

```markdown
## Step 3A: Build Bundled Python Runtime And Wheelhouse

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\python-runtime\stage-rook-python-runtime.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\python-runtime\build-rook-python-wheelhouse.ps1 -Version X.Y.Z
```

This stage must run from the exact checked-out release SHA. It stages CPython
3.11.9 from the pinned NuGet package, builds non-editable Rook/Chirp wheels,
rejects source distributions in the final wheelhouse, validates import origins
from temp venv site-packages, runs `pip check`, records Chirp sibling-repo
source identity, records package license/provenance evidence, and writes
`installer\runtime\python-runtime-manifest.json`.
```

2. Adjust subsequent step numbers or add text without renumbering if renumbering is too noisy.

- [ ] **Step 4: Update source path checklists**

In both `.agents/skills/build-release/references/iss-source-paths.md` and `.claude/skills/build-release/references/iss-source-paths.md`, add a section:

```markdown
## Bundled Python Runtime Payload

| File/Dir | Notes |
|----------|-------|
| `installer/runtime/python/cpython-3.11.9/python.exe` | Private CPython runtime staged from official Python NuGet package |
| `installer/runtime/python/cpython-3.11.9/Lib/` | Runtime standard library |
| `installer/runtime/python-wheelhouse/` | Union wheelhouse; wheels only, no sdists |
| `installer/runtime/requirements-rook-lock.txt` | Fully pinned hash-locked Rook MCP/chat requirements |
| `installer/runtime/requirements-chirp-lock.txt` | Fully pinned hash-locked Chirp requirements |
| `installer/runtime/python-runtime-manifest.json` | Runtime, wheelhouse, lockfile, audit, license/provenance, source provenance, and import-origin manifest |
| `installer/python_runtime_install.py` | Stdlib post-install helper for private runtime installs |
```

Add these paths to the checklist script block in the same files.

- [ ] **Step 5: Run guard**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add .agents\skills\build-release\SKILL.md .claude\skills\build-release\SKILL.md .agents\skills\build-release\references\iss-source-paths.md .claude\skills\build-release\references\iss-source-paths.md scripts\tests\release-installer-guards.tests.ps1
git commit -m "docs: add bundled python release workflow"
```

---

### Task 11: Negative Contamination Test

**Files:**
- Modify: `mcp_server/tests/test_python_runtime_install.py`
- Modify: `installer/python_runtime_install.py`

- [ ] **Step 1: Add failing negative contamination test**

Append:

```python
def test_public_install_ignores_user_python_and_pip_contamination(tmp_path: Path, monkeypatch) -> None:
    runtime = load_runtime_install()
    fake_user_python = tmp_path / "UserPython" / "python.exe"
    fake_user_python.parent.mkdir()
    fake_user_python.write_text("not real", encoding="utf-8")

    monkeypatch.setenv("PATH", str(fake_user_python.parent))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "source-shadow"))
    monkeypatch.setenv("PYTHONHOME", str(tmp_path / "bad-pythonhome"))
    monkeypatch.setenv("PIP_INDEX_URL", "https://bad.example/simple")
    monkeypatch.setenv("PIP_EXTRA_INDEX_URL", "https://bad.example/extra")

    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")
    env = runtime.build_sanitized_python_env(require_virtualenv=True)
    command = runtime.build_offline_pip_install_command(
        layout.rook_venv / "Scripts" / "python.exe",
        layout.wheelhouse,
        layout.rook_lock,
    )

    runtime.assert_offline_pip_command(command)
    assert str(fake_user_python) not in " ".join(command)
    assert env["PIP_NO_INDEX"] == "1"
    assert "PIP_INDEX_URL" not in env
    assert "PIP_EXTRA_INDEX_URL" not in env
    assert "PYTHONPATH" not in env
    assert "PYTHONHOME" not in env
```

- [ ] **Step 2: Run test**

Run:

```powershell
python -m pytest mcp_server\tests\test_python_runtime_install.py -q
```

Expected: PASS if earlier tasks implemented env sanitization correctly. If it fails, fix `build_sanitized_python_env` and command construction until it passes.

- [ ] **Step 3: Commit**

```powershell
git add installer\python_runtime_install.py mcp_server\tests\test_python_runtime_install.py
git commit -m "test: prove public install ignores python contamination"
```

---

### Task 12: Full Local Verification And Installer Compile

**Files:**
- No source edits unless verification exposes a defect.

- [ ] **Step 1: Run Python unit tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_python_runtime_install.py mcp_server\tests\test_post_install.py -q
```

Expected: PASS.

- [ ] **Step 2: Run PowerShell guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\python-runtime-packaging.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\validate-release-artifacts.tests.ps1
```

Expected: PASS.

- [ ] **Step 3: Stage runtime and wheelhouse**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\python-runtime\stage-rook-python-runtime.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\python-runtime\build-rook-python-wheelhouse.ps1 -Version 1.5.10
```

Expected:
- `installer\runtime\python\cpython-3.11.9\python.exe` exists.
- `installer\runtime\python-wheelhouse` contains only `.whl` files.
- `installer\runtime\requirements-rook-lock.txt` exists.
- `installer\runtime\requirements-chirp-lock.txt` exists.
- `installer\runtime\python-runtime-manifest.json` exists and has `schema_version: 1` plus `license_provenance`.

- [ ] **Step 4: Compile installer**

Run:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "C:\Users\aryan\source\repos\Rook\installer\RookSetup.iss"
```

Expected:
- Exit code 0.
- `installer\output\Rook-Setup-1.5.10.exe` exists.

- [ ] **Step 5: Record verification defects as follow-up work**

If verification exposes a defect, stop this verification task and create a focused follow-up fix task with its own failing test. Do not create a catch-all verification commit from this task.

---

## Self-Review Checklist

- Spec coverage:
  - Private CPython runtime: Tasks 1, 7, 10, 12.
  - Offline wheelhouse and non-editable wheels: Tasks 2, 6, 7, 12.
  - Two venvs and Chirp contract: Tasks 4, 6, 7.
  - OCR out of scope: Task 3.
  - Config identity and no source `PYTHONPATH`: Tasks 5, 8, 9.
  - Security gates and install-state evidence: Tasks 4, 6, 9, 11.
  - Release docs/checklists synchronization: Task 10.
  - Clean verification and installer compile: Task 12.

- Plan-quality scan:
  - No task uses deferred work markers or unspecified “handle edge cases” instructions.

- Type consistency:
  - Runtime helper names used across tasks: `RuntimeLayout`, `build_sanitized_python_env`, `build_offline_pip_install_command`, `assert_offline_pip_command`, `build_release_mcp_env`, `build_chat_service_manifest`.
  - Manifest schema field name is consistently `schema_version`.
  - License/provenance manifest field name is consistently `license_provenance`.
  - Chirp source identity fields are consistently `chirp_git_sha` and `chirp_source_archive_sha256`.

## Execution Handoff

Plan complete. Use subagent-driven execution for this plan unless there is a reason to keep all work inline. Each task has a focused test/implementation/commit boundary.
