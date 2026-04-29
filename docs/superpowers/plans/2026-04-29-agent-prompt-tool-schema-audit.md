# Agent Prompt Tool-Schema Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring every Rook agent system prompt into alignment with the actual `gh_edit` and `gh_move` MCP tool schemas, eliminating the wrong-field-name failure mode that just bricked an Architect-agent session.

**Architecture:** Locate every agent-facing prompt that contains a `gh_edit` JSON example, replace the four stale field names (`id` → `temp_id`, `component` → `name`, `nickname` → `nick`, plus the non-existent `actions` wrapper) with the schema-correct equivalents, add a `gh_move` signature line where the tool is listed, then verify with grep + a live agent smoke test.

**Tech Stack:** Markdown prompt files under `mcp_server/src/rook/agent/`; the authoritative schema lives in the running MCP server's tool definitions (verified via `ToolSearch`).

---

## Background — The Failure Mode

A user-driven Architect agent failed in 6 ways during a single session. Triage revealed **all 6 are downstream of 4 wrong field names** in the agent's system prompt:

| What the prompt teaches | What the schema actually accepts |
|---|---|
| `{"id": "T1", "type": "slider", "nickname": "Count", ...}` | `{"temp_id": "T1", "type": "slider", "nick": "Count", ...}` |
| `{"id": "T2", "component": "Series", ...}` | `{"temp_id": "T2", "name": "Series", ...}` |
| `gh_edit({"actions": {"create": [...]}})` (sometimes inferred) | `gh_edit(create=[...], connect=[...], epoch=N)` flat |
| `gh_move(moves=[{"id", "x", "y"}])` | `gh_move(positions=[{"guid", "x", "y"}])` |
| `"x": N, "y": M` inside `gh_edit.create` entries (also taught in prose: *"use x/y offsets when creating multiple components"*) | `"pos": [N, M]` for `gh_edit.create`. `x`/`y` are correct **only** for `gh_move.positions` entries. |

The `set_values` field was *not* on this list originally — it was misdiagnosed in an earlier version of this plan. The C# handler (`GrasshopperHandler.cs` → `ApplyEdit` → `ResolveEditId`) resolves both T-prefixed temp_ids and C-prefixed snapshot ids in `set_values`, so `{"id": "T1", "value": 10}` in the same call as `create` does work. The only reason we drop it from the canonical example is redundancy — slider initial values belong inline in `create.value`.

**Verified-correct schema** (from live `ToolSearch` results today, 2026-04-29):

```jsonc
// gh_edit create entry
{
  "temp_id": "T1",                    // REQUIRED — must be T-prefixed
  "guid":   "abc-...",                // OR
  "name":   "Series",                 // OR
  "type":   "slider"|"panel"|"toggle",
  "nick":   "Count",                  // optional nickname
  "pos":    [50, 100],                // optional [x, y]
  "min": 1, "max": 20, "value": 5     // slider-only
}

// gh_edit top-level (NO actions wrapper)
{
  "epoch":     <int from latest gh_snapshot>,    // REQUIRED
  "create":    [...],
  "connect":   ["T1.O0>T2.I1"],
  "disconnect":[...],
  "set_values":[{"id": "C1", "value": 10}],      // id = C-prefixed snapshot id
  "delete":    ["C3"],
  "groups":    [...]
}

// gh_move
{
  "positions": [
    {"guid": "C5", "x": 50, "y": 100}            // guid accepts C-prefixed short ids OR instance GUIDs
  ]
}
```

---

## File Structure

Files modified (all are markdown prompts loaded into agent system prompts at runtime):

| File | Stale content | Purpose after fix |
|---|---|---|
| `mcp_server/src/rook/agent/prompts/WORKER.md` | gh_edit example (lines 44-54), gh_move bullet (line 17) | Authoritative WORKER prompt example |
| `mcp_server/src/rook/agent/personas/architect/role.md` | gh_edit example (lines 50-60), gh_move bullet (line 29) | Architect persona role |
| `mcp_server/src/rook/agent/personas/worker/role.md` | gh_edit example (lines 50-60), gh_move bullet (line 29) | Worker persona role |
| `mcp_server/src/rook/agent/personas/specialist/role.md` | gh_edit example (lines 21-31), inline `"component":` references (lines 17-18) | Specialist persona role |
| `mcp_server/src/rook/agent/personas/scripter/role.md` | Negative example uses stale `{"component": ...}` (line 20) | Scripter persona role |

