# RoadCreator/RookRoads Surface Containment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove RoadCreator/RookRoads from Rook's admitted user and agent surface while retaining dormant compatibility implementation and native road-intersection tools.

**Architecture:** Extend the existing lifecycle admission decision with an exact 40-name suspended inventory and one central fail-closed `rc_*` namespace rule. Remove only active memberships, six shipped road-skill roots, and scoped active guidance; add one exact-path, non-following Codex migration that runs independently of component selection. Keep the private change in one coherent PR with two reviewable implementation commits and a final evidence gate.

**Tech Stack:** Python 3.11, MCP Python SDK tool schemas, pytest, Windows stdlib filesystem APIs, PowerShell/Pester, Inno Setup 6.

## Global Constraints

- Begin implementation from the commit containing this plan on
  `codex/release-surface-hardening-roadmap`, and verify its first parent is approved
  design commit `abb623363801b66be2b09fd1359b9c154c0d5198` before editing code.
- The raw pre-lifecycle inventory is exactly 40 `rc_*` names; Task 1 defines the full set verbatim.
- Known `rc_*` names use the existing `suspended` lifecycle envelope; an unknown `rc_*` name receives one fixed-field fail-closed denial through the same central admission path. Response-size hardening is deferred.
- Remove `rc_*` from every active profile, full-profile set, allowlist, targeting set, and model-facing tool group.
- Preserve `road_intersection_candidates`, `road_intersection_resolve`, and all other admitted native `road_*` tools.
- Do not modify `src/RookNative`, `mcp_server/src/rook/bridge.py`, dormant `rc_*` schemas or dispatch cases, `/rc/*` routes, `mcp_server/src/rook/agent/tool_dispatcher.py` adapter mappings, `knowledge/roads/profiles`, historical documents, or retained Wasp product assets.
- Delete only the six specified `design-road` and `masterplan-roads` skill roots. Do not extract their road-owned Wasp scaffold files.
- Active-guidance checks target only `design-road`, `masterplan-roads`, `RoadCreator`, and `RookRoads`; do not reject generic `road` wording.
- Installer migration targets only `~/.codex/skills/design-road` and `~/.codex/skills/masterplan-roads`, uses no enumeration/glob/prefix deletion, does not follow links or junctions, and never touches Claude or sibling Codex skills.
- Installer cleanup failures are nonfatal but must record `complete: false` and bounded per-target outcomes in `post_install_summary.json`.
- Keep `382 / 385 / 120 / 20` in one authoritative profile-count test, not duplicated across active documents.
- Add no dependency, feature flag, plugin framework, generalized cleanup framework, implementation purge, or adjacent refactor.
- Public `rook-release` cleanup and the one-time removal release note are a separate follow-up PR and are not implemented by this plan.

---

## File Structure and Ownership Map

### Runtime admission and active catalogs

- Modify `mcp_server/src/rook/tool_lifecycle.py`: own the pinned names, shared recovery strings, and central namespace reservation.
- Modify `mcp_server/src/rook/server.py`: expose raw schemas before lifecycle filtering, retain central filtering, and remove the one admitted catalog description that advertises RoadCreator.
- Modify `mcp_server/src/rook/mcp_tool_profiles.py`: remove 28 readonly `rc_*` memberships.
- Modify `mcp_server/src/rook/targeting.py`: remove all 40 known-tool and five read-policy `rc_*` memberships.
- Modify `mcp_server/src/rook/agent/tool_groups.py`: remove the all-`rc_*` `road_design` group while retaining `road_intersections`.
- Modify `mcp_server/tests/test_containment_catalogs.py`, `test_containment_execution.py`, `test_containment_supported_paths.py`, and `test_server_tool_profiles.py`: pin raw inventory, fail-closed future admission, before-arguments denial, native preservation, active membership absence, and authoritative counts.
- Modify `AGENTS.md`, `README.md`, `docs/CURRENT_ARCHITECTURE.md`, and `docs/AGENT_ARCHITECTURE.md`: replace volatile exact MCP counts with count-neutral language.

### Shipped skills and active guidance

- Delete `.agents/skills/design-road`, `.agents/skills/masterplan-roads`, `.claude/skills/design-road`, `.claude/skills/masterplan-roads`, `installer/agent-assets/codex-skills/design-road`, and `installer/agent-assets/codex-skills/masterplan-roads` in full.
- Modify `README.md`, `QUICK_START.md`, `AGENT_SETUP.md`, `installer/agent-assets/ROOK_CLAUDE_POST_INSTALL.md`, `installer/agent-assets/ROOK_CODEX_POST_INSTALL.md`, and `scripts/session-start.sh`: remove the four exact retired identities and their capability claims.
- Modify `mcp_server/tests/test_containment_guidance.py`: define the exact retired roots/vocabulary, expand active-file coverage, and add lightweight retained-Wasp root checks.

### Installer migration

- Modify `installer/post_install.py`: add one migration-specific helper, early unconditional invocation, bounded outcomes, and summary recording.
- Modify `mcp_server/tests/test_python_runtime_install.py`: cover selected/deselected execution, exact paths, directories/files/reparse points, sibling and Claude preservation, repeat repair, and nonfatal partial failure.

### Evidence only

- Do not add a permanent Wasp hash fixture or a new evidence file. Record Task 3 command output in the private PR description/check run.

---

### Task 1: Central Lifecycle Admission and Complete Shipped-Surface Containment

**Files:**
- Modify: `mcp_server/src/rook/tool_lifecycle.py:1-73`
- Modify: `mcp_server/src/rook/server.py:3237-12974`
- Modify: `mcp_server/src/rook/mcp_tool_profiles.py:97-152`
- Modify: `mcp_server/src/rook/targeting.py:250-299,665-680`
- Modify: `mcp_server/src/rook/agent/tool_groups.py:321-364`
- Modify: `mcp_server/tests/test_containment_catalogs.py`
- Modify: `mcp_server/tests/test_containment_execution.py`
- Modify: `mcp_server/tests/test_containment_supported_paths.py`
- Modify: `mcp_server/tests/test_server_tool_profiles.py`
- Modify: `mcp_server/tests/test_containment_guidance.py:69-78`
- Modify: `AGENTS.md:39-43`
- Modify: `CLAUDE.md:1-50`
- Modify: `README.md:10-70,295-303`
- Modify: `AGENT_SETUP.md:276-280`
- Modify: `docs/CURRENT_ARCHITECTURE.md:8-18,80-85`
- Modify: `docs/AGENT_ARCHITECTURE.md:118-125`

