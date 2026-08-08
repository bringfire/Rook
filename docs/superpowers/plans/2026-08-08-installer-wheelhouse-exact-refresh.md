# Installer Wheelhouse Exact Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every installer run that selects MCP or Chirp replace the installer-owned sealed Python wheelhouse exactly, preventing obsolete wheels from surviving upgrades.

**Architecture:** Add one component-scoped declarative `[InstallDelete]` entry immediately before the existing `[Files]` replacement copy. Extend the existing PowerShell release guard to pin the exact paired delete/copy contract, then rebuild and install 1.5.18 from the prerequisite's immutable merge SHA to prove exact source/installed inventory and hash equality.

**Tech Stack:** Inno Setup 6, Windows PowerShell 5.1, Git, existing Rook release scripts.

## Global Constraints

- Approved specification: `docs/superpowers/specs/2026-08-07-installer-wheelhouse-exact-refresh-design.md` at `91769977d420d502821a84b287b580ef8240b8c4`.
- Implementation changes exactly `installer/RookSetup.iss` and `scripts/tests/release-installer-guards.tests.ps1`.
- Delete exactly `{app}\python-wheelhouse` with `Type: filesandordirs`; use no wildcard or parent-directory deletion.
- Both deletion and replacement use exactly `Components: mcp chirp`.
- Do not add Pascal cleanup, post-install cleanup, Python synchronization, or a generalized deployment framework.
- Do not modify dependencies, lockfiles, release version fields, native code, managed code, RookBIM, local deployment, or Chirp.
- Preserve `.env`, virtual environments, the private Python runtime, installed lockfiles, the runtime manifest, user data, configuration, and sibling application directories.
- The installer built from private merge `02918747d38412419954c86fa3167a421eadfea4` is diagnostic-only and must never be published.
- One implementation commit carries both the focused guard and installer correction.
- Stop on scope drift or any failed gate. Do not repair unrelated failures in this branch.

## File Map

| Path | Responsibility |
|---|---|
| `installer/RookSetup.iss` | Declaratively delete the exact installed sealed wheelhouse before its existing replacement copy. |
| `scripts/tests/release-installer-guards.tests.ps1` | Pin section ordering, exact path/type, matching component selection, and the single existing copy operation. |

---

### Task 0: Verify the Approved Planning Baseline

**Files:**
- Read: `docs/superpowers/specs/2026-08-07-installer-wheelhouse-exact-refresh-design.md`
- Read: `docs/superpowers/plans/2026-08-08-installer-wheelhouse-exact-refresh.md`

**Interfaces:**
- Consumes: annotated execution tag `plan/installer-wheelhouse-exact-refresh-2026-08-08-approved`.
- Produces: a clean, immutable plan baseline for the one implementation commit.

- [ ] **Step 1: Resolve the approval tag and ancestry**

Run from the isolated planning worktree:

```powershell
$expectedSpec = '91769977d420d502821a84b287b580ef8240b8c4'
$approvalTag = 'plan/installer-wheelhouse-exact-refresh-2026-08-08-approved'
$planCommit = (git rev-parse HEAD).Trim()
$tagCommit = (git rev-list -n 1 $approvalTag).Trim()
$planParent = (git rev-parse HEAD^).Trim()

if ($tagCommit -ne $planCommit) {
    throw "Approval tag resolves to $tagCommit, expected plan HEAD $planCommit."
}
if ($planParent -ne $expectedSpec) {
    throw "Plan parent is $planParent, expected approved specification $expectedSpec."
}
```

Expected: no output and no exception.

- [ ] **Step 2: Prove the plan commit changes exactly one file**

```powershell
$expectedPlan = 'docs/superpowers/plans/2026-08-08-installer-wheelhouse-exact-refresh.md'
$paths = @(git diff --name-only HEAD^ HEAD)
if ($paths.Count -ne 1 -or $paths[0] -ne $expectedPlan) {
    throw "Unexpected plan scope: $($paths -join ', ')"
}
git diff --check HEAD^ HEAD
if ($LASTEXITCODE -ne 0) { throw 'Plan diff check failed.' }
if (git status --porcelain) { git status --short; throw 'Planning worktree is dirty.' }
```

Expected: no output and a clean worktree.

