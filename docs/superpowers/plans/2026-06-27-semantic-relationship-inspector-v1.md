# Semantic Relationship Inspector v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `scene_semantic_relationships`, a read-only object-centric inspector for already-projected `relationship_fact_v1` edges in the current Python scene graph.

**Architecture:** Put all business logic in a focused `rook.scene.semantic_relationship_inspector` module. Keep `server.py`, `tool_dispatcher.py`, `tool_groups.py`, and `targeting.py` as thin schema/dispatch/registration seams. The inspector reads the current in-memory `SceneGraphAnalytics.graph`; it does not sync, project, infer, mutate Rhino, or include fuzzy spatial edges.

**Tech Stack:** Python 3, pytest, NetworkX `MultiDiGraph` through `SceneGraphAnalytics`, existing MCP server `Tool` schemas, existing Rook local tool dispatcher and targeting policy tables.

---

## 1. Reviewer Backfill

Worktree:

```text
C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph
```

Branch:

```text
codex/semantic-relationship-inspector-v1
```

Approved spec:

```text
docs/superpowers/specs/2026-06-27-semantic-relationship-inspector-v1-design.md
```

Stack base:

```text
a601bc7f docs: clarify semantic relationship count semantics
```

Lower stack already provides:

- `scene_project_relationship_facts`;
- `relationship_fact_v1` projected owner-object-to-owner-object edges;
- smoke and Pearson `g002` round-trip tests proving projection works;
- `scene_context(sync=false)` readable relationship-fact prose.

This slice adds a structured inspector over those already-projected edges. It must not add display
overlays, inference, sync, implicit projection, or fuzzy-edge fallback.

## 2. File Structure

Create:

```text
mcp_server/src/rook/scene/semantic_relationship_inspector.py
```

Responsibility: validation, relationship-fact edge extraction, filtering, object grouping,
diagnostics, counts, and response shaping.

Create:

```text
mcp_server/tests/test_semantic_relationship_inspector.py
```

Responsibility: pure unit tests for the read-model behavior. No MCP dispatch, no Rhino.

Create:

```text
mcp_server/tests/test_semantic_relationship_inspector_tool.py
```

Responsibility: server schema, local dispatcher, tool group, targeting policy, and dispatch behavior
tests. No Rhino.

Modify:

```text
mcp_server/src/rook/server.py
mcp_server/src/rook/agent/tool_dispatcher.py
mcp_server/src/rook/agent/tool_groups.py
mcp_server/src/rook/targeting.py
```

Responsibility: thin registration only.

Do not modify:

```text
mcp_server/src/rook/scene/relationship_fact_projection.py
mcp_server/src/rook/scene/relationship_fact_roundtrip.py
mcp_server/src/rook/scene/scene_graph.py
```

If implementation appears to require changing those files, stop and re-check the design. This
slice is an inspector over existing projected edges.

## 3. Task 1: Pure Inspector Module

**Files:**

- Create: `mcp_server/tests/test_semantic_relationship_inspector.py`
- Create: `mcp_server/src/rook/scene/semantic_relationship_inspector.py`

- [ ] **Step 1: Write the failing pure tests**

Create `mcp_server/tests/test_semantic_relationship_inspector.py`:

```python
import pytest

from rook.scene.scene_graph import SceneGraphAnalytics
from rook.scene.semantic_relationship_inspector import query_semantic_relationships


def _scene_graph() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node("member-id", name="spine_base_to_spine_top", domain_label="member")
    sg.graph.add_node("joint-id", name="spine_base", domain_label="joint")
    sg.graph.add_node("other-id", name="unrelated", domain_label="marker")
    sg.graph.add_node("missing-peer-id", name="unused", domain_label="marker")
    sg.graph.add_edge(
        "member-id",
        "joint-id",
        key="relationship_fact:authored_graph_user_strings:pearson_robot_skeleton_graph:g002:reclined_robot:spine",
        relationship="connects",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="connects",
        relationshipFactId="spine_base_to_spine_top.start_connects_spine_base",
        provenance="authored_assembly_graph",
        confidence=1.0,
        status="accepted",
        sourceMode="authored_graph_user_strings",
        contactKind="point_to_point",
        graphSource="pearson_robot_skeleton_graph",
        graphRevision="g002",
        pose="reclined_robot",
        fromFeature="spine_base_to_spine_top.start",
        toFeature="spine_base.point",
        relationshipObjectId="relationship-marker-id",
        fromFeatureObjectId="feature-member-start-id",
        toFeatureObjectId="feature-joint-point-id",
        engineVersion=1,
    )
    sg.graph.add_edge(
        "member-id",
        "other-id",
        key="spatial:near",
        relationship="near",
        projectionKind="spatial_heuristic_v1",
    )
    return sg


def test_missing_object_ids_is_validation_failure():
    result = query_semantic_relationships(_scene_graph(), object_ids=[])

    assert result == {
        "success": False,
        "error": "missing_object_ids",
        "message": "scene_semantic_relationships requires object_ids in v1",
    }


def test_invalid_direction_is_validation_failure():
    result = query_semantic_relationships(_scene_graph(), object_ids=["member-id"], direction="sideways")

    assert result == {
        "success": False,
        "error": "invalid_direction",
        "message": "direction must be one of: both, outgoing, incoming",
    }


def test_object_entries_preserve_input_order_and_missing_objects():
    result = query_semantic_relationships(
        _scene_graph(),
        object_ids=["missing-id", "member-id", "missing-id", "other-id"],
    )

    assert result["success"] is True
    assert result["counts"]["requestedObjectCount"] == 3
    assert result["counts"]["existingSelectedObjectCount"] == 2
    assert result["counts"]["missingSelectedObjectCount"] == 1
    assert [entry["objectId"] for entry in result["objects"]] == ["missing-id", "member-id", "other-id"]
    assert result["objects"][0] == {
        "objectId": "missing-id",
        "exists": False,
        "name": None,
        "facts": [],
        "lines": [],
    }
    assert result["diagnostics"]["missingSelectedObjects"] == 1


def test_outgoing_fact_ignores_fuzzy_edges_and_reports_structured_fields():
    result = query_semantic_relationships(_scene_graph(), object_ids=["member-id"])

    assert result["success"] is True
    assert result["projectionKind"] == "relationship_fact_v1"
    assert result["counts"]["relationshipFactCount"] == 1
    assert result["counts"]["relationshipViewCount"] == 1
    member = result["objects"][0]
    assert member["exists"] is True
    assert member["name"] == "spine_base_to_spine_top"
    assert len(member["facts"]) == 1
    fact = member["facts"][0]
    assert fact["direction"] == "outgoing"
    assert fact["relationship"] == "connects"
    assert fact["objectId"] == "member-id"
    assert fact["otherObjectId"] == "joint-id"
    assert fact["otherName"] == "spine_base"
    assert fact["fromFeature"] == "spine_base_to_spine_top.start"
    assert fact["toFeature"] == "spine_base.point"
    assert fact["contactKind"] == "point_to_point"
    assert fact["provenance"] == "authored_assembly_graph"
    assert fact["confidence"] == 1.0
    assert fact["status"] == "accepted"
    assert fact["graphSource"] == "pearson_robot_skeleton_graph"
    assert fact["graphRevision"] == "g002"
    assert fact["pose"] == "reclined_robot"
    assert "connects spine_base via spine_base_to_spine_top.start -> spine_base.point" in member["lines"][0]


def test_incoming_direction_view_for_target_object():
    result = query_semantic_relationships(_scene_graph(), object_ids=["joint-id"])

    joint = result["objects"][0]
    assert result["counts"]["relationshipFactCount"] == 1
    assert result["counts"]["relationshipViewCount"] == 1
    assert joint["facts"][0]["direction"] == "incoming"
    assert joint["facts"][0]["otherObjectId"] == "member-id"
    assert "connected by spine_base_to_spine_top" in joint["lines"][0]


def test_selecting_both_endpoints_counts_unique_fact_and_two_views():
    result = query_semantic_relationships(_scene_graph(), object_ids=["member-id", "joint-id"])

    assert result["counts"]["relationshipFactCount"] == 1
    assert result["counts"]["relationshipViewCount"] == 2
    assert [len(entry["facts"]) for entry in result["objects"]] == [1, 1]
    assert result["objects"][0]["facts"][0]["direction"] == "outgoing"
    assert result["objects"][1]["facts"][0]["direction"] == "incoming"


def test_direction_filter_is_relative_to_selected_object():
    outgoing = query_semantic_relationships(_scene_graph(), object_ids=["member-id", "joint-id"], direction="outgoing")
    incoming = query_semantic_relationships(_scene_graph(), object_ids=["member-id", "joint-id"], direction="incoming")

    assert outgoing["counts"]["relationshipFactCount"] == 1
    assert outgoing["counts"]["relationshipViewCount"] == 1
    assert [len(entry["facts"]) for entry in outgoing["objects"]] == [1, 0]
    assert incoming["counts"]["relationshipFactCount"] == 1
    assert incoming["counts"]["relationshipViewCount"] == 1
    assert [len(entry["facts"]) for entry in incoming["objects"]] == [0, 1]


def test_filters_apply_before_grouping_and_report_filter_diagnostics():
    result = query_semantic_relationships(
        _scene_graph(),
        object_ids=["member-id"],
        graph_source="other_source",
        graph_revision="g002",
        poses=["reclined_robot"],
        relationship_types=["connects"],
        status=["accepted"],
        provenance=["authored_assembly_graph"],
    )

    assert result["success"] is True
    assert result["counts"]["relationshipFactCount"] == 0
    assert result["counts"]["relationshipViewCount"] == 0
    assert result["diagnostics"]["filteredByGraphSource"] == 1
    assert result["diagnostics"]["noFactsForSelectedObjects"] == 1


def test_empty_graph_diagnostics_distinguish_no_projection_from_no_facts_for_selection():
    no_projection = SceneGraphAnalytics()
    no_projection.graph.add_node("member-id", name="member")

    result = query_semantic_relationships(no_projection, object_ids=["member-id"])

    assert result["diagnostics"]["noProjectedRelationshipFacts"] == 1
    assert result["diagnostics"]["projectionRequired"] == 1
    assert "noFactsForSelectedObjects" not in result["diagnostics"]

    existing_projection = query_semantic_relationships(_scene_graph(), object_ids=["other-id"])
    assert existing_projection["diagnostics"]["noFactsForSelectedObjects"] == 1
    assert "noProjectedRelationshipFacts" not in existing_projection["diagnostics"]
```