**Interfaces:**
- Consumes: existing `LifecycleEntry`, `ToolDisposition`, `resolve_contained_tool()`, `denial_payload()`, and `deny_if_contained()` lifecycle pipeline.
- Produces: `ROADCREATOR_TOOL_NAMES: frozenset[str]`, central `resolve_contained_tool(name: object) -> LifecycleEntry | None` behavior for known and future `rc_*` names, and `server._all_tool_schemas() -> list[Tool]` as the raw pre-lifecycle source.
- Preserves: `server._all_live_tools() -> list[Tool]`, all existing dispatch origins, and both native intersection route mappings.

- [ ] **Step 1: Write failing raw-inventory, future-namespace, and lifecycle tests**

Add these imports and tests to `test_containment_catalogs.py`:

```python
from types import SimpleNamespace

from rook.tool_lifecycle import (  # noqa: E402
    CONTAINED_TOOLS,
    ROADCREATOR_TOOL_NAMES,
    ToolDisposition,
    resolve_contained_tool,
)


@pytest.mark.asyncio
async def test_raw_schema_inventory_equals_pinned_roadcreator_names() -> None:
    from rook import server

    raw_names = {
        tool.name
        for tool in await server._all_tool_schemas()
        if tool.name.startswith("rc_")
    }
    registered = {
        entry.name: entry
        for entry in CONTAINED_TOOLS
        if entry.name.startswith("rc_")
    }
    assert raw_names == ROADCREATOR_TOOL_NAMES == set(registered)
    assert len(raw_names) == 40
    assert all(
        entry.disposition is ToolDisposition.SUSPENDED
        for entry in registered.values()
    )


@pytest.mark.asyncio
async def test_future_rc_namespace_is_hidden_by_central_live_filter(monkeypatch) -> None:
    from rook import server

    async def raw_tools():
        return [
            SimpleNamespace(name="safe_probe"),
            SimpleNamespace(name="rc_future_probe"),
        ]

    monkeypatch.setattr(server, "_all_tool_schemas", raw_tools)
    assert [tool.name for tool in await server._all_live_tools()] == ["safe_probe"]

    entry = resolve_contained_tool("rc_future_probe")
    assert entry is not None
    assert entry.name == "rc_future_probe"
    assert entry.disposition is ToolDisposition.SUSPENDED
    assert "explicit lifecycle entry" in entry.recovery
```

Change `test_containment_execution.py` to exercise the synthetic name through the same before-argument seams:

```python
PINNED = [entry.name for entry in CONTAINED_TOOLS]
DENIED = [*PINNED, "rc_future_probe"]

# Use DENIED for public/server, progressive, internal-executor, and ToolDispatcher
# parametrization. Keep private-handler branches limited to spawn_agent and
# plan_and_execute exactly as they are today.
```

Add this assertion to `test_tool_dispatcher_refuses_contained_local_registration`:

```python
dispatcher.register_local("rc_future_probe", object())
assert "rc_future_probe" not in dispatcher._local_tools
```

- [ ] **Step 2: Run the new tests and verify the intended failures**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_containment_catalogs.py `
  mcp_server/tests/test_containment_execution.py -q
```

Expected: FAIL because `ROADCREATOR_TOOL_NAMES` and `_all_tool_schemas` do not exist, and `rc_future_probe` is not yet contained.

- [ ] **Step 3: Pin the 40 names and reserve `rc_*` centrally**

In `tool_lifecycle.py`, add the exact production constant:

```python
ROADCREATOR_TOOL_NAMES = frozenset({
    "rc_apply_intersection_ownership",
    "rc_apply_sidewalk_ownership",
    "rc_assemble_route",
    "rc_build_profile",
    "rc_clothoid",
    "rc_concrete_barrier_profile",
    "rc_contour_levels",
    "rc_cross_section",
    "rc_crossing",
    "rc_crossing_params",
    "rc_cubic_parabola",
    "rc_deltablok_profile",
    "rc_extract_offsets",
    "rc_get_road_profile",
    "rc_guardrail",
    "rc_guardrail_profile",
    "rc_list_road_profiles",
    "rc_longitudinal_profile",
    "rc_ping",
    "rc_pole_spacing",
    "rc_project_offset_profile",
    "rc_resolve_edges",
    "rc_road_3d",
    "rc_road_footprint",
    "rc_roads",
    "rc_roundabout_params",
    "rc_sidewalk",
    "rc_sidewalk_corners",
    "rc_sidewalk_profile",
    "rc_slope_profile",
    "rc_slopes",
    "rc_standards",
    "rc_store_road_profile",
    "rc_terrain_profile",
    "rc_validate_profile",
    "rc_validate_road_profile",
    "rc_validate_style_set",
    "rc_verge_profile",
    "rc_vertical_curve",
    "rc_widening",
})

_ROADCREATOR_RECOVERY = (
    _REDISCOVER
    + "RoadCreator/RookRoads is not in the supported Rook surface; use admitted native "
    "Rook tools or another supported workflow."
)
_UNCLASSIFIED_RC_RECOVERY = (
    _REDISCOVER
    + "the rc_* namespace is reserved; add an explicit lifecycle entry before admitting "
    "this tool."
)
```

Immediately before the closing parenthesis of the existing `CONTAINED_TOOLS` tuple,
insert this exact unpacking expression; leave all six preceding entries byte-for-byte
unchanged:

```python
    *(
        LifecycleEntry(name, ToolDisposition.SUSPENDED, _ROADCREATOR_RECOVERY)
        for name in sorted(ROADCREATOR_TOOL_NAMES)
    ),
```

Keep `_BY_NAME` exact and change only central resolution:

```python
def resolve_contained_tool(name: object) -> LifecycleEntry | None:
    """Resolve exact tombstones and fail closed for the reserved rc_* namespace."""
    if type(name) is not str:
        return None
    entry = _BY_NAME.get(name)
    if entry is not None:
        return entry
    if name.startswith("rc_"):
        return LifecycleEntry(
            name,
            ToolDisposition.SUSPENDED,
            _UNCLASSIFIED_RC_RECOVERY,
        )
    return None
```

Do not add `startswith("rc_")` checks to `server.py`, dispatcher classes, registries, agents, chat, or progressive handlers. Their existing calls to `resolve_contained_tool()` and `deny_if_contained()` must remain the sole propagation mechanism.

- [ ] **Step 4: Split raw schema construction from lifecycle admission without editing schema blocks**

