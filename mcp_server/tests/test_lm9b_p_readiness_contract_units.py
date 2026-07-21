"""Contract units: ack-conformance matrix for route_ready and the
credential-source resolver edges (spec tests 10 unknown-route, 11
helper/declaration disagreement)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


C = _load_script("lm9b_p_readiness_contract")


def _ok_row():
    return {
        "outcome": {
            "kind": "model_response",
            "assistant_present": True,
            "tool_calls": [{"name": "ack", "arguments": '{"ok": true}'}],
        }
    }


def test_route_ready_accepts_conforming():
    assert C.route_ready(_ok_row()) is True


def test_route_ready_accepts_parsed_closed_object():
    row = _ok_row()
    row["outcome"]["tool_calls"] = [{"name": "ack", "arguments": {"ok": True}}]
    assert C.route_ready(row) is True


def test_route_ready_rejects_duplicate_key_string():
    row = _ok_row()
    row["outcome"]["tool_calls"] = [
        {"name": "ack", "arguments": '{"ok": true, "ok": true}'}
    ]
    assert C.route_ready(row) is False


def test_route_ready_rejects_fingerprint_only_argument():
    row = _ok_row()
    row["outcome"]["tool_calls"] = [{"name": "ack", "arguments": 123}]
    assert C.route_ready(row) is False


@pytest.mark.parametrize(
    "mut",
    [
        lambda o: o.update(kind="transport_failure"),
        lambda o: o.update(assistant_present=False),
        lambda o: o.update(tool_calls=[]),
        lambda o: o.update(tool_calls=[{"name": "ack", "arguments": '{"ok": true}'}] * 2),
        lambda o: o.update(tool_calls=[{"name": "no", "arguments": '{"ok": true}'}]),
        lambda o: o.update(tool_calls=[{"name": "ack", "arguments": '{"ok": false}'}]),
        lambda o: o.update(tool_calls=[{"name": "ack", "arguments": "not json"}]),
        lambda o: o.update(tool_calls=[{"name": "ack"}]),
    ],
)
def test_route_ready_rejects(mut):
    row = _ok_row()
    mut(row["outcome"])
    assert C.route_ready(row) is False


def test_declaration_is_closed_two_entries():
    assert C.CREDENTIAL_SOURCE_DECLARATIONS == {
        ("openai", "gpt-5.4"): ("OPENAI_API_KEY",),
        ("gemini", "gemini/gemini-3.1-pro-preview"): ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    }


def test_resolver_null_helper_uses_declaration():
    assert C.resolve_credential_source("openai", "gpt-5.4", None) == ("OPENAI_API_KEY",)
    assert C.resolve_credential_source(
        "gemini", "gemini/gemini-3.1-pro-preview", None
    ) == ("GOOGLE_API_KEY", "GEMINI_API_KEY")


def test_resolver_member_helper_ok():
    assert C.resolve_credential_source(
        "gemini", "gemini/gemini-3.1-pro-preview", "GEMINI_API_KEY"
    ) == ("GOOGLE_API_KEY", "GEMINI_API_KEY")


def test_resolver_nonmember_helper_fails():
    with pytest.raises(C.ReadinessError):
        C.resolve_credential_source("openai", "gpt-5.4", "WRONG_KEY")


def test_unknown_route_fails_closed():
    with pytest.raises(C.ReadinessError):
        C.resolve_credential_source("openai", "mystery", None)
    with pytest.raises(C.ReadinessError):
        C.derive_routes(
            (C.RoleRoute("x", "litellm.completion", "openai", "mystery"),),
            lambda m: None,
        )
