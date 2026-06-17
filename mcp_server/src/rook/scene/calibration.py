"""Offline calibration fixture parsing and report schema helpers.

Revit sidecar labels and relationship indexes are post-hoc evaluation data for
calibration only. This module intentionally does not call runtime scene graph
projection, containment refinement, or mutation paths.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MODE_LIVE = "live_calibration"
MODE_OFFLINE = "offline_fixture_validation"
REQUIRED_RELATIONSHIPS = (
    "hostMembership",
    "roomMembership",
    "levelMembership",
)

_RELATIONSHIP_VALUE_KEYS = {
    "hostMembership": "hostUniqueId",
    "roomMembership": "roomUniqueId",
    "levelMembership": "levelName",
}


class FixtureValidationError(ValueError):
    """Raised when a calibration fixture bundle is missing required data."""


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
    relationships: dict[str, dict[str, Any]]
    rooms_by_unique_id: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class LoadedFixture:
    paths: FixturePaths
    fixture: FixtureData


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


def json_dumps(value: Any) -> str:
    """Serialize fixture JSON consistently for tests and report artifacts."""
    return json.dumps(value, indent=2, sort_keys=True)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FixtureValidationError(f"{name} must be an object")
    return value


def validate_fixture_payload(
    sidecar_payload: dict[str, Any],
    validation_payload: dict[str, Any],
) -> FixtureData:
    """Validate and normalize the Revit fixture sidecar and validation payloads."""
    sidecar = _require_dict(sidecar_payload, "sidecar")
    validation = _require_dict(validation_payload, "validation")

    elements = sidecar.get("elements")
    if not isinstance(elements, list):
        raise FixtureValidationError("sidecar.elements must be a list")

    elements_by_unique_id: dict[str, dict[str, Any]] = {}
    for index, element in enumerate(elements):
        element_dict = _require_dict(element, f"sidecar.elements[{index}]")
        unique_id = _element_unique_id(element_dict)
        if not unique_id:
            raise FixtureValidationError(f"sidecar.elements[{index}] is missing a unique id")
        if unique_id in elements_by_unique_id:
            raise FixtureValidationError(f"duplicate element unique id: {unique_id}")
        elements_by_unique_id[unique_id] = element_dict

    rooms = sidecar.get("rooms", [])
    if rooms is None:
        rooms = []
    if not isinstance(rooms, list):
        raise FixtureValidationError("sidecar.rooms must be a list when present")

    rooms_by_unique_id: dict[str, dict[str, Any]] = {}
    for index, room in enumerate(rooms):
        room_dict = _require_dict(room, f"sidecar.rooms[{index}]")
        unique_id = room_dict.get("uniqueId")
        if isinstance(unique_id, str) and unique_id:
            rooms_by_unique_id[unique_id] = room_dict

    relationships = _normalize_relationships(sidecar)
    _validate_relationship_integrity(
        relationships,
        elements_by_unique_id=elements_by_unique_id,
        rooms_by_unique_id=rooms_by_unique_id,
    )
    _validate_relationship_counts(relationships, validation)

    return FixtureData(
        sidecar=sidecar,
        validation=validation,
        elements_by_unique_id=elements_by_unique_id,
        relationships=relationships,
        rooms_by_unique_id=rooms_by_unique_id,
    )


def _element_unique_id(element: dict[str, Any]) -> str | None:
    identity = element.get("identity")
    if isinstance(identity, dict):
        unique_id = identity.get("uniqueId")
        if isinstance(unique_id, str) and unique_id:
            return unique_id

    for key in ("uniqueId", "revitUniqueId"):
        unique_id = element.get(key)
        if isinstance(unique_id, str) and unique_id:
            return unique_id

    return None


def _normalize_relationships(sidecar: dict[str, Any]) -> dict[str, dict[str, Any]]:
    relationships = _require_dict(sidecar.get("relationships"), "sidecar.relationships")
    normalized: dict[str, dict[str, Any]] = {}

    for relationship_name in REQUIRED_RELATIONSHIPS:
        if relationship_name not in relationships:
            raise FixtureValidationError(f"sidecar.relationships.{relationship_name} is required")
        normalized[relationship_name] = _normalize_membership(
            relationships[relationship_name],
            relationship_name=relationship_name,
            value_key=_RELATIONSHIP_VALUE_KEYS[relationship_name],
        )

    return normalized


def _normalize_membership(
    membership: Any,
    *,
    relationship_name: str,
    value_key: str,
) -> dict[str, Any]:
    if isinstance(membership, dict):
        return dict(membership)

    if not isinstance(membership, list):
        raise FixtureValidationError(f"sidecar.relationships.{relationship_name} must be a list or object")

    normalized: dict[str, Any] = {}
    for index, record in enumerate(membership):
        record_dict = _require_dict(
            record,
            f"sidecar.relationships.{relationship_name}[{index}]",
        )
        element_unique_id = record_dict.get("elementUniqueId")
        value = record_dict.get(value_key)
        if not element_unique_id:
            raise FixtureValidationError(
                f"sidecar.relationships.{relationship_name}[{index}] is missing elementUniqueId"
            )
        if value is None:
            continue
        element_key = str(element_unique_id)
        if element_key in normalized:
            raise FixtureValidationError(
                f"duplicate {relationship_name} relationship for element {element_key}"
            )
        normalized[element_key] = value

    return normalized


def _validate_relationship_integrity(
    relationships: dict[str, dict[str, Any]],
    *,
    elements_by_unique_id: dict[str, dict[str, Any]],
    rooms_by_unique_id: dict[str, dict[str, Any]],
) -> None:
    for element_unique_id, host_unique_id in relationships["hostMembership"].items():
        _require_known_element("hostMembership", "source element", element_unique_id, elements_by_unique_id)
        _require_known_element("hostMembership", "target host", host_unique_id, elements_by_unique_id)

    for element_unique_id, room_unique_id in relationships["roomMembership"].items():
        _require_known_element("roomMembership", "source element", element_unique_id, elements_by_unique_id)
        if room_unique_id not in rooms_by_unique_id:
            raise FixtureValidationError(f"roomMembership target room {room_unique_id} is not in rooms")

    for element_unique_id, level_name in relationships["levelMembership"].items():
        _require_known_element("levelMembership", "source element", element_unique_id, elements_by_unique_id)
        if not isinstance(level_name, str) or not level_name:
            raise FixtureValidationError(
                f"levelMembership level name for element {element_unique_id} must be a non-empty string"
            )


def _require_known_element(
    relationship_name: str,
    role: str,
    unique_id: Any,
    elements_by_unique_id: dict[str, dict[str, Any]],
) -> None:
    if unique_id not in elements_by_unique_id:
        raise FixtureValidationError(f"{relationship_name} {role} {unique_id} is not in elements")


def _validate_relationship_counts(
    relationships: dict[str, dict[str, Any]],
    validation: dict[str, Any],
) -> None:
    validation_relationships = validation.get("relationships")
    if validation_relationships is None:
        return
    if not isinstance(validation_relationships, dict):
        raise FixtureValidationError("validation.relationships must be an object when present")

    for relationship_name in REQUIRED_RELATIONSHIPS:
        validation_record = validation_relationships.get(relationship_name)
        if validation_record is None:
            continue
        if not isinstance(validation_record, dict):
            raise FixtureValidationError(f"validation.relationships.{relationship_name} must be an object")
        expected_count = validation_record.get("count")
        if expected_count is None:
            continue
        if expected_count != len(relationships[relationship_name]):
            raise FixtureValidationError(
                f"{relationship_name} count mismatch: validation has "
                f"{expected_count}, sidecar has {len(relationships[relationship_name])}"
            )


def load_fixture_bundle(paths: FixturePaths) -> LoadedFixture:
    """Read and validate a 3dm/sidecar/validation fixture bundle."""
    model_path = Path(paths.model3dm)
    sidecar_path = Path(paths.sidecar)
    validation_path = Path(paths.validation)

    for name, path in (
        ("model3dm", model_path),
        ("sidecar", sidecar_path),
        ("validation", validation_path),
    ):
        if not path.exists():
            raise FixtureValidationError(f"{name} path does not exist: {path}")

    sidecar = _read_json_file(sidecar_path, "sidecar")
    validation = _read_json_file(validation_path, "validation")
    fixture = validate_fixture_payload(sidecar, validation)
    return LoadedFixture(paths=paths, fixture=fixture)


def _read_json_file(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FixtureValidationError(f"invalid {label} JSON at {path}: {exc}") from exc


def build_offline_fixture_validation_report(
    fixture: FixtureData,
    *,
    paths: FixturePaths,
    fixture_id: str,
) -> dict[str, Any]:
    """Build the offline report envelope before runtime metrics are computed."""
    relationship_indexes = {
        name: name in fixture.relationships
        for name in REQUIRED_RELATIONSHIPS
    }

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
                "summary": {
                    "metricsComputed": False,
                    "elementCount": len(fixture.elements_by_unique_id),
                    "roomCount": len(fixture.rooms_by_unique_id),
                    "relationshipIndexes": relationship_indexes,
                },
                "metrics": {},
                "candidates": [],
            }
        ],
    }


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
    container_labels = candidate["container"].get("labels", {})
    contained_labels = candidate["contained"].get("labels", {})
    expected_host = host_map.get(contained_uid) or _label_value(contained_labels.get("host"))
    container_host = host_map.get(container_uid) or _label_value(container_labels.get("host"))

    if _positive(candidate):
        if container_host == contained_uid:
            return "host_contradicted_positive", "host_unique_id", True
        if not expected_host:
            return "host_missing_label", "none", False
        if expected_host == container_uid:
            return "host_supported_positive", "host_unique_id", True
        return "host_contradicted_positive", "host_unique_id", True

    if not expected_host:
        return "host_missing_label", "none", False
    if expected_host == container_uid:
        return "host_missed_labeled_relation", "host_unique_id", True
    return "host_not_applicable", "none", False


def _room_bucket(candidate: dict[str, Any], fixture: FixtureData) -> tuple[str, str, bool]:
    container_uid = _uid(candidate["container"])
    contained_uid = _uid(candidate["contained"])
    if not container_uid or not contained_uid:
        return "room_not_applicable", "none", False

    room_map = fixture.relationships.get("roomMembership") or {}
    container_labels = candidate["container"].get("labels", {})
    contained_labels = candidate["contained"].get("labels", {})
    container_room = room_map.get(container_uid) or _label_value(container_labels.get("room"))
    contained_room = room_map.get(contained_uid) or _label_value(contained_labels.get("room"))

    if container_uid in fixture.rooms_by_unique_id:
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
    container_labels = candidate["container"].get("labels", {})
    contained_labels = candidate["contained"].get("labels", {})
    container_level = level_map.get(container_uid) or _label_value(container_labels.get("level"))
    contained_level = level_map.get(contained_uid) or _label_value(contained_labels.get("level"))

    if not container_level or not contained_level:
        return "level_missing_label", "same_level", False
    if _positive(candidate) and container_level != contained_level:
        return "level_contradicted_positive", "same_level", True
    return "level_not_applicable", "same_level", False


def _review_bucket(
    host_bucket: str,
    room_bucket: str,
    level_bucket: str,
) -> str:
    meaningful_host_buckets = {
        "host_supported_positive",
        "host_contradicted_positive",
        "host_missed_labeled_relation",
        "host_missing_label",
    }
    if host_bucket in meaningful_host_buckets:
        return host_bucket

    context_buckets = [room_bucket, level_bucket]
    review = next((bucket for bucket in context_buckets if "contradicted_positive" in bucket), None)
    if review is None:
        review = next((bucket for bucket in context_buckets if "missed_labeled_relation" in bucket), None)
    if review is None:
        review = next((bucket for bucket in context_buckets if "supported_positive" in bucket), None)
    return review or "not_applicable"


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
    review_bucket = _review_bucket(host_bucket, room_bucket, level_bucket)

    out = dict(candidate)
    out.update({
        "hostBucket": host_bucket,
        "roomBucket": room_bucket,
        "levelBucket": level_bucket,
        "reviewBucket": review_bucket,
        "comparisonBasis": {"host": host_basis, "room": room_basis, "level": level_basis},
        "metricEligible": {"host": host_eligible, "room": room_eligible, "level": level_eligible},
    })
    return out


def _candidate_uid_pairs(candidates: list[dict[str, Any]]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for candidate in candidates:
        container_uid = _uid(candidate.get("container", {}))
        contained_uid = _uid(candidate.get("contained", {}))
        if container_uid and contained_uid:
            pairs.add((container_uid, contained_uid))
    return pairs


def add_missed_labeled_relation_records(
    classified_candidates: list[dict[str, Any]],
    join: RuntimeJoinMap,
    fixture: FixtureData,
    *,
    evaluated_runtime_ids: set[str],
) -> list[dict[str, Any]]:
    """Append in-scope host misses without using labels in runtime/refiner inputs."""
    out = list(classified_candidates)
    existing_pairs = _candidate_uid_pairs(out)
    host_map = fixture.relationships.get("hostMembership") or {}

    for contained_uid, host_uid in host_map.items():
        if not contained_uid or not host_uid or (host_uid, contained_uid) in existing_pairs:
            continue

        host_objects = join.by_revit_unique_id.get(host_uid) or []
        contained_objects = join.by_revit_unique_id.get(contained_uid) or []
        if not host_objects or not contained_objects:
            continue

        host_obj = host_objects[0]
        contained_obj = contained_objects[0]
        if host_obj.runtime_id not in evaluated_runtime_ids or contained_obj.runtime_id not in evaluated_runtime_ids:
            continue

        out.append({
            "candidateId": f"{host_obj.runtime_id}|contains|{contained_obj.runtime_id}|missed_host",
            "container": _endpoint_payload(host_obj, host_obj.runtime_id),
            "contained": _endpoint_payload(contained_obj, contained_obj.runtime_id),
            "rook": {
                "verdict": "missing_positive",
                "confidence": "none",
                "reason": "no_contains_semantic_candidate",
                "evidence": [],
            },
            "fixtureRelationships": {
                "hostMembership": fixture.relationships.get("hostMembership", {}),
                "roomMembership": fixture.relationships.get("roomMembership", {}),
                "levelMembership": fixture.relationships.get("levelMembership", {}),
            },
            "hostBucket": "host_missed_labeled_relation",
            "roomBucket": "room_not_applicable",
            "levelBucket": "level_not_applicable",
            "reviewBucket": "host_missed_labeled_relation",
            "comparisonBasis": {"host": "host_unique_id", "room": "none", "level": "none"},
            "metricEligible": {"host": True, "room": False, "level": False},
        })

    return out
