# LM4X Workflow Contract Fingerprint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add content-addressed workflow contract snapshots and deterministic compile records to the LM4W workflow contract compiler.

**Architecture:** Extend the existing workflow contract compiler with one graph-free normalization path that produces an immutable `WorkflowContractSnapshot`, then compile from the same normalized intermediate and attach a compact `WorkflowCompileRecord` to every successful `CompiledWorkflowScaffold`. Expose the LM4U provider id as a public constant so the receipt does not duplicate a private magic string.

**Tech Stack:** Python 3, dataclasses, pytest, `hashlib`, `json`, existing PlanGraph/LM4U/LM4W agent modules.

---

## File Structure

- Modify: `mcp_server/src/rook/agent/plan_graph_current_step_provider.py`
  - Expose `CATALOG_CURRENT_STEP_PROVIDER_ID`.
  - Keep `_PROVIDER_ID` as an alias to preserve existing provider behavior.
- Modify: `mcp_server/src/rook/agent/plan_graph_workflow_contract.py`
  - Add public schema/compiler/fingerprint constants.
  - Add `WorkflowContractSnapshot`, `WorkflowCompileRecord`, and `snapshot_workflow_contract`.
  - Refactor graph-free validation into one private `_normalize_workflow_contract` path.
  - Extend `CompiledWorkflowScaffold` with `contract_snapshot` and `compile_record`.
  - Build compile records after provider construction succeeds.
- Create: `mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py`
  - Own LM4X snapshot/fingerprint/receipt tests.
- Modify: `mcp_server/tests/test_plan_graph_workflow_contract.py`
  - Add small scaffold invariant assertions to the existing success test.
  - Update the boundary guard allowed imports for `hashlib`, `json`, and provider id.
  - Keep broad LM4W test rewrites out of scope.

No live test, no new chain guard, no JSON/YAML loader, no stream metadata integration.

---

### Task 1: Add Failing LM4X Fingerprint And Receipt Tests

**Files:**
- Create: `mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py`

- [ ] **Step 1: Create the LM4X test file**

Add this complete file:

```python
"""LM4X workflow contract snapshot and compile-record tests."""

from __future__ import annotations

from dataclasses import replace

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


def _repair_rules(*, reversed_rules: bool = False, reversed_repair_steps: bool = False):
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
```

- [ ] **Step 2: Run the new tests and confirm they fail for missing LM4X API**

Run:

```powershell
pytest mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py -q
```

Expected: collection fails with an import error for at least one of:

```text
CATALOG_CURRENT_STEP_PROVIDER_ID
CONTRACT_FINGERPRINT_ALGORITHM
WORKFLOW_CONTRACT_COMPILER_ID
WORKFLOW_CONTRACT_SCHEMA
WorkflowContractSnapshot
WorkflowCompileRecord
snapshot_workflow_contract
```

- [ ] **Step 3: Commit failing tests**

```powershell
git add mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py
git commit -m "test(lm4x): add workflow contract fingerprint tests"
```

---

### Task 2: Expose Provider Id Constant

**Files:**
- Modify: `mcp_server/src/rook/agent/plan_graph_current_step_provider.py`

- [ ] **Step 1: Replace the private provider id definition**

Change:

```python
ProviderId = Literal["catalog_current_step_provider:v1"]
StepKind = Literal["producer", "verifier", "bind"]

_PROVIDER_ID: ProviderId = "catalog_current_step_provider:v1"
```

to:

```python
ProviderId = Literal["catalog_current_step_provider:v1"]
StepKind = Literal["producer", "verifier", "bind"]

CATALOG_CURRENT_STEP_PROVIDER_ID: ProviderId = "catalog_current_step_provider:v1"
_PROVIDER_ID: ProviderId = CATALOG_CURRENT_STEP_PROVIDER_ID
```

- [ ] **Step 2: Run provider tests**

Run:

```powershell
pytest mcp_server/tests/test_plan_graph_current_step_provider.py -q
```

Expected: all provider tests pass.

- [ ] **Step 3: Commit provider constant exposure**

