# Architectural Relationship Fixture v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small authored architectural relationship fixture that proves Rhino user text can round-trip through projection, semantic inspection, and object semantic context cards beyond the robot domain.

**Architecture:** Create a durable experiment fixture with `assembly_graph.json`, a repeatable Rhino fixture script, and README documentation. Add test-only architectural helpers that build expected facts/cards from the graph and validate the same authored facts through non-live synthetic projection and a skippable live Rhino projection path; no production MCP/tool/schema code changes.

**Tech Stack:** Python 3, pytest, Rhino Python executed through `rhino_execute`, existing `SceneGraphAnalytics`, `scene_project_relationship_facts`, `scene_semantic_relationships`, and `scene_object_semantic_context`.

---

## 1. Source Spec

Implement exactly this reviewed spec:

```text
docs/superpowers/specs/2026-06-28-architectural-relationship-fixture-v1-design.md
```

Branch/worktree:

```text
C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph
codex/architectural-relationship-fixture-v1
```

Immediate stack base:

```text
3f883967 feat: expose object semantic context tool
```

Current spec commit:

```text
8076fcec docs: clarify architectural fixture visual types
```

## 2. File Structure

Create:

```text
experiments/architectural_relationship_fixture/assembly_graph.json
experiments/architectural_relationship_fixture/generated/create_architectural_fixture_rhino.py
experiments/architectural_relationship_fixture/README.md
mcp_server/tests/architectural_fixture_helpers.py
mcp_server/tests/test_architectural_relationship_fixture.py
mcp_server/tests/test_architectural_relationship_fixture_live.py
```

Modify no production code.

Responsibilities:

- `assembly_graph.json`: durable authored semantic fixture graph, human architecture terms.
- `create_architectural_fixture_rhino.py`: repeatable Rhino fixture creator; clears one layer and stamps v1 projection-compatible user text.
- `README.md`: fixture purpose, counts, commands, and boundaries.
- `architectural_fixture_helpers.py`: test-only loading, expected fact generation, synthetic graph construction, card/group assertions, Rhino execute output parsing.
- `test_architectural_relationship_fixture.py`: non-live graph shape, expected facts, synthetic inspector/card assertions.
- `test_architectural_relationship_fixture_live.py`: skippable live Rhino loop.

Do not change:

```text
mcp_server/src/rook/scene/relationship_fact_projection.py
mcp_server/src/rook/scene/semantic_relationship_inspector.py
mcp_server/src/rook/scene/object_semantic_context.py
mcp_server/src/rook/server.py
```

## 3. Fixture Contract

Constants:

```python
GRAPH_SOURCE = "architectural_relationship_fixture"
GRAPH_REVISION = "a001"
POSE = "architectural_reference"
PROVENANCE = "authored_architectural_fixture"
STATUS = "accepted"
LAYER_NAME = "Rook_ArchitecturalRelationshipFixture"
```

Owners:

```text
column_01
slab_01
wall_01
door_01
opening_01
duct_01
space_01
```

Features:

```text
column_01.top_point
slab_01.underside_region
door_01.body
wall_01.host_region
opening_01.profile
wall_01.opening_region
duct_01.centerline
wall_01.penetration_region
space_01.boundary
wall_01.inner_face
```

Relationships:

```text
column_01.top_point supports slab_01.underside_region
door_01.body hosted_by wall_01.host_region
opening_01.profile voids wall_01.opening_region
duct_01.centerline penetrates wall_01.penetration_region
space_01.boundary bounded_by wall_01.inner_face
```

Live fixture summary counts:

```text
ownerObjectCount == 7
featureObjectCount == 10
relationshipObjectCount == 5
createdObjectCount == 22
```

Projection counts:

```text
relationshipFactCount == 5
projectedEdgeCount == 5
skippedFactCount == 0
```

User-text compatibility rule:

```text
Owner objects:      rook.graph.visual_type = member, rook.graph.member_id = architectural owner id
Feature objects:    rook.graph.visual_type = feature, rook.graph.owner_kind = member
Relationship marks: rook.graph.visual_type = relationship
```

The graph file may preserve human architectural `kind` values. The Rhino user text must use
`member` as the projection-v1 owner kind.

## 4. Task 1: Authored Graph And README

**Files:**
- Create: `experiments/architectural_relationship_fixture/assembly_graph.json`
- Create: `experiments/architectural_relationship_fixture/README.md`

- [ ] **Step 1: Create the experiment folder**

Run:

```powershell
New-Item -ItemType Directory -Force experiments/architectural_relationship_fixture/generated
```

- [ ] **Step 2: Create `assembly_graph.json`**

Create `experiments/architectural_relationship_fixture/assembly_graph.json` with this exact content:

```json
{
  "schema": "rook.architectural_relationship_fixture.v1",
  "source": "architectural_relationship_fixture",
  "revision": "a001",
  "unit": "meters",
  "poses": {
    "architectural_reference": {
      "description": "Single authored architectural semantic fixture pose"
    }
  },
  "objects": [
    {
      "id": "column_01",
      "kind": "column",
      "name": "Column 01"
    },
    {
      "id": "slab_01",
      "kind": "slab",
      "name": "Slab 01"
    },
    {
      "id": "wall_01",
      "kind": "wall",
      "name": "Wall 01"
    },
    {
      "id": "door_01",
      "kind": "door",
      "name": "Door 01"
    },
    {
      "id": "opening_01",
      "kind": "opening",
      "name": "Opening 01"
    },
    {
      "id": "duct_01",
      "kind": "duct",
      "name": "Duct 01"
    },
    {
      "id": "space_01",
      "kind": "space",
      "name": "Space 01"
    }
  ],
  "features": [
    {
      "id": "column_01.top_point",
      "owner": "column_01",
      "owner_kind": "column",
      "feature_kind": "point",
      "role": "top_point"
    },
    {
      "id": "slab_01.underside_region",
      "owner": "slab_01",
      "owner_kind": "slab",
      "feature_kind": "region",
      "role": "underside_region"
    },
    {
      "id": "door_01.body",
      "owner": "door_01",
      "owner_kind": "door",
      "feature_kind": "body",
      "role": "body"
    },
    {
      "id": "wall_01.host_region",
      "owner": "wall_01",
      "owner_kind": "wall",
      "feature_kind": "region",
      "role": "host_region"
    },
    {
      "id": "opening_01.profile",
      "owner": "opening_01",
      "owner_kind": "opening",
      "feature_kind": "profile",
      "role": "profile"
    },
    {
      "id": "wall_01.opening_region",
      "owner": "wall_01",
      "owner_kind": "wall",
      "feature_kind": "region",
      "role": "opening_region"
    },
    {
      "id": "duct_01.centerline",
      "owner": "duct_01",
      "owner_kind": "duct",
      "feature_kind": "line",
      "role": "centerline"
    },
    {
      "id": "wall_01.penetration_region",
      "owner": "wall_01",
      "owner_kind": "wall",
      "feature_kind": "region",
      "role": "penetration_region"
    },
    {
      "id": "space_01.boundary",
      "owner": "space_01",
      "owner_kind": "space",
      "feature_kind": "boundary",
      "role": "boundary"
    },
    {
      "id": "wall_01.inner_face",
      "owner": "wall_01",
      "owner_kind": "wall",
      "feature_kind": "face",
      "role": "inner_face"
    }
  ],
  "relationships": [
    {
      "id": "column_01.top_point_supports_slab_01.underside_region",
      "type": "supports",
      "from": "column_01.top_point",
      "to": "slab_01.underside_region",
      "contact_kind": "point_to_region",
      "provenance": "authored_architectural_fixture",
      "status": "accepted"
    },
    {
      "id": "door_01.body_hosted_by_wall_01.host_region",
      "type": "hosted_by",
      "from": "door_01.body",
      "to": "wall_01.host_region",
      "contact_kind": "body_to_region",
      "provenance": "authored_architectural_fixture",
      "status": "accepted"
    },
    {
      "id": "opening_01.profile_voids_wall_01.opening_region",
      "type": "voids",
      "from": "opening_01.profile",
      "to": "wall_01.opening_region",
      "contact_kind": "profile_to_region",
      "provenance": "authored_architectural_fixture",
      "status": "accepted"
    },
    {
      "id": "duct_01.centerline_penetrates_wall_01.penetration_region",
      "type": "penetrates",
      "from": "duct_01.centerline",
      "to": "wall_01.penetration_region",
      "contact_kind": "line_to_region",
      "provenance": "authored_architectural_fixture",
      "status": "accepted"
    },
    {
      "id": "space_01.boundary_bounded_by_wall_01.inner_face",
      "type": "bounded_by",
      "from": "space_01.boundary",
      "to": "wall_01.inner_face",
      "contact_kind": "boundary_to_face",
      "provenance": "authored_architectural_fixture",
      "status": "accepted"
    }
  ]
}
```

- [ ] **Step 3: Create `README.md`**

Create `experiments/architectural_relationship_fixture/README.md` with this exact content:

```markdown
# Architectural Relationship Fixture

Small authored architecture-flavored fixture for relationship fact projection.

This fixture proves the existing neutral `RelationshipFact` substrate works beyond the Pearson
robot graph without adding ontology integration or geometry inference.

## Scope

- graph source: `architectural_relationship_fixture`
- graph revision: `a001`
- pose: `architectural_reference`
- owners: 7
- features: 10
- relationships: 5

Relationships:

```text
column_01.top_point supports slab_01.underside_region
door_01.body hosted_by wall_01.host_region
opening_01.profile voids wall_01.opening_region
duct_01.centerline penetrates wall_01.penetration_region
space_01.boundary bounded_by wall_01.inner_face
```

The wall is the main stress object. Its semantic context card should contain four incoming groups:

```text
hosted_by:incoming:accepted:authored_architectural_fixture
voids:incoming:accepted:authored_architectural_fixture
penetrates:incoming:accepted:authored_architectural_fixture
bounded_by:incoming:accepted:authored_architectural_fixture
```

## Projection Compatibility

The Rhino user text uses `rook.graph.visual_type=member` and `rook.graph.member_id` for all owner
objects. This is parser-facing compatibility language only. The authored graph still names objects
as columns, slabs, walls, doors, openings, ducts, and spaces.

## Commands

Non-live:

```powershell
python -m pytest mcp_server/tests/test_architectural_relationship_fixture.py -q
```

Live, in a throwaway Rhino document:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_architectural_relationship_fixture_live.py -q
```
```

- [ ] **Step 4: Commit graph and README**

Run:

```powershell
git add experiments/architectural_relationship_fixture/assembly_graph.json experiments/architectural_relationship_fixture/README.md
git commit -m "test: add architectural relationship graph fixture"
```

## 5. Task 2: Non-Live Helper And Tests

**Files:**
- Create: `mcp_server/tests/architectural_fixture_helpers.py`
- Create: `mcp_server/tests/test_architectural_relationship_fixture.py`
- Read: `mcp_server/tests/pearson_g002_roundtrip_helpers.py`
- Read: `mcp_server/tests/test_object_semantic_context.py`

- [ ] **Step 1: Create helper module**

Create `mcp_server/tests/architectural_fixture_helpers.py` with this full content:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rook.scene.object_semantic_context import query_object_semantic_context
from rook.scene.scene_graph import SceneGraphAnalytics
from rook.scene.semantic_relationship_inspector import query_semantic_relationships


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "experiments" / "architectural_relationship_fixture"
GRAPH_PATH = FIXTURE_DIR / "assembly_graph.json"
GENERATED_SCRIPT_PATH = FIXTURE_DIR / "generated" / "create_architectural_fixture_rhino.py"

GRAPH_SOURCE = "architectural_relationship_fixture"
GRAPH_REVISION = "a001"
POSE = "architectural_reference"
PROVENANCE = "authored_architectural_fixture"
STATUS = "accepted"

EXPECTED_OWNER_IDS = {
    "column_01",
    "slab_01",
    "wall_01",
    "door_01",
    "opening_01",
    "duct_01",
    "space_01",
}

EXPECTED_FEATURE_IDS = {
    "column_01.top_point",
    "slab_01.underside_region",
    "door_01.body",
    "wall_01.host_region",
    "opening_01.profile",
    "wall_01.opening_region",
    "duct_01.centerline",
    "wall_01.penetration_region",
    "space_01.boundary",
    "wall_01.inner_face",
}

EXPECTED_RELATIONSHIP_TYPES = {
    "bounded_by",
    "hosted_by",
    "penetrates",
    "supports",
    "voids",
}

WALL_EXPECTED_GROUP_KEYS = {
    "hosted_by:incoming:accepted:authored_architectural_fixture",
    "voids:incoming:accepted:authored_architectural_fixture",
    "penetrates:incoming:accepted:authored_architectural_fixture",
    "bounded_by:incoming:accepted:authored_architectural_fixture",
}

FACT_SORT_FIELDS = (
    "relationship",
    "fromFeature",
    "toFeature",
    "graphSource",
    "graphRevision",
    "pose",
)

STRUCTURED_FACT_FIELDS = (
    "relationship",
    "fromFeature",
    "toFeature",
    "contactKind",
    "provenance",
    "status",
    "graphSource",
    "graphRevision",
    "pose",
)


def load_architectural_graph(path: Path = GRAPH_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sorted_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(facts, key=lambda fact: tuple(fact.get(field) for field in FACT_SORT_FIELDS))


def build_expected_facts(graph: dict[str, Any]) -> list[dict[str, Any]]:
    revision = graph["revision"]
    pose_ids = sorted(graph["poses"])
    expected: list[dict[str, Any]] = []
    for pose in pose_ids:
        for relationship in graph["relationships"]:
            expected.append(
                {
                    "relationship": relationship["type"],
                    "fromFeature": relationship["from"],
                    "toFeature": relationship["to"],
                    "contactKind": relationship["contact_kind"],
                    "provenance": relationship.get("provenance", PROVENANCE),
                    "status": relationship.get("status", STATUS),
                    "graphSource": graph["source"],
                    "graphRevision": revision,
                    "pose": pose,
                }
            )
    return sorted_facts(expected)


def semantic_fact(fact: dict[str, Any]) -> dict[str, Any]:
    return {field: fact.get(field) for field in STRUCTURED_FACT_FIELDS}


def semantic_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted_facts([semantic_fact(fact) for fact in facts])


def owner_for_feature(graph: dict[str, Any], feature_id: str) -> str:
    features = {feature["id"]: feature for feature in graph["features"]}
    return str(features[feature_id]["owner"])


def object_name(graph: dict[str, Any], object_id: str) -> str:
    objects = {obj["id"]: obj for obj in graph["objects"]}
    return str(objects[object_id]["name"])


def build_synthetic_projected_graph(graph: dict[str, Any]) -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    for obj in graph["objects"]:
        sg.graph.add_node(obj["id"], name=obj["name"], objectKind=obj["kind"])

    for relationship in graph["relationships"]:
        source_id = owner_for_feature(graph, relationship["from"])
        target_id = owner_for_feature(graph, relationship["to"])
        sg.graph.add_edge(
            source_id,
            target_id,
            key=f"relationship_fact:authored_graph_user_strings:{GRAPH_SOURCE}:{GRAPH_REVISION}:{POSE}:{relationship['id']}",
            relationship=relationship["type"],
            projectionKind="relationship_fact_v1",
            semanticRelationshipType=relationship["type"],
            relationshipFactId=relationship["id"],
            provenance=relationship.get("provenance", PROVENANCE),
            confidence=1.0,
            status=relationship.get("status", STATUS),
            sourceMode="authored_graph_user_strings",
            contactKind=relationship["contact_kind"],
            graphSource=graph["source"],
            graphRevision=graph["revision"],
            pose=POSE,
            fromFeature=relationship["from"],
            toFeature=relationship["to"],
        )
    return sg


def extract_projected_facts(analytics: Any) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for source_id, target_id, _key, attrs in analytics.graph.edges(keys=True, data=True):
        if attrs.get("projectionKind") != "relationship_fact_v1":
            continue
        if attrs.get("graphSource") != GRAPH_SOURCE:
            continue
        if attrs.get("graphRevision") != GRAPH_REVISION:
            continue
        facts.append(
            {
                "relationship": attrs.get("semanticRelationshipType") or attrs.get("relationship"),
                "fromFeature": attrs.get("fromFeature"),
                "toFeature": attrs.get("toFeature"),
                "contactKind": attrs.get("contactKind"),
                "provenance": attrs.get("provenance"),
                "status": attrs.get("status"),
                "graphSource": attrs.get("graphSource"),
                "graphRevision": attrs.get("graphRevision"),
                "pose": attrs.get("pose"),
                "fromObjectId": str(source_id),
                "toObjectId": str(target_id),
            }
        )
    return sorted_facts(facts)


def object_ids_for_features(facts: list[dict[str, Any]], feature_pairs: list[tuple[str, str]]) -> list[str]:
    wanted = set(feature_pairs)
    ids: list[str] = []
    seen: set[str] = set()
    for fact in facts:
        pair = (str(fact.get("fromFeature")), str(fact.get("toFeature")))
        if pair not in wanted:
            continue
        for key in ("fromObjectId", "toObjectId"):
            object_id = fact.get(key)
            if object_id and object_id not in seen:
                seen.add(str(object_id))
                ids.append(str(object_id))
    return ids


def query_fixture_semantic_relationships(analytics: Any, object_ids: list[str]) -> dict[str, Any]:
    return query_semantic_relationships(
        analytics,
        object_ids=object_ids,
        graph_source=GRAPH_SOURCE,
        graph_revision=GRAPH_REVISION,
        poses=[POSE],
    )


def query_fixture_cards(analytics: Any, object_ids: list[str]) -> dict[str, Any]:
    return query_object_semantic_context(
        analytics,
        object_ids=object_ids,
        graph_source=GRAPH_SOURCE,
        graph_revision=GRAPH_REVISION,
        poses=[POSE],
    )


def card_by_id(cards_result: dict[str, Any], object_id: str) -> dict[str, Any]:
    for card in cards_result["cards"]:
        if card["objectId"] == object_id:
            return card
    raise AssertionError(f"card not found for {object_id!r}: {cards_result!r}")


def group_keys(card: dict[str, Any]) -> set[str]:
    return {group["groupKey"] for group in card["groups"]}


def assert_architectural_card_expectations(
    cards_result: dict[str, Any],
    owner_object_ids: dict[str, str] | None = None,
) -> None:
    if owner_object_ids is None:
        owner_object_ids = {owner_id: owner_id for owner_id in EXPECTED_OWNER_IDS}

    assert cards_result["success"] is True, cards_result
    assert cards_result["counts"]["relationshipFactCount"] == 5
    assert cards_result["counts"]["relationshipViewCount"] == 10

    column = card_by_id(cards_result, owner_object_ids["column_01"])
    assert group_keys(column) == {"supports:outgoing:accepted:authored_architectural_fixture"}
    assert column["summary"]["byRelationship"] == {"supports": 1}

    slab = card_by_id(cards_result, owner_object_ids["slab_01"])
    assert group_keys(slab) == {"supports:incoming:accepted:authored_architectural_fixture"}

    door = card_by_id(cards_result, owner_object_ids["door_01"])
    assert group_keys(door) == {"hosted_by:outgoing:accepted:authored_architectural_fixture"}

    duct = card_by_id(cards_result, owner_object_ids["duct_01"])
    assert group_keys(duct) == {"penetrates:outgoing:accepted:authored_architectural_fixture"}

    space = card_by_id(cards_result, owner_object_ids["space_01"])
    assert group_keys(space) == {"bounded_by:outgoing:accepted:authored_architectural_fixture"}

    wall = card_by_id(cards_result, owner_object_ids["wall_01"])
    assert group_keys(wall) == WALL_EXPECTED_GROUP_KEYS
    assert wall["summary"]["relationshipFactCount"] == 4
    assert wall["summary"]["relationshipViewCount"] == 4
    assert wall["summary"]["byDirection"] == {"incoming": 4}
    assert wall["summary"]["byRelationship"] == {
        "bounded_by": 1,
        "hosted_by": 1,
        "penetrates": 1,
        "voids": 1,
    }


def assert_fixture_summary(summary: dict[str, Any]) -> None:
    assert summary["success"] is True
    assert summary["source"] == GRAPH_SOURCE
    assert summary["revision"] == GRAPH_REVISION
    assert summary["pose"] == POSE
    assert summary["ownerObjectCount"] == 7
    assert summary["featureObjectCount"] == 10
    assert summary["relationshipObjectCount"] == 5
    assert summary["createdObjectCount"] == 22
    assert "clearedObjectCount" in summary
    assert set(summary["ownerObjectIds"]) == EXPECTED_OWNER_IDS


def json_from_execute_output(output: str) -> dict[str, Any]:
    start = output.find("{")
    end = output.rfind("}")
    assert start >= 0 and end > start, f"rhino_execute output contained no JSON object: {output!r}"
    return json.loads(output[start : end + 1])


def script_output_from_execute_result(result: dict[str, Any]) -> str:
    output = result.get("output")
    if output is None:
        output = result.get("data", "")
    if isinstance(output, (dict, list)):
        return json.dumps(output)
    assert isinstance(output, str), f"rhino_execute output/data was not text-like: {result!r}"
    assert output, f"rhino_execute returned no script output: {result!r}"
    return output
```

