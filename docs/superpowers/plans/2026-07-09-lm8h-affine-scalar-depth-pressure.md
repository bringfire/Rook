# LM8H Affine Scalar Depth Pressure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic LM8H affine scalar live probe surface without running live Rhino/GH in the implementation PR.

**Architecture:** LM8H adds an affine-specific scalar source/packet layer and a new sibling live script. It reuses the frozen worker publication helper, neutral worker-turn renderer, scalar value applier, and static source-routing validator, but does not import or mutate LM8F behavior. The only shared validator change is a bounded allowlist extension for affine scalar source paths.

**Tech Stack:** Python 3.10, pytest, existing Rook MCP Python modules, existing LM8F fake-tool test pattern.

## Global Constraints

- No live Rhino/GH run in the implementation PR.
- No Planner model.
- No model-authored template selection.
- No worker-authored topology, components, wires, tools, code, scripts, or GUIDs.
- No `gh_edit`.
- No retry.
- No N=5.
- Canonical worker remains `gemma4:12b-it-qat` through direct Ollama.
- Canonical fixture is editable `2.0`, factor `2.0`, offset `1.5`, initial observed output `5.5`, expected output `7.5`.
- Hidden derived worker value `3.0` must not appear in pre-publication worker-visible/source/request artifacts.
- `3.0` may appear only after worker publication if the model authors it.
- Multiplication library lookup must select an exact active/non-deprecated Multiplication component; deprecated-first results gate-fail.
- Trusted editable slider GUID remains applier-only runtime authority.
- Final verifier floor is `gh_inspect_output` on final Addition `R`.
- No raw probe artifacts committed.

---

## File Structure

Create:

- `mcp_server/src/rook/agent/gh_affine_scalar_transform_expectation_sources.py`
  - Affine source-path constants, projection contract, dataclasses, and extraction from workflow/task payload + live fixture receipt.
- `mcp_server/src/rook/agent/gh_affine_scalar_transform_expectation_acceptance_criteria.py`
  - Affine worker evidence packet and legacy worker-visible projection.
- `scripts/lm8h_affine_scalar_depth_probe.py`
  - New sibling live script owning affine fixture creation, scalar runtime readiness, worker publication, action apply, live set, and verifier settle.
- `mcp_server/tests/test_gh_affine_scalar_transform_expectation_sources.py`
- `mcp_server/tests/test_gh_affine_scalar_transform_expectation_acceptance_criteria.py`
- `mcp_server/tests/test_lm8h_affine_scalar_depth_probe.py`

Modify:

- `mcp_server/src/rook/agent/local_worker_source_routing_validator.py`
  - Add affine scalar source path allowlist constants.
- `mcp_server/tests/test_local_worker_source_routing_validator.py`
  - Add static-valid and class-keyed regressions for the affine route set.

Do not modify:

- `scripts/lm8f_scalar_transform_depth_probe.py`
- `scripts/lm8g_scalar_transform_repeatability_probe.py`
- LM6/LM7 scripts
- worker publication helper
- scalar value applier
- production `src/Rook*`

---

### Task 1: Affine Source Extraction And Routing Validator Allowlist

**Files:**
- Create: `mcp_server/src/rook/agent/gh_affine_scalar_transform_expectation_sources.py`
- Create: `mcp_server/tests/test_gh_affine_scalar_transform_expectation_sources.py`
- Modify: `mcp_server/src/rook/agent/local_worker_source_routing_validator.py`
- Modify: `mcp_server/tests/test_local_worker_source_routing_validator.py`

**Interfaces:**
- Produces constants:
  - `AFFINE_EXPECTED_OUTPUT_SOURCE_PATH`
  - `AFFINE_FACTOR_VALUE_SOURCE_PATH`
  - `AFFINE_OFFSET_VALUE_SOURCE_PATH`
  - `AFFINE_PROJECTION_SOURCE_PATH`
  - `AFFINE_OBSERVED_OUTPUT_SOURCE_PATH`
  - `AFFINE_EDITABLE_VALUE_SOURCE_PATH`
  - `AFFINE_FIXTURE_ANCHOR_SOURCE_PATH`
  - `AFFINE_CONVENTION_SOURCE_PATH`
- Produces:
  - `EXPECTED_AFFINE_PROJECTION: dict[str, str]`
  - `GhAffineScalarTransformExpectationSource`
  - `GhAffineScalarTransformExpectationSources`
  - `extract_gh_affine_scalar_transform_expectation_sources(...)`
- Consumes:
  - `PlanGraph`
  - `WorkerKnowledgePacket`
- Later tasks rely on exact field names:
  - `expected_output_contract`
  - `factor_contract`
  - `offset_contract`
  - `projection_contract`
  - `observed_output`
  - `editable_observation`
  - `fixture_anchor`
  - `convention`

- [ ] **Step 1: Add failing source extraction tests**

Create `mcp_server/tests/test_gh_affine_scalar_transform_expectation_sources.py` with the following test skeleton:

```python
import ast
import inspect

import pytest

from rook.agent.gh_affine_scalar_transform_expectation_sources import (
    AFFINE_CONVENTION_SOURCE_PATH,
    AFFINE_EDITABLE_VALUE_SOURCE_PATH,
    AFFINE_EXPECTED_OUTPUT_SOURCE_PATH,
    AFFINE_FACTOR_VALUE_SOURCE_PATH,
    AFFINE_FIXTURE_ANCHOR_SOURCE_PATH,
    AFFINE_OBSERVED_OUTPUT_SOURCE_PATH,
    AFFINE_OFFSET_VALUE_SOURCE_PATH,
    AFFINE_PROJECTION_SOURCE_PATH,
    EXPECTED_AFFINE_PROJECTION,
    extract_gh_affine_scalar_transform_expectation_sources,
)
from rook.agent.local_worker_turn_context import WorkerKnowledgePacket
from rook.learning.plan_graph import GraphMemory, NodeEvidence, PlanGraph, PlanGraphNode


def _contract_payload(expected_value=7.5, factor_value=2.0, offset_value=1.5, projection=None):
    return {
        "rules": {
            "verify_affine_scalar_transform_output": {
                "expected_output_value": expected_value,
                "factor_value": factor_value,
                "offset_value": offset_value,
                "projection": projection or EXPECTED_AFFINE_PROJECTION,
            }
        }
    }


def _graph(
    *,
    observed_value=5.5,
    editable_value=2.0,
    editable_contract=None,
    component_guid="EDITABLE-GUID-1",
    internal_component_guid=None,
):
    editable_contract = editable_contract or {
        "label": "LM8H_Editable",
        "value_type": "number",
        "current_value": editable_value,
        "projection_id": "editable_times_factor_plus_offset",
    }
    receipt = {
        "observed_output_value": observed_value,
        "editable_value": editable_value,
        "scalar_anchor": {"editable_value_contract": editable_contract},
    }
    if component_guid is not None:
        receipt["scalar_anchor"]["component_guid"] = component_guid
    if internal_component_guid is not None:
        receipt["scalar_anchor"]["internal_component_guid"] = internal_component_guid
    return PlanGraph(
        nodes={
            "create_affine_scalar_transform": PlanGraphNode(
                id="create_affine_scalar_transform",
                intent="create affine scalar transform fixture",
                evidence=NodeEvidence(tool_status="success", verified=True, receipt=receipt),
            )
        },
        memory=GraphMemory(),
    )


def _convention_packet():
    return WorkerKnowledgePacket(
        packet_id="gh_affine_scalar_transform_set_value_convention",
        kind="convention",
        title="GH affine scalar transform values are changed with gh_set_value",
        content={"action_id": "draft_gh_set_value_params"},
    )


def test_extracts_affine_sources_without_guid_in_visible_anchor():
    sources = extract_gh_affine_scalar_transform_expectation_sources(
        workflow_contract_payload=_contract_payload(),
        graph=_graph(),
        convention_packets=(_convention_packet(),),
    )

    assert sources.expected_output_contract.source_path == AFFINE_EXPECTED_OUTPUT_SOURCE_PATH
    assert sources.expected_output_contract.value == 7.5
    assert sources.factor_contract.source_path == AFFINE_FACTOR_VALUE_SOURCE_PATH
    assert sources.factor_contract.value == 2.0
    assert sources.offset_contract.source_path == AFFINE_OFFSET_VALUE_SOURCE_PATH
    assert sources.offset_contract.value == 1.5
    assert sources.projection_contract.source_path == AFFINE_PROJECTION_SOURCE_PATH
    assert sources.projection_contract.value == EXPECTED_AFFINE_PROJECTION
    assert sources.observed_output.source_path == AFFINE_OBSERVED_OUTPUT_SOURCE_PATH
    assert sources.observed_output.value == 5.5
    assert sources.editable_observation.source_path == AFFINE_EDITABLE_VALUE_SOURCE_PATH
    assert sources.editable_observation.value == 2.0
    assert sources.fixture_anchor.source_path == AFFINE_FIXTURE_ANCHOR_SOURCE_PATH
    assert sources.fixture_anchor.value == {
        "label": "LM8H_Editable",
        "value_type": "number",
        "current_value": 2.0,
        "projection_id": "editable_times_factor_plus_offset",
    }
    assert sources.convention is not None
    assert sources.convention.source_path == AFFINE_CONVENTION_SOURCE_PATH
    assert "EDITABLE-GUID-1" not in repr(sources.fixture_anchor.value)


@pytest.mark.parametrize("field", ["expected_output_value", "factor_value", "offset_value"])
@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "2.0", True])
def test_affine_contract_numbers_must_be_finite(field, bad_value):
    payload = _contract_payload()
    payload["rules"]["verify_affine_scalar_transform_output"][field] = bad_value

    with pytest.raises(ValueError, match=field):
        extract_gh_affine_scalar_transform_expectation_sources(
            workflow_contract_payload=payload,
            graph=_graph(),
            convention_packets=(),
        )


def test_projection_must_be_exact_affine_relationship():
    bad_projection = {
        "projection_id": "editable_plus_offset",
        "description": "observed_output = editable_value + offset_value",
        "editable_variable": "editable_value",
        "offset_variable": "offset_value",
        "output_variable": "observed_output",
    }

    with pytest.raises(ValueError, match=AFFINE_PROJECTION_SOURCE_PATH):
        extract_gh_affine_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(projection=bad_projection),
            graph=_graph(),
            convention_packets=(),
        )


def test_fixture_anchor_contract_must_not_expose_guid():
    graph = _graph(
        editable_contract={
            "label": "LM8H_Editable",
            "value_type": "number",
            "current_value": 2.0,
            "projection_id": "editable_times_factor_plus_offset",
            "component_guid": "EDITABLE-GUID-1",
        }
    )

    with pytest.raises(ValueError, match=AFFINE_FIXTURE_ANCHOR_SOURCE_PATH):
        extract_gh_affine_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(),
            graph=graph,
            convention_packets=(),
        )


def test_affine_source_import_boundary_stays_narrow():
    import rook.agent.gh_affine_scalar_transform_expectation_sources as module

    source = inspect.getsource(module)
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")

    forbidden = {
        "rook.server",
        "scripts.lm8f_scalar_transform_depth_probe",
        "scripts.lm8c_gh_scalar_expectation_live_probe",
        "scripts.lm7e_model_authored_live_splice_probe",
        "yaml",
        "LiteLLM",
        "BindStepSpec",
    }
    assert imports.isdisjoint(forbidden)
    assert "base_params" not in source
```

