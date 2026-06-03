import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import server
from rook import bridge
from rook import targeting


@pytest.mark.asyncio
async def test_session_tools_are_registered():
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert "rhino_sessions" in names
    assert "rhino_session_capabilities" in names

    gsc = next(t for t in tools if t.name == "rhino_session_capabilities")
    assert gsc.inputSchema["required"] == ["session"]
    assert "session" in gsc.inputSchema["properties"]


@pytest.mark.asyncio
async def test_dispatch_list_sessions(monkeypatch):
    # server.py imports these names directly (server.py:52 pattern), so dispatch
    # calls server.list_sessions_result — patch THERE, not on the bridge module,
    # or the monkeypatch won't intercept.
    monkeypatch.setattr(
        server, "list_sessions_result",
        lambda: {"success": True, "data": {"sessions": [{"session": "rhino-1"}]}},
    )
    result = await server._call_tool_dispatch("rhino_sessions", {})
    assert result["success"] is True
    assert result["data"]["sessions"][0]["session"] == "rhino-1"


@pytest.mark.asyncio
async def test_dispatch_get_session_capabilities(monkeypatch):
    async def fake_gsc(session):
        return {"success": True, "data": {"session": session, "capabilities": {}}}

    monkeypatch.setattr(server, "get_session_capabilities", fake_gsc)
    result = await server._call_tool_dispatch(
        "rhino_session_capabilities", {"session": "rhino-7"}
    )
    assert result["success"] is True
    assert result["data"]["session"] == "rhino-7"


def test_session_tools_are_meta_policy():
    # Must be meta (requires_rhino=False), like rhino_instances. Otherwise the
    # outer call_tool routes them through resolve_tool_route and they fail at
    # zero/multiple discovered Rhinos -- exactly the cases they exist to handle.
    for name in ("rhino_sessions", "rhino_session_capabilities"):
        p = targeting.policy_for_tool(name)
        assert p.requires_rhino is False, name
        assert p.risk == "meta", name


@pytest.mark.asyncio
async def test_call_tool_rhino_sessions_zero_rhinos_returns_empty_not_error(monkeypatch):
    # Real call_tool path (policy + routing), not _call_tool_dispatch. With zero
    # discovered Rhinos it must return an empty session list, never no_rhino_instance.
    monkeypatch.setattr(bridge, "discover_instances", lambda: [])
    out = await server.call_tool("rhino_sessions", {})
    text = out[0].text
    assert "no_rhino_instance" not in text
    assert not text.startswith("Error:")
    assert json.loads(text)["sessions"] == []


@pytest.mark.asyncio
async def test_call_tool_rhino_sessions_multiple_rhinos_lists_all(monkeypatch):
    # With multiple discovered Rhinos it must list them all, never
    # multiple_rhino_instances (which a mutate-risk tool would raise).
    insts = [
        {"host": "127.0.0.1", "port": 10500, "pluginType": "native", "processId": 111},
        {"host": "127.0.0.1", "port": 10501, "pluginType": "native", "processId": 222},
    ]
    monkeypatch.setattr(bridge, "discover_instances", lambda: insts)
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: True)
    out = await server.call_tool("rhino_sessions", {})
    text = out[0].text
    assert "multiple_rhino_instances" not in text
    assert not text.startswith("Error:")
    sessions = {s["session"] for s in json.loads(text)["sessions"]}
    assert sessions == {"rhino-111", "rhino-222"}


@pytest.mark.asyncio
async def test_call_tool_rhino_session_capabilities_unrouted_not_routing_error(monkeypatch):
    # Symmetry with rhino_sessions: the real call_tool path must reach the meta
    # dispatch (get_session_capabilities), not resolve_tool_route. With zero
    # discovered Rhinos, asking for a session returns the structured
    # rhino_session_dead -- never a no_rhino_instance/multiple_rhino_instances
    # routing error.
    monkeypatch.setattr(bridge, "discover_instances", lambda: [])
    out = await server.call_tool("rhino_session_capabilities", {"session": "rhino-404"})
    text = out[0].text
    assert "no_rhino_instance" not in text
    assert "multiple_rhino_instances" not in text
    assert "rhino_session_dead" in text
    assert "rhino-404" in text
