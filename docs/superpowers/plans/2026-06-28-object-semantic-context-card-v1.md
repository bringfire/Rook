# Object Semantic Context Card v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `scene_object_semantic_context`, a read-only per-object semantic context card surface over already-projected `relationship_fact_v1` edges.

**Architecture:** Keep `scene_semantic_relationships` as the raw fact inspector and add a separate `object_semantic_context.py` presentation module that calls the inspector and groups/truncates its object-local fact views. MCP/server/dispatcher/targeting changes are thin registration seams only; no Rhino sync, projection, inference, mutation, or visual overlay is added.

**Tech Stack:** Python 3, NetworkX-backed `SceneGraphAnalytics`, pytest, MCP tool schema in `mcp_server/src/rook/server.py`, local agent dispatcher in `mcp_server/src/rook/agent/tool_dispatcher.py`.

---

## 1. Source Spec

Implement exactly this reviewed spec:

```text
docs/superpowers/specs/2026-06-28-object-semantic-context-card-v1-design.md
```

The branch/worktree is:

```text
C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph
codex/semantic-relationship-display-v1
```

The immediate stack base is:

```text
9440cb6b fix: validate semantic relationship object ids
```

## 2. File Structure

Create:

```text
mcp_server/src/rook/scene/object_semantic_context.py
mcp_server/tests/test_object_semantic_context.py
mcp_server/tests/test_object_semantic_context_tool.py
```

Modify:

```text
mcp_server/src/rook/server.py
mcp_server/src/rook/agent/tool_dispatcher.py
mcp_server/src/rook/agent/tool_groups.py
mcp_server/src/rook/targeting.py
```

Responsibilities:

- `object_semantic_context.py`: validation for card-only bounds, call `query_semantic_relationships`, copy optional object metadata, build zero-card summaries, deterministic summary counts, groups, sample sorting, truncation, diagnostics, and response shaping.
- `test_object_semantic_context.py`: pure read-model tests using synthetic `SceneGraphAnalytics` graphs.
- `test_object_semantic_context_tool.py`: MCP schema, dispatcher, targeting, and no-sync/no-projection registration tests.
- `server.py`: add the tool schema and dispatch case only.
- `tool_dispatcher.py`: add a local wrapper only.
- `tool_groups.py`: add the tool to the `scene_graph` group only.
- `targeting.py`: mark the tool as known, Rhino-independent, read-only.

Do not modify `scene_semantic_relationships` public behavior. If a helper is moved or reused, prove the existing inspector tests still pass unchanged.

## 3. Public Contract Constants

Use these names and defaults:

```python
PROJECTION_KIND = "relationship_fact_v1"
DEFAULT_MAX_GROUPS = 8
DEFAULT_MAX_FACTS_PER_GROUP = 5
VALID_DIRECTIONS = {"both", "outgoing", "incoming"}
GROUP_UNKNOWN = "unknown"
```

Validation failures:

```python
{
    "success": False,
    "error": "missing_object_ids",
    "message": "scene_object_semantic_context requires object_ids in v1",
}
```

```python
{
    "success": False,
    "error": "invalid_object_ids",
    "message": "scene_object_semantic_context requires object_ids to be a list of strings in v1",
}
```

```python
{
    "success": False,
    "error": "invalid_direction",
    "message": "direction must be one of: both, outgoing, incoming",
}
```

```python
{
    "success": False,
    "error": "invalid_card_bounds",
    "message": "max_groups and max_facts_per_group must be positive integers in v1",
}
```

## 4. Task 1: Pure Card Tests

**Files:**
- Create: `mcp_server/tests/test_object_semantic_context.py`
- Read: `mcp_server/tests/test_semantic_relationship_inspector.py`
- Read: `mcp_server/src/rook/scene/semantic_relationship_inspector.py`

- [ ] **Step 1: Create failing pure tests**

Create `mcp_server/tests/test_object_semantic_context.py` with this full content:

```python
import pytest

from rook.scene.scene_graph import SceneGraphAnalytics
from rook.scene.object_semantic_context import query_object_semantic_context


def _scene_graph() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node(
        "member-a",
        name="spine_base_to_spine_top",
        objectKind="block_instance",
        definitionId="robot_member_definition",
        definitionName="RobotMember",
    )
    sg.graph.add_node("member-b", name="pelvis_to_left_hip")
    sg.graph.add_node("joint-a", name="spine_base")
    sg.graph.add_node("joint-b", name="left_hip")
    sg.graph.add_node("empty-id", name="empty_node")
    sg.graph.add_node("marker-id", name="feature_marker")
    sg.graph.add_edge(
        "member-a",
        "joint-a",
        key="relationship_fact:a",
        relationship="connects",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="connects",
        relationshipFactId="fact-a",
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
    )
    sg.graph.add_edge(
        "member-b",
        "joint-a",
        key="relationship_fact:b",
        relationship="connects",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="connects",
        relationshipFactId="fact-b",
        provenance="authored_assembly_graph",
        confidence=1.0,
        status="accepted",
        sourceMode="authored_graph_user_strings",
        contactKind="point_to_point",
        graphSource="pearson_robot_skeleton_graph",
        graphRevision="g002",
        pose="rest_t_pose",
        fromFeature="pelvis_to_left_hip.end",
        toFeature="spine_base.point",
    )
    sg.graph.add_edge(
        "member-a",
        "joint-b",
        key="relationship_fact:c",
        relationship="supports",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="supports",
        relationshipFactId="fact-c",
        provenance="inferred_from_geometry",
        confidence=0.72,
        status="candidate",
        contactKind="point_to_region",
        graphSource="pearson_robot_skeleton_graph",
        graphRevision="g002",
        pose="rest_t_pose",
        fromFeature="spine_base_to_spine_top.end",
        toFeature="left_hip.region",
    )
    sg.graph.add_edge(
        "member-a",
        "empty-id",
        key="spatial:near",
        relationship="near",
        projectionKind="spatial_heuristic_v1",
    )
    return sg


def _zero_summary():
    return {
        "relationshipFactCount": 0,
        "relationshipViewCount": 0,
        "byRelationship": {},
        "byDirection": {},
        "byStatus": {},
        "byProvenance": {},
        "poses": [],
    }


def test_missing_object_ids_is_validation_failure():
    result = query_object_semantic_context(_scene_graph(), object_ids=[])

    assert result == {
        "success": False,
        "error": "missing_object_ids",
        "message": "scene_object_semantic_context requires object_ids in v1",
    }


@pytest.mark.parametrize("bad_object_ids", ["member-a", ("member-a",), ["member-a", 123]])
def test_invalid_object_ids_shape_is_validation_failure(bad_object_ids):
    result = query_object_semantic_context(_scene_graph(), object_ids=bad_object_ids)

    assert result == {
        "success": False,
        "error": "invalid_object_ids",
        "message": "scene_object_semantic_context requires object_ids to be a list of strings in v1",
    }


def test_invalid_direction_is_validation_failure():
    result = query_object_semantic_context(_scene_graph(), object_ids=["member-a"], direction="sideways")

    assert result == {
        "success": False,
        "error": "invalid_direction",
        "message": "direction must be one of: both, outgoing, incoming",
    }


@pytest.mark.parametrize("kwargs", [{"max_groups": 0}, {"max_facts_per_group": -1}, {"max_groups": True}])
def test_invalid_card_bounds_are_validation_failure(kwargs):
    result = query_object_semantic_context(_scene_graph(), object_ids=["member-a"], **kwargs)

    assert result == {
        "success": False,
        "error": "invalid_card_bounds",
        "message": "max_groups and max_facts_per_group must be positive integers in v1",
    }


def test_missing_and_empty_cards_have_full_zero_shape_and_diagnostics():
    result = query_object_semantic_context(_scene_graph(), object_ids=["missing-id", "empty-id"])

    assert result["success"] is True
    assert result["counts"] == {
        "requestedObjectCount": 2,
        "existingSelectedObjectCount": 1,
        "missingSelectedObjectCount": 1,
        "relationshipFactCount": 0,
        "relationshipViewCount": 0,
        "cardCount": 2,
    }
    assert result["cards"][0] == {
        "objectId": "missing-id",
        "exists": False,
        "name": None,
        "objectKind": None,
        "definitionId": None,
        "definitionName": None,
        "canExpandChildren": False,
        "summary": _zero_summary(),
        "groups": [],
        "expandableGroups": [],
    }
    assert result["cards"][1]["objectId"] == "empty-id"
    assert result["cards"][1]["exists"] is True
    assert result["cards"][1]["summary"] == _zero_summary()
    assert result["cards"][1]["groups"] == []
    assert result["diagnostics"]["missingSelectedObjects"] == 1
    assert result["diagnostics"]["noFactsForSelectedObjects"] == 1


def test_card_preserves_order_metadata_summary_and_ignores_fuzzy_edges():
    result = query_object_semantic_context(_scene_graph(), object_ids=["member-a", "joint-a", "member-a"])

    assert result["success"] is True
    assert result["projectionKind"] == "relationship_fact_v1"
    assert [card["objectId"] for card in result["cards"]] == ["member-a", "joint-a"]
    assert result["counts"]["requestedObjectCount"] == 2
    assert result["counts"]["cardCount"] == 2
    assert result["counts"]["relationshipFactCount"] == 3
    assert result["counts"]["relationshipViewCount"] == 4

    member = result["cards"][0]
    assert member["name"] == "spine_base_to_spine_top"
    assert member["objectKind"] == "block_instance"
    assert member["definitionId"] == "robot_member_definition"
    assert member["definitionName"] == "RobotMember"
    assert member["canExpandChildren"] is False
    assert member["summary"]["relationshipFactCount"] == 2
    assert member["summary"]["relationshipViewCount"] == 2
    assert member["summary"]["byRelationship"] == {"connects": 1, "supports": 1}
    assert member["summary"]["byDirection"] == {"outgoing": 2}
    assert member["summary"]["byStatus"] == {"accepted": 1, "candidate": 1}
    assert member["summary"]["byProvenance"] == {
        "authored_assembly_graph": 1,
        "inferred_from_geometry": 1,
    }
    assert member["summary"]["poses"] == ["reclined_robot", "rest_t_pose"]

    joint = result["cards"][1]
    assert joint["summary"]["relationshipFactCount"] == 2
    assert joint["summary"]["relationshipViewCount"] == 2
    assert joint["summary"]["byDirection"] == {"incoming": 2}


def test_groups_are_deterministic_and_sample_facts_keep_raw_fields():
    result = query_object_semantic_context(_scene_graph(), object_ids=["joint-a"])

    groups = result["cards"][0]["groups"]
    assert [group["groupKey"] for group in groups] == [
        "connects:incoming:accepted:authored_assembly_graph"
    ]
    group = groups[0]
    assert group["relationship"] == "connects"
    assert group["direction"] == "incoming"
    assert group["status"] == "accepted"
    assert group["provenance"] == "authored_assembly_graph"
    assert group["count"] == 2
    assert group["truncated"] is False
    assert [fact["relationshipFactId"] for fact in group["sampleFacts"]] == ["fact-b", "fact-a"]
    assert group["sampleFacts"][0]["fromFeature"] == "pelvis_to_left_hip.end"
    assert group["sampleFacts"][0]["toFeature"] == "spine_base.point"
    assert group["sampleFacts"][0]["graphSource"] == "pearson_robot_skeleton_graph"
    assert group["sampleFacts"][0]["graphRevision"] == "g002"
    assert group["sampleFacts"][0]["pose"] == "rest_t_pose"
    assert "connected by pelvis_to_left_hip" in group["lines"][0]


def test_max_facts_per_group_truncates_samples_and_lines():
    result = query_object_semantic_context(
        _scene_graph(),
        object_ids=["joint-a"],
        max_facts_per_group=1,
    )

    group = result["cards"][0]["groups"][0]
    assert group["count"] == 2
    assert group["truncated"] is True
    assert [fact["relationshipFactId"] for fact in group["sampleFacts"]] == ["fact-b"]
    assert len(group["lines"]) == 1


def test_max_groups_populates_expandable_groups():
    result = query_object_semantic_context(
        _scene_graph(),
        object_ids=["member-a"],
        max_groups=1,
    )

    card = result["cards"][0]
    assert len(card["groups"]) == 1
    assert card["groups"][0]["groupKey"] == "connects:outgoing:accepted:authored_assembly_graph"
    assert card["expandableGroups"] == [
        {
            "groupKey": "supports:outgoing:candidate:inferred_from_geometry",
            "relationship": "supports",
            "direction": "outgoing",
            "status": "candidate",
            "provenance": "inferred_from_geometry",
            "count": 1,
            "reason": "group_limit",
        }
    ]


def test_filters_are_forwarded_to_raw_inspector_before_grouping():
    result = query_object_semantic_context(
        _scene_graph(),
        object_ids=["member-a"],
        relationship_types=["supports"],
        status=["candidate"],
        provenance=["inferred_from_geometry"],
        poses=["rest_t_pose"],
    )

    card = result["cards"][0]
    assert result["counts"]["relationshipFactCount"] == 1
    assert result["counts"]["relationshipViewCount"] == 1
    assert card["summary"]["byRelationship"] == {"supports": 1}
    assert card["groups"][0]["groupKey"] == "supports:outgoing:candidate:inferred_from_geometry"
    assert result["diagnostics"]["filteredByRelationshipType"] == 2


def test_empty_graph_reports_projection_required_without_no_facts_for_selection():
    sg = SceneGraphAnalytics()
    sg.graph.add_node("member-a", name="member")

    result = query_object_semantic_context(sg, object_ids=["member-a"])

    assert result["success"] is True
    assert result["diagnostics"]["noProjectedRelationshipFacts"] == 1
    assert result["diagnostics"]["projectionRequired"] == 1
    assert "noFactsForSelectedObjects" not in result["diagnostics"]
```

