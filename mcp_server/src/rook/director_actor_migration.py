from __future__ import annotations

import argparse
import copy
import hashlib
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
    root = project_root.resolve()
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
            path = root / path
        resolved_path = path.resolve()
        if not _is_relative_to(resolved_path, root):
            _raise(
                "path_outside_project_root",
                "Migration file is outside the project root.",
                field=f"$.files[{index}]",
                path=str(resolved_path),
                project_root=str(root),
            )
        paths.append(resolved_path)
    write_value = arguments.get("write", False)
    if not isinstance(write_value, bool):
        _raise(
            "metadata_invalid",
            "Migration write must be a boolean.",
            field="write",
        )
    write = write_value
    suffix = arguments.get("suffix", ".v2")
    if not isinstance(suffix, str):
        _raise(
            "migration_arguments_invalid",
            "Migration suffix must be a string.",
            field="suffix",
        )
    if suffix == "":
        _raise(
            "metadata_invalid",
            "Migration suffix must be non-empty.",
            field="suffix",
        )
    return project_root, paths, write, suffix


def _output_path(source_path: Path, suffix: str) -> Path:
    return source_path.with_name(f"{source_path.stem}{suffix}{source_path.suffix}")


_KNOWN_REF_FIELDS_BY_KIND: dict[str, tuple[tuple[str, str], ...]] = {
    dam.KIND_ACTOR_SET: (
        ("source_snapshot_ref", dam.KIND_SELECTION_SNAPSHOT),
        ("source_occurrence_snapshot_ref", dam.KIND_SELECTION_SNAPSHOT),
    ),
    dam.KIND_ACTOR_SUBSET: (),
    dam.KIND_ACTOR_GROUPING: (
        ("exemplar_selection_snapshot_ref", dam.KIND_SELECTION_SNAPSHOT),
    ),
    dam.KIND_SELECTION_SNAPSHOT: (),
}