Files **verified clean** (no edits needed):
- `mcp_server/src/rook/agent/prompts/PLANNER.md` — describes gh_edit at high level, no JSON examples
- `mcp_server/src/rook/agent/personas/explorer/role.md` — read-only persona, no mutation examples
- `mcp_server/src/rook/agent/personas/guardian/role.md` — no mutation examples
- `mcp_server/src/rook/agent/personas/planner/role.md` — no mutation examples
- All `personas/*/personality.md` — tone/style only, no tool examples

The 5 prompt files share **two identical-shape examples** (a slider+component create with one connect, plus a set_values line). The fix is the same canonical replacement applied to each.

---

## Canonical Replacement (used by every fix task below)

**Old (broken) example:**

```json
{
  "create": [
    {"id": "T1", "type": "slider", "nickname": "Count", "min": 1, "max": 20, "value": 5, "x": 50, "y": 100},
    {"id": "T2", "component": "Series", "x": 250, "y": 100}
  ],
  "connect": ["T1.O0>T2.I1"],
  "set_values": [{"id": "T1", "value": 10}]
}
```

**New (schema-correct) example:**

```json
{
  "epoch": 7,
  "create": [
    {"temp_id": "T1", "type": "slider", "nick": "Count", "min": 1, "max": 20, "value": 5, "pos": [50, 100]},
    {"temp_id": "T2", "name": "Series", "pos": [250, 100]}
  ],
  "connect": ["T1.O0>T2.I1"]
}
```

Notes on the change:
- `id` → `temp_id` for create entries (the schema field is literally named `temp_id`)
- `component` → `name`
- `nickname` → `nick`
- `"x": N, "y": M` → `"pos": [N, M]` for `gh_edit.create` entries. **`x`/`y` are still correct for `gh_move.positions` entries** — the two tools have different shapes here, which is part of why agents got confused.
- Added `epoch` at top level (required)
- Dropped `set_values` from the example. *Not* because it doesn't work in the same call (it does — temp_ids resolve via `tempIdMap` in `ResolveEditId`), but because the slider's initial value belongs inline in `create.value`. Re-using `set_values` for that is redundant and the `{"id": "T1", "value": 10}` form reinforced the impression that `id` was the universal field name. Use `set_values` in *follow-up* edits or to mutate a panel/toggle that you don't want to recreate.

---

## Task 1: Verify Schema Source-of-Truth Snapshot

**Files:**
- Read-only: live MCP `ToolSearch` results

- [ ] **Step 1: Re-confirm gh_edit and gh_move schemas with ToolSearch**

Run:
```
ToolSearch(query="select:mcp__rook__gh_edit,mcp__rook__gh_move", max_results=2)
```

Expected: `gh_edit` returns a `create` entry shape with `temp_id` (required), `guid|name|type`, `nick`, `pos`. `gh_move` returns `positions: [{guid, x, y}]`.

If the live schema differs from what's documented in this plan's "Canonical Replacement" section above, **stop and update the plan** — the schema is the source of truth, not this document.

- [ ] **Step 2: Snapshot the current grep baseline**

Run:
```bash
grep -rn '"id": "T\|"component":\|"nickname":\|"actions":' mcp_server/src/rook/agent/ | tee /tmp/rook-stale-fields-before.txt
wc -l /tmp/rook-stale-fields-before.txt
```

Expected: ~13-15 lines across 5 files (record exact count for the post-fix verification step).

---

## Task 2: Fix `prompts/WORKER.md`

**Files:**
- Modify: `mcp_server/src/rook/agent/prompts/WORKER.md` — gh_move bullet (~line 17), gh_edit example block (~lines 44-54), gotcha bullet (~line 70)

- [ ] **Step 1: Update the gh_move bullet to include the signature**

Replace the line:
```diff
- `gh_move` — reposition components
+ `gh_move` — reposition components. Signature: `gh_move(positions=[{"guid": "C5", "x": 50, "y": 100}, ...])`. The `guid` field accepts C-prefixed short ids from `gh_snapshot` OR full instance GUIDs. Note: `gh_move.positions` uses flat `x`/`y` keys, while `gh_edit.create` entries use `pos: [x, y]` — these tools have different shapes.
```

- [ ] **Step 2: Replace the gh_edit example block**

Replace the existing `Example gh_edit call:` JSON block with the canonical replacement from the "Canonical Replacement" section of this plan.

