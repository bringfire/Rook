import asyncio
from rook import server
from rook.tool_lifecycle import contained_names


def test_dispatchable_names_include_meta_and_a_known_native():
    names = server._dispatchable_tool_names()
    assert server.META_TOOL_NAMES <= names            # meta-tools unioned in (P1b)
    assert "rhino_objects" in names                    # a known dispatcher case label


def test_dispatchable_names_include_or_case_arms():
    # server.py has: case "rhino_command_knowledge" | "rhino_knowledge_query":
    names = server._dispatchable_tool_names()
    assert "rhino_command_knowledge" in names and "rhino_knowledge_query" in names


def test_dispatch_case_scan_and_cached_projection_omit_contained_identities(
    monkeypatch,
    tmp_path,
):
    from rook.learning import metrics_store

    store = metrics_store.MetricsStore(tmp_path / "metrics.json")
    monkeypatch.setattr(metrics_store, "_metrics_store", store)
    before = store.get_containment_denials_snapshot()
    hidden = contained_names()
    scanned = server._scan_dispatch_case_labels()
    cached = server._dispatchable_tool_names()
    after = store.get_containment_denials_snapshot()
    assert (
        hidden.isdisjoint(scanned)
        and hidden.isdisjoint(cached)
        and after == before
    ), (
        "EXPECTED_RED:T2:PYTEST AST dispatch labels still expose contained identities"
    )


def test_capability_index_covers_full_unprofiled_surface(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    server._reset_capability_index_cache()
    idx = asyncio.run(server._get_capability_index())
    live = {t.name for t in asyncio.run(server._all_live_tools())}
    assert {r.name for r in idx.records} == live
    assert idx.by_name["rhino_objects"].mcp_dispatchable is True
    assert "rhino_director_preview_motion" not in idx.by_name
    assert contained_names().isdisjoint(idx.by_name), (
        "EXPECTED_RED:T2:PYTEST capability index cache exposes contained identities"
    )


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


def test_lean_reaches_hidden_tool_via_search_read_call(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    _stub_dispatch(monkeypatch)
    found = json.loads(_text("rook_tools_search", {"query": "gh_status"}))
    assert any(entry["name"] == "gh_status" for entry in found)
    schema = json.loads(_text("rook_tools_read", {"name": "gh_status"}))
    assert "input_schema" in schema
    called = json.loads(
        _text("rook_tools_call", {"name": "gh_status", "arguments": {}})
    )
    assert called == {"dispatched": "gh_status", "origin": "meta"}


def test_readonly_block_wall_before_validation(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    _stub_dispatch(monkeypatch)
    text = _text(
        "rook_tools_call",
        {"name": "rhino_create", "arguments": {"bogus": 1}},
    )
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


def test_rook_tools_call_rejects_non_object_arguments(monkeypatch):
    # Malformed 'arguments' must return a structured error, not raise (dict("abc") would ValueError).
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    text = _text("rook_tools_call", {"name": "rhino_instances", "arguments": "abc"})
    assert "invalid_arguments" in text


def test_rook_tools_ls_tolerates_malformed_depth(monkeypatch):
    # A non-int depth must fall back to the default, not raise int('nope').
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    out = json.loads(_text("rook_tools_ls", {"path": "/rhino", "depth": "nope"}))
    assert "entries" in out


def test_rook_tools_search_tolerates_malformed_limit(monkeypatch):
    # A non-int limit must fall back to the default, not raise int('nope').
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    found = json.loads(_text("rook_tools_search", {"query": "objects", "limit": "nope"}))
    assert isinstance(found, list)


DG009_GH_TOOL_NAMES = (
    "gh_update_script",
    "gh_set_script_pins",
    "gh_status",
    "gh_create_csharp_script",
    "gh_snapshot",
)


def _lean_tool_descriptions(monkeypatch):
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    return {tool.name: tool.description for tool in asyncio.run(server.list_tools())}


def test_lean_gateway_metadata_contains_dg009_exact_gh_aliases(monkeypatch):
    descriptions = _lean_tool_descriptions(monkeypatch)
    for gateway in ("rook_tools_search", "rook_tools_read", "rook_tools_call"):
        assert gateway in descriptions
        desc = descriptions[gateway]
        for tool_name in DG009_GH_TOOL_NAMES:
            assert tool_name in desc


def test_rook_tools_search_exact_dg009_gh_names_resolve_real_records(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    server._reset_capability_index_cache()
    for tool_name in DG009_GH_TOOL_NAMES:
        found = json.loads(_text("rook_tools_search", {"query": tool_name, "limit": 10}))
        assert any(entry["name"] == tool_name for entry in found), tool_name


def test_rook_tools_read_exact_dg009_gh_names_return_schemas(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    server._reset_capability_index_cache()
    for tool_name in DG009_GH_TOOL_NAMES:
        record = json.loads(_text("rook_tools_read", {"name": tool_name}))
        assert record["name"] == tool_name
        assert record["domain"] == "gh"
        assert record["mcp_dispatchable"] is True
        assert isinstance(record["input_schema"], dict)
        assert record["input_schema"].get("type") == "object"
