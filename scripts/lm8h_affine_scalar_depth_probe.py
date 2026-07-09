#!/usr/bin/env python
"""LM8H GH affine scalar depth live probe."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
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
from rook.agent.gh_affine_scalar_transform_expectation_acceptance_criteria import (  # noqa: E402
    assemble_gh_affine_scalar_transform_expectation_packet,
    project_gh_affine_scalar_transform_expectation_legacy,
)
from rook.agent.gh_affine_scalar_transform_expectation_sources import (  # noqa: E402
    AFFINE_CONVENTION_SOURCE_PATH,
    AFFINE_EDITABLE_VALUE_SOURCE_PATH,
    AFFINE_EXPECTED_OUTPUT_SOURCE_PATH,
    AFFINE_FACTOR_VALUE_SOURCE_PATH,
    AFFINE_FIXTURE_ANCHOR_SOURCE_PATH,
    AFFINE_OBSERVED_OUTPUT_SOURCE_PATH,
    AFFINE_OFFSET_VALUE_SOURCE_PATH,
    AFFINE_PROJECTION_SOURCE_PATH,
    EXPECTED_AFFINE_PROJECTION,
    extract_gh_affine_scalar_transform_expectation_sources,
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


SCRIPT_SCHEMA = "rook.lm8h_affine_scalar_depth_probe:v1"
DECISION_SCHEMA = "rook.lm8h_decision:v1"
DEFAULT_MODEL = "gemma4:12b-it-qat"
DEFAULT_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_TEMPERATURE = 0
DEFAULT_TIMEOUT_S = 120
DEFAULT_EXCERPT_CHARS = 1200
INITIAL_EDITABLE_VALUE = 2.0
FACTOR_VALUE = 2.0
OFFSET_VALUE = 1.5
INITIAL_OBSERVED_OUTPUT = 5.5
EXPECTED_OUTPUT_VALUE = 7.5
SCALAR_TOLERANCE = 1e-9
VERIFY_INSPECT_ATTEMPTS = 3
VERIFY_INSPECT_DELAY_S = 0.1
WORKER_NODE_ID = "set_scalar_value"
CREATE_NODE_ID = "create_affine_scalar_transform"
VERIFY_NODE_ID = "verify_affine_scalar_transform_output"
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


class FixtureSetupFailure(ValueError):
    def __init__(
        self,
        *,
        step: str,
        tool_name: str,
        failure_reason: str,
        result: Any,
    ) -> None:
        super().__init__(failure_reason)
        self.step = step
        self.tool_name = tool_name
        self.failure_reason = failure_reason
        self.result = result


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM8H GH affine scalar depth live probe."
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
    base_dir = Path(run_root) / f"lm8h-{timestamp}-{_git_short_sha()}"
    suffix = 0
    while True:
        run_dir = (
            base_dir
            if suffix == 0
            else base_dir.parent / f"{base_dir.name}-{suffix:03d}"
        )
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            suffix += 1
            continue
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


def _coerce_scalar_value(value: Any) -> float | int:
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


def _guid_from_result(result: Any) -> str:
    guid = _tool_field(result, "guid", "Guid", "component_guid")
    if not isinstance(guid, str) or not guid.strip():
        raise ValueError("tool_result_guid_missing")
    return guid.strip()


def _inspect_output_scalar_value(result: Any) -> float | int:
    if _tool_result_failed(result):
        raise ValueError("inspect_output_scalar_result_failed")
    data = _tool_data(result)
    if not isinstance(data, Mapping):
        raise ValueError("inspect_output_scalar_data_missing")
    preview = data.get("preview")
    if isinstance(preview, Sequence) and not isinstance(
        preview, (str, bytes, bytearray)
    ):
        if len(preview) != 1:
            raise ValueError("inspect_output_scalar_preview_invalid")
        try:
            return _coerce_scalar_value(preview[0])
        except ValueError as exc:
            raise ValueError("inspect_output_scalar_value_invalid") from exc
    value = _tool_field(result, "value", "Value")
    try:
        return _coerce_scalar_value(value)
    except ValueError as exc:
        raise ValueError("inspect_output_scalar_value_invalid") from exc


def _fixture_reason_from_exception(exc: Exception) -> str:
    reason = str(exc).strip() or type(exc).__name__
    return re.sub(r"[^a-zA-Z0-9]+", "_", reason).strip("_").casefold()


async def _fixture_tool_call(
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]],
    *,
    step: str,
    tool_name: str,
    args: Mapping[str, Any],
) -> Any:
    try:
        return await tool_executor(tool_name, args)
    except Exception as exc:
        raise FixtureSetupFailure(
            step=step,
            tool_name=tool_name,
            failure_reason=f"{tool_name}_exception:{type(exc).__name__}",
            result={"exception": type(exc).__name__},
        ) from exc


def _raise_fixture_failure(
    *,
    step: str,
    tool_name: str,
    failure_reason: str,
    result: Any,
) -> None:
    raise FixtureSetupFailure(
        step=step,
        tool_name=tool_name,
        failure_reason=failure_reason,
        result=result,
    )


def _library_components(result: Any) -> list[Mapping[str, Any]]:
    components: list[Mapping[str, Any]] = []
    if isinstance(result, Mapping):
        root_components = result.get("components")
        if isinstance(root_components, Sequence):
            components.extend(
                item for item in root_components if isinstance(item, Mapping)
            )
    data = _tool_data(result)
    if isinstance(data, Mapping):
        nested_components = data.get("components")
        if isinstance(nested_components, Sequence):
            components.extend(
                item for item in nested_components if isinstance(item, Mapping)
            )
    return components


def _component_proxy_guid(component: Mapping[str, Any]) -> str:
    for key in ("guid", "Guid", "proxyGuid", "ProxyGuid"):
        value = component.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError("tool_result_guid_missing")


def _active_component_proxy_guid_from_library(result: Any, component_name: str) -> str:
    components = _library_components(result)
    active_exact = [
        component
        for component in components
        if str(component.get("name", "")).casefold() == component_name.casefold()
        and component.get("deprecated") is not True
    ]
    if not active_exact:
        raise ValueError(f"active_{component_name.casefold()}_component_missing")
    return _component_proxy_guid(active_exact[0])


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


def _result_shape(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        shape: dict[str, Any] = {
            "type": "object",
            "keys": sorted(str(key) for key in value.keys()),
        }
        data = value.get("data")
        if isinstance(data, Mapping):
            shape["data"] = _result_shape(data)
        return shape
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return {"type": "array", "length": len(value)}
    return {"type": type(value).__name__}


def _first_guid_value(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key in ("guid", "Guid", "proxyGuid", "ProxyGuid"):
            nested_value = value.get(key)
            if isinstance(nested_value, str) and nested_value.strip():
                return nested_value.strip()
        data = value.get("data")
        if isinstance(data, Mapping):
            return _first_guid_value(data)
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for item in value:
            nested_guid = _first_guid_value(item)
            if nested_guid is not None:
                return nested_guid
    return None


def _fixture_failure_summary(
    failure: FixtureSetupFailure, *, excerpt_chars: int
) -> dict[str, Any]:
    sanitized = _sanitize_decision_excerpt_value(failure.result)
    rendered = json.dumps(sanitized, sort_keys=True, default=str)
    guid = _first_guid_value(failure.result)
    return {
        "schema": "rook.lm8h_fixture_failure_summary:v1",
        "step": failure.step,
        "tool_name": failure.tool_name,
        "failure_reason": failure.failure_reason,
        "result_sha256": _fingerprint_json(failure.result),
        "result_excerpt": rendered[:excerpt_chars],
        "result_shape": _result_shape(failure.result),
        "guid_present": guid is not None,
        "guid_sha256": _guid_sha256(guid),
    }


def _bounded_tool_result_artifact(value: Any, *, excerpt_chars: int) -> dict[str, Any]:
    sanitized = _sanitize_decision_excerpt_value(value)
    rendered = json.dumps(sanitized, sort_keys=True, default=str)
    return {
        "result_sha256": _fingerprint_json(value),
        "result_excerpt": rendered[:excerpt_chars],
        "result_shape": _result_shape(sanitized),
    }


def _verifier_attempt_summary(
    *,
    attempt_index: int,
    result: Any = None,
    exception: Exception | None = None,
    observed_output_value: float | int | None = None,
    matched: bool = False,
    failure_reason: str | None = None,
    excerpt_chars: int = DEFAULT_EXCERPT_CHARS,
) -> dict[str, Any]:
    if exception is not None:
        artifact_value = {"exception": type(exception).__name__}
        summary = {
            "attempt_index": attempt_index,
            "reported_success": False,
            "observed_output_value": None,
            "matched": False,
            "failure_reason": failure_reason
            or f"gh_inspect_output_exception:{type(exception).__name__}",
            "exception": type(exception).__name__,
        }
    else:
        tool_failed = _tool_result_failed(result)
        artifact_value = result
        summary = {
            "attempt_index": attempt_index,
            "reported_success": not tool_failed,
            "observed_output_value": observed_output_value,
            "matched": matched,
            "failure_reason": failure_reason,
        }
    summary.update(
        _bounded_tool_result_artifact(artifact_value, excerpt_chars=excerpt_chars)
    )
    return summary


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


def _affine_scalar_source_routing_artifact() -> dict[str, Any]:
    return {
        "schema": "rook.worker_visible_source_routing:v1",
        "routes": [
            {
                "node_id": WORKER_NODE_ID,
                "visible_sources": [
                    {
                        "route_id": "affine_scalar_expected_output",
                        "source_class": "expected_output_contract",
                        "source_path": AFFINE_EXPECTED_OUTPUT_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_factor_value",
                        "source_class": "expected_output_contract",
                        "source_path": AFFINE_FACTOR_VALUE_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_offset_value",
                        "source_class": "expected_output_contract",
                        "source_path": AFFINE_OFFSET_VALUE_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_projection",
                        "source_class": "expected_output_contract",
                        "source_path": AFFINE_PROJECTION_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_current_output",
                        "source_class": "receipt_observation",
                        "source_path": AFFINE_OBSERVED_OUTPUT_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_current_editable_value",
                        "source_class": "receipt_observation",
                        "source_path": AFFINE_EDITABLE_VALUE_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_editable_target_contract",
                        "source_class": "fixture_anchor",
                        "source_path": AFFINE_FIXTURE_ANCHOR_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "affine_scalar_set_value_convention",
                        "source_class": "convention",
                        "source_path": AFFINE_CONVENTION_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": False,
                    },
                ],
            }
        ],
    }


def _affine_scalar_contract_payload() -> dict[str, Any]:
    return {
        "rules": {
            VERIFY_NODE_ID: {
                "expected_output_value": EXPECTED_OUTPUT_VALUE,
                "factor_value": FACTOR_VALUE,
                "offset_value": OFFSET_VALUE,
                "projection": dict(EXPECTED_AFFINE_PROJECTION),
            }
        }
    }


async def _create_affine_fixture(
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]],
) -> dict[str, Any]:
    multiplication_library_result = await _fixture_tool_call(
        tool_executor,
        step="gh_library_multiplication",
        tool_name="gh_library",
        args={"search": "multiplication", "limit": 20},
    )
    if _tool_result_failed(multiplication_library_result):
        _raise_fixture_failure(
            step="gh_library_multiplication",
            tool_name="gh_library",
            failure_reason="gh_library_failed",
            result=multiplication_library_result,
        )
    try:
        multiplication_proxy_guid = _active_component_proxy_guid_from_library(
            multiplication_library_result, "Multiplication"
        )
    except ValueError:
        raise FixtureSetupFailure(
            step="gh_library_multiplication",
            tool_name="gh_library",
            failure_reason="active_multiplication_component_missing",
            result=multiplication_library_result,
        ) from None

    addition_library_result = await _fixture_tool_call(
        tool_executor,
        step="gh_library_addition",
        tool_name="gh_library",
        args={"search": "addition", "limit": 20},
    )
    if _tool_result_failed(addition_library_result):
        _raise_fixture_failure(
            step="gh_library_addition",
            tool_name="gh_library",
            failure_reason="gh_library_failed",
            result=addition_library_result,
        )
    try:
        addition_proxy_guid = _active_component_proxy_guid_from_library(
            addition_library_result, "Addition"
        )
    except ValueError:
        raise FixtureSetupFailure(
            step="gh_library_addition",
            tool_name="gh_library",
            failure_reason="active_addition_component_missing",
            result=addition_library_result,
        ) from None

    editable_result = await _fixture_tool_call(
        tool_executor,
        step="gh_create_editable_slider",
        tool_name="gh_create_slider",
        args={
            "nickname": "LM8H_Editable",
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
        _raise_fixture_failure(
            step="gh_create_editable_slider",
            tool_name="gh_create_slider",
            failure_reason="gh_create_editable_slider_failed",
            result=editable_result,
        )
    editable_guid = _guid_from_result(editable_result)

    factor_result = await _fixture_tool_call(
        tool_executor,
        step="gh_create_factor_slider",
        tool_name="gh_create_slider",
        args={
            "nickname": "LM8H_Factor",
            "min": 0,
            "max": 10,
            "value": FACTOR_VALUE,
            "x": 20,
            "y": 180,
        },
    )
    if _tool_result_failed(factor_result) or _tool_field(
        factor_result, "created", "Created"
    ) is not True:
        _raise_fixture_failure(
            step="gh_create_factor_slider",
            tool_name="gh_create_slider",
            failure_reason="gh_create_factor_slider_failed",
            result=factor_result,
        )
    factor_guid = _guid_from_result(factor_result)

    offset_result = await _fixture_tool_call(
        tool_executor,
        step="gh_create_offset_slider",
        tool_name="gh_create_slider",
        args={
            "nickname": "LM8H_Offset",
            "min": 0,
            "max": 10,
            "value": OFFSET_VALUE,
            "x": 20,
            "y": 280,
        },
    )
    if _tool_result_failed(offset_result) or _tool_field(
        offset_result, "created", "Created"
    ) is not True:
        _raise_fixture_failure(
            step="gh_create_offset_slider",
            tool_name="gh_create_slider",
            failure_reason="gh_create_offset_slider_failed",
            result=offset_result,
        )
    offset_guid = _guid_from_result(offset_result)

    multiplication_result = await _fixture_tool_call(
        tool_executor,
        step="gh_create_multiplication",
        tool_name="gh_create_component",
        args={"guid": multiplication_proxy_guid, "x": 280, "y": 130},
    )
    if _tool_result_failed(multiplication_result) or _tool_field(
        multiplication_result, "created", "Created"
    ) is not True:
        _raise_fixture_failure(
            step="gh_create_multiplication",
            tool_name="gh_create_component",
            failure_reason="gh_create_multiplication_failed",
            result=multiplication_result,
        )
    multiplication_guid = _guid_from_result(multiplication_result)

    addition_result = await _fixture_tool_call(
        tool_executor,
        step="gh_create_addition",
        tool_name="gh_create_component",
        args={"guid": addition_proxy_guid, "x": 520, "y": 180},
    )
    if _tool_result_failed(addition_result) or _tool_field(
        addition_result, "created", "Created"
    ) is not True:
        _raise_fixture_failure(
            step="gh_create_addition",
            tool_name="gh_create_component",
            failure_reason="gh_create_addition_failed",
            result=addition_result,
        )
    addition_guid = _guid_from_result(addition_result)

    connect_steps = [
        (
            "gh_connect_editable",
            {
                "sourceGuid": editable_guid,
                "targetGuid": multiplication_guid,
                "targetParam": "A",
            },
            "gh_connect_editable_failed",
        ),
        (
            "gh_connect_factor",
            {
                "sourceGuid": factor_guid,
                "targetGuid": multiplication_guid,
                "targetParam": "B",
            },
            "gh_connect_factor_failed",
        ),
        (
            "gh_connect_multiplication_to_addition",
            {
                "sourceGuid": multiplication_guid,
                "sourceParam": "R",
                "targetGuid": addition_guid,
                "targetParam": "A",
            },
            "gh_connect_multiplication_to_addition_failed",
        ),
        (
            "gh_connect_offset",
            {
                "sourceGuid": offset_guid,
                "targetGuid": addition_guid,
                "targetParam": "B",
            },
            "gh_connect_offset_failed",
        ),
    ]
    for step, args, failure_reason in connect_steps:
        connect_result = await _fixture_tool_call(
            tool_executor,
            step=step,
            tool_name="gh_connect",
            args=args,
        )
        if _tool_result_failed(connect_result):
            _raise_fixture_failure(
                step=step,
                tool_name="gh_connect",
                failure_reason=failure_reason,
                result=connect_result,
            )

    solve_result = await _fixture_tool_call(
        tool_executor,
        step="gh_solve",
        tool_name="gh_solve",
        args={"delay": 25},
    )
    if _tool_result_failed(solve_result):
        _raise_fixture_failure(
            step="gh_solve",
            tool_name="gh_solve",
            failure_reason="gh_solve_failed",
            result=solve_result,
        )

    editable_value_result = await _fixture_tool_call(
        tool_executor,
        step="gh_get_editable_value",
        tool_name="gh_get_value",
        args={"guid": editable_guid},
    )
    if _tool_result_failed(editable_value_result):
        _raise_fixture_failure(
            step="gh_get_editable_value",
            tool_name="gh_get_value",
            failure_reason="gh_get_value_failed",
            result=editable_value_result,
        )
    editable_value = _coerce_scalar_value(
        _tool_field(editable_value_result, "value", "Value")
    )
    if abs(float(editable_value) - INITIAL_EDITABLE_VALUE) > SCALAR_TOLERANCE:
        _raise_fixture_failure(
            step="gh_get_editable_value",
            tool_name="gh_get_value",
            failure_reason="initial_editable_value_mismatch",
            result=editable_value_result,
        )

    factor_value_result = await _fixture_tool_call(
        tool_executor,
        step="gh_get_factor_value",
        tool_name="gh_get_value",
        args={"guid": factor_guid},
    )
    if _tool_result_failed(factor_value_result):
        _raise_fixture_failure(
            step="gh_get_factor_value",
            tool_name="gh_get_value",
            failure_reason="gh_get_value_failed",
            result=factor_value_result,
        )
    factor_value = _coerce_scalar_value(
        _tool_field(factor_value_result, "value", "Value")
    )
    if abs(float(factor_value) - FACTOR_VALUE) > SCALAR_TOLERANCE:
        _raise_fixture_failure(
            step="gh_get_factor_value",
            tool_name="gh_get_value",
            failure_reason="factor_value_mismatch",
            result=factor_value_result,
        )

    offset_value_result = await _fixture_tool_call(
        tool_executor,
        step="gh_get_offset_value",
        tool_name="gh_get_value",
        args={"guid": offset_guid},
    )
    if _tool_result_failed(offset_value_result):
        _raise_fixture_failure(
            step="gh_get_offset_value",
            tool_name="gh_get_value",
            failure_reason="gh_get_value_failed",
            result=offset_value_result,
        )
    offset_value = _coerce_scalar_value(
        _tool_field(offset_value_result, "value", "Value")
    )
    if abs(float(offset_value) - OFFSET_VALUE) > SCALAR_TOLERANCE:
        _raise_fixture_failure(
            step="gh_get_offset_value",
            tool_name="gh_get_value",
            failure_reason="offset_value_mismatch",
            result=offset_value_result,
        )

    inspect_result = await _fixture_tool_call(
        tool_executor,
        step="gh_inspect_output",
        tool_name="gh_inspect_output",
        args={"guid": addition_guid, "param": "R"},
    )
    observed_output_value = _inspect_output_scalar_value(inspect_result)
    if abs(float(observed_output_value) - INITIAL_OBSERVED_OUTPUT) > SCALAR_TOLERANCE:
        _raise_fixture_failure(
            step="gh_inspect_output",
            tool_name="gh_inspect_output",
            failure_reason="initial_observed_output_mismatch",
            result=inspect_result,
        )

    receipt = {
        "editable_value": editable_value,
        "observed_output_value": observed_output_value,
        "scalar_anchor": {
            "internal_component_guid": editable_guid,
            "editable_value_contract": {
                "label": "LM8H_Editable",
                "value_type": "number",
                "current_value": editable_value,
                "projection_id": "editable_times_factor_plus_offset",
            },
        },
    }
    visible_receipt = {
        "editable_value": editable_value,
        "observed_output_value": observed_output_value,
        "scalar_anchor": {
            "internal_component_guid_present": True,
            "internal_component_guid_sha256": _guid_sha256(editable_guid),
            "editable_value_contract": dict(receipt["scalar_anchor"]["editable_value_contract"]),
        },
        "component_guid_presence": {
            "editable": True,
            "factor": True,
            "offset": True,
            "multiplication": True,
            "addition": True,
        },
        "component_guid_sha256": {
            "editable": _guid_sha256(editable_guid),
            "factor": _guid_sha256(factor_guid),
            "offset": _guid_sha256(offset_guid),
            "multiplication": _guid_sha256(multiplication_guid),
            "addition": _guid_sha256(addition_guid),
        },
    }
    fixture_setup_summary = {
        "editable_component_guid": editable_guid,
        "factor_component_guid": factor_guid,
        "offset_component_guid": offset_guid,
        "multiplication_component_guid": multiplication_guid,
        "addition_component_guid": addition_guid,
        "editable_component_guid_sha256": _guid_sha256(editable_guid),
        "factor_component_guid_sha256": _guid_sha256(factor_guid),
        "offset_component_guid_sha256": _guid_sha256(offset_guid),
        "multiplication_component_guid_sha256": _guid_sha256(multiplication_guid),
        "addition_component_guid_sha256": _guid_sha256(addition_guid),
        "editable_value": editable_value,
        "factor_value": factor_value,
        "offset_value": offset_value,
        "observed_output_value": observed_output_value,
    }
    return {
        "editable_component_guid": editable_guid,
        "factor_component_guid": factor_guid,
        "offset_component_guid": offset_guid,
        "multiplication_component_guid": multiplication_guid,
        "addition_component_guid": addition_guid,
        "editable_value": editable_value,
        "factor_value": factor_value,
        "offset_value": offset_value,
        "observed_output_value": observed_output_value,
        "receipt": receipt,
        "visible_receipt": visible_receipt,
        "fixture_setup_summary": fixture_setup_summary,
    }


def _graph_from_affine_receipt(receipt: Mapping[str, Any]) -> PlanGraph:
    return PlanGraph(
        nodes={
            CREATE_NODE_ID: PlanGraphNode(
                id=CREATE_NODE_ID,
                intent="Create GH affine scalar transform fixture",
                status="succeeded",
                evidence=NodeEvidence(
                    tool_status="success",
                    verified=True,
                    receipt=dict(receipt),
                ),
            ),
            WORKER_NODE_ID: PlanGraphNode(
                id=WORKER_NODE_ID,
                intent="Set editable GH affine scalar value",
                execution_ref="gh_set_value:v1",
                status="ready",
            ),
            VERIFY_NODE_ID: PlanGraphNode(
                id=VERIFY_NODE_ID,
                intent="Verify GH affine scalar transform output",
                execution_ref="gh_inspect_output:v1",
                status="pending",
                is_terminal=True,
            ),
        },
        memory=GraphMemory(),
    )


def _affine_projection_invariant_holds(sources: Any) -> bool:
    expected_observed = (
        float(sources.editable_observation.value)
        * float(sources.factor_contract.value)
        + float(sources.offset_contract.value)
    )
    return abs(float(sources.observed_output.value) - expected_observed) <= SCALAR_TOLERANCE


def _affine_runtime_context(*, graph, workflow_contract_payload, convention_packets):
    routing_artifact = _affine_scalar_source_routing_artifact()
    static_report = validate_worker_visible_source_routing(routing_artifact)
    sources = extract_gh_affine_scalar_transform_expectation_sources(
        workflow_contract_payload=workflow_contract_payload,
        graph=graph,
        convention_packets=convention_packets,
    )
    if not _affine_projection_invariant_holds(sources):
        raise FixtureSetupFailure(
            step="scalar_runtime_ready",
            tool_name="affine_runtime_context",
            failure_reason="projection_invariant_mismatch",
            result={
                "editable_value": sources.editable_observation.value,
                "factor_value": sources.factor_contract.value,
                "offset_value": sources.offset_contract.value,
                "observed_output_value": sources.observed_output.value,
            },
        )
    packet = assemble_gh_affine_scalar_transform_expectation_packet(sources)
    worker_visible = project_gh_affine_scalar_transform_expectation_legacy(packet)
    return {
        "routing_artifact": routing_artifact,
        "static_routing_report": _routing_report_json(static_report),
        "scalar_runtime_ready": static_report.valid,
        "sources": sources,
        "packet": packet,
        "worker_visible": worker_visible,
    }


def _affine_scalar_scaffold(graph: PlanGraph) -> CompiledWorkflowScaffold:
    normalized_contract = {
        "schema": "rook.workflow_contract:v1",
        "workflow_id": "lm8h-gh-affine-scalar-transform",
    }
    contract_fingerprint = _fingerprint_json(normalized_contract).removeprefix(
        "sha256:"
    )
    snapshot = WorkflowContractSnapshot(
        workflow_id="lm8h-gh-affine-scalar-transform",
        normalized_contract=normalized_contract,
        contract_fingerprint=contract_fingerprint,
    )
    compile_record = WorkflowCompileRecord(
        workflow_id="lm8h-gh-affine-scalar-transform",
        compiler_id="lm8h.script_local_affine_scaffold:v1",
        contract_schema="rook.workflow_contract:v1",
        contract_fingerprint_algorithm="sha256",
        contract_fingerprint=contract_fingerprint,
        provider_id="lm8h.script_local_provider:v1",
        expected_template_id="gh_affine_scalar_transform_expectation",
        selected_template_id="gh_affine_scalar_transform_expectation",
        graph_node_ids=tuple(sorted(graph.nodes)),
        initial_param_node_ids=(),
        rule_node_ids=(WORKER_NODE_ID, VERIFY_NODE_ID),
        terminal_node_ids=(VERIFY_NODE_ID,),
        expected_refs=((WORKER_NODE_ID, "gh_set_value:v1"),),
        step_kinds_by_rule=(),
        max_steps=4,
    )
    return CompiledWorkflowScaffold(
        workflow_id="lm8h-gh-affine-scalar-transform",
        graph=graph,
        provider=object(),
        max_steps=4,
        metadata={},
        rules=(),
        steps=(),
        contract_snapshot=snapshot,
        compile_record=compile_record,
    )


def _affine_scalar_worker_evidence_packet(
    *,
    packet: Mapping[str, Any],
    worker_visible: Mapping[str, Any],
) -> WorkerKnowledgePacket:
    fields = packet["fields"]
    return WorkerKnowledgePacket(
        packet_id="gh_affine_scalar_transform_evidence",
        kind="evidence",
        title="GH affine scalar transform evidence",
        content={
            "current_editable_value": fields["current_editable_value"],
            "factor_value": fields["factor_value"],
            "offset_value": fields["offset_value"],
            "current_observed_output": fields["current_observed_output"],
            "expected_output_value": fields["expected_output_value"],
            "projection": dict(fields["projection"]),
            "editable_value_contract": dict(fields["editable_value_contract"]),
            "recommended_action_id": ACTION_ID,
            "action_selection_contract": dict(fields["action_selection_contract"]),
            "acceptance_criteria": dict(worker_visible),
        },
    )


def _affine_scalar_allowed_action() -> WorkerAllowedAction:
    return WorkerAllowedAction(
        action_id=ACTION_ID,
        kind="stage_params",
        description="Draft parameters for setting the trusted editable GH scalar value.",
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
        _affine_scalar_scaffold(graph),
        graph,
        records=(),
        supply_records=(),
        current_node_id=WORKER_NODE_ID,
        knowledge=(
            _affine_scalar_worker_evidence_packet(
                packet=packet,
                worker_visible=worker_visible,
            ),
        ),
        allowed_actions=(_affine_scalar_allowed_action(),),
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
        "factor_value": FACTOR_VALUE,
        "offset_value": OFFSET_VALUE,
        "initial_observed_output": INITIAL_OBSERVED_OUTPUT,
        "expected_output_value": EXPECTED_OUTPUT_VALUE,
        "projection_id": EXPECTED_AFFINE_PROJECTION["projection_id"],
        "worker_retry_enabled": False,
        "planner_model": None,
        "gh_edit_enabled": False,
    }


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
        raise ValueError(f"Unsupported LM8H decision: {decision}")
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
                "LM8H decision extra contains reserved identity fields: "
                + ", ".join(sorted(blocked_paths))
            )
        record.update(extra_record)
    return record


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


_FORBIDDEN_PUBLICATION_MARKERS = (
    "gh" + "_edit",
    "gh" + "_update_script",
    "gh" + "_connect",
    "gh" + "_set_value",
    "code",
    "script",
    "topology",
    "wiring",
    "wire",
)


def _find_publication_forbidden_marker(value: Any, *, path: str = "") -> str | None:
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            key_text = str(key)
            if key_text == "input":
                continue
            next_path = f"{path}.{key_text}" if path else key_text
            if key_text == "action_id":
                continue
            nested_marker = _find_publication_forbidden_marker(
                nested_value, path=next_path
            )
            if nested_marker is not None:
                return nested_marker
            key_marker = _find_publication_forbidden_marker(key_text, path=next_path)
            if key_marker is not None:
                return key_marker
        return None
    if isinstance(value, str):
        lowered = value.casefold()
        for marker in _FORBIDDEN_PUBLICATION_MARKERS:
            if marker.casefold() in lowered:
                return marker
        return None
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        for index, item in enumerate(value):
            nested_marker = _find_publication_forbidden_marker(
                item,
                path=f"{path}[{index}]",
            )
            if nested_marker is not None:
                return nested_marker
    return None


def _published_action_payload_failure_reason(
    response_payload: Mapping[str, Any],
) -> str | None:
    action_id = response_payload.get("action_id")
    if action_id != ACTION_ID:
        return "worker_publication_invalid_action_id"

    marker = _find_publication_forbidden_marker(response_payload)
    if marker is not None:
        return f"worker_publication_forbidden_content:{marker}"
    return None


async def _dispatch_set_value_solve_and_verify(
    *,
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]],
    editable_component_guid: str,
    addition_component_guid: str,
    worker_value: float | int,
    expected_value: float | int,
) -> dict[str, Any]:
    try:
        set_result = await tool_executor(
            "gh_set_value",
            {"guid": editable_component_guid, "value": worker_value},
        )
    except Exception as exc:
        return {
            "live_set_value_summary": {
                "tool_name": "gh_set_value",
                "component_guid": editable_component_guid,
                "component_guid_sha256": _guid_sha256(editable_component_guid),
                "worker_action_value": worker_value,
                "set_value_reported_success": False,
                "exception": type(exc).__name__,
            },
            "verify_scalar_output_summary": None,
            "decision": {
                "decision": "rejected",
                "reason": f"gh_set_value_exception:{type(exc).__name__}",
                "phase": "live_set_value",
            },
        }
    set_value_reported_success = not _tool_result_failed(set_result)
    set_summary = {
        "tool_name": "gh_set_value",
        "component_guid": editable_component_guid,
        "component_guid_sha256": _guid_sha256(editable_component_guid),
        "worker_action_value": worker_value,
        "success": set_value_reported_success,
        "set_value_reported_success": set_value_reported_success,
        "receipt_sha256": _fingerprint_json(set_result),
    }

    try:
        solve_result = await tool_executor("gh_solve", {"delay": 25})
    except Exception as exc:
        return {
            "live_set_value_summary": set_summary,
            "verify_scalar_output_summary": None,
            "decision": {
                "decision": "rejected",
                "reason": f"gh_solve_exception:{type(exc).__name__}",
                "phase": "live_set_value",
            },
        }
    set_summary["solve_receipt_sha256"] = _fingerprint_json(solve_result)
    if _tool_result_failed(solve_result):
        return {
            "live_set_value_summary": set_summary,
            "verify_scalar_output_summary": None,
            "decision": {
                "decision": "rejected",
                "reason": "gh_solve_failed",
                "phase": "live_set_value",
            },
        }

    attempts: list[dict[str, Any]] = []
    observed: float | int | None = None
    matched = False
    final_reason = "verify_scalar_output_failed"
    final_exception: str | None = None
    final_receipt: Any = None
    final_reported_success = False

    for attempt_index in range(1, VERIFY_INSPECT_ATTEMPTS + 1):
        try:
            inspect_result = await tool_executor(
                "gh_inspect_output",
                {"guid": addition_component_guid, "param": "R"},
            )
        except Exception as exc:
            observed = None
            matched = False
            final_exception = type(exc).__name__
            final_reason = f"gh_inspect_output_exception:{type(exc).__name__}"
            final_receipt = {"exception": type(exc).__name__}
            final_reported_success = False
            attempts.append(
                _verifier_attempt_summary(
                    attempt_index=attempt_index,
                    exception=exc,
                    failure_reason=final_reason,
                )
            )
        else:
            final_receipt = inspect_result
            final_exception = None
            tool_failed = _tool_result_failed(inspect_result)
            final_reported_success = not tool_failed
            if tool_failed:
                observed = None
                matched = False
                final_reason = "verify_scalar_output_failed"
                failure_reason = "gh_inspect_output_failed"
            else:
                try:
                    observed = _inspect_output_scalar_value(inspect_result)
                except ValueError as exc:
                    observed = None
                    matched = False
                    final_reason = "verify_scalar_output_invalid_value"
                    failure_reason = _fixture_reason_from_exception(exc)
                else:
                    matched = (
                        abs(float(observed) - float(expected_value)) <= SCALAR_TOLERANCE
                    )
                    final_reason = (
                        "verify_scalar_output_succeeded"
                        if matched
                        else "verify_scalar_output_failed"
                    )
                    failure_reason = None if matched else "verify_scalar_output_mismatch"
            attempts.append(
                _verifier_attempt_summary(
                    attempt_index=attempt_index,
                    result=inspect_result,
                    observed_output_value=observed,
                    matched=matched,
                    failure_reason=failure_reason,
                )
            )
            if matched:
                break
        if attempt_index < VERIFY_INSPECT_ATTEMPTS:
            await asyncio.sleep(VERIFY_INSPECT_DELAY_S)

    final_attempt = attempts[-1]
    verify_summary = {
        "tool_name": "gh_inspect_output",
        "component_guid_sha256": _guid_sha256(addition_component_guid),
        "expected_output_value": expected_value,
        "observed_output_value": observed,
        "tolerance": SCALAR_TOLERANCE,
        "matched": matched,
        "receipt_sha256": _fingerprint_json(final_receipt),
        "reported_success": final_reported_success,
        "attempt_count": len(attempts),
        "attempts": attempts,
    }
    if final_exception:
        verify_summary["exception"] = final_exception
    return {
        "live_set_value_summary": set_summary,
        "verify_scalar_output_summary": verify_summary,
        "decision": {
            "decision": "accepted" if matched else "rejected",
            "reason": final_reason,
            "phase": "verify_scalar_output",
            "expected_output_value": expected_value,
            "observed_output_after": final_attempt["observed_output_value"],
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
    _write_json_value(run_dir / "preflight_summary.json", preflight_summaries)
    if not ok:
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
        fixture = asyncio.run(_create_affine_fixture(tool_executor))
    except FixtureSetupFailure as exc:
        _write_json(
            run_dir / "fixture_failure_summary.json",
            _fixture_failure_summary(exc, excerpt_chars=excerpt_chars),
        )
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason=f"affine_fixture_failed:{exc.failure_reason}",
                phase="live_fixture",
                canonical_evidence=canonical_evidence,
            ),
        )
        return run_dir
    except Exception as exc:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason=f"affine_fixture_failed:{type(exc).__name__}",
                phase="live_fixture",
                canonical_evidence=canonical_evidence,
            ),
        )
        return run_dir

    editable_component_guid = fixture["editable_component_guid"]
    factor_component_guid = fixture["factor_component_guid"]
    offset_component_guid = fixture["offset_component_guid"]
    multiplication_component_guid = fixture["multiplication_component_guid"]
    addition_component_guid = fixture["addition_component_guid"]
    _write_json(run_dir / "fixture_setup_summary.json", fixture["fixture_setup_summary"])
    _write_json_value(run_dir / "affine_fixture_receipt.json", fixture["visible_receipt"])
    workflow_contract_payload = _affine_scalar_contract_payload()
    _write_json_value(
        run_dir / "affine_scalar_contract.json",
        workflow_contract_payload,
    )

    graph = _graph_from_affine_receipt(fixture["receipt"])
    try:
        runtime = _affine_runtime_context(
            graph=graph,
            workflow_contract_payload=workflow_contract_payload,
            convention_packets=(),
        )
    except FixtureSetupFailure as exc:
        _write_json(
            run_dir / "fixture_failure_summary.json",
            _fixture_failure_summary(exc, excerpt_chars=excerpt_chars),
        )
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason=f"affine_fixture_failed:{exc.failure_reason}",
                phase="scalar_runtime_ready",
                canonical_evidence=canonical_evidence,
                live_fixture_created=True,
                component_guid=editable_component_guid,
            ),
        )
        return run_dir
    except Exception as exc:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason=f"scalar_runtime_readiness_failed:{type(exc).__name__}",
                phase="scalar_runtime_ready",
                canonical_evidence=canonical_evidence,
                live_fixture_created=True,
                component_guid=editable_component_guid,
            ),
        )
        return run_dir
    _write_json_value(
        run_dir / "affine_scalar_source_routing.json", runtime["routing_artifact"]
    )
    _write_json(
        run_dir / "static_routing_validation.json",
        runtime["static_routing_report"],
    )
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
                component_guid=editable_component_guid,
            ),
        )
        return run_dir

    _write_json_value(
        run_dir / "scalar_sources.json",
        {
            "expected_output_contract": runtime["sources"].expected_output_contract.__dict__,
            "factor_contract": runtime["sources"].factor_contract.__dict__,
            "offset_contract": runtime["sources"].offset_contract.__dict__,
            "projection_contract": runtime["sources"].projection_contract.__dict__,
            "editable_observation": runtime["sources"].editable_observation.__dict__,
            "observed_output": runtime["sources"].observed_output.__dict__,
            "fixture_anchor": runtime["sources"].fixture_anchor.__dict__,
            "convention": (
                runtime["sources"].convention.__dict__
                if runtime["sources"].convention is not None
                else None
            ),
        },
    )
    _write_json_value(
        run_dir / "acceptance_criteria_packet.json",
        runtime["packet"],
    )
    _write_json(
        run_dir / "worker_visible_acceptance_criteria.json",
        runtime["worker_visible"],
    )
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
                component_guid=editable_component_guid,
            ),
        )
        return run_dir

    component_guids = (
        editable_component_guid,
        factor_component_guid,
        offset_component_guid,
        multiplication_component_guid,
        addition_component_guid,
    )
    for component_guid in component_guids:
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
                    component_guid=editable_component_guid,
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
                component_guid=editable_component_guid,
                extra={
                    key: value
                    for key, value in worker_decision.items()
                    if key not in {"decision", "reason", "phase"}
                },
            ),
        )
        return run_dir

    response_payload = publication.response_payload
    publication_failure_reason = _published_action_payload_failure_reason(
        response_payload
    )
    if publication_failure_reason is not None:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="publication_failed",
                reason=publication_failure_reason,
                phase="worker_publication",
                canonical_evidence=canonical_evidence,
                scalar_runtime_ready=True,
                live_fixture_created=True,
                worker_publication_ran=True,
                component_guid=editable_component_guid,
            ),
        )
        return run_dir
    _write_json(run_dir / "worker_action.json", response_payload)
    action_context = _action_context(response_payload, excerpt_chars)
    apply_result = apply_gh_scalar_value_action_to_node(
        graph,
        WORKER_NODE_ID,
        action_id=str(response_payload.get("action_id") or ""),
        action_input=response_payload.get("input"),
        anchor_binding={"component_guid": editable_component_guid},
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
                component_guid=editable_component_guid,
                extra=action_context,
            ),
        )
        return run_dir

    params = apply_result.graph.nodes[WORKER_NODE_ID].metadata[EXECUTION_PARAMS_KEY]
    dispatch = asyncio.run(
        _dispatch_set_value_solve_and_verify(
            tool_executor=tool_executor,
            editable_component_guid=str(params["guid"]),
            addition_component_guid=addition_component_guid,
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
            verify_scalar_output_ran=dispatch["verify_scalar_output_summary"] is not None,
            component_guid=editable_component_guid,
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
        "LM8H GH affine scalar depth live probe complete "
        f"run_dir={run_dir} "
        f"decision={decision.get('decision')} "
        f"reason={decision.get('reason')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
