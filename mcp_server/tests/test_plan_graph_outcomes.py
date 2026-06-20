from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys

import pytest

from rook.learning.plan_graph_outcomes import node_outcome_from_tool_result


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


def test_receipt_extraction_only_uses_internal_data_script_receipt_location():
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
