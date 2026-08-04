# Rook 1.5.17 Mechanical Version-Bump Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce and merge one atomic pull request that changes exactly Rook's 14 declared release-version values across exactly ten files from `1.5.16` to `1.5.17`.

**Architecture:** Keep the approved specification and this plan on their separate planning branch. At execution time, create a fresh bump worktree from the exact current private `origin/main`, apply nine literal source edits, regenerate `uv.lock` normally, and prove the exact path, numstat, hunk, value, and integration contracts before a regular merge.

**Tech Stack:** Git, PowerShell, `uv`, Claude plugin validator, existing Rook release-surface guard.

## Global Constraints

- Approved specification: `docs/superpowers/specs/2026-08-03-release-1-5-17-version-bump-design.md` at `f1fb73cbb30a93281e3df1354cb6abc52576e86d`.
- Planning commits never enter the bump pull request.
- Change exactly ten declared version files and exactly 14 version values from `1.5.16` to `1.5.17`.
- Outside the accepted generated lock normalization, avoid every incidental formatting, ordering, dependency, source, hash, documentation, or code change.
- Derive expected version truth from `mcp_server/pyproject.toml`.
- Never edit `mcp_server/uv.lock` manually; regenerate it with the recorded installed official `uv 0.11.3` binary and require exactly one local `rook-mcp` version pair plus 59 marker-only normalization pairs.
- The committed bump is one atomic commit.
- Do not build, stage runtimes, compile an installer, install, deploy, run hosts, write release notes, modify `rook-release`, promote, tag, or publish.
- Do not run the built-payload installer guard; it belongs after the private bump merge.
- Stop on scope drift, unexpected lock movement, failed focused gates, overlapping current-main paths, or merge conflict. Do not absorb repairs.
- Merge with a regular two-parent merge commit; do not squash or rebase the reviewed bump.

## File Map

The implementation pull request modifies only:

1. `mcp_server/pyproject.toml` — canonical package version.
2. `mcp_server/uv.lock` — generated local `rook-mcp` version plus accepted marker normalization.
3. `installer/RookSetup.iss` — installer version.
4. `src/Rook/Rook.csproj` — companion version.
5. `src/RookBim/RookBim.csproj` — BIM module version.
6. `src/RookNative/RookNative.rc` — four native resource values.
7. `src/RookNative/RookNativePlugin.cpp` — native plug-in version.
8. `src/RookNative/RookServer.cpp` — native server-reported version.
9. `.claude-plugin/plugin.json` — Claude plug-in version.
10. `.claude-plugin/marketplace.json` — marketplace metadata and plug-in versions.

The specification and this plan remain only in the planning worktree and are not part
of that changed-path set.

---

### Task 0: Pin the approved plan and create the isolated bump worktree

**Files:**
- Read: `docs/superpowers/specs/2026-08-03-release-1-5-17-version-bump-design.md`
- Read: `docs/superpowers/plans/2026-08-03-release-1-5-17-version-bump.md`
- Modify: none.

**Interfaces:**
- Consumes: annotated approval tag `plan/release-1-5-17-version-bump-2026-08-03-approved`, created only after this plan is reviewed.
- Produces: `$bumpBaseSha`, branch `codex/release-1-5-17-version-bump`, and isolated worktree `C:\Users\aryan\source\repos\Rook\.worktrees\release-1-5-17-version-bump`.

- [ ] **Step 1: Verify the exact planning checkout**

Run from `C:\Users\aryan\source\repos\Rook\.worktrees\release-1-5-17-version-bump-design`:

```powershell
$ErrorActionPreference = 'Stop'
$approvedTag = 'plan/release-1-5-17-version-bump-2026-08-03-approved'
$approvedPlan = (git rev-parse "$approvedTag^{}" ).Trim()
$planningHead = (git rev-parse HEAD).Trim()
$approvedSpec = 'f1fb73cbb30a93281e3df1354cb6abc52576e86d'

if ($planningHead -ne $approvedPlan) {
  throw "Planning HEAD $planningHead does not equal approved plan $approvedPlan"
}
if ((git rev-parse HEAD^).Trim() -ne $approvedSpec) {
  throw 'Approved plan does not directly follow the approved specification'
}
if (git status --porcelain) {
  git status --short
  throw 'Planning worktree is dirty'
}
```