- [ ] **Step 3: Patch the canvas-position gotcha bullet**

The "Common Gotchas" section currently says (line 70 before Step 2; line number may shift after Step 2):

```markdown
- **Canvas position**: Components default to (0,0) — use x/y offsets when creating multiple components
```

Replace with:
```markdown
- **Canvas position**: Components default to (0,0). For `gh_edit.create` entries use `"pos": [x, y]`. For `gh_move.positions` entries use flat `"x": N, "y": M` keys. (The two shapes differ — see the gh_move bullet above.)
```

- [ ] **Step 4: Verify by grep**

Run:
```bash
grep -nE '"id": "T|"component":|"nickname":|x/y offsets when creating' mcp_server/src/rook/agent/prompts/WORKER.md
```

Expected: zero matches.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/agent/prompts/WORKER.md
git commit -m "docs(agent): align WORKER prompt with gh_edit/gh_move schemas"
```

---

## Task 3: Fix `personas/architect/role.md`

**Files:**
- Modify: `mcp_server/src/rook/agent/personas/architect/role.md` — gh_move bullet (~line 29), gh_edit example block (~lines 50-60), gotcha bullet (~line 91)

- [ ] **Step 1: Update the gh_move bullet**

Replace the line:
```diff
- `gh_move` -- reposition components
+ `gh_move` -- reposition components. Signature: `gh_move(positions=[{"guid": "C5", "x": 50, "y": 100}, ...])`. The `guid` field accepts C-prefixed short ids from `gh_snapshot` OR full instance GUIDs. Note: `gh_move.positions` uses flat `x`/`y` keys, while `gh_edit.create` entries use `pos: [x, y]` — these tools have different shapes.
```

- [ ] **Step 2: Replace the gh_edit example block**

Replace with the canonical replacement.

- [ ] **Step 3: Patch the canvas-position gotcha bullet**

The "Common Gotchas" section currently says:

```markdown
- **Canvas position**: Components default to (0,0) -- use x/y offsets when creating multiple components
```

Replace with:
```markdown
- **Canvas position**: Components default to (0,0). For `gh_edit.create` entries use `"pos": [x, y]`. For `gh_move.positions` entries use flat `"x": N, "y": M` keys. (The two shapes differ — see the gh_move bullet above.)
```

- [ ] **Step 4: Verify by grep**

Run:
```bash
grep -nE '"id": "T|"component":|"nickname":|x/y offsets when creating' mcp_server/src/rook/agent/personas/architect/role.md
```

Expected: zero matches.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/agent/personas/architect/role.md
git commit -m "docs(agent): align architect persona prompt with gh_edit/gh_move schemas"
```

---

## Task 4: Fix `personas/worker/role.md`

**Files:**
- Modify: `mcp_server/src/rook/agent/personas/worker/role.md` — gh_move bullet (~line 29), gh_edit example block (~lines 50-60), gotcha bullet (~line 83)

(Identical 5-step fix to Task 3 — the worker and architect role.md files share the same shape.)

- [ ] **Step 1: Update the gh_move bullet** — same diff as Task 3 step 1.

- [ ] **Step 2: Replace the gh_edit example block** — same canonical replacement as Task 3 step 2.

- [ ] **Step 3: Patch the canvas-position gotcha bullet** — same diff as Task 3 step 3 (look for the line that contains `use x/y offsets when creating multiple components`).

- [ ] **Step 4: Verify by grep**

```bash
grep -nE '"id": "T|"component":|"nickname":|x/y offsets when creating' mcp_server/src/rook/agent/personas/worker/role.md
```

Expected: zero matches.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/agent/personas/worker/role.md
git commit -m "docs(agent): align worker persona prompt with gh_edit/gh_move schemas"
```

---

## Task 5: Fix `personas/specialist/role.md`

**Files:**
- Modify: `mcp_server/src/rook/agent/personas/specialist/role.md` lines 17-18 and 21-31

The specialist file has BOTH an inline mention of `"component"` keys AND a JSON example block, so it needs two patches.

- [ ] **Step 1: Replace the inline-key references (lines 17-18)**

Old:
```markdown
   - Then processing components: `"component": "Series"`, `"component": "Cross Reference"`, etc.
   - Finally output/display components: `"component": "Custom Preview"`
