# Issue #251 Rhino Launch Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the recorded live gate classification artifact that decides whether #251 may proceed to `rhino_launch` delegation.

**Architecture:** This plan runs only the gate described in the approved design spec. It gathers static timeout facts, captures out-of-band launch evidence, performs clean Rook-owned teardown, runs the MCP-wrapped `rhino_workbench_launch` arm, conditionally runs an async direct control, and writes one classification artifact. No delegation code is edited by this plan.

**Tech Stack:** PowerShell, Git, GitHub CLI, Codex MCP tools for Rook, Python MCP server source, Windows process inspection.

---

## File Structure

- Read: `docs/superpowers/specs/2026-06-14-issue-251-rhino-launch-workbench-delegation-design.md`
- Read: `mcp_server/src/rook/server.py`
- Read: `mcp_server/src/rook/workbench.py`
- Read: `mcp_server/src/rook/rhino_launch.py`
- Create: `docs/superpowers/audits/2026-06-14-issue-251-rhino-workbench-launch-gate.md`

The audit artifact is the only repository file this gate should create. It is reviewed before any delegation implementation plan or code is allowed.

## Task 1: Confirm Baseline And Artifact Skeleton

**Files:**
- Create: `docs/superpowers/audits/2026-06-14-issue-251-rhino-workbench-launch-gate.md`

- [ ] **Step 1: Confirm the working tree and branch**

Run:

```powershell
git status -sb
git log -1 --oneline
```

Expected: record the branch, HEAD commit, and any unrelated untracked files. Do not stage or edit unrelated files.

- [ ] **Step 2: Create the audit artifact skeleton**

Add `docs/superpowers/audits/2026-06-14-issue-251-rhino-workbench-launch-gate.md` with this exact structure:

```markdown
# Issue #251 Rhino Workbench Launch Gate

## Repository State

- Branch:
- HEAD:
- Working tree notes:

## Static Timeout Comparison

- Owned launcher default readiness timeout:
- MCP client call timeout:
- Static comparison result:

## Pre-Run Snapshot

- Timestamp:
- Rhino processes:
- Rook-owned workbench sessions:
- Non-owned Rhino processes:
- Recovery or modal evidence:
- Discovery files:

## Cleanup Actions

- Rook-owned sessions closed:
- Non-owned Rhino action:
- Recovery/profile action:

## MCP-Wrapped Launch Arm

- Tool:
- Arguments:
- Start time:
- End time:
- Elapsed:
- Result or transport symptom:
- MCP server liveness after call:
- Rhino process liveness after call:
- Registry rows after call:
- Discovery/log evidence after call:
- Modal/window evidence after call:

## Short-Timeout Arm

- Run required:
- Tool:
- Arguments:
- Result:
- Evidence:

## Direct Async Control

- Run required:
- Reason:
- Baseline re-clean completed:
- Start time:
- End time:
- Elapsed:
- Result:
- Evidence:

## Classification

- Outcome:
- Rationale:
- Routing:

## Reviewer Notes

- Optional concurrent-service evidence:
- Follow-up issue required:
```

Expected: the file exists and contains only empty fields ready for captured evidence.

## Task 2: Record Static Timeout Facts

**Files:**
- Modify: `docs/superpowers/audits/2026-06-14-issue-251-rhino-workbench-launch-gate.md`

- [ ] **Step 1: Verify owned launcher default**

Run:

```powershell
rg --line-number "rhino_workbench_launch|readinessTimeoutSeconds|launch_owned_workbench" mcp_server\src\rook\server.py mcp_server\src\rook\workbench.py
```

Expected: record the `rhino_workbench_launch` default `readinessTimeoutSeconds` from `server.py` and the `launch_owned_workbench` default from `workbench.py`.

- [ ] **Step 2: Try to discover the MCP client call timeout**

Run targeted searches for explicit client timeout configuration:

```powershell
rg --line-number --hidden --glob '!**/.git/**' "Transport closed|timeout|call timeout|mcp" .codex C:\Users\aryan\.codex 2>$null
```

If this search is too broad or noisy, narrow to visible config files:

```powershell
Get-ChildItem C:\Users\aryan\.codex -Force | Select-Object Name,Length,LastWriteTime
rg --line-number --hidden --glob '!**/.git/**' "timeout|mcp" C:\Users\aryan\.codex\config.toml C:\Users\aryan\.codex\*.json 2>$null
```

