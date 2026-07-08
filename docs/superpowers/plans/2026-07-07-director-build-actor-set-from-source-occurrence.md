# Director Actor-Set Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `rhino_director_build_actor_set_from_source_occurrence_v2`, a capture-first Director tool that turns one captured block source occurrence into a durable schema-v2 `director_actor_set`.

**Architecture:** The new capability lives in `mcp_server/src/rook/director_actor_metadata.py` beside the existing capture/write/read v2 functions. It loads an existing `director_selection_snapshot`, validates live source occurrence drift, enumerates `/block/objects-detailed`, builds a semantic actor-set payload, then delegates persistence to `write_actor_metadata_bundle_v2`. MCP exposure is a second layer; targeting/profile classification is a third layer; the live gate proves the full Pearson authoring flow.

**Tech Stack:** Python async MCP server, pytest, mocked native calls, existing Rook/Rhino native HTTP routes, no native or C# changes.

## Global Constraints

- Worktree: `C:/Users/aryan/source/repos/Rook/.claude/worktrees/director-actor-set-builder`
- Branch: `feature/director-actor-set-builder`
- Binding spec: `docs/superpowers/specs/2026-07-07-director-build-actor-set-from-source-occurrence-design.md`
- Python-only implementation; do not edit `src/RookNative/**` or `src/Rook/**`.
- The builder is capture-first: it consumes `source_occurrence_snapshot_ref`; it does not inspect active selection or call `/select`.
- Durable member identity is only `resolved_reference.definition_object_id`.
- Authoring grouping join is only `ordinal`, set to `/block/objects-detailed` def-table `index`; do not renumber to contiguous array position.
- Do not emit `actor_member_id`, `definition_object_index`, `current_reference`, or `observed_selection` in authoring members.
- `/block/objects-detailed` native semantics are authoritative: it skips `!obj || !obj->Geometry()`, emits raw def-table `index`, and labels `bboxMethod`; admit only `tight_object`.
- Existing error codes must pass through for existing infrastructure failures: `document_path_required`, `metadata_ref_not_found`, `metadata_kind_mismatch`.
- New typed codes: `snapshot_not_single_source`, `snapshot_source_mismatch`, `snapshot_source_not_block`, `source_occurrence_missing_in_document`, `block_definition_drift`, `block_enumeration_empty`, `tight_bbox_unavailable`, `actor_set_exists`, `actor_set_source_mismatch`.
- Full MCP surface count moves `442 -> 443`; readonly stays `149`; lean stays `22`.
- Run commands from `mcp_server/` unless a task says otherwise.
- One commit per task. Stop after each task and report changed files, tests, and deviations.

---

## File Structure

- `mcp_server/src/rook/director_actor_metadata.py`
  - Add the builder function and small private helpers.
  - Reuse existing `_call_native_data`, `load_metadata_ref`, `resolve_active_project_root`, `_actor_set_ref`, `resolve_metadata_ref`, `_validate_filename_segment_id`, and `write_actor_metadata_bundle_v2`.
- `mcp_server/tests/test_director_actor_metadata.py`
  - Add all core builder unit tests using a new fake native that can read/write `.rook` files and emulate `/block/instances`, `/block/info`, `/block/objects-detailed`.
- `mcp_server/src/rook/server.py`
  - Add MCP tool schema and dispatch case.
- `mcp_server/tests/test_director_mcp_tools.py`
  - Add registration, group, dispatch success, and dispatch error coverage.
- `mcp_server/src/rook/agent/tool_groups.py`
  - Add the tool to the `director` group only.
- `mcp_server/src/rook/targeting.py`
  - Add to `_ALL_KNOWN_TOOLS`. Do not add to read sets; default routed mutate policy must apply.
- `mcp_server/src/rook/mcp_tool_profiles.py`
  - No source change expected unless the sweep shows a profile-specific set needs an explicit assertion. The new tool must not enter `PUBLIC_READONLY_TOOL_NAMES` or `PUBLIC_LEAN_TOOL_NAMES`.
- `mcp_server/tests/test_multi_instance_targeting.py`
  - Assert routed mutating policy.
- `mcp_server/tests/test_server_tool_profiles.py`
  - Pin full/_all_live counts to `443`; keep readonly `149`, lean `22`.
- `mcp_server/tests/test_mcp_tool_profiles.py`
  - Add negative membership assertion for readonly/lean if the implementation touches profile sets.
- `mcp_server/tests/test_director_actor_set_builder_live.py`
  - Add env-gated live proof file; skip cleanly by default.

---

### Task 1: Core Builder Function + Unit Tests

**Files:**
- Modify: `mcp_server/src/rook/director_actor_metadata.py`
- Modify: `mcp_server/tests/test_director_actor_metadata.py`

**Interfaces:**
- Produces: `async def build_actor_set_from_source_occurrence_v2(arguments: dict[str, Any], *, call_native=call_rhino, port=None) -> dict[str, Any]`
- Consumes: `source_occurrence_snapshot_ref`, optional `actor_set_id`, optional `replace_existing`
- Produces persisted actor-set file through `write_actor_metadata_bundle_v2`

- [ ] **Step 1: Add failing tests for the happy path and schema shape**

Append these helpers and tests near the existing actor metadata v2 tests in `mcp_server/tests/test_director_actor_metadata.py`. Keep the existing `FakeDocumentNative` and `_error_code` helpers; do not modify existing tests.

