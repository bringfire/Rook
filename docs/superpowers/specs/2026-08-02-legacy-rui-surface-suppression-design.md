# Legacy RUI Surface Suppression Design

**Date:** 2026-08-02

**Status:** Proposed

**Decision:** Stop loading, building, deploying, registering, and documenting the legacy `Rook.rui` toolbar. Remove only its known installed files and registry value. Retain the dormant source asset and unrelated UI functionality.

## Goal

Make the legacy Rook toolbar invisible to users after a supported build, local deployment, install, upgrade, or repair.

This is surface suppression and exact migration cleanup, not a toolbar-system rewrite or a purge of every historical RUI reference.

## KISS boundary

The correction is deliberately small:

1. Rook stops programmatically loading `Rook.rui`.
2. Supported builds and deployment paths stop copying it.
3. Those deployment paths remove only the exact obsolete runtime-child file.
4. The installer removes the three exact installed files and the exact `RuiFile` registry value.
5. Active build and release guidance stops requiring the artifact.

No generalized UI-lifecycle framework, wildcard cleanup, Rhino settings crawler, version branch, live toolbar manipulation, native change, or new installer helper is introduced.

## Preserved behavior and artifacts

The following remain unchanged:

- `src/Rook/UI/Rook.rui` stays tracked as a dormant source artifact.
- Rook's Eto panels, panel commands, chat, knowledge graph, vision UI, and companion startup remain supported.
- Native commands and command discovery remain supported.
- Grasshopper and RookBIM behavior remain outside this change.
- Historical specifications, plans, reports, and release evidence remain intact.
- Rhino's unrelated `ExportRuiFile` command knowledge remains intact.
- The historical native comment referring to the old toolbar is not an active loading or packaging surface and does not justify native code work.

## Runtime suppression

`src/Rook/RookPlugin.cs` will remove:

- `_toolbarLoaded`;
- the deferred-startup call to `EnsureToolbarLoaded()`;
- `EnsureToolbarLoaded()`; and
- `LoadToolbar()`.

No replacement loader or feature flag is added. Startup proceeds through the existing companion, bridge, and panel paths without attempting to locate or open an RUI file.

A focused managed source contract will prove that `RookPlugin.cs` contains none of the retired loader field, methods, call, or `Rook.rui` path while preserving the existing panel/startup assertions.

## Build and source/local deployment

All three supported source/local deployment paths participate in the cutover.

### MSBuild auto-deploy

`src/Rook/Rook.csproj` will:

- remove the `UI\Rook.rui` output item;
- remove the `Rook.rui` copy from `DeployToRhino`; and
- exact-delete `$(RhinoManagedRuntimeDir)\$(TargetName).rui` when that existing Release auto-deploy target runs.

The delete is limited to the target framework's existing runtime child. It does not enumerate or delete sibling files.

### Local testing deployment

`scripts/deploy-local-testing.ps1` will:

- stop copying `Rook.rui` from each companion build output;
- exact-delete `Rook.rui` from each deployed `net8.0`, `net7.0`, and `net48` runtime child; and
- retain the existing exact stale-root cleanup.

### Bootstrap/source installer

`install.ps1` will make the equivalent change:

- stop copying `Rook.rui`; and
- exact-delete it from each target runtime child during companion deployment.

Cleanup is idempotent: a missing exact file succeeds without changing the deployment result. Neither PowerShell path gains a reusable migration framework, glob, directory deletion, or alternate cleanup root.

### Source/local companion registration

The full `deploy-local-testing.ps1` and `install.ps1` registration flows ultimately invoke the existing registry owner, `scripts/register-companion.ps1`. That script will:

- remove only the `RuiFile` property from the exact companion key, idempotently;
- perform the removal inline with its existing companion registration writes, without adding a helper or migration framework;
- verify that the `RuiFile` property is absent alongside its existing registration checks; and
- leave every other companion registration value unchanged.

The `-Unregister` path already removes the entire companion key and needs no additional RUI handling. MSBuild auto-deploy remains file-only because it does not own companion registration.

## Supported installer migration

`installer/RookSetup.iss` owns the installed-product migration.

### Files

Remove the three `Rook.rui` entries from `[Files]`.

Add these exact entries to the existing `[InstallDelete]` section before `[Files]`:

```ini
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rui"
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0\Rook.rui"
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48\Rook.rui"
```

