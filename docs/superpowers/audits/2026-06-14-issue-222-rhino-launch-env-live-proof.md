# Issue #222 Rhino Launch Env Live Proof

## Runtime Bound

- Branch: `codex/rhino-launch-workbench-spec`
- Code commit under proof: `1dd4d10 Apply controlled env to owned Rhino launches`
- Installed runtime import path after sync:
  `C:\Users\aryan\AppData\Local\Rook\venv\Lib\site-packages\rook\rhino_launch.py`

### Sync Method

First attempted the supported local deploy path:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning
```

That script copied the AppData payload, but failed during `post_install.py`
config refresh with exit code `1`. The installed venv still imported stale
`rook-mcp` from site-packages and did not expose `build_launch_env`.

For this live proof, synced the three changed Python modules directly into the
installed package the runtime imports:

```powershell
C:\Users\aryan\AppData\Local\Rook\venv\Lib\site-packages\rook\rhino_launch.py
C:\Users\aryan\AppData\Local\Rook\venv\Lib\site-packages\rook\workbench.py
C:\Users\aryan\AppData\Local\Rook\venv\Lib\site-packages\rook\runtime_harness.py
```

Post-sync import verification from the installed venv:

```text
rhino_launch.py path: C:\Users\aryan\AppData\Local\Rook\venv\Lib\site-packages\rook\rhino_launch.py
rook.rhino_launch.build_launch_env: True
rook.workbench.build_launch_env: True
rook.runtime_harness.build_launch_env: True
build_launch_env({'PATH':'C:\Tools'}).env['windir']: C:\Windows
```

Report from that import check:

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
  "inherited": {
    "PATH": "C:\\Tools"
  },
  "missing_unresolved": [
    "APPDATA",
    "LOCALAPPDATA",
    "TEMP",
    "TMP",
    "USERPROFILE"
  ],
  "fallback_used": []
}
```

### Binding Note

The in-app Rook tool binding was attached to a stale `python -m rook` process
started before these commits. After stopping those stale MCP processes, the
in-app wrapper remained in a closed-transport state in this thread and did not
spawn a replacement server. To keep the proof MCP-driven, the live launch below
used an explicit MCP stdio client against the installed AppData venv:

```text
command: C:\Users\aryan\AppData\Local\Rook\venv\Scripts\python.exe
args: -m rook
cwd: C:\Users\aryan\AppData\Local\Rook\app\mcp_server
```

The client deliberately removed `windir`, `SystemRoot`, and `SystemDrive` from
the MCP parent environment before launching the Rook MCP server.

## MCP Launch Result

- Tool: `rhino_workbench_launch`
- Arguments: `{"readinessTimeoutSeconds": 90}`
- MCP server name: `rook`
- Tool count: `402`
- Initial owned workbench list: `{"workbenches": []}`
- Result: success data object returned directly by MCP call

```json
{
  "session": "rhino-62768",
  "processId": 62768,
  "port": 55091,
  "owned": true,
  "mode": "workbench",
  "boundInSeconds": 50.89,
  "evidence": {
    "requestedScheme": "RookWorkbench",
    "activeScheme": null,
    "isolationMode": "default",
    "discoveryRecordPath": "C:\\Users\\aryan\\AppData\\Local\\Rook\\discovery\\instance-62768-native.json",
    "discoveryLogSeen": true,
    "visibleWindowCount": 0,
    "emptyTitleWindowPresent": false,
    "exitCode": null,
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
      "fallback_used": [],
      "missing_unresolved": []
    }
  }
}
```

The full runtime response included inherited parent-customizable values such as
`PATH`, `APPDATA`, `LOCALAPPDATA`, `TEMP`, `TMP`, and `USERPROFILE`. The
load-bearing proof is that the three removed Windows invariants were restored
in `evidence.launchEnv.authoritative` and Rhino bound successfully.

Non-owned Rhino state was not required for this #222 proof. No user Rhino
session was closed solely for this proof.

## MCP Close Result

The proof client initially expected a `{"success": true, "data": ...}` wrapper,
but this MCP path returned the success data object directly, so the immediate
close branch did not run in that first client invocation.

Follow-up process and MCP checks:

- Rhino PID `62768`: not running after the proof client exited.
- `python -m rook` proof server: not running after the proof client exited.
- Fresh MCP `rhino_workbench_list`: `{"workbenches": []}`
- Follow-up `rhino_workbench_close` for `rhino-62768`: returned `not_owned`
  because the session was already absent from the fresh runtime's owned list.
- Fresh MCP `rhino_workbench_list` after close attempt: `{"workbenches": []}`

No owned workbench session or Rhino process remained after the proof.

## Classification

The #222 environment defect is fixed on the installed MCP runtime under an
MCP-driven launch: with `windir`, `SystemRoot`, and `SystemDrive` removed from
the MCP parent environment, `rhino_workbench_launch` created a Rhino process,
bound RookNative discovery successfully, and returned
`evidence.launchEnv.authoritative` containing all three Windows invariants.

The in-app Codex Rook connector in this thread remained closed after killing its
stale pre-fix MCP process. A fresh Codex session should be used before treating
the in-app connector itself as refreshed.
