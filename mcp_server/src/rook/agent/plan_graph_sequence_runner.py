"""LM4M explicit live mixed-step sequence runner (agent layer).

run_explicit_sequence left-folds a CALLER-AUTHORED ordered list of typed steps
(ProducerStep / VerifierStep / BindStep) over a PlanGraph, threading the graph and
stopping at the first failed/not-applied step. Each step kind delegates to an existing
seam: live producer (run_live_producer_node via the LM4G SupportsLiveProducerNode
Protocol), pure apply_verifier_step (learning), LM4L apply_memory_bound_params (agent).

The LIVE, agent-layer, mixed-step sibling of LM3A's pure plan_graph_walker.py (which
replays one (node_id, raw_result) kind via apply_tool_result). Like the walker, this is
NOT a scheduler: it never selects a node, branches, loops, inspects topology to choose,
or constructs terminal outcomes. The caller dictates the exact sequence; the terminal
`done` marker stays OUTSIDE this runner. ``completed`` means SEQUENCE-completed (all
supplied steps ran and passed), NOT graph_status == "complete".

Boundary: agent -> {agent LM4G/LM4L, learning}, one way. NO runnable_nodes import (the
clean no-selection proof), NO apply_outcome import (no terminal construction), NO
base_agent/server/dispatcher import (the runner arrives only as a structural Protocol).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    LiveProducerRecord,
    SupportsLiveProducerNode,
    build_live_producer_record,
)
from rook.agent.plan_graph_param_apply import (
    MemoryParamApplyResult,
    apply_memory_bound_params,
)
from rook.learning.plan_graph import OutcomeStatus
from rook.learning.plan_graph_runner import VerifierStepResult, apply_verifier_step

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


@dataclass(frozen=True)
class ProducerStep:
    node_id: str
    expectation: LiveProducerExpectation | None = None


@dataclass(frozen=True)
class VerifierStep:
    verifier_node_id: str
    source_node_id: str
    expected_outcome: OutcomeStatus | None = None


@dataclass(frozen=True)
class BindStep:
    node_id: str
    base_params: Mapping
    bindings: Mapping[str, tuple[str, ...]]


Step = ProducerStep | VerifierStep | BindStep


@dataclass(frozen=True)
class StepOutcome:
    kind: Literal["producer", "verifier", "bind"]
    label: str
    ok: bool
    producer_record: LiveProducerRecord | None = None
    verifier_result: VerifierStepResult | None = None
    bind_result: MemoryParamApplyResult | None = None


@dataclass(frozen=True)
class SequenceResult:
    graph: "PlanGraph"
    completed: bool
    stopped_at: int | None
    step_results: tuple[StepOutcome, ...]
    remaining_steps: tuple[Step, ...]


async def run_explicit_sequence(
    runner: SupportsLiveProducerNode,
    graph: "PlanGraph",
    steps: "Sequence[Step]",
) -> SequenceResult:
    """Left-fold an explicit, caller-authored step list over ``graph``.

    Threads the graph through each step (every delegated seam returns a graph: advanced
    on apply, input-unchanged on not-applied), stopping at the first step whose ``ok`` is
    False. ``completed`` means SEQUENCE-completed (all supplied steps ran and passed), NOT
    ``graph_status == "complete"`` -- the terminal ``done`` marker stays outside this
    runner. No node selection, no branching/looping beyond the linear fold + early stop,
    no rollback. A producer step that applies but fails its expectation still advances the
    graph (the returned graph reflects the dispatch).
    """
    executed: list[StepOutcome] = []

    for index, step in enumerate(steps):
        if isinstance(step, ProducerStep):
            result = await runner.run_live_producer_node(graph, step.node_id)
            graph = result.graph
            record = build_live_producer_record(result, step.expectation)
            ok = (
                record.passed is True
                if step.expectation is not None
                else result.applied is True
            )
            executed.append(
                StepOutcome(
                    kind="producer",
                    label=step.node_id,
                    ok=ok,
                    producer_record=record,
                )
            )
        elif isinstance(step, VerifierStep):
            vres = apply_verifier_step(
                graph, step.verifier_node_id, step.source_node_id
            )
            graph = vres.graph
            ok = vres.applied and (
                step.expected_outcome is None
                or vres.outcome_status == step.expected_outcome
            )
            executed.append(
                StepOutcome(
                    kind="verifier",
                    label=step.verifier_node_id,
                    ok=ok,
                    verifier_result=vres,
                )
            )
        else:  # BindStep -- the closed taxonomy's third and final kind
            bres = apply_memory_bound_params(
                graph, step.node_id, step.base_params, step.bindings
            )
            graph = bres.graph
            ok = bres.applied
            executed.append(
                StepOutcome(
                    kind="bind",
                    label=step.node_id,
                    ok=ok,
                    bind_result=bres,
                )
            )

        if not ok:
            return SequenceResult(
                graph=graph,
                completed=False,
                stopped_at=index,
                step_results=tuple(executed),
                remaining_steps=tuple(steps[index + 1 :]),
            )

    return SequenceResult(
        graph=graph,
        completed=True,
        stopped_at=None,
        step_results=tuple(executed),
        remaining_steps=(),
    )
