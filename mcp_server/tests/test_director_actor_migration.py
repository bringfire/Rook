from __future__ import annotations

import json
from pathlib import Path

import pytest

from rook import director_actor_metadata as metadata
from rook import director_actor_migration as migration


def _change_fields(changes: list[dict]) -> set[str]:
    return {change["field"] for change in changes}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_convert_v1_actor_set_payload_renames_paths_and_preserves_members(tmp_path):
    project_root = tmp_path / "project"
    model = project_root / "Axon.3dm"
    snapshot_path = (
        project_root
        / ".rook"
        / "director_planning"
        / "selection_snapshots"
        / "intent_001.json"
    )
    subset_path = (
        project_root
        / ".rook"
        / "director_planning"
        / "actor_sets"
        / "set_001_subsets"
        / "subset_001.json"
    )
    snapshot_path.parent.mkdir(parents=True)
    subset_path.parent.mkdir(parents=True)
    snapshot_path.write_text("{}", encoding="utf-8")
    subset_path.write_text("{}", encoding="utf-8")
    members = [{"id": "mesh_001"}, {"id": "mesh_002"}]
    payload = {
        "schema_version": 1,
        "actor_set_id": "set_001",
        "model_path": str(model),
        "source_snapshot_path": str(snapshot_path),
        "members": members,
        "subsets": [{"subset_id": "subset_001", "path": str(subset_path)}],
    }

    converted, changes = migration.convert_v1_payload(
        payload,
        project_root=project_root,
        source_path=project_root
        / ".rook"
        / "director_planning"
        / "actor_sets"
        / "set_001.json",
    )

    assert converted["schema_version"] == 2
    assert converted["metadata_kind"] == metadata.KIND_ACTOR_SET
    assert (
        converted["source_snapshot_ref"]
        == ".rook/director_planning/selection_snapshots/intent_001.json"
    )
    assert (
        converted["subsets"][0]["ref"]
        == ".rook/director_planning/actor_sets/set_001_subsets/subset_001.json"
    )
    assert converted["members"] == members
    assert "model_path" not in converted
    assert "source_snapshot_path" not in converted
    assert "path" not in converted["subsets"][0]
    assert {"$.model_path", "$.source_snapshot_path", "$.subsets[0].path"} <= (
        _change_fields(changes)
    )


def test_convert_v1_snapshot_replaces_model_path_and_document_path(tmp_path):
    project_root = tmp_path / "project"
    model = project_root / "Axon.3dm"
    document = project_root / "ModelFromDocument.3dm"
    payload = {
        "schema_version": 1,
        "snapshot_id": "intent_001",
        "model_path": str(model),
        "document": {
            "path": str(document),
            "units": "Feet",
        },
        "selected": [{"id": "mesh_001"}],
    }

    converted, changes = migration.convert_v1_payload(
        payload,
        project_root=project_root,
        source_path=project_root
        / ".rook"
        / "director_planning"
        / "selection_snapshots"
        / "intent_001.json",
    )

    assert converted["schema_version"] == 2
    assert converted["metadata_kind"] == metadata.KIND_SELECTION_SNAPSHOT
    assert converted["source_document"]["file_name"] == model.name
    assert converted["document"]["units"] == "Feet"
    assert "path" not in converted["document"]
    assert "model_path" not in converted
    assert {"$.model_path", "$.document.path"} <= _change_fields(changes)


def test_convert_v1_rejects_model_path_outside_project(tmp_path):
    project_root = tmp_path / "project"
    payload = {
        "schema_version": 1,
        "snapshot_id": "intent_001",
        "model_path": str(tmp_path / "outside" / "Axon.3dm"),
    }

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        migration.convert_v1_payload(
            payload,
            project_root=project_root,
            source_path=project_root / "intent_001.json",
        )

    data = exc.value.to_data()
    assert data["code"] == "path_outside_project_root"
    assert data["field"] == "$.model_path"


