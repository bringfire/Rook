# LM3F Role-Aware Outcome Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `project_receipt_outcome(evidence, role)` — a pure function that projects already-captured `NodeEvidence` into a role-aware `NodeOutcome` — and make LM3D's `script_receipt_verifier_outcome` a thin compatibility wrapper that delegates with `role="artifact_verifier"`.

**Architecture:** A new pure module `plan_graph_projection.py` owns the role table (`direct_task` / `artifact_verifier` share the conservative `ARTIFACT_STATUS_TO_OUTCOME` mapping; `artifact_producer` promotes artifact-existence to `succeeded` behind a mutation-evidence gate, decoupling `status` from `verified`). `plan_graph_verifiers.py` delegates to it (one-way import). No `PlanGraph`, walker, LM1F, or LM3E change.

**Tech Stack:** Python 3.12, stdlib `copy` + `typing.Literal`, pytest. Test runner: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider`.

## Global Constraints

- **Pure / non-live / import-light.** No model calls, no live tools, no scheduling, no `planner.py`. `plan_graph_projection` imports only `rook.learning.plan_graph` and `rook.learning.plan_graph_outcomes` among rook modules, plus stdlib `copy` and `typing`.
- **One-way imports.** `plan_graph_verifiers → plan_graph_projection → {plan_graph, plan_graph_outcomes}`. Projection must NEVER import verifiers.
- **LM1F untouched.** Do not modify `plan_graph_outcomes.py` (it is consumed read-only for `ARTIFACT_STATUS_TO_OUTCOME`).
- **LM3D behavior is a hard regression contract.** The existing behavior assertions in `test_plan_graph_verifiers.py` stay unchanged and green. Only the purity allowlist test is updated (to permit `plan_graph_projection`).
- **`NodeOutcome.status`** is always one of `succeeded` / `needs_repair` / `blocked`. Never `needs_escalation`.
- **Invalid role raises `ValueError`** (API misuse), before any evidence inspection. Evidence failures (malformed / unrecognized status / deep-copy failure) return `blocked`, never raise.
- **Facts are emitted when derivable, not guaranteed.** Conservative roles preserve LM3D facts behavior. Producer emits facts only on confirmed success and only when a `component_guid` / `repair_anchor` is derivable.
- **`_has_mutation_evidence` (the gate) and the facts predicate are different.** The gate requires a NON-EMPTY repair anchor; the facts helper emits `repair_anchor` whenever `isinstance(repair_anchor, dict)` (matching LM3D exactly, including empty `{}`). Do not conflate them.

---

## File Structure

- **New:** `mcp_server/src/rook/learning/plan_graph_projection.py` — `OutcomeProjectionRole`, `project_receipt_outcome`, `_has_mutation_evidence`, and small private outcome-construction helpers.
- **Modify:** `mcp_server/src/rook/learning/plan_graph_verifiers.py` — `script_receipt_verifier_outcome` becomes a one-line delegation; remove the now-dead private helpers; fix imports.
- **Modify:** `mcp_server/tests/test_plan_graph_verifiers.py` — update ONLY the AST purity allowlist (new set `{plan_graph, plan_graph_projection}`); leave every behavior assertion untouched.
- **New:** `mcp_server/tests/test_plan_graph_projection.py` — LM3F tests.

This is a single cohesive deliverable (the parity claim requires both the new helper and the delegating wrapper to exist together), so it is one task.

---

### Task 1: Role-aware projection module + LM3D delegation

**Files:**
- Create: `mcp_server/src/rook/learning/plan_graph_projection.py`
- Modify: `mcp_server/src/rook/learning/plan_graph_verifiers.py`
- Modify: `mcp_server/tests/test_plan_graph_verifiers.py` (purity allowlist only)
- Test: `mcp_server/tests/test_plan_graph_projection.py`

**Interfaces:**
- Consumes: `NodeEvidence`, `NodeOutcome` from `rook.learning.plan_graph`; `ARTIFACT_STATUS_TO_OUTCOME` from `rook.learning.plan_graph_outcomes`.
- Produces: `OutcomeProjectionRole = Literal["direct_task", "artifact_producer", "artifact_verifier"]` and `project_receipt_outcome(evidence: NodeEvidence | None, role: OutcomeProjectionRole) -> NodeOutcome`. `plan_graph_verifiers.script_receipt_verifier_outcome(evidence)` continues to exist with the same signature, now delegating to `project_receipt_outcome(evidence, "artifact_verifier")`.

---

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_plan_graph_projection.py`:

```python
import ast
import copy
import subprocess
import sys
from pathlib import Path

import pytest

from rook.learning.plan_graph import NodeEvidence, NodeOutcome
from rook.learning.plan_graph_outcomes import ARTIFACT_STATUS_TO_OUTCOME
from rook.learning.plan_graph_projection import (
    OutcomeProjectionRole,
    project_receipt_outcome,
)
from rook.learning.plan_graph_verifiers import script_receipt_verifier_outcome


def _receipt(artifact_status, *, mutation=None, repair_anchor=None):
    receipt = {"artifact_status": artifact_status}
    if mutation is not None:
        receipt["mutation"] = mutation
    if repair_anchor is not None:
        receipt["repair_anchor"] = repair_anchor
    return receipt


def _evidence(receipt, *, tool_status="success", verified=None, repair_anchor=None):
    return NodeEvidence(
        tool_status=tool_status,
        verified=verified,
        receipt=receipt,
        repair_anchor=repair_anchor,
    )


# --- Parity: artifact_verifier == LM3D wrapper, FULL public shape ---------

@pytest.mark.parametrize(
    "evidence",
    [
        _evidence(_receipt("usable", mutation={"status": "created", "component_guid": "g1"})),
        _evidence(_receipt("created_with_errors", mutation={"status": "created", "component_guid": "g2"},
                           repair_anchor={"component_guid": "g2", "target_errors": []}),
                  repair_anchor={"component_guid": "g2", "target_errors": []}),
        _evidence(_receipt("verification_pending", mutation={"status": "created"})),
        _evidence(None),                                  # missing receipt
        _evidence(_receipt("future_status")),             # unrecognized
    ],
)
def test_artifact_verifier_parity_full_shape(evidence):
    # dataclass __eq__ recurses into evidence -> full public-shape comparison
    assert project_receipt_outcome(evidence, "artifact_verifier") == \
        script_receipt_verifier_outcome(evidence)


def test_artifact_verifier_parity_deepcopy_failure():
    class Boom:
        def __deepcopy__(self, memo):
            raise RuntimeError("nope")

    receipt = {"artifact_status": "usable", "mutation": {"status": "created"}, "boom": Boom()}
    evidence = _evidence(receipt)
    assert project_receipt_outcome(evidence, "artifact_verifier") == \
        script_receipt_verifier_outcome(evidence)


# --- Producer success: facts WHEN DERIVABLE -----------------------------

def test_producer_created_with_errors_with_guid_succeeds_with_facts():
    anchor = {"component_guid": "g9", "target_errors": ["e1"]}
    evidence = _evidence(
        _receipt("created_with_errors", mutation={"status": "created", "component_guid": "g9"},
                 repair_anchor=anchor),
        repair_anchor=anchor,
    )
    outcome = project_receipt_outcome(evidence, "artifact_producer")
    assert outcome.status == "succeeded"
    assert outcome.evidence.verified is False
    assert outcome.memory_updates["facts"]["component_guid"] == "g9"
    assert outcome.memory_updates["facts"]["repair_anchor"] == anchor


def test_producer_written_with_errors_with_guid_succeeds_verified_false():
    evidence = _evidence(_receipt("written_with_errors", mutation={"status": "written", "component_guid": "g8"}))
    outcome = project_receipt_outcome(evidence, "artifact_producer")
    assert outcome.status == "succeeded"
    assert outcome.evidence.verified is False
    assert outcome.memory_updates["facts"]["component_guid"] == "g8"


def test_producer_verification_pending_with_evidence_succeeds_verified_none():
    evidence = _evidence(_receipt("verification_pending", mutation={"status": "created", "component_guid": "g7"}))
    outcome = project_receipt_outcome(evidence, "artifact_producer")
    assert outcome.status == "succeeded"
    assert outcome.evidence.verified is None
    assert outcome.memory_updates["facts"]["component_guid"] == "g7"


def test_producer_mutation_status_only_succeeds_with_no_facts():
    # mutation.status alone is evidence, but yields nothing derivable to emit
    evidence = _evidence(_receipt("created_with_errors", mutation={"status": "created"}))
    outcome = project_receipt_outcome(evidence, "artifact_producer")
    assert outcome.status == "succeeded"
    assert outcome.evidence.verified is False
    assert "facts" not in outcome.memory_updates


# --- Producer gate failure: blocked-unconfirmed, receipt preserved ------

def test_producer_no_mutation_evidence_blocked_unconfirmed_receipt_preserved():
    # mutation.status not in the success set, no guid, empty {} anchor (NOT evidence)
    receipt = _receipt("created_with_errors", mutation={"status": "skipped"}, repair_anchor={})
    evidence = _evidence(receipt, repair_anchor={})
    outcome = project_receipt_outcome(evidence, "artifact_producer")
    assert outcome.status == "blocked"
    assert outcome.error == "producer: artifact existence unconfirmed"
    assert outcome.evidence.receipt is not None          # receipt PRESERVED
    assert outcome.evidence.receipt["artifact_status"] == "created_with_errors"
    assert "facts" not in outcome.memory_updates


def test_producer_empty_anchor_alone_is_not_evidence():
    receipt = _receipt("written_with_errors", repair_anchor={})
    evidence = _evidence(receipt, repair_anchor={})
    outcome = project_receipt_outcome(evidence, "artifact_producer")
    assert outcome.status == "blocked"
    assert outcome.error == "producer: artifact existence unconfirmed"


# --- Producer ungated rows ----------------------------------------------

def test_producer_usable_succeeds_verified_true():
    evidence = _evidence(_receipt("usable", mutation={"status": "created", "component_guid": "g1"}))
    outcome = project_receipt_outcome(evidence, "artifact_producer")
    assert outcome.status == "succeeded"
    assert outcome.evidence.verified is True


def test_producer_unknown_blocked_no_facts():
    evidence = _evidence(_receipt("unknown", mutation={"status": "created", "component_guid": "g1"}))
    outcome = project_receipt_outcome(evidence, "artifact_producer")
    assert outcome.status == "blocked"
    assert outcome.error is None                         # non-error blocked
    assert "facts" not in outcome.memory_updates         # producer: facts only on success


# --- direct_task: conservative mapping, "task:" messages ----------------

def test_direct_task_created_with_errors_needs_repair():
    evidence = _evidence(_receipt("created_with_errors", mutation={"status": "created", "component_guid": "g1"}))
    outcome = project_receipt_outcome(evidence, "direct_task")
    assert outcome.status == "needs_repair"
    assert outcome.evidence.verified is False
    assert outcome.message == "task: artifact needs repair"


def test_direct_task_usable_succeeds():
    evidence = _evidence(_receipt("usable", mutation={"status": "created", "component_guid": "g1"}))
    outcome = project_receipt_outcome(evidence, "direct_task")
    assert outcome.status == "succeeded"
    assert outcome.message == "task: artifact usable"


def test_direct_task_verification_pending_blocked():
    evidence = _evidence(_receipt("verification_pending", mutation={"status": "created"}))
    outcome = project_receipt_outcome(evidence, "direct_task")
    assert outcome.status == "blocked"
    assert outcome.message == "task: artifact_status 'verification_pending' is not usable"


# --- Invalid role raises (API misuse), before evidence inspection -------

def test_invalid_role_raises_value_error():
    evidence = _evidence(_receipt("usable", mutation={"status": "created"}))
    with pytest.raises(ValueError):
        project_receipt_outcome(evidence, "banana")  # type: ignore[arg-type]


def test_invalid_role_raises_even_with_none_evidence():
    with pytest.raises(ValueError):
        project_receipt_outcome(None, "banana")  # type: ignore[arg-type]


# --- Deep-copy isolation ------------------------------------------------

def test_producer_success_isolated_from_input_mutation():
    anchor = {"component_guid": "g9", "target_errors": ["e1"]}
    receipt = _receipt("created_with_errors", mutation={"status": "created", "component_guid": "g9"},
                       repair_anchor=anchor)
    evidence = _evidence(receipt, repair_anchor=anchor)
    outcome = project_receipt_outcome(evidence, "artifact_producer")
    receipt["artifact_status"] = "MUTATED"
    anchor["target_errors"].append("e2")
    assert outcome.evidence.receipt["artifact_status"] == "created_with_errors"
    assert outcome.memory_updates["facts"]["repair_anchor"]["target_errors"] == ["e1"]


def test_producer_unconfirmed_isolated_from_input_mutation():
    receipt = _receipt("created_with_errors", mutation={"status": "skipped"})
    evidence = _evidence(receipt)
    outcome = project_receipt_outcome(evidence, "artifact_producer")
    receipt["artifact_status"] = "MUTATED"
    receipt["mutation"]["status"] = "created"
    assert outcome.status == "blocked"
    assert outcome.evidence.receipt["artifact_status"] == "created_with_errors"
    assert outcome.evidence.receipt["mutation"]["status"] == "skipped"


# --- Single-source / closed-Literal guards ------------------------------

@pytest.mark.parametrize("artifact_status,expected", list(ARTIFACT_STATUS_TO_OUTCOME.items()))
def test_conservative_roles_ride_shared_table(artifact_status, expected):
    evidence = _evidence(_receipt(artifact_status, mutation={"status": "created", "component_guid": "g1"}))
    assert project_receipt_outcome(evidence, "artifact_verifier").status == expected
    assert project_receipt_outcome(evidence, "direct_task").status == expected


def test_role_literal_has_exactly_three_members():
    from typing import get_args
    assert set(get_args(OutcomeProjectionRole)) == {
        "direct_task", "artifact_producer", "artifact_verifier",
    }


# --- Purity: import allowlist + subprocess probe ------------------------

def test_projection_import_allowlist():
    src = Path(__file__).resolve().parents[1] / "src" / "rook" / "learning" / "plan_graph_projection.py"
    tree = ast.parse(src.read_text())
    rook_imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("rook"):
            rook_imports.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("rook"):
                    rook_imports.add(alias.name)
    assert rook_imports <= {"rook.learning.plan_graph", "rook.learning.plan_graph_outcomes"}


def test_projection_loads_no_live_deps():
    code = (
        "import sys; import rook.learning.plan_graph_projection; "
        "assert 'dspy' not in sys.modules; assert 'litellm' not in sys.modules; "
        "assert 'rook.agent.tool_dispatcher' not in sys.modules"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_projection.py -p no:cacheprovider -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'rook.learning.plan_graph_projection'` (collection error).