```powershell
git add mcp_server/src/rook/agent/plan_graph_current_step_provider.py
git commit -m "feat(lm4x): expose catalog provider id"
```

---

### Task 3: Implement Snapshot, Fingerprint, And Compile Record

**Files:**
- Modify: `mcp_server/src/rook/agent/plan_graph_workflow_contract.py`

- [ ] **Step 1: Add imports and provider id**

Update imports:

```python
import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, TypeAlias, get_args
```

Update the provider import:

```python
from rook.agent.plan_graph_current_step_provider import (
    CATALOG_CURRENT_STEP_PROVIDER_ID,
    CatalogCurrentStepProvider,
    NodeStepRule,
)
```

- [ ] **Step 2: Add constants and private aliases before `_OUTCOME_STATUSES`**

```python
WORKFLOW_CONTRACT_SCHEMA = "rook.workflow_contract:v1"
WORKFLOW_CONTRACT_COMPILER_ID = "rook_workflow_contract_compiler:v1"
CONTRACT_FINGERPRINT_ALGORITHM = "sha256"

StepKindTag = Literal["producer", "verifier", "bind"]

_OUTCOME_STATUSES = frozenset(get_args(OutcomeStatus))
```

If `_OUTCOME_STATUSES` already exists, keep exactly one definition after these constants.

- [ ] **Step 3: Add public receipt dataclasses before `CompiledWorkflowScaffold`**

```python
@dataclass(frozen=True)
class WorkflowContractSnapshot:
    workflow_id: str
    normalized_contract: Mapping[str, Any]
    contract_fingerprint: str


@dataclass(frozen=True)
class WorkflowCompileRecord:
    workflow_id: str
    compiler_id: str
    contract_schema: str
    contract_fingerprint_algorithm: str
    contract_fingerprint: str
    provider_id: str
    expected_template_id: str
    selected_template_id: str
    graph_node_ids: tuple[str, ...]
    initial_param_node_ids: tuple[str, ...]
    rule_node_ids: tuple[str, ...]
    terminal_node_ids: tuple[str, ...]
    expected_refs: tuple[tuple[str, str], ...]
    step_kinds_by_rule: tuple[tuple[str, tuple[str, ...]], ...]
    max_steps: int


@dataclass(frozen=True)
class _NormalizedWorkflowTemplateRef:
    descriptor: Mapping[str, str]
    expected_template_id: str


@dataclass(frozen=True)
class _NormalizedInitialNodeParams:
    node_id: str
    execution_params: Mapping[str, Any]


@dataclass(frozen=True)
class _NormalizedProducerStepSpec:
    kind: StepKindTag
    node_id: str


@dataclass(frozen=True)
class _NormalizedVerifierStepSpec:
    kind: StepKindTag
    verifier_node_id: str
    source_node_id: str
    expected_outcome: OutcomeStatus | None


@dataclass(frozen=True)
class _NormalizedBindStepSpec:
    kind: StepKindTag
    node_id: str
    base_params: Mapping[str, Any]
    bindings: Mapping[str, tuple[str, ...]]


NormalizedStepSpec: TypeAlias = (
    "_NormalizedProducerStepSpec | _NormalizedVerifierStepSpec | _NormalizedBindStepSpec"
)


@dataclass(frozen=True)
class _NormalizedWorkflowNodeRule:
    node_id: str
    steps_by_seen_count: tuple[NormalizedStepSpec, ...]


@dataclass(frozen=True)
class _NormalizedExpectedNodeRef:
    node_id: str
    execution_ref: str


@dataclass(frozen=True)
class _NormalizedWorkflowContract:
    workflow_id: str
    template: _NormalizedWorkflowTemplateRef
    initial_params: tuple[_NormalizedInitialNodeParams, ...]
    rules: tuple[_NormalizedWorkflowNodeRule, ...]
    terminal_node_ids: tuple[str, ...]
    expected_refs: tuple[_NormalizedExpectedNodeRef, ...]
    max_steps: int
    metadata: Mapping[str, Any]
    normalized_contract: Mapping[str, Any]
```

- [ ] **Step 4: Append snapshot and record fields to `CompiledWorkflowScaffold`**

