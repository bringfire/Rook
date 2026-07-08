#!/usr/bin/env python
"""LM7E model-authored request-driven live splice probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
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
    _decision_from_worker_action_apply,
    _decision_from_worker_publication,
    _dispatch_repair_and_verify,
    _hidden_answer_leaks,
    _pass1_decision_hidden_answer_failure,
    _routing_report_json,
    _worker_action_context,
)
from lm7b_request_driven_live_splice_probe import (  # noqa: E402
    _acceptance_source_contract,
    _build_agent,
    _build_worker_context,
    _is_materialized_live_result,
    _report_fingerprint,
    _routing_report_has_errors,
    _run_live_create_and_verify,
    _script_body_gotcha_packet,
)
from lm_worker_two_pass_publication import run_two_pass_worker_publication  # noqa: E402
from rook.agent.local_worker_source_routing_validator import (  # noqa: E402
    validate_worker_visible_source_routing,
)
from rook.agent.plan_graph_worker_action_apply import (  # noqa: E402
    apply_worker_action_to_node,
)
from lm7_planner_authoring_prompt_support import (  # noqa: E402
    INTENT_CORRECT,
    INTENT_INCOMPLETE_BRIEF_VERSION,
    INTENT_NOT_CLASSIFIABLE,
    PARSE_FAILED,
    PARSE_PARSED,
    PROMPT_PROFILE_SHAPE_GUIDANCE_V2,
    SHAPE_GUIDANCE_PROMPT_VERSION,
    TEMPLATE_MENU_VERSION,
    classify_intent_decision,
    fingerprint_json,
    prompt_call_payload,
    strict_parse_model_output,
    write_prompt_artifacts,
)
from rook.agent.plan_graph_workflow_contract import (  # noqa: E402
    BindStepSpec,
    load_workflow_contract_payload,
)
from rook.agent.planner_worker_contract_request import (  # noqa: E402
    materialize_planner_worker_contract_request,
)
from rook.agent.workflow_validate import (  # noqa: E402
    validate_planner_worker_contract_request,
)


SCRIPT_SCHEMA = "rook.lm7e_model_authored_live_splice_probe:v1"
DECISION_SCHEMA = "rook.lm7e_decision:v1"
CANONICAL_PLANNER_PROVIDER = "codex-cli-chatgpt"
CANONICAL_PLANNER_MODEL = "gpt-5.5"
CANONICAL_SCENARIO = "intent_incomplete"
CANONICAL_ATTEMPTS = 1
HIDDEN_MARKER_SCAN_TERMS = (
    "PROBE_REPAIR_CODE",
    "A = 42.0",
    "A = 0.0",
    "A = 1.0",
    "BindStepSpec.base_params",
    "repair_same_component.bind.base_params",
)
PLANNER_MARKER_SCAN_KEYS = frozenset(
    {
        "planner_model_output_excerpt",
        "planner_request",
        "planner_request.json",
        "resolved_source_routing",
        "resolved_source_routing.json",
        "workflow_contract_summary",
        "workflow_contract_summary.json",
        "planner_authoring_prompt",
        "template_menu",
        "intent_complete_brief",
        "intent_incomplete_brief",
        "prompts",
    }
)
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
        description="LM7E model-authored request-driven live splice probe."
    )
    parser.add_argument("--planner-provider-command", required=True)
    parser.add_argument("--planner-provider", default=CANONICAL_PLANNER_PROVIDER)
    parser.add_argument("--planner-provider-timeout-s", type=float, default=120)
    parser.add_argument("--planner-model", default=CANONICAL_PLANNER_MODEL)
    parser.add_argument("--worker-model", default=DEFAULT_MODEL)
    parser.add_argument("--worker-endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--worker-temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--worker-timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--run-dir", default="probe_runs")
    parser.add_argument("--output-excerpt-chars", type=int, default=DEFAULT_EXCERPT_CHARS)
    parser.add_argument("--canonical-evidence", action="store_true")
    args = parser.parse_args(argv)
    if args.output_excerpt_chars < 0:
        parser.error("output_excerpt_chars_must_be_non_negative")
    return args


def _git_short_sha() -> str:
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
    run_dir = Path(run_root) / f"lm7e-{timestamp}-{_git_short_sha()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _write_json_value(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def _excerpt(value: str, chars: int) -> str:
    return value[:chars]


def _contains_marker_text(value: str) -> bool:
    return any(marker in value for marker in HIDDEN_MARKER_SCAN_TERMS)


def _contains_marker_value(value: Any) -> bool:
    rendered = json.dumps(value, sort_keys=True, default=str)
    return _contains_marker_text(rendered)


def _planner_marker_matches_in_metadata(value: Any) -> list[str]:
    matches: list[str] = []

    def scan(current: Any, *, allow_scan: bool = False) -> None:
        if isinstance(current, Mapping):
            for key, nested in current.items():
                key_text = str(key)
                if key_text.startswith("worker_action_input_"):
                    continue
                if key_text == "worker_action.json":
                    continue
                scan(
                    nested,
                    allow_scan=allow_scan or key_text in PLANNER_MARKER_SCAN_KEYS,
                )
            return
        if isinstance(current, (list, tuple)):
            if not allow_scan:
                return
            for nested in current:
                scan(nested, allow_scan=True)
            return
        if not allow_scan:
            return

        text = json.dumps(current, sort_keys=True, default=str)
        for marker in HIDDEN_MARKER_SCAN_TERMS:
            if marker in text and marker not in matches:
                matches.append(marker)

    scan(value)
    return matches


def _parsed_request_has_planner_markers(payload: Mapping[str, Any]) -> bool:
    return _contains_marker_value(payload)


def _canonical_evidence_is_valid(args: argparse.Namespace) -> bool:
    if not args.canonical_evidence:
        return True
    return (
        args.planner_provider == CANONICAL_PLANNER_PROVIDER
        and args.planner_model == CANONICAL_PLANNER_MODEL
        and args.worker_model == DEFAULT_MODEL
        and args.worker_endpoint == DEFAULT_ENDPOINT
        and args.worker_temperature == DEFAULT_TEMPERATURE
    )


def _call_provider_command(
    command: str,
    call_payload: Mapping[str, Any],
    timeout_s: float,
) -> str:
    result = subprocess.run(
        command,
        input=json.dumps(dict(call_payload), sort_keys=True),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        shell=True,
        check=False,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            command,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result.stdout


def _decision_record(
    *,
    decision: str,
    reason: str,
    phase: str,
    planner_parse_status: str,
    planner_validation_status: str,
    planner_intent_decision: str,
    planner_model_output_sha256: str | None,
    planner_model_output_excerpt: str | None,
    planner_model_output_path: str | None,
    request_fingerprint: str | None,
    workflow_validate_valid: bool | None,
    workflow_validate_report_fingerprint: str | None,
    live_rhino_work_started: bool,
    worker_publication_ran: bool,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if decision not in DECISIONS:
        raise ValueError(f"Unsupported LM7E decision: {decision}")
    record = {
        "schema": DECISION_SCHEMA,
        "decision": decision,
        "reason": reason,
        "phase": phase,
        "planner_parse_status": planner_parse_status,
        "planner_validation_status": planner_validation_status,
        "planner_intent_decision": planner_intent_decision,
        "planner_model_output_sha256": planner_model_output_sha256,
        "planner_model_output_excerpt": planner_model_output_excerpt,
        "planner_model_output_path": planner_model_output_path,
        "request_fingerprint": request_fingerprint,
        "workflow_validate_valid": workflow_validate_valid,
        "workflow_validate_report_fingerprint": workflow_validate_report_fingerprint,
        "live_rhino_work_started": live_rhino_work_started,
        "worker_publication_ran": worker_publication_ran,
        "worker_retry_enabled": False,
        "live_repair_dispatched": False,
        "verify_repair_ran": False,
    }
    if extra:
        record.update(dict(extra))
    return record


def _manifest(
    *,
    planner_provider: str,
    planner_model: str,
    worker_model: str,
    worker_endpoint: str,
    worker_temperature: float,
    canonical_evidence: bool,
    planner_model_output_sha256: str | None,
    request_fingerprint: str | None,
    workflow_validate_report_fingerprint: str | None,
    workflow_contract_fingerprint: str | None,
) -> dict[str, Any]:
    return {
        "schema": SCRIPT_SCHEMA,
        "git_commit": _git_short_sha(),
        "planner_provider": planner_provider,
        "planner_model": planner_model,
        "worker_model": worker_model,
        "worker_endpoint": worker_endpoint,
        "worker_temperature": worker_temperature,
        "canonical_evidence": canonical_evidence,
        "scenario": CANONICAL_SCENARIO,
        "attempts": CANONICAL_ATTEMPTS,
        "prompt_profile": PROMPT_PROFILE_SHAPE_GUIDANCE_V2,
        "prompt_version": SHAPE_GUIDANCE_PROMPT_VERSION,
        "template_menu_version": TEMPLATE_MENU_VERSION,
        "brief_version": INTENT_INCOMPLETE_BRIEF_VERSION,
        "worker_retry_enabled": False,
        "planner_model_output_path": "planner_model_output.txt",
        "planner_model_output_sha256": planner_model_output_sha256,
        "request_fingerprint": request_fingerprint,
        "workflow_validate_report_fingerprint": workflow_validate_report_fingerprint,
        "workflow_contract_fingerprint": workflow_contract_fingerprint,
        "raw_artifacts": "local evidence under probe_runs; do not commit",
    }


def _value_shape(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {
            "type": "mapping",
            "keys": sorted(str(key) for key in value.keys()),
            "sha256": fingerprint_json(value),
        }
    if isinstance(value, (list, tuple)):
        return {
            "type": "sequence",
            "count": len(value),
            "sha256": fingerprint_json(list(value)),
        }
    return {
        "type": type(value).__name__,
        "sha256": fingerprint_json(str(value)),
    }


def _worker_node_bind_step_presence(
    *,
    workflow_contract_payload: Mapping[str, Any],
    workflow_contract: Any,
    worker_node_ids: Sequence[str],
) -> dict[str, bool]:
    presence = {str(node_id): False for node_id in worker_node_ids}
    for rule in workflow_contract_payload.get("rules", ()):
        if not isinstance(rule, Mapping):
            continue
        node_id = str(rule.get("node_id") or "")
        if node_id not in presence:
            continue
        for step in rule.get("steps_by_seen_count", ()):
            if isinstance(step, Mapping) and step.get("kind") == "bind":
                presence[node_id] = True
    for rule in getattr(workflow_contract, "rules", ()):
        node_id = str(getattr(rule, "node_id", ""))
        if node_id not in presence:
            continue
        for step in getattr(rule, "steps_by_seen_count", ()):
            if isinstance(step, BindStepSpec) or getattr(step, "kind", None) == "bind":
                presence[node_id] = True
    return presence


def _workflow_contract_summary(
    *,
    template_id: str,
    workflow_contract_payload: Mapping[str, Any],
    workflow_contract: Any,
    worker_node_ids: Sequence[str],
) -> dict[str, Any]:
    node_ids: set[str] = set()
    rule_ids: list[str] = []
    initial_param_summary: dict[str, Any] = {}

    for initial in workflow_contract_payload.get("initial_params", ()):
        if isinstance(initial, Mapping):
            node_id = str(initial.get("node_id") or "")
            if node_id:
                node_ids.add(node_id)

    for rule in workflow_contract_payload.get("rules", ()):
        if isinstance(rule, Mapping):
            node_id = str(rule.get("node_id") or "")
            if node_id:
                node_ids.add(node_id)

    for expected_ref in workflow_contract_payload.get("expected_refs", ()):
        if isinstance(expected_ref, Mapping):
            node_id = str(expected_ref.get("node_id") or "")
            if node_id:
                node_ids.add(node_id)

    for initial in getattr(workflow_contract, "initial_params", ()):
        node_id = str(getattr(initial, "node_id", ""))
        if node_id:
            node_ids.add(node_id)
            initial_param_summary[node_id] = {
                str(key): _value_shape(value)
                for key, value in getattr(initial, "execution_params", {}).items()
            }

    for rule in getattr(workflow_contract, "rules", ()):
        node_id = str(getattr(rule, "node_id", ""))
        if node_id:
            rule_ids.append(node_id)

    worker_node_bind_steps = _worker_node_bind_step_presence(
        workflow_contract_payload=workflow_contract_payload,
        workflow_contract=workflow_contract,
        worker_node_ids=worker_node_ids,
    )
    return {
        "schema": "rook.lm7e_workflow_contract_summary:v1",
        "template_id": template_id,
        "node_ids": sorted(node_ids),
        "rule_ids": sorted(rule_ids),
        "worker_node_ids": list(worker_node_ids),
        "worker_node_bind_steps": worker_node_bind_steps,
        "initial_param_summary": initial_param_summary,
    }


def _workflow_contract_summary_fingerprint(summary: Mapping[str, Any]) -> str:
    return fingerprint_json(summary)


def _wrapped_worker_decision(
    worker_decision: Mapping[str, Any],
    *,
    intent_decision: str,
    output_sha: str,
    output_excerpt: str,
    request_fingerprint: str,
    workflow_validate_report_fingerprint: str,
) -> dict[str, Any]:
    return _decision_record(
        decision=str(worker_decision["decision"]),
        reason=str(worker_decision["reason"]),
        phase=str(worker_decision["phase"]),
        planner_parse_status=PARSE_PARSED,
        planner_validation_status="workflow_validate_valid",
        planner_intent_decision=intent_decision,
        planner_model_output_sha256=output_sha,
        planner_model_output_excerpt=output_excerpt,
        planner_model_output_path="planner_model_output.txt",
        request_fingerprint=request_fingerprint,
        workflow_validate_valid=True,
        workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
        live_rhino_work_started=True,
        worker_publication_ran=True,
        extra={
            key: value
            for key, value in worker_decision.items()
            if key not in {"schema", "decision", "reason", "phase"}
        },
    )


def _run_probe(
    *,
    planner_provider: str,
    planner_model: str,
    planner_provider_command: str,
    planner_provider_timeout_s: float,
    worker_model: str,
    worker_endpoint: str,
    worker_temperature: float,
    worker_timeout_s: float,
    output_excerpt_chars: int,
    run_root: str | Path,
    canonical_evidence: bool,
    call_provider: Callable[[Mapping[str, Any]], str] | None = None,
    agent: Any | None = None,
) -> Path:
    run_dir = _new_run_dir(run_root)
    write_prompt_artifacts(
        run_dir,
        PROMPT_PROFILE_SHAPE_GUIDANCE_V2,
        scenarios=(CANONICAL_SCENARIO,),
    )
    call_payload = prompt_call_payload(
        scenario=CANONICAL_SCENARIO,
        attempt_index=0,
        provider=planner_provider,
        model=planner_model,
        temperature=0,
        prompt_profile=PROMPT_PROFILE_SHAPE_GUIDANCE_V2,
    )
    provider = call_provider or (
        lambda payload: _call_provider_command(
            planner_provider_command,
            payload,
            planner_provider_timeout_s,
        )
    )
    try:
        raw_output = provider(call_payload)
    except Exception as exc:
        raw_output = ""
        output_sha = fingerprint_json(raw_output)
        _write_text(run_dir / "planner_model_output.txt", raw_output)
        _write_json(
            run_dir / "manifest.json",
            _manifest(
                planner_provider=planner_provider,
                planner_model=planner_model,
                worker_model=worker_model,
                worker_endpoint=worker_endpoint,
                worker_temperature=worker_temperature,
                canonical_evidence=canonical_evidence,
                planner_model_output_sha256=output_sha,
                request_fingerprint=None,
                workflow_validate_report_fingerprint=None,
                workflow_contract_fingerprint=None,
            ),
        )
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="rejected_by_validate",
                reason=f"planner_provider_failed:{type(exc).__name__}",
                phase="planner_provider",
                planner_parse_status=PARSE_FAILED,
                planner_validation_status="not_evaluated",
                planner_intent_decision=INTENT_NOT_CLASSIFIABLE,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt="",
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=None,
                workflow_validate_valid=None,
                workflow_validate_report_fingerprint=None,
                live_rhino_work_started=False,
                worker_publication_ran=False,
            ),
        )
        return run_dir

    output_sha = fingerprint_json(raw_output)
    _write_text(run_dir / "planner_model_output.txt", raw_output)
    output_excerpt = _excerpt(raw_output, output_excerpt_chars)

    parsed = strict_parse_model_output(raw_output)
    if parsed.parse_status != PARSE_PARSED or parsed.payload is None:
        _write_json(
            run_dir / "manifest.json",
            _manifest(
                planner_provider=planner_provider,
                planner_model=planner_model,
                worker_model=worker_model,
                worker_endpoint=worker_endpoint,
                worker_temperature=worker_temperature,
                canonical_evidence=canonical_evidence,
                planner_model_output_sha256=output_sha,
                request_fingerprint=None,
                workflow_validate_report_fingerprint=None,
                workflow_contract_fingerprint=None,
            ),
        )
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="rejected_by_validate",
                reason="planner_parse_failed",
                phase="planner_parse",
                planner_parse_status=PARSE_FAILED,
                planner_validation_status="not_evaluated",
                planner_intent_decision=INTENT_NOT_CLASSIFIABLE,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt=output_excerpt,
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=None,
                workflow_validate_valid=None,
                workflow_validate_report_fingerprint=None,
                live_rhino_work_started=False,
                worker_publication_ran=False,
                extra={"planner_parse_failure_reason": parsed.failure_reason},
            ),
        )
        return run_dir

    planner_request = parsed.payload
    _write_json_value(run_dir / "planner_request.json", planner_request)
    request_fingerprint = fingerprint_json(planner_request)
    intent = classify_intent_decision(CANONICAL_SCENARIO, planner_request)

    if _parsed_request_has_planner_markers(planner_request):
        _write_json(
            run_dir / "manifest.json",
            _manifest(
                planner_provider=planner_provider,
                planner_model=planner_model,
                worker_model=worker_model,
                worker_endpoint=worker_endpoint,
                worker_temperature=worker_temperature,
                canonical_evidence=canonical_evidence,
                planner_model_output_sha256=output_sha,
                request_fingerprint=request_fingerprint,
                workflow_validate_report_fingerprint=None,
                workflow_contract_fingerprint=None,
            ),
        )
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="rejected_by_validate",
                reason="planner_hidden_marker_detected",
                phase="planner_request_marker_gate",
                planner_parse_status=PARSE_PARSED,
                planner_validation_status="not_evaluated",
                planner_intent_decision=intent.intent_decision,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt=output_excerpt,
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=request_fingerprint,
                workflow_validate_valid=None,
                workflow_validate_report_fingerprint=None,
                live_rhino_work_started=False,
                worker_publication_ran=False,
            ),
        )
        return run_dir

    report = validate_planner_worker_contract_request(planner_request)
    _write_json_value(run_dir / "workflow_validate_report.json", report)
    workflow_validate_report_fingerprint = _report_fingerprint(report)
    workflow_validate_valid = report.get("valid") is True
    if not workflow_validate_valid:
        _write_json(
            run_dir / "manifest.json",
            _manifest(
                planner_provider=planner_provider,
                planner_model=planner_model,
                worker_model=worker_model,
                worker_endpoint=worker_endpoint,
                worker_temperature=worker_temperature,
                canonical_evidence=canonical_evidence,
                planner_model_output_sha256=output_sha,
                request_fingerprint=request_fingerprint,
                workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
                workflow_contract_fingerprint=None,
            ),
        )
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="rejected_by_validate",
                reason="workflow_validate_failed",
                phase="workflow_validate",
                planner_parse_status=PARSE_PARSED,
                planner_validation_status="workflow_validate_failed",
                planner_intent_decision=intent.intent_decision,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt=output_excerpt,
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=request_fingerprint,
                workflow_validate_valid=False,
                workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
                live_rhino_work_started=False,
                worker_publication_ran=False,
            ),
        )
        return run_dir

    materialization = materialize_planner_worker_contract_request(planner_request)
    workflow_contract = load_workflow_contract_payload(
        materialization.workflow_contract_payload
    )
    resolved_routing = materialization.resolved_routing_artifact
    worker_node_ids = tuple(materialization.worker_node_ids)
    _write_json_value(run_dir / "resolved_source_routing.json", resolved_routing)
    contract_summary = _workflow_contract_summary(
        template_id=str(planner_request.get("template_id")),
        workflow_contract_payload=materialization.workflow_contract_payload,
        workflow_contract=workflow_contract,
        worker_node_ids=worker_node_ids,
    )
    if _contains_marker_value(contract_summary):
        raise RuntimeError("workflow_contract_summary_hidden_marker")
    _write_json_value(run_dir / "workflow_contract_summary.json", contract_summary)
    workflow_contract_fingerprint = _workflow_contract_summary_fingerprint(
        contract_summary
    )
    _write_json(
        run_dir / "manifest.json",
        _manifest(
            planner_provider=planner_provider,
            planner_model=planner_model,
            worker_model=worker_model,
            worker_endpoint=worker_endpoint,
            worker_temperature=worker_temperature,
            canonical_evidence=canonical_evidence,
            planner_model_output_sha256=output_sha,
            request_fingerprint=request_fingerprint,
            workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
            workflow_contract_fingerprint=workflow_contract_fingerprint,
        ),
    )

    try:
        live_result = _run_live_create_and_verify(
            agent=agent,
            workflow_contract=workflow_contract,
        )
    except NotImplementedError:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason="runtime_not_implemented",
                phase="runtime_live_create",
                planner_parse_status=PARSE_PARSED,
                planner_validation_status="workflow_validate_valid",
                planner_intent_decision=intent.intent_decision,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt=output_excerpt,
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=request_fingerprint,
                workflow_validate_valid=True,
                workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
                live_rhino_work_started=False,
                worker_publication_ran=False,
            ),
        )
        return run_dir

    if not (isinstance(live_result, Mapping) and _is_materialized_live_result(live_result)):
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason="live_create_result_invalid",
                phase="live_create",
                planner_parse_status=PARSE_PARSED,
                planner_validation_status="workflow_validate_valid",
                planner_intent_decision=intent.intent_decision,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt=output_excerpt,
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=request_fingerprint,
                workflow_validate_valid=True,
                workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
                live_rhino_work_started=True,
                worker_publication_ran=False,
            ),
        )
        return run_dir

    live_result = dict(live_result)
    live_result["resolved_routing_artifact"] = resolved_routing
    live_result["planner_request"] = planner_request

    _write_json(run_dir / "live_create_summary.json", live_result["live_create_summary"])
    _write_json(
        run_dir / "verify_create_summary.json", live_result["verify_create_summary"]
    )

    routing_report = validate_worker_visible_source_routing(
        resolved_routing,
        workflow_contract=_acceptance_source_contract(live_result["workflow_contract"]),
        graph=live_result["graph"],
        convention_packets=live_result["convention_packets"],
        worker_node_ids=tuple(worker_node_ids),
    )
    _write_json(
        run_dir / "runtime_routing_validation.json",
        _routing_report_json(routing_report),
    )

    runtime_routing_valid = (
        routing_report.valid if isinstance(routing_report.valid, bool) else None
    )
    runtime_routability_evaluated = routing_report.routability_evaluated is True
    if not runtime_routability_evaluated:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason="runtime_routability_not_evaluated",
                phase="runtime_routing",
                planner_parse_status=PARSE_PARSED,
                planner_validation_status="workflow_validate_valid",
                planner_intent_decision=intent.intent_decision,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt=output_excerpt,
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=request_fingerprint,
                workflow_validate_valid=True,
                workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
                live_rhino_work_started=True,
                worker_publication_ran=False,
                extra={
                    "runtime_routing_valid": runtime_routing_valid,
                    "runtime_routability_evaluated": runtime_routability_evaluated,
                },
            ),
        )
        return run_dir
    elif _routing_report_has_errors(routing_report):
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason="runtime_routability_failed",
                phase="runtime_routing",
                planner_parse_status=PARSE_PARSED,
                planner_validation_status="workflow_validate_valid",
                planner_intent_decision=intent.intent_decision,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt=output_excerpt,
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=request_fingerprint,
                workflow_validate_valid=True,
                workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
                live_rhino_work_started=True,
                worker_publication_ran=False,
                extra={
                    "runtime_routing_valid": runtime_routing_valid,
                    "runtime_routability_evaluated": runtime_routability_evaluated,
                },
            ),
        )
        return run_dir

    request_payload = _build_worker_context(live=live_result, run_dir=run_dir)

    publication = run_two_pass_worker_publication(
        request_payload,
        model=worker_model,
        endpoint=worker_endpoint,
        temperature=worker_temperature,
        timeout_s=worker_timeout_s,
        excerpt_chars=output_excerpt_chars,
        decision_guard=_pass1_decision_hidden_answer_failure,
    )

    if _hidden_answer_leaks(publication.row) or _hidden_answer_leaks(
        publication.response_payload
    ):
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="publication_failed",
                reason="worker_publication_hidden_answer_leak",
                phase="worker_publication",
                planner_parse_status=PARSE_PARSED,
                planner_validation_status="workflow_validate_valid",
                planner_intent_decision=intent.intent_decision,
                planner_model_output_sha256=output_sha,
                planner_model_output_excerpt=output_excerpt,
                planner_model_output_path="planner_model_output.txt",
                request_fingerprint=request_fingerprint,
                workflow_validate_valid=True,
                workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
                live_rhino_work_started=True,
                worker_publication_ran=True,
            ),
        )
        return run_dir

    _write_json(run_dir / "worker_publication_row.json", publication.row)

    worker_decision = _decision_from_worker_publication(
        publication_row=publication.row,
        response_payload=publication.response_payload,
    )
    if worker_decision is not None:
        _write_json(
            run_dir / "decision.json",
            _wrapped_worker_decision(
                worker_decision,
                intent_decision=intent.intent_decision,
                output_sha=output_sha,
                output_excerpt=output_excerpt,
                request_fingerprint=request_fingerprint,
                workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
            ),
        )
        return run_dir

    response_payload = publication.response_payload
    action_context = _worker_action_context(
        response_payload=response_payload,
        run_dir=run_dir,
        excerpt_chars=output_excerpt_chars,
    )
    _write_json(run_dir / "worker_action.json", response_payload)
    apply_result = apply_worker_action_to_node(
        live_result["graph"],
        "repair_same_component",
        action_id=str(response_payload.get("action_id") or ""),
        action_input=response_payload.get("input"),
        anchor_binding=live_result["anchor_binding"],
    )

    if apply_result.applied is not True:
        worker_decision = _decision_from_worker_action_apply(
            apply_result,
            action_context=action_context,
        )
        _write_json(
            run_dir / "decision.json",
            _wrapped_worker_decision(
                worker_decision,
                intent_decision=intent.intent_decision,
                output_sha=output_sha,
                output_excerpt=output_excerpt,
                request_fingerprint=request_fingerprint,
                workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
            ),
        )
        return run_dir

    repair_result = _dispatch_repair_and_verify(
        graph=apply_result.graph,
        agent=agent,
        params_sha256=apply_result.params_sha256,
        run_dir=run_dir,
        action_context=action_context,
    )
    worker_decision = repair_result["decision"]
    _write_json(
        run_dir / "decision.json",
        _wrapped_worker_decision(
            worker_decision,
            intent_decision=intent.intent_decision,
            output_sha=output_sha,
            output_excerpt=output_excerpt,
            request_fingerprint=request_fingerprint,
            workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
        ),
    )
    return run_dir


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    if not _canonical_evidence_is_valid(args):
        print("invalid_canonical_evidence", file=sys.stderr)
        raise SystemExit(2)
    run_dir = _run_probe(
        planner_provider=args.planner_provider,
        planner_model=args.planner_model,
        planner_provider_command=args.planner_provider_command,
        planner_provider_timeout_s=args.planner_provider_timeout_s,
        worker_model=args.worker_model,
        worker_endpoint=args.worker_endpoint,
        worker_temperature=args.worker_temperature,
        worker_timeout_s=args.worker_timeout_s,
        output_excerpt_chars=args.output_excerpt_chars,
        run_root=args.run_dir,
        canonical_evidence=args.canonical_evidence,
        agent=_build_agent(),
    )
    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    print(
        "LM7E model-authored live splice probe complete "
        f"run_dir={run_dir} "
        f"decision={decision.get('decision')} "
        f"reason={decision.get('reason')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
