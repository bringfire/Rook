from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

from .loader import (
    CanvasDirectorTemplateError,
    load_template_pack,
    template_by_id,
    template_root,
    validate_template_pack,
)


CallTool = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


SCRIPT_ORDER = [
    "canvas_director.clock",
    "canvas_director.timing_gate",
    "canvas_director.oscillator",
    "canvas_director.actors_v2",
    "canvas_director.transform",
    "canvas_director.camera_path",
    "canvas_director.camera_controller",
    "canvas_director.export_marker",
]

NODE_ALIASES = {
    "canvas_director.clock": "clock",
    "canvas_director.timing_gate": "timing_gate",
    "canvas_director.oscillator": "oscillator",
    "canvas_director.actors_v2": "actors_v2",
    "canvas_director.transform": "transform",
    "canvas_director.camera_path": "camera_path",
    "canvas_director.camera_controller": "camera_controller",
    "canvas_director.export_marker": "export_marker",
}
SCRIPT_ALIASES = frozenset(NODE_ALIASES.values())


def build_instantiation_plan(fixture: dict[str, Any]) -> dict[str, Any]:
    pack = load_template_pack()
    errors = validate_template_pack(pack)
    if errors:
        raise CanvasDirectorTemplateError("invalid_template_pack", ";".join(errors))

    _validate_fixture(fixture)
    _validate_fixture_templates(fixture, pack)

    calls = _script_create_calls(pack, fixture)
    calls.append(
        {
            "tool": "gh_snapshot",
            "alias": "snapshot_before_edit",
            "arguments": {"include_data": False},
        }
    )

    deferred_edit = {
        "create": _control_create_ops(fixture),
        "connect": [
            "TActorSetControl.O0>actors_v2.I0",
            "TActorGroupingControl.O0>actors_v2.I1",
            "actors_v2.O1>transform.I0",
            "TMotionMaxHeightControl.O0>transform.I3",
            "TMotionSpreadControl.O0>transform.I4",
            "TMotionFastPreviewControl.O0>transform.I5",
            "TMotionStrategyControl.O0>transform.I6",
            "TCameraProjectionControl.O0>camera_controller.I5",
            "TCameraLensControl.O0>camera_controller.I4",
            "actors_v2.O1>export_marker.I0",
            "transform.O0>export_marker.I1",
            "camera_controller.O1>export_marker.I2",
            "TFpsControl.O0>export_marker.I3",
            "TFrameCountControl.O0>export_marker.I4",
            "TExportIdControl.O0>export_marker.I5",
            "TProposalIdControl.O0>export_marker.I6",
            "TResolutionControl.O0>export_marker.I7",
        ],
        "groups": [
            {
                "action": "create",
                "nick": "CanvasDirector Template Pack",
                "colour": "#B4D2F596",
                "members": [
                    "clock",
                    "timing_gate",
                    "oscillator",
                    "actors_v2",
                    "transform",
                    "camera_path",
                    "camera_controller",
                    "export_marker",
                ],
            }
        ],
    }
    calls.append(
        {
            "tool": "gh_edit",
            "alias": "deferred_wiring",
            "arguments": {
                "epoch": "$snapshot_before_edit.epoch",
                **deferred_edit,
            },
        }
    )

    return {
        "template_pack_id": pack["template_pack_id"],
        "template_pack_version": pack["template_pack_version"],
        "fixture_id": fixture["fixture_id"],
        "calls": calls,
        "deferred_edit": deferred_edit,
        "extract_tool": "rhino_director_canvas_extract",
        "extract_arguments": {
            "project_root": fixture["project_root"],
            "export_id": fixture["export_id"],
            "solve_mode": "require_fresh_solve",
        },
    }


async def instantiate_fixture(fixture: dict[str, Any], call_tool: CallTool) -> dict[str, Any]:
    plan = build_instantiation_plan(fixture)
    alias_results: dict[str, dict[str, Any]] = {}
    component_aliases: dict[str, str] = {}

    for call in plan["calls"]:
        tool = call["tool"]
        alias = call["alias"]
        arguments = deepcopy(call["arguments"])

        if tool == "gh_edit":
            arguments["epoch"] = _snapshot_epoch(alias_results)
            arguments["connect"] = [
                _resolve_flow_aliases(flow, component_aliases)
                for flow in arguments.get("connect", [])
            ]
            for group in arguments.get("groups", []):
                group["members"] = [
                    _resolve_node_alias(member, component_aliases)
                    for member in group.get("members", [])
                ]

        try:
            result = await call_tool(tool, arguments)
        except Exception as exc:
            raise CanvasDirectorTemplateError("tool_call_failed", f"{tool}:{exc}") from exc

        if not isinstance(result, dict) or not result.get("success", False):
            raise CanvasDirectorTemplateError("tool_call_failed", f"{tool}:{result}")

        alias_results[alias] = result
        if tool == "gh_create_script":
            component_aliases[alias] = _component_guid_from_result(alias, result)

    return {"success": True, "plan": plan, "results": alias_results}


