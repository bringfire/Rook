# Relationship Fact Projection v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python read-model projector that turns authored Rhino object user-string relationship facts into semantic `connects` edges in Rook's in-memory NetworkX scene graph.

**Architecture:** Follow the existing BIM relationship projection pattern, but keep the model neutral as `RelationshipFact` rather than robot-specific or BIM-specific. The pure core parses owner, feature, and relationship records, projects owner-object-to-owner-object edges, and keeps projection artifacts idempotent and pruneable. The MCP tool hydrates current scene objects through `/usertext/object-get`, projects into `SceneGraphAnalytics.graph`, and exposes results through projection response counts plus `scene_context(sync=false)`.

**Tech Stack:** Python 3.10+, NetworkX `MultiDiGraph`, pytest, pytest-asyncio, Rook MCP server, Rhino `/usertext/object-get` read route.

---

## Execution Context

Use the isolated Pearson worktree, not the clean packaging checkout:

```powershell
cd C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph
git status --short --branch
```

Expected:

```text
## codex/pearson-robot-feature-graph...origin/codex/pearson-robot-feature-graph
```

Keep `C:/Users/aryan/source/repos/Rook` on `main` untouched while installer packaging continues elsewhere.

## Reference Inputs

Design spec:

```text
docs/superpowers/specs/2026-06-26-relationship-fact-projection-v1-design.md
```

Existing pattern to mirror:

```text
mcp_server/src/rook/scene/bim_relationship_projection.py
mcp_server/tests/test_bim_relationship_projection.py
mcp_server/tests/test_bim_relationship_projection_tool.py
```

Robot experiment source data and screenshot evidence:

```text
experiments/pearson_robot_skeleton_graph/assembly_graph.json
experiments/pearson_robot_skeleton_graph/screenshots/g002_feature_graph_plain.png
```

## File Structure

Create:

- `mcp_server/src/rook/scene/relationship_fact_projection.py`
  - Pure dataclasses, parsing, owner resolution, deterministic edge keys, projection, pruning, hydration orchestration, and tool response flattening.
- `mcp_server/tests/test_relationship_fact_projection.py`
  - Pure tests for parsing, defaults, owner projection, edge metadata, idempotency, pruning, scoped pruning, strict/lenient diagnostics, and source safety.
- `mcp_server/tests/test_relationship_fact_projection_tool.py`
  - Tool tests for MCP schema, local dispatcher, targeting policy, hydration orchestration, server dispatch, and `scene_context(sync=false)`.

Modify:

- `mcp_server/src/rook/scene/scene_graph.py`
  - Add friendly context formatting for `relationship_fact_v1` `connects` edges.
- `mcp_server/src/rook/server.py`
  - Add MCP tool schema and `_call_tool_dispatch` dispatch for `scene_project_relationship_facts`.
- `mcp_server/src/rook/agent/tool_dispatcher.py`
  - Add local agent-direct handler for `scene_project_relationship_facts`.
- `mcp_server/src/rook/agent/tool_groups.py`
  - Add the new tool to the `scene_graph` group.
- `mcp_server/src/rook/targeting.py`
  - Add the new tool to `_ALL_KNOWN_TOOLS` and `_RHINO_READ_TOOLS`.

Do not modify:

- Native C++ scene graph code.
- Managed C# code.
- Rhino document mutation routes.
- The generic `scene_stats` contract.

Modularity rule for `relationship_fact_projection.py`:

- Keep public orchestration functions thin: `project_relationship_facts_for_tool`, `parse_runtime_records`, and `project_relationship_facts`.
- Split parser branches into `_parse_owner_record`, `_parse_feature_record`, and `_parse_relationship_record`.
- Use `RelationshipFactScope` / `ReplacementScope` helpers with `matches_record()` and `matches_edge()` instead of open-coded scope checks.
- Add `_filter_facts_for_primary_scope(facts, object_ids)` so scoped calls hydrate the full scene for dependency resolution but project only facts whose owner endpoint is in the requested primary object scope.
- Keep response shaping in `_build_projection_response(...)`.

## Task 1: Pure Relationship Fact Model and Parsing

**Files:**
- Create: `mcp_server/src/rook/scene/relationship_fact_projection.py`
- Create: `mcp_server/tests/test_relationship_fact_projection.py`

- [ ] **Step 1: Write failing tests for constants, source safety, and parsing defaults**

Create `mcp_server/tests/test_relationship_fact_projection.py` with this initial content:

```python
import ast
from pathlib import Path

import pytest

from rook.scene import relationship_fact_projection as rel


def _owner_record(object_id: str, *, pose: str = "reclined_robot") -> rel.RuntimeObjectRecord:
    return rel.RuntimeObjectRecord(
        object_id,
        {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": pose,
            "rook.graph.visual_type": "member",
            "rook.graph.member_id": "spine_base_to_spine_top",
            "rook.graph.feature_ids": "spine_base_to_spine_top.start,spine_base_to_spine_top.end",
            "rook.graph.relationship_ids": "spine_base_to_spine_top.start_connects_spine_base",
        },
    )


def _joint_record(object_id: str, *, pose: str = "reclined_robot") -> rel.RuntimeObjectRecord:
    return rel.RuntimeObjectRecord(
        object_id,
        {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": pose,
            "rook.graph.visual_type": "joint",
            "rook.graph.node_id": "spine_base",
            "rook.graph.feature_ids": "spine_base.point",
            "rook.graph.relationship_ids": "spine_base_to_spine_top.start_connects_spine_base",
        },
    )


def _feature_record(
    object_id: str,
    feature_id: str,
    owner: str,
    owner_kind: str,
    *,
    pose: str = "reclined_robot",
) -> rel.RuntimeObjectRecord:
    return rel.RuntimeObjectRecord(
        object_id,
        {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": pose,
            "rook.graph.visual_type": "feature",
            "rook.graph.feature_id": feature_id,
            "rook.graph.owner": owner,
            "rook.graph.owner_kind": owner_kind,
            "rook.graph.feature_kind": "endpoint",
            "rook.graph.role": "start",
            "rook.graph.true_position_m": "[0.0, 0.0, 0.0]",
            "rook.graph.visual_lift_m": "0.08",
        },
    )


def _relationship_record(object_id: str, *, pose: str = "reclined_robot") -> rel.RuntimeObjectRecord:
    return rel.RuntimeObjectRecord(
        object_id,
        {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": pose,
            "rook.graph.visual_type": "relationship",
            "rook.graph.relationship_id": "spine_base_to_spine_top.start_connects_spine_base",
            "rook.graph.relationship_type": "connects",
            "rook.graph.from_feature": "spine_base_to_spine_top.start",
            "rook.graph.to_feature": "spine_base.point",
            "rook.graph.contact_kind": "point_to_point",
            "rook.graph.provenance": "authored_assembly_graph",
        },
    )


def _valid_records() -> list[rel.RuntimeObjectRecord]:
    return [
        _owner_record("member-rhino-id"),
        _joint_record("joint-rhino-id"),
        _feature_record(
            "feature-member-start-id",
            "spine_base_to_spine_top.start",
            "spine_base_to_spine_top",
            "member",
        ),
        _feature_record("feature-joint-point-id", "spine_base.point", "spine_base", "node"),
        _relationship_record("relationship-marker-id"),
    ]


def test_module_constants():
    assert rel.PROJECTION_KIND == "relationship_fact_v1"
    assert rel.DEFAULT_SOURCE_MODE == "authored_graph_user_strings"
    assert rel.DEFAULT_CONFIDENCE == 1.0
    assert rel.DEFAULT_STATUS == "accepted"
    assert rel.ENGINE_VERSION == 1


def test_projector_source_is_read_only_and_uses_object_get():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "rook"
        / "scene"
        / "relationship_fact_projection.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden = [
        "/usertext/object-set",
        "/usertext/object-delete",
        "/usertext/document-set",
        "/usertext/document-delete",
        "/document/save",
        "scene_exact_neighbors",
        "scene_refine_containment",
    ]

    executable_tokens: set[str] = set()
    docstring_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                value = node.body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    docstring_nodes.add(value)

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node not in docstring_nodes:
                executable_tokens.add(node.value)
        elif isinstance(node, ast.Name):
            executable_tokens.add(node.id)
        elif isinstance(node, ast.Attribute):
            executable_tokens.add(node.attr)

    assert "/usertext/object-get" in executable_tokens
    for token in forbidden:
        assert not any(token in executable_token for executable_token in executable_tokens)


def test_parse_runtime_records_defaults_missing_fact_fields():
    parsed = rel.parse_runtime_records(_valid_records())

    assert parsed.diagnostics == {}
    assert set(parsed.owners_by_key) == {
        ("pearson_robot_skeleton_graph", "g002", "reclined_robot", "member", "spine_base_to_spine_top"),
        ("pearson_robot_skeleton_graph", "g002", "reclined_robot", "node", "spine_base"),
    }
    assert set(parsed.features_by_key) == {
        ("pearson_robot_skeleton_graph", "g002", "reclined_robot", "spine_base_to_spine_top.start"),
        ("pearson_robot_skeleton_graph", "g002", "reclined_robot", "spine_base.point"),
    }
    assert len(parsed.relationship_records) == 1
    relationship = parsed.relationship_records[0]
    assert relationship.relationship_id == "spine_base_to_spine_top.start_connects_spine_base"
    assert relationship.relationship_type == "connects"
    assert relationship.confidence == 1.0
    assert relationship.status == "accepted"
    assert relationship.source_mode == "authored_graph_user_strings"


def test_parse_runtime_records_requires_pose_for_graph_records():
    bad_relationship = _relationship_record("relationship-marker-id")
    bad_relationship.user_strings.pop("rook.graph.pose")

    parsed = rel.parse_runtime_records([bad_relationship])

    assert parsed.relationship_records == []
    assert parsed.diagnostics["recordsMissingPose"] == 1
```

- [ ] **Step 2: Run the new test file and verify it fails because the module is missing**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection.py -q
```

Expected: FAIL with `ImportError` or `ModuleNotFoundError` for `relationship_fact_projection`.

- [ ] **Step 3: Create the initial parser module**

Create `mcp_server/src/rook/scene/relationship_fact_projection.py` with these definitions:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PROJECTION_KIND = "relationship_fact_v1"
DEFAULT_SOURCE_MODE = "authored_graph_user_strings"
DEFAULT_CONFIDENCE = 1.0
DEFAULT_STATUS = "accepted"
ENGINE_VERSION = 1


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
```

- [ ] **Step 4: Run the parsing tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection.py -q
```

Expected: PASS for the four tests in the file.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add mcp_server/src/rook/scene/relationship_fact_projection.py mcp_server/tests/test_relationship_fact_projection.py
git commit -m "feat: add relationship fact parsing model"
```

## Task 2: Owner Projection, Edge Keys, Idempotency, and Scoped Pruning

**Files:**
- Modify: `mcp_server/src/rook/scene/relationship_fact_projection.py`
- Modify: `mcp_server/tests/test_relationship_fact_projection.py`

- [ ] **Step 1: Add failing projection tests**

Append these tests to `mcp_server/tests/test_relationship_fact_projection.py`:

```python
from rook.scene.scene_graph import SceneGraphAnalytics


def _analytics_for_relationship_projection() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node("member-rhino-id", name="Spine member", domain_label="member", shape_class="curve")
    sg.graph.add_node("joint-rhino-id", name="Spine base", domain_label="joint", shape_class="point")
    sg.graph.add_node("unrelated-rhino-id", name="Unrelated", domain_label="marker", shape_class="point")
    sg._sequence = 42
    return sg


def test_resolve_relationship_facts_projects_owner_to_owner():
    parsed = rel.parse_runtime_records(_valid_records())
    facts = rel.resolve_relationship_facts(parsed)

    assert len(facts) == 1
    fact = facts[0]
    assert fact.from_owner == "spine_base_to_spine_top"
    assert fact.from_owner_kind == "member"
    assert fact.from_owner_object_id == "member-rhino-id"
    assert fact.from_feature == "spine_base_to_spine_top.start"
    assert fact.from_feature_object_id == "feature-member-start-id"
    assert fact.to_owner == "spine_base"
    assert fact.to_owner_kind == "node"
    assert fact.to_owner_object_id == "joint-rhino-id"
    assert fact.to_feature == "spine_base.point"
    assert fact.to_feature_object_id == "feature-joint-point-id"


def test_project_relationship_facts_adds_connects_edge_with_metadata():
    sg = _analytics_for_relationship_projection()
    parsed = rel.parse_runtime_records(_valid_records())
    facts = rel.resolve_relationship_facts(parsed)

    result = rel.project_relationship_facts(sg, facts, prune_scope=rel.ReplacementScope())

    assert result["success"] is True
    assert result["counts"]["projectedEdgeCount"] == 1
    assert sg.graph.has_edge("member-rhino-id", "joint-rhino-id")
    edge_data = list(sg.graph["member-rhino-id"]["joint-rhino-id"].values())[0]
    assert edge_data["relationship"] == "connects"
    assert edge_data["projectionKind"] == rel.PROJECTION_KIND
    assert edge_data["semanticRelationshipType"] == "connects"
    assert edge_data["provenance"] == "authored_assembly_graph"
    assert edge_data["confidence"] == 1.0
    assert edge_data["status"] == "accepted"
    assert edge_data["sourceMode"] == "authored_graph_user_strings"
    assert edge_data["contactKind"] == "point_to_point"
    assert edge_data["fromFeature"] == "spine_base_to_spine_top.start"
    assert edge_data["toFeature"] == "spine_base.point"
    assert edge_data["fromFeatureObjectId"] == "feature-member-start-id"
    assert edge_data["toFeatureObjectId"] == "feature-joint-point-id"
    assert edge_data["relationshipObjectId"] == "relationship-marker-id"
    assert edge_data["engineVersion"] == 1


def test_projection_is_idempotent_for_same_fact_key():
    sg = _analytics_for_relationship_projection()
    facts = rel.resolve_relationship_facts(rel.parse_runtime_records(_valid_records()))

    first = rel.project_relationship_facts(sg, facts, prune_scope=rel.ReplacementScope())
    second = rel.project_relationship_facts(sg, facts, prune_scope=rel.ReplacementScope())

    assert first["counts"]["projectedEdgeCount"] == 1
    assert second["counts"]["projectedEdgeCount"] == 1
    assert sg.graph.number_of_edges("member-rhino-id", "joint-rhino-id") == 1


def test_pose_separation_creates_distinct_edge_keys():
    sg = _analytics_for_relationship_projection()
    records = [
        *_valid_records(),
        _owner_record("member-rhino-id", pose="rest_t_pose"),
        _joint_record("joint-rhino-id", pose="rest_t_pose"),
        _feature_record(
            "feature-member-start-id-rest",
            "spine_base_to_spine_top.start",
            "spine_base_to_spine_top",
            "member",
            pose="rest_t_pose",
        ),
        _feature_record("feature-joint-point-id-rest", "spine_base.point", "spine_base", "node", pose="rest_t_pose"),
        _relationship_record("relationship-marker-id-rest", pose="rest_t_pose"),
    ]
    facts = rel.resolve_relationship_facts(rel.parse_runtime_records(records))

    result = rel.project_relationship_facts(sg, facts, prune_scope=rel.ReplacementScope())

    assert result["counts"]["projectedEdgeCount"] == 2
    assert sg.graph.number_of_edges("member-rhino-id", "joint-rhino-id") == 2
    poses = {data["pose"] for data in sg.graph["member-rhino-id"]["joint-rhino-id"].values()}
    assert poses == {"reclined_robot", "rest_t_pose"}


def test_prune_relationship_fact_projection_preserves_other_projection_kinds():
    sg = _analytics_for_relationship_projection()
    sg.graph.add_edge(
        "member-rhino-id",
        "joint-rhino-id",
        key="relationship_fact:authored_graph_user_strings:pearson_robot_skeleton_graph:g001:reclined_robot:old",
        relationship="connects",
        projectionKind=rel.PROJECTION_KIND,
        sourceMode=rel.DEFAULT_SOURCE_MODE,
        graphSource="pearson_robot_skeleton_graph",
        graphRevision="g001",
        pose="reclined_robot",
        engineVersion=rel.ENGINE_VERSION,
    )
    sg.graph.add_edge(
        "member-rhino-id",
        "unrelated-rhino-id",
        key="bim-edge",
        relationship="revit_hosted_by",
        projectionKind="bim_relationship_v1",
    )

    result = rel.prune_relationship_fact_projection(
        sg,
        rel.ReplacementScope(
            graph_source="pearson_robot_skeleton_graph",
            graph_revision="g001",
            poses=["reclined_robot"],
        ),
    )

    assert result["removedEdges"] == 1
    assert not sg.graph.has_edge("member-rhino-id", "joint-rhino-id")
    assert sg.graph.has_edge("member-rhino-id", "unrelated-rhino-id", "bim-edge")


def test_scoped_prune_preserves_out_of_scope_pose():
    sg = _analytics_for_relationship_projection()
    for pose in ("reclined_robot", "rest_t_pose"):
        sg.graph.add_edge(
            "member-rhino-id",
            "joint-rhino-id",
            key=f"relationship_fact:authored_graph_user_strings:pearson_robot_skeleton_graph:g002:{pose}:old",
            relationship="connects",
            projectionKind=rel.PROJECTION_KIND,
            sourceMode=rel.DEFAULT_SOURCE_MODE,
            graphSource="pearson_robot_skeleton_graph",
            graphRevision="g002",
            pose=pose,
            engineVersion=rel.ENGINE_VERSION,
        )

    result = rel.prune_relationship_fact_projection(
        sg,
        rel.ReplacementScope(
            graph_source="pearson_robot_skeleton_graph",
            graph_revision="g002",
            poses=["reclined_robot"],
        ),
    )

    assert result["removedEdges"] == 1
    assert not any(data["pose"] == "reclined_robot" for _, _, data in sg.graph.edges(data=True))
    assert any(data["pose"] == "rest_t_pose" for _, _, data in sg.graph.edges(data=True))


def test_scoped_prune_preserves_edges_outside_primary_object_scope():
    sg = _analytics_for_relationship_projection()
    sg.graph.add_node("other-member-id", name="Other member")
    sg.graph.add_node("other-joint-id", name="Other joint")
    for source_id, target_id in (("member-rhino-id", "joint-rhino-id"), ("other-member-id", "other-joint-id")):
        sg.graph.add_edge(
            source_id,
            target_id,
            key=f"relationship_fact:authored_graph_user_strings:pearson_robot_skeleton_graph:g002:reclined_robot:{source_id}",
            relationship="connects",
            projectionKind=rel.PROJECTION_KIND,
            sourceMode=rel.DEFAULT_SOURCE_MODE,
            graphSource="pearson_robot_skeleton_graph",
            graphRevision="g002",
            pose="reclined_robot",
            engineVersion=rel.ENGINE_VERSION,
        )

    result = rel.prune_relationship_fact_projection(
        sg,
        rel.ReplacementScope(
            graph_source="pearson_robot_skeleton_graph",
            graph_revision="g002",
            poses=["reclined_robot"],
            primary_object_ids=["member-rhino-id"],
        ),
    )

    assert result["removedEdges"] == 1
    assert not sg.graph.has_edge("member-rhino-id", "joint-rhino-id")
    assert sg.graph.has_edge("other-member-id", "other-joint-id")
```

