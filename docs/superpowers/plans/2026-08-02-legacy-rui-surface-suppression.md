# Legacy RUI Surface Suppression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop exposing the legacy `Rook.rui` toolbar while preserving supported Rook panels, commands, Grasshopper behavior, and RookBIM behavior.

**Architecture:** Remove the one managed loader and every active RUI copy path. Reuse existing deployment and registration owners for exact file/property cleanup; retain the dormant source asset and avoid new frameworks.

**Tech Stack:** C#/.NET 8, 7, and Framework 4.8; MSBuild; Windows PowerShell; Inno Setup 6; Rhino 8; Rhino.Inside.Revit.

## Global Constraints

- Pinned base: `f22904c21474b616e2fe3487f686c5632bba8a37`.
- Approved specification: `92d7c1581a8b26f978f8aee3aa18dea9c1f23059`.
- Approved plan ref: `refs/tags/plan/legacy-rui-suppression-2026-08-02-approved`; it must resolve to the exact execution `HEAD` whose parent is the approved specification.
- Retain and do not edit `src/Rook/UI/Rook.rui`.
- Do not modify native C++, Python MCP, RookBIM, panel/command implementations, historical documents, dependencies, or versions.
- Do not add a feature flag, cleanup framework, wildcard/directory deletion, settings scrubber, or live toolbar manipulation.
- Installed runtime children are exactly `net8.0`, `net7.0`, and `net48` under `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative`.
- Companion registry cleanup targets only `RuiFile` under `HKCU\Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B`.
- Before the explicit deployment gate, every command that builds `src/Rook/Rook.csproj` passes `-p:RhinoPluginDir=`.
- Rhino, Rhinoceros, Revit, and Grasshopper must be closed before installed-file or registry mutation.
- Run focused gates only; do not enter repository-wide test-debt work.

## File and commit structure

1. Runtime/source-local commit: loader, MSBuild, two PowerShell deployers, companion registration, and focused guards.
2. Installer/release commit: Inno migration, release guidance, and installer guards.
3. Evidence-only acceptance commit after all required gates pass.

---

### Task 0: Verify the approved execution boundary

**Files:**
- Read: `docs/superpowers/specs/2026-08-02-legacy-rui-surface-suppression-design.md`
- Read: `docs/superpowers/plans/2026-08-02-legacy-rui-surface-suppression.md`

**Interfaces:**
- Consumes: approved spec and pinned base.
- Produces: a clean, correctly based execution worktree.

- [ ] **Step 1: Verify ancestry, cleanliness, and host state**

```powershell
$base = 'f22904c21474b616e2fe3487f686c5632bba8a37'
$spec = '92d7c1581a8b26f978f8aee3aa18dea9c1f23059'
$planRef = 'refs/tags/plan/legacy-rui-suppression-2026-08-02-approved'
if ((git rev-parse "$spec^").Trim() -ne $base) { throw 'Approved spec parent changed.' }
git show-ref --verify --quiet $planRef
if ($LASTEXITCODE -ne 0) { throw 'Approved plan ref is missing.' }
$plan = (git rev-parse "$planRef^{commit}").Trim()
if ((git rev-parse HEAD).Trim() -ne $plan) { throw 'Execution must start at the exact approved plan commit.' }
if ((git rev-parse "$plan^").Trim() -ne $spec) { throw 'Approved plan parent changed.' }
if (@(git status --porcelain).Count -ne 0) { git status --short; throw 'Worktree is dirty.' }
$hosts = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '^(Rhino|Rhinoceros|Revit|Grasshopper)$' })
if ($hosts.Count -ne 0) { $hosts | Select ProcessName,Id; throw 'Close host applications.' }
```

Expected: exit `0` with no listed hosts.

---

### Task 1: Remove runtime and source/local RUI surfaces

**Files:**
- Modify: `src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs`
- Modify: `scripts/tests/deploy-local-testing-guards.tests.ps1`
- Modify: `src/Rook/RookPlugin.cs`
- Modify: `src/Rook/Rook.csproj`
- Modify: `scripts/deploy-local-testing.ps1`
- Modify: `install.ps1`
- Modify: `scripts/register-companion.ps1`