- [ ] **Step 2: Create non-live tests**

Create `mcp_server/tests/test_architectural_relationship_fixture.py` with this full content:

```python
from __future__ import annotations

from .architectural_fixture_helpers import (
    EXPECTED_FEATURE_IDS,
    EXPECTED_OWNER_IDS,
    EXPECTED_RELATIONSHIP_TYPES,
    GRAPH_PATH,
    GRAPH_REVISION,
    GRAPH_SOURCE,
    POSE,
    assert_architectural_card_expectations,
    build_expected_facts,
    build_synthetic_projected_graph,
    extract_projected_facts,
    group_keys,
    load_architectural_graph,
    query_fixture_cards,
    query_fixture_semantic_relationships,
    semantic_facts,
)


def test_architectural_graph_shape_is_expected():
    graph = load_architectural_graph(GRAPH_PATH)

    assert graph["schema"] == "rook.architectural_relationship_fixture.v1"
    assert graph["source"] == GRAPH_SOURCE
    assert graph["revision"] == GRAPH_REVISION
    assert graph["unit"] == "meters"
    assert set(graph["poses"]) == {POSE}
    assert {obj["id"] for obj in graph["objects"]} == EXPECTED_OWNER_IDS
    assert {feature["id"] for feature in graph["features"]} == EXPECTED_FEATURE_IDS
    assert {relationship["type"] for relationship in graph["relationships"]} == EXPECTED_RELATIONSHIP_TYPES
    assert len(graph["objects"]) == 7
    assert len(graph["features"]) == 10
    assert len(graph["relationships"]) == 5


def test_expected_architectural_facts_expand_from_graph():
    facts = build_expected_facts(load_architectural_graph(GRAPH_PATH))

    assert len(facts) == 5
    assert {
        "relationship": "supports",
        "fromFeature": "column_01.top_point",
        "toFeature": "slab_01.underside_region",
        "contactKind": "point_to_region",
        "provenance": "authored_architectural_fixture",
        "status": "accepted",
        "graphSource": GRAPH_SOURCE,
        "graphRevision": GRAPH_REVISION,
        "pose": POSE,
    } in facts
    assert {
        "relationship": "bounded_by",
        "fromFeature": "space_01.boundary",
        "toFeature": "wall_01.inner_face",
        "contactKind": "boundary_to_face",
        "provenance": "authored_architectural_fixture",
        "status": "accepted",
        "graphSource": GRAPH_SOURCE,
        "graphRevision": GRAPH_REVISION,
        "pose": POSE,
    } in facts


def test_synthetic_projection_matches_expected_semantic_facts():
    graph = load_architectural_graph(GRAPH_PATH)
    sg = build_synthetic_projected_graph(graph)

    assert semantic_facts(extract_projected_facts(sg)) == build_expected_facts(graph)


def test_semantic_relationship_inspector_reads_architectural_fixture_edges():
    sg = build_synthetic_projected_graph(load_architectural_graph(GRAPH_PATH))

    result = query_fixture_semantic_relationships(sg, ["column_01", "slab_01", "wall_01"])

    assert result["success"] is True
    assert result["counts"]["relationshipFactCount"] == 5
    assert result["counts"]["relationshipViewCount"] == 6
    wall = next(entry for entry in result["objects"] if entry["objectId"] == "wall_01")
    assert {fact["relationship"] for fact in wall["facts"]} == {
        "hosted_by",
        "voids",
        "penetrates",
        "bounded_by",
    }
    assert {fact["direction"] for fact in wall["facts"]} == {"incoming"}


def test_object_semantic_context_cards_summarize_architectural_fixture():
    sg = build_synthetic_projected_graph(load_architectural_graph(GRAPH_PATH))

    cards = query_fixture_cards(
        sg,
        ["column_01", "slab_01", "wall_01", "door_01", "opening_01", "duct_01", "space_01"],
    )

    assert_architectural_card_expectations(cards)


def test_wall_card_is_multi_fact_architectural_stress_point():
    sg = build_synthetic_projected_graph(load_architectural_graph(GRAPH_PATH))

    cards = query_fixture_cards(sg, ["wall_01"])
    wall = cards["cards"][0]

    assert cards["counts"]["relationshipFactCount"] == 4
    assert cards["counts"]["relationshipViewCount"] == 4
    assert group_keys(wall) == {
        "hosted_by:incoming:accepted:authored_architectural_fixture",
        "voids:incoming:accepted:authored_architectural_fixture",
        "penetrates:incoming:accepted:authored_architectural_fixture",
        "bounded_by:incoming:accepted:authored_architectural_fixture",
    }
```

