# Relationship Geometry Evidence v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `scene_relationship_evidence` tool that measures feature-marker-position distance for already-projected `relationship_fact_v1` edges.

**Architecture:** Put evidence filtering, validation, position parsing, distance measurement, hydration orchestration, and response shaping in one focused scene module: `mcp_server/src/rook/scene/relationship_geometry_evidence.py`. Keep `server.py`, `agent/tool_dispatcher.py`, `agent/tool_groups.py`, and `targeting.py` as thin registration surfaces. V1 reads only feature marker user text (`rook.graph.true_position_m`) for `fromFeatureObjectId` / `toFeatureObjectId`; it does not sync, project, infer, mutate Rhino, inspect owner geometry, or change fact truth.

**Tech Stack:** Python 3, pytest, pytest-asyncio, NetworkX-backed `SceneGraphAnalytics`, existing Rhino bridge `call_rhino("/usertext/object-get", "POST", {"id": ...})`, MCP `Tool` schemas in `mcp_server/src/rook/server.py`.

---

## File Structure

Create:

- `mcp_server/src/rook/scene/relationship_geometry_evidence.py`
  - Pure evidence model and async tool orchestration.
  - Public functions:
    - `query_relationship_evidence(...)`
    - `query_relationship_evidence_for_tool(...)`
  - No Rhino mutation, no scene sync, no projection side effect.

- `mcp_server/tests/test_relationship_geometry_evidence.py`
  - Pure tests for filtering, validation, position parsing, measured/missing evidence, and count shaping.

- `mcp_server/tests/test_relationship_geometry_evidence_tool.py`
  - Tool schema, targeting, local dispatcher, server dispatch, hydration behavior, no-sync behavior.

- `mcp_server/tests/test_relationship_geometry_evidence_live.py`
  - Skippable Rhino live gate using the architectural fixture.

Modify:

- `mcp_server/src/rook/server.py`
  - Add `scene_relationship_evidence` tool schema.
  - Add `_call_tool_dispatch` case.

- `mcp_server/src/rook/agent/tool_dispatcher.py`
  - Add local dispatcher wrapper.

- `mcp_server/src/rook/agent/tool_groups.py`
  - Add tool to `TOOL_GROUPS["scene_graph"]`.

- `mcp_server/src/rook/targeting.py`
  - Add tool to `_ALL_KNOWN_TOOLS`.
  - Add tool to `_RHINO_READ_TOOLS`, not `_RHINO_INDEPENDENT_READ_TOOLS`.

Do not modify:

- `mcp_server/src/rook/scene/relationship_fact_projection.py`
- `mcp_server/src/rook/scene/semantic_relationship_inspector.py`
- `mcp_server/src/rook/scene/object_semantic_context.py`
- architectural or Pearson fixture graph data

---

### Task 1: Pure Evidence Module Skeleton and Input Validation

**Files:**
- Create: `mcp_server/src/rook/scene/relationship_geometry_evidence.py`
- Create: `mcp_server/tests/test_relationship_geometry_evidence.py`

- [ ] **Step 1: Write failing tests for invalid inputs and no projected facts**

Create `mcp_server/tests/test_relationship_geometry_evidence.py` with this initial content:

```python
from __future__ import annotations

import pytest

from rook.scene.relationship_geometry_evidence import query_relationship_evidence
from rook.scene.scene_graph import SceneGraphAnalytics


def _empty_scene_graph() -> SceneGraphAnalytics:
    return SceneGraphAnalytics()


def test_query_relationship_evidence_rejects_bad_object_ids():
    result = query_relationship_evidence(_empty_scene_graph(), object_ids="owner-id")

    assert result == {
        "success": False,
        "error": "invalid_object_ids",
        "message": "object_ids must be a list of strings when supplied",
    }


def test_query_relationship_evidence_rejects_bad_list_filters():
    result = query_relationship_evidence(_empty_scene_graph(), poses="architectural_reference")

    assert result == {
        "success": False,
        "error": "invalid_poses",
        "message": "poses must be a list of strings when supplied",
    }


@pytest.mark.parametrize("value", [None, "0.01", -0.1, float("inf"), True])
def test_query_relationship_evidence_rejects_invalid_tolerance(value):
    result = query_relationship_evidence(_empty_scene_graph(), tolerance_m=value)

    assert result["success"] is False
    assert result["error"] == "invalid_tolerance_m"
    assert result["message"] == "tolerance_m must be a finite number greater than or equal to 0"


def test_query_relationship_evidence_returns_empty_success_without_projected_facts():
    result = query_relationship_evidence(_empty_scene_graph())

    assert result == {
        "success": True,
        "projectionKind": "relationship_fact_v1",
        "evidenceKind": "relationship_geometry_evidence_v1",
        "method": "feature_marker_position_distance",
        "counts": {
            "matchingRelationshipFactCount": 0,
            "evidenceRecordCount": 0,
            "measuredEvidenceCount": 0,
            "missingEvidenceCount": 0,
            "withinToleranceCount": 0,
            "outsideToleranceCount": 0,
            "hydratedFeatureObjectCount": 0,
        },
        "records": [],
        "diagnostics": {
            "noProjectedRelationshipFacts": 1,
        },
    }
```

- [ ] **Step 2: Run tests and verify they fail because the module does not exist**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_geometry_evidence.py -q
```

Expected: import failure similar to:

```text
ModuleNotFoundError: No module named 'rook.scene.relationship_geometry_evidence'
```

- [ ] **Step 3: Add minimal module with constants and validation**

Create `mcp_server/src/rook/scene/relationship_geometry_evidence.py`:

```python
from __future__ import annotations

import math
from typing import Any


PROJECTION_KIND = "relationship_fact_v1"
EVIDENCE_KIND = "relationship_geometry_evidence_v1"
EVIDENCE_METHOD = "feature_marker_position_distance"
EVIDENCE_SOURCE = "rhino_user_text_feature_positions"
DEFAULT_TOLERANCE_M = 0.01


def _bump(diagnostics: dict[str, int], key: str) -> None:
    diagnostics[key] = diagnostics.get(key, 0) + 1


def _optional_list_of_strings_is_valid(value: Any) -> bool:
    return value is None or (isinstance(value, list) and all(isinstance(item, str) for item in value))


def _invalid_list_result(name: str) -> dict[str, Any]:
    return {
        "success": False,
        "error": f"invalid_{name}",
        "message": f"{name} must be a list of strings when supplied",
    }


