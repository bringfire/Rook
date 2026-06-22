# LM3D Verifier-Outcome Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure `script_receipt_verifier_outcome(evidence)` adapter that converts an already-captured `NodeEvidence` into a verifier node's `NodeOutcome`, single-sourcing the `artifact_status → outcome` table with LM1F.

**Architecture:** A new import-light module `plan_graph_verifiers.py` reads `evidence.receipt`'s `artifact_status`, maps it through the shared `ARTIFACT_STATUS_TO_OUTCOME` table (promoted to public in `plan_graph_outcomes`), and emits `succeeded`/`needs_repair`/`blocked`. Malformed evidence and deep-copy failures return `blocked` with an explanatory error — never an exception, never `needs_escalation`, never walker/tool integration.

**Tech Stack:** Python 3.12, pytest. Stdlib `copy` only inside the module, plus `rook.learning.plan_graph` and `rook.learning.plan_graph_outcomes`.

## Global Constraints

- **Input is `NodeEvidence | None`; output is `NodeOutcome`.** Never a raw tool result, never `GraphMemory`.
- **Single-sourced mapping:** promote `plan_graph_outcomes._ARTIFACT_STATUS_TO_OUTCOME` → public `ARTIFACT_STATUS_TO_OUTCOME` (behavior-preserving; the private name is referenced only inside that module). Both LM1F and LM3D consume it. LM3D reuses ONLY the table, not LM1F private helpers.
- **Mapping:** `usable→succeeded`; `created_with_errors`/`written_with_errors→needs_repair`; `verification_pending`/`unknown→blocked`. Missing (no evidence / non-dict receipt / no `artifact_status`) → `blocked` (error: missing). Present-but-not-a-key → `blocked` (error: unrecognized). **Never `needs_escalation`.**
- **`verified`:** `succeeded→True`; `needs_repair→False`; `blocked→` the input's `verified` if `evidence is not None and evidence.verified is not None`, else `None`. Don't overstate verification.
- **Distinct diagnostics:** missing vs unrecognized vs known-not-usable (`pending`/`unknown`) carry distinct messages; `error` is set only for missing / unrecognized / copy-failure (known-not-usable sets a non-error message).
- **Deep-copy guard:** copying `receipt`/`repair_anchor` is wrapped; on failure → `blocked`, `error="verifier: evidence copy failed"`, never raise. **Watchpoint 1:** the copy-failure (and every error) evidence must be REFERENCE-FREE — `receipt=None`, `repair_anchor=None`, only simple strings/`None` — never embed the uncopyable object.
- **Memory facts only from well-formed receipts:** emit `facts` (`component_guid`/`repair_anchor`) only for the well-formed path (status mapped, copy succeeded). Missing/unrecognized/copy-failed emit NO `facts`. `node_summary` is always a minimal verifier-local string; LM1F's summary table is NOT promoted/duplicated.
- **Watchpoint 2:** the single-source parity test must iterate the public table AND pin the expected current key set, so a future new `artifact_status` fails loudly for deliberate review.
- **Import-light, enforced:** module imports only `rook.learning.plan_graph` + `rook.learning.plan_graph_outcomes` among rook modules (+ stdlib `copy`). AST allowlist + subprocess probe (no `tool_dispatcher`/`dspy`/`litellm`; no walker/bridge/templates/planner).
- **No model calls, no live tools, no `planner.py`, no walker integration.**
- Test commands run from repo root (`C:\UDEV\Rook`) with the repo venv: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider ...`.

## File Structure

- `mcp_server/src/rook/learning/plan_graph_verifiers.py` (new) — `script_receipt_verifier_outcome` + small private helpers.
- `mcp_server/src/rook/learning/plan_graph_outcomes.py` (modify) — rename the mapping constant to public; update its one internal use.
- `mcp_server/tests/test_plan_graph_verifiers.py` (new) — full behavior + parity + purity suite.

---

### Task 1: `script_receipt_verifier_outcome` + public mapping

**Files:**
- Create: `mcp_server/src/rook/learning/plan_graph_verifiers.py`
- Modify: `mcp_server/src/rook/learning/plan_graph_outcomes.py` (constant rename: dict def + one `.get` use)
- Create: `mcp_server/tests/test_plan_graph_verifiers.py`

**Interfaces:**
- Consumes (from `rook.learning.plan_graph`): `NodeEvidence` (fields `tool_status`, `verified`, `receipt: dict|None`, `repair_anchor: dict|None`, `message`, `error`), `NodeOutcome` (constructed with `status`, `evidence`, `memory_updates`, `message`, `error`; `__post_init__` rejects `pending`/`ready`/`running`).
- Consumes (from `rook.learning.plan_graph_outcomes`): `ARTIFACT_STATUS_TO_OUTCOME` (public dict, after rename).
- Produces: `script_receipt_verifier_outcome(evidence: NodeEvidence | None) -> NodeOutcome`.

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_plan_graph_verifiers.py`:

```python
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from rook.learning.plan_graph import NodeEvidence
from rook.learning.plan_graph_outcomes import ARTIFACT_STATUS_TO_OUTCOME
from rook.learning.plan_graph_verifiers import script_receipt_verifier_outcome


COMPONENT_GUID = "fbfd3ba5-5951-4064-8478-ee1d173150a9"


def _receipt(artifact_status: str) -> dict:
    return {
        "version": 1,
        "operation": "create",
        "language": "csharp",
        "artifact_status": artifact_status,
        "mutation": {"status": "created", "component_guid": COMPONENT_GUID},
        "verification": {"status": "failed", "target_error_count": 1},
        "repair_anchor": {
            "component_guid": COMPONENT_GUID,
            "pins_out": [{"name": "A", "type": "double"}],
        },
    }


def _evidence(artifact_status: str, *, verified=None, tool_status=None) -> NodeEvidence:
    receipt = _receipt(artifact_status)
    return NodeEvidence(
        tool_status=tool_status,
        verified=verified,
        receipt=receipt,
        repair_anchor=receipt["repair_anchor"],
        message=None,
        error=None,
    )


def test_usable_is_succeeded_with_verified_true():
    outcome = script_receipt_verifier_outcome(_evidence("usable"))

    assert outcome.status == "succeeded"
    assert outcome.evidence.verified is True
    assert outcome.evidence.receipt["artifact_status"] == "usable"
    assert outcome.error is None
    assert outcome.memory_updates["facts"]["component_guid"] == COMPONENT_GUID
    assert (
        outcome.memory_updates["facts"]["repair_anchor"]["component_guid"]
        == COMPONENT_GUID
    )


@pytest.mark.parametrize("status", ["created_with_errors", "written_with_errors"])
def test_errors_are_needs_repair_with_verified_false(status):
    outcome = script_receipt_verifier_outcome(_evidence(status))

    assert outcome.status == "needs_repair"
    assert outcome.evidence.verified is False
    assert outcome.error is None
    assert outcome.memory_updates["facts"]["component_guid"] == COMPONENT_GUID


@pytest.mark.parametrize("status", ["verification_pending", "unknown"])
def test_pending_unknown_are_blocked_without_error(status):
    outcome = script_receipt_verifier_outcome(_evidence(status))

    assert outcome.status == "blocked"
    assert outcome.error is None
    assert outcome.evidence.error is None
    assert outcome.evidence.verified is None
    assert "not usable" in outcome.evidence.message
    # well-formed receipt → facts still emitted
    assert outcome.memory_updates["facts"]["component_guid"] == COMPONENT_GUID


def test_none_evidence_is_blocked_missing():
    outcome = script_receipt_verifier_outcome(None)

    assert outcome.status == "blocked"
    assert "missing" in outcome.error
    assert outcome.evidence.receipt is None
    assert outcome.evidence.repair_anchor is None
    assert "facts" not in outcome.memory_updates


def test_missing_receipt_variants_are_blocked_missing():
    for ev in (
        NodeEvidence(receipt=None),
        NodeEvidence(receipt="not a dict"),
        NodeEvidence(receipt={"version": 1}),  # no artifact_status
    ):
        outcome = script_receipt_verifier_outcome(ev)
        assert outcome.status == "blocked"
        assert "missing" in outcome.error
        assert "facts" not in outcome.memory_updates


def test_unrecognized_artifact_status_is_blocked_unrecognized():
    outcome = script_receipt_verifier_outcome(_evidence("future_status"))

    assert outcome.status == "blocked"
    assert "unrecognized" in outcome.error
    assert "future_status" in outcome.error
    assert "missing" not in outcome.error  # distinct from the missing case
    assert "facts" not in outcome.memory_updates


def test_deepcopy_failure_is_blocked_with_reference_free_evidence():
    class _Uncopyable:
        def __deepcopy__(self, memo):
            raise RuntimeError("nope")

    receipt = {
        "artifact_status": "usable",
        "mutation": {"component_guid": COMPONENT_GUID},
        "repair_anchor": {"component_guid": COMPONENT_GUID},
        "blob": _Uncopyable(),
    }
    ev = NodeEvidence(receipt=receipt, repair_anchor=receipt["repair_anchor"])

    outcome = script_receipt_verifier_outcome(ev)

    assert outcome.status == "blocked"
    assert outcome.error == "verifier: evidence copy failed"
    # Watchpoint 1: error evidence references nothing uncopyable
    assert outcome.evidence.receipt is None
    assert outcome.evidence.repair_anchor is None
    assert "facts" not in outcome.memory_updates


def test_blocked_preserves_meaningful_verified_else_none():
    carried = script_receipt_verifier_outcome(
        _evidence("verification_pending", verified=True)
    )
    assert carried.evidence.verified is True

    absent = script_receipt_verifier_outcome(
        _evidence("verification_pending", verified=None)
    )
    assert absent.evidence.verified is None


def test_outcome_is_isolated_from_input_mutation():
    ev = _evidence("created_with_errors")

    outcome = script_receipt_verifier_outcome(ev)

    ev.receipt["artifact_status"] = "mutated"
    ev.receipt["repair_anchor"]["component_guid"] = "mutated"

    assert outcome.evidence.receipt["artifact_status"] == "created_with_errors"
    assert outcome.evidence.repair_anchor["component_guid"] == COMPONENT_GUID
    assert (
        outcome.memory_updates["facts"]["repair_anchor"]["component_guid"]
        == COMPONENT_GUID
    )


def test_parity_with_shared_artifact_status_table():
    for status, expected in ARTIFACT_STATUS_TO_OUTCOME.items():
        outcome = script_receipt_verifier_outcome(_evidence(status))
        assert outcome.status == expected, status


def test_artifact_status_table_keys_are_pinned():
    # Watchpoint 2: adding/removing an artifact_status must trigger a deliberate
    # review of verifier semantics (escalation must NOT silently enter the table).
    assert set(ARTIFACT_STATUS_TO_OUTCOME) == {
        "usable",
        "created_with_errors",
        "written_with_errors",
        "verification_pending",
        "unknown",
    }


def _direct_import_modules(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            modules.add(f"{prefix}{node.module or ''}")
    return modules


def test_verifiers_module_imports_only_plan_graph_layer():
    imports = _direct_import_modules(
        "mcp_server/src/rook/learning/plan_graph_verifiers.py"
    )
    rook_or_relative = {
        m for m in imports if m.startswith("rook.") or m.startswith(".")
    }
    assert rook_or_relative == {
        "rook.learning.plan_graph",
        "rook.learning.plan_graph_outcomes",
    }
    assert "rook.agent.tool_dispatcher" not in imports
    assert "rook.learning.plan_graph_walker" not in imports
    assert "rook.learning.plan_graph_bridge" not in imports
    assert "rook.learning.plan_graph_templates" not in imports
    assert "rook.agent.planner" not in imports


def test_importing_verifiers_does_not_load_heavy_modules():
    env = os.environ.copy()
    src_path = str(Path("mcp_server/src").resolve())
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )

    probe = (
        "import sys\n"
        "import rook.learning.plan_graph_verifiers\n"
        "for mod in ('rook.agent.tool_dispatcher', 'dspy', 'litellm'):\n"
        "    if mod in sys.modules:\n"
        "        raise SystemExit(mod + ' loaded')\n"
    )

    subprocess.run([sys.executable, "-c", probe], check=True, env=env)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_verifiers.py -v`