```

New:
```markdown
   - Then processing components: `"name": "Series"`, `"name": "Cross Reference"`, etc.
   - Finally output/display components: `"name": "Custom Preview"`
```

- [ ] **Step 2: Replace the JSON example (lines 21-31)**

Replace the existing example block. Use a 3-component variant of the canonical replacement (since the original example had 3 components):

```json
{
  "epoch": 7,
  "create": [
    {"temp_id": "T1", "type": "slider", "nick": "Count", "min": 1, "max": 50, "value": 10, "pos": [50, 0]},
    {"temp_id": "T2", "type": "slider", "nick": "Step", "min": 0.1, "max": 5.0, "value": 1.0, "pos": [50, 80]},
    {"temp_id": "T3", "name": "Series", "pos": [300, 40]}
  ],
  "connect": ["T1.O0>T3.I1", "T2.O0>T3.I2"]
}
```

- [ ] **Step 3: Verify by grep**

```bash
grep -n '"id": "T\|"component":\|"nickname":' mcp_server/src/rook/agent/personas/specialist/role.md
```

Expected: zero matches.

- [ ] **Step 4: Commit**

```bash
git add mcp_server/src/rook/agent/personas/specialist/role.md
git commit -m "docs(agent): align specialist persona prompt with gh_edit/gh_move schemas"
```

---

## Task 6: Fix `personas/scripter/role.md` Negative Example

**Files:**
- Modify: `mcp_server/src/rook/agent/personas/scripter/role.md` line 20

This file's content is technically a *negative* example ("do NOT do this"), but it still uses the wrong field name. Update for consistency so the negative example is itself schema-correct.

- [ ] **Step 1: Replace the negative example**

Old line 20:
```markdown
   **Do NOT** use `gh_edit` with `{"component": "Python 3 Script"}` or `{"component": "C# Script"}` — that's a name-lookup path that can resolve to a legacy component (see server.py around the create-component code where the warning is documented).
```

New:
```markdown
   **Do NOT** use `gh_edit` with `{"name": "Python 3 Script"}` or `{"name": "C# Script"}` — that's a name-lookup path that can resolve to a legacy component (see server.py around the create-component code where the warning is documented).
```

- [ ] **Step 2: Verify by grep**

```bash
grep -n '"component":' mcp_server/src/rook/agent/personas/scripter/role.md
```

Expected: zero matches.

- [ ] **Step 3: Commit**

```bash
git add mcp_server/src/rook/agent/personas/scripter/role.md
git commit -m "docs(agent): align scripter persona negative example with current schema field name"
```

---

## Task 7: Add Prompt-Schema Regression Test

**Files:**
- Create: `mcp_server/tests/test_persona_prompt_schema.py`
- Reference (existing pattern): `mcp_server/tests/test_chat_prompt_builder.py:41-81`

**Why a separate test file:** the existing `test_chat_prompt_builder.py` already anchors the gh-script-routing drift (the 2026-04-21 incident). This new file anchors the gh_edit/gh_move schema drift (the 2026-04-29 incident). Keeping the two anchors in different files makes the failure messages and the "see X for context" memos easier to read when the next drift happens.

The test must cover (a) what the agent actually sees at runtime — `PromptBuilder.build_system(persona)` for `worker`, `architect`, `specialist`, `scripter`, and (b) the human-readable display snapshot at `prompts/WORKER.md`, which is loaded as a file (not via PromptBuilder) and read directly by anyone debugging an agent.

- [ ] **Step 1: Write the failing test file**

Create `mcp_server/tests/test_persona_prompt_schema.py`:

```python
"""Regression tests for gh_edit / gh_move schema field names in agent prompts.

Anchored against the 2026-04-29 Architect-agent failure: the prompts taught
`id`/`component`/`nickname`/`actions`/`moves` and flat `x`/`y` for create
entries. The runtime schema accepts `temp_id`/`name`/`nick`, no `actions`
wrapper, `pos: [x, y]` in gh_edit.create, and `gh_move.positions`.

See docs/superpowers/plans/2026-04-29-agent-prompt-tool-schema-audit.md.

The runtime worker/architect/specialist/scripter prompts come from
`PromptBuilder.build_system(persona)` (which reads personas/<name>/role.md).
The `prompts/WORKER.md` file is a display snapshot loaded directly by humans
debugging an agent — it must also stay in sync with the schema, but is checked
as a raw file read here, not via PromptBuilder.
"""
import re
from pathlib import Path

import pytest

