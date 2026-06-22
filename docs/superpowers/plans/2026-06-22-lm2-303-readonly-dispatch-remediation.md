# #303 Readonly Dispatch Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clear the four genuine readonly visible-but-not-dispatchable tools (`scene_query`, `scene_classify`, `scene_overlay`, `gh_canvas_image`) so the LM2 surface smoke residue goes 4 → 0 — by fixing dispatch reality, not the audit.

**Architecture:** Two small data corrections: add three `BRIDGE_ROUTES` entries (scene trio, mirroring their pure `call_rhino` server handlers) and remove `gh_canvas_image` from the `gh_canvas_readonly` group (MCP-only, returns a PNG). No audit/inventory/wire/architecture changes.

**Tech Stack:** Python 3.12, pytest.

## Global Constraints

- No audit / reporting changes (no severity edits, no hiding tools).
- No `CapabilityInventory` / `capability_record` / `execution_profile` / `profile_reconciliation` changes.
- No MCP wire changes (`server.list_tools` / `_call_tool_dispatch` untouched).
- No bridge route or local handler for `gh_canvas_image`.
- Do NOT touch `scene_graph` / `scene_context` / `scene_stats` in `LOCAL_TIER_0_DISPATCH_EXCLUSIONS`.
- Do NOT touch anything in `external_mcp` (LM2G).
- Scope limited to `tool_dispatcher.py`, `tool_groups.py`, and focused tests.
- Test commands run from the repo root (`C:\UDEV\Rook`) with the repo venv: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider ...`.

## File Structure

- `mcp_server/src/rook/agent/tool_dispatcher.py` (modify) — 3 `BRIDGE_ROUTES` entries.
- `mcp_server/src/rook/agent/tool_groups.py` (modify) — remove `gh_canvas_image` from `gh_canvas_readonly`.
- `mcp_server/tests/test_lm303_readonly_dispatch.py` (new) — focused regression tests for both changes.
- `mcp_server/tests/test_phase5b_readonly_enforcement.py` (modify) — update `test_has_inspection_tools`.

---

### Task 1: Scene trio bridge routes

**Files:**
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py` (BRIDGE_ROUTES dict, closes at line 479)
- Create: `mcp_server/tests/test_lm303_readonly_dispatch.py`

**Interfaces:**
- Consumes: `BRIDGE_ROUTES` (tool_dispatcher), `collect_live_sources` + `dispatch_context_from_sources` (capability_inventory), `classify_visible_tool` (chat.tool_contracts).
- Produces: three new `BRIDGE_ROUTES` keys (`scene_query`, `scene_classify`, `scene_overlay`).

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_lm303_readonly_dispatch.py`:

```python
from __future__ import annotations

from rook.agent.tool_dispatcher import BRIDGE_ROUTES
from rook.agent.capability_inventory import (
    collect_live_sources,
    dispatch_context_from_sources,
)
from rook.agent.chat.tool_contracts import classify_visible_tool

_SCENE_TRIO = {
    "scene_query": ("/scene/graph/query", "POST"),
    "scene_classify": ("/scene/graph/classify", "POST"),
    "scene_overlay": ("/scene/graph/overlay", "POST"),
}


def test_scene_trio_in_bridge_routes():
    for tool, route in _SCENE_TRIO.items():
        assert tool in BRIDGE_ROUTES, f"{tool} missing from BRIDGE_ROUTES"
        assert BRIDGE_ROUTES[tool] == route, (
            f"{tool} route mismatch: {BRIDGE_ROUTES[tool]} != {route}"
        )


def test_scene_trio_classifies_as_bridge_route():
    # Realistic DispatchContext from the static surface snapshot; bridge_names is
    # populated from BRIDGE_ROUTES.keys(), so the trio must now classify as a
    # real dispatch path (was "failure" before the routes were added).
    ctx = dispatch_context_from_sources(collect_live_sources())
    for tool in _SCENE_TRIO:
        assert classify_visible_tool(tool, ctx) == "bridge_route", (
            f"{tool} did not classify as bridge_route"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_lm303_readonly_dispatch.py -v`
Expected: both FAIL — `scene_query` not in `BRIDGE_ROUTES`; classify returns `"failure"`, not `"bridge_route"`.

- [ ] **Step 3: Add the three bridge routes**

In `mcp_server/src/rook/agent/tool_dispatcher.py`, the `BRIDGE_ROUTES` dict ends at line 479 (`}`), with the last entries being the Rook Reconstruction block. Insert a Scene Graph section immediately before the closing brace. Replace:

```python
    "rhino_2d_to_3d_submit": ("/reconstruction/2d-to-3d/jobs", "POST"),
    "rhino_2d_to_3d_import": ("/reconstruction/2d-to-3d/import", "POST"),
}
```

with:

```python
    "rhino_2d_to_3d_submit": ("/reconstruction/2d-to-3d/jobs", "POST"),
    "rhino_2d_to_3d_import": ("/reconstruction/2d-to-3d/import", "POST"),

    # --- Scene Graph (agent bridge access; endpoints mirror the pure call_rhino
    # handlers in server._call_tool_dispatch so the agent path and MCP path hit
    # the identical Rhino route). See #303. scene_graph/context/stats stay parked
    # in LOCAL_TIER_0_DISPATCH_EXCLUSIONS by separate decision.
    "scene_query":    ("/scene/graph/query", "POST"),
    "scene_classify": ("/scene/graph/classify", "POST"),
    "scene_overlay":  ("/scene/graph/overlay", "POST"),
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_lm303_readonly_dispatch.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/tests/test_lm303_readonly_dispatch.py
git commit -m "feat(303): add scene_query/classify/overlay bridge routes"
```

---

### Task 2: Remove gh_canvas_image from gh_canvas_readonly

**Files:**
- Modify: `mcp_server/src/rook/agent/tool_groups.py` (`gh_canvas_readonly` group, line 420)
- Modify: `mcp_server/tests/test_phase5b_readonly_enforcement.py` (`test_has_inspection_tools`)
- Modify: `mcp_server/tests/test_lm303_readonly_dispatch.py` (append two tests)

**Interfaces:**
- Consumes: `TOOL_GROUPS`, `READONLY_ALLOWED_GROUPS` (tool_groups); `server.list_tools` (advertised-name pin).
- Produces: `gh_canvas_image` no longer a member of any `READONLY_ALLOWED_GROUPS` group; still advertised over MCP.

- [ ] **Step 1: Write/extend the failing tests**

Append to `mcp_server/tests/test_lm303_readonly_dispatch.py`:

```python
import pytest