- [ ] **Step 3: Run non-live tests and verify they pass**

Run:

```powershell
python -m pytest mcp_server/tests/test_architectural_relationship_fixture.py -q
```

Expected:

```text
6 passed
```

- [ ] **Step 4: Commit graph helper and non-live tests**

Run:

```powershell
git add mcp_server/tests/architectural_fixture_helpers.py mcp_server/tests/test_architectural_relationship_fixture.py
git commit -m "test: validate architectural relationship fixture"
```

## 6. Task 3: Rhino Fixture Script

**Files:**
- Create: `experiments/architectural_relationship_fixture/generated/create_architectural_fixture_rhino.py`
- Test: `mcp_server/tests/test_architectural_relationship_fixture.py`

- [ ] **Step 1: Create the Rhino fixture script**

Create `experiments/architectural_relationship_fixture/generated/create_architectural_fixture_rhino.py` with this full content:

```python
"""Create a tiny architectural relationship fixture in Rhino.

Run inside Rhino Python via Rook `rhino_execute` or Rhino's script editor.
The script creates 22 objects on one layer and prints JSON with owner ids.
"""

from __future__ import annotations

import json

import Rhino
import scriptcontext as sc


SOURCE = "architectural_relationship_fixture"
REVISION = "a001"
POSE = "architectural_reference"
LAYER_NAME = "Rook_ArchitecturalRelationshipFixture"


OBJECTS = [
    {"id": "column_01", "name": "Column 01", "kind": "column"},
    {"id": "slab_01", "name": "Slab 01", "kind": "slab"},
    {"id": "wall_01", "name": "Wall 01", "kind": "wall"},
    {"id": "door_01", "name": "Door 01", "kind": "door"},
    {"id": "opening_01", "name": "Opening 01", "kind": "opening"},
    {"id": "duct_01", "name": "Duct 01", "kind": "duct"},
    {"id": "space_01", "name": "Space 01", "kind": "space"},
]

FEATURES = [
    {"id": "column_01.top_point", "owner": "column_01", "feature_kind": "point", "role": "top_point", "point": [0.0, 0.0, 3.0]},
    {"id": "slab_01.underside_region", "owner": "slab_01", "feature_kind": "region", "role": "underside_region", "point": [0.0, 0.0, 3.0]},
    {"id": "door_01.body", "owner": "door_01", "feature_kind": "body", "role": "body", "point": [2.0, -0.1, 1.0]},
    {"id": "wall_01.host_region", "owner": "wall_01", "feature_kind": "region", "role": "host_region", "point": [2.0, 0.0, 1.0]},
    {"id": "opening_01.profile", "owner": "opening_01", "feature_kind": "profile", "role": "profile", "point": [2.0, 0.02, 1.0]},
    {"id": "wall_01.opening_region", "owner": "wall_01", "feature_kind": "region", "role": "opening_region", "point": [2.0, 0.0, 1.0]},
    {"id": "duct_01.centerline", "owner": "duct_01", "feature_kind": "line", "role": "centerline", "point": [4.0, 0.0, 2.2]},
    {"id": "wall_01.penetration_region", "owner": "wall_01", "feature_kind": "region", "role": "penetration_region", "point": [4.0, 0.0, 2.2]},
    {"id": "space_01.boundary", "owner": "space_01", "feature_kind": "boundary", "role": "boundary", "point": [5.5, 0.0, 1.2]},
    {"id": "wall_01.inner_face", "owner": "wall_01", "feature_kind": "face", "role": "inner_face", "point": [5.5, 0.0, 1.2]},
]

RELATIONSHIPS = [
    {
        "id": "column_01.top_point_supports_slab_01.underside_region",
        "type": "supports",
        "from": "column_01.top_point",
        "to": "slab_01.underside_region",
        "contact_kind": "point_to_region",
        "provenance": "authored_architectural_fixture",
        "status": "accepted",
    },
    {
        "id": "door_01.body_hosted_by_wall_01.host_region",
        "type": "hosted_by",
        "from": "door_01.body",
        "to": "wall_01.host_region",
        "contact_kind": "body_to_region",
        "provenance": "authored_architectural_fixture",
        "status": "accepted",
    },
    {
        "id": "opening_01.profile_voids_wall_01.opening_region",
        "type": "voids",
        "from": "opening_01.profile",
        "to": "wall_01.opening_region",
        "contact_kind": "profile_to_region",
        "provenance": "authored_architectural_fixture",
        "status": "accepted",
    },
    {
        "id": "duct_01.centerline_penetrates_wall_01.penetration_region",
        "type": "penetrates",
        "from": "duct_01.centerline",
        "to": "wall_01.penetration_region",
        "contact_kind": "line_to_region",
        "provenance": "authored_architectural_fixture",
        "status": "accepted",
    },
    {
        "id": "space_01.boundary_bounded_by_wall_01.inner_face",
        "type": "bounded_by",
        "from": "space_01.boundary",
        "to": "wall_01.inner_face",
        "contact_kind": "boundary_to_face",
        "provenance": "authored_architectural_fixture",
        "status": "accepted",
    },
]


def _ensure_layer(name: str) -> int:
    layer_index = sc.doc.Layers.FindByFullPath(name, -1)
    if layer_index >= 0:
        return layer_index
    layer = Rhino.DocObjects.Layer()
    layer.Name = name
    return sc.doc.Layers.Add(layer)


def _clear_layer(layer_index: int) -> int:
    layer = sc.doc.Layers[layer_index]
    objects = sc.doc.Objects.FindByLayer(layer)
    cleared = 0
    if objects:
        for rhino_object in list(objects):
            if sc.doc.Objects.Delete(rhino_object, True):
                cleared += 1
    return cleared


def _attrs(layer_index: int, name: str) -> Rhino.DocObjects.ObjectAttributes:
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = layer_index
    attrs.Name = name
    return attrs


def _stamp(object_id, values: dict[str, str]) -> None:
    rhino_object = sc.doc.Objects.FindId(object_id)
    if rhino_object is None:
        raise RuntimeError("object not found: {}".format(object_id))
    for key, value in values.items():
        rhino_object.Attributes.SetUserString(key, value)
    rhino_object.CommitChanges()


def _base_attrs(visual_type: str) -> dict[str, str]:
    return {
        "rook.graph.source": SOURCE,
        "rook.graph.revision": REVISION,
        "rook.graph.pose": POSE,
        "rook.graph.visual_type": visual_type,
    }


def _box(corner1, corner2) -> Rhino.Geometry.Brep:
    bbox = Rhino.Geometry.BoundingBox(
        Rhino.Geometry.Point3d(*corner1),
        Rhino.Geometry.Point3d(*corner2),
    )
    return Rhino.Geometry.Brep.CreateFromBox(bbox)


def _feature_by_id(feature_id: str) -> dict:
    for feature in FEATURES:
        if feature["id"] == feature_id:
            return feature
    raise RuntimeError("feature not found: {}".format(feature_id))


def _object_geometry(object_id: str):
    if object_id == "column_01":
        return _box([-0.15, -0.15, 0.0], [0.15, 0.15, 3.0])
    if object_id == "slab_01":
        return _box([-1.0, -1.0, 3.0], [6.5, 1.0, 3.25])
    if object_id == "wall_01":
        return _box([1.0, -0.05, 0.0], [6.0, 0.05, 3.0])
    if object_id == "door_01":
        return _box([1.7, -0.08, 0.0], [2.3, -0.02, 2.1])
    if object_id == "opening_01":
        return Rhino.Geometry.Rectangle3d(
            Rhino.Geometry.Plane.WorldZX,
            Rhino.Geometry.Interval(0.0, 2.1),
            Rhino.Geometry.Interval(1.7, 2.3),
        ).ToNurbsCurve()
    if object_id == "duct_01":
        return Rhino.Geometry.LineCurve(
            Rhino.Geometry.Point3d(3.5, -0.8, 2.2),
            Rhino.Geometry.Point3d(4.5, 0.8, 2.2),
        )
    if object_id == "space_01":
        polyline = Rhino.Geometry.Polyline(
            [
                Rhino.Geometry.Point3d(1.0, -1.0, 0.02),
                Rhino.Geometry.Point3d(6.0, -1.0, 0.02),
                Rhino.Geometry.Point3d(6.0, 0.0, 0.02),
                Rhino.Geometry.Point3d(1.0, 0.0, 0.02),
                Rhino.Geometry.Point3d(1.0, -1.0, 0.02),
            ]
        )
        return polyline.ToNurbsCurve()
    raise RuntimeError("object geometry not found: {}".format(object_id))


def _add_geometry(geometry, attrs):
    if isinstance(geometry, Rhino.Geometry.Brep):
        return sc.doc.Objects.AddBrep(geometry, attrs)
    if isinstance(geometry, Rhino.Geometry.Curve):
        return sc.doc.Objects.AddCurve(geometry, attrs)
    raise RuntimeError("unsupported geometry type: {}".format(type(geometry)))


def main() -> dict:
    layer_index = _ensure_layer(LAYER_NAME)
    cleared_count = _clear_layer(layer_index)

    feature_ids_by_owner: dict[str, list[str]] = {}
    relationship_ids_by_owner: dict[str, list[str]] = {}
    for feature in FEATURES:
        feature_ids_by_owner.setdefault(feature["owner"], []).append(feature["id"])
    for relationship in RELATIONSHIPS:
        for feature_key in ("from", "to"):
            owner = _feature_by_id(relationship[feature_key])["owner"]
            relationship_ids_by_owner.setdefault(owner, []).append(relationship["id"])

    owner_object_ids: dict[str, str] = {}
    for obj in OBJECTS:
        object_id = _add_geometry(_object_geometry(obj["id"]), _attrs(layer_index, obj["name"]))
        owner_object_ids[obj["id"]] = str(object_id)
        _stamp(
            object_id,
            {
                **_base_attrs("member"),
                "rook.graph.member_id": obj["id"],
                "rook.graph.feature_ids": ",".join(sorted(feature_ids_by_owner.get(obj["id"], []))),
                "rook.graph.relationship_ids": ",".join(sorted(set(relationship_ids_by_owner.get(obj["id"], [])))),
                "rook.graph.arch_kind": obj["kind"],
                "rook.graph.display_name": obj["name"],
            },
        )

    feature_object_ids: dict[str, str] = {}
    for feature in FEATURES:
        point = Rhino.Geometry.Point3d(*feature["point"])
        object_id = sc.doc.Objects.AddPoint(point, _attrs(layer_index, feature["id"]))
        feature_object_ids[feature["id"]] = str(object_id)
        _stamp(
            object_id,
            {
                **_base_attrs("feature"),
                "rook.graph.feature_id": feature["id"],
                "rook.graph.owner": feature["owner"],
                "rook.graph.owner_kind": "member",
                "rook.graph.feature_kind": feature["feature_kind"],
                "rook.graph.role": feature["role"],
                "rook.graph.true_position_m": json.dumps(feature["point"]),
            },
        )

    relationship_object_ids: dict[str, str] = {}
    for relationship in RELATIONSHIPS:
        from_point = Rhino.Geometry.Point3d(*_feature_by_id(relationship["from"])["point"])
        to_point = Rhino.Geometry.Point3d(*_feature_by_id(relationship["to"])["point"])
        object_id = sc.doc.Objects.AddCurve(
            Rhino.Geometry.LineCurve(from_point, to_point),
            _attrs(layer_index, relationship["id"]),
        )
        relationship_object_ids[relationship["id"]] = str(object_id)
        _stamp(
            object_id,
            {
                **_base_attrs("relationship"),
                "rook.graph.relationship_id": relationship["id"],
                "rook.graph.relationship_type": relationship["type"],
                "rook.graph.from_feature": relationship["from"],
                "rook.graph.to_feature": relationship["to"],
                "rook.graph.contact_kind": relationship["contact_kind"],
                "rook.graph.provenance": relationship["provenance"],
                "rook.graph.status": relationship["status"],
            },
        )

    sc.doc.Views.Redraw()
    return {
        "success": True,
        "source": SOURCE,
        "revision": REVISION,
        "pose": POSE,
        "clearedObjectCount": cleared_count,
        "ownerObjectCount": len(owner_object_ids),
        "featureObjectCount": len(feature_object_ids),
        "relationshipObjectCount": len(relationship_object_ids),
        "createdObjectCount": len(owner_object_ids) + len(feature_object_ids) + len(relationship_object_ids),
        "ownerObjectIds": owner_object_ids,
        "featureObjectIds": feature_object_ids,
        "relationshipObjectIds": relationship_object_ids,
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
```