def _valid_tolerance(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def _invalid_tolerance_result() -> dict[str, Any]:
    return {
        "success": False,
        "error": "invalid_tolerance_m",
        "message": "tolerance_m must be a finite number greater than or equal to 0",
    }


def _empty_response(diagnostics: dict[str, int]) -> dict[str, Any]:
    return {
        "success": True,
        "projectionKind": PROJECTION_KIND,
        "evidenceKind": EVIDENCE_KIND,
        "method": EVIDENCE_METHOD,
        "counts": {
            "matchingRelationshipFactCount": 0,
            "evidenceRecordCount": 0,
            "measuredEvidenceCount": 0,
            "missingEvidenceCount": 0,
            "withinToleranceCount": 0,
            "outsideToleranceCount": 0,
            "hydratedFeatureObjectCount": 0,
        },
        "records": [],
        "diagnostics": diagnostics,
    }


def _projected_edges(graph: Any) -> list[tuple[str, str, Any, dict[str, Any]]]:
    return [
        (str(source), str(target), key, dict(attrs))
        for source, target, key, attrs in graph.edges(keys=True, data=True)
        if attrs.get("projectionKind") == PROJECTION_KIND
    ]


def query_relationship_evidence(
    analytics: Any,
    *,
    object_ids: Any = None,
    graph_source: str | None = None,
    graph_revision: str | None = None,
    poses: Any = None,
    relationship_types: Any = None,
    relationship_fact_ids: Any = None,
    tolerance_m: Any = DEFAULT_TOLERANCE_M,
    feature_user_strings_by_id: dict[str, dict[str, Any] | None] | None = None,
    hydration_diagnostics: dict[str, int] | None = None,
) -> dict[str, Any]:
    for name, value in (
        ("object_ids", object_ids),
        ("poses", poses),
        ("relationship_types", relationship_types),
        ("relationship_fact_ids", relationship_fact_ids),
    ):
        if not _optional_list_of_strings_is_valid(value):
            return _invalid_list_result(name)
    if not _valid_tolerance(tolerance_m):
        return _invalid_tolerance_result()

    diagnostics = dict(hydration_diagnostics or {})
    projected_edges = _projected_edges(analytics.graph)
    if not projected_edges:
        diagnostics["noProjectedRelationshipFacts"] = 1
        return _empty_response(diagnostics)

    diagnostics["noMatchingRelationshipFacts"] = 1
    return _empty_response(diagnostics)
```

- [ ] **Step 4: Run tests and verify Task 1 passes**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_geometry_evidence.py -q
```

Expected:

```text
8 passed
```

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add mcp_server/src/rook/scene/relationship_geometry_evidence.py mcp_server/tests/test_relationship_geometry_evidence.py
git commit -m "feat: add relationship evidence query skeleton"
```

---

### Task 2: Edge Filtering and Evidence Record Construction

**Files:**
- Modify: `mcp_server/src/rook/scene/relationship_geometry_evidence.py`
- Modify: `mcp_server/tests/test_relationship_geometry_evidence.py`

- [ ] **Step 1: Add failing pure tests for matching filters**

Append to `mcp_server/tests/test_relationship_geometry_evidence.py`:

```python
def _scene_graph_with_projected_edges() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node("column-owner", name="column_01")
    sg.graph.add_node("slab-owner", name="slab_01")
    sg.graph.add_node("door-owner", name="door_01")
    sg.graph.add_node("wall-owner", name="wall_01")
    sg.graph.add_edge(
        "column-owner",
        "slab-owner",
        key="relationship_fact:architectural:supports",
        relationship="supports",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="supports",
        relationshipFactId="column_01.top_point_supports_slab_01.underside_region",
        fromFeature="column_01.top_point",
        toFeature="slab_01.underside_region",
        fromFeatureObjectId="feature-column-top",
        toFeatureObjectId="feature-slab-underside",
        contactKind="point_to_region",
        provenance="authored_architectural_fixture",
        confidence=1.0,
        status="accepted",
        graphSource="architectural_relationship_fixture",
        graphRevision="a001",
        pose="architectural_reference",
    )
    sg.graph.add_edge(
        "door-owner",
        "wall-owner",
        key="relationship_fact:architectural:hosted",
        relationship="hosted_by",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="hosted_by",
        relationshipFactId="door_01.body_hosted_by_wall_01.host_region",
        fromFeature="door_01.body",
        toFeature="wall_01.host_region",
        fromFeatureObjectId="feature-door-body",
        toFeatureObjectId="feature-wall-host",
        contactKind="body_to_region",
        provenance="authored_architectural_fixture",
        confidence=1.0,
        status="accepted",
        graphSource="architectural_relationship_fixture",
        graphRevision="a001",
        pose="architectural_reference",
    )
    sg.graph.add_edge(
        "column-owner",
        "wall-owner",
        key="spatial-near",
        relationship="near",
        distance=0.2,
    )
    return sg


def _positions() -> dict[str, dict[str, str]]:
    return {
        "feature-column-top": {"rook.graph.true_position_m": "[0.0, 0.0, 3.0]"},
        "feature-slab-underside": {"rook.graph.true_position_m": "[0.0, 0.0, 3.0]"},
        "feature-door-body": {"rook.graph.true_position_m": "[2.0, -0.1, 1.0]"},
        "feature-wall-host": {"rook.graph.true_position_m": "[2.0, 0.0, 1.0]"},
    }


def test_query_relationship_evidence_filters_by_graph_scope_and_relationship_type():
    result = query_relationship_evidence(
        _scene_graph_with_projected_edges(),
        graph_source="architectural_relationship_fixture",
        graph_revision="a001",
        poses=["architectural_reference"],
        relationship_types=["supports"],
        feature_user_strings_by_id=_positions(),
    )

    assert result["success"] is True
    assert result["counts"]["matchingRelationshipFactCount"] == 1
    assert result["counts"]["evidenceRecordCount"] == 1
    assert result["records"][0]["relationship"] == "supports"
    assert result["records"][0]["relationshipFactId"] == "column_01.top_point_supports_slab_01.underside_region"
    assert "filteredByRelationshipType" in result["diagnostics"]


def test_query_relationship_evidence_filters_by_object_ids_and_fact_ids():
    result = query_relationship_evidence(
        _scene_graph_with_projected_edges(),
        object_ids=["door-owner"],
        relationship_fact_ids=["door_01.body_hosted_by_wall_01.host_region"],
        feature_user_strings_by_id=_positions(),
    )

    assert result["success"] is True
    assert result["counts"]["matchingRelationshipFactCount"] == 1
    assert result["records"][0]["fromObjectId"] == "door-owner"
    assert result["records"][0]["toObjectId"] == "wall-owner"
    assert result["records"][0]["relationship"] == "hosted_by"
```

- [ ] **Step 2: Run new tests and verify they fail because matching edges are not processed**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_geometry_evidence.py::test_query_relationship_evidence_filters_by_graph_scope_and_relationship_type mcp_server/tests/test_relationship_geometry_evidence.py::test_query_relationship_evidence_filters_by_object_ids_and_fact_ids -q
```

Expected: failures where `matchingRelationshipFactCount` is `0`.

- [ ] **Step 3: Implement edge matching and base record fields**

In `mcp_server/src/rook/scene/relationship_geometry_evidence.py`, add these helpers after `_projected_edges`:

```python
def _relationship(attrs: dict[str, Any]) -> str | None:
    value = attrs.get("semanticRelationshipType") or attrs.get("relationship")
    return str(value) if value is not None else None


def _matches_filters(
    source_id: str,
    target_id: str,
    attrs: dict[str, Any],
    *,
    object_ids: list[str] | None,
    graph_source: str | None,
    graph_revision: str | None,
    poses: list[str] | None,
    relationship_types: list[str] | None,
    relationship_fact_ids: list[str] | None,
    diagnostics: dict[str, int],
) -> bool:
    if object_ids is not None and source_id not in set(object_ids) and target_id not in set(object_ids):
        _bump(diagnostics, "filteredByObjectId")
        return False
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
    if relationship_fact_ids and attrs.get("relationshipFactId") not in set(relationship_fact_ids):
        _bump(diagnostics, "filteredByRelationshipFactId")
        return False
    return True


def _base_record(source_id: str, target_id: str, attrs: dict[str, Any]) -> dict[str, Any]:
    return {
        "relationshipFactId": attrs.get("relationshipFactId"),
        "relationship": _relationship(attrs),
        "fromObjectId": source_id,
        "toObjectId": target_id,
        "fromFeature": attrs.get("fromFeature"),
        "toFeature": attrs.get("toFeature"),
        "fromFeatureObjectId": attrs.get("fromFeatureObjectId"),
        "toFeatureObjectId": attrs.get("toFeatureObjectId"),
        "contactKind": attrs.get("contactKind"),
        "graphSource": attrs.get("graphSource"),
        "graphRevision": attrs.get("graphRevision"),
        "pose": attrs.get("pose"),
        "provenance": attrs.get("provenance"),
        "status": attrs.get("status"),
    }
```

Replace the final `diagnostics["noMatchingRelationshipFacts"] = 1` block in `query_relationship_evidence` with:

```python
    records: list[dict[str, Any]] = []
    for source_id, target_id, _key, attrs in projected_edges:
        if not _matches_filters(
            source_id,
            target_id,
            attrs,
            object_ids=object_ids,
            graph_source=graph_source,
            graph_revision=graph_revision,
            poses=poses,
            relationship_types=relationship_types,
            relationship_fact_ids=relationship_fact_ids,
            diagnostics=diagnostics,
        ):
            continue
        record = _base_record(source_id, target_id, attrs)
        record["evidence"] = {
            "kind": EVIDENCE_KIND,
            "method": EVIDENCE_METHOD,
            "status": "missing",
            "missing": ["fromFeaturePosition", "toFeaturePosition"],
            "toleranceM": float(tolerance_m),
            "withinTolerance": None,
            "source": EVIDENCE_SOURCE,
        }
        records.append(record)

    if not records:
        diagnostics["noMatchingRelationshipFacts"] = 1
        return _empty_response(diagnostics)

    return _response(records, diagnostics, hydrated_feature_object_count=0)
```

Add `_response` above `query_relationship_evidence`:

```python
def _response(
    records: list[dict[str, Any]],
    diagnostics: dict[str, int],
    *,
    hydrated_feature_object_count: int,
) -> dict[str, Any]:
    measured = [record for record in records if record["evidence"].get("status") == "measured"]
    missing = [record for record in records if record["evidence"].get("status") == "missing"]
    within = [
        record
        for record in measured
        if record["evidence"].get("withinTolerance") is True
    ]
    outside = [
        record
        for record in measured
        if record["evidence"].get("withinTolerance") is False
    ]
    return {
        "success": True,
        "projectionKind": PROJECTION_KIND,
        "evidenceKind": EVIDENCE_KIND,
        "method": EVIDENCE_METHOD,
        "counts": {
            "matchingRelationshipFactCount": len(records),
            "evidenceRecordCount": len(records),
            "measuredEvidenceCount": len(measured),
            "missingEvidenceCount": len(missing),
            "withinToleranceCount": len(within),
            "outsideToleranceCount": len(outside),
            "hydratedFeatureObjectCount": hydrated_feature_object_count,
        },
        "records": records,
        "diagnostics": diagnostics,
    }
```

- [ ] **Step 4: Run tests and verify Task 2 passes**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_geometry_evidence.py -q
```

Expected: all tests in this file pass.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add mcp_server/src/rook/scene/relationship_geometry_evidence.py mcp_server/tests/test_relationship_geometry_evidence.py
git commit -m "feat: filter projected relationship evidence facts"
```

---

### Task 3: Position Parsing, Distance Measurement, and Missing Evidence

**Files:**
- Modify: `mcp_server/src/rook/scene/relationship_geometry_evidence.py`
- Modify: `mcp_server/tests/test_relationship_geometry_evidence.py`

- [ ] **Step 1: Add failing tests for measured, outside-tolerance, and missing evidence**

Append to `mcp_server/tests/test_relationship_geometry_evidence.py`:

```python
def test_query_relationship_evidence_measures_distance_inside_tolerance():
    result = query_relationship_evidence(
        _scene_graph_with_projected_edges(),
        relationship_types=["supports"],
        tolerance_m=0.01,
        feature_user_strings_by_id=_positions(),
    )

    evidence = result["records"][0]["evidence"]
    assert evidence == {
        "kind": "relationship_geometry_evidence_v1",
        "method": "feature_marker_position_distance",
        "status": "measured",
        "distanceM": 0.0,
        "toleranceM": 0.01,
        "withinTolerance": True,
        "source": "rhino_user_text_feature_positions",
    }
    assert result["counts"]["measuredEvidenceCount"] == 1
    assert result["counts"]["withinToleranceCount"] == 1
    assert result["counts"]["outsideToleranceCount"] == 0


def test_query_relationship_evidence_measures_distance_outside_tolerance():
    result = query_relationship_evidence(
        _scene_graph_with_projected_edges(),
        relationship_types=["hosted_by"],
        tolerance_m=0.01,
        feature_user_strings_by_id=_positions(),
    )

    evidence = result["records"][0]["evidence"]
    assert evidence["status"] == "measured"
    assert evidence["distanceM"] == pytest.approx(0.1)
    assert evidence["toleranceM"] == 0.01
    assert evidence["withinTolerance"] is False
    assert result["counts"]["outsideToleranceCount"] == 1
    assert result["diagnostics"]["outsideTolerance"] == 1


def test_query_relationship_evidence_reports_missing_feature_object_id():
    sg = _scene_graph_with_projected_edges()
    edge_attrs = list(sg.graph["column-owner"]["slab-owner"].values())[0]
    edge_attrs.pop("fromFeatureObjectId")

    result = query_relationship_evidence(
        sg,
        relationship_types=["supports"],
        feature_user_strings_by_id=_positions(),
    )

    assert result["records"][0]["evidence"]["status"] == "missing"
    assert result["records"][0]["evidence"]["missing"] == ["fromFeatureObjectId"]
    assert result["diagnostics"]["missingFeatureObjectId"] == 1


def test_query_relationship_evidence_reports_missing_user_text():
    result = query_relationship_evidence(
        _scene_graph_with_projected_edges(),
        relationship_types=["supports"],
        feature_user_strings_by_id={"feature-slab-underside": _positions()["feature-slab-underside"]},
    )

    assert result["records"][0]["evidence"]["status"] == "missing"
    assert result["records"][0]["evidence"]["missing"] == ["fromFeatureUserText"]
    assert result["diagnostics"]["missingFeatureUserText"] == 1


def test_query_relationship_evidence_reports_invalid_position():
    positions = dict(_positions())
    positions["feature-slab-underside"] = {"rook.graph.true_position_m": "[0.0, 0.0]"}

    result = query_relationship_evidence(
        _scene_graph_with_projected_edges(),
        relationship_types=["supports"],
        feature_user_strings_by_id=positions,
    )

    assert result["records"][0]["evidence"]["status"] == "missing"
    assert result["records"][0]["evidence"]["missing"] == ["toFeaturePosition"]
    assert result["diagnostics"]["invalidFeaturePosition"] == 1
```

- [ ] **Step 2: Run new tests and verify they fail because evidence is always missing**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_geometry_evidence.py::test_query_relationship_evidence_measures_distance_inside_tolerance mcp_server/tests/test_relationship_geometry_evidence.py::test_query_relationship_evidence_measures_distance_outside_tolerance mcp_server/tests/test_relationship_geometry_evidence.py::test_query_relationship_evidence_reports_missing_feature_object_id mcp_server/tests/test_relationship_geometry_evidence.py::test_query_relationship_evidence_reports_missing_user_text mcp_server/tests/test_relationship_geometry_evidence.py::test_query_relationship_evidence_reports_invalid_position -q
```

Expected: failures where `evidence["status"]` is still `"missing"` for measured cases and missing reasons are not specific.

- [ ] **Step 3: Implement position parsing and evidence building**

In `mcp_server/src/rook/scene/relationship_geometry_evidence.py`, add imports:

```python
import json
```

Add these helpers before `_response`:

```python
def _parse_position(value: Any) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, list) or len(value) != 3:
        return None
    coords: list[float] = []
    for item in value:
        if not isinstance(item, (int, float)) or isinstance(item, bool):
            return None
        coord = float(item)
        if not math.isfinite(coord):
            return None
        coords.append(coord)
    return (coords[0], coords[1], coords[2])


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def _missing_evidence(missing: list[str], tolerance_m: float) -> dict[str, Any]:
    return {
        "kind": EVIDENCE_KIND,
        "method": EVIDENCE_METHOD,
        "status": "missing",
        "missing": missing,
        "toleranceM": tolerance_m,
        "withinTolerance": None,
        "source": EVIDENCE_SOURCE,
    }


