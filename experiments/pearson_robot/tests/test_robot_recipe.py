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
