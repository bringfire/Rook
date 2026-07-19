from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm9b_c_compiler_sufficiency_support.py"
    )


def _load_support():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm9b_c_compiler_sufficiency_support",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SUPPORT = _load_support()
_FIXTURE_DIR = Path(__file__).with_name("fixtures")


def _preserved_first_candidate() -> str:
    fixture = json.loads(
        (_FIXTURE_DIR / "lm9b_c_first_candidate.json").read_text(encoding="utf-8")
    )
    source = fixture["source"]
    digest = "sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()
    assert digest == fixture["source_sha256"]
    assert len(source.encode("utf-8")) == 1661
    return source


def _contract_index() -> dict[str, object]:
    return {
        "recipe_fingerprint": "sha256:" + "1" * 64,
        "maintains_clause_ids": ["maintained.radial_box_field"],
        "requires_clause_ids": ["required.document_unit_context"],
        "invariant_clause_ids": [],
        "postcondition_clause_ids": [
            "postcondition.box_geometry",
            "postcondition.element_count",
        ],
        "shape_delegation_ids": [
            "shape.delegate.representation",
            "shape.delegate.topology",
            "shape.delegate.verification",
        ],
        "capability_ids": ["capability.construct_parametric_geometry"],
        "support_ids": [
            "assumption.grid_spacing",
            "derived.element_count",
            "task_envelope:/facts/grid_count_x",
        ],
    }


def _candidate() -> dict[str, object]:
    return {
        "schema": SUPPORT.COMPILER_RESULT_SCHEMA_ID,
        "result_kind": "compiled_candidate",
        "recipe_fingerprint": "sha256:" + "1" * 64,
        "compiled_candidate": {
            "representation": {
                "kind": "csharp_script_instance",
                "pins_in": [],
                "pins_out": [
                    {"name": "Geometry", "type": "Brep", "access": "list"}
                ],
                "source": (
                    "public class Script_Instance : GH_ScriptInstance { "
                    "private void RunScript(ref object Geometry) { Geometry = null; } }"
                ),
            },
            "decisions": [
                {
                    "decision_id": "decision.material.spacing",
                    "decision_kind": "material_semantic",
                    "statement": "Use the authorized grid spacing.",
                    "maintains_clause_id": "maintained.radial_box_field",
                    "support_refs": ["assumption.grid_spacing"],
                    "requires_or_invariant_clause_id": None,
                    "shape_delegation_id": None,
                    "capability_id": None,
                },
                {
                    "decision_id": "decision.implementation.script",
                    "decision_kind": "implementation",
                    "statement": "Lower the field into one C# script component.",
                    "maintains_clause_id": "maintained.radial_box_field",
                    "support_refs": [],
                    "requires_or_invariant_clause_id": None,
                    "shape_delegation_id": "shape.delegate.representation",
                    "capability_id": "capability.construct_parametric_geometry",
                },
                {
                    "decision_id": "decision.guard.units",
                    "decision_kind": "guard_or_read",
                    "statement": "Interpret dimensions in the current unit context.",
                    "maintains_clause_id": None,
                    "support_refs": [],
                    "requires_or_invariant_clause_id": (
                        "required.document_unit_context"
                    ),
                    "shape_delegation_id": None,
                    "capability_id": None,
                },
            ],
            "verification_plan": [
                {
                    "verification_id": "verification.box_geometry",
                    "clause_id": "postcondition.box_geometry",
                    "observation": "Observe every output Brep.",
                    "acceptance": "Every observed item is a box with authorized dimensions.",
                },
                {
                    "verification_id": "verification.element_count",
                    "clause_id": "postcondition.element_count",
                    "observation": "Count output Breps.",
                    "acceptance": "The observed count equals the derived count.",
                },
            ],
            "unused_recipe_paths": [],
        },
    }


