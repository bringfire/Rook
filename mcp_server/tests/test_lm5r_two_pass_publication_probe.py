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
        / "lm5r_two_pass_publication_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm5r_two_pass_publication_probe",
        path,
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


PROBE = _load_script()


def test_constants_are_pinned() -> None:
    assert PROBE.SCRIPT_SCHEMA == "rook.lm5r_two_pass_publication_probe:v1"
    assert PROBE.DEFAULT_MODEL == "gemma4:12b-it-qat"
    assert PROBE.SCENARIO_NAMES == (
        "evidence_absent_like",
        "evidence_present_like",
    )
    assert PROBE.DEFAULT_ATTEMPTS == 5
    assert PROBE.DEFAULT_TEMPERATURE == 0
    assert PROBE.EXCERPT_CHARS == 500
    assert PROBE.STATUSES == (
        "pass1_provider_error",
        "pass1_decision_invalid",
        "pass2_provider_error",
        "pass2_lm5g_invalid",
        "pass2_invariant_violation",
        "published",
    )


def test_args_defaults_and_custom_values() -> None:
    defaults = PROBE._args([])
    assert defaults.model == PROBE.DEFAULT_MODEL
    assert defaults.scenarios == list(PROBE.SCENARIO_NAMES)
    assert defaults.attempts == 5
    assert defaults.excerpt_chars == 500

    custom = PROBE._args(
        [
            "--model",
            "gemma4:12b-it-qat",
            "--scenario",
            "evidence_absent_like",
            "--scenario",
            "evidence_present_like",
            "--attempts",
            "5",
            "--excerpt-chars",
            "1200",
        ]
    )
    assert custom.model == "gemma4:12b-it-qat"
    assert custom.scenarios == [
        "evidence_absent_like",
        "evidence_present_like",
    ]
    assert custom.attempts == 5
    assert custom.excerpt_chars == 1200


def test_args_reject_invalid_scenario_and_non_positive_attempts() -> None:
    with pytest.raises(SystemExit):
        PROBE._args(["--scenario", "missing"])

    with pytest.raises(SystemExit):
        PROBE._args(["--attempts", "0"])


def test_pass1_messages_use_real_lm5n_envelopes() -> None:
    messages, envelope = PROBE._pass1_messages_for_scenario("evidence_absent_like")

    assert [message["role"] for message in messages] == ["system", "user", "user"]
    assert envelope["schema"] == "rook.local_worker_turn_request:v1"
    assert envelope["context"]["current_node"]["node_id"] == "repair_same_component"
    assert [packet["packet_id"] for packet in envelope["context"]["knowledge"]] == [
        "script_body_gotcha"
    ]
    assert "decision JSON object" in messages[-1]["content"]


def test_pass1_messages_evidence_present_include_evidence_packet() -> None:
    _messages, envelope = PROBE._pass1_messages_for_scenario("evidence_present_like")

    assert [packet["packet_id"] for packet in envelope["context"]["knowledge"]] == [
        "script_body_gotcha",
        "lm5n_repair_evidence",
    ]


def test_extract_first_json_object_accepts_surrounding_prose() -> None:
    text = 'before {"kind": "clarification_request", "question": "Need code?"} after'

    assert PROBE._extract_first_json_object(text) == (
        '{"kind": "clarification_request", "question": "Need code?"}'
    )


def test_extract_first_json_object_handles_strings_and_nested_objects() -> None:
    text = 'x {"kind":"action_request","known_inputs":{"code":"A = { value;"},"action_id":"draft_repair_params"} y'

    assert json.loads(PROBE._extract_first_json_object(text)) == {
        "kind": "action_request",
        "known_inputs": {"code": "A = { value;"},
        "action_id": "draft_repair_params",
    }


def test_extract_first_json_object_returns_none_when_absent() -> None:
    assert PROBE._extract_first_json_object("plain prose only") is None


def test_parse_pass1_decision_accepts_minimum_valid_decisions() -> None:
    assert PROBE._parse_pass1_decision(
        '{"kind":"clarification_request","question":"Need code?"}'
    ) == (
        {
            "kind": "clarification_request",
            "question": "Need code?",
        },
        None,
    )
    assert PROBE._parse_pass1_decision(
        '{"kind":"action_request","action_id":"draft_repair_params"}'
    ) == (
        {
            "kind": "action_request",
            "action_id": "draft_repair_params",
        },
        None,
    )
    assert PROBE._parse_pass1_decision(
        '{"kind":"refusal","category":"out_of_scope","reason":"No authority."}'
    )[1] is None
    assert PROBE._parse_pass1_decision(
        '{"kind":"observation","message":"Already terminal."}'
    )[1] is None


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("plain prose", "pass1_no_json_object"),
        ("{not json}", "pass1_json_invalid:JSONDecodeError"),
        ('{"kind":"unknown"}', "pass1_unknown_kind"),
        ('{"kind":"action_request"}', "pass1_missing_action_id"),
        ('{"kind":"clarification_request"}', "pass1_missing_question"),
        ('{"kind":"refusal","reason":"No."}', "pass1_missing_refusal_category"),
        ('{"kind":"refusal","category":"out_of_scope"}', "pass1_missing_refusal_reason"),
        ('{"kind":"observation"}', "pass1_missing_observation_message"),
        ('{"kind":"observation","message":"ok","rationale":null}', "pass1_optional_rationale_type_invalid"),
        ('{"kind":"observation","message":"ok","known_inputs":[]}', "pass1_optional_known_inputs_type_invalid"),
        ('{"kind":"action_request","action_id":"draft_repair_params","action_input_intent":[]}', "pass1_optional_action_input_intent_type_invalid"),
        ('{"kind":"observation","message":"ok","data_intent":[]}', "pass1_optional_data_intent_type_invalid"),
        ('{"kind":"observation","message":"ok","rationale":{}}', "pass1_optional_rationale_type_invalid"),
        ('{"kind":"observation","message":"ok","intent":{}}', "pass1_optional_intent_type_invalid"),
    ],
)
def test_parse_pass1_decision_rejects_invalid_shapes(
    content: str,
    reason: str,
) -> None:
    decision, failure_reason = PROBE._parse_pass1_decision(content)

    assert decision is None
    assert failure_reason == reason


def test_parse_pass1_decision_records_recursion_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_recursion(_text: str) -> object:
        raise RecursionError("nested too deeply")

    monkeypatch.setattr(PROBE.json, "loads", raise_recursion)

    decision, failure_reason = PROBE._parse_pass1_decision(
        '{"kind":"clarification_request","question":"Need code?"}'
    )

    assert decision is None
    assert failure_reason == "pass1_json_invalid:RecursionError"


def test_script_help_runs_from_repo_root() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    python = repo_root / "mcp_server" / ".venv" / "Scripts" / "python.exe"
    result = subprocess.run(
        [str(python), "scripts/lm5r_two_pass_publication_probe.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "LM5R two-pass worker publication probe." in result.stdout


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
