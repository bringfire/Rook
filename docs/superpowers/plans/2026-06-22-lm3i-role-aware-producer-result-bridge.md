# LM3I Role-Aware Producer-Result Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let realistic raw tool-result dicts land on producer nodes as evidence and be projected by the node's `artifact_producer` role (`created_with_errors → succeeded / verified=False`), without LM1F's conservative direct-task mapping — and prove the registered 5-node chain drives to `complete` from raw payloads.

**Architecture:** (1) single-source LM1F's evidence construction into a public `node_evidence_from_tool_result`; (2) add `apply_producer_result` sharing a private producer *application* core with `apply_producer_step` (which stays byte-behavioral). Live-SHAPED (raw dicts), NOT live dispatch — pure, no HTTP/tools/scheduler.

**Tech Stack:** Python 3.12, stdlib, pytest. Test runner: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider`.

## Global Constraints

- **Live-SHAPED, not live.** Consumes raw result dicts only; no tool execution, HTTP, dispatcher, scheduler, or network.
- **Single-sourced capture.** `node_evidence_from_tool_result(raw) -> NodeEvidence` is the one owner of "raw → evidence." LM1F's `node_outcome_from_tool_result` is refactored to build evidence via it (identical output); only the evidence helper is promoted public — LM1F's private status/memory helpers stay private and unchanged.
- **LM1F behavior-stable (full public `NodeOutcome` shape equivalent), not byte-identical source.** The function is intentionally refactored; the invariant is that `node_outcome_from_tool_result(raw)` returns the same public `NodeOutcome` shape as before. Full-shape parity test proves it for representative raws; existing LM1F tests stay green, unmodified.
- **Shared producer APPLICATION core, distinct ladders.** `_apply_admissible_producer(graph, node_id, evidence)` (project + apply) + `_producer_runnable_check` + `_producer_role_check` are shared. `apply_producer_step`: runnable → `evidence_missing` → role → apply (order preserved; **public behavior + guard precedence stable, not byte-identical source**). `apply_producer_result`: runnable → role → **capture** → apply.
- **`apply_producer_result` producer-restricted, no `evidence_missing`.** Reasons subset `{unknown_node, node_not_runnable, role_missing, role_invalid, role_not_producer}`. Malformed/receipt-less raw → **applied `blocked`** (from projection), node status becomes `blocked`.
- **Admissibility before capture.** Inadmissible node returns not-applied WITHOUT interpreting the raw (proven with an `ExplodingRaw` dict-subclass whose `.get()` raises).
- **Never calls `apply_tool_result`.** No `needs_escalation`. No reducer/walker/projection-logic/verifier-logic/template change.
- **Error payloads are real-contract `success: False`.** Errored script results (`created_with_errors`) are top-level `success: False` (server contract); usable results are `success: True`.

---

## File Structure

- **Modify:** `mcp_server/src/rook/learning/plan_graph_outcomes.py` — add `node_evidence_from_tool_result`; refactor `node_outcome_from_tool_result` to use it.
- **Modify:** `mcp_server/src/rook/learning/plan_graph_runner.py` — add `apply_producer_result` + shared core helpers; refactor `apply_producer_step` (behavior-identical); add `plan_graph_outcomes` import.
- **Modify:** `mcp_server/tests/test_plan_graph_outcomes.py` — capture-helper + full-shape parity tests.
- **Modify:** `mcp_server/tests/test_plan_graph_runner.py` — `apply_producer_result` tests, live 5-node proof, allowlist update.

---

### Task 1: Single-source capture helper + LM1F refactor

**Files:**
- Modify: `mcp_server/src/rook/learning/plan_graph_outcomes.py`
- Test: `mcp_server/tests/test_plan_graph_outcomes.py`

**Interfaces:**
- Produces: `node_evidence_from_tool_result(result: Any) -> NodeEvidence`. `node_outcome_from_tool_result` unchanged in behavior/signature.

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_plan_graph_outcomes.py` (add imports if absent: `from rook.learning.plan_graph import NodeEvidence, NodeOutcome` and `from rook.learning.plan_graph_outcomes import node_evidence_from_tool_result, node_outcome_from_tool_result`):

