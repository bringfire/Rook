# LM4Y Workflow Contract Payload Loader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a strict already-parsed mapping loader that converts the LM4X normalized workflow contract schema envelope into `RookWorkflowContract`.

**Architecture:** Keep LM4Y in `plan_graph_workflow_contract.py` beside the LM4X schema constants and dataclasses. The loader validates exact schema record shapes, copies JSON-shaped payload containers to avoid caller aliasing, constructs typed dataclasses, and calls `snapshot_workflow_contract(contract)` before returning only the contract.

**Tech Stack:** Python 3, dataclasses, pytest, AST inspection, existing LM4W/LM4X workflow contract compiler module.

---

## File Structure

- Modify: `mcp_server/src/rook/agent/plan_graph_workflow_contract.py`
  - Add public `load_workflow_contract_payload(payload: Mapping[str, Any]) -> RookWorkflowContract`.
  - Add private `_load_*` helper functions.
  - Add strict field-set helpers and JSON-shaped copy helper.
  - Do not add JSON text/file parsing, compile helpers, or runtime calls.
- Create: `mcp_server/tests/test_plan_graph_workflow_contract_loader.py`
  - Dedicated LM4Y loader tests.
- Modify: `mcp_server/tests/test_plan_graph_workflow_contract.py`
  - Extend existing AST boundary guard only if needed.
  - Keep broad LM4W/LM4X test rewrites out of scope.

No new production module, no package-level exports, no chain guard, no live test.

---

### Task 1: Add Failing Loader Tests

**Files:**
- Create: `mcp_server/tests/test_plan_graph_workflow_contract_loader.py`

- [ ] **Step 1: Create the loader test file**

Add this complete file:

