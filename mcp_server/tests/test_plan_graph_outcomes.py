from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys

import pytest

from rook.learning.plan_graph import NodeEvidence, NodeOutcome, PlanGraph, PlanGraphNode
from rook.learning.plan_graph_outcomes import (
    node_evidence_from_tool_result,
    node_outcome_from_tool_result,
    _extract_script_receipt,
)
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
from rook.learning.plan_graph_runner import apply_producer_result


def _receipt_result(
    artifact_status: str | None,
    *,
    success: bool = False,
    message: str | None = "script result message",
    error: str | None = None,
    mutation_guid: str | None = "component-guid",
    repair_guid: str | None = "repair-guid",
    repair_anchor: object | None = None,
):
    if repair_anchor is None:
        repair_anchor = {
            "component_guid": repair_guid,
            "pins_out": [{"name": "B", "type": "Brep"}],
        }
    receipt = {
        "version": 1,
        "operation": "create",
        "language": "csharp",
        "mutation": {
            "status": "created",
            "method": "gh_create_component_then_script",
            "component_guid": mutation_guid,
            "note": None,
        },
        "verification": {
            "status": "failed",
            "method": "gh_errors",
            "target_error_count": 1,
            "target_warning_count": 0,
            "unrelated_error_count": 0,
            "unrelated_warning_count": 0,
            "note": None,
        },
        "repair_anchor": repair_anchor,
    }
    if artifact_status is not None:
        receipt["artifact_status"] = artifact_status

    result = {
        "success": success,
        "data": {
            "script_receipt": receipt,
        },
    }
    if message is not None:
        result["message"] = message
    if error is not None:
        result["error"] = error
    return result


@pytest.mark.parametrize(
    "artifact_status,expected_status,expected_summary",
    [
        ("usable", "succeeded", "artifact usable"),
        ("created_with_errors", "needs_repair", "artifact needs repair"),
        ("written_with_errors", "needs_repair", "artifact needs repair"),
        ("verification_pending", "blocked", "verification pending"),
        ("unknown", "blocked", "verification unknown"),
    ],
)
def test_artifact_status_maps_to_node_outcome_status(
    artifact_status, expected_status, expected_summary
):
    outcome = node_outcome_from_tool_result(_receipt_result(artifact_status))

    assert outcome.status == expected_status
    assert outcome.memory_updates == {
        "facts": {
            "component_guid": "component-guid",
            "repair_anchor": {
                "component_guid": "repair-guid",
                "pins_out": [{"name": "B", "type": "Brep"}],
            },
        },
        "node_summary": expected_summary,
    }


@pytest.mark.parametrize(
    "result,expected_status,expected_summary",
    [
        ({"success": True, "message": "ok"}, "succeeded", "tool succeeded"),
        ({"success": False, "error": "bad input"}, "failed", "tool failed"),
        ({"status": "loaded"}, "blocked", "tool blocked"),
    ],
)
def test_missing_receipt_falls_back_to_tool_result_view(
    result, expected_status, expected_summary
):
    outcome = node_outcome_from_tool_result(result)

    assert outcome.status == expected_status
    assert outcome.evidence.receipt is None
    assert outcome.evidence.repair_anchor is None
    assert outcome.memory_updates == {
        "facts": {},
        "node_summary": expected_summary,
    }


@pytest.mark.parametrize("artifact_status", [None, "future_status"])
def test_missing_or_unrecognized_artifact_status_falls_back_but_carries_receipt(
    artifact_status,
):
    result = _receipt_result(artifact_status, success=True)

    outcome = node_outcome_from_tool_result(result)

    assert outcome.status == "succeeded"
    assert outcome.evidence.receipt == result["data"]["script_receipt"]
    assert outcome.evidence.repair_anchor == result["data"]["script_receipt"]["repair_anchor"]
    assert outcome.memory_updates["node_summary"] == "tool succeeded"
    assert outcome.memory_updates["facts"]["component_guid"] == "component-guid"


def test_evidence_preserves_tool_result_view_fields_and_verification_note():
    result = {
        "success": False,
        "data": {
            "verified": False,
            "verification_note": "verification failed note",
        },
    }

    outcome = node_outcome_from_tool_result(result)

    assert outcome.status == "failed"
    assert outcome.evidence.tool_status == "failed"
    assert outcome.evidence.verified is False
    assert outcome.evidence.message == "verification failed note"
    assert outcome.evidence.error is None
    assert outcome.message is None
    assert outcome.error is None


def test_message_wins_over_verification_note_and_error_is_preserved():
    result = {
        "success": False,
        "message": "top message",
        "error": "top error",
        "data": {
            "verified": False,
            "message": "nested verification note",
        },
    }

    outcome = node_outcome_from_tool_result(result)

    assert outcome.evidence.message == "top message"
    assert outcome.evidence.error == "top error"
    assert outcome.message == "top message"
    assert outcome.error == "top error"