Change `CompiledWorkflowScaffold` to:

```python
@dataclass(frozen=True)
class CompiledWorkflowScaffold:
    workflow_id: str
    graph: PlanGraph
    provider: CatalogCurrentStepProvider
    max_steps: int
    metadata: Mapping[str, Any]
    rules: tuple[NodeStepRule, ...]
    steps: tuple[Step, ...]
    contract_snapshot: WorkflowContractSnapshot
    compile_record: WorkflowCompileRecord
```

- [ ] **Step 5: Add snapshot and fingerprint helpers before `compile_workflow_contract`**

```python
def snapshot_workflow_contract(
    contract: RookWorkflowContract,
) -> WorkflowContractSnapshot:
    """Snapshot and fingerprint a graph-free workflow contract artifact."""
    normalized = _normalize_workflow_contract(contract)
    return _snapshot_from_normalized(normalized)


def _snapshot_from_normalized(
    normalized: _NormalizedWorkflowContract,
) -> WorkflowContractSnapshot:
    fingerprint = _fingerprint_normalized_contract(normalized.normalized_contract)
    return WorkflowContractSnapshot(
        workflow_id=normalized.workflow_id,
        normalized_contract=normalized.normalized_contract,
        contract_fingerprint=fingerprint,
    )


def _fingerprint_normalized_contract(normalized_contract: Mapping[str, Any]) -> str:
    canonical_json = json.dumps(
        _plain_json_tree(normalized_contract),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
```

- [ ] **Step 6: Replace `compile_workflow_contract` with normalized compile flow**

```python
def compile_workflow_contract(contract: RookWorkflowContract) -> CompiledWorkflowScaffold:
    """Compile a declarative contract into provider-ready workflow scaffold data."""
    normalized = _normalize_workflow_contract(contract)
    snapshot = _snapshot_from_normalized(normalized)

    descriptor = dict(normalized.template.descriptor)
    selection = select_template(descriptor)
    if selection.selected_template_id != normalized.template.expected_template_id:
        raise ValueError(
            "selected template id does not match expected template id: "
            f"{selection.selected_template_id!r} != "
            f"{normalized.template.expected_template_id!r}"
        )
    if selection.graph is None:
        raise ValueError("selected template did not provide a graph")

    graph = initialize_graph(selection.graph)
    _validate_expected_refs(graph, normalized.expected_refs)
    _stage_initial_params(graph, normalized.initial_params)
    rules, steps = _compile_rules(graph, normalized.rules)
    terminal_node_ids = _validate_terminal_node_ids(
        graph,
        normalized.terminal_node_ids,
        {rule.node_id for rule in rules},
    )
    provider = CatalogCurrentStepProvider(
        rules,
        terminal_node_ids=frozenset(terminal_node_ids),
    )
    compile_record = _build_compile_record(
        normalized,
        snapshot,
        selected_template_id=selection.selected_template_id,
        graph=graph,
    )

    return CompiledWorkflowScaffold(
        workflow_id=normalized.workflow_id,
        graph=graph,
        provider=provider,
        max_steps=normalized.max_steps,
        metadata=normalized.metadata,
        rules=rules,
        steps=steps,
        contract_snapshot=snapshot,
        compile_record=compile_record,
    )
```

- [ ] **Step 7: Add graph-free normalization helpers after `_require_non_empty_str`**

