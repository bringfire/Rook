# Issue #251 Rhino Workbench Launch Gate

## Repository State

- Branch: `codex/rhino-launch-workbench-spec`
- HEAD: `7d62d30 Record Rook MCP transport probe`
- Working tree notes:
  - Gate artifact reset to the approved skeleton and filled with fresh evidence from this run.
  - Pre-existing unrelated untracked files were left untouched:
    - `docs/rook_docs/2026-06-13-freecad-rook-bim-architecture.md`
    - `docs/rook_docs/freecad-spike/`

## Static Timeout Comparison

- Owned launcher default readiness timeout: 90s from `mcp_server/src/rook/workbench.py` (`launch_owned_workbench(readiness_timeout_seconds: int = 90)`) and `mcp_server/src/rook/server.py` (`readinessTimeoutSeconds` schema and dispatcher default 90).
- MCP client call timeout: 120s from `C:/Users/aryan/.codex/config.toml`, `[mcp_servers.rook]`, `tool_timeout_sec = 120`.
- Static comparison result: `readiness < client`.

## Pre-Run Snapshot

- Timestamp: `2026-06-13T23:17:35.2449644-04:00`.
- Cold/warm: `warm-clean`. No live Rhino process was present, but this is not the first Rhino/Rook launch since boot. OS boot was `2026-06-12 21:53:54-04:00`, and existing discovery files from `2026-06-13` show prior Rhino/Rook startup in this boot session.
- Rhino processes: none from `Get-Process Rhino` and `Get-CimInstance Win32_Process -Filter "Name = 'Rhino.exe'"`.
- Rook-owned workbench sessions: `{"workbenches": []}` from MCP `rhino_workbench_list`.
- Non-owned Rhino processes: none visible.
- Recovery or modal evidence: none visible; no Rhino window titles were present and nothing was dismissed.
- Discovery files:
  - Discovery folder resolved to `C:/Users/aryan/AppData/Local/Rook/discovery`.
  - Resolver source candidates: `C:/Users/aryan/AppData/Local/Rook/discovery`, `C:/Users/aryan/AppData/Local/Temp/rook`.
  - Folder contains stale historical discovery/log files, including `companion-42648.json`, `native-discovery-42648.log`, and many older `native-discovery-*.log` / `companion-load-*.log` rows. No matching live `Rhino.exe` process was present.

## Cleanup Actions

- Rook-owned sessions closed: none; `rhino_workbench_list` returned no owned workbenches.
- Non-owned Rhino action: none required; no non-owned Rhino processes remained.
- Recovery/profile action: none; recovery/profile state was only observed passively.

## MCP-Wrapped Launch Arm

- Cold/warm at arm start: `warm-clean`; no live Rhino process or owned workbench rows were present, but the run was not cold because Rhino/Rook had launched earlier in this OS boot session.
- Tool: `rhino_workbench_launch`.
- Arguments: `{}`.
- Start time: `2026-06-13T23:18:06.8977896-04:00`.
- End time: `2026-06-13T23:18:27.4728869-04:00`.
- Elapsed: MCP tool wall time reported `8.9153s`; timestamp span including surrounding shell probes was about `20.6s`.
- Result or transport symptom:
  - Structured MCP payload returned; transport did not close.
  - Result:

```json
{
  "code": "workbench_exited_before_bind",
  "message": "Rhino exited with code 3762504530 before RookNative discovery appeared",
  "processId": 54396,
  "retryable": true,
  "reason": "exited_before_bind",
  "evidence": {
    "requestedScheme": "RookWorkbench",
    "activeScheme": null,
    "isolationMode": "default",
    "discoveryRecordPath": null,
    "discoveryLogSeen": false,
    "windows": [],
    "visibleWindowCount": 0,
    "emptyTitleWindowPresent": false,
    "exitCode": 3762504530,
    "argv": [
      "C:\\Program Files\\Rhino 8\\System\\Rhino.exe",
      "/nosplash"
    ],
    "elapsedSeconds": 8.828999999997905,
    "diagnosticHint": null
  },
  "cleanupStatus": "forced_kill"
}
```

- MCP server liveness after call: live. `rhino_workbench_list` and `rhino_instances` both returned after the launch failure.
- Rhino process liveness after call: no live `Rhino.exe` process remained after the failed launch arm.
- Registry rows after call:
  - `rhino_workbench_list`: `{"workbenches": []}`.
  - `rhino_instances`: `{"count": 0, "instances": [], "active": null}`.
