# LM5X Acceptance-Criteria Source Extraction Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic source-extraction boundary that projects passed workflow/graph/convention objects into `AcceptanceCriteriaSources`, then proves `assemble(extract(...))` reproduces the LM5U acceptance-criteria packet.

**Architecture:** Add one new production module beside the LM5W assembler. The new module extracts source facts from already-passed objects and returns LM5W typed source containers; it does not assemble packets, import probe scripts, read hidden bind params, or change runtime probe behavior. Tests compare the extractor against the real LM5U fixture while keeping probe-script wiring unchanged.

**Tech Stack:** Python 3.10, pytest, existing Rook plan-graph dataclasses, LM5W `local_worker_acceptance_criteria` types.

---

## File Structure

Create:

```text
mcp_server/src/rook/agent/local_worker_acceptance_criteria_sources.py
```

Responsibility: pure source extraction from explicitly passed `RookWorkflowContract`, `PlanGraph`, and worker-visible `WorkerKnowledgePacket` objects into LM5W `AcceptanceCriteriaSources`.

Create:

```text
mcp_server/tests/test_local_worker_acceptance_criteria_sources.py
```

Responsibility: deterministic tests for public surface, fixture reproduction, source-resolution failures, aliasing, and import/static guards.

Modify:

```text
docs/superpowers/plans/2026-07-05-lm5x-acceptance-criteria-source-extraction-boundary.md
```

Responsibility: implementation plan only.

Do not modify:

```text
mcp_server/src/rook/agent/local_worker_acceptance_criteria.py
mcp_server/src/rook/agent/__init__.py
scripts/lm5k_worker_probe.py
scripts/lm5r_two_pass_publication_probe.py
```

---

### Task 1: Public Surface And Fixture Reproduction RED/GREEN

**Files:**
- Create: `mcp_server/tests/test_local_worker_acceptance_criteria_sources.py`
- Create: `mcp_server/src/rook/agent/local_worker_acceptance_criteria_sources.py`

- [ ] **Step 1: Write failing public-surface and fixture anchor tests**

Create `mcp_server/tests/test_local_worker_acceptance_criteria_sources.py` with this content:

```python
import ast
import copy
import importlib.util
import inspect
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

from rook.agent.local_worker_acceptance_criteria import (
    AcceptanceCriteriaSource,
    AcceptanceCriteriaSources,
    assemble_acceptance_criteria_packet,
)
from rook.agent import local_worker_acceptance_criteria_sources as module
from rook.agent.local_worker_acceptance_criteria_sources import (
    extract_acceptance_criteria_sources,
)


PIN_SOURCE_PATH = "create_script.initial_execution_params.pins_out"
VERIFY_SOURCE_PATH = "workflow_contract.rules.verify_repair.expected_outcome"
DIAGNOSTIC_SOURCE_PATH = "create_script.receipt.script_receipt.repair_anchor.target_errors"
CONVENTION_SOURCE_PATH = "script_body_gotcha"
TARGET_DIAGNOSTIC = (
    "CS0103: The name 'DefinitelyMissingSymbol' does not exist in the current context."
)


def _expected_sources(**overrides):
    values = {
        "pin_contract": AcceptanceCriteriaSource(
            source_class="pin_contract",
            source_path=PIN_SOURCE_PATH,
            value={"pins_out": ["A:double"]},
        ),
        "verifier_outcome": AcceptanceCriteriaSource(
            source_class="verifier_outcome",
            source_path=VERIFY_SOURCE_PATH,
            value="succeeded",
        ),
        "receipt_diagnostic": AcceptanceCriteriaSource(
            source_class="receipt_diagnostic",
            source_path=DIAGNOSTIC_SOURCE_PATH,
            value=[TARGET_DIAGNOSTIC],
        ),
        "convention": AcceptanceCriteriaSource(
            source_class="convention",
            source_path=CONVENTION_SOURCE_PATH,
            value={"mode": "body"},
        ),
        "unresolved_intent": (),
    }
    values.update(overrides)
    return AcceptanceCriteriaSources(**values)


def _load_lm5k_probe_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "lm5k_worker_probe.py"
    spec = importlib.util.spec_from_file_location("lm5k_worker_probe_for_lm5x", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fixture_objects():
    probe = _load_lm5k_probe_script()
    _scaffold, result = probe.derive_probe_graph_state()
    return {
        "probe": probe,
        "workflow_contract": probe._probe_contract(),
        "graph": result.final_graph,
        "convention_packets": (probe._script_body_gotcha_packet(),),
    }


def _extract_from_fixture():
    fixture = _fixture_objects()
    return extract_acceptance_criteria_sources(
        workflow_contract=fixture["workflow_contract"],
        graph=fixture["graph"],
        convention_packets=fixture["convention_packets"],
    )


def _jsonable(value):
    if isinstance(value, Mapping):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _legacy_projection(packet):
    return [
        {
            "criterion_id": criterion["criterion_id"],
            "description": criterion["description"],
            "source": criterion["source"],
        }
        for criterion in packet["criteria"]
    ]


def _import_names(source):
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
            imports.update(alias.name for alias in node.names)
            if node.module:
                imports.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imports


def _call_names(source):
    tree = ast.parse(source)
    calls = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            calls.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                calls.add(f"{node.func.value.id}.{node.func.attr}")
            calls.add(node.func.attr)
    return calls


def test_public_surface_exports_only_extractor():
    assert module.__all__ == ("extract_acceptance_criteria_sources",)


def test_extracts_lm5u_fixture_sources():
    assert _extract_from_fixture() == _expected_sources()


def test_assemble_extracted_sources_matches_lm5w_expected_packet_fingerprint():
    extracted_packet = assemble_acceptance_criteria_packet(_extract_from_fixture())
    expected_packet = assemble_acceptance_criteria_packet(_expected_sources())

    assert extracted_packet["fingerprint"] == expected_packet["fingerprint"]
    assert extracted_packet == expected_packet


def test_extracted_sources_match_lm5u_legacy_acceptance_criteria_projection():
    fixture = _fixture_objects()
    lm5u_packet = _jsonable(
        fixture["probe"]._acceptance_criteria_evidence_packet(
            fixture["graph"]
        ).content
    )
    extracted_packet = assemble_acceptance_criteria_packet(
        extract_acceptance_criteria_sources(
            workflow_contract=fixture["workflow_contract"],
            graph=fixture["graph"],
            convention_packets=fixture["convention_packets"],
        )
    )

    assert _legacy_projection(extracted_packet) == (
        lm5u_packet["fields"]["acceptance_criteria"]["criteria"]
    )
```