- [ ] **Step 3: Run the unmodified source-only release guard**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\tests\release-installer-guards.tests.ps1 `
  -SkipBuiltPayloadCheck
if ($LASTEXITCODE -ne 0) { throw 'Baseline release-installer guard failed.' }
```

Expected: `Release installer guard tests passed.` This is the pre-edit baseline; it does not yet prove exact wheelhouse refresh.

---

### Task 1: Add the Exact Delete-and-Replace Contract with TDD

**Files:**
- Modify: `scripts/tests/release-installer-guards.tests.ps1`
- Modify: `installer/RookSetup.iss`

**Interfaces:**
- Consumes: existing `[InstallDelete]` before `[Files]`, existing `Assert-True`, and the existing wheelhouse `[Files]` entry.
- Produces: `Test-InstallerExactRefreshesPythonWheelhouse` and one exact component-scoped installer deletion.

- [ ] **Step 1: Add the failing focused guard**

Add this function near `Test-InstallerDeletesStaleChildChatManifests` in `scripts/tests/release-installer-guards.tests.ps1`:

```powershell
function Test-InstallerExactRefreshesPythonWheelhouse {
    $content = Get-Content -LiteralPath $InstallerScript -Raw
    $installDeleteMatch = [regex]::Match(
        $content,
        '(?ms)^\[InstallDelete\]\s*(?<block>.*?)(?=^\[Files\])'
    )
    $filesMatch = [regex]::Match(
        $content,
        '(?ms)^\[Files\]\s*(?<block>.*?)(?=^\[|\z)'
    )

    Assert-True -Condition $installDeleteMatch.Success -Message '[InstallDelete] must precede [Files].'
    Assert-True -Condition $filesMatch.Success -Message 'Installer must contain a [Files] section.'

    $deleteLine = 'Type: filesandordirs; Name: "{app}\python-wheelhouse"; Components: mcp chirp'
    $copyLine = 'Source: "{#PythonWheelhouseDir}\*"; DestDir: "{app}\python-wheelhouse"; Components: mcp chirp; Flags: ignoreversion'
    $deleteLines = @(
        $installDeleteMatch.Groups['block'].Value -split '\r?\n' |
            Where-Object { $_ -match 'python-wheelhouse' } |
            ForEach-Object { $_.Trim() }
    )
    $copyLines = @(
        $filesMatch.Groups['block'].Value -split '\r?\n' |
            Where-Object { $_ -match 'DestDir: "\{app\}\\python-wheelhouse"' } |
            ForEach-Object { $_.Trim() }
    )

    Assert-True -Condition ($deleteLines.Count -eq 1) -Message "Expected exactly one wheelhouse deletion; found $($deleteLines.Count)."
    Assert-True -Condition ($deleteLines[0] -ceq $deleteLine) -Message 'Wheelhouse deletion must use the exact owned directory, filesandordirs, and mcp chirp components.'
    Assert-True -Condition ($copyLines.Count -eq 1) -Message "Expected exactly one wheelhouse replacement copy; found $($copyLines.Count)."
    Assert-True -Condition ($copyLines[0] -ceq $copyLine) -Message 'Wheelhouse replacement must preserve the exact source, destination, components, and flags.'
}
```

Add this invocation immediately after `Test-InstallerDeletesStaleChildChatManifests` at the bottom of the file:

```powershell
Test-InstallerExactRefreshesPythonWheelhouse
```

- [ ] **Step 2: Run the guard and prove RED**

```powershell
$output = powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\tests\release-installer-guards.tests.ps1 `
  -SkipBuiltPayloadCheck 2>&1
$exitCode = $LASTEXITCODE
$output | Write-Host
if ($exitCode -eq 0) { throw 'Expected the new wheelhouse guard to fail before implementation.' }
if (($output -join "`n") -notmatch 'Expected exactly one wheelhouse deletion; found 0') {
    throw 'Guard failed for an unexpected reason.'
}
```

Expected: nonzero exit with `Expected exactly one wheelhouse deletion; found 0`.

- [ ] **Step 3: Add the minimal declarative deletion**

In `installer/RookSetup.iss`, add these two lines inside `[InstallDelete]`, before `[Files]` and without changing any existing entry:

```iss
; Replace the installer-owned sealed wheelhouse instead of overlaying stale wheels.
Type: filesandordirs; Name: "{app}\python-wheelhouse"; Components: mcp chirp
```

Do not add a `Check` function, wildcard, Pascal code, or post-install operation.

- [ ] **Step 4: Run the focused guard and prove GREEN**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\tests\release-installer-guards.tests.ps1 `
  -SkipBuiltPayloadCheck
