# Issue #251 Rhino Workbench Launch Gate Rerun

## Repository State

- Branch: `codex/rhino-launch-workbench-spec`
- Worktree: clean at start and end of tester run.
- Relevant commits present:
  - `6c813096 Record in-app Rhino launch env validation`
  - `7c679662 Record Rhino launch env live proof`
  - `1dd4d102 Apply controlled env to owned Rhino launches`

## Static Timeout Comparison

- Owned launcher readiness timeout: `90s`, from `rhino_workbench_launch {"readinessTimeoutSeconds":90}` and the launcher default.
- MCP client tool timeout: `120s`, from `C:/Users/aryan/.codex/config.toml`, `[mcp_servers.rook]`, `tool_timeout_sec = 120`.
- Static comparison result: `readiness < client`; the run is not structurally racing the client timeout.

## Pre-Run Snapshot

- `rhino_workbench_list`: `{"workbenches":[]}`.
- OS `Rhino.exe` snapshot: none.
- Rook-owned workbenches: none.
- Non-owned Rhino processes: none.
- User decision: none required because no non-owned Rhino was present.

## MCP-Wrapped Launch Arm

- Tool: `rhino_workbench_launch`.
- Arguments:

```json
{"readinessTimeoutSeconds":90}
```

- Result:
  - session: `rhino-46584`
  - processId: `46584`
  - port: `65226`
  - wall time: `15.1017s`
  - `boundInSeconds`: `15.03`
  - `evidence.elapsedSeconds`: `15.062999999994645`
  - `evidence.launchEnv`: present

Launch environment evidence:

```json
{
  "authoritative": {
    "SystemDrive": "C:",
    "SystemRoot": "C:\\Windows",
    "windir": "C:\\Windows"
  },
  "backfilled": {
    "ProgramData": "C:\\ProgramData"
  },
  "inherited": [
    "APPDATA",
    "LOCALAPPDATA",
    "PATH",
    "TEMP",
    "TMP",
    "USERPROFILE"
  ],
  "missing_unresolved": [],
  "fallback_used": []
}
```

## MCP Liveness After Launch

- Follow-up `rhino_workbench_list` returned session `rhino-46584`.
- lifecycle: `bound`.
- liveness: `live`.
- `pidAlive`: `true`.
- `portListening`: `true`.
- MCP remained live after the launch call.

## Cleanup

Close call:

```json
{"session":"rhino-46584","graceful":false}
```

Close result:

```json
{
  "session": "rhino-46584",
  "owned": true,
  "mode": "workbench",
  "closed": true,
  "cleanupStatus": "forced_kill",
  "discardedUnsavedChanges": true
}
```

Final cleanup evidence:

- `rhino_workbench_list`: `{"workbenches":[]}`.
- `Get-Process -Id 46584`: no process found.
- OS `Rhino.exe` snapshot: none.
- Final `git status --short`: clean.

## Classification

- Outcome: `clear`.
- Rationale:
  - The gate ran through the MCP-wrapped `rhino_workbench_launch` path, not a direct control.
  - The pre-run state was clean: no owned workbenches and no live `Rhino.exe` processes.
  - The launch succeeded with a structured owned workbench payload and real `launchEnv` evidence.
  - The launch completed in about 15 seconds, with comfortable headroom under the 90s readiness timeout and 120s MCP client timeout.
  - MCP remained live after launch and serviced follow-up `rhino_workbench_list`.
  - Cleanup removed the owned session and PID.

## Routing

- Per the approved issue #251 spec, `clear` unblocks the `rhino_launch` delegation implementation.
- No transport split issue is required from this gate result.
