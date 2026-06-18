# BIM Facts Query + Context v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure `scene_bim_facts` query surface and explicit BIM-enriched `scene_context(sync=false)` rendering over already-projected RookBIM graph facts.

**Architecture:** Keep projection and query separate. `scene_project_bim_relationships` remains the explicit enrichment step; the new `bim_facts_query.py` module reads only the current Python `SceneGraphAnalytics.graph` and returns structured query results. MCP/server/local dispatcher wiring wraps that pure module without calling Rhino, Revit, sync, projection, exact adjacency, or containment refinement.

**Tech Stack:** Python 3.10+, `networkx.MultiDiGraph`, existing MCP server/tool schema patterns, pytest, existing Rook `SceneGraphAnalytics`.

---

## File Structure

- Create: `mcp_server/src/rook/scene/bim_facts_query.py`
  - Pure query helpers for projected BIM facts.
  - No runtime route imports and no sync/projection calls.
  - Owns response envelope, mode validation, selector matching, detail serialization, caps, and relationship counts.
- Create: `mcp_server/tests/test_bim_facts_query.py`
  - Offline unit tests for pure query behavior.
  - Builds small in-memory `SceneGraphAnalytics` fixtures with projected BIM nodes/edges.
- Modify: `mcp_server/src/rook/scene/scene_graph.py`
  - Add compact BIM block to `SceneGraphAnalytics._format_node`.
  - Keep generic relationship lines intact.
- Modify: `mcp_server/src/rook/server.py`
  - Add `scene_bim_facts` tool schema.
  - Add `scene_bim_facts` executor case.
  - Add optional `sync` boolean to `scene_context` schema and dispatch.
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
  - Add local `scene_bim_facts` dispatcher.
  - Add or preserve local `scene_context` flag pass-through if this path exists for local scene tools.
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
  - Add `scene_bim_facts` to the scene graph group.
- Modify: `mcp_server/src/rook/targeting.py`
  - Add `scene_bim_facts` to known tools and Rhino read tools.
- Modify: `mcp_server/tests/test_bim_relationship_projection_tool.py`
  - Add server/local/targeting registration tests for `scene_bim_facts`.
  - Add `scene_context(sync=false)` dispatch tests where this file already covers scene tool wiring.
- Modify: `mcp_server/tests/test_scene_graph.py`
  - Add BIM context block formatter tests.

## Shared Test Fixture Shape

Use this fixture pattern in `mcp_server/tests/test_bim_facts_query.py` and context tests:

```python
from rook.scene.scene_graph import SceneGraphAnalytics


def _bim_graph() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg._sequence = 42
    sg.graph.add_node(
        "wall",
        name="Wall-01",
        layer="RookBim::L1::Walls",
        domain_label="wall",
        shape_class="vertical-planar",
        rookbimJoined=True,
        rookbimSidecarFingerprint="fp1",
        revitUniqueId="uid-wall",
        revitElementId="100",
        revitCategory="Walls",
        revitFamily="Basic Wall",
        revitType="Generic 200mm",
        revitName="Wall Type",
        revitLevel="L1",
    )
    sg.graph.add_node(
        "door",
        name="Door-01",
        layer="RookBim::L1::Doors",
        domain_label="door",
        shape_class="compact",
        rookbimJoined=True,
        rookbimSidecarFingerprint="fp1",
        revitUniqueId="uid-door",
        revitElementId="200",
        revitCategory="Doors",
        revitFamily="Single-Flush",
        revitType="0915 x 2134mm",
        revitName="Door Type",
        revitLevel="L1",
    )
    sg.graph.add_node("chair", name="Chair-01", domain_label="furniture", shape_class="compact")
    sg.graph.add_node(
        "room-a",
        nodeKind="rookbim_room",
        displayName="101 Office",
        roomUniqueId="room-1",
        roomNumber="101",
        roomName="Office",
        sidecarFingerprint="fp1",
        projectionKind="bim_relationship_v1",
        provenance="rookbim_sidecar",
    )
    sg.graph.add_node(
        "level-l1",
        nodeKind="rookbim_level",
        displayName="L1",
        levelName="L1",
        sidecarFingerprint="fp1",
        projectionKind="bim_relationship_v1",
        provenance="rookbim_sidecar",
    )
    sg.graph.add_edge(
        "door",
        "wall",
        key="rookbim:hosted_by:fp1:uid-door:uid-wall",
        relationship="revit_hosted_by",
        provenance="rookbim_sidecar",
        projectionKind="bim_relationship_v1",
        sidecarFingerprint="fp1",
        confidence="high",
        source="revit_api",
    )
    sg.graph.add_edge(
        "door",
        "room-a",
        key="rookbim:in_room:fp1:uid-door:room-1",
        relationship="revit_in_room",
        provenance="rookbim_sidecar",
        projectionKind="bim_relationship_v1",
        sidecarFingerprint="fp1",
        confidence="high",
    )
    sg.graph.add_edge(
        "door",
        "level-l1",
        key="rookbim:on_level:fp1:uid-door:L1",
        relationship="revit_on_level",
        provenance="rookbim_sidecar",
        projectionKind="bim_relationship_v1",
        sidecarFingerprint="fp1",
        confidence="high",
    )
    sg.graph.add_edge(
        "wall",
        "level-l1",
        key="rookbim:on_level:fp1:uid-wall:L1",
        relationship="revit_on_level",
        provenance="rookbim_sidecar",
        projectionKind="bim_relationship_v1",
        sidecarFingerprint="fp1",
        confidence="high",
    )
    return sg
```

---

### Task 1: Pure Module Foundation And Projection Precondition

**Files:**
- Create: `mcp_server/src/rook/scene/bim_facts_query.py`
- Create: `mcp_server/tests/test_bim_facts_query.py`

- [ ] **Step 1: Write failing tests for projection detection, input validation, and source guards**

Add this to `mcp_server/tests/test_bim_facts_query.py` after the shared fixture:

```python
from pathlib import Path

from rook.scene import bim_facts_query as query
from rook.scene.scene_graph import SceneGraphAnalytics


def test_projection_absent_returns_hard_precondition_failure():
    sg = SceneGraphAnalytics()
    sg._sequence = 7
    sg.graph.add_node("plain", name="Plain")

    result = query.query_bim_facts(sg, mode="relationship_scan")

    assert result["success"] is False
    assert result["error"] == "bim_projection_required"
    assert result["bimProjectionPresent"] is False
    assert result["graphSequence"] == 7
    assert result["sidecarFingerprints"] == []
    assert "scene_project_bim_relationships" in result["message"]


def test_unknown_mode_and_detail_are_input_errors():
    sg = _bim_graph()

    bad_mode = query.query_bim_facts(sg, mode="not_a_mode")
    assert bad_mode["success"] is False
    assert bad_mode["error"] == "invalid_bim_query_input"

    bad_detail = query.query_bim_facts(sg, mode="relationship_scan", detail="verbose")
    assert bad_detail["success"] is False
    assert bad_detail["error"] == "invalid_bim_query_input"


def test_query_module_does_not_import_runtime_projection_or_inference_modules():
    source = Path(query.__file__).read_text(encoding="utf-8")

    forbidden = [
        "call_rhino",
        "project_bim_relationships_for_tool",
        "exact_projection",
        "containment_refinement",
        "analytics.sync",
    ]
    for token in forbidden:
        assert token not in source
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_facts_query.py::test_projection_absent_returns_hard_precondition_failure mcp_server/tests/test_bim_facts_query.py::test_unknown_mode_and_detail_are_input_errors mcp_server/tests/test_bim_facts_query.py::test_query_module_does_not_import_runtime_projection_or_inference_modules -q
```

Expected: FAIL because `rook.scene.bim_facts_query` does not exist yet.

- [ ] **Step 3: Create the pure query module foundation**

Create `mcp_server/src/rook/scene/bim_facts_query.py`:

```python
from __future__ import annotations

from typing import Any

PROJECTION_KIND = "bim_relationship_v1"
PROVENANCE = "rookbim_sidecar"
REL_HOSTED_BY = "revit_hosted_by"
REL_IN_ROOM = "revit_in_room"
REL_ON_LEVEL = "revit_on_level"

VALID_MODES = {
    "object_context",
    "room_members",
    "level_members",
    "hosted_elements",
    "relationship_scan",
}
VALID_DETAILS = {"ids", "compact", "full"}

MODE_LIMITS = {
    "object_context": (10, 50),
    "room_members": (100, 500),
    "level_members": (100, 500),
    "hosted_elements": (100, 500),
    "relationship_scan": (20, 100),
}


def _clean_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _projection_edges(graph: Any) -> list[tuple[str, str, Any, dict[str, Any]]]:
    return [
        (source, target, key, dict(attrs))
        for source, target, key, attrs in graph.edges(keys=True, data=True)
        if attrs.get("projectionKind") == PROJECTION_KIND
        and attrs.get("provenance") == PROVENANCE
        and attrs.get("relationship") in {REL_HOSTED_BY, REL_IN_ROOM, REL_ON_LEVEL}
    ]


def _projection_nodes(graph: Any) -> list[tuple[str, dict[str, Any]]]:
    return [
        (node_id, dict(attrs))
        for node_id, attrs in graph.nodes(data=True)
        if attrs.get("projectionKind") == PROJECTION_KIND
        and attrs.get("provenance") == PROVENANCE
    ]


def _sidecar_fingerprints(graph: Any, edges: list[tuple[str, str, Any, dict[str, Any]]]) -> list[str]:
    values: set[str] = set()
    for _, attrs in _projection_nodes(graph):
        fp = _clean_str(attrs.get("sidecarFingerprint") or attrs.get("rookbimSidecarFingerprint"))
        if fp:
            values.add(fp)
    for _, _, _, attrs in edges:
        fp = _clean_str(attrs.get("sidecarFingerprint") or attrs.get("rookbimSidecarFingerprint"))
        if fp:
            values.add(fp)
    for _, attrs in graph.nodes(data=True):
        if attrs.get("rookbimJoined"):
            fp = _clean_str(attrs.get("rookbimSidecarFingerprint") or attrs.get("sidecarFingerprint"))
            if fp:
                values.add(fp)
    return sorted(values)


def _relationship_counts(edges: list[tuple[str, str, Any, dict[str, Any]]]) -> dict[str, int]:
    counts = {REL_HOSTED_BY: 0, REL_IN_ROOM: 0, REL_ON_LEVEL: 0}
    for _, _, _, attrs in edges:
        rel = attrs.get("relationship")
        if rel in counts:
            counts[rel] += 1
    return counts


def _effective_limit(mode: str, limit: int | None = None, sample_limit: int | None = None) -> int:
    default, maximum = MODE_LIMITS[mode]
    raw = sample_limit if mode == "relationship_scan" else limit
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(0, min(value, maximum))


def _invalid(message: str, *, graph_sequence: int, fingerprints: list[str] | None = None) -> dict[str, Any]:
    return {
        "success": False,
        "error": "invalid_bim_query_input",
        "message": message,
        "bimProjectionPresent": bool(fingerprints),
        "graphSequence": graph_sequence,
        "sidecarFingerprints": fingerprints or [],
    }


def _base_success(
    *,
    mode: str,
    graph_sequence: int,
    fingerprints: list[str],
    relationship_counts: dict[str, int],
    effective_limit: int,
    query: dict[str, Any],
    results: list[Any],
    total_count: int = 0,
    truncated: bool = False,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "success": True,
        "mode": mode,
        "bimProjectionPresent": True,
        "graphSequence": graph_sequence,
        "sidecarFingerprints": fingerprints,
        "query": query,
        "summary": {
            "relationshipCounts": relationship_counts,
            "effectiveLimit": effective_limit,
            "totalCount": total_count,
        },
        "results": results,
        "truncated": truncated,
        "diagnostics": diagnostics or {},
    }


def query_bim_facts(
    analytics: Any,
    *,
    mode: str,
    object_ids: list[str] | None = None,
    room_id: str | None = None,
    room_name: str | None = None,
    level_name: str | None = None,
    host_object_id: str | None = None,
    detail: str = "compact",
    limit: int | None = None,
    sample_limit: int | None = None,
) -> dict[str, Any]:
    graph = analytics.graph
    graph_sequence = int(getattr(analytics, "sequence", 0))

    edges = _projection_edges(graph)
    fingerprints = _sidecar_fingerprints(graph, edges)
    relationship_counts = _relationship_counts(edges)

    if mode not in VALID_MODES:
        return _invalid(f"Unknown BIM facts query mode: {mode}", graph_sequence=graph_sequence, fingerprints=fingerprints)
    if detail not in VALID_DETAILS:
        return _invalid(f"Unknown BIM facts detail level: {detail}", graph_sequence=graph_sequence, fingerprints=fingerprints)

    effective_limit = _effective_limit(mode, limit=limit, sample_limit=sample_limit)

    if not edges and not fingerprints:
        return {
            "success": False,
            "error": "bim_projection_required",
            "message": "No BIM relationship projection is present in the scene graph. Run scene_project_bim_relationships first.",
            "bimProjectionPresent": False,
            "graphSequence": graph_sequence,
            "sidecarFingerprints": [],
        }

    if mode == "relationship_scan":
        return _base_success(
            mode=mode,
            graph_sequence=graph_sequence,
            fingerprints=fingerprints,
            relationship_counts=relationship_counts,
            effective_limit=effective_limit,
            query={"detail": detail, "sampleLimit": effective_limit},
            results=[],
            total_count=sum(relationship_counts.values()),
        )

    return _invalid(f"Mode {mode} is not implemented yet.", graph_sequence=graph_sequence, fingerprints=fingerprints)
```

