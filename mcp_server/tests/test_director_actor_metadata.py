from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest

from rook import director_actor_metadata as metadata


class FakeDocumentNative:
    def __init__(self, path: str | None, *, envelope: bool = False):
        self.path = path
        self.envelope = envelope
        self.calls = []

    async def __call__(
        self,
        endpoint: str,
        method: str = "GET",
        data: dict | None = None,
        port: int | None = None,
    ) -> dict:
        self.calls.append((endpoint, method, data, port))
        assert endpoint == "/document"
        document = {
            "success": True,
            "name": Path(self.path).name if self.path else "Unsaved.3dm",
            "path": self.path,
        }
        if self.envelope:
            return {"success": True, "data": document}
        return document


class FakeCaptureNative:
    def __init__(self, model_path: Path):
        self.model_path = model_path
        self.calls = []

    async def __call__(
        self,
        endpoint: str,
        method: str = "GET",
        data: dict | None = None,
        port: int | None = None,
    ) -> dict:
        self.calls.append((endpoint, method, data, port))
        if endpoint == "/document":
            return {
                "success": True,
                "data": {
                    "name": self.model_path.name,
                    "path": str(self.model_path),
                    "units": "millimeters",
                    "tolerance": 1.0,
                    "angleTolerance": 0.1,
                },
            }
        if endpoint == "/select":
            assert method == "POST"
            return {"success": True, "data": {"selectedCount": len(data["ids"])}}
        if endpoint == "/selection":
            return {
                "success": True,
                "data": {
                    "count": 1,
                    "subObjectCount": 0,
                    "objects": [
                        {
                            "id": "a28cbdb5-51fa-46b2-b18b-ab880b54ded7",
                            "type": "InstanceReference",
                            "layer": "004_DIAGRAM::STRUCTURE",
                            "name": None,
                            "visible": True,
                            "bbox": {"min": [1, 2, 3], "max": [4, 5, 6]},
                            "blockDefinitionId": (
                                "2a38c499-7763-4532-a5ff-d71b90d9d95c"
                            ),
                            "blockName": (
                                "3D_BLOCK_ARCH_ROOF_0502 UPLIFT ROOF - VERTICAL"
                            ),
                        }
                    ],
                },
            }
        if endpoint == "/block/info":
            assert method == "POST"
            assert data == {"name": "3D_BLOCK_ARCH_ROOF_0502 UPLIFT ROOF - VERTICAL"}
            return {
                "success": True,
                "data": {
                    "id": "2a38c499-7763-4532-a5ff-d71b90d9d95c",
                    "index": 3,
                    "name": "3D_BLOCK_ARCH_ROOF_0502 UPLIFT ROOF - VERTICAL",
                    "blockType": "Embedded",
                    "isLinked": False,
                    "instanceCount": 1,
                    "objectCount": 3,
                },
            }
        if endpoint == "/block/instances":
            assert method == "POST"
            return {
                "success": True,
                "data": {
                    "blockName": data["name"],
                    "depth": data["depth"],
                    "instanceCount": 1,
                    "instances": [
                        {
                            "id": "a28cbdb5-51fa-46b2-b18b-ab880b54ded7",
                            "layer": "004_DIAGRAM::STRUCTURE",
                            "name": "",
                            "insertionPoint": [0.0, 0.0, 0.0],
                            "point": [0.0, 0.0, 0.0],
                            "scale": [1.0, 1.0, 1.0],
                        }
                    ],
                },
            }
        if endpoint == "/block/objects-detailed":
            assert method == "POST"
            return {
                "success": True,
                "data": {
                    "blockName": data["name"],
                    "objectCount": 3,
                    "bbox": {"min": [1, 2, 3], "max": [4, 5, 6]},
                    "objects": [
                        {
                            "id": "o1",
                            "type": "Brep",
                            "layer": "001_MATERIAL::001_01_GARDEN WOOD",
                            "visible": True,
                            "colorSource": "ColorFromLayer",
                            "materialSource": "MaterialFromLayer",
                        },
                        {
                            "id": "o2",
                            "type": "Curve",
                            "layer": "000_SETOUT LINES::000_SETOUT_PRIMARY",
                            "visible": False,
                            "colorSource": "ColorFromLayer",
                            "materialSource": "MaterialFromLayer",
                        },
                        {
                            "id": "o3",
                            "type": "InstanceReference",
                            "layer": "002_BLOCKS::002_01_BLOCK_ARCH_GARDEN ROOF",
                            "visible": True,
                            "colorSource": "ColorFromLayer",
                            "materialSource": "MaterialFromLayer",
                        },
                    ],
                },
            }
        if endpoint == "/block/nested":
            assert method == "POST"
            return {
                "success": True,
                "data": {
                    "name": "3D_BLOCK_ARCH_ROOF_0502 UPLIFT ROOF - VERTICAL",
                    "objectCount": 3,
                    "children": [
                        {
                            "name": "Nested Roof Panel",
                            "objectCount": 2,
                            "children": [
                                {
                                    "name": "Nested Bracket",
                                    "objectCount": 4,
                                    "children": [],
                                }
                            ],
                        }
                    ],
                },
            }
        raise AssertionError(f"unexpected endpoint {endpoint}")


def _minimal_bundle() -> dict:
    return {
        "actor_set": {
            "actor_set_id": "roof_uplift_vertical_test_chunk_001",
            "source_snapshot_entry_id": "intent_005_20260701_144245",
            "summary": "Roof uplift vertical test chunk.",
            "members": [{"id": "roof_panel_001"}],
        },
        "selection_snapshots": [
            {
                "snapshot_id": "intent_005_20260701_144245",
                "selected": [{"id": "roof_panel_001"}],
            },
            {
                "snapshot_id": "intent_007_20260701_151718",
                "selected": [{"id": "mullion_001"}],
            },
        ],
        "subsets": [
            {
                "subset_id": "same_orientation_mullions_001",
                "parent_actor_set_id": "roof_uplift_vertical_test_chunk_001",
                "acceptance": {
                    "accepted_selection_snapshot_id": "intent_005_20260701_144245",
                    "accepted": True,
                },
                "band_set_ids": ["same_orientation_mullions_001_bands_001"],
                "members": [{"id": "mullion_001"}],
            }
        ],
        "groupings": [
            {
                "band_set_id": "same_orientation_mullions_001_bands_001",
                "parent_actor_set_id": "roof_uplift_vertical_test_chunk_001",
                "parent_subset_id": "same_orientation_mullions_001",
                "exemplar_selection_snapshot_id": "intent_007_20260701_151718",
                "bands": [{"band_id": "vertical", "members": [{"id": "mullion_001"}]}],
            }
        ],
    }


