# Rhino Runtime Harness Design

Date: 2026-05-08

## Summary

Build the first slice of a process-owning Rhino runtime harness for Rook live smoke and development validation. This slice is strictly non-invasive: it does not add a native shutdown route, test-control route, or Rhino SDK lifecycle seam. The harness owns one Rhino process, proves that exact process loaded RookNative, runs a tiny selected live smoke through existing validation surfaces, captures useful artifacts, and cleans up only the process it started.

The central invariant is that the harness must never treat "some Rhino answered `/ping`" as readiness. Every readiness, test-routing, and cleanup decision is tied to the `Popen.pid` of the Rhino process launched by the harness.

## Existing Context

Rook already has a live Rhino test foundation:

- `BUILDING.md` documents `pytest -m requires_rhino`.
- `mcp_server/tests/conftest.py` provides a `fresh_document` fixture for live pytest tests.
- `mcp_server/tests/*_live.py` contains many existing `requires_rhino` live tests.
- `scripts/validate_rhino_operational_suite.py`, `scripts/validate_gh_runtime.py`, and `scripts/validate_gh_operational_suite.py` provide scriptable live validation once Rhino is running.
- `install.ps1` and `scripts/register-rooknative-suite.ps1` already know how to deploy and register RookNative plus the managed companion.
- RookNative writes `%TEMP%\rook\instance-{PID}-native.json` with `processId`, OS-assigned `port`, `pluginType`, and readiness capabilities.
- `bridge.py` already supports scoped routing by `port` and `process_id` through its request-context path.

The missing foundation is not another live-test universe. The missing piece is a runner that owns Rhino's process lifecycle and pins existing live-test execution to that owned runtime.

## Goals

- Start a specific Rhino 8 executable and record the owned PID.
- Wait only for `%TEMP%\rook\instance-{pid}-native.json` for that owned PID.
- Validate the discovery JSON before trusting it.
- Prove readiness with `/ping` on the exact discovered host/port.
- Recheck that discovery still reports the same PID and port before smoke execution.
- Scope pytest live tests by both owned port and owned PID.
- Reuse selected existing live tests and validation scripts.
- Capture `%TEMP%\rook` logs and run metadata before shutdown, including a snapshot of the owned discovery JSON.
- Request an external graceful close of only the owned Rhino process.
- Force-kill only the owned PID if graceful close times out, and mark the run non-green.
- Produce a manifest that records readiness, smoke, artifact, and cleanup outcomes.

## Non-Goals

- No native shutdown, lifecycle-control, or test-control HTTP route in v1.
- No `RookPlugin.OnLoad` / `OnShutdown` failure injection in v1.
- No changes to `.vcxproj` or `.vcxproj.filters`.
- No new external dependencies.
- No full live-suite runner by default.
- No install/deploy automation inside the default harness path. Deployment stays opt-in and explicit.
- No fallback to broad Rhino discovery once the harness owns a PID.

## Architecture

The v1 harness is a Python-owned process runner. It launches Rhino with `subprocess.Popen`, records `Popen.pid`, and treats that PID as the only valid runtime for the run.

Readiness is established only when `%TEMP%\rook\instance-{pid}-native.json` exists, parses as JSON, reports `processId == pid`, reports `pluginType == "native"`, contains a valid loopback host and positive port, and responds to `/ping` on that exact host and port. The harness rejects stale or ambiguous state rather than falling through to general discovery. If the owned discovery file exists but is malformed, points to another PID, is not native, has no valid port, or never becomes pingable before timeout, the run fails with captured artifacts.

After readiness, the harness snapshots the discovery JSON into its own run artifact directory. This snapshot is required because clean `CRookServer::Stop()` is expected to remove the canonical discovery file during shutdown.

The harness then runs a tiny selected smoke path through existing validation surfaces. Pytest runs only after owned-port and owned-PID scoping is enforced. Validation scripts may continue to receive `NATIVE_PORT=<port>` where that is their existing convention, but pytest uses a stronger contract: `ROOK_RHINO_PORT=<port>` and `ROOK_RHINO_PROCESS_ID=<pid>`.

