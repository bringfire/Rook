from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_script():
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm5p_ollama_think_format_spike.py"
    )
    spec = importlib.util.spec_from_file_location(
        "lm5p_ollama_think_format_spike", path
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


SPIKE = _load_script()


def test_constants_and_modes_are_pinned() -> None:
    assert SPIKE.DEFAULT_MODELS == ("gemma4:12b-it-qat", "gemma4:12b")
    assert SPIKE.SCENARIO_NAMES == (
        "evidence_absent_like",
        "evidence_present_like",
    )
    assert SPIKE._MODES == {
        "free_default": {"format": False, "think": "omitted"},
        "free_think_true": {"format": False, "think": True},
        "format_default": {"format": True, "think": "omitted"},
        "format_think_true": {"format": True, "think": True},
        "format_think_false": {"format": True, "think": False},
    }


def test_response_union_schema_root_and_variants() -> None:
    schema = SPIKE._response_union_schema()
    assert set(schema) == {"oneOf"}
    variants = schema["oneOf"]
    assert len(variants) == 4
    assert [variant["properties"]["kind"]["const"] for variant in variants] == [
        "action_request",
        "clarification_request",
        "refusal",
        "observation",
    ]

    for variant in variants:
        assert variant["type"] == "object"
        assert variant["additionalProperties"] is False
        assert (
            variant["properties"]["schema"]["const"]
            == "rook.local_worker_turn_response:v1"
        )


def test_response_union_schema_lm5g_field_shapes() -> None:
    variants = {
        variant["properties"]["kind"]["const"]: variant
        for variant in SPIKE._response_union_schema()["oneOf"]
    }

    action = variants["action_request"]
    assert action["required"] == [
        "schema",
        "kind",
        "action_id",
        "rationale",
        "input",
    ]
    assert action["properties"]["input"]["type"] == "object"

    clarification = variants["clarification_request"]
    assert clarification["required"] == [
        "schema",
        "kind",
        "question",
        "rationale",
    ]
    assert clarification["properties"]["rationale"]["type"] == ["string", "null"]

    refusal = variants["refusal"]
    assert refusal["required"] == ["schema", "kind", "category", "reason"]
    assert refusal["properties"]["category"]["enum"] == [
        "unsafe",
        "insufficient_context",
        "unsupported_action",
        "out_of_scope",
    ]

    observation = variants["observation"]
    assert observation["required"] == ["schema", "kind", "message", "data"]
    assert observation["properties"]["data"]["type"] == ["object", "null"]


def test_build_request_body_free_default_omits_format_and_think() -> None:
    messages = [{"role": "user", "content": "hello"}]
    body = SPIKE._build_request_body(
        "gemma4:12b-it-qat", messages, "free_default", 0
    )
    assert body == {
        "model": "gemma4:12b-it-qat",
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0},
    }
    assert "format" not in body
    assert "think" not in body


def test_build_request_body_free_think_true_sets_think_and_no_format() -> None:
    body = SPIKE._build_request_body(
        "gemma4:12b-it-qat",
        [{"role": "user", "content": "hello"}],
        "free_think_true",
        0,
    )
    assert body["think"] is True
    assert "format" not in body


def test_build_request_body_format_think_false_includes_fresh_schema() -> None:
    messages = [{"role": "user", "content": "hello"}]
    body = SPIKE._build_request_body(
        "gemma4:12b-it-qat", messages, "format_think_false", 0
    )
    second = SPIKE._build_request_body(
        "gemma4:12b-it-qat", messages, "format_think_false", 0
    )
    assert body["think"] is False
    assert body["format"] == SPIKE._response_union_schema()
    assert body["format"] is not second["format"]
    body["format"]["oneOf"][0]["properties"]["input"]["type"] = "mutated"
    assert second["format"]["oneOf"][0]["properties"]["input"]["type"] == "object"


def test_build_request_body_unknown_mode_raises() -> None:
    with pytest.raises(ValueError, match="unknown LM5P mode"):
        SPIKE._build_request_body(
            "gemma4:12b-it-qat",
            [{"role": "user", "content": "hello"}],
            "missing",
            0,
        )
