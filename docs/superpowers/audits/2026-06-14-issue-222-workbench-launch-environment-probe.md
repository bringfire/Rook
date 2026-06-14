# Issue #222 Workbench Launch Environment Probe

## Purpose

Issue #251's launch gate found an MCP-wrapped `rhino_workbench_launch` failure:
`workbench_exited_before_bind`, Rhino PID `54396`, exit code `3762504530`
(`0xE0434352`). The direct async control succeeded. This probe isolates the
parent-environment difference before any #251 delegation code is written.

## Repository State

- Branch: `codex/rhino-launch-workbench-spec`
- Starting commit: `58a37e2 Record rhino_workbench_launch gate classification`
- Timestamp: `2026-06-14T00:58:39.9160381-04:00`
- Unrelated untracked files left untouched:
  - `docs/rook_docs/2026-06-13-freecad-rook-bim-architecture.md`
  - `docs/rook_docs/2026-06-13-spatial-intelligence-foundation.md`
  - `docs/rook_docs/freecad-spike/`

## Source Finding

`launch_owned_workbench()` does not pass a controlled environment to Rhino:

- `workbench.py` calls `start_rhino_process(..., env=None, popen=lambda argv: subprocess.Popen(argv))`.
- The `popen` override drops the `env` argument entirely, so Rhino inherits the
  full parent process environment from whichever process called the launcher.
- In the MCP arm, that parent is the Codex-launched Rook MCP process.
- In the direct async control, that parent is the shell/control process.

This makes the MCP-fails/direct-succeeds differential environment-conditioned.

## Real CLR Exception

Windows Application Event Log for the original gate failure window:

- Time: `2026-06-13 23:18:17-04:00`
- Provider: `.NET Runtime`
- Event ID: `1026`
- Application: `Rhino.exe`
- CoreCLR: `8.0.2826.26413`
- .NET: `8.0.28`
- Exception: `System.TypeInitializationException`
- Type initializer: `MS.Internal.FontCache.Util`
- Inner exception: `System.UriFormatException: Invalid URI: The format of the URI could not be determined.`
- Stack includes:
  - `MS.Internal.FontCache.Util..cctor()`
  - `System.Windows.Media.FontFamily.get_Baseline()`
  - `Eto.Wpf.Forms.ApplicationHandler.Initialize()`
  - `RhinoWindows.Runtime.Initialization.Start(String s)`
  - `dotnetstart.DotNetInitialization.InitializeRhino(String args)`

The controlled repro below emitted the same `.NET Runtime` event at
`2026-06-14 00:56:36-04:00`.

## Environment Delta

The current shell environment and the Codex-owned Rook MCP server environments
were read directly from live process memory. The old gate pair (`42628`/`44156`)
and current pair (`56640`/`45572`) matched for the relevant variables.

Relevant shell values:

- `windir=C:\Windows`
- `SystemRoot=C:\Windows`
- `PYTHONPATH=C:\Program Files\Chaos\V-Ray\AppSDK/python`
- `ROOK_PROJECT_ROOT=C:\Users\aryan\source\repos\Rook`

Relevant Codex Rook MCP values:

- `windir` absent
- `SYSTEMROOT=C:\Windows`
- `PYTHONHOME=` (present but empty)
- `PYTHONPATH=` (present but empty)
- `ROOK_INSTALL_ROOT=C:/Users/aryan/AppData/Local/Rook/app`
- `ROOK_DATA_DIR=C:/Users/aryan/AppData/Local/Rook/data`
- `ROOK_MODE=release`
- `ROOK_DSPY_RESTRICT_PICKLE=1`
- `CHIRP_HOME=C:/Users/aryan/AppData/Local/Rook/app/chirp`
- `DSPY_CACHEDIR=C:/Users/aryan/AppData/Local/Rook/data/dspy-cache`

Because the successful probe below keeps `PYTHONHOME=`, `PYTHONPATH=`, the Rook
vars, and the MCP `PATH` unchanged, those are not the discriminating variables.
The discriminating variable is `windir`.

## Probe A: Direct Control With MCP Env As-Is

Setup:

- Source env PID: `56640` (`python.exe -m rook`, parent `codex.exe`)
- Probe runner: repo `.venv` Python
- Launcher: `await workbench.launch_owned_workbench(readiness_timeout_seconds=60)`
- Environment: captured MCP env as-is, with `windir` absent.

Result:

```json
{
  "elapsed_seconds": 11.136,
  "result": {
    "success": false,
    "data": {
      "code": "workbench_exited_before_bind",
      "message": "Rhino exited with code 3762504530 before RookNative discovery appeared",
      "processId": 43240,
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
        "elapsedSeconds": 11.09299999999348,
        "diagnosticHint": null
      },
      "cleanupStatus": "forced_kill"
    }
  }
}
```

No `Rhino.exe` process remained after the failed launch.

## Probe B: Same MCP Env Plus `windir`

Setup:

- Same captured MCP env as Probe A.
- Only change: add `windir=C:\Windows`.
- Launcher: `await workbench.launch_owned_workbench(readiness_timeout_seconds=90)`.

Result:

```json
{
  "elapsed_seconds": 38.843,
  "result": {
    "success": true,
    "data": {
      "session": "rhino-44372",
      "processId": 44372,
      "port": 59127,
      "owned": true,
      "mode": "workbench",
      "boundInSeconds": 38.8
    }
  }
}
```

The probe closed the owned session through `close_owned_workbench(..., graceful=True)`:

```json
{
  "success": true,
  "data": {
    "session": "rhino-44372",
    "closed": true,
    "cleanupStatus": "graceful_exit",
    "discardedUnsavedChanges": false,
    "owned": true,
    "mode": "workbench"
  }
}
```

Discovery evidence for PID `44372`:

- `native-discovery-44372.log` was written and then removed its
  `instance-44372-native.json` on unload.
- `companion-load-44372.log` was written.
- No live `Rhino.exe` process remained after cleanup.

## Classification

Confirmed root cause:

- `rhino_workbench_launch` inherits an MCP parent environment that lacks
  `windir`.
- Rhino's .NET/WPF/Eto startup requires `windir` for font/cache URI
  initialization.
- Without `windir`, Rhino exits before RookNative discovery with CLR code
  `0xE0434352` and `.NET Runtime` event `MS.Internal.FontCache.Util` /
  `System.UriFormatException`.
- Restoring only `windir=C:\Windows` to the same MCP environment makes the owned
  launcher bind successfully and close cleanly.

This is a launcher-environment hardening bug, not a transport timeout and not a
registry/server-death bug.

## Routing

- Route to #222 launcher hardening.
- Do not implement #251 delegation until the owned launcher environment fix lands
  and the approved #251 gate reruns cleanly.
- The expected fix is internal and should preserve the `LaunchOutcome` return
  contract, so #251 remains sequenced behind this fix rather than redesigned.

Implementation trap to preserve:

- Passing a sanitized env only to `start_rhino_process(..., env=...)` is
  insufficient while `workbench.py` supplies `popen=lambda argv:
  subprocess.Popen(argv)`.
- The fixed launch path must pass the controlled environment through the
  `subprocess.Popen(..., env=controlled_env)` lambda, while preserving the local
  test patching pattern.