```python
SOURCE_ID = "a28cbdb5-51fa-46b2-b18b-ab880b54ded7"
BLOCK_ID = "2a38c499-7763-4532-a5ff-d71b90d9d95c"
BLOCK_NAME = "3D_BLOCK_ARCH_ROOF_0502 UPLIFT ROOF - VERTICAL"
SNAPSHOT_REF = ".rook/director_planning/selection_snapshots/source_occurrence_roof.json"


def _source_occurrence(*, object_type="InstanceReference", block_id=BLOCK_ID, block_name=BLOCK_NAME):
    return {
        "source_top_level_object_id": SOURCE_ID,
        "object_type": object_type,
        "layer": "004_DIAGRAM::STRUCTURE",
        "name": "",
        "block_definition": {
            "id": block_id,
            "index": 3,
            "name": block_name,
            "block_type": "Embedded",
            "is_linked": False,
            "instance_count": 1,
            "direct_object_count": 3,
        },
        "instance": {"id": SOURCE_ID, "layer": "004_DIAGRAM::STRUCTURE", "name": ""},
    }


def _selection_snapshot(**overrides):
    occ = overrides.pop("occurrence", _source_occurrence())
    payload = {
        "schema_version": 2,
        "metadata_kind": metadata.KIND_SELECTION_SNAPSHOT,
        "snapshot_id": "source_occurrence_roof",
        "source_occurrences": [copy.deepcopy(occ)],
        "source_occurrence": copy.deepcopy(occ),
        "summary": {"selected_count": 1, "source_top_level_object_count": 1},
    }
    payload.update(overrides)
    return payload


def _write_snapshot(project_root: Path, payload: dict | None = None, ref: str = SNAPSHOT_REF) -> None:
    path = metadata.resolve_metadata_ref(project_root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload or _selection_snapshot(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


class FakeActorSetBuilderNative:
    def __init__(
        self,
        model_path: Path,
        *,
        instances=None,
        block_info=None,
        objects=None,
        document_path: str | None = "USE_MODEL",
    ):
        self.model_path = model_path
        self.document_path = str(model_path) if document_path == "USE_MODEL" else document_path
        self.instances = instances if instances is not None else [
            {"id": SOURCE_ID, "definitionId": BLOCK_ID, "definitionName": BLOCK_NAME, "layer": "004_DIAGRAM::STRUCTURE", "name": ""}
        ]
        self.block_info = block_info if block_info is not None else {"id": BLOCK_ID, "name": BLOCK_NAME, "index": 3, "objectCount": 3}
        self.objects = objects if objects is not None else [
            {
                "index": 0,
                "id": "11111111-1111-1111-1111-111111111111",
                "type": "Brep",
                "layer": "001_MATERIAL::001_01_GARDEN WOOD",
                "name": "",
                "bboxMethod": "tight_object",
                "bbox": {"min": [0.0, 0.0, 0.0], "max": [10.123456, 2.0, 3.0]},
            },
            {
                "index": 2,
                "id": "22222222-2222-2222-2222-222222222222",
                "type": "InstanceReference",
                "layer": "002_BLOCKS::002_01_BLOCK_ARCH_GARDEN ROOF",
                "name": "nested-ref",
                "bboxMethod": "tight_object",
                "bbox": {"min": [5.0, 6.0, 7.0], "max": [8.0, 9.0, 10.0]},
            },
        ]
        self.calls = []

    async def __call__(self, endpoint: str, method: str = "GET", data: dict | None = None, port: int | None = None) -> dict:
        self.calls.append((endpoint, method, copy.deepcopy(data), port))
        if endpoint == "/document":
            return {"success": True, "data": {"name": self.model_path.name, "path": self.document_path}}
        if endpoint == "/block/instances":
            assert method == "POST"
            assert data == {"name": BLOCK_NAME, "depth": 0}
            return {"success": True, "data": {"blockName": BLOCK_NAME, "instances": copy.deepcopy(self.instances)}}
        if endpoint == "/block/info":
            assert method == "POST"
            assert data == {"name": BLOCK_NAME}
            return {"success": True, "data": copy.deepcopy(self.block_info)}
        if endpoint == "/block/objects-detailed":
            assert method == "POST"
            assert data == {"name": BLOCK_NAME}
            return {"success": True, "data": {"name": BLOCK_NAME, "objects": copy.deepcopy(self.objects)}}
        raise AssertionError(f"unexpected endpoint {endpoint}")


def _build_actor_set(project_root: Path, *, native=None, args=None):
    model = project_root / "scene.3dm"
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"fake 3dm")
    _write_snapshot(project_root)
    return asyncio.run(
        metadata.build_actor_set_from_source_occurrence_v2(
            args or {"source_occurrence_snapshot_ref": SNAPSHOT_REF},
            call_native=native or FakeActorSetBuilderNative(model),
            port=None,
        )
    )


def test_build_actor_set_from_source_occurrence_v2_happy_path(tmp_path):
    result = _build_actor_set(tmp_path)

    assert result["schema_version"] == 2
    assert result["metadata_kind"] == metadata.KIND_ACTOR_SET
    assert result["actor_set_id"] == "source_occurrence_roof"
    assert result["member_count"] == 2
    actor_set = json.loads(Path(result["resolved_actor_set_path"]).read_text(encoding="utf-8"))
    assert actor_set["source_occurrence_snapshot_ref"] == SNAPSHOT_REF
    assert actor_set["summary"] == {"member_count": 2, "resolved_count": 2}
    assert [m["ordinal"] for m in actor_set["members"]] == [0, 2]
    first = actor_set["members"][0]
    assert first["resolved_reference"]["definition_object_id"] == "11111111-1111-1111-1111-111111111111"
    assert first["expected"] == {"type": "Brep", "layer": "001_MATERIAL::001_01_GARDEN WOOD", "name": ""}
    assert first["bbox_evidence"] == {
        "bbox_method": "tight_object",
        "bbox_space": "definition_object",
        "min": [0.0, 0.0, 0.0],
        "max": [10.1235, 2.0, 3.0],
        "rounding_policy": "round_to_4_decimal_places",
        "validation_strength": "tight_bbox",
    }


def test_build_actor_set_authoring_member_schema_omits_false_identity_fields(tmp_path):
    result = _build_actor_set(tmp_path)
    actor_set = json.loads(Path(result["resolved_actor_set_path"]).read_text(encoding="utf-8"))
    member = actor_set["members"][0]

    assert "actor_member_id" not in member
    assert "definition_object_index" not in member
    assert "current_reference" not in member
    assert "observed_selection" not in member
```

