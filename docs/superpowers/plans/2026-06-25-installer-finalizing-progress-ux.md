# Installer Finalizing Progress UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show an honest indeterminate `Finalizing Rook` page during the long post-install finalization wait without weakening fail-closed installer behavior.

**Architecture:** Keep the current Pascal-script `RunPostInstallSetup()` orchestration and blocking `Exec(... ewWaitUntilTerminated ...)` exit-code gate. Add an Inno output marquee page only around the child process launch/wait after component selection and private Python checks pass. Pin this with source guards so the work does not drift into `[Run]`, fake percentages, or `post_install.py` telemetry.

**Tech Stack:** Inno Setup Pascal Script (`installer/RookSetup.iss`), PowerShell source guard tests (`scripts/tests/release-installer-guards.tests.ps1`).

---

## File Map

- `installer/RookSetup.iss`
  - Add a `TOutputMarqueeProgressWizardPage` variable and two helper procedures.
  - Show/animate the page immediately before the blocking `Exec` that runs `post_install.py`.
  - Hide the page in a protected `finally` block.
  - Fix the stale source-section comment that says `post_install.py` is used by `[Run]`.

- `scripts/tests/release-installer-guards.tests.ps1`
  - Strengthen the `[Run]` guard by extracting the actual `[Run]` section and asserting it does not mention `post_install.py` or the private Python executable.
  - Add assertions for the finalizing page type, copy, `Show`, `Animate`, `Hide`, and absence of `SetProgress`.
  - Keep existing assertions for Pascal-script gating and nonzero exit abort behavior.

## Source-Only Guard Runner

The full release guard script also checks built release payloads. For this branch's red/green loop, run only the source-only guard functions with this command:

```powershell
$repo = (Get-Location).Path
$script = Get-Content scripts\tests\release-installer-guards.tests.ps1 -Raw
$funcStart = $script.IndexOf('function Assert-True')
$invokeStart = $script.IndexOf("`nTest-InstallerPackagesBundledPythonRuntime")
$defs = $script.Substring($funcStart, $invokeStart - $funcStart)
$global:TestRoot = Join-Path $repo 'scripts\tests'
$global:RepoRoot = $repo
$global:InstallerScript = Join-Path $repo 'installer\RookSetup.iss'
$global:BuildReleaseSkill = Join-Path $repo '.agents\skills\build-release\SKILL.md'
$global:IssSourcePaths = Join-Path $repo '.agents\skills\build-release\references\iss-source-paths.md'
$global:ClaudeBuildReleaseSkill = Join-Path $repo '.claude\skills\build-release\SKILL.md'
$global:ClaudeIssSourcePaths = Join-Path $repo '.claude\skills\build-release\references\iss-source-paths.md'
$global:VersionLocations = Join-Path $repo '.agents\skills\build-release\references\version-locations.md'
$global:ClaudeVersionLocations = Join-Path $repo '.claude\skills\build-release\references\version-locations.md'
$global:BuildingDoc = Join-Path $repo 'BUILDING.md'
$global:PostInstallScript = Join-Path $repo 'installer\post_install.py'
$global:DoctorScript = Join-Path $repo 'mcp_server\src\rook\doctor.py'
$global:BuildNativeScript = Join-Path $repo 'build_native.ps1'
$global:ReleaseArtifactValidator = Join-Path $repo 'scripts\validate-release-artifacts.ps1'
$global:CompanionNet8RuntimeConfig = Join-Path $repo 'src\Rook\bin\Release\net8.0\Rook.runtimeconfig.json'
$global:CompanionNet7RuntimeConfig = Join-Path $repo 'src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json'
$global:CompanionNet8Rhp = Join-Path $repo 'src\Rook\bin\Release\net8.0\Rook.rhp'
$global:CompanionNet7Rhp = Join-Path $repo 'src\Rook\bin\Release\net7.0\Rook.rhp'
$global:CompanionNet48Rhp = Join-Path $repo 'src\Rook\bin\Release\net48\Rook.rhp'
$global:CompanionNet48RookBimDll = Join-Path $repo 'src\Rook\bin\Release\net48\RookBim.dll'
$global:CompanionNet48WebView2Core = Join-Path $repo 'src\Rook\bin\Release\net48\Microsoft.Web.WebView2.Core.dll'
$global:CompanionNet48WebView2Loader = Join-Path $repo 'src\Rook\bin\Release\net48\runtimes\win-x64\native\WebView2Loader.dll'
$global:FfmpegValidationScript = Join-Path $repo 'scripts\validate-ffmpeg-bundle.ps1'
$global:FfmpegBuildScript = Join-Path $repo 'scripts\ffmpeg\build-rook-ffmpeg.ps1'
$global:FfmpegConfigureRecipe = Join-Path $repo 'scripts\ffmpeg\rook-ffmpeg-configure.txt'
$global:ReleaseWorkflow = Join-Path $repo '.github\workflows\release.yml'
Invoke-Expression $defs
Test-InstallerFailsWhenPostInstallFails
Test-InstallerExplainsOfflineWheelhouseProgress
Write-Host 'Targeted installer progress guards passed.'
```

---

### Task 1: Red Source Guards

**Files:**
- Modify: `scripts/tests/release-installer-guards.tests.ps1`

- [ ] **Step 1: Strengthen `[Run]` extraction in `Test-InstallerFailsWhenPostInstallFails`**

Replace the current exact literal `[Run]` guard inside `Test-InstallerFailsWhenPostInstallFails` with a section-aware check:

```powershell
$runMatch = [regex]::Match($content, '(?ms)^\[Run\]\s*(?<block>.*?)(?=^\[|$)')
$runBlock = if ($runMatch.Success) { $runMatch.Groups['block'].Value } else { '' }
Assert-NotContains -Text $runBlock -Unexpected 'post_install.py' -Message 'Post-install must not run through [Run], which cannot gate child exit codes.'
Assert-NotContains -Text $runBlock -Unexpected '{localappdata}\Rook\python\cpython-3.11.9\python.exe' -Message 'Bundled private Python post-install must not be launched from [Run].'
```

Keep these existing assertions immediately after the new section-aware guard:

```powershell
Assert-Contains -Text $content -Expected 'function RunPostInstallSetup(): Boolean;' -Message 'Installer must run post_install.py from Pascal script where ResultCode can be checked.'
Assert-Contains -Text $content -Expected 'Exec(PythonExe, Args, '''', SW_HIDE, ewWaitUntilTerminated, ResultCode)' -Message 'Installer post-install runner must capture the child process exit code.'
Assert-Contains -Text $content -Expected 'ResultCode <> 0' -Message 'Installer must explicitly reject a nonzero post_install.py exit code.'
Assert-Contains -Text $content -Expected 'Abort;' -Message 'Installer must abort when post_install.py fails instead of reporting success.'
Assert-NotContains -Text $content -Unexpected 'Rook Python setup failed' -Message 'Installer must not misdiagnose client/finalization failures as Python setup failures.'
Assert-Contains -Text $content -Expected 'Rook post-install finalization failed' -Message 'Installer failure dialog must name post-install finalization, not only Python setup.'
```

- [ ] **Step 2: Add red assertions for finalizing marquee UX**

Append these assertions to `Test-InstallerExplainsOfflineWheelhouseProgress`:

```powershell
Assert-Contains -Text $content -Expected 'FinalizingRookPage: TOutputMarqueeProgressWizardPage;' -Message 'Installer must define an indeterminate finalization progress page.'
Assert-Contains -Text $content -Expected 'CreateOutputMarqueeProgressPage(''Finalizing Rook''' -Message 'Installer must create a dedicated Finalizing Rook marquee page.'
Assert-Contains -Text $content -Expected 'First-time setup can take 10-12 minutes. The installer is still working.' -Message 'Finalization page must tell users the long wait is expected and active.'
Assert-Contains -Text $content -Expected 'private Python, bundled wheels, MCP entries, skills, and validation' -Message 'Finalization page must name the real work being performed.'
Assert-Contains -Text $content -Expected 'FinalizingRookPage.Show;' -Message 'Installer must show the finalization page before post-install work starts.'
Assert-Contains -Text $content -Expected 'FinalizingRookPage.Animate;' -Message 'Installer must animate the indeterminate finalization page.'
Assert-Contains -Text $content -Expected 'HideFinalizingRookPage();' -Message 'Installer must hide the finalization page after post-install work returns.'
Assert-Contains -Text $content -Expected 'finally' -Message 'Installer must protect finalization page cleanup with finally.'
Assert-NotContains -Text $content -Unexpected 'FinalizingRookPage.SetProgress' -Message 'Finalization UX must remain indeterminate and must not fake percentages.'
Assert-Contains -Text $content -Expected 'Post-install setup script (always included, launched from Pascal script)' -Message 'Installer source comment must not claim post_install.py is launched from [Run].'
Assert-NotContains -Text $content -Unexpected 'Post-install setup script (always included, used by [Run])' -Message 'Installer source comment must not contradict the Pascal-script post-install contract.'
```

- [ ] **Step 3: Run targeted source guards and verify red**

Run the source-only guard runner from the section above.

Expected result: `Test-InstallerExplainsOfflineWheelhouseProgress` fails on missing `FinalizingRookPage: TOutputMarqueeProgressWizardPage;`.

- [ ] **Step 4: Commit red guards**

```powershell
git add scripts/tests/release-installer-guards.tests.ps1
git commit -m "test(installer): guard finalizing progress ux"
```

---

### Task 2: Inno Marquee Page Implementation

**Files:**
- Modify: `installer/RookSetup.iss`

- [ ] **Step 1: Add the finalization page variable**

In the `[Code] var` block, after `RookPreflightLastSweepTick: Cardinal;`, add:

```pascal
  FinalizingRookPage: TOutputMarqueeProgressWizardPage;
