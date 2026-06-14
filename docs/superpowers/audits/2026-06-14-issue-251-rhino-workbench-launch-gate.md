# Issue #251 Rhino Workbench Launch Gate

## Repository State

- Branch: `codex/rhino-launch-workbench-spec`
- HEAD: `167e430 Clarify rhino launch gate evidence plan`
- Working tree notes:
  - This artifact is the only intended tracked addition from the gate run.
  - Pre-existing unrelated untracked files were left untouched:
    - `docs/rook_docs/2026-06-13-freecad-rook-bim-architecture.md`
    - `docs/rook_docs/freecad-spike/`

## Static Timeout Comparison

- Owned launcher default readiness timeout: 90 seconds.
  - Source: `mcp_server/src/rook/workbench.py` defines `launch_owned_workbench(readiness_timeout_seconds: int = 90)`.
  - Tool schema and dispatcher also use default 90 at `mcp_server/src/rook/server.py`.
- MCP client call timeout: 120 seconds for the same Codex Rook MCP client.
  - Source: `C:\Users\aryan\.codex\config.toml`, `[mcp_servers.rook]`, `tool_timeout_sec = 120`.
- Static comparison result: readiness timeout is lower than the client tool timeout (`90 < 120`), so the simple "owned launcher can block longer than the client allows" mechanism is not shown by static constants.

## Pre-Run Snapshot

- Timestamp:
  - Process/discovery evidence captured around `2026-06-13T22:06:38.7662831-04:00` (`2026-06-14T02:06:38Z`).
  - OS boot time: `2026-06-12 21:53:54-04:00`.
- Cold/warm:
  - Not cold. A Rhino process was already running before the gate could launch anything.
- Rhino processes:
  - `Rhino.exe` PID `42648`
  - Start time: `2026-06-13 21:50:48-04:00`
  - Command line: `"C:\Program Files\Rhino 8\System\Rhino.exe"`
  - Window title: `Rhino 8 Commercial - [Perspective]`
- Rook-owned workbench sessions:
  - Could not be enumerated. The MCP-wrapped ownership query `rhino_workbench_list` closed the transport immediately.
- Non-owned Rhino processes:
  - PID `42648` must be treated as non-owned until the Rook owned-session registry can be read successfully.
  - No automatic close or kill was performed.
- Recovery or modal evidence:
  - No recovery-modal evidence was observed from `tasklist /v` or `Get-Process`; visible title was `Rhino 8 Commercial - [Perspective]`.
  - No crash-recovery or profile state was cleared.
- Discovery files:
  - Discovery folder resolved through `rook.bridge.resolve_discovery_folder()` to `C:\Users\aryan\AppData\Local\Rook\discovery`.
  - Focused files for PID `42648`:
    - `instance-42648-native.json`, last write `2026-06-13 21:51:38-04:00`
    - `native-discovery-42648.log`, last write `2026-06-13 21:51:38-04:00`
    - `companion-42648.json`, last write `2026-06-13 21:51:38-04:00`
    - `companion-load-42648.log`, last write `2026-06-13 21:51:35-04:00`
  - `instance-42648-native.json` reports:
    - `processId`: `42648`
    - `port`: `58522`
    - `pluginType`: `native`
    - `pluginVersion`: `1.5.12`
    - `native.core`, `native.command_control`, and `gh.bridge` ready.
  - Out-of-band HTTP evidence:
    - `GET http://127.0.0.1:58522/ping` returned HTTP 200 with `{"data":"pong","success":true}`.
    - `GET http://127.0.0.1:58522/capabilities` returned HTTP 200.

## Cleanup Actions

- Rook-owned sessions closed:
  - None. The required owned-session list call failed before ownership could be determined.
- Non-owned Rhino action:
  - None. PID `42648` was left running because it could be a user session with unsaved work.
- Recovery/profile action:
  - None. Recovery/profile state was detected-only per the approved gate protocol.

## MCP-Wrapped Launch Arm

- Cold/warm at arm start:
  - Not reached. The pre-launch MCP ownership/liveness check failed first.
- Tool:
  - Intended launch arm: `rhino_workbench_launch`.
  - Actual pre-launch check attempted: `rhino_workbench_list`.
- Arguments:
  - `rhino_workbench_list`: none.
