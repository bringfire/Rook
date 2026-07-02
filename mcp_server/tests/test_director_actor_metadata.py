from __future__ import annotations

import json

import pytest

from rook import director_actor_metadata as metadata


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