Cleanup is process-owned. The harness captures artifacts before shutdown, requests an external graceful close of only the owned Rhino process, waits for exit, and verifies that `%TEMP%\rook\instance-{pid}-native.json` is gone. If graceful close times out, it captures artifacts again, marks cleanup as forced, force-kills only the owned PID, and reports the run as failed or non-green even if smoke passed.

## Components

### `RhinoRuntimeHarness`

Owns the lifecycle and run result state.

Responsibilities:

- Resolve the Rhino executable path.
- Launch Rhino and record PID, start time, command line, and timeouts.
- Ask `OwnedRhinoDiscovery` to establish readiness for the exact PID.
- Run the configured smoke command with scoped environment variables.
- Capture stdout, stderr, exit code, and elapsed time from the smoke command.
- Capture artifacts before shutdown and after cleanup failures.
- Request graceful close for the owned process only.
- Force-kill only the owned PID if cleanup times out.
- Produce a manifest that includes the cleanup path and whether the run is green.

A smoke pass followed by forced cleanup is not green because deterministic graceful shutdown is part of the harness contract.

### `OwnedRhinoDiscovery`

Owns exact-PID discovery and health checks.

Responsibilities:

- Read only `%TEMP%\rook\instance-{pid}-native.json` for harness readiness.
- Never fall back to `discover_instances()` or broad discovery in harness readiness.
- Reject malformed JSON, missing fields, wrong PID, non-native `pluginType`, non-loopback host, and invalid port.
- Detect and report when the owned Rhino process exits before discovery appears.
- Ping the exact discovered host/port.
- Re-read discovery before smoke execution and confirm PID and port are unchanged.
- Snapshot the owned discovery JSON into the run artifact directory before shutdown.

Parsing or normalization helpers may be reused from existing code if practical, but the authority is always the exact owned discovery path.

### Harness-Aware Pytest Scoping

Updates live-test setup so existing `requires_rhino` tests can run safely under the harness.

Behavior:

- If neither `ROOK_RHINO_PORT` nor `ROOK_RHINO_PROCESS_ID` is set, ambient live pytest behavior stays unchanged. Tests can discover any available Rhino and skip if none is reachable.
- If exactly one variable is set, pytest fails early. Partial harness mode is unsafe.
- If either value is malformed, pytest fails early.
- If both are set, pytest binds live calls to both port and process ID through the existing `bridge.py` request-context path or equivalent explicit routing.
- In harness mode, unreachable owned runtime is a failure, not a `requires_rhino` skip.
- The first ping in harness mode verifies the selected discovery record still reports the requested PID.

### Artifact Manifest and Log Copy

Artifact capture is a best-effort copy with a manifest, not a large subsystem.

The harness creates a per-run artifact directory and records:

- run start/end timestamps;
- Rhino executable and command line;
- owned PID;
- discovery path;
- owned discovery snapshot;
- selected smoke command;
- scoped environment keys passed to smoke;
- smoke stdout, stderr, exit code, and elapsed time;
- copied `%TEMP%\rook` files by timestamp window where readable;
- artifact-copy warnings for missing or unreadable files;
- cleanup path and cleanup outcome.

The collector runs before shutdown and again after cleanup failure paths. It tolerates `%TEMP%\rook` being missing or partially unreadable, records warnings, and continues.

## Data Flow

1. User runs the harness entry point with an optional Rhino executable path and explicit smoke selection.
2. `RhinoRuntimeHarness` records run metadata and starts Rhino.
3. `OwnedRhinoDiscovery` waits only on `%TEMP%\rook\instance-{pid}-native.json`.
4. Discovery validation rejects malformed, stale, non-native, wrong-PID, and invalid-port records.
5. If the owned process exits before discovery appears, the harness reports that separately from a generic timeout.
6. The harness pings `http://<host>:<port>/ping`.
7. The harness re-reads the same discovery file and confirms PID and port are unchanged.
8. The harness snapshots the discovery JSON into the run artifact directory.
9. The smoke command runs with scoped environment:
   - `ROOK_RHINO_PORT=<port>`
   - `ROOK_RHINO_PROCESS_ID=<pid>`
   - `NATIVE_PORT=<port>` only for selected validation scripts that already use it.
10. Harness-aware pytest validates full owned-mode env before touching Rhino.
11. The harness captures artifacts before shutdown.
12. The harness requests external graceful close of the owned process only.
13. Graceful shutdown is green only if the owned process exits and `%TEMP%\rook\instance-{pid}-native.json` is gone.
14. If graceful close times out, the harness captures artifacts again, force-kills only the owned PID, records forced cleanup, and reports failure.