```python
def test_capture_evidence_from_realistic_raw():
    raw = {
        "success": False,  # real-contract: errored script result is success: False
        "data": {
            "script_receipt": {
                "artifact_status": "created_with_errors",
                "mutation": {"status": "created", "component_guid": "g1"},
                "repair_anchor": {"component_guid": "g1", "target_errors": ["e1"]},
            }
        },
    }
    ev = node_evidence_from_tool_result(raw)
    assert ev.tool_status == "failed"
    assert ev.receipt["artifact_status"] == "created_with_errors"
    assert ev.repair_anchor == {"component_guid": "g1", "target_errors": ["e1"]}


def test_capture_evidence_malformed_raw_no_receipt():
    assert node_evidence_from_tool_result("not a dict").receipt is None
    assert node_evidence_from_tool_result({"success": True}).receipt is None
    ev = node_evidence_from_tool_result({"success": False, "error": "boom"})
    assert ev.receipt is None
    assert ev.tool_status == "failed"
    assert ev.error == "boom"


def test_outcome_evidence_is_capture_helper_output():
    raw = {"success": True, "data": {"script_receipt": {
        "artifact_status": "usable",
        "mutation": {"status": "created", "component_guid": "g1"},
    }}}
    assert node_outcome_from_tool_result(raw).evidence == node_evidence_from_tool_result(raw)


def test_node_outcome_full_shape_parity():
    # Case A: usable / success:True
    raw_a = {"success": True, "data": {"script_receipt": {
        "artifact_status": "usable",
        "mutation": {"status": "created", "component_guid": "g1"},
    }}}
    expected_a = NodeOutcome(
        status="succeeded",
        evidence=NodeEvidence(
            tool_status="success",
            verified=None,
            receipt={"artifact_status": "usable", "mutation": {"status": "created", "component_guid": "g1"}},
            repair_anchor=None,
            message=None,
            error=None,
        ),
        memory_updates={"facts": {"component_guid": "g1"}, "node_summary": "artifact usable"},
        message=None,
        error=None,
    )
    assert node_outcome_from_tool_result(raw_a) == expected_a

    # Case B: created_with_errors / success:False (real contract)
    raw_b = {"success": False, "data": {"script_receipt": {
        "artifact_status": "created_with_errors",
        "mutation": {"status": "created", "component_guid": "g2"},
    }}}
    expected_b = NodeOutcome(
        status="needs_repair",
        evidence=NodeEvidence(
            tool_status="failed",
            verified=None,
            receipt={"artifact_status": "created_with_errors", "mutation": {"status": "created", "component_guid": "g2"}},
            repair_anchor=None,
            message=None,
            error=None,
        ),
        memory_updates={"facts": {"component_guid": "g2"}, "node_summary": "artifact needs repair"},
        message=None,
        error=None,
    )
    assert node_outcome_from_tool_result(raw_b) == expected_b

    # Case C: malformed / no script_receipt
    raw_c = {"success": False, "error": "boom"}
    expected_c = NodeOutcome(
        status="failed",
        evidence=NodeEvidence(
            tool_status="failed",
            verified=None,
            receipt=None,
            repair_anchor=None,
            message=None,
            error="boom",
        ),
        memory_updates={"facts": {}, "node_summary": "tool failed"},
        message=None,
        error="boom",
    )
    assert node_outcome_from_tool_result(raw_c) == expected_c
```

- [ ] **Step 2: Run to verify failure**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_outcomes.py -p no:cacheprovider -q`
Expected: FAIL — `ImportError: cannot import name 'node_evidence_from_tool_result'`.

- [ ] **Step 3: Add the helper + refactor LM1F**

In `mcp_server/src/rook/learning/plan_graph_outcomes.py`, replace `node_outcome_from_tool_result` (lines 109-127) with the helper + refactored outcome:

```python
def node_evidence_from_tool_result(result: Any) -> NodeEvidence:
    """Role-agnostic capture: a raw tool result -> ``NodeEvidence``.

    Extracts ``tool_status`` / ``verified`` / ``script_receipt`` / ``repair_anchor``
    / message / error. Holds NO status or role semantics -- the conservative status
    mapping (``node_outcome_from_tool_result``) and the role-aware projection
    (``plan_graph_projection.project_receipt_outcome``) layer on top of this
    evidence. The single owner of "raw tool result -> evidence."
    """
    view = normalize_tool_result(result)
    receipt = _extract_script_receipt(result)
    repair_anchor = _repair_anchor(receipt)
    return NodeEvidence(
        tool_status=view.status,
        verified=view.verified,
        receipt=deepcopy(receipt) if receipt is not None else None,
        repair_anchor=deepcopy(repair_anchor) if repair_anchor is not None else None,
        message=view.message or view.verification_note,
        error=view.error,
    )


