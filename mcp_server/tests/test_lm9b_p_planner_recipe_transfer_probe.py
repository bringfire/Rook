from __future__ import annotations

import builtins
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "scripts" / "lm9b_p_fixtures"
READY_RECIPE = ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json"
BLOCKED_RECIPE = ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_blocked_recipe.json"
COMPILER_FIXTURES = ROOT / "scripts" / "lm9b_c_fixtures"
READY_RECIPE_BYTES = READY_RECIPE.read_bytes()


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


LM9B_C_SUPPORT = _load_script("lm9b_c_compiler_sufficiency_support")
LM9B_C_ARTIFACTS = _load_script("lm9b_c_compiler_sufficiency_artifacts")
LM9B_C_PROBE = _load_script("lm9b_c_compiler_sufficiency_probe")
SUPPORT = _load_script("lm9b_p_planner_recipe_transfer_support")
ARTIFACTS = _load_script("lm9b_p_planner_recipe_transfer_artifacts")
RCONTRACT = _load_script("lm9b_p_readiness_contract")
PROBE = _load_script("lm9b_p_planner_recipe_transfer_probe")


ARCHIVE_IDENTITY = {
    "git_commit_sha": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip(),
    "planner_model_identity": "planner-model-2026-07-20",
    "evaluator_model_identity": "evaluator-model-2026-07-20",
    "provider_profile_identity": "provider-profile-2026-07-20",
}
ARCHIVE_RECORD_PATHS = (
    "inputs/attempt_context.json",
    "inputs/radial_brief.txt",
    "inputs/task_envelope.json",
    "inputs/environment_snapshot.json",
    "inputs/planning_policy.json",
    "inputs/payload_schema_registry.json",
    "inputs/capability_registry.json",
    "inputs/semantic_authority_code_vocabulary.json",
    "inputs/semantic_capability_code_vocabulary.json",
    "inputs/worker_slot_code_vocabulary.json",
    "inputs/semantic_materiality_code_vocabulary.json",
    "inputs/semantic_value_schema_registry.json",
    "inputs/planner_recipe_probe_schema.json",
    "inputs/recipe_normalization_profile.json",
    "inputs/planner_authoring_contract.json",
    "inputs/planner_exclusion_policy.json",
    "inputs/planner_evaluation_rubric.json",
    "inputs/manifest.json",
    "planner/request.json",
    "planner/turns/000/raw_response.bin",
    "planner/turns/000/feedback.json",
    "planner/turns/000/usage.json",
    "planner/turns/000/timing.json",
    "planner/attempts/000/capture.json",
    "planner/attempts/000/provider_request.json",
    "planner/attempts/000/raw_request.bin",
    "planner/attempts/000/raw_response.bin",
    "planner/attempts/000/usage.json",
    "planner/attempts/000/tool_arguments/000.bin",
    "planner/final_recipe.json",
    "planner/final_recipe_identity.json",
    "evaluator/request.json",
    "evaluator/raw_response.bin",
    "evaluator/report.json",
    "evaluator/usage.json",
    "evaluator/timing.json",
    "evaluator/attempts/000/capture.json",
    "evaluator/attempts/000/provider_request.json",
    "evaluator/attempts/000/raw_request.bin",
    "evaluator/attempts/000/raw_response.bin",
    "evaluator/attempts/000/usage.json",
    "evaluator/attempts/000/tool_arguments/000.bin",
    "checkpoint/classification.json",
    "checkpoint/session.json",
    "identity.json",
    "checksums.json",
)


class _Provider:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    def __call__(self, request: dict[str, object]) -> object:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _planner_turn(recipe_path: Path) -> object:
    return _planner_turn_bytes(recipe_path.read_bytes())


def _planner_turn_bytes(recipe_bytes: bytes) -> object:
    return SUPPORT.ProviderTurn(
        raw_request=b'{"planner":"request"}',
        raw_response=b'{"planner":"response"}',
        assistant_message={
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "planner-call-1",
                    "function": {
                        "name": "submit_planner_recipe",
                        "arguments": json.dumps(
                            {
                                "recipe_json": recipe_bytes.decode("utf-8")
                            }
                        ),
                    },
                }
            ],
        },
        usage={},
        provider_metadata={
            "model_identity": "planner-model-2026-07-20",
            "profile_identity": "provider-profile-2026-07-20",
        },
    )


def _evaluator_turn(recommendation: str) -> object:
    return SUPPORT.ProviderTurn(
        raw_request=b'{"evaluator":"request"}',
        raw_response=b'{"evaluator":"response"}',
        assistant_message={
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "evaluator-call-1",
                    "function": {
                        "name": "submit_planner_evaluation",
                        "arguments": json.dumps(
                            {
                                "evaluation_json": json.dumps(
                                    {
                                        "recommendation": recommendation,
                                        "evidence": [
                                            {
                                                "criterion_id": "brief_fidelity",
                                                "finding": "Evidence is recorded.",
                                            }
                                        ],
                                    }
                                )
                            }
                        ),
                    },
                }
            ],
        },
        usage={},
        provider_metadata={
            "model_identity": "evaluator-model-2026-07-20",
            "profile_identity": "provider-profile-2026-07-20",
        },
    )


def _empty_planner_turn() -> object:
    return SUPPORT.ProviderTurn(
        raw_request=b'{"planner":"request"}',
        raw_response=b'{"planner":"response"}',
        assistant_message={"role": "assistant", "tool_calls": []},
        usage={},
        provider_metadata={
            "model_identity": "planner-model-2026-07-20",
            "profile_identity": "provider-profile-2026-07-20",
        },
    )


def _compiler_turn(submission: dict[str, object]) -> object:
    return LM9B_C_SUPPORT.ProviderTurn(
        raw_request=b'{"compiler":"request"}',
        raw_response=b'{"compiler":"response"}',
        assistant_message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "compiler-call-1",
                    "type": "function",
                    "function": {
                        "name": "submit_compiler_result",
                        "arguments": json.dumps(
                            {"submission_json": json.dumps(submission)}
                        ),
                    },
                }
            ],
        },
        usage={"total_tokens": 100, "cost_usd": 0.01},
        provider_metadata={"provider": "fake", "model": "compiler"},
    )


def _compiler_empty_turn(*, total_tokens: int) -> object:
    return LM9B_C_SUPPORT.ProviderTurn(
        raw_request=b'{"compiler":"request"}',
        raw_response=b'{"compiler":"response"}',
        assistant_message={"role": "assistant", "content": None, "tool_calls": []},
        usage={"total_tokens": total_tokens, "cost_usd": 0.01},
        provider_metadata={"provider": "fake", "model": "compiler"},
    )


def _compiler_evaluator_turn(report: dict[str, object]) -> object:
    return LM9B_C_SUPPORT.ProviderTurn(
        raw_request=b'{"compiler_evaluator":"request"}',
        raw_response=b'{"compiler_evaluator":"response"}',
        assistant_message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "compiler-evaluator-call-1",
                    "type": "function",
                    "function": {
                        "name": "submit_evaluation_result",
                        "arguments": json.dumps(
                            {"evaluation_json": json.dumps(report)}
                        ),
                    },
                }
            ],
        },
        usage={"total_tokens": 100, "cost_usd": 0.01},
        provider_metadata={"provider": "fake", "model": "evaluator"},
    )


def _contract_index() -> dict[str, object]:
    return LM9B_C_ARTIFACTS.derive_contract_index(
        json.loads(READY_RECIPE_BYTES)
    )


def _valid_compiler_candidate() -> dict[str, object]:
    index = _contract_index()
    return {
        "schema": LM9B_C_SUPPORT.COMPILER_RESULT_SCHEMA_ID,
        "result_kind": "compiled_candidate",
        "recipe_fingerprint": index["recipe_fingerprint"],
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
                {
                    "decision_id": "decision.guard",
                    "decision_kind": "guard_or_read",
                    "statement": "Read the governed document context.",
                    "maintains_clause_id": None,
                    "support_refs": [],
                    "requires_or_invariant_clause_id": index["requires_clause_ids"][0],
                    "shape_delegation_id": None,
                    "capability_id": None,
                },
            ],
            "verification_plan": [
                {
                    "verification_id": f"verification.{position}",
                    "clause_id": clause_id,
                    "observation": "Observe the inert candidate output.",
                    "acceptance": "Compare the observation with the clause.",
                }
                for position, clause_id in enumerate(
                    index["postcondition_clause_ids"]
                )
            ],
            "unused_recipe_paths": [],
        },
    }


def _contract_insufficient() -> dict[str, object]:
    index = _contract_index()
    return {
        "schema": LM9B_C_SUPPORT.COMPILER_RESULT_SCHEMA_ID,
        "result_kind": "contract_insufficient",
        "recipe_fingerprint": index["recipe_fingerprint"],
        "contract_insufficient": {
            "missing_decisions": [
                {
                    "missing_decision_id": "missing.some_decision",
                    "statement": "A required semantic decision is absent.",
                    "affected_clause_ids": [index["maintains_clause_ids"][0]],
                    "absent_authority": "No declared authority supplies the value.",
                    "why_delegation_is_insufficient": (
                        "The fixed representation cannot choose material meaning."
                    ),
                }
            ]
        },
    }


def _candidate_evaluation(*, accepted: bool = True) -> dict[str, object]:
    decision = "accepted" if accepted else "rejected"
    return {
        "schema": LM9B_C_SUPPORT.EVALUATION_REPORT_SCHEMA_ID,
        "evaluated_result_kind": "compiled_candidate",
        "decision": decision,
        "candidate_assessment": {
            "source_fidelity": decision,
            "material_authority": decision,
            "representation_coherence": decision,
            "verification_fidelity": decision,
        },
        "issue_codes": [] if accepted else ["material_invention"],
        "bounded_rationale": "The candidate is checked against the source.",
    }


def _gap_evaluation(*, accepted: bool = True) -> dict[str, object]:
    return {
        "schema": LM9B_C_SUPPORT.EVALUATION_REPORT_SCHEMA_ID,
        "evaluated_result_kind": "contract_insufficient",
        "decision": "accepted" if accepted else "rejected",
        "contract_gap_assessment": {
            "missing_decision_precise": True,
            "absent_from_semantic_source": True,
            "necessary_for_conforming_lowering": accepted,
            "outside_delegated_latitude": True,
        },
        "issue_codes": [] if accepted else ["gap_not_necessary"],
        "bounded_rationale": "The explicit gap is checked against the source.",
    }


