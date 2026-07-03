from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm5p_ollama_think_format_spike.py"
    )


def _load_script():
    path = _script_path()
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


def test_args_custom_model_replaces_defaults() -> None:
    args = SPIKE._args(["--model", "custom:model"])
    assert args.models == ["custom:model"]


def test_args_no_model_uses_default_models() -> None:
    args = SPIKE._args([])
    assert args.models == list(SPIKE.DEFAULT_MODELS)
    assert args.models is not SPIKE.DEFAULT_MODELS


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


def _request_envelope_for_scenario(name: str) -> dict:
    messages = SPIKE._messages_for_scenario(name)
    assert [message["role"] for message in messages] == ["system", "user"]
    return json.loads(messages[1]["content"])


def test_messages_for_evidence_absent_like_renders_real_lm5j_prompt() -> None:
    envelope = _request_envelope_for_scenario("evidence_absent_like")

    assert envelope["schema"] == "rook.local_worker_turn_request:v1"
    context = envelope["context"]
    assert context["current_node"]["node_id"] == "repair_same_component"
    assert [packet["packet_id"] for packet in context["knowledge"]] == [
        "script_body_gotcha"
    ]
    assert context["current_node"]["has_execution_params"] is False


def test_messages_for_evidence_present_like_adds_evidence_packet() -> None:
    envelope = _request_envelope_for_scenario("evidence_present_like")

    packets = envelope["context"]["knowledge"]
    assert [packet["packet_id"] for packet in packets] == [
        "script_body_gotcha",
        "lm5n_repair_evidence",
    ]
    evidence = packets[1]
    assert evidence["kind"] == "evidence"
    assert evidence["content"]["state"] == "post_verify_pre_bind"


def test_messages_for_unknown_scenario_raises() -> None:
    with pytest.raises(ValueError, match="unknown LM5P scenario"):
        SPIKE._messages_for_scenario("missing")


def test_script_help_runs_from_repo_root() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    python = repo_root / "mcp_server" / ".venv" / "Scripts" / "python.exe"
    result = subprocess.run(
        [str(python), "scripts/lm5p_ollama_think_format_spike.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "LM5P Ollama think/format diagnostic spike scaffold." in result.stdout


def test_script_static_import_and_call_guards() -> None:
    tree = ast.parse(_script_path().read_text(encoding="utf-8"))
    forbidden_modules = {"requests", "httpx", "ollama", "litellm"}
    forbidden_names = {
        "run_probe",
        "run_candidate",
        "_default_transport_factory",
        "LiteLLMWorkerTransport",
        "run_local_worker_adapter",
        "run_local_worker_turn",
        "evaluate_local_worker_scenario_result",
    }

    imported_modules: set[str] = set()
    imported_names: set[str] = set()
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name.split(".", 1)[0])
                imported_names.add(alias.asname or alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module.split(".", 1)[0])
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                called_names.add(func.attr)

    assert imported_modules.isdisjoint(forbidden_modules)
    assert imported_names.isdisjoint(forbidden_names)
    assert called_names.isdisjoint(forbidden_names)
    assert {"_SCENARIOS", "build_probe_context"} <= imported_names
