from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from rook.agent.planner_worker_contract_request import (
    DESIRED_OUTPUT_VALUE_INTENT_ID,
    LM7A_TEMPLATE_ID,
    MISSING_DESIRED_OUTPUT_ROUTE_ID,
    PLANNER_INTENT_SOURCE_PATH,
    PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
)


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm7c_planner_authoring_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm7c_planner_authoring_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def _minimal_complete_request() -> dict[str, object]:
    return {
        "schema": PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
        "template_id": LM7A_TEMPLATE_ID,
        "initial_params": {
            "create_script": {
                "pins_out": ["A:double"],
            },
        },
        "routing_delta": {
            "enable_routes": [],
            "disable_routes": [],
            "set_required": {},
            "add_unresolved_intent_routes": [],
        },
        "intent_slots": [],
    }


def _exact_unresolved_slot() -> dict[str, object]:
    return {
        "intent_id": DESIRED_OUTPUT_VALUE_INTENT_ID,
        "status": "unresolved",
        "source_path": PLANNER_INTENT_SOURCE_PATH,
        "description": "Desired output value was not provided.",
    }


def _exact_unresolved_route() -> dict[str, object]:
    return {
        "route_id": MISSING_DESIRED_OUTPUT_ROUTE_ID,
        "source_class": "planner_user_intent",
        "source_path": PLANNER_INTENT_SOURCE_PATH,
        "purpose": "unresolved_intent",
        "required": False,
    }


def test_cli_defaults_are_canonical_probe_defaults() -> None:
    args = PROBE._args([])

    assert args.attempts == 5
    assert args.provider == "ceiling-provider"
    assert args.model == "ceiling-planner-model"
    assert args.temperature == 0
    assert args.run_dir == "probe_runs"
    assert args.output_excerpt_chars == 1200
    assert args.provider_timeout_s == 120
    assert args.provider_command is None
    assert args.canonical_evidence is False


def test_cli_rejects_live_and_worker_options() -> None:
    for option in (
        "--phase",
        "--retry-clean-observation",
        "--request-json",
        "--endpoint",
        "--ollama-url",
    ):
        with pytest.raises(SystemExit):
            PROBE._args([option, "x"])


def test_template_menu_is_versioned_and_single_template() -> None:
    menu = PROBE._template_menu()

    assert menu["version"] == PROBE.TEMPLATE_MENU_VERSION
    assert [item["template_id"] for item in menu["templates"]] == [LM7A_TEMPLATE_ID]
    rendered = json.dumps(menu, sort_keys=True)
    assert PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA in rendered
    assert "repair_same_component_from_create_error" in rendered


def test_briefs_are_paired_and_control_only_intent_availability() -> None:
    complete = PROBE._scenario_brief("intent_complete")
    incomplete = PROBE._scenario_brief("intent_incomplete")

    assert complete["version"] == PROBE.INTENT_COMPLETE_BRIEF_VERSION
    assert incomplete["version"] == PROBE.INTENT_INCOMPLETE_BRIEF_VERSION
    assert "7.5" in complete["text"]
    assert "7.5" not in incomplete["text"]
    assert 'pins_out: ["A:double"]' in complete["text"]
    assert 'pins_out: ["A:double"]' in incomplete["text"]


def test_prompt_contains_rules_but_no_full_request_exemplar() -> None:
    prompt = PROBE._planner_authoring_prompt()

    assert PROBE.PLANNER_AUTHORING_PROMPT_VERSION in prompt
    assert PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA in prompt
    assert "exactly one JSON object" in prompt
    assert "no markdown" in prompt.lower()
    assert '"template_id": "repair_same_component_from_create_error"' not in prompt
    assert '"initial_params": {' not in prompt
    assert '"add_unresolved_intent_routes": [' not in prompt
    assert "Output A must be assigned" not in prompt
    assert "A = " not in prompt


