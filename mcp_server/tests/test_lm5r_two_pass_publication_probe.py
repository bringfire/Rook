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


def _ollama_response(
    content: str,
    *,
    thinking: str | None = None,
    prompt_eval_count: int = 10,
    eval_count: int = 20,
) -> str:
    message: dict[str, str] = {"content": content}
    if thinking is not None:
        message["thinking"] = thinking
    return json.dumps(
        {
            "message": message,
            "prompt_eval_count": prompt_eval_count,
            "eval_count": eval_count,
            "done_reason": "stop",
        }
    )


def _summary_row(
    *,
    scenario: str = "evidence_absent_like",
    status: str = "published",
    pass1_kind: str | None = "clarification_request",
    pass2_response_kind: str | None = "clarification_request",
    kind_preserved: bool | None = True,
    action_id_preserved: bool | None = None,
    refusal_category_preserved: bool | None = None,
    lm5g_loadable: bool = True,
    failure_reason: str | None = None,
    observation_action_intent_anomaly: bool = False,
    observation_action_intent_reasons: list[str] | None = None,
) -> dict:
    return {
        "scenario": scenario,
        "status": status,
        "pass1_kind": pass1_kind,
        "pass2_response_kind": pass2_response_kind,
        "kind_preserved": kind_preserved,
        "action_id_preserved": action_id_preserved,
        "refusal_category_preserved": refusal_category_preserved,
        "lm5g_loadable": lm5g_loadable,
        "failure_reason": failure_reason,
        "observation_action_intent_anomaly": observation_action_intent_anomaly,
        "observation_action_intent_reasons": observation_action_intent_reasons or [],
    }


class _FakeProvider:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, endpoint: str, body: dict, timeout_s: float) -> str:
        self.calls.append(body)
        if not self.responses:
            raise AssertionError("unexpected provider call")
        return self.responses.pop(0)


def test_constants_are_pinned() -> None:
    assert PROBE.SCRIPT_SCHEMA == "rook.lm5r_two_pass_publication_probe:v1"
    assert (
        PROBE.PASS1_DECISION_INSTRUCTION_VERSION
        == "lm5s.pass1_decision_instruction:v2"
    )
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


def test_pass1_instruction_v2_pins_generic_kind_semantics() -> None:
    text = PROBE._PASS1_DECISION_INSTRUCTION
    normalized_text = " ".join(text.split())

    assert "action_request" in text
    assert "visible context is sufficient" in text
    assert "author the required action input" in normalized_text
    assert "clarification_request" in text
    assert "required information is missing" in text
    assert "refusal" in text
    assert "unsafe, unsupported, or out of scope" in text
    assert "observation" in text
    assert "visible state or evidence" in text
    assert "Do not use observation to choose, suggest, imply, or carry an action" in text
    assert "Do not put action identity or action choice" in text


def test_pass1_instruction_v2_contains_no_scenario_specific_literals() -> None:
    text = PROBE._PASS1_DECISION_INSTRUCTION
    forbidden_literals = [
        "draft_repair_params",
        "repair_same_component",
        "component_guid",
        "RunScript",
        "DefinitelyMissingSymbol",
        '"code"',
        '"mode"',
        "gemma",
        "Gemma",
    ]

    for literal in forbidden_literals:
        assert literal not in text


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


def test_observation_action_intent_reasons_ignore_non_observation_payloads() -> None:
    assert PROBE._observation_action_intent_reasons(
        payload={"kind": "action_request", "action_id": "draft_repair_params"},
        allowed_action_ids=("draft_repair_params",),
    ) == ()


def test_observation_action_intent_reasons_detect_data_action_id_only_once() -> None:
    assert PROBE._observation_action_intent_reasons(
        payload={
            "kind": "observation",
            "message": "State report.",
            "data": {"action_id": "draft_repair_params"},
        },
        allowed_action_ids=("draft_repair_params",),
    ) == ("observation_data_action_id_allowed",)