- [ ] **Step 2: Run the projection tests and verify they fail on missing functions**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection.py -q
```

Expected: FAIL on missing `resolve_relationship_facts`, `project_relationship_facts`, `ReplacementScope`, or `prune_relationship_fact_projection`.

- [ ] **Step 3: Add fact resolution and projection implementation**

Extend `mcp_server/src/rook/scene/relationship_fact_projection.py` with these definitions:

```python
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


def resolve_relationship_facts(parsed: ParsedRuntimeRecords) -> list[RelationshipFact]:
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
    return facts


def _is_relationship_fact_edge(attrs: dict[str, Any]) -> bool:
    return attrs.get("projectionKind") == PROJECTION_KIND


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
            "relationshipFactCount": len(facts),
            "projectedEdgeCount": projected,
            "skippedFactCount": skipped,
        },
        "byRelationshipType": by_relationship_type,
        "byPose": by_pose,
        "diagnostics": {},
        "samples": {},
        "prune": prune_result,
    }
```

- [ ] **Step 4: Run the projection tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add mcp_server/src/rook/scene/relationship_fact_projection.py mcp_server/tests/test_relationship_fact_projection.py
git commit -m "feat: project relationship facts into scene graph"
```

## Task 3: Diagnostics, Strict Mode, and Response Counts

**Files:**
- Modify: `mcp_server/src/rook/scene/relationship_fact_projection.py`
- Modify: `mcp_server/tests/test_relationship_fact_projection.py`

- [ ] **Step 1: Add failing diagnostics and strict-mode tests**

Append these tests to `mcp_server/tests/test_relationship_fact_projection.py`:

```python
def test_lenient_missing_feature_endpoint_reports_diagnostic_without_crashing():
    records = [
        _owner_record("member-rhino-id"),
        _joint_record("joint-rhino-id"),
        _relationship_record("relationship-marker-id"),
    ]

    result = rel.build_relationship_fact_set(rel.parse_runtime_records(records), strict=False)

    assert result.success is True
    assert result.facts == []
    assert result.diagnostics["relationshipFactsMissingFeatureEndpoint"] == 1


def test_strict_missing_feature_endpoint_fails():
    records = [
        _owner_record("member-rhino-id"),
        _joint_record("joint-rhino-id"),
        _relationship_record("relationship-marker-id"),
    ]

    with pytest.raises(rel.RelationshipFactProjectionError) as exc:
        rel.build_relationship_fact_set(rel.parse_runtime_records(records), strict=True)

    assert "relationshipFactsMissingFeatureEndpoint" in str(exc.value)


def test_strict_mode_ignores_informational_filter_diagnostics():
    records = [
        *_valid_records(),
        _owner_record("member-rhino-id-rest", pose="rest_t_pose"),
        _joint_record("joint-rhino-id-rest", pose="rest_t_pose"),
    ]
    parsed = rel.parse_runtime_records(records, poses=["reclined_robot"])

    result = rel.build_relationship_fact_set(parsed, strict=True)

    assert result.success is True
    assert len(result.facts) == 1
    assert parsed.diagnostics["filteredByPose"] == 2


def test_missing_owner_object_reports_diagnostic():
    records = [
        _feature_record(
            "feature-member-start-id",
            "spine_base_to_spine_top.start",
            "spine_base_to_spine_top",
            "member",
        ),
        _feature_record("feature-joint-point-id", "spine_base.point", "spine_base", "node"),
        _relationship_record("relationship-marker-id"),
    ]

    result = rel.build_relationship_fact_set(rel.parse_runtime_records(records), strict=False)

    assert result.success is True
    assert result.facts == []
    assert result.diagnostics["relationshipFactsMissingOwnerObject"] == 1


def test_duplicate_records_report_bounded_diagnostics():
    records = [
        *_valid_records(),
        _feature_record(
            "feature-member-start-id-duplicate",
            "spine_base_to_spine_top.start",
            "spine_base_to_spine_top",
            "member",
        ),
    ]

    parsed = rel.parse_runtime_records(records)

    assert parsed.diagnostics["duplicateFeatureRecords"] == 1
```

- [ ] **Step 2: Run tests and verify missing `build_relationship_fact_set` failure**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection.py -q
```

Expected: FAIL on missing `build_relationship_fact_set`.

- [ ] **Step 3: Add `RelationshipFactSet` and strict validation**

Modify `relationship_fact_projection.py` so diagnostics from resolution are preserved:

```python
@dataclass(frozen=True)
class RelationshipFactSet:
    success: bool
    facts: list[RelationshipFact]
    diagnostics: dict[str, int]


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
```

Then update `project_relationship_facts` to accept a `diagnostics` argument and include `ownerObjectCount`, `featureObjectCount`, `relationshipObjectCount`, `relationshipFactCount`, and `skippedFactCount` in the response. Keep the existing `facts` argument so Task 2 tests remain valid:

```python
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
```

- [ ] **Step 4: Run pure tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add mcp_server/src/rook/scene/relationship_fact_projection.py mcp_server/tests/test_relationship_fact_projection.py
git commit -m "feat: add relationship fact diagnostics"
```

## Task 4: Tool Hydration Orchestration

**Files:**
- Modify: `mcp_server/src/rook/scene/relationship_fact_projection.py`
- Create: `mcp_server/tests/test_relationship_fact_projection_tool.py`

- [ ] **Step 1: Add failing async tool orchestration tests**

Create `mcp_server/tests/test_relationship_fact_projection_tool.py` with this content:

```python
import pytest

from rook.scene import relationship_fact_projection as rel
from rook.scene.scene_graph import SceneGraphAnalytics


def _scene_graph() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    for object_id in [
        "member-rhino-id",
        "joint-rhino-id",
        "feature-member-start-id",
        "feature-joint-point-id",
        "relationship-marker-id",
    ]:
        sg.graph.add_node(object_id, name=object_id, domain_label="debug", shape_class="point")
    sg._sequence = 77
    return sg


def _add_unrelated_fact_nodes(sg: SceneGraphAnalytics) -> None:
    for object_id in [
        "unrelated-member-id",
        "unrelated-joint-id",
        "unrelated-feature-member-id",
        "unrelated-feature-joint-id",
        "unrelated-relationship-id",
    ]:
        sg.graph.add_node(object_id, name=object_id, domain_label="debug", shape_class="point")


def _user_strings_for(object_id: str) -> dict:
    records = {
        "member-rhino-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "member",
            "rook.graph.member_id": "spine_base_to_spine_top",
        },
        "joint-rhino-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "joint",
            "rook.graph.node_id": "spine_base",
        },
        "feature-member-start-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "feature",
            "rook.graph.feature_id": "spine_base_to_spine_top.start",
            "rook.graph.owner": "spine_base_to_spine_top",
            "rook.graph.owner_kind": "member",
        },
        "feature-joint-point-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "feature",
            "rook.graph.feature_id": "spine_base.point",
            "rook.graph.owner": "spine_base",
            "rook.graph.owner_kind": "node",
        },
        "relationship-marker-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "relationship",
            "rook.graph.relationship_id": "spine_base_to_spine_top.start_connects_spine_base",
            "rook.graph.relationship_type": "connects",
            "rook.graph.from_feature": "spine_base_to_spine_top.start",
            "rook.graph.to_feature": "spine_base.point",
            "rook.graph.contact_kind": "point_to_point",
            "rook.graph.provenance": "authored_assembly_graph",
        },
        "unrelated-member-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "member",
            "rook.graph.member_id": "unrelated_member",
        },
        "unrelated-joint-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "joint",
            "rook.graph.node_id": "unrelated_joint",
        },
        "unrelated-feature-member-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "feature",
            "rook.graph.feature_id": "unrelated_member.start",
            "rook.graph.owner": "unrelated_member",
            "rook.graph.owner_kind": "member",
        },
        "unrelated-feature-joint-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "feature",
            "rook.graph.feature_id": "unrelated_joint.point",
            "rook.graph.owner": "unrelated_joint",
            "rook.graph.owner_kind": "node",
        },
        "unrelated-relationship-id": {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": "reclined_robot",
            "rook.graph.visual_type": "relationship",
            "rook.graph.relationship_id": "unrelated_member.start_connects_unrelated_joint",
            "rook.graph.relationship_type": "connects",
            "rook.graph.from_feature": "unrelated_member.start",
            "rook.graph.to_feature": "unrelated_joint.point",
            "rook.graph.contact_kind": "point_to_point",
            "rook.graph.provenance": "authored_assembly_graph",
        },
    }
    return records[object_id]


@pytest.mark.asyncio
async def test_project_relationship_facts_for_tool_hydrates_scene_and_projects(monkeypatch):
    sg = _scene_graph()
    sg.graph.add_node(
        "rookbim:room:synthetic",
        name="Synthetic BIM room",
        projectionKind="bim_relationship_v1",
        nodeKind="rookbim_room",
    )
    calls = []

    async def fake_sync(port=None):
        calls.append(("sync", port))
        return {"success": True, "sequence": sg.sequence}

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        calls.append((path, payload["id"], port))
        return {"success": True, "data": {"id": payload["id"], "userStrings": _user_strings_for(payload["id"])}}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr(rel, "call_rhino", fake_call_rhino)

    result = await rel.project_relationship_facts_for_tool(
        graph_source="pearson_robot_skeleton_graph",
        port=9876,
        analytics=sg,
    )

    assert result["success"] is True
    assert result["counts"]["candidateObjectCount"] == 5
    assert result["counts"]["hydratedObjectCount"] == 5
    assert result["counts"]["ownerObjectCount"] == 2
    assert result["counts"]["featureObjectCount"] == 2
    assert result["counts"]["relationshipObjectCount"] == 1
    assert result["counts"]["relationshipFactCount"] == 1
    assert result["counts"]["projectedEdgeCount"] == 1
    assert result["byRelationshipType"] == {"connects": 1}
    assert result["byPose"] == {"reclined_robot": 1}
    assert sg.graph.has_edge("member-rhino-id", "joint-rhino-id")
    assert all(call[0] in {"sync", "/usertext/object-get"} for call in calls)
    hydrated_ids = {call[1] for call in calls if call[0] == "/usertext/object-get"}
    assert "rookbim:room:synthetic" not in hydrated_ids


@pytest.mark.asyncio
async def test_scoped_object_ids_hydrate_full_scene_but_filter_projected_facts(monkeypatch):
    sg = _scene_graph()
    _add_unrelated_fact_nodes(sg)
    hydrated_ids = []

    async def fake_sync(port=None):
        return {"success": True, "sequence": sg.sequence}

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        hydrated_ids.append(payload["id"])
        return {"success": True, "data": {"id": payload["id"], "userStrings": _user_strings_for(payload["id"])}}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr(rel, "call_rhino", fake_call_rhino)

    result = await rel.project_relationship_facts_for_tool(
        graph_source="pearson_robot_skeleton_graph",
        object_ids=["member-rhino-id"],
        analytics=sg,
    )

    assert result["success"] is True
    assert set(hydrated_ids) == {
        "member-rhino-id",
        "joint-rhino-id",
        "feature-member-start-id",
        "feature-joint-point-id",
        "relationship-marker-id",
        "unrelated-member-id",
        "unrelated-joint-id",
        "unrelated-feature-member-id",
        "unrelated-feature-joint-id",
        "unrelated-relationship-id",
    }
    assert result["counts"]["relationshipFactCount"] == 2
    assert result["counts"]["projectedEdgeCount"] == 1
    assert sg.graph.has_edge("member-rhino-id", "joint-rhino-id")
    assert not sg.graph.has_edge("unrelated-member-id", "unrelated-joint-id")


@pytest.mark.asyncio
async def test_strict_tool_failure_on_malformed_fact(monkeypatch):
    sg = _scene_graph()

    async def fake_sync(port=None):
        return {"success": True, "sequence": sg.sequence}

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        user_strings = dict(_user_strings_for(payload["id"]))
        if payload["id"] == "relationship-marker-id":
            user_strings.pop("rook.graph.to_feature", None)
        return {"success": True, "data": {"id": payload["id"], "userStrings": user_strings}}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr(rel, "call_rhino", fake_call_rhino)

    result = await rel.project_relationship_facts_for_tool(
        graph_source="pearson_robot_skeleton_graph",
        strict=True,
        analytics=sg,
    )

    assert result["success"] is False
    assert result["error"] == "relationship_fact_projection_validation_failed"
    assert "relationshipObjectsMissingFeatureEndpoint" in result["message"]
```

