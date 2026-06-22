# LM3G — Role Adoption + Verifier-Mediated Template Revival

**Date:** 2026-06-22
**Status:** Approved (design)
**Category:** LM campaign — LM3 (Planner / PlanGraph execution scaffold), seventh slice
**Branch:** `codex/lm3g-role-adoption-template-revival`
**North-star:** `docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md`
**Builds on:** LM1E reducer/types (`plan_graph.py`), LM1G bridge (`plan_graph_bridge.py`), LM3B/LM3C templates (`plan_graph_templates.py`), LM3E verifier-step runner (`plan_graph_runner.py`), LM3F role-aware projection (`plan_graph_projection.py`).

---

## Summary

LM3G makes the LM3F projection role **adopted on the graph node** and adds the
**producer runner primitive** that consumes it, then proves the payoff: a
verifier-mediated template driven end-to-end (non-live) where a producer node's
`created_with_errors` evidence promotes to `succeeded` and **unlocks a downstream
verifier through the reducer's `requires` edge**.

This is the slice where LM3F's `status=succeeded` / `verified=False` split — the
architectural hinge — first pays off inside a registered template. It ships two
small production additions (a role accessor + the producer step) plus a second
registered template, and proves composition with a **test-only explicit
sequence** — no production sequencer, no broad autonomous runner.

The role lives in `node.metadata` (not a typed `PlanGraphNode` field): a typed
field of type `OutcomeProjectionRole` would invert the strict one-way layering
(`plan_graph_projection → plan_graph`) or force the role taxonomy down into the
core reducer dataclass before revival proves it belongs there. Metadata is the
graph's existing extension seam, already exercised by LM3C's `bind_parameters`.

## Boundary (hard constraints)

- **Role lives in `node.metadata`**, keyed by a constant, read by a strict
  boundary helper. No typed `PlanGraphNode` field; no typed-field roadmap
  commitment.
- **Invalid role in node metadata is graph-data**, surfaced as a runner
  not-applied diagnostic — never a raw exception. (The raise stays in
  `project_receipt_outcome` for direct API misuse.)
- **`apply_producer_step` is producer-restricted, no default.** It requires
  `node.metadata["outcome_projection_role"] == "artifact_producer"`. Missing role
  → `role_missing`; present-but-invalid → `role_invalid`; valid-but-not-producer
  → `role_not_producer`. It never defaults the role and never accepts
  `artifact_verifier` / `direct_task`.
- **`runnable_nodes(graph)` is the sole readiness authority** for the producer
  step (same as the verifier step). The guard order is fixed: existence →
  runnable → evidence → role. A pending node with invalid metadata returns
  `node_not_runnable`, **not** `role_invalid` — reducer readiness precedes
  data diagnostics, and tests pin this precedence.
- **Never mutates the input graph.** Every not-applied path returns the input
  graph object unchanged (`result.graph is graph`); an applied result returns
  `apply_outcome`'s fresh graph.
- **Second template, additive.** `gh_csharp_create_verify_repair` is added beside
  the untouched `gh_csharp_create_repair`. Distinct, structured criteria
  (`operation="create_verify_repair"`) — no inference of verifier-mediation from
  `verify=true` or free text (no scoring/interpretation in the birth seam).
- **Honest template naming.** The template proves "create was verifier-mediated
  before repair," **not** "repair result was reverified clean." Terminal
  `repair_same_component` means the repair step returned `usable` through the
  existing bridge, not that a second verifier node judged it.
- **Role is intrinsic to the template**, baked into `build_graph` metadata, not a
  descriptor-bound value. `plan_graph_templates` does **not** import
  `plan_graph_projection`; it uses literal metadata strings, pinned to the
  projection constants by a test (birth stays independent of drive/projection).
- **Test-only composition.** No production `run_*` sequencer. The end-to-end proof
  is a test that composes the dedicated primitives explicitly and drives the
  repair node through the LM1G bridge (`apply_tool_result`) — **not**
  `walk_plan_graph` (avoids walker re-init interfering with the already-mutated
  graph).
