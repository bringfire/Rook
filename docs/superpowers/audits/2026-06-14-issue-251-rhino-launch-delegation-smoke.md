# Issue #251 Rhino Launch Delegation Smoke

## Repository State

- Branch: `codex/rhino-launch-workbench-spec`
- Base: merged #222 on `main`, plus the separate #254 hygiene fix for
  `rhino_vision_presentation` targeting policy.
- Delegation commit under test: `6a25e009 Delegate rhino_launch to owned workbench launcher`

## Runtime State

- Supported deploy attempt:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning
```

- Result: payload sync ran, then `post_install.py config refresh failed with exit code 1`.
- Fallback sync used for the changed Python modules:
  - `mcp_server/src/rook/server.py` -> `C:\Users\aryan\AppData\Local\Rook\venv\Lib\site-packages\rook\server.py`
  - `mcp_server/src/rook/targeting.py` -> `C:\Users\aryan\AppData\Local\Rook\venv\Lib\site-packages\rook\targeting.py`
- Installed-runtime import check:
  - `rook.server.__file__`: `C:\Users\aryan\AppData\Local\Rook\venv\Lib\site-packages\rook\server.py`
  - `rook.targeting.__file__`: `C:\Users\aryan\AppData\Local\Rook\venv\Lib\site-packages\rook\targeting.py`
  - `_RHINO_LAUNCH_CANONICAL_TOOL`: `rhino_workbench_launch`
  - `rhino_vision_presentation in targeting.TOOL_POLICIES`: `True`

## In-App MCP Connector

- The current Codex session's in-app Rook MCP connector did not recover after stopping stale `python -m rook` processes.
- `rhino_workbench_list {}` returned:

```text
tool call error: tool call failed for `rook/rhino_workbench_list`

Caused by:
    Transport closed
```

- Retried after direct stdio MCP cleanup with the same result.
- Therefore this audit distinguishes the successful direct stdio MCP proof below from a fresh-Codex in-app connector proof. A fresh Tester Codex can rerun the same tool calls if reviewer policy requires the exact in-app path.

## Direct Stdio MCP Tool Metadata

The smoke spawned the installed runtime with `C:\Users\aryan\AppData\Local\Rook\venv\Scripts\python.exe -m rook` and called tools through the MCP Python client.

`rhino_launch` description:

```text
Compatibility launcher for Rhino availability. If Rhino is already reachable, returns already_running without changing the active binding. If Rhino is not reachable, delegates to rhino_workbench_launch and returns that owned workbench launch envelope.

Prefer rhino_workbench_launch for new automation that needs an owned disposable Rhino session. Safe to call multiple times.
```

`timeout` schema:

```json
{
  "description": "Max seconds to wait for owned workbench readiness (default: 90). Maps to readinessTimeoutSeconds.",
  "type": "integer"
}
```

This is the stale-code guard for the direct stdio run: the installed runtime loaded the delegated `rhino_launch` tool schema.

## Success Smoke

Pre-run `rhino_workbench_list`:

```json
{
  "workbenches": []
}
```

Pre-run OS `Rhino.exe` snapshot: none.

`rhino_launch {"timeout":90}` result:

```json
{
  "session": "rhino-52240",
  "processId": 52240,
  "port": 56733,
  "owned": true,
  "mode": "workbench",
  "boundInSeconds": 19.06,
  "evidence": {
    "requestedScheme": "RookWorkbench",
    "activeScheme": null,
    "isolationMode": "default",
    "discoveryRecordPath": "C:\\Users\\aryan\\AppData\\Local\\Rook\\discovery\\instance-52240-native.json",
    "discoveryLogSeen": true,
    "windows": [],
    "visibleWindowCount": 0,
    "emptyTitleWindowPresent": false,
    "exitCode": null,
    "argv": [
      "C:\\Program Files\\Rhino 8\\System\\Rhino.exe",
      "/nosplash"
    ],
    "elapsedSeconds": 19.078000000008615,
    "diagnosticHint": null,
    "launchEnv": {
      "authoritative": {
        "SystemDrive": "C:",
        "SystemRoot": "C:\\Windows",
        "windir": "C:\\Windows"
      },
      "backfilled": {
        "ProgramData": "C:\\ProgramData"
      },
      "missing_unresolved": [],
      "fallback_used": []
    }
  },
  "auto_bound": true,
  "active": {
    "port": 56733,
    "processId": 52240
  },
  "canonicalTool": "rhino_workbench_launch"
}
```

Follow-up `rhino_workbench_list`:

```json
{
  "workbenches": [
    {
      "session": "rhino-52240",
      "processId": 52240,
      "port": 56733,
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
  ]
}
```

Cleanup:

```json
{
  "session": "rhino-52240",
  "owned": true,
  "mode": "workbench",
  "closed": true,
  "cleanupStatus": "forced_kill",
  "discardedUnsavedChanges": true
}
```

Post-close `rhino_workbench_list`:

```json
{
  "workbenches": []
}
```

Final OS `Rhino.exe` snapshot: none.

## Forced-Failure Smoke

Preconditions:

- No visible `Rhino.exe`.
- No owned workbench sessions after closing `rhino-52240`.

`rhino_launch {"timeout":0}` result:

```text
Error: {
  "code": "invalid_readiness_timeout",
  "message": "readinessTimeoutSeconds must be a positive number, got 0.",
  "retryable": false,
  "canonicalTool": "rhino_workbench_launch"
}
```

Legacy bare string absent: yes. The response did not contain `Rhino failed to start within`.

Post-failure `rhino_workbench_list`:

```json
{
  "workbenches": []
}
```

## Cleanup

- Final OS `Rhino.exe` snapshot: none.
- Direct-smoke `python -m rook` processes were stopped after the run.
- Final `python -m rook` process snapshot: none.

## Classification

- Outcome: `direct_stdio_mcp_passed_in_app_blocked`.
- Rationale:
  - The installed runtime loaded the delegated `rhino_launch` schema.
  - MCP-driven `rhino_launch` success returned an owned workbench payload with `canonicalTool`, `launchEnv`, and auto-bind metadata.
  - MCP-driven forced failure returned a structured `invalid_readiness_timeout` envelope with `canonicalTool`; the legacy bare timeout string was absent.
  - Cleanup removed the owned workbench, Rhino PID, and direct-smoke MCP processes.
  - The current Codex in-app connector remained stuck at `Transport closed`, so a fresh in-app Tester Codex is needed only if the review gate requires that exact connector path rather than direct stdio MCP.