def _error_code(exc: pytest.ExceptionInfo[metadata.DirectorActorMetadataError]) -> str:
    return exc.value.to_data()["code"]


def _write_bundle(bundle: dict, model: Path) -> dict:
    return asyncio.run(
        metadata.write_actor_metadata_bundle_v2(
            bundle,
            call_native=FakeDocumentNative(str(model)),
            port=None,
        )
    )


def _expected_storage_identity(payload: dict) -> dict:
    metadata_kind = payload["metadata_kind"]
    if metadata_kind == metadata.KIND_ACTOR_SET:
        return {
            "kind": metadata.STORAGE_KIND_ACTOR_SET,
            "actor_set_id": payload["actor_set_id"],
        }
    if metadata_kind == metadata.KIND_SELECTION_SNAPSHOT:
        return {
            "kind": metadata.STORAGE_KIND_SELECTION_SNAPSHOT,
            "snapshot_id": payload["snapshot_id"],
        }
    if metadata_kind == metadata.KIND_ACTOR_SUBSET:
        return {
            "kind": metadata.STORAGE_KIND_SUBSET,
            "actor_set_id": payload["parent_actor_set_id"],
            "subset_id": payload["subset_id"],
        }
    if metadata_kind == metadata.KIND_ACTOR_GROUPING:
        return {
            "kind": metadata.STORAGE_KIND_GROUPING,
            "actor_set_id": payload["parent_actor_set_id"],
            "subset_id": payload["parent_subset_id"],
            "band_set_id": payload["band_set_id"],
        }
    raise AssertionError(f"unexpected metadata kind {metadata_kind}")


def _canonical_actor_set_ref(actor_set_id: str) -> str:
    return metadata.canonical_ref_for_storage_identity(
        {
            "kind": metadata.STORAGE_KIND_ACTOR_SET,
            "actor_set_id": actor_set_id,
        }
    )


def _canonical_snapshot_ref(snapshot_id: str) -> str:
    return metadata.canonical_ref_for_storage_identity(
        {
            "kind": metadata.STORAGE_KIND_SELECTION_SNAPSHOT,
            "snapshot_id": snapshot_id,
        }
    )


def _assert_no_rook_files(project_root: Path) -> None:
    rook_dir = project_root / ".rook"
    assert not rook_dir.exists() or not any(rook_dir.rglob("*.json"))


def _assert_no_absolute_or_backslash_refs(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "ref" or key.endswith("_ref"):
                assert isinstance(item, str)
                assert "\\" not in item
                assert not item.startswith("/")
                assert not item.startswith("//")
                assert not (len(item) >= 2 and item[1] == ":")
                assert item.startswith(".rook/")
            _assert_no_absolute_or_backslash_refs(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_absolute_or_backslash_refs(item)


def _walk_strings(value, path="$"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_strings(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def _assert_not_durable_absolute_identity_path(path, value):
    assert not (value.startswith("\\\\") or value.startswith("//")), (path, value)
    assert not (
        len(value) >= 3 and value[1] == ":" and value[2] in ("\\", "/")
    ), (path, value)


def test_validate_metadata_ref_accepts_project_relative_rook_ref():
    ref = ".rook/director_planning/actor_sets/a.json"

    assert metadata.validate_metadata_ref(ref) == ref


@pytest.mark.parametrize(
    "ref",
    [
        "",
        "director_planning/a.json",
        "/.rook/a.json",
        "C:\\project\\.rook\\a.json",
        "\\\\server\\share\\.rook\\a.json",
        ".rook\\a.json",
        ".rook/../a.json",
        ".rook/./a.json",
        ".rook//a.json",
        ".rook/director_planning/actor_sets/a:b.json",
        ".rook/director_planning/actor_sets/a|b.json",
        ".rook/director_planning/actor_sets/CON.json",
        ".rook/director_planning/actor_sets/name .json",
        ".rook/director_planning/actor_sets/name.",
        ".rook/director_planning/actor_sets/control\x1f.json",
    ],
)
def test_validate_metadata_ref_rejects_invalid_refs(ref):
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        metadata.validate_metadata_ref(ref)

    assert _error_code(exc) == "invalid_metadata_ref"


def test_resolve_metadata_ref_resolves_under_project_root(tmp_path):
    project_root = tmp_path / "project"
    ref = ".rook/director_planning/actor_sets/a.json"

    resolved = metadata.resolve_metadata_ref(project_root, ref)

    assert resolved == (
        project_root / ".rook" / "director_planning" / "actor_sets" / "a.json"
    ).resolve()
    resolved.relative_to(project_root.resolve())


def test_ref_from_project_path_converts_project_local_rook_path(tmp_path):
    project_root = tmp_path / "project"
    path = project_root / ".rook" / "director_planning" / "selection_snapshots" / "s.json"

    assert (
        metadata.ref_from_project_path(project_root, path)
        == ".rook/director_planning/selection_snapshots/s.json"
    )


def test_ref_from_project_path_resolves_relative_rook_path_against_project_root(tmp_path):
    project_root = tmp_path / "project"

    assert (
        metadata.ref_from_project_path(
            project_root,
            Path(".rook/director_planning/selection_snapshots/s.json"),
        )
        == ".rook/director_planning/selection_snapshots/s.json"
    )


def test_ref_from_project_path_rejects_path_outside_project_root(tmp_path):
    project_root = tmp_path / "project"

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        metadata.ref_from_project_path(
            project_root,
            tmp_path / "outside" / ".rook" / "a.json",
        )

    assert _error_code(exc) == "path_outside_project_root"


def test_load_metadata_ref_requires_schema_version_2_and_expected_kind(tmp_path):
    project_root = tmp_path / "project"
    path = project_root / ".rook" / "director_planning" / "actor_sets" / "a.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": metadata.SCHEMA_VERSION,
                "metadata_kind": metadata.KIND_ACTOR_SET,
                "actors": [],
            }
        ),
        encoding="utf-8",
    )

    loaded = metadata.load_metadata_ref(
        project_root,
        ".rook/director_planning/actor_sets/a.json",
        expected_kind=metadata.KIND_ACTOR_SET,
    )

    assert loaded["schema_version"] == 2
    assert loaded["metadata_kind"] == metadata.KIND_ACTOR_SET


def test_validate_loaded_metadata_rejects_v1():
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        metadata.validate_loaded_metadata(
            {"schema_version": 1, "metadata_kind": metadata.KIND_ACTOR_SET},
            expected_kind=metadata.KIND_ACTOR_SET,
        )

    assert _error_code(exc) == "metadata_schema_unsupported"


@pytest.mark.parametrize(
    "payload, expected_kind",
    [
        ({"schema_version": 2, "metadata_kind": "typo"}, "typo"),
        ({"schema_version": 2, "metadata_kind": "typo"}, metadata.KIND_ACTOR_SET),
        ({"schema_version": 2, "metadata_kind": metadata.KIND_ACTOR_SET}, "typo"),
    ],
)
def test_validate_loaded_metadata_rejects_unknown_metadata_kinds(payload, expected_kind):
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        metadata.validate_loaded_metadata(payload, expected_kind=expected_kind)

    assert _error_code(exc) == "metadata_kind_mismatch"


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 2, "metadata_kind": metadata.KIND_ACTOR_SUBSET},
        {"schema_version": 2},
    ],
)
def test_validate_loaded_metadata_rejects_wrong_or_missing_metadata_kind(payload):
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        metadata.validate_loaded_metadata(payload, expected_kind=metadata.KIND_ACTOR_SET)

    assert _error_code(exc) == "metadata_kind_mismatch"


