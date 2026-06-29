# Authored Graph Schema v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate authored relationship graph records from robot-era parser keys to domain-neutral but typed v2 object/feature/relationship vocabulary.

**Architecture:** Make the parser v2-first, then migrate checked-in fixture source JSON and generated Rhino scripts one fixture at a time. Keep relationship fact projection output stable, keep domain terms as data/profile values, and add a stale-key scan after migrated fixtures/tests no longer need `member_id`, `node_id`, `visual_type=member|joint`, or `rook.graph.owner`.

**Tech Stack:** Python 3, `pytest`, JSON fixture files, existing Rhino script generators, Rook MCP scene graph modules.

---

## File Structure

- Modify `mcp_server/src/rook/scene/relationship_fact_projection.py`
  - Parse v2 owner object records with `visual_type=object`, `object_id`, and `object_kind`.
  - Parse feature records with `owner_id` and optional `owner_kind`.
  - Resolve owners by `owner_id`; validate optional feature `owner_kind` against owner `object_kind`.
  - Keep relationship record parsing and projected edge attributes stable.

- Modify `mcp_server/tests/test_relationship_fact_projection.py`
  - Convert pure parser fixtures to v2 user strings.
  - Add tests for missing `object_id`, missing `object_kind`, optional `owner_kind`, and mismatched `owner_kind`.

- Modify `mcp_server/tests/test_relationship_fact_projection_tool.py`
  - Convert tool hydration fixtures to v2 user strings.
  - Preserve scoped hydration/filter tests and strict-mode behavior.

- Modify `experiments/architectural_relationship_fixture/assembly_graph.json`
  - Persist v2 source field names: `object_id`, `object_kind`, `feature_id`, `owner_id`, `relationship_id`, `relationship_type`, `from_feature`, `to_feature`.

- Modify `experiments/architectural_relationship_fixture/generated/create_architectural_fixture_rhino.py`
  - Consume v2 source field names.
  - Emit v2 user text.

- Modify `mcp_server/tests/architectural_fixture_helpers.py`
  - Read v2 source field names.

- Modify `mcp_server/tests/test_architectural_relationship_fixture.py`
  - Update generated-script assertions to require v2 keys and reject v1 keys.

- Modify `experiments/architectural_relationship_fixture/README.md`
  - Replace v1 parser-facing wording with v2 schema wording.

- Modify `experiments/pearson_robot_skeleton_graph/assembly_graph.json`
  - Add/migrate to canonical `objects`, v2 `features`, and v2 `relationships`.
  - It may retain domain-specific metadata such as former member endpoints and node positions where the generator needs them, but persisted relationship graph schema should use v2 names.

- Modify `experiments/pearson_robot_skeleton_graph/scripts/build_skeleton_graph_rhino.py`
  - Consume v2 objects/features/relationships.
  - Emit v2 user text.

- Regenerate `experiments/pearson_robot_skeleton_graph/generated/skeleton_graph_rhino.py`
  - Use the updated builder script.

- Modify Pearson helper/tests:
  - `mcp_server/tests/pearson_g002_roundtrip_helpers.py`
  - `mcp_server/tests/test_pearson_g002_roundtrip_gate.py`
  - `mcp_server/tests/test_pearson_g002_roundtrip_gate_live.py`

- Add or modify a stale-key scan test:
  - Preferred new file: `mcp_server/tests/test_authored_graph_schema_v2.py`

---

## Task 1: Parser v2 Core

**Files:**
- Modify: `mcp_server/src/rook/scene/relationship_fact_projection.py`
- Modify: `mcp_server/tests/test_relationship_fact_projection.py`

- [ ] **Step 1: Update pure parser test helpers to v2**

In `mcp_server/tests/test_relationship_fact_projection.py`, replace `_owner_record`, `_joint_record`, and `_feature_record` with v2 versions:

```python
def _owner_record(object_id: str, *, pose: str = "reclined_robot") -> rel.RuntimeObjectRecord:
    return rel.RuntimeObjectRecord(
        object_id,
        {
            "rook.graph.source": "pearson_robot_skeleton_graph",
            "rook.graph.revision": "g002",
            "rook.graph.pose": pose,
            "rook.graph.visual_type": "object",
            "rook.graph.object_id": "spine_base_to_spine_top",
            "rook.graph.object_kind": "member",
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
            "rook.graph.visual_type": "object",
            "rook.graph.object_id": "spine_base",
            "rook.graph.object_kind": "joint",
            "rook.graph.feature_ids": "spine_base.point",
            "rook.graph.relationship_ids": "spine_base_to_spine_top.start_connects_spine_base",
        },
    )


def _feature_record(
    object_id: str,
    feature_id: str,
    owner_id: str,
    owner_kind: str | None = None,
    *,
    pose: str = "reclined_robot",
) -> rel.RuntimeObjectRecord:
    user_strings = {
        "rook.graph.source": "pearson_robot_skeleton_graph",
        "rook.graph.revision": "g002",
        "rook.graph.pose": pose,
        "rook.graph.visual_type": "feature",
        "rook.graph.feature_id": feature_id,
        "rook.graph.owner_id": owner_id,
        "rook.graph.feature_kind": "endpoint",
        "rook.graph.role": "start",
        "rook.graph.true_position_m": "[0.0, 0.0, 0.0]",
        "rook.graph.visual_lift_m": "0.08",
    }
    if owner_kind is not None:
        user_strings["rook.graph.owner_kind"] = owner_kind
    return rel.RuntimeObjectRecord(object_id, user_strings)
```

Then update `_valid_records()` so the joint feature uses `owner_kind="joint"`:

```python
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
        _feature_record("feature-joint-point-id", "spine_base.point", "spine_base", "joint"),
        _relationship_record("relationship-marker-id"),
    ]
```

- [ ] **Step 2: Update parser expectations for v2 owner kinds**

In `test_parse_runtime_records_defaults_missing_fact_fields`, update the expected owner keys:

```python
assert set(parsed.owners_by_key) == {
    ("pearson_robot_skeleton_graph", "g002", "reclined_robot", "spine_base_to_spine_top"),
    ("pearson_robot_skeleton_graph", "g002", "reclined_robot", "spine_base"),
}
```

In `test_resolve_relationship_facts_projects_owner_to_owner`, update:

```python
assert fact.to_owner_kind == "joint"
```

In `test_pose_separation_creates_distinct_edge_keys`, update the rest-pose joint feature call:

```python
_feature_record("feature-joint-point-id-rest", "spine_base.point", "spine_base", "joint", pose="rest_t_pose")
```

In `test_missing_owner_object_reports_diagnostic`, update the joint feature call:

```python
_feature_record("feature-joint-point-id", "spine_base.point", "spine_base", "joint")
```

- [ ] **Step 3: Add parser tests for v2 validation**

Append these tests to `mcp_server/tests/test_relationship_fact_projection.py`:

```python
def test_parse_runtime_records_requires_object_id_for_object_records():
    bad_owner = _owner_record("member-rhino-id")
    bad_owner.user_strings.pop("rook.graph.object_id")

    parsed = rel.parse_runtime_records([bad_owner])

    assert parsed.owners_by_key == {}
    assert parsed.diagnostics["ownerObjectsMissingOwnerId"] == 1


def test_parse_runtime_records_requires_object_kind_for_object_records():
    bad_owner = _owner_record("member-rhino-id")
    bad_owner.user_strings.pop("rook.graph.object_kind")

    parsed = rel.parse_runtime_records([bad_owner])

    assert parsed.owners_by_key == {}
    assert parsed.diagnostics["ownerObjectsMissingOwnerKind"] == 1


def test_feature_owner_kind_is_optional_and_resolves_by_owner_id():
    records = [
        _owner_record("member-rhino-id"),
        _joint_record("joint-rhino-id"),
        _feature_record(
            "feature-member-start-id",
            "spine_base_to_spine_top.start",
            "spine_base_to_spine_top",
            owner_kind=None,
        ),
        _feature_record("feature-joint-point-id", "spine_base.point", "spine_base", owner_kind=None),
        _relationship_record("relationship-marker-id"),
    ]

    fact_set = rel.build_relationship_fact_set(rel.parse_runtime_records(records), strict=True)

    assert fact_set.success is True
    assert len(fact_set.facts) == 1
    fact = fact_set.facts[0]
    assert fact.from_owner_kind == "member"
    assert fact.to_owner_kind == "joint"


def test_feature_owner_kind_mismatch_reports_diagnostic():
    records = [
        _owner_record("member-rhino-id"),
        _joint_record("joint-rhino-id"),
        _feature_record(
            "feature-member-start-id",
            "spine_base_to_spine_top.start",
            "spine_base_to_spine_top",
            "joint",
        ),
        _feature_record("feature-joint-point-id", "spine_base.point", "spine_base", "joint"),
        _relationship_record("relationship-marker-id"),
    ]

    result = rel.build_relationship_fact_set(rel.parse_runtime_records(records), strict=False)

    assert result.success is True
    assert result.facts == []
    assert result.diagnostics["featureObjectsOwnerKindMismatch"] == 1


def test_duplicate_object_id_with_conflicting_kind_reports_diagnostic():
    duplicate = _owner_record("member-rhino-id-duplicate")
    duplicate.user_strings["rook.graph.object_kind"] = "joint"

    parsed = rel.parse_runtime_records([_owner_record("member-rhino-id"), duplicate])

    assert len(parsed.owners_by_key) == 1
    assert parsed.owners_by_key[
        ("pearson_robot_skeleton_graph", "g002", "reclined_robot", "spine_base_to_spine_top")
    ].owner_kind == "member"
    assert parsed.diagnostics["duplicateOwnerRecords"] == 1
```

