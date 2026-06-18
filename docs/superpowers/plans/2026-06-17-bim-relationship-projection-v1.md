# BIM Relationship Projection v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only MCP scene tool that projects RookBIM sidecar host/room/level facts into the Python `networkx` scene graph mirror as provenance-tagged, idempotent read-model enrichment.

**Architecture:** Build a pure Python projector module first, then wire it to the MCP scene tool boundary. The tool syncs `SceneGraphAnalytics`, self-hydrates object user strings through read-only `/usertext/object-get`, joins by `revit.uniqueId`, and upserts BIM nodes/edges into the in-memory mirror without mutating Rhino or Revit documents.

**Tech Stack:** Python 3.10+, `networkx.MultiDiGraph`, existing Rook MCP `server.py`, `SceneGraphAnalytics`, pytest.

---

## File Structure

- Create `mcp_server/src/rook/scene/bim_relationship_projection.py`
  - Sidecar parsing and validation.
  - Sidecar fingerprinting and reference-node id helpers.
  - Runtime record normalization from hydrated user strings.
  - Eligibility filtering.
  - Projection/upsert/prune logic for `networkx.MultiDiGraph`.
  - Tool-boundary orchestration helper that calls `analytics.sync()` and `/usertext/object-get`.
- Modify `mcp_server/src/rook/scene/scene_graph.py`
  - Add friendly display labels/details for `revit_hosted_by`, `revit_in_room`, and `revit_on_level`.
  - Keep generic context behavior intact for other relationships.
- Modify `mcp_server/src/rook/server.py`
  - Add the MCP tool schema.
  - Add dispatch case for `scene_project_bim_relationships`.
- Modify `mcp_server/src/rook/agent/tool_dispatcher.py`
  - Add local dispatcher registration for agent/runtime surfaces that use local tools.
- Modify `mcp_server/src/rook/agent/tool_groups.py`
  - Add the tool to the `scene_graph` group.
- Modify `mcp_server/src/rook/targeting.py`
  - Add the tool to known tools and Rhino read tools.
- Create `mcp_server/tests/test_bim_relationship_projection.py`
  - Pure unit tests for parser, join/filtering, projection, pruning, and invariant guards.
- Create `mcp_server/tests/test_bim_relationship_projection_tool.py`
  - Tool schema, dispatch, tool group, targeting, and read-only hydration orchestration tests.
- Create `mcp_server/tests/test_live_bim_relationship_projection.py`
  - `requires_rhino` live-gated wiring test using an already exported `.3dm` + sidecar.

---

## Task 1: Sidecar Parser, Fingerprint, and Constants

**Files:**
- Create: `mcp_server/src/rook/scene/bim_relationship_projection.py`
- Create: `mcp_server/tests/test_bim_relationship_projection.py`

- [ ] **Step 1: Write failing parser and constants tests**

Create `mcp_server/tests/test_bim_relationship_projection.py` with this initial content:

```python
import json

import pytest

from rook.scene import bim_relationship_projection as bim


def _sidecar() -> dict:
    return {
        "schemaVersion": 1,
        "elements": [
            {
                "identity": {
                    "uniqueId": "uid-wall",
                    "elementId": 100,
                    "documentTitle": "Model A",
                },
                "category": "Walls",
                "family": "Basic Wall",
                "type": "Generic 200mm",
                "name": "Wall Type",
                "labels": {
                    "level": {"value": "L1", "source": "revit_api", "confidence": "high"},
                    "hostId": {"value": None, "source": "unavailable", "confidence": None},
                    "containingRoomId": {"value": None, "source": "unavailable", "confidence": None},
                },
            },
            {
                "identity": {
                    "uniqueId": "uid-door",
                    "elementId": 200,
                    "documentTitle": "Model A",
                },
                "category": "Doors",
                "family": "Single-Flush",
                "type": "0915 x 2134mm",
                "name": "Door Type",
                "labels": {
                    "level": {"value": "L1", "source": "revit_api", "confidence": "high"},
                    "hostId": {"value": 100, "source": "revit_api", "confidence": "high"},
                    "containingRoomId": {"value": "room-1", "source": "revit_api", "confidence": "high"},
                },
            },
        ],
        "rooms": [
            {
                "uniqueId": "room-1",
                "roomId": "room-1",
                "number": "101",
                "name": "Office",
                "geometryRepresentation": "room_mesh",
                "referenceGeometry": True,
            }
        ],
        "relationships": {
            "hostMembership": [
                {
                    "elementUniqueId": "uid-door",
                    "hostUniqueId": "uid-wall",
                    "source": "revit_api",
                    "confidence": "high",
                }
            ],
            "roomMembership": [
                {
                    "elementUniqueId": "uid-door",
                    "roomUniqueId": "room-1",
                    "source": "revit_api",
                    "confidence": "high",
                }
            ],
            "levelMembership": [
                {
                    "elementUniqueId": "uid-wall",
                    "levelName": "L1",
                    "source": "revit_api",
                    "confidence": "high",
                },
                {
                    "elementUniqueId": "uid-door",
                    "levelName": "L1",
                    "source": "revit_api",
                    "confidence": "high",
                },
            ],
        },
    }


def test_module_constants():
    assert bim.PROJECTION_KIND == "bim_relationship_v1"
    assert bim.PROVENANCE == "rookbim_sidecar"
    assert bim.REL_HOSTED_BY == "revit_hosted_by"
    assert bim.REL_IN_ROOM == "revit_in_room"
    assert bim.REL_ON_LEVEL == "revit_on_level"
    assert bim.ENGINE_VERSION == 1


def test_parse_sidecar_payload_normalizes_real_export_shape():
    sidecar = bim.parse_sidecar_payload(_sidecar(), source_path="C:/tmp/shell.sidecar.json")

    assert sidecar.schema_version == 1
    assert sidecar.source_path == "C:/tmp/shell.sidecar.json"
    assert set(sidecar.elements_by_uid) == {"uid-wall", "uid-door"}
    assert sidecar.elements_by_uid["uid-door"].category == "Doors"
    assert sidecar.elements_by_uid["uid-door"].level == "L1"
    assert sidecar.rooms_by_uid["room-1"].display_name == "101 Office"
    assert sidecar.host_memberships[0].element_uid == "uid-door"
    assert sidecar.host_memberships[0].target_uid == "uid-wall"
    assert sidecar.room_memberships[0].target_uid == "room-1"
    assert sidecar.level_memberships[0].target_uid == "L1"


def test_parse_sidecar_payload_requires_enabled_sections():
    payload = _sidecar()
    del payload["relationships"]["roomMembership"]

    with pytest.raises(bim.BimProjectionValidationError) as exc:
        bim.parse_sidecar_payload(payload, include_rooms=True, include_levels=True)

    assert "roomMembership" in str(exc.value)


def test_parse_sidecar_payload_allows_disabled_room_section():
    payload = _sidecar()
    del payload["relationships"]["roomMembership"]

    sidecar = bim.parse_sidecar_payload(payload, include_rooms=False, include_levels=True)

    assert sidecar.room_memberships == []


def test_fingerprint_uses_file_content(tmp_path):
    path_a = tmp_path / "a.sidecar.json"
    path_b = tmp_path / "b.sidecar.json"
    path_a.write_text(json.dumps(_sidecar(), sort_keys=True), encoding="utf-8")
    path_b.write_text(json.dumps(_sidecar(), sort_keys=True), encoding="utf-8")

    fp_a = bim.fingerprint_sidecar_path(path_a)
    fp_b = bim.fingerprint_sidecar_path(path_b)

    assert fp_a == fp_b
    assert len(fp_a.short_id) == 16
    assert fp_a.full_hash
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_relationship_projection.py -q
```

Expected: FAIL with `ImportError` or `AttributeError` because `bim_relationship_projection.py` does not exist yet.