def _insufficient() -> dict[str, object]:
    return {
        "schema": SUPPORT.COMPILER_RESULT_SCHEMA_ID,
        "result_kind": "contract_insufficient",
        "recipe_fingerprint": "sha256:" + "1" * 64,
        "contract_insufficient": {
            "missing_decisions": [
                {
                    "missing_decision_id": "missing.height_profile",
                    "statement": "No height profile is authorized.",
                    "affected_clause_ids": ["maintained.radial_box_field"],
                    "absent_authority": "No source, assumption, or derived fact supplies it.",
                    "why_delegation_is_insufficient": (
                        "Representation latitude cannot choose a material height outcome."
                    ),
                }
            ]
        },
    }


def test_compiled_candidate_schema_and_trace_are_accepted() -> None:
    result = SUPPORT.validate_terminal_submission(_candidate(), _contract_index())

    assert result.schema_valid is True
    assert result.trace_valid is True
    assert result.errors == ()
    assert result.representation_contract_ok is True
    assert result.representation_contract_error_codes == ()


def test_preserved_candidate_fails_the_exact_representation_contract() -> None:
    value = _candidate()
    value["compiled_candidate"]["representation"]["source"] = (
        _preserved_first_candidate()
    )

    result = SUPPORT.validate_terminal_submission(value, _contract_index())

    assert result.schema_valid is True
    assert result.trace_valid is True
    assert result.representation_contract_ok is False
    assert result.representation_contract_error_codes == (
        "missing_gh_script_instance_base",
        "runscript_signature_mismatch",
    )


def test_contract_insufficient_is_an_honest_terminal_variant() -> None:
    result = SUPPORT.validate_terminal_submission(_insufficient(), _contract_index())

    assert result.schema_valid is True
    assert result.trace_valid is True
    assert result.result_kind == "contract_insufficient"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (lambda value: value.update(extra=True), "terminal_schema_invalid"),
        (
            lambda value: value.__setitem__("recipe_fingerprint", "sha256:" + "2" * 64),
            "recipe_fingerprint_mismatch",
        ),
        (
            lambda value: value["compiled_candidate"]["decisions"][0].__setitem__(
                "maintains_clause_id", "goal.primary"
            ),
            "unknown_maintains_clause",
        ),
        (
            lambda value: value["compiled_candidate"]["decisions"][0].__setitem__(
                "support_refs", []
            ),
            "material_decision_missing_support",
        ),
        (
            lambda value: value["compiled_candidate"]["decisions"][1].__setitem__(
                "shape_delegation_id", None
            ),
            "implementation_decision_missing_delegation",
        ),
        (
            lambda value: value["compiled_candidate"].__setitem__(
                "verification_plan",
                value["compiled_candidate"]["verification_plan"][:1],
            ),
            "verification_coverage_missing",
        ),
    ],
)
def test_trace_checker_rejects_container_and_authority_failures(
    mutation,
    expected_code: str,
) -> None:
    value = json.loads(json.dumps(_candidate()))
    mutation(value)

    result = SUPPORT.validate_terminal_submission(value, _contract_index())

    assert expected_code in {error.code for error in result.errors}


def test_trace_checker_does_not_claim_csharp_compilation() -> None:
    value = _candidate()
    value["compiled_candidate"]["representation"]["source"] = "not valid C#"

    result = SUPPORT.validate_terminal_submission(value, _contract_index())

    assert result.schema_valid is True
    assert result.trace_valid is True
    assert result.csharp_preflight_ok is False
    assert result.csharp_compiled is None


def test_tool_definition_exposes_only_terminal_submission() -> None:
    tool = SUPPORT.compiler_tool_definition()

    assert tool["function"]["name"] == "submit_compiler_result"
    assert tool["function"]["parameters"] == {
        "type": "object",
        "properties": {
            "submission_json": {
                "type": "string",
                "description": "Exact JSON serialization of the terminal result.",
            }
        },
        "required": ["submission_json"],
    }
    assert tool["type"] == "function"