from rook.agent.chat.prompt_builder import PromptBuilder


# Patterns that MUST NOT appear in any agent-facing prompt.
STALE_PATTERNS = [
    (r'"id"\s*:\s*"T\d', 'uses {"id": "T..."} for gh_edit.create — should be "temp_id"'),
    (r'"component"\s*:', 'uses {"component": "..."} — should be "name"'),
    (r'"nickname"\s*:', 'uses {"nickname": "..."} — should be "nick"'),
    (r'"actions"\s*:\s*\{', 'wraps gh_edit args in an {"actions": {...}} object — params are flat'),
    (r'"moves"\s*:', 'uses {"moves": [...]} for gh_move — should be "positions"'),
    (r'x/y offsets when creating', 'prose says "x/y offsets when creating" — gh_edit.create uses pos: [x, y]'),
]

# Tokens that SHOULD appear in any prompt that documents gh_edit.
EXPECTED_TOKENS = [
    'temp_id',          # the create-entry id field
    '"epoch"',          # required top-level field
    '"pos"',            # create-entry position
]


def _assert_clean(prompt: str, label: str) -> None:
    for pattern, why in STALE_PATTERNS:
        match = re.search(pattern, prompt)
        assert match is None, (
            f"{label}: stale schema reference matched /{pattern}/ ({why}). "
            f"Excerpt: {prompt[max(0, match.start()-40):match.end()+40]!r}"
        )


def _assert_has_schema_cues(prompt: str, label: str) -> None:
    for token in EXPECTED_TOKENS:
        assert token in prompt, (
            f"{label}: missing expected schema cue {token!r} — the prompt no "
            f"longer documents the current gh_edit shape."
        )


@pytest.mark.parametrize("persona", ["worker", "architect", "specialist", "scripter"])
def test_persona_prompt_uses_current_gh_edit_schema(persona):
    """PromptBuilder output for each persona must use current schema field names."""
    prompt = PromptBuilder().build_system(persona)
    _assert_clean(prompt, f"persona {persona}")


@pytest.mark.parametrize("persona", ["worker", "architect", "specialist"])
def test_persona_prompt_documents_current_gh_edit_cues(persona):
    """Personas that include a gh_edit JSON example must show current schema tokens.

    Scripter is excluded — its role.md only has a negative example
    (\"do NOT use gh_edit with name='Python 3 Script'\") and is not expected
    to carry a positive gh_edit example with epoch/pos/temp_id.
    """
    prompt = PromptBuilder().build_system(persona)
    _assert_has_schema_cues(prompt, f"persona {persona}")


def test_persona_prompt_documents_gh_move_signature():
    """At least one of worker/architect mentions the full gh_move signature.

    Without the explicit positions=[{guid, x, y}] signature, agents have
    historically invented gh_move(moves=[{id, x, y}]).
    """
    builder = PromptBuilder()
    combined = builder.build_system("worker") + builder.build_system("architect")
    assert "gh_move(positions=" in combined, (
        "Neither worker nor architect prompt documents the gh_move(positions=...) "
        "signature — agents will keep guessing the wrong field names."
    )


def test_worker_md_display_snapshot_uses_current_schema():
    """prompts/WORKER.md is a human-readable display snapshot — must stay in sync."""
    repo_root = Path(__file__).resolve().parents[2]
    worker_md = repo_root / "src" / "rook" / "agent" / "prompts" / "WORKER.md"
    assert worker_md.exists(), f"missing display snapshot: {worker_md}"
    content = worker_md.read_text(encoding="utf-8")
    _assert_clean(content, "prompts/WORKER.md")
    _assert_has_schema_cues(content, "prompts/WORKER.md")
    assert "gh_move(positions=" in content, (
        "prompts/WORKER.md no longer documents the gh_move(positions=...) signature."
    )
```

- [ ] **Step 2: Run the test before fixing prompts (must FAIL on the stale state if you run it on the pre-fix branch, must PASS after Tasks 2-6)**

If this task is executed AFTER Tasks 2-6 (the recommended order — the regression test guards what we just fixed), run:
```bash
cd mcp_server
pytest tests/test_persona_prompt_schema.py -v
```

Expected: all 9 parameterized cases PASS.

If you want to confirm the test would have caught the original failure, stash your prompt fixes and re-run; you should see failures on every persona that mentions `gh_edit`, with the exact stale pattern that drifted.

- [ ] **Step 3: Commit**

```bash
git add mcp_server/tests/test_persona_prompt_schema.py
git commit -m "test(agent): regression test for gh_edit/gh_move schema in persona prompts"
```

---

## Task 8: Final Verification

**Files:** Read-only across all of `mcp_server/src/rook/agent/`.

- [ ] **Step 1: Confirm zero stale patterns remain in agent prompt files**

Run:
```bash
grep -rn '"id": "T\|"component":\|"nickname":\|"actions":\|"moves":' mcp_server/src/rook/agent/ \
  --include="*.md"
