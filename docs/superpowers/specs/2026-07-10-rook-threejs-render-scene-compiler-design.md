# Rook Three.js Render Scene Compiler Design

## Purpose

Design a Rook workflow that prepares a Rhino model for efficient Three.js
delivery without making the user reason about export internals, draw-call
batching, or synchronization ownership.

The user edits the authoritative Rhino model and deliberately invokes **Update
Render Scene** when ready to preview. Rook synchronizes a persistent derived
Rhino render scene, applies an evidence-backed optimization profile, publishes
an optimized Three.js scene package, validates it, and refreshes the browser
preview. The authoring model is never mutated by this workflow.

## Existing Rook Substrate

This design builds on capabilities already present in Rook:

- native Rhino object, render-mesh, block, layer, and material access;
- layer creation, movement, merging, visibility, locking, and convention tools;
- material inventory, creation, assignment, and purge tools;
- a Rook-owned GLB writer and validator in the mesh2splat pipeline;
- artifact registration and bounded filesystem-safety patterns;
- Director actor IDs, actor sets, pivots, motion packages, and stable metadata;
- worker/snapshot patterns for preparing derived Rhino documents; and
- the isolated Three.js Rhino stress harness, which proves deterministic GLB
  loading, actor metadata survival, absolute-time animation, static-context
  merging, coordinate comparison, browser CPU/GPU measurement, and lifecycle
  handling.

The existing mesh2splat GLB contract remains purpose-specific. The Three.js
scene compiler defines a separate standards-oriented package contract rather
than silently expanding mesh2splat behavior.

## Product Decision

Use a **manifest-first hybrid compiler**.

The derived `.3dm` is a durable, inspectable Rhino render scene. A canonical
manifest bridges Rhino semantics and Three.js runtime structures. Static
optimizations are baked into the GLB where practical; the manifest instructs
the Rook Three.js runtime how to construct ordinary `Mesh`, `InstancedMesh`,
and `BatchedMesh` representations while preserving actor identity.

The primary user actions are:

1. **Create Render Scene** on first use.
2. **Update Render Scene** after a deliberate editing interval.

Updates never run automatically on save. A source change marks the render scene
as stale, but the user controls when synchronization, compilation, and preview
refresh occur.

## Alternatives Considered

### Rhino-document-first

Make layers, blocks, joined meshes, and materials in the derived `.3dm` the
complete export contract. This is easy to inspect, but Rhino structures cannot
fully express Three.js batching, package-specific actor lookup, or runtime
assembly. Export behavior would depend too strongly on document organization.

### Three.js-runtime-first

Export a mostly raw GLB and optimize it entirely in the browser. This enables
fast experimentation, but large scenes pay unnecessary transfer and startup
costs, and the derived Rhino render scene no longer represents the compiled
deliverable.

### Bidirectional general synchronization

Merge arbitrary geometry edits from both the authoring and render documents.
This creates a large conflict-resolution subsystem and weakens the simple user
contract. The authoring model remains authoritative for geometry.

## Architecture

One versioned scene link connects:

```text
Authoring .3dm
  -> synchronized render .3dm
  -> canonical scene manifest
  -> optimized GLB
  -> Three.js runtime assembly
  -> validation, evidence, and browser preview
```

The architecture has six bounded components.

1. **Source snapshot capture** records stable identity, geometry, transforms,
   hierarchy, layers, blocks, materials, pivots, render meshes, and Director
   metadata.
2. **Render-scene synchronizer** creates or updates the derived `.3dm` while
   preserving recognized render-only content and overrides.
3. **Semantic auditor** applies conventions and classifies every exportable
   object.
4. **Scene compiler** applies the selected optimization profile and builds the
   canonical manifest plus package inputs.
5. **Package writer and validator** produce and verify the GLB, manifest, and
   compilation report in an isolated run directory.
6. **Preview runtime** loads the package, assembles Three.js runtime objects,
   validates browser behavior, and atomically swaps the visible scene.

These components communicate through versioned plain-data contracts and are
independently testable.

## Project Layout And Artifact Model

The first Create Render Scene operation allocates a stable `sceneId` and asks
the user to choose the derived `.3dm` path. The default is a sibling file named
`<source-stem>.render.3dm`. Rook stores project bookkeeping under:

```text
.rook/render-scenes/<sceneId>/
  scene-link.json
  current.json
  promotion.json
  runs/<runId>/
    candidate.render.3dm
    scene.glb
    scene.manifest.json
    compilation-report.json
```

Run directories are immutable after completion. `current.json` is an atomic
pointer to the last successful run. `promotion.json` is a durable promotion
journal that exists only while a validated run is being promoted. The
persistent derived `.3dm` is replaced through a same-directory temporary file
and backup. If the process or machine stops between file replacements, the
next Create or Update command uses the journal and hashes to complete the
promotion or restore the prior derived document before accepting new work.