```

- [ ] **Step 2: Fix the stale post-install source comment**

Replace:

```pascal
; --- Post-install setup script (always included, used by [Run]) ---
```

with:

```pascal
; --- Post-install setup script (always included, launched from Pascal script) ---
```

- [ ] **Step 3: Add page helpers before `RunPostInstallSetup()`**

Insert these procedures immediately before `function RunPostInstallSetup(): Boolean;`:

```pascal
procedure ShowFinalizingRookPage();
begin
  if FinalizingRookPage = nil then
  begin
    FinalizingRookPage :=
      CreateOutputMarqueeProgressPage(
        'Finalizing Rook',
        'First-time setup can take 10-12 minutes. The installer is still working.');
  end;

  FinalizingRookPage.SetText(
    'This step configures private Python, bundled wheels, MCP entries, skills, and validation.',
    '');
  FinalizingRookPage.Show;
  FinalizingRookPage.Animate;
  WizardForm.Update;
end;

procedure HideFinalizingRookPage();
begin
  if FinalizingRookPage <> nil then
    FinalizingRookPage.Hide;
end;
```

- [ ] **Step 4: Wrap only the blocking child process**

Inside `RunPostInstallSetup()`, leave `PostInstallSelected()` and `FileExists(PythonExe)` checks before the page show. Replace the direct `Exec` block with:

```pascal
  WizardForm.StatusLabel.Caption :=
    'Finalizing Rook: creating private Python environments and installing bundled wheels offline (no internet download required). This can take several minutes.';
  WizardForm.StatusLabel.Update;
  Log('Post-install: running post_install.py with private Python: ' + PythonExe);
  ShowFinalizingRookPage();
  try
    if not Exec(PythonExe, Args, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      Log('Post-install failed: could not launch post_install.py');
      MsgBox(
        'Rook could not launch its post-install Python setup.' + #13#10 + #13#10 +
        'Close Rhino/Revit, then rerun the installer repair flow.',
        mbCriticalError, MB_OK);
      Result := False;
      Exit;
    end;
  finally
    HideFinalizingRookPage();
  end;
```

Do not move the `if ResultCode <> 0 then` block into the `try` body. It should stay after `finally` so the page is hidden before showing the critical error dialog.

- [ ] **Step 5: Run targeted source guards and verify green**

Run the source-only guard runner from the section above.

Expected result: `Targeted installer progress guards passed.`

- [ ] **Step 6: Run diff check**

```powershell
git diff --check
```

Expected result: no whitespace errors. CRLF warnings are acceptable if reported by Git.

- [ ] **Step 7: Commit implementation**

```powershell
git add installer/RookSetup.iss scripts/tests/release-installer-guards.tests.ps1
git commit -m "fix(installer): show finalizing progress page"
```

---

### Task 3: PR Validation Notes

**Files:**
- No file changes.

- [ ] **Step 1: Record the installer-smoke requirement in the PR body**

Add this checklist to the PR body under verification:

```text
Manual installer smoke required before release promotion:
- Finalizing page shown before post_install.py wait: not yet run
- Copy says 10-12 minutes and installer still working: not yet run
- Marquee animation continued during blocking Exec: not yet run
- Install success reached final page: not yet run
- Nonzero post_install.py still aborts setup: not yet run
```

- [ ] **Step 2: If a release-prepared installer smoke is run, replace `not yet run` values**

Use the release-prepared installer generated by the normal Rook release workflow. Replace the checklist values with observed `yes` or `no` results:


```text
Finalizing page shown before post_install.py wait: yes/no
Copy says 10-12 minutes and installer still working: yes/no
Marquee animation continued during blocking Exec: yes/no
Install success reached final page: yes/no
Nonzero post_install.py still aborts setup: yes/no
```

- [ ] **Step 3: If animation freezes, do not expand scope**

If the page text renders but the marquee freezes while `Exec` blocks, keep Phase 1 as-is and document that behavior in the PR. Phase 2 owns telemetry/polling.
