# Director MCP Surface Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every Director operation from Rook's public MCP and internal-agent execution surfaces while preserving the underlying Director implementation, native routes, user artifacts, and the 17 retained public media tools.

**Architecture:** `server.call_tool()` keeps the existing readonly wall first, then applies a narrow `rhino_director_` prefix tombstone before meta-tool handling, targeting, discovery, and dispatch. The 18 Director tool definitions and dispatch cases are deleted, and the same names are removed from profiles, targeting metadata, progressive-disclosure groups, the internal agent bridge, current documentation, and actionable historical guidance. Director implementation modules and native `/director/*` routes remain available only to direct implementation/live-route tests pending the later disposition review.

**Tech Stack:** Python 3.12, MCP Python SDK, pytest/pytest-asyncio, PowerShell documentation/release guards, Markdown.

## Global Constraints

- The approved contract is `docs/superpowers/specs/2026-07-13-director-mcp-surface-retirement-design.md`.
- Retire all 18 named `rhino_director_*` tools plus the already-unadvertised migration helper and any future name under that prefix.
- Preserve readonly non-enumeration: readonly applies its default-deny wall before the tombstone; full and lean return canonical `Unknown tool` before any target work.
- Do not create a global dispatch-membership guard. `_DISPATCHABLE_TOOL_NAMES` remains best-effort progressive-disclosure metadata and never controls direct dispatch admission.
- Do not add a Director-specific deprecation envelope, alias, environment flag, or compatibility path.
- Do not remove native `/director/*` routes, managed CanvasDirector code, Python Director implementation modules, direct implementation tests, release artifact preservation, or user data.
- Keep the 17 media sentinels' existing discovery, dispatch, profile, and targeting contracts unchanged.
- Exact post-change profile counts are: full/default `428`, lean `22`, readonly `148`; static `Tool(...)` definitions are `431`, with 3 deprecated-interactive definitions gated by default.
- No changes are made in `rook2` or RookStudio.
- In the feature worktree, create and use that worktree's own `mcp_server/.venv` with `uv sync --extra test`; do not reuse or junction the primary checkout's environment. Before baseline tests or subagent execution, verify `rook.__file__` resolves under the feature worktree. Add no dependency.
- Run every pytest command from the repository root with `mcp_server/.venv/Scripts/python.exe` and repository-root-relative test paths. Do not `cd mcp_server` for pytest.
- Work on `codex/director-mcp-surface-retirement`; do not modify `main` directly.

---

## Pre-Implementation Differential Baseline