Expected: collection/import error — `ImportError: cannot import name 'script_receipt_verifier_outcome'` (and `ARTIFACT_STATUS_TO_OUTCOME` does not exist publicly yet). Neither the module nor the public constant exists.

- [ ] **Step 3a: Promote the mapping constant to public in `plan_graph_outcomes.py`**

Two edits, both behavior-preserving:

Replace the dict definition line:
```python
_ARTIFACT_STATUS_TO_OUTCOME = {
```
with:
```python
ARTIFACT_STATUS_TO_OUTCOME = {
```

Replace the single use inside `_outcome_status`:
```python
    mapped = _ARTIFACT_STATUS_TO_OUTCOME.get(artifact_status)
```
with:
```python
    mapped = ARTIFACT_STATUS_TO_OUTCOME.get(artifact_status)
```

(The private name appears nowhere else in code — verified by repo-wide search. `_ARTIFACT_STATUS_TO_SUMMARY` and the other private constants are left unchanged.)

- [ ] **Step 3b: Create the verifier module**

Create `mcp_server/src/rook/learning/plan_graph_verifiers.py`:

```python
"""LM3D verifier-outcome adapter.

Pure adapter that converts an already-captured ``NodeEvidence`` (its
``script_receipt``) into a *verifier node's* ``NodeOutcome``. Distinct from LM1F
(``plan_graph_outcomes.node_outcome_from_tool_result``), which consumes a *raw
tool result* and produces the *executing* node's outcome. Both share one truth
table -- ``ARTIFACT_STATUS_TO_OUTCOME`` -- so a receipt's artifact_status can
never mean different things to the two adapters.

It never calls tools, inspects live state, schedules, or emits
``needs_escalation`` (escalation needs retry/attempt policy, not receipt status).
Malformed evidence and deep-copy failures return a ``blocked`` outcome with an
explanatory error, never an exception.
"""

import copy

from rook.learning.plan_graph import NodeEvidence, NodeOutcome
from rook.learning.plan_graph_outcomes import ARTIFACT_STATUS_TO_OUTCOME


_KNOWN_ARTIFACT_STATUSES = frozenset(ARTIFACT_STATUS_TO_OUTCOME)


def _component_guid(receipt: dict, repair_anchor: dict | None) -> str | None:
    mutation = receipt.get("mutation")
    if isinstance(mutation, dict):
        guid = mutation.get("component_guid")
        if isinstance(guid, str) and guid:
            return guid
    if isinstance(repair_anchor, dict):
        guid = repair_anchor.get("component_guid")
        if isinstance(guid, str) and guid:
            return guid
    return None


def _blocked_outcome(message: str, verified: bool | None, tool_status) -> NodeOutcome:
    """Blocked outcome with REFERENCE-FREE evidence (no receipt/anchor objects)."""
    return NodeOutcome(
        status="blocked",
        evidence=NodeEvidence(
            tool_status=tool_status,
            verified=verified,
            receipt=None,
            repair_anchor=None,
            message=message,
            error=message,
        ),
        memory_updates={"node_summary": "verifier: blocked"},
        message=message,
        error=message,
    )


def script_receipt_verifier_outcome(evidence: NodeEvidence | None) -> NodeOutcome:
    """Convert an already-captured ``NodeEvidence`` into a verifier ``NodeOutcome``.

    Reads ``evidence.receipt``'s ``artifact_status`` and maps it through the shared
    ``ARTIFACT_STATUS_TO_OUTCOME`` table. Malformed evidence, an unrecognized
    status, or a deep-copy failure return ``blocked`` with an explanatory error
    and reference-free evidence. Never raises; never emits ``needs_escalation``.
    """
    tool_status = evidence.tool_status if evidence is not None else None
    carried_verified = evidence.verified if evidence is not None else None

    receipt = evidence.receipt if evidence is not None else None
    if not isinstance(receipt, dict) or "artifact_status" not in receipt:
        return _blocked_outcome(
            "verifier: missing receipt or artifact_status",
            carried_verified,
            tool_status,
        )

    artifact_status = receipt.get("artifact_status")
    if artifact_status not in _KNOWN_ARTIFACT_STATUSES:
        return _blocked_outcome(
            f"verifier: unrecognized artifact_status '{artifact_status}'",
            carried_verified,
            tool_status,
        )

    status = ARTIFACT_STATUS_TO_OUTCOME[artifact_status]

    try:
        receipt_copy = copy.deepcopy(receipt)
        repair_anchor_copy = (
            copy.deepcopy(evidence.repair_anchor)
            if evidence.repair_anchor is not None
            else None
        )
    except Exception:
        return _blocked_outcome(
            "verifier: evidence copy failed",
            carried_verified,
            tool_status,
        )

    if status == "succeeded":
        verified: bool | None = True
        message = "verifier: artifact usable"
    elif status == "needs_repair":
        verified = False
        message = "verifier: artifact needs repair"
    else:  # blocked: verification_pending / unknown
        verified = carried_verified
        message = f"verifier: artifact_status '{artifact_status}' is not usable"

    facts: dict = {}
    guid = _component_guid(receipt_copy, repair_anchor_copy)
    if guid is not None:
        facts["component_guid"] = guid
    if isinstance(repair_anchor_copy, dict):
        facts["repair_anchor"] = repair_anchor_copy

    memory_updates: dict = {"node_summary": f"verifier: {status}"}
    if facts:
        memory_updates["facts"] = facts

    return NodeOutcome(
        status=status,
        evidence=NodeEvidence(
            tool_status=tool_status,
            verified=verified,
            receipt=receipt_copy,
            repair_anchor=repair_anchor_copy,
            message=message,
            error=None,
        ),
        memory_updates=memory_updates,
        message=message,
        error=None,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_verifiers.py -v`
