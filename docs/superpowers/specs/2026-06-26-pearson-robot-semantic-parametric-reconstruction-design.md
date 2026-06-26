# Pearson Robot Semantic Parametric Reconstruction Design

**Date:** 2026-06-26
**Status:** Design approved for spec capture
**Scope:** recognizable study model of the Pearson / ArtScience Laboratory robot installation
**Primary workspace:** `C:\Users\aryan\source\repos\Rook`
**Reference image folder:** `H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT`

## Goal

Build a recognizable 3D study model of the turquoise robot installation from the
reference photos. The model should clearly read as the same object: a large
reclined, faceted, climbable robot made from blocky turquoise solids.

The goal is not photogrammetric fidelity or fabrication documentation. The goal
is to test a durable, Codex-native modeling workflow: semantic parametric
reconstruction. The model should be generated from an inspectable recipe of
named parts, local frames, dimensions, and metadata, then checked from camera
views that roughly match the reference images.

## Reference Images

The source images are local files. Future sessions should inspect these before
continuing work:

| File | Path | Use |
|---|---|---|
| `image.png` | `H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT\image.png` | front-ish portrait view with child seated on the viewer-left leg/seat |
| `image (1).png` | `H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT\image (1).png` | wide frontal social-media frame with wall context and people for scale |
| `image (2).png` | `H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT\image (2).png` | side/reclined view, best for posture, torso lean, legs, and seat geometry |
| `image (3).png` | `H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT\image (3).png` | wide architectural rendering, best for overall composition and environment scale |

The two most important reconstruction references are `image (2).png` for the
reclined side structure and `image (3).png` for the full-room relationship.

## Unit System and Scale

Use meters. Treat `1 Rhino unit = 1 meter`.

The first-pass model should be exhibit/furniture scale rather than exact. Use
human scale in the photos as a guide:

- Overall robot length: roughly 4.0 to 5.0 m.
- Overall width across arms/legs: roughly 3.0 to 4.0 m.
- Seat/leg blocks: child- and adult-sittable, roughly bench height.
- Head: visually small relative to torso, tilted with the reclined body.

Exact numbers belong in a machine-readable recipe and may change per iteration.
The spec only fixes the unit convention and approximate scale intent.

## Coordinate and Side Convention

Use robot-anatomical left/right for all semantic ids, recipe keys, layers, and
metadata. `left_arm`, `right_arm`, `left_leg`, and `right_leg` mean the robot's
own left/right, not the viewer's left/right in a reference image.

Use this first-pass world convention:

- `+Z`: up.
- `+Y`: the robot's forward direction, from torso toward feet.
- `+X`: the robot's anatomical left.
- Origin: near the root seat/torso base, centered between the two hip frames.

When describing a reference image, use viewer-facing language explicitly, such
as `viewer-left` or `viewer-right`. For example, in `image.png`, the child sits
on the viewer-left side, which may correspond to the robot's anatomical right
if the robot is facing the camera.

## Chosen Approach

Use semantic parametric reconstruction.

Codex should not try to freeform sculpt the robot. Instead, it should describe
the robot as a named assembly of primitive solids, local orientation frames, and
simple operations:

- oriented boxes
- tapered boxes or wedges
- sloped slabs
- shallow recessed slots
- simple circular or rounded rectangular face details
- turquoise material assignment

The model recipe is the source of truth. Geometry is generated from the recipe,
then checked visually and through Rook/Rhino scene metadata.

This approach plays to Codex strengths:

- decomposing an object into named semantic parts
- writing deterministic construction logic
- preserving relationships as metadata
- iterating parameters instead of manually editing anonymous geometry
- using camera screenshots and scene graph data as external feedback

## Secondary Approaches

### Image-to-3D Mesh Scaffold

A 2D-to-3D mesh pipeline may be used later as a ghost/scaffold reference, but it
should not be treated as the final model. The expected failure mode is noisy,
lumpy topology that loses the crisp planar construction of the installation.

Use it only if it helps recover:

- rough overall posture
- silhouette proportions
- recline angle
- approximate arm/leg massing

If used, the generated mesh should live on a reference layer and remain separate
from the clean semantic model.

### Grasshopper

Grasshopper is not the first path. It could help if the team wants interactive
human slider tuning or a visual parametric rig, but it adds graph-maintenance
overhead for a relatively small asymmetric assembly.

The first implementation should be script/Rook-driven. A later Grasshopper layer
can expose high-level parameters if repeated interactive tuning becomes useful.

### Full Joint Constraint Solver

Do not build a full mechanical rig or constraint solver for the first pass.
The robot is static. Lightweight "bones" as local orientation frames are useful;
animation-style constraints are unnecessary.

## Semantic Part Hierarchy

The first-pass robot should use a small, explicit hierarchy:

```text
robot
  root_frame
  torso
    torso_back_slab
    torso_front_panel
    torso_side_panels
    neck_slot
  head
    head_box
    left_eye
    right_eye
    mouth_slot
  left_arm
    upper_side_block
    seat_ledge
    lower_step
    vertical_slot
  right_arm
    upper_side_block
    seat_ledge
    lower_step
    vertical_slot
  left_leg
    thigh_block
    shin_or_ramp
    foot_block
    foot_slot
  right_leg
    thigh_block
    shin_or_ramp
    foot_block
    foot_slot
  details
    dark_recesses
    optional_panel_lines
```

The hierarchy can be simplified if the first generated version is too granular,
but every visible major mass should have a stable semantic part id.

## Lightweight Bone Frames

Use bones as construction frames, not as an animation rig. Each bone is a local
coordinate frame with a name, parent, origin, orientation, and approximate length.

Initial frame vocabulary:

```text
root_frame
  torso_frame: reclines backward from root
    head_frame: attached near torso top, tilted with the torso
    left_shoulder_frame: torso side, arm angled down/forward
    right_shoulder_frame: torso side, arm angled down/forward
    left_hip_frame: lower torso, leg projecting forward/outward
    right_hip_frame: lower torso, leg projecting forward/outward
```

Parts should be generated relative to these frames. This keeps changes coherent:
adjusting torso recline should carry the head and side masses with it.

## Metadata and Layer Conventions

Use Rhino layers and object metadata as working memory. The model should be
self-describing after context compaction.

Recommended layer tree:

```text
Pearson Robot
  00 Reference
  01 Skeleton
  02 Torso
  03 Head
  04 Arms
    Left
    Right
  05 Legs
    Left
    Right
  06 Details
  90 Cameras
  99 Debug
```

Recommended object user strings:

| Key | Meaning |
|---|---|
| `rook.part_id` | stable semantic id, e.g. `left_leg_foot_block` |
| `rook.part_type` | primitive/category, e.g. `box`, `wedge`, `slot`, `face_detail` |
| `rook.parent` | parent semantic id |
| `rook.role` | visual/functional role, e.g. `torso`, `seat`, `armrest`, `foot`, `detail` |
| `rook.frame` | construction frame name |
| `rook.recipe_revision` | recipe revision used to generate the object |
| `rook.source_strategy` | `semantic_parametric_reconstruction` |
| `rook.reference_images` | reference folder or image id list |

Recommended document user strings:

| Key | Value |
|---|---|
| `rook.project` | `pearson_robot` |
| `rook.units` | `meters` |
| `rook.reference_folder` | `H:\AI EXPERIMENTS\Pearson\reference_images\ROBOT` |
| `rook.target_fidelity` | `recognizable_study_model` |
| `rook.modeling_strategy` | `semantic_parametric_reconstruction` |
| `rook.active_recipe` | path to the current recipe file |

## Durable File Artifacts

The implementation should create a small experiment folder. Suggested location:

```text
experiments/pearson_robot/
  README.md
  robot_recipe.json
  ITERATIONS.md
  screenshots/
  exports/
```

