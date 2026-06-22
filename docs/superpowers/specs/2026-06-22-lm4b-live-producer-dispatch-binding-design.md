# LM4B — Real Dispatcher Binding for One Live Producer Node (contract proof, NOT live Rhino dispatch)

**Date:** 2026-06-22
**Status:** Draft — pending user review
**Category:** LM campaign — Stage 5 (live PlanGraph execution), second slice (LM4B)
**Branch:** `codex/lm4b-live-producer-dispatch-binding`
**North-star:** `docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md`
**Builds on:** LM4A live adapter (`agent/plan_graph_live.py`), LM3I producer-result bridge (`learning/plan_graph_runner.py`, `learning/plan_graph_outcomes.py`), LM3F role-aware projection (`learning/plan_graph_projection.py`), LM1B tool-result view (`agent/chat/tool_result_view.py`), the `ToolDispatcher` agent dispatch path (`agent/tool_dispatcher.py`).

---

## Summary

LM4A proved the live producer adapter works when fed an **injected fake** dispatch callable. LM4B proves the **real `ToolDispatcher.dispatch`** callable satisfies that same injected-dispatch contract and drives one producer node end-to-end — and lands the named agent-layer composition root that a future one-node live runner (LM4C+) grows from.

The production code is a humble forwarder. Its load-bearing value is the **named boundary** plus the **real-dispatcher contract proof**: a genuine `ToolDispatcher` instance, routing a registered local tool through its public `dispatch()` method, satisfies the `Callable[[str, dict], Awaitable[dict]]` contract that `apply_live_producer_node` already consumes.

**This is real dispatcher contract proof, NOT real Rhino dispatch.** The test exercises the genuine `ToolDispatcher.dispatch` method against a **synthetic registered local tool** that returns realistic raw payloads. It does **not** reach Rhino over HTTP, does **not** wire LM4B into any production call site (`base_agent` / `spawn` / `chat_runner` are untouched), and is **not** a scheduler or sequencer. LM4B decides only that a real dispatcher *can* satisfy the dispatch contract — not where production agents call it.

One production addition (a single forwarding function) plus one new test module.

## Boundary (hard constraints)

