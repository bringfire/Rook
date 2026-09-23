"""Live-Rhino characterization tests for POST /surface/patch (Phase 2 PR-2).

Pins the worked-example contract for the managed-bridge (reuse) substrate:
  - full ObjectSnapshot on success (singular-contract)
  - structured {errorCode, errorMessage} on failure
  - dispatch branch on startingSurfaceId presence (overload 2 vs 3)
  - dependency rule: flexibility/surfacePull require startingSurfaceId
  - worker-thread rejections for uSpans/vSpans/flexibility/tolerance (<=0)
  - managed-strict filtering for geometryIds (curve/point/cloud whitelist)
  - managed seed-surface resolution (single-face Brep auto-extract)
  - real Rhino-side failure: single-point-only geometryIds -> operation_failed

Run (from repo root):
    pytest -m requires_rhino mcp_server/tests/test_patch_live.py

See rook_docs/2026-04-20-phase2-surface-curve-plan.md (§/surface/patch)
for the binding contract these tests pin. Overload findings pinned
empirically 2026-04-20 before implementation.
"""

from __future__ import annotations

from typing import Any

from rook.bridge import native_client
import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


# --- Helpers --------------------------------------------------------------


async def _create_interp_curve(points: list[list[float]], name: str) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_execute",
        {"code": (
            "import rhinoscriptsyntax as rs\n"
            f"_id = rs.AddInterpCurve({points!r})\n"
            "print(str(_id))\n"
        )},
    )
    assert not _is_error(res), f"AddInterpCurve failed: {res!r}"
    # Parse printed ID from stdout
    output = res.get("output", "").strip()
    assert output, f"No output from AddInterpCurve: {res!r}"
    return output.splitlines()[-1].strip()


async def _create_point(point: list[float], name: str) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "POINT", "point": point, "name": name},
    )
    assert not _is_error(res), f"rhino_create POINT failed: {res!r}"
    return res["id"]


async def _create_plane_surface(origin: list[float], width: float, height: float, name: str) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_execute",
        {"code": (
            "import rhinoscriptsyntax as rs\n"
            f"_id = rs.AddPlaneSurface({origin!r}, {width}, {height})\n"
            "print(str(_id))\n"
        )},
    )
    assert not _is_error(res), f"AddPlaneSurface failed: {res!r}"
    output = res.get("output", "").strip()
    assert output, f"No output from AddPlaneSurface: {res!r}"
    return output.splitlines()[-1].strip()


async def _create_line(start: list[float], end: list[float], name: str) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "LINE", "start": start, "end": end, "name": name},
    )
    assert not _is_error(res), f"rhino_create LINE failed: {res!r}"
    return res["id"]