Expected: record a concrete MCP client call timeout if found. If no reliable value is found, record `unknown` and state that the gate cannot classify `clear` from timing headroom.

- [ ] **Step 3: Record static comparison**

Update the artifact:

```markdown
## Static Timeout Comparison

- Owned launcher default readiness timeout: 90s from `server.py` / `workbench.py`
- MCP client call timeout: record the discovered value, or `unknown - no reliable client timeout was found`
- Static comparison result: record exactly one of `readiness >= client`, `readiness < client`, or `cannot compare because client timeout is unknown`
```

Expected: if client timeout is unknown, the artifact explicitly says unknown timeout prevents a `clear` classification unless later evidence resolves it.

## Task 3: Snapshot And Clean Rook-Owned State

**Files:**
- Modify: `docs/superpowers/audits/2026-06-14-issue-251-rhino-workbench-launch-gate.md`

- [ ] **Step 1: Snapshot Rhino processes out-of-band**

Run:

```powershell
Get-Process Rhino -ErrorAction SilentlyContinue |
  Select-Object Id,ProcessName,MainWindowTitle,StartTime,Path |
  Format-List
```

Run:

```powershell
Get-CimInstance Win32_Process -Filter "Name = 'Rhino.exe'" |
  Select-Object ProcessId,CreationDate,CommandLine |
  Format-List
```

Expected: record all Rhino PIDs, titles, start times, executable paths, and command lines that are visible.

- [ ] **Step 2: Snapshot owned workbench sessions through MCP**

Call the Rook MCP tool `rhino_workbench_list` with empty arguments.

Expected: record all returned owned sessions. If the tool call fails, record the raw failure and continue with process evidence.

- [ ] **Step 3: Snapshot discovery files**

Run:

```powershell
$paths = @(
  "$env:LOCALAPPDATA\Rook\discovery",
  "$env:TEMP\rook"
)
foreach ($p in $paths) {
  if (Test-Path $p) {
    Get-ChildItem $p -Force | Select-Object FullName,Length,LastWriteTime
  }
}
```

Expected: record discovery files relevant to Rhino native instances and workbench launch.

- [ ] **Step 4: Detect recovery or modal windows without clearing them**

Run:

```powershell
Get-Process Rhino -ErrorAction SilentlyContinue |
  Select-Object Id,MainWindowTitle |
  Format-Table -AutoSize
```

Expected: record visible titles that suggest crash recovery, error dialogs, modal prompts, or startup blockers. Do not dismiss or clear anything.

- [ ] **Step 5: Close only Rook-owned workbench sessions**

For each owned session from `rhino_workbench_list`, call the Rook MCP tool:

```json
{"session": "rhino-7000", "graceful": false}
```

using `rhino_workbench_close`.

Expected: replace `rhino-7000` with each actual owned session id and record each close result. Do not use raw `taskkill`.

- [ ] **Step 6: Stop for non-owned Rhino processes**

After closing owned sessions, rerun the process snapshot from Step 1.

Expected: if non-owned Rhino processes remain, stop and ask the user whether each PID is safe to close. Do not continue the gate until the user decides. If none remain, record that the Rook-side baseline is clean.

## Task 4: Run The MCP-Wrapped Launch Arm

**Files:**
- Modify: `docs/superpowers/audits/2026-06-14-issue-251-rhino-workbench-launch-gate.md`

- [ ] **Step 1: Capture start timestamp**

Run:

```powershell
Get-Date -Format o
```

Expected: record this as the MCP arm start time.

- [ ] **Step 2: Call MCP `rhino_workbench_launch`**

Call the Rook MCP tool `rhino_workbench_launch` with:

```json
{}
```

Expected: record the returned payload if it returns. If the transport closes and no payload returns, continue using out-of-band evidence from the remaining steps.

- [ ] **Step 3: Capture end timestamp and elapsed**

Run:

```powershell
Get-Date -Format o
```

Expected: record the end time and compute elapsed wall time from start/end timestamps.

- [ ] **Step 4: Capture server and Rhino liveness out-of-band**

Run:

```powershell
Get-Process python -ErrorAction SilentlyContinue |
  Select-Object Id,ProcessName,MainWindowTitle,StartTime,Path |
  Format-List
Get-Process Rhino -ErrorAction SilentlyContinue |
  Select-Object Id,ProcessName,MainWindowTitle,StartTime,Path |
  Format-List
```

Expected: record whether the MCP server process appears alive and whether any launched Rhino process appears alive.

- [ ] **Step 5: Capture owned sessions and discovery after call**

