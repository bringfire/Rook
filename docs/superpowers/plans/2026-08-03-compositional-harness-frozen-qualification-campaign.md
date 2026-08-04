# Compositional Harness Frozen Qualification Campaign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one private, single-row operator command that runs the approved 23-row frozen compositional-harness campaign through existing Planner, Worker, semantic compiler, causal fake, native result, and optional live Grasshopper boundaries without changing product code.

**Architecture:** One script-local closed campaign table owns exact cases, model identities, generation settings, provider schema materialization, structural-tier observation, mechanical promotion, one causal fake, and ordinary local JSON projection. Each invocation executes at most one row through the existing Slice 1 or Slice 2 runner; prior ordinary result files are read only to select the frozen finalist pair, count identical repetitions, and gate the two separately authorized live rows.

**Tech Stack:** Python 3.12.12, LiteLLM 1.89.4, pytest, existing semantic-graph modules, existing Worker adapter/handoff, existing `ToolDispatcher`, `tiktoken` already present through the locked environment, PowerShell verification commands.

## Global Constraints

- Baseline is exact `8baf325a459ec9bb53cae24b1af0fab452b3001e`.
- Implement from the existing clean isolated worktree `C:/UDEV/Rook/.worktrees/compositional-harness-frozen-qualification-campaign-design`.
- Do not modify the primary checkout.
- Production code, prompts, schemas, loaders, compiler rules, runner behavior, generation settings, primitive contracts, and receipt interpretation remain unchanged.
- Runtime implementation scope is exactly `scripts/compositional_harness_qualification_campaign.py` plus `mcp_server/tests/test_compositional_harness_qualification_campaign.py`.
- Documentation scope is the already-approved specification plus this plan ledger.
- Do not modify any file under `mcp_server/src`, `src/`, `knowledge/`, or existing scripts/tests.
- No provider, Ollama, Rhino, Grasshopper, or Worker-box contact occurs during implementation or review.
- Tests patch transport and tool boundaries before invoking any path that could contact an external system.
- The script executes one campaign row per process. It does not loop through the matrix or select replacement rows.
- The scored roster, priority order, six case intents, structural facts, Planner `8192` token bound, Worker `1024` token bound, temperature `0`, `max_retries=0`, and timeout `120` are exact code-owned constants.
- Stage B deterministic rows perform zero Worker calls. Stage B Worker-leaf rows perform one fake Worker transport call and zero Worker model calls.
- `structural_tier_attained` is campaign telemetry derived from the admitted canonical graph, not a native outcome or semantic-fidelity claim.
- Medium cases require exactly one weakly connected component. Other tiers do not add a connectivity condition.
- Planner and Worker finalist eligibility and priority are mechanical and frozen before contact.
- A failed Stage D repetition blocks Stage E; no substitute pair is promoted.
- Stage E is limited to one maximum deterministic row and one maximum Worker-leaf row, each separately authorized after merge.
- The complete campaign ceiling is 23 scored rows. Identical prior rows count once.
- The exact ceiling reconciliation is Stage A `6`, Stage B `6`, Stage C `3`,
  Stage D at most `6`, and Stage E `2`.
- No retry, fallback, repair, update, cleanup, resnapshot, alternate model, output patching, benchmark scheduler, registry, manifest, archive, dataset manager, or product UI is added.
- Raw local result files are sensitive disposable diagnostic data and remain outside the repository.
- Use Inline Execution for implementation. These case, promotion, execution, and projection rules form one coupled script; do not dispatch subagents.
- Mandatory independent review stops follow Tasks 1, 2, and 3.
- Hard growth stop: if the new operator script exceeds 800 nonblank source lines, stop and report the concrete existing API constraint before adding more code. Do not introduce another module to evade the limit.

## File Structure

### Create: `scripts/compositional_harness_qualification_campaign.py`

One private operator command with these responsibilities:

- exact candidate/case/row constants;
- exact provider-specific transport construction;
- structural-tier projection;
- one causal fake tool executor;
- one-row deterministic or Worker-leaf invocation;
- direct native-result projection;
- mechanical promotion and Stage D/E gating from explicitly supplied prior result files;
- exact live-target discovery and frozen-context construction for Stage E only;
- one exclusive bounded JSON result file;
- one bounded stdout summary.

It is not imported by production modules.

### Create: `mcp_server/tests/test_compositional_harness_qualification_campaign.py`

Focused no-contact tests that load the script by path and prove:

- exact constants, cases, legal reference graphs, and transport materialization;
- structural-tier observation, including medium weak connectivity;
- causal fake behavior and exact native call prefixes;
- Stage B fake Worker isolation;
- mechanical finalist selection and promotion blocking;
- CLI refusal and one-row behavior;
- result projection, sensitive stdout exclusion, and exclusive local writing;
- Stage E cannot construct a dispatcher or contact Grasshopper until every gate
  passes.

### Modify: `docs/superpowers/plans/2026-08-03-compositional-harness-frozen-qualification-campaign.md`

During execution only, check completed steps and record exact commands, counts,
scope, commit SHAs, and the no-contact statement. No other documentation is
required before implementation review.

---

### Task 1: Freeze cases, models, transports, and structural observation

**Files:**
- Create: `scripts/compositional_harness_qualification_campaign.py`
- Create: `mcp_server/tests/test_compositional_harness_qualification_campaign.py`

**Interfaces:**
- Consumes: `build_semantic_graph_response_schema()`, `build_worker_leaf_semantic_graph_response_schema()`, `load_semantic_graph()`, `compile_semantic_graph()`, `compile_semantic_graph_worker_leaf_partition()`, `LiteLLMWorkerTransport`, and `build_local_worker_response_schema()`.
- Produces: private `_Case`, `_Row`, `_CASES`, `_FIXED_ROWS`, `_structural_tier_attained()`, `_planner_transport_kwargs()`, and `_worker_transport_kwargs()` for Tasks 2–3.
- Produces no product API.

- [ ] **Step 1: Create an importable operator skeleton**

Add the script with imports, constants, exact private records, and deliberate
behavioral stubs:

```python
from __future__ import annotations

import json
import math
import os
import sys
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
MCP_ROOT = ROOT / "mcp_server"
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from rook.agent.local_worker_model_transport import (  # noqa: E402
    LiteLLMWorkerTransport,
    build_local_worker_response_schema,
)
from rook.agent.semantic_graph import (  # noqa: E402
    build_semantic_graph_response_schema,
    build_worker_leaf_semantic_graph_response_schema,
)

_PLANNER_MAX_TOKENS = 8192
_WORKER_MAX_TOKENS = 1024
_MAX_RETRIES = 0
_TEMPERATURE = 0
_TIMEOUT_S = 120.0
_MAX_RESULT_BYTES = 4 * 1024 * 1024

_PLANNER_PRIORITY = (
    "ollama_chat/qwen3.6:35b",
    "ollama_chat/gpt-oss:20b",
    "ollama_chat/qwen3:14b",
    "anthropic/claude-opus-4-6",
)
_WORKER_PRIORITY = (
    "ollama_chat/north-mini-code-1.0:q4_K_M",
    "ollama_chat/gemma4:12b-it-qat",
    "ollama_chat/qwen3-coder:30b-a3b-q4_K_M",
)

@dataclass(frozen=True, slots=True)
class _Case:
    case_id: str
    intent: str
    worker_leaf: bool
    node_count: int
    edge_count: int
    maximum_depth: int
    primitive_counts: tuple[tuple[str, int], ...]
    weak_component_count: int | None

@dataclass(frozen=True, slots=True)
class _Row:
    row_id: str
    stage: str
    case_id: str
    planner_model: str | None
    worker_model: str | None
    worker_mode: Literal["none", "fake", "model"]
    tool_mode: Literal["fake", "live"]

def _structural_tier_attained(case: _Case, canonical_graph: object) -> bool:
    raise NotImplementedError

def _planner_transport_kwargs(model: str, *, worker_leaf: bool) -> dict[str, Any]:
    raise NotImplementedError

def _worker_transport_kwargs(model: str) -> dict[str, Any]:
    raise NotImplementedError
```

Keep these six exact intent strings as code-owned case data; do not construct or
normalize them at runtime:

```text
minimum_deterministic
Create a Grasshopper semantic graph containing exactly one Number Slider and no edges.

minimum_worker_leaf
Create a Grasshopper semantic graph containing exactly one C# script leaf and one Construct Point. The C# leaf goal is to produce one finite numeric value for a point coordinate. Use the exact [] -> A:double interface, connect A to one compatible Number input, and use exactly two nodes and one edge.

medium_deterministic
Create one connected Grasshopper semantic graph containing exactly three Number Sliders, one Series, one Construct Point, one Polyline, and one Square Grid. Use exactly seven nodes, six edges, and maximum topological depth three. Satisfy every compiler-required input and choose any wiring admitted by the listed pin contracts.

medium_worker_leaf
Create one connected Grasshopper semantic graph containing exactly three Number Sliders, one Series, one Construct Point, one Polyline, one Square Grid, and one C# script leaf. The C# leaf goal is to produce one finite numeric value used by the deterministic graph. Use the exact [] -> A:double interface with no incoming edge and exactly one outgoing edge to a compatible Number input. Use exactly eight nodes, seven edges, and maximum topological depth three. Satisfy every compiler-required input and choose any other wiring admitted by the listed pin contracts.

maximum_deterministic
Create one Grasshopper semantic DAG containing exactly six Number Sliders, three Series components, four Construct Points, two Square Grids, and one Polyline. Use exactly sixteen nodes, twenty-four edges, and maximum topological depth five. Satisfy every compiler-required input and choose any wiring admitted by the listed pin contracts.

maximum_worker_leaf
Create one Grasshopper semantic DAG containing exactly five Number Sliders, one C# script leaf, three Series components, four Construct Points, two Square Grids, and one Polyline. The C# leaf goal is to produce one finite numeric value used by the deterministic graph. Use the exact [] -> A:double interface with no incoming edge and exactly one outgoing edge to a compatible Number input. Use exactly sixteen nodes, twenty-four edges, and maximum topological depth five. Satisfy every compiler-required input and choose any other wiring admitted by the listed pin contracts.
```

Construct `_CASES` with these exact structural facts:

```python
(
    # id, leaf, nodes, edges, depth, primitive multiset, weak components
    ("minimum_deterministic", False, 1, 0, 0,
     (("number_slider", 1),), None),
    ("minimum_worker_leaf", True, 2, 1, 1,
     (("construct_point", 1), ("csharp_script", 1)), None),
    ("medium_deterministic", False, 7, 6, 3,
     (("construct_point", 1), ("number_slider", 3), ("polyline", 1),
      ("series", 1), ("square_grid", 1)), 1),
    ("medium_worker_leaf", True, 8, 7, 3,
     (("construct_point", 1), ("csharp_script", 1),
      ("number_slider", 3), ("polyline", 1), ("series", 1),
      ("square_grid", 1)), 1),
    ("maximum_deterministic", False, 16, 24, 5,
     (("construct_point", 4), ("number_slider", 6), ("polyline", 1),
      ("series", 3), ("square_grid", 2)), None),
    ("maximum_worker_leaf", True, 16, 24, 5,
     (("construct_point", 4), ("csharp_script", 1),
      ("number_slider", 5), ("polyline", 1), ("series", 3),
      ("square_grid", 2)), None),
)
```

Define the fifteen fixed Stage A–C rows explicitly:

- `stage_a.minimum_deterministic`, `stage_a.minimum_worker_leaf`,
  `stage_a.medium_deterministic`, `stage_a.medium_worker_leaf`,
  `stage_a.maximum_deterministic`, and `stage_a.maximum_worker_leaf` use Opus;
  deterministic rows use no Worker, and leaf rows use Qwen-Coder Q4.
- `stage_b.qwen36.medium_deterministic`,
  `stage_b.qwen36.medium_worker_leaf`,
  `stage_b.gpt_oss.medium_deterministic`,
  `stage_b.gpt_oss.medium_worker_leaf`,
  `stage_b.qwen14.medium_deterministic`, and
  `stage_b.qwen14.medium_worker_leaf` use their named non-control Planner;
  deterministic rows use `worker_mode="none"`, leaf rows use
  `worker_mode="fake"`, and every Stage B `worker_model` is null.
- `stage_c.qwen_coder`, `stage_c.north_mini`, and `stage_c.gemma4` use a fake
  Planner response for `medium_worker_leaf`, `planner_model=None`,
  `worker_mode="model"`, and exactly the named scored Worker.

Do not generate the fixed rows through a Cartesian-product helper. Explicit rows
make accidental additions visible in review.

- [ ] **Step 2: Add behavioral RED tests for the exact catalog**

Load the script by path using the established operator-test pattern:

```python
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "compositional_harness_qualification_campaign.py"

def _load_campaign():
    spec = importlib.util.spec_from_file_location(
        "compositional_harness_qualification_campaign", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
```

Add tests asserting:

```python
def test_catalog_is_exact_and_has_fifteen_fixed_stage_a_to_c_rows():
    assert tuple(CAMPAIGN._CASES) == (
        "minimum_deterministic",
        "minimum_worker_leaf",
        "medium_deterministic",
        "medium_worker_leaf",
        "maximum_deterministic",
        "maximum_worker_leaf",
    )
    assert len(CAMPAIGN._FIXED_ROWS) == 15
    assert CAMPAIGN._PLANNER_PRIORITY == (
        "ollama_chat/qwen3.6:35b",
        "ollama_chat/gpt-oss:20b",
        "ollama_chat/qwen3:14b",
        "anthropic/claude-opus-4-6",
    )
    assert CAMPAIGN._WORKER_PRIORITY == (
        "ollama_chat/north-mini-code-1.0:q4_K_M",
        "ollama_chat/gemma4:12b-it-qat",
        "ollama_chat/qwen3-coder:30b-a3b-q4_K_M",
    )
```

Assert exact Stage B ownership:

```python
def test_stage_b_rows_freeze_worker_ownership():
    rows = [row for row in CAMPAIGN._FIXED_ROWS.values() if row.stage == "B"]
    assert len(rows) == 6
    assert all(
        row.worker_mode == ("fake" if CAMPAIGN._CASES[row.case_id].worker_leaf else "none")
        for row in rows
    )
    assert all(row.worker_model is None for row in rows)
```

Run the single catalog test and require a behavioral failure from the stub or
missing constants rather than collection failure.

- [ ] **Step 3: Run the catalog RED**

Run:

```powershell
cd C:/UDEV/Rook/.worktrees/compositional-harness-frozen-qualification-campaign-design/mcp_server
uv run --frozen --extra test pytest -q tests/test_compositional_harness_qualification_campaign.py -k "catalog or stage_b_rows"
```

Expected: tests collect and fail against incomplete `_CASES`, `_FIXED_ROWS`, or
the `NotImplementedError` boundary.

- [ ] **Step 4: Add exact legal reference-graph builders in the test module**

Keep legal reference topology in tests only. Add helpers for nodes and edges:

```python
def _slider(node_id: str) -> dict[str, object]:
    return {
        "id": node_id,
        "primitive": "number_slider",
        "parameters": {
            "label": node_id,
            "minimum": 0,
            "maximum": 100,
            "initial": 2,
        },
    }

def _node(node_id: str, primitive: str) -> dict[str, object]:
    return {"id": node_id, "primitive": primitive, "parameters": {}}

def _leaf() -> dict[str, object]:
    return {
        "id": "code_leaf",
        "primitive": "csharp_script",
        "parameters": {
            "goal": "Produce one finite numeric value for the connected control input.",
            "interface": {
                "inputs": [],
                "outputs": [{"name": "A", "type": "double"}],
            },
        },
    }

def _edge(source: str, output: str, target: str, input_name: str) -> dict[str, str]:
    return {
        "from_node": source,
        "from_pin": output,
        "to_node": target,
        "to_pin": input_name,
    }
```

Implement six explicit reference payloads. Use these node IDs and exact edges so
no topology choice remains during implementation:

```text
minimum_deterministic
nodes: s1
edges: none

minimum_worker_leaf
nodes: code_leaf, p1
edges: code_leaf.A -> p1.x

medium_deterministic
nodes: s1, s2, s3, series1, p1, poly1, grid1
edges:
  s1.value -> series1.start
  s2.value -> series1.step
  s3.value -> series1.count
  series1.values -> p1.x
  p1.point -> poly1.vertices
  s1.value -> grid1.cell_size

medium_worker_leaf
nodes: code_leaf plus the medium_deterministic nodes
edges: the six medium_deterministic edges plus code_leaf.A -> p1.y

maximum_deterministic
nodes: s1..s6, series1..series3, p1..p4, grid1, grid2, poly1
edges:
  s1.value -> series1.start
  s2.value -> series1.step
  s3.value -> series1.count
  series1.values -> series2.start
  s4.value -> series2.step
  s5.value -> series2.count
  series2.values -> series3.start
  s5.value -> series3.step
  s6.value -> series3.count
  series1.values -> p1.x
  s1.value -> p1.y
  s2.value -> p1.z
  series2.values -> p2.x
  s3.value -> p2.y
  s4.value -> p2.z
  series3.values -> p3.x
  s5.value -> p3.y
  s6.value -> p3.z
  series3.values -> p4.x
  s1.value -> p4.y
  s2.value -> p4.z
  s3.value -> grid1.cell_size
  s4.value -> grid2.cell_size
  p4.point -> poly1.vertices

maximum_worker_leaf
nodes: s1..s5, code_leaf, series1..series3, p1..p4, grid1, grid2, poly1
edges:
  s1.value -> series1.start
  s2.value -> series1.step
  s3.value -> series1.count
  series1.values -> series2.start
  s4.value -> series2.step
  s5.value -> series2.count
  series2.values -> series3.start
  s4.value -> series3.step
  s5.value -> series3.count
  series1.values -> p1.x
  s1.value -> p1.y
  s2.value -> p1.z
  series2.values -> p2.x
  s3.value -> p2.y
  s4.value -> p2.z
  series3.values -> p3.x
  s5.value -> p3.y
  s1.value -> p3.z
  series3.values -> p4.x
  s2.value -> p4.y
  code_leaf.A -> p4.z
  s3.value -> grid1.cell_size
  s4.value -> grid2.cell_size
  p4.point -> poly1.vertices
```

For both maximum cases, group the 24 edges visibly as:

```text
9 Series-chain/control edges
12 Construct Point coordinate edges
2 Square Grid input edges
1 required Polyline vertices edge
```

In the Worker-leaf maximum, one of the twelve coordinate edges must be
`code_leaf.A -> p4.z`; no deterministic edge may also target `p4.z`.

- [ ] **Step 5: Add RED tests for legal compilation and tier observation**

For every reference payload:

```python
raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
loaded = load_semantic_graph(raw)
assert loaded.admitted is True
compiled = (
    compile_semantic_graph_worker_leaf_partition(loaded.graph)
    if case.worker_leaf
    else compile_semantic_graph(loaded.graph)
)
assert compiled.admitted is True
canonical = (
    compiled.partition.deterministic_plan.canonical_graph
    if case.worker_leaf
    else compiled.plan.canonical_graph
)
assert CAMPAIGN._structural_tier_attained(case, loaded.graph) is True
```

The structural projector must consume the complete admitted semantic graph,
including the Worker leaf. It must not inspect the deterministic plan after the
leaf has been removed.

Add mutations proving `False` for:

- one removed node;
- one removed edge;
- reduced maximum depth;
- changed primitive multiplicity;
- missing Worker cross-edge;
- a medium graph split into two weak components while retaining its counts;
- a valid alternative medium wiring with the same counts, depth, primitive
  multiplicities, and one weak component returning `True`.

Also serialize every exact test fixture with
`json.dumps(..., ensure_ascii=True, sort_keys=True, separators=(",", ":"))` and
measure its UTF-8 bytes plus local `cl100k_base` reference tokens. Assert the
maximum test fixture is at most 4,096 UTF-8 bytes and 1,024 reference tokens,
then require `_PLANNER_MAX_TOKENS == 8192` and at least eight times the observed
maximum token count. Record all six observed pairs in the Task 1 ledger. The
approved specification separately retains the qualification measurements
`175/46`, `395/98`, `1075/272`, `1351/338`, `2884/858`, and `2985/874`; this test
proves the independently reconstructed legal fixtures also fit the one uniform
budget without requiring byte identity from node-symbol spelling. This is an
offline regression only; it does not invoke a tokenizer service or model.

- [ ] **Step 6: Implement the structural projector minimally**

Use generic graph operations only:

```python
def _maximum_depth(graph: SemanticGraph) -> int:
    incoming = {node.id: [] for node in graph.nodes}
    for edge in graph.edges:
        incoming[edge.to_node].append(edge.from_node)
    memo: dict[str, int] = {}
    def visit(node_id: str) -> int:
        if node_id not in memo:
            parents = incoming[node_id]
            memo[node_id] = 0 if not parents else 1 + max(visit(p) for p in parents)
        return memo[node_id]
    return max(visit(node.id) for node in graph.nodes)

def _weak_component_count(graph: SemanticGraph) -> int:
    neighbors = {node.id: set() for node in graph.nodes}
    for edge in graph.edges:
        neighbors[edge.from_node].add(edge.to_node)
        neighbors[edge.to_node].add(edge.from_node)
    remaining = set(neighbors)
    components = 0
    while remaining:
        components += 1
        queue = deque([remaining.pop()])
        while queue:
            current = queue.popleft()
            for neighbor in neighbors[current]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
    return components
```

`_structural_tier_attained()` compares exact counts, sorted primitive counts,
maximum depth, Worker-leaf count, one cross-edge for leaf cases, and the optional
weak-component requirement. It never compares the exact edge set.

- [ ] **Step 7: Add transport-materialization RED tests**

Assert exact Planner settings for all four identities and both schemas:

```python
assert kwargs["generation_params"]["temperature"] == 0
assert kwargs["generation_params"]["max_tokens"] == 8192
assert kwargs["generation_params"]["max_retries"] == 0
assert kwargs["timeout_s"] == 120.0
```

For Anthropic:

```python
assert kwargs["structured_response_schema"] is None
assert kwargs["generation_params"]["response_format"]["type"] == "json_schema"
assert kwargs["generation_params"]["response_format"]["json_schema"]["strict"] is True
assert kwargs["generation_params"]["response_format"]["json_schema"]["schema"] == expected_schema
```

For every Ollama Planner:

```python
assert "response_format" not in kwargs["generation_params"]
assert kwargs["structured_response_schema"] == expected_schema
```

For every Worker:

```python
assert kwargs["generation_params"] == {
    "temperature": 0,
    "max_tokens": 1024,
    "max_retries": 0,
}
assert kwargs["structured_response_schema"] == build_local_worker_response_schema()
```

Mutate one returned schema and prove the next constructor call receives a fresh
schema from the existing builder.

- [ ] **Step 8: Implement exact transport kwargs**

Return constructor kwargs rather than constructing transports inside the pure
helpers. Use one provider predicate:

```python
if model.startswith("anthropic/"):
    generation_params["response_format"] = {
        "type": "json_schema",
        "json_schema": {
            "name": (
                "rook_semantic_graph_worker_leaf"
                if worker_leaf else "rook_semantic_graph"
            ),
            "strict": True,
            "schema": schema,
        },
    }
    structured_schema = None
elif model.startswith("ollama_chat/"):
    structured_schema = schema
else:
    raise ValueError("planner_provider_not_allowed")
```

Do not add a provider registry or accept model strings outside the exact scored
roster.

- [ ] **Step 9: Verify Task 1**

Run:

```powershell
cd C:/UDEV/Rook/.worktrees/compositional-harness-frozen-qualification-campaign-design/mcp_server
uv run --frozen --extra test pytest -q tests/test_compositional_harness_qualification_campaign.py tests/test_semantic_graph.py tests/test_semantic_graph_compiler.py tests/test_local_worker_model_transport.py
uv run --frozen python -m compileall -q ../scripts/compositional_harness_qualification_campaign.py tests/test_compositional_harness_qualification_campaign.py
git diff --check
```

Expected: all selected tests pass; no external contact.

- [ ] **Step 10: Record growth and commit Task 1**

Run:

```powershell
$script = '../scripts/compositional_harness_qualification_campaign.py'
$nonblank = (Get-Content -LiteralPath $script | Where-Object { $_.Trim() }).Count
"TASK1_NONBLANK_SCRIPT_LINES=$nonblank"
if ($nonblank -gt 800) { throw 'operator script exceeded reviewed hard stop' }
git add -- ../scripts/compositional_harness_qualification_campaign.py tests/test_compositional_harness_qualification_campaign.py
git commit -m "test: freeze compositional qualification cases"
```

Expected: one script/test commit, beneath the hard stop.

**Mandatory independent review stop:** Review exact cases, schemas, model roster,
structural observation, alternative-topology acceptance, and absence of external
contact before Task 2.

---

### Task 2: Add causal fake execution and ordinary result projection

**Files:**
- Modify: `scripts/compositional_harness_qualification_campaign.py`
- Modify: `mcp_server/tests/test_compositional_harness_qualification_campaign.py`

**Interfaces:**
- Consumes: Task 1 `_Case`, `_Row`, transport kwargs, structural projector, six reference payloads in tests, `SemanticGraphPlannerAdapter`, `run_semantic_graph_transaction()`, and `run_semantic_graph_single_worker_leaf_transaction()`.
- Produces: private `_CausalFakeTools`, `_RecordingTransport`, `_FakeWorkerTransport`, `_run_row_once()`, `_project_run_result()`, `_write_local_result()`, and `_bounded_summary()` for Task 3.

- [ ] **Step 1: Add a behavioral RED for the deterministic single-row path**

Create a recording fake Planner transport returning the medium deterministic raw
payload and a causal tool executor. Invoke `_run_row_once()` for the Stage A
medium deterministic row and assert:

```python
assert capture["native_result"].terminal_stage == "terminal"
assert capture["native_result"].terminal_reason == "terminal_node_selected:done"
assert capture["structural_tier_attained"] is True
assert capture["call_counts"] == {
    "planner_transport": 1,
    "planner_model": 0,
    "worker_transport": 0,
    "worker_model": 0,
    "gh_create_csharp_script": 0,
    "gh_snapshot": 1,
    "gh_edit": 1,
    "gh_connect": 0,
}
```

The test injects the fake Planner transport, so its model-call count is zero.
Run this test and require `NotImplementedError` from `_run_row_once()`.

- [ ] **Step 2: Implement a transparent recording transport**

Use one small wrapper:

```python
class _RecordingTransport:
    def __init__(self, delegate: object, role: str, model_call: bool) -> None:
        self.delegate = delegate
        self.role = role
        self.model_call = model_call
        self.calls: list[dict[str, object]] = []
        self.responses: list[str] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        snapshot = json.loads(json.dumps(prompt_artifact, ensure_ascii=True))
        self.calls.append(snapshot)
        response = self.delegate.send(prompt_artifact)
        self.responses.append(response)
        return response
```

The wrapper delegates exactly once and returns or raises the original value. It
does not retry, parse, trim, or patch output.

`model_call` distinguishes an actual LiteLLM transport from a frozen fake
transport for campaign call accounting.

- [ ] **Step 3: Implement one causal fake tool executor**

The fake accepts these exact prefixes:

```text
deterministic: gh_snapshot -> gh_edit
Worker leaf:  gh_create_csharp_script -> gh_snapshot -> gh_edit -> gh_connect
```

It must derive every response from the actual request:

- `gh_create_csharp_script` requires `pins_in == ()`,
  `pins_out == ("A:double",)`, exact fixed component name/position from the
  existing handoff, and a nonblank exact code string; it returns one clean
  existing create receipt with a fake receipt-derived GUID;
- `gh_snapshot` returns one positive epoch and includes the previously created
  C# component only if create was actually called;
- the C# snapshot exposes outputs in exact physical order `out/0`, `A/1`;
- `gh_edit` reads its actual `create` and `connect` arrays, assigns one unique
  `C*` ID and instance GUID per actual `T*`, returns actual component identities,
  maps every requested internal flow, and retains any pre-existing fake C#
  component;
- `gh_connect` requires the exact receipt-derived source GUID/index and
  deterministic correlation-derived target GUID/index, then returns those exact
  endpoints with `connected=true`.

Reject port parameters, unknown tools, repeated calls, update calls, request
substitutions, or calls after the complete prefix before producing a response.

Do not copy the broad mutation matrix from existing semantic tests. This fake
needs only truthful success plus one configurable ordinary failure at each tool
boundary for the focused stop tests.

- [ ] **Step 4: Implement `_run_row_once()` through existing runners**

Use this private signature:

```python
async def _run_row_once(
    row: _Row,
    *,
    planner_transport: object,
    worker_transport: object | None,
    tool_executor: Callable[[str, dict[str, object]], object],
) -> dict[str, object]:
```

Behavior:

1. Resolve the exact `_Case` from `row.case_id`.
2. Wrap the supplied Planner transport and construct the exact concrete
   `SemanticGraphPlannerAdapter`.
3. For deterministic cases, require `worker_transport is None` and invoke
   `run_semantic_graph_transaction()`.
4. For Worker-leaf cases, require a transport with callable `send` and invoke
   `run_semantic_graph_single_worker_leaf_transaction()`.
5. Read the admitted complete semantic graph from the existing load result:
   - deterministic result: load the retained raw Planner response through the
     existing strict loader for observation only;
   - Worker-leaf result: use its retained `graph_load_result.graph` when present.
6. Compute `structural_tier_attained` only when the existing load result owns an
   admitted graph; otherwise use `False`.
7. Return a private dictionary containing the exact row/case, native result,
   recording transports, call counts, structural observation, and tool records.

The observation does not alter the native result or control execution.

- [ ] **Step 5: Add the Worker-leaf and Stage B isolation REDs**

Run the maximum Worker-leaf reference through a fake Planner, the existing fake
Worker action response, and the causal fake tools. Assert:

```python
assert capture["native_result"].completed is True
assert capture["structural_tier_attained"] is True
assert capture["call_counts"] == {
    "planner_transport": 1,
    "planner_model": 0,
    "worker_transport": 1,
    "worker_model": 0,
    "gh_create_csharp_script": 1,
    "gh_snapshot": 1,
    "gh_edit": 1,
    "gh_connect": 1,
}
```

For a Stage B Worker-leaf row, inject the frozen fake Worker and assert its call
count is one while Worker model count remains zero. For a Stage B deterministic
row, pass `worker_transport=None` and assert both counts are zero.

Add one malformed fake Worker response and prove zero tool calls.

- [ ] **Step 6: Add ordinary result projection REDs**

`_project_run_result(capture)` must produce one closed JSON-shaped object with
these exact top-level keys:

```text
schema = rook.compositional_harness_qualification_row:v1
campaign_sha
row_id
repetition
stage
case_id
tool_mode
intent
planner_model
worker_model
generation_settings
provider_materialization
planner
graph_load
graph_compile
worker_handoff
deterministic_execution
connect
completed
call_counts
structural_tier_attained
transport_telemetry
tool_records
raised_exception_type
```

`campaign_sha` is `git rev-parse HEAD` for the executing checkout, not the
planning baseline. `planner` retains status, failure reason, transport error
type, exact prompt, and raw response. `graph_load` and `graph_compile` are null
when not reached; otherwise they retain the existing admitted/failure/reason
fields. `graph_load` also retains the canonical nodes and edges when admitted.
`worker_handoff` and `deterministic_execution` are null when not reached and
otherwise retain their existing terminal stage/reason plus their immediate
native record projection. `connect` is null until reached; otherwise it retains
the exact request and response without renaming response keys. Optional absent
values are JSON null rather than omitted keys. The strict prior-result loader in
Task 3 requires this closed top-level shape.

Do not add a campaign-wide pass/fail token or semantic-fidelity score.

Assert raw prompts, responses, code, tool payloads, and exception text remain in
the local object but the bounded stdout summary contains only:

```text
row_id
stage
case_id
operator_status
native_terminal_stage
native_terminal_reason
completed
structural_tier_attained
call_counts
result_path
```

`operator_status` is operational file/process state only:
`result_written`, `refused`, or `result_write_failed`. It is not a scored
campaign outcome and cannot replace any native stage, reason, receipt, or
`completed` field.