- [ ] **Step 2: Run the RED test**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  -q
```

Expected: FAIL during import with `ModuleNotFoundError` or `ImportError` for `local_worker_acceptance_criteria_sources`.

- [ ] **Step 3: Add the minimal extractor module**

Create `mcp_server/src/rook/agent/local_worker_acceptance_criteria_sources.py` with this content:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from rook.agent.local_worker_acceptance_criteria import (
    AcceptanceCriteriaSource,
    AcceptanceCriteriaSources,
)
from rook.agent.local_worker_turn_context import WorkerKnowledgePacket
from rook.agent.plan_graph_workflow_contract import (
    RookWorkflowContract,
    VerifierStepSpec,
)
from rook.learning.plan_graph import PlanGraph


PIN_SOURCE_PATH = "create_script.initial_execution_params.pins_out"
VERIFY_SOURCE_PATH = "workflow_contract.rules.verify_repair.expected_outcome"
DIAGNOSTIC_SOURCE_PATH = (
    "create_script.receipt.script_receipt.repair_anchor.target_errors"
)
CONVENTION_SOURCE_PATH = "script_body_gotcha"


def extract_acceptance_criteria_sources(
    *,
    workflow_contract: RookWorkflowContract,
    graph: PlanGraph,
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> AcceptanceCriteriaSources:
    return AcceptanceCriteriaSources(
        pin_contract=_extract_pin_contract_source(workflow_contract),
        verifier_outcome=_extract_verifier_outcome_source(workflow_contract),
        receipt_diagnostic=_extract_receipt_diagnostic_source(graph),
        convention=_extract_convention_source(convention_packets),
        unresolved_intent=(),
    )


def _extract_pin_contract_source(
    workflow_contract: RookWorkflowContract,
) -> AcceptanceCriteriaSource:
    matches = [
        initial
        for initial in workflow_contract.initial_params
        if initial.node_id == "create_script"
    ]
    if len(matches) != 1:
        raise ValueError(f"{PIN_SOURCE_PATH} missing or ambiguous")
    params = matches[0].execution_params
    if not isinstance(params, Mapping):
        raise ValueError(f"{PIN_SOURCE_PATH} params not mapping")
    pins_out = params.get("pins_out")
    if not isinstance(pins_out, list) or not all(
        isinstance(pin, str) for pin in pins_out
    ):
        raise ValueError(f"{PIN_SOURCE_PATH} not list[str]")
    return AcceptanceCriteriaSource(
        source_class="pin_contract",
        source_path=PIN_SOURCE_PATH,
        value={"pins_out": list(pins_out)},
    )


def _extract_verifier_outcome_source(
    workflow_contract: RookWorkflowContract,
) -> AcceptanceCriteriaSource:
    rules = [rule for rule in workflow_contract.rules if rule.node_id == "verify_repair"]
    if len(rules) != 1:
        raise ValueError(f"{VERIFY_SOURCE_PATH} missing or ambiguous")
    verifier_steps = [
        step for step in rules[0].steps_by_seen_count if isinstance(step, VerifierStepSpec)
    ]
    expected_outcomes = [
        step.expected_outcome
        for step in verifier_steps
        if step.expected_outcome is not None
    ]
    if len(expected_outcomes) != 1:
        raise ValueError(f"{VERIFY_SOURCE_PATH} missing or ambiguous")
    expected = expected_outcomes[0]
    if not isinstance(expected, str) or not expected:
        raise ValueError(f"{VERIFY_SOURCE_PATH} not non-empty string")
    return AcceptanceCriteriaSource(
        source_class="verifier_outcome",
        source_path=VERIFY_SOURCE_PATH,
        value=expected,
    )


def _extract_receipt_diagnostic_source(graph: PlanGraph) -> AcceptanceCriteriaSource:
    if "create_script" not in graph.nodes:
        raise ValueError(f"{DIAGNOSTIC_SOURCE_PATH} create_script missing")
    evidence = graph.nodes["create_script"].evidence
    if evidence is None:
        raise ValueError(f"{DIAGNOSTIC_SOURCE_PATH} evidence missing")
    receipt = getattr(evidence, "receipt", None)
    if not isinstance(receipt, Mapping):
        raise ValueError(f"{DIAGNOSTIC_SOURCE_PATH} receipt missing")
    repair_anchor = receipt.get("repair_anchor")
    if not isinstance(repair_anchor, Mapping):
        raise ValueError(f"{DIAGNOSTIC_SOURCE_PATH} repair_anchor missing")
    target_errors = repair_anchor.get("target_errors")
    if not isinstance(target_errors, list) or not all(
        isinstance(item, str) for item in target_errors
    ):
        raise ValueError(f"{DIAGNOSTIC_SOURCE_PATH} not list[str]")
    return AcceptanceCriteriaSource(
        source_class="receipt_diagnostic",
        source_path=DIAGNOSTIC_SOURCE_PATH,
        value=list(target_errors),
    )


def _extract_convention_source(
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> AcceptanceCriteriaSource:
    candidates = [
        packet
        for packet in convention_packets
        if packet.packet_id == "script_body_gotcha"
    ]
    if len(candidates) != 1:
        raise ValueError(f"{CONVENTION_SOURCE_PATH} missing or ambiguous")
    packet = candidates[0]
    if packet.kind != "gotcha":
        raise ValueError(f"{CONVENTION_SOURCE_PATH} unexpected kind")
    if packet.title != "C# script components use body-style code":
        raise ValueError(f"{CONVENTION_SOURCE_PATH} unexpected title")
    return AcceptanceCriteriaSource(
        source_class="convention",
        source_path=CONVENTION_SOURCE_PATH,
        value={"mode": "body"},
    )


__all__ = ("extract_acceptance_criteria_sources",)
```

