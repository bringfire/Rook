# LM4V Catalog Provider Live Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one `requires_rhino` live proof that production `CatalogCurrentStepProvider` can replace LM4T's bespoke provider in the full current-step repair stream.

**Architecture:** This is test-only. The new live test uses the merged LM4U provider directly, configured with caller-authored `NodeStepRule`s, then drives LM4S through live create, pure verify, memory bind, live repair, pure verify, and provider halt at `done` readiness. LM4G records remain test-local observations, and terminal completion remains outside LM4S.

**Tech Stack:** Python 3, pytest `requires_rhino` + `asyncio`, existing `RookAgent` live runner, LM4U `CatalogCurrentStepProvider`, LM4S stream runner, existing PlanGraph repair template.

---

## File Structure

- Create `mcp_server/tests/test_live_catalog_current_step_provider_vertical_live.py`
  - Owns the LM4V live proof.
  - Imports production `CatalogCurrentStepProvider` / `NodeStepRule`.
  - Configures the five-node repair catalog in test code.
  - Runs `run_current_step_stream` through real Rhino/GH producer dispatches.
  - Asserts stream trace, supply-record provider metadata, LM4G producer observations, and terminal boundary.
- Do not modify production code:
  - no `mcp_server/src/**`;
  - no provider factory/helper;
  - no LM4S changes;
  - no LM4T helper extraction.
- Runtime cleanup:
  - live runs may dirty `knowledge/gh/operations_knowledge.json`;
  - restore it after live verification and never commit it.

---

### Task 1: Live Catalog Provider Proof

**Files:**
- Create: `mcp_server/tests/test_live_catalog_current_step_provider_vertical_live.py`

- [ ] **Step 1: Write the live proof test**

Create `mcp_server/tests/test_live_catalog_current_step_provider_vertical_live.py`:

```python
"""LM4V live proof that CatalogCurrentStepProvider carries the repair stream.

LM4T proved the full current-step stream with a bespoke test-local provider. LM4V
replaces that closure with the production LM4U CatalogCurrentStepProvider and keeps
the rest of the live repair ladder intentionally familiar:
LM4N proposal -> LM4P mapping/revalidation -> LM4Q execution -> LM4R record -> LM4S stream.

requires_rhino: deselected from CI; fresh_document + _ensure_gh_document skip when
Rhino/GH is unavailable. Run from repo root:
    pytest -m requires_rhino mcp_server/tests/test_live_catalog_current_step_provider_vertical_live.py
Then restore knowledge/gh/operations_knowledge.json if the live run dirties it:
    git restore knowledge/gh/operations_knowledge.json
"""

from __future__ import annotations

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_current_step_provider import (
    CatalogCurrentStepProvider,
    NodeStepRule,
)
from rook.agent.plan_graph_current_step_stream import run_current_step_stream
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    build_live_producer_record,
)
from rook.agent.plan_graph_sequence_runner import BindStep, ProducerStep, VerifierStep
from rook.learning.plan_graph import (
    NodeOutcome,
    apply_outcome,
    graph_status,
    initialize_graph,
)
from rook.learning.plan_graph_templates import select_template
from rook.server import _mcp_tool_executor

from .conftest import _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_CREATE_EXPECTATION = LiveProducerExpectation(
    applied=True,
    outcome_status="succeeded",
    node_status="succeeded",
    tool_status="failed",
    verified=False,
    artifact_status="created_with_errors",
)
_REPAIR_EXPECTATION = LiveProducerExpectation(
    applied=True,
    outcome_status="succeeded",
    node_status="succeeded",
    verified=True,
    artifact_status="usable",
)


async def _ensure_gh_document() -> None:
    """Establish an active Grasshopper document or skip with evidence."""
    res = await _mcp_tool_executor("gh_document_new", {})
    if _is_error(res) or not isinstance(res, dict):
        pytest.skip(f"Grasshopper document setup unavailable: {res!r}")


def _build_catalog_provider() -> CatalogCurrentStepProvider:
    return CatalogCurrentStepProvider(
        (
            NodeStepRule("create_script", (ProducerStep("create_script"),)),
            NodeStepRule(
                "verify_create",
                (
                    VerifierStep(
                        "verify_create",
                        "create_script",
                        expected_outcome="needs_repair",
                    ),
                ),
            ),
            NodeStepRule(
                "repair_same_component",
                (
                    BindStep(
                        "repair_same_component",
                        {"code": "A = 42.0;", "mode": "body", "language": "csharp"},
                        {"guid": ("repair_anchor", "component_guid")},
                    ),
                    ProducerStep("repair_same_component"),
                ),
            ),
            NodeStepRule(
                "verify_repair",
                (
                    VerifierStep(
                        "verify_repair",
                        "repair_same_component",
                        expected_outcome="succeeded",
                    ),
                ),
            ),
        ),
        terminal_node_ids=frozenset({"done"}),
    )


async def test_live_catalog_provider_stream_reaches_done_boundary(fresh_document):
    await _ensure_gh_document()

    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    assert selection.graph is not None

    graph = initialize_graph(selection.graph)
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
    assert graph.nodes["repair_same_component"].execution_ref == "gh_update_script:v1"
    assert graph.nodes["create_script"].status == "ready"
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4VCatalogCurrentStepProviderLive",
        "x": 350,
        "y": 1040,
    }

    provider = _build_catalog_provider()
    agent = RookAgent(tool_executor=_mcp_tool_executor)

    result = await run_current_step_stream(
        graph,
        provider,
        max_steps=6,
        runner=agent,
    )

    assert result.stop_reason == "provider_halt"
    assert result.steps_attempted == 5
    assert len(result.records) == 5
    assert len(result.supply_records) == 6

    expected_nodes = [
        "create_script",
        "verify_create",
        "repair_same_component",
        "repair_same_component",
        "verify_repair",
    ]
    expected_kinds = ["producer", "verifier", "bind", "producer", "verifier"]
    assert [record.accepted_node_id for record in result.records] == expected_nodes
    assert [record.execution_kind for record in result.records] == expected_kinds

    for index, record in enumerate(result.records):
        supply = result.supply_records[index]
        assert supply.decision == "SUPPLY"
        assert supply.envelope is not None
        assert supply.envelope.mapping is record.mapping
        assert supply.metadata is not None
        assert supply.metadata["provider"] == "catalog_current_step_provider:v1"
        assert supply.metadata["selected_node_id"] == record.accepted_node_id
        assert supply.metadata["proposal_decision"] == "SELECT_NODE"
        assert record.ran is True
        assert record.execution_failure is None
        assert record.mapping_mapped is True
        assert record.revalidation.decision == "ACCEPT"
        assert record.mapping.revalidation is record.revalidation
        assert record.supplied_selected_node_id == record.accepted_node_id
        assert record.fresh_selected_node_id == record.accepted_node_id

    bind_record = result.records[2]
    repair_record = result.records[3]
    assert bind_record.accepted_node_id == "repair_same_component"
    assert repair_record.accepted_node_id == "repair_same_component"
    assert bind_record.execution_kind == "bind"
    assert repair_record.execution_kind == "producer"
    assert bind_record.bind_applied is True
    assert bind_record.execution.bind_result is not None
    assert bind_record.execution.bind_result.applied is True

    bind_supply = result.supply_records[2]
    repair_supply = result.supply_records[3]
    assert bind_supply.metadata is not None
    assert repair_supply.metadata is not None
    assert bind_supply.metadata["selected_node_id"] == "repair_same_component"
    assert bind_supply.metadata["seen_count"] == 0
    assert bind_supply.metadata["step_kind"] == "bind"
    assert repair_supply.metadata["selected_node_id"] == "repair_same_component"
    assert repair_supply.metadata["seen_count"] == 1
    assert repair_supply.metadata["step_kind"] == "producer"

    assert result.records[1].verifier_applied is True
    assert result.records[1].verifier_outcome_status == "needs_repair"
    assert result.records[4].verifier_applied is True
    assert result.records[4].verifier_outcome_status == "succeeded"

    final_supply = result.supply_records[5]
    assert final_supply.decision == "HALT"
    assert final_supply.envelope is None
    assert final_supply.reason == "terminal_node_selected:done"
    assert final_supply.metadata is not None
    assert final_supply.metadata["proposal_decision"] == "SELECT_NODE"
    assert final_supply.metadata["selected_node_id"] == "done"

    create_producer = result.records[0].execution.producer_result
    repair_producer = result.records[3].execution.producer_result
    assert create_producer is not None
    assert repair_producer is not None

    create_record = build_live_producer_record(create_producer, _CREATE_EXPECTATION)
    assert create_record.tool_name == "gh_create_csharp_script"
    assert create_record.artifact_status == "created_with_errors"
    assert create_record.verified is False
    assert create_record.repair_anchor_guid is not None
    assert create_record.evaluated is True
    assert create_record.passed is True, f"mismatches={create_record.mismatches!r}"

    assert bind_record.execution.bind_result.binding is not None
    assert bind_record.execution.bind_result.binding.params["guid"] == (
        create_record.repair_anchor_guid
    )

    repair_live_record = build_live_producer_record(
        repair_producer,
        _REPAIR_EXPECTATION,
    )
    assert repair_live_record.tool_name == "gh_update_script"
    assert repair_live_record.artifact_status == "usable"
    assert repair_live_record.verified is True
    assert repair_live_record.tool_status is None
    assert repair_live_record.evaluated is True
    assert repair_live_record.passed is True, (
        f"mismatches={repair_live_record.mismatches!r}"
    )

    assert result.final_graph.nodes["done"].status == "ready"
    assert result.final_graph.nodes["done"].is_terminal is True
    assert graph_status(result.final_graph) != "complete"

    completed = apply_outcome(
        result.final_graph,
        "done",
        NodeOutcome(status="succeeded"),
    )
    assert graph_status(completed) == "complete"
```

