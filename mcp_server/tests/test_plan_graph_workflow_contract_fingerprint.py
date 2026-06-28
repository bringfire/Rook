"""LM4X workflow contract snapshot and compile-record tests."""

from __future__ import annotations

import pytest

import rook.agent.plan_graph_workflow_contract as contract_module
from rook.agent.plan_graph_current_step_provider import (
    CATALOG_CURRENT_STEP_PROVIDER_ID,
)
from rook.agent.plan_graph_workflow_contract import (
    CONTRACT_FINGERPRINT_ALGORITHM,
    WORKFLOW_CONTRACT_COMPILER_ID,
    WORKFLOW_CONTRACT_SCHEMA,
    BindStepSpec,
    ExpectedNodeRef,
    InitialNodeParams,
    ProducerStepSpec,
    RookWorkflowContract,
    VerifierStepSpec,
    WorkflowCompileRecord,
    WorkflowContractSnapshot,
    WorkflowNodeRule,
    WorkflowTemplateRef,
    compile_workflow_contract,
    snapshot_workflow_contract,
)


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}
_DESCRIPTOR_REORDERED = {
    "language": "csharp",
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
}
_TEMPLATE_ID = "gh_csharp_create_verify_repair_verify"
_GOLDEN_REPAIR_FINGERPRINT = (
    "f9253a62991c3afd5af99abab9a4497e82c7819843357d4757c2007b8c8ec7a7"
)


def _create_params(*, pins_as_tuple: bool = False, reordered: bool = False) -> dict:
    pins_in = () if pins_as_tuple else []
    pins_out = ("A:double",) if pins_as_tuple else ["A:double"]
    if reordered:
        return {
            "y": 1080,
            "x": 350,
            "name": "LM4XWorkflowContractFingerprint",
            "pins_out": pins_out,
            "pins_in": pins_in,
            "code": "A = DefinitelyMissingSymbol;",
        }
    return {
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": pins_in,
        "pins_out": pins_out,
        "name": "LM4XWorkflowContractFingerprint",
        "x": 350,
        "y": 1080,
    }


def _repair_params(*, reordered: bool = False) -> dict:
    if reordered:
        return {"language": "csharp", "mode": "body", "code": "A = 42.0;"}
    return {"code": "A = 42.0;", "mode": "body", "language": "csharp"}


def _repair_rules(
    *,
    reversed_rules: bool = False,
    reversed_repair_steps: bool = False,
):
    repair_steps = (
        BindStepSpec(
            "repair_same_component",
            _repair_params(),
            {"guid": ("repair_anchor", "component_guid")},
        ),
        ProducerStepSpec("repair_same_component"),
    )
    if reversed_repair_steps:
        repair_steps = tuple(reversed(repair_steps))
    rules = (
        WorkflowNodeRule("create_script", (ProducerStepSpec("create_script"),)),
        WorkflowNodeRule(
            "verify_create",
            (
                VerifierStepSpec(
                    "verify_create",
                    "create_script",
                    expected_outcome="needs_repair",
                ),
            ),
        ),
        WorkflowNodeRule("repair_same_component", repair_steps),
        WorkflowNodeRule(
            "verify_repair",
            (
                VerifierStepSpec(
                    "verify_repair",
                    "repair_same_component",
                    expected_outcome="succeeded",
                ),
            ),
        ),
    )
    if reversed_rules:
        return tuple(reversed(rules))
    return rules


def _repair_contract(**overrides) -> RookWorkflowContract:
    values = {
        "workflow_id": "lm4x_repair_contract",
        "template": WorkflowTemplateRef(dict(_DESCRIPTOR), _TEMPLATE_ID),
        "initial_params": (
            InitialNodeParams("create_script", _create_params()),
        ),
        "rules": _repair_rules(),
        "terminal_node_ids": ("done",),
        "expected_refs": (
            ExpectedNodeRef("create_script", "gh_create_csharp_script:v1"),
            ExpectedNodeRef("repair_same_component", "gh_update_script:v1"),
        ),
        "max_steps": 6,
        "metadata": {
            "workflow_label": "LM4X repair contract",
            "trace": {"slice": "LM4X"},
        },
    }
    values.update(overrides)
    return RookWorkflowContract(**values)