if ($LASTEXITCODE -ne 0) { throw 'Release-installer guard failed after implementation.' }
```

Expected: `Release installer guard tests passed.`

- [ ] **Step 5: Verify the exact implementation boundary**

```powershell
$expected = @(
    'installer/RookSetup.iss',
    'scripts/tests/release-installer-guards.tests.ps1'
)
$actual = @(git diff --name-only HEAD | Sort-Object)
$unexpected = @(Compare-Object ($expected | Sort-Object) $actual)
if ($unexpected) {
    $unexpected | Format-Table | Out-String | Write-Host
    throw 'Implementation path scope drifted.'
}

$diff = git diff -- installer/RookSetup.iss scripts/tests/release-installer-guards.tests.ps1
if (($diff | Select-String -SimpleMatch 'post_install.py')) {
    throw 'Implementation introduced post-install cleanup.'
}
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Implementation diff check failed.' }
```

Expected: exactly the two approved paths and no diff errors.

- [ ] **Step 6: Commit the complete correction atomically**

```powershell
git add -- installer/RookSetup.iss scripts/tests/release-installer-guards.tests.ps1
$staged = @(git diff --cached --name-only | Sort-Object)
$expected = @(
    'installer/RookSetup.iss',
    'scripts/tests/release-installer-guards.tests.ps1'
) | Sort-Object
if (Compare-Object $expected $staged) { throw 'Unexpected staged scope.' }
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Staged diff check failed.' }
git commit -m "fix(installer): replace sealed wheelhouse exactly"
if ($LASTEXITCODE -ne 0) { throw 'Implementation commit failed.' }
```

Expected: one implementation commit containing exactly the two approved files.

- [ ] **Step 7: Re-run the committed-head contracts**

```powershell
$paths = @(git diff --name-only HEAD^ HEAD | Sort-Object)
$expected = @(
    'installer/RookSetup.iss',
    'scripts/tests/release-installer-guards.tests.ps1'
) | Sort-Object
if (Compare-Object $expected $paths) { throw 'Committed implementation scope is incorrect.' }

powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\tests\release-installer-guards.tests.ps1 `
  -SkipBuiltPayloadCheck
if ($LASTEXITCODE -ne 0) { throw 'Committed release-installer guard failed.' }
git diff --check HEAD^ HEAD
if ($LASTEXITCODE -ne 0) { throw 'Committed diff check failed.' }
if (git status --porcelain) { git status --short; throw 'Worktree is dirty.' }
```

Expected: focused guard passes and the worktree is clean.

---

### Task 2: Review, Merge, and Pin the New Release Provenance

**Files:**
- Review: `docs/superpowers/specs/2026-08-07-installer-wheelhouse-exact-refresh-design.md`
- Review: `docs/superpowers/plans/2026-08-08-installer-wheelhouse-exact-refresh.md`
- Review: `installer/RookSetup.iss`
- Review: `scripts/tests/release-installer-guards.tests.ps1`

**Interfaces:**
- Consumes: the reviewed one-commit implementation head.
- Produces: a regular two-parent merge SHA that becomes the only source provenance for rebuilt 1.5.18 artifacts.

- [ ] **Step 1: Refresh current main and verify mergeability without rebasing**

```powershell
$reviewedHead = (git rev-parse HEAD).Trim()
git fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Failed to refresh origin/main.' }
$currentMain = (git rev-parse origin/main).Trim()

$featurePaths = @(
    git diff --name-only 02918747d38412419954c86fa3167a421eadfea4 $reviewedHead
)
$mainPaths = @(
    git diff --name-only 02918747d38412419954c86fa3167a421eadfea4 $currentMain
)
$overlap = @($featurePaths | Where-Object { $mainPaths -contains $_ })
if ($overlap) { throw "Current main overlaps reviewed paths: $($overlap -join ', ')" }

git merge-tree --write-tree $currentMain $reviewedHead | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Synthetic merge failed.' }
```