- [ ] **Step 2: Run pure tests and verify they fail for missing module**

Run:

```powershell
python -m pytest mcp_server/tests/test_object_semantic_context.py -q
```

Expected:

```text
ERROR mcp_server/tests/test_object_semantic_context.py
ModuleNotFoundError: No module named 'rook.scene.object_semantic_context'
```

## 5. Task 2: Object Semantic Context Module

**Files:**
- Create: `mcp_server/src/rook/scene/object_semantic_context.py`
- Test: `mcp_server/tests/test_object_semantic_context.py`

- [ ] **Step 1: Add the implementation module**

Create `mcp_server/src/rook/scene/object_semantic_context.py` with this full content:

```python
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .semantic_relationship_inspector import PROJECTION_KIND, query_semantic_relationships


DEFAULT_MAX_GROUPS = 8
DEFAULT_MAX_FACTS_PER_GROUP = 5
GROUP_UNKNOWN = "unknown"
VALID_DIRECTIONS = {"both", "outgoing", "incoming"}

ZERO_SUMMARY = {
    "relationshipFactCount": 0,
    "relationshipViewCount": 0,
    "byRelationship": {},
    "byDirection": {},
    "byStatus": {},
    "byProvenance": {},
    "poses": [],
}

SAMPLE_SORT_FIELDS = (
    "relationship",
    "direction",
    "otherName",
    "otherObjectId",
    "fromFeature",
    "toFeature",
    "pose",
    "relationshipFactId",
)


def _validation_error(error: str, message: str) -> dict[str, Any]:
    return {"success": False, "error": error, "message": message}


def _valid_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _resolve_bound(value: Any, default: int) -> int | None:
    if value is None:
        return default
    if not _valid_positive_int(value):
        return None
    return value


def _zero_summary() -> dict[str, Any]:
    return {
        "relationshipFactCount": 0,
        "relationshipViewCount": 0,
        "byRelationship": {},
        "byDirection": {},
        "byStatus": {},
        "byProvenance": {},
        "poses": [],
    }


def _bump(bucket: dict[str, int], key: Any) -> None:
    label = str(key) if key not in (None, "") else GROUP_UNKNOWN
    bucket[label] = bucket.get(label, 0) + 1


def _node_attrs(analytics: Any, object_id: str) -> dict[str, Any]:
    if object_id not in analytics.graph.nodes:
        return {}
    return dict(analytics.graph.nodes.get(object_id, {}))


def _card_metadata(analytics: Any, object_id: str, exists: bool) -> dict[str, Any]:
    attrs = _node_attrs(analytics, object_id) if exists else {}
    return {
        "objectKind": attrs.get("objectKind"),
        "definitionId": attrs.get("definitionId"),
        "definitionName": attrs.get("definitionName"),
        "canExpandChildren": False,
    }


def _group_component(value: Any) -> str:
    return str(value) if value not in (None, "") else GROUP_UNKNOWN


def _group_key(fact: dict[str, Any]) -> str:
    return ":".join(
        [
            _group_component(fact.get("relationship")),
            _group_component(fact.get("direction")),
            _group_component(fact.get("status")),
            _group_component(fact.get("provenance")),
        ]
    )


def _sample_sort_key(fact: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(fact.get(field) or "") for field in SAMPLE_SORT_FIELDS)


def _line_for_fact(fact: dict[str, Any]) -> str:
    relationship = fact.get("relationship") or "relates to"
    other_name = fact.get("otherName") or fact.get("otherObjectId")
    if fact.get("direction") == "outgoing":
        prefix = f"{relationship} {other_name}"
    else:
        prefix = f"connected by {other_name}"
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


def _summary_for_facts(facts: list[dict[str, Any]]) -> dict[str, Any]:
    if not facts:
        return _zero_summary()
    by_relationship: dict[str, int] = {}
    by_direction: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_provenance: dict[str, int] = {}
    poses: set[str] = set()
    for fact in facts:
        _bump(by_relationship, fact.get("relationship"))
        _bump(by_direction, fact.get("direction"))
        _bump(by_status, fact.get("status"))
        _bump(by_provenance, fact.get("provenance"))
        if fact.get("pose") not in (None, ""):
            poses.add(str(fact["pose"]))
    return {
        "relationshipFactCount": len(facts),
        "relationshipViewCount": len(facts),
        "byRelationship": dict(sorted(by_relationship.items())),
        "byDirection": dict(sorted(by_direction.items())),
        "byStatus": dict(sorted(by_status.items())),
        "byProvenance": dict(sorted(by_provenance.items())),
        "poses": sorted(poses),
    }


def _group_sort_key(group: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -int(group["count"]),
        str(group["relationship"]),
        str(group["direction"]),
        str(group["status"]),
        str(group["provenance"]),
        str(group["groupKey"]),
    )


def _groups_for_facts(
    facts: list[dict[str, Any]],
    *,
    max_groups: int,
    max_facts_per_group: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        grouped[_group_key(fact)].append(fact)

    all_groups: list[dict[str, Any]] = []
    for group_key, group_facts in grouped.items():
        sample_facts = sorted(group_facts, key=_sample_sort_key)
        first = sample_facts[0]
        visible_facts = sample_facts[:max_facts_per_group]
        all_groups.append(
            {
                "groupKey": group_key,
                "relationship": _group_component(first.get("relationship")),
                "direction": _group_component(first.get("direction")),
                "status": _group_component(first.get("status")),
                "provenance": _group_component(first.get("provenance")),
                "count": len(group_facts),
                "sampleFacts": visible_facts,
                "lines": [_line_for_fact(fact) for fact in visible_facts],
                "truncated": len(group_facts) > max_facts_per_group,
            }
        )

    ordered = sorted(all_groups, key=_group_sort_key)
    visible_groups = ordered[:max_groups]
    expandable_groups = [
        {
            "groupKey": group["groupKey"],
            "relationship": group["relationship"],
            "direction": group["direction"],
            "status": group["status"],
            "provenance": group["provenance"],
            "count": group["count"],
            "reason": "group_limit",
        }
        for group in ordered[max_groups:]
    ]
    return visible_groups, expandable_groups


def _card_from_object_entry(
    analytics: Any,
    entry: dict[str, Any],
    *,
    max_groups: int,
    max_facts_per_group: int,
) -> dict[str, Any]:
    facts = list(entry.get("facts", []))
    groups, expandable_groups = _groups_for_facts(
        facts,
        max_groups=max_groups,
        max_facts_per_group=max_facts_per_group,
    )
    card = {
        "objectId": entry.get("objectId"),
        "exists": bool(entry.get("exists")),
        "name": entry.get("name"),
        **_card_metadata(analytics, str(entry.get("objectId")), bool(entry.get("exists"))),
        "summary": _summary_for_facts(facts),
        "groups": groups,
        "expandableGroups": expandable_groups,
    }
    return card


def query_object_semantic_context(
    analytics: Any,
    *,
    object_ids: Any,
    graph_source: str | None = None,
    graph_revision: str | None = None,
    poses: list[str] | None = None,
    relationship_types: list[str] | None = None,
    status: list[str] | None = None,
    provenance: list[str] | None = None,
    direction: str = "both",
    max_groups: Any = None,
    max_facts_per_group: Any = None,
) -> dict[str, Any]:
    resolved_max_groups = _resolve_bound(max_groups, DEFAULT_MAX_GROUPS)
    resolved_max_facts_per_group = _resolve_bound(
        max_facts_per_group,
        DEFAULT_MAX_FACTS_PER_GROUP,
    )
    if resolved_max_groups is None or resolved_max_facts_per_group is None:
        return _validation_error(
            "invalid_card_bounds",
            "max_groups and max_facts_per_group must be positive integers in v1",
        )

    raw = query_semantic_relationships(
        analytics,
        object_ids=object_ids,
        graph_source=graph_source,
        graph_revision=graph_revision,
        poses=poses,
        relationship_types=relationship_types,
        status=status,
        provenance=provenance,
        direction=direction,
    )

    if raw.get("success") is False:
        error = raw.get("error")
        if error == "missing_object_ids":
            return _validation_error(
                "missing_object_ids",
                "scene_object_semantic_context requires object_ids in v1",
            )
        if error == "invalid_object_ids":
            return _validation_error(
                "invalid_object_ids",
                "scene_object_semantic_context requires object_ids to be a list of strings in v1",
            )
        return raw

    cards = [
        _card_from_object_entry(
            analytics,
            entry,
            max_groups=resolved_max_groups,
            max_facts_per_group=resolved_max_facts_per_group,
        )
        for entry in raw.get("objects", [])
    ]

    counts = dict(raw.get("counts", {}))
    counts["cardCount"] = len(cards)

    return {
        "success": True,
        "projectionKind": PROJECTION_KIND,
        "counts": counts,
        "cards": cards,
        "diagnostics": dict(raw.get("diagnostics", {})),
    }
```

