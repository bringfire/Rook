"""One-turn Worker-authored initial C# body handoff."""

from __future__ import annotations

from rook.agent.minimal_csharp_repair_handoff import (
    ValidatedPlannerDraft,
    _require_validated_draft,
)
from rook.agent.plan_graph_workflow_contract import (
    ExpectedNodeRef,
    InitialNodeParams,
    ProducerStepSpec,
    RookWorkflowContract,
    VerifierStepSpec,
    WorkflowNodeRule,
    WorkflowTemplateRef,
)


_WORKFLOW_ID = "minimal_csharp_initial_body_handoff"
_TEMPLATE_ID = "gh_csharp_create_verify"
_CREATE_NODE_ID = "create_script"
_VERIFY_NODE_ID = "verify_create"
_TERMINAL_NODE_ID = "done"
_ACTION_ID = "draft_create_body"


def _build_initial_body_contract(
    draft: ValidatedPlannerDraft,
) -> RookWorkflowContract:
    _require_validated_draft(draft)
    return RookWorkflowContract(
        workflow_id=_WORKFLOW_ID,
        template=WorkflowTemplateRef(
            descriptor={
                "domain": "grasshopper",
                "operation": "create_verify",
                "language": "csharp",
            },
            expected_template_id=_TEMPLATE_ID,
        ),
        initial_params=(
            InitialNodeParams(
                node_id=_CREATE_NODE_ID,
                execution_params={
                    "pins_in": list(draft.interface.inputs),
                    "pins_out": [
                        f"{output.name}:{output.type}"
                        for output in draft.interface.outputs
                    ],
                    "name": "RookMinimalInitialBodyHandoff",
                    "x": 375,
                    "y": 1080,
                },
            ),
        ),
        rules=(
            WorkflowNodeRule(
                node_id=_CREATE_NODE_ID,
                steps_by_seen_count=(ProducerStepSpec(_CREATE_NODE_ID),),
            ),
            WorkflowNodeRule(
                node_id=_VERIFY_NODE_ID,
                steps_by_seen_count=(
                    VerifierStepSpec(
                        verifier_node_id=_VERIFY_NODE_ID,
                        source_node_id=_CREATE_NODE_ID,
                        expected_outcome="succeeded",
                    ),
                ),
            ),
        ),
        terminal_node_ids=(_TERMINAL_NODE_ID,),
        expected_refs=(
            ExpectedNodeRef(_CREATE_NODE_ID, "gh_create_csharp_script:v1"),
        ),
        max_steps=4,
        metadata={
            "capability": "grasshopper_csharp_component",
            "acceptance": "clean_compile_receipt",
        },
    )