Before Task 1, keep the worktree-local virtual environment unchanged and run this full non-live gate from the repository root:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests -m "not requires_rhino" -q
```

Record the exact failed/error node IDs and pass/fail/error/skip totals. Pre-existing failures do not authorize repairs to `main` and do not block this retirement. All new and retirement-focused tests must pass. At final verification, rerun the same command in the same environment: it may retain the recorded pre-existing failed/error node IDs, but it must introduce no new failed/error node IDs. Live-Rhino tests remain a separate, explicitly enabled gate.

---

## File Structure

### Create

- `mcp_server/tests/test_director_mcp_retirement.py` — one contract-focused regression suite for discovery, direct and meta dispatch ordering, secondary registries, retained media sentinels, scanner failure, documentation, installed assets, and artifact preservation.

### Modify

- `mcp_server/src/rook/server.py` — delete 18 `Tool` definitions and dispatch cases, remove now-unused Director imports, scrub the four meta-tool contracts, and add the narrow post-readonly tombstone.
- `mcp_server/src/rook/mcp_tool_profiles.py` — remove the retired readonly curve-sampling entry.
- `mcp_server/src/rook/targeting.py` — remove all Director names from callable targeting classifications.
- `mcp_server/src/rook/agent/tool_groups.py` — remove Director groups, readonly admission, and MCP-only group metadata.
- `mcp_server/src/rook/agent/tool_dispatcher.py` — remove the direct curve-samples bridge route.
- `mcp_server/tests/test_mcp_tool_profiles.py` — pin the new readonly count and absence contract.
- `mcp_server/tests/test_server_tool_profiles.py` — pin exact post-retirement profile counts and partitions.
- `mcp_server/tests/test_multi_instance_targeting.py` — replace positive Director targeting tests with absence checks.
- `mcp_server/tests/test_rook_tools_meta.py` — use non-Director fixtures for the still-active progressive-disclosure architecture and test retired meta targets.
- `mcp_server/tests/test_capability_index.py` — use retained video fixtures instead of Director fixtures.
- `mcp_server/tests/test_director_routes_live.py` — exercise retained video assembly/publishing modules directly rather than through retired wrappers.
- `mcp_server/tests/test_director_actor_set_builder_live.py` — exercise retained actor metadata primitives directly.
- `mcp_server/tests/test_director_take_package.py` — remove wrapper-only registration/dispatch coverage.
- `mcp_server/tests/test_director_worker_prepare.py` — remove wrapper-only dispatch coverage.
- `mcp_server/tests/test_director_worker_compile.py` — remove wrapper-only dispatch coverage.
- `mcp_server/tests/test_director_worker_play.py` — remove wrapper-only dispatch coverage.
- `mcp_server/tests/test_director_worker_capture.py` — remove wrapper-only dispatch/error-envelope coverage.
- `README.md`, `AGENTS.md`, `docs/CURRENT_ARCHITECTURE.md`, `docs/AGENT_ARCHITECTURE.md` — state the measured 428-tool contract and the new product boundary.
- `docs/rook_docs/work-queue.md` and `docs/rook_docs/2026-04-15-typed-route-gap-analysis.md` — add dated retirement notices without rewriting evidence.
- Every tracked Markdown document matched by the route-aware Director audit — add a precise partial-supersession notice unless it is one of the two current retirement documents or one of the four explicitly classified historical-evidence documents.

### Delete

- `mcp_server/tests/test_director_mcp_tools.py` — this file exclusively asserts the public MCP contract being retired; retained implementation behavior is covered in the module-specific tests.

### Intentionally Unchanged

- `mcp_server/src/rook/capability_index.py` — the generic longest-prefix domain classifier may remain because records are built only from live tool definitions and cannot synthesize a callable Director record.
- `mcp_server/src/rook/director*.py`, `mcp_server/src/rook/canvas_director.py`, and `mcp_server/src/rook/canvas_director_templates/**` — preserved for the next disposition pass.
- `src/RookNative/**`, `src/Rook/**`, and native `/director/*` route tests — preserved implementation boundary.
- `docs/TROUBLESHOOTING.md` — its dated replay incident remains historical operational evidence, not current guidance.
- `scripts/tests/release-installer-guards.tests.ps1` — its `RookVisionDirector` artifact-root protection remains active.

---

### Task 1: Retire Director discovery and direct dispatch at the MCP boundary

**Files:**
- Create: `mcp_server/tests/test_director_mcp_retirement.py`
- Modify: `mcp_server/src/rook/mcp_tool_profiles.py:103-258`
- Modify: `mcp_server/src/rook/server.py:74`
- Modify: `mcp_server/src/rook/server.py:3717-4479`
- Modify: `mcp_server/src/rook/server.py:13854-13920`
- Modify: `mcp_server/src/rook/server.py:21108-21279`
- Modify: `mcp_server/src/rook/server.py:21791-21818`

**Interfaces:**
- Consumes: `resolve_profile()`, `tool_blocked()`, `_format_tool_result()`, and the existing canonical `Unknown tool: <name>` text.
- Produces: a direct-call boundary where readonly blocks first and full/lean reject every `rhino_director_*` name before targeting or dispatch.

- [ ] **Step 1: Write the failing discovery and direct-call contract tests**

Create `mcp_server/tests/test_director_mcp_retirement.py` with this initial content:

```python
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from rook import server


RETIRED_DIRECTOR_TOOLS = (
    "rhino_director_run",
    "rhino_director_curve_samples",
    "rhino_director_assemble_video",
    "rhino_director_publish_video",
    "rhino_director_canvas_extract",
    "rhino_director_replay",
    "rhino_director_replay_cancel",
    "rhino_director_compile_motion",
    "rhino_director_package_take",
    "rhino_director_prepare_take",
    "rhino_director_compile_take",
    "rhino_director_worker_play",
    "rhino_director_capture_take",
    "rhino_director_preview_motion",
    "rhino_director_capture_source_occurrence_v2",
    "rhino_director_build_actor_set_from_source_occurrence_v2",
    "rhino_director_write_actor_metadata_v2",
    "rhino_director_read_actor_metadata_v2",
)

DIRECTOR_PREFIX_PROBES = RETIRED_DIRECTOR_TOOLS + (
    "rhino_director_migrate_actor_metadata_v2",
    "rhino_director_future_probe",
)


def _serialized_tools(tools) -> str:
    return json.dumps(
        [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema,
            }
            for tool in tools
        ],
        sort_keys=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ("full", "lean", "readonly"))
async def test_serialized_discovery_contains_no_director_guidance(monkeypatch, profile):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
    payload = _serialized_tools(await server.list_tools())
    lowered = payload.lower()
    assert "rhino_director_" not in lowered
    assert "/director" not in lowered
    assert "visiondirector" not in lowered
    assert '\"director\"' not in lowered


def _forbidden_sync(label):
    def fail(*args, **kwargs):
        raise AssertionError(f"{label} must not run")

    return fail


def _forbidden_async(label):
    async def fail(*args, **kwargs):
        raise AssertionError(f"{label} must not run")

    return fail


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ("full", "lean", "readonly"))
@pytest.mark.parametrize("tool_name", DIRECTOR_PREFIX_PROBES)
async def test_director_prefix_stops_before_targeting_and_dispatch(
    monkeypatch, profile, tool_name
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
    discovery_calls = []

    def no_live_instances():
        discovery_calls.append("entered")
        return []

    monkeypatch.setattr(
        server.targeting, "policy_for_tool", _forbidden_sync("targeting policy")
    )
    monkeypatch.setattr(
        server.targeting,
        "get_panel_target_config_error",
        _forbidden_sync("panel policy"),
    )
    monkeypatch.setattr(
        server.targeting, "get_panel_target_lock", _forbidden_sync("panel lock")
    )
    monkeypatch.setattr(
        server.targeting, "discover_instances", no_live_instances
    )
    monkeypatch.setattr(
        server.targeting, "resolve_tool_route", _forbidden_sync("target resolution")
    )
    monkeypatch.setattr(
        server, "_call_tool_dispatch", _forbidden_async("tool dispatch")
    )

    result = await server.call_tool(
        tool_name,
        {"port": 9950, "session": "conflicting-target"},
    )
    text = result[0].text
    if profile == "readonly":
        assert "tool_profile_blocked" in text
        assert tool_name in text
    else:
        assert text == f"Error: Unknown tool: {tool_name}"
    assert discovery_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ("full", "lean", "readonly"))
async def test_non_director_unknown_keeps_existing_policy_path(monkeypatch, profile):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
    calls = []

    def policy_for_tool(name):
        calls.append(("policy", name))
        return SimpleNamespace(requires_rhino=False)

    async def dispatch(name, arguments):
        calls.append(("dispatch", name))
        return {"success": False, "data": f"Unknown tool: {name}"}

    monkeypatch.setattr(server.targeting, "policy_for_tool", policy_for_tool)
    monkeypatch.setattr(server, "_call_tool_dispatch", dispatch)
    result = await server.call_tool("rhino_unknown_future_probe", {})

    if profile == "readonly":
        assert "tool_profile_blocked" in result[0].text
        assert calls == []
    else:
        assert result[0].text == "Error: Unknown tool: rhino_unknown_future_probe"
        assert calls == [
            ("policy", "rhino_unknown_future_probe"),
            ("dispatch", "rhino_unknown_future_probe"),
        ]


def test_server_has_no_active_director_runtime_imports():
    for attribute in (
        "canvas_director",
        "director",
        "director_actor_metadata",
        "director_compiler",
        "director_preview",
        "director_publish",
        "director_take_package",
        "director_video",
        "director_worker_capture",
        "director_worker_compile",
        "director_worker_play",
        "director_worker_prepare",
    ):
        assert not hasattr(server, attribute), attribute


def test_director_case_labels_are_absent():
    labels = server._scan_dispatch_case_labels()
    assert set(DIRECTOR_PREFIX_PROBES).isdisjoint(labels)
```

- [ ] **Step 2: Run the tests and confirm the current surface fails**

Run from the repository root:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_mcp_retirement.py -q
```

Expected: FAIL because Director names and metadata are still advertised, direct calls reach targeting/dispatch, and the 18 case labels still exist.

- [ ] **Step 3: Remove the 18 public tool definitions and their runtime imports**

In `server.py`:

- Delete the contiguous 18 Director `Tool(...)` blocks beginning with `rhino_director_run` and ending with `rhino_director_read_actor_metadata_v2`.
- Delete the contiguous 18 `_call_tool_dispatch()` cases with the same names.
- Delete `rhino_director_curve_samples` from `PUBLIC_READONLY_TOOL_NAMES`; otherwise that retired read tool would bypass the readonly wall and reveal the tombstone.
- Replace the broad import line so the server no longer imports Director runtime modules solely for those deleted cases:

```python
from . import artifacts, merge_execution, script_library, targeting, workbench, work_units
```

Do not delete any of the imported modules from disk.

- [ ] **Step 4: Scrub the four serialized meta-tool contracts**

Use these non-Director examples in the existing four `Tool(...)` objects:

```python
# rook_tools_ls description
"under a domain/group path (e.g. '/', '/rhino', '/gh', '/video'). Returns compact "

# rook_tools_search description/domain property
"summary each. Covers the full tool surface — geometry, Grasshopper, vision, "
"RoadCreator, BIM, scene, video, knowledge. Use this to discover a tool, then "
"domain": {"type": "string", "description": "Optional domain filter, e.g. 'rhino', 'gh', 'video', 'bim'."},

# rook_tools_read name property
"name": {"type": "string", "description": "Exact tool name, e.g. 'rhino_video_models'."},
```

Keep the existing hidden-GH guidance and `rook_tools_call` behavior unchanged.

- [ ] **Step 5: Add the narrow tombstone at the approved ordering seam**

Immediately after the readonly profile wall in `call_tool()` and before the meta-tool branch, add:

```python
    if name.startswith("rhino_director_"):
        return _format_tool_result(
            {"success": False, "data": f"Unknown tool: {name}"}
        )
```

The resulting opening order must be exactly:

```python
    arguments = dict(arguments) if arguments else {}
    _active_profile = resolve_profile(os.environ)
    if tool_blocked(name, _active_profile):
        return _format_tool_result(profile_blocked_envelope(name, _active_profile))

    if name.startswith("rhino_director_"):
        return _format_tool_result(
            {"success": False, "data": f"Unknown tool: {name}"}
        )

    if name in META_TOOL_NAMES:
        return await _handle_meta_tool(name, arguments, _active_profile)
```

- [ ] **Step 6: Run the new contract and the existing server contract suite**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_mcp_retirement.py mcp_server/tests/test_server_contract_hardening.py -q
```

Expected: the new retirement tests PASS; server hardening tests PASS. Other existing tests are not expected to be green until Tasks 2 and 3 replace positive Director assertions.

- [ ] **Step 7: Commit the MCP boundary retirement**

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/mcp_tool_profiles.py mcp_server/tests/test_director_mcp_retirement.py
git commit -m "refactor: retire Director MCP boundary"
```

---

### Task 2: Remove secondary callable surfaces and protect retained media

**Files:**
- Modify: `mcp_server/tests/test_director_mcp_retirement.py`
- Modify: `mcp_server/src/rook/targeting.py:148-800`
- Modify: `mcp_server/src/rook/agent/tool_groups.py:87-110,213-240,530-549`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py:345-346`
- Modify: `mcp_server/tests/test_mcp_tool_profiles.py`
- Modify: `mcp_server/tests/test_server_tool_profiles.py`
- Modify: `mcp_server/tests/test_multi_instance_targeting.py`
- Modify: `mcp_server/tests/test_rook_tools_meta.py`
- Modify: `mcp_server/tests/test_capability_index.py`

**Interfaces:**
- Consumes: `RETIRED_DIRECTOR_TOOLS` and `DIRECTOR_PREFIX_PROBES` from Task 1.
- Produces: no Director profile, targeting, agent, inventory, catalog, or meta-dispatch record; all 17 media sentinels retain their pre-change policy.

- [ ] **Step 1: Add failing secondary-surface, meta-dispatch, and sentinel tests**

Append to `test_director_mcp_retirement.py`:

```python
from rook import targeting
from rook.agent import tool_dispatcher, tool_groups
from rook.mcp_tool_profiles import (
    PUBLIC_LEAN_TOOL_NAMES,
    PUBLIC_READONLY_TOOL_NAMES,
    Profile,
)


MEDIA_SENTINELS = frozenset(
    {
        "rhino_render_video",
        "rhino_video_status",
        "rhino_video_cancel",
        "rhino_video_result",
        "rhino_video_estimate",
        "rhino_video_jobs",
        "rhino_video_models",
        "rhino_viewport",
        "rhino_capture_depth",
        "rhino_display_modes",
        "rhino_display_mode_set",
        "rhino_vision_artifacts",
        "rhino_vision_get_artifact",
        "rhino_vision_approve",
        "rhino_vision_delete_artifact",
        "rhino_vision_consume_approved",
        "rhino_vision_presentation",
    }
)

READONLY_MEDIA_SENTINELS = frozenset(
    {
        "rhino_video_status",
        "rhino_video_result",
        "rhino_video_estimate",
        "rhino_video_jobs",
        "rhino_video_models",
        "rhino_display_modes",
        "rhino_vision_artifacts",
        "rhino_vision_get_artifact",
    }
)


def test_secondary_callable_registries_contain_no_director_surface():
    assert "director" not in tool_groups.TOOL_GROUPS
    assert "director_readonly" not in tool_groups.TOOL_GROUPS
    assert "director" not in tool_groups.MCP_ONLY_GROUPS
    assert "director_readonly" not in tool_groups.READONLY_ALLOWED_GROUPS
    grouped_names = {
        name for names in tool_groups.TOOL_GROUPS.values() for name in names
    }
    assert not any(name.startswith("rhino_director_") for name in grouped_names)
    assert not any(
        name.startswith("rhino_director_")
        for name in tool_dispatcher.BRIDGE_ROUTES
    )
    assert not any(
        name.startswith("rhino_director_") for name in targeting._ALL_KNOWN_TOOLS
    )
    assert not any(
        name.startswith("rhino_director_") for name in targeting.TOOL_POLICIES
    )
    assert not any(
        name.startswith("rhino_director_") for name in PUBLIC_LEAN_TOOL_NAMES
    )
    assert not any(
        name.startswith("rhino_director_") for name in PUBLIC_READONLY_TOOL_NAMES
    )


@pytest.mark.asyncio
async def test_live_agent_inventory_contains_no_director_record():
    tools = await server._all_live_tools()
    records = server._collect_agent_records(tools)
    assert "rhino_objects" in records
    assert not any(name.startswith("rhino_director_") for name in records)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile", "expected_error"),
    (
        (Profile.FULL, "not_mcp_dispatchable"),
        (Profile.LEAN, "not_mcp_dispatchable"),
        (Profile.READONLY, "tool_profile_blocked"),
    ),
)
@pytest.mark.parametrize("tool_name", DIRECTOR_PREFIX_PROBES)
async def test_meta_dispatch_cannot_recover_director(
    monkeypatch, profile, expected_error, tool_name
):
    server._reset_capability_index_cache()

    async def forbidden_call_tool(*args, **kwargs):
        raise AssertionError("meta dispatcher must not re-enter call_tool")

    monkeypatch.setattr(server, "call_tool", forbidden_call_tool)
    result = await server._handle_meta_tool(
        "rook_tools_call",
        {"name": tool_name, "arguments": {}},
        profile,
    )
    assert expected_error in result[0].text


@pytest.mark.asyncio
async def test_progressive_catalog_has_no_director_record_or_path():
    server._reset_capability_index_cache()
    index = await server._get_capability_index()
    assert not any(record.name.startswith("rhino_director_") for record in index.records)
    assert not any(record.domain == "director" for record in index.records)
    assert index.read("rhino_director_preview_motion") is None
    root = index.ls("/", depth=1)
    assert "/director" not in root["children"]
    assert not any(entry["domain"] == "director" for entry in root["entries"])


@pytest.mark.asyncio
async def test_media_sentinels_keep_discovery_dispatch_and_targeting(monkeypatch):
    monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
    full = {tool.name for tool in await server.list_tools()}
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    lean = {tool.name for tool in await server.list_tools()}
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    readonly = {tool.name for tool in await server.list_tools()}

    assert MEDIA_SENTINELS <= full
    assert MEDIA_SENTINELS.isdisjoint(lean)
    assert MEDIA_SENTINELS & readonly == READONLY_MEDIA_SENTINELS
    assert MEDIA_SENTINELS <= server._dispatchable_tool_names()

    for name in MEDIA_SENTINELS:
        policy = targeting.policy_for_tool(name)
        assert policy.requires_rhino is True
        assert policy.risk == (
            "read" if name in READONLY_MEDIA_SENTINELS else "mutate"
        )


@pytest.mark.asyncio
async def test_scanner_failure_cannot_gate_normal_direct_dispatch(monkeypatch):
    def source_unavailable(*args, **kwargs):
        raise OSError("source unavailable in frozen build")

    monkeypatch.setattr(server.inspect, "getsource", source_unavailable)
    assert server._scan_dispatch_case_labels() == server.META_TOOL_NAMES
    monkeypatch.setattr(
        server, "_DISPATCHABLE_TOOL_NAMES", server.META_TOOL_NAMES
    )
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda name: SimpleNamespace(requires_rhino=False),
    )

    called = []

    async def dispatch(name, arguments):
        called.append(name)
        return {"success": True, "data": {"name": name}}

    monkeypatch.setattr(server, "_call_tool_dispatch", dispatch)
    result = await server.call_tool("rhino_objects", {})
    assert json.loads(result[0].text) == {"name": "rhino_objects"}
    assert called == ["rhino_objects"]
```

- [ ] **Step 2: Run the expanded contract and confirm the remaining leaks**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_mcp_retirement.py -q
```

Expected: FAIL on targeting sets, Director agent groups, the internal bridge route, inventory, and meta-dispatch assertions. The profile absence, media, and scanner tests should already PASS.

- [ ] **Step 3: Remove Director from profiles, targeting, and internal agent execution**

Make only these removals:

```python
# targeting.py
# Delete all 18 rhino_director_* literals from _ALL_KNOWN_TOOLS.
# Delete the four Director read literals from _RHINO_READ_TOOLS.
# Do not add a special policy; unknown policy remains the general fail-closed fallback.

# agent/tool_groups.py
# Delete "director_readonly" from READONLY_ALLOWED_GROUPS.
# Delete the complete "director" and "director_readonly" TOOL_GROUPS entries.
# Delete "director" from MCP_ONLY_GROUPS.

# agent/tool_dispatcher.py
# Delete the comment and route below:
"rhino_director_curve_samples": ("/director/curve-samples", "POST"),
```

Leave `capability_index._DOMAIN_PREFIXES` unchanged; the tests prove it cannot create a record without a live tool.

- [ ] **Step 4: Replace obsolete positive profile and targeting assertions**

Update the exact counts and invariants:

```python
# test_mcp_tool_profiles.py
assert len(PUBLIC_LEAN_TOOL_NAMES) == 22
assert len(PUBLIC_READONLY_TOOL_NAMES) == 148
assert len(SENTINEL_TOOL_NAMES) == 26
assert not any(name.startswith("rhino_director_") for name in PUBLIC_READONLY_TOOL_NAMES)

# test_server_tool_profiles.py
# Rename and update count tests to full/default 428, all-live 428, lean 22, readonly 148.
assert len(full) == 428
assert len(ro) + len(excluded) == len(full) == 428

# test_multi_instance_targeting.py
def test_director_tools_have_no_callable_targeting_metadata():
    assert not any(name.startswith("rhino_director_") for name in targeting._ALL_KNOWN_TOOLS)
    assert not any(name.startswith("rhino_director_") for name in targeting.TOOL_POLICIES)
```

Delete the old positive Director targeting tests and the positive Director partition literals. Keep `test_every_exposed_tool_has_policy_entry()` unchanged.

- [ ] **Step 5: Replace Director fixtures in progressive-disclosure tests**

In `test_rook_tools_meta.py`, preserve the general capability-index behavior with retained fixtures:

```python
def test_capability_index_covers_full_unprofiled_surface(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    server._reset_capability_index_cache()
    idx = asyncio.run(server._get_capability_index())
    live = {t.name for t in asyncio.run(server._all_live_tools())}
    assert {r.name for r in idx.records} == live
    assert idx.by_name["rhino_objects"].mcp_dispatchable is True
    assert "rhino_director_preview_motion" not in idx.by_name


def test_lean_reaches_hidden_tool_via_search_read_call(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    _stub_dispatch(monkeypatch)
    found = json.loads(_text("rook_tools_search", {"query": "gh_status"}))
    assert any(entry["name"] == "gh_status" for entry in found)
    schema = json.loads(_text("rook_tools_read", {"name": "gh_status"}))
    assert "input_schema" in schema
    called = json.loads(
        _text("rook_tools_call", {"name": "gh_status", "arguments": {}})
    )
    assert called == {"dispatched": "gh_status", "origin": "meta"}


def test_readonly_block_wall_before_validation(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    _stub_dispatch(monkeypatch)
    text = _text(
        "rook_tools_call",
        {"name": "rhino_create", "arguments": {"bogus": 1}},
    )
    assert "tool_profile_blocked" in text
```

In `test_capability_index.py`, replace the Director sample with `rhino_video_models`, rename `test_search_finds_director_and_respects_readonly_scope` to `test_search_finds_video_and_respects_readonly_scope`, and use:

```python
tools = [
    _tool("rhino_video_models", "List available video models."),
    _tool("rhino_create", "Create geometry."),
]
index = build_index(
    tools,
    {},
    frozenset({"rhino_video_models", "rhino_create"}),
)
assert any(record["name"] == "rhino_video_models" for record in index.search("video"))
readonly_results = index.search(
    "video create", scope_readonly=True, limit=20
)
readonly_names = {record["name"] for record in readonly_results}
assert "rhino_video_models" in readonly_names
assert "rhino_create" not in readonly_names
```

- [ ] **Step 6: Run all profile, targeting, agent, and catalog tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_mcp_retirement.py mcp_server/tests/test_mcp_tool_profiles.py mcp_server/tests/test_server_tool_profiles.py mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_rook_tools_meta.py mcp_server/tests/test_capability_index.py mcp_server/tests/test_capability_inventory.py mcp_server/tests/test_dispatcher_safety.py -q
```

Expected: PASS, with full/default `428`, lean `22`, readonly `148`, and no Director record in any callable registry.

- [ ] **Step 7: Commit the secondary-surface retirement**

```powershell
git add mcp_server/src/rook/targeting.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/tests/test_director_mcp_retirement.py mcp_server/tests/test_mcp_tool_profiles.py mcp_server/tests/test_server_tool_profiles.py mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_rook_tools_meta.py mcp_server/tests/test_capability_index.py
git commit -m "test: close Director capability surfaces"
```

---

### Task 3: Retire wrapper-only tests while retaining implementation coverage

**Files:**
- Delete: `mcp_server/tests/test_director_mcp_tools.py`
- Modify: `mcp_server/tests/test_director_take_package.py:269-286`
- Modify: `mcp_server/tests/test_director_worker_prepare.py:617-638`
- Modify: `mcp_server/tests/test_director_worker_compile.py:521-538`
- Modify: `mcp_server/tests/test_director_worker_play.py:471-494`
- Modify: `mcp_server/tests/test_director_worker_capture.py:654-719`
- Modify: `mcp_server/tests/test_director_routes_live.py:1-15,1121-1220`
- Modify: `mcp_server/tests/test_director_actor_set_builder_live.py:1-29,39-115`

**Interfaces:**
- Consumes: retained functions in `director_video`, `director_publish`, and `director_actor_metadata`.
- Produces: implementation tests that do not depend on an MCP name or `server.py` Director import.

- [ ] **Step 1: Run the Director test family to identify wrapper failures**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_mcp_tools.py mcp_server/tests/test_director_take_package.py mcp_server/tests/test_director_worker_prepare.py mcp_server/tests/test_director_worker_compile.py mcp_server/tests/test_director_worker_play.py mcp_server/tests/test_director_worker_capture.py -q
```

Expected: wrapper registration/dispatch tests FAIL with `Unknown tool`; direct module tests continue to PASS.

- [ ] **Step 2: Delete tests whose only subject is the retired MCP wrapper**

Delete `test_director_mcp_tools.py` in full. It is replaced by `test_director_mcp_retirement.py`.

Delete these exact wrapper-only test functions from their module suites:

```text
test_mcp_tool_is_registered_and_dispatches
test_mcp_dispatch_prepare_take
test_mcp_dispatch_compile_take
test_mcp_dispatch_worker_play
test_mcp_dispatch_capture_take
test_mcp_dispatch_capture_take_error_preserves_extra_payload
```

Do not remove any neighboring `package_take()`, `prepare_take()`, `compile_take()`, `play_take()`, or `capture_take()` tests.

- [ ] **Step 3: Convert the actor-set live gate to direct retained primitives**

Replace `from rook import server` with:

```python
from rook import director_actor_metadata as actor_metadata
```

Replace `_call_tool()` with:

```python
async def _read_metadata(arguments: dict) -> dict:
    project_root, source_document = await actor_metadata.resolve_active_project_root()
    ref = arguments["ref"]
    expected_kind = arguments["expected_kind"]
    return {
        "ref": ref,
        "expected_kind": expected_kind,
        "resolved_metadata_path": str(
            actor_metadata.resolve_metadata_ref(project_root, ref)
        ),
        "source_document": source_document,
        "payload": actor_metadata.load_metadata_ref(
            project_root, ref, expected_kind=expected_kind
        ),
    }
```

Use direct calls in the live test:

```python
capture = await actor_metadata.capture_source_occurrence_v2(
    {
        "snapshot_id": snapshot_id,
        "ids": [SOURCE_ID],
        "intent": "live_actor_set_builder_gate",
        "label": "Live actor-set builder gate",
    }
)
built = await actor_metadata.build_actor_set_from_source_occurrence_v2(
    {
        "source_occurrence_snapshot_ref": capture["snapshot_ref"],
        "actor_set_id": actor_set_id,
    }
)
loaded = await _read_metadata(
    {"ref": built["actor_set_ref"], "expected_kind": "director_actor_set"}
)
```

For the optional existing oracle, call `_read_metadata()` and catch `actor_metadata.DirectorActorMetadataError` instead of `AssertionError`.

- [ ] **Step 4: Convert the live video smoke to direct retained modules**

Change the imports to:

```python
from rook import director, director_publish, director_video, server
```

Replace the retired assembly wrapper with:

```python
assemble_payload = await director_video.assemble_director_video(
    {"run_root": str(run_root)},
    port=_director_port(),
)
if assemble_payload.get("state") == "failed":
    error = assemble_payload.get("error") or {}
    if error.get("code") == "backend_unavailable":
        pytest.skip(
            f"Media Foundation backend unavailable on this machine: {error}"
        )
    pytest.fail(f"Video assembly failed before publish smoke: {error!r}")
```

Replace the retired publish wrapper with:

```python
payload = await director_publish.publish_director_video(
    {"run_root": str(run_root)},
    port=_director_port(),
)
```

Keep the retained `rhino_vision_get_artifact` call intact; it is one of the 17 media sentinels.

- [ ] **Step 5: Prove wrapper references are gone but retained implementation evidence remains**

Run from the repository root:

```powershell
rg -n -U -P 'server\.call_tool\([\s\r\n]*"rhino_director_' mcp_server/tests --glob "*.py"
```

Expected: no matches. Negative tombstone fixtures and dormant template assertions may still contain retired names, but no test may invoke them through `server.call_tool()`.

Then run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director.py mcp_server/tests/test_director_compiler.py mcp_server/tests/test_director_video.py mcp_server/tests/test_director_publish.py mcp_server/tests/test_director_actor_metadata.py mcp_server/tests/test_director_take_package.py mcp_server/tests/test_director_worker_prepare.py mcp_server/tests/test_director_worker_compile.py mcp_server/tests/test_director_worker_play.py mcp_server/tests/test_director_worker_capture.py mcp_server/tests/test_canvas_director.py mcp_server/tests/test_canvas_director_templates.py -q
```

Expected: PASS. Tests marked `requires_rhino` remain skipped unless a live test environment is explicitly enabled.

- [ ] **Step 6: Commit the test-boundary cleanup**

```powershell
git add mcp_server/tests
git commit -m "test: preserve Director implementation below MCP"
```

---

### Task 4: Supersede actionable guidance and publish the measured architecture

**Files:**
- Modify: `mcp_server/tests/test_director_mcp_retirement.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/CURRENT_ARCHITECTURE.md`
- Modify: `docs/AGENT_ARCHITECTURE.md`
- Modify: `docs/rook_docs/work-queue.md`
- Modify: `docs/rook_docs/2026-04-15-typed-route-gap-analysis.md`
- Modify/classify: every tracked `docs/**/*.md` selected by `DIRECTOR_DOC_PATTERN`. The measured taxonomy is two current-guidance architecture documents, two current retirement documents, four historical-evidence documents, and 55 actionable historical documents with partial-supersession notices. `CURRENT_GUIDANCE` is exempt only from the historical-classification loop and remains covered by its dedicated stricter test.
- Modify: `docs/superpowers/specs/2026-05-20-rookvisiondirector-camera-video-roadmap.md`, `docs/superpowers/specs/2026-07-06-director-v3-snapshot-boundary-design.md`, and `docs/superpowers/plans/2026-07-07-director-build-actor-set-from-source-occurrence.md` are named load-bearing examples of that repository-wide selection, not its limit.

**Interfaces:**
- Consumes: measured counts from Task 2 and the approved product boundary.
- Produces: current guidance with no actionable Director workflow and visible notices on every active-looking historical contract.

- [ ] **Step 1: Add failing documentation and preservation tests**

Append to `test_director_mcp_retirement.py`. The executable test must explicitly enumerate the exact 55-path `ACTIONABLE_DIRECTOR_DOCS` frozenset (no glob-derived expected set), define the exact full partial/historical notice strings, and define every directory-correct reference string. The condensed sample below shows the required tracked-only enumeration and assertions; the executable constants carry the complete literal snapshot from Steps 3–4.

```python
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CURRENT_GUIDANCE = (
    "AGENTS.md",
    "README.md",
    "docs/CURRENT_ARCHITECTURE.md",
    "docs/AGENT_ARCHITECTURE.md",
)
APPROVED_DIRECTOR_BOUNDARY = (
    "- Director is retired from MCP discovery, profiles, meta-tools, targeting, "
    "and internal-agent dispatch. Native `/director/*` routes and implementation "
    "modules remain temporarily preserved for disposition review; they are not a "
    "public or agent-callable capability."
)
CURRENT_DIRECTOR_GUIDANCE_DOCS = frozenset(
    {"docs/CURRENT_ARCHITECTURE.md", "docs/AGENT_ARCHITECTURE.md"}
)
BOUNDARY_GUIDANCE = frozenset(
    {"AGENTS.md", *CURRENT_DIRECTOR_GUIDANCE_DOCS}
)
DIRECTOR_DOC_PATTERN = re.compile(
    r"rhino_director_|"
    r"(?<![A-Za-z0-9_])/director(?:/|\b)|"
    r"\b(?:Rook)?VisionDirector\b",
    re.IGNORECASE,
)
CURRENT_DIRECTOR_RETIREMENT_DOCS = {
    "docs/superpowers/specs/2026-07-13-director-mcp-surface-retirement-design.md",
    "docs/superpowers/plans/2026-07-13-director-mcp-surface-retirement.md",
}
HISTORICAL_DIRECTOR_EVIDENCE_DOCS = frozenset({
    "docs/TROUBLESHOOTING.md",
    "docs/superpowers/2026-06-24-replay-live-gate-postmortem.md",
    "docs/superpowers/plans/2026-05-19-rookvisiondirector-slice1-phase0-inventory.md",
    "docs/superpowers/plans/2026-06-23-hunyuan-3d-pro-image-to-3d.md",
})
# ACTIONABLE_DIRECTOR_DOCS is an explicit frozenset of the exact 55 tracked paths.
# PARTIAL_SUPERSESSION_NOTICE and HISTORICAL_EVIDENCE_NOTICE are the exact full
# multiline blocks from Steps 3 and 4, not marker substrings.
# PARTIAL_REFERENCE_BY_DIRECTORY maps specs/, plans/, and rook_docs/ to the exact
# reference definitions in Step 3. HISTORICAL_REFERENCE_BY_DOCUMENT maps all four
# evidence documents to the exact reference definitions in Step 4.
TRACKED_GUIDANCE_ROOTS = (
    ".agents",
    ".claude/skills",
    ".claude-plugin",
    "hooks",
    "installer",
)
TRACKED_GUIDANCE_SUFFIXES = {
    ".iss", ".json", ".md", ".ps1", ".py", ".toml", ".txt", ".yaml", ".yml"
}


