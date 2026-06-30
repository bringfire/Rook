# MCP Tool Exposure Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a server-side, env-driven MCP tool-exposure profile (`ROOK_MCP_TOOL_PROFILE=full|lean|readonly`) so Rook does not depend on the client doing progressive disclosure.

**Architecture:** A new pure module `mcp_tool_profiles.py` owns the `Profile` enum, the pure `resolve_profile(env)` resolver, the pinned name sets (`PUBLIC_LEAN_TOOL_NAMES` 17, `PUBLIC_READONLY_TOOL_NAMES` 145, `SENTINEL_TOOL_NAMES` 26), and pure helpers (`filter_tools`, `tool_blocked`, `profile_blocked_envelope`). `server.py` consumes it at two seams: `list_tools()` filters its output by profile (lean/readonly hide tools), and `call_tool()` rejects non-allowlisted tools **only** under `readonly`. Config generators (`doctor.py`, `install.ps1`) inject `lean` into Codex/external configs only. The module never imports `server.py` (one-way dependency).

**Tech Stack:** Python 3.12, MCP Python SDK (`mcp.server`), pytest (tests in `mcp_server/tests/`), PowerShell (`install.ps1`).

## Global Constraints

- **Source of truth is `mcp_server/src/rook/mcp_tool_profiles.py`.** It must **not** import `server.py` (one-way dependency: `server.py` → module).
- **Public env var name (exact):** `ROOK_MCP_TOOL_PROFILE`. Values (exact, normalized via `.strip().lower()`): `full`, `lean`, `readonly`.
- **Absent / empty ⇒ `full`.** Any other non-empty value ⇒ `InvalidProfileError` (no silent fallback).
- **Named invariant "lean list-only / readonly wall":** `lean` filters `list_tools()` only; `readonly` filters `list_tools()` **and** rejects in `call_tool()`. Never give `lean` a `call_tool()` guard.
- **Rejection envelope (exact):** `{"success": False, "data": {"code": "tool_profile_blocked", "tool": <name>, "profile": <profile-value>}}`.
- **`lean` = exactly 17 names; `readonly` = exactly 145 names; sentinels = exactly 26 names** (literals provided in Task 2 — copy verbatim).
- **Live `list_tools()` default surface = 427** (430 static defs minus 3 deprecated-interactive tools gated by `_interactive_command_learning_enabled()`); snapshot tests pin the default flag-off state.
- **Config trap:** inject `lean` only in the Codex/external writer. Never add the profile to the shared `doctor._build_expected_env()` (it feeds Claude too). Claude/panel configs stay `full`.
- **Tests:** **Task 0 creates a worktree-local venv** at `mcp_server/.venv` (the worktree has none, and the main checkout's venv imports `rook` from the wrong tree). Run all pytest from `mcp_server/` via `.venv/Scripts/python.exe -m pytest tests/<file>::<test> -v`. Tests invoke the async handlers via `asyncio.run(server.list_tools())` / `asyncio.run(server.call_tool(name, args))` (mirrors `tests/test_artifacts.py`).
- **Commits:** every commit message ends with the trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Work on branch `worktree-codex+mcp-tool-exposure-profile`; do not merge to main.
- DRY, YAGNI, TDD, frequent commits. No change to the LM5D worker surface.

---

## File Structure

- **Create** `mcp_server/src/rook/mcp_tool_profiles.py` — Profile enum, resolver, name sets, pure helpers. (Tasks 1-3)
- **Create** `mcp_server/tests/test_mcp_tool_profiles.py` — pure unit tests. (Tasks 1-3)
- **Modify** `mcp_server/src/rook/server.py`:
  - add import of the new module (Task 4),
  - `list_tools()` return block (lines ~13358-13364) — apply profile filter (Task 4),
  - `call_tool()` head (after line ~20918) — readonly guard (Task 5),
  - `main()` (line ~21003) — startup fail-fast (Task 6).
- **Create** `mcp_server/tests/test_server_tool_profiles.py` — list_tools/call_tool integration + snapshot/partition tests. (Tasks 4-6)
- **Modify** `mcp_server/src/rook/doctor.py` — `_generate_codex_toml()` injects profile (Codex only). (Task 7)
- **Modify** `mcp_server/tests/test_doctor.py` — Codex-has-lean / Claude-and-shared-env-don't tests. (Task 7)
- **Modify** `install.ps1` — Codex TOML here-string injects profile. (Task 8)
- **Create** `mcp_server/tests/test_install_ps1_profile.py` — text-guard test over `install.ps1`. (Task 8)
- **Modify** docs (`CLAUDE.md`, `AGENTS.md`, `docs/`) + memory — stale count 392 → 427. (Task 9)

---

## Task 0: Worktree environment preflight

**Files:** none (environment only — no commit).

**Why:** This plan runs inside the git worktree, which has **no** Python venv. Plain `python` resolves to an unrelated interpreter and cannot import `rook`; the **main** checkout's venv imports `rook` from the main source tree, not this worktree. Create a worktree-local venv with an editable install so `import rook` resolves to **this** worktree's `src/rook`.

- [ ] **Step 1: Create the worktree venv + editable install (with test extra)**

Run from the worktree root:

```bash
cd mcp_server
uv venv .venv --python 3.12
uv pip install -e ".[test]"
```

Expected: `.venv` created at `mcp_server/.venv`; `rook-mcp` plus the `[test]` extra (`pytest`, `pytest-asyncio`, `pytest-cov`, `anyio`) installed.

- [ ] **Step 2: Verify `rook` imports from the WORKTREE source (not the main checkout)**

```bash
cd mcp_server && .venv/Scripts/python.exe -c "import rook, pathlib; print(pathlib.Path(rook.__file__).resolve())"
```

Expected: a path **under** `...\worktrees\codex+mcp-tool-exposure-profile\mcp_server\src\rook\__init__.py`. If it prints a path under `C:\UDEV\Rook\mcp_server\src` (the main checkout), **STOP and fix** before any further task — every later test would otherwise exercise the wrong tree.

- [ ] **Step 3: Confirm the venv runs the existing suite (sanity)**

```bash
cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_doctor.py -q
```

Expected: the existing doctor tests PASS — confirming the venv + import path are correct. No commit (environment only).

---

## Task 1: Profile resolver + enum (pure)

**Files:**
- Create: `mcp_server/src/rook/mcp_tool_profiles.py`
- Test: `mcp_server/tests/test_mcp_tool_profiles.py`

**Interfaces:**
- Produces: `class Profile(str, Enum)` with `FULL="full"`, `LEAN="lean"`, `READONLY="readonly"`; `ENV_VAR = "ROOK_MCP_TOOL_PROFILE"`; `class InvalidProfileError(ValueError)`; `resolve_profile(env: Mapping[str, str]) -> Profile`.

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_mcp_tool_profiles.py`:

```python
import pytest

from rook.mcp_tool_profiles import (
    ENV_VAR,
    InvalidProfileError,
    Profile,
    resolve_profile,
)


def test_absent_resolves_to_full():
    assert resolve_profile({}) is Profile.FULL


def test_empty_and_whitespace_resolve_to_full():
    assert resolve_profile({ENV_VAR: ""}) is Profile.FULL
    assert resolve_profile({ENV_VAR: "   "}) is Profile.FULL


def test_explicit_values_resolve():
    assert resolve_profile({ENV_VAR: "full"}) is Profile.FULL
    assert resolve_profile({ENV_VAR: "lean"}) is Profile.LEAN
    assert resolve_profile({ENV_VAR: "readonly"}) is Profile.READONLY


def test_values_are_normalized_case_and_whitespace():
    assert resolve_profile({ENV_VAR: "  LEAN "}) is Profile.LEAN
    assert resolve_profile({ENV_VAR: "ReadOnly"}) is Profile.READONLY


def test_invalid_value_raises_not_silent_fallback():
    with pytest.raises(InvalidProfileError) as exc:
        resolve_profile({ENV_VAR: "readonyl"})
    assert ENV_VAR in str(exc.value)
    assert "readonyl" in str(exc.value)


def test_profile_values_are_exact_strings():
    assert Profile.FULL.value == "full"
    assert Profile.LEAN.value == "lean"
    assert Profile.READONLY.value == "readonly"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_mcp_tool_profiles.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rook.mcp_tool_profiles'`.

- [ ] **Step 3: Write the minimal implementation**

Create `mcp_server/src/rook/mcp_tool_profiles.py`:

```python
"""Public MCP tool-exposure profiles.

Single source of truth for the ``ROOK_MCP_TOOL_PROFILE`` contract. This module
is intentionally pure: it MUST NOT import ``server.py`` (one-way dependency —
``server.py`` consumes this module, never the reverse).
"""

from __future__ import annotations

from enum import Enum
from typing import Mapping

ENV_VAR = "ROOK_MCP_TOOL_PROFILE"


class Profile(str, Enum):
    FULL = "full"
    LEAN = "lean"
    READONLY = "readonly"


class InvalidProfileError(ValueError):
    """Raised when ROOK_MCP_TOOL_PROFILE is set to an unrecognized value."""


def resolve_profile(env: Mapping[str, str]) -> Profile:
    """Resolve the active profile from an environment mapping.

    Absent or empty/whitespace ⇒ FULL (backward-compatible default).
    Any other unrecognized value ⇒ InvalidProfileError (never a silent fallback).
    """
    raw = env.get(ENV_VAR)
    if raw is None:
        return Profile.FULL
    normalized = raw.strip().lower()
    if normalized == "":
        return Profile.FULL
    try:
        return Profile(normalized)
    except ValueError:
        raise InvalidProfileError(
            f"Invalid {ENV_VAR}={raw!r}. Expected one of: full, lean, readonly."
        ) from None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_mcp_tool_profiles.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/mcp_tool_profiles.py mcp_server/tests/test_mcp_tool_profiles.py
git commit -m "feat(mcp-profile): pure resolve_profile + Profile enum" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Pinned tool-name constants + structural invariants (pure)

**Files:**
- Modify: `mcp_server/src/rook/mcp_tool_profiles.py`
- Test: `mcp_server/tests/test_mcp_tool_profiles.py`

**Interfaces:**
- Produces: `PUBLIC_LEAN_TOOL_NAMES` (frozenset, 17), `PUBLIC_READONLY_TOOL_NAMES` (frozenset, 145), `SENTINEL_TOOL_NAMES` (frozenset, 26).

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_mcp_tool_profiles.py`:

```python
from rook.mcp_tool_profiles import (
    PUBLIC_LEAN_TOOL_NAMES,
    PUBLIC_READONLY_TOOL_NAMES,
    SENTINEL_TOOL_NAMES,
)


def test_set_sizes_are_pinned():
    assert len(PUBLIC_LEAN_TOOL_NAMES) == 17
    assert len(PUBLIC_READONLY_TOOL_NAMES) == 145
    assert len(SENTINEL_TOOL_NAMES) == 26


def test_readonly_is_disjoint_from_sentinels():
    # The safety boundary: no sentinel may ever be in the readonly allowlist.
    assert PUBLIC_READONLY_TOOL_NAMES.isdisjoint(SENTINEL_TOOL_NAMES)


def test_lean_is_not_a_subset_of_readonly():
    # lean is a *context* surface that must do work; it deliberately includes
    # 5 mutators not in the *safety* readonly surface.
    lean_only = PUBLIC_LEAN_TOOL_NAMES - PUBLIC_READONLY_TOOL_NAMES
    assert lean_only == {
        "gh_edit",
        "rhino_execute_intent",
        "gh_execute_intent",
        "rhino_set_active_instance",
        "rhino_clear_active_instance",
    }


def test_named_sentinels_present():
    # Spot-check the easy "not geometry-creation ⇒ readonly" fallacy names.
    for name in ("rhino_select", "rhino_layer_visibility", "gh_edit", "rhino_create"):
        assert name in SENTINEL_TOOL_NAMES
        assert name not in PUBLIC_READONLY_TOOL_NAMES
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_mcp_tool_profiles.py -k "set_sizes or disjoint or subset or sentinels" -v`
Expected: FAIL — `ImportError: cannot import name 'PUBLIC_LEAN_TOOL_NAMES'`.

- [ ] **Step 3: Add the constants**

Append to `mcp_server/src/rook/mcp_tool_profiles.py` (copy the literals **verbatim** — they are the pinned contract from the design spec §4 and §5.5):

```python
# --- Pinned name sets (design spec §4, §5.4, §5.5) -------------------------

PUBLIC_LEAN_TOOL_NAMES = frozenset({
    "rhino_ping",
    "rhino_instances",
    "rhino_sessions",
    "rhino_session_capabilities",
    "rhino_get_active_instance",
    "rhino_set_active_instance",
    "rhino_clear_active_instance",
    "knowledge_query",
    "rhino_knowledge_query",
    "gh_knowledge_query",
    "rhino_objects",
    "rhino_geometry",
    "gh_snapshot",
    "gh_errors",
    "gh_edit",
    "rhino_execute_intent",
    "gh_execute_intent",
})

SENTINEL_TOOL_NAMES = frozenset({
    "rhino_select",
    "rhino_deselect",
    "rhino_select_all",
    "rhino_select_none",
    "rhino_select_invert",
    "rhino_select_by_name",
    "rhino_select_by_type",
    "rhino_layer_visibility",
    "rhino_layer_lock",
    "rhino_layer_current",
    "gh_edit",
    "gh_clear",
    "gh_bake_output",
    "rhino_create",
    "rhino_transform",
    "rhino_delete",
    "rhino_boolean",
    "capture_script_artifact",
    "gh_add_pattern",
    "knowledge_record",
    "spawn_agent",
    "plan_and_execute",
    "rhino_execute",
    "rhino_command",
    "rhino_execute_intent",
    "gh_execute_intent",
})

PUBLIC_READONLY_TOOL_NAMES = frozenset({
    "agent_status",
    "gh_batch_component_info",
    "gh_categories",
    "gh_constraints",
    "gh_errors",
    "gh_get_reference",
    "gh_inspect_output",
    "gh_knowledge_query",
    "gh_library",
    "gh_migration_status",
    "gh_pattern_links",
    "gh_pattern_stats",
    "gh_query_observations",
    "gh_query_patterns",
    "gh_selection",
    "gh_session_current",
    "gh_session_history",
    "gh_snapshot",
    "gh_status",
    "gh_structure_query",
    "gh_validate_latency",
    "gh_validate_regression",
    "gh_validate_scenarios",
    "knowledge_query",
    "metrics_summary",
    "parse_command",
    "rc_assemble_route",
    "rc_build_profile",
    "rc_clothoid",
    "rc_concrete_barrier_profile",
    "rc_contour_levels",
    "rc_cross_section",
    "rc_crossing_params",
    "rc_cubic_parabola",
    "rc_deltablok_profile",
    "rc_extract_offsets",
    "rc_get_road_profile",
    "rc_guardrail_profile",
    "rc_list_road_profiles",
    "rc_ping",
    "rc_pole_spacing",
    "rc_project_offset_profile",
    "rc_roads",
    "rc_roundabout_params",
    "rc_sidewalk_profile",
    "rc_slope_profile",
    "rc_standards",
    "rc_terrain_profile",
    "rc_validate_profile",
    "rc_validate_road_profile",
    "rc_validate_style_set",
    "rc_verge_profile",
    "rc_vertical_curve",
    "rc_widening",
    "rhino_2d_to_3d_jobs",
    "rhino_2d_to_3d_models",
    "rhino_2d_to_3d_result",
    "rhino_2d_to_3d_status",
    "rhino_analyze_prompt",
    "rhino_artifacts",
    "rhino_block_compare",
    "rhino_block_find_instances",
    "rhino_block_info",
    "rhino_block_instances",
    "rhino_block_layer_census",
    "rhino_block_nested",
    "rhino_block_objects_detailed",
    "rhino_blocks",
    "rhino_brep_edges",
    "rhino_brep_faces",
    "rhino_brep_vertices",
    "rhino_closest_point",
    "rhino_command_knowledge",
    "rhino_command_observations",
    "rhino_command_queue",
    "rhino_curvature_curve",
    "rhino_curvature_surface",
    "rhino_curve_frame",
    "rhino_curve_point_at",
    "rhino_curve_tangent",
    "rhino_declared_targets",
    "rhino_director_curve_samples",
    "rhino_display_modes",
    "rhino_document",
    "rhino_draft_angle",
    "rhino_geometry",
    "rhino_get_active_instance",
    "rhino_gumball_history",
    "rhino_gumball_status",
    "rhino_instances",
    "rhino_is_closed",
    "rhino_is_valid",
    "rhino_knowledge_query",
    "rhino_layer_dependencies",
    "rhino_layers",
    "rhino_learning_progress",
    "rhino_linetypes",
    "rhino_materials",
    "rhino_measure_area",
    "rhino_measure_bbox",
    "rhino_measure_centroid",
    "rhino_measure_distance",
    "rhino_measure_length",
    "rhino_measure_volume",
    "rhino_merge_contract_validate",
    "rhino_objects",
    "rhino_ping",
    "rhino_planned_contracts",
    "rhino_selection",
    "rhino_session_capabilities",
    "rhino_sessions",
    "rhino_surface_normal",
    "rhino_usertext_document_get",
    "rhino_usertext_object_get",
    "rhino_validate_export",
    "rhino_video_estimate",
    "rhino_video_jobs",
    "rhino_video_models",
    "rhino_video_result",
    "rhino_video_status",
    "rhino_views",
    "rhino_vision_artifacts",
    "rhino_vision_get_artifact",
    "rhino_work_units",
    "rhino_workbench_list",
    "road_intersection_candidates",
    "rookbim_active_document",
    "rookbim_element_info",
    "rookbim_element_parameters",
    "rookbim_list_categories",
    "rookbim_query_elements",
    "rookbim_status",
    "scene_bim_facts",
    "scene_context",
    "scene_graph",
    "scene_object_semantic_context",
    "scene_query",
    "scene_relationship_evidence",
    "scene_relationship_profile",
    "scene_semantic_relationships",
    "scene_stats",
    "script_library_search",
    "session_current",
    "session_history",
    "session_list",
})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_mcp_tool_profiles.py -v`
Expected: PASS (all Task 1 + Task 2 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/mcp_tool_profiles.py mcp_server/tests/test_mcp_tool_profiles.py
git commit -m "feat(mcp-profile): pin lean/readonly/sentinel name sets" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Pure filter / guard / envelope helpers

**Files:**
- Modify: `mcp_server/src/rook/mcp_tool_profiles.py`
- Test: `mcp_server/tests/test_mcp_tool_profiles.py`

**Interfaces:**
- Consumes: `Profile`, the three name sets.
- Produces:
  - `filter_tools(all_tools: Iterable[T], profile: Profile) -> list[T]` — `T` is any object with a `.name: str` attribute (e.g. an MCP `Tool`). FULL ⇒ all; LEAN ⇒ only `PUBLIC_LEAN_TOOL_NAMES`; READONLY ⇒ only `PUBLIC_READONLY_TOOL_NAMES`.
  - `tool_blocked(name: str, profile: Profile) -> bool` — `True` only when `profile is Profile.READONLY and name not in PUBLIC_READONLY_TOOL_NAMES`.
  - `profile_blocked_envelope(name: str, profile: Profile) -> dict` — the exact rejection envelope.

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_mcp_tool_profiles.py`:

```python
from collections import namedtuple

from rook.mcp_tool_profiles import (
    filter_tools,
    profile_blocked_envelope,
    tool_blocked,
)

_StubTool = namedtuple("_StubTool", "name")


def _names(tools):
    return {t.name for t in tools}


def test_filter_tools_full_returns_all():
    tools = [_StubTool("rhino_create"), _StubTool("rhino_ping"), _StubTool("gh_align")]
    assert filter_tools(tools, Profile.FULL) == tools


def test_filter_tools_lean_keeps_only_lean_names():
    tools = [_StubTool("rhino_ping"), _StubTool("rhino_create"), _StubTool("gh_edit")]
    assert _names(filter_tools(tools, Profile.LEAN)) == {"rhino_ping", "gh_edit"}


def test_filter_tools_readonly_keeps_only_readonly_names():
    tools = [_StubTool("rhino_objects"), _StubTool("rhino_create"), _StubTool("gh_edit")]
    assert _names(filter_tools(tools, Profile.READONLY)) == {"rhino_objects"}


def test_tool_blocked_only_in_readonly_for_non_allowlisted():
    assert tool_blocked("rhino_create", Profile.READONLY) is True
    assert tool_blocked("rhino_objects", Profile.READONLY) is False
    # lean is list-only — never blocks at call_tool
    assert tool_blocked("rhino_create", Profile.LEAN) is False
    assert tool_blocked("rhino_create", Profile.FULL) is False


def test_profile_blocked_envelope_shape():
    env = profile_blocked_envelope("rhino_create", Profile.READONLY)
    assert env == {
        "success": False,
        "data": {
            "code": "tool_profile_blocked",
            "tool": "rhino_create",
            "profile": "readonly",
        },
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_mcp_tool_profiles.py -k "filter_tools or tool_blocked or envelope" -v`
Expected: FAIL — `ImportError: cannot import name 'filter_tools'`.

- [ ] **Step 3: Add the helpers**

Append to `mcp_server/src/rook/mcp_tool_profiles.py` (add `Iterable`, `Any`, `List` to the typing import at the top: `from typing import Any, Iterable, List, Mapping`):

```python
def filter_tools(all_tools: Iterable[Any], profile: Profile) -> List[Any]:
    """Return the subset of tools advertised under ``profile``.

    Each item must expose a ``.name`` attribute. FULL returns every tool
    unchanged; LEAN/READONLY keep only their pinned name sets.
    """
    if profile is Profile.FULL:
        return list(all_tools)
    allowed = PUBLIC_LEAN_TOOL_NAMES if profile is Profile.LEAN else PUBLIC_READONLY_TOOL_NAMES
    return [tool for tool in all_tools if tool.name in allowed]


def tool_blocked(name: str, profile: Profile) -> bool:
    """Whether a call to ``name`` must be rejected under ``profile``.

    Only ``readonly`` is an enforced wall (default-deny). ``lean`` is
    advertisement-only and never blocks a call.
    """
    return profile is Profile.READONLY and name not in PUBLIC_READONLY_TOOL_NAMES


def profile_blocked_envelope(name: str, profile: Profile) -> dict:
    """The Rhino-bridge-style result envelope for a profile-blocked call."""
    return {
        "success": False,
        "data": {
            "code": "tool_profile_blocked",
            "tool": name,
            "profile": profile.value,
        },
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_mcp_tool_profiles.py -v`
Expected: PASS (all module tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/mcp_tool_profiles.py mcp_server/tests/test_mcp_tool_profiles.py
git commit -m "feat(mcp-profile): pure filter_tools/tool_blocked/envelope helpers" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Wire `list_tools()` filter + live snapshot & partition tests

**Files:**
- Modify: `mcp_server/src/rook/server.py` (import near line 57; return block lines ~13358-13364)
- Create: `mcp_server/tests/test_server_tool_profiles.py`

**Interfaces:**
- Consumes: `resolve_profile`, `filter_tools`, `PUBLIC_LEAN_TOOL_NAMES`, `PUBLIC_READONLY_TOOL_NAMES`, `SENTINEL_TOOL_NAMES` from `mcp_tool_profiles`.
- Produces: `server.list_tools()` now returns the profile-filtered tool list.

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_server_tool_profiles.py`:

```python
import asyncio

import pytest

from rook import server
from rook.mcp_tool_profiles import (
    PUBLIC_LEAN_TOOL_NAMES,
    PUBLIC_READONLY_TOOL_NAMES,
    SENTINEL_TOOL_NAMES,
)

_GATED = {"rhino_command_experiment", "rhino_learn_next", "rhino_prepare_geometry"}


def _list_names(monkeypatch, profile_value):
    # Default flag-off state so the live surface is the canonical 427.
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    monkeypatch.delenv("ROOK_MCP_TARGET_MODE", raising=False)
    if profile_value is None:
        monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
    else:
        monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile_value)
    tools = asyncio.run(server.list_tools())
    return {t.name for t in tools}


def test_full_surface_is_427_and_gates_deprecated(monkeypatch):
    full = _list_names(monkeypatch, None)  # absent ⇒ full
    assert len(full) == 427
    assert _GATED.isdisjoint(full)
    assert PUBLIC_LEAN_TOOL_NAMES <= full
    assert PUBLIC_READONLY_TOOL_NAMES <= full
    assert SENTINEL_TOOL_NAMES <= full


def test_explicit_full_equals_absent(monkeypatch):
    assert _list_names(monkeypatch, "full") == _list_names(monkeypatch, None)


def test_lean_surface_is_exactly_17(monkeypatch):
    lean = _list_names(monkeypatch, "lean")
    assert lean == set(PUBLIC_LEAN_TOOL_NAMES)
    assert len(lean) == 17


def test_readonly_surface_is_exactly_145(monkeypatch):
    ro = _list_names(monkeypatch, "readonly")
    assert ro == set(PUBLIC_READONLY_TOOL_NAMES)
    assert len(ro) == 145


def test_readonly_partition_over_live_surface(monkeypatch):
    full = _list_names(monkeypatch, None)
    ro = set(PUBLIC_READONLY_TOOL_NAMES)
    assert ro <= full
    assert ro.isdisjoint(SENTINEL_TOOL_NAMES)
    excluded = full - ro
    assert ro | excluded == full          # no gaps
    assert ro.isdisjoint(excluded)        # no overlap
    assert len(ro) + len(excluded) == len(full) == 427
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_server_tool_profiles.py -v`
Expected: FAIL — `test_lean_surface_is_exactly_17` and `test_readonly_surface_is_exactly_145` fail (unfiltered `list_tools()` returns 427 for every profile). `test_full_surface_is_427...` should already PASS.

- [ ] **Step 3: Add the import to `server.py`**

Immediately after the existing `from .bridge import ...` line (`server.py:57`), add:

```python
from .mcp_tool_profiles import (
    InvalidProfileError,
    filter_tools,
    profile_blocked_envelope,
    resolve_profile,
    tool_blocked,
)
```

- [ ] **Step 4: Apply the profile filter in `list_tools()`**

Replace the return block at the end of `list_tools()` (`server.py:13358-13364`):

```python
    if not _interactive_command_learning_enabled():
        return [
            tool for tool in all_tools
            if tool.name not in _DEPRECATED_INTERACTIVE_COMMAND_TOOLS
        ]

    return all_tools
```

with:

```python
    if not _interactive_command_learning_enabled():
        live_tools = [
            tool for tool in all_tools
            if tool.name not in _DEPRECATED_INTERACTIVE_COMMAND_TOOLS
        ]
    else:
        live_tools = all_tools

    return filter_tools(live_tools, resolve_profile(os.environ))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_server_tool_profiles.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/server.py mcp_server/tests/test_server_tool_profiles.py
git commit -m "feat(mcp-profile): filter list_tools() by active profile" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `call_tool()` readonly wall + rejection / no-side-effect / lean-list-only tests

**Files:**
- Modify: `mcp_server/src/rook/server.py` (`call_tool()` head, after line ~20918)
- Modify: `mcp_server/tests/test_server_tool_profiles.py`

**Interfaces:**
- Consumes: `resolve_profile`, `tool_blocked`, `profile_blocked_envelope`, `_format_tool_result` (existing in `server.py`).
- Produces: under `readonly`, `call_tool(name, args)` returns the `tool_profile_blocked` envelope for non-allowlisted tools **before** any targeting/observation side effects.

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_server_tool_profiles.py`:

```python
def _call_text(name, args=None):
    result = asyncio.run(server.call_tool(name, args or {}))
    return result[0].text


def _blocked_payload(text):
    # _format_tool_result renders failures as 'Error: ' + json.dumps(data, indent=2).
    import json

    assert text.startswith("Error: ")
    return json.loads(text[len("Error: "):])


def test_readonly_block_returns_exact_payload(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    payload = _blocked_payload(_call_text("rhino_create"))
    assert payload == {
        "code": "tool_profile_blocked",
        "tool": "rhino_create",
        "profile": "readonly",
    }


@pytest.mark.parametrize(
    "mutator",
    ["rhino_layer_visibility", "rhino_select", "gh_edit", "rhino_transform", "rhino_create"],
)
def test_readonly_blocks_representative_mutators(monkeypatch, mutator):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    assert "tool_profile_blocked" in _call_text(mutator)


def test_readonly_allows_allowlisted_tool_past_the_guard(monkeypatch):
    # rhino_objects is in the allowlist — the guard must NOT block it.
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    assert "tool_profile_blocked" not in _call_text("rhino_objects")


def test_lean_is_list_only_does_not_block_calls(monkeypatch):
    # A mutator NOT in lean must still be callable under lean (list-only).
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    assert "tool_profile_blocked" not in _call_text("rhino_create")


def test_full_does_not_block_calls(monkeypatch):
    monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
    assert "tool_profile_blocked" not in _call_text("rhino_create")


def test_blocked_readonly_call_has_no_side_effects(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    calls = {"observed": False, "policy": False, "dispatched": False}

    def _spy_observe(*a, **k):
        calls["observed"] = True

    def _spy_policy(*a, **k):
        calls["policy"] = True
        raise AssertionError("policy_for_tool must not run for a blocked call")

    async def _spy_dispatch(*a, **k):
        calls["dispatched"] = True
        return {"success": True, "data": {}}

    monkeypatch.setattr(server, "_record_observation", _spy_observe)
    monkeypatch.setattr(server.targeting, "policy_for_tool", _spy_policy)
    monkeypatch.setattr(server, "_call_tool_dispatch", _spy_dispatch)

    text = _call_text("rhino_create")
    assert "tool_profile_blocked" in text
    assert calls == {"observed": False, "policy": False, "dispatched": False}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_server_tool_profiles.py -k "readonly_blocks or no_side_effects" -v`
Expected: FAIL — no guard yet, so blocked-mutator calls do not contain `tool_profile_blocked` (and `policy_for_tool` runs).

- [ ] **Step 3: Insert the readonly guard at the head of `call_tool()`**

In `call_tool()`, immediately after the argument-normalization line (`server.py:20918`):

```python
    arguments = dict(arguments) if arguments else {}
```

insert the guard (before the existing `_DEPRECATED_INTERACTIVE_COMMAND_TOOLS` branch and before `targeting.policy_for_tool`):

```python
    _active_profile = resolve_profile(os.environ)
    if tool_blocked(name, _active_profile):
        return _format_tool_result(profile_blocked_envelope(name, _active_profile))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_server_tool_profiles.py -v`
Expected: PASS (all Task 4 + Task 5 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/server.py mcp_server/tests/test_server_tool_profiles.py
git commit -m "feat(mcp-profile): readonly call_tool wall with no-side-effect denial" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Startup fail-fast on invalid profile

**Files:**
- Modify: `mcp_server/src/rook/server.py` (`main()` line ~21003; add `_validate_profile_or_exit`)
- Modify: `mcp_server/tests/test_server_tool_profiles.py`

**Interfaces:**
- Produces: `server._validate_profile_or_exit()` — raises `SystemExit(2)` on `InvalidProfileError`, returns `None` on a valid profile. Called first inside `main()`.

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_server_tool_profiles.py`:

```python
def test_validate_profile_or_exit_raises_on_invalid(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "bogus")
    with pytest.raises(SystemExit) as exc:
        server._validate_profile_or_exit()
    assert exc.value.code == 2


def test_validate_profile_or_exit_passes_on_valid(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    assert server._validate_profile_or_exit() is None


def test_validate_profile_or_exit_passes_when_absent(monkeypatch):
    monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
    assert server._validate_profile_or_exit() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_server_tool_profiles.py -k "validate_profile_or_exit" -v`
Expected: FAIL — `AttributeError: module 'rook.server' has no attribute '_validate_profile_or_exit'`.

- [ ] **Step 3: Add the helper and call it from `main()`**

Add this function just above `def main():` (`server.py:21003`):

```python
def _validate_profile_or_exit() -> None:
    """Fail fast at startup if ROOK_MCP_TOOL_PROFILE is invalid."""
    import sys

    try:
        resolve_profile(os.environ)
    except InvalidProfileError as exc:
        sys.stderr.write(f"FATAL: {exc}\n")
        raise SystemExit(2)
```

Then, inside `main()`, add the call as the first line of the body (after the docstring, before `import asyncio`):

```python
def main():
    """Run the MCP server."""
    _validate_profile_or_exit()
    import asyncio
    import sys
    ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_server_tool_profiles.py -k "validate_profile_or_exit" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/server.py mcp_server/tests/test_server_tool_profiles.py
git commit -m "feat(mcp-profile): startup fail-fast on invalid ROOK_MCP_TOOL_PROFILE" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: `doctor.py` Codex-only profile injection

**Files:**
- Modify: `mcp_server/src/rook/doctor.py` (`_generate_codex_toml`, line ~82)
- Modify: `mcp_server/tests/test_doctor.py`

**Interfaces:**
- Consumes: `ENV_VAR` from `mcp_tool_profiles`.
- Produces: `_generate_codex_toml(...)` output includes `ROOK_MCP_TOOL_PROFILE = "lean"`; `_build_expected_env(...)` and `_build_expected_mcp_entry(...)["env"]` (Claude) do **not**.

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_doctor.py` (the `_runtime_paths` helper and `import rook.doctor as doctor` already exist at the top of this file):

```python
from rook.mcp_tool_profiles import ENV_VAR as PROFILE_ENV_VAR


def test_codex_toml_sets_lean_profile(tmp_path: Path):
    rp = _runtime_paths(tmp_path)
    toml = doctor._generate_codex_toml(rp, python_path="/usr/bin/python")
    assert f'{PROFILE_ENV_VAR} = "lean"' in toml


def test_shared_env_has_no_profile_key(tmp_path: Path):
    rp = _runtime_paths(tmp_path)
    assert PROFILE_ENV_VAR not in doctor._build_expected_env(rp)


def test_claude_entry_env_has_no_profile_key(tmp_path: Path):
    rp = _runtime_paths(tmp_path)
    entry = doctor._build_expected_mcp_entry(rp, python_path="/usr/bin/python")
    assert PROFILE_ENV_VAR not in entry["env"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_doctor.py -k "lean_profile or no_profile_key" -v`
Expected: FAIL — `test_codex_toml_sets_lean_profile` fails (Codex TOML has no profile key yet).

- [ ] **Step 3: Inject the profile in the Codex generator only**

Add the import near the top of `doctor.py` (with the other `from .` imports):

```python
from .mcp_tool_profiles import ENV_VAR as PROFILE_ENV_VAR
```

In `_generate_codex_toml` (`doctor.py:82`), replace:

```python
    env_vars = _build_expected_env(runtime_paths, chirp_home=chirp_home)
```

with:

```python
    # External (Codex) configs default to the lean profile. This is the ONLY
    # place the profile is injected — never the shared _build_expected_env(),
    # which also feeds the Claude entry (which must stay full).
    env_vars = dict(_build_expected_env(runtime_paths, chirp_home=chirp_home))
    env_vars[PROFILE_ENV_VAR] = "lean"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_doctor.py -k "lean_profile or no_profile_key" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full doctor suite (no regressions)**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_doctor.py -v`
Expected: PASS (existing tests still green — Codex TOML gained one env line; Claude entries unchanged).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/doctor.py mcp_server/tests/test_doctor.py
git commit -m "feat(mcp-profile): doctor injects lean into Codex config only" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: `install.ps1` Codex-only profile injection + text guard

**Files:**
- Modify: `install.ps1` (the `$codexTomlScript` here-string env block, lines ~1160-1167)
- Create: `mcp_server/tests/test_install_ps1_profile.py`

**Interfaces:**
- Produces: the installer-generated Codex `config.toml` includes `ROOK_MCP_TOOL_PROFILE = "lean"`; the installer's Claude `.mcp.json` / `.claude.json` env (`$env` dict built around lines 1005/1037) does not.

- [ ] **Step 1: Write the failing text-guard test**

Create `mcp_server/tests/test_install_ps1_profile.py`:

```python
"""Text-guard over install.ps1: lean profile is Codex-only.

install.ps1 generates configs in PowerShell (Pester-free here), so we assert on
the script source: the Codex TOML here-string must add the lean profile env
line, and the Claude .mcp.json / .claude.json generation must not.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INSTALL_PS1 = _REPO_ROOT / "install.ps1"


def _text():
    return _INSTALL_PS1.read_text(encoding="utf-8")


def test_install_ps1_exists():
    assert _INSTALL_PS1.is_file()


def test_codex_here_string_sets_lean_profile():
    text = _text()
    # The Codex TOML here-string is the only block emitting `[mcp_servers.rook.env]`.
    assert "[mcp_servers.rook.env]" in text
    assert "'ROOK_MCP_TOOL_PROFILE = \"lean\"'," in text


def test_claude_mcp_json_block_has_no_lean_profile():
    text = _text()
    # The Claude project/user config is generated via the `cfg = {...}` /
    # `config['mcpServers']['rook']` Python blocks; none may set the profile.
    assert "'ROOK_MCP_TOOL_PROFILE': 'lean'" not in text
    assert '"ROOK_MCP_TOOL_PROFILE": "lean"' not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_install_ps1_profile.py -v`
Expected: FAIL — `test_codex_here_string_sets_lean_profile` fails (the env line is not present yet).

- [ ] **Step 3: Add the profile line to the Codex here-string**

In `install.ps1`, inside the `$codexTomlScript` here-string, in the `lines = [ ... ]` list, add the profile line immediately after the `ROOK_MODE` line (currently line ~1165):

```python
    f'ROOK_MODE = "{rook_mode}"',
    'ROOK_MCP_TOOL_PROFILE = "lean"',
    '',
```

(Do **not** add any `ROOK_MCP_TOOL_PROFILE` to the Claude `.mcp.json` `cfg = {...}` block near line 1005 or the `.claude.json` block near line 1037.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && .venv/Scripts/python.exe -m pytest tests/test_install_ps1_profile.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add install.ps1 mcp_server/tests/test_install_ps1_profile.py
git commit -m "feat(mcp-profile): installer injects lean into Codex config only" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: Stale-doc correction (392 → 427)

**Files:**
- Modify: `CLAUDE.md` (root and/or `Rook/CLAUDE.md`), `AGENTS.md`, any `docs/*` and `README*` that state the tool count.
- Modify: memory index/topic files under the user memory dir if they cite a tool count.

**Interfaces:** none (documentation only).

- [ ] **Step 1: Find every stale count**

Run: `cd "C:/UDEV/Rook/.claude/worktrees/codex+mcp-tool-exposure-profile" && rg -n -e "392 (MCP )?tools" -e "234 tools" -g "*.md"`
Record each hit. (Expected: `CLAUDE.md`, possibly `AGENTS.md`, `README`, `docs/`.)

- [ ] **Step 2: Correct each occurrence to 427**

For each file, replace the stale figure with **427** and, where the doc explains the surface, add the one-line note: "427 tools advertised by `list_tools()` (430 static defs minus 3 deprecated-interactive tools gated by default)." Keep wording consistent with the project's existing voice. Do **not** invent counts for unrelated metrics (handlers/routes/notes) — only the MCP tool count.

- [ ] **Step 3: Verify no stale tool-count remains**

Run: `cd "C:/UDEV/Rook/.claude/worktrees/codex+mcp-tool-exposure-profile" && rg -n -e "392 (MCP )?tools" -e "234 tools" -g "*.md"`
Expected: no output (all corrected). A remaining `430` is acceptable **only** where the text explicitly means "static definitions."

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs(mcp-profile): correct MCP tool count 392 -> 427 live surface" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage** (spec → task):
- §2 contract / resolver / invalid-fail → Tasks 1, 6.
- §3 asymmetry (lean list-only / readonly wall) → Tasks 4 (lean filter), 5 (readonly wall + lean-list-only test).
- §4 lean 17 → Tasks 2 (constant), 4 (snapshot).
- §5.1-5.5 readonly 145 + default-deny + sentinels → Tasks 2 (constants), 4 (snapshot + partition), 5 (wall).
- §5.6 enforcement point / envelope / no side effects → Tasks 3 (envelope), 5 (guard placement + no-side-effect test).
- §6 single source of truth, no server import → Tasks 1-3 (module); one-way dependency respected (module imports nothing from server).
- §7 config seams (Codex-only lean; shared-env trap) → Tasks 7 (doctor), 8 (install.ps1).
- §7.4 stale-doc → Task 9.
- §8 testing contract items 1-8 → Tasks 1/6 (resolver), 4 (snapshots #2 + partition #8), 2/4 (sentinels #3), 5 (rejection #4, no-side-effects #5, lean list-only #6), 7 (config #7).
- §5.7 annotations, §9 out-of-scope → intentionally not implemented (deferred).

**Placeholder scan:** none — every code step contains complete code; the 145/17/26 literals are pasted verbatim; commands have expected output.

**Type consistency:** `Profile`, `resolve_profile`, `filter_tools`, `tool_blocked`, `profile_blocked_envelope`, `PUBLIC_LEAN_TOOL_NAMES`, `PUBLIC_READONLY_TOOL_NAMES`, `SENTINEL_TOOL_NAMES`, `ENV_VAR`, `InvalidProfileError`, `_validate_profile_or_exit` are named identically everywhere they appear (module → server import → tests). `ENV_VAR` is imported into `doctor.py` as `PROFILE_ENV_VAR`.

**Note on `_call_tool_dispatch` vs `call_tool`:** the readonly guard goes in the outer `call_tool` (Task 5), which is what the MCP runtime invokes and what the spec §5.6 targets (before `targeting.policy_for_tool`). `_call_tool_dispatch` is the inner router used only as a spy seam in the no-side-effect test.