- [ ] **Step 2: Run the focused happy-path tests and verify RED**

Run:

```bash
python -m pytest tests/test_director_actor_metadata.py::test_build_actor_set_from_source_occurrence_v2_happy_path tests/test_director_actor_metadata.py::test_build_actor_set_authoring_member_schema_omits_false_identity_fields -q
```

Expected: FAIL with `AttributeError: module 'rook.director_actor_metadata' has no attribute 'build_actor_set_from_source_occurrence_v2'`.

- [ ] **Step 3: Add the builder implementation**

Add this implementation to `mcp_server/src/rook/director_actor_metadata.py` after `capture_source_occurrence_v2` and before `_remember_unique_id`.

```python
def _snapshot_source_occurrence(snapshot: dict[str, Any]) -> dict[str, Any]:
    occurrences = snapshot.get("source_occurrences")
    if not isinstance(occurrences, list) or len(occurrences) != 1:
        _raise(
            "snapshot_not_single_source",
            "Source occurrence snapshot must contain exactly one source occurrence.",
            count=len(occurrences) if isinstance(occurrences, list) else None,
        )
    source = occurrences[0]
    if not isinstance(source, dict):
        _raise(
            "snapshot_not_single_source",
            "Source occurrence snapshot entry must be an object.",
        )
    convenience = snapshot.get("source_occurrence")
    if convenience is not None and convenience != source:
        _raise(
            "snapshot_source_mismatch",
            "source_occurrence convenience field must match source_occurrences[0].",
        )
    return source


def _block_definition_from_source(source: dict[str, Any]) -> dict[str, Any]:
    block_definition = source.get("block_definition")
    if not isinstance(block_definition, dict):
        _raise(
            "snapshot_source_not_block",
            "Source occurrence does not contain block_definition context.",
        )
    block_id = block_definition.get("id")
    block_name = block_definition.get("name")
    if not isinstance(block_id, str) or not block_id or not isinstance(block_name, str) or not block_name:
        _raise(
            "snapshot_source_not_block",
            "Source occurrence block_definition requires id and name.",
        )
    return block_definition


def _round_bbox_values(values: Any) -> list[float]:
    if not isinstance(values, list) or len(values) != 3:
        _raise("tight_bbox_unavailable", "Tight bbox min/max must be 3-number arrays.")
    return [round(float(value), 4) for value in values]


def _member_from_block_object(obj: dict[str, Any]) -> dict[str, Any]:
    if obj.get("bboxMethod") != "tight_object":
        _raise(
            "tight_bbox_unavailable",
            "Actor-set builder requires tight_object bbox for every member.",
            object_id=obj.get("id"),
            bbox_method=obj.get("bboxMethod"),
        )
    bbox = obj.get("bbox") if isinstance(obj.get("bbox"), dict) else {}
    return {
        "ordinal": obj.get("index"),
        "resolved_reference": {
            "definition_object_id": obj.get("id"),
        },
        "expected": {
            "type": obj.get("type"),
            "layer": obj.get("layer"),
            "name": obj.get("name") or "",
        },
        "bbox_evidence": {
            "bbox_method": "tight_object",
            "bbox_space": "definition_object",
            "min": _round_bbox_values(bbox.get("min")),
            "max": _round_bbox_values(bbox.get("max")),
            "rounding_policy": "round_to_4_decimal_places",
            "validation_strength": "tight_bbox",
        },
    }


def _same_source_snapshot(existing: dict[str, Any], source_ref: str) -> bool:
    return existing.get("source_occurrence_snapshot_ref") == source_ref


async def build_actor_set_from_source_occurrence_v2(
    arguments: dict[str, Any], *, call_native=call_rhino, port=None
) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        _raise("metadata_bundle_invalid", "Actor-set build arguments must be an object.")
    _reject_legacy_path_fields(arguments)
    _reject_generated_ref_input_fields(
        arguments,
        allowed_field_paths={"$.source_occurrence_snapshot_ref"},
    )
    _validate_ref_fields(arguments)

    project_root, _source_document = await resolve_active_project_root(
        call_native=call_native,
        port=port,
    )

    source_ref = arguments.get("source_occurrence_snapshot_ref")
    snapshot = load_metadata_ref(
        project_root,
        source_ref,
        expected_kind=KIND_SELECTION_SNAPSHOT,
    )
    source = _snapshot_source_occurrence(snapshot)
    if source.get("object_type") != "InstanceReference":
        _raise(
            "snapshot_source_not_block",
            "Source occurrence must be a block InstanceReference.",
            object_type=source.get("object_type"),
        )
    block_definition = _block_definition_from_source(source)
    block_name = block_definition["name"]
    block_id = block_definition["id"]
    source_object_id = source.get("source_top_level_object_id")
    if not isinstance(source_object_id, str) or not source_object_id:
        _raise(
            "snapshot_source_not_block",
            "Source occurrence requires source_top_level_object_id.",
        )

    actor_set_id = arguments.get("actor_set_id")
    if actor_set_id is None:
        actor_set_id = snapshot.get("snapshot_id")
    if not isinstance(actor_set_id, str) or not actor_set_id:
        _raise(
            "metadata_id_required",
            "Actor-set builder requires actor_set_id or snapshot_id.",
            field="actor_set_id",
        )
    _validate_filename_segment_id(
        actor_set_id,
        key="actor_set_id",
        field_path="$.actor_set_id",
    )
    replace_existing = bool(arguments.get("replace_existing", False))
    actor_ref = _actor_set_ref(actor_set_id)
    actor_path = resolve_metadata_ref(project_root, actor_ref)
    if actor_path.exists():
        existing = load_metadata_ref(project_root, actor_ref, expected_kind=KIND_ACTOR_SET)
        if not replace_existing:
            _raise(
                "actor_set_exists",
                "Actor set already exists; pass replace_existing=true to overwrite.",
                actor_set_ref=actor_ref,
            )
        if not _same_source_snapshot(existing, source_ref):
            _raise(
                "actor_set_source_mismatch",
                "Existing actor set was built from a different source occurrence snapshot.",
                actor_set_ref=actor_ref,
                existing_source_occurrence_snapshot_ref=existing.get("source_occurrence_snapshot_ref"),
                source_occurrence_snapshot_ref=source_ref,
            )

    instances = await _call_native_data(
        "/block/instances",
        "POST",
        {"name": block_name, "depth": 0},
        call_native=call_native,
        port=port,
    )
    instance_rows = instances.get("instances") if isinstance(instances, dict) else None
    if not isinstance(instance_rows, list) or not any(
        isinstance(row, dict) and row.get("id") == source_object_id for row in instance_rows
    ):
        _raise(
            "source_occurrence_missing_in_document",
            "Captured source occurrence is not present in the active document.",
            source_top_level_object_id=source_object_id,
            block_name=block_name,
        )

    block_info = await _call_native_data(
        "/block/info",
        "POST",
        {"name": block_name},
        call_native=call_native,
        port=port,
    )
    if not isinstance(block_info, dict) or block_info.get("id") != block_id or block_info.get("name") != block_name:
        _raise(
            "block_definition_drift",
            "Current block definition id/name does not match the captured source occurrence.",
            expected_block_definition={"id": block_id, "name": block_name},
            actual_block_definition={
                "id": block_info.get("id") if isinstance(block_info, dict) else None,
                "name": block_info.get("name") if isinstance(block_info, dict) else None,
            },
        )

    detail = await _call_native_data(
        "/block/objects-detailed",
        "POST",
        {"name": block_name},
        call_native=call_native,
        port=port,
    )
    objects = detail.get("objects") if isinstance(detail, dict) else None
    if not isinstance(objects, list) or not objects:
        _raise(
            "block_enumeration_empty",
            "Block definition has no direct geometry objects to build as actor members.",
            block_name=block_name,
        )
    members = []
    for obj in objects:
        if not isinstance(obj, dict):
            _raise("block_enumeration_empty", "Block object entry was not an object.")
        members.append(_member_from_block_object(obj))

    actor_set = {
        "actor_set_id": actor_set_id,
        "source_occurrence_snapshot_ref": source_ref,
        "summary": {"member_count": len(members), "resolved_count": len(members)},
        "members": members,
    }
    result = await write_actor_metadata_bundle_v2(
        {"actor_set": actor_set},
        call_native=call_native,
        port=port,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "metadata_kind": KIND_ACTOR_SET,
        "actor_set_id": actor_set_id,
        "actor_set_ref": result["actor_set_ref"],
        "resolved_actor_set_path": result["resolved_actor_set_path"],
        "member_count": len(members),
    }
```