Expected: zero path overlap and a successful synthetic merge. Do not rebase or amend the reviewed commits.

- [ ] **Step 2: Push and open one private PR**

```powershell
$branch = (git branch --show-current).Trim()
git push -u origin $branch
if ($LASTEXITCODE -ne 0) { throw 'Push failed.' }

gh pr create `
  --base main `
  --head $branch `
  --title "Fix exact installer wheelhouse refresh" `
  --body "Adds one component-scoped InstallDelete entry and one focused guard so MCP/Chirp upgrades replace the sealed wheelhouse instead of retaining obsolete wheels. No dependency, runtime, or version changes. The installer built from 02918747 remains diagnostic-only; release artifacts will be rebuilt from the eventual merge SHA."
if ($LASTEXITCODE -ne 0) { throw 'PR creation failed.' }
```

Expected: one non-draft PR against `main` preserving the specification, plan, and implementation commits.

- [ ] **Step 3: Stop for PR review**

Reviewer must confirm:

- exact four-path PR scope: specification, plan, installer, and focused guard;
- implementation commit changes only the two approved implementation files;
- exact delete/copy component parity;
- no custom cleanup mechanism;
- focused guard and synthetic merge pass.

Do not merge until review is clean.

- [ ] **Step 4: Merge with a regular merge commit and verify both parents**

After approval:

```powershell
$pr = gh pr view --json number,baseRefOid,headRefOid | ConvertFrom-Json
$prNumber = $pr.number
$currentMain = $pr.baseRefOid
$reviewedHead = $pr.headRefOid
gh pr merge $prNumber --merge --delete-branch=false
if ($LASTEXITCODE -ne 0) { throw 'PR merge failed.' }

git fetch origin main
$mergedSha = (git rev-parse origin/main).Trim()
$parents = @((git show -s --format='%P' $mergedSha).Trim() -split ' ')
if ($parents.Count -ne 2) { throw "Expected a two-parent merge, found $($parents.Count)." }
if ($parents[0] -ne $currentMain) { throw "Unexpected first parent $($parents[0]); expected $currentMain." }
if ($parents[1] -ne $reviewedHead) { throw "Unexpected second parent $($parents[1]); expected $reviewedHead." }
if ((git rev-parse origin/main).Trim() -ne $mergedSha) { throw 'origin/main does not point to the merge commit.' }

$statePath = Join-Path $env:TEMP 'rook-release-1.5.18-wheelhouse-refresh-state.json'
if (Test-Path -LiteralPath $statePath) { throw "Release state already exists: $statePath" }
[pscustomobject]@{
    version = '1.5.18'
    merged_sha = $mergedSha
    reviewed_head = $reviewedHead
    merge_first_parent = $currentMain
    chirp_sha = 'c7b1aacec6b1ae23514cb9fb0d2a365e1fb7a468'
} | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8

Write-Host "NEW_RELEASE_SOURCE_SHA=$mergedSha"
Write-Host "RELEASE_STATE=$statePath"
```

Expected: a regular two-parent merge. Record `$mergedSha`; it supersedes `02918747` as the sole private source provenance for every rebuilt artifact.

---

### Task 3: Rebuild and Prove the Corrected Installed Payload

**Files:**
- Build from: detached Rook checkout at `$mergedSha`
- Build from: detached Chirp checkout at `c7b1aacec6b1ae23514cb9fb0d2a365e1fb7a468`
- Produce: `installer/output/Rook-Setup-1.5.18.exe`

**Interfaces:**
- Consumes: the immutable private merge SHA from Task 2 and the existing `rook:build-release` workflow.
- Produces: a rebuilt installed 1.5.18 payload with exact source/installed wheelhouse equality, ready to resume standalone and Rhino.Inside.Revit acceptance.

- [ ] **Step 1: Create clean detached provenance roots**

