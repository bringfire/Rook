# LM8F Scalar Transform Depth Pressure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first deterministic live GH-native scalar transform pressure probe, where the worker must choose an editable scalar value from source-owned relationship evidence while topology remains script-owned.

**Architecture:** LM8F is a sibling probe, not an LM8C mode. It adds transform-specific source extraction and acceptance-packet assembly, extends static scalar source-routing allowlists for bounded transform paths, then runs a direct-tool live fixture through the existing two-pass worker publication helper and scalar value applier. The worker sees no GUIDs, no topology authority, no derived target value, and may publish only `draft_gh_set_value_params {"value": number}`.

**Tech Stack:** Python 3.10, pytest, existing Rook MCP tool executor, existing `run_two_pass_worker_publication(...)`, existing `apply_gh_scalar_value_action_to_node(...)`, direct Ollama `/api/chat` for post-merge canonical evidence.

## Global Constraints

- No live Rhino/GH run in the implementation PR.
- No Planner model, no Planner request, and no model-authored template selection.
- No retry, no N=5, no model panel, and no worker prompt/protocol change outside the LM8F scalar evidence packet.
- No `gh_edit`; if direct tools cannot build the transform fixture, LM8F records gate/tooling evidence.
- Canonical worker model is `gemma4:12b-it-qat` through direct Ollama.
- Canonical fixture values are editable `2.0`, offset `1.5`, current observed output `3.5`, expected observed output `7.5`.
- Hidden derived editable value `6.0` is allowed only in deterministic tests and interpretation, never in worker-visible criteria, prompt text, request payload, or scalar source artifacts.
- Topology is script-owned: the worker must not author component ids, wires, tool names, code, GUIDs, or batch edits.
- Trusted editable slider GUID comes only from the live fixture anchor and scalar applier.
- Verifier floor is `gh_inspect_output` on Addition output `R`, not `gh_get_value`.
- `gh_get_value` is allowed only for editable-slider precheck.
- Scalar runtime readiness is static routing valid plus live fixture/receipt construction plus transform source extraction plus transform packet assembly.

---

## File Structure

Create:

- `mcp_server/src/rook/agent/gh_scalar_transform_expectation_sources.py`
  - Transform-specific source paths, source dataclasses, and extractor.
  - Reads source-owned task facts from a script-local workflow contract payload.
  - Reads observed output, editable precheck value, and GUID-free editable target contract from a live fixture receipt.

- `mcp_server/src/rook/agent/gh_scalar_transform_expectation_acceptance_criteria.py`
  - Transform acceptance packet assembler, legacy projection helper, and scalar action-selection contract.
  - Keeps `6.0`, raw GUIDs, repair markers, and full routing metadata out of worker-visible projection.

- `scripts/lm8f_scalar_transform_depth_probe.py`
  - Sibling live probe script.
  - Owns direct GH fixture setup, scalar runtime readiness, worker request rendering, publication decision mapping, scalar applier call, `gh_set_value`, `gh_solve`, `gh_inspect_output` verifier, artifacts, and decisions.

- `mcp_server/tests/test_gh_scalar_transform_expectation_sources.py`
  - Unit tests for transform source extraction and import boundary.

- `mcp_server/tests/test_gh_scalar_transform_expectation_acceptance_criteria.py`
  - Unit tests for packet shape, projection, fingerprint, marker exclusion, and action-selection contract.

- `mcp_server/tests/test_lm8f_scalar_transform_depth_probe.py`
  - Script-level tests with fake tool executor and fake publication runner.

Modify:

- `mcp_server/src/rook/agent/local_worker_source_routing_validator.py`
  - Add exact transform source paths to existing scalar source-class allowlists.
  - Keep `fixture_anchor` evidence-only.

- `mcp_server/tests/test_local_worker_source_routing_validator.py`
  - Add transform route static validation and negative source-class/purpose tests.

Do not modify:

- `scripts/lm8c_gh_scalar_expectation_live_probe.py`
- `scripts/lm_worker_two_pass_publication.py`
- `mcp_server/src/rook/agent/plan_graph_gh_scalar_value_apply.py`
- `mcp_server/src/rook/server.py`
- LM5/LM6/LM7 Planner or repair-family modules

---

### Task 1: Transform Source Routing And Source Extraction

**Files:**
- Create: `mcp_server/src/rook/agent/gh_scalar_transform_expectation_sources.py`
- Create: `mcp_server/tests/test_gh_scalar_transform_expectation_sources.py`
- Modify: `mcp_server/src/rook/agent/local_worker_source_routing_validator.py`
- Modify: `mcp_server/tests/test_local_worker_source_routing_validator.py`

**Interfaces:**
- Produces constants:
  - `TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH`
  - `TRANSFORM_OFFSET_VALUE_SOURCE_PATH`
  - `TRANSFORM_PROJECTION_SOURCE_PATH`
  - `TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH`
  - `TRANSFORM_EDITABLE_VALUE_SOURCE_PATH`
  - `TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH`
  - `TRANSFORM_CONVENTION_SOURCE_PATH`
- Produces dataclasses:
  - `GhScalarTransformExpectationSource(source_class: str, source_path: str, value: Any)`
  - `GhScalarTransformExpectationSources(...)`
- Produces:
  - `extract_gh_scalar_transform_expectation_sources(*, workflow_contract_payload: Mapping[str, Any], graph: PlanGraph, convention_packets: Sequence[WorkerKnowledgePacket]) -> GhScalarTransformExpectationSources`
- Consumes existing:
  - `PlanGraph`, `PlanGraphNode`, `NodeEvidence`
  - `WorkerKnowledgePacket`
  - `validate_worker_visible_source_routing(...)`

- [ ] **Step 1: Add validator tests for exact transform route allowlists**

Add this helper and tests to `mcp_server/tests/test_local_worker_source_routing_validator.py`:

```python
TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_transform_output.expected_output_value"
)
TRANSFORM_OFFSET_VALUE_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_transform_output.offset_value"
)
TRANSFORM_PROJECTION_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_transform_output.projection"
)
TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH = (
    "create_scalar_transform.receipt.gh_receipt.observed_output_value"
)
TRANSFORM_EDITABLE_VALUE_SOURCE_PATH = (
    "create_scalar_transform.receipt.gh_receipt.editable_value"
)
TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH = (
    "create_scalar_transform.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
TRANSFORM_CONVENTION_SOURCE_PATH = "gh_scalar_transform_set_value_convention"


def _gh_scalar_transform_artifact(*, fixture_anchor_purpose="evidence_context"):
    return {
        "schema": SOURCE_ROUTING_SCHEMA,
        "routes": [
            {
                "node_id": "set_scalar_value",
                "visible_sources": [
                    {
                        "route_id": "scalar_transform_expected_output",
                        "source_class": "expected_output_contract",
                        "source_path": TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "scalar_transform_offset_value",
                        "source_class": "expected_output_contract",
                        "source_path": TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "scalar_transform_projection",
                        "source_class": "expected_output_contract",
                        "source_path": TRANSFORM_PROJECTION_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "scalar_transform_current_output",
                        "source_class": "receipt_observation",
                        "source_path": TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "scalar_transform_current_editable_value",
                        "source_class": "receipt_observation",
                        "source_path": TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "scalar_transform_editable_target_contract",
                        "source_class": "fixture_anchor",
                        "source_path": TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH,
                        "purpose": fixture_anchor_purpose,
                        "required": True,
                    },
                    {
                        "route_id": "scalar_transform_set_value_convention",
                        "source_class": "convention",
                        "source_path": TRANSFORM_CONVENTION_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": False,
                    },
                ],
            }
        ],
    }


def test_gh_scalar_transform_routes_are_static_valid():
    report = validate_worker_visible_source_routing(_gh_scalar_transform_artifact())

    assert report.valid is True
    assert report.routability_evaluated is False
    assert report.static_diagnostics == ()
    assert report.routability_diagnostics == ()


def test_gh_scalar_transform_fixture_anchor_cannot_feed_acceptance_criteria():
    report = validate_worker_visible_source_routing(
        _gh_scalar_transform_artifact(fixture_anchor_purpose="acceptance_criteria")
    )

    assert report.valid is False
    assert [
        (diagnostic.code, diagnostic.source_class, diagnostic.purpose)
        for diagnostic in report.static_diagnostics
    ] == [("invalid_source_purpose", "fixture_anchor", "acceptance_criteria")]


def test_gh_scalar_transform_source_paths_are_class_keyed():
    artifact = _gh_scalar_transform_artifact()
    artifact["routes"][0]["visible_sources"][0] = {
        "route_id": "wrong_class_transform_expected_value",
        "source_class": "receipt_observation",
        "source_path": TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
        "purpose": "acceptance_criteria",
        "required": True,
    }

    report = validate_worker_visible_source_routing(artifact)

    assert report.valid is False
    assert [
        diagnostic.code
        for diagnostic in report.static_diagnostics
        if diagnostic.route_id == "wrong_class_transform_expected_value"
    ] == ["invalid_source_path"]
```

- [ ] **Step 2: Run validator test to verify it fails**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_gh_scalar_transform_routes_are_static_valid `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_gh_scalar_transform_fixture_anchor_cannot_feed_acceptance_criteria `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_gh_scalar_transform_source_paths_are_class_keyed `
  -q
```

Expected: at least `test_gh_scalar_transform_routes_are_static_valid` fails with `invalid_source_path`.

- [ ] **Step 3: Extend validator allowlists only for bounded transform paths**

In `mcp_server/src/rook/agent/local_worker_source_routing_validator.py`, add constants near the identity scalar constants:

```python
SCALAR_TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_transform_output.expected_output_value"
)
SCALAR_TRANSFORM_OFFSET_VALUE_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_transform_output.offset_value"
)
SCALAR_TRANSFORM_PROJECTION_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_transform_output.projection"
)
SCALAR_TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH = (
    "create_scalar_transform.receipt.gh_receipt.observed_output_value"
)
SCALAR_TRANSFORM_EDITABLE_VALUE_SOURCE_PATH = (
    "create_scalar_transform.receipt.gh_receipt.editable_value"
)
SCALAR_TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH = (
    "create_scalar_transform.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
SCALAR_TRANSFORM_CONVENTION_SOURCE_PATH = "gh_scalar_transform_set_value_convention"
```

Then extend `_ALLOWED_SOURCE_PATHS`:

```python
"convention": (
    CONVENTION_SOURCE_PATH,
    "grasshopper_definition_style_convention",
    SCALAR_CONVENTION_SOURCE_PATH,
    SCALAR_TRANSFORM_CONVENTION_SOURCE_PATH,
),
"expected_output_contract": (
    SCALAR_EXPECTED_OUTPUT_SOURCE_PATH,
    SCALAR_TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
    SCALAR_TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
    SCALAR_TRANSFORM_PROJECTION_SOURCE_PATH,
),
"receipt_observation": (
    SCALAR_OBSERVED_OUTPUT_SOURCE_PATH,
    SCALAR_TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
    SCALAR_TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
),
"fixture_anchor": (
    SCALAR_FIXTURE_ANCHOR_SOURCE_PATH,
    SCALAR_TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH,
),
```