- [ ] **Step 2: Run source extraction tests to verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_gh_affine_scalar_transform_expectation_sources.py -q
```

Expected: import failure for missing module.

- [ ] **Step 3: Implement affine source extraction module**

Create `mcp_server/src/rook/agent/gh_affine_scalar_transform_expectation_sources.py`:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

from rook.agent.local_worker_turn_context import WorkerKnowledgePacket
from rook.learning.plan_graph import PlanGraph


AFFINE_EXPECTED_OUTPUT_SOURCE_PATH = (
    "workflow_contract.rules.verify_affine_scalar_transform_output.expected_output_value"
)
AFFINE_FACTOR_VALUE_SOURCE_PATH = (
    "workflow_contract.rules.verify_affine_scalar_transform_output.factor_value"
)
AFFINE_OFFSET_VALUE_SOURCE_PATH = (
    "workflow_contract.rules.verify_affine_scalar_transform_output.offset_value"
)
AFFINE_PROJECTION_SOURCE_PATH = (
    "workflow_contract.rules.verify_affine_scalar_transform_output.projection"
)
AFFINE_OBSERVED_OUTPUT_SOURCE_PATH = (
    "create_affine_scalar_transform.receipt.gh_receipt.observed_output_value"
)
AFFINE_EDITABLE_VALUE_SOURCE_PATH = (
    "create_affine_scalar_transform.receipt.gh_receipt.editable_value"
)
AFFINE_FIXTURE_ANCHOR_SOURCE_PATH = (
    "create_affine_scalar_transform.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
AFFINE_CONVENTION_SOURCE_PATH = "gh_affine_scalar_transform_set_value_convention"

EXPECTED_AFFINE_PROJECTION = {
    "projection_id": "editable_times_factor_plus_offset",
    "description": "observed_output = editable_value * factor_value + offset_value",
    "editable_variable": "editable_value",
    "factor_variable": "factor_value",
    "offset_variable": "offset_value",
    "output_variable": "observed_output",
}


@dataclass(frozen=True)
class GhAffineScalarTransformExpectationSource:
    source_class: str
    source_path: str
    value: Any


@dataclass(frozen=True)
class GhAffineScalarTransformExpectationSources:
    expected_output_contract: GhAffineScalarTransformExpectationSource
    factor_contract: GhAffineScalarTransformExpectationSource
    offset_contract: GhAffineScalarTransformExpectationSource
    projection_contract: GhAffineScalarTransformExpectationSource
    observed_output: GhAffineScalarTransformExpectationSource
    editable_observation: GhAffineScalarTransformExpectationSource
    fixture_anchor: GhAffineScalarTransformExpectationSource
    convention: GhAffineScalarTransformExpectationSource | None = None


def extract_gh_affine_scalar_transform_expectation_sources(
    *,
    workflow_contract_payload: Mapping[str, Any],
    graph: PlanGraph,
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> GhAffineScalarTransformExpectationSources:
    return GhAffineScalarTransformExpectationSources(
        expected_output_contract=GhAffineScalarTransformExpectationSource(
            "expected_output_contract",
            AFFINE_EXPECTED_OUTPUT_SOURCE_PATH,
            _rule_number(workflow_contract_payload, "expected_output_value", AFFINE_EXPECTED_OUTPUT_SOURCE_PATH),
        ),
        factor_contract=GhAffineScalarTransformExpectationSource(
            "expected_output_contract",
            AFFINE_FACTOR_VALUE_SOURCE_PATH,
            _rule_number(workflow_contract_payload, "factor_value", AFFINE_FACTOR_VALUE_SOURCE_PATH),
        ),
        offset_contract=GhAffineScalarTransformExpectationSource(
            "expected_output_contract",
            AFFINE_OFFSET_VALUE_SOURCE_PATH,
            _rule_number(workflow_contract_payload, "offset_value", AFFINE_OFFSET_VALUE_SOURCE_PATH),
        ),
        projection_contract=GhAffineScalarTransformExpectationSource(
            "expected_output_contract",
            AFFINE_PROJECTION_SOURCE_PATH,
            _projection(workflow_contract_payload),
        ),
        observed_output=GhAffineScalarTransformExpectationSource(
            "receipt_observation",
            AFFINE_OBSERVED_OUTPUT_SOURCE_PATH,
            _finite_number(_receipt(graph).get("observed_output_value"), AFFINE_OBSERVED_OUTPUT_SOURCE_PATH),
        ),
        editable_observation=GhAffineScalarTransformExpectationSource(
            "receipt_observation",
            AFFINE_EDITABLE_VALUE_SOURCE_PATH,
            _finite_number(_receipt(graph).get("editable_value"), AFFINE_EDITABLE_VALUE_SOURCE_PATH),
        ),
        fixture_anchor=GhAffineScalarTransformExpectationSource(
            "fixture_anchor",
            AFFINE_FIXTURE_ANCHOR_SOURCE_PATH,
            _editable_value_contract(graph),
        ),
        convention=_convention_source(convention_packets),
    )


def _rule(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    rules = payload.get("rules")
    if not isinstance(rules, Mapping):
        raise ValueError(f"{AFFINE_EXPECTED_OUTPUT_SOURCE_PATH} rules missing")
    verify = rules.get("verify_affine_scalar_transform_output")
    if not isinstance(verify, Mapping):
        raise ValueError(f"{AFFINE_EXPECTED_OUTPUT_SOURCE_PATH} rule missing")
    return verify


def _rule_number(payload: Mapping[str, Any], key: str, path: str) -> float | int:
    return _finite_number(_rule(payload).get(key), path)


def _projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    projection = _rule(payload).get("projection")
    if not isinstance(projection, Mapping):
        raise ValueError(f"{AFFINE_PROJECTION_SOURCE_PATH} missing")
    copied = dict(projection)
    if copied != EXPECTED_AFFINE_PROJECTION:
        raise ValueError(f"{AFFINE_PROJECTION_SOURCE_PATH} invalid")
    return copied


def _receipt(graph: PlanGraph) -> Mapping[str, Any]:
    if "create_affine_scalar_transform" not in graph.nodes:
        raise ValueError(f"{AFFINE_OBSERVED_OUTPUT_SOURCE_PATH} node missing")
    evidence = graph.nodes["create_affine_scalar_transform"].evidence
    if evidence is None or not isinstance(evidence.receipt, Mapping):
        raise ValueError(f"{AFFINE_OBSERVED_OUTPUT_SOURCE_PATH} receipt missing")
    return evidence.receipt


def _editable_value_contract(graph: PlanGraph) -> dict[str, Any]:
    anchor = _receipt(graph).get("scalar_anchor")
    if not isinstance(anchor, Mapping):
        raise ValueError(f"{AFFINE_FIXTURE_ANCHOR_SOURCE_PATH} scalar_anchor missing")
    _trusted_anchor_guid(anchor)
    contract = anchor.get("editable_value_contract")
    if not isinstance(contract, Mapping):
        raise ValueError(f"{AFFINE_FIXTURE_ANCHOR_SOURCE_PATH} missing")
    copied = dict(contract)
    if "component_guid" in copied or "guid" in copied:
        raise ValueError(f"{AFFINE_FIXTURE_ANCHOR_SOURCE_PATH} must not expose guid")
    required = {"label", "value_type", "current_value", "projection_id"}
    if set(copied) != required:
        raise ValueError(f"{AFFINE_FIXTURE_ANCHOR_SOURCE_PATH} invalid fields")
    if copied["value_type"] != "number":
        raise ValueError(f"{AFFINE_FIXTURE_ANCHOR_SOURCE_PATH} value_type invalid")
    _finite_number(copied["current_value"], AFFINE_FIXTURE_ANCHOR_SOURCE_PATH)
    if copied["projection_id"] != EXPECTED_AFFINE_PROJECTION["projection_id"]:
        raise ValueError(f"{AFFINE_FIXTURE_ANCHOR_SOURCE_PATH} projection_id invalid")
    return copied


def _trusted_anchor_guid(anchor: Mapping[str, Any]) -> str:
    component_guid_present = "component_guid" in anchor
    internal_guid_present = "internal_component_guid" in anchor
    if component_guid_present == internal_guid_present:
        raise ValueError(f"{AFFINE_FIXTURE_ANCHOR_SOURCE_PATH} trusted anchor guid invalid")
    guid = anchor["component_guid"] if component_guid_present else anchor["internal_component_guid"]
    if not isinstance(guid, str) or not guid.strip():
        raise ValueError(f"{AFFINE_FIXTURE_ANCHOR_SOURCE_PATH} trusted anchor guid invalid")
    return guid


def _convention_source(
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> GhAffineScalarTransformExpectationSource | None:
    matches = [
        packet
        for packet in convention_packets
        if getattr(packet, "packet_id", None) == AFFINE_CONVENTION_SOURCE_PATH
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"{AFFINE_CONVENTION_SOURCE_PATH} ambiguous")
    packet = matches[0]
    return GhAffineScalarTransformExpectationSource(
        source_class="convention",
        source_path=AFFINE_CONVENTION_SOURCE_PATH,
        value=dict(packet.content) if isinstance(packet.content, Mapping) else packet.content,
    )


def _finite_number(value: Any, source_path: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{source_path} must be a finite number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{source_path} must be a finite number")
    return value


__all__ = (
    "AFFINE_EXPECTED_OUTPUT_SOURCE_PATH",
    "AFFINE_FACTOR_VALUE_SOURCE_PATH",
    "AFFINE_OFFSET_VALUE_SOURCE_PATH",
    "AFFINE_PROJECTION_SOURCE_PATH",
    "AFFINE_OBSERVED_OUTPUT_SOURCE_PATH",
    "AFFINE_EDITABLE_VALUE_SOURCE_PATH",
    "AFFINE_FIXTURE_ANCHOR_SOURCE_PATH",
    "AFFINE_CONVENTION_SOURCE_PATH",
    "EXPECTED_AFFINE_PROJECTION",
    "GhAffineScalarTransformExpectationSource",
    "GhAffineScalarTransformExpectationSources",
    "extract_gh_affine_scalar_transform_expectation_sources",
)
```

