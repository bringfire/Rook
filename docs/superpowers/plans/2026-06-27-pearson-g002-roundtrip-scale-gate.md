# Pearson g002 Round-Trip Scale Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a skippable live pytest gate proving Pearson `g002` relationship facts round-trip at 56-fact scale, plus cheap non-live drift checks for the checked-in fixture script.

**Architecture:** Keep this as test harness infrastructure, not a new product surface. Add one focused test-support module for Pearson graph expectations and fixture parsing, one non-live pytest file for pure checks, and one `requires_rhino` live pytest file that mirrors the existing smoke round-trip adapter. Reuse `compare_roundtrip`, `project_relationship_facts_for_tool`, `get_scene_graph`, `_mcp_tool_executor`, and `_call_tool_dispatch`; do not add MCP tools or change `scene_context` rendering.

**Tech Stack:** Python 3, pytest, asyncio pytest marker, NetworkX-backed `SceneGraphAnalytics`, existing Rook MCP source-level dispatch helpers, Rhino live fixture execution through `rhino_execute`.

---

## 1. Reviewer Backfill

Work in the isolated Pearson worktree only:

```text
C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph
```

Current branch:

```text
codex/pearson-robot-g002-roundtrip-gate
```

Approved design spec:

```text
docs/superpowers/specs/2026-06-27-pearson-g002-roundtrip-scale-gate-design.md
```

Do not touch the main checkout at:

```text
C:/Users/aryan/source/repos/Rook
```

The main checkout has unrelated local state and is reserved for other work.

The lower stack already has:

- `mcp_server/src/rook/scene/relationship_fact_roundtrip.py`
- `mcp_server/tests/test_relationship_fact_roundtrip.py`
- `mcp_server/tests/test_relationship_fact_roundtrip_live.py`
- `mcp_server/src/rook/scene/relationship_fact_projection.py`

The existing smoke live test is the pattern to follow:

```text
mcp_server/tests/test_relationship_fact_roundtrip_live.py
```

The Pearson source artifacts are:

```text
experiments/pearson_robot_skeleton_graph/assembly_graph.json
experiments/pearson_robot_skeleton_graph/generated/skeleton_graph_rhino.py
```

Expected fixture summary from the generated Rhino script:

```json
{
  "success": true,
  "revision": "g002",
  "pose_count": 2,
  "joint_count": 30,
  "member_count": 28,
  "feature_count": 86,
  "relationship_marker_count": 56,
  "created_count": 200
}
```

`deleted_count` is intentionally variable.

Expected semantic relationship scale:

```text
28 relationships * 2 poses = 56 projected facts
rest_t_pose = 28
reclined_robot = 28
```

## 2. File Structure

Create:

```text
mcp_server/tests/pearson_g002_roundtrip_helpers.py
```

Responsibility: Pure test-support helpers for loading `assembly_graph.json`, extracting the embedded generated-script graph payload, building expected normalized facts, extracting projected `relationship_fact_v1` edge facts from `SceneGraphAnalytics.graph`, computing per-pose counts, and formatting Pearson mismatch reports.

Create:

```text
mcp_server/tests/test_pearson_g002_roundtrip_gate.py
```

Responsibility: Non-live tests for expected fact expansion, generated-script drift, and mismatch report enrichment. These tests must not require Rhino.

Create:

```text
mcp_server/tests/test_pearson_g002_roundtrip_gate_live.py
```

Responsibility: Skippable `requires_rhino` live test. It resets to a throwaway document via `fresh_document`, executes the checked-in Pearson generated fixture script through `rhino_execute`, projects `pearson_robot_skeleton_graph` revision `g002` in the pytest process, inspects the same `SceneGraphAnalytics.graph`, compares 56 structured facts, and checks small `scene_context(sync=false)` evidence.

Modify:

```text
experiments/relationship_fact_projection_smoke/README.md
```

Responsibility: Replace the stale sentence that says Pearson `g002` remains manual-only with a short pointer to the new Pearson live scale gate command.