- **Tiny forwarder, callable-only.** The production seam is a single `async` function that forwards to `apply_live_producer_node`. Its `dispatch` parameter is a callable `Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]` — it **never** accepts a `ToolDispatcher` object. (Production's stable handle is the `_tool_executor` callable, which equals `dispatcher.dispatch` only in the auto-built case; see `chat_runner.py:632-638`, `base_agent.py:174-181`, `spawn.py:247-251`.)
- **No dispatcher import in production.** The production module does **not** import `ToolDispatcher` / `tool_dispatcher`, `rook.server`, `chat`, or `ChatRunner`. Only the **test** may import `ToolDispatcher`.
- **Contract proof, not live Rhino.** The test instantiates a real `ToolDispatcher` and drives a registered synthetic local tool through Tier 1 (`_call_local`), which never calls `call_rhino`. A sentinel actively guarantees no Rhino contact (below).
- **No re-export of adapter types.** `LiveProducerResult` / `LiveProducerReason` are **not** re-exported from the new module. The function returns the adapter's `LiveProducerResult`; callers that need the type import it from `agent/plan_graph_live`.
- **Pure modules untouched.** No change to `learning/plan_graph*.py`. The LM4A adapter (`agent/plan_graph_live.py`) is **not** modified.
- **No scheduler, no call-site wiring, no port/targeting, no template mutation.** One node, one forwarding call. No `base_agent` / `spawn` / `chat_runner` edits, no `targeting.py`, no `execution_params` added to any registered template.
- **Never calls `apply_tool_result`.** Producer application stays the LM3I path (`apply_live_producer_node` → `apply_producer_result`).

## Module & files

- **Add:** `mcp_server/src/rook/agent/plan_graph_live_dispatch.py` — the named composition root with the single `run_live_producer_node` forwarder.
- **Add:** `mcp_server/tests/test_plan_graph_live_dispatch.py` — the real-`ToolDispatcher` contract proof (happy + error seam) plus the import-boundary guard.

No `agent/__init__.py` change: that module re-exports a fixed symbol set via lazy `__getattr__` over an explicit `_EXPORT_MODULES` map (`agent/__init__.py:38-70`), and `plan_graph_live` was deliberately omitted there. The new module follows the same full-path-import precedent — it is imported as `rook.agent.plan_graph_live_dispatch`, not surfaced on the package.

## Public surface

```python
# rook.agent.plan_graph_live_dispatch (additive)
async def run_live_producer_node(graph, node_id, dispatch):
    return await apply_live_producer_node(graph, node_id, dispatch)
```

Full shape, with the callable-only type and the no-re-export rule:

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from rook.agent.plan_graph_live import apply_live_producer_node

if TYPE_CHECKING:
    from rook.agent.plan_graph_live import LiveProducerResult
    from rook.learning.plan_graph import PlanGraph


async def run_live_producer_node(
    graph: "PlanGraph",
    node_id: str,
    dispatch: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
) -> "LiveProducerResult":
    """Drive one live producer node through a real dispatch callable.

    Thin composition root over the LM4A adapter. Production passes a real
    dispatch callable (e.g. ``ToolDispatcher.dispatch``); the adapter owns
    resolution, pre-dispatch side-effect safety, and delegation to the pure
    runner. This is the named home where a future one-node live runner accrues.
    """
    return await apply_live_producer_node(graph, node_id, dispatch)
```

Imports are limited to `rook.agent.plan_graph_live` (the forwarder target + the return type under `TYPE_CHECKING`) and, optionally and only for the `PlanGraph` type hint, `rook.learning.plan_graph` under `TYPE_CHECKING`. No runtime `rook.learning.*` import is required.

## Why the forwarder, despite its thinness

A callable-taking seam over the existing adapter is a near-synonym, but it earns its keep as the **named agent-layer boundary** the campaign's "each slice lands a named seam" rhythm expects:

- `plan_graph_live.py` stays the low-level adapter (resolve one node, fire dispatch, delegate-apply).
- `plan_graph_live_dispatch.py` is the live-dispatch composition root — the single, stable thing a future call site wires, and where one-node live-runner behavior accrues in LM4C+ without bloating the adapter or sneaking into `ChatRunner` / `ToolDispatcher`.
- The module is named `live_dispatch` (not `runtime`) deliberately: "runtime" reads as scheduler territory; "live dispatch" states exactly what this slice proves and does not overpromise.

## The contract proof (test-only; real `ToolDispatcher`, hermetically Rhino-free)

### Hermeticity posture: synthetic tool + active no-Rhino sentinel

Belt-and-suspenders for the first real-dispatcher test, setting the isolation pattern later live-layer tests inherit.

**Structural isolation.** A registered local tool name routes through Tier 1 `_call_local` (`tool_dispatcher.py:1929-1936, 1993`), which never calls `call_rhino`. Because the synthetic name is outside `NEEDS_VERIFICATION` (`execution_policy.py:69, 91`), the post-dispatch verification branch (`tool_dispatcher.py:1911-1925`) never issues `call_rhino("/command/prompt")`. So no Rhino contact by construction.

**Active enforcement.** Additionally patch the name **as bound in the dispatcher module** so any future dispatcher change that adds a Rhino/post-dispatch hook to this path fails loudly:

```python
async def _fail_call_rhino(*args, **kwargs):
    raise AssertionError("LM4B contract test must not call Rhino")

monkeypatch.setattr("rook.agent.tool_dispatcher.call_rhino", _fail_call_rhino)
```

The patch target is `rook.agent.tool_dispatcher.call_rhino` (the name the dispatcher module actually calls), **not** `rook.bridge.call_rhino`. The sentinel is installed in **both** the happy-path and error-path contract tests.

### Dispatcher + synthetic tool setup

- Instantiate a real `ToolDispatcher()` with **no port** (port-less, so no `port` is injected into local-tool kwargs; see `_call_local`'s port gating at `tool_dispatcher.py:2003-2006`).
- Register a synthetic local tool under the name `lm4b_live_producer_probe` via `dispatcher.register_local("lm4b_live_producer_probe", probe)`. The name intentionally avoids the `gh_*` namespace to dodge accidental policy/knowledge-wrapping coupling (it is not in `KNOWLEDGE_WRAPPED_TOOLS`, `TRANSFORM_FUNCTIONS`, `BRIDGE_ROUTES`, or `NEEDS_VERIFICATION`).
- The probe handler **records the kwargs it received** and returns a configured raw payload, so the test proves params actually traverse `ToolDispatcher.dispatch` (and `_call_local`'s `fn(**call_params)`), not a canned raw appearing nearby:

```python
class _Probe:
    def __init__(self, raw):
        self.calls = []
        self._raw = raw

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self._raw
```

- Pass `dispatcher.dispatch` (the bound method) into the seam: `run_live_producer_node(graph, "create_script", dispatcher.dispatch)`.

### Fixture producer node

Build the node directly (no template mutation): `execution_ref="lm4b_live_producer_probe"`, `metadata[OUTCOME_PROJECTION_ROLE_KEY]="artifact_producer"`, `metadata[EXECUTION_PARAMS_KEY]={...}`, and `status="ready"`. Reuse the LM4A fixture/raw-builder conventions from `test_plan_graph_live.py` (`_producer_graph`, `_usable_raw`, `_error_raw`, receipt builders).

### The mutation-evidence requirement (watchpoint)

The error-path payload **must** carry producer mutation evidence, or the proof inverts. Verified against the pure code:

- The producer gate `_has_mutation_evidence(receipt, repair_anchor)` (`plan_graph_projection.py:72-81`) returns `True` only if **any** of: `mutation.status in {"created","written","updated"}`, a non-empty `component_guid` (from `mutation.component_guid` or `repair_anchor.component_guid`), or a non-empty `repair_anchor`.
- For `artifact_status="created_with_errors"` with the gate satisfied, `_producer_outcome` (`plan_graph_projection.py:199-205`) returns `_producer_success(..., verified=False, ..., tool_status=...)` → node `succeeded`.
- **Without** mutation evidence, the same `created_with_errors` falls through to `_producer_blocked("producer: artifact existence unconfirmed")` (`plan_graph_projection.py:216-220`) → node `blocked`. LM3F correctly blocks; the proof would be meaningless.

The reused `_errors_receipt()` from `test_plan_graph_live.py` already satisfies the gate: it has `mutation.status == "created"`, `mutation.component_guid`, and a non-empty `repair_anchor`. The spec keeps that payload so the gate is satisfied via the canonical `mutation.status == "created"` plus component-guid/repair-anchor evidence.

### `tool_status="failed"` / `verified is False` derivation (verified)

For the error raw `{"success": False, "data": {"verified": False, "script_receipt": {...}}}`:
- `node_evidence_from_tool_result` (`plan_graph_outcomes.py:109-128`) → `normalize_tool_result` reads top-level `success: False` → `tool_status="failed"`; nested `data.verified == False` → `verified=False` (`tool_result_view.py:61-76`).
- The producer projection promotes graph `status` to `succeeded` while **preserving** `evidence.tool_status="failed"` and `evidence.verified=False` (status carried straight into `_producer_success`'s `NodeEvidence`).

### Assertions

**Happy path** (probe returns `_usable_raw()`):
- `result.applied is True`, `result.reason is None`, `result.outcome_status == "succeeded"`, `result.tool_name == "lm4b_live_producer_probe"`.
- `result.graph.nodes["create_script"].status == "succeeded"`.
- The probe was called exactly once and received **exactly** the declared `execution_params` — a plain dispatcher call with **no accidental `port`** key (assert `probe.calls[0] == declared_params` and `"port" not in probe.calls[0]`).
- The sentinel never fired.

**Error seam** (probe returns `_error_raw()` — `success: False` + `created_with_errors` + mutation evidence):
- `result.applied is True`, `result.reason is None`, `result.outcome_status == "succeeded"`.
- `node = result.graph.nodes["create_script"]`: `node.status == "succeeded"`, `node.evidence.tool_status == "failed"`, `node.evidence.verified is False`.
- The probe received exactly the declared params, no `port`.
- The sentinel never fired.

This is the exact seam LM4B exists to prove: **the raw tool says failed, the producer role says the artifact exists, and the graph node becomes `succeeded` with `tool_status == "failed"` and `verified is False`** — now demonstrated through a real `ToolDispatcher.dispatch`.

## Import-boundary guard (test)

Mirror the LM4A adapter guard (`test_plan_graph_live.py:354-390`), an established pattern across six sibling pure modules (`test_plan_graph_bridge.py:209`, `_runner.py:168`, `_verifiers.py:196`, `_templates.py:196`, `_walker.py:322`, plus the adapter):

- AST-parse `plan_graph_live_dispatch.py`.
- **Allowed** rook imports: `rook.agent.plan_graph_live`; optionally `rook.learning.plan_graph` (typing only).
- **Forbidden** substrings in the production module: `tool_dispatcher`, `rook.server`, `chat`, `ChatRunner`; no `_producer_*` private import/attribute/name; no wildcard (`import *`).
- The `ToolDispatcher` / `tool_dispatcher` ban is asserted against the **production module only** — the contract test legitimately imports `ToolDispatcher`, so the guard must not scan the test file.

The reverse guard already covers the new module for free: `test_pure_modules_do_not_import_live_adapter` (`test_plan_graph_live.py:423-437`) forbids the substring `"plan_graph_live"` in `learning/plan_graph*.py`, and `"plan_graph_live_dispatch"` contains it. No reverse-guard extension needed.

## Approved decisions

- **A — Tiny named seam + real-dispatcher contract test only.** Production is a one-line `async` forwarder; the proof is the slice's value.
- **B — Callable-only seam.** `dispatch` is a callable; the module never imports or accepts `ToolDispatcher`. Only the test imports it.
- **C — Real `ToolDispatcher`, synthetic local tool, port-less.** `lm4b_live_producer_probe` registered via `register_local`; `dispatcher.dispatch` passed into the seam.
- **D — Active no-Rhino sentinel** patched at `rook.agent.tool_dispatcher.call_rhino`, used in both contract tests.
- **E — Mutation-evidence payload mandatory** on the error path (`mutation.status == "created"` + component guid/repair anchor) so LM3F promotes to `succeeded` instead of blocking.
- **F — Params fidelity asserted.** The probe records kwargs; the test proves the declared params arrive verbatim with no injected `port`.
- **G — Strict import-boundary guard** for the new module; reverse guard already covers it by substring.
- **H — No re-export, no `__init__` change, no call-site wiring, no scheduler, no port/targeting, no template mutation.**

## Testing (TDD)

1. **Happy-path contract proof:** real `ToolDispatcher` + registered `lm4b_live_producer_probe` returning `_usable_raw()`; under the sentinel, `run_live_producer_node(..., dispatcher.dispatch)` yields `applied`, `outcome_status="succeeded"`, `tool_name="lm4b_live_producer_probe"`, node `succeeded`; probe called once with exactly the declared params and no `port`.
2. **Error-seam contract proof:** probe returns `_error_raw()` (`success: False`, `created_with_errors` + mutation evidence); under the sentinel, `applied`, `outcome_status="succeeded"`, node `succeeded`, `evidence.tool_status == "failed"`, `evidence.verified is False`; probe got exactly the declared params, no `port`.
3. **Params-fidelity assertion** (folded into 1 & 2): `probe.calls[0]` equals the declared `execution_params` dict and contains no `port` key — proving a plain dispatcher call carrying the adapter's deep-copied params.
4. **Sentinel proof:** both tests install the `rook.agent.tool_dispatcher.call_rhino` sentinel; neither triggers it (no Rhino contact).
5. **Import-boundary guard:** AST allow/forbid lists above, asserted against the production module only.

## Out of scope (LM4B)

- Real Rhino dispatch / HTTP / live `gh_*` tool execution — the proof uses a synthetic local tool.
- Call-site wiring into `base_agent` / `spawn` / `chat_runner` — deferred; production's stable seam is a callable, and where to wire it is a later decision.
- Port / multi-instance targeting (`targeting.py`) — deferred.
- Template `execution_params` binding (`plan_graph_templates.py`) — the test builds a fixture node directly.
- Scheduler / sequencer / multi-node walk; any new public primitive beyond `run_live_producer_node`.
- Re-exporting `LiveProducerResult` / `LiveProducerReason`; any `agent/__init__.py` change.
- `apply_tool_result` on the producer path.

## Roadmap (recorded, not built)

Stage 5 continues. With LM4B proving a real dispatcher satisfies the dispatch contract through a named composition root, the next slices are: **LM4C — one-node live runner / call-site integration** (deciding where production agents invoke `run_live_producer_node`, likely against the `_tool_executor` callable seam), then knowledge-push / rolling-memory persistence at node boundaries, bounded repair/escalation policy, and the eval harness measuring whether the graph improves local-model reliability.

## File touch list

- Add: `mcp_server/src/rook/agent/plan_graph_live_dispatch.py` — `run_live_producer_node` forwarder (callable-only; no dispatcher import).
- Add: `mcp_server/tests/test_plan_graph_live_dispatch.py` — real-`ToolDispatcher` happy + error-seam contract proofs (synthetic `lm4b_live_producer_probe`, no-Rhino sentinel, params fidelity) + import-boundary guard.