Rename the current `_all_live_tools()` definition to `_all_tool_schemas()` and replace
its docstring with:

```python
async def _all_tool_schemas() -> list[Tool]:
    """Raw tool schemas before deprecated gates, lifecycle admission, or profiles."""
```

Leave the existing `all_tools = [...]` body byte-for-byte unchanged. At the current
function tail, replace the deprecated-gate/lifecycle-filter block with this complete
tail and admitted wrapper:

```python
    return all_tools


async def _all_live_tools() -> list[Tool]:
    """Deprecated-gated, lifecycle-admitted, unprofiled tool surface."""
    all_tools = await _all_tool_schemas()
    if not _interactive_command_learning_enabled():
        all_tools = [
            tool
            for tool in all_tools
            if tool.name not in _DEPRECATED_INTERACTIVE_COMMAND_TOOLS
        ]
    return [tool for tool in all_tools if resolve_contained_tool(tool.name) is None]
```

Do not edit any dormant `Tool(name="rc_...")` schema or `case "rc_..."` dispatch body.

- [ ] **Step 5: Remove all active `rc_*` memberships**

Apply exact removals only:

```text
mcp_tool_profiles.py
  Remove the 28 rc_* strings from PUBLIC_READONLY_TOOL_NAMES.

targeting.py
  Remove all 40 rc_* strings from _ALL_KNOWN_TOOLS.
  Remove rc_get_road_profile, rc_list_road_profiles, rc_ping, rc_roads,
  and rc_standards from _RHINO_READ_TOOLS.

agent/tool_groups.py
  Delete the road_design key and its 30-value all-rc_* list.
  Keep road_intersections with road_intersection_candidates and
  road_intersection_resolve unchanged.
```

Retain the generic uppercase-container assertion in `test_containment_catalogs.py`, and strengthen it with:

```python
assert not {value for value in active_strings if value.startswith("rc_")}, module.__name__
```

- [ ] **Step 6: Make profile counts authoritative in one test and remove volatile document copies**

Replace numeric count tests in `test_server_tool_profiles.py` with one authoritative test:

```python
def test_profile_surface_counts_are_authoritative(monkeypatch):
    full = _list_names(monkeypatch, None)
    lean = _list_names(monkeypatch, "lean")
    readonly = _list_names(monkeypatch, "readonly")

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    monkeypatch.setenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", "1")
    deprecated_enabled = {tool.name for tool in asyncio.run(server.list_tools())}

    assert {
        "full": len(full),
        "full_with_deprecated": len(deprecated_enabled),
        "readonly": len(readonly),
        "lean": len(lean),
    } == {
        "full": 382,
        "full_with_deprecated": 385,
        "readonly": 120,
        "lean": 20,
    }
    assert deprecated_enabled - full == _GATED
```

Keep set-equality and partition tests, but remove duplicate literal count assertions from them. Delete `test_current_architecture_documents_pin_live_profile_counts()` from `test_containment_guidance.py`.

Use these count-neutral replacements in active documents:

```text
AGENTS.md:
  The Python MCP server exposes its lifecycle-admitted surface through full,
  lean, and readonly profiles; test_server_tool_profiles.py is the authoritative
  count contract.

CLAUDE.md:
  Replace both 422/425 claims with “The Python MCP surface is lifecycle-admitted
  and profile-filtered; test_server_tool_profiles.py is the authoritative count
  contract.”

README.md:
  Replace the “422 MCP tools by default” header claim with “Lifecycle-admitted MCP tools”.
  Rook MCP Server (Python) — lifecycle-admitted tools, knowledge graph, chat runtime
  MCP Server (Python) — Defines the MCP schema source, applies lifecycle and profile
  admission, and translates admitted calls into HTTP requests.
  server.py — Raw schemas plus lifecycle/profile admission

AGENT_SETUP.md:
  Replace “the default full profile advertises 422 tools” with “the default full
  profile is ready” before the existing key-tools table.

docs/CURRENT_ARCHITECTURE.md:
  Replace diagram/table counts with “lifecycle-admitted MCP tools” and list the
  full, lean, readonly, and deprecated-gated profiles without numbers.

docs/AGENT_ARCHITECTURE.md:
  “The MCP surface is large enough that showing every admitted tool to every agent
  wastes context. The system uses three disclosure tiers. Full, lean, and readonly
  counts are pinned by test_server_tool_profiles.py.”
```

- [ ] **Step 7: Pin native intersection advertisement, readability, and routing**

Add both names to `SUPPORTED` in `test_containment_supported_paths.py` and add:

```python
NATIVE_INTERSECTION_ROUTES = {
    "road_intersection_candidates": "/road/intersection/candidates",
    "road_intersection_resolve": "/road/intersection/resolve",
}


@pytest.mark.asyncio
async def test_native_intersection_tools_reach_normal_routing_boundary(monkeypatch) -> None:
    from rook import server

    calls = []

    async def fake_call_rhino(path, method="GET", data=None, *, port=None, **_kwargs):
        calls.append((path, method, data, port))
        return {"success": True, "data": {"verified": True}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    for name, path in NATIVE_INTERSECTION_ROUTES.items():
        result = await server._call_tool_dispatch(name, {"marker": name, "port": 12001})
        assert result["success"] is True
        assert calls[-1] == (path, "POST", {"marker": name}, 12001)
```

In `test_containment_catalogs.py`, read both through the capability index and assert the returned records are nonempty and MCP-dispatchable. Do not invoke Rhino geometry.

- [ ] **Step 8: Run the focused runtime slice before shipped-surface removal**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_containment_catalogs.py `
  mcp_server/tests/test_containment_execution.py `
  mcp_server/tests/test_containment_agent_protocols.py `
  mcp_server/tests/test_containment_packaged_executors.py `
  mcp_server/tests/test_containment_supported_paths.py `
  mcp_server/tests/test_server_tool_profiles.py -q
```

Expected: PASS; the sole numeric profile contract reports `382 / 385 / 120 / 20`.

- [ ] **Step 9: Inspect the uncommitted runtime slice before completing its coupled shipped surface**

```powershell
git diff --check
git diff --stat
```

Expected: only Task 1 runtime, active-membership, test, and count-neutral guidance paths
are modified. Do not commit yet: the existing containment-guidance contract correctly
requires the coupled skill and active-guidance removals below.

#### Task 1 continuation: Remove Shipped Road Skills and Active Guidance