- [ ] **Step 2: Run pure tests and verify they pass**

Run:

```powershell
python -m pytest mcp_server/tests/test_object_semantic_context.py -q
```

Expected:

```text
15 passed
```

- [ ] **Step 3: Run raw inspector tests to verify the raw contract is unchanged**

Run:

```powershell
python -m pytest mcp_server/tests/test_semantic_relationship_inspector.py -q
```

Expected:

```text
10 passed
```

- [ ] **Step 4: Commit pure module and tests**

Run:

```powershell
git add mcp_server/src/rook/scene/object_semantic_context.py mcp_server/tests/test_object_semantic_context.py
git commit -m "feat: add object semantic context cards"
```

## 6. Task 3: Tool Surface Tests

**Files:**
- Create: `mcp_server/tests/test_object_semantic_context_tool.py`
- Read: `mcp_server/tests/test_semantic_relationship_inspector_tool.py`

- [ ] **Step 1: Create failing tool tests**

Create `mcp_server/tests/test_object_semantic_context_tool.py` with this full content:

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
async def test_server_tool_schema_exposes_scene_object_semantic_context_parameters():
    from rook.server import list_tools

    tools = {tool.name: tool for tool in await list_tools()}
    schema = tools["scene_object_semantic_context"].inputSchema

    assert schema["required"] == ["object_ids"]
    assert schema["properties"]["object_ids"]["items"]["type"] == "string"
    assert schema["properties"]["graph_source"]["type"] == "string"
    assert schema["properties"]["graph_revision"]["type"] == "string"
    assert schema["properties"]["poses"]["items"]["type"] == "string"
    assert schema["properties"]["relationship_types"]["items"]["type"] == "string"
    assert schema["properties"]["status"]["items"]["type"] == "string"
    assert schema["properties"]["provenance"]["items"]["type"] == "string"
    assert schema["properties"]["direction"]["enum"] == ["both", "outgoing", "incoming"]
    assert schema["properties"]["max_groups"]["type"] == "integer"
    assert schema["properties"]["max_facts_per_group"]["type"] == "integer"
    assert "sync" not in schema["properties"]
    assert "project_first" not in schema["properties"]
    assert "port" not in schema["properties"]


