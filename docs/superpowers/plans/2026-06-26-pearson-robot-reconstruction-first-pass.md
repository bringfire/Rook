# Pearson Robot Reconstruction First Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended for this live Rhino workflow) or superpowers:subagent-driven-development only for narrow pure-Python review tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first recognizable, regenerable study model of the Pearson / ArtScience Laboratory turquoise robot in Rhino from a semantic recipe.

**Architecture:** Create a repo-local experiment folder whose recipe is the source of truth, then generate a Rhino Python script from that recipe and execute it through Rook's existing `rhino_execute` surface. Keep geometry creation in Rhino, but keep validation, recipe integrity checks, and script generation testable as pure Python so most mistakes are caught before mutating a Rhino document.

**Tech Stack:** Python standard library, `pytest`, JSON recipe files, Rhino Python via `rhinoscriptsyntax` and `Rhino.Geometry`, existing Rook MCP tools (`rhino_execute`, `rhino_views`, `rhino_views_restore`, `rhino_viewport`), no new external dependencies.

---

## Spec Reference

Use `docs/superpowers/specs/2026-06-26-pearson-robot-semantic-parametric-reconstruction-design.md` as the controlling design.

Important invariants:

- Units are meters: `1 Rhino unit = 1 meter`.
- Semantic ids use robot-anatomical left/right, not viewer-left/right.
- `+Z` is up, `+Y` is robot forward toward feet, `+X` is robot anatomical left.
- The Rhino model is generated from `experiments/pearson_robot/robot_recipe.json`.
- Rhino layers and user strings are working memory, not decoration.
- The first pass is a recognizable study model, not fabrication or photogrammetry.

## File Map

- Create `experiments/pearson_robot/README.md`
  - Human entry point for the experiment, reference image paths, unit convention, and run sequence.
- Create `experiments/pearson_robot/robot_recipe.json`
  - Machine-readable source of truth for units, references, layers, materials, frames, parts, named views, and revision.
- Create `experiments/pearson_robot/ITERATIONS.md`
  - Durable modeling log for context-compaction recovery.
- Create `experiments/pearson_robot/scripts/validate_robot_recipe.py`
  - Pure-Python validator for the recipe schema and first-pass semantic invariants.
- Create `experiments/pearson_robot/scripts/build_rhino_script.py`
  - Pure-Python generator that embeds the recipe into a Rhino-executable script.
- Create `experiments/pearson_robot/generated/.gitkeep`
  - Keeps the generated output directory visible while generated scripts/screenshots can remain local unless promoted as evidence.
- Create `experiments/pearson_robot/tests/test_robot_recipe.py`
  - Tests the committed recipe has required semantic structure and reference paths.
- Create `experiments/pearson_robot/tests/test_rhino_script_generation.py`
  - Tests that script generation is deterministic and includes expected metadata/layer operations.

Generated but not normally committed:

- `experiments/pearson_robot/generated/pearson_robot_rhino.py`
  - Rhino script produced by `build_rhino_script.py`.
- `experiments/pearson_robot/screenshots/*.png`
  - Optional viewport evidence; commit only intentionally selected checkpoint images.
- `experiments/pearson_robot/exports/*.3dm`
  - Optional exported Rhino files; usually local scratch unless promoted as checkpoint evidence.

## Task 1: Create Experiment Skeleton and Initial Recipe

**Files:**
- Create: `experiments/pearson_robot/README.md`
- Create: `experiments/pearson_robot/robot_recipe.json`
- Create: `experiments/pearson_robot/ITERATIONS.md`
- Create: `experiments/pearson_robot/generated/.gitkeep`
- Test: `experiments/pearson_robot/tests/test_robot_recipe.py`

- [ ] **Step 1: Create the experiment folders**

Run:

```powershell
New-Item -ItemType Directory -Force -Path `
  'experiments\pearson_robot', `
  'experiments\pearson_robot\scripts', `
  'experiments\pearson_robot\tests', `
  'experiments\pearson_robot\generated', `
  'experiments\pearson_robot\screenshots', `
  'experiments\pearson_robot\exports'
```

Expected: directories exist.

- [ ] **Step 2: Create the README**

Create `experiments/pearson_robot/README.md` with:

```markdown
# Pearson Robot Reconstruction Experiment

This experiment builds a recognizable study model of the turquoise robot installation from `H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT`.

## References

- `H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT\image.png`
- `H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT\image (1).png`
- `H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT\image (2).png`
- `H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT\image (3).png`

## Units and Axes

- `1 Rhino unit = 1 meter`
- `+Z`: up
- `+Y`: robot forward, from torso toward feet
- `+X`: robot anatomical left
- Semantic `left_*` and `right_*` ids are robot-anatomical, not viewer-left/viewer-right.

## Workflow

1. Validate the recipe:
   `python experiments\pearson_robot\scripts\validate_robot_recipe.py experiments\pearson_robot\robot_recipe.json`
2. Generate the Rhino script:
   `python experiments\pearson_robot\scripts\build_rhino_script.py experiments\pearson_robot\robot_recipe.json experiments\pearson_robot\generated\pearson_robot_rhino.py`
3. Execute the generated script in Rhino through Rook `rhino_execute`.
4. Restore/capture named views through `rhino_views_restore` and `rhino_viewport`.
5. Record the result in `ITERATIONS.md`.
```

- [ ] **Step 3: Create the initial recipe**

Create `experiments/pearson_robot/robot_recipe.json` with this first-pass content:

```json
{
  "project": "pearson_robot",
  "revision": "r001",
  "units": {
    "rhino_unit": "meter",
    "scale_note": "1 Rhino unit = 1 meter"
  },
  "coordinate_convention": {
    "x": "robot_anatomical_left",
    "y": "robot_forward_toward_feet",
    "z": "up",
    "origin": "centered near root seat and lower torso base"
  },
  "reference_images": [
    {
      "id": "front_child",
      "path": "H:\\AI EXPERIMENTS\\Pearson\\reference_images\\ROBOT\\image.png",
      "description": "Front-ish portrait view with child seated on viewer-left side."
    },
    {
      "id": "wide_front",
      "path": "H:\\AI EXPERIMENTS\\Pearson\\reference_images\\ROBOT\\image (1).png",
      "description": "Wide front frame with wall context and people for scale."
    },
    {
      "id": "side_recline",
      "path": "H:\\AI EXPERIMENTS\\Pearson\\reference_images\\ROBOT\\image (2).png",
      "description": "Side reclined view, best for torso lean and seat/leg structure."
    },
    {
      "id": "architectural_wide",
      "path": "H:\\AI EXPERIMENTS\\Pearson\\reference_images\\ROBOT\\image (3).png",
      "description": "Wide architectural view, best for footprint and room relationship."
    }
  ],
  "materials": {
    "robot_turquoise": {
      "diffuse": [0, 188, 186],
      "description": "Matte saturated cyan/turquoise robot paint."
    },
    "slot_dark": {
      "diffuse": [18, 76, 86],
      "description": "Dark teal recess material for slots and face details."
    },
    "skeleton_debug": {
      "diffuse": [255, 225, 80],
      "description": "Temporary skeleton/frame marker material."
    }
  },
  "layers": {
    "root": "Pearson Robot",
    "reference": "Pearson Robot::00 Reference",
    "skeleton": "Pearson Robot::01 Skeleton",
    "torso": "Pearson Robot::02 Torso",
    "head": "Pearson Robot::03 Head",
    "left_arm": "Pearson Robot::04 Arms::Left",
    "right_arm": "Pearson Robot::04 Arms::Right",
    "left_leg": "Pearson Robot::05 Legs::Left",
    "right_leg": "Pearson Robot::05 Legs::Right",
    "details": "Pearson Robot::06 Details",
    "cameras": "Pearson Robot::90 Cameras",
    "debug": "Pearson Robot::99 Debug"
  },
  "frames": [
    {
      "id": "root_frame",
      "parent": null,
      "origin": [0.0, 0.0, 0.45],
      "rotation_degrees": [0.0, 0.0, 0.0],
      "description": "Seat/root frame near lower torso base."
    },
    {
      "id": "torso_frame",
      "parent": "root_frame",
      "origin": [0.0, -0.25, 0.65],
      "rotation_degrees": [-22.0, 0.0, 0.0],
      "description": "Reclined torso frame."
    },
    {
      "id": "head_frame",
      "parent": "torso_frame",
      "origin": [0.0, -1.55, 2.10],
      "rotation_degrees": [-12.0, 0.0, 0.0],
      "description": "Small tilted head frame."
    },
    {
      "id": "left_shoulder_frame",
      "parent": "torso_frame",
      "origin": [1.15, -0.85, 1.05],
      "rotation_degrees": [-12.0, 0.0, 4.0],
      "description": "Robot anatomical left shoulder/arm frame."
    },
    {
      "id": "right_shoulder_frame",
      "parent": "torso_frame",
      "origin": [-1.15, -0.85, 1.05],
      "rotation_degrees": [-12.0, 0.0, -4.0],
      "description": "Robot anatomical right shoulder/arm frame."
    },
    {
      "id": "left_hip_frame",
      "parent": "root_frame",
      "origin": [0.55, 0.80, 0.42],
      "rotation_degrees": [0.0, 0.0, 8.0],
      "description": "Robot anatomical left hip/leg frame."
    },
    {
      "id": "right_hip_frame",
      "parent": "root_frame",
      "origin": [-0.55, 0.80, 0.42],
      "rotation_degrees": [0.0, 0.0, -8.0],
      "description": "Robot anatomical right hip/leg frame."
    }
  ],
  "parts": [
    {
      "id": "torso_back_slab",
      "parent": "robot",
      "frame": "torso_frame",
      "type": "box",
      "role": "torso",
      "layer": "torso",
      "material": "robot_turquoise",
      "center": [0.0, 0.0, 0.0],
      "size": [2.2, 0.32, 2.15],
      "rotation_degrees": [0.0, 0.0, 0.0]
    },
    {
      "id": "torso_front_panel",
      "parent": "torso_back_slab",
      "frame": "torso_frame",
      "type": "wedge",
      "role": "torso_panel",
      "layer": "torso",
      "material": "robot_turquoise",
      "center": [0.0, 0.42, -0.18],
      "size": [2.0, 0.70, 1.85],
      "rotation_degrees": [0.0, 0.0, 0.0],
      "slope_axis": "y",
      "slope": 0.22
    },
    {
      "id": "head_box",
      "parent": "torso_back_slab",
      "frame": "head_frame",
      "type": "box",
      "role": "head",
      "layer": "head",
      "material": "robot_turquoise",
      "center": [0.0, 0.0, 0.0],
      "size": [0.72, 0.28, 0.48],
      "rotation_degrees": [0.0, 0.0, 0.0]
    },
    {
      "id": "left_eye",
      "parent": "head_box",
      "frame": "head_frame",
      "type": "face_detail",
      "role": "eye",
      "layer": "details",
      "material": "slot_dark",
      "center": [0.18, 0.155, 0.10],
      "size": [0.08, 0.025, 0.08],
      "rotation_degrees": [0.0, 0.0, 0.0]
    },
    {
      "id": "right_eye",
      "parent": "head_box",
      "frame": "head_frame",
      "type": "face_detail",
      "role": "eye",
      "layer": "details",
      "material": "slot_dark",
      "center": [-0.18, 0.155, 0.10],
      "size": [0.08, 0.025, 0.08],
      "rotation_degrees": [0.0, 0.0, 0.0]
    },
    {
      "id": "mouth_slot",
      "parent": "head_box",
      "frame": "head_frame",
      "type": "slot",
      "role": "mouth",
      "layer": "details",
      "material": "slot_dark",
      "center": [0.0, 0.16, -0.08],
      "size": [0.44, 0.035, 0.07],
      "rotation_degrees": [0.0, 0.0, 0.0]
    },
    {
      "id": "left_arm_upper_side_block",
      "parent": "torso_back_slab",
      "frame": "left_shoulder_frame",
      "type": "box",
      "role": "armrest",
      "layer": "left_arm",
      "material": "robot_turquoise",
      "center": [0.0, 0.0, -0.22],
      "size": [0.58, 1.50, 1.45],
      "rotation_degrees": [0.0, 0.0, 0.0]
    },
    {
      "id": "right_arm_upper_side_block",
      "parent": "torso_back_slab",
      "frame": "right_shoulder_frame",
      "type": "box",
      "role": "armrest",
      "layer": "right_arm",
      "material": "robot_turquoise",
      "center": [0.0, 0.0, -0.22],
      "size": [0.58, 1.50, 1.45],
      "rotation_degrees": [0.0, 0.0, 0.0]
    },
    {
      "id": "left_leg_thigh_block",
      "parent": "robot",
      "frame": "left_hip_frame",
      "type": "box",
      "role": "seat",
      "layer": "left_leg",
      "material": "robot_turquoise",
      "center": [0.0, 0.55, 0.0],
      "size": [0.72, 1.45, 0.46],
      "rotation_degrees": [0.0, 0.0, 0.0]
    },
    {
      "id": "right_leg_thigh_block",
      "parent": "robot",
      "frame": "right_hip_frame",
      "type": "box",
      "role": "seat",
      "layer": "right_leg",
      "material": "robot_turquoise",
      "center": [0.0, 0.55, 0.0],
      "size": [0.72, 1.45, 0.46],
      "rotation_degrees": [0.0, 0.0, 0.0]
    },
    {
      "id": "left_leg_foot_block",
      "parent": "left_leg_thigh_block",
      "frame": "left_hip_frame",
      "type": "wedge",
      "role": "foot",
      "layer": "left_leg",
      "material": "robot_turquoise",
      "center": [0.0, 1.55, -0.02],
      "size": [0.82, 1.05, 0.58],
      "rotation_degrees": [0.0, 0.0, 0.0],
      "slope_axis": "y",
      "slope": -0.18
    },
    {
      "id": "right_leg_foot_block",
      "parent": "right_leg_thigh_block",
      "frame": "right_hip_frame",
      "type": "wedge",
      "role": "foot",
      "layer": "right_leg",
      "material": "robot_turquoise",
      "center": [0.0, 1.55, -0.02],
      "size": [0.82, 1.05, 0.58],
      "rotation_degrees": [0.0, 0.0, 0.0],
      "slope_axis": "y",
      "slope": -0.18
    },
    {
      "id": "left_foot_slot",
      "parent": "left_leg_foot_block",
      "frame": "left_hip_frame",
      "type": "slot",
      "role": "foot_slot",
      "layer": "details",
      "material": "slot_dark",
      "center": [0.0, 2.05, 0.06],
      "size": [0.08, 0.035, 0.36],
      "rotation_degrees": [0.0, 0.0, 0.0]
    },
    {
      "id": "right_foot_slot",
      "parent": "right_leg_foot_block",
      "frame": "right_hip_frame",
      "type": "slot",
      "role": "foot_slot",
      "layer": "details",
      "material": "slot_dark",
      "center": [0.0, 2.05, 0.06],
      "size": [0.08, 0.035, 0.36],
      "rotation_degrees": [0.0, 0.0, 0.0]
    }
  ],
  "named_views": [
    {
      "name": "robot_front_child_view",
      "reference_image_id": "front_child",
      "camera_location": [0.0, 6.6, 2.0],
      "target": [0.0, 0.6, 0.95],
      "lens_length": 28.0
    },
    {
      "name": "robot_side_recline_view",
      "reference_image_id": "side_recline",
      "camera_location": [-5.2, 3.6, 1.9],
      "target": [0.0, 0.5, 0.9],
      "lens_length": 28.0
    },
    {
      "name": "robot_architectural_wide_view",
      "reference_image_id": "architectural_wide",
      "camera_location": [-4.8, 6.2, 2.2],
      "target": [0.0, 0.7, 0.95],
      "lens_length": 24.0
    }
  ]
}
```