**Interfaces:**
- Consumes: existing `DeployToRhino`, runtime-copy functions, and companion registry verification.
- Produces: no managed RUI loader; exact per-runtime file cleanup; exact source/local `RuiFile` cleanup.

- [ ] **Step 1: Add the failing managed source contract**

Add this fact to `RookPluginLifecycleSourceTests`:

```csharp
[Fact]
public void LegacyRuiToolbar_HasNoActiveManagedLoader()
{
    var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
    Assert.DoesNotContain("_toolbarLoaded", source);
    Assert.DoesNotContain("EnsureToolbarLoaded", source);
    Assert.DoesNotContain("LoadToolbar", source);
    Assert.DoesNotContain("Rook.rui", source);
    Assert.DoesNotContain("ToolbarFiles.Open", source);
}
```

Keep all existing startup and panel assertions.

- [ ] **Step 2: Add the failing source/local guard**

In `deploy-local-testing-guards.tests.ps1`, add paths for `src/Rook/Rook.csproj` and `install.ps1`, then add and invoke `Test-LegacyRuiIsSuppressedFromSourceDeployments`. It must assert these exact contracts:

```powershell
Assert-NotContains -Text $project -Unexpected '<None Include="UI\Rook.rui"' -Message 'Build must not emit RUI.'
Assert-NotContains -Text $project -Unexpected '<Copy SourceFiles="$(TargetDir)$(TargetName).rui"' -Message 'MSBuild must not copy RUI.'
Assert-Contains -Text $project -Expected '<Delete Files="$(RhinoManagedRuntimeDir)\$(TargetName).rui" />' -Message 'MSBuild must exact-delete RUI.'

Assert-NotContains -Text $deploy -Unexpected "Copy-OptionalFile (Join-Path `$sourceDir 'Rook.rui')" -Message 'Local deploy must not copy RUI.'
Assert-Contains -Text $deploy -Expected "Remove-Item -LiteralPath (Join-Path `$targetDir 'Rook.rui') -Force -ErrorAction SilentlyContinue" -Message 'Local deploy must exact-delete RUI.'

Assert-NotContains -Text $sourceInstall -Unexpected 'Copy-Item (Join-Path $sourceDir "Rook.rui")' -Message 'Source installer must not copy RUI.'
Assert-Contains -Text $sourceInstall -Expected 'Remove-Item -LiteralPath (Join-Path $targetDir "Rook.rui") -Force -ErrorAction SilentlyContinue' -Message 'Source installer must exact-delete RUI.'

Assert-Contains -Text $registration -Expected "Remove-ItemProperty -LiteralPath `$RegBase -Name 'RuiFile' -ErrorAction SilentlyContinue" -Message 'Registration must remove RuiFile.'
Assert-Contains -Text $registration -Expected "Get-ItemProperty -LiteralPath `$RegBase -Name 'RuiFile' -ErrorAction SilentlyContinue" -Message 'Registration must verify RuiFile absence.'
Assert-Contains -Text $registration -Expected "`$Errors += 'RuiFile: expected absent'" -Message 'Retained RuiFile must fail verification.'
```

- [ ] **Step 3: Run the red gates**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -c Release --filter "FullyQualifiedName~RookPluginLifecycleSourceTests" -p:RhinoPluginDir=
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected: failures on the current loader and RUI copy/registration contracts.

- [ ] **Step 4: Remove the complete managed loader**

From `RookPlugin.cs`, delete `_toolbarLoaded`, the `EnsureToolbarLoaded()` call and wrapper, and the complete `LoadToolbar()` method. Add no replacement.

- [ ] **Step 5: Apply exact source/local cleanup**

In `Rook.csproj`, remove the RUI `<None>` item and RUI `<Copy>` element. Add this inside the existing `DeployToRhino` target after `MakeDir`:

```xml
<Delete Files="$(RhinoManagedRuntimeDir)\$(TargetName).rui" />
```

Replace each PowerShell RUI copy with the matching exact removal:

```powershell
# scripts/deploy-local-testing.ps1
Remove-Item -LiteralPath (Join-Path $targetDir 'Rook.rui') -Force -ErrorAction SilentlyContinue