- [ ] **Step 4: Extend static routing validator allowlists**

In `mcp_server/src/rook/agent/local_worker_source_routing_validator.py`, add constants beside the existing scalar transform constants:

```python
AFFINE_SCALAR_TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH = (
    "workflow_contract.rules.verify_affine_scalar_transform_output.expected_output_value"
)
AFFINE_SCALAR_TRANSFORM_FACTOR_VALUE_SOURCE_PATH = (
    "workflow_contract.rules.verify_affine_scalar_transform_output.factor_value"
)
AFFINE_SCALAR_TRANSFORM_OFFSET_VALUE_SOURCE_PATH = (
    "workflow_contract.rules.verify_affine_scalar_transform_output.offset_value"
)
AFFINE_SCALAR_TRANSFORM_PROJECTION_SOURCE_PATH = (
    "workflow_contract.rules.verify_affine_scalar_transform_output.projection"
)
AFFINE_SCALAR_TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH = (
    "create_affine_scalar_transform.receipt.gh_receipt.observed_output_value"
)
AFFINE_SCALAR_TRANSFORM_EDITABLE_VALUE_SOURCE_PATH = (
    "create_affine_scalar_transform.receipt.gh_receipt.editable_value"
)
AFFINE_SCALAR_TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH = (
    "create_affine_scalar_transform.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
AFFINE_SCALAR_TRANSFORM_CONVENTION_SOURCE_PATH = (
    "gh_affine_scalar_transform_set_value_convention"
)
```

Add those paths to `_ALLOWED_SOURCE_PATHS` under their existing source classes:

```python
"convention": (
    CONVENTION_SOURCE_PATH,
    "grasshopper_definition_style_convention",
    SCALAR_CONVENTION_SOURCE_PATH,
    SCALAR_TRANSFORM_CONVENTION_SOURCE_PATH,
    AFFINE_SCALAR_TRANSFORM_CONVENTION_SOURCE_PATH,
),
"expected_output_contract": (
    SCALAR_EXPECTED_OUTPUT_SOURCE_PATH,
    SCALAR_TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
    SCALAR_TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
    SCALAR_TRANSFORM_PROJECTION_SOURCE_PATH,
    AFFINE_SCALAR_TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
    AFFINE_SCALAR_TRANSFORM_FACTOR_VALUE_SOURCE_PATH,
    AFFINE_SCALAR_TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
    AFFINE_SCALAR_TRANSFORM_PROJECTION_SOURCE_PATH,
),
"receipt_observation": (
    SCALAR_OBSERVED_OUTPUT_SOURCE_PATH,
    SCALAR_TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
    SCALAR_TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
    AFFINE_SCALAR_TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
    AFFINE_SCALAR_TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
),
"fixture_anchor": (
    SCALAR_FIXTURE_ANCHOR_SOURCE_PATH,
    SCALAR_TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH,
    AFFINE_SCALAR_TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH,
),
```

- [ ] **Step 5: Add routing validator tests**

In `mcp_server/tests/test_local_worker_source_routing_validator.py`, add helper `_gh_affine_scalar_transform_artifact()` near `_gh_scalar_transform_artifact()`:

```python
def _gh_affine_scalar_transform_artifact(fixture_anchor_purpose="evidence_context"):
    return {
        "schema": SOURCE_ROUTING_SCHEMA,
        "routes": [
            {
                "node_id": "set_scalar_value",
                "visible_sources": [
                    {
                        "route_id": "affine_scalar_expected_output",
                        "source_class": "expected_output_contract",
                        "source_path": "workflow_contract.rules.verify_affine_scalar_transform_output.expected_output_value",
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_factor_value",
                        "source_class": "expected_output_contract",
                        "source_path": "workflow_contract.rules.verify_affine_scalar_transform_output.factor_value",
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_offset_value",
                        "source_class": "expected_output_contract",
                        "source_path": "workflow_contract.rules.verify_affine_scalar_transform_output.offset_value",
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_projection",
                        "source_class": "expected_output_contract",
                        "source_path": "workflow_contract.rules.verify_affine_scalar_transform_output.projection",
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_current_output",
                        "source_class": "receipt_observation",
                        "source_path": "create_affine_scalar_transform.receipt.gh_receipt.observed_output_value",
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_current_editable_value",
                        "source_class": "receipt_observation",
                        "source_path": "create_affine_scalar_transform.receipt.gh_receipt.editable_value",
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_editable_target_contract",
                        "source_class": "fixture_anchor",
                        "source_path": "create_affine_scalar_transform.receipt.gh_receipt.scalar_anchor.editable_value_contract",
                        "purpose": fixture_anchor_purpose,
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_set_value_convention",
                        "source_class": "convention",
                        "source_path": "gh_affine_scalar_transform_set_value_convention",
                        "purpose": "evidence_context",
                        "required": False,
                    },
                ],
            }
        ],
    }
```

Add tests:

```python
def test_gh_affine_scalar_transform_routes_are_static_valid():
    report = validate_worker_visible_source_routing(_gh_affine_scalar_transform_artifact())

    assert report.valid is True
    assert report.routability_evaluated is False
    assert report.static_diagnostics == ()
    assert report.routability_diagnostics == ()


def test_gh_affine_scalar_transform_fixture_anchor_cannot_feed_acceptance_criteria():
    report = validate_worker_visible_source_routing(
        _gh_affine_scalar_transform_artifact(fixture_anchor_purpose="acceptance_criteria")
    )

    assert report.valid is False
    assert [
        (diagnostic.code, diagnostic.source_class, diagnostic.purpose)
        for diagnostic in report.static_diagnostics
    ] == [("invalid_source_purpose", "fixture_anchor", "acceptance_criteria")]


def test_gh_affine_scalar_transform_source_paths_are_class_keyed():
    artifact = _gh_affine_scalar_transform_artifact()
    artifact["routes"][0]["visible_sources"][0] = {
        "route_id": "wrong_class_affine_expected_value",
        "source_class": "receipt_observation",
        "source_path": "workflow_contract.rules.verify_affine_scalar_transform_output.expected_output_value",
        "purpose": "acceptance_criteria",
        "required": True,
    }

    report = validate_worker_visible_source_routing(artifact)

    assert report.valid is False
    assert [
        diagnostic.code
        for diagnostic in report.static_diagnostics
        if diagnostic.route_id == "wrong_class_affine_expected_value"
    ] == ["invalid_source_path"]
```

- [ ] **Step 6: Run Task 1 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_gh_affine_scalar_transform_expectation_sources.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q
```

Expected: pass.

- [ ] **Step 7: Commit Task 1**

```powershell
git add `
  mcp_server\src\rook\agent\gh_affine_scalar_transform_expectation_sources.py `
  mcp_server\src\rook\agent\local_worker_source_routing_validator.py `
  mcp_server\tests\test_gh_affine_scalar_transform_expectation_sources.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py
git commit -m "feat(lm8h): add affine scalar source routing"
```

