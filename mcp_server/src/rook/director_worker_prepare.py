"""Director v3 Slice 2: worker prepare + member map + resolved motion.

Spec: docs/superpowers/specs/2026-07-06-director-v3-snapshot-boundary-design.md
(Decision 2, step 1). Opens a take package's scene.3dm as the active document
(the disposable copy — destructive explode is legal there), validates the
package against scene_manifest.json, explodes declared actor-source instances
via POST /director/prepare-take (provenance recorded at creation time),
proves 100% coverage of claimed members, verifies type/layer/name/tight-bbox
evidence, writes member_map.json, and derives resolved_motion.json.

Mapping keys are (definition_object_index, definition_object_id) plus
occurrence paths for nested instances. Tight bbox / type / layer / name are
VERIFICATION evidence only — never identity.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .bridge import call_rhino
from .director_worker_common import (
    enforce_save_copy_evidence,
    native_call,
    norm_path,
    open_package_document,
)
from .director_take_package import (
    PACKAGE_SCHEMA_VERSION,
    canonical_json_text,
    sha256_file,
    utc_now_iso,
)

MEMBER_MAP_SCHEMA_VERSION = 1


class DirectorWorkerPrepareError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

    def to_data(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self)}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _norm_path(value: str) -> str:
    return norm_path(value)


async def _native(call_native, endpoint: str, method: str, data: dict | None,
                  port: int | None, error_code: str) -> Any:
    return await native_call(
        call_native, endpoint, method, data, port, error_code,
        DirectorWorkerPrepareError)


def _load_package(package_root_arg: Any) -> dict[str, Any]:
    if not isinstance(package_root_arg, str) or not package_root_arg.strip():
        raise DirectorWorkerPrepareError("invalid_input", "package_root is required")
    root = Path(package_root_arg).expanduser().resolve()
    if not root.is_dir():
        raise DirectorWorkerPrepareError(
            "package_invalid", f"not a package directory: {root}")
    for required in ("scene_manifest.json", "scene.3dm", "motion.json", "status.json"):
        if not (root / required).is_file():
            raise DirectorWorkerPrepareError(
                "package_invalid", f"package is missing {required}")
    try:
        manifest = json.loads((root / "scene_manifest.json").read_text(encoding="utf-8"))
        status = json.loads((root / "status.json").read_text(encoding="utf-8"))
        motion = json.loads((root / "motion.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DirectorWorkerPrepareError(
            "package_invalid", f"unparseable package JSON: {exc}") from exc
    if (manifest.get("schema_version") != PACKAGE_SCHEMA_VERSION
            or manifest.get("metadata_kind") != "director_take_package_manifest"):
        raise DirectorWorkerPrepareError(
            "package_invalid", "unrecognized scene_manifest.json schema")
    if status.get("phase") not in ("packaged", "prepared"):
        raise DirectorWorkerPrepareError(
            "package_invalid",
            f"package phase {status.get('phase')!r} is not preparable")
    if not isinstance(manifest.get("actor_sets"), list) or not manifest["actor_sets"]:
        raise DirectorWorkerPrepareError(
            "package_invalid", "scene_manifest.json has no actor_sets")
    return {"root": root, "manifest": manifest, "status": status, "motion": motion}


def _verify_package_hashes(pkg: dict[str, Any]) -> None:
    root, manifest, status = pkg["root"], pkg["manifest"], pkg["status"]
    hashes = manifest.get("hashes") or {}
    mismatches: list[str] = []

    motion_sha = _sha256_text((root / "motion.json").read_text(encoding="utf-8"))
    if motion_sha != hashes.get("motion_json_sha256"):
        mismatches.append("motion.json")

    scene = root / "scene.3dm"
    if (sha256_file(scene) != hashes.get("scene_3dm_sha256")
            or scene.stat().st_size != hashes.get("scene_3dm_bytes")):
        mismatches.append("scene.3dm")

    camera_sha = hashes.get("camera_json_sha256")
    if camera_sha is not None:
        camera = root / "camera.json"
        if not camera.is_file() or _sha256_text(
                camera.read_text(encoding="utf-8")) != camera_sha:
            mismatches.append("camera.json")

    manifest_sha = _sha256_text(
        (root / "scene_manifest.json").read_text(encoding="utf-8"))
    if manifest_sha != status.get("scene_manifest_sha256"):
        mismatches.append("scene_manifest.json")

    if mismatches:
        raise DirectorWorkerPrepareError(
            "package_hash_mismatch",
            "package artifacts disagree with recorded hashes: "
            + ", ".join(mismatches))


async def _open_scene_document(call_native, pkg: dict[str, Any],
                               port: int | None) -> None:
    await open_package_document(
        call_native, pkg["root"], pkg["root"] / "scene.3dm", port=port,
        error_cls=DirectorWorkerPrepareError, mode="fail_closed")


async def _verify_take_copy_pristine(call_native, manifest: dict[str, Any],
                                     port: int | None) -> None:
    """Object-level pristine gate: every actor-set source instance must
    exist in the opened copy. A prior prepare deletes the source instances,
    so their absence proves the copy is mutated (flag checks cannot — see
    _open_scene_document). Mirrors Slice 1's /block/instances resolution."""
    for actor in manifest["actor_sets"]:
        data = await _native(call_native, "/block/instances", "POST",
                             {"name": actor["block_name"]}, port,
                             "take_copy_not_pristine")
        ids = {inst.get("id") for inst in data.get("instances") or []}
        if actor["source_top_level_object_id"] not in ids:
            raise DirectorWorkerPrepareError(
                "take_copy_not_pristine",
                f"actor set {actor['actor_set_id']!r}: source instance "
                f"{actor['source_top_level_object_id']} is missing from the "
                "opened copy — the copy was mutated (e.g. a prior prepare) "
                "and the reopen did not reload it; close the document in "
                "Rhino and re-run prepare")


