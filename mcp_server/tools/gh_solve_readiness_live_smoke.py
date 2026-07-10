"""Post-merge-only deterministic smoke for the GH solve-readiness receipt path."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any, Awaitable, Callable


ToolExecutor = Callable[[str, dict[str, object]], Awaitable[object]]
WAIT_TIMEOUT_MS = 10_000
EXPECTED_VALUE = 7.5
RECEIPT_SCHEMA = "rook.gh_solve_readiness_receipt:v1"


class SmokeFailure(RuntimeError):
    def __init__(self, reason: str, detail: object | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def _write_json(run_dir: Path, name: str, value: object) -> None:
    (run_dir / name).write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


async def _call_tool(
    tool_executor: ToolExecutor, tool_name: str, args: dict[str, object]
) -> object:
    result = await tool_executor(tool_name, args)
    return result


def _success(result: dict[str, Any]) -> bool:
    return result.get("success") is True


def _data(result: dict[str, Any]) -> dict[str, Any]:
    value = result.get("data")
    return value if isinstance(value, dict) else {}


def _field(value: dict[str, Any], name: str) -> object | None:
    return value.get(name) if name in value else value.get(name[:1].upper() + name[1:])


def _require_guid(result: dict[str, Any], step: str) -> str:
    data = _data(result)
    created = _field(data, "created")
    guid = _field(data, "guid")
    if not _success(result) or created is not True or not isinstance(guid, str) or not guid:
        raise SmokeFailure(f"{step}_failed", result)
    return guid


def _receipt_from(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    for key in ("solve_readiness_receipt", "readiness_receipt", "receipt"):
        receipt = value.get(key)
        if isinstance(receipt, dict):
            return receipt
    return None


def _receipt_identity(receipt: dict[str, Any]) -> tuple[object, ...]:
    return tuple(
        receipt.get(key)
        for key in (
            "receipt_id",
            "document_session_id",
            "mutation_epoch",
            "solution_run_epoch",
            "completed_solution_run_epoch",
        )
    )


def _receipt_has_schema_and_status(receipt: dict[str, Any], status: str) -> bool:
    return receipt.get("schema") == RECEIPT_SCHEMA and receipt.get("status") == status


def _fenced_output_matches_receipt(data: dict[str, Any], receipt: dict[str, Any]) -> bool:
    return (
        data.get("readiness_fenced") is True
        and data.get("readiness_receipt_id") == receipt.get("receipt_id")
        and data.get("document_session_id") == receipt.get("document_session_id")
        and data.get("mutation_epoch") == receipt.get("mutation_epoch")
        and data.get("completed_solution_epoch") == receipt.get("completed_solution_run_epoch")
    )


def _observed_output_value(result: dict[str, Any]) -> float:
    preview = _data(result).get("preview")
    if not isinstance(preview, list) or len(preview) != 1:
        raise SmokeFailure("fenced_output_value_missing", result)
    value = preview[0]
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise SmokeFailure("fenced_output_value_invalid", result)
    try:
        parsed_value = float(value)
    except (TypeError, ValueError, OverflowError):
        raise SmokeFailure("fenced_output_value_invalid", result) from None
    if not math.isfinite(parsed_value):
        raise SmokeFailure("fenced_output_value_invalid", result)
    return parsed_value


async def run_smoke(tool_executor: ToolExecutor, *, run_dir: Path) -> dict[str, object]:
    """Run one receipt-fenced mutation/read sequence against direct GH tools."""
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "rook.gh_solve_readiness_live_smoke:v1",
        "expected_output_value": EXPECTED_VALUE,
        "wait_timeout_ms": WAIT_TIMEOUT_MS,
        "baseline_setup_only": True,
        "model_call": False,
    }
    _write_json(run_dir, "manifest.json", manifest)

    try:
        ping = await _call_tool(tool_executor, "rhino_ping", {})
        if ping != "pong":
            raise SmokeFailure("rhino_ping_failed", ping)
        document = await _call_tool(tool_executor, "gh_document_new", {})
        if not isinstance(document, dict):
            raise SmokeFailure("gh_document_new_invalid_result", document)
        if not _success(document):
            raise SmokeFailure("gh_document_new_failed", document)

        library = await _call_tool(tool_executor, "gh_library", {"search": "addition", "limit": 20})
        if not isinstance(library, dict):
            raise SmokeFailure("gh_library_invalid_result", library)
        components = library.get("components") if _success(library) else None
        addition_proxy = next(
            (
                component.get("guid")
                for component in components or []
                if isinstance(component, dict)
                and component.get("name") == "Addition"
                and isinstance(component.get("guid"), str)
                and component["guid"]
            ),
            None,
        )
        if not isinstance(addition_proxy, str):
            raise SmokeFailure("addition_component_missing", library)

        editable_result = await _call_tool(
                tool_executor,
                "gh_create_slider",
                {"nickname": "LM8K_Editable", "min": 0, "max": 10, "value": 0.0, "x": 20, "y": 80},
            )
        if not isinstance(editable_result, dict):
            raise SmokeFailure("editable_slider_invalid_result", editable_result)
        editable = _require_guid(editable_result, "editable_slider")
        offset_result = await _call_tool(
                tool_executor,
                "gh_create_slider",
                {"nickname": "LM8K_Offset", "min": 0, "max": 10, "value": 0.0, "x": 20, "y": 180},
            )
        if not isinstance(offset_result, dict):
            raise SmokeFailure("offset_slider_invalid_result", offset_result)
        offset = _require_guid(offset_result, "offset_slider")
        addition_result = await _call_tool(
            tool_executor, "gh_create_component", {"guid": addition_proxy, "x": 280, "y": 130}
        )
        if not isinstance(addition_result, dict):
            raise SmokeFailure("addition_component_invalid_result", addition_result)
        addition = _require_guid(addition_result, "addition_component")
        for args in (
            {"sourceGuid": editable, "targetGuid": addition, "targetParam": "A"},
            {"sourceGuid": offset, "targetGuid": addition, "targetParam": "B"},
        ):
            connected = await _call_tool(tool_executor, "gh_connect", args)
            if not isinstance(connected, dict):
                raise SmokeFailure("gh_connect_invalid_result", connected)
            if not _success(connected):
                raise SmokeFailure("gh_connect_failed", connected)
        _write_json(
            run_dir,
            "baseline_setup_summary.json",
            {
                "baseline_setup_only": True,
                "editable_initial_value": 0.0,
                "offset_initial_value": 0.0,
                "addition_output_read": False,
            },
        )

        mutation = await _call_tool(tool_executor, "gh_set_value", {"guid": editable, "value": EXPECTED_VALUE})
        if not isinstance(mutation, dict):
            raise SmokeFailure("gh_set_value_invalid_result", mutation)
        mutation_receipt = _receipt_from(_data(mutation))
        _write_json(run_dir, "mutation_receipt.json", {"mutation": mutation, "receipt": mutation_receipt})
        if not _success(mutation) or mutation_receipt is None:
            raise SmokeFailure("solve_readiness_receipt_missing", mutation)
        receipt_id = mutation_receipt.get("receipt_id")
        if not isinstance(receipt_id, str) or not receipt_id:
            raise SmokeFailure("solve_readiness_receipt_missing", mutation_receipt)
        if not _receipt_has_schema_and_status(mutation_receipt, "pending"):
            raise SmokeFailure("solve_readiness_receipt_invalid", mutation_receipt)

        wait = await _call_tool(
            tool_executor,
            "gh_wait_for_solve_readiness",
            {"readiness_receipt_id": receipt_id, "timeout_ms": WAIT_TIMEOUT_MS},
        )
        if not isinstance(wait, dict):
            raise SmokeFailure("solve_readiness_wait_invalid_result", wait)
        _write_json(run_dir, "wait_result.json", wait)
        wait_data = _data(wait)
        wait_receipt = _receipt_from(wait_data)
        if (
            not _success(wait)
            or wait_data.get("wait_status") != "ready"
            or wait_receipt is None
            or not _receipt_has_schema_and_status(wait_receipt, "ready")
            or _receipt_identity(wait_receipt) != _receipt_identity(mutation_receipt)
        ):
            raise SmokeFailure("solve_readiness_wait_not_ready", wait)

        fenced_output = await _call_tool(
            tool_executor,
            "gh_inspect_output",
            {"guid": addition, "param": "R", "readiness_receipt_id": receipt_id},
        )
        if not isinstance(fenced_output, dict):
            raise SmokeFailure("fenced_output_invalid_result", fenced_output)
        _write_json(run_dir, "fenced_output_summary.json", fenced_output)
        if not _success(fenced_output):
            raise SmokeFailure("fenced_output_read_failed", fenced_output)
        if not _fenced_output_matches_receipt(_data(fenced_output), wait_receipt):
            raise SmokeFailure("fenced_output_provenance_mismatch", fenced_output)
        observed_output_value = _observed_output_value(fenced_output)
        if observed_output_value != EXPECTED_VALUE:
            raise SmokeFailure("fenced_output_value_mismatch", fenced_output)

        decision = {
            "accepted": True,
            "baseline_setup_only": True,
            "readiness_fenced": True,
            "observed_output_value": observed_output_value,
        }
        _write_json(run_dir, "decision.json", decision)
        return {"run_dir": str(run_dir), "decision": decision}
    except SmokeFailure as exc:
        decision = {"accepted": False, "reason": exc.reason}
        _write_json(run_dir, "decision.json", decision)
        raise


def _default_run_dir() -> Path:
    root = Path(__file__).resolve().parents[2]
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    revision = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=root, check=True, text=True, capture_output=True
    ).stdout.strip()
    return root / "probe_runs" / f"lm8k-{timestamp}-{revision}"


async def _direct_executor(tool_name: str, args: dict[str, object]) -> object:
    root = Path(__file__).resolve().parents[2]
    source_root = root / "mcp_server" / "src"
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    from rook import server

    return await server._call_tool_dispatch(tool_name, args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args(argv)
    run_dir = args.run_dir or _default_run_dir()
    try:
        asyncio.run(run_smoke(_direct_executor, run_dir=run_dir))
    except SmokeFailure as exc:
        print(f"FAIL: {exc.reason}", file=sys.stderr)
        return 1
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
