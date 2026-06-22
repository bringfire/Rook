# LM3C — PlanGraph Parameter Binding (descriptor → template metadata/memory)

**Date:** 2026-06-22
**Status:** Approved (design)
**Category:** LM campaign — LM3 (Planner / PlanGraph execution scaffold), third slice
**Branch:** `codex/lm3c-plan-graph-param-binding`
**North-star:** `docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md`
**Builds on:** LM3B selector (`select_template`, `TemplateEntry`, `DEFAULT_REGISTRY`), LM3A walker, LM1E reducer/types, LM1G bridge.

---

## Summary

LM3C is the **parameter-binding seam**: a pure, deterministic step that injects
values from a structured intent descriptor into a *selected* template's graph —
writing **only** node `metadata` and graph `memory.facts`, never structure. It
sits beside the LM3B selector as a distinct seam: selection chooses a graph;
binding fills in declared, safe parameters.

Binding never builds, renames, or rewires anything. It applies only a per-template
declared allow-list of `descriptor_field → target` mappings. Successful binding is
proven by the graph's own metadata/memory; the report stays quiet — **findings are
emitted only on error**. Bound values are **deep-copied** so a later mutation of
the descriptor cannot reach into graph state.

The governing LM3 invariant is preserved: because binding touches only
metadata/memory (not ids, edges, `*_ref`, status, or retry), a bound graph is
still drivable to `complete` by the LM3A walker through the LM1G bridge.

## Boundary (hard constraints)

- **Binding writes only** `node.metadata[key]` and `graph.memory.facts[key]`.
  **Forbidden targets:** node ids, edges, `execution_ref`, `verifier_ref`,
  `repair_policy_ref`, retry policy, status, and any structural change.
- **Selection stays separate and unbound.** `select_template` is byte-stable
  except `TemplateEntry` gains a defaulted `bindings` field. The unbound selected
  copy remains inspectable.
- **Values copied, never interpreted.** Each bound value is `copy.deepcopy`-ed
  before storage; binding never parses or transforms it.
- **Deterministic, pure, import-light.** No model calls, no live tools, no
  `planner.py`. The module imports only `rook.learning.plan_graph` among rook
  modules (+ stdlib) — unchanged from LM3B. Enforced by the existing AST allowlist
  test and subprocess probe.
- **Findings only on error** (LM3C). Optional-missing and successful bindings emit
  nothing.

## Module & files

- **Extend:** `mcp_server/src/rook/learning/plan_graph_templates.py` (BindingSpec
  is referenced by `TemplateEntry`; the registry's binding specs live beside the
  templates they bind — cohesion).
- **Extend tests:** `mcp_server/tests/test_plan_graph_templates.py`.

## Types (frozen dataclasses)

```python
@dataclass(frozen=True)
class BindingSpec:
    descriptor_field: str
    target: Literal["memory_fact", "node_metadata"]
    key: str
    node_id: str | None = None      # required when target == "node_metadata"
    required: bool = False

@dataclass(frozen=True)
class BindingFinding:
    code: str
    severity: Literal["info", "warning", "error"]   # LM3C emits "error" only
    field: str
    message: str

@dataclass(frozen=True)
class BindingResult:
    graph: PlanGraph | None
    findings: tuple[BindingFinding, ...]

@dataclass(frozen=True)
class SelectAndBindResult:
    selection: TemplateSelection        # carries the UNBOUND selected copy
    binding: BindingResult | None       # None when nothing was selected
```

`TemplateEntry` gains `bindings: tuple[BindingSpec, ...] = ()` (the only LM3B
surface change; defaulted, so existing positional construction still works). The
`_make_entry` helper gains a defaulted `bindings: tuple[BindingSpec, ...] = ()`
param so the `DEFAULT_REGISTRY` entry can declare its bindings; existing callers
pass nothing and get `()`.

Binding finding codes (single-source `_BINDING_SEVERITY_BY_CODE`, mirroring the
LM3B `_SEVERITY_BY_CODE` pattern — all `error` in LM3C):

| code | when |
|------|------|
| `missing_required_binding` | a `required=True` field is absent from the descriptor |
| `unknown_binding_target` | a `node_metadata` spec whose `node_id` is `None` or absent from the graph |
| `binding_value_copy_failed` | `copy.deepcopy(value)` raised for a bound value |

## `bind_parameters(graph, bindings, descriptor) -> BindingResult`

```python
def bind_parameters(
    graph: PlanGraph,
    bindings: tuple[BindingSpec, ...],
    descriptor: Mapping[str, object],
) -> BindingResult
```

Registry-agnostic pure primitive. The `descriptor` is typed `Mapping[str, object]`
so the primitive is robust to any value type (this is what makes the
mutable-value and copy-failure paths real and testable).