- [ ] **Step 2: Run the pure tests to verify failure**

Run:

```powershell
python -m pytest mcp_server/tests/test_semantic_relationship_inspector.py -q
```

Expected: collection fails with:

```text
ModuleNotFoundError: No module named 'rook.scene.semantic_relationship_inspector'
```

- [ ] **Step 3: Add the inspector module**

Create `mcp_server/src/rook/scene/semantic_relationship_inspector.py`:

```python
from __future__ import annotations

from typing import Any


PROJECTION_KIND = "relationship_fact_v1"
VALID_DIRECTIONS = {"both", "outgoing", "incoming"}

CORE_FACT_FIELDS = (
    "relationship",
    "fromFeature",
    "toFeature",
    "contactKind",
    "provenance",
    "confidence",
    "status",
    "graphSource",
    "graphRevision",
    "pose",
)

OPTIONAL_FACT_FIELDS = (
    "semanticRelationshipType",
    "relationshipFactId",
    "sourceMode",
    "relationshipObjectId",
    "fromFeatureObjectId",
    "toFeatureObjectId",
    "engineVersion",
)


def _bump(diagnostics: dict[str, int], key: str) -> None:
    diagnostics[key] = diagnostics.get(key, 0) + 1


def _dedupe_object_ids(object_ids: list[str] | None) -> list[str]:
    if not object_ids:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for raw_id in object_ids:
        object_id = str(raw_id)
        if object_id in seen:
            continue
        seen.add(object_id)
        result.append(object_id)
    return result


def _node_name(graph: Any, node_id: str) -> str | None:
    attrs = graph.nodes.get(node_id, {})
    value = attrs.get("displayName") or attrs.get("name") or attrs.get("label")
    return str(value) if value else str(node_id)


def _relationship(attrs: dict[str, Any]) -> str | None:
    value = attrs.get("semanticRelationshipType") or attrs.get("relationship")
    return str(value) if value is not None else None


def _projected_edges(graph: Any) -> list[tuple[str, str, Any, dict[str, Any]]]:
    return [
        (str(source), str(target), key, dict(attrs))
        for source, target, key, attrs in graph.edges(keys=True, data=True)
        if attrs.get("projectionKind") == PROJECTION_KIND
    ]


def _matches_filters(
    attrs: dict[str, Any],
    *,
    graph_source: str | None,
    graph_revision: str | None,
    poses: list[str] | None,
    relationship_types: list[str] | None,
    status: list[str] | None,
    provenance: list[str] | None,
    diagnostics: dict[str, int],
) -> bool:
    if graph_source is not None and attrs.get("graphSource") != graph_source:
        _bump(diagnostics, "filteredByGraphSource")
        return False
    if graph_revision is not None and attrs.get("graphRevision") != graph_revision:
        _bump(diagnostics, "filteredByGraphRevision")
        return False
    if poses and attrs.get("pose") not in set(poses):
        _bump(diagnostics, "filteredByPose")
        return False
    if relationship_types and _relationship(attrs) not in set(relationship_types):
        _bump(diagnostics, "filteredByRelationshipType")
        return False
    if status and attrs.get("status") not in set(status):
        _bump(diagnostics, "filteredByStatus")
        return False
    if provenance and attrs.get("provenance") not in set(provenance):
        _bump(diagnostics, "filteredByProvenance")
        return False
    return True


def _direction_for(selected_id: str, source_id: str, target_id: str) -> str | None:
    if selected_id == source_id:
        return "outgoing"
    if selected_id == target_id:
        return "incoming"
    return None


def _fact_payload(
    graph: Any,
    *,
    selected_id: str,
    other_id: str,
    direction: str,
    attrs: dict[str, Any],
) -> dict[str, Any]:
    fact: dict[str, Any] = {
        "direction": direction,
        "relationship": _relationship(attrs),
        "objectId": selected_id,
        "otherObjectId": other_id,
        "otherName": _node_name(graph, other_id),
    }
    for field in CORE_FACT_FIELDS:
        if field == "relationship":
            continue
        if field in attrs:
            fact[field] = attrs.get(field)
    for field in OPTIONAL_FACT_FIELDS:
        if field in attrs:
            fact[field] = attrs.get(field)
    return fact


def _line_for_fact(fact: dict[str, Any]) -> str:
    relationship = fact.get("relationship") or "relates to"
    other_name = fact.get("otherName") or fact.get("otherObjectId")
    prefix = (
        f"{relationship} {other_name}"
        if fact.get("direction") == "outgoing"
        else f"connected by {other_name}"
    )
    feature_part = ""
    if fact.get("fromFeature") and fact.get("toFeature"):
        feature_part = f" via {fact['fromFeature']} -> {fact['toFeature']}"
    details = [
        str(value)
        for value in (fact.get("contactKind"), fact.get("status"), fact.get("provenance"))
        if value
    ]
    suffix = f", {', '.join(details)}" if details else ""
    return f"{prefix}{feature_part}{suffix}"


def _empty_entry(graph: Any, object_id: str) -> dict[str, Any]:
    exists = object_id in graph.nodes
    return {
        "objectId": object_id,
        "exists": exists,
        "name": _node_name(graph, object_id) if exists else None,
        "facts": [],
        "lines": [],
    }


def query_semantic_relationships(
    analytics: Any,
    *,
    object_ids: list[str] | None,
    graph_source: str | None = None,
    graph_revision: str | None = None,
    poses: list[str] | None = None,
    relationship_types: list[str] | None = None,
    status: list[str] | None = None,
    provenance: list[str] | None = None,
    direction: str = "both",
) -> dict[str, Any]:
    selected_ids = _dedupe_object_ids(object_ids)
    if not selected_ids:
        return {
            "success": False,
            "error": "missing_object_ids",
            "message": "scene_semantic_relationships requires object_ids in v1",
        }
    if direction not in VALID_DIRECTIONS:
        return {
            "success": False,
            "error": "invalid_direction",
            "message": "direction must be one of: both, outgoing, incoming",
        }

    graph = analytics.graph
    diagnostics: dict[str, int] = {}
    entries = {object_id: _empty_entry(graph, object_id) for object_id in selected_ids}
    missing_count = sum(1 for entry in entries.values() if not entry["exists"])
    if missing_count:
        diagnostics["missingSelectedObjects"] = missing_count

    projected_edges = _projected_edges(graph)
    if not projected_edges:
        diagnostics["noProjectedRelationshipFacts"] = 1
        diagnostics["projectionRequired"] = 1

    selected_existing = {object_id for object_id, entry in entries.items() if entry["exists"]}
    unique_fact_keys: set[tuple[str, str, Any]] = set()
    relationship_view_count = 0

    for source_id, target_id, key, attrs in projected_edges:
        if not _matches_filters(
            attrs,
            graph_source=graph_source,
            graph_revision=graph_revision,
            poses=poses,
            relationship_types=relationship_types,
            status=status,
            provenance=provenance,
            diagnostics=diagnostics,
        ):
            continue
        emitted_for_edge = False
        for selected_id in selected_ids:
            if selected_id not in selected_existing:
                continue
            fact_direction = _direction_for(selected_id, source_id, target_id)
            if fact_direction is None:
                continue
            if direction != "both" and fact_direction != direction:
                _bump(diagnostics, "filteredByDirection")
                continue
            other_id = target_id if fact_direction == "outgoing" else source_id
            fact = _fact_payload(
                graph,
                selected_id=selected_id,
                other_id=other_id,
                direction=fact_direction,
                attrs=attrs,
            )
            entries[selected_id]["facts"].append(fact)
            entries[selected_id]["lines"].append(_line_for_fact(fact))
            relationship_view_count += 1
            emitted_for_edge = True
        if emitted_for_edge:
            unique_fact_keys.add((source_id, target_id, key))

    if projected_edges and relationship_view_count == 0:
        diagnostics["noFactsForSelectedObjects"] = 1

    return {
        "success": True,
        "projectionKind": PROJECTION_KIND,
        "counts": {
            "requestedObjectCount": len(selected_ids),
            "existingSelectedObjectCount": len(selected_existing),
            "missingSelectedObjectCount": missing_count,
            "relationshipFactCount": len(unique_fact_keys),
            "relationshipViewCount": relationship_view_count,
        },
        "objects": [entries[object_id] for object_id in selected_ids],
        "diagnostics": diagnostics,
    }
```

