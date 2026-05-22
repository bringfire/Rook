# Beta Installer Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current beta Inno installer into a signed, self-contained, per-user installer with sealed runtime payloads, transactional migration, release evidence, and a path that does not block a future enterprise installer.

**Architecture:** The release pipeline becomes artifact-first: build static payloads, generate `rook-payload-manifest.json`, run evidence-producing gates, compile/sign the installer, then publish `rook-release-manifest.json`. The installer becomes transaction-oriented: stage payloads, verify, activate Rhino plugins, rewrite checked client configs, write durable client-config state, then commit install state.

**Tech Stack:** Inno Setup, PowerShell release scripts, Python stdlib installer helpers, existing Python `rook doctor`, .NET/Rhino plugin outputs, Authenticode/SignTool, GitHub Releases.

---

## Scope And Execution Notes

This plan lands the evidence-file contract first, then adds concrete release gates behind it. Scanner implementations may become stricter in future work, but every task here must produce the named evidence files and enforce the release-blocking behavior described in the design spec.

Run implementation in an isolated worktree if other installer/Rhino.Inside changes are still pending. Do not revert unrelated modified files in the main worktree.

## Planned File Structure

Create:

- `scripts/release/Build-RookPayloadManifest.ps1` - builds `rook-payload-manifest.json` from staged static payload files.
- `scripts/release/Test-RookPayloadManifest.ps1` - validates payload manifest schema and recomputes static payload hashes.
- `scripts/release/Build-RookMcpWheel.ps1` - builds the first-party `rook-mcp` wheel from the current release commit and produces `rook-mcp-wheel-report.json`.
- `scripts/release/Build-RookWheelhouse.ps1` - builds the sealed wheelhouse from a hash-pinned requirements lock and produces `wheelhouse-lock-report.json`.
- `scripts/release/Build-RookPythonRuntime.ps1` - creates the bundled CPython runtime and sealed wheelhouse/materialized package tree.
- `scripts/release/Invoke-RookRuntimeSecurityScan.ps1` - produces vulnerability, license, startup-hook, and wheelhouse evidence reports.
- `mcp_server/requirements-lock.txt` - flat, fully pinned, hash-locked third-party runtime requirements consumed by the wheelhouse builder.
- `scripts/release/license-policy.json` - release-blocking license policy and explicit missing-license exceptions.
- `scripts/release/release-tools-requirements.txt` - pinned release-build tooling requirements, including `pip-audit`.
- `scripts/release/Test-RookNativeClosure.ps1` - produces `native-dependency-report.json`.
- `scripts/release/Test-RookManagedClosure.ps1` - produces `managed-dependency-report.json`.
- `scripts/release/New-RookReleaseManifest.ps1` - creates `rook-release-manifest.json` after installer signing.
- `scripts/release/Invoke-RookInstallerSmoke.ps1` - runs smoke checks and writes `installer-smoke-summary.md`.
- `artifacts/release/network-isolation-evidence.json` - release smoke evidence recording the network-disabled test environment.
- `installer/install_state.py` - shared stdlib-only helpers for durable install state, backups, client-config state, and atomic writes.
- `installer/runtime_verify.py` - stdlib-only verification helper invoked by `post_install.py`.
- `mcp_server/tests/test_doctor_installed_payload.py` - unit tests for doctor checks around payload/client state.
- `scripts/tests/beta-installer-hardening-guards.tests.ps1` - static guard tests for the new release/installer contracts.

Modify:

- `installer/RookSetup.iss` - package bundled runtime/manifests, remove release Python prerequisite, add update checkbox, wire new install flow.
- `installer/post_install.py` - use bundled runtime and transaction helpers; stop creating venvs from user Python in release install.
- `installer/pre-install-readme.txt` - document no Python prerequisite, offline install, same-user install, update checks.
- `mcp_server/src/rook/doctor.py` - validate payload manifest, client-config state, bundled runtime targeting, plugin registration, and provider configuration.
- `scripts/tests/release-installer-guards.tests.ps1` - extend existing guard coverage.
- `BUILDING.md`, `README.md`, `QUICK_START.md`, `.agents/skills/build-release/SKILL.md`, `.claude/skills/build-release/SKILL.md` - update release/install docs after behavior is implemented.

Do not change `src/RookNative/*.vcxproj` unless a later reviewed task explicitly requires project-file changes.

---

### Task 1: Release Manifest And Evidence Contract

**Files:**
- Create: `scripts/release/Build-RookPayloadManifest.ps1`
- Create: `scripts/release/Test-RookPayloadManifest.ps1`
- Create: `scripts/release/New-RookReleaseManifest.ps1`
- Create: `scripts/tests/beta-installer-hardening-guards.tests.ps1`
- Modify: `installer/RookSetup.iss`
- Modify: `scripts/tests/release-installer-guards.tests.ps1`

- [ ] **Step 1: Write failing guard tests for manifest artifacts**

Add these checks to `scripts/tests/beta-installer-hardening-guards.tests.ps1`:

```powershell
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$InstallerScript = Join-Path $RepoRoot 'installer\RookSetup.iss'

function Assert-Contains {
    param([string]$Text, [string]$Expected, [string]$Message)
    if (-not $Text.Contains($Expected)) { throw $Message }
}

function Assert-PathExists {
    param([string]$Path, [string]$Message)
    if (-not (Test-Path -LiteralPath $Path)) { throw $Message }
}

Assert-PathExists (Join-Path $RepoRoot 'scripts\release\Build-RookPayloadManifest.ps1') 'Missing payload manifest builder.'
Assert-PathExists (Join-Path $RepoRoot 'scripts\release\Test-RookPayloadManifest.ps1') 'Missing payload manifest validator.'
Assert-PathExists (Join-Path $RepoRoot 'scripts\release\New-RookReleaseManifest.ps1') 'Missing release manifest builder.'

$iss = Get-Content -Path $InstallerScript -Raw
Assert-Contains $iss 'rook-payload-manifest.json' 'Installer must package the payload manifest.'
Assert-Contains $iss 'installed-version.json' 'Installer must write installed-version state.'
Assert-Contains $iss 'client-config-state.json' 'Installer must create durable client config state.'

Write-Host 'Beta installer hardening guard tests passed.'
```

- [ ] **Step 2: Run the guard test and verify it fails**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\beta-installer-hardening-guards.tests.ps1
```

Expected: failure mentioning the missing payload manifest builder.

- [ ] **Step 3: Implement `Build-RookPayloadManifest.ps1`**

Create `scripts/release/Build-RookPayloadManifest.ps1` with parameters and schema:

```powershell
param(
    [Parameter(Mandatory=$true)][string]$PayloadRoot,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [string[]]$ExcludeRelativePath = @(
        'rook-payload-manifest.json',
        'installed-version.json',
        'update-settings.json',
        'client-config-state.json',
        'logs',
        'data',
        'config'
    )
)