- [ ] **Step 4: Run the tests again**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_facts_query.py::test_projection_absent_returns_hard_precondition_failure mcp_server/tests/test_bim_facts_query.py::test_unknown_mode_and_detail_are_input_errors mcp_server/tests/test_bim_facts_query.py::test_query_module_does_not_import_runtime_projection_or_inference_modules -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add mcp_server/src/rook/scene/bim_facts_query.py mcp_server/tests/test_bim_facts_query.py
git commit -m "feat: add BIM facts query foundation"
```

---

### Task 2: Object Context Mode

**Files:**
- Modify: `mcp_server/src/rook/scene/bim_facts_query.py`
- Modify: `mcp_server/tests/test_bim_facts_query.py`

- [ ] **Step 1: Add failing object-context tests**

Add:

```python
def test_object_context_returns_joined_and_unjoined_results():
    sg = _bim_graph()

    result = query.query_bim_facts(
        sg,
        mode="object_context",
        object_ids=["door", "chair"],
        limit=1,
    )

    assert result["success"] is True
    assert result["summary"]["effectiveLimit"] == 1
    assert result["truncated"] is False
    door = result["results"][0]
    chair = result["results"][1]

    assert door["objectId"] == "door"
    assert door["bimJoined"] is True
    assert door["identity"]["revitUniqueId"] == "uid-door"
    assert door["hostedBy"][0]["objectId"] == "wall"
    assert door["rooms"][0]["displayName"] == "101 Office"
    assert door["levels"][0]["displayName"] == "L1"
    assert door["hostedElements"]["totalCount"] == 0
    assert door["sameRoomCount"] == 1
    assert door["sameLevelCount"] == 2

    assert chair == {"objectId": "chair", "bimJoined": False}


def test_object_context_missing_object_ids_is_input_error():
    result = query.query_bim_facts(_bim_graph(), mode="object_context")

    assert result["success"] is False
    assert result["error"] == "invalid_bim_query_input"


def test_object_context_child_truncation_sets_top_level_truncated():
    sg = _bim_graph()
    for i in range(3):
        oid = f"door-{i}"
        sg.graph.add_node(oid, name=f"Door {i}", rookbimJoined=True, revitUniqueId=f"uid-door-{i}")
        sg.graph.add_edge(
            oid,
            "wall",
            key=f"rookbim:hosted_by:fp1:uid-door-{i}:uid-wall",
            relationship="revit_hosted_by",
            provenance="rookbim_sidecar",
            projectionKind="bim_relationship_v1",
            sidecarFingerprint="fp1",
        )

    result = query.query_bim_facts(sg, mode="object_context", object_ids=["wall"], limit=2)

    wall = result["results"][0]
    assert wall["hostedElements"]["totalCount"] == 4
    assert wall["hostedElements"]["effectiveLimit"] == 2
    assert wall["hostedElements"]["truncated"] is True
    assert result["truncated"] is True
```

- [ ] **Step 2: Run failing object-context tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_facts_query.py::test_object_context_returns_joined_and_unjoined_results mcp_server/tests/test_bim_facts_query.py::test_object_context_missing_object_ids_is_input_error mcp_server/tests/test_bim_facts_query.py::test_object_context_child_truncation_sets_top_level_truncated -q
```

Expected: FAIL because `object_context` still returns the not-implemented input error.

- [ ] **Step 3: Implement object-context helpers**

Add helpers above `query_bim_facts`:

```python
GEOMETRY_ATTR_PREFIXES = ("bbox_",)
GEOMETRY_ATTRS = {
    "max_dim", "mid_dim", "min_dim", "elongation", "flatness", "thinness",
    "volume", "centroid_z", "base_z", "top_z", "primary_axis", "thin_axis",
}


def _display_name(graph: Any, node_id: str) -> str:
    attrs = graph.nodes.get(node_id, {})
    return _clean_str(attrs.get("displayName") or attrs.get("name") or node_id)


def _compact_object(graph: Any, node_id: str, edge_attrs: dict[str, Any] | None = None, *, detail: str = "compact") -> Any:
    if detail == "ids":
        return node_id
    attrs = dict(graph.nodes.get(node_id, {}))
    payload: dict[str, Any] = {
        "objectId": node_id,
        "displayName": _display_name(graph, node_id),
        "name": attrs.get("name", ""),
        "category": attrs.get("revitCategory") or attrs.get("domain_label") or attrs.get("shape_class") or "",
        "family": attrs.get("revitFamily", ""),
        "type": attrs.get("revitType", ""),
        "revitUniqueId": attrs.get("revitUniqueId", ""),
        "revitElementId": attrs.get("revitElementId", ""),
        "layer": attrs.get("layer", ""),
    }
    if edge_attrs:
        payload["edge"] = {
            key: edge_attrs[key]
            for key in ("relationship", "confidence", "source", "sidecarFingerprint", "provenance")
            if key in edge_attrs
        }
    if detail == "full":
        payload["nodeAttrs"] = {
            key: value
            for key, value in attrs.items()
            if key not in GEOMETRY_ATTRS
            and not any(key.startswith(prefix) for prefix in GEOMETRY_ATTR_PREFIXES)
        }
        if edge_attrs:
            payload["edgeAttrs"] = dict(edge_attrs)
    return payload


def _target_facts(graph: Any, node_id: str, relationship: str, *, detail: str) -> list[Any]:
    facts = []
    for _, target, attrs in graph.out_edges(node_id, data=True):
        if attrs.get("relationship") == relationship:
            facts.append(_compact_object(graph, target, attrs, detail=detail))
    return facts


def _incoming_hosted(graph: Any, node_id: str, *, detail: str, effective_limit: int) -> dict[str, Any]:
    rows = []
    for source, _, attrs in graph.in_edges(node_id, data=True):
        if attrs.get("relationship") == REL_HOSTED_BY:
            rows.append(_compact_object(graph, source, attrs, detail=detail))
    total = len(rows)
    return {
        "results": rows[:effective_limit],
        "totalCount": total,
        "effectiveLimit": effective_limit,
        "truncated": total > effective_limit,
    }


def _same_target_peer_count(graph: Any, node_id: str, relationship: str) -> int:
    targets = {
        target
        for _, target, attrs in graph.out_edges(node_id, data=True)
        if attrs.get("relationship") == relationship
    }
    if not targets:
        return 0
    peers = set()
    for target in targets:
        for source, _, attrs in graph.in_edges(target, data=True):
            if attrs.get("relationship") == relationship:
                peers.add(source)
    return len(peers)


def _object_context(
    graph: Any,
    *,
    object_ids: list[str] | None,
    detail: str,
    effective_limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    if not object_ids:
        raise ValueError("object_context requires non-empty object_ids.")
    results: list[dict[str, Any]] = []
    any_truncated = False
    for object_id in object_ids:
        attrs = graph.nodes.get(object_id)
        if not attrs or not attrs.get("rookbimJoined"):
            results.append({"objectId": object_id, "bimJoined": False})
            continue
        hosted = _incoming_hosted(graph, object_id, detail=detail, effective_limit=effective_limit)
        any_truncated = any_truncated or hosted["truncated"]
        results.append({
            "objectId": object_id,
            "bimJoined": True,
            "identity": {
                "revitUniqueId": attrs.get("revitUniqueId", ""),
                "revitElementId": attrs.get("revitElementId", ""),
                "revitCategory": attrs.get("revitCategory", ""),
                "revitFamily": attrs.get("revitFamily", ""),
                "revitType": attrs.get("revitType", ""),
                "revitName": attrs.get("revitName", ""),
                "revitLevel": attrs.get("revitLevel", ""),
            },
            "hostedBy": _target_facts(graph, object_id, REL_HOSTED_BY, detail=detail),
            "rooms": _target_facts(graph, object_id, REL_IN_ROOM, detail=detail),
            "levels": _target_facts(graph, object_id, REL_ON_LEVEL, detail=detail),
            "hostedElements": hosted,
            "sameRoomCount": _same_target_peer_count(graph, object_id, REL_IN_ROOM),
            "sameLevelCount": _same_target_peer_count(graph, object_id, REL_ON_LEVEL),
        })
    return results, any_truncated
```