- [ ] **Step 4: Run the Task 1 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  -q
```

Expected: PASS for the initial public surface and fixture reproduction tests.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add `
  mcp_server\src\rook\agent\local_worker_acceptance_criteria_sources.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py
git commit -m "feat(lm5x): extract acceptance criteria sources"
```

---

### Task 2: Source-Resolution Failures And Validation Split

**Files:**
- Modify: `mcp_server/tests/test_local_worker_acceptance_criteria_sources.py`
- Modify: `mcp_server/src/rook/agent/local_worker_acceptance_criteria_sources.py`

- [ ] **Step 1: Add source-resolution failure and composition-boundary tests**

Append these tests to `mcp_server/tests/test_local_worker_acceptance_criteria_sources.py`:

```python
def _replace_contract_initial_params(workflow_contract, initial_params):
    from dataclasses import replace

    return replace(workflow_contract, initial_params=tuple(initial_params))


def _replace_contract_rules(workflow_contract, rules):
    from dataclasses import replace

    return replace(workflow_contract, rules=tuple(rules))


def _replace_graph_create_receipt(graph, receipt):
    graph_copy = copy.deepcopy(graph)
    graph_copy.nodes["create_script"].evidence.receipt = receipt
    return graph_copy


def test_missing_create_initial_params_fails_with_pin_source_path():
    fixture = _fixture_objects()
    contract = _replace_contract_initial_params(fixture["workflow_contract"], ())

    with pytest.raises(ValueError, match="create_script.initial_execution_params.pins_out"):
        extract_acceptance_criteria_sources(
            workflow_contract=contract,
            graph=fixture["graph"],
            convention_packets=fixture["convention_packets"],
        )


