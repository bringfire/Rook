#!/usr/bin/env python3
"""Bounded governed-resolution checkpoint orchestration."""

from __future__ import annotations

import copy
import base64
import json
import sys
import threading
import time
from collections.abc import Callable, Mapping
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
    checkpoint_gate: PLANNER_SUPPORT.MechanicalGateResult | None
    candidate_recipe_bytes: bytes | None
    call_ledger: tuple[Mapping[str, object], ...]
    derived_stop_cause: str
    state: str


class _StagedCallLedger:
    """Persist immutable adapter-boundary requests before each dispatch."""

    def __init__(
        self,
        *,
        preflight: ARTIFACTS.VerifiedResolutionPreflight,
        readiness_record: Mapping[str, object],
        readiness_verified_at: str,
    ) -> None:
        self._preflight = preflight
        self._runtime = preflight.attempt.staging_path / ".resolution-runtime"
        self._calls = self._runtime / "calls"
        self._runtime.mkdir(parents=False, exist_ok=False)
        self._calls.mkdir(parents=False, exist_ok=False)
        self._rows: list[dict[str, object]] = []
        self._dispatch_lock = threading.Lock()
        self._role_open = {"planner": True, "planner_evaluator": True}
        attempt = {
            "schema": "rook.lm9b_p.governed_resolution_staged_attempt:v1",
            "attempt_id": preflight.attempt.attempt_id,
            "attempt_fingerprint": preflight.attempt.attempt_fingerprint,
            "canonical_destination": str(preflight.attempt.destination),
            "staging_path": str(preflight.attempt.staging_path),
        }
        readiness = {
            "schema": "rook.lm9b_p.governed_resolution_staged_readiness:v1",
            "record": PLANNER_SUPPORT._json_builtins(readiness_record),
            "verified_at": readiness_verified_at,
        }
        self._persist_and_reread(
            self._runtime / "preflight.json",
            (preflight.archive_dir / "record.json").read_bytes(),
        )
        self._persist_and_reread(
            self._runtime / "attempt.json", _canonical_bytes(attempt)
        )
        self._persist_and_reread(
            self._runtime / "readiness.json", _canonical_bytes(readiness)
        )
        self._persist_and_reread(
            self._runtime / "initial-request.json",
            preflight.instrument.initial_request.raw_bytes,
        )

    @property
    def has_unjoined_dispatch(self) -> bool:
        return any(row["terminal"] is False for row in self._rows)

    def role_dispatch_complete(self, role: str) -> bool:
        rows = [row for row in self._rows if row["role"] == role]
        return bool(rows) and all(row["terminal"] is True for row in rows)

    def close_role(self, role: str) -> None:
        with self._dispatch_lock:
            self._role_open[role] = False

    def wrap(
        self,
        provider: Callable[[dict[str, object]], object],
        *,
        role: str,
        materialize: Callable[[bytes], dict[str, object]],
    ) -> Callable[[dict[str, object]], object]:
        if role not in {"planner", "planner_evaluator"}:
            raise ValueError("unregistered resolution provider role")

        def invoke(request: dict[str, object]) -> object:
            request_bytes = _canonical_bytes(copy.deepcopy(request))
            # The role-specific materializer replays the code-owned builder and
            # rejects drift before the irreversible dispatch marker.
            materialize(request_bytes)
            call_index = len(self._rows)
            prefix = f"{call_index:02d}-{role}"
            request_path = self._calls / f"{prefix}-request.json"
            self._persist_and_reread(request_path, request_bytes)
            request_value = materialize(request_path.read_bytes())
            role_contract = self._preflight.record["instrument_contracts"][
                "planner" if role == "planner" else "evaluator"
            ]
            with self._dispatch_lock:
                if not self._role_open[role]:
                    raise RuntimeError("resolution role dispatch is closed")
                marker = {
                    "schema": "rook.lm9b_p.governed_resolution_dispatch_started:v1",
                    "call_index": call_index,
                    "role": role,
                    "request_raw_sha256": PLANNER_SUPPORT.sha256_prefixed(request_bytes),
                    "preceding_transcript_fingerprint": PLANNER_SUPPORT.fingerprint(
                        request_value["messages"]
                    ),
                    "provider_timeout_s": request_value["provider_timeout_s"],
                    "role_contract_fingerprint": PLANNER_SUPPORT.fingerprint(
                        role_contract
                    ),
                }
                marker_raw = _canonical_bytes(marker)
                self._persist_and_reread(
                    self._calls / f"{prefix}-dispatch_started.json", marker_raw
                )
                row: dict[str, object] = {
                    **marker,
                    "dispatch_marker_raw_sha256": PLANNER_SUPPORT.sha256_prefixed(
                        marker_raw
                    ),
                    "canonical_request_json": request_bytes.decode("utf-8"),
                    "provider_claimed_raw_request_b64": None,
                    "raw_response_b64": None,
                    "raw_response_sha256": None,
                    "assistant_message": None,
                    "usage": None,
                    "provider_metadata": None,
                    "outcome": "dispatch_started",
                    "exception_type": None,
                    "failure_type": None,
                    "elapsed_ms": None,
                    "terminal": False,
                }
                self._rows.append(row)
            started = time.monotonic()
            try:
                response = provider(request_value)
            except BaseException as exc:
                row["outcome"] = "raised"
                row["exception_type"] = type(exc).__name__
                row["failure_type"] = getattr(exc, "failure_type", None)
                row["elapsed_ms"] = max(
                    0, int((time.monotonic() - started) * 1000)
                )
                row["terminal"] = True
                raise
            row["outcome"] = "returned"
            row["elapsed_ms"] = max(
                0, int((time.monotonic() - started) * 1000)
            )
            row["terminal"] = True
            if type(response) is PLANNER_SUPPORT.ProviderTurn:
                row.update(
                    {
                        "provider_claimed_raw_request_b64": base64.b64encode(
                            response.raw_request
                        ).decode("ascii"),
                        "raw_response_b64": base64.b64encode(
                            response.raw_response
                        ).decode("ascii"),
                        "raw_response_sha256": PLANNER_SUPPORT.sha256_prefixed(
                            response.raw_response
                        ),
                        "assistant_message": PLANNER_SUPPORT._json_builtins(
                            response.assistant_message
                        ),
                        "usage": PLANNER_SUPPORT._json_builtins(response.usage),
                        "provider_metadata": PLANNER_SUPPORT._json_builtins(
                            response.provider_metadata
                        ),
                    }
                )
            return response

        return invoke

    def frozen_rows(self) -> tuple[Mapping[str, object], ...]:
        return tuple(copy.deepcopy(self._rows))

    def remove_runtime_after_capture(self) -> None:
        for path in sorted(self._calls.iterdir()):
            path.unlink()
        self._calls.rmdir()
        for name in (
            "attempt.json",
            "initial-request.json",
            "preflight.json",
            "readiness.json",
        ):
            (self._runtime / name).unlink()
        self._runtime.rmdir()

    @staticmethod
    def _persist_and_reread(path: Path, raw: bytes) -> None:
        path.write_bytes(raw)
        if path.read_bytes() != raw:
            raise ValueError("staged resolution evidence write verification failed")


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
    expected_route_identity = preflight.record["instrument_contracts"]["readiness"][
        "route_identity_projection"
    ]
    if (
        type(readiness_manifest) is not READINESS.RouteManifest
        or readiness_manifest.manifest_fingerprint
        != expected_manifest_fingerprint
        or ARTIFACTS.readiness_route_identity_projection(readiness_manifest)
        != expected_route_identity
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
    ledger = _StagedCallLedger(
        preflight=preflight,
        readiness_record=readiness_record,
        readiness_verified_at=_kwargs["now_iso"],
    )
    planner_provider = ledger.wrap(
        _kwargs["planner_provider"],
        role="planner",
        materialize=PLANNER_SUPPORT.materialize_planner_provider_call_request,
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
    ledger.close_role("planner")
    planner_stop = _planner_stop_cause(planner_session)
    if planner_session.termination in {"provider_failure", "timeout"}:
        if (
            ledger.has_unjoined_dispatch
            or not ledger.role_dispatch_complete("planner")
        ):
            return _attempt_result(
                preflight=preflight,
                classification=None,
                planner_session=planner_session,
                evaluator_result=None,
                isolation_result=None,
                checkpoint_gate=None,
                candidate_recipe_bytes=None,
                call_ledger=ledger.frozen_rows(),
                derived_stop_cause="ambiguous_planner_dispatch",
                state="post_dispatch_unsealed",
            )
        return _attempt_result(
            preflight=preflight,
            classification="probe_inconclusive",
            planner_session=planner_session,
            evaluator_result=None,
            isolation_result=None,
            checkpoint_gate=None,
            candidate_recipe_bytes=None,
            call_ledger=ledger.frozen_rows(),
            derived_stop_cause=planner_stop,
        )
    if planner_session.termination == "mechanically_rejected":
        return _attempt_result(
            preflight=preflight,
            classification="probe_mechanically_rejected",
            planner_session=planner_session,
            evaluator_result=None,
            isolation_result=None,
            checkpoint_gate=None,
            candidate_recipe_bytes=None,
            call_ledger=ledger.frozen_rows(),
            derived_stop_cause=planner_stop,
        )
    if planner_session.termination != "mechanically_accepted":
        raise ValueError("Planner session returned an unknown termination")
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
    if isolation.status == "isolation_rejected":
        return _attempt_result(
            preflight=preflight,
            classification="probe_resolution_isolation_failure",
            planner_session=planner_session,
            evaluator_result=None,
            isolation_result=isolation,
            checkpoint_gate=checkpoint_gate,
            candidate_recipe_bytes=candidate_raw,
            call_ledger=ledger.frozen_rows(),
            derived_stop_cause="isolation_rejected",
        )
    if isolation.status != "isolated":
        raise ValueError("resolution isolation returned an unknown status")

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

    staged_evaluator_provider = ledger.wrap(
        evaluator_provider,
        role="planner_evaluator",
        materialize=(
            PLANNER_SUPPORT.materialize_planner_evaluator_provider_call_request
        ),
    )
    evaluator_result = PLANNER_SUPPORT.run_planner_evaluation(
        provider=staged_evaluator_provider,
        provider_call_request_bytes=evaluator_request_bytes,
    )
    ledger.close_role("planner_evaluator")
    if (
        not evaluator_result.quiescent
        or ledger.has_unjoined_dispatch
        or not ledger.role_dispatch_complete("planner_evaluator")
    ):
        return _attempt_result(
            preflight=preflight,
            classification=None,
            planner_session=planner_session,
            evaluator_result=evaluator_result,
            isolation_result=isolation,
            checkpoint_gate=checkpoint_gate,
            candidate_recipe_bytes=candidate_raw,
            call_ledger=ledger.frozen_rows(),
            derived_stop_cause="ambiguous_evaluator_dispatch",
            state="post_dispatch_unsealed",
        )
    classification = PLANNER_ARTIFACTS.derive_evaluated_recipe_classification(
        evaluator_result,
        final_recipe_bytes=candidate_raw,
    )
    if classification == "probe_candidate_blocked":
        raise ValueError("isolation-passing candidate retained an explicit blocker")
    if classification not in {
        "probe_candidate_ready",
        "probe_planner_failure",
        "probe_inconclusive",
    }:
        raise ValueError("shared classifier returned an invalid resolution outcome")
    stop_cause = _evaluator_stop_cause(evaluator_result)
    call_ledger = ledger.frozen_rows()
    if classification != "probe_candidate_ready":
        return _attempt_result(
            preflight=preflight,
            classification=classification,
            planner_session=planner_session,
            evaluator_result=evaluator_result,
            isolation_result=isolation,
            checkpoint_gate=checkpoint_gate,
            candidate_recipe_bytes=candidate_raw,
            call_ledger=call_ledger,
            derived_stop_cause=stop_cause,
        )
    if len(evaluator_responses) != 1:
        raise ValueError("ready evaluator evidence is incomplete")
    ledger.remove_runtime_after_capture()
    sealed = ARTIFACTS.seal_task1_resolution_checkpoint(
        preflight=preflight,
        readiness_record=readiness_record,
        readiness_verified_at=_kwargs["now_iso"],
        planner_session=planner_session,
        planner_call_records=[
            row for row in call_ledger if row["role"] == "planner"
        ],
        checkpoint_gate=checkpoint_gate,
        isolation_result=isolation,
        evaluator_turn=evaluator_responses[0],
        evaluator_request_bytes=evaluator_request_bytes,
        evaluator_result=evaluator_result,
        classification=classification,
    )
    return _attempt_result(
        preflight=preflight,
        classification=classification,
        planner_session=planner_session,
        evaluator_result=evaluator_result,
        isolation_result=isolation,
        checkpoint_gate=checkpoint_gate,
        candidate_recipe_bytes=candidate_raw,
        call_ledger=call_ledger,
        derived_stop_cause=stop_cause,
        sealed_checkpoint=sealed,
        state="sealed",
    )


def _attempt_result(
    *,
    preflight: ARTIFACTS.VerifiedResolutionPreflight,
    classification: str | None,
    planner_session: PLANNER_SUPPORT.PlannerSessionResult,
    evaluator_result: PLANNER_SUPPORT.PlannerEvaluationResult | None,
    isolation_result: SUPPORT.IsolationGateResult | None,
    checkpoint_gate: PLANNER_SUPPORT.MechanicalGateResult | None,
    candidate_recipe_bytes: bytes | None,
    call_ledger: tuple[Mapping[str, object], ...],
    derived_stop_cause: str,
    state: str = "terminal_evidence_complete",
    sealed_checkpoint: ARTIFACTS.SealedResolutionCheckpoint | None = None,
) -> ResolutionAttemptResult:
    result = ResolutionAttemptResult(
        classification=classification,
        planner_session=planner_session,
        evaluator_result=evaluator_result,
        isolation_result=isolation_result,
        sealed_checkpoint=sealed_checkpoint,
        checkpoint_gate=checkpoint_gate,
        candidate_recipe_bytes=candidate_recipe_bytes,
        call_ledger=call_ledger,
        derived_stop_cause=derived_stop_cause,
        state=state,
    )
    if state != "post_dispatch_unsealed":
        ARTIFACTS.verify_resolution_call_ledger(
            preflight=preflight,
            planner_session=planner_session,
            evaluator_result=evaluator_result,
            isolation_result=isolation_result,
            classification=classification,
            candidate_recipe_bytes=candidate_recipe_bytes,
            call_ledger=call_ledger,
            derived_stop_cause=derived_stop_cause,
        )
    return result


def _planner_stop_cause(
    session: PLANNER_SUPPORT.PlannerSessionResult,
) -> str:
    if session.termination == "mechanically_accepted":
        return "mechanically_accepted"
    if session.termination == "provider_failure":
        return "planner_provider_failure"
    if session.termination == "timeout":
        return "planner_terminal_timeout"
    if session.termination != "mechanically_rejected":
        raise ValueError("unknown Planner termination")
    total_tokens = 0
    total_cost = 0.0
    cost_complete = True
    for turn in session.turns:
        tokens, cost, complete = PLANNER_SUPPORT._planner_usage_values(turn.usage)
        total_tokens += tokens
        total_cost += cost
        cost_complete = cost_complete and complete
    if total_tokens >= PLANNER_SUPPORT.PLANNER_TOKEN_STOP_THRESHOLD:
        return "token_stop"
    if cost_complete and total_cost >= PLANNER_SUPPORT.PLANNER_COST_STOP_THRESHOLD_USD:
        return "cost_stop"
    if len(session.turns) == PLANNER_SUPPORT.PLANNER_MAX_TURNS:
        return "max_turns"
    raise ValueError("mechanically rejected session has no derivable stop cause")


def _evaluator_stop_cause(
    result: PLANNER_SUPPORT.PlannerEvaluationResult,
) -> str:
    if result.termination == "valid_recommendation":
        if result.recommendation == "semantically_faithful":
            return "semantic_faithful"
        if result.recommendation == "semantically_unfaithful":
            return "semantic_unfaithful"
        if result.recommendation == "evaluation_inconclusive":
            return "evaluation_inconclusive"
    if result.termination == "malformed":
        return "evaluator_malformed"
    if result.termination == "provider_failure":
        return "evaluator_provider_failure"
    if result.termination == "timeout":
        return "evaluator_terminal_timeout"
    raise ValueError("unknown evaluator termination")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        PLANNER_SUPPORT._json_builtins(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


__all__ = ("ResolutionAttemptResult", "run_resolution_attempt")