def _git_tracked_relative_paths(*roots: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", *roots],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return [
        relative
        for relative in result.stdout.decode("utf-8").split("\0")
        if relative
    ]


def _route_aware_director_documents() -> dict[str, str]:
    matches = {}
    for relative in _git_tracked_relative_paths("docs"):
        if not relative.startswith("docs/") or not relative.endswith(".md"):
            continue
        path = REPO_ROOT / relative
        text = path.read_text(encoding="utf-8", errors="replace")
        if DIRECTOR_DOC_PATTERN.search(text):
            matches[relative] = text
    return matches


def test_current_guidance_has_no_actionable_director_instruction():
    for relative in CURRENT_GUIDANCE:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        expected_boundary_count = 1 if relative in BOUNDARY_GUIDANCE else 0
        assert text.count(APPROVED_DIRECTOR_BOUNDARY) == expected_boundary_count
        remaining = text.replace(APPROVED_DIRECTOR_BOUNDARY, "")
        assert DIRECTOR_DOC_PATTERN.search(remaining) is None, relative
        assert "director-based" not in remaining.lower(), relative


def _assert_exact_notice_block(text, notice, reference, relative):
    block = f"{notice}\n\n{reference}"
    assert text.count(block) == 1, relative
    assert text.count(notice) == 1, relative
    references = re.findall(
        r"(?m)^\[director-mcp-retirement\]: .+$", text
    )
    assert references == [reference], relative