def _measured_evidence(distance_m: float, tolerance_m: float) -> dict[str, Any]:
    return {
        "kind": EVIDENCE_KIND,
        "method": EVIDENCE_METHOD,
        "status": "measured",
        "distanceM": distance_m,
        "toleranceM": tolerance_m,
        "withinTolerance": distance_m <= tolerance_m,
        "source": EVIDENCE_SOURCE,
    }


def _evidence_for_record(
    record: dict[str, Any],
    *,
    feature_user_strings_by_id: dict[str, dict[str, Any] | None],
    tolerance_m: float,
    diagnostics: dict[str, int],
) -> dict[str, Any]:
    missing: list[str] = []
    from_feature_object_id = record.get("fromFeatureObjectId")
    to_feature_object_id = record.get("toFeatureObjectId")
    if not from_feature_object_id:
        missing.append("fromFeatureObjectId")
        _bump(diagnostics, "missingFeatureObjectId")
    if not to_feature_object_id:
        missing.append("toFeatureObjectId")
        _bump(diagnostics, "missingFeatureObjectId")
    if missing:
        return _missing_evidence(missing, tolerance_m)

    from_user_text = feature_user_strings_by_id.get(str(from_feature_object_id))
    to_user_text = feature_user_strings_by_id.get(str(to_feature_object_id))
    if from_user_text is None:
        missing.append("fromFeatureUserText")
        _bump(diagnostics, "missingFeatureUserText")
    if to_user_text is None:
        missing.append("toFeatureUserText")
        _bump(diagnostics, "missingFeatureUserText")
    if missing:
        return _missing_evidence(missing, tolerance_m)

    from_position = _parse_position(from_user_text.get("rook.graph.true_position_m"))
    to_position = _parse_position(to_user_text.get("rook.graph.true_position_m"))
    if from_position is None:
        key = (
            "missingFeaturePosition"
            if from_user_text.get("rook.graph.true_position_m") is None
            else "invalidFeaturePosition"
        )
        _bump(diagnostics, key)
        missing.append("fromFeaturePosition")
    if to_position is None:
        key = (
            "missingFeaturePosition"
            if to_user_text.get("rook.graph.true_position_m") is None
            else "invalidFeaturePosition"
        )
        _bump(diagnostics, key)
        missing.append("toFeaturePosition")
    if missing:
        return _missing_evidence(missing, tolerance_m)

    distance_m = _distance(from_position, to_position)
    evidence = _measured_evidence(distance_m, tolerance_m)
    if evidence["withinTolerance"] is False:
        _bump(diagnostics, "outsideTolerance")
    return evidence