- [ ] **Step 3: Create the projection module**

Create `mcp_server/src/rook/learning/plan_graph_projection.py`:

```python
"""LM3F role-aware outcome projection.

Pure function that converts an already-captured ``NodeEvidence`` (its
``script_receipt``) into a ``NodeOutcome`` whose meaning depends on the node's
ROLE. The same receipt projects to different graph outcomes by role:

- ``artifact_producer`` treats artifact EXISTENCE as success
  (``created_with_errors`` -> ``succeeded`` when mutation evidence is present),
  decoupling ``status`` (existence / task progress) from ``verified`` (functional
  success). This is the projection that makes a producer node unlock a downstream
  verifier via the reducer's ``requires`` edge.
- ``artifact_verifier`` and ``direct_task`` treat the same receipt conservatively
  (``created_with_errors`` -> ``needs_repair``), riding the shared
  ``ARTIFACT_STATUS_TO_OUTCOME`` table.

Role-awareness is the layer ABOVE LM1F, not a correction to it. LM1F is unchanged.
``plan_graph_verifiers.script_receipt_verifier_outcome`` is a compatibility
wrapper delegating here with ``role="artifact_verifier"``; that role reproduces
LM3D verbatim (hard regression contract).

Never calls tools, inspects live state, schedules, or emits ``needs_escalation``.
Malformed evidence and deep-copy failures return a ``blocked`` outcome with an
explanatory error -- never an exception. An invalid ROLE, however, raises
``ValueError``: that is API misuse, not bad data.
"""

import copy
from typing import Literal

from rook.learning.plan_graph import NodeEvidence, NodeOutcome
from rook.learning.plan_graph_outcomes import ARTIFACT_STATUS_TO_OUTCOME


OutcomeProjectionRole = Literal["direct_task", "artifact_producer", "artifact_verifier"]

_VALID_ROLES = frozenset(("direct_task", "artifact_producer", "artifact_verifier"))
_KNOWN_ARTIFACT_STATUSES = frozenset(ARTIFACT_STATUS_TO_OUTCOME)
_ROLE_PREFIX = {
    "direct_task": "task",
    "artifact_producer": "producer",
    "artifact_verifier": "verifier",
}
_PROMOTED_STATUSES = frozenset(
    ("created_with_errors", "written_with_errors", "verification_pending")
)
_MUTATION_DONE = frozenset(("created", "written", "updated"))


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


def _has_mutation_evidence(receipt: dict, repair_anchor: dict | None) -> bool:
    """Producer GATE predicate. NOTE: requires a NON-EMPTY repair anchor."""
    mutation = receipt.get("mutation")
    if isinstance(mutation, dict) and mutation.get("status") in _MUTATION_DONE:
        return True
    if _component_guid(receipt, repair_anchor) is not None:
        return True
    if isinstance(repair_anchor, dict) and repair_anchor:
        return True
    return False


def _facts(receipt: dict, repair_anchor: dict | None) -> dict:
    """Facts helper (LM3D-equivalent): emit repair_anchor whenever it is a dict."""
    facts: dict = {}
    guid = _component_guid(receipt, repair_anchor)
    if guid is not None:
        facts["component_guid"] = guid
    if isinstance(repair_anchor, dict):
        facts["repair_anchor"] = repair_anchor
    return facts


def _reference_free_blocked(message, verified, tool_status, prefix) -> NodeOutcome:
    """Blocked with NO receipt/anchor references (missing/unrecognized/copy-fail)."""
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
        memory_updates={"node_summary": f"{prefix}: blocked"},
        message=message,
        error=message,
    )


def _conservative_outcome(
    artifact_status, receipt_copy, repair_anchor_copy, carried_verified, tool_status, prefix
) -> NodeOutcome:
    status = ARTIFACT_STATUS_TO_OUTCOME[artifact_status]
    if status == "succeeded":
        verified: bool | None = True
        message = f"{prefix}: artifact usable"
    elif status == "needs_repair":
        verified = False
        message = f"{prefix}: artifact needs repair"
    else:  # blocked: verification_pending / unknown
        verified = carried_verified
        message = f"{prefix}: artifact_status '{artifact_status}' is not usable"

    facts = _facts(receipt_copy, repair_anchor_copy)
    memory_updates: dict = {"node_summary": f"{prefix}: {status}"}
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


def _producer_success(receipt_copy, repair_anchor_copy, verified, message, tool_status) -> NodeOutcome:
    facts = _facts(receipt_copy, repair_anchor_copy)
    memory_updates: dict = {"node_summary": "producer: succeeded"}
    if facts:
        memory_updates["facts"] = facts
    return NodeOutcome(
        status="succeeded",
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


def _producer_blocked(message, receipt_copy, repair_anchor_copy, verified, tool_status, error) -> NodeOutcome:
    """Producer blocked with the cleanly-copied receipt PRESERVED, no facts."""
    return NodeOutcome(
        status="blocked",
        evidence=NodeEvidence(
            tool_status=tool_status,
            verified=verified,
            receipt=receipt_copy,
            repair_anchor=repair_anchor_copy,
            message=message,
            error=error,
        ),
        memory_updates={"node_summary": "producer: blocked"},
        message=message,
        error=error,
    )


def _producer_outcome(
    artifact_status, receipt_copy, repair_anchor_copy, carried_verified, tool_status
) -> NodeOutcome:
    if artifact_status == "usable":
        return _producer_success(
            receipt_copy, repair_anchor_copy, True, "producer: artifact usable", tool_status
        )
    if artifact_status == "unknown":
        return _producer_blocked(
            "producer: artifact_status 'unknown' is not usable",
            receipt_copy, repair_anchor_copy, carried_verified, tool_status, error=None,
        )
    # promoted rows: created_with_errors / written_with_errors / verification_pending
    if _has_mutation_evidence(receipt_copy, repair_anchor_copy):
        if artifact_status == "created_with_errors":
            return _producer_success(
                receipt_copy, repair_anchor_copy, False,
                "producer: artifact created with repairable errors", tool_status,
            )
        if artifact_status == "written_with_errors":
            return _producer_success(
                receipt_copy, repair_anchor_copy, False,
                "producer: artifact written with repairable errors", tool_status,
            )
        # verification_pending
        return _producer_success(
            receipt_copy, repair_anchor_copy, None,
            "producer: artifact produced, verification pending", tool_status,
        )
    return _producer_blocked(
        "producer: artifact existence unconfirmed",
        receipt_copy, repair_anchor_copy, carried_verified, tool_status,
        error="producer: artifact existence unconfirmed",
    )


def project_receipt_outcome(
    evidence: NodeEvidence | None, role: OutcomeProjectionRole
) -> NodeOutcome:
    """Project already-captured ``NodeEvidence`` into a role-aware ``NodeOutcome``.

    Raises ``ValueError`` for an unknown ``role`` (API misuse), before any evidence
    inspection. Malformed evidence / deep-copy failures return ``blocked``.
    """
    if role not in _VALID_ROLES:
        raise ValueError(f"Unknown outcome projection role: {role!r}")
    prefix = _ROLE_PREFIX[role]

    tool_status = evidence.tool_status if evidence is not None else None
    carried_verified = evidence.verified if evidence is not None else None

    receipt = evidence.receipt if evidence is not None else None
    if not isinstance(receipt, dict) or "artifact_status" not in receipt:
        return _reference_free_blocked(
            f"{prefix}: missing receipt or artifact_status", carried_verified, tool_status, prefix
        )

    artifact_status = receipt.get("artifact_status")
    if artifact_status not in _KNOWN_ARTIFACT_STATUSES:
        return _reference_free_blocked(
            f"{prefix}: unrecognized artifact_status '{artifact_status}'",
            carried_verified, tool_status, prefix,
        )

    try:
        receipt_copy = copy.deepcopy(receipt)
        repair_anchor_copy = (
            copy.deepcopy(evidence.repair_anchor)
            if evidence is not None and evidence.repair_anchor is not None
            else None
        )
    except Exception:
        return _reference_free_blocked(
            f"{prefix}: evidence copy failed", carried_verified, tool_status, prefix
        )

    if role == "artifact_producer":
        return _producer_outcome(
            artifact_status, receipt_copy, repair_anchor_copy, carried_verified, tool_status
        )
    return _conservative_outcome(
        artifact_status, receipt_copy, repair_anchor_copy, carried_verified, tool_status, prefix
    )
```