Then add this branch inside `query_bim_facts` before the not-implemented fallback:

```python
    if mode == "object_context":
        try:
            results, truncated = _object_context(
                graph,
                object_ids=object_ids,
                detail=detail,
                effective_limit=effective_limit,
            )
        except ValueError as exc:
            return _invalid(str(exc), graph_sequence=graph_sequence, fingerprints=fingerprints)
        return _base_success(
            mode=mode,
            graph_sequence=graph_sequence,
            fingerprints=fingerprints,
            relationship_counts=relationship_counts,
            effective_limit=effective_limit,
            query={"objectIds": object_ids or [], "detail": detail},
            results=results,
            total_count=len(results),
            truncated=truncated,
        )
```

- [ ] **Step 4: Run object-context tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_facts_query.py::test_object_context_returns_joined_and_unjoined_results mcp_server/tests/test_bim_facts_query.py::test_object_context_missing_object_ids_is_input_error mcp_server/tests/test_bim_facts_query.py::test_object_context_child_truncation_sets_top_level_truncated -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```powershell
git add mcp_server/src/rook/scene/bim_facts_query.py mcp_server/tests/test_bim_facts_query.py
git commit -m "feat: query BIM object context"
```

---

### Task 3: Room, Level, Hosted, And Scan Modes

**Files:**
- Modify: `mcp_server/src/rook/scene/bim_facts_query.py`
- Modify: `mcp_server/tests/test_bim_facts_query.py`

- [ ] **Step 1: Add failing member-mode tests**

Add:

```python
def test_room_members_matches_conjunctive_room_id_and_name():
    sg = _bim_graph()

    result = query.query_bim_facts(
        sg,
        mode="room_members",
        room_id="101",
        room_name="Office",
        detail="compact",
    )

    assert result["success"] is True
    assert result["summary"]["totalCount"] == 1
    assert result["results"][0]["objectId"] == "door"


def test_room_members_rejects_missing_selector_and_ambiguous_selector():
    sg = _bim_graph()
    missing = query.query_bim_facts(sg, mode="room_members")
    assert missing["success"] is False
    assert missing["error"] == "invalid_bim_query_input"

    sg.graph.add_node(
        "room-b",
        nodeKind="rookbim_room",
        displayName="101 Office",
        roomUniqueId="room-2",
        roomNumber="101",
        roomName="Office",
        sidecarFingerprint="fp1",
        projectionKind="bim_relationship_v1",
        provenance="rookbim_sidecar",
    )
    ambiguous = query.query_bim_facts(sg, mode="room_members", room_name="101 Office")
    assert ambiguous["success"] is False
    assert ambiguous["error"] == "ambiguous_bim_reference"
    assert len(ambiguous["candidates"]) == 2


def test_level_members_and_hosted_elements_return_capped_results():
    sg = _bim_graph()

    level = query.query_bim_facts(sg, mode="level_members", level_name="L1", limit=1)
    assert level["success"] is True
    assert level["summary"]["totalCount"] == 2
    assert level["summary"]["effectiveLimit"] == 1
    assert level["truncated"] is True
    assert len(level["results"]) == 1

    hosted = query.query_bim_facts(sg, mode="hosted_elements", host_object_id="wall")
    assert hosted["success"] is True
    assert hosted["summary"]["totalCount"] == 1
    assert hosted["results"][0]["objectId"] == "door"


def test_member_modes_projected_but_no_match_returns_empty_success():
    sg = _bim_graph()

    result = query.query_bim_facts(sg, mode="level_members", level_name="L9")

    assert result["success"] is True
    assert result["bimProjectionPresent"] is True
    assert result["results"] == []
    assert result["summary"]["totalCount"] == 0


def test_relationship_scan_returns_bounded_samples_and_counts():
    sg = _bim_graph()

    result = query.query_bim_facts(sg, mode="relationship_scan", sample_limit=2)

    assert result["success"] is True
    assert result["summary"]["relationshipCounts"]["revit_hosted_by"] == 1
    assert result["summary"]["totalCount"] == 4
    assert result["summary"]["effectiveLimit"] == 2
    assert result["truncated"] is True
    assert len(result["results"]) == 2
    sample = result["results"][0]
    assert set(sample) >= {"relationship", "source", "target", "sidecarFingerprint"}
```

