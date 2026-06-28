"""LM4W tests for declarative workflow contract compilation.

LM4W compiles a JSON-shaped RookWorkflowContract into existing scaffold objects.
It does not execute, select current nodes, map, revalidate, stream, evaluate, or
apply terminal outcomes.
"""

from __future__ import annotations

import ast
import copy
import pathlib
from collections.abc import Mapping

import pytest

import rook.agent.plan_graph_workflow_contract as contract_module
from rook.agent.plan_graph_current_step_provider import (
    CATALOG_CURRENT_STEP_PROVIDER_ID,
    CatalogCurrentStepProvider,
    NodeStepRule,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_sequence_runner import (
    BindStep,
    ProducerStep,
    VerifierStep,
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
    WorkflowNodeRule,
    WorkflowTemplateRef,
    compile_workflow_contract,
)
from rook.learning.plan_graph_templates import select_template as real_select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}
_TEMPLATE_ID = "gh_csharp_create_verify_repair_verify"
_CREATE_PARAMS = {
    "code": "A = DefinitelyMissingSymbol;",
    "pins_in": [],
    "pins_out": ["A:double"],
    "name": "LM4WWorkflowContract",
    "x": 375,
    "y": 1080,
}
_REPAIR_PARAMS = {"code": "A = 42.0;", "mode": "body", "language": "csharp"}
_BINDINGS = {"guid": ("repair_anchor", "component_guid")}