async def _post_patch_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=15.0) as client:
        resp = await client.post(f"{base_url}/surface/patch", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/surface/patch returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


def _assert_structured_error(envelope: dict[str, Any], expected_code: str) -> None:
    assert envelope.get("success") is False, f"Expected failure envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected structured data dict: {envelope!r}"
    assert data.get("errorCode") == expected_code, (
        f"Expected errorCode={expected_code!r}, got {data.get('errorCode')!r} in {envelope!r}"
    )
    assert isinstance(data.get("errorMessage"), str) and data["errorMessage"], (
        f"Expected non-empty errorMessage in {envelope!r}"
    )


def _assert_object_snapshot(snapshot: Any) -> None:
    assert isinstance(snapshot, dict), f"Expected ObjectSnapshot dict, got {snapshot!r}"
    for key in ("id", "type"):
        assert key in snapshot, f"ObjectSnapshot missing {key!r}: {snapshot!r}"


async def _build_boundary_curves() -> list[str]:
    """4-curve interpolated boundary (probe geometry). Returns IDs."""
    return [
        await _create_interp_curve([[0,0,0],[5,0,1],[10,0,0]], "BoundA"),
        await _create_interp_curve([[10,0,0],[10,5,1],[10,10,0]], "BoundB"),
        await _create_interp_curve([[10,10,0],[5,10,1],[0,10,0]], "BoundC"),
        await _create_interp_curve([[0,10,0],[0,5,1],[0,0,0]], "BoundD"),
    ]


# --- Happy-path tests ------------------------------------------------------


async def test_patch_no_seed_4_curves(fresh_document):
    """(a) 4-curve boundary, no seed -> 1 brep via overload 2 path."""
    from rook.server import _mcp_tool_executor

    ids = await _build_boundary_curves()
    res = await _mcp_tool_executor(
        "rhino_create_patch",
        {"geometryIds": ids, "name": "PatchNoSeed"},
    )
    assert not _is_error(res), f"No-seed patch failed: {res!r}"
    _assert_object_snapshot(res)


async def test_patch_curves_plus_points(fresh_document):
    """(b) curves + interior points -> 1 brep fits both."""
    from rook.server import _mcp_tool_executor

    ids = await _build_boundary_curves()
    p_id = await _create_point([5, 5, 3], "InteriorPoint")
    res = await _mcp_tool_executor(
        "rhino_create_patch",
        {"geometryIds": ids + [p_id], "name": "PatchWithPoint"},
    )
    assert not _is_error(res), f"Curves+point patch failed: {res!r}"
    _assert_object_snapshot(res)


async def test_patch_curves_plus_cloud(fresh_document):
    """(c) curves + point cloud -> 1 brep."""
    from rook.server import _mcp_tool_executor

    ids = await _build_boundary_curves()
    # Build a small point cloud via rhinoscriptsyntax
    cloud_res = await _mcp_tool_executor(
        "rhino_execute",
        {"code": (
            "import rhinoscriptsyntax as rs\n"
            "_id = rs.AddPointCloud([[2,2,0.5],[5,5,0.5],[8,8,0.5]])\n"
            "print(str(_id))\n"
        )},
    )
    assert not _is_error(cloud_res), f"AddPointCloud failed: {cloud_res!r}"
    cloud_id = cloud_res["output"].strip().splitlines()[-1]

    res = await _mcp_tool_executor(
        "rhino_create_patch",
        {"geometryIds": ids + [cloud_id], "name": "PatchWithCloud"},
    )
    assert not _is_error(res), f"Curves+cloud patch failed: {res!r}"
    _assert_object_snapshot(res)


async def test_patch_with_seed(fresh_document):
    """(d) with plane-surface seed -> overload 3 path; auto-extracts UnderlyingSurface."""
    from rook.server import _mcp_tool_executor

    ids = await _build_boundary_curves()
    seed_id = await _create_plane_surface([0, 0, 0], 10, 10, "SeedSurface")
    res = await _mcp_tool_executor(
        "rhino_create_patch",
        {
            "geometryIds": ids,
            "startingSurfaceId": seed_id,
            "flexibility": 1.0,
            "surfacePull": 1.0,
            "name": "PatchWithSeed",
        },
    )
    assert not _is_error(res), f"Seeded patch failed: {res!r}"
    _assert_object_snapshot(res)


# --- Validation-error tests -----------------------------------------------


async def test_patch_missing_geometryids(fresh_document):
    """(e) missing geometryIds -> invalid_input."""
    status, envelope = await _post_patch_raw({})
    _assert_structured_error(envelope, "invalid_input")


async def test_patch_uspans_zero(fresh_document):
    """(f) uSpans=0 -> invalid_spans (worker-thread rejection; factory would coerce)."""
    ids = await _build_boundary_curves()
    status, envelope = await _post_patch_raw({"geometryIds": ids, "uSpans": 0})
    _assert_structured_error(envelope, "invalid_spans")


async def test_patch_flexibility_negative(fresh_document):
    """(g) flexibility=-1 with seed -> invalid_flexibility."""
    ids = await _build_boundary_curves()
    seed_id = await _create_plane_surface([0, 0, 0], 10, 10, "SeedFlex")
    status, envelope = await _post_patch_raw({
        "geometryIds": ids,
        "startingSurfaceId": seed_id,
        "flexibility": -1.0,
    })
    _assert_structured_error(envelope, "invalid_flexibility")


async def test_patch_flexibility_requires_seed(fresh_document):
    """(h) flexibility set without startingSurfaceId -> invalid_input (dependency rule)."""
    ids = await _build_boundary_curves()
    status, envelope = await _post_patch_raw({
        "geometryIds": ids,
        "flexibility": 1.5,
    })
    _assert_structured_error(envelope, "invalid_input")
    assert "startingSurfaceId" in envelope["data"]["errorMessage"], (
        f"Expected dependency message: {envelope!r}"
    )


async def test_patch_surfacepull_requires_seed(fresh_document):
    """(i) surfacePull set without startingSurfaceId -> invalid_input (dependency rule)."""
    ids = await _build_boundary_curves()
    status, envelope = await _post_patch_raw({
        "geometryIds": ids,
        "surfacePull": 2.0,
    })
    _assert_structured_error(envelope, "invalid_input")
    assert "startingSurfaceId" in envelope["data"]["errorMessage"], (
        f"Expected dependency message: {envelope!r}"
    )


async def test_patch_tolerance_zero(fresh_document):
    """(j) tolerance=0 -> invalid_input (worker-thread; factory would produce ~50% larger surface)."""
    ids = await _build_boundary_curves()
    status, envelope = await _post_patch_raw({"geometryIds": ids, "tolerance": 0.0})
    _assert_structured_error(envelope, "invalid_input")


async def test_patch_brep_face_in_geometryids(fresh_document):
    """(k) brep input in geometryIds -> invalid_geometry_class.

    Factory would accept this silently; route pre-filters for contract
    clarity (Curve / Point / PointCloud whitelist).
    """
    from rook.server import _mcp_tool_executor

    ids = await _build_boundary_curves()
    box_res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "BOX", "corner1": [0, 0, 0], "corner2": [1, 1, 1], "name": "BoxInput"},
    )
    assert not _is_error(box_res), f"Box create failed: {box_res!r}"
    status, envelope = await _post_patch_raw({"geometryIds": ids + [box_res["id"]]})
    _assert_structured_error(envelope, "invalid_geometry_class")


