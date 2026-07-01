import asyncio
from rook import server


def test_dispatchable_names_include_meta_and_a_known_native():
    names = server._dispatchable_tool_names()
    assert server.META_TOOL_NAMES <= names            # meta-tools unioned in (P1b)
    assert "rhino_objects" in names                    # a known dispatcher case label


def test_dispatchable_names_include_or_case_arms():
    # server.py has: case "rhino_command_knowledge" | "rhino_knowledge_query":
    names = server._dispatchable_tool_names()
    assert "rhino_command_knowledge" in names and "rhino_knowledge_query" in names


def test_capability_index_covers_full_unprofiled_surface(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")  # profile must NOT shrink the index
    server._reset_capability_index_cache()
    idx = asyncio.run(server._get_capability_index())
    live = {t.name for t in asyncio.run(server._all_live_tools())}
    assert {r.name for r in idx.records} == live
    assert idx.by_name["rhino_director_preview_motion"].mcp_dispatchable is True


def test_index_survives_lm2a_failure(monkeypatch):
    server._reset_capability_index_cache()  # test hook (Step 3)
    import rook.agent.capability_inventory as inv
    monkeypatch.setattr(inv, "collect_live_sources", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    idx = asyncio.run(server._get_capability_index())
    assert all(r.agent_record is None for r in idx.records)  # tolerated -> agent_records = {}
    server._reset_capability_index_cache()  # don't leak the degraded index to later tests


def test_dispatch_origin_defaults_native_and_is_readable():
    from rook.server import _dispatch_origin
    assert _dispatch_origin.get() == "native"
    tok = _dispatch_origin.set("meta")
    try:
        assert _dispatch_origin.get() == "meta"
    finally:
        _dispatch_origin.reset(tok)


import json


def _text(name, args=None):
    return asyncio.run(server.call_tool(name, args or {}))[0].text


def _stub_dispatch(monkeypatch):
    # requires_rhino=False routes call_tool straight to _call_tool_dispatch (no Rhino/route
    # resolution needed), so the meta re-entry actually reaches the stub.
    from types import SimpleNamespace
    monkeypatch.setattr(server.targeting, "policy_for_tool",
                        lambda name: SimpleNamespace(requires_rhino=False))
    async def ok(name, arguments):
        return {"success": True, "data": {"dispatched": name, "origin": server._dispatch_origin.get()}}
    monkeypatch.setattr(server, "_call_tool_dispatch", ok)


def test_lean_reach_search_read_call(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    _stub_dispatch(monkeypatch)
    found = json.loads(_text("rook_tools_search", {"query": "director preview"}))
    assert any(e["name"] == "rhino_director_preview_motion" for e in found)
    schema = json.loads(_text("rook_tools_read", {"name": "rhino_director_preview_motion"}))
    assert "input_schema" in schema
    called = json.loads(_text("rook_tools_call",
                              {"name": "rhino_director_preview_motion",
                               "arguments": {"timeline": {}, "motion": []}}))  # satisfies required timeline+motion
    assert called["dispatched"] == "rhino_director_preview_motion" and called["origin"] == "meta"


def test_readonly_block_wall_before_validation(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    _stub_dispatch(monkeypatch)
    # invalid args, but the blocked target must still return tool_profile_blocked (wall first):
    text = _text("rook_tools_call",
                 {"name": "rhino_director_preview_motion", "arguments": {"bogus": 1}})
    assert "tool_profile_blocked" in text


def test_recursion_guard(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    assert "error" in _text("rook_tools_call", {"name": "rook_tools_ls"}).lower()


def test_non_dispatchable_refused(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    _stub_dispatch(monkeypatch)
    assert "error" in _text("rook_tools_call", {"name": "definitely_not_a_tool"}).lower()


def test_meta_layer_never_self_records(monkeypatch):
    # Meta tools are intercepted BEFORE _call_tool_dispatch's recording tail, so they must never
    # appear as observations. (Target-under-real-name + origin=meta is covered by test_lean_reach:
    # the stub reads _dispatch_origin at dispatch time; the real recording tail is exercised by a
    # requires_rhino integration run, out of scope for this unit suite.)
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    _stub_dispatch(monkeypatch)
    recorded = []
    monkeypatch.setattr(server, "_record_observation", lambda name, *a, **k: recorded.append(name))
    _text("rook_tools_search", {"query": "objects"})
    _text("rook_tools_read", {"name": "rhino_objects"})
    _text("rook_tools_call", {"name": "rhino_objects", "arguments": {}})
    assert "rook_tools_call" not in recorded
    assert "rook_tools_search" not in recorded and "rook_tools_read" not in recorded


def test_meta_dispatch_records_target_once_with_origin_meta(monkeypatch):
    # Real non-Rhino target: rhino_instances -> targeting.instances_result() needs no live Rhino, so the
    # REAL _call_tool_dispatch recording tail runs. Do NOT stub dispatch.
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    recorded = []
    monkeypatch.setattr(server, "_record_observation",
                        lambda name, *a, **k: recorded.append((name, server._dispatch_origin.get())))
    _text("rook_tools_call", {"name": "rhino_instances", "arguments": {}})
    assert recorded == [("rhino_instances", "meta")]   # one record, target name, tagged meta


def test_readonly_blocked_meta_call_has_no_side_effects(monkeypatch):
    # Mirror test_blocked_readonly_call_has_no_side_effects for the meta path.
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    flags = {"observed": False, "dispatched": False}
    monkeypatch.setattr(server, "_record_observation", lambda *a, **k: flags.__setitem__("observed", True))
    async def _spy(*a, **k): flags["dispatched"] = True; return {"success": True, "data": {}}
    monkeypatch.setattr(server, "_call_tool_dispatch", _spy)
    assert "tool_profile_blocked" in _text("rook_tools_call",
                                           {"name": "rhino_create", "arguments": {}})
    assert flags == {"observed": False, "dispatched": False}