The scene link records the source document identity, derived document path,
selected profile and version, object mappings, last successful source snapshot,
last successful run ID, and hashes of all promoted artifacts. Paths inside the
project root use safe project-relative references. External derived-document
paths require an explicit user selection and are stored as normalized absolute
paths; Rook never infers a writable path outside the project.

## Update Transaction

**Update Render Scene** performs one transaction:

1. Validate the scene link, source document, destination, profile, and current
   render-scene state.
2. Capture the authoritative source snapshot.
3. Diff it against the last successful snapshot.
4. Produce a candidate derived `.3dm` in the new run directory.
5. Apply semantic preparation and compile the candidate package.
6. Validate the candidate derived document, GLB, manifest, actor mapping,
   visible output, and browser assembly.
7. Write the promotion journal, promote the derived `.3dm`, advance
   `current.json` and `scene-link.json`, verify the promoted hashes, remove the
   journal and backup, and refresh the browser preview.

The scene link advances only when the derived document, package, report, and
preview evidence all describe the same successful run. Ordinary cancellation
or failure stops future work, removes only attempt-owned temporary files, and
leaves the last known-good run current. Interrupted promotion is a recoverable
journaled state, not a successful or failed compilation result.

## Synchronization And Ownership Contract

The authoring model is authoritative for:

- geometry and topology;
- object transforms and hierarchy;
- object presence or deletion;
- source layer membership;
- source material assignments; and
- Director actor identity, actor-set membership, pivots, and authored motion.

The derived render scene owns:

- render cameras;
- lights and environments;
- explicitly recognized material overrides; and
- render-only helper objects and layers.

Rook maintains a stable mapping from source document ID and source object UUID
to the corresponding render-scene object and compiled representation. A source
object copy receives a new identity. Director-authored actor IDs remain
authoritative. An object classified as an actor without Director metadata
receives a deterministic ID of the form `rhino_<uuid-without-separators>` and
that ID is persisted in the scene link.

On update:

- new source objects are added;
- changed objects are replaced or updated;
- deleted objects are removed from the render scene and package;
- unchanged objects may reuse prior compiled results when all dependencies are
  unchanged; and
- a changed layer, material, pivot, hierarchy, or geometry signature
  invalidates every affected merge, instance, or batch group.

Direct geometry edits to synchronized objects in the render scene are not a
second source of truth. The next update restores source geometry and reports
that the render-side edit was superseded. Recognized presentation changes are
preserved. If the render scene has unsaved or unclassifiable changes, promotion
is blocked instead of silently discarding them.

## Semantic Classification

Classification precedence is deterministic:

1. user exclusion or protected override;
2. Director actor or actor-set metadata;
3. saved layer convention;
4. block-instance and canonical geometry-signature evidence; and
5. conservative fallback to an ordinary mesh.

Every exportable object receives one role:

- `static_context`;
- `ordinary_actor`;
- `instance_candidate`;
- `batch_candidate`;
- `render_only`;
- `excluded`; or
- `unsupported`.

Layer paths provide semantic intent but never prove material or geometry
compatibility. Block names suggest reuse but never replace geometry hashing.
The compiler report records the winning rule and evidence for each nontrivial
classification.

## Coordinate And Unit Contract

The source snapshot records Rhino document units and its right-handed Z-up
basis. The Three.js scene GLB uses glTF's right-handed Y-up, meter-based
convention. Conversion is applied exactly once during package compilation.

The manifest keeps these values distinct:

- source origin;
- rebase origin; and
- applied render offset.

Actor pivots are transformed into package coordinates without changing their
local semantics. Large-coordinate scenes use an explicit recorded rebase
origin selected by the compiler profile. Coordinate conversion and rebasing
must pass fixed-camera pixel comparisons before publication.

## Balanced Optimization Profile

Balanced is a versioned profile family. The initial profile is `balanced@1`.
Profiles are immutable, and a scene link remains pinned until the user
deliberately adopts another version.

Every Balanced version performs only transformations proven to preserve exact
geometry, material appearance, identity, pivots, transforms, and visible
output. `balanced@1` automatically applies compatible static-context merging
and material consolidation. It detects and reports instance and batch
candidates but keeps them as ordinary actor nodes until the Slice 2 evidence
gate authorizes a new Balanced version.

### Static context

- Bake source transforms into a common, rebased coordinate frame.
- Merge geometry by exact material and render-state signature.
- Emit one GLB primitive per compatible material bucket.
- Never merge geometry requiring independent visibility, selection, or motion.