**Files:**
- Delete: `.agents/skills/design-road/**`
- Delete: `.agents/skills/masterplan-roads/**`
- Delete: `.claude/skills/design-road/**`
- Delete: `.claude/skills/masterplan-roads/**`
- Delete: `installer/agent-assets/codex-skills/design-road/**`
- Delete: `installer/agent-assets/codex-skills/masterplan-roads/**`
- Modify: `README.md:115-145,305-318`
- Modify: `QUICK_START.md:60-69,90-99`
- Modify: `AGENT_SETUP.md:25-37`
- Modify: `installer/agent-assets/ROOK_CLAUDE_POST_INSTALL.md:1-25`
- Modify: `installer/agent-assets/ROOK_CODEX_POST_INSTALL.md:1-27`
- Modify: `scripts/session-start.sh:17-25`
- Modify: `mcp_server/src/rook/server.py:12907-12917`
- Modify: `mcp_server/tests/test_containment_guidance.py`

**Interfaces:**
- Consumes: Task 1's lifecycle-admitted `server._all_live_tools()` and current guidance-scan structure.
- Produces: exact `RETIRED_SKILL_ROOTS`, `RETIRED_GUIDANCE_IDENTITIES`, `ACTIVE_RETIREMENT_GUIDANCE_FILES`, and `RETAINED_WASP_SKILL_ROOTS` test constants.
- Preserves: every skill/reference path outside the six retired roots, including retained Wasp content.

- [ ] **Step 10: Write failing exact-root, active-vocabulary, and retained-Wasp guards**

Add to `test_containment_guidance.py`:

```python
RETIRED_SKILL_ROOTS = (
    ROOT / ".agents" / "skills" / "design-road",
    ROOT / ".agents" / "skills" / "masterplan-roads",
    ROOT / ".claude" / "skills" / "design-road",
    ROOT / ".claude" / "skills" / "masterplan-roads",
    ROOT / "installer" / "agent-assets" / "codex-skills" / "design-road",
    ROOT / "installer" / "agent-assets" / "codex-skills" / "masterplan-roads",
)
RETIRED_GUIDANCE_IDENTITIES = (
    "design-road",
    "masterplan-roads",
    "RoadCreator",
    "RookRoads",
)
ACTIVE_RETIREMENT_GUIDANCE_FILES = (
    ROOT / "README.md",
    ROOT / "QUICK_START.md",
    ROOT / "AGENT_SETUP.md",
    ROOT / "installer" / "agent-assets" / "ROOK_CLAUDE_POST_INSTALL.md",
    ROOT / "installer" / "agent-assets" / "ROOK_CODEX_POST_INSTALL.md",
    ROOT / "scripts" / "session-start.sh",
)
RETAINED_WASP_SKILL_ROOTS = tuple(
    ROOT / prefix / skill
    for prefix in (
        Path(".agents/skills"),
        Path(".claude/skills"),
        Path("installer/agent-assets/codex-skills"),
    )
    for skill in ("chirp-cascade", "design-grasshopper", "plan-grasshopper")
)


def test_retired_road_skill_roots_are_absent() -> None:
    assert [str(path.relative_to(ROOT)) for path in RETIRED_SKILL_ROOTS if path.exists()] == []


def test_scoped_active_guidance_has_no_retired_road_identity() -> None:
    findings = []
    for path in ACTIVE_RETIREMENT_GUIDANCE_FILES:
        text = path.read_text(encoding="utf-8", errors="replace")
        for identity in RETIRED_GUIDANCE_IDENTITIES:
            if identity in text:
                findings.append(f"{path.relative_to(ROOT)}: {identity}")
    assert findings == []


@pytest.mark.asyncio
async def test_live_model_visible_catalog_has_no_retired_road_identity() -> None:
    from rook import server

    tools = await server._all_live_tools()
    rendered = json.dumps(
        [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
            for tool in tools
        ],
        sort_keys=True,
    )
    assert [identity for identity in RETIRED_GUIDANCE_IDENTITIES if identity in rendered] == []


def test_retained_wasp_skill_roots_remain_outside_retired_roots() -> None:
    for path in RETAINED_WASP_SKILL_ROOTS:
        assert path.is_dir(), path
        skill_file = path / "SKILL.md"
        assert skill_file.is_file(), skill_file
        assert "Wasp" in skill_file.read_text(encoding="utf-8", errors="replace")
        assert all(retired not in path.parents and path != retired for retired in RETIRED_SKILL_ROOTS)
```

Do not add roadmap, specification, plan, probes, reports, or historical directories to `ACTIVE_RETIREMENT_GUIDANCE_FILES`.

- [ ] **Step 11: Run the guard tests and verify the intended failures**

Run:

```powershell
python -m pytest mcp_server/tests/test_containment_guidance.py -q
```

Expected: FAIL because all six roots exist and the active files/model-visible search description contain retired identities.

- [ ] **Step 12: Delete exactly the six retired skill roots**

```powershell
git rm -r -- `
  .agents/skills/design-road `
  .agents/skills/masterplan-roads `
  .claude/skills/design-road `
  .claude/skills/masterplan-roads `
  installer/agent-assets/codex-skills/design-road `
  installer/agent-assets/codex-skills/masterplan-roads
```

Do not copy or move either `road-rhino-scaffold.md`; their deletion is owned by the retired parent skills.

- [ ] **Step 13: Remove exact retired claims while preserving supported guidance**

Make these bounded edits:

```text
README.md
  Delete the complete “Road Design (RoadCreator)” section.
  Delete the design-road/masterplan-roads tree row.
  Make the .claude/skills tree heading count-neutral rather than changing 16 to 14.

QUICK_START.md
  Delete the RookRoads + RoadCreator optional-add-on row.
  Delete the /design-road next-step bullet.

AGENT_SETUP.md
  Remove /design-road from the orchestration-skill examples; retain the distinction
  between MCP-only clients and clients that receive supported skills/hooks.

ROOK_CLAUDE_POST_INSTALL.md
  Remove /design-road from the examples.
  Replace “confirm the 11 skills appear” with “confirm the curated Rook skills appear.”

ROOK_CODEX_POST_INSTALL.md
  Remove design-road and masterplan-roads from the list.
  Replace “11 user skills” with count-neutral “curated Rook user skills.”

scripts/session-start.sh
  Delete only the complete paragraph beginning “When the user asks to create a road”.
  Keep Chirp, Grasshopper cascade, consolidate, and twisted-column wording unchanged.

server.py
  In the admitted rook_tools_search description, replace
  “geometry, Grasshopper, vision, RoadCreator, BIM, scene, video, knowledge” with
  “geometry, Grasshopper, native road intersections, vision, BIM, scene, video,
  knowledge”. Do not edit dormant rc_* schema descriptions or dispatch comments.
```