```

In `query_relationship_evidence`, after `record = _base_record(...)`, replace the temporary missing evidence assignment with:

```python
        record["evidence"] = _evidence_for_record(
            record,
            feature_user_strings_by_id=feature_user_strings_by_id or {},
            tolerance_m=float(tolerance_m),
            diagnostics=diagnostics,
        )
```

Also pass the hydrated count to `_response`:

```python
    hydrated_feature_object_count = len(
        [value for value in (feature_user_strings_by_id or {}).values() if value is not None]
    )
    return _response(records, diagnostics, hydrated_feature_object_count=hydrated_feature_object_count)
```

- [ ] **Step 4: Run tests and verify Task 3 passes**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_geometry_evidence.py -q
```

Expected: all pure evidence tests pass.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add mcp_server/src/rook/scene/relationship_geometry_evidence.py mcp_server/tests/test_relationship_geometry_evidence.py
git commit -m "feat: measure relationship feature evidence"
```

---

### Task 4: Async Rhino User Text Hydration for Tool Use

**Files:**
- Modify: `mcp_server/src/rook/scene/relationship_geometry_evidence.py`
- Modify: `mcp_server/tests/test_relationship_geometry_evidence.py`

- [ ] **Step 1: Add failing async tests for feature-id collection and hydration failures**

Append to `mcp_server/tests/test_relationship_geometry_evidence.py`:

```python
@pytest.mark.asyncio
async def test_query_relationship_evidence_for_tool_hydrates_only_matching_feature_ids(monkeypatch):
    from rook.scene import relationship_geometry_evidence as evidence

    sg = _scene_graph_with_projected_edges()
    calls: list[tuple[str, str, dict, int | None]] = []

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        calls.append((path, method, payload, port))
        return {
            "success": True,
            "data": {
                "id": payload["id"],
                "userStrings": _positions()[payload["id"]],
            },
        }

    monkeypatch.setattr(evidence, "call_rhino", fake_call_rhino)

    result = await evidence.query_relationship_evidence_for_tool(
        analytics=sg,
        graph_source="architectural_relationship_fixture",
        relationship_types=["supports"],
        port=9876,
    )

    assert result["success"] is True
    assert calls == [
        ("/usertext/object-get", "POST", {"id": "feature-column-top"}, 9876),
        ("/usertext/object-get", "POST", {"id": "feature-slab-underside"}, 9876),
    ]
    assert result["counts"]["hydratedFeatureObjectCount"] == 2
    assert result["counts"]["withinToleranceCount"] == 1


