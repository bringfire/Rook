# LM4W Workflow Contract Compile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Rook-native declarative workflow contract that validates and compiles the known repair workflow into the existing LM4U/LM4S scaffold without executing it.

**Architecture:** Add one agent-layer module, `plan_graph_workflow_contract.py`, that turns JSON-shaped frozen dataclasses into an initialized `PlanGraph`, staged initial execution params, compiled LM4M `Step` objects, LM4U `NodeStepRule`s, and a `CatalogCurrentStepProvider`. The compiler calls only template selection/initialization plus scaffold constructors; it does not select current nodes, revalidate proposals, map steps, execute, stream, evaluate producers, or apply terminal outcomes.

**Tech Stack:** Python dataclasses, existing PlanGraph learning seams, LM4M step dataclasses, LM4U provider, pytest.

---

## File Structure

- Create `mcp_server/src/rook/agent/plan_graph_workflow_contract.py`
  - Owns LM4W public contract dataclasses and `compile_workflow_contract`.
  - Imports `select_template` / `initialize_graph`, LM4M step types, LM4U provider, and `EXECUTION_PARAMS_KEY`.
  - Contains local JSON-safe snapshot helpers; does not import LM4N/O/P/Q/R/S runtime seams.
- Create `mcp_server/tests/test_plan_graph_workflow_contract.py`
  - Unit tests for successful compile, validation failures, snapshot behavior, and import-boundary guards.
- Create `mcp_server/tests/test_plan_graph_workflow_contract_chain.py`
  - Offline LM4S chain guard proving the compiled scaffold can replace hand-authored runtime objects for the known repair flow.

---

### Task 1: Write Compiler Unit Tests First

**Files:**
- Create: `mcp_server/tests/test_plan_graph_workflow_contract.py`
- Expected failure before Task 2: module import fails because `rook.agent.plan_graph_workflow_contract` does not exist.

- [ ] **Step 1: Create the failing unit test file**

Create `mcp_server/tests/test_plan_graph_workflow_contract.py` with this content:

```python
"""LM4W tests for declarative workflow contract compilation.

LM4W compiles a JSON-shaped RookWorkflowContract into existing scaffold objects.
It does not execute, select current nodes, map, revalidate, stream, evaluate, or
apply terminal outcomes.
"""

from __future__ import annotations

import ast
import pathlib
from collections.abc import Mapping

import pytest

import rook.agent.plan_graph_workflow_contract as contract_module
from rook.agent.plan_graph_current_step_provider import (
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
    metadata = {"trace_id": "lm4w", "tags": ["before"], "nested": {"k": "v"}}
    contract = _repair_contract(
        template=WorkflowTemplateRef(descriptor, _TEMPLATE_ID),
        initial_params=(InitialNodeParams("create_script", create_params),),
        rules=_repair_rules(
            repair_steps=(
                BindStepSpec(
                    "repair_same_component",
                    repair_params,
                    {"guid": ("repair_anchor", "component_guid")},
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

    assert scaffold.workflow_id == "lm4w_repair_contract"
    assert scaffold.max_steps == 6
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
    with pytest.raises(TypeError):
        bind_step.base_params["late"] = True


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
    ],
    ids=[
        "duplicate-node",
        "empty-node",
        "unknown-node",
        "non-mapping",
        "non-string-nested-key",
        "non-json-value",
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
                    (BindStepSpec("repair_same_component", {}, {"guid": ()}),),
                ),
            ),
            ValueError,
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
        "empty-binding-path",
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
        {1: "bad"},
        {"bad": object()},
        {"bad": {"nested": object()}},
        {"bad": {"set"}},
        {"bad": lambda: None},
    ],
    ids=[
        "non-mapping",
        "non-string-key",
        "object-value",
        "nested-object",
        "set-value",
        "callable-value",
    ],
)
def test_metadata_validation(metadata):
    with pytest.raises(TypeError):
        compile_workflow_contract(_repair_contract(metadata=metadata))


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
        "apply_verifier_step",
        "apply_memory_bound_params",
        "apply_producer_result",
        "apply_outcome",
        "NodeOutcome",
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
```

- [ ] **Step 2: Run the unit tests and verify they fail for the expected reason**

