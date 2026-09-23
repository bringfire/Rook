"""Pearson roof TL_Brep live gate.

Requires ROOK_PEARSON_TL_BREP=1 and the production Pearson document open in
Rhino, saved and unmodified. This test packages the real roof actor set from
the live document, prepares the disposable copy, compiles the take, and reopens
the original document afterward. It must not modify the live Pearson document.
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
from rook import director_worker_compile as dwc
from rook import director_worker_prepare as dprep

pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

PEARSON_ROOF_BLOCK_NAME = "3D_BLOCK_ARCH_ROOF_0502 UPLIFT ROOF - VERTICAL"
PEARSON_ROOF_INSTANCE_ID = "a28cbdb5-51fa-46b2-b18b-ab880b54ded7"
EXPECTED_MEMBER_COUNT = 890
EXPECTED_TL_BREP_CONVERSIONS = 4


def _require_opt_in() -> None:
    if os.environ.get("ROOK_PEARSON_TL_BREP") != "1":
        pytest.skip("Set ROOK_PEARSON_TL_BREP=1 to run the Pearson TL_Brep gate.")


def _require_host() -> str:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")
    return base_url  # type: ignore[return-value]


async def _call_live_native(endpoint: str, method: str = "GET",
                            data: dict[str, Any] | None = None,
                            port: int | None = None) -> dict[str, Any]:
    del port
    base_url = _require_host()
    async with native_client(timeout=900.0) as client:
        if method == "GET":
            resp = await client.get(f"{base_url}{endpoint}")
        else:
            resp = await client.post(
                f"{base_url}{endpoint}",
                json=data if data is not None else {})
    return resp.json()


async def _post(route: str, body: dict[str, Any]) -> dict[str, Any]:
    return await _call_live_native(route, "POST", body)


async def _get(route: str) -> dict[str, Any]:
    return await _call_live_native(route, "GET", None)


async def _doc() -> dict[str, Any]:
    envelope = await _get("/document")
    assert envelope.get("success"), envelope
    return envelope["data"]


async def _assert_roof_instance_present() -> None:
    envelope = await _post("/block/instances", {"name": PEARSON_ROOF_BLOCK_NAME})
    assert envelope.get("success"), envelope
    instances = envelope["data"].get("instances") or []
    instance_ids = {entry.get("id") for entry in instances}
    assert PEARSON_ROOF_INSTANCE_ID in instance_ids, (
        f"Pearson roof instance {PEARSON_ROOF_INSTANCE_ID} not found; "
        f"available ids: {sorted(instance_ids)}")


def _motion() -> dict[str, Any]:
    return {
        "timeline": {"fps": 24, "frame_count": 48},
        "groups": {"roof": ["pearson_roof"]},
        "motion": [{
            "target": "roof",
            "keyframes": [
                {"t": 0},
                {"t": 1, "translate": [0.0, 0.0, 8000.0]},
            ],
        }],
    }


async def test_pearson_roof_tl_brep_prepare_compile(tmp_path):
    _require_opt_in()
    before = await _doc()
    if before.get("modified"):
        pytest.skip("Pearson document has unsaved changes; save before running.")
    original_path = before.get("path") or ""
    assert original_path, "Pearson document must have a path to restore to"
    await _assert_roof_instance_present()

    run = uuid4().hex[:8]
    package_root: str | None = None
    try:
        package = await dtp.package_take({
            "take_id": f"pearson_tl_brep_{run}",
            "output_root": str(tmp_path),
            "actor_sets": [{
                "actor_set_id": "pearson_roof",
                "block_name": PEARSON_ROOF_BLOCK_NAME,
                "source_top_level_object_id": PEARSON_ROOF_INSTANCE_ID,
            }],
            "motion": _motion(),
            "display_modes": ["Shaded"],
        })
        package_root = package["package_root"]
        manifest = json.loads(
            (Path(package_root) / "scene_manifest.json").read_text(encoding="utf-8"))
        members = manifest["actor_sets"][0]["members"]
        assert len(members) == EXPECTED_MEMBER_COUNT

        prepare = await dprep.prepare_take({"package_root": package_root})
        assert prepare["phase"] == "prepared"
        (summary,) = prepare["actor_sets"]
        assert summary["member_count"] == EXPECTED_MEMBER_COUNT
        assert summary["created_object_count"] >= EXPECTED_MEMBER_COUNT

        member_map = json.loads(
            (Path(package_root) / "member_map.json").read_text(encoding="utf-8"))
        mapped_members = member_map["actor_sets"][0]["members"]
        all_occurrences = [
            occurrence
            for member in mapped_members
            for occurrence in member["occurrences"]
        ]
        conversions = [
            occurrence for occurrence in all_occurrences
            if occurrence.get("converted_from") == "TL_Brep"
        ]
        assert len(conversions) == EXPECTED_TL_BREP_CONVERSIONS, conversions
        assert {
            occurrence.get("conversion_path") for occurrence in conversions
        } <= {"clean_copy", "brep_form"}
        assert all(member["created_object_ids"] for member in mapped_members)

        compile_result = await dwc.compile_take({"package_root": package_root})
        assert compile_result["phase"] == "compiled"
        assert compile_result["animated_object_count"] == summary["created_object_count"]

        print(f"Pearson TL_Brep package_root={package_root}")
        print(f"Pearson TL_Brep conversions={conversions}")
    finally:
        restore = await _post("/document/open", {"path": original_path})
        assert restore.get("success"), restore
        after = await _doc()
        assert (after.get("path") or "").lower() == original_path.lower()
        assert not after.get("modified")
