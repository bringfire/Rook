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
    _probe_contract,
)
from rook.agent.local_worker_acceptance_criteria import (  # noqa: E402
    assemble_acceptance_criteria_packet,
)
from rook.agent.local_worker_acceptance_criteria_sources import (  # noqa: E402
    extract_acceptance_criteria_sources,
)
from rook.agent.local_worker_source_routing_validator import (  # noqa: E402
    validate_worker_visible_source_routing,
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
    raise RuntimeError("live create/verify is implemented in Task 10")


def _run_phase_a_recon(*, run_dir: Path, agent: Any) -> dict[str, Any]:
    live = _run_live_create_and_verify(agent=agent)
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

    return {
        "decision": None,
        "routing_report": report,
        "acceptance_criteria_packet": packet,
        "legacy_acceptance_criteria": visible,
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


def main(argv: list[str] | None = None) -> int:
    _args(argv)
    raise SystemExit("LM6A runtime flow is implemented in later tasks")


if __name__ == "__main__":
    sys.exit(main())