def _turn_with_tool_calls(
    *,
    role: str,
    calls: list[object],
) -> object:
    return SUPPORT.ProviderTurn(
        raw_request=(f'{{"{role}":"request"}}').encode("utf-8"),
        raw_response=(f'{{"{role}":"response"}}').encode("utf-8"),
        assistant_message={"role": "assistant", "tool_calls": calls},
        usage={},
        provider_metadata={
            "model_identity": (
                "planner-model-2026-07-20"
                if role == "planner"
                else "evaluator-model-2026-07-20"
            ),
            "profile_identity": "provider-profile-2026-07-20",
        },
    )


def _recompute_checksums(archive_dir: Path) -> None:
    checksums_path = archive_dir / "checksums.json"
    checksums = json.loads(checksums_path.read_bytes())
    records = checksums["records"]
    checksums["aggregate_identity"] = ARTIFACTS.canonical_fingerprint(
        ARTIFACTS.own_trusted_json(
            {
                "schema": checksums["schema"],
                "records": records,
            }
        )
    )
    checksums_path.write_text(
        json.dumps(checksums, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


@pytest.mark.parametrize(
    ("recommendation", "classification"),
    [
        ("faithful_ready", "probe_candidate_ready"),
        ("planner_failure", "probe_planner_failure"),
    ],
)
def test_checkpoint_derives_the_only_public_classification(
    recommendation: str, classification: str
) -> None:
    planner = _Provider([_planner_turn(READY_RECIPE)])
    evaluator = _Provider([_evaluator_turn(recommendation)])
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=planner,
        evaluator_provider=evaluator,
    )
    assert result.classification == classification
    assert result.evaluator.recommendation == recommendation
    assert result.final_recipe_bytes == READY_RECIPE.read_bytes()
    assert result.checkpoint_2 == "not_evaluated"
    assert len(planner.requests) == 1
    assert len(evaluator.requests) == 1
    assert "probe_candidate" not in json.dumps(evaluator.requests[0])
    assert "planner-call-1" not in json.dumps(evaluator.requests[0])


def test_blocked_witness_never_enters_checkpoint_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planner = _Provider([_planner_turn(BLOCKED_RECIPE)])
    evaluator = _Provider([_evaluator_turn("faithful_blocked")])
    compiler_calls: list[object] = []

    def unexpected_handoff(*args, **kwargs):
        compiler_calls.append((args, kwargs))
        raise AssertionError("Checkpoint 1 must not build a compiler handoff")

    monkeypatch.setattr(PROBE.ARTIFACTS, "build_lm9bc_handoff", unexpected_handoff)
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=planner,
        evaluator_provider=evaluator,
    )
    assert result.classification == "probe_candidate_blocked"
    assert result.final_recipe_bytes == BLOCKED_RECIPE.read_bytes()
    assert result.checkpoint_2 == "not_evaluated"
    assert compiler_calls == []
    assert len(planner.requests) == 1
    assert len(evaluator.requests) == 1


def test_mechanical_rejection_skips_evaluation() -> None:
    planner = _Provider(
        [
            SUPPORT.ProviderTurn(
                raw_request=b'{"planner":"request"}',
                raw_response=b'{"planner":"response"}',
                assistant_message={"role": "assistant", "tool_calls": []},
                usage={},
                provider_metadata={},
            )
            for _ in range(SUPPORT.PLANNER_MAX_TURNS)
        ]
    )
    evaluator = _Provider([RuntimeError("must not be consumed")])
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=planner,
        evaluator_provider=evaluator,
    )
    assert result.classification == "probe_mechanically_rejected"
    assert result.evaluator is None
    assert result.final_recipe_bytes is None
    assert result.checkpoint_2 == "not_evaluated"
    assert evaluator.requests == []


@pytest.mark.parametrize(
    "evaluator_response",
    [
        RuntimeError("provider unavailable"),
        _evaluator_turn("probe_candidate_ready"),
    ],
)
def test_evaluator_failure_or_malformed_output_is_inconclusive_without_retry(
    evaluator_response: object,
) -> None:
    planner = _Provider([_planner_turn(READY_RECIPE)])
    evaluator = _Provider([evaluator_response, RuntimeError("must not be consumed")])
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=planner,
        evaluator_provider=evaluator,
    )
    assert result.classification == "probe_inconclusive"
    assert result.checkpoint_2 == "not_evaluated"
    assert len(evaluator.requests) == 1


@pytest.fixture
def sealed_checkpoint(tmp_path: Path):
    archive_dir = tmp_path / "checkpoint-1"
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
        evaluator_provider=_Provider([_evaluator_turn("faithful_ready")]),
        archive_destination=archive_dir,
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert result.sealed_archive is not None
    return result, archive_dir


def _run_joined(
    *,
    tmp_path: Path,
    checkpoint: object,
    compiler: _Provider,
    evaluator: _Provider,
) -> object:
    # Other test modules load these scripts under the same names during collection.
    sys.modules["lm9b_c_compiler_sufficiency_support"] = LM9B_C_SUPPORT
    sys.modules["lm9b_c_compiler_sufficiency_artifacts"] = LM9B_C_ARTIFACTS
    sys.modules["lm9b_c_compiler_sufficiency_probe"] = LM9B_C_PROBE
    return PROBE.run_joined_probe(
        checkpoint_1=checkpoint,
        compiler_fixture_dir=COMPILER_FIXTURES,
        handoff_destination=tmp_path / "handoff",
        compiler_run_root=tmp_path / "compiler-run",
        aggregate_destination=tmp_path / "aggregate",
        compiler_provider=compiler,
        compiler_evaluator_provider=evaluator,
        compiler_identity={"provider": "fake", "model": "compiler"},
        compiler_evaluator_identity={"provider": "fake", "model": "evaluator"},
        git_sha="deadbeef",
    )


@pytest.mark.parametrize(
    (
        "case",
        "expected_aggregate",
        "expected_compiler_calls",
        "expected_evaluator_calls",
    ),
    [
        ("bounded", "joined_transfer_demonstrated", 1, 1),
        ("explicit_gap", "contract_gap_demonstrated", 1, 1),
        ("malformed_candidate", "candidate_failure", LM9B_C_PROBE.MAX_TURNS, 0),
        ("csharp_preflight", "candidate_failure", LM9B_C_PROBE.MAX_TURNS, 0),
        ("evaluator_rejection", "candidate_failure", 1, 1),
    ],
)
def test_ready_checkpoint_derives_joined_attribution_matrix(
    tmp_path: Path,
    sealed_checkpoint,
    case: str,
    expected_aggregate: str,
    expected_compiler_calls: int,
    expected_evaluator_calls: int,
) -> None:
    checkpoint, _ = sealed_checkpoint
    candidate = _valid_compiler_candidate()
    if case == "bounded":
        compiler_responses = [_compiler_turn(candidate)]
        evaluator_responses = [
            _compiler_evaluator_turn(_candidate_evaluation())
        ]
    elif case == "explicit_gap":
        compiler_responses = [_compiler_turn(_contract_insufficient())]
        evaluator_responses = [_compiler_evaluator_turn(_gap_evaluation())]
    elif case == "malformed_candidate":
        candidate.pop("schema")
        compiler_responses = [
            _compiler_turn(candidate) for _ in range(LM9B_C_PROBE.MAX_TURNS)
        ]
        evaluator_responses = [AssertionError("evaluator must not run")]
    elif case == "csharp_preflight":
        candidate["compiled_candidate"]["representation"]["source"] = "not valid C#"
        compiler_responses = [
            _compiler_turn(candidate) for _ in range(LM9B_C_PROBE.MAX_TURNS)
        ]
        evaluator_responses = [AssertionError("evaluator must not run")]
    else:
        compiler_responses = [_compiler_turn(candidate)]
        evaluator_responses = [
            _compiler_evaluator_turn(_candidate_evaluation(accepted=False))
        ]
    compiler = _Provider(compiler_responses)
    evaluator = _Provider(evaluator_responses)

    result = _run_joined(
        tmp_path=tmp_path,
        checkpoint=checkpoint,
        compiler=compiler,
        evaluator=evaluator,
    )

    assert result.checkpoint_1.classification == "probe_candidate_ready"
    assert result.aggregate_outcome == expected_aggregate
    assert len(compiler.requests) == expected_compiler_calls
    assert len(evaluator.requests) == expected_evaluator_calls
    assert result.sealed_aggregate is not None
    aggregate = json.loads(
        (result.sealed_aggregate.archive_dir / "aggregate.json").read_bytes()
    )
    assert aggregate["aggregate_outcome"] == expected_aggregate
    assert aggregate["checkpoint_1"]["aggregate_identity"] == (
        checkpoint.sealed_archive.aggregate_identity
    )
    assert aggregate["lm9b_c_archive"]["aggregate_identity"].startswith("sha256:")


@pytest.mark.parametrize(
    ("control", "response"),
    [
        ("provider", RuntimeError("provider unavailable")),
        ("timeout", TimeoutError("provider timed out")),
        (
            "budget",
            _compiler_empty_turn(
                total_tokens=LM9B_C_PROBE.TOKEN_STOP_THRESHOLD
            ),
        ),
    ],
)
def test_compiler_control_failures_are_inconclusive_without_evaluator(
    tmp_path: Path,
    sealed_checkpoint,
    control: str,
    response: object,
) -> None:
    checkpoint, _ = sealed_checkpoint
    compiler = _Provider([response])
    evaluator = _Provider([AssertionError("evaluator must not run")])

    result = _run_joined(
        tmp_path=tmp_path,
        checkpoint=checkpoint,
        compiler=compiler,
        evaluator=evaluator,
    )

    assert result.checkpoint_2 == "inconclusive", control
    assert result.aggregate_outcome == "inconclusive"
    assert len(compiler.requests) == 1
    assert evaluator.requests == []
    assert result.lm9bc_result is not None


