#!/usr/bin/env python3
"""Bounded governed-resolution checkpoint orchestration."""

from __future__ import annotations

import copy
import base64
import json
import sys
from dataclasses import dataclass
from pathlib import Path


_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _import_path in (_SCRIPTS_DIR, _MCP_SRC):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

import lm9b_p_governed_resolution_artifacts as ARTIFACTS
import lm9b_p_governed_resolution_support as SUPPORT
import lm9b_p_planner_recipe_transfer_artifacts as PLANNER_ARTIFACTS
import lm9b_p_planner_recipe_transfer_support as PLANNER_SUPPORT
import lm9b_p_readiness_contract as READINESS


@dataclass(frozen=True)
class ResolutionAttemptResult:
    classification: str | None
    planner_session: PLANNER_SUPPORT.PlannerSessionResult | None
    evaluator_result: PLANNER_SUPPORT.PlannerEvaluationResult | None
    isolation_result: SUPPORT.IsolationGateResult | None
    sealed_checkpoint: ARTIFACTS.SealedResolutionCheckpoint | None
    state: str


def run_resolution_attempt(**_kwargs: object) -> ResolutionAttemptResult:
    required = {
        "preflight",
        "invocation_binding",
        "readiness_record",
        "readiness_manifest",
        "head_sha",
        "now_iso",
        "credential_present",
        "planner_provider",
        "evaluator_provider",
    }
    if set(_kwargs) != required:
        raise ValueError("resolution attempt arguments are incomplete or contain extras")
    supplied = _kwargs["preflight"]
    if type(supplied) is not ARTIFACTS.VerifiedResolutionPreflight:
        raise TypeError("verified resolution preflight is required")
    preflight = ARTIFACTS.verify_resolution_preflight(
        supplied.archive_dir,
        expected_fingerprint=supplied.preflight_fingerprint,
    )
    head_sha = _kwargs["head_sha"]
    if head_sha != preflight.record["reviewed_commit_sha"]:
        raise ValueError("execution commit differs from resolution preflight")
    readiness_record = _kwargs["readiness_record"]
    readiness_manifest = _kwargs["readiness_manifest"]
    if type(readiness_record) is not dict:
        raise TypeError("readiness record must be an object")
    expected_manifest_fingerprint = preflight.record["instrument_contracts"][
        "readiness"
    ]["route_manifest_fingerprint"]
    expected_route_roles = preflight.record["instrument_contracts"]["readiness"][
        "route_role_projection"
    ]
    if (
        type(readiness_manifest) is not READINESS.RouteManifest
        or readiness_manifest.manifest_fingerprint
        != expected_manifest_fingerprint
        or ARTIFACTS.readiness_route_role_projection(readiness_manifest)
        != expected_route_roles
    ):
        raise ValueError(
            "resolution readiness route or role membership differs from preflight"
        )
    decision = READINESS.verify_launch_readiness(
        record=readiness_record,
        manifest=readiness_manifest,
        head_sha=head_sha,
        now_iso=_kwargs["now_iso"],
        credential_present=_kwargs["credential_present"],
    )
    if not decision.ok:
        raise ValueError("resolution readiness refused: " + "; ".join(decision.failures))
    expected_invocation = ARTIFACTS.build_resolution_invocation_binding(
        supplied_preflight_fingerprint=preflight.preflight_fingerprint,
        transmit=True,
        reviewed_commit_sha=head_sha,
        readiness_identity=readiness_record.get("record_fingerprint"),
        attempt_id=preflight.attempt.attempt_id,
        attempt_fingerprint=preflight.attempt.attempt_fingerprint,
    )
    ARTIFACTS.verify_resolution_invocation_binding(
        _kwargs["invocation_binding"], expected=expected_invocation
    )
    ARTIFACTS.require_clean_reviewed_checkout(
        ARTIFACTS._REPO_ROOT, preflight.record["reviewed_commit_sha"]
    )
    if preflight.attempt.destination.exists() or preflight.attempt.staging_path.exists():
        raise FileExistsError("resolution destination or staging already exists")
    ARTIFACTS.reserve_resolution_staging(preflight)

    planner_calls: list[dict[str, object]] = []
    planner_provider = _recording_provider(
        _kwargs["planner_provider"], planner_calls, role="planner"
    )
    inputs = preflight.instrument.inputs
    planner_session = PLANNER_SUPPORT.run_planner_session(
        provider=planner_provider,
        system_prompt=SUPPORT.REVISION_SYSTEM_PROMPT,
        user_prompt=preflight.instrument.initial_request.raw_bytes.decode("utf-8"),
        authority=inputs.current_authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    if planner_session.termination != "mechanically_accepted":
        statuses = [
            None
            if turn.gate_result is None
            else {
                "status": turn.gate_result.status,
                "diagnostics": [
                    {"code": row.code, "path": row.path, "message": row.message}
                    for row in turn.gate_result.diagnostics
                ],
            }
            for turn in planner_session.turns
        ]
        raise ValueError(
            "Task-1 walking witness requires an accepted Planner session: "
            f"{planner_session.termination}, gates={statuses}"
        )
    candidate_raw = planner_session.final_recipe_bytes
    assert candidate_raw is not None
    checkpoint_gate = PLANNER_SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=candidate_raw,
        authority=inputs.current_authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    accepted_turns = tuple(
        turn.gate_result
        for turn in planner_session.turns
        if turn.gate_result is not None
        and turn.gate_result.status == "mechanically_accepted"
    )
    if (
        checkpoint_gate.status != "mechanically_accepted"
        or checkpoint_gate.final_recipe_bytes != candidate_raw
        or len(accepted_turns) != 1
        or checkpoint_gate != accepted_turns[0]
    ):
        raise ValueError("independent checkpoint gate differs from Planner session")
    isolation = SUPPORT.evaluate_resolution_isolation(
        inputs=inputs,
        candidate_recipe_bytes=candidate_raw,
    )
    if isolation.status != "isolated":
        raise ValueError("Task-1 walking witness candidate failed isolation")

    rendered_evaluator = SUPPORT.render_planner_revision_evaluation_request(
        inputs,
        candidate_recipe_bytes=candidate_raw,
    )
    evaluator_request_bytes = (
        PLANNER_SUPPORT.build_planner_evaluator_provider_call_request(
            system_prompt=PLANNER_SUPPORT.PLANNER_EVALUATOR_SYSTEM_PROMPT,
            user_prompt=rendered_evaluator.raw_bytes.decode("utf-8"),
        )
    )
    evaluator_responses: list[PLANNER_SUPPORT.ProviderTurn] = []

    def evaluator_provider(request: dict[str, object]) -> object:
        response = _kwargs["evaluator_provider"](request)
        if type(response) is PLANNER_SUPPORT.ProviderTurn:
            evaluator_responses.append(response)
        return response

    evaluator_result = PLANNER_SUPPORT.run_planner_evaluation(
        provider=evaluator_provider,
        provider_call_request_bytes=evaluator_request_bytes,
    )
    if len(evaluator_responses) != 1:
        raise ValueError("Task-1 walking witness evaluator evidence is incomplete")
    classification = PLANNER_ARTIFACTS.derive_evaluated_recipe_classification(
        evaluator_result,
        final_recipe_bytes=candidate_raw,
    )
    if classification == "probe_candidate_blocked":
        raise ValueError("isolation-passing candidate retained an explicit blocker")
    if classification != "probe_candidate_ready":
        raise ValueError("Task-1 walking witness did not derive ready eligibility")
    sealed = ARTIFACTS.seal_task1_resolution_checkpoint(
        preflight=preflight,
        readiness_record=readiness_record,
        readiness_verified_at=_kwargs["now_iso"],
        planner_session=planner_session,
        planner_call_records=planner_calls,
        checkpoint_gate=checkpoint_gate,
        isolation_result=isolation,
        evaluator_turn=evaluator_responses[0],
        evaluator_request_bytes=evaluator_request_bytes,
        evaluator_result=evaluator_result,
        classification=classification,
    )
    return ResolutionAttemptResult(
        classification=classification,
        planner_session=planner_session,
        evaluator_result=evaluator_result,
        isolation_result=isolation,
        sealed_checkpoint=sealed,
        state="sealed",
    )


def _recording_provider(provider: object, ledger: list[dict[str, object]], *, role: str):
    def invoke(request: dict[str, object]) -> object:
        request_bytes = _canonical_bytes(copy.deepcopy(request))
        response = provider(request)
        ledger.append(
            {
                "call_index": len(ledger) + 1,
                "role": role,
                "request_raw_sha256": PLANNER_SUPPORT.sha256_prefixed(request_bytes),
                "canonical_request_json": request_bytes.decode("utf-8"),
                "raw_response_sha256": (
                    PLANNER_SUPPORT.sha256_prefixed(response.raw_response)
                    if type(response) is PLANNER_SUPPORT.ProviderTurn
                    else None
                ),
                "provider_raw_request_b64": (
                    base64.b64encode(response.raw_request).decode("ascii")
                    if type(response) is PLANNER_SUPPORT.ProviderTurn
                    else None
                ),
                "raw_response_b64": (
                    base64.b64encode(response.raw_response).decode("ascii")
                    if type(response) is PLANNER_SUPPORT.ProviderTurn
                    else None
                ),
                "assistant_message": (
                    PLANNER_SUPPORT._json_builtins(response.assistant_message)
                    if type(response) is PLANNER_SUPPORT.ProviderTurn
                    else None
                ),
                "usage": (
                    PLANNER_SUPPORT._json_builtins(response.usage)
                    if type(response) is PLANNER_SUPPORT.ProviderTurn
                    else None
                ),
                "provider_metadata": (
                    PLANNER_SUPPORT._json_builtins(response.provider_metadata)
                    if type(response) is PLANNER_SUPPORT.ProviderTurn
                    else None
                ),
            }
        )
        return response

    return invoke


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        PLANNER_SUPPORT._json_builtins(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


__all__ = ("ResolutionAttemptResult", "run_resolution_attempt")
