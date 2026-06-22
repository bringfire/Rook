# LM3B — PlanGraph Birth Seam (deterministic template selector)

**Date:** 2026-06-22
**Status:** Approved (design)
**Category:** LM campaign — LM3 (Planner / PlanGraph execution scaffold), second slice
**Branch:** `codex/lm3b-plan-graph-template-selector`
**North-star:** `docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md`
**Builds on:** LM3A walker (`walk_plan_graph`), LM1E reducer/types (`plan_graph`), LM1G bridge.

---

## Summary

LM3B is the **birth seam** of the PlanGraph execution scaffold: a pure,
deterministic **template selector** that maps a small *structured* intent
descriptor to a registered, hand-authored `PlanGraph` template and returns a
fresh copy of that template plus an auditable selection record.

It proves **graph birth, not graph binding**. The selector never builds a bespoke
plan, never infers from free text, never calls a model or a live tool, and never
couples to `planner.py`. Vague→structured normalization stays upstream (a future
planner/intent normalizer); LM3B requires the structure to already exist.

The selector is a **deterministic router**: each registered template declares
required criteria as `field=value` pairs; a template matches iff *every* declared
criterion equals the descriptor's value for that field. Exactly one match returns
a fresh graph; zero or many returns no graph plus an explicit finding. No scoring,
no ranking, no fallback — scoring is where hidden planner intelligence would
sneak in.

Parameter binding (injecting intent-specific values into the template) is
explicitly **deferred to LM3C**. LM3B returns templates verbatim.

## Boundary (hard constraints)

- **Selection only.** The selector never mutates node ids, edges, refs, metadata,
  graph memory, or retry settings. It returns a fresh deep copy of the template.
- **Birth is independent of drive.** The module imports only stdlib (`copy`,
  `dataclasses`, `typing`) plus `rook.learning.plan_graph` (to *build* the
  hand-authored template). It must **not** import `plan_graph_bridge`,
  `plan_graph_walker`, `rook.agent.planner`, `rook.server`,
  `rook.agent.tool_dispatcher`, `dspy`, or `litellm`. Enforced by an AST
  allowlist test and a subprocess probe.
- **No long-lived mutable graph in the registry.** Registry entries hold a graph
  **factory** (`Callable[[], PlanGraph]`), not a stored instance, so no caller can
  corrupt a shared template. Criteria are stored as immutable sorted tuples.
- **Deterministic.** Evaluations are emitted in registry order; per-criterion
  checks follow the entry's sorted criteria order; the ambiguous finding lists
  matching ids sorted.
- **No model calls, no live tools, no `planner.py`.**

## Module & files

- **New:** `mcp_server/src/rook/learning/plan_graph_templates.py`
- **New tests:** `mcp_server/tests/test_plan_graph_templates.py`

## Public surface

```python
def select_template(
    descriptor: Mapping[str, str],
    registry: tuple[TemplateEntry, ...] = DEFAULT_REGISTRY,
) -> TemplateSelection
```

- `descriptor` — a structured `field → value` mapping (e.g.
  `{"domain": "grasshopper", "operation": "create_repair", "language":
  "csharp"}`). Not free text.
- `registry` — defaults to the built-in `DEFAULT_REGISTRY`; tests inject a custom
  registry (e.g. two overlapping-criteria templates) to exercise ambiguity without
  polluting global state.

## Types (frozen dataclasses)