@pytest.mark.parametrize(
    ("control", "response"),
    [
        ("provider", RuntimeError("evaluator unavailable")),
        ("timeout", TimeoutError("evaluator timed out")),
        ("protocol", object()),
        (
            "malformed_report",
            LM9B_C_SUPPORT.ProviderTurn(
                raw_request=b'{"compiler_evaluator":"request"}',
                raw_response=b'{"compiler_evaluator":"malformed"}',
                assistant_message={"role": "assistant", "tool_calls": []},
                usage={"total_tokens": 11},
                provider_metadata={"provider": "fake", "model": "evaluator"},
            ),
        ),
    ],
)
def test_compiler_evaluator_control_failures_remain_inconclusive(
    tmp_path: Path,
    sealed_checkpoint,
    control: str,
    response: object,
) -> None:
    checkpoint, _ = sealed_checkpoint
    compiler = _Provider([_compiler_turn(_valid_compiler_candidate())])
    evaluator = _Provider([response, AssertionError("evaluator retried")])

    result = _run_joined(
        tmp_path=tmp_path,
        checkpoint=checkpoint,
        compiler=compiler,
        evaluator=evaluator,
    )

    assert result.checkpoint_2 == "inconclusive", control
    assert result.aggregate_outcome == "inconclusive"
    assert len(compiler.requests) == 1
    assert len(evaluator.requests) == 1
    assert result.lm9bc_result is not None
    assert result.sealed_aggregate is not None


def test_join_does_not_reparse_verified_checkpoint_recipe_bytes(
    tmp_path: Path,
    sealed_checkpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint, _ = sealed_checkpoint
    recipe_bytes = checkpoint.final_recipe_bytes
    assert type(recipe_bytes) is bytes
    artifact_parse_calls = 0
    support_parse_calls = 0
    gate_calls = 0
    original_artifact_parse = ARTIFACTS.parse_strict_json
    original_support_parse = SUPPORT.parse_strict_json

    def observed_artifact_parse(raw: bytes):
        nonlocal artifact_parse_calls
        if raw == recipe_bytes:
            artifact_parse_calls += 1
        return original_artifact_parse(raw)

    def observed_support_parse(raw: bytes):
        nonlocal support_parse_calls
        if raw == recipe_bytes:
            support_parse_calls += 1
        return original_support_parse(raw)

    def observed_gate(**kwargs):
        nonlocal gate_calls
        gate_calls += 1
        raise AssertionError("the join adapter recomputed the mechanical gate")

    monkeypatch.setattr(ARTIFACTS, "parse_strict_json", observed_artifact_parse)
    monkeypatch.setattr(SUPPORT, "parse_strict_json", observed_support_parse)
    monkeypatch.setattr(ARTIFACTS, "evaluate_mechanical_gate", observed_gate)
    result = _run_joined(
        tmp_path=tmp_path,
        checkpoint=checkpoint,
        compiler=_Provider([RuntimeError("compiler unavailable")]),
        evaluator=_Provider([AssertionError("evaluator must not run")]),
    )

    assert result.checkpoint_2 == "inconclusive"
    assert artifact_parse_calls == 0
    assert support_parse_calls == 0
    assert gate_calls == 0


@pytest.mark.parametrize(
    ("compiler_response", "evaluator_response", "expected_evaluator_calls"),
    [
        (
            _compiler_turn(_valid_compiler_candidate()),
            _compiler_evaluator_turn(_candidate_evaluation()),
            1,
        ),
        (RuntimeError("compiler unavailable"), AssertionError("must not run"), 0),
    ],
)
def test_post_contact_lm9bc_evidence_failure_has_no_aggregate_or_retry(
    tmp_path: Path,
    sealed_checkpoint,
    monkeypatch: pytest.MonkeyPatch,
    compiler_response: object,
    evaluator_response: object,
    expected_evaluator_calls: int,
) -> None:
    checkpoint, _ = sealed_checkpoint
    compiler = _Provider([compiler_response, AssertionError("compiler retried")])
    evaluator = _Provider([evaluator_response, AssertionError("evaluator retried")])
    monkeypatch.setattr(
        LM9B_C_PROBE,
        "write_probe_evidence",
        lambda **kwargs: (_ for _ in ()).throw(OSError("evidence unavailable")),
    )

    result = _run_joined(
        tmp_path=tmp_path,
        checkpoint=checkpoint,
        compiler=compiler,
        evaluator=evaluator,
    )

    assert result.checkpoint_2 == "inconclusive"
    assert result.aggregate_outcome == "inconclusive"
    assert result.sealed_aggregate is None
    assert not (tmp_path / "aggregate").exists()
    assert len(compiler.requests) == 1
    assert len(evaluator.requests) == expected_evaluator_calls
    assert len(result.compiler_provider_attempts) == 1
    assert result.compiler_provider_attempts[0].provider_request_bytes
    if expected_evaluator_calls:
        assert len(result.compiler_evaluator_provider_attempts) == 1
        turn = result.compiler_evaluator_provider_attempts[0].provider_turn
        assert turn.raw_response == b'{"compiler_evaluator":"response"}'
    else:
        assert result.compiler_evaluator_provider_attempts == ()
        assert result.compiler_provider_attempts[0].raw_request is None
        assert result.compiler_provider_attempts[0].raw_error is None
    assert result.control_failure["locus"] == "lm9b_c_session_or_evidence"


def test_provider_failure_evidence_survives_post_contact_archive_failure(
    tmp_path: Path,
    sealed_checkpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint, _ = sealed_checkpoint
    raw_request = b'{"transport":"sanitized request"}'
    raw_error = b'{"transport":"sanitized error"}'
    failure = LM9B_C_SUPPORT.ProviderCallFailure(
        failure_type="BadRequestError",
        message="provider rejected request",
        raw_request=raw_request,
        raw_error=raw_error,
    )
    compiler = _Provider([failure, AssertionError("compiler retried")])
    evaluator = _Provider([AssertionError("evaluator must not run")])
    monkeypatch.setattr(
        LM9B_C_PROBE,
        "write_probe_evidence",
        lambda **kwargs: (_ for _ in ()).throw(OSError("evidence unavailable")),
    )

    result = _run_joined(
        tmp_path=tmp_path,
        checkpoint=checkpoint,
        compiler=compiler,
        evaluator=evaluator,
    )

    assert result.checkpoint_2 == "inconclusive"
    assert result.aggregate_outcome == "inconclusive"
    assert result.sealed_aggregate is None
    assert not (tmp_path / "aggregate").exists()
    assert len(compiler.requests) == 1
    assert evaluator.requests == []
    assert len(result.compiler_provider_attempts) == 1
    attempt = result.compiler_provider_attempts[0]
    assert attempt.outcome == "raised"
    assert attempt.raw_request == raw_request
    assert attempt.raw_error == raw_error
    assert result.compiler_evaluator_provider_attempts == ()
    assert result.control_failure["locus"] == "lm9b_c_session_or_evidence"


@pytest.mark.parametrize("failure_locus", ["load_or_index", "render"])
def test_pre_session_failure_is_inconclusive_without_compiler_contact(
    tmp_path: Path,
    sealed_checkpoint,
    monkeypatch: pytest.MonkeyPatch,
    failure_locus: str,
) -> None:
    checkpoint, _ = sealed_checkpoint
    compiler = _Provider([AssertionError("compiler must not run")])
    evaluator = _Provider([AssertionError("evaluator must not run")])
    if failure_locus == "load_or_index":
        monkeypatch.setattr(
            LM9B_C_ARTIFACTS,
            "load_frozen_inputs",
            lambda fixture_dir: (_ for _ in ()).throw(ValueError("bad manifest")),
        )
    else:
        monkeypatch.setattr(
            LM9B_C_ARTIFACTS,
            "render_compiler_request",
            lambda inputs: (_ for _ in ()).throw(ValueError("bad projection")),
        )

    result = _run_joined(
        tmp_path=tmp_path,
        checkpoint=checkpoint,
        compiler=compiler,
        evaluator=evaluator,
    )

    assert result.checkpoint_2 == "inconclusive"
    assert result.aggregate_outcome == "inconclusive"
    assert result.pre_session_failure["locus"] == failure_locus
    assert compiler.requests == []
    assert evaluator.requests == []
    assert result.lm9bc_result is None
    aggregate = json.loads(
        (result.sealed_aggregate.archive_dir / "aggregate.json").read_bytes()
    )
    assert aggregate["pre_session_failure"]["locus"] == failure_locus
    assert aggregate["lm9b_c_archive"] is None


def test_handoff_construction_failure_is_inconclusive_without_compiler_contact(
    tmp_path: Path,
    sealed_checkpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint, _ = sealed_checkpoint
    compiler = _Provider([AssertionError("compiler must not run")])
    evaluator = _Provider([AssertionError("evaluator must not run")])
    monkeypatch.setattr(
        PROBE.ARTIFACTS,
        "build_lm9bc_handoff",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("bad handoff manifest")),
    )

    result = _run_joined(
        tmp_path=tmp_path,
        checkpoint=checkpoint,
        compiler=compiler,
        evaluator=evaluator,
    )

    assert result.checkpoint_2 == "inconclusive"
    assert result.aggregate_outcome == "inconclusive"
    assert result.pre_session_failure["locus"] == "handoff"
    assert result.handoff is None
    assert result.lm9bc_result is None
    assert compiler.requests == []
    assert evaluator.requests == []


@pytest.mark.parametrize(
    ("planner_responses", "evaluator_responses", "classification"),
    [
        (
            [_planner_turn(BLOCKED_RECIPE)],
            [_evaluator_turn("faithful_blocked")],
            "probe_candidate_blocked",
        ),
        (
            [_planner_turn(READY_RECIPE)],
            [_evaluator_turn("planner_failure")],
            "probe_planner_failure",
        ),
        (
            [_planner_turn(READY_RECIPE)],
            [RuntimeError("evaluator unavailable")],
            "probe_inconclusive",
        ),
        (
            [_empty_planner_turn() for _ in range(SUPPORT.PLANNER_MAX_TURNS)],
            [AssertionError("evaluator must not run")],
            "probe_mechanically_rejected",
        ),
    ],
)
def test_every_non_ready_checkpoint_skips_handoff_and_compiler(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    planner_responses: list[object],
    evaluator_responses: list[object],
    classification: str,
) -> None:
    checkpoint = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider(planner_responses),
        evaluator_provider=_Provider(evaluator_responses),
        archive_destination=tmp_path / "checkpoint-1",
        archive_identity=ARCHIVE_IDENTITY,
    )
    handoff_calls: list[object] = []

    def unexpected_handoff(*args, **kwargs):
        handoff_calls.append((args, kwargs))
        raise AssertionError("non-ready checkpoint reached handoff")

    monkeypatch.setattr(PROBE.ARTIFACTS, "build_lm9bc_handoff", unexpected_handoff)
    compiler = _Provider([AssertionError("compiler must not run")])
    evaluator = _Provider([AssertionError("compiler evaluator must not run")])

    result = _run_joined(
        tmp_path=tmp_path,
        checkpoint=checkpoint,
        compiler=compiler,
        evaluator=evaluator,
    )

    assert result.checkpoint_1.classification == classification
    assert result.checkpoint_2 == "not_evaluated"
    assert result.aggregate_outcome == classification
    assert handoff_calls == []
    assert compiler.requests == []
    assert evaluator.requests == []


def test_join_verifies_retained_checkpoint_aggregate_before_handoff(
    tmp_path: Path,
    sealed_checkpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint, archive_dir = sealed_checkpoint
    (archive_dir / "checkpoint" / "classification.json").write_bytes(b"{}\n")
    handoff_calls: list[object] = []
    monkeypatch.setattr(
        PROBE.ARTIFACTS,
        "build_lm9bc_handoff",
        lambda *args, **kwargs: handoff_calls.append((args, kwargs)),
    )

    with pytest.raises(ValueError, match="sealed checkpoint archive"):
        _run_joined(
            tmp_path=tmp_path,
            checkpoint=checkpoint,
            compiler=_Provider([AssertionError("compiler must not run")]),
            evaluator=_Provider([AssertionError("evaluator must not run")]),
        )
    assert handoff_calls == []


def test_joined_aggregate_proves_all_recipe_byte_boundaries(
    tmp_path: Path,
    sealed_checkpoint,
) -> None:
    checkpoint, _ = sealed_checkpoint
    result = _run_joined(
        tmp_path=tmp_path,
        checkpoint=checkpoint,
        compiler=_Provider([RuntimeError("bounded stop")]),
        evaluator=_Provider([AssertionError("evaluator must not run")]),
    )

    aggregate = json.loads(
        (result.sealed_aggregate.archive_dir / "aggregate.json").read_bytes()
    )
    proof = aggregate["recipe_byte_equality"]
    expected = SUPPORT.sha256_prefixed(checkpoint.final_recipe_bytes)
    assert proof == {
        "planner_final_raw_sha256": expected,
        "handoff_archive_raw_sha256": expected,
        "lm9b_c_loaded_raw_sha256": expected,
        "lm9b_c_evidence_raw_sha256": expected,
        "all_equal": True,
    }
    assert checkpoint.final_recipe_bytes == result.handoff.archived_recipe_bytes
    assert checkpoint.final_recipe_bytes == result.lm9bc_result.inputs.recipe_bytes
    assert checkpoint.final_recipe_bytes == (
        result.lm9bc_result.run_dir / "inputs" / "recipe.json"
    ).read_bytes()


def test_checkpoint_archive_is_complete_atomic_and_byte_derived(
    sealed_checkpoint,
) -> None:
    result, archive_dir = sealed_checkpoint
    sealed = ARTIFACTS.verify_sealed_planner_checkpoint_archive(
        archive_dir,
        expected_aggregate_identity=result.sealed_archive.aggregate_identity,
    )
    assert result.sealed_archive.aggregate_identity == sealed.aggregate_identity
    assert sorted(
        path.relative_to(archive_dir).as_posix()
        for path in archive_dir.rglob("*")
        if path.is_file()
    ) == sorted(ARCHIVE_RECORD_PATHS)
    assert not list(archive_dir.parent.glob(f".{archive_dir.name}.tmp-*"))
    identity = json.loads((archive_dir / "identity.json").read_bytes())
    assert identity == {
        "schema": "rook.lm9b_p.checkpoint_identity:v1",
        "git_commit_sha": ARCHIVE_IDENTITY["git_commit_sha"],
        "planner_model_identity": "planner-model-2026-07-20",
        "evaluator_model_identity": "evaluator-model-2026-07-20",
        "provider_profile_identity": "provider-profile-2026-07-20",
        "normalization_profile_identity": {
            "profile_id": "lm9b_p.recipe_normalization_profile:v1",
            "profile_fingerprint": "sha256:5b8833bd1f2554c1d91fb8f04aa71a8e7509d850ccca28036096ea24f1ac000e",
        },
        "bounds": {
            "planner_max_turns": SUPPORT.PLANNER_MAX_TURNS,
            "evaluator_max_attempts": 1,
        },
        "execution_permitted": False,
    }
    assert json.loads(
        (archive_dir / "planner/attempts/000/capture.json").read_bytes()
    )["provider_metadata"] == {
        "model_identity": "planner-model-2026-07-20",
        "profile_identity": "provider-profile-2026-07-20",
    }
    assert json.loads(
        (archive_dir / "evaluator/attempts/000/capture.json").read_bytes()
    )["provider_metadata"] == {
        "model_identity": "evaluator-model-2026-07-20",
        "profile_identity": "provider-profile-2026-07-20",
    }
    classification = json.loads(
        (archive_dir / "checkpoint/classification.json").read_bytes()
    )
    assert classification == {
        "schema": "rook.lm9b_p.checkpoint_classification:v1",
        "classification": "probe_candidate_ready",
        "checkpoint_2": "not_evaluated",
    }


@pytest.mark.parametrize("relative_path", ARCHIVE_RECORD_PATHS)
def test_checkpoint_archive_rejects_deletion_of_every_required_record(
    sealed_checkpoint, tmp_path: Path, relative_path: str
) -> None:
    sealed_result, archive_dir = sealed_checkpoint
    damaged = tmp_path / "deleted"
    shutil.copytree(archive_dir, damaged)
    (damaged / relative_path).unlink()
    with pytest.raises(ValueError, match="sealed checkpoint archive"):
        ARTIFACTS.verify_sealed_planner_checkpoint_archive(
            damaged,
            expected_aggregate_identity=sealed_result.sealed_archive.aggregate_identity,
        )


@pytest.mark.parametrize("relative_path", ARCHIVE_RECORD_PATHS)
def test_checkpoint_archive_rejects_mutation_of_every_required_record(
    sealed_checkpoint, tmp_path: Path, relative_path: str
) -> None:
    sealed_result, archive_dir = sealed_checkpoint
    damaged = tmp_path / "mutated"
    shutil.copytree(archive_dir, damaged)
    target = damaged / relative_path
    target.write_bytes(b"{}" if target.name == "checksums.json" else target.read_bytes() + b"!")
    with pytest.raises(ValueError, match="sealed checkpoint archive"):
        ARTIFACTS.verify_sealed_planner_checkpoint_archive(
            damaged,
            expected_aggregate_identity=sealed_result.sealed_archive.aggregate_identity,
        )


def test_checkpoint_archive_rejects_reduced_records_even_after_recomputed_checksums(
    sealed_checkpoint, tmp_path: Path
) -> None:
    sealed_result, archive_dir = sealed_checkpoint
    damaged = tmp_path / "reduced"
    shutil.copytree(archive_dir, damaged)
    removed = "planner/final_recipe_identity.json"
    (damaged / removed).unlink()
    checksums_path = damaged / "checksums.json"
    checksums = json.loads(checksums_path.read_bytes())
    checksums["records"] = [
        record for record in checksums["records"] if record["path"] != removed
    ]
    checksums_path.write_text(json.dumps(checksums), encoding="utf-8")
    _recompute_checksums(damaged)
    with pytest.raises(ValueError, match="sealed checkpoint archive"):
        ARTIFACTS.verify_sealed_planner_checkpoint_archive(
            damaged,
            expected_aggregate_identity=sealed_result.sealed_archive.aggregate_identity,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("planner_model_identity", "different-planner-model"),
        ("evaluator_model_identity", "different-evaluator-model"),
        ("provider_profile_identity", "different-profile"),
    ],
)
def test_checkpoint_archive_metadata_mismatch_is_post_contact_inconclusive(
    field: str, value: str, tmp_path: Path,
) -> None:
    identity = dict(ARCHIVE_IDENTITY)
    identity[field] = value
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
        evaluator_provider=_Provider([_evaluator_turn("faithful_ready")]),
        archive_destination=tmp_path / "checkpoint-1",
        archive_identity=identity,
    )
    assert result.classification == "probe_inconclusive"
    assert result.sealed_archive is None
    assert result.control_failure["locus"] == "checkpoint_1_seal"
    assert "provider identity" in result.control_failure["message"]