def _provider_response(
    *,
    tool_calls: list[dict[str, object]] | None = None,
    content: str | None = None,
    raw: bytes = b'{"provider":"raw"}',
    total_tokens: int = 100,
    cost_usd: float | None = 0.01,
) -> object:
    return SUPPORT.ProviderTurn(
        raw_response=raw,
        assistant_message={
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls or [],
        },
        usage={"total_tokens": total_tokens, "cost_usd": cost_usd},
        provider_metadata={"request_id": "provider-request"},
    )


def _tool_call(
    arguments: object,
    *,
    name: str = "submit_compiler_result",
    invalid_outer_json: bool = False,
) -> dict[str, object]:
    argument_name = (
        "evaluation_json" if name == "submit_evaluation_result" else "submission_json"
    )
    inner = arguments if isinstance(arguments, str) else json.dumps(arguments)
    outer = "{not-json" if invalid_outer_json else json.dumps({argument_name: inner})
    return {
        "id": "call-1",
        "type": "function",
        "function": {
            "name": name,
            "arguments": outer,
        },
    }


class _SequenceProvider:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    def __call__(self, request: dict[str, object]) -> object:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _limits(**overrides: object) -> object:
    values = {
        "max_turns": 3,
        "max_completion_tokens_per_call": 1024,
        "provider_timeout_s": 30.0,
        "overall_deadline_s": 60.0,
        "cumulative_token_stop_threshold": 10000,
        "cumulative_cost_stop_threshold_usd": 5.0,
    }
    values.update(overrides)
    return SUPPORT.SessionLimits(**values)


def test_session_uses_mechanical_feedback_then_accepts_one_valid_submission() -> None:
    provider = _SequenceProvider(
        [
            _provider_response(tool_calls=[_tool_call({"wrong": "shape"})]),
            _provider_response(
                tool_calls=[_tool_call(_candidate())],
                raw=b'{"provider":"terminal"}',
            ),
        ]
    )

    result = SUPPORT.run_compiler_session(
        provider=provider,
        system_prompt="compiler system",
        user_prompt="frozen input",
        contract_index=_contract_index(),
        limits=_limits(),
    )

    assert result.terminal_submission == _candidate()
    assert result.stop_reason == "terminal_submission"
    assert result.turn_count == 2
    assert result.turns[0].feedback_codes == ("terminal_schema_invalid",)
    assert result.turns[1].raw_provider_response == b'{"provider":"terminal"}'
    assert len(provider.requests) == 2
    feedback = json.dumps(provider.requests[1]["messages"])
    assert "terminal_schema_invalid" in feedback
    assert "radial" not in feedback.lower()
    assert "height" not in feedback.lower()


@pytest.mark.parametrize(
    ("first_response", "expected_code"),
    [
        (_provider_response(content="I will explain instead."), "terminal_tool_missing"),
        (
            _provider_response(
                tool_calls=[_tool_call(_candidate()), _tool_call(_candidate())]
            ),
            "multiple_tool_calls",
        ),
        (
            _provider_response(tool_calls=[_tool_call({}, name="other_tool")]),
            "unknown_tool",
        ),
        (
            _provider_response(tool_calls=[_tool_call({}, invalid_outer_json=True)]),
            "tool_arguments_invalid_json",
        ),
    ],
)
def test_session_structural_surprise_can_be_reconsidered_without_retry(
    first_response: object,
    expected_code: str,
) -> None:
    provider = _SequenceProvider(
        [
            first_response,
            _provider_response(tool_calls=[_tool_call(_insufficient())]),
        ]
    )

    result = SUPPORT.run_compiler_session(
        provider=provider,
        system_prompt="compiler system",
        user_prompt="frozen input",
        contract_index=_contract_index(),
        limits=_limits(),
    )

    assert result.stop_reason == "terminal_submission"
    assert result.turn_count == 2
    assert result.turns[0].feedback_codes == (expected_code,)
    assert result.terminal_submission["result_kind"] == "contract_insufficient"


