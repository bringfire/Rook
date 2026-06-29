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

## r001 - Screenshot review

Screenshots:
- `experiments/pearson_robot/screenshots/r001_robot_front_child_view.png`
- `experiments/pearson_robot/screenshots/r001_robot_side_recline_view.png`

Reference comparison:
- Front target: `H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT\image.png`
- Side target: `H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT\image (2).png`

Result:
- The model reads as a first-pass turquoise block robot with visible face, reclined torso, large side arms, and forward legs.
- The side view is the strongest match to the reference silhouette.
- The front view is recognizable but the legs/feet are visually narrow and compressed compared with the reference photos.

Next planned adjustment:
- Use Set B - width for r002 to increase hip spacing and foot block width.

## r002 - First parameter adjustment

Adjustment set: Set B - width

Changed:
- `left_hip_frame.origin[0]`: `0.55` to `0.72`
- `right_hip_frame.origin[0]`: `-0.55` to `-0.72`
- `left_leg_foot_block.size[0]`: `0.82` to `0.95`
- `right_leg_foot_block.size[0]`: `0.82` to `0.95`

Screenshots:
- `experiments/pearson_robot/screenshots/r002_robot_front_child_view.png`
- `experiments/pearson_robot/screenshots/r002_robot_side_recline_view.png`

Result:
- r002 improves front-view leg and foot readability by separating and widening the forward masses.
- Side-view silhouette remains comparable to r001.
- Next likely modeling target is posture/head framing rather than additional width.

## Handoff

Current durable state:
- Spec: `docs/superpowers/specs/2026-06-26-pearson-robot-semantic-parametric-reconstruction-design.md`
- Recipe: `experiments/pearson_robot/robot_recipe.json`
- Validator: `experiments/pearson_robot/scripts/validate_robot_recipe.py`
- Script generator: `experiments/pearson_robot/scripts/build_rhino_script.py`
- Evidence: `experiments/pearson_robot/screenshots/r001_*.png` and `experiments/pearson_robot/screenshots/r002_*.png`

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
- Face details and foot slots are shallow applied dark solids rather than true boolean recesses.
- The next refinement should likely tune posture/head framing after comparing r002 against the side and front references.