def _snapshot(contract: RookWorkflowContract | None = None) -> WorkflowContractSnapshot:
    return snapshot_workflow_contract(contract or _repair_contract())


def test_snapshot_repair_contract_has_golden_fingerprint_and_selected_shape():
    snapshot = _snapshot()

    assert isinstance(snapshot, WorkflowContractSnapshot)
    assert snapshot.workflow_id == "lm4x_repair_contract"
    assert snapshot.workflow_id == snapshot.normalized_contract["workflow_id"]
    assert snapshot.normalized_contract["schema"] == WORKFLOW_CONTRACT_SCHEMA
    assert snapshot.contract_fingerprint == _GOLDEN_REPAIR_FINGERPRINT
    assert len(snapshot.contract_fingerprint) == 64
    assert snapshot.contract_fingerprint.islower()

    template = snapshot.normalized_contract["template"]
    assert template["descriptor"] == _DESCRIPTOR
    assert template["expected_template_id"] == _TEMPLATE_ID

    initial_params = snapshot.normalized_contract["initial_params"]
    assert initial_params[0]["node_id"] == "create_script"
    assert initial_params[0]["execution_params"]["pins_in"] == ()
    assert initial_params[0]["execution_params"]["pins_out"] == ("A:double",)

    rules = snapshot.normalized_contract["rules"]
    assert [rule["node_id"] for rule in rules] == [
        "create_script",
        "verify_create",
        "repair_same_component",
        "verify_repair",
    ]
    assert [
        tuple(step["kind"] for step in rule["steps_by_seen_count"])
        for rule in rules
    ] == [
        ("producer",),
        ("verifier",),
        ("bind", "producer"),
        ("verifier",),
    ]
    bind_step = rules[2]["steps_by_seen_count"][0]
    assert bind_step["bindings"]["guid"] == (
        "repair_anchor",
        "component_guid",
    )


def test_snapshot_does_not_call_template_selection(monkeypatch):
    def raising_select_template(*args, **kwargs):
        raise AssertionError("snapshot must not select a template")

    monkeypatch.setattr(contract_module, "select_template", raising_select_template)

    snapshot = snapshot_workflow_contract(_repair_contract())

    assert snapshot.contract_fingerprint == _GOLDEN_REPAIR_FINGERPRINT


def test_equivalent_contract_objects_have_same_snapshot_and_fingerprint():
    first = _repair_contract()
    second = _repair_contract(
        template=WorkflowTemplateRef(dict(_DESCRIPTOR_REORDERED), _TEMPLATE_ID),
        initial_params=(
            InitialNodeParams(
                "create_script",
                _create_params(pins_as_tuple=True, reordered=True),
            ),
        ),
        rules=(
            WorkflowNodeRule("create_script", (ProducerStepSpec("create_script"),)),
            WorkflowNodeRule(
                "verify_create",
                (
                    VerifierStepSpec(
                        "verify_create",
                        "create_script",
                        expected_outcome="needs_repair",
                    ),
                ),
            ),
            WorkflowNodeRule(
                "repair_same_component",
                (
                    BindStepSpec(
                        "repair_same_component",
                        _repair_params(reordered=True),
                        {"guid": ["repair_anchor", "component_guid"]},
                    ),
                    ProducerStepSpec("repair_same_component"),
                ),
            ),
            WorkflowNodeRule(
                "verify_repair",
                (
                    VerifierStepSpec(
                        "verify_repair",
                        "repair_same_component",
                        expected_outcome="succeeded",
                    ),
                ),
            ),
        ),
    )

    a = snapshot_workflow_contract(first)
    b = snapshot_workflow_contract(second)

    assert a.contract_fingerprint == b.contract_fingerprint
    assert a.normalized_contract == b.normalized_contract


