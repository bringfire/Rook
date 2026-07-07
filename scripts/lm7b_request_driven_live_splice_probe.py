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
from dataclasses import replace
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
    _await,
    _decision_from_worker_action_apply,
    _decision_from_worker_publication,
    _dispatch_repair_and_verify,
    _extract_script_receipt,
    _hidden_answer_leaks,
    _live_result_summary,
    _pass1_decision_hidden_answer_failure,
    _phase_a_recon_summary,
    _routing_report_json,
    _worker_action_context,
)
from lm5k_worker_probe import _script_body_gotcha_packet  # noqa: E402
from lm_worker_two_pass_publication import run_two_pass_worker_publication  # noqa: E402
from rook.agent.local_worker_acceptance_criteria import (  # noqa: E402
    AcceptanceCriteriaSources,
    UnresolvedIntentEntry,
    assemble_acceptance_criteria_packet,
)
from rook.agent.local_worker_acceptance_criteria_sources import (  # noqa: E402
    extract_acceptance_criteria_sources,
)
from rook.agent.local_worker_source_routing_validator import (  # noqa: E402
    validate_worker_visible_source_routing,
)
from rook.agent.local_worker_turn_context import (  # noqa: E402
    WorkerAllowedAction,
    WorkerKnowledgePacket,
    build_local_worker_turn_context,
)
from rook.agent.local_worker_turn_request import (  # noqa: E402
    render_local_worker_turn_request_payload,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY  # noqa: E402
from rook.agent.plan_graph_worker_action_apply import (  # noqa: E402
    apply_worker_action_to_node,
)
from rook.agent.plan_graph_workflow_contract import (  # noqa: E402
    compile_workflow_contract,
    load_workflow_contract_payload,
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
from rook.learning.plan_graph_runner import apply_verifier_step  # noqa: E402


SCRIPT_SCHEMA = "rook.lm7b_request_driven_live_splice_probe:v1"
PLANNER_REQUEST_SOURCE = "script_local_canonical_lm7a_request"
ACCEPTANCE_CRITERIA_LEGACY_SOURCE = (
    "workflow_contract + create_script.initial_execution_params + "
    "create_script.receipt.script_receipt.repair_anchor + script_body_gotcha"
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


def _normalized_optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


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
        "runtime_routing_valid": _normalized_optional_bool(runtime_routing_valid),
        "runtime_routability_evaluated": runtime_routability_evaluated,
        "worker_retry_enabled": False,
        "live_repair_dispatched": False,
        "verify_repair_ran": False,
    }
    if extra:
        record.update(dict(extra))
    return record


def _with_lm7b_metadata(
    decision: Mapping[str, Any],
    *,
    request_fingerprint: str | None,
    workflow_validate_report_fingerprint: str | None,
    runtime_routing_valid: bool | None,
    runtime_routability_evaluated: bool,
    workflow_validate_valid: bool = True,
) -> dict[str, Any]:
    extra = dict(decision)
    decision_value = str(extra.pop("decision"))
    reason = str(extra.pop("reason"))
    phase = str(extra.pop("phase"))
    extra.pop("schema", None)
    extra.pop("worker_retry_enabled", None)
    extra["retry_attempted"] = False
    extra["retry_count"] = 0
    return _decision_record(
        decision=decision_value,
        reason=reason,
        phase=phase,
        request_fingerprint=request_fingerprint,
        workflow_validate_valid=workflow_validate_valid,
        workflow_validate_report_fingerprint=workflow_validate_report_fingerprint,
        runtime_routing_valid=runtime_routing_valid,
        runtime_routability_evaluated=runtime_routability_evaluated,
        extra=extra,
    )


def _routing_report_has_errors(report: Any) -> bool:
    diagnostics = tuple(getattr(report, "static_diagnostics", ())) + tuple(
        getattr(report, "routability_diagnostics", ())
    )
    return any(
        getattr(diagnostic, "severity", None) == "error"
        for diagnostic in diagnostics
    )


def _run_live_create_and_verify(*, agent: Any, workflow_contract: Any) -> dict[str, Any]:
    if not hasattr(agent, "run_live_producer_node"):
        raise NotImplementedError("LM7B live create/verify requires a live agent.")

    scaffold = compile_workflow_contract(workflow_contract)
    graph = scaffold.graph
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = dict(
        workflow_contract.initial_params[0].execution_params
    )

    create_result = _await(agent.run_live_producer_node(graph, "create_script"))
    graph = create_result.graph
    verify_create = apply_verifier_step(graph, "verify_create", "create_script")
    graph = verify_create.graph
    receipt = _extract_script_receipt(graph, "create_script")
    create_evidence = graph.nodes["create_script"].evidence
    live_create_summary = _live_result_summary(
        node_id="create_script",
        tool_name=create_result.tool_name,
        node_status=graph.nodes["create_script"].status,
        outcome_status=str(create_result.outcome_status),
        verified=create_evidence.verified if create_evidence is not None else None,
        receipt=receipt,
    )
    verify_create_summary = {
        "verifier_node_id": "verify_create",
        "source_node_id": "create_script",
        "applied": verify_create.applied,
        "outcome_status": verify_create.outcome_status,
    }
    anchor = receipt.get("repair_anchor") if isinstance(receipt, Mapping) else None
    anchor_binding = {
        "component_guid": (
            anchor.get("component_guid") if isinstance(anchor, Mapping) else None
        ),
        "language": anchor.get("language") if isinstance(anchor, Mapping) else None,
    }
    return {
        "workflow_contract": workflow_contract,
        "scaffold": scaffold,
        "graph": graph,
        "convention_packets": (_script_body_gotcha_packet(),),
        "anchor_binding": anchor_binding,
        "live_create_summary": live_create_summary,
        "verify_create_summary": verify_create_summary,
    }


def _build_worker_context(*, live: Mapping[str, Any], run_dir: Path) -> dict[str, Any]:
    sources = extract_acceptance_criteria_sources(
        workflow_contract=_acceptance_source_contract(live["workflow_contract"]),
        graph=live["graph"],
        convention_packets=live["convention_packets"],
    )
    sources = AcceptanceCriteriaSources(
        pin_contract=sources.pin_contract,
        verifier_outcome=sources.verifier_outcome,
        receipt_diagnostic=sources.receipt_diagnostic,
        convention=sources.convention,
        unresolved_intent=_unresolved_intent_entries(
            routing_artifact=live["resolved_routing_artifact"],
            planner_request=live["planner_request"],
        ),
    )
    full_packet = assemble_acceptance_criteria_packet(sources)
    worker_visible = _legacy_acceptance_criteria_projection(full_packet)
    _write_json(run_dir / "acceptance_criteria_packet.json", full_packet)
    _write_json(run_dir / "worker_visible_acceptance_criteria.json", worker_visible)
    context = build_local_worker_turn_context(
        live["scaffold"],
        live["graph"],
        (),
        (),
        current_node_id="repair_same_component",
        knowledge=(
            WorkerKnowledgePacket(
                packet_id="acceptance_criteria",
                kind="acceptance_criteria",
                title="Materialized acceptance criteria",
                content=worker_visible,
            ),
            *tuple(live["convention_packets"]),
        ),
        allowed_actions=(
            WorkerAllowedAction(
                action_id="draft_repair_params",
                kind="draft_repair_params",
                description="Draft replacement C# body repair parameters.",
                input_schema={"type": "object", "required": ["code", "mode"]},
            ),
        ),
    )
    return dict(render_local_worker_turn_request_payload(context))


def _legacy_acceptance_criteria_projection(packet: Mapping[str, Any]) -> dict[str, Any]:
    criteria = packet.get("criteria")
    if not isinstance(criteria, list):
        raise ValueError("acceptance criteria packet criteria missing")
    return {
        "source": ACCEPTANCE_CRITERIA_LEGACY_SOURCE,
        "criteria": [
            {
                "criterion_id": item["criterion_id"],
                "description": item["description"],
                "source": item["source"],
            }
            for item in criteria
        ],
    }


def _acceptance_source_contract(workflow_contract: Any) -> Any:
    initial_params = []
    for initial in workflow_contract.initial_params:
        execution_params = {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in initial.execution_params.items()
        }
        initial_params.append(replace(initial, execution_params=execution_params))
    return replace(workflow_contract, initial_params=tuple(initial_params))


def _unresolved_intent_entries(
    *,
    routing_artifact: Mapping[str, Any],
    planner_request: Mapping[str, Any],
) -> tuple[UnresolvedIntentEntry, ...]:
    intents_by_source_path = {
        intent["source_path"]: intent
        for intent in planner_request.get("intent_slots", [])
        if isinstance(intent, Mapping)
        and intent.get("status") == "unresolved"
        and isinstance(intent.get("source_path"), str)
    }
    entries: list[UnresolvedIntentEntry] = []
    for route in routing_artifact.get("routes", []):
        if not isinstance(route, Mapping):
            continue
        for visible_source in route.get("visible_sources", []):
            if not isinstance(visible_source, Mapping):
                continue
            if visible_source.get("source_class") != "planner_user_intent":
                continue
            if visible_source.get("purpose") != "unresolved_intent":
                continue
            source_path = visible_source.get("source_path")
            intent = intents_by_source_path.get(source_path)
            if not isinstance(intent, Mapping):
                continue
            entries.append(
                UnresolvedIntentEntry(
                    intent_id=str(intent["intent_id"]),
                    description=str(intent["description"]),
                    source_class="planner_user_intent",
                    source_path=str(source_path),
                    reason=(
                        "required_route_unresolved"
                        if visible_source.get("required") is True
                        else "optional_route_unresolved"
                    ),
                )
            )
    return tuple(entries)


def _is_materialized_live_result(value: Mapping[str, Any]) -> bool:
    required_keys = {
        "workflow_contract",
        "scaffold",
        "graph",
        "convention_packets",
        "anchor_binding",
        "live_create_summary",
        "verify_create_summary",
    }
    return required_keys.issubset(value)


def _report_fingerprint(report: Mapping[str, Any]) -> str:
    fingerprint = report.get("report_fingerprint")
    return fingerprint if isinstance(fingerprint, str) else _fingerprint(report)


def _request_fingerprint(
    request: Mapping[str, Any],
    report: Mapping[str, Any],
) -> str:
    fingerprint = report.get("request_fingerprint")
    return fingerprint if isinstance(fingerprint, str) else _fingerprint(request)


def _run_probe(
    *,
    model: str,
    endpoint: str,
    temperature: float,
    timeout_s: float,
    excerpt_chars: int,
    run_root: str | Path,
    agent: Any,
) -> Path:
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
    workflow_contract = load_workflow_contract_payload(
        materialization.workflow_contract_payload
    )
    try:
        live_result = _run_live_create_and_verify(
            agent=agent,
            workflow_contract=workflow_contract,
        )
    except NotImplementedError:
        live_result = None

    if isinstance(live_result, Mapping) and _is_materialized_live_result(live_result):
        live_result = dict(live_result)
        live_result["resolved_routing_artifact"] = (
            materialization.resolved_routing_artifact
        )
        live_result["planner_request"] = planner_request
        _write_json(
            run_dir / "live_create_summary.json",
            live_result["live_create_summary"],
        )
        _write_json(
            run_dir / "verify_create_summary.json",
            live_result["verify_create_summary"],
        )
        phase_a_recon = _phase_a_recon_summary(live_result)
        _write_json(run_dir / "phase_a_recon.json", phase_a_recon)
        if (
            _hidden_answer_leaks(live_result["live_create_summary"])
            or _hidden_answer_leaks(live_result["verify_create_summary"])
            or _hidden_answer_leaks(phase_a_recon)
        ):
            _write_json(
                run_dir / "decision.json",
                _decision_record(
                    decision="gate_failed",
                    reason="phase_a_hidden_answer_leak",
                    phase="receipt_recon",
                    request_fingerprint=request_fingerprint,
                    workflow_validate_valid=True,
                    workflow_validate_report_fingerprint=(
                        workflow_validate_report_fingerprint
                    ),
                ),
            )
            return run_dir

        routing_report = validate_worker_visible_source_routing(
            materialization.resolved_routing_artifact,
            workflow_contract=live_result["workflow_contract"],
            graph=live_result["graph"],
            convention_packets=live_result["convention_packets"],
            worker_node_ids=tuple(materialization.worker_node_ids),
        )
        _write_json(
            run_dir / "runtime_routing_validation.json",
            _routing_report_json(routing_report),
        )
        runtime_routing_valid = _normalized_optional_bool(routing_report.valid)
        runtime_routability_evaluated = routing_report.routability_evaluated is True
        if not runtime_routability_evaluated:
            _write_json(
                run_dir / "decision.json",
                _decision_record(
                    decision="gate_failed",
                    reason="runtime_routability_not_evaluated",
                    phase="runtime_routing_gate",
                    request_fingerprint=request_fingerprint,
                    workflow_validate_valid=True,
                    workflow_validate_report_fingerprint=(
                        workflow_validate_report_fingerprint
                    ),
                    runtime_routing_valid=runtime_routing_valid,
                    runtime_routability_evaluated=False,
                ),
            )
            return run_dir
        if _routing_report_has_errors(routing_report):
            _write_json(
                run_dir / "decision.json",
                _decision_record(
                    decision="gate_failed",
                    reason="runtime_routability_failed",
                    phase="runtime_routing_gate",
                    request_fingerprint=request_fingerprint,
                    workflow_validate_valid=True,
                    workflow_validate_report_fingerprint=(
                        workflow_validate_report_fingerprint
                    ),
                    runtime_routing_valid=runtime_routing_valid,
                    runtime_routability_evaluated=True,
                ),
            )
            return run_dir

        try:
            request_payload = _build_worker_context(live=live_result, run_dir=run_dir)
        except NotImplementedError:
            request_payload = None

        if request_payload is not None:
            publication = run_two_pass_worker_publication(
                request_payload,
                model=model,
                endpoint=endpoint,
                temperature=temperature,
                timeout_s=timeout_s,
                excerpt_chars=excerpt_chars,
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
                        request_fingerprint=request_fingerprint,
                        workflow_validate_valid=True,
                        workflow_validate_report_fingerprint=(
                            workflow_validate_report_fingerprint
                        ),
                        runtime_routing_valid=runtime_routing_valid,
                        runtime_routability_evaluated=True,
                        extra={
                            "retry_attempted": False,
                            "retry_count": 0,
                        },
                    ),
                )
                return run_dir
            _write_json(run_dir / "worker_publication_row.json", publication.row)
            publication_decision = _decision_from_worker_publication(
                publication_row=publication.row,
                response_payload=publication.response_payload,
            )
            if publication_decision is not None:
                _write_json(
                    run_dir / "decision.json",
                    _with_lm7b_metadata(
                        publication_decision,
                        request_fingerprint=request_fingerprint,
                        workflow_validate_report_fingerprint=(
                            workflow_validate_report_fingerprint
                        ),
                        runtime_routing_valid=runtime_routing_valid,
                        runtime_routability_evaluated=True,
                    ),
                )
                return run_dir

            response_payload = publication.response_payload
            action_context = _worker_action_context(
                response_payload=response_payload,
                run_dir=run_dir,
                excerpt_chars=excerpt_chars,
            )
            action_context.update(
                {
                    "retry_attempted": False,
                    "retry_count": 0,
                    "retry_eligibility_reason": None,
                    "first_worker_response_kind": response_payload.get("kind"),
                    "first_worker_decline_reason": None,
                    "final_worker_response_kind": response_payload.get("kind"),
                }
            )
            _write_json(run_dir / "worker_action.json", response_payload)
            apply_result = apply_worker_action_to_node(
                live_result["graph"],
                "repair_same_component",
                action_id=response_payload["action_id"],
                action_input=response_payload["input"],
                anchor_binding=live_result["anchor_binding"],
            )
            if apply_result.applied is not True:
                _write_json(
                    run_dir / "decision.json",
                    _with_lm7b_metadata(
                        _decision_from_worker_action_apply(
                            apply_result,
                            action_context=action_context,
                        ),
                        request_fingerprint=request_fingerprint,
                        workflow_validate_report_fingerprint=(
                            workflow_validate_report_fingerprint
                        ),
                        runtime_routing_valid=runtime_routing_valid,
                        runtime_routability_evaluated=True,
                    ),
                )
                return run_dir

            final = _dispatch_repair_and_verify(
                graph=apply_result.graph,
                agent=agent,
                params_sha256=apply_result.params_sha256,
                run_dir=run_dir,
                action_context=action_context,
            )
            _write_json(
                run_dir / "decision.json",
                _with_lm7b_metadata(
                    final["decision"],
                    request_fingerprint=request_fingerprint,
                    workflow_validate_report_fingerprint=(
                        workflow_validate_report_fingerprint
                    ),
                    runtime_routing_valid=runtime_routing_valid,
                    runtime_routability_evaluated=True,
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
            runtime_routing_valid=(
                runtime_routing_valid
                if "runtime_routing_valid" in locals()
                else None
            ),
            runtime_routability_evaluated=(
                runtime_routability_evaluated
                if "runtime_routability_evaluated" in locals()
                else False
            ),
        ),
    )
    return run_dir


def _build_agent() -> Any:
    from rook.agent.base_agent import RookAgent
    from rook.server import _mcp_tool_executor

    return RookAgent(tool_executor=_mcp_tool_executor)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    run_dir = _run_probe(
        model=args.model,
        endpoint=args.endpoint,
        temperature=args.temperature,
        timeout_s=args.timeout_s,
        excerpt_chars=args.excerpt_chars,
        run_root=args.run_dir,
        agent=_build_agent(),
    )
    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    print(
        "LM7B request-driven live splice probe complete "
        f"run_dir={run_dir} "
        f"decision={decision.get('decision')} "
        f"reason={decision.get('reason')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