```python
def _normalize_workflow_contract(
    contract: RookWorkflowContract,
) -> _NormalizedWorkflowContract:
    workflow_id = _require_non_empty_str(contract.workflow_id, "workflow_id")
    max_steps = _validate_max_steps(contract.max_steps)
    template = _normalize_template(contract.template)
    metadata = _snapshot_metadata(contract.metadata)
    initial_params = _normalize_initial_params(contract.initial_params)
    rules = _normalize_rules(contract.rules)
    terminal_node_ids = _normalize_terminal_node_ids(contract.terminal_node_ids)
    expected_refs = _normalize_expected_refs(contract.expected_refs)
    _reject_terminal_rule_overlap(terminal_node_ids, rules)

    normalized_contract = _ImmutableJsonMapping(
        {
            "schema": WORKFLOW_CONTRACT_SCHEMA,
            "workflow_id": workflow_id,
            "template": _ImmutableJsonMapping(
                {
                    "descriptor": template.descriptor,
                    "expected_template_id": template.expected_template_id,
                }
            ),
            "initial_params": tuple(
                _normalized_initial_param_payload(entry)
                for entry in initial_params
            ),
            "rules": tuple(_normalized_rule_payload(rule) for rule in rules),
            "terminal_node_ids": terminal_node_ids,
            "expected_refs": tuple(
                _ImmutableJsonMapping(
                    {
                        "node_id": ref.node_id,
                        "execution_ref": ref.execution_ref,
                    }
                )
                for ref in expected_refs
            ),
            "max_steps": max_steps,
            "metadata": metadata,
        }
    )

    return _NormalizedWorkflowContract(
        workflow_id=workflow_id,
        template=template,
        initial_params=initial_params,
        rules=rules,
        terminal_node_ids=terminal_node_ids,
        expected_refs=expected_refs,
        max_steps=max_steps,
        metadata=metadata,
        normalized_contract=normalized_contract,
    )


def _normalize_template(template: Any) -> _NormalizedWorkflowTemplateRef:
    if not isinstance(template, WorkflowTemplateRef):
        raise TypeError("contract.template must be WorkflowTemplateRef")
    descriptor = _snapshot_descriptor(template.descriptor)
    expected_template_id = _require_non_empty_str(
        template.expected_template_id,
        "WorkflowTemplateRef.expected_template_id",
    )
    return _NormalizedWorkflowTemplateRef(
        descriptor=_ImmutableJsonMapping(descriptor),
        expected_template_id=expected_template_id,
    )


def _normalize_initial_params(
    initial_params: tuple[InitialNodeParams, ...],
) -> tuple[_NormalizedInitialNodeParams, ...]:
    seen: set[str] = set()
    normalized: list[_NormalizedInitialNodeParams] = []
    for entry in tuple(initial_params):
        if not isinstance(entry, InitialNodeParams):
            raise TypeError("initial_params entries must be InitialNodeParams")
        node_id = _require_non_empty_str(entry.node_id, "InitialNodeParams.node_id")
        if node_id in seen:
            raise ValueError(f"duplicate InitialNodeParams.node_id: {node_id!r}")
        seen.add(node_id)
        if not isinstance(entry.execution_params, Mapping):
            raise TypeError("InitialNodeParams.execution_params must be a mapping")
        normalized.append(
            _NormalizedInitialNodeParams(
                node_id=node_id,
                execution_params=_immutable_json_snapshot(entry.execution_params),
            )
        )
    return tuple(normalized)


def _normalize_rules(
    rules: tuple[WorkflowNodeRule, ...],
) -> tuple[_NormalizedWorkflowNodeRule, ...]:
    rule_tuple = tuple(rules)
    if not rule_tuple:
        raise ValueError("rules must contain at least one WorkflowNodeRule")
    seen: set[str] = set()
    normalized: list[_NormalizedWorkflowNodeRule] = []
    for rule in rule_tuple:
        if not isinstance(rule, WorkflowNodeRule):
            raise TypeError("rules entries must be WorkflowNodeRule")
        node_id = _require_non_empty_str(rule.node_id, "WorkflowNodeRule.node_id")
        if node_id in seen:
            raise ValueError(f"duplicate WorkflowNodeRule.node_id: {node_id!r}")
        seen.add(node_id)
        steps = tuple(rule.steps_by_seen_count)
        if not steps:
            raise ValueError(
                "WorkflowNodeRule.steps_by_seen_count must be non-empty for "
                f"{node_id!r}"
            )
        normalized.append(
            _NormalizedWorkflowNodeRule(
                node_id=node_id,
                steps_by_seen_count=tuple(
                    _normalize_step_spec(node_id, spec) for spec in steps
                ),
            )
        )
    return tuple(normalized)


def _normalize_step_spec(rule_node_id: str, spec: WorkflowStepSpec) -> NormalizedStepSpec:
    if isinstance(spec, ProducerStepSpec):
        node_id = _require_non_empty_str(spec.node_id, "ProducerStepSpec.node_id")
        if node_id != rule_node_id:
            raise ValueError(
                f"ProducerStepSpec for {rule_node_id!r} targets {node_id!r}"
            )
        return _NormalizedProducerStepSpec(kind="producer", node_id=node_id)

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
        if (
            spec.expected_outcome is not None
            and spec.expected_outcome not in _OUTCOME_STATUSES
        ):
            raise ValueError(
                "invalid VerifierStepSpec.expected_outcome: "
                f"{spec.expected_outcome!r}"
            )
        return _NormalizedVerifierStepSpec(
            kind="verifier",
            verifier_node_id=verifier_node_id,
            source_node_id=source_node_id,
            expected_outcome=spec.expected_outcome,
        )

    if isinstance(spec, BindStepSpec):
        node_id = _require_non_empty_str(spec.node_id, "BindStepSpec.node_id")
        if node_id != rule_node_id:
            raise ValueError(f"BindStepSpec for {rule_node_id!r} targets {node_id!r}")
        if not isinstance(spec.base_params, Mapping):
            raise TypeError("BindStepSpec.base_params must be a mapping")
        return _NormalizedBindStepSpec(
            kind="bind",
            node_id=node_id,
            base_params=_immutable_json_snapshot(spec.base_params),
            bindings=_compile_bindings(spec.bindings),
        )

    raise TypeError("WorkflowNodeRule.steps_by_seen_count contains a non-step spec")


def _normalize_terminal_node_ids(terminal_node_ids: tuple[str, ...]) -> tuple[str, ...]:
    terminal_ids = tuple(terminal_node_ids)
    if not terminal_ids:
        raise ValueError("terminal_node_ids must contain at least one node")
    seen: set[str] = set()
    normalized: list[str] = []
    for node_id in terminal_ids:
        node_id = _require_non_empty_str(node_id, "terminal_node_ids")
        if node_id in seen:
            raise ValueError(f"duplicate terminal node id: {node_id!r}")
        seen.add(node_id)
        normalized.append(node_id)
    return tuple(normalized)


def _normalize_expected_refs(
    expected_refs: tuple[ExpectedNodeRef, ...],
) -> tuple[_NormalizedExpectedNodeRef, ...]:
    seen: set[str] = set()
    normalized: list[_NormalizedExpectedNodeRef] = []
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
        normalized.append(
            _NormalizedExpectedNodeRef(
                node_id=node_id,
                execution_ref=execution_ref,
            )
        )
    return tuple(normalized)


def _reject_terminal_rule_overlap(
    terminal_node_ids: tuple[str, ...],
    rules: tuple[_NormalizedWorkflowNodeRule, ...],
) -> None:
    rule_node_ids = {rule.node_id for rule in rules}
    for node_id in terminal_node_ids:
        if node_id in rule_node_ids:
            raise ValueError(
                f"terminal node id must not also have a rule: {node_id!r}"
            )
```