The entries are unconditional: they have no `Components` condition. Clean install, upgrade, and repair therefore converge even when the plugin component is deselected. Inno Setup processes `[InstallDelete]` before installation, and exact `Type: files` entries avoid directory traversal or sibling deletion ([official documentation](https://jrsoftware.org/ishelp/topic_installdeletesection.htm)).

### Registry

Replace the companion's current `RuiFile` registration with one unconditional deletion entry:

```ini
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: none; ValueName: "RuiFile"; Flags: deletevalue dontcreatekey
```

It has no `ValueData` and no `Components` condition. `ValueType: none` with `deletevalue dontcreatekey` deletes the exact value without recreating an empty value or creating a missing key ([official documentation](https://jrsoftware.org/ishelp/topic_registrysection.htm)). Other companion registration values remain unchanged.

`VerifyPluginRegistration` will:

- remove its obsolete `RuiFile` variable and expected path;
- require `RegValueExists(HKCU, BaseKey, 'RuiFile')` to be false for the companion; and
- retain all existing plugin-file, metadata, command, and DWORD verification.

The supported installer already blocks installation while Rhino, Rhino.Inside.Revit, or Revit is running. This change adds no live unload or toolbar manipulation. Upgrade and repair acceptance therefore starts host-closed and evaluates the next host launch.

## Active guidance and release contracts

Remove obsolete RUI copy and required-artifact instructions from:

- `BUILDING.md`;
- `.agents/skills/build-release/references/iss-source-paths.md`; and
- `.claude/skills/build-release/references/iss-source-paths.md`.

Where `BUILDING.md` shows manual deployment, it will remove the exact runtime-child `Rook.rui` files instead of copying them.

The mirrored build-release references must remain byte-equivalent after editing. Their source-path tables and verification script will no longer require any `Rook.rui` build output.

## Focused automated contracts

Tests will cover only active surfaces:

- `RookPlugin.cs` has no toolbar-loader state, call, method, or RUI path.
- `Rook.csproj` neither emits nor copies the RUI and exact-deletes the deployed runtime-child file.
- `deploy-local-testing.ps1` and `install.ps1` do not copy the RUI and exact-delete it independently in each runtime child.
- `register-companion.ps1` exact-removes only the companion `RuiFile` property and fails verification if that property remains.
- `[Files]` has no RUI source entry.
- `[InstallDelete]` has exactly the three unconditional exact-file entries before `[Files]`.
- `[Registry]` contains the exact unconditional `ValueType: none` deletion contract and no `RuiFile` value data.
- installer verification requires the companion `RuiFile` value to be absent.
- active build/release instructions do not require or copy RUI build outputs.
- the dormant source file remains tracked.
- panel registration and supported UI command contracts remain intact.

There is no repository-wide ban on the strings `Rook.rui`, `RuiFile`, or `RUI`. Such a ban would conflict with the retained dormant source, exact migration code, tests, and historical evidence.

## Acceptance

Implementation is accepted only after:

1. Focused managed and PowerShell guard suites pass.
2. A clean Release companion build produces no `Rook.rui` in any managed output.
3. MSBuild auto-deploy, `deploy-local-testing.ps1`, and `install.ps1` each leave no `Rook.rui` in the three runtime children while preserving sibling payloads; the two full source/local registration flows also leave the companion `RuiFile` value absent.
4. The installer builds successfully.
5. Host-closed clean install, upgrade, and repair runs leave all three files absent and the companion `RuiFile` registry value absent; cleanup also holds with the plugin component deselected.
6. After restart in standalone Rhino, no Rook toolbar, missing-RUI prompt, or toolbar-load warning appears. Preserved panel commands remain registered and invocable to their existing boundary, with no regression from the implementation branch's pinned base.
7. After restart in the admitted Rhino.Inside.Revit host, no Rook toolbar or missing-RUI warning appears. Companion/RookBIM startup and preserved command registration/invocation show no regression from that same base.

If Rhino retains an undiscovered toolbar reference after exact file and registry cleanup, acceptance stops and records that host behavior. This specification does not pre-authorize a broader Rhino-settings migration.

Pre-existing panel behavior belongs to the separate RS-02 workstream. This change may record such behavior but may not repair, refactor, or expand it to satisfy acceptance.

## Expected implementation scope

The production/documentation cutover is limited to:

- `src/Rook/RookPlugin.cs`
- `src/Rook/Rook.csproj`
- `scripts/deploy-local-testing.ps1`
- `scripts/register-companion.ps1`
- `install.ps1`
- `installer/RookSetup.iss`
- `BUILDING.md`
- `.agents/skills/build-release/references/iss-source-paths.md`
- `.claude/skills/build-release/references/iss-source-paths.md`

Focused managed and PowerShell guard files may change to enforce this contract. No native C++, Python MCP, RookBIM, toolbar-source, panel implementation, or historical-document change belongs in the implementation PR.
