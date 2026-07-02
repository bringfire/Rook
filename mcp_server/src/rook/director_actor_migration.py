from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from . import director_actor_metadata as dam


def _raise(code: str, message: str, **data: Any) -> None:
    raise dam.DirectorActorMetadataError(code, message, **data)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _classify_kind(payload: dict, source_path: Path) -> str:
    if "actor_set_id" in payload:
        return dam.KIND_ACTOR_SET
    if "subset_id" in payload:
        return dam.KIND_ACTOR_SUBSET
    if "band_set_id" in payload:
        return dam.KIND_ACTOR_GROUPING
    if "snapshot_id" in payload or "entry_id" in payload:
        return dam.KIND_SELECTION_SNAPSHOT
    if source_path.name.startswith("intent_"):
        return dam.KIND_SELECTION_SNAPSHOT
    _raise(
        "metadata_kind_unknown",
        "Could not infer Director actor metadata kind.",
        source_path=str(source_path),
    )


def _record_change(changes: list[dict], field: str, action: str) -> None:
    changes.append({"field": field, "action": action})


def _path_value(value: Any, *, field: str) -> Path:
    if not isinstance(value, str) or not value:
        _raise(
            "metadata_path_invalid",
            "Metadata path field must be a non-empty string.",
            field=field,
        )
    return Path(value)


def _validate_absolute_under_project(
    project_root: Path,
    path: Path,
    *,
    field: str,
) -> None:
    if not path.is_absolute():
        return
    root = Path(project_root).resolve()
    resolved = path.resolve()
    if not _is_relative_to(resolved, root):
        _raise(
            "path_outside_project_root",
            "Metadata path is outside the project root.",
            field=field,
            path=str(resolved),
            project_root=str(root),
        )


def _file_name_from_path(
    project_root: Path,
    value: Any,
    *,
    field: str,
) -> str:
    path = _path_value(value, field=field)
    _validate_absolute_under_project(project_root, path, field=field)
    return path.name


def _ensure_source_document(payload: dict) -> dict:
    source_document = payload.get("source_document")
    if not isinstance(source_document, dict):
        source_document = {}
        payload["source_document"] = source_document
    return source_document


def _set_source_document_file_name(
    payload: dict,
    file_name: str,
    *,
    only_when_unknown: bool,
) -> None:
    source_document = _ensure_source_document(payload)
    if only_when_unknown and source_document.get("file_name"):
        return
    source_document["file_name"] = file_name


def _convert_document_identity(
    payload: dict,
    changes: list[dict],
    *,
    project_root: Path,
) -> None:
    if "model_path" in payload:
        file_name = _file_name_from_path(
            project_root,
            payload.pop("model_path"),
            field="$.model_path",
        )
        _set_source_document_file_name(
            payload,
            file_name,
            only_when_unknown=False,
        )
        _record_change(changes, "$.model_path", "moved_to_source_document_file_name")

    document = payload.get("document")
    if isinstance(document, dict) and "path" in document:
        file_name = _file_name_from_path(
            project_root,
            document.pop("path"),
            field="$.document.path",
        )
        _set_source_document_file_name(
            payload,
            file_name,
            only_when_unknown=True,
        )
        _record_change(changes, "$.document.path", "moved_to_source_document_file_name")


def _ref_from_path(project_root: Path, value: Any, *, field: str) -> str:
    path = _path_value(value, field=field)
    try:
        return dam.ref_from_project_path(project_root, path)
    except dam.DirectorActorMetadataError as ex:
        if ex.code == "path_outside_project_root":
            data = dict(ex.data)
            data["field"] = field
            raise dam.DirectorActorMetadataError(ex.code, ex.message, **data) from ex
        raise


def _convert_ref_field(
    payload: dict,
    changes: list[dict],
    *,
    project_root: Path,
    old_key: str,
    new_key: str,
    field: str,
) -> None:
    if old_key not in payload:
        return
    old_value = payload.pop(old_key)
    payload[new_key] = _ref_from_path(project_root, old_value, field=field)
    _record_change(changes, field, f"renamed_to_{new_key}")


def _convert_indexed_ref_fields(
    payload: dict,
    changes: list[dict],
    *,
    project_root: Path,
    collection_key: str,
    old_key: str,
    new_key: str,
    field_prefix: str,
) -> None:
    collection = payload.get(collection_key)
    if not isinstance(collection, list):
        return
    for index, item in enumerate(collection):
        if not isinstance(item, dict):
            continue
        _convert_ref_field(
            item,
            changes,
            project_root=project_root,
            old_key=old_key,
            new_key=new_key,
            field=f"{field_prefix}[{index}].{old_key}",
        )


