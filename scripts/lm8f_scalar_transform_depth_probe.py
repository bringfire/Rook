#!/usr/bin/env python
"""LM8F GH scalar transform depth pressure live probe."""

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
from rook.agent.gh_scalar_transform_expectation_acceptance_criteria import (  # noqa: E402
    assemble_gh_scalar_transform_expectation_packet,
    project_gh_scalar_transform_expectation_legacy,
)
from rook.agent.gh_scalar_transform_expectation_sources import (  # noqa: E402
    TRANSFORM_CONVENTION_SOURCE_PATH,
    TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
    TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
    TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH,
    TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
    TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
    TRANSFORM_PROJECTION_SOURCE_PATH,
    extract_gh_scalar_transform_expectation_sources,
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
from rook.agent.plan_graph_gh_scalar_value_apply import (  # noqa: E402,F401
    apply_gh_scalar_value_action_to_node,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY  # noqa: E402,F401
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


SCRIPT_SCHEMA = "rook.lm8f_scalar_transform_depth_probe:v1"
DECISION_SCHEMA = "rook.lm8f_decision:v1"
DEFAULT_MODEL = "gemma4:12b-it-qat"
DEFAULT_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_TEMPERATURE = 0
DEFAULT_TIMEOUT_S = 120
DEFAULT_EXCERPT_CHARS = 1200
INITIAL_EDITABLE_VALUE = 2.0
OFFSET_VALUE = 1.5
INITIAL_OBSERVED_OUTPUT = 3.5
EXPECTED_OUTPUT_VALUE = 7.5
SCALAR_TOLERANCE = 1e-9
WORKER_NODE_ID = "set_scalar_value"
CREATE_NODE_ID = "create_scalar_transform"
VERIFY_NODE_ID = "verify_scalar_transform_output"
ACTION_ID = "draft_gh_set_value_params"


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM8F GH scalar transform depth pressure live probe."
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
    run_dir = Path(run_root) / f"lm8f-{timestamp}-{_git_short_sha()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _fingerprint_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _guid_sha256(guid: str | None) -> str | None:
    return None if guid is None else _sha256_text(guid)


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


def _scalar_transform_source_routing_artifact() -> dict[str, Any]:
    return {
        "schema": "rook.worker_visible_source_routing:v1",
        "routes": [
            {
                "node_id": WORKER_NODE_ID,
                "visible_sources": [
                    {
                        "route_id": "transform_expected_output_value",
                        "source_class": "expected_output_contract",
                        "source_path": TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "transform_offset_value",
                        "source_class": "expected_output_contract",
                        "source_path": TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "transform_projection",
                        "source_class": "expected_output_contract",
                        "source_path": TRANSFORM_PROJECTION_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "transform_observed_output",
                        "source_class": "receipt_observation",
                        "source_path": TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "transform_editable_value",
                        "source_class": "receipt_observation",
                        "source_path": TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "transform_editable_target_contract",
                        "source_class": "fixture_anchor",
                        "source_path": TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "transform_set_value_convention",
                        "source_class": "convention",
                        "source_path": TRANSFORM_CONVENTION_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": False,
                    },
                ],
            }
        ],
    }


def _scalar_transform_contract_payload() -> dict[str, Any]:
    return {
        "rules": {
            VERIFY_NODE_ID: {
                "expected_output_value": EXPECTED_OUTPUT_VALUE,
                "offset_value": OFFSET_VALUE,
                "projection": {
                    "projection_id": "editable_plus_offset",
                    "description": "observed_output = editable_value + offset_value",
                    "editable_variable": "editable_value",
                    "offset_variable": "offset_value",
                    "output_variable": "observed_output",
                },
            }
        }
    }


def _graph_from_transform_receipt(receipt: Mapping[str, Any]) -> PlanGraph:
    return PlanGraph(
        nodes={
            CREATE_NODE_ID: PlanGraphNode(
                id=CREATE_NODE_ID,
                intent="Create GH scalar transform fixture",
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
                intent="Verify GH scalar transform output",
                execution_ref="gh_inspect_output:v1",
                status="pending",
                is_terminal=True,
            ),
        },
        memory=GraphMemory(),
    )


def _projection_invariant_holds(sources: Any) -> bool:
    expected_observed = (
        float(sources.editable_observation.value) + float(sources.offset_contract.value)
    )
    return (
        abs(float(sources.observed_output.value) - expected_observed) <= SCALAR_TOLERANCE
    )


def _scalar_runtime_context(
    *,
    graph: PlanGraph,
    workflow_contract_payload: Mapping[str, Any],
    convention_packets: tuple[WorkerKnowledgePacket, ...],
) -> dict[str, Any]:
    routing_artifact = _scalar_transform_source_routing_artifact()
    static_report = validate_worker_visible_source_routing(routing_artifact)
    static_report_json = _routing_report_json(static_report)
    if static_report.valid is not True:
        return {
            "scalar_runtime_ready": False,
            "routing_artifact": routing_artifact,
            "static_routing_report": static_report_json,
        }
    sources = extract_gh_scalar_transform_expectation_sources(
        workflow_contract_payload=workflow_contract_payload,
        graph=graph,
        convention_packets=convention_packets,
    )
    if not _projection_invariant_holds(sources):
        raise ValueError("projection_invariant_mismatch")
    packet = assemble_gh_scalar_transform_expectation_packet(sources)
    worker_visible = project_gh_scalar_transform_expectation_legacy(packet)
    return {
        "scalar_runtime_ready": True,
        "routing_artifact": routing_artifact,
        "static_routing_report": static_report_json,
        "sources": sources,
        "packet": packet,
        "worker_visible": worker_visible,
    }


def _scalar_transform_scaffold(graph: PlanGraph) -> CompiledWorkflowScaffold:
    normalized_contract = {
        "schema": "rook.workflow_contract:v1",
        "workflow_id": "lm8f-gh-scalar-transform",
    }
    contract_fingerprint = _fingerprint_json(normalized_contract).removeprefix(
        "sha256:"
    )
    snapshot = WorkflowContractSnapshot(
        workflow_id="lm8f-gh-scalar-transform",
        normalized_contract=normalized_contract,
        contract_fingerprint=contract_fingerprint,
    )
    compile_record = WorkflowCompileRecord(
        workflow_id="lm8f-gh-scalar-transform",
        compiler_id="lm8f.script_local_transform_scaffold:v1",
        contract_schema="rook.workflow_contract:v1",
        contract_fingerprint_algorithm="sha256",
        contract_fingerprint=contract_fingerprint,
        provider_id="lm8f.script_local_provider:v1",
        expected_template_id="gh_scalar_transform_expectation",
        selected_template_id="gh_scalar_transform_expectation",
        graph_node_ids=tuple(sorted(graph.nodes)),
        initial_param_node_ids=(),
        rule_node_ids=(WORKER_NODE_ID, VERIFY_NODE_ID),
        terminal_node_ids=(VERIFY_NODE_ID,),
        expected_refs=((WORKER_NODE_ID, "gh_set_value:v1"),),
        step_kinds_by_rule=(),
        max_steps=4,
    )
    return CompiledWorkflowScaffold(
        workflow_id="lm8f-gh-scalar-transform",
        graph=graph,
        provider=object(),
        max_steps=4,
        metadata={},
        rules=(),
        steps=(),
        contract_snapshot=snapshot,
        compile_record=compile_record,
    )


def _scalar_transform_worker_evidence_packet(
    *,
    packet: Mapping[str, Any],
    worker_visible: Mapping[str, Any],
) -> WorkerKnowledgePacket:
    fields = packet["fields"]
    return WorkerKnowledgePacket(
        packet_id="gh_scalar_transform_expectation_evidence",
        kind="evidence",
        title="GH scalar transform expectation evidence",
        content={
            "source": "gh_scalar_transform_expectation",
            "trust": "high",
            "state": "post_scalar_transform_fixture_pre_worker",
            "fields": {
                "current_editable_value": fields["current_editable_value"],
                "offset_value": fields["offset_value"],
                "current_observed_output": fields["current_observed_output"],
                "expected_output_value": fields["expected_output_value"],
                "projection": dict(fields["projection"]),
                "editable_value_contract": dict(fields["editable_value_contract"]),
                "acceptance_criteria": dict(worker_visible),
                "recommended_action_id": ACTION_ID,
                "action_selection_contract": dict(fields["action_selection_contract"]),
            },
        },
    )


def _scalar_transform_allowed_action() -> WorkerAllowedAction:
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
        _scalar_transform_scaffold(graph),
        graph,
        records=(),
        supply_records=(),
        current_node_id=WORKER_NODE_ID,
        knowledge=(
            _scalar_transform_worker_evidence_packet(
                packet=packet,
                worker_visible=worker_visible,
            ),
        ),
        allowed_actions=(_scalar_transform_allowed_action(),),
    )
    return dict(render_local_worker_turn_request_payload(context))


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
        "initial_editable_value": INITIAL_EDITABLE_VALUE,
        "offset_value": OFFSET_VALUE,
        "initial_observed_output": INITIAL_OBSERVED_OUTPUT,
        "expected_output_value": EXPECTED_OUTPUT_VALUE,
        "projection_id": "editable_plus_offset",
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


def _inspect_output_scalar_value(result: Any) -> float | int:
    if _tool_result_failed(result):
        raise ValueError("inspect output scalar result failed")
    data = _tool_data(result)
    if not isinstance(data, Mapping):
        raise ValueError("inspect output scalar data missing")
    preview = data.get("preview")
    if isinstance(preview, Sequence) and not isinstance(
        preview, (str, bytes, bytearray)
    ):
        if len(preview) != 1:
            raise ValueError("inspect output scalar preview must contain one value")
        try:
            return _coerce_scalar_value(preview[0])
        except ValueError as exc:
            raise ValueError("inspect output scalar value invalid") from exc
    value = _tool_field(result, "value", "Value")
    try:
        return _coerce_scalar_value(value)
    except ValueError as exc:
        raise ValueError("inspect output scalar value invalid") from exc


def _addition_proxy_guid_from_library(result: Any) -> str:
    data = _tool_data(result)
    components = []
    if isinstance(result, Mapping) and isinstance(result.get("components"), Sequence):
        components.extend(result["components"])
    if isinstance(data, Mapping) and isinstance(data.get("components"), Sequence):
        components.extend(data["components"])
    for component in components:
        if not isinstance(component, Mapping):
            continue
        if (
            component.get("name") == "Addition"
            and component.get("nickName") == "A+B"
            and component.get("category") == "Maths"
        ):
            guid = component.get("guid") or component.get("Guid")
            if isinstance(guid, str) and guid.strip():
                return guid
    raise ValueError("gh_library_addition_not_found")


async def _create_transform_fixture(
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]],
) -> dict[str, Any]:
    library_result = await tool_executor("gh_library", {"search": "addition", "limit": 20})
    if _tool_result_failed(library_result):
        raise ValueError("gh_library_failed")
    addition_proxy_guid = _addition_proxy_guid_from_library(library_result)

    editable_result = await tool_executor(
        "gh_create_slider",
        {
            "nickname": "LM8F_Editable",
            "min": 0,
            "max": 10,
            "value": INITIAL_EDITABLE_VALUE,
            "x": 20,
            "y": 80,
        },
    )
    if _tool_result_failed(editable_result) or _tool_field(
        editable_result, "created", "Created"
    ) is not True:
        raise ValueError("gh_create_editable_slider_failed")
    editable_guid = _guid_from_result(editable_result)

    offset_result = await tool_executor(
        "gh_create_slider",
        {
            "nickname": "LM8F_Offset",
            "min": 0,
            "max": 10,
            "value": OFFSET_VALUE,
            "x": 20,
            "y": 180,
        },
    )
    if _tool_result_failed(offset_result) or _tool_field(
        offset_result, "created", "Created"
    ) is not True:
        raise ValueError("gh_create_offset_slider_failed")
    offset_guid = _guid_from_result(offset_result)

    addition_result = await tool_executor(
        "gh_create_component",
        {"guid": addition_proxy_guid, "x": 280, "y": 120},
    )
    if _tool_result_failed(addition_result) or _tool_field(
        addition_result, "created", "Created"
    ) is not True:
        raise ValueError("gh_create_addition_failed")
    addition_guid = _guid_from_result(addition_result)

    connect_a_result = await tool_executor(
        "gh_connect",
        {
            "sourceGuid": editable_guid,
            "targetGuid": addition_guid,
            "targetParam": "A",
        },
    )
    if _tool_result_failed(connect_a_result):
        raise ValueError("gh_connect_editable_failed")

    connect_b_result = await tool_executor(
        "gh_connect",
        {
            "sourceGuid": offset_guid,
            "targetGuid": addition_guid,
            "targetParam": "B",
        },
    )
    if _tool_result_failed(connect_b_result):
        raise ValueError("gh_connect_offset_failed")

    solve_result = await tool_executor("gh_solve", {"delay": 25})
    if _tool_result_failed(solve_result):
        raise ValueError("gh_solve_failed")

    editable_value_result = await tool_executor("gh_get_value", {"guid": editable_guid})
    if _tool_result_failed(editable_value_result):
        raise ValueError("gh_get_value_failed")
    editable_value = _coerce_scalar_value(
        _tool_field(editable_value_result, "value", "Value")
    )

    inspect_result = await tool_executor(
        "gh_inspect_output",
        {"guid": addition_guid, "param": "R"},
    )
    observed_output_value = _inspect_output_scalar_value(inspect_result)

    if abs(float(editable_value) - float(INITIAL_EDITABLE_VALUE)) > SCALAR_TOLERANCE:
        raise ValueError("initial_editable_value_mismatch")
    if (
        abs(float(observed_output_value) - float(INITIAL_OBSERVED_OUTPUT))
        > SCALAR_TOLERANCE
    ):
        raise ValueError("initial_observed_output_mismatch")

    receipt = {
        "editable_value": editable_value,
        "observed_output_value": observed_output_value,
        "offset_value": OFFSET_VALUE,
        "scalar_anchor": {
            "internal_component_guid": editable_guid,
            "editable_value_contract": {
                "label": "LM8F_Editable",
                "value_type": "number",
                "current_value": editable_value,
                "projection_id": "editable_plus_offset",
            },
        },
    }
    visible_receipt = {
        "editable_value": editable_value,
        "observed_output_value": observed_output_value,
        "offset_value": OFFSET_VALUE,
        "scalar_anchor": {
            "guid_present": True,
            "component_guid_sha256": _guid_sha256(editable_guid),
            "editable_value_contract": {
                "label": "LM8F_Editable",
                "value_type": "number",
                "current_value": editable_value,
                "projection_id": "editable_plus_offset",
            },
        },
        "offset_component": {
            "guid_present": True,
            "component_guid_sha256": _guid_sha256(offset_guid),
        },
        "addition_component": {
            "guid_present": True,
            "component_guid_sha256": _guid_sha256(addition_guid),
        },
    }
    fixture_setup_summary = {
        "tool_name": "gh_create_component",
        "editable_component_guid": editable_guid,
        "editable_component_guid_sha256": _guid_sha256(editable_guid),
        "offset_component_guid": offset_guid,
        "offset_component_guid_sha256": _guid_sha256(offset_guid),
        "addition_component_guid": addition_guid,
        "addition_component_guid_sha256": _guid_sha256(addition_guid),
        "editable_value": editable_value,
        "offset_value": OFFSET_VALUE,
        "observed_output_value": observed_output_value,
        "receipt_sha256": _fingerprint_json(
            {
                "gh_library": library_result,
                "gh_create_slider_editable": editable_result,
                "gh_create_slider_offset": offset_result,
                "gh_create_component": addition_result,
                "gh_connect_editable": connect_a_result,
                "gh_connect_offset": connect_b_result,
                "gh_solve": solve_result,
                "gh_get_value": editable_value_result,
                "gh_inspect_output": inspect_result,
            }
        ),
    }
    return {
        "editable_component_guid": editable_guid,
        "offset_component_guid": offset_guid,
        "addition_component_guid": addition_guid,
        "editable_value": editable_value,
        "observed_output_value": observed_output_value,
        "receipt": receipt,
        "visible_receipt": visible_receipt,
        "fixture_setup_summary": fixture_setup_summary,
    }
