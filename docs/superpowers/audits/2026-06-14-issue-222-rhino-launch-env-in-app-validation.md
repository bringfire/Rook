# Issue 222 In-App Rhino Launch Env Validation

Date: 2026-06-14
Branch: `codex/rhino-launch-workbench-spec`

## Scope

Validate the in-app Codex Rook MCP connector path for issue #222 after the local stdio proof. This validation did not run the issue #251 clean-state gate.

## Repository State

`git branch --show-current`:

```text
codex/rhino-launch-workbench-spec
```

`git status --short` before validation:

```text
```

`git log --oneline --decorate -6`:

```text
7c679662 (HEAD -> codex/rhino-launch-workbench-spec) Record Rhino launch env live proof
1dd4d102 Apply controlled env to owned Rhino launches
0bd5ad11 Harden Rhino launch environment construction
c8d92004 Plan Rhino launch env hardening
b46d65f6 Clarify Rhino launch env verification design
e8f3f9be Document Rhino launch environment hardening design
```

## In-App MCP Validation

Initial `rhino_workbench_list` returned normally:

```json
{
  "workbenches": []
}
```

`rhino_workbench_launch` with `{"readinessTimeoutSeconds": 90}` succeeded:

```json
{
  "session": "rhino-64584",
  "processId": 64584,
  "port": 62674,
  "owned": true,
  "mode": "workbench",
  "boundInSeconds": 23.14,
  "evidence": {
    "requestedScheme": "RookWorkbench",
    "activeScheme": null,
    "isolationMode": "default",
    "discoveryRecordPath": "C:\\Users\\aryan\\AppData\\Local\\Rook\\discovery\\instance-64584-native.json",
    "discoveryLogSeen": true,
    "windows": [],
    "visibleWindowCount": 0,
    "emptyTitleWindowPresent": false,
    "exitCode": null,
    "argv": [
      "C:\\Program Files\\Rhino 8\\System\\Rhino.exe",
      "/nosplash"
    ],
    "elapsedSeconds": 23.17200000002049,
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
  }
}
```

`rhino_workbench_close`:

```json
{
  "session": "rhino-64584",
  "owned": true,
  "mode": "workbench",
  "closed": true,
  "cleanupStatus": "graceful_exit",
  "discardedUnsavedChanges": false
}
```

Final `rhino_workbench_list`:

```json
{
  "workbenches": []
}
```

`Get-Process -Id 64584 -ErrorAction SilentlyContinue` returned no process.

## Classification

`in_app_clear`
