from __future__ import annotations

from collections import defaultdict
from typing import Any

from .relationship_profile import (
    contact_kind_profile,
    relationship_profile,
    resolve_relationship_profile,
)
from .semantic_relationship_inspector import PROJECTION_KIND, query_semantic_relationships


DEFAULT_MAX_GROUPS = 8
DEFAULT_MAX_FACTS_PER_GROUP = 5
GROUP_UNKNOWN = "unknown"
VALID_DIRECTIONS = {"both", "outgoing", "incoming"}

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


def _object_ids_are_valid(object_ids: Any) -> bool:
    return isinstance(object_ids, list) and all(isinstance(object_id, str) for object_id in object_ids)


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
        "byRelationshipCategory": {},
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


def _enrich_fact(fact: dict[str, Any], profile_result: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(fact)
    relationship_entry = relationship_profile(profile_result, fact.get("relationship"))
    contact_entry = contact_kind_profile(profile_result, fact.get("contactKind"))
    enriched["relationshipLabel"] = relationship_entry.get("label")
    enriched["inverseRelationship"] = relationship_entry.get("inverse")
    enriched["relationshipCategory"] = relationship_entry.get("category")
    enriched["contactKindLabel"] = contact_entry.get("label")
    enriched["contactKindCategory"] = contact_entry.get("category")
    return enriched


def _line_for_fact(fact: dict[str, Any]) -> str:
    relationship = fact.get("relationshipLabel") or fact.get("relationship") or "relates to"
    inverse = fact.get("inverseRelationship") or "connected by"
    other_name = fact.get("otherName") or fact.get("otherObjectId")
    if fact.get("direction") == "outgoing":
        prefix = f"{relationship} {other_name}"
    else:
        prefix = f"{inverse} {other_name}"
    feature_part = ""
    if fact.get("fromFeature") and fact.get("toFeature"):
        feature_part = f" via {fact['fromFeature']} -> {fact['toFeature']}"
    details = [
        str(value)
        for value in (
            fact.get("contactKindLabel") or fact.get("contactKind"),
            fact.get("status"),
            fact.get("provenance"),
        )
        if value
    ]
    suffix = f", {', '.join(details)}" if details else ""
    return f"{prefix}{feature_part}{suffix}"


def _summary_for_facts(facts: list[dict[str, Any]]) -> dict[str, Any]:
    if not facts:
        return _zero_summary()
    by_relationship: dict[str, int] = {}
    by_relationship_category: dict[str, int] = {}
    by_direction: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_provenance: dict[str, int] = {}
    poses: set[str] = set()
    for fact in facts:
        _bump(by_relationship, fact.get("relationship"))
        _bump(by_relationship_category, fact.get("relationshipCategory"))
        _bump(by_direction, fact.get("direction"))
        _bump(by_status, fact.get("status"))
        _bump(by_provenance, fact.get("provenance"))
        if fact.get("pose") not in (None, ""):
            poses.add(str(fact["pose"]))
    return {
        "relationshipFactCount": len(facts),
        "relationshipViewCount": len(facts),
        "byRelationship": dict(sorted(by_relationship.items())),
        "byRelationshipCategory": dict(sorted(by_relationship_category.items())),
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
                "relationshipLabel": first.get("relationshipLabel"),
                "inverseRelationship": first.get("inverseRelationship"),
                "relationshipCategory": first.get("relationshipCategory"),
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
            "relationshipLabel": group.get("relationshipLabel"),
            "inverseRelationship": group.get("inverseRelationship"),
            "relationshipCategory": group.get("relationshipCategory"),
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
    profile_result: dict[str, Any],
) -> dict[str, Any]:
    facts = [_enrich_fact(fact, profile_result) for fact in entry.get("facts", [])]
    groups, expandable_groups = _groups_for_facts(
        facts,
        max_groups=max_groups,
        max_facts_per_group=max_facts_per_group,
    )
    object_id = str(entry.get("objectId"))
    return {
        "objectId": entry.get("objectId"),
        "exists": bool(entry.get("exists")),
        "name": entry.get("name"),
        **_card_metadata(analytics, object_id, bool(entry.get("exists"))),
        "summary": _summary_for_facts(facts),
        "groups": groups,
        "expandableGroups": expandable_groups,
    }


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
    project_root: str | None = None,
) -> dict[str, Any]:
    if object_ids is None or object_ids == []:
        return _validation_error(
            "missing_object_ids",
            "scene_object_semantic_context requires object_ids in v1",
        )
    if not _object_ids_are_valid(object_ids):
        return _validation_error(
            "invalid_object_ids",
            "scene_object_semantic_context requires object_ids to be a list of strings in v1",
        )
    if direction not in VALID_DIRECTIONS:
        return _validation_error(
            "invalid_direction",
            "direction must be one of: both, outgoing, incoming",
        )

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

    profile_result = resolve_relationship_profile(project_root=project_root)
    if profile_result.get("success") is False:
        return profile_result

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
        return raw

    cards = [
        _card_from_object_entry(
            analytics,
            entry,
            max_groups=resolved_max_groups,
            max_facts_per_group=resolved_max_facts_per_group,
            profile_result=profile_result,
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