def test_checkpoint_archive_rejects_coordinated_attempt_count_and_index_reduction(
    tmp_path: Path,
) -> None:
    archive_dir = tmp_path / "checkpoint-1"
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider(
            [_empty_planner_turn() for _ in range(SUPPORT.PLANNER_MAX_TURNS)]
        ),
        evaluator_provider=_Provider([RuntimeError("must not be consumed")]),
        archive_destination=archive_dir,
        archive_identity=ARCHIVE_IDENTITY,
    )
    damaged = tmp_path / "reduced"
    shutil.copytree(archive_dir, damaged)
    for index in range(2, SUPPORT.PLANNER_MAX_TURNS):
        shutil.rmtree(damaged / "planner" / "attempts" / f"{index:03d}")
        shutil.rmtree(damaged / "planner" / "turns" / f"{index:03d}")
    session_path = damaged / "checkpoint/session.json"
    session = json.loads(session_path.read_bytes())
    session["planner"]["attempt_count"] = 2
    session["planner"]["turn_count"] = 2
    session_path.write_text(json.dumps(session), encoding="utf-8")
    checksums_path = damaged / "checksums.json"
    checksums = json.loads(checksums_path.read_bytes())
    checksums["records"] = [
        record
        for record in checksums["records"]
        if not any(
            record["path"].startswith(f"planner/{kind}/{index:03d}/")
            for kind in ("attempts", "turns")
            for index in range(2, SUPPORT.PLANNER_MAX_TURNS)
        )
    ]
    for record in checksums["records"]:
        path = damaged / record["path"]
        raw = path.read_bytes()
        record["raw_sha256"] = SUPPORT.sha256_prefixed(raw)
        record["byte_length"] = len(raw)
    checksums_path.write_text(json.dumps(checksums), encoding="utf-8")
    _recompute_checksums(damaged)
    with pytest.raises(ValueError, match="retained seal"):
        ARTIFACTS.verify_sealed_planner_checkpoint_archive(
            damaged,
            expected_aggregate_identity=result.sealed_archive.aggregate_identity,
        )