- [ ] **Step 4: Run the pure tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_semantic_relationship_inspector.py -q
```

Expected:

```text
9 passed
```

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add mcp_server/src/rook/scene/semantic_relationship_inspector.py mcp_server/tests/test_semantic_relationship_inspector.py
git commit -m "feat: add semantic relationship inspector read model"
```

## 4. Task 2: MCP and Local Tool Registration

**Files:**

- Create: `mcp_server/tests/test_semantic_relationship_inspector_tool.py`
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/src/rook/targeting.py`

- [ ] **Step 1: Write failing tool surface tests**

Create `mcp_server/tests/test_semantic_relationship_inspector_tool.py`:

```python
import pytest

from rook.scene.scene_graph import SceneGraphAnalytics


def _scene_graph() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node("member-id", name="spine_base_to_spine_top")
    sg.graph.add_node("joint-id", name="spine_base")
    sg.graph.add_edge(
        "member-id",
        "joint-id",
        key="relationship_fact:example",
        relationship="connects",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="connects",
        fromFeature="spine_base_to_spine_top.start",
        toFeature="spine_base.point",
        contactKind="point_to_point",
        provenance="authored_assembly_graph",
        confidence=1.0,
        status="accepted",
        graphSource="pearson_robot_skeleton_graph",
        graphRevision="g002",
        pose="reclined_robot",
    )
    return sg


