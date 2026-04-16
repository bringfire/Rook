# Phase D handoff — #28 block basePoint UserData migration

**Date:** 2026-04-15
**Issue:** [#28](https://github.com/bringfire/Rook/issues/28)
**Branch:** `fix/block-basepoint-userdata-migration` (off `main` at `7429895`)
**Status at handoff:** Phases A–C complete + Codex-approved. Phase D + E remain.

This document exists so a fresh Claude session can resume without re-reading the full design discussion, the implementation arc, or the mid-session diagnostic logs.

## Branch state

| Commit | Scope |
|---|---|
| `c036376` | Phase A — scaffold Rook-owned basePoint UserData class on native and managed sides |
| `519f8fa` | Phase B — dual-write basePoint metadata to new userdata slot in native (amended after Codex scope-slip review) |
| `874984a` | Phase C — prefer new basePoint userdata over legacy fallback on read |

Branch is **not yet pushed** to remote. Open a PR only after Phase E.

**6 live-Rhino tests green as of last verification** (commit `874984a`, 37.4s):
- `test_origin_basepoint_replace_passes_through` (PR #32)
- `test_non_origin_basepoint_plain_geometry_zero_drift` (PR #32)
- `test_nested_block_instance_source_composes_xform` (PR #32)
- `test_batch_per_group_basepoint_independent_normalization` (PR #32)
- `test_new_slot_populated_on_block_create` (Phase B)
- `test_disagreement_new_slot_wins` (Phase C — native-scoped)

## Key artifacts

- **Design doc:** `docs/plans/2026-04-15-block-basepoint-metadata-userdata-migration-design.md` (gitignored on main; travels with final commit per user decision)
- **Implementation plan (Codex):** `docs/plans/2026-04-15-block-basepoint-metadata-userdata-migration-plan.md` (gitignored)
- **UUID (load-bearing):** `0CD9F899-C9AA-4FC5-8F45-E081409245E9` — identical on native `ON_UUID` constant and C# `[Guid]`. Both sides MUST keep this value verbatim.
- **Rook-owned files:**
  - `src/RookNative/UserData/RookBlockBasePointUserData.{h,cpp}`
  - `src/Rook/UserData/RookBlockBasePointUserData.cs`
- **Test support:**
  - Native internal route `POST /block/_debug/basepoint-userdata` — reads the new slot (Phase B)
  - Native internal route `POST /block/_debug/set-legacy-basepoint` — writes ONLY the legacy user-string, leaves new slot alone (Phase C)
  - Both routes are OFF MCP. Helpers `assert_new_slot` and `set_legacy_basepoint_for_test` live in `mcp_server/tests/conftest.py` and hit them directly via `httpx`.

## Doubts and gaps going into Phase D

### Verified

| Invariant | Verified by |
|---|---|
| Native dual-write on `rhino_block_create` | test 5 (introspection + behavior) |
| Native dual-write on `rhino_block_duplicate` | *implicit — test 7 in Phase D will validate* |
| Native read switches to new-first | test 9 via `rhino_block_replace_geometry` |
| Pre-migration legacy-only reads still work | 4 PR #32 regression tests (none of them have the new slot) |
| New slot survives dual-write through all callsites of `StoreDefinitionBasePoint` | by construction — single helper handles both slots, post-condition enforced via `CRookBlockBasePointUserData::Attach` detach-then-attach-fresh |

### Unverified (Phase D targets)

| Gap | Tested by in Phase D |
|---|---|
| **`.3dm` save/load round-trip** — new slot survives close + reopen | test 6 `test_save_load_roundtrip_preserves_basepoint` |
| **HandleBlockDuplicate** — source's basePoint carries to the new idef | test 7 `test_block_duplicate_carries_basepoint` |
| **UpdateDefinitionBasePoint (rebase)** — slice-copy + `ModifyInstanceDefinition(idef_userdata_setting)` actually carries the new UserData through to the live table entry | test 8 `test_block_rebase_updates_new_slot` |
| **Preserve sites** — SDK preserves UserData through `ModifyInstanceDefinitionGeometry` on add-objects / remove-objects / replace-geometry | test 10 `test_preserve_sites_retain_basepoint` |
| **Mask-audit sites** — `HandleBlockRename`, `HandleBlockUnlink` use a mask that preserves attached UserData | code-reading during Phase D (no live test) |
| **Intended-rule audit sites** — `HandleBlockRefresh`, `HandleBlockMerge` behave as documented in design §3.4 | code-reading + inline comments during Phase D |
| **`HandleBlockLink`** — does NOT synthesize origin UserData for externally-authored linked defs | code-reading |

### Known limitations (documented, not fixed)

1. **`InstanceDefinition.UserData` doesn't surface plugin-defined custom UserData to managed callers in RhinoCommon 8.0.23304.** Diagnosed via `rhino_execute` Python probe during Phase C:
   - `idef.UserData.Contains(UUID)` returns `True` (slot IS present on native)
   - `idef.UserData[i]` returns `None` (no managed wrapper)
   - `idef.UserData.Add(managed_ud)` returns `False`
   - `UserData.RegisterType` (internal, via reflection) did NOT change this

   **Consequence:** managed `TryReadDefinitionBasePoint` new-first code is **graceful-degrade only** — always falls through to the PR #30 reflection-bridge legacy-string path. Zero behavior change vs PR #30 on managed side. The code keeps the new-first shape so the day RhinoCommon exposes the missing surface, managed reads upgrade automatically.

   Documented in:
   - Commit message on `874984a`
   - `src/Rook/RookPlugin.cs:81–97` (inline comment)
   - Test comment in `test_disagreement_new_slot_wins`

2. **Managed disagreement-wins is unverified** during this transition window. Test 9 was narrowed to the native path (`rhino_block_replace_geometry`) for this reason. Companion-path disagreement coverage is deferred to follow-up #34 where legacy retirement also requires solving the managed read gap.

3. **Rebase carry-through of the new UserData through slice-copy + `ModifyInstanceDefinition` is an assumption.** The helper uses `ON_InstanceDefinition::idef_userdata_setting` mask on native; the assumption is that the SDK's `operator=` carries UserData (since `m_userdata_copycount = 1` in the ctor) AND that the mask preserves it on the live entry. **Test 8 is the decider.** If test 8 fails, plan Phase B step 2 says to escalate `UpdateDefinitionBasePoint` to direct-attach-on-live-entry:
   ```cpp
   // After ModifyInstanceDefinition succeeds:
   CRhinoInstanceDefinition* pLive = const_cast<CRhinoInstanceDefinition*>(
       pDoc->m_instance_definition_table[idefIndex]);
   if (pLive) CRookBlockBasePointUserData::Attach(*pLive, newBasePoint);
   ```

### Pre-existing repo state unrelated to this PR

Branch has three uncommitted modifications on `main` (from before this work started):
- `.agents/skills/project-setup/SKILL.md`
- `.claude/skills/project-setup/SKILL.md`
- `knowledge/gh/operations_knowledge.json`

Plus a file that auto-generated during a Phase C `rhino_execute` diagnostic run:
- `knowledge/gh/notes/teaching_d9d15b6e.json`

**None of these belong in this PR.** Keep them staged as `M`/untracked but never `git add` them. Phase D + E commits should use targeted `git add <file>` like A/B/C did.

Other untracked items to leave alone: `.scratch/`, `mcp_server/_import_test.py`, `mcp_server/_mcp_probe.py`.

## Phase D instructions (next session)

Per the Codex-written implementation plan at `docs/plans/2026-04-15-block-basepoint-metadata-userdata-migration-plan.md`:

### 1. Pre-flight

- `git log --oneline -3` should show `874984a` on top of `519f8fa` on top of `c036376`.
- `git status` should show the three uncommitted main-branch modifications above. Do NOT stage them.
- Build status check: `cd mcp_server && pytest tests/test_block_replace_object_geometry_live.py -m requires_rhino` should return 6 passed. If not, stop and investigate before starting Phase D.

### 2. Add the four tests

All in `mcp_server/tests/test_block_replace_object_geometry_live.py`, below `test_disagreement_new_slot_wins`. Each should use `@pytest.mark.requires_rhino` via the existing module-level `pytestmark`. All should use `assert_new_slot` from conftest where the slot's presence matters.

- `test_save_load_roundtrip_preserves_basepoint`
  - Create block with basePoint=(5,0,0). Behavior + introspection confirm new slot present.
  - Save `.3dm` to a temp path via `rhino_document_ops({"action": "save", "path": ...})`.
  - Create new document via `rhino_document_ops({"action": "new"})`.
  - Open the saved file via `rhino_document_ops({"action": "open", "path": ...})`.
  - Introspection via `assert_new_slot` — must read (5,0,0) back. Also behavior check (local bbox of the object).
  - Clean up temp file.

- `test_block_duplicate_carries_basepoint`
  - Create source block with basePoint=(5,0,0).
  - Duplicate via `rhino_block_duplicate({"name": "SRC_BLOCK", "newName": "DUP_BLOCK"})`.
  - `assert_new_slot("DUP_BLOCK", (5,0,0))` — proves the explicit reattach in `HandleBlockDuplicate` (Phase B) worked.
  - Behavior check: both blocks produce identical local-coord geometry for the same source.

- `test_block_rebase_updates_new_slot`
  - Create block with basePoint=(5,0,0).
  - Rebase via `rhino_block_rebase` with an anchor move that changes basePoint to (7,0,0) (check rhino_block_rebase tool for exact schema — it likely takes axes + anchor).
  - `assert_new_slot("BLOCK", (7,0,0))` — proves `UpdateDefinitionBasePoint` carried the new slot through slice-copy + `ModifyInstanceDefinition`.
  - **If this test fails**: escalate per the code snippet in the "Known limitations" section #3 above. Amend Phase B's commit (don't create a new commit) with the direct-attach-on-live-entry fix.

- `test_preserve_sites_retain_basepoint`
  - Create block with basePoint=(5,0,0).
  - Call in sequence, checking `assert_new_slot("BLOCK", (5,0,0))` between each:
    1. `rhino_block_add_objects` — add a new object
    2. `rhino_block_remove_objects` — remove it
    3. `rhino_block_replace_geometry` — replace with a fresh source
  - Each should leave the new UserData slot intact with value (5,0,0).
  - **If this test fails**: don't weaken the invariant. Audit the specific preserve path that dropped UserData and patch it (the plan's "only patch code if the SDK path demonstrably drops metadata").

### 3. Mask + intended-rule audits (code-reading, no tests)

For each of these, add a brief inline comment at the callsite documenting the observed behavior:
- `HandleBlockRename` — mask used on `ModifyInstanceDefinition` should be name-only; verify UserData is not cleared. Design §3.4 categorizes this as "Mask audit."
- `HandleBlockUnlink` — linked → local conversion; verify any present UserData survives.
- `HandleBlockRefresh` — design §3.4 says "Audit whether refresh replaces or preserves existing definition metadata; document observed behavior; ensure no duplicate/stale payloads."
- `HandleBlockMerge` — design §3.4 intended rule: "Surviving target retains its metadata; discarded source metadata goes with the definition; merge must not create duplicate payloads on the survivor."
- `HandleBlockLink` — design §3.4: "Externally-authored linked defs do NOT get synthetic origin-basePoint written."

### 4. Commit Phase D

Commit message template (echo the Phase B/C style):

```
feat(blocks): harden basePoint userdata round-trips and preserve-path survival

Phase D of the #28 migration. ...
```

Include:
- Which tests were added
- Which audit sites had inline comments added
- Whether `UpdateDefinitionBasePoint` was escalated to direct-attach (if test 8 forced it)
- Verification: all 10 live tests green

### 5. Phase E docs cleanup

Design doc edits needed before final commit:
- **§2.2** — verify the `m_userdata_xformage = ON_UserData::not_transformed` reference was fully corrected (partially done earlier in this session; check for residuals)
- **§3.3** — add a native-vs-managed distinction during the transition window. Native: new-first actually works. Managed: reflection-bridge fallback always fires (SDK limitation), new-first is graceful-degrade code.
- **§5.2** — correct the introspection-mechanism wording. The helper uses a native internal HTTP route + httpx, NOT managed reflection. The original design-doc wording said managed reflection.
- **§5.4 test 9 scope** — was originally "companion-path disagreement"; now native-path via `rhino_block_replace_geometry`. Update the description.
- **"Open questions resolved" table** — one row near the end (~line 383) still says `ON_UserData::not_transformed` per earlier Codex round.
- Add a new row or section to the design doc about the `InstanceDefinition.UserData` SDK limitation and what it means for managed-side behavior during the transition window.

Plan doc edits:
- Line ~340 of the implementation plan describes the introspection helper as reflection-based. Update to match reality: native internal HTTP route + httpx.

### 6. PR open

One PR for all five commits (squash-merge at end per repo convention):
- `gh pr create` against `main`
- PR body: summarize each phase's contribution, list the 10 tests, restate the known limitations, reference follow-up #34 for legacy retirement
- After merge: delete remote + local branch via `gh pr merge --squash --delete-branch`
- **Auto-close trigger**: PR body must use `Closes #28` (bare `#28`, not `Closes Issue #28`)
- File follow-up #34 for reflection-bridge retirement + legacy-slot-write retirement, gated on ≥1 release window (done — tracked at #34; coverage follow-up at #35)

## Deploy sequence reminder

The Phase C native binary + managed binary are currently deployed:
- `RookNative.rhp` at 18:10 (Phase C native read switch + debug routes)
- `Rook.rhp` at 18:27 (Phase C managed with RegisterType-reflection removed)

Phase D changes will be Python-only if no test requires native changes. Test 8 might escalate native if rebase carry-through fails — in that case:
1. Close Rhino
2. Build native via `scripts/build-native.bat` or `powershell -ExecutionPolicy Bypass -File build_native.ps1 -Configuration Release`
3. `cp src/RookNative/bin/Release/x64/RookNative.rhp $APPDATA/McNeel/Rhinoceros/8.0/Plug-ins/RookNative/`
4. User restarts Rhino
5. Rerun tests

The managed auto-deploy target fires on `dotnet build src/Rook/Rook.csproj -c Release -f net7.0`, but only when Rhino doesn't have `Rook.rhp` locked. LoadMode=2 means Rhino usually releases the lock if no companion-routed tool has been called.

## Contact / tokens

- **Rhino MCP** is the tool path. Use `rhino_ping` to verify connection after Rhino restart.
- **Git user:** `bringfire`.
- **Repo convention:** `fix/` branches off main, one PR, squash-merge via `gh pr merge --squash --delete-branch` at the end.

## If something goes sideways

- Phase A/B/C are orthogonal verification boundaries. You can run the 6-test suite at any point to confirm nothing regressed.
- If a Phase D test fails: do NOT weaken the invariant or skip the test. Investigate the specific failure and patch the specific path.
- If deploy/build gets stuck in file-lock loop: ask the user to close Rhino. LoadMode=2 on the companion usually lets the managed deploy through after a short wait, but native always needs Rhino closed.
- Reflection-bridge fallback is doing a lot of load-bearing work on the managed side; don't accidentally break it while fixing other things.

Good luck.
