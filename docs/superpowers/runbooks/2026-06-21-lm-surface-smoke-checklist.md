# LM Live-Smoke Checklist (pre-LM2E)

Manual/diagnostic checkpoint after LM2A–D. Run the steps in order; each gate
must pass before the next is meaningful. The script is a diagnostic only — it
deploys nothing and starts/stops nothing. You run the deploy, Rhino, and
RookChat steps.

Deployed venv interpreter (used for every script command below):
`C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe`

---

## Gate 0 — Fresh release deploy (manual)

The deployed runtime must contain LM2A–D before anything else.

1. Close Rhino and stop the rook MCP (so the deploy can recreate the venv).
2. From the repo, run the release deploy:
   `pwsh -File scripts/deploy-local-testing.ps1` (release mode).
3. Restart Rhino.

**PASS:** the deploy completes and its own release verification passes
(`rook.server.__file__` under site-packages; all seven `rhino_2d_to_3d_*`
tools advertised). **FAIL:** the deploy errors or its verification fails — fix
the deploy before continuing.

---

## Gate 1 — Coherence

```powershell
$env:PYTHONPATH=""; & "C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe" "C:/UDEV/Rook/scripts/lm_surface_smoke.py" coherence
```

**Expected evidence:** prints `PYTHONPATH=''`, `sys.prefix` under
`…/Rook/venv`, and a `…__file__` line for `rook`, `rook.server`, and each of the
four LM2 modules — every path under `…/Rook/venv/Lib/site-packages/rook`.

**PASS:** final line `PASS: all LM2 modules import from deployed site-packages`
(exit 0). **FAIL:** any `FAIL:` line — a module is absent, failed to import, or
resolved from repo source (split-brain) — or a non-empty `PYTHONPATH`. Re-run
Gate 0.

### Gate 1b — Chat runtime currency (manual)

Open RookChat and confirm the model dropdown populates (cloud + local models).
An empty dropdown means a stale AppData chat runtime (no `/agent/chat/models`)
— redeploy / clear the shadowing `RookChatService.json`. **PASS:** dropdown
populates. **FAIL:** empty dropdown.

---

## Gate 2 — Surface evidence

```powershell
$env:PYTHONPATH=""; & "C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe" "C:/UDEV/Rook/scripts/lm_surface_smoke.py" surface
```

**Expected evidence:** the origin guard lines (as Gate 1), then a catalog tool
count, the readonly profile name/intended/active counts, a `registry_findings
by code` histogram, and the profile-findings count.

**PASS:** final line `PASS: surface evidence smoke passed` (exit 0) — the
readonly MCP-only exclusion holds (`gh_exploration`, `gh_knowledge`,
`gh_validation` excluded), no catalog-present group failed to activate, and the
cache (if present) does not drift on a required tool.
**DEGRADED:** a `DEGRADED:` cache-absent line is informational, not a failure —
the surface was still built from the live `list_tools()`.
**WARNING:** a `WARNING:` cache-drift line on non-required tools — note it, not a
failure.
**FAIL:** any `FAIL:` line (empty catalog, broken exclusion, a catalog-present
group failing to activate, or cache drift on a required tool).

---

## Gate 3 — GH C# repair canary (manual, RookChat)

Through RookChat:

1. Ask it to create a C# Grasshopper script with a deliberate compile error —
   e.g. an output pin `A` (double) set from an undefined symbol:
   "Create a C# script component with output A (double) where `A = nope + 1;`."
2. Inspect the create result: confirm `data.script_receipt` is present with
   `mutation`, `verification`, `artifact_status`, and `repair_anchor`.
3. Ask it to repair: "Set `A = 42.0;` instead."
4. Confirm the receipt's `artifact_status` reaches `usable` and `gh_errors` is
   clean.

**PASS:** receipt present on create, repair reaches `usable`, errors clean.
**FAIL:** receipt absent or repair does not reach `usable`.

### Optional complement (assistant-run, once Rhino is up)

The assistant can cross-check the deployed GH C# path at the MCP-tool level
(`gh_create_csharp_script` → `gh_update_script` → `gh_errors`) for a
deterministic second data point. This complements — does not replace — the
manual RookChat run above.

---

## Outcome summary

Record per gate: `PASS` / `FAIL` / `DEGRADED` / `WARNING`. Gate 0 and Gate 1
are hard gates (must pass). Gate 2 `DEGRADED`/`WARNING` are acceptable to
proceed with a note. Any `FAIL` blocks the LM2E start until resolved.