- [ ] **Step 4: Refactor LM3D into a compatibility wrapper**

Replace the body of `mcp_server/src/rook/learning/plan_graph_verifiers.py` so it delegates and no longer carries its own projection logic. Remove the now-dead private helpers (`_component_guid`, `_blocked_outcome`, `_KNOWN_ARTIFACT_STATUSES`) and the `copy` / `ARTIFACT_STATUS_TO_OUTCOME` imports. **First confirm `test_plan_graph_verifiers.py` does not import any of those private names** (`grep` for `_blocked_outcome`, `_component_guid`, `_KNOWN_ARTIFACT_STATUSES`); the campaign's tests are black-box, so this should be clean. The full replacement file:

```python
"""LM3D verifier-outcome adapter (compatibility wrapper over LM3F).

``script_receipt_verifier_outcome`` converts an already-captured ``NodeEvidence``
(its ``script_receipt``) into a *verifier node's* ``NodeOutcome``. As of LM3F the
projection logic lives in ``plan_graph_projection.project_receipt_outcome``; this
module keeps the original public function as the ``artifact_verifier`` role, so
existing callers (e.g. ``plan_graph_runner``) and the LM3D regression tests are
unchanged.

Distinct from LM1F (``plan_graph_outcomes.node_outcome_from_tool_result``), which
consumes a *raw tool result* and produces the *executing* node's outcome.
"""

from rook.learning.plan_graph import NodeEvidence, NodeOutcome
from rook.learning.plan_graph_projection import project_receipt_outcome


def script_receipt_verifier_outcome(evidence: NodeEvidence | None) -> NodeOutcome:
    """Re-judge an already-captured ``NodeEvidence`` as a verifier node would.

    Thin compatibility wrapper for the ``artifact_verifier`` projection role. Reads
    ``evidence.receipt``'s ``artifact_status`` and maps it through the shared
    ``ARTIFACT_STATUS_TO_OUTCOME`` table. Malformed evidence, an unrecognized
    status, or a deep-copy failure return ``blocked`` with an explanatory error.
    Never raises; never emits ``needs_escalation``.
    """
    return project_receipt_outcome(evidence, "artifact_verifier")
```

