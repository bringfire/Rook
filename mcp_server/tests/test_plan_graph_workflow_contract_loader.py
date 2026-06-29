"""LM4Y tests for loading workflow contract schema payloads."""

from __future__ import annotations

import ast
import copy
import json
import pathlib

import pytest

import rook.agent.plan_graph_workflow_contract as contract_module
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
