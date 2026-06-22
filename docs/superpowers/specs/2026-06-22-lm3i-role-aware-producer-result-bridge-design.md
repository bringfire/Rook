# LM3I — Role-Aware Producer-Result Bridge (live-shaped raw payloads, NOT live dispatch)

**Date:** 2026-06-22
**Status:** Approved (design)
**Category:** LM campaign — LM3 (Planner / PlanGraph execution scaffold), ninth slice; stage 4 (live execution bridge) at the pure-dict layer
**Branch:** `codex/lm3i-role-aware-producer-result-bridge`
**North-star:** `docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md`
**Builds on:** LM1B tool-result view (`agent/chat/tool_result_view.py`), LM1E reducer (`plan_graph.py`), LM1F tool-result adapter (`plan_graph_outcomes.py`), LM3F role-aware projection (`plan_graph_projection.py`), LM3G producer step (`plan_graph_runner.py`), LM3H 5-node chain template (`plan_graph_templates.py`).

---

## Summary

LM3I lets a **realistic raw tool-result payload** land on a producer node as evidence and be projected by the node's declared `artifact_producer` role — so `created_with_errors → succeeded / verified=False` — instead of collapsing through LM1F's conservative direct-task mapping (`created_with_errors → needs_repair`). If LM3H proved "the graph shape works," LM3I proves "live-shaped results can feed that graph shape truthfully."

**This is NOT live dispatch.** LM3I stays a pure learning-layer slice: it consumes raw tool-result **dicts** of the shape `{success, data: {script_receipt: {...}}}` (what `gh_create_csharp_script` / `gh_update_script` return), built in tests. It does **not** execute tools, make HTTP calls, touch the dispatcher, or schedule. "Live-shaped" means real payloads instead of hand-built `NodeEvidence`. Wiring capture to the actual dispatcher/HTTP path is a later layer (stage 5), explicitly out of scope.

Two production additions, both single-sourcing existing logic:
1. **`node_evidence_from_tool_result(raw) -> NodeEvidence`** — promote LM1F's evidence-construction to a public, role-agnostic capture helper consumed by both LM1F (then conservative status) and LM3I (then role projection).
2. **`apply_producer_result(graph, node_id, raw_result)`** — the live-shaped, producer-restricted analog of LM3G's `apply_producer_step`, sharing a private **producer application core** with it.

## Boundary (hard constraints)

- **Pure, live-SHAPED, not live.** Consumes raw result dicts only. No tool execution, no HTTP, no dispatcher, no scheduler, no network. Import-light.
- **Single-sourced capture.** `node_evidence_from_tool_result` is the one owner of "raw tool result → `NodeEvidence`." LM1F is refactored (behavior-preserving) to build evidence via it; LM3I calls it then role-projects. Only the **evidence** helper is promoted — LM1F's private status/memory helpers stay private.
- **LM1F byte-equivalent after refactor.** `node_outcome_from_tool_result` produces an identical `NodeOutcome` (status, evidence, memory_updates, message, error) for all inputs. Proven by its existing tests **plus a full-shape parity test** (representative raw results → exact expected `NodeOutcome`).
- **Shared producer APPLICATION core, not a shared step core.** The two public primitives intentionally have different pre-apply ladders:
  - `apply_producer_step`: exists → runnable → `evidence_missing` → role → apply existing `node.evidence`.
  - `apply_producer_result`: exists → runnable → role → **capture raw** → apply captured evidence.
  The truly shared piece is `_apply_admissible_producer(graph, node_id, evidence)` (project + apply) plus the shared guard helpers (runnable check, role check). The ordering difference is preserved.
- **`apply_producer_step` is byte-behavioral.** Its public behavior — including `evidence_missing` and the LM3G test-pinned guard precedence — is unchanged. Its LM3G tests stay green, unmodified.
- **`apply_producer_result` is producer-restricted, no default role.** Reasons are the subset `{unknown_node, node_not_runnable, role_missing, role_invalid, role_not_producer}` — **never** `evidence_missing`. A malformed / receipt-less raw result becomes an **applied `blocked`** outcome (from the projection), not a not-applied diagnostic.
- **Admissibility before capture.** `apply_producer_result` validates exists → runnable → role **first**; an inadmissible node returns not-applied **without** interpreting the raw result.
- **Never calls `apply_tool_result`.** No `needs_escalation`. No walker / projection-logic / verifier-logic / reducer / template change.

## Module & files

- **Modify (additive + behavior-preserving refactor):**
  `mcp_server/src/rook/learning/plan_graph_outcomes.py` — add public
  `node_evidence_from_tool_result`; refactor `node_outcome_from_tool_result` to
  build evidence via it (identical output). Private status/memory helpers
  unchanged. LM1F's import allowlist unchanged (still `plan_graph` +
  `tool_result_view`).