def test_memory_component_guid_falls_back_to_repair_anchor_guid():
    result = _receipt_result(
        "created_with_errors",
        mutation_guid=None,
        repair_guid="anchor-guid",
    )

    outcome = node_outcome_from_tool_result(result)

    assert outcome.memory_updates["facts"]["component_guid"] == "anchor-guid"


def test_memory_ignores_non_dict_repair_anchor_and_does_not_parse_messages():
    result = _receipt_result(
        "created_with_errors",
        message="Use component 11111111-1111-1111-1111-111111111111",
        mutation_guid=None,
        repair_anchor="not a dict",
    )

    outcome = node_outcome_from_tool_result(result)

    assert outcome.evidence.repair_anchor is None
    assert outcome.memory_updates == {
        "facts": {},
        "node_summary": "artifact needs repair",
    }


def test_non_dict_result_is_blocked_with_empty_evidence_fields():
    outcome = node_outcome_from_tool_result("plain string result")

    assert outcome.status == "blocked"
    assert outcome.evidence.tool_status is None
    assert outcome.evidence.verified is None
    assert outcome.evidence.receipt is None
    assert outcome.evidence.repair_anchor is None
    assert outcome.evidence.message is None
    assert outcome.evidence.error is None
    assert outcome.memory_updates == {
        "facts": {},
        "node_summary": "tool blocked",
    }


def test_adapter_deep_copies_receipt_repair_anchor_and_memory_facts():
    result = _receipt_result("created_with_errors")

    outcome = node_outcome_from_tool_result(result)

    result["data"]["script_receipt"]["artifact_status"] = "mutated"
    result["data"]["script_receipt"]["repair_anchor"]["pins_out"][0]["name"] = "Mutated"

    assert outcome.evidence.receipt["artifact_status"] == "created_with_errors"
    assert outcome.evidence.repair_anchor["pins_out"][0]["name"] == "B"
    assert outcome.memory_updates["facts"]["repair_anchor"]["pins_out"][0]["name"] == "B"

    outcome.evidence.receipt["repair_anchor"]["pins_out"][0]["name"] = "ReceiptOnly"
    assert outcome.evidence.repair_anchor["pins_out"][0]["name"] == "B"
    assert outcome.memory_updates["facts"]["repair_anchor"]["pins_out"][0]["name"] == "B"

    outcome.evidence.repair_anchor["pins_out"][0]["name"] = "EvidenceOnly"
    assert outcome.evidence.receipt["repair_anchor"]["pins_out"][0]["name"] == "ReceiptOnly"
    assert outcome.memory_updates["facts"]["repair_anchor"]["pins_out"][0]["name"] == "B"

    outcome.memory_updates["facts"]["repair_anchor"]["pins_out"][0]["name"] = "MemoryOnly"
    assert outcome.evidence.receipt["repair_anchor"]["pins_out"][0]["name"] == "ReceiptOnly"
    assert outcome.evidence.repair_anchor["pins_out"][0]["name"] == "EvidenceOnly"


def test_top_level_receipt_ignored_when_envelope_markers_present():
    """LM4F refined rule: a top-level script_receipt is honored ONLY for the
    MCP success-unwrapped payload shape (no internal-envelope markers). When the
    dict still looks like an internal result envelope (here a ``success`` key),
    the stray top-level receipt is NOT reinterpreted -- preserving the original
    guardrail. The MCP success-unwrapped case (no markers) is covered separately
    by test_extract_receipt_top_level_shape_extracted_and_deepcopied."""
    result = {
        "success": True,
        "script_receipt": {
            "artifact_status": "created_with_errors",
            "repair_anchor": {"component_guid": "top-level"},
        },
    }

    outcome = node_outcome_from_tool_result(result)

    assert outcome.status == "succeeded"
    assert outcome.evidence.receipt is None
    assert outcome.memory_updates == {
        "facts": {},
        "node_summary": "tool succeeded",
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


def test_plan_graph_outcomes_uses_pure_tool_result_view_boundary():
    imports = _direct_import_modules(
        "mcp_server/src/rook/learning/plan_graph_outcomes.py"
    )

    assert "rook.agent.chat.tool_result_view" in imports
    assert "rook.agent.chat.tool_contracts" not in imports
    assert "rook.agent.tool_dispatcher" not in imports
    assert "rook.agent.chat.chat_runner" not in imports
    assert "rook.server" not in imports
    assert "rook.learning.plan_graph" in imports


def test_tool_result_view_stays_pure():
    imports = _direct_import_modules("mcp_server/src/rook/agent/chat/tool_result_view.py")

    assert imports <= {"dataclasses", "typing"}


def test_importing_plan_graph_outcomes_does_not_load_tool_dispatcher():
    env = os.environ.copy()
    src_path = str(Path("mcp_server/src").resolve())
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )

    probe = (
        "import sys\n"
        "import rook.learning.plan_graph_outcomes\n"
        "if 'rook.agent.tool_dispatcher' in sys.modules:\n"
        "    raise SystemExit('rook.agent.tool_dispatcher loaded')\n"
        "if 'dspy' in sys.modules:\n"
        "    raise SystemExit('dspy loaded')\n"
        "if 'litellm' in sys.modules:\n"
        "    raise SystemExit('litellm loaded')\n"
    )

    subprocess.run(
        [sys.executable, "-c", probe],
        check=True,
        env=env,
    )


