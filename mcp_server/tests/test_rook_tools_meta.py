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
