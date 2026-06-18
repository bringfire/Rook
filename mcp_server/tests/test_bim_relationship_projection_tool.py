import json

import pytest

from rook.scene import bim_relationship_projection as bim
from rook.scene.scene_graph import SceneGraphAnalytics


def _sidecar_payload() -> dict:
    return {
        "schemaVersion": 1,
        "elements": [
            {
                "identity": {"uniqueId": "uid-wall", "elementId": 100},
                "category": "Walls",
                "family": "Basic Wall",
                "type": "Generic 200mm",
                "name": "Wall Type",
                "labels": {"level": {"value": "L1"}},
            },
            {
                "identity": {"uniqueId": "uid-door", "elementId": 200},
                "category": "Doors",
                "family": "Single-Flush",
                "type": "0915 x 2134mm",
                "name": "Door Type",
                "labels": {"level": {"value": "L1"}},
            },
        ],
        "rooms": [{"uniqueId": "room-1", "number": "101", "name": "Office"}],
        "relationships": {
            "hostMembership": [
                {
                    "elementUniqueId": "uid-door",
                    "hostUniqueId": "uid-wall",
                    "source": "revit_api",
                    "confidence": "high",
                }
            ],
            "roomMembership": [
                {
                    "elementUniqueId": "uid-door",
                    "roomUniqueId": "room-1",
                    "source": "revit_api",
                    "confidence": "high",
                }
            ],
            "levelMembership": [
                {
                    "elementUniqueId": "uid-wall",
                    "levelName": "L1",
                    "source": "revit_api",
                    "confidence": "high",
                },
                {
                    "elementUniqueId": "uid-door",
                    "levelName": "L1",
                    "source": "revit_api",
                    "confidence": "high",
                },
            ],
        },
    }


def _write_sidecar(tmp_path, payload: dict | None = None):
    path = tmp_path / "relationships.sidecar.json"
    path.write_text(json.dumps(payload or _sidecar_payload()), encoding="utf-8")
    return path


def _scene_graph() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node("rh-wall", name="Wall", domain_label="wall", shape_class="vertical-planar")
    sg.graph.add_node("rh-door", name="Door", domain_label="door", shape_class="compact")
    sg._sequence = 4
    return sg


def test_tool_group_contains_scene_project_bim_relationships():
    from rook.agent.tool_groups import TOOL_GROUPS

    assert "scene_project_bim_relationships" in TOOL_GROUPS["scene_graph"]


def test_targeting_policy_is_rhino_read():
    from rook import targeting

    pol = targeting.policy_for_tool("scene_project_bim_relationships")

    assert pol.requires_rhino is True
    assert pol.risk == "read"
    assert "scene_project_bim_relationships" in targeting._ALL_KNOWN_TOOLS


@pytest.mark.asyncio
async def test_server_tool_schema_exposes_bim_projection_parameters():
    from rook.server import list_tools

    tools = {tool.name: tool for tool in await list_tools()}
    schema = tools["scene_project_bim_relationships"].inputSchema

    assert set(schema["properties"]) >= {
        "sidecar_path",
        "object_ids",
        "category_filters",
        "include_rooms",
        "include_levels",
        "port",
    }
    assert schema["required"] == ["sidecar_path"]


def test_local_dispatcher_registers_scene_project_bim_relationships():
    from rook.agent.tool_dispatcher import build_local_tools

    tools = build_local_tools()

    assert "scene_project_bim_relationships" in tools
    assert callable(tools["scene_project_bim_relationships"])


@pytest.mark.asyncio
async def test_tool_orchestration_hydrates_projects_and_preserves_same_sequence_facts(tmp_path, monkeypatch):
    sidecar_path = _write_sidecar(tmp_path)
    sg = _scene_graph()

    async def fake_sync(port=None):
        assert port == 9876
        return {"synced": True, "sequence": sg.sequence}

    calls = []

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        calls.append((path, method, payload, port))
        assert path == "/usertext/object-get"
        assert method == "POST"
        assert port == 9876
        object_id = payload["id"]
        user_strings = {
            "rh-wall": {
                "revit.uniqueId": "uid-wall",
                "revit.elementId": "100",
                "revit.category": "Walls",
            },
            "rh-door": {
                "revit.uniqueId": "uid-door",
                "revit.elementId": "200",
                "revit.category": "Doors",
            },
        }[object_id]
        return {"success": True, "data": {"id": object_id, "userStrings": user_strings}}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr(bim, "call_rhino", fake_call_rhino)

    first = await bim.project_bim_relationships_for_tool(
        str(sidecar_path),
        port=9876,
        analytics=sg,
    )

    assert first["success"] is True
    assert first["candidateObjectCount"] == 2
    assert first["hydratedCount"] == 2
    assert first["joinableCount"] == 2
    assert first["eligibleObjectCount"] == 2
    assert first["joinedObjectCount"] == 2
    assert first["projectedHostEdges"] == 1
    assert first["projectedLevelEdges"] == 2
    assert first["graphSequence"] == 4
    assert first["sidecarPath"] == str(sidecar_path)
    assert first["projectionKind"] == bim.PROJECTION_KIND
    assert first["provenance"] == bim.PROVENANCE
    assert first["pruned"] is False

    fp = bim.fingerprint_sidecar_path(sidecar_path)
    level_id = bim.level_node_id(fp, "L1")
    wall_level_key = bim.level_edge_key(fp, "uid-wall", "L1")
    assert sg.graph.has_edge("rh-wall", level_id, wall_level_key)

    second = await bim.project_bim_relationships_for_tool(
        str(sidecar_path),
        object_ids=["rh-door"],
        port=9876,
        analytics=sg,
    )

    assert second["success"] is True
    assert second["pruned"] is False
    assert second["eligibleObjectCount"] == 1
    assert second["projectedHostEdges"] == 1
    assert second["projectedLevelEdges"] == 1
    assert sg.graph.has_edge("rh-wall", level_id, wall_level_key)
    assert all(call[0] == "/usertext/object-get" for call in calls)