Algorithm:
1. `working = copy.deepcopy(graph)` — never mutate the input.
2. `findings: list[BindingFinding] = []`.
3. For each `spec` in `bindings`, in order:
   - **field absent:** if `spec.required` → append `missing_required_binding`
     (error); else **skip silently**. Continue.
   - **field present:** `raw = descriptor[spec.descriptor_field]`.
     - Copy defensively: `try: value = copy.deepcopy(raw)` / `except Exception:`
       append `binding_value_copy_failed` (error); continue. (Catches arbitrary
       `__deepcopy__` failures — never crash on data.)
     - **target `memory_fact`:** `working.memory.facts[spec.key] = value`.
     - **target `node_metadata`:** if `spec.node_id is None or spec.node_id not in
       working.nodes` → append `unknown_binding_target` (error), continue; else
       `working.nodes[spec.node_id].metadata[spec.key] = value`.
4. All errors are collected (not first-only). If any finding has
   `severity == "error"` → return `BindingResult(graph=None,
   findings=tuple(findings))`; else `BindingResult(graph=working,
   findings=tuple(findings))` (findings is `()` on full success).

Determinism: bindings applied in tuple order; no ordering heuristics.

## `select_and_bind(descriptor, registry=DEFAULT_REGISTRY) -> SelectAndBindResult`

```python
def select_and_bind(
    descriptor: Mapping[str, str],
    registry: tuple[TemplateEntry, ...] = DEFAULT_REGISTRY,
) -> SelectAndBindResult
```

Thin composer:
1. `selection = select_template(descriptor, registry)`.
2. If `selection.graph is None` (no match / ambiguous) → return
   `SelectAndBindResult(selection=selection, binding=None)`.
3. Else find the matched entry (`selection.selected_template_id`), and return
   `SelectAndBindResult(selection=selection, binding=bind_parameters(
   selection.graph, entry.bindings, descriptor))`.

Selection findings (`result.selection.findings`) and binding findings
(`result.binding.findings`) stay **separate**. The usable bound graph is
`result.binding.graph`; the unbound copy remains `result.selection.graph`.

## First template's bindings (both optional)

On the `gh_csharp_create_repair` entry:
- `goal → memory_fact`, key `"goal"`, optional.
- `component_name → node_metadata` on `create_script`, key `"component_name"`,
  optional.

Both `required=False`, so the existing LM3B `_DESCRIPTOR` (no `goal` /
`component_name`) still selects-and-binds to a clean graph with **no findings**.
The required-missing path is exercised with a custom `BindingSpec(required=True)`
in tests, not by burdening the default template. (`pins_in` / `pins_out` are
deferred — they drift toward tool arguments, a later slice.)

## Governing invariant preserved

Binding writes only metadata/memory; structure, `*_ref`, and status are untouched.
A composition test proves: `select_and_bind({...,"component_name":"MyComp"})` →
`result.binding.graph` → `walk_plan_graph` + `apply_tool_result` (canned
create→repair results) → `final_graph_status == "complete"`, with
`create_script.metadata["component_name"] == "MyComp"` on the driven graph.

## Testing (TDD)

1. **`bind_parameters` success:** a descriptor with both fields → memory fact and
   node metadata written; **input graph unmutated**; `findings == ()`.
2. **Required-missing:** custom `BindingSpec(required=True)` for an absent field →
   `graph is None`, exactly one `missing_required_binding` (error).
3. **Optional-missing:** optional field absent → graph returned, target untouched,
   `findings == ()`.
4. **Malformed target:** `node_metadata` spec with `node_id=None` or an unknown
   `node_id` → `graph is None`, `unknown_binding_target` (error).
5. **Value isolation (deepcopy):** a descriptor whose value is a mutable `dict`/
   `list`; after binding, mutate the descriptor's value; assert the graph's
   metadata/memory copy is unchanged.
6. **Copy failure:** a value whose `__deepcopy__` raises → `graph is None`,
   `binding_value_copy_failed` (error); no partial/shared object stored.
7. **Multiple errors:** two failing specs → both reported, graph nulled.
8. **`select_and_bind` compose:** descriptor matching the default template with
   `component_name` → `binding.graph` carries the metadata and memory fact;
   `selection.graph` (unbound) does NOT carry them; findings streams separate.
9. **No-match compose:** unmatched descriptor → `binding is None`,
   `selection.findings` has `no_matching_template`.
10. **Governing invariant:** bound default-template graph drives to `complete`
    through the walker; `component_name` present on the driven graph.
11. **Determinism + purity:** bindings applied in tuple order; AST allowlist still
    `== {"rook.learning.plan_graph"}`; subprocess probe still bars
    walker/bridge/planner/tool_dispatcher/server/dspy/litellm.

## Out of scope (LM3C)

- Tool-argument binding (`pins_in`/`pins_out`, concrete script source) — later slice.
- Binding into refs/ids/edges/status/retry/structure — forbidden by design.
- Free-text inference, scoring, value interpretation/transformation.
- Any `planner.py` integration.

## File touch list

- Modify: `mcp_server/src/rook/learning/plan_graph_templates.py` — add `BindingSpec`,
  `BindingFinding`, `BindingResult`, `SelectAndBindResult`,
  `_BINDING_SEVERITY_BY_CODE`, `bind_parameters`, `select_and_bind`; add `bindings`
  field to `TemplateEntry`; add bindings to the `gh_csharp_create_repair` entry.
- Modify: `mcp_server/tests/test_plan_graph_templates.py` — add LM3C tests.
