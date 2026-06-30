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