def test_session_provider_failure_is_inconclusive_control_evidence() -> None:
    provider = _SequenceProvider([RuntimeError("provider unavailable")])

    result = SUPPORT.run_compiler_session(
        provider=provider,
        system_prompt="compiler system",
        user_prompt="frozen input",
        contract_index=_contract_index(),
        limits=_limits(),
    )

    assert result.stop_reason == "provider_failure"
    assert result.terminal_submission is None
    assert result.control_error == "RuntimeError"
    assert result.control_evidence == {
        "failure_type": "RuntimeError",
        "message": "provider unavailable",
    }
    assert "provider unavailable" in json.dumps(result.to_summary())


def test_provider_call_failure_preserves_exact_request_and_error_bytes() -> None:
    failure = SUPPORT.ProviderCallFailure(
        failure_type="BadRequestError",
        message="tool schema rejected",
        raw_request=b'{"request":"exact"}',
        raw_error=b'{"error":"schema"}',
    )
    provider = _SequenceProvider([failure])

    result = SUPPORT.run_compiler_session(
        provider=provider,
        system_prompt="compiler system",
        user_prompt="frozen input",
        contract_index=_contract_index(),
        limits=_limits(),
    )

    assert result.stop_reason == "provider_failure"
    assert result.raw_control_request == b'{"request":"exact"}'
    assert result.raw_control_error == b'{"error":"schema"}'
    assert result.control_evidence["message"] == "tool schema rejected"


def test_session_exhausts_turn_bound_without_external_retry() -> None:
    provider = _SequenceProvider(
        [_provider_response(content="no submission") for _ in range(3)]
    )

    result = SUPPORT.run_compiler_session(
        provider=provider,
        system_prompt="compiler system",
        user_prompt="frozen input",
        contract_index=_contract_index(),
        limits=_limits(max_turns=3),
    )

    assert result.stop_reason == "max_turns_exhausted"
    assert result.turn_count == 3
    assert result.terminal_submission is None
    assert len(provider.requests) == 3


def test_session_token_and_cost_values_are_post_response_stop_thresholds() -> None:
    provider = _SequenceProvider(
        [_provider_response(content="no submission", total_tokens=1200, cost_usd=0.5)]
    )

    result = SUPPORT.run_compiler_session(
        provider=provider,
        system_prompt="compiler system",
        user_prompt="frozen input",
        contract_index=_contract_index(),
        limits=_limits(
            cumulative_token_stop_threshold=1000,
            cumulative_cost_stop_threshold_usd=10.0,
        ),
    )

    assert result.stop_reason == "token_stop_threshold_reached"
    assert result.total_tokens == 1200
    assert result.terminal_submission is None


def test_valid_terminal_submission_wins_after_already_incurred_usage() -> None:
    provider = _SequenceProvider(
        [
            _provider_response(
                tool_calls=[_tool_call(_candidate())],
                total_tokens=1200,
                cost_usd=0.5,
            )
        ]
    )

    result = SUPPORT.run_compiler_session(
        provider=provider,
        system_prompt="compiler system",
        user_prompt="frozen input",
        contract_index=_contract_index(),
        limits=_limits(cumulative_token_stop_threshold=1000),
    )

    assert result.stop_reason == "terminal_submission"
    assert result.terminal_submission is not None


def _candidate_evaluation(*, accepted: bool = True) -> dict[str, object]:
    status = "accepted" if accepted else "rejected"
    return {
        "schema": SUPPORT.EVALUATION_REPORT_SCHEMA_ID,
        "evaluated_result_kind": "compiled_candidate",
        "decision": status,
        "candidate_assessment": {
            "source_fidelity": status,
            "material_authority": status,
            "representation_coherence": status,
            "verification_fidelity": status,
        },
        "issue_codes": [] if accepted else ["material_invention"],
        "bounded_rationale": "The candidate stays within the supplied contract.",
    }


