# VIP Tree Primary Bifurcation Design

**Date:** 2026-09-01  
**Status:** Approved in conversation; awaiting review of this written record  
**Target artifacts:** `Tree.3dm` and `Tree.gh` in the VIP Trees study directory

## Intent

Extend the existing wire-tree trunk into a convincing primary bifurcation while preserving the continuous flow of the original strands. The fork must read as a division of the trunk's strand field, not as two branches attached to a completed trunk. It must be spatially credible from all sides and remain directly shapeable through Rhino guide geometry.

The first implementation stops after the primary split. Secondary branches, locally introduced strands, leaves, fabrication rationalization, and final structural detailing remain outside this stage.

## Existing Definition

The current study has:

- an editable Rhino base ellipse and parent spine;
- a Grasshopper C# trunk generator with controls for strand count, sampling, gathering, taper, twist, and weave;
- curve and pipe preview geometry; and
- saved Front, Right, Top, and Perspective evaluation views.

The current generator produces the desired family of tapered strands, but its sampling, framing, strand construction, and preview preparation are concentrated in one script. The extension will preserve its visual controls while separating the parent field, bifurcation, and final geometry responsibilities.

## Authoritative Inputs

Rhino owns the major sculptural gestures:

1. **Base ellipse** — existing editable footprint driver.
2. **Parent spine** — existing editable trunk-gesture driver.
3. **Primary Branch A Driver** — a new editable 3D curve for the stronger, more vertically continuous child.
4. **Primary Branch B Driver** — a new editable 3D curve for the more outward child.

The two child curves begin below the visible fork and overlap the parent spine through an approximately one-metre transition zone. Their control points remain freely editable in Rhino. Neither child is constrained as a mirror of the other, and there is no separate continuing main trunk above the split.

Grasshopper owns the strand-field transformation and exposes controls for:

- split ratio, initially approximately 60/40;
- transition length;
- split-seam rotation around the parent field;
- central-throat or crossover amount;
- independent child taper; and
- independent child twist.

Any additional irregularity must be deterministic and subtle. Random noise is disabled by default.

## Modular Architecture

### 1. Parent Strand Field

Refactor the existing trunk generator into a focused component that transports an ordered set of strand samples along the parent spine. In addition to preview curves, it exposes a plain-data strand-field contract:

- one ordered point path per strand;
- sampled section frames or equivalent planes;
- stable integer strand identities; and
- section parameters needed by the bifurcation stage.

The data exchanged between components uses Rhino and Grasshopper-native types such as points, planes, integers, curves, and data trees. It does not depend on custom cross-component C# classes or an external assembly.

### 2. Primary Bifurcation

A dedicated scripted component receives the parent field, both child-spine curves, and the bifurcation controls. Its responsibilities are limited to:

- selecting a rotatable split seam in the ordered parent cross-section;
- partitioning the existing strands into two contiguous child groups;
- conserving every parent strand and its identity;
- staggering the divergence so one child begins peeling away before the other;
- transporting both groups smoothly from the parent frames to independent child frames;
- maintaining a controllable dense central throat with limited strand crossover; and
- emitting continuous child point fields and combined full strand paths.

The arrowed location in the reference is treated as the visual midpoint of a transition region, not as a mathematical branch point. Smooth eased interpolation governs the handoff to each child spine. No primary strand is created, deleted, cut, or joined at the fork.

### 3. Curve and Pipe Preview

A separate stage converts the continuous strand paths into interpolated curves and optional pipe Breps. This keeps display geometry, wire radius, and pipe caps independent of the field topology.

### 4. Later Secondary Branching

Each child field is emitted in the same conceptual format as the parent field so a later branch module can consume it. Secondary branches may eventually use either peeled parent strands or locally introduced strands, but that logic is excluded from the primary-bifurcation component.

## Asymmetry

Asymmetry is deliberate and editable rather than stochastic. It comes from:

- independently shaped 3D child spines;
- an adjustable, initially unequal strand allocation;
- a rotatable split seam;
- staggered divergence through the overlap zone; and
- independent taper and twist on the child fields.

The default study makes Branch A the more vertical and visually dominant flow and Branch B the more outward flow. The controls permit reversing or softening that relationship without redrawing the entire definition.

## Validation and Failure Behavior

The component should return a clear warning and avoid misleading preview geometry when required curves are missing or invalid. Numeric controls should be clamped to safe ranges, and incompatible strand counts or transition settings should be reported in a summary output.

The primary bifurcation is accepted when:

1. every parent strand remains a continuous curve from the base into exactly one child field;
2. the total child strand count equals the parent strand count;
3. editing either Rhino child-spine curve updates the corresponding bundle predictably;
4. the transition is smooth, visually dense, and free of an obvious graft or hard Y-junction;
5. the two children are visibly asymmetric in direction and mass;
6. the split reads as spatially convincing in Front, Right, Top, and Perspective views;
7. the Grasshopper canvas reports no runtime errors or warnings; and
8. parent-field, bifurcation, and curve/pipe responsibilities remain separate.

## Preservation Boundaries

- Preserve the user's current trunk controls and editable Rhino drivers.
- Do not introduce Florasynth or another external runtime dependency.
- Do not bake the generated strand or pipe geometry during this stage.
- Do not add secondary branches, leaves, fabrication joints, or structural members yet.
- Do not impose bilateral symmetry or unseeded randomness.

## Rejected Alternatives

- **One expanded monolithic script:** faster initially, but obscures topology and makes later branching difficult to reuse.
- **Many small scripts for every calculation:** visually transparent but produces excessive wiring and fragile data-tree coupling.
- **Branches appended to completed trunk curves:** contradicts the continuous-flow character of the reference.
- **A single exact fork point:** produces an abrupt junction and gives strands no space to sort in three dimensions.
- **Perfect 50/50 mirrored children:** loses the natural hierarchy visible in the reference.
- **A custom compiled helper assembly:** reduces portability and creates an unnecessary dependency for this study.

## Next Stage

Because this change refactors the live parent generator and establishes the data contract for future branching, a short implementation plan is warranted after this written design is approved. Implementation will then proceed in bounded checkpoints: preserve the current trunk, expose its field data, add the Rhino child drivers, build the primary bifurcation, and validate the four review views before any secondary branching work.
