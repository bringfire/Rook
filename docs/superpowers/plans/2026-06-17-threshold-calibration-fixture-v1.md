# Threshold Calibration Fixture v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pure calibration library and gated live script that evaluate `contains_semantic` against RookBIM fixture labels without feeding Revit labels into runtime inference.

**Architecture:** `mcp_server/src/rook/scene/calibration.py` owns deterministic fixture parsing, joining, bucket classification, metrics, and JSON/Markdown report building. A thin script under `docs/rook_docs/rookbim-export-spike/` owns live Rhino/Rook orchestration and passes runtime outputs into the library. The first tasks are library-only and test-heavy so live Rhino debugging starts late.

**Tech Stack:** Python 3.10+, pytest, standard-library `json`/`pathlib`/`dataclasses`, existing Rook scene graph tools (`scene_exact_neighbors`, `scene_refine_containment`) via live script only.

---

## Branch discipline

Work only in `C:/Users/aryan/source/repos/rook-spatial` on branch `feature/spatial-intelligence`.

Before every commit:

```powershell
git branch --show-current
```

Expected:

```text
feature/spatial-intelligence
```

Never stage these known local/runtime files:

```text
knowledge/contextual_mab.pkl
knowledge/gh/component_observations.json
src/Rook/Properties/launchSettings.json
```

---

## File structure

- Create `mcp_server/src/rook/scene/calibration.py`
  - Pure deterministic calibration library.
  - Parses fixture JSON already loaded by callers or loaded through a dedicated parser helper.
  - Builds offline validation reports, live calibration reports, per-family buckets, review counts, and Markdown text.
  - Owns `write_report_bundle(...)`, the only disk-writing helper in the module.

- Create `mcp_server/tests/test_calibration.py`
  - Unit tests for fixture validation, schema shape, join map, bucket classifier, metrics, Markdown, report writing, and the Revit-label honesty invariant.
  - No live Rhino.

- Create `docs/rook_docs/rookbim-export-spike/live_calibrate_containment_fixture.py`
  - Gated live runner.
  - Discovers live Rook/Rhino, opens/imports a fixture `.3dm`, restricts calibration to imported fixture ids, optionally runs exact projection, runs containment refinement, writes report artifacts.

- Create `mcp_server/tests/test_live_calibrate_containment_fixture.py`
  - Script-level tests using fakes.
  - Tests argument parsing and orchestration order without live Rhino.

No MCP tool is added in v1.

---

### Task 1: Fixture Parsing + Offline Report Schema

**Files:**
- Create: `mcp_server/src/rook/scene/calibration.py`
- Create: `mcp_server/tests/test_calibration.py`

- [ ] **Step 1: Write failing tests for fixture validation and offline report schema**

Create `mcp_server/tests/test_calibration.py` with this initial content:

```python
from pathlib import Path

import pytest

from rook.scene import calibration as cal


def _sidecar():
    return {
        "schemaVersion": 1,
        "elements": [
            {
                "identity": {"uniqueId": "uid-wall", "elementId": 101, "source": "revit"},
                "elementId": 101,
                "category": "Walls",
                "family": "Basic Wall",
                "type": "Generic - 200mm",
                "name": "Wall 101",
                "labels": {
                    "level": {"value": "L1", "source": "revit_api", "confidence": "high", "missingReason": None},
                    "hostId": {"value": None, "source": "unavailable", "confidence": "low", "missingReason": "no_host"},
                    "containingRoomId": {"value": "room-1", "source": "revit_api", "confidence": "high", "missingReason": None},
                },
            },
            {
                "identity": {"uniqueId": "uid-door", "elementId": 202, "source": "revit"},
                "elementId": 202,
                "category": "Doors",
                "family": "Single Flush",
                "type": "0915 x 2134mm",
                "name": "Door 202",
                "labels": {
                    "level": {"value": "L1", "source": "revit_api", "confidence": "high", "missingReason": None},
                    "hostId": {"value": "uid-wall", "source": "revit_api", "confidence": "high", "missingReason": None},
                    "containingRoomId": {"value": "room-1", "source": "revit_api", "confidence": "high", "missingReason": None},
                },
            },
        ],
        "rooms": [
            {"uniqueId": "room-1", "number": "101", "name": "Office", "level": {"value": "L1"}}
        ],
        "relationships": {
            "hostMembership": [
                {"elementUniqueId": "uid-door", "hostUniqueId": "uid-wall", "source": "revit_api", "confidence": "high"}
            ],
            "roomMembership": [
                {"elementUniqueId": "uid-door", "roomUniqueId": "room-1", "source": "revit_api", "confidence": "high"},
                {"elementUniqueId": "uid-wall", "roomUniqueId": "room-1", "source": "revit_api", "confidence": "high"},
            ],
            "levelMembership": [
                {"elementUniqueId": "uid-door", "levelName": "L1", "source": "revit_api", "confidence": "high"},
                {"elementUniqueId": "uid-wall", "levelName": "L1", "source": "revit_api", "confidence": "high"},
            ],
        },
    }


def _validation():
    return {
        "schemaVersion": 1,
        "counts": {"resolved": 2, "exportedBrep": 2, "exportedMesh": 0, "exportedBboxProxy": 0, "failed": 0},
        "relationships": {
            "hostMembership": {"count": 1},
            "roomMembership": {"count": 2},
            "levelMembership": {"count": 2},
        },
        "objects": {"objectCount": 2, "withUniqueIdCount": 2},
    }


def test_validate_fixture_requires_relationship_indexes():
    sidecar = _sidecar()
    del sidecar["relationships"]["hostMembership"]

    with pytest.raises(cal.FixtureValidationError) as exc:
        cal.validate_fixture_payload(sidecar, _validation())

    assert "hostMembership" in str(exc.value)


def test_validate_fixture_normalizes_real_sidecar_shape():
    fixture = cal.validate_fixture_payload(_sidecar(), _validation())

    assert fixture.elements_by_unique_id["uid-door"]["labels"]["hostId"]["value"] == "uid-wall"
    assert fixture.relationships["hostMembership"] == {"uid-door": "uid-wall"}
    assert fixture.relationships["roomMembership"]["uid-wall"] == "room-1"
    assert fixture.relationships["levelMembership"]["uid-door"] == "L1"


def test_build_offline_fixture_validation_report_schema():
    fixture = cal.validate_fixture_payload(_sidecar(), _validation())

    report = cal.build_offline_fixture_validation_report(
        fixture,
        paths=cal.FixturePaths(
            model3dm="C:/tmp/shell-preset.3dm",
            sidecar="C:/tmp/shell-preset.sidecar.json",
            validation="C:/tmp/shell-preset.validation.json",
        ),
        fixture_id="shell-preset",
    )

    assert report["schemaVersion"] == 1
    assert report["mode"] == "offline_fixture_validation"
    assert len(report["fixtures"]) == 1
    fx = report["fixtures"][0]
    assert fx["fixtureId"] == "shell-preset"
    assert fx["summary"]["metricsComputed"] is False
    assert fx["summary"]["elementCount"] == 2
    assert fx["summary"]["relationshipIndexes"] == {
        "hostMembership": True,
        "roomMembership": True,
        "levelMembership": True,
    }
    assert fx["metrics"] == {}
    assert fx["candidates"] == []


def test_load_fixture_bundle_reads_three_paths(tmp_path):
    model = tmp_path / "shell-preset.3dm"
    sidecar = tmp_path / "shell-preset.sidecar.json"
    validation = tmp_path / "shell-preset.validation.json"
    model.write_bytes(b"fake-3dm-for-path-validation")
    sidecar.write_text(cal.json_dumps(_sidecar()), encoding="utf-8")
    validation.write_text(cal.json_dumps(_validation()), encoding="utf-8")

    loaded = cal.load_fixture_bundle(
        cal.FixturePaths(str(model), str(sidecar), str(validation))
    )

    assert loaded.fixture.elements_by_unique_id["uid-door"]["category"] == "Doors"
    assert loaded.paths.model3dm == str(model)
```