- [ ] **Step 4: Create the iteration log**

Create `experiments/pearson_robot/ITERATIONS.md` with:

```markdown
# Pearson Robot Iterations

## r001 - Initial semantic recipe

Status: planned

Intent:
- Establish meters, coordinate convention, reference paths, layer names, and first-pass semantic parts.
- Generate a recognizable blocky robot with reclined torso, tilted head, arms, legs, face details, and foot slots.

Known inaccuracies before first Rhino run:
- Dimensions are approximate.
- The torso/arm/leg intersections are expected to need visual adjustment.
- Camera views are rough, not calibrated to the photographs.

Next action:
- Validate the recipe and generate the first Rhino script.
```

- [ ] **Step 5: Keep generated directory in git**

Create `experiments/pearson_robot/generated/.gitkeep` as an empty file.

- [ ] **Step 6: Commit skeleton and recipe**

Run:

```powershell
git add experiments\pearson_robot\README.md `
  experiments\pearson_robot\robot_recipe.json `
  experiments\pearson_robot\ITERATIONS.md `
  experiments\pearson_robot\generated\.gitkeep
git commit -m "chore: add Pearson robot experiment recipe"
```

Expected: one commit containing only durable experiment source files.

## Task 2: Add Pure-Python Recipe Validator

**Files:**
- Create: `experiments/pearson_robot/scripts/validate_robot_recipe.py`
- Create: `experiments/pearson_robot/tests/test_robot_recipe.py`

- [ ] **Step 1: Write failing recipe validation tests**

Create `experiments/pearson_robot/tests/test_robot_recipe.py`:

```python
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT = ROOT / "experiments" / "pearson_robot"
RECIPE = EXPERIMENT / "robot_recipe.json"
VALIDATOR = EXPERIMENT / "scripts" / "validate_robot_recipe.py"


def load_recipe():
    return json.loads(RECIPE.read_text(encoding="utf-8"))


def test_recipe_declares_meter_units_and_axis_convention():
    recipe = load_recipe()
    assert recipe["units"]["rhino_unit"] == "meter"
    assert recipe["coordinate_convention"]["x"] == "robot_anatomical_left"
    assert recipe["coordinate_convention"]["y"] == "robot_forward_toward_feet"
    assert recipe["coordinate_convention"]["z"] == "up"


def test_recipe_references_all_four_source_images():
    recipe = load_recipe()
    paths = {item["path"] for item in recipe["reference_images"]}
    assert paths == {
        r"H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT\image.png",
        r"H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT\image (1).png",
        r"H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT\image (2).png",
        r"H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT\image (3).png",
    }


def test_recipe_has_expected_semantic_parts():
    recipe = load_recipe()
    part_ids = {part["id"] for part in recipe["parts"]}
    assert {
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
    }.issubset(part_ids)