from rook.agent.tool_groups import TOOL_GROUPS, READONLY_ALLOWED_GROUPS


def test_gh_canvas_image_not_in_any_readonly_group():
    # Removed from gh_canvas_readonly (MCP-only, returns a PNG, no agent dispatch
    # path). Must not be reachable by the readonly profile via ANY allowed group.
    assert "gh_canvas_image" not in TOOL_GROUPS["gh_canvas_readonly"]
    for group in READONLY_ALLOWED_GROUPS:
        members = TOOL_GROUPS.get(group, [])
        assert "gh_canvas_image" not in members, (
            f"gh_canvas_image leaked into readonly-allowed group {group}"
        )


@pytest.mark.asyncio
async def test_gh_canvas_image_still_advertised_over_mcp():
    # Intent is "not local readonly, still public MCP". Pin that it remains in the
    # advertised catalog for Claude Code / external clients.
    from rook import server

    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert "gh_canvas_image" in names
```

Update `mcp_server/tests/test_phase5b_readonly_enforcement.py` — replace the existing `test_has_inspection_tools` (currently asserts `gh_canvas_image` is present):

```python
    def test_has_inspection_tools(self):
        readonly_tools = set(TOOL_GROUPS["gh_canvas_readonly"])
        for tool in ("gh_snapshot", "gh_inspect_output"):
            self.assertIn(tool, readonly_tools, f"Missing: {tool}")
        # gh_canvas_image intentionally excluded: MCP/server-side only (returns a
        # PNG, no agent dispatch path). See #303.
        self.assertNotIn("gh_canvas_image", readonly_tools)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_lm303_readonly_dispatch.py mcp_server/tests/test_phase5b_readonly_enforcement.py -v`
Expected: `test_gh_canvas_image_not_in_any_readonly_group` FAILS (still in the group); `test_has_inspection_tools` now FAILS at the new `assertNotIn` (image still present). `test_gh_canvas_image_still_advertised_over_mcp` should PASS already (the tool is unchanged in `list_tools`).

- [ ] **Step 3: Remove gh_canvas_image from the readonly group**

In `mcp_server/src/rook/agent/tool_groups.py`, the `gh_canvas_readonly` group lists `gh_canvas_image` at line 420. Replace:

```python
        "gh_snapshot",
        "gh_canvas_image",
    ],
```

with:

```python
        "gh_snapshot",
        # gh_canvas_image intentionally NOT exposed here: MCP/server-side only
        # (returns a canvas PNG, no agent ToolDispatcher path), consistent with
        # the read-write gh_canvas group's deliberate omission. See #303.
    ],
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_lm303_readonly_dispatch.py mcp_server/tests/test_phase5b_readonly_enforcement.py -v`
Expected: all PASS.

- [ ] **Step 5: Regression — LM2 suite + py_compile**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_lm303_readonly_dispatch.py mcp_server/tests/test_phase5b_readonly_enforcement.py mcp_server/tests/test_dispatcher_safety.py mcp_server/tests/test_capability_inventory.py mcp_server/tests/test_profile_reconciliation.py mcp_server/tests/test_rookchat_visible_dispatchability.py -v
mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/src/rook/agent/tool_groups.py
```
Expected: all PASS; py_compile silent.

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/agent/tool_groups.py mcp_server/tests/test_phase5b_readonly_enforcement.py mcp_server/tests/test_lm303_readonly_dispatch.py
git commit -m "feat(303): remove gh_canvas_image from gh_canvas_readonly (MCP-only)"
```

---

## Post-implementation (controller, not a task)

After Task 2 + the final whole-branch review:
- Open a PR `codex/lm2-303-readonly-dispatch-remediation` → `main`. **Stop before merge — explicit human approval required** (no self-merge to main).
- After merge: re-mirror current `main` into the deployed venv (#300 stopgap), then run the deployed smoke `surface` (deployed interpreter, empty `PYTHONPATH`). Expect the readonly `not_dispatchable` residue **4 → 0**; `coherence` and `external` remain PASS (`external` unaffected — `gh_canvas_image` is still advertised-with-handler, `advertised_not_dispatchable: 0`).
- Close #303; update campaign memory.