def test_convert_v1_rejects_document_path_outside_project(tmp_path):
    project_root = tmp_path / "project"
    payload = {
        "schema_version": 1,
        "snapshot_id": "intent_001",
        "document": {"path": str(tmp_path / "outside" / "Axon.3dm")},
    }

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        migration.convert_v1_payload(
            payload,
            project_root=project_root,
            source_path=project_root / "intent_001.json",
        )

    data = exc.value.to_data()
    assert data["code"] == "path_outside_project_root"
    assert data["field"] == "$.document.path"


def test_convert_v1_rejects_absolute_path_outside_project(tmp_path):
    project_root = tmp_path / "project"
    payload = {
        "schema_version": 1,
        "actor_set_id": "set_001",
        "source_snapshot_path": str(tmp_path / "outside" / "intent_001.json"),
    }

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        migration.convert_v1_payload(
            payload,
            project_root=project_root,
            source_path=project_root / "set_001.json",
        )

    data = exc.value.to_data()
    assert data["code"] == "path_outside_project_root"
    assert data["field"] == "$.source_snapshot_path"


def test_convert_v1_grouping_preserves_curated_metadata_and_order(tmp_path):
    project_root = tmp_path / "project"
    exemplar_path = (
        project_root
        / ".rook"
        / "director_planning"
        / "selection_snapshots"
        / "intent_007.json"
    )
    source_path = (
        project_root
        / ".rook"
        / "director_planning"
        / "actor_sets"
        / "set_001_subsets"
        / "subset_001_band_sets"
        / "bands_001.json"
    )
    exemplar_path.parent.mkdir(parents=True)
    exemplar_path.write_text("{}", encoding="utf-8")
    bands = [
        {"band_id": "front", "order": 1, "members": [{"id": "mesh_001"}]},
        {"band_id": "rear", "order": 2, "members": [{"id": "mesh_002"}]},
    ]
    classifier = {"method": "distance_from_exemplar", "threshold_model_units": 0.125}
    provenance = {"curated_by": "reviewer", "source": "manual"}
    summary = {
        "label": "Curated orientation bands.",
        "band_count": 2,
    }
    payload = {
        "schema_version": 1,
        "band_set_id": "bands_001",
        "parent_actor_set_id": "set_001",
        "parent_subset_id": "subset_001",
        "summary": summary,
        "classifier": classifier,
        "provenance": provenance,
        "exemplar_selection_snapshot_path": str(exemplar_path),
        "bands": bands,
    }

    converted, changes = migration.convert_v1_payload(
        payload,
        project_root=project_root,
        source_path=source_path,
    )

    assert converted["metadata_kind"] == metadata.KIND_ACTOR_GROUPING
    assert (
        converted["exemplar_selection_snapshot_ref"]
        == ".rook/director_planning/selection_snapshots/intent_007.json"
    )
    assert converted["parent_actor_set_id"] == "set_001"
    assert converted["parent_subset_id"] == "subset_001"
    assert converted["classifier"] == classifier
    assert converted["provenance"] == provenance
    assert converted["summary"] == summary
    assert converted["bands"] == bands
    assert "exemplar_selection_snapshot_path" not in converted
    assert "$.exemplar_selection_snapshot_path" in _change_fields(changes)


def test_migrate_actor_metadata_v2_writes_converted_copy_and_report(tmp_path):
    project_root = tmp_path / "project"
    actor_set_path = (
        project_root
        / ".rook"
        / "director_planning"
        / "actor_sets"
        / "set_001.json"
    )
    snapshot_path = (
        project_root
        / ".rook"
        / "director_planning"
        / "selection_snapshots"
        / "intent_001.json"
    )
    actor_set_path.parent.mkdir(parents=True)
    snapshot_path.parent.mkdir(parents=True)
    actor_set_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "actor_set_id": "set_001",
                "source_snapshot_path": str(snapshot_path),
                "members": [{"id": "mesh_001"}],
            }
        ),
        encoding="utf-8",
    )
    snapshot_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "snapshot_id": "intent_001",
                "model_path": str(project_root / "Axon.3dm"),
                "selected": [{"id": "mesh_001"}],
            }
        ),
        encoding="utf-8",
    )

    report = migration.migrate_actor_metadata_v2(
        {
            "project_root": str(project_root),
            "files": [str(actor_set_path), str(snapshot_path)],
            "write": True,
            "suffix": ".v2",
        }
    )

    assert report["state"] == "complete"
    assert report["write"] is True
    assert len(report["files"]) == 2
    for file_report in report["files"]:
        output_path = Path(file_report["output_path"])
        assert output_path.exists()
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 2