def test_metadata_none_and_empty_metadata_are_fingerprint_equivalent():
    none_metadata = snapshot_workflow_contract(_repair_contract(metadata=None))
    empty_metadata = snapshot_workflow_contract(_repair_contract(metadata={}))

    assert none_metadata.contract_fingerprint == empty_metadata.contract_fingerprint
    assert none_metadata.normalized_contract["metadata"] == {}


@pytest.mark.parametrize(
    "contract",
    [
        _repair_contract(
            metadata={
                "workflow_label": "LM4X repair contract",
                "trace": {"slice": "LM4X-alt"},
            },
        ),
        _repair_contract(rules=_repair_rules(reversed_rules=True)),
        _repair_contract(
            rules=_repair_rules(reversed_repair_steps=True),
        ),
        _repair_contract(workflow_id="lm4x_repair_contract_alt"),
    ],
    ids=[
        "metadata-value",
        "rule-order",
        "repair-step-order",
        "workflow-id",
    ],
)
def test_fingerprint_changes_for_authored_artifact_changes(contract):
    assert snapshot_workflow_contract(contract).contract_fingerprint != (
        _GOLDEN_REPAIR_FINGERPRINT
    )


def test_snapshot_normalized_contract_is_deeply_immutable():
    snapshot = _snapshot()

    with pytest.raises(TypeError):
        snapshot.normalized_contract["late"] = True
    with pytest.raises(TypeError):
        snapshot.normalized_contract["metadata"]["trace"]["slice"] = "mutated"


def test_compile_scaffold_carries_snapshot_and_compile_record():
    scaffold = compile_workflow_contract(_repair_contract())

    assert scaffold.workflow_id == scaffold.contract_snapshot.workflow_id
    assert scaffold.workflow_id == scaffold.compile_record.workflow_id
    assert scaffold.workflow_id == (
        scaffold.contract_snapshot.normalized_contract["workflow_id"]
    )
    assert scaffold.metadata is scaffold.contract_snapshot.normalized_contract[
        "metadata"
    ]

    record = scaffold.compile_record
    assert isinstance(record, WorkflowCompileRecord)
    assert record.compiler_id == WORKFLOW_CONTRACT_COMPILER_ID
    assert record.contract_schema == WORKFLOW_CONTRACT_SCHEMA
    assert record.contract_fingerprint_algorithm == CONTRACT_FINGERPRINT_ALGORITHM
    assert record.contract_fingerprint == scaffold.contract_snapshot.contract_fingerprint
    assert record.provider_id == CATALOG_CURRENT_STEP_PROVIDER_ID
    assert record.expected_template_id == _TEMPLATE_ID
    assert record.selected_template_id == _TEMPLATE_ID
    assert record.graph_node_ids == tuple(sorted(scaffold.graph.nodes))
    assert record.initial_param_node_ids == ("create_script",)
    assert record.rule_node_ids == (
        "create_script",
        "verify_create",
        "repair_same_component",
        "verify_repair",
    )
    assert record.terminal_node_ids == ("done",)
    assert record.expected_refs == (
        ("create_script", "gh_create_csharp_script:v1"),
        ("repair_same_component", "gh_update_script:v1"),
    )
    assert record.step_kinds_by_rule == (
        ("create_script", ("producer",)),
        ("verify_create", ("verifier",)),
        ("repair_same_component", ("bind", "producer")),
        ("verify_repair", ("verifier",)),
    )
    assert record.max_steps == 6
    assert not hasattr(record, "metadata")
    assert not hasattr(record, "descriptor")
    assert not hasattr(record, "compiled_at")
    assert not hasattr(record, "graph_status")


def test_compile_record_is_deterministic_for_repeated_compiles():
    contract = _repair_contract()

    first = compile_workflow_contract(contract).compile_record
    second = compile_workflow_contract(contract).compile_record

    assert first == second