---

### Task 2: Affine Worker Evidence Packet

**Files:**
- Create: `mcp_server/src/rook/agent/gh_affine_scalar_transform_expectation_acceptance_criteria.py`
- Create: `mcp_server/tests/test_gh_affine_scalar_transform_expectation_acceptance_criteria.py`

**Interfaces:**
- Consumes from Task 1:
  - `GhAffineScalarTransformExpectationSource`
  - `GhAffineScalarTransformExpectationSources`
  - affine source path constants
  - `EXPECTED_AFFINE_PROJECTION`
- Produces:
  - `GH_AFFINE_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA`
  - `affine_scalar_transform_action_selection_contract() -> dict[str, Any]`
  - `assemble_gh_affine_scalar_transform_expectation_packet(sources) -> dict[str, Any]`
  - `project_gh_affine_scalar_transform_expectation_legacy(packet) -> dict[str, Any]`

- [ ] **Step 1: Add failing packet tests**

Create `mcp_server/tests/test_gh_affine_scalar_transform_expectation_acceptance_criteria.py`:

```python
import ast
import hashlib
import inspect
import json

import pytest

from rook.agent import gh_affine_scalar_transform_expectation_acceptance_criteria as module
from rook.agent.gh_affine_scalar_transform_expectation_acceptance_criteria import (
    GH_AFFINE_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA,
    GhAffineScalarTransformExpectationSource,
    GhAffineScalarTransformExpectationSources,
    affine_scalar_transform_action_selection_contract,
    assemble_gh_affine_scalar_transform_expectation_packet,
    project_gh_affine_scalar_transform_expectation_legacy,
)

EXPECTED_PATH = "workflow_contract.rules.verify_affine_scalar_transform_output.expected_output_value"
FACTOR_PATH = "workflow_contract.rules.verify_affine_scalar_transform_output.factor_value"
OFFSET_PATH = "workflow_contract.rules.verify_affine_scalar_transform_output.offset_value"
PROJECTION_PATH = "workflow_contract.rules.verify_affine_scalar_transform_output.projection"
OBSERVED_PATH = "create_affine_scalar_transform.receipt.gh_receipt.observed_output_value"
EDITABLE_PATH = "create_affine_scalar_transform.receipt.gh_receipt.editable_value"
ANCHOR_PATH = "create_affine_scalar_transform.receipt.gh_receipt.scalar_anchor.editable_value_contract"
CONVENTION_PATH = "gh_affine_scalar_transform_set_value_convention"


def _projection():
    return {
        "projection_id": "editable_times_factor_plus_offset",
        "description": "observed_output = editable_value * factor_value + offset_value",
        "editable_variable": "editable_value",
        "factor_variable": "factor_value",
        "offset_variable": "offset_value",
        "output_variable": "observed_output",
    }


def _valid_sources(**overrides):
    values = {
        "expected_output_contract": GhAffineScalarTransformExpectationSource("expected_output_contract", EXPECTED_PATH, 7.5),
        "factor_contract": GhAffineScalarTransformExpectationSource("expected_output_contract", FACTOR_PATH, 2.0),
        "offset_contract": GhAffineScalarTransformExpectationSource("expected_output_contract", OFFSET_PATH, 1.5),
        "projection_contract": GhAffineScalarTransformExpectationSource("expected_output_contract", PROJECTION_PATH, _projection()),
        "observed_output": GhAffineScalarTransformExpectationSource("receipt_observation", OBSERVED_PATH, 5.5),
        "editable_observation": GhAffineScalarTransformExpectationSource("receipt_observation", EDITABLE_PATH, 2.0),
        "fixture_anchor": GhAffineScalarTransformExpectationSource(
            "fixture_anchor",
            ANCHOR_PATH,
            {
                "label": "LM8H_Editable",
                "value_type": "number",
                "current_value": 2.0,
                "projection_id": "editable_times_factor_plus_offset",
            },
        ),
        "convention": GhAffineScalarTransformExpectationSource(
            "convention",
            CONVENTION_PATH,
            {"action_id": "draft_gh_set_value_params"},
        ),
    }
    values.update(overrides)
    return GhAffineScalarTransformExpectationSources(**values)


def _without_fingerprint(packet):
    copied = dict(packet)
    copied.pop("fingerprint")
    return copied


def test_public_surface():
    assert module.__all__ == (
        "GH_AFFINE_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA",
        "GhAffineScalarTransformExpectationSource",
        "GhAffineScalarTransformExpectationSources",
        "affine_scalar_transform_action_selection_contract",
        "assemble_gh_affine_scalar_transform_expectation_packet",
        "project_gh_affine_scalar_transform_expectation_legacy",
    )
    assert (
        GH_AFFINE_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA
        == "rook.gh_affine_scalar_transform_expectation_packet:v1"
    )


def test_action_selection_contract_preserves_two_pass_shapes():
    contract = affine_scalar_transform_action_selection_contract()

    assert contract["required_action_id"] == "draft_gh_set_value_params"
    assert contract["pass1_decision_required_fields_if_acting"] == ["kind", "action_id"]
    assert contract["final_action_request_required_fields"] == [
        "schema",
        "kind",
        "action_id",
        "rationale",
        "input",
    ]
    assert contract["action_input_schema"] == {
        "type": "object",
        "required": ["value"],
        "properties": {"value": {"type": "number"}},
        "additionalProperties": False,
    }
    assert "you must act" not in contract["worker_agency"].casefold()
    assert "input" not in contract["pass1_decision_required_fields_if_acting"]


def test_assembles_affine_packet_without_derived_target_value():
    packet = assemble_gh_affine_scalar_transform_expectation_packet(_valid_sources())

    assert packet["schema"] == GH_AFFINE_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA
    assert packet["fields"]["current_editable_value"] == 2.0
    assert packet["fields"]["factor_value"] == 2.0
    assert packet["fields"]["offset_value"] == 1.5
    assert packet["fields"]["current_observed_output"] == 5.5
    assert packet["fields"]["expected_output_value"] == 7.5
    assert packet["fields"]["projection"] == _projection()
    assert packet["fields"]["recommended_action_id"] == "draft_gh_set_value_params"
    assert packet["fields"]["acceptance_criteria"] == {
        "source": "gh_affine_scalar_transform_expectation",
        "criteria": [
            {
                "criterion_id": "match_expected_observed_output",
                "description": "Set the editable scalar value so the inspected GH output equals the source-owned expected output value.",
                "source": EXPECTED_PATH,
            },
            {
                "criterion_id": "use_affine_scalar_projection",
                "description": "Use the source-owned scalar projection relationship: observed_output = editable_value * factor_value + offset_value.",
                "source": PROJECTION_PATH,
            },
        ],
    }
    rendered = json.dumps(packet, sort_keys=True)
    assert "3.0" not in rendered
    assert "set editable value to 3" not in rendered.lower()
    assert "component_guid" not in rendered
    assert "EDITABLE-GUID" not in rendered
    assert "gh_edit" not in rendered
    assert "gh_update_script" not in rendered
    assert "repair_same_component" not in rendered
    assert packet["fingerprint"].startswith("sha256:")


def test_legacy_projection_excludes_schema_source_set_source_class_and_fingerprint():
    packet = assemble_gh_affine_scalar_transform_expectation_packet(_valid_sources())

    projection = project_gh_affine_scalar_transform_expectation_legacy(packet)

    assert projection == packet["fields"]["acceptance_criteria"]
    rendered = json.dumps(projection, sort_keys=True)
    for forbidden in ("schema", "source_set", "source_class", "fingerprint"):
        assert forbidden not in rendered
    assert "3.0" not in rendered


def test_fingerprint_matches_canonical_packet_without_fingerprint():
    packet = assemble_gh_affine_scalar_transform_expectation_packet(_valid_sources())

    expected = hashlib.sha256(
        json.dumps(
            _without_fingerprint(packet),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert packet["fingerprint"] == f"sha256:{expected}"


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "7.5", True])
def test_numeric_sources_fail_closed_for_non_finite_number(bad_value):
    for field_name in ("expected_output_contract", "factor_contract", "offset_contract", "observed_output", "editable_observation"):
        sources = _valid_sources(
            **{
                field_name: GhAffineScalarTransformExpectationSource(
                    source_class="expected_output_contract" if "contract" in field_name else "receipt_observation",
                    source_path=EXPECTED_PATH,
                    value=bad_value,
                )
            }
        )
        with pytest.raises(ValueError):
            assemble_gh_affine_scalar_transform_expectation_packet(sources)


def test_fixture_anchor_cannot_contain_guid_or_feed_criteria():
    with pytest.raises(ValueError, match="fixture_anchor"):
        assemble_gh_affine_scalar_transform_expectation_packet(
            _valid_sources(
                fixture_anchor=GhAffineScalarTransformExpectationSource(
                    source_class="fixture_anchor",
                    source_path=ANCHOR_PATH,
                    value={
                        "label": "LM8H_Editable",
                        "value_type": "number",
                        "current_value": 2.0,
                        "projection_id": "editable_times_factor_plus_offset",
                        "component_guid": "EDITABLE-GUID-1",
                    },
                )
            )
        )


def test_import_boundary_stays_narrow():
    source = inspect.getsource(module)
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")

    forbidden_import_fragments = (
        "plan_graph",
        "RookWorkflowContract",
        "lm5k_worker_probe",
        "lm8f_scalar_transform_depth_probe",
        "lm8c_gh_scalar_expectation_live_probe",
        "LiteLLM",
        "yaml",
    )
    for fragment in forbidden_import_fragments:
        assert not any(fragment in imported for imported in imports)
    assert "base_params" not in source
```