$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath($PayloadRoot)
$files = Get-ChildItem -LiteralPath $root -File -Recurse | Where-Object {
    $relative = [System.IO.Path]::GetRelativePath($root, $_.FullName).Replace('\', '/')
    foreach ($excluded in $ExcludeRelativePath) {
        if ($relative -eq $excluded -or $relative.StartsWith($excluded.TrimEnd('/') + '/')) {
            return $false
        }
    }
    return $true
}

$entries = foreach ($file in $files) {
    $relative = [System.IO.Path]::GetRelativePath($root, $file.FullName).Replace('\', '/')
    [ordered]@{
        path = $relative
        size = $file.Length
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$manifest = [ordered]@{
    schemaVersion = 1
    generatedAt = (Get-Date).ToUniversalTime().ToString('o')
    payloadRoot = $root
    staticFiles = @($entries)
    excludes = @($ExcludeRelativePath)
}

$parent = Split-Path -Parent $OutputPath
if ($parent -and -not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
Write-Host "Wrote payload manifest: $OutputPath"
```

- [ ] **Step 4: Implement `Test-RookPayloadManifest.ps1`**

Create `scripts/release/Test-RookPayloadManifest.ps1`:

```powershell
param(
    [Parameter(Mandatory=$true)][string]$PayloadRoot,
    [Parameter(Mandatory=$true)][string]$ManifestPath,
    [string]$ReportPath
)

$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath($PayloadRoot)
$manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if ($manifest.schemaVersion -ne 1) { throw 'payload manifest schemaVersion must be 1' }

$failures = @()
foreach ($entry in @($manifest.staticFiles)) {
    $path = Join-Path $root ([string]$entry.path)
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        $failures += "missing: $($entry.path)"
        continue
    }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne [string]$entry.sha256) {
        $failures += "hash mismatch: $($entry.path)"
    }
}

$report = [ordered]@{
    schemaVersion = 1
    manifest = [System.IO.Path]::GetFullPath($ManifestPath)
    payloadRoot = $root
    checkedFiles = @($manifest.staticFiles).Count
    success = ($failures.Count -eq 0)
    failures = @($failures)
}

if ($ReportPath) {
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
}
if ($failures.Count -gt 0) { throw ($failures -join '; ') }
Write-Host "Payload manifest validation passed: $($report.checkedFiles) files"
```

- [ ] **Step 5: Implement `New-RookReleaseManifest.ps1`**

Create `scripts/release/New-RookReleaseManifest.ps1`:

```powershell
param(
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$InstallerPath,
    [Parameter(Mandatory=$true)][string]$PayloadManifestPath,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [string[]]$ReportPath = @(),
    [string[]]$RequiredReportName = @(
        'build-identity-report.json',
        'native-dependency-report.json',
        'managed-dependency-report.json',
        'python-runtime-report.json',
        'rook-mcp-wheel-report.json',
        'wheelhouse-lock-report.json',
        'pip-audit-report.json',
        'runtime-scan-report.json',
        'license-scan-report.json',
        'ffmpeg-compliance-report.json',
        'payload-manifest-validation.json',
        'installer-smoke-summary.md',
        'network-isolation-evidence.json',
        'rhino-smoke-summary.md',
        'mcp-client-config-report.json',
        'update-check-report.json'
    )
)

$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') { throw 'Version must be X.Y.Z' }
if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) { throw "Installer missing: $InstallerPath" }
if (-not (Test-Path -LiteralPath $PayloadManifestPath -PathType Leaf)) { throw "Payload manifest missing: $PayloadManifestPath" }

$reports = foreach ($path in $ReportPath) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required report missing: $path" }
    [ordered]@{
        fileName = Split-Path -Leaf $path
        sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$actualReportNames = @($reports | ForEach-Object { $_.fileName })
foreach ($required in $RequiredReportName) {
    if ($actualReportNames -notcontains $required) {
        throw "Missing required release evidence report: $required"
    }
}

$manifest = [ordered]@{
    schemaVersion = 1
    product = 'Rook'
    version = $Version
    channel = 'beta'
    generatedAt = (Get-Date).ToUniversalTime().ToString('o')
    installer = [ordered]@{
        fileName = Split-Path -Leaf $InstallerPath
        sha256 = (Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    payloadManifest = [ordered]@{
        fileName = Split-Path -Leaf $PayloadManifestPath
        sha256 = (Get-FileHash -LiteralPath $PayloadManifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    reports = @($reports)
}

$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
Write-Host "Wrote release manifest: $OutputPath"
```

- [ ] **Step 6: Wire manifest file references into `installer/RookSetup.iss`**

Add manifest file sources once the release build stages them:

```ini
; --- Release manifests ---
Source: "{#RepoRoot}\artifacts\release\rook-payload-manifest.json"; DestDir: "{app}"; Flags: ignoreversion
```

Do not add `rook-release-manifest.json` to the installer; it is generated after final installer signing and published with the release.

- [ ] **Step 7: Run tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\beta-installer-hardening-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: both pass.

- [ ] **Step 8: Commit**

Commit only files touched in this task:

```powershell
git add scripts\release\Build-RookPayloadManifest.ps1 scripts\release\Test-RookPayloadManifest.ps1 scripts\release\New-RookReleaseManifest.ps1 scripts\tests\beta-installer-hardening-guards.tests.ps1 installer\RookSetup.iss scripts\tests\release-installer-guards.tests.ps1
git commit -m "release: add installer payload manifest contract"
```

---

### Task 2: Bundled Python Runtime And Sealed Wheelhouse

**Files:**
- Create: `scripts/release/Build-RookMcpWheel.ps1`
- Create: `scripts/release/Build-RookWheelhouse.ps1`
- Create: `scripts/release/Build-RookPythonRuntime.ps1`
- Create: `scripts/release/Test-RookPythonRuntime.ps1`
- Create or update: `mcp_server/requirements-lock.txt`
- Create: `scripts/release/release-tools-requirements.txt`
- Modify: `installer/RookSetup.iss`
- Modify: `installer/post_install.py`
- Modify: `scripts/tests/beta-installer-hardening-guards.tests.ps1`

- [ ] **Step 1: Add failing tests for no release-time user Python dependency**

Extend `scripts/tests/beta-installer-hardening-guards.tests.ps1`:

```powershell
$postInstall = Get-Content -Path (Join-Path $RepoRoot 'installer\post_install.py') -Raw
$iss = Get-Content -Path $InstallerScript -Raw
Assert-Contains $iss 'rook-runtime' 'Installer must package the bundled Rook runtime.'
Assert-PathExists (Join-Path $RepoRoot 'scripts\release\Build-RookMcpWheel.ps1') 'Missing first-party rook-mcp wheel builder.'
Assert-PathExists (Join-Path $RepoRoot 'scripts\release\Build-RookWheelhouse.ps1') 'Missing sealed wheelhouse builder.'
Assert-PathExists (Join-Path $RepoRoot 'mcp_server\requirements-lock.txt') 'Missing flat hashed runtime requirements lock.'
Assert-PathExists (Join-Path $RepoRoot 'scripts\release\release-tools-requirements.txt') 'Missing pinned release tooling requirements.'
if ($iss.Contains('GetPythonPath') -or $iss.Contains('PythonFound')) {
    throw 'Release installer must not use Python prerequisite detection.'
}
if ($postInstall.Contains('pip", "install"') -or $postInstall.Contains("pip', 'install'")) {
    throw 'Release post_install.py must not run pip install on the user machine.'
}
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\beta-installer-hardening-guards.tests.ps1
```

Expected: failure because current installer still has Python detection and `post_install.py` still uses pip.

- [ ] **Step 3: Create the runtime dependency lock and release-tooling lock**

Create or update `mcp_server/requirements-lock.txt` as the canonical third-party runtime dependency closure. It must be a flat requirements file:

- every installable requirement is fully pinned with `==`.
- every installable requirement has at least one `--hash=sha256:<64 hex chars>`.
- all transitive runtime dependencies are present explicitly.
- extras, environment markers, direct URLs, VCS refs, editable installs, local paths, nested `-r`/`-c` includes, sdists, and ambiguous platform markers are forbidden.
- first-party `rook-mcp` is not listed here; Step 4 builds it from the current release commit, writes `rook-mcp-wheel-report.json`, and Step 5 passes that exact reported wheel/report pair into the wheelhouse builder.

Create `scripts/release/release-tools-requirements.txt` for release-build tooling. Pin `build`, `pip-audit`, and any other release-only tooling here with hashes. These tools are build-machine prerequisites only and are not shipped in the installer runtime.

- [ ] **Step 4: Implement `Build-RookMcpWheel.ps1`**

Create `scripts/release/Build-RookMcpWheel.ps1`. This script builds the first-party MCP server wheel from the current release commit and writes `rook-mcp-wheel-report.json`. `Build-RookWheelhouse.ps1` must consume this report and reject any wheel whose hash, version, or source commit does not match.

```powershell
param(
    [Parameter(Mandatory=$true)][string]$RepoRoot,
    [Parameter(Mandatory=$true)][string]$ReleasePythonExe,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [Parameter(Mandatory=$true)][string]$ReportPath
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $ReleasePythonExe -PathType Leaf)) { throw "Release Python missing: $ReleasePythonExe" }
$repo = [System.IO.Path]::GetFullPath($RepoRoot)
$mcpRoot = Join-Path $repo 'mcp_server'
if (-not (Test-Path -LiteralPath (Join-Path $mcpRoot 'pyproject.toml') -PathType Leaf)) { throw "mcp_server pyproject missing: $mcpRoot" }

$sourceCommit = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($sourceCommit)) { throw 'Could not resolve source commit.' }
$dirty = (& git -C $repo status --porcelain -- mcp_server).Trim()
if (-not [string]::IsNullOrWhiteSpace($dirty)) { throw "mcp_server has uncommitted changes; build the first-party wheel from a committed release state." }

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
Remove-Item -LiteralPath (Join-Path $OutputDir 'rook_mcp-*.whl') -Force -ErrorAction SilentlyContinue
& $ReleasePythonExe -m build --wheel --no-isolation --outdir $OutputDir $mcpRoot
if ($LASTEXITCODE -ne 0) { throw 'rook-mcp wheel build failed' }
$wheel = Get-ChildItem -LiteralPath $OutputDir -File -Filter 'rook_mcp-*.whl' | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $wheel) { throw 'rook-mcp wheel was not produced.' }
if ($wheel.Name -notmatch '^rook_mcp-(?<version>[^-]+)-') { throw "Could not parse rook-mcp wheel version: $($wheel.Name)" }

$report = [ordered]@{
    schemaVersion = 1
    sourceCommit = $sourceCommit
    sourceTree = [System.IO.Path]::GetFullPath($mcpRoot)
    version = $Matches.version
    wheelPath = [System.IO.Path]::GetFullPath($wheel.FullName)
    wheelFileName = $wheel.Name
    wheelSha256 = (Get-FileHash -LiteralPath $wheel.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    wheelSize = $wheel.Length
    builtAt = (Get-Date).ToUniversalTime().ToString('o')
    buildTool = 'python -m build --wheel --no-isolation'
    success = $true
}
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
Write-Host "Wrote rook-mcp wheel report: $ReportPath"
```

- [ ] **Step 5: Implement `Build-RookWheelhouse.ps1`**

Create `scripts/release/Build-RookWheelhouse.ps1`. This script is the only place release-time third-party package download can happen. It must consume a hash-pinned third-party requirements lock plus the current-commit `rook-mcp` wheel/report from `Build-RookMcpWheel.ps1`; it must not accept source directories or unreported wheels as install inputs. The requirements lock represents the third-party dependency closure. The first-party `rook-mcp` wheel is copied into the sealed wheelhouse only after its report proves source commit, version, and hash, then it is later installed from that wheel with `--no-deps`.

```powershell
param(
    [Parameter(Mandatory=$true)][string]$RepoRoot,
    [Parameter(Mandatory=$true)][string]$RequirementsLockPath,
    [Parameter(Mandatory=$true)][string]$RookMcpWheelPath,
    [Parameter(Mandatory=$true)][string]$RookMcpWheelReportPath,
    [Parameter(Mandatory=$true)][string]$WheelhouseDir,
    [Parameter(Mandatory=$true)][string]$ReportPath
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $RequirementsLockPath -PathType Leaf)) { throw "Requirements lock missing: $RequirementsLockPath" }
if (-not (Test-Path -LiteralPath $RookMcpWheelPath -PathType Leaf)) { throw "rook-mcp wheel missing: $RookMcpWheelPath" }
if (-not (Test-Path -LiteralPath $RookMcpWheelReportPath -PathType Leaf)) { throw "rook-mcp wheel report missing: $RookMcpWheelReportPath" }
if ((Split-Path -Leaf $RookMcpWheelPath) -notmatch '^rook_mcp-.+\.whl$') { throw "rook-mcp artifact must be a wheel: $RookMcpWheelPath" }

$rookWheelReport = Get-Content -LiteralPath $RookMcpWheelReportPath -Raw | ConvertFrom-Json
if (-not $rookWheelReport.success) { throw 'rook-mcp wheel report did not pass.' }
$currentCommit = (& git -C $RepoRoot rev-parse HEAD).Trim()
if ([string]$rookWheelReport.sourceCommit -ne $currentCommit) { throw "rook-mcp wheel source commit mismatch. report=$($rookWheelReport.sourceCommit) current=$currentCommit" }
$reportedWheelPath = [System.IO.Path]::GetFullPath([string]$rookWheelReport.wheelPath)
$actualWheelPath = [System.IO.Path]::GetFullPath($RookMcpWheelPath)
if ($reportedWheelPath -ne $actualWheelPath) { throw "rook-mcp wheel path does not match wheel report. report=$reportedWheelPath actual=$actualWheelPath" }
if ([string]$rookWheelReport.wheelFileName -ne (Split-Path -Leaf $RookMcpWheelPath)) { throw 'rook-mcp wheel filename does not match wheel report.' }
$actualRookHash = (Get-FileHash -LiteralPath $RookMcpWheelPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualRookHash -ne [string]$rookWheelReport.wheelSha256) { throw 'rook-mcp wheel hash does not match wheel report.' }

New-Item -ItemType Directory -Path $WheelhouseDir -Force | Out-Null
Copy-Item -LiteralPath $RookMcpWheelPath -Destination $WheelhouseDir -Force

function Test-FlatHashedRequirementsLock([string]$Path) {
    $rawLines = Get-Content -LiteralPath $Path
    $logical = New-Object System.Collections.Generic.List[string]
    $current = ''
    foreach ($line in $rawLines) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith('#')) { continue }
        if ($trimmed.EndsWith('\')) {
            $current += ' ' + $trimmed.Substring(0, $trimmed.Length - 1).Trim()
            continue
        }
        $logical.Add(($current + ' ' + $trimmed).Trim())
        $current = ''
    }
    if ($current.Trim().Length -gt 0) { throw 'Requirements lock has dangling line continuation.' }
    if ($logical.Count -eq 0) { throw 'Requirements lock is empty.' }

    foreach ($entry in $logical) {
        if ($entry -match '^\s*(-r|--requirement|-c|--constraint)\b') { throw "Nested requirement/constraint files are forbidden: $entry" }
        if ($entry -match '^\s*(-e|--editable)\b|file:|git\+|://|\.tar\.gz\b|\.zip\b') { throw "Editable, local, VCS, URL, and sdist entries are forbidden: $entry" }
        if ($entry -match ';') { throw "Environment markers are forbidden in the runtime lock: $entry" }
        if ($entry -match '^[A-Za-z0-9_.-]+\[') { throw "Extras are forbidden in the runtime lock: $entry" }
        if ($entry -notmatch '^[A-Za-z0-9_.-]+==[A-Za-z0-9_.!+-]+(\s+--hash=sha256:[a-fA-F0-9]{64})+$') {
            throw "Requirements lock entries must be exact pins with sha256 hashes: $entry"
        }
    }
}

Test-FlatHashedRequirementsLock -Path $RequirementsLockPath

python -m pip download --require-hashes --only-binary=:all: --no-deps --dest $WheelhouseDir -r $RequirementsLockPath
if ($LASTEXITCODE -ne 0) { throw 'pip download from hash-pinned lock failed' }

$wheels = Get-ChildItem -LiteralPath $WheelhouseDir -File -Filter '*.whl'
if (-not ($wheels | Where-Object { $_.Name -like 'rook_mcp-*.whl' })) { throw 'Wheelhouse does not contain rook-mcp wheel.' }

$entries = foreach ($wheel in $wheels) {
    [ordered]@{
        fileName = $wheel.Name
        sha256 = (Get-FileHash -LiteralPath $wheel.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        size = $wheel.Length
    }
}

[ordered]@{
    schemaVersion = 1
    requirementsLock = [System.IO.Path]::GetFullPath($RequirementsLockPath)
    rookMcpWheelReport = [System.IO.Path]::GetFullPath($RookMcpWheelReportPath)
    rookMcp = $rookWheelReport
    wheelhouse = [System.IO.Path]::GetFullPath($WheelhouseDir)
    wheels = @($entries)
    success = $true
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
Write-Host "Wrote wheelhouse lock report: $ReportPath"
```

- [ ] **Step 6: Implement `Build-RookPythonRuntime.ps1`**

Create a release-build script that constructs `artifacts\release\rook-runtime` from a release-staged CPython runtime directory and a locked wheelhouse. The release builder provides `-PythonRuntimeSourceDir`; user install never discovers or uses system Python.

```powershell
param(
    [Parameter(Mandatory=$true)][string]$PythonRuntimeSourceDir,
    [Parameter(Mandatory=$true)][string]$WheelhouseDir,
    [Parameter(Mandatory=$true)][string]$RequirementsLockPath,
    [Parameter(Mandatory=$true)][string]$OutputRoot,
    [Parameter(Mandatory=$true)][string]$WheelhouseLockReportPath
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $PythonRuntimeSourceDir -PathType Container)) { throw "PythonRuntimeSourceDir missing: $PythonRuntimeSourceDir" }
if (-not (Test-Path -LiteralPath $WheelhouseDir -PathType Container)) { throw "WheelhouseDir missing: $WheelhouseDir" }
if (-not (Test-Path -LiteralPath $RequirementsLockPath -PathType Leaf)) { throw "RequirementsLockPath missing: $RequirementsLockPath" }
if (-not (Test-Path -LiteralPath $WheelhouseLockReportPath -PathType Leaf)) { throw "WheelhouseLockReportPath missing: $WheelhouseLockReportPath" }

$runtimeRoot = Join-Path $OutputRoot 'rook-runtime'
$pythonDir = Join-Path $runtimeRoot 'python'
$siteDir = Join-Path $pythonDir 'Lib\site-packages'
New-Item -ItemType Directory -Path $pythonDir,$siteDir -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PythonRuntimeSourceDir '*') -Destination $pythonDir -Recurse -Force
$PythonExe = Join-Path $pythonDir 'python.exe'
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { throw "Staged runtime missing python.exe: $PythonExe" }

$lockReport = Get-Content -LiteralPath $WheelhouseLockReportPath -Raw | ConvertFrom-Json
if (-not $lockReport.success) { throw 'wheelhouse lock report did not pass' }
if (-not (@($lockReport.wheels).fileName | Where-Object { $_ -like 'rook_mcp-*.whl' })) { throw 'wheelhouse lock report does not include rook-mcp wheel' }

$rookWheel = Get-ChildItem -LiteralPath $WheelhouseDir -File -Filter 'rook_mcp-*.whl' | Select-Object -First 1
if (-not $rookWheel) { throw 'sealed wheelhouse missing rook-mcp wheel' }
$rookEntry = @($lockReport.wheels) | Where-Object { $_.fileName -eq $rookWheel.Name } | Select-Object -First 1
if (-not $rookEntry) { throw "wheelhouse lock report missing entry for $($rookWheel.Name)" }
$rookHash = (Get-FileHash -LiteralPath $rookWheel.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if ($rookHash -ne [string]$rookEntry.sha256) { throw "rook-mcp wheel hash mismatch: $($rookWheel.Name)" }

& $PythonExe -m pip install --no-index --find-links $WheelhouseDir --require-hashes --only-binary=:all: --target $siteDir -r $RequirementsLockPath
if ($LASTEXITCODE -ne 0) { throw 'sealed third-party package install failed' }
& $PythonExe -m pip install --no-index --find-links $WheelhouseDir --only-binary=:all: --no-deps --target $siteDir $rookWheel.FullName
if ($LASTEXITCODE -ne 0) { throw 'sealed rook-mcp wheel install failed' }

$report = [ordered]@{
    schemaVersion = 1
    pythonRuntimeSourceDir = [System.IO.Path]::GetFullPath($PythonRuntimeSourceDir)
    wheelhouse = [System.IO.Path]::GetFullPath($WheelhouseDir)
    requirementsLock = [System.IO.Path]::GetFullPath($RequirementsLockPath)
    wheelhouseLockReport = [System.IO.Path]::GetFullPath($WheelhouseLockReportPath)
    runtimeRoot = [System.IO.Path]::GetFullPath($runtimeRoot)
    generatedAt = (Get-Date).ToUniversalTime().ToString('o')
}
$report | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $runtimeRoot 'python-runtime-report.json') -Encoding UTF8
Write-Host "Built Rook runtime: $runtimeRoot"
```

This task is incomplete unless `artifacts\release\rook-runtime\python\python.exe` exists and `Test-RookPythonRuntime.ps1` proves both isolated startup and normal Rook startup from that staged executable.

- [ ] **Step 7: Implement `Test-RookPythonRuntime.ps1`**

Create a verifier that proves isolated and normal startup:

```powershell
param(
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [Parameter(Mandatory=$true)][string]$PythonExe,
    [Parameter(Mandatory=$true)][string]$ReportPath
)

$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = ''
$env:PYTHONHOME = ''

$isolated = & $PythonExe -I -c "import sys, site, os; print('ok'); print(sys.executable); print(site.ENABLE_USER_SITE)" 2>&1
if ($LASTEXITCODE -ne 0 -or ($isolated -join "`n") -notmatch 'ok') { throw "isolated Python startup failed: $isolated" }

$normal = & $PythonExe -c "import rook; import rook.doctor; print('rook-ok')" 2>&1
if ($LASTEXITCODE -ne 0 -or ($normal -join "`n") -notmatch 'rook-ok') { throw "normal Rook startup failed: $normal" }

[ordered]@{
    schemaVersion = 1
    runtimeRoot = [System.IO.Path]::GetFullPath($RuntimeRoot)
    pythonExe = [System.IO.Path]::GetFullPath($PythonExe)
    isolatedStartup = 'passed'
    normalRookStartup = 'passed'
} | ConvertTo-Json -Depth 4 | Set-Content -Path $ReportPath -Encoding UTF8
Write-Host "Rook Python runtime validation passed."
```

- [ ] **Step 8: Update `installer/RookSetup.iss` runtime packaging**

Add release runtime sources and remove Python prerequisite execution from `[Run]`.

Expected shape:

```ini
#define RookRuntimeDir RepoRoot + "\artifacts\release\rook-runtime"

; --- Bundled Rook runtime ---
Source: "{#RookRuntimeDir}\*"; DestDir: "{localappdata}\Rook\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
```

Remove or bypass `[Code]` functions whose only purpose is user Python detection for release install. Keep any API-key page only if it writes durable config and does not depend on Python.

- [ ] **Step 9: Rewrite `installer/post_install.py` to use bundled runtime**

Replace venv creation/pip installation with lookup of the bundled runtime:

```python
def get_bundled_python(runtime_root: Path) -> Path:
    candidates = [
        runtime_root / "python" / "python.exe",
        runtime_root / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Bundled Rook Python runtime not found under {runtime_root}")
```

The release install path must call `get_bundled_python(runtime_root)` and then generate client configs using that path. It must not call `venv`, `pip`, or user `sys.executable` except when running as a source/dev bootstrap outside the release installer.

- [ ] **Step 10: Run tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\beta-installer-hardening-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: both pass.

- [ ] **Step 11: Commit**

```powershell
git add mcp_server\requirements-lock.txt scripts\release\release-tools-requirements.txt scripts\release\Build-RookMcpWheel.ps1 scripts\release\Build-RookWheelhouse.ps1 scripts\release\Build-RookPythonRuntime.ps1 scripts\release\Test-RookPythonRuntime.ps1 installer\RookSetup.iss installer\post_install.py scripts\tests\beta-installer-hardening-guards.tests.ps1
git commit -m "installer: use bundled Rook Python runtime"
```

---

### Task 3: Runtime Security, License, And Native/Managed Closure Gates

**Files:**
- Create: `scripts/release/Invoke-RookRuntimeSecurityScan.ps1`
- Create: `scripts/release/license-policy.json`
- Create: `scripts/release/Test-RookNativeClosure.ps1`
- Create: `scripts/release/Test-RookManagedClosure.ps1`
- Modify: `scripts/tests/beta-installer-hardening-guards.tests.ps1`
- Modify: `BUILDING.md`

- [ ] **Step 1: Add failing evidence-file guard tests**

Extend `scripts/tests/beta-installer-hardening-guards.tests.ps1`:

```powershell
foreach ($scriptName in @(
    'Invoke-RookRuntimeSecurityScan.ps1',
    'Test-RookNativeClosure.ps1',
    'Test-RookManagedClosure.ps1'
)) {
    Assert-PathExists (Join-Path $RepoRoot "scripts\release\$scriptName") "Missing release gate script: $scriptName"
}
Assert-PathExists (Join-Path $RepoRoot 'scripts\release\license-policy.json') 'Missing release license policy.'
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\beta-installer-hardening-guards.tests.ps1
```

Expected: missing release gate script or license policy failure.

- [ ] **Step 3: Create release license policy**

Create `scripts/release/license-policy.json`:

```json
{
  "schemaVersion": 1,
  "prohibitedLicenses": [
    "AGPL-3.0-only",
    "AGPL-3.0-or-later",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "SSPL-1.0"
  ],
  "allowedMissingLicensePackages": []
}
```

Every package with missing license metadata must either be fixed upstream in the sealed runtime evidence or explicitly listed in `allowedMissingLicensePackages` with reviewer approval in the release notes. Do not add license exceptions inside the scan script.

- [ ] **Step 4: Implement runtime static scan**

Create `scripts/release/Invoke-RookRuntimeSecurityScan.ps1`. This script must consume the wheelhouse lock report, a `pip-audit` JSON report generated from the same requirements lock using the pinned release tooling from `scripts\release\release-tools-requirements.txt`, and a committed license policy file. It must fail if any installed package is not represented in the locked wheelhouse report.

The scan is intentionally conservative: any `pip-audit` vulnerability in the sealed runtime is release-blocking. Severity/reachability exceptions are handled before this report is accepted, either by updating/removing the dependency or by a separately reviewed release exception that produces an accepted audit report. The script itself does not downgrade vulnerability findings.

```powershell
param(
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [Parameter(Mandatory=$true)][string]$WheelhouseLockReportPath,
    [Parameter(Mandatory=$true)][string]$PipAuditReportPath,
    [Parameter(Mandatory=$true)][string]$LicensePolicyPath,
    [Parameter(Mandatory=$true)][string]$OutputDir
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
if (-not (Test-Path -LiteralPath $WheelhouseLockReportPath -PathType Leaf)) { throw "Missing wheelhouse lock report: $WheelhouseLockReportPath" }
if (-not (Test-Path -LiteralPath $PipAuditReportPath -PathType Leaf)) { throw "Missing pip-audit report: $PipAuditReportPath" }
if (-not (Test-Path -LiteralPath $LicensePolicyPath -PathType Leaf)) { throw "Missing license policy: $LicensePolicyPath" }

$badPackages = @(
    @{ name = 'litellm'; version = '1.82.7'; reason = 'known compromised release' },
    @{ name = 'litellm'; version = '1.82.8'; reason = 'known compromised release' }
)
$policy = Get-Content -LiteralPath $LicensePolicyPath -Raw | ConvertFrom-Json
$prohibitedLicenses = @($policy.prohibitedLicenses)
$allowedMissingLicensePackages = @($policy.allowedMissingLicensePackages)
$wheelhouse = Get-Content -LiteralPath $WheelhouseLockReportPath -Raw | ConvertFrom-Json
if (-not $wheelhouse.success) { throw 'Wheelhouse lock report is not successful.' }
$lockedWheelNames = @($wheelhouse.wheels | ForEach-Object { [string]$_.fileName })

$metadataFiles = Get-ChildItem -LiteralPath $RuntimeRoot -Recurse -File -Filter 'METADATA'
$packages = foreach ($metadata in $metadataFiles) {
    $text = Get-Content -LiteralPath $metadata.FullName -Raw
    $name = [regex]::Match($text, '(?m)^Name:\s*(.+)$').Groups[1].Value.Trim()
    $version = [regex]::Match($text, '(?m)^Version:\s*(.+)$').Groups[1].Value.Trim()
    $license = [regex]::Match($text, '(?m)^License:\s*(.+)$').Groups[1].Value.Trim()
    $distInfo = Split-Path -Parent $metadata.FullName
    $recordPath = Join-Path $distInfo 'RECORD'
    [ordered]@{ name = $name; version = $version; license = $license; metadata = $metadata.FullName; record = $recordPath }
}

$pthFiles = Get-ChildItem -LiteralPath $RuntimeRoot -Recurse -File -Filter '*.pth'
$scriptFiles = Get-ChildItem -LiteralPath $RuntimeRoot -Recurse -File | Where-Object { $_.FullName -match '\\Scripts\\|/Scripts/' -or $_.Extension -in '.exe','.dll','.pyd' }
$findings = @()
foreach ($pkg in $packages) {
    foreach ($bad in $badPackages) {
        if ($pkg.name -eq $bad.name -and $pkg.version -eq $bad.version) {
            $findings += [ordered]@{ severity = 'critical'; package = $pkg.name; version = $pkg.version; reason = $bad.reason }
        }
    }
    $wheelPrefix = (($pkg.name -replace '[-.]','_') + '-' + $pkg.version).ToLowerInvariant()
    if (-not ($lockedWheelNames | Where-Object { $_.ToLowerInvariant().StartsWith($wheelPrefix) })) {
        $findings += [ordered]@{ severity = 'critical'; package = $pkg.name; version = $pkg.version; reason = 'installed package is not represented in wheelhouse-lock-report.json' }
    }
    if (-not (Test-Path -LiteralPath $pkg.record -PathType Leaf)) {
        $findings += [ordered]@{ severity = 'critical'; package = $pkg.name; version = $pkg.version; reason = 'missing RECORD file' }
    }
    if ([string]::IsNullOrWhiteSpace($pkg.license) -and ($allowedMissingLicensePackages -notcontains $pkg.name)) {
        $findings += [ordered]@{ severity = 'license'; package = $pkg.name; version = $pkg.version; reason = 'missing license metadata' }
    }
    foreach ($license in $prohibitedLicenses) {
        if (-not [string]::IsNullOrWhiteSpace($pkg.license) -and $pkg.license -match [regex]::Escape($license)) {
            $findings += [ordered]@{ severity = 'license'; package = $pkg.name; version = $pkg.version; reason = "prohibited license: $license" }
        }
    }
}
foreach ($pth in $pthFiles) {
    $content = Get-Content -LiteralPath $pth.FullName -Raw
    if ($content -match 'import\s+|exec\s*\(|eval\s*\(') {
        $findings += [ordered]@{ severity = 'critical'; file = $pth.FullName; reason = 'startup hook code in .pth file' }
    }
}
$audit = Get-Content -LiteralPath $PipAuditReportPath -Raw | ConvertFrom-Json
foreach ($dependency in @($audit.dependencies)) {
    foreach ($vuln in @($dependency.vulns)) {
        $aliases = @($vuln.aliases)
        $id = if ($aliases.Count -gt 0) { $aliases[0] } else { $vuln.id }
        $fixVersions = @($vuln.fix_versions)
        $findings += [ordered]@{
            severity = 'vulnerability'
            package = $dependency.name
            version = $dependency.version
            reason = "pip-audit finding: $id"
            fixVersions = $fixVersions
            policy = 'release-blocking unless resolved before scan acceptance'
        }
    }
}

$runtimeReport = [ordered]@{
    schemaVersion = 1
    runtimeRoot = [System.IO.Path]::GetFullPath($RuntimeRoot)
    packages = @($packages)
    pthFiles = @($pthFiles | ForEach-Object { $_.FullName })
    nativeAndScriptPayloads = @($scriptFiles | ForEach-Object { $_.FullName })
    findings = @($findings | Where-Object { $_.severity -ne 'license' })
    success = (@($findings | Where-Object { $_.severity -ne 'license' }).Count -eq 0)
}
$licenseReport = [ordered]@{
    schemaVersion = 1
    packages = @($packages)
    findings = @($findings | Where-Object { $_.severity -eq 'license' })
    success = (@($findings | Where-Object { $_.severity -eq 'license' }).Count -eq 0)
}

$runtimeReport | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDir 'runtime-scan-report.json') -Encoding UTF8
$licenseReport | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDir 'license-scan-report.json') -Encoding UTF8
if (-not $runtimeReport.success) { throw 'runtime security scan failed' }
if (-not $licenseReport.success) { throw 'license scan failed' }
Write-Host 'Runtime security and license scan passed.'
```

- [ ] **Step 5: Implement native closure report**

Create `scripts/release/Test-RookNativeClosure.ps1`:

```powershell
param(
    [Parameter(Mandatory=$true)][string]$NativeRhpPath,
    [Parameter(Mandatory=$true)][string]$ReportPath,
    [string]$RhinoSystemDir
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $NativeRhpPath -PathType Leaf)) { throw "Native plugin missing: $NativeRhpPath" }

if (-not (Get-Command dumpbin.exe -ErrorAction SilentlyContinue)) { throw 'dumpbin.exe is required for native dependency closure. Run from a VS developer shell.' }
$baseline = @('kernel32.dll','user32.dll','gdi32.dll','advapi32.dll','shell32.dll','ole32.dll','oleaut32.dll','msvcrt.dll','vcruntime140.dll','vcruntime140_1.dll','ucrtbase.dll')
if (-not $RhinoSystemDir) { $RhinoSystemDir = 'C:\Program Files\Rhino 8\System' }
if (-not (Test-Path -LiteralPath (Join-Path $RhinoSystemDir 'Rhino.exe') -PathType Leaf)) {
    throw "Rhino 8 System directory could not be verified for native baseline: $RhinoSystemDir"
}
$pluginDir = Split-Path -Parent $NativeRhpPath
$localDlls = Get-ChildItem -LiteralPath $pluginDir -File -Filter '*.dll' | Select-Object -ExpandProperty Name
$rhinoDlls = Get-ChildItem -LiteralPath $RhinoSystemDir -File -Filter '*.dll' | Select-Object -ExpandProperty Name
$dumpbin = & dumpbin.exe /DEPENDENTS $NativeRhpPath 2>&1
if ($LASTEXITCODE -ne 0) { throw "dumpbin dependency walk failed: $dumpbin" }
$dependents = @(
    $dumpbin |
        Where-Object { $_ -match '^\s+[A-Za-z0-9_.-]+\.dll\s*$' } |
        ForEach-Object { $_.Trim().ToLowerInvariant() }
)
$localSet = @($localDlls | ForEach-Object { $_.ToLowerInvariant() })
$baselineSet = @($baseline | ForEach-Object { $_.ToLowerInvariant() })
$rhinoSet = @($rhinoDlls | ForEach-Object { $_.ToLowerInvariant() })
$missing = @($dependents | Where-Object {
    ($baselineSet -notcontains $_) -and
    ($localSet -notcontains $_) -and
    ($rhinoSet -notcontains $_)
})
if ($missing.Count -gt 0) { throw "Native dependency closure failed. Non-baseline, non-Rhino DLLs not shipped app-local: $($missing -join ', ')" }

$report = [ordered]@{
    schemaVersion = 1
    nativeRhpPath = [System.IO.Path]::GetFullPath($NativeRhpPath)
    pluginDirectory = [System.IO.Path]::GetFullPath($pluginDir)
    rhinoSystemDir = [System.IO.Path]::GetFullPath($RhinoSystemDir)
    baselineDlls = $baseline
    localDlls = @($localDlls)
    rhinoBaselineDlls = @($rhinoDlls)
    dependents = @($dependents)
    missingNonBaselineDlls = @($missing)
    success = ($missing.Count -eq 0)
}
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
Write-Host "Wrote native dependency report: $ReportPath"
```

- [ ] **Step 6: Implement managed closure report**

Create `scripts/release/Test-RookManagedClosure.ps1`:

```powershell
param(
    [Parameter(Mandatory=$true)][string]$CompanionRhpPath,
    [Parameter(Mandatory=$true)][string]$ReportPath,
    [string]$RhinoInstallDir
)

$ErrorActionPreference = 'Stop'
$runtimeConfig = [System.IO.Path]::ChangeExtension($CompanionRhpPath, '.runtimeconfig.json')
if (-not (Test-Path -LiteralPath $CompanionRhpPath -PathType Leaf)) { throw "Companion missing: $CompanionRhpPath" }
if (-not (Test-Path -LiteralPath $runtimeConfig -PathType Leaf)) { throw "Runtimeconfig missing: $runtimeConfig" }

$json = Get-Content -LiteralPath $runtimeConfig -Raw | ConvertFrom-Json
$tfm = [string]$json.runtimeOptions.tfm
if ($tfm -ne 'net7.0') { throw "Companion runtimeconfig must target net7.0, got $tfm" }
if (-not $RhinoInstallDir) {
    $rhinoExe = Get-ChildItem 'C:\Program Files\Rhino 8\System\Rhino.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($rhinoExe) { $RhinoInstallDir = Split-Path -Parent $rhinoExe.FullName }
}
if (-not $RhinoInstallDir -or -not (Test-Path -LiteralPath (Join-Path $RhinoInstallDir 'Rhino.exe') -PathType Leaf)) {
    throw 'Rhino 8 install directory could not be verified for managed .NET baseline.'
}
$rhinoCommon = Join-Path $RhinoInstallDir 'RhinoCommon.dll'
if (-not (Test-Path -LiteralPath $rhinoCommon -PathType Leaf)) {
    throw "RhinoCommon.dll missing from Rhino baseline: $rhinoCommon"
}

[ordered]@{
    schemaVersion = 1
    companionRhpPath = [System.IO.Path]::GetFullPath($CompanionRhpPath)
    runtimeConfig = [System.IO.Path]::GetFullPath($runtimeConfig)
    tfm = $tfm
    baseline = 'Rhino 8-provided .NET runtime'
    rhinoInstallDir = [System.IO.Path]::GetFullPath($RhinoInstallDir)
    rhinoCommon = [System.IO.Path]::GetFullPath($rhinoCommon)
    success = $true
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
Write-Host "Wrote managed dependency report: $ReportPath"
```

- [ ] **Step 7: Update docs with gate commands**

Add to `BUILDING.md` release section:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release\Test-RookNativeClosure.ps1 -NativeRhpPath src\RookNative\bin\Release\x64\RookNative.rhp -ReportPath artifacts\release\native-dependency-report.json
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release\Test-RookManagedClosure.ps1 -CompanionRhpPath src\Rook\bin\Release\net7.0\Rook.rhp -ReportPath artifacts\release\managed-dependency-report.json
python -m venv artifacts\release-tools\.venv
& .\artifacts\release-tools\.venv\Scripts\python.exe -m pip install --require-hashes -r scripts\release\release-tools-requirements.txt
& .\artifacts\release-tools\.venv\Scripts\pip-audit.exe -r mcp_server\requirements-lock.txt --format json --output artifacts\release\pip-audit-report.json
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release\Invoke-RookRuntimeSecurityScan.ps1 -RuntimeRoot artifacts\release\rook-runtime -WheelhouseLockReportPath artifacts\release\wheelhouse-lock-report.json -PipAuditReportPath artifacts\release\pip-audit-report.json -LicensePolicyPath scripts\release\license-policy.json -OutputDir artifacts\release
```

- [ ] **Step 8: Run tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\beta-installer-hardening-guards.tests.ps1
```

Expected: pass.

- [ ] **Step 9: Commit**

```powershell
git add scripts\release\Invoke-RookRuntimeSecurityScan.ps1 scripts\release\license-policy.json scripts\release\Test-RookNativeClosure.ps1 scripts\release\Test-RookManagedClosure.ps1 scripts\tests\beta-installer-hardening-guards.tests.ps1 BUILDING.md
git commit -m "release: add runtime security and closure gates"
```

---

### Task 4: Installer Transaction, Migration, And Rollback

**Files:**
- Create: `installer/install_state.py`
- Create: `installer/runtime_verify.py`
- Modify: `installer/post_install.py`
- Modify: `installer/RookSetup.iss`
- Modify: `scripts/tests/beta-installer-hardening-guards.tests.ps1`

- [ ] **Step 1: Add failing guard tests for transaction helpers**

Extend the guard test:

```powershell
Assert-PathExists (Join-Path $RepoRoot 'installer\install_state.py') 'Missing installer install_state.py helper.'
Assert-PathExists (Join-Path $RepoRoot 'installer\runtime_verify.py') 'Missing installer runtime_verify.py helper.'
$postInstall = Get-Content -Path (Join-Path $RepoRoot 'installer\post_install.py') -Raw
Assert-Contains $postInstall 'client-config-state.json' 'post_install.py must write durable client config state.'
Assert-Contains $iss 'staging\plugins\RookNative' 'Installer must stage Rhino plugin files outside the active plugin folder.'
Assert-Contains $postInstall 'backup_plugin_folder' 'post_install.py must back up the active Rhino plugin folder before activation.'
Assert-Contains $postInstall 'restore_plugin_folder' 'post_install.py must support plugin folder rollback.'
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\beta-installer-hardening-guards.tests.ps1
```

Expected: missing helper failure.

- [ ] **Step 3: Implement `installer/install_state.py`**

Create stdlib-only helpers:

```python
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    Path(tmp_name).replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_plugin_folder(plugin_dir: Path, backup_root: Path, payload_hash: str) -> Path | None:
    if not plugin_dir.exists():
        return None
    backup = backup_root / f"RookNative-{utc_stamp()}-{payload_hash[:12]}"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(plugin_dir, backup)
    return backup


def activate_plugin_folder(staged_plugin_dir: Path, active_plugin_dir: Path) -> None:
    if not staged_plugin_dir.exists():
        raise FileNotFoundError(f"staged plugin folder missing: {staged_plugin_dir}")
    if active_plugin_dir.exists():
        shutil.rmtree(active_plugin_dir)
    shutil.copytree(staged_plugin_dir, active_plugin_dir)


def restore_plugin_folder(backup_dir: Path, plugin_dir: Path) -> None:
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir)
    shutil.copytree(backup_dir, plugin_dir)


def write_client_config_state(config_dir: Path, state: dict[str, Any]) -> Path:
    state_path = config_dir / "client-config-state.json"
    atomic_write_json(state_path, state)
    return state_path
```

- [ ] **Step 4: Implement `installer/runtime_verify.py`**

Create:

```python
from __future__ import annotations

import json
from pathlib import Path

from install_state import sha256_file


def verify_payload_manifest(payload_root: Path, manifest_path: Path) -> list[str]:
    failures: list[str] = []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest.get("staticFiles", []):
        relative = entry["path"]
        expected = entry["sha256"]
        path = payload_root / relative
        if not path.exists():
            failures.append(f"missing: {relative}")
            continue
        actual = sha256_file(path)
        if actual.lower() != expected.lower():
            failures.append(f"hash mismatch: {relative}")
    return failures
```

- [ ] **Step 5: Update `post_install.py` transaction flow**

Modify `post_install.py` to:

- import `activate_plugin_folder`, `backup_plugin_folder`, `restore_plugin_folder`, `write_client_config_state`.
- compute payload manifest hash.
- backup the active plugin folder before calling `activate_plugin_folder`.
- activate plugin files from `{app}\staging\plugins\RookNative` into `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative`.
- write HKCU Rhino plugin registration only after the active folder has been replaced.
- verify HKCU registration points to the active folder before config rewrite.
- write `client-config-state.json` only after successful config writes.

The generated state shape must be:

```python
client_state = {
    "schemaVersion": 1,
    "payloadManifestSha256": payload_manifest_hash,
    "clients": [
        {
            "name": "codex",
            "selected": True,
            "configPath": str(user_config),
            "backupPath": str(backup_path),
            "entryFingerprint": entry_fingerprint,
            "command": managed_python_path,
            "cwd": str(mcp_server_dir),
            "envKeys": sorted(env_vars.keys()),
            "state": "installed",
        }
    ],
}
```

- [ ] **Step 6: Update Inno file staging**

Change `installer/RookSetup.iss` so all Rhino plugin files are copied to a staging folder, not directly to `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative`. The active folder must only be replaced by `post_install.py` after backup and staged validation.

```ini
Source: "install_state.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "runtime_verify.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#NativePlugin}"; DestDir: "{app}\staging\plugins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionDir}\Rook.rhp"; DestDir: "{app}\staging\plugins\RookNative"; Components: plugins; Flags: ignoreversion
```

Move every existing plugin-side source line that currently targets `{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative` or its `ffmpeg` child to the matching `{app}\staging\plugins\RookNative` path. Leave the `[Registry]` values pointing at the active `%APPDATA%` folder; registration is verified after activation.

- [ ] **Step 7: Run tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\beta-installer-hardening-guards.tests.ps1
python -m py_compile installer\post_install.py installer\install_state.py installer\runtime_verify.py
```

Expected: pass.

- [ ] **Step 8: Commit**

```powershell
git add installer\install_state.py installer\runtime_verify.py installer\post_install.py installer\RookSetup.iss scripts\tests\beta-installer-hardening-guards.tests.ps1
git commit -m "installer: add transactional install state"
```

---

### Task 5: Installer UX And Client Selection

**Files:**
- Modify: `installer/RookSetup.iss`
- Modify: `installer/post_install.py`
- Modify: `installer/pre-install-readme.txt`
- Modify: `scripts/tests/beta-installer-hardening-guards.tests.ps1`

- [ ] **Step 1: Add failing UX guard tests**

Extend guard tests:

```powershell
$iss = Get-Content -Path $InstallerScript -Raw
Assert-Contains $iss 'Check GitHub Releases for Rook updates' 'Installer must expose update-check checkbox.'
Assert-Contains $iss 'Claude Desktop' 'Installer must expose supported client selection.'
Assert-Contains $iss 'Codex CLI' 'Installer must expose supported client selection.'
Assert-Contains $iss 'Claude Code' 'Installer must expose supported client selection.'
Assert-Contains $iss 'DetectClaudeDesktop' 'Installer must default Claude Desktop checkbox from detection.'
Assert-Contains $iss 'DetectCodexCli' 'Installer must default Codex checkbox from detection.'
Assert-Contains $iss 'DetectClaudeCode' 'Installer must default Claude Code checkbox from detection.'
Assert-Contains $iss 'No Python prerequisite' 'Installer UX/docs must communicate no Python prerequisite.'
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\beta-installer-hardening-guards.tests.ps1
```

Expected: missing checkbox/client wording failure.

- [ ] **Step 3: Add Inno wizard/client selections**

In `installer/RookSetup.iss`, add custom checkbox page variables:

```pascal
var
  ClientPage: TInputOptionWizardPage;

function DetectClaudeDesktop(): Boolean;
begin
  Result := DirExists(ExpandConstant('{userappdata}\Claude'));
end;

function DetectClaudeCode(): Boolean;
begin
  Result := FileExists(ExpandConstant('{userprofile}\.claude.json')) or DirExists(ExpandConstant('{userprofile}\.claude'));
end;

function DetectCodexCli(): Boolean;
begin
  Result := DirExists(ExpandConstant('{userprofile}\.codex'));
end;

procedure InitializeWizard();
begin
  ClientPage := CreateInputOptionPage(wpSelectComponents,
    'MCP Client Configuration',
    'Choose which detected clients Rook should configure.',
    'Rook only modifies checked clients. Existing non-Rook MCP entries are preserved.',
    True, False);
  ClientPage.Add('Claude Desktop');
  ClientPage.Add('Claude Code');
  ClientPage.Add('Codex CLI');
  ClientPage.Add('Check GitHub Releases for Rook updates');
  ClientPage.Values[0] := DetectClaudeDesktop();
  ClientPage.Values[1] := DetectClaudeCode();
  ClientPage.Values[2] := DetectCodexCli();
  ClientPage.Values[3] := True;
end;
```

If an existing `InitializeWizard()` already exists, merge this into it rather than creating a second procedure.

- [ ] **Step 4: Pass selected clients to `post_install.py`**

Add code functions:

```pascal
function GetClientArgs(Param: String): String;
begin
  Result := '';
  if ClientPage.Values[0] then Result := Result + ' --claude-desktop';
  if ClientPage.Values[1] then Result := Result + ' --claude-code';
  if ClientPage.Values[2] then Result := Result + ' --codex';
  if ClientPage.Values[3] then Result := Result + ' --update-checks';
end;
```

Use `{code:GetClientArgs}` in the `post_install.py` command.

- [ ] **Step 5: Update `post_install.py` arguments**

Replace broad `--claude` behavior with explicit flags:

```python
parser.add_argument("--claude-desktop", action="store_true")
parser.add_argument("--claude-code", action="store_true")
parser.add_argument("--codex", action="store_true")
parser.add_argument("--update-checks", action="store_true")
```

Only call each client config writer if its flag is true.

- [ ] **Step 6: Update pre-install readme**

Add exact text to `installer/pre-install-readme.txt`:

```text
No Python prerequisite
Rook's beta installer includes its own runtime. You do not need to install Python, pip, or developer tools.

Client configuration
The installer only modifies MCP clients you select. It preserves unrelated MCP entries.

Update checks
The optional update check contacts GitHub Releases at most daily, sends no telemetry, and never downloads or runs updates automatically.
```

- [ ] **Step 7: Run tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\beta-installer-hardening-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: pass.

- [ ] **Step 8: Commit**

```powershell
git add installer\RookSetup.iss installer\post_install.py installer\pre-install-readme.txt scripts\tests\beta-installer-hardening-guards.tests.ps1
git commit -m "installer: add beta client selection UX"
```

---

### Task 6: `rook doctor` Installed-Payload Verification

**Files:**
- Modify: `mcp_server/src/rook/doctor.py`
- Create: `mcp_server/tests/test_doctor_installed_payload.py`

- [ ] **Step 1: Write failing doctor tests**

Create `mcp_server/tests/test_doctor_installed_payload.py`:

```python
import json
from pathlib import Path

from rook import doctor


def test_doctor_reports_payload_manifest_state(tmp_path, monkeypatch):
    app = tmp_path / "app"
    config = tmp_path / "config"
    app.mkdir()
    config.mkdir()
    payload = app / "rook-payload-manifest.json"
    payload.write_text(json.dumps({"schemaVersion": 1, "staticFiles": []}), encoding="utf-8")
    client_state = config / "client-config-state.json"
    client_state.write_text(json.dumps({"schemaVersion": 1, "clients": []}), encoding="utf-8")

    monkeypatch.setenv("ROOK_INSTALL_ROOT", str(app))
    monkeypatch.setenv("ROOK_CONFIG_DIR", str(config))
    result = doctor.run_doctor(json_output=True)

    names = {check["name"]: check["ok"] for check in result["checks"]}
    assert names["payload_manifest_present"] is True
    assert names["client_config_state_present"] is True


def test_doctor_flags_missing_client_config_state(tmp_path, monkeypatch):
    app = tmp_path / "app"
    config = tmp_path / "config"
    app.mkdir()
    config.mkdir()
    (app / "rook-payload-manifest.json").write_text(
        json.dumps({"schemaVersion": 1, "staticFiles": []}),
        encoding="utf-8",
    )

    monkeypatch.setenv("ROOK_INSTALL_ROOT", str(app))
    monkeypatch.setenv("ROOK_CONFIG_DIR", str(config))
    result = doctor.run_doctor(json_output=True)

    names = {check["name"]: check["ok"] for check in result["checks"]}
    assert names["client_config_state_present"] is False
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
cd mcp_server
pytest tests\test_doctor_installed_payload.py -q
```

Expected: failure because the doctor checks do not exist.

- [ ] **Step 3: Add doctor checks**

In `mcp_server/src/rook/doctor.py`, add helpers:

```python
def _path_from_env(name: str, fallback: str | None = None) -> Path | None:
    value = os.environ.get(name) or fallback
    return Path(value) if value else None


def _json_file_ok(path: Path, expected_schema: int = 1) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"malformed JSON: {exc}"
    if payload.get("schemaVersion") != expected_schema:
        return False, f"schemaVersion must be {expected_schema}"
    return True, "ok"
```

Add checks in `run_doctor`:

```python
install_root = _path_from_env("ROOK_INSTALL_ROOT")
config_dir = _path_from_env("ROOK_CONFIG_DIR")
if install_root:
    ok, detail = _json_file_ok(install_root / "rook-payload-manifest.json")
    checks.append({"name": "payload_manifest_present", "ok": ok, "detail": detail})
if config_dir:
    ok, detail = _json_file_ok(config_dir / "client-config-state.json")
    checks.append({"name": "client_config_state_present", "ok": ok, "detail": detail})
```

Match the existing `doctor.py` result shape exactly. If current checks use dataclasses/helpers, implement through those local patterns instead of appending raw dictionaries.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
cd mcp_server
pytest tests\test_doctor_installed_payload.py -q
```

Expected: pass.

- [ ] **Step 5: Run broader doctor-related tests**

Run:

```powershell
cd mcp_server
pytest tests -k doctor -q
```

Expected: pass or existing skips only.

- [ ] **Step 6: Commit**

```powershell
git add mcp_server\src\rook\doctor.py mcp_server\tests\test_doctor_installed_payload.py
git commit -m "doctor: verify installed payload state"
```

---

### Task 7: Release Publication Flow And Smoke Matrix

**Files:**
- Create: `scripts/release/Invoke-RookInstallerSmoke.ps1`
- Modify: `.agents/skills/build-release/SKILL.md`
- Modify: `.claude/skills/build-release/SKILL.md`
- Modify: `BUILDING.md`
- Modify: `scripts/tests/beta-installer-hardening-guards.tests.ps1`

- [ ] **Step 1: Add failing publication guard tests**

Extend guard tests:

```powershell
Assert-PathExists (Join-Path $RepoRoot 'scripts\release\Invoke-RookInstallerSmoke.ps1') 'Missing installer smoke script.'
$buildSkill = Get-Content -Path (Join-Path $RepoRoot '.agents\skills\build-release\SKILL.md') -Raw
Assert-Contains $buildSkill 'rook-release-manifest.json' 'Build-release skill must publish release manifest.'
Assert-Contains $buildSkill 'rook-mcp-wheel-report.json' 'Build-release skill must publish first-party MCP wheel provenance.'
Assert-Contains $buildSkill 'pip-audit-report.json' 'Build-release skill must publish raw vulnerability scan evidence.'
Assert-Contains $buildSkill 'runtime-scan-report.json' 'Build-release skill must publish runtime scan report.'
Assert-Contains $buildSkill 'installer-smoke-summary.md' 'Build-release skill must require installer smoke summary.'
Assert-Contains $buildSkill 'network-isolation-evidence.json' 'Build-release skill must require network isolation evidence.'
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\beta-installer-hardening-guards.tests.ps1
```

Expected: missing smoke script or docs failure.

- [ ] **Step 3: Implement smoke script**

Create `scripts/release/Invoke-RookInstallerSmoke.ps1`:

```powershell
param(
    [Parameter(Mandatory=$true)][string]$InstallerPath,
    [Parameter(Mandatory=$true)][string]$SummaryPath,
    [Parameter(Mandatory=$true)][string]$ExpectedVersion,
    [Parameter(Mandatory=$true)][string]$NetworkIsolationEvidencePath,
    [switch]$NetworkDisabled
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) { throw "Installer missing: $InstallerPath" }
if (-not $NetworkDisabled) { throw 'Run this smoke in a network-disabled test profile and pass -NetworkDisabled.' }
if (-not (Test-Path -LiteralPath $NetworkIsolationEvidencePath -PathType Leaf)) { throw "Network isolation evidence missing: $NetworkIsolationEvidencePath" }
$networkEvidence = Get-Content -LiteralPath $NetworkIsolationEvidencePath -Raw | ConvertFrom-Json
if (-not $networkEvidence.networkDisabled) { throw 'Network isolation evidence must record networkDisabled=true.' }
if ([string]::IsNullOrWhiteSpace([string]$networkEvidence.method)) { throw 'Network isolation evidence must record the enforcement method.' }

$checks = New-Object System.Collections.Generic.List[object]
$checks.Add([ordered]@{ name = 'installer_exists'; ok = $true; detail = $InstallerPath })
$checks.Add([ordered]@{ name = 'network_isolation_evidence'; ok = $true; detail = "method=$($networkEvidence.method); evidence=$NetworkIsolationEvidencePath" })

foreach ($target in @('pypi.org', 'python.org', 'files.pythonhosted.org')) {
    $probe = Test-NetConnection -ComputerName $target -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue
    $checks.Add([ordered]@{ name = "network_probe_blocked_$($target -replace '[^A-Za-z0-9]','_')"; ok = (-not $probe); detail = "${target}:443 reachable=$probe" })
}

$logDir = Join-Path ([System.IO.Path]::GetTempPath()) ("rook-installer-smoke-" + [System.Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$installLog = Join-Path $logDir 'inno-install.log'
$installArgs = @(
    '/VERYSILENT',
    '/SUPPRESSMSGBOXES',
    '/NORESTART',
    "/LOG=$installLog"
)
$process = Start-Process -FilePath $InstallerPath -ArgumentList $installArgs -Wait -PassThru
$checks.Add([ordered]@{ name = 'installer_exit_code'; ok = ($process.ExitCode -eq 0); detail = "exit=$($process.ExitCode)" })

$localAppData = [Environment]::GetFolderPath('LocalApplicationData')
$appRoot = Join-Path $localAppData 'Rook\app'
$runtimeRoot = Join-Path $localAppData 'Rook\runtime'
$payloadManifest = Join-Path $appRoot 'rook-payload-manifest.json'
$installedVersion = Join-Path $appRoot 'installed-version.json'
$clientState = Join-Path $localAppData 'Rook\config\client-config-state.json'
$activePluginDir = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative'
$nativeRhp = Join-Path $activePluginDir 'RookNative.rhp'
$companionRhp = Join-Path $activePluginDir 'Rook.rhp'
$checks.Add([ordered]@{ name = 'payload_manifest_installed'; ok = (Test-Path $payloadManifest); detail = $payloadManifest })
$checks.Add([ordered]@{ name = 'installed_version_state'; ok = (Test-Path $installedVersion); detail = $installedVersion })
$checks.Add([ordered]@{ name = 'client_config_state'; ok = (Test-Path $clientState); detail = $clientState })
$checks.Add([ordered]@{ name = 'runtime_installed'; ok = (Test-Path $runtimeRoot); detail = $runtimeRoot })
$checks.Add([ordered]@{ name = 'active_native_plugin_installed'; ok = (Test-Path $nativeRhp); detail = $nativeRhp })
$checks.Add([ordered]@{ name = 'active_companion_plugin_installed'; ok = (Test-Path $companionRhp); detail = $companionRhp })

$nativeRegPath = 'HKCU:\Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906\PlugIn'
$companionRegPath = 'HKCU:\Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B\PlugIn'
$nativeReg = if (Test-Path $nativeRegPath) { (Get-ItemProperty -LiteralPath $nativeRegPath -Name FileName -ErrorAction SilentlyContinue).FileName } else { $null }
$companionReg = if (Test-Path $companionRegPath) { (Get-ItemProperty -LiteralPath $companionRegPath -Name FileName -ErrorAction SilentlyContinue).FileName } else { $null }
$checks.Add([ordered]@{ name = 'native_registry_points_to_active_plugin'; ok = ([string]$nativeReg -eq $nativeRhp); detail = [string]$nativeReg })
$checks.Add([ordered]@{ name = 'companion_registry_points_to_active_plugin'; ok = ([string]$companionReg -eq $companionRhp); detail = [string]$companionReg })

$logText = if (Test-Path $installLog) { Get-Content -LiteralPath $installLog -Raw } else { '' }
$forbiddenNetworkSignals = @('pypi.org', 'python.org', 'pip install', 'Downloading', 'Collecting ')
foreach ($signal in $forbiddenNetworkSignals) {
    $checks.Add([ordered]@{ name = "no_network_signal_$($signal -replace '[^A-Za-z0-9]','_')"; ok = (-not $logText.Contains($signal)); detail = $signal })
}

if (Test-Path $installedVersion) {
    $versionState = Get-Content -LiteralPath $installedVersion -Raw | ConvertFrom-Json
    $checks.Add([ordered]@{ name = 'installed_version_matches'; ok = ([string]$versionState.version -eq $ExpectedVersion); detail = "expected=$ExpectedVersion actual=$($versionState.version)" })
}

if (Test-Path $clientState) {
    $state = Get-Content -LiteralPath $clientState -Raw | ConvertFrom-Json
    foreach ($client in @($state.clients)) {
        $checks.Add([ordered]@{ name = "client_$($client.name)_uses_bundled_runtime"; ok = ([string]$client.command).StartsWith($runtimeRoot); detail = [string]$client.command })
    }
}

$pythonExe = Get-ChildItem -LiteralPath $runtimeRoot -Recurse -File -Filter 'python.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($pythonExe) {
    $doctorJson = Join-Path $logDir 'rook-doctor.json'
    & $pythonExe.FullName -m rook doctor --json | Set-Content -LiteralPath $doctorJson -Encoding UTF8
    $checks.Add([ordered]@{ name = 'rook_doctor_exit_code'; ok = ($LASTEXITCODE -eq 0); detail = "exit=$LASTEXITCODE report=$doctorJson" })
} else {
    $checks.Add([ordered]@{ name = 'rook_doctor_exit_code'; ok = $false; detail = "No python.exe below $runtimeRoot" })
}

$failed = @($checks | Where-Object { -not $_.ok })
$lines = @(
    '# Rook Installer Smoke Summary',
    '',
    "Installer: $InstallerPath",
    "Generated: $((Get-Date).ToUniversalTime().ToString('o'))",
    '',
    '| Check | Result | Detail |',
    '|---|---|---|'
)
foreach ($check in $checks) {
    $result = if ($check.ok) { 'PASS' } else { 'FAIL' }
    $lines += "| $($check.name) | $result | $($check.detail) |"
}
$parent = Split-Path -Parent $SummaryPath
if ($parent -and -not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
$lines | Set-Content -LiteralPath $SummaryPath -Encoding UTF8
if ($failed.Count -gt 0) { throw "Installer smoke had failing checks. See $SummaryPath" }
Write-Host "Wrote installer smoke summary: $SummaryPath"
```

The smoke script runs the installer and must fail unless `-NetworkDisabled` is provided for a network-disabled release smoke run and `-NetworkIsolationEvidencePath` points at a JSON file recording how egress was disabled. Valid evidence examples are a Windows test VM with NIC disabled, a Windows Sandbox/network policy profile with outbound traffic denied, or a release lab firewall rule denying egress for the test user. The smoke also probes common package/runtime hosts and fails if they are reachable. The run validates installed state, active Rhino plugin files, HKCU plugin registration, bundled-runtime client config, `rook doctor`, install logs, and absence of PyPI/package/runtime download signals.

The network evidence file must be saved as `artifacts\release\network-isolation-evidence.json` and published with the release evidence:

```json
{
  "schemaVersion": 1,
  "networkDisabled": true,
  "method": "Windows test VM NIC disabled before installer launch",
  "capturedAt": "2026-05-21T00:00:00Z",
  "operator": "release-builder"
}
```

- [ ] **Step 4: Update build-release skills**

In both `.agents/skills/build-release/SKILL.md` and `.claude/skills/build-release/SKILL.md`, add a release gate before GitHub release creation:

```powershell
$releaseReports = @(
  'artifacts\release\build-identity-report.json',
  'artifacts\release\native-dependency-report.json',
  'artifacts\release\managed-dependency-report.json',
  'artifacts\release\python-runtime-report.json',
  'artifacts\release\rook-mcp-wheel-report.json',
  'artifacts\release\wheelhouse-lock-report.json',
  'artifacts\release\pip-audit-report.json',
  'artifacts\release\runtime-scan-report.json',
  'artifacts\release\license-scan-report.json',
  'artifacts\release\ffmpeg-compliance-report.json',
  'artifacts\release\payload-manifest-validation.json',
  'artifacts\release\installer-smoke-summary.md',
  'artifacts\release\network-isolation-evidence.json',
  'artifacts\release\rhino-smoke-summary.md',
  'artifacts\release\mcp-client-config-report.json',
  'artifacts\release\update-check-report.json'
)
foreach ($report in $releaseReports) {
  if (-not (Test-Path $report)) { throw "Missing release evidence: $report" }
}
```

- [ ] **Step 5: Update `BUILDING.md` publication section**

Document GitHub Release assets:

```powershell
gh release create vX.Y.Z `
  installer\output\Rook-Setup-X.Y.Z.exe `
  installer\output\Rook-Setup-X.Y.Z.exe.sha256 `
  artifacts\release\rook-release-manifest.json `
  artifacts\release\rook-payload-manifest.json `
  artifacts\release\build-identity-report.json `
  artifacts\release\native-dependency-report.json `
  artifacts\release\managed-dependency-report.json `
  artifacts\release\python-runtime-report.json `
  artifacts\release\rook-mcp-wheel-report.json `
  artifacts\release\wheelhouse-lock-report.json `
  artifacts\release\pip-audit-report.json `
  artifacts\release\runtime-scan-report.json `
  artifacts\release\license-scan-report.json `
  artifacts\release\ffmpeg-compliance-report.json `
  artifacts\release\payload-manifest-validation.json `
  artifacts\release\installer-smoke-summary.md `
  artifacts\release\network-isolation-evidence.json `
  artifacts\release\rhino-smoke-summary.md `
  artifacts\release\mcp-client-config-report.json `
  artifacts\release\update-check-report.json `
  --title "Rook vX.Y.Z" --generate-notes
```

- [ ] **Step 6: Run tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\beta-installer-hardening-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add scripts\release\Invoke-RookInstallerSmoke.ps1 .agents\skills\build-release\SKILL.md .claude\skills\build-release\SKILL.md BUILDING.md scripts\tests\beta-installer-hardening-guards.tests.ps1
git commit -m "release: require installer evidence publication"
```

---

### Task 8: Enterprise Path Documentation And Final Verification

**Files:**
- Modify: `docs/CURRENT_ARCHITECTURE.md`
- Modify: `README.md`
- Modify: `QUICK_START.md`
- Modify: `BUILDING.md`
- Modify: `docs/superpowers/specs/2026-05-21-beta-installer-hardening-design.md` only if implementation discovers a necessary design correction

- [ ] **Step 1: Update user-facing install docs**

Replace release-install Python prerequisite language in `README.md` and `QUICK_START.md` with:

```markdown
The Windows release installer includes Rook's runtime. You do not need to install Python, pip, Visual Studio, or developer tools for a release install. Source/developer bootstrap still has separate development prerequisites.
```

- [ ] **Step 2: Document enterprise-preserved constraints**

Add to `docs/CURRENT_ARCHITECTURE.md`:

```markdown
## Installer Boundary

The beta installer is per-user and writes HKCU Rhino registration. App/runtime payloads, user config, data, and logs are separated so a later enterprise installer can reuse the same runtime/config model with per-machine roots and HKLM registration.
```

- [ ] **Step 3: Run documentation guard search**

Run:

```powershell
rg -n "Python 3.10\\+ required for the Windows installer|install Python.*release installer|pip install.*release" README.md QUICK_START.md BUILDING.md AGENT_SETUP.md
```

Expected: no matches that imply Python is required for release install. Mentions for source/development bootstrap are acceptable only if clearly labeled.

- [ ] **Step 4: Run final guard suite**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\beta-installer-hardening-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
cd mcp_server
pytest tests\test_doctor_installed_payload.py -q
```

Expected: all pass.

- [ ] **Step 5: Produce final implementation summary**

Create an implementation summary in the PR description or release branch notes with:

```markdown
## Installer Hardening Summary

- Bundled runtime: yes
- User-machine PyPI install: no
- Payload manifest: rook-payload-manifest.json
- Release manifest: rook-release-manifest.json
- Client config state: %LOCALAPPDATA%\Rook\config\client-config-state.json
- Rhino plugin rollback: active folder backup/restore
- Update checks: GitHub awareness only, no auto-download
- Release blockers: missing reports, failed smoke, undocumented exceptions
```

- [ ] **Step 6: Commit**

```powershell
git add docs\CURRENT_ARCHITECTURE.md README.md QUICK_START.md BUILDING.md
git commit -m "docs: describe beta installer runtime model"
```

---

## Final Verification Before Merge

Run from a clean implementation branch:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\beta-installer-hardening-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
python -m py_compile installer\post_install.py installer\install_state.py installer\runtime_verify.py
python -m pytest mcp_server\tests\test_doctor_installed_payload.py -q
```

If the native/Rhino toolchain is available, also run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release\Test-RookNativeClosure.ps1 -NativeRhpPath src\RookNative\bin\Release\x64\RookNative.rhp -ReportPath artifacts\release\native-dependency-report.json
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release\Test-RookManagedClosure.ps1 -CompanionRhpPath src\Rook\bin\Release\net7.0\Rook.rhp -ReportPath artifacts\release\managed-dependency-report.json
python -m venv artifacts\release-tools\.venv
& .\artifacts\release-tools\.venv\Scripts\python.exe -m pip install --require-hashes -r scripts\release\release-tools-requirements.txt
& .\artifacts\release-tools\.venv\Scripts\pip-audit.exe -r mcp_server\requirements-lock.txt --format json --output artifacts\release\pip-audit-report.json
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release\Invoke-RookRuntimeSecurityScan.ps1 -RuntimeRoot artifacts\release\rook-runtime -WheelhouseLockReportPath artifacts\release\wheelhouse-lock-report.json -PipAuditReportPath artifacts\release\pip-audit-report.json -LicensePolicyPath scripts\release\license-policy.json -OutputDir artifacts\release
```

Do not claim a full release smoke unless the signed installer was built, installed into a test profile, and verified with Rhino closed/open as described in the design spec.