@pytest.mark.asyncio
async def test_server_tool_schema_exposes_scene_semantic_relationships_parameters():
    from rook.server import list_tools

    tools = {tool.name: tool for tool in await list_tools()}
    schema = tools["scene_semantic_relationships"].inputSchema

    assert schema["required"] == ["object_ids"]
    assert schema["properties"]["object_ids"]["items"]["type"] == "string"
    assert schema["properties"]["graph_source"]["type"] == "string"
    assert schema["properties"]["graph_revision"]["type"] == "string"
    assert schema["properties"]["poses"]["items"]["type"] == "string"
    assert schema["properties"]["relationship_types"]["items"]["type"] == "string"
    assert schema["properties"]["status"]["items"]["type"] == "string"
    assert schema["properties"]["provenance"]["items"]["type"] == "string"
    assert schema["properties"]["direction"]["enum"] == ["both", "outgoing", "incoming"]
    assert "sync" not in schema["properties"]
    assert "project_first" not in schema["properties"]


def test_tool_group_contains_scene_semantic_relationships():
    from rook.agent.tool_groups import TOOL_GROUPS

    assert "scene_semantic_relationships" in TOOL_GROUPS["scene_graph"]


def test_scene_semantic_relationships_targeting_policy_is_rhino_independent_read():
    from rook import targeting

    pol = targeting.policy_for_tool("scene_semantic_relationships")

    assert pol.requires_rhino is False
    assert pol.risk == "read"
    assert "scene_semantic_relationships" in targeting._ALL_KNOWN_TOOLS