Expected: the tag resolves to the plan commit, its parent is `f1fb73cb`, and the
planning worktree is clean.

- [ ] **Step 2: Record current private main and prove the approved baseline is ancestral**

```powershell
git fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Could not refresh private origin/main' }

$bumpBaseSha = (git rev-parse origin/main).Trim()
$designBaseline = '8baf325a459ec9bb53cae24b1af0fab452b3001e'
git merge-base --is-ancestor $designBaseline $bumpBaseSha
if ($LASTEXITCODE -ne 0) {
  throw "Current origin/main $bumpBaseSha no longer descends from design baseline $designBaseline"
}

Write-Host "Recorded bump base: $bumpBaseSha"
```

Expected: one exact current private-main SHA is printed and retained in the execution
record.

- [ ] **Step 3: Create the fresh implementation branch and worktree**

```powershell
$implementationBranch = 'codex/release-1-5-17-version-bump'
$implementationRoot = 'C:\Users\aryan\source\repos\Rook\.worktrees\release-1-5-17-version-bump'
$bumpBaseSha = (git rev-parse origin/main).Trim()

if (Test-Path -LiteralPath $implementationRoot) {
  throw "Implementation worktree path already exists: $implementationRoot"
}
git show-ref --verify --quiet "refs/heads/$implementationBranch"
if ($LASTEXITCODE -eq 0) { throw "Implementation branch already exists: $implementationBranch" }

git worktree add -b $implementationBranch $implementationRoot $bumpBaseSha
if ($LASTEXITCODE -ne 0) { throw 'Could not create implementation worktree' }

if ((git -C $implementationRoot rev-parse HEAD).Trim() -ne $bumpBaseSha) {
  throw 'Implementation worktree was not created at the recorded bump base'
}
if (git -C $implementationRoot status --porcelain) {
  throw 'Implementation worktree is not clean at creation'
}
```

Expected: the new worktree is clean at exactly `$bumpBaseSha` and does not contain
the planning commits.

---

### Task 1: Apply, verify, and commit the exact mechanical bump

**Files:**
- Modify: `mcp_server/pyproject.toml:3`
- Modify: `mcp_server/uv.lock` — generated local `rook-mcp` block only
- Modify: `installer/RookSetup.iss:17`
- Modify: `src/Rook/Rook.csproj:17`
- Modify: `src/RookBim/RookBim.csproj:10`
- Modify: `src/RookNative/RookNative.rc:17-18,35,40`
- Modify: `src/RookNative/RookNativePlugin.cpp:424`
- Modify: `src/RookNative/RookServer.cpp:1994`
- Modify: `.claude-plugin/plugin.json:3`
- Modify: `.claude-plugin/marketplace.json:8,15`
- Test: `scripts/tests/release-surface-hygiene.tests.ps1`

**Interfaces:**
- Consumes: clean implementation worktree at `$bumpBaseSha` from Task 0.
- Produces: one clean atomic bump commit, `$reviewedBumpHead`, whose parent is `$bumpBaseSha` and whose diff is exactly ten paths and `73/73` lines.

- [ ] **Step 1: Run immutable baseline gates before editing**

Run from `C:\Users\aryan\source\repos\Rook\.worktrees\release-1-5-17-version-bump`:

```powershell
$ErrorActionPreference = 'Stop'
$bumpBaseSha = (git rev-parse HEAD).Trim()
if (git status --porcelain) { throw 'Bump worktree is dirty before editing' }

powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-surface-hygiene.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'Baseline release-surface guard failed' }

claude plugin validate --strict .
if ($LASTEXITCODE -ne 0) { throw 'Baseline strict Claude validation failed' }

& 'C:\Users\aryan\.local\bin\uv.exe' lock --check --directory mcp_server
if ($LASTEXITCODE -ne 0) { throw 'Baseline lock metadata is stale' }

git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Baseline diff check failed' }
```

Expected: all source/version gates pass at `1.5.16`; no built-payload gate runs.

