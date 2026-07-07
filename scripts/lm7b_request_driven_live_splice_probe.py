#!/usr/bin/env python
"""LM7B request-driven live worker splice probe.

LM7B validates the canonical LM7A PlannerWorkerContractRequest, materializes
its workflow contract and worker-visible source routing, then drives the frozen
one-turn LM6 worker splice with that provenance head.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _path in (str(_SCRIPT_DIR), str(_REPO_ROOT), str(_MCP_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from lm6a_live_worker_splice_probe import (  # noqa: E402
    DEFAULT_ENDPOINT,
    DEFAULT_EXCERPT_CHARS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_S,
)
from rook.agent.planner_worker_contract_request import (  # noqa: E402
    DESIRED_OUTPUT_VALUE_INTENT_ID,
    LM7A_TEMPLATE_ID,
    PLANNER_INTENT_SOURCE_PATH,
    PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
    materialize_planner_worker_contract_request,
)
from rook.agent.workflow_validate import (  # noqa: E402
    validate_planner_worker_contract_request,
)


SCRIPT_SCHEMA = "rook.lm7b_request_driven_live_splice_probe:v1"
PLANNER_REQUEST_SOURCE = "script_local_canonical_lm7a_request"
DECISIONS = {
    "accepted",
    "rejected",
    "worker_declined",
    "gate_failed",
    "publication_failed",
    "rejected_by_validate",
}


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM7B request-driven live worker splice probe."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--excerpt-chars", type=int, default=DEFAULT_EXCERPT_CHARS)
    parser.add_argument("--run-dir", default="probe_runs")
    return parser.parse_args(argv)


def _canonical_planner_request() -> dict[str, Any]:
    return {
        "schema": PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
        "template_id": LM7A_TEMPLATE_ID,
        "initial_params": {
            "create_script": {
                "pins_out": ["A:double"],
            },
        },
        "routing_delta": {
            "enable_routes": [],
            "disable_routes": [],
            "set_required": {},
            "add_unresolved_intent_routes": [
                {
                    "route_id": "missing_desired_output_value",
                    "source_class": "planner_user_intent",
                    "source_path": PLANNER_INTENT_SOURCE_PATH,
                    "purpose": "unresolved_intent",
                    "required": False,
                }
            ],
        },
        "intent_slots": [
            {
                "intent_id": DESIRED_OUTPUT_VALUE_INTENT_ID,
                "status": "unresolved",
                "source_path": PLANNER_INTENT_SOURCE_PATH,
                "description": "Desired output value was not provided.",
            }
        ],
    }


def _canonical_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return [
            [str(key), _canonical_json_value(nested_value)]
            for key, nested_value in sorted(
                value.items(),
                key=lambda item: (
                    str(item[0]),
                    type(item[0]).__name__,
                    repr(item[0]),
                ),
            )
        ]
    if isinstance(value, list):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _fingerprint(value: Any) -> str:
    rendered = json.dumps(
        _canonical_json_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_json_value(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _git_short_sha() -> str:
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _new_run_dir(run_root: str | Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(run_root) / f"lm7b-{timestamp}-{_git_short_sha()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _manifest(
    *,
    model: str,
    endpoint: str,
    temperature: float,
    request_fingerprint: str | None,
    workflow_validate_report_fingerprint: str | None,
) -> dict[str, Any]:
    return {
        "script_schema": SCRIPT_SCHEMA,
        "git_commit": _git_short_sha(),
        "planner_request_source": PLANNER_REQUEST_SOURCE,
        "request_fingerprint": request_fingerprint,
        "workflow_validate_report_fingerprint": workflow_validate_report_fingerprint,
        "model": model,
        "endpoint": endpoint,
        "temperature": temperature,
        "worker_retry_enabled": False,
        "raw_artifacts": "local evidence under probe_runs; do not commit",
    }


def _decision_record(
    *,
    decision: str,
    reason: str,
    phase: str,
    request_fingerprint: str | None,
    workflow_validate_valid: bool | None,
    workflow_validate_report_fingerprint: str | None,
    runtime_routing_valid: bool | None = None,
    runtime_routability_evaluated: bool = False,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if decision not in DECISIONS:
        raise ValueError(f"Unsupported LM7B decision: {decision}")
    record = {
        "schema": "rook.lm7b_decision:v1",
        "decision": decision,
        "reason": reason,
        "phase": phase,
        "request_fingerprint": request_fingerprint,
        "workflow_validate_valid": workflow_validate_valid,
        "workflow_validate_report_fingerprint": workflow_validate_report_fingerprint,
        "runtime_routing_valid": runtime_routing_valid,
        "runtime_routability_evaluated": runtime_routability_evaluated,
        "worker_retry_enabled": False,
        "live_repair_dispatched": False,
        "verify_repair_ran": False,
    }
    if extra:
        record.update(dict(extra))
    return record


def _run_live_create_and_verify(*, agent: str, workflow_contract: Mapping[str, Any]):
    raise NotImplementedError("LM7B live create/verify is not implemented yet.")


def _report_fingerprint(report: Mapping[str, Any]) -> str:
    fingerprint = report.get("report_fingerprint")
    return fingerprint if isinstance(fingerprint, str) else _fingerprint(report)


def _request_fingerprint(
    request: Mapping[str, Any],
    report: Mapping[str, Any],
) -> str:
    fingerprint = report.get("request_fingerprint")
    return fingerprint if isinstance(fingerprint, str) else _fingerprint(request)


def _normalized_live_decision(
    payload: Mapping[str, Any],
    *,
    request_fingerprint: str,
    workflow_validate_report_fingerprint: str,
) -> dict[str, Any]:
    stable_fields = {
        "schema",
        "decision",
        "reason",
        "phase",
        "request_fingerprint",
        "workflow_validate_valid",
        "workflow_validate_report_fingerprint",
        "runtime_routing_valid",
        "runtime_routability_evaluated",
        "worker_retry_enabled",
        "live_repair_dispatched",
        "verify_repair_ran",
    }
    extra = {
        key: value
        for key, value in payload.items()
        if key not in stable_fields
    }
    decision = payload.get("decision")
    reason = payload.get("reason")
    phase = payload.get("phase", "runtime_live_create")
    normalized_decision = decision if decision in DECISIONS else "gate_failed"
    normalized_reason = reason if isinstance(reason, str) else "live_decision_missing_reason"
    if decision not in DECISIONS and isinstance(decision, str):
        normalized_reason = f"{decision}:{normalized_reason}"
    return _decision_record(
        decision=normalized_decision,
        reason=normalized_reason,
        phase=phase if isinstance(phase, str) else "runtime_live_create",
        request_fingerprint=request_fingerprint,
        workflow_validate_valid=True,
        workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
        runtime_routing_valid=payload.get("runtime_routing_valid"),
        runtime_routability_evaluated=(
            payload.get("runtime_routability_evaluated") is True
        ),
        extra=extra,
    )


def _run_probe(
    *,
    model: str,
    endpoint: str,
    temperature: float,
    timeout_s: float,
    excerpt_chars: int,
    run_root: str | Path,
    agent: str,
) -> Path:
    del timeout_s, excerpt_chars

    run_dir = _new_run_dir(run_root)
    planner_request = _canonical_planner_request()
    _write_json_value(run_dir / "planner_request.json", planner_request)

    workflow_validate_report = validate_planner_worker_contract_request(
        planner_request
    )
    _write_json_value(
        run_dir / "workflow_validate_report.json",
        workflow_validate_report,
    )

    request_fingerprint = _request_fingerprint(
        planner_request,
        workflow_validate_report,
    )
    workflow_validate_report_fingerprint = _report_fingerprint(
        workflow_validate_report
    )
    _write_json(
        run_dir / "manifest.json",
        _manifest(
            model=model,
            endpoint=endpoint,
            temperature=temperature,
            request_fingerprint=request_fingerprint,
            workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
        ),
    )

    workflow_validate_valid = workflow_validate_report.get("valid") is True
    if not workflow_validate_valid:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="rejected_by_validate",
                reason="workflow_validate_failed",
                phase="workflow_validate",
                request_fingerprint=request_fingerprint,
                workflow_validate_valid=False,
                workflow_validate_report_fingerprint=(
                    workflow_validate_report_fingerprint
                ),
            ),
        )
        return run_dir

    materialization = materialize_planner_worker_contract_request(planner_request)
    try:
        live_result = _run_live_create_and_verify(
            agent=agent,
            workflow_contract=materialization.workflow_contract_payload,
        )
    except NotImplementedError:
        live_result = None
    if isinstance(live_result, Mapping) and isinstance(
        live_result.get("decision"),
        Mapping,
    ):
        _write_json(
            run_dir / "decision.json",
            _normalized_live_decision(
                live_result["decision"],
                request_fingerprint=request_fingerprint,
                workflow_validate_report_fingerprint=(
                    workflow_validate_report_fingerprint
                ),
            ),
        )
        return run_dir

    _write_json(
        run_dir / "decision.json",
        _decision_record(
            decision="gate_failed",
            reason="runtime_not_implemented",
            phase="runtime_live_create",
            request_fingerprint=request_fingerprint,
            workflow_validate_valid=True,
            workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
        ),
    )
    return run_dir