def test_missing_verify_repair_rule_fails_with_verifier_source_path():
    fixture = _fixture_objects()
    contract = _replace_contract_rules(
        fixture["workflow_contract"],
        [
            rule
            for rule in fixture["workflow_contract"].rules
            if rule.node_id != "verify_repair"
        ],
    )

    with pytest.raises(
        ValueError,
        match="workflow_contract.rules.verify_repair.expected_outcome",
    ):
        extract_acceptance_criteria_sources(
            workflow_contract=contract,
            graph=fixture["graph"],
            convention_packets=fixture["convention_packets"],
        )


def test_target_errors_wrong_shape_fails_with_diagnostic_source_path():
    fixture = _fixture_objects()
    receipt = copy.deepcopy(
        fixture["graph"].nodes["create_script"].evidence.receipt
    )
    receipt["repair_anchor"]["target_errors"] = "not-a-list"
    graph = _replace_graph_create_receipt(fixture["graph"], receipt)

    with pytest.raises(
        ValueError,
        match="create_script.receipt.script_receipt.repair_anchor.target_errors",
    ):
        extract_acceptance_criteria_sources(
            workflow_contract=fixture["workflow_contract"],
            graph=graph,
            convention_packets=fixture["convention_packets"],
        )


def test_missing_script_body_gotcha_fails_with_packet_id():
    fixture = _fixture_objects()

    with pytest.raises(ValueError, match="script_body_gotcha"):
        extract_acceptance_criteria_sources(
            workflow_contract=fixture["workflow_contract"],
            graph=fixture["graph"],
            convention_packets=(),
        )


def test_wrong_diagnostic_shape_extracts_but_assembler_rejects_semantics():
    fixture = _fixture_objects()
    receipt = copy.deepcopy(
        fixture["graph"].nodes["create_script"].evidence.receipt
    )
    receipt["repair_anchor"]["target_errors"] = ["CS0000: Different diagnostic"]
    graph = _replace_graph_create_receipt(fixture["graph"], receipt)

    sources = extract_acceptance_criteria_sources(
        workflow_contract=fixture["workflow_contract"],
        graph=graph,
        convention_packets=fixture["convention_packets"],
    )

    assert sources.receipt_diagnostic.value == ["CS0000: Different diagnostic"]
    with pytest.raises(ValueError, match="DefinitelyMissingSymbol"):
        assemble_acceptance_criteria_packet(sources)
```

- [ ] **Step 2: Run the RED tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  -q
```

Expected: PASS if Task 1 already implemented the planned failure paths. If any test fails, the failure should identify one extractor guard that needs a narrower check or message.

- [ ] **Step 3: Patch implementation only if the RED tests revealed a gap**

If the Task 2 tests fail, update only `mcp_server/src/rook/agent/local_worker_acceptance_criteria_sources.py` so the relevant extractor raises `ValueError` with the source path fragment named in the test.

Use these exact source path constants in messages:

```python
PIN_SOURCE_PATH = "create_script.initial_execution_params.pins_out"
VERIFY_SOURCE_PATH = "workflow_contract.rules.verify_repair.expected_outcome"
DIAGNOSTIC_SOURCE_PATH = (
    "create_script.receipt.script_receipt.repair_anchor.target_errors"
)
CONVENTION_SOURCE_PATH = "script_body_gotcha"
```

- [ ] **Step 4: Run Task 2 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  -q
```

Expected: PASS for success extraction, source-resolution failures, and composition-boundary tests.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add `
  mcp_server\src\rook\agent\local_worker_acceptance_criteria_sources.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py