- [ ] **Step 4: Run parser tests and verify they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection.py -q
```

Expected before implementation:

- failures because `visual_type=object` is not parsed;
- missing diagnostic key `ownerObjectsMissingOwnerKind`;
- mismatch diagnostic not produced.

- [ ] **Step 5: Implement v2 parser changes**

In `mcp_server/src/rook/scene/relationship_fact_projection.py`, update `VALIDATION_DIAGNOSTIC_KEYS` by adding:

```python
"ownerObjectsMissingOwnerKind",
"featureObjectsOwnerKindMismatch",
```

Replace `_parse_owner_record` with:

```python
def _parse_owner_record(
    record: RuntimeObjectRecord,
    source: str,
    revision: str,
    pose: str,
    diagnostics: dict[str, int],
) -> OwnerRecord | None:
    owner_id = _clean_str(record.user_strings.get("rook.graph.object_id"))
    owner_kind = _clean_str(record.user_strings.get("rook.graph.object_kind"))
    if not owner_id:
        _bump(diagnostics, "ownerObjectsMissingOwnerId")
        return None
    if not owner_kind:
        _bump(diagnostics, "ownerObjectsMissingOwnerKind")
        return None
    return OwnerRecord(record.object_id, source, revision, pose, owner_kind, owner_id)
```

Update `ParsedRuntimeRecords.owners_by_key` to remove `owner_kind` from the key:

```python
owners_by_key: dict[tuple[str, str, str, str], OwnerRecord]
```

Update the local variable in `parse_runtime_records`:

```python
owners_by_key: dict[tuple[str, str, str, str], OwnerRecord] = {}
```

Replace the feature owner read in `_parse_feature_record`:

```python
owner = _clean_str(user_strings.get("rook.graph.owner_id"))
owner_kind = _clean_str(user_strings.get("rook.graph.owner_kind"))
```

and keep the missing-owner diagnostic only for `owner_id`:

```python
if not owner:
    _bump(diagnostics, "featureObjectsMissingOwner")
    return None
```

In `parse_runtime_records`, replace:

```python
if visual_type in {"member", "joint"}:
    owner = _parse_owner_record(record, source, revision, pose, visual_type, diagnostics)
```

with:

```python
if visual_type == "object":
    owner = _parse_owner_record(record, source, revision, pose, diagnostics)
```

Then key owner records by owner id only and preserve the first object when a duplicate/conflicting
record appears:

```python
key = (source, revision, pose, owner.owner_id)
if key in owners_by_key:
    _bump(diagnostics, "duplicateOwnerRecords")
    continue