- [ ] **Step 2: Run packet tests to verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_gh_affine_scalar_transform_expectation_acceptance_criteria.py -q
```

Expected: import failure for missing module.

- [ ] **Step 3: Implement affine packet module**

Create `mcp_server/src/rook/agent/gh_affine_scalar_transform_expectation_acceptance_criteria.py` by adapting the LM8F packet module with these exact differences:

```python
GH_AFFINE_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA = (
    "rook.gh_affine_scalar_transform_expectation_packet:v1"
)
```

Packet field additions:

```python
"fields": {
    "current_editable_value": sources.editable_observation.value,
    "factor_value": sources.factor_contract.value,
    "offset_value": sources.offset_contract.value,
    "current_observed_output": sources.observed_output.value,
    "expected_output_value": sources.expected_output_contract.value,
    "projection": dict(sources.projection_contract.value),
    "editable_value_contract": dict(sources.fixture_anchor.value),
    "recommended_action_id": "draft_gh_set_value_params",
    "action_selection_contract": affine_scalar_transform_action_selection_contract(),
    "acceptance_criteria": acceptance_criteria,
}
```

Criteria:

```python
criteria = [
    {
        "criterion_id": "match_expected_observed_output",
        "description": "Set the editable scalar value so the inspected GH output equals the source-owned expected output value.",
        "source": sources.expected_output_contract.source_path,
        "source_class": sources.expected_output_contract.source_class,
    },
    {
        "criterion_id": "use_affine_scalar_projection",
        "description": "Use the source-owned scalar projection relationship: observed_output = editable_value * factor_value + offset_value.",
        "source": sources.projection_contract.source_path,
        "source_class": sources.projection_contract.source_class,
    },
]
```

Validation must reject:

- wrong source classes
- wrong source paths
- non-finite expected/factor/offset/observed/editable values
- projection not equal to `EXPECTED_AFFINE_PROJECTION`
- fixture anchor with `guid` or `component_guid`
- malformed convention, including any `gh_edit` tool authority

- [ ] **Step 4: Run Task 2 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_gh_affine_scalar_transform_expectation_sources.py `
  mcp_server\tests\test_gh_affine_scalar_transform_expectation_acceptance_criteria.py `
  -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add `
  mcp_server\src\rook\agent\gh_affine_scalar_transform_expectation_acceptance_criteria.py `
  mcp_server\tests\test_gh_affine_scalar_transform_expectation_acceptance_criteria.py
git commit -m "feat(lm8h): assemble affine scalar worker evidence"
```

---

### Task 3: LM8H Live Script Fixture And Scalar Runtime Readiness

**Files:**
- Create: `scripts/lm8h_affine_scalar_depth_probe.py`
- Create/modify: `mcp_server/tests/test_lm8h_affine_scalar_depth_probe.py`

**Interfaces:**
- Consumes Task 1 and Task 2 modules.
- Produces script-local functions:
  - `_args(argv) -> argparse.Namespace`
  - `_canonical_evidence_is_valid(args) -> bool`
  - `_new_run_dir(run_root) -> Path`
  - `_affine_scalar_source_routing_artifact() -> dict[str, Any]`
  - `_affine_scalar_contract_payload() -> dict[str, Any]`
  - `_create_affine_fixture(tool_executor) -> dict[str, Any]`
  - `_affine_runtime_context(...) -> dict[str, Any]`
- Later task relies on:
  - `_run_probe(...) -> Path`
  - `FixtureSetupFailure`

- [ ] **Step 1: Seed LM8H test file with CLI, drift, and routing tests**

Create `mcp_server/tests/test_lm8h_affine_scalar_depth_probe.py`:

```python
from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm8h_affine_scalar_depth_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location("lm8h_affine_scalar_depth_probe", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical_affine_shape():
    args = PROBE._args([])

    assert args.model == "gemma4:12b-it-qat"
    assert args.endpoint == "http://localhost:11434/api/chat"
    assert args.temperature == 0
    assert args.timeout_s == 120
    assert args.excerpt_chars == 1200
    assert args.run_dir == "probe_runs"
    assert args.canonical_evidence is True


def test_cli_rejects_non_lm8h_surfaces():
    forbidden = [
        ["--phase", "receipt_recon"],
        ["--attempts", "5"],
        ["--retry-clean-observation"],
        ["--planner-provider-command", "x"],
        ["--prompt-profile", "shape_guidance_v2"],
        ["--request-json", "request.json"],
        ["--gh-edit"],
    ]
    for argv in forbidden:
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_manifest_records_lm8h_identity():
    manifest = PROBE._manifest(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        canonical_evidence=True,
    )

    assert manifest["schema"] == "rook.lm8h_affine_scalar_depth_probe:v1"
    assert manifest["attempts"] == 1
    assert manifest["initial_editable_value"] == 2.0
    assert manifest["factor_value"] == 2.0
    assert manifest["offset_value"] == 1.5
    assert manifest["initial_observed_output"] == 5.5
    assert manifest["expected_output_value"] == 7.5
    assert manifest["projection_id"] == "editable_times_factor_plus_offset"
    assert manifest["worker_retry_enabled"] is False
    assert manifest["planner_model"] is None
    assert manifest["gh_edit_enabled"] is False


def test_lm8h_source_does_not_import_lm8f_lm8g_repair_planner_retry_or_gh_edit_paths():
    source = inspect.getsource(PROBE)
    forbidden_import_or_call_fragments = (
        "lm8f_scalar_transform_depth_probe",
        "lm8g_scalar_transform_repeatability_probe",
        "lm6a_live_worker_splice_probe",
        "lm7e_model_authored_live_splice_probe",
        "planner_worker_contract_request",
        "workflow_validate",
        "--retry-clean-observation",
        '"gh_edit"',
        "'gh_edit'",
        "gh_update_script",
    )
    for fragment in forbidden_import_or_call_fragments:
        assert fragment not in source


def test_affine_source_routing_artifact_uses_canonical_route_ids():
    artifact = PROBE._affine_scalar_source_routing_artifact()
    route_ids = [item["route_id"] for item in artifact["routes"][0]["visible_sources"]]

    assert route_ids == [
        "affine_scalar_expected_output",
        "affine_scalar_factor_value",
        "affine_scalar_offset_value",
        "affine_scalar_projection",
        "affine_scalar_current_output",
        "affine_scalar_current_editable_value",
        "affine_scalar_editable_target_contract",
        "affine_scalar_set_value_convention",
    ]
```

- [ ] **Step 2: Run initial LM8H script tests to verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8h_affine_scalar_depth_probe.py -q
```

Expected: missing script import failure.

- [ ] **Step 3: Create LM8H script skeleton**

Create `scripts/lm8h_affine_scalar_depth_probe.py` by copying the structural pattern from `scripts/lm8f_scalar_transform_depth_probe.py`, then replacing identity constants:

```python
SCRIPT_SCHEMA = "rook.lm8h_affine_scalar_depth_probe:v1"
DECISION_SCHEMA = "rook.lm8h_decision:v1"
INITIAL_EDITABLE_VALUE = 2.0
FACTOR_VALUE = 2.0
OFFSET_VALUE = 1.5
INITIAL_OBSERVED_OUTPUT = 5.5
EXPECTED_OUTPUT_VALUE = 7.5
SCALAR_TOLERANCE = 1e-9
WORKER_NODE_ID = "set_scalar_value"
CREATE_NODE_ID = "create_affine_scalar_transform"
VERIFY_NODE_ID = "verify_affine_scalar_transform_output"
ACTION_ID = "draft_gh_set_value_params"
```

Imports must use affine modules:

```python
from rook.agent.gh_affine_scalar_transform_expectation_acceptance_criteria import (
    assemble_gh_affine_scalar_transform_expectation_packet,
    project_gh_affine_scalar_transform_expectation_legacy,
)
from rook.agent.gh_affine_scalar_transform_expectation_sources import (
    AFFINE_CONVENTION_SOURCE_PATH,
    AFFINE_EDITABLE_VALUE_SOURCE_PATH,
    AFFINE_EXPECTED_OUTPUT_SOURCE_PATH,
    AFFINE_FACTOR_VALUE_SOURCE_PATH,
    AFFINE_FIXTURE_ANCHOR_SOURCE_PATH,
    AFFINE_OBSERVED_OUTPUT_SOURCE_PATH,
    AFFINE_OFFSET_VALUE_SOURCE_PATH,
    AFFINE_PROJECTION_SOURCE_PATH,
    EXPECTED_AFFINE_PROJECTION,
    extract_gh_affine_scalar_transform_expectation_sources,
)
```

The script should own local helper implementations rather than importing LM8F.

- [ ] **Step 4: Implement manifest and source routing artifact**

In `scripts/lm8h_affine_scalar_depth_probe.py`, implement:

```python
def _affine_scalar_source_routing_artifact() -> dict[str, Any]:
    return {
        "schema": "rook.worker_visible_source_routing:v1",
        "routes": [
            {
                "node_id": WORKER_NODE_ID,
                "visible_sources": [
                    {
                        "route_id": "affine_scalar_expected_output",
                        "source_class": "expected_output_contract",
                        "source_path": AFFINE_EXPECTED_OUTPUT_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_factor_value",
                        "source_class": "expected_output_contract",
                        "source_path": AFFINE_FACTOR_VALUE_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_offset_value",
                        "source_class": "expected_output_contract",
                        "source_path": AFFINE_OFFSET_VALUE_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_projection",
                        "source_class": "expected_output_contract",
                        "source_path": AFFINE_PROJECTION_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_current_output",
                        "source_class": "receipt_observation",
                        "source_path": AFFINE_OBSERVED_OUTPUT_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_current_editable_value",
                        "source_class": "receipt_observation",
                        "source_path": AFFINE_EDITABLE_VALUE_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_editable_target_contract",
                        "source_class": "fixture_anchor",
                        "source_path": AFFINE_FIXTURE_ANCHOR_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_set_value_convention",
                        "source_class": "convention",
                        "source_path": AFFINE_CONVENTION_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": False,
                    },
                ],
            }
        ],
    }