- [ ] **Step 7: Implement explicit native projectors**

Project only immediate fields from the actual result type. Do not reconstruct
lineage or replay the compiler. Implement four explicit private helpers named
`_project_planner_record()`, `_project_worker_handoff()`,
`_project_deterministic()`, and `_project_worker_leaf()`. Each helper must return
only JSON-shaped copies of fields owned by its input record; it must not call a
loader, compiler, runner, or tool.

For canonical graph serialization, project each admitted node's exact ID,
primitive, and recursively JSON-shaped parameters, plus each canonical edge's
four exact fields. Retain the canonical edge set even though tier attainment
does not compare it to the reference fixture.

- [ ] **Step 8: Add exclusive bounded local JSON writing**

Implement:

```python
def _write_local_result(payload: dict[str, object]) -> Path:
```

Requirements:

- require exact nonblank `LOCALAPPDATA`;
- use `%LOCALAPPDATA%/Rook/traces/`;
- create one filename containing UTC timestamp, process ID, and random suffix;
- serialize with `ensure_ascii=True`, compact separators, `allow_nan=False`;
- reject complete serialized UTF-8 size above 4 MiB;
- open in exclusive binary mode;
- require a complete write, flush, and close before reporting success;
- never truncate, retry, overwrite, hash, or write a second file;
- return the absolute path only after close succeeds.

This is one finished-result writer, not the existing flight recorder and not a
new event system.

Add tests for exclusive creation, overflow, serialization failure, short write,
write/flush/close exception, no overwrite, sensitive stdout exclusion, and a
successful round trip.

- [ ] **Step 9: Verify Task 2**

Run:

```powershell
cd C:/UDEV/Rook/.worktrees/compositional-harness-frozen-qualification-campaign-design/mcp_server
uv run --frozen --extra test pytest -q tests/test_compositional_harness_qualification_campaign.py tests/test_semantic_graph_runner.py tests/test_semantic_graph_worker_leaf_runner.py tests/test_minimal_csharp_initial_body_handoff.py
uv run --frozen python -m compileall -q ../scripts/compositional_harness_qualification_campaign.py tests/test_compositional_harness_qualification_campaign.py
git diff --check
```

Expected: all selected tests pass with fake transports/tools only.

- [ ] **Step 10: Record growth and commit Task 2**

Run the same nonblank-line hard stop, then:

```powershell
git add -- ../scripts/compositional_harness_qualification_campaign.py tests/test_compositional_harness_qualification_campaign.py
git commit -m "feat: run one frozen qualification row"
```

**Mandatory independent review stop:** Review causal fake derivation, exact call
budgets, no Worker model call in Stage B, ordinary result ownership, sensitive
stdout exclusion, and script growth before Task 3.

---

### Task 3: Add mechanical promotion, one-row CLI, and live-contact gate

**Files:**
- Modify: `scripts/compositional_harness_qualification_campaign.py`
- Modify: `mcp_server/tests/test_compositional_harness_qualification_campaign.py`

**Interfaces:**
- Consumes: Task 2 local result schema, fixed Stage A–C rows, `_run_row_once()`, result writer, `discover_instances()`, `rhino_request_context()`, `ToolDispatcher`, and `build_local_tools()`.
- Produces: `_load_prior_results()`, `_select_first_eligible_pair()`, `_stage_d_passed()`, `_resolve_dynamic_row()`, `_resolve_single_live_target()`, and `main()`.

- [ ] **Step 1: Add promotion-rule RED fixtures**

Build small JSON-shaped prior-result helpers containing only fields actually
written by Task 2. Use exact row IDs and model identities. Add these five named
tests before implementation:

- `test_no_eligible_planner_selects_no_pair`: supply both medium rows for every
  Planner, make at least one required row fail its native admission equation,
  keep every Worker eligible, and assert the selected pair is `None`.
- `test_no_eligible_worker_selects_no_pair`: make the first-priority Planner
  eligible, make every Stage C Worker row fail its clean native equation, and
  assert the selected pair is `None`.
- `test_priority_selects_first_eligible_planner_and_worker`: make every candidate
  eligible, add conflicting cost/latency ordering, and assert the selected pair
  is exactly `("ollama_chat/qwen3.6:35b",
  "ollama_chat/north-mini-code-1.0:q4_K_M")`.
- `test_failed_stage_d_repetition_blocks_live_promotion`: supply all six selected
  pair repetitions, make exactly one maximum repetition fail its direct native
  equation, and assert `_stage_d_passed()` is false and both Stage E row
  resolutions refuse.
- `test_blocked_stage_e_constructs_no_models_dispatcher_or_tools`: patch model
  constructors, `discover_instances`, `ToolDispatcher`, and the row runner with
  call counters that raise if entered; invoke `main()` for a Stage E row using
  the failed Stage D files; assert bounded refusal, nonzero exit, and every
  counter remains zero.

For the no-Planner case, make every Planner fail one of its two medium rows by
native transport, admission, compilation, or
`structural_tier_attained=False`.

For the no-Worker case, make every Stage C Worker result have `completed=False`
or a non-clean retained terminal.

For priority selection, make all candidates eligible and require exactly:

```python
(
    "ollama_chat/qwen3.6:35b",
    "ollama_chat/north-mini-code-1.0:q4_K_M",
)
```

Also add cases proving priority skips an ineligible first model and never uses
cost or latency fields.

- [ ] **Step 2: Implement strict prior-result loading**

Use:

```python
def _load_prior_results(paths: Sequence[Path]) -> tuple[dict[str, object], ...]:
```

Each file must be:

- exact JSON object;
- schema `rook.compositional_harness_qualification_row:v1`;
- from the exact campaign merge SHA recorded by the current script;
- an exact known Stage A–D row identity;
- unique by `(row_id, repetition, planner_model, worker_model, tool_mode)`;
- no larger than 4 MiB.

Reject duplicate keys, nonfinite values, trailing content, wrong roots, duplicate
row identities, repetition outside the exact allowed range, foreign
cases/models, more than 23 supplied results, or a future Stage E result. Do not
search a directory or infer missing files.

- [ ] **Step 3: Implement mechanical Planner and Worker eligibility**

Use exact pure predicates:

```python
def _planner_row_passed(row: Mapping[str, object]) -> bool:
    return (
        row["planner"]["status"] == "response_received"
        and row["graph_load"]["admitted"] is True
        and row["graph_compile"]["admitted"] is True
        and row["structural_tier_attained"] is True
    )

def _worker_row_passed(row: Mapping[str, object]) -> bool:
    return (
        row["worker_handoff"]["terminal_stage"] == "terminal"
        and row["worker_handoff"]["terminal_reason"] == "terminal_node_selected:done"
        and row["deterministic_execution"]["terminal_stage"] == "terminal"
        and row["deterministic_execution"]["terminal_reason"] == "terminal_node_selected:done"
        and row["completed"] is True
        and row["call_counts"] == expected_stage_c_counts
    )
```

For `graph_compile`, project the deterministic compiler or Worker-partition
compiler into the same `{admitted, failure, reason}` JSON shape. For
`connect`, compare the retained exact normalized response keys used by
`SemanticGraphSingleWorkerLeafResult`; do not invent renamed aliases.

The Stage C and Stage D Worker equation additionally requires the exact retained
normalized connect response to report tool success, `connected is True`, and
the same source/target GUIDs and pin indices as the retained request. The
deterministic live equation requires its native deterministic terminal plus the
frozen Planner/snapshot/edit call counts. Do not treat `completed` alone as a
replacement for those direct properties.

The real implementation must use closed-key/type checks before reading nested
values. It must not accept Python objects; it consumes strict decoded JSON only.

Planner eligibility requires both medium rows. Opus uses the two Stage A medium
control rows. Other Planners use their two Stage B rows. Worker eligibility uses
its one Stage C row.

Select the first eligible identity in `_PLANNER_PRIORITY` and
`_WORKER_PRIORITY`. If either is absent, return no pair. Do not score or sort by
latency, cost, tokens, canonical topology, or exception type.

- [ ] **Step 4: Implement Stage D repetition accounting and pass equation**

Use exact pair/case/settings/tool-mode equality to count prior identical rows.
A prior Stage A row counts only when both selected identities and every frozen
setting match.

`_resolve_dynamic_row("stage_d.medium", prior)` and
`_resolve_dynamic_row("stage_d.maximum", prior)` must:

- mechanically select the pair;
- count existing identical fake-tool results for that case;
- refuse when no pair is eligible;
- refuse when three total repetitions already exist;
- otherwise return the next repetition numbered 1, 2, or 3 using that exact
  selected pair.

`_stage_d_passed()` requires three total medium and three total maximum results,
each with admission, `structural_tier_attained=True`, both clean terminals, exact
connect evidence, `completed=True`, and the frozen full Worker-leaf call budget.

One failed repetition returns `False`. Do not replace it or count a fourth row.

- [ ] **Step 5: Add argument and pre-contact RED tests**

Accept only these shapes:

```text
no arguments
-> bounded execution_not_requested refusal

--row <fixed-stage-a-to-c-row> --execute-screen
-> one fake-tool model-screening row

--row stage_d.medium --prior-result <path-1> [--prior-result <path-N>] --execute-screen
--row stage_d.maximum --prior-result <path-1> [--prior-result <path-N>] --execute-screen
-> one mechanically resolved repeatability row

--row stage_e.maximum_deterministic --prior-result <path-1> [--prior-result <path-N>] --execute-live
--row stage_e.maximum_worker_leaf --prior-result <path-1> [--prior-result <path-N>] --execute-live
-> one eligible live row
```

Reject:

- unknown rows;
- model overrides;
- tool-mode overrides;
- missing prior results for dynamic rows;
- `--execute-live` on a fake row;
- `--execute-screen` on a live row;
- duplicate flags;
- additional arguments;
- blocked promotion;
- already completed repetition counts.

Every rejection occurs before constructing `LiteLLMWorkerTransport`,
`ToolDispatcher`, calling `discover_instances()`, or invoking any transport/tool.

- [ ] **Step 6: Implement exact model construction after gating**

Only after arguments, prior records, row resolution, and promotion gates pass:

- load credentials from `MCP_ROOT / ".env"` with `override=False` and never print
  values;
- construct the exact Planner transport from Task 1 kwargs;
- construct the exact scored Worker transport only for Stage A Worker-leaf,
  Stage C, and Stage D/Stage E Worker-leaf model rows;
- construct the frozen fake Worker for Stage B Worker-leaf rows;
- pass `None` for deterministic rows;
- wrap actual LiteLLM transports with `model_call=True` and fake transports with
  `model_call=False`.

No `get_models()`, active profile, `ROOK_MODEL_PROFILE`,
`ROOK_PLANNER_MODEL`, or `ROOK_WORKER_MODEL` participates in campaign identity.

- [ ] **Step 7: Implement finalists-only live targeting**

For Stage E only, after `_stage_d_passed()`:

1. call `discover_instances()` once;
2. require exactly one exact `dict` with `pluginType == "native"`;
3. require exact positive integer `processId` and `port`;
4. record PID as discovery identity and freeze the port;
5. construct `ToolDispatcher(port=port, local_tools=build_local_tools())`;
6. enter `rhino_request_context(port=port, process_id=process_id)` around the
   complete existing transaction;
7. pass `dispatcher.dispatch` unchanged as the tool executor.

Discovery reads instance records and is not a Grasshopper tool call. Do not issue
`ping`, `gh_status`, `gh_document_new`, readiness, cleanup, or liveness calls.
Canvas preparation and authorization remain manual operator responsibilities.
The runner's existing snapshot is the first Grasshopper call.

Add tests for zero/multiple/malformed instances and ensure no model or dispatcher
construction follows refusal.

- [ ] **Step 8: Implement one-row `main()`**

`main()` performs:

```text
classify exact arguments
-> load and validate explicit prior result paths when required
-> resolve fixed or dynamic row mechanically
-> enforce Stage E gate before discovery/contact
-> construct exact transports and fake/live tool executor
-> run exactly one row
-> project one local result
-> write and close one result file
-> print one bounded summary
-> exit
```

Catch ordinary `Exception`, never `BaseException`. On an ordinary runner
exception, project only observed calls/responses and the exception type, write one
ordinary result if possible, print a bounded failure summary, and exit nonzero.
Do not retry or choose another row.

Do not print raw prompts, responses, generated code, tool payloads, GUIDs,
credentials, local exception messages, cost metadata, or canonical edges.

- [ ] **Step 9: Run promotion and CLI tests**

Run:

```powershell
cd C:/UDEV/Rook/.worktrees/compositional-harness-frozen-qualification-campaign-design/mcp_server
uv run --frozen --extra test pytest -q tests/test_compositional_harness_qualification_campaign.py -k "eligible or priority or stage_d or stage_e or arguments or main or target"
```

Expected: all tests pass; no external contact. Confirm specifically that the
five required promotion tests pass by exact test ID.

- [ ] **Step 10: Run the complete adjacent seam**