def test_validate_loaded_metadata_rejects_legacy_durable_path_fields():
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        metadata.validate_loaded_metadata(
            {
                "schema_version": 2,
                "metadata_kind": metadata.KIND_ACTOR_SET,
                "source_snapshot_path": "C:/project/.rook/source.json",
            },
            expected_kind=metadata.KIND_ACTOR_SET,
        )

    data = exc.value.to_data()
    assert data["code"] == "legacy_path_field_present"
    assert data["field_path"] == "$.source_snapshot_path"


@pytest.mark.parametrize(
    "legacy_value",
    [
        None,
        {"ref": ".rook/director_planning/selection_snapshots/s.json"},
        [".rook/director_planning/selection_snapshots/s.json"],
    ],
)
def test_validate_loaded_metadata_rejects_legacy_durable_path_fields_by_key_presence(
    legacy_value,
):
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        metadata.validate_loaded_metadata(
            {
                "schema_version": 2,
                "metadata_kind": metadata.KIND_ACTOR_SET,
                "source_snapshot_path": legacy_value,
            },
            expected_kind=metadata.KIND_ACTOR_SET,
        )

    data = exc.value.to_data()
    assert data["code"] == "legacy_path_field_present"
    assert data["field_path"] == "$.source_snapshot_path"


@pytest.mark.parametrize(
    "payload, expected_field_path",
    [
        (
            {
                "schema_version": 2,
                "metadata_kind": metadata.KIND_ACTOR_SET,
                "items": [{"model_path": None}],
            },
            "$.items[0].model_path",
        ),
        (
            {
                "schema_version": 2,
                "metadata_kind": metadata.KIND_ACTOR_SET,
                "group": {"exemplar_selection_snapshot_path": 123},
            },
            "$.group.exemplar_selection_snapshot_path",
        ),
    ],
)
def test_validate_loaded_metadata_rejects_nested_legacy_durable_path_fields(
    payload,
    expected_field_path,
):
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        metadata.validate_loaded_metadata(payload, expected_kind=metadata.KIND_ACTOR_SET)

    data = exc.value.to_data()
    assert data["code"] == "legacy_path_field_present"
    assert data["field_path"] == expected_field_path


def test_load_metadata_ref_maps_read_os_error(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    path = project_root / ".rook" / "director_planning" / "actor_sets" / "a.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")

    def fail_read_text(self, *, encoding=None):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        metadata.load_metadata_ref(
            project_root,
            ".rook/director_planning/actor_sets/a.json",
            expected_kind=metadata.KIND_ACTOR_SET,
        )

    assert _error_code(exc) == "metadata_ref_read_failed"


def test_load_metadata_ref_maps_unicode_decode_error(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    path = project_root / ".rook" / "director_planning" / "actor_sets" / "a.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")

    def fail_read_text(self, *, encoding=None):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        metadata.load_metadata_ref(
            project_root,
            ".rook/director_planning/actor_sets/a.json",
            expected_kind=metadata.KIND_ACTOR_SET,
        )

    assert _error_code(exc) == "metadata_text_decode_failed"


def test_write_actor_metadata_bundle_v2_creates_refs_and_no_legacy_paths(tmp_path):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    native = FakeDocumentNative(str(model))

    result = asyncio.run(
        metadata.write_actor_metadata_bundle_v2(
            _minimal_bundle(),
            call_native=native,
            port=None,
        )
    )

    actor_set_ref = _canonical_actor_set_ref("roof_uplift_vertical_test_chunk_001")
    assert result["actor_set_ref"] == actor_set_ref

    actor_set_path = metadata.resolve_metadata_ref(model.parent, actor_set_ref)
    actor_set = json.loads(actor_set_path.read_text(encoding="utf-8"))
    assert actor_set["schema_version"] == 2
    assert actor_set["metadata_kind"] == metadata.KIND_ACTOR_SET
    assert actor_set["source_document"]["file_name"] == model.name
    assert (
        actor_set["source_snapshot_ref"]
        == _canonical_snapshot_ref("intent_005_20260701_144245")
    )
    assert actor_set["actor_set_id"] == "roof_uplift_vertical_test_chunk_001"
    assert actor_set["subsets"][0]["subset_id"] == "same_orientation_mullions_001"
    assert actor_set["subsets"][0]["ref"].startswith(metadata.CANONICAL_REF_PREFIX)
    assert "model_path" not in actor_set
    assert "source_snapshot_path" not in actor_set

    subset_path = metadata.resolve_metadata_ref(
        model.parent,
        actor_set["subsets"][0]["ref"],
    )
    subset = json.loads(subset_path.read_text(encoding="utf-8"))
    assert (
        subset["acceptance"]["accepted_selection_snapshot_ref"]
        == _canonical_snapshot_ref("intent_005_20260701_144245")
    )
    assert subset["subset_id"] == "same_orientation_mullions_001"
    assert subset["band_sets"][0]["band_set_id"] == (
        "same_orientation_mullions_001_bands_001"
    )
    assert subset["band_sets"][0]["ref"].startswith(metadata.CANONICAL_REF_PREFIX)
    assert "accepted_selection_snapshot_path" not in subset["acceptance"]

    grouping_path = metadata.resolve_metadata_ref(
        model.parent,
        subset["band_sets"][0]["ref"],
    )
    grouping = json.loads(grouping_path.read_text(encoding="utf-8"))
    assert grouping["metadata_kind"] == metadata.KIND_ACTOR_GROUPING
    assert (
        grouping["exemplar_selection_snapshot_ref"]
        == _canonical_snapshot_ref("intent_007_20260701_151718")
    )
    assert grouping["band_set_id"] == "same_orientation_mullions_001_bands_001"
    assert "exemplar_selection_snapshot_path" not in grouping

    for item in result["written"]:
        assert item["ref"].startswith(metadata.CANONICAL_REF_PREFIX)
        assert item["resolved_path"].endswith(".json")
        persisted = json.loads(Path(item["resolved_path"]).read_text(encoding="utf-8"))
        _assert_no_absolute_or_backslash_refs(persisted)