@pytest.mark.asyncio
async def test_query_relationship_evidence_for_tool_fails_when_all_hydration_fails(monkeypatch):
    from rook.scene import relationship_geometry_evidence as evidence

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        raise RuntimeError("no_rhino_instance")

    monkeypatch.setattr(evidence, "call_rhino", fake_call_rhino)

    result = await evidence.query_relationship_evidence_for_tool(
        analytics=_scene_graph_with_projected_edges(),
        graph_source="architectural_relationship_fixture",
    )

    assert result == {
        "success": False,
        "error": "relationship_evidence_hydration_unavailable",
        "message": "Unable to read Rhino user text for any requested feature marker objects",
        "diagnostics": {"hydrationFailures": 4},
    }


@pytest.mark.asyncio
async def test_query_relationship_evidence_for_tool_keeps_partial_hydration_failures_as_missing(monkeypatch):
    from rook.scene import relationship_geometry_evidence as evidence

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        if payload["id"] == "feature-door-body":
            raise RuntimeError("transient read failure")
        return {
            "success": True,
            "data": {
                "id": payload["id"],
                "userStrings": _positions()[payload["id"]],
            },
        }

    monkeypatch.setattr(evidence, "call_rhino", fake_call_rhino)

    result = await evidence.query_relationship_evidence_for_tool(
        analytics=_scene_graph_with_projected_edges(),
        graph_source="architectural_relationship_fixture",
    )

    assert result["success"] is True
    assert result["counts"]["matchingRelationshipFactCount"] == 2
    assert result["counts"]["measuredEvidenceCount"] == 1
    assert result["counts"]["missingEvidenceCount"] == 1
    assert result["diagnostics"]["hydrationFailures"] == 1
```

- [ ] **Step 2: Run new async tests and verify they fail because the async tool function does not exist**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_geometry_evidence.py::test_query_relationship_evidence_for_tool_hydrates_only_matching_feature_ids mcp_server/tests/test_relationship_geometry_evidence.py::test_query_relationship_evidence_for_tool_fails_when_all_hydration_fails mcp_server/tests/test_relationship_geometry_evidence.py::test_query_relationship_evidence_for_tool_keeps_partial_hydration_failures_as_missing -q
```

Expected: attribute error for `query_relationship_evidence_for_tool`.

- [ ] **Step 3: Implement async hydration and tool entry point**

In `mcp_server/src/rook/scene/relationship_geometry_evidence.py`, add imports:

```python
from ..bridge import call_rhino
```

Add constant:

```python
USER_TEXT_OBJECT_GET_ROUTE = "/usertext/object-get"
```

Add these helpers before `query_relationship_evidence`:

```python
def _feature_object_ids_for_matching_edges(
    analytics: Any,
    *,
    object_ids: list[str] | None,
    graph_source: str | None,
    graph_revision: str | None,
    poses: list[str] | None,
    relationship_types: list[str] | None,
    relationship_fact_ids: list[str] | None,
) -> list[str]:
    diagnostics: dict[str, int] = {}
    result: list[str] = []
    seen: set[str] = set()
    for source_id, target_id, _key, attrs in _projected_edges(analytics.graph):
        if not _matches_filters(
            source_id,
            target_id,
            attrs,
            object_ids=object_ids,
            graph_source=graph_source,
            graph_revision=graph_revision,
            poses=poses,
            relationship_types=relationship_types,
            relationship_fact_ids=relationship_fact_ids,
            diagnostics=diagnostics,
        ):
            continue
        for field in ("fromFeatureObjectId", "toFeatureObjectId"):
            value = attrs.get(field)
            if not value:
                continue
            object_id = str(value)
            if object_id in seen:
                continue
            seen.add(object_id)
            result.append(object_id)
    return result


def _response_route_failed(response: dict[str, Any]) -> bool:
    if not response.get("success"):
        return True
    data = response.get("data")
    if not isinstance(data, dict):
        return True
    return False


def _extract_user_strings(response: dict[str, Any]) -> dict[str, Any] | None:
    data = response.get("data")
    if not isinstance(data, dict):
        return None
    user_strings = data.get("userStrings")
    return user_strings if isinstance(user_strings, dict) else None


async def _hydrate_feature_user_strings(
    object_ids: list[str],
    *,
    port: int | None = None,
) -> tuple[dict[str, dict[str, Any] | None], dict[str, int], bool]:
    user_strings_by_id: dict[str, dict[str, Any] | None] = {}
    diagnostics: dict[str, int] = {}
    failures = 0
    for object_id in object_ids:
        try:
            response = await call_rhino(
                USER_TEXT_OBJECT_GET_ROUTE,
                "POST",
                {"id": object_id},
                port=port,
            )
        except Exception:
            failures += 1
            _bump(diagnostics, "hydrationFailures")
            user_strings_by_id[object_id] = None
            continue
        if _response_route_failed(response):
            failures += 1
            _bump(diagnostics, "hydrationFailures")
            user_strings_by_id[object_id] = None
            continue
        user_strings_by_id[object_id] = _extract_user_strings(response)
    all_failed = bool(object_ids) and failures == len(object_ids)
    return user_strings_by_id, diagnostics, all_failed
```

Add public async function:

```python
async def query_relationship_evidence_for_tool(
    *,
    object_ids: Any = None,
    graph_source: str | None = None,
    graph_revision: str | None = None,
    poses: Any = None,
    relationship_types: Any = None,
    relationship_fact_ids: Any = None,
    tolerance_m: Any = DEFAULT_TOLERANCE_M,
    port: int | None = None,
    analytics: Any | None = None,
) -> dict[str, Any]:
    if analytics is None:
        from .scene_graph import get_scene_graph

        analytics = get_scene_graph()

    for name, value in (
        ("object_ids", object_ids),
        ("poses", poses),
        ("relationship_types", relationship_types),
        ("relationship_fact_ids", relationship_fact_ids),
    ):
        if not _optional_list_of_strings_is_valid(value):
            return _invalid_list_result(name)
    if not _valid_tolerance(tolerance_m):
        return _invalid_tolerance_result()

    feature_object_ids = _feature_object_ids_for_matching_edges(
        analytics,
        object_ids=object_ids,
        graph_source=graph_source,
        graph_revision=graph_revision,
        poses=poses,
        relationship_types=relationship_types,
        relationship_fact_ids=relationship_fact_ids,
    )
    feature_user_strings_by_id, hydration_diagnostics, all_failed = await _hydrate_feature_user_strings(
        feature_object_ids,
        port=port,
    )
    if all_failed:
        return {
            "success": False,
            "error": "relationship_evidence_hydration_unavailable",
            "message": "Unable to read Rhino user text for any requested feature marker objects",
            "diagnostics": hydration_diagnostics,
        }
    return query_relationship_evidence(
        analytics,
        object_ids=object_ids,
        graph_source=graph_source,
        graph_revision=graph_revision,
        poses=poses,
        relationship_types=relationship_types,
        relationship_fact_ids=relationship_fact_ids,
        tolerance_m=tolerance_m,
        feature_user_strings_by_id=feature_user_strings_by_id,
        hydration_diagnostics=hydration_diagnostics,
    )
```

- [ ] **Step 4: Run tests and verify Task 4 passes**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_geometry_evidence.py -q
```

Expected: pure and async tests pass.

- [ ] **Step 5: Commit Task 4**

Run:

```powershell
git add mcp_server/src/rook/scene/relationship_geometry_evidence.py mcp_server/tests/test_relationship_geometry_evidence.py
git commit -m "feat: hydrate relationship evidence feature positions"
```

---

### Task 5: MCP, Local Dispatcher, Targeting, and Tool Group Wiring

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Create: `mcp_server/tests/test_relationship_geometry_evidence_tool.py`

- [ ] **Step 1: Write failing registration and dispatch tests**

Create `mcp_server/tests/test_relationship_geometry_evidence_tool.py`:

```python
from __future__ import annotations

import pytest

from rook.scene.scene_graph import SceneGraphAnalytics


def _scene_graph() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node("column-owner", name="column_01")
    sg.graph.add_node("slab-owner", name="slab_01")
    sg.graph.add_edge(
        "column-owner",
        "slab-owner",
        key="relationship_fact:architectural:supports",
        relationship="supports",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="supports",
        relationshipFactId="column_01.top_point_supports_slab_01.underside_region",
        fromFeature="column_01.top_point",
        toFeature="slab_01.underside_region",
        fromFeatureObjectId="feature-column-top",
        toFeatureObjectId="feature-slab-underside",
        contactKind="point_to_region",
        provenance="authored_architectural_fixture",
        confidence=1.0,
        status="accepted",
        graphSource="architectural_relationship_fixture",
        graphRevision="a001",
        pose="architectural_reference",
    )
    return sg


def _user_strings_for(object_id: str) -> dict[str, str]:
    return {
        "feature-column-top": {"rook.graph.true_position_m": "[0.0, 0.0, 3.0]"},
        "feature-slab-underside": {"rook.graph.true_position_m": "[0.0, 0.0, 3.0]"},
    }[object_id]


@pytest.mark.asyncio
async def test_server_tool_schema_exposes_scene_relationship_evidence_parameters():
    from rook.server import list_tools

    tools = {tool.name: tool for tool in await list_tools()}
    schema = tools["scene_relationship_evidence"].inputSchema

    assert schema["required"] == []
    assert schema["properties"]["object_ids"]["items"]["type"] == "string"
    assert schema["properties"]["graph_source"]["type"] == "string"
    assert schema["properties"]["graph_revision"]["type"] == "string"
    assert schema["properties"]["poses"]["items"]["type"] == "string"
    assert schema["properties"]["relationship_types"]["items"]["type"] == "string"
    assert schema["properties"]["relationship_fact_ids"]["items"]["type"] == "string"
    assert schema["properties"]["tolerance_m"]["type"] == "number"
    assert schema["properties"]["port"]["type"] == "integer"
    assert "sync" not in schema["properties"]
    assert "project_first" not in schema["properties"]


def test_tool_group_contains_scene_relationship_evidence():
    from rook.agent.tool_groups import TOOL_GROUPS

    assert "scene_relationship_evidence" in TOOL_GROUPS["scene_graph"]


def test_scene_relationship_evidence_targeting_policy_is_rhino_read():
    from rook import targeting

    pol = targeting.policy_for_tool("scene_relationship_evidence")

    assert pol.requires_rhino is True
    assert pol.risk == "read"
    assert "scene_relationship_evidence" in targeting._ALL_KNOWN_TOOLS


def test_local_dispatcher_registers_scene_relationship_evidence():
    from rook.agent.tool_dispatcher import build_local_tools

    tools = build_local_tools()

    assert "scene_relationship_evidence" in tools
    assert callable(tools["scene_relationship_evidence"])


@pytest.mark.asyncio
async def test_local_scene_relationship_evidence_dispatch_does_not_sync(monkeypatch):
    from rook.scene import relationship_geometry_evidence as evidence

    sg = _scene_graph()
    called = {"sync": 0}

    async def fake_sync(port=None):
        called["sync"] += 1
        return {"success": True}

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        return {"success": True, "data": {"id": payload["id"], "userStrings": _user_strings_for(payload["id"])}}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)
    monkeypatch.setattr(evidence, "call_rhino", fake_call_rhino)

    from rook.agent.tool_dispatcher import build_local_tools

    result = await build_local_tools()["scene_relationship_evidence"](
        graph_source="architectural_relationship_fixture",
    )

    assert result["success"] is True
    assert result["counts"]["withinToleranceCount"] == 1
    assert called["sync"] == 0


@pytest.mark.asyncio
async def test_server_dispatch_scene_relationship_evidence(monkeypatch):
    from rook.scene import relationship_geometry_evidence as evidence

    sg = _scene_graph()

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        return {"success": True, "data": {"id": payload["id"], "userStrings": _user_strings_for(payload["id"])}}

    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)
    monkeypatch.setattr(evidence, "call_rhino", fake_call_rhino)

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch(
        "scene_relationship_evidence",
        {"graph_source": "architectural_relationship_fixture"},
    )

    assert result["success"] is True
    payload = result["data"]
    assert payload["success"] is True
    assert payload["evidenceKind"] == "relationship_geometry_evidence_v1"
    assert payload["counts"]["measuredEvidenceCount"] == 1


@pytest.mark.asyncio
async def test_server_dispatch_scene_relationship_evidence_reports_hydration_unavailable(monkeypatch):
    from rook.scene import relationship_geometry_evidence as evidence

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        raise RuntimeError("no_rhino_instance")

    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: _scene_graph())
    monkeypatch.setattr(evidence, "call_rhino", fake_call_rhino)

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch(
        "scene_relationship_evidence",
        {"graph_source": "architectural_relationship_fixture"},
    )

    assert result["success"] is False
    assert result["data"]["error"] == "relationship_evidence_hydration_unavailable"
