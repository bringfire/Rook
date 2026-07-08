#!/usr/bin/env python
"""LM8C GH scalar expectation live splice probe."""

from __future__ import annotations

import argparse
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
) -> Path:
    raise NotImplementedError(
        "LM8C live probe execution is intentionally not implemented in Task 1; "
        "later tasks must wire live Grasshopper behavior through this interface."
    )