git commit -m "test(lm5x): cover acceptance source resolution failures"
```

---

### Task 3: Convention Candidate Semantics And Aliasing

**Files:**
- Modify: `mcp_server/tests/test_local_worker_acceptance_criteria_sources.py`
- Modify: `mcp_server/src/rook/agent/local_worker_acceptance_criteria_sources.py`

- [ ] **Step 1: Add convention candidate and aliasing tests**

Append these tests to `mcp_server/tests/test_local_worker_acceptance_criteria_sources.py`:

```python
def test_duplicate_script_body_gotcha_candidates_fail():
    fixture = _fixture_objects()
    packet = fixture["convention_packets"][0]

    with pytest.raises(ValueError, match="script_body_gotcha"):
        extract_acceptance_criteria_sources(
            workflow_contract=fixture["workflow_contract"],
            graph=fixture["graph"],
            convention_packets=(packet, packet),
        )


def test_script_body_gotcha_wrong_kind_fails_after_id_selection():
    fixture = _fixture_objects()
    packet = fixture["convention_packets"][0]
    wrong_kind = type(packet)(
        packet_id=packet.packet_id,
        kind="evidence",
        title=packet.title,
        content=packet.content,
    )

    with pytest.raises(ValueError, match="script_body_gotcha"):
        extract_acceptance_criteria_sources(
            workflow_contract=fixture["workflow_contract"],
            graph=fixture["graph"],
            convention_packets=(wrong_kind,),
        )


def test_script_body_gotcha_wrong_title_fails_after_id_selection():
    fixture = _fixture_objects()
    packet = fixture["convention_packets"][0]
    wrong_title = type(packet)(
        packet_id=packet.packet_id,
        kind=packet.kind,
        title="Different gotcha",
        content=packet.content,
    )

    with pytest.raises(ValueError, match="script_body_gotcha"):
        extract_acceptance_criteria_sources(
            workflow_contract=fixture["workflow_contract"],
            graph=fixture["graph"],
            convention_packets=(wrong_title,),
        )


def test_extracted_values_are_copied_from_contract_and_receipt():
    fixture = _fixture_objects()
    sources = extract_acceptance_criteria_sources(
        workflow_contract=fixture["workflow_contract"],
        graph=fixture["graph"],
        convention_packets=fixture["convention_packets"],
    )

    contract_pins_out = fixture["workflow_contract"].initial_params[
        0
    ].execution_params["pins_out"]
    receipt_target_errors = fixture["graph"].nodes[
        "create_script"
    ].evidence.receipt["repair_anchor"]["target_errors"]

    contract_pins_out.append("B:int")
    receipt_target_errors.append("CS9999: extra")
    sources.pin_contract.value["pins_out"].append("C:string")
    sources.receipt_diagnostic.value.append("CS8888: source mutation")

    assert sources.pin_contract.value["pins_out"] == ["A:double", "C:string"]
    assert sources.receipt_diagnostic.value == [
        TARGET_DIAGNOSTIC,
        "CS8888: source mutation",
    ]
    assert fixture["workflow_contract"].initial_params[0].execution_params[
        "pins_out"
    ] == ["A:double", "B:int"]
    assert fixture["graph"].nodes["create_script"].evidence.receipt[
        "repair_anchor"
    ]["target_errors"] == [TARGET_DIAGNOSTIC, "CS9999: extra"]
```

- [ ] **Step 2: Run the tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  -q
```

Expected: PASS if the Task 1 implementation selected convention candidates by `packet_id` first and copied list values. If not, patch the extractor to:

```python
candidates = [
    packet
    for packet in convention_packets
    if packet.packet_id == "script_body_gotcha"
]
```

and ensure list values are copied with `list(...)`.

- [ ] **Step 3: Commit Task 3**

Run:

```powershell
git add `
  mcp_server\src\rook\agent\local_worker_acceptance_criteria_sources.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py
git commit -m "test(lm5x): guard source extraction aliasing"
```

---

### Task 4: Static Import Guards And Scope Lock

**Files:**
- Modify: `mcp_server/tests/test_local_worker_acceptance_criteria_sources.py`

- [ ] **Step 1: Add static guard tests**

Append these tests to `mcp_server/tests/test_local_worker_acceptance_criteria_sources.py`:

```python
def test_source_module_import_boundary_stays_one_way_and_narrow():
    source = inspect.getsource(module)
    imports = _import_names(source)
    calls = _call_names(source)

    assert "rook.agent.local_worker_acceptance_criteria" in imports
    assert not any(
        "local_worker_acceptance_criteria_sources" in imported
        for imported in _import_names(
            inspect.getsource(
                __import__(
                    "rook.agent.local_worker_acceptance_criteria",
                    fromlist=["dummy"],
                )
            )
        )
    )
    forbidden_import_fragments = (
        "BindStepSpec",
        "lm5k_worker_probe",
        "lm5r_two_pass_publication_probe",
        "LiteLLM",
        "run_local_worker",
        "yaml",
    )
    for fragment in forbidden_import_fragments:
        assert not any(fragment in imported for imported in imports)
    assert "base_params" not in source
    assert "PROBE_REPAIR_CODE" not in source
    assert {"open", "Path", "json.load"}.isdisjoint(calls)