def test_validator_accepts_committed_recipe():
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(RECIPE)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "recipe valid" in result.stdout
```

- [ ] **Step 2: Run tests to verify validator is missing**

Run:

```powershell
python -m pytest experiments\pearson_robot\tests\test_robot_recipe.py -q
```

Expected: tests fail because `validate_robot_recipe.py` does not exist.

- [ ] **Step 3: Implement the validator**

Create `experiments/pearson_robot/scripts/validate_robot_recipe.py`:

```python
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
    _require(recipe.get("units", {}).get("rhino_unit") == "meter", "rhino_unit must be meter", errors)

    convention = recipe.get("coordinate_convention", {})
    _require(convention.get("x") == "robot_anatomical_left", "x axis convention is wrong", errors)
    _require(convention.get("y") == "robot_forward_toward_feet", "y axis convention is wrong", errors)
    _require(convention.get("z") == "up", "z axis convention is wrong", errors)

    references = recipe.get("reference_images", [])
    _require(isinstance(references, list), "reference_images must be a list", errors)
    reference_ids = {item.get("id") for item in references if isinstance(item, dict)}
    _require(REQUIRED_REFERENCE_IDS.issubset(reference_ids), "missing required reference image ids", errors)
    for item in references:
        _require(isinstance(item, dict), "each reference image must be an object", errors)
        if isinstance(item, dict):
            _require(isinstance(item.get("path"), str) and item["path"].endswith(".png"), f"bad reference path for {item.get('id')}", errors)

    layers = recipe.get("layers", {})
    for key in ["root", "torso", "head", "left_arm", "right_arm", "left_leg", "right_leg", "details"]:
        _require(isinstance(layers.get(key), str) and layers[key], f"missing layer {key}", errors)

    frames = recipe.get("frames", [])
    _require(isinstance(frames, list), "frames must be a list", errors)
    frame_ids = {frame.get("id") for frame in frames if isinstance(frame, dict)}
    _require(REQUIRED_FRAME_IDS.issubset(frame_ids), "missing required frame ids", errors)
    for frame in frames:
        if not isinstance(frame, dict):
            errors.append("each frame must be an object")
            continue
        _require(_is_vec3(frame.get("origin")), f"frame {frame.get('id')} origin must be vec3", errors)
        _require(_is_vec3(frame.get("rotation_degrees")), f"frame {frame.get('id')} rotation_degrees must be vec3", errors)

    parts = recipe.get("parts", [])
    _require(isinstance(parts, list), "parts must be a list", errors)
    part_ids = {part.get("id") for part in parts if isinstance(part, dict)}
    _require(REQUIRED_PART_IDS.issubset(part_ids), "missing required semantic part ids", errors)
    for part in parts:
        if not isinstance(part, dict):
            errors.append("each part must be an object")
            continue
        part_id = part.get("id")
        _require(part.get("type") in VALID_PART_TYPES, f"part {part_id} has invalid type", errors)
        _require(part.get("frame") in frame_ids, f"part {part_id} references unknown frame", errors)
        _require(part.get("layer") in layers, f"part {part_id} references unknown layer key", errors)
        _require(part.get("material") in recipe.get("materials", {}), f"part {part_id} references unknown material", errors)
        _require(_is_vec3(part.get("center")), f"part {part_id} center must be vec3", errors)
        _require(_is_vec3(part.get("size")), f"part {part_id} size must be vec3", errors)
        _require(_is_vec3(part.get("rotation_degrees")), f"part {part_id} rotation_degrees must be vec3", errors)

    named_views = recipe.get("named_views", [])
    _require(len(named_views) >= 2, "at least two named views are required", errors)
    for view in named_views:
        if not isinstance(view, dict):
            errors.append("each named view must be an object")
            continue
        _require(view.get("reference_image_id") in reference_ids, f"view {view.get('name')} references unknown image", errors)
        _require(_is_vec3(view.get("camera_location")), f"view {view.get('name')} camera_location must be vec3", errors)
        _require(_is_vec3(view.get("target")), f"view {view.get('name')} target must be vec3", errors)

    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate_robot_recipe.py <recipe.json>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    recipe = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_recipe(recipe)
    if errors:
        for error in errors:
            print(f"recipe error: {error}", file=sys.stderr)
        return 1
    print(f"recipe valid: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run validator tests**

Run:

```powershell
python -m pytest experiments\pearson_robot\tests\test_robot_recipe.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit validator and tests**

Run:

```powershell
git add experiments\pearson_robot\scripts\validate_robot_recipe.py `
  experiments\pearson_robot\tests\test_robot_recipe.py
git commit -m "test: validate Pearson robot recipe"
```

Expected: one commit for validator plus tests.

## Task 3: Generate a Rhino-Executable Script from the Recipe

**Files:**
- Create: `experiments/pearson_robot/scripts/build_rhino_script.py`
- Create: `experiments/pearson_robot/tests/test_rhino_script_generation.py`
- Generated locally: `experiments/pearson_robot/generated/pearson_robot_rhino.py`

- [ ] **Step 1: Write failing script generation tests**

Create `experiments/pearson_robot/tests/test_rhino_script_generation.py`:

```python
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT = ROOT / "experiments" / "pearson_robot"
RECIPE = EXPERIMENT / "robot_recipe.json"
BUILDER = EXPERIMENT / "scripts" / "build_rhino_script.py"


def test_build_rhino_script_writes_deterministic_script(tmp_path):
    out_a = tmp_path / "robot_a.py"
    out_b = tmp_path / "robot_b.py"
    for out in [out_a, out_b]:
        result = subprocess.run(
            [sys.executable, str(BUILDER), str(RECIPE), str(out)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr + result.stdout

    assert out_a.read_text(encoding="utf-8") == out_b.read_text(encoding="utf-8")


def test_generated_script_contains_expected_metadata_and_parts(tmp_path):
    out = tmp_path / "robot.py"
    result = subprocess.run(
        [sys.executable, str(BUILDER), str(RECIPE), str(out)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    text = out.read_text(encoding="utf-8")
    assert "ROBOT_RECIPE =" in text
    assert "def create_oriented_box" in text
    assert "def create_wedge" in text
    assert "rook.part_id" in text
    assert "torso_back_slab" in text
    assert "left_leg_foot_block" in text
    assert "right_leg_foot_block" in text
    assert "robot_front_child_view" in text
```

- [ ] **Step 2: Run tests to verify builder is missing**

Run:

```powershell
python -m pytest experiments\pearson_robot\tests\test_rhino_script_generation.py -q
```

Expected: tests fail because `build_rhino_script.py` does not exist.

- [ ] **Step 3: Implement the script generator**

Create `experiments/pearson_robot/scripts/build_rhino_script.py`:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path


GENERATED_HEADER = """# Generated by experiments/pearson_robot/scripts/build_rhino_script.py
# Source recipe: experiments/pearson_robot/robot_recipe.json
# Execute in Rhino through Rook rhino_execute. Do not edit by hand.
"""


RUNTIME_CODE = r'''
import json
import math

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc


ROBOT_RECIPE = __ROBOT_RECIPE_JSON__


def deg_to_rad(value):
    return value * math.pi / 180.0


def ensure_layer(path):
    parts = path.split("::")
    current = ""
    parent = None
    for part in parts:
        current = part if not current else current + "::" + part
        if not rs.IsLayer(current):
            if parent:
                rs.AddLayer(part, parent=parent)
            else:
                rs.AddLayer(part)
        parent = current
    return path


def ensure_material(name, diffuse):
    table = sc.doc.Materials
    for index, material in enumerate(table):
        if material and material.Name == name:
            material.DiffuseColor = System.Drawing.Color.FromArgb(int(diffuse[0]), int(diffuse[1]), int(diffuse[2]))
            material.CommitChanges()
            return index
    material = Rhino.DocObjects.Material()
    material.Name = name
    material.DiffuseColor = System.Drawing.Color.FromArgb(int(diffuse[0]), int(diffuse[1]), int(diffuse[2]))
    return table.Add(material)


def rotation_transform_xyz(rotation_degrees):
    rx, ry, rz = [deg_to_rad(v) for v in rotation_degrees]
    transform = Rhino.Geometry.Transform.Identity
    transform = Rhino.Geometry.Transform.Rotation(rx, Rhino.Geometry.Vector3d.XAxis, Rhino.Geometry.Point3d.Origin) * transform
    transform = Rhino.Geometry.Transform.Rotation(ry, Rhino.Geometry.Vector3d.YAxis, Rhino.Geometry.Point3d.Origin) * transform
    transform = Rhino.Geometry.Transform.Rotation(rz, Rhino.Geometry.Vector3d.ZAxis, Rhino.Geometry.Point3d.Origin) * transform
    return transform


def frame_world_transform(frame_id, frames_by_id, cache):
    if frame_id in cache:
        return cache[frame_id]
    frame = frames_by_id[frame_id]
    transform = rotation_transform_xyz(frame["rotation_degrees"])
    transform = Rhino.Geometry.Transform.Translation(Rhino.Geometry.Vector3d(*frame["origin"])) * transform
    parent = frame.get("parent")
    if parent:
        transform = frame_world_transform(parent, frames_by_id, cache) * transform
    cache[frame_id] = transform
    return transform


def part_transform(part, frame_transform):
    transform = rotation_transform_xyz(part["rotation_degrees"])
    transform = Rhino.Geometry.Transform.Translation(Rhino.Geometry.Vector3d(*part["center"])) * transform
    return frame_transform * transform


def create_oriented_box(size, transform):
    sx, sy, sz = size
    plane = Rhino.Geometry.Plane.WorldXY
    box = Rhino.Geometry.Box(
        plane,
        Rhino.Geometry.Interval(-sx / 2.0, sx / 2.0),
        Rhino.Geometry.Interval(-sy / 2.0, sy / 2.0),
        Rhino.Geometry.Interval(-sz / 2.0, sz / 2.0),
    )
    brep = box.ToBrep()
    brep.Transform(transform)
    return brep


def create_wedge(size, transform, slope):
    sx, sy, sz = size
    dz = sz * float(slope)
    pts = [
        Rhino.Geometry.Point3d(-sx / 2.0, -sy / 2.0, -sz / 2.0),
        Rhino.Geometry.Point3d(sx / 2.0, -sy / 2.0, -sz / 2.0),
        Rhino.Geometry.Point3d(sx / 2.0, sy / 2.0, -sz / 2.0),
        Rhino.Geometry.Point3d(-sx / 2.0, sy / 2.0, -sz / 2.0),
        Rhino.Geometry.Point3d(-sx / 2.0, -sy / 2.0, sz / 2.0 - dz),
        Rhino.Geometry.Point3d(sx / 2.0, -sy / 2.0, sz / 2.0 - dz),
        Rhino.Geometry.Point3d(sx / 2.0, sy / 2.0, sz / 2.0 + dz),
        Rhino.Geometry.Point3d(-sx / 2.0, sy / 2.0, sz / 2.0 + dz),
    ]
    faces = [
        [0, 1, 2, 3],
        [4, 7, 6, 5],
        [0, 4, 5, 1],
        [1, 5, 6, 2],
        [2, 6, 7, 3],
        [3, 7, 4, 0],
    ]
    breps = []
    for face in faces:
        poly = Rhino.Geometry.Polyline([pts[i] for i in face] + [pts[face[0]]])
        curve = poly.ToNurbsCurve()
        face_brep = Rhino.Geometry.Brep.CreatePlanarBreps(curve)
        if face_brep:
            breps.append(face_brep[0])
    joined = Rhino.Geometry.Brep.JoinBreps(breps, sc.doc.ModelAbsoluteTolerance)
    brep = joined[0] if joined else create_oriented_box(size, Rhino.Geometry.Transform.Identity)
    brep.Transform(transform)
    return brep


def add_part_object(part, brep, recipe, material_indices):
    layer_path = recipe["layers"][part["layer"]]
    ensure_layer(layer_path)
    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.Name = part["id"]
    attributes.LayerIndex = sc.doc.Layers.FindByFullPath(layer_path, True)
    diffuse = recipe["materials"][part["material"]]["diffuse"]
    attributes.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    attributes.ObjectColor = System.Drawing.Color.FromArgb(diffuse[0], diffuse[1], diffuse[2])
    attributes.MaterialSource = Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject
    attributes.MaterialIndex = material_indices[part["material"]]
    attributes.SetUserString("rook.part_id", part["id"])
    attributes.SetUserString("rook.part_type", part["type"])
    attributes.SetUserString("rook.parent", part["parent"])
    attributes.SetUserString("rook.role", part["role"])
    attributes.SetUserString("rook.frame", part["frame"])
    attributes.SetUserString("rook.recipe_revision", recipe["revision"])
    attributes.SetUserString("rook.source_strategy", "semantic_parametric_reconstruction")
    attributes.SetUserString("rook.reference_images", recipe["reference_images"][0]["path"])
    return sc.doc.Objects.AddBrep(brep, attributes)


def set_document_metadata(recipe):
    sc.doc.Strings.SetString("rook.project", recipe["project"])
    sc.doc.Strings.SetString("rook.units", "meters")
    sc.doc.Strings.SetString("rook.reference_folder", r"H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT")
    sc.doc.Strings.SetString("rook.target_fidelity", "recognizable_study_model")
    sc.doc.Strings.SetString("rook.modeling_strategy", "semantic_parametric_reconstruction")
    sc.doc.Strings.SetString("rook.active_recipe", r"experiments\pearson_robot\robot_recipe.json")


def make_named_views(recipe):
    for view in recipe["named_views"]:
        rs.ViewCameraTarget(
            None,
            tuple(view["camera_location"]),
            tuple(view["target"]),
        )
        rs.ViewProjection(None, 2)
        existing = sc.doc.NamedViews.FindByName(view["name"])
        if existing >= 0:
            sc.doc.NamedViews.Delete(existing)
        active_view = sc.doc.Views.ActiveView
        if active_view is not None:
            sc.doc.NamedViews.Add(view["name"], active_view.ActiveViewportID)


def clear_previous_robot():
    ids = rs.AllObjects()
    if not ids:
        return
    delete_ids = []
    for object_id in ids:
        if rs.GetUserText(object_id, "rook.source_strategy") == "semantic_parametric_reconstruction":
            delete_ids.append(object_id)
    if delete_ids:
        rs.DeleteObjects(delete_ids)


def main():
    recipe = ROBOT_RECIPE
    set_document_metadata(recipe)
    for layer_path in recipe["layers"].values():
        ensure_layer(layer_path)
    material_indices = {}
    for name, material in recipe["materials"].items():
        material_indices[name] = ensure_material(name, material["diffuse"])

    clear_previous_robot()
    frames_by_id = {frame["id"]: frame for frame in recipe["frames"]}
    frame_cache = {}
    created = []
    for part in recipe["parts"]:
        frame_transform = frame_world_transform(part["frame"], frames_by_id, frame_cache)
        transform = part_transform(part, frame_transform)
        if part["type"] == "wedge":
            brep = create_wedge(part["size"], transform, part.get("slope", 0.0))
        else:
            brep = create_oriented_box(part["size"], transform)
        created.append(str(add_part_object(part, brep, recipe, material_indices)))

    make_named_views(recipe)
    sc.doc.Views.Redraw()
    print(json.dumps({"success": True, "created_count": len(created), "created_ids": created, "revision": recipe["revision"]}))


main()
'''


def build_script(recipe_path: Path) -> str:
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    payload = json.dumps(recipe, indent=2, sort_keys=True)
    code = RUNTIME_CODE.replace("__ROBOT_RECIPE_JSON__", "json.loads(" + repr(payload) + ")")
    return GENERATED_HEADER + "\n" + "import System\n" + code


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: build_rhino_script.py <recipe.json> <output.py>", file=sys.stderr)
        return 2
    recipe_path = Path(argv[1])
    output_path = Path(argv[2])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_script(recipe_path), encoding="utf-8")
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run script generation tests**