- [ ] **Step 8: Add normalized payload builders**

```python
def _normalized_initial_param_payload(
    entry: _NormalizedInitialNodeParams,
) -> Mapping[str, Any]:
    return _ImmutableJsonMapping(
        {
            "node_id": entry.node_id,
            "execution_params": entry.execution_params,
        }
    )


def _normalized_rule_payload(rule: _NormalizedWorkflowNodeRule) -> Mapping[str, Any]:
    return _ImmutableJsonMapping(
        {
            "node_id": rule.node_id,
            "steps_by_seen_count": tuple(
                _normalized_step_payload(step)
                for step in rule.steps_by_seen_count
            ),
        }
    )


def _normalized_step_payload(step: NormalizedStepSpec) -> Mapping[str, Any]:
    if isinstance(step, _NormalizedProducerStepSpec):
        return _ImmutableJsonMapping(
            {
                "kind": step.kind,
                "node_id": step.node_id,
            }
        )
    if isinstance(step, _NormalizedVerifierStepSpec):
        return _ImmutableJsonMapping(
            {
                "kind": step.kind,
                "verifier_node_id": step.verifier_node_id,
                "source_node_id": step.source_node_id,
                "expected_outcome": step.expected_outcome,
            }
        )
    if isinstance(step, _NormalizedBindStepSpec):
        return _ImmutableJsonMapping(
            {
                "kind": step.kind,
                "node_id": step.node_id,
                "base_params": step.base_params,
                "bindings": step.bindings,
            }
        )
    raise TypeError("unknown normalized step spec")
```