```

Expected: zero matches. (Python files may still contain `"component"` as a domain term in `knowledge_graph_export.py` and `tool_dispatcher.py` — those are internal data keys, not prompt content, and are out of scope for this plan.)

- [ ] **Step 2: Confirm `gh_move` signature is now documented in all places that list the tool**

Run:
```bash
grep -A1 '`gh_move`' mcp_server/src/rook/agent/prompts/WORKER.md \
  mcp_server/src/rook/agent/personas/architect/role.md \
  mcp_server/src/rook/agent/personas/worker/role.md
```

Expected: each match is followed by a line containing `Signature: `gh_move(positions=` so an agent reading the prompt sees the correct signature without having to guess.

- [ ] **Step 3: Live smoke test — spawn an agent that exercises the corrected fields**

Restart the MCP server (or kill stale Python processes per the CLAUDE.md memory note: `powershell.exe -NoProfile -Command 'Get-Process python* | Where-Object {$_.Path -like "*Rook*"} | Stop-Process -Force'`) so the next call reloads the prompts.

Then in a fresh chat session, ask:
```
Architect: please add a slider connected to a Series component on the GH canvas, and then move them so they're side-by-side.
```

Expected: agent succeeds in one or two `gh_edit` calls, and one `gh_move` call. No "Missing required parameter: epoch", no "unknown source 'T1'", no "Create failed: Create entry needs 'type', 'guid', or 'name'".

If the agent still fails on the same six patterns from the original report, the prompt fix didn't take effect — verify the server process actually reloaded.

- [ ] **Step 4: Commit any final touch-ups (if smoke test surfaced more stale docs)**

If the smoke test reveals an additional prompt file that wasn't caught by the grep (e.g. an inline string in `prompt_builder.py`), patch it inline and commit:

```bash
git add <file>
git commit -m "docs(agent): catch additional stale schema reference found in smoke test"
```

If the smoke test passes cleanly, no commit needed for this step.

---

## Self-Review Notes

- **Spec coverage:** All 5 stale-field-name locations have a dedicated task. All 3 prose-drift locations (`prompts/WORKER.md` ~line 70, `personas/architect/role.md` ~line 91, `personas/worker/role.md` ~line 83) are now patched as Step 3 inside Tasks 2/3/4 respectively. The 2 secondary issues from the original failure report (temp-IDs-don't-resolve and x/y-ignored) heal automatically once the JSON examples are correct AND the prose gotchas no longer pull agents back. Task 7 adds a regression test that fails the build if any of the patched-out patterns reappear.
- **Placeholder check:** Every diff is fully written out. Task 4 explicitly says "same diff as Task 3 step N" and Task 3 has the actual diffs reproduced inline, so a reader executing Task 4 doesn't need to scroll back.
- **Type/name consistency:** Canonical replacement is defined once. The two-shape difference (`gh_edit.create` uses `pos: [x, y]` vs. `gh_move.positions` uses flat `x`/`y`) is now called out *three* times — in the canonical-replacement notes, in every gh_move-bullet patch, and in every canvas-position-gotcha patch — so an agent skimming any single section gets the warning.
- **`set_values` correction (review feedback applied):** Earlier draft incorrectly claimed temp_ids don't resolve in same-call `set_values`. Corrected after reviewer pointed at `GrasshopperHandler.cs` `ApplyEdit` → `ResolveEditId`, which accepts both T- and C-prefixed ids via `tempIdMap`. The example still drops `set_values` but for the right reason (slider initial values belong inline in `create.value`, not duplicated in `set_values`).
- **Out-of-scope items:** `tool_dispatcher.py:1126,1135` use `"component"` as an internal constraint dict key — this is *runtime* code, not a prompt, and not relevant to the agent failure mode. `knowledge_graph_export.py` uses `"component"` as a `note_type` value, also unrelated. Both correctly excluded.