- [ ] **Step 14: Run the complete Task 1 containment contract**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_containment_guidance.py `
  mcp_server/tests/test_containment_catalogs.py `
  mcp_server/tests/test_containment_execution.py `
  mcp_server/tests/test_containment_agent_protocols.py `
  mcp_server/tests/test_containment_packaged_executors.py `
  mcp_server/tests/test_containment_supported_paths.py `
  mcp_server/tests/test_server_tool_profiles.py -q
```

Expected: PASS. A repository search scoped to the six active files returns no exact retired identity:

```powershell
rg -n -i "design-road|masterplan-roads|RoadCreator|RookRoads" `
  README.md QUICK_START.md AGENT_SETUP.md `
  installer/agent-assets/ROOK_CLAUDE_POST_INSTALL.md `
  installer/agent-assets/ROOK_CODEX_POST_INSTALL.md `
  scripts/session-start.sh
```

Expected: no output. Do not run a replacement across historical documents.

Also prove the former exact profile counts were removed from scoped active guidance:

```powershell
rg -n "422 MCP|422 tools|425 available|425 with|advertises 148|148 tools|advertises 20|20 tools" `
  AGENTS.md CLAUDE.md README.md AGENT_SETUP.md `
  docs/CURRENT_ARCHITECTURE.md docs/AGENT_ARCHITECTURE.md
```

Expected: no output. The numeric contract remains only in
`test_profile_surface_counts_are_authoritative`.

- [ ] **Step 15: Commit the complete admitted-surface unit**

```powershell
git add -A -- `
  mcp_server/src/rook/tool_lifecycle.py `
  mcp_server/src/rook/server.py `
  mcp_server/src/rook/mcp_tool_profiles.py `
  mcp_server/src/rook/targeting.py `
  mcp_server/src/rook/agent/tool_groups.py `
  mcp_server/tests/test_containment_catalogs.py `
  mcp_server/tests/test_containment_execution.py `
  mcp_server/tests/test_containment_supported_paths.py `
  mcp_server/tests/test_server_tool_profiles.py `
  mcp_server/tests/test_containment_guidance.py `
  .agents/skills `
  .claude/skills `
  installer/agent-assets/codex-skills `
  AGENTS.md CLAUDE.md README.md QUICK_START.md AGENT_SETUP.md `
  docs/CURRENT_ARCHITECTURE.md docs/AGENT_ARCHITECTURE.md `
  installer/agent-assets/ROOK_CLAUDE_POST_INSTALL.md `
  installer/agent-assets/ROOK_CODEX_POST_INSTALL.md `
  scripts/session-start.sh
git commit -m "feat: contain RoadCreator release surface"
```

---

### Task 2: Exact-Path Codex Skill Migration

**Files:**
- Modify: `installer/post_install.py:18-38,104-137,905-939,1210-1235`
- Modify: `mcp_server/tests/test_python_runtime_install.py`

**Interfaces:**
- Consumes: `_read_install_summary()`, `_write_install_summary()`, `_append_install_summary_warnings()`, and the early `main()` finalizer flow.
- Produces: `RETIRED_CODEX_SKILL_NAMES: tuple[str, str]`, `_is_reparse_point(metadata: os.stat_result) -> bool`, `_remove_retired_codex_skill(target: Path) -> dict[str, str]`, and `cleanup_retired_codex_skills(runtime_root: Path) -> list[dict[str, str]]`.
- Summary contract: `retired_codex_skill_cleanup = {"complete": bool, "targets": [{"name": str, "outcome": str, "error"?: str}]}`.

- [ ] **Step 1: Write failing exact-path and idempotence tests**

Add `import pytest` beside the existing test imports, then add:

```python
def test_retired_codex_skill_cleanup_removes_only_exact_targets(tmp_path: Path, monkeypatch) -> None:
    post_install = load_post_install()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runtime_root = tmp_path / "runtime"
    skills = tmp_path / ".codex" / "skills"
    claude = tmp_path / ".claude" / "skills" / "design-road"
    sibling = skills / "design-grasshopper"
    retired_dir = skills / "design-road"
    retired_file = skills / "masterplan-roads"

    (retired_dir / "nested").mkdir(parents=True)
    (retired_dir / "nested" / "payload.txt").write_text("retired", encoding="utf-8")
    retired_file.write_text("retired-file", encoding="utf-8")
    sibling.mkdir()
    (sibling / "SKILL.md").write_text("supported", encoding="utf-8")
    claude.mkdir(parents=True)
    (claude / "SKILL.md").write_text("claude-owned", encoding="utf-8")

    first = post_install.cleanup_retired_codex_skills(runtime_root)
    second = post_install.cleanup_retired_codex_skills(runtime_root)

    assert [item["outcome"] for item in first] == ["removed_directory", "removed_file"]
    assert [item["outcome"] for item in second] == ["absent", "absent"]
    assert not retired_dir.exists()
    assert not retired_file.exists()
    assert (sibling / "SKILL.md").read_text(encoding="utf-8") == "supported"
    assert (claude / "SKILL.md").read_text(encoding="utf-8") == "claude-owned"