The source recipe and hand-written notes should be committed when they are useful
for continuation: `README.md`, `robot_recipe.json`, and `ITERATIONS.md`. Generated
screenshots, Rhino exports, meshes, and large intermediate artifacts should be
committed only when they are intentionally selected as review/checkpoint evidence;
otherwise keep them local scratch outputs or ignore them in follow-up tooling.

`robot_recipe.json` should be the model source of truth. It should contain:

- unit system
- reference image paths
- material definitions
- skeleton frame definitions
- part definitions
- layer mapping
- metadata mapping
- named comparison camera definitions
- recipe revision

`ITERATIONS.md` should record each pass:

- revision id
- what changed
- which reference image/camera was checked
- what still looks wrong
- next planned adjustment

The Rhino model should be regenerable from the recipe. The Rhino document is the
working artifact; the recipe is the durable construction memory.

## Camera Comparison Loop

Use named Rhino views to compare the generated model with the references.

Initial comparison cameras:

| Camera | Reference | Purpose |
|---|---|---|
| `robot_front_child_view` | `image.png` | front-ish seated-child composition and readable face/legs |
| `robot_wide_front_view` | `image (1).png` | broad front proportions, wall context, head/torso silhouette |
| `robot_side_recline_view` | `image (2).png` | torso recline, side blocks, leg/seat geometry |
| `robot_architectural_wide_view` | `image (3).png` | overall room-scale composition and robot footprint |

The first implementation does not need exact camera calibration. It should use
rough matched named views and screenshots. Later iterations may add image
overlay, silhouette scoring, or camera calibration if those become useful.

## Rook and Scene Graph Use

Use Rook's scene graph as an inspection and reasoning layer:

- verify that expected part objects exist
- inspect bounding boxes and object extents
- confirm parent/child metadata and layer placement
- compare left/right symmetry where intended
- find accidental outliers or misplaced pieces
- support camera/screenshot iteration

The scene graph is not the primary model representation. It is a feedback and
inspection layer over the generated Rhino geometry.

## Success Criteria

The first successful pass should satisfy these conditions:

1. A future user can identify the model as the turquoise robot installation from
   the reference images.
2. Major masses are present: reclined torso, tilted head, blocky arms, forward
   legs/feet, face, slots/recesses.
3. The model is at plausible meter scale for an interactive exhibit object.
4. Objects are named/layered/tagged with semantic metadata.
5. The model can be regenerated from a recipe.
6. At least two named camera screenshots are captured for comparison.
7. The iteration log states what is still inaccurate.

## Non-Goals

- Exact fabrication drawings.
- Exact material/lighting recreation.
- Perfect camera matching.
- Full photogrammetry.
- Full image-to-3D mesh cleanup.
- Grasshopper-first implementation.
- Animation rigging or mechanical joint solving.
- Broad Rook tool refactors unrelated to this experiment.

## Implementation Direction

The first implementation should be a narrow experiment, not a product feature.
Prefer small scripts or existing Rook tools over new native/managed plugin code
unless a missing capability blocks the experiment.

Recommended order:

1. Create the experiment folder and initial `robot_recipe.json`.
2. Generate first-pass primitives in Rhino from the recipe.
3. Apply layers, materials, and object user strings.
4. Create named views for the main references.
5. Capture screenshots.
6. Record iteration notes.
7. Adjust recipe parameters and regenerate.

If a tool gap appears, capture it as a candidate Rook improvement only after the
manual/procedural path proves the need.

## Context-Compaction Protocol

Future Codex sessions should resume by reading, in order:

1. This spec.
2. `experiments/pearson_robot/README.md`, if present.
3. `experiments/pearson_robot/robot_recipe.json`, if present.
4. `experiments/pearson_robot/ITERATIONS.md`, if present.
5. The four reference images listed above.
6. The current Rhino document metadata and scene graph, if Rhino is running.

Do not rely on chat history to reconstruct modeling intent. Durable state should
live in the spec, recipe, iteration log, screenshots, Rhino layers, and object
metadata.
