#!/usr/bin/env python
"""LM8C GH scalar expectation live splice probe."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _path in (str(_SCRIPT_DIR), str(_REPO_ROOT), str(_MCP_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from lm_worker_two_pass_publication import run_two_pass_worker_publication  # noqa: E402,F401
from rook.agent.gh_scalar_expectation_acceptance_criteria import (  # noqa: E402
    assemble_gh_scalar_expectation_packet,
    project_gh_scalar_expectation_legacy,
)
from rook.agent.gh_scalar_expectation_sources import (  # noqa: E402
    CONVENTION_SOURCE_PATH,
    EXPECTED_OUTPUT_SOURCE_PATH,
    FIXTURE_ANCHOR_SOURCE_PATH,
    OBSERVED_OUTPUT_SOURCE_PATH,
    extract_gh_scalar_expectation_sources,
)
from rook.agent.local_worker_source_routing_validator import (  # noqa: E402
    validate_worker_visible_source_routing,
)
from rook.agent.local_worker_turn_context import (  # noqa: E402
    WorkerAllowedAction,
    WorkerKnowledgePacket,
    build_local_worker_turn_context,
)
from rook.agent.local_worker_turn_request import (  # noqa: E402
    render_local_worker_turn_request_payload,
)
from rook.agent.plan_graph_gh_scalar_value_apply import (  # noqa: E402
    apply_gh_scalar_value_action_to_node,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY  # noqa: E402
from rook.agent.plan_graph_workflow_contract import (  # noqa: E402
    CompiledWorkflowScaffold,
    WorkflowCompileRecord,
    WorkflowContractSnapshot,
)
from rook.learning.plan_graph import (  # noqa: E402
    GraphMemory,
    NodeEvidence,
    PlanGraph,
    PlanGraphNode,
)


SCRIPT_SCHEMA = "rook.lm8c_gh_scalar_expectation_live_probe:v1"
DECISION_SCHEMA = "rook.lm8c_decision:v1"
DEFAULT_MODEL = "gemma4:12b-it-qat"
DEFAULT_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_TEMPERATURE = 0
DEFAULT_TIMEOUT_S = 120
DEFAULT_EXCERPT_CHARS = 1200
INITIAL_SCALAR_VALUE = 0.0
EXPECTED_OUTPUT_VALUE = 7.5
SCALAR_TOLERANCE = 1e-9
WORKER_NODE_ID = "set_scalar_value"
CREATE_NODE_ID = "create_scalar_expectation"
VERIFY_NODE_ID = "verify_scalar_output"
ACTION_ID = "draft_gh_set_value_params"
DECISIONS = {
    "preflight_failed",
    "gate_failed",
    "publication_failed",
    "worker_declined",
    "rejected",
    "accepted",
}
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM8C GH scalar expectation live splice probe."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--excerpt-chars", type=int, default=DEFAULT_EXCERPT_CHARS)
    parser.add_argument("--run-dir", default="probe_runs")
    parser.add_argument("--canonical-evidence", action="store_true")
    args = parser.parse_args(argv)
    if args.excerpt_chars < 0:
        parser.error("excerpt_chars_must_be_non_negative")
    if not args.canonical_evidence:
        args.canonical_evidence = (
            args.model == DEFAULT_MODEL
            and args.endpoint == DEFAULT_ENDPOINT
            and args.temperature == DEFAULT_TEMPERATURE
        )
    return args


def _canonical_evidence_is_valid(args: argparse.Namespace) -> bool:
    if not args.canonical_evidence:
        return True
    return (
        args.model == DEFAULT_MODEL
        and args.endpoint == DEFAULT_ENDPOINT
        and args.temperature == DEFAULT_TEMPERATURE
    )


def _git_short_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _new_run_dir(run_root: str | Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(run_root) / f"lm8c-{timestamp}-{_git_short_sha()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _fingerprint_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _guid_sha256(guid: str | None) -> str | None:
    return None if guid is None else _sha256_text(guid)


def _routing_report_json(report: Any) -> dict[str, Any]:
    return {
        "schema": report.schema,
        "valid": report.valid,
        "routability_evaluated": report.routability_evaluated,
        "static_diagnostics": [
            {
                "severity": item.severity,
                "code": item.code,
                "node_id": item.node_id,
                "route_id": item.route_id,
                "source_class": item.source_class,
                "source_path": item.source_path,
                "purpose": item.purpose,
                "message": item.message,
            }
            for item in report.static_diagnostics
        ],
        "routability_diagnostics": [
            {
                "severity": item.severity,
                "code": item.code,
                "node_id": item.node_id,
                "route_id": item.route_id,
                "source_class": item.source_class,
                "source_path": item.source_path,
                "purpose": item.purpose,
                "message": item.message,
            }
            for item in report.routability_diagnostics
        ],
    }


def _scalar_source_routing_artifact() -> dict[str, Any]:
    return {
        "schema": "rook.worker_visible_source_routing:v1",
        "routes": [
            {
                "node_id": WORKER_NODE_ID,
                "visible_sources": [
                    {
                        "route_id": "scalar_expected_output_value",
                        "source_class": "expected_output_contract",
                        "source_path": EXPECTED_OUTPUT_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "scalar_current_output",
                        "source_class": "receipt_observation",
                        "source_path": OBSERVED_OUTPUT_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "scalar_editable_target_contract",
                        "source_class": "fixture_anchor",
                        "source_path": FIXTURE_ANCHOR_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "scalar_set_value_convention",
                        "source_class": "convention",
                        "source_path": CONVENTION_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": False,
                    },
                ],
            }
        ],
    }


def _scalar_contract_payload() -> dict[str, Any]:
    return {
        "rules": {
            VERIFY_NODE_ID: {
                "expected_output_value": EXPECTED_OUTPUT_VALUE,
            }
        }
    }


def _graph_from_scalar_receipt(receipt: Mapping[str, Any]) -> PlanGraph:
    return PlanGraph(
        nodes={
            CREATE_NODE_ID: PlanGraphNode(
                id=CREATE_NODE_ID,
                intent="Create GH scalar expectation fixture",
                status="succeeded",
                evidence=NodeEvidence(
                    tool_status="success",
                    verified=True,
                    receipt=dict(receipt),
                ),
            ),
            WORKER_NODE_ID: PlanGraphNode(
                id=WORKER_NODE_ID,
                intent="Set editable GH scalar value",
                execution_ref="gh_set_value:v1",
                status="ready",
            ),
            VERIFY_NODE_ID: PlanGraphNode(
                id=VERIFY_NODE_ID,
                intent="Verify GH scalar output",
                verifier_ref="gh_get_value:v1",
                status="pending",
                is_terminal=True,
            ),
        },
        memory=GraphMemory(),
    )


def _scalar_runtime_context(
    *,
    graph: PlanGraph,
    workflow_contract_payload: Mapping[str, Any],
    convention_packets: tuple[WorkerKnowledgePacket, ...],
) -> dict[str, Any]:
    routing_artifact = _scalar_source_routing_artifact()
    static_report = validate_worker_visible_source_routing(routing_artifact)
    static_report_json = _routing_report_json(static_report)
    if static_report.valid is not True:
        return {
            "scalar_runtime_ready": False,
            "routing_artifact": routing_artifact,
            "static_routing_report": static_report_json,
        }
    sources = extract_gh_scalar_expectation_sources(
        workflow_contract_payload=workflow_contract_payload,
        graph=graph,
        convention_packets=convention_packets,
    )
    packet = assemble_gh_scalar_expectation_packet(sources)
    worker_visible = project_gh_scalar_expectation_legacy(packet)
    return {
        "scalar_runtime_ready": True,
        "routing_artifact": routing_artifact,
        "static_routing_report": static_report_json,
        "sources": sources,
        "packet": packet,
        "worker_visible": worker_visible,
    }


def _scalar_scaffold(graph: PlanGraph) -> CompiledWorkflowScaffold:
    normalized_contract = {
        "schema": "rook.workflow_contract:v1",
        "workflow_id": "lm8c-gh-scalar-expectation",
    }
    contract_fingerprint = _fingerprint_json(normalized_contract).removeprefix(
        "sha256:"
    )
    snapshot = WorkflowContractSnapshot(
        workflow_id="lm8c-gh-scalar-expectation",
        normalized_contract=normalized_contract,
        contract_fingerprint=contract_fingerprint,
    )
    compile_record = WorkflowCompileRecord(
        workflow_id="lm8c-gh-scalar-expectation",
        compiler_id="lm8c.script_local_scalar_scaffold:v1",
        contract_schema="rook.workflow_contract:v1",
        contract_fingerprint_algorithm="sha256",
        contract_fingerprint=contract_fingerprint,
        provider_id="lm8c.script_local_provider:v1",
        expected_template_id="gh_scalar_value_expectation",
        selected_template_id="gh_scalar_value_expectation",
        graph_node_ids=tuple(sorted(graph.nodes)),
        initial_param_node_ids=(),
        rule_node_ids=(WORKER_NODE_ID, VERIFY_NODE_ID),
        terminal_node_ids=(VERIFY_NODE_ID,),
        expected_refs=((WORKER_NODE_ID, "gh_set_value:v1"),),
        step_kinds_by_rule=(),
        max_steps=4,
    )
    return CompiledWorkflowScaffold(
        workflow_id="lm8c-gh-scalar-expectation",
        graph=graph,
        provider=object(),
        max_steps=4,
        metadata={},
        rules=(),
        steps=(),
        contract_snapshot=snapshot,
        compile_record=compile_record,
    )


def _scalar_action_selection_contract() -> dict[str, Any]:
    return {
        "contract_id": "gh_scalar_action_selection:v1",
        "worker_agency": (
            "If the acceptance criteria are sufficient and action is warranted, "
            "publish action_request with the exact required_action_id. If action "
            "is not warranted, publish a non-action response."
        ),
        "required_response_kind_if_acting": "action_request",
        "required_action_id": ACTION_ID,
        "pass1_decision_required_fields_if_acting": ["kind", "action_id"],
        "final_action_request_required_fields": [
            "schema",
            "kind",
            "action_id",
            "rationale",
            "input",
        ],
        "action_input_schema": {
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "number"}},
            "additionalProperties": False,
        },
        "authority_limits": [
            "do not author target GUID",
            "do not call GH tools directly",
            "do not author topology, code, or batch edits",
        ],
    }


def _scalar_worker_evidence_packet(
    *,
    packet: Mapping[str, Any],
    worker_visible: Mapping[str, Any],
) -> WorkerKnowledgePacket:
    fields = packet["fields"]
    editable = dict(fields["editable_value_contract"])
    return WorkerKnowledgePacket(
        packet_id="gh_scalar_expectation_evidence",
        kind="evidence",
        title="GH scalar expectation evidence",
        content={
            "source": "gh_scalar_expectation",
            "trust": "high",
            "state": "post_scalar_fixture_pre_worker",
            "fields": {
                "current_observed_output": fields["current_observed_output"],
                "expected_output_value": fields["expected_output_value"],
                "editable_value_contract": editable,
                "acceptance_criteria": dict(worker_visible),
                "recommended_action_id": ACTION_ID,
                "action_selection_contract": _scalar_action_selection_contract(),
            },
        },
    )


def _scalar_allowed_action() -> WorkerAllowedAction:
    return WorkerAllowedAction(
        action_id=ACTION_ID,
        kind="stage_params",
        description="Draft the scalar value to apply to the trusted editable GH target.",
        input_schema={
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "number"}},
            "additionalProperties": False,
        },
    )


def _build_local_turn_payload(
    *,
    graph: PlanGraph,
    packet: Mapping[str, Any],
    worker_visible: Mapping[str, Any],
) -> dict[str, Any]:
    context = build_local_worker_turn_context(
        _scalar_scaffold(graph),
        graph,
        records=(),
        supply_records=(),
        current_node_id=WORKER_NODE_ID,
        knowledge=(
            _scalar_worker_evidence_packet(
                packet=packet,
                worker_visible=worker_visible,
            ),
        ),
        allowed_actions=(_scalar_allowed_action(),),
    )
    return dict(render_local_worker_turn_request_payload(context))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _write_json_value(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _find_forbidden_decision_extra_paths(
    value: Any, *, base_keys: set[str], path: str = "extra"
) -> list[str]:
    forbidden: list[str] = []
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            key_text = str(key)
            key_path = f"{path}.{key_text}"
            if key_text in base_keys or "guid" in key_text.casefold():
                forbidden.append(key_path)
            forbidden.extend(
                _find_forbidden_decision_extra_paths(
                    nested_value, base_keys=base_keys, path=key_path
                )
            )
        return forbidden
    if isinstance(value, str):
        if "guid" in value.casefold() or _UUID_RE.search(value):
            forbidden.append(path)
        return forbidden
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for index, nested_value in enumerate(value):
            forbidden.extend(
                _find_forbidden_decision_extra_paths(
                    nested_value, base_keys=base_keys, path=f"{path}[{index}]"
                )
            )
    return forbidden


def _sanitize_decision_excerpt_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, nested_value in value.items():
            key_text = str(key)
            if "guid" in key_text.casefold():
                sanitized["reserved_key"] = "[redacted]"
            else:
                sanitized[key_text] = _sanitize_decision_excerpt_value(nested_value)
        return sanitized
    if isinstance(value, str):
        if "guid" in value.casefold() or _UUID_RE.search(value):
            return "[redacted]"
        return value
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_sanitize_decision_excerpt_value(item) for item in value]
    return value


def _decision_record(
    *,
    decision: str,
    reason: str,
    phase: str,
    canonical_evidence: bool,
    scalar_runtime_ready: bool | None = None,
    live_fixture_created: bool = False,
    worker_publication_ran: bool = False,
    live_set_value_dispatched: bool = False,
    verify_scalar_output_ran: bool = False,
    component_guid: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if decision not in DECISIONS:
        raise ValueError(f"Unsupported LM8C decision: {decision}")
    record = {
        "schema": DECISION_SCHEMA,
        "decision": decision,
        "reason": reason,
        "phase": phase,
        "canonical_evidence": canonical_evidence,
        "scalar_runtime_ready": scalar_runtime_ready,
        "live_fixture_created": live_fixture_created,
        "worker_publication_ran": worker_publication_ran,
        "live_set_value_dispatched": live_set_value_dispatched,
        "verify_scalar_output_ran": verify_scalar_output_ran,
        "guid_present": component_guid is not None,
        "component_guid_sha256": _guid_sha256(component_guid),
    }
    if extra:
        extra_record = dict(extra)
        blocked_paths = _find_forbidden_decision_extra_paths(
            extra_record, base_keys=set(record)
        )
        if blocked_paths:
            raise ValueError(
                "LM8C decision extra contains reserved identity fields: "
                + ", ".join(sorted(blocked_paths))
            )
        record.update(extra_record)
    return record


def _manifest(
    *, model: str, endpoint: str, temperature: float, canonical_evidence: bool
) -> dict[str, Any]:
    return {
        "schema": SCRIPT_SCHEMA,
        "git_commit": _git_short_sha(),
        "model": model,
        "endpoint": endpoint,
        "temperature": temperature,
        "canonical_evidence": canonical_evidence,
        "attempts": 1,
        "initial_scalar_value": INITIAL_SCALAR_VALUE,
        "expected_output_value": EXPECTED_OUTPUT_VALUE,
        "identity_projection": True,
        "worker_retry_enabled": False,
        "planner_model": None,
        "gh_edit_enabled": False,
    }


def _tool_result_failed(result: Any) -> bool:
    if result is None:
        return True
    if isinstance(result, Mapping):
        if result.get("success") is False:
            return True
        if result.get("error"):
            return True
        data = result.get("data")
        if isinstance(data, str) and data.startswith("Error:"):
            return True
    return False


def _preflight_ping_ok(result: Any) -> bool:
    if result == "pong":
        return True
    if isinstance(result, Mapping):
        return result.get("success") is True and result.get("data") == "pong"
    return False


def _document_new_ok(result: Any) -> bool:
    if not isinstance(result, Mapping):
        return False
    data = result.get("data")
    if result.get("created") is True or result.get("Created") is True:
        return True
    if isinstance(data, Mapping):
        return data.get("created") is True or data.get("Created") is True
    return False


async def _run_preflight(
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]],
) -> tuple[bool, str | None, dict[str, Any]]:
    summaries: dict[str, Any] = {}
    try:
        ping = await tool_executor("rhino_ping", {})
    except Exception as exc:
        summaries["rhino_ping"] = {"exception": type(exc).__name__}
        return False, "rhino_ping_failed", summaries
    summaries["rhino_ping"] = ping
    if _tool_result_failed(ping) or not _preflight_ping_ok(ping):
        return False, "rhino_ping_failed", summaries

    try:
        document = await tool_executor("gh_document_new", {})
    except Exception as exc:
        summaries["gh_document_new"] = {"exception": type(exc).__name__}
        return False, "gh_document_new_failed", summaries
    summaries["gh_document_new"] = document
    if _tool_result_failed(document) or not _document_new_ok(document):
        return False, "gh_document_new_failed", summaries
    return True, None, summaries


def _coerce_scalar_value(value: Any) -> float | int:
    import math

    if isinstance(value, bool):
        raise ValueError("live scalar value must be a finite number")
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("live scalar value must be a finite number")
        return value
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError as exc:
            raise ValueError("live scalar value must be a finite number") from exc
        if not math.isfinite(parsed):
            raise ValueError("live scalar value must be a finite number")
        return parsed
    raise ValueError("live scalar value must be a finite number")


def _tool_data(result: Any) -> Any:
    if isinstance(result, Mapping) and isinstance(result.get("data"), Mapping):
        return result["data"]
    return result


def _tool_field(result: Any, *names: str) -> Any:
    if not isinstance(result, Mapping):
        return None
    for name in names:
        if name in result:
            return result[name]
    data = result.get("data")
    if not isinstance(data, Mapping):
        return None
    for name in names:
        if name in data:
            return data[name]
    return None


def _guid_from_result(result: Any) -> str:
    guid = _tool_field(result, "guid", "Guid", "component_guid")
    if not isinstance(guid, str) or not guid.strip():
        raise ValueError("tool result guid missing")
    return guid


def _receipt_sha256(result: Any) -> str:
    return _fingerprint_json(result)


def _decision_from_publication(
    publication_row: Mapping[str, Any],
    response_payload: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    status = publication_row.get("status")
    if status != "published":
        reason = str(publication_row.get("failure_reason") or status or "unknown")
        return {
            "decision": "publication_failed",
            "reason": f"{status}:{reason}",
            "phase": "worker_publication",
        }
    if not isinstance(response_payload, Mapping):
        return {
            "decision": "publication_failed",
            "reason": "published_response_missing",
            "phase": "worker_publication",
        }
    kind = response_payload.get("kind")
    if kind == "action_request":
        return None
    if publication_row.get("observation_action_intent_anomaly") is True:
        return {
            "decision": "worker_declined",
            "reason": "worker_observation_action_intent_anomaly",
            "phase": "worker_publication",
            "final_worker_response_kind": kind,
        }
    reasons = {
        "clarification_request": "worker_clarified",
        "refusal": "worker_refused",
        "observation": "worker_observed",
    }
    return {
        "decision": "worker_declined",
        "reason": reasons.get(str(kind), "worker_non_action"),
        "phase": "worker_publication",
        "final_worker_response_kind": kind,
    }


def _hidden_marker_leaks(value: Any) -> bool:
    rendered = json.dumps(value, sort_keys=True, default=str)
    forbidden = (
        "PROBE_REPAIR_CODE",
        "A = 42.0",
        "BindStepSpec.base_params",
        "repair_same_component.bind.base_params",
    )
    return any(marker in rendered for marker in forbidden)


def _raw_component_guid_leaks(value: Any, component_guid: str) -> bool:
    if not component_guid:
        return False
    rendered = json.dumps(value, sort_keys=True, default=str)
    return component_guid.casefold() in rendered.casefold()


async def _create_scalar_fixture(
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]],
) -> dict[str, Any]:
    create_args = {
        "nickname": "LM8C_Target",
        "min": 0,
        "max": 10,
        "value": INITIAL_SCALAR_VALUE,
        "x": 20,
        "y": 80,
    }
    create_result = await tool_executor("gh_create_slider", create_args)
    if _tool_result_failed(create_result):
        raise ValueError("gh_create_slider_failed")
    if _tool_field(create_result, "created", "Created") is not True:
        raise ValueError("gh_create_slider_failed")
    component_guid = _guid_from_result(create_result)

    get_result = await tool_executor("gh_get_value", {"guid": component_guid})
    if _tool_result_failed(get_result):
        raise ValueError("gh_get_value_failed")
    if not isinstance(_tool_data(get_result), Mapping):
        raise ValueError("gh_get_value_result_invalid")
    observed = _coerce_scalar_value(_tool_field(get_result, "value", "Value"))

    editable_contract = {
        "label": "LM8C_Target",
        "value_type": "number",
        "current_value": observed,
        "identity_projection": True,
    }
    receipt = {
        "observed_output_value": observed,
        "scalar_anchor": {
            "internal_component_guid": component_guid,
            "editable_value_contract": dict(editable_contract),
        },
    }
    visible_receipt = {
        "observed_output_value": observed,
        "scalar_anchor": {
            "guid_present": True,
            "component_guid_sha256": _guid_sha256(component_guid),
            "editable_value_contract": dict(editable_contract),
        },
    }
    live_summary = {
        "tool_name": "gh_create_slider",
        "created": True,
        "component_guid": component_guid,
        "component_guid_sha256": _guid_sha256(component_guid),
        "nickname": create_args["nickname"],
        "initial_value": INITIAL_SCALAR_VALUE,
        "observed_value": observed,
        "receipt_sha256": _receipt_sha256(
            {"create": create_result, "get_value": get_result}
        ),
    }
    return {
        "component_guid": component_guid,
        "observed_output_value": observed,
        "receipt": receipt,
        "visible_receipt": visible_receipt,
        "live_create_scalar_summary": live_summary,
    }


async def _dispatch_set_value_and_verify(
    *,
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]],
    component_guid: str,
    worker_value: float | int,
    expected_value: float | int,
) -> dict[str, Any]:
    set_result = await tool_executor(
        "gh_set_value",
        {"guid": component_guid, "value": worker_value},
    )
    set_summary = {
        "tool_name": "gh_set_value",
        "component_guid": component_guid,
        "component_guid_sha256": _guid_sha256(component_guid),
        "worker_action_value": worker_value,
        "success": not _tool_result_failed(set_result),
        "receipt_sha256": _receipt_sha256(set_result),
    }
    if _tool_result_failed(set_result):
        return {
            "live_set_value_summary": set_summary,
            "verify_scalar_output_summary": None,
            "decision": {
                "decision": "rejected",
                "reason": "gh_set_value_failed",
                "phase": "live_set_value",
            },
        }

    get_result = await tool_executor("gh_get_value", {"guid": component_guid})
    invalid_value = False
    if _tool_result_failed(get_result) or not isinstance(_tool_data(get_result), Mapping):
        observed = None
        matched = False
    else:
        try:
            observed = _coerce_scalar_value(_tool_field(get_result, "value", "Value"))
        except ValueError:
            observed = None
            matched = False
            invalid_value = True
        else:
            matched = abs(float(observed) - float(expected_value)) <= SCALAR_TOLERANCE
    verify_summary = {
        "tool_name": "gh_get_value",
        "component_guid_sha256": _guid_sha256(component_guid),
        "expected_output_value": expected_value,
        "observed_output_value": observed,
        "tolerance": SCALAR_TOLERANCE,
        "matched": matched,
        "receipt_sha256": _receipt_sha256(get_result),
    }
    return {
        "live_set_value_summary": set_summary,
        "verify_scalar_output_summary": verify_summary,
        "decision": {
            "decision": "accepted" if matched else "rejected",
            "reason": (
                "verify_scalar_output_succeeded"
                if matched
                else "verify_scalar_output_invalid_value"
                if invalid_value
                else "verify_scalar_output_failed"
            ),
            "phase": "verify_scalar_output",
            "expected_output_value": expected_value,
            "observed_output_after": observed,
            "scalar_tolerance": SCALAR_TOLERANCE,
        },
    }


def _worker_action_context(
    response_payload: Mapping[str, Any], excerpt_chars: int
) -> dict[str, Any]:
    action_input = response_payload.get("input")
    rendered = json.dumps(action_input, sort_keys=True, default=str)
    sanitized_rendered = json.dumps(
        _sanitize_decision_excerpt_value(action_input),
        sort_keys=True,
        default=str,
    )
    return {
        "worker_action_input_sha256": _sha256_text(rendered),
        "worker_action_input_excerpt": sanitized_rendered[:excerpt_chars],
    }


def _action_context(
    response_payload: Mapping[str, Any], excerpt_chars: int
) -> dict[str, Any]:
    return _worker_action_context(response_payload, excerpt_chars)


def _run_probe(
    *,
    model: str,
    endpoint: str,
    temperature: float,
    timeout_s: float,
    excerpt_chars: int,
    run_root: str | Path,
    canonical_evidence: bool,
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]] | None = None,
    publication_runner: Callable[..., Any] | None = None,
) -> Path:
    run_dir = _new_run_dir(run_root)
    _write_json(
        run_dir / "manifest.json",
        _manifest(
            model=model,
            endpoint=endpoint,
            temperature=temperature,
            canonical_evidence=canonical_evidence,
        ),
    )
    if tool_executor is None:
        from rook.server import _mcp_tool_executor

        tool_executor = _mcp_tool_executor
    publisher = publication_runner or run_two_pass_worker_publication

    ok, preflight_reason, preflight_summaries = asyncio.run(
        _run_preflight(tool_executor)
    )
    if not ok:
        _write_json_value(run_dir / "preflight_summary.json", preflight_summaries)
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="preflight_failed",
                reason=str(preflight_reason),
                phase="preflight",
                canonical_evidence=canonical_evidence,
            ),
        )
        return run_dir

    try:
        fixture = asyncio.run(_create_scalar_fixture(tool_executor))
    except Exception as exc:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason=f"scalar_fixture_failed:{type(exc).__name__}",
                phase="live_fixture",
                canonical_evidence=canonical_evidence,
            ),
        )
        return run_dir

    component_guid = fixture["component_guid"]
    _write_json(
        run_dir / "live_create_scalar_summary.json",
        fixture["live_create_scalar_summary"],
    )
    _write_json_value(run_dir / "scalar_fixture_contract.json", _scalar_contract_payload())

    graph = _graph_from_scalar_receipt(fixture["receipt"])
    try:
        runtime = _scalar_runtime_context(
            graph=graph,
            workflow_contract_payload=_scalar_contract_payload(),
            convention_packets=(),
        )
    except Exception as exc:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason=f"scalar_runtime_readiness_failed:{type(exc).__name__}",
                phase="scalar_runtime_ready",
                canonical_evidence=canonical_evidence,
                live_fixture_created=True,
                component_guid=component_guid,
            ),
        )
        return run_dir

    _write_json_value(run_dir / "scalar_source_routing.json", runtime["routing_artifact"])
    _write_json(run_dir / "static_routing_validation.json", runtime["static_routing_report"])
    if runtime["scalar_runtime_ready"] is not True:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason="scalar_runtime_not_ready",
                phase="scalar_runtime_ready",
                canonical_evidence=canonical_evidence,
                scalar_runtime_ready=False,
                live_fixture_created=True,
                component_guid=component_guid,
            ),
        )
        return run_dir

    _write_json_value(
        run_dir / "scalar_sources.json",
        {
            "expected_output_contract": runtime[
                "sources"
            ].expected_output_contract.__dict__,
            "receipt_observation": runtime["sources"].receipt_observation.__dict__,
            "fixture_anchor": runtime["sources"].fixture_anchor.__dict__,
        },
    )
    _write_json_value(run_dir / "acceptance_criteria_packet.json", runtime["packet"])
    _write_json(run_dir / "worker_visible_acceptance_criteria.json", runtime["worker_visible"])
    request_payload = _build_local_turn_payload(
        graph=graph,
        packet=runtime["packet"],
        worker_visible=runtime["worker_visible"],
    )
    _write_json_value(run_dir / "worker_request_payload.json", request_payload)

    publication = publisher(
        request_payload,
        model=model,
        endpoint=endpoint,
        temperature=temperature,
        timeout_s=timeout_s,
        excerpt_chars=excerpt_chars,
    )
    if _hidden_marker_leaks(publication.row) or _hidden_marker_leaks(
        publication.response_payload
    ):
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="publication_failed",
                reason="worker_publication_hidden_answer_leak",
                phase="worker_publication",
                canonical_evidence=canonical_evidence,
                scalar_runtime_ready=True,
                live_fixture_created=True,
                worker_publication_ran=True,
                component_guid=component_guid,
            ),
        )
        return run_dir

    if _raw_component_guid_leaks(
        publication.row, component_guid
    ) or _raw_component_guid_leaks(publication.response_payload, component_guid):
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="publication_failed",
                reason="worker_publication_guid_leak",
                phase="worker_publication",
                canonical_evidence=canonical_evidence,
                scalar_runtime_ready=True,
                live_fixture_created=True,
                worker_publication_ran=True,
                component_guid=component_guid,
            ),
        )
        return run_dir

    _write_json(run_dir / "worker_publication_row.json", publication.row)
    worker_decision = _decision_from_publication(
        publication.row, publication.response_payload
    )
    if worker_decision is not None:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision=worker_decision["decision"],
                reason=worker_decision["reason"],
                phase=worker_decision["phase"],
                canonical_evidence=canonical_evidence,
                scalar_runtime_ready=True,
                live_fixture_created=True,
                worker_publication_ran=True,
                component_guid=component_guid,
                extra={
                    key: value
                    for key, value in worker_decision.items()
                    if key not in {"decision", "reason", "phase"}
                },
            ),
        )
        return run_dir

    response_payload = publication.response_payload
    _write_json(run_dir / "worker_action.json", response_payload)
    action_context = _action_context(response_payload, excerpt_chars)
    apply_result = apply_gh_scalar_value_action_to_node(
        graph,
        WORKER_NODE_ID,
        action_id=str(response_payload.get("action_id") or ""),
        action_input=response_payload.get("input"),
        anchor_binding={"component_guid": component_guid},
    )
    if apply_result.applied is not True:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="rejected",
                reason=f"worker_action_apply_failed:{apply_result.reason}",
                phase="worker_action_apply",
                canonical_evidence=canonical_evidence,
                scalar_runtime_ready=True,
                live_fixture_created=True,
                worker_publication_ran=True,
                component_guid=component_guid,
                extra=action_context,
            ),
        )
        return run_dir

    params = apply_result.graph.nodes[WORKER_NODE_ID].metadata[EXECUTION_PARAMS_KEY]
    dispatch = asyncio.run(
        _dispatch_set_value_and_verify(
            tool_executor=tool_executor,
            component_guid=str(params["guid"]),
            worker_value=params["value"],
            expected_value=EXPECTED_OUTPUT_VALUE,
        )
    )
    _write_json(run_dir / "live_set_value_summary.json", dispatch["live_set_value_summary"])
    if dispatch["verify_scalar_output_summary"] is not None:
        _write_json(
            run_dir / "verify_scalar_output_summary.json",
            dispatch["verify_scalar_output_summary"],
        )
    final = dispatch["decision"]
    _write_json(
        run_dir / "decision.json",
        _decision_record(
            decision=final["decision"],
            reason=final["reason"],
            phase=final["phase"],
            canonical_evidence=canonical_evidence,
            scalar_runtime_ready=True,
            live_fixture_created=True,
            worker_publication_ran=True,
            live_set_value_dispatched=True,
            verify_scalar_output_ran=dispatch["verify_scalar_output_summary"]
            is not None,
            component_guid=component_guid,
            extra={
                **action_context,
                **{
                    key: value
                    for key, value in final.items()
                    if key not in {"decision", "reason", "phase"}
                },
            },
        ),
    )
    return run_dir


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    if not _canonical_evidence_is_valid(args):
        print("invalid_canonical_evidence", file=sys.stderr)
        raise SystemExit(2)
    run_dir = _run_probe(
        model=args.model,
        endpoint=args.endpoint,
        temperature=args.temperature,
        timeout_s=args.timeout_s,
        excerpt_chars=args.excerpt_chars,
        run_root=args.run_dir,
        canonical_evidence=args.canonical_evidence,
    )
    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    print(
        "LM8C GH scalar expectation live splice probe complete "
        f"run_dir={run_dir} "
        f"decision={decision.get('decision')} "
        f"reason={decision.get('reason')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
