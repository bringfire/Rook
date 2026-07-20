from __future__ import annotations

import builtins
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

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
def test_checkpoint_archive_rejects_successful_provider_metadata_mismatch(
    field: str, value: str, tmp_path: Path,
) -> None:
    identity = dict(ARCHIVE_IDENTITY)
    identity[field] = value
    with pytest.raises(ValueError, match="provider identity"):
        PROBE.run_planner_checkpoint(
            fixture_dir=FIXTURES,
            planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
            evaluator_provider=_Provider([_evaluator_turn("faithful_ready")]),
            archive_destination=tmp_path / "checkpoint-1",
            archive_identity=identity,
        )


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


def test_checkpoint_archive_rejects_a_valid_but_non_head_git_sha(
    tmp_path: Path,
) -> None:
    identity = dict(ARCHIVE_IDENTITY)
    identity["git_commit_sha"] = "f" * 40
    with pytest.raises(ValueError, match="checked-out HEAD"):
        PROBE.run_planner_checkpoint(
            fixture_dir=FIXTURES,
            planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
            evaluator_provider=_Provider([_evaluator_turn("faithful_ready")]),
            archive_destination=tmp_path / "checkpoint-1",
            archive_identity=identity,
        )


def test_checkpoint_archive_never_overwrites_an_existing_seal(
    sealed_checkpoint,
) -> None:
    _, archive_dir = sealed_checkpoint
    with pytest.raises(FileExistsError, match="already exists"):
        PROBE.run_planner_checkpoint(
            fixture_dir=FIXTURES,
            planner_provider=_Provider([_planner_turn_bytes(READY_RECIPE_BYTES)]),
            evaluator_provider=_Provider([_evaluator_turn("faithful_ready")]),
            archive_destination=archive_dir,
            archive_identity=ARCHIVE_IDENTITY,
        )


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