### Repeated geometry

- In `balanced@1`, report eligibility and projected savings without changing
  the runtime representation.
- Detect identity with canonical local-space geometry hashes, including
  topology and all required vertex attributes.
- Treat block-definition identity as supporting evidence, not sole proof.
- Preserve one geometry payload and per-instance transforms.
- Map every actor ID to its package-specific instance entry.
- Fall back to ordinary nodes when geometry, material, pivot, or behavior is
  incompatible.

### Batchable actors

- In `balanced@1`, report eligibility and projected savings without changing
  the runtime representation.
- Group distinct geometries only when their normalized material, render state,
  vertex-attribute layout, and runtime behavior are compatible with
  `BatchedMesh`.
- Preserve independent matrices, visibility, selection, raycast identity, and
  actor addressing through the manifest.
- Keep unsupported or ambiguous actors as ordinary meshes.

### Material compatibility

The material signature includes normalized PBR factors, texture content hashes,
texture-coordinate sets and transforms, alpha mode and cutoff, sidedness,
vertex-color requirements, and normal/tangent requirements. Materials are
consolidated only when all appearance-affecting fields are equivalent. Names
alone do not affect compatibility; intentional property differences do.

### Explicit exclusions

Balanced does not automatically:

- decimate geometry;
- generate LODs;
- create texture atlases;
- alter UVs;
- approximate or replace materials;
- discard hidden source geometry permanently; or
- change pivots, actor identity, or animation semantics.

Objects that cannot be optimized safely remain visually complete ordinary
meshes and produce a warning, not a failed compilation.

## Evidence-Backed Profile Evolution

Every profile version records its fixtures, supported Three.js revision,
visual-equivalence thresholds, performance protocol, and benchmark evidence.
A new profile version requires regression tests and fresh browser measurements.
Evidence must distinguish correctness from performance; a faster result that
changes appearance or actor behavior is invalid.

The current stress harness is sufficient for Slice 1 ordinary meshes and
static-context merging. It must be extended before Balanced automatically
enables actor instancing or batching.

## Scene Package Contract

Each successful run contains:

```text
scene.glb
scene.manifest.json
compilation-report.json
```

Supported textures are embedded in the GLB for portable first-slice packages.
The GLB remains standards-compliant and visually complete in a normal glTF
viewer. The manifest adds Rook-specific synchronization, identity, and runtime
assembly data.

The manifest records:

- schema, package, profile, source snapshot, and render-scene versions;
- GLB filename, byte size, and SHA-256;
- source units and basis plus package units, basis, and origins;
- canonical geometry and material signatures;
- deterministic merge, instance, and batch groups;
- actor IDs, actor-set IDs, pivots, and representation types;
- ordinary-node, instance, or batch lookup data;
- compilation warnings and unsupported features; and
- expected structural counts and validation evidence.

Instance and batch indices are package-local implementation details. Consumers
always address actors by `actorId`; the runtime resolves the current index. A
new compilation may reorganize batches without breaking the actor API.

## Three.js Preview Runtime

The first production runtime pins the Three.js revision validated by the
stress harness. It does not import production behavior from the experiment;
shared logic is promoted into production-owned modules with dedicated tests.

The runtime:

1. reads `current.json` and the referenced immutable run;
2. verifies the GLB and manifest hashes;
3. loads the GLB with `GLTFLoader`;
4. builds and validates the ordinary actor index;
5. applies the manifest assembly plan;
6. removes replaced ordinary nodes only after successful runtime assembly;
7. verifies final actor addressability and expected structural counts; and
8. swaps the candidate scene into view.

It exposes a representation-neutral actor API for lookup, metadata inspection,
absolute-time transforms, visibility, selection, actor-set operations, and
translation of raycast results back to actor IDs.

Preview refresh preserves the camera and timeline position when compatible. A
failed refresh leaves the previous scene visible. The preview reports actual
renderer calls, triangles, CPU measurements, GPU timing when available, and
the package/profile provenance.

## User Experience

### Create Render Scene

First use asks for the derived `.3dm` path, selects Balanced by default, creates
the scene link, completes the first transaction, and opens the Three.js preview.

### Update Render Scene

Subsequent source changes mark the scene stale. The explicit update command
shows these stages:

```text
Capturing -> Synchronizing -> Preparing -> Compiling -> Validating -> Refreshing
```

The successful summary reports:

- added, changed, deleted, and unchanged source objects;
- layer and material preparation actions;
- ordinary, merged, instanced, and batched counts;
- before/after nodes, meshes, materials, draw calls, triangles, and bytes;
- actor-addressability and visible-equivalence results;
- profile and package versions; and
- unoptimized objects and reasons.

