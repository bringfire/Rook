# Dev Live Smoke Scriptability Design

Date: 2026-06-19

## Goal

Make the existing local deploy live smoke work with the same explicit dev runtime
contract used by normal local development.

Target command after a full deploy and Rhino restart:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning -UseRepoVenv -LiveSmoke
```

This is a post-restart live smoke. Rhino and Grasshopper must already be open,
RookNative must be loaded, and the previously deployed payload must be active.

## Problem

The current deploy script supports a bounded live smoke for release runtime mode,
but rejects `-LiveSmoke` when `-UseRepoVenv` or `-DevPythonRuntime` is selected.
That leaves the normal dev-runtime loop without a scriptable live proof, even
though full deploy and manual Rhino/GH smoke can pass.

The current `Test-LiveSmoke` also hardcodes release runtime state: it sets
release environment variables and runs the smoke with the installed AppData
Python. Dev runtime smoke should instead use the resolved deploy runtime
contract.

## Scope

Included:

- Allow `-PayloadOnly -AllowRunning -UseRepoVenv -LiveSmoke`.
- Allow `-PayloadOnly -AllowRunning -DevPythonRuntime <path> -LiveSmoke`.
- Make `Test-LiveSmoke` use the same `$RuntimeContract` resolved by deploy.
- Keep one Python smoke body and one `Test-LiveSmoke` function.
- Preserve release-runtime live smoke behavior.
- Add guard coverage for the new allowed dev-runtime combinations.
- Keep `-NativeOnly -LiveSmoke` rejected.
- Keep `-LiveSmoke` requiring `-PayloadOnly -AllowRunning`.

Excluded:

- No stale MCP process list or stop helper.
- No automatic process killing.
- No long-lived `python -m rook` process startup.
- No changes to OCCT fallback paths.
- No owned Rhino launch or release-readiness proof changes.

## Runtime Contract

`Resolve-DeployRuntimeContract` remains the single source of truth for runtime
selection. `Test-LiveSmoke` must receive the resolved contract:

```powershell
Test-LiveSmoke -Contract $RuntimeContract
```

The contract must expose an `Environment` object containing the complete
environment needed by the smoke subprocess. The smoke implementation must not
hardcode repo paths or installed paths when a contract field already exists.

Required contract-driven values:

- `PythonPath`: executable used for the smoke subprocess.
- `WorkingDirectory`: directory used while invoking the smoke subprocess.
- `PythonPathEntries`: source paths used to build `PYTHONPATH`.
- `Mode`: `dev` or `release`.
- `InstallRoot`: value for `ROOK_INSTALL_ROOT`.
- `DataRoot`: value for `ROOK_DATA_DIR`.
- `ProjectRoot`: value for `ROOK_PROJECT_ROOT`; empty for release.
- `Environment`: object or hashtable with the concrete subprocess environment
  values listed below.

Environment semantics:

- Dev mode uses the repo-backed values already produced by
  `Resolve-DeployRuntimeContract`.
- Release mode stays equivalent to current installed runtime behavior.
- `PYTHONPATH` is derived only from `$Contract.PythonPathEntries`.
- `CHIRP_HOME` remains the installed AppData Chirp root, matching current deploy
  behavior for both release and dev live smoke.
- `$Contract.Environment` contains `ROOK_MODE`, `ROOK_INSTALL_ROOT`,
  `ROOK_DATA_DIR`, `CHIRP_HOME`, and `PYTHONPATH`.
- `$Contract.Environment` contains `ROOK_PROJECT_ROOT` only when
  `$Contract.ProjectRoot` is non-empty. Release mode must leave
  `ROOK_PROJECT_ROOT` absent or remove it for the smoke subprocess, matching
  current release-runtime behavior.
- `Test-LiveSmoke` reads those values from `$Contract.Environment`.

## Live Smoke Flow

`Test-LiveSmoke` keeps the existing bounded Python smoke script. It calls the
same dispatch path directly and does not start a long-lived MCP server.

Required tool calls:

- `rhino_ping`
- `gh_status`
- deterministic `chirp_create`
- `gh_errors`
- `gh_undo`

The Chirp smoke remains deterministic-only and must not depend on external LLM
providers, API keys, model latency, or provider availability.

The smoke must reject:

- failed `rhino_ping`
- failed `gh_status`
- failed `chirp_create`
- `chirp_create` warnings or compilation errors
- Grasshopper errors on the created component
- failed `gh_undo`

## Restoration Discipline

`Test-LiveSmoke` must restore all PowerShell process state it changes, even when
a live call fails.

The implementation must use `try/finally` to restore:

- `ROOK_MODE`
- `ROOK_INSTALL_ROOT`
- `ROOK_DATA_DIR`
- `CHIRP_HOME`
- `ROOK_PROJECT_ROOT`, including restoring an originally absent state
- `PYTHONPATH`
- current working directory
- temporary smoke script file

Preferred location handling:

```powershell
Push-Location $Contract.WorkingDirectory
try {
    & $Contract.PythonPath $smokePath
} finally {
    Pop-Location
}
```

If the implementation uses a different working-directory mechanism, it must
still restore the original location in `finally`.

## Mode Rules

Allowed:

```powershell
-PayloadOnly -AllowRunning -LiveSmoke
-PayloadOnly -AllowRunning -UseRepoVenv -LiveSmoke
-PayloadOnly -AllowRunning -DevPythonRuntime <path> -LiveSmoke
```

Rejected:

```powershell
-NativeOnly -LiveSmoke
-LiveSmoke without -PayloadOnly -AllowRunning
-UseRepoVenv with -DevPythonRuntime
```

The old rejection that says live smoke cannot be combined with
`-UseRepoVenv` or `-DevPythonRuntime` must be removed.

## Testing

Update `scripts/tests/deploy-local-testing-guards.tests.ps1`.

Required guard assertions:

- The old dev-runtime live smoke rejection string is absent.
- `Test-LiveSmoke` accepts a contract parameter or otherwise consumes
  `$RuntimeContract` explicitly.
- `Test-LiveSmoke` invokes `$Contract.PythonPath`, not `$VenvPython`.
- `Test-LiveSmoke` derives `PYTHONPATH` from `$Contract.PythonPathEntries`.
- `Test-LiveSmoke` contains `try`/`finally` restoration for environment and
  location changes.
- `-PayloadOnly -AllowRunning -UseRepoVenv -LiveSmoke` is documented or
  represented as an allowed script contract.
- `-PayloadOnly -AllowRunning -DevPythonRuntime <path> -LiveSmoke` is documented
  or represented as an allowed script contract.
- Release live smoke remains documented through
  `-PayloadOnly -AllowRunning -LiveSmoke`.
- `-NativeOnly -LiveSmoke` remains rejected.
- `-LiveSmoke` still requires `-PayloadOnly -AllowRunning`.

Verification commands for the implementation PR:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\issue112-net48-companion-guards.tests.ps1
git diff --check
```

Manual/live verification after a full deploy and Rhino restart:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning -UseRepoVenv -LiveSmoke
```

Only claim live Rhino/GH/Chirp proof when that command passes against an open
Rhino/GH session with Rook loaded.