owners_by_key[key] = owner
```

In `build_relationship_fact_set`, replace owner lookup with `owner_id` only and validate optional `owner_kind` after resolving owners:

```python
from_owner = _owner_for_feature(parsed, source, revision, pose, from_feature)
to_owner = _owner_for_feature(parsed, source, revision, pose, to_feature)
if from_owner is None or to_owner is None:
    _bump(diagnostics, "relationshipFactsMissingOwnerObject")
    continue
if from_feature.owner_kind and from_feature.owner_kind != from_owner.owner_kind:
    _bump(diagnostics, "featureObjectsOwnerKindMismatch")
    continue
if to_feature.owner_kind and to_feature.owner_kind != to_owner.owner_kind:
    _bump(diagnostics, "featureObjectsOwnerKindMismatch")
    continue
```

Add the helper above `build_relationship_fact_set`:

```python
def _owner_for_feature(
    parsed: ParsedRuntimeRecords,
    source: str,
    revision: str,
    pose: str,
    feature: FeatureRecord,
) -> OwnerRecord | None:
    return parsed.owners_by_key.get((source, revision, pose, feature.owner))
```

- [ ] **Step 6: Run parser tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit parser v2 core**

Run:

```powershell
git add mcp_server/src/rook/scene/relationship_fact_projection.py mcp_server/tests/test_relationship_fact_projection.py
git commit -m "feat: parse authored graph schema v2"
```

---

## Task 2: Tool Projection Fixtures v2

**Files:**
- Modify: `mcp_server/tests/test_relationship_fact_projection_tool.py`

- [ ] **Step 1: Convert `_user_strings_for` records to v2**

In `mcp_server/tests/test_relationship_fact_projection_tool.py`, update every owner record:

```python
"rook.graph.visual_type": "object",
"rook.graph.object_id": "spine_base_to_spine_top",
"rook.graph.object_kind": "member",
```

for former member records, and:

```python
"rook.graph.visual_type": "object",
"rook.graph.object_id": "spine_base",
"rook.graph.object_kind": "joint",
```

for former joint records.

For unrelated records, use:

```python
"rook.graph.object_id": "unrelated_member",
"rook.graph.object_kind": "member",
```

and:

```python
"rook.graph.object_id": "unrelated_joint",
"rook.graph.object_kind": "joint",
```

Update feature records from:

```python
"rook.graph.owner": "spine_base_to_spine_top",
```

to:

```python
"rook.graph.owner_id": "spine_base_to_spine_top",
```

and from:

```python
"rook.graph.owner_kind": "node",
```

to:

```python
"rook.graph.owner_kind": "joint",
```

- [ ] **Step 2: Run tool projection tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection_tool.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Commit tool fixture migration**

Run:

```powershell
git add mcp_server/tests/test_relationship_fact_projection_tool.py
git commit -m "test: migrate projection tool fixtures to schema v2"
```

---

## Task 3: Architectural Fixture v2

**Files:**
- Modify: `experiments/architectural_relationship_fixture/assembly_graph.json`
- Modify: `experiments/architectural_relationship_fixture/generated/create_architectural_fixture_rhino.py`
- Modify: `experiments/architectural_relationship_fixture/README.md`
- Modify: `mcp_server/tests/architectural_fixture_helpers.py`
- Modify: `mcp_server/tests/test_architectural_relationship_fixture.py`

- [ ] **Step 1: Migrate architectural source JSON field names**

In `experiments/architectural_relationship_fixture/assembly_graph.json`:

- for each object, rename `id` to `object_id`;
- for each object, rename `kind` to `object_kind`;
- for each feature, rename `id` to `feature_id`;
- for each feature, rename `owner` to `owner_id`;
- keep `owner_kind` as optional metadata;
- keep `feature_kind`;
- for each relationship, rename `id` to `relationship_id`;
- for each relationship, rename `type` to `relationship_type`;
- for each relationship, rename `from` to `from_feature`;
- for each relationship, rename `to` to `to_feature`.

The first object should become:

```json
{
  "object_id": "column_01",
  "object_kind": "column",
  "name": "Column 01"
}
```

The first feature should become:

```json
{
  "feature_id": "column_01.top_point",
  "owner_id": "column_01",
  "owner_kind": "column",
  "feature_kind": "point",
  "role": "top_point"
}
```

The first relationship should become:

```json
{
  "relationship_id": "column_01.top_point_supports_slab_01.underside_region",
  "relationship_type": "supports",
  "from_feature": "column_01.top_point",
  "to_feature": "slab_01.underside_region",
  "contact_kind": "point_to_region",
  "provenance": "authored_architectural_fixture",
  "status": "accepted"
}
```

- [ ] **Step 2: Update architectural fixture helpers**

In `mcp_server/tests/architectural_fixture_helpers.py`, update helper reads:

```python
return {obj["object_id"] for obj in graph["objects"]}
```

where object ids are collected.

Update feature reads:

```python
feature["feature_id"]
feature["owner_id"]
relationship["from_feature"]
relationship["to_feature"]
relationship["relationship_id"]
relationship["relationship_type"]
```

Preserve runtime output keys such as `ownerObjectIds` because they are fixture summary API keys, not authored graph schema keys.

- [ ] **Step 3: Update architectural Rhino generator**

In `experiments/architectural_relationship_fixture/generated/create_architectural_fixture_rhino.py`, update dictionary reads:

```python
feature_ids_by_owner.setdefault(feature["owner_id"], []).append(feature["feature_id"])
for feature_key in ("from_feature", "to_feature"):
    owner = _feature_by_id(relationship[feature_key])["owner_id"]
