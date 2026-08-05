# Bank of China Tower Reference Reconstruction Design

## Goal

Create a parametric Rhino/Grasshopper reconstruction of the Bank of China Tower whose exterior massing and expressed structural geometry look convincingly exact across all nine supplied reference images.

The result is a visual and geometric reference reconstruction. It is not a construction model, structural-analysis model, BIM model, or claim about concealed conditions.

## Success Boundary

The reconstruction must reproduce:

- the four-part triangular tower organization;
- the order, orientation, and height of the major setbacks;
- the sloping transition and atrium faces;
- the podium, principal entrances, roof frame, and twin masts at silhouette level;
- the primary horizontal transfer bands;
- the visible diagonal super-frame and its node locations; and
- the curtain-wall rhythm at a level that reads correctly in the supplied photographs.

The reconstruction does not need to reproduce:

- interior partitions, elevators, stairs, or tenant layouts;
- concealed framing, foundations, or detailed connections;
- construction-grade member sizes;
- exact curtain-wall unit fabrication; or
- neighboring buildings, landscaping, or the full site.

## Reference Set and Authority

The source images are under `C:/Users/aryan/Desktop/BoCTower`.

| Reference | Evidence role | Authority |
| --- | --- | --- |
| `boc-07.jpg` | elevation plus floor plans at stories 4, 25, 39, and 51/52 | primary geometric evidence |
| `e777e6f3ae01c8bdfcb40c111a685022.jpg` | elevation/section, story and mechanical-floor landmarks, central-column transfer note | primary geometric evidence |
| `boc-08.jpg` | analytical axonometric and setback orientation | secondary geometric evidence |
| `boc-06.jpg` | conceptual decomposition and structural expression | secondary geometric evidence |
| `boc-01.jpg` through `boc-05.jpg` | perspective silhouettes, façade expression, visible-face relationships, podium and mast appearance | validation evidence |

Evidence precedence is:

1. analytical plan, elevation, and section drawings;
2. analytical axonometrics;
3. agreement across multiple photographs;
4. a single photograph; and
5. an explicit modeling assumption.

The official project description supplies two organizing constraints: the tower is composed of four vertical shafts, and it emerges from a 52 m cube before diminishing quadrant by quadrant to one triangular prism. Those constraints govern interpretation of the low-resolution drawings rather than replacing them.

## Accuracy Model

Every calibrated quantity has one of three confidence classes:

- **High:** directly dimensioned, shown orthographically, or corroborated by at least two analytical references.
- **Medium:** triangulated from an axonometric and multiple photographs.
- **Low:** hidden, visible in only one cropped photograph, or inferred to close the model.

Low-confidence quantities remain exposed as Grasshopper inputs. They must not be embedded as unexplained constants.

The analytical references determine dimensions and topology. Photographs validate projected geometry after an independent camera is fitted to each image. A camera fit may absorb camera location, target, lens length, and crop offset; it must not deform the tower geometry to rescue one photograph.

## Parametric Geometry

### Global frame and levels

- Model in metres with World Z vertical.
- Centre the 52 m base square on the World origin.
- Assign permanent cardinal names to its four corners and four triangular plan sectors.
- Keep the tower orientation stable after the first accepted axonometric checkpoint.
- Represent podium top, primary transfer bands, the four shaft terminal levels, roof, and mast top as named numeric inputs.
- Seed story-related levels from the section labels around stories 4/6, 18/19, 25, 31/32, 44/45, 57/58, and 69/70, then calibrate their Z values against the complete analytical elevation.

### Massing

Construct the tower from four triangular sectors meeting at the centre of the base square. Each sector has an independently controllable terminal condition. Shared plan vertices and shared elevation levels must remain coincident so parameter edits cannot create cracks between sectors.

The generator produces:

- four closed primary massing bodies;
- the exposed sloping transition faces;
- reference footprints at the four documented plan levels;
- key corner, centre, setback, roof, and mast landmarks; and
- silhouette curves for orthographic validation.

The first massing checkpoint uses only these outputs. Façade and member detail remain disabled until the massing passes the analytical views.

### Expressed structure

Represent the visible super-frame as a node-and-edge graph rather than independent decorative lines.

Nodes occur at:

- surviving exterior corners at major transfer levels;
- the centre-axis transfer location where it remains expressed;
- setback vertices;
- roof-frame vertices; and
- mast bases.

Edges describe:

- primary diagonals;
- horizontal transfer bands;
- major vertical corner covers; and
- roof-frame members.

Brace axes are authoritative. Display solids are generated from those axes with rectangular or box-like profiles sized by global visual parameters. This keeps brace intersections exact while allowing apparent width and depth to be tuned independently.

### Envelope and secondary elements

Curtain-wall geometry is subordinate to the massing and structural graph. Generate a lightweight façade grid on exposed exterior faces, clipped to each face boundary. It needs to read at building scale without reproducing every fabricated panel.

