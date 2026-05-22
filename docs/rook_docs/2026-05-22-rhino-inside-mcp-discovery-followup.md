# Rhino.Inside MCP Discovery Follow-up

Date: 2026-05-22

## Context

Rook 1.5.6 was smoke-tested in Revit 2024 with Rhino.Inside.Revit after the multi-runtime installer fixes. RookNative, the managed Rook companion, RookChat, RookVision, and RookKnowledgeGraph loaded and functioned in the Revit-hosted Rhino session.

The remaining issue is specific to external MCP discovery from Codex/Claude sessions. It is not a plugin-load failure.

## Observed State

- Revit process: `Revit.exe` PID `39240`.
- RookNative HTTP bridge: `127.0.0.1:52045`.
- Direct HTTP probe: `GET http://127.0.0.1:52045/ping` returned `{"data":"pong","success":true}`.
- Panel-owned chat service: `python.exe` PID `45316` on `127.0.0.1:62747`.
- Chat health: `GET http://127.0.0.1:62747/agent/chat/health` reported:
  - owner `rhino-panel`
  - `rhinoProcessId: 39240`
  - Rhino connected `true`
  - Rhino ping data `pong`

External Codex MCP tools did not attach to that session:

- `rhino_instances`: `count: 0`
- `rhino_get_active_instance`: `active: null`
- `rhino_ping`: `no_rhino_instance`
- explicit bind to port `52045`: `rhino_target_unavailable`

## Current Discovery Mechanism

The external MCP server discovers Rhino instances by reading JSON files under `%TEMP%\rook`:

- `mcp_server/src/rook/bridge.py` uses `Path(tempfile.gettempdir()) / "rook"`.
- `mcp_server/src/rook/agent/chat/server.py` writes chat service discovery under the same temp-derived folder.
- `src/RookNative/RookServer.cpp` writes `instance-<pid>-native.json` under `std::filesystem::temp_directory_path() / "rook"`.
- `src/Rook/RookPaths.cs` uses `Path.GetTempPath()` for companion-side discovery paths.

During the Rhino.Inside smoke, the Codex process saw no live `instance-*-native.json` files in its `%TEMP%\rook` folder even though direct HTTP to RookNative was healthy. The panel chat service could reach the same bridge because its process-local context was already bound to the owning Revit process.

## Working Theory

`%TEMP%` is not a robust cross-process discovery contract for all supported hosts. Revit/Rhino.Inside, panel-owned Python services, and external Codex/MCP server processes can disagree about the effective temp directory or discovery lifecycle. When the discovery file is absent from the external process' temp view, the external MCP layer reports no instances even though the RookNative HTTP bridge is live.

There is also an MCP targeting strictness issue: explicit port binding currently requires the port to appear in discovery first. In this incident, direct HTTP proved `52045` was valid, but `rhino_set_active_instance(port=52045)` returned `rhino_target_unavailable` because discovery returned zero instances.

## Recommended Follow-up

Implement a stable per-user discovery root and keep `%TEMP%\rook` as a temporary fallback during migration.

Suggested root:

```text
%LOCALAPPDATA%\Rook\runtime\discovery
```

Design goals:

- Native Rook, managed Rook, panel chat services, and external MCP servers should all read/write the same per-user discovery folder.
- Discovery records should continue to include process ID, host, port, plugin type, Rhino.Inside flag, version, and capabilities.
- Stale cleanup should still remove records for dead PIDs.
- MCP discovery should read the stable folder first and optionally merge legacy `%TEMP%\rook` records until existing installs age out.
- Explicit port binding should have a controlled live-probe fallback for loopback ports when discovery is empty or stale. A direct probe should verify `/ping`, then bind only if the response is a valid Rook response.

## Non-goals

- Do not change plugin loading or installer runtime selection as part of this QOL fix.
- Do not introduce Yak/package-directory distribution changes.
- Do not weaken multi-instance safety for mutating tools; direct port fallback must still be explicit and loopback-only.

## Validation for the Follow-up

- Unit-test discovery root selection and legacy fallback.
- Unit-test stale cleanup against both discovery roots.
- Unit-test explicit-port fallback when discovery is empty but `/ping` succeeds.
- Live-test standalone Rhino and Rhino.Inside.Revit from a fresh external Codex session:
  - `rhino_instances` lists the active instance.
  - `rhino_set_active_instance(port=<live-port>)` succeeds.
  - `rhino_ping` returns `pong`.
  - Panel chat service health continues to report the owning Rhino process and connected bridge.
