from __future__ import annotations

import pytest

from rook.scene.scene_graph import SceneGraphAnalytics


def _scene_graph() -> SceneGraphAnalytics:
    sg = SceneGraphAnalytics()
    sg.graph.add_node("column-owner", name="column_01")
    sg.graph.add_node("slab-owner", name="slab_01")
    sg.graph.add_edge(
        "column-owner",
        "slab-owner",
        key="relationship_fact:architectural:supports",
        relationship="supports",
        projectionKind="relationship_fact_v1",
        semanticRelationshipType="supports",
        relationshipFactId="column_01.top_point_supports_slab_01.underside_region",
        fromFeature="column_01.top_point",
        toFeature="slab_01.underside_region",
        fromFeatureObjectId="feature-column-top",
        toFeatureObjectId="feature-slab-underside",
        contactKind="point_to_region",
        provenance="authored_architectural_fixture",
        confidence=1.0,
        status="accepted",
        graphSource="architectural_relationship_fixture",
        graphRevision="a001",
        pose="architectural_reference",
    )
    return sg


def _user_strings_for(object_id: str) -> dict[str, str]:
    return {
        "feature-column-top": {"rook.graph.true_position_m": "[0.0, 0.0, 3.0]"},
        "feature-slab-underside": {"rook.graph.true_position_m": "[0.0, 0.0, 3.0]"},
    }[object_id]


@pytest.mark.asyncio
async def test_server_tool_schema_exposes_scene_relationship_evidence_parameters():
    from rook.server import list_tools

    tools = {tool.name: tool for tool in await list_tools()}
    schema = tools["scene_relationship_evidence"].inputSchema

    assert schema["required"] == []
    assert schema["properties"]["object_ids"]["items"]["type"] == "string"
    assert schema["properties"]["graph_source"]["type"] == "string"
    assert schema["properties"]["graph_revision"]["type"] == "string"
    assert schema["properties"]["poses"]["items"]["type"] == "string"
    assert schema["properties"]["relationship_types"]["items"]["type"] == "string"
    assert schema["properties"]["relationship_fact_ids"]["items"]["type"] == "string"
    assert schema["properties"]["tolerance_m"]["type"] == "number"
    assert schema["properties"]["port"]["type"] == "integer"
    assert "sync" not in schema["properties"]
    assert "project_first" not in schema["properties"]


def test_tool_group_contains_scene_relationship_evidence():
    from rook.agent.tool_groups import TOOL_GROUPS

    assert "scene_relationship_evidence" in TOOL_GROUPS["scene_graph"]


def test_scene_relationship_evidence_targeting_policy_is_rhino_read():
    from rook import targeting

    pol = targeting.policy_for_tool("scene_relationship_evidence")

    assert pol.requires_rhino is True
    assert pol.risk == "read"
    assert "scene_relationship_evidence" in targeting._ALL_KNOWN_TOOLS


def test_local_dispatcher_registers_scene_relationship_evidence():
    from rook.agent.tool_dispatcher import build_local_tools

    tools = build_local_tools()

    assert "scene_relationship_evidence" in tools
    assert callable(tools["scene_relationship_evidence"])


@pytest.mark.asyncio
async def test_local_scene_relationship_evidence_dispatch_does_not_sync(monkeypatch):
    from rook.scene import relationship_geometry_evidence as evidence

    sg = _scene_graph()
    called = {"sync": 0}

    async def fake_sync(port=None):
        called["sync"] += 1
        return {"success": True}

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        return {"success": True, "data": {"id": payload["id"], "userStrings": _user_strings_for(payload["id"])}}

    monkeypatch.setattr(sg, "sync", fake_sync)
    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)
    monkeypatch.setattr(evidence, "call_rhino", fake_call_rhino)

    from rook.agent.tool_dispatcher import build_local_tools

    result = await build_local_tools()["scene_relationship_evidence"](
        graph_source="architectural_relationship_fixture",
    )

    assert result["success"] is True
    assert result["counts"]["withinToleranceCount"] == 1
    assert called["sync"] == 0


@pytest.mark.asyncio
async def test_server_dispatch_scene_relationship_evidence(monkeypatch):
    from rook.scene import relationship_geometry_evidence as evidence

    sg = _scene_graph()

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        return {"success": True, "data": {"id": payload["id"], "userStrings": _user_strings_for(payload["id"])}}

    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: sg)
    monkeypatch.setattr(evidence, "call_rhino", fake_call_rhino)

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch(
        "scene_relationship_evidence",
        {"graph_source": "architectural_relationship_fixture"},
    )

    assert result["success"] is True
    payload = result["data"]
    assert payload["success"] is True
    assert payload["evidenceKind"] == "relationship_geometry_evidence_v1"
    assert payload["counts"]["measuredEvidenceCount"] == 1


@pytest.mark.asyncio
async def test_server_dispatch_scene_relationship_evidence_reports_hydration_unavailable(monkeypatch):
    from rook.scene import relationship_geometry_evidence as evidence

    async def fake_call_rhino(path, method="GET", payload=None, *, port=None):
        raise RuntimeError("no_rhino_instance")

    monkeypatch.setattr("rook.scene.scene_graph.get_scene_graph", lambda: _scene_graph())
    monkeypatch.setattr(evidence, "call_rhino", fake_call_rhino)

    from rook.server import _call_tool_dispatch

    result = await _call_tool_dispatch(
        "scene_relationship_evidence",
        {"graph_source": "architectural_relationship_fixture"},
    )

    assert result["success"] is False
    assert result["data"]["error"] == "relationship_evidence_hydration_unavailable"