- Start time:
  - Second reproduced check occurred after tool metadata reload during this gate run.
- End time:
  - Immediate.
- Elapsed:
  - Reported wall time: `0.0110 seconds`.
- Result or transport symptom:
  - `tool call error: tool call failed for rook/rhino_workbench_list`
  - Cause: `Transport closed`
  - This same symptom was also seen on the first `rhino_workbench_list` attempt before any workbench launch request was issued.
- MCP server liveness after call:
  - Exact Codex-bound MCP server process could not be identified from process names alone.
  - Multiple `python.exe -m rook` processes were still alive out-of-band after the transport closed, including installed AppData runtimes and the repo `.venv` runtime.
  - Because the exact stdio peer was not identified, this does not prove the peer process survived.
- Rhino process liveness after call:
  - PID `42648` remained alive.
  - Native Rook endpoint on port `58522` responded to `/ping` and `/capabilities`.
- Registry rows after call:
  - Could not read the MCP owned-session registry via `rhino_workbench_list` because transport closed.
  - Discovery files for PID `42648` remained present.
- Discovery/log evidence after call:
  - Focused discovery files for PID `42648` remained unchanged from startup.
- Modal/window evidence after call:
  - Visible Rhino title remained `Rhino 8 Commercial - [Perspective]`.
  - No recovery-modal evidence was observed from the process/window-title checks performed.

## Short-Timeout Arm

- Run required:
  - No.
- Tool:
  - Not run.
- Arguments:
  - Not applicable.
- Result:
  - Not applicable.
- Evidence:
  - The MCP wrapper was already closing on `rhino_workbench_list`, and a non-owned Rhino process remained present. Running a short-timeout launch arm would violate the clean-state gate protocol and would not classify the intended launch behavior.

## Direct Async Control

- Run required:
  - No.
- Reason:
  - The MCP launch arm did not run, so there was no launch-arm failure, ambiguity, or no-headroom success to control against.
  - The baseline was not clean because PID `42648` remained present and could not be classified as owned through the broken MCP wrapper.
- Baseline re-clean completed:
  - No; stopped before any destructive cleanup.
- Start time:
  - Not applicable.
- End time:
  - Not applicable.
- Elapsed:
  - Not applicable.
- Result:
  - Not applicable.
- Evidence:
  - Direct control would have been contaminated by the already-running Rhino process and would not isolate the MCP wrapper variable.

## Classification

- Outcome: `unverified`
- Rationale:
  - The approved gate requires an MCP-wrapped `rhino_workbench_launch` from clean state.
  - Clean state was not achieved because PID `42648` was already running and had to be treated as non-owned until the owned-session registry could be read.
  - The required MCP ownership/liveness call `rhino_workbench_list` failed twice with immediate `Transport closed`, before any workbench launch request was issued.
  - Static timeout constants do not explain this pre-launch failure (`readinessTimeoutSeconds` default 90 seconds; Codex Rook MCP `tool_timeout_sec` 120 seconds).
  - Rhino itself was not wedged by the evidence collected: its native endpoint responded out-of-band, and no recovery-modal window title was observed.
  - Because the failure is pre-launch and the exact MCP stdio peer was not identified, this run cannot classify `rhino_workbench_launch` as `clear`, `client_timeout`, `event_loop_starvation`, `server_death`, or `recovery_modal_222`.
- Routing:
  - Per the approved spec, do not implement #251 delegation from this artifact unless the user explicitly accepts the `unverified` risk.
  - Restore or restart the Rook MCP transport, then rerun the gate from a clean state.
  - Before rerun, the user must decide whether Rhino PID `42648` is safe to close; it was not closed automatically.

## Reviewer Notes

- Optional concurrent-service evidence:
  - Not captured through MCP because the MCP transport closed before the launch arm.
  - Out-of-band HTTP evidence shows the existing Rhino/Rook native endpoint was healthy during the MCP failure.
- Follow-up issue required:
  - Not yet filed from this artifact alone. The observed failure is a pre-launch MCP transport precondition failure, not a classified `rhino_workbench_launch` gate result.
  - If the same immediate `rhino_workbench_list` transport closure reproduces after MCP restart with no stale/non-owned Rhino state, it should be tracked separately from #251.