def test_observation_action_intent_reasons_detect_message_action_id() -> None:
    assert PROBE._observation_action_intent_reasons(
        payload={
            "kind": "observation",
            "message": "I would call draft_repair_params next.",
            "data": None,
        },
        allowed_action_ids=("draft_repair_params",),
    ) == ("observation_message_mentions_allowed_action_id",)


def test_observation_action_intent_reasons_detect_top_level_data_string_action_id_text() -> None:
    assert PROBE._observation_action_intent_reasons(
        payload={
            "kind": "observation",
            "message": "State report.",
            "data": "candidate action draft_repair_params",
        },
        allowed_action_ids=("draft_repair_params",),
    ) == ("observation_data_mentions_allowed_action_id",)


def test_observation_action_intent_reasons_detect_top_level_data_list_action_id_text() -> None:
    assert PROBE._observation_action_intent_reasons(
        payload={
            "kind": "observation",
            "message": "State report.",
            "data": ["other", "candidate action draft_repair_params"],
        },
        allowed_action_ids=("draft_repair_params",),
    ) == ("observation_data_mentions_allowed_action_id",)


def test_observation_action_intent_reasons_detect_nested_data_action_id_text() -> None:
    assert PROBE._observation_action_intent_reasons(
        payload={
            "kind": "observation",
            "message": "State report.",
            "data": {
                "note": "candidate action draft_repair_params",
                "nested": ["other", {"text": "use draft_repair_params"}],
            },
        },
        allowed_action_ids=("draft_repair_params",),
    ) == ("observation_data_mentions_allowed_action_id",)


def test_observation_action_intent_reasons_detect_data_intent_action_id_text() -> None:
    assert PROBE._observation_action_intent_reasons(
        payload={
            "kind": "observation",
            "message": "State report.",
            "data_intent": {"action_id": "draft_repair_params"},
        },
        allowed_action_ids=("draft_repair_params",),
    ) == ("observation_data_intent_mentions_allowed_action_id",)


def test_observation_action_intent_reasons_sort_and_deduplicate_reasons() -> None:
    assert PROBE._observation_action_intent_reasons(
        payload={
            "kind": "observation",
            "message": "draft_repair_params",
            "data": {
                "action_id": "draft_repair_params",
                "note": "draft_repair_params",
            },
            "data_intent": "draft_repair_params",
        },
        allowed_action_ids=("draft_repair_params",),
    ) == (
        "observation_data_action_id_allowed",
        "observation_data_intent_mentions_allowed_action_id",
        "observation_data_mentions_allowed_action_id",
        "observation_message_mentions_allowed_action_id",
    )


def test_single_kind_schema_action_request_const_pins_kind_and_action_id() -> None:
    schema = PROBE._single_kind_response_schema(
        {"kind": "action_request", "action_id": "draft_repair_params"}
    )

    assert "oneOf" not in schema
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["schema", "kind", "action_id", "rationale", "input"]
    assert schema["properties"]["schema"]["const"] == "rook.local_worker_turn_response:v1"
    assert schema["properties"]["kind"]["const"] == "action_request"
    assert schema["properties"]["action_id"]["const"] == "draft_repair_params"
    assert schema["properties"]["input"]["type"] == "object"


def test_single_kind_schema_clarification_request_shape() -> None:
    schema = PROBE._single_kind_response_schema(
        {"kind": "clarification_request", "question": "Need code?"}
    )

    assert "oneOf" not in schema
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["schema", "kind", "question", "rationale"]
    assert schema["properties"]["schema"]["const"] == "rook.local_worker_turn_response:v1"
    assert schema["properties"]["kind"]["const"] == "clarification_request"
    assert schema["properties"]["question"]["type"] == "string"
    assert schema["properties"]["rationale"]["type"] == ["string", "null"]


def test_single_kind_schema_refusal_const_pins_category() -> None:
    schema = PROBE._single_kind_response_schema(
        {"kind": "refusal", "category": "out_of_scope", "reason": "No authority."}
    )

    assert "oneOf" not in schema
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["schema", "kind", "category", "reason"]
    assert schema["properties"]["schema"]["const"] == "rook.local_worker_turn_response:v1"
    assert schema["properties"]["kind"]["const"] == "refusal"
    assert schema["properties"]["category"]["const"] == "out_of_scope"
    assert schema["properties"]["reason"]["type"] == "string"


