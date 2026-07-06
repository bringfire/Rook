#!/usr/bin/env python
"""LM6A live worker splice probe.

Deterministic implementation plus post-merge live evidence script. The script
manually sequences create/verify/worker/apply/repair/verify and writes bounded
local artifacts under probe_runs/.
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

from lm5k_worker_probe import (  # noqa: E402
    ACCEPTANCE_CRITERIA_LEGACY_SOURCE,
    REPAIR_TARGET_ERROR,
    _probe_contract,
)
from lm_worker_two_pass_publication import run_two_pass_worker_publication  # noqa: E402
from rook.agent.local_worker_acceptance_criteria import (  # noqa: E402
    assemble_acceptance_criteria_packet,
)
from rook.agent.local_worker_acceptance_criteria_sources import (  # noqa: E402
    extract_acceptance_criteria_sources,
)
from rook.agent.local_worker_source_routing_validator import (  # noqa: E402
    validate_worker_visible_source_routing,
)
from rook.agent.plan_graph_worker_action_apply import (  # noqa: E402
    apply_worker_action_to_node,
)


SCRIPT_SCHEMA = "rook.lm6a_live_worker_splice_probe:v1"
DEFAULT_MODEL = "gemma4:12b-it-qat"
DEFAULT_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_PHASE = "full"
DEFAULT_TEMPERATURE = 0
DEFAULT_TIMEOUT_S = 120
DEFAULT_EXCERPT_CHARS = 1200
PHASES = ("receipt_recon", "full")
DECISIONS = (
    "accepted",
    "rejected",
    "worker_declined",
    "gate_failed",
    "publication_failed",
)

_LM6A_ROUTING_ARTIFACT = {
    "schema": "rook.worker_visible_source_routing:v1",
    "routes": [
        {
            "node_id": "repair_same_component",
            "visible_sources": [
                {
                    "route_id": "repair_pin_contract",
                    "source_class": "pin_contract",
                    "source_path": "create_script.initial_execution_params.pins_out",
                    "purpose": "acceptance_criteria",
                    "required": True,
                },
                {
                    "route_id": "repair_expected_outcome",
                    "source_class": "verifier_outcome",
                    "source_path": (
                        "workflow_contract.rules.verify_repair.expected_outcome"
                    ),
                    "purpose": "acceptance_criteria",
                    "required": True,
                },
                {
                    "route_id": "repair_target_diagnostics",
                    "source_class": "receipt_diagnostic",
                    "source_path": (
                        "create_script.receipt.script_receipt.repair_anchor."
                        "target_errors"
                    ),
                    "purpose": "acceptance_criteria",
                    "required": True,
                },
                {
                    "route_id": "repair_body_mode_convention",
                    "source_class": "convention",
                    "source_path": "script_body_gotcha",
                    "purpose": "acceptance_criteria",
                    "required": True,
                },
            ],
        }
    ],
}


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LM6A live worker splice probe.")
    parser.add_argument("--phase", choices=PHASES, default=DEFAULT_PHASE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--excerpt-chars", type=int, default=DEFAULT_EXCERPT_CHARS)
    parser.add_argument("--run-dir", default="probe_runs")
    return parser.parse_args(argv)


def _lm6a_bind_free_contract():
    from rook.agent.plan_graph_workflow_contract import (
        ProducerStepSpec,
        RookWorkflowContract,
        WorkflowNodeRule,
    )

    base = _probe_contract()
    rules = []
    for rule in base.rules:
        if rule.node_id == "repair_same_component":
            rules.append(
                WorkflowNodeRule(
                    node_id="repair_same_component",
                    steps_by_seen_count=(
                        ProducerStepSpec(node_id="repair_same_component"),
                    ),
                )
            )
        else:
            rules.append(rule)
    return RookWorkflowContract(
        workflow_id="lm6a_live_worker_splice",
        template=base.template,
        initial_params=base.initial_params,
        expected_refs=base.expected_refs,
        rules=tuple(rules),
        terminal_node_ids=base.terminal_node_ids,
        max_steps=base.max_steps,
        metadata={
            **dict(base.metadata),
            "trace": {
                "slice": "LM6A",
                "contract_variant": "worker_binds_repair_params",
            },
        },
    )


def _contract_to_jsonable(contract: Any) -> dict[str, Any]:
    return {
        "workflow_id": contract.workflow_id,
        "initial_params": [
            {
                "node_id": initial.node_id,
                "execution_params": dict(initial.execution_params),
            }
            for initial in contract.initial_params
        ],
        "expected_refs": [
            {
                "node_id": ref.node_id,
                "execution_ref": ref.execution_ref,
            }
            for ref in contract.expected_refs
        ],
        "rules": [
            {
                "node_id": rule.node_id,
                "steps_by_seen_count": [
                    step.__class__.__name__ for step in rule.steps_by_seen_count
                ],
            }
            for rule in contract.rules
        ],
        "metadata": dict(contract.metadata),
    }


def _legacy_acceptance_criteria_projection(
    packet: Mapping[str, Any],
) -> dict[str, Any]:
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


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _hidden_answer_leaks(value: Any) -> list[str]:
    rendered = json.dumps(value, sort_keys=True, default=str)
    leaks = []
    for needle in ("PROBE_REPAIR_CODE", "A = 42.0", "BindStepSpec.base_params.code"):
        if needle in rendered:
            leaks.append(needle)
    return leaks


def _decision_record(
    *,
    decision: str,
    reason: str,
    phase: str,
    live_repair_dispatched: bool = False,
    verify_repair_ran: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "schema": "rook.lm6a_decision:v1",
        "decision": decision,
        "reason": reason,
        "phase": phase,
        "live_repair_dispatched": live_repair_dispatched,
        "verify_repair_ran": verify_repair_ran,
        **extra,
    }


def _run_live_create_and_verify(*, agent: Any) -> dict[str, Any]:
    from lm5k_worker_probe import _script_body_gotcha_packet
    from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
    from rook.agent.plan_graph_workflow_contract import compile_workflow_contract
    from rook.learning.plan_graph_runner import apply_verifier_step

    contract = _lm6a_bind_free_contract()
    scaffold = compile_workflow_contract(contract)
    graph = scaffold.graph
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = dict(
        contract.initial_params[0].execution_params
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
        "workflow_contract": contract,
        "scaffold": scaffold,
        "graph": graph,
        "convention_packets": (_script_body_gotcha_packet(),),
        "anchor_binding": anchor_binding,
        "live_create_summary": live_create_summary,
        "verify_create_summary": verify_create_summary,
    }


def _await(awaitable: Any) -> Any:
    import asyncio

    return asyncio.run(awaitable)


def _extract_script_receipt(graph: Any, node_id: str) -> dict[str, Any] | None:
    evidence = graph.nodes[node_id].evidence
    if evidence is None or not isinstance(evidence.receipt, Mapping):
        return None
    return dict(evidence.receipt)


def _live_result_summary(
    *,
    node_id: str,
    tool_name: str | None,
    node_status: str | None,
    outcome_status: str | None,
    verified: bool | None,
    receipt: Mapping[str, Any] | None,
    params_sha256: str | None = None,
) -> dict[str, Any]:
    repair_anchor = None
    receipt_sha256 = None
    if isinstance(receipt, Mapping):
        receipt_sha256 = _sha256_json(receipt)
        anchor = receipt.get("repair_anchor")
        if isinstance(anchor, Mapping):
            target_errors = anchor.get("target_errors")
            repair_anchor = {
                "component_guid": anchor.get("component_guid"),
                "language": anchor.get("language"),
            }
            if isinstance(target_errors, list):
                repair_anchor["target_errors"] = [
                    str(item)[:300] for item in target_errors[:3]
                ]
    summary = {
        "node_id": node_id,
        "tool_name": tool_name,
        "node_status": node_status,
        "outcome_status": outcome_status,
        "verified": verified,
        "receipt_status": (
            receipt.get("artifact_status") if isinstance(receipt, Mapping) else None
        ),
        "repair_anchor": repair_anchor,
        "receipt_sha256": receipt_sha256,
    }
    if params_sha256 is not None:
        summary["params_sha256"] = params_sha256
    return summary


def _worker_request_payload(
    *,
    scaffold: Any,
    graph: Any,
) -> dict[str, Any]:
    from lm5k_worker_probe import (
        _acceptance_criteria_evidence_packet,
        _script_body_gotcha_packet,
    )
    from rook.agent.local_worker_turn_context import (
        WorkerAllowedAction,
        build_local_worker_turn_context,
    )
    from rook.agent.local_worker_turn_request import (
        render_local_worker_turn_request_payload,
    )

    context = build_local_worker_turn_context(
        scaffold,
        graph,
        (),
        (),
        current_node_id="repair_same_component",
        knowledge=(
            _script_body_gotcha_packet(),
            _acceptance_criteria_evidence_packet(graph),
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


def _run_phase_a_recon(*, run_dir: Path, agent: Any) -> dict[str, Any]:
    live = _run_live_create_and_verify(agent=agent)
    _write_json(run_dir / "live_create_summary.json", live["live_create_summary"])
    _write_json(run_dir / "verify_create_summary.json", live["verify_create_summary"])
    _write_json(
        run_dir / "phase_a_recon.json",
        {
            "repair_anchor_target_errors_present": True,
            "anchor_binding": live["anchor_binding"],
        },
    )
    report = validate_worker_visible_source_routing(
        _LM6A_ROUTING_ARTIFACT,
        workflow_contract=live["workflow_contract"],
        graph=live["graph"],
        convention_packets=live["convention_packets"],
        worker_node_ids=("repair_same_component",),
    )
    if report.routability_evaluated is not True:
        decision = _decision_record(
            decision="gate_failed",
            reason="phase_a_routability_not_evaluated",
            phase="receipt_recon",
        )
        return {"decision": decision, "routing_report": report, **live}

    errors = [
        diagnostic
        for diagnostic in (*report.static_diagnostics, *report.routability_diagnostics)
        if diagnostic.severity == "error"
    ]
    if errors:
        decision = _decision_record(
            decision="gate_failed",
            reason="phase_a_routability_failed",
            phase="receipt_recon",
        )
        return {"decision": decision, "routing_report": report, **live}

    anchor_binding = live["anchor_binding"]
    if (
        not isinstance(anchor_binding.get("component_guid"), str)
        or not anchor_binding["component_guid"]
        or anchor_binding.get("language") != "csharp"
    ):
        decision = _decision_record(
            decision="gate_failed",
            reason="phase_a_anchor_binding_invalid",
            phase="receipt_recon",
        )
        return {"decision": decision, "routing_report": report, **live}

    sources = extract_acceptance_criteria_sources(
        workflow_contract=live["workflow_contract"],
        graph=live["graph"],
        convention_packets=live["convention_packets"],
    )
    packet = assemble_acceptance_criteria_packet(sources)
    visible = _legacy_acceptance_criteria_projection(packet)
    if _hidden_answer_leaks(visible):
        decision = _decision_record(
            decision="gate_failed",
            reason="phase_a_hidden_answer_leak",
            phase="receipt_recon",
        )
        return {
            "decision": decision,
            "routing_report": report,
            "acceptance_criteria_packet": packet,
            **live,
        }
    request_payload = _worker_request_payload(
        scaffold=live["scaffold"],
        graph=live["graph"],
    )
    if _hidden_answer_leaks(request_payload):
        decision = _decision_record(
            decision="gate_failed",
            reason="phase_a_hidden_answer_leak",
            phase="receipt_recon",
        )
        return {
            "decision": decision,
            "routing_report": report,
            "acceptance_criteria_packet": packet,
            **live,
        }

    return {
        "decision": None,
        "routing_report": report,
        "acceptance_criteria_packet": packet,
        "legacy_acceptance_criteria": visible,
        "request_payload": request_payload,
        **live,
    }


def _decision_from_worker_publication(
    *,
    publication_row: Mapping[str, Any],
    response_payload: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    status = publication_row.get("status")
    if status != "published" or response_payload is None:
        return _decision_record(
            decision="publication_failed",
            reason=str(publication_row.get("failure_reason") or status),
            phase="worker_publication",
        )

    kind = response_payload.get("kind")
    if kind == "action_request":
        return None
    if kind == "clarification_request":
        reason = "worker_clarified"
    elif kind == "refusal":
        reason = "worker_refused"
    elif kind == "observation":
        reason = (
            "worker_observation_action_intent_anomaly"
            if publication_row.get("observation_action_intent_anomaly") is True
            else "worker_observed"
        )
    else:
        reason = "worker_unknown_non_action"
    return _decision_record(
        decision="worker_declined",
        reason=reason,
        phase="worker_publication",
        worker_response_kind=str(kind),
        observation_action_intent_anomaly=bool(
            publication_row.get("observation_action_intent_anomaly")
        ),
        observation_action_intent_reasons=list(
            publication_row.get("observation_action_intent_reasons") or []
        ),
    )


def _decision_from_worker_action_apply(apply_result: Any) -> dict[str, Any]:
    return _decision_record(
        decision="rejected",
        reason=f"worker_action_apply_failed:{apply_result.reason}",
        phase="worker_action_apply",
        worker_action_apply={
            "applied": False,
            "reason": apply_result.reason,
            "params_sha256": apply_result.params_sha256,
        },
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
    run_dir = Path(run_root) / f"lm6a-{timestamp}-{_git_short_sha()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _diagnostic_json(diagnostic: Any) -> dict[str, Any]:
    return {
        "severity": diagnostic.severity,
        "code": diagnostic.code,
        "node_id": diagnostic.node_id,
        "route_id": diagnostic.route_id,
        "source_class": diagnostic.source_class,
        "source_path": diagnostic.source_path,
        "purpose": diagnostic.purpose,
        "message": diagnostic.message,
    }


def _routing_report_json(report: Any) -> dict[str, Any]:
    return {
        "schema": report.schema,
        "valid": report.valid,
        "routability_evaluated": report.routability_evaluated,
        "static_diagnostics": [
            _diagnostic_json(diagnostic)
            for diagnostic in report.static_diagnostics
        ],
        "routability_diagnostics": [
            _diagnostic_json(diagnostic)
            for diagnostic in report.routability_diagnostics
        ],
    }


def _dispatch_repair_and_verify(
    *,
    graph: Any,
    agent: Any,
    params_sha256: str | None,
    run_dir: Path,
) -> dict[str, Any]:
    from rook.learning.plan_graph_runner import apply_verifier_step

    repair_result = _await(agent.run_live_producer_node(graph, "repair_same_component"))
    graph = repair_result.graph
    repair_receipt = _extract_script_receipt(graph, "repair_same_component")
    repair_evidence = graph.nodes["repair_same_component"].evidence
    _write_json(
        run_dir / "live_repair_summary.json",
        _live_result_summary(
            node_id="repair_same_component",
            tool_name=repair_result.tool_name,
            node_status=graph.nodes["repair_same_component"].status,
            outcome_status=str(repair_result.outcome_status),
            verified=repair_evidence.verified if repair_evidence is not None else None,
            receipt=repair_receipt,
            params_sha256=params_sha256,
        ),
    )
    if repair_result.applied is not True:
        return {
            "decision": _decision_record(
                decision="rejected",
                reason=f"live_repair_failed:{repair_result.reason}",
                phase="live_repair",
                live_repair_dispatched=True,
                verify_repair_ran=False,
            )
        }

    verify_repair = apply_verifier_step(
        graph,
        "verify_repair",
        "repair_same_component",
    )
    _write_json(
        run_dir / "verify_repair_summary.json",
        {
            "verifier_node_id": "verify_repair",
            "source_node_id": "repair_same_component",
            "applied": verify_repair.applied,
            "outcome_status": verify_repair.outcome_status,
        },
    )
    accepted = (
        verify_repair.applied is True and verify_repair.outcome_status == "succeeded"
    )
    return {
        "decision": _decision_record(
            decision="accepted" if accepted else "rejected",
            reason="verify_repair_succeeded" if accepted else "verify_repair_failed",
            phase="verify_repair",
            live_repair_dispatched=True,
            verify_repair_ran=True,
        )
    }


def _run_probe(
    *,
    phase: str,
    model: str,
    endpoint: str,
    temperature: float,
    timeout_s: float,
    excerpt_chars: int,
    run_root: str | Path,
    agent: Any,
) -> Path:
    run_dir = _new_run_dir(run_root)
    git_commit = _git_short_sha()
    _write_json(
        run_dir / "manifest.json",
        {
            "script_schema": SCRIPT_SCHEMA,
            "git_commit": git_commit,
            "phase": phase,
            "model": model,
            "endpoint": endpoint,
            "temperature": temperature,
            "raw_artifacts": "local evidence under probe_runs; do not commit",
        },
    )

    recon = _run_phase_a_recon(run_dir=run_dir, agent=agent)
    if recon.get("routing_report") is not None:
        _write_json(
            run_dir / "routing_validation.json",
            _routing_report_json(recon["routing_report"]),
        )
    if recon.get("acceptance_criteria_packet") is not None:
        _write_json(
            run_dir / "acceptance_criteria_packet.json",
            recon["acceptance_criteria_packet"],
        )
    if recon.get("decision") is not None:
        _write_json(run_dir / "decision.json", recon["decision"])
        return run_dir
    if phase == "receipt_recon":
        decision = _decision_record(
            decision="gate_passed",
            reason="receipt_recon_passed",
            phase="receipt_recon",
        )
        _write_json(run_dir / "decision.json", decision)
        return run_dir

    publication = run_two_pass_worker_publication(
        recon["request_payload"],
        model=model,
        endpoint=endpoint,
        temperature=temperature,
        timeout_s=timeout_s,
        excerpt_chars=excerpt_chars,
    )
    _write_json(run_dir / "worker_publication_row.json", publication.row)
    decision = _decision_from_worker_publication(
        publication_row=publication.row,
        response_payload=publication.response_payload,
    )
    if decision is not None:
        _write_json(run_dir / "decision.json", decision)
        return run_dir

    response_payload = publication.response_payload
    action_input = response_payload["input"]
    _write_json(run_dir / "worker_action.json", response_payload)
    apply_result = apply_worker_action_to_node(
        recon["graph"],
        "repair_same_component",
        action_id=response_payload["action_id"],
        action_input=action_input,
        anchor_binding=recon["anchor_binding"],
    )
    if apply_result.applied is not True:
        _write_json(
            run_dir / "decision.json",
            _decision_from_worker_action_apply(apply_result),
        )
        return run_dir

    final = _dispatch_repair_and_verify(
        graph=apply_result.graph,
        agent=agent,
        params_sha256=apply_result.params_sha256,
        run_dir=run_dir,
    )
    _write_json(run_dir / "decision.json", final["decision"])
    return run_dir


def main(argv: list[str] | None = None) -> int:
    _args(argv)
    raise SystemExit("LM6A runtime flow is implemented in later tasks")


if __name__ == "__main__":
    sys.exit(main())