- [ ] **Step 3: Implement parser, dataclasses, validation, and fingerprint helpers**

Create `mcp_server/src/rook/scene/bim_relationship_projection.py`:

```python
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECTION_KIND = "bim_relationship_v1"
PROVENANCE = "rookbim_sidecar"
REL_HOSTED_BY = "revit_hosted_by"
REL_IN_ROOM = "revit_in_room"
REL_ON_LEVEL = "revit_on_level"
ENGINE_VERSION = 1

NODE_ATTRS = (
    "rookbimJoined",
    "rookbimSidecarFingerprint",
    "rookbimSidecarPath",
    "rookbimGraphSequence",
    "revitUniqueId",
    "revitElementId",
    "revitCategory",
    "revitFamily",
    "revitType",
    "revitName",
    "revitLevel",
    "revitRoomUniqueId",
    "revitHostUniqueId",
)


class BimProjectionValidationError(ValueError):
    """Raised when the sidecar shape is not valid for BIM relationship projection."""


@dataclass(frozen=True)
class SidecarFingerprint:
    full_hash: str
    short_id: str


@dataclass(frozen=True)
class BimElement:
    unique_id: str
    element_id: str
    category: str
    family: str
    type_name: str
    name: str
    level: str
    raw: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class BimRoom:
    unique_id: str
    room_number: str
    room_name: str
    display_name: str
    completeness: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class BimMembership:
    element_uid: str
    target_uid: str
    source: str
    confidence: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ParsedSidecar:
    schema_version: int | None
    source_path: str
    elements_by_uid: dict[str, BimElement]
    rooms_by_uid: dict[str, BimRoom]
    host_memberships: list[BimMembership]
    room_memberships: list[BimMembership]
    level_memberships: list[BimMembership]
    raw: dict[str, Any] = field(repr=False)


def _label_value(labels: dict[str, Any], name: str) -> str:
    entry = labels.get(name)
    if isinstance(entry, dict):
        value = entry.get("value")
        return "" if value is None else str(value)
    return "" if entry is None else str(entry)


def _clean_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _room_display_name(number: str, name: str, fallback_uid: str) -> str:
    if number and name:
        return f"{number} {name}"
    if number:
        return number
    if name:
        return name
    return f"Room {fallback_uid[:8]}"


def normalize_id_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return cleaned or "unnamed"


def fingerprint_sidecar_path(path: str | Path) -> SidecarFingerprint:
    data = Path(path).read_bytes()
    full_hash = hashlib.sha256(data).hexdigest()
    return SidecarFingerprint(full_hash=full_hash, short_id=full_hash[:16])


def _require_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise BimProjectionValidationError(f"sidecar field {key!r} must be a list")
    return value


def _require_relationship_list(relationships: dict[str, Any], key: str) -> list[Any]:
    value = relationships.get(key)
    if not isinstance(value, list):
        raise BimProjectionValidationError(f"relationships.{key} must be a list")
    return value


def parse_sidecar_payload(
    payload: dict[str, Any],
    *,
    source_path: str = "",
    include_rooms: bool = True,
    include_levels: bool = True,
) -> ParsedSidecar:
    elements = _require_list(payload, "elements")
    relationships = payload.get("relationships")
    if not isinstance(relationships, dict):
        raise BimProjectionValidationError("sidecar field 'relationships' must be an object")

    host_records = _require_relationship_list(relationships, "hostMembership")
    room_records = _require_relationship_list(relationships, "roomMembership") if include_rooms else []
    level_records = _require_relationship_list(relationships, "levelMembership") if include_levels else []

    elements_by_uid: dict[str, BimElement] = {}
    for record in elements:
        if not isinstance(record, dict):
            continue
        identity = record.get("identity") if isinstance(record.get("identity"), dict) else {}
        uid = _clean_str(identity.get("uniqueId") or record.get("uniqueId") or record.get("revitUniqueId"))
        if not uid:
            continue
        labels = record.get("labels") if isinstance(record.get("labels"), dict) else {}
        elements_by_uid[uid] = BimElement(
            unique_id=uid,
            element_id=_clean_str(identity.get("elementId") or record.get("elementId")),
            category=_clean_str(record.get("category")),
            family=_clean_str(record.get("family")),
            type_name=_clean_str(record.get("type")),
            name=_clean_str(record.get("name")),
            level=_label_value(labels, "level"),
            raw=record,
        )

    rooms_by_uid: dict[str, BimRoom] = {}
    rooms = payload.get("rooms", [])
    if isinstance(rooms, list):
        for record in rooms:
            if not isinstance(record, dict):
                continue
            uid = _clean_str(record.get("uniqueId") or record.get("roomId"))
            if not uid:
                continue
            number = _clean_str(record.get("number"))
            name = _clean_str(record.get("name"))
            rooms_by_uid[uid] = BimRoom(
                unique_id=uid,
                room_number=number,
                room_name=name,
                display_name=_room_display_name(number, name, uid),
                completeness="complete",
                raw=record,
            )

    return ParsedSidecar(
        schema_version=payload.get("schemaVersion"),
        source_path=source_path,
        elements_by_uid=elements_by_uid,
        rooms_by_uid=rooms_by_uid,
        host_memberships=_parse_memberships(host_records, "hostUniqueId"),
        room_memberships=_parse_memberships(room_records, "roomUniqueId"),
        level_memberships=_parse_memberships(level_records, "levelName"),
        raw=payload,
    )


def _parse_memberships(records: list[Any], target_key: str) -> list[BimMembership]:
    out: list[BimMembership] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        element_uid = _clean_str(record.get("elementUniqueId"))
        target_uid = _clean_str(record.get(target_key))
        if not element_uid or not target_uid:
            continue
        out.append(BimMembership(
            element_uid=element_uid,
            target_uid=target_uid,
            source=_clean_str(record.get("source")),
            confidence=_clean_str(record.get("confidence")),
            raw=record,
        ))
    return out


def load_sidecar_path(
    sidecar_path: str | Path,
    *,
    include_rooms: bool = True,
    include_levels: bool = True,
) -> tuple[ParsedSidecar, SidecarFingerprint]:
    path = Path(sidecar_path)
    if not path.is_file():
        raise BimProjectionValidationError(f"sidecar_path is not a file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BimProjectionValidationError(f"sidecar JSON is invalid: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise BimProjectionValidationError("sidecar root must be an object")
    return (
        parse_sidecar_payload(
            payload,
            source_path=str(path),
            include_rooms=include_rooms,
            include_levels=include_levels,
        ),
        fingerprint_sidecar_path(path),
    )
```

- [ ] **Step 4: Run parser tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_relationship_projection.py -q
```

Expected: PASS for the tests added in this task.

- [ ] **Step 5: Commit parser foundation**

Run:

```powershell
git add mcp_server/src/rook/scene/bim_relationship_projection.py mcp_server/tests/test_bim_relationship_projection.py
git commit -m "Add BIM relationship sidecar parser"
```

---

## Task 2: Runtime Join Records and Eligibility Filtering

**Files:**
- Modify: `mcp_server/src/rook/scene/bim_relationship_projection.py`
- Modify: `mcp_server/tests/test_bim_relationship_projection.py`

- [ ] **Step 1: Add failing tests for runtime joins and filters**

Append to `mcp_server/tests/test_bim_relationship_projection.py`:

```python
def test_build_runtime_join_map_extracts_revit_user_strings():
    records = [
        bim.RuntimeObjectRecord(
            object_id="rh-wall",
            user_strings={
                "revit.uniqueId": "uid-wall",
                "revit.elementId": "100",
                "revit.category": "Walls",
            },
        ),
        bim.RuntimeObjectRecord(
            object_id="rh-no-uid",
            user_strings={"revit.category": "Doors"},
        ),
    ]

    join = bim.build_runtime_join_map(records)

    assert join.by_revit_uid["uid-wall"].object_id == "rh-wall"
    assert join.by_object_id["rh-wall"].revit_category == "Walls"
    assert join.diagnostics["objectsMissingRevitUniqueId"] == 1