Do not change `_SOURCE_PURPOSES`; `fixture_anchor` must remain `("evidence_context",)`.

- [ ] **Step 4: Run validator tests to verify they pass**

Run the same command from Step 2.

Expected: all three tests pass.

- [ ] **Step 5: Add transform source extractor tests**

Create `mcp_server/tests/test_gh_scalar_transform_expectation_sources.py`:

```python
import ast
import inspect

import pytest

from rook.agent.gh_scalar_transform_expectation_sources import (
    TRANSFORM_CONVENTION_SOURCE_PATH,
    TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
    TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
    TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH,
    TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
    TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
    TRANSFORM_PROJECTION_SOURCE_PATH,
    extract_gh_scalar_transform_expectation_sources,
)
from rook.agent.local_worker_turn_context import WorkerKnowledgePacket
from rook.learning.plan_graph import GraphMemory, NodeEvidence, PlanGraph, PlanGraphNode


def _projection():
    return {
        "projection_id": "editable_plus_offset",
        "description": "observed_output = editable_value + offset_value",
        "editable_variable": "editable_value",
        "offset_variable": "offset_value",
        "output_variable": "observed_output",
    }


def _contract_payload(expected_value=7.5, offset_value=1.5, projection=None):
    return {
        "rules": {
            "verify_scalar_transform_output": {
                "expected_output_value": expected_value,
                "offset_value": offset_value,
                "projection": projection or _projection(),
            }
        }
    }


def _graph(
    *,
    observed_value=3.5,
    editable_value=2.0,
    editable_contract=None,
    guid="EDITABLE-GUID-1",
):
    editable_contract = editable_contract or {
        "label": "LM8F_Editable",
        "value_type": "number",
        "current_value": editable_value,
        "projection_id": "editable_plus_offset",
    }
    receipt = {
        "observed_output_value": observed_value,
        "editable_value": editable_value,
        "scalar_anchor": {
            "component_guid": guid,
            "editable_value_contract": editable_contract,
        },
    }
    return PlanGraph(
        nodes={
            "create_scalar_transform": PlanGraphNode(
                id="create_scalar_transform",
                intent="create scalar transform fixture",
                evidence=NodeEvidence(
                    tool_status="success",
                    verified=True,
                    receipt=receipt,
                ),
            )
        },
        memory=GraphMemory(),
    )


def _convention_packet():
    return WorkerKnowledgePacket(
        packet_id="gh_scalar_transform_set_value_convention",
        kind="convention",
        title="GH scalar transform values are changed with gh_set_value",
        content={"action_id": "draft_gh_set_value_params"},
    )


def test_extracts_transform_sources_without_guid_in_visible_anchor():
    sources = extract_gh_scalar_transform_expectation_sources(
        workflow_contract_payload=_contract_payload(),
        graph=_graph(),
        convention_packets=(_convention_packet(),),
    )

    assert sources.expected_output_contract.source_class == "expected_output_contract"
    assert sources.expected_output_contract.source_path == TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH
    assert sources.expected_output_contract.value == 7.5
    assert sources.offset_contract.source_class == "expected_output_contract"
    assert sources.offset_contract.source_path == TRANSFORM_OFFSET_VALUE_SOURCE_PATH
    assert sources.offset_contract.value == 1.5
    assert sources.projection_contract.source_class == "expected_output_contract"
    assert sources.projection_contract.source_path == TRANSFORM_PROJECTION_SOURCE_PATH
    assert sources.projection_contract.value == _projection()
    assert sources.observed_output.source_class == "receipt_observation"
    assert sources.observed_output.source_path == TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH
    assert sources.observed_output.value == 3.5
    assert sources.editable_observation.source_class == "receipt_observation"
    assert sources.editable_observation.source_path == TRANSFORM_EDITABLE_VALUE_SOURCE_PATH
    assert sources.editable_observation.value == 2.0
    assert sources.fixture_anchor.source_class == "fixture_anchor"
    assert sources.fixture_anchor.source_path == TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH
    assert sources.fixture_anchor.value == {
        "label": "LM8F_Editable",
        "value_type": "number",
        "current_value": 2.0,
        "projection_id": "editable_plus_offset",
    }
    assert sources.convention is not None
    assert sources.convention.source_path == TRANSFORM_CONVENTION_SOURCE_PATH
    assert "EDITABLE-GUID-1" not in repr(sources.fixture_anchor.value)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "7.5", True])
def test_expected_output_value_must_be_finite_number(bad_value):
    with pytest.raises(ValueError, match=TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH):
        extract_gh_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(expected_value=bad_value),
            graph=_graph(),
            convention_packets=(),
        )


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "1.5", False])
def test_offset_value_must_be_finite_number(bad_value):
    with pytest.raises(ValueError, match=TRANSFORM_OFFSET_VALUE_SOURCE_PATH):
        extract_gh_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(offset_value=bad_value),
            graph=_graph(),
            convention_packets=(),
        )


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "3.5", True])
def test_observed_output_value_must_be_finite_number(bad_value):
    with pytest.raises(ValueError, match=TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH):
        extract_gh_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(),
            graph=_graph(observed_value=bad_value),
            convention_packets=(),
        )


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "2.0", False])
def test_editable_value_must_be_finite_number(bad_value):
    with pytest.raises(ValueError, match=TRANSFORM_EDITABLE_VALUE_SOURCE_PATH):
        extract_gh_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(),
            graph=_graph(editable_value=bad_value),
            convention_packets=(),
        )


def test_projection_must_be_exact_v1_relationship():
    bad_projection = {
        "projection_id": "editable_times_offset",
        "description": "observed_output = editable_value * offset_value",
        "editable_variable": "editable_value",
        "offset_variable": "offset_value",
        "output_variable": "observed_output",
    }

    with pytest.raises(ValueError, match=TRANSFORM_PROJECTION_SOURCE_PATH):
        extract_gh_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(projection=bad_projection),
            graph=_graph(),
            convention_packets=(),
        )


def test_missing_fixture_anchor_contract_fails_closed():
    graph = _graph()
    graph.nodes["create_scalar_transform"].evidence.receipt["scalar_anchor"].pop(
        "editable_value_contract"
    )

    with pytest.raises(ValueError, match=TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH):
        extract_gh_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(),
            graph=graph,
            convention_packets=(),
        )


def test_fixture_anchor_contract_must_not_expose_guid():
    graph = _graph(
        editable_contract={
            "label": "LM8F_Editable",
            "value_type": "number",
            "current_value": 2.0,
            "projection_id": "editable_plus_offset",
            "component_guid": "EDITABLE-GUID-1",
        }
    )

    with pytest.raises(ValueError, match=TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH):
        extract_gh_scalar_transform_expectation_sources(
            workflow_contract_payload=_contract_payload(),
            graph=graph,
            convention_packets=(),
        )


def test_transform_source_import_boundary_stays_narrow():
    import rook.agent.gh_scalar_transform_expectation_sources as module

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
        "scripts.lm8c_gh_scalar_expectation_live_probe",
        "scripts.lm7e_model_authored_live_splice_probe",
        "yaml",
        "LiteLLM",
        "BindStepSpec",
    }
    assert imports.isdisjoint(forbidden)
    assert "base_params" not in source
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "base_params"
        for node in ast.walk(tree)
    )
```

- [ ] **Step 6: Run extractor tests to verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_gh_scalar_transform_expectation_sources.py `
  -q
```

Expected: import failure because the module does not exist.

- [ ] **Step 7: Implement transform source extractor**

Create `mcp_server/src/rook/agent/gh_scalar_transform_expectation_sources.py` with this structure:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

from rook.agent.local_worker_turn_context import WorkerKnowledgePacket
from rook.learning.plan_graph import PlanGraph


TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_transform_output.expected_output_value"
)
TRANSFORM_OFFSET_VALUE_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_transform_output.offset_value"
)
TRANSFORM_PROJECTION_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_transform_output.projection"
)
TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH = (
    "create_scalar_transform.receipt.gh_receipt.observed_output_value"
)
TRANSFORM_EDITABLE_VALUE_SOURCE_PATH = (
    "create_scalar_transform.receipt.gh_receipt.editable_value"
)
TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH = (
    "create_scalar_transform.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
TRANSFORM_CONVENTION_SOURCE_PATH = "gh_scalar_transform_set_value_convention"

EXPECTED_PROJECTION = {
    "projection_id": "editable_plus_offset",
    "description": "observed_output = editable_value + offset_value",
    "editable_variable": "editable_value",
    "offset_variable": "offset_value",
    "output_variable": "observed_output",
}


@dataclass(frozen=True)
class GhScalarTransformExpectationSource:
    source_class: str
    source_path: str
    value: Any


@dataclass(frozen=True)
class GhScalarTransformExpectationSources:
    expected_output_contract: GhScalarTransformExpectationSource
    offset_contract: GhScalarTransformExpectationSource
    projection_contract: GhScalarTransformExpectationSource
    observed_output: GhScalarTransformExpectationSource
    editable_observation: GhScalarTransformExpectationSource
    fixture_anchor: GhScalarTransformExpectationSource
    convention: GhScalarTransformExpectationSource | None = None


def extract_gh_scalar_transform_expectation_sources(
    *,
    workflow_contract_payload: Mapping[str, Any],
    graph: PlanGraph,
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> GhScalarTransformExpectationSources:
    return GhScalarTransformExpectationSources(
        expected_output_contract=GhScalarTransformExpectationSource(
            source_class="expected_output_contract",
            source_path=TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
            value=_expected_output_value(workflow_contract_payload),
        ),
        offset_contract=GhScalarTransformExpectationSource(
            source_class="expected_output_contract",
            source_path=TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
            value=_offset_value(workflow_contract_payload),
        ),
        projection_contract=GhScalarTransformExpectationSource(
            source_class="expected_output_contract",
            source_path=TRANSFORM_PROJECTION_SOURCE_PATH,
            value=_projection(workflow_contract_payload),
        ),
        observed_output=GhScalarTransformExpectationSource(
            source_class="receipt_observation",
            source_path=TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
            value=_observed_output_value(graph),
        ),
        editable_observation=GhScalarTransformExpectationSource(
            source_class="receipt_observation",
            source_path=TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
            value=_editable_value(graph),
        ),
        fixture_anchor=GhScalarTransformExpectationSource(
            source_class="fixture_anchor",
            source_path=TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH,
            value=_editable_value_contract(graph),
        ),
        convention=_convention_source(convention_packets),
    )
```

Add private helpers matching the tests:

```python
def _rule(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    rules = payload.get("rules")
    if not isinstance(rules, Mapping):
        raise ValueError(f"{TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH} rules missing")
    verify = rules.get("verify_scalar_transform_output")
    if not isinstance(verify, Mapping):
        raise ValueError(f"{TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH} rule missing")
    return verify


def _expected_output_value(payload: Mapping[str, Any]) -> float | int:
    return _finite_number(
        _rule(payload).get("expected_output_value"),
        TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
    )


def _offset_value(payload: Mapping[str, Any]) -> float | int:
    return _finite_number(
        _rule(payload).get("offset_value"),
        TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
    )


def _projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    projection = _rule(payload).get("projection")
    if not isinstance(projection, Mapping):
        raise ValueError(f"{TRANSFORM_PROJECTION_SOURCE_PATH} missing")
    copied = dict(projection)
    if copied != EXPECTED_PROJECTION:
        raise ValueError(f"{TRANSFORM_PROJECTION_SOURCE_PATH} invalid")
    return copied


def _receipt(graph: PlanGraph) -> Mapping[str, Any]:
    if "create_scalar_transform" not in graph.nodes:
        raise ValueError(f"{TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH} node missing")
    evidence = graph.nodes["create_scalar_transform"].evidence
    if evidence is None or not isinstance(evidence.receipt, Mapping):
        raise ValueError(f"{TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH} receipt missing")
    return evidence.receipt


def _observed_output_value(graph: PlanGraph) -> float | int:
    return _finite_number(
        _receipt(graph).get("observed_output_value"),
        TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
    )


def _editable_value(graph: PlanGraph) -> float | int:
    return _finite_number(
        _receipt(graph).get("editable_value"),
        TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
    )


def _editable_value_contract(graph: PlanGraph) -> dict[str, Any]:
    receipt = _receipt(graph)
    anchor = receipt.get("scalar_anchor")
    if not isinstance(anchor, Mapping):
        raise ValueError(f"{TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH} scalar_anchor missing")
    contract = anchor.get("editable_value_contract")
    if not isinstance(contract, Mapping):
        raise ValueError(f"{TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH} missing")
    copied = dict(contract)
    if "component_guid" in copied or "guid" in copied:
        raise ValueError(f"{TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH} must not expose guid")
    required = {
        "label",
        "value_type",
        "current_value",
        "projection_id",
    }
    if set(copied) != required:
        raise ValueError(f"{TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH} invalid fields")
    if copied["value_type"] != "number":
        raise ValueError(f"{TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH} value_type invalid")
    _finite_number(copied["current_value"], TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH)
    if copied["projection_id"] != "editable_plus_offset":
        raise ValueError(f"{TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH} projection_id invalid")
    return copied


def _convention_source(
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> GhScalarTransformExpectationSource | None:
    matches = [
        packet
        for packet in convention_packets
        if getattr(packet, "packet_id", None) == TRANSFORM_CONVENTION_SOURCE_PATH
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"{TRANSFORM_CONVENTION_SOURCE_PATH} ambiguous")
    packet = matches[0]
    return GhScalarTransformExpectationSource(
        source_class="convention",
        source_path=TRANSFORM_CONVENTION_SOURCE_PATH,
        value=(
            dict(packet.content)
            if isinstance(packet.content, Mapping)
            else packet.content
        ),
    )


def _finite_number(value: Any, source_path: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{source_path} must be a finite number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{source_path} must be a finite number")
    return value
```

Add `__all__` for every public constant, dataclass, and extractor.

- [ ] **Step 8: Run Task 1 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_gh_scalar_transform_routes_are_static_valid `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_gh_scalar_transform_fixture_anchor_cannot_feed_acceptance_criteria `
  mcp_server\tests\test_local_worker_source_routing_validator.py::test_gh_scalar_transform_source_paths_are_class_keyed `
  mcp_server\tests\test_gh_scalar_transform_expectation_sources.py `
  -q
```

Expected: all pass.

- [ ] **Step 9: Commit Task 1**

```powershell
git add `
  mcp_server\src\rook\agent\local_worker_source_routing_validator.py `
  mcp_server\src\rook\agent\gh_scalar_transform_expectation_sources.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  mcp_server\tests\test_gh_scalar_transform_expectation_sources.py
git commit -m "feat(lm8f): add scalar transform source extraction"
```

---

### Task 2: Transform Acceptance Packet Assembly

**Files:**
- Create: `mcp_server/src/rook/agent/gh_scalar_transform_expectation_acceptance_criteria.py`
- Create: `mcp_server/tests/test_gh_scalar_transform_expectation_acceptance_criteria.py`

**Interfaces:**
- Consumes:
  - `GhScalarTransformExpectationSource`
  - `GhScalarTransformExpectationSources`
  - transform source path constants from Task 1
- Produces:
  - `GH_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA = "rook.gh_scalar_transform_expectation_packet:v1"`
  - `scalar_transform_action_selection_contract() -> dict[str, Any]`
  - `assemble_gh_scalar_transform_expectation_packet(sources: GhScalarTransformExpectationSources) -> dict[str, Any]`
  - `project_gh_scalar_transform_expectation_legacy(packet: dict[str, Any]) -> dict[str, Any]`

- [ ] **Step 1: Write failing packet tests**

Create `mcp_server/tests/test_gh_scalar_transform_expectation_acceptance_criteria.py`:

```python
import ast
import hashlib
import inspect
import json

import pytest

from rook.agent import gh_scalar_transform_expectation_acceptance_criteria as module
from rook.agent.gh_scalar_transform_expectation_acceptance_criteria import (
    GH_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA,
    GhScalarTransformExpectationSource,
    GhScalarTransformExpectationSources,
    assemble_gh_scalar_transform_expectation_packet,
    project_gh_scalar_transform_expectation_legacy,
    scalar_transform_action_selection_contract,
)


EXPECTED_PATH = "workflow_contract.rules.verify_scalar_transform_output.expected_output_value"
OFFSET_PATH = "workflow_contract.rules.verify_scalar_transform_output.offset_value"
PROJECTION_PATH = "workflow_contract.rules.verify_scalar_transform_output.projection"
OBSERVED_PATH = "create_scalar_transform.receipt.gh_receipt.observed_output_value"
EDITABLE_PATH = "create_scalar_transform.receipt.gh_receipt.editable_value"
ANCHOR_PATH = (
    "create_scalar_transform.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
CONVENTION_PATH = "gh_scalar_transform_set_value_convention"


def _projection():
    return {
        "projection_id": "editable_plus_offset",
        "description": "observed_output = editable_value + offset_value",
        "editable_variable": "editable_value",
        "offset_variable": "offset_value",
        "output_variable": "observed_output",
    }


def _valid_sources(**overrides):
    values = {
        "expected_output_contract": GhScalarTransformExpectationSource(
            source_class="expected_output_contract",
            source_path=EXPECTED_PATH,
            value=7.5,
        ),
        "offset_contract": GhScalarTransformExpectationSource(
            source_class="expected_output_contract",
            source_path=OFFSET_PATH,
            value=1.5,
        ),
        "projection_contract": GhScalarTransformExpectationSource(
            source_class="expected_output_contract",
            source_path=PROJECTION_PATH,
            value=_projection(),
        ),
        "observed_output": GhScalarTransformExpectationSource(
            source_class="receipt_observation",
            source_path=OBSERVED_PATH,
            value=3.5,
        ),
        "editable_observation": GhScalarTransformExpectationSource(
            source_class="receipt_observation",
            source_path=EDITABLE_PATH,
            value=2.0,
        ),
        "fixture_anchor": GhScalarTransformExpectationSource(
            source_class="fixture_anchor",
            source_path=ANCHOR_PATH,
            value={
                "label": "LM8F_Editable",
                "value_type": "number",
                "current_value": 2.0,
                "projection_id": "editable_plus_offset",
            },
        ),
        "convention": GhScalarTransformExpectationSource(
            source_class="convention",
            source_path=CONVENTION_PATH,
            value={"action_id": "draft_gh_set_value_params"},
        ),
    }
    values.update(overrides)
    return GhScalarTransformExpectationSources(**values)


def _without_fingerprint(packet):
    copied = dict(packet)
    copied.pop("fingerprint")
    return copied


def test_public_surface():
    assert module.__all__ == (
        "GH_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA",
        "GhScalarTransformExpectationSource",
        "GhScalarTransformExpectationSources",
        "assemble_gh_scalar_transform_expectation_packet",
        "project_gh_scalar_transform_expectation_legacy",
        "scalar_transform_action_selection_contract",
    )
    assert (
        GH_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA
        == "rook.gh_scalar_transform_expectation_packet:v1"
    )


def test_action_selection_contract_preserves_two_pass_shapes():
    contract = scalar_transform_action_selection_contract()

    assert contract["required_action_id"] == "draft_gh_set_value_params"
    assert contract["pass1_decision_required_fields_if_acting"] == [
        "kind",
        "action_id",
    ]
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


def test_assembles_scalar_transform_packet_without_derived_target_value():
    packet = assemble_gh_scalar_transform_expectation_packet(_valid_sources())

    assert packet["schema"] == GH_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA
    assert packet["source_set"] == {
        "source_classes": [
            "convention",
            "expected_output_contract",
            "fixture_anchor",
            "receipt_observation",
        ],
        "source_paths": sorted(
            [
                CONVENTION_PATH,
                ANCHOR_PATH,
                EDITABLE_PATH,
                OBSERVED_PATH,
                OFFSET_PATH,
                PROJECTION_PATH,
                EXPECTED_PATH,
            ]
        ),
    }
    assert packet["fields"]["current_editable_value"] == 2.0
    assert packet["fields"]["offset_value"] == 1.5
    assert packet["fields"]["current_observed_output"] == 3.5
    assert packet["fields"]["expected_output_value"] == 7.5
    assert packet["fields"]["projection"] == _projection()
    assert packet["fields"]["editable_value_contract"] == {
        "label": "LM8F_Editable",
        "value_type": "number",
        "current_value": 2.0,
        "projection_id": "editable_plus_offset",
    }
    assert packet["fields"]["recommended_action_id"] == "draft_gh_set_value_params"
    assert packet["fields"]["action_selection_contract"]["required_action_id"] == (
        "draft_gh_set_value_params"
    )
    assert packet["fields"]["acceptance_criteria"] == {
        "source": "gh_scalar_transform_expectation",
        "criteria": [
            {
                "criterion_id": "match_expected_observed_output",
                "description": "Set the editable scalar value so the inspected GH output equals the source-owned expected output value.",
                "source": EXPECTED_PATH,
            },
            {
                "criterion_id": "use_editable_plus_offset_projection",
                "description": "Use the source-owned scalar projection relationship: observed_output = editable_value + offset_value.",
                "source": PROJECTION_PATH,
            },
        ],
    }
    rendered = json.dumps(packet, sort_keys=True)
    assert "6.0" not in rendered
    assert "set editable value to 6" not in rendered.lower()
    assert "component_guid" not in rendered
    assert "EDITABLE-GUID" not in rendered
    assert "gh_edit" not in rendered
    assert "gh_update_script" not in rendered
    assert "repair_same_component" not in rendered
    assert packet["fingerprint"].startswith("sha256:")


def test_legacy_projection_excludes_schema_source_set_source_class_and_fingerprint():
    packet = assemble_gh_scalar_transform_expectation_packet(_valid_sources())

    projection = project_gh_scalar_transform_expectation_legacy(packet)

    assert projection == packet["fields"]["acceptance_criteria"]
    rendered = json.dumps(projection, sort_keys=True)
    for forbidden in ("schema", "source_set", "source_class", "fingerprint"):
        assert forbidden not in rendered
    assert "6.0" not in rendered


def test_fingerprint_matches_canonical_packet_without_fingerprint():
    packet = assemble_gh_scalar_transform_expectation_packet(_valid_sources())

    expected = hashlib.sha256(
        json.dumps(
            _without_fingerprint(packet),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert packet["fingerprint"] == f"sha256:{expected}"


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "7.5", True])
def test_expected_value_fails_closed_for_non_finite_number(bad_value):
    with pytest.raises(ValueError, match="expected_output_contract"):
        assemble_gh_scalar_transform_expectation_packet(
            _valid_sources(
                expected_output_contract=GhScalarTransformExpectationSource(
                    source_class="expected_output_contract",
                    source_path=EXPECTED_PATH,
                    value=bad_value,
                )
            )
        )


def test_fixture_anchor_cannot_contain_guid_or_feed_criteria():
    with pytest.raises(ValueError, match="fixture_anchor"):
        assemble_gh_scalar_transform_expectation_packet(
            _valid_sources(
                fixture_anchor=GhScalarTransformExpectationSource(
                    source_class="fixture_anchor",
                    source_path=ANCHOR_PATH,
                    value={
                        "label": "LM8F_Editable",
                        "value_type": "number",
                        "current_value": 2.0,
                        "projection_id": "editable_plus_offset",
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
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_gh_scalar_transform_expectation_acceptance_criteria.py `
  -q
```

Expected: import failure because the module does not exist.

- [ ] **Step 3: Implement transform packet assembler**

Create `mcp_server/src/rook/agent/gh_scalar_transform_expectation_acceptance_criteria.py`.

Import transform source dataclasses and constants from Task 1:

```python
from rook.agent.gh_scalar_transform_expectation_sources import (
    EXPECTED_PROJECTION,
    TRANSFORM_CONVENTION_SOURCE_PATH,
    TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
    TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
    TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH,
    TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
    TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
    TRANSFORM_PROJECTION_SOURCE_PATH,
    GhScalarTransformExpectationSource,
    GhScalarTransformExpectationSources,
)
```

Implement `scalar_transform_action_selection_contract()` using the same two-pass distinction as LM8D:

```python
def scalar_transform_action_selection_contract() -> dict[str, Any]:
    return {
        "contract_id": "gh_scalar_transform_action_selection:v1",
        "worker_agency": (
            "If the acceptance criteria are sufficient and action is warranted, "
            "publish action_request with the exact required_action_id. If action "
            "is not warranted, publish a non-action response."
        ),
        "required_response_kind_if_acting": "action_request",
        "required_action_id": "draft_gh_set_value_params",
        "pass1_decision_required_fields_if_acting": ["kind", "action_id"],
        "final_action_request_required_fields": [
            "schema",
            "kind",
            "action_id",
            "rationale",
            "input",
        ],
        "action_input_schema": {
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "number"}},
            "additionalProperties": False,
        },
        "authority_limits": [
            "do not author target GUID",
            "do not call GH tools directly",
            "do not author topology, code, or batch edits",
        ],
    }
```

Implement `assemble_gh_scalar_transform_expectation_packet(...)` with:

```python
GH_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA = (
    "rook.gh_scalar_transform_expectation_packet:v1"
)
```

The packet must include:

```python
packet = {
    "schema": GH_SCALAR_TRANSFORM_EXPECTATION_PACKET_SCHEMA,
    "source_set": {
        "source_classes": sorted(source_classes),
        "source_paths": sorted(source_paths),
    },
    "criteria": criteria,
    "fields": {
        "current_editable_value": sources.editable_observation.value,
        "offset_value": sources.offset_contract.value,
        "current_observed_output": sources.observed_output.value,
        "expected_output_value": sources.expected_output_contract.value,
        "projection": dict(sources.projection_contract.value),
        "editable_value_contract": dict(sources.fixture_anchor.value),
        "recommended_action_id": "draft_gh_set_value_params",
        "action_selection_contract": scalar_transform_action_selection_contract(),
        "acceptance_criteria": acceptance_criteria,
    },
}
```

Compute fingerprint exactly like LM8C packets:

```python
canonical_packet = json.dumps(packet, sort_keys=True, separators=(",", ":"))
packet["fingerprint"] = (
    f"sha256:{hashlib.sha256(canonical_packet.encode('utf-8')).hexdigest()}"
)
```

Implement `project_gh_scalar_transform_expectation_legacy(packet)` by returning only `fields.acceptance_criteria`.

- [ ] **Step 4: Run Task 2 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_gh_scalar_transform_expectation_sources.py `
  mcp_server\tests\test_gh_scalar_transform_expectation_acceptance_criteria.py `
  -q
```

Expected: all pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add `
  mcp_server\src\rook\agent\gh_scalar_transform_expectation_acceptance_criteria.py `
  mcp_server\tests\test_gh_scalar_transform_expectation_acceptance_criteria.py
git commit -m "feat(lm8f): assemble scalar transform acceptance packet"
```

---

### Task 3: LM8F CLI, Preflight, Tool Result Normalization, And Fixture Setup

**Files:**
- Create: `scripts/lm8f_scalar_transform_depth_probe.py`
- Create: `mcp_server/tests/test_lm8f_scalar_transform_depth_probe.py`

**Interfaces:**
- Produces script constants:
  - `SCRIPT_SCHEMA = "rook.lm8f_scalar_transform_depth_probe:v1"`
  - `DECISION_SCHEMA = "rook.lm8f_decision:v1"`
  - `DEFAULT_MODEL = "gemma4:12b-it-qat"`
  - `DEFAULT_ENDPOINT = "http://localhost:11434/api/chat"`
  - `INITIAL_EDITABLE_VALUE = 2.0`
  - `OFFSET_VALUE = 1.5`
  - `INITIAL_OBSERVED_OUTPUT = 3.5`
  - `EXPECTED_OUTPUT_VALUE = 7.5`
  - `SCALAR_TOLERANCE = 1e-9`
  - `ACTION_ID = "draft_gh_set_value_params"`
- Produces helpers:
  - `_args(argv: list[str] | None) -> argparse.Namespace`
  - `_canonical_evidence_is_valid(args: argparse.Namespace) -> bool`
  - `_tool_field(result: Any, *names: str) -> Any`
  - `_guid_from_result(result: Any) -> str`
  - `_inspect_output_scalar_value(result: Any) -> float | int`
  - `_run_preflight(tool_executor) -> tuple[bool, str | None, dict[str, Any]]`
  - `_create_transform_fixture(tool_executor) -> dict[str, Any]`

- [ ] **Step 1: Create script test loader and CLI tests**

Create `mcp_server/tests/test_lm8f_scalar_transform_depth_probe.py` with:

```python
from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm8f_scalar_transform_depth_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm8f_scalar_transform_depth_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical_transform_shape():
    args = PROBE._args([])

    assert args.model == "gemma4:12b-it-qat"
    assert args.endpoint == "http://localhost:11434/api/chat"
    assert args.temperature == 0
    assert args.timeout_s == 120
    assert args.excerpt_chars == 1200
    assert args.run_dir == "probe_runs"
    assert args.canonical_evidence is True


def test_cli_overrides_are_exploratory_unless_explicitly_marked_canonical():
    args = PROBE._args(["--model", "qwen3:14b"])

    assert args.canonical_evidence is False


def test_cli_rejects_non_lm8f_surfaces():
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


def test_canonical_evidence_requires_default_shape():
    args = PROBE._args(["--canonical-evidence"])
    assert PROBE._canonical_evidence_is_valid(args) is True

    for argv in (
        ["--canonical-evidence", "--model", "qwen3:14b"],
        ["--canonical-evidence", "--endpoint", "http://example.invalid/chat"],
        ["--canonical-evidence", "--temperature", "0.2"],
    ):
        assert PROBE._canonical_evidence_is_valid(PROBE._args(argv)) is False


def test_manifest_records_lm8f_identity():
    manifest = PROBE._manifest(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        canonical_evidence=True,
    )

    assert manifest["schema"] == "rook.lm8f_scalar_transform_depth_probe:v1"
    assert manifest["attempts"] == 1
    assert manifest["expected_output_value"] == 7.5
    assert manifest["initial_editable_value"] == 2.0
    assert manifest["offset_value"] == 1.5
    assert manifest["initial_observed_output"] == 3.5
    assert manifest["projection_id"] == "editable_plus_offset"
    assert manifest["worker_retry_enabled"] is False
    assert manifest["planner_model"] is None
    assert manifest["gh_edit_enabled"] is False
```

- [ ] **Step 2: Run CLI tests to verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py::test_cli_defaults_are_canonical_transform_shape `
  -q
```

Expected: import failure because the script does not exist.

- [ ] **Step 3: Create LM8F script skeleton with CLI and manifest**

Create `scripts/lm8f_scalar_transform_depth_probe.py` by following LM8C's import bootstrap, but with LM8F schema/name constants:

```python
#!/usr/bin/env python
"""LM8F GH scalar transform depth pressure live probe."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _path in (str(_SCRIPT_DIR), str(_REPO_ROOT), str(_MCP_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)
```

Define constants:

```python
SCRIPT_SCHEMA = "rook.lm8f_scalar_transform_depth_probe:v1"
DECISION_SCHEMA = "rook.lm8f_decision:v1"
DEFAULT_MODEL = "gemma4:12b-it-qat"
DEFAULT_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_TEMPERATURE = 0
DEFAULT_TIMEOUT_S = 120
DEFAULT_EXCERPT_CHARS = 1200
INITIAL_EDITABLE_VALUE = 2.0
OFFSET_VALUE = 1.5
INITIAL_OBSERVED_OUTPUT = 3.5
EXPECTED_OUTPUT_VALUE = 7.5
SCALAR_TOLERANCE = 1e-9
WORKER_NODE_ID = "set_scalar_value"
CREATE_NODE_ID = "create_scalar_transform"
VERIFY_NODE_ID = "verify_scalar_transform_output"
ACTION_ID = "draft_gh_set_value_params"
```

Implement `_args`, `_canonical_evidence_is_valid`, `_git_short_sha`, `_new_run_dir`, `_fingerprint_json`, `_sha256_text`, `_guid_sha256`, `_write_json`, `_write_json_value`, and `_manifest` using LM8C patterns and LM8F constants.

- [ ] **Step 4: Add fake executor and preflight/tool-shape tests**

Append to `mcp_server/tests/test_lm8f_scalar_transform_depth_probe.py`:

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


def test_preflight_accepts_pong_and_document_created():
    executor = FakeToolExecutor(
        {
            "rhino_ping": "pong",
            "gh_document_new": {"success": True, "data": {"Created": True}},
        }
    )

    ok, reason, summaries = _run(PROBE._run_preflight(executor))

    assert ok is True
    assert reason is None
    assert summaries["rhino_ping"] == "pong"
    assert summaries["gh_document_new"] == {"success": True, "data": {"Created": True}}
    assert executor.calls == [("rhino_ping", {}), ("gh_document_new", {})]


def test_preflight_classifies_ping_and_document_failures():
    ping_failed = FakeToolExecutor(
        {
            "rhino_ping": {"success": False, "error": "offline"},
            "gh_document_new": {"created": True},
        }
    )
    ok, reason, _summaries = _run(PROBE._run_preflight(ping_failed))
    assert ok is False
    assert reason == "rhino_ping_failed"
    assert ping_failed.calls == [("rhino_ping", {})]

    document_failed = FakeToolExecutor(
        {
            "rhino_ping": "pong",
            "gh_document_new": {"created": False},
        }
    )
    ok, reason, _summaries = _run(PROBE._run_preflight(document_failed))
    assert ok is False
    assert reason == "gh_document_new_failed"


def test_tool_result_field_helpers_handle_top_level_and_nested_data():
    assert PROBE._tool_field(
        {"success": True, "value": "TOP", "data": {"Value": "NESTED"}},
        "value",
        "Value",
    ) == "TOP"
    assert PROBE._tool_field(
        {"success": True, "data": {"Value": "NESTED"}},
        "value",
        "Value",
    ) == "NESTED"
    assert PROBE._guid_from_result(
        {"success": True, "data": {"Guid": "COMPONENT-GUID"}}
    ) == "COMPONENT-GUID"


def test_inspect_output_scalar_value_accepts_real_preview_shape():
    assert PROBE._inspect_output_scalar_value(
        {
            "success": True,
            "data": {
                "param_nickname": "R",
                "structure": "single",
                "data_count": 1,
                "preview": ["7.5"],
            },
        }
    ) == 7.5
    assert PROBE._inspect_output_scalar_value(
        {"success": True, "data_count": 1, "preview": [3.5]}
    ) == 3.5


@pytest.mark.parametrize(
    "result",
    [
        {"success": True, "data": {"data_count": 0, "preview": []}},
        {"success": True, "data": {"data_count": 1, "preview": ["not-number"]}},
        {"success": False, "data": "Object not found"},
    ],
)
def test_inspect_output_scalar_value_rejects_invalid_live_shapes(result):
    with pytest.raises(ValueError, match="inspect output scalar"):
        PROBE._inspect_output_scalar_value(result)
```

- [ ] **Step 5: Implement preflight and tool-shape helpers**

In `scripts/lm8f_scalar_transform_depth_probe.py`, implement the helpers by adapting LM8C:

```python
def _tool_result_failed(result: Any) -> bool:
    if result is None:
        return True
    if isinstance(result, Mapping):
        if result.get("success") is False:
            return True
        if result.get("error"):
            return True
        data = result.get("data")
        if isinstance(data, str) and data.startswith("Error:"):
            return True
    return False


def _tool_data(result: Any) -> Any:
    if isinstance(result, Mapping) and isinstance(result.get("data"), Mapping):
        return result["data"]
    return result


def _tool_field(result: Any, *names: str) -> Any:
    if not isinstance(result, Mapping):
        return None
    for name in names:
        if name in result:
            return result[name]
    data = result.get("data")
    if not isinstance(data, Mapping):
        return None
    for name in names:
        if name in data:
            return data[name]
    return None
```

Implement `_inspect_output_scalar_value(result)` using `data.preview[0]` first, then `value`/`Value` fallback:

```python
def _inspect_output_scalar_value(result: Any) -> float | int:
    if _tool_result_failed(result):
        raise ValueError("inspect output scalar result failed")
    data = _tool_data(result)
    if not isinstance(data, Mapping):
        raise ValueError("inspect output scalar data missing")
    preview = data.get("preview")
    if isinstance(preview, Sequence) and not isinstance(preview, (str, bytes, bytearray)):
        if len(preview) != 1:
            raise ValueError("inspect output scalar preview must contain one value")
        return _coerce_scalar_value(preview[0])
    value = _tool_field(result, "value", "Value")
    return _coerce_scalar_value(value)
```

Keep `_coerce_scalar_value` identical in behavior to LM8C.

- [ ] **Step 6: Add direct-tool fixture setup test**

Append:

```python
def _fixture_tool_responses(*, editable_value="2.0", observed_output="3.5"):
    return {
        "gh_library": {
            "success": True,
            "count": 1,
            "components": [
                {
                    "name": "Addition",
                    "nickName": "A+B",
                    "category": "Maths",
                    "guid": "ADDITION-PROXY-GUID",
                }
            ],
        },
        "gh_create_slider": [
            {
                "success": True,
                "data": {
                    "Created": True,
                    "Guid": "EDITABLE-GUID-1",
                    "NickName": "LM8F_Editable",
                },
            },
            {
                "success": True,
                "data": {
                    "Created": True,
                    "Guid": "OFFSET-GUID-1",
                    "NickName": "LM8F_Offset",
                },
            },
        ],
        "gh_create_component": {
            "success": True,
            "data": {
                "Created": True,
                "Guid": "ADDITION-GUID-1",
                "NickName": "A+B",
            },
        },
        "gh_connect": [
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
        ],
        "gh_solve": {"success": True, "data": {"scheduled": True}},
        "gh_get_value": {
            "success": True,
            "data": {"Guid": "EDITABLE-GUID-1", "Value": editable_value},
        },
        "gh_inspect_output": {
            "success": True,
            "data": {
                "param_nickname": "R",
                "structure": "single",
                "data_count": 1,
                "preview": [observed_output],
            },
        },
    }


def test_create_transform_fixture_uses_direct_tools_and_hashes_worker_hidden_guid():
    executor = FakeToolExecutor(
        {
            "gh_library": {
                "success": True,
                "count": 1,
                "components": [
                    {
                        "name": "Addition",
                        "nickName": "A+B",
                        "category": "Maths",
                        "guid": "ADDITION-PROXY-GUID",
                    }
                ],
            },
            "gh_create_slider": [
                {
                    "success": True,
                    "data": {
                        "Created": True,
                        "Guid": "EDITABLE-GUID-1",
                        "NickName": "LM8F_Editable",
                    },
                },
                {
                    "success": True,
                    "data": {
                        "Created": True,
                        "Guid": "OFFSET-GUID-1",
                        "NickName": "LM8F_Offset",
                    },
                },
            ],
            "gh_create_component": {
                "success": True,
                "data": {
                    "Created": True,
                    "Guid": "ADDITION-GUID-1",
                    "NickName": "A+B",
                },
            },
            "gh_connect": [
                {"success": True, "data": {"connected": True}},
                {"success": True, "data": {"connected": True}},
            ],
            "gh_solve": {"success": True, "data": {"scheduled": True}},
            "gh_get_value": {
                "success": True,
                "data": {"Guid": "EDITABLE-GUID-1", "Value": "2.0"},
            },
            "gh_inspect_output": {
                "success": True,
                "data": {
                    "param_nickname": "R",
                    "structure": "single",
                    "data_count": 1,
                    "preview": ["3.5"],
                },
            },
        }
    )

    fixture = _run(PROBE._create_transform_fixture(executor))

    assert executor.calls == [
        ("gh_library", {"search": "addition", "limit": 20}),
        (
            "gh_create_slider",
            {
                "nickname": "LM8F_Editable",
                "min": 0,
                "max": 10,
                "value": 2.0,
                "x": 20,
                "y": 80,
            },
        ),
        (
            "gh_create_slider",
            {
                "nickname": "LM8F_Offset",
                "min": 0,
                "max": 10,
                "value": 1.5,
                "x": 20,
                "y": 180,
            },
        ),
        ("gh_create_component", {"guid": "ADDITION-PROXY-GUID", "x": 280, "y": 120}),
        (
            "gh_connect",
            {
                "sourceGuid": "EDITABLE-GUID-1",
                "targetGuid": "ADDITION-GUID-1",
                "targetParam": "A",
            },
        ),
        (
            "gh_connect",
            {
                "sourceGuid": "OFFSET-GUID-1",
                "targetGuid": "ADDITION-GUID-1",
                "targetParam": "B",
            },
        ),
        ("gh_solve", {"delay": 25}),
        ("gh_get_value", {"guid": "EDITABLE-GUID-1"}),
        ("gh_inspect_output", {"guid": "ADDITION-GUID-1", "param": "R"}),
    ]
    assert fixture["editable_component_guid"] == "EDITABLE-GUID-1"
    assert fixture["offset_component_guid"] == "OFFSET-GUID-1"
    assert fixture["addition_component_guid"] == "ADDITION-GUID-1"
    assert fixture["editable_value"] == 2.0
    assert fixture["observed_output_value"] == 3.5
    assert fixture["receipt"]["editable_value"] == 2.0
    assert fixture["receipt"]["observed_output_value"] == 3.5
    assert fixture["receipt"]["scalar_anchor"]["internal_component_guid"] == "EDITABLE-GUID-1"
    rendered_visible = json.dumps(fixture["visible_receipt"], sort_keys=True)
    assert "EDITABLE-GUID-1" not in rendered_visible
    assert "OFFSET-GUID-1" not in rendered_visible
    assert "ADDITION-GUID-1" not in rendered_visible
    assert fixture["fixture_setup_summary"]["editable_component_guid"] == "EDITABLE-GUID-1"
    assert fixture["fixture_setup_summary"]["addition_component_guid"] == "ADDITION-GUID-1"


def test_create_transform_fixture_rejects_missing_addition_component():
    executor = FakeToolExecutor(
        {
            "gh_library": {
                "success": True,
                "count": 1,
                "components": [{"name": "Multiply", "nickName": "A*B", "category": "Maths"}],
            },
        }
    )

    with pytest.raises(ValueError, match="gh_library_addition_not_found"):
        _run(PROBE._create_transform_fixture(executor))

    assert executor.calls == [("gh_library", {"search": "addition", "limit": 20})]


def test_create_transform_fixture_rejects_noncanonical_editable_precheck_value():
    executor = FakeToolExecutor(_fixture_tool_responses(editable_value="2.25"))

    with pytest.raises(ValueError, match="initial_editable_value_mismatch"):
        _run(PROBE._create_transform_fixture(executor))


def test_create_transform_fixture_rejects_noncanonical_initial_observed_output():
    executor = FakeToolExecutor(_fixture_tool_responses(observed_output="3.25"))

    with pytest.raises(ValueError, match="initial_observed_output_mismatch"):
        _run(PROBE._create_transform_fixture(executor))
```

- [ ] **Step 7: Implement transform fixture setup**

Implement `_addition_proxy_guid_from_library(result)` that searches both top-level `components` and nested `data.components` for:

```python
component.get("name") == "Addition"
component.get("nickName") == "A+B"
component.get("category") == "Maths"
```

Use `component["guid"]` or `component["Guid"]` as the proxy GUID.

Implement `_create_transform_fixture(tool_executor)`:

```python
async def _create_transform_fixture(
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]],
) -> dict[str, Any]:
    library_result = await tool_executor("gh_library", {"search": "addition", "limit": 20})
    if _tool_result_failed(library_result):
        raise ValueError("gh_library_failed")
    addition_proxy_guid = _addition_proxy_guid_from_library(library_result)

    editable_result = await tool_executor(
        "gh_create_slider",
        {
            "nickname": "LM8F_Editable",
            "min": 0,
            "max": 10,
            "value": INITIAL_EDITABLE_VALUE,
            "x": 20,
            "y": 80,
        },
    )
    if _tool_result_failed(editable_result) or _tool_field(editable_result, "created", "Created") is not True:
        raise ValueError("gh_create_editable_slider_failed")
    editable_guid = _guid_from_result(editable_result)
```

Repeat for offset slider, create Addition, connect A/B, solve, `gh_get_value` editable slider, and `gh_inspect_output` Addition `R`. Return:

```python
{
    "editable_component_guid": editable_guid,
    "offset_component_guid": offset_guid,
    "addition_component_guid": addition_guid,
    "editable_value": editable_value,
    "observed_output_value": observed_output_value,
    "receipt": receipt,
    "visible_receipt": visible_receipt,
    "fixture_setup_summary": fixture_setup_summary,
}
```

The internal receipt may include the editable GUID as `scalar_anchor.internal_component_guid`; the visible receipt must include only `guid_present` and SHA-256 hashes.

After coercing the editable-slider precheck and Addition `R` output, reject any
non-canonical starting state before returning the fixture:

```python
if abs(float(editable_value) - float(INITIAL_EDITABLE_VALUE)) > SCALAR_TOLERANCE:
    raise ValueError("initial_editable_value_mismatch")
if abs(float(observed_output_value) - float(INITIAL_OBSERVED_OUTPUT)) > SCALAR_TOLERANCE:
    raise ValueError("initial_observed_output_mismatch")
```

These checks belong in `_create_transform_fixture(...)` because they fence the
live fixture setup before scalar source extraction and before the worker path.

- [ ] **Step 8: Run Task 3 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py::test_cli_defaults_are_canonical_transform_shape `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py::test_preflight_accepts_pong_and_document_created `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py::test_tool_result_field_helpers_handle_top_level_and_nested_data `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py::test_inspect_output_scalar_value_accepts_real_preview_shape `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py::test_create_transform_fixture_uses_direct_tools_and_hashes_worker_hidden_guid `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py::test_create_transform_fixture_rejects_missing_addition_component `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py::test_create_transform_fixture_rejects_noncanonical_editable_precheck_value `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py::test_create_transform_fixture_rejects_noncanonical_initial_observed_output `
  -q
```

Expected: all pass.

- [ ] **Step 9: Commit Task 3**

```powershell
git add scripts\lm8f_scalar_transform_depth_probe.py mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py
git commit -m "feat(lm8f): create scalar transform live probe scaffold"
```

---

### Task 4: Scalar Runtime Readiness And Worker Request Rendering

**Files:**
- Modify: `scripts/lm8f_scalar_transform_depth_probe.py`
- Modify: `mcp_server/tests/test_lm8f_scalar_transform_depth_probe.py`

**Interfaces:**
- Consumes Task 1 and Task 2 modules.
- Produces:
  - `_scalar_transform_source_routing_artifact() -> dict[str, Any]`
  - `_scalar_transform_contract_payload() -> dict[str, Any]`
  - `_graph_from_transform_receipt(receipt: Mapping[str, Any]) -> PlanGraph`
  - `_scalar_runtime_context(...) -> dict[str, Any]`
  - `_scalar_transform_worker_evidence_packet(...) -> WorkerKnowledgePacket`
  - `_build_local_turn_payload(...) -> dict[str, Any]`

- [ ] **Step 1: Add runtime readiness and worker request tests**

Append:

```python
def _valid_transform_fixture():
    return {
        "editable_component_guid": "EDITABLE-GUID-1",
        "offset_component_guid": "OFFSET-GUID-1",
        "addition_component_guid": "ADDITION-GUID-1",
        "editable_value": 2.0,
        "observed_output_value": 3.5,
        "receipt": {
            "editable_value": 2.0,
            "observed_output_value": 3.5,
            "scalar_anchor": {
                "internal_component_guid": "EDITABLE-GUID-1",
                "editable_value_contract": {
                    "label": "LM8F_Editable",
                    "value_type": "number",
                    "current_value": 2.0,
                    "projection_id": "editable_plus_offset",
                },
            },
        },
        "visible_receipt": {},
        "fixture_setup_summary": {},
    }


def test_scalar_transform_runtime_context_static_validates_without_lm5x_routability():
    graph = PROBE._graph_from_transform_receipt(_valid_transform_fixture()["receipt"])
    context = PROBE._scalar_runtime_context(
        graph=graph,
        workflow_contract_payload=PROBE._scalar_transform_contract_payload(),
        convention_packets=(),
    )

    routing_report = context["static_routing_report"]
    assert routing_report["valid"] is True
    assert routing_report["routability_evaluated"] is False
    assert context["scalar_runtime_ready"] is True
    assert context["sources"].expected_output_contract.value == 7.5
    assert context["sources"].offset_contract.value == 1.5
    assert context["sources"].editable_observation.value == 2.0
    assert context["sources"].observed_output.value == 3.5
    assert context["packet"]["fields"]["expected_output_value"] == 7.5
    assert context["packet"]["fields"]["offset_value"] == 1.5
    assert context["worker_visible"]["source"] == "gh_scalar_transform_expectation"


def test_scalar_transform_runtime_context_fails_when_live_receipt_missing_output():
    receipt = _valid_transform_fixture()["receipt"]
    receipt.pop("observed_output_value")
    graph = PROBE._graph_from_transform_receipt(receipt)

    with pytest.raises(ValueError, match="observed_output_value"):
        PROBE._scalar_runtime_context(
            graph=graph,
            workflow_contract_payload=PROBE._scalar_transform_contract_payload(),
            convention_packets=(),
        )


def test_scalar_transform_runtime_context_rejects_projection_invariant_mismatch():
    graph = PROBE._graph_from_transform_receipt(_valid_transform_fixture()["receipt"])
    payload = PROBE._scalar_transform_contract_payload()
    payload["rules"]["verify_scalar_transform_output"]["offset_value"] = 1.25

    with pytest.raises(ValueError, match="projection_invariant_mismatch"):
        PROBE._scalar_runtime_context(
            graph=graph,
            workflow_contract_payload=payload,
            convention_packets=(),
        )


def test_worker_request_uses_transform_knowledge_and_never_exposes_raw_guid_or_derived_value():
    fixture = _valid_transform_fixture()
    graph = PROBE._graph_from_transform_receipt(fixture["receipt"])
    runtime = PROBE._scalar_runtime_context(
        graph=graph,
        workflow_contract_payload=PROBE._scalar_transform_contract_payload(),
        convention_packets=(),
    )

    payload = PROBE._build_local_turn_payload(
        graph=graph,
        packet=runtime["packet"],
        worker_visible=runtime["worker_visible"],
    )

    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema"] == "rook.local_worker_turn_request:v1"
    assert "gh_scalar_transform_expectation_evidence" in rendered
    assert "draft_gh_set_value_params" in rendered
    assert "observed_output = editable_value + offset_value" in rendered
    assert "current_editable_value" in rendered
    assert "offset_value" in rendered
    assert "expected_output_value" in rendered
    assert "EDITABLE-GUID-1" not in rendered
    assert "OFFSET-GUID-1" not in rendered
    assert "ADDITION-GUID-1" not in rendered
    assert "6.0" not in rendered
    assert "set editable value to 6" not in rendered.lower()
    assert "gh_edit" not in rendered
    assert "gh_update_script" not in rendered
    assert "repair_same_component" not in rendered
    assert "action_selection_contract" in rendered
    assert "pass1_decision_required_fields_if_acting" in rendered
    assert "final_action_request_required_fields" in rendered
    assert "do not author target GUID" in rendered
    assert "do not call GH tools directly" in rendered
    assert "do not author topology, code, or batch edits" in rendered
```

- [ ] **Step 2: Run new tests to verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py::test_scalar_transform_runtime_context_static_validates_without_lm5x_routability `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py::test_worker_request_uses_transform_knowledge_and_never_exposes_raw_guid_or_derived_value `
  -q
```

Expected: attribute failures for missing runtime/request helpers.

- [ ] **Step 3: Implement runtime context and worker request helpers**

In `scripts/lm8f_scalar_transform_depth_probe.py`, import:

```python
from lm_worker_two_pass_publication import run_two_pass_worker_publication
from rook.agent.gh_scalar_transform_expectation_acceptance_criteria import (
    assemble_gh_scalar_transform_expectation_packet,
    project_gh_scalar_transform_expectation_legacy,
)
from rook.agent.gh_scalar_transform_expectation_sources import (
    TRANSFORM_CONVENTION_SOURCE_PATH,
    TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
    TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
    TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH,
    TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
    TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
    TRANSFORM_PROJECTION_SOURCE_PATH,
    extract_gh_scalar_transform_expectation_sources,
)
from rook.agent.local_worker_source_routing_validator import (
    validate_worker_visible_source_routing,
)
from rook.agent.local_worker_turn_context import (
    WorkerAllowedAction,
    WorkerKnowledgePacket,
    build_local_worker_turn_context,
)
from rook.agent.local_worker_turn_request import render_local_worker_turn_request_payload
from rook.agent.plan_graph_gh_scalar_value_apply import apply_gh_scalar_value_action_to_node
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_workflow_contract import (
    CompiledWorkflowScaffold,
    WorkflowCompileRecord,
    WorkflowContractSnapshot,
)
from rook.learning.plan_graph import GraphMemory, NodeEvidence, PlanGraph, PlanGraphNode
```

Implement `_scalar_transform_source_routing_artifact()` with the exact routes from Task 1. Implement `_scalar_transform_contract_payload()`:

```python
def _scalar_transform_contract_payload() -> dict[str, Any]:
    return {
        "rules": {
            VERIFY_NODE_ID: {
                "expected_output_value": EXPECTED_OUTPUT_VALUE,
                "offset_value": OFFSET_VALUE,
                "projection": {
                    "projection_id": "editable_plus_offset",
                    "description": "observed_output = editable_value + offset_value",
                    "editable_variable": "editable_value",
                    "offset_variable": "offset_value",
                    "output_variable": "observed_output",
                },
            }
        }
    }
```

Build a graph with nodes `create_scalar_transform`, `set_scalar_value`, and `verify_scalar_transform_output`. The worker node should use execution ref `gh_set_value:v1`; the verifier node should use `gh_inspect_output:v1`.

Use `assemble_gh_scalar_transform_expectation_packet(...)` and `project_gh_scalar_transform_expectation_legacy(...)` in `_scalar_runtime_context(...)`.

Before assembling the packet, assert the extracted live/source facts agree with
the declared projection:

```python
def _projection_invariant_holds(sources: Any) -> bool:
    expected_observed = (
        float(sources.editable_observation.value)
        + float(sources.offset_contract.value)
    )
    return (
        abs(float(sources.observed_output.value) - expected_observed)
        <= SCALAR_TOLERANCE
    )
```

In `_scalar_runtime_context(...)`:

```python
sources = extract_gh_scalar_transform_expectation_sources(...)
if not _projection_invariant_holds(sources):
    raise ValueError("projection_invariant_mismatch")
packet = assemble_gh_scalar_transform_expectation_packet(sources)
```

This keeps a stale or malformed transform fixture from reaching the worker even
when each individual scalar fact is syntactically valid.

Create worker evidence packet:

```python
def _scalar_transform_worker_evidence_packet(
    *,
    packet: Mapping[str, Any],
    worker_visible: Mapping[str, Any],
) -> WorkerKnowledgePacket:
    fields = packet["fields"]
    return WorkerKnowledgePacket(
        packet_id="gh_scalar_transform_expectation_evidence",
        kind="evidence",
        title="GH scalar transform expectation evidence",
        content={
            "source": "gh_scalar_transform_expectation",
            "trust": "high",
            "state": "post_scalar_transform_fixture_pre_worker",
            "fields": {
                "current_editable_value": fields["current_editable_value"],
                "offset_value": fields["offset_value"],
                "current_observed_output": fields["current_observed_output"],
                "expected_output_value": fields["expected_output_value"],
                "projection": dict(fields["projection"]),
                "editable_value_contract": dict(fields["editable_value_contract"]),
                "acceptance_criteria": dict(worker_visible),
                "recommended_action_id": ACTION_ID,
                "action_selection_contract": dict(fields["action_selection_contract"]),
            },
        },
    )
```

Use `build_local_worker_turn_context(...)` and `render_local_worker_turn_request_payload(...)` as LM8C does.

- [ ] **Step 4: Run Task 4 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py::test_scalar_transform_runtime_context_static_validates_without_lm5x_routability `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py::test_scalar_transform_runtime_context_fails_when_live_receipt_missing_output `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py::test_scalar_transform_runtime_context_rejects_projection_invariant_mismatch `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py::test_worker_request_uses_transform_knowledge_and_never_exposes_raw_guid_or_derived_value `
  -q
```

Expected: all pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add scripts\lm8f_scalar_transform_depth_probe.py mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py
git commit -m "feat(lm8f): render transform worker request"
```

---

### Task 5: Worker Publication Decisions, Scalar Applier, Live Set, Solve, And Verifier Floor

**Files:**
- Modify: `scripts/lm8f_scalar_transform_depth_probe.py`
- Modify: `mcp_server/tests/test_lm8f_scalar_transform_depth_probe.py`

**Interfaces:**
- Consumes:
  - `run_two_pass_worker_publication(...)`
  - `apply_gh_scalar_value_action_to_node(...)`
- Produces:
  - `_decision_from_publication(publication_row, response_payload) -> dict[str, Any] | None`
  - `_dispatch_set_value_solve_and_verify(...) -> dict[str, Any]`
  - `_run_probe(...) -> Path`
  - `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: Add publication decision tests**

Append:

```python
class FakePublication:
    def __init__(self, row, response_payload=None):
        self.row = row
        self.response_payload = response_payload


def test_publication_non_action_maps_to_worker_declined():
    row = {
        "status": "published",
        "pass2_response_kind": "observation",
        "observation_action_intent_anomaly": False,
    }
    payload = {
        "schema": "rook.local_worker_turn_response:v1",
        "kind": "observation",
        "message": "not acting",
        "data": None,
    }

    decision = PROBE._decision_from_publication(row, payload)

    assert decision == {
        "decision": "worker_declined",
        "reason": "worker_observed",
        "phase": "worker_publication",
        "final_worker_response_kind": "observation",
    }


def test_publication_failure_maps_to_publication_failed():
    decision = PROBE._decision_from_publication(
        {"status": "pass2_lm5g_invalid", "failure_reason": "bad-json"},
        None,
    )

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "pass2_lm5g_invalid:bad-json"


def test_missing_pass1_action_id_stays_publication_failed():
    decision = PROBE._decision_from_publication(
        {
            "status": "pass1_decision_invalid",
            "failure_reason": "pass1_missing_action_id",
            "pass1_content_excerpt": '{"kind": "action_request"}',
        },
        None,
    )

    assert decision == {
        "decision": "publication_failed",
        "reason": "pass1_decision_invalid:pass1_missing_action_id",
        "phase": "worker_publication",
    }
```

- [ ] **Step 2: Add verifier-floor dispatch tests**

Append:

```python
def test_dispatch_set_value_solve_and_verify_accepts_inspected_output_match():
    executor = FakeToolExecutor(
        {
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "EDITABLE-GUID-1", "NewValue": 6.0},
            },
            "gh_solve": {"success": True, "data": {"scheduled": True}},
            "gh_inspect_output": {
                "success": True,
                "data": {
                    "param_nickname": "R",
                    "structure": "single",
                    "data_count": 1,
                    "preview": ["7.5"],
                },
            },
        }
    )

    result = _run(
        PROBE._dispatch_set_value_solve_and_verify(
            tool_executor=executor,
            editable_component_guid="EDITABLE-GUID-1",
            addition_component_guid="ADDITION-GUID-1",
            worker_value=6.0,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "accepted"
    assert result["decision"]["reason"] == "verify_scalar_output_succeeded"
    assert result["live_set_value_summary"]["component_guid"] == "EDITABLE-GUID-1"
    assert result["live_set_value_summary"]["worker_action_value"] == 6.0
    assert result["verify_scalar_output_summary"]["component_guid_sha256"].startswith("sha256:")
    assert "component_guid" not in result["verify_scalar_output_summary"]
    assert result["verify_scalar_output_summary"]["observed_output_value"] == 7.5
    assert executor.calls == [
        ("gh_set_value", {"guid": "EDITABLE-GUID-1", "value": 6.0}),
        ("gh_solve", {"delay": 25}),
        ("gh_inspect_output", {"guid": "ADDITION-GUID-1", "param": "R"}),
    ]


def test_dispatch_set_value_solve_and_verify_rejects_inspected_output_mismatch():
    executor = FakeToolExecutor(
        {
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "EDITABLE-GUID-1", "NewValue": 6.0},
            },
            "gh_solve": {"success": True, "data": {"scheduled": True}},
            "gh_inspect_output": {
                "success": True,
                "data": {"data_count": 1, "preview": ["6.5"]},
            },
        }
    )

    result = _run(
        PROBE._dispatch_set_value_solve_and_verify(
            tool_executor=executor,
            editable_component_guid="EDITABLE-GUID-1",
            addition_component_guid="ADDITION-GUID-1",
            worker_value=6.0,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "rejected"
    assert result["decision"]["reason"] == "verify_scalar_output_failed"
    assert result["verify_scalar_output_summary"]["observed_output_value"] == 6.5


def test_dispatch_set_value_solve_and_verify_accepts_when_set_reports_false_but_output_matches():
    executor = FakeToolExecutor(
        {
            "gh_set_value": {
                "success": False,
                "data": {"Guid": "EDITABLE-GUID-1", "NewValue": 6.0},
            },
            "gh_solve": {"success": True, "data": {"scheduled": True}},
            "gh_inspect_output": {
                "success": True,
                "data": {"data_count": 1, "preview": ["7.5"]},
            },
        }
    )

    result = _run(
        PROBE._dispatch_set_value_solve_and_verify(
            tool_executor=executor,
            editable_component_guid="EDITABLE-GUID-1",
            addition_component_guid="ADDITION-GUID-1",
            worker_value=6.0,
            expected_value=7.5,
        )
    )

    assert result["live_set_value_summary"]["set_value_reported_success"] is False
    assert result["decision"]["decision"] == "accepted"


def test_dispatch_set_value_solve_and_verify_rejects_transport_exception_without_verifier():
    executor = FakeToolExecutor(
        {
            "gh_set_value": RuntimeError("transport down"),
            "gh_solve": {"success": True, "data": {"scheduled": True}},
            "gh_inspect_output": {"success": True, "data": {"preview": ["7.5"]}},
        }
    )

    result = _run(
        PROBE._dispatch_set_value_solve_and_verify(
            tool_executor=executor,
            editable_component_guid="EDITABLE-GUID-1",
            addition_component_guid="ADDITION-GUID-1",
            worker_value=6.0,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "rejected"
    assert result["decision"]["reason"].startswith("gh_set_value_exception:")
    assert result["verify_scalar_output_summary"] is None
    assert executor.calls == [
        ("gh_set_value", {"guid": "EDITABLE-GUID-1", "value": 6.0})
    ]


def test_dispatch_set_value_solve_and_verify_rejects_invalid_inspected_value():
    executor = FakeToolExecutor(
        {
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "EDITABLE-GUID-1", "NewValue": 6.0},
            },
            "gh_solve": {"success": True, "data": {"scheduled": True}},
            "gh_inspect_output": {
                "success": True,
                "data": {"data_count": 1, "preview": ["not-number"]},
            },
        }
    )

    result = _run(
        PROBE._dispatch_set_value_solve_and_verify(
            tool_executor=executor,
            editable_component_guid="EDITABLE-GUID-1",
            addition_component_guid="ADDITION-GUID-1",
            worker_value=6.0,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "rejected"
    assert result["decision"]["reason"] == "verify_scalar_output_invalid_value"
```

- [ ] **Step 3: Implement publication and verifier dispatch helpers**

Copy `_decision_from_publication(...)` behavior from LM8C, preserving the real field name:

```python
if publication_row.get("observation_action_intent_anomaly") is True:
    ...
```

Do not use `combined_observation_action_intent_anomaly`.

Implement `_dispatch_set_value_solve_and_verify(...)`:

```python
async def _dispatch_set_value_solve_and_verify(
    *,
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]],
    editable_component_guid: str,
    addition_component_guid: str,
    worker_value: float | int,
    expected_value: float | int,
) -> dict[str, Any]:
    try:
        set_result = await tool_executor(
            "gh_set_value",
            {"guid": editable_component_guid, "value": worker_value},
        )
    except Exception as exc:
        return {
            "live_set_value_summary": {
                "tool_name": "gh_set_value",
                "component_guid": editable_component_guid,
                "component_guid_sha256": _guid_sha256(editable_component_guid),
                "worker_action_value": worker_value,
                "set_value_reported_success": False,
                "exception": type(exc).__name__,
            },
            "verify_scalar_output_summary": None,
            "decision": {
                "decision": "rejected",
                "reason": f"gh_set_value_exception:{type(exc).__name__}",
                "phase": "live_set_value",
            },
        }
```

After a completed `gh_set_value` call, always attempt `gh_solve` and `gh_inspect_output` unless `gh_solve` raises. Treat reported `success:false` as diagnostic when the call completed. The verifier-floor match is:

```python
matched = abs(float(observed) - float(expected_value)) <= SCALAR_TOLERANCE
```

- [ ] **Step 4: Add run-probe accepted path test**

Append:

```python
def _published_action(value=6.0):
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
            "rationale": "Use the offset relationship to match the expected output.",
            "input": {"value": value},
        },
    )


def _fixture_responses_for_success():
    return {
        "rhino_ping": "pong",
        "gh_document_new": {"success": True, "data": {"Created": True}},
        "gh_library": {
            "success": True,
            "count": 1,
            "components": [
                {
                    "name": "Addition",
                    "nickName": "A+B",
                    "category": "Maths",
                    "guid": "ADDITION-PROXY-GUID",
                }
            ],
        },
        "gh_create_slider": [
            {"success": True, "data": {"Created": True, "Guid": "EDITABLE-GUID-1"}},
            {"success": True, "data": {"Created": True, "Guid": "OFFSET-GUID-1"}},
        ],
        "gh_create_component": {
            "success": True,
            "data": {"Created": True, "Guid": "ADDITION-GUID-1"},
        },
        "gh_connect": [
            {"success": True, "data": {"connected": True}},
            {"success": True, "data": {"connected": True}},
        ],
        "gh_solve": [
            {"success": True, "data": {"scheduled": True}},
            {"success": True, "data": {"scheduled": True}},
        ],
        "gh_get_value": {"success": True, "data": {"Value": "2.0"}},
        "gh_inspect_output": [
            {"success": True, "data": {"data_count": 1, "preview": ["3.5"]}},
            {"success": True, "data": {"data_count": 1, "preview": ["7.5"]}},
        ],
        "gh_set_value": {"success": True, "data": {"Guid": "EDITABLE-GUID-1"}},
    }


def test_run_probe_accepts_worker_value_that_matches_transform_output(tmp_path):
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
        publication_runner=lambda *args, **kwargs: _published_action(6.0),
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    request = json.loads((run_dir / "worker_request_payload.json").read_text(encoding="utf-8"))
    worker_action = json.loads((run_dir / "worker_action.json").read_text(encoding="utf-8"))
    verify = json.loads((run_dir / "verify_scalar_output_summary.json").read_text(encoding="utf-8"))

    assert decision["decision"] == "accepted"
    assert decision["reason"] == "verify_scalar_output_succeeded"
    assert decision["scalar_runtime_ready"] is True
    assert decision["worker_publication_ran"] is True
    assert decision["live_set_value_dispatched"] is True
    assert decision["verify_scalar_output_ran"] is True
    assert worker_action["input"] == {"value": 6.0}
    assert verify["observed_output_value"] == 7.5
    rendered_request = json.dumps(request, sort_keys=True)
    assert "6.0" not in rendered_request
    assert "EDITABLE-GUID-1" not in rendered_request
    assert "ADDITION-GUID-1" not in rendered_request
    rendered_decision = json.dumps(decision, sort_keys=True)
    assert "EDITABLE-GUID-1" not in rendered_decision
    assert "ADDITION-GUID-1" not in rendered_decision
```

- [ ] **Step 5: Implement `_run_probe(...)` and `main(...)`**

Use LM8C's `_run_probe(...)` structure with LM8F names:

1. Create `probe_runs/lm8f-<timestamp>-<sha>/`.
2. Write `manifest.json`.
3. Run script-owned preflight.
4. Create transform fixture.
5. Write `fixture_setup_summary.json`.
6. Write `scalar_transform_contract.json`.
7. Build graph from internal receipt.
8. Build scalar runtime context.
9. Write:
   - `scalar_source_routing.json`
   - `static_routing_validation.json`
   - `scalar_sources.json`
   - `acceptance_criteria_packet.json`
   - `worker_visible_acceptance_criteria.json`
   - `worker_request_payload.json`
10. Run worker publication.
11. Check hidden marker and raw GUID leaks before writing publication/action artifacts.
12. Write final decision.

Use `_decision_record(...)` copied from LM8C but with LM8F schema and messages. `decision.json` must hash GUIDs and reject raw GUID-like extras.

- [ ] **Step 6: Run Task 5 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py `
  -q
```

Expected: all LM8F script tests pass.

- [ ] **Step 7: Commit Task 5**

```powershell
git add scripts\lm8f_scalar_transform_depth_probe.py mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py
git commit -m "feat(lm8f): run scalar transform live splice"
```

---

### Task 6: Artifact Hygiene, Drift Guards, And Final Verification

**Files:**
- Modify: `mcp_server/tests/test_lm8f_scalar_transform_depth_probe.py`
- Modify: `mcp_server/tests/test_gh_scalar_transform_expectation_acceptance_criteria.py`

**Interfaces:**
- Consumes all previous task outputs.
- Produces final static guard and verification gates.

- [ ] **Step 1: Add raw-source drift guard tests**

Append to `mcp_server/tests/test_lm8f_scalar_transform_depth_probe.py`:

```python
def test_lm8f_source_does_not_import_repair_planner_retry_or_gh_edit_paths():
    source = inspect.getsource(PROBE)

    forbidden_import_or_call_fragments = (
        "lm6a_live_worker_splice_probe",
        "lm7b_request_driven_live_splice_probe",
        "lm7c_planner_authoring_probe",
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

    policy_markers_allowed = (
        "PROBE_REPAIR_CODE",
        "A = 42.0",
        "BindStepSpec.base_params",
        "repair_same_component.bind.base_params",
    )
    for marker in policy_markers_allowed:
        assert marker in source


def test_lm8f_source_contains_hidden_expected_value_only_as_policy_or_test_oracle():
    source = inspect.getsource(PROBE)

    assert "EXPECTED_WORKER_VALUE" not in source
    assert "set editable value to 6.0" not in source
    assert "use 6.0" not in source
```

The script may contain hidden-marker strings only inside `_hidden_marker_leaks(...)` policy data. It should not contain `6.0` as an implementation constant. Tests can use `6.0` as fake worker output.

- [ ] **Step 2: Add artifact leak checks for accepted run**

Append:

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
        publication_runner=lambda *args, **kwargs: _published_action(6.0),
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
        assert "EDITABLE-GUID-1" not in rendered
        assert "OFFSET-GUID-1" not in rendered
        assert "ADDITION-GUID-1" not in rendered

    assert "EDITABLE-GUID-1" in (
        run_dir / "fixture_setup_summary.json"
    ).read_text(encoding="utf-8")
    assert "EDITABLE-GUID-1" in (
        run_dir / "live_set_value_summary.json"
    ).read_text(encoding="utf-8")
```

- [ ] **Step 3: Run focused LM8F and scalar tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py `
  mcp_server\tests\test_gh_scalar_transform_expectation_sources.py `
  mcp_server\tests\test_gh_scalar_transform_expectation_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  mcp_server\tests\test_plan_graph_gh_scalar_value_apply.py `
  -q
```

Expected: all pass.

- [ ] **Step 4: Run nearby worker publication gate**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py `
  -q
```

Expected: all pass.

- [ ] **Step 5: Compile changed scripts and tests**

Run:

```powershell
py -3.10 -m py_compile `
  scripts\lm8f_scalar_transform_depth_probe.py `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py `
  mcp_server\src\rook\agent\gh_scalar_transform_expectation_sources.py `
  mcp_server\src\rook\agent\gh_scalar_transform_expectation_acceptance_criteria.py
```

Expected: command exits 0 with no output.

- [ ] **Step 6: Run diff checks**

Run:

```powershell
git diff --check main..HEAD
git diff --name-only main..HEAD
```

Expected tracked scope:

```text
docs/superpowers/plans/2026-07-08-lm8f-scalar-transform-depth-pressure.md
docs/superpowers/specs/2026-07-08-lm8f-scalar-transform-depth-pressure-design.md
mcp_server/src/rook/agent/gh_scalar_transform_expectation_acceptance_criteria.py
mcp_server/src/rook/agent/gh_scalar_transform_expectation_sources.py
mcp_server/src/rook/agent/local_worker_source_routing_validator.py
mcp_server/tests/test_gh_scalar_transform_expectation_acceptance_criteria.py
mcp_server/tests/test_gh_scalar_transform_expectation_sources.py
mcp_server/tests/test_lm8f_scalar_transform_depth_probe.py
mcp_server/tests/test_local_worker_source_routing_validator.py
scripts/lm8f_scalar_transform_depth_probe.py
```

No `probe_runs/` artifacts should be tracked.

- [ ] **Step 7: Commit Task 6**

```powershell
git add `
  scripts\lm8f_scalar_transform_depth_probe.py `
  mcp_server\src\rook\agent\gh_scalar_transform_expectation_sources.py `
  mcp_server\src\rook\agent\gh_scalar_transform_expectation_acceptance_criteria.py `
  mcp_server\src\rook\agent\local_worker_source_routing_validator.py `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py `
  mcp_server\tests\test_gh_scalar_transform_expectation_sources.py `
  mcp_server\tests\test_gh_scalar_transform_expectation_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py
git commit -m "test(lm8f): guard scalar transform live probe hygiene"
```

---

## Post-Merge Runbook

After implementation PR merge and sync to `main`, with Rhino and Grasshopper open:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe scripts\lm8f_scalar_transform_depth_probe.py
```

Inspect:

```powershell
$run = "C:\UDEV\Rook\probe_runs\<printed-lm8f-run-dir>"
Get-Content "$run\decision.json"
Get-Content "$run\fixture_setup_summary.json"
Get-Content "$run\scalar_sources.json"
Get-Content "$run\worker_publication_row.json" -ErrorAction SilentlyContinue
Get-Content "$run\worker_action.json" -ErrorAction SilentlyContinue
Get-Content "$run\live_set_value_summary.json" -ErrorAction SilentlyContinue
Get-Content "$run\verify_scalar_output_summary.json" -ErrorAction SilentlyContinue
Select-String -Path "$run\*.json" `
  -Pattern "PROBE_REPAIR_CODE","A = 42.0","BindStepSpec.base_params","repair_same_component.bind.base_params"
```

Canonical success read:

```text
decision = accepted
reason = verify_scalar_output_succeeded
scalar_runtime_ready = true
worker_publication_ran = true
live_set_value_dispatched = true
verify_scalar_output_ran = true
worker action = draft_gh_set_value_params {"value": 6.0-ish}
verify observed Addition R = 7.5 within 1e-9
```

If the worker publishes another value and the verifier rejects, keep the run as scalar-depth evidence. Do not replace the attempt without a reviewed follow-up slice.

---

## Self-Review

- Spec coverage:
  - Direct-tool fixture setup is covered in Task 3.
  - Static source routing and exact transform paths are covered in Task 1.
  - Transform source extraction and packet assembly are covered in Tasks 1 and 2.
  - Worker-visible request shape and no derived `6.0` are covered in Tasks 2 and 4.
  - Existing scalar applier reuse and no action-id autofill are covered in Task 5.
  - Verifier-floor Addition `R` acceptance is covered in Task 5.
  - GUID/artifact policy is covered in Tasks 3, 5, and 6.
  - No `gh_edit`, Planner, retry, LM8C mutation, or live run in PR is covered in global constraints and Task 6.

- Placeholder scan:
  - The plan contains no placeholder tokens, no open-ended validation steps, and every task has concrete tests, implementation targets, and commands.

- Type consistency:
  - Source dataclass and packet function names are consistent across Tasks 1, 2, and 4.
  - Script helper names used in tests are defined in Tasks 3 through 5.
  - Worker node/action ids stay `set_scalar_value` and `draft_gh_set_value_params`.