- [ ] **Step 9: Update graph-context functions to accept normalized types**

Replace `_stage_initial_params` signature/body with:

```python
def _stage_initial_params(
    graph: PlanGraph,
    initial_params: tuple[_NormalizedInitialNodeParams, ...],
) -> None:
    for entry in initial_params:
        node_id = entry.node_id
        if node_id not in graph.nodes:
            raise ValueError(f"unknown initial-param node: {node_id!r}")
        graph.nodes[node_id].metadata[EXECUTION_PARAMS_KEY] = _plain_json_tree(
            entry.execution_params
        )
```

Replace `_compile_rules` with:

```python
def _compile_rules(
    graph: PlanGraph,
    rules: tuple[_NormalizedWorkflowNodeRule, ...],
) -> tuple[tuple[NodeStepRule, ...], tuple[Step, ...]]:
    compiled_rules: list[NodeStepRule] = []
    compiled_steps: list[Step] = []
    for rule in rules:
        if rule.node_id not in graph.nodes:
            raise ValueError(f"unknown workflow rule node: {rule.node_id!r}")
        steps = tuple(
            _compile_step_spec(graph, spec)
            for spec in rule.steps_by_seen_count
        )
        compiled_rules.append(NodeStepRule(rule.node_id, steps))
        compiled_steps.extend(steps)
    return tuple(compiled_rules), tuple(compiled_steps)
```

Replace `_compile_step_spec` with:

```python
def _compile_step_spec(
    graph: PlanGraph,
    spec: NormalizedStepSpec,
) -> Step:
    if isinstance(spec, _NormalizedProducerStepSpec):
        return ProducerStep(spec.node_id)

    if isinstance(spec, _NormalizedVerifierStepSpec):
        if spec.source_node_id not in graph.nodes:
            raise ValueError(f"unknown verifier source node: {spec.source_node_id!r}")
        return VerifierStep(
            spec.verifier_node_id,
            spec.source_node_id,
            expected_outcome=spec.expected_outcome,
        )

    if isinstance(spec, _NormalizedBindStepSpec):
        return BindStep(spec.node_id, spec.base_params, spec.bindings)

    raise TypeError("unknown normalized step spec")
```

Replace `_validate_terminal_node_ids` with:

```python
def _validate_terminal_node_ids(
    graph: PlanGraph,
    terminal_node_ids: tuple[str, ...],
    rule_node_ids: set[str],
) -> tuple[str, ...]:
    for node_id in terminal_node_ids:
        if node_id not in graph.nodes:
            raise ValueError(f"unknown terminal node id: {node_id!r}")
        if node_id in rule_node_ids:
            raise ValueError(
                f"terminal node id must not also have a rule: {node_id!r}"
            )
        if not graph.nodes[node_id].is_terminal:
            raise ValueError(f"declared terminal node is not terminal: {node_id!r}")
    return terminal_node_ids
```

Replace `_validate_expected_refs` signature/body with:

```python
def _validate_expected_refs(
    graph: PlanGraph,
    expected_refs: tuple[_NormalizedExpectedNodeRef, ...],
) -> None:
    for expected in expected_refs:
        if expected.node_id not in graph.nodes:
            raise ValueError(f"unknown expected-ref node: {expected.node_id!r}")
        actual_ref = graph.nodes[expected.node_id].execution_ref
        if actual_ref != expected.execution_ref:
            raise ValueError(
                f"execution_ref mismatch for {expected.node_id!r}: "
                f"expected {expected.execution_ref!r}, got {actual_ref!r}"
            )
```

- [ ] **Step 10: Tighten `_compile_bindings` taxonomy**