def _repair_rules(
    *,
    create_rule_node: str = "create_script",
    verify_source: str = "create_script",
    repair_steps: tuple | None = None,
) -> tuple[WorkflowNodeRule, ...]:
    repair_steps = repair_steps or (
        BindStepSpec("repair_same_component", dict(_REPAIR_PARAMS), dict(_BINDINGS)),
        ProducerStepSpec("repair_same_component"),
    )
    return (
        WorkflowNodeRule(create_rule_node, (ProducerStepSpec(create_rule_node),)),
        WorkflowNodeRule(
            "verify_create",
            (
                VerifierStepSpec(
                    "verify_create",
                    verify_source,
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


def _repair_contract(**overrides) -> RookWorkflowContract:
    values = {
        "workflow_id": "lm4w_repair_contract",
        "template": WorkflowTemplateRef(dict(_DESCRIPTOR), _TEMPLATE_ID),
        "initial_params": (
            InitialNodeParams("create_script", dict(_CREATE_PARAMS)),
        ),
        "rules": _repair_rules(),
        "terminal_node_ids": ("done",),
        "expected_refs": (
            ExpectedNodeRef("create_script", "gh_create_csharp_script:v1"),
            ExpectedNodeRef("repair_same_component", "gh_update_script:v1"),
        ),
        "max_steps": 6,
        "metadata": {
            "trace_id": "lm4w",
            "tags": ["contract", "repair"],
            "nested": {"stage": "compile"},
        },
    }
    values.update(overrides)
    return RookWorkflowContract(**values)


def _compile(contract: RookWorkflowContract | None = None):
    return compile_workflow_contract(contract or _repair_contract())


def test_compile_repair_contract_produces_initialized_scaffold_and_snapshots():
    descriptor = dict(_DESCRIPTOR)
    create_params = {
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4WWorkflowContract",
        "x": 375,
        "y": 1080,
    }
    repair_params = {
        "code": "A = 42.0;",
        "mode": "body",
        "language": "csharp",
        "nested": {"tags": ["before"]},
    }
    bindings = {"guid": ["repair_anchor", "component_guid"]}
    metadata = {"trace_id": "lm4w", "tags": ["before"], "nested": {"k": "v"}}
    contract = _repair_contract(
        template=WorkflowTemplateRef(descriptor, _TEMPLATE_ID),
        initial_params=(InitialNodeParams("create_script", create_params),),
        rules=_repair_rules(
            repair_steps=(
                BindStepSpec(
                    "repair_same_component",
                    repair_params,
                    bindings,
                ),
                ProducerStepSpec("repair_same_component"),
            )
        ),
        metadata=metadata,
    )

    scaffold = compile_workflow_contract(contract)

    descriptor["operation"] = "mutated"
    create_params["pins_out"].append("B:double")
    repair_params["nested"]["tags"].append("after")
    metadata["tags"].append("after")
    metadata["nested"]["k"] = "changed"
    bindings["guid"].append("late_path_part")
    bindings["late"] = ["repair_anchor"]

    assert scaffold.workflow_id == "lm4w_repair_contract"
    assert scaffold.max_steps == 6
    assert scaffold.contract_snapshot.workflow_id == scaffold.workflow_id
    assert scaffold.compile_record.workflow_id == scaffold.workflow_id
    assert scaffold.compile_record.compiler_id == WORKFLOW_CONTRACT_COMPILER_ID
    assert scaffold.compile_record.contract_schema == WORKFLOW_CONTRACT_SCHEMA
    assert scaffold.compile_record.contract_fingerprint_algorithm == (
        CONTRACT_FINGERPRINT_ALGORITHM
    )
    assert scaffold.compile_record.contract_fingerprint == (
        scaffold.contract_snapshot.contract_fingerprint
    )
    assert scaffold.compile_record.provider_id == CATALOG_CURRENT_STEP_PROVIDER_ID
    assert scaffold.metadata is scaffold.contract_snapshot.normalized_contract[
        "metadata"
    ]
    assert isinstance(scaffold.provider, CatalogCurrentStepProvider)
    assert scaffold.graph.nodes["create_script"].status == "ready"
    assert scaffold.graph.nodes["done"].is_terminal is True
    assert scaffold.graph.nodes["create_script"].execution_ref == (
        "gh_create_csharp_script:v1"
    )
    assert scaffold.graph.nodes["repair_same_component"].execution_ref == (
        "gh_update_script:v1"
    )

    graph_params = scaffold.graph.nodes["create_script"].metadata[
        EXECUTION_PARAMS_KEY
    ]
    assert graph_params == {
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": (),
        "pins_out": ("A:double",),
        "name": "LM4WWorkflowContract",
        "x": 375,
        "y": 1080,
    }
    assert isinstance(graph_params, dict)

    assert dict(scaffold.metadata) == {
        "trace_id": "lm4w",
        "tags": ("before",),
        "nested": {"k": "v"},
    }
    with pytest.raises(TypeError):
        scaffold.metadata["late"] = True

    assert len(scaffold.rules) == 4
    assert all(isinstance(rule, NodeStepRule) for rule in scaffold.rules)
    assert [type(step).__name__ for step in scaffold.steps] == [
        "ProducerStep",
        "VerifierStep",
        "BindStep",
        "ProducerStep",
        "VerifierStep",
    ]
    bind_step = scaffold.steps[2]
    assert isinstance(bind_step, BindStep)
    assert bind_step.base_params["nested"]["tags"] == ("before",)
    assert bind_step.bindings == {"guid": ("repair_anchor", "component_guid")}
    assert "late" not in bind_step.bindings
    with pytest.raises(TypeError):
        bind_step.base_params["late"] = True


def test_template_descriptor_is_copied_before_selection(monkeypatch):
    caller_descriptor = dict(_DESCRIPTOR)
    captured_descriptors: list[Mapping[str, str]] = []

    def capturing_select_template(descriptor, *args, **kwargs):
        captured_descriptors.append(descriptor)
        return real_select_template(descriptor, *args, **kwargs)

    monkeypatch.setattr(
        contract_module,
        "select_template",
        capturing_select_template,
    )

    compile_workflow_contract(
        _repair_contract(
            template=WorkflowTemplateRef(caller_descriptor, _TEMPLATE_ID),
        )
    )

    assert len(captured_descriptors) == 1
    captured_descriptor = captured_descriptors[0]
    assert captured_descriptor is not caller_descriptor
    assert captured_descriptor == _DESCRIPTOR

    caller_descriptor["operation"] = "mutated"
    caller_descriptor["late"] = "after-compile"

    assert captured_descriptor == _DESCRIPTOR
    assert "late" not in captured_descriptor


@pytest.mark.parametrize(
    "contract_factory,exc_type",
    [
        (
            lambda: _repair_contract(workflow_id=""),
            ValueError,
        ),
        (
            lambda: _repair_contract(max_steps="6"),
            TypeError,
        ),
        (
            lambda: _repair_contract(max_steps=True),
            TypeError,
        ),
        (
            lambda: _repair_contract(max_steps=0),
            ValueError,
        ),
        (
            lambda: _repair_contract(max_steps=-1),
            ValueError,
        ),
    ],
    ids=[
        "empty-workflow-id",
        "max-steps-non-int",
        "max-steps-bool",
        "max-steps-zero",
        "max-steps-negative",
    ],
)
def test_workflow_identity_and_budget_validation(contract_factory, exc_type):
    with pytest.raises(exc_type):
        compile_workflow_contract(contract_factory())


@pytest.mark.parametrize(
    "template",
    [
        WorkflowTemplateRef(dict(_DESCRIPTOR), "wrong_template"),
        WorkflowTemplateRef(
            {"domain": "grasshopper", "operation": "missing", "language": "csharp"},
            _TEMPLATE_ID,
        ),
        WorkflowTemplateRef({"domain": "grasshopper", "operation": 1}, _TEMPLATE_ID),
        WorkflowTemplateRef({1: "grasshopper"}, _TEMPLATE_ID),
        WorkflowTemplateRef(dict(_DESCRIPTOR), ""),
    ],
    ids=[
        "selected-id-mismatch",
        "no-template-match",
        "descriptor-value-not-string",
        "descriptor-key-not-string",
        "empty-expected-id",
    ],
)
def test_template_reference_validation(template):
    exc_type = TypeError if template.descriptor and any(
        not isinstance(k, str) or not isinstance(v, str)
        for k, v in template.descriptor.items()
    ) else ValueError
    with pytest.raises(exc_type):
        compile_workflow_contract(_repair_contract(template=template))


@pytest.mark.parametrize(
    "initial_params,exc_type",
    [
        (
            (
                InitialNodeParams("create_script", {}),
                InitialNodeParams("create_script", {}),
            ),
            ValueError,
        ),
        ((InitialNodeParams("", {}),), ValueError),
        ((InitialNodeParams("missing", {}),), ValueError),
        ((InitialNodeParams("create_script", object()),), TypeError),
        ((InitialNodeParams("create_script", {"nested": {1: "bad"}}),), TypeError),
        ((InitialNodeParams("create_script", {"bad": object()}),), TypeError),
        ((InitialNodeParams("create_script", {"bad": float("inf")}),), TypeError),
    ],
    ids=[
        "duplicate-node",
        "empty-node",
        "unknown-node",
        "non-mapping",
        "non-string-nested-key",
        "non-json-value",
        "non-finite-float",
    ],
)
def test_initial_params_validation(initial_params, exc_type):
    with pytest.raises(exc_type):
        compile_workflow_contract(_repair_contract(initial_params=initial_params))


@pytest.mark.parametrize(
    "rules,exc_type",
    [
        (
            (
                WorkflowNodeRule("create_script", (ProducerStepSpec("create_script"),)),
                WorkflowNodeRule("create_script", (ProducerStepSpec("create_script"),)),
            ),
            ValueError,
        ),
        ((WorkflowNodeRule("", (ProducerStepSpec(""),)),), ValueError),
        ((WorkflowNodeRule("missing", (ProducerStepSpec("missing"),)),), ValueError),
        ((WorkflowNodeRule("create_script", ()),), ValueError),
        ((WorkflowNodeRule("create_script", (object(),)),), TypeError),
        (
            (WorkflowNodeRule("create_script", (ProducerStepSpec("verify_create"),)),),
            ValueError,
        ),
        (
            (
                WorkflowNodeRule(
                    "verify_create",
                    (VerifierStepSpec("repair_same_component", "create_script"),),
                ),
            ),
            ValueError,
        ),
        (
            (
                WorkflowNodeRule(
                    "repair_same_component",
                    (BindStepSpec("create_script", {}, {}),),
                ),
            ),
            ValueError,
        ),
        (
            (
                WorkflowNodeRule(
                    "verify_create",
                    (VerifierStepSpec("verify_create", ""),),
                ),
            ),
            ValueError,
        ),
        (
            (
                WorkflowNodeRule(
                    "verify_create",
                    (VerifierStepSpec("verify_create", "missing"),),
                ),
            ),
            ValueError,
        ),
        (
            (
                WorkflowNodeRule(
                    "verify_create",
                    (VerifierStepSpec("verify_create", "create_script", "usable"),),
                ),
            ),
            ValueError,
        ),
        (
            (
                WorkflowNodeRule(
                    "repair_same_component",
                    (BindStepSpec("repair_same_component", object(), {}),),
                ),
            ),
            TypeError,
        ),
        (
            (
                WorkflowNodeRule(
                    "repair_same_component",
                    (BindStepSpec("repair_same_component", {"bad": float("nan")}, {}),),
                ),
            ),
            TypeError,
        ),
        (
            (
                WorkflowNodeRule(
                    "repair_same_component",
                    (BindStepSpec("repair_same_component", {}, object()),),
                ),
            ),
            TypeError,
        ),
        (
            (
                WorkflowNodeRule(
                    "repair_same_component",
                    (BindStepSpec("repair_same_component", {}, {"guid": ()}),),
                ),
            ),
            ValueError,
        ),
        (
            (
                WorkflowNodeRule(
                    "repair_same_component",
                    (BindStepSpec("repair_same_component", {}, {"guid": (1,)}),),
                ),
            ),
            ValueError,
        ),
        (
            (
                WorkflowNodeRule(
                    "repair_same_component",
                    (BindStepSpec("repair_same_component", {}, {1: ("x",)}),),
                ),
            ),
            TypeError,
        ),
        (
            (
                WorkflowNodeRule(
                    "repair_same_component",
                    (BindStepSpec("repair_same_component", {}, {"": ("x",)}),),
                ),
            ),
            ValueError,
        ),
    ],
    ids=[
        "duplicate-rule-node",
        "empty-rule-node",
        "unknown-rule-node",
        "empty-steps",
        "non-step-spec",
        "producer-target-mismatch",
        "verifier-target-mismatch",
        "bind-target-mismatch",
        "empty-verifier-source",
        "unknown-verifier-source",
        "invalid-verifier-outcome",
        "bind-base-non-mapping",
        "bind-base-non-finite-float",
        "bind-bindings-non-mapping",
        "empty-binding-path",
        "non-string-binding-path-element",
        "non-string-binding-key",
        "empty-binding-key",
    ],
)
def test_rule_and_step_spec_validation(rules, exc_type):
    with pytest.raises(exc_type):
        compile_workflow_contract(_repair_contract(rules=rules))


@pytest.mark.parametrize(
    "terminal_node_ids",
    [
        (),
        ("",),
        ("done", "done"),
        ("missing",),
        ("verify_repair",),
        ("create_script",),
    ],
    ids=[
        "missing-terminal",
        "empty-terminal",
        "duplicate-terminal",
        "unknown-terminal",
        "non-terminal-node",
        "terminal-overlaps-rule",
    ],
)
def test_terminal_node_validation(terminal_node_ids):
    with pytest.raises(ValueError):
        compile_workflow_contract(
            _repair_contract(terminal_node_ids=terminal_node_ids)
        )


@pytest.mark.parametrize(
    "expected_refs",
    [
        (
            ExpectedNodeRef("create_script", "gh_create_csharp_script:v1"),
            ExpectedNodeRef("create_script", "gh_create_csharp_script:v1"),
        ),
        (ExpectedNodeRef("", "gh_create_csharp_script:v1"),),
        (ExpectedNodeRef("create_script", ""),),
        (ExpectedNodeRef("missing", "tool:v1"),),
        (ExpectedNodeRef("create_script", "gh_create_script:v1"),),
    ],
    ids=[
        "duplicate",
        "empty-node",
        "empty-ref",
        "unknown-node",
        "mismatch",
    ],
)
def test_expected_ref_validation(expected_refs):
    with pytest.raises(ValueError):
        compile_workflow_contract(_repair_contract(expected_refs=expected_refs))


@pytest.mark.parametrize(
    "metadata",
    [
        object(),
        [],
        "",
        0,
        {1: "bad"},
        {"bad": object()},
        {"bad": {"nested": object()}},
        {"bad": {"set"}},
        {"bad": lambda: None},
        {"bad": float("-inf")},
    ],
    ids=[
        "non-mapping",
        "falsey-list",
        "falsey-string",
        "falsey-int",
        "non-string-key",
        "object-value",
        "nested-object",
        "set-value",
        "callable-value",
        "non-finite-float",
    ],
)
def test_metadata_validation(metadata):
    with pytest.raises(TypeError):
        compile_workflow_contract(_repair_contract(metadata=metadata))


def test_metadata_none_compiles_to_empty_immutable_mapping():
    scaffold = compile_workflow_contract(_repair_contract(metadata=None))

    assert dict(scaffold.metadata) == {}
    with pytest.raises(TypeError):
        scaffold.metadata["late"] = True


def test_compiled_metadata_supports_deepcopy_as_plain_dict():
    scaffold = _compile()

    metadata_copy = copy.deepcopy(scaffold.metadata)

    assert metadata_copy == {
        "trace_id": "lm4w",
        "tags": ("contract", "repair"),
        "nested": {"stage": "compile"},
    }
    assert isinstance(metadata_copy, dict)


def test_expected_refs_are_assertions_not_overrides():
    scaffold = _compile()

    assert scaffold.graph.nodes["create_script"].execution_ref == (
        "gh_create_csharp_script:v1"
    )
    assert scaffold.graph.nodes["repair_same_component"].execution_ref == (
        "gh_update_script:v1"
    )
    assert scaffold.graph.nodes["verify_create"].execution_ref is None


def test_workflow_contract_module_stays_compile_only_boundary():
    source = pathlib.Path(contract_module.__file__).read_text()
    tree = ast.parse(source)

    allowed_imports = {
        "__future__",
        "collections.abc",
        "copy",
        "dataclasses",
        "hashlib",
        "json",
        "math",
        "types",
        "typing",
        "rook.agent.plan_graph_current_step_provider",
        "rook.agent.plan_graph_live",
        "rook.agent.plan_graph_sequence_runner",
        "rook.learning.plan_graph",
        "rook.learning.plan_graph_templates",
    }
    banned_names = {
        "propose_next_node",
        "revalidate_proposal",
        "map_accepted_proposal_to_step",
        "execute_mapped_step",
        "run_current_mapped_step",
        "run_current_step_stream",
        "run_explicit_sequence",
        "run_live_producer_node",
        "build_live_producer_record",
        "LiveProducerExpectation",
        "LiveProducerRecord",
        "LiveProducerResult",
        "LiveProducerReason",
        "SupportsLiveProducerNode",
        "run_and_record_live_producer_node",
        "_evaluate",
        "apply_verifier_step",
        "apply_memory_bound_params",
        "apply_producer_result",
        "apply_outcome",
        "NodeOutcome",
        "Mismatch",
        "RookAgent",
        "dispatcher",
        "base_agent",
        "server",
        "LiteLLM",
        "model",
        "ok",
        "passed",
        "completed",
        "should_continue",
        "evaluated",
        "mismatches",
        "producer_record",
        "expectation",
        "observed",
    }

    imported_modules: set[str] = set()
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
                imported_names.add(alias.asname or alias.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)

    assert imported_modules <= allowed_imports
    assert imported_names.isdisjoint(banned_names)

    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    referenced_attrs = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert referenced_names.isdisjoint(banned_names)
    assert referenced_attrs.isdisjoint(banned_names)