- [ ] **Step 2: Run tool tests and verify missing orchestration failure**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection_tool.py -q
```

Expected: FAIL on missing `project_relationship_facts_for_tool` or missing `call_rhino`.

- [ ] **Step 3: Add hydration orchestration**

At the top of `relationship_fact_projection.py`, add the bridge import:

```python
from ..bridge import call_rhino
```

Add these functions:

```python
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
            response = await call_rhino("/usertext/object-get", "POST", {"id": object_id}, port=port)
        except Exception:
            _bump(diagnostics, "hydrationFailures")
            continue
        user_strings = _extract_user_strings(response)
        if user_strings is None:
            _bump(diagnostics, "hydrationFailures")
            continue
        records.append(RuntimeObjectRecord(object_id=object_id, user_strings=user_strings))
    return records, diagnostics


def _count_visual_type(records: list[RuntimeObjectRecord], visual_type: str) -> int:
    return sum(1 for record in records if _clean_str(record.user_strings.get("rook.graph.visual_type")) == visual_type)


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
    hydration_object_ids = list(dict.fromkeys(candidate_object_ids))
    records, hydration_diagnostics = await hydrate_runtime_object_records(hydration_object_ids, port=port)

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
```

- [ ] **Step 4: Run pure and tool tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection.py mcp_server/tests/test_relationship_fact_projection_tool.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

Run:

```powershell
git add mcp_server/src/rook/scene/relationship_fact_projection.py mcp_server/tests/test_relationship_fact_projection_tool.py
git commit -m "feat: hydrate relationship facts from Rhino user text"
```

## Task 5: Scene Context Formatting

**Files:**
- Modify: `mcp_server/src/rook/scene/scene_graph.py`
- Modify: `mcp_server/tests/test_relationship_fact_projection_tool.py`

- [ ] **Step 1: Add failing context formatting test**

Append this test to `mcp_server/tests/test_relationship_fact_projection_tool.py`:

```python
@pytest.mark.asyncio
async def test_scene_context_sync_false_renders_relationship_fact_details(monkeypatch):
    sg = _scene_graph()
    sg.graph.add_edge(
        "member-rhino-id",
        "joint-rhino-id",
        key="relationship_fact:authored_graph_user_strings:pearson_robot_skeleton_graph:g002:reclined_robot:spine",
        relationship="connects",
        projectionKind=rel.PROJECTION_KIND,
        semanticRelationshipType="connects",
        provenance="authored_assembly_graph",
        confidence=1.0,
        status="accepted",
        sourceMode=rel.DEFAULT_SOURCE_MODE,
        contactKind="point_to_point",
        graphSource="pearson_robot_skeleton_graph",
        graphRevision="g002",
        pose="reclined_robot",
        relationshipFactId="spine_base_to_spine_top.start_connects_spine_base",
        fromFeature="spine_base_to_spine_top.start",
        toFeature="spine_base.point",
        engineVersion=rel.ENGINE_VERSION,
    )
    called = {"sync": 0}

    async def fake_sync(port=None):
        called["sync"] += 1
        return {"success": True}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch(
        "scene_context",
        {"object_ids": ["member-rhino-id", "joint-rhino-id"], "sync": False},
    )

    assert result["success"] is True
    assert called["sync"] == 0
    assert "connects: JOINT" in result["data"]
    assert "connected by: DEBUG" in result["data"]
    assert "via spine_base_to_spine_top.start -> spine_base.point" in result["data"]
    assert "point_to_point" in result["data"]
    assert "accepted" in result["data"]
    assert "authored_assembly_graph" in result["data"]
```

- [ ] **Step 2: Run the context test and verify formatting failure**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection_tool.py::test_scene_context_sync_false_renders_relationship_fact_details -q
```

Expected: FAIL because `_edge_detail` does not yet include relationship fact details, and inverse `connects` text is not `connected by`.

- [ ] **Step 3: Update context labels and edge detail**

In `mcp_server/src/rook/scene/scene_graph.py`, add only the `connects` inverse label to the existing `_INVERSE_RELS` dictionary. Do not replace the whole dictionary, because existing entries such as `adjacent_exact` are already used by tests and live context formatting:

```python
    "connects": "connected by",
```

Then modify `_edge_detail` so projected relationship facts render semantic detail before the generic distance branch:

```python
    if edata.get("projectionKind") == "relationship_fact_v1":
        feature_part = ""
        from_feature = edata.get("fromFeature")
        to_feature = edata.get("toFeature")
        if from_feature and to_feature:
            feature_part = f" via {from_feature} -> {to_feature}"
        detail_parts = [
            str(part)
            for part in (
                edata.get("contactKind"),
                edata.get("status"),
                edata.get("provenance"),
            )
            if part
        ]
        suffix = f", {', '.join(detail_parts)}" if detail_parts else ""
        return f"{feature_part}{suffix}"
```

- [ ] **Step 4: Run context and BIM context regression tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection_tool.py::test_scene_context_sync_false_renders_relationship_fact_details mcp_server/tests/test_bim_relationship_projection_tool.py::test_scene_context_sync_false_skips_sync_and_reads_current_mirror -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

Run:

```powershell
git add mcp_server/src/rook/scene/scene_graph.py mcp_server/tests/test_relationship_fact_projection_tool.py
git commit -m "feat: render relationship facts in scene context"
```

## Task 6: MCP Schema, Server Dispatch, Local Dispatcher, Tool Groups, and Targeting

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Modify: `mcp_server/tests/test_relationship_fact_projection_tool.py`

- [ ] **Step 1: Add failing registration tests**

Append these tests to `mcp_server/tests/test_relationship_fact_projection_tool.py`:

```python
@pytest.mark.asyncio
async def test_server_tool_schema_exposes_scene_project_relationship_facts_parameters():
    from rook.server import list_tools

    tools = {tool.name: tool for tool in await list_tools()}
    schema = tools["scene_project_relationship_facts"].inputSchema

    assert schema["properties"]["graph_source"]["type"] == "string"
    assert schema["properties"]["graph_revision"]["type"] == "string"
    assert schema["properties"]["poses"]["items"]["type"] == "string"
    assert schema["properties"]["object_ids"]["items"]["type"] == "string"
    assert schema["properties"]["source_mode"]["enum"] == ["authored_graph_user_strings"]
    assert schema["properties"]["strict"]["type"] == "boolean"
    assert schema["properties"]["port"]["type"] == "integer"


def test_tool_group_contains_scene_project_relationship_facts():
    from rook.agent.tool_groups import TOOL_GROUPS

    assert "scene_project_relationship_facts" in TOOL_GROUPS["scene_graph"]


def test_scene_project_relationship_facts_targeting_policy_is_rhino_read():
    from rook import targeting

    pol = targeting.policy_for_tool("scene_project_relationship_facts")

    assert pol.requires_rhino is True
    assert pol.risk == "read"
    assert "scene_project_relationship_facts" in targeting._ALL_KNOWN_TOOLS


def test_local_dispatcher_registers_scene_project_relationship_facts():
    from rook.agent.tool_dispatcher import build_local_tools

    tools = build_local_tools()

    assert "scene_project_relationship_facts" in tools
    assert callable(tools["scene_project_relationship_facts"])


@pytest.mark.asyncio
async def test_server_dispatch_projects_relationship_facts(monkeypatch):
    sg = _scene_graph()

    async def fake_sync(port=None):
        return {"success": True, "sequence": sg.sequence}

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        return {"success": True, "data": {"id": payload["id"], "userStrings": _user_strings_for(payload["id"])}}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)
    monkeypatch.setattr(rel, "call_rhino", fake_call_rhino)

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch(
        "scene_project_relationship_facts",
        {"graph_source": "pearson_robot_skeleton_graph"},
    )

    assert result["success"] is True
    payload = result["data"]
    assert payload["success"] is True
    assert payload["projectionKind"] == rel.PROJECTION_KIND
    assert payload["counts"]["projectedEdgeCount"] == 1
```

