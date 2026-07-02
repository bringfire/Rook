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