```powershell
$statePath = Join-Path $env:TEMP 'rook-release-1.5.18-wheelhouse-refresh-state.json'
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$version = $state.version
$mergedSha = $state.merged_sha
$chirpSha = $state.chirp_sha
$primaryRook = 'C:\Users\aryan\source\repos\Rook'
$primaryChirp = 'C:\Users\aryan\source\repos\Chirp'
$releaseContainer = Join-Path $env:TEMP "rook-release-$version-$($mergedSha.Substring(0, 8))"
$releaseRook = Join-Path $releaseContainer 'Rook'
$releaseChirp = Join-Path $releaseContainer 'Chirp'

if (Test-Path -LiteralPath $releaseContainer) {
    throw "Release container already exists: $releaseContainer"
}
New-Item -ItemType Directory -Path $releaseContainer | Out-Null
git -C $primaryRook worktree add --detach $releaseRook $mergedSha
if ($LASTEXITCODE -ne 0) { throw 'Failed to create detached Rook release checkout.' }
git -C $primaryChirp worktree add --detach $releaseChirp $chirpSha
if ($LASTEXITCODE -ne 0) { throw 'Failed to create detached Chirp release checkout.' }

if ((git -C $releaseRook rev-parse HEAD).Trim() -ne $mergedSha) { throw 'Rook release SHA mismatch.' }
if ((git -C $releaseChirp rev-parse HEAD).Trim() -ne $chirpSha) { throw 'Chirp release SHA mismatch.' }
if (git -C $releaseRook status --porcelain) { throw 'Detached Rook checkout is dirty.' }
if (git -C $releaseChirp status --porcelain) { throw 'Detached Chirp checkout is dirty.' }
$buildStartedAt = [DateTimeOffset]::Now.ToString('o')

$state | Add-Member -NotePropertyName release_container -NotePropertyValue $releaseContainer
$state | Add-Member -NotePropertyName release_rook -NotePropertyValue $releaseRook
$state | Add-Member -NotePropertyName release_chirp -NotePropertyValue $releaseChirp
$state | Add-Member -NotePropertyName build_started_at -NotePropertyValue $buildStartedAt
$state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
```

Expected: clean detached sibling checkouts at the two exact SHAs.

- [ ] **Step 2: Execute the canonical release build through installer compilation**

Preserve the ordering and validation contract from `rook:build-release`, but do
not execute its primary-checkout path literals. Run the exact commands below,
with every source and output path rooted at detached `$releaseRook`. Rerun all
of these stages from the new merge SHA rather than reusing the diagnostic build:

1. Source preflight and release guards.
2. CPython staging, sealed wheelhouse build, and wheelhouse validation against
   the exact detached Rook and Chirp roots.
3. Canonical FFmpeg source build and validation.
4. Native Release build with MSVC `14.44.35207`.
5. Managed Rook Release build, followed by the RookBIM Release build.
6. Full built-payload installer guard.
7. ISCC compilation.

Begin with these provenance-bound Python commands:

```powershell
$state = Get-Content -LiteralPath (Join-Path $env:TEMP 'rook-release-1.5.18-wheelhouse-refresh-state.json') -Raw | ConvertFrom-Json
$version = $state.version
$releaseRook = $state.release_rook
$releaseChirp = $state.release_chirp
Push-Location -LiteralPath $releaseRook
try {
    powershell -NoProfile -ExecutionPolicy Bypass -File "$releaseRook\scripts\tests\release-surface-hygiene.tests.ps1"
    if ($LASTEXITCODE -ne 0) { throw 'Release-surface guard failed.' }
    powershell -NoProfile -ExecutionPolicy Bypass -File "$releaseRook\scripts\tests\release-installer-guards.tests.ps1" -SkipBuiltPayloadCheck
    if ($LASTEXITCODE -ne 0) { throw 'Source-only installer guard failed.' }
    claude plugin validate --strict $releaseRook
    if ($LASTEXITCODE -ne 0) { throw 'Strict Claude validation failed.' }
    uv lock --check --directory "$releaseRook\mcp_server"
    if ($LASTEXITCODE -ne 0) { throw 'uv lock check failed.' }

    powershell -NoProfile -ExecutionPolicy Bypass -File "$releaseRook\scripts\python-runtime\stage-rook-python-runtime.ps1" -RepoRoot $releaseRook
    if ($LASTEXITCODE -ne 0) { throw 'Private Python staging failed.' }
    powershell -NoProfile -ExecutionPolicy Bypass -File "$releaseRook\scripts\python-runtime\build-rook-python-wheelhouse.ps1" -Version $version -RepoRoot $releaseRook -ChirpRoot $releaseChirp
    if ($LASTEXITCODE -ne 0) { throw 'Sealed wheelhouse build failed.' }
    powershell -NoProfile -ExecutionPolicy Bypass -File "$releaseRook\scripts\validate-python-wheelhouse.ps1" -Version $version -RepoRoot $releaseRook
    if ($LASTEXITCODE -ne 0) { throw 'Sealed wheelhouse validation failed.' }
}
finally {
    Pop-Location
}
```