def test_tool_group_contains_scene_object_semantic_context():
    from rook.agent.tool_groups import TOOL_GROUPS

    assert "scene_object_semantic_context" in TOOL_GROUPS["scene_graph"]


def test_scene_object_semantic_context_targeting_policy_is_rhino_independent_read():
    from rook import targeting

    pol = targeting.policy_for_tool("scene_object_semantic_context")

    assert pol.requires_rhino is False
    assert pol.risk == "read"
    assert "scene_object_semantic_context" in targeting._ALL_KNOWN_TOOLS


def test_local_dispatcher_registers_scene_object_semantic_context():
    from rook.agent.tool_dispatcher import build_local_tools

    tools = build_local_tools()

    assert "scene_object_semantic_context" in tools
    assert callable(tools["scene_object_semantic_context"])


@pytest.mark.asyncio
async def test_local_scene_object_semantic_context_dispatch_uses_current_mirror_without_sync(monkeypatch):
    sg = _scene_graph()
    called = {"sync": 0}

    async def fake_sync(port=None):
        called["sync"] += 1
        return {"synced": True}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)

    from rook.agent.tool_dispatcher import build_local_tools

    result = await build_local_tools()["scene_object_semantic_context"](object_ids=["member-id"])

    assert result["success"] is True
    assert result["counts"]["relationshipFactCount"] == 1
    assert result["counts"]["cardCount"] == 1
    assert result["cards"][0]["groups"][0]["groupKey"] == "connects:outgoing:accepted:authored_assembly_graph"
    assert called["sync"] == 0