```

For owner objects, stamp:

```python
{
    **_base_attrs("object"),
    "rook.graph.object_id": obj["object_id"],
    "rook.graph.object_kind": obj["object_kind"],
    "rook.graph.feature_ids": ",".join(sorted(feature_ids_by_owner.get(obj["object_id"], []))),
    "rook.graph.relationship_ids": ",".join(
        sorted(set(relationship_ids_by_owner.get(obj["object_id"], [])))
    ),
    "rook.graph.display_name": obj["name"],
}
```

For features, stamp:

```python
{
    **_base_attrs("feature"),
    "rook.graph.feature_id": feature["feature_id"],
    "rook.graph.owner_id": feature["owner_id"],
    "rook.graph.feature_kind": feature["feature_kind"],
    "rook.graph.role": feature["role"],
    "rook.graph.true_position_m": json.dumps(feature["point"]),
}
```

Add `rook.graph.owner_kind` only if present:

```python
if feature.get("owner_kind"):
    user_strings["rook.graph.owner_kind"] = feature["owner_kind"]
```

For relationships, stamp:

```python
{
    **_base_attrs("relationship"),
    "rook.graph.relationship_id": relationship["relationship_id"],
    "rook.graph.relationship_type": relationship["relationship_type"],
    "rook.graph.from_feature": relationship["from_feature"],
    "rook.graph.to_feature": relationship["to_feature"],
    "rook.graph.contact_kind": relationship["contact_kind"],
    "rook.graph.provenance": relationship["provenance"],
    "rook.graph.status": relationship["status"],
}
```

- [ ] **Step 4: Update architectural script assertions**

In `mcp_server/tests/test_architectural_relationship_fixture.py`, replace v1 assertions:

```python
assert '"rook.graph.member_id": obj["id"]' in script
assert '"rook.graph.owner_kind": "member"' in script
```

with v2 assertions:

```python
assert '"rook.graph.visual_type": visual_type' in script
assert '"rook.graph.object_id": obj["object_id"]' in script
assert '"rook.graph.object_kind": obj["object_kind"]' in script
assert '"rook.graph.owner_id": feature["owner_id"]' in script
assert '"rook.graph.relationship_type": relationship["relationship_type"]' in script
assert '"rook.graph.from_feature": relationship["from_feature"]' in script
assert '"rook.graph.to_feature": relationship["to_feature"]' in script
assert '"rook.graph.member_id"' not in script
assert '"rook.graph.owner":' not in script
```

- [ ] **Step 5: Update architectural README**

In `experiments/architectural_relationship_fixture/README.md`, replace the old sentence:

```text
The Rhino user text uses `rook.graph.visual_type=member` and `rook.graph.member_id` for all owner
```

with:

```text
The Rhino user text uses `rook.graph.visual_type=object`, `rook.graph.object_id`, and
`rook.graph.object_kind` for owner objects. Feature markers use `rook.graph.owner_id`; optional
`rook.graph.owner_kind` is denormalized metadata and must match the owner object's kind when present.
```

- [ ] **Step 6: Run architectural non-live tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_architectural_relationship_fixture.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit architectural migration**

Run:

```powershell
git add experiments/architectural_relationship_fixture/assembly_graph.json experiments/architectural_relationship_fixture/generated/create_architectural_fixture_rhino.py experiments/architectural_relationship_fixture/README.md mcp_server/tests/architectural_fixture_helpers.py mcp_server/tests/test_architectural_relationship_fixture.py
git commit -m "test: migrate architectural fixture to authored graph schema v2"
```

---

## Task 4: Pearson Fixture v2

**Files:**
- Modify: `experiments/pearson_robot_skeleton_graph/assembly_graph.json`
- Modify: `experiments/pearson_robot_skeleton_graph/scripts/build_skeleton_graph_rhino.py`
- Regenerate: `experiments/pearson_robot_skeleton_graph/generated/skeleton_graph_rhino.py`
- Modify: `mcp_server/tests/pearson_g002_roundtrip_helpers.py`
- Modify: `mcp_server/tests/test_pearson_g002_roundtrip_gate.py`

- [ ] **Step 1: Migrate Pearson source JSON to include v2 `objects`**

In `experiments/pearson_robot_skeleton_graph/assembly_graph.json`, add a top-level `objects` list.

For every current `nodes[]` entry, add:

```json
{
  "object_id": "spine_base",
  "object_kind": "joint",
  "role": "lower_torso",
  "side": "center",
  "domain_aliases": ["spine", "datum"]
}
```

For every current `members[]` entry, add:

```json
{
  "object_id": "spine_base_to_spine_top",
  "object_kind": "member",
  "from_object_id": "spine_base",
  "to_object_id": "spine_top",
  "role": "spine",
  "member_type": "primary_axis",
  "domain_aliases": ["bone", "spine", "datum"]
}
```

Keep `nodes` and `members` only if the generator still needs them for geometry during this slice. If retained, they are geometry/domain convenience sections, not parser-facing authored relationship schema.

- [ ] **Step 2: Migrate Pearson features and relationships in source JSON**

In the same JSON file:

- rename every feature `id` to `feature_id`;
- rename every feature `owner` to `owner_id`;
- rename every feature `kind` to `feature_kind`;
- change former `owner_kind=node` values to `owner_kind=joint`;
- keep former `owner_kind=member` values as `member`;
- rename every relationship `id` to `relationship_id`;
- rename every relationship `type` to `relationship_type`;
- rename every relationship `from` to `from_feature`;
- rename every relationship `to` to `to_feature`.

The first node-owned feature should become:

```json
{
  "feature_id": "root_pelvis.point",
  "owner_id": "root_pelvis",
  "owner_kind": "joint",
  "feature_kind": "point",
  "role": "assembly_datum"
}
```

The first member-owned feature should become:

```json
{
  "feature_id": "root_to_spine_base.start",
  "owner_id": "root_to_spine_base",
  "owner_kind": "member",
  "feature_kind": "endpoint",
  "role": "start_port"
}
```

The first relationship should become:

```json
{
  "relationship_id": "root_to_spine_base.start_connects_root_pelvis",
  "relationship_type": "connects",
  "from_feature": "root_to_spine_base.start",
  "to_feature": "root_pelvis.point",
  "contact_kind": "point_to_point",
  "provenance": "authored_assembly_graph"
}
```

- [ ] **Step 3: Update Pearson builder script for v2 source and user text**

In `experiments/pearson_robot_skeleton_graph/scripts/build_skeleton_graph_rhino.py`:

Create dictionaries from v2 objects:

```python
objects_by_id = {obj["object_id"]: obj for obj in GRAPH["objects"]}
joint_objects = [obj for obj in GRAPH["objects"] if obj["object_kind"] == "joint"]
member_objects = [obj for obj in GRAPH["objects"] if obj["object_kind"] == "member"]
```

Update `add_joint` to accept an object record and stamp:

```python
"rook.graph.visual_type": "object",
"rook.graph.object_id": joint["object_id"],
"rook.graph.object_kind": joint["object_kind"],
```

Update `add_member` to stamp:

```python
"rook.graph.visual_type": "object",
"rook.graph.object_id": member["object_id"],
"rook.graph.object_kind": member["object_kind"],
"rook.graph.from_object_id": member["from_object_id"],
"rook.graph.to_object_id": member["to_object_id"],
```

Update feature access:

```python
owner_id = feature["owner_id"]
feature_id = feature["feature_id"]
feature_kind = feature["feature_kind"]
```

Update feature stamps:

```python
"rook.graph.feature_id": feature["feature_id"],
"rook.graph.owner_id": feature["owner_id"],
"rook.graph.feature_kind": feature["feature_kind"],
```

Add optional owner kind:

```python
if feature.get("owner_kind"):
    user_strings["rook.graph.owner_kind"] = feature["owner_kind"]
