# LM4K — Memory-Backed Repair-Param Sourcing (`bind_params_from_memory`)

Status: design approved (brainstorming), pre-plan.
Campaign: Rook local/internal-model reliability (LM). North-star:
`docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md`.
Predecessors: LM4I (PR #339, `5d21f27b`) full live repair chain; LM4J (PR #340,
`487aa3ef`) declared-ref chain with no producer overrides + an **observational**
memory-substrate guard (producer projection writes `component_guid` / `repair_anchor`
into `graph.memory.facts`).

## Goal

Move one step beyond LM4J's *observation* by making `graph.memory.facts` the **source
of truth** for the repair target guid: a small **pure learning-layer** primitive,
`bind_params_from_memory`, resolves a node's producer params from the runtime memory
substrate instead of the test hand-wiring them from `create.evidence`. This is the
reusable seam a future runner will call to bind producer params without the model —
**runtime `graph.memory.facts → producer params`**.

Framed as **memory-backed param binding / repair-param sourcing**, NOT workflow
automation.

## Non-Goals (explicit, load-bearing)

- **No scheduler / runner / node-selection policy.** The helper is a single pure
  function. The tests still hand-drive node order and still perform the assignment of
  the returned params into `node.metadata["execution_params"]`.
- **The helper does NOT write `node.metadata["execution_params"]`** and does NOT import
  `EXECUTION_PARAMS_KEY` or anything in the agent layer. It **returns** the merged
  params; the caller (test now, runner later) assigns them. This keeps it from quietly
  becoming a live-execution primitive.
- **No graph mutation.** The helper reads `graph.memory.facts` and returns new data.
- **No model involvement.** Rook owns memory, contracts, verifier gates, and params.
- **The helper has no production caller yet** — its consumers are the LM4K tests now
  and a future runner. (Consistent with LM1E–LM4G primitives that preceded their
  runner.)

## Why This Slice

- LM4J proved the substrate exists but used it only observationally; a purely
  test-only inline `graph.memory.facts["component_guid"]` read would mostly re-prove
  LM4J. The useful new artifact is the **reusable runtime memory→param primitive**.
- The existing `BindingSpec` / `bind_parameters` (plan_graph_templates.py) is the
  WRONG direction and time: it binds an **intent-descriptor field → memory/metadata at
  construction time**, before execution. It reads `descriptor[field]`, not
  `graph.memory.facts`. LM4K's runtime memory→param sourcing is a distinct seam — hence
  distinct types (`ParamBindingResult` / `ParamBindingFinding`), so construction-time
  descriptor binding and runtime memory binding stay mentally separate.

## The Helper — Contract

New module `mcp_server/src/rook/learning/plan_graph_param_binding.py` (pure; stdlib +
`rook.learning.plan_graph` types only; no agent import).

```python
@dataclass(frozen=True)
class ParamBindingFinding:
    code: str
    severity: Literal["error"]          # all LM4K findings are errors (no partial bind)
    param_key: str | None
    message: str

@dataclass(frozen=True)
class ParamBindingResult:
    params: dict | None
    findings: tuple[ParamBindingFinding, ...]

def bind_params_from_memory(
    base_params: Mapping,
    graph: PlanGraph,
    bindings: Mapping[str, tuple[str, ...]],   # {param_key: explicit path into memory.facts}
) -> ParamBindingResult: ...
```

**Behavior:**
1. Start from a **deep copy** of `base_params` (the static params: code, mode, language).
2. For each `(param_key, path)` in `bindings`, traverse `graph.memory.facts` along the
   **explicit `path`** (a tuple of string keys, e.g. `("repair_anchor",
   "component_guid")`); deep-copy the resolved value and set `merged[param_key]`.
3. Return `ParamBindingResult(params=merged, findings=())` on full success.

**No partial success (mirrors `bind_parameters`):** process every binding and collect
**all** findings; if **any** error finding exists, return `params=None` (never a
partially merged dict).

**Findings (all severity `error` → cause `params=None`):**
| code | when |
|------|------|
| `base_params_invalid` | `base_params` is not a `Mapping` |
| `base_params_copy_failed` | deep-copy of `base_params` raises |
| `param_key_invalid` | a binding's `param_key` is not a non-empty string (the merged dict becomes tool params, so keys must be valid) |
| `memory_path_invalid` | a binding `path` is empty, or contains a non-string element |
| `memory_fact_missing` | a path key is absent at its traversal step |
| `memory_fact_invalid` | a non-final path element resolves to a non-`Mapping` (cannot descend) |
| `memory_value_copy_failed` | deep-copy of a resolved memory value raises |

**Purity / boundary invariants:**
- Reads only `graph.memory.facts`; never mutates `graph` or `base_params`.
- Deep-copies `base_params` and every bound value (no shared references leak).
- Imports only stdlib + `rook.learning.plan_graph` (TYPE_CHECKING-quoted `PlanGraph`).
  **No** `rook.agent.*`, **no** `EXECUTION_PARAMS_KEY`. Pinned by an AST import-boundary
  guard test.

## Architecture — Seams

- Consumes: `graph.memory.facts` (populated at runtime by `apply_producer_result` →
  `project_receipt_outcome` → `apply_outcome` → `_merge_memory`, LM4J).
- Produced for: the LM4K tests now; a future runner that binds producer params from
  memory between nodes.
- The caller assigns the returned dict into `node.metadata[EXECUTION_PARAMS_KEY]`
  (agent-layer key, owned by the test/runner — NOT the helper).

## Deliverables — One Production Module + Tests