def test_single_kind_schema_observation_shape() -> None:
    schema = PROBE._single_kind_response_schema(
        {"kind": "observation", "message": "Done."}
    )

    assert "oneOf" not in schema
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["schema", "kind", "message", "data"]
    assert schema["properties"]["schema"]["const"] == "rook.local_worker_turn_response:v1"
    assert schema["properties"]["kind"]["const"] == "observation"
    assert schema["properties"]["message"]["type"] == "string"
    assert schema["properties"]["data"]["type"] == ["object", "null"]


def test_formatter_messages_are_not_lm5j_worker_messages() -> None:
    request_payload = {"schema": "rook.local_worker_turn_request:v1", "context": {}}
    decision = {"kind": "clarification_request", "question": "Need code?"}
    schema = PROBE._single_kind_response_schema(decision)

    messages = PROBE._formatter_messages(request_payload, decision, schema)

    assert [message["role"] for message in messages] == ["system", "user"]
    assert "formatting an already-made Rook worker decision" in messages[0]["content"]
    payload = json.loads(messages[1]["content"])
    assert payload["request_envelope"] == request_payload
    assert payload["decision"] == decision
    assert payload["kind"] == "clarification_request"
    assert payload["response_schema"] == "rook.local_worker_turn_response:v1"
    assert payload["single_kind_schema"] == schema


def test_pass2_request_body_uses_single_kind_format_and_think_false() -> None:
    request_payload = {"schema": "rook.local_worker_turn_request:v1", "context": {}}
    decision = {"kind": "action_request", "action_id": "draft_repair_params"}
    schema = PROBE._single_kind_response_schema(decision)

    body = PROBE._build_pass2_body(
        model="gemma4:12b-it-qat",
        request_payload=request_payload,
        decision=decision,
        single_kind_schema=schema,
        temperature=0,
    )

    assert body["model"] == "gemma4:12b-it-qat"
    assert body["stream"] is False
    assert body["think"] is False
    assert body["format"] == schema
    assert body["format"] is not schema
    assert body["format"]["properties"] is not schema["properties"]
    body["format"]["properties"]["action_id"]["const"] = "mutated"
    assert schema["properties"]["action_id"]["const"] == "draft_repair_params"
    assert body["options"]["temperature"] == 0
    assert body["messages"] == PROBE._formatter_messages(
        request_payload,
        decision,
        schema,
    )


def test_run_attempt_stops_before_pass2_when_pass1_decision_missing_action_id() -> None:
    provider = _FakeProvider(
        [
            _ollama_response('{"kind":"action_request"}', thinking="deciding"),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_present_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["status"] == "pass1_decision_invalid"
    assert row["failure_reason"] == "pass1_missing_action_id"
    assert len(provider.calls) == 1
    assert row["pass1_kind"] is None
    assert row["lm5g_loadable"] is False


def test_run_attempt_records_pass1_provider_error() -> None:
    def raising_provider(endpoint: str, body: dict, timeout_s: float) -> str:
        raise RuntimeError("boom")

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_absent_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=raising_provider,
    )

    assert row["status"] == "pass1_provider_error"
    assert row["failure_reason"] == "pass1_provider_error:RuntimeError"


def test_run_attempt_publishes_valid_same_kind_clarification() -> None:
    provider = _FakeProvider(
        [
            _ollama_response(
                '{"kind":"clarification_request","question":"Please provide the current code."}',
                thinking="need code",
            ),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "clarification_request",
                        "question": "Please provide the current code.",
                        "rationale": "The request lacks code.",
                    }
                )
            ),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_absent_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["status"] == "published"
    assert row["failure_reason"] is None
    assert row["pass1_kind"] == "clarification_request"
    assert row["pass2_response_kind"] == "clarification_request"
    assert row["kind_preserved"] is True
    assert row["action_id_preserved"] is None
    assert row["lm5g_loadable"] is True
    assert provider.calls[1]["think"] is False


