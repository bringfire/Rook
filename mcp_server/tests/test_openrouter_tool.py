import asyncio
from rook import targeting
from rook import mcp_tool_profiles as mtp
import rook.server as server
import rook.providers.openrouter_catalog as cat


class _T:
    def __init__(self, name):
        self.name = name


def test_tool_is_non_rhino():
    assert targeting.policy_for_tool("openrouter_refresh_catalog").requires_rhino is False


def test_tool_is_listed_under_full(monkeypatch):
    monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert "openrouter_refresh_catalog" in names


def test_lean_advertises_refresh():
    tools = [_T("openrouter_refresh_catalog"), _T("rhino_create")]
    names = {t.name for t in mtp.filter_tools(tools, mtp.Profile.LEAN)}
    assert "openrouter_refresh_catalog" in names


def test_readonly_hides_refresh():
    tools = [_T("openrouter_refresh_catalog")]
    assert mtp.filter_tools(tools, mtp.Profile.READONLY) == []


def test_tool_blocked_readonly_true():
    assert mtp.tool_blocked("openrouter_refresh_catalog", mtp.Profile.READONLY) is True


def test_tool_blocked_lean_false():
    assert mtp.tool_blocked("openrouter_refresh_catalog", mtp.Profile.LEAN) is False


def test_tool_dispatch_maps_result(monkeypatch):
    fake = cat.RefreshResult(
        success=True, models_fetched=2, favorites_matched=1, unknown_favorites=[],
        cache_path="X", source_endpoint=cat.OPENROUTER_MODELS_ENDPOINT,
        fetched_at="2026-06-29T00:00:00+00:00", last_refresh_error=None)
    monkeypatch.setattr(cat, "refresh", lambda *a, **k: fake)
    result = asyncio.run(server._call_tool_dispatch("openrouter_refresh_catalog", {}))
    assert result["success"] is True
    assert result["data"]["models_fetched"] == 2
    assert result["data"]["favorites_matched"] == 1
    assert result["data"]["source_endpoint"] == cat.OPENROUTER_MODELS_ENDPOINT