If `ffmpeg.org` is still unreachable, stop and confirm that exact network
failure. The three immutable inputs previously cached under the diagnostic
release may be copied into the new builder's download cache only after checking
their recorded SHA-256 values; the canonical builder must still reverify the
archive signature and rebuild the binary. Never copy the old compiled FFmpeg
binary or its generated provenance output.

Build FFmpeg, native Rook, managed Rook, and RookBIM from the same detached
root. The temporary native batch receives the detached project as its only
argument:

```powershell
$state = Get-Content -LiteralPath (Join-Path $env:TEMP 'rook-release-1.5.18-wheelhouse-refresh-state.json') -Raw | ConvertFrom-Json
$version = $state.version
$mergedSha = $state.merged_sha
$releaseRook = $state.release_rook
$buildStartedAt = [DateTimeOffset]::Parse($state.build_started_at)
$buildBat = Join-Path $env:TEMP "rook-build-native-$($mergedSha.Substring(0, 8)).bat"
if (Test-Path -LiteralPath $buildBat) { throw "Temporary native-build batch already exists: $buildBat" }

@'
@echo off
set "VSCMD_START_DIR=%CD%"
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64 -vcvars_ver=14.44
if errorlevel 1 exit /b %errorlevel%
set VCToolsVersion=14.44.35207
msbuild "%~1" /t:Build /p:Configuration=Release /p:Platform=x64 /p:VCToolsVersion=14.44.35207 /m /v:minimal
exit /b %errorlevel%
'@ | Set-Content -LiteralPath $buildBat -Encoding Ascii

Push-Location -LiteralPath $releaseRook
try {
    powershell -NoProfile -ExecutionPolicy Bypass -File "$releaseRook\scripts\ffmpeg\build-rook-ffmpeg.ps1" -InstallPayload
    if ($LASTEXITCODE -ne 0) { throw 'Canonical FFmpeg build failed.' }
    powershell -NoProfile -ExecutionPolicy Bypass -File "$releaseRook\scripts\validate-ffmpeg-bundle.ps1" `
      -SourceBundleManifestPath "$releaseRook\artifacts\ffmpeg\ffmpeg-8.1.1-rook-minimal\rook-ffmpeg-source-bundle-manifest.json"
    if ($LASTEXITCODE -ne 0) { throw 'FFmpeg validation failed.' }

    & $buildBat "$releaseRook\src\RookNative\RookNative.vcxproj"
    if ($LASTEXITCODE -ne 0) { throw "Native Release build failed with exit code $LASTEXITCODE." }
    dotnet build "$releaseRook\src\Rook\Rook.csproj" -c Release
    if ($LASTEXITCODE -ne 0) { throw 'Managed Rook Release build failed.' }
    dotnet build "$releaseRook\src\RookBim\RookBim.csproj" -c Release
    if ($LASTEXITCODE -ne 0) { throw 'RookBIM Release build failed.' }
}
finally {
    Pop-Location
    if (Test-Path -LiteralPath $buildBat -PathType Leaf) {
        Remove-Item -LiteralPath $buildBat -Force
    }
}

$requiredOutputs = @(
    "$releaseRook\src\RookNative\bin\Release\x64\RookNative.rhp",
    "$releaseRook\src\Rook\bin\Release\net8.0\Rook.rhp",
    "$releaseRook\src\Rook\bin\Release\net8.0\Rook.runtimeconfig.json",
    "$releaseRook\src\Rook\bin\Release\net7.0\Rook.rhp",
    "$releaseRook\src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json",
    "$releaseRook\src\Rook\bin\Release\net48\Rook.rhp",
    "$releaseRook\src\Rook\bin\Release\net48\RookBim.dll"
)
foreach ($path in $requiredOutputs) {
    $item = Get-Item -LiteralPath $path -ErrorAction Stop
    if ([DateTimeOffset]$item.LastWriteTime -le $buildStartedAt) { throw "Build output is stale: $path" }
}

