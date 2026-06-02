# Tester Brief — Rook GH Locked-Solver Crash Fix (live verification)

> Paste everything below the line into a **fresh Claude session that has a working Rook MCP
> connection** (open Rhino + Grasshopper first). It is self-contained — the tester needs no
> prior context. When done, paste its **REPORT BACK** section back to the requesting session.

---

You are verifying a **crash fix** in Rook. Previously, **locking the Grasshopper solver and then
asking Rook to update a GH script crashed Rhino instantly** (a synchronous `ExpireSolution(true)`
re-entered Grasshopper's non-reentrant solver). The fix defers the solve when the solver is locked.
A freshly built companion (deployed 18:19) and updated Python are loaded. Your job: **prove the
crash is gone** and report specific data back.

## SAFETY — read first
- Use a **brand-new throwaway Grasshopper document**. Do NOT open or modify any real/important file.
- This test deliberately reproduces the crash trigger. **If Rhino crashes, the fix is not active —
  stop and report that.**
- You cannot click the Grasshopper UI; when a step needs the solver locked/unlocked, **ask the user
  to do it and wait for confirmation.**

## Step 0 — Preflight (confirms the NEW build is loaded)
1. Call `rhino_ping` → expect a pong.
2. Call `gh_status`. **Check whether the response includes the NEW solver fields:**
   `solverEnabled`, `solverStateKnown`, `solutionState`.
   - **Present** → new companion is loaded; continue.
   - **Absent** → the OLD companion is still loaded (Rhino cached the old plugin). **STOP.** Tell the
     user to fully quit Rhino and reopen it, then restart you. Report this outcome.
   - Paste the full `gh_status` JSON into your report.

## Step 1 — Create a throwaway script component
Call:
```
gh_create_script(
  language="csharp",
  code="A = Convert.ToDouble(R);",
  pins_in=[{"name":"R","type":"double"}],
  pins_out=[{"name":"A","type":"double"}],
  name="LockedSolverCrashTest", x=400, y=300
)
```
Record the returned component **GUID**.

## Step 2 — THE CRITICAL REGRESSION (faithful repro of the crash)
1. **Ask the user to LOCK the solver** in the Grasshopper UI: menu **Solution → Lock Solver**
   (the padlock). Wait until they confirm it is locked.
2. Call `gh_update_script(guid=<GUID>, language="csharp", code="A = Convert.ToDouble(R) * 3.0;")`.
3. **Immediately** call `rhino_ping`.
4. Read the source back: `gh_set_script(guid=<GUID>)` (no `script` argument = read).

**Expected if the fix works:**
- Rhino does **not** crash; `rhino_ping` still returns a pong.
- The `gh_update_script` response has **`verification_deferred: true`** and **`solver_locked: true`**
  (or `solver_state_known: false`), and does **not** claim a clean compile.
- The read-back source contains **`* 3.0`** (the source was written even though it was not recomputed).

**If Rhino crashed or `rhino_ping` fails after step 2 → the fix did not take. Report immediately**
(include whether Step 0 showed the new solver fields).

## Step 3 — Unlock and confirm normal behavior is intact
1. **Ask the user to UNLOCK the solver** (toggle Solution → Lock Solver off). Wait for confirmation.
2. Call `gh_update_script(guid=<GUID>, language="csharp", code="A = Convert.ToDouble(R) + 1.0;")`.
3. **Expected:** a normal response — **not** `verification_deferred`; `component_errors` present
   (an actual compile/error check ran). The component should recompute.

## Step 4 — OPTIONAL probe U1 (only if the requester asks; helps finalize an automated test)
With the solver **UNLOCKED**, call `rhino_execute` with:
```python
import Grasshopper as gh
import System.Reflection as R
doc = gh.Instances.ActiveCanvas.Document
T = doc.GetType()
def rd(n, s=False):
    try:
        f = R.BindingFlags.Public | (R.BindingFlags.Static if s else R.BindingFlags.Instance)
        p = T.GetProperty(n, f)
        return "<none>" if p is None else p.GetValue(None if s else doc)
    except Exception as e:
        return "ERR:%s" % e
print("EnableSolutions(static)=", rd("EnableSolutions", True),
      "| Enabled=", rd("Enabled"),
      "| SolutionState=", rd("SolutionState"),
      "| SolutionDepth=", rd("SolutionDepth"))
```
Then ask the user to **LOCK** the solver, run the same snippet again, and report **which value(s)
changed `True`→`False`** when locked. (That identifies the real "lock" member.)

> Probes U2 (pin-description clobber timing) and U3 (solve-completion marker) are **deferred
> follow-ups** — not needed for this verification. Skip unless explicitly asked.

## REPORT BACK (paste this whole section to the requesting session)
1. **Step 0:** Did `gh_status` include `solverEnabled` / `solverStateKnown` / `solutionState`? Paste the JSON.
2. **Step 2 (CRITICAL):** Did Rhino survive (pong after)? Paste the full `gh_update_script` response —
   especially `verification_deferred`, `solver_locked`, `solver_state_known`. Did the source round-trip (`* 3.0` present on read-back)?
3. **Step 3:** Did the unlocked update behave normally (no `verification_deferred`, compile/errors checked)?
4. **Step 4 (if run):** Which member flipped `True`→`False` on lock (`EnableSolutions` static and/or `Enabled` instance)?
5. Anything unexpected (errors, dialogs, slow responses, etc.).
