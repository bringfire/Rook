"""Checkpoint 1 controller for the bounded LM9B-P Planner probe."""

from __future__ import annotations

import importlib
import json
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
    planner_inputs: ARTIFACTS.FrozenPlannerInputs | None = None
    gate_result: ARTIFACTS.MechanicalGateResult | None = None


@dataclass(frozen=True)
class JoinedProbeResult:
    checkpoint_1: PlannerCheckpointResult
    checkpoint_2: Literal[
        "not_evaluated",
        "bounded_lowering_demonstrated",
        "contract_gap_demonstrated",
        "candidate_failure",
        "inconclusive",
    ]
    aggregate_outcome: str
    handoff: ARTIFACTS.Lm9bcHandoff | None
    lm9bc_result: object | None
    pre_session_failure: Mapping[str, object] | None
    sealed_aggregate: ARTIFACTS.SealedJoinedAggregate


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
    planner_provider_attempts: list[ARTIFACTS.ProviderAttemptEvidence] = []
    evaluator_provider_attempts: list[ARTIFACTS.ProviderAttemptEvidence] = []
    evaluator_request: ARTIFACTS.RenderedRequest | None = None
    evaluator_elapsed_ms: int | None = None
    checkpoint_gate: ARTIFACTS.MechanicalGateResult | None = None

    def provider_request_bytes(request: dict[str, object]) -> bytes:
        return json.dumps(
            request, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def recorded_planner_provider(request: dict[str, object]) -> ProviderTurn:
        attempt = ARTIFACTS.ProviderAttemptEvidence(
            provider_request_bytes=provider_request_bytes(request)
        )
        planner_provider_attempts.append(attempt)
        started_at = time.perf_counter()
        try:
            turn = planner_provider(request)
        except BaseException as exc:
            attempt.record_exception(exc, started_at)
            raise
        attempt.record_return(turn, started_at)
        return turn

    def finish(result: PlannerCheckpointResult) -> PlannerCheckpointResult:
        result = replace(
            result,
            planner_inputs=inputs,
            gate_result=checkpoint_gate,
        )
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
            planner_provider_attempts=planner_provider_attempts,
            evaluator_provider_attempts=evaluator_provider_attempts,
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
    checkpoint_gate = gate_result
    if type(gate_result) is not ARTIFACTS.MechanicalGateResult:
        return finish(_checkpoint_classification(planner_session, None))
    evaluator_request = ARTIFACTS.render_planner_evaluator_request(
        inputs, gate_result=gate_result
    )
    def recorded_evaluator_provider(request: dict[str, object]) -> ProviderTurn:
        attempt = ARTIFACTS.ProviderAttemptEvidence(
            provider_request_bytes=provider_request_bytes(request)
        )
        evaluator_provider_attempts.append(attempt)
        started_at = time.perf_counter()
        try:
            turn = evaluator_provider(request)
        except BaseException as exc:
            attempt.record_exception(exc, started_at)
            raise
        attempt.record_return(turn, started_at)
        return turn

    started_at = time.perf_counter()
    evaluator = run_planner_evaluation(
        provider=recorded_evaluator_provider,
        system_prompt=_PLANNER_EVALUATOR_SYSTEM_PROMPT,
        user_prompt=evaluator_request.raw_bytes.decode("utf-8"),
    )
    evaluator_elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    return finish(_checkpoint_classification(planner_session, evaluator))


def _load_lm9bc_modules() -> tuple[object, object]:
    return (
        importlib.import_module("lm9b_c_compiler_sufficiency_artifacts"),
        importlib.import_module("lm9b_c_compiler_sufficiency_probe"),
    )


def run_joined_probe(
    *,
    checkpoint_1: PlannerCheckpointResult,
    compiler_fixture_dir: Path,
    handoff_destination: Path,
    compiler_run_root: Path,
    aggregate_destination: Path,
    compiler_provider: Callable[[dict[str, object]], object],
    compiler_evaluator_provider: Callable[[dict[str, object]], object],
    compiler_identity: Mapping[str, object],
    compiler_evaluator_identity: Mapping[str, object],
    git_sha: str,
) -> JoinedProbeResult:
    """Join one sealed ready checkpoint to one unchanged LM9B-C session."""

    if type(checkpoint_1) is not PlannerCheckpointResult:
        raise TypeError("PlannerCheckpointResult is required")
    sealed_checkpoint = checkpoint_1.sealed_archive
    if sealed_checkpoint is None:
        raise ValueError("Checkpoint 1 must be sealed before the join")
    ARTIFACTS.verify_sealed_planner_checkpoint_archive(
        sealed_checkpoint.archive_dir,
        expected_aggregate_identity=sealed_checkpoint.aggregate_identity,
    )
    persisted_classification = ARTIFACTS.parse_strict_json(
        (
            sealed_checkpoint.archive_dir
            / "checkpoint"
            / "classification.json"
        ).read_bytes()
    )
    if (
        not isinstance(persisted_classification, dict)
        or persisted_classification.get("classification")
        != checkpoint_1.classification
    ):
        raise ValueError("Checkpoint 1 classification is not bound to its seal")

    def seal_result(
        *,
        checkpoint_2: str,
        aggregate_outcome: str,
        reason_codes: tuple[str, ...] = (),
        handoff: ARTIFACTS.Lm9bcHandoff | None = None,
        loaded_recipe_bytes: bytes | None = None,
        lm9bc_result: object | None = None,
        pre_session_failure: Mapping[str, object] | None = None,
    ) -> JoinedProbeResult:
        run_dir = getattr(lm9bc_result, "run_dir", None)
        sealed_aggregate = ARTIFACTS.seal_joined_aggregate(
            destination=aggregate_destination,
            checkpoint_1_archive=sealed_checkpoint,
            checkpoint_1_classification=checkpoint_1.classification,
            checkpoint_2_outcome=checkpoint_2,
            checkpoint_2_reason_codes=reason_codes,
            aggregate_outcome=aggregate_outcome,
            handoff=handoff,
            planner_recipe_bytes=checkpoint_1.final_recipe_bytes,
            lm9bc_loaded_recipe_bytes=loaded_recipe_bytes,
            lm9bc_run_dir=run_dir,
            pre_session_failure=pre_session_failure,
        )
        return JoinedProbeResult(
            checkpoint_1=checkpoint_1,
            checkpoint_2=checkpoint_2,
            aggregate_outcome=aggregate_outcome,
            handoff=handoff,
            lm9bc_result=lm9bc_result,
            pre_session_failure=pre_session_failure,
            sealed_aggregate=sealed_aggregate,
        )

    if checkpoint_1.classification != "probe_candidate_ready":
        outcome = ARTIFACTS.derive_joined_aggregate_outcome(
            checkpoint_1_classification=checkpoint_1.classification,
            checkpoint_2_outcome="not_evaluated",
        )
        return seal_result(
            checkpoint_2="not_evaluated",
            aggregate_outcome=outcome,
        )

    planner_inputs = checkpoint_1.planner_inputs
    gate_result = checkpoint_1.gate_result
    final_recipe_bytes = checkpoint_1.final_recipe_bytes
    if (
        planner_inputs is None
        or type(gate_result) is not ARTIFACTS.MechanicalGateResult
        or type(final_recipe_bytes) is not bytes
        or gate_result.final_recipe_bytes is not final_recipe_bytes
    ):
        raise ValueError("ready Checkpoint 1 has no exact accepted gate transition")
    sealed_recipe_bytes = (
        sealed_checkpoint.archive_dir / "planner" / "final_recipe.json"
    ).read_bytes()
    if sealed_recipe_bytes != final_recipe_bytes:
        raise ValueError("ready Checkpoint 1 recipe is not bound to its seal")

    def finish_pre_session_failure(
        locus: str,
        exc: Exception,
        *,
        handoff: ARTIFACTS.Lm9bcHandoff | None = None,
        loaded_recipe_bytes: bytes | None = None,
    ) -> JoinedProbeResult:
        failure = {
            "locus": locus,
            "exception_type": type(exc).__name__,
            "message": str(exc)[:2000],
        }
        return seal_result(
            checkpoint_2="inconclusive",
            aggregate_outcome="inconclusive",
            reason_codes=(f"pre_session_{locus}_failed",),
            handoff=handoff,
            loaded_recipe_bytes=loaded_recipe_bytes,
            pre_session_failure=failure,
        )

    try:
        handoff = ARTIFACTS.build_lm9bc_handoff(
            planner_inputs=planner_inputs,
            gate_result=gate_result,
            compiler_fixture_dir=compiler_fixture_dir,
            destination=handoff_destination,
        )
    except Exception as exc:
        return finish_pre_session_failure("handoff", exc)
    lm9bc_artifacts, lm9bc_probe = _load_lm9bc_modules()

    try:
        loaded_inputs = lm9bc_artifacts.load_frozen_inputs(handoff.fixture_dir)
    except Exception as exc:
        return finish_pre_session_failure("load_or_index", exc, handoff=handoff)
    loaded_recipe_bytes = getattr(loaded_inputs, "recipe_bytes", None)
    if loaded_recipe_bytes != final_recipe_bytes:
        return finish_pre_session_failure(
            "load_or_index",
            ValueError("LM9B-C loaded different recipe bytes"),
            handoff=handoff,
            loaded_recipe_bytes=loaded_recipe_bytes,
        )
    try:
        lm9bc_artifacts.render_compiler_request(loaded_inputs)
    except Exception as exc:
        return finish_pre_session_failure(
            "render",
            exc,
            handoff=handoff,
            loaded_recipe_bytes=loaded_recipe_bytes,
        )

    compiler_contacts = 0

    def counted_compiler_provider(request: dict[str, object]) -> object:
        nonlocal compiler_contacts
        compiler_contacts += 1
        return compiler_provider(request)

    try:
        lm9bc_result = lm9bc_probe.run_probe(
            run_root=compiler_run_root,
            fixture_dir=handoff.fixture_dir,
            compiler_provider=counted_compiler_provider,
            evaluator_provider=compiler_evaluator_provider,
            compiler_identity=compiler_identity,
            evaluator_identity=compiler_evaluator_identity,
            git_sha=git_sha,
        )
    except Exception as exc:
        if compiler_contacts == 0:
            return finish_pre_session_failure(
                "load_or_index_or_render",
                exc,
                handoff=handoff,
                loaded_recipe_bytes=loaded_recipe_bytes,
            )
        return seal_result(
            checkpoint_2="inconclusive",
            aggregate_outcome="inconclusive",
            reason_codes=("compiler_session_or_evidence_failure",),
            handoff=handoff,
            loaded_recipe_bytes=loaded_recipe_bytes,
        )

    result_loaded_bytes = getattr(getattr(lm9bc_result, "inputs", None), "recipe_bytes", None)
    if result_loaded_bytes != final_recipe_bytes:
        raise ValueError("unchanged LM9B-C run loaded different recipe bytes")
    checkpoint_2 = lm9bc_result.decision.outcome
    aggregate_outcome = ARTIFACTS.derive_joined_aggregate_outcome(
        checkpoint_1_classification=checkpoint_1.classification,
        checkpoint_2_outcome=checkpoint_2,
        compiler_session=lm9bc_result.compiler_session,
        evaluator_result=lm9bc_result.evaluator_result,
    )
    return seal_result(
        checkpoint_2=checkpoint_2,
        aggregate_outcome=aggregate_outcome,
        reason_codes=tuple(lm9bc_result.decision.reason_codes),
        handoff=handoff,
        loaded_recipe_bytes=result_loaded_bytes,
        lm9bc_result=lm9bc_result,
    )


__all__ = (
    "JoinedProbeResult",
    "PlannerCheckpointResult",
    "run_joined_probe",
    "run_planner_checkpoint",
)
