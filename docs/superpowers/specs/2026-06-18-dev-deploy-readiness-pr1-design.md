# Dev Deploy Readiness PR 1 Design

## Purpose

Make current `main` diagnosable and deployable on a prepared Windows development
machine without changing native project fallback behavior. This PR is operational,
not architectural: it adds a read-only doctor, fixes known local deploy gaps, and
documents the current laptop/desktop convention.

Success condition:

- A clean machine can tell what is missing.
- A prepared machine can deploy current `main` into Rhino with the dev chat runtime
  and required OCCT runtime DLLs.

## Scope

Included:

- Add `scripts/rook-dev-doctor.ps1`.
- Copy the required OCCT runtime DLL closure during local native payload deploy.
- Register the full local deploy companion at `net8.0\Rook.rhp`.
- Prefer `net8.0` in `scripts/register-rooknative-suite.ps1` fallback discovery.
- Allow `scripts/register-companion.ps1` to validate `net8.0` companion paths
  and runtime metadata while preserving `net7.0` support and `net48` rejection.
- Update `AGENT_SETUP.md` with the current solo-dev machine convention.
- Add lightweight PowerShell guard tests for the script structure.

Excluded:

- No `.vcxproj` or `.vcxproj.filters` edits.
- No neutralization of the hardcoded OCCT fallback paths.
- No new dependency manager, package cache, or CI platform.
- No installer or release pipeline changes in PR 1. Guard updates should cover only
  local deploy and doctor behavior.

## Doctor Script

`scripts/rook-dev-doctor.ps1` is read-only by default. It reports `PASS`, `WARN`,
and `FAIL` lines plus a short summary. It should not stop processes, write
environment variables, register plugins, install packages, create venvs, or edit
files.

The default mode exits nonzero only for core dev-deploy blockers. Add a simple
`-Strict` switch that escalates warnings to a failing exit for pre-deploy hygiene.

Default core blockers:

- Git is unavailable or the repo cannot be inspected.
- Required local deploy paths are missing:
  - repo root and `scripts`
  - `scripts\deploy-local-testing.ps1`
  - `mcp_server`
  - `mcp_server\.venv\Scripts\python.exe`
  - `src\RookNative`
  - `src\Rook`
  - `src\RookBim`
- `OCCT_ROOT` is missing or points to a root without required headers, libs, or
  runtime DLLs, unless the script can explicitly report that the current project
  fallback would be used.
- Repo MCP venv is missing or cannot `import rook`.
- Required Revit API assemblies for full deploy are missing.

Warnings by default, failures under `-Strict`:

- Rhino is running.
- `python -m rook` is running.
- Inno Setup is missing.
- Sibling `../Chirp` is missing or incomplete.
- Git worktree has local changes.
- Local branch is ahead or behind its upstream.
- Installed chat manifest is absent or is in an unexpected mode.

The doctor must explicitly state whether `OCCT_ROOT` is being used or whether the
native project would rely on its hardcoded fallback. This does not remove or modify
the fallback; it only makes the state visible.

## OCCT Runtime Deploy

`scripts/deploy-local-testing.ps1` gets an explicit `$OcctRuntimeDlls` list. Do not
parse `.vcxproj` files in this PR. The list should match the documented runtime
closure rather than attempting dynamic dependency discovery.

OCCT root resolution in local deploy should follow the same PR 1 rule as the
doctor: use the `OCCT_ROOT` environment variable first, then the existing hardcoded
fallback path. The deploy output should report which source was used. Do not parse
the project files to discover this path in PR 1.

Use the measured runtime closure from `docs/rook_docs/occt-build.md`:

- `TKernel.dll`
- `TKMath.dll`
- `TKG2d.dll`
- `TKG3d.dll`
- `TKGeomBase.dll`
- `TKGeomAlgo.dll`
- `TKBRep.dll`
- `TKTopAlgo.dll`
- `TKPrim.dll`
- `TKBO.dll`
- `TKShHealing.dll`

`TKBool.dll` and `TKMesh.dll` are linked but documented as not loaded in the measured
closure. Do not add them in PR 1 unless implementation verification proves the
documented closure is stale; if that happens, call out the choice as intentionally
less trimmed.

The copy source should be the resolved OCCT root's `win64\vc14\bin` directory.
The target is the Rhino plugin folder next to `RookNative.rhp`, because Rhino loads
the OCCT DLLs from the plugin directory. Missing DLLs should fail the deploy with a
clear message.

## Companion Registration

Full deploy must call `scripts/register-rooknative-suite.ps1` with:

```powershell
-CompanionRhpPath (Join-Path $PluginDir 'net8.0\Rook.rhp')
```

Native-only preserve-companion behavior remains unchanged.

`scripts/register-rooknative-suite.ps1` should also prefer fallback discovery in
this order when called without `-CompanionRhpPath`:

1. `net8.0\Rook.rhp`
2. `net7.0\Rook.rhp`
3. root-level `Rook.rhp`

This makes ad hoc registration match the full deploy direction without removing
legacy fallback support.

`scripts/register-companion.ps1` must also accept `net8.0` as a supported managed
companion runtime. Otherwise the full deploy and suite fallback changes select
`net8.0\Rook.rhp` only to be rejected by the final companion registration gate.
The script should continue to accept `net7.0` and reject `net48`.

## AGENT_SETUP Update

Add a short developer-machine convention section. Keep it procedural and concise:

1. Pull current `main`.
2. Run `scripts\rook-dev-doctor.ps1`.
3. Close Rhino and any `python -m rook` processes.
4. Deploy with:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -UseRepoVenv
   ```

5. Restart Rhino.
6. Optionally run the existing payload-only live smoke flow.

The doc should state that `OCCT_ROOT` is expected on prepared dev machines and that
removing the hardcoded project fallback is a follow-up PR after laptop and desktop
both pass doctor from a fresh shell.

## Guard Tests

Use the existing lightweight PowerShell guard-test style in
`scripts/tests/deploy-local-testing-guards.tests.ps1`.

Add guards that assert:

- `scripts/rook-dev-doctor.ps1` exists.
- The doctor exposes `-Strict`.
- The doctor reports `OCCT_ROOT` versus fallback use.
- The deploy script has an explicit `$OcctRuntimeDlls` list.
- The deploy script copies OCCT DLLs during native payload deploy.
- The known OCCT runtime DLL names appear in the deploy script.
- Full deploy registers `net8.0\Rook.rhp`.
- Native-only preserve-companion registration still exists.
- `register-rooknative-suite.ps1` fallback order prefers `net8.0` before `net7.0`.
- `register-companion.ps1` accepts `net8.0` and `net7.0` runtime metadata while
  still rejecting `net48`.

Do not try to enforce "no `.vcxproj` changes" through a source-content guard. Treat
that as PR review criteria or a separate changed-files check if needed later.

## Verification

Implementation verification:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\rook-dev-doctor.ps1
```

Implementation verification should also include the normal dev deploy command on a
prepared machine:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -UseRepoVenv
```

Do not claim native build or live Rhino verification unless those commands actually
run successfully on a machine with Rhino, MSVC/MFC, OCCT, Revit API assemblies, and
the repo venv available.

## Follow-Up PR

After both laptop and desktop pass doctor from a fresh shell with `OCCT_ROOT`
resolved to the intended OCCT install, PR 2 can neutralize the hardcoded OCCT
fallbacks in the native project files and update the OCCT setup docs.
