from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_REFERENCE_IDS = {"front_child", "wide_front", "side_recline", "architectural_wide"}
REQUIRED_FRAME_IDS = {
    "root_frame",
    "torso_frame",
    "head_frame",
    "left_shoulder_frame",
    "right_shoulder_frame",
    "left_hip_frame",
    "right_hip_frame",
}
REQUIRED_PART_IDS = {
    "torso_back_slab",
    "torso_front_panel",
    "head_box",
    "left_eye",
    "right_eye",
    "mouth_slot",
    "left_arm_upper_side_block",
    "right_arm_upper_side_block",
    "left_leg_thigh_block",
    "right_leg_thigh_block",
    "left_leg_foot_block",
    "right_leg_foot_block",
    "left_foot_slot",
    "right_foot_slot",
}
VALID_PART_TYPES = {"box", "wedge", "slot", "face_detail"}


def _is_vec3(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
    )


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_recipe(recipe: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    _require(recipe.get("project") == "pearson_robot", "project must be pearson_robot", errors)
    _require(recipe.get("revision") == "r001", "revision must be r001 for the first pass", errors)
    _require(recipe.get("units", {}).get("rhino_unit") == "meter", "units.rhino_unit must be meter", errors)

    convention = recipe.get("coordinate_convention", {})
    _require(convention.get("x") == "robot_anatomical_left", "x axis must be robot anatomical left", errors)
    _require(convention.get("y") == "robot_forward_toward_feet", "y axis must be robot forward", errors)
    _require(convention.get("z") == "up", "z axis must be up", errors)

    references = recipe.get("reference_images", [])
    _require(isinstance(references, list), "reference_images must be a list", errors)
    reference_ids = {item.get("id") for item in references if isinstance(item, dict)}
    _require(REQUIRED_REFERENCE_IDS.issubset(reference_ids), "all required reference ids must exist", errors)
    for item in references:
        if not isinstance(item, dict):
            errors.append("each reference image must be an object")
            continue
        _require(isinstance(item.get("path"), str) and item["path"], f"reference {item.get('id')} needs path", errors)
        _require(
            isinstance(item.get("description"), str) and item["description"],
            f"reference {item.get('id')} needs description",
            errors,
        )

    materials = recipe.get("materials", {})
    _require(isinstance(materials, dict), "materials must be an object", errors)
    for name, material in materials.items():
        if not isinstance(material, dict):
            errors.append(f"material {name} must be an object")
            continue
        diffuse = material.get("diffuse")
        _require(
            isinstance(diffuse, list)
            and len(diffuse) == 3
            and all(isinstance(channel, int) and 0 <= channel <= 255 for channel in diffuse),
            f"material {name} diffuse must be three 0-255 integers",
            errors,
        )

    layers = recipe.get("layers", {})
    _require(isinstance(layers, dict), "layers must be an object", errors)
    _require(layers.get("root") == "Pearson Robot", "root layer must be Pearson Robot", errors)

    frames = recipe.get("frames", [])
    _require(isinstance(frames, list), "frames must be a list", errors)
    frame_ids = {frame.get("id") for frame in frames if isinstance(frame, dict)}
    _require(REQUIRED_FRAME_IDS.issubset(frame_ids), "all required frame ids must exist", errors)
    for frame in frames:
        if not isinstance(frame, dict):
            errors.append("each frame must be an object")
            continue
        _require(_is_vec3(frame.get("origin")), f"frame {frame.get('id')} origin must be vec3", errors)
        _require(
            _is_vec3(frame.get("rotation_degrees")),
            f"frame {frame.get('id')} rotation_degrees must be vec3",
            errors,
        )
        parent = frame.get("parent")
        _require(parent is None or parent in frame_ids, f"frame {frame.get('id')} parent must exist", errors)

    parts = recipe.get("parts", [])
    _require(isinstance(parts, list), "parts must be a list", errors)
    part_ids = {part.get("id") for part in parts if isinstance(part, dict)}
    _require(REQUIRED_PART_IDS.issubset(part_ids), "all required part ids must exist", errors)
    _require(len(parts) == len(part_ids), "part ids must be unique", errors)
    for part in parts:
        if not isinstance(part, dict):
            errors.append("each part must be an object")
            continue
        part_id = part.get("id")
        part_type = part.get("type")
        _require(part_type in VALID_PART_TYPES, f"part {part_id} has invalid type", errors)
        _require(part.get("frame") in frame_ids, f"part {part_id} frame must exist", errors)
        _require(part.get("layer") in layers, f"part {part_id} layer key must exist", errors)
        _require(part.get("material") in materials, f"part {part_id} material must exist", errors)
        _require(_is_vec3(part.get("center")), f"part {part_id} center must be vec3", errors)
        _require(_is_vec3(part.get("size")), f"part {part_id} size must be vec3", errors)
        if _is_vec3(part.get("size")):
            _require(all(value > 0 for value in part["size"]), f"part {part_id} size values must be positive", errors)
        _require(_is_vec3(part.get("rotation_degrees")), f"part {part_id} rotation_degrees must be vec3", errors)
        if part_type == "wedge":
            _require(isinstance(part.get("slope"), (int, float)), f"wedge {part_id} needs numeric slope", errors)

    named_views = recipe.get("named_views", [])
    _require(isinstance(named_views, list), "named_views must be a list", errors)
    view_names = {view.get("name") for view in named_views if isinstance(view, dict)}
    _require(
        {"robot_front_child_view", "robot_side_recline_view", "robot_architectural_wide_view"}.issubset(view_names),
        "required named views must exist",
        errors,
    )
    for view in named_views:
        if not isinstance(view, dict):
            errors.append("each named view must be an object")
            continue
        _require(view.get("reference_image_id") in reference_ids, f"view {view.get('name')} reference must exist", errors)
        _require(_is_vec3(view.get("camera_location")), f"view {view.get('name')} camera_location must be vec3", errors)
        _require(_is_vec3(view.get("target")), f"view {view.get('name')} target must be vec3", errors)

    left_ids = [part_id for part_id in part_ids if isinstance(part_id, str) and part_id.startswith("left_")]
    right_ids = [part_id for part_id in part_ids if isinstance(part_id, str) and part_id.startswith("right_")]
    _require(bool(left_ids) and bool(right_ids), "recipe must include anatomical left and right parts", errors)

    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate_robot_recipe.py <recipe.json>", file=sys.stderr)
        return 2

    recipe_path = Path(argv[1])
    try:
        recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"failed to read recipe: {exc}", file=sys.stderr)
        return 1

    errors = validate_recipe(recipe)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"recipe valid: {recipe_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