- [ ] **Step 2: Apply the nine literal source edits**

Use `apply_patch` with these exact replacements; do not touch `uv.lock`:

```diff
*** Begin Patch
*** Update File: mcp_server/pyproject.toml
-version = "1.5.16"
+version = "1.5.17"
*** Update File: installer/RookSetup.iss
-#define MyAppVersion "1.5.16"
+#define MyAppVersion "1.5.17"
*** Update File: src/Rook/Rook.csproj
-    <Version>1.5.16</Version>
+    <Version>1.5.17</Version>
*** Update File: src/RookBim/RookBim.csproj
-    <Version>1.5.16</Version>
+    <Version>1.5.17</Version>
*** Update File: src/RookNative/RookNative.rc
- FILEVERSION 1,5,16,0
- PRODUCTVERSION 1,5,16,0
+ FILEVERSION 1,5,17,0
+ PRODUCTVERSION 1,5,17,0
@@
-            VALUE "FileVersion", "1.5.16.0"
+            VALUE "FileVersion", "1.5.17.0"
@@
-            VALUE "ProductVersion", "1.5.16.0"
+            VALUE "ProductVersion", "1.5.17.0"
*** Update File: src/RookNative/RookNativePlugin.cpp
-    : m_plugin_version(L"1.5.16")
+    : m_plugin_version(L"1.5.17")
*** Update File: src/RookNative/RookServer.cpp
-constexpr const char* kRookNativePluginVersion = "1.5.16";
+constexpr const char* kRookNativePluginVersion = "1.5.17";
*** Update File: .claude-plugin/plugin.json
-  "version": "1.5.16",
+  "version": "1.5.17",
*** Update File: .claude-plugin/marketplace.json
-    "version": "1.5.16"
+    "version": "1.5.17"
@@
-      "version": "1.5.16",
+      "version": "1.5.17",
*** End Patch
```

Expected: nine modified files; `mcp_server/uv.lock` remains untouched.

- [ ] **Step 3: Regenerate the lock normally**

```powershell
$uvPath = (Get-Command uv -CommandType Application).Source
$expectedUvPath = 'C:\Users\aryan\.local\bin\uv.exe'
$uvVersion = (& $uvPath --version).Trim()
$uvSha256 = (Get-FileHash -LiteralPath $uvPath -Algorithm SHA256).Hash

if ([IO.Path]::GetFullPath($uvPath) -ne [IO.Path]::GetFullPath($expectedUvPath)) {
  throw "Unexpected uv path: $uvPath"
}
if ($uvVersion -notmatch '^uv 0\.11\.3\b') {
  throw "Unexpected uv version: $uvVersion"
}
if ($uvSha256 -ne '07876908E19CF9A875A01D3B702C89B25DED154CC736079FEEB4EF78A8F4CA64') {
  throw "Unexpected uv SHA-256: $uvSha256"
}

Write-Host "Lock generator path: $uvPath"
Write-Host "Lock generator version: $uvVersion"
Write-Host "Lock generator SHA-256: $uvSha256"

& $uvPath lock --directory mcp_server
if ($LASTEXITCODE -ne 0) { throw 'uv lock regeneration failed' }
```

Expected: `mcp_server/uv.lock` becomes the tenth modified file with the observed
`60/60` generated normalization. Never patch or format the lock manually.

- [ ] **Step 4: Enforce the exact changed-path and numstat contracts**

```powershell
$bumpBaseSha = (git rev-parse HEAD).Trim()
$expected = [ordered]@{
  '.claude-plugin/marketplace.json' = @(2, 2)
  '.claude-plugin/plugin.json' = @(1, 1)
  'installer/RookSetup.iss' = @(1, 1)
  'mcp_server/pyproject.toml' = @(1, 1)
  'mcp_server/uv.lock' = @(60, 60)
  'src/Rook/Rook.csproj' = @(1, 1)
  'src/RookBim/RookBim.csproj' = @(1, 1)
  'src/RookNative/RookNative.rc' = @(4, 4)
  'src/RookNative/RookNativePlugin.cpp' = @(1, 1)
  'src/RookNative/RookServer.cpp' = @(1, 1)
}

$rows = @(git diff --numstat $bumpBaseSha --)
$actual = [ordered]@{}
foreach ($row in $rows) {
  $parts = $row -split "`t", 3
  if ($parts.Count -ne 3 -or $parts[0] -notmatch '^\d+$' -or $parts[1] -notmatch '^\d+$') {
    throw "Unexpected numstat row: $row"
  }
  $actual[$parts[2] -replace '\\', '/'] = @([int]$parts[0], [int]$parts[1])
}