- [ ] **Step 2: Run failing member-mode tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_facts_query.py::test_room_members_matches_conjunctive_room_id_and_name mcp_server/tests/test_bim_facts_query.py::test_room_members_rejects_missing_selector_and_ambiguous_selector mcp_server/tests/test_bim_facts_query.py::test_level_members_and_hosted_elements_return_capped_results mcp_server/tests/test_bim_facts_query.py::test_member_modes_projected_but_no_match_returns_empty_success mcp_server/tests/test_bim_facts_query.py::test_relationship_scan_returns_bounded_samples_and_counts -q
```

Expected: FAIL because these modes are not implemented yet.

- [ ] **Step 3: Implement selector and member helpers**

Add helpers:

```python
def _matches(value: Any, needle: str) -> bool:
    return _clean_str(value).casefold() == needle.strip().casefold()


def _node_candidate(graph: Any, node_id: str, attrs: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    return {
        "nodeId": node_id,
        "displayName": _display_name(graph, node_id),
        **{field: attrs.get(field, "") for field in fields},
    }


def _find_room_nodes(graph: Any, *, room_id: str | None, room_name: str | None) -> tuple[list[str], list[dict[str, Any]]]:
    if not room_id and not room_name:
        raise ValueError("room_members requires room_id or room_name.")
    matches: list[tuple[str, dict[str, Any]]] = []
    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("nodeKind") != "rookbim_room":
            continue
        id_values = [node_id, attrs.get("roomUniqueId"), attrs.get("roomNumber"), attrs.get("roomName"), attrs.get("displayName")]
        name_values = [attrs.get("roomName"), attrs.get("displayName"), attrs.get("roomNumber")]
        id_ok = True if not room_id else any(_matches(value, room_id) for value in id_values)
        name_ok = True if not room_name else any(_matches(value, room_name) for value in name_values)
        if id_ok and name_ok:
            matches.append((node_id, dict(attrs)))
    return [node_id for node_id, _ in matches], [
        _node_candidate(graph, node_id, attrs, ["roomUniqueId", "roomNumber", "roomName"])
        for node_id, attrs in matches
    ]


def _find_level_nodes(graph: Any, *, level_name: str | None) -> tuple[list[str], list[dict[str, Any]]]:
    if not level_name:
        raise ValueError("level_members requires level_name.")
    matches: list[tuple[str, dict[str, Any]]] = []
    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("nodeKind") != "rookbim_level":
            continue
        values = [node_id, attrs.get("levelName"), attrs.get("displayName")]
        if any(_matches(value, level_name) for value in values):
            matches.append((node_id, dict(attrs)))
    return [node_id for node_id, _ in matches], [
        _node_candidate(graph, node_id, attrs, ["levelName"])
        for node_id, attrs in matches
    ]


def _incoming_members(graph: Any, target_node: str, relationship: str, *, detail: str, effective_limit: int) -> tuple[list[Any], int, bool]:
    rows = [
        _compact_object(graph, source, attrs, detail=detail)
        for source, _, attrs in graph.in_edges(target_node, data=True)
        if attrs.get("relationship") == relationship
    ]
    total = len(rows)
    return rows[:effective_limit], total, total > effective_limit


def _relationship_samples(
    graph: Any,
    edges: list[tuple[str, str, Any, dict[str, Any]]],
    *,
    effective_limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    rows = [
        {
            "relationship": attrs.get("relationship", ""),
            "source": {"objectId": source, "displayName": _display_name(graph, source)},
            "target": {"objectId": target, "displayName": _display_name(graph, target)},
            "sidecarFingerprint": attrs.get("sidecarFingerprint", ""),
        }
        for source, target, _, attrs in edges
    ]
    return rows[:effective_limit], len(rows) > effective_limit
```

Then replace the existing `relationship_scan` branch and add member branches:

```python
    if mode == "relationship_scan":
        samples, truncated = _relationship_samples(graph, edges, effective_limit=effective_limit)
        return _base_success(
            mode=mode,
            graph_sequence=graph_sequence,
            fingerprints=fingerprints,
            relationship_counts=relationship_counts,
            effective_limit=effective_limit,
            query={"detail": detail, "sampleLimit": effective_limit},
            results=samples,
            total_count=sum(relationship_counts.values()),
            truncated=truncated,
        )

    if mode == "room_members":
        try:
            node_ids, candidates = _find_room_nodes(graph, room_id=room_id, room_name=room_name)
        except ValueError as exc:
            return _invalid(str(exc), graph_sequence=graph_sequence, fingerprints=fingerprints)
        if len(node_ids) > 1:
            return {"success": False, "error": "ambiguous_bim_reference", "message": "Room selector matched multiple BIM room nodes.", "candidates": candidates, "bimProjectionPresent": True, "graphSequence": graph_sequence, "sidecarFingerprints": fingerprints}
        if not node_ids:
            return _base_success(mode=mode, graph_sequence=graph_sequence, fingerprints=fingerprints, relationship_counts=relationship_counts, effective_limit=effective_limit, query={"roomId": room_id, "roomName": room_name, "detail": detail}, results=[], total_count=0)
        rows, total, truncated = _incoming_members(graph, node_ids[0], REL_IN_ROOM, detail=detail, effective_limit=effective_limit)
        return _base_success(mode=mode, graph_sequence=graph_sequence, fingerprints=fingerprints, relationship_counts=relationship_counts, effective_limit=effective_limit, query={"roomId": room_id, "roomName": room_name, "detail": detail}, results=rows, total_count=total, truncated=truncated)

    if mode == "level_members":
        try:
            node_ids, candidates = _find_level_nodes(graph, level_name=level_name)
        except ValueError as exc:
            return _invalid(str(exc), graph_sequence=graph_sequence, fingerprints=fingerprints)
        if len(node_ids) > 1:
            return {"success": False, "error": "ambiguous_bim_reference", "message": "Level selector matched multiple BIM level nodes.", "candidates": candidates, "bimProjectionPresent": True, "graphSequence": graph_sequence, "sidecarFingerprints": fingerprints}
        if not node_ids:
            return _base_success(mode=mode, graph_sequence=graph_sequence, fingerprints=fingerprints, relationship_counts=relationship_counts, effective_limit=effective_limit, query={"levelName": level_name, "detail": detail}, results=[], total_count=0)
        rows, total, truncated = _incoming_members(graph, node_ids[0], REL_ON_LEVEL, detail=detail, effective_limit=effective_limit)
        return _base_success(mode=mode, graph_sequence=graph_sequence, fingerprints=fingerprints, relationship_counts=relationship_counts, effective_limit=effective_limit, query={"levelName": level_name, "detail": detail}, results=rows, total_count=total, truncated=truncated)

    if mode == "hosted_elements":
        if not host_object_id:
            return _invalid("hosted_elements requires host_object_id.", graph_sequence=graph_sequence, fingerprints=fingerprints)
        rows, total, truncated = _incoming_members(graph, host_object_id, REL_HOSTED_BY, detail=detail, effective_limit=effective_limit)
        return _base_success(mode=mode, graph_sequence=graph_sequence, fingerprints=fingerprints, relationship_counts=relationship_counts, effective_limit=effective_limit, query={"hostObjectId": host_object_id, "detail": detail}, results=rows, total_count=total, truncated=truncated)
```

- [ ] **Step 4: Run member-mode tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_facts_query.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```powershell
git add mcp_server/src/rook/scene/bim_facts_query.py mcp_server/tests/test_bim_facts_query.py
git commit -m "feat: query BIM rooms levels and hosts"
```

---

### Task 4: scene_context(sync=false) And BIM Block Formatting

**Files:**
- Modify: `mcp_server/src/rook/scene/scene_graph.py`
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/tests/test_scene_graph.py`
- Modify: `mcp_server/tests/test_bim_relationship_projection_tool.py`

- [ ] **Step 1: Add failing context formatter tests**

Add to `TestNLContext` in `mcp_server/tests/test_scene_graph.py`:

```python
    def test_context_renders_compact_bim_block_with_correct_edge_directions(self):
        sg = SceneGraphAnalytics()
        sg.graph.add_node(
            "wall",
            name="Wall-01",
            domain_label="wall",
            shape_class="vertical-planar",
            rookbimJoined=True,
            revitElementId="100",
            revitUniqueId="uid-wall",
            revitCategory="Walls",
            revitFamily="Basic Wall",
            revitType="Generic 200mm",
        )
        sg.graph.add_node(
            "door",
            name="Door-01",
            domain_label="door",
            shape_class="compact",
            rookbimJoined=True,
            revitElementId="200",
            revitUniqueId="uid-door",
            revitCategory="Doors",
            revitFamily="Single-Flush",
            revitType="0915 x 2134mm",
        )
        sg.graph.add_node("room", displayName="101 Office", domain_label="room", nodeKind="rookbim_room")
        sg.graph.add_node("level", displayName="L1", domain_label="level", nodeKind="rookbim_level")
        sg.graph.add_edge("door", "wall", relationship="revit_hosted_by")
        sg.graph.add_edge("door", "room", relationship="revit_in_room")
        sg.graph.add_edge("door", "level", relationship="revit_on_level")

        text = sg.get_context(["door", "wall"])

        assert "BIM: Doors | Single-Flush | 0915 x 2134mm" in text
        assert "Revit: element 200, uniqueId uid-door" in text
        assert "Room: 101 Office" in text
        assert "Level: L1" in text
        assert "Hosted by: Wall-01" in text
        assert "Hosts: 1 elements" in text

    def test_context_caps_multiple_bim_rooms_and_levels(self):
        sg = SceneGraphAnalytics()
        sg.graph.add_node("obj", name="Obj", rookbimJoined=True, revitCategory="Furniture")
        for i in range(5):
            sg.graph.add_node(f"room-{i}", displayName=f"{100 + i} Room", nodeKind="rookbim_room")
            sg.graph.add_node(f"level-{i}", displayName=f"L{i}", nodeKind="rookbim_level")
            sg.graph.add_edge("obj", f"room-{i}", relationship="revit_in_room")
            sg.graph.add_edge("obj", f"level-{i}", relationship="revit_on_level")

        text = sg.get_context(["obj"])

        assert "Room: 100 Room, 101 Room, 102 Room, +2 more" in text
        assert "Level: L0, L1, L2, +2 more" in text
```

- [ ] **Step 2: Add failing server dispatch test for `sync=false`**

Add to `mcp_server/tests/test_bim_relationship_projection_tool.py`:

```python
@pytest.mark.asyncio
async def test_scene_context_sync_false_skips_sync_and_reads_current_mirror(monkeypatch):
    sg = _scene_graph()
    sg.graph.nodes["rh-door"]["rookbimJoined"] = True
    sg.graph.nodes["rh-door"]["revitCategory"] = "Doors"
    called = {"sync": 0}

    async def fake_sync(port=None):
        called["sync"] += 1
        return {"synced": True}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)

    from rook.server import _mcp_tool_executor

    result = await _mcp_tool_executor("scene_context", {"object_ids": ["rh-door"], "sync": False})

    assert result["success"] is True
    assert called["sync"] == 0
    assert "BIM:" in result["data"]
```

- [ ] **Step 3: Run failing context tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_scene_graph.py::TestNLContext::test_context_renders_compact_bim_block_with_correct_edge_directions mcp_server/tests/test_scene_graph.py::TestNLContext::test_context_caps_multiple_bim_rooms_and_levels mcp_server/tests/test_bim_relationship_projection_tool.py::test_scene_context_sync_false_skips_sync_and_reads_current_mirror -q
```

Expected: FAIL because no BIM block exists and `scene_context` always syncs.

- [ ] **Step 4: Implement BIM block helpers in `scene_graph.py`**

Add helper methods to `SceneGraphAnalytics` before graph algorithms:

```python
    def _format_bim_block(self, node_id: str, attrs: dict[str, Any]) -> list[str]:
        if not attrs.get("rookbimJoined"):
            return []
        category = attrs.get("revitCategory", "")
        family = attrs.get("revitFamily", "")
        type_name = attrs.get("revitType", "")
        title_parts = [part for part in (category, family, type_name) if part]
        lines = [f"  BIM: {' | '.join(title_parts) if title_parts else 'joined'}"]

        element_id = attrs.get("revitElementId", "")
        unique_id = attrs.get("revitUniqueId", "")
        if element_id or unique_id:
            lines.append(f"    Revit: element {element_id}, uniqueId {unique_id}".rstrip())

        rooms = self._bim_targets(node_id, "revit_in_room")
        levels = self._bim_targets(node_id, "revit_on_level")
        hosted_by = self._bim_targets(node_id, "revit_hosted_by")
        host_count = sum(
            1 for _, _, edata in self.graph.in_edges(node_id, data=True)
            if edata.get("relationship") == "revit_hosted_by"
        )

        if rooms:
            lines.append(f"    Room: {self._format_limited_names(rooms)}")
        if levels:
            lines.append(f"    Level: {self._format_limited_names(levels)}")
        if hosted_by:
            lines.append(f"    Hosted by: {self._format_limited_names(hosted_by)}")
        if host_count:
            suffix = "element" if host_count == 1 else "elements"
            lines.append(f"    Hosts: {host_count} {suffix}")
        return lines

    def _bim_targets(self, node_id: str, relationship: str) -> list[str]:
        names = []
        for _, target, edata in self.graph.out_edges(node_id, data=True):
            if edata.get("relationship") != relationship:
                continue
            t_attrs = self.graph.nodes.get(target, {})
            names.append(t_attrs.get("displayName") or t_attrs.get("name") or target[:8])
        return names

    @staticmethod
    def _format_limited_names(names: list[str], limit: int = 3) -> str:
        shown = names[:limit]
        suffix = f", +{len(names) - limit} more" if len(names) > limit else ""
        return ", ".join(shown) + suffix
```

Then in `_format_node`, after created-by lines and before outgoing edges, add:

```python
        lines.extend(self._format_bim_block(node_id, attrs))
```

- [ ] **Step 5: Implement `scene_context(sync=false)` in server dispatch**

In the `scene_context` tool schema in `server.py`, add:

```python
                    "sync": {
                        "type": "boolean",
                        "description": "Whether to sync from Rhino before rendering context. Default true. Use false after scene_project_bim_relationships to preserve Python-only BIM projection facts."
                    },
```

In the `case "scene_context"` executor, replace unconditional sync:

```python
                if arguments.get("sync", True):
                    await sg.sync(port=port)
```

- [ ] **Step 6: Verify local dispatcher coverage for `scene_context(sync=false)`**

Inspect `mcp_server/src/rook/agent/tool_dispatcher.py` for a local `scene_context` function:

- Current expected state: there is no local `scene_context` implementation in `build_local_tools`; agent callers reach `scene_context` through the MCP/bridge path.
- If that remains true, do not add a new local `scene_context` function in this slice. Keep Task 4 scoped to the MCP `call_tool` path.
- If the file has changed and a local `scene_context` implementation now exists, add `sync=True` to its signature and conditionally call sync using this exact shape:

```python
        async def _scene_context(object_ids=None, sync=True, port: int | None = None, **kwargs) -> dict:
            if not object_ids:
                return {"success": False, "data": "Missing object_ids parameter"}
            sg = get_scene_graph()
            if sync:
                await sg.sync(port=port)
            return {"success": True, "data": sg.get_context(object_ids)}
```

- [ ] **Step 7: Run context tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_scene_graph.py::TestNLContext mcp_server/tests/test_bim_relationship_projection_tool.py::test_scene_context_sync_false_skips_sync_and_reads_current_mirror -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

```powershell
git add mcp_server/src/rook/scene/scene_graph.py mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/tests/test_scene_graph.py mcp_server/tests/test_bim_relationship_projection_tool.py
git commit -m "feat: render BIM context without sync"
```

---

### Task 5: MCP Tool Registration, Local Dispatcher, Tool Groups, And Targeting

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Modify: `mcp_server/tests/test_bim_relationship_projection_tool.py`

- [ ] **Step 1: Add failing registration and dispatch tests**

Add to `mcp_server/tests/test_bim_relationship_projection_tool.py`:

```python
def test_tool_group_contains_scene_bim_facts():
    from rook.agent.tool_groups import TOOL_GROUPS

    assert "scene_bim_facts" in TOOL_GROUPS["scene_graph"]


def test_scene_bim_facts_targeting_policy_is_rhino_read():
    from rook import targeting

    pol = targeting.policy_for_tool("scene_bim_facts")

    assert pol.requires_rhino is True
    assert pol.risk == "read"
    assert "scene_bim_facts" in targeting._ALL_KNOWN_TOOLS


@pytest.mark.asyncio
async def test_server_tool_schema_exposes_scene_bim_facts_parameters():
    from rook.server import list_tools

    tools = {tool.name: tool for tool in await list_tools()}
    schema = tools["scene_bim_facts"].inputSchema

    assert set(schema["properties"]) >= {
        "mode",
        "object_ids",
        "room_id",
        "room_name",
        "level_name",
        "host_object_id",
        "detail",
        "limit",
        "sample_limit",
    }
    assert schema["required"] == ["mode"]


def test_local_dispatcher_registers_scene_bim_facts():
    from rook.agent.tool_dispatcher import build_local_tools

    tools = build_local_tools()

    assert "scene_bim_facts" in tools
    assert callable(tools["scene_bim_facts"])


@pytest.mark.asyncio
async def test_local_scene_bim_facts_dispatch_uses_current_mirror_without_sync(monkeypatch):
    sg = _scene_graph()
    called = {"sync": 0}

    async def fake_sync(port=None):
        called["sync"] += 1
        return {"synced": True}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)

    from rook.agent.tool_dispatcher import build_local_tools

    tools = build_local_tools()
    result = await tools["scene_bim_facts"](mode="relationship_scan")

    assert result["success"] is False
    assert result["error"] == "bim_projection_required"
    assert called["sync"] == 0


@pytest.mark.asyncio
async def test_server_scene_bim_facts_dispatch_does_not_sync(monkeypatch):
    sg = _scene_graph()
    called = {"sync": 0}

    async def fake_sync(port=None):
        called["sync"] += 1
        return {"synced": True}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)

    from rook.server import _mcp_tool_executor

    result = await _mcp_tool_executor("scene_bim_facts", {"mode": "relationship_scan"})

    assert result["success"] is False
    assert result["data"]["error"] == "bim_projection_required"
    assert called["sync"] == 0