```

Update relationship access:

```python
relationship["relationship_id"]
relationship["relationship_type"]
relationship["from_feature"]
relationship["to_feature"]
```

Do not emit `rook.graph.member_id`, `rook.graph.node_id`, or `rook.graph.owner`.

- [ ] **Step 4: Regenerate Pearson generated script**

Run the builder script:

```powershell
python experiments/pearson_robot_skeleton_graph/scripts/build_skeleton_graph_rhino.py
```

Expected:

- `experiments/pearson_robot_skeleton_graph/generated/skeleton_graph_rhino.py` updates;
- generated script contains `rook.graph.object_id`;
- generated script does not contain `rook.graph.member_id`, `rook.graph.node_id`, or `"rook.graph.owner":`.

- [ ] **Step 5: Update Pearson helpers/tests**

In `mcp_server/tests/pearson_g002_roundtrip_helpers.py`, update graph reads:

```python
relationship["relationship_id"]
relationship["relationship_type"]
relationship["from_feature"]
relationship["to_feature"]
relationship["contact_kind"]
```

If helper code counts members/nodes from source JSON, count from `objects`:

```python
member_count = sum(1 for obj in graph["objects"] if obj["object_kind"] == "member")
joint_count = sum(1 for obj in graph["objects"] if obj["object_kind"] == "joint")
```

Expected authored fact count remains:

```python
len(graph["relationships"]) * len(graph["poses"]) == 56
```

- [ ] **Step 6: Run Pearson non-live tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_pearson_g002_roundtrip_gate.py -q
```