@pytest.mark.asyncio
async def test_local_scene_object_semantic_context_rejects_bare_string_object_ids(monkeypatch):
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: _scene_graph())

    from rook.agent.tool_dispatcher import build_local_tools

    result = await build_local_tools()["scene_object_semantic_context"](object_ids="member-id")

    assert result == {
        "success": False,
        "error": "invalid_object_ids",
        "message": "scene_object_semantic_context requires object_ids to be a list of strings in v1",
    }


@pytest.mark.asyncio
async def test_server_dispatch_scene_object_semantic_context_does_not_sync_or_project(monkeypatch):
    sg = _scene_graph()
    called = {"sync": 0, "project": 0}

    async def fake_sync(port=None):
        called["sync"] += 1
        return {"synced": True}

    async def fake_project(*args, **kwargs):
        called["project"] += 1
        return {"success": True}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)
    monkeypatch.setattr(
        "rook.scene.relationship_fact_projection.project_relationship_facts_for_tool",
        fake_project,
    )

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch("scene_object_semantic_context", {"object_ids": ["joint-id"]})

    assert result["success"] is True
    assert result["data"]["counts"]["relationshipFactCount"] == 1
    assert result["data"]["cards"][0]["groups"][0]["direction"] == "incoming"
    assert called == {"sync": 0, "project": 0}


