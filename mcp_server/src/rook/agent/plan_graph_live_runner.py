"""LM4G one-node live producer runner / eval harness (Stage 5).

A downstream, behaviorally-PURE record/eval layer over ONE LiveProducerResult:
- build_live_producer_record(result, expectation) reads the RETURNED graph node
  (status + evidence) into a structured record and evaluates it against a
  declarative expectation (declared fields -> mismatches + pass/fail).
- run_and_record_live_producer_node(runner, graph, node_id, expectation) is a thin
  async wrapper: await runner.run_live_producer_node(...), then build the record.

Boundary: agent-layer (consumes LiveProducerResult) but NO I/O, no dispatcher, no
Rhino, no base_agent import. The runner arrives only as a structural Protocol. The
graph node's evidence is the canonical execution record -- no raw side channel.
One node only: no selection, no successor advancement, no scheduler.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


@dataclass(frozen=True)
class LiveProducerExpectation:
    applied: bool | None = None
    outcome_status: str | None = None
    node_status: str | None = None
    tool_status: str | None = None
    verified: bool | None = None
    artifact_status: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class Mismatch:
    field: str
    expected: Any
    observed: Any


@dataclass(frozen=True)
class LiveProducerRecord:
    node_id: str
    tool_name: str | None
    applied: bool
    reason: str | None
    outcome_status: str | None
    node_status: str | None
    tool_status: str | None
    verified: bool | None
    artifact_status: str | None
    repair_anchor_guid: str | None
    declared_params: dict | None
    expectation: "LiveProducerExpectation | None"
    evaluated: bool
    passed: bool | None
    mismatches: tuple[Mismatch, ...]


class SupportsLiveProducerNode(Protocol):
    async def run_live_producer_node(
        self, graph: "PlanGraph", node_id: str
    ) -> LiveProducerResult: ...


_EXPECTATION_FIELDS = (
    "applied",
    "outcome_status",
    "node_status",
    "tool_status",
    "verified",
    "artifact_status",
    "reason",
)


def _safe_declared_params(node: Any) -> dict | None:
    """Best-effort declared-params capture; deep copy when possible, else None.
    NEVER raises. Mirrors LM4A's validity rule: a non-Mapping execution_params is
    execution_params_invalid, NOT declared params (do not dict()-coerce). A
    non-deepcopyable Mapping (the shape that makes LM4A return params_copy_failed)
    is swallowed to None rather than crashing the record."""
    if node is None:
        return None
    meta = getattr(node, "metadata", None)
    if not isinstance(meta, dict) or EXECUTION_PARAMS_KEY not in meta:
        return None
    params_source = meta[EXECUTION_PARAMS_KEY]
    if not isinstance(params_source, Mapping):
        return None
    try:
        return deepcopy(dict(params_source))
    except Exception:
        return None


def _artifact_status(evidence: Any) -> str | None:
    receipt = getattr(evidence, "receipt", None)
    if isinstance(receipt, dict):
        value = receipt.get("artifact_status")
        if isinstance(value, str):
            return value
    return None


def _repair_anchor_guid(evidence: Any) -> str | None:
    anchor = getattr(evidence, "repair_anchor", None)
    if isinstance(anchor, dict):
        value = anchor.get("component_guid")
        if isinstance(value, str) and value:
            return value
    return None


def _evaluate(
    observed: dict[str, Any], expectation: "LiveProducerExpectation | None"
) -> tuple[bool, bool | None, tuple[Mismatch, ...]]:
    if expectation is None:
        return False, None, ()
    mismatches: list[Mismatch] = []
    for field in _EXPECTATION_FIELDS:
        expected = getattr(expectation, field)
        if expected is None:
            continue
        actual = observed[field]
        if actual != expected:
            mismatches.append(Mismatch(field=field, expected=expected, observed=actual))
    return True, len(mismatches) == 0, tuple(mismatches)


def build_live_producer_record(
    result: LiveProducerResult,
    expectation: "LiveProducerExpectation | None" = None,
) -> LiveProducerRecord:
    """Build a structured record from ONE LiveProducerResult + its returned graph,
    then evaluate against an optional declarative expectation. Reads result.graph
    (the fresh reducer copy on applied paths); never crashes on not-applied /
    missing-node / non-copyable params."""
    node = result.graph.nodes.get(result.node_id)
    if node is None:
        node_status: str | None = None
        tool_status: str | None = None
        verified: bool | None = None
        artifact_status: str | None = None
        repair_anchor_guid: str | None = None
    else:
        node_status = node.status
        evidence = getattr(node, "evidence", None)
        tool_status = getattr(evidence, "tool_status", None) if evidence is not None else None
        verified = getattr(evidence, "verified", None) if evidence is not None else None
        artifact_status = _artifact_status(evidence)
        repair_anchor_guid = _repair_anchor_guid(evidence)

    observed = {
        "applied": result.applied,
        "outcome_status": result.outcome_status,
        "node_status": node_status,
        "tool_status": tool_status,
        "verified": verified,
        "artifact_status": artifact_status,
        "reason": result.reason,
    }
    evaluated, passed, mismatches = _evaluate(observed, expectation)

    return LiveProducerRecord(
        node_id=result.node_id,
        tool_name=result.tool_name,
        applied=result.applied,
        reason=result.reason,
        outcome_status=result.outcome_status,
        node_status=node_status,
        tool_status=tool_status,
        verified=verified,
        artifact_status=artifact_status,
        repair_anchor_guid=repair_anchor_guid,
        declared_params=_safe_declared_params(node),
        expectation=expectation,
        evaluated=evaluated,
        passed=passed,
        mismatches=mismatches,
    )


async def run_and_record_live_producer_node(
    runner: SupportsLiveProducerNode,
    graph: "PlanGraph",
    node_id: str,
    expectation: "LiveProducerExpectation | None" = None,
) -> LiveProducerRecord:
    """Thin live wrapper: drive ONE producer node through the runner, then record +
    evaluate. One node only -- no selection, no successor advancement, no
    scheduler."""
    result = await runner.run_live_producer_node(graph, node_id)
    return build_live_producer_record(result, expectation)