def test_checkpoint_archive_preserves_every_planner_tool_argument(
    tmp_path: Path,
) -> None:
    first = '{"recipe_json":"{}"}'
    second = '{"malformed":true}'
    planner = _turn_with_tool_calls(
        role="planner",
        calls=[
            {
                "id": "planner-call-1",
                "function": {"name": "submit_planner_recipe", "arguments": first},
            },
            {
                "id": "planner-call-2",
                "function": {"name": "unexpected", "arguments": second},
            },
        ],
    )
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([planner]),
        evaluator_provider=_Provider([RuntimeError("must not be consumed")]),
        archive_destination=tmp_path / "checkpoint-1",
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert result.classification == "probe_inconclusive"
    assert (tmp_path / "checkpoint-1/planner/attempts/000/tool_arguments/000.bin").read_bytes() == first.encode("utf-8")
    assert (tmp_path / "checkpoint-1/planner/attempts/000/tool_arguments/001.bin").read_bytes() == second.encode("utf-8")


def test_checkpoint_archive_preserves_every_evaluator_tool_argument(
    tmp_path: Path,
) -> None:
    first = '{"evaluation_json":"{}"}'
    second = '{"extra":true}'
    evaluator = _turn_with_tool_calls(
        role="evaluator",
        calls=[
            {
                "id": "evaluator-call-1",
                "function": {
                    "name": "submit_planner_evaluation",
                    "arguments": first,
                },
            },
            {
                "id": "evaluator-call-2",
                "function": {"name": "unexpected", "arguments": second},
            },
        ],
    )
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
        evaluator_provider=_Provider([evaluator]),
        archive_destination=tmp_path / "checkpoint-1",
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert result.classification == "probe_inconclusive"
    assert (tmp_path / "checkpoint-1/evaluator/attempts/000/tool_arguments/000.bin").read_bytes() == first.encode("utf-8")
    assert (tmp_path / "checkpoint-1/evaluator/attempts/000/tool_arguments/001.bin").read_bytes() == second.encode("utf-8")


def test_checkpoint_archive_preserves_argument_after_a_malformed_tool_call(
    tmp_path: Path,
) -> None:
    argument = '{"evaluation_json":"{}"}'
    evaluator = _turn_with_tool_calls(
        role="evaluator",
        calls=[
            {"id": "malformed", "function": []},
            {
                "id": "evaluator-call-2",
                "function": {
                    "name": "submit_planner_evaluation",
                    "arguments": argument,
                },
            },
        ],
    )
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
        evaluator_provider=_Provider([evaluator]),
        archive_destination=tmp_path / "checkpoint-1",
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert result.classification == "probe_inconclusive"
    assert (tmp_path / "checkpoint-1/evaluator/attempts/000/tool_arguments/001.bin").read_bytes() == argument.encode("utf-8")
    assert ARTIFACTS.verify_sealed_planner_checkpoint_archive(
        tmp_path / "checkpoint-1",
        expected_aggregate_identity=result.sealed_archive.aggregate_identity,
    )


@pytest.mark.parametrize("failure", [RuntimeError("provider unavailable"), TimeoutError("provider timeout")])
def test_evaluator_failure_paths_still_seal_complete_inconclusive_evidence(
    failure: BaseException, tmp_path: Path
) -> None:
    archive_dir = tmp_path / "checkpoint-1"
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
        evaluator_provider=_Provider([failure]),
        archive_destination=archive_dir,
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert result.classification == "probe_inconclusive"
    assert result.sealed_archive is not None
    capture = json.loads(
        (archive_dir / "evaluator/attempts/000/capture.json").read_bytes()
    )
    assert capture["outcome"] == "raised"
    assert capture["exception_type"] == type(failure).__name__
    assert capture["provider_metadata"] is None
    assert ARTIFACTS.verify_sealed_planner_checkpoint_archive(
        archive_dir,
        expected_aggregate_identity=result.sealed_archive.aggregate_identity,
    )


def test_provider_call_failure_archive_round_trips_transport_evidence(
    tmp_path: Path,
) -> None:
    raw_request = b'{"sanitized":"request"}'
    raw_error = b'{"sanitized":"provider error"}'
    failure = LM9B_C_SUPPORT.ProviderCallFailure(
        failure_type="BadRequestError",
        message="provider rejected request",
        raw_request=raw_request,
        raw_error=raw_error,
    )
    archive_dir = tmp_path / "checkpoint-1"
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([failure]),
        evaluator_provider=_Provider([AssertionError("evaluator must not run")]),
        archive_destination=archive_dir,
        archive_identity=ARCHIVE_IDENTITY,
    )

    assert result.classification == "probe_inconclusive"
    assert result.sealed_archive is not None
    capture = json.loads(
        (archive_dir / "planner/attempts/000/capture.json").read_bytes()
    )
    assert capture["outcome"] == "raised"
    assert capture["exception_type"] == "ProviderCallFailure"
    assert capture["failure_type"] == "BadRequestError"
    assert capture["has_raw_request"] is True
    assert capture["has_raw_error"] is True
    assert capture["has_raw_response"] is False
    assert (archive_dir / "planner/attempts/000/raw_request.bin").read_bytes() == raw_request
    assert (archive_dir / "planner/attempts/000/raw_error.bin").read_bytes() == raw_error
    assert ARTIFACTS.verify_sealed_planner_checkpoint_archive(
        archive_dir,
        expected_aggregate_identity=result.sealed_archive.aggregate_identity,
    )


def test_evaluator_provider_call_failure_archive_round_trips_transport_evidence(
    tmp_path: Path,
) -> None:
    raw_request = b'{"sanitized":"evaluator request"}'
    raw_error = b'{"sanitized":"evaluator error"}'
    failure = LM9B_C_SUPPORT.ProviderCallFailure(
        failure_type="TimeoutError",
        message="evaluator timed out",
        raw_request=raw_request,
        raw_error=raw_error,
    )
    archive_dir = tmp_path / "checkpoint-1"
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
        evaluator_provider=_Provider([failure]),
        archive_destination=archive_dir,
        archive_identity=ARCHIVE_IDENTITY,
    )

    assert result.classification == "probe_inconclusive"
    assert result.sealed_archive is not None
    capture = json.loads(
        (archive_dir / "evaluator/attempts/000/capture.json").read_bytes()
    )
    assert capture["failure_type"] == "TimeoutError"
    assert (archive_dir / "evaluator/attempts/000/raw_request.bin").read_bytes() == raw_request
    assert (archive_dir / "evaluator/attempts/000/raw_error.bin").read_bytes() == raw_error
    assert ARTIFACTS.verify_sealed_planner_checkpoint_archive(
        archive_dir,
        expected_aggregate_identity=result.sealed_archive.aggregate_identity,
    )


def test_generic_provider_exception_archive_does_not_invent_transport_bytes(
    tmp_path: Path,
) -> None:
    archive_dir = tmp_path / "checkpoint-1"
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([RuntimeError("offline")]),
        evaluator_provider=_Provider([AssertionError("evaluator must not run")]),
        archive_destination=archive_dir,
        archive_identity=ARCHIVE_IDENTITY,
    )

    assert result.sealed_archive is not None
    capture = json.loads(
        (archive_dir / "planner/attempts/000/capture.json").read_bytes()
    )
    assert capture["failure_type"] is None
    assert capture["has_raw_request"] is False
    assert capture["has_raw_error"] is False
    assert not (archive_dir / "planner/attempts/000/raw_request.bin").exists()
    assert not (archive_dir / "planner/attempts/000/raw_error.bin").exists()


@pytest.mark.parametrize("contact_stage", ["planner", "evaluator"])
def test_checkpoint_seal_failure_after_contact_is_in_memory_inconclusive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contact_stage: str,
) -> None:
    planner = _Provider(
        [
            RuntimeError("planner unavailable")
            if contact_stage == "planner"
            else _planner_turn_bytes(READY_RECIPE_BYTES)
        ]
    )
    evaluator = _Provider(
        [
            AssertionError("evaluator must not run")
            if contact_stage == "planner"
            else _evaluator_turn("faithful_ready")
        ]
    )
    monkeypatch.setattr(
        ARTIFACTS,
        "seal_planner_checkpoint_archive",
        lambda **kwargs: (_ for _ in ()).throw(OSError("seal unavailable")),
    )

    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=planner,
        evaluator_provider=evaluator,
        archive_destination=tmp_path / "checkpoint-1",
        archive_identity=ARCHIVE_IDENTITY,
    )

    assert result.classification == "probe_inconclusive"
    assert result.sealed_archive is None
    assert result.control_failure == {
        "locus": "checkpoint_1_seal",
        "exception_type": "OSError",
        "message": "seal unavailable",
    }
    assert len(planner.requests) == 1
    assert len(result.planner_provider_attempts) == 1
    assert result.planner_provider_attempts[0].outcome == (
        "raised" if contact_stage == "planner" else "returned"
    )
    expected_evaluator_calls = 0 if contact_stage == "planner" else 1
    assert len(evaluator.requests) == expected_evaluator_calls
    assert len(result.evaluator_provider_attempts) == expected_evaluator_calls
    if contact_stage == "evaluator":
        assert result.evaluator_provider_attempts[0].outcome == "returned"


@pytest.mark.parametrize("contact_stage", ["planner", "evaluator"])
def test_execute_stops_after_checkpoint_seal_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contact_stage: str,
) -> None:
    _record_path = _install_passing_readiness(monkeypatch, tmp_path, sha="a" * 40)
    config = PROBE.parse_cli_args(
        _canonical_cli_args(
            tmp_path / f"run-{contact_stage}",
            transmit=True,
            readiness_record=_record_path,
        )
    )
    inputs = ARTIFACTS.load_planner_inputs(FIXTURES)
    prepared = PROBE.PreparedTransmission(
        config=config,
        git_sha="a" * 40,
        planner_inputs=inputs,
        planner_request=ARTIFACTS.render_planner_request(inputs),
        compiler_controls=PROBE._freeze_compiler_controls(),
        summary={},
    )
    planner = _Provider(
        [
            RuntimeError("planner unavailable")
            if contact_stage == "planner"
            else _planner_turn_bytes(READY_RECIPE_BYTES)
        ]
    )
    evaluator = _Provider(
        [
            AssertionError("evaluator must not run")
            if contact_stage == "planner"
            else _evaluator_turn("faithful_ready")
        ]
    )
    built_roles: list[str] = []

    def build_provider(**kwargs: object) -> object:
        role = str(kwargs["role"])
        built_roles.append(role)
        if role == "planner":
            return planner
        if role == "planner_evaluator":
            return evaluator
        raise AssertionError("compiler provider must not be constructed")

    monkeypatch.setattr(
        PROBE, "_git_checkout_state", lambda: PROBE.GitCheckoutState("a" * 40, True)
    )
    monkeypatch.setattr(PROBE, "_build_provider", build_provider)
    monkeypatch.setattr(
        ARTIFACTS,
        "seal_planner_checkpoint_archive",
        lambda **kwargs: (_ for _ in ()).throw(OSError("seal unavailable")),
    )
    joined_calls: list[object] = []
    monkeypatch.setattr(
        PROBE,
        "run_joined_probe",
        lambda **kwargs: joined_calls.append(kwargs),
    )

    result = PROBE._execute_transmitted_attempt(prepared)

    assert result.checkpoint_1.classification == "probe_inconclusive"
    assert result.checkpoint_2 == "not_evaluated"
    assert result.aggregate_outcome == "inconclusive"
    assert result.sealed_aggregate is None
    assert result.control_failure == result.checkpoint_1.control_failure
    assert built_roles == ["planner", "planner_evaluator"]
    assert len(planner.requests) == 1
    assert len(evaluator.requests) == (0 if contact_stage == "planner" else 1)
    assert joined_calls == []