def _partial_reference_for(relative):
    matches = [
        reference
        for directory, reference in PARTIAL_REFERENCE_BY_DIRECTORY.items()
        if relative.startswith(directory)
    ]
    assert len(matches) == 1, relative
    return matches[0]


def test_every_route_aware_director_document_is_classified():
    documents = _route_aware_director_documents()
    groups = (
        CURRENT_DIRECTOR_GUIDANCE_DOCS,
        CURRENT_DIRECTOR_RETIREMENT_DOCS,
        HISTORICAL_DIRECTOR_EVIDENCE_DOCS,
        ACTIONABLE_DIRECTOR_DOCS,
    )
    assert [len(group) for group in groups] == [2, 2, 4, 55]
    for index, group in enumerate(groups):
        for other in groups[index + 1:]:
            assert group.isdisjoint(other)
    expected_documents = frozenset().union(*groups)
    assert len(expected_documents) == 63
    assert set(documents) == expected_documents
    assert set(HISTORICAL_REFERENCE_BY_DOCUMENT) == (
        HISTORICAL_DIRECTOR_EVIDENCE_DOCS
    )

    for relative in sorted(ACTIONABLE_DIRECTOR_DOCS):
        _assert_exact_notice_block(
            documents[relative],
            PARTIAL_SUPERSESSION_NOTICE,
            _partial_reference_for(relative),
            relative,
        )
    for relative in sorted(HISTORICAL_DIRECTOR_EVIDENCE_DOCS):
        _assert_exact_notice_block(
            documents[relative],
            HISTORICAL_EVIDENCE_NOTICE,
            HISTORICAL_REFERENCE_BY_DOCUMENT[relative],
            relative,
        )


