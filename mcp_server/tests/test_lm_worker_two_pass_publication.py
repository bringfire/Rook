from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _helper_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm_worker_two_pass_publication.py"
    )


def _load_helper():
    path = _helper_path()
    spec = importlib.util.spec_from_file_location(
        "lm_worker_two_pass_publication",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


HELPER = _load_helper()


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


class _FakeProvider:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, endpoint: str, body: dict, timeout_s: float) -> str:
        self.calls.append(body)
        if not self.responses:
            raise AssertionError("unexpected provider call")
        return self.responses.pop(0)


def _request_payload() -> dict:
    return {
        "schema": "rook.local_worker_turn_request:v1",
        "context": {
            "current_node": {"node_id": "repair_same_component"},
            "allowed_actions": [
                {
                    "action_id": "draft_repair_params",
                    "kind": "draft_repair_params",
                    "description": "Draft replacement C# body repair parameters.",
                    "input_schema": {"type": "object", "required": ["code", "mode"]},
                }
            ],
            "knowledge": [],
        },
    }


def test_public_constants_match_lm5r() -> None:
    assert (
        HELPER.PASS1_DECISION_INSTRUCTION_VERSION
        == "lm5s.pass1_decision_instruction:v2"
    )
    assert HELPER.STATUSES == (
        "pass1_provider_error",
        "pass1_decision_invalid",
        "pass2_provider_error",
        "pass2_lm5g_invalid",
        "pass2_invariant_violation",
        "published",
    )


def test_successful_action_publication_returns_row_and_payload() -> None:
    provider = _FakeProvider(
        [
            _ollama_response(
                '{"kind":"action_request","action_id":"draft_repair_params"}',
                thinking="I can act.",
            ),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "action_request",
                        "action_id": "draft_repair_params",
                        "rationale": "Criteria are sufficient.",
                        "input": {"code": "A = 0.0;", "mode": "body"},
                    }
                )
            ),
        ]
    )

    result = HELPER.run_two_pass_worker_publication(
        _request_payload(),
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert result.row["status"] == "published"
    assert result.row["pass1_kind"] == "action_request"
    assert result.row["pass2_response_kind"] == "action_request"
    assert result.row["action_id_preserved"] is True
    assert result.row["lm5g_loadable"] is True
    assert result.response_payload == {
        "schema": "rook.local_worker_turn_response:v1",
        "kind": "action_request",
        "action_id": "draft_repair_params",
        "rationale": "Criteria are sufficient.",
        "input": {"code": "A = 0.0;", "mode": "body"},
    }
    assert provider.calls[0]["think"] is True
    assert provider.calls[1]["think"] is False
    assert provider.calls[1]["format"]["properties"]["action_id"]["const"] == (
        "draft_repair_params"
    )


def test_successful_clarification_publication_returns_payload() -> None:
    provider = _FakeProvider(
        [
            _ollama_response('{"kind":"clarification_request","question":"Need value?"}'),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "clarification_request",
                        "question": "Need value?",
                        "rationale": None,
                    }
                )
            ),
        ]
    )

    result = HELPER.run_two_pass_worker_publication(
        _request_payload(),
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert result.row["status"] == "published"
    assert result.row["pass1_kind"] == "clarification_request"
    assert result.response_payload["kind"] == "clarification_request"


def test_pass1_provider_error_maps_to_status() -> None:
    def provider(_endpoint: str, _body: dict, _timeout_s: float) -> str:
        raise RuntimeError("provider down")

    result = HELPER.run_two_pass_worker_publication(
        _request_payload(),
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert result.row["status"] == "pass1_provider_error"
    assert result.row["failure_reason"] == "pass1_provider_error:RuntimeError"
    assert result.response_payload is None


def test_pass1_decision_invalid_maps_to_status() -> None:
    provider = _FakeProvider([_ollama_response("plain prose only")])

    result = HELPER.run_two_pass_worker_publication(
        _request_payload(),
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert result.row["status"] == "pass1_decision_invalid"
    assert result.row["failure_reason"] == "pass1_no_json_object"
    assert result.response_payload is None


def test_pass2_lm5g_invalid_maps_to_status() -> None:
    provider = _FakeProvider(
        [
            _ollama_response('{"kind":"clarification_request","question":"Need value?"}'),
            _ollama_response('{"kind":"clarification_request","question":"Need value?"}'),
        ]
    )

    result = HELPER.run_two_pass_worker_publication(
        _request_payload(),
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert result.row["status"] == "pass2_lm5g_invalid"
    assert result.row["failure_reason"] == "pass2_lm5g_load_failed:ValueError"
    assert result.response_payload is None


def test_invariant_violation_maps_to_status_after_lm5g_load() -> None:
    provider = _FakeProvider(
        [
            _ollama_response('{"kind":"clarification_request","question":"Need value?"}'),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "observation",
                        "message": "Changed kind.",
                        "data": None,
                    }
                )
            ),
        ]
    )

    result = HELPER.run_two_pass_worker_publication(
        _request_payload(),
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert result.row["status"] == "pass2_invariant_violation"
    assert result.row["failure_reason"] == "pass2_kind_changed"
    assert result.row["lm5g_loadable"] is True
    assert result.response_payload is None


def test_observation_action_anomaly_is_scored_from_parsed_objects_only() -> None:
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
                thinking="draft_repair_params in thinking is not scored separately",
            ),
            _ollama_response(
                json.dumps(
                    {
                        "schema": "rook.local_worker_turn_response:v1",
                        "kind": "observation",
                        "message": "Visible state.",
                        "data": None,
                    }
                )
            ),
        ]
    )

    result = HELPER.run_two_pass_worker_publication(
        _request_payload(),
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        post_chat=provider,
    )

    assert result.row["status"] == "published"
    assert result.row["pass1_observation_action_intent_anomaly"] is True
    assert result.row["pass1_observation_action_intent_reasons"] == [
        "observation_data_action_id_allowed",
        "observation_message_mentions_allowed_action_id",
    ]
    assert result.row["observation_action_intent_anomaly"] is True
    assert result.response_payload["kind"] == "observation"