```python
@dataclass(frozen=True)
class TemplateEntry:
    template_id: str
    criteria: tuple[tuple[str, str], ...]   # immutable, sorted (field, value) pairs
    build_graph: Callable[[], PlanGraph]     # factory: builds a fresh graph per call

@dataclass(frozen=True)
class CriterionCheck:
    field: str
    expected: str
    actual: str | None                       # descriptor's value, None if absent
    outcome: Literal["accepted", "missing_field", "value_mismatch"]

@dataclass(frozen=True)
class TemplateEvaluation:
    template_id: str
    matched: bool                            # True iff every criterion accepted
    criteria: tuple[CriterionCheck, ...]

@dataclass(frozen=True)
class TemplateFinding:
    code: str                                # see _SEVERITY_BY_CODE
    severity: Literal["error", "info"]
    message: str
    template_ids: tuple[str, ...]

@dataclass(frozen=True)
class TemplateSelection:
    selected_template_id: str | None
    graph: PlanGraph | None                  # copy.deepcopy(entry.build_graph()) or None
    evaluations: tuple[TemplateEvaluation, ...]   # ALL templates — full audit trail
    findings: tuple[TemplateFinding, ...]
```

Finding codes (single-source `_SEVERITY_BY_CODE`, LM2 style):

| code | severity | when |
|------|----------|------|
| `template_selected` | info | exactly one template matched |
| `no_matching_template` | error | zero templates matched |
| `ambiguous_template` | error | two or more templates matched (no tiebreak) |

A private helper `_make_entry(template_id, criteria: Mapping[str, str],
build_graph)` normalizes `criteria` into a sorted tuple and constructs the frozen
`TemplateEntry` (avoids a mutable dict in the entry and a frozen `__post_init__`
dance).

## Algorithm

1. For each entry in `registry` (registry order), evaluate every criterion against
   `descriptor`:
   - field absent from descriptor → `CriterionCheck(outcome="missing_field",
     actual=None)`.
   - present but unequal → `outcome="value_mismatch"` (with `actual`).
   - present and equal → `outcome="accepted"`.
   - `matched = all(check.outcome == "accepted")`. Append a `TemplateEvaluation`.
2. `matched_ids = sorted(e.template_id for matched evaluations)`.
3. **Exactly one** → `selected_template_id = that id`, `graph =
   copy.deepcopy(entry.build_graph())`, finding `template_selected` (info,
   `template_ids=(id,)`).
4. **Zero** → `graph=None`, finding `no_matching_template` (error,
   `template_ids=()`).
5. **Two or more** → `graph=None`, finding `ambiguous_template` (error,
   `template_ids=tuple(matched_ids)`, no tiebreak).
6. Always return all `evaluations` (every template, every criterion outcome).

`missing_field` vs `value_mismatch` are kept distinct so a later planner failing to
supply enough structure is diagnosable separately from supplying wrong values.

## First (only) registered template

`gh_csharp_create_repair` — the GH C# create-repair loop that LM3A proved
**end-to-end through the LM1G bridge** (`test_plan_graph_bridge.py::
test_canned_create_repair_loop_reaches_complete_through_bridge`).

**Why this 2-node `on_repair` shape, not a verifier-mediated 5-node shape:** the
LM1G adapter maps a `created_with_errors` receipt directly to `needs_repair` at
the *create* node. A richer `create → verify_receipt → repair → verify_clean →
done` template uses `requires` edges that only unlock on `succeeded`, so when the
walker drives it through the bridge the create node lands `needs_repair` and the
`requires` edge to `verify_receipt` never unlocks — the walk stalls `blocked`,
never `complete`. (That 5-node fixture is only drivable via `apply_outcome` with
hand-chosen statuses, not the bridge.) The bridge-drivable create-repair loop is
the 2-node `on_repair` shape; it is the one whose end-to-end path is already
proven, so it is the honest first template. Verifier-mediated templates wait until
a verifier adapter (not the raw bridge) drives verifier nodes — a later slice.

- Nodes:
  - `create_script` — `execution_ref="gh_create_csharp_script:v1"`,
    `verifier_ref="script_receipt_has_artifact_or_errors:v1"`,
    `repair_policy_ref="repair_same_component_once:v1"`.
  - `repair_same_component` — `execution_ref="gh_update_script:v1"`,
    `repair_policy_ref="repair_same_component_once:v1"`, `is_terminal=True`.
  - (`verifier_ref`/`repair_policy_ref` are inert forward-looking refs the walker
    only reflects; they are not consumed in LM3B.)