$actualPathSet = @($actual.Keys | Sort-Object) -join "`n"
$expectedPathSet = @($expected.Keys | Sort-Object) -join "`n"
if ($actualPathSet -ne $expectedPathSet) {
  throw "Changed-path set is not the exact ten-file inventory: $($actual.Keys -join ', ')"
}

foreach ($path in $expected.Keys) {
  $want = $expected[$path]
  $got = $actual[$path]
  if ($got[0] -ne $want[0] -or $got[1] -ne $want[1]) {
    throw "$path has numstat $($got[0])/$($got[1]); expected $($want[0])/$($want[1])"
  }
}

$added = ($actual.Values | ForEach-Object { $_[0] } | Measure-Object -Sum).Sum
$deleted = ($actual.Values | ForEach-Object { $_[1] } | Measure-Object -Sum).Sum
if ($added -ne 73 -or $deleted -ne 73) {
  throw "Total numstat is $added/$deleted; expected 73/73"
}
```

Expected: exact ten paths; seven ordinary non-lock files `1/1`, native resource
`4/4`, marketplace `2/2`, generated lock `60/60`, total `73/73`.

- [ ] **Step 5: Inspect every hunk and the generated lock boundary**

```powershell
$bumpBaseSha = (git rev-parse HEAD).Trim()
git diff --unified=3 $bumpBaseSha --
if ($LASTEXITCODE -ne 0) { throw 'Could not render the complete bump diff' }

git diff --unified=3 $bumpBaseSha -- mcp_server/uv.lock
if ($LASTEXITCODE -ne 0) { throw 'Could not render the lock diff' }

$lockDiff = @(git diff --unified=0 $bumpBaseSha -- mcp_server/uv.lock)
$removed = @($lockDiff | Where-Object { $_ -match '^-' -and $_ -notmatch '^---' } | ForEach-Object { $_.Substring(1) })
$added = @($lockDiff | Where-Object { $_ -match '^\+' -and $_ -notmatch '^\+\+\+' } | ForEach-Object { $_.Substring(1) })
if ($removed.Count -ne 60 -or $added.Count -ne 60) {
  throw "Lock diff is $($removed.Count)/$($added.Count); expected 60/60"
}

$versionPairs = 0
$markerPairs = 0
for ($i = 0; $i -lt 60; $i++) {
  if ($removed[$i] -eq 'version = "1.5.16"' -and $added[$i] -eq 'version = "1.5.17"') {
    $versionPairs++
    continue
  }
  if ($removed[$i] -notmatch '^\s*\{ name = ' -or $added[$i] -notmatch '^\s*\{ name = ') {
    throw "Non-dependency lock change at pair ${i}"
  }
  $oldTarget = $removed[$i] -replace ', marker = ".*"(?= \})', ''
  $newTarget = $added[$i] -replace ', marker = ".*"(?= \})', ''
  if ($oldTarget -ne $newTarget) {
    throw "Dependency target, version, or source changed at pair ${i}"
  }
  $markerPairs++
}
if ($versionPairs -ne 1 -or $markerPairs -ne 59) {
  throw "Lock classification is version=$versionPairs marker=$markerPairs; expected 1/59"
}
```

Read the complete output. Outside the lock, require every removed token to be the
declared `1.5.16` form and every added token to be its `1.5.17` replacement. In the
lock, require exactly one project-version pair and 59 marker-only dependency-edge
pairs; no dependency target, third-party version, source, resolution, wheel, or hash
may change.

- [ ] **Step 6: Prove final version truth and absence in declared fields**

```powershell
$oldChecks = [ordered]@{
  'mcp_server/pyproject.toml' = '(?m)^version = "1\.5\.16"$'
  'mcp_server/uv.lock' = '(?ms)^\[\[package\]\]\r?\nname = "rook-mcp"\r?\nversion = "1\.5\.16"$'
  'installer/RookSetup.iss' = '(?m)^#define MyAppVersion "1\.5\.16"$'
  'src/Rook/Rook.csproj' = '<Version>1\.5\.16</Version>'
  'src/RookBim/RookBim.csproj' = '<Version>1\.5\.16</Version>'
  'src/RookNative/RookNative.rc' = '(?m)(FILEVERSION 1,5,16,0|PRODUCTVERSION 1,5,16,0|VALUE "(?:FileVersion|ProductVersion)", "1\.5\.16\.0")'
  'src/RookNative/RookNativePlugin.cpp' = 'm_plugin_version\(L"1\.5\.16"\)'
  'src/RookNative/RookServer.cpp' = 'kRookNativePluginVersion = "1\.5\.16"'
  '.claude-plugin/plugin.json' = '(?m)^  "version": "1\.5\.16",$'
  '.claude-plugin/marketplace.json' = '(?m)^\s+"version": "1\.5\.16",?$'
}