- [ ] **Step 2: Run tests and verify they fail**

Run from `C:/Users/aryan/source/repos/rook-spatial/mcp_server`:

```powershell
python -m pytest tests/test_calibration.py -q
```

Expected: FAIL with `ImportError` or `AttributeError` because `rook.scene.calibration` does not exist.

- [ ] **Step 3: Implement fixture parsing and offline report schema**

Create `mcp_server/src/rook/scene/calibration.py`:

```python
"""Threshold calibration utilities for RookBIM fixture reports.

Pure library: no live Rhino discovery, no HTTP calls, no process launching. Core builders
return dictionaries or strings. Only write_report_bundle() writes files.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MODE_LIVE = "live_calibration"
MODE_OFFLINE = "offline_fixture_validation"
REQUIRED_RELATIONSHIPS = ("hostMembership", "roomMembership", "levelMembership")


class FixtureValidationError(ValueError):
    """Raised when a RookBIM calibration fixture is not usable."""


@dataclass(frozen=True)
class FixturePaths:
    model3dm: str
    sidecar: str
    validation: str


@dataclass(frozen=True)
class FixtureData:
    sidecar: dict[str, Any]
    validation: dict[str, Any]
    elements_by_unique_id: dict[str, dict[str, Any]]
    rooms_by_unique_id: dict[str, dict[str, Any]]
    relationships: dict[str, Any]


@dataclass(frozen=True)
class LoadedFixture:
    paths: FixturePaths
    fixture: FixtureData


def json_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FixtureValidationError(f"{name} must be an object")
    return value


def validate_fixture_payload(sidecar: dict[str, Any], validation: dict[str, Any]) -> FixtureData:
    sidecar = _require_dict(sidecar, "sidecar")
    validation = _require_dict(validation, "validation")
    elements = sidecar.get("elements")
    if not isinstance(elements, list):
        raise FixtureValidationError("sidecar.elements must be an array")
    relationships = sidecar.get("relationships")
    if not isinstance(relationships, dict):
        raise FixtureValidationError("sidecar.relationships must be an object")
    missing = [name for name in REQUIRED_RELATIONSHIPS if name not in relationships]
    if missing:
        raise FixtureValidationError(f"missing relationship indexes: {', '.join(missing)}")

    elements_by_uid: dict[str, dict[str, Any]] = {}
    for idx, element in enumerate(elements):
        if not isinstance(element, dict):
            raise FixtureValidationError(f"sidecar.elements[{idx}] must be an object")
        uid = _element_unique_id(element)
        if not isinstance(uid, str) or not uid:
            raise FixtureValidationError(f"sidecar.elements[{idx}] missing uniqueId")
        elements_by_uid[uid] = element

    rooms = sidecar.get("rooms") or []
    if not isinstance(rooms, list):
        raise FixtureValidationError("sidecar.rooms must be an array when present")
    rooms_by_uid = {
        room["uniqueId"]: room
        for room in rooms
        if isinstance(room, dict) and isinstance(room.get("uniqueId"), str) and room.get("uniqueId")
    }

    return FixtureData(
        sidecar=sidecar,
        validation=validation,
        elements_by_unique_id=elements_by_uid,
        rooms_by_unique_id=rooms_by_uid,
        relationships=_normalize_relationships(relationships),
    )


def _element_unique_id(element: dict[str, Any]) -> str | None:
    identity = element.get("identity")
    if isinstance(identity, dict) and isinstance(identity.get("uniqueId"), str):
        return identity["uniqueId"]
    for key in ("uniqueId", "revitUniqueId"):
        value = element.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _normalize_relationships(raw: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {
        "hostMembership": _normalize_membership(
            raw.get("hostMembership"),
            source_key="elementUniqueId",
            target_key="hostUniqueId",
        ),
        "roomMembership": _normalize_membership(
            raw.get("roomMembership"),
            source_key="elementUniqueId",
            target_key="roomUniqueId",
        ),
        "levelMembership": _normalize_membership(
            raw.get("levelMembership"),
            source_key="elementUniqueId",
            target_key="levelName",
        ),
    }


def _normalize_membership(value: Any, *, source_key: str, target_key: str) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items() if k and v}
    out: dict[str, str] = {}
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            source = item.get(source_key)
            target = item.get(target_key)
            if source and target:
                out[str(source)] = str(target)
    return out


def load_fixture_bundle(paths: FixturePaths) -> LoadedFixture:
    for label, raw_path in (
        ("model3dm", paths.model3dm),
        ("sidecar", paths.sidecar),
        ("validation", paths.validation),
    ):
        if not Path(raw_path).exists():
            raise FixtureValidationError(f"missing {label}: {raw_path}")
    sidecar = json.loads(Path(paths.sidecar).read_text(encoding="utf-8"))
    validation = json.loads(Path(paths.validation).read_text(encoding="utf-8"))
    return LoadedFixture(paths=paths, fixture=validate_fixture_payload(sidecar, validation))


def build_offline_fixture_validation_report(
    fixture: FixtureData,
    *,
    paths: FixturePaths,
    fixture_id: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "mode": MODE_OFFLINE,
        "generatedAt": _utc_now_iso(),
        "fixtures": [
            {
                "fixtureId": fixture_id,
                "paths": {
                    "model3dm": paths.model3dm,
                    "sidecar": paths.sidecar,
                    "validation": paths.validation,
                },
                "runtime": {
                    "projectExactAdjacency": False,
                    "freshDocument": None,
                    "graphSequence": None,
                    "sceneExactNeighbors": {"attempted": False, "succeeded": False, "errors": []},
                    "sceneRefineContainment": {"attempted": False, "succeeded": False, "errors": []},
                    "inputObjectCount": 0,
                    "joinedObjectCount": 0,
                    "evaluatedObjectCount": 0,
                    "categoryFilters": [],
                    "cap": None,
                },
                "summary": {
                    "metricsComputed": False,
                    "elementCount": len(fixture.elements_by_unique_id),
                    "roomCount": len(fixture.rooms_by_unique_id),
                    "relationshipIndexes": {
                        name: name in fixture.relationships for name in REQUIRED_RELATIONSHIPS
                    },
                },
                "metrics": {},
                "candidates": [],
            }
        ],
    }
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_calibration.py -q
```

Expected: PASS for the three tests in Task 1.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git branch --show-current
git add mcp_server/src/rook/scene/calibration.py mcp_server/tests/test_calibration.py
git commit -m "feat(spatial): add calibration fixture parser"
```

Expected: branch is `feature/spatial-intelligence`; commit includes only `calibration.py` and `test_calibration.py`.

---

### Task 2: Runtime Join Map + Candidate Records

**Files:**
- Modify: `mcp_server/src/rook/scene/calibration.py`
- Modify: `mcp_server/tests/test_calibration.py`

- [ ] **Step 1: Add failing tests for runtime metadata joins**

Append to `mcp_server/tests/test_calibration.py`:

```python
def _runtime_objects():
    return [
        {
            "runtimeId": "rook-wall",
            "name": "Wall 101",
            "layer": "RookBim::L1::Walls",
            "userStrings": {
                "revit.uniqueId": "uid-wall",
                "revit.elementId": "101",
                "revit.category": "Walls",
            },
        },
        {
            "runtimeId": "rook-door",
            "name": "Door 202",
            "layer": "RookBim::L1::Doors",
            "userStrings": {
                "revit.uniqueId": "uid-door",
                "revit.elementId": "202",
                "revit.category": "Doors",
            },
        },
        {
            "runtimeId": "unjoined-box",
            "name": "No Revit Key",
            "layer": "Default",
            "userStrings": {},
        },
    ]


