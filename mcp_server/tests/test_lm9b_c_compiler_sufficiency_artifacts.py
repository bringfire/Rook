from __future__ import annotations

import importlib.util
import json
import sys
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


def _fixture_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "lm9b_c_fixtures"


def _provider_response(arguments: dict[str, object]) -> object:
    return SUPPORT.ProviderTurn(
        raw_response=b'{"exact":"response"}',
        raw_request=b'{"exact":"request"}',
        assistant_message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "submit_compiler_result",
                        "arguments": json.dumps(
                            {"submission_json": json.dumps(arguments)}
                        ),
                    },
                }
            ],
        },
        usage={"total_tokens": 100, "cost_usd": 0.01},
        provider_metadata={"request_id": "request-1"},
    )


def _minimal_candidate(inputs: object) -> dict[str, object]:
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


def test_frozen_manifest_authenticates_all_probe_inputs() -> None:
    inputs = ARTIFACTS.load_frozen_inputs(_fixture_dir())

    assert inputs.recipe["schema"] == "rook.planner_graph_recipe:v1"
    assert inputs.recipe["recipe_fingerprint"] == inputs.contract_index[
        "recipe_fingerprint"
    ]
    assert set(inputs.authority_artifacts) == {
        "environment_snapshot",
        "planning_policy",
        "task_envelope",
    }
    assert inputs.manifest["schema"] == "rook.lm9b_c.input_manifest:v1"
    assert all(record.raw_sha256.startswith("sha256:") for record in inputs.records)


def test_generic_implementation_context_contains_no_task_solution() -> None:
    inputs = ARTIFACTS.load_frozen_inputs(_fixture_dir())
    rendered = inputs.implementation_context_bytes.decode("utf-8").lower()

    for leaked_term in (
        "radial",
        "box",
        "10 x 10",
        "grid_spacing",
        "height_profile",
        "script_instance example",
    ):
        assert leaked_term not in rendered
    assert "csharp_script_instance" in rendered
    assert "no auxiliary canvas components" in rendered


def test_renderer_partitions_source_context_and_exclusions() -> None:
    inputs = ARTIFACTS.load_frozen_inputs(_fixture_dir())
    compiler = ARTIFACTS.render_compiler_request(inputs)
    rendered = compiler.user_prompt.decode("utf-8")

    assert '"semantic_source"' in rendered
    assert '"implementation_context"' in rendered
    assert "Create a 10 x 10" not in rendered
    assert "evaluation rubric" not in rendered.lower()
    assert inputs.recipe["recipe_fingerprint"] in rendered
    assert compiler.renderer_id == "lm9b_c.compiler_request_renderer:v1"


def test_contract_index_is_derived_from_frozen_recipe_not_a_parallel_dialect() -> None:
    inputs = ARTIFACTS.load_frozen_inputs(_fixture_dir())
    recipe = inputs.recipe

    assert inputs.contract_index["maintains_clause_ids"] == [
        item["clause_id"] for item in recipe["maintains"]
    ]
    assert inputs.contract_index["capability_ids"] == [
        item["capability_id"] for item in recipe["required_capabilities"]["entries"]
    ]
    assert "assumption.grid_spacing" in inputs.contract_index["support_ids"]
    assert "derived.element_count" in inputs.contract_index["support_ids"]


def test_r01_witness_arithmetic_and_spacing_discretion_are_frozen() -> None:
    inputs = ARTIFACTS.load_frozen_inputs(_fixture_dir())
    recipe = inputs.recipe
    nodes = list(ARTIFACTS.walk_json(recipe))

    assert len(recipe["assumptions"]) == 9
    assert sum(
        isinstance(node, dict) and node.get("kind") == "artifact_value"
        for node in nodes
    ) == 50
    assert sum(
        isinstance(node, dict) and node.get("kind") == "policy_rule"
        for node in nodes
    ) == 9
    assert len(recipe["authority_artifacts"]) + 1 == 3

    spacing_rule = inputs.authority_artifacts["planning_policy"]["rules"][
        "rule.grid_spacing"
    ]
    assert spacing_rule["effect"] == "allow"
    assert spacing_rule["value_constraint"] == {
        "kind": "closed_range",
        "exact_value": None,
        "minimum": "1",
        "maximum": "5",
        "minimum_inclusive": True,
        "maximum_inclusive": True,
    }


def test_evaluator_request_excludes_compiler_transcript() -> None:
    inputs = ARTIFACTS.load_frozen_inputs(_fixture_dir())
    terminal = _minimal_candidate(inputs)
    trace = SUPPORT.validate_terminal_submission(terminal, inputs.contract_index)

    request = ARTIFACTS.render_evaluator_request(inputs, terminal, trace)
    rendered = request.user_prompt.decode("utf-8").lower()

    assert "compiler transcript" not in rendered
    assert '"terminal_result"' in rendered
    assert '"deterministic_trace_check"' in rendered
    assert '"evaluation_rubric"' in rendered


def test_evidence_writer_preserves_exact_requests_responses_and_inputs(tmp_path: Path) -> None:
    inputs = ARTIFACTS.load_frozen_inputs(_fixture_dir())
    candidate = _minimal_candidate(inputs)
    provider = lambda request: _provider_response(candidate)
    session = SUPPORT.run_compiler_session(
        provider=provider,
        system_prompt="system",
        user_prompt="user",
        contract_index=inputs.contract_index,
        limits=SUPPORT.SessionLimits(
            max_turns=1,
            max_completion_tokens_per_call=1024,
            provider_timeout_s=10.0,
            overall_deadline_s=20.0,
            cumulative_token_stop_threshold=10000,
            cumulative_cost_stop_threshold_usd=5.0,
        ),
    )
    evaluator = SUPPORT.EvaluatorAttemptResult.control_failure("not_run")
    decision = SUPPORT.classify_observation(session, evaluator)

    run_dir = tmp_path / "run"
    ARTIFACTS.write_probe_evidence(
        run_dir=run_dir,
        inputs=inputs,
        compiler_request=ARTIFACTS.render_compiler_request(inputs),
        compiler_session=session,
        evaluator_request=None,
        evaluator_result=evaluator,
        decision=decision,
        run_metadata={"run_id": "test-run", "git_sha": "deadbeef"},
    )

    assert (run_dir / "inputs" / "recipe.json").read_bytes() == inputs.recipe_bytes
    assert (
        run_dir / "compiler" / "turns" / "turn-01" / "raw_request.json"
    ).read_bytes() == b'{"exact":"request"}'
    assert (
        run_dir / "compiler" / "turns" / "turn-01" / "raw_response.json"
    ).read_bytes() == b'{"exact":"response"}'
    assert json.loads((run_dir / "decision.json").read_text("utf-8"))[
        "outcome"
    ] == "inconclusive"
    assert json.loads(
        (run_dir / "evaluator" / "summary.json").read_text("utf-8")
    )["attempted"] is False