Expected: all non-live Pearson tests pass.

- [ ] **Step 7: Commit Pearson migration**

Run:

```powershell
git add experiments/pearson_robot_skeleton_graph/assembly_graph.json experiments/pearson_robot_skeleton_graph/scripts/build_skeleton_graph_rhino.py experiments/pearson_robot_skeleton_graph/generated/skeleton_graph_rhino.py mcp_server/tests/pearson_g002_roundtrip_helpers.py mcp_server/tests/test_pearson_g002_roundtrip_gate.py
git commit -m "test: migrate Pearson fixture to authored graph schema v2"
```

---

## Task 5: Stale-Key Guard and Final Regression

**Files:**
- Create: `mcp_server/tests/test_authored_graph_schema_v2.py`

- [ ] **Step 1: Add stale-key scan test**

Create `mcp_server/tests/test_authored_graph_schema_v2.py`:

```python
from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

MIGRATED_PATHS = [
    REPO_ROOT / "mcp_server" / "src" / "rook" / "scene" / "relationship_fact_projection.py",
    REPO_ROOT / "mcp_server" / "tests" / "test_relationship_fact_projection.py",
    REPO_ROOT / "mcp_server" / "tests" / "test_relationship_fact_projection_tool.py",
    REPO_ROOT / "mcp_server" / "tests" / "test_architectural_relationship_fixture.py",
    REPO_ROOT / "mcp_server" / "tests" / "architectural_fixture_helpers.py",
    REPO_ROOT / "mcp_server" / "tests" / "pearson_g002_roundtrip_helpers.py",
    REPO_ROOT / "mcp_server" / "tests" / "test_pearson_g002_roundtrip_gate.py",
    REPO_ROOT / "experiments" / "architectural_relationship_fixture" / "assembly_graph.json",
    REPO_ROOT / "experiments" / "architectural_relationship_fixture" / "generated" / "create_architectural_fixture_rhino.py",
    REPO_ROOT / "experiments" / "architectural_relationship_fixture" / "README.md",
    REPO_ROOT / "experiments" / "pearson_robot_skeleton_graph" / "assembly_graph.json",
    REPO_ROOT / "experiments" / "pearson_robot_skeleton_graph" / "scripts" / "build_skeleton_graph_rhino.py",
    REPO_ROOT / "experiments" / "pearson_robot_skeleton_graph" / "generated" / "skeleton_graph_rhino.py",
]

STALE_SCHEMA_PATTERNS = [
    re.compile(r"rook\.graph\.member_id"),
    re.compile(r"rook\.graph\.node_id"),
    re.compile(r"rook\.graph\.owner(?!_)"),
    re.compile(r"rook\.graph\.visual_type\s*=\s*member"),
    re.compile(r"rook\.graph\.visual_type\s*=\s*joint"),
    re.compile(r"rook\.graph\.visual_type[\\\"]*\s*:\s*[\\\"]*member"),
    re.compile(r"rook\.graph\.visual_type[\\\"]*\s*:\s*[\\\"]*joint"),
]


def test_migrated_authored_graph_schema_v2_paths_do_not_use_v1_usertext_keys():
    hits: list[tuple[str, str]] = []
    for path in MIGRATED_PATHS:
        text = path.read_text(encoding="utf-8")
        for pattern in STALE_SCHEMA_PATTERNS:
            if pattern.search(text):
                hits.append((str(path.relative_to(REPO_ROOT)), pattern.pattern))

    assert hits == []
```