def test_build_runtime_join_map_by_revit_unique_id():
    fixture = cal.validate_fixture_payload(_sidecar(), _validation())

    join = cal.build_runtime_join_map(_runtime_objects(), fixture)

    assert join.by_runtime_id["rook-door"].revit_unique_id == "uid-door"
    assert join.by_runtime_id["rook-door"].element["category"] == "Doors"
    assert join.not_joinable["unjoined-box"] == "missing_revit_unique_id"


def test_build_candidate_records_join_endpoints_and_preserve_runtime_verdict():
    fixture = cal.validate_fixture_payload(_sidecar(), _validation())
    join = cal.build_runtime_join_map(_runtime_objects(), fixture)
    refinement = {
        "success": True,
        "graphSequence": 9,
        "refined": [
            {
                "candidateId": "rook-wall|contains|rook-door",
                "containerId": "rook-wall",
                "containedId": "rook-door",
                "verdict": "contains_semantic",
                "confidence": "high",
                "reason": "strong_clearance_plausible_container",
                "evidence": [{"signal": "bbox_margin", "polarity": "supports", "detail": "positive"}],
            }
        ],
    }

    candidates = cal.build_candidate_records(refinement, join, fixture)

    assert len(candidates) == 1
    c = candidates[0]
    assert c["candidateId"] == "rook-wall|contains|rook-door"
    assert c["container"]["revitUniqueId"] == "uid-wall"
    assert c["contained"]["revitUniqueId"] == "uid-door"
    assert c["rook"]["verdict"] == "contains_semantic"
    assert c["rook"]["confidence"] == "high"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_calibration.py -q
```

Expected: FAIL with missing `build_runtime_join_map`.

- [ ] **Step 3: Implement join map and candidate record builder**

Append/merge into `mcp_server/src/rook/scene/calibration.py`:

```python
@dataclass(frozen=True)
class JoinedRuntimeObject:
    runtime_id: str
    revit_unique_id: str
    revit_element_id: str | None
    revit_category: str | None
    name: str
    layer: str
    user_strings: dict[str, Any]
    element: dict[str, Any]


@dataclass(frozen=True)
class RuntimeJoinMap:
    by_runtime_id: dict[str, JoinedRuntimeObject]
    by_revit_unique_id: dict[str, list[JoinedRuntimeObject]]
    not_joinable: dict[str, str]


def _user_strings(obj: dict[str, Any]) -> dict[str, Any]:
    raw = obj.get("userStrings") or obj.get("user_strings") or {}
    return raw if isinstance(raw, dict) else {}


def _runtime_id(obj: dict[str, Any]) -> str:
    return str(obj.get("runtimeId") or obj.get("id") or obj.get("objectId") or "")


def build_runtime_join_map(runtime_objects: list[dict[str, Any]], fixture: FixtureData) -> RuntimeJoinMap:
    by_runtime: dict[str, JoinedRuntimeObject] = {}
    by_uid: dict[str, list[JoinedRuntimeObject]] = {}
    not_joinable: dict[str, str] = {}
    for obj in runtime_objects:
        rid = _runtime_id(obj)
        if not rid:
            continue
        strings = _user_strings(obj)
        uid = strings.get("revit.uniqueId")
        if not isinstance(uid, str) or not uid:
            not_joinable[rid] = "missing_revit_unique_id"
            continue
        element = fixture.elements_by_unique_id.get(uid) or fixture.rooms_by_unique_id.get(uid)
        if element is None:
            not_joinable[rid] = "unknown_revit_unique_id"
            continue
        joined = JoinedRuntimeObject(
            runtime_id=rid,
            revit_unique_id=uid,
            revit_element_id=str(strings.get("revit.elementId")) if strings.get("revit.elementId") is not None else None,
            revit_category=str(strings.get("revit.category")) if strings.get("revit.category") is not None else None,
            name=str(obj.get("name") or ""),
            layer=str(obj.get("layer") or ""),
            user_strings=strings,
            element=element,
        )
        by_runtime[rid] = joined
        by_uid.setdefault(uid, []).append(joined)
    return RuntimeJoinMap(by_runtime_id=by_runtime, by_revit_unique_id=by_uid, not_joinable=not_joinable)


def _endpoint_payload(joined: JoinedRuntimeObject | None, runtime_id: str) -> dict[str, Any]:
    if joined is None:
        return {"runtimeId": runtime_id, "joinStatus": "not_joinable"}
    identity = joined.element.get("identity") if isinstance(joined.element.get("identity"), dict) else {}
    labels = joined.element.get("labels") if isinstance(joined.element.get("labels"), dict) else {}
    return {
        "runtimeId": joined.runtime_id,
        "joinStatus": "joined",
        "revitUniqueId": joined.revit_unique_id,
        "revitElementId": joined.revit_element_id or identity.get("elementId"),
        "category": joined.element.get("category") or joined.revit_category,
        "family": joined.element.get("family"),
        "type": joined.element.get("type"),
        "name": joined.name or joined.element.get("name"),
        "layer": joined.layer,
        "labels": {
            "host": labels.get("hostId"),
            "room": labels.get("containingRoomId"),
            "level": labels.get("level"),
        },
    }