- [ ] **Step 4: Run the happy-path tests and verify GREEN**

Run:

```bash
python -m pytest tests/test_director_actor_metadata.py::test_build_actor_set_from_source_occurrence_v2_happy_path tests/test_director_actor_metadata.py::test_build_actor_set_authoring_member_schema_omits_false_identity_fields -q
```

Expected: `2 passed`.

- [ ] **Step 5: Add the remaining core error tests**

Append these tests to `mcp_server/tests/test_director_actor_metadata.py`.

```python
def test_build_actor_set_rejects_non_block_snapshot(tmp_path):
    model = tmp_path / "scene.3dm"
    _write_snapshot(tmp_path, _selection_snapshot(occurrence=_source_occurrence(object_type="Brep")))
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        asyncio.run(metadata.build_actor_set_from_source_occurrence_v2(
            {"source_occurrence_snapshot_ref": SNAPSHOT_REF},
            call_native=FakeActorSetBuilderNative(model),
        ))
    assert _error_code(exc) == "snapshot_source_not_block"


def test_build_actor_set_rejects_multi_source_snapshot(tmp_path):
    first = _source_occurrence()
    second = _source_occurrence()
    second["source_top_level_object_id"] = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    snap = _selection_snapshot()
    snap["source_occurrences"] = [first, second]
    snap.pop("source_occurrence", None)
    model = tmp_path / "scene.3dm"
    _write_snapshot(tmp_path, snap)
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        asyncio.run(metadata.build_actor_set_from_source_occurrence_v2(
            {"source_occurrence_snapshot_ref": SNAPSHOT_REF},
            call_native=FakeActorSetBuilderNative(model),
        ))
    assert _error_code(exc) == "snapshot_not_single_source"


def test_build_actor_set_rejects_source_occurrence_convenience_mismatch(tmp_path):
    snap = _selection_snapshot()
    snap["source_occurrence"] = _source_occurrence(block_name="Different Block")
    model = tmp_path / "scene.3dm"
    _write_snapshot(tmp_path, snap)
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        asyncio.run(metadata.build_actor_set_from_source_occurrence_v2(
            {"source_occurrence_snapshot_ref": SNAPSHOT_REF},
            call_native=FakeActorSetBuilderNative(model),
        ))
    assert _error_code(exc) == "snapshot_source_mismatch"


def test_build_actor_set_rejects_zero_objects(tmp_path):
    model = tmp_path / "scene.3dm"
    _write_snapshot(tmp_path)
    native = FakeActorSetBuilderNative(model, objects=[])
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        asyncio.run(metadata.build_actor_set_from_source_occurrence_v2(
            {"source_occurrence_snapshot_ref": SNAPSHOT_REF},
            call_native=native,
        ))
    assert _error_code(exc) == "block_enumeration_empty"


def test_build_actor_set_rejects_non_tight_bbox(tmp_path):
    model = tmp_path / "scene.3dm"
    bad = [{
        "index": 0, "id": "11111111-1111-1111-1111-111111111111",
        "type": "Brep", "layer": "L", "name": "",
        "bboxMethod": "loose_fallback",
        "bbox": {"min": [0, 0, 0], "max": [1, 1, 1]},
    }]
    _write_snapshot(tmp_path)
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        asyncio.run(metadata.build_actor_set_from_source_occurrence_v2(
            {"source_occurrence_snapshot_ref": SNAPSHOT_REF},
            call_native=FakeActorSetBuilderNative(model, objects=bad),
        ))
    assert _error_code(exc) == "tight_bbox_unavailable"


def test_build_actor_set_existing_ref_fails_without_replace(tmp_path):
    result = _build_actor_set(tmp_path)
    model = tmp_path / "scene.3dm"
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        asyncio.run(metadata.build_actor_set_from_source_occurrence_v2(
            {"source_occurrence_snapshot_ref": SNAPSHOT_REF},
            call_native=FakeActorSetBuilderNative(model),
        ))
    assert result["actor_set_ref"].endswith("source_occurrence_roof.json")
    assert _error_code(exc) == "actor_set_exists"


def test_build_actor_set_replace_existing_same_source_succeeds(tmp_path):
    _build_actor_set(tmp_path)
    model = tmp_path / "scene.3dm"
    result = asyncio.run(metadata.build_actor_set_from_source_occurrence_v2(
        {"source_occurrence_snapshot_ref": SNAPSHOT_REF, "replace_existing": True},
        call_native=FakeActorSetBuilderNative(model),
    ))
    assert result["member_count"] == 2


def test_build_actor_set_replace_existing_different_source_fails(tmp_path):
    _build_actor_set(tmp_path)
    model = tmp_path / "scene.3dm"
    other_ref = ".rook/director_planning/selection_snapshots/other_source.json"
    _write_snapshot(tmp_path, _selection_snapshot(snapshot_id="other_source"), ref=other_ref)
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        asyncio.run(metadata.build_actor_set_from_source_occurrence_v2(
            {"source_occurrence_snapshot_ref": other_ref, "replace_existing": True, "actor_set_id": "source_occurrence_roof"},
            call_native=FakeActorSetBuilderNative(model),
        ))
    assert _error_code(exc) == "actor_set_source_mismatch"


def test_build_actor_set_rejects_missing_source_instance(tmp_path):
    model = tmp_path / "scene.3dm"
    _write_snapshot(tmp_path)
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        asyncio.run(metadata.build_actor_set_from_source_occurrence_v2(
            {"source_occurrence_snapshot_ref": SNAPSHOT_REF},
            call_native=FakeActorSetBuilderNative(model, instances=[]),
        ))
    assert _error_code(exc) == "source_occurrence_missing_in_document"


def test_build_actor_set_rejects_block_definition_drift(tmp_path):
    model = tmp_path / "scene.3dm"
    _write_snapshot(tmp_path)
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        asyncio.run(metadata.build_actor_set_from_source_occurrence_v2(
            {"source_occurrence_snapshot_ref": SNAPSHOT_REF},
            call_native=FakeActorSetBuilderNative(model, block_info={"id": "different", "name": BLOCK_NAME}),
        ))
    assert _error_code(exc) == "block_definition_drift"


def test_build_actor_set_reuses_document_path_required_for_unsaved_doc(tmp_path):
    model = tmp_path / "scene.3dm"
    _write_snapshot(tmp_path)
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        asyncio.run(metadata.build_actor_set_from_source_occurrence_v2(
            {"source_occurrence_snapshot_ref": SNAPSHOT_REF},
            call_native=FakeActorSetBuilderNative(model, document_path=None),
        ))
    assert _error_code(exc) == "document_path_required"
```