Do not modify:

```text
mcp_server/src/rook/scene/relationship_fact_projection.py
mcp_server/src/rook/scene/relationship_fact_roundtrip.py
mcp_server/src/rook/scene/scene_graph.py
mcp_server/src/rook/server.py
```

If implementation appears to require modifying those files, stop and re-evaluate the plan; the approved slice is a test harness gate.

## 3. Task 1: Add Pure Pearson Helper Tests First

**Files:**

- Create: `mcp_server/tests/test_pearson_g002_roundtrip_gate.py`
- Create: `mcp_server/tests/pearson_g002_roundtrip_helpers.py`

- [ ] **Step 1: Create the non-live failing tests**

Create `mcp_server/tests/test_pearson_g002_roundtrip_gate.py` with this content:

```python
from __future__ import annotations

from pathlib import Path

from .pearson_g002_roundtrip_helpers import (
    GENERATED_SCRIPT_PATH,
    GRAPH_PATH,
    build_expected_facts,
    embedded_graph_from_generated_script,
    load_assembly_graph,
    pearson_fact_counts_by_pose,
    pearson_mismatch_report,
)


def test_pearson_expected_facts_expand_across_both_poses():
    graph = load_assembly_graph(GRAPH_PATH)

    facts = build_expected_facts(graph)

    assert len(graph["relationships"]) == 28
    assert set(graph["poses"]) == {"rest_t_pose", "reclined_robot"}
    assert len(facts) == 56
    assert pearson_fact_counts_by_pose(facts) == {
        "reclined_robot": 28,
        "rest_t_pose": 28,
    }
    assert {
        "relationship": "connects",
        "fromFeature": "spine_base_to_spine_top.start",
        "toFeature": "spine_base.point",
        "contactKind": "point_to_point",
        "provenance": "authored_assembly_graph",
        "status": "accepted",
        "graphSource": "pearson_robot_skeleton_graph",
        "graphRevision": "g002",
        "pose": "rest_t_pose",
    } in facts
    assert {
        "relationship": "connects",
        "fromFeature": "right_knee_to_right_foot.end",
        "toFeature": "right_foot.point",
        "contactKind": "point_to_point",
        "provenance": "authored_assembly_graph",
        "status": "accepted",
        "graphSource": "pearson_robot_skeleton_graph",
        "graphRevision": "g002",
        "pose": "reclined_robot",
    } in facts


def test_generated_pearson_fixture_payload_matches_assembly_graph():
    assembly_graph = load_assembly_graph(GRAPH_PATH)
    embedded_graph = embedded_graph_from_generated_script(GENERATED_SCRIPT_PATH)

    assert embedded_graph["revision"] == assembly_graph["revision"] == "g002"
    assert set(embedded_graph["poses"]) == set(assembly_graph["poses"])
    assert len(embedded_graph["nodes"]) == len(assembly_graph["nodes"]) == 15
    assert len(embedded_graph["members"]) == len(assembly_graph["members"]) == 14
    assert len(embedded_graph["features"]) == len(assembly_graph["features"]) == 43
    assert len(embedded_graph["relationships"]) == len(assembly_graph["relationships"]) == 28
    assert {
        relationship["id"] for relationship in embedded_graph["relationships"]
    } == {
        relationship["id"] for relationship in assembly_graph["relationships"]
    }


def test_pearson_mismatch_report_adds_pose_counts():
    report = pearson_mismatch_report(
        roundtrip_report={
            "success": False,
            "missingFacts": [{"pose": "rest_t_pose"}],
            "unexpectedFacts": [],
            "wrongMetadata": [],
            "missingContextSubstrings": [],
        },
        actual_facts=[
            {"pose": "rest_t_pose"},
            {"pose": "reclined_robot"},
            {"pose": "reclined_robot"},
        ],
        expected_facts=[
            {"pose": "rest_t_pose"},
            {"pose": "rest_t_pose"},
            {"pose": "reclined_robot"},
        ],
        fixture_summary={"revision": "g002", "created_count": 200},
    )

    assert report["success"] is False
    assert report["expectedByPose"] == {"reclined_robot": 1, "rest_t_pose": 2}
    assert report["actualByPose"] == {"reclined_robot": 2, "rest_t_pose": 1}
    assert report["fixtureSummary"] == {"revision": "g002", "created_count": 200}
```

