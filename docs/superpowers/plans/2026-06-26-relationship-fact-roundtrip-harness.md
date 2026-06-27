# Relationship Fact Round-Trip Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a smoke-first round-trip harness that validates authored Rhino user text becomes projected `relationship_fact_v1` edges and readable `scene_context(sync=false)` evidence.

**Architecture:** Add one small pure comparator module for normalized relationship facts, then add one live pytest adapter around the existing five-object smoke fixture. The live adapter creates the Rhino fixture externally, but projection and NetworkX edge extraction must run in the same pytest Python process against the same `SceneGraphAnalytics` singleton.

**Tech Stack:** Python 3.10+, pytest, pytest-asyncio, NetworkX `MultiDiGraph`, Rook MCP server source dispatcher, Rook live Rhino pytest fixtures.

---

## Execution Context

Use the stacked round-trip branch, not `main`:

```powershell
cd C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph
git status --short --branch
```

Expected:

```text
## codex/pearson-robot-roundtrip-harness...origin/codex/pearson-robot-roundtrip-harness
```

This branch is stacked on the frozen projection slice at:

```text
d66f3119 fix: make relationship projection smoke repeatable
```

Reference design:

```text
docs/superpowers/specs/2026-06-26-relationship-fact-roundtrip-harness-design.md
```

Existing projection implementation and tests:

```text
mcp_server/src/rook/scene/relationship_fact_projection.py
mcp_server/tests/test_relationship_fact_projection.py
mcp_server/tests/test_relationship_fact_projection_tool.py
```

Existing smoke fixture:

```text
experiments/relationship_fact_projection_smoke/scripts/create_smoke_fixture_rhino.py
experiments/relationship_fact_projection_smoke/README.md
```

## File Structure

Create:

- `mcp_server/src/rook/scene/relationship_fact_roundtrip.py`
  - Pure normalized fact comparison.
  - No Rhino imports.
  - No NetworkX imports.
  - Public API: `compare_roundtrip(...)`.

- `mcp_server/tests/test_relationship_fact_roundtrip.py`
  - Pure unit tests for exact match, missing facts, unexpected facts, wrong metadata, and missing context substrings.

- `mcp_server/tests/test_relationship_fact_roundtrip_live.py`
  - Live smoke adapter using `@pytest.mark.requires_rhino`.
  - Creates the existing Rhino fixture with `rhino_execute`.
  - Calls `project_relationship_facts_for_tool(..., analytics=sg)` in-process.
  - Extracts actual facts from `sg.graph` projected edge attributes.
  - Queries `scene_context(sync=false)` through source dispatcher against the same singleton graph.

Modify:

- `experiments/relationship_fact_projection_smoke/README.md`
  - Add the round-trip harness command and state that Pearson `g002` remains a manual follow-up gate.

Do not modify:

- Native C++ code.
- Managed C# code.
- Existing projection behavior.
- MCP tool registration.

## Task 1: Pure Comparator Tests

**Files:**

- Create: `mcp_server/tests/test_relationship_fact_roundtrip.py`

- [ ] **Step 1: Write the failing pure tests**

Create `mcp_server/tests/test_relationship_fact_roundtrip.py` with:

```python
from rook.scene.relationship_fact_roundtrip import compare_roundtrip


EXPECTED_FACT = {
    "relationship": "connects",
    "fromFeature": "smoke_member.start",
    "toFeature": "smoke_joint.point",
    "contactKind": "point_to_point",
    "provenance": "authored_assembly_graph",
    "status": "accepted",
    "graphSource": "relationship_fact_smoke",
    "graphRevision": "smoke001",
    "pose": "smoke_pose",
}


REQUIRED_CONTEXT = [
    "connects",
    "connected by",
    "smoke_member.start -> smoke_joint.point",
    "point_to_point",
    "accepted",
    "authored_assembly_graph",
]


CONTEXT_TEXT = """
connects: POINT via smoke_member.start -> smoke_joint.point, point_to_point, accepted, authored_assembly_graph
connected by: CURVE via smoke_member.start -> smoke_joint.point, point_to_point, accepted, authored_assembly_graph
"""


def test_compare_roundtrip_exact_fact_and_context_succeeds():
    report = compare_roundtrip(
        expected_facts=[EXPECTED_FACT],
        actual_facts=[dict(EXPECTED_FACT, fromObjectId="member-id", toObjectId="joint-id")],
        context_text=CONTEXT_TEXT,
        required_substrings=REQUIRED_CONTEXT,
    )

    assert report == {
        "success": True,
        "missingFacts": [],
        "unexpectedFacts": [],
        "wrongMetadata": [],
        "missingContextSubstrings": [],
    }


def test_compare_roundtrip_reports_missing_fact():
    report = compare_roundtrip(
        expected_facts=[EXPECTED_FACT],
        actual_facts=[],
        context_text=CONTEXT_TEXT,
        required_substrings=REQUIRED_CONTEXT,
    )

    assert report["success"] is False
    assert report["missingFacts"] == [EXPECTED_FACT]
    assert report["unexpectedFacts"] == []
    assert report["wrongMetadata"] == []
    assert report["missingContextSubstrings"] == []


def test_compare_roundtrip_reports_unexpected_fact():
    unexpected = dict(EXPECTED_FACT, toFeature="smoke_other.point")

    report = compare_roundtrip(
        expected_facts=[EXPECTED_FACT],
        actual_facts=[unexpected],
        context_text=CONTEXT_TEXT,
        required_substrings=REQUIRED_CONTEXT,
    )

    assert report["success"] is False
    assert report["missingFacts"] == [EXPECTED_FACT]
    assert report["unexpectedFacts"] == [unexpected]
    assert report["wrongMetadata"] == []
    assert report["missingContextSubstrings"] == []


def test_compare_roundtrip_reports_wrong_metadata_for_matching_identity():
    actual = dict(EXPECTED_FACT, status="candidate")

    report = compare_roundtrip(
        expected_facts=[EXPECTED_FACT],
        actual_facts=[actual],
        context_text=CONTEXT_TEXT,
        required_substrings=REQUIRED_CONTEXT,
    )

    assert report["success"] is False
    assert report["missingFacts"] == []
    assert report["unexpectedFacts"] == []
    assert report["wrongMetadata"] == [
        {
            "identity": {
                "relationship": "connects",
                "fromFeature": "smoke_member.start",
                "toFeature": "smoke_joint.point",
                "graphSource": "relationship_fact_smoke",
                "graphRevision": "smoke001",
                "pose": "smoke_pose",
            },
            "expected": {"status": "accepted"},
            "actual": {"status": "candidate"},
        }
    ]
    assert report["missingContextSubstrings"] == []


def test_compare_roundtrip_reports_missing_context_substrings():
    report = compare_roundtrip(
        expected_facts=[EXPECTED_FACT],
        actual_facts=[EXPECTED_FACT],
        context_text="connects: smoke_member.start -> smoke_joint.point",
        required_substrings=REQUIRED_CONTEXT,
    )

    assert report["success"] is False
    assert report["missingFacts"] == []
    assert report["unexpectedFacts"] == []
    assert report["wrongMetadata"] == []
    assert report["missingContextSubstrings"] == [
        "connected by",
        "point_to_point",
        "accepted",
        "authored_assembly_graph",
    ]
```

- [ ] **Step 2: Run the pure tests and verify they fail for the missing module**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_roundtrip.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'rook.scene.relationship_fact_roundtrip'
```

Do not continue until the failure is the missing module, not an import-path or syntax error.

## Task 2: Pure Comparator Implementation

**Files:**

- Create: `mcp_server/src/rook/scene/relationship_fact_roundtrip.py`
- Test: `mcp_server/tests/test_relationship_fact_roundtrip.py`

- [ ] **Step 1: Implement the pure comparator**

Create `mcp_server/src/rook/scene/relationship_fact_roundtrip.py` with:

```python
from __future__ import annotations

from typing import Any


IDENTITY_FIELDS = (
    "relationship",
    "fromFeature",
    "toFeature",
    "graphSource",
    "graphRevision",
    "pose",
)

