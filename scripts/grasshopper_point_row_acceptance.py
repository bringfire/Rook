"""Evaluate retained point-row behavioral evidence through the common owner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MCP_SOURCE = ROOT / "mcp_server" / "src"
if str(MCP_SOURCE) not in sys.path:
    sys.path.insert(0, str(MCP_SOURCE))

from rook.gh_behavioral_acceptance import (  # noqa: E402
    canonical_json_bytes,
    evaluate_behavioral_probe,
    validate_acceptance_artifact,
)


_COMPATIBILITY_SCHEMA = "rook.experimental.grasshopper_point_row_evaluation:v2"


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def _load_json(path: Path, *, canonical: bool) -> Any:
    payload = Path(path).read_bytes()
    if payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError("utf8_bom_forbidden")
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicates,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"nonfinite_json:{item}")
            ),
        )
    except UnicodeDecodeError as exc:
        raise ValueError("invalid_utf8") from exc
    if canonical and payload != canonical_json_bytes(value):
        raise ValueError("noncanonical_json")
    return value


def load_acceptance(path: Path) -> dict[str, Any]:
    return validate_acceptance_artifact(_load_json(path, canonical=True))


def _combine_status(*statuses: str) -> str:
    if "fail" in statuses:
        return "fail"
    if "unproven" in statuses:
        return "unproven"
    return "pass"


def compatibility_report(result: dict[str, Any]) -> dict[str, Any]:
    """Map generic predicate results onto the six historical report headings."""

    if (
        not isinstance(result, dict)
        or result.get("schema") != "rook.gh_behavioral_evaluation:v1"
        or not isinstance(result.get("criteria"), list)
    ):
        raise ValueError("invalid_point_row_evaluation")
    raw_criteria = result["criteria"]
    for item in raw_criteria:
        if (
            not isinstance(item, dict)
            or set(item) != {"criterion_id", "status", "failure_ids", "evidence_refs"}
            or item["status"] not in {"pass", "fail", "unproven"}
            or item["failure_ids"]
            != ([] if item["status"] == "pass" else [item["criterion_id"]])
            or not isinstance(item["evidence_refs"], list)
        ):
            raise ValueError("invalid_point_row_evaluation")
    by_id = {
        item["criterion_id"]: item
        for item in raw_criteria
        if isinstance(item, dict) and isinstance(item.get("criterion_id"), str)
    }
    required = {
        "adjustable_start_present",
        "adjustable_step_present",
        "adjustable_count_present",
        "point_count_equals_count",
        "x_values_equal_start_step_count",
        "all_y_zero",
        "all_z_zero",
        "no_runtime_errors",
    }
    if set(by_id) != required or len(raw_criteria) != len(required):
        raise ValueError("invalid_point_row_criteria")

    def mapped(criterion_id: str, status: str, failure_ids: list[str]) -> dict[str, Any]:
        return {
            "criterion_id": criterion_id,
            "status": status,
            "failure_ids": failure_ids,
        }

    control_items = [
        by_id["adjustable_start_present"],
        by_id["adjustable_step_present"],
        by_id["adjustable_count_present"],
    ]
    control_status = _combine_status(*(item["status"] for item in control_items))
    control_failures = [
        item["criterion_id"]
        for item in control_items
        if item["status"] == "fail"
    ]
    x_status = by_id["x_values_equal_start_step_count"]["status"]
    yz_status = _combine_status(by_id["all_y_zero"]["status"], by_id["all_z_zero"]["status"])
    criteria = [
        mapped("adjustable_controls_present", control_status, control_failures),
        mapped(
            "point_count_equals_count",
            by_id["point_count_equals_count"]["status"],
            ["point_count_equals_count"] if by_id["point_count_equals_count"]["status"] == "fail" else [],
        ),
        mapped("first_x_equals_start", x_status, ["first_x_equals_start"] if x_status == "fail" else []),
        mapped("successive_x_difference_equals_step", x_status, ["successive_x_difference_equals_step"] if x_status == "fail" else []),
        mapped("all_yz_zero", yz_status, ["all_yz_zero"] if yz_status == "fail" else []),
        mapped(
            "no_runtime_errors",
            by_id["no_runtime_errors"]["status"],
            ["no_runtime_errors"] if by_id["no_runtime_errors"]["status"] == "fail" else [],
        ),
    ]
    failure_ids = [failure for item in criteria for failure in item["failure_ids"]]
    overall = "fail" if failure_ids else "incomplete" if any(item["status"] == "unproven" for item in criteria) else "pass"
    return {
        "schema": _COMPATIBILITY_SCHEMA,
        "overall": overall,
        "failure_ids": failure_ids,
        "criteria": criteria,
        "behavioral_evaluation": result,
    }


def evaluate(
    acceptance: dict[str, Any],
    authoring_trace_path: Path,
    probe_trace_path: Path,
) -> dict[str, Any]:
    authoring_trace = _load_json(authoring_trace_path, canonical=True)
    probe_trace = _load_json(probe_trace_path, canonical=True)
    return compatibility_report(
        evaluate_behavioral_probe(acceptance, authoring_trace, probe_trace)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acceptance", type=Path)
    parser.add_argument("authoring_trace", type=Path)
    parser.add_argument("probe_trace", type=Path)
    args = parser.parse_args(argv)
    try:
        result = evaluate(
            load_acceptance(args.acceptance),
            args.authoring_trace,
            args.probe_trace,
        )
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
