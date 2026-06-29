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