# install.ps1
Remove-Item -LiteralPath (Join-Path $targetDir "Rook.rui") -Force -ErrorAction SilentlyContinue
```

After `register-companion.ps1` ensures `$RegBase` exists, add:

```powershell
Remove-ItemProperty -LiteralPath $RegBase -Name 'RuiFile' -ErrorAction SilentlyContinue
```

Add to its existing verification block:

```powershell
$verifyRuiFile = Get-ItemProperty -LiteralPath $RegBase -Name 'RuiFile' -ErrorAction SilentlyContinue
if ($verifyRuiFile) { $Errors += 'RuiFile: expected absent' }
```

Do not change the `-Unregister` path or any sibling file/value.

- [ ] **Step 6: Run the green gates and commit**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -c Release --filter "FullyQualifiedName~RookPluginLifecycleSourceTests" -p:RhinoPluginDir=
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
git diff --check
git add src/Rook/RookPlugin.cs src/Rook/Rook.csproj src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs scripts/deploy-local-testing.ps1 scripts/register-companion.ps1 scripts/tests/deploy-local-testing-guards.tests.ps1 install.ps1
git commit -m "fix(ui): suppress legacy RUI in source deployments"
```

Expected: both focused gates pass and exactly seven files enter the commit.

---

### Task 2: Remove installer and active release RUI surfaces

**Files:**
- Modify: `scripts/tests/release-installer-guards.tests.ps1`
- Modify: `installer/RookSetup.iss`
- Modify: `BUILDING.md`
- Modify: `.agents/skills/build-release/references/iss-source-paths.md`
- Modify: `.claude/skills/build-release/references/iss-source-paths.md`

**Interfaces:**
- Consumes: existing Inno `[InstallDelete]`, `[Files]`, `[Registry]`, and verification blocks.
- Produces: unconditional exact installer cleanup and accurate active release guidance.

- [ ] **Step 1: Add and run the failing installer guard**

Add and invoke `Test-LegacyRuiInstallerMigrationIsExact` in `release-installer-guards.tests.ps1`. It must:

- extract `[InstallDelete]` and require one exact, unconditional `Type: files` line for each runtime child;
- require no `Rook.rui` entry in `[Files]`;
- require `ValueType: none; ValueName: "RuiFile"; Flags: deletevalue dontcreatekey` with no `ValueData` or `Components`;
- require `RegValueExists(HKCU, BaseKey, 'RuiFile')` and reject `RuiFile: String;`;
- reject RUI copy commands in `BUILDING.md` while requiring exact destination removal;
- reject `Rook.rui` from both `iss-source-paths.md` files; and
- require those mirrored references to remain byte-identical.

Use these exact file-deletion expectations:

```powershell
foreach ($runtime in @('net8.0', 'net7.0', 'net48')) {
    $line = "Type: files; Name: `"{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\$runtime\Rook.rui`""
    Assert-Contains -Text $installDelete -Expected $line -Message "Missing exact $runtime RUI deletion."
    Assert-True -Condition (@($installDelete -split '\r?\n' | Where-Object { $_ -eq $line }).Count -eq 1) -Message "Expected one unconditional $runtime RUI deletion."
}
```

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: failure on the current `[Files]` or registry contract.

- [ ] **Step 2: Apply the exact Inno migration**

Add to `[InstallDelete]`, without component conditions:

```ini
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rui"
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0\Rook.rui"
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48\Rook.rui"
```

Remove the three RUI `[Files]` entries. Replace the companion `RuiFile` registry write with:

```ini
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: none; ValueName: "RuiFile"; Flags: deletevalue dontcreatekey
```

Remove the obsolete `RuiFile` variable, assignment, and string-value verification. Require absence instead:

```pascal
if (IsDotNet = 1) and RegValueExists(HKCU, BaseKey, 'RuiFile') then
begin
  Log('Rhino plugin verification failed: obsolete RuiFile value remains at ' + BaseKey);
  Exit;