- Edges: `create_script → repair_same_component` (`on_repair`).
- Built by a module-private factory `_build_gh_csharp_create_repair() ->
  PlanGraph` (fresh graph each call).
- Criteria: `{"domain": "grasshopper", "operation": "create_repair", "language":
  "csharp"}`.

Drive path (test #6): `create_script` fed a `created_with_errors` result →
`needs_repair` → `on_repair` unlocks `repair_same_component`; fed a `usable`
result → `succeeded`; `repair_same_component` is terminal → graph `complete`.

## Testing (TDD)

1. **Single exact match:** descriptor satisfying all three criteria →
   `selected_template_id == "gh_csharp_create_repair"`, `graph` populated, finding
   `template_selected` (info), the matched evaluation's criteria all `accepted`.
2. **Isolation invariant (required):** call `select_template` twice; mutate
   selection A's nodes/edges; assert selection B is structurally pristine AND a
   third fresh selection is pristine — proving no shared mutable state and that
   the factory yields independent graphs.
3. **Zero match — value_mismatch:** descriptor with `language="python"` →
   `graph=None`, finding `no_matching_template` (error), the `language` criterion
   `outcome=="value_mismatch"` with `actual=="python"`.
4. **Zero match — missing_field:** descriptor omitting `language` → `graph=None`,
   `no_matching_template`, the `language` criterion `outcome=="missing_field"`,
   `actual is None` (distinct from value_mismatch).
5. **Ambiguous:** a custom registry with two templates whose criteria both match
   the descriptor → `graph=None`, `selected_template_id is None`, finding
   `ambiguous_template` (error) with `template_ids` = both ids (sorted).
6. **Birth→drive composition (payoff):** feed `select_template(...).graph` into
   `walk_plan_graph` with the canned LM1D-shaped create→repair results; assert the
   walk reaches `final_graph_status == "complete"`. Proves LM3B graphs are
   drivable by LM3A. No live calls; `walk_plan_graph` imported in the test only.
7. **Determinism:** `evaluations` order is stable across calls; per-criterion
   order follows the entry's sorted criteria.
8. **Purity — imports:** AST allowlist test (module imports only `copy`,
   `dataclasses`, `typing`, `rook.learning.plan_graph`); subprocess probe asserting
   importing `rook.learning.plan_graph_templates` loads no
   `rook.learning.plan_graph_bridge`, `rook.learning.plan_graph_walker`,
   `rook.agent.planner`, `rook.agent.tool_dispatcher`, `dspy`, or `litellm`.

## Governing invariant

**Every registered template must be drivable to `complete` by the LM3A walker
through the LM1G bridge (`walk_plan_graph` + `apply_tool_result`) using canned
tool results — not via hand-built `NodeOutcome`s.** A template that requires
hand-chosen verifier-node statuses is not admissible until a verifier-outcome
adapter exists.

## Out of scope (LM3B)

- **The 5-node verifier-mediated create-repair template** (`create → verify_receipt
  → repair → verify_clean → done`) is **deferred** until a verifier-outcome adapter
  exists — one that produces explicit `NodeOutcome` statuses for verifier nodes
  (the raw LM1G bridge cannot, since it collapses `created_with_errors` to
  `needs_repair` at the create node). Not faked here.
- **Parameter binding** (injecting descriptor values into the template) → LM3C.
- Any `Plan`→`PlanGraph` adapter / `planner.py` integration.
- Any free-text intent inference, scoring, ranking, or fallback selection.
- More than one registered template (the second template appears only as a test
  fixture for the ambiguity case).

## File touch list

- Add: `mcp_server/src/rook/learning/plan_graph_templates.py`
- Add: `mcp_server/tests/test_plan_graph_templates.py`