## Error Handling

Harness failures are explicit and artifact-rich.

Startup and readiness failures include:

- Rhino executable not found;
- process launch failure;
- owned process exits before readiness, reported with its exit code;
- owned discovery file never appears while process stays alive;
- discovery file contains malformed JSON;
- discovery file has wrong `processId`;
- discovery file has missing or non-native `pluginType`;
- discovery file has missing, non-loopback, or invalid host/port;
- `/ping` fails or times out on the exact owned host/port;
- PID or port changes during the pre-smoke recheck.

Harness-mode pytest failures include:

- only one of `ROOK_RHINO_PORT` or `ROOK_RHINO_PROCESS_ID` is set;
- either env var is malformed;
- the owned runtime cannot be reached;
- discovery for the owned runtime does not still report the requested PID.

Cleanup is part of success. The manifest records one of these cleanup paths:

- `graceful_exit`;
- `graceful_exit_discovery_leftover`;
- `graceful_timeout_forced_kill`;
- `already_exited_before_cleanup`;
- `force_kill_failed`.

`graceful_exit` is green only when the owned process exits and the owned discovery file is gone. `graceful_exit_discovery_leftover` is non-green because clean `CRookServer::Stop()` should remove the discovery file. Forced cleanup paths are non-green. `already_exited_before_cleanup` is classified separately so startup crashes and post-smoke exits are diagnosable.

## Testing

Most first-slice tests should avoid requiring Rhino by using temp directories, fake process objects, and fake ping/close adapters.

### Unit Tests

`OwnedRhinoDiscovery` tests:

- valid owned discovery succeeds;
- wrong PID fails;
- non-native `pluginType` fails;
- missing port fails;
- invalid port fails;
- malformed JSON fails;
- no file before timeout fails;
- owned process exits before discovery is reported separately;
- discovery snapshot is written into the artifact directory;
- harness mode never falls back to broad discovery, even if another fake healthy Rhino exists.

Harness result tests:

- `graceful_exit`;
- `graceful_exit_discovery_leftover`;
- `graceful_timeout_forced_kill`;
- `already_exited_before_cleanup`;
- `force_kill_failed`;
- smoke pass plus forced cleanup is non-green;
- startup/readiness failure captures artifacts and writes a manifest;
- smoke stdout, stderr, exit code, and elapsed time are recorded.

Pytest scoping tests:

- ambient mode remains unchanged when both env vars are absent;
- owned mode binds both port and process ID;
- partial env fails early;
- malformed env fails early;
- owned runtime unreachable fails rather than skips;
- the first harness-mode ping verifies discovery still reports the requested PID.

Smoke subprocess environment tests:

- pytest smoke receives exactly `ROOK_RHINO_PORT` and `ROOK_RHINO_PROCESS_ID` as the harness contract;
- validation-script smoke receives `NATIVE_PORT` only when the selected script needs it;
- unrelated harness internals are not exposed as test-routing contracts.

Artifact tests:

- manifest records command output and cleanup outcome on success;
- manifest records command output and cleanup outcome on failure;
- log copy succeeds when `%TEMP%\rook` contains matching files;
- missing `%TEMP%\rook` records a warning but does not hide the original failure;
- partially unreadable log files record warnings and continue.

### Live Verification

The documented live command should be opt-in and small. It should:

- start Rhino from a clean local state;
- wait for exact owned-PID discovery;
- prove `/ping` on the exact port;
- run one tiny selected live smoke using existing tests or validation scripts;
- capture artifacts;
- gracefully close Rhino;
- report non-green if cleanup requires force-kill or leaves the owned discovery file behind.

It should not run full `pytest -m requires_rhino` by default.

## Future Work

After v1 is proven reliable, later work may add lifecycle-wrapper coverage for `RookPlugin.OnLoad` / `OnShutdown` try/catch paths. If external graceful close proves unreliable, a native control route can be designed separately. Such a route must not rely on `ROOK_ENABLE_DEBUG_ROUTES=1` alone; it should also require a per-run secret injected into the harness-owned Rhino process and never published in discovery.

