"""Director v3 Slice 1: immutable take-package builder.

Spec: docs/superpowers/specs/2026-07-06-director-v3-snapshot-boundary-design.md
Builds <output_root>/<take_id>/ with scene.3dm (save-copy snapshot),
scene_manifest.json (member + display-mode contract), motion.json (authoring),
camera.json (optional), status.json (job ledger). Never mutates the live doc.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bridge import call_rhino

PACKAGE_SCHEMA_VERSION = 1
_TAKE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class DirectorTakePackageError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

    def to_data(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self)}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    text = json.dumps(payload, indent=2, sort_keys=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _native(call_native, endpoint: str, method: str, data: dict | None,
                  port: int | None, error_code: str) -> Any:
    envelope = await call_native(endpoint, method, data, port=port)
    if not isinstance(envelope, dict) or not envelope.get("success"):
        detail = envelope.get("data") if isinstance(envelope, dict) else envelope
        raise DirectorTakePackageError(error_code, f"{endpoint} failed: {detail}")
    return envelope.get("data")


def _validate(arguments: dict[str, Any]) -> dict[str, Any]:
    take_id = arguments.get("take_id")
    if not isinstance(take_id, str) or not _TAKE_ID_RE.match(take_id):
        raise DirectorTakePackageError(
            "invalid_input", "take_id must match [A-Za-z0-9._-]{1,128}")
    output_root = arguments.get("output_root")
    if not isinstance(output_root, str) or not output_root.strip():
        raise DirectorTakePackageError("invalid_input", "output_root is required")
    actor_sets = arguments.get("actor_sets")
    if not isinstance(actor_sets, list) or not actor_sets:
        raise DirectorTakePackageError("invalid_input", "actor_sets must be non-empty")
    for entry in actor_sets:
        if not isinstance(entry, dict):
            raise DirectorTakePackageError("invalid_input", "actor_sets entries must be objects")
        for key in ("actor_set_id", "block_name", "source_top_level_object_id"):
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise DirectorTakePackageError("invalid_input", f"actor_sets[].{key} is required")
        if not _UUID_RE.match(entry["source_top_level_object_id"]):
            raise DirectorTakePackageError(
                "invalid_input", "source_top_level_object_id must be a UUID")
    motion = arguments.get("motion")
    if not isinstance(motion, dict) or not motion:
        raise DirectorTakePackageError("invalid_input", "motion (authoring request) is required")
    display_modes = arguments.get("display_modes")
    if (not isinstance(display_modes, list) or not display_modes
            or not all(isinstance(m, str) and m for m in display_modes)):
        raise DirectorTakePackageError(
            "invalid_input", "display_modes must be a non-empty list of mode names")
    camera = arguments.get("camera")
    if camera is not None and not isinstance(camera, dict):
        raise DirectorTakePackageError("invalid_input", "camera must be an object or null")
    return {"take_id": take_id, "output_root": output_root, "actor_sets": actor_sets,
            "motion": motion, "display_modes": display_modes, "camera": camera}


async def _resolve_actor_state(call_native, actor_sets: list[dict[str, Any]],
                               port: int | None) -> list[dict[str, Any]]:
    """Resolve source instances + member evidence. Called twice: before the
    scene snapshot and after it — the two results must be identical
    (deep drift gate), so everything here must be deterministic."""
    resolved = []
    for entry in actor_sets:
        instances = await _native(call_native, "/block/instances", "POST",
                                  {"name": entry["block_name"]}, port,
                                  "actor_set_resolution_failed")
        match = next((inst for inst in (instances.get("instances") or [])
                      if inst.get("id") == entry["source_top_level_object_id"]), None)
        if match is None:
            raise DirectorTakePackageError(
                "source_instance_mismatch",
                f"object {entry['source_top_level_object_id']} is not a current "
                f"instance of block '{entry['block_name']}'")
        xform = match.get("xform")
        if not xform:
            raise DirectorTakePackageError(
                "source_instance_mismatch",
                "native /block/instances returned no xform; deploy the Slice 1 "
                "native build")
        xform_rounded = [[round(v, 6) for v in row] for row in xform]
        source_instance = {
            "instance_id": match["id"],
            "definition_id": match.get("definitionId"),
            "definition_name": match.get("definitionName"),
            "layer": match.get("layer"),
            "name": match.get("name") or "",
            "xform": xform_rounded,
            "xform_sha256": hashlib.sha256(
                json.dumps(xform_rounded).encode("utf-8")).hexdigest(),
        }

        block = await _native(call_native, "/block/objects-detailed", "POST",
                              {"name": entry["block_name"]}, port,
                              "actor_set_resolution_failed")
        objects = block.get("objects") or []
        if not objects:
            raise DirectorTakePackageError(
                "actor_set_resolution_failed",
                f"block '{entry['block_name']}' has no definition objects")
        members = []
        non_tight: list[str] = []
        for obj in objects:
            index = obj.get("index")
            member_id = f"{entry['actor_set_id']}_member_{index:04d}"
            bbox = obj.get("bbox") or {}
            bbox_method = obj.get("bboxMethod")
            if bbox_method != "tight_object":
                # DEC-021: loose/unlabeled bbox never enters the manifest as
                # evidence. Old native builds (no bboxMethod field) fail here
                # too — deploy the labeled build.
                non_tight.append(f"{member_id} (bboxMethod={bbox_method!r})")
                continue
            members.append({
                "actor_member_id": member_id,
                "definition_object_index": index,
                "definition_object_id": obj.get("id"),
                "expected": {"type": obj.get("type"), "layer": obj.get("layer"),
                             "name": obj.get("name") or ""},
                "bbox_evidence": {
                    "bbox_method": "tight_object",
                    "bbox_space": "definition_object",
                    "min": [round(v, 4) for v in (bbox.get("min") or [])],
                    "max": [round(v, 4) for v in (bbox.get("max") or [])],
                    "rounding_policy": "round_to_4_decimal_places",
                    "validation_strength": "tight_bbox",
                },
            })
        if non_tight:
            raise DirectorTakePackageError(
                "tight_bbox_unavailable",
                "tight bbox unavailable for members: " + ", ".join(non_tight))
        resolved.append({
            "actor_set_id": entry["actor_set_id"],
            "block_name": entry["block_name"],
            "source_top_level_object_id": entry["source_top_level_object_id"],
            "source_instance": source_instance,
            "member_count": len(members),
            "members": members,
        })
    return resolved


async def package_take(arguments: dict[str, Any], *, call_native=call_rhino,
                       port: int | None = None, now_fn=_utc_now,
                       source_path_override: str | None = None) -> dict[str, Any]:
    spec = _validate(arguments)

    package_root = Path(spec["output_root"]).expanduser().resolve() / spec["take_id"]
    if package_root.exists():
        raise DirectorTakePackageError(
            "package_already_exists",
            f"package directory already exists: {package_root}")

    doc = await _native(call_native, "/document", "GET", None, port, "invalid_input")
    doc_path = source_path_override or doc.get("path") or ""
    doc_modified = bool(doc.get("modified"))
    doc_object_count = doc.get("objectCount")

    # Display-mode requirements: verify every requested mode exists NOW, by name.
    modes_data = await _native(call_native, "/display-modes", "GET", None, port,
                               "display_mode_missing")
    available = {m.get("name"): m.get("id") for m in modes_data.get("modes", [])}
    missing = [m for m in spec["display_modes"] if m not in available]
    if missing:
        raise DirectorTakePackageError(
            "display_mode_missing",
            f"requested display modes not present in this Rhino: {missing}")
    display_mode_requirements = [
        {"name": name, "id": available[name], "settings_fingerprint": None}
        for name in spec["display_modes"]
    ]

    # Actor state resolution (source instance identity + member evidence).
    # Definition-object order = provenance order.
    actor_sets_manifest = await _resolve_actor_state(
        call_native, spec["actor_sets"], port)

    # Stage everything; promote atomically on success so a failed run can
    # never poison the output directory (retry-safe: a failed attempt leaves
    # no <take_id> dir behind, so retries do not hit package_already_exists).
    staging_root = package_root.parent / f".{spec['take_id']}.staging"
    if staging_root.exists():
        # Single-writer assumption: concurrent package_take calls must use distinct take_ids.
        shutil.rmtree(staging_root)  # leftover from a crashed run; ours by construction
    staging_root.mkdir(parents=True, exist_ok=False)
    scene_path = staging_root / "scene.3dm"

    # Scene snapshot: save-copy preferred; raw copy only for a saved, unmodified doc.
    save_copy = await call_native("/document/save-copy", "POST",
                                  {"path": str(scene_path)}, port=port)
    if isinstance(save_copy, dict) and save_copy.get("success"):
        evidence = save_copy.get("data") or {}
        required = ("path_before", "path_after", "title_before", "title_after",
                    "modified_before", "modified_after", "save_small_used")
        missing_fields = [k for k in required if k not in evidence]
        if missing_fields:
            raise DirectorTakePackageError(
                "save_copy_invariant_violation",
                f"save-copy evidence incomplete (old native build?); "
                f"missing: {missing_fields}")
        if (evidence["path_before"] != evidence["path_after"]
                or evidence["title_before"] != evidence["title_after"]
                or evidence["modified_before"] != evidence["modified_after"]
                or evidence["save_small_used"] is not False):
            raise DirectorTakePackageError(
                "save_copy_invariant_violation",
                f"save-copy changed document state: {evidence}")
        scene_mechanism = "save_copy"
        scene_evidence = evidence
    elif doc_modified:
        raise DirectorTakePackageError(
            "document_not_saved",
            "document has unsaved edits and /document/save-copy is unavailable; "
            "save the document or deploy a native build with save-copy")
    else:
        if not doc_path:
            raise DirectorTakePackageError(
                "save_copy_failed", "document has no path to raw-copy from")
        shutil.copyfile(doc_path, scene_path)
        scene_mechanism = "raw_copy_saved_file"
        scene_evidence = {"copy_path": str(scene_path), "source_path": doc_path}

    if not scene_path.is_file() or scene_path.stat().st_size == 0:
        raise DirectorTakePackageError("save_copy_failed", "scene.3dm missing or empty")

    # Deep drift gate: the ACTOR STATE (instance identity/xform + every member's
    # id/type/layer/name/tight bbox) must be identical before and after the
    # scene snapshot. Object count alone is NOT sufficient — a dirty document
    # can mutate actors while preserving count (Codex plan review, finding 2).
    actor_state_after = await _resolve_actor_state(
        call_native, spec["actor_sets"], port)
    if actor_state_after != actor_sets_manifest:
        raise DirectorTakePackageError(
            "package_state_drift",
            "actor state changed between enumeration and snapshot; "
            "scene.3dm and scene_manifest.json would disagree — re-run packaging")

    # Cheap document-level check as a second line (path/modified/count).
    doc_after = await _native(call_native, "/document", "GET", None, port, "invalid_input")
    if (doc_after.get("objectCount") != doc_object_count
            or bool(doc_after.get("modified")) != doc_modified
            or (doc_after.get("path") or "") != (doc.get("path") or "")):
        raise DirectorTakePackageError(
            "package_state_drift",
            "live document changed during packaging; re-run packaging")

    motion_hash = _write_json(staging_root / "motion.json", spec["motion"])
    camera_hash = None
    if spec["camera"] is not None:
        camera_hash = _write_json(staging_root / "camera.json", spec["camera"])
    scene_hash = _sha256_file(scene_path)

    hashes = {
        "motion_json_sha256": motion_hash,
        "camera_json_sha256": camera_hash,
        "scene_3dm_sha256": scene_hash,
        "scene_3dm_bytes": scene_path.stat().st_size,
    }

    manifest = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "metadata_kind": "director_take_package_manifest",
        "take_id": spec["take_id"],
        "created_at_utc": now_fn(),
        "source_document": {
            "path": doc.get("path") or "",
            "modified_at_package_time": doc_modified,
            "object_count": doc_object_count,
            "units": doc.get("units"),
        },
        "scene": {"file": "scene.3dm", "mechanism": scene_mechanism,
                  "evidence": scene_evidence, "bytes": hashes["scene_3dm_bytes"],
                  "sha256": scene_hash},
        "actor_sets": actor_sets_manifest,
        "display_mode_requirements": display_mode_requirements,
        "hashes": hashes,
    }
    manifest_hash = _write_json(staging_root / "scene_manifest.json", manifest)

    package_id = f"{spec['take_id']}-{manifest_hash[:12]}"
    status = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "package_id": package_id,
        "take_id": spec["take_id"],
        "phase": "packaged",
        "heartbeat_utc": now_fn(),
        "scene_manifest_sha256": manifest_hash,
        "evidence": {"scene_mechanism": scene_mechanism},
    }
    _write_json(staging_root / "status.json", status)

    # Atomic promotion: the final <take_id> directory appears only for a
    # fully-gated, complete package. A failed run leaves only the staging
    # dir, which the next run removes — so retries never see
    # package_already_exists from a failure.
    staging_root.rename(package_root)

    return {
        "package_root": str(package_root),
        "package_id": package_id,
        "take_id": spec["take_id"],
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "scene": manifest["scene"],
        "actor_set_member_counts": {
            a["actor_set_id"]: a["member_count"] for a in actor_sets_manifest},
        "display_mode_requirements": display_mode_requirements,
        "hashes": hashes,
    }
