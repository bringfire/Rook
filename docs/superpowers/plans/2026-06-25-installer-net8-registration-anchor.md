# Installer Net8 Registration Anchor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the standalone Rhino companion registration anchor from `net7.0` to `net8.0` while preserving packaged `net7.0` fallback coverage.

**Architecture:** This is a two-file installer slice. The PowerShell guard test pins the intended installer contract, and `installer/RookSetup.iss` implements the matching registry metadata and post-install verification paths.

**Tech Stack:** Inno Setup script, PowerShell guard tests, Git/GitHub PR workflow.

---

## File Structure

- Modify `scripts/tests/release-installer-guards.tests.ps1`: update release guard assertions so `net8.0` is the standalone Rhino registration anchor and `net7.0` remains a packaged fallback.
- Modify `installer/RookSetup.iss`: update companion `RuiFile`, `PlugIn\FileName`, and post-install companion verification path from `net7.0` to `net8.0`.

No production Python, C#, native C++, release version, generated installer, or knowledge-store files are part of this plan.

---

### Task 1: Guard Test Contract

**Files:**
- Modify: `scripts/tests/release-installer-guards.tests.ps1`

- [ ] **Step 1: Update companion payload packaging assertions**

In `Test-InstallerPackagesMultiRuntimeCompanionPayloads`, keep the runtime-folder deployment loop but make the `Rook.rhp` packaging assertions explicit by source directory:

```powershell
foreach ($runtime in @('net8.0', 'net7.0', 'net48')) {
    Assert-Contains -Text $content -Expected "DestDir: `"{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\$runtime`"" -Message "Installer must deploy the companion into the $runtime runtime subfolder."
}