@pytest.mark.asyncio
async def test_tool_returns_zero_join_failure_with_per_object_hydration_diagnostics(tmp_path, monkeypatch):
    sidecar_path = _write_sidecar(tmp_path)
    sg = _scene_graph()

    async def fake_sync(port=None):
        return {"synced": True, "sequence": sg.sequence}

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        if payload["id"] == "rh-wall":
            return {"success": False, "data": {"errorCode": "not_found"}}
        return {"success": True, "data": {"id": payload["id"], "userStrings": {}}}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr(bim, "call_rhino", fake_call_rhino)

    result = await bim.project_bim_relationships_for_tool(str(sidecar_path), analytics=sg)

    assert result["success"] is False
    assert result["error"] == "bim_projection_no_eligible_scene_objects"
    assert result["candidateObjectCount"] == 2
    assert result["hydratedCount"] == 1
    assert result["joinableCount"] == 0
    assert result["eligibleObjectCount"] == 0
    assert result["diagnostics"]["hydrationFailures"] == 1
    assert result["diagnostics"]["objectsMissingRevitUniqueId"] == 1


@pytest.mark.asyncio
async def test_server_boundary_returns_invalid_sidecar_error_response(tmp_path, monkeypatch):
    bad_sidecar = tmp_path / "bad.sidecar.json"
    bad_sidecar.write_text("{not json", encoding="utf-8")
    sg = _scene_graph()

    async def fake_sync(port=None):
        return {"synced": True, "sequence": sg.sequence}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)

    from rook.server import _mcp_tool_executor

    result = await _mcp_tool_executor(
        "scene_project_bim_relationships",
        {"sidecar_path": str(bad_sidecar)},
    )

    assert result["success"] is False
    payload = result["data"]
    assert payload["success"] is False
    assert payload["error"] == "bim_projection_invalid_sidecar"
    assert "sidecar" in payload["message"].lower()


@pytest.mark.asyncio
async def test_server_boundary_returns_zero_join_as_error_response(tmp_path, monkeypatch):
    sidecar_path = _write_sidecar(tmp_path)
    sg = _scene_graph()

    async def fake_sync(port=None):
        return {"synced": True, "sequence": sg.sequence}

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        return {"success": True, "data": {"id": payload["id"], "userStrings": {}}}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)
    monkeypatch.setattr(bim, "call_rhino", fake_call_rhino)

    from rook.server import _mcp_tool_executor

    result = await _mcp_tool_executor(
        "scene_project_bim_relationships",
        {"sidecar_path": str(sidecar_path)},
    )

    assert result["success"] is False
    payload = result["data"]
    assert payload["success"] is False
    assert payload["error"] == "bim_projection_no_eligible_scene_objects"
    assert payload["joinableCount"] == 0


@pytest.mark.asyncio
async def test_direct_call_tool_marks_missing_sidecar_path_as_error_textcontent():
    from rook.server import call_tool

    result = await call_tool("scene_project_bim_relationships", {})

    assert len(result) == 1
    text = result[0].text
    assert text.startswith("Error: ")
    payload = json.loads(text[len("Error: "):])
    assert payload["success"] is False
    assert payload["error"] == "bim_projection_invalid_sidecar"


@pytest.mark.asyncio
async def test_scene_context_sync_false_skips_sync_and_reads_current_mirror(monkeypatch):
    sg = _scene_graph()
    sg.graph.nodes["rh-door"]["rookbimJoined"] = True
    sg.graph.nodes["rh-door"]["revitCategory"] = "Doors"
    called = {"sync": 0}

    async def fake_sync(port=None):
        called["sync"] += 1
        return {"synced": True}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch(
        "scene_context",
        {"object_ids": ["rh-door"], "sync": False},
    )

    assert result["success"] is True
    assert called["sync"] == 0
    assert "BIM:" in result["data"]