def test_installed_agent_assets_do_not_teach_director_mcp():
    tracked = [
        REPO_ROOT / relative
        for relative in _git_tracked_relative_paths(*TRACKED_GUIDANCE_ROOTS)
    ]
    assert tracked
    for path in tracked:
        if path.suffix.lower() not in TRACKED_GUIDANCE_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        assert DIRECTOR_DOC_PATTERN.search(text) is None, path


def test_director_artifact_preservation_guard_remains():
    guard = (
        REPO_ROOT / "scripts/tests/release-installer-guards.tests.ps1"
    ).read_text(encoding="utf-8")
    assert "RookVisionDirector" in guard
```

- [ ] **Step 2: Run the documentation tests and confirm the missing notices**

Run from the repository root:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_mcp_retirement.py -q
```

Expected: FAIL on current README copy and on every route-aware Director document that lacks its required classification marker. The failure list includes the active May 20 camera/video roadmap, the July 6 snapshot-boundary design, and the July 7 actor-set implementation plan. The tracked-guidance and artifact-preservation checks PASS.

- [ ] **Step 3: Add partial-supersession notices to every actionable match**

Enumerate the complete tracked route-aware document set from the repository root. This tracked-only audit mirrors the NUL-safe `git ls-files -z` enumeration in the test; filesystem `rglob()`/`rg` results are not the contract because ignored or untracked scratch Markdown must not affect it:

```powershell
git grep -Il --perl-regexp 'rhino_director_|(?<![A-Za-z0-9_])/director(?:/|\b)|\b(?:Rook)?VisionDirector\b' -- 'docs/*.md' 'docs/**/*.md' | Sort-Object
```

Classify the 63 measured results into four exact, pairwise-disjoint sets: two current-guidance architecture documents (`docs/CURRENT_ARCHITECTURE.md` and `docs/AGENT_ARCHITECTURE.md`), two paths in `CURRENT_DIRECTOR_RETIREMENT_DOCS`, four paths in `HISTORICAL_DIRECTOR_EVIDENCE_DOCS`, and the explicitly enumerated 55-path `ACTIONABLE_DIRECTOR_DOCS` snapshot. Assert the union equals the complete tracked route-aware set exactly. The two current-guidance documents are exempt only from historical notice classification: do not add a supersession notice to them, and keep all four `CURRENT_GUIDANCE` paths under `test_current_guidance_has_no_actionable_director_instruction`, which allows the exact approved boundary once in the three boundary documents, zero times in README, removes that exact text, and rejects every remaining `DIRECTOR_DOC_PATTERN` match.

For each of the 55 actionable historical results, add this notice immediately below the title/status preamble. The contract asserts the complete notice plus its directory-correct reference definition as one exact block, exactly once; marker substrings or a design filename elsewhere do not satisfy it:

```markdown
> **PARTIALLY SUPERSEDED — Director MCP retirement (2026-07-13):** The general
> non-Director architecture and dated evidence in this document remain available.
> All `rhino_director_*`, `/director`, VisionDirector, and Director-domain examples,
> allowlist entries, count assumptions, acceptance criteria, and positive dispatch
> tests are superseded as of 2026-07-13. Replace those examples with
> non-Director fixtures when maintaining or replaying this work. This document must
> not be used to restore a Director MCP tool. See the
> [Director MCP Surface Retirement Design][director-mcp-retirement].
```

Add the exact matching reference definition after the notice, selected by the document's directory:

| Document directory | Reference definition |
|---|---|
| `docs/superpowers/specs/` | `[director-mcp-retirement]: 2026-07-13-director-mcp-surface-retirement-design.md` |
| `docs/superpowers/plans/` | `[director-mcp-retirement]: ../specs/2026-07-13-director-mcp-surface-retirement-design.md` |
| `docs/rook_docs/` | `[director-mcp-retirement]: ../superpowers/specs/2026-07-13-director-mcp-surface-retirement-design.md` |

This default-to-superseded rule deliberately catches all present and future actionable matches; the four historical exceptions are the only files that receive the different marker in Step 4. Do not edit the body beneath any notice.

- [ ] **Step 4: Mark the four explicit evidence-only documents as historical**

The only historical-evidence exceptions are:

```text
docs/TROUBLESHOOTING.md
docs/superpowers/2026-06-24-replay-live-gate-postmortem.md
docs/superpowers/plans/2026-05-19-rookvisiondirector-slice1-phase0-inventory.md
docs/superpowers/plans/2026-06-23-hunyuan-3d-pro-image-to-3d.md
```

Add this notice directly below each title/status preamble. The contract asserts this complete notice plus the exact document-specific reference definition as one block, exactly once:

```markdown
> **DIRECTOR HISTORICAL EVIDENCE — classified 2026-07-13:** Director routes,
> tool names, and workflows below are retained only as dated evidence. They are not
> current instructions and must not be used to restore a Director MCP tool. See the
> [Director MCP Surface Retirement Design][director-mcp-retirement].
```

Use these exact reference definitions:

| Document path | Reference definition |
|---|---|
| `docs/TROUBLESHOOTING.md` | `[director-mcp-retirement]: superpowers/specs/2026-07-13-director-mcp-surface-retirement-design.md` |
| `docs/superpowers/2026-06-24-replay-live-gate-postmortem.md` | `[director-mcp-retirement]: specs/2026-07-13-director-mcp-surface-retirement-design.md` |
| Either historical file under `docs/superpowers/plans/` | `[director-mcp-retirement]: ../specs/2026-07-13-director-mcp-surface-retirement-design.md` |

Preserve all dated evidence below these notices unchanged. Assert the four-path historical reference map equals `HISTORICAL_DIRECTOR_EVIDENCE_DOCS` exactly, so no evidence document can silently fall back to an actionable marker or an incorrect relative link.

- [ ] **Step 5: Update current product copy and measured counts**

Use these exact facts consistently:

```text
431 static Tool definitions
3 deprecated-interactive definitions gated by default
428 tools advertised by default/full
22 tools advertised by lean
148 tools advertised by readonly
```

Specific edits:

```markdown
# README.md feature copy
- **Video** — Render viewport/turntable video, manage generation jobs, and inspect status/estimate/cancel results

# README.md count references
428 MCP tools
428 tools advertised by `list_tools()`
431 static tool definitions in `server.py` (428 advertised by default)

# docs/CURRENT_ARCHITECTURE.md
| MCP tools | 431 static definitions; 428 advertised by default (`full`) |
```

