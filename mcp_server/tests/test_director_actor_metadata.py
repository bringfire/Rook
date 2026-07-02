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
        persisted = json.loads(Path(item["resolved_path"]).read_text(encoding="utf-8"))
        _assert_no_absolute_or_backslash_refs(persisted)


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

    assert result["actor_set_ref"].endswith("roof_uplift_vertical_test_chunk_001.json")
    assert Path(result["resolved_actor_set_path"]).exists()


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
