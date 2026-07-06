#!/usr/bin/env python
"""LM6A live worker splice probe.

Deterministic implementation plus post-merge live evidence script. The script
manually sequences create/verify/worker/apply/repair/verify and writes bounded
local artifacts under probe_runs/.
"""

from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None) -> int:
    _args(argv)
    raise SystemExit("LM6A runtime flow is implemented in later tasks")


if __name__ == "__main__":
    sys.exit(main())