Run:

```powershell
python -m pytest experiments\pearson_robot\tests\test_rhino_script_generation.py -q
```

Expected: tests pass.

- [ ] **Step 5: Generate the Rhino script locally**

Run:

```powershell
python experiments\pearson_robot\scripts\validate_robot_recipe.py experiments\pearson_robot\robot_recipe.json
python experiments\pearson_robot\scripts\build_rhino_script.py experiments\pearson_robot\robot_recipe.json experiments\pearson_robot\generated\pearson_robot_rhino.py
```

Expected:

```text
recipe valid: experiments\pearson_robot\robot_recipe.json
wrote experiments\pearson_robot\generated\pearson_robot_rhino.py
```

- [ ] **Step 6: Commit builder and tests**

Run:

```powershell
git add experiments\pearson_robot\scripts\build_rhino_script.py `
  experiments\pearson_robot\tests\test_rhino_script_generation.py
git commit -m "feat: generate Pearson robot Rhino script"
```

Expected: one commit for the generator and tests. Do not commit `generated/pearson_robot_rhino.py` unless the team chooses it as a checkpoint artifact.

## Task 4: Execute First Rhino Generation Pass

**Files:**
- Local generated input: `experiments/pearson_robot/generated/pearson_robot_rhino.py`
- Modify after execution: `experiments/pearson_robot/ITERATIONS.md`

- [ ] **Step 1: Confirm Rhino and Rook are ready**

Run through available Rook MCP tools:

```text
rhino_session_capabilities
```

Expected: active Rhino session reports `rhino_execute` capability. If no session is available, start Rhino with the locally deployed Rook plugin, then retry.

- [ ] **Step 2: Execute the generated script**

Read `experiments/pearson_robot/generated/pearson_robot_rhino.py` from disk, then call Rook:

Use `rhino_execute` with the `code` field set to the exact contents of
`experiments/pearson_robot/generated/pearson_robot_rhino.py`.

Expected result payload includes:

```json
{"success": true, "data": {"objectsCreated": 14, "output": "..."}}
```

The generated script also prints a JSON line to stdout:

```json
{"success": true, "created_count": 14, "revision": "r001"}
```

Verify that JSON inside `data.output`; do not expect `created_count` or
`revision` as top-level `rhino_execute` fields.

If Rhino reports an exception, fix the generator in Task 3 rather than editing the generated script by hand.

- [ ] **Step 3: Verify layers and metadata with Rook**

Call:

```text
rhino_layers()
rhino_usertext_document_get({})
rhino_select({ "namePattern": "*leg*" })
```

Expected:

- Layers include `Pearson Robot::02 Torso`, `Pearson Robot::03 Head`, `Pearson Robot::04 Arms::Left`, `Pearson Robot::04 Arms::Right`, `Pearson Robot::05 Legs::Left`, `Pearson Robot::05 Legs::Right`, and `Pearson Robot::06 Details`.
- Document user strings include `rook.project=pearson_robot`, `rook.units=meters`, and `rook.modeling_strategy=semantic_parametric_reconstruction`.
- Leg objects have names containing `left_leg` and `right_leg`.

- [ ] **Step 4: Verify named views exist**

Call:

```text
rhino_views()
```

Expected: list includes at least:

```text
robot_front_child_view
robot_side_recline_view
robot_architectural_wide_view
```

- [ ] **Step 5: Update iteration log with first execution**

Append to `experiments/pearson_robot/ITERATIONS.md`:

```markdown

