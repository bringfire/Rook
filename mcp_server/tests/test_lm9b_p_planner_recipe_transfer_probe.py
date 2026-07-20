from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "scripts" / "lm9b_p_fixtures"
READY_RECIPE = ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json"
BLOCKED_RECIPE = ROOT / "mcp_server/tests/fixtures/lm9b_p/non_r01_blocked_recipe.json"


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SUPPORT = _load_script("lm9b_p_planner_recipe_transfer_support")
PROBE = _load_script("lm9b_p_planner_recipe_transfer_probe")


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
                                "recipe_json": recipe_path.read_bytes().decode(
                                    "utf-8"
                                )
                            }
                        ),
                    },
                }
            ],
        },
        usage={},
        provider_metadata={},
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
        provider_metadata={},
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