@pytest.mark.parametrize(
    "contract_factory,exc_type",
    [
        (lambda: _repair_contract(workflow_id=""), ValueError),
        (
            lambda: _repair_contract(
                template=WorkflowTemplateRef({1: "grasshopper"}, _TEMPLATE_ID)
            ),
            TypeError,
        ),
        (
            lambda: _repair_contract(
                template=WorkflowTemplateRef(
                    {"domain": "grasshopper", "operation": 1},
                    _TEMPLATE_ID,
                )
            ),
            TypeError,
        ),
        (lambda: _repair_contract(max_steps=True), TypeError),
        (lambda: _repair_contract(max_steps=0), ValueError),
        (
            lambda: _repair_contract(
                initial_params=(
                    InitialNodeParams("create_script", {}),
                    InitialNodeParams("create_script", {}),
                )
            ),
            ValueError,
        ),
        (
            lambda: _repair_contract(rules=()),
            ValueError,
        ),
        (
            lambda: _repair_contract(
                rules=(WorkflowNodeRule("create_script", ()),)
            ),
            ValueError,
        ),
        (
            lambda: _repair_contract(
                rules=(
                    WorkflowNodeRule("create_script", (object(),)),
                )
            ),
            TypeError,
        ),
        (
            lambda: _repair_contract(
                rules=(
                    WorkflowNodeRule(
                        "create_script",
                        (ProducerStepSpec("verify_create"),),
                    ),
                )
            ),
            ValueError,
        ),
        (
            lambda: _repair_contract(
                rules=(
                    WorkflowNodeRule(
                        "verify_create",
                        (VerifierStepSpec("verify_create", ""),),
                    ),
                )
            ),
            ValueError,
        ),
        (
            lambda: _repair_contract(
                rules=(
                    WorkflowNodeRule(
                        "verify_create",
                        (
                            VerifierStepSpec(
                                "verify_create",
                                "create_script",
                                "usable",
                            ),
                        ),
                    ),
                )
            ),
            ValueError,
        ),
        (
            lambda: _repair_contract(
                rules=(
                    WorkflowNodeRule(
                        "repair_same_component",
                        (
                            BindStepSpec(
                                "repair_same_component",
                                {},
                                {1: ("repair_anchor",)},
                            ),
                        ),
                    ),
                )
            ),
            TypeError,
        ),
        (
            lambda: _repair_contract(
                rules=(
                    WorkflowNodeRule(
                        "repair_same_component",
                        (
                            BindStepSpec(
                                "repair_same_component",
                                {},
                                {"": ("repair_anchor",)},
                            ),
                        ),
                    ),
                )
            ),
            ValueError,
        ),
        (
            lambda: _repair_contract(
                terminal_node_ids=("done", "done"),
            ),
            ValueError,
        ),
        (
            lambda: _repair_contract(
                terminal_node_ids=("create_script",),
            ),
            ValueError,
        ),
        (
            lambda: _repair_contract(
                expected_refs=(
                    ExpectedNodeRef("create_script", ""),
                )
            ),
            ValueError,
        ),
    ],
    ids=[
        "empty-workflow-id",
        "descriptor-key-type",
        "descriptor-value-type",
        "max-steps-bool",
        "max-steps-zero",
        "duplicate-initial-param",
        "empty-rules",
        "empty-step-list",
        "non-step-spec",
        "step-target-mismatch",
        "empty-verifier-source",
        "invalid-verifier-outcome",
        "binding-key-type",
        "empty-binding-key",
        "duplicate-terminal",
        "terminal-rule-overlap",
        "empty-expected-ref",
    ],
)
def test_structural_failures_are_rejected_by_snapshot_and_compile(
    contract_factory,
    exc_type,
):
    contract = contract_factory()

    with pytest.raises(exc_type):
        snapshot_workflow_contract(contract)
    with pytest.raises(exc_type):
        compile_workflow_contract(contract)


def test_graph_context_failure_can_snapshot_before_compile_fails():
    contract = _repair_contract(
        rules=(
            WorkflowNodeRule("missing", (ProducerStepSpec("missing"),)),
        ),
        terminal_node_ids=("done",),
    )

    snapshot = snapshot_workflow_contract(contract)

    assert snapshot.workflow_id == "lm4x_repair_contract"
    with pytest.raises(ValueError, match="unknown workflow rule node"):
        compile_workflow_contract(contract)