@pytest.mark.parametrize(
    "failure_role",
    ["planner", "planner_evaluator", "compiler", "compiler_evaluator"],
)
def test_provider_constructor_failure_is_terminal_and_preserves_completed_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_role: str,
) -> None:
    run_root = tmp_path / f"run-{failure_role}"
    _record_path = _install_passing_readiness(
        monkeypatch, tmp_path, sha=ARCHIVE_IDENTITY["git_commit_sha"]
    )
    config = PROBE.parse_cli_args(
        _canonical_cli_args(run_root, transmit=True, readiness_record=_record_path)
    )
    inputs = ARTIFACTS.load_planner_inputs(FIXTURES)
    prepared = PROBE.PreparedTransmission(
        config=config,
        git_sha=ARCHIVE_IDENTITY["git_commit_sha"],
        planner_inputs=inputs,
        planner_request=ARTIFACTS.render_planner_request(inputs),
        compiler_controls=PROBE._freeze_compiler_controls(),
        summary={},
    )
    planner_turn = _planner_turn_bytes(READY_RECIPE_BYTES)
    planner_turn = SUPPORT.ProviderTurn(
        raw_request=planner_turn.raw_request,
        raw_response=planner_turn.raw_response,
        assistant_message=planner_turn.assistant_message,
        usage=planner_turn.usage,
        provider_metadata={
            "model_identity": config.planner_model,
            "profile_identity": PROBE._PLANNER_PROVIDER_PROFILE_ID,
        },
    )
    evaluator_turn = _evaluator_turn("faithful_ready")
    evaluator_turn = SUPPORT.ProviderTurn(
        raw_request=evaluator_turn.raw_request,
        raw_response=evaluator_turn.raw_response,
        assistant_message=evaluator_turn.assistant_message,
        usage=evaluator_turn.usage,
        provider_metadata={
            "model_identity": config.planner_evaluator_model,
            "profile_identity": PROBE._PLANNER_PROVIDER_PROFILE_ID,
        },
    )
    planner = _Provider([planner_turn])
    planner_evaluator = _Provider([evaluator_turn])
    compiler = _Provider([AssertionError("compiler must not be called")])
    compiler.identity = {"provider": "fake-compiler"}
    compiler_evaluator = _Provider(
        [AssertionError("compiler evaluator must not be called")]
    )
    compiler_evaluator.identity = {"provider": "fake-compiler-evaluator"}
    providers = {
        "planner": planner,
        "planner_evaluator": planner_evaluator,
        "compiler": compiler,
        "compiler_evaluator": compiler_evaluator,
    }
    role_order = list(providers)
    constructed_roles: list[str] = []
    failure_message = f"{failure_role} adapter unavailable"
    if failure_role == "planner":
        failure_message += ":" + "x" * 2100

    def build_provider(**kwargs: object) -> object:
        role = str(kwargs["role"])
        constructed_roles.append(role)
        if role == failure_role:
            raise LookupError(failure_message)
        return providers[role]

    monkeypatch.setattr(
        PROBE,
        "_git_checkout_state",
        lambda: PROBE.GitCheckoutState(ARCHIVE_IDENTITY["git_commit_sha"], True),
    )
    monkeypatch.setattr(PROBE, "_build_provider", build_provider)
    joined_calls: list[object] = []
    monkeypatch.setattr(
        PROBE,
        "run_joined_probe",
        lambda **kwargs: joined_calls.append(kwargs),
    )

    result = PROBE._execute_transmitted_attempt(prepared)

    assert type(result) is PROBE.TerminalControlFailureResult
    assert result.aggregate_outcome == "inconclusive"
    assert result.checkpoint_2 == "not_evaluated"
    assert result.sealed_aggregate is None
    assert result.control_failure == {
        "locus": "provider_construction",
        "role": failure_role,
        "exception_type": "LookupError",
        "message": failure_message[:2000],
    }
    failure_index = role_order.index(failure_role)
    assert constructed_roles == role_order[: failure_index + 1]
    if failure_role in {"planner", "planner_evaluator"}:
        assert result.checkpoint_1 is None
        assert planner.requests == []
        assert planner_evaluator.requests == []
    else:
        assert result.checkpoint_1 is not None
        assert result.checkpoint_1.classification == "probe_candidate_ready"
        assert result.checkpoint_1.sealed_archive is not None
        assert len(result.checkpoint_1.planner_provider_attempts) == 1
        assert len(result.checkpoint_1.evaluator_provider_attempts) == 1
        assert result.checkpoint_1.planner_provider_attempts[0].provider_turn is planner_turn
        assert (
            result.checkpoint_1.evaluator_provider_attempts[0].provider_turn
            is evaluator_turn
        )
        assert ARTIFACTS.verify_sealed_planner_checkpoint_archive(
            result.checkpoint_1.sealed_archive.archive_dir,
            expected_aggregate_identity=(
                result.checkpoint_1.sealed_archive.aggregate_identity
            ),
        )
        assert len(planner.requests) == 1
        assert len(planner_evaluator.requests) == 1
    assert compiler.requests == []
    assert compiler_evaluator.requests == []
    assert joined_calls == []
    assert run_root.is_dir()
    with pytest.raises(FileExistsError):
        PROBE._execute_transmitted_attempt(prepared)


def test_cli_reports_provider_constructor_failure_without_fabricated_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failure = {
        "locus": "provider_construction",
        "role": "planner",
        "exception_type": "LookupError",
        "message": "planner adapter unavailable",
    }
    monkeypatch.setattr(
        PROBE,
        "_git_checkout_state",
        lambda: PROBE.GitCheckoutState("d" * 40, True),
    )
    monkeypatch.setattr(
        PROBE,
        "_execute_transmitted_attempt",
        lambda prepared: PROBE.TerminalControlFailureResult(
            checkpoint_1=None,
            checkpoint_2="not_evaluated",
            aggregate_outcome="inconclusive",
            sealed_aggregate=None,
            control_failure=failure,
        ),
    )

    assert PROBE.main(_canonical_cli_args(tmp_path / "run", transmit=True)) == 0

    output_lines = capsys.readouterr().out.splitlines()
    terminal = json.loads(output_lines[-1])
    assert terminal == {
        "aggregate_outcome": "inconclusive",
        "checkpoint_1": None,
        "checkpoint_2": "not_evaluated",
        "control_failure": failure,
        "sealed_aggregate": None,
    }


@pytest.mark.parametrize("tamper", ["raw_request", "raw_error", "failure_type"])
def test_provider_call_failure_archive_rejects_reauthenticated_transport_tamper(
    tmp_path: Path, tamper: str,
) -> None:
    failure = LM9B_C_SUPPORT.ProviderCallFailure(
        failure_type="BadRequestError",
        message="provider rejected request",
        raw_request=b'{"sanitized":"request"}',
        raw_error=b'{"sanitized":"error"}',
    )
    archive_dir = tmp_path / "checkpoint-1"
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([failure]),
        evaluator_provider=_Provider([AssertionError("evaluator must not run")]),
        archive_destination=archive_dir,
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert result.sealed_archive is not None
    relative_path = "planner/attempts/000/capture.json"
    if tamper in {"raw_request", "raw_error"}:
        relative_path = f"planner/attempts/000/{tamper}.bin"
        (archive_dir / relative_path).write_bytes(b"tampered")
    else:
        capture_path = archive_dir / relative_path
        capture = json.loads(capture_path.read_bytes())
        capture["failure_type"] = None
        capture_path.write_text(json.dumps(capture), encoding="utf-8")
    original_identity = result.sealed_archive.aggregate_identity
    if tamper in {"raw_request", "raw_error"}:
        with pytest.raises(ValueError, match="sealed checkpoint archive"):
            ARTIFACTS.verify_sealed_planner_checkpoint_archive(
                archive_dir,
                expected_aggregate_identity=original_identity,
            )
        return
    checksums_path = archive_dir / "checksums.json"
    checksums = json.loads(checksums_path.read_bytes())
    for record in checksums["records"]:
        if record["path"] == relative_path:
            raw = (archive_dir / relative_path).read_bytes()
            record["raw_sha256"] = SUPPORT.sha256_prefixed(raw)
            record["byte_length"] = len(raw)
    checksums["aggregate_identity"] = ARTIFACTS.canonical_fingerprint(
        ARTIFACTS.own_trusted_json(
            {"schema": checksums["schema"], "records": checksums["records"]}
        )
    )
    checksums_path.write_text(json.dumps(checksums), encoding="utf-8")
    with pytest.raises(ValueError, match="sealed checkpoint archive"):
        ARTIFACTS.verify_sealed_planner_checkpoint_archive(
            archive_dir,
            expected_aggregate_identity=checksums["aggregate_identity"],
        )


def test_checkpoint_archive_rejects_reauthenticated_return_with_exception_fields(
    sealed_checkpoint,
) -> None:
    result, archive_dir = sealed_checkpoint
    capture_path = archive_dir / "planner/attempts/000/capture.json"
    capture = json.loads(capture_path.read_bytes())
    capture["exception_type"] = "RuntimeError"
    capture["exception_message"] = "invented"
    capture_path.write_text(json.dumps(capture), encoding="utf-8")
    checksums_path = archive_dir / "checksums.json"
    checksums = json.loads(checksums_path.read_bytes())
    relative_path = "planner/attempts/000/capture.json"
    for record in checksums["records"]:
        if record["path"] == relative_path:
            raw = capture_path.read_bytes()
            record["raw_sha256"] = SUPPORT.sha256_prefixed(raw)
            record["byte_length"] = len(raw)
    checksums["aggregate_identity"] = ARTIFACTS.canonical_fingerprint(
        ARTIFACTS.own_trusted_json(
            {"schema": checksums["schema"], "records": checksums["records"]}
        )
    )
    checksums_path.write_text(json.dumps(checksums), encoding="utf-8")

    with pytest.raises(ValueError, match="sealed checkpoint archive"):
        ARTIFACTS.verify_sealed_planner_checkpoint_archive(
            archive_dir,
            expected_aggregate_identity=checksums["aggregate_identity"],
        )