```

- [ ] **Step 2: Write failing non-following reparse and partial-failure tests**

Add:

```python
def test_retired_codex_skill_cleanup_unlinks_link_without_following_target(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runtime_root = tmp_path / "runtime"
    skills = tmp_path / ".codex" / "skills"
    skills.mkdir(parents=True)
    external = tmp_path / "external-road-data"
    external.mkdir()
    sentinel = external / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    target = skills / "design-road"

    if sys.platform == "win32":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(external)],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        target.symlink_to(external, target_is_directory=True)

    outcomes = post_install.cleanup_retired_codex_skills(runtime_root)

    assert outcomes[0]["outcome"] == "unlinked_reparse_point"
    assert not target.exists()
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_retired_cleanup_does_not_follow_nested_reparse_point(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runtime_root = tmp_path / "runtime"
    retired = tmp_path / ".codex" / "skills" / "masterplan-roads"
    retired.mkdir(parents=True)
    external = tmp_path / "external-nested-data"
    external.mkdir()
    sentinel = external / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    nested_link = retired / "nested-link"

    if sys.platform == "win32":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(nested_link), str(external)],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        nested_link.symlink_to(external, target_is_directory=True)

    outcomes = post_install.cleanup_retired_codex_skills(runtime_root)

    assert outcomes[1]["outcome"] == "removed_directory"
    assert not retired.exists()
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_retired_cleanup_failure_is_nonfatal_and_records_incomplete_summary(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runtime_root = tmp_path / "runtime"
    skills = tmp_path / ".codex" / "skills"
    design = skills / "design-road"
    masterplan = skills / "masterplan-roads"
    design.mkdir(parents=True)
    masterplan.write_text("remove me", encoding="utf-8")

    real_rmtree = post_install.shutil.rmtree

    def fail_design(path):
        if Path(path) == design:
            raise PermissionError("blocked design-road")
        return real_rmtree(path)

    monkeypatch.setattr(post_install.shutil, "rmtree", fail_design)
    outcomes = post_install.cleanup_retired_codex_skills(runtime_root)
    summary = json.loads(
        (runtime_root / "logs" / "post_install_summary.json").read_text(encoding="utf-8")
    )

    assert [item["outcome"] for item in outcomes] == ["failed", "removed_file"]
    assert design.exists()
    assert not masterplan.exists()
    assert summary["retired_codex_skill_cleanup"]["complete"] is False
    assert summary["retired_codex_skill_cleanup"]["targets"] == outcomes
    assert any(
        "retired-skill containment is incomplete" in item.lower()
        for item in summary["warnings"]
    )
```

- [ ] **Step 3: Write the failing component-selection integration test**

Add this helper and parametrized test:

```python
def _run_main_for_retired_skill_migration(
    post_install,
    tmp_path: Path,
    monkeypatch,
    codex_selected: bool,
    cleanup_outcomes: list[dict[str, str]] | None = None,
) -> tuple[list[Path], list[bool]]:
    install_dir = tmp_path / "app"
    mcp_server_dir = install_dir / "mcp_server"
    runtime_root = tmp_path / "runtime"
    mcp_server_dir.mkdir(parents=True)
    managed_python = runtime_root / "venv" / "Scripts" / "python.exe"
    managed_python.parent.mkdir(parents=True)
    managed_python.write_text("fake", encoding="utf-8")
    argv = [
        "post_install.py",
        "--install-dir", str(install_dir),
        "--mcp-server-dir", str(mcp_server_dir),
        "--runtime-root", str(runtime_root),
        "--skip-validation",
    ]
    if codex_selected:
        argv.append("--codex")
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(post_install, "install_mcp_server", lambda *_args: managed_python)
    monkeypatch.setattr(post_install, "configure_codex", lambda *_args: True)
    monkeypatch.setattr(post_install, "write_chat_service_manifest", lambda *_args: True)
    monkeypatch.setattr(post_install, "create_env_examples", lambda *_args: None)
    cleanup_calls = []
    asset_calls = []
    monkeypatch.setattr(
        post_install,
        "cleanup_retired_codex_skills",
        lambda runtime: cleanup_calls.append(runtime) or list(cleanup_outcomes or []),
    )
    monkeypatch.setattr(
        post_install,
        "install_user_assets",
        lambda _install_dir, install_claude, install_codex: (
            asset_calls.append(install_codex) or True
        ),
    )
    assert post_install.main() == 0
    return cleanup_calls, asset_calls


@pytest.mark.parametrize("codex_selected", [False, True])
def test_main_runs_retired_skill_migration_regardless_of_codex_selection(
    tmp_path: Path, monkeypatch, codex_selected: bool
) -> None:
    post_install = load_post_install()
    cleanup_calls, asset_calls = _run_main_for_retired_skill_migration(
        post_install, tmp_path, monkeypatch, codex_selected
    )
    assert cleanup_calls == [tmp_path / "runtime"]
    assert asset_calls == [codex_selected]
```

- [ ] **Step 4: Run the migration tests and verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_python_runtime_install.py `
  -k "retired_codex_skill or retired_cleanup or main_runs_retired" -q
```

Expected: FAIL because `cleanup_retired_codex_skills()` does not exist.

- [ ] **Step 5: Implement the small non-following migration helper**

Add `import stat` and these constants/helpers to `post_install.py` near `_copy_children()`:

```python
RETIRED_CODEX_SKILL_NAMES = ("design-road", "masterplan-roads")
_REPARSE_POINT_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _is_reparse_point(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT_ATTRIBUTE
    )


def _remove_retired_codex_skill(target: Path) -> dict[str, str]:
    result = {"name": target.name, "outcome": "absent"}
    try:
        metadata = target.lstat()
    except FileNotFoundError:
        return result
    except OSError as exc:
        return {
            "name": target.name,
            "outcome": "failed",
            "error": str(exc)[:500],
        }

    try:
        if _is_reparse_point(metadata):
            if stat.S_ISDIR(metadata.st_mode):
                os.rmdir(target)
            else:
                target.unlink()
            result["outcome"] = "unlinked_reparse_point"
        elif stat.S_ISDIR(metadata.st_mode):
            shutil.rmtree(target)
            result["outcome"] = "removed_directory"
        else:
            target.unlink()
            result["outcome"] = "removed_file"
    except OSError as exc:
        result["outcome"] = "failed"
        result["error"] = str(exc)[:500]
    return result


def cleanup_retired_codex_skills(runtime_root: Path) -> list[dict[str, str]]:
    try:
        skills_root = (Path.home() / ".codex" / "skills").resolve(strict=False)
    except OSError as exc:
        outcomes = [
            {"name": name, "outcome": "failed", "error": str(exc)[:500]}
            for name in RETIRED_CODEX_SKILL_NAMES
        ]
    else:
        outcomes = []
        for name in RETIRED_CODEX_SKILL_NAMES:
            target = skills_root / name
            if target.parent != skills_root or target.name != name:
                outcomes.append({
                    "name": name,
                    "outcome": "failed",
                    "error": "target is not a direct child of the canonical Codex skills root",
                })
                continue
            outcomes.append(_remove_retired_codex_skill(target))

    failed = [item for item in outcomes if item["outcome"] == "failed"]
    payload = _read_install_summary(runtime_root)
    payload["retired_codex_skill_cleanup"] = {
        "complete": not failed,
        "targets": outcomes,
    }
    if failed:
        warning = (
            "Retired-skill containment is incomplete: "
            + ", ".join(item["name"] for item in failed)
        )
        _append_install_summary_warnings(payload, [warning])
        print(f"WARNING: {warning}")
        _INSTALL_LOGGER.warning("%s outcomes=%s", warning, outcomes)
    else:
        print(f"Retired Codex skill migration: {outcomes}")
        _INSTALL_LOGGER.info("Retired Codex skill migration outcomes=%s", outcomes)
    _write_install_summary(runtime_root, payload)
    return outcomes
```

The helper resolves only the parent. It must not call `resolve()` on either target before `lstat()`.

- [ ] **Step 6: Invoke migration before failure-prone component work**

In `main()`, immediately after `_update_install_summary(... finalizer-started ...)` and the startup banner, add:

```python
    cleanup_retired_codex_skills(runtime_root)
```

Keep `install_user_assets()` component-gated exactly for copying. Do not put cleanup inside its `if not install_codex` branch.

- [ ] **Step 7: Prove cleanup failure does not block supported skill installation**

Use the integration helper's explicit `cleanup_outcomes` input and asset-call capture:

```python
def test_cleanup_failure_does_not_block_selected_codex_skill_copy(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    cleanup_calls, asset_calls = _run_main_for_retired_skill_migration(
        post_install,
        tmp_path,
        monkeypatch,
        codex_selected=True,
        cleanup_outcomes=[{"name": "design-road", "outcome": "failed"}],
    )
    assert cleanup_calls == [tmp_path / "runtime"]
    assert asset_calls == [True]
```

Do not introduce a production abstraction only to shorten this test setup.

- [ ] **Step 8: Run installer unit and release guard tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_python_runtime_install.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-installer-guards.tests.ps1
```

Expected: the pytest file and guard script PASS. Confirm the failure test leaves `final_outcome` available for the outer finalizer while `retired_codex_skill_cleanup.complete` remains `false`.

- [ ] **Step 9: Commit the migration unit**

```powershell
git add -- installer/post_install.py mcp_server/tests/test_python_runtime_install.py
git commit -m "fix: remove retired Codex road skills on upgrade"
```

---

### Task 3: Integrated Containment Acceptance and PR Evidence

**Files:**
- Verify only; do not create a permanent evidence or hash fixture.
- PR evidence references base: `c7687554ceba29be8cf559cb3244cce0d56d6fd1`

**Interfaces:**
- Consumes: both implementation commits, the approved design, current release scripts, and the installed MCP Python runtime.
- Produces: test/build/smoke output copied into the private PR description or check run.

- [ ] **Step 1: Record the repository-wide suite caveat and baseline comparison**

Do not claim that the repository-wide suite is green and do not rerun it for this
containment acceptance. Cite the prior identical locked-environment comparison instead:
624 failures/errors were common and pre-existing, one baseline-only result was
order/environment pollution, and the two candidate-only failures were stale expectations
corrected in the containment test commit. Use the focused containment, installer, packaging,
build, and installed-smoke gates below as the acceptance evidence.

- [ ] **Step 2: Run release and installer guard suites**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-installer-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/validate-release-artifacts.tests.ps1
```

Expected: both guard scripts PASS.

- [ ] **Step 3: Compare retained Wasp product assets against the pinned base**

Run this one-off PowerShell acceptance check; do not save its hashes in the repository:

```powershell
$base = 'c7687554ceba29be8cf559cb3244cce0d56d6fd1'
$roots = @('.agents/skills', '.claude/skills', 'installer/agent-assets/codex-skills')
$retired = @(
  '.agents/skills/design-road', '.agents/skills/masterplan-roads',
  '.claude/skills/design-road', '.claude/skills/masterplan-roads',
  'installer/agent-assets/codex-skills/design-road',
  'installer/agent-assets/codex-skills/masterplan-roads'
)
$baseEntries = @(git grep -Il -i 'Wasp' $base -- $roots)
$basePaths = @($baseEntries | ForEach-Object {
  $_.Substring($_.IndexOf(':') + 1).Replace('\', '/')
} | Where-Object {
  $path = $_
  -not ($retired | Where-Object { $path -eq $_ -or $path.StartsWith("$_/") })
} | Sort-Object -Unique)
$currentEntries = @(git grep -Il -i 'Wasp' HEAD -- $roots)
$currentPaths = @($currentEntries | ForEach-Object {
  $_.Substring($_.IndexOf(':') + 1).Replace('\', '/')
} | Where-Object {
  $path = $_
  -not ($retired | Where-Object { $path -eq $_ -or $path.StartsWith("$_/") })
} | Sort-Object -Unique)
$pathDiff = @(Compare-Object $basePaths $currentPaths)
if ($pathDiff) { throw "Retained Wasp path inventory changed: $($pathDiff | Out-String)" }
foreach ($path in $basePaths) {
  $baseHash = (git rev-parse "$base`:$path").Trim()
  $currentHash = (git hash-object -- $path).Trim()
  if ($baseHash -ne $currentHash) { throw "Retained Wasp asset changed: $path" }
}
"Retained Wasp assets unchanged: $($basePaths.Count) files"
```

Expected: one success line and no mismatch.

- [ ] **Step 4: Prove dormant schema and dispatch ASTs are unchanged**

Run:

```powershell
@'
import ast
import subprocess
from pathlib import Path

BASE = "c7687554ceba29be8cf559cb3244cce0d56d6fd1"
PATH = "mcp_server/src/rook/server.py"

def base_text():
    return subprocess.run(
        ["git", "show", f"{BASE}:{PATH}"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout

def snapshots(source):
    tree = ast.parse(source)
    schemas = {}
    dispatch = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Tool":
            name = next(
                (kw.value.value for kw in node.keywords
                 if kw.arg == "name" and isinstance(kw.value, ast.Constant)),
                None,
            )
            if isinstance(name, str) and name.startswith("rc_"):
                schemas[name] = ast.dump(node, include_attributes=False)
        if isinstance(node, ast.match_case):
            pattern = node.pattern
            if (
                isinstance(pattern, ast.MatchValue)
                and isinstance(pattern.value, ast.Constant)
                and isinstance(pattern.value.value, str)
                and pattern.value.value.startswith("rc_")
            ):
                dispatch[pattern.value.value] = tuple(
                    ast.dump(statement, include_attributes=False)
                    for statement in node.body
                )
    return schemas, dispatch

before = snapshots(base_text())
after = snapshots(Path(PATH).read_text(encoding="utf-8"))
assert before == after, "Dormant rc_* schema or dispatch AST changed"
assert len(after[0]) == 40
assert len(after[1]) == 40
print("Dormant rc_* schemas and dispatch cases unchanged: 40/40")
'@ | python -
```

Expected: `Dormant rc_* schemas and dispatch cases unchanged: 40/40`.

- [ ] **Step 5: Prove dedicated protected paths have no diff**

```powershell
$protected = @(
  'src/RookNative',
  'mcp_server/src/rook/bridge.py',
  'mcp_server/src/rook/agent/tool_dispatcher.py',
  'knowledge/roads/profiles'
)
$protectedDiff = @(git diff --name-status c7687554..HEAD -- $protected)
if ($protectedDiff) { throw "Protected implementation changed: $($protectedDiff | Out-String)" }
git diff --name-status c7687554..HEAD
```

Expected: no protected diff. Review the complete name list and confirm every path belongs to this design, current active architecture guidance, the six retired roots, focused tests, or this plan/specification. Historical-document paths must not appear.

- [ ] **Step 6: Build and validate the Python wheelhouse and installer payload**

Use the repository's pinned release version `1.5.16`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/python-runtime/stage-rook-python-runtime.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/python-runtime/build-rook-python-wheelhouse.ps1 -Version 1.5.16
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/validate-python-wheelhouse.ps1 -Version 1.5.16
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' `
  'C:\Users\aryan\source\repos\Rook-deploy-main-90242fa4\installer\RookSetup.iss'
```

Expected: wheelhouse validation PASS and Inno Setup reports `Successful compile`. Inspect the compiler source list and confirm neither retired skill root is staged.

- [ ] **Step 7: Run installed MCP containment/native-boundary smoke without Rhino geometry**

After installing the candidate installer, run:

```powershell
$installedPython = Join-Path $env:LOCALAPPDATA 'Rook\venv\Scripts\python.exe'
@'
import asyncio
import json
from rook import server

NATIVE = {
    "road_intersection_candidates": "/road/intersection/candidates",
    "road_intersection_resolve": "/road/intersection/resolve",
}

async def main():
    tools = await server.list_tools()
    names = {tool.name for tool in tools}
    assert not {name for name in names if name.startswith("rc_")}
    assert set(NATIVE) <= names

    search = await server.call_tool("rook_tools_search", {"query": "rc_ping"})
    assert "rc_ping" not in search[0].text
    hidden_read = await server.call_tool("rook_tools_read", {"name": "rc_ping"})
    assert "unknown_or_non_dispatchable" in hidden_read[0].text

    for name in NATIVE:
        read = await server.call_tool("rook_tools_read", {"name": name})
        payload = json.loads(read[0].text)
        assert payload["name"] == name

    routed = []
    async def fake_call_rhino(path, method="GET", data=None, *, port=None, **_kwargs):
        routed.append((path, method, data, port))
        return {"success": True, "data": {"verified": True}}

    server.call_rhino = fake_call_rhino
    for name, path in NATIVE.items():
        result = await server._call_tool_dispatch(name, {"smoke": True, "port": 12001})
        assert result["success"] is True
        assert routed[-1] == (path, "POST", {"smoke": True}, 12001)

    for name in ("rc_ping", "rc_future_probe"):
        denied = await server.call_tool(name, {})
        assert "legacy_semantic_tool_contained" in denied[0].text
    print("installed containment/native routing smoke passed")

asyncio.run(main())
'@ | & $installedPython -
```

Expected: `installed containment/native routing smoke passed`. Do not start Rhino or require geometry execution.

- [ ] **Step 8: Confirm installed migration outcomes for selected and deselected repair**

Run the candidate installer twice with explicit component sets, once with Codex selected
and once with Codex deselected. This script seeds only the two exact retired paths plus
one dedicated sibling sentinel before each repair and validates the summary afterward:

```powershell
$installer = (Resolve-Path 'installer\output\Rook-Setup-1.5.16.exe').Path
$skills = Join-Path $HOME '.codex\skills'
$retired = @('design-road', 'masterplan-roads')
$sibling = Join-Path $skills 'containment-sibling-sentinel'
$summaryPath = Join-Path $env:LOCALAPPDATA 'Rook\logs\post_install_summary.json'

function Invoke-ContainmentRepair {
  param([string]$Components)
  New-Item -ItemType Directory -Force -Path $sibling | Out-Null
  Set-Content -LiteralPath (Join-Path $sibling 'keep.txt') -Value 'keep'
  foreach ($name in $retired) {
    New-Item -ItemType Directory -Force -Path (Join-Path $skills $name) | Out-Null
  }
  $process = Start-Process -FilePath $installer -WindowStyle Hidden -Wait -PassThru `
    -ArgumentList @(
      '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/TYPE=custom',
      "/COMPONENTS=$Components"
    )
  if ($process.ExitCode -ne 0) {
    throw "Repair failed: $Components exit=$($process.ExitCode)"
  }
  foreach ($name in $retired) {
    if (Test-Path -LiteralPath (Join-Path $skills $name)) {
      throw "Retired skill survived repair: $name"
    }
  }
  if ((Get-Content -LiteralPath (Join-Path $sibling 'keep.txt') -Raw).Trim() -ne 'keep') {
    throw 'Sibling sentinel changed'
  }
  $summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
  if (-not $summary.retired_codex_skill_cleanup.complete) {
    throw "Cleanup incomplete: $($summary.retired_codex_skill_cleanup | ConvertTo-Json -Depth 5)"
  }
  if (@($summary.retired_codex_skill_cleanup.targets).Count -ne 2) {
    throw 'Cleanup summary did not report exactly two targets'
  }
}

Invoke-ContainmentRepair -Components 'plugins,mcp,codex'
Invoke-ContainmentRepair -Components 'plugins,mcp'

$canonicalSkills = (Resolve-Path -LiteralPath $skills).Path
$canonicalSiblingParent = (Resolve-Path -LiteralPath (Split-Path -Parent $sibling)).Path
if ($canonicalSiblingParent -ne $canonicalSkills) {
  throw 'Unsafe sentinel cleanup target'
}
Remove-Item -LiteralPath $sibling -Recurse -Force
```

Expected: both repairs exit zero; both exact retired paths are absent; the sibling
sentinel remains unchanged until its validated cleanup; the summary reports two bounded
outcomes with `complete: true`. Do not enumerate or clean any other skill.

- [ ] **Step 9: Final clean-tree and commit audit**

```powershell
git status --short --branch
git log --oneline abb62336..HEAD
git diff --check abb62336..HEAD
```

Expected: clean tree, two focused implementation commits after the plan commit, and no whitespace errors. Copy the test, Wasp, dormant-block, protected-path, build, installed-smoke, and migration outputs into the private PR evidence.

Do not open or modify the public `rook-release` promotion in this task. Create that separate PR only after the private containment PR is accepted; its scope is public-page removal plus one one-time release note.
