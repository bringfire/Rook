from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

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
    resolved = Path(path).resolve()
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
            if key in LEGACY_DURABLE_PATH_FIELDS and isinstance(item, str):
                _raise(
                    "legacy_path_field_present",
                    "Metadata contains a legacy durable path field.",
                    field_path=child_path,
                )
            _reject_legacy_path_fields(item, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_legacy_path_fields(item, f"{field_path}[{index}]")


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
    if payload.get("metadata_kind") != expected_kind:
        _raise(
            "metadata_kind_mismatch",
            "Metadata kind does not match the expected kind.",
            metadata_kind=payload.get("metadata_kind"),
            expected_kind=expected_kind,
        )
    _reject_legacy_path_fields(payload)
    return payload


def load_metadata_ref(project_root: Path, ref: str, *, expected_kind: str) -> dict:
    path = resolve_metadata_ref(project_root, ref)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as ex:
        raise DirectorActorMetadataError(
            "metadata_ref_not_found",
            "Metadata ref does not exist.",
            ref=validate_metadata_ref(ref),
        ) from ex
    except json.JSONDecodeError as ex:
        raise DirectorActorMetadataError(
            "metadata_json_invalid",
            "Metadata ref did not contain valid JSON.",
            ref=validate_metadata_ref(ref),
        ) from ex
    return validate_loaded_metadata(payload, expected_kind=expected_kind)