## r001 - First Rhino generation

Status: generated

Execution:
- Generated from `robot_recipe.json`.
- Rhino script generated at `experiments/pearson_robot/generated/pearson_robot_rhino.py`.
- Expected semantic object count: 14.

Checks:
- Layers created under `Pearson Robot`.
- Document user strings stamped.
- Named views created: `robot_front_child_view`, `robot_side_recline_view`, `robot_architectural_wide_view`.

Visual notes:
- Inspect the reclined torso/head relationship first.
- Inspect whether legs read as forward seat/foot volumes from front and side views.
- Inspect whether the arm side blocks are too vertical or too bulky.

Next adjustment target:
- Tune `torso_frame.rotation_degrees`, hip frame positions, and leg block sizes based on screenshots.
```

- [ ] **Step 6: Commit iteration log update**

Run:

```powershell
git add experiments\pearson_robot\ITERATIONS.md
git commit -m "docs: record Pearson robot first generation pass"
```

Expected: one docs-only commit after live generation succeeds.

## Task 5: Capture First Comparison Screenshots

**Files:**
- Generated local evidence: `experiments/pearson_robot/screenshots/*.png`
- Modify: `experiments/pearson_robot/ITERATIONS.md`

- [ ] **Step 1: Restore and capture front view**

Call:

```text
rhino_views_restore({ "name": "robot_front_child_view" })
rhino_viewport({
  "view": "robot_front_child_view",
  "displayMode": "Shaded",
  "width": 1600,
  "height": 1200
})
```

Expected: `rhino_viewport` returns `data.filePath`. Replace `$src` below with
that exact returned file path, then promote it into the experiment folder:

```powershell
$src = 'C:\path\returned\by\rhino_viewport\data.filePath.png'
Copy-Item -LiteralPath $src -Destination 'C:\Users\aryan\source\repos\Rook\experiments\pearson_robot\screenshots\r001_robot_front_child_view.png' -Force
```

Expected: PNG file exists at `experiments/pearson_robot/screenshots/r001_robot_front_child_view.png`.

- [ ] **Step 2: Restore and capture side/recline view**

Call:

```text
rhino_views_restore({ "name": "robot_side_recline_view" })
rhino_viewport({
  "view": "robot_side_recline_view",
  "displayMode": "Shaded",
  "width": 1600,
  "height": 1200
})
```

Expected: `rhino_viewport` returns `data.filePath`. Replace `$src` below with
that exact returned file path, then promote it:

```powershell
$src = 'C:\path\returned\by\rhino_viewport\data.filePath.png'
Copy-Item -LiteralPath $src -Destination 'C:\Users\aryan\source\repos\Rook\experiments\pearson_robot\screenshots\r001_robot_side_recline_view.png' -Force
```

Expected: PNG file exists at `experiments/pearson_robot/screenshots/r001_robot_side_recline_view.png`.

- [ ] **Step 3: Inspect screenshots**

Use `view_image` for:

```text
C:\Users\aryan\source\repos\Rook\experiments\pearson_robot\screenshots\r001_robot_front_child_view.png
C:\Users\aryan\source\repos\Rook\experiments\pearson_robot\screenshots\r001_robot_side_recline_view.png
```

Expected:

- The object reads as a turquoise block robot.
- The face is visible from the front-ish view.
- The torso is reclined from the side view.
- Legs project forward and are visually larger than the head.

- [ ] **Step 4: Record screenshot notes**

Append to `experiments/pearson_robot/ITERATIONS.md`:

```markdown

## r001 - Screenshot review

Screenshots:
- `experiments/pearson_robot/screenshots/r001_robot_front_child_view.png`
- `experiments/pearson_robot/screenshots/r001_robot_side_recline_view.png`

Reference comparison:
- Front target: `H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT\image.png`
- Side target: `H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT\image (2).png`

Result:
- The model is considered a first-pass recognizable study model if the face, reclined torso, blocky arms, and forward legs are readable.

Next planned adjustment:
- If the torso is too upright, increase negative X rotation on `torso_frame`.
- If the legs are too narrow, increase hip frame X offsets and foot block widths.
- If the head is too large, reduce `head_box.size`.
```

- [ ] **Step 5: Decide whether to commit screenshots**

If the screenshots are useful checkpoint evidence, run:

```powershell
git add experiments\pearson_robot\screenshots\r001_robot_front_child_view.png `
  experiments\pearson_robot\screenshots\r001_robot_side_recline_view.png `
  experiments\pearson_robot\ITERATIONS.md
git commit -m "docs: add Pearson robot r001 screenshot evidence"
```

If screenshots are not committed, run:

```powershell
git add experiments\pearson_robot\ITERATIONS.md
git commit -m "docs: record Pearson robot r001 screenshot review"
```

Expected: one commit captures the screenshot review decision either way.

## Task 6: First Parameter Adjustment Loop

**Files:**
- Modify: `experiments/pearson_robot/robot_recipe.json`
- Modify: `experiments/pearson_robot/ITERATIONS.md`
- Generated local: `experiments/pearson_robot/generated/pearson_robot_rhino.py`

- [ ] **Step 1: Choose one adjustment set**

Based on screenshots, choose exactly one of these adjustment sets for the first revision:

```text
Set A - posture:
- torso_frame.rotation_degrees[0]: -22.0 -> -28.0
- head_frame.origin[2]: 2.10 -> 2.18

Set B - width:
- left_hip_frame.origin[0]: 0.55 -> 0.72
- right_hip_frame.origin[0]: -0.55 -> -0.72
- left_leg_foot_block.size[0]: 0.82 -> 0.95
- right_leg_foot_block.size[0]: 0.82 -> 0.95

Set C - head scale:
- head_box.size: [0.72, 0.28, 0.48] -> [0.62, 0.24, 0.42]
- mouth_slot.size: [0.44, 0.035, 0.07] -> [0.36, 0.035, 0.06]
```

Do not combine adjustment sets in the first tuning pass.

- [ ] **Step 2: Edit the recipe revision and chosen parameters**

Modify `experiments/pearson_robot/robot_recipe.json`:

```json
"revision": "r002"
```

Then apply only the chosen adjustment set from Step 1.

- [ ] **Step 3: Validate and regenerate**

Run:

```powershell
python experiments\pearson_robot\scripts\validate_robot_recipe.py experiments\pearson_robot\robot_recipe.json
python experiments\pearson_robot\scripts\build_rhino_script.py experiments\pearson_robot\robot_recipe.json experiments\pearson_robot\generated\pearson_robot_rhino.py
```

Expected:

```text
recipe valid: experiments\pearson_robot\robot_recipe.json
wrote experiments\pearson_robot\generated\pearson_robot_rhino.py
```

If the validator rejects `r002`, update the validator's revision check to allow `r001` or `r002` by replacing:

```python
_require(recipe.get("revision") == "r001", "revision must be r001 for the first pass", errors)
```

with:

```python
_require(isinstance(recipe.get("revision"), str) and recipe["revision"].startswith("r"), "revision must be an r-prefixed string", errors)
```

Then rerun the tests.

- [ ] **Step 4: Re-execute in Rhino**

Call:

Use `rhino_execute` with the `code` field set to the exact contents of
`experiments/pearson_robot/generated/pearson_robot_rhino.py`.

Expected: previous robot objects are deleted and regenerated. The
`rhino_execute` route returns success, and its `data.output` contains the
generated script's JSON line with `"revision": "r002"`.

- [ ] **Step 5: Capture the same two views**

Call:

```text
rhino_views_restore({ "name": "robot_front_child_view" })
rhino_viewport({
  "view": "robot_front_child_view",
  "displayMode": "Shaded",
  "width": 1600,
  "height": 1200
})
rhino_views_restore({ "name": "robot_side_recline_view" })
rhino_viewport({
  "view": "robot_side_recline_view",
  "displayMode": "Shaded",
  "width": 1600,
  "height": 1200
})
```

Expected: each `rhino_viewport` call returns `data.filePath`. Replace `$front`
and `$side` below with the exact returned file paths, then promote the two
captures:

```powershell
$front = 'C:\path\returned\by\front\rhino_viewport\data.filePath.png'
$side = 'C:\path\returned\by\side\rhino_viewport\data.filePath.png'
Copy-Item -LiteralPath $front -Destination 'C:\Users\aryan\source\repos\Rook\experiments\pearson_robot\screenshots\r002_robot_front_child_view.png' -Force
Copy-Item -LiteralPath $side -Destination 'C:\Users\aryan\source\repos\Rook\experiments\pearson_robot\screenshots\r002_robot_side_recline_view.png' -Force
```

Expected: two r002 screenshots exist in `experiments/pearson_robot/screenshots`.

- [ ] **Step 6: Record the parameter adjustment**

Append to `experiments/pearson_robot/ITERATIONS.md` with the chosen set filled in:

```markdown

## r002 - First parameter adjustment

Adjustment set: Set A - posture

Changed:
- `torso_frame.rotation_degrees[0]`: `-22.0` to `-28.0`
- `head_frame.origin[2]`: `2.10` to `2.18`

Screenshots:
- `experiments/pearson_robot/screenshots/r002_robot_front_child_view.png`
- `experiments/pearson_robot/screenshots/r002_robot_side_recline_view.png`

Result:
- Compare against r001 before deciding whether to keep this parameter direction.
```

If Set B or Set C was used, replace the "Adjustment set" and "Changed" bullets with the exact parameter names and values from Step 1.

- [ ] **Step 7: Run all local tests**

Run:

```powershell
python -m pytest experiments\pearson_robot\tests -q
git diff --check
```

Expected: tests pass and whitespace check is clean.

- [ ] **Step 8: Commit recipe adjustment**

Commit durable source files and selected evidence:

```powershell
git add experiments\pearson_robot\robot_recipe.json `
  experiments\pearson_robot\ITERATIONS.md `
  experiments\pearson_robot\scripts\validate_robot_recipe.py
git commit -m "feat: tune Pearson robot first pass"
```

If screenshots are intentionally selected as checkpoint evidence, include them in the same commit with `git add experiments\pearson_robot\screenshots\r002_*.png`.

## Task 7: Final Verification and Handoff Notes

**Files:**
- Modify: `experiments/pearson_robot/ITERATIONS.md`

- [ ] **Step 1: Verify recipe and tests**

Run:

```powershell
python experiments\pearson_robot\scripts\validate_robot_recipe.py experiments\pearson_robot\robot_recipe.json
python -m pytest experiments\pearson_robot\tests -q
git diff --check
```

Expected: validator passes, tests pass, and whitespace check is clean.

- [ ] **Step 2: Verify live Rhino state if Rhino is available**

Call:

```text
rhino_layers()
rhino_views()
rhino_usertext_document_get({})
```

Expected:

- `Pearson Robot` layer tree exists.
- Named views include `robot_front_child_view` and `robot_side_recline_view`.
- Document user strings include `rook.project=pearson_robot`.

- [ ] **Step 3: Add final handoff entry**

Append to `experiments/pearson_robot/ITERATIONS.md`:

```markdown

## Handoff

Current durable state:
- Spec: `docs/superpowers/specs/2026-06-26-pearson-robot-semantic-parametric-reconstruction-design.md`
- Recipe: `experiments/pearson_robot/robot_recipe.json`
- Validator: `experiments/pearson_robot/scripts/validate_robot_recipe.py`
- Script generator: `experiments/pearson_robot/scripts/build_rhino_script.py`

Resume sequence:
1. Inspect the four reference images in `H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT`.
2. Run the recipe validator.
3. Regenerate `generated/pearson_robot_rhino.py`.
4. Execute the generated script in Rhino through Rook `rhino_execute`.
5. Capture `robot_front_child_view` and `robot_side_recline_view`.
6. Tune only the recipe, not generated Rhino script output.

Known remaining modeling risk:
- The first pass is still proportion-driven by visual judgment, not calibrated photogrammetry.
- The wedge geometry is a simple planar approximation.
- Face details are shallow applied dark solids rather than true boolean recesses.
```

- [ ] **Step 4: Commit final handoff**

Run:

```powershell
git add experiments\pearson_robot\ITERATIONS.md
git commit -m "docs: add Pearson robot reconstruction handoff"
```

Expected: final docs commit records continuation state.

## Verification Summary

Minimum completion proof for the first pass:

```powershell
python experiments\pearson_robot\scripts\validate_robot_recipe.py experiments\pearson_robot\robot_recipe.json
python -m pytest experiments\pearson_robot\tests -q
git diff --check
```

Live Rhino proof, when Rhino is available:

```text
rhino_execute generated script succeeds with success=true
rhino_execute data.output contains the generated script JSON line
rhino_layers shows Pearson Robot layer tree
rhino_views shows robot_front_child_view and robot_side_recline_view
rhino_viewport returns data.filePath for at least two captures
```

Do not claim live visual success unless the screenshots are inspected.
