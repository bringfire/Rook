from __future__ import annotations

import copy
import datetime
import json
import re
import uuid
from pathlib import Path
from typing import Any

from .bridge import call_rhino

SCHEMA_VERSION = 2
KIND_ACTOR_SET = "director_actor_set"
KIND_ACTOR_SUBSET = "director_actor_subset"
KIND_ACTOR_GROUPING = "director_actor_grouping"
KIND_SELECTION_SNAPSHOT = "director_selection_snapshot"

METADATA_KINDS = {
    KIND_ACTOR_SET,
    KIND_ACTOR_SUBSET,
    KIND_ACTOR_GROUPING,
    KIND_SELECTION_SNAPSHOT,
}

LEGACY_DURABLE_PATH_FIELDS = {
    "model_path",
    "source_snapshot_path",
    "path",
    "accepted_selection_snapshot_path",
    "exemplar_selection_snapshot_path",
}

_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")


class DirectorActorMetadataError(Exception):
    def __init__(self, code: str, message: str, **data: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = dict(data)

    def to_data(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.data}


def _raise(code: str, message: str, **data: Any) -> None:
    raise DirectorActorMetadataError(code, message, **data)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validate_metadata_ref(ref: str) -> str:
    if not isinstance(ref, str) or ref == "":
        _raise("invalid_metadata_ref", "Metadata ref must be a non-empty string.")
    if "\\" in ref:
        _raise("invalid_metadata_ref", "Metadata ref must use forward slashes.")
    if ref.startswith("/") or ref.startswith("//") or _DRIVE_PREFIX_RE.match(ref):
        _raise("invalid_metadata_ref", "Metadata ref must be project-relative.")
    if not ref.startswith(".rook/"):
        _raise("invalid_metadata_ref", "Metadata ref must start with '.rook/'.")
    segments = ref.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        _raise("invalid_metadata_ref", "Metadata ref contains an invalid path segment.")
    return ref


def resolve_metadata_ref(project_root: Path, ref: str) -> Path:
    valid_ref = validate_metadata_ref(ref)
    root = Path(project_root).resolve()
    resolved = (root / Path(valid_ref)).resolve()
    if not _is_relative_to(resolved, root):
        _raise(
            "metadata_ref_escape",
            "Metadata ref resolves outside the project root.",
            ref=valid_ref,
        )
    return resolved


def ref_from_project_path(project_root: Path, path: Path) -> str:
    root = Path(project_root).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as ex:
        raise DirectorActorMetadataError(
            "path_outside_project_root",
            "Metadata path is outside the project root.",
            path=str(resolved),
            project_root=str(root),
        ) from ex
    return validate_metadata_ref("/".join(relative.parts))


def _legacy_field_path(parent: str, key: str) -> str:
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        return f"{parent}.{key}"
    return f"{parent}[{key!r}]"


def _reject_legacy_path_fields(value: Any, field_path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            child_path = _legacy_field_path(field_path, key_text)
            if key in LEGACY_DURABLE_PATH_FIELDS:
                _raise(
                    "legacy_path_field_present",
                    "Metadata contains a legacy durable path field.",
                    field_path=child_path,
                )
            _reject_legacy_path_fields(item, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_legacy_path_fields(item, f"{field_path}[{index}]")


def _validate_ref_fields(value: Any, field_path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            child_path = _legacy_field_path(field_path, key_text)
            if key_text == "ref" or key_text.endswith("_ref"):
                try:
                    validate_metadata_ref(item)
                except DirectorActorMetadataError as ex:
                    raise DirectorActorMetadataError(
                        ex.code,
                        ex.message,
                        field_path=child_path,
                        ref=item,
                    ) from ex
            _validate_ref_fields(item, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_ref_fields(item, f"{field_path}[{index}]")


def _reject_generated_ref_input_fields(value: Any, field_path: str = "$") -> None:
    generated_ref_keys = {
        "source_snapshot_ref",
        "accepted_selection_snapshot_ref",
        "exemplar_selection_snapshot_ref",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            child_path = _legacy_field_path(field_path, key_text)
            if key_text in generated_ref_keys or (
                key_text == "ref"
                and (
                    ".actor_set.subsets[" in field_path
                    or ".band_sets[" in field_path
                )
            ):
                _raise(
                    "generated_ref_field_present",
                    "Director metadata writer generates durable refs from semantic IDs.",
                    field_path=child_path,
                )
            _reject_generated_ref_input_fields(item, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_generated_ref_input_fields(item, f"{field_path}[{index}]")


def validate_loaded_metadata(payload: dict, *, expected_kind: str) -> dict:
    if not isinstance(payload, dict):
        _raise("metadata_payload_invalid", "Metadata payload root must be an object.")
    if payload.get("schema_version") != SCHEMA_VERSION:
        _raise(
            "metadata_schema_unsupported",
            "Only Director actor metadata schema_version 2 is supported.",
            schema_version=payload.get("schema_version"),
            expected_schema_version=SCHEMA_VERSION,
        )
    if expected_kind not in METADATA_KINDS:
        _raise(
            "metadata_kind_mismatch",
            "Expected metadata kind is not supported.",
            expected_kind=expected_kind,
            allowed_metadata_kinds=sorted(METADATA_KINDS),
        )
    metadata_kind = payload.get("metadata_kind")
    if metadata_kind not in METADATA_KINDS or metadata_kind != expected_kind:
        _raise(
            "metadata_kind_mismatch",
            "Metadata kind does not match the expected kind.",
            metadata_kind=metadata_kind,
            expected_kind=expected_kind,
            allowed_metadata_kinds=sorted(METADATA_KINDS),
        )
    _reject_legacy_path_fields(payload)
    _validate_ref_fields(payload)
    return payload


def load_metadata_ref(project_root: Path, ref: str, *, expected_kind: str) -> dict:
    path = resolve_metadata_ref(project_root, ref)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as ex:
        raise DirectorActorMetadataError(
            "metadata_ref_not_found",
            "Metadata ref does not exist.",
            ref=validate_metadata_ref(ref),
        ) from ex
    except UnicodeDecodeError as ex:
        raise DirectorActorMetadataError(
            "metadata_text_decode_failed",
            "Metadata ref could not be decoded as UTF-8 text.",
            ref=validate_metadata_ref(ref),
        ) from ex
    except OSError as ex:
        raise DirectorActorMetadataError(
            "metadata_ref_read_failed",
            "Metadata ref could not be read.",
            ref=validate_metadata_ref(ref),
        ) from ex
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as ex:
        raise DirectorActorMetadataError(
            "metadata_json_invalid",
            "Metadata ref did not contain valid JSON.",
            ref=validate_metadata_ref(ref),
        ) from ex
    return validate_loaded_metadata(payload, expected_kind=expected_kind)


async def resolve_active_project_root(
    *, call_native=call_rhino, port=None
) -> tuple[Path, dict[str, Any]]:
    document_response = await call_native("/document", port=port)
    document = document_response
    if (
        isinstance(document_response, dict)
        and document_response.get("success") is True
        and "data" in document_response
    ):
        document = document_response.get("data")
    if not isinstance(document, dict):
        _raise(
            "document_path_required",
            "Active Rhino document metadata was not returned as an object.",
        )

    document_path_text = document.get("path")
    if not isinstance(document_path_text, str) or not document_path_text.strip():
        _raise(
            "document_path_required",
            "Save the active Rhino document before writing Director metadata.",
        )

    document_path = Path(document_path_text).expanduser()
    if document_path.suffix.lower() != ".3dm":
        _raise(
            "document_path_required",
            "Active Rhino document path must point to a saved .3dm file.",
            document_path=document_path_text,
        )

    source_document = {
        "file_name": document_path.name,
    }
    document_name = document.get("name")
    if isinstance(document_name, str) and document_name:
        source_document["name"] = document_name

    return document_path.parent.resolve(), source_document


def _metadata_timestamp_utc() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _require_text_id(
    payload: dict[str, Any],
    key: str,
    *,
    field_path: str | None = None,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        _raise(
            "metadata_id_required",
            f"Metadata payload requires a non-empty {key}.",
            field=key,
            field_path=field_path or key,
        )
    return value


def _optional_list(
    payload: dict[str, Any],
    key: str,
    *,
    field_path: str,
) -> list[Any]:
    if key not in payload:
        return []
    value = payload[key]
    if not isinstance(value, list):
        _raise(
            "metadata_collection_invalid",
            "Director metadata collection field must be a list.",
            field=key,
            field_path=field_path,
        )
    return value


def _snapshot_ref(snapshot_id: str) -> str:
    return (
        ".rook/director_planning/selection_snapshots/"
        f"{snapshot_id}.json"
    )


def _actor_set_ref(actor_set_id: str) -> str:
    return f".rook/director_planning/actor_sets/{actor_set_id}.json"


def _subset_ref(actor_set_id: str, subset_id: str) -> str:
    return (
        ".rook/director_planning/actor_sets/"
        f"{actor_set_id}_subsets/{subset_id}.json"
    )


def _grouping_ref(actor_set_id: str, subset_id: str, band_set_id: str) -> str:
    return (
        ".rook/director_planning/actor_sets/"
        f"{actor_set_id}_subsets/{subset_id}_band_sets/{band_set_id}.json"
    )


def _normalize_common_metadata(
    payload: dict[str, Any],
    *,
    metadata_kind: str,
    source_document: dict[str, Any],
    generated_at_utc: str,
) -> dict[str, Any]:
    normalized = copy.deepcopy(payload)
    normalized["schema_version"] = SCHEMA_VERSION
    normalized["metadata_kind"] = metadata_kind
    normalized["source_document"] = copy.deepcopy(source_document)
    normalized["generated_at_utc"] = generated_at_utc
    return normalized


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def _written_entry(project_root: Path, ref: str, *, metadata_kind: str) -> dict[str, str]:
    return {
        "metadata_kind": metadata_kind,
        "ref": validate_metadata_ref(ref),
        "resolved_path": str(resolve_metadata_ref(project_root, ref)),
    }


def _remember_unique_id(
    seen: dict[str, str],
    *,
    field: str,
    value: str,
    field_path: str,
) -> None:
    previous_field_path = seen.get(value)
    if previous_field_path is not None:
        _raise(
            "duplicate_metadata_id",
            "Director metadata bundle contains a duplicate id.",
            field=field,
            value=value,
            field_path=field_path,
            previous_field_path=previous_field_path,
        )
    seen[value] = field_path


def _require_snapshot_ref(
    snapshot_refs: dict[str, str],
    snapshot_id: Any,
    *,
    field_path: str,
) -> str:
    if not isinstance(snapshot_id, str) or not snapshot_id:
        _raise(
            "metadata_id_required",
            "Selection snapshot link requires a non-empty snapshot id.",
            field_path=field_path,
        )
    ref = snapshot_refs.get(snapshot_id)
    if ref is None:
        _raise(
            "metadata_ref_target_missing",
            "Selection snapshot link does not match a supplied snapshot.",
            field_path=field_path,
            target_id=snapshot_id,
            target_kind=KIND_SELECTION_SNAPSHOT,
        )
    return ref


def _require_parent_actor_set(
    parent_actor_set_id: Any,
    actor_set_id: str,
    *,
    field_path: str,
) -> str:
    if parent_actor_set_id is None:
        return actor_set_id
    if not isinstance(parent_actor_set_id, str) or not parent_actor_set_id:
        _raise(
            "metadata_id_required",
            "Parent actor set id must be a non-empty string.",
            field_path=field_path,
        )
    if parent_actor_set_id != actor_set_id:
        _raise(
            "metadata_parent_mismatch",
            "Parent actor set id does not match the supplied actor set.",
            field_path=field_path,
            parent_actor_set_id=parent_actor_set_id,
            actor_set_id=actor_set_id,
        )
    return parent_actor_set_id


def _require_parent_subset(
    subset_refs: dict[str, str],
    parent_subset_id: Any,
    *,
    field_path: str,
) -> str:
    if not isinstance(parent_subset_id, str) or not parent_subset_id:
        _raise(
            "metadata_id_required",
            "Grouping payload requires a non-empty parent_subset_id.",
            field_path=field_path,
        )
    if parent_subset_id not in subset_refs:
        _raise(
            "metadata_ref_target_missing",
            "Grouping parent_subset_id does not match a supplied subset.",
            field_path=field_path,
            target_id=parent_subset_id,
            target_kind=KIND_ACTOR_SUBSET,
        )
    return parent_subset_id


def _preflight_payloads(
    project_root: Path,
    payloads: list[tuple[str, str, dict[str, Any]]],
) -> list[tuple[Path, dict[str, Any]]]:
    resolved_payloads: list[tuple[Path, dict[str, Any]]] = []
    refs_by_resolved_path: dict[Path, str] = {}
    for ref, expected_kind, payload in payloads:
        validate_metadata_ref(ref)
        resolved_path = resolve_metadata_ref(project_root, ref)
        previous_ref = refs_by_resolved_path.get(resolved_path)
        if previous_ref is not None:
            _raise(
                "metadata_ref_collision",
                "Multiple Director metadata payloads resolve to the same path.",
                ref=ref,
                previous_ref=previous_ref,
                resolved_path=str(resolved_path),
            )
        refs_by_resolved_path[resolved_path] = ref
        validate_loaded_metadata(payload, expected_kind=expected_kind)
        resolved_payloads.append((resolved_path, payload))
    return resolved_payloads


async def write_actor_metadata_bundle_v2(
    arguments: dict[str, Any], *, call_native=call_rhino, port=None
) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        _raise("metadata_bundle_invalid", "Director metadata bundle must be an object.")
    _reject_legacy_path_fields(arguments)
    _reject_generated_ref_input_fields(arguments)
    _validate_ref_fields(arguments)

    project_root, source_document = await resolve_active_project_root(
        call_native=call_native,
        port=port,
    )
    generated_at_utc = _metadata_timestamp_utc()

    actor_set_input = arguments.get("actor_set")
    if not isinstance(actor_set_input, dict):
        _raise("metadata_bundle_invalid", "Director metadata bundle requires actor_set.")
    actor_set_id = _require_text_id(
        actor_set_input,
        "actor_set_id",
        field_path="$.actor_set.actor_set_id",
    )
    actor_ref = _actor_set_ref(actor_set_id)

    snapshot_refs: dict[str, str] = {}
    snapshot_ids: dict[str, str] = {}
    snapshot_payloads: list[tuple[str, dict[str, Any]]] = []
    selection_snapshots = _optional_list(
        arguments,
        "selection_snapshots",
        field_path="$.selection_snapshots",
    )
    for snapshot_index, snapshot_input in enumerate(selection_snapshots):
        if not isinstance(snapshot_input, dict):
            _raise(
                "metadata_bundle_invalid",
                "Selection snapshot entries must be objects.",
            )
        snapshot_field_path = f"$.selection_snapshots[{snapshot_index}].snapshot_id"
        snapshot_id = _require_text_id(
            snapshot_input,
            "snapshot_id",
            field_path=snapshot_field_path,
        )
        _remember_unique_id(
            snapshot_ids,
            field="snapshot_id",
            value=snapshot_id,
            field_path=snapshot_field_path,
        )
        ref = _snapshot_ref(snapshot_id)
        snapshot_refs[snapshot_id] = ref
        snapshot = _normalize_common_metadata(
            snapshot_input,
            metadata_kind=KIND_SELECTION_SNAPSHOT,
            source_document=source_document,
            generated_at_utc=generated_at_utc,
        )
        snapshot_payloads.append((ref, snapshot))

    subset_refs: dict[str, str] = {}
    subset_ids: dict[str, str] = {}
    subset_payloads: list[tuple[str, dict[str, Any]]] = []
    subsets = _optional_list(arguments, "subsets", field_path="$.subsets")
    for subset_index, subset_input in enumerate(subsets):
        if not isinstance(subset_input, dict):
            _raise("metadata_bundle_invalid", "Subset entries must be objects.")
        subset_field_path = f"$.subsets[{subset_index}].subset_id"
        subset_id = _require_text_id(
            subset_input,
            "subset_id",
            field_path=subset_field_path,
        )
        _remember_unique_id(
            subset_ids,
            field="subset_id",
            value=subset_id,
            field_path=subset_field_path,
        )
        parent_actor_set_id = _require_parent_actor_set(
            subset_input.get("parent_actor_set_id"),
            actor_set_id,
            field_path=f"$.subsets[{subset_index}].parent_actor_set_id",
        )
        ref = _subset_ref(parent_actor_set_id, subset_id)
        subset_refs[subset_id] = ref
        subset = _normalize_common_metadata(
            subset_input,
            metadata_kind=KIND_ACTOR_SUBSET,
            source_document=source_document,
            generated_at_utc=generated_at_utc,
        )
        acceptance = subset.get("acceptance")
        if isinstance(acceptance, dict):
            accepted_key = "accepted_selection_snapshot_id"
            if accepted_key in acceptance:
                accepted_snapshot_id = acceptance.pop(accepted_key)
                acceptance["accepted_selection_snapshot_ref"] = _require_snapshot_ref(
                    snapshot_refs,
                    accepted_snapshot_id,
                    field_path=(
                        f"$.subsets[{subset_index}].acceptance."
                        f"{accepted_key}"
                    ),
            )
        subset["parent_actor_set_id"] = actor_set_id
        if "band_sets" in subset:
            _optional_list(
                subset,
                "band_sets",
                field_path=f"$.subsets[{subset_index}].band_sets",
            )
            subset.pop("band_sets", None)
        band_sets = []
        band_set_ids = _optional_list(
            subset,
            "band_set_ids",
            field_path=f"$.subsets[{subset_index}].band_set_ids",
        )
        subset.pop("band_set_ids", None)
        for band_set_index, band_set_id in enumerate(band_set_ids):
            if isinstance(band_set_id, str) and band_set_id:
                band_sets.append({"band_set_id": band_set_id})
            else:
                _raise(
                    "metadata_id_required",
                    "Subset band_set_ids entries must be non-empty strings.",
                    field_path=(
                        f"$.subsets[{subset_index}].band_set_ids[{band_set_index}]"
                    ),
                )
        if band_sets:
            subset["band_sets"] = band_sets
        subset_payloads.append((ref, subset))

    grouping_refs: dict[str, str] = {}
    grouping_ids: dict[str, str] = {}
    grouping_payloads: list[tuple[str, dict[str, Any]]] = []
    groupings = _optional_list(arguments, "groupings", field_path="$.groupings")
    for grouping_index, grouping_input in enumerate(groupings):
        if not isinstance(grouping_input, dict):
            _raise("metadata_bundle_invalid", "Grouping entries must be objects.")
        band_set_field_path = f"$.groupings[{grouping_index}].band_set_id"
        band_set_id = _require_text_id(
            grouping_input,
            "band_set_id",
            field_path=band_set_field_path,
        )
        _remember_unique_id(
            grouping_ids,
            field="band_set_id",
            value=band_set_id,
            field_path=band_set_field_path,
        )
        parent_actor_set_id = _require_parent_actor_set(
            grouping_input.get("parent_actor_set_id"),
            actor_set_id,
            field_path=f"$.groupings[{grouping_index}].parent_actor_set_id",
        )
        parent_subset_id = _require_parent_subset(
            subset_refs,
            grouping_input.get("parent_subset_id"),
            field_path=f"$.groupings[{grouping_index}].parent_subset_id",
        )
        ref = _grouping_ref(parent_actor_set_id, parent_subset_id, band_set_id)
        grouping_refs[band_set_id] = ref
        grouping = _normalize_common_metadata(
            grouping_input,
            metadata_kind=KIND_ACTOR_GROUPING,
            source_document=source_document,
            generated_at_utc=generated_at_utc,
        )
        grouping["parent_actor_set_id"] = actor_set_id
        grouping["parent_subset_id"] = parent_subset_id
        exemplar_key = "exemplar_selection_snapshot_id"
        if exemplar_key in grouping:
            exemplar_snapshot_id = grouping.pop(exemplar_key)
            grouping["exemplar_selection_snapshot_ref"] = _require_snapshot_ref(
                snapshot_refs,
                exemplar_snapshot_id,
                field_path=f"$.groupings[{grouping_index}].{exemplar_key}",
            )
        grouping_payloads.append((ref, grouping))

    for subset_index, (_, subset) in enumerate(subset_payloads):
        band_sets = subset.get("band_sets")
        if isinstance(band_sets, list):
            for band_set_index, band_set in enumerate(band_sets):
                if not isinstance(band_set, dict):
                    continue
                band_set_id = band_set.get("band_set_id")
                if band_set_id in grouping_refs:
                    band_set["ref"] = grouping_refs[band_set_id]
                else:
                    _raise(
                        "metadata_ref_target_missing",
                        "Subset band_set_ids entry does not match a supplied grouping.",
                        field_path=(
                            f"$.subsets[{subset_index}]."
                            f"band_set_ids[{band_set_index}]"
                        ),
                        target_id=band_set_id,
                        target_kind=KIND_ACTOR_GROUPING,
                    )

    actor_set = _normalize_common_metadata(
        actor_set_input,
        metadata_kind=KIND_ACTOR_SET,
        source_document=source_document,
        generated_at_utc=generated_at_utc,
    )
    source_snapshot_key = "source_snapshot_entry_id"
    if source_snapshot_key in actor_set:
        source_snapshot_id = actor_set.pop(source_snapshot_key)
        actor_set["source_snapshot_ref"] = _require_snapshot_ref(
            snapshot_refs,
            source_snapshot_id,
            field_path=f"$.actor_set.{source_snapshot_key}",
        )
    if subset_payloads:
        actor_set["subsets"] = [
            {
                "subset_id": subset.get("subset_id"),
                "ref": ref,
            }
            for ref, subset in subset_payloads
        ]

    payloads: list[tuple[str, str, dict[str, Any]]] = []
    payloads.extend(
        (ref, KIND_SELECTION_SNAPSHOT, payload)
        for ref, payload in snapshot_payloads
    )
    payloads.append((actor_ref, KIND_ACTOR_SET, actor_set))
    payloads.extend((ref, KIND_ACTOR_SUBSET, payload) for ref, payload in subset_payloads)
    payloads.extend(
        (ref, KIND_ACTOR_GROUPING, payload)
        for ref, payload in grouping_payloads
    )

    resolved_payloads = _preflight_payloads(project_root, payloads)

    for resolved_path, payload in resolved_payloads:
        _atomic_write_json(resolved_path, payload)

    written = [
        _written_entry(project_root, ref, metadata_kind=metadata_kind)
        for ref, metadata_kind, _ in payloads
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "actor_set_ref": actor_ref,
        "resolved_actor_set_path": str(resolve_metadata_ref(project_root, actor_ref)),
        "written": written,
    }