def test_write_actor_metadata_bundle_v2_writes_only_canonical_short_refs(tmp_path):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()

    result = _write_bundle(_minimal_bundle(), model)

    assert metadata.LEGACY_REF_PREFIX not in json.dumps(result, sort_keys=True)
    assert result["actor_set_ref"].startswith(metadata.CANONICAL_REF_PREFIX)
    assert len(result["actor_set_ref"]) <= metadata.CANONICAL_REF_MAX_LENGTH
    for item in result["written"]:
        ref = item["ref"]
        assert ref.startswith(metadata.CANONICAL_REF_PREFIX)
        assert len(ref) <= metadata.CANONICAL_REF_MAX_LENGTH
        persisted = json.loads(Path(item["resolved_path"]).read_text(encoding="utf-8"))
        assert metadata.LEGACY_REF_PREFIX not in json.dumps(persisted, sort_keys=True)
        expected_identity = _expected_storage_identity(persisted)
        assert persisted["schema_version"] == 2
        assert persisted["storage_version"] == metadata.STORAGE_VERSION
        assert persisted["ref_protocol"] == metadata.REF_PROTOCOL
        assert persisted["storage_identity"] == expected_identity
        assert metadata.canonical_ref_for_storage_identity(expected_identity) == ref


def test_write_actor_metadata_bundle_v2_same_identity_updates_same_ref(tmp_path):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    first = _write_bundle(_minimal_bundle(), model)
    second_bundle = _minimal_bundle()
    second_bundle["actor_set"]["summary"] = "Updated roof uplift vertical summary."

    second = _write_bundle(second_bundle, model)

    assert second["actor_set_ref"] == first["actor_set_ref"]
    assert second["resolved_actor_set_path"] == first["resolved_actor_set_path"]
    actor_set = json.loads(
        Path(second["resolved_actor_set_path"]).read_text(encoding="utf-8")
    )
    assert actor_set["summary"] == "Updated roof uplift vertical summary."
    assert actor_set["storage_identity"] == {
        "kind": metadata.STORAGE_KIND_ACTOR_SET,
        "actor_set_id": "roof_uplift_vertical_test_chunk_001",
    }


def test_write_actor_metadata_bundle_v2_existing_ref_with_wrong_storage_identity(
    tmp_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    actor_set_ref = _canonical_actor_set_ref("roof_uplift_vertical_test_chunk_001")
    actor_set_path = metadata.resolve_metadata_ref(model.parent, actor_set_ref)
    actor_set_path.parent.mkdir(parents=True)
    existing_payload = {
        "schema_version": 2,
        "metadata_kind": metadata.KIND_ACTOR_SET,
        "storage_version": metadata.STORAGE_VERSION,
        "ref_protocol": metadata.REF_PROTOCOL,
        "storage_identity": {
            "kind": metadata.STORAGE_KIND_ACTOR_SET,
            "actor_set_id": "different_actor_set",
        },
        "actor_set_id": "roof_uplift_vertical_test_chunk_001",
        "source_document": {"file_name": model.name},
        "generated_at_utc": "2026-07-06T00:00:00Z",
        "summary": "Existing file must survive.",
    }
    original_text = json.dumps(existing_payload, indent=2, sort_keys=True) + "\n"
    actor_set_path.write_text(original_text, encoding="utf-8")

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(_minimal_bundle(), model)

    assert _error_code(exc) == "metadata_ref_collision"
    assert actor_set_path.read_text(encoding="utf-8") == original_text


def test_generated_bundle_contains_no_durable_absolute_identity_paths(tmp_path):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"not-a-real-3dm")

    result = asyncio.run(
        metadata.write_actor_metadata_bundle_v2(
            _minimal_bundle(),
            call_native=FakeDocumentNative(str(model)),
            port=None,
        )
    )

    for item in result["written"]:
        payload = json.loads(Path(item["resolved_path"]).read_text(encoding="utf-8"))
        for path, value in _walk_strings(payload):
            if path.endswith("resolved_metadata_path") or ".resolved_" in path:
                continue
            _assert_not_durable_absolute_identity_path(path, value)