- [ ] **Step 5: Update the verifier purity allowlist test**

In `mcp_server/tests/test_plan_graph_verifiers.py`, the test `test_verifiers_module_imports_only_plan_graph_layer` asserts an exact-equality set (currently `{"rook.learning.plan_graph", "rook.learning.plan_graph_outcomes"}`). Make a single change: replace `"rook.learning.plan_graph_outcomes"` with `"rook.learning.plan_graph_projection"` so the set becomes:

```python
    assert rook_or_relative == {
        "rook.learning.plan_graph",
        "rook.learning.plan_graph_projection",
    }
```

(After delegation the wrapper imports `plan_graph` for the type annotations and `plan_graph_projection` for `project_receipt_outcome`; it no longer imports `plan_graph_outcomes`.) Leave the negative assertions (`plan_graph_walker`/`bridge`/`templates`/`planner`/`tool_dispatcher` not in imports), the `test_importing_verifiers_does_not_load_heavy_modules` subprocess probe, and every behavior assertion exactly as they are.

- [ ] **Step 6: Run the full PlanGraph suite to verify green**

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
Expected: PASS — all LM3F tests green, all prior PlanGraph tests (including the unchanged LM3D behavior assertions) still green. Then `mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/learning/plan_graph_projection.py mcp_server/src/rook/learning/plan_graph_verifiers.py` (silent).

