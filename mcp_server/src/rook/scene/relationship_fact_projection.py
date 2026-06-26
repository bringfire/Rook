from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
