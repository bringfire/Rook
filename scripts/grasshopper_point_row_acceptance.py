"""Mechanically evaluate a frozen Grasshopper point-row snapshot."""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any


_ACCEPTANCE_SCHEMA = "rook.experimental.grasshopper_point_row_acceptance:v1"
_EVALUATION_SCHEMA = "rook.experimental.grasshopper_point_row_evaluation:v1"
_CRITERIA = (
    "adjustable_controls_present",
    "point_count_equals_count",
    "first_x_equals_start",
    "successive_x_difference_equals_step",
    "all_yz_zero",
    "no_runtime_errors",
)
_CONTROL_REQUIREMENTS = (
    ("Start", "adjustable_start_present"),
    ("Step", "adjustable_step_present"),
    ("Count", "adjustable_count_present"),
)
_GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_FLOW = re.compile(r"^([A-Za-z0-9_-]+)\.O(\d+)>([A-Za-z0-9_-]+)\.I(\d+)$")


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def _load_json_bytes(payload: bytes) -> Any:
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("invalid_utf8") from exc
    return json.loads(text, object_pairs_hook=_reject_duplicates)


def _closed_indices(value: Any, keys: set[str]) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == keys
        and all(type(item) is int and item >= 0 for item in value.values())
        and len(set(value.values())) == len(value)
    )


def _validate_series_semantics(value: Any) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"kind", "inputs", "outputs", "facts"}
        or value["kind"] != "series"
        or not _closed_indices(value["inputs"], {"start", "step", "count"})
        or not _closed_indices(value["outputs"], {"values"})
        or not isinstance(value["facts"], dict)
        or set(value["facts"])
        != {
            "output_count_equals_count",
            "first_value_equals_start",
            "successive_difference_equals_step",
        }
        or not all(type(fact) is bool for fact in value["facts"].values())
    ):
        raise ValueError("invalid_series_semantics")


def _validate_construct_point_semantics(value: Any) -> None:
    facts = value.get("facts") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or set(value) != {"kind", "inputs", "outputs", "facts"}
        or value["kind"] != "construct_point"
        or not _closed_indices(value["inputs"], {"x", "y", "z"})
        or not _closed_indices(value["outputs"], {"point"})
        or not isinstance(facts, dict)
        or set(facts) != {"unconnected_y_default", "unconnected_z_default"}
        or any(
            isinstance(fact, bool)
            or not isinstance(fact, (int, float))
            or (isinstance(fact, float) and not math.isfinite(fact))
            for fact in facts.values()
        )
    ):
        raise ValueError("invalid_construct_point_semantics")


def load_acceptance(path: Path) -> dict[str, Any]:
    document = _load_json_bytes(Path(path).read_bytes())
    if not isinstance(document, dict) or set(document) != {
        "schema",
        "intent",
        "criteria",
        "reviewed_primitive_semantics",
    }:
        raise ValueError("invalid_acceptance_shape")
    if document["schema"] != _ACCEPTANCE_SCHEMA:
        raise ValueError("invalid_acceptance_schema")
    criteria = document["criteria"]
    if not isinstance(criteria, list) or tuple(
        item.get("id") if isinstance(item, dict) else None for item in criteria
    ) != _CRITERIA:
        raise ValueError("invalid_acceptance_criteria")
    semantics = document["reviewed_primitive_semantics"]
    if not isinstance(semantics, dict) or len(semantics) != 2:
        raise ValueError("invalid_primitive_semantics")
    kinds: list[str] = []
    for guid, value in semantics.items():
        if not isinstance(guid, str) or _GUID.fullmatch(guid) is None:
            raise ValueError("invalid_primitive_guid")
        kind = value.get("kind") if isinstance(value, dict) else None
        if kind == "series":
            _validate_series_semantics(value)
        elif kind == "construct_point":
            _validate_construct_point_semantics(value)
        else:
            raise ValueError("invalid_primitive_semantics")
        kinds.append(kind)
    if sorted(kinds) != ["construct_point", "series"]:
        raise ValueError("invalid_primitive_semantics")
    return document


