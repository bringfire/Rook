# Local Testing Live Proof Design

Date: 2026-05-17

## Goal

Build a robust live-test system that proves Rook local development is testing the installed product path that users exercise, while also proving that the local deploy workflow does not weaken or interfere with the release installer path.

The test system must cover Rook MCP, RookNative, the managed companion, Grasshopper, Chirp, chat panel configuration, local AppData runtime deployment, and release installer defaults.

Core invariant:

```text
Local tests may be fast.
Release-readiness tests must be installed-path, owned-process, and fail-closed.
No test may silently fall back to repo source.
```

## Problem

Rook development often happens from git worktrees, while the Rhino plugin and MCP runtime are installed under AppData. A test can accidentally pass by importing source from the active repo or worktree while the installed runtime, MCP config, chat service manifest, or Chirp checkout remains stale. That creates false confidence.

The new local deploy workflow reduces that risk by syncing source into `%LOCALAPPDATA%/Rook/app`, refreshing editable installs, verifying AppData imports, verifying MCP configs, verifying the chat service manifest, and optionally running a live Rhino/GH/Chirp smoke.

That is necessary but not sufficient as the permanent proof system. The proof system must separate:

- fast developer feedback against an already-open Rhino session;
- installed-runtime verification that does not depend on Rhino;
- owned-process release-readiness proof against a clean Rhino startup;
- release non-interference checks that protect installer behavior.

## Required Test Layers

### 1. Static Guard Gate

Always run. No Rhino required.

Purpose:

- Detect deploy-script drift.
- Detect release-installer drift.
- Detect local-only skip flags leaking into release.
- Detect stale path assumptions.
- Detect missing Chirp packaging or install behavior.
- Protect post-install defaults.

Existing inputs:

- `scripts/tests/deploy-local-testing-guards.tests.ps1`
- `scripts/tests/release-installer-guards.tests.ps1`
- PowerShell parse checks for deploy and guard scripts.
- `python -m py_compile installer/post_install.py`
- `git diff --check`

Required assertions:

- `scripts/deploy-local-testing.ps1` uses explicit MSVC toolset selection for native builds.
- Local deploy syncs Rook MCP/runtime payload into `%LOCALAPPDATA%/Rook/app`.
- Local deploy syncs bundled seed knowledge only to `%LOCALAPPDATA%/Rook/app/knowledge`, not mutable `%LOCALAPPDATA%/Rook/data`.
- Local deploy preserves `.env`, runtime data, logs, local generated artifacts, and virtual environments unless explicitly refreshed by intended install logic.
- Local deploy syncs sibling Chirp source into `%LOCALAPPDATA%/Rook/app/chirp`.
- Local deploy refreshes Chirp install by default.
- Local deploy verifies installed `rook` import origin under `%LOCALAPPDATA%/Rook/app/mcp_server/src/rook`.
- Local deploy verifies installed `chirp` import origin under `%LOCALAPPDATA%/Rook/app/chirp`.
- Local deploy structurally parses MCP configs and verifies `command`, `args`, `cwd`, `ROOK_INSTALL_ROOT`, `ROOK_DATA_DIR`, `ROOK_MODE`, and `CHIRP_HOME` point to AppData runtime paths.
- Local deploy verifies the Rhino chat service manifest points to the AppData Rook venv and AppData MCP server.
- Release installer packages Chirp from the sibling release source.
- Release installer packages bundled knowledge as app seed content.
- Release installer invokes `post_install.py` without local-only skip flags.
- `post_install.py` defaults still install/refresh MCP and Chirp behavior unless explicit local deploy flags disable them.

Stable failure labels:

- `deploy_guard_failed`
- `release_guard_failed`
- `powershell_parse_failed`
- `post_install_compile_failed`
- `diff_check_failed`
- `release_skip_flag_leakage`
- `chirp_release_packaging_missing`
- `knowledge_sync_policy_violation`

This gate may say "static guard passed." It must not claim live capability.

### 2. Installed Runtime Gate

Runs after `scripts/deploy-local-testing.ps1`. No live Rhino required.

Purpose:

- Prove the deployed AppData runtime is the runtime that will be used.
- Prove configs point to AppData, not a repo or worktree.
- Prove Chirp and chat panel configuration are installed-path correct.

Canonical command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1
```

Fast payload-only command after code-only changes that do not require native/managed rebuild:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -SkipBuild
```

Required runtime authority:

- Use `%LOCALAPPDATA%/Rook/venv/Scripts/python.exe`.
- Import `rook` using the installed venv.
- Assert `rook.__file__` starts under `%LOCALAPPDATA%/Rook/app/mcp_server/src/rook`.
- Resolve runtime paths through installed `rook.runtime_paths.resolve_runtime_paths()`.
- Assert `ROOK_INSTALL_ROOT == %LOCALAPPDATA%/Rook/app`.
- Assert `ROOK_DATA_DIR == %LOCALAPPDATA%/Rook/data`.
- Import `chirp` using the installed Chirp venv or the installed Chirp environment established by post-install.
- Assert Chirp import origin starts under `%LOCALAPPDATA%/Rook/app/chirp`.
- Parse MCP client configs structurally and assert all Rook MCP entries use AppData command/cwd/env values.
- Parse `RookChatService.json` and assert it uses the AppData venv Python, AppData MCP server path, and expected chat service module.
- Reject any runtime path containing a deleted worktree, current repo source path, or other non-AppData source root.

Stable failure labels:

- `rook_import_failed`
- `rook_import_leakage`
- `runtime_path_mismatch`
- `chirp_import_failed`
- `chirp_import_leakage`
- `mcp_config_missing`
- `mcp_config_stale`
- `mcp_config_repo_leakage`
- `chat_manifest_missing`
- `chat_manifest_stale`
- `worktree_path_leakage`

This gate may say "installed runtime verified." It must not claim live Rhino/GH/Chirp capability.

### 3. Developer-Open Live Smoke Gate

Fast loop against an already-open Rhino/GH session.

Purpose:

- Give developers quick confidence that the installed runtime can communicate with the currently active Rhino/GH environment.
- Validate the local deploy path during normal iterative development.

Canonical command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning -LiveSmoke
```

Preconditions:

- Rhino is already open.
- RookNative is loaded.
- Grasshopper is available.
- This mode is explicitly allowed to run while Rhino is running because it is an interactive developer smoke.

Required live checks:

- Run installed-runtime verification before live calls.
- Call `rhino_ping`.
- Call `gh_status`.
- Call deterministic `chirp_create`.
- Do not call external LLM providers.
- Reject `chirp_create` responses that include warnings or compilation errors, even if `success: true`.
- Verify `gh_errors` is clean for the created Chirp component.
- Run `gh_undo`.
- Fail if `gh_undo` does not report success.

No external LLM dependency:

The Chirp smoke must exercise deterministic component creation and Grasshopper compilation. It must not depend on API keys, model availability, model latency, or provider behavior.

Stable failure labels:

- `rhino_ping_failed`
- `gh_not_ready`
- `chirp_create_failed`
- `chirp_component_warning`
- `chirp_component_compile_error`
- `gh_component_error`
- `cleanup_failed`

This gate may say "developer-open live smoke passed." It must not claim release readiness because it did not prove clean startup or process ownership.

### 4. Owned Rhino Release-Readiness Gate

Slower, explicit, non-default. This is the only gate allowed to claim full installed capability has been proven.

Purpose:

- Prove Rook works from a clean user-like Rhino startup.
- Prove calls are routed to the launched Rhino process, not some ambient Rhino.
- Prove the installed AppData runtime, installed plugin, Grasshopper, Chirp, and chat config work together.

Canonical future command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate-local-testing-stack.ps1 -ReleaseReadiness
```

Equivalent implementation may be a Python harness command, but the public entry point should remain a stable script command.

Ownership policy:

- Release-readiness mode is allowed to launch Rhino automatically.
- Release-readiness mode must only manage the Rhino process it launched.
- If Rhino is already running, release-readiness mode fails closed with `rhino_already_running`.
- It must not attach to, reuse, or close a developer's existing Rhino session.
- It launches one clean Rhino process.
- It records the launched PID.
- It discovers the launched process's Rook port.
- It binds every live call to the launched PID and discovered port.
- It closes only the owned Rhino process.
- It attempts cleanup by default.
- It may support an explicit diagnostic option such as `-KeepRhinoOnFailure`.

PID and port authority:

Owned means PID-bound and port-bound. The harness must prove every Rhino call is routed to the launched Rhino process, not just "some Rhino responded."

Required recorded metadata:

- launched Rhino PID;
- Rhino executable path;
- command line;
- discovered Rook host and port;
- active target metadata;
- `rhino_ping` target metadata if available;
- AppData Rook install root;
- AppData Rook data root;
- AppData Chirp home;
- MCP config paths checked;
- chat manifest path checked;
- artifact directory;
- cleanup result.

Required sequence:

1. Run static guard gate.
2. Run release non-interference gate.
3. Run a fresh local deploy from the current commit.
4. Refuse if any Rhino process is already running.
5. Launch Rhino.
6. Wait for owned Rook discovery tied to the launched PID.
7. Verify discovered port belongs to the launched PID.
8. Run installed-runtime verification from AppData venv.
9. Bind MCP/live calls to the owned PID and port.
10. Call `rhino_ping` and verify target metadata matches the owned PID/port when metadata is available.
11. Call `gh_status`.
12. Call deterministic `chirp_create`.
13. Reject Chirp warnings, compilation errors, and GH component errors.
14. Run `gh_undo` and require success.
15. Capture artifacts.
16. Close only the owned Rhino process.
17. Verify cleanup.

Cleanup policy:

- Default release-readiness attempts cleanup.
- Default release-readiness should not leave Rhino processes around.
- `-KeepRhinoOnFailure` may preserve the owned process for diagnostics only when explicitly requested.
- Cleanup failure makes the gate fail even if live smoke passed.
- The harness must never close a Rhino process it did not launch.

Stable failure labels:

- `static_guard_failed`
- `release_non_interference_failed`
- `local_deploy_failed`
- `installed_runtime_failed`
- `rhino_already_running`
- `rhino_launch_failed`
- `owned_discovery_timeout`
- `owned_discovery_malformed`
- `owned_pid_mismatch`
- `owned_port_mismatch`
- `target_binding_failed`
- `rook_import_leakage`
- `mcp_config_stale`
- `chat_manifest_stale`
- `rhino_ping_failed`
- `gh_not_ready`
- `chirp_import_failed`
- `chirp_create_failed`
- `chirp_component_warning`
- `chirp_component_compile_error`
- `gh_component_error`
- `cleanup_failed`

This gate may claim "release-readiness proven" only when all required sequence steps pass and cleanup is green.

Fresh deploy is the default contract. Reusing a prior installed-runtime artifact is not part of the release-readiness v1 path. A future diagnostic mode may allow reuse only if it validates git commit, dirty-tree status, deploy timestamp, installed runtime metadata, and artifact integrity before any live call.

### 5. Release Non-Interference Gate

Separate from local deploy and live Rhino behavior.

Purpose:

- Prove the release installer path still behaves like the release installer.
- Prove local deploy shortcuts remain opt-in and cannot silently affect release behavior.

Required assertions:

- `installer/RookSetup.iss` packages release payloads from intended release locations.
- Chirp release payload comes from the sibling source used by the installer.
- Bundled knowledge is packaged into the app install location as seed content.
- Release invocation of `post_install.py` does not pass local-only flags such as `--skip-chirp-install` or `--skip-validation`.
- `post_install.py` default behavior still installs/refreshes MCP and Chirp unless explicit flags disable those behaviors.
- Local deploy flags remain local deploy flags; they are not used by release installer invocations.
- Release build skill and release scripts continue to point at release build commands, not local deploy shortcuts.

Stable failure labels:

- `release_packaging_drift`
- `release_skip_flag_leakage`
- `post_install_default_drift`
- `chirp_release_packaging_missing`
- `knowledge_release_packaging_missing`
- `release_skill_drift`

This gate may say "release non-interference verified." It must not claim installed live capability.

## Existing Suite Classification

Existing live suites should be classified rather than merged into one ambiguous proof path.

### Repo-Source Developer Suites

These are valuable for development but cannot claim installed-runtime release readiness if they import repo source directly:

- `scripts/validate_rhino_operational_suite.py`
- `scripts/validate_gh_operational_suite.py`
- repo-source pytest live tests that run from `mcp_server/src`

Allowed claims:

- Rhino route behavior passed against the selected development source.
- Grasshopper route behavior passed against the selected development source.

Disallowed claims:

- installed AppData runtime verified;
- local deploy verified;
- release-readiness proven.

### Installed-Runtime Suites

Release-readiness proof must have its own installed-runtime suite or installed-runtime mode.

Requirements:

- Run with `%LOCALAPPDATA%/Rook/venv/Scripts/python.exe`.
- Assert `rook.__file__` is under `%LOCALAPPDATA%/Rook/app/mcp_server/src/rook`.
- Assert `chirp` import origin is under `%LOCALAPPDATA%/Rook/app/chirp`.
- Use AppData runtime paths.
- Bind live calls to explicit target PID and port in owned mode.
- Refuse repo/worktree imports.

Candidate implementation options:

- Add `--installed-runtime` mode to existing operational suites.
- Add a new small installed-runtime live suite dedicated to release-readiness.
- Keep broad repo-source operational suites separate and use them as optional additional developer coverage.

The release-readiness gate should start with a narrow installed-runtime smoke. Broad operational coverage can be layered on later once target binding and installed import authority are proven.