def test_run_attempt_records_pass1_observation_action_intent_anomaly() -> None:
    provider = _FakeProvider(
        [
            _ollama_response(
                json.dumps(
                    {
                        "kind": "observation",
                        "message": "Decision: draft_repair_params",
                        "data": {"action_id": "draft_repair_params"},
                    }
                ),
                thinking="state report",
            ),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "observation",
                        "message": "State only.",
                        "data": None,
                    }
                )
            ),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_present_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    expected_reasons = [
        "observation_data_action_id_allowed",
        "observation_message_mentions_allowed_action_id",
    ]
    assert row["status"] == "published"
    assert row["pass1_observation_action_intent_anomaly"] is True
    assert row["pass1_observation_action_intent_reasons"] == expected_reasons
    assert row["pass2_observation_action_intent_anomaly"] is False
    assert row["pass2_observation_action_intent_reasons"] == []
    assert row["observation_action_intent_anomaly"] is True
    assert row["observation_action_intent_reasons"] == expected_reasons


def test_run_attempt_records_pass2_observation_action_intent_anomaly_after_lm5g_load() -> None:
    provider = _FakeProvider(
        [
            _ollama_response(
                json.dumps(
                    {
                        "kind": "observation",
                        "message": "Visible state only.",
                        "data": None,
                    }
                )
            ),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "observation",
                        "message": "State report.",
                        "data": {"note": "draft_repair_params"},
                    }
                )
            ),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_present_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    expected_reasons = ["observation_data_mentions_allowed_action_id"]
    assert row["status"] == "published"
    assert row["pass1_observation_action_intent_anomaly"] is False
    assert row["pass1_observation_action_intent_reasons"] == []
    assert row["pass2_observation_action_intent_anomaly"] is True
    assert row["pass2_observation_action_intent_reasons"] == expected_reasons
    assert row["observation_action_intent_anomaly"] is True
    assert row["observation_action_intent_reasons"] == expected_reasons


def test_run_attempt_does_not_score_pass2_anomaly_when_lm5g_load_fails() -> None:
    provider = _FakeProvider(
        [
            _ollama_response(
                json.dumps(
                    {
                        "kind": "observation",
                        "message": "Visible state only.",
                        "data": None,
                    }
                )
            ),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "observation",
                        "message": "draft_repair_params",
                    }
                )
            ),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_present_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["status"] == "pass2_lm5g_invalid"
    assert row["failure_reason"] == "pass2_lm5g_load_failed:ValueError"
    assert row["pass2_observation_action_intent_anomaly"] is False
    assert row["pass2_observation_action_intent_reasons"] == []


def test_run_attempt_reports_pass2_kind_changed_after_lm5g_load() -> None:
    provider = _FakeProvider(
        [
            _ollama_response('{"kind":"clarification_request","question":"Need code?"}'),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "observation",
                        "message": "I changed kind.",
                        "data": None,
                    }
                )
            ),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_absent_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["lm5g_loadable"] is True
    assert row["status"] == "pass2_invariant_violation"
    assert row["failure_reason"] == "pass2_kind_changed"
    assert row["kind_preserved"] is False


def test_run_attempt_reports_pass2_action_id_changed_after_lm5g_load() -> None:
    provider = _FakeProvider(
        [
            _ollama_response('{"kind":"action_request","action_id":"draft_repair_params"}'),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "action_request",
                        "action_id": "other_action",
                        "rationale": "Changed action.",
                        "input": {},
                    }
                )
            ),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_present_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["lm5g_loadable"] is True
    assert row["status"] == "pass2_invariant_violation"
    assert row["failure_reason"] == "pass2_action_id_changed"
    assert row["action_id_preserved"] is False