async def _verify_display_modes(call_native, manifest: dict[str, Any],
                                port: int | None) -> None:
    data = await _native(call_native, "/display-modes", "GET", None, port,
                         "display_mode_missing")
    available = {m.get("name") for m in data.get("modes", [])}
    required = [r.get("name") for r in manifest.get("display_mode_requirements") or []]
    missing = [name for name in required if name not in available]
    if missing:
        raise DirectorWorkerPrepareError(
            "display_mode_missing",
            f"required display modes not present in this Rhino: {missing}")


async def _run_prepare(call_native, pkg: dict[str, Any],
                       port: int | None) -> dict[str, Any]:
    manifest = pkg["manifest"]
    actor_sets = [
        {"actorSetId": a["actor_set_id"],
         "instanceId": a["source_top_level_object_id"]}
        for a in manifest["actor_sets"]
    ]
    return await _native(
        call_native, "/director/prepare-take", "POST",
        {"expectedDocumentPath": str(pkg["root"] / "scene.3dm"),
         "actorSets": actor_sets},
        port, "prepare_route_failed")


def _verify_and_map(manifest: dict[str, Any],
                    prepare_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Coverage proof + evidence verification. Returns member-map actor sets.

    Coverage failures (missing/skipped/identity mismatch) and verification
    failures (type/layer/name/bbox evidence) are collected exhaustively so a
    single failed run reports every problem, then coverage wins precedence.
    """
    by_set = {s.get("actorSetId"): s for s in prepare_data.get("actorSets") or []}
    coverage: list[str] = []
    verification: list[str] = []
    map_sets: list[dict[str, Any]] = []

    for actor in manifest["actor_sets"]:
        set_id = actor["actor_set_id"]
        prepared = by_set.get(set_id)
        if prepared is None:
            coverage.append(f"{set_id}: absent from prepare response")
            continue
        members_by_index = {m.get("index"): m for m in prepared.get("members") or []}
        map_members: list[dict[str, Any]] = []

        for member in actor["members"]:
            mid = member["actor_member_id"]
            idx = member["definition_object_index"]
            got = members_by_index.get(idx)
            if got is None:
                coverage.append(f"{mid}: no prepare entry for definition index {idx}")
                continue
            if got.get("definitionObjectId") != member["definition_object_id"]:
                coverage.append(
                    f"{mid}: definition object id changed "
                    f"({member['definition_object_id']} -> "
                    f"{got.get('definitionObjectId')}) — take copy does not "
                    "match the manifest")
                continue
            for skip in got.get("skipped") or []:
                coverage.append(
                    f"{mid}: skipped {skip.get('occurrencePath')}: "
                    f"{skip.get('reason')}")
            created = got.get("created") or []
            if not created:
                coverage.append(f"{mid}: no objects created")

            expected = member["expected"]
            if got.get("type") != expected.get("type"):
                verification.append(
                    f"{mid}: type {got.get('type')!r} != expected "
                    f"{expected.get('type')!r}")
            if got.get("layer") != expected.get("layer"):
                verification.append(
                    f"{mid}: layer {got.get('layer')!r} != expected "
                    f"{expected.get('layer')!r}")
            if (got.get("name") or "") != (expected.get("name") or ""):
                verification.append(f"{mid}: name mismatch")
            evidence = member["bbox_evidence"]
            if got.get("bboxMethod") != "tight_object":
                verification.append(
                    f"{mid}: bboxMethod {got.get('bboxMethod')!r} is not "
                    "tight_object")
            else:
                bbox = got.get("defBbox") or {}
                got_min = [round(v, 4) for v in bbox.get("min") or []]
                got_max = [round(v, 4) for v in bbox.get("max") or []]
                if got_min != evidence["min"] or got_max != evidence["max"]:
                    verification.append(
                        f"{mid}: definition-space tight bbox mismatch "
                        f"({got_min}/{got_max} != "
                        f"{evidence['min']}/{evidence['max']})")

            map_members.append({
                "actor_member_id": mid,
                "definition_object_index": idx,
                "definition_object_id": member["definition_object_id"],
                "member_type": expected.get("type"),
                "created_object_ids": [c["createdObjectId"] for c in created],
                "occurrences": [
                    {"occurrence_path": c.get("occurrencePath"),
                     "definition_object_id": c.get("definitionObjectId"),
                     "created_object_id": c.get("createdObjectId"),
                     "type": c.get("type")}
                    for c in created
                ],
            })

        map_sets.append({
            "actor_set_id": set_id,
            "source_top_level_object_id": actor["source_top_level_object_id"],
            "exploded_instance_id": prepared.get("instanceId"),
            "members": map_members,
        })

    if coverage:
        raise DirectorWorkerPrepareError(
            "prepare_coverage_incomplete", "; ".join(coverage))
    if verification:
        raise DirectorWorkerPrepareError(
            "prepare_verification_failed", "; ".join(verification))
    return map_sets


def _derive_resolved_motion(motion: dict[str, Any],
                            map_sets: list[dict[str, Any]],
                            derived_from: dict[str, Any]) -> dict[str, Any]:
    lookup: dict[str, list[str]] = {}
    for actor in map_sets:
        set_ids: list[str] = []
        for member in actor["members"]:
            lookup[member["actor_member_id"]] = list(member["created_object_ids"])
            set_ids.extend(member["created_object_ids"])
        lookup[actor["actor_set_id"]] = set_ids

    def expand(names: list[Any], context: str) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for name in names:
            ids = lookup.get(name) if isinstance(name, str) else None
            if ids is None:
                raise DirectorWorkerPrepareError(
                    "motion_member_unmapped",
                    f"{context}: {name!r} is not a canonical actor_set_id or "
                    "actor_member_id (v3 motion targets are canonical members "
                    "only — raw object UUIDs are not allowed)")
            for oid in ids:
                if oid not in seen:
                    seen.add(oid)
                    out.append(oid)
        return out

    # Real compiler vocabulary (director_compiler.py:56/:102): timeline is
    # the fps/duration DICT (passes through untouched); motion is the track
    # ARRAY whose entries carry target + keyframes.
    if not isinstance(motion.get("timeline"), dict):
        raise DirectorWorkerPrepareError(
            "package_invalid", "motion.json timeline must be an object")

    groups_in = motion.get("groups") or {}
    if not isinstance(groups_in, dict):
        raise DirectorWorkerPrepareError(
            "package_invalid", "motion.json groups must be an object")
    # An authored group named exactly like a canonical actor_set_id or
    # actor_member_id would silently shadow it: the compiler resolves group
    # names before bare targets (director_compiler.py:122), so a canonical
    # target would animate the group's expansion instead of the canonical
    # members. Reject the collision outright.
    collisions = sorted(name for name in groups_in if name in lookup)
    if collisions:
        raise DirectorWorkerPrepareError(
            "package_invalid",
            "motion.json group names collide with canonical actor/member "
            f"ids and would shadow them in the compiler: {collisions}")
    resolved_groups: dict[str, list[str]] = {}
    for name, members in groups_in.items():
        if not isinstance(members, list) or not members:
            raise DirectorWorkerPrepareError(
                "package_invalid",
                f"motion.json group {name!r} must be a non-empty list")
        resolved_groups[name] = expand(members, f"group {name!r}")

    tracks = motion.get("motion")
    if not isinstance(tracks, list) or not tracks:
        raise DirectorWorkerPrepareError(
            "package_invalid", "motion.json must contain a non-empty motion array")
    for track in tracks:
        if not isinstance(track, dict):
            raise DirectorWorkerPrepareError(
                "package_invalid", "motion.json motion entries must be objects")
        target = track.get("target")
        if not isinstance(target, str) or not target:
            raise DirectorWorkerPrepareError(
                "package_invalid",
                "motion.json motion entries need a string target")
        if target in resolved_groups:
            continue
        resolved_groups[target] = expand([target], f"target {target!r}")

    # motion[].target strings are intentionally left unresolved: each now
    # names a group in resolved_groups, and the Slice 3 file-backed compiler
    # expands them through expand_targets exactly like authored groups. One
    # track per target name keeps its duplicate_object_target check happy.
    resolved = dict(motion)
    resolved["groups"] = resolved_groups
    resolved["metadata_kind"] = "director_resolved_motion"
    resolved["schema_version"] = MEMBER_MAP_SCHEMA_VERSION
    resolved["derived_from"] = derived_from
    return resolved


async def prepare_take(arguments: dict[str, Any], *, call_native=call_rhino,
                       port: int | None = None,
                       now_fn=utc_now_iso) -> dict[str, Any]:
    pkg = _load_package(arguments.get("package_root"))
    _verify_package_hashes(pkg)
    await _open_scene_document(call_native, pkg, port)
    await _verify_take_copy_pristine(call_native, pkg["manifest"], port)
    await _verify_display_modes(call_native, pkg["manifest"], port)
    prepare_data = await _run_prepare(call_native, pkg, port)
    map_sets = _verify_and_map(pkg["manifest"], prepare_data)

    staging = pkg["root"] / ".prepared.3dm.staging"
    prepared_path = pkg["root"] / "prepared.3dm"
    if staging.exists():
        staging.unlink()
    try:
        evidence = await _native(
            call_native, "/document/save-copy", "POST",
            {"path": str(staging)}, port, "save_copy_failed")
        enforce_save_copy_evidence(evidence, DirectorWorkerPrepareError)
        if not staging.is_file() or staging.stat().st_size == 0:
            raise DirectorWorkerPrepareError(
                "save_copy_failed", "prepared.3dm staging missing or empty")
        os.replace(staging, prepared_path)
    except Exception:
        if staging.exists():
            staging.unlink()
        raise
    prepared_sha = sha256_file(prepared_path)
    prepared_scene = {
        "file": "prepared.3dm",
        "sha256": prepared_sha,
        "bytes": prepared_path.stat().st_size,
    }

    manifest_sha = pkg["status"].get("scene_manifest_sha256")
    member_map = {
        "schema_version": MEMBER_MAP_SCHEMA_VERSION,
        "metadata_kind": "director_member_map",
        "take_id": pkg["manifest"]["take_id"],
        "package_id": pkg["status"].get("package_id"),
        "prepared_at_utc": now_fn(),
        "scene_manifest_sha256": manifest_sha,
        "prepared_scene": prepared_scene,
        "actor_sets": map_sets,
    }
    # Hash before writing so a failed resolved-motion derivation leaves no
    # partial artifacts (all-or-nothing writes below).
    member_map_text = canonical_json_text(member_map)
    member_map_sha = _sha256_text(member_map_text)

    resolved = _derive_resolved_motion(pkg["motion"], map_sets, {
        "member_map_sha256": member_map_sha,
        "motion_json_sha256": pkg["manifest"]["hashes"]["motion_json_sha256"],
        "scene_manifest_sha256": manifest_sha,
    })
    resolved_text = canonical_json_text(resolved)
    resolved_sha = _sha256_text(resolved_text)

    (pkg["root"] / "member_map.json").write_text(member_map_text, encoding="utf-8")
    (pkg["root"] / "resolved_motion.json").write_text(resolved_text, encoding="utf-8")

    status = dict(pkg["status"])
    status["phase"] = "prepared"
    status["heartbeat_utc"] = now_fn()
    status["evidence"] = {**(status.get("evidence") or {}),
                          "member_map_sha256": member_map_sha,
                          "resolved_motion_sha256": resolved_sha,
                          "prepared_scene_sha256": prepared_sha}
    status_text = canonical_json_text(status)
    (pkg["root"] / "status.json").write_text(status_text, encoding="utf-8")

    return {
        "package_root": str(pkg["root"]),
        "take_id": member_map["take_id"],
        "package_id": member_map["package_id"],
        "phase": "prepared",
        "actor_sets": [
            {"actor_set_id": s["actor_set_id"],
             "member_count": len(s["members"]),
             "created_object_count": sum(
                 len(m["created_object_ids"]) for m in s["members"])}
            for s in map_sets
        ],
        "prepared_scene": prepared_scene,
        "member_map_sha256": member_map_sha,
        "resolved_motion_sha256": resolved_sha,
    }