- [ ] **Step 2: Run tests to verify they fail because the helper module is missing**

Run:

```powershell
python -m pytest mcp_server/tests/test_pearson_g002_roundtrip_gate.py -q
```

Expected: FAIL during collection with:

```text
ModuleNotFoundError: No module named 'mcp_server.tests.pearson_g002_roundtrip_helpers'
```

The exact module path in the error may be shortened by pytest, but it should fail because `pearson_g002_roundtrip_helpers.py` does not exist.

- [ ] **Step 3: Create the helper module**

Create `mcp_server/tests/pearson_g002_roundtrip_helpers.py` with this content:

```python
from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
GRAPH_SOURCE = "pearson_robot_skeleton_graph"
GRAPH_PATH = REPO_ROOT / "experiments" / "pearson_robot_skeleton_graph" / "assembly_graph.json"
GENERATED_SCRIPT_PATH = (
    REPO_ROOT
    / "experiments"
    / "pearson_robot_skeleton_graph"
    / "generated"
    / "skeleton_graph_rhino.py"
)

STRUCTURED_FACT_FIELDS = (
    "relationship",
    "fromFeature",
    "toFeature",
    "contactKind",
    "provenance",
    "status",
    "graphSource",
    "graphRevision",
    "pose",
)

FACT_SORT_FIELDS = (
    "pose",
    "relationship",
    "fromFeature",
    "toFeature",
    "graphSource",
    "graphRevision",
)


def load_assembly_graph(path: Path = GRAPH_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def embedded_graph_from_generated_script(path: Path = GENERATED_SCRIPT_PATH) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "GRAPH" for target in node.targets):
            continue
        value = node.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "loads"
            and isinstance(value.func.value, ast.Name)
            and value.func.value.id == "json"
            and len(value.args) == 1
            and isinstance(value.args[0], ast.Constant)
            and isinstance(value.args[0].value, str)
        ):
            return json.loads(value.args[0].value)
    raise AssertionError(f"Could not find GRAPH = json.loads(...) in {path}")


def build_expected_facts(graph: dict[str, Any]) -> list[dict[str, Any]]:
    revision = graph["revision"]
    pose_ids = sorted(graph["poses"])
    expected: list[dict[str, Any]] = []
    for pose in pose_ids:
        for relationship in graph["relationships"]:
            expected.append(
                {
                    "relationship": relationship["type"],
                    "fromFeature": relationship["from"],
                    "toFeature": relationship["to"],
                    "contactKind": relationship["contact_kind"],
                    "provenance": relationship["provenance"],
                    "status": relationship.get("status", "accepted"),
                    "graphSource": GRAPH_SOURCE,
                    "graphRevision": revision,
                    "pose": pose,
                }
            )
    return sorted_facts(expected)


def sorted_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        facts,
        key=lambda fact: tuple(fact.get(field) for field in FACT_SORT_FIELDS),
    )


def pearson_fact_counts_by_pose(facts: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(fact.get("pose")) for fact in facts).items()))


def extract_projected_facts(analytics: Any) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for source_id, target_id, _key, attrs in analytics.graph.edges(keys=True, data=True):
        if attrs.get("projectionKind") != "relationship_fact_v1":
            continue
        if attrs.get("graphSource") != GRAPH_SOURCE:
            continue
        if attrs.get("graphRevision") != "g002":
            continue
        fact = {
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
        facts.append(fact)
    return sorted_facts(facts)


def semantic_fact(fact: dict[str, Any]) -> dict[str, Any]:
    return {field: fact.get(field) for field in STRUCTURED_FACT_FIELDS}


def semantic_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted_facts([semantic_fact(fact) for fact in facts])


def object_ids_for_feature_pairs(
    facts: list[dict[str, Any]],
    selected_pairs: list[tuple[str, str]],
) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    wanted = set(selected_pairs)
    for fact in facts:
        pair = (str(fact.get("fromFeature")), str(fact.get("toFeature")))
        if pair not in wanted:
            continue
        for key in ("fromObjectId", "toObjectId"):
            object_id = fact.get(key)
            if object_id and object_id not in seen:
                seen.add(object_id)
                ids.append(str(object_id))
    return ids


def pearson_mismatch_report(
    *,
    roundtrip_report: dict[str, Any],
    actual_facts: list[dict[str, Any]],
    expected_facts: list[dict[str, Any]],
    fixture_summary: dict[str, Any],
) -> dict[str, Any]:
    report = dict(roundtrip_report)
    report["expectedByPose"] = pearson_fact_counts_by_pose(expected_facts)
    report["actualByPose"] = pearson_fact_counts_by_pose(actual_facts)
    report["fixtureSummary"] = fixture_summary
    return report
```

