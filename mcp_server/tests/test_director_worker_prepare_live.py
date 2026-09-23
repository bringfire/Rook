"""Slice 2 live gate: package -> open copy -> prepare -> verify -> restore.

DOCUMENT-SWITCHING TEST. Requires ROOK_S2_DOC_SWITCH=1, an unmodified live
document, and a SCRATCH document (the fixture is temporarily saved into it).

Flow rationale: prepare_take's document_not_saved guard refuses to switch
away from a dirty document (correct: native /document/open silently
discards unsaved edits). So the single-instance gate mirrors the real v3
workflow -- fixture objects (a nested-block pair) are created in the live
doc and the doc is SAVED before prepare runs. An earlier draft tried to
let the fixture "evaporate" by switching away from the dirty doc; the
guard forbids exactly that, by design (first live-gate run, 2026-07-06).
After the round trip the gate reopens the original document, deletes the
fixture block definitions (with instances), and saves again, restoring
the document to its pre-gate object count. Run this on a scratch file:
a mid-gate failure can leave the fixture saved in the document until the
cleanup is re-run.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from rook.bridge import native_client
import pytest

from rook import director_take_package as dtp
from rook import director_worker_prepare as dwp
from .conftest import _create_brep

pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


def _require_opt_in() -> None:
    if os.environ.get("ROOK_S2_DOC_SWITCH") != "1":
        pytest.skip("Set ROOK_S2_DOC_SWITCH=1 to allow document switching.")


def _require_host() -> str:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")
    return base_url  # type: ignore[return-value]


async def _post(route: str, body: dict[str, Any]) -> dict[str, Any]:
    base_url = _require_host()
    async with native_client(timeout=120.0) as client:
        resp = await client.post(f"{base_url}{route}", json=body)
    return resp.json()


async def _get(route: str) -> dict[str, Any]:
    base_url = _require_host()
    async with native_client(timeout=30.0) as client:
        resp = await client.get(f"{base_url}{route}")
    return resp.json()


async def _doc() -> dict[str, Any]:
    envelope = await _get("/document")
    assert envelope.get("success"), envelope
    return envelope["data"]


async def _make_block(name: str, object_ids: list[str]) -> dict[str, Any]:
    envelope = await _post("/block/create", {
        "name": name, "ids": object_ids, "basePoint": [0.0, 0.0, 0.0],
        "replaceWithInstance": True})
    assert envelope.get("success"), envelope
    return envelope["data"]


async def _instance_id(block_name: str) -> str:
    envelope = await _post("/block/instances", {"name": block_name})
    assert envelope.get("success"), envelope
    instances = envelope["data"].get("instances") or []
    assert len(instances) == 1, instances
    return instances[0]["id"]


async def _save_document(path: str) -> None:
    envelope = await _post("/document/save", {"path": path})
    assert envelope.get("success"), envelope


async def _delete_block(name: str) -> None:
    base_url = _require_host()
    async with native_client(timeout=30.0) as client:
        resp = await client.request(
            "DELETE", f"{base_url}/block",
            json={"name": name, "deleteInstances": True})
    envelope = resp.json()
    assert envelope.get("success"), envelope


async def test_prepare_round_trip_with_nested_block(tmp_path):
    _require_opt_in()
    before = await _doc()
    if before.get("modified"):
        pytest.skip("Live document has unsaved changes; save it first — the "
                    "gate discards unsaved edits by design.")
    original_path = before.get("path") or ""
    assert original_path, "live document must have a path to restore to"

    run = uuid4().hex[:8]
    inner_name = f"S2LiveInner_{run}"
    outer_name = f"S2LiveOuter_{run}"

    # Fixture: inner block (one box), then outer block containing the inner
    # instance + a second box -> outer definition has a Brep member and an
    # InstanceReference member (the nested-recursion proof).
    inner_box = await _create_brep([0.0, 0.0, 0.0], [1.0, 1.0, 1.0],
                                   f"s2_inner_{run}")
    await _make_block(inner_name, [inner_box])
    inner_instance = await _instance_id(inner_name)
    outer_box = await _create_brep([2.0, 0.0, 0.0], [3.0, 1.0, 1.0],
                                   f"s2_outer_{run}")
    await _make_block(outer_name, [outer_box, inner_instance])
    outer_instance = await _instance_id(outer_name)

    # Save the fixture into the (scratch) document: prepare_take's
    # document_not_saved guard refuses to switch away from a dirty doc.
    # The cleanup section below removes the fixture and saves again.
    await _save_document(original_path)

    # Package the take (read-only on the live doc).
    motion = {
        "timeline": {"fps": 24, "frame_count": 48},
        "groups": {"all": ["s2live"]},
        "motion": [
            {"target": "all",
             "keyframes": [{"t": 1, "translate": [0, 0, 100]}]},
            {"target": "s2live_member_0001",
             "keyframes": [{"t": 1, "translate": [0, 0, 50]}]},
        ],
    }
    package = await dtp.package_take({
        "take_id": f"s2live_{run}",
        "output_root": str(tmp_path),
        "actor_sets": [{"actor_set_id": "s2live", "block_name": outer_name,
                        "source_top_level_object_id": outer_instance}],
        "motion": motion,
        "display_modes": ["Shaded"],
    })
    package_root = package["package_root"]
    manifest = json.loads(
        (Path(package_root) / "scene_manifest.json").read_text(encoding="utf-8"))
    member_types = [m["expected"]["type"]
                    for m in manifest["actor_sets"][0]["members"]]
    assert "InstanceReference" in member_types, member_types

    # Prepare: switches to the copy, explodes, maps, resolves.
    result = await dwp.prepare_take({"package_root": package_root})
    assert result["phase"] == "prepared"
    (summary,) = result["actor_sets"]
    assert summary["member_count"] == len(manifest["actor_sets"][0]["members"])
    assert summary["created_object_count"] >= 2

    member_map = json.loads(
        (Path(package_root) / "member_map.json").read_text(encoding="utf-8"))
    members = member_map["actor_sets"][0]["members"]
    nested = [m for m in members if m["member_type"] == "InstanceReference"]
    assert nested, "nested member missing from member map"
    nested_paths = [o["occurrence_path"] for o in nested[0]["occurrences"]]
    assert all("/" in p for p in nested_paths), nested_paths
    for m in members:
        assert m["created_object_ids"], m
        assert m["definition_object_id"] not in m["created_object_ids"], (
            "created object reused the definition-object UUID — fresh-UUID "
            "mandate violated")

    # Created objects really exist in the opened copy.
    all_created = [oid for m in members for oid in m["created_object_ids"]]
    states = await _post("/director/object-states", {"object_ids": all_created})
    assert states.get("success"), states
    assert len(states["data"].get("objects") or []) == len(all_created)

    resolved = json.loads(
        (Path(package_root) / "resolved_motion.json").read_text(encoding="utf-8"))
    assert set(resolved["groups"]["all"]) == set(all_created)
    assert resolved["derived_from"]["member_map_sha256"] == (
        result["member_map_sha256"])

    status = json.loads(
        (Path(package_root) / "status.json").read_text(encoding="utf-8"))
    assert status["phase"] == "prepared"

    # Restore the original document (the fixture is saved in it), then
    # remove the fixture blocks and save the document back to its
    # pre-gate state.
    restore = await _post("/document/open", {"path": original_path})
    assert restore.get("success"), restore
    after = await _doc()
    assert (after.get("path") or "").lower() == original_path.lower()

    await _delete_block(outer_name)   # removes the top-level instance too
    await _delete_block(inner_name)   # definition only; its sole instance
                                      # lived inside the outer definition
    await _save_document(original_path)
    final = await _doc()
    assert final.get("objectCount") == before.get("objectCount"), (
        "fixture cleanup left residue objects")
    assert not final.get("modified")