def node_outcome_from_tool_result(result: Any) -> NodeOutcome:
    view = normalize_tool_result(result)
    receipt = _extract_script_receipt(result)
    repair_anchor = _repair_anchor(receipt)
    return NodeOutcome(
        status=_outcome_status(view, receipt),
        evidence=node_evidence_from_tool_result(result),
        memory_updates=_memory_updates(view, receipt, repair_anchor),
        message=view.message,
        error=view.error,
    )
```

(The evidence is now built solely by the shared helper; status/memory re-extract `receipt`/`repair_anchor` locally — pure, idempotent, byte-identical output.)

- [ ] **Step 4: Run to verify pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_outcomes.py -p no:cacheprovider -q`
Expected: PASS (existing LM1F tests unchanged + 4 new tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/learning/plan_graph_outcomes.py mcp_server/tests/test_plan_graph_outcomes.py
git commit -m "feat(lm3i): single-source node_evidence_from_tool_result; LM1F builds evidence via it"
```

---

### Task 2: apply_producer_result + shared producer application core

**Files:**
- Modify: `mcp_server/src/rook/learning/plan_graph_runner.py`
- Test: `mcp_server/tests/test_plan_graph_runner.py`

**Interfaces:**
- Consumes: `node_evidence_from_tool_result` (Task 1); existing `project_receipt_outcome`, `projection_role_for_node`, `OUTCOME_PROJECTION_ROLE_KEY`, `apply_outcome`, `runnable_nodes`, `ProducerStepResult`, `ProducerStepReason`, `_producer_not_applied`.
- Produces: `apply_producer_result(graph, node_id, raw_result) -> ProducerStepResult`; `apply_producer_step` behavior-identical.

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_plan_graph_runner.py` (reuses LM3G/LM3H helpers `_producer_verifier_graph`, `_ROLE_ABSENT`, `_created_with_errors_receipt`, `_usable_raw_result`; add `apply_producer_result` to the existing `from rook.learning.plan_graph_runner import ...` line):

```python
class _ExplodingRaw(dict):
    def get(self, *args, **kwargs):
        raise AssertionError("raw result was interpreted")


def _error_script_result(component_guid="g1"):
    # real-contract: an errored script result is top-level success: False
    return {"success": False, "data": {"script_receipt": _created_with_errors_receipt(component_guid)}}


def test_producer_result_error_payload_succeeds_seam():
    g = _producer_verifier_graph(evidence=None)
    r = apply_producer_result(g, "create", _error_script_result())
    assert r.applied and r.outcome_status == "succeeded"
    node = r.graph.nodes["create"]
    assert node.status == "succeeded"
    assert node.evidence.tool_status == "failed"   # raw said failed
    assert node.evidence.verified is False         # producer role: artifact exists, not clean
    assert r.graph.nodes["verify"].status == "ready"


def test_producer_result_usable_payload_verified_true():
    g = _producer_verifier_graph(evidence=None)
    r = apply_producer_result(g, "create", _usable_raw_result())
    assert r.applied and r.outcome_status == "succeeded"
    node = r.graph.nodes["create"]
    assert node.evidence.tool_status == "success"
    assert node.evidence.verified is True
    assert r.graph.nodes["verify"].status == "ready"


def test_producer_result_never_emits_evidence_missing():
    # A runnable producer node with node.evidence is None: apply_producer_step would
    # return "evidence_missing" here. apply_producer_result captures from the raw
    # instead -- it has no evidence_missing path.
    g = _producer_verifier_graph(evidence=None)
    assert g.nodes["create"].evidence is None
    r = apply_producer_result(g, "create", _usable_raw_result())
    assert r.reason != "evidence_missing"
    assert r.applied and r.outcome_status == "succeeded"


def test_producer_result_malformed_raw_applies_blocked():
    g = _producer_verifier_graph(evidence=None)
    r = apply_producer_result(g, "create", {"success": False, "error": "boom"})
    assert r.applied is True
    assert r.reason is None
    assert r.outcome_status == "blocked"
    assert r.graph is not g
    assert r.graph.nodes["create"].status == "blocked"
    assert r.graph.nodes["verify"].status == "pending"


def test_producer_result_unknown_node_no_capture():
    g = _producer_verifier_graph(evidence=None)
    r = apply_producer_result(g, "nope", _ExplodingRaw())
    assert not r.applied and r.reason == "unknown_node" and r.graph is g


def test_producer_result_not_runnable_no_capture():
    g = _producer_verifier_graph(create_status="pending", evidence=None)
    r = apply_producer_result(g, "create", _ExplodingRaw())
    assert not r.applied and r.reason == "node_not_runnable" and r.graph is g


def test_producer_result_role_missing_no_capture():
    g = _producer_verifier_graph(role=_ROLE_ABSENT, evidence=None)
    r = apply_producer_result(g, "create", _ExplodingRaw())
    assert not r.applied and r.reason == "role_missing" and r.graph is g


def test_producer_result_role_invalid_no_capture():
    g = _producer_verifier_graph(role="banana", evidence=None)
    r = apply_producer_result(g, "create", _ExplodingRaw())
    assert not r.applied and r.reason == "role_invalid" and r.graph is g


def test_producer_result_role_not_producer_no_capture():
    g = _producer_verifier_graph(role="artifact_verifier", evidence=None)
    r = apply_producer_result(g, "create", _ExplodingRaw())
    assert not r.applied and r.reason == "role_not_producer" and r.graph is g
```

Also update the import-allowlist assertion in `test_runner_imports_only_plan_graph_layer` to add `plan_graph_outcomes`:

```python
    assert rook_or_relative == {
        "rook.learning.plan_graph",
        "rook.learning.plan_graph_verifiers",
        "rook.learning.plan_graph_projection",
        "rook.learning.plan_graph_outcomes",
    }
```

Leave the negative assertions and the subprocess heavy-module probe unchanged.

- [ ] **Step 2: Run to verify failure**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_runner.py -p no:cacheprovider -q`
Expected: FAIL — `ImportError: cannot import name 'apply_producer_result'`.

- [ ] **Step 3: Add the import, shared core, and primitives**

In `mcp_server/src/rook/learning/plan_graph_runner.py`, add the capture import after the projection import:

```python
from rook.learning.plan_graph_outcomes import node_evidence_from_tool_result
```

Then **replace** the existing `apply_producer_step` function with the shared-core decomposition (the helpers + both primitives). `apply_producer_step`'s guard order is preserved exactly:

```python
def _producer_runnable_check(graph: PlanGraph, node_id: str) -> ProducerStepReason | None:
    if node_id not in graph.nodes:
        return "unknown_node"
    if node_id not in {node.id for node in runnable_nodes(graph)}:
        return "node_not_runnable"
    return None


def _producer_role_check(node) -> ProducerStepReason | None:
    present = OUTCOME_PROJECTION_ROLE_KEY in node.metadata
    role = projection_role_for_node(node)
    if not present:
        return "role_missing"
    if role is None:
        return "role_invalid"
    if role != "artifact_producer":
        return "role_not_producer"
    return None


def _apply_admissible_producer(
    graph: PlanGraph, node_id: str, evidence
) -> ProducerStepResult:
    """Project an ADMISSIBLE producer node's evidence and apply it."""
    outcome = project_receipt_outcome(evidence, "artifact_producer")
    new_graph = apply_outcome(graph, node_id, outcome)
    return ProducerStepResult(
        graph=new_graph,
        applied=True,
        node_id=node_id,
        outcome_status=outcome.status,
        reason=None,
    )


def apply_producer_step(graph: PlanGraph, node_id: str) -> ProducerStepResult:
    """Apply one producer node's outcome from its OWN captured evidence.

    Order: exists -> runnable -> evidence_missing -> role -> apply (unchanged).
    """
    reason = _producer_runnable_check(graph, node_id)
    if reason is not None:
        return _producer_not_applied(graph, node_id, reason)
    node = graph.nodes[node_id]
    if node.evidence is None:
        return _producer_not_applied(graph, node_id, "evidence_missing")
    reason = _producer_role_check(node)
    if reason is not None:
        return _producer_not_applied(graph, node_id, reason)
    return _apply_admissible_producer(graph, node_id, node.evidence)


def apply_producer_result(
    graph: PlanGraph, node_id: str, raw_result
) -> ProducerStepResult:
    """Apply one producer node's outcome from a raw tool-result dict.

    Live-SHAPED, not live: ``raw_result`` is a tool-result dict, not a live call.
    Order: exists -> runnable -> role -> CAPTURE -> apply. Admissibility precedes
    capture: an inadmissible node returns not-applied without interpreting the raw.
    No ``evidence_missing`` reason -- a malformed/receipt-less raw becomes an
    applied ``blocked`` outcome from the projection. Never calls
    ``apply_tool_result``.
    """
    reason = _producer_runnable_check(graph, node_id)
    if reason is not None:
        return _producer_not_applied(graph, node_id, reason)
    reason = _producer_role_check(graph.nodes[node_id])
    if reason is not None:
        return _producer_not_applied(graph, node_id, reason)
    evidence = node_evidence_from_tool_result(raw_result)
    return _apply_admissible_producer(graph, node_id, evidence)
```

(Keep the existing `ProducerStepReason`, `ProducerStepResult`, and `_producer_not_applied` definitions as they are — only `apply_producer_step` is replaced and the new helpers + `apply_producer_result` are added.)

- [ ] **Step 4: Run to verify pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_runner.py -p no:cacheprovider -q`
Expected: PASS (existing LM3E/LM3G/LM3H runner tests incl. the apply_producer_step guard-precedence test + the new apply_producer_result tests + updated allowlist).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/learning/plan_graph_runner.py mcp_server/tests/test_plan_graph_runner.py
git commit -m "feat(lm3i): apply_producer_result + shared producer application core (apply_producer_step behavior-stable)"
```

---

### Task 3: Live 5-node chain proof from raw payloads

**Files:**
- Test: `mcp_server/tests/test_plan_graph_runner.py`

**Interfaces:**
- Consumes: `apply_producer_result` (Task 2), `_error_script_result` (Task 2), `_usable_raw_result` (LM3G), `apply_verifier_step`, `select_and_bind`, `initialize_graph`, `graph_status`, `NodeOutcome`, `apply_outcome` (all already imported from LM3G/LM3H).

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_plan_graph_runner.py`:

```python
def test_create_verify_repair_verify_chain_live_from_raw_payloads():
    descriptor = {
        "domain": "grasshopper",
        "operation": "create_verify_repair_verify",
        "language": "csharp",
    }
    bound = select_and_bind(descriptor)
    graph = bound.binding.graph
    assert graph is not None

    graph = initialize_graph(graph)  # ONCE, before any step
    assert graph.nodes["create_script"].status == "ready"

    # 1. producer from a REAL-contract error payload (success: False)
    pr = apply_producer_result(graph, "create_script", _error_script_result())
    assert pr.applied and pr.outcome_status == "succeeded"
    graph = pr.graph
    # the seam: raw tool said failed; producer graph role says succeed
    assert graph.nodes["create_script"].evidence.tool_status == "failed"
    assert graph.nodes["create_script"].evidence.verified is False
    assert graph.nodes["verify_create"].status == "ready"

    # 2. verifier re-judges the captured receipt -> needs_repair
    vr = apply_verifier_step(graph, "verify_create", "create_script")
    assert vr.applied and vr.outcome_status == "needs_repair"
    graph = vr.graph
    assert graph.nodes["repair_same_component"].status == "ready"

    # 3. repair-as-producer from a usable raw payload
    rp = apply_producer_result(graph, "repair_same_component", _usable_raw_result())
    assert rp.applied and rp.outcome_status == "succeeded"
    graph = rp.graph
    assert graph.nodes["repair_same_component"].evidence.tool_status == "success"
    assert graph.nodes["repair_same_component"].evidence.verified is True
    assert graph.nodes["verify_repair"].status == "ready"

    # 4. second verifier -> succeeded
    vr2 = apply_verifier_step(graph, "verify_repair", "repair_same_component")
    assert vr2.applied and vr2.outcome_status == "succeeded"
    graph = vr2.graph
    assert graph.nodes["done"].status == "ready"

    # 5. finalize done explicitly
    assert graph.nodes["done"].status == "ready"
    graph = apply_outcome(
        graph, "done", NodeOutcome(status="succeeded", message="done: reverified clean")
    )
    assert graph.nodes["done"].status == "succeeded"
    assert graph_status(graph) == "complete"
```

- [ ] **Step 2: Run to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_runner.py::test_create_verify_repair_verify_chain_live_from_raw_payloads -p no:cacheprovider -q`
Expected: PASS.

- [ ] **Step 3: Run the full PlanGraph suite + py_compile**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider \
  mcp_server/tests/test_plan_graph.py \
  mcp_server/tests/test_plan_graph_outcomes.py \
  mcp_server/tests/test_plan_graph_bridge.py \
  mcp_server/tests/test_plan_graph_walker.py \
  mcp_server/tests/test_plan_graph_templates.py \
  mcp_server/tests/test_plan_graph_verifiers.py \
  mcp_server/tests/test_plan_graph_runner.py \
  mcp_server/tests/test_plan_graph_projection.py -q
```
Expected: PASS (all). Then: `mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/learning/plan_graph_outcomes.py mcp_server/src/rook/learning/plan_graph_runner.py` (silent).

- [ ] **Step 4: Commit**

```bash
git add mcp_server/tests/test_plan_graph_runner.py
git commit -m "test(lm3i): live 5-node chain driven from raw tool-result payloads (seam: failed->succeeded)"
```

---

## Self-Review

- **Spec coverage:** single-source capture helper + LM1F refactor + full-shape parity (Task 1); shared application core + `apply_producer_result` + byte-stable `apply_producer_step` + malformed-as-blocked + admissibility-before-capture (Task 2); live 5-node proof from raw payloads with the failed→succeeded seam (Task 3). All spec sections mapped.
- **Tightenings:** error payloads use `success: False` (Tasks 1-3); `ExplodingRaw` is a `dict` subclass whose `.get()` raises (Task 2 admission tests); full-shape parity via dataclass `==` (Task 1).
- **Placeholder scan:** none — every step carries full code or an exact command.
- **Type consistency:** `node_evidence_from_tool_result`, `apply_producer_result`, helper names, and the reasons subset match across tasks and the spec; the three parity expected-`NodeOutcome`s are traced against the actual LM1F/view logic.

## Execution Handoff

Three tasks (1 → 2 → 3; Task 2 needs Task 1's helper, Task 3 needs both). Recommended: subagent-driven-development — haiku implementer per task, sonnet task reviewer per task, opus final whole-branch review. Final reviewer EXTRA instructions:
(a) `node_evidence_from_tool_result` is role-agnostic (no status/role logic); `node_outcome_from_tool_result` is **behavior-stable — same public `NodeOutcome` shape, not byte-identical source** (full-shape parity test + existing LM1F tests green, unmodified); only the evidence helper is promoted public.
(b) shared producer APPLICATION core: `apply_producer_step` is **behavior-stable, not byte-identical** — same public behavior + guard precedence, exact order (runnable → `evidence_missing` → role → apply); its LM3G tests + guard-precedence test pass unchanged. `apply_producer_result` order is runnable → role → capture → apply, with NO `evidence_missing`; a test must explicitly prove `apply_producer_result` never emits `evidence_missing` (the shared `ProducerStepReason` Literal still includes it globally for `apply_producer_step` — do NOT split the Literal; shared result type is fine).
(c) admissibility precedes capture: the `ExplodingRaw` (dict subclass, `.get` raises) admission tests prove the raw is never interpreted on `unknown_node`/`node_not_runnable`/`role_missing`/`role_invalid`/`role_not_producer`; all five return the input graph object.
(d) malformed/receipt-less raw → applied `blocked` (`applied is True`, `reason is None`, `outcome_status == "blocked"`, `graph is not graph`, `node.status == "blocked"`), distinct from not-applied admission failures.
(e) the seam is proven: error payload (`success: False`, `created_with_errors`) yields node `succeeded` with `evidence.tool_status == "failed"` and `verified is False`; usable (`success: True`) yields `tool_status == "success"`, `verified is True`.
(f) `apply_producer_result` never calls `apply_tool_result`; runner imports exactly `{plan_graph, plan_graph_verifiers, plan_graph_projection, plan_graph_outcomes}`; subprocess probe loads no `tool_dispatcher`/`dspy`/`litellm`; no reducer/walker/projection-logic/verifier-logic/template change; no `needs_escalation`.
(g) live proof calls `initialize_graph` exactly once; producers via `apply_producer_result`, verifiers via `apply_verifier_step`, `done` via explicit `apply_outcome`; reaches `graph_status == "complete"`.