- [ ] **Step 4: Run the non-live helper tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_pearson_g002_roundtrip_gate.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add mcp_server/tests/pearson_g002_roundtrip_helpers.py mcp_server/tests/test_pearson_g002_roundtrip_gate.py
git commit -m "test: add Pearson g002 expectation helpers"
```

## 4. Task 2: Add the Skippable Pearson Live Gate

**Files:**

- Create: `mcp_server/tests/test_pearson_g002_roundtrip_gate_live.py`
- Modify: `mcp_server/tests/pearson_g002_roundtrip_helpers.py`

- [ ] **Step 1: Add live test helper tests for fixture summary parsing**

Append these tests to `mcp_server/tests/test_pearson_g002_roundtrip_gate.py`:

```python
from .pearson_g002_roundtrip_helpers import (
    REQUIRED_FIXTURE_SUMMARY,
    assert_fixture_summary,
    json_from_execute_output,
    script_output_from_execute_result,
)


def test_json_from_execute_output_extracts_fixture_summary():
    output = 'noise before\\n{"success": true, "revision": "g002", "created_count": 200}\\nnoise after'

    assert json_from_execute_output(output) == {
        "success": True,
        "revision": "g002",
        "created_count": 200,
    }


def test_script_output_from_execute_result_accepts_output_and_data_shapes():
    assert script_output_from_execute_result({"output": "hello"}) == "hello"
    assert script_output_from_execute_result({"data": {"success": True}}) == '{"success": true}'


def test_assert_fixture_summary_checks_fixed_counts():
    summary = dict(REQUIRED_FIXTURE_SUMMARY, deleted_count=12)

    assert_fixture_summary(summary)
```

Because the import block in the file already imports from `.pearson_g002_roundtrip_helpers`, merge these names into the existing import instead of creating a duplicate import block. The final import should include:

```python
from .pearson_g002_roundtrip_helpers import (
    GENERATED_SCRIPT_PATH,
    GRAPH_PATH,
    REQUIRED_FIXTURE_SUMMARY,
    assert_fixture_summary,
    build_expected_facts,
    embedded_graph_from_generated_script,
    json_from_execute_output,
    load_assembly_graph,
    pearson_fact_counts_by_pose,
    pearson_mismatch_report,
    script_output_from_execute_result,
)
```

- [ ] **Step 2: Run the new helper tests and verify failure**

Run:

```powershell
python -m pytest mcp_server/tests/test_pearson_g002_roundtrip_gate.py -q
```

Expected: FAIL during import because `REQUIRED_FIXTURE_SUMMARY`, `assert_fixture_summary`, `json_from_execute_output`, and `script_output_from_execute_result` do not exist yet.

- [ ] **Step 3: Extend the helper module with fixture summary utilities**

Add this block to `mcp_server/tests/pearson_g002_roundtrip_helpers.py` after `GENERATED_SCRIPT_PATH`:

```python
REQUIRED_FIXTURE_SUMMARY = {
    "success": True,
    "revision": "g002",
    "pose_count": 2,
    "joint_count": 30,
    "member_count": 28,
    "feature_count": 86,
    "relationship_marker_count": 56,
    "created_count": 200,
}
```

Add these functions after `embedded_graph_from_generated_script`:

```python
def json_from_execute_output(output: str) -> dict[str, Any]:
    start = output.find("{")
    end = output.rfind("}")
    assert start >= 0 and end > start, f"rhino_execute output contained no JSON object: {output!r}"
    return json.loads(output[start : end + 1])