- **No change** to `walk_plan_graph`, LM1F (`plan_graph_outcomes.py`), or LM3F's
  projection logic (`project_receipt_outcome` and its helpers are consumed, not
  modified). No live tools, no model calls, no `planner.py`, no
  `needs_escalation`.
- **Import-light.** New imports: `plan_graph_runner` adds
  `rook.learning.plan_graph_projection`. Enforced by updated AST allowlist +
  subprocess probe.

## Module & files

- **Modify (additive):** `mcp_server/src/rook/learning/plan_graph_projection.py`
  — add `OUTCOME_PROJECTION_ROLE_KEY` constant and
  `projection_role_for_node(node)` helper; add `PlanGraphNode` to the existing
  `plan_graph` import. No change to `project_receipt_outcome` or its helpers.
- **Modify (additive):** `mcp_server/src/rook/learning/plan_graph_runner.py` —
  add `ProducerStepReason`, `ProducerStepResult`, `apply_producer_step`; import
  the projection symbols. Existing `apply_verifier_step` unchanged.
- **Modify (additive):** `mcp_server/src/rook/learning/plan_graph_templates.py` —
  add `_build_gh_csharp_create_verify_repair()` and a second `DEFAULT_REGISTRY`
  entry. Existing entry and all functions unchanged.
- **Modify:** `mcp_server/tests/test_plan_graph_runner.py` — update the AST
  allowlist to `{plan_graph, plan_graph_verifiers, plan_graph_projection}`; add
  producer-step tests + the end-to-end composition test.
- **Modify:** `mcp_server/tests/test_plan_graph_projection.py` — add
  `projection_role_for_node` helper tests.
- **Modify:** `mcp_server/tests/test_plan_graph_templates.py` — add selection /
  ambiguity / metadata-pin tests for the new template.

## Public surface

```python
# plan_graph_projection.py (additive)
OUTCOME_PROJECTION_ROLE_KEY = "outcome_projection_role"

def projection_role_for_node(node: PlanGraphNode) -> OutcomeProjectionRole | None:
    """The node's declared projection role if present AND valid, else None.
    Never raises (node metadata is graph data, not API misuse)."""

# plan_graph_runner.py (additive)
ProducerStepReason = Literal[
    "unknown_node", "node_not_runnable", "evidence_missing",
    "role_missing", "role_invalid", "role_not_producer",
]

@dataclass(frozen=True)
class ProducerStepResult:
    graph: PlanGraph
    applied: bool
    node_id: str
    outcome_status: OutcomeStatus | None
    reason: ProducerStepReason | None

def apply_producer_step(graph: PlanGraph, node_id: str) -> ProducerStepResult:
    ...
```

## Role-on-node mechanism

`projection_role_for_node` returns the declared role only if present **and** valid
against LM3F's role set, else `None`; it never raises. The producer step
distinguishes *missing* from *invalid* using only **public** projection symbols
(no private `_VALID_ROLES` import):

```python
present = OUTCOME_PROJECTION_ROLE_KEY in node.metadata
role    = projection_role_for_node(node)   # valid role or None
# not present     -> role_missing
# present, role is None (invalid value) -> role_invalid
# role valid but != "artifact_producer" -> role_not_producer
```

## `apply_producer_step` algorithm