def build_candidate_records(
    refinement_result: dict[str, Any],
    join: RuntimeJoinMap,
    fixture: FixtureData,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in refinement_result.get("refined") or []:
        container_id = str(item.get("containerId") or "")
        contained_id = str(item.get("containedId") or "")
        container = join.by_runtime_id.get(container_id)
        contained = join.by_runtime_id.get(contained_id)
        records.append({
            "candidateId": item.get("candidateId") or f"{container_id}|contains|{contained_id}",
            "container": _endpoint_payload(container, container_id),
            "contained": _endpoint_payload(contained, contained_id),
            "rook": {
                "verdict": item.get("verdict"),
                "confidence": item.get("confidence"),
                "reason": item.get("reason"),
                "evidence": item.get("evidence") or [],
            },
            "fixtureRelationships": {
                "hostMembership": fixture.relationships.get("hostMembership", {}),
                "roomMembership": fixture.relationships.get("roomMembership", {}),
                "levelMembership": fixture.relationships.get("levelMembership", {}),
            },
        })
    return records
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_calibration.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git branch --show-current
git add mcp_server/src/rook/scene/calibration.py mcp_server/tests/test_calibration.py
git commit -m "feat(spatial): join calibration candidates to revit labels"
```

---

### Task 3: Per-Family Buckets + Metric Eligibility

**Files:**
- Modify: `mcp_server/src/rook/scene/calibration.py`
- Modify: `mcp_server/tests/test_calibration.py`

- [ ] **Step 1: Add failing tests for buckets and eligibility**

Append to `mcp_server/tests/test_calibration.py`:

```python
def test_classify_candidate_host_supported_positive():
    fixture = cal.validate_fixture_payload(_sidecar(), _validation())
    join = cal.build_runtime_join_map(_runtime_objects(), fixture)
    candidate = cal.build_candidate_records({
        "refined": [{
            "candidateId": "rook-wall|contains|rook-door",
            "containerId": "rook-wall",
            "containedId": "rook-door",
            "verdict": "contains_semantic",
            "confidence": "high",
            "reason": "strong_clearance_plausible_container",
            "evidence": [],
        }]
    }, join, fixture)[0]

    classified = cal.classify_candidate(candidate, fixture)

    assert classified["hostBucket"] == "host_supported_positive"
    assert classified["roomBucket"] == "room_not_applicable"
    assert classified["levelBucket"] == "level_not_applicable"
    assert classified["comparisonBasis"]["host"] == "host_unique_id"
    assert classified["metricEligible"] == {"host": True, "room": False, "level": False}


def test_classify_candidate_host_contradicted_positive():
    fixture = cal.validate_fixture_payload(_sidecar(), _validation())
    join = cal.build_runtime_join_map(_runtime_objects(), fixture)
    candidate = cal.build_candidate_records({
        "refined": [{
            "candidateId": "rook-door|contains|rook-wall",
            "containerId": "rook-door",
            "containedId": "rook-wall",
            "verdict": "contains_semantic",
            "confidence": "high",
            "reason": "strong_clearance_plausible_container",
            "evidence": [],
        }]
    }, join, fixture)[0]

    classified = cal.classify_candidate(candidate, fixture)

    assert classified["hostBucket"] == "host_contradicted_positive"
    assert classified["comparisonBasis"]["host"] == "host_unique_id"
    assert classified["metricEligible"]["host"] is True


def test_classify_missing_labels_are_not_ambiguous():
    sidecar = _sidecar()
    sidecar["elements"][1]["labels"]["hostId"] = {"value": None, "source": "unavailable", "confidence": "low", "missingReason": "no_host"}
    sidecar["relationships"]["hostMembership"] = {}
    fixture = cal.validate_fixture_payload(sidecar, _validation())
    join = cal.build_runtime_join_map(_runtime_objects(), fixture)
    candidate = cal.build_candidate_records({
        "refined": [{
            "candidateId": "rook-wall|contains|rook-door",
            "containerId": "rook-wall",
            "containedId": "rook-door",
            "verdict": "contains_semantic",
            "confidence": "medium",
            "reason": "clear_containment_minor_gaps",
            "evidence": [],
        }]
    }, join, fixture)[0]

    classified = cal.classify_candidate(candidate, fixture)

    assert classified["hostBucket"] == "host_missing_label"
    assert classified["reviewBucket"] != "ambiguous"


def test_not_joinable_candidate_is_excluded_from_metrics():
    fixture = cal.validate_fixture_payload(_sidecar(), _validation())
    join = cal.build_runtime_join_map(_runtime_objects(), fixture)
    candidate = cal.build_candidate_records({
        "refined": [{
            "candidateId": "rook-wall|contains|unjoined-box",
            "containerId": "rook-wall",
            "containedId": "unjoined-box",
            "verdict": "contains_semantic",
            "confidence": "low",
            "reason": "weak_positive_containment",
            "evidence": [],
        }]
    }, join, fixture)[0]

    classified = cal.classify_candidate(candidate, fixture)

    assert classified["reviewBucket"] == "not_joinable"
    assert classified["metricEligible"] == {"host": False, "room": False, "level": False}


def test_add_missed_host_relation_when_no_positive_candidate_exists_inside_evaluated_scope():
    fixture = cal.validate_fixture_payload(_sidecar(), _validation())
    join = cal.build_runtime_join_map(_runtime_objects(), fixture)

    missed = cal.add_missed_labeled_relation_records(
        [],
        join,
        fixture,
        evaluated_runtime_ids={"rook-wall", "rook-door"},
    )

    assert len(missed) == 1
    assert missed[0]["candidateId"] == "rook-wall|contains|rook-door|missed_host"
    assert missed[0]["hostBucket"] == "host_missed_labeled_relation"
    assert missed[0]["metricEligible"]["host"] is True


def test_missed_host_relation_respects_evaluated_scope():
    fixture = cal.validate_fixture_payload(_sidecar(), _validation())
    join = cal.build_runtime_join_map(_runtime_objects(), fixture)

    missed = cal.add_missed_labeled_relation_records(
        [],
        join,
        fixture,
        evaluated_runtime_ids={"rook-wall"},
    )

    assert missed == []
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_calibration.py -q
```

Expected: FAIL with missing `classify_candidate`.

- [ ] **Step 3: Implement bucket classification**

Add to `mcp_server/src/rook/scene/calibration.py`:

```python
def _label_value(label: Any) -> Any:
    if isinstance(label, dict):
        return label.get("value")
    return label


def _uid(endpoint: dict[str, Any]) -> str | None:
    value = endpoint.get("revitUniqueId")
    return value if isinstance(value, str) and value else None


def _positive(candidate: dict[str, Any]) -> bool:
    return candidate.get("rook", {}).get("verdict") == "contains_semantic"


def _host_bucket(candidate: dict[str, Any], fixture: FixtureData) -> tuple[str, str, bool]:
    container_uid = _uid(candidate["container"])
    contained_uid = _uid(candidate["contained"])
    if not container_uid or not contained_uid:
        return "host_not_applicable", "none", False
    host_map = fixture.relationships.get("hostMembership") or {}
    expected_host = host_map.get(contained_uid) or _label_value(candidate["contained"].get("labels", {}).get("host"))
    if not expected_host:
        return "host_missing_label", "none", False
    if _positive(candidate):
        if expected_host == container_uid:
            return "host_supported_positive", "host_unique_id", True
        return "host_contradicted_positive", "host_unique_id", True
    if expected_host == container_uid:
        return "host_missed_labeled_relation", "host_unique_id", True
    return "host_not_applicable", "none", False


def _room_bucket(candidate: dict[str, Any], fixture: FixtureData) -> tuple[str, str, bool]:
    container_uid = _uid(candidate["container"])
    contained_uid = _uid(candidate["contained"])
    if not container_uid or not contained_uid:
        return "room_not_applicable", "none", False
    room_map = fixture.relationships.get("roomMembership") or {}
    container_room = room_map.get(container_uid) or _label_value(candidate["container"].get("labels", {}).get("room"))
    contained_room = room_map.get(contained_uid) or _label_value(candidate["contained"].get("labels", {}).get("room"))
    container_is_room = container_uid in fixture.rooms_by_unique_id
    if container_is_room:
        if not contained_room:
            return "room_missing_label", "room_endpoint", False
        if _positive(candidate) and contained_room == container_uid:
            return "room_supported_positive", "room_endpoint", True
        if _positive(candidate):
            return "room_contradicted_positive", "room_endpoint", True
        if contained_room == container_uid:
            return "room_missed_labeled_relation", "room_endpoint", True
        return "room_not_applicable", "none", False
    if not container_room or not contained_room:
        return "room_missing_label", "same_room", False
    if _positive(candidate) and container_room != contained_room:
        return "room_contradicted_positive", "same_room", True
    return "room_not_applicable", "same_room", False


def _level_bucket(candidate: dict[str, Any], fixture: FixtureData) -> tuple[str, str, bool]:
    container_uid = _uid(candidate["container"])
    contained_uid = _uid(candidate["contained"])
    if not container_uid or not contained_uid:
        return "level_not_applicable", "none", False
    level_map = fixture.relationships.get("levelMembership") or {}
    container_level = level_map.get(container_uid) or _label_value(candidate["container"].get("labels", {}).get("level"))
    contained_level = level_map.get(contained_uid) or _label_value(candidate["contained"].get("labels", {}).get("level"))
    if not container_level or not contained_level:
        return "level_missing_label", "same_level", False
    if _positive(candidate) and container_level != contained_level:
        return "level_contradicted_positive", "same_level", True
    return "level_not_applicable", "same_level", False


def classify_candidate(candidate: dict[str, Any], fixture: FixtureData) -> dict[str, Any]:
    if candidate["container"].get("joinStatus") != "joined" or candidate["contained"].get("joinStatus") != "joined":
        out = dict(candidate)
        out.update({
            "hostBucket": "not_joinable",
            "roomBucket": "not_joinable",
            "levelBucket": "not_joinable",
            "reviewBucket": "not_joinable",
            "comparisonBasis": {"host": "none", "room": "none", "level": "none"},
            "metricEligible": {"host": False, "room": False, "level": False},
        })
        return out

    host_bucket, host_basis, host_eligible = _host_bucket(candidate, fixture)
    room_bucket, room_basis, room_eligible = _room_bucket(candidate, fixture)
    level_bucket, level_basis, level_eligible = _level_bucket(candidate, fixture)
    priority = [
        host_bucket,
        room_bucket,
        level_bucket,
    ]
    review = next((b for b in priority if "contradicted_positive" in b), None)
    if review is None:
        review = next((b for b in priority if "missed_labeled_relation" in b), None)
    if review is None:
        review = next((b for b in priority if "supported_positive" in b), None)
    if review is None:
        review = "not_applicable"

    out = dict(candidate)
    out.update({
        "hostBucket": host_bucket,
        "roomBucket": room_bucket,
        "levelBucket": level_bucket,
        "reviewBucket": review,
        "comparisonBasis": {"host": host_basis, "room": room_basis, "level": level_basis},
        "metricEligible": {"host": host_eligible, "room": room_eligible, "level": level_eligible},
    })
    return out


def _positive_uid_pairs(candidates: list[dict[str, Any]]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for c in candidates:
        if c.get("rook", {}).get("verdict") != "contains_semantic":
            continue
        cu = _uid(c.get("container", {}))
        bu = _uid(c.get("contained", {}))
        if cu and bu:
            pairs.add((cu, bu))
    return pairs


def add_missed_labeled_relation_records(
    classified_candidates: list[dict[str, Any]],
    join: RuntimeJoinMap,
    fixture: FixtureData,
    *,
    evaluated_runtime_ids: set[str],
) -> list[dict[str, Any]]:
    """Add in-scope host missed-relation records for labeled host relations absent from positives.

    v1 only synthesizes host misses. Room/level misses are weaker contextual families and remain
    review-only until a later slice defines expected candidate generation for spatial structures.
    Both endpoints must be inside the evaluated runtime-id set so category filters/caps do not
    contaminate missed-relation metrics.
    """
    out = list(classified_candidates)
    positive_pairs = _positive_uid_pairs(out)
    host_map = fixture.relationships.get("hostMembership") or {}
    for contained_uid, host_uid in host_map.items():
        if not contained_uid or not host_uid or (host_uid, contained_uid) in positive_pairs:
            continue
        host_objects = join.by_revit_unique_id.get(host_uid) or []
        contained_objects = join.by_revit_unique_id.get(contained_uid) or []
        if not host_objects or not contained_objects:
            continue
        host_obj = host_objects[0]
        contained_obj = contained_objects[0]
        if host_obj.runtime_id not in evaluated_runtime_ids or contained_obj.runtime_id not in evaluated_runtime_ids:
            continue
        record = {
            "candidateId": f"{host_obj.runtime_id}|contains|{contained_obj.runtime_id}|missed_host",
            "container": _endpoint_payload(host_obj, host_obj.runtime_id),
            "contained": _endpoint_payload(contained_obj, contained_obj.runtime_id),
            "rook": {
                "verdict": "missing_positive",
                "confidence": "none",
                "reason": "no_contains_semantic_candidate",
                "evidence": [],
            },
            "hostBucket": "host_missed_labeled_relation",
            "roomBucket": "room_not_applicable",
            "levelBucket": "level_not_applicable",
            "reviewBucket": "host_missed_labeled_relation",
            "comparisonBasis": {"host": "host_unique_id", "room": "none", "level": "none"},
            "metricEligible": {"host": True, "room": False, "level": False},
        }
        out.append(record)
    return out
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_calibration.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git branch --show-current
git add mcp_server/src/rook/scene/calibration.py mcp_server/tests/test_calibration.py
git commit -m "feat(spatial): classify calibration buckets by label family"
```

---

### Task 4: Live Report Builder, Review Counts, Markdown, Writer

**Files:**
- Modify: `mcp_server/src/rook/scene/calibration.py`
- Modify: `mcp_server/tests/test_calibration.py`

- [ ] **Step 1: Add failing tests for live report, Markdown, and disk writer boundary**

Append to `mcp_server/tests/test_calibration.py`:

```python
def _classified_candidates():
    fixture = cal.validate_fixture_payload(_sidecar(), _validation())
    join = cal.build_runtime_join_map(_runtime_objects(), fixture)
    raw = cal.build_candidate_records({
        "refined": [{
            "candidateId": "rook-wall|contains|rook-door",
            "containerId": "rook-wall",
            "containedId": "rook-door",
            "verdict": "contains_semantic",
            "confidence": "high",
            "reason": "strong_clearance_plausible_container",
            "evidence": [{"signal": "bbox_margin", "polarity": "supports", "detail": "positive"}],
        }]
    }, join, fixture)
    return fixture, [cal.classify_candidate(c, fixture) for c in raw]


def test_build_live_calibration_report_counts_by_family():
    fixture, candidates = _classified_candidates()

    report = cal.build_live_calibration_report(
        fixture,
        paths=cal.FixturePaths("C:/tmp/shell-preset.3dm", "C:/tmp/shell-preset.sidecar.json", "C:/tmp/shell-preset.validation.json"),
        fixture_id="shell-preset",
        runtime=cal.RuntimeSummary(
            project_exact_adjacency=True,
            fresh_document=True,
            graph_sequence=9,
            scene_exact_neighbors={"attempted": True, "succeeded": True, "errors": []},
            scene_refine_containment={"attempted": True, "succeeded": True, "errors": []},
            input_object_count=2,
            joined_object_count=2,
            evaluated_object_count=2,
            category_filters=["Walls", "Doors"],
            cap=100,
        ),
        candidates=candidates,
    )

    fx = report["fixtures"][0]
    assert report["mode"] == "live_calibration"
    assert fx["runtime"]["projectExactAdjacency"] is True
    assert fx["metrics"]["byLabelFamily"]["host"]["host_supported_positive"] == 1
    assert fx["summary"]["reviewCounts"]["host_supported_positive"] == 1
    assert fx["candidates"][0]["metricEligible"]["host"] is True


def test_render_markdown_summary_mentions_no_global_accuracy():
    fixture, candidates = _classified_candidates()
    report = cal.build_live_calibration_report(
        fixture,
        paths=cal.FixturePaths("C:/tmp/shell-preset.3dm", "C:/tmp/shell-preset.sidecar.json", "C:/tmp/shell-preset.validation.json"),
        fixture_id="shell-preset",
        runtime=cal.RuntimeSummary(True, True, 9, {"attempted": True, "succeeded": True, "errors": []}, {"attempted": True, "succeeded": True, "errors": []}, 2, 2, 2, [], None),
        candidates=candidates,
    )

    md = cal.render_markdown_summary(report)

    assert "# Threshold Calibration Report" in md
    assert "shell-preset" in md
    assert "No global accuracy/F1 is computed" in md
    assert "host_supported_positive" in md


def test_write_report_bundle_is_only_disk_writer(tmp_path):
    fixture, candidates = _classified_candidates()
    report = cal.build_live_calibration_report(
        fixture,
        paths=cal.FixturePaths("C:/tmp/shell-preset.3dm", "C:/tmp/shell-preset.sidecar.json", "C:/tmp/shell-preset.validation.json"),
        fixture_id="shell-preset",
        runtime=cal.RuntimeSummary(True, True, 9, {"attempted": True, "succeeded": True, "errors": []}, {"attempted": True, "succeeded": True, "errors": []}, 2, 2, 2, [], None),
        candidates=candidates,
    )

    paths = cal.write_report_bundle(report, tmp_path, "shell-preset")

    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()
    assert Path(paths["json"]).name == "shell-preset.calibration.json"
    assert Path(paths["markdown"]).read_text(encoding="utf-8").startswith("# Threshold Calibration Report")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_calibration.py -q
```

Expected: FAIL with missing `RuntimeSummary`.

- [ ] **Step 3: Implement live report, Markdown, and writer**

Add to `mcp_server/src/rook/scene/calibration.py`:

```python
@dataclass(frozen=True)
class RuntimeSummary:
    project_exact_adjacency: bool
    fresh_document: bool | None
    graph_sequence: int | None
    scene_exact_neighbors: dict[str, Any]
    scene_refine_containment: dict[str, Any]
    input_object_count: int
    joined_object_count: int
    evaluated_object_count: int
    category_filters: list[str]
    cap: int | None


def _runtime_payload(runtime: RuntimeSummary) -> dict[str, Any]:
    return {
        "projectExactAdjacency": runtime.project_exact_adjacency,
        "freshDocument": runtime.fresh_document,
        "graphSequence": runtime.graph_sequence,
        "sceneExactNeighbors": runtime.scene_exact_neighbors,
        "sceneRefineContainment": runtime.scene_refine_containment,
        "inputObjectCount": runtime.input_object_count,
        "joinedObjectCount": runtime.joined_object_count,
        "evaluatedObjectCount": runtime.evaluated_object_count,
        "categoryFilters": runtime.category_filters,
        "cap": runtime.cap,
    }


def _count(values: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return out


def _metrics(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    host = _count([c["hostBucket"] for c in candidates])
    room = _count([c["roomBucket"] for c in candidates])
    level = _count([c["levelBucket"] for c in candidates])
    by_pair: dict[str, dict[str, dict[str, int]]] = {}
    by_conf: dict[str, dict[str, int]] = {}
    for c in candidates:
        pair = f"{c['container'].get('category')}->{c['contained'].get('category')}"
        by_pair.setdefault(pair, {"host": {}, "room": {}, "level": {}})
        for fam, bucket_name in (("host", "hostBucket"), ("room", "roomBucket"), ("level", "levelBucket")):
            bucket = c[bucket_name]
            by_pair[pair][fam][bucket] = by_pair[pair][fam].get(bucket, 0) + 1
        conf = str(c.get("rook", {}).get("confidence") or "none")
        by_conf.setdefault(conf, {})
        review = c.get("reviewBucket", "not_applicable")
        by_conf[conf][review] = by_conf[conf].get(review, 0) + 1
    return {
        "byLabelFamily": {"host": host, "room": room, "level": level},
        "byCategoryPair": by_pair,
        "byConfidence": by_conf,
    }


def build_live_calibration_report(
    fixture: FixtureData,
    *,
    paths: FixturePaths,
    fixture_id: str,
    runtime: RuntimeSummary,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    metrics = _metrics(candidates)
    review_counts = _count([c.get("reviewBucket", "not_applicable") for c in candidates])
    return {
        "schemaVersion": SCHEMA_VERSION,
        "mode": MODE_LIVE,
        "generatedAt": _utc_now_iso(),
        "fixtures": [
            {
                "fixtureId": fixture_id,
                "paths": {
                    "model3dm": paths.model3dm,
                    "sidecar": paths.sidecar,
                    "validation": paths.validation,
                },
                "runtime": _runtime_payload(runtime),
                "summary": {
                    "metricsComputed": True,
                    "reviewCounts": review_counts,
                    "notJoinableCount": review_counts.get("not_joinable", 0),
                    "ambiguousCount": review_counts.get("ambiguous", 0),
                    "candidateCount": len(candidates),
                },
                "metrics": metrics,
                "candidates": candidates,
            }
        ],
    }


def render_markdown_summary(report: dict[str, Any]) -> str:
    fx = report["fixtures"][0]
    lines = [
        "# Threshold Calibration Report",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Fixture: `{fx['fixtureId']}`",
        f"- Model: `{fx['paths']['model3dm']}`",
        f"- Exact adjacency projected: `{fx['runtime'].get('projectExactAdjacency')}`",
        f"- Graph sequence: `{fx['runtime'].get('graphSequence')}`",
        "",
        "No global accuracy/F1 is computed. Host, room, and level are separate review families.",
        "",
        "## Review Counts",
    ]
    for key, value in sorted((fx.get("summary", {}).get("reviewCounts") or {}).items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Label-Family Metrics"])
    for family, counts in (fx.get("metrics", {}).get("byLabelFamily") or {}).items():
        lines.append(f"- `{family}`: {counts}")
    return "\n".join(lines) + "\n"


def write_report_bundle(report: dict[str, Any], output_dir: str | Path, name: str) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"{name}.calibration.json"
    md_path = out / f"{name}.calibration.md"
    json_path.write_text(json_dumps(report), encoding="utf-8")
    md_path.write_text(render_markdown_summary(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_calibration.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

Run:

```powershell
git branch --show-current
git add mcp_server/src/rook/scene/calibration.py mcp_server/tests/test_calibration.py
git commit -m "feat(spatial): build calibration reports"
```

---

### Task 5: Offline CLI Path in the Gated Script

**Files:**
- Create: `docs/rook_docs/rookbim-export-spike/live_calibrate_containment_fixture.py`
- Create: `mcp_server/tests/test_live_calibrate_containment_fixture.py`

- [ ] **Step 1: Add failing script tests for offline mode**

Create `mcp_server/tests/test_live_calibrate_containment_fixture.py`:

```python
import importlib.util
from pathlib import Path

from rook.scene import calibration as cal


SCRIPT = Path(__file__).parents[2] / "docs" / "rook_docs" / "rookbim-export-spike" / "live_calibrate_containment_fixture.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("live_calibrate_containment_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_args_defaults_exact_projection_on(tmp_path):
    script = _load_script()
    args = script.parse_args([
        "--model3dm", str(tmp_path / "a.3dm"),
        "--sidecar", str(tmp_path / "a.sidecar.json"),
        "--validation", str(tmp_path / "a.validation.json"),
        "--output-dir", str(tmp_path),
        "--name", "fixture",
        "--offline",
    ])

    assert args.project_exact_adjacency is True
    assert args.offline is True


def test_offline_main_writes_schema_report(monkeypatch, tmp_path):
    script = _load_script()
    model = tmp_path / "a.3dm"
    sidecar = tmp_path / "a.sidecar.json"
    validation = tmp_path / "a.validation.json"
    model.write_bytes(b"fake")
    sidecar.write_text(cal.json_dumps({
        "elements": [{"identity": {"uniqueId": "u1", "elementId": 1}, "category": "Walls", "labels": {}}],
        "rooms": [],
        "relationships": {"hostMembership": {}, "roomMembership": {}, "levelMembership": {}},
    }), encoding="utf-8")
    validation.write_text(cal.json_dumps({"relationships": {"hostMembership": {}, "roomMembership": {}, "levelMembership": {}}}), encoding="utf-8")

    code = script.main([
        "--model3dm", str(model),
        "--sidecar", str(sidecar),
        "--validation", str(validation),
        "--output-dir", str(tmp_path),
        "--name", "fixture",
        "--offline",
    ])

    assert code == 0
    report = tmp_path / "fixture.calibration.json"
    assert report.exists()
    assert '"mode": "offline_fixture_validation"' in report.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_live_calibrate_containment_fixture.py -q
```

Expected: FAIL because the script file does not exist.

- [ ] **Step 3: Implement offline-capable script skeleton**

Create `docs/rook_docs/rookbim-export-spike/live_calibrate_containment_fixture.py`:

```python
"""Gated live calibration for RookBIM threshold fixtures.

Offline mode validates fixture/report shape only. Live mode requires Rhino/Rook.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MCP_SRC = ROOT / "mcp_server" / "src"
if str(MCP_SRC) not in sys.path:
    sys.path.insert(0, str(MCP_SRC))

from rook.scene import calibration as cal  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model3dm", required=True)
    parser.add_argument("--sidecar", required=True)
    parser.add_argument("--validation", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--project-exact-adjacency", dest="project_exact_adjacency", action="store_true", default=True)
    parser.add_argument("--no-project-exact-adjacency", dest="project_exact_adjacency", action="store_false")
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--cap", type=int, default=None)
    return parser.parse_args(argv)


def run_offline(args) -> dict:
    paths = cal.FixturePaths(args.model3dm, args.sidecar, args.validation)
    loaded = cal.load_fixture_bundle(paths)
    report = cal.build_offline_fixture_validation_report(
        loaded.fixture,
        paths=loaded.paths,
        fixture_id=args.name,
    )
    cal.write_report_bundle(report, args.output_dir, args.name)
    return report


def run_live(args) -> dict:
    raise RuntimeError("live calibration orchestration is implemented in the next task")


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.offline:
        run_offline(args)
        return 0
    run_live(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run script tests and calibration tests**

Run:

```powershell
python -m pytest tests/test_calibration.py tests/test_live_calibrate_containment_fixture.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

Run:

```powershell
git branch --show-current
git add docs/rook_docs/rookbim-export-spike/live_calibrate_containment_fixture.py mcp_server/tests/test_live_calibrate_containment_fixture.py
git commit -m "feat(spatial): add offline calibration fixture runner"
```

---

### Task 6: Live Orchestration With Faked Runtime Calls

**Files:**
- Modify: `docs/rook_docs/rookbim-export-spike/live_calibrate_containment_fixture.py`
- Modify: `mcp_server/tests/test_live_calibrate_containment_fixture.py`

- [ ] **Step 1: Add failing tests for live orchestration order and honesty invariant**

Append to `mcp_server/tests/test_live_calibrate_containment_fixture.py`:

```python
def test_live_orchestration_runs_exact_before_refinement_and_never_passes_labels(monkeypatch, tmp_path):
    script = _load_script()
    model = tmp_path / "a.3dm"
    sidecar = tmp_path / "a.sidecar.json"
    validation = tmp_path / "a.validation.json"
    model.write_bytes(b"fake")
    sidecar.write_text(cal.json_dumps({
        "elements": [
            {"identity": {"uniqueId": "uid-wall", "elementId": 101}, "category": "Walls", "labels": {"hostId": {"value": None}, "containingRoomId": {"value": "room-1"}, "level": {"value": "L1"}}},
            {"identity": {"uniqueId": "uid-door", "elementId": 202}, "category": "Doors", "labels": {"hostId": {"value": "uid-wall"}, "containingRoomId": {"value": "room-1"}, "level": {"value": "L1"}}},
        ],
        "rooms": [],
        "relationships": {
            "hostMembership": [{"elementUniqueId": "uid-door", "hostUniqueId": "uid-wall"}],
            "roomMembership": [{"elementUniqueId": "uid-door", "roomUniqueId": "room-1"}, {"elementUniqueId": "uid-wall", "roomUniqueId": "room-1"}],
            "levelMembership": [{"elementUniqueId": "uid-door", "levelName": "L1"}, {"elementUniqueId": "uid-wall", "levelName": "L1"}],
        },
    }), encoding="utf-8")
    validation.write_text(cal.json_dumps({"relationships": {"hostMembership": {}, "roomMembership": {}, "levelMembership": {}}}), encoding="utf-8")
    calls = []

    monkeypatch.setattr(script, "discover_port", lambda: 9876)
    monkeypatch.setattr(script, "open_fixture_in_isolated_context", lambda port, path: {
        "freshDocument": True,
        "runtimeObjects": [
            {"runtimeId": "rook-wall", "name": "Wall", "layer": "RookBim::L1::Walls", "userStrings": {"revit.uniqueId": "uid-wall", "revit.elementId": "101", "revit.category": "Walls"}},
            {"runtimeId": "rook-door", "name": "Door", "layer": "RookBim::L1::Doors", "userStrings": {"revit.uniqueId": "uid-door", "revit.elementId": "202", "revit.category": "Doors"}},
        ],
    })

    def fake_exact(port, object_ids):
        calls.append(("exact", list(object_ids)))
        return {
            "attempted": True,
            "succeeded": True,
            "errors": [],
            "graphSequence": 7,
            "attemptedObjectCount": len(object_ids),
            "elapsedMs": 12,
        }

    def fake_refine(port, object_ids):
        calls.append(("refine", list(object_ids)))
        # Honesty invariant: runtime input ids only, no sidecar labels or Revit relationship maps.
        assert object_ids == ["rook-wall", "rook-door"]
        return {
            "status": {"attempted": True, "succeeded": True, "errors": []},
            "payload": {
                "success": True,
                "graphSequence": 7,
                "refined": [{
                    "candidateId": "rook-wall|contains|rook-door",
                    "containerId": "rook-wall",
                    "containedId": "rook-door",
                    "verdict": "contains_semantic",
                    "confidence": "high",
                    "reason": "strong_clearance_plausible_container",
                    "evidence": [{"signal": "bbox_margin", "polarity": "supports", "detail": "positive"}],
                }],
            },
        }

    monkeypatch.setattr(script, "run_exact_projection", fake_exact)
    monkeypatch.setattr(script, "run_containment_refinement", fake_refine)

    code = script.main([
        "--model3dm", str(model),
        "--sidecar", str(sidecar),
        "--validation", str(validation),
        "--output-dir", str(tmp_path),
        "--name", "fixture",
    ])

    assert code == 0
    assert calls[0][0] == "exact"
    assert calls[1][0] == "refine"
    assert (tmp_path / "fixture.calibration.json").exists()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_live_calibrate_containment_fixture.py -q
```

Expected: FAIL with missing live helper functions.

- [ ] **Step 3: Implement live orchestration helpers with HTTP seams**

Modify `docs/rook_docs/rookbim-export-spike/live_calibrate_containment_fixture.py`:

```python
import asyncio
import json
import time
import urllib.request

from rook.bridge import discover_instances
from rook.scene.scene_graph import get_scene_graph
from rook.scene.exact_projection import get_exact_projector
from rook.scene.containment_refinement import get_containment_refiner


def discover_port() -> int:
    instances = discover_instances()
    native = [i for i in instances if i.get("pluginType") == "native" and isinstance(i.get("port"), int)]
    if not native:
        raise RuntimeError("No native Rook instance found. Start Rhino/Rook before live calibration.")
    return int(native[0]["port"])


def _post(port: int, path: str, payload: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(port: int, path: str, timeout: int = 180) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def open_fixture_in_isolated_context(port: int, model3dm: str) -> dict:
    new_doc = _post(port, "/document/new", {})
    if not new_doc.get("success"):
        raise RuntimeError(f"failed to create fresh document: {new_doc}")
    imported = _post(port, "/import", {"path": model3dm})
    if not imported.get("success"):
        raise RuntimeError(f"failed to import fixture: {imported}")
    imported_ids = set((imported.get("data") or {}).get("importedIds") or [])
    graph = _get(port, "/scene/graph?depth=full")
    data = graph.get("data", {}) if graph.get("success") else {}
    runtime_objects = []
    for node in data.get("nodes", []):
        node_id = node.get("id")
        if imported_ids and node_id not in imported_ids:
            continue
        user_strings = node.get("userStrings") or node.get("user_strings") or {}
        if isinstance(user_strings, dict) and user_strings.get("revit.uniqueId"):
            runtime_objects.append({
                "runtimeId": node_id,
                "name": node.get("name", ""),
                "layer": node.get("layer", ""),
                "userStrings": user_strings,
            })
    return {
        "freshDocument": True,
        "importedIds": sorted(imported_ids),
        "runtimeObjects": runtime_objects,
        "graphSequence": data.get("sequence"),
    }


def run_exact_projection(port: int, object_ids: list[str]) -> dict:
    start = time.perf_counter()
    try:
        analytics = get_scene_graph()
        projector = get_exact_projector(analytics)
        result = asyncio.run(projector.project(object_ids, port=port))
        return {
            "attempted": True,
            "succeeded": bool(result.get("success")),
            "errors": [] if result.get("success") else [str(result.get("error") or result)],
            "graphSequence": result.get("graphSequence"),
            "attemptedObjectCount": len(object_ids),
            "elapsedMs": int((time.perf_counter() - start) * 1000),
        }
    except Exception as exc:
        return {
            "attempted": True,
            "succeeded": False,
            "errors": [str(exc)],
            "attemptedObjectCount": len(object_ids),
            "elapsedMs": int((time.perf_counter() - start) * 1000),
        }


def run_containment_refinement(port: int, object_ids: list[str]) -> dict:
    analytics = get_scene_graph()
    refiner = get_containment_refiner(analytics)
    result = asyncio.run(refiner.refine(object_ids, port=port))
    if not result.get("success"):
        raise RuntimeError(f"scene_refine_containment failed: {result}")
    return {
        "status": {"attempted": True, "succeeded": True, "errors": []},
        "payload": result,
    }
```

Then replace `run_live` with:

```python
def _bounded_object_ids(runtime_objects: list[dict], categories: list[str], cap: int | None) -> list[str]:
    ids = []
    categories_set = set(categories)
    for obj in runtime_objects:
        strings = obj.get("userStrings") or {}
        if categories_set and strings.get("revit.category") not in categories_set:
            continue
        rid = obj.get("runtimeId")
        if rid:
            ids.append(rid)
        if cap is not None and len(ids) >= cap:
            break
    return ids


def run_live(args) -> dict:
    paths = cal.FixturePaths(args.model3dm, args.sidecar, args.validation)
    loaded = cal.load_fixture_bundle(paths)
    port = discover_port()
    imported = open_fixture_in_isolated_context(port, args.model3dm)
    runtime_objects = imported["runtimeObjects"]
    join = cal.build_runtime_join_map(runtime_objects, loaded.fixture)
    object_ids = _bounded_object_ids(runtime_objects, args.category, args.cap)
    exact_status = {"attempted": False, "succeeded": False, "errors": []}
    if args.project_exact_adjacency:
        exact_status = run_exact_projection(port, object_ids)
    refine = run_containment_refinement(port, object_ids)
    candidates = [
        cal.classify_candidate(c, loaded.fixture)
        for c in cal.build_candidate_records(refine["payload"], join, loaded.fixture)
    ]
    candidates = cal.add_missed_labeled_relation_records(
        candidates,
        join,
        loaded.fixture,
        evaluated_runtime_ids=set(object_ids),
    )
    runtime = cal.RuntimeSummary(
        project_exact_adjacency=args.project_exact_adjacency,
        fresh_document=imported.get("freshDocument"),
        graph_sequence=refine["payload"].get("graphSequence") or imported.get("graphSequence"),
        scene_exact_neighbors=exact_status,
        scene_refine_containment=refine["status"],
        input_object_count=len(runtime_objects),
        joined_object_count=len(join.by_runtime_id),
        evaluated_object_count=len(object_ids),
        category_filters=args.category,
        cap=args.cap,
    )
    report = cal.build_live_calibration_report(
        loaded.fixture,
        paths=loaded.paths,
        fixture_id=args.name,
        runtime=runtime,
        candidates=candidates,
    )
    cal.write_report_bundle(report, args.output_dir, args.name)
    return report
```

The live script calls the Python read-model modules directly. HTTP remains limited to native Rhino
operations such as import/scene graph fetch. Do not move HTTP calls into `calibration.py`.

- [ ] **Step 4: Run script tests and library tests**

Run:

```powershell
python -m pytest tests/test_calibration.py tests/test_live_calibrate_containment_fixture.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

Run:

```powershell
git branch --show-current
git add docs/rook_docs/rookbim-export-spike/live_calibrate_containment_fixture.py mcp_server/tests/test_live_calibrate_containment_fixture.py
git commit -m "feat(spatial): orchestrate live containment calibration"
```

---

### Task 7: Verification Runs and Gated Live Calibration

**Files:**
- Modify only if needed after live findings:
  - `docs/rook_docs/rookbim-export-spike/live_calibrate_containment_fixture.py`
  - `mcp_server/src/rook/scene/calibration.py`
  - `mcp_server/tests/test_calibration.py`
  - `mcp_server/tests/test_live_calibrate_containment_fixture.py`

- [ ] **Step 1: Run focused unit tests**

Run from `C:/Users/aryan/source/repos/rook-spatial/mcp_server`:

```powershell
python -m pytest tests/test_calibration.py tests/test_live_calibrate_containment_fixture.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run existing read-model regression tests**

Run:

```powershell
python -m pytest tests/test_containment_refinement.py tests/test_exact_projection.py tests/test_scene_graph.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run offline validation against the existing fixture**

Use the known live-verified #263 bundle if it still exists:

```powershell
python ..\docs\rook_docs\rookbim-export-spike\live_calibrate_containment_fixture.py `
  --model3dm C:\Users\aryan\AppData\Local\Temp\rookbim_preset_live_fix\shell-preset.3dm `
  --sidecar C:\Users\aryan\AppData\Local\Temp\rookbim_preset_live_fix\shell-preset.sidecar.json `
  --validation C:\Users\aryan\AppData\Local\Temp\rookbim_preset_live_fix\shell-preset.validation.json `
  --output-dir C:\Users\aryan\AppData\Local\Temp\rookbim_preset_live_fix `
  --name shell-preset `
  --offline
```

Expected: writes:

```text
C:\Users\aryan\AppData\Local\Temp\rookbim_preset_live_fix\shell-preset.calibration.json
C:\Users\aryan\AppData\Local\Temp\rookbim_preset_live_fix\shell-preset.calibration.md
```

The JSON must contain `"mode": "offline_fixture_validation"` and no calibration metrics.

- [ ] **Step 4: Run gated live calibration**

With Rhino/Rook running in a clean or isolated document context:

```powershell
python ..\docs\rook_docs\rookbim-export-spike\live_calibrate_containment_fixture.py `
  --model3dm C:\Users\aryan\AppData\Local\Temp\rookbim_preset_live_fix\shell-preset.3dm `
  --sidecar C:\Users\aryan\AppData\Local\Temp\rookbim_preset_live_fix\shell-preset.sidecar.json `
  --validation C:\Users\aryan\AppData\Local\Temp\rookbim_preset_live_fix\shell-preset.validation.json `
  --output-dir C:\Users\aryan\AppData\Local\Temp\rookbim_preset_live_fix `
  --name shell-preset `
  --category Walls `
  --category Doors `
  --category Windows `
  --cap 500
```

Expected:

- JSON report has `"mode": "live_calibration"`.
- `runtime.projectExactAdjacency` is `true`.
- `runtime.sceneExactNeighbors.attempted` is `true`.
- `runtime.sceneExactNeighbors.attemptedObjectCount <= 500`.
- `runtime.sceneExactNeighbors.elapsedMs` is present.
- `runtime.sceneRefineContainment.succeeded` is `true`.
- `runtime.evaluatedObjectCount <= 500`.
- Candidate records include per-family buckets, `comparisonBasis`, and `metricEligible`.

- [ ] **Step 5: Inspect top review cases manually**

Open the Markdown report and inspect:

- high-confidence host-contradicted positives;
- host missed labeled relations;
- category-pair hotspots;
- any `not_joinable` count greater than zero;
- whether `ambiguous` is reserved for conflicting signals, not missing labels.

Do not change thresholds in this task.

- [ ] **Step 6: Commit verification adjustments only if code changed**

If live verification required script/library changes, run the focused tests again and commit:

```powershell
git branch --show-current
git add docs/rook_docs/rookbim-export-spike/live_calibrate_containment_fixture.py mcp_server/src/rook/scene/calibration.py mcp_server/tests/test_calibration.py mcp_server/tests/test_live_calibrate_containment_fixture.py
git commit -m "fix(spatial): stabilize threshold calibration runner"
```

Expected: only calibration files are staged.

---

## Final verification checklist

- [ ] `python -m pytest tests/test_calibration.py tests/test_live_calibrate_containment_fixture.py -q` passes.
- [ ] `python -m pytest tests/test_containment_refinement.py tests/test_exact_projection.py tests/test_scene_graph.py -q` passes.
- [ ] Offline report writes JSON + Markdown and says `offline_fixture_validation`.
- [ ] Live report writes JSON + Markdown and says `live_calibration`.
- [ ] Revit labels are not passed to runtime/refiner inputs.
- [ ] No global accuracy/F1 appears in JSON or Markdown.
- [ ] `write_report_bundle(...)` is the only disk-writing helper in `calibration.py`.
- [ ] Known runtime/local dirt remains unstaged.