def script_output_from_execute_result(result: dict[str, Any]) -> str:
    output = result.get("output")
    if output is None:
        output = result.get("data", "")
    if isinstance(output, (dict, list)):
        return json.dumps(output)
    assert isinstance(output, str), f"rhino_execute output/data was not text-like: {result!r}"
    assert output, f"rhino_execute returned no script output: {result!r}"
    return output


def assert_fixture_summary(summary: dict[str, Any]) -> None:
    for key, expected in REQUIRED_FIXTURE_SUMMARY.items():
        assert summary.get(key) == expected, (
            f"fixture summary {key}={summary.get(key)!r}, expected {expected!r}; "
            f"summary={summary!r}"
        )
    assert "deleted_count" in summary, f"fixture summary missing deleted_count: {summary!r}"
```

- [ ] **Step 4: Run the non-live tests again**

Run:

```powershell
python -m pytest mcp_server/tests/test_pearson_g002_roundtrip_gate.py -q
```

Expected:

```text
6 passed
```

- [ ] **Step 5: Create the live test file**

Create `mcp_server/tests/test_pearson_g002_roundtrip_gate_live.py` with this content:

```python
from __future__ import annotations

import json
from typing import Any

import pytest

from .conftest import _is_error, fresh_document
from .pearson_g002_roundtrip_helpers import (
    GENERATED_SCRIPT_PATH,
    GRAPH_PATH,
    GRAPH_SOURCE,
    assert_fixture_summary,
    build_expected_facts,
    extract_projected_facts,
    json_from_execute_output,
    load_assembly_graph,
    object_ids_for_feature_pairs,
    pearson_mismatch_report,
    script_output_from_execute_result,
    semantic_facts,
)


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


SELECTED_CONTEXT_PAIRS = [
    ("spine_base_to_spine_top.start", "spine_base.point"),
    ("spine_top_to_left_shoulder.end", "left_shoulder.point"),
    ("left_hip_to_left_knee.end", "left_knee.point"),
    ("right_knee_to_right_foot.end", "right_foot.point"),
]

REQUIRED_CONTEXT_SUBSTRINGS = [
    "connects",
    "connected by",
    "spine_base_to_spine_top.start -> spine_base.point",
    "spine_top_to_left_shoulder.end -> left_shoulder.point",
    "left_hip_to_left_knee.end -> left_knee.point",
    "right_knee_to_right_foot.end -> right_foot.point",
    "point_to_point",
    "accepted",
    "authored_assembly_graph",
]


async def _create_pearson_fixture() -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    script = GENERATED_SCRIPT_PATH.read_text(encoding="utf-8")
    result = await _mcp_tool_executor("rhino_execute", {"code": script})
    assert not _is_error(result), f"rhino_execute Pearson fixture failed: {result!r}"
    summary = json_from_execute_output(script_output_from_execute_result(result))
    assert_fixture_summary(summary)
    return summary