def test_core_modules_do_not_import_adapter_or_each_other():
    tool_contracts_imports = _direct_import_modules(
        "mcp_server/src/rook/agent/chat/tool_contracts.py"
    )
    plan_graph_imports = _direct_import_modules("mcp_server/src/rook/learning/plan_graph.py")

    assert "rook.learning.plan_graph" not in tool_contracts_imports
    assert "rook.learning.plan_graph_outcomes" not in tool_contracts_imports
    assert "rook.agent.chat.tool_contracts" not in plan_graph_imports
    assert "rook.learning.plan_graph_outcomes" not in plan_graph_imports


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


# --- LM4F: MCP success-unwrapped top-level script_receipt -------------------

def _nested_usable_result(component_guid="comp-nested"):
    """Wrapped dispatcher / MCP-failure shape: receipt under data."""
    return {
        "success": True,
        "data": {
            "marker": "nested",
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "usable",
                "mutation": {"status": "created", "component_guid": component_guid},
                "repair_anchor": {"component_guid": component_guid},
            },
        },
    }


def _top_level_usable_result(component_guid="comp-top"):
    """MCP success-unwrapped shape: receipt at the top level, no success/data key."""
    return {
        "component_guid": component_guid,
        "name": "TopLevelUsable",
        "code_length": 120,
        "script_receipt": {
            "version": 1,
            "operation": "create",
            "language": "csharp",
            "artifact_status": "usable",
            "mutation": {"status": "created", "component_guid": component_guid},
            "repair_anchor": {"component_guid": component_guid},
        },
    }


def _ready_producer_graph():
    node = PlanGraphNode(
        id="create",
        intent="create",
        metadata={OUTCOME_PROJECTION_ROLE_KEY: "artifact_producer"},
        status="ready",
    )
    return PlanGraph(nodes={"create": node})


def test_extract_receipt_nested_shape_unchanged_and_deepcopied():
    """Regression: the wrapped data.script_receipt path still extracts and
    returns a deep copy (mutating the result must not touch the input)."""
    result = _nested_usable_result()
    receipt = _extract_script_receipt(result)
    assert isinstance(receipt, dict)
    assert receipt["artifact_status"] == "usable"
    receipt["artifact_status"] = "MUTATED"
    assert result["data"]["script_receipt"]["artifact_status"] == "usable"


def test_extract_receipt_top_level_shape_extracted_and_deepcopied():
    """The fix: a top-level script_receipt (no data key) is extracted and
    deep-copied."""
    result = _top_level_usable_result()
    receipt = _extract_script_receipt(result)
    assert isinstance(receipt, dict)
    assert receipt["artifact_status"] == "usable"
    receipt["artifact_status"] = "MUTATED"
    assert result["script_receipt"]["artifact_status"] == "usable"


def test_extract_receipt_both_present_nested_wins():
    """Precedence: when both locations carry a receipt, nested wins."""
    result = _nested_usable_result(component_guid="nested-guid")
    result["script_receipt"] = {
        "artifact_status": "usable",
        "mutation": {"status": "created", "component_guid": "top-guid"},
    }
    receipt = _extract_script_receipt(result)
    assert receipt["mutation"]["component_guid"] == "nested-guid"


def test_extract_receipt_non_dict_top_level_falls_through_to_none():
    """A non-dict top-level script_receipt is ignored; no data key -> None."""
    assert _extract_script_receipt({"script_receipt": "not a dict"}) is None
    assert _extract_script_receipt({"data": "err-string"}) is None


def test_node_evidence_from_top_level_usable_payload():
    """node_evidence_from_tool_result on the unwrapped usable shape captures the
    receipt + repair_anchor; tool_status/verified are None (the payload carries
    neither -- grounded, not over-asserted)."""
    evidence = node_evidence_from_tool_result(_top_level_usable_result())
    assert evidence.receipt is not None
    assert evidence.receipt["artifact_status"] == "usable"
    assert evidence.repair_anchor is not None
    assert evidence.repair_anchor["component_guid"] == "comp-top"
    assert evidence.tool_status is None
    assert evidence.verified is None


def test_apply_producer_result_top_level_usable_succeeds_end_to_end():
    """Payoff through the REAL consumer path LM4E uses:
    raw top-level MCP success payload -> node_evidence_from_tool_result ->
    producer projection -> reducer."""
    graph = _ready_producer_graph()
    result = apply_producer_result(graph, "create", _top_level_usable_result())

    assert result.applied is True
    assert result.outcome_status == "succeeded"
    node = result.graph.nodes["create"]
    assert node.status == "succeeded"
    assert node.evidence.verified is True
    # The top-level receipt survived capture -> projection -> reducer onto the node.
    assert node.evidence.receipt["artifact_status"] == "usable"