```

- [ ] **Step 2: Run tool tests and verify they fail because the tool is not wired**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_geometry_evidence_tool.py -q
```

Expected: failures for missing `scene_relationship_evidence` in schemas/registries.

- [ ] **Step 3: Add MCP tool schema**

In `mcp_server/src/rook/server.py`, add a `Tool(...)` near `scene_semantic_relationships`:

```python
        Tool(
            name="scene_relationship_evidence",
            description="""Measure feature-marker-position evidence for already-projected relationship facts.

Reads relationship_fact_v1 edges from the current in-memory scene graph and reads Rhino user text only for their feature marker object ids. Does not sync, project, infer, mutate Rhino, inspect owner geometry, or change relationship status.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional owner object ids; include facts touching any supplied owner id",
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
                        "description": "Optional relationship type filter",
                    },
                    "relationship_fact_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional relationshipFactId filter",
                    },
                    "tolerance_m": {
                        "type": "number",
                        "description": "Distance tolerance in meters for withinTolerance; default 0.01",
                    },
                    "port": {"type": "integer", "description": "Rhino instance port"},
                },
                "required": [],
            },
        ),
```

- [ ] **Step 4: Add server dispatch case**

In `mcp_server/src/rook/server.py`, add a `match` case near the other scene relationship tools:

```python
        case "scene_relationship_evidence":
            from .scene.relationship_geometry_evidence import query_relationship_evidence_for_tool

            payload = await query_relationship_evidence_for_tool(
                object_ids=arguments.get("object_ids"),
                graph_source=arguments.get("graph_source"),
                graph_revision=arguments.get("graph_revision"),
                poses=arguments.get("poses"),
                relationship_types=arguments.get("relationship_types"),
                relationship_fact_ids=arguments.get("relationship_fact_ids"),
                tolerance_m=arguments.get("tolerance_m", 0.01),
                port=port,
            )
            if payload.get("success") is False:
                result = {"success": False, "data": payload}
            else:
                result = {"success": True, "data": payload}
```

- [ ] **Step 5: Add local dispatcher registration**

In `mcp_server/src/rook/agent/tool_dispatcher.py`, add near the semantic relationship local tools:

```python
    # --- scene_relationship_evidence (Python-side relationship geometry evidence) ---
    try:
        from ..scene.relationship_geometry_evidence import query_relationship_evidence_for_tool

        async def _scene_relationship_evidence(
            object_ids=None,
            graph_source=None,
            graph_revision=None,
            poses=None,
            relationship_types=None,
            relationship_fact_ids=None,
            tolerance_m=0.01,
            port: int | None = None,
            **kwargs,
        ) -> dict:
            return await query_relationship_evidence_for_tool(
                object_ids=object_ids,
                graph_source=graph_source,
                graph_revision=graph_revision,
                poses=poses,
                relationship_types=relationship_types,
                relationship_fact_ids=relationship_fact_ids,
                tolerance_m=tolerance_m,
                port=port,
            )

        tools["scene_relationship_evidence"] = _scene_relationship_evidence
    except ImportError:
        logger.debug("scene_relationship_evidence local tool unavailable (import failed)")
```

- [ ] **Step 6: Add tool group and targeting policy**

In `mcp_server/src/rook/agent/tool_groups.py`, add to `TOOL_GROUPS["scene_graph"]`:

```python
        "scene_relationship_evidence",
```

In `mcp_server/src/rook/targeting.py`:

Add to `_ALL_KNOWN_TOOLS`:

```python
    "scene_relationship_evidence",
```

Add to `_RHINO_READ_TOOLS`:

```python
    "scene_relationship_evidence",
```

Do not add it to `_RHINO_INDEPENDENT_READ_TOOLS`.

- [ ] **Step 7: Run tool tests and verify Task 5 passes**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_geometry_evidence.py mcp_server/tests/test_relationship_geometry_evidence_tool.py -q
```

Expected: all relationship evidence pure and tool tests pass.

- [ ] **Step 8: Commit Task 5**

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/targeting.py mcp_server/tests/test_relationship_geometry_evidence_tool.py
git commit -m "feat: expose relationship geometry evidence tool"
```

---

### Task 6: Architectural Fixture Live Evidence Gate

**Files:**
- Create: `mcp_server/tests/test_relationship_geometry_evidence_live.py`

- [ ] **Step 1: Write failing live test for architectural evidence counts**

Create `mcp_server/tests/test_relationship_geometry_evidence_live.py`:

```python
from __future__ import annotations

import json

import pytest

from .architectural_fixture_helpers import (
    GENERATED_SCRIPT_PATH,
    GRAPH_REVISION,
    GRAPH_SOURCE,
    POSE,
    assert_fixture_summary,
    json_from_execute_output,
    script_output_from_execute_result,
)
from .conftest import _is_error, fresh_document


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


async def _create_architectural_fixture() -> dict:
    from rook.server import _mcp_tool_executor

    script = GENERATED_SCRIPT_PATH.read_text(encoding="utf-8")
    result = await _mcp_tool_executor("rhino_execute", {"code": script})
    assert not _is_error(result), f"rhino_execute architectural fixture failed: {result!r}"
    summary = json_from_execute_output(script_output_from_execute_result(result))
    assert_fixture_summary(summary)
    return summary


def _record_by_relationship(records: list[dict], relationship: str) -> dict:
    for record in records:
        if record["relationship"] == relationship:
            return record
    raise AssertionError(f"relationship evidence record not found: {relationship}; records={records!r}")


async def test_architectural_relationship_geometry_evidence_live(fresh_document):
    from rook.scene.relationship_fact_projection import project_relationship_facts_for_tool
    from rook.scene.relationship_geometry_evidence import query_relationship_evidence_for_tool
    from rook.scene.scene_graph import get_scene_graph

    fixture_summary = await _create_architectural_fixture()
    sg = get_scene_graph()

    projection = await project_relationship_facts_for_tool(
        graph_source=GRAPH_SOURCE,
        graph_revision=GRAPH_REVISION,
        poses=[POSE],
        strict=True,
        analytics=sg,
    )
    assert projection["success"] is True, f"projection failed: {projection!r}"
    assert projection["counts"]["projectedEdgeCount"] == 5

    evidence = await query_relationship_evidence_for_tool(
        analytics=sg,
        graph_source=GRAPH_SOURCE,
        graph_revision=GRAPH_REVISION,
        poses=[POSE],
    )
    if evidence.get("success") is not True:
        pytest.fail(json.dumps({"fixtureSummary": fixture_summary, "evidence": evidence}, indent=2, sort_keys=True))

    assert evidence["counts"] == {
        "matchingRelationshipFactCount": 5,
        "evidenceRecordCount": 5,
        "measuredEvidenceCount": 5,
        "missingEvidenceCount": 0,
        "withinToleranceCount": 3,
        "outsideToleranceCount": 2,
        "hydratedFeatureObjectCount": 10,
    }
    assert evidence["diagnostics"]["outsideTolerance"] == 2

    supports = _record_by_relationship(evidence["records"], "supports")
    assert supports["contactKind"] == "point_to_region"
    assert supports["evidence"]["status"] == "measured"
    assert supports["evidence"]["distanceM"] == pytest.approx(0.0)
    assert supports["evidence"]["withinTolerance"] is True

    hosted_by = _record_by_relationship(evidence["records"], "hosted_by")
    assert hosted_by["contactKind"] == "body_to_region"
    assert hosted_by["evidence"]["distanceM"] == pytest.approx(0.1)
    assert hosted_by["evidence"]["withinTolerance"] is False

    voids = _record_by_relationship(evidence["records"], "voids")
    assert voids["contactKind"] == "profile_to_region"
    assert voids["evidence"]["distanceM"] == pytest.approx(0.02)
    assert voids["evidence"]["withinTolerance"] is False

    penetrates = _record_by_relationship(evidence["records"], "penetrates")
    assert penetrates["contactKind"] == "line_to_region"
    assert penetrates["evidence"]["distanceM"] == pytest.approx(0.0)
    assert penetrates["evidence"]["withinTolerance"] is True

    bounded_by = _record_by_relationship(evidence["records"], "bounded_by")
    assert bounded_by["contactKind"] == "boundary_to_face"
    assert bounded_by["evidence"]["distanceM"] == pytest.approx(0.0)
    assert bounded_by["evidence"]["withinTolerance"] is True
```

