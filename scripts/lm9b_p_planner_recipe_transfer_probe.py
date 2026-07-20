"""Checkpoint 1 controller for the bounded LM9B-P Planner probe."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Literal, Mapping


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
    sealed_archive: ARTIFACTS.SealedPlannerCheckpointArchive | None = None


def _checkpoint_classification(
    planner_session: PlannerSessionResult,
    evaluator: PlannerEvaluationResult | None,
) -> PlannerCheckpointResult:
    classification = ARTIFACTS.derive_checkpoint_classification(
        planner_session, evaluator
    )
    if classification == "probe_mechanically_rejected":
        return PlannerCheckpointResult(
            "probe_mechanically_rejected", planner_session, None, None, "not_evaluated"
        )
    if classification == "probe_inconclusive":
        return PlannerCheckpointResult(
            "probe_inconclusive",
            planner_session,
            evaluator,
            (
                planner_session.final_recipe_bytes
                if planner_session.termination == "mechanically_accepted"
                and evaluator is not None
                else None
            ),
            "not_evaluated",
        )
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
    archive_destination: Path | None = None,
    archive_identity: Mapping[str, object] | None = None,
) -> PlannerCheckpointResult:
    """Run one Planner session and at most one isolated evaluation attempt."""

    if archive_destination is None and archive_identity is not None:
        raise ValueError("archive identity requires an archive destination")
    if archive_destination is not None and archive_identity is None:
        raise ValueError("checkpoint archive identity is required")
    inputs = ARTIFACTS.load_planner_inputs(Path(fixture_dir))
    planner_request = ARTIFACTS.render_planner_request(inputs)
    planner_provider_turns: list[ProviderTurn] = []
    evaluator_provider_turns: list[ProviderTurn] = []
    evaluator_request: ARTIFACTS.RenderedRequest | None = None
    evaluator_elapsed_ms: int | None = None

    def recorded_planner_provider(request: dict[str, object]) -> ProviderTurn:
        turn = planner_provider(request)
        planner_provider_turns.append(turn)
        return turn

    def finish(result: PlannerCheckpointResult) -> PlannerCheckpointResult:
        if archive_destination is None:
            return result
        assert archive_identity is not None
        sealed = ARTIFACTS.seal_planner_checkpoint_archive(
            destination=archive_destination,
            inputs=inputs,
            planner_request=planner_request,
            planner_session=result.planner_session,
            evaluator=result.evaluator,
            evaluator_request=evaluator_request,
            planner_provider_turns=planner_provider_turns,
            evaluator_provider_turns=evaluator_provider_turns,
            evaluator_elapsed_ms=evaluator_elapsed_ms,
            classification=result.classification,
            archive_identity=archive_identity,
        )
        return replace(result, sealed_archive=sealed)

    planner_session = run_planner_session(
        provider=recorded_planner_provider,
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
        return finish(_checkpoint_classification(planner_session, None))

    final_recipe_bytes = planner_session.final_recipe_bytes
    if final_recipe_bytes is None:
        return finish(_checkpoint_classification(planner_session, None))
    gate_result = ARTIFACTS.evaluate_mechanical_gate(
        recipe_bytes=final_recipe_bytes,
        authority=inputs.authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.authority.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    if type(gate_result) is not ARTIFACTS.MechanicalGateResult:
        return finish(_checkpoint_classification(planner_session, None))
    evaluator_request = ARTIFACTS.render_planner_evaluator_request(
        inputs, gate_result=gate_result
    )
    def recorded_evaluator_provider(request: dict[str, object]) -> ProviderTurn:
        turn = evaluator_provider(request)
        evaluator_provider_turns.append(turn)
        return turn

    started_at = time.perf_counter()
    evaluator = run_planner_evaluation(
        provider=recorded_evaluator_provider,
        system_prompt=_PLANNER_EVALUATOR_SYSTEM_PROMPT,
        user_prompt=evaluator_request.raw_bytes.decode("utf-8"),
    )
    evaluator_elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    return finish(_checkpoint_classification(planner_session, evaluator))


__all__ = ("PlannerCheckpointResult", "run_planner_checkpoint")