- [ ] **Step 2: Add non-live script drift check**

Append this test to `mcp_server/tests/test_architectural_relationship_fixture.py`:

```python
def test_generated_script_embeds_expected_fixture_constants():
    script = GENERATED_SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'SOURCE = "architectural_relationship_fixture"' in script
    assert 'REVISION = "a001"' in script
    assert 'POSE = "architectural_reference"' in script
    assert 'LAYER_NAME = "Rook_ArchitecturalRelationshipFixture"' in script
    assert '"rook.graph.visual_type": visual_type' in script
    assert '"rook.graph.member_id": obj["id"]' in script
    assert '"rook.graph.owner_kind": "member"' in script
```

Also update the import list at the top of that file to include:

```python
    GENERATED_SCRIPT_PATH,
```

- [ ] **Step 3: Run non-live tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_architectural_relationship_fixture.py -q
```

Expected:

```text
7 passed
```

- [ ] **Step 4: Commit Rhino script**

Run:

```powershell
git add experiments/architectural_relationship_fixture/generated/create_architectural_fixture_rhino.py mcp_server/tests/test_architectural_relationship_fixture.py
git commit -m "test: add architectural Rhino fixture script"
```

## 7. Task 4: Skippable Live Test

**Files:**
- Create: `mcp_server/tests/test_architectural_relationship_fixture_live.py`
- Test: `mcp_server/tests/test_architectural_relationship_fixture_live.py`

- [ ] **Step 1: Create live test**

Create `mcp_server/tests/test_architectural_relationship_fixture_live.py` with this full content:

```python
from __future__ import annotations