Assert-Contains -Text $content -Expected 'Source: "{#CompanionNet8Dir}\Rook.rhp"' -Message 'Installer must package the net8.0 Rook.rhp payload.'
Assert-Contains -Text $content -Expected 'Source: "{#CompanionNet7Dir}\Rook.rhp"' -Message 'Installer must package the net7.0 fallback Rook.rhp payload.'
Assert-Contains -Text $content -Expected 'Source: "{#CompanionNet48Dir}\Rook.rhp"' -Message 'Installer must package the net48 Rook.rhp payload.'
```

- [ ] **Step 2: Rename the net7 payload role in the built-payload check**

In `Test-BuiltCompanionPayloadsExist`, change the net7 message to say fallback:

```powershell
Assert-True -Condition (Test-Path $CompanionNet7Rhp) -Message "Built net7.0 fallback companion payload is missing: $CompanionNet7Rhp"
```

- [ ] **Step 3: Pin net8 RUI registration and reject net7 RUI registration**

In `Test-InstallerWritesRhinoPluginEnumerationMetadata`, assert the companion `RuiFile` registration points at `net8.0` and does not point at `net7.0`:

```powershell
Assert-Contains -Text $content -Expected 'ValueName: "RuiFile"; ValueData: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rui"' -Message 'Installer must pre-populate the companion RuiFile metadata for Rhino plugin enumeration.'
Assert-NotContains -Text $content -Unexpected 'ValueName: "RuiFile"; ValueData: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0\Rook.rui"' -Message 'Installer must not register the net7.0 companion RUI as the standalone Rhino metadata anchor.'
```

- [ ] **Step 4: Pin net8 RHP registration and reject net7 RHP registration**

In `Test-InstallerVerifiesRhinoPluginRegistrationAfterInstall`, assert the companion verification path and registry `FileName` point at `net8.0`, and reject the old `net7.0` anchor:

```powershell
Assert-Contains -Text $content -Expected 'CompanionPath := ExpandConstant(''{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rhp'');' -Message 'Installer verification must use the net8.0 companion runtime child as the direct-registry anchor.'
Assert-Contains -Text $content -Expected 'ValueName: "FileName"; ValueData: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rhp"' -Message 'Installer must register the net8.0 companion runtime child RHP anchor.'
Assert-NotContains -Text $content -Unexpected 'ValueName: "FileName"; ValueData: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0\Rook.rhp"' -Message 'Installer must not register the net7.0 companion runtime child as the standalone Rhino anchor.'
```

- [ ] **Step 5: Run the guard tests against the current installer**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected before Task 2 is not required to fail in this branch because the installer edits already exist locally. Expected after Task 2: exit code `0`.

---

### Task 2: Installer Registration Anchor

**Files:**
- Modify: `installer/RookSetup.iss`

- [ ] **Step 1: Update companion registry metadata**

In `[Registry]`, change the companion `RuiFile` and `PlugIn\FileName` values:

```iss
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: string; ValueName: "RuiFile"; ValueData: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rui"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B\PlugIn"; ValueType: string; ValueName: "FileName"; ValueData: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rhp"; Components: plugins
```

- [ ] **Step 2: Update post-install companion metadata verification**

In `VerifyRhinoPluginInstall`, set the companion `RuiFile` verification path to `net8.0`:

```iss
RuiFile := ExpandConstant('{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rui');
```

- [ ] **Step 3: Update direct companion RHP verification**

In `VerifyRhinoPluginInstall`, set `CompanionPath` to the `net8.0` child payload:

```iss
CompanionPath := ExpandConstant('{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rhp');
```

- [ ] **Step 4: Update the net8 missing-payload message**

Change the missing-net8 payload message so it identifies standalone Rhino as affected:

```iss
'Standalone Rhino and Rhino.Inside/Revit .NET 8 hosts will not be able to load the runtime-specific Rook payload. Rebuild the installer from all companion target frameworks and reinstall.',
```

- [ ] **Step 5: Verify the old standalone anchor is gone**

Run:

```powershell
rg -n 'ValueName: "(RuiFile|FileName)"; ValueData: "\{userappdata\}\\McNeel\\Rhinoceros\\8\.0\\Plug-ins\\RookNative\\net7\.0\\Rook\.(rui|rhp)"' installer\RookSetup.iss scripts\tests\release-installer-guards.tests.ps1
```

Expected: no matches.

---

### Task 3: Verification and PR

**Files:**
- Review: `installer/RookSetup.iss`
- Review: `scripts/tests/release-installer-guards.tests.ps1`

- [ ] **Step 1: Run installer guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: guard tests pass with exit code `0`.

- [ ] **Step 2: Run whitespace diff check**

Run:

```powershell
git diff --check main..HEAD
git diff --check
```

Expected: both commands produce no output and exit `0`.

- [ ] **Step 3: Confirm PR scope**

Run:

```powershell
git diff --stat main..HEAD
git status --short --branch
```

Expected committed PR scope after final commit:

```text
docs/superpowers/specs/2026-06-25-installer-net8-registration-anchor-design.md
docs/superpowers/plans/2026-06-25-installer-net8-registration-anchor.md
installer/RookSetup.iss
scripts/tests/release-installer-guards.tests.ps1
```

- [ ] **Step 4: Commit implementation**

Run:

```powershell
git add docs/superpowers/plans/2026-06-25-installer-net8-registration-anchor.md installer/RookSetup.iss scripts/tests/release-installer-guards.tests.ps1
git commit -m "fix(installer): register standalone companion with net8 payload"
```

- [ ] **Step 5: Push and open PR**

Run:

```powershell
$body = @'
## Summary
- register standalone Rhino companion metadata against the net8.0 managed payload
- keep net7.0 packaged as a fallback payload instead of the direct registration anchor
- update release installer guards to pin the net8 anchor and reject the old net7 anchor

## Verification
- powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
- git diff --check main..HEAD
- git diff --check
'@
$bodyPath = Join-Path $env:TEMP 'rook-installer-net8-registration-anchor-pr.md'
Set-Content -Path $bodyPath -Value $body -Encoding UTF8
git push -u origin codex/installer-net8-registration-anchor
gh pr create --title "Register standalone companion with net8 installer payload" --body-file $bodyPath
```

Expected: a focused review PR against `main`.