def convert_v1_payload(
    payload: dict,
    *,
    project_root: Path,
    source_path: Path,
) -> tuple[dict, list[dict]]:
    if not isinstance(payload, dict):
        _raise("metadata_payload_invalid", "Metadata payload root must be an object.")
    if payload.get("schema_version") != 1:
        _raise(
            "metadata_schema_unsupported",
            "Only Director actor metadata schema_version 1 can be migrated.",
            schema_version=payload.get("schema_version"),
            expected_schema_version=1,
        )

    root = Path(project_root).resolve()
    source = Path(source_path)
    kind = _classify_kind(payload, source)
    converted = copy.deepcopy(payload)
    changes: list[dict] = []
    converted["schema_version"] = dam.SCHEMA_VERSION
    converted["metadata_kind"] = kind
    _record_change(changes, "$.schema_version", "set_to_v2")
    _record_change(changes, "$.metadata_kind", "set")

    _convert_document_identity(converted, changes, project_root=root)
    _convert_ref_field(
        converted,
        changes,
        project_root=root,
        old_key="source_snapshot_path",
        new_key="source_snapshot_ref",
        field="$.source_snapshot_path",
    )
    _convert_ref_field(
        converted,
        changes,
        project_root=root,
        old_key="exemplar_selection_snapshot_path",
        new_key="exemplar_selection_snapshot_ref",
        field="$.exemplar_selection_snapshot_path",
    )
    acceptance = converted.get("acceptance")
    if isinstance(acceptance, dict):
        _convert_ref_field(
            acceptance,
            changes,
            project_root=root,
            old_key="accepted_selection_snapshot_path",
            new_key="accepted_selection_snapshot_ref",
            field="$.acceptance.accepted_selection_snapshot_path",
        )
    _convert_indexed_ref_fields(
        converted,
        changes,
        project_root=root,
        collection_key="subsets",
        old_key="path",
        new_key="ref",
        field_prefix="$.subsets",
    )
    _convert_indexed_ref_fields(
        converted,
        changes,
        project_root=root,
        collection_key="band_sets",
        old_key="path",
        new_key="ref",
        field_prefix="$.band_sets",
    )

    dam.validate_loaded_metadata(converted, expected_kind=kind)
    return converted, changes


def _require_arguments(arguments: dict) -> tuple[Path, list[Path], bool, str]:
    if not isinstance(arguments, dict):
        _raise("migration_arguments_invalid", "Migration arguments must be an object.")
    project_root_value = arguments.get("project_root")
    if not isinstance(project_root_value, (str, Path)) or not str(project_root_value):
        _raise(
            "migration_arguments_invalid",
            "Migration requires a project_root string.",
            field="project_root",
        )
    project_root = Path(project_root_value)
    files = arguments.get("files")
    if not isinstance(files, list) or not files:
        _raise(
            "migration_arguments_invalid",
            "Migration requires a non-empty files list.",
            field="files",
        )
    paths: list[Path] = []
    for index, item in enumerate(files):
        if not isinstance(item, (str, Path)) or not str(item):
            _raise(
                "migration_arguments_invalid",
                "Migration file entries must be non-empty strings.",
                field=f"files[{index}]",
            )
        path = Path(item)
        if not path.is_absolute():
            path = project_root / path
        paths.append(path)
    write = bool(arguments.get("write", False))
    suffix = arguments.get("suffix", ".v2")
    if not isinstance(suffix, str):
        _raise(
            "migration_arguments_invalid",
            "Migration suffix must be a string.",
            field="suffix",
        )
    return project_root, paths, write, suffix


def _output_path(source_path: Path, suffix: str) -> Path:
    if suffix == "":
        return source_path
    return source_path.with_name(f"{source_path.stem}{suffix}{source_path.suffix}")


def migrate_actor_metadata_v2(arguments: dict) -> dict:
    project_root, files, write, suffix = _require_arguments(arguments)
    root = project_root.resolve()
    report_files: list[dict] = []
    for source_path in files:
        text = source_path.read_text(encoding="utf-8")
        payload = json.loads(text)
        converted, changes = convert_v1_payload(
            payload,
            project_root=root,
            source_path=source_path,
        )
        output_path = _output_path(source_path, suffix)
        if write:
            output_path.write_text(
                json.dumps(converted, indent=2) + "\n",
                encoding="utf-8",
            )
        report_files.append(
            {
                "source_path": str(source_path),
                "output_path": str(output_path),
                "metadata_kind": converted["metadata_kind"],
                "changes": changes,
            }
        )
    return {
        "state": "complete",
        "project_root": str(root),
        "write": write,
        "files": report_files,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate explicit Director actor metadata v1 JSON files to v2 refs."
    )
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--file", action="append", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--suffix", default=".v2")
    args = parser.parse_args(argv)
    report = migrate_actor_metadata_v2(
        {
            "project_root": args.project_root,
            "files": args.file,
            "write": args.write,
            "suffix": args.suffix,
        }
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
