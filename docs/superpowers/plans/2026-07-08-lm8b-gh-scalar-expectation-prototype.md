# LM8B GH Scalar Expectation Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic GH-native scalar expectation prototype promised by LM8A, without live Rhino/GH, model calls, worker publication, or protocol drift.

**Architecture:** LM8B adds a second-family source-routing/static validation surface, a GH-scalar-specific source extractor/assembler, and a narrow worker-action applier for `draft_gh_set_value_params`. It does not wire the family into Planner models, LM7E live scripts, generic workflow execution, or production `RookWorkflowContract` schema storage.

**Tech Stack:** Python 3.10, pytest, dataclasses, existing `PlanGraph` / `NodeEvidence` test fixtures, existing LM5AA validator style, existing LM6A worker-action applier style.

## Global Constraints

- Deterministic only.
- No live Rhino/GH.
- No model calls.
- No worker publication.
- No `gh_edit` batch.
- No wiring/topology repair.
- No script repair.
- No prompt changes.
- No retry or pull loop.
- No `PlannerWorkerContractRequest` schema changes.
- No `RookWorkflowContract` schema changes in LM8B.
- No broad router implementation.
- LM8B opens the GH scalar family; it does not claim GH scalar family
  readiness.
- After the first live GH scalar receipt, prefer same-family pressure before
  adding a third family.
- No package-level re-export from `rook.agent`.
- Expected scalar value authority is `expected_output_contract`.
- Observed scalar value authority is `receipt_observation`.
- Editable target contract authority is `fixture_anchor`.
- `fixture_anchor` is `evidence_context` only and must never feed `acceptance_criteria`.
- Trusted GUID is applier-only.
- Worker action input is exactly `{"value": number}`.
- The applier output params may include trusted `guid` and worker-authored `value`, but the worker must never provide `guid`.

---

## File Structure

Create:

- `mcp_server/src/rook/agent/gh_scalar_expectation_sources.py`
  - Owns the shared source dataclasses:
    `GhScalarExpectationSource` and `GhScalarExpectationSources`.
  - Owns exact-path extraction for LM8B deterministic source facts.
  - Consumes a mapping-shaped scalar expectation contract payload, a `PlanGraph`, and optional convention packets.
  - Produces `GhScalarExpectationSources`.

- `mcp_server/src/rook/agent/gh_scalar_expectation_acceptance_criteria.py`
  - Owns validation, packet assembly, and legacy worker-visible projection.
  - Imports and re-exports the source dataclasses from
    `gh_scalar_expectation_sources.py`.
  - Does not inspect graphs, contracts, files, or live tools.

- `mcp_server/src/rook/agent/plan_graph_gh_scalar_value_apply.py`
  - Owns copy-on-write staging of worker-authored scalar value plus trusted anchor GUID into `EXECUTION_PARAMS_KEY`.
  - Mirrors the fail-closed style of `plan_graph_worker_action_apply.py`, but remains separate.

- `mcp_server/tests/test_gh_scalar_expectation_sources.py`
  - Tests exact source extraction, fail-closed shape checks, and no hidden GUID leakage into visible source values.

- `mcp_server/tests/test_gh_scalar_expectation_acceptance_criteria.py`
  - Tests packet assembly, fingerprint stability, legacy projection, validation failures, and import boundaries.

- `mcp_server/tests/test_plan_graph_gh_scalar_value_apply.py`
  - Tests action validation, trusted anchor validation, staged params, copy-on-write, and import boundaries.

Modify:

- `mcp_server/src/rook/agent/local_worker_source_routing_validator.py`
  - Add LM8B static allowlist support for `expected_output_contract`, `receipt_observation`, and `fixture_anchor`.
  - Do not add LM8B routability to the LM5X resolver path in this task.

- `mcp_server/tests/test_local_worker_source_routing_validator.py`
  - Add static validation tests for LM8B route classes, source paths, and purpose compatibility.

Do not modify:

- `mcp_server/src/rook/agent/planner_worker_contract_request.py`
- `mcp_server/src/rook/agent/workflow_validate.py`
- `mcp_server/src/rook/agent/plan_graph_workflow_contract.py`
- `scripts/lm6a_live_worker_splice_probe.py`
- `scripts/lm7b_request_driven_live_splice_probe.py`
- `scripts/lm7e_model_authored_live_splice_probe.py`

---

### Task 1: Extend Static Source-Routing Validation For LM8B Classes

**Files:**
- Modify: `mcp_server/src/rook/agent/local_worker_source_routing_validator.py`
- Modify: `mcp_server/tests/test_local_worker_source_routing_validator.py`

**Interfaces:**
- Consumes: `validate_worker_visible_source_routing(artifact, ...)`
- Produces: Static validation support for:
  - `expected_output_contract`
  - `receipt_observation`
  - `fixture_anchor`

- [ ] **Step 1: Add failing tests for the LM8B route set**

Append these constants near the existing source-path constants in `mcp_server/tests/test_local_worker_source_routing_validator.py`:

```python
SCALAR_EXPECTED_OUTPUT_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_output.expected_output_value"
)
SCALAR_OBSERVED_OUTPUT_SOURCE_PATH = (
    "create_scalar_expectation.receipt.gh_receipt.observed_output_value"
)
SCALAR_FIXTURE_ANCHOR_SOURCE_PATH = (
    "create_scalar_expectation.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
SCALAR_CONVENTION_SOURCE_PATH = "gh_set_value_scalar_convention"
```

Add this helper near `_gh_pressure_artifact()`:

```python
def _gh_scalar_expectation_artifact(*, fixture_anchor_purpose="evidence_context"):
    return {
        "schema": SOURCE_ROUTING_SCHEMA,
        "routes": [
            {
                "node_id": "set_scalar_value",
                "visible_sources": [
                    {
                        "route_id": "scalar_expected_output_value",
                        "source_class": "expected_output_contract",
                        "source_path": SCALAR_EXPECTED_OUTPUT_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "scalar_current_output",
                        "source_class": "receipt_observation",
                        "source_path": SCALAR_OBSERVED_OUTPUT_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "scalar_editable_target_contract",
                        "source_class": "fixture_anchor",
                        "source_path": SCALAR_FIXTURE_ANCHOR_SOURCE_PATH,
                        "purpose": fixture_anchor_purpose,
                        "required": True,
                    },
                    {
                        "route_id": "scalar_set_value_convention",
                        "source_class": "convention",
                        "source_path": SCALAR_CONVENTION_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": False,
                    },
                ],
            }
        ],
    }
```