def test_run_attempt_reports_pass2_refusal_category_changed_after_lm5g_load() -> None:
    provider = _FakeProvider(
        [
            _ollama_response(
                '{"kind":"refusal","category":"out_of_scope","reason":"No authority."}'
            ),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "refusal",
                        "category": "unsafe",
                        "reason": "Changed category.",
                    }
                )
            ),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_absent_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["lm5g_loadable"] is True
    assert row["status"] == "pass2_invariant_violation"
    assert row["failure_reason"] == "pass2_refusal_category_changed"
    assert row["refusal_category_preserved"] is False


def test_run_attempt_reports_pass2_lm5g_invalid() -> None:
    provider = _FakeProvider(
        [
            _ollama_response('{"kind":"clarification_request","question":"Need code?"}'),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "clarification_request",
                        "question": "Need code?",
                    }
                )
            ),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_absent_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["status"] == "pass2_lm5g_invalid"
    assert row["failure_reason"] == "pass2_lm5g_load_failed:ValueError"
    assert row["lm5g_loadable"] is False


def test_provider_message_fields_records_recursion_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_recursion(_text: str) -> object:
        raise RecursionError("nested too deeply")

    monkeypatch.setattr(PROBE.json, "loads", raise_recursion)

    fields, failure_reason = PROBE._provider_message_fields(
        "provider payload",
        prefix="pass1",
        excerpt_chars=500,
    )

    assert fields is None
    assert failure_reason == "pass1_provider_json_invalid:RecursionError"


def test_build_summary_groups_by_status_kind_and_preservation() -> None:
    rows = [
        _summary_row(),
        _summary_row(
            scenario="evidence_absent_like",
            pass1_kind="observation",
            pass2_response_kind="observation",
            observation_action_intent_anomaly=True,
            observation_action_intent_reasons=[
                "observation_data_action_id_allowed",
                "observation_message_mentions_allowed_action_id",
            ],
        ),
        _summary_row(
            scenario="evidence_present_like",
            pass1_kind="action_request",
            pass2_response_kind="action_request",
            action_id_preserved=True,
        ),
        _summary_row(
            scenario="evidence_present_like",
            status="pass2_invariant_violation",
            pass1_kind="action_request",
            pass2_response_kind="action_request",
            action_id_preserved=False,
            failure_reason="pass2_action_id_changed",
        ),
    ]

    summary = PROBE._build_summary(
        run_id="lm5r-demo",
        git_commit="abc1234",
        model="gemma4:12b-it-qat",
        scenarios=["evidence_absent_like", "evidence_present_like"],
        attempts_per_scenario=5,
        rows=rows,
    )

    assert summary["run_id"] == "lm5r-demo"
    assert summary["git_commit"] == "abc1234"
    assert summary["model"] == "gemma4:12b-it-qat"
    assert summary["scenarios"] == ["evidence_absent_like", "evidence_present_like"]
    assert summary["attempts_per_scenario"] == 5
    assert summary["groups"] == [
        {
            "scenario": "evidence_absent_like",
            "status": "published",
            "pass1_kind": "clarification_request",
            "pass2_response_kind": "clarification_request",
            "kind_preserved": True,
            "action_id_preserved": None,
            "refusal_category_preserved": None,
            "attempts": 1,
            "lm5g_loadable_count": 1,
            "failure_reason_counts": {},
            "observation_action_intent_anomaly_count": 0,
            "observation_action_intent_reason_counts": {},
        },
        {
            "scenario": "evidence_absent_like",
            "status": "published",
            "pass1_kind": "observation",
            "pass2_response_kind": "observation",
            "kind_preserved": True,
            "action_id_preserved": None,
            "refusal_category_preserved": None,
            "attempts": 1,
            "lm5g_loadable_count": 1,
            "failure_reason_counts": {},
            "observation_action_intent_anomaly_count": 1,
            "observation_action_intent_reason_counts": {
                "observation_data_action_id_allowed": 1,
                "observation_message_mentions_allowed_action_id": 1,
            },
        },
        {
            "scenario": "evidence_present_like",
            "status": "pass2_invariant_violation",
            "pass1_kind": "action_request",
            "pass2_response_kind": "action_request",
            "kind_preserved": True,
            "action_id_preserved": False,
            "refusal_category_preserved": None,
            "attempts": 1,
            "lm5g_loadable_count": 1,
            "failure_reason_counts": {"pass2_action_id_changed": 1},
            "observation_action_intent_anomaly_count": 0,
            "observation_action_intent_reason_counts": {},
        },
        {
            "scenario": "evidence_present_like",
            "status": "published",
            "pass1_kind": "action_request",
            "pass2_response_kind": "action_request",
            "kind_preserved": True,
            "action_id_preserved": True,
            "refusal_category_preserved": None,
            "attempts": 1,
            "lm5g_loadable_count": 1,
            "failure_reason_counts": {},
            "observation_action_intent_anomaly_count": 0,
            "observation_action_intent_reason_counts": {},
        },
    ]