## Artifacts

Each release-readiness run should create an artifact directory under a deterministic local path such as:

```text
artifacts/local-testing/<timestamp>-release-readiness/
```

Required files:

- `manifest.json`
- `stdout.log`
- `stderr.log`
- `static-guards.log`
- `installed-runtime.json`
- `owned-rhino.json`
- `live-smoke.json`
- `cleanup.json`

Every gate result written into `manifest.json` must use a machine-verifiable envelope:

```json
{
  "gate": "installed_runtime",
  "success": false,
  "failure_label": "rook_import_leakage",
  "command": "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\deploy-local-testing.ps1",
  "duration_seconds": 12.34,
  "stdout_path": "stdout.log",
  "stderr_path": "stderr.log",
  "details": {},
  "cleanup": {
    "attempted": false,
    "success": null,
    "label": null,
    "details": {}
  }
}
```

Envelope fields:

- `gate`: stable gate id.
- `success`: boolean pass/fail.
- `failure_label`: stable label on failure, `null` on success.
- `command`: exact command or tool invocation used for the gate.
- `duration_seconds`: elapsed time.
- `stdout_path`: relative path to captured stdout when applicable.
- `stderr_path`: relative path to captured stderr when applicable.
- `details`: structured gate-specific evidence.
- `cleanup`: structured cleanup outcome for gates that create state or launch processes.

`manifest.json` should include:

- source repo path;
- git commit;
- git branch;
- dirty tree status;
- deploy command;
- installed AppData paths;
- launched Rhino PID;
- discovered port;
- active target;
- gate results;
- stable failure label if failed;
- cleanup result;
- whether `-KeepRhinoOnFailure` was used.

## Command Contract

The public testing commands should be small in number and unambiguous.

### Static Guards

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

### Local Deploy And Installed Runtime

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1
```

### Fast Developer Live Smoke

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning -LiveSmoke
```

### Release-Readiness Proof

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate-local-testing-stack.ps1 -ReleaseReadiness
```

Expected behavior:

- Runs static guards.
- Runs release non-interference checks.
- Performs a fresh local deploy from the current commit.
- Fails if Rhino is already running.
- Launches owned Rhino.
- Runs installed-runtime verification.
- Runs owned live smoke.
- Cleans up owned Rhino.
- Writes artifacts.
- Exits nonzero on any required gate failure.

Diagnostic option:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate-local-testing-stack.ps1 -ReleaseReadiness -KeepRhinoOnFailure
```

This option is only for debugging. It does not relax pass/fail criteria.

## Pass/Fail Language

Use precise claims:

- Static guard passed.
- Installed runtime verified.
- Developer-open live smoke passed.
- Release non-interference verified.
- Release-readiness proven.

Only the owned Rhino release-readiness gate may emit:

```text
release-readiness proven
```

Any other gate must use narrower wording.

## Implementation Notes

The implementation should reuse existing deploy and runtime harness pieces where possible:

- `scripts/deploy-local-testing.ps1` remains the authoritative local deploy script.
- `.agents/skills/deploy-local-testing/SKILL.md` remains thin and points to the script.
- `installer/post_install.py` remains the shared post-install config writer.
- `mcp_server/src/rook/runtime_harness.py` is the natural owned-process foundation.
- `scripts/run_rhino_runtime_harness.py` must not be used as-is for release-readiness because it currently prepends repo MCP source to `sys.path`. Release-readiness must either add an installed-runtime mode that skips repo-source path injection or use a new wrapper launched by `%LOCALAPPDATA%/Rook/venv/Scripts/python.exe`.
- Existing repo-source operational suites remain useful but must not be repurposed as installed-runtime proof without explicit installed-runtime mode.

The implementation should not duplicate config-writing logic in the test harness. It should call the deploy/post-install paths and then verify their effective output.

## Non-Goals

- No CI requirement for full owned Rhino release-readiness in v1.
- No external LLM calls in smoke gates.
- No broad Rhino/GH operational marathon in the first release-readiness gate.
- No automatic closing of developer-owned Rhino processes.
- No mutation of runtime data or local secrets during verification.
- No hidden fallback to repo Python.

## Open Implementation Decisions

- Whether `validate-local-testing-stack.ps1` should be a thin orchestrator over Python harness code or contain most orchestration directly.
- Whether existing `validate_rhino_operational_suite.py` and `validate_gh_operational_suite.py` should get `--installed-runtime` modes or remain repo-source only.
- Whether a future diagnostic-only mode should allow reuse of a prior installed-runtime artifact after strict commit, dirty-tree, timestamp, and metadata validation.
- Exact artifact retention policy.