def test_select_eligible_objects_honors_object_ids_and_category_filters():
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = bim.build_runtime_join_map([
        bim.RuntimeObjectRecord("rh-wall", {"revit.uniqueId": "uid-wall", "revit.category": "Walls"}),
        bim.RuntimeObjectRecord("rh-door", {"revit.uniqueId": "uid-door", "revit.category": "Doors"}),
    ])

    eligible = bim.select_eligible_objects(
        join,
        sidecar,
        object_ids=["rh-door"],
        category_filters=["doors"],
    )

    assert eligible.object_ids == {"rh-door"}
    assert eligible.revit_uids == {"uid-door"}
    assert eligible.diagnostics == {}


def test_select_eligible_objects_uses_all_joinable_when_no_filters():
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = bim.build_runtime_join_map([
        bim.RuntimeObjectRecord("rh-wall", {"revit.uniqueId": "uid-wall", "revit.category": "Walls"}),
        bim.RuntimeObjectRecord("rh-door", {"revit.uniqueId": "uid-door", "revit.category": "Doors"}),
    ])

    eligible = bim.select_eligible_objects(join, sidecar)

    assert eligible.object_ids == {"rh-wall", "rh-door"}
    assert eligible.revit_uids == {"uid-wall", "uid-door"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_relationship_projection.py -q
```

Expected: FAIL with missing `RuntimeObjectRecord` / join-map helpers.

- [ ] **Step 3: Implement runtime records, join map, and filtering**

Add to `mcp_server/src/rook/scene/bim_relationship_projection.py`:

```python
@dataclass(frozen=True)
class RuntimeObjectRecord:
    object_id: str
    user_strings: dict[str, Any]


@dataclass(frozen=True)
class JoinedRuntimeObject:
    object_id: str
    revit_unique_id: str
    revit_element_id: str
    revit_category: str


@dataclass(frozen=True)
class RuntimeJoinMap:
    by_object_id: dict[str, JoinedRuntimeObject]
    by_revit_uid: dict[str, JoinedRuntimeObject]
    diagnostics: dict[str, int]


@dataclass(frozen=True)
class EligibleObjects:
    object_ids: set[str]
    revit_uids: set[str]
    diagnostics: dict[str, int]


def build_runtime_join_map(records: list[RuntimeObjectRecord]) -> RuntimeJoinMap:
    by_object_id: dict[str, JoinedRuntimeObject] = {}
    by_revit_uid: dict[str, JoinedRuntimeObject] = {}
    diagnostics: dict[str, int] = {}

    for record in records:
        uid = _clean_str(record.user_strings.get("revit.uniqueId"))
        if not uid:
            diagnostics["objectsMissingRevitUniqueId"] = diagnostics.get("objectsMissingRevitUniqueId", 0) + 1
            continue
        joined = JoinedRuntimeObject(
            object_id=record.object_id,
            revit_unique_id=uid,
            revit_element_id=_clean_str(record.user_strings.get("revit.elementId")),
            revit_category=_clean_str(record.user_strings.get("revit.category")),
        )
        by_object_id[record.object_id] = joined
        by_revit_uid[uid] = joined

    return RuntimeJoinMap(by_object_id=by_object_id, by_revit_uid=by_revit_uid, diagnostics=diagnostics)


def _category_matches(joined: JoinedRuntimeObject, sidecar: ParsedSidecar, filters: set[str]) -> bool:
    if not filters:
        return True
    element = sidecar.elements_by_uid.get(joined.revit_unique_id)
    candidates = {
        joined.revit_category.strip().lower(),
        (element.category.strip().lower() if element else ""),
    }
    return any(candidate in filters for candidate in candidates if candidate)


def select_eligible_objects(
    join: RuntimeJoinMap,
    sidecar: ParsedSidecar,
    *,
    object_ids: list[str] | None = None,
    category_filters: list[str] | None = None,
) -> EligibleObjects:
    requested = set(object_ids or join.by_object_id.keys())
    filters = {item.strip().lower() for item in (category_filters or []) if item and item.strip()}
    diagnostics: dict[str, int] = {}
    object_out: set[str] = set()
    uid_out: set[str] = set()

    for object_id in requested:
        joined = join.by_object_id.get(object_id)
        if joined is None:
            diagnostics["requestedObjectNotJoinable"] = diagnostics.get("requestedObjectNotJoinable", 0) + 1
            continue
        if joined.revit_unique_id not in sidecar.elements_by_uid:
            diagnostics["joinedObjectMissingFromSidecar"] = diagnostics.get("joinedObjectMissingFromSidecar", 0) + 1
            continue
        if not _category_matches(joined, sidecar, filters):
            diagnostics["filteredByCategory"] = diagnostics.get("filteredByCategory", 0) + 1
            continue
        object_out.add(object_id)
        uid_out.add(joined.revit_unique_id)

    return EligibleObjects(object_ids=object_out, revit_uids=uid_out, diagnostics=diagnostics)
```

- [ ] **Step 4: Run join/filter tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_relationship_projection.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit join/filter layer**

Run:

```powershell
git add mcp_server/src/rook/scene/bim_relationship_projection.py mcp_server/tests/test_bim_relationship_projection.py
git commit -m "Add BIM runtime join filtering"
```

---

## Task 3: Pure Projection Upsert for Host, Room, and Level Facts

**Files:**
- Modify: `mcp_server/src/rook/scene/bim_relationship_projection.py`
- Modify: `mcp_server/tests/test_bim_relationship_projection.py`

- [ ] **Step 1: Add failing projection tests**

Append:

```python
from rook.scene.scene_graph import SceneGraphAnalytics


def _analytics_with_bim_nodes() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node("rh-wall", name="Wall", domain_label="wall", shape_class="vertical-planar")
    sg.graph.add_node("rh-door", name="Door", domain_label="door", shape_class="compact")
    sg._sequence = 9
    return sg


def _joined_for_projection():
    return bim.build_runtime_join_map([
        bim.RuntimeObjectRecord("rh-wall", {"revit.uniqueId": "uid-wall", "revit.elementId": "100", "revit.category": "Walls"}),
        bim.RuntimeObjectRecord("rh-door", {"revit.uniqueId": "uid-door", "revit.elementId": "200", "revit.category": "Doors"}),
    ])


def test_project_bim_relationships_upserts_nodes_edges_and_annotations():
    sg = _analytics_with_bim_nodes()
    sidecar = bim.parse_sidecar_payload(_sidecar(), source_path="C:/tmp/shell.sidecar.json")
    join = _joined_for_projection()
    eligible = bim.select_eligible_objects(join, sidecar)
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")

    result = bim.project_bim_relationships(
        sg,
        sidecar,
        fp,
        join,
        eligible,
        include_rooms=True,
        include_levels=True,
    )

    assert result["counts"]["annotatedObjectCount"] == 2
    assert result["counts"]["projectedHostEdges"] == 1
    assert result["counts"]["projectedRoomEdges"] == 1
    assert result["counts"]["projectedLevelEdges"] == 2
    assert sg.graph.nodes["rh-door"]["revitUniqueId"] == "uid-door"
    assert sg.graph.nodes["rh-door"]["revitCategory"] == "Doors"

    host_key = "rookbim:hosted_by:abcdefabcdefabcd:uid-door:uid-wall"
    assert sg.graph["rh-door"]["rh-wall"][host_key]["relationship"] == "revit_hosted_by"
    assert sg.graph["rh-door"]["rh-wall"][host_key]["projectionKind"] == bim.PROJECTION_KIND

    room_id = "rookbim:abcdefabcdefabcd:room:room-1"
    assert sg.graph.nodes[room_id]["nodeKind"] == "rookbim_room"
    assert sg.graph.nodes[room_id]["displayName"] == "101 Office"

    level_id = "rookbim:abcdefabcdefabcd:level:L1"
    assert sg.graph.nodes[level_id]["nodeKind"] == "rookbim_level"
    assert sg.graph.has_edge("rh-door", level_id, "rookbim:on_level:abcdefabcdefabcd:uid-door:L1")


def test_project_bim_relationships_is_idempotent_for_same_inputs():
    sg = _analytics_with_bim_nodes()
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = _joined_for_projection()
    eligible = bim.select_eligible_objects(join, sidecar)
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")

    bim.project_bim_relationships(sg, sidecar, fp, join, eligible)
    first_edges = sg.graph.number_of_edges()
    second = bim.project_bim_relationships(sg, sidecar, fp, join, eligible)

    assert sg.graph.number_of_edges() == first_edges
    assert second["counts"]["roomNodes"] == 1
    assert second["counts"]["levelNodes"] == 1
    assert second["counts"]["createdRoomNodes"] == 0
    assert second["counts"]["createdLevelNodes"] == 0


def test_host_edge_requires_host_present_but_not_eligible():
    sg = _analytics_with_bim_nodes()
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = _joined_for_projection()
    eligible = bim.select_eligible_objects(join, sidecar, object_ids=["rh-door"])
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")

    result = bim.project_bim_relationships(sg, sidecar, fp, join, eligible)

    assert result["counts"]["eligibleObjectCount"] == 1
    assert result["counts"]["projectedHostEdges"] == 1
    assert sg.graph.has_edge("rh-door", "rh-wall", "rookbim:hosted_by:abcdefabcdefabcd:uid-door:uid-wall")


def test_sparse_room_node_is_created_when_room_record_missing():
    payload = _sidecar()
    payload["rooms"] = []
    sidecar = bim.parse_sidecar_payload(payload)
    sg = _analytics_with_bim_nodes()
    join = _joined_for_projection()
    eligible = bim.select_eligible_objects(join, sidecar, object_ids=["rh-door"])
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")

    result = bim.project_bim_relationships(sg, sidecar, fp, join, eligible)

    room_id = "rookbim:abcdefabcdefabcd:room:room-1"
    assert sg.graph.nodes[room_id]["recordCompleteness"] == "sparse"
    assert result["diagnostics"]["roomReferenceMissingRecord"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_relationship_projection.py -q
```

Expected: FAIL with missing `project_bim_relationships`.

- [ ] **Step 3: Implement projection upsert**

Add these helpers and projection function:

```python
import networkx as nx

from .scene_graph import SceneGraphAnalytics


def _base_projection_attrs(sidecar: ParsedSidecar, fp: SidecarFingerprint, graph_sequence: int) -> dict[str, Any]:
    return {
        "provenance": PROVENANCE,
        "projectionKind": PROJECTION_KIND,
        "sourceSidecarPath": sidecar.source_path,
        "sidecarFingerprint": fp.short_id,
        "sidecarHash": fp.full_hash,
        "graphSequence": graph_sequence,
        "engineVersion": ENGINE_VERSION,
    }


def room_node_id(fp: SidecarFingerprint, room_uid: str) -> str:
    return f"rookbim:{fp.short_id}:room:{normalize_id_segment(room_uid)}"


def level_node_id(fp: SidecarFingerprint, level_name: str) -> str:
    return f"rookbim:{fp.short_id}:level:{normalize_id_segment(level_name)}"


def host_edge_key(fp: SidecarFingerprint, element_uid: str, host_uid: str) -> str:
    return f"rookbim:hosted_by:{fp.short_id}:{element_uid}:{host_uid}"


def room_edge_key(fp: SidecarFingerprint, element_uid: str, room_uid: str) -> str:
    return f"rookbim:in_room:{fp.short_id}:{element_uid}:{room_uid}"


def level_edge_key(fp: SidecarFingerprint, element_uid: str, level_name: str) -> str:
    return f"rookbim:on_level:{fp.short_id}:{element_uid}:{normalize_id_segment(level_name)}"


def _bump(counter: dict[str, int], key: str, amount: int = 1) -> None:
    counter[key] = counter.get(key, 0) + amount


def _annotate_joined_node(
    graph: nx.MultiDiGraph,
    object_id: str,
    element: BimElement,
    sidecar: ParsedSidecar,
    fp: SidecarFingerprint,
    graph_sequence: int,
) -> None:
    graph.nodes[object_id].update({
        "rookbimJoined": True,
        "rookbimSidecarFingerprint": fp.short_id,
        "rookbimSidecarPath": sidecar.source_path,
        "rookbimGraphSequence": graph_sequence,
        "revitUniqueId": element.unique_id,
        "revitElementId": element.element_id,
        "revitCategory": element.category,
        "revitFamily": element.family,
        "revitType": element.type_name,
        "revitName": element.name,
        "revitLevel": element.level,
    })


def _ensure_room_node(
    graph: nx.MultiDiGraph,
    sidecar: ParsedSidecar,
    fp: SidecarFingerprint,
    graph_sequence: int,
    room_uid: str,
    diagnostics: dict[str, int],
) -> tuple[str, bool]:
    node_id = room_node_id(fp, room_uid)
    created = not graph.has_node(node_id)
    attrs = _base_projection_attrs(sidecar, fp, graph_sequence)
    room = sidecar.rooms_by_uid.get(room_uid)
    if room is None:
        _bump(diagnostics, "roomReferenceMissingRecord")
        attrs.update({
            "nodeKind": "rookbim_room",
            "roomUniqueId": room_uid,
            "displayName": f"Room {room_uid[:8]}",
            "recordCompleteness": "sparse",
            "diagnostics": ["roomReferenceMissingRecord"],
            "name": f"Room {room_uid[:8]}",
            "domain_label": "room",
            "shape_class": "bim-reference",
        })
    else:
        attrs.update({
            "nodeKind": "rookbim_room",
            "roomUniqueId": room.unique_id,
            "roomNumber": room.room_number,
            "roomName": room.room_name,
            "displayName": room.display_name,
            "recordCompleteness": room.completeness,
            "name": room.display_name,
            "domain_label": "room",
            "shape_class": "bim-reference",
        })
    graph.add_node(node_id, **attrs)
    return node_id, created


def _ensure_level_node(
    graph: nx.MultiDiGraph,
    sidecar: ParsedSidecar,
    fp: SidecarFingerprint,
    graph_sequence: int,
    level_name: str,
) -> tuple[str, bool]:
    node_id = level_node_id(fp, level_name)
    created = not graph.has_node(node_id)
    attrs = _base_projection_attrs(sidecar, fp, graph_sequence)
    attrs.update({
        "nodeKind": "rookbim_level",
        "levelName": level_name,
        "displayName": level_name,
        "recordCompleteness": "membership_only",
        "name": level_name,
        "domain_label": "level",
        "shape_class": "bim-reference",
    })
    graph.add_node(node_id, **attrs)
    return node_id, created


def project_bim_relationships(
    analytics: SceneGraphAnalytics,
    sidecar: ParsedSidecar,
    fp: SidecarFingerprint,
    join: RuntimeJoinMap,
    eligible: EligibleObjects,
    *,
    include_rooms: bool = True,
    include_levels: bool = True,
) -> dict[str, Any]:
    graph = analytics.graph
    diagnostics: dict[str, int] = dict(join.diagnostics)
    for key, value in eligible.diagnostics.items():
        diagnostics[key] = diagnostics.get(key, 0) + value

    counts = {
        "candidateObjectCount": len(join.by_object_id),
        "joinableCount": len(join.by_object_id),
        "eligibleObjectCount": len(eligible.object_ids),
        "joinedObjectCount": len(eligible.object_ids),
        "annotatedObjectCount": 0,
        "projectedHostEdges": 0,
        "projectedRoomEdges": 0,
        "projectedLevelEdges": 0,
        "roomNodes": 0,
        "levelNodes": 0,
        "createdRoomNodes": 0,
        "createdLevelNodes": 0,
        "skippedHostMissingHostedObject": 0,
        "skippedHostMissingHostObject": 0,
        "skippedHostBothMissing": 0,
    }

    for object_id in sorted(eligible.object_ids):
        joined = join.by_object_id[object_id]
        element = sidecar.elements_by_uid[joined.revit_unique_id]
        _annotate_joined_node(graph, object_id, element, sidecar, fp, analytics.sequence)
        counts["annotatedObjectCount"] += 1

    base = _base_projection_attrs(sidecar, fp, analytics.sequence)
    touched_room_nodes: set[str] = set()
    touched_level_nodes: set[str] = set()

    for rel in sidecar.host_memberships:
        hosted = join.by_revit_uid.get(rel.element_uid)
        host = join.by_revit_uid.get(rel.target_uid)
        hosted_eligible = rel.element_uid in eligible.revit_uids
        if not hosted_eligible and host is None:
            counts["skippedHostBothMissing"] += 1
            continue
        if not hosted_eligible:
            counts["skippedHostMissingHostedObject"] += 1
            continue
        if host is None:
            counts["skippedHostMissingHostObject"] += 1
            _bump(diagnostics, "hostTargetNotInScene")
            continue
        graph.add_edge(
            hosted.object_id,
            host.object_id,
            key=host_edge_key(fp, rel.element_uid, rel.target_uid),
            **base,
            relationship=REL_HOSTED_BY,
            sourceRevitUniqueId=rel.element_uid,
            targetRevitUniqueId=rel.target_uid,
            source=rel.source,
            confidence=rel.confidence,
        )
        counts["projectedHostEdges"] += 1

    if include_rooms:
        for rel in sidecar.room_memberships:
            joined = join.by_revit_uid.get(rel.element_uid)
            if joined is None or rel.element_uid not in eligible.revit_uids:
                continue
            node_id, created = _ensure_room_node(graph, sidecar, fp, analytics.sequence, rel.target_uid, diagnostics)
            touched_room_nodes.add(node_id)
            if created:
                counts["createdRoomNodes"] += 1
            graph.add_edge(
                joined.object_id,
                node_id,
                key=room_edge_key(fp, rel.element_uid, rel.target_uid),
                **base,
                relationship=REL_IN_ROOM,
                sourceRevitUniqueId=rel.element_uid,
                roomUniqueId=rel.target_uid,
                source=rel.source,
                confidence=rel.confidence,
            )
            counts["projectedRoomEdges"] += 1

    if include_levels:
        for rel in sidecar.level_memberships:
            joined = join.by_revit_uid.get(rel.element_uid)
            if joined is None or rel.element_uid not in eligible.revit_uids:
                continue
            node_id, created = _ensure_level_node(graph, sidecar, fp, analytics.sequence, rel.target_uid)
            touched_level_nodes.add(node_id)
            if created:
                counts["createdLevelNodes"] += 1
            graph.add_edge(
                joined.object_id,
                node_id,
                key=level_edge_key(fp, rel.element_uid, rel.target_uid),
                **base,
                relationship=REL_ON_LEVEL,
                sourceRevitUniqueId=rel.element_uid,
                levelName=rel.target_uid,
                source=rel.source,
                confidence=rel.confidence,
            )
            counts["projectedLevelEdges"] += 1

    counts["roomNodes"] = len(touched_room_nodes)
    counts["levelNodes"] = len(touched_level_nodes)
    analytics._invalidate_caches()

    return {
        "success": True,
        "projectionKind": PROJECTION_KIND,
        "provenance": PROVENANCE,
        "graphSequence": analytics.sequence,
        "sidecarPath": sidecar.source_path,
        "sidecarFingerprint": fp.short_id,
        "pruned": False,
        "upserted": True,
        "counts": counts,
        "diagnostics": diagnostics,
        "samples": {},
    }
```

- [ ] **Step 4: Run projection tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_relationship_projection.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit projection core**

Run:

```powershell
git add mcp_server/src/rook/scene/bim_relationship_projection.py mcp_server/tests/test_bim_relationship_projection.py
git commit -m "Project BIM relationships into scene graph"
```

---

## Task 4: Projector-Owned Pruning and Disabled Relationship Families

**Files:**
- Modify: `mcp_server/src/rook/scene/bim_relationship_projection.py`
- Modify: `mcp_server/tests/test_bim_relationship_projection.py`

- [ ] **Step 1: Add failing tests for pruning and disabled rooms/levels**

Append:

```python
def test_prune_removes_only_bim_relationship_v1_artifacts():
    sg = _analytics_with_bim_nodes()
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = _joined_for_projection()
    eligible = bim.select_eligible_objects(join, sidecar)
    bim.project_bim_relationships(sg, sidecar, fp, join, eligible)
    sg.graph.add_edge("rh-door", "rh-wall", key="future:bim", relationship="future_bim", provenance="rookbim_sidecar")

    result = bim.prune_bim_relationship_projection(sg)

    assert result["pruned"] is True
    assert sg.graph.has_edge("rh-door", "rh-wall", "future:bim")
    assert not sg.graph.has_edge("rh-door", "rh-wall", "rookbim:hosted_by:abcdefabcdefabcd:uid-door:uid-wall")
    assert "revitUniqueId" not in sg.graph.nodes["rh-door"]


def test_project_can_skip_room_and_level_families():
    sg = _analytics_with_bim_nodes()
    sidecar = bim.parse_sidecar_payload(_sidecar(), include_rooms=False, include_levels=False)
    join = _joined_for_projection()
    eligible = bim.select_eligible_objects(join, sidecar)
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")

    result = bim.project_bim_relationships(
        sg,
        sidecar,
        fp,
        join,
        eligible,
        include_rooms=False,
        include_levels=False,
    )

    assert result["counts"]["projectedHostEdges"] == 1
    assert result["counts"]["projectedRoomEdges"] == 0
    assert result["counts"]["projectedLevelEdges"] == 0
    assert not any(attrs.get("nodeKind") in {"rookbim_room", "rookbim_level"} for _, attrs in sg.graph.nodes(data=True))


def test_projection_requires_prune_only_for_changed_sequence_or_sidecar():
    sg = _analytics_with_bim_nodes()
    fp = bim.SidecarFingerprint(full_hash="abcdef" * 11, short_id="abcdefabcdefabcd")
    sidecar = bim.parse_sidecar_payload(_sidecar())
    join = _joined_for_projection()
    eligible = bim.select_eligible_objects(join, sidecar)
    bim.project_bim_relationships(sg, sidecar, fp, join, eligible)

    assert bim.projection_requires_prune(sg, fp) is False

    other_fp = bim.SidecarFingerprint(full_hash="123456" * 11, short_id="1234561234561234")
    assert bim.projection_requires_prune(sg, other_fp) is True

    sg._sequence = 10
    assert bim.projection_requires_prune(sg, fp) is True
```

- [ ] **Step 2: Run tests to verify pruning failures**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_relationship_projection.py -q
```

Expected: FAIL with missing `prune_bim_relationship_projection`.

- [ ] **Step 3: Implement projector-owned pruning**

Add:

```python
def _is_projection_edge(attrs: dict[str, Any]) -> bool:
    return attrs.get("projectionKind") == PROJECTION_KIND


def _is_projection_node(attrs: dict[str, Any]) -> bool:
    return attrs.get("projectionKind") == PROJECTION_KIND and attrs.get("nodeKind") in {"rookbim_room", "rookbim_level"}


def _projection_artifact_attrs(analytics: SceneGraphAnalytics) -> list[dict[str, Any]]:
    graph = analytics.graph
    attrs: list[dict[str, Any]] = []
    attrs.extend(data for _, _, _, data in graph.edges(keys=True, data=True) if _is_projection_edge(data))
    attrs.extend(data for _, data in graph.nodes(data=True) if _is_projection_node(data))
    attrs.extend(
        data
        for _, data in graph.nodes(data=True)
        if data.get("rookbimJoined") is True and data.get("rookbimSidecarFingerprint")
    )
    return attrs


def projection_requires_prune(analytics: SceneGraphAnalytics, fp: SidecarFingerprint) -> bool:
    for attrs in _projection_artifact_attrs(analytics):
        artifact_fingerprint = attrs.get("sidecarFingerprint") or attrs.get("rookbimSidecarFingerprint")
        artifact_sequence = attrs.get("graphSequence") or attrs.get("rookbimGraphSequence")
        if artifact_fingerprint != fp.short_id:
            return True
        if artifact_sequence != analytics.sequence:
            return True
    return False


def prune_bim_relationship_projection(analytics: SceneGraphAnalytics) -> dict[str, Any]:
    graph = analytics.graph
    removed_edges = 0
    removed_nodes = 0
    cleaned_annotations = 0

    for u, v, key, attrs in list(graph.edges(keys=True, data=True)):
        if _is_projection_edge(attrs):
            graph.remove_edge(u, v, key=key)
            removed_edges += 1

    for node_id, attrs in list(graph.nodes(data=True)):
        if _is_projection_node(attrs):
            graph.remove_node(node_id)
            removed_nodes += 1
            continue
        if attrs.get("rookbimJoined") is True and attrs.get("rookbimSidecarFingerprint"):
            for key in NODE_ATTRS:
                attrs.pop(key, None)
            cleaned_annotations += 1

    if removed_edges or removed_nodes or cleaned_annotations:
        analytics._invalidate_caches()

    return {
        "pruned": bool(removed_edges or removed_nodes or cleaned_annotations),
        "removedEdges": removed_edges,
        "removedNodes": removed_nodes,
        "cleanedAnnotations": cleaned_annotations,
    }
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_relationship_projection.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit pruning behavior**

Run:

```powershell
git add mcp_server/src/rook/scene/bim_relationship_projection.py mcp_server/tests/test_bim_relationship_projection.py
git commit -m "Add BIM projection pruning"
```

---

## Task 5: Scene Context Formatting for BIM Relationships

**Files:**
- Modify: `mcp_server/src/rook/scene/scene_graph.py`
- Modify: `mcp_server/tests/test_scene_graph.py`

- [ ] **Step 1: Add failing context-formatting tests**

Append to `mcp_server/tests/test_scene_graph.py`:

```python
def test_context_formats_bim_relationships_readably():
    sg = SceneGraphAnalytics()
    sg.graph.add_node("door", name="Door", domain_label="door", shape_class="compact")
    sg.graph.add_node("wall", name="Wall", domain_label="wall", shape_class="vertical-planar")
    sg.graph.add_node(
        "room",
        name="101 Office",
        displayName="101 Office",
        nodeKind="rookbim_room",
        domain_label="room",
        shape_class="bim-reference",
    )
    sg.graph.add_node(
        "level",
        name="L1",
        displayName="L1",
        nodeKind="rookbim_level",
        domain_label="level",
        shape_class="bim-reference",
    )
    sg.graph.add_edge("door", "wall", key="rookbim:hosted_by:fp:uid-door:uid-wall", relationship="revit_hosted_by", provenance="rookbim_sidecar")
    sg.graph.add_edge("door", "room", key="rookbim:in_room:fp:uid-door:room-1", relationship="revit_in_room", provenance="rookbim_sidecar")
    sg.graph.add_edge("door", "level", key="rookbim:on_level:fp:uid-door:L1", relationship="revit_on_level", provenance="rookbim_sidecar")

    text = sg.get_context(["door", "wall"])

    assert 'Hosted by Revit: WALL "Wall"' in text
    assert 'In Revit room: ROOM "101 Office"' in text
    assert 'On Revit level: LEVEL "L1"' in text
    assert 'Revit host for: DOOR "Door"' in text
```

- [ ] **Step 2: Run context test to verify failure**

Run:

```powershell
python -m pytest mcp_server/tests/test_scene_graph.py::test_context_formats_bim_relationships_readably -q
```

Expected: FAIL because labels are raw relationship names.

- [ ] **Step 3: Update context relationship labels and display names**

Modify the helper maps in `mcp_server/src/rook/scene/scene_graph.py`:

```python
_INVERSE_RELS = {
    "contains": "within",
    "supports": "supported by",
    "above": "below",
    "intersects": "intersects",
    "adjacent": "adjacent to",
    "adjacent_exact": "adjacent to (exact)",
    "near": "near",
    "contains_semantic": "within (semantic)",
    "revit_hosted_by": "Revit host for",
    "revit_in_room": "Contains Revit room member",
    "revit_on_level": "Has Revit level member",
}

_FORWARD_RELS = {
    "adjacent_exact": "adjacent to (exact)",
    "contains_semantic": "contains (semantic)",
    "revit_hosted_by": "Hosted by Revit",
    "revit_in_room": "In Revit room",
    "revit_on_level": "On Revit level",
}
```

Then update `_format_node()` target/source name selection:

```python
t_name = t_attrs.get("displayName") or t_attrs.get("name") or target[:8]
```

and:

```python
s_name = s_attrs.get("displayName") or s_attrs.get("name") or source[:8]
```

- [ ] **Step 4: Run scene graph tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_scene_graph.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit context formatting**

Run:

```powershell
git add mcp_server/src/rook/scene/scene_graph.py mcp_server/tests/test_scene_graph.py
git commit -m "Render BIM relationships in scene context"
```

---

## Task 6: MCP Tool Boundary, Hydration, Dispatch, and Targeting

**Files:**
- Modify: `mcp_server/src/rook/scene/bim_relationship_projection.py`
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Create: `mcp_server/tests/test_bim_relationship_projection_tool.py`

- [ ] **Step 1: Add failing tool-boundary tests**

Create `mcp_server/tests/test_bim_relationship_projection_tool.py`:

```python
import pytest

from rook import targeting
from rook.agent import tool_groups


def test_tool_group_contains_bim_relationship_projection():
    assert "scene_project_bim_relationships" in tool_groups.TOOL_GROUPS["scene_graph"]


def test_targeting_treats_bim_relationship_projection_as_rhino_read():
    policy = targeting.policy_for_tool("scene_project_bim_relationships")

    assert policy.requires_rhino is True
    assert policy.risk == "read"


@pytest.mark.asyncio
async def test_server_tool_schema_exposes_bim_relationship_projection():
    from rook import server

    tools = await server.list_tools()
    tool = next(t for t in tools if t.name == "scene_project_bim_relationships")

    props = tool.inputSchema["properties"]
    assert set(["sidecar_path", "object_ids", "category_filters", "include_rooms", "include_levels"]).issubset(props)
    assert tool.inputSchema["required"] == ["sidecar_path"]


@pytest.mark.asyncio
async def test_projector_tool_hydrates_userstrings_and_projects(monkeypatch, tmp_path):
    from rook.scene import bim_relationship_projection as bim
    from rook.scene.scene_graph import SceneGraphAnalytics

    sidecar_path = tmp_path / "fixture.sidecar.json"
    sidecar_path.write_text(
        bim.json.dumps({
            "schemaVersion": 1,
            "elements": [
                {"identity": {"uniqueId": "uid-wall", "elementId": 100}, "category": "Walls", "labels": {"level": {"value": "L1"}}},
                {"identity": {"uniqueId": "uid-door", "elementId": 200}, "category": "Doors", "labels": {"level": {"value": "L1"}}},
            ],
            "rooms": [],
            "relationships": {
                "hostMembership": [{"elementUniqueId": "uid-door", "hostUniqueId": "uid-wall"}],
                "roomMembership": [],
                "levelMembership": [
                    {"elementUniqueId": "uid-wall", "levelName": "L1"},
                    {"elementUniqueId": "uid-door", "levelName": "L1"},
                ],
            },
        }),
        encoding="utf-8",
    )

    sg = SceneGraphAnalytics()
    sg.graph.add_node("rh-wall", name="Wall")
    sg.graph.add_node("rh-door", name="Door")
    sg._sequence = 4

    async def fake_sync(port=None):
        return {"synced": True, "sequence": 4}

    async def fake_call_rhino(route, method="GET", data=None, port=None):
        assert route == "/usertext/object-get"
        object_id = data["id"]
        user_strings = {
            "rh-wall": {"revit.uniqueId": "uid-wall", "revit.elementId": "100", "revit.category": "Walls"},
            "rh-door": {"revit.uniqueId": "uid-door", "revit.elementId": "200", "revit.category": "Doors"},
        }[object_id]
        return {"success": True, "data": {"id": object_id, "userStrings": user_strings}}

    sg.sync = fake_sync
    monkeypatch.setattr(bim, "call_rhino", fake_call_rhino)

    payload = await bim.project_bim_relationships_for_tool(
        sidecar_path=str(sidecar_path),
        analytics=sg,
        object_ids=None,
        category_filters=None,
        include_rooms=True,
        include_levels=True,
        port=9999,
    )

    assert payload["success"] is True
    assert payload["counts"]["hydratedCount"] == 2
    assert payload["counts"]["projectedHostEdges"] == 1
    assert payload["counts"]["projectedLevelEdges"] == 2

    focused = await bim.project_bim_relationships_for_tool(
        sidecar_path=str(sidecar_path),
        analytics=sg,
        object_ids=["rh-door"],
        category_filters=None,
        include_rooms=True,
        include_levels=True,
        port=9999,
    )

    assert focused["success"] is True
    assert focused["pruned"] is False
    level_id = f"rookbim:{focused['sidecarFingerprint']}:level:L1"
    assert sg.graph.has_edge("rh-wall", level_id, f"rookbim:on_level:{focused['sidecarFingerprint']}:uid-wall:L1")
```

- [ ] **Step 2: Run tool tests to verify failure**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_relationship_projection_tool.py -q
```

Expected: FAIL on missing tool registration and `project_bim_relationships_for_tool`.

- [ ] **Step 3: Implement tool orchestration helper**

Add to `bim_relationship_projection.py`:

```python
from ..bridge import call_rhino
from .scene_graph import SceneGraphAnalytics, get_scene_graph


async def _hydrate_user_strings(object_id: str, *, port: int | None = None) -> tuple[RuntimeObjectRecord | None, str | None]:
    result = await call_rhino("/usertext/object-get", "POST", {"id": object_id}, port=port)
    if not result.get("success"):
        return None, "hydrationFailed"
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    user_strings = data.get("userStrings")
    if not isinstance(user_strings, dict):
        user_strings = {}
    return RuntimeObjectRecord(object_id=object_id, user_strings=user_strings), None


async def project_bim_relationships_for_tool(
    *,
    sidecar_path: str,
    analytics: SceneGraphAnalytics | None = None,
    object_ids: list[str] | None = None,
    category_filters: list[str] | None = None,
    include_rooms: bool = True,
    include_levels: bool = True,
    port: int | None = None,
) -> dict[str, Any]:
    sg = analytics or get_scene_graph()
    await sg.sync(port=port)
    sidecar, fp = load_sidecar_path(sidecar_path, include_rooms=include_rooms, include_levels=include_levels)

    candidate_ids = list(object_ids or sg.graph.nodes)
    records: list[RuntimeObjectRecord] = []
    diagnostics: dict[str, int] = {}
    for object_id in candidate_ids:
        record, error = await _hydrate_user_strings(object_id, port=port)
        if error:
            _bump(diagnostics, error)
            continue
        if record is not None:
            records.append(record)

    join = build_runtime_join_map(records)
    for key, value in diagnostics.items():
        join.diagnostics[key] = join.diagnostics.get(key, 0) + value
    eligible = select_eligible_objects(
        join,
        sidecar,
        object_ids=object_ids,
        category_filters=category_filters,
    )
    if not eligible.object_ids:
        return {
            "success": False,
            "error": "No scene objects joined to the BIM sidecar by revit.uniqueId.",
            "projectionKind": PROJECTION_KIND,
            "provenance": PROVENANCE,
            "graphSequence": sg.sequence,
            "sidecarPath": sidecar.source_path,
            "sidecarFingerprint": fp.short_id,
            "counts": {
                "candidateObjectCount": len(candidate_ids),
                "hydratedCount": len(records),
                "joinableCount": len(join.by_object_id),
                "eligibleObjectCount": 0,
                "joinedObjectCount": 0,
            },
            "diagnostics": {**join.diagnostics, **eligible.diagnostics},
            "samples": {},
        }

    prune_result = {"pruned": False, "removedEdges": 0, "removedNodes": 0, "cleanedAnnotations": 0}
    if projection_requires_prune(sg, fp):
        prune_result = prune_bim_relationship_projection(sg)
    payload = project_bim_relationships(
        sg,
        sidecar,
        fp,
        join,
        eligible,
        include_rooms=include_rooms,
        include_levels=include_levels,
    )
    payload["pruned"] = prune_result["pruned"]
    payload["counts"]["candidateObjectCount"] = len(candidate_ids)
    payload["counts"]["hydratedCount"] = len(records)
    return payload
```

- [ ] **Step 4: Register MCP tool in `server.py`**

Add a `Tool(...)` entry near `scene_refine_containment`:

```python
Tool(
    name="scene_project_bim_relationships",
    description="""Project RookBIM sidecar host/room/level relationships into the Python scene graph mirror.

This is a read-model enrichment only: it syncs and reads the current Rhino scene plus object user strings, then mutates only the in-memory Python networkx mirror. It does not mutate Rhino or Revit documents.""",
    inputSchema={
        "type": "object",
        "properties": {
            "sidecar_path": {"type": "string", "description": "Absolute path to a RookBIM .sidecar.json export artifact"},
            "object_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional scene object ids eligible as primary projected objects"},
            "category_filters": {"type": "array", "items": {"type": "string"}, "description": "Optional Revit category display names to include"},
            "include_rooms": {"type": "boolean", "description": "Project room reference nodes and revit_in_room edges (default true)"},
            "include_levels": {"type": "boolean", "description": "Project level reference nodes and revit_on_level edges (default true)"},
            "port": {"type": "integer", "description": "Rhino instance port"},
        },
        "required": ["sidecar_path"],
    },
)
```

Add a dispatch case near the other scene cases:

```python
case "scene_project_bim_relationships":
    from .scene.bim_relationship_projection import (
        BimProjectionValidationError,
        project_bim_relationships_for_tool,
    )
    try:
        payload = await project_bim_relationships_for_tool(
            sidecar_path=arguments.get("sidecar_path", ""),
            object_ids=arguments.get("object_ids"),
            category_filters=arguments.get("category_filters"),
            include_rooms=arguments.get("include_rooms", True),
            include_levels=arguments.get("include_levels", True),
            port=port,
        )
        result = {"success": payload.get("success", True), "data": payload}
    except BimProjectionValidationError as exc:
        result = {"success": False, "data": {"code": "bim_projection_invalid_sidecar", "message": str(exc)}}
```

- [ ] **Step 5: Register local tool dispatcher**

Add to `mcp_server/src/rook/agent/tool_dispatcher.py` near scene tools:

```python
    # --- scene_project_bim_relationships (Python-side RookBIM sidecar projection) ---
    try:
        from ..scene.bim_relationship_projection import project_bim_relationships_for_tool

        async def _scene_project_bim_relationships(
            sidecar_path: str = "",
            object_ids=None,
            category_filters=None,
            include_rooms: bool = True,
            include_levels: bool = True,
            port: int | None = None,
            **kwargs,
        ) -> dict:
            payload = await project_bim_relationships_for_tool(
                sidecar_path=sidecar_path,
                object_ids=object_ids,
                category_filters=category_filters,
                include_rooms=include_rooms,
                include_levels=include_levels,
                port=port,
            )
            return {"success": payload.get("success", True), "data": payload}

        tools["scene_project_bim_relationships"] = _scene_project_bim_relationships
    except ImportError:
        logger.debug("scene_project_bim_relationships local tool unavailable (import failed)")
```

- [ ] **Step 6: Register tool group and targeting**

In `mcp_server/src/rook/agent/tool_groups.py`, add `"scene_project_bim_relationships"` to the
`"scene_graph"` group next to `scene_exact_neighbors` and `scene_refine_containment`.

In `mcp_server/src/rook/targeting.py`, add `"scene_project_bim_relationships"` to `_ALL_KNOWN_TOOLS`
and `_RHINO_READ_TOOLS`. Do not add it to mutate tool sets.

- [ ] **Step 7: Run tool registration tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_relationship_projection_tool.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit tool boundary**

Run:

```powershell
git add mcp_server/src/rook/scene/bim_relationship_projection.py mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/targeting.py mcp_server/tests/test_bim_relationship_projection_tool.py
git commit -m "Add BIM relationship projection scene tool"
```

---

## Task 7: Invariant Guards and Live-Gated Wiring Test

**Files:**
- Modify: `mcp_server/tests/test_bim_relationship_projection.py`
- Create: `mcp_server/tests/test_live_bim_relationship_projection.py`

- [ ] **Step 1: Add source-text invariant guards**

Append to `mcp_server/tests/test_bim_relationship_projection.py`:

```python
from pathlib import Path


def test_bim_projector_does_not_call_inference_or_mutating_routes():
    source = Path("mcp_server/src/rook/scene/bim_relationship_projection.py").read_text(encoding="utf-8")

    assert "scene_exact_neighbors" not in source
    assert "scene_refine_containment" not in source
    assert "/scene/graph/adjacency/exact" not in source
    assert "/bim/" not in source
    assert "/usertext/object-set" not in source
    assert "/usertext/object-delete" not in source
    assert "/document/save" not in source
```

- [ ] **Step 2: Add live-gated wiring test**

Create `mcp_server/tests/test_live_bim_relationship_projection.py`:

```python
from pathlib import Path

import pytest

from rook.bridge import call_rhino, discover_instances
from rook.scene.bim_relationship_projection import project_bim_relationships_for_tool
from rook.scene.scene_graph import get_scene_graph

pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

FIXTURE_DIR = Path("C:/Users/aryan/AppData/Local/Temp/rookbim_preset_live_fix")
MODEL_PATH = FIXTURE_DIR / "shell-preset.3dm"
SIDECAR_PATH = FIXTURE_DIR / "shell-preset.sidecar.json"


async def test_live_projects_bim_relationships_into_scene_graph():
    if not MODEL_PATH.is_file() or not SIDECAR_PATH.is_file():
        pytest.skip(f"RookBIM live fixture missing: {MODEL_PATH} / {SIDECAR_PATH}")

    instances = [
        instance for instance in discover_instances()
        if isinstance(instance, dict) and instance.get("pluginType") == "native" and instance.get("port")
    ]
    if not instances:
        pytest.skip("No discoverable Rook/Rhino instance")
    port = int(instances[0]["port"])

    new_doc = await call_rhino("/document/new", "POST", {}, port=port)
    assert new_doc.get("success"), new_doc

    opened = await call_rhino("/document/open", "POST", {"path": str(MODEL_PATH)}, port=port)
    assert opened.get("success"), opened

    sg = get_scene_graph()
    payload = await project_bim_relationships_for_tool(
        sidecar_path=str(SIDECAR_PATH),
        analytics=sg,
        include_rooms=True,
        include_levels=True,
        port=port,
    )

    assert payload["success"] is True
    assert payload["counts"]["joinedObjectCount"] > 0
    assert payload["counts"]["projectedLevelEdges"] > 0
    assert payload["counts"]["projectedHostEdges"] >= 0
    context_object = next(
        node_id
        for node_id, attrs in sg.graph.nodes(data=True)
        if attrs.get("rookbimJoined") is True
    )
    context = sg.get_context([context_object])
    assert "Revit" in context
```

- [ ] **Step 3: Run non-live invariant tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_relationship_projection.py mcp_server/tests/test_bim_relationship_projection_tool.py -q
```

Expected: PASS.

- [ ] **Step 4: Run live gate when Rhino/Rook is discoverable**

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_live_bim_relationship_projection.py -q
```

Expected when Rhino/Rook is open and the fixture exists: PASS. If no native instance is discoverable, the test is skipped and the PR remains live-gated.

- [ ] **Step 5: Commit guards and live test**

Run:

```powershell
git add mcp_server/tests/test_bim_relationship_projection.py mcp_server/tests/test_live_bim_relationship_projection.py
git commit -m "Add BIM projection invariants and live gate"
```

---

## Task 8: Final Verification

**Files:**
- No new code files unless earlier verification exposes a defect.

- [ ] **Step 1: Run focused Python test suite**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_relationship_projection.py mcp_server/tests/test_bim_relationship_projection_tool.py mcp_server/tests/test_scene_graph.py mcp_server/tests/test_exact_projection.py mcp_server/tests/test_containment_refinement.py -q
```

Expected: PASS.

- [ ] **Step 2: Confirm targeting/tool registration does not regress broad MCP tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_rookbim_mcp_tools.py mcp_server/tests/test_rookbim_export_preset_tool.py mcp_server/tests/test_bridge.py -q
```

Expected: PASS.

- [ ] **Step 3: Check branch scope**

Run:

```powershell
git status --short --branch
git diff --stat origin/main...HEAD
```

Expected:

```text
## feature/bim-relationship-projection-v1...origin/main [ahead N]
```

The diff should be limited to:

- `docs/superpowers/specs/2026-06-17-bim-relationship-projection-v1-design.md`
- `docs/superpowers/plans/2026-06-17-bim-relationship-projection-v1.md`
- `mcp_server/src/rook/scene/bim_relationship_projection.py`
- `mcp_server/src/rook/scene/scene_graph.py`
- `mcp_server/src/rook/server.py`
- `mcp_server/src/rook/agent/tool_dispatcher.py`
- `mcp_server/src/rook/agent/tool_groups.py`
- `mcp_server/src/rook/targeting.py`
- `mcp_server/tests/test_bim_relationship_projection.py`
- `mcp_server/tests/test_bim_relationship_projection_tool.py`
- `mcp_server/tests/test_live_bim_relationship_projection.py`

- [ ] **Step 4: Run live gate or record it pending**

If Rhino/Rook is discoverable and the Snowdon fixture exists, run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_live_bim_relationship_projection.py -q
```

Expected: PASS.

If skipped because no native instance is discoverable, record in the PR notes:

```text
Live BIM relationship projection gate pending: no discoverable native Rook/Rhino instance.
```

- [ ] **Step 5: Final commit if verification fixes were required**

If Step 1-4 required no code changes, do not create an empty commit. If fixes were made, run:

```powershell
git add <changed-files>
git commit -m "Fix BIM relationship projection verification issues"
```
