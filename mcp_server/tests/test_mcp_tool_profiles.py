import pytest

from rook.mcp_tool_profiles import (
    ENV_VAR,
    InvalidProfileError,
    Profile,
    resolve_profile,
)


def test_absent_resolves_to_full():
    assert resolve_profile({}) is Profile.FULL


def test_empty_and_whitespace_resolve_to_full():
    assert resolve_profile({ENV_VAR: ""}) is Profile.FULL
    assert resolve_profile({ENV_VAR: "   "}) is Profile.FULL


def test_explicit_values_resolve():
    assert resolve_profile({ENV_VAR: "full"}) is Profile.FULL
    assert resolve_profile({ENV_VAR: "lean"}) is Profile.LEAN
    assert resolve_profile({ENV_VAR: "readonly"}) is Profile.READONLY


def test_values_are_normalized_case_and_whitespace():
    assert resolve_profile({ENV_VAR: "  LEAN "}) is Profile.LEAN
    assert resolve_profile({ENV_VAR: "ReadOnly"}) is Profile.READONLY


def test_invalid_value_raises_not_silent_fallback():
    with pytest.raises(InvalidProfileError) as exc:
        resolve_profile({ENV_VAR: "readonyl"})
    assert ENV_VAR in str(exc.value)
    assert "readonyl" in str(exc.value)


def test_profile_values_are_exact_strings():
    assert Profile.FULL.value == "full"
    assert Profile.LEAN.value == "lean"
    assert Profile.READONLY.value == "readonly"


from rook.mcp_tool_profiles import (
    PUBLIC_LEAN_TOOL_NAMES,
    PUBLIC_READONLY_TOOL_NAMES,
    SENTINEL_TOOL_NAMES,
)


def test_set_sizes_are_pinned():
    assert len(PUBLIC_LEAN_TOOL_NAMES) == 17
    assert len(PUBLIC_READONLY_TOOL_NAMES) == 145
    assert len(SENTINEL_TOOL_NAMES) == 26


def test_readonly_is_disjoint_from_sentinels():
    # The safety boundary: no sentinel may ever be in the readonly allowlist.
    assert PUBLIC_READONLY_TOOL_NAMES.isdisjoint(SENTINEL_TOOL_NAMES)


def test_lean_is_not_a_subset_of_readonly():
    # lean is a *context* surface that must do work; it deliberately includes
    # 5 mutators not in the *safety* readonly surface.
    lean_only = PUBLIC_LEAN_TOOL_NAMES - PUBLIC_READONLY_TOOL_NAMES
    assert lean_only == {
        "gh_edit",
        "rhino_execute_intent",
        "gh_execute_intent",
        "rhino_set_active_instance",
        "rhino_clear_active_instance",
    }


def test_named_sentinels_present():
    # Spot-check the easy "not geometry-creation => readonly" fallacy names.
    for name in ("rhino_select", "rhino_layer_visibility", "gh_edit", "rhino_create"):
        assert name in SENTINEL_TOOL_NAMES
        assert name not in PUBLIC_READONLY_TOOL_NAMES