Model the podium, entrance rhythm, sloping glazed atrium faces, roof frame, and masts as separate outputs so each can be hidden during calibration and revised without disturbing the primary massing.

## Grasshopper and Rhino Responsibilities

Grasshopper is the source of truth for geometry and parameters. Use one focused RhinoCode C# Script component for deterministic generation, native sliders/toggles for calibrated numeric inputs, and Panels for evidence notes and confidence labels. Keep outputs separated by responsibility: massing, glass/envelope, brace axes, brace solids, transfer bands, podium, masts, landmarks, and diagnostics.

Rhino owns:

- the model units and coordinate frame;
- baked review geometry and layer organization;
- named orthographic and fitted perspective views;
- viewport captures;
- material/display settings; and
- the final `.3dm` deliverable.

Rook owns orchestration and evidence collection:

- admit and snapshot the live Grasshopper document before every bounded mutation;
- create and edit only execution-owned components;
- wait for settled solves and inspect diagnostics;
- capture Rhino validation views;
- retain a calibration ledger; and
- avoid replaying already committed operations after partial success.

## Working Artifacts

Execution outputs live under the ignored workspace directory:

```text
artifacts/bank-of-china-tower/
  BankOfChinaTower.gh
  BankOfChinaTower.3dm
  evidence/
    manifest.json
    assumptions.json
  validation/
    landmarks.json
    cameras.json
    captures/
    overlays/
    report.md
  execution-ledger.json
```

The source images remain in place and are referenced by absolute path. They are not copied into the repository.

## Calibration and Validation

### Analytical views

For each analytical elevation, section, plan, or axonometric, record normalized two-dimensional landmarks in image coordinates. Use stable semantic names such as `base_sw`, `setback_25_east`, `roof_north`, and `mast_left_top` rather than pixel-only identifiers.

The massing passes when:

- normalized root-mean-square landmark error is at most 1% of image diagonal for analytical orthographic views;
- the four plan states agree with the visible footprint topology;
- all primary setbacks have the correct order and orientation; and
- no sector gaps, duplicate coincident skins, or invalid primary bodies are present.

### Photographic views

Fit one independent Rhino camera per photograph after the massing is stable. Use distributed corresponding landmarks and save every accepted camera as a named view. Because the supplied photographs may be asymmetrically cropped or perspective-corrected, camera fit is a validation operation rather than a source of metric dimensions.

A photographic view passes when:

- normalized root-mean-square error for major corners, setbacks, brace nodes, roof, and masts is at most 2% of image diagonal;
- the projected silhouette agrees without changing geometry solely for that view;
- the primary brace graph has the correct visible incidence and direction; and
- any remaining discrepancy is recorded with a confidence class and explanation.

Raw pixel similarity is not an acceptance metric because glass reflections, sky, exposure, vegetation, and neighboring buildings vary independently of geometry.

## Review Checkpoints

1. **Evidence calibration:** approve orientation, scale, named levels, and the landmark manifest.
2. **Massing:** approve the four-sector bodies and all analytical silhouettes with detail disabled.
3. **Super-frame:** approve nodes, diagonal incidence, and transfer bands in orthographic views.
4. **Envelope and secondary geometry:** approve façade rhythm, podium, roof frame, and masts.
5. **Nine-source audit:** approve saved cameras, composite-sheet comparisons, captures, residuals, and the final uncertainty report.

No later checkpoint may conceal a failure from an earlier checkpoint. If an edit improves one view while exceeding the accepted tolerance in another, reject the edit or expose a more appropriate shared parameter.

## Error Handling and Preservation

- Stop if the active Rhino or Grasshopper document cannot be unambiguously admitted.
- Preserve all pre-existing Rhino and Grasshopper content; mutate only execution-owned objects.
- Treat script compilation errors, invalid primary bodies, failed saves, and missing captures as stop conditions.
- Treat mullion or display-member failures as degradations: report them and continue with validated massing and brace axes intact.
- Store assumptions separately from measured parameters.
- Use fresh epochs for every Grasshopper mutation and inspect every partial-success response before retrying.
- Bake only after the final Grasshopper state has passed the nine-view audit.
- Save the Grasshopper definition through a verified host-supported path. If the admitted Rook surface cannot save the active Grasshopper document, the only manual handoff is an explicit Grasshopper **Save As** to the specified artifact path; geometry generation and validation remain automated.

## Deliverables

- an editable Grasshopper definition with exposed calibration parameters;
- a layered Rhino model containing the accepted exterior reconstruction;
- named Rhino validation views for every distinct exterior orientation, plus a comparison artifact for each of the nine source images;
- a validation report listing landmark residuals and unresolved low-confidence assumptions; and
- an execution ledger sufficient to turn the reconstruction into a future image-to-parametric-CAD training episode.
