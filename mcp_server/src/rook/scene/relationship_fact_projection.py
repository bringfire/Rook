from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..bridge import call_rhino

PROJECTION_KIND = "relationship_fact_v1"
DEFAULT_SOURCE_MODE = "authored_graph_user_strings"
DEFAULT_CONFIDENCE = 1.0
DEFAULT_STATUS = "accepted"
ENGINE_VERSION = 1
USER_TEXT_OBJECT_GET_ROUTE = "/usertext/object-get"

INFO_DIAGNOSTIC_KEYS = {
    "filteredByGraphSource",
    "filteredByGraphRevision",
    "filteredByPose",
}

VALIDATION_DIAGNOSTIC_KEYS = {
    "recordsMissingGraphSource",
    "recordsMissingGraphRevision",
    "recordsMissingPose",
    "recordsMissingVisualType",
    "ownerObjectsMissingOwnerId",
    "featureObjectsMissingFeatureId",
    "featureObjectsMissingOwner",
    "relationshipObjectsMissingRelationshipId",
    "relationshipObjectsMissingRelationshipType",
    "relationshipObjectsMissingFeatureEndpoint",
    "relationshipFactsMissingFeatureEndpoint",
    "relationshipFactsMissingOwnerObject",
    "duplicateOwnerRecords",
    "duplicateFeatureRecords",
}


class RelationshipFactProjectionError(ValueError):
    """Raised when relationship fact projection input is invalid."""


@dataclass(frozen=True)
class RuntimeObjectRecord:
    object_id: str
    user_strings: dict[str, Any]


@dataclass(frozen=True)
class OwnerRecord:
    object_id: str
    graph_source: str
    graph_revision: str
    pose: str
    owner_kind: str
    owner_id: str


@dataclass(frozen=True)
class FeatureRecord:
    object_id: str
    graph_source: str
    graph_revision: str
    pose: str
    feature_id: str
    owner: str
    owner_kind: str
    feature_kind: str
    role: str


@dataclass(frozen=True)
class RelationshipRecord:
    object_id: str
    graph_source: str
    graph_revision: str
    pose: str
    relationship_id: str
    relationship_type: str
    from_feature: str
    to_feature: str
    contact_kind: str
    provenance: str
    confidence: float
    status: str
    source_mode: str


@dataclass(frozen=True)
class ParsedRuntimeRecords:
    owners_by_key: dict[tuple[str, str, str, str, str], OwnerRecord]
    features_by_key: dict[tuple[str, str, str, str], FeatureRecord]
    relationship_records: list[RelationshipRecord]
    diagnostics: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RelationshipFact:
    relationship_fact_id: str
    relationship_type: str
    from_feature: str
    to_feature: str
    from_owner: str
    from_owner_kind: str
    from_owner_object_id: str
    from_feature_object_id: str
    to_owner: str
    to_owner_kind: str
    to_owner_object_id: str
    to_feature_object_id: str
    relationship_object_id: str
    contact_kind: str
    provenance: str
    confidence: float
    status: str
    source_mode: str
    graph_source: str
    graph_revision: str
    pose: str


@dataclass(frozen=True)
class RelationshipFactSet:
    success: bool
    facts: list[RelationshipFact]
    diagnostics: dict[str, int]


@dataclass(frozen=True)
class RelationshipFactScope:
    graph_source: str | None = None
    graph_revision: str | None = None
    poses: list[str] | None = None
    source_mode: str = DEFAULT_SOURCE_MODE

    def matches_record(self, source: str, revision: str, pose: str, diagnostics: dict[str, int]) -> bool:
        if self.graph_source is not None and source != self.graph_source:
            _bump(diagnostics, "filteredByGraphSource")
            return False
        if self.graph_revision is not None and revision != self.graph_revision:
            _bump(diagnostics, "filteredByGraphRevision")
            return False
        if self.poses and pose not in set(self.poses):
            _bump(diagnostics, "filteredByPose")
            return False
        return True


@dataclass(frozen=True)
class ReplacementScope:
    graph_source: str | None = None
    graph_revision: str | None = None
    poses: list[str] | None = None
    primary_object_ids: list[str] | None = None
    source_mode: str = DEFAULT_SOURCE_MODE

    def matches_edge(self, source_id: str, target_id: str, attrs: dict[str, Any]) -> bool:
        if attrs.get("projectionKind") != PROJECTION_KIND:
            return False
        if attrs.get("sourceMode") != self.source_mode:
            return False
        if self.graph_source is not None and attrs.get("graphSource") != self.graph_source:
            return False
        if self.graph_revision is not None and attrs.get("graphRevision") != self.graph_revision:
            return False
        if self.poses and attrs.get("pose") not in set(self.poses):
            return False
        if self.primary_object_ids is not None:
            primary_ids = {str(object_id) for object_id in self.primary_object_ids}
            if source_id not in primary_ids and target_id not in primary_ids:
                return False
        return True