end;
```

- [ ] **Step 3: Update only active build/release guidance**

In `BUILDING.md`, replace the three RUI copy lines with exact removals using `$net8Dest`, `$net7Dest`, and `$net48Dest`:

```powershell
Remove-Item -LiteralPath (Join-Path $net8Dest "Rook.rui") -Force -ErrorAction SilentlyContinue
```

Remove only the three RUI table rows and three `$files` entries from the Agent `iss-source-paths.md`; copy it byte-for-byte to the Claude mirror. Do not edit either `SKILL.md` unless a fresh scoped search finds an active RUI requirement there.

- [ ] **Step 4: Run the green guard, scan scope, and commit**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
$active = @('src/Rook/RookPlugin.cs','src/Rook/Rook.csproj','scripts/deploy-local-testing.ps1','scripts/register-companion.ps1','install.ps1','installer/RookSetup.iss','BUILDING.md','.agents/skills/build-release/references/iss-source-paths.md','.claude/skills/build-release/references/iss-source-paths.md')
rg -n 'EnsureToolbarLoaded|LoadToolbar|_toolbarLoaded|Copy.*Rook\.rui|Source:.*Rook\.rui|ValueName: "RuiFile"; ValueData:' $active
git diff --check
git add installer/RookSetup.iss scripts/tests/release-installer-guards.tests.ps1 BUILDING.md .agents/skills/build-release/references/iss-source-paths.md .claude/skills/build-release/references/iss-source-paths.md
git commit -m "fix(installer): retire legacy RUI surface"
```

Expected: guard exit `0`, scoped scan has no matches, and exactly five files enter the commit.

---

### Task 3: Focused build and host-closed acceptance

**Files:**
- Create: `docs/superpowers/reports/2026-08-02-legacy-rui-surface-suppression-acceptance.md`

**Interfaces:**
- Consumes: the exact two reviewed implementation commits.
- Produces: durable focused evidence without entering RS-02 or unrelated release work.

- [ ] **Step 1: Enforce scope and rerun authoritative gates**