```

- [ ] **Step 2: Run failing registration tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_relationship_projection_tool.py::test_tool_group_contains_scene_bim_facts mcp_server/tests/test_bim_relationship_projection_tool.py::test_scene_bim_facts_targeting_policy_is_rhino_read mcp_server/tests/test_bim_relationship_projection_tool.py::test_server_tool_schema_exposes_scene_bim_facts_parameters mcp_server/tests/test_bim_relationship_projection_tool.py::test_local_dispatcher_registers_scene_bim_facts mcp_server/tests/test_bim_relationship_projection_tool.py::test_local_scene_bim_facts_dispatch_uses_current_mirror_without_sync mcp_server/tests/test_bim_relationship_projection_tool.py::test_server_scene_bim_facts_dispatch_does_not_sync -q
```

Expected: FAIL because the tool is not registered yet.

- [ ] **Step 3: Add MCP tool schema**

In `server.py` near other scene tools, add:

```python
        Tool(
            name="scene_bim_facts",
            description="""Query already-projected RookBIM facts from the current in-memory Python scene graph mirror.

Reads only the current projected scene graph. Does not sync Rhino. Does not call Rhino/Revit routes. Run scene_project_bim_relationships first.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["object_context", "room_members", "level_members", "hosted_elements", "relationship_scan"],
                        "description": "BIM facts query mode",
                    },
                    "object_ids": {"type": "array", "items": {"type": "string"}},
                    "room_id": {"type": "string"},
                    "room_name": {"type": "string"},
                    "level_name": {"type": "string"},
                    "host_object_id": {"type": "string"},
                    "detail": {"type": "string", "enum": ["ids", "compact", "full"], "description": "Result detail level. Default compact."},
                    "limit": {"type": "integer", "description": "Result limit, clamped by mode."},
                    "sample_limit": {"type": "integer", "description": "Relationship scan sample limit, clamped by mode."},
                },
                "required": ["mode"],
            },
        ),
```

