"""LM4Q single mapped-step executor (agent layer) -- first bounded execution authority.

execute_mapped_step consumes an LM4P StepMappingResult and, ONLY if the mapping is a green
light, dispatches exactly that one Step to the existing seam for its kind:
- ProducerStep -> runner.run_live_producer_node (the LM4A/G SupportsLiveProducerNode seam),
- VerifierStep -> apply_verifier_step (learning),
- BindStep     -> apply_memory_bound_params (LM4L).
It returns the advanced graph + the NATIVE seam result. It answers only "am I allowed to run
this already-mapped Step?", never "what should I run?".

Containment (load-bearing):
- execute the artifact, never rebuild the ladder: consumes a StepMappingResult; never imports
  or references propose_next_node / revalidate_proposal / map_accepted_proposal_to_step /
  runnable_nodes (AST-guarded).
- one step, no loop, no fold, no run_explicit_sequence (AST-guarded); no terminal apply_outcome.
- raw dispatch-and-report: never computes pass/fail, never reads ProducerStep.expectation /
  VerifierStep.expected_outcome, never imports build_live_producer_record. Once a seam is
  invoked, ran=True even if the seam result is not-applied/failed -- the native result carries
  that truth, LM4Q never reinterprets it.
- distrust the public artifact's shape: a forged mapped-but-not-a-Step value is refused
  (mapping_invalid) via an explicit-tuple isinstance BEFORE any field read -- never crashes,
  never misdispatches. (This is artifact-shape validation, NOT LM4P's target-node validation.)
- no fallback: a refused mapping runs nothing, even when a different, now-correct Step exists.

Failures are ONLY pre-execution refusals: not_mapped / mapping_invalid / runner_required. On
every refusal result.graph is the INPUT graph (unchanged). Pure-of-policy: never mutates the
mapping; verifier/bind never touch the runner. NO base_agent / dispatcher / server / model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from rook.agent.plan_graph_live import LiveProducerResult
from rook.agent.plan_graph_live_runner import SupportsLiveProducerNode
from rook.agent.plan_graph_param_apply import (
    MemoryParamApplyResult,
    apply_memory_bound_params,
)
from rook.agent.plan_graph_sequence_runner import BindStep, ProducerStep, VerifierStep
from rook.agent.plan_graph_step_mapping import StepMappingResult
from rook.learning.plan_graph_runner import VerifierStepResult, apply_verifier_step

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


StepExecutionFailure = Literal["not_mapped", "mapping_invalid", "runner_required"]


@dataclass(frozen=True)
class StepExecutionResult:
    ran: bool
    kind: Literal["producer", "verifier", "bind"] | None
    graph: "PlanGraph"
    failure: StepExecutionFailure | None
    reason: str
    mapping: StepMappingResult
    producer_result: LiveProducerResult | None = None
    verifier_result: VerifierStepResult | None = None
    bind_result: MemoryParamApplyResult | None = None


def _refused(
    failure: StepExecutionFailure,
    reason: str,
    graph: "PlanGraph",
    mapping: StepMappingResult,
) -> StepExecutionResult:
    return StepExecutionResult(
        ran=False,
        kind=None,
        graph=graph,
        failure=failure,
        reason=reason,
        mapping=mapping,
    )


async def execute_mapped_step(
    mapping: StepMappingResult,
    graph: "PlanGraph",
    runner: SupportsLiveProducerNode | None = None,
) -> StepExecutionResult:
    """Execute exactly the one Step carried by an accepted ``mapping``.

    Gate -> structural check -> dispatch one Step to its existing seam -> report the native
    result + advanced graph. No selection, no evaluation, no loop, no terminal construction,
    no fallback. On any pre-execution refusal, returns the INPUT ``graph`` unchanged.
    """
    # 1. Gate: the mapping must be a green light.
    if mapping.mapped is not True or mapping.step is None:
        return _refused(
            "not_mapped",
            "mapping is not an accepted, step-carrying result",
            graph,
            mapping,
        )

    step = mapping.step

    # 2. Structural check: distrust the public artifact's shape BEFORE reading any field.
    #    Explicit tuple isinstance -- never the Step union alias at runtime.
    if not isinstance(step, (ProducerStep, VerifierStep, BindStep)):
        return _refused(
            "mapping_invalid",
            "mapping.step is not a ProducerStep/VerifierStep/BindStep",
            graph,
            mapping,
        )

    # 3. Dispatch with explicit per-kind branches (no final else-as-bind).
    if isinstance(step, ProducerStep):
        if runner is None:
            return _refused(
                "runner_required",
                f"ProducerStep {step.node_id!r} needs a runner but none was supplied",
                graph,
                mapping,
            )
        result = await runner.run_live_producer_node(graph, step.node_id)
        return StepExecutionResult(
            ran=True,
            kind="producer",
            graph=result.graph,
            failure=None,
            reason=f"executed producer step {step.node_id!r}",
            mapping=mapping,
            producer_result=result,
        )
    elif isinstance(step, VerifierStep):
        vres = apply_verifier_step(graph, step.verifier_node_id, step.source_node_id)
        return StepExecutionResult(
            ran=True,
            kind="verifier",
            graph=vres.graph,
            failure=None,
            reason=f"executed verifier step {step.verifier_node_id!r}",
            mapping=mapping,
            verifier_result=vres,
        )
    elif isinstance(step, BindStep):
        bres = apply_memory_bound_params(
            graph, step.node_id, step.base_params, step.bindings
        )
        return StepExecutionResult(
            ran=True,
            kind="bind",
            graph=bres.graph,
            failure=None,
            reason=f"executed bind step {step.node_id!r}",
            mapping=mapping,
            bind_result=bres,
        )