async def test_patch_mesh_in_geometryids(fresh_document):
    """(l) mesh input in geometryIds -> invalid_geometry_class."""
    from rook.server import _mcp_tool_executor

    ids = await _build_boundary_curves()
    # Build a small mesh via rhinoscriptsyntax (AddMesh takes vertices + face
    # indices; the typed rhino_mesh_box tool has its own corner-free schema
    # not suited to this test).
    mesh_res = await _mcp_tool_executor(
        "rhino_execute",
        {"code": (
            "import rhinoscriptsyntax as rs\n"
            "_id = rs.AddMesh([[0,0,0],[1,0,0],[1,1,0],[0,1,0]], [[0,1,2,3]])\n"
            "print(str(_id))\n"
        )},
    )
    assert not _is_error(mesh_res), f"AddMesh failed: {mesh_res!r}"
    mesh_id = mesh_res.get("output", "").strip().splitlines()[-1]
    assert mesh_id, f"Mesh creation returned no id: {mesh_res!r}"

    status, envelope = await _post_patch_raw({"geometryIds": ids + [mesh_id]})
    _assert_structured_error(envelope, "invalid_geometry_class")


async def test_patch_single_point_only_operation_failed(fresh_document):
    """(m) single-point-only input -> operation_failed (empirically verified 2026-04-20).

    Pins the real Rhino-side failure case identified during the pre-implementation
    probe. Satisfies the Common Plan's amended rule without needing
    test_factory_permissive_smoke.
    """
    p_id = await _create_point([5, 5, 0], "LonePoint")
    status, envelope = await _post_patch_raw({"geometryIds": [p_id]})
    _assert_structured_error(envelope, "operation_failed")


async def test_patch_seed_malformed_uuid(fresh_document):
    """(n) startingSurfaceId malformed UUID -> invalid_input."""
    ids = await _build_boundary_curves()
    status, envelope = await _post_patch_raw({
        "geometryIds": ids,
        "startingSurfaceId": "not-a-uuid",
    })
    _assert_structured_error(envelope, "invalid_input")


async def test_patch_seed_multi_face_brep(fresh_document):
    """(o) seed refers to multi-face Brep -> invalid_seed_class."""
    from rook.server import _mcp_tool_executor

    ids = await _build_boundary_curves()
    box_res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "BOX", "corner1": [0, 0, 0], "corner2": [1, 1, 1], "name": "MultiFaceSeed"},
    )
    assert not _is_error(box_res), f"Box create failed: {box_res!r}"
    status, envelope = await _post_patch_raw({
        "geometryIds": ids,
        "startingSurfaceId": box_res["id"],
    })
    _assert_structured_error(envelope, "invalid_seed_class")


async def test_patch_seed_wrong_class_curve(fresh_document):
    """(p) seed refers to a curve (wrong class entirely) -> invalid_seed_class."""
    ids = await _build_boundary_curves()
    line_id = await _create_line([0, 0, 0], [10, 0, 0], "CurveAsSeed")
    status, envelope = await _post_patch_raw({
        "geometryIds": ids,
        "startingSurfaceId": line_id,
    })
    _assert_structured_error(envelope, "invalid_seed_class")


async def test_patch_full_attribute_bundle(fresh_document):
    """(q) happy path with full attribute bundle -> response echoes attrs."""
    from rook.server import _mcp_tool_executor

    # Tolerant layer-create (prior test runs may have created it).
    layer_res = await _mcp_tool_executor(
        "rhino_layer_create",
        {"name": "PatchTest"},
    )
    if _is_error(layer_res):
        err_text = str(layer_res.get("data", ""))
        assert "already exists" in err_text, f"Layer create failed: {layer_res!r}"

    ids = await _build_boundary_curves()
    res = await _mcp_tool_executor(
        "rhino_create_patch",
        {
            "geometryIds": ids,
            "name": "BundledPatch",
            "layer": "PatchTest",
            "color": "#80c0ff",
            "visible": True,
        },
    )
    assert not _is_error(res), f"Bundled patch failed: {res!r}"
    _assert_object_snapshot(res)
    assert res.get("name") == "BundledPatch", f"name echo failed: {res!r}"
    assert res.get("layer") == "PatchTest", f"layer echo failed: {res!r}"