def _pin_definitions(pins: list[dict[str, Any]], *, optional_default: bool | None) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    for pin in pins:
        definition = {
            "name": str(pin["name"]),
            "type": str(pin["type"]),
            "description": str(pin["description"]),
        }
        for key in ("nick", "access", "hidden"):
            if key in pin:
                definition[key] = pin[key]
        if "optional" in pin:
            definition["optional"] = bool(pin["optional"])
        elif optional_default is not None:
            definition["optional"] = optional_default
        definitions.append(definition)
    return definitions


def _script_create_calls(pack: dict[str, Any], fixture: dict[str, Any]) -> list[dict[str, Any]]:
    x0, y0 = fixture.get("layout", {}).get("origin", [-1200, -200])
    x_spacing = fixture.get("layout", {}).get("x_spacing", 260)
    y_spacing = fixture.get("layout", {}).get("y_spacing", 120)
    calls: list[dict[str, Any]] = []

    for index, template_id in enumerate(SCRIPT_ORDER):
        entry = template_by_id(pack, template_id)
        script_path = template_root() / entry["script"]["path"]
        calls.append(
            {
                "tool": "gh_create_script",
                "alias": NODE_ALIASES[template_id],
                "arguments": {
                    "language": "csharp",
                    "code": script_path.read_text(encoding="utf-8"),
                    "pins_in": _pin_definitions(entry["inputs"], optional_default=True),
                    "pins_out": _pin_definitions(entry["outputs"], optional_default=None),
                    "name": entry["display_name"],
                    "x": x0 + x_spacing * (index % 4),
                    "y": y0 + y_spacing * (index // 4),
                },
            }
        )
    return calls


def _validate_fixture(fixture: dict[str, Any]) -> None:
    errors: list[str] = []
    if not isinstance(fixture, dict):
        raise CanvasDirectorTemplateError("invalid_fixture", "fixture must be an object")

    for field_name in ("fixture_id", "project_root", "export_id", "proposal_id"):
        _require_string(fixture, field_name, errors)

    templates = fixture.get("templates")
    if not isinstance(templates, list) or not templates:
        errors.append("templates")
    elif not all(isinstance(item, str) and item.strip() for item in templates):
        errors.append("templates")

    timeline = _require_object(fixture, "timeline", errors)
    if timeline is not None:
        _require_number(timeline, "fps", errors, "timeline.fps")
        _require_number(timeline, "frame_count", errors, "timeline.frame_count")

    resolution = _require_object(fixture, "resolution", errors)
    if resolution is not None:
        _require_number(resolution, "width", errors, "resolution.width")
        _require_number(resolution, "height", errors, "resolution.height")

    actor_bindings = _require_object(fixture, "actor_bindings", errors)
    if actor_bindings is not None:
        _require_string(actor_bindings, "actor_set_ref", errors, "actor_bindings.actor_set_ref")
        _require_string(
            actor_bindings,
            "actor_grouping_ref",
            errors,
            "actor_bindings.actor_grouping_ref",
        )

    motion = _require_object(fixture, "motion", errors)
    if motion is not None:
        _require_string(motion, "strategy", errors, "motion.strategy")
        _require_number(motion, "max_height", errors, "motion.max_height")
        _require_number(motion, "spread", errors, "motion.spread")
        if not isinstance(motion.get("fast_preview"), bool):
            errors.append("motion.fast_preview")

    camera = _require_object(fixture, "camera", errors)
    if camera is not None:
        _require_string(camera, "projection", errors, "camera.projection")
        _require_number(camera, "lens_length", errors, "camera.lens_length")

    if "layout" in fixture:
        layout = fixture["layout"]
        if not isinstance(layout, dict):
            errors.append("layout")
        else:
            origin = layout.get("origin")
            if origin is not None and not _is_number_pair(origin):
                errors.append("layout.origin")
            for field_name in ("x_spacing", "y_spacing"):
                if field_name in layout:
                    _require_number(layout, field_name, errors, f"layout.{field_name}")

    if errors:
        raise CanvasDirectorTemplateError("invalid_fixture", ",".join(errors))


def _control_create_ops(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    timeline = fixture["timeline"]
    resolution = fixture["resolution"]
    actor_bindings = fixture["actor_bindings"]
    motion = fixture["motion"]
    camera = fixture["camera"]
    x0, y0 = fixture.get("layout", {}).get("origin", [-1200, -200])

    return [
        {
            "temp_id": "TActorSetControl",
            "type": "panel",
            "content": actor_bindings["actor_set_ref"],
            "pos": [x0, y0 + 220],
        },
        {
            "temp_id": "TActorGroupingControl",
            "type": "panel",
            "content": actor_bindings["actor_grouping_ref"],
            "pos": [x0, y0 + 280],
        },
        {
            "temp_id": "TFpsControl",
            "type": "slider",
            "nick": "FPS",
            "min": 1,
            "max": 120,
            "value": timeline["fps"],
            "pos": [x0, y0],
        },
        {
            "temp_id": "TFrameCountControl",
            "type": "slider",
            "nick": "FrameCount",
            "min": 1,
            "max": 10000,
            "value": timeline["frame_count"],
            "pos": [x0, y0 + 60],
        },
        {
            "temp_id": "TExportIdControl",
            "type": "panel",
            "content": fixture["export_id"],
            "pos": [x0, y0 + 420],
        },
        {
            "temp_id": "TProposalIdControl",
            "type": "panel",
            "content": fixture["proposal_id"],
            "pos": [x0, y0 + 480],
        },
        {
            "temp_id": "TResolutionControl",
            "type": "panel",
            "content": f"{resolution['width']}x{resolution['height']}",
            "pos": [x0, y0 + 540],
        },
        {
            "temp_id": "TMotionStrategyControl",
            "type": "panel",
            "content": motion["strategy"],
            "pos": [x0, y0 + 660],
        },
        {
            "temp_id": "TMotionMaxHeightControl",
            "type": "slider",
            "nick": "MaxH",
            "min": 0,
            "max": 50000,
            "value": motion["max_height"],
            "pos": [x0, y0 + 720],
        },
        {
            "temp_id": "TMotionSpreadControl",
            "type": "slider",
            "nick": "Spread",
            "min": 0,
            "max": 200,
            "value": motion["spread"],
            "pos": [x0, y0 + 780],
        },
        {
            "temp_id": "TMotionFastPreviewControl",
            "type": "toggle",
            "value": motion["fast_preview"],
            "pos": [x0, y0 + 840],
        },
        {
            "temp_id": "TCameraProjectionControl",
            "type": "panel",
            "content": camera["projection"],
            "pos": [x0, y0 + 960],
        },
        {
            "temp_id": "TCameraLensControl",
            "type": "slider",
            "nick": "Lens",
            "min": 1,
            "max": 200,
            "value": camera["lens_length"],
            "pos": [x0, y0 + 1020],
        },
    ]


def _require_object(
    value: dict[str, Any],
    field_name: str,
    errors: list[str],
) -> dict[str, Any] | None:
    nested = value.get(field_name)
    if not isinstance(nested, dict):
        errors.append(field_name)
        return None
    return nested


def _require_string(
    value: dict[str, Any],
    field_name: str,
    errors: list[str],
    label: str | None = None,
) -> None:
    if not isinstance(value.get(field_name), str) or not value[field_name].strip():
        errors.append(label or field_name)


def _require_number(
    value: dict[str, Any],
    field_name: str,
    errors: list[str],
    label: str,
) -> None:
    if not _is_number(value.get(field_name)):
        errors.append(label)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_number_pair(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(_is_number(item) for item in value)
    )


def _validate_fixture_templates(fixture: dict[str, Any], pack: dict[str, Any]) -> None:
    fixture_templates = fixture.get("templates")
    if not isinstance(fixture_templates, list):
        raise CanvasDirectorTemplateError("invalid_fixture", "templates must be a list")

    pack_template_ids = {
        entry["template_id"]
        for entry in pack.get("templates", [])
        if isinstance(entry, dict) and isinstance(entry.get("template_id"), str)
    }
    missing = sorted(set(SCRIPT_ORDER) - set(fixture_templates))
    unknown = sorted(set(fixture_templates) - pack_template_ids)
    if missing:
        raise CanvasDirectorTemplateError("invalid_fixture", f"missing templates: {missing}")
    if unknown:
        raise CanvasDirectorTemplateError("invalid_fixture", f"unknown templates: {unknown}")


def _snapshot_epoch(alias_results: dict[str, dict[str, Any]]) -> int:
    snapshot = alias_results.get("snapshot_before_edit")
    if not isinstance(snapshot, dict):
        raise CanvasDirectorTemplateError("missing_snapshot_epoch", "snapshot_before_edit")

    data = snapshot.get("data", snapshot)
    if not isinstance(data, dict) or not isinstance(data.get("epoch"), int):
        raise CanvasDirectorTemplateError("missing_snapshot_epoch", "snapshot_before_edit")
    return data["epoch"]


def _component_guid_from_result(alias: str, result: dict[str, Any]) -> str:
    data = result.get("data", result)
    if not isinstance(data, dict):
        raise CanvasDirectorTemplateError("missing_component_guid", alias)

    component_guid = data.get("component_guid")
    if not isinstance(component_guid, str) or not component_guid.strip():
        raise CanvasDirectorTemplateError("missing_component_guid", alias)
    return component_guid


def _resolve_flow_aliases(flow: str, component_aliases: dict[str, str]) -> str:
    left, right = flow.split(">", 1)
    source, output = left.split(".", 1)
    target, input_pin = right.split(".", 1)
    return (
        f"{_resolve_node_alias(source, component_aliases)}.{output}>"
        f"{_resolve_node_alias(target, component_aliases)}.{input_pin}"
    )


def _resolve_node_alias(node_id: str, component_aliases: dict[str, str]) -> str:
    if node_id in component_aliases:
        return component_aliases[node_id]
    if node_id in SCRIPT_ALIASES:
        raise CanvasDirectorTemplateError("missing_component_guid", node_id)
    return node_id