Add this current boundary statement to `AGENTS.md`, `docs/CURRENT_ARCHITECTURE.md`, and `docs/AGENT_ARCHITECTURE.md` near their MCP architecture descriptions:

```markdown
- Director is retired from MCP discovery, profiles, meta-tools, targeting, and internal-agent dispatch. Native `/director/*` routes and implementation modules remain temporarily preserved for disposition review; they are not a public or agent-callable capability.
```

In `docs/CURRENT_ARCHITECTURE.md`, follow it with:

```markdown
Future scene preview, timeline, rendering, and finalized-video export belongs in RookStudio. `rook2` remains a narrow Rhino connector/broker and is unchanged by this retirement.
```

- [ ] **Step 6: Run documentation, count, and release-preservation checks**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_mcp_retirement.py mcp_server/tests/test_server_tool_profiles.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-installer-guards.tests.ps1
```

Expected: pytest PASS with counts `428/22/148`; PowerShell prints `Release installer guard tests passed.`

- [ ] **Step 7: Commit the guidance retirement**

```powershell
git add AGENTS.md README.md docs mcp_server/tests/test_director_mcp_retirement.py
git commit -m "docs: supersede Director MCP guidance"
```

---

### Task 5: Run the complete retirement acceptance gate

**Files:**
- Verify only; modify earlier task files only if a failing assertion exposes an omitted retirement surface.

**Interfaces:**
- Consumes: all prior task deliverables.
- Produces: one evidence-backed, reviewable Director MCP retirement branch.

- [ ] **Step 1: Check the final static surface**

Run from the repository root:

```powershell
$pattern = 'rhino_director_|(?<![A-Za-z0-9_])/director(?:/|\b)|\b(?:Rook)?VisionDirector\b|director_readonly'
$activeSurface = git grep -n -P $pattern -- `
  mcp_server/src/rook/server.py `
  mcp_server/src/rook/mcp_tool_profiles.py `
  mcp_server/src/rook/targeting.py `
  mcp_server/src/rook/agent/tool_groups.py `
  mcp_server/src/rook/agent/tool_dispatcher.py `
  mcp_server/src/rook/capability_index.py
if ($LASTEXITCODE -gt 1) { throw 'git grep failed for active surfaces' }
$allowedActive = @($activeSurface | Where-Object {
  $_ -match '^mcp_server/src/rook/server\.py:\d+:\s+if name\.startswith\("rhino_director_"\):' -or
  $_ -match '^mcp_server/src/rook/capability_index\.py:\d+:\s+\("rhino_director_", "director"\),'
})
$unexpectedActive = @($activeSurface | Where-Object { $_ -notin $allowedActive })
if ($unexpectedActive.Count -ne 0) { throw ($unexpectedActive -join "`n") }
if ($allowedActive.Count -ne 2) { throw "Expected tombstone + inert classifier; found $($allowedActive.Count)" }

$guidance = git grep -n -P $pattern -- `
  .agents .claude/skills .claude-plugin hooks installer `
  README.md AGENTS.md docs/CURRENT_ARCHITECTURE.md docs/AGENT_ARCHITECTURE.md
if ($LASTEXITCODE -gt 1) { throw 'git grep failed for guidance surfaces' }
$unexpectedGuidance = @($guidance | Where-Object {
  $_ -notmatch 'not a public or agent-callable capability'
})
if ($unexpectedGuidance.Count -ne 0) { throw ($unexpectedGuidance -join "`n") }
if (@($guidance).Count -ne 3) { throw "Expected three explicit architecture boundary statements" }
```

Expected active-surface matches are exactly:

- the narrow `server.py` tombstone; and
- the intentionally retained `capability_index.py` prefix classifier.

Expected current-guidance matches are exactly the three explicit, non-callable boundary statements in `AGENTS.md`, `docs/CURRENT_ARCHITECTURE.md`, and `docs/AGENT_ARCHITECTURE.md`. Tracked skills, plugin assets, hooks, installer inputs, and README produce no match. The repository-wide Markdown classification test separately proves that every historical/actionable document is marked.

- [ ] **Step 2: Run the focused MCP/agent acceptance suite**

Run from the repository root:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_director_mcp_retirement.py mcp_server/tests/test_mcp_tool_profiles.py mcp_server/tests/test_server_tool_profiles.py mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_rook_tools_meta.py mcp_server/tests/test_capability_index.py mcp_server/tests/test_capability_inventory.py mcp_server/tests/test_dispatcher_safety.py mcp_server/tests/test_director.py mcp_server/tests/test_director_compiler.py mcp_server/tests/test_director_video.py mcp_server/tests/test_director_publish.py mcp_server/tests/test_director_actor_metadata.py mcp_server/tests/test_director_take_package.py mcp_server/tests/test_director_worker_prepare.py mcp_server/tests/test_director_worker_compile.py mcp_server/tests/test_director_worker_play.py mcp_server/tests/test_director_worker_capture.py mcp_server/tests/test_canvas_director.py mcp_server/tests/test_canvas_director_templates.py mcp_server/tests/test_video_mcp_tools.py mcp_server/tests/test_vision_mcp_tools.py mcp_server/tests/test_display_modes.py mcp_server/tests/test_viewport_views.py -q
```

Expected: PASS, with live-Rhino tests skipped unless explicitly enabled.

- [ ] **Step 3: Run the full Python suite**

Run from the repository root using the unchanged worktree environment:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests -m "not requires_rhino" -q
```

Expected: every new and retirement-focused test passes, and the failed/error node-ID set introduces no entries beyond the pre-Task-1 differential baseline. Pre-existing failed/error node IDs may remain. Record the exact final totals and node-ID comparison in the branch handoff; do not copy a historical total into the claim.

- [ ] **Step 4: Run repository and artifact checks**

Run from the repository root:

```powershell
git diff --check
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-installer-guards.tests.ps1
git status --short
```

Expected: no whitespace errors, release guards PASS, and only intentional task files are modified. No native build is required because no native or managed source changed.

- [ ] **Step 5: Review the acceptance boundary before handoff**

Confirm all of the following from test output and diff, not assumption:

```text
No Director MCP name is discoverable under full, lean, or readonly.
Full/lean direct calls return Unknown tool before targeting.
Readonly direct calls preserve tool_profile_blocked non-enumeration.
rook_tools_call returns not_mcp_dispatchable in full/lean and tool_profile_blocked in readonly.
Scanner failure does not gate a known normal tool.
No internal agent group, bridge route, inventory, targeting policy, or current instruction restores Director.
All 17 media sentinels retain their prior profiles and policies.
Native routes, Python modules, managed bridge code, user artifacts, and the installer preservation guard remain.
RookStudio and rook2 are unchanged.
```

If verification exposes a gap, return to the task that owns that surface, add a
failing regression there, make the smallest correction, rerun that task's exact
verification command, and commit with that task's listed file set. Do not create
an empty acceptance commit.