powershell -NoProfile -ExecutionPolicy Bypass -File "$releaseRook\scripts\tests\release-installer-guards.tests.ps1"
if ($LASTEXITCODE -ne 0) { throw 'Full release-installer guard failed.' }

$iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
$iss = "$releaseRook\installer\RookSetup.iss"
& $iscc $iss
if ($LASTEXITCODE -ne 0) { throw 'ISCC failed.' }

$installer = Join-Path $releaseRook "installer\output\Rook-Setup-$version.exe"
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw 'Corrected installer is missing.' }
$installerHash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash
Write-Host "CORRECTED_INSTALLER=$installer"
Write-Host "CORRECTED_INSTALLER_SHA256=$installerHash"
```

Stop immediately on any failed build or validation. Do not reuse the prior `02918747` installer or any compiled binary from its checkout.

- [ ] **Step 3: Close release-sensitive processes and install the corrected candidate**

```powershell
$state = Get-Content -LiteralPath (Join-Path $env:TEMP 'rook-release-1.5.18-wheelhouse-refresh-state.json') -Raw | ConvertFrom-Json
$version = $state.version
$releaseRook = $state.release_rook
$installer = Join-Path $releaseRook "installer\output\Rook-Setup-$version.exe"
$blocking = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match '^(Rhino|Rhinoceros|Revit|Grasshopper|Claude)$'
})
if ($blocking) {
    $blocking | Select-Object ProcessName, Id | Format-Table | Out-String | Write-Host
    throw 'Close Rhino, Grasshopper, Revit, and Claude before installation.'
}

$processHelper = Join-Path $releaseRook 'scripts\rook-mcp-processes.ps1'
powershell -NoProfile -ExecutionPolicy Bypass -File $processHelper -Stop
if ($LASTEXITCODE -ne 0) { throw 'Rook MCP process stop failed.' }
$processCheck = @(powershell -NoProfile -ExecutionPolicy Bypass -File $processHelper 2>&1)
if ($LASTEXITCODE -ne 0) { throw 'Rook MCP process recheck failed.' }
$processCheck | Write-Host
if (($processCheck -join "`n").Trim() -cne 'No python -m rook processes found.') {
    throw 'Second Rook MCP process inventory did not report zero processes.'
}

$installedWheelhouse = Join-Path $env:LOCALAPPDATA 'Rook\app\python-wheelhouse'
$preInstallFiles = @(Get-ChildItem -LiteralPath $installedWheelhouse -File -Recurse)
$staleNames = @(
    'huggingface_hub-1.26.1-py3-none-any.whl',
    'pydantic_settings-2.14.2-py3-none-any.whl',
    'rook_mcp-1.5.17-py3-none-any.whl'
)
if ($preInstallFiles.Count -ne 106) {
    throw "Contaminated upgrade baseline is absent: expected 106 files, found $($preInstallFiles.Count)."
}
foreach ($name in $staleNames) {
    if (-not (Test-Path -LiteralPath (Join-Path $installedWheelhouse $name) -PathType Leaf)) {
        throw "Contaminated upgrade baseline is absent: missing $name"
    }
}
Write-Host 'CONTAMINATED_BASELINE=106 files plus all three stale wheels'

