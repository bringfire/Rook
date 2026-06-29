import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT = ROOT / "experiments" / "pearson_robot"
RECIPE = EXPERIMENT / "robot_recipe.json"
BUILDER = EXPERIMENT / "scripts" / "build_rhino_script.py"


def test_builder_writes_deterministic_script(tmp_path):
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"

    for output in (first, second):
        result = subprocess.run(
            [sys.executable, str(BUILDER), str(RECIPE), str(output)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr + result.stdout

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_generated_script_contains_expected_rook_metadata(tmp_path):
    output = tmp_path / "pearson_robot_rhino.py"
    result = subprocess.run(
        [sys.executable, str(BUILDER), str(RECIPE), str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    text = output.read_text(encoding="utf-8")

    assert "rook.project" in text
    assert "rook.modeling_strategy" in text
    assert "semantic_parametric_reconstruction" in text
    assert "Pearson Robot::02 Torso" in text
    assert "robot_front_child_view" in text
    assert "robot_side_recline_view" in text


def test_generated_script_embeds_all_semantic_parts(tmp_path):
    output = tmp_path / "pearson_robot_rhino.py"
    result = subprocess.run(
        [sys.executable, str(BUILDER), str(RECIPE), str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    text = output.read_text(encoding="utf-8")

    for part_id in [
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
    ]:
        assert part_id in text
