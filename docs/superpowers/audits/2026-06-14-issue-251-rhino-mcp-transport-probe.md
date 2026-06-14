# Issue #251 Rook MCP Transport Probe

## Purpose

The initial launch gate produced an `unverified` launch result because the Codex-wrapped Rook MCP call failed before `rhino_workbench_launch` could run. This follow-up probe tests the narrower question raised by review: whether `rhino_workbench_list` crashes the Rook server/registry path, or whether the current Codex MCP binding is stale/dead independent of the Rook server code.

## Repository State

- Branch: `codex/rhino-launch-workbench-spec`
- Starting gate artifact commit: `d431aa4 Record rhino workbench launch gate result`
- Timestamp: `2026-06-13T22:48:49.2753768-04:00`
- Unrelated untracked files left untouched:
  - `docs/rook_docs/2026-06-13-freecad-rook-bim-architecture.md`
  - `docs/rook_docs/freecad-spike/`

## Bound Runtime From Codex Config

- Codex Rook MCP config: `C:\Users\aryan\.codex\config.toml`
- Configured command: `C:/Users/aryan/AppData/Local/Rook/venv/Scripts/python.exe`
- Configured args: `["-m", "rook"]`
- Configured cwd: `C:/Users/aryan/AppData/Local/Rook/app/mcp_server`
- Configured tool timeout: `120` seconds
- Configured env includes:
  - `ROOK_INSTALL_ROOT=C:/Users/aryan/AppData/Local/Rook/app`
  - `ROOK_DATA_DIR=C:/Users/aryan/AppData/Local/Rook/data`
  - `ROOK_MODE=release`
  - `DSPY_CACHEDIR=C:/Users/aryan/AppData/Local/Rook/data/dspy-cache`
  - `CHIRP_HOME=C:/Users/aryan/AppData/Local/Rook/app/chirp`

## Process Evidence

- Before restart attempt, the Codex-owned Rook MCP process pair was:
  - PID `45624`, parent PID `57172`, parent `codex.exe`, command `"C:/Users/aryan/AppData/Local/Rook/venv/Scripts\python.exe" -m rook`
  - PID `41192`, parent PID `45624`, command `"C:\Users\aryan\AppData\Local\Rook\python\cpython-3.11.9\python.exe" -m rook`
- Both were created at `2026-06-13 19:40:16-04:00`.
- Other live Rook MCP processes belonged to Claude/Claude Code sessions and were not touched.
- Rhino PID `42648` was not touched.

## Codex-Wrapped MCP Calls

- `rhino_workbench_list` after tool metadata reload:
  - Elapsed: `0.0110` seconds
  - Result: `Transport closed`
- `rhino_instances`:
  - Elapsed: `0.0127` seconds
  - Result: `Transport closed`
- After stopping only the Codex-owned Rook MCP process pair (`45624`, `41192`) and rediscovering tools through `tool_search`, `rhino_workbench_list` still returned immediate `Transport closed`.
- Process check after stopping the pair showed no new Codex-owned `python.exe -m rook` server had been started by the tool rediscovery/call path.

## Fresh Installed-Runtime Probe

The configured installed runtime was spawned directly under a controlled stdio JSON-RPC harness with the same command, cwd, and env from Codex config.

- Command: `C:\Users\aryan\AppData\Local\Rook\venv\Scripts\python.exe -m rook`
- Cwd: `C:\Users\aryan\AppData\Local\Rook\app\mcp_server`
- Server PID: `50440`
- MCP initialize:
  - Succeeded.
  - Server info: `rook` version `1.27.2`
- `tools/call` `rhino_workbench_list`:
  - Succeeded.
  - Response payload: `{"workbenches": []}`
  - `isError`: `false`
- Process status:
  - Server was alive after the call.
  - Server exited with return code `0` after normal stdin shutdown.
- Stderr:
  - INFO-only Rook/DSPy/MCP logs.
  - No traceback.
  - No registry exception.
  - No stdout framing corruption observed.

## Fresh Repo-Runtime Probe

The current repo runtime was spawned directly under the same controlled stdio JSON-RPC harness.

- Command: `C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe -m rook`
- Cwd: `C:\Users\aryan\source\repos\Rook\mcp_server`
- Server PID: `42868`
- MCP initialize:
  - Succeeded.
  - Server info: `rook` version `1.27.1`
- `tools/call` `rhino_workbench_list`:
  - Succeeded.
  - Response payload: `{"workbenches": []}`
  - `isError`: `false`
- Process status:
  - Server was alive after the call.
  - Server exited with return code `0` after normal stdin shutdown.
- Stderr:
  - LiteLLM warnings about optional `botocore` absence.
  - INFO-only Rook/DSPy/MCP logs after startup.
  - No traceback.
  - No registry exception.
  - No stdout framing corruption observed.

## Runtime Skew Check

- Relevant installed source copies hash-match repo copies for:
  - `workbench.py`
  - `server.py`
- Installed runtime reports server version `1.27.2`; repo runtime reports `1.27.1`.
- The version skew did not affect this probe: both freshly spawned runtimes successfully initialized and returned `{"workbenches": []}` for `rhino_workbench_list`.

## Classification

- Launch-duration timeout race: refuted by the prior static comparison (`90 < 120`) and by the fact that immediate read-only calls fail through Codex before launch.
- Registry/server-death hypothesis for `rhino_workbench_list`: refuted for freshly spawned installed and repo runtimes. Both return successfully and remain alive.
- Workbench-family-only dispatch bug: refuted by `rhino_instances` also returning immediate `Transport closed` through Codex.
- Current finding: this Codex session's Rook MCP tool binding is stale/dead at the client/tool-manager transport layer. Fresh Rook MCP servers are healthy, but the current Codex tool wrapper continues to report a closed transport and did not restart a new server after the Codex-owned Rook process pair was stopped.

## Routing

- Do not implement #251 delegation from the original `unverified` launch gate.
- Do not file a Rook registry/`rhino_workbench_list` server-death issue from this evidence; the controlled server probes did not reproduce it.
- Do not ask the user to close Rhino PID `42648` for this transport diagnosis; Rhino state is not causal for the immediate Codex transport closure.
- The next actionable step is to restore the Codex-side Rook MCP binding outside this thread's current stale transport state, then rerun the approved launch gate.
- If `rhino_workbench_list` still closes transport after a fresh Codex MCP binding starts a known-version Rook server, then file a separate transport/tool-manager issue with that stderr and process-survival evidence.