- [ ] **Step 4: Add MCP executor case**

In `_mcp_tool_executor`, add near scene tool cases:

```python
        case "scene_bim_facts":
            from .scene.scene_graph import get_scene_graph
            from .scene.bim_facts_query import query_bim_facts

            sg = get_scene_graph()
            payload = query_bim_facts(
                sg,
                mode=arguments.get("mode", ""),
                object_ids=arguments.get("object_ids"),
                room_id=arguments.get("room_id"),
                room_name=arguments.get("room_name"),
                level_name=arguments.get("level_name"),
                host_object_id=arguments.get("host_object_id"),
                detail=arguments.get("detail", "compact"),
                limit=arguments.get("limit"),
                sample_limit=arguments.get("sample_limit"),
            )
            if payload.get("success") is False:
                result = {"success": False, "data": payload}
            else:
                result = {"success": True, "data": payload}
```

- [ ] **Step 5: Add local dispatcher registration**

In `tool_dispatcher.py`, near `scene_project_bim_relationships`, add:

```python
    # --- scene_bim_facts (Python-side BIM facts query) ---
    try:
        from ..scene.scene_graph import get_scene_graph
        from ..scene.bim_facts_query import query_bim_facts

        async def _scene_bim_facts(
            mode=None,
            object_ids=None,
            room_id=None,
            room_name=None,
            level_name=None,
            host_object_id=None,
            detail="compact",
            limit=None,
            sample_limit=None,
            **kwargs,
        ) -> dict:
            payload = query_bim_facts(
                get_scene_graph(),
                mode=mode or "",
                object_ids=object_ids,
                room_id=room_id,
                room_name=room_name,
                level_name=level_name,
                host_object_id=host_object_id,
                detail=detail,
                limit=limit,
                sample_limit=sample_limit,
            )
            return payload

        tools["scene_bim_facts"] = _scene_bim_facts
    except ImportError:
        logger.debug("scene_bim_facts local tool unavailable (import failed)")
```

