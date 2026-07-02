from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest

from rook import director_actor_metadata as metadata


class FakeDocumentNative:
    def __init__(self, path: str | None):
        self.path = path
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
        return {
            "success": True,
            "name": Path(self.path).name if self.path else "Unsaved.3dm",
            "path": self.path,
        }


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

    actor_set_ref = (
        ".rook/director_planning/actor_sets/"
        "roof_uplift_vertical_test_chunk_001.json"
    )
    assert result["actor_set_ref"] == actor_set_ref

    actor_set_path = metadata.resolve_metadata_ref(model.parent, actor_set_ref)
    actor_set = json.loads(actor_set_path.read_text(encoding="utf-8"))
    assert actor_set["schema_version"] == 2
    assert actor_set["metadata_kind"] == metadata.KIND_ACTOR_SET
    assert actor_set["source_document"]["file_name"] == model.name
    assert (
        actor_set["source_snapshot_ref"]
        == ".rook/director_planning/selection_snapshots/"
        "intent_005_20260701_144245.json"
    )
    assert actor_set["subsets"][0]["ref"].endswith("same_orientation_mullions_001.json")
    assert "model_path" not in actor_set
    assert "source_snapshot_path" not in actor_set

    subset_path = metadata.resolve_metadata_ref(
        model.parent,
        actor_set["subsets"][0]["ref"],
    )
    subset = json.loads(subset_path.read_text(encoding="utf-8"))
    assert subset["acceptance"]["accepted_selection_snapshot_ref"].endswith(
        "intent_005_20260701_144245.json"
    )
    assert subset["band_sets"][0]["ref"].endswith(
        "same_orientation_mullions_001_bands_001.json"
    )
    assert "accepted_selection_snapshot_path" not in subset["acceptance"]

    grouping_path = metadata.resolve_metadata_ref(
        model.parent,
        subset["band_sets"][0]["ref"],
    )
    grouping = json.loads(grouping_path.read_text(encoding="utf-8"))
    assert grouping["metadata_kind"] == metadata.KIND_ACTOR_GROUPING
    assert grouping["exemplar_selection_snapshot_ref"].endswith(
        "intent_007_20260701_151718.json"
    )
    assert "exemplar_selection_snapshot_path" not in grouping

    for item in result["written"]:
        assert item["ref"].startswith(".rook/")
        assert item["resolved_path"].endswith(".json")


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