@pytest.mark.asyncio
async def test_server_dispatch_scene_object_semantic_context_rejects_bad_bounds(monkeypatch):
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: _scene_graph())

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch(
        "scene_object_semantic_context",
        {"object_ids": ["member-id"], "max_groups": 0},
    )

    assert result == {
        "success": False,
        "data": {
            "success": False,
            "error": "invalid_card_bounds",
            "message": "max_groups and max_facts_per_group must be positive integers in v1",
        },
    }
```

- [ ] **Step 2: Run tool tests and verify they fail for missing registration**

Run:

```powershell
python -m pytest mcp_server/tests/test_object_semantic_context_tool.py -q
```

Expected:

```text
FAILED ... KeyError: 'scene_object_semantic_context'
FAILED ... AssertionError: assert 'scene_object_semantic_context' in ...
```

## 7. Task 4: MCP And Local Registration

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Test: `mcp_server/tests/test_object_semantic_context_tool.py`

- [ ] **Step 1: Add the MCP schema in `server.py`**

In `mcp_server/src/rook/server.py`, add this `Tool(...)` immediately after the existing
`scene_semantic_relationships` tool:

```python
        Tool(
            name="scene_object_semantic_context",
            description="""Build compact semantic context cards for selected scene objects.

Reads only already-projected relationship_fact_v1 edges from the current in-memory Python scene graph through the semantic relationship inspector. Requires object_ids. Does not sync, project, infer, mutate Rhino, use a port, expand block definitions, or include fuzzy spatial edges.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Required selected scene object ids to summarize",
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
                    "max_groups": {
                        "type": "integer",
                        "description": "Maximum groups per card. Must be a positive integer.",
                    },
                    "max_facts_per_group": {
                        "type": "integer",
                        "description": "Maximum sample facts per group. Must be a positive integer.",
                    },
                },
                "required": ["object_ids"],
            },
        ),
```

- [ ] **Step 2: Add the MCP dispatch case in `server.py`**

In `_call_tool_dispatch`, add this case immediately after `case "scene_semantic_relationships":`
and before `case "scene_bim_facts":`

```python
        case "scene_object_semantic_context":
            from .scene.object_semantic_context import query_object_semantic_context
            from .scene.scene_graph import get_scene_graph

            payload = query_object_semantic_context(
                get_scene_graph(),
                object_ids=arguments.get("object_ids"),
                graph_source=arguments.get("graph_source"),
                graph_revision=arguments.get("graph_revision"),
                poses=arguments.get("poses"),
                relationship_types=arguments.get("relationship_types"),
                status=arguments.get("status"),
                provenance=arguments.get("provenance"),
                direction=arguments.get("direction", "both"),
                max_groups=arguments.get("max_groups"),
                max_facts_per_group=arguments.get("max_facts_per_group"),
            )
            if payload.get("success") is False:
                result = {"success": False, "data": payload}
            else:
                result = {"success": True, "data": payload}
```

Do not pass `port`. Do not call `sync`. Do not call `scene_project_relationship_facts`.

- [ ] **Step 3: Add the local dispatcher wrapper**

In `mcp_server/src/rook/agent/tool_dispatcher.py`, add this block immediately after the
`scene_semantic_relationships` local tool block:

```python
    # --- scene_object_semantic_context (Python-side semantic context cards) ---
    try:
        from ..scene.object_semantic_context import query_object_semantic_context
        from ..scene.scene_graph import get_scene_graph

        async def _scene_object_semantic_context(
            object_ids=None,
            graph_source=None,
            graph_revision=None,
            poses=None,
            relationship_types=None,
            status=None,
            provenance=None,
            direction="both",
            max_groups=None,
            max_facts_per_group=None,
            **kwargs,
        ) -> dict:
            return query_object_semantic_context(
                get_scene_graph(),
                object_ids=object_ids,
                graph_source=graph_source,
                graph_revision=graph_revision,
                poses=poses,
                relationship_types=relationship_types,
                status=status,
                provenance=provenance,
                direction=direction,
                max_groups=max_groups,
                max_facts_per_group=max_facts_per_group,
            )

        tools["scene_object_semantic_context"] = _scene_object_semantic_context
    except ImportError:
        logger.debug("scene_object_semantic_context local tool unavailable (import failed)")
```

- [ ] **Step 4: Add the tool group entry**

In `mcp_server/src/rook/agent/tool_groups.py`, update the `"scene_graph"` group tail from:

```python
        "scene_project_relationship_facts", "scene_semantic_relationships",
```

to:

```python
        "scene_project_relationship_facts", "scene_semantic_relationships",
        "scene_object_semantic_context",
```

- [ ] **Step 5: Add targeting entries**

In `mcp_server/src/rook/targeting.py`, add `"scene_object_semantic_context"` to `_ALL_KNOWN_TOOLS`
near `"scene_semantic_relationships"`:

```python
    "scene_object_semantic_context",
    "scene_semantic_relationships",
```

Add `"scene_object_semantic_context"` to `_RHINO_INDEPENDENT_READ_TOOLS` near
`"scene_semantic_relationships"`:

```python
    "scene_object_semantic_context",
    "scene_semantic_relationships",
```

- [ ] **Step 6: Run tool tests and verify they pass**

Run:

```powershell
python -m pytest mcp_server/tests/test_object_semantic_context_tool.py -q
```

Expected:

```text
8 passed
```

- [ ] **Step 7: Commit registration and tool tests**

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/targeting.py mcp_server/tests/test_object_semantic_context_tool.py
git commit -m "feat: expose object semantic context tool"
```

## 8. Task 5: Focused Regression Suite

**Files:**
- Verify: all files touched above

- [ ] **Step 1: Run the new card tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_object_semantic_context.py mcp_server/tests/test_object_semantic_context_tool.py -q
```

Expected:

```text
23 passed
```

- [ ] **Step 2: Run the raw inspector tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_semantic_relationship_inspector.py mcp_server/tests/test_semantic_relationship_inspector_tool.py -q
```

Expected:

```text
20 passed
```

- [ ] **Step 3: Run projection and roundtrip guard tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection.py mcp_server/tests/test_relationship_fact_projection_tool.py mcp_server/tests/test_relationship_fact_roundtrip.py mcp_server/tests/test_pearson_g002_roundtrip_gate.py -q
```

Expected:

```text
38 passed
```

- [ ] **Step 4: Run the combined focused suite**

Run:

```powershell
python -m pytest mcp_server/tests/test_object_semantic_context.py mcp_server/tests/test_object_semantic_context_tool.py mcp_server/tests/test_semantic_relationship_inspector.py mcp_server/tests/test_semantic_relationship_inspector_tool.py mcp_server/tests/test_relationship_fact_projection_tool.py -q
```

Expected:

```text
53 passed
```

If the number differs because upstream tests were added on this stacked branch, inspect failures.
Passing behavior is required; the exact count may increase if unrelated tests are added.

- [ ] **Step 5: Run whitespace checks**

Run:

```powershell
git diff --check
git show --check --stat HEAD
```

Expected:

```text
no whitespace errors
```

- [ ] **Step 6: Inspect final diff**

Run:

```powershell
git diff --stat origin/codex/semantic-relationship-display-v1...HEAD
git diff -- mcp_server/src/rook/scene/object_semantic_context.py
```

Expected:

```text
The diff is limited to the new context module, its tests, and thin registration seams.
```

## 9. Self-Review Checklist

Before handing this to review, verify:

- [ ] `scene_semantic_relationships` remains the raw structured fact inspector.
- [ ] `scene_object_semantic_context` does not accept `sync`, `port`, `project_first`, or recursive expansion parameters.
- [ ] `scene_object_semantic_context` does not call `sync`.
- [ ] `scene_object_semantic_context` does not call `scene_project_relationship_facts`.
- [ ] Only `relationship_fact_v1` edges appear because the card module consumes the raw inspector.
- [ ] Fuzzy spatial edges are ignored.
- [ ] Missing selected objects return full zero-count card shape.
- [ ] Existing no-fact objects return full zero-count card shape.
- [ ] Optional block metadata is copied only when present.
- [ ] Block definitions and block contents are not expanded.
- [ ] `relationshipFactCount` and `relationshipViewCount` retain inspector semantics.
- [ ] `groupKey` uses `relationship:direction:status:provenance`.
- [ ] Group ordering is deterministic.
- [ ] `sampleFacts` ordering is deterministic before truncation.
- [ ] `max_groups` populates `expandableGroups`.
- [ ] `max_facts_per_group` truncates both `sampleFacts` and `lines`.
- [ ] Shared MCP files contain no card business logic.
- [ ] New tests are synthetic and do not require Rhino.

## 10. Final Commit And Push

- [ ] **Step 1: Check status**

Run:

```powershell
git status --short --branch
```

Expected:

```text
## codex/semantic-relationship-display-v1...origin/codex/semantic-relationship-display-v1 [ahead 2]
```

- [ ] **Step 2: Push the branch**

Run:

```powershell
git push
```

Expected:

```text
codex/semantic-relationship-display-v1 -> codex/semantic-relationship-display-v1
```

- [ ] **Step 3: Report review handoff**

Report:

```text
Implemented scene_object_semantic_context.
Focused tests passed:
- object semantic context tests
- semantic relationship inspector tests
- relationship fact projection/roundtrip guards
Branch clean/synced after push.
```

Do not claim a live Rhino gate for this slice unless a live test is added and run.