- [ ] **Step 6: Add tool groups and targeting**

In `tool_groups.py`, add `"scene_bim_facts"` to `TOOL_GROUPS["scene_graph"]`.

In `targeting.py`, add `"scene_bim_facts"` to:

```python
_ALL_KNOWN_TOOLS
_RHINO_READ_TOOLS
```

- [ ] **Step 7: Run registration tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_relationship_projection_tool.py::test_tool_group_contains_scene_bim_facts mcp_server/tests/test_bim_relationship_projection_tool.py::test_scene_bim_facts_targeting_policy_is_rhino_read mcp_server/tests/test_bim_relationship_projection_tool.py::test_server_tool_schema_exposes_scene_bim_facts_parameters mcp_server/tests/test_bim_relationship_projection_tool.py::test_local_dispatcher_registers_scene_bim_facts mcp_server/tests/test_bim_relationship_projection_tool.py::test_local_scene_bim_facts_dispatch_uses_current_mirror_without_sync mcp_server/tests/test_bim_relationship_projection_tool.py::test_server_scene_bim_facts_dispatch_does_not_sync -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 5**

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/targeting.py mcp_server/tests/test_bim_relationship_projection_tool.py
git commit -m "feat: register BIM facts query tool"
```

---

### Task 6: Final Verification And Cleanup

**Files:**
- Modify only if verification reveals a scoped issue:
  - `mcp_server/src/rook/scene/bim_facts_query.py`
  - `mcp_server/src/rook/scene/scene_graph.py`
  - `mcp_server/src/rook/server.py`
  - `mcp_server/src/rook/agent/tool_dispatcher.py`
  - `mcp_server/src/rook/agent/tool_groups.py`
  - `mcp_server/src/rook/targeting.py`
  - related tests

- [ ] **Step 1: Run focused BIM/query/context tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_facts_query.py mcp_server/tests/test_bim_relationship_projection_tool.py mcp_server/tests/test_scene_graph.py -q
```

Expected: PASS.

- [ ] **Step 2: Run adjacent spatial regression tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_relationship_projection.py mcp_server/tests/test_exact_projection.py mcp_server/tests/test_containment_refinement.py -q
```

Expected: PASS.

- [ ] **Step 3: Run registration/bridge regression tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_rookbim_mcp_tools.py mcp_server/tests/test_rookbim_export_preset_tool.py mcp_server/tests/test_bridge.py -q
```

Expected: PASS.

- [ ] **Step 4: Check diff hygiene**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected:

- `git diff --check` prints no errors.
- Status shows only intended files modified since the task commits.

- [ ] **Step 5: Optional local smoke with projected fixture**

If a live projected graph is available in the same Python process, manually exercise:

```python
from rook.scene.scene_graph import get_scene_graph
from rook.scene.bim_facts_query import query_bim_facts

sg = get_scene_graph()
query_bim_facts(sg, mode="relationship_scan")
```

Expected after `scene_project_bim_relationships`: `success=True`, nonzero `relationshipCounts`, and bounded samples. Expected before projection: `success=False`, `error="bim_projection_required"`.

- [ ] **Step 6: Commit any final scoped fixes**

Only commit if Step 1-4 required corrections:

```powershell
git add <fixed-files>
git commit -m "test: verify BIM facts query context"
```

---

## Self-Review Checklist

- The plan creates a pure query module before any MCP wiring.
- `scene_bim_facts` never syncs and never calls Rhino/Revit/projection/inference code.
- Absence of BIM projection is a hard precondition failure.
- Unknown mode/detail and missing required inputs are explicit input errors.
- `room_members`, `level_members`, `hosted_elements`, `object_context`, and `relationship_scan` are all covered.
- Room selectors use conjunctive matching when both `room_id` and `room_name` are supplied.
- `hosted_elements` uses incoming edges to the host, expressed as source objects with outgoing `revit_hosted_by` targets.
- Limits are clamped by mode and report `effectiveLimit`.
- Multi-object `object_context` truncation is per object and rolls up to top-level `truncated`.
- `full` detail excludes raw sidecar and large geometry fields.
- `scene_context(sync=false)` is explicit; default remains `sync=true`.
- MCP and local dispatcher paths are both covered where applicable.
- Tool group and targeting tests cover the new tool.
- No C++, C#, Revit, Rhino mutation, calibration, threshold tuning, or sidecar parsing is added.