def test_local_dispatcher_registers_scene_semantic_relationships():
    from rook.agent.tool_dispatcher import build_local_tools

    tools = build_local_tools()

    assert "scene_semantic_relationships" in tools
    assert callable(tools["scene_semantic_relationships"])


@pytest.mark.asyncio
async def test_local_scene_semantic_relationships_dispatch_uses_current_mirror_without_sync(monkeypatch):
    sg = _scene_graph()
    called = {"sync": 0}

    async def fake_sync(port=None):
        called["sync"] += 1
        return {"synced": True}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)

    from rook.agent.tool_dispatcher import build_local_tools

    result = await build_local_tools()["scene_semantic_relationships"](object_ids=["member-id"])

    assert result["success"] is True
    assert result["counts"]["relationshipFactCount"] == 1
    assert called["sync"] == 0


@pytest.mark.asyncio
async def test_server_dispatch_scene_semantic_relationships_does_not_sync(monkeypatch):
    sg = _scene_graph()
    called = {"sync": 0}

    async def fake_sync(port=None):
        called["sync"] += 1
        return {"synced": True}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch("scene_semantic_relationships", {"object_ids": ["joint-id"]})

    assert result["success"] is True
    assert result["data"]["counts"]["relationshipFactCount"] == 1
    assert result["data"]["objects"][0]["facts"][0]["direction"] == "incoming"
    assert called["sync"] == 0
