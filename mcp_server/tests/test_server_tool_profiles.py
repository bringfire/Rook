import asyncio

import pytest

from rook import server
from rook.mcp_tool_profiles import (
    PUBLIC_LEAN_TOOL_NAMES,
    PUBLIC_READONLY_TOOL_NAMES,
    SENTINEL_TOOL_NAMES,
)
from rook.tool_lifecycle import contained_names

_GATED = {"rhino_command_experiment", "rhino_learn_next", "rhino_prepare_geometry"}


def _list_names(monkeypatch, profile_value):
    # Default flag-off state so the live surface is the canonical 428.
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    monkeypatch.delenv("ROOK_MCP_TARGET_MODE", raising=False)
    if profile_value is None:
        monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
    else:
        monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile_value)
    tools = asyncio.run(server.list_tools())
    return {t.name for t in tools}


def test_full_surface_is_422_and_gates_deprecated(monkeypatch):
    full = _list_names(monkeypatch, None)  # absent => full
    hidden = contained_names()
    assert len(full) == 422, (
        "EXPECTED_RED:T2:PYTEST full catalog still exposes contained identities"
    )
    assert {"gh_solve_readiness", "gh_wait_for_solve_readiness"} <= full
    assert _GATED.isdisjoint(full)
    assert (PUBLIC_LEAN_TOOL_NAMES - hidden) <= full
    assert PUBLIC_READONLY_TOOL_NAMES <= full
    assert (SENTINEL_TOOL_NAMES - hidden) <= full
    assert hidden.isdisjoint(full)


def test_deprecated_interactive_gate_adds_exactly_three_tools(monkeypatch):
    default = _list_names(monkeypatch, None)
    monkeypatch.setenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", "1")
    enabled = {t.name for t in asyncio.run(server.list_tools())}
    assert len(enabled) == 425, (
        "EXPECTED_RED:T2:PYTEST interactive catalog still exposes contained identities"
    )
    assert enabled - default == _GATED
    assert contained_names().isdisjoint(enabled)


def test_all_live_tools_is_unprofiled_422(monkeypatch):
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    # Even with a restrictive profile set, the unprofiled source is the full
    # lifecycle-projected 422.
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    names = {t.name for t in asyncio.run(server._all_live_tools())}
    assert len(names) == 422, (
        "EXPECTED_RED:T2:PYTEST _all_live_tools still exposes contained identities"
    )
    assert _GATED.isdisjoint(names)
    assert contained_names().isdisjoint(names)


def test_live_and_post_profile_projection_omit_without_telemetry(
    monkeypatch,
    tmp_path,
):
    from rook.learning import metrics_store

    store = metrics_store.MetricsStore(tmp_path / "metrics.json")
    monkeypatch.setattr(metrics_store, "_metrics_store", store)
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    before = store.get_containment_denials_snapshot()
    live = {tool.name for tool in asyncio.run(server._all_live_tools())}
    profiled = {tool.name for tool in asyncio.run(server.list_tools())}
    after = store.get_containment_denials_snapshot()

    assert (
        contained_names().isdisjoint(live)
        and contained_names().isdisjoint(profiled)
        and after == before
    ), "EXPECTED_RED:T2:PYTEST live/profile omission records telemetry or leaks names"


def test_explicit_full_equals_absent(monkeypatch):
    assert _list_names(monkeypatch, "full") == _list_names(monkeypatch, None)


def test_lean_surface_is_exactly_20(monkeypatch):
    lean = _list_names(monkeypatch, "lean")
    expected = set(PUBLIC_LEAN_TOOL_NAMES) - contained_names()
    assert lean == expected, (
        "EXPECTED_RED:T2:PYTEST lean catalog still exposes contained identities"
    )
    assert len(lean) == 20


def test_readonly_surface_is_exactly_148(monkeypatch):
    ro = _list_names(monkeypatch, "readonly")
    assert ro == set(PUBLIC_READONLY_TOOL_NAMES)
    assert len(ro) == 148
    assert contained_names().isdisjoint(ro)


def test_meta_tools_present_in_all_profiles(monkeypatch):
    for prof in (None, "full", "lean", "readonly"):
        names = _list_names(monkeypatch, prof)
        assert {"rook_tools_ls", "rook_tools_search", "rook_tools_read", "rook_tools_call"} <= names
        assert contained_names().isdisjoint(names), (
            "EXPECTED_RED:T2:PYTEST profile catalog exposes contained identities"
        )


def test_readonly_partition_over_live_surface(monkeypatch):
    full = _list_names(monkeypatch, None)
    ro = set(PUBLIC_READONLY_TOOL_NAMES)
    assert ro <= full
    assert ro.isdisjoint(SENTINEL_TOOL_NAMES)
    excluded = full - ro
    assert ro | excluded == full
    assert ro.isdisjoint(excluded)
    assert len(ro) + len(excluded) == len(full) == 422, (
        "EXPECTED_RED:T2:PYTEST readonly partition still includes contained identities"
    )


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