```python
"""LM4Y tests for loading workflow contract schema payloads."""

from __future__ import annotations

import ast
import copy
import json
import pathlib
from collections.abc import Mapping

import pytest

import rook.agent.plan_graph_workflow_contract as contract_module
from rook.agent.plan_graph_workflow_contract import (
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
    load_workflow_contract_payload,
    snapshot_workflow_contract,
)


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}
_TEMPLATE_ID = "gh_csharp_create_verify_repair_verify"


def _repair_contract(**overrides) -> RookWorkflowContract:
    values = {
        "workflow_id": "lm4y_repair_contract",
        "template": WorkflowTemplateRef(dict(_DESCRIPTOR), _TEMPLATE_ID),
        "initial_params": (
            InitialNodeParams(
                "create_script",
                {
                    "code": "A = DefinitelyMissingSymbol;",
                    "pins_in": [],
                    "pins_out": ["A:double"],
                    "name": "LM4YWorkflowContractLoader",
                    "x": 360,
                    "y": 1100,
                },
            ),
        ),
        "rules": (
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
        "terminal_node_ids": ("done",),
        "expected_refs": (
            ExpectedNodeRef("create_script", "gh_create_csharp_script:v1"),
            ExpectedNodeRef("repair_same_component", "gh_update_script:v1"),
        ),
        "max_steps": 6,
        "metadata": {
            "workflow_label": "LM4Y repair contract",
            "trace": {"slice": "LM4Y"},
        },
    }
    values.update(overrides)
    return RookWorkflowContract(**values)


def _source_snapshot():
    return snapshot_workflow_contract(_repair_contract())


def _json_payload() -> dict:
    return json.loads(json.dumps(copy.deepcopy(_source_snapshot().normalized_contract)))


def _with_removed(payload: dict, key: str) -> dict:
    clone = dict(payload)
    clone.pop(key)
    return clone


def _with_extra(payload: dict, key: str = "extra") -> dict:
    clone = dict(payload)
    clone[key] = "unexpected"
    return clone


def _first_step(payload: dict) -> dict:
    return payload["rules"][0]["steps_by_seen_count"][0]


def _repair_bind_step(payload: dict) -> dict:
    return payload["rules"][2]["steps_by_seen_count"][0]


def test_loads_direct_normalized_snapshot_payload_roundtrip():
    source = _source_snapshot()

    loaded = load_workflow_contract_payload(source.normalized_contract)
    roundtrip = snapshot_workflow_contract(loaded)

    assert isinstance(loaded, RookWorkflowContract)
    assert roundtrip.contract_fingerprint == source.contract_fingerprint
    assert roundtrip.normalized_contract == source.normalized_contract


def test_loads_json_style_parsed_payload_roundtrip():
    source = _source_snapshot()
    payload = json.loads(json.dumps(copy.deepcopy(source.normalized_contract)))

    loaded = load_workflow_contract_payload(payload)
    roundtrip = snapshot_workflow_contract(loaded)

    assert roundtrip.contract_fingerprint == source.contract_fingerprint
    assert roundtrip.normalized_contract == source.normalized_contract


def test_loaded_contract_compiles_to_matching_snapshot():
    source = _source_snapshot()
    loaded = load_workflow_contract_payload(source.normalized_contract)

    scaffold = compile_workflow_contract(loaded)

    assert scaffold.contract_snapshot.contract_fingerprint == source.contract_fingerprint
    assert scaffold.contract_snapshot.normalized_contract == source.normalized_contract


@pytest.mark.parametrize(
    "payload_factory",
    [
        lambda: _with_removed(_json_payload(), "schema"),
        lambda: _with_removed(_json_payload(), "metadata"),
        lambda: _with_extra(_json_payload()),
        lambda: {
            **_json_payload(),
            "schema": "rook.workflow_contract:v999",
        },
    ],
    ids=[
        "missing-schema",
        "missing-metadata",
        "extra-top-level",
        "unsupported-schema",
    ],
)
def test_rejects_top_level_schema_drift(payload_factory):
    with pytest.raises(ValueError):
        load_workflow_contract_payload(payload_factory())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["template"].update({"extra": True}),
        lambda payload: payload["initial_params"][0].update({"extra": True}),
        lambda payload: payload["rules"][0].update({"extra": True}),
        lambda payload: _first_step(payload).update({"extra": True}),
        lambda payload: payload["rules"][1]["steps_by_seen_count"][0].update(
            {"extra": True}
        ),
        lambda payload: _repair_bind_step(payload).update({"extra": True}),
        lambda payload: payload["expected_refs"][0].update({"extra": True}),
    ],
    ids=[
        "template",
        "initial-param",
        "rule",
        "producer-step",
        "verifier-step",
        "bind-step",
        "expected-ref",
    ],
)
def test_rejects_unknown_nested_fields(mutate):
    payload = _json_payload()
    mutate(payload)

    with pytest.raises(ValueError, match="unknown fields"):
        load_workflow_contract_payload(payload)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["template"].pop("expected_template_id"),
        lambda payload: payload["initial_params"][0].pop("execution_params"),
        lambda payload: payload["rules"][0].pop("steps_by_seen_count"),
        lambda payload: payload["expected_refs"][0].pop("execution_ref"),
    ],
    ids=[
        "template-expected-id",
        "initial-param-execution-params",
        "rule-steps",
        "expected-ref-execution-ref",
    ],
)
def test_rejects_missing_nested_fields(mutate):
    payload = _json_payload()
    mutate(payload)

    with pytest.raises(ValueError, match="missing required fields"):
        load_workflow_contract_payload(payload)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: _first_step(payload).pop("kind"),
        lambda payload: _first_step(payload).__setitem__("kind", 1),
        lambda payload: _first_step(payload).__setitem__("kind", "ProducerStepSpec"),
        lambda payload: payload["rules"][1]["steps_by_seen_count"][0].pop("kind"),
    ],
    ids=[
        "missing-kind",
        "non-string-kind",
        "unknown-kind",
        "verifier-shaped-without-kind",
    ],
)
def test_rejects_non_literal_step_dispatch(mutate):
    payload = _json_payload()
    mutate(payload)

    with pytest.raises(ValueError):
        load_workflow_contract_payload(payload)


@pytest.mark.parametrize(
    "mutate,exc_type",
    [
        (lambda payload: payload.__setitem__("metadata", None), TypeError),
        (lambda payload: payload.__setitem__("initial_params", "bad"), TypeError),
        (lambda payload: payload.__setitem__("rules", "bad"), TypeError),
        (lambda payload: payload.__setitem__("terminal_node_ids", "done"), TypeError),
        (lambda payload: payload.__setitem__("expected_refs", "bad"), TypeError),
        (
            lambda payload: _repair_bind_step(payload)["bindings"].__setitem__(
                "guid",
                "repair_anchor.component_guid",
            ),
            TypeError,
        ),
        (lambda payload: payload["metadata"].__setitem__(1, "bad"), TypeError),
    ],
    ids=[
        "metadata-none",
        "initial-params-string",
        "rules-string",
        "terminal-string",
        "expected-refs-string",
        "bind-path-dotted-string",
        "metadata-non-string-key",
    ],
)
def test_rejects_bad_container_shapes(mutate, exc_type):
    payload = _json_payload()
    mutate(payload)

    with pytest.raises(exc_type):
        load_workflow_contract_payload(payload)


def test_empty_metadata_mapping_loads():
    source = snapshot_workflow_contract(_repair_contract(metadata={}))
    payload = json.loads(json.dumps(copy.deepcopy(source.normalized_contract)))

    loaded = load_workflow_contract_payload(payload)

    assert snapshot_workflow_contract(loaded).normalized_contract["metadata"] == {}


def test_loaded_contract_does_not_alias_caller_payload():
    source = _source_snapshot()
    payload = json.loads(json.dumps(copy.deepcopy(source.normalized_contract)))

    loaded = load_workflow_contract_payload(payload)

    payload["template"]["descriptor"]["operation"] = "mutated"
    payload["metadata"]["trace"]["slice"] = "mutated"
    payload["initial_params"][0]["execution_params"]["pins_out"].append("B:double")
    _repair_bind_step(payload)["base_params"]["code"] = "A = 0.0;"
    _repair_bind_step(payload)["bindings"]["guid"].append("late")

    roundtrip = snapshot_workflow_contract(loaded)
    assert roundtrip.contract_fingerprint == source.contract_fingerprint
    assert roundtrip.normalized_contract == source.normalized_contract


@pytest.mark.parametrize(
    "mutate,exc_type",
    [
        (
            lambda payload: payload["rules"].append(payload["rules"][0]),
            ValueError,
        ),
        (
            lambda payload: payload["rules"][1]["steps_by_seen_count"][0].__setitem__(
                "expected_outcome",
                "usable",
            ),
            ValueError,
        ),
        (lambda payload: payload.__setitem__("max_steps", True), TypeError),
    ],
    ids=[
        "duplicate-rule",
        "invalid-expected-outcome",
        "max-steps-bool",
    ],
)
def test_delegates_contract_validation_to_snapshot_before_return(mutate, exc_type):
    payload = _json_payload()
    mutate(payload)

    with pytest.raises(exc_type):
        load_workflow_contract_payload(payload)


def test_rejects_top_level_non_mapping():
    with pytest.raises(TypeError):
        load_workflow_contract_payload([])


def test_loader_helpers_do_not_parse_compile_or_touch_runtime():
    source = pathlib.Path(contract_module.__file__).read_text()
    tree = ast.parse(source)
    banned_names = {
        "compile_workflow_contract",
        "select_template",
        "initialize_graph",
        "open",
        "Path",
        "yaml",
    }
    banned_json_attrs = {"loads", "dumps"}
    checked_helper_names = {
        "_copy_json_payload",
        "_copy_required_mapping",
        "_require_mapping",
        "_require_sequence",
        "_require_fields",
    }

    checked = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if (
            node.name != "load_workflow_contract_payload"
            and not node.name.startswith("_load_")
            and node.name not in checked_helper_names
        ):
            continue
        checked += 1
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                assert child.id not in banned_names
            if isinstance(child, ast.Attribute):
                assert child.attr not in banned_names
                if isinstance(child.value, ast.Name) and child.value.id == "json":
                    assert child.attr not in banned_json_attrs

    assert checked >= 2
```