def test_migrate_actor_metadata_v2_rejects_string_write_without_writing(tmp_path):
    project_root = tmp_path / "project"
    actor_set_path = (
        project_root
        / ".rook"
        / "director_planning"
        / "actor_sets"
        / "set_001.json"
    )
    _write_json(
        actor_set_path,
        {
            "schema_version": 1,
            "actor_set_id": "set_001",
            "members": [{"id": "mesh_001"}],
        },
    )

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        migration.migrate_actor_metadata_v2(
            {
                "project_root": str(project_root),
                "files": [str(actor_set_path)],
                "write": "false",
            }
        )

    data = exc.value.to_data()
    assert data["code"] == "metadata_invalid"
    assert data["field"] == "write"
    assert not actor_set_path.with_name("set_001.v2.json").exists()


def test_migrate_actor_metadata_v2_rejects_absolute_file_outside_project_without_writing(
    tmp_path,
):
    project_root = tmp_path / "project"
    outside_path = tmp_path / "outside" / "set_001.json"
    _write_json(
        outside_path,
        {
            "schema_version": 1,
            "actor_set_id": "set_001",
            "members": [{"id": "mesh_001"}],
        },
    )

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        migration.migrate_actor_metadata_v2(
            {
                "project_root": str(project_root),
                "files": [str(outside_path)],
                "write": True,
                "suffix": ".v2",
            }
        )

    data = exc.value.to_data()
    assert data["code"] == "path_outside_project_root"
    assert data["field"] == "$.files[0]"
    assert data["path"] == str(outside_path.resolve())
    assert data["project_root"] == str(project_root.resolve())
    assert not outside_path.with_name("set_001.v2.json").exists()