import json

import pytest

from .architectural_fixture_helpers import (
    GENERATED_SCRIPT_PATH,
    GRAPH_REVISION,
    GRAPH_SOURCE,
    POSE,
    assert_architectural_card_expectations,
    assert_fixture_summary,
    build_expected_facts,
    extract_projected_facts,
    json_from_execute_output,
    load_architectural_graph,
    object_ids_for_features,
    query_fixture_cards,
    query_fixture_semantic_relationships,
    script_output_from_execute_result,
    semantic_facts,
)
from .conftest import _is_error, fresh_document


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


SELECTED_FEATURE_PAIRS = [
    ("column_01.top_point", "slab_01.underside_region"),
    ("door_01.body", "wall_01.host_region"),
    ("duct_01.centerline", "wall_01.penetration_region"),
    ("space_01.boundary", "wall_01.inner_face"),
]


async def _create_architectural_fixture() -> dict:
    from rook.server import _mcp_tool_executor

    script = GENERATED_SCRIPT_PATH.read_text(encoding="utf-8")
    result = await _mcp_tool_executor("rhino_execute", {"code": script})
    assert not _is_error(result), f"rhino_execute architectural fixture failed: {result!r}"
    summary = json_from_execute_output(script_output_from_execute_result(result))
    assert_fixture_summary(summary)
    return summary


