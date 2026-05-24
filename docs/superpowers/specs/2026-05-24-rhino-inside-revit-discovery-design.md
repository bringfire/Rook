# Rhino.Inside Revit Discovery Reliability Design

## Context

Fresh-machine release smoke for the refreshed Rook installer showed that normal
Rhino now works: RookNative loads, the managed companion loads, native discovery
is published, `/ping` works, RookChat works, and Claude Code works after the
user signs in to Claude Code in a terminal.

The remaining release blocker is Rhino.Inside Revit target discovery. On the
test laptop, Revit 2024 hosted Rhino 8 and loaded `RookNative.rhp`. The native
HTTP bridge listened on `127.0.0.1:57011` and `/ping` returned `pong`, but the
Rook MCP server reported no discovered instances:

```text
rhino_ping({"port":57011}) -> rhino_target_unavailable, instances: []
rhino_ping({})             -> no_rhino_instance, instances: []
```

The observed installed binary was `1.5.7.0`. Local source has since advanced to
`1.5.8`, so implementation and validation must confirm that the tested binary
contains the discovery behavior under investigation before drawing conclusions
from another live run.

## Goal

Make Rhino.Inside Revit publish the same authoritative native discovery metadata
as normal Rhino, then keep MCP target selection based on that discovery metadata.
When Revit is the only live host, `rhino_ping({})` should discover and target
the Revit-hosted RookNative bridge.

## Non-Goals

Do not make an explicit `port` a general fallback target. Explicit ports remain
selectors over discovered targets only.

Do not add a hidden second routing model that bypasses PID, plugin type,
capabilities, stale cleanup, panel locking, or multi-instance safety.

Do not treat installer registration as the primary suspect unless discovery
publication proves to depend on installer paths.

## Design Decisions

Native discovery remains the single source of truth for Rhino targets. The file
contract is a discovery record under the shared discovery root resolved by both
native and MCP:

```text
<shared-discovery-root>\instance-<host-process-pid>-native.json
```

Today's default shared discovery root is `%TEMP%\rook`, but the implementation
must not hard-code that as the architectural contract if native and MCP resolve
different temp roots on the test machine.

For Rhino.Inside Revit, `<host-process-pid>` and JSON `processId` should be the
Revit process ID, because `RookNative.rhp` is loaded in the Revit process. The
JSON record should include at least:

```json
{
  "host": "127.0.0.1",
  "port": 57011,
  "pluginType": "native",
  "processId": 528,
  "pluginVersion": "1.5.8",
  "rhinoInside": true,
  "capabilities": {
    "ghProvider": "callback",
    "ghRoutes": []
  }
}
```

MCP route resolution should not probe HTTP as part of normal explicit-port
routing. If `rhino_ping({"port": 57011})` is requested and no discovered
instance owns port `57011`, return a discovery-based error such as
`requested_port_not_discovered` with the requested port, the MCP-resolved
discovery folder, and current discovered instances. A separate doctor/debug path
may probe arbitrary ports, but normal tool routing must not.

## Native Diagnostics

Add best-effort durable diagnostics around native discovery publication and
cleanup. Diagnostics should help distinguish:

- the discovery write never ran
- the file was written to a different temp root
- temp file creation failed
- atomic rename failed
- the file was written and later deleted
- startup cleanup removed a still-live Revit-hosted discovery file

The native diagnostic log should live under the resolved native discovery root,
for example:

```text
<native-discovery-root>\native-discovery-<pid>.log
```

Each relevant event should include:

- native temp root from `std::filesystem::temp_directory_path()`
- final selected shared discovery root and the precedence branch that selected it
- `TEMP` and `TMP` environment values visible to the native process
- final discovery file path and temporary file path
- current process ID
- process image/name when cheaply available
- `rhinoInside`
- native HTTP port
- temp file open/write result
- `MoveFileExW` result and Windows error code on failure
- post-rename verification result: final file exists, final file size is
  nonzero, and read-back or JSON parse success when practical
- startup cleanup scan decisions for discovery files
- remove-on-unload decisions

Diagnostics are not operationally required. Rook should continue operating if
diagnostic logging fails. Discovery write failure is the product bug; diagnostic
write failure should only emit best-effort `RhinoApp().Print` or debug output.

## Temp Root Mismatch