- [ ] **Step 2: Verify the new live test collects**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest --collect-only mcp_server\tests\test_live_catalog_current_step_provider_vertical_live.py -q
```

Expected: exactly one collected test:

```text
mcp_server/tests/test_live_catalog_current_step_provider_vertical_live.py::test_live_catalog_provider_stream_reaches_done_boundary
```

- [ ] **Step 3: Run deterministic provider tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_current_step_provider.py -q
```

Expected: provider tests pass. Current baseline at spec time: `24 passed`.

- [ ] **Step 4: Commit the live test**

Run:

```powershell
git add -- mcp_server\tests\test_live_catalog_current_step_provider_vertical_live.py
git commit -m "test(lm4v): prove catalog provider live stream"
```

Expected: commit includes only `mcp_server/tests/test_live_catalog_current_step_provider_vertical_live.py`.

---

### Task 2: Live Acceptance and Branch Gates

**Files:**
- Review: `docs/superpowers/specs/2026-06-25-lm4v-catalog-provider-live-proof-design.md`
- Review: `docs/superpowers/plans/2026-06-25-lm4v-catalog-provider-live-proof.md`
- Review: `mcp_server/tests/test_live_catalog_current_step_provider_vertical_live.py`

- [ ] **Step 1: Run the live proof when Rhino and Grasshopper are available**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -m requires_rhino mcp_server\tests\test_live_catalog_current_step_provider_vertical_live.py -q
```

Expected when Rhino/GH are available: `1 passed`.

If Rhino/GH are unavailable, expected result is a skip with a concrete reason from `fresh_document` or `_ensure_gh_document`. Do not weaken or fake the live proof.

- [ ] **Step 2: Restore live runtime knowledge mutation**

Run after any live execution:

```powershell
git restore knowledge/gh/operations_knowledge.json
git status --short
```

Expected: `knowledge/gh/operations_knowledge.json` is not listed.

- [ ] **Step 3: Run focused LM4N-U gate**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_selector.py mcp_server\tests\test_plan_graph_revalidation.py mcp_server\tests\test_plan_graph_step_mapping.py mcp_server\tests\test_plan_graph_step_executor.py mcp_server\tests\test_plan_graph_current_step_runner.py mcp_server\tests\test_plan_graph_current_step_stream.py mcp_server\tests\test_plan_graph_current_step_provider.py -q
```

Expected: focused gate passes. Current baseline at spec time: `106 passed`.

- [ ] **Step 4: Verify diff and scope**

Run:

```powershell
git diff --check main..HEAD
git diff --name-status main..HEAD
git status --short --branch
```

Expected `git diff --name-status main..HEAD` lists exactly:

```text
A	docs/superpowers/specs/2026-06-25-lm4v-catalog-provider-live-proof-design.md
A	docs/superpowers/plans/2026-06-25-lm4v-catalog-provider-live-proof.md
A	mcp_server/tests/test_live_catalog_current_step_provider_vertical_live.py
```