async def test_pearson_g002_roundtrip_scale_gate_live(fresh_document):
    from rook.scene.relationship_fact_projection import project_relationship_facts_for_tool
    from rook.scene.relationship_fact_roundtrip import compare_roundtrip
    from rook.scene.scene_graph import get_scene_graph
    from rook.server import _call_tool_dispatch

    expected_facts = build_expected_facts(load_assembly_graph(GRAPH_PATH))
    fixture_summary = await _create_pearson_fixture()
    sg = get_scene_graph()

    projection = await project_relationship_facts_for_tool(
        graph_source=GRAPH_SOURCE,
        graph_revision="g002",
        strict=True,
        analytics=sg,
    )

    assert projection["success"] is True, f"projection failed: {projection!r}"
    counts = projection["counts"]
    assert counts["relationshipFactCount"] == 56
    assert counts["projectedEdgeCount"] == 56
    assert counts["skippedFactCount"] == 0
    assert projection["byRelationshipType"] == {"connects": 56}
    assert projection["byPose"] == {
        "reclined_robot": 28,
        "rest_t_pose": 28,
    }

    actual_facts = extract_projected_facts(sg)
    selected_object_ids = object_ids_for_feature_pairs(actual_facts, SELECTED_CONTEXT_PAIRS)
    assert selected_object_ids, f"no owner object ids found for selected context pairs: {actual_facts!r}"

    context_result = await _call_tool_dispatch(
        "scene_context",
        {
            "object_ids": selected_object_ids,
            "sync": False,
        },
    )
    assert context_result["success"] is True, f"scene_context failed: {context_result!r}"

    report = compare_roundtrip(
        expected_facts=expected_facts,
        actual_facts=semantic_facts(actual_facts),
        context_text=context_result["data"],
        required_substrings=REQUIRED_CONTEXT_SUBSTRINGS,
    )
    if not report["success"]:
        enriched = pearson_mismatch_report(
            roundtrip_report=report,
            actual_facts=actual_facts,
            expected_facts=expected_facts,
            fixture_summary=fixture_summary,
        )
        enriched["selectedObjectIds"] = selected_object_ids
        enriched["projectionCounts"] = counts
        pytest.fail(json.dumps(enriched, indent=2, sort_keys=True))
```

- [ ] **Step 6: Run the live test without Rhino or with unavailable Rhino to verify clean skip**

Run when no reachable Rhino/Rook target is available:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_pearson_g002_roundtrip_gate_live.py -q
```

Expected:

```text
1 skipped
```

If Rhino is currently open and reachable, this may run instead of skipping. In that case it should either pass or expose a real implementation/runtime issue to debug under Task 3.

- [ ] **Step 7: Run the live test with a throwaway Rhino document**

Prerequisite: Rhino is open with Rook loaded. The test uses `fresh_document`, which replaces the active document. Use only a throwaway document.

Run:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_pearson_g002_roundtrip_gate_live.py -q
```

Expected:

```text
1 passed
```

If the test fails on missing context substrings, inspect `context_result["data"]` in the failure. Do not add graph source, graph revision, or pose as required context strings; those belong to structured fact assertions in this slice.

- [ ] **Step 8: Commit Task 2**

Run:

```powershell
git add mcp_server/tests/pearson_g002_roundtrip_helpers.py mcp_server/tests/test_pearson_g002_roundtrip_gate.py mcp_server/tests/test_pearson_g002_roundtrip_gate_live.py
git commit -m "test: add Pearson g002 roundtrip live gate"
```

## 5. Task 3: Update Experiment Documentation

**Files:**

- Modify: `experiments/relationship_fact_projection_smoke/README.md`

- [ ] **Step 1: Update the stale manual-only Pearson note**

In `experiments/relationship_fact_projection_smoke/README.md`, replace the final paragraph:

```markdown
Pearson `g002` remains a manual follow-up gate. It should not be required for this smoke harness
to pass.
```

with:

````markdown
The Pearson `g002` scale gate is automated separately as a skippable live test:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_pearson_g002_roundtrip_gate_live.py -q
```

