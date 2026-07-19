from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_script(name: str):
    path = Path(__file__).resolve().parents[2] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SUPPORT = _load_script("lm9b_c_compiler_sufficiency_support")
ARTIFACTS = _load_script("lm9b_c_compiler_sufficiency_artifacts")
PROBE = _load_script("lm9b_c_compiler_sufficiency_probe")


def _fixture_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "lm9b_c_fixtures"


class _Provider:
    def __init__(self, response_factory) -> None:
        self.response_factory = response_factory
        self.requests: list[dict[str, object]] = []

    def __call__(self, request: dict[str, object]) -> object:
        self.requests.append(request)
        response = self.response_factory(request)
        if isinstance(response, BaseException):
            raise response
        return response


def _turn(arguments: dict[str, object], *, tool_name: str) -> object:
    argument_name = (
        "evaluation_json"
        if tool_name == "submit_evaluation_result"
        else "submission_json"
    )
    raw_request = b'{"logical":"provider-request"}'
    raw_response = b'{"logical":"provider-response"}'
    return SUPPORT.ProviderTurn(
        raw_request=raw_request,
        raw_response=raw_response,
        assistant_message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(
                            {argument_name: json.dumps(arguments)}
                        ),
                    },
                }
            ],
        },
        usage={"total_tokens": 100, "cost_usd": 0.01},
        provider_metadata={"provider": "fake", "model": "fake"},
    )


def _insufficient(inputs: object) -> dict[str, object]:
    return {
        "schema": SUPPORT.COMPILER_RESULT_SCHEMA_ID,
        "result_kind": "contract_insufficient",
        "recipe_fingerprint": inputs.contract_index["recipe_fingerprint"],
        "contract_insufficient": {
            "missing_decisions": [
                {
                    "missing_decision_id": "missing.some_decision",
                    "statement": "A required semantic decision is absent.",
                    "affected_clause_ids": [
                        inputs.contract_index["maintains_clause_ids"][0]
                    ],
                    "absent_authority": "No declared authority supplies the value.",
                    "why_delegation_is_insufficient": (
                        "The fixed representation cannot choose material meaning."
                    ),
                }
            ]
        },
    }


def _accepted_gap_evaluation() -> dict[str, object]:
    return {
        "schema": SUPPORT.EVALUATION_REPORT_SCHEMA_ID,
        "evaluated_result_kind": "contract_insufficient",
        "decision": "accepted",
        "contract_gap_assessment": {
            "missing_decision_precise": True,
            "absent_from_semantic_source": True,
            "necessary_for_conforming_lowering": True,
            "outside_delegated_latitude": True,
        },
        "issue_codes": [],
        "bounded_rationale": "The exact absence is necessary and not delegated.",
    }


def _mechanically_invalid_candidate(inputs: object) -> dict[str, object]:
    index = inputs.contract_index
    return {
        "schema": SUPPORT.COMPILER_RESULT_SCHEMA_ID,
        "result_kind": "compiled_candidate",
        "recipe_fingerprint": index["recipe_fingerprint"],
        "compiled_candidate": {
            "representation": {
                "kind": "csharp_script_instance",
                "pins_in": [],
                "pins_out": [
                    {"name": "Boxes", "type": "System.Object", "access": "list"}
                ],
                "source": (
                    "public class Script_Instance { "
                    "public void RunScript(out object Boxes) { Boxes = null; } }"
                ),
            },
            "decisions": [
                {
                    "decision_id": "decision.material",
                    "decision_kind": "material_semantic",
                    "statement": "Use one authorized semantic value.",
                    "maintains_clause_id": index["maintains_clause_ids"][0],
                    "support_refs": [index["support_ids"][0]],
                    "requires_or_invariant_clause_id": None,
                    "shape_delegation_id": None,
                    "capability_id": None,
                },
                {
                    "decision_id": "decision.implementation",
                    "decision_kind": "implementation",
                    "statement": "Use the fixed script representation.",
                    "maintains_clause_id": index["maintains_clause_ids"][0],
                    "support_refs": [],
                    "requires_or_invariant_clause_id": None,
                    "shape_delegation_id": index["shape_delegation_ids"][0],
                    "capability_id": index["capability_ids"][0],
                },
            ],
            "verification_plan": [
                {
                    "verification_id": f"verification.{position}",
                    "clause_id": clause_id,
                    "observation": "Observe the inert candidate output.",
                    "acceptance": "Compare the observation with the clause.",
                }
                for position, clause_id in enumerate(index["postcondition_clause_ids"])
            ],
            "unused_recipe_paths": [],
        },
    }


