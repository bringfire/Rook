#!/usr/bin/env python3
"""No-contact preflight for the LM9B-P evaluator-only continuation."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Mapping, Sequence


_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _import_path in (_SCRIPTS_DIR, _MCP_SRC):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

import lm9b_p_evaluator_only_continuation_artifacts as CONT_ARTIFACTS
import lm9b_p_planner_recipe_transfer_artifacts as PLANNER_ARTIFACTS
import lm9b_p_planner_recipe_transfer_probe as PLANNER_PROBE
import lm9b_p_planner_recipe_transfer_support as SUPPORT
import lm9b_p_readiness_contract as READINESS
from rook.agent.model_profiles import api_key_env_for_model


CORRECTED_RUBRIC_PATH = (
    _SCRIPTS_DIR / "lm9b_p_fixtures" / "planner_evaluation_rubric.json"
)


@dataclass(frozen=True)
class PreflightConfig:
    output_dir: Path
    reviewed_commit_sha: str
    attempt_id: str
    derivative_root: Path
    destination: Path
    launch_eligibility: Literal[
        "development_non_operational",
        "operator_review_candidate",
    ]


@dataclass(frozen=True)
class ExecutionConfig:
    preflight_dir: Path
    expected_preflight_fingerprint: str
    readiness_record: Path
    credential_preflight: Path
    transmit: bool


@dataclass(frozen=True)
class ExecutionSnapshot:
    preflight: CONT_ARTIFACTS.VerifiedContinuationPreflight
    source: CONT_ARTIFACTS.VerifiedHistoricalSource
    instrument: CONT_ARTIFACTS.ContinuationInstrument
    attempt: CONT_ARTIFACTS.AttemptBinding
    preflight_record_bytes: bytes
    allowed_delta_bytes: bytes
    mechanical_gate_bytes: bytes
    rendered_request_bytes: bytes
    provider_request_bytes: bytes
    readiness_record_bytes: bytes
    credential_preflight_bytes: bytes
    invocation_binding_bytes: bytes


@dataclass(frozen=True)
class PreparedExecution:
    snapshot: ExecutionSnapshot
    provider: object


def _git_checkout_state() -> tuple[str, bool]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return head, not bool(status.strip())


def _build_evaluator_provider() -> object:
    """Construct the existing evaluator adapter; preflight never calls this."""

    return PLANNER_PROBE.build_planner_evaluator_provider(
        model=CONT_ARTIFACTS.EVALUATOR_MODEL,
        temperature=CONT_ARTIFACTS.EVALUATOR_TEMPERATURE,
    )


def emit_no_contact_preflight(
    config: PreflightConfig,
) -> CONT_ARTIFACTS.VerifiedContinuationPreflight:
    head, clean = _git_checkout_state()
    if not clean or head != config.reviewed_commit_sha:
        raise RuntimeError("preflight requires the clean reviewed commit")
    source = CONT_ARTIFACTS.verify_historical_source()
    corrected_rubric_bytes = CORRECTED_RUBRIC_PATH.read_bytes()
    instrument = CONT_ARTIFACTS.assemble_continuation_instrument(
        source,
        corrected_rubric_bytes=corrected_rubric_bytes,
        reviewed_commit_sha=head,
    )
    attempt = CONT_ARTIFACTS.bind_attempt(
        instrument_fingerprint=instrument.instrument_fingerprint,
        attempt_id=config.attempt_id,
        derivative_root=config.derivative_root,
        destination=config.destination,
    )
    return CONT_ARTIFACTS.write_preflight_archive(
        output_dir=config.output_dir,
        reviewed_commit_sha=head,
        launch_eligibility=config.launch_eligibility,
        instrument=instrument,
        attempt=attempt,
    )


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _object(raw: bytes, label: str) -> dict[str, object]:
    value = SUPPORT.parse_archive_json(raw)
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def _stable_read(path: Path, label: str) -> bytes:
    first = Path(path).read_bytes()
    second = Path(path).read_bytes()
    if first != second:
        raise ValueError(f"{label} changed while being read")
    return first


def _readiness_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gate_value(gate: SUPPORT.MechanicalGateResult) -> dict[str, object]:
    return {
        "schema": "rook.lm9b_p.evaluator_continuation_mechanical_gate:v1",
        "status": gate.status,
        "diagnostics": [
            {"code": row.code, "path": row.path, "message": row.message}
            for row in gate.diagnostics
        ],
        "final_recipe_raw_sha256": (
            SUPPORT.sha256_prefixed(gate.final_recipe_bytes)
            if gate.final_recipe_bytes is not None
            else None
        ),
        "recipe_value_fingerprint": gate.recipe_value_fingerprint,
        "ratified_recipe_fingerprint": gate.ratified_recipe_fingerprint,
        "historical_recipe_fingerprint": gate.historical_recipe_fingerprint,
    }


def _verify_pre_dispatch(config: ExecutionConfig) -> PreparedExecution:
    if config.transmit is not True:
        raise RuntimeError("continuation execution requires explicit transmit")
    preflight = CONT_ARTIFACTS.verify_preflight_archive(
        config.preflight_dir,
        expected_preflight_fingerprint=config.expected_preflight_fingerprint,
    )
    if preflight.record["launch_eligibility"] != "operator_review_candidate":
        raise RuntimeError("development preflight is not eligible for execution")
    head, clean = _git_checkout_state()
    if not clean or head != preflight.record["reviewed_commit_sha"]:
        raise RuntimeError("execution requires the clean reviewed commit")

    source = CONT_ARTIFACTS.verify_historical_source()
    if dict(source.identity_value) != preflight.record["source"]:
        raise ValueError("historical source no longer matches the preflight")
    corrected_rubric_bytes = _stable_read(
        CORRECTED_RUBRIC_PATH,
        "corrected evaluator rubric",
    )
    instrument = CONT_ARTIFACTS.assemble_continuation_instrument(
        source,
        corrected_rubric_bytes=corrected_rubric_bytes,
        reviewed_commit_sha=head,
    )
    preflight_instrument = preflight.record["instrument"]
    if not isinstance(preflight_instrument, Mapping):
        raise ValueError("preflight instrument identity is invalid")
    if (
        instrument.instrument_fingerprint != preflight.instrument_fingerprint
        or dict(instrument.protocol_identity)
        != preflight_instrument["protocol_identity"]
        or instrument.rendered_request.raw_bytes != preflight.rendered_request_bytes
        or instrument.provider_call_request_bytes
        != preflight.provider_call_request_bytes
    ):
        raise ValueError("current evaluator instrument differs from the preflight")

    preflight_record_bytes = _stable_read(
        preflight.archive_dir / "record.json", "preflight record"
    )
    allowed_delta_bytes = _stable_read(
        preflight.archive_dir / "allowed-delta-manifest.json",
        "allowed delta manifest",
    )
    mechanical_gate_bytes = _stable_read(
        preflight.archive_dir / "mechanical-gate.json",
        "mechanical gate",
    )
    rendered_request_bytes = _stable_read(
        preflight.archive_dir / "rendered-evaluator-request.json",
        "rendered evaluator request",
    )
    provider_request_bytes = _stable_read(
        preflight.archive_dir / "provider-call-request.json",
        "provider-call request",
    )
    expected_delta = {
        "schema": CONT_ARTIFACTS.ALLOWED_DELTA_SCHEMA_ID,
        "rows": [dict(row) for row in instrument.allowed_delta_rows],
    }
    if _object(allowed_delta_bytes, "allowed delta manifest") != expected_delta:
        raise ValueError("allowed delta manifest differs from verified inputs")
    if _object(mechanical_gate_bytes, "mechanical gate") != _gate_value(
        instrument.gate_result
    ):
        raise ValueError("mechanical gate differs from independent recomputation")
    if (
        rendered_request_bytes != instrument.rendered_request.raw_bytes
        or provider_request_bytes != instrument.provider_call_request_bytes
    ):
        raise ValueError("preflight request bytes differ from current construction")
    SUPPORT.materialize_planner_evaluator_provider_call_request(
        provider_request_bytes
    )

    readiness_record_bytes = _stable_read(
        config.readiness_record,
        "readiness record",
    )
    credential_preflight_bytes = _stable_read(
        config.credential_preflight,
        "credential preflight",
    )
    readiness_record = _object(readiness_record_bytes, "readiness record")
    credential_preflight = _object(
        credential_preflight_bytes,
        "credential preflight",
    )
    if set(credential_preflight) != {"credential_present"} or not isinstance(
        credential_preflight["credential_present"], dict
    ):
        raise ValueError("credential preflight shape is invalid")
    manifest = READINESS.derive_routes(
        READINESS.role_routes_from_models(
            {"planner_evaluator": CONT_ARTIFACTS.EVALUATOR_MODEL}
        ),
        api_key_env_for_model,
    )
    current_presence = {
        route.route_fingerprint: any(
            bool(os.environ.get(name)) for name in route.credential_source
        )
        for route in manifest.routes
    }
    if credential_preflight["credential_present"] != current_presence:
        raise RuntimeError("credential presence differs from readiness evidence")
    readiness_decision = READINESS.verify_launch_readiness(
        record=readiness_record,
        manifest=manifest,
        head_sha=head,
        now_iso=_readiness_now_iso(),
        credential_present=current_presence,
    )
    if not readiness_decision.ok:
        raise RuntimeError(
            "readiness gate refused: " + "; ".join(readiness_decision.failures)
        )

    provider = _build_evaluator_provider()
    provider_identity = getattr(provider, "identity", None)
    if (
        getattr(provider, "model", None) != CONT_ARTIFACTS.EVALUATOR_MODEL
        or getattr(provider, "temperature", None)
        != CONT_ARTIFACTS.EVALUATOR_TEMPERATURE
        or getattr(provider, "profile_identity", None)
        != CONT_ARTIFACTS.PROVIDER_PROFILE_ID
        or not isinstance(provider_identity, Mapping)
        or provider_identity.get("adapter_path") != "litellm.completion"
        or provider_identity.get("model") != CONT_ARTIFACTS.EVALUATOR_MODEL
        or provider_identity.get("profile_identity")
        != CONT_ARTIFACTS.PROVIDER_PROFILE_ID
        or provider_identity.get("temperature")
        != CONT_ARTIFACTS.EVALUATOR_TEMPERATURE
    ):
        raise RuntimeError("constructed evaluator adapter identity mismatch")

    attempt = CONT_ARTIFACTS.bind_attempt(
        instrument_fingerprint=instrument.instrument_fingerprint,
        attempt_id=preflight.attempt_id,
        derivative_root=preflight.derivative_root,
        destination=preflight.destination,
    )
    if (
        attempt.attempt_fingerprint != preflight.attempt_fingerprint
        or attempt.staging_path != preflight.staging_path
    ):
        raise ValueError("execution attempt identity differs from preflight")
    second_preflight = CONT_ARTIFACTS.verify_preflight_archive(
        config.preflight_dir,
        expected_preflight_fingerprint=config.expected_preflight_fingerprint,
    )
    if second_preflight != preflight:
        raise ValueError("preflight changed during final verification")
    invocation_binding = _json_bytes(
        {
            "schema": "rook.lm9b_p.evaluator.continuation_invocation_binding:v1",
            "supplied_preflight_fingerprint": config.expected_preflight_fingerprint,
            "transmit": True,
            "reviewed_commit_sha": head,
            "readiness_record_fingerprint": readiness_record.get(
                "record_fingerprint"
            ),
            "attempt_id": preflight.attempt_id,
            "attempt_fingerprint": preflight.attempt_fingerprint,
        }
    )
    snapshot = ExecutionSnapshot(
        preflight=preflight,
        source=source,
        instrument=instrument,
        attempt=attempt,
        preflight_record_bytes=preflight_record_bytes,
        allowed_delta_bytes=allowed_delta_bytes,
        mechanical_gate_bytes=mechanical_gate_bytes,
        rendered_request_bytes=rendered_request_bytes,
        provider_request_bytes=provider_request_bytes,
        readiness_record_bytes=readiness_record_bytes,
        credential_preflight_bytes=credential_preflight_bytes,
        invocation_binding_bytes=invocation_binding,
    )
    return PreparedExecution(snapshot=snapshot, provider=provider)


def _cleanup_unconsumed_staging(snapshot: ExecutionSnapshot) -> None:
    staging = snapshot.attempt.staging_path.resolve()
    root = snapshot.attempt.derivative_root.resolve()
    marker = staging / "dispatch/dispatch-started.json"
    if staging.parent != root or marker.exists():
        raise RuntimeError("refusing to clean a consumed or escaped staging path")
    if staging.exists():
        shutil.rmtree(staging)


def execute_continuation(
    config: ExecutionConfig,
) -> CONT_ARTIFACTS.SealedDerivative | CONT_ARTIFACTS.PostDispatchUnsealed:
    prepared = _verify_pre_dispatch(config)
    snapshot = prepared.snapshot
    staging = CONT_ARTIFACTS.reserve_staging(snapshot.attempt)
    dispatch_started = False
    attempt = PLANNER_ARTIFACTS.ProviderAttemptEvidence(
        provider_request_bytes=snapshot.provider_request_bytes
    )

    def recorded_provider(request: dict[str, object]) -> SUPPORT.ProviderTurn:
        started_at = time.perf_counter()
        try:
            turn = prepared.provider(request)
        except BaseException as exc:
            attempt.record_exception(exc, started_at)
            raise
        attempt.record_return(turn, started_at)
        return turn

    try:
        CONT_ARTIFACTS.write_static_derivative_snapshot(
            staging=staging,
            source=snapshot.source,
            instrument=snapshot.instrument,
            preflight_record_bytes=snapshot.preflight_record_bytes,
            allowed_delta_bytes=snapshot.allowed_delta_bytes,
            mechanical_gate_bytes=snapshot.mechanical_gate_bytes,
            rendered_request_bytes=snapshot.rendered_request_bytes,
            provider_request_bytes=snapshot.provider_request_bytes,
            invocation_binding_bytes=snapshot.invocation_binding_bytes,
            readiness_record_bytes=snapshot.readiness_record_bytes,
            credential_preflight_bytes=snapshot.credential_preflight_bytes,
        )
        staged_request_bytes = (
            staging / "preflight/provider-call-request.json"
        ).read_bytes()
        if staged_request_bytes != snapshot.provider_request_bytes:
            raise ValueError("staged provider request differs from the snapshot")
        materialized_request = (
            SUPPORT.materialize_planner_evaluator_provider_call_request(
                staged_request_bytes
            )
        )
        CONT_ARTIFACTS.write_dispatch_started(
            staging=staging,
            attempt_id=snapshot.preflight.attempt_id,
            attempt_fingerprint=snapshot.preflight.attempt_fingerprint,
            provider_call_request_bytes=staged_request_bytes,
        )
        dispatch_started = True
        evaluator = SUPPORT.run_planner_evaluation(
            provider=recorded_provider,
            provider_call_request_bytes=staged_request_bytes,
            materialized_request=materialized_request,
        )
        if evaluator.quiescent is not True:
            return CONT_ARTIFACTS.retain_post_dispatch_unsealed(
                staging=staging,
                preflight_fingerprint=snapshot.preflight.preflight_fingerprint,
                instrument_fingerprint=snapshot.instrument.instrument_fingerprint,
                attempt_id=snapshot.preflight.attempt_id,
                attempt_fingerprint=snapshot.preflight.attempt_fingerprint,
                failure_locus="evaluator_not_quiescent",
            )
        if attempt.outcome not in {"returned", "raised"}:
            raise ValueError("evaluator adapter entry was not completely captured")
        turn = attempt.provider_turn
        if turn is not None:
            metadata = getattr(turn, "provider_metadata", None)
            if (
                not isinstance(metadata, Mapping)
                or metadata.get("model_identity")
                != CONT_ARTIFACTS.EVALUATOR_MODEL
                or metadata.get("profile_identity")
                != CONT_ARTIFACTS.PROVIDER_PROFILE_ID
            ):
                raise ValueError("returned evaluator provider identity mismatch")
        classification = PLANNER_ARTIFACTS.derive_evaluated_recipe_classification(
            evaluator,
            final_recipe_bytes=snapshot.source.final_recipe_bytes,
        )
        return CONT_ARTIFACTS.seal_derivative_archive(
            staging=staging,
            destination=snapshot.attempt.destination,
            preflight=snapshot.preflight,
            instrument=snapshot.instrument,
            evaluator=evaluator,
            attempt=attempt,
            classification=classification,
        )
    except BaseException as exc:
        if dispatch_started or (
            staging / "dispatch/dispatch-started.json"
        ).exists():
            retained = CONT_ARTIFACTS.retain_post_dispatch_unsealed(
                staging=staging,
                preflight_fingerprint=snapshot.preflight.preflight_fingerprint,
                instrument_fingerprint=snapshot.instrument.instrument_fingerprint,
                attempt_id=snapshot.preflight.attempt_id,
                attempt_fingerprint=snapshot.preflight.attempt_fingerprint,
                failure_locus="post_dispatch_evidence_or_seal",
                exception=exc,
            )
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            return retained
        _cleanup_unconsumed_staging(snapshot)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LM9B-P evaluator-only derivative continuation"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser(
        "preflight",
        help="emit a content-addressed preflight without provider contact",
    )
    preflight.add_argument("--output-dir", type=Path, required=True)
    preflight.add_argument("--reviewed-commit-sha", required=True)
    preflight.add_argument("--attempt-id", required=True)
    preflight.add_argument("--derivative-root", type=Path, required=True)
    preflight.add_argument("--destination", type=Path, required=True)
    eligibility = preflight.add_mutually_exclusive_group(required=True)
    eligibility.add_argument("--development-witness", action="store_true")
    eligibility.add_argument("--operator-review-candidate", action="store_true")

    verify = subparsers.add_parser(
        "verify-preflight",
        help="verify a closed preflight archive",
    )
    verify.add_argument("--preflight-dir", type=Path, required=True)
    verify.add_argument("--expected-fingerprint", required=True)

    execute = subparsers.add_parser(
        "execute",
        help="consume one operator-review preflight after fresh readiness",
    )
    execute.add_argument("--preflight-dir", type=Path, required=True)
    execute.add_argument("--expected-preflight-fingerprint", required=True)
    execute.add_argument("--readiness-record", type=Path, required=True)
    execute.add_argument("--credential-preflight", type=Path, required=True)
    execute.add_argument("--transmit", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "preflight":
        launch_eligibility = (
            "operator_review_candidate"
            if args.operator_review_candidate
            else "development_non_operational"
        )
        verified = emit_no_contact_preflight(
            PreflightConfig(
                output_dir=args.output_dir,
                reviewed_commit_sha=args.reviewed_commit_sha,
                attempt_id=args.attempt_id,
                derivative_root=args.derivative_root,
                destination=args.destination,
                launch_eligibility=launch_eligibility,
            )
        )
    elif args.command == "verify-preflight":
        verified = CONT_ARTIFACTS.verify_preflight_archive(
            args.preflight_dir,
            expected_preflight_fingerprint=args.expected_fingerprint,
        )
    elif args.command == "execute":
        result = execute_continuation(
            ExecutionConfig(
                preflight_dir=args.preflight_dir,
                expected_preflight_fingerprint=(
                    args.expected_preflight_fingerprint
                ),
                readiness_record=args.readiness_record,
                credential_preflight=args.credential_preflight,
                transmit=args.transmit,
            )
        )
        if isinstance(result, CONT_ARTIFACTS.SealedDerivative):
            payload = {
                "state": result.state,
                "archive_dir": str(result.archive_dir),
                "derivative_archive_identity": result.derivative_archive_identity,
                "classification": result.classification,
            }
        else:
            payload = {
                "state": result.state,
                "staging_dir": str(result.staging_dir),
                "attempt_fingerprint": result.attempt_fingerprint,
                "classification": None,
            }
        print(json.dumps(payload, sort_keys=True))
        return 0
    else:  # pragma: no cover - argparse closes this vocabulary.
        raise AssertionError(f"unsupported command: {args.command}")
    print(
        json.dumps(
            {
                "preflight_fingerprint": verified.preflight_fingerprint,
                "instrument_fingerprint": verified.instrument_fingerprint,
                "attempt_fingerprint": verified.attempt_fingerprint,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = (
    "CORRECTED_RUBRIC_PATH",
    "ExecutionConfig",
    "ExecutionSnapshot",
    "PreflightConfig",
    "_build_evaluator_provider",
    "_git_checkout_state",
    "emit_no_contact_preflight",
    "execute_continuation",
    "main",
)