Expected:

- `git diff --check main..HEAD` exits 0;
- no `mcp_server/src/**` changes;
- no `knowledge/gh/operations_knowledge.json` change.

- [ ] **Step 5: Commit this implementation plan if not already committed**

If this plan file is not committed yet, run:

```powershell
git add -- docs\superpowers\plans\2026-06-25-lm4v-catalog-provider-live-proof.md
git commit -m "docs(lm4v): plan catalog provider live proof"
```

Expected: commit includes only `docs/superpowers/plans/2026-06-25-lm4v-catalog-provider-live-proof.md`.

- [ ] **Step 6: Push and open draft PR**

Run:

```powershell
$body = @'
## Summary
- add LM4V, a test-only live proof that production CatalogCurrentStepProvider carries the LM4T repair stream
- keep the slice to docs + one requires_rhino test; no production code changes
- assert stream trace, provider supply-record metadata, LM4G producer observations, and terminal done outside LM4S

## Verification
- mcp_server\.venv\Scripts\python.exe -m pytest --collect-only mcp_server\tests\test_live_catalog_current_step_provider_vertical_live.py -q
- mcp_server\.venv\Scripts\python.exe -m pytest -m requires_rhino mcp_server\tests\test_live_catalog_current_step_provider_vertical_live.py -q
- mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_current_step_provider.py -q
- mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_selector.py mcp_server\tests\test_plan_graph_revalidation.py mcp_server\tests\test_plan_graph_step_mapping.py mcp_server\tests\test_plan_graph_step_executor.py mcp_server\tests\test_plan_graph_current_step_runner.py mcp_server\tests\test_plan_graph_current_step_stream.py mcp_server\tests\test_plan_graph_current_step_provider.py -q
- git diff --check main..HEAD
'@
$bodyPath = Join-Path $env:TEMP 'rook-lm4v-catalog-provider-live-proof-pr.md'
Set-Content -Path $bodyPath -Value $body -Encoding UTF8
git push -u origin codex/lm4v-catalog-provider-live-proof
gh pr create --draft --title "LM4V catalog provider live proof" --body-file $bodyPath
```

Expected: draft PR opens against `main`; do not merge.

---

## Self-Review Checklist

- Spec coverage:
  - Test-only live proof: Task 1 creates one `requires_rhino` file.
  - Production provider substitution: Task 1 imports `CatalogCurrentStepProvider` / `NodeStepRule` directly and defines no test-local provider class.
  - Declared refs: Task 1 asserts both `execution_ref`s before running the stream.
  - Distinct LM4V live component: Task 1 uses `LM4VCatalogCurrentStepProviderLive`, `x=350`, `y=1040`.
  - Exact trace: Task 1 asserts five records and six supply records, accepted ids, and execution kinds.
  - Supply-record metadata: Task 1 asserts provider metadata through `result.supply_records`.
  - Same-node repair pressure: Task 1 asserts repair bind/producers have seen counts `0` and `1`.
  - LM4G observations: Task 1 builds records after the stream from native producer results only.
  - Terminal boundary: Task 1 asserts `done` ready/not complete, then applies terminal outside LM4S.
  - No production diff: Task 2 diff guard checks no `mcp_server/src/**`.
- Placeholder scan:
  - Run a red-flag phrase search against this plan file.
  - Expected: no matches for the forbidden red-flag phrases from the writing-plans skill.
- Type consistency:
  - `CatalogCurrentStepProvider`, `NodeStepRule`, `run_current_step_stream`, `ProducerStep`, `VerifierStep`, `BindStep`, `LiveProducerExpectation`, `NodeOutcome`, `initialize_graph`, and `EXECUTION_PARAMS_KEY` match merged modules.
  - Provider metadata assertions read from `EnvelopeSupplyRecord.metadata`, not `CurrentStepRecord.metadata`.
  - Terminal application uses `apply_outcome(result.final_graph, "done", NodeOutcome(status="succeeded"))`.

---

## Execution Choice

Plan complete and saved to `docs/superpowers/plans/2026-06-25-lm4v-catalog-provider-live-proof.md`. Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent for the live test and review before live acceptance.
2. **Inline Execution** - Execute in this session using executing-plans, with checkpoints before the live run.
