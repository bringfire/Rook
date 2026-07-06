import asyncio

import pytest

from rook import server
from rook.mcp_tool_profiles import (
    PUBLIC_LEAN_TOOL_NAMES,
    PUBLIC_READONLY_TOOL_NAMES,
    SENTINEL_TOOL_NAMES,
)

_GATED = {"rhino_command_experiment", "rhino_learn_next", "rhino_prepare_geometry"}


def _list_names(monkeypatch, profile_value):
    # Default flag-off state so the live surface is the canonical 438.
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    monkeypatch.delenv("ROOK_MCP_TARGET_MODE", raising=False)
    if profile_value is None:
        monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
    else:
        monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile_value)
    tools = asyncio.run(server.list_tools())
    return {t.name for t in tools}


def test_full_surface_is_438_and_gates_deprecated(monkeypatch):
    full = _list_names(monkeypatch, None)  # absent => full
    # 431 pre-meta base (427 #382 + mesh2splat #384 + openrouter #385
    # + Director v2 actor metadata tools + source occurrence capture) + 4
    # rook_tools_* meta-tools + rhino_director_canvas_extract (#post-436, prior
    # task) + rhino_director_package_take (this task) = 438.
    assert len(full) == 438
    assert _GATED.isdisjoint(full)
    assert PUBLIC_LEAN_TOOL_NAMES <= full
    assert PUBLIC_READONLY_TOOL_NAMES <= full
    assert SENTINEL_TOOL_NAMES <= full


def test_all_live_tools_is_unprofiled_438(monkeypatch):
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    # Even with a restrictive profile set, the unprofiled source is the full 438.
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    names = {t.name for t in asyncio.run(server._all_live_tools())}
    assert len(names) == 438
    assert _GATED.isdisjoint(names)


def test_explicit_full_equals_absent(monkeypatch):
    assert _list_names(monkeypatch, "full") == _list_names(monkeypatch, None)


def test_lean_surface_is_exactly_22(monkeypatch):
    lean = _list_names(monkeypatch, "lean")
    assert lean == set(PUBLIC_LEAN_TOOL_NAMES)
    assert len(lean) == 22


def test_readonly_surface_is_exactly_149(monkeypatch):
    ro = _list_names(monkeypatch, "readonly")
    assert ro == set(PUBLIC_READONLY_TOOL_NAMES)
    assert len(ro) == 149


def test_meta_tools_present_in_all_profiles(monkeypatch):
    for prof in (None, "full", "lean", "readonly"):
        names = _list_names(monkeypatch, prof)
        assert {"rook_tools_ls", "rook_tools_search", "rook_tools_read", "rook_tools_call"} <= names


def test_readonly_partition_over_live_surface(monkeypatch):
    full = _list_names(monkeypatch, None)
    ro = set(PUBLIC_READONLY_TOOL_NAMES)
    assert ro <= full
    assert ro.isdisjoint(SENTINEL_TOOL_NAMES)
    excluded = full - ro
    assert ro | excluded == full
    assert ro.isdisjoint(excluded)
    assert len(ro) + len(excluded) == len(full) == 438


def _call_text(name, args=None):
    result = asyncio.run(server.call_tool(name, args or {}))
    return result[0].text


def _blocked_payload(text):
    # _format_tool_result renders failures as 'Error: ' + json.dumps(data, indent=2).
    import json

    assert text.startswith("Error: ")
    return json.loads(text[len("Error: "):])


def test_readonly_block_returns_exact_payload(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    payload = _blocked_payload(_call_text("rhino_create"))
    assert payload == {
        "code": "tool_profile_blocked",
        "tool": "rhino_create",
        "profile": "readonly",
    }


@pytest.mark.parametrize(
    "mutator",
    ["rhino_layer_visibility", "rhino_select", "gh_edit", "rhino_transform", "rhino_create"],
)
def test_readonly_blocks_representative_mutators(monkeypatch, mutator):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    assert "tool_profile_blocked" in _call_text(mutator)


def test_readonly_allows_allowlisted_tool_past_the_guard(monkeypatch):
    # rhino_objects is in the allowlist -- the guard must NOT block it.
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    assert "tool_profile_blocked" not in _call_text("rhino_objects")


def test_lean_is_list_only_does_not_block_calls(monkeypatch):
    # A mutator NOT in lean must still be callable under lean (list-only).
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    assert "tool_profile_blocked" not in _call_text("rhino_create")


def test_full_does_not_block_calls(monkeypatch):
    monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
    assert "tool_profile_blocked" not in _call_text("rhino_create")


def test_blocked_readonly_call_has_no_side_effects(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    calls = {"observed": False, "policy": False, "dispatched": False}

    def _spy_observe(*a, **k):
        calls["observed"] = True

    def _spy_policy(*a, **k):
        calls["policy"] = True
        raise AssertionError("policy_for_tool must not run for a blocked call")

    async def _spy_dispatch(*a, **k):
        calls["dispatched"] = True
        return {"success": True, "data": {}}

    monkeypatch.setattr(server, "_record_observation", _spy_observe)
    monkeypatch.setattr(server.targeting, "policy_for_tool", _spy_policy)
    monkeypatch.setattr(server, "_call_tool_dispatch", _spy_dispatch)

    text = _call_text("rhino_create")
    assert "tool_profile_blocked" in text
    assert calls == {"observed": False, "policy": False, "dispatched": False}


def test_validate_profile_or_exit_raises_on_invalid(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "bogus")
    with pytest.raises(SystemExit) as exc:
        server._validate_profile_or_exit()
    assert exc.value.code == 2


def test_validate_profile_or_exit_passes_on_valid(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    assert server._validate_profile_or_exit() is None


def test_validate_profile_or_exit_passes_when_absent(monkeypatch):
    monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
    assert server._validate_profile_or_exit() is None


def test_lean_keeps_dg009_hidden_gh_mutators_behind_gateway(monkeypatch):
    lean = _list_names(monkeypatch, "lean")
    assert {"rook_tools_search", "rook_tools_read", "rook_tools_call"} <= lean
    assert {
        "gh_update_script",
        "gh_set_script_pins",
        "gh_create_csharp_script",
    }.isdisjoint(lean)