### (a) Pure unit tests — `mcp_server/tests/test_plan_graph_param_binding.py`

In the focused `test_plan_graph*` gate. Covers the helper in isolation:
- **Nested-path success:** `bind_params_from_memory({"code": "...", "mode": "body",
  "language": "csharp"}, graph, {"guid": ("repair_anchor", "component_guid")})` →
  `params["guid"]` == the memory guid, base params preserved, `findings == ()`.
- **Flat equivalence / control:** binding `{"guid": ("component_guid",)}` yields the
  same guid as the nested path (assert equal) — pins flat vs nested coverage.
- **`memory_fact_missing` → `params is None`** (binding a path whose key is absent).
- **`memory_path_invalid` → `params is None`** (empty path; non-string element).
- **`memory_fact_invalid` → `params is None`** (descend into a non-Mapping intermediate).
- **`base_params_invalid` → `params is None`** (non-Mapping base).
- **`param_key_invalid` → `params is None`** (a binding with a non-string / empty
  `param_key`, e.g. `{None: (...)}` or `{"": (...)}`).
- **Immutability:** input `graph` (and `graph.memory.facts`) and the `base_params`
  mapping are unchanged after the call; mutating the returned `params` does not affect
  memory (deep-copy independence).
- **AST import-boundary guard:** the module imports no `rook.agent.*` and no
  `EXECUTION_PARAMS_KEY`.

### (b) Pure chain guard — extend the memory→param→repair flow

In the focused gate (raw-dict driven, like LM4J's pure guard). After
`apply_producer_result("create_script", <wrapped-failure raw>)` populates
`graph.memory.facts`, call `bind_params_from_memory(base_repair_params, graph, {"guid":
("repair_anchor", "component_guid")})`, assert `params["guid"]` matches the
memory/component guid, assign it into `repair_same_component.metadata[
EXECUTION_PARAMS_KEY]`, and drive the chain (`apply_producer_result` repair →
`apply_verifier_step` → `apply_outcome(done)`) to `graph_status == "complete"`.

**Scope of this guard (honest):** `apply_producer_result` consumes a raw tool-result
dict, **not** the node's `execution_params` — so the pure guard proves *deterministic
memory→params binding* (the helper sources the guid from memory) *plus continued graph
composition to `complete`*. It does **not** prove the bound guid drives a real repair
dispatch — only the live proof (c) does that, where `run_live_producer_node` actually
reads `execution_params` and dispatches `gh_update_script` with the memory-sourced guid.

(This may be a new test or an added case alongside `test_plan_graph_live_repair_memory.py`;
the plan will choose — a separate file keeps the LM4J guard untouched.)

### (c) Live proof — `mcp_server/tests/test_live_repair_chain_memory_sourced_live.py`

`requires_rhino`. LM4J's declared-ref live chain, but the repair params are sourced
from memory via the helper:
- After the live create dispatch, `repair_guid_control =
  create_result.graph.nodes["create_script"].evidence.repair_anchor["component_guid"]`
  is captured **only as a control**.
- `binding = bind_params_from_memory({"code": "A = 42.0;", "mode": "body", "language":
  "csharp"}, create_result.graph, {"guid": ("repair_anchor", "component_guid")})`;
  assert `binding.findings == ()` and `binding.params["guid"] == repair_guid_control`
  (memory matches evidence — the source-of-truth control).
- Assign `binding.params` into `repair_same_component.metadata[EXECUTION_PARAMS_KEY]`
  (the test performs the assignment), then run the same LM4J chain to
  `graph_status == "complete"`. No producer ref overrides; `tool_status is None` on the
  repair record (LM4I/J finding) still pinned.

## Data Flow

```
live create (declared gh_create_csharp_script:v1) -> apply_producer_result
   -> graph.memory.facts{component_guid, repair_anchor{component_guid}}   (RUNTIME)
bind_params_from_memory(base={code,mode,language}, graph, {"guid": ("repair_anchor","component_guid")})
   -> params{code,mode,language, guid <- memory.facts.repair_anchor.component_guid}
test assigns params -> repair_same_component.metadata["execution_params"]
   -> live repair -> verify_repair -> done -> "complete"
   (control: assert params["guid"] == create.evidence.repair_anchor.component_guid)
```

## Error Handling / Risks

- **Memory fact absent** (e.g. a producer that emits no anchor) → `memory_fact_missing`
  + `params=None`; the caller must not dispatch with a fabricated guid. The tests
  assert this no-fabrication contract.
- **Path typo / wrong shape** → `memory_path_invalid` / `memory_fact_invalid`, never a
  silent whole-dict bind.
- **Live receipt shape drift** → caught by the existing live record `mismatches`
  (unchanged from LM4J).
- **`operations_knowledge.json` dirtied by live run** → `git restore` post-run.

## Testing Strategy

- Unit + pure chain guard run in the focused `test_plan_graph*` gate (deterministic, CI).
- Live proof is `requires_rhino` (skip-safe; `_ensure_gh_document` guard). Acceptance:
  Rhino + GH open, run `pytest -m requires_rhino
  mcp_server/tests/test_live_repair_chain_memory_sourced_live.py`.

## Diff Guard

- **Production change is exactly one new module:**
  `mcp_server/src/rook/learning/plan_graph_param_binding.py`. No edits to any existing
  `src/` file. `git diff --numstat main...HEAD -- mcp_server/src` lists only that file.
- New test files + this spec + the plan. No `knowledge/` changes;
  `operations_knowledge.json` restored after live runs (never committed).