def _require_string_id(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        _raise(
            "metadata_id_required",
            f"Metadata payload requires a non-empty {key}.",
            field=key,
        )
    return value


def _semantic_id(payload: dict) -> str:
    for key in ("actor_set_id", "subset_id", "band_set_id", "snapshot_id", "entry_id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _storage_identity_for_payload(payload: dict) -> dict:
    kind = payload.get("metadata_kind")
    if kind == dam.KIND_ACTOR_SET:
        return {
            "kind": dam.STORAGE_KIND_ACTOR_SET,
            "actor_set_id": _require_string_id(payload, "actor_set_id"),
        }
    if kind == dam.KIND_SELECTION_SNAPSHOT:
        snapshot_id = payload.get("snapshot_id")
        if not isinstance(snapshot_id, str) or not snapshot_id:
            snapshot_id = _require_string_id(payload, "entry_id")
        return {
            "kind": dam.STORAGE_KIND_SELECTION_SNAPSHOT,
            "snapshot_id": snapshot_id,
        }
    if kind == dam.KIND_ACTOR_SUBSET:
        return {
            "kind": dam.STORAGE_KIND_SUBSET,
            "actor_set_id": _require_string_id(payload, "parent_actor_set_id"),
            "subset_id": _require_string_id(payload, "subset_id"),
        }
    if kind == dam.KIND_ACTOR_GROUPING:
        return {
            "kind": dam.STORAGE_KIND_GROUPING,
            "actor_set_id": _require_string_id(payload, "parent_actor_set_id"),
            "subset_id": _require_string_id(payload, "parent_subset_id"),
            "band_set_id": _require_string_id(payload, "band_set_id"),
        }
    _raise(
        "metadata_kind_mismatch",
        "Unsupported Director actor metadata kind for migration.",
        metadata_kind=kind,
    )


def _collection_refs(
    payload: dict,
    collection_key: str,
    expected_kind: str,
) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    collection = payload.get(collection_key)
    if not isinstance(collection, list):
        return refs
    for item in collection:
        if not isinstance(item, dict):
            continue
        ref = item.get("ref")
        if isinstance(ref, str) and ref:
            refs.append((ref, expected_kind))
    return refs


def _known_link_refs(payload: dict) -> list[tuple[str, str]]:
    kind = payload.get("metadata_kind")
    refs: list[tuple[str, str]] = []
    for key, expected_kind in _KNOWN_REF_FIELDS_BY_KIND.get(kind, ()):
        value = payload.get(key)
        if isinstance(value, str) and value:
            refs.append((value, expected_kind))
    if kind == dam.KIND_ACTOR_SET:
        refs.extend(_collection_refs(payload, "subsets", dam.KIND_ACTOR_SUBSET))
    elif kind == dam.KIND_ACTOR_SUBSET:
        acceptance = payload.get("acceptance")
        if isinstance(acceptance, dict):
            value = acceptance.get("accepted_selection_snapshot_ref")
            if isinstance(value, str) and value:
                refs.append((value, dam.KIND_SELECTION_SNAPSHOT))
        refs.extend(_collection_refs(payload, "band_sets", dam.KIND_ACTOR_GROUPING))
    return refs


def _is_legacy_ref(ref: str) -> bool:
    return dam.classify_metadata_ref(ref) == "legacy"


def _load_legacy_payload(
    project_root: Path,
    ref: str,
    *,
    expected_kind: str,
) -> dict:
    if not _is_legacy_ref(ref):
        _raise(
            "metadata_ref_prefix_unsupported",
            "Storage-ref migration requires legacy Director actor metadata refs.",
            ref=ref,
            allowed_prefixes=[dam.LEGACY_REF_PREFIX],
        )
    return dam.load_metadata_ref(project_root, ref, expected_kind=expected_kind)


def _rewrite_ref(value: Any, ref_map: dict[str, str]) -> Any:
    if isinstance(value, str) and value in ref_map:
        return ref_map[value]
    return value


def _rewrite_known_refs(payload: dict, ref_map: dict[str, str]) -> dict:
    converted = copy.deepcopy(payload)
    for key in (
        "source_snapshot_ref",
        "source_occurrence_snapshot_ref",
        "exemplar_selection_snapshot_ref",
    ):
        if key in converted:
            converted[key] = _rewrite_ref(converted[key], ref_map)
    acceptance = converted.get("acceptance")
    if isinstance(acceptance, dict) and "accepted_selection_snapshot_ref" in acceptance:
        acceptance["accepted_selection_snapshot_ref"] = _rewrite_ref(
            acceptance["accepted_selection_snapshot_ref"],
            ref_map,
        )
    for collection_key in ("subsets", "band_sets"):
        collection = converted.get(collection_key)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if isinstance(item, dict) and "ref" in item:
                item["ref"] = _rewrite_ref(item["ref"], ref_map)
    return converted


def _canonical_json(payload: dict) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _preflight_canonical_payload(
    project_root: Path,
    ref: str,
    payload: dict,
    *,
    write: bool,
) -> str:
    path = dam.resolve_metadata_ref(project_root, ref)
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return "conflicted"
        if not isinstance(existing, dict):
            return "conflicted"
        if existing.get("storage_identity") != payload.get("storage_identity"):
            return "conflicted"
        if _canonical_json(existing) != _canonical_json(payload):
            return "conflicted"
        return "reused"
    return "created" if write else "planned"


def _write_new_canonical_payload(project_root: Path, ref: str, payload: dict) -> None:
    path = dam.resolve_metadata_ref(project_root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _report_ref(mappings: list[dict]) -> str:
    report_identity = [
        {
            "old_ref": entry["old_ref"],
            "new_ref": entry["new_ref"],
            "metadata_kind": entry["metadata_kind"],
            "semantic_id": entry["semantic_id"],
        }
        for entry in sorted(
            mappings,
            key=lambda item: (
                item["old_ref"],
                item["new_ref"],
                item["metadata_kind"],
                item["semantic_id"],
            ),
        )
    ]
    digest = hashlib.sha256(
        json.dumps(
            report_identity,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()[:12]
    return f".rook/director/v2/migration_reports/mig_{digest}.json"


def _mark_intra_run_ref_conflicts(
    mappings: list[dict],
    canonical_payloads: dict[str, dict],
) -> None:
    mappings_by_new_ref: dict[str, list[dict]] = {}
    for mapping in mappings:
        mappings_by_new_ref.setdefault(mapping["new_ref"], []).append(mapping)
    for grouped_mappings in mappings_by_new_ref.values():
        if len(grouped_mappings) < 2:
            continue
        canonical_payload_json = {
            _canonical_json(canonical_payloads[mapping["old_ref"]])
            for mapping in grouped_mappings
        }
        if len(canonical_payload_json) == 1:
            continue
        for mapping in grouped_mappings:
            mapping["status"] = "conflicted"


def _require_storage_migration_arguments(
    arguments: dict,
) -> tuple[Path, list[str], bool, bool]:
    if not isinstance(arguments, dict):
        _raise("migration_arguments_invalid", "Migration arguments must be an object.")
    project_root_value = arguments.get("project_root")
    if not isinstance(project_root_value, (str, Path)) or not str(project_root_value):
        _raise(
            "migration_arguments_invalid",
            "Migration requires a project_root string.",
            field="project_root",
        )
    project_root = Path(project_root_value).resolve()
    actor_set_refs = arguments.get("actor_set_refs")
    if not isinstance(actor_set_refs, list) or not actor_set_refs:
        _raise(
            "migration_arguments_invalid",
            "Storage-ref migration requires a non-empty actor_set_refs list.",
            field="actor_set_refs",
        )
    refs: list[str] = []
    for index, item in enumerate(actor_set_refs):
        if not isinstance(item, str) or not item:
            _raise(
                "migration_arguments_invalid",
                "Actor set ref entries must be non-empty strings.",
                field=f"actor_set_refs[{index}]",
            )
        refs.append(dam.validate_metadata_ref(item))
    write = arguments.get("write", False)
    if not isinstance(write, bool):
        _raise("metadata_invalid", "Migration write must be a boolean.", field="write")
    write_report = arguments.get("write_report", False)
    if not isinstance(write_report, bool):
        _raise(
            "metadata_invalid",
            "Migration write_report must be a boolean.",
            field="write_report",
        )
    return project_root, refs, write, write_report


def _reachable_legacy_payloads(
    project_root: Path,
    actor_set_refs: list[str],
) -> dict[str, dict]:
    payloads: dict[str, dict] = {}
    expected_kinds: dict[str, str] = {
        ref: dam.KIND_ACTOR_SET for ref in sorted(set(actor_set_refs))
    }
    queue = sorted(expected_kinds)
    while queue:
        ref = queue.pop(0)
        expected_kind = expected_kinds[ref]
        if ref in payloads:
            continue
        payload = _load_legacy_payload(project_root, ref, expected_kind=expected_kind)
        payloads[ref] = payload
        for linked_ref, linked_kind in sorted(_known_link_refs(payload)):
            if not _is_legacy_ref(linked_ref):
                continue
            previous_kind = expected_kinds.get(linked_ref)
            if previous_kind is not None and previous_kind != linked_kind:
                _raise(
                    "metadata_kind_mismatch",
                    "Director metadata ref was linked with conflicting kinds.",
                    ref=linked_ref,
                    metadata_kind=previous_kind,
                    expected_kind=linked_kind,
                )
            expected_kinds[linked_ref] = linked_kind
            if linked_ref not in payloads and linked_ref not in queue:
                queue.append(linked_ref)
                queue.sort()
    return payloads


def migrate_actor_metadata_storage_refs_v2(arguments: dict) -> dict:
    project_root, actor_set_refs, write, write_report = (
        _require_storage_migration_arguments(arguments)
    )
    payloads_by_old_ref = _reachable_legacy_payloads(project_root, actor_set_refs)
    identities_by_old_ref: dict[str, dict] = {}
    ref_map: dict[str, str] = {}
    for old_ref, payload in sorted(payloads_by_old_ref.items()):
        identity = _storage_identity_for_payload(payload)
        identities_by_old_ref[old_ref] = identity
        ref_map[old_ref] = dam.canonical_ref_for_storage_identity(identity)

    canonical_payloads: dict[str, dict] = {}
    mappings: list[dict] = []
    for old_ref, payload in sorted(payloads_by_old_ref.items()):
        identity = identities_by_old_ref[old_ref]
        new_ref = ref_map[old_ref]
        canonical_payload = _rewrite_known_refs(payload, ref_map)
        canonical_payload["storage_version"] = dam.STORAGE_VERSION
        canonical_payload["ref_protocol"] = dam.REF_PROTOCOL
        canonical_payload["storage_identity"] = copy.deepcopy(identity)
        dam.validate_loaded_metadata_for_ref(
            canonical_payload,
            ref=new_ref,
            expected_kind=canonical_payload["metadata_kind"],
        )
        canonical_payloads[old_ref] = canonical_payload
        mappings.append(
            {
                "old_ref": old_ref,
                "new_ref": new_ref,
                "metadata_kind": canonical_payload["metadata_kind"],
                "semantic_id": _semantic_id(canonical_payload),
                "status": "pending",
            }
        )

    statuses: dict[str, str] = {}
    for mapping in mappings:
        old_ref = mapping["old_ref"]
        status = _preflight_canonical_payload(
            project_root,
            mapping["new_ref"],
            canonical_payloads[old_ref],
            write=write,
        )
        mapping["status"] = status
        statuses[old_ref] = status
    _mark_intra_run_ref_conflicts(mappings, canonical_payloads)
    statuses = {mapping["old_ref"]: mapping["status"] for mapping in mappings}

    state = (
        "failed"
        if any(status == "conflicted" for status in statuses.values())
        else "complete"
    )
    if state == "failed":
        for mapping in mappings:
            if mapping["status"] == "created":
                mapping["status"] = "planned"
    elif write:
        written_refs: set[str] = set()
        for mapping in mappings:
            if mapping["status"] == "created":
                if mapping["new_ref"] in written_refs:
                    continue
                _write_new_canonical_payload(
                    project_root,
                    mapping["new_ref"],
                    canonical_payloads[mapping["old_ref"]],
                )
                written_refs.add(mapping["new_ref"])
    report_ref = _report_ref(mappings)
    report = {
        "schema_version": dam.SCHEMA_VERSION,
        "state": state,
        "project_root": str(project_root),
        "write": write,
        "write_report": write_report,
        "actor_set_refs": sorted(actor_set_refs),
        "report_ref": report_ref,
        "mappings": sorted(
            mappings,
            key=lambda item: (
                item["old_ref"],
                item["new_ref"],
                item["metadata_kind"],
                item["semantic_id"],
            ),
        ),
    }
    if write_report:
        report_path = dam.resolve_metadata_ref(project_root, report_ref)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def migrate_actor_metadata_v2(arguments: dict) -> dict:
    project_root, files, write, suffix = _require_arguments(arguments)
    root = project_root.resolve()
    report_files: list[dict] = []
    converted_files: list[tuple[Path, dict]] = []
    for source_path in files:
        text = source_path.read_text(encoding="utf-8")
        payload = json.loads(text)
        converted, changes = convert_v1_payload(
            payload,
            project_root=root,
            source_path=source_path,
        )
        output_path = _output_path(source_path, suffix)
        converted_files.append((output_path, converted))
        report_files.append(
            {
                "source_path": str(source_path),
                "output_path": str(output_path),
                "metadata_kind": converted["metadata_kind"],
                "changes": changes,
            }
        )
    if write:
        for output_path, converted in converted_files:
            output_path.write_text(
                json.dumps(converted, indent=2) + "\n",
                encoding="utf-8",
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