def test_checkpoint_archive_non_head_git_sha_is_post_contact_inconclusive(
    tmp_path: Path,
) -> None:
    identity = dict(ARCHIVE_IDENTITY)
    identity["git_commit_sha"] = "f" * 40
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
        evaluator_provider=_Provider([_evaluator_turn("faithful_ready")]),
        archive_destination=tmp_path / "checkpoint-1",
        archive_identity=identity,
    )
    assert result.classification == "probe_inconclusive"
    assert result.sealed_archive is None
    assert "checked-out HEAD" in result.control_failure["message"]


def test_checkpoint_archive_never_overwrites_an_existing_seal(
    sealed_checkpoint,
) -> None:
    _, archive_dir = sealed_checkpoint
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
        evaluator_provider=_Provider([_evaluator_turn("faithful_ready")]),
        archive_destination=archive_dir,
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert result.classification == "probe_inconclusive"
    assert result.sealed_archive is None
    assert result.control_failure["exception_type"] == "FileExistsError"
    assert "already exists" in result.control_failure["message"]


def test_mechanically_rejected_checkpoint_seals_without_an_evaluator_call(
    tmp_path: Path,
) -> None:
    archive_dir = tmp_path / "checkpoint-1"
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider(
            [_empty_planner_turn() for _ in range(SUPPORT.PLANNER_MAX_TURNS)]
        ),
        evaluator_provider=_Provider([RuntimeError("must not be consumed")]),
        archive_destination=archive_dir,
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert result.classification == "probe_mechanically_rejected"
    assert result.sealed_archive is not None
    assert (archive_dir / "evaluator/not_run.json").is_file()
    assert ARTIFACTS.verify_sealed_planner_checkpoint_archive(
        archive_dir,
        expected_aggregate_identity=result.sealed_archive.aggregate_identity,
    )


def test_pre_freeze_checkpoint_and_sealing_never_read_hidden_controls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    forbidden = {
        (COMPILER_FIXTURES / "input_manifest.json").resolve(),
        (COMPILER_FIXTURES / "r01_recipe.json").resolve(),
        READY_RECIPE.resolve(),
        BLOCKED_RECIPE.resolve(),
    }
    observed: set[Path] = set()
    original_read_bytes = Path.read_bytes
    original_open = Path.open
    original_stat = Path.stat
    original_builtin_open = builtins.open

    def notice(value) -> None:
        try:
            resolved = Path(value).absolute()
        except TypeError:
            return
        if resolved in forbidden:
            observed.add(resolved)

    def audited_read_bytes(path: Path):
        notice(path)
        return original_read_bytes(path)

    def audited_open(path: Path, *args, **kwargs):
        notice(path)
        return original_open(path, *args, **kwargs)

    def audited_stat(path: Path, *args, **kwargs):
        notice(path)
        return original_stat(path, *args, **kwargs)

    def audited_builtin_open(file, *args, **kwargs):
        notice(file)
        return original_builtin_open(file, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", audited_read_bytes)
    monkeypatch.setattr(Path, "open", audited_open)
    monkeypatch.setattr(Path, "stat", audited_stat)
    monkeypatch.setattr(builtins, "open", audited_builtin_open)
    PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
        evaluator_provider=_Provider([_evaluator_turn("faithful_ready")]),
        archive_destination=tmp_path / "checkpoint-1",
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert observed == set()


def test_post_freeze_r01_comparison_requires_verified_sealed_aggregate_and_preserves_archive(
    sealed_checkpoint,
) -> None:
    result, archive_dir = sealed_checkpoint
    before = (archive_dir / "checksums.json").read_bytes()
    with pytest.raises(ValueError, match="retained seal"):
        ARTIFACTS.compare_sealed_checkpoint_with_r01(
            archive_dir=archive_dir,
            sealed_aggregate_identity="sha256:" + "0" * 64,
            r01_recipe_path=COMPILER_FIXTURES / "r01_recipe.json",
        )
    comparison = ARTIFACTS.compare_sealed_checkpoint_with_r01(
        archive_dir=archive_dir,
        sealed_aggregate_identity=result.sealed_archive.aggregate_identity,
        r01_recipe_path=COMPILER_FIXTURES / "r01_recipe.json",
    )
    assert comparison["sealed_aggregate_identity"] == result.sealed_archive.aggregate_identity
    assert comparison["r01_raw_sha256"].startswith("sha256:")
    assert (archive_dir / "checksums.json").read_bytes() == before


def _canonical_cli_args(
    run_root: Path,
    *,
    transmit: bool = False,
    readiness_record: "Path | str | None" = None,
) -> list[str]:
    args = [
        "--planner-model",
        "gpt-5.4",
        "--planner-evaluator-model",
        "gpt-5.4",
        "--compiler-model",
        "gemini/gemini-3.1-pro-preview",
        "--compiler-evaluator-model",
        "gemini/gemini-3.1-pro-preview",
        "--planner-temperature",
        "0.0",
        "--planner-evaluator-temperature",
        "0.0",
        "--compiler-temperature",
        "0.0",
        "--compiler-evaluator-temperature",
        "0.0",
        "--run-root",
        str(run_root),
    ]
    if transmit:
        args.append("--transmit")
        # --readiness-record is required with --transmit. Tests whose earlier
        # guard (argparse, dirty checkout, existing run root) fires before the
        # gate reads the record only need a placeholder path; downstream
        # execution tests pass a real passing record via `readiness_record`.
        record = readiness_record if readiness_record is not None else (
            run_root.parent / "placeholder-readiness.json"
        )
        args += ["--readiness-record", str(record)]
    return args


def _install_passing_readiness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, sha: str
) -> Path:
    """Write an authentic passing readiness record bound to the test's checkout
    SHA, set the launch clock and credential presence, and return its path for
    `--readiness-record`. Derives routes from the exact canonical models; the
    canonical helper returns None for both, so `lambda: None` derivation matches
    the gate's real-helper derivation exactly."""
    manifest = RCONTRACT.derive_routes(
        RCONTRACT.role_routes_from_models(RCONTRACT.CANONICAL_ROLE_MODELS),
        lambda _model: None,
    )
    rows = [
        {
            "route_fingerprint": route.route_fingerprint,
            "member_roles": list(route.member_roles),
            "observed_at": "2026-07-21T12:00:05Z",
            "request_fingerprint": RCONTRACT.request_fingerprint(route),
            "outcome": {
                "kind": "model_response",
                "assistant_present": True,
                "tool_calls": [{"name": "ack", "arguments": '{"ok": true}'}],
                "raw_response_fingerprint": "sha256:resp",
            },
        }
        for route in manifest.routes
    ]
    record = {
        "schema_id": RCONTRACT.SCHEMA_ID,
        "reviewed_commit_sha": sha,
        "route_manifest_fingerprint": manifest.manifest_fingerprint,
        "canary_protocol_fingerprint": RCONTRACT.canary_protocol_fingerprint(),
        "max_age_seconds": RCONTRACT.FROZEN_MAX_AGE_S,
        "completed_at": "2026-07-21T12:00:06Z",
        "routes": rows,
    }
    record["record_fingerprint"] = RCONTRACT.record_fingerprint(record)
    path = tmp_path / "passing_readiness_record.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    monkeypatch.setattr(PROBE, "_readiness_now_iso", lambda: "2026-07-21T12:00:30Z")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "y")
    return path


def test_direct_cli_entrypoint_loads_before_argument_processing() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/lm9b_p_planner_recipe_transfer_probe.py"),
            "--help",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--transmit" in completed.stdout


def test_cli_dry_run_prints_complete_pretransmission_summary_without_contact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    contacts: list[object] = []
    monkeypatch.setattr(
        PROBE,
        "_git_checkout_state",
        lambda: PROBE.GitCheckoutState("a" * 40, True),
    )
    monkeypatch.setattr(
        PROBE,
        "_execute_transmitted_attempt",
        lambda prepared: contacts.append(prepared),
    )
    monkeypatch.setattr(
        PROBE,
        "_build_provider",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("provider contact")),
    )

    assert PROBE.main(_canonical_cli_args(tmp_path / "unused-run")) == 0

    summary = json.loads(capsys.readouterr().out)
    assert summary["git_sha"] == "a" * 40
    assert summary["models"] == {
        "planner": {"model": "gpt-5.4", "temperature": 0.0},
        "planner_evaluator": {"model": "gpt-5.4", "temperature": 0.0},
        "compiler": {
            "model": "gemini/gemini-3.1-pro-preview",
            "temperature": 0.0,
        },
        "compiler_evaluator": {
            "model": "gemini/gemini-3.1-pro-preview",
            "temperature": 0.0,
        },
    }
    assert summary["planner_request"]["byte_length"] > 0
    assert summary["planner_request"]["raw_sha256"].startswith("sha256:")
    assert summary["authority_manifest_fingerprint"].startswith("sha256:")
    assert summary["normalization_profile_fingerprint"].startswith("sha256:")
    assert summary["compiler_renderer_identity"] == LM9B_C_ARTIFACTS.COMPILER_RENDERER_ID
    assert summary["r01_pre_freeze_access"] == "forbidden"
    assert summary["execution_permitted"] is False
    assert summary["transmission_requested"] is False
    assert summary["bounds"]["compiler"] == {
        "max_turns": 6,
        "max_completion_tokens_per_call": 16_384,
        "provider_timeout_s": 180.0,
        "overall_deadline_s": 600.0,
        "cumulative_token_stop_threshold": 120_000,
        "cumulative_cost_stop_threshold_usd": 10.0,
    }
    assert summary["bounds"]["compiler_evaluator"] == {
        "max_attempts": 1,
        "max_completion_tokens": 8_192,
        "provider_timeout_s": 180.0,
    }
    assert contacts == []
    assert not (tmp_path / "unused-run").exists()


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--compiler-model", "different-model"),
        ("--compiler-evaluator-model", "different-model"),
        ("--compiler-temperature", "0.1"),
        ("--compiler-evaluator-temperature", "0.1"),
    ],
)
def test_cli_rejects_changes_to_archived_compiler_controls(
    tmp_path: Path, flag: str, value: str
) -> None:
    args = _canonical_cli_args(tmp_path / "run")
    args[args.index(flag) + 1] = value
    with pytest.raises(SystemExit):
        PROBE.parse_cli_args(args)