- [ ] **Step 2: Run live test and verify it fails before implementation wiring is complete, or skips if Rhino is unavailable**

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_relationship_geometry_evidence_live.py -q -rs
```

Expected before Task 5 is complete: import/tool failure.

Expected after Task 5 is complete with Rhino open:

```text
1 passed
```

If it skips with `no_rhino_instance`, do not patch code. Confirm Rhino/Rook session discovery before changing implementation.

- [ ] **Step 3: Run live test after Task 5 is green**

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_relationship_geometry_evidence_live.py -q -rs
```

Expected with a reachable throwaway Rhino document:

```text
1 passed
```

- [ ] **Step 4: Commit Task 6**

Run:

```powershell
git add mcp_server/tests/test_relationship_geometry_evidence_live.py
git commit -m "test: add architectural relationship evidence live gate"
```

---

### Task 7: Regression Suite and Final Checks

**Files:**
- No new files unless prior tasks expose a real regression.

- [ ] **Step 1: Run focused evidence tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_geometry_evidence.py mcp_server/tests/test_relationship_geometry_evidence_tool.py -q
```

Expected: all pass.

- [ ] **Step 2: Run existing relationship and semantic graph focused tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_authored_graph_schema_v2.py mcp_server/tests/test_relationship_fact_projection.py mcp_server/tests/test_relationship_fact_projection_tool.py mcp_server/tests/test_architectural_relationship_fixture.py mcp_server/tests/test_pearson_g002_roundtrip_gate.py -q
```

Expected: all pass. Current baseline before this slice is `47 passed`.

- [ ] **Step 3: Run downstream semantic/profile tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_semantic_relationship_inspector.py mcp_server/tests/test_semantic_relationship_inspector_tool.py mcp_server/tests/test_object_semantic_context.py mcp_server/tests/test_object_semantic_context_tool.py mcp_server/tests/test_relationship_profile.py mcp_server/tests/test_relationship_profile_tool.py mcp_server/tests/test_object_semantic_context_profile_boundary.py -q
```

Expected: all pass. Current baseline before this slice is `69 passed`.

- [ ] **Step 4: Run live evidence gate if Rhino is open**

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_relationship_geometry_evidence_live.py -q -rs
```

Expected with reachable Rhino/Rook:

```text
1 passed
```

If skipped with `no_rhino_instance`, report the skip separately and do not patch behavior.

- [ ] **Step 5: Run existing architectural and Pearson live gates if Rhino remains open**

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_architectural_relationship_fixture_live.py mcp_server/tests/test_pearson_g002_roundtrip_gate_live.py -q -rs
```

Expected with reachable Rhino/Rook:

```text
2 passed
```

If skipped with `no_rhino_instance`, report the skip separately and do not patch behavior.

- [ ] **Step 6: Run git whitespace and commit checks**

Run:

```powershell
git diff --check
git show --check --stat HEAD
git status --short --branch
```

Expected:

```text
git diff --check exits 0
git show --check --stat HEAD exits 0
git status shows a clean worktree on codex/relationship-geometry-evidence-v1
```

- [ ] **Step 7: Push branch**

Run:

```powershell
git push -u origin codex/relationship-geometry-evidence-v1
```

Expected:

```text
branch 'codex/relationship-geometry-evidence-v1' set up to track 'origin/codex/relationship-geometry-evidence-v1'
```

---

## Self-Review Checklist

- [ ] Spec Section 2 goal is covered by `scene_relationship_evidence` and `query_relationship_evidence_for_tool`.
- [ ] Spec Section 3 non-goals are preserved: no sync, no projection, no inference, no mutation, no owner geometry inspection, no card enrichment.
- [ ] Spec Section 4 tool inputs are represented in server schema, local dispatcher, and public function signatures.
- [ ] Spec Section 5 filters are covered by pure tests.
- [ ] Spec Section 6 hydration source is implemented through `/usertext/object-get` for only unique `fromFeatureObjectId` / `toFeatureObjectId` values.
- [ ] Spec Section 6 failure distinction is tested: partial hydration failure is missing evidence; all hydration failure is `success=false`.
- [ ] Spec Section 7 position source uses only `rook.graph.true_position_m`.
- [ ] Spec Section 8 evidence model returns `measured` and `missing` states with stable missing keys.
- [ ] Spec Section 9 response counts include measured, missing, within tolerance, outside tolerance, and hydrated feature object counts.
- [ ] Spec Section 10 targeting policy is Rhino read access, not Rhino-independent.
- [ ] Spec Section 11 live architectural evidence gate asserts 3 inside tolerance and 2 outside tolerance at default `0.01m`.

## Implementation Notes

- Keep `relationship_geometry_evidence.py` focused. If `query_relationship_evidence_for_tool()` grows beyond validation, matching, hydration, and response assembly, extract a private helper immediately.
- Do not reuse `scene_semantic_relationships` for filtering. It is selected-object view oriented and duplicates facts per selected endpoint; this tool needs unique projected edge records.
- Do not read feature marker rendered geometry. The only v1 measurement source is `rook.graph.true_position_m`.
- Do not turn outside tolerance into failure. Outside tolerance is measured evidence and should keep `success=true`.
- Do not add evidence to object semantic cards in this slice.
