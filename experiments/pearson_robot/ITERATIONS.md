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