Call `rhino_workbench_list` if the MCP transport is still available.

Run the discovery-file command from Task 3 Step 3 again.

Expected: record registry/session rows and discovery evidence. If the MCP transport is unavailable, record that liveness/session state was unavailable through MCP and rely on filesystem/process evidence.

- [ ] **Step 6: Optional concurrent-service evidence**

If the MCP transport remains available during a long in-flight launch, call a cheap non-Rhino or meta tool such as `rhino_instances` from another client surface if available.

Expected: record whether the server services other requests. If no second client surface is available, record `not captured`.

## Task 5: Run Short-Timeout Arm If Needed

**Files:**
- Modify: `docs/superpowers/audits/2026-06-14-issue-251-rhino-workbench-launch-gate.md`

- [ ] **Step 1: Decide whether short-timeout arm is needed**

Run this arm when the default MCP launch arm blocks, fails ambiguously, or returns a timeout-like symptom.

Expected: record `Run required: yes` or `Run required: no` with one sentence.

- [ ] **Step 2: Re-clean to baseline if running**

Repeat Task 3 cleanup before this arm.

Expected: record that owned sessions were closed and non-owned Rhino handling was resolved.

- [ ] **Step 3: Call MCP `rhino_workbench_launch` with short timeout**

Call:

```json
{"readinessTimeoutSeconds": 3}
```

Expected: a healthy wrapper should return a structured workbench readiness failure or success quickly. Record payload, elapsed time, and out-of-band process/discovery evidence.

## Task 6: Run Direct Async Control If Triggered

**Files:**
- Modify: `docs/superpowers/audits/2026-06-14-issue-251-rhino-workbench-launch-gate.md`

- [ ] **Step 1: Determine trigger**

Run the direct control when:

- MCP arm failed;
- MCP arm was ambiguous;
- MCP arm succeeded without obvious headroom against known timeout constants;
- MCP client timeout is unknown.

Expected: record the trigger reason. Unknown client timeout is sufficient reason.

- [ ] **Step 2: Re-clean to baseline**

Repeat Task 3 cleanup before the direct control.

Expected: record that the control starts from the same baseline as the MCP arm.

- [ ] **Step 3: Run equivalent async in-process control**

Run:

```powershell
$env:PYTHONPATH = "$PWD\mcp_server\src"
@'
import asyncio
import json
import time
from rook import workbench

async def main():
    start = time.perf_counter()
    result = await workbench.launch_owned_workbench()
    elapsed = time.perf_counter() - start
    print(json.dumps({"elapsed_seconds": round(elapsed, 3), "result": result}, indent=2))

asyncio.run(main())
'@ | & mcp_server\.venv\Scripts\python.exe -
```

Expected: record elapsed and result. This control localizes whether the owned launcher itself works in an async context; it does not by itself classify the transport mechanism.

## Task 7: Classify And Stop

**Files:**
- Modify: `docs/superpowers/audits/2026-06-14-issue-251-rhino-workbench-launch-gate.md`

- [ ] **Step 1: Select the classification**

Pick exactly one:

- `clear`
- `unverified`
- `client_timeout`
- `event_loop_starvation`
- `server_death`
- `recovery_modal_222`

Expected: the artifact includes the selected outcome and a rationale tied to evidence.

- [ ] **Step 2: Record routing**

Use the approved routing rule:

- `clear`: proceed with #251 delegation after reviewer approval;
- `recovery_modal_222`: route evidence to #222 and proceed with #251 delegation after reviewer approval;
- `client_timeout`, `event_loop_starvation`, or `server_death`: file a separate issue and do not ship a blocking alias unless the transport fix preserves `launch_owned_workbench()`'s return contract;
- `unverified`: hold implementation unless the user explicitly accepts the risk.

Expected: the artifact states the next step.

- [ ] **Step 3: Leave machine clean**

Close any Rook-owned workbench sessions created by the gate through `rhino_workbench_close`.

Expected: no Rook-owned workbench sessions remain unless the artifact explicitly says cleanup was impossible and why. Non-owned Rhino processes are not touched without user approval.

- [ ] **Step 4: Commit the gate artifact**

Run:

```powershell
git add -- docs/superpowers/audits/2026-06-14-issue-251-rhino-workbench-launch-gate.md
git commit -m "Record rhino_workbench_launch gate classification"
```

Expected: commit contains only the gate artifact. Stop after this commit and present the artifact for review. Do not edit delegation code.