```

Implement `_affine_scalar_contract_payload()`:

```python
def _affine_scalar_contract_payload() -> dict[str, Any]:
    return {
        "rules": {
            VERIFY_NODE_ID: {
                "expected_output_value": EXPECTED_OUTPUT_VALUE,
                "factor_value": FACTOR_VALUE,
                "offset_value": OFFSET_VALUE,
                "projection": dict(EXPECTED_AFFINE_PROJECTION),
            }
        }
    }
```

- [ ] **Step 5: Add fake-tool fixture tests**

Append fake executor and fixture helpers to `test_lm8h_affine_scalar_depth_probe.py`:

```python
class FakeToolExecutor:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []

    async def __call__(self, tool_name, args):
        self.calls.append((tool_name, dict(args)))
        value = self.responses[tool_name]
        if isinstance(value, list):
            value = value.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def _library_result_for(name, guid, *, deprecated=False):
    return {
        "name": name,
        "nickName": "A*B" if name == "Multiplication" else "A+B",
        "category": "Maths",
        "guid": guid,
        "deprecated": deprecated,
    }


def _fixture_tool_responses(
    *,
    editable_value="2.0",
    factor_value="2.0",
    offset_value="1.5",
    observed_output="5.5",
):
    return {
        "gh_library": [
            {
                "success": True,
                "count": 1,
                "components": [_library_result_for("Multiplication", "MULTIPLY-PROXY-GUID")],
            },
            {
                "success": True,
                "count": 1,
                "components": [_library_result_for("Addition", "ADDITION-PROXY-GUID")],
            },
        ],
        "gh_create_slider": [
            {"success": True, "data": {"Created": True, "Guid": "EDITABLE-GUID-1", "NickName": "LM8H_Editable"}},
            {"success": True, "data": {"Created": True, "Guid": "FACTOR-GUID-1", "NickName": "LM8H_Factor"}},
            {"success": True, "data": {"Created": True, "Guid": "OFFSET-GUID-1", "NickName": "LM8H_Offset"}},
        ],
        "gh_create_component": [
            {"success": True, "data": {"Created": True, "Guid": "MULTIPLY-GUID-1", "NickName": "A*B"}},
            {"success": True, "data": {"Created": True, "Guid": "ADDITION-GUID-1", "NickName": "A+B"}},
        ],
        "gh_connect": [
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
        ],
        "gh_solve": {"success": True, "data": {"scheduled": True}},
        "gh_get_value": [
            {"success": True, "data": {"Guid": "EDITABLE-GUID-1", "Value": editable_value}},
            {"success": True, "data": {"Guid": "FACTOR-GUID-1", "Value": factor_value}},
            {"success": True, "data": {"Guid": "OFFSET-GUID-1", "Value": offset_value}},
        ],
        "gh_inspect_output": {
            "success": True,
            "data": {"param_nickname": "R", "structure": "single", "data_count": 1, "preview": [observed_output]},
        },
    }
```

Add direct fixture test:

```python
def test_create_affine_fixture_uses_direct_tools_and_hashes_worker_hidden_guid():
    executor = FakeToolExecutor(_fixture_tool_responses())

    fixture = _run(PROBE._create_affine_fixture(executor))

    assert executor.calls == [
        ("gh_library", {"search": "multiplication", "limit": 20}),
        ("gh_library", {"search": "addition", "limit": 20}),
        ("gh_create_slider", {"nickname": "LM8H_Editable", "min": 0, "max": 10, "value": 2.0, "x": 20, "y": 80}),
        ("gh_create_slider", {"nickname": "LM8H_Factor", "min": 0, "max": 10, "value": 2.0, "x": 20, "y": 180}),
        ("gh_create_slider", {"nickname": "LM8H_Offset", "min": 0, "max": 10, "value": 1.5, "x": 20, "y": 280}),
        ("gh_create_component", {"guid": "MULTIPLY-PROXY-GUID", "x": 280, "y": 130}),
        ("gh_create_component", {"guid": "ADDITION-PROXY-GUID", "x": 520, "y": 180}),
        ("gh_connect", {"sourceGuid": "EDITABLE-GUID-1", "targetGuid": "MULTIPLY-GUID-1", "targetParam": "A"}),
        ("gh_connect", {"sourceGuid": "FACTOR-GUID-1", "targetGuid": "MULTIPLY-GUID-1", "targetParam": "B"}),
        ("gh_connect", {"sourceGuid": "MULTIPLY-GUID-1", "sourceParam": "R", "targetGuid": "ADDITION-GUID-1", "targetParam": "A"}),
        ("gh_connect", {"sourceGuid": "OFFSET-GUID-1", "targetGuid": "ADDITION-GUID-1", "targetParam": "B"}),
        ("gh_solve", {"delay": 25}),
        ("gh_get_value", {"guid": "EDITABLE-GUID-1"}),
        ("gh_get_value", {"guid": "FACTOR-GUID-1"}),
        ("gh_get_value", {"guid": "OFFSET-GUID-1"}),
        ("gh_inspect_output", {"guid": "ADDITION-GUID-1", "param": "R"}),
    ]
    assert fixture["editable_component_guid"] == "EDITABLE-GUID-1"
    assert fixture["factor_component_guid"] == "FACTOR-GUID-1"
    assert fixture["offset_component_guid"] == "OFFSET-GUID-1"
    assert fixture["multiplication_component_guid"] == "MULTIPLY-GUID-1"
    assert fixture["addition_component_guid"] == "ADDITION-GUID-1"
    assert fixture["editable_value"] == 2.0
    assert fixture["factor_value"] == 2.0
    assert fixture["offset_value"] == 1.5
    assert fixture["observed_output_value"] == 5.5
    rendered_visible = json.dumps(fixture["visible_receipt"], sort_keys=True)
    for raw_guid in ("EDITABLE-GUID-1", "FACTOR-GUID-1", "OFFSET-GUID-1", "MULTIPLY-GUID-1", "ADDITION-GUID-1"):
        assert raw_guid not in rendered_visible
```

Add deprecated-first Multiplication regression:

```python
def test_create_affine_fixture_rejects_deprecated_first_multiplication_without_active_exact_match():
    responses = _fixture_tool_responses()
    responses["gh_library"][0] = {
        "success": True,
        "count": 1,
        "components": [_library_result_for("Multiplication", "DEPRECATED-MUL-GUID", deprecated=True)],
    }
    executor = FakeToolExecutor(responses)

    with pytest.raises(PROBE.FixtureSetupFailure) as exc:
        _run(PROBE._create_affine_fixture(executor))

    assert exc.value.step == "gh_library_multiplication"
    assert exc.value.failure_reason == "active_multiplication_component_missing"
```

Add deprecated-first plus active-exact Multiplication regression:

```python
def test_create_affine_fixture_selects_active_multiplication_after_deprecated_alias():
    responses = _fixture_tool_responses()
    responses["gh_library"][0] = {
        "success": True,
        "count": 2,
        "components": [
            _library_result_for("Multiplication", "DEPRECATED-MUL-GUID", deprecated=True),
            _library_result_for("Multiplication", "ACTIVE-MUL-PROXY-GUID"),
        ],
    }
    executor = FakeToolExecutor(responses)

    fixture = _run(PROBE._create_affine_fixture(executor))

    assert fixture["multiplication_component_guid"] == "MULTIPLY-GUID-1"
    assert ("gh_create_component", {"guid": "ACTIVE-MUL-PROXY-GUID", "x": 280, "y": 130}) in executor.calls
```

Add initial invariant rejections:

```python
@pytest.mark.parametrize(
    ("responses", "expected_reason"),
    [
        (_fixture_tool_responses(editable_value="2.25"), "initial_editable_value_mismatch"),
        (_fixture_tool_responses(factor_value="2.25"), "factor_value_mismatch"),
        (_fixture_tool_responses(offset_value="1.25"), "offset_value_mismatch"),
        (_fixture_tool_responses(observed_output="5.25"), "initial_observed_output_mismatch"),
    ],
)
def test_create_affine_fixture_rejects_noncanonical_initial_state(responses, expected_reason):
    with pytest.raises(ValueError, match=expected_reason):
        _run(PROBE._create_affine_fixture(FakeToolExecutor(responses)))
```

- [ ] **Step 6: Implement active component selection and fixture creation**

Implement `_active_component_proxy_guid_from_library(result, component_name)` in LM8H. It must scan past deprecated aliases, select an exact active component by name, and use only explicit top-level component proxy GUID fields as component authority:

```python
def _component_proxy_guid(component: Mapping[str, Any]) -> str:
    for key in ("guid", "Guid", "proxyGuid", "ProxyGuid"):
        value = component.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError("tool_result_guid_missing")