```powershell
$hosts = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '^(Rhino|Rhinoceros|Revit|Grasshopper)$' })
if ($hosts.Count -ne 0) { $hosts | Select ProcessName,Id; throw 'Hosts must be closed.' }
$expectedPaths = @(
  '.agents/skills/build-release/references/iss-source-paths.md'
  '.claude/skills/build-release/references/iss-source-paths.md'
  'BUILDING.md'
  'docs/superpowers/plans/2026-08-02-legacy-rui-surface-suppression.md'
  'docs/superpowers/specs/2026-08-02-legacy-rui-surface-suppression-design.md'
  'install.ps1'
  'installer/RookSetup.iss'
  'scripts/deploy-local-testing.ps1'
  'scripts/register-companion.ps1'
  'scripts/tests/deploy-local-testing-guards.tests.ps1'
  'scripts/tests/release-installer-guards.tests.ps1'
  'src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs'
  'src/Rook/Rook.csproj'
  'src/Rook/RookPlugin.cs'
) | Sort-Object
$actualPaths = @(git diff --name-only f22904c21474b616e2fe3487f686c5632bba8a37...HEAD) | Sort-Object
$scopeDelta = @(Compare-Object -ReferenceObject $expectedPaths -DifferenceObject $actualPaths)
if ($scopeDelta.Count -ne 0) { $scopeDelta | Format-Table; throw 'Changed-file set differs from the exact pre-acceptance allowlist.' }

dotnet test src\Rook.Tests\Rook.Tests.csproj -c Release --filter "FullyQualifiedName~RookPluginLifecycleSourceTests|FullyQualifiedName~RookVisionPanelHostTests" -p:RhinoPluginDir=
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: exact changed-file equality and all three focused gates pass. Do not run the repository-wide suite.

- [ ] **Step 2: Build clean managed payloads without deployment**

```powershell
foreach ($runtime in @('net8.0','net7.0','net48')) { Remove-Item -LiteralPath (Join-Path "src\Rook\bin\Release\$runtime" 'Rook.rui') -Force -ErrorAction SilentlyContinue }
dotnet build src\Rook\Rook.csproj -c Release -p:RhinoPluginDir=
dotnet build src\RookBim\RookBim.csproj -c Release -p:RhinoPluginDir=
$ruiOutputs = @(Get-ChildItem src\Rook\bin\Release -Recurse -File -Filter Rook.rui -ErrorAction SilentlyContinue)
if ($ruiOutputs.Count -ne 0) { throw "Managed outputs contain RUI: $($ruiOutputs.FullName -join ', ')" }
```

Expected: both builds succeed and no managed output contains `Rook.rui`. Record existing warnings; do not repair them here.

- [ ] **Step 3: Verify the three source/local deployment owners**

With hosts closed, seed `src/Rook/UI/Rook.rui` into each exact installed runtime child and seed the companion `RuiFile` value before each run. Execute:

```powershell
$pluginRoot = Join-Path $env:APPDATA 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative'
$regPath = 'HKCU:\Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B'
foreach ($runtime in @('net8.0','net7.0','net48')) {
  $dir = Join-Path $pluginRoot $runtime
  New-Item -ItemType Directory -Path $dir -Force | Out-Null
  Copy-Item -LiteralPath 'src\Rook\UI\Rook.rui' -Destination (Join-Path $dir 'Rook.rui') -Force
}
New-Item -Path $regPath -Force | Out-Null
Set-ItemProperty -LiteralPath $regPath -Name 'RuiFile' -Value (Join-Path $pluginRoot 'net8.0\Rook.rui') -Type String
```

1. `dotnet build src\Rook\Rook.csproj -c Release -t:Rebuild` — three files absent; registry deliberately unchanged.
2. Immediately rebuild `dotnet build src\RookBim\RookBim.csproj -c Release -p:RhinoPluginDir=`. Require success and a current `src\Rook\bin\Release\net48\RookBim.dll`; do not rebuild `Rook.csproj` again before deployment or packaging.
3. Reseed, then run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -SkipBuild -SkipChirpInstall` — files and registry value absent.
4. Reseed, then run `powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 -SkipNative -SkipChirp -SkipConfig -Json` — files and registry value absent; no companion deploy/register error.

Use this assertion after each run, setting `$expectRegistryAbsent` to `$false` only for MSBuild:

```powershell
$remaining = @(foreach ($runtime in @('net8.0','net7.0','net48')) { $path = Join-Path (Join-Path $pluginRoot $runtime) 'Rook.rui'; if (Test-Path -LiteralPath $path) { $path } })
if ($remaining.Count -ne 0) { throw "Legacy files remain: $($remaining -join ', ')" }
$ruiValue = Get-ItemProperty -LiteralPath $regPath -Name 'RuiFile' -ErrorAction SilentlyContinue
if ($expectRegistryAbsent -and $ruiValue) { throw 'RuiFile remains.' }
if (-not $expectRegistryAbsent -and -not $ruiValue) { throw 'MSBuild changed registry ownership.' }
```

If an unrelated MCP, Chirp, or toolchain prerequisite blocks a whole-script run, stop and record the environmental block. Do not change unrelated code.

- [ ] **Step 4: Compile and exercise the existing installer**

Run the existing source-path checklist in `.agents/skills/build-release/references/iss-source-paths.md`. Confirm the complete managed output is reused and no command rebuilds `Rook.csproj` after the final RookBIM build. If unrelated staged artifacts are missing, stop rather than refreshing dependencies.