def test_prompt_artifacts_do_not_contain_invention_or_hidden_answer_markers() -> None:
    artifacts = {
        "prompt": PROBE._planner_authoring_prompt(),
        "template_menu": json.dumps(PROBE._template_menu(), sort_keys=True),
        "intent_complete": PROBE._scenario_brief("intent_complete")["text"],
        "intent_incomplete": PROBE._scenario_brief("intent_incomplete")["text"],
    }

    forbidden = (
        "PROBE_REPAIR_CODE",
        "A = 42.0",
        "42.0",
        "A = 0.0",
        "A = 1.0",
        "use a default",
        "set A to",
        "BindStepSpec.base_params",
        "repair_same_component.bind.base_params",
    )
    for name, artifact in artifacts.items():
        for marker in forbidden:
            assert marker not in artifact, (name, marker)

    assert "7.5" in artifacts["intent_complete"]
    assert "7.5" not in artifacts["prompt"]
    assert "7.5" not in artifacts["template_menu"]
    assert "7.5" not in artifacts["intent_incomplete"]


def test_parse_accepts_exact_json_object() -> None:
    parsed = PROBE._strict_parse_model_output(json.dumps(_minimal_complete_request()))

    assert parsed.parse_status == "parsed"
    assert parsed.payload == _minimal_complete_request()
    assert parsed.failure_reason is None


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("```json\n{}\n```", "json_decode_failed"),
        ("Here is the request: {}", "json_decode_failed"),
        ("[]", "json_not_object"),
        ("{} {}", "json_decode_failed"),
        ("{", "json_decode_failed"),
    ],
)
def test_parse_rejects_non_strict_output(raw: str, reason: str) -> None:
    parsed = PROBE._strict_parse_model_output(raw)

    assert parsed.parse_status == "parse_failed"
    assert parsed.payload is None
    assert parsed.failure_reason == reason


@pytest.mark.parametrize("payload", [{}, {"schema": "wrong:v1"}])
def test_parse_rejects_missing_or_wrong_schema(payload: dict[str, object]) -> None:
    parsed = PROBE._strict_parse_model_output(json.dumps(payload))

    assert parsed.parse_status == "parse_failed"
    assert parsed.payload is None
    assert parsed.failure_reason == "invalid_schema"


def test_intent_complete_correct_when_unresolved_slot_and_route_absent() -> None:
    request = _minimal_complete_request()

    result = PROBE._classify_intent_decision("intent_complete", request)

    assert result.intent_decision == "correct_declared"
    assert result.failure_reason is None


def test_intent_complete_over_declared_when_missing_intent_is_declared() -> None:
    request = _minimal_complete_request()
    request["intent_slots"] = [_exact_unresolved_slot()]
    request["routing_delta"]["add_unresolved_intent_routes"] = [_exact_unresolved_route()]

    result = PROBE._classify_intent_decision("intent_complete", request)

    assert result.intent_decision == "over_declared"
    assert result.failure_reason == "desired_output_value_over_declared"


@pytest.mark.parametrize("marker", ["7.5", "A = 0.0", "A = 1.0", "use a default"])
def test_intent_complete_invented_when_request_copies_or_adds_concrete_semantics(
    marker: str,
) -> None:
    request = _minimal_complete_request()
    request["extra_semantic_field"] = marker

    result = PROBE._classify_intent_decision("intent_complete", request)

    assert result.intent_decision == "invented"
    assert result.failure_reason == "invented_concrete_intent"


def test_intent_incomplete_correct_when_exact_slot_and_route_present() -> None:
    request = _minimal_complete_request()
    request["intent_slots"] = [_exact_unresolved_slot()]
    request["routing_delta"]["add_unresolved_intent_routes"] = [_exact_unresolved_route()]

    result = PROBE._classify_intent_decision("intent_incomplete", request)

    assert result.intent_decision == "correct_declared"
    assert result.failure_reason is None


def test_intent_incomplete_over_declared_when_extra_unresolved_slot_is_added() -> None:
    request = _minimal_complete_request()
    request["intent_slots"] = [
        _exact_unresolved_slot(),
        {
            "intent_id": "desired_material",
            "status": "unresolved",
            "source_path": "planner.intent.desired_material",
            "description": "Material was not provided.",
        },
    ]
    request["routing_delta"]["add_unresolved_intent_routes"] = [_exact_unresolved_route()]

    result = PROBE._classify_intent_decision("intent_incomplete", request)

    assert result.intent_decision == "over_declared"
    assert result.failure_reason == "extra_unresolved_intent"