- [ ] **Step 6: Run Task 1 covering tests**

Run:

```bash
python -m pytest tests/test_director_actor_metadata.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 7: Commit Task 1**

```bash
git add mcp_server/src/rook/director_actor_metadata.py mcp_server/tests/test_director_actor_metadata.py
git commit -m "feat: build Director actor set from source occurrence"
```

**STOP FOR REVIEW.** Report the commit, test output, and any deviations.

---

### Task 2: MCP Tool Definition and Dispatch

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/tests/test_director_mcp_tools.py`

**Interfaces:**
- Consumes: `director_actor_metadata.build_actor_set_from_source_occurrence_v2(arguments, port=port)`
- Produces: MCP tool `rhino_director_build_actor_set_from_source_occurrence_v2`

- [ ] **Step 1: Add failing MCP registration and dispatch tests**

Modify `test_actor_metadata_v2_tools_registered` in `mcp_server/tests/test_director_mcp_tools.py` so it also asserts the new tool exists:

```python
    assert "rhino_director_build_actor_set_from_source_occurrence_v2" in by_name
```

Add it to the `for name in {...}` set in that test. Modify `test_actor_metadata_v2_tools_are_in_director_group` to assert the new tool is in `TOOL_GROUPS["director"]`; this assertion will stay RED until Task 3, so do not run that test in this task's initial RED command.

Append dispatch tests:

```python
@pytest.mark.asyncio
async def test_build_actor_set_from_source_occurrence_v2_tool_dispatch_success():
    request = {
        "source_occurrence_snapshot_ref": ".rook/director_planning/selection_snapshots/source_occurrence_roof.json",
        "actor_set_id": "roof_full_set",
    }

    async def fake_build(arguments, *, port=None):
        assert arguments == request
        assert port is None
        return {
            "schema_version": 2,
            "metadata_kind": "director_actor_set",
            "actor_set_id": "roof_full_set",
            "actor_set_ref": ".rook/director_planning/actor_sets/roof_full_set.json",
            "member_count": 376,
        }

    with patch(
        "rook.server.director_actor_metadata.build_actor_set_from_source_occurrence_v2",
        new=fake_build,
    ):
        out = await server.call_tool(
            "rhino_director_build_actor_set_from_source_occurrence_v2",
            request,
        )

    payload = json.loads(out[0].text)
    assert payload["metadata_kind"] == "director_actor_set"
    assert payload["actor_set_ref"].endswith("roof_full_set.json")
    assert payload["member_count"] == 376


@pytest.mark.asyncio
async def test_build_actor_set_from_source_occurrence_v2_tool_dispatch_error():
    async def fake_build(arguments, *, port=None):
        raise server.director_actor_metadata.DirectorActorMetadataError(
            "actor_set_exists",
            "Actor set already exists.",
        )

    with patch(
        "rook.server.director_actor_metadata.build_actor_set_from_source_occurrence_v2",
        new=fake_build,
    ):
        out = await server.call_tool(
            "rhino_director_build_actor_set_from_source_occurrence_v2",
            {"source_occurrence_snapshot_ref": ".rook/director_planning/selection_snapshots/source_occurrence_roof.json"},
        )

    text = out[0].text
    assert text.startswith("Error: ")
    payload = json.loads(text.removeprefix("Error: "))
    assert payload["code"] == "actor_set_exists"
```

- [ ] **Step 2: Run registration/dispatch tests and verify RED**

Run:

```bash
python -m pytest tests/test_director_mcp_tools.py::test_actor_metadata_v2_tools_registered tests/test_director_mcp_tools.py::test_build_actor_set_from_source_occurrence_v2_tool_dispatch_success tests/test_director_mcp_tools.py::test_build_actor_set_from_source_occurrence_v2_tool_dispatch_error -q
```

Expected: fails because the tool is not registered/dispatchable.

- [ ] **Step 3: Add MCP tool schema**

In `mcp_server/src/rook/server.py`, insert this `Tool(...)` immediately after `rhino_director_capture_source_occurrence_v2` and before `rhino_director_write_actor_metadata_v2`:

```python
        Tool(
            name="rhino_director_build_actor_set_from_source_occurrence_v2",
            description=(
                "Build a schema-v2 Director ActorSet from an existing source "
                "occurrence SelectionSnapshot. Enumerates direct block definition "
                "objects, writes the ActorSet under .rook, and requires a saved "
                ".3dm document. Mutating: writes Director planning metadata."
            ),
            inputSchema={
                "type": "object",
                "required": ["source_occurrence_snapshot_ref"],
                "properties": {
                    "source_occurrence_snapshot_ref": {
                        "type": "string",
                        "description": "Project-relative .rook ref to a director_selection_snapshot captured by rhino_director_capture_source_occurrence_v2.",
                    },
                    "actor_set_id": {
                        "type": "string",
                        "description": "Optional safe id for the generated ActorSet. Defaults to the snapshot_id.",
                    },
                    "replace_existing": {
                        "type": "boolean",
                        "description": "Default false. If true, replaces only an existing ActorSet built from the same source_occurrence_snapshot_ref.",
                    },
                },
            },
        ),
```

- [ ] **Step 4: Add dispatch case**

In `server.py`, insert this `case` immediately after `rhino_director_capture_source_occurrence_v2`:

```python
        case "rhino_director_build_actor_set_from_source_occurrence_v2":
            try:
                result = {
                    "success": True,
                    "data": await director_actor_metadata.build_actor_set_from_source_occurrence_v2(
                        arguments, port=port
                    ),
                }
            except director_actor_metadata.DirectorActorMetadataError as exc:
                result = {"success": False, "data": exc.to_data()}
```

- [ ] **Step 5: Run Task 2 tests**

Run:

```bash
python -m pytest tests/test_director_mcp_tools.py::test_actor_metadata_v2_tools_registered tests/test_director_mcp_tools.py::test_build_actor_set_from_source_occurrence_v2_tool_dispatch_success tests/test_director_mcp_tools.py::test_build_actor_set_from_source_occurrence_v2_tool_dispatch_error -q
```

Expected: registration/dispatch tests pass. `test_actor_metadata_v2_tools_are_in_director_group` may still fail until Task 3.

- [ ] **Step 6: Commit Task 2**

```bash
git add mcp_server/src/rook/server.py mcp_server/tests/test_director_mcp_tools.py
git commit -m "feat: expose Director actor-set builder tool"
```

**STOP FOR REVIEW.** Report the commit and test output.

---

### Task 3: Classification, Profiles, and Tool Groups

**Files:**
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Modify: `mcp_server/tests/test_director_mcp_tools.py`
- Modify: `mcp_server/tests/test_multi_instance_targeting.py`
- Modify: `mcp_server/tests/test_server_tool_profiles.py`
- Modify: `mcp_server/tests/test_mcp_tool_profiles.py` only if needed by the sweep

**Interfaces:**
- Consumes: registered MCP tool from Task 2
- Produces: routed mutating policy, Director group membership, full surface count `443`, no readonly/lean membership

- [ ] **Step 1: Run the required sweep**

Run:

```bash
rg -n "rhino_director_capture_source_occurrence_v2|rhino_director_write_actor_metadata_v2|rhino_director_read_actor_metadata_v2|442|149|22" mcp_server/src/rook mcp_server/tests
```

Record every file that needs a mirrored update. At minimum the sweep must include `server.py`, `agent/tool_groups.py`, `targeting.py`, `test_director_mcp_tools.py`, `test_multi_instance_targeting.py`, `test_server_tool_profiles.py`, and `test_mcp_tool_profiles.py`.

- [ ] **Step 2: Add failing classification assertions**

Modify `test_director_actor_metadata_v2_tool_policies` in `mcp_server/tests/test_multi_instance_targeting.py`:

```python
    assert targeting.policy_for_tool(
        "rhino_director_build_actor_set_from_source_occurrence_v2"
    ) == targeting.RhinoToolPolicy(True, "mutate")
```

Modify `test_actor_metadata_v2_tools_are_in_director_group` in `mcp_server/tests/test_director_mcp_tools.py`:

```python
    assert (
        "rhino_director_build_actor_set_from_source_occurrence_v2"
        in tool_groups.TOOL_GROUPS["director"]
    )
```

Modify `test_readonly_partition_over_live_surface` in `mcp_server/tests/test_server_tool_profiles.py` to include the new mutating tool in the full-but-not-readonly set:

```python
    assert {
        "rhino_director_compile_take",
        "rhino_director_worker_play",
        "rhino_director_capture_take",
        "rhino_director_build_actor_set_from_source_occurrence_v2",
    } <= full
    assert {
        "rhino_director_compile_take",
        "rhino_director_worker_play",
        "rhino_director_capture_take",
        "rhino_director_build_actor_set_from_source_occurrence_v2",
    }.isdisjoint(ro)
```

In `mcp_server/tests/test_mcp_tool_profiles.py`, add:

```python
def test_director_actor_set_builder_not_public_readonly_or_lean():
    tool = "rhino_director_build_actor_set_from_source_occurrence_v2"
    assert tool not in PUBLIC_READONLY_TOOL_NAMES
    assert tool not in PUBLIC_LEAN_TOOL_NAMES
```

- [ ] **Step 3: Run classification tests and verify RED**

Run:

```bash
python -m pytest tests/test_director_mcp_tools.py::test_actor_metadata_v2_tools_are_in_director_group tests/test_multi_instance_targeting.py::test_director_actor_metadata_v2_tool_policies tests/test_server_tool_profiles.py::test_full_surface_is_442_and_gates_deprecated tests/test_server_tool_profiles.py::test_all_live_tools_is_unprofiled_442 tests/test_server_tool_profiles.py::test_readonly_partition_over_live_surface tests/test_mcp_tool_profiles.py::test_director_actor_set_builder_not_public_readonly_or_lean -q
```

Expected: failures for missing group/policy and old `442` names/counts.

- [ ] **Step 4: Update source classification files**

In `mcp_server/src/rook/agent/tool_groups.py`, add `"rhino_director_build_actor_set_from_source_occurrence_v2"` to `TOOL_GROUPS["director"]` near the v2 actor metadata tools. Do not add it to `director_readonly`.

In `mcp_server/src/rook/targeting.py`, add `"rhino_director_build_actor_set_from_source_occurrence_v2"` to `_ALL_KNOWN_TOOLS` near `rhino_director_capture_source_occurrence_v2`. Do not add it to `_RHINO_READ_TOOLS` or any independent read set; the default `_RHINO_MUTATE_TOOLS` computation must classify it as `RhinoToolPolicy(True, "mutate")`.

Do not add the tool to `PUBLIC_READONLY_TOOL_NAMES` or `PUBLIC_LEAN_TOOL_NAMES` in `mcp_tool_profiles.py`.

- [ ] **Step 5: Update full-surface count tests**

In `mcp_server/tests/test_server_tool_profiles.py`:

- Rename `test_full_surface_is_442_and_gates_deprecated` to `test_full_surface_is_443_and_gates_deprecated`.
- Rename `test_all_live_tools_is_unprofiled_442` to `test_all_live_tools_is_unprofiled_443`.
- Change `442` assertions and comments to `443`.
- Keep readonly count `149` and lean count `22`.
- In `test_readonly_partition_over_live_surface`, change `len(full) == 442` to `len(full) == 443`.

- [ ] **Step 6: Run Task 3 covering tests**

Run:

```bash
python -m pytest tests/test_director_mcp_tools.py tests/test_multi_instance_targeting.py tests/test_server_tool_profiles.py tests/test_mcp_tool_profiles.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/targeting.py mcp_server/tests/test_director_mcp_tools.py mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_server_tool_profiles.py mcp_server/tests/test_mcp_tool_profiles.py
git commit -m "test: classify Director actor-set builder"
```

**STOP FOR REVIEW.** Report sweep results, commit, and test output.

---

### Task 4: Live Gate File for Pearson Actor-Set Builder

**Files:**
- Create: `mcp_server/tests/test_director_actor_set_builder_live.py`

**Interfaces:**
- Consumes: MCP tools `rhino_director_capture_source_occurrence_v2`, `rhino_director_build_actor_set_from_source_occurrence_v2`, `rhino_director_read_actor_metadata_v2`
- Produces: env-gated live proof that a fresh capture can build a full roof actor set and that emitted authoring members have clean identity fields

- [ ] **Step 1: Add the skipped-by-default live test**

Create `mcp_server/tests/test_director_actor_set_builder_live.py`:

```python
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from rook import server


pytestmark = pytest.mark.live

SOURCE_ID = "a28cbdb5-51fa-46b2-b18b-ab880b54ded7"
EXISTING_ROOF_ACTOR_SET_REF = ".rook/director_planning/actor_sets/roof_uplift_vertical_test_chunk_001.json"


def _live_enabled() -> bool:
    return os.environ.get("ROOK_DIRECTOR_ACTOR_SET_BUILDER_LIVE") == "1"


async def _call_tool(name: str, arguments: dict) -> dict:
    result = await server.call_tool(name, arguments)
    text = result[0].text
    if text.startswith("Error: "):
        raise AssertionError(text)
    return json.loads(text)


def _member_identity(member: dict) -> tuple[int, str]:
    return (
        member["ordinal"],
        member["resolved_reference"]["definition_object_id"],
    )


@pytest.mark.asyncio
async def test_live_build_actor_set_from_fresh_source_occurrence():
    if not _live_enabled():
        pytest.skip("Set ROOK_DIRECTOR_ACTOR_SET_BUILDER_LIVE=1 with Pearson open to run.")

    suffix = uuid.uuid4().hex[:8]
    snapshot_id = f"source_occurrence_roof_builder_live_{suffix}"
    actor_set_id = f"roof_builder_live_{suffix}"

    capture = await _call_tool(
        "rhino_director_capture_source_occurrence_v2",
        {
            "snapshot_id": snapshot_id,
            "ids": [SOURCE_ID],
            "intent": "live_actor_set_builder_gate",
            "label": "Live actor-set builder gate",
        },
    )
    built = await _call_tool(
        "rhino_director_build_actor_set_from_source_occurrence_v2",
        {
            "source_occurrence_snapshot_ref": capture["snapshot_ref"],
            "actor_set_id": actor_set_id,
        },
    )
    loaded = await _call_tool(
        "rhino_director_read_actor_metadata_v2",
        {"ref": built["actor_set_ref"], "expected_kind": "director_actor_set"},
    )
    payload = loaded["payload"]
    assert payload["schema_version"] == 2
    assert payload["metadata_kind"] == "director_actor_set"
    assert payload["actor_set_id"] == actor_set_id
    assert payload["source_occurrence_snapshot_ref"] == capture["snapshot_ref"]
    assert payload["summary"]["member_count"] == payload["summary"]["resolved_count"] == built["member_count"]
    assert built["member_count"] > 0

    ordinals = [m["ordinal"] for m in payload["members"]]
    assert ordinals == sorted(ordinals)
    assert len(ordinals) == len(set(ordinals))
    for member in payload["members"]:
        assert "actor_member_id" not in member
        assert "definition_object_index" not in member
        assert "current_reference" not in member
        assert "observed_selection" not in member
        assert member["resolved_reference"]["definition_object_id"]
        assert member["bbox_evidence"]["bbox_method"] == "tight_object"

    try:
        existing = await _call_tool(
            "rhino_director_read_actor_metadata_v2",
            {"ref": EXISTING_ROOF_ACTOR_SET_REF, "expected_kind": "director_actor_set"},
        )
    except AssertionError:
        print("Existing hand-authored roof actor set not found; skipped oracle diff.")
        return

    existing_members = existing["payload"].get("members") or []
    existing_pairs = {
        _member_identity(m)
        for m in existing_members
        if isinstance(m, dict)
        and isinstance(m.get("ordinal"), int)
        and isinstance(m.get("resolved_reference"), dict)
        and m["resolved_reference"].get("definition_object_id")
    }
    built_pairs = {_member_identity(m) for m in payload["members"]}
    if existing_pairs:
        assert built_pairs == existing_pairs
```

- [ ] **Step 2: Run skip-only verification**

Run:

```bash
python -m pytest tests/test_director_actor_set_builder_live.py -q
```

Expected: one skipped test, no collection errors.

- [ ] **Step 3: Commit Task 4**

```bash
git add mcp_server/tests/test_director_actor_set_builder_live.py
git commit -m "test: add Director actor-set builder live gate"
```

**STOP FOR REVIEW.** Do not deploy or launch Rhino. The live gate runs later with the human controlling Rhino.

---

## Final Verification Before PR

After Tasks 1-4 are reviewed and approved, run:

```bash
python -m pytest tests/test_director_actor_metadata.py tests/test_director_mcp_tools.py tests/test_multi_instance_targeting.py tests/test_server_tool_profiles.py tests/test_mcp_tool_profiles.py tests/test_director_actor_set_builder_live.py -q
```

Expected: all non-live tests pass and the live test skips unless `ROOK_DIRECTOR_ACTOR_SET_BUILDER_LIVE=1`.

Then run:

```bash
git status --short --branch
```

Expected: clean branch with all task commits.

## Live Gate Handoff

When the implementation branch is otherwise ready:

1. User opens Pearson model in Rhino.
2. Verify Rook MCP can reach Rhino (`rhino_ping` or the existing live route pattern).
3. Run:

```bash
set ROOK_DIRECTOR_ACTOR_SET_BUILDER_LIVE=1
python -m pytest tests/test_director_actor_set_builder_live.py -q -s
```

The live gate writes a new `.rook/director_planning/selection_snapshots/source_occurrence_roof_builder_live_*.json` and a new `.rook/director_planning/actor_sets/roof_builder_live_*.json` in the project. These are expected proof artifacts; if cleanup is required, remove only the generated live-gate refs by suffix.

## Plan Self-Review Notes

- Spec §4 tool contract is covered by Task 1 implementation/tests and Task 2 MCP schema.
- Spec §5 identity model is covered by Task 1 schema omission test and Task 4 live assertions.
- Spec §7 overwrite semantics are covered by Task 1 replace tests.
- Spec §8 native full-set semantics are covered by Task 1 gapped ordinal happy path and tight-bbox failure.
- Spec §10 error taxonomy is covered by Task 1 tests and existing pass-through behavior.
- Spec §11 exposure/classification is covered by Tasks 2-3.
- No native/C# files are touched.
