"""Checkpoint 1 controller for the bounded LM9B-P Planner probe."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal


_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_PLANNER_EVALUATOR_SYSTEM_PROMPT = (
    "Evaluate the submitted Planner recipe only against the visible brief, exact "
    "authority, deterministic findings, and frozen rubric. Do not infer compiler "
    "behavior, use hidden context, repair the recipe, or classify the probe. Submit "
    "exactly one evidence-backed recommendation through submit_planner_evaluation."
)

import lm9b_p_planner_recipe_transfer_artifacts as ARTIFACTS
from lm9b_p_planner_recipe_transfer_support import (
    PlannerEvaluationResult,
    PlannerSessionResult,
    ProviderTurn,
    run_planner_evaluation,
    run_planner_session,
)


@dataclass(frozen=True)
class PlannerCheckpointResult:
    classification: Literal[
        "probe_mechanically_rejected",
        "probe_inconclusive",
        "probe_candidate_blocked",
        "probe_planner_failure",
        "probe_candidate_ready",
    ]
    planner_session: PlannerSessionResult
    evaluator: PlannerEvaluationResult | None
    final_recipe_bytes: bytes | None
    checkpoint_2: Literal["not_evaluated"]


def _checkpoint_classification(
    planner_session: PlannerSessionResult,
    evaluator: PlannerEvaluationResult | None,
) -> PlannerCheckpointResult:
    if planner_session.termination == "mechanically_rejected":
        return PlannerCheckpointResult(
            "probe_mechanically_rejected", planner_session, None, None, "not_evaluated"
        )
    if planner_session.termination != "mechanically_accepted" or evaluator is None:
        return PlannerCheckpointResult(
            "probe_inconclusive", planner_session, evaluator, None, "not_evaluated"
        )
    if evaluator.termination != "valid_recommendation":
        return PlannerCheckpointResult(
            "probe_inconclusive",
            planner_session,
            evaluator,
            planner_session.final_recipe_bytes,
            "not_evaluated",
        )
    classifications = {
        "faithful_blocked": "probe_candidate_blocked",
        "planner_failure": "probe_planner_failure",
        "faithful_ready": "probe_candidate_ready",
    }
    classification = classifications[evaluator.recommendation]
    return PlannerCheckpointResult(
        classification,
        planner_session,
        evaluator,
        planner_session.final_recipe_bytes,
        "not_evaluated",
    )


def run_planner_checkpoint(
    *,
    fixture_dir: Path,
    planner_provider: Callable[[dict[str, object]], ProviderTurn],
    evaluator_provider: Callable[[dict[str, object]], ProviderTurn],
) -> PlannerCheckpointResult:
    """Run one Planner session and at most one isolated evaluation attempt."""

    inputs = ARTIFACTS.load_planner_inputs(Path(fixture_dir))
    planner_request = ARTIFACTS.render_planner_request(inputs)
    planner_session = run_planner_session(
        provider=planner_provider,
        system_prompt=(
            "Author one governed Planner recipe using only the supplied request and "
            "submit it with submit_planner_recipe."
        ),
        user_prompt=planner_request.raw_bytes.decode("utf-8"),
        authority=inputs.authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.authority.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    if planner_session.termination != "mechanically_accepted":
        return _checkpoint_classification(planner_session, None)

    final_recipe_bytes = planner_session.final_recipe_bytes
    if final_recipe_bytes is None:
        return _checkpoint_classification(planner_session, None)
    gate_result = ARTIFACTS.evaluate_mechanical_gate(
        recipe_bytes=final_recipe_bytes,
        authority=inputs.authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.authority.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    if type(gate_result) is not ARTIFACTS.MechanicalGateResult:
        return _checkpoint_classification(planner_session, None)
    evaluator_request = ARTIFACTS.render_planner_evaluator_request(
        inputs, gate_result=gate_result
    )
    evaluator = run_planner_evaluation(
        provider=evaluator_provider,
        system_prompt=_PLANNER_EVALUATOR_SYSTEM_PROMPT,
        user_prompt=evaluator_request.raw_bytes.decode("utf-8"),
    )
    return _checkpoint_classification(planner_session, evaluator)


__all__ = ("PlannerCheckpointResult", "run_planner_checkpoint")