async def test_architectural_relationship_fixture_roundtrip_live(fresh_document):
    from rook.scene.relationship_fact_projection import project_relationship_facts_for_tool
    from rook.scene.relationship_fact_roundtrip import compare_roundtrip
    from rook.scene.scene_graph import get_scene_graph

    graph = load_architectural_graph()
    expected_facts = build_expected_facts(graph)
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
    counts = projection["counts"]
    assert counts["relationshipFactCount"] == 5
    assert counts["projectedEdgeCount"] == 5
    assert counts["skippedFactCount"] == 0
    assert projection["byRelationshipType"] == {
        "bounded_by": 1,
        "hosted_by": 1,
        "penetrates": 1,
        "supports": 1,
        "voids": 1,
    }
    assert projection["byPose"] == {POSE: 5}

    actual_facts = extract_projected_facts(sg)
    report = compare_roundtrip(
        expected_facts=expected_facts,
        actual_facts=semantic_facts(actual_facts),
        context_text="",
        required_substrings=[],
    )
    if not report["success"]:
        report["fixtureSummary"] = fixture_summary
        report["actualFacts"] = actual_facts
        report["projectionCounts"] = counts
        pytest.fail(json.dumps(report, indent=2, sort_keys=True))

    selected_from_projection = object_ids_for_features(actual_facts, SELECTED_FEATURE_PAIRS)
    expected_selected_subset = {
        fixture_summary["ownerObjectIds"]["column_01"],
        fixture_summary["ownerObjectIds"]["slab_01"],
        fixture_summary["ownerObjectIds"]["door_01"],
        fixture_summary["ownerObjectIds"]["wall_01"],
        fixture_summary["ownerObjectIds"]["duct_01"],
        fixture_summary["ownerObjectIds"]["space_01"],
    }
    assert set(selected_from_projection) == expected_selected_subset, (
        f"unexpected projected object ids: {selected_from_projection!r}; "
        f"expected={expected_selected_subset!r}; facts={actual_facts!r}"
    )

    selected_object_ids = [
        fixture_summary["ownerObjectIds"][owner_id]
        for owner_id in sorted(fixture_summary["ownerObjectIds"])
    ]

    inspector = query_fixture_semantic_relationships(sg, selected_object_ids)
    assert inspector["success"] is True, inspector
    assert inspector["counts"]["relationshipFactCount"] == 5
    assert inspector["counts"]["relationshipViewCount"] == 10

    cards = query_fixture_cards(sg, selected_object_ids)
    assert_architectural_card_expectations(cards, fixture_summary["ownerObjectIds"])

    card_text = json.dumps(cards, sort_keys=True)
    for substring in [
        "supports",
        "hosted_by",
        "penetrates",
        "bounded_by",
        "column_01.top_point",
        "slab_01.underside_region",
        "door_01.body",
        "wall_01.host_region",
        "duct_01.centerline",
        "wall_01.penetration_region",
        "space_01.boundary",
        "wall_01.inner_face",
        "accepted",
        "authored_architectural_fixture",
    ]:
        assert substring in card_text
```

- [ ] **Step 2: Run live test without Rhino and confirm it skips or with Rhino and confirm it passes**

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_architectural_relationship_fixture_live.py -q
```

Expected without reachable Rhino:

```text
1 skipped
```

Expected with reachable throwaway Rhino:

```text
1 passed
```

- [ ] **Step 3: Commit live test**

Run:

```powershell
git add mcp_server/tests/test_architectural_relationship_fixture_live.py
git commit -m "test: add live architectural relationship fixture gate"
```

## 8. Task 5: Focused Regression Suite

**Files:**
- Verify all files touched above.

- [ ] **Step 1: Run architectural non-live tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_architectural_relationship_fixture.py -q
```

Expected:

```text
7 passed
```

- [ ] **Step 2: Run existing projection/inspector/card guard tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection.py mcp_server/tests/test_semantic_relationship_inspector.py mcp_server/tests/test_object_semantic_context.py -q
```

Expected:

```text
44 passed
```

If the count differs because upstream tests were added, inspect failures. Passing behavior is required.

- [ ] **Step 3: Run live gate**

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_architectural_relationship_fixture_live.py -q
```

Expected without reachable Rhino:

```text
1 skipped
```

Expected with reachable throwaway Rhino:

```text
1 passed
```

- [ ] **Step 4: Run whitespace checks**

Run:

```powershell
git diff --check
git show --check --stat HEAD
```

Expected:

```text
no whitespace errors
```

- [ ] **Step 5: Inspect final diff**

Run:

```powershell
git diff --stat origin/codex/architectural-relationship-fixture-v1...HEAD
```

Expected:

```text
Diff is limited to experiment fixture files and tests.
```

## 9. Self-Review Checklist

Before handoff, verify:

- [ ] No production source files changed.
- [ ] No new MCP tool was added.
- [ ] No ontology, IFC, BOT, Brick, RDF, TopologicPy, or Revit dependency was added.
- [ ] No projection parser expansion was added.
- [ ] Rhino user text uses `visual_type=member` for owner objects.
- [ ] Rhino feature user text uses `owner_kind=member`.
- [ ] Graph source is `architectural_relationship_fixture`.
- [ ] Graph revision is `a001`.
- [ ] Pose is `architectural_reference`.
- [ ] Non-live tests assert 7 owners, 10 features, 5 relationships.
- [ ] Live script creates 22 objects and clears its dedicated layer on rerun.
- [ ] Wall card asserts four incoming architecture-flavored groups.
- [ ] Tests assert structured facts/groups, not exact prose.
- [ ] Live test projects and inspects the same `SceneGraphAnalytics` instance.

## 10. Final Push

- [ ] **Step 1: Check status**

Run:

```powershell
git status --short --branch
```

Expected:

```text
## codex/architectural-relationship-fixture-v1...origin/codex/architectural-relationship-fixture-v1 [ahead 3]
```

If the live-test commit is skipped because no Rhino target is available, the branch may be ahead by
2 instead of 3 at this point. The required condition is a clean branch with all completed commits
present locally before pushing.

- [ ] **Step 2: Push branch**

Run:

```powershell
git push
```

Expected:

```text
codex/architectural-relationship-fixture-v1 -> codex/architectural-relationship-fixture-v1
```

- [ ] **Step 3: Report handoff**

Report:

```text
Implemented Architectural Relationship Fixture v1.
Non-live tests passed.
Live test skipped cleanly or passed against throwaway Rhino.
Branch clean/synced after push.
```

Do not claim the live gate passed unless it actually reports `1 passed`.