- [ ] **Step 2: Run the new tests and confirm they fail for missing public loader**

Run:

```powershell
pytest mcp_server/tests/test_plan_graph_workflow_contract_loader.py -q
```

Expected: collection fails with:

```text
ImportError: cannot import name 'load_workflow_contract_payload'
```

- [ ] **Step 3: Commit failing tests**

```powershell
git add mcp_server/tests/test_plan_graph_workflow_contract_loader.py
git commit -m "test(lm4y): add workflow contract payload loader tests"
```

---

### Task 2: Implement Payload Loader

**Files:**
- Modify: `mcp_server/src/rook/agent/plan_graph_workflow_contract.py`

- [ ] **Step 1: Add field-set constants after `_OUTCOME_STATUSES`**

Add:

```python
_WORKFLOW_PAYLOAD_FIELDS = frozenset(
    {
        "schema",
        "workflow_id",
        "template",
        "initial_params",
        "rules",
        "terminal_node_ids",
        "expected_refs",
        "max_steps",
        "metadata",
    }
)
_TEMPLATE_PAYLOAD_FIELDS = frozenset({"descriptor", "expected_template_id"})
_INITIAL_PARAM_PAYLOAD_FIELDS = frozenset({"node_id", "execution_params"})
_RULE_PAYLOAD_FIELDS = frozenset({"node_id", "steps_by_seen_count"})
_EXPECTED_REF_PAYLOAD_FIELDS = frozenset({"node_id", "execution_ref"})
_PRODUCER_STEP_PAYLOAD_FIELDS = frozenset({"kind", "node_id"})
_VERIFIER_STEP_PAYLOAD_FIELDS = frozenset(
    {"kind", "verifier_node_id", "source_node_id", "expected_outcome"}
)
_BIND_STEP_PAYLOAD_FIELDS = frozenset(
    {"kind", "node_id", "base_params", "bindings"}
)
```