Same-node self-projection (symmetric to the verifier step's cross-node read).
Guard ladder — each returns not-applied with the named reason and the **input
graph unchanged**; precedence is fixed and test-pinned:

1. `node_id not in graph.nodes` → `unknown_node`.
2. `node_id not in {n.id for n in runnable_nodes(graph)}` → `node_not_runnable`.
   (Sole readiness authority; precedes evidence/role diagnostics.)
3. `graph.nodes[node_id].evidence is None` → `evidence_missing`.
4. role key absent → `role_missing`.
5. role present but invalid → `role_invalid`.
6. valid role ≠ `artifact_producer` → `role_not_producer`.
7. `outcome = project_receipt_outcome(node.evidence, "artifact_producer")`;
   `new_graph = apply_outcome(graph, node_id, outcome)`; return applied with
   `outcome_status=outcome.status`.

The producer projection promotes a `created_with_errors` (mutation-evidenced)
receipt to `succeeded` / `verified=False`; `apply_outcome` then flips the
`requires`-downstream verifier node to `ready`. A producer receipt **without**
mutation evidence projects (honestly) to `blocked` — the step still "applies"
(returns `applied=True`, `outcome_status="blocked"`), and the downstream verifier
stays `pending`. The step does not second-guess the projection.

## The 3-node template

`gh_csharp_create_verify_repair`, criteria
`{domain: "grasshopper", operation: "create_verify_repair", language: "csharp"}` —
disjoint from `gh_csharp_create_repair`'s `operation: "create_repair"`:

```
create_script        metadata[outcome_projection_role] = "artifact_producer"
  --requires-->   verify_create   metadata[outcome_projection_role] = "artifact_verifier"
  --on_repair-->  repair_same_component  [is_terminal]
```

- `create_script`: `execution_ref="gh_create_csharp_script:v1"`,
  `verifier_ref="script_receipt_has_artifact_or_errors:v1"`,
  `repair_policy_ref="repair_same_component_once:v1"`, plus the producer role
  metadata.
- `verify_create`: a verifier node; `requires` edge from `create_script`. Its
  `artifact_verifier` role metadata is **self-describing only** — `apply_verifier_step`
  is hardcoded to the verifier projection and does not read it (forward-looking
  for the deferred 5-node slice / a future general projection step). Only
  `create_script`'s role is functionally consumed in LM3G.
- `repair_same_component`: terminal; `on_repair` edge from `verify_create`;
  `execution_ref="gh_update_script:v1"`.

`build_graph` sets the role metadata with **literal strings** (`"outcome_projection_role"`
/ `"artifact_producer"` / `"artifact_verifier"`); a test pins those literals to
the projection constants (`OUTCOME_PROJECTION_ROLE_KEY` + the role set) so they
cannot drift — without `plan_graph_templates` importing `plan_graph_projection`.

Bindings: reuse the existing pattern (`goal → memory_fact`,
`component_name → create_script.metadata`, both optional). The role is **not** a
binding (it is intrinsic to the template).

## End-to-end composition proof (test-only)

One test composes the dedicated primitives + bridge explicitly:

1. `select_and_bind({domain, operation: "create_verify_repair", language})` →
   bound graph; `initialize_graph(graph)` → `create_script` becomes `ready`
   (root).
2. Inject `graph.nodes["create_script"].evidence` = a `NodeEvidence` whose
   `receipt` is a `created_with_errors` `script_receipt` **carrying mutation
   evidence** (e.g. `mutation.status="created"` and/or a `component_guid`) so the
   producer gate promotes.
3. `apply_producer_step(graph, "create_script")` → assert `applied`,
   `outcome_status="succeeded"`, the result graph's `create_script` is
   `succeeded` with `evidence.verified is False`, and `verify_create` is now
   `ready` — **the producer-unlocks-verifier-via-`requires` proof.**
4. `apply_verifier_step(graph, "verify_create", "create_script")` → assert
   `outcome_status="needs_repair"`, `verify_create` is `needs_repair`, and
   `repair_same_component` is now `ready` (via `on_repair`).
5. `apply_tool_result(graph, "repair_same_component", <raw result with a usable
   script_receipt>)` → `repair_same_component` becomes `succeeded`. Bridge seam
   only for the repair node — **not** `walk_plan_graph` (avoids walker re-init on
   the already-mutated graph); producer/verifier steps use their dedicated
   primitives.
6. Assert `graph_status(graph) == "complete"`.

## Approved decisions

- **A — Role in `node.metadata`** (constant key + strict helper), not a typed
  field; the typed-field option is rejected for this slice (layering inversion /
  premature taxonomy in the core dataclass) and no roadmap is committed.
- **B — Producer-restricted, no default.** `apply_producer_step` requires the
  node's declared role to be exactly `artifact_producer`; missing / invalid /
  non-producer are distinct not-applied reasons.
- **C — `runnable_nodes` is the sole readiness authority**, and the guard order
  (runnable before evidence/role) is fixed and test-pinned.
- **D — Minimal 3-node verifier-mediated template**, registered (not a fixture),
  added beside the untouched 2-node; the full 5-node re-verification loop is
  deferred.
- **E — Test-only explicit composition.** No production sequencer; the repair node
  is driven via `apply_tool_result`, the producer/verifier nodes via their
  primitives.

## Testing (TDD)

1. **Helper `projection_role_for_node`:** absent key → `None`; each of the three
   valid roles → itself; present-but-invalid (e.g. `"banana"`) → `None`; never
   raises.
2. **Producer happy path:** `created_with_errors` + mutation-evidence on a runnable
   producer node → `applied`, `succeeded`, `verified is False`, downstream
   `verify_create` flips `pending → ready`.
3. **Producer gate-blocked:** producer evidence **without** mutation evidence →
   `applied=True`, `outcome_status="blocked"`, downstream verifier stays
   `pending` (the step honors the projection, does not second-guess it).
4. **Producer not-applied reasons** (each returns `result.graph is graph`):
   `unknown_node`; `node_not_runnable` (pending node); `evidence_missing`;
   `role_missing` (no role key); `role_invalid` (role `"banana"`);
   `role_not_producer` (role `"artifact_verifier"`).
5. **Guard precedence (watchpoint):** a node that is BOTH pending AND has an
   invalid role returns `node_not_runnable` (reducer readiness wins) — pins the
   order so diagnostics can't be reordered ahead of readiness.
6. **Template selection:** descriptor `operation="create_verify_repair"` selects
   `gh_csharp_create_verify_repair`; `operation="create_repair"` still selects the
   2-node entry.
7. **Ambiguity disjointness:** no single descriptor matches both entries (the
   exact-match criteria are disjoint); the ambiguity guard is never triggered for
   the canonical descriptors.
8. **Metadata-literal pin:** the built template's `create_script.metadata` equals
   `{OUTCOME_PROJECTION_ROLE_KEY: "artifact_producer", ...}` and `verify_create`'s
   equals `artifact_verifier` — pinned against the imported projection constant
   (test imports it; production template does not).
9. **End-to-end composition:** the six-step sequence above, asserting every
   transition through to `graph_status == "complete"`.
10. **Purity:** updated runner AST allowlist
    (`{plan_graph, plan_graph_verifiers, plan_graph_projection}`); subprocess probe
    (importing `plan_graph_runner` loads no `tool_dispatcher` / `dspy` / `litellm`);
    `plan_graph_templates` AST allowlist still `{plan_graph}` (no projection import).

## Out of scope (LM3G)

- Typed `PlanGraphNode` role field; production `run_*` sequencer / scheduler;
  live role-aware evidence capture (injected in the proof).
- The full 5-node create→verify→repair→verify→done loop (repair-as-producer +
  second verifier pass) — next candidate.
- Any change to `walk_plan_graph`, LM1F, or LM3F's `project_receipt_outcome`
  logic; `needs_escalation`; `planner.py`.

## Roadmap (recorded, not built)

**Next candidate — full 5-node verifier-mediated loop** (`create → verify_create →
repair → verify_repair → terminal`): repair becomes a producer (its own evidence
projected by `artifact_producer`), a second verifier pass re-judges the repaired
artifact, and the terminal reaches "reverified clean." Separately, a **role-aware
live evidence-capture bridge** would let a real run land producer evidence on a
node without LM1F's conservative outcome, closing the non-live gap.

## File touch list

- Modify: `plan_graph_projection.py` — `OUTCOME_PROJECTION_ROLE_KEY`,
  `projection_role_for_node`, `PlanGraphNode` import.
- Modify: `plan_graph_runner.py` — `ProducerStepReason`, `ProducerStepResult`,
  `apply_producer_step`, projection imports.
- Modify: `plan_graph_templates.py` — `_build_gh_csharp_create_verify_repair`,
  second `DEFAULT_REGISTRY` entry.
- Modify: `test_plan_graph_projection.py` — helper tests.
- Modify: `test_plan_graph_runner.py` — allowlist update, producer-step tests,
  end-to-end composition test.
- Modify: `test_plan_graph_templates.py` — selection / ambiguity / metadata-pin
  tests.
