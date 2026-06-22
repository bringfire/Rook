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