@pytest.mark.parametrize("marker", ["0.0", "1.0", "7.5", "42.0", "A = 0.0", "set A to"])
def test_intent_incomplete_invented_when_any_concrete_value_is_filled(
    marker: str,
) -> None:
    request = _minimal_complete_request()
    request["intent_slots"] = [_exact_unresolved_slot()]
    request["routing_delta"]["add_unresolved_intent_routes"] = [_exact_unresolved_route()]
    request["invented_value"] = marker

    result = PROBE._classify_intent_decision("intent_incomplete", request)

    assert result.intent_decision == "invented"
    assert result.failure_reason == "invented_concrete_intent"


def test_intent_incomplete_missing_unresolved_identity_is_not_classifiable_failure() -> None:
    request = _minimal_complete_request()

    result = PROBE._classify_intent_decision("intent_incomplete", request)

    assert result.intent_decision == "not_classifiable"
    assert result.failure_reason == "missing_unresolved_desired_output_value"


def test_row_for_valid_complete_request_is_canonical_success() -> None:
    row = PROBE._score_model_output(
        scenario="intent_complete",
        attempt_index=0,
        provider="fake",
        model="fake-planner",
        temperature=0,
        raw_output=json.dumps(_minimal_complete_request()),
        output_excerpt_chars=120,
    )

    assert row["parse_status"] == "parsed"
    assert row["validation_status"] == "workflow_validate_valid"
    assert row["intent_decision"] == "correct_declared"
    assert row["canonical_success"] is True
    assert row["request_fingerprint"].startswith("sha256:")
    assert row["workflow_validate_report_fingerprint"].startswith("sha256:")
    assert row["failure_reason"] is None


def test_row_for_parse_failure_does_not_call_validate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_validate(_payload):
        raise AssertionError("validate must not run")

    monkeypatch.setattr(PROBE, "validate_planner_worker_contract_request", fail_validate)

    row = PROBE._score_model_output(
        scenario="intent_complete",
        attempt_index=0,
        provider="fake",
        model="fake-planner",
        temperature=0,
        raw_output="```json\n{}\n```",
        output_excerpt_chars=120,
    )

    assert row["parse_status"] == "parse_failed"
    assert row["validation_status"] == "not_evaluated"
    assert row["intent_decision"] == "not_classifiable"
    assert row["canonical_success"] is False
    assert row["request_fingerprint"] is None
    assert row["workflow_validate_report_fingerprint"] is None


def test_row_separates_validation_failure_from_intent_decision() -> None:
    payload = _minimal_complete_request()
    payload["unexpected"] = "schema extension"

    row = PROBE._score_model_output(
        scenario="intent_complete",
        attempt_index=0,
        provider="fake",
        model="fake-planner",
        temperature=0,
        raw_output=json.dumps(payload),
        output_excerpt_chars=120,
    )

    assert row["parse_status"] == "parsed"
    assert row["validation_status"] == "workflow_validate_failed"
    assert row["intent_decision"] == "correct_declared"
    assert row["canonical_success"] is False


def test_row_separates_valid_shape_from_over_declaration() -> None:
    payload = _minimal_complete_request()
    payload["intent_slots"] = [_exact_unresolved_slot()]
    payload["routing_delta"]["add_unresolved_intent_routes"] = [_exact_unresolved_route()]

    row = PROBE._score_model_output(
        scenario="intent_complete",
        attempt_index=0,
        provider="fake",
        model="fake-planner",
        temperature=0,
        raw_output=json.dumps(payload),
        output_excerpt_chars=120,
    )

    assert row["validation_status"] == "workflow_validate_valid"
    assert row["intent_decision"] == "over_declared"
    assert row["canonical_success"] is False


