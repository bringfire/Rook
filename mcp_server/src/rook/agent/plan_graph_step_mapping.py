"""LM4P accepted-selection -> typed Step mapper (agent layer).

map_accepted_proposal_to_step delegates to the LM4O distrust gate (revalidate_proposal)
and, ONLY if the proposal is ACCEPTED, looks up the accepted node id in a caller-authored
``step_map`` of prebuilt LM4M Steps and returns that exact Step. It is a GATED LOOKUP, not
a Step builder: it never constructs/infers a Step, never re-derives (it asks LM4O, not the
selector), never dispatches, never loops, never mutates, and never falls back.

Containment (load-bearing):
- lookup, never construct: the module contains NO constructor call to ProducerStep /
  VerifierStep / BindStep (AST-guarded by the tests); it only returns the caller's object.
- delegate revalidation to LM4O: imports revalidate_proposal, NOT propose_next_node.
- no fallback: a rejected proposal yields no step even when ``step_map`` holds a valid entry
  for the node that is now correct.
- distrust the caller map: a missing entry (no_step_for_node), a non-Step value
  (step_map_invalid -- explicit tuple isinstance, checked before any field read), or a Step
  that targets a different node (step_node_mismatch) are each rejected cleanly.

Agent-layer is forced: imports both the LM4M Step types (agent) and LM4O revalidate_proposal
(learning). Pure-of-execution: never mutates proposal/graph/step_map; ``step`` is non-None
only on mapped=True and is the same object as ``step_map[accepted]``. NO base_agent /
dispatcher / server / runner / model import.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from rook.agent.plan_graph_sequence_runner import (
    BindStep,
    ProducerStep,
    Step,
    VerifierStep,
)
from rook.learning.plan_graph_revalidation import RevalidationResult, revalidate_proposal

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph
    from rook.learning.plan_graph_selector import NodeSelectionProposal


StepMappingFailure = Literal[
    "revalidation_rejected",
    "no_step_for_node",
    "step_map_invalid",
    "step_node_mismatch",
]

_DEFAULT_EXPECTED_SELECTOR_IDS = ("unique_ready_node:v1",)


@dataclass(frozen=True)
class StepMappingResult:
    mapped: bool
    step: Step | None
    accepted_node_id: str | None
    failure: StepMappingFailure | None
    reason: str
    revalidation: RevalidationResult


def _step_target_node_id(step: Step) -> str:
    """The node a Step acts on. Runs only after the caller value is confirmed a real Step."""
    if isinstance(step, VerifierStep):
        return step.verifier_node_id
    # ProducerStep and BindStep both carry ``node_id``.
    return step.node_id


def _not_mapped(
    failure: StepMappingFailure,
    reason: str,
    accepted_node_id: str | None,
    revalidation: RevalidationResult,
) -> StepMappingResult:
    return StepMappingResult(
        mapped=False,
        step=None,
        accepted_node_id=accepted_node_id,
        failure=failure,
        reason=reason,
        revalidation=revalidation,
    )


def map_accepted_proposal_to_step(
    proposal: "NodeSelectionProposal",
    graph: "PlanGraph",
    step_map: "Mapping[str, Step]",
    expected_selector_ids: tuple[str, ...] = _DEFAULT_EXPECTED_SELECTOR_IDS,
) -> StepMappingResult:
    """Revalidate ``proposal`` via LM4O, then look up the accepted node in ``step_map``.

    Returns the caller's prebuilt Step verbatim on ACCEPT + a matching, well-formed,
    node-targeted map entry. Otherwise a typed not-mapped result. Never constructs a Step,
    never re-derives, never dispatches, never falls back, never mutates inputs.
    """
    # 1. Delegate distrust + revalidation to LM4O (never re-derive here).
    revalidation = revalidate_proposal(proposal, graph, expected_selector_ids)

    # 2. A rejected proposal yields no step -- no fallback.
    if revalidation.decision != "ACCEPT":
        return _not_mapped(
            "revalidation_rejected",
            f"revalidation rejected the proposal: {revalidation.reject_reason}",
            None,
            revalidation,
        )

    accepted = revalidation.accepted_node_id

    # 3. Look up the accepted node in the caller-authored map -- refuse to invent.
    if accepted not in step_map:
        return _not_mapped(
            "no_step_for_node",
            f"no step_map entry for accepted node {accepted!r}",
            accepted,
            revalidation,
        )

    step = step_map[accepted]

    # 4. Distrust the map value: it must be a real LM4M Step (explicit tuple isinstance,
    #    never the Step union alias at runtime), checked before reading any field.
    if not isinstance(step, (ProducerStep, VerifierStep, BindStep)):
        return _not_mapped(
            "step_map_invalid",
            f"step_map entry for {accepted!r} is not a ProducerStep/VerifierStep/BindStep",
            accepted,
            revalidation,
        )

    # 5. The mapped Step must target the accepted node -- the map cannot redirect execution.
    if _step_target_node_id(step) != accepted:
        return _not_mapped(
            "step_node_mismatch",
            f"mapped step targets {_step_target_node_id(step)!r}, not accepted {accepted!r}",
            accepted,
            revalidation,
        )

    # 6. Gated lookup succeeds: return the caller's exact Step.
    return StepMappingResult(
        mapped=True,
        step=step,
        accepted_node_id=accepted,
        failure=None,
        reason="accepted node mapped to caller-authored step",
        revalidation=revalidation,
    )
