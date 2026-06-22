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