def test_migrate_actor_metadata_v2_rejects_empty_suffix(tmp_path):
    project_root = tmp_path / "project"
    actor_set_path = (
        project_root
        / ".rook"
        / "director_planning"
        / "actor_sets"
        / "set_001.json"
    )
    _write_json(
        actor_set_path,
        {
            "schema_version": 1,
            "actor_set_id": "set_001",
            "members": [{"id": "mesh_001"}],
        },
    )

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        migration.migrate_actor_metadata_v2(
            {
                "project_root": str(project_root),
                "files": [str(actor_set_path)],
                "write": True,
                "suffix": "",
            }
        )

    data = exc.value.to_data()
    assert data["code"] == "metadata_invalid"
    assert data["field"] == "suffix"
    assert json.loads(actor_set_path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_migrate_actor_metadata_v2_preflights_all_files_before_writing(tmp_path):
    project_root = tmp_path / "project"
    actor_set_path = (
        project_root
        / ".rook"
        / "director_planning"
        / "actor_sets"
        / "set_001.json"
    )
    invalid_snapshot_path = (
        project_root
        / ".rook"
        / "director_planning"
        / "selection_snapshots"
        / "intent_001.json"
    )
    _write_json(
        actor_set_path,
        {
            "schema_version": 1,
            "actor_set_id": "set_001",
            "members": [{"id": "mesh_001"}],
        },
    )
    _write_json(
        invalid_snapshot_path,
        {
            "schema_version": 1,
            "snapshot_id": "intent_001",
            "model_path": str(tmp_path / "outside" / "Axon.3dm"),
        },
    )

    with pytest.raises(metadata.DirectorActorMetadataError) as exc:
        migration.migrate_actor_metadata_v2(
            {
                "project_root": str(project_root),
                "files": [str(actor_set_path), str(invalid_snapshot_path)],
                "write": True,
                "suffix": ".v2",
            }
        )

    data = exc.value.to_data()
    assert data["code"] == "path_outside_project_root"
    assert data["field"] == "$.model_path"
    assert not actor_set_path.with_name("set_001.v2.json").exists()


def test_migrate_actor_metadata_storage_refs_v2_writes_canonical_short_tree_and_report(
    tmp_path,
):
    root = tmp_path / "project"
    actor = root / ".rook" / "director_planning" / "actor_sets" / "set_001.json"
    snapshot = (
        root
        / ".rook"
        / "director_planning"
        / "selection_snapshots"
        / "snap_001.json"
    )
    subset = (
        root
        / ".rook"
        / "director_planning"
        / "actor_sets"
        / "set_001_subsets"
        / "subset_001.json"
    )
    grouping = (
        root
        / ".rook"
        / "director_planning"
        / "actor_sets"
        / "set_001_subsets"
        / "subset_001_band_sets"
        / "bands_001.json"
    )

    _write(
        snapshot,
        {
            "schema_version": 2,
            "metadata_kind": metadata.KIND_SELECTION_SNAPSHOT,
            "snapshot_id": "snap_001",
            "objects": [],
        },
    )
    _write(
        grouping,
        {
            "schema_version": 2,
            "metadata_kind": metadata.KIND_ACTOR_GROUPING,
            "band_set_id": "bands_001",
            "parent_actor_set_id": "set_001",
            "parent_subset_id": "subset_001",
            "exemplar_selection_snapshot_ref": metadata.ref_from_project_path(
                root,
                snapshot,
            ),
            "bands": [],
        },
    )
    _write(
        subset,
        {
            "schema_version": 2,
            "metadata_kind": metadata.KIND_ACTOR_SUBSET,
            "subset_id": "subset_001",
            "parent_actor_set_id": "set_001",
            "acceptance": {
                "accepted_selection_snapshot_ref": metadata.ref_from_project_path(
                    root,
                    snapshot,
                ),
            },
            "band_sets": [
                {
                    "band_set_id": "bands_001",
                    "ref": metadata.ref_from_project_path(root, grouping),
                }
            ],
        },
    )
    _write(
        actor,
        {
            "schema_version": 2,
            "metadata_kind": metadata.KIND_ACTOR_SET,
            "actor_set_id": "set_001",
            "source_snapshot_ref": metadata.ref_from_project_path(root, snapshot),
            "subsets": [
                {
                    "subset_id": "subset_001",
                    "ref": metadata.ref_from_project_path(root, subset),
                }
            ],
        },
    )

    result = migration.migrate_actor_metadata_storage_refs_v2(
        {
            "project_root": str(root),
            "actor_set_refs": [metadata.ref_from_project_path(root, actor)],
            "write": True,
            "write_report": True,
        }
    )

    assert result["state"] == "complete"
    assert result["report_ref"].startswith(".rook/director/v2/migration_reports/mig_")
    assert all(
        entry["new_ref"].startswith(".rook/director/v2/")
        for entry in result["mappings"]
    )
    assert {entry["status"] for entry in result["mappings"]} == {"created"}
    assert actor.exists()
    assert snapshot.exists()
    report_path = metadata.resolve_metadata_ref(root, result["report_ref"])
    assert report_path.exists()
    canonical_actor_entry = next(
        entry
        for entry in result["mappings"]
        if entry["metadata_kind"] == metadata.KIND_ACTOR_SET
    )
    canonical_actor = _read(
        metadata.resolve_metadata_ref(root, canonical_actor_entry["new_ref"])
    )
    canonical_subset_entry = next(
        entry
        for entry in result["mappings"]
        if entry["metadata_kind"] == metadata.KIND_ACTOR_SUBSET
    )
    canonical_subset = _read(
        metadata.resolve_metadata_ref(root, canonical_subset_entry["new_ref"])
    )
    canonical_grouping_entry = next(
        entry
        for entry in result["mappings"]
        if entry["metadata_kind"] == metadata.KIND_ACTOR_GROUPING
    )
    canonical_grouping = _read(
        metadata.resolve_metadata_ref(root, canonical_grouping_entry["new_ref"])
    )
    assert canonical_actor["subsets"][0]["ref"].startswith(
        ".rook/director/v2/subsets/sub_"
    )
    assert canonical_actor["source_snapshot_ref"].startswith(
        ".rook/director/v2/snapshots/snap_"
    )
    assert canonical_subset["acceptance"]["accepted_selection_snapshot_ref"].startswith(
        ".rook/director/v2/snapshots/snap_"
    )
    assert canonical_subset["band_sets"][0]["ref"].startswith(
        ".rook/director/v2/groupings/grp_"
    )
    assert canonical_grouping["exemplar_selection_snapshot_ref"].startswith(
        ".rook/director/v2/snapshots/snap_"
    )


def test_migrate_actor_metadata_storage_refs_v2_rerun_reuses_same_report_ref(tmp_path):
    root = tmp_path / "project"
    actor = root / ".rook" / "director_planning" / "actor_sets" / "set_001.json"
    _write(
        actor,
        {
            "schema_version": 2,
            "metadata_kind": metadata.KIND_ACTOR_SET,
            "actor_set_id": "set_001",
            "subsets": [],
        },
    )
    args = {
        "project_root": str(root),
        "actor_set_refs": [metadata.ref_from_project_path(root, actor)],
        "write": True,
        "write_report": True,
    }

    first = migration.migrate_actor_metadata_storage_refs_v2(args)
    second = migration.migrate_actor_metadata_storage_refs_v2(args)

    assert first["report_ref"] == second["report_ref"]
    assert {entry["status"] for entry in first["mappings"]} == {"created"}
    assert {entry["status"] for entry in second["mappings"]} == {"reused"}


def test_migrate_actor_metadata_storage_refs_v2_dry_run_marks_planned_without_writing(
    tmp_path,
):
    root = tmp_path / "project"
    actor = root / ".rook" / "director_planning" / "actor_sets" / "set_001.json"
    _write(
        actor,
        {
            "schema_version": 2,
            "metadata_kind": metadata.KIND_ACTOR_SET,
            "actor_set_id": "set_001",
            "subsets": [],
        },
    )

    result = migration.migrate_actor_metadata_storage_refs_v2(
        {
            "project_root": str(root),
            "actor_set_refs": [metadata.ref_from_project_path(root, actor)],
            "write": False,
            "write_report": False,
        }
    )

    assert result["state"] == "complete"
    assert {entry["status"] for entry in result["mappings"]} == {"planned"}
    canonical_actor = metadata.resolve_metadata_ref(
        root,
        result["mappings"][0]["new_ref"],
    )
    assert not canonical_actor.exists()


def test_migrate_actor_metadata_storage_refs_v2_conflict_fails_overall(tmp_path):
    root = tmp_path / "project"
    actor = root / ".rook" / "director_planning" / "actor_sets" / "set_001.json"
    _write(
        actor,
        {
            "schema_version": 2,
            "metadata_kind": metadata.KIND_ACTOR_SET,
            "actor_set_id": "set_001",
            "subsets": [],
            "summary": "source",
        },
    )
    identity = {"kind": "actor_set", "actor_set_id": "set_001"}
    canonical_ref = metadata.canonical_ref_for_storage_identity(identity)
    canonical_path = metadata.resolve_metadata_ref(root, canonical_ref)
    _write(
        canonical_path,
        {
            "schema_version": 2,
            "metadata_kind": metadata.KIND_ACTOR_SET,
            "storage_version": 2,
            "ref_protocol": metadata.REF_PROTOCOL,
            "storage_identity": identity,
            "actor_set_id": "set_001",
            "summary": "different",
        },
    )

    result = migration.migrate_actor_metadata_storage_refs_v2(
        {
            "project_root": str(root),
            "actor_set_refs": [metadata.ref_from_project_path(root, actor)],
            "write": True,
            "write_report": True,
        }
    )

    assert result["state"] == "failed"
    assert result["mappings"][0]["status"] == "conflicted"


def test_migrate_actor_metadata_storage_refs_v2_conflict_writes_no_partial_tree(
    tmp_path,
):
    root = tmp_path / "project"
    actor = root / ".rook" / "director_planning" / "actor_sets" / "set_001.json"
    subset = (
        root
        / ".rook"
        / "director_planning"
        / "actor_sets"
        / "set_001_subsets"
        / "subset_001.json"
    )
    _write(
        subset,
        {
            "schema_version": 2,
            "metadata_kind": metadata.KIND_ACTOR_SUBSET,
            "subset_id": "subset_001",
            "parent_actor_set_id": "set_001",
            "summary": "source subset",
        },
    )
    _write(
        actor,
        {
            "schema_version": 2,
            "metadata_kind": metadata.KIND_ACTOR_SET,
            "actor_set_id": "set_001",
            "subsets": [
                {
                    "subset_id": "subset_001",
                    "ref": metadata.ref_from_project_path(root, subset),
                }
            ],
        },
    )
    subset_identity = {
        "kind": "subset",
        "actor_set_id": "set_001",
        "subset_id": "subset_001",
    }
    canonical_subset_ref = metadata.canonical_ref_for_storage_identity(
        subset_identity,
    )
    _write(
        metadata.resolve_metadata_ref(root, canonical_subset_ref),
        {
            "schema_version": 2,
            "metadata_kind": metadata.KIND_ACTOR_SUBSET,
            "storage_version": 2,
            "ref_protocol": metadata.REF_PROTOCOL,
            "storage_identity": subset_identity,
            "subset_id": "subset_001",
            "parent_actor_set_id": "set_001",
            "summary": "different subset",
        },
    )

    result = migration.migrate_actor_metadata_storage_refs_v2(
        {
            "project_root": str(root),
            "actor_set_refs": [metadata.ref_from_project_path(root, actor)],
            "write": True,
            "write_report": True,
        }
    )

    statuses = {
        entry["metadata_kind"]: entry["status"]
        for entry in result["mappings"]
    }
    actor_entry = next(
        entry
        for entry in result["mappings"]
        if entry["metadata_kind"] == metadata.KIND_ACTOR_SET
    )
    assert result["state"] == "failed"
    assert statuses[metadata.KIND_ACTOR_SET] == "planned"
    assert statuses[metadata.KIND_ACTOR_SUBSET] == "conflicted"
    assert not metadata.resolve_metadata_ref(root, actor_entry["new_ref"]).exists()


def test_migrate_actor_metadata_storage_refs_v2_intra_run_ref_conflict_fails(
    tmp_path,
):
    root = tmp_path / "project"
    actor_a = root / ".rook" / "director_planning" / "actor_sets" / "set_001_a.json"
    actor_b = root / ".rook" / "director_planning" / "actor_sets" / "set_001_b.json"
    _write(
        actor_a,
        {
            "schema_version": 2,
            "metadata_kind": metadata.KIND_ACTOR_SET,
            "actor_set_id": "set_001",
            "subsets": [],
            "summary": "first source",
        },
    )
    _write(
        actor_b,
        {
            "schema_version": 2,
            "metadata_kind": metadata.KIND_ACTOR_SET,
            "actor_set_id": "set_001",
            "subsets": [],
            "summary": "second source",
        },
    )

    result = migration.migrate_actor_metadata_storage_refs_v2(
        {
            "project_root": str(root),
            "actor_set_refs": [
                metadata.ref_from_project_path(root, actor_a),
                metadata.ref_from_project_path(root, actor_b),
            ],
            "write": True,
            "write_report": True,
        }
    )

    assert result["state"] == "failed"
    assert {entry["new_ref"] for entry in result["mappings"]} == {
        metadata.canonical_ref_for_storage_identity(
            {"kind": "actor_set", "actor_set_id": "set_001"}
        )
    }
    assert {entry["status"] for entry in result["mappings"]} == {"conflicted"}
    assert not metadata.resolve_metadata_ref(
        root,
        result["mappings"][0]["new_ref"],
    ).exists()