- [ ] **Step 2: Add public loader after `snapshot_workflow_contract`**

Add:

```python
def load_workflow_contract_payload(payload: Mapping[str, Any]) -> RookWorkflowContract:
    """Load an already-parsed LM4X workflow contract payload."""
    payload = _require_mapping(payload, "workflow contract payload")
    _require_fields(
        payload,
        required=_WORKFLOW_PAYLOAD_FIELDS,
        context="workflow contract payload",
    )
    schema = payload["schema"]
    if schema != WORKFLOW_CONTRACT_SCHEMA:
        raise ValueError(f"unsupported workflow contract schema: {schema!r}")

    contract = RookWorkflowContract(
        workflow_id=payload["workflow_id"],
        template=_load_template_ref_payload(payload["template"]),
        initial_params=tuple(
            _load_initial_param_payload(item)
            for item in _require_sequence(
                payload["initial_params"],
                "initial_params",
            )
        ),
        rules=tuple(
            _load_rule_payload(item)
            for item in _require_sequence(payload["rules"], "rules")
        ),
        terminal_node_ids=tuple(
            _require_sequence(payload["terminal_node_ids"], "terminal_node_ids")
        ),
        expected_refs=tuple(
            _load_expected_ref_payload(item)
            for item in _require_sequence(payload["expected_refs"], "expected_refs")
        ),
        max_steps=payload["max_steps"],
        metadata=_copy_required_mapping(payload["metadata"], "metadata"),
    )
    snapshot_workflow_contract(contract)
    return contract
```

Do not return the snapshot.

- [ ] **Step 3: Add private loader helpers before `_validate_max_steps`**