- **Modify (additive):** `mcp_server/src/rook/learning/plan_graph_runner.py` —
  add `apply_producer_result` + the shared producer application core helpers;
  refactor `apply_producer_step` to ride the shared core **without changing its
  order/behavior**. Add the `plan_graph_outcomes` import.
- **Modify:** `mcp_server/tests/test_plan_graph_outcomes.py` — capture-helper
  tests + the full-shape LM1F parity test.
- **Modify:** `mcp_server/tests/test_plan_graph_runner.py` — `apply_producer_result`
  tests, the live 5-node end-to-end proof, and the updated import allowlist.

## Public surface

```python
# plan_graph_outcomes.py (additive)
def node_evidence_from_tool_result(result: Any) -> NodeEvidence:
    """Role-agnostic capture: raw tool result -> NodeEvidence (tool_status,
    verified, receipt, repair_anchor, message, error). No status/role semantics."""

# plan_graph_runner.py (additive; reuses LM3G ProducerStepResult / ProducerStepReason)
def apply_producer_result(
    graph: PlanGraph, node_id: str, raw_result: Any
) -> ProducerStepResult:
    ...
```

`apply_producer_result` returns a `ProducerStepResult` whose `reason` is drawn
from the subset above (never `evidence_missing`).

## Capture helper (single-sourced from LM1F)

`node_evidence_from_tool_result(raw)` reproduces LM1F's exact evidence block:

```python
view = normalize_tool_result(raw)
receipt = _extract_script_receipt(raw)
repair_anchor = _repair_anchor(receipt)
return NodeEvidence(
    tool_status=view.status,
    verified=view.verified,
    receipt=deepcopy(receipt) if receipt is not None else None,
    repair_anchor=deepcopy(repair_anchor) if repair_anchor is not None else None,
    message=view.message or view.verification_note,
    error=view.error,
)
```

`node_outcome_from_tool_result` is refactored to call it, then compute status +
memory exactly as before (it re-extracts `receipt`/`repair_anchor` locally for its
own `_outcome_status` / `_memory_updates`, which are pure and idempotent). Malformed
raw → `view` defaults + `receipt=None` — **identical** to today; no new failure
semantics in capture.

## Producer application core & primitives

Private helpers in `plan_graph_runner.py`:

- `_producer_runnable_check(graph, node_id) -> ProducerStepReason | None` — exists
  (`unknown_node`) → runnable via `runnable_nodes` (`node_not_runnable`); else None.
- `_producer_role_check(node) -> ProducerStepReason | None` — `role_missing` (key
  absent) → `role_invalid` (present but not in the role set, via
  `projection_role_for_node`) → `role_not_producer` (valid but ≠
  `artifact_producer`); else None. Uses only public projection symbols.
- `_apply_admissible_producer(graph, node_id, evidence) -> ProducerStepResult` —
  `project_receipt_outcome(evidence, "artifact_producer")` then `apply_outcome`;
  returns `applied=True` with `outcome_status=outcome.status`.

`apply_producer_step` (refactored, behavior-identical):
1. `_producer_runnable_check` → not-applied on reason.
2. `node.evidence is None` → `evidence_missing`.
3. `_producer_role_check` → not-applied on reason.
4. `_apply_admissible_producer(graph, node_id, node.evidence)`.

`apply_producer_result` (new):
1. `_producer_runnable_check` → not-applied on reason.
2. `_producer_role_check` → not-applied on reason.
3. `evidence = node_evidence_from_tool_result(raw_result)` — **capture only after
   admissible.**
4. `_apply_admissible_producer(graph, node_id, evidence)`.

Both return the **input graph object** on every not-applied path; the applied path
returns `apply_outcome`'s fresh graph. `apply_producer_step`'s order
(`evidence_missing` between runnable and role) is preserved exactly.

## Live proof (test-only; the LM3H chain fed from raw payloads)

Drive the registered `gh_csharp_create_verify_repair_verify` template from
realistic raw dicts; `initialize_graph` once, before any step:

1. `apply_producer_result(graph, "create_script", {"success": True, "data":
   {"script_receipt": {<created_with_errors + mutation evidence>}}})` →
   `applied`, `outcome_status="succeeded"`, `create_script.evidence.verified is
   False`; `verify_create` ready.
2. `apply_verifier_step(graph, "verify_create", "create_script")` → `needs_repair`;
   `repair_same_component` ready.
3. `apply_producer_result(graph, "repair_same_component", {"success": True, "data":
   {"script_receipt": {<usable + mutation evidence>}}})` → `succeeded`,
   `repair_same_component.evidence.verified is True`; `verify_repair` ready.
   **← live-shaped repair-as-producer from a raw payload.**
4. `apply_verifier_step(graph, "verify_repair", "repair_same_component")` →
   `succeeded`; `done` ready.