- [ ] **Step 7: Commit**

```bash
git add mcp_server/src/rook/learning/plan_graph_projection.py \
        mcp_server/src/rook/learning/plan_graph_verifiers.py \
        mcp_server/tests/test_plan_graph_projection.py \
        mcp_server/tests/test_plan_graph_verifiers.py
git commit -m "feat(lm3f): role-aware outcome projection; LM3D delegates as artifact_verifier"
```

---

## Self-Review

- **Spec coverage:** role declaration as explicit `Literal` arg (§Public surface; `project_receipt_outcome`), 3-role table + producer promotion (§Role table; `_producer_outcome` / `_conservative_outcome`), mutation-evidence gate with non-empty-anchor rule (§Gate; `_has_mutation_evidence`), producer-unconfirmed blocked preserving the copied receipt (§Gate; `_producer_blocked`, tests 5/6 + isolation test), role-conditional facts emitted-when-derivable (§Facts; `_facts` used on producer success only, mutation-status-only test), verbatim verifier message parity + full-shape parity (parity tests via dataclass `==`), `ValueError` on bad role before evidence inspection (tests 14/15), one-way import + purity probes (allowlist + subprocess tests), LM3D delegation + allowlist-only test edit (Steps 4–5). All covered.
- **Placeholder scan:** none — every step carries full code or an exact command.
- **Type consistency:** `OutcomeProjectionRole`, `project_receipt_outcome`, `script_receipt_verifier_outcome` names/signatures match the spec and across steps; `_has_mutation_evidence` (gate, non-empty anchor) is deliberately distinct from `_facts` (LM3D-equivalent, any dict) and the plan flags this in Global Constraints.

## Execution Handoff

Single-task slice. Recommended: subagent-driven-development (haiku implementer — this is transcription-plus-testing; sonnet task reviewer; opus final whole-branch review). Final reviewer EXTRA instructions to carry:
(a) projection imports ONLY `plan_graph` + `plan_graph_outcomes`; verifiers imports ONLY `plan_graph` + `plan_graph_projection`; projection never imports verifiers.
(b) the entire `artifact_verifier` path reproduces LM3D byte-for-byte — parity tests must pass via full `NodeOutcome` dataclass equality (not just status/message), and LM3D's own behavior assertions are unedited.
(c) `_has_mutation_evidence` requires a NON-EMPTY repair anchor; `_facts` emits `repair_anchor` for any dict — confirm they are not conflated.
(d) producer-unconfirmed and producer success both carry the deep-COPIED receipt/anchor (never input references); the post-call mutation isolation tests prove it.
(e) invalid role raises `ValueError` before evidence inspection (proven with `evidence=None`).
(f) no `PlanGraph` / walker / LM1F / LM3E change; no 5-node template revival; no `needs_escalation`.