foreach ($entry in $oldChecks.GetEnumerator()) {
  $text = (Get-Content -LiteralPath $entry.Key -Raw) -replace "`r`n", "`n"
  if ([regex]::IsMatch($text, $entry.Value)) {
    throw "Declared 1.5.16 version remains in $($entry.Key)"
  }
}

powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-surface-hygiene.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'Release-surface guard failed at 1.5.17' }

claude plugin validate --strict .
if ($LASTEXITCODE -ne 0) { throw 'Strict Claude validation failed at 1.5.17' }

$uvPath = 'C:\Users\aryan\.local\bin\uv.exe'
& $uvPath lock --check --directory mcp_server
if ($LASTEXITCODE -ne 0) { throw 'Generated lock is stale' }

git diff --check $bumpBaseSha --
if ($LASTEXITCODE -ne 0) { throw 'Bump diff has whitespace errors' }
```

Expected: every declared version is `1.5.17`, no declared `1.5.16` remains, and all
focused source/version gates pass.

- [ ] **Step 7: Stage exactly the ten files and create the atomic bump commit**

```powershell
$bumpBaseSha = (git rev-parse HEAD).Trim()
$expectedPaths = @(
  '.claude-plugin/marketplace.json',
  '.claude-plugin/plugin.json',
  'installer/RookSetup.iss',
  'mcp_server/pyproject.toml',
  'mcp_server/uv.lock',
  'src/Rook/Rook.csproj',
  'src/RookBim/RookBim.csproj',
  'src/RookNative/RookNative.rc',
  'src/RookNative/RookNativePlugin.cpp',
  'src/RookNative/RookServer.cpp'
) | Sort-Object

git add -- @($expectedPaths)

$stagedPaths = @(git diff --cached --name-only | ForEach-Object { $_ -replace '\\', '/' } | Sort-Object)
if (($stagedPaths -join "`n") -ne ($expectedPaths -join "`n")) {
  throw "Staged path set is not the exact ten-file inventory: $($stagedPaths -join ', ')"
}

git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Staged bump has whitespace errors' }

git commit -m 'release: bump versions to 1.5.17'
if ($LASTEXITCODE -ne 0) { throw 'Atomic version-bump commit failed' }

$reviewedBumpHead = (git rev-parse HEAD).Trim()
if ((git rev-parse HEAD^).Trim() -ne $bumpBaseSha) {
  throw 'Bump commit is not the single direct child of the recorded base'
}
if (git status --porcelain) {
  git status --short
  throw 'Bump worktree is dirty after commit'
}
```

Expected: one clean commit directly above `$bumpBaseSha`.

- [ ] **Step 8: Re-run the committed-head gates**

```powershell
$bumpBaseSha = (git rev-parse HEAD^).Trim()
$reviewedBumpHead = (git rev-parse HEAD).Trim()
$expectedPaths = @(
  '.claude-plugin/marketplace.json',
  '.claude-plugin/plugin.json',
  'installer/RookSetup.iss',
  'mcp_server/pyproject.toml',
  'mcp_server/uv.lock',
  'src/Rook/Rook.csproj',
  'src/RookBim/RookBim.csproj',
  'src/RookNative/RookNative.rc',
  'src/RookNative/RookNativePlugin.cpp',
  'src/RookNative/RookServer.cpp'
) | Sort-Object

powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-surface-hygiene.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'Committed release-surface guard failed' }
claude plugin validate --strict .
if ($LASTEXITCODE -ne 0) { throw 'Committed strict Claude validation failed' }
$uvPath = 'C:\Users\aryan\.local\bin\uv.exe'
& $uvPath lock --check --directory mcp_server
if ($LASTEXITCODE -ne 0) { throw 'Committed lock check failed' }
git diff --check "$bumpBaseSha..$reviewedBumpHead"
if ($LASTEXITCODE -ne 0) { throw 'Committed diff check failed' }

$committedPaths = @(git diff --name-only "$bumpBaseSha..$reviewedBumpHead" | Sort-Object)
if (($committedPaths -join "`n") -ne ($expectedPaths -join "`n")) {
  throw 'Committed head no longer has the exact ten-file scope'
}

$expectedNumstat = [ordered]@{
  '.claude-plugin/marketplace.json' = @(2, 2)
  '.claude-plugin/plugin.json' = @(1, 1)
  'installer/RookSetup.iss' = @(1, 1)
  'mcp_server/pyproject.toml' = @(1, 1)
  'mcp_server/uv.lock' = @(60, 60)
  'src/Rook/Rook.csproj' = @(1, 1)
  'src/RookBim/RookBim.csproj' = @(1, 1)
  'src/RookNative/RookNative.rc' = @(4, 4)
  'src/RookNative/RookNativePlugin.cpp' = @(1, 1)
  'src/RookNative/RookServer.cpp' = @(1, 1)
}
$committedNumstat = [ordered]@{}
foreach ($row in @(git diff --numstat "$bumpBaseSha..$reviewedBumpHead" --)) {
  $parts = $row -split "`t", 3
  if ($parts.Count -ne 3 -or $parts[0] -notmatch '^\d+$' -or $parts[1] -notmatch '^\d+$') {
    throw "Unexpected committed numstat row: $row"
  }
  $committedNumstat[$parts[2] -replace '\\', '/'] = @([int]$parts[0], [int]$parts[1])
}
foreach ($path in $expectedNumstat.Keys) {
  $want = $expectedNumstat[$path]
  $got = $committedNumstat[$path]
  if ($null -eq $got -or $got[0] -ne $want[0] -or $got[1] -ne $want[1]) {
    throw "$path committed numstat is not $($want[0])/$($want[1])"
  }
}
$committedAdded = ($committedNumstat.Values | ForEach-Object { $_[0] } | Measure-Object -Sum).Sum
$committedDeleted = ($committedNumstat.Values | ForEach-Object { $_[1] } | Measure-Object -Sum).Sum
if ($committedAdded -ne 73 -or $committedDeleted -ne 73) {
  throw "Committed total numstat is $committedAdded/$committedDeleted; expected 73/73"
}

$lockDiff = @(git diff --unified=0 "$bumpBaseSha..$reviewedBumpHead" -- mcp_server/uv.lock)
$removed = @($lockDiff | Where-Object { $_ -match '^-' -and $_ -notmatch '^---' } | ForEach-Object { $_.Substring(1) })
$added = @($lockDiff | Where-Object { $_ -match '^\+' -and $_ -notmatch '^\+\+\+' } | ForEach-Object { $_.Substring(1) })
if ($removed.Count -ne 60 -or $added.Count -ne 60) {
  throw "Committed lock diff is $($removed.Count)/$($added.Count); expected 60/60"
}
$versionPairs = 0
$markerPairs = 0
for ($i = 0; $i -lt 60; $i++) {
  if ($removed[$i] -eq 'version = "1.5.16"' -and $added[$i] -eq 'version = "1.5.17"') {
    $versionPairs++
    continue
  }
  $oldTarget = $removed[$i] -replace ', marker = ".*"(?= \})', ''
  $newTarget = $added[$i] -replace ', marker = ".*"(?= \})', ''
  if ($removed[$i] -notmatch '^\s*\{ name = ' -or
      $added[$i] -notmatch '^\s*\{ name = ' -or
      $oldTarget -ne $newTarget) {
    throw "Unexpected committed lock change at pair ${i}"
  }
  $markerPairs++
}
if ($versionPairs -ne 1 -or $markerPairs -ne 59) {
  throw "Committed lock classification is version=$versionPairs marker=$markerPairs; expected 1/59"
}