5. `apply_outcome(graph, "done", NodeOutcome(status="succeeded", message="done:
   reverified clean"))`; `graph_status(graph) == "complete"`.

Producers are now fed raw tool-result dicts; verifiers still cross-read evidence
via `apply_verifier_step`; `done` is finalized by the explicit terminal outcome.

## Approved decisions

- **A — Single-source capture** via public `node_evidence_from_tool_result`; LM1F
  refactored behavior-preserving (full-shape parity test).
- **B — Shared producer APPLICATION core** (`_apply_admissible_producer` + guard
  helpers); the two public primitives keep their distinct pre-apply ladders.
- **C — `apply_producer_result` producer-restricted, no `evidence_missing`**;
  malformed raw → applied `blocked`; admissibility before capture.
- **D — `apply_producer_step` byte-behavioral**; LM3G tests unchanged and green.
- **E — Live-SHAPED, not live**; pure dicts only; no dispatcher/HTTP/scheduler.

## Testing (TDD)

1. **Capture helper:** a realistic raw dict yields `NodeEvidence` with the right
   `tool_status`/`verified`/`receipt`/`repair_anchor`/`message`/`error`; a
   malformed raw (non-dict, or no `data.script_receipt`) yields `receipt=None`,
   identical to LM1F's current behavior.
2. **LM1F full-shape parity (tightening 2):** for representative raw results
   (`usable`, `created_with_errors`, malformed/no-receipt, failed), assert
   `node_outcome_from_tool_result(raw)` equals the expected full `NodeOutcome`
   (status, evidence — incl. receipt/repair_anchor/message/error —,
   memory_updates, message, error) via dataclass `==`. Existing LM1F tests also
   stay green, unmodified.
3. **`apply_producer_result` happy:** `created_with_errors` + mutation evidence →
   `applied`, `outcome_status="succeeded"`, `evidence.verified is False`,
   downstream verifier flips `pending → ready`; `usable` + mutation → `succeeded`,
   `verified is True`.
4. **Malformed raw → applied blocked (tightening 3):** a raw with no
   `script_receipt` → `result.applied is True`, `result.reason is None`,
   `result.outcome_status == "blocked"`, `result.graph is not graph`, and
   `result.graph.nodes[node_id].status == "blocked"` — distinct from a not-applied
   admission failure.
5. **Not-applied admission reasons + no-capture (tightening 3 cont.):** each of
   `unknown_node` / `node_not_runnable` / `role_missing` / `role_invalid` /
   `role_not_producer` returns the **input graph object** (`result.graph is
   graph`), `applied is False`. For these, pass a **raw object that raises if
   interpreted** (e.g. an object whose `.get`/deepcopy explodes) and prove the
   call still returns the admission reason — proving the raw was never captured.
6. **`apply_producer_step` regression:** its LM3G tests + the guard-precedence test
   (pending + invalid role → `node_not_runnable`) pass unchanged.
7. **Live end-to-end:** the §"Live proof" sequence, asserting every transition
   through `graph_status == "complete"`, with `initialize_graph` called once.
8. **Purity:** runner AST allowlist updated to `{plan_graph,
   plan_graph_verifiers, plan_graph_projection, plan_graph_outcomes}`; subprocess
   probe still loads no `tool_dispatcher` / `dspy` / `litellm` (the transitive
   `tool_result_view` is pure).

## Out of scope (LM3I)

- Live dispatch / HTTP / tool execution / wiring capture to the real dispatcher
  path — stage 5.
- Production sequencer / scheduler; any new public role primitive beyond
  `apply_producer_result`.
- `needs_escalation`; verifier-result or done-result live primitives (verifiers
  cross-read via `apply_verifier_step`; `done` is an explicit outcome).
- Any change to the reducer, walker, projection logic, verifier logic, or
  templates.

## Roadmap (recorded, not built)

Stage 4 (live execution bridge) is established here at the pure-dict layer. Next:
**stage 5 — runner / scheduler / eval harness**, and the actual wiring of
`node_evidence_from_tool_result` / `apply_producer_result` to the live dispatcher
path (real `gh_create_csharp_script` / `gh_update_script` results landing on graph
nodes during an agent run).

## File touch list

- Modify: `plan_graph_outcomes.py` — public `node_evidence_from_tool_result`;
  `node_outcome_from_tool_result` refactored to use it (identical output).
- Modify: `plan_graph_runner.py` — `apply_producer_result` + shared producer
  application core; `apply_producer_step` rides the core, behavior-identical; add
  `plan_graph_outcomes` import.
- Modify: `test_plan_graph_outcomes.py` — capture-helper + full-shape parity tests.
- Modify: `test_plan_graph_runner.py` — `apply_producer_result` tests, live 5-node
  proof, updated allowlist.