def test_probe_scripts_do_not_import_acceptance_criteria_sources():
    root = Path(__file__).resolve().parents[2]
    for relative in (
        "scripts/lm5k_worker_probe.py",
        "scripts/lm5r_two_pass_publication_probe.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        imports = _import_names(source)
        assert not any(
            "local_worker_acceptance_criteria_sources" in imported
            for imported in imports
        )
```

- [ ] **Step 2: Run the static guard tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  -q
```

Expected: PASS. If the import guard fails, remove the forbidden import or string from the source module; do not loosen the guard.

- [ ] **Step 3: Commit Task 4**

Run:

```powershell
git add mcp_server\tests\test_local_worker_acceptance_criteria_sources.py
git commit -m "test(lm5x): guard source extraction boundaries"
```

---

### Task 5: Final Verification And Scope Review

**Files:**
- Verify only.

- [ ] **Step 1: Run targeted LM5X tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  -q
```

Expected: all LM5X tests pass.

- [ ] **Step 2: Run nearby acceptance/probe gate**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  -q
```

Expected: all tests pass. The exact count may change as LM5X tests are added; report the count.

- [ ] **Step 3: Run Python 3.10 compile**

Run:

```powershell
py -3.10 -m py_compile `
  mcp_server\src\rook\agent\local_worker_acceptance_criteria_sources.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py
```

Expected: exits 0 with no output.

- [ ] **Step 4: Verify exact diff scope**

Run:

```powershell
$expected = @(
  "docs/superpowers/plans/2026-07-05-lm5x-acceptance-criteria-source-extraction-boundary.md",
  "docs/superpowers/specs/2026-07-05-lm5x-acceptance-criteria-source-extraction-boundary-design.md",
  "mcp_server/src/rook/agent/local_worker_acceptance_criteria_sources.py",
  "mcp_server/tests/test_local_worker_acceptance_criteria_sources.py"
)
$actual = git diff --name-only main..HEAD
Compare-Object $expected $actual
```

Expected: no output.

- [ ] **Step 5: Verify forbidden runtime/probe drift is absent**

Run:

```powershell
git diff --name-only main..HEAD |
  rg "mcp_server/src/rook/agent/__init__\.py|scripts/lm5k_worker_probe\.py|scripts/lm5r_two_pass_publication_probe\.py|mcp_server/src/rook/agent/local_worker_acceptance_criteria\.py|mcp_server/src/rook/agent/plan_graph_workflow_contract\.py"
```

Expected: no output. `rg` exits 1 when no matches are found.

- [ ] **Step 6: Run final whitespace check**

Run:

```powershell
git diff --check main..HEAD
```

Expected: exits 0 with no output.

- [ ] **Step 7: Confirm worktree state**

Run:

```powershell
git status --short --branch
```

Expected: branch is `codex/lm5x-acceptance-criteria-source-extraction`; tracked files are clean after commits. Known unrelated untracked files may remain:

```text
.understand-anything/
docs/superpowers/plans/2026-07-04-rook2-minimal-base-roadmap.md
docs/superpowers/probes/2026-07-04-rook20-v01-hermes-plugin-validation.md
docs/superpowers/specs/2026-07-03-rook-2.0-minimal-iteration-design.md
```

---

## Implementation Notes

- LM5X is deterministic only. Do not run live probes.
- Do not update curated evidence docs.
- Do not wire the extractor into `scripts/lm5k_worker_probe.py`; that is LM5Y.
- Do not add package-level re-exports.
- Do not generalize LM5W assembler strictness.
- Do not read `BindStepSpec`, `base_params`, or `PROBE_REPAIR_CODE`.
- If a failure could be fixed by weakening LM5W strictness, stop and ask for review instead.

## Recommended Execution

Use **Subagent-Driven execution**.

Reasons:

- Task 1 adds the production seam.
- Task 2 and Task 3 are boundary-sensitive validation/aliasing tests.
- Task 4 is a drift guard that benefits from fresh review.
- LM5Y depends on LM5X staying boring and exact.