$installLog = Join-Path (Split-Path -Parent $installer) "install-$version-wheelhouse-refresh.log"
$process = Start-Process -FilePath $installer -ArgumentList @(
    '/VERYSILENT',
    '/SUPPRESSMSGBOXES',
    '/NORESTART',
    '/TYPE=full',
    "/LOG=$installLog"
) -Wait -PassThru
if ($process.ExitCode -ne 0) { throw "Installer failed with exit code $($process.ExitCode)." }
```

Expected: exit code 0 and a new log for the corrected installer.

- [ ] **Step 4: Prove exact wheelhouse inventory and hashes**

```powershell
$state = Get-Content -LiteralPath (Join-Path $env:TEMP 'rook-release-1.5.18-wheelhouse-refresh-state.json') -Raw | ConvertFrom-Json
$releaseRook = $state.release_rook
$sourceWheelhouse = Join-Path $releaseRook 'installer\runtime\python-wheelhouse'
$installedWheelhouse = Join-Path $env:LOCALAPPDATA 'Rook\app\python-wheelhouse'
$staleNames = @(
    'huggingface_hub-1.26.1-py3-none-any.whl',
    'pydantic_settings-2.14.2-py3-none-any.whl',
    'rook_mcp-1.5.17-py3-none-any.whl'
)

foreach ($name in $staleNames) {
    if (Test-Path -LiteralPath (Join-Path $installedWheelhouse $name)) {
        throw "Stale wheel survived corrected upgrade: $name"
    }
}

function Get-WheelhouseInventory {
    param([string]$Root)
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        throw "Wheelhouse missing: $Root"
    }
    @(
        Get-ChildItem -LiteralPath $Root -File -Recurse |
            ForEach-Object {
                [pscustomobject]@{
                    Path = $_.FullName.Substring($Root.Length).TrimStart('\').Replace('\', '/')
                    Sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
                }
            } |
            Sort-Object Path
    )
}

$sourceInventory = @(Get-WheelhouseInventory -Root $sourceWheelhouse)
$installedInventory = @(Get-WheelhouseInventory -Root $installedWheelhouse)
if ($sourceInventory.Count -ne 103) {
    throw "Expected the unchanged sealed graph to contain 103 files; found $($sourceInventory.Count)."
}
$delta = @(Compare-Object $sourceInventory $installedInventory -Property Path, Sha256)
if ($delta) {
    $delta | Format-Table -AutoSize | Out-String | Write-Host
    throw 'Installed wheelhouse differs from the sealed source inventory or hashes.'
}
Write-Host "WHEELHOUSE_FILES=$($installedInventory.Count)"
```

Expected: all three stale wheels absent and `WHEELHOUSE_FILES=103` with no delta.

- [ ] **Step 5: Re-prove installed runtime health**

```powershell
$rookPython = Join-Path $env:LOCALAPPDATA 'Rook\venv\Scripts\python.exe'
$chirpPython = Join-Path $env:LOCALAPPDATA 'Rook\app\chirp\.venv\Scripts\python.exe'
$pythonEvidence = Join-Path $env:TEMP 'rook-python-smoke-evidence-1.5.18-wheelhouse-refresh.json'

& $rookPython -m rook.local_testing_proof python-smoke-evidence --out $pythonEvidence
if ($LASTEXITCODE -ne 0) { throw 'Installed Python smoke evidence failed.' }
$evidence = Get-Content -LiteralPath $pythonEvidence -Raw | ConvertFrom-Json
if ($evidence.success -ne $true) { throw 'Installed Python smoke evidence reported success=false.' }
& $rookPython -c "import importlib.metadata as m; assert m.version('rook-mcp') == '1.5.18'; assert m.version('mcp') == '1.28.1'; print('rook-mcp=1.5.18 mcp=1.28.1')"
if ($LASTEXITCODE -ne 0) { throw 'Installed Rook/MCP version check failed.' }
& $chirpPython -c "import importlib.metadata as m; assert m.version('chirp') == '0.1.0'; print('chirp=0.1.0')"
if ($LASTEXITCODE -ne 0) { throw 'Installed Chirp version check failed.' }
& $rookPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Installed Rook pip check failed.' }
& $chirpPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Installed Chirp pip check failed.' }
```

Expected: correct versions, successful installed evidence, and both `pip check` commands pass.

- [ ] **Step 6: Resume—not bypass—the remaining release gates**

Record the new private merge SHA, corrected installer SHA-256, exact 103-file wheelhouse evidence, install log, and Python evidence with the ongoing 1.5.18 release evidence. Then resume `rook:build-release` at standalone Rhino and Rhino.Inside.Revit acceptance.

Do not claim 1.5.18 complete and do not begin public promotion until both live host gates and final artifact validation pass against `$mergedSha` and `$installerHash`.