```powershell
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' 'installer\RookSetup.iss'
if ($LASTEXITCODE -ne 0) { throw 'ISCC failed.' }
$installer = (Resolve-Path 'installer\output\Rook-Setup-1.5.16.exe').Path
function Invoke-RuiCandidateInstaller([string]$components) {
  $componentArg = '/COMPONENTS="' + $components + '"'
  $p = Start-Process -FilePath $installer -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',$componentArg) -Wait -PassThru
  if ($p.ExitCode -ne 0) { throw "Installer failed with $($p.ExitCode)." }
}
$pluginRoot = Join-Path $env:APPDATA 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative'
$regPath = 'HKCU:\Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B'
$legacySource = (Resolve-Path 'src\Rook\UI\Rook.rui').Path
$runtimes = @('net8.0','net7.0','net48')
function Clear-LegacyRuiFixture {
  foreach ($runtime in $runtimes) { Remove-Item -LiteralPath (Join-Path (Join-Path $pluginRoot $runtime) 'Rook.rui') -Force -ErrorAction SilentlyContinue }
  Remove-ItemProperty -LiteralPath $regPath -Name 'RuiFile' -ErrorAction SilentlyContinue
}
function Seed-LegacyRuiFixture {
  foreach ($runtime in $runtimes) {
    $dir = Join-Path $pluginRoot $runtime
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    Copy-Item -LiteralPath $legacySource -Destination (Join-Path $dir 'Rook.rui') -Force
  }
  New-Item -Path $regPath -Force | Out-Null
  New-ItemProperty -LiteralPath $regPath -Name 'RuiFile' -PropertyType String -Value (Join-Path $pluginRoot 'net8.0\Rook.rui') -Force | Out-Null
}
function Assert-LegacyRuiAbsent {
  $remaining = @(foreach ($runtime in $runtimes) { $path = Join-Path (Join-Path $pluginRoot $runtime) 'Rook.rui'; if (Test-Path -LiteralPath $path) { $path } })
  if ($remaining.Count -ne 0) { throw "Legacy files remain: $($remaining -join ', ')" }
  $ruiValue = Get-ItemProperty -LiteralPath $regPath -Name 'RuiFile' -ErrorAction SilentlyContinue
  if ($ruiValue) { throw 'RuiFile remains.' }
}

Clear-LegacyRuiFixture
Invoke-RuiCandidateInstaller 'plugins'
Assert-LegacyRuiAbsent

Seed-LegacyRuiFixture
Invoke-RuiCandidateInstaller 'plugins'
Assert-LegacyRuiAbsent

Seed-LegacyRuiFixture
Invoke-RuiCandidateInstaller 'plugins'
Assert-LegacyRuiAbsent

Seed-LegacyRuiFixture
Invoke-RuiCandidateInstaller 'mcp'
Assert-LegacyRuiAbsent
```

The four host-closed cases are, in order:

1. Candidate non-creation from an absent legacy state.
2. Seeded legacy migration state with the plugin component selected.
3. Seeded repair/idempotence state with the plugin component selected.
4. Seeded plugin-deselected migration state.

These are seeded migration-state checks, not claims of a literal clean-machine install or an actual previous-version upgrade. Do not uninstall the product solely to manufacture either fixture.

- [ ] **Step 5: Run bounded live acceptance**

Standalone Rhino:

- confirm no Rook toolbar, missing-RUI prompt, or toolbar-load warning;
- invoke `_ShowRookChat`, `_ShowRookKnowledgeGraph`, and `_ShowRookVision` once;
- record only command recognition and arrival at the existing panel boundary; and
- require the following exact harness command to exit `0`:

```powershell
$rookPython = Join-Path $env:LOCALAPPDATA 'Rook\venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $rookPython -PathType Leaf)) { throw "Installed Rook interpreter missing: $rookPython" }
& $rookPython scripts\run_rhino_runtime_harness.py --smoke ping-only
if ($LASTEXITCODE -ne 0) { throw 'Standalone ping-only harness failed.' }
```

Admitted Rhino.Inside.Revit host:

- confirm no Rook toolbar or missing-RUI warning;
- with Revit/Rhino.Inside running, execute the exact non-mutating checks below; record success and the named self-report fields, but do not persist document names, paths, or identity payloads; and
- record command registration/invocation parity only.