Expected: all PASS (13 test functions; the two `parametrize`d tests contribute 2 cases each).

- [ ] **Step 5: Regression — PlanGraph suites + py_compile**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_verifiers.py mcp_server/tests/test_plan_graph_outcomes.py mcp_server/tests/test_plan_graph.py mcp_server/tests/test_plan_graph_bridge.py mcp_server/tests/test_plan_graph_walker.py mcp_server/tests/test_plan_graph_templates.py -v
mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/learning/plan_graph_verifiers.py mcp_server/src/rook/learning/plan_graph_outcomes.py
```
Expected: all PASS; py_compile silent. `test_plan_graph_outcomes.py` must stay green — the constant rename is internal and behavior-preserving (this is the LM1F regression gate).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/learning/plan_graph_verifiers.py mcp_server/src/rook/learning/plan_graph_outcomes.py mcp_server/tests/test_plan_graph_verifiers.py
git commit -m "feat(lm3d): verifier-outcome adapter (NodeEvidence -> verifier NodeOutcome)"
```

---

## Post-implementation (controller, not a task)

After Task 1 + the final whole-branch review:
- Open a PR `codex/lm3d-verifier-outcome-adapter` → `main`. **Stop before merge — explicit human approval required (no self-merge).**
- Final reviewer EXTRA instructions:
  - (a) LM3D consumes `NodeEvidence` (not raw results / not memory); output is a verifier `NodeOutcome`. No walker/tool/model/planner integration.
  - (b) Single-sourced: `ARTIFACT_STATUS_TO_OUTCOME` is public and used by both LM1F and LM3D; only the table is shared (no LM1F private helpers imported). Parity test iterates the table; key-set is pinned (loud failure on table growth).
  - (c) Mapping correct; `verified` not overstated (`True`/`False`/preserved-or-`None`); never `needs_escalation`.
  - (d) **Watchpoint 1:** copy-failure (and every error) outcome's evidence is reference-free — `receipt=None`, `repair_anchor=None`, only simple strings/`None`; never embeds the uncopyable object; never raises.
  - (e) Distinct missing vs unrecognized vs known-not-usable diagnostics; `error` only on missing/unrecognized/copy-failure; `facts` only from well-formed receipts.
  - (f) Deep-copy isolation: mutating input evidence after the call doesn't change the outcome.
  - (g) Import boundary — module imports only `rook.learning.plan_graph` + `rook.learning.plan_graph_outcomes` among rook modules; AST + subprocess probes pass. LM1F regression (`test_plan_graph_outcomes.py`) green after the rename.
- No deployed-runtime verification needed (pure learning-layer module; no wire/surface/runtime impact).