METADATA_FIELDS = (
    "contactKind",
    "provenance",
    "status",
)

CONTRACT_FIELDS = (*IDENTITY_FIELDS, *METADATA_FIELDS)


def _normalize_fact(fact: dict[str, Any]) -> dict[str, Any]:
    return {field: fact.get(field) for field in CONTRACT_FIELDS}


def _identity(fact: dict[str, Any]) -> dict[str, Any]:
    return {field: fact.get(field) for field in IDENTITY_FIELDS}


def _identity_key(fact: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(fact.get(field) for field in IDENTITY_FIELDS)


def _metadata_delta(expected: dict[str, Any], actual: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_delta: dict[str, Any] = {}
    actual_delta: dict[str, Any] = {}
    for field in METADATA_FIELDS:
        expected_value = expected.get(field)
        actual_value = actual.get(field)
        if expected_value != actual_value:
            expected_delta[field] = expected_value
            actual_delta[field] = actual_value
    return expected_delta, actual_delta


def compare_roundtrip(
    *,
    expected_facts: list[dict[str, Any]],
    actual_facts: list[dict[str, Any]],
    context_text: str,
    required_substrings: list[str],
) -> dict[str, Any]:
    expected_by_key = {_identity_key(fact): _normalize_fact(fact) for fact in expected_facts}
    actual_by_key = {_identity_key(fact): _normalize_fact(fact) for fact in actual_facts}

    missing_facts = [
        expected
        for key, expected in expected_by_key.items()
        if key not in actual_by_key
    ]
    unexpected_facts = [
        actual
        for key, actual in actual_by_key.items()
        if key not in expected_by_key
    ]
    wrong_metadata = []
    for key, expected in expected_by_key.items():
        actual = actual_by_key.get(key)
        if actual is None:
            continue
        expected_delta, actual_delta = _metadata_delta(expected, actual)
        if expected_delta or actual_delta:
            wrong_metadata.append(
                {
                    "identity": _identity(expected),
                    "expected": expected_delta,
                    "actual": actual_delta,
                }
            )

    missing_context_substrings = [
        substring
        for substring in required_substrings
        if substring not in context_text
    ]

    success = not (
        missing_facts
        or unexpected_facts
        or wrong_metadata
        or missing_context_substrings
    )
    return {
        "success": success,
        "missingFacts": missing_facts,
        "unexpectedFacts": unexpected_facts,
        "wrongMetadata": wrong_metadata,
        "missingContextSubstrings": missing_context_substrings,
    }
```

- [ ] **Step 2: Run the pure tests and verify they pass**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_roundtrip.py -q
```

Expected:

```text
5 passed
```

- [ ] **Step 3: Commit the pure comparator**

Run:

```powershell
git add mcp_server/src/rook/scene/relationship_fact_roundtrip.py mcp_server/tests/test_relationship_fact_roundtrip.py
git commit -m "feat: add relationship fact roundtrip comparator"
```

## Task 3: Live Smoke Adapter Test

**Files:**

- Create: `mcp_server/tests/test_relationship_fact_roundtrip_live.py`
- Test: `mcp_server/tests/test_relationship_fact_roundtrip_live.py`

- [ ] **Step 1: Write the live adapter test**

Create `mcp_server/tests/test_relationship_fact_roundtrip_live.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = (
    REPO_ROOT
    / "experiments"
    / "relationship_fact_projection_smoke"
    / "scripts"
    / "create_smoke_fixture_rhino.py"
)

SOURCE = "relationship_fact_smoke"

EXPECTED_FACT = {
    "relationship": "connects",
    "fromFeature": "smoke_member.start",
    "toFeature": "smoke_joint.point",
    "contactKind": "point_to_point",
    "provenance": "authored_assembly_graph",
    "status": "accepted",
    "graphSource": SOURCE,
    "graphRevision": "smoke001",
    "pose": "smoke_pose",
}

REQUIRED_CONTEXT_SUBSTRINGS = [
    "connects",
    "connected by",
    "smoke_member.start -> smoke_joint.point",
    "point_to_point",
    "accepted",
    "authored_assembly_graph",
]


def _json_from_output(output: str) -> dict[str, Any]:
    start = output.find("{")
    end = output.rfind("}")
    assert start >= 0 and end > start, f"rhino_execute output contained no JSON object: {output!r}"
    return json.loads(output[start : end + 1])


async def _create_smoke_fixture() -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    script = SMOKE_SCRIPT.read_text(encoding="utf-8")
    result = await _mcp_tool_executor("rhino_execute", {"code": script})
    assert not _is_error(result), f"rhino_execute smoke fixture failed: {result!r}"
    output = result.get("output") or ""
    fixture = _json_from_output(output)
    assert fixture["source"] == SOURCE
    assert fixture["revision"] == "smoke001"
    assert fixture["pose"] == "smoke_pose"
    assert fixture["memberObjectId"]
    assert fixture["jointObjectId"]
    return fixture


def _extract_projected_facts(analytics, *, graph_source: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for source_id, target_id, _key, attrs in analytics.graph.edges(keys=True, data=True):
        if attrs.get("projectionKind") != "relationship_fact_v1":
            continue
        if attrs.get("graphSource") != graph_source:
            continue
        facts.append(
            {
                "relationship": attrs.get("semanticRelationshipType") or attrs.get("relationship"),
                "fromFeature": attrs.get("fromFeature"),
                "toFeature": attrs.get("toFeature"),
                "contactKind": attrs.get("contactKind"),
                "provenance": attrs.get("provenance"),
                "status": attrs.get("status"),
                "graphSource": attrs.get("graphSource"),
                "graphRevision": attrs.get("graphRevision"),
                "pose": attrs.get("pose"),
                "fromObjectId": str(source_id),
                "toObjectId": str(target_id),
            }
        )
    return sorted(
        facts,
        key=lambda fact: (
            fact["relationship"],
            fact["fromFeature"],
            fact["toFeature"],
            fact["graphSource"],
            fact["graphRevision"],
            fact["pose"],
        ),
    )


async def test_relationship_fact_smoke_roundtrip_live(fresh_document):
    from rook.scene.relationship_fact_projection import project_relationship_facts_for_tool
    from rook.scene.relationship_fact_roundtrip import compare_roundtrip
    from rook.scene.scene_graph import get_scene_graph
    from rook.server import _call_tool_dispatch

    fixture = await _create_smoke_fixture()
    sg = get_scene_graph()

    projection = await project_relationship_facts_for_tool(
        graph_source=SOURCE,
        strict=True,
        analytics=sg,
    )

    assert projection["success"] is True, f"projection failed: {projection!r}"
    counts = projection["counts"]
    assert counts["relationshipFactCount"] == 1
    assert counts["projectedEdgeCount"] == 1
    assert counts["skippedFactCount"] == 0

    actual_facts = _extract_projected_facts(sg, graph_source=SOURCE)
    context_result = await _call_tool_dispatch(
        "scene_context",
        {
            "object_ids": [fixture["memberObjectId"], fixture["jointObjectId"]],
            "sync": False,
        },
    )
    assert context_result["success"] is True, f"scene_context failed: {context_result!r}"

    report = compare_roundtrip(
        expected_facts=[EXPECTED_FACT],
        actual_facts=actual_facts,
        context_text=context_result["data"],
        required_substrings=REQUIRED_CONTEXT_SUBSTRINGS,
    )
    if not report["success"]:
        report["fixture"] = {
            "memberObjectId": fixture["memberObjectId"],
            "jointObjectId": fixture["jointObjectId"],
            "clearedObjectCount": fixture.get("clearedObjectCount"),
        }
        report["actualFacts"] = actual_facts
        pytest.fail(json.dumps(report, indent=2, sort_keys=True))
```

- [ ] **Step 2: Run the live adapter without Rhino and verify it skips or reports live unavailability**

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_relationship_fact_roundtrip_live.py -q
```

Expected without a reachable Rhino/Rook session:

```text
1 skipped
```

If Rhino is reachable, expected:

```text
1 passed
```

If the test fails because `rook.scene.relationship_fact_roundtrip` is missing, Task 2 was not completed in the current branch.

- [ ] **Step 3: Run the live adapter against a blank throwaway Rhino document when available**

Prerequisites:

- Rhino is running with RookNative loaded.
- The document can be replaced by `fresh_document`.
- If using harness scoping, `ROOK_RHINO_PORT` and `ROOK_RHINO_PROCESS_ID` are set together.

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_relationship_fact_roundtrip_live.py -q
```

Expected with Rhino available:

```text
1 passed
```

The test must create the fixture with `rhino_execute`, project through `project_relationship_facts_for_tool(..., analytics=sg)`, extract from `sg.graph`, and query `scene_context(sync=false)`.

- [ ] **Step 4: Commit the live adapter**

Run:

```powershell
git add mcp_server/tests/test_relationship_fact_roundtrip_live.py
git commit -m "test: add relationship fact roundtrip live smoke"
```

## Task 4: Smoke README Harness Instructions

**Files:**

- Modify: `experiments/relationship_fact_projection_smoke/README.md`

- [ ] **Step 1: Update the smoke README**

Append this section to `experiments/relationship_fact_projection_smoke/README.md`:

````markdown

## Round-trip harness

The automated round-trip harness uses this fixture as its canonical live target:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_relationship_fact_roundtrip_live.py -q
```

The live test creates the fixture in Rhino, projects `relationship_fact_smoke` through
`project_relationship_facts_for_tool` in the pytest Python process, extracts projected
`relationship_fact_v1` edge attributes from the same `SceneGraphAnalytics` instance, and checks
`scene_context(sync=false)` for high-signal relationship evidence.

Pearson `g002` remains a manual follow-up gate. It should not be required for this smoke harness
to pass.
````

- [ ] **Step 2: Run the README source test**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection_smoke_fixture.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 3: Commit the README update**

Run:

```powershell
git add experiments/relationship_fact_projection_smoke/README.md
git commit -m "docs: document relationship fact roundtrip smoke"
```

## Task 5: Focused Verification

**Files:**

- Verify: `mcp_server/tests/test_relationship_fact_roundtrip.py`
- Verify: `mcp_server/tests/test_relationship_fact_roundtrip_live.py`
- Verify: existing projection tests.

- [ ] **Step 1: Run the pure and projection-focused tests**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_relationship_fact_roundtrip.py `
  mcp_server/tests/test_relationship_fact_projection.py `
  mcp_server/tests/test_relationship_fact_projection_tool.py `
  mcp_server/tests/test_relationship_fact_projection_smoke_fixture.py `
  mcp_server/tests/test_bim_relationship_projection.py `
  mcp_server/tests/test_bim_relationship_projection_tool.py `
  -q
```

Expected:

```text
92 passed
```

If the count differs because upstream tests changed, verify there are zero failures and no unexpected skips in this focused pure suite.

- [ ] **Step 2: Run the live smoke harness when Rhino is available**

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_relationship_fact_roundtrip_live.py -q
```

Expected without Rhino:

```text
1 skipped
```

Expected with Rhino:

```text
1 passed
```

Record which result occurred in the final implementation summary.

- [ ] **Step 3: Run whitespace and committed-diff checks**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected:

```text
git diff --check exits 0
## codex/pearson-robot-roundtrip-harness...origin/codex/pearson-robot-roundtrip-harness
```

- [ ] **Step 4: Push the branch**

Run:

```powershell
git push
```

Expected:

```text
codex/pearson-robot-roundtrip-harness -> codex/pearson-robot-roundtrip-harness
```

## Self-Review Checklist

- [ ] The live adapter projects and extracts graph facts in the same pytest Python process.
- [ ] The live adapter does not inspect a local graph after projecting through an external MCP process.
- [ ] Structured facts are the primary contract.
- [ ] Runtime object ids are included only as evidence in actual facts and failure reports.
- [ ] Context checks use substrings, not full-line snapshots.
- [ ] The pure comparator has no Rhino, NetworkX, MCP, or filesystem dependencies.
- [ ] Pearson `g002` remains documented as manual only.
- [ ] No geometry inference or new MCP tool surface is introduced.