def _load_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    payload = Path(path).read_bytes()
    rows = [
        _load_json_bytes(line)
        for line in payload.splitlines()
        if line.strip()
    ]
    expected_request = {
        "kind": "request",
        "payload": {
            "name": "gh_snapshot",
            "arguments": {"include_data": True, "max_preview_items": 3},
        },
    }
    if len(rows) != 2 or rows[0] != expected_request:
        raise ValueError("invalid_snapshot_request")
    result = rows[1]
    if (
        not isinstance(result, dict)
        or set(result) != {"kind", "payload"}
        or result["kind"] != "result"
        or not isinstance(result["payload"], dict)
        or result["payload"].get("success") is not True
        or not isinstance(result["payload"].get("data"), dict)
    ):
        raise ValueError("invalid_snapshot_result")
    return result["payload"]["data"], hashlib.sha256(payload).hexdigest().upper()


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _point(value: Any) -> tuple[Decimal, Decimal, Decimal] | None:
    if not isinstance(value, str):
        return None
    parts = value.split(",")
    if len(parts) != 3:
        return None
    coordinates = tuple(_decimal(part) for part in parts)
    if any(item is None for item in coordinates):
        return None
    return coordinates  # type: ignore[return-value]


def _result(
    criterion_id: str,
    status: str,
    evidence: dict[str, Any],
    failure_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "criterion_id": criterion_id,
        "status": status,
        "failure_ids": failure_ids or [],
        "evidence": evidence,
    }