Treat temp-directory mismatch as a first-class suspect. Native uses
`std::filesystem::temp_directory_path()` while MCP uses Python
`tempfile.gettempdir()`. In Rhino.Inside Revit, launch context, environment,
elevation, or user profile state could make these disagree.

Native diagnostics must record native `TEMP`/`TMP` and resolved discovery root.
MCP diagnostics/errors must report Python `tempfile.gettempdir()` and the
resolved `DISCOVERY_FOLDER`. If those differ on the test machine, the fix should
prefer a deterministic per-user discovery root both runtimes can compute without
installer state.

Only use an installer-provided stable runtime setting if a code-computed
per-user root is proven insufficient. If that fallback is used, specify
precedence explicitly: runtime environment or config value first, computed
per-user root second, and legacy `%TEMP%\rook` only as a compatibility fallback.
Upgrade behavior must preserve discovery for already-installed users, and the
implementation must document that already-running Rhino or Revit processes will
not observe installer-time setting changes until restart.

## MCP Diagnostics

Keep `discover_instances()` authoritative. Add clearer error reporting for
explicit-port misses without probing HTTP:

```json
{
  "error": "requested_port_not_discovered",
  "message": "No discovered RookNative instance owns the requested port. Native discovery publication may have failed or MCP may be looking in a different temp directory.",
  "requestedPort": 57011,
  "discoveryFolder": "<MCP-resolved-shared-discovery-root>",
  "instances": []
}
```

This error should be returned by normal MCP routing before dispatch. It must not
silently call `http://127.0.0.1:<port>/ping`.

## Cleanup Contract

Native startup cleanup and MCP stale cleanup must not remove an active
Rhino.Inside Revit discovery file while Revit is alive. The filename PID and JSON
`processId` are the core identity contract, so cleanup must validate process
liveness against the host process ID recorded in the file.

If cleanup removes a file, diagnostics should record the file name, parsed PID,
JSON PID when applicable, and the liveness decision.

## Tests

Python unit tests:

- `discover_instances()` accepts native discovery records with
  `rhinoInside: true`.
- `resolve_tool_route("rhino_ping", explicit_port=<known>)` succeeds when the
  discovered Rhino.Inside native instance owns the port.
- `resolve_tool_route("rhino_ping", explicit_port=<missing>)` fails with
  `requested_port_not_discovered` and includes the requested port, discovery
  folder, and current instances.
- stale cleanup keeps a Rhino.Inside native discovery file when `_is_pid_alive`
  returns true for its `processId`.
- stale cleanup removes a Rhino.Inside native discovery file when `_is_pid_alive`
  returns false.

Native/source guard tests:

These are static or source-level regression guards only. They can prevent
obvious omissions, but they do not prove runtime discovery publication,
filesystem visibility, or Revit-hosted cleanup behavior. Live validation remains
the behavioral gate.

- discovery publication includes `rhinoInside`.
- discovery publication includes process ID, port, plugin version, plugin type,
  and capabilities.
- discovery diagnostics include temp-root, path, PID, `rhinoInside`, port, write,
  rename, cleanup, and removal event strings.

Live validation:

- install the current release-candidate build and confirm file versions match
  the source version being investigated.
- launch Revit with Rhino.Inside Revit and load RookNative.
- require `<shared-discovery-root>\instance-<RevitPID>-native.json`, where the
  shared discovery root is the same path reported by native diagnostics and MCP
  diagnostics.
- require JSON `processId` to equal Revit PID.
- require `rhinoInside: true`.
- require JSON `port` to match the listening Rook native port.
- require `/ping` on that port to return `pong`.
- require `rhino_ping({})` from MCP to succeed when this is the only live target.
- require `rhino_ping({"port": <port>})` to succeed only because that port is
  present in discovery.

## Acceptance Criteria

The fix is complete when:

- Rhino.Inside Revit publishes a native discovery file under the MCP-visible
  discovery root.
- The discovery file represents the Revit host process identity and includes
  `rhinoInside: true`.
- MCP `rhino_instances` lists the Revit-hosted native bridge.
- MCP `rhino_ping({})` succeeds when the Revit-hosted bridge is the only live
  target.
- MCP `rhino_ping({"port": <port>})` succeeds only when discovery contains that
  port.
- MCP explicit-port misses return `requested_port_not_discovered` without HTTP
  probing.
- Startup and MCP cleanup do not remove live Revit-hosted discovery files.
- Unit/source guards pass.
- Live Revit smoke passes on the test laptop or equivalent clean machine.