def test_cli_rejects_dirty_checkout_before_provider_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contacts: list[object] = []
    monkeypatch.setattr(
        PROBE,
        "_git_checkout_state",
        lambda: PROBE.GitCheckoutState("b" * 40, False),
    )
    monkeypatch.setattr(PROBE, "_build_provider", lambda **kwargs: contacts.append(kwargs))
    with pytest.raises(RuntimeError, match="clean committed HEAD"):
        PROBE.main(_canonical_cli_args(tmp_path / "run", transmit=True))
    assert contacts == []


def test_cli_rejects_existing_run_root_before_provider_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = tmp_path / "existing"
    run_root.mkdir()
    contacts: list[object] = []
    monkeypatch.setattr(
        PROBE,
        "_git_checkout_state",
        lambda: PROBE.GitCheckoutState("c" * 40, True),
    )
    monkeypatch.setattr(PROBE, "_build_provider", lambda **kwargs: contacts.append(kwargs))
    with pytest.raises(FileExistsError, match="run root"):
        PROBE.main(_canonical_cli_args(run_root, transmit=True))
    assert contacts == []


def test_transmit_path_uses_prepared_frozen_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    observed: list[object] = []
    monkeypatch.setattr(
        PROBE,
        "_git_checkout_state",
        lambda: PROBE.GitCheckoutState("d" * 40, True),
    )
    monkeypatch.setattr(
        PROBE,
        "_execute_transmitted_attempt",
        lambda prepared: (
            observed.append(prepared)
            or SimpleNamespace(
                checkpoint_1=SimpleNamespace(classification="probe_candidate_ready"),
                checkpoint_2="bounded_lowering_demonstrated",
                aggregate_outcome="joined_transfer_demonstrated",
                sealed_aggregate=SimpleNamespace(aggregate_identity="sha256:" + "e" * 64),
                control_failure=None,
            )
        ),
    )
    assert PROBE.main(_canonical_cli_args(tmp_path / "run", transmit=True)) == 0
    assert len(observed) == 1
    prepared = observed[0]
    assert prepared.git_sha == "d" * 40
    assert prepared.config.transmit is True
    assert prepared.config.compiler_model == "gemini/gemini-3.1-pro-preview"
    assert prepared.config.compiler_evaluator_model == "gemini/gemini-3.1-pro-preview"
    output = capsys.readouterr().out
    assert '"transmission_requested": true' in output
    assert '"aggregate_outcome": "joined_transfer_demonstrated"' in output


def test_cli_reports_unsealed_post_contact_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    failure = {
        "locus": "checkpoint_1_seal",
        "exception_type": "OSError",
        "message": "seal unavailable",
    }
    monkeypatch.setattr(
        PROBE,
        "_git_checkout_state",
        lambda: PROBE.GitCheckoutState("d" * 40, True),
    )
    monkeypatch.setattr(
        PROBE,
        "_execute_transmitted_attempt",
        lambda prepared: SimpleNamespace(
            checkpoint_1=SimpleNamespace(classification="probe_inconclusive"),
            checkpoint_2="not_evaluated",
            aggregate_outcome="inconclusive",
            sealed_aggregate=None,
            control_failure=failure,
        ),
    )

    assert PROBE.main(_canonical_cli_args(tmp_path / "run", transmit=True)) == 0

    output = capsys.readouterr().out
    assert '"aggregate_outcome": "inconclusive"' in output
    assert '"sealed_aggregate": null' in output
    assert '"locus": "checkpoint_1_seal"' in output


def test_scope_guard_rejects_forbidden_imports_and_pre_freeze_r01_references(
    tmp_path: Path,
) -> None:
    forbidden_import = tmp_path / "forbidden_import.py"
    forbidden_import.write_text("from rook.agent.base_agent import RookAgent\n", encoding="utf-8")
    with pytest.raises(ValueError, match="forbidden import"):
        PROBE.verify_scope_guards((forbidden_import,))

    hidden_control = tmp_path / "hidden_control.py"
    hidden_control.write_text("CONTROL = 'r01_recipe.json'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="matched-control"):
        PROBE.verify_scope_guards((hidden_control,))


@pytest.mark.parametrize(
    "source",
    [
        "TOOL_NAME = 'gh_edit'\n",
        "r01_recipe_path = object()\n",
        "from rook.validation_kernel._private import unsafe\n",
    ],
)
def test_scope_guard_rejects_forbidden_tools_names_and_private_kernel_imports(
    tmp_path: Path, source: str
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text(source, encoding="utf-8")
    with pytest.raises(ValueError, match="forbidden|matched-control"):
        PROBE.verify_scope_guards((candidate,))


def test_scope_guard_rejects_a_forbidden_imported_symbol(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("from tools import gh_edit\n", encoding="utf-8")
    with pytest.raises(ValueError, match="forbidden"):
        PROBE.verify_scope_guards((candidate,))


def test_scope_guard_accepts_current_production_probe_surface() -> None:
    PROBE.verify_scope_guards(PROBE.PRODUCTION_SCOPE_FILES)


def test_frozen_compiler_control_assertion_detects_lm9bc_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(LM9B_C_PROBE, "MAX_TURNS", 7)
    monkeypatch.setattr(PROBE, "_load_lm9bc_modules", lambda: (LM9B_C_ARTIFACTS, LM9B_C_PROBE))
    with pytest.raises(RuntimeError, match="LM9B-C control drift"):
        PROBE.assert_frozen_compiler_controls()


def test_frozen_planner_control_assertion_detects_local_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(PROBE, "PLANNER_MAX_TURNS", 7)
    with pytest.raises(RuntimeError, match="Planner control drift"):
        PROBE.assert_frozen_planner_controls()


def test_checkpoint_consumes_the_pretransmission_snapshot_without_reloading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = ARTIFACTS.load_planner_inputs(FIXTURES)
    request = ARTIFACTS.render_planner_request(inputs)
    monkeypatch.setattr(
        ARTIFACTS,
        "load_planner_inputs",
        lambda path: (_ for _ in ()).throw(AssertionError("authority reread")),
    )

    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        frozen_inputs=inputs,
        frozen_planner_request=request,
        planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
        evaluator_provider=_Provider([_evaluator_turn("faithful_ready")]),
    )

    assert result.classification == "probe_candidate_ready"
    assert result.planner_inputs is inputs


def test_execute_reauthenticates_head_and_passes_frozen_inputs_to_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_path = _install_passing_readiness(monkeypatch, tmp_path, sha="f" * 40)
    config = PROBE.parse_cli_args(
        _canonical_cli_args(tmp_path / "run", transmit=True, readiness_record=_record_path)
    )
    inputs = ARTIFACTS.load_planner_inputs(FIXTURES)
    request = ARTIFACTS.render_planner_request(inputs)
    prepared = PROBE.PreparedTransmission(
        config=config,
        git_sha="f" * 40,
        planner_inputs=inputs,
        planner_request=request,
        compiler_controls=PROBE._freeze_compiler_controls(),
        summary={},
    )
    contacts: list[object] = []
    monkeypatch.setattr(
        PROBE,
        "_git_checkout_state",
        lambda: PROBE.GitCheckoutState("e" * 40, True),
    )
    monkeypatch.setattr(PROBE, "_build_provider", lambda **kwargs: contacts.append(kwargs))
    with pytest.raises(RuntimeError, match="changed after pre-transmission"):
        PROBE._execute_transmitted_attempt(prepared)
    assert contacts == []
    assert not config.run_root.exists()

    captured: list[dict[str, object]] = []
    monkeypatch.setattr(
        PROBE,
        "_git_checkout_state",
        lambda: PROBE.GitCheckoutState("f" * 40, True),
    )

    class _FakeProvider:
        identity = {"provider": "fake"}

        def __call__(self, request):
            raise AssertionError("fake provider must not be contacted by this test")

    monkeypatch.setattr(PROBE, "_build_provider", lambda **kwargs: _FakeProvider())
    monkeypatch.setattr(
        PROBE,
        "run_planner_checkpoint",
        lambda **kwargs: captured.append(kwargs) or "checkpoint",
    )
    monkeypatch.setattr(PROBE, "run_joined_probe", lambda **kwargs: "joined")

    assert PROBE._execute_transmitted_attempt(prepared) == "joined"
    assert captured[0]["frozen_inputs"] is inputs
    assert captured[0]["frozen_planner_request"] is request


def test_compiler_controls_are_snapshotted_before_provider_contact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiler_fixtures = tmp_path / "compiler-fixtures"
    compiler_fixtures.mkdir()
    expected: dict[str, bytes] = {}
    for name in ("implementation_context.json", "exclusion_policy.json", "evaluation_rubric.json"):
        raw = (COMPILER_FIXTURES / name).read_bytes()
        expected[name] = raw
        (compiler_fixtures / name).write_bytes(raw)
    monkeypatch.setattr(PROBE, "_COMPILER_FIXTURES", compiler_fixtures)
    monkeypatch.setattr(
        PROBE,
        "_git_checkout_state",
        lambda: PROBE.GitCheckoutState("a" * 40, True),
    )
    _record_path = _install_passing_readiness(monkeypatch, tmp_path, sha="a" * 40)
    config = PROBE.parse_cli_args(
        _canonical_cli_args(tmp_path / "run", transmit=True, readiness_record=_record_path)
    )
    prepared = PROBE.prepare_pretransmission(config)
    (compiler_fixtures / "implementation_context.json").write_bytes(b"{}\n")

    class _FakeProvider:
        identity = {"provider": "fake"}

        def __call__(self, request):
            raise AssertionError("fake provider must not be contacted by this test")

    monkeypatch.setattr(PROBE, "_build_provider", lambda **kwargs: _FakeProvider())
    monkeypatch.setattr(PROBE, "run_planner_checkpoint", lambda **kwargs: "checkpoint")
    observed: list[Path] = []

    def joined(**kwargs):
        observed.append(kwargs["compiler_fixture_dir"])
        return "joined"

    monkeypatch.setattr(PROBE, "run_joined_probe", joined)
    assert PROBE._execute_transmitted_attempt(prepared) == "joined"
    assert len(observed) == 1
    assert {
        name: (observed[0] / name).read_bytes()
        for name in expected
    } == expected