Add these tests:

```python
def test_gh_scalar_expectation_routes_are_static_valid():
    report = validate_worker_visible_source_routing(_gh_scalar_expectation_artifact())

    assert report.valid is True
    assert report.routability_evaluated is False
    assert report.static_diagnostics == ()
    assert report.routability_diagnostics == ()


def test_fixture_anchor_cannot_feed_acceptance_criteria():
    report = validate_worker_visible_source_routing(
        _gh_scalar_expectation_artifact(fixture_anchor_purpose="acceptance_criteria")
    )

    assert report.valid is False
    assert [
        (diagnostic.code, diagnostic.source_class, diagnostic.purpose)
        for diagnostic in report.static_diagnostics
    ] == [("invalid_source_purpose", "fixture_anchor", "acceptance_criteria")]


def test_gh_scalar_source_paths_are_class_keyed():
    artifact = _gh_scalar_expectation_artifact()
    artifact["routes"][0]["visible_sources"][0] = {
        "route_id": "wrong_class_expected_value",
        "source_class": "receipt_observation",
        "source_path": SCALAR_EXPECTED_OUTPUT_SOURCE_PATH,
        "purpose": "acceptance_criteria",
        "required": True,
    }

    report = validate_worker_visible_source_routing(artifact)

    assert report.valid is False
    assert [
        diagnostic.code
        for diagnostic in report.static_diagnostics
        if diagnostic.route_id == "wrong_class_expected_value"
    ] == ["invalid_source_path"]
```