def _active_component_proxy_guid_from_library(result: Any, component_name: str) -> str:
    components = _library_components(result)
    active_exact = [
        component
        for component in components
        if str(component.get("name", "")).casefold() == component_name.casefold()
        and component.get("deprecated") is not True
    ]
    if not active_exact:
        raise ValueError(f"active_{component_name.casefold()}_component_missing")
    return _component_proxy_guid(active_exact[0])
```

Implement `_create_affine_fixture(...)` with the exact tool sequence asserted in the test. Use `_fixture_tool_call(...)` and `FixtureSetupFailure` like LM8F. For lookup failures, raise:

```python
FixtureSetupFailure(
    step="gh_library_multiplication",
    tool_name="gh_library",
    failure_reason="active_multiplication_component_missing",
    result=multiplication_library_result,
)
```

and for Addition:

```python
FixtureSetupFailure(
    step="gh_library_addition",
    tool_name="gh_library",
    failure_reason="active_addition_component_missing",
    result=addition_library_result,
)
```

The fixture receipt should be:

```python
receipt = {
    "editable_value": editable_value,
    "observed_output_value": observed_output_value,
    "scalar_anchor": {
        "internal_component_guid": editable_guid,
        "editable_value_contract": {
            "label": "LM8H_Editable",
            "value_type": "number",
            "current_value": editable_value,
            "projection_id": "editable_times_factor_plus_offset",
        },
    },
}
```

The visible receipt must omit every raw GUID and may include only GUID presence/hash fields.

- [ ] **Step 7: Implement scalar runtime readiness**

Implement `_graph_from_affine_receipt(receipt)` using node id `create_affine_scalar_transform`.

Implement `_affine_projection_invariant_holds(sources)`:

```python
expected_observed = (
    float(sources.editable_observation.value)
    * float(sources.factor_contract.value)
    + float(sources.offset_contract.value)
)
return abs(float(sources.observed_output.value) - expected_observed) <= SCALAR_TOLERANCE
```

Implement `_affine_runtime_context(...)`:

```python
def _affine_runtime_context(*, graph, workflow_contract_payload, convention_packets):
    routing_artifact = _affine_scalar_source_routing_artifact()
    static_report = validate_worker_visible_source_routing(routing_artifact)
    sources = extract_gh_affine_scalar_transform_expectation_sources(
        workflow_contract_payload=workflow_contract_payload,
        graph=graph,
        convention_packets=convention_packets,
    )
    if not _affine_projection_invariant_holds(sources):
        raise ValueError("projection_invariant_mismatch")
    packet = assemble_gh_affine_scalar_transform_expectation_packet(sources)
    worker_visible = project_gh_affine_scalar_transform_expectation_legacy(packet)
    return {
        "routing_artifact": routing_artifact,
        "static_routing_report": _routing_report_json(static_report),
        "scalar_runtime_ready": static_report.valid,
        "sources": sources,
        "packet": packet,
        "worker_visible": worker_visible,
    }
```

- [ ] **Step 8: Run Task 3 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8h_affine_scalar_depth_probe.py `
  mcp_server\tests\test_gh_affine_scalar_transform_expectation_sources.py `
  mcp_server\tests\test_gh_affine_scalar_transform_expectation_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q
```

Expected: pass.

- [ ] **Step 9: Commit Task 3**

```powershell
git add scripts\lm8h_affine_scalar_depth_probe.py mcp_server\tests\test_lm8h_affine_scalar_depth_probe.py
git commit -m "feat(lm8h): create affine scalar live probe fixture"
```

---

### Task 4: Worker Publication, Action Apply, Dispatch, And Artifact Policy

**Files:**
- Modify: `scripts/lm8h_affine_scalar_depth_probe.py`
- Modify: `mcp_server/tests/test_lm8h_affine_scalar_depth_probe.py`

**Interfaces:**
- Consumes Task 3:
  - `_create_affine_fixture`
  - `_affine_runtime_context`
- Consumes existing helpers:
  - `run_two_pass_worker_publication`
  - `build_local_worker_turn_context`
  - `render_local_worker_turn_request_payload`
  - `apply_gh_scalar_value_action_to_node`
- Produces complete `_run_probe(...) -> Path`.

- [ ] **Step 1: Add publication/dispatch tests**

In `mcp_server/tests/test_lm8h_affine_scalar_depth_probe.py`, add fake publication and end-to-end fake run helpers:

```python
class FakePublication:
    def __init__(self, row, response_payload=None):
        self.row = row
        self.response_payload = response_payload


def _published_action(value=3.0):
    return FakePublication(
        row={
            "status": "published",
            "pass2_response_kind": "action_request",
            "observation_action_intent_anomaly": False,
        },
        response_payload={
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "action_request",
            "action_id": "draft_gh_set_value_params",
            "rationale": "Use the affine relationship to match the expected output.",
            "input": {"value": value},
        },
    )


def _fixture_responses_for_success():
    responses = _fixture_tool_responses()
    responses.update(
        {
            "rhino_ping": "pong",
            "gh_document_new": {"success": True, "data": {"Created": True}},
            "gh_solve": [
                {"success": True, "data": {"scheduled": True}},
                {"success": True, "data": {"scheduled": True}},
            ],
            "gh_inspect_output": [
                {"success": True, "data": {"data_count": 1, "preview": ["5.5"]}},
                {"success": True, "data": {"data_count": 1, "preview": ["7.5"]}},
            ],
            "gh_set_value": {"success": True, "data": {"Guid": "EDITABLE-GUID-1"}},
        }
    )
    return responses
```

Add accepted run test:

```python
def test_run_probe_accepts_worker_value_that_matches_affine_output(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *args, **kwargs: _published_action(3.0),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    request = json.loads((run_dir / "worker_request_payload.json").read_text(encoding="utf-8"))
    worker_action = json.loads((run_dir / "worker_action.json").read_text(encoding="utf-8"))
    live_set = json.loads((run_dir / "live_set_value_summary.json").read_text(encoding="utf-8"))
    verify = json.loads((run_dir / "verify_scalar_output_summary.json").read_text(encoding="utf-8"))

    assert decision["decision"] == "accepted"
    assert decision["reason"] == "verify_scalar_output_succeeded"
    assert decision["scalar_runtime_ready"] is True
    assert decision["worker_publication_ran"] is True
    assert decision["live_set_value_dispatched"] is True
    assert decision["verify_scalar_output_ran"] is True
    assert worker_action["input"] == {"value": 3.0}
    assert live_set["worker_action_value"] == 3.0
    assert verify["observed_output_value"] == 7.5
    assert "3.0" not in json.dumps(request, sort_keys=True)
    assert "3.0" in json.dumps(worker_action, sort_keys=True)
```

Add pre-publication derived-value policy test:

```python
def test_run_probe_prepublication_artifacts_do_not_contain_hidden_derived_value(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *args, **kwargs: _published_action(3.0),
    )

    forbidden_pre_publication = [
        "scalar_sources.json",
        "acceptance_criteria_packet.json",
        "worker_visible_acceptance_criteria.json",
        "worker_request_payload.json",
    ]
    for filename in forbidden_pre_publication:
        rendered = (run_dir / filename).read_text(encoding="utf-8")
        assert "3.0" not in rendered

    allowed_post_publication = [
        "worker_action.json",
        "live_set_value_summary.json",
        "decision.json",
    ]
    assert any("3.0" in (run_dir / filename).read_text(encoding="utf-8") for filename in allowed_post_publication)
```

Add GUID policy test:

```python
def test_run_probe_artifacts_keep_raw_guid_out_of_source_request_decision_and_verifier(tmp_path):
    executor = FakeToolExecutor(_fixture_responses_for_success())

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *args, **kwargs: _published_action(3.0),
    )

    forbidden_guid_files = [
        "scalar_sources.json",
        "acceptance_criteria_packet.json",
        "worker_visible_acceptance_criteria.json",
        "worker_request_payload.json",
        "verify_scalar_output_summary.json",
        "decision.json",
    ]
    for filename in forbidden_guid_files:
        rendered = (run_dir / filename).read_text(encoding="utf-8")
        for raw_guid in ("EDITABLE-GUID-1", "FACTOR-GUID-1", "OFFSET-GUID-1", "MULTIPLY-GUID-1", "ADDITION-GUID-1"):
            assert raw_guid not in rendered

    assert "EDITABLE-GUID-1" in (run_dir / "fixture_setup_summary.json").read_text(encoding="utf-8")
    assert "EDITABLE-GUID-1" in (run_dir / "live_set_value_summary.json").read_text(encoding="utf-8")
```

Add mismatch rejection test:

```python
def test_run_probe_rejects_worker_value_that_does_not_match_affine_output(tmp_path):
    responses = _fixture_responses_for_success()
    responses["gh_inspect_output"] = [
        {"success": True, "data": {"data_count": 1, "preview": ["5.5"]}},
        {"success": True, "data": {"data_count": 1, "preview": ["9.5"]}},
        {"success": True, "data": {"data_count": 1, "preview": ["9.5"]}},
        {"success": True, "data": {"data_count": 1, "preview": ["9.5"]}},
    ]
    executor = FakeToolExecutor(responses)

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *args, **kwargs: _published_action(4.0),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "rejected"
    assert decision["reason"] == "verify_scalar_output_failed"
    assert decision["observed_output_after"] == 9.5
```