git diff --unified=3 "$bumpBaseSha..$reviewedBumpHead" --
if ($LASTEXITCODE -ne 0) { throw 'Could not render the complete committed diff' }
```

Read the complete committed diff again. Require every removed token to be the
declared `1.5.16` form and every added token to be its `1.5.17` replacement. Require
the committed lock to retain the exact one-version / 59-marker classification from
Step 5. Expected: exact committed `73/73` numstat, all focused gates pass, and the
worktree remains clean. Do not build.

---

### Task 2: Open the bounded PR, recheck integration, and preserve merge provenance

**Files:**
- Modify: none.

**Interfaces:**
- Consumes: `$bumpBaseSha`, `$reviewedBumpHead`, and the clean atomic bump from Task 1.
- Produces: one reviewed regular merge commit `$privateMergeSha`, recorded for later source and artifact provenance.

- [ ] **Step 1: Refresh private main and reject overlap before publishing**

```powershell
$bumpBaseSha = (git rev-parse HEAD^).Trim()
$reviewedBumpHead = (git rev-parse HEAD).Trim()
$expectedPaths = @(
  '.claude-plugin/marketplace.json',
  '.claude-plugin/plugin.json',
  'installer/RookSetup.iss',
  'mcp_server/pyproject.toml',
  'mcp_server/uv.lock',
  'src/Rook/Rook.csproj',
  'src/RookBim/RookBim.csproj',
  'src/RookNative/RookNative.rc',
  'src/RookNative/RookNativePlugin.cpp',
  'src/RookNative/RookServer.cpp'
) | Sort-Object

git fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Could not refresh private origin/main' }

$mainPaths = @(git diff --name-only "$bumpBaseSha..origin/main" | ForEach-Object { $_ -replace '\\', '/' })
$overlap = @($mainPaths | Where-Object { $expectedPaths -contains $_ })
if ($overlap) { throw "Current main overlaps bump paths: $($overlap -join ', ')" }

git merge-tree --write-tree $reviewedBumpHead origin/main | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Reviewed bump does not merge cleanly with current main' }
```

Expected: no current-main overlap and a clean synthetic merge.

- [ ] **Step 2: Push the exact head and open one PR**

```powershell
$bumpBaseSha = (git rev-parse HEAD^).Trim()
$reviewedBumpHead = (git rev-parse HEAD).Trim()
git push -u origin codex/release-1-5-17-version-bump
if ($LASTEXITCODE -ne 0) { throw 'Could not push the bump branch' }
if ((git rev-parse HEAD).Trim() -ne (git rev-parse origin/codex/release-1-5-17-version-bump).Trim()) {
  throw 'Local and remote bump heads differ'
}

gh pr create --repo bringfire/Rook `
  --base main `
  --head codex/release-1-5-17-version-bump `
  --title 'release: bump versions to 1.5.17' `
  --body "Mechanical 10-file / 14-version-value bump from 1.5.16 to 1.5.17, including the accepted uv 0.11.3 marker normalization.`n`nBase: $bumpBaseSha`nReviewed head: $reviewedBumpHead`n`nNo builds, artifacts, installation, live acceptance, release notes, or public promotion are included."
if ($LASTEXITCODE -ne 0) { throw 'Could not create the bump PR' }