def _bump(diagnostics: dict[str, int], key: str) -> None:
    diagnostics[key] = diagnostics.get(key, 0) + 1


def _clean_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _clean_float(value: Any, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _common_scope(user_strings: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _clean_str(user_strings.get("rook.graph.source")),
        _clean_str(user_strings.get("rook.graph.revision")),
        _clean_str(user_strings.get("rook.graph.pose")),
    )


def _has_graph_user_strings(user_strings: dict[str, Any]) -> bool:
    return any(str(key).startswith("rook.graph.") for key in user_strings)


def _scope_is_valid(source: str, revision: str, pose: str, diagnostics: dict[str, int]) -> bool:
    valid = True
    if not source:
        _bump(diagnostics, "recordsMissingGraphSource")
        valid = False
    if not revision:
        _bump(diagnostics, "recordsMissingGraphRevision")
        valid = False
    if not pose:
        _bump(diagnostics, "recordsMissingPose")
        valid = False
    return valid


def _parse_owner_record(
    record: RuntimeObjectRecord,
    source: str,
    revision: str,
    pose: str,
    visual_type: str,
    diagnostics: dict[str, int],
) -> OwnerRecord | None:
    if visual_type == "member":
        owner_id = _clean_str(record.user_strings.get("rook.graph.member_id"))
        owner_kind = "member"
    elif visual_type == "joint":
        owner_id = _clean_str(record.user_strings.get("rook.graph.node_id"))
        owner_kind = "node"
    else:
        return None
    if not owner_id:
        _bump(diagnostics, "ownerObjectsMissingOwnerId")
        return None
    return OwnerRecord(record.object_id, source, revision, pose, owner_kind, owner_id)


def _parse_feature_record(
    record: RuntimeObjectRecord,
    source: str,
    revision: str,
    pose: str,
    diagnostics: dict[str, int],
) -> FeatureRecord | None:
    user_strings = record.user_strings
    feature_id = _clean_str(user_strings.get("rook.graph.feature_id"))
    owner = _clean_str(user_strings.get("rook.graph.owner"))
    owner_kind = _clean_str(user_strings.get("rook.graph.owner_kind"))
    if not feature_id:
        _bump(diagnostics, "featureObjectsMissingFeatureId")
        return None
    if not owner or not owner_kind:
        _bump(diagnostics, "featureObjectsMissingOwner")
        return None
    return FeatureRecord(
        object_id=record.object_id,
        graph_source=source,
        graph_revision=revision,
        pose=pose,
        feature_id=feature_id,
        owner=owner,
        owner_kind=owner_kind,
        feature_kind=_clean_str(user_strings.get("rook.graph.feature_kind")),
        role=_clean_str(user_strings.get("rook.graph.role")),
    )


def _parse_relationship_record(
    record: RuntimeObjectRecord,
    source: str,
    revision: str,
    pose: str,
    diagnostics: dict[str, int],
) -> RelationshipRecord | None:
    user_strings = record.user_strings
    relationship_id = _clean_str(user_strings.get("rook.graph.relationship_id"))
    relationship_type = _clean_str(user_strings.get("rook.graph.relationship_type"))
    from_feature = _clean_str(user_strings.get("rook.graph.from_feature"))
    to_feature = _clean_str(user_strings.get("rook.graph.to_feature"))
    if not relationship_id:
        _bump(diagnostics, "relationshipObjectsMissingRelationshipId")
        return None
    if not relationship_type:
        _bump(diagnostics, "relationshipObjectsMissingRelationshipType")
        return None
    if not from_feature or not to_feature:
        _bump(diagnostics, "relationshipObjectsMissingFeatureEndpoint")
        return None
    return RelationshipRecord(
        object_id=record.object_id,
        graph_source=source,
        graph_revision=revision,
        pose=pose,
        relationship_id=relationship_id,
        relationship_type=relationship_type,
        from_feature=from_feature,
        to_feature=to_feature,
        contact_kind=_clean_str(user_strings.get("rook.graph.contact_kind")),
        provenance=_clean_str(user_strings.get("rook.graph.provenance")) or "authored_assembly_graph",
        confidence=_clean_float(user_strings.get("rook.graph.confidence"), DEFAULT_CONFIDENCE),
        status=_clean_str(user_strings.get("rook.graph.status")) or DEFAULT_STATUS,
        source_mode=_clean_str(user_strings.get("rook.graph.sourceMode")) or DEFAULT_SOURCE_MODE,
    )


def parse_runtime_records(
    records: list[RuntimeObjectRecord],
    *,
    graph_source: str | None = None,
    graph_revision: str | None = None,
    poses: list[str] | None = None,
    source_mode: str = DEFAULT_SOURCE_MODE,
) -> ParsedRuntimeRecords:
    if source_mode != DEFAULT_SOURCE_MODE:
        raise RelationshipFactProjectionError(f"unsupported source_mode: {source_mode}")

    scope = RelationshipFactScope(
        graph_source=graph_source,
        graph_revision=graph_revision,
        poses=poses,
        source_mode=source_mode,
    )
    owners_by_key: dict[tuple[str, str, str, str, str], OwnerRecord] = {}
    features_by_key: dict[tuple[str, str, str, str], FeatureRecord] = {}
    relationship_records: list[RelationshipRecord] = []
    diagnostics: dict[str, int] = {}

    for record in records:
        user_strings = record.user_strings
        if not _has_graph_user_strings(user_strings):
            _bump(diagnostics, "ignoredNonGraphObjects")
            continue
        source, revision, pose = _common_scope(user_strings)
        if not _scope_is_valid(source, revision, pose, diagnostics):
            continue
        if not scope.matches_record(source, revision, pose, diagnostics):
            continue

        visual_type = _clean_str(user_strings.get("rook.graph.visual_type"))
        if visual_type in {"member", "joint"}:
            owner = _parse_owner_record(record, source, revision, pose, visual_type, diagnostics)
            if owner is None:
                continue
            key = (source, revision, pose, owner.owner_kind, owner.owner_id)
            if key in owners_by_key:
                _bump(diagnostics, "duplicateOwnerRecords")
            owners_by_key[key] = owner
        elif visual_type == "feature":
            feature = _parse_feature_record(record, source, revision, pose, diagnostics)
            if feature is None:
                continue
            key = (source, revision, pose, feature.feature_id)
            if key in features_by_key:
                _bump(diagnostics, "duplicateFeatureRecords")
            features_by_key[key] = feature
        elif visual_type == "relationship":
            relationship = _parse_relationship_record(record, source, revision, pose, diagnostics)
            if relationship is not None:
                relationship_records.append(relationship)
        else:
            _bump(diagnostics, "recordsMissingVisualType")

    return ParsedRuntimeRecords(
        owners_by_key=owners_by_key,
        features_by_key=features_by_key,
        relationship_records=relationship_records,
        diagnostics=diagnostics,
    )


def _merge_diagnostics(*sources: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for source in sources:
        for key, count in source.items():
            merged[key] = merged.get(key, 0) + count
    return merged


def relationship_fact_edge_key(fact: RelationshipFact) -> str:
    return (
        f"relationship_fact:{fact.source_mode}:{fact.graph_source}:"
        f"{fact.graph_revision}:{fact.pose}:{fact.relationship_fact_id}"
    )


def _validation_diagnostics(diagnostics: dict[str, int]) -> dict[str, int]:
    return {
        key: count
        for key, count in diagnostics.items()
        if key in VALIDATION_DIAGNOSTIC_KEYS and count
    }


def build_relationship_fact_set(
    parsed: ParsedRuntimeRecords,
    *,
    strict: bool = False,
) -> RelationshipFactSet:
    facts: list[RelationshipFact] = []
    diagnostics = dict(parsed.diagnostics)
    for relationship in parsed.relationship_records:
        source = relationship.graph_source
        revision = relationship.graph_revision
        pose = relationship.pose
        from_feature = parsed.features_by_key.get((source, revision, pose, relationship.from_feature))
        to_feature = parsed.features_by_key.get((source, revision, pose, relationship.to_feature))
        if from_feature is None or to_feature is None:
            _bump(diagnostics, "relationshipFactsMissingFeatureEndpoint")
            continue
        from_owner = parsed.owners_by_key.get((source, revision, pose, from_feature.owner_kind, from_feature.owner))
        to_owner = parsed.owners_by_key.get((source, revision, pose, to_feature.owner_kind, to_feature.owner))
        if from_owner is None or to_owner is None:
            _bump(diagnostics, "relationshipFactsMissingOwnerObject")
            continue
        facts.append(
            RelationshipFact(
                relationship_fact_id=relationship.relationship_id,
                relationship_type=relationship.relationship_type,
                from_feature=relationship.from_feature,
                to_feature=relationship.to_feature,
                from_owner=from_feature.owner,
                from_owner_kind=from_feature.owner_kind,
                from_owner_object_id=from_owner.object_id,
                from_feature_object_id=from_feature.object_id,
                to_owner=to_feature.owner,
                to_owner_kind=to_feature.owner_kind,
                to_owner_object_id=to_owner.object_id,
                to_feature_object_id=to_feature.object_id,
                relationship_object_id=relationship.object_id,
                contact_kind=relationship.contact_kind,
                provenance=relationship.provenance,
                confidence=relationship.confidence,
                status=relationship.status,
                source_mode=relationship.source_mode,
                graph_source=relationship.graph_source,
                graph_revision=relationship.graph_revision,
                pose=relationship.pose,
            )
        )

    validation_errors = _validation_diagnostics(diagnostics)
    if strict and validation_errors:
        keys = ", ".join(sorted(validation_errors))
        raise RelationshipFactProjectionError(f"relationship fact projection strict validation failed: {keys}")
    return RelationshipFactSet(success=True, facts=facts, diagnostics=diagnostics)


def resolve_relationship_facts(parsed: ParsedRuntimeRecords) -> list[RelationshipFact]:
    return build_relationship_fact_set(parsed, strict=False).facts


def prune_relationship_fact_projection(analytics: Any, scope: ReplacementScope) -> dict[str, Any]:
    graph = analytics.graph
    removed_edges = 0
    for u, v, key, attrs in list(graph.edges(keys=True, data=True)):
        if scope.matches_edge(str(u), str(v), attrs):
            graph.remove_edge(u, v, key=key)
            removed_edges += 1
    if removed_edges:
        analytics._invalidate_caches()
    return {"pruned": bool(removed_edges), "removedEdges": removed_edges}


def _edge_attrs(fact: RelationshipFact, graph_sequence: int) -> dict[str, Any]:
    return {
        "relationship": fact.relationship_type,
        "projectionKind": PROJECTION_KIND,
        "semanticRelationshipType": fact.relationship_type,
        "provenance": fact.provenance,
        "confidence": fact.confidence,
        "status": fact.status,
        "sourceMode": fact.source_mode,
        "contactKind": fact.contact_kind,
        "graphSource": fact.graph_source,
        "graphRevision": fact.graph_revision,
        "pose": fact.pose,
        "relationshipFactId": fact.relationship_fact_id,
        "fromFeature": fact.from_feature,
        "toFeature": fact.to_feature,
        "fromFeatureObjectId": fact.from_feature_object_id,
        "toFeatureObjectId": fact.to_feature_object_id,
        "relationshipObjectId": fact.relationship_object_id,
        "graphSequence": graph_sequence,
        "engineVersion": ENGINE_VERSION,
    }


def project_relationship_facts(
    analytics: Any,
    facts: list[RelationshipFact],
    *,
    prune_scope: ReplacementScope,
    prune: bool = False,
    diagnostics: dict[str, int] | None = None,
    owner_object_count: int = 0,
    feature_object_count: int = 0,
    relationship_object_count: int = 0,
    relationship_fact_count: int | None = None,
) -> dict[str, Any]:
    graph = analytics.graph
    prune_result = (
        prune_relationship_fact_projection(analytics, prune_scope)
        if prune
        else {"pruned": False, "removedEdges": 0}
    )
    by_relationship_type: dict[str, int] = {}
    by_pose: dict[str, int] = {}
    projected = 0
    skipped = 0

    for fact in facts:
        if not graph.has_node(fact.from_owner_object_id) or not graph.has_node(fact.to_owner_object_id):
            skipped += 1
            continue
        graph.add_edge(
            fact.from_owner_object_id,
            fact.to_owner_object_id,
            key=relationship_fact_edge_key(fact),
            **_edge_attrs(fact, getattr(analytics, "sequence", 0)),
        )
        projected += 1
        by_relationship_type[fact.relationship_type] = by_relationship_type.get(fact.relationship_type, 0) + 1
        by_pose[fact.pose] = by_pose.get(fact.pose, 0) + 1

    if projected or prune_result.get("removedEdges"):
        analytics._invalidate_caches()

    return {
        "success": True,
        "projectionKind": PROJECTION_KIND,
        "sourceMode": DEFAULT_SOURCE_MODE,
        "graphSequence": getattr(analytics, "sequence", 0),
        "counts": {
            "ownerObjectCount": owner_object_count,
            "featureObjectCount": feature_object_count,
            "relationshipObjectCount": relationship_object_count,
            "relationshipFactCount": relationship_fact_count if relationship_fact_count is not None else len(facts),
            "projectedEdgeCount": projected,
            "skippedFactCount": skipped,
        },
        "byRelationshipType": by_relationship_type,
        "byPose": by_pose,
        "diagnostics": diagnostics or {},
        "samples": {},
        "prune": prune_result,
    }


def _is_runtime_rhino_node(attrs: dict[str, Any]) -> bool:
    return not attrs.get("projectionKind")


def _scene_candidate_object_ids(analytics: Any) -> list[str]:
    return [
        str(node_id)
        for node_id, attrs in analytics.graph.nodes(data=True)
        if _is_runtime_rhino_node(attrs)
    ]


def _extract_user_strings(response: dict[str, Any]) -> dict[str, Any] | None:
    if not response.get("success"):
        return None
    data = response.get("data")
    if not isinstance(data, dict):
        return None
    user_strings = data.get("userStrings")
    return user_strings if isinstance(user_strings, dict) else None


async def hydrate_runtime_object_records(
    object_ids: list[str],
    *,
    port: int | None = None,
) -> tuple[list[RuntimeObjectRecord], dict[str, int]]:
    records: list[RuntimeObjectRecord] = []
    diagnostics: dict[str, int] = {}
    for object_id in object_ids:
        try:
            response = await call_rhino(USER_TEXT_OBJECT_GET_ROUTE, "POST", {"id": object_id}, port=port)
        except Exception:
            _bump(diagnostics, "hydrationFailures")
            continue
        user_strings = _extract_user_strings(response)
        if user_strings is None:
            _bump(diagnostics, "hydrationFailures")
            continue
        records.append(RuntimeObjectRecord(object_id=object_id, user_strings=user_strings))
    return records, diagnostics


def _filter_facts_for_primary_scope(
    facts: list[RelationshipFact],
    object_ids: list[str] | None,
) -> list[RelationshipFact]:
    if object_ids is None:
        return facts
    primary_ids = {str(object_id) for object_id in object_ids}
    return [
        fact
        for fact in facts
        if fact.from_owner_object_id in primary_ids or fact.to_owner_object_id in primary_ids
    ]


def _build_projection_response(
    projection: dict[str, Any],
    *,
    candidate_object_count: int,
    hydrated_object_count: int,
) -> dict[str, Any]:
    counts = dict(projection["counts"])
    counts["candidateObjectCount"] = candidate_object_count
    counts["hydratedObjectCount"] = hydrated_object_count
    projection["counts"] = counts
    return projection


async def project_relationship_facts_for_tool(
    *,
    graph_source: str | None = None,
    graph_revision: str | None = None,
    poses: list[str] | None = None,
    object_ids: list[str] | None = None,
    source_mode: str = DEFAULT_SOURCE_MODE,
    strict: bool = False,
    port: int | None = None,
    analytics: Any | None = None,
) -> dict[str, Any]:
    if source_mode != DEFAULT_SOURCE_MODE:
        return {
            "success": False,
            "error": "relationship_fact_projection_invalid_source_mode",
            "message": f"Unsupported source_mode: {source_mode}",
        }

    if analytics is None:
        from .scene_graph import get_scene_graph

        analytics = get_scene_graph()

    await analytics.sync(port=port)
    candidate_object_ids = _scene_candidate_object_ids(analytics)
    records, hydration_diagnostics = await hydrate_runtime_object_records(candidate_object_ids, port=port)

    try:
        parsed = parse_runtime_records(
            records,
            graph_source=graph_source,
            graph_revision=graph_revision,
            poses=poses,
            source_mode=source_mode,
        )
        fact_set = build_relationship_fact_set(parsed, strict=strict)
    except RelationshipFactProjectionError as exc:
        return {
            "success": False,
            "error": "relationship_fact_projection_validation_failed",
            "message": str(exc),
        }

    diagnostics = _merge_diagnostics(hydration_diagnostics, fact_set.diagnostics)
    facts_to_project = _filter_facts_for_primary_scope(fact_set.facts, object_ids)
    projection = project_relationship_facts(
        analytics,
        facts_to_project,
        prune_scope=ReplacementScope(
            graph_source=graph_source,
            graph_revision=graph_revision,
            poses=poses,
            primary_object_ids=object_ids,
            source_mode=source_mode,
        ),
        prune=True,
        diagnostics=diagnostics,
        owner_object_count=len(parsed.owners_by_key),
        feature_object_count=len(parsed.features_by_key),
        relationship_object_count=len(parsed.relationship_records),
        relationship_fact_count=len(fact_set.facts),
    )
    return _build_projection_response(
        projection,
        candidate_object_count=len(candidate_object_ids),
        hydrated_object_count=len(records),
    )
