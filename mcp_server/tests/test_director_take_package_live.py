from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from rook.bridge import native_client
import pytest

from rook import director_take_package as dtp
from .conftest import _create_brep

pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


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


async def _add_box() -> str:
    # Mutates the live doc; the test undoes it before finishing. Uses the
    # same box-creation helper as test_director_routes_live.py (via
    # rhino_create / MCP tool executor) rather than a raw /geometry/box
    # guess — see conftest._create_brep.
    return await _create_brep(
        [0.0, 0.0, 0.0],
        [1.0, 1.0, 1.0],
        f"director_take_package_live_{uuid4().hex}",
    )


async def test_save_copy_four_invariants(tmp_path):
    """THE gate for CRhinoFileWriteOptions mode selection (spec open question 3)."""
    before = await _doc()
    added_id = await _add_box()  # make the doc dirty + create an undo record
    dirty = await _doc()
    assert dirty["modified"] is True
    assert dirty["objectCount"] == before["objectCount"] + 1

    target = tmp_path / "copy.3dm"
    envelope = await _post("/document/save-copy", {"path": str(target)})
    assert envelope.get("success"), envelope
    evidence = envelope["data"]

    # Invariants 1-3: path, title, and modified flag unchanged
    # (native evidence + independent re-read).
    assert evidence["path_before"] == evidence["path_after"]
    assert evidence["title_before"] == evidence["title_after"]
    assert evidence["modified_before"] is True and evidence["modified_after"] is True
    assert evidence["save_small_used"] is False
    after = await _doc()
    assert after["path"] == dirty["path"]
    assert after["modified"] is True

    # Copy-exists proof: nonzero file with a valid 3dm header. This does NOT
    # prove render meshes are present — that open-fidelity proof belongs to
    # the Slice 2 worker gate; save_small_used=False is the route's evidence.
    assert target.is_file() and target.stat().st_size > 0
    assert target.read_bytes()[:24].startswith(b"3D Geometry File Format")

    # Invariant 4: the undo stack survived the write — undo removes the box.
    envelope = await _post("/undo", {})
    assert envelope.get("success"), envelope
    restored = await _doc()
    assert restored["objectCount"] == before["objectCount"]


async def test_package_round_trip_against_live_doc(tmp_path):
    doc = await _doc()
    blocks = await _get("/blocks")
    assert blocks.get("success"), blocks
    placed = [b for b in blocks["data"]["blocks"]
              if b.get("instanceCount", 0) > 0 and b.get("objectCount", 0) >= 2]
    if not placed:
        pytest.skip("live doc has no placed multi-member block to package")
    block = placed[0]

    instances = await _post("/block/instances", {"name": block["name"]})
    if not instances.get("success") or not instances["data"].get("instances"):
        pytest.skip("could not resolve an instance id for the block")
    instance_id = instances["data"]["instances"][0]["id"]

    modes = await _get("/display-modes")
    mode_name = modes["data"]["modes"][0]["name"]

    result = await dtp.package_take({
        "output_root": str(tmp_path),
        "take_id": "live_gate_take",
        "actor_sets": [{"actor_set_id": "live_gate_set", "block_name": block["name"],
                        "source_top_level_object_id": instance_id}],
        "motion": {"timeline": {"fps": 24, "frame_count": 8},
                   "motion": [{"target": "live_gate_set",
                               "keyframes": [{"t": 1, "translate": [0, 0, 100]}]}]},
        "camera": None,
        "display_modes": [mode_name],
    })

    root = Path(result["package_root"])
    manifest = json.loads((root / "scene_manifest.json").read_text())
    assert manifest["actor_sets"][0]["member_count"] == block["objectCount"]
    # DEC-021 live proof: every manifest member carries tight-bbox evidence.
    for member in manifest["actor_sets"][0]["members"]:
        assert member["bbox_evidence"]["bbox_method"] == "tight_object"
        assert member["bbox_evidence"]["validation_strength"] == "tight_bbox"
    # Source-instance evidence proves the Task 1 /block/instances extension
    # is actually present in the deployed native route.
    src = manifest["actor_sets"][0]["source_instance"]
    assert src["instance_id"] == instance_id
    assert src["definition_id"] and src["definition_name"]
    assert len(src["xform"]) == 4 and all(len(row) == 4 for row in src["xform"])
    assert len(src["xform_sha256"]) == 64
    assert (root / "scene.3dm").stat().st_size > 0
    assert manifest["scene"]["mechanism"] in ("save_copy", "raw_copy_saved_file")
    # Live doc untouched:
    after = await _doc()
    assert after["objectCount"] == doc["objectCount"]
    assert after["modified"] == doc["modified"]
