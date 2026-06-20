from copy import deepcopy
from typing import Any

from rook.agent.chat.tool_result_view import ToolResultView, normalize_tool_result
from rook.learning.plan_graph import NodeEvidence, NodeOutcome


_ARTIFACT_STATUS_TO_OUTCOME = {
    "usable": "succeeded",
    "created_with_errors": "needs_repair",
    "written_with_errors": "needs_repair",
    "verification_pending": "blocked",
    "unknown": "blocked",
}

_ARTIFACT_STATUS_TO_SUMMARY = {
    "usable": "artifact usable",
    "created_with_errors": "artifact needs repair",
    "written_with_errors": "artifact needs repair",
    "verification_pending": "verification pending",
    "unknown": "verification unknown",
}

_TOOL_STATUS_TO_OUTCOME = {
    "success": "succeeded",
    "failed": "failed",
}

_TOOL_STATUS_TO_SUMMARY = {
    "success": "tool succeeded",
    "failed": "tool failed",
}


def _extract_script_receipt(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    data = result.get("data")
    if not isinstance(data, dict):
        return None
    receipt = data.get("script_receipt")
    return deepcopy(receipt) if isinstance(receipt, dict) else None


def _artifact_status(receipt: dict[str, Any] | None) -> str | None:
    if not isinstance(receipt, dict):
        return None
    value = receipt.get("artifact_status")
    return value if isinstance(value, str) else None


def _repair_anchor(receipt: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(receipt, dict):
        return None
    value = receipt.get("repair_anchor")
    return deepcopy(value) if isinstance(value, dict) else None


def _outcome_status(view: ToolResultView, receipt: dict[str, Any] | None) -> str:
    artifact_status = _artifact_status(receipt)
    mapped = _ARTIFACT_STATUS_TO_OUTCOME.get(artifact_status)
    if mapped is not None:
        return mapped
    return _TOOL_STATUS_TO_OUTCOME.get(view.status, "blocked")


def _node_summary(view: ToolResultView, receipt: dict[str, Any] | None) -> str:
    artifact_status = _artifact_status(receipt)
    mapped = _ARTIFACT_STATUS_TO_SUMMARY.get(artifact_status)
    if mapped is not None:
        return mapped
    return _TOOL_STATUS_TO_SUMMARY.get(view.status, "tool blocked")


def _component_guid_from_receipt(
    receipt: dict[str, Any] | None,
    repair_anchor: dict[str, Any] | None,
) -> str | None:
    if isinstance(receipt, dict):
        mutation = receipt.get("mutation")
        if isinstance(mutation, dict):
            component_guid = mutation.get("component_guid")
            if isinstance(component_guid, str) and component_guid:
                return component_guid
    if isinstance(repair_anchor, dict):
        component_guid = repair_anchor.get("component_guid")
        if isinstance(component_guid, str) and component_guid:
            return component_guid
    return None


def _memory_updates(
    view: ToolResultView,
    receipt: dict[str, Any] | None,
    repair_anchor: dict[str, Any] | None,
) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    component_guid = _component_guid_from_receipt(receipt, repair_anchor)
    if component_guid is not None:
        facts["component_guid"] = component_guid
    if repair_anchor is not None:
        facts["repair_anchor"] = deepcopy(repair_anchor)
    return {
        "facts": facts,
        "node_summary": _node_summary(view, receipt),
    }


def node_outcome_from_tool_result(result: Any) -> NodeOutcome:
    view = normalize_tool_result(result)
    receipt = _extract_script_receipt(result)
    repair_anchor = _repair_anchor(receipt)
    evidence = NodeEvidence(
        tool_status=view.status,
        verified=view.verified,
        receipt=deepcopy(receipt) if receipt is not None else None,
        repair_anchor=deepcopy(repair_anchor) if repair_anchor is not None else None,
        message=view.message or view.verification_note,
        error=view.error,
    )
    return NodeOutcome(
        status=_outcome_status(view, receipt),
        evidence=evidence,
        memory_updates=_memory_updates(view, receipt, repair_anchor),
        message=view.message,
        error=view.error,
    )