class _Snapshot:
    def __init__(self, data: dict[str, Any], semantics: dict[str, Any]):
        components = data.get("components")
        self.components = components if isinstance(components, list) else []
        self.data = data
        self.semantics = semantics
        self.by_id: dict[str, dict[str, Any]] = {}
        self.incoming: dict[tuple[str, int], list[tuple[str, int]]] = {}
        for component in self.components:
            if not isinstance(component, dict):
                continue
            component_id = component.get("id")
            if isinstance(component_id, str) and component_id not in self.by_id:
                self.by_id[component_id] = component
        flows = data.get("flows")
        if isinstance(flows, list):
            for raw in flows:
                match = _FLOW.fullmatch(raw) if isinstance(raw, str) else None
                if match is None:
                    continue
                source, output, target, input_index = match.groups()
                self.incoming.setdefault((target, int(input_index)), []).append(
                    (source, int(output))
                )

    def controls(self) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        admitted: dict[str, dict[str, Any]] = {}
        states: dict[str, str] = {}
        for nickname, _ in _CONTROL_REQUIREMENTS:
            matches = [
                component
                for component in self.components
                if isinstance(component, dict)
                and component.get("type") == "NumberSlider"
                and component.get("nick") == nickname
            ]
            if not matches:
                states[nickname] = "missing"
                continue
            if len(matches) != 1:
                states[nickname] = "ambiguous"
                continue
            value = matches[0].get("value")
            if not isinstance(value, dict) or value.get("type") != "slider":
                states[nickname] = "malformed"
                continue
            current = _decimal(value.get("val"))
            minimum = _decimal(value.get("min"))
            maximum = _decimal(value.get("max"))
            if None in (current, minimum, maximum) or minimum >= maximum:
                states[nickname] = "malformed"
                continue
            states[nickname] = "admitted"
            admitted[nickname] = matches[0]
        return admitted, states

    def point_output(self) -> tuple[dict[str, Any], dict[str, Any]] | None:
        matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for component in self.components:
            if not isinstance(component, dict):
                continue
            outputs = component.get("outputs")
            if not isinstance(outputs, list):
                continue
            for output in outputs:
                if isinstance(output, dict) and output.get("type") == "Point":
                    matches.append((component, output))
        return matches[0] if len(matches) == 1 else None

    def primitive(self, kind: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        matches = []
        for component in self.components:
            if not isinstance(component, dict):
                continue
            semantics = self.semantics.get(component.get("componentGuid"))
            if isinstance(semantics, dict) and semantics.get("kind") == kind:
                matches.append((component, semantics))
        return matches[0] if len(matches) == 1 else None

    def connected(self, source: dict[str, Any], output: int, target: dict[str, Any], input_index: int) -> bool:
        return self.incoming.get((target.get("id"), input_index)) == [
            (source.get("id"), output)
        ]


def _series_path(snapshot: _Snapshot, controls: dict[str, dict[str, Any]]) -> bool:
    point = snapshot.primitive("construct_point")
    series = snapshot.primitive("series")
    if point is None or series is None or set(controls) != {"Start", "Step", "Count"}:
        return False
    point_component, point_semantics = point
    series_component, series_semantics = series
    inputs = series_semantics.get("inputs")
    outputs = series_semantics.get("outputs")
    facts = series_semantics.get("facts")
    point_inputs = point_semantics.get("inputs")
    point_outputs = point_semantics.get("outputs")
    selected_point = snapshot.point_output()
    if (
        not all(
            isinstance(item, dict)
            for item in (inputs, outputs, facts, point_inputs, point_outputs)
        )
        or not all(
            facts.get(key) is True
            for key in (
                "output_count_equals_count",
                "first_value_equals_start",
                "successive_difference_equals_step",
            )
        )
        or selected_point is None
        or selected_point[0].get("id") != point_component.get("id")
        or selected_point[1].get("idx") != point_outputs.get("point")
    ):
        return False
    return all(
        [
            snapshot.connected(controls["Start"], 0, series_component, inputs.get("start")),
            snapshot.connected(controls["Step"], 0, series_component, inputs.get("step")),
            snapshot.connected(controls["Count"], 0, series_component, inputs.get("count")),
            snapshot.connected(series_component, outputs.get("values"), point_component, point_inputs.get("x")),
        ]
    )


def _point_data(snapshot: _Snapshot) -> tuple[dict[str, Any] | None, list[tuple[Decimal, Decimal, Decimal]]]:
    selected = snapshot.point_output()
    if selected is None:
        return None, []
    data = selected[1].get("data")
    if not isinstance(data, dict):
        return None, []
    preview = data.get("preview")
    if not isinstance(preview, list):
        return data, []
    points = [_point(item) for item in preview]
    return data, [item for item in points if item is not None]


def _fixed_zero_source(snapshot: _Snapshot, component: dict[str, Any], input_index: int) -> bool:
    sources = snapshot.incoming.get((component.get("id"), input_index), [])
    if len(sources) != 1:
        return False
    source = snapshot.by_id.get(sources[0][0])
    if source is None or any(key[0] == source.get("id") for key in snapshot.incoming):
        return False
    value = source.get("value")
    return (
        isinstance(value, dict)
        and value.get("type") == "panel"
        and _decimal(value.get("val")) == 0
    )


def _yz_structurally_zero(snapshot: _Snapshot) -> bool:
    primitive = snapshot.primitive("construct_point")
    if primitive is None:
        return False
    component, semantics = primitive
    inputs = semantics.get("inputs")
    facts = semantics.get("facts")
    component_inputs = component.get("inputs")
    if not isinstance(inputs, dict) or not isinstance(facts, dict) or not isinstance(component_inputs, list):
        return False
    by_index = {
        item.get("idx"): item
        for item in component_inputs
        if isinstance(item, dict) and isinstance(item.get("idx"), int)
    }
    for axis in ("y", "z"):
        index = inputs.get(axis)
        observed = by_index.get(index)
        if not isinstance(observed, dict) or not isinstance(observed.get("sources"), int):
            return False
        if observed["sources"] == 0:
            if _decimal(facts.get(f"unconnected_{axis}_default")) != 0:
                return False
        elif observed["sources"] == 1:
            if not _fixed_zero_source(snapshot, component, index):
                return False
        else:
            return False
    return True


def evaluate(acceptance: dict[str, Any], snapshot_path: Path) -> dict[str, Any]:
    data, source_sha256 = _load_snapshot(Path(snapshot_path))
    snapshot = _Snapshot(data, acceptance["reviewed_primitive_semantics"])
    controls, control_states = snapshot.controls()
    point_data, points = _point_data(snapshot)
    series_path = _series_path(snapshot, controls)
    criteria: list[dict[str, Any]] = []

    requirement_failures = [
        requirement
        for nickname, requirement in _CONTROL_REQUIREMENTS
        if control_states.get(nickname) == "missing"
    ]
    if requirement_failures:
        control_status = "fail"
    elif all(control_states.get(nickname) == "admitted" for nickname, _ in _CONTROL_REQUIREMENTS):
        control_status = "pass"
    else:
        control_status = "unproven"
    criteria.append(
        _result(
            "adjustable_controls_present",
            control_status,
            {"controls": control_states},
            requirement_failures,
        )
    )

    count_value = _decimal(controls.get("Count", {}).get("value", {}).get("val"))
    point_count = point_data.get("count") if isinstance(point_data, dict) else None
    if count_value is None or isinstance(point_count, bool) or not isinstance(point_count, int):
        status = "unproven"
    elif count_value != point_count:
        status = "fail"
    else:
        status = "pass" if series_path else "unproven"
    criteria.append(
        _result(
            "point_count_equals_count",
            status,
            {"count_control": str(count_value) if count_value is not None else None, "point_count": point_count, "reviewed_causal_path": series_path},
            ["point_count_equals_count"] if status == "fail" else [],
        )
    )

    start_value = _decimal(controls.get("Start", {}).get("value", {}).get("val"))
    first_x = points[0][0] if points else None
    if series_path:
        status = "pass"
    elif start_value is None or first_x is None:
        status = "unproven"
    elif first_x != start_value:
        status = "fail"
    else:
        status = "unproven"
    criteria.append(
        _result(
            "first_x_equals_start",
            status,
            {"start": str(start_value) if start_value is not None else None, "first_x_preview": str(first_x) if first_x is not None else None, "preview_matches": start_value is not None and first_x is not None and first_x == start_value, "reviewed_causal_path": series_path},
            ["first_x_equals_start"] if status == "fail" else [],
        )
    )

    step_value = _decimal(controls.get("Step", {}).get("value", {}).get("val"))
    differences = [points[index + 1][0] - points[index][0] for index in range(len(points) - 1)]
    if series_path:
        status = "pass"
    elif step_value is None or not differences:
        status = "unproven"
    elif any(difference != step_value for difference in differences):
        status = "fail"
    else:
        status = "unproven"
    criteria.append(
        _result(
            "successive_x_difference_equals_step",
            status,
            {"step": str(step_value) if step_value is not None else None, "preview_differences": [str(item) for item in differences], "preview_matches": step_value is not None and bool(differences) and all(item == step_value for item in differences), "reviewed_causal_path": series_path},
            ["successive_x_difference_equals_step"] if status == "fail" else [],
        )
    )

    nonzero_preview = any(point[1] != 0 or point[2] != 0 for point in points)
    structurally_zero = _yz_structurally_zero(snapshot)
    if nonzero_preview:
        status = "fail"
    elif not points or not structurally_zero:
        status = "unproven"
    else:
        status = "pass"
    criteria.append(
        _result(
            "all_yz_zero",
            status,
            {"preview_points_observed": len(points), "nonzero_preview": nonzero_preview, "structurally_fixed_zero": structurally_zero},
            ["all_yz_zero"] if status == "fail" else [],
        )
    )

    diagnostics = data.get("diagnostics")
    errors = diagnostics.get("errors") if isinstance(diagnostics, dict) else None
    if isinstance(errors, bool) or not isinstance(errors, int) or errors < 0:
        status = "unproven"
    else:
        status = "pass" if errors == 0 else "fail"
    criteria.append(
        _result(
            "no_runtime_errors",
            status,
            {"errors": errors},
            ["no_runtime_errors"] if status == "fail" else [],
        )
    )

    failure_ids = [failure for item in criteria for failure in item["failure_ids"]]
    if failure_ids:
        overall = "fail"
    elif any(item["status"] == "unproven" for item in criteria):
        overall = "incomplete"
    else:
        overall = "pass"
    return {
        "schema": _EVALUATION_SCHEMA,
        "acceptance_schema": acceptance["schema"],
        "snapshot_sha256": source_sha256,
        "overall": overall,
        "failure_ids": failure_ids,
        "criteria": criteria,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acceptance", type=Path)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args(argv)
    try:
        result = evaluate(load_acceptance(args.acceptance), args.snapshot)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