def test_cli_defaults_match_frozen_charter() -> None:
    args = PROBE._args(
        [
            "--compiler-model",
            "provider/compiler",
            "--evaluator-model",
            "provider/evaluator",
        ]
    )

    assert args.max_turns == 6
    assert args.max_completion_tokens == 16384
    assert args.provider_timeout_s == 180.0
    assert args.overall_deadline_s == 600.0
    assert args.token_stop_threshold == 120000
    assert args.cost_stop_threshold_usd == 10.0
    assert args.temperature == 0.0


def test_probe_runs_one_compiler_session_then_one_independent_evaluator(
    tmp_path: Path,
) -> None:
    inputs = ARTIFACTS.load_frozen_inputs(_fixture_dir())
    compiler = _Provider(
        lambda request: _turn(
            _insufficient(inputs),
            tool_name="submit_compiler_result",
        )
    )
    evaluator = _Provider(
        lambda request: _turn(
            _accepted_gap_evaluation(),
            tool_name="submit_evaluation_result",
        )
    )

    result = PROBE.run_probe(
        run_root=tmp_path,
        fixture_dir=_fixture_dir(),
        compiler_provider=compiler,
        evaluator_provider=evaluator,
        compiler_identity={"provider": "fake", "model": "compiler"},
        evaluator_identity={"provider": "fake", "model": "evaluator"},
        git_sha="deadbeef",
        now=lambda: datetime(2026, 7, 19, 12, 34, 56, tzinfo=timezone.utc),
    )

    assert result.decision.outcome == "contract_gap_demonstrated"
    assert len(compiler.requests) == 1
    assert len(evaluator.requests) == 1
    compiler_rendered = json.dumps(compiler.requests[0])
    evaluator_rendered = json.dumps(evaluator.requests[0])
    assert "evaluation_rubric" not in compiler_rendered
    assert "compiler transcript" not in evaluator_rendered.lower()
    assert (result.run_dir / "decision.json").exists()
    evaluator_summary = json.loads(
        (result.run_dir / "evaluator" / "summary.json").read_text("utf-8")
    )
    assert evaluator_summary["usage"] == {
        "cost_usd": 0.01,
        "total_tokens": 100,
    }
    assert evaluator_summary["provider_metadata"] == {
        "model": "fake",
        "provider": "fake",
    }
    assert isinstance(evaluator_summary["elapsed_s"], float)


def test_compiler_control_failure_skips_evaluator_and_still_writes_evidence(
    tmp_path: Path,
) -> None:
    compiler = _Provider(lambda request: RuntimeError("offline"))
    evaluator = _Provider(lambda request: AssertionError("must not run"))

    result = PROBE.run_probe(
        run_root=tmp_path,
        fixture_dir=_fixture_dir(),
        compiler_provider=compiler,
        evaluator_provider=evaluator,
        compiler_identity={"provider": "fake", "model": "compiler"},
        evaluator_identity={"provider": "fake", "model": "evaluator"},
        git_sha="deadbeef",
        now=lambda: datetime(2026, 7, 19, 12, 34, 56, tzinfo=timezone.utc),
    )

    assert result.decision.outcome == "inconclusive"
    assert len(evaluator.requests) == 0
    summary = json.loads(
        (result.run_dir / "evaluator" / "summary.json").read_text("utf-8")
    )
    assert summary["attempted"] is False
    control = json.loads(
        (result.run_dir / "compiler" / "control_failure.json").read_text("utf-8")
    )
    assert control == {"failure_type": "RuntimeError", "message": "offline"}


def test_mechanical_contract_failure_stays_in_session_and_skips_evaluator(
    tmp_path: Path,
) -> None:
    inputs = ARTIFACTS.load_frozen_inputs(_fixture_dir())
    compiler = _Provider(
        lambda request: _turn(
            _mechanically_invalid_candidate(inputs),
            tool_name="submit_compiler_result",
        )
    )
    evaluator = _Provider(lambda request: AssertionError("must not run"))

    result = PROBE.run_probe(
        run_root=tmp_path,
        fixture_dir=_fixture_dir(),
        compiler_provider=compiler,
        evaluator_provider=evaluator,
        compiler_identity={"provider": "fake", "model": "compiler"},
        evaluator_identity={"provider": "fake", "model": "evaluator"},
        git_sha="deadbeef",
        now=lambda: datetime(2026, 7, 19, 12, 34, 56, tzinfo=timezone.utc),
    )

    assert result.decision.outcome == "inconclusive"
    assert result.decision.reason_codes == ("compiler_max_turns_exhausted",)
    assert len(evaluator.requests) == 0
    assert result.compiler_session.turn_count == 6
    feedback = json.loads(
        (
            result.run_dir
            / "compiler"
            / "turns"
            / "turn-01"
            / "feedback.json"
        ).read_text("utf-8")
    )
    assert feedback["codes"] == [
        "missing_gh_script_instance_base",
        "runscript_signature_mismatch",
    ]