- [ ] **Step 2: Run stale-key scan**

Run:

```powershell
python -m pytest mcp_server/tests/test_authored_graph_schema_v2.py -q
```

Expected: pass. If it fails, remove stale v1 usertext keys from migrated files rather than broadening the test.

- [ ] **Step 3: Run focused schema-v2 suite**

Run:

```powershell
python -m pytest mcp_server/tests/test_authored_graph_schema_v2.py mcp_server/tests/test_relationship_fact_projection.py mcp_server/tests/test_relationship_fact_projection_tool.py mcp_server/tests/test_architectural_relationship_fixture.py mcp_server/tests/test_pearson_g002_roundtrip_gate.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Run adjacent semantic suites**

Run:

```powershell
python -m pytest mcp_server/tests/test_semantic_relationship_inspector.py mcp_server/tests/test_semantic_relationship_inspector_tool.py mcp_server/tests/test_object_semantic_context.py mcp_server/tests/test_object_semantic_context_tool.py mcp_server/tests/test_relationship_profile.py mcp_server/tests/test_relationship_profile_tool.py mcp_server/tests/test_object_semantic_context_profile_boundary.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Optional live gates**

If Rhino is open with a throwaway document, run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_architectural_relationship_fixture_live.py -q
python -m pytest -m requires_rhino mcp_server/tests/test_pearson_g002_roundtrip_gate_live.py -q
```

Expected:

- each live test passes when Rhino/Rook is reachable;
- each live test skips cleanly when Rhino/Rook is unavailable.

- [ ] **Step 6: Commit stale-key guard**

Run:

```powershell
git add mcp_server/tests/test_authored_graph_schema_v2.py
git commit -m "test: guard authored graph schema v2 keys"
```

- [ ] **Step 7: Final hygiene**

Run:

```powershell
git diff --check
git show --check --stat HEAD
git status --short --branch
```

Expected:

- no whitespace errors;
- `git show --check --stat HEAD` exits 0;
- worktree is clean.

- [ ] **Step 8: Push branch**

Run:

```powershell
git push -u origin codex/authored-graph-schema-v2
```

Expected: branch pushes successfully.

---

## Self-Review Notes

- Spec coverage: This plan migrates parser keys, persisted fixture JSON, emitted Rhino user text, architectural fixture, Pearson fixture, stale-key guard, and focused regression tests.
- Compatibility stance: The plan does not add a v1 compatibility path. If implementation forces one, it must be private, diagnostic-emitting, and tested as legacy only before continuing.
- Risk control: Parser changes happen first, then architectural fixture migration, then Pearson fixture migration, with focused tests after each step.
- Red-flag scan: No incomplete markers or vague future tasks remain.