def test_capture_source_occurrence_v2_writes_selection_snapshot_without_takes(
    tmp_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir(parents=True)
    native = FakeCaptureNative(model)

    result = asyncio.run(
        metadata.capture_source_occurrence_v2(
            {
                "snapshot_id": "source_occurrence_roof_uplift_vertical_test_chunk_001",
                "ids": ["a28cbdb5-51fa-46b2-b18b-ab880b54ded7"],
            },
            call_native=native,
            port=None,
        )
    )

    assert result["snapshot_ref"] == _canonical_snapshot_ref(
        "source_occurrence_roof_uplift_vertical_test_chunk_001"
    )
    assert result["metadata_kind"] == metadata.KIND_SELECTION_SNAPSHOT
    assert "resolved_snapshot_path" in result
    assert not (model.parent / ".rook" / "director_takes").exists()

    payload = json.loads(Path(result["resolved_snapshot_path"]).read_text("utf-8"))
    loaded = metadata.validate_loaded_metadata(
        payload,
        expected_kind=metadata.KIND_SELECTION_SNAPSHOT,
    )
    assert loaded["snapshot_id"] == "source_occurrence_roof_uplift_vertical_test_chunk_001"
    assert loaded["storage_version"] == metadata.STORAGE_VERSION
    assert loaded["ref_protocol"] == metadata.REF_PROTOCOL
    assert loaded["storage_identity"] == {
        "kind": metadata.STORAGE_KIND_SELECTION_SNAPSHOT,
        "snapshot_id": "source_occurrence_roof_uplift_vertical_test_chunk_001",
    }
    assert loaded["objects"][0]["id"] == "a28cbdb5-51fa-46b2-b18b-ab880b54ded7"
    occurrence = loaded["source_occurrence"]
    assert occurrence["source_top_level_object_id"] == (
        "a28cbdb5-51fa-46b2-b18b-ab880b54ded7"
    )
    assert occurrence["block_definition"]["direct_object_count"] == 3
    inventory = occurrence["definition_inventory_summary"]
    assert inventory["direct_object_count"] == 3
    assert inventory["direct_instance_reference_count"] == 1
    assert inventory["recursive_object_count"] == 9
    assert inventory["recursive_definition_reference_count"] == 3
    assert inventory["nested_definition_reference_count"] == 2
    assert inventory["nested_hierarchy"]["children"][0]["name"] == "Nested Roof Panel"
    assert inventory["type_counts"] == {"Brep": 1, "Curve": 1, "InstanceReference": 1}
    assert loaded["captured_object_source"]["endpoints"] == [
        "/document",
        "/select",
        "/selection",
        "/block/info",
        "/block/instances",
        "/block/objects-detailed",
        "/block/nested",
    ]
    for path, value in _walk_strings(loaded):
        _assert_not_durable_absolute_identity_path(path, value)


def test_capture_source_occurrence_v2_non_block_provenance_omits_block_endpoints(
    tmp_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir(parents=True)

    class NonBlockSelectionNative(FakeCaptureNative):
        async def __call__(self, endpoint, method="GET", data=None, port=None):
            if endpoint.startswith("/block/"):
                raise AssertionError(f"unexpected block endpoint {endpoint}")
            if endpoint == "/selection":
                return {
                    "success": True,
                    "data": {
                        "count": 1,
                        "subObjectCount": 0,
                        "objects": [
                            {
                                "id": "49f0d686-1c0b-4652-8946-3a5804d18a54",
                                "type": "Brep",
                                "layer": "001_MATERIAL::001_01_GARDEN WOOD",
                                "name": "loose_roof_piece",
                                "visible": True,
                                "bbox": {"min": [1, 2, 3], "max": [4, 5, 6]},
                            }
                        ],
                    },
                }
            return await super().__call__(endpoint, method=method, data=data, port=port)

    result = asyncio.run(
        metadata.capture_source_occurrence_v2(
            {
                "snapshot_id": "source_occurrence_loose_roof_piece",
                "ids": ["49f0d686-1c0b-4652-8946-3a5804d18a54"],
            },
            call_native=NonBlockSelectionNative(model),
            port=None,
        )
    )

    loaded = metadata.validate_loaded_metadata(
        json.loads(Path(result["resolved_snapshot_path"]).read_text("utf-8")),
        expected_kind=metadata.KIND_SELECTION_SNAPSHOT,
    )
    assert loaded["captured_object_source"]["endpoints"] == [
        "/document",
        "/select",
        "/selection",
    ]
    assert loaded["source_occurrence"] == {
        "source_top_level_object_id": "49f0d686-1c0b-4652-8946-3a5804d18a54",
        "object_type": "Brep",
        "layer": "001_MATERIAL::001_01_GARDEN WOOD",
        "name": "loose_roof_piece",
        "visible": True,
        "bbox": {"min": [1, 2, 3], "max": [4, 5, 6]},
    }


def test_capture_source_occurrence_v2_rejects_empty_selection(tmp_path):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir(parents=True)

    class EmptySelectionNative(FakeCaptureNative):
        async def __call__(self, endpoint, method="GET", data=None, port=None):
            if endpoint == "/selection":
                return {"success": True, "data": {"count": 0, "objects": []}}
            return await super().__call__(endpoint, method=method, data=data, port=port)

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        asyncio.run(
            metadata.capture_source_occurrence_v2(
                {"snapshot_id": "source_occurrence_empty"},
                call_native=EmptySelectionNative(model),
                port=None,
            )
        )

    assert _error_code(exc) == "source_occurrence_selection_required"
    assert not (model.parent / ".rook").exists()


def test_write_actor_metadata_bundle_v2_accepts_captured_source_occurrence_ref(
    tmp_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir(parents=True)
    capture_native = FakeCaptureNative(model)
    capture = asyncio.run(
        metadata.capture_source_occurrence_v2(
            {
                "snapshot_id": "source_occurrence_roof_uplift_vertical_test_chunk_001",
                "ids": ["a28cbdb5-51fa-46b2-b18b-ab880b54ded7"],
            },
            call_native=capture_native,
            port=None,
        )
    )
    bundle = _minimal_bundle()
    bundle["actor_set"]["source_occurrence_snapshot_ref"] = capture["snapshot_ref"]

    result = _write_bundle(bundle, model)

    actor_set = json.loads(
        Path(result["resolved_actor_set_path"]).read_text(encoding="utf-8")
    )
    assert actor_set["source_occurrence_snapshot_ref"] == capture["snapshot_ref"]


def test_write_actor_metadata_bundle_v2_rejects_legacy_source_occurrence_ref(
    tmp_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir(parents=True)
    legacy_ref = (
        ".rook/director_planning/selection_snapshots/"
        "legacy_source_occurrence.json"
    )
    legacy_path = metadata.resolve_metadata_ref(model.parent, legacy_ref)
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "metadata_kind": metadata.KIND_SELECTION_SNAPSHOT,
                "snapshot_id": "legacy_source_occurrence",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    bundle = _minimal_bundle()
    bundle["actor_set"]["source_occurrence_snapshot_ref"] = legacy_ref

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(bundle, model)

    data = exc.value.to_data()
    assert data["code"] == "metadata_ref_not_canonical"
    assert data["field_path"] == "$.actor_set.source_occurrence_snapshot_ref"
    assert data["ref"] == legacy_ref
    assert not (model.parent / ".rook" / "director" / "v2").exists()


def test_write_actor_metadata_bundle_v2_rejects_missing_source_occurrence_ref(
    tmp_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir(parents=True)
    bundle = _minimal_bundle()
    bundle["actor_set"]["source_occurrence_snapshot_ref"] = _canonical_snapshot_ref(
        "missing_source_occurrence"
    )

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(bundle, model)

    assert _error_code(exc) == "metadata_ref_not_found"


@pytest.mark.parametrize(
    "value",
    [
        r"\\server\share\model.3dm",
        r"C:\project\model.3dm",
        "//server/share/model.3dm",
        "C:/project/model.3dm",
    ],
)
def test_durable_absolute_identity_path_assertion_rejects_windows_absolute_forms(
    value,
):
    with pytest.raises(AssertionError):
        _assert_not_durable_absolute_identity_path("$.source_document.path", value)


def test_write_actor_metadata_bundle_v2_accepts_document_success_envelope(tmp_path):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    native = FakeDocumentNative(str(model), envelope=True)

    result = asyncio.run(
        metadata.write_actor_metadata_bundle_v2(
            _minimal_bundle(),
            call_native=native,
            port=None,
        )
    )

    assert result["actor_set_ref"] == _canonical_actor_set_ref(
        "roof_uplift_vertical_test_chunk_001"
    )
    assert Path(result["resolved_actor_set_path"]).exists()
    actor_set = json.loads(
        Path(result["resolved_actor_set_path"]).read_text(encoding="utf-8")
    )
    assert actor_set["actor_set_id"] == "roof_uplift_vertical_test_chunk_001"


def test_write_actor_metadata_bundle_v2_rejects_unsaved_document():
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        asyncio.run(
            metadata.write_actor_metadata_bundle_v2(
                _minimal_bundle(),
                call_native=FakeDocumentNative(None),
                port=None,
            )
        )

    assert _error_code(exc) == "document_path_required"


def test_write_actor_metadata_bundle_v2_rejects_legacy_input_path_field():
    bundle = copy.deepcopy(_minimal_bundle())
    bundle["actor_set"]["model_path"] = (
        r"H:\AI EXPERIMENTS\Pearson\ANIMATION\Axon.3dm"
    )

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        asyncio.run(
            metadata.write_actor_metadata_bundle_v2(
                bundle,
                call_native=FakeDocumentNative(
                    r"C:\Users\aryan\V2\Axon_Pearson_Experimental_TESTING.3dm"
                ),
                port=None,
            )
        )

    assert _error_code(exc) == "legacy_path_field_present"


def test_write_actor_metadata_bundle_v2_invalid_generated_ref_writes_no_files(tmp_path):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    bundle = _minimal_bundle()
    bundle["actor_set"]["actor_set_id"] = "roof\\bad"
    bundle["subsets"][0]["parent_actor_set_id"] = "roof\\bad"
    bundle["groupings"][0]["parent_actor_set_id"] = "roof\\bad"

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(bundle, model)

    assert _error_code(exc) == "metadata_id_invalid"
    _assert_no_rook_files(model.parent)


@pytest.mark.parametrize(
    "mutate, field_path",
    [
        (
            lambda bundle: (
                bundle["actor_set"].pop("source_snapshot_entry_id"),
                bundle["actor_set"].update({"source_snapshot_ref": r"C:\old\s.json"}),
            ),
            "$.actor_set.source_snapshot_ref",
        ),
        (
            lambda bundle: (
                bundle["subsets"][0]["acceptance"].pop(
                    "accepted_selection_snapshot_id"
                ),
                bundle["subsets"][0]["acceptance"].update(
                    {"accepted_selection_snapshot_ref": r"C:\old\snapshot.json"}
                ),
            ),
            "$.subsets[0].acceptance.accepted_selection_snapshot_ref",
        ),
        (
            lambda bundle: (
                bundle["groupings"][0].pop("exemplar_selection_snapshot_id"),
                bundle["groupings"][0].update(
                    {"exemplar_selection_snapshot_ref": r"C:\old\exemplar.json"}
                ),
            ),
            "$.groupings[0].exemplar_selection_snapshot_ref",
        ),
        (
            lambda bundle: (
                bundle["subsets"][0].pop("band_set_ids"),
                bundle["subsets"][0].update(
                    {"band_sets": [{"ref": r"C:\old\band-set.json"}]}
                ),
            ),
            "$.subsets[0].band_sets[0].ref",
        ),
    ],
)
def test_write_actor_metadata_bundle_v2_rejects_caller_supplied_generated_refs(
    tmp_path,
    mutate,
    field_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    bundle = _minimal_bundle()
    mutate(bundle)

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(bundle, model)

    data = exc.value.to_data()
    assert data["code"] == "generated_ref_field_present"
    assert data["field_path"] == field_path
    _assert_no_rook_files(model.parent)


def test_write_actor_metadata_bundle_v2_rejects_supplied_unknown_source_snapshot_ref(
    tmp_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    bundle = _minimal_bundle()
    bundle["actor_set"].pop("source_snapshot_entry_id")
    bundle["actor_set"]["source_snapshot_ref"] = (
        ".rook/director_planning/selection_snapshots/not_supplied.json"
    )

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(bundle, model)

    data = exc.value.to_data()
    assert data["code"] == "generated_ref_field_present"
    assert data["field_path"] == "$.actor_set.source_snapshot_ref"
    _assert_no_rook_files(model.parent)


def test_write_actor_metadata_bundle_v2_strips_actor_set_subsets_without_top_level_subsets(
    tmp_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    bundle = _minimal_bundle()
    bundle["actor_set"]["subsets"] = [
        {
            "subset_id": "stale_subset",
        }
    ]
    bundle["subsets"] = []
    bundle["groupings"] = []

    result = _write_bundle(bundle, model)

    actor_set = json.loads(
        Path(result["resolved_actor_set_path"]).read_text(encoding="utf-8")
    )
    assert "subsets" not in actor_set


@pytest.mark.parametrize(
    "mutate, field_path",
    [
        (
            lambda bundle: bundle["selection_snapshots"][0].update(
                {"ref": ".rook/director_planning/selection_snapshots/old.json"}
            ),
            "$.selection_snapshots[0].ref",
        ),
        (
            lambda bundle: bundle["subsets"][0].setdefault("notes", {}).update(
                {"review_ref": ".rook/director_planning/selection_snapshots/old.json"}
            ),
            "$.subsets[0].notes.review_ref",
        ),
    ],
)
def test_write_actor_metadata_bundle_v2_rejects_any_incoming_durable_refs(
    tmp_path,
    mutate,
    field_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    bundle = _minimal_bundle()
    mutate(bundle)

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(bundle, model)

    data = exc.value.to_data()
    assert data["code"] == "generated_ref_field_present"
    assert data["field_path"] == field_path
    _assert_no_rook_files(model.parent)


@pytest.mark.parametrize(
    "mutate, field_path",
    [
        (
            lambda bundle: bundle["subsets"][0].update(
                {"ref": ".rook/director_planning/actor_sets/other.json"}
            ),
            "$.subsets[0].ref",
        ),
        (
            lambda bundle: bundle["groupings"][0].update(
                {"ref": ".rook/director_planning/actor_sets/other_grouping.json"}
            ),
            "$.groupings[0].ref",
        ),
    ],
)
def test_write_actor_metadata_bundle_v2_rejects_valid_copied_owned_refs(
    tmp_path,
    mutate,
    field_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    bundle = _minimal_bundle()
    mutate(bundle)

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(bundle, model)

    data = exc.value.to_data()
    assert data["code"] == "generated_ref_field_present"
    assert data["field_path"] == field_path
    _assert_no_rook_files(model.parent)


@pytest.mark.parametrize(
    "mutate, field_path",
    [
        (
            lambda bundle: bundle["actor_set"].update(
                {"source_snapshot_entry_id": "missing_snapshot"}
            ),
            "$.actor_set.source_snapshot_entry_id",
        ),
        (
            lambda bundle: bundle["subsets"][0]["acceptance"].update(
                {"accepted_selection_snapshot_id": "missing_snapshot"}
            ),
            "$.subsets[0].acceptance.accepted_selection_snapshot_id",
        ),
        (
            lambda bundle: bundle["groupings"][0].update(
                {"exemplar_selection_snapshot_id": "missing_snapshot"}
            ),
            "$.groupings[0].exemplar_selection_snapshot_id",
        ),
    ],
)
def test_write_actor_metadata_bundle_v2_rejects_missing_semantic_targets(
    tmp_path,
    mutate,
    field_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    bundle = _minimal_bundle()
    mutate(bundle)

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(bundle, model)

    data = exc.value.to_data()
    assert data["code"] == "metadata_ref_target_missing"
    assert data["field_path"] == field_path
    _assert_no_rook_files(model.parent)


def test_write_actor_metadata_bundle_v2_rejects_duplicate_snapshot_ids(tmp_path):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    bundle = _minimal_bundle()
    bundle["selection_snapshots"].append(copy.deepcopy(bundle["selection_snapshots"][0]))

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(bundle, model)

    data = exc.value.to_data()
    assert data["code"] == "duplicate_metadata_id"
    assert data["field"] == "snapshot_id"
    _assert_no_rook_files(model.parent)


@pytest.mark.parametrize(
    "mutate, field",
    [
        (
            lambda bundle: bundle["subsets"].append(copy.deepcopy(bundle["subsets"][0])),
            "subset_id",
        ),
        (
            lambda bundle: bundle["groupings"].append(
                copy.deepcopy(bundle["groupings"][0])
            ),
            "band_set_id",
        ),
    ],
)
def test_write_actor_metadata_bundle_v2_rejects_duplicate_subset_and_grouping_ids(
    tmp_path,
    mutate,
    field,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    bundle = _minimal_bundle()
    mutate(bundle)

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(bundle, model)

    data = exc.value.to_data()
    assert data["code"] == "duplicate_metadata_id"
    assert data["field"] == field
    _assert_no_rook_files(model.parent)


@pytest.mark.parametrize(
    "mutate, field_path",
    [
        (
            lambda bundle: bundle["actor_set"].update({"actor_set_id": "actor/bad"}),
            "$.actor_set.actor_set_id",
        ),
        (
            lambda bundle: bundle["selection_snapshots"][0].update(
                {"snapshot_id": "snapshot/bad"}
            ),
            "$.selection_snapshots[0].snapshot_id",
        ),
        (
            lambda bundle: bundle["subsets"][0].update({"subset_id": "subset/bad"}),
            "$.subsets[0].subset_id",
        ),
        (
            lambda bundle: bundle["groupings"][0].update(
                {"band_set_id": "band/bad"}
            ),
            "$.groupings[0].band_set_id",
        ),
    ],
)
def test_write_actor_metadata_bundle_v2_rejects_ids_with_path_separators(
    tmp_path,
    mutate,
    field_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    bundle = _minimal_bundle()
    mutate(bundle)

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(bundle, model)

    data = exc.value.to_data()
    assert data["code"] == "metadata_id_invalid"
    assert data["field_path"] == field_path
    _assert_no_rook_files(model.parent)


def test_write_actor_metadata_bundle_v2_rejects_unsafe_band_set_id_before_lookup(
    tmp_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    bundle = _minimal_bundle()
    bundle["subsets"][0]["band_set_ids"] = ["band/bad"]

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(bundle, model)

    data = exc.value.to_data()
    assert data["code"] == "metadata_id_invalid"
    assert data["field_path"] == "$.subsets[0].band_set_ids[0]"
    _assert_no_rook_files(model.parent)


@pytest.mark.parametrize(
    "actor_set_id",
    [
        "bad:name",
        "bad*name",
        "NUL",
        "name.",
        "name ",
    ],
)
def test_write_actor_metadata_bundle_v2_rejects_windows_invalid_filename_ids(
    tmp_path,
    actor_set_id,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    bundle = _minimal_bundle()
    bundle["actor_set"]["actor_set_id"] = actor_set_id
    bundle["subsets"][0]["parent_actor_set_id"] = actor_set_id
    bundle["groupings"][0]["parent_actor_set_id"] = actor_set_id

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(bundle, model)

    data = exc.value.to_data()
    assert data["code"] == "metadata_id_invalid"
    assert data["field_path"] == "$.actor_set.actor_set_id"
    _assert_no_rook_files(model.parent)


@pytest.mark.parametrize(
    "mutate, field_path",
    [
        (
            lambda bundle: bundle["subsets"][0].update(
                {"parent_actor_set_id": "other_actor_set"}
            ),
            "$.subsets[0].parent_actor_set_id",
        ),
        (
            lambda bundle: bundle["groupings"][0].update(
                {"parent_actor_set_id": "other_actor_set"}
            ),
            "$.groupings[0].parent_actor_set_id",
        ),
    ],
)
def test_write_actor_metadata_bundle_v2_rejects_parent_actor_set_mismatch(
    tmp_path,
    mutate,
    field_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    bundle = _minimal_bundle()
    mutate(bundle)

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(bundle, model)

    data = exc.value.to_data()
    assert data["code"] == "metadata_parent_mismatch"
    assert data["field_path"] == field_path
    _assert_no_rook_files(model.parent)


def test_write_actor_metadata_bundle_v2_rejects_unknown_grouping_parent_subset(
    tmp_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    bundle = _minimal_bundle()
    bundle["groupings"][0]["parent_subset_id"] = "not_a_supplied_subset"

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(bundle, model)

    data = exc.value.to_data()
    assert data["code"] == "metadata_ref_target_missing"
    assert data["field_path"] == "$.groupings[0].parent_subset_id"
    _assert_no_rook_files(model.parent)


@pytest.mark.parametrize(
    "mutate, field_path",
    [
        (
            lambda bundle: bundle.update(
                {"selection_snapshots": {"snapshot_id": "intent_005_20260701_144245"}}
            ),
            "$.selection_snapshots",
        ),
        (
            lambda bundle: bundle.update({"subsets": {"subset_id": "s"}}),
            "$.subsets",
        ),
        (
            lambda bundle: bundle.update({"groupings": {"band_set_id": "g"}}),
            "$.groupings",
        ),
        (
            lambda bundle: bundle["subsets"][0].update({"band_set_ids": "not-a-list"}),
            "$.subsets[0].band_set_ids",
        ),
    ],
)
def test_write_actor_metadata_bundle_v2_rejects_non_list_collections(
    tmp_path,
    mutate,
    field_path,
):
    model = tmp_path / "V2" / "Axon_Pearson_Experimental_TESTING.3dm"
    model.parent.mkdir()
    bundle = _minimal_bundle()
    mutate(bundle)

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        _write_bundle(bundle, model)

    data = exc.value.to_data()
    assert data["code"] == "metadata_collection_invalid"
    assert data["field_path"] == field_path
    _assert_no_rook_files(model.parent)


def test_storage_identity_ref_vectors_are_stable():
    cases = [
        (
            metadata.KIND_ACTOR_SET,
            {
                "kind": "actor_set",
                "actor_set_id": "roof_uplift_vertical_test_chunk_001",
            },
            ".rook/director/v2/actor_sets/as_c1ec0538f22b.json",
        ),
        (
            metadata.KIND_SELECTION_SNAPSHOT,
            {
                "kind": "selection_snapshot",
                "snapshot_id": "intent_007_20260701_151718",
            },
            ".rook/director/v2/snapshots/snap_df85677fc72b.json",
        ),
        (
            metadata.KIND_ACTOR_SUBSET,
            {
                "kind": "subset",
                "actor_set_id": "roof_uplift_vertical_test_chunk_001",
                "subset_id": "same_orientation_mullions_001",
            },
            ".rook/director/v2/subsets/sub_441d535918e7.json",
        ),
        (
            metadata.KIND_ACTOR_GROUPING,
            {
                "kind": "grouping",
                "actor_set_id": "roof_uplift_vertical_test_chunk_001",
                "subset_id": "same_orientation_mullions_001",
                "band_set_id": "same_orientation_mullions_001_bands_001",
            },
            ".rook/director/v2/groupings/grp_bc337869b2f0.json",
        ),
    ]

    for metadata_kind, identity, expected_ref in cases:
        ref = metadata.canonical_ref_for_storage_identity(identity)
        assert ref == expected_ref
        assert metadata.canonical_ref_matches_storage_identity(ref, identity)
        assert metadata.metadata_kind_for_storage_identity(identity) == metadata_kind


def test_storage_identity_ref_uses_expected_canonical_hash():
    identity = {
        "kind": "grouping",
        "actor_set_id": "roof_uplift_vertical_test_chunk_001",
        "subset_id": "same_orientation_mullions_001",
        "band_set_id": "same_orientation_mullions_001_bands_001",
    }

    assert metadata.storage_identity_hash(identity) == "bc337869b2f0"
    assert metadata.storage_identity_hash(
        {
            "band_set_id": "same_orientation_mullions_001_bands_001",
            "subset_id": "same_orientation_mullions_001",
            "actor_set_id": "roof_uplift_vertical_test_chunk_001",
            "kind": "grouping",
        }
    ) == "bc337869b2f0"
    assert metadata.canonical_ref_for_storage_identity(identity) == (
        ".rook/director/v2/groupings/grp_bc337869b2f0.json"
    )


@pytest.mark.parametrize(
    "identity",
    [
        {"kind": "unknown", "actor_set_id": "actor_set_001"},
        {
            "kind": "actor_set",
            "actor_set_id": "actor_set_001",
            "subset_id": "extra",
        },
        {"kind": "selection_snapshot", "snapshot_id": ""},
        {"kind": "subset", "actor_set_id": "actor_set_001"},
        {
            "kind": "grouping",
            "actor_set_id": "actor_set_001",
            "subset_id": "subset_001",
            "band_set_id": 123,
        },
    ],
)
def test_storage_identity_ref_rejects_invalid_canonical_identity(identity):
    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        metadata.storage_identity_hash(identity)

    assert _error_code(exc) == "storage_identity_invalid"


def test_canonical_refs_have_path_budget_and_no_semantic_path_leakage():
    semantic_values = {
        "roof_uplift_vertical_test_chunk_001",
        "same_orientation_mullions_001",
        "same_orientation_mullions_001_bands_001",
        "intent_007_20260701_151718",
    }
    identities = [
        {
            "kind": "actor_set",
            "actor_set_id": "roof_uplift_vertical_test_chunk_001",
        },
        {
            "kind": "selection_snapshot",
            "snapshot_id": "intent_007_20260701_151718",
        },
        {
            "kind": "subset",
            "actor_set_id": "roof_uplift_vertical_test_chunk_001",
            "subset_id": "same_orientation_mullions_001",
        },
        {
            "kind": "grouping",
            "actor_set_id": "roof_uplift_vertical_test_chunk_001",
            "subset_id": "same_orientation_mullions_001",
            "band_set_id": "same_orientation_mullions_001_bands_001",
        },
    ]
    deep_root = Path(
        "C:/Users/aryan/Documents/Project Transfers/"
        "Pearson Director Animation Transfer/V2"
    )

    for identity in identities:
        ref = metadata.canonical_ref_for_storage_identity(identity)
        assert len(ref) <= metadata.CANONICAL_REF_MAX_LENGTH
        assert (
            len(str(deep_root / Path(*ref.split("/"))))
            < metadata.DEEP_TRANSFER_PATH_MAX_LENGTH
        )
        segments = ref.split("/")
        for semantic_value in semantic_values:
            assert semantic_value not in segments
            assert semantic_value not in ref