def test_run_probe_writes_artifacts_and_summary(tmp_path: Path) -> None:
    outputs = {
        ("intent_complete", 0): json.dumps(_minimal_complete_request()),
        ("intent_incomplete", 0): json.dumps(
            {
                **_minimal_complete_request(),
                "intent_slots": [_exact_unresolved_slot()],
                "routing_delta": {
                    **_minimal_complete_request()["routing_delta"],
                    "add_unresolved_intent_routes": [_exact_unresolved_route()],
                },
            }
        ),
    }

    def fake_provider(call_payload):
        return outputs[(call_payload["scenario"], call_payload["attempt_index"])]

    run_dir = PROBE._run_probe(
        run_root=tmp_path,
        provider="fake",
        model="fake-planner",
        temperature=0,
        attempts=1,
        canonical_evidence=False,
        output_excerpt_chars=120,
        call_provider=fake_provider,
    )

    assert run_dir.name.startswith("lm7c-")
    assert (run_dir / "manifest.json").is_file()
    assert (run_dir / "rows.jsonl").is_file()
    assert (run_dir / "summary.json").is_file()
    assert (run_dir / "prompts" / "planner_authoring_prompt.txt").is_file()
    assert (run_dir / "prompts" / "template_menu.json").is_file()
    assert (run_dir / "prompts" / "intent_complete_brief.txt").is_file()
    assert (run_dir / "prompts" / "intent_incomplete_brief.txt").is_file()

    rows = [
        json.loads(line)
        for line in (run_dir / "rows.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 2
    assert all(row["canonical_success"] for row in rows)

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["scheduled_attempts_per_scenario"] == 1
    assert summary["scenario_counts"]["intent_complete"]["canonical_success_count"] == 1
    assert summary["scenario_counts"]["intent_incomplete"]["canonical_success_count"] == 1


def test_summary_counts_parse_validation_intent_and_canonical_success() -> None:
    rows = [
        {
            "scenario": "intent_complete",
            "parse_status": "parsed",
            "validation_status": "workflow_validate_valid",
            "intent_decision": "correct_declared",
            "canonical_success": True,
        },
        {
            "scenario": "intent_complete",
            "parse_status": "parsed",
            "validation_status": "workflow_validate_valid",
            "intent_decision": "over_declared",
            "canonical_success": False,
        },
        {
            "scenario": "intent_incomplete",
            "parse_status": "parse_failed",
            "validation_status": "not_evaluated",
            "intent_decision": "not_classifiable",
            "canonical_success": False,
        },
    ]

    summary = PROBE._summarize_rows(
        rows,
        attempts=5,
        provider="fake",
        model="fake-planner",
        temperature=0,
        canonical_evidence=False,
    )

    assert summary["parse_success_count"] == 2
    assert summary["workflow_validate_valid_count"] == 2
    assert summary["correct_intent_count"] == 1
    assert summary["canonical_success_count"] == 1
    assert summary["over_declared_count"] == 1
    assert summary["invented_count"] == 0
    assert summary["not_classifiable_count"] == 1


def test_main_requires_provider_command_for_cli_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        PROBE.main(["--run-dir", str(tmp_path), "--provider", "ceiling-provider"])

    assert exc.value.code == 2
    assert "provider_command_required" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["--canonical-evidence", "--attempts", "1"],
        ["--canonical-evidence", "--provider", "fake", "--model", "fake-planner"],
        [
            "--canonical-evidence",
            "--provider",
            "ceiling-provider",
            "--model",
            "ceiling-planner-model",
        ],
        [
            "--canonical-evidence",
            "--provider",
            "ollama",
            "--model",
            "gemma4:12b-it-qat",
        ],
    ],
)
def test_main_rejects_invalid_canonical_evidence_declarations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        PROBE.main(
            [
                "--run-dir",
                str(tmp_path),
                "--provider-command",
                "fake-provider",
                *argv,
            ]
        )

    assert exc.value.code == 2
    assert "invalid_canonical_evidence" in capsys.readouterr().err


def test_main_uses_injected_provider_command_without_live_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_command(command, call_payload, timeout_s):
        calls.append((command, call_payload, timeout_s))
        return json.dumps(_minimal_complete_request())

    monkeypatch.setattr(PROBE, "_call_provider_command", fake_command)

    exit_code = PROBE.main(
        [
            "--run-dir",
            str(tmp_path),
            "--attempts",
            "1",
            "--provider",
            "fake-provider-label",
            "--provider-command",
            "fake-provider",
            "--model",
            "fake-planner",
        ]
    )

    assert exit_code == 0
    assert calls


def test_lm7c_script_does_not_import_live_worker_or_rhino_surfaces() -> None:
    source = _script_path().read_text(encoding="utf-8")

    forbidden = (
        "lm7b_request_driven_live_splice_probe",
        "lm6a_live_worker_splice_probe",
        "lm_worker_two_pass_publication",
        "plan_graph_worker_action_apply",
        "_mcp_tool_executor",
        "run_live_producer_node",
        "run_live_repair",
        "rhino_ping",
        "gh_document_new",
        "gh_update_script",
    )
    for token in forbidden:
        assert token not in source