def _gap_evaluation(*, necessary: bool = True) -> dict[str, object]:
    return {
        "schema": SUPPORT.EVALUATION_REPORT_SCHEMA_ID,
        "evaluated_result_kind": "contract_insufficient",
        "decision": "accepted" if necessary else "rejected",
        "contract_gap_assessment": {
            "missing_decision_precise": True,
            "absent_from_semantic_source": True,
            "necessary_for_conforming_lowering": necessary,
            "outside_delegated_latitude": True,
        },
        "issue_codes": [] if necessary else ["gap_not_necessary"],
        "bounded_rationale": "The reported gap is checked against the source.",
    }


def _terminal_session(value: dict[str, object]) -> object:
    provider = _SequenceProvider([_provider_response(tool_calls=[_tool_call(value)])])
    return SUPPORT.run_compiler_session(
        provider=provider,
        system_prompt="compiler system",
        user_prompt="frozen input",
        contract_index=_contract_index(),
        limits=_limits(),
    )


def test_evaluator_runs_once_without_compiler_transcript_or_feedback() -> None:
    provider = _SequenceProvider(
        [
            _provider_response(
                tool_calls=[
                    _tool_call(
                        _candidate_evaluation(),
                        name="submit_evaluation_result",
                    )
                ],
                raw=b'{"evaluator":"raw"}',
            )
        ]
    )

    result = SUPPORT.run_evaluator_once(
        provider=provider,
        system_prompt="independent evaluator",
        user_prompt="source, context, terminal, trace, rubric",
        evaluated_result_kind="compiled_candidate",
        max_completion_tokens=4096,
        provider_timeout_s=120.0,
    )

    assert result.stop_reason == "valid_report"
    assert result.report == _candidate_evaluation()
    assert result.raw_provider_response == b'{"evaluator":"raw"}'
    assert len(provider.requests) == 1
    rendered = json.dumps(provider.requests[0])
    assert "compiler transcript" not in rendered.lower()
    assert provider.requests[0]["tools"][0]["function"]["name"] == (
        "submit_evaluation_result"
    )


def test_evaluator_invalid_output_is_not_repaired_or_retried() -> None:
    provider = _SequenceProvider(
        [
            _provider_response(
                tool_calls=[
                    _tool_call(
                        {"not": "a report"},
                        name="submit_evaluation_result",
                    )
                ]
            )
        ]
    )

    result = SUPPORT.run_evaluator_once(
        provider=provider,
        system_prompt="independent evaluator",
        user_prompt="frozen evidence",
        evaluated_result_kind="compiled_candidate",
        max_completion_tokens=4096,
        provider_timeout_s=120.0,
    )

    assert result.stop_reason == "invalid_report"
    assert result.report is None
    assert len(provider.requests) == 1


def test_evaluator_provider_failure_preserves_diagnostic_transport() -> None:
    provider = _SequenceProvider(
        [
            SUPPORT.ProviderCallFailure(
                failure_type="AuthenticationError",
                message="credential rejected",
                raw_request=b'{"evaluator":"request"}',
                raw_error=b'{"evaluator":"error"}',
            )
        ]
    )

    result = SUPPORT.run_evaluator_once(
        provider=provider,
        system_prompt="independent evaluator",
        user_prompt="frozen evidence",
        evaluated_result_kind="compiled_candidate",
        max_completion_tokens=4096,
        provider_timeout_s=120.0,
    )

    assert result.stop_reason == "provider_failure"
    assert result.control_evidence["message"] == "credential rejected"
    assert result.raw_provider_request == b'{"evaluator":"request"}'
    assert result.raw_provider_error == b'{"evaluator":"error"}'


