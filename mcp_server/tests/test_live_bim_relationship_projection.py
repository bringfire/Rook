from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from rook.bridge import call_rhino, discover_instances
from rook.scene import bim_relationship_projection as bim
from rook.scene.scene_graph import SceneGraphAnalytics


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

_LIVE_FIXTURE_DIR = Path(os.environ.get("ROOK_BIM_LIVE_FIXTURE_DIR") or Path(tempfile.gettempdir()) / "rookbim_preset_live_fix")
MODEL_3DM = _LIVE_FIXTURE_DIR / "shell-preset.3dm"
SIDECAR_JSON = _LIVE_FIXTURE_DIR / "shell-preset.sidecar.json"


def _native_port_or_skip() -> int:
    scoped_port = os.environ.get("ROOK_RHINO_PORT")
    if scoped_port:
        try:
            port = int(scoped_port)
        except ValueError:
            pytest.skip(f"ROOK_RHINO_PORT is not a valid integer: {scoped_port!r}")
        if port > 0:
            return port
        pytest.skip(f"ROOK_RHINO_PORT must be positive: {scoped_port!r}")

    for instance in discover_instances():
        if not isinstance(instance, dict):
            continue
        if instance.get("pluginType") != "native" or not instance.get("port"):
            continue
        try:
            return int(instance.get("port"))
        except (TypeError, ValueError):
            continue
    pytest.skip("No native RookNative instance discovered")


def _skip_if_fixture_missing() -> None:
    missing = [str(path) for path in (MODEL_3DM, SIDECAR_JSON) if not path.is_file()]
    if missing:
        pytest.skip(f"BIM relationship live fixture missing: {', '.join(missing)}")


def _assert_route_success(route: str, response: dict[str, Any]) -> None:
    assert response.get("success") is not False, f"{route} failed: {response!r}"


async def _select_level_joinable_object_id(analytics: SceneGraphAnalytics, port: int) -> str:
    sidecar, _ = bim.load_sidecar_path(
        SIDECAR_JSON,
        include_rooms=True,
        include_levels=True,
    )
    level_joinable_uids = {membership.element_uid for membership in sidecar.level_memberships}

    for node_id in analytics.graph.nodes:
        response = await call_rhino(
            "/usertext/object-get",
            "POST",
            {"id": str(node_id)},
            port=port,
        )
        if response.get("success") is False:
            continue
        data = response.get("data")
        if not isinstance(data, dict):
            continue
        user_strings = data.get("userStrings")
        if not isinstance(user_strings, dict):
            continue
        revit_uid = str(user_strings.get("revit.uniqueId") or "")
        if revit_uid in sidecar.elements_by_uid and revit_uid in level_joinable_uids:
            return str(node_id)

    pytest.fail("No live scene object had Revit user strings matching a level sidecar relationship")


async def test_live_bim_relationship_projection_wires_sidecar_into_scene_graph_context(monkeypatch):
    _skip_if_fixture_missing()
    port = _native_port_or_skip()

    new_result = await call_rhino("/document/new", "POST", {}, port=port)
    _assert_route_success("/document/new", new_result)

    open_result = await call_rhino(
        "/document/open",
        "POST",
        {"path": str(MODEL_3DM)},
        port=port,
    )
    _assert_route_success("/document/open", open_result)

    analytics = SceneGraphAnalytics()
    sync_result = await analytics.sync(port=port)
    assert sync_result.get("synced") is True, f"scene graph sync failed: {sync_result!r}"

    joined_object_id = await _select_level_joinable_object_id(analytics, port)
    analytics.graph = analytics.graph.subgraph([joined_object_id]).copy()

    async def _use_current_scene_graph(port: int | None = None) -> dict[str, Any]:
        return {
            "synced": True,
            "mode": "live_test_snapshot",
            "nodes": analytics.node_count,
            "edges": analytics.edge_count,
            "sequence": analytics.sequence,
        }

    monkeypatch.setattr(analytics, "sync", _use_current_scene_graph)

    result = await bim.project_bim_relationships_for_tool(
        str(SIDECAR_JSON),
        include_rooms=True,
        include_levels=True,
        port=port,
        analytics=analytics,
    )

    assert result["success"] is True
    assert result["joinedObjectCount"] > 0
    assert result["projectedLevelEdges"] > 0
    assert result["projectedHostEdges"] >= 0

    joined_object_ids = [
        str(node_id)
        for node_id, attrs in analytics.graph.nodes(data=True)
        if attrs.get("rookbimJoined") is True
    ]
    assert joined_object_ids
    assert "Revit" in analytics.get_context([joined_object_ids[0]])
