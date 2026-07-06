from __future__ import annotations

import copy
from collections import Counter
import datetime
import hashlib
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

STORAGE_VERSION = 2
REF_PROTOCOL = "director_short_refs_v1"
CANONICAL_REF_PREFIX = ".rook/director/v2/"
LEGACY_REF_PREFIX = ".rook/director_planning/"
CANONICAL_REF_MAX_LENGTH = 120
DEEP_TRANSFER_PATH_MAX_LENGTH = 240

STORAGE_KIND_ACTOR_SET = "actor_set"
STORAGE_KIND_SELECTION_SNAPSHOT = "selection_snapshot"
STORAGE_KIND_SUBSET = "subset"
STORAGE_KIND_GROUPING = "grouping"

_STORAGE_KIND_TO_METADATA_KIND = {
    STORAGE_KIND_ACTOR_SET: KIND_ACTOR_SET,
    STORAGE_KIND_SELECTION_SNAPSHOT: KIND_SELECTION_SNAPSHOT,
    STORAGE_KIND_SUBSET: KIND_ACTOR_SUBSET,
    STORAGE_KIND_GROUPING: KIND_ACTOR_GROUPING,
}

_STORAGE_KIND_TO_REF_PARTS = {
    STORAGE_KIND_ACTOR_SET: ("actor_sets", "as"),
    STORAGE_KIND_SELECTION_SNAPSHOT: ("snapshots", "snap"),
    STORAGE_KIND_SUBSET: ("subsets", "sub"),
    STORAGE_KIND_GROUPING: ("groupings", "grp"),
}

_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")
_WINDOWS_INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


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
    for segment in segments[1:]:
        if not _is_safe_windows_filename_segment(segment):
            _raise(
                "invalid_metadata_ref",
                "Metadata ref contains an unsafe Windows filename segment.",
            )
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


def classify_metadata_ref(ref: str) -> str:
    valid_ref = validate_metadata_ref(ref)
    if valid_ref.startswith(CANONICAL_REF_PREFIX):
        return "canonical"
    if valid_ref.startswith(LEGACY_REF_PREFIX):
        return "legacy"
    _raise(
        "metadata_ref_prefix_unsupported",
        "Director metadata ref must use .rook/director/v2/ or .rook/director_planning/.",
        ref=valid_ref,
        allowed_prefixes=[CANONICAL_REF_PREFIX, LEGACY_REF_PREFIX],
    )


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