- [ ] **Step 2: Run tests to verify they fail on incomplete `_run_probe`**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8h_affine_scalar_depth_probe.py -q
```

Expected: failures for missing `_run_probe` or incomplete artifact writes.

- [ ] **Step 3: Implement worker request payload**

Implement `_build_local_turn_payload(...)` in LM8H:

```python
def _build_local_turn_payload(*, graph: PlanGraph, packet: Mapping[str, Any], worker_visible: Mapping[str, Any]) -> dict[str, Any]:
    knowledge = WorkerKnowledgePacket(
        packet_id="gh_affine_scalar_transform_evidence",
        kind="evidence",
        title="GH affine scalar transform evidence",
        content={
            "current_editable_value": packet["fields"]["current_editable_value"],
            "factor_value": packet["fields"]["factor_value"],
            "offset_value": packet["fields"]["offset_value"],
            "current_observed_output": packet["fields"]["current_observed_output"],
            "expected_output_value": packet["fields"]["expected_output_value"],
            "projection": packet["fields"]["projection"],
            "editable_value_contract": packet["fields"]["editable_value_contract"],
            "recommended_action_id": packet["fields"]["recommended_action_id"],
            "action_selection_contract": packet["fields"]["action_selection_contract"],
            "acceptance_criteria": worker_visible,
        },
    )
    allowed_action = WorkerAllowedAction(
        action_id=ACTION_ID,
        description="Draft parameters for setting the trusted editable GH scalar value.",
        input_schema={
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "number"}},
            "additionalProperties": False,
        },
    )
    context = build_local_worker_turn_context(
        graph=graph,
        worker_node_id=WORKER_NODE_ID,
        knowledge_packets=(knowledge,),
        allowed_actions=(allowed_action,),
    )
    return render_local_worker_turn_request_payload(context)
```

- [ ] **Step 4: Implement dispatch/verifier helper**

Adapt LM8F `_dispatch_set_value_solve_and_verify(...)` with unchanged semantics:

- call `gh_set_value` on editable slider GUID
- call `gh_solve`
- poll `gh_inspect_output` on final Addition GUID param `R`
- accept iff observed output matches `7.5` within `1e-9`
- keep `gh_set_value` success diagnostic only
- keep verifier summary GUID hash-only

Function signature:

```python
async def _dispatch_set_value_solve_and_verify(
    *,
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]],
    editable_component_guid: str,
    addition_component_guid: str,
    worker_value: float | int,
    expected_value: float | int,
) -> dict[str, Any]:
```

- [ ] **Step 5: Implement `_run_probe` complete flow**

Implement `_run_probe(...)` using LM8F order, with LM8H names:

```text
manifest
preflight
affine fixture
fixture_setup_summary
affine contract payload
affine runtime context
source routing/static validation/scalar sources/packet/worker visible/request artifacts
one worker publication
hidden marker + raw GUID publication guards
worker decision handling
worker_action artifact
scalar applier
gh_set_value + solve + verifier settle
decision.json
```

Publication guard must scan for:

```python
forbidden = (
    "PROBE_REPAIR_CODE",
    "A = 42.0",
    "BindStepSpec.base_params",
    "repair_same_component.bind.base_params",
)
```

Raw GUID publication guard must check all fixture GUIDs:

```python
component_guids = (
    editable_component_guid,
    factor_component_guid,
    offset_component_guid,
    multiplication_component_guid,
    addition_component_guid,
)
```

The derived `3.0` guard is test-based for pre-publication artifacts. Do not block `3.0` in `worker_action.json`, live set summaries, verifier summaries, or bounded decision fields.

- [ ] **Step 6: Run Task 4 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8h_affine_scalar_depth_probe.py -q
```

Expected: pass.

- [ ] **Step 7: Commit Task 4**

```powershell
git add scripts\lm8h_affine_scalar_depth_probe.py mcp_server\tests\test_lm8h_affine_scalar_depth_probe.py
git commit -m "feat(lm8h): run affine scalar worker splice"
```

---

### Task 5: Final Gates, Nearby Tests, And Drift Checks

**Files:**
- Modify: `docs/superpowers/plans/2026-07-09-lm8h-affine-scalar-depth-pressure.md` only if implementation discoveries require plan correction.

**Interfaces:**
- Consumes all previous tasks.
- Produces a branch ready for PR review.

- [ ] **Step 1: Add final source guard tests if not already present**

Ensure `mcp_server/tests/test_lm8h_affine_scalar_depth_probe.py` contains:

```python
def test_lm8h_source_contains_hidden_expected_value_only_as_policy_or_test_oracle():
    source = inspect.getsource(PROBE)
    assert "3.0" not in source
    assert "EXPECTED_WORKER_VALUE" not in source
    assert "set editable value to 3.0" not in source
    assert "use 3.0" not in source


def test_lm8h_source_policy_markers_are_not_worker_visible_evidence():
    source = inspect.getsource(PROBE)
    for marker in (
        "PROBE_REPAIR_CODE",
        "A = 42.0",
        "BindStepSpec.base_params",
        "repair_same_component.bind.base_params",
    ):
        assert marker in source
```

The first test blocks any raw derived-answer leakage in the LM8H script. The `3.0` value is allowed only in tests and in post-worker-authored runtime artifacts after a live run; the script must not contain a constant, prompt hint, or request hint for it. The second test allows hidden-marker policy strings as policy data.

- [ ] **Step 2: Run focused LM8H gate**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_gh_affine_scalar_transform_expectation_sources.py `
  mcp_server\tests\test_gh_affine_scalar_transform_expectation_acceptance_criteria.py `
  mcp_server\tests\test_lm8h_affine_scalar_depth_probe.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q
```

Expected: all tests pass.

- [ ] **Step 3: Run nearby scalar/worker gate**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py `
  mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py `
  mcp_server\tests\test_plan_graph_gh_scalar_value_apply.py `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  -q
```

Expected: all tests pass.

- [ ] **Step 4: Compile changed Python files**

Run:

```powershell
py -3.10 -m py_compile `
  scripts\lm8h_affine_scalar_depth_probe.py `
  mcp_server\src\rook\agent\gh_affine_scalar_transform_expectation_sources.py `
  mcp_server\src\rook\agent\gh_affine_scalar_transform_expectation_acceptance_criteria.py `
  mcp_server\tests\test_lm8h_affine_scalar_depth_probe.py `
  mcp_server\tests\test_gh_affine_scalar_transform_expectation_sources.py `
  mcp_server\tests\test_gh_affine_scalar_transform_expectation_acceptance_criteria.py
```

Expected: exit code 0.

- [ ] **Step 5: Run forbidden drift scan**

Run:

```powershell
$files = @(
  "scripts\lm8h_affine_scalar_depth_probe.py",
  "mcp_server\src\rook\agent\gh_affine_scalar_transform_expectation_sources.py",
  "mcp_server\src\rook\agent\gh_affine_scalar_transform_expectation_acceptance_criteria.py"
)
foreach ($file in $files) {
  Select-String -Path $file -Pattern "lm6a_live_worker_splice_probe|lm7e_model_authored_live_splice_probe|planner_worker_contract_request|workflow_validate|gh_update_script|`"gh_edit`"|'gh_edit'|EXPECTED_WORKER_VALUE|set editable value to 3\.0|use 3\.0" -CaseSensitive
}
```

Expected: no matches, except no output. Hidden repair marker strings are allowed only in LM8H script marker-policy data and should not be included in this guard.

- [ ] **Step 6: Run diff checks**

Run:

```powershell
git diff --check origin/main..HEAD
git diff --name-only origin/main..HEAD
```

Expected tracked scope:

```text
docs/superpowers/specs/2026-07-09-lm8h-affine-scalar-depth-pressure-design.md
docs/superpowers/plans/2026-07-09-lm8h-affine-scalar-depth-pressure.md
mcp_server/src/rook/agent/gh_affine_scalar_transform_expectation_sources.py
mcp_server/src/rook/agent/gh_affine_scalar_transform_expectation_acceptance_criteria.py
mcp_server/src/rook/agent/local_worker_source_routing_validator.py
mcp_server/tests/test_gh_affine_scalar_transform_expectation_sources.py
mcp_server/tests/test_gh_affine_scalar_transform_expectation_acceptance_criteria.py
mcp_server/tests/test_lm8h_affine_scalar_depth_probe.py
mcp_server/tests/test_local_worker_source_routing_validator.py
scripts/lm8h_affine_scalar_depth_probe.py
```

No `probe_runs/`, live telemetry files, or unrelated local dirt should be staged.

- [ ] **Step 7: Commit final verification updates if needed**

If Task 5 required any small test/plan edits, commit them:

```powershell
git add docs\superpowers\plans\2026-07-09-lm8h-affine-scalar-depth-pressure.md mcp_server\tests\test_lm8h_affine_scalar_depth_probe.py
git commit -m "test(lm8h): pin affine scalar drift guards"
```

If no files changed, do not create an empty commit.

---

## Post-Merge Live Runbook

Do not run this in the implementation PR.

After merge and synced `main`, with Rhino and Grasshopper open:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm8h_affine_scalar_depth_probe.py
```

Expected clean success shape:

```text
decision: accepted
reason: verify_scalar_output_succeeded
worker action: draft_gh_set_value_params {"value": 3.0}
final Addition R: 7.5
```

Any terminal outcome is evidence. Do not replace the attempt.