```

- [ ] **Step 2: Run the tool tests to verify failure**

Run:

```powershell
python -m pytest mcp_server/tests/test_semantic_relationship_inspector_tool.py -q
```

Expected: failures because `scene_semantic_relationships` is not registered in server schema,
local dispatcher, tool groups, or targeting.

- [ ] **Step 3: Register the MCP schema in `server.py`**

In `mcp_server/src/rook/server.py`, add a new `Tool(...)` entry near `scene_project_relationship_facts`:

```python
        Tool(
            name="scene_semantic_relationships",
            description="""Inspect already-projected semantic relationship facts for selected scene objects.

Reads only relationship_fact_v1 edges from the current in-memory Python scene graph. Requires object_ids. Does not sync, project, infer, mutate Rhino, or include fuzzy spatial edges.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Required selected scene object ids to inspect",
                    },
                    "graph_source": {"type": "string", "description": "Optional graphSource filter"},
                    "graph_revision": {"type": "string", "description": "Optional graphRevision filter"},
                    "poses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional pose filter",
                    },
                    "relationship_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional relationship type filter, for example connects",
                    },
                    "status": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional status filter, for example accepted",
                    },
                    "provenance": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional provenance filter, for example authored_assembly_graph",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["both", "outgoing", "incoming"],
                        "description": "Relationship direction relative to each selected object",
                    },
                },
                "required": ["object_ids"],
            },
        ),
```

In `_call_tool_dispatch`, add a case near `scene_project_relationship_facts`:

```python
        case "scene_semantic_relationships":
            from .scene.scene_graph import get_scene_graph
            from .scene.semantic_relationship_inspector import query_semantic_relationships

            payload = query_semantic_relationships(
                get_scene_graph(),
                object_ids=arguments.get("object_ids"),
                graph_source=arguments.get("graph_source"),
                graph_revision=arguments.get("graph_revision"),
                poses=arguments.get("poses"),
                relationship_types=arguments.get("relationship_types"),
                status=arguments.get("status"),
                provenance=arguments.get("provenance"),
                direction=arguments.get("direction", "both"),
            )
            if payload.get("success") is False:
                result = {"success": False, "data": payload}
            else:
                result = {"success": True, "data": payload}
```

Do not call `sync` in this case.

- [ ] **Step 4: Register the local dispatcher wrapper**

In `mcp_server/src/rook/agent/tool_dispatcher.py`, add near the relationship projection local wrapper:

```python
    # --- scene_semantic_relationships (Python-side semantic relationship inspector) ---
    try:
        from ..scene.scene_graph import get_scene_graph
        from ..scene.semantic_relationship_inspector import query_semantic_relationships

        async def _scene_semantic_relationships(
            object_ids=None,
            graph_source=None,
            graph_revision=None,
            poses=None,
            relationship_types=None,
            status=None,
            provenance=None,
            direction="both",
            **kwargs,
        ) -> dict:
            return query_semantic_relationships(
                get_scene_graph(),
                object_ids=object_ids,
                graph_source=graph_source,
                graph_revision=graph_revision,
                poses=poses,
                relationship_types=relationship_types,
                status=status,
                provenance=provenance,
                direction=direction,
            )

        tools["scene_semantic_relationships"] = _scene_semantic_relationships
    except ImportError:
        logger.debug("scene_semantic_relationships local tool unavailable (import failed)")
```

Do not include `port`, `sync`, or `project_first`.

- [ ] **Step 5: Register the tool group**

In `mcp_server/src/rook/agent/tool_groups.py`, add `scene_semantic_relationships` to the `"scene_graph"` group next to `scene_project_relationship_facts`:

```python
        "scene_project_relationship_facts", "scene_semantic_relationships",
```

- [ ] **Step 6: Register targeting policy**

In `mcp_server/src/rook/targeting.py`:

1. Add `"scene_semantic_relationships"` to `_ALL_KNOWN_TOOLS`.
2. Add `"scene_semantic_relationships"` to `_RHINO_INDEPENDENT_READ_TOOLS`.
3. Do not add it to `_META_TOOLS`.
4. Do not add it to `_RHINO_READ_TOOLS`.

Expected policy:

```python
RhinoToolPolicy(False, "read")
```

- [ ] **Step 7: Run tool surface tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_semantic_relationship_inspector_tool.py -q
```

Expected:

```text
6 passed
```

- [ ] **Step 8: Commit Task 2**

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/targeting.py mcp_server/tests/test_semantic_relationship_inspector_tool.py
git commit -m "feat: expose semantic relationship inspector tool"
```

## 5. Task 3: Focused Verification

**Files:**

- Verify only.

- [ ] **Step 1: Run pure inspector tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_semantic_relationship_inspector.py -q
```

Expected:

```text
9 passed
```

- [ ] **Step 2: Run tool tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_semantic_relationship_inspector_tool.py -q
```

Expected:

```text
6 passed
```

- [ ] **Step 3: Run existing relationship projection and round-trip focused tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection.py mcp_server/tests/test_relationship_fact_projection_tool.py mcp_server/tests/test_relationship_fact_roundtrip.py mcp_server/tests/test_pearson_g002_roundtrip_gate.py -q
```

Expected: all tests pass. Current expected count on this branch is:

```text
38 passed
```

If the count differs because upstream tests changed, record the actual passing count.

- [ ] **Step 4: Run combined focused semantic suite**

Run:

```powershell
python -m pytest mcp_server/tests/test_semantic_relationship_inspector.py mcp_server/tests/test_semantic_relationship_inspector_tool.py mcp_server/tests/test_relationship_fact_projection_tool.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Run whitespace and commit checks**

Run:

```powershell
git diff --check
git show --check --stat HEAD
git status --short --branch
```

Expected:

```text
git diff --check
```

prints nothing and exits `0`.

```text
git show --check --stat HEAD
```

prints the latest commit with no whitespace errors.

```text
git status --short --branch
```

shows the branch and no local changes:

```text
## codex/semantic-relationship-inspector-v1...origin/codex/semantic-relationship-inspector-v1 [ahead N]
```

- [ ] **Step 6: Push**

Run:

```powershell
git push
```

Expected: pushes to:

```text
origin/codex/semantic-relationship-inspector-v1
```

## 6. Self-Review Checklist

Before handing off:

- [ ] `scene_semantic_relationships` requires `object_ids`.
- [ ] Missing/empty `object_ids` returns `missing_object_ids`.
- [ ] Invalid `direction` returns `invalid_direction`.
- [ ] No `sync`, `port`, or `project_first` parameter appears in schema or dispatcher.
- [ ] No code calls `SceneGraphAnalytics.sync`.
- [ ] Only `projectionKind == "relationship_fact_v1"` edges appear in facts.
- [ ] Fuzzy spatial edges are ignored.
- [ ] Missing selected objects are returned with `exists: false`.
- [ ] Existing selected objects with no facts are returned with `exists: true`.
- [ ] `relationshipFactCount` counts unique projected edges.
- [ ] `relationshipViewCount` counts emitted object-local fact views.
- [ ] Selecting both endpoints gives one fact and two views.
- [ ] Targeting policy is `requires_rhino=False`, `risk="read"`.
- [ ] No Rhino live test is required for this slice.

## 7. Handoff Notes

Final report should include:

- commit hashes for Task 1 and Task 2;
- exact focused pytest outputs;
- confirmation that no live Rhino gate was required;
- any residual risk, especially around future display-mode consumers relying on `lines`.