Replace the param-key block with:

```python
    for param_key, path in bindings.items():
        if not isinstance(param_key, str):
            raise TypeError("binding param keys must be strings")
        if not param_key:
            raise ValueError("binding param keys must be non-empty strings")
```

Keep path validation as `ValueError` for empty/malformed paths.

- [ ] **Step 11: Add compile-record builder**

```python
def _build_compile_record(
    normalized: _NormalizedWorkflowContract,
    snapshot: WorkflowContractSnapshot,
    *,
    selected_template_id: str,
    graph: PlanGraph,
) -> WorkflowCompileRecord:
    return WorkflowCompileRecord(
        workflow_id=normalized.workflow_id,
        compiler_id=WORKFLOW_CONTRACT_COMPILER_ID,
        contract_schema=WORKFLOW_CONTRACT_SCHEMA,
        contract_fingerprint_algorithm=CONTRACT_FINGERPRINT_ALGORITHM,
        contract_fingerprint=snapshot.contract_fingerprint,
        provider_id=CATALOG_CURRENT_STEP_PROVIDER_ID,
        expected_template_id=normalized.template.expected_template_id,
        selected_template_id=selected_template_id,
        graph_node_ids=tuple(sorted(graph.nodes)),
        initial_param_node_ids=tuple(
            entry.node_id for entry in normalized.initial_params
        ),
        rule_node_ids=tuple(rule.node_id for rule in normalized.rules),
        terminal_node_ids=normalized.terminal_node_ids,
        expected_refs=tuple(
            (ref.node_id, ref.execution_ref)
            for ref in normalized.expected_refs
        ),
        step_kinds_by_rule=tuple(
            (
                rule.node_id,
                tuple(step.kind for step in rule.steps_by_seen_count),
            )
            for rule in normalized.rules
        ),
        max_steps=normalized.max_steps,
    )
```

- [ ] **Step 12: Run LM4X tests**

Run:

```powershell
pytest mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py -q
```

Expected: all tests pass.

- [ ] **Step 13: Commit production implementation**

```powershell
git add mcp_server/src/rook/agent/plan_graph_workflow_contract.py
git commit -m "feat(lm4x): fingerprint workflow contract compiles"
```

---

### Task 4: Update Existing Compile Test Invariants And Boundary Guard

**Files:**
- Modify: `mcp_server/tests/test_plan_graph_workflow_contract.py`

- [ ] **Step 1: Import new constants and snapshot helper symbols**

Update imports from `rook.agent.plan_graph_current_step_provider`:

```python
from rook.agent.plan_graph_current_step_provider import (
    CATALOG_CURRENT_STEP_PROVIDER_ID,
    CatalogCurrentStepProvider,
    NodeStepRule,
)
```

Update imports from `rook.agent.plan_graph_workflow_contract`:

```python
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
```

- [ ] **Step 2: Add scaffold identity assertions to the existing success test**

In `test_compile_repair_contract_produces_initialized_scaffold_and_snapshots`, after:

```python
assert scaffold.workflow_id == "lm4w_repair_contract"
assert scaffold.max_steps == 6
```

add:

```python
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
```

- [ ] **Step 3: Add non-string binding-key validation case**

In `test_rule_and_step_spec_validation`, add this case to the param list:

```python
        (
            (
                WorkflowNodeRule(
                    "repair_same_component",
                    (BindStepSpec("repair_same_component", {}, {1: ("x",)}),),
                ),
            ),
            TypeError,
        ),
```

Add id:

```python
        "non-string-binding-key",
```

- [ ] **Step 4: Update boundary guard allowed imports**

In `test_workflow_contract_module_stays_compile_only_boundary`, update `allowed_imports` to include:

```python
        "hashlib",
        "json",
```

Keep existing allowed compile-time imports.

- [ ] **Step 5: Run existing LM4W compiler tests**

Run:

```powershell
pytest mcp_server/tests/test_plan_graph_workflow_contract.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit test compatibility updates**

```powershell
git add mcp_server/tests/test_plan_graph_workflow_contract.py
git commit -m "test(lm4x): assert workflow compile receipt invariants"
```

---

### Task 5: Run Gates And Final Verification

**Files:**
- No file edits expected.

- [ ] **Step 1: Run targeted LM4X/LM4W tests**

Run:

```powershell
pytest `
  mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py `
  mcp_server/tests/test_plan_graph_workflow_contract.py `
  mcp_server/tests/test_plan_graph_workflow_contract_chain.py `
  -q
```

Expected: all targeted tests pass.

- [ ] **Step 2: Run focused LM4N-X PlanGraph gate**

Run:

```powershell
pytest mcp_server/tests/test_plan_graph*.py -q
```

Expected: focused PlanGraph gate passes.

- [ ] **Step 3: Check production scope**

Run:

```powershell
git diff --name-only main..HEAD
```

Expected changed production files are limited to:

```text
mcp_server/src/rook/agent/plan_graph_current_step_provider.py
mcp_server/src/rook/agent/plan_graph_workflow_contract.py
```

Expected non-production additions are:

```text
docs/superpowers/specs/2026-06-27-lm4x-workflow-contract-fingerprint-design.md
docs/superpowers/plans/2026-06-27-lm4x-workflow-contract-fingerprint.md
mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py
mcp_server/tests/test_plan_graph_workflow_contract.py
```

`mcp_server/tests/test_plan_graph_workflow_contract_chain.py` should be unchanged.

- [ ] **Step 4: Run diff and drift checks**

Run:

```powershell
git diff --check main..HEAD
git diff --name-only main..HEAD -- base_agent.py knowledge/gh/operations_knowledge.json
```

Expected:

```text
git diff --check main..HEAD
```

prints nothing and exits 0.

Expected:

```text
git diff --name-only main..HEAD -- base_agent.py knowledge/gh/operations_knowledge.json
```

prints nothing.

- [ ] **Step 5: Review boundary scan**

Run:

```powershell
@'
import ast
from pathlib import Path

path = Path("mcp_server/src/rook/agent/plan_graph_workflow_contract.py")
tree = ast.parse(path.read_text())
banned = {
    "propose_next_node",
    "revalidate_proposal",
    "map_accepted_proposal_to_step",
    "execute_mapped_step",
    "run_current_mapped_step",
    "run_current_step_stream",
    "build_live_producer_record",
    "LiveProducerExpectation",
    "apply_outcome",
    "NodeOutcome",
    "RookAgent",
    "dispatcher",
    "base_agent",
    "server",
    "model",
}
names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
hits = sorted((names | attrs) & banned)
if hits:
    raise SystemExit(f"banned references: {hits}")
print("boundary scan clean")
'@ | python -
```

Expected:

```text
boundary scan clean
```

- [ ] **Step 6: Commit any final verification-only plan updates**

If no files changed during verification, do not commit. If the plan was corrected during
execution, commit that correction:

```powershell
git add docs/superpowers/plans/2026-06-27-lm4x-workflow-contract-fingerprint.md
git commit -m "docs(lm4x): refine workflow fingerprint plan"
```

---

## Self-Review Checklist

- Spec coverage:
  - public snapshot helper covered in Task 3;
  - snapshot/compile single normalization path covered in Task 3;
  - provider id constant exposure covered in Task 2;
  - new fingerprint/receipt tests covered in Task 1;
  - compatibility invariants and boundary guard covered in Task 4;
  - final gates covered in Task 5.
- Placeholder scan:
  - no `TBD`, `TODO`, `fill in`, or unspecified test content.
- Type consistency:
  - public names match spec: `WorkflowContractSnapshot`, `WorkflowCompileRecord`,
    `snapshot_workflow_contract`, `CATALOG_CURRENT_STEP_PROVIDER_ID`;
  - compile record uses `contract_fingerprint_algorithm`, not `fingerprint_algorithm`;
  - `step_kinds_by_rule` derives from `step.kind` on normalized specs.

Recommended execution approach: inline execution is acceptable because the plan is compact
and the work is deterministic/offline. Subagent-driven execution is also valid if a fresh
review checkpoint is desired before the final focused gate.