def test_run_probe_writes_manifest_attempts_and_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    rows_returned = [
        _summary_row(scenario="evidence_absent_like"),
        _summary_row(
            scenario="evidence_present_like",
            pass1_kind="action_request",
            pass2_response_kind="action_request",
            action_id_preserved=True,
        ),
    ]
    calls: list[tuple[str, int]] = []

    def fake_run_attempt(**kwargs):
        calls.append((kwargs["scenario"], kwargs["attempt"]))
        return rows_returned[len(calls) - 1]

    monkeypatch.setattr(PROBE, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(PROBE, "_git_short_sha", lambda: "abc1234")
    monkeypatch.setattr(PROBE, "_ollama_version", lambda: "ollama version is 0.31.1")
    monkeypatch.setattr(
        PROBE,
        "_model_metadata",
        lambda model: {
            "model": model,
            "model_id": None,
            "model_quantization": "Q4_0",
            "ollama_show_status": "ok",
            "ollama_show_excerpt": "quantization        Q4_0",
        },
    )
    monkeypatch.setattr(PROBE, "_run_attempt", fake_run_attempt)

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        scenarios=["evidence_absent_like", "evidence_present_like"],
        endpoint="http://fake.local/api/chat",
        temperature=0,
        attempts_per_scenario=1,
        timeout_s=9,
        excerpt_chars=500,
    )

    assert calls == [("evidence_absent_like", 1), ("evidence_present_like", 1)]
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["script_schema"] == "rook.lm5r_two_pass_publication_probe:v1"
    assert manifest["git_commit"] == "abc1234"
    assert manifest["model"]["model"] == "gemma4:12b-it-qat"
    assert manifest["scenarios"] == ["evidence_absent_like", "evidence_present_like"]
    assert manifest["attempts_per_scenario"] == 1
    assert (
        manifest["pass1_decision_instruction_version"]
        == PROBE.PASS1_DECISION_INSTRUCTION_VERSION
    )
    assert manifest["pass1_decision_instruction_sha256"] == PROBE._sha256_text(
        PROBE._PASS1_DECISION_INSTRUCTION
    )

    attempt_rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert attempt_rows == rows_returned

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["run_id"] == run_dir.name
    assert len(summary["groups"]) == 2


def test_run_attempt_reports_pass2_content_recursion_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_loads = json.loads

    def loads_with_recursion(text: str) -> object:
        if text == "RECURSIVE_CONTENT":
            raise RecursionError("nested too deeply")
        return real_loads(text)

    monkeypatch.setattr(PROBE.json, "loads", loads_with_recursion)
    provider = _FakeProvider(
        [
            _ollama_response('{"kind":"clarification_request","question":"Need code?"}'),
            _ollama_response("RECURSIVE_CONTENT"),
        ]
    )

    row = PROBE._run_attempt(
        model="gemma4:12b-it-qat",
        scenario="evidence_absent_like",
        attempt=1,
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert row["status"] == "pass2_lm5g_invalid"
    assert row["failure_reason"] == "pass2_content_json_invalid:RecursionError"
    assert row["lm5g_loadable"] is False


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