```powershell
$revit = @(Get-Process Revit -ErrorAction SilentlyContinue | Sort-Object StartTime -Descending)
if ($revit.Count -ne 1) { throw 'Require exactly one admitted Revit host.' }
$revitProcessId = $revit[0].Id
$records = @(Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Rook\discovery\*.json') -File -ErrorAction SilentlyContinue | ForEach-Object {
  try { Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json } catch { $null }
} | Where-Object { $_ -and $_.processId -eq $revitProcessId -and $_.pluginType -eq 'native' })
if ($records.Count -ne 1) { throw 'Require one native discovery record owned by the admitted Revit process.' }
$port = [int]$records[0].port
if ($port -le 0) { throw 'Discovery record has no positive port.' }
$baseUrl = "http://127.0.0.1:$port"
$null = Invoke-RestMethod -Method Get -Uri "$baseUrl/ping"
$null = Invoke-RestMethod -Method Get -Uri "$baseUrl/bim/status"
$null = Invoke-RestMethod -Method Get -Uri "$baseUrl/bim/active-document"

$companionPath = Join-Path $env:LOCALAPPDATA "Rook\discovery\companion-$revitProcessId.json"
$companion = Get-Content -LiteralPath $companionPath -Raw | ConvertFrom-Json
if ($companion.processId -ne $revitProcessId -or -not $companion.rhinoInside -or -not $companion.deferredLocalStartupComplete -or -not $companion.startupComplete -or -not $companion.bridgeRegistered) {
  throw 'Companion self-report is not healthy for the admitted Revit process.'
}
$companion | Select-Object processId,processName,rhinoInside,assemblyLocation,runtimeChild,targetFramework,startupGateAttached,deferredLocalStartupComplete,startupComplete,bridgeRegistered,panelsRegistered,onLoadUtc,startupCompleteUtc,statusUpdatedUtc
```

Do not diagnose or fix panel contents, sizing, focus, WebView, or other RS-02 behavior. Close all hosts afterward.

- [ ] **Step 6: Record and commit acceptance evidence**

Create `docs/superpowers/reports/2026-08-02-legacy-rui-surface-suppression-acceptance.md` recording exact base/commit identities, test counts, build warnings, output/install/registry checks, installer path and SHA-256, bounded host results, RS-02 exclusion, final host state, and worktree state.

```powershell
git diff --check
$dirty = @(git status --porcelain)
if ($dirty.Count -ne 1 -or $dirty[0] -notmatch '2026-08-02-legacy-rui-surface-suppression-acceptance\.md$') { git status --short; throw 'Only the acceptance report may remain.' }
git add docs/superpowers/reports/2026-08-02-legacy-rui-surface-suppression-acceptance.md
git commit -m "docs: record legacy RUI suppression acceptance"
```

Write `PASS` only for observed passing gates; record skipped or blocked gates literally.

---

## Final review gate

```powershell
git diff --check f22904c21474b616e2fe3487f686c5632bba8a37...HEAD
git diff --stat f22904c21474b616e2fe3487f686c5632bba8a37...HEAD
$expectedPaths = @(
  '.agents/skills/build-release/references/iss-source-paths.md'
  '.claude/skills/build-release/references/iss-source-paths.md'
  'BUILDING.md'
  'docs/superpowers/plans/2026-08-02-legacy-rui-surface-suppression.md'
  'docs/superpowers/reports/2026-08-02-legacy-rui-surface-suppression-acceptance.md'
  'docs/superpowers/specs/2026-08-02-legacy-rui-surface-suppression-design.md'
  'install.ps1'
  'installer/RookSetup.iss'
  'scripts/deploy-local-testing.ps1'
  'scripts/register-companion.ps1'
  'scripts/tests/deploy-local-testing-guards.tests.ps1'
  'scripts/tests/release-installer-guards.tests.ps1'
  'src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs'
  'src/Rook/Rook.csproj'
  'src/Rook/RookPlugin.cs'
) | Sort-Object
$actualPaths = @(git diff --name-only f22904c21474b616e2fe3487f686c5632bba8a37...HEAD) | Sort-Object
$scopeDelta = @(Compare-Object -ReferenceObject $expectedPaths -DifferenceObject $actualPaths)
if ($scopeDelta.Count -ne 0) { $scopeDelta | Format-Table; throw 'Final changed-file set differs from the exact allowlist.' }
git status --short
```

Reject native, Python, RookBIM, dormant RUI, panel/command implementation, historical, dependency, version, or unrelated release changes. Push and PR creation require a separate explicit integration decision.