- Discovery/log evidence after call:
  - No discovery rows matching PID `54396` were present.
  - Recent discovery folder rows still pointed at earlier stale historical PIDs, such as `native-discovery-42648.log`; no live process matched them.
- Modal/window evidence after call: none. No live Rhino process or visible Rhino title remained.

## Short-Timeout Arm

- Run required: no. The default MCP launch arm returned a structured non-timeout launcher failure quickly; it did not block, fail ambiguously, or return a timeout-like symptom.
- Tool: not run.
- Arguments: not applicable.
- Result: not applicable.
- Evidence: The MCP server continued servicing `rhino_workbench_list` and `rhino_instances` after the launch arm, and the launch failure was `workbench_exited_before_bind`, not a timeout.

## Direct Async Control

- Run required: yes.
- Reason: Required because the MCP launch arm failed. This localizes whether `launch_owned_workbench()` can succeed in an equivalent async in-process context.
- Baseline re-clean completed: yes. Before the control, `Get-Process Rhino` / Win32 process inspection showed no live Rhino process, and `rhino_workbench_list` returned `{"workbenches": []}`.
- Start time: `2026-06-13T23:18:41.2457613-04:00`.
- End time: command returned about `36.835s` later; teardown evidence was captured at `2026-06-13T23:19:43.3266607-04:00`.
- Elapsed: `36.835s`.
- Result:

```json
{
  "elapsed_seconds": 36.835,
  "result": {
    "success": true,
    "data": {
      "session": "rhino-53792",
      "processId": 53792,
      "port": 52056,
      "owned": true,
      "mode": "workbench",
      "boundInSeconds": 36.8
    }
  }
}
```

- Evidence:
  - MCP saw the control-created row:

```json
{
  "session": "rhino-53792",
  "processId": 53792,
  "port": 52056,
  "lifecycleStatus": "bound",
  "mode": "workbench",
  "lastPortUp": true,
  "liveness": {
    "state": "live",
    "pidAlive": true,
    "portListening": true,
    "code": null
  }
}
```

  - The session was closed through MCP `rhino_workbench_close` with `{"session":"rhino-53792","graceful":true}`.
  - Close result: `{"closed": true, "cleanupStatus": "graceful_exit", "discardedUnsavedChanges": false}`.
  - Post-close `rhino_workbench_list` returned `{"workbenches": []}`.
  - Post-close `Get-Process Rhino` showed no live Rhino process.
  - Discovery files for PID `53792` were created: `native-discovery-53792.log`, `companion-53792.json`, and `companion-load-53792.log`.

## Classification

- Outcome: `unverified`.
- Rationale:
  - The run cannot be `clear` because it was not cold by the approved definition and the MCP-wrapped launch arm did not succeed.
  - The MCP-wrapped launch arm returned a structured launcher failure (`workbench_exited_before_bind`) instead of a transport closure.
  - Static timeout constants do not indicate client timeout pressure (`readiness < client`, `90s < 120s`), and the failure returned in about 9 seconds.
  - The MCP server remained live and serviced `rhino_workbench_list` and `rhino_instances` after the failed launch, so this run does not classify as `server_death` or `event_loop_starvation`.
  - There was no live Rhino process or modal/window evidence after the failed launch, so this run does not classify as `recovery_modal_222`.
  - The direct async control succeeded from the re-cleaned baseline and was visible/closable through MCP, proving the owned launcher can work in-process but not proving the MCP-wrapped launch arm is clear.
  - The observed MCP-arm failure (`Rhino exited with code 3762504530 before RookNative discovery appeared`) is outside the approved failure buckets, so the gate must remain unverified.
- Routing:
  - Per the approved spec, hold #251 delegation unless the reviewer/user explicitly accepts the `unverified` risk.
  - Present this artifact for review before writing delegation code.

## Reviewer Notes

- Optional concurrent-service evidence:
  - Not captured concurrently during a long in-flight launch because the MCP arm returned quickly.
  - Post-failure MCP calls succeeded: `rhino_workbench_list` returned no owned sessions; `rhino_instances` returned no active instances.
- Follow-up issue required:
  - Not filed yet from this artifact alone.
  - Reviewer should decide whether the MCP-only `workbench_exited_before_bind` versus direct-control success requires a separate launch-environment issue before #251 delegation.