- [ ] **Step 2: Run registration tests and verify missing tool failures**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection_tool.py -q
```

Expected: FAIL because `scene_project_relationship_facts` is not registered.

- [ ] **Step 3: Add MCP tool schema in `server.py`**

In `mcp_server/src/rook/server.py`, locate the `scene_project_bim_relationships` `Tool(...)` block and add this sibling `Tool(...)` in the Scene Graph / Spatial Intelligence section:

```python
        Tool(
            name="scene_project_relationship_facts",
            description="""Project authored relationship facts from Rhino object user strings into the in-memory scene graph read model.

Creates semantic owner-object-to-owner-object edges such as member -> joint with relationship="connects". Use scene_context(sync=false) after this tool to inspect Python-only projected facts. This tool reads Rhino object user text and mutates only the Python scene graph mirror; it does not mutate Rhino geometry, object attributes, layers, blocks, or document user text.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "graph_source": {
                        "type": "string",
                        "description": "Optional graph source filter, for example pearson_robot_skeleton_graph",
                    },
                    "graph_revision": {
                        "type": "string",
                        "description": "Optional graph revision filter, for example g002",
                    },
                    "poses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional pose filter. Scoped projection preserves out-of-scope poses.",
                    },
                    "object_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional primary owner object scope. Resolution still hydrates the full current scene.",
                    },
                    "source_mode": {
                        "type": "string",
                        "enum": ["authored_graph_user_strings"],
                        "description": "Relationship fact source mode. v1 supports authored_graph_user_strings only.",
                    },
                    "strict": {
                        "type": "boolean",
                        "description": "If true, malformed facts fail the tool instead of returning diagnostics.",
                    },
                    "port": {"type": "integer", "description": "Rhino instance port"},
                },
                "required": [],
            },
        ),
```

- [ ] **Step 4: Add `_call_tool_dispatch` dispatch in `server.py`**

In the scene graph dispatch section, add this case next to `scene_project_bim_relationships`:

```python
        case "scene_project_relationship_facts":
            from .scene.relationship_fact_projection import project_relationship_facts_for_tool

            payload = await project_relationship_facts_for_tool(
                graph_source=arguments.get("graph_source"),
                graph_revision=arguments.get("graph_revision"),
                poses=arguments.get("poses"),
                object_ids=arguments.get("object_ids"),
                source_mode=arguments.get("source_mode", "authored_graph_user_strings"),
                strict=arguments.get("strict", False),
                port=port,
            )
            if payload.get("success") is False:
                result = {"success": False, "data": payload}
            else:
                result = {"success": True, "data": payload}
```

- [ ] **Step 5: Add local dispatcher handler**

In `mcp_server/src/rook/agent/tool_dispatcher.py`, add a local handler next to the BIM projection handler:

```python
    # --- scene_project_relationship_facts (Python-side relationship fact projection) ---
    try:
        from ..scene.relationship_fact_projection import project_relationship_facts_for_tool

        async def _scene_project_relationship_facts(
            graph_source=None,
            graph_revision=None,
            poses=None,
            object_ids=None,
            source_mode="authored_graph_user_strings",
            strict=False,
            port: int | None = None,
            **kwargs,
        ) -> dict:
            return await project_relationship_facts_for_tool(
                graph_source=graph_source,
                graph_revision=graph_revision,
                poses=poses,
                object_ids=object_ids,
                source_mode=source_mode,
                strict=strict,
                port=port,
            )

        tools["scene_project_relationship_facts"] = _scene_project_relationship_facts
    except ImportError:
        logger.debug("scene_project_relationship_facts local tool unavailable (import failed)")
```

- [ ] **Step 6: Add tool group and targeting entries**

In `mcp_server/src/rook/agent/tool_groups.py`, add the tool to `TOOL_GROUPS["scene_graph"]`:

```python
        "scene_project_bim_relationships", "scene_bim_facts",
        "scene_project_relationship_facts",
```

In `mcp_server/src/rook/targeting.py`, add `scene_project_relationship_facts` to `_ALL_KNOWN_TOOLS` near the other scene tools:

```python
    "scene_project_relationship_facts",
```

Also add it to `_RHINO_READ_TOOLS`:

```python
    "scene_project_relationship_facts",
```

- [ ] **Step 7: Run registration and dispatch tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection_tool.py -q
```

Expected: PASS.

- [ ] **Step 8: Run BIM projection tool regression tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bim_relationship_projection_tool.py -q
```

Expected: PASS. This protects the existing BIM projection registration and `scene_context(sync=false)` behavior.

- [ ] **Step 9: Commit Task 6**

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/targeting.py mcp_server/tests/test_relationship_fact_projection_tool.py
git commit -m "feat: expose relationship fact projection tool"
```

## Task 7: Full Verification and Manual Rhino Gate

**Files:**
- Modify only if verification finds a bug in files already touched by Tasks 1-6.

- [ ] **Step 1: Run focused unit suite**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_relationship_fact_projection.py `
  mcp_server/tests/test_relationship_fact_projection_tool.py `
  mcp_server/tests/test_bim_relationship_projection.py `
  mcp_server/tests/test_bim_relationship_projection_tool.py `
  -q
```

Expected: PASS.

- [ ] **Step 2: Run whitespace and committed-diff verification**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected:

```text
## codex/pearson-robot-feature-graph...origin/codex/pearson-robot-feature-graph [ahead N]
```

No unstaged changes after the final commit in this task.

- [ ] **Step 3: Run live smoke only when Rhino has the Pearson `g002` document open**

In MCP/Rook tool terms, run:

```text
scene_project_relationship_facts(graph_source="pearson_robot_skeleton_graph")
```

Expected payload shape:

```json
{
  "success": true,
  "projectionKind": "relationship_fact_v1",
  "sourceMode": "authored_graph_user_strings",
  "counts": {
    "relationshipFactCount": 56,
    "projectedEdgeCount": 56,
    "skippedFactCount": 0
  },
  "byRelationshipType": {
    "connects": 56
  },
  "byPose": {
    "rest_t_pose": 28,
    "reclined_robot": 28
  }
}
```

If only one pose is present in the active Rhino document, expected `relationshipFactCount` and `projectedEdgeCount` are `28`, and `byPose` contains only that pose.

- [ ] **Step 4: Inspect context without syncing**

Run:

```text
scene_context(object_ids=["<sample-member-object-id>", "<sample-joint-object-id>"], sync=false)
```

Expected context includes lines shaped like:

```text
connects: JOINT "joint_reclined_robot_spine_base" via spine_base_to_spine_top.start -> spine_base.point, point_to_point, accepted, authored_assembly_graph
connected by: MEMBER "member_reclined_robot_spine_base_to_spine_top" via spine_base_to_spine_top.start -> spine_base.point, point_to_point, accepted, authored_assembly_graph
```

Do not use `scene_stats` as an acceptance check for this slice.

- [ ] **Step 5: Re-run projection to verify idempotency**

Run:

```text
scene_project_relationship_facts(graph_source="pearson_robot_skeleton_graph")
```

Expected:

- `success` is `true`;
- `counts.projectedEdgeCount` remains the same as the first run;
- context does not show duplicate `connects` facts for the same relationship id, revision, and pose.

- [ ] **Step 6: Commit any verification fixes**

If Task 7 found and fixed a bug, commit with:

```powershell
git add <changed-files>
git commit -m "fix: stabilize relationship fact projection"
```

If Task 7 did not require file changes, do not create an empty commit.

## Task 8: Final Branch Hygiene and Handoff

**Files:**
- No source edits expected.

- [ ] **Step 1: Run final status checks in both worktrees**

Run:

```powershell
git status --short --branch
git log --oneline -5
```

From the main checkout:

```powershell
cd C:/Users/aryan/source/repos/Rook
git status --short --branch
```

Expected:

```text
## main...origin/main
```

- [ ] **Step 2: Push the Pearson branch**

Run from the Pearson worktree:

```powershell
cd C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph
git push
```

Expected: branch `codex/pearson-robot-feature-graph` pushed successfully.

- [ ] **Step 3: Prepare reviewer backfill**

Provide this reviewer context:

```text
This branch implements Relationship Fact Projection v1 from the reviewed spec.

Core behavior:
- Hydrates Rhino object user strings through /usertext/object-get.
- Parses rook.graph.* owner, feature, and relationship records.
- Projects relationship facts as owner object -> owner object edges.
- Keeps marker object ids as edge metadata only.
- Uses relationship="connects", projectionKind="relationship_fact_v1", semanticRelationshipType="connects".
- Defaults missing confidence/status/sourceMode to 1.0/accepted/authored_graph_user_strings.
- Prunes only relationship_fact_v1 edges inside the explicit replacement scope.
- Exposes visibility through projection response counts and scene_context(sync=false), not scene_stats.

Main review targets:
- mcp_server/src/rook/scene/relationship_fact_projection.py
- mcp_server/src/rook/scene/scene_graph.py
- mcp_server/src/rook/server.py
- mcp_server/src/rook/agent/tool_dispatcher.py
- mcp_server/src/rook/agent/tool_groups.py
- mcp_server/src/rook/targeting.py
- mcp_server/tests/test_relationship_fact_projection.py
- mcp_server/tests/test_relationship_fact_projection_tool.py

Verification:
- python -m pytest mcp_server/tests/test_relationship_fact_projection.py mcp_server/tests/test_relationship_fact_projection_tool.py mcp_server/tests/test_bim_relationship_projection.py mcp_server/tests/test_bim_relationship_projection_tool.py -q
- git diff --check
- Optional live smoke in Rhino with Pearson g002 document:
  scene_project_relationship_facts(graph_source="pearson_robot_skeleton_graph")
  scene_context(sync=false)
```

## Self-Review Checklist

- Spec coverage:
  - Data model and defaults: Tasks 1 and 3.
  - Required `graphSource`, `graphRevision`, and `pose` validation for graph records: Task 1.
  - Owner-object endpoints with feature metadata: Task 2.
  - Idempotency and scoped pruning: Task 2.
  - Primary `object_ids` scope filtering after full-scene hydration: Task 4.
  - Candidate hydration excludes all Python-only projection nodes, not only `relationship_fact_v1`: Task 4.
  - Strict mode ignores informational filter diagnostics and fails only validation diagnostics: Task 3.
  - Read-only hydration: Task 4.
  - MCP schema, dispatcher, tool group, targeting: Task 6.
  - Context visibility through `scene_context(sync=false)`: Task 5.
  - Explicit exclusion of `scene_stats`: Task 7 live gate.
  - Tests for malformed facts, strict mode, owner projection, scoped hydration, and pruning: Tasks 2-4.
- Placeholder scan:
  - No unresolved implementation markers are left in the plan.
  - Every code-changing step includes concrete code or exact insertion text.
  - Every verification step includes an exact command and expected result.
- Type consistency:
  - Public module constants are `PROJECTION_KIND`, `DEFAULT_SOURCE_MODE`, `DEFAULT_CONFIDENCE`, `DEFAULT_STATUS`, `ENGINE_VERSION`.
  - Public tool function is `project_relationship_facts_for_tool`.
  - Public MCP tool is `scene_project_relationship_facts`.
  - Edge metadata uses `relationship`, `projectionKind`, `semanticRelationshipType`, `sourceMode`, `graphSource`, `graphRevision`, `pose`, `fromFeature`, and `toFeature` consistently.