def test_four_way_classification_requires_independent_acceptance() -> None:
    candidate_session = _terminal_session(_candidate())
    gap_session = _terminal_session(_insufficient())

    assert SUPPORT.classify_observation(
        candidate_session,
        SUPPORT.evaluator_result_from_report(_candidate_evaluation()),
    ).outcome == "bounded_lowering_demonstrated"
    assert SUPPORT.classify_observation(
        gap_session,
        SUPPORT.evaluator_result_from_report(_gap_evaluation()),
    ).outcome == "contract_gap_demonstrated"
    assert SUPPORT.classify_observation(
        candidate_session,
        SUPPORT.evaluator_result_from_report(_candidate_evaluation(accepted=False)),
    ).outcome == "candidate_failure"
    assert SUPPORT.classify_observation(
        candidate_session,
        SUPPORT.EvaluatorAttemptResult.control_failure("provider_failure"),
    ).outcome == "inconclusive"


def test_gap_requires_all_three_absence_necessity_and_latitude_findings() -> None:
    gap_session = _terminal_session(_insufficient())

    decision = SUPPORT.classify_observation(
        gap_session,
        SUPPORT.evaluator_result_from_report(_gap_evaluation(necessary=False)),
    )

    assert decision.outcome == "candidate_failure"
    assert "contract_gap_not_demonstrated" in decision.reason_codes


def test_evaluator_result_kind_mismatch_is_inconclusive_not_a_crash() -> None:
    candidate_session = _terminal_session(_candidate())

    decision = SUPPORT.classify_observation(
        candidate_session,
        SUPPORT.evaluator_result_from_report(_gap_evaluation()),
    )

    assert decision.outcome == "inconclusive"
    assert decision.reason_codes == ("evaluator_result_kind_mismatch",)


def test_invalid_full_source_is_candidate_failure_even_if_evaluator_accepts() -> None:
    value = _candidate()
    value["compiled_candidate"]["representation"]["source"] = "not valid C#"
    session = replace(
        _terminal_session(_candidate()),
        terminal_submission=value,
        terminal_validation=SUPPORT.validate_terminal_submission(
            value, _contract_index()
        ),
    )

    decision = SUPPORT.classify_observation(
        session,
        SUPPORT.evaluator_result_from_report(_candidate_evaluation()),
    )

    assert decision.outcome == "candidate_failure"
    assert decision.reason_codes == ("representation_contract_failed",)


def test_evaluator_acceptance_cannot_override_representation_contract_failure() -> None:
    value = _candidate()
    value["compiled_candidate"]["representation"]["source"] = (
        _preserved_first_candidate()
    )
    session = replace(
        _terminal_session(_candidate()),
        terminal_submission=value,
        terminal_validation=SUPPORT.validate_terminal_submission(
            value, _contract_index()
        ),
    )

    decision = SUPPORT.classify_observation(
        session,
        SUPPORT.evaluator_result_from_report(_candidate_evaluation()),
    )

    assert decision.outcome == "candidate_failure"
    assert decision.reason_codes == ("representation_contract_failed",)


@pytest.mark.parametrize(
    "validation_field,reason_code",
    [
        ("schema_valid", "terminal_schema_failed"),
        ("trace_valid", "trace_validation_failed"),
    ],
)
def test_evaluator_acceptance_cannot_override_terminal_validation_failure(
    validation_field: str,
    reason_code: str,
) -> None:
    session = _terminal_session(_candidate())
    assert session.terminal_validation is not None
    session = replace(
        session,
        terminal_validation=replace(
            session.terminal_validation,
            **{validation_field: False},
        ),
    )

    decision = SUPPORT.classify_observation(
        session,
        SUPPORT.evaluator_result_from_report(_candidate_evaluation()),
    )

    assert decision.outcome == "candidate_failure"
    assert decision.reason_codes == (reason_code,)


def test_no_terminal_result_is_inconclusive_without_evaluation() -> None:
    provider = _SequenceProvider([RuntimeError("offline")])
    session = SUPPORT.run_compiler_session(
        provider=provider,
        system_prompt="compiler system",
        user_prompt="frozen input",
        contract_index=_contract_index(),
        limits=_limits(),
    )

    decision = SUPPORT.classify_observation(session, None)

    assert decision.outcome == "inconclusive"
    assert decision.reason_codes == ("compiler_provider_failure",)
