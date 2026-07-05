# CanvasDirector Template Promotion Design

Date: 2026-07-04
Branch: `codex/canvas-director-template-promotion`

## Goal

Promote the captured Pearson CanvasDirector prototype into durable,
repo-versioned template assets that can be used to create and refine future
Grasshopper proposal graphs.

The prototype capture remains the working reference. The promoted templates
become the reusable authoring substrate.

## Source Capture

The source of this slice is the live Pearson capture:

`C:\Users\bring\OneDrive\Desktop\Pearson\ANIMATION\V2\.rook\director\prototype_captures\pearson_canvas_director_prototype_20260704_144510`

Important captured artifacts:

- `template_candidates/canvas_director_pearson_prototype.template_candidates.json`
- `gh_snapshot.data.json`
- `canvas_extract_envelope.raw.json`
- `scripts/*.cs`
- `referenced_project_artifacts/director_planning`
- `canvas.png`

The capture recorded:

- 52 Grasshopper components plus 4 groups;
- 55 wires;
- 0 Grasshopper errors;
- 0 Grasshopper warnings;
- 9 readable C# script components;
- a read-only CanvasDirector extraction envelope;
- matching live and persisted `canvas_export_state_sha256`:
  `44bcaf61c8446bfcab84e518bb5cfd7019d7891594053e727c841663adc1cfb7`.

## Architectural Position

Grasshopper remains the editable proposal surface. Director remains the runtime
truth.

Templates are authoring assets. They help Rook create and refresh proposal
graphs, but they are not a parallel rendering or animation runtime. The durable
runtime path remains:

`CanvasProposal -> CanvasExportState -> DirectorAuthoringSpec -> DirectorTrack -> DirectorRunArtifacts`

This slice must not change Native capture, Director compile behavior, video
assembly, or the existing CanvasDirector extraction contract.

## Promotion Model

The captured prototype splits into three artifact classes:

1. **Template Pack**
   Repo-versioned generic CanvasDirector components with stable ids, versions,
   pin schemas, script source, script hash, default values, and notes about
   expected outputs.

2. **Fixture Binding**
   Project-specific Pearson values used to instantiate the templates for a
   smoke fixture. These include actor-set paths, object ids, proposal ids,
   export ids, camera defaults, FPS, frame count, and motion magnitudes.

3. **Reference Capture**
   The captured `.rook/director/prototype_captures/...` directory remains the
   historical source evidence. It is not the promoted template pack.

The implementation should preserve this separation. A template should not
hard-code Pearson-only ids or project-local paths unless the field is explicitly
declared as a default binding placeholder.

## Promoted Template Ids

The first template pack should promote these core templates:

| Template id | Role | Source prototype |
| --- | --- | --- |
| `canvas_director.export_marker` | Extractable typed export marker | `CanvasDirector Export:pearson_animation_test` |
| `canvas_director.clock` | Timeline and scrub state | `Director Clock` |
| `canvas_director.timing_gate` | Local timing window and active-state gate | `Director Timing Gate` |
| `canvas_director.oscillator` | Reusable normalized motion curve | `Director Oscillator` |
| `canvas_director.actors_v2` | Actor-set and grouping resolver | `Director Actors` |
| `canvas_director.transform` | Transform authoring and preview primitive | `Director Band Peel Wave Preview` |
| `canvas_director.camera_path` | Camera location/target path sampling | `Director Camera Path` |
| `canvas_director.camera_controller` | Camera state payload and optional viewport preview | `Director Camera Controller` |

### Transform Naming

The band peel component must not be promoted as
`canvas_director.band_peel_wave_preview`.

The durable template id is:

`canvas_director.transform`

The current band peel behavior is a strategy or preset of that transform
template:

`strategy: "band_peel_wave"`

This keeps the template contract aligned with Director runtime truth: the
component authors transform/keyframe intent, not only one visual motion effect.

Future transform strategies may include:

- `translate`
- `lift`
- `band_peel_wave`
- `rotate`
- `scale`
- `path_follow`

The canvas-facing label may remain friendly, for example `Director Transform`
or `Director Movement`, but the contract id should be `canvas_director.transform`.

## Deferred Prototype Components

`Director Block Piece Preview` should remain diagnostic for this slice.

It was captured and should stay available as reference evidence, but it should
not be promoted as a first-class template until it has a project-agnostic role.
Possible future roles include:

- `canvas_director.single_actor_probe`
- `canvas_director.selection_preview`
- `canvas_director.debug_piece_preview`

This slice should not choose one prematurely.

## Template Asset Shape

Each promoted template should carry:

- `template_id`
- `template_version`
- `role`
- display name and default nickname
- source script file path
- source script SHA-256
- input pin schema
- output pin schema
- default input controls
- expected output payload kind, when applicable
- required metadata markers, when applicable
- fixture-binding placeholders
- promotion notes from the Pearson source capture

For script components, the promoted script source should be stored as a normal
repo file rather than embedded only in a large manifest. The manifest should
refer to script paths and hashes.

## Fixture Binding Shape

The Pearson fixture binding should contain project-specific values separately
from generic template definitions:

- `project_root`
- Rhino document path and hash
- Grasshopper source document path and capture id
- `export_id`
- `proposal_id`
- actor-set paths
- grouping paths
- source object ids
- FPS and frame count defaults
- motion height/default transform strategy values
- camera default strategy

This binding may live in tests or docs during the first promotion slice. It
should not become the only way templates work.

## Creation And Extraction Flow

The first implementation should avoid adding a new Native route.

Python/MCP or test harness code may instantiate templates through existing GH
routes:

- create script components;
- set script source and pins;
- create controls;
- wire components;
- group components;
- solve;
- call existing `/director/canvas/extract`.

The generated clean fixture must be extracted through the existing
CanvasDirector route and produce a valid `CanvasExportState`.

## Non-Goals

- No new Native HTTP route.
- No new public Companion surface.
- No changes to Director compile or run artifacts.
- No changes to frame capture or video assembly.
- No promotion of `Director Block Piece Preview` as a core template.
- No hard-coded Pearson ids inside generic templates.
- No separate animation or rendering system.

## Failure Model

Template promotion should fail early when:

- a manifest entry references a missing script file;
- a script hash does not match the manifest;
- a required pin schema is missing or malformed;
- a required metadata marker is missing;
- a Pearson fixture binding refers to a missing captured artifact;
- clean fixture extraction does not produce a valid `CanvasExportState`;
- generated export state differs from the expected fixture contract for fields
  that are meant to be deterministic.

## Tests And Verification

The implementation plan should include:

1. Manifest tests for required template ids, versions, roles, script paths, and
   hashes.
2. Schema tests for required pins and output payload kinds.
3. A guard proving `canvas_director.transform` is the promoted id and
   `canvas_director.band_peel_wave_preview` is not promoted as a template id.
4. A guard proving `Director Block Piece Preview` remains diagnostic/deferred.
5. Fixture-binding tests that keep Pearson-specific values out of generic
   templates.
6. A live or semi-live clean fixture smoke that instantiates the template pack
   and runs CanvasDirector extraction through the existing route.
7. The Pearson golden smoke remains available as a higher-confidence acceptance
   check after template promotion.

## Acceptance Criteria

This slice is complete when:

- the repo contains a versioned CanvasDirector template manifest;
- promoted script sources are stored as repo files with pinned hashes;
- `canvas_director.transform` is the transform primitive;
- `band_peel_wave` is encoded as a transform strategy/preset;
- `Director Block Piece Preview` remains captured but not promoted;
- Pearson-specific data lives in fixture bindings, not generic templates;
- tests prove the template pack is internally consistent;
- a generated clean proposal graph can be extracted into a valid
  `CanvasExportState` using the existing CanvasDirector route.