def _reject_generated_ref_input_fields(
    value: Any,
    field_path: str = "$",
    *,
    allowed_field_paths: set[str] | None = None,
) -> None:
    allowed = allowed_field_paths or set()
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            child_path = _legacy_field_path(field_path, key_text)
            if (
                key_text == "ref" or key_text.endswith("_ref")
            ) and child_path not in allowed:
                _raise(
                    "generated_ref_field_present",
                    "Director metadata writer generates durable refs from semantic IDs.",
                    field_path=child_path,
                )
            _reject_generated_ref_input_fields(
                item,
                child_path,
                allowed_field_paths=allowed,
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_generated_ref_input_fields(
                item,
                f"{field_path}[{index}]",
                allowed_field_paths=allowed,
            )


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


def validate_loaded_metadata_for_ref(
    payload: dict,
    *,
    ref: str,
    expected_kind: str,
) -> dict[str, Any]:
    valid_ref = validate_metadata_ref(ref)
    ref_class = classify_metadata_ref(valid_ref)
    loaded = validate_loaded_metadata(payload, expected_kind=expected_kind)
    if ref_class == "legacy":
        return {
            "payload": loaded,
            "legacy_ref": True,
            "storage_protocol": "legacy_director_planning_v2",
        }

    storage_version = loaded.get("storage_version")
    if storage_version != STORAGE_VERSION:
        _raise(
            "metadata_storage_version_mismatch",
            "Canonical Director metadata requires the current storage version.",
            ref=valid_ref,
            storage_version=storage_version,
            expected_storage_version=STORAGE_VERSION,
        )
    ref_protocol = loaded.get("ref_protocol")
    if ref_protocol != REF_PROTOCOL:
        _raise(
            "metadata_ref_protocol_mismatch",
            "Canonical Director metadata requires the current ref protocol.",
            ref=valid_ref,
            ref_protocol=ref_protocol,
            expected_ref_protocol=REF_PROTOCOL,
        )
    storage_identity = loaded.get("storage_identity")
    if not isinstance(storage_identity, dict):
        _raise(
            "storage_identity_invalid",
            "Canonical Director metadata requires a storage identity object.",
            ref=valid_ref,
        )
    identity_metadata_kind = metadata_kind_for_storage_identity(storage_identity)
    if identity_metadata_kind != expected_kind:
        _raise(
            "storage_identity_kind_mismatch",
            "Storage identity kind does not match the expected metadata kind.",
            ref=valid_ref,
            storage_identity_kind=storage_identity.get("kind"),
            metadata_kind=identity_metadata_kind,
            expected_kind=expected_kind,
        )
    if not canonical_ref_matches_storage_identity(valid_ref, storage_identity):
        _raise(
            "storage_identity_ref_mismatch",
            "Canonical Director metadata ref does not match its storage identity.",
            ref=valid_ref,
            storage_identity=storage_identity,
            expected_ref=canonical_ref_for_storage_identity(storage_identity),
        )
    return {
        "payload": loaded,
        "legacy_ref": False,
        "storage_protocol": REF_PROTOCOL,
    }


def load_metadata_ref_with_diagnostics(
    project_root: Path,
    ref: str,
    *,
    expected_kind: str,
) -> dict[str, Any]:
    classify_metadata_ref(ref)
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
    return validate_loaded_metadata_for_ref(
        payload,
        ref=ref,
        expected_kind=expected_kind,
    )


def load_metadata_ref(project_root: Path, ref: str, *, expected_kind: str) -> dict:
    return load_metadata_ref_with_diagnostics(
        project_root,
        ref,
        expected_kind=expected_kind,
    )["payload"]


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


def _unwrap_native_data(response: Any, *, endpoint: str) -> Any:
    if isinstance(response, dict) and response.get("success") is False:
        error = response.get("error")
        if isinstance(error, dict):
            message = error.get("message") or "Rhino route returned an error."
            code = error.get("code") or "rhino_route_failed"
        else:
            message = str(error or "Rhino route returned an error.")
            code = "rhino_route_failed"
        _raise(code, message, endpoint=endpoint)
    if (
        isinstance(response, dict)
        and response.get("success") is True
        and "data" in response
    ):
        return response["data"]
    return response


async def _call_native_data(
    endpoint: str,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    *,
    call_native=call_rhino,
    port=None,
) -> Any:
    response = await call_native(endpoint, method, data, port=port)
    return _unwrap_native_data(response, endpoint=endpoint)


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


def _require_filename_segment_id(
    payload: dict[str, Any],
    key: str,
    *,
    field_path: str,
) -> str:
    value = _require_text_id(payload, key, field_path=field_path)
    _validate_filename_segment_id(value, key=key, field_path=field_path)
    return value


def _validate_filename_segment_id(
    value: str,
    *,
    key: str,
    field_path: str,
) -> None:
    if not _is_safe_windows_filename_segment(value):
        _raise(
            "metadata_id_invalid",
            "Metadata id must be a single safe filename segment.",
            field=key,
            field_path=field_path,
            value=value,
        )


def _is_safe_windows_filename_segment(value: str) -> bool:
    reserved_name = value.split(".", 1)[0].upper()
    name_before_extension = value.rsplit(".", 1)[0] if "." in value else value
    return not (
        _WINDOWS_INVALID_FILENAME_CHARS_RE.search(value)
        or value in (".", "..")
        or value.endswith(".")
        or value.endswith(" ")
        or name_before_extension.endswith(".")
        or name_before_extension.endswith(" ")
        or value.startswith("//")
        or _DRIVE_PREFIX_RE.match(value)
        or reserved_name in _WINDOWS_RESERVED_DEVICE_NAMES
    )


def _canonical_identity_bytes(identity: dict[str, Any]) -> bytes:
    return json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def storage_identity_hash(identity: dict[str, Any]) -> str:
    _validate_storage_identity(identity)
    return hashlib.sha256(_canonical_identity_bytes(identity)).hexdigest()[:12]


def _validate_storage_identity(identity: dict[str, Any]) -> None:
    if not isinstance(identity, dict):
        _raise("storage_identity_invalid", "Storage identity must be an object.")
    kind = identity.get("kind")
    if kind not in _STORAGE_KIND_TO_METADATA_KIND:
        _raise(
            "storage_identity_invalid",
            "Storage identity kind is unsupported.",
            kind=kind,
        )
    required_by_kind = {
        STORAGE_KIND_ACTOR_SET: ("kind", "actor_set_id"),
        STORAGE_KIND_SELECTION_SNAPSHOT: ("kind", "snapshot_id"),
        STORAGE_KIND_SUBSET: ("kind", "actor_set_id", "subset_id"),
        STORAGE_KIND_GROUPING: (
            "kind",
            "actor_set_id",
            "subset_id",
            "band_set_id",
        ),
    }
    required = required_by_kind[kind]
    if set(identity) != set(required):
        _raise(
            "storage_identity_invalid",
            "Storage identity fields do not match the storage kind.",
            kind=kind,
            expected_fields=list(required),
            actual_fields=sorted(identity),
        )
    for key in required:
        value = identity[key]
        if not isinstance(value, str) or not value:
            _raise(
                "storage_identity_invalid",
                "Storage identity fields must be non-empty strings.",
                field=key,
            )


def metadata_kind_for_storage_identity(identity: dict[str, Any]) -> str:
    _validate_storage_identity(identity)
    return _STORAGE_KIND_TO_METADATA_KIND[identity["kind"]]


def canonical_ref_for_storage_identity(identity: dict[str, Any]) -> str:
    _validate_storage_identity(identity)
    folder, prefix = _STORAGE_KIND_TO_REF_PARTS[identity["kind"]]
    ref = f"{CANONICAL_REF_PREFIX}{folder}/{prefix}_{storage_identity_hash(identity)}.json"
    validate_metadata_ref(ref)
    if len(ref) > CANONICAL_REF_MAX_LENGTH:
        _raise(
            "metadata_ref_path_budget_exceeded",
            "Canonical Director metadata ref exceeds the path budget.",
            ref=ref,
            ref_length=len(ref),
            max_ref_length=CANONICAL_REF_MAX_LENGTH,
        )
    return ref


def canonical_ref_matches_storage_identity(ref: str, identity: dict[str, Any]) -> bool:
    return validate_metadata_ref(ref) == canonical_ref_for_storage_identity(identity)


def _require_canonical_metadata_ref(ref: Any, *, field_path: str) -> str:
    if not isinstance(ref, str):
        _raise(
            "invalid_metadata_ref",
            "Metadata ref must be a string.",
            field_path=field_path,
            ref=ref,
        )
    valid_ref = validate_metadata_ref(ref)
    if not valid_ref.startswith(CANONICAL_REF_PREFIX):
        _raise(
            "metadata_ref_not_canonical",
            "Director metadata writer requires canonical metadata refs.",
            field_path=field_path,
            ref=valid_ref,
            required_prefix=CANONICAL_REF_PREFIX,
        )
    return valid_ref


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


def _snapshot_identity(snapshot_id: str) -> dict[str, str]:
    return {
        "kind": STORAGE_KIND_SELECTION_SNAPSHOT,
        "snapshot_id": snapshot_id,
    }


def _actor_set_identity(actor_set_id: str) -> dict[str, str]:
    return {
        "kind": STORAGE_KIND_ACTOR_SET,
        "actor_set_id": actor_set_id,
    }


def _source_occurrence_snapshot_id_from_object_id(object_id: str) -> str:
    compact = re.sub(r"[^A-Za-z0-9]+", "_", object_id).strip("_").lower()
    return f"source_occurrence_{compact[:32]}"


def _subset_identity(actor_set_id: str, subset_id: str) -> dict[str, str]:
    return {
        "kind": STORAGE_KIND_SUBSET,
        "actor_set_id": actor_set_id,
        "subset_id": subset_id,
    }


def _grouping_identity(
    actor_set_id: str,
    subset_id: str,
    band_set_id: str,
) -> dict[str, str]:
    return {
        "kind": STORAGE_KIND_GROUPING,
        "actor_set_id": actor_set_id,
        "subset_id": subset_id,
        "band_set_id": band_set_id,
    }


def _normalize_common_metadata(
    payload: dict[str, Any],
    *,
    metadata_kind: str,
    storage_identity: dict[str, Any],
    source_document: dict[str, Any],
    generated_at_utc: str,
) -> dict[str, Any]:
    normalized = copy.deepcopy(payload)
    normalized["schema_version"] = SCHEMA_VERSION
    normalized["metadata_kind"] = metadata_kind
    normalized["storage_version"] = STORAGE_VERSION
    normalized["ref_protocol"] = REF_PROTOCOL
    normalized["storage_identity"] = copy.deepcopy(storage_identity)
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


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _inventory_summary(block_objects_detail: dict[str, Any]) -> dict[str, Any]:
    objects = block_objects_detail.get("objects")
    if not isinstance(objects, list):
        objects = []
    type_counts: Counter[str] = Counter()
    layer_counts: Counter[str] = Counter()
    color_source_counts: Counter[str] = Counter()
    material_source_counts: Counter[str] = Counter()
    visible_count = 0
    hidden_count = 0
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        type_counts[str(obj.get("type") or "Unknown")] += 1
        layer_counts[str(obj.get("layer") or "")] += 1
        color_source_counts[str(obj.get("colorSource") or "unknown")] += 1
        material_source_counts[str(obj.get("materialSource") or "unknown")] += 1
        if obj.get("visible") is True:
            visible_count += 1
        elif obj.get("visible") is False:
            hidden_count += 1
    return {
        "direct_object_count": block_objects_detail.get("objectCount", len(objects)),
        "direct_instance_reference_count": type_counts.get("InstanceReference", 0),
        "visible_count": visible_count,
        "hidden_count": hidden_count,
        "bbox": block_objects_detail.get("bbox"),
        "type_counts": _counter_dict(type_counts),
        "layer_counts": _counter_dict(layer_counts),
        "color_source_counts": _counter_dict(color_source_counts),
        "material_source_counts": _counter_dict(material_source_counts),
    }


def _nested_hierarchy_summary(nested_hierarchy: Any) -> dict[str, Any]:
    if not isinstance(nested_hierarchy, dict):
        return {
            "nested_hierarchy": {},
            "recursive_object_count": 0,
            "recursive_definition_reference_count": 0,
            "nested_definition_reference_count": 0,
            "circular_reference_count": 0,
        }

    recursive_object_count = 0
    recursive_definition_reference_count = 0
    circular_reference_count = 0

    def visit(node: Any) -> None:
        nonlocal recursive_object_count
        nonlocal recursive_definition_reference_count
        nonlocal circular_reference_count
        if not isinstance(node, dict):
            return
        recursive_definition_reference_count += 1
        object_count = node.get("objectCount")
        if isinstance(object_count, int):
            recursive_object_count += object_count
        elif isinstance(object_count, float):
            recursive_object_count += int(object_count)
        if node.get("circular") is True:
            circular_reference_count += 1
        children = node.get("children")
        if isinstance(children, list):
            for child in children:
                visit(child)

    visit(nested_hierarchy)
    return {
        "nested_hierarchy": nested_hierarchy,
        "recursive_object_count": recursive_object_count,
        "recursive_definition_reference_count": recursive_definition_reference_count,
        "nested_definition_reference_count": max(
            0,
            recursive_definition_reference_count - 1,
        ),
        "circular_reference_count": circular_reference_count,
    }


async def _capture_block_occurrence_context(
    selected_object: dict[str, Any],
    *,
    call_native=call_rhino,
    port=None,
) -> dict[str, Any]:
    block_name = selected_object.get("blockName")
    if not isinstance(block_name, str) or not block_name:
        _raise(
            "source_occurrence_block_name_required",
            "Selected InstanceReference does not report a blockName.",
            object_id=selected_object.get("id"),
        )
    block_info = await _call_native_data(
        "/block/info",
        "POST",
        {"name": block_name},
        call_native=call_native,
        port=port,
    )
    block_instances = await _call_native_data(
        "/block/instances",
        "POST",
        {"name": block_name, "depth": 0},
        call_native=call_native,
        port=port,
    )
    block_objects_detail = await _call_native_data(
        "/block/objects-detailed",
        "POST",
        {"name": block_name, "geometry": False},
        call_native=call_native,
        port=port,
    )
    nested_hierarchy = await _call_native_data(
        "/block/nested",
        "POST",
        {"name": block_name},
        call_native=call_native,
        port=port,
    )
    if not isinstance(block_info, dict):
        _raise("source_occurrence_block_info_invalid", "Block info was not an object.")
    if not isinstance(block_instances, dict):
        _raise(
            "source_occurrence_block_instances_invalid",
            "Block instances response was not an object.",
        )
    if not isinstance(block_objects_detail, dict):
        _raise(
            "source_occurrence_block_inventory_invalid",
            "Block inventory response was not an object.",
        )
    if not isinstance(nested_hierarchy, dict):
        _raise(
            "source_occurrence_nested_hierarchy_invalid",
            "Nested block hierarchy response was not an object.",
        )

    selected_id = selected_object.get("id")
    instances = block_instances.get("instances")
    if not isinstance(instances, list):
        instances = []
    matching_instances = [
        instance
        for instance in instances
        if isinstance(instance, dict) and instance.get("id") == selected_id
    ]
    instance = matching_instances[0] if matching_instances else {}

    inventory = _inventory_summary(block_objects_detail)
    inventory.update(_nested_hierarchy_summary(nested_hierarchy))

    return {
        "source_top_level_object_id": selected_id,
        "object_type": selected_object.get("type"),
        "layer": selected_object.get("layer"),
        "name": selected_object.get("name") or "",
        "visible": selected_object.get("visible"),
        "bbox": selected_object.get("bbox"),
        "block_definition": {
            "id": block_info.get("id") or selected_object.get("blockDefinitionId"),
            "index": block_info.get("index"),
            "name": block_info.get("name") or block_name,
            "block_type": block_info.get("blockType"),
            "is_linked": block_info.get("isLinked"),
            "instance_count": block_info.get("instanceCount"),
            "direct_object_count": block_info.get("objectCount"),
        },
        "instance": {
            "id": instance.get("id") or selected_id,
            "layer": instance.get("layer") or selected_object.get("layer"),
            "name": instance.get("name") or selected_object.get("name") or "",
            "insertion_point": instance.get("insertionPoint") or instance.get("point"),
            "scale": instance.get("scale"),
        },
        "definition_inventory_summary": inventory,
    }


async def capture_source_occurrence_v2(
    arguments: dict[str, Any], *, call_native=call_rhino, port=None
) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        _raise(
            "source_occurrence_capture_invalid",
            "Source occurrence capture arguments must be an object.",
        )
    _reject_legacy_path_fields(arguments)
    _reject_generated_ref_input_fields(arguments)
    _validate_ref_fields(arguments)

    project_root, source_document = await resolve_active_project_root(
        call_native=call_native,
        port=port,
    )

    ids = arguments.get("ids")
    if ids is not None:
        if not isinstance(ids, list) or not all(
            isinstance(item, str) and item for item in ids
        ):
            _raise(
                "source_occurrence_ids_invalid",
                "Source occurrence ids must be a list of non-empty strings.",
            )
        await _call_native_data(
            "/select",
            "POST",
            {"ids": ids, "clear": True},
            call_native=call_native,
            port=port,
        )

    selection = await _call_native_data(
        "/selection",
        call_native=call_native,
        port=port,
    )
    if not isinstance(selection, dict):
        _raise(
            "source_occurrence_selection_invalid",
            "Selection response was not an object.",
        )
    selected_objects = selection.get("objects")
    if not isinstance(selected_objects, list) or not selected_objects:
        _raise(
            "source_occurrence_selection_required",
            "Select at least one top-level object before source occurrence capture.",
        )
    for index, selected_object in enumerate(selected_objects):
        if not isinstance(selected_object, dict) or not selected_object.get("id"):
            _raise(
                "source_occurrence_selection_invalid",
                "Selection entries must be objects with ids.",
                index=index,
            )

    first_selected = selected_objects[0]
    snapshot_id = arguments.get("snapshot_id")
    if snapshot_id is None:
        snapshot_id = _source_occurrence_snapshot_id_from_object_id(
            str(first_selected.get("id"))
        )
    if not isinstance(snapshot_id, str) or not snapshot_id:
        _raise(
            "metadata_id_required",
            "Source occurrence capture requires a non-empty snapshot_id.",
            field="snapshot_id",
        )
    _validate_filename_segment_id(
        snapshot_id,
        key="snapshot_id",
        field_path="$.snapshot_id",
    )
    storage_identity = _snapshot_identity(snapshot_id)
    snapshot_ref = canonical_ref_for_storage_identity(storage_identity)
    generated_at_utc = _metadata_timestamp_utc()

    endpoints_used = ["/document"]
    if ids is not None:
        endpoints_used.append("/select")
    endpoints_used.append("/selection")

    def remember_endpoint(endpoint: str) -> None:
        if endpoint not in endpoints_used:
            endpoints_used.append(endpoint)

    source_occurrences: list[dict[str, Any]] = []
    for selected_object in selected_objects:
        if selected_object.get("type") == "InstanceReference":
            for endpoint in (
                "/block/info",
                "/block/instances",
                "/block/objects-detailed",
                "/block/nested",
            ):
                remember_endpoint(endpoint)
            source_occurrences.append(
                await _capture_block_occurrence_context(
                    selected_object,
                    call_native=call_native,
                    port=port,
                )
            )
        else:
            source_occurrences.append(
                {
                    "source_top_level_object_id": selected_object.get("id"),
                    "object_type": selected_object.get("type"),
                    "layer": selected_object.get("layer"),
                    "name": selected_object.get("name") or "",
                    "visible": selected_object.get("visible"),
                    "bbox": selected_object.get("bbox"),
                }
            )

    objects = [
        {
            "id": obj.get("id"),
            "type": obj.get("type"),
            "layer": obj.get("layer"),
            "name": obj.get("name") or "",
            "visible": obj.get("visible"),
            "bbox": obj.get("bbox"),
            **(
                {"block_name": obj.get("blockName")}
                if obj.get("blockName") is not None
                else {}
            ),
            **(
                {"block_definition_id": obj.get("blockDefinitionId")}
                if obj.get("blockDefinitionId") is not None
                else {}
            ),
        }
        for obj in selected_objects
    ]
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "metadata_kind": KIND_SELECTION_SNAPSHOT,
        "storage_version": STORAGE_VERSION,
        "ref_protocol": REF_PROTOCOL,
        "storage_identity": copy.deepcopy(storage_identity),
        "snapshot_id": snapshot_id,
        "intent": arguments.get("intent")
        or "source_occurrence_context_for_director_actor_set",
        "label": arguments.get("label") or "Director source occurrence",
        "generated_at_utc": generated_at_utc,
        "source_document": source_document,
        "capture_context": {
            "capture_mode": "explicit_ids" if ids is not None else "active_selection",
            "selection_count": len(selected_objects),
            "sub_object_count": selection.get("subObjectCount", 0),
        },
        "captured_object_source": {
            "toolchain": "rook_live_rhino_api",
            "endpoints": endpoints_used,
        },
        "objects": objects,
        "source_occurrences": source_occurrences,
        "summary": {
            "selected_count": len(selected_objects),
            "source_top_level_object_count": len(source_occurrences),
        },
    }
    if len(source_occurrences) == 1:
        snapshot["source_occurrence"] = source_occurrences[0]
        inventory = source_occurrences[0].get("definition_inventory_summary")
        if isinstance(inventory, dict):
            snapshot["summary"]["block_definition_direct_object_count"] = (
                inventory.get("direct_object_count")
            )
    validate_loaded_metadata(snapshot, expected_kind=KIND_SELECTION_SNAPSHOT)
    resolved_snapshot_path = resolve_metadata_ref(project_root, snapshot_ref)
    _preflight_existing_canonical_file(
        resolved_snapshot_path,
        snapshot_ref,
        snapshot,
    )
    _atomic_write_json(resolved_snapshot_path, snapshot)

    return {
        "schema_version": SCHEMA_VERSION,
        "metadata_kind": KIND_SELECTION_SNAPSHOT,
        "snapshot_id": snapshot_id,
        "snapshot_ref": snapshot_ref,
        "resolved_snapshot_path": str(resolved_snapshot_path),
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
    _validate_filename_segment_id(
        parent_actor_set_id,
        key="parent_actor_set_id",
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
    _validate_filename_segment_id(
        parent_subset_id,
        key="parent_subset_id",
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


def _preflight_existing_canonical_file(
    path: Path,
    ref: str,
    payload: dict[str, Any],
) -> None:
    if not path.exists():
        return
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as ex:
        raise DirectorActorMetadataError(
            "metadata_ref_collision",
            "Existing canonical Director metadata ref could not be verified.",
            ref=ref,
            resolved_path=str(path),
        ) from ex
    if not isinstance(existing, dict):
        _raise(
            "metadata_ref_collision",
            "Existing canonical Director metadata ref is not an object.",
            ref=ref,
            resolved_path=str(path),
        )
    storage_identity = payload.get("storage_identity")
    existing_storage_identity = existing.get("storage_identity")
    if existing_storage_identity != storage_identity:
        _raise(
            "metadata_ref_collision",
            "Existing canonical Director metadata ref belongs to a different storage identity.",
            ref=ref,
            resolved_path=str(path),
            storage_identity=storage_identity,
            existing_storage_identity=existing_storage_identity,
        )


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
        if ref.startswith(CANONICAL_REF_PREFIX):
            _preflight_existing_canonical_file(resolved_path, ref, payload)
        resolved_payloads.append((resolved_path, payload))
    return resolved_payloads


async def write_actor_metadata_bundle_v2(
    arguments: dict[str, Any], *, call_native=call_rhino, port=None
) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        _raise("metadata_bundle_invalid", "Director metadata bundle must be an object.")
    _reject_legacy_path_fields(arguments)
    _reject_generated_ref_input_fields(
        arguments,
        allowed_field_paths={"$.actor_set.source_occurrence_snapshot_ref"},
    )
    _validate_ref_fields(arguments)

    project_root, source_document = await resolve_active_project_root(
        call_native=call_native,
        port=port,
    )
    generated_at_utc = _metadata_timestamp_utc()

    actor_set_input = arguments.get("actor_set")
    if not isinstance(actor_set_input, dict):
        _raise("metadata_bundle_invalid", "Director metadata bundle requires actor_set.")
    actor_set_id = _require_filename_segment_id(
        actor_set_input,
        "actor_set_id",
        field_path="$.actor_set.actor_set_id",
    )
    actor_identity = _actor_set_identity(actor_set_id)
    actor_ref = canonical_ref_for_storage_identity(actor_identity)
    source_occurrence_snapshot_ref = actor_set_input.get(
        "source_occurrence_snapshot_ref"
    )
    if source_occurrence_snapshot_ref is not None:
        source_occurrence_snapshot_ref = _require_canonical_metadata_ref(
            source_occurrence_snapshot_ref,
            field_path="$.actor_set.source_occurrence_snapshot_ref",
        )
        actor_set_input["source_occurrence_snapshot_ref"] = (
            source_occurrence_snapshot_ref
        )
        load_metadata_ref(
            project_root,
            source_occurrence_snapshot_ref,
            expected_kind=KIND_SELECTION_SNAPSHOT,
        )

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
        snapshot_id = _require_filename_segment_id(
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
        storage_identity = _snapshot_identity(snapshot_id)
        ref = canonical_ref_for_storage_identity(storage_identity)
        snapshot_refs[snapshot_id] = ref
        snapshot = _normalize_common_metadata(
            snapshot_input,
            metadata_kind=KIND_SELECTION_SNAPSHOT,
            storage_identity=storage_identity,
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
        subset_id = _require_filename_segment_id(
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
        storage_identity = _subset_identity(parent_actor_set_id, subset_id)
        ref = canonical_ref_for_storage_identity(storage_identity)
        subset_refs[subset_id] = ref
        subset = _normalize_common_metadata(
            subset_input,
            metadata_kind=KIND_ACTOR_SUBSET,
            storage_identity=storage_identity,
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
                _validate_filename_segment_id(
                    band_set_id,
                    key="band_set_id",
                    field_path=(
                        f"$.subsets[{subset_index}].band_set_ids[{band_set_index}]"
                    ),
                )
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
        band_set_id = _require_filename_segment_id(
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
        storage_identity = _grouping_identity(
            parent_actor_set_id,
            parent_subset_id,
            band_set_id,
        )
        ref = canonical_ref_for_storage_identity(storage_identity)
        grouping_refs[band_set_id] = ref
        grouping = _normalize_common_metadata(
            grouping_input,
            metadata_kind=KIND_ACTOR_GROUPING,
            storage_identity=storage_identity,
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
        storage_identity=actor_identity,
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
    actor_set.pop("subsets", None)
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