The preview exposes current, stale, running, cancelled, and failed states plus
links to the derived `.3dm`, current package, and report.

## Failure And Recovery

Failures are stage-specific and include an object ID, actor ID, layer, material,
or package entry when available. Blocking conditions include duplicate actor
IDs, invalid geometry, unsafe paths, unavailable required textures, unsaved
render-scene edits, invalid GLB output, actor-mapping mismatch, visible
divergence, browser assembly failure, or WebGL context loss.

Warnings are non-blocking when the compiler can preserve the original ordinary
representation exactly. Unsupported optimization never justifies dropping an
object.

No failed or cancelled run advances `current.json` or the scene link. Cleanup
is manifest-driven and limited to attempt-owned staging files. Published run
directories are immutable. The previous derived scene, package, report, and
preview remain the last known-good result. On startup, an existing promotion
journal is recovered before the scene can be updated or presented as current.

## Staged Delivery

### Slice 1: End-to-end render-scene workflow

- Create and persist the scene link and derived render `.3dm`.
- Detect source additions, changes, and deletions.
- Apply layer and material semantic classification.
- Preserve ordinary actor nodes, metadata, pivots, and absolute-time behavior.
- Merge exact-compatible static context by material.
- Produce and validate GLB, manifest, report, and automatic preview refresh.
- Preserve render-only cameras, lights, environments, and recognized material
  overrides.
- Publish transactionally and retain the last known-good result.
- Report instance and batch candidates without applying them.

### Slice 2: Instancing and batching

First extend the benchmark harness to compare ordinary meshes,
`InstancedMesh`, and `BatchedMesh` across actor counts, geometry diversity,
materials, transforms, visibility, selection, raycasting, and deterministic
animation. After the evidence gate passes, implement manifest-driven runtime
assembly and enable those Balanced decisions.

### Slice 3: Profile refinement and scale

Add evidence-backed profile revisions, incremental compiled-result reuse,
richer material support, representative large Rhino fixtures, capacity
policies, and improved override management.

## Testing

### Pure tests

- canonical geometry and material signatures;
- scene diffing and dependency invalidation;
- semantic classification precedence;
- Balanced decisions and conservative fallbacks;
- scene-link and manifest schema validation;
- actor mapping across representation changes;
- safe path normalization and attempt-owned cleanup; and
- deterministic reports and hashes.

### Rhino integration tests

- source capture for meshes, Breps, blocks, layers, materials, pivots, and
  Director metadata;
- initial derived-document creation;
- add, change, delete, hierarchy, layer, and material synchronization;
- preservation of render-only cameras, lights, environments, and overrides;
- detection of unsaved or unclassifiable render-scene changes; and
- proof that the authoring document remains unchanged.

### Package and browser tests

- GLB framing, bounds, attributes, materials, embedded textures, and SHA-256;
- `GLTFLoader` round trips and exact metadata survival;
- actor lookup, pivots, transforms, visibility, selection, and raycasts;
- ordinary-versus-optimized fixed-camera pixel equivalence;
- unit, basis, and large-coordinate comparisons;
- actual renderer calls and triangle counts;
- CPU/GPU protocol results across declared presets; and
- stop, reset, cancellation, context loss, and last-known-good refresh behavior.

## Slice 1 Acceptance Criteria

A representative checked-in Rhino fixture contains static context, multiple
materials, repeated blocks, ordinary actors, Director metadata, and render-only
presentation content. Acceptance requires:

- Create Render Scene produces the derived `.3dm`, GLB, manifest, report, and
  live browser preview without changing the source file.
- A second update adds, modifies, and deletes source objects and the changes
  appear across the derived scene and browser preview.
- Actor IDs, actor sets, pivots, materials, and transforms survive both runs.
- Render-only cameras, lights, environment, and recognized overrides survive
  the second update.
- Static-context merging reduces actual browser draw calls while passing the
  fixed-camera visible-equivalence gate.
- Instance and batch candidates are reported deterministically but remain
  ordinary actor nodes in Slice 1.
- Failure injected at every transaction stage preserves the first run as the
  current render scene and preview.
- The source worktree and production dependency boundaries remain clean and
  explicit.

## Out Of Scope

- automatic background synchronization;
- bidirectional geometry merging;
- geometry decimation or remeshing;
- texture atlasing;
- automatic LOD generation;
- cloud hosting or public deployment;
- non-Rhino authoring sources;
- silently upgrading a scene link to a newer optimization profile; and
- using the experiment directory as a production runtime dependency.

## Follow-On Decision

After Slice 1 acceptance, extend the stress harness for instancing and batching.
Only measured, correctness-preserving results may define a new Balanced version
and authorize Slice 2 runtime representations.