It remains outside this smoke fixture so the five-object harness stays the smallest closed-loop
debug target.
````

When editing markdown, keep the nested code fence valid. The replacement block should render as one paragraph, one PowerShell code block, and one final paragraph.

- [ ] **Step 2: Run markdown and whitespace checks**

Run:

```powershell
git diff --check
```

Expected: no output and exit code `0`.

- [ ] **Step 3: Commit Task 3**

Run:

```powershell
git add experiments/relationship_fact_projection_smoke/README.md
git commit -m "docs: document Pearson g002 scale gate"
```

## 6. Task 4: Focused Verification and Self-Review

**Files:**

- Verify only; no planned file edits.

- [ ] **Step 1: Run focused non-live tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_roundtrip.py mcp_server/tests/test_pearson_g002_roundtrip_gate.py -q
```

Expected:

```text
11 passed
```

Count explanation: existing `test_relationship_fact_roundtrip.py` has 5 tests and the new non-live Pearson file has 6 tests.

- [ ] **Step 2: Run focused projection tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection.py mcp_server/tests/test_relationship_fact_projection_tool.py -q
```

Expected: all tests pass. Based on the current branch this is expected to be:

```text
29 passed
```

If the count differs because upstream tests changed, verify there are no failures and record the actual count in the final handoff.

- [ ] **Step 3: Run live Pearson gate**

Run with Rhino/Rook available in a throwaway document:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_pearson_g002_roundtrip_gate_live.py -q
```

Expected with Rhino available:

```text
1 passed
```

Expected without Rhino available:

```text
1 skipped
```

Do not claim end-to-end live pass unless this command actually reports `1 passed`.

- [ ] **Step 4: Run combined focused suite**

Run:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_roundtrip.py mcp_server/tests/test_relationship_fact_projection.py mcp_server/tests/test_relationship_fact_projection_tool.py mcp_server/tests/test_pearson_g002_roundtrip_gate.py -q
```

Expected: all tests pass. If any unrelated live-Rhino tests are collected accidentally, narrow the command back to the explicit files above.

- [ ] **Step 5: Run whitespace and commit checks**

Run:

```powershell
git diff --check
git show --check --stat HEAD
git status --short --branch
```

Expected:

```text
git diff --check
```

prints nothing and exits `0`.

```text
git show --check --stat HEAD
```

prints the most recent commit metadata/stat with no whitespace errors.

```text
git status --short --branch
```

shows the Pearson branch and no unstaged/staged changes:

```text
## codex/pearson-robot-g002-roundtrip-gate...origin/codex/pearson-robot-g002-roundtrip-gate [ahead N]
```

- [ ] **Step 6: Push the branch**

Run:

```powershell
git push
```

Expected: pushes the new commits to:

```text
origin/codex/pearson-robot-g002-roundtrip-gate
```

## 7. Self-Review Checklist

Before asking for review, confirm:

- [ ] The live test uses `generated/skeleton_graph_rhino.py`; it does not regenerate it.
- [ ] The live test asserts the generated script's actual summary keys and fixed counts.
- [ ] `deleted_count` is checked for presence only, not fixed value.
- [ ] Expected facts come from `assembly_graph.json` and expand across both poses.
- [ ] Actual facts come from `SceneGraphAnalytics.graph` after source-level projection in the same pytest process.
- [ ] `graphSource`, `graphRevision`, and `pose` are asserted through structured facts, not required context substrings.
- [ ] Context checks remain small and substring-based.
- [ ] No new MCP tool, server route, or scene graph query surface was added.
- [ ] The smoke fixture README no longer says Pearson `g002` is manual-only.
- [ ] The branch remains clean and pushed.

## 8. Handoff Notes

When reporting completion, include:

- commit hashes for the helper/test/doc commits;
- exact non-live pytest command output;
- exact live pytest outcome (`1 passed` or `1 skipped`);
- whether Rhino was available for the live gate;
- any residual risk, especially if the live command skipped instead of passing.