```python
def _load_template_ref_payload(payload: Any) -> WorkflowTemplateRef:
    payload = _require_mapping(payload, "template")
    _require_fields(
        payload,
        required=_TEMPLATE_PAYLOAD_FIELDS,
        context="template",
    )
    descriptor = _copy_required_mapping(payload["descriptor"], "template.descriptor")
    return WorkflowTemplateRef(
        descriptor=descriptor,
        expected_template_id=payload["expected_template_id"],
    )


def _load_initial_param_payload(payload: Any) -> InitialNodeParams:
    payload = _require_mapping(payload, "initial_params entry")
    _require_fields(
        payload,
        required=_INITIAL_PARAM_PAYLOAD_FIELDS,
        context="initial_params entry",
    )
    return InitialNodeParams(
        node_id=payload["node_id"],
        execution_params=_copy_required_mapping(
            payload["execution_params"],
            "initial_params.execution_params",
        ),
    )


def _load_rule_payload(payload: Any) -> WorkflowNodeRule:
    payload = _require_mapping(payload, "rules entry")
    _require_fields(payload, required=_RULE_PAYLOAD_FIELDS, context="rules entry")
    return WorkflowNodeRule(
        node_id=payload["node_id"],
        steps_by_seen_count=tuple(
            _load_step_spec_payload(item)
            for item in _require_sequence(
                payload["steps_by_seen_count"],
                "rules.steps_by_seen_count",
            )
        ),
    )


def _load_step_spec_payload(payload: Any) -> WorkflowStepSpec:
    payload = _require_mapping(payload, "step spec")
    if "kind" not in payload:
        raise ValueError("step spec missing required fields: ['kind']")
    kind = payload["kind"]
    if not isinstance(kind, str):
        raise ValueError(f"step spec kind must be a string: {kind!r}")

    if kind == "producer":
        _require_fields(
            payload,
            required=_PRODUCER_STEP_PAYLOAD_FIELDS,
            context="producer step",
        )
        return ProducerStepSpec(node_id=payload["node_id"])

    if kind == "verifier":
        _require_fields(
            payload,
            required=_VERIFIER_STEP_PAYLOAD_FIELDS,
            context="verifier step",
        )
        return VerifierStepSpec(
            verifier_node_id=payload["verifier_node_id"],
            source_node_id=payload["source_node_id"],
            expected_outcome=payload["expected_outcome"],
        )

    if kind == "bind":
        _require_fields(
            payload,
            required=_BIND_STEP_PAYLOAD_FIELDS,
            context="bind step",
        )
        return BindStepSpec(
            node_id=payload["node_id"],
            base_params=_copy_required_mapping(payload["base_params"], "bind.base_params"),
            bindings=_load_bindings_payload(payload["bindings"]),
        )

    raise ValueError(f"unknown step spec kind: {kind!r}")


def _load_expected_ref_payload(payload: Any) -> ExpectedNodeRef:
    payload = _require_mapping(payload, "expected_refs entry")
    _require_fields(
        payload,
        required=_EXPECTED_REF_PAYLOAD_FIELDS,
        context="expected_refs entry",
    )
    return ExpectedNodeRef(
        node_id=payload["node_id"],
        execution_ref=payload["execution_ref"],
    )
```

- [ ] **Step 4: Add shape/copy helpers**

```python
def _load_bindings_payload(payload: Any) -> Mapping[str, tuple[str, ...]]:
    payload = _require_mapping(payload, "bind.bindings")
    bindings: dict[str, tuple[str, ...]] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("bind.bindings keys must be strings")
        bindings[key] = tuple(_require_sequence(value, f"bind.bindings[{key!r}]"))
    return bindings


def _copy_required_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} must be a mapping")
    copied = _copy_json_payload(value)
    if not isinstance(copied, Mapping):
        raise TypeError(f"{context} must be a mapping")
    return copied


def _copy_json_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        copied: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON mapping keys must be strings")
            copied[key] = _copy_json_payload(item)
        return copied
    if isinstance(value, (list, tuple)):
        return tuple(_copy_json_payload(item) for item in value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("JSON float values must be finite")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"value is not JSON-safe: {type(value).__name__}")


def _require_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} must be a mapping")
    for key in value:
        if not isinstance(key, str):
            raise TypeError(f"{context} keys must be strings")
    return value


def _require_sequence(value: Any, context: str) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{context} must be a list or tuple")
    return tuple(value)


def _require_fields(
    payload: Mapping[str, Any],
    *,
    required: frozenset[str],
    context: str,
) -> None:
    keys = set(payload)
    missing = required - keys
    extra = keys - required
    if missing:
        raise ValueError(f"{context} missing required fields: {sorted(missing)!r}")
    if extra:
        raise ValueError(f"{context} has unknown fields: {sorted(extra)!r}")
```

- [ ] **Step 5: Run loader tests**

Run:

```powershell
pytest mcp_server/tests/test_plan_graph_workflow_contract_loader.py -q
```

Expected: all LM4Y loader tests pass.

- [ ] **Step 6: Commit loader implementation**

```powershell
git add mcp_server/src/rook/agent/plan_graph_workflow_contract.py
git commit -m "feat(lm4y): load workflow contract payloads"
```

---

### Task 3: Update Existing Boundary Guard

**Files:**
- Modify: `mcp_server/tests/test_plan_graph_workflow_contract.py`

- [ ] **Step 1: Add loader-specific AST guard to the existing boundary test**

Append this block to `test_workflow_contract_module_stays_compile_only_boundary` after the existing `referenced_attrs` assertion:

```python
    loader_banned_names = {
        "compile_workflow_contract",
        "select_template",
        "initialize_graph",
        "open",
        "Path",
        "yaml",
    }
    loader_banned_json_attrs = {"loads", "dumps"}
    loader_checked_helper_names = {
        "_copy_json_payload",
        "_copy_required_mapping",
        "_require_mapping",
        "_require_sequence",
        "_require_fields",
    }
    loader_functions_checked = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if (
            node.name != "load_workflow_contract_payload"
            and not node.name.startswith("_load_")
            and node.name not in loader_checked_helper_names
        ):
            continue
        loader_functions_checked += 1
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                assert child.id not in loader_banned_names
            if isinstance(child, ast.Attribute):
                assert child.attr not in loader_banned_names
                if isinstance(child.value, ast.Name) and child.value.id == "json":
                    assert child.attr not in loader_banned_json_attrs

    assert loader_functions_checked >= 2
```

- [ ] **Step 2: Run workflow contract tests**

Run:

```powershell
pytest mcp_server/tests/test_plan_graph_workflow_contract.py mcp_server/tests/test_plan_graph_workflow_contract_loader.py -q
```

Expected: both test files pass.

- [ ] **Step 3: Commit boundary guard update**

```powershell
git add mcp_server/tests/test_plan_graph_workflow_contract.py
git commit -m "test(lm4y): guard loader boundary"
```

---

### Task 4: Final Verification

**Files:**
- No file edits expected.

- [ ] **Step 1: Run targeted LM4Y/LM4X/LM4W tests**

Run:

```powershell
pytest `
  mcp_server/tests/test_plan_graph_workflow_contract_loader.py `
  mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py `
  mcp_server/tests/test_plan_graph_workflow_contract.py `
  mcp_server/tests/test_plan_graph_workflow_contract_chain.py `
  -q
```

Expected: all targeted tests pass.

- [ ] **Step 2: Run focused PlanGraph gate**

Run:

```powershell
$files = Get-ChildItem mcp_server/tests -Filter 'test_plan_graph*.py' | ForEach-Object { $_.FullName }
pytest $files -q
```

Expected: focused PlanGraph gate passes.

- [ ] **Step 3: Run diff checks**

Run:

```powershell
git diff --check main..HEAD
git diff --name-only main..HEAD
git diff --name-only main..HEAD -- base_agent.py knowledge/gh/operations_knowledge.json
```

Expected changed files:

```text
docs/superpowers/specs/2026-06-27-lm4y-workflow-contract-payload-loader-design.md
docs/superpowers/plans/2026-06-27-lm4y-workflow-contract-payload-loader.md
mcp_server/src/rook/agent/plan_graph_workflow_contract.py
mcp_server/tests/test_plan_graph_workflow_contract.py
mcp_server/tests/test_plan_graph_workflow_contract_loader.py
```

Expected sensitive drift command prints nothing:

```text
git diff --name-only main..HEAD -- base_agent.py knowledge/gh/operations_knowledge.json
```

- [ ] **Step 4: Confirm no new production module**

Run:

```powershell
git diff --name-only main..HEAD -- mcp_server/src/rook/agent | Sort-Object
```

Expected:

```text
mcp_server/src/rook/agent/plan_graph_workflow_contract.py
```

- [ ] **Step 5: Commit plan corrections only if needed**

If verification reveals this plan needed a correction, commit only the plan correction:

```powershell
git add docs/superpowers/plans/2026-06-27-lm4y-workflow-contract-payload-loader.md
git commit -m "docs(lm4y): refine workflow contract loader plan"
```

If no files changed during verification, do not commit.

---

## Self-Review Checklist

- Spec coverage:
  - strict LM4X schema envelope only: Task 1 tests and Task 2 loader;
  - direct and JSON-style round trip: Task 1;
  - no caller aliasing: Task 1 and Task 2 copy helper;
  - post-load snapshot validation: Task 2 and delegated-validation tests;
  - returns only `RookWorkflowContract`: Task 2 public function signature;
  - no JSON/file/YAML/compile/runtime calls from loader: Task 1 and Task 3 AST guards.
- Placeholder scan:
  - no `TBD`, `TODO`, `fill in`, or unspecified test bodies.
- Type consistency:
  - public function is `load_workflow_contract_payload`;
  - no `WorkflowContractLoadError`;
  - loader helpers are private `_load_*`;
  - sequence fields accept only `list | tuple`;
  - `metadata` is required and must be a mapping.

Execution recommendation after plan approval: inline execution using `superpowers:executing-plans`, because the slice is deterministic and no live services are involved.