$prNumber = [int](gh pr view --repo bringfire/Rook --json number --jq '.number')
```

Expected: one open PR with exactly the ten version files and the reviewed head. Stop
for user/reviewer approval; do not merge automatically.

- [ ] **Step 3: After explicit merge authorization, recheck, merge, and verify provenance atomically**

```powershell
$bumpBaseSha = (git rev-parse HEAD^).Trim()
$reviewedBumpHead = (git rev-parse HEAD).Trim()
$expectedPaths = @(
  '.claude-plugin/marketplace.json',
  '.claude-plugin/plugin.json',
  'installer/RookSetup.iss',
  'mcp_server/pyproject.toml',
  'mcp_server/uv.lock',
  'src/Rook/Rook.csproj',
  'src/RookBim/RookBim.csproj',
  'src/RookNative/RookNative.rc',
  'src/RookNative/RookNativePlugin.cpp',
  'src/RookNative/RookServer.cpp'
) | Sort-Object

git fetch origin codex/release-1-5-17-version-bump
if ($LASTEXITCODE -ne 0) { throw 'Could not refresh the remote bump head' }
$remoteHead = (git rev-parse origin/codex/release-1-5-17-version-bump).Trim()
if ($remoteHead -ne $reviewedBumpHead) {
  throw "Remote bump head changed from reviewed $reviewedBumpHead to $remoteHead"
}

git fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Could not refresh private main before merge' }
$checkedMainSha = (git rev-parse origin/main).Trim()

$mainPaths = @(git diff --name-only "$bumpBaseSha..$checkedMainSha" | ForEach-Object { $_ -replace '\\', '/' })
$overlap = @($mainPaths | Where-Object { $expectedPaths -contains $_ })
if ($overlap) { throw "Current main overlaps bump paths: $($overlap -join ', ')" }

git merge-tree --write-tree $reviewedBumpHead $checkedMainSha | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Final synthetic merge failed' }
$prNumber = [int](gh pr view --repo bringfire/Rook --json number --jq '.number')
gh pr merge $prNumber --repo bringfire/Rook --merge --match-head-commit $reviewedBumpHead
if ($LASTEXITCODE -ne 0) { throw 'Regular PR merge failed' }

git fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Could not refresh merged private main' }
$privateMergeSha = (git rev-parse origin/main).Trim()
$parentLine = @((git rev-list --parents -n 1 $privateMergeSha).Trim() -split '\s+')

if ($parentLine.Count -ne 3) { throw "$privateMergeSha is not a two-parent merge commit" }
if ($parentLine[1] -ne $checkedMainSha) {
  throw "Merge first parent $($parentLine[1]) does not equal checked main $checkedMainSha"
}
if ($parentLine[2] -ne $reviewedBumpHead) {
  throw "Merge second parent $($parentLine[2]) does not equal reviewed bump $reviewedBumpHead"
}
if ((git rev-parse origin/main).Trim() -ne $privateMergeSha) {
  throw 'origin/main does not point to the verified private merge'
}

$prState = gh pr view $prNumber --repo bringfire/Rook --json state,mergeCommit | ConvertFrom-Json
if ($prState.state -ne 'MERGED' -or $prState.mergeCommit.oid -ne $privateMergeSha) {
  throw 'GitHub PR merge identity does not equal private origin/main'
}

Write-Host "Private 1.5.17 source and artifact provenance: $privateMergeSha"
```

Expected: the exact reviewed head merges cleanly into the checked current main as a
regular two-parent merge whose first parent is `$checkedMainSha`, whose second parent
is `$reviewedBumpHead`, and which is now private `origin/main`. Record
`$privateMergeSha`; do not build or promote in this plan.

---

## Completion Contract

Completion means:

- exactly ten files and 14 version values changed from `1.5.16` to `1.5.17`;
- the lock contains one generated local `rook-mcp` version replacement and exactly
  59 marker-only dependency-edge normalization pairs;
- exact numstat is `73/73`, with 13 version lines outside the lock and the accepted
  generated `60/60` lock diff;
- release-surface, strict Claude, lock, and diff gates passed;
- the bump is one atomic commit and one regular two-parent merge;
- private `origin/main` points to the verified merge SHA; and
- no build, artifact, installation, live acceptance, release note, public promotion,
  tag, or publication occurred.

The recorded private merge SHA is the starting provenance for the later build and
acceptance workflow. The later public promotion merge and public tag retain their
separate provenance roles defined by the approved specification.