- [ ] **Step 2: Run the failing validator tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q
```

Expected before implementation: failures with `unknown_source_class` for `expected_output_contract`, `receipt_observation`, and `fixture_anchor`.

- [ ] **Step 3: Add the static allowlists**

In `mcp_server/src/rook/agent/local_worker_source_routing_validator.py`, add constants near the existing source path constants:

```python
SCALAR_EXPECTED_OUTPUT_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_output.expected_output_value"
)
SCALAR_OBSERVED_OUTPUT_SOURCE_PATH = (
    "create_scalar_expectation.receipt.gh_receipt.observed_output_value"
)
SCALAR_FIXTURE_ANCHOR_SOURCE_PATH = (
    "create_scalar_expectation.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
SCALAR_CONVENTION_SOURCE_PATH = "gh_set_value_scalar_convention"
```

Extend `_SOURCE_CLASSES`:

```python
_SOURCE_CLASSES = (
    "pin_contract",
    "verifier_outcome",
    "receipt_diagnostic",
    "convention",
    "planner_user_intent",
    "expected_output_contract",
    "receipt_observation",
    "fixture_anchor",
)
```

Extend `_SOURCE_PURPOSES`:

```python
    "expected_output_contract": ("acceptance_criteria", "evidence_context"),
    "receipt_observation": ("acceptance_criteria", "evidence_context"),
    "fixture_anchor": ("evidence_context",),
```

Extend `_ALLOWED_SOURCE_PATHS`:

```python
    "expected_output_contract": (SCALAR_EXPECTED_OUTPUT_SOURCE_PATH,),
    "receipt_observation": (SCALAR_OBSERVED_OUTPUT_SOURCE_PATH,),
    "fixture_anchor": (SCALAR_FIXTURE_ANCHOR_SOURCE_PATH,),
```

Add `SCALAR_CONVENTION_SOURCE_PATH` to the existing `convention` tuple:

```python
    "convention": (
        CONVENTION_SOURCE_PATH,
        "grasshopper_definition_style_convention",
        SCALAR_CONVENTION_SOURCE_PATH,
    ),
```

Do not add these LM8B paths to `_LM5X_SOURCE_PATHS`. LM8B routability is not part of the LM5X extraction seam.

- [ ] **Step 4: Run validator tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q
```

Expected: all tests in the file pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add `
  mcp_server\src\rook\agent\local_worker_source_routing_validator.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py
git commit -m "feat: add LM8 scalar routing classes"
```

---

### Task 2: Add GH Scalar Source Extraction

**Files:**
- Create: `mcp_server/src/rook/agent/gh_scalar_expectation_sources.py`
- Create: `mcp_server/tests/test_gh_scalar_expectation_sources.py`

**Interfaces:**
- Produces:
  - `GhScalarExpectationSource`
  - `GhScalarExpectationSources`
  - `EXPECTED_OUTPUT_SOURCE_PATH: str`
  - `OBSERVED_OUTPUT_SOURCE_PATH: str`
  - `FIXTURE_ANCHOR_SOURCE_PATH: str`
  - `CONVENTION_SOURCE_PATH: str`
  - `extract_gh_scalar_expectation_sources(...) -> GhScalarExpectationSources`

- [ ] **Step 1: Write failing extraction tests**

Create `mcp_server/tests/test_gh_scalar_expectation_sources.py`:

```python
import ast
import inspect

import pytest

from rook.agent.gh_scalar_expectation_sources import (
    CONVENTION_SOURCE_PATH,
    EXPECTED_OUTPUT_SOURCE_PATH,
    FIXTURE_ANCHOR_SOURCE_PATH,
    OBSERVED_OUTPUT_SOURCE_PATH,
    extract_gh_scalar_expectation_sources,
)
from rook.agent.local_worker_turn_context import WorkerKnowledgePacket
from rook.learning.plan_graph import GraphMemory, NodeEvidence, PlanGraph, PlanGraphNode


def _contract_payload(expected_value=7.5):
    return {
        "rules": {
            "verify_scalar_output": {
                "expected_output_value": expected_value,
            }
        }
    }


def _graph(*, observed_value=0.0, editable_contract=None, guid="GUID-1"):
    editable_contract = editable_contract or {
        "label": "Target scalar value",
        "value_type": "number",
        "current_value": observed_value,
        "identity_projection": True,
    }
    receipt = {
        "observed_output_value": observed_value,
        "scalar_anchor": {
            "component_guid": guid,
            "editable_value_contract": editable_contract,
        },
    }
    return PlanGraph(
        nodes={
            "create_scalar_expectation": PlanGraphNode(
                id="create_scalar_expectation",
                intent="create scalar expectation",
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
        packet_id="gh_set_value_scalar_convention",
        kind="convention",
        title="GH scalar values are changed with gh_set_value",
        content={"action_id": "draft_gh_set_value_params"},
    )


def test_extracts_all_scalar_sources_without_guid_in_visible_anchor():
    sources = extract_gh_scalar_expectation_sources(
        workflow_contract_payload=_contract_payload(expected_value=7.5),
        graph=_graph(observed_value=0.0),
        convention_packets=(_convention_packet(),),
    )

    assert sources.expected_output_contract.source_class == "expected_output_contract"
    assert sources.expected_output_contract.source_path == EXPECTED_OUTPUT_SOURCE_PATH
    assert sources.expected_output_contract.value == 7.5
    assert sources.receipt_observation.source_class == "receipt_observation"
    assert sources.receipt_observation.source_path == OBSERVED_OUTPUT_SOURCE_PATH
    assert sources.receipt_observation.value == 0.0
    assert sources.fixture_anchor.source_class == "fixture_anchor"
    assert sources.fixture_anchor.source_path == FIXTURE_ANCHOR_SOURCE_PATH
    assert sources.fixture_anchor.value == {
        "label": "Target scalar value",
        "value_type": "number",
        "current_value": 0.0,
        "identity_projection": True,
    }
    assert sources.convention is not None
    assert sources.convention.source_class == "convention"
    assert sources.convention.source_path == CONVENTION_SOURCE_PATH
    assert "GUID-1" not in repr(sources.fixture_anchor.value)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "7.5", True])
def test_expected_output_value_must_be_finite_number(bad_value):
    with pytest.raises(ValueError, match=EXPECTED_OUTPUT_SOURCE_PATH):
        extract_gh_scalar_expectation_sources(
            workflow_contract_payload=_contract_payload(expected_value=bad_value),
            graph=_graph(),
            convention_packets=(),
        )


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "0.0", False])
def test_observed_output_value_must_be_finite_number(bad_value):
    with pytest.raises(ValueError, match=OBSERVED_OUTPUT_SOURCE_PATH):
        extract_gh_scalar_expectation_sources(
            workflow_contract_payload=_contract_payload(),
            graph=_graph(observed_value=bad_value),
            convention_packets=(),
        )


def test_missing_observed_output_fails_closed():
    graph = _graph()
    graph.nodes["create_scalar_expectation"].evidence.receipt.pop(
        "observed_output_value"
    )

    with pytest.raises(ValueError, match=OBSERVED_OUTPUT_SOURCE_PATH):
        extract_gh_scalar_expectation_sources(
            workflow_contract_payload=_contract_payload(),
            graph=graph,
            convention_packets=(),
        )


def test_missing_fixture_anchor_contract_fails_closed():
    graph = _graph()
    graph.nodes["create_scalar_expectation"].evidence.receipt["scalar_anchor"].pop(
        "editable_value_contract"
    )

    with pytest.raises(ValueError, match=FIXTURE_ANCHOR_SOURCE_PATH):
        extract_gh_scalar_expectation_sources(
            workflow_contract_payload=_contract_payload(),
            graph=graph,
            convention_packets=(),
        )


def test_extractor_import_boundary_stays_narrow():
    import rook.agent.gh_scalar_expectation_sources as module

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
        "scripts.lm7e_model_authored_live_splice_probe",
        "scripts.lm7b_request_driven_live_splice_probe",
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

- [ ] **Step 2: Run the failing extraction tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_gh_scalar_expectation_sources.py `
  -q
```

Expected before implementation: import failure for `rook.agent.gh_scalar_expectation_sources`.

- [ ] **Step 3: Implement the extraction module**

Create `mcp_server/src/rook/agent/gh_scalar_expectation_sources.py`:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

from rook.agent.local_worker_turn_context import WorkerKnowledgePacket
from rook.learning.plan_graph import PlanGraph


EXPECTED_OUTPUT_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_output.expected_output_value"
)
OBSERVED_OUTPUT_SOURCE_PATH = (
    "create_scalar_expectation.receipt.gh_receipt.observed_output_value"
)
FIXTURE_ANCHOR_SOURCE_PATH = (
    "create_scalar_expectation.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
CONVENTION_SOURCE_PATH = "gh_set_value_scalar_convention"


@dataclass(frozen=True)
class GhScalarExpectationSource:
    source_class: str
    source_path: str
    value: Any


@dataclass(frozen=True)
class GhScalarExpectationSources:
    expected_output_contract: GhScalarExpectationSource
    receipt_observation: GhScalarExpectationSource
    fixture_anchor: GhScalarExpectationSource
    convention: GhScalarExpectationSource | None = None


def extract_gh_scalar_expectation_sources(
    *,
    workflow_contract_payload: Mapping[str, Any],
    graph: PlanGraph,
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> GhScalarExpectationSources:
    return GhScalarExpectationSources(
        expected_output_contract=GhScalarExpectationSource(
            source_class="expected_output_contract",
            source_path=EXPECTED_OUTPUT_SOURCE_PATH,
            value=_expected_output_value(workflow_contract_payload),
        ),
        receipt_observation=GhScalarExpectationSource(
            source_class="receipt_observation",
            source_path=OBSERVED_OUTPUT_SOURCE_PATH,
            value=_observed_output_value(graph),
        ),
        fixture_anchor=GhScalarExpectationSource(
            source_class="fixture_anchor",
            source_path=FIXTURE_ANCHOR_SOURCE_PATH,
            value=_editable_value_contract(graph),
        ),
        convention=_convention_source(convention_packets),
    )


def _expected_output_value(payload: Mapping[str, Any]) -> float | int:
    rules = payload.get("rules")
    if not isinstance(rules, Mapping):
        raise ValueError(f"{EXPECTED_OUTPUT_SOURCE_PATH} rules missing")
    verify = rules.get("verify_scalar_output")
    if not isinstance(verify, Mapping):
        raise ValueError(f"{EXPECTED_OUTPUT_SOURCE_PATH} rule missing")
    return _finite_number(verify.get("expected_output_value"), EXPECTED_OUTPUT_SOURCE_PATH)


def _receipt(graph: PlanGraph) -> Mapping[str, Any]:
    if "create_scalar_expectation" not in graph.nodes:
        raise ValueError(f"{OBSERVED_OUTPUT_SOURCE_PATH} node missing")
    evidence = graph.nodes["create_scalar_expectation"].evidence
    if evidence is None or not isinstance(evidence.receipt, Mapping):
        raise ValueError(f"{OBSERVED_OUTPUT_SOURCE_PATH} receipt missing")
    return evidence.receipt


def _observed_output_value(graph: PlanGraph) -> float | int:
    return _finite_number(_receipt(graph).get("observed_output_value"), OBSERVED_OUTPUT_SOURCE_PATH)


def _editable_value_contract(graph: PlanGraph) -> dict[str, Any]:
    receipt = _receipt(graph)
    anchor = receipt.get("scalar_anchor")
    if not isinstance(anchor, Mapping):
        raise ValueError(f"{FIXTURE_ANCHOR_SOURCE_PATH} scalar_anchor missing")
    contract = anchor.get("editable_value_contract")
    if not isinstance(contract, Mapping):
        raise ValueError(f"{FIXTURE_ANCHOR_SOURCE_PATH} missing")
    copied = dict(contract)
    if "component_guid" in copied or "guid" in copied:
        raise ValueError(f"{FIXTURE_ANCHOR_SOURCE_PATH} must not expose guid")
    return copied


def _convention_source(
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> GhScalarExpectationSource | None:
    matches = [
        packet
        for packet in convention_packets
        if getattr(packet, "packet_id", None) == CONVENTION_SOURCE_PATH
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"{CONVENTION_SOURCE_PATH} ambiguous")
    packet = matches[0]
    return GhScalarExpectationSource(
        source_class="convention",
        source_path=CONVENTION_SOURCE_PATH,
        value=dict(packet.content) if isinstance(packet.content, Mapping) else packet.content,
    )


def _finite_number(value: Any, source_path: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{source_path} must be a finite number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{source_path} must be a finite number")
    return value


__all__ = (
    "GhScalarExpectationSource",
    "GhScalarExpectationSources",
    "EXPECTED_OUTPUT_SOURCE_PATH",
    "OBSERVED_OUTPUT_SOURCE_PATH",
    "FIXTURE_ANCHOR_SOURCE_PATH",
    "CONVENTION_SOURCE_PATH",
    "extract_gh_scalar_expectation_sources",
)
```

- [ ] **Step 4: Run extraction tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_gh_scalar_expectation_sources.py `
  -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add `
  mcp_server\src\rook\agent\gh_scalar_expectation_sources.py `
  mcp_server\tests\test_gh_scalar_expectation_sources.py
git commit -m "feat: add GH scalar expectation sources"
```

---

### Task 3: Add GH Scalar Acceptance Criteria Assembly

**Files:**
- Create: `mcp_server/src/rook/agent/gh_scalar_expectation_acceptance_criteria.py`
- Create: `mcp_server/tests/test_gh_scalar_expectation_acceptance_criteria.py`
- Test: `mcp_server/tests/test_gh_scalar_expectation_sources.py`

**Interfaces:**
- Produces:
  - `GH_SCALAR_EXPECTATION_PACKET_SCHEMA`
  - `assemble_gh_scalar_expectation_packet(sources)`
  - `project_gh_scalar_expectation_legacy(packet)`
- Consumes:
  - `GhScalarExpectationSource` from Task 2
  - `GhScalarExpectationSources` from Task 2
  - Source constants from Task 2

- [ ] **Step 1: Write failing assembler tests**

Create `mcp_server/tests/test_gh_scalar_expectation_acceptance_criteria.py`:

```python
import ast
import hashlib
import inspect
import json

import pytest

from rook.agent import gh_scalar_expectation_acceptance_criteria as module
from rook.agent.gh_scalar_expectation_acceptance_criteria import (
    GH_SCALAR_EXPECTATION_PACKET_SCHEMA,
    GhScalarExpectationSource,
    GhScalarExpectationSources,
    assemble_gh_scalar_expectation_packet,
    project_gh_scalar_expectation_legacy,
)


EXPECTED_PATH = "workflow_contract.rules.verify_scalar_output.expected_output_value"
OBSERVED_PATH = "create_scalar_expectation.receipt.gh_receipt.observed_output_value"
ANCHOR_PATH = (
    "create_scalar_expectation.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
CONVENTION_PATH = "gh_set_value_scalar_convention"


def _valid_sources(**overrides):
    values = {
        "expected_output_contract": GhScalarExpectationSource(
            source_class="expected_output_contract",
            source_path=EXPECTED_PATH,
            value=7.5,
        ),
        "receipt_observation": GhScalarExpectationSource(
            source_class="receipt_observation",
            source_path=OBSERVED_PATH,
            value=0.0,
        ),
        "fixture_anchor": GhScalarExpectationSource(
            source_class="fixture_anchor",
            source_path=ANCHOR_PATH,
            value={
                "label": "Target scalar value",
                "value_type": "number",
                "current_value": 0.0,
                "identity_projection": True,
            },
        ),
        "convention": GhScalarExpectationSource(
            source_class="convention",
            source_path=CONVENTION_PATH,
            value={"action_id": "draft_gh_set_value_params"},
        ),
    }
    values.update(overrides)
    return GhScalarExpectationSources(**values)


def _without_fingerprint(packet):
    copied = dict(packet)
    copied.pop("fingerprint")
    return copied


def test_public_surface():
    assert module.__all__ == (
        "GH_SCALAR_EXPECTATION_PACKET_SCHEMA",
        "GhScalarExpectationSource",
        "GhScalarExpectationSources",
        "assemble_gh_scalar_expectation_packet",
        "project_gh_scalar_expectation_legacy",
    )
    assert GH_SCALAR_EXPECTATION_PACKET_SCHEMA == "rook.gh_scalar_expectation_packet:v1"


def test_assembles_scalar_expectation_packet():
    packet = assemble_gh_scalar_expectation_packet(_valid_sources())

    assert packet["schema"] == GH_SCALAR_EXPECTATION_PACKET_SCHEMA
    assert packet["source_set"] == {
        "source_classes": [
            "convention",
            "expected_output_contract",
            "fixture_anchor",
            "receipt_observation",
        ],
        "source_paths": sorted([
            CONVENTION_PATH,
            ANCHOR_PATH,
            OBSERVED_PATH,
            EXPECTED_PATH,
        ]),
    }
    assert packet["fields"] == {
        "current_observed_output": 0.0,
        "expected_output_value": 7.5,
        "editable_value_contract": {
            "label": "Target scalar value",
            "value_type": "number",
            "current_value": 0.0,
            "identity_projection": True,
        },
        "recommended_action_id": "draft_gh_set_value_params",
        "acceptance_criteria": {
            "source": "gh_scalar_expectation",
            "criteria": [
                {
                    "criterion_id": "set_scalar_to_match_expected_output",
                    "description": "Set the editable scalar value to the source-owned expected output value.",
                    "source": EXPECTED_PATH,
                },
                {
                    "criterion_id": "identity_projection_output_matches_value",
                    "description": "In this v1 fixture, the editable scalar value is the inspected output value.",
                    "source": OBSERVED_PATH,
                },
            ],
        },
    }
    assert [criterion["source_class"] for criterion in packet["criteria"]] == [
        "expected_output_contract",
        "receipt_observation",
    ]
    assert "component_guid" not in json.dumps(packet, sort_keys=True)
    assert packet["fingerprint"].startswith("sha256:")


def test_legacy_projection_excludes_schema_source_set_and_fingerprint():
    packet = assemble_gh_scalar_expectation_packet(_valid_sources())

    projection = project_gh_scalar_expectation_legacy(packet)

    assert projection == packet["fields"]["acceptance_criteria"]
    rendered = json.dumps(projection, sort_keys=True)
    for forbidden in ("schema", "source_set", "source_class", "fingerprint"):
        assert forbidden not in rendered


def test_fingerprint_matches_canonical_packet_without_fingerprint():
    packet = assemble_gh_scalar_expectation_packet(_valid_sources())

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
        assemble_gh_scalar_expectation_packet(
            _valid_sources(
                expected_output_contract=GhScalarExpectationSource(
                    source_class="expected_output_contract",
                    source_path=EXPECTED_PATH,
                    value=bad_value,
                )
            )
        )


def test_fixture_anchor_cannot_contain_guid_or_feed_criteria():
    with pytest.raises(ValueError, match="fixture_anchor"):
        assemble_gh_scalar_expectation_packet(
            _valid_sources(
                fixture_anchor=GhScalarExpectationSource(
                    source_class="fixture_anchor",
                    source_path=ANCHOR_PATH,
                    value={
                        "label": "Target scalar value",
                        "value_type": "number",
                        "current_value": 0.0,
                        "identity_projection": True,
                        "component_guid": "GUID-1",
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
        "lm7e_model_authored_live_splice_probe",
        "LiteLLM",
        "yaml",
    )
    for fragment in forbidden_import_fragments:
        assert not any(fragment in imported for imported in imports)
    assert "base_params" not in source
```

- [ ] **Step 2: Run failing assembler tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_gh_scalar_expectation_acceptance_criteria.py `
  -q
```

Expected before implementation: import failure for `rook.agent.gh_scalar_expectation_acceptance_criteria`.

- [ ] **Step 3: Implement the assembler module**

Create `mcp_server/src/rook/agent/gh_scalar_expectation_acceptance_criteria.py`:

```python
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from rook.agent.gh_scalar_expectation_sources import (
    CONVENTION_SOURCE_PATH,
    EXPECTED_OUTPUT_SOURCE_PATH,
    FIXTURE_ANCHOR_SOURCE_PATH,
    OBSERVED_OUTPUT_SOURCE_PATH,
    GhScalarExpectationSource,
    GhScalarExpectationSources,
)


GH_SCALAR_EXPECTATION_PACKET_SCHEMA = "rook.gh_scalar_expectation_packet:v1"


def assemble_gh_scalar_expectation_packet(
    sources: GhScalarExpectationSources,
) -> dict[str, Any]:
    _validate_sources(sources)
    source_classes = {
        sources.expected_output_contract.source_class,
        sources.receipt_observation.source_class,
        sources.fixture_anchor.source_class,
    }
    source_paths = {
        sources.expected_output_contract.source_path,
        sources.receipt_observation.source_path,
        sources.fixture_anchor.source_path,
    }
    if sources.convention is not None:
        source_classes.add(sources.convention.source_class)
        source_paths.add(sources.convention.source_path)

    criteria = [
        {
            "criterion_id": "set_scalar_to_match_expected_output",
            "description": "Set the editable scalar value to the source-owned expected output value.",
            "source": sources.expected_output_contract.source_path,
            "source_class": sources.expected_output_contract.source_class,
        },
        {
            "criterion_id": "identity_projection_output_matches_value",
            "description": "In this v1 fixture, the editable scalar value is the inspected output value.",
            "source": sources.receipt_observation.source_path,
            "source_class": sources.receipt_observation.source_class,
        },
    ]
    acceptance_criteria = {
        "source": "gh_scalar_expectation",
        "criteria": [
            {
                "criterion_id": criterion["criterion_id"],
                "description": criterion["description"],
                "source": criterion["source"],
            }
            for criterion in criteria
        ],
    }
    packet = {
        "schema": GH_SCALAR_EXPECTATION_PACKET_SCHEMA,
        "source_set": {
            "source_classes": sorted(source_classes),
            "source_paths": sorted(source_paths),
        },
        "criteria": criteria,
        "fields": {
            "current_observed_output": sources.receipt_observation.value,
            "expected_output_value": sources.expected_output_contract.value,
            "editable_value_contract": dict(sources.fixture_anchor.value),
            "recommended_action_id": "draft_gh_set_value_params",
            "acceptance_criteria": acceptance_criteria,
        },
    }
    canonical_packet = json.dumps(packet, sort_keys=True, separators=(",", ":"))
    packet["fingerprint"] = (
        f"sha256:{hashlib.sha256(canonical_packet.encode('utf-8')).hexdigest()}"
    )
    return packet


def project_gh_scalar_expectation_legacy(packet: dict[str, Any]) -> dict[str, Any]:
    fields = packet.get("fields")
    if not isinstance(fields, dict):
        raise ValueError("GH scalar packet fields missing")
    acceptance_criteria = fields.get("acceptance_criteria")
    if not isinstance(acceptance_criteria, dict):
        raise ValueError("GH scalar acceptance_criteria missing")
    return {
        "source": acceptance_criteria["source"],
        "criteria": [dict(item) for item in acceptance_criteria["criteria"]],
    }


def _validate_sources(sources: GhScalarExpectationSources) -> None:
    _validate_source(
        sources.expected_output_contract,
        source_class="expected_output_contract",
        source_path=EXPECTED_OUTPUT_SOURCE_PATH,
    )
    _validate_source(
        sources.receipt_observation,
        source_class="receipt_observation",
        source_path=OBSERVED_OUTPUT_SOURCE_PATH,
    )
    _validate_source(
        sources.fixture_anchor,
        source_class="fixture_anchor",
        source_path=FIXTURE_ANCHOR_SOURCE_PATH,
    )
    if sources.convention is not None:
        _validate_source(
            sources.convention,
            source_class="convention",
            source_path=CONVENTION_SOURCE_PATH,
        )
    _finite_number(sources.expected_output_contract.value, "expected_output_contract")
    _finite_number(sources.receipt_observation.value, "receipt_observation")
    _validate_fixture_anchor(sources.fixture_anchor.value)


def _validate_source(
    source: GhScalarExpectationSource,
    *,
    source_class: str,
    source_path: str,
) -> None:
    if source.source_class != source_class:
        raise ValueError(f"expected source class {source_class!r}.")
    if source.source_path != source_path:
        raise ValueError(f"expected source path {source_path!r}.")


def _finite_number(value: Any, context: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} value must be a finite number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{context} value must be a finite number")


def _validate_fixture_anchor(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("fixture_anchor value must be a mapping")
    if "guid" in value or "component_guid" in value:
        raise ValueError("fixture_anchor value must not contain a guid")
    required = {
        "label",
        "value_type",
        "current_value",
        "identity_projection",
    }
    if set(value) != required:
        raise ValueError("fixture_anchor value has invalid fields")
    if not isinstance(value["label"], str) or not value["label"]:
        raise ValueError("fixture_anchor label must be non-empty")
    if value["value_type"] != "number":
        raise ValueError("fixture_anchor value_type must be number")
    _finite_number(value["current_value"], "fixture_anchor.current_value")
    if value["identity_projection"] is not True:
        raise ValueError("fixture_anchor identity_projection must be true")


__all__ = (
    "GH_SCALAR_EXPECTATION_PACKET_SCHEMA",
    "GhScalarExpectationSource",
    "GhScalarExpectationSources",
    "assemble_gh_scalar_expectation_packet",
    "project_gh_scalar_expectation_legacy",
)
```

- [ ] **Step 4: Run assembler and extraction tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_gh_scalar_expectation_acceptance_criteria.py `
  mcp_server\tests\test_gh_scalar_expectation_sources.py `
  -q
```

Expected: both new test files pass.

- [ ] **Step 5: Commit Task 3**

```powershell
git add `
  mcp_server\src\rook\agent\gh_scalar_expectation_acceptance_criteria.py `
  mcp_server\tests\test_gh_scalar_expectation_acceptance_criteria.py
git commit -m "feat: add GH scalar expectation criteria"
```

---

### Task 4: Add GH Scalar Worker-Action Applier

**Files:**
- Create: `mcp_server/src/rook/agent/plan_graph_gh_scalar_value_apply.py`
- Create: `mcp_server/tests/test_plan_graph_gh_scalar_value_apply.py`

**Interfaces:**
- Produces:
  - `GhScalarValueApplyResult`
  - `apply_gh_scalar_value_action_to_node(...)`

- [ ] **Step 1: Write failing applier tests**

Create `mcp_server/tests/test_plan_graph_gh_scalar_value_apply.py`:

```python
import ast
import math
import pathlib
from types import MappingProxyType

from rook.agent.plan_graph_gh_scalar_value_apply import (
    GhScalarValueApplyResult,
    apply_gh_scalar_value_action_to_node,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.learning.plan_graph import GraphMemory, PlanGraph, PlanGraphNode


ACTION_ID = "draft_gh_set_value_params"
NODE_ID = "set_scalar_value"


class _NoDeepcopy:
    def __deepcopy__(self, memo):
        raise RuntimeError("no copy")


def _node(node_id: str, **metadata):
    return PlanGraphNode(id=node_id, intent="x", metadata=dict(metadata))


def _graph(nodes):
    return PlanGraph(nodes={node.id: node for node in nodes}, memory=GraphMemory())


def _valid_action_input():
    return {"value": 7.5}


def _valid_anchor():
    return {"component_guid": "GUID-1"}


def _apply(graph, *, action_id=ACTION_ID, action_input=None, anchor_binding=None):
    return apply_gh_scalar_value_action_to_node(
        graph,
        NODE_ID,
        action_id=action_id,
        action_input=_valid_action_input() if action_input is None else action_input,
        anchor_binding=_valid_anchor() if anchor_binding is None else anchor_binding,
    )


def _assert_rejected(result, graph, reason):
    assert result.applied is False
    assert result.reason == reason
    assert result.graph is graph
    assert result.params_sha256 is None
    assert EXECUTION_PARAMS_KEY not in graph.nodes[NODE_ID].metadata


def test_success_stages_gh_set_value_params_copy_on_write():
    graph = _graph([_node(NODE_ID)])

    result = _apply(graph)

    assert isinstance(result, GhScalarValueApplyResult)
    assert result.applied is True
    assert result.reason is None
    assert result.graph is not graph
    assert result.params_sha256 is not None
    assert EXECUTION_PARAMS_KEY not in graph.nodes[NODE_ID].metadata
    assert result.graph.nodes[NODE_ID].metadata[EXECUTION_PARAMS_KEY] == {
        "guid": "GUID-1",
        "value": 7.5,
    }


def test_accepts_non_dict_mappings_without_aliasing():
    action_input = {"value": 7.5}
    anchor = {"component_guid": "GUID-1"}
    graph = _graph([_node(NODE_ID)])

    result = apply_gh_scalar_value_action_to_node(
        graph,
        NODE_ID,
        action_id=ACTION_ID,
        action_input=MappingProxyType(action_input),
        anchor_binding=MappingProxyType(anchor),
    )

    action_input["value"] = 0.0
    anchor["component_guid"] = "MUTATED"
    assert result.graph.nodes[NODE_ID].metadata[EXECUTION_PARAMS_KEY] == {
        "guid": "GUID-1",
        "value": 7.5,
    }


def test_invalid_action_id_and_unknown_node_reject():
    graph = _graph([_node(NODE_ID)])

    invalid_action = _apply(graph, action_id="other")
    unknown_node = apply_gh_scalar_value_action_to_node(
        graph,
        "missing",
        action_id=ACTION_ID,
        action_input=_valid_action_input(),
        anchor_binding=_valid_anchor(),
    )

    _assert_rejected(invalid_action, graph, "invalid_action_id")
    assert unknown_node.reason == "unknown_node"
    assert unknown_node.graph is graph


def test_action_input_validation_rejects_extra_keys_guid_and_non_numbers():
    graph = _graph([_node(NODE_ID)])

    cases = [
        (["bad"], "invalid_action_input"),
        ({}, "missing_value"),
        ({"value": "7.5"}, "invalid_value"),
        ({"value": True}, "invalid_value"),
        ({"value": math.inf}, "invalid_value"),
        ({"value": 7.5, "guid": "BAD"}, "unexpected_action_input_key"),
        ({"value": 7.5, "tool_name": "gh_set_value"}, "unexpected_action_input_key"),
    ]

    for action_input, reason in cases:
        result = _apply(graph, action_input=action_input)
        _assert_rejected(result, graph, reason)


def test_anchor_validation_rejects_extra_keys_and_missing_guid():
    graph = _graph([_node(NODE_ID)])

    cases = [
        (["bad"], "invalid_anchor_binding"),
        ({}, "missing_component_guid"),
        ({"component_guid": ""}, "invalid_component_guid"),
        ({"component_guid": 123}, "invalid_component_guid"),
        ({"component_guid": "GUID-1", "value": 7.5}, "unexpected_anchor_binding_key"),
    ]

    for anchor, reason in cases:
        result = _apply(graph, anchor_binding=anchor)
        _assert_rejected(result, graph, reason)


def test_graph_copy_failed_rejects():
    graph = _graph([_node(NODE_ID), _node("other", bad=_NoDeepcopy())])

    result = _apply(graph)

    _assert_rejected(result, graph, "graph_copy_failed")


def test_applier_import_boundary():
    import rook.agent.plan_graph_gh_scalar_value_apply as module

    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")

    forbidden = {
        "rook.agent.plan_graph_param_apply",
        "BindStepSpec",
        "rook.server",
        "yaml",
    }
    assert imports.isdisjoint(forbidden)
    assert "base_params" not in source
    assert "gh_edit" not in source
    assert "code" not in source
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "base_params"
        for node in ast.walk(tree)
    )
```

- [ ] **Step 2: Run failing applier tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph_gh_scalar_value_apply.py `
  -q
```

Expected before implementation: import failure for `rook.agent.plan_graph_gh_scalar_value_apply`.

- [ ] **Step 3: Implement the applier module**

Create `mcp_server/src/rook/agent/plan_graph_gh_scalar_value_apply.py`:

```python
"""Stage GH scalar value params from a worker action onto one plan-graph node."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY


_ACTION_INPUT_KEYS = {"value"}
_ANCHOR_BINDING_KEYS = {"component_guid"}


@dataclass(frozen=True)
class GhScalarValueApplyResult:
    graph: Any
    applied: bool
    node_id: str
    reason: str | None
    params_sha256: str | None


def apply_gh_scalar_value_action_to_node(
    graph: Any,
    node_id: str,
    *,
    action_id: str,
    action_input: Mapping[str, Any],
    anchor_binding: Mapping[str, Any],
    allowed_action_id: str = "draft_gh_set_value_params",
) -> GhScalarValueApplyResult:
    if node_id not in graph.nodes:
        return _reject(graph, node_id, "unknown_node")
    if action_id != allowed_action_id:
        return _reject(graph, node_id, "invalid_action_id")

    action_reason = _validate_action_input(action_input)
    if action_reason is not None:
        return _reject(graph, node_id, action_reason)

    anchor_reason = _validate_anchor_binding(anchor_binding)
    if anchor_reason is not None:
        return _reject(graph, node_id, anchor_reason)

    params = {
        "guid": anchor_binding["component_guid"],
        "value": action_input["value"],
    }
    try:
        new_graph = deepcopy(graph)
    except Exception:
        return _reject(graph, node_id, "graph_copy_failed")

    new_graph.nodes[node_id].metadata[EXECUTION_PARAMS_KEY] = dict(params)
    return GhScalarValueApplyResult(
        graph=new_graph,
        applied=True,
        node_id=node_id,
        reason=None,
        params_sha256=_params_sha256(params),
    )


def _reject(graph: Any, node_id: str, reason: str) -> GhScalarValueApplyResult:
    return GhScalarValueApplyResult(
        graph=graph,
        applied=False,
        node_id=node_id,
        reason=reason,
        params_sha256=None,
    )


def _validate_action_input(action_input: Any) -> str | None:
    if not isinstance(action_input, Mapping):
        return "invalid_action_input"
    if set(action_input) - _ACTION_INPUT_KEYS:
        return "unexpected_action_input_key"
    if "value" not in action_input:
        return "missing_value"
    value = action_input["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "invalid_value"
    if isinstance(value, float) and not math.isfinite(value):
        return "invalid_value"
    return None


def _validate_anchor_binding(anchor_binding: Any) -> str | None:
    if not isinstance(anchor_binding, Mapping):
        return "invalid_anchor_binding"
    if set(anchor_binding) - _ANCHOR_BINDING_KEYS:
        return "unexpected_anchor_binding_key"
    if "component_guid" not in anchor_binding:
        return "missing_component_guid"
    component_guid = anchor_binding["component_guid"]
    if not isinstance(component_guid, str) or not component_guid.strip():
        return "invalid_component_guid"
    return None


def _params_sha256(params: Mapping[str, Any]) -> str:
    encoded = json.dumps(params, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
```

- [ ] **Step 4: Run applier tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph_gh_scalar_value_apply.py `
  -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add `
  mcp_server\src\rook\agent\plan_graph_gh_scalar_value_apply.py `
  mcp_server\tests\test_plan_graph_gh_scalar_value_apply.py
git commit -m "feat: add GH scalar value action applier"
```

---

### Task 5: Boundary And Nearby Seam Verification

**Files:**
- No planned file changes. If a verification command fails, patch only the file
  named by that failing test or guard, then rerun the exact failing command
  before continuing.

**Interfaces:**
- Consumes all public modules created above.
- Produces a clean deterministic verification record.

- [ ] **Step 1: Run focused LM8B tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  mcp_server\tests\test_gh_scalar_expectation_acceptance_criteria.py `
  mcp_server\tests\test_gh_scalar_expectation_sources.py `
  mcp_server\tests\test_plan_graph_gh_scalar_value_apply.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run nearby seam tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  mcp_server\tests\test_plan_graph_workflow_contract.py `
  mcp_server\tests\test_workflow_validate.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run Python 3.10 compile gate**

Run:

```powershell
py -3.10 -m py_compile `
  mcp_server\src\rook\agent\local_worker_source_routing_validator.py `
  mcp_server\src\rook\agent\gh_scalar_expectation_acceptance_criteria.py `
  mcp_server\src\rook\agent\gh_scalar_expectation_sources.py `
  mcp_server\src\rook\agent\plan_graph_gh_scalar_value_apply.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  mcp_server\tests\test_gh_scalar_expectation_acceptance_criteria.py `
  mcp_server\tests\test_gh_scalar_expectation_sources.py `
  mcp_server\tests\test_plan_graph_gh_scalar_value_apply.py
```

Expected: no output and exit code 0.

- [ ] **Step 4: Run forbidden drift checks**

Run:

```powershell
Select-String -Path `
  mcp_server\src\rook\agent\gh_scalar_expectation_acceptance_criteria.py, `
  mcp_server\src\rook\agent\gh_scalar_expectation_sources.py, `
  mcp_server\src\rook\agent\plan_graph_gh_scalar_value_apply.py `
  -Pattern "gh_edit","BindStepSpec","base_params","PROBE_REPAIR_CODE","A = 42.0","gh_update_script","gh_create_csharp_script"
```

Expected:

```text
No matches
```

Run:

```powershell
git diff --name-only main..HEAD
```

Expected exact tracked scope:

```text
docs/superpowers/plans/2026-07-08-lm8b-gh-scalar-expectation-prototype.md
docs/superpowers/specs/2026-07-08-lm8a-second-template-family-design.md
mcp_server/src/rook/agent/gh_scalar_expectation_acceptance_criteria.py
mcp_server/src/rook/agent/gh_scalar_expectation_sources.py
mcp_server/src/rook/agent/local_worker_source_routing_validator.py
mcp_server/src/rook/agent/plan_graph_gh_scalar_value_apply.py
mcp_server/tests/test_gh_scalar_expectation_acceptance_criteria.py
mcp_server/tests/test_gh_scalar_expectation_sources.py
mcp_server/tests/test_local_worker_source_routing_validator.py
mcp_server/tests/test_plan_graph_gh_scalar_value_apply.py
```

- [ ] **Step 5: Run diff whitespace check**

Run:

```powershell
git diff --check main..HEAD
```

Expected: no output and exit code 0.

- [ ] **Step 6: Commit any final test-only or guard adjustments**

If Task 5 changed tests or guard wording, commit them:

```powershell
git add mcp_server\tests mcp_server\src\rook\agent
git commit -m "test: cover LM8 scalar expectation boundaries"
```

If Task 5 made no changes, do not create an empty commit.

---

## Post-LM8B / LM8C Roadmap Discipline

LM8B is the deterministic prototype for opening a second family. If LM8C later
produces a receipted live scalar run, the next pressure should generally deepen
the same GH scalar family before broadening. Useful same-family pressures are:

- non-identity scalar relation
- numeric tolerance
- multiple candidate scalar targets
- multi-fact scalar criteria
- repeatability under the same scalar fixture

Do not jump directly from a first scalar receipt to missing-wire repair,
component replacement, `gh_edit` batches, or a broad router unless the LM8B/LM8C
artifacts expose a cross-family protocol defect. This preserves the distinction
between task-family transfer and complexity/difficulty scaling.

---

## Self-Review Checklist

- LM8A's new source classes are statically validated: Task 1.
- `fixture_anchor` is `evidence_context` only: Task 1.
- The expected scalar value remains source-owned: Tasks 2 and 3.
- Observed scalar output uses `receipt_observation`, not `receipt_diagnostic`: Tasks 1, 2, and 3.
- Editable target contract comes from create receipt scalar anchor and excludes GUID: Tasks 2 and 3.
- Worker action is exactly `{"value": number}`: Task 4.
- Trusted GUID is applier-only: Task 4.
- No live Rhino/GH, model calls, worker publication, script repair, topology edit, or `gh_edit` batch: Global Constraints and Task 5.
- LM5 repair seams remain nearby-verified: Task 5.