Run:

```powershell
cd C:/UDEV/Rook/.worktrees/compositional-harness-frozen-qualification-campaign-design/mcp_server
uv run --frozen --extra test pytest -q `
  tests/test_compositional_harness_qualification_campaign.py `
  tests/test_semantic_graph.py `
  tests/test_semantic_graph_compiler.py `
  tests/test_semantic_graph_runner.py `
  tests/test_semantic_graph_worker_leaf_runner.py `
  tests/test_local_worker_model_transport.py `
  tests/test_minimal_csharp_initial_body_handoff.py `
  tests/test_plan_graph_worker_create_body_apply.py
uv run --frozen python -m compileall -q ../scripts/compositional_harness_qualification_campaign.py tests/test_compositional_harness_qualification_campaign.py
git diff --check
```

Expected: new and inherited seams pass; no external contact.

- [ ] **Step 11: Run source-surface and growth gates**

Run:

```powershell
$allowed = @(
  'docs/superpowers/specs/2026-08-03-compositional-harness-frozen-qualification-campaign-design.md',
  'docs/superpowers/plans/2026-08-03-compositional-harness-frozen-qualification-campaign.md',
  'scripts/compositional_harness_qualification_campaign.py',
  'mcp_server/tests/test_compositional_harness_qualification_campaign.py'
)
$actual = @(git diff --name-only 8baf325a459ec9bb53cae24b1af0fab452b3001e...HEAD) + @(git diff --name-only)
$unexpected = $actual | Sort-Object -Unique | Where-Object { $_ -notin $allowed }
if ($unexpected) { throw "unexpected scope: $($unexpected -join ', ')" }

$script = '../scripts/compositional_harness_qualification_campaign.py'
$nonblank = (Get-Content -LiteralPath $script | Where-Object { $_.Trim() }).Count
"FINAL_NONBLANK_SCRIPT_LINES=$nonblank"
if ($nonblank -gt 800) { throw 'operator script exceeded reviewed hard stop' }

rg -n "get_models|ROOK_MODEL_PROFILE|ROOK_PLANNER_MODEL|ROOK_WORKER_MODEL|retry|fallback|gh_update_script|gh_document_new|gh_status" `
  ../scripts/compositional_harness_qualification_campaign.py
```

Interpret the source scan manually. Expected allowed matches are explanatory
failure tokens or explicit environment-variable refusal checks; there must be no
profile resolution, retry/fallback implementation, update, preparation, or
status dispatch.

- [ ] **Step 12: Commit Task 3**

```powershell
git add -- ../scripts/compositional_harness_qualification_campaign.py tests/test_compositional_harness_qualification_campaign.py
git commit -m "feat: gate frozen qualification promotion"
```

**Mandatory independent review stop:** Review all five required promotion tests,
pre-contact ordering, one-row CLI behavior, prior-result strictness, live target
binding, result safety, final growth, and absence of product changes before final
reconciliation.

---

### Task 4: Final verification and plan reconciliation

**Files:**
- Modify: `docs/superpowers/plans/2026-08-03-compositional-harness-frozen-qualification-campaign.md`

**Interfaces:**
- Consumes: reviewed Tasks 1–3.
- Produces: reproducible verification ledger and implementation-review handoff.
- Produces no runtime code.

- [ ] **Step 1: Re-run the focused campaign test**

```powershell
cd C:/UDEV/Rook/.worktrees/compositional-harness-frozen-qualification-campaign-design/mcp_server
uv run --frozen --extra test pytest -q tests/test_compositional_harness_qualification_campaign.py
```

Record the exact count and warnings.

- [ ] **Step 2: Re-run the inherited 352-test baseline plus campaign tests**

```powershell
uv run --frozen --extra test pytest -q `
  tests/test_compositional_harness_qualification_campaign.py `
  tests/test_semantic_graph.py `
  tests/test_semantic_graph_compiler.py `
  tests/test_semantic_graph_runner.py `
  tests/test_semantic_graph_worker_leaf_runner.py `
  tests/test_local_worker_model_transport.py `
  tests/test_worker_first_csharp_application.py `
  tests/test_minimal_csharp_initial_body_handoff.py `
  tests/test_plan_graph_worker_create_body_apply.py
```

The inherited portion was **352 passed** at planning baseline. Record the new
combined count exactly; do not hardcode a predicted final total.

- [ ] **Step 3: Run compilation and whitespace verification**

```powershell
uv run --frozen python -m compileall -q ../scripts/compositional_harness_qualification_campaign.py tests/test_compositional_harness_qualification_campaign.py
cd ..
git diff --check
git show --check --oneline HEAD
```

- [ ] **Step 4: Prove exact scope and no product changes**

```powershell
$base = '8baf325a459ec9bb53cae24b1af0fab452b3001e'
git diff --name-status "$base...HEAD"
git diff --name-only "$base...HEAD" -- mcp_server/src src knowledge
git status --short
```

Expected:

- complete branch scope contains only the specification, plan, new operator
  script, and new test module;
- product/managed/knowledge scan prints nothing;
- worktree is clean after reconciliation commit.

- [ ] **Step 5: Prove no external contact occurred**

Record in this ledger:

```text
Provider calls during implementation/review: 0
Ollama calls during implementation/review: 0
Rhino calls during implementation/review: 0
Grasshopper calls during implementation/review: 0
Worker-box calls during implementation/review: 0
Live flags launched as subprocesses: 0
```

Controlled in-process tests may exercise guarded argument branches only after
patching every constructor/discovery/dispatch boundary.

- [ ] **Step 6: Reconcile all checkboxes and commands**

Mark completed steps, record:

- Task commit SHAs;
- independent-review approvals;
- exact focused and combined test counts;
- exact nonblank script line count;
- exact four-file branch scope;
- the zero-contact statement;
- current `origin/main` and any drift;
- final `git diff --check` and worktree status.

Do not add campaign results. No scored model row is authorized by implementation
or merge.

- [ ] **Step 7: Commit the ledger only**

```powershell
git add -- docs/superpowers/plans/2026-08-03-compositional-harness-frozen-qualification-campaign.md
git commit -m "docs: reconcile frozen qualification campaign"
```

- [ ] **Step 8: Stop for final independent implementation review**

Do not push, open a PR, merge, or execute any campaign row until separately
approved.

## Execution Recommendation

Use **Inline Execution** with `superpowers:executing-plans`. The case table,
structural observation, causal fake, promotion rules, and one-row CLI share one
private script and must remain coherent. Stop after Tasks 1, 2, and 3 for the
mandatory independent reviews recorded above.