Run from repo root:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_workflow_contract.py -q
```

Expected before Task 2: collection fails with `ModuleNotFoundError` or `ImportError` for `rook.agent.plan_graph_workflow_contract`.

- [ ] **Step 3: Commit the failing tests**

```powershell
git add mcp_server\tests\test_plan_graph_workflow_contract.py
git commit -m "test(lm4w): add workflow contract compiler tests"
```

---

### Task 2: Implement Workflow Contract Compiler

**Files:**
- Create: `mcp_server/src/rook/agent/plan_graph_workflow_contract.py`
- Test: `mcp_server/tests/test_plan_graph_workflow_contract.py`

- [ ] **Step 1: Create the production module**

Create `mcp_server/src/rook/agent/plan_graph_workflow_contract.py` with this content:

```python
"""LM4W declarative workflow contract compiler.

Compiles a JSON-shaped, Rook-native workflow contract into existing PlanGraph
scaffold objects. This module prepares artifacts only: it never selects current
nodes, maps proposals, revalidates, executes, streams, evaluates, or applies
terminal outcomes.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, TypeAlias

from rook.agent.plan_graph_current_step_provider import (
    CatalogCurrentStepProvider,
    NodeStepRule,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_sequence_runner import (
    BindStep,
    ProducerStep,
    Step,
    VerifierStep,
)
from rook.learning.plan_graph import OutcomeStatus, PlanGraph, initialize_graph
from rook.learning.plan_graph_templates import select_template


_OUTCOME_STATUSES = frozenset(
    {
        "succeeded",
        "failed",
        "blocked",
        "needs_repair",
        "needs_escalation",
        "skipped",
    }
)
_JSON_SCALARS = (str, int, float, bool, type(None))


class _ImmutableJsonMapping(Mapping[str, Any]):
    def __init__(self, items: Mapping[str, Any]) -> None:
        self._items = MappingProxyType(dict(items))

    def __getitem__(self, key: str) -> Any:
        return self._items[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return dict(self.items()) == dict(other.items())
        return False

    def __repr__(self) -> str:
        return repr(dict(self._items))

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[str, Any]:
        return deepcopy(dict(self._items), memo)


@dataclass(frozen=True)
class WorkflowTemplateRef:
    descriptor: Mapping[str, str]
    expected_template_id: str


@dataclass(frozen=True)
class InitialNodeParams:
    node_id: str
    execution_params: Mapping[str, Any]


@dataclass(frozen=True)
class ProducerStepSpec:
    node_id: str


@dataclass(frozen=True)
class VerifierStepSpec:
    verifier_node_id: str
    source_node_id: str
    expected_outcome: OutcomeStatus | None = None


@dataclass(frozen=True)
class BindStepSpec:
    node_id: str
    base_params: Mapping[str, Any]
    bindings: Mapping[str, tuple[str, ...]]


WorkflowStepSpec: TypeAlias = ProducerStepSpec | VerifierStepSpec | BindStepSpec


@dataclass(frozen=True)
class WorkflowNodeRule:
    node_id: str
    steps_by_seen_count: tuple[WorkflowStepSpec, ...]


@dataclass(frozen=True)
class ExpectedNodeRef:
    node_id: str
    execution_ref: str


@dataclass(frozen=True)
class RookWorkflowContract:
    workflow_id: str
    template: WorkflowTemplateRef
    initial_params: tuple[InitialNodeParams, ...]
    rules: tuple[WorkflowNodeRule, ...]
    terminal_node_ids: tuple[str, ...]
    expected_refs: tuple[ExpectedNodeRef, ...]
    max_steps: int
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class CompiledWorkflowScaffold:
    workflow_id: str
    graph: PlanGraph
    provider: CatalogCurrentStepProvider
    max_steps: int
    metadata: Mapping[str, Any]
    rules: tuple[NodeStepRule, ...]
    steps: tuple[Step, ...]


def compile_workflow_contract(contract: RookWorkflowContract) -> CompiledWorkflowScaffold:
    """Validate and compile a workflow contract into existing scaffold objects."""
    _require_non_empty_str(contract.workflow_id, "workflow_id")
    _validate_max_steps(contract.max_steps)

    descriptor = _descriptor_plain_dict(contract.template.descriptor)
    expected_template_id = _require_non_empty_str(
        contract.template.expected_template_id,
        "template.expected_template_id",
    )
    metadata = _metadata_snapshot(contract.metadata)

    selection = select_template(descriptor)
    if selection.selected_template_id != expected_template_id:
        raise ValueError(
            "selected template id mismatch: "
            f"expected {expected_template_id!r}, got {selection.selected_template_id!r}"
        )
    if selection.graph is None:
        raise ValueError("selected template did not provide a graph")

    graph = initialize_graph(selection.graph)
    _validate_expected_refs(graph, contract.expected_refs)
    _apply_initial_params(graph, contract.initial_params)
    rules, steps = _compile_rules(graph, contract.rules)
    terminal_node_ids = _validate_terminal_node_ids(
        graph,
        contract.terminal_node_ids,
        {rule.node_id for rule in rules},
    )
    provider = CatalogCurrentStepProvider(
        rules,
        terminal_node_ids=frozenset(terminal_node_ids),
    )
    return CompiledWorkflowScaffold(
        workflow_id=contract.workflow_id,
        graph=graph,
        provider=provider,
        max_steps=contract.max_steps,
        metadata=metadata,
        rules=rules,
        steps=steps,
    )


def _validate_max_steps(max_steps: Any) -> None:
    if isinstance(max_steps, bool) or not isinstance(max_steps, int):
        raise TypeError("max_steps must be an int and not a bool")
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")


def _require_non_empty_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _immutable_json_snapshot(value: Any) -> Any:
    if isinstance(value, Mapping):
        items: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON mappings require string keys")
            items[key] = _immutable_json_snapshot(item)
        return _ImmutableJsonMapping(items)
    if isinstance(value, (list, tuple)):
        return tuple(_immutable_json_snapshot(item) for item in value)
    if isinstance(value, (set, frozenset)) or callable(value):
        raise TypeError(f"non-JSON-safe value: {type(value).__name__}")
    if isinstance(value, _JSON_SCALARS):
        return deepcopy(value)
    raise TypeError(f"non-JSON-safe value: {type(value).__name__}")


def _plain_json_tree(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain_json_tree(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain_json_tree(item) for item in value)
    if isinstance(value, list):
        return tuple(_plain_json_tree(item) for item in value)
    return deepcopy(value)


def _descriptor_plain_dict(descriptor: Any) -> dict[str, str]:
    if not isinstance(descriptor, Mapping):
        raise TypeError("template.descriptor must be a mapping")
    snapshot = _immutable_json_snapshot(descriptor)
    plain = _plain_json_tree(snapshot)
    for key, value in plain.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("template.descriptor must be Mapping[str, str]")
    return plain


def _metadata_snapshot(metadata: Any) -> Mapping[str, Any]:
    if metadata is None:
        return _ImmutableJsonMapping({})
    if not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping")
    return _immutable_json_snapshot(metadata)


def _apply_initial_params(
    graph: PlanGraph,
    initial_params: tuple[InitialNodeParams, ...],
) -> None:
    seen: set[str] = set()
    for entry in tuple(initial_params):
        if not isinstance(entry, InitialNodeParams):
            raise TypeError("initial_params entries must be InitialNodeParams")
        node_id = _require_non_empty_str(entry.node_id, "InitialNodeParams.node_id")
        if node_id in seen:
            raise ValueError(f"duplicate InitialNodeParams.node_id: {node_id!r}")
        seen.add(node_id)
        if node_id not in graph.nodes:
            raise ValueError(f"unknown initial params node: {node_id!r}")
        if not isinstance(entry.execution_params, Mapping):
            raise TypeError("InitialNodeParams.execution_params must be a mapping")
        snapshot = _immutable_json_snapshot(entry.execution_params)
        graph.nodes[node_id].metadata[EXECUTION_PARAMS_KEY] = _plain_json_tree(snapshot)


def _compile_rules(
    graph: PlanGraph,
    rules: tuple[WorkflowNodeRule, ...],
) -> tuple[tuple[NodeStepRule, ...], tuple[Step, ...]]:
    seen: set[str] = set()
    compiled_rules: list[NodeStepRule] = []
    compiled_steps: list[Step] = []
    for rule in tuple(rules):
        if not isinstance(rule, WorkflowNodeRule):
            raise TypeError("rules entries must be WorkflowNodeRule")
        node_id = _require_non_empty_str(rule.node_id, "WorkflowNodeRule.node_id")
        if node_id in seen:
            raise ValueError(f"duplicate WorkflowNodeRule.node_id: {node_id!r}")
        seen.add(node_id)
        if node_id not in graph.nodes:
            raise ValueError(f"unknown workflow rule node: {node_id!r}")
        steps_by_seen_count = tuple(rule.steps_by_seen_count)
        if not steps_by_seen_count:
            raise ValueError(
                f"WorkflowNodeRule.steps_by_seen_count must be non-empty for {node_id!r}"
            )
        steps = tuple(_compile_step_spec(graph, node_id, spec) for spec in steps_by_seen_count)
        compiled_rules.append(NodeStepRule(node_id, steps))
        compiled_steps.extend(steps)
    return tuple(compiled_rules), tuple(compiled_steps)


def _compile_step_spec(
    graph: PlanGraph,
    rule_node_id: str,
    spec: WorkflowStepSpec,
) -> Step:
    if isinstance(spec, ProducerStepSpec):
        node_id = _require_non_empty_str(spec.node_id, "ProducerStepSpec.node_id")
        if node_id != rule_node_id:
            raise ValueError(
                f"ProducerStepSpec for {rule_node_id!r} targets {node_id!r}"
            )
        return ProducerStep(node_id)

    if isinstance(spec, VerifierStepSpec):
        verifier_node_id = _require_non_empty_str(
            spec.verifier_node_id,
            "VerifierStepSpec.verifier_node_id",
        )
        if verifier_node_id != rule_node_id:
            raise ValueError(
                f"VerifierStepSpec for {rule_node_id!r} targets {verifier_node_id!r}"
            )
        source_node_id = _require_non_empty_str(
            spec.source_node_id,
            "VerifierStepSpec.source_node_id",
        )
        if source_node_id not in graph.nodes:
            raise ValueError(f"unknown verifier source node: {source_node_id!r}")
        if (
            spec.expected_outcome is not None
            and spec.expected_outcome not in _OUTCOME_STATUSES
        ):
            raise ValueError(
                f"invalid VerifierStepSpec.expected_outcome: {spec.expected_outcome!r}"
            )
        return VerifierStep(
            verifier_node_id,
            source_node_id,
            expected_outcome=spec.expected_outcome,
        )

    if isinstance(spec, BindStepSpec):
        node_id = _require_non_empty_str(spec.node_id, "BindStepSpec.node_id")
        if node_id != rule_node_id:
            raise ValueError(f"BindStepSpec for {rule_node_id!r} targets {node_id!r}")
        if not isinstance(spec.base_params, Mapping):
            raise TypeError("BindStepSpec.base_params must be a mapping")
        base_params = _immutable_json_snapshot(spec.base_params)
        bindings = _compile_bindings(spec.bindings)
        return BindStep(node_id, base_params, bindings)

    raise TypeError("WorkflowNodeRule.steps_by_seen_count contains a non-step spec")


def _compile_bindings(bindings: Any) -> Mapping[str, tuple[str, ...]]:
    if not isinstance(bindings, Mapping):
        raise TypeError("BindStepSpec.bindings must be a mapping")
    compiled: dict[str, tuple[str, ...]] = {}
    for param_key, path in bindings.items():
        if not isinstance(param_key, str) or not param_key:
            raise ValueError("binding param keys must be non-empty strings")
        if not isinstance(path, (list, tuple)) or not path:
            raise ValueError(f"binding path for {param_key!r} must be non-empty")
        path_tuple = tuple(path)
        if any(not isinstance(part, str) or not part for part in path_tuple):
            raise ValueError(f"binding path for {param_key!r} must contain strings")
        compiled[param_key] = path_tuple
    return _ImmutableJsonMapping(compiled)


def _validate_terminal_node_ids(
    graph: PlanGraph,
    terminal_node_ids: tuple[str, ...],
    rule_node_ids: set[str],
) -> tuple[str, ...]:
    terminal_ids = tuple(terminal_node_ids)
    if not terminal_ids:
        raise ValueError("terminal_node_ids must contain at least one node")
    seen: set[str] = set()
    for node_id in terminal_ids:
        node_id = _require_non_empty_str(node_id, "terminal_node_ids")
        if node_id in seen:
            raise ValueError(f"duplicate terminal node id: {node_id!r}")
        seen.add(node_id)
        if node_id not in graph.nodes:
            raise ValueError(f"unknown terminal node id: {node_id!r}")
        if node_id in rule_node_ids:
            raise ValueError(
                f"terminal node id must not also have a rule: {node_id!r}"
            )
        if not graph.nodes[node_id].is_terminal:
            raise ValueError(f"declared terminal node is not terminal: {node_id!r}")
    return terminal_ids


def _validate_expected_refs(
    graph: PlanGraph,
    expected_refs: tuple[ExpectedNodeRef, ...],
) -> None:
    seen: set[str] = set()
    for expected in tuple(expected_refs):
        if not isinstance(expected, ExpectedNodeRef):
            raise TypeError("expected_refs entries must be ExpectedNodeRef")
        node_id = _require_non_empty_str(expected.node_id, "ExpectedNodeRef.node_id")
        execution_ref = _require_non_empty_str(
            expected.execution_ref,
            "ExpectedNodeRef.execution_ref",
        )
        if node_id in seen:
            raise ValueError(f"duplicate ExpectedNodeRef.node_id: {node_id!r}")
        seen.add(node_id)
        if node_id not in graph.nodes:
            raise ValueError(f"unknown expected-ref node: {node_id!r}")
        actual = graph.nodes[node_id].execution_ref
        if actual != execution_ref:
            raise ValueError(
                f"execution_ref mismatch for {node_id!r}: "
                f"expected {execution_ref!r}, got {actual!r}"
            )
```

- [ ] **Step 2: Run the unit tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_workflow_contract.py -q
```

Expected after implementation: all tests in `test_plan_graph_workflow_contract.py` pass.

- [ ] **Step 3: Run a py_compile smoke for the new module**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m py_compile mcp_server\src\rook\agent\plan_graph_workflow_contract.py
```

Expected: command exits 0 with no output.

- [ ] **Step 4: Commit the module**

```powershell
git add mcp_server\src\rook\agent\plan_graph_workflow_contract.py mcp_server\tests\test_plan_graph_workflow_contract.py
git commit -m "feat(lm4w): compile workflow contracts"
```

---

### Task 3: Add Offline Chain Guard

**Files:**
- Create: `mcp_server/tests/test_plan_graph_workflow_contract_chain.py`
- Uses: `mcp_server/src/rook/agent/plan_graph_workflow_contract.py`

- [ ] **Step 1: Create the chain guard test file**

Create `mcp_server/tests/test_plan_graph_workflow_contract_chain.py` with this content:

```python
"""LM4W offline chain guard for compiled workflow contracts."""

from __future__ import annotations

import pytest

from rook.agent.plan_graph_current_step_provider import CatalogCurrentStepProvider
from rook.agent.plan_graph_current_step_stream import run_current_step_stream
from rook.agent.plan_graph_live import LiveProducerResult
from rook.agent.plan_graph_workflow_contract import (
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
from rook.learning.plan_graph_runner import apply_producer_result


_GUID = "lm4w-workflow-contract-guid"
_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}


def _wrapped_failure_create_raw() -> dict:
    return {
        "success": False,
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "created_with_errors",
                "mutation": {"status": "created", "component_guid": _GUID},
                "verification": {"status": "failed", "target_error_count": 1},
                "repair_anchor": {"component_guid": _GUID, "language": "csharp"},
            }
        },
    }


def _unwrapped_success_repair_raw() -> dict:
    return {
        "script_receipt": {
            "version": 1,
            "operation": "update",
            "language": "csharp",
            "artifact_status": "usable",
            "mutation": {"status": "written", "component_guid": _GUID},
            "verification": {"status": "passed", "target_error_count": 0},
            "repair_anchor": {"component_guid": _GUID, "language": "csharp"},
        }
    }


class _OfflineProducerRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run_live_producer_node(self, graph, node_id):
        self.calls.append(node_id)
        raw = {
            "create_script": _wrapped_failure_create_raw(),
            "repair_same_component": _unwrapped_success_repair_raw(),
        }[node_id]
        tool_name = {
            "create_script": "gh_create_csharp_script",
            "repair_same_component": "gh_update_script",
        }[node_id]
        inner = apply_producer_result(graph, node_id, raw)
        return LiveProducerResult(
            graph=inner.graph,
            applied=inner.applied,
            node_id=node_id,
            tool_name=tool_name,
            outcome_status=inner.outcome_status,
            reason=inner.reason,
        )


def _repair_contract() -> RookWorkflowContract:
    return RookWorkflowContract(
        workflow_id="lm4w_repair_contract",
        template=WorkflowTemplateRef(
            descriptor=dict(_DESCRIPTOR),
            expected_template_id="gh_csharp_create_verify_repair_verify",
        ),
        initial_params=(
            InitialNodeParams(
                "create_script",
                {
                    "code": "A = DefinitelyMissingSymbol;",
                    "pins_in": [],
                    "pins_out": ["A:double"],
                    "name": "LM4WWorkflowContract",
                    "x": 375,
                    "y": 1080,
                },
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
                        {
                            "code": "A = 42.0;",
                            "mode": "body",
                            "language": "csharp",
                        },
                        {"guid": ("repair_anchor", "component_guid")},
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
        terminal_node_ids=("done",),
        expected_refs=(
            ExpectedNodeRef("create_script", "gh_create_csharp_script:v1"),
            ExpectedNodeRef("repair_same_component", "gh_update_script:v1"),
        ),
        max_steps=6,
        metadata={"trace_id": "lm4w-chain", "workflow": "repair"},
    )


@pytest.mark.asyncio
async def test_compiled_workflow_contract_runs_offline_repair_stream_to_done_halt():
    scaffold = compile_workflow_contract(_repair_contract())
    runner = _OfflineProducerRunner()

    result = await run_current_step_stream(
        scaffold.graph,
        scaffold.provider,
        max_steps=scaffold.max_steps,
        runner=runner,
    )

    assert isinstance(scaffold.provider, CatalogCurrentStepProvider)
    assert scaffold.max_steps == 6
    assert result.stop_reason == "provider_halt"
    assert result.steps_attempted == 5
    assert runner.calls == ["create_script", "repair_same_component"]
    assert len(result.records) == 5
    assert len(result.supply_records) == 6

    assert [record.accepted_node_id for record in result.records] == [
        "create_script",
        "verify_create",
        "repair_same_component",
        "repair_same_component",
        "verify_repair",
    ]
    assert [record.execution_kind for record in result.records] == [
        "producer",
        "verifier",
        "bind",
        "producer",
        "verifier",
    ]

    for index, record in enumerate(result.records):
        supply = result.supply_records[index]
        assert supply.decision == "SUPPLY"
        assert supply.envelope is not None
        assert supply.envelope.mapping is record.mapping
        assert record.ran is True
        assert record.execution_failure is None
        assert record.mapping_mapped is True
        assert record.revalidation.decision == "ACCEPT"

    bind_record = result.records[2]
    assert bind_record.bind_node_id == "repair_same_component"
    assert bind_record.bind_applied is True
    assert bind_record.execution.bind_result is not None
    assert bind_record.execution.bind_result.binding is not None
    assert bind_record.execution.bind_result.binding.params["guid"] == _GUID

    assert result.records[0].producer_tool_name == "gh_create_csharp_script"
    assert result.records[0].producer_outcome_status == "succeeded"
    assert result.records[1].verifier_outcome_status == "needs_repair"
    assert result.records[3].producer_tool_name == "gh_update_script"
    assert result.records[3].producer_outcome_status == "succeeded"
    assert result.records[4].verifier_outcome_status == "succeeded"

    final_supply = result.supply_records[5]
    assert final_supply.decision == "HALT"
    assert final_supply.envelope is None
    assert final_supply.reason == "terminal_node_selected:done"
    assert final_supply.metadata is not None
    assert final_supply.metadata["selected_node_id"] == "done"

    assert result.final_graph.nodes["done"].status == "ready"
    assert result.final_graph.nodes["done"].is_terminal is True
```

- [ ] **Step 2: Run the chain guard**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_workflow_contract_chain.py -q
```

Expected: the chain guard passes.

- [ ] **Step 3: Run both LM4W test files**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_workflow_contract.py mcp_server\tests\test_plan_graph_workflow_contract_chain.py -q
```

Expected: all LM4W tests pass.

- [ ] **Step 4: Commit the chain guard**

```powershell
git add mcp_server\tests\test_plan_graph_workflow_contract_chain.py
git commit -m "test(lm4w): prove compiled workflow offline chain"
```

---

### Task 4: Final Verification And Scope Guards

**Files:**
- Review: `docs/superpowers/specs/2026-06-26-lm4w-workflow-contract-design.md`
- Review: `mcp_server/src/rook/agent/plan_graph_workflow_contract.py`
- Review: `mcp_server/tests/test_plan_graph_workflow_contract.py`
- Review: `mcp_server/tests/test_plan_graph_workflow_contract_chain.py`

- [ ] **Step 1: Run targeted LM4W tests**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_workflow_contract.py mcp_server\tests\test_plan_graph_workflow_contract_chain.py -q
```

Expected: all LM4W tests pass.

- [ ] **Step 2: Run focused LM4N-W gate**

PowerShell does not expand `test_plan_graph*.py` safely for this repo, so enumerate the active LM4N-W focused files:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_selector.py mcp_server\tests\test_plan_graph_revalidation.py mcp_server\tests\test_plan_graph_step_mapping.py mcp_server\tests\test_plan_graph_step_executor.py mcp_server\tests\test_plan_graph_current_step_runner.py mcp_server\tests\test_plan_graph_current_step_stream.py mcp_server\tests\test_plan_graph_current_step_provider.py mcp_server\tests\test_plan_graph_workflow_contract.py mcp_server\tests\test_plan_graph_workflow_contract_chain.py -q
```

Expected: focused gate passes. The LM4U/LM4V baseline is `106 passed`; the new count must equal that baseline plus the collected LM4W unit and chain cases.

- [ ] **Step 3: Run diff checks**

```powershell
git diff --check main..HEAD
git diff --numstat main..HEAD -- mcp_server/src
git diff --name-only main..HEAD
```

Expected:

- `git diff --check` exits 0.
- `mcp_server/src` diff contains exactly `mcp_server/src/rook/agent/plan_graph_workflow_contract.py`.
- whole-branch diff contains the spec, plan, one production module, and two test files.

- [ ] **Step 4: Confirm banned runtime seams are absent from the new production module**

```powershell
rg -n "propose_next_node|revalidate_proposal|map_accepted_proposal_to_step|execute_mapped_step|run_current_mapped_step|run_current_step_stream|run_explicit_sequence|build_live_producer_record|LiveProducerExpectation|apply_outcome|NodeOutcome|RookAgent|dispatcher|base_agent|server|litellm|model" mcp_server\src\rook\agent\plan_graph_workflow_contract.py
```

Expected: no matches.

- [ ] **Step 5: Confirm `base_agent.py` is byte-stable**

```powershell
git diff -- mcp_server\src\rook\agent\base_agent.py
```

Expected: no output.

- [ ] **Step 6: Confirm no live/runtime knowledge drift**

```powershell
git diff -- knowledge\gh\operations_knowledge.json
```

Expected: no output.

- [ ] **Step 7: Final status**

```powershell
git status --short --branch
```

Expected: branch is `codex/lm4w-workflow-contract`; no uncommitted changes except intentional plan/spec edits if they are not committed yet.

---

## Self-Review Notes

Spec coverage:

- Workflow-level contract: Task 2 defines `RookWorkflowContract` and `CompiledWorkflowScaffold`.
- Dataclasses first, no parser: Task 2 adds only Python dataclasses and compile function.
- Descriptor + expected template id: Task 2 validates `TemplateSelection.selected_template_id`.
- Initial params records: Task 2 stages copied params via `EXECUTION_PARAMS_KEY`; Task 1 tests validation and snapshot independence.
- Contract-level step specs: Task 2 compiles specs into LM4M steps; Task 1 tests target mismatches and invalid source ids.
- Terminal ids: Task 2 validates explicit terminal ids; Task 1 tests missing/duplicate/unknown/non-terminal/overlap.
- Expected refs: Task 2 asserts, never sets; Task 1 tests duplicate/empty/unknown/mismatch and no override.
- JSON-safe snapshots: Task 2 implements immutable mapping / tuple snapshot policy; Task 1 tests caller mutation and rejects non-JSON values.
- No execution/runtime authority: Task 1 AST guard and Task 4 rg scan ban LM4N/O/P/Q/R/S and evaluation seams.
- Offline chain guard: Task 3 compiles and runs through LM4S with a fake producer that advances via `apply_producer_result`.

Red-flag scan for the completed plan: run the standard writing-plans red-flag search
against this file and expect no matches.

Type consistency:

- `TemplateSelection.selected_template_id` is the exact field exposed by `select_template`.
- `VerifierStepSpec.expected_outcome` compiles into `VerifierStep.expected_outcome`.
- `BindStepSpec.bindings` compiles to tuple paths for `BindStep`.
- `CompiledWorkflowScaffold.provider` is directly consumable by `run_current_step_stream`.
