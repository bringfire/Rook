# RookVision CanvasDirector Design

Date: 2026-07-03
Status: ready for user review
Branch: `codex/rookvision-canvas-director`
Base: `origin/main` at `d860b34c0d76a6ece7e13ab199a63d2a38dc6122`

## Purpose

RookVisionDirector needs a Grasshopper-based authoring workflow without making
the Grasshopper canvas the runtime authority for animation capture.

The design principle is:

**Grasshopper is the editable proposal surface. Director is the runtime truth.**

Rook can create a Grasshopper proposal graph from versioned CanvasDirector
templates, the user can tweak curves, sliders, keyframes, camera controls, actor
groups, and other authoring controls, and the Companion can safely extract typed
declared outputs. After extraction, the Grasshopper canvas is not authoritative.
Only declared CanvasDirector export components are read. The durable
`DirectorAuthoringSpec` becomes canonical for animation intent, and Director
tracks/run artifacts become canonical for execution.

## Scope

In scope for this design:

- a Rook-owned `RookVisionCanvasDirector` module, not a separate plugin;
- versioned CanvasDirector template components for proposal graphs;
- side-effect-free extraction of typed Grasshopper exports into
  `CanvasExportState`;
- project-local persistence of `CanvasExportState` and `DirectorAuthoringSpec`;
- a first compile path from `DirectorAuthoringSpec` into existing Director track
  data;
- reuse of existing Director capture, evidence, video assembly, and publish
  contracts;
- public Native routes under `/director/canvas/...` as thin managed-dispatch
  facades.

Out of scope for the first slice:

- treating arbitrary Grasshopper canvas topology as semantic meaning;
- making the GH canvas replayable runtime state;
- GH-preview viewport capture as the default execution path;
- a separate `.gha`, Rhino plugin, or external system outside Rook;
- global nondeterminism analysis of arbitrary upstream GH components;
- replacing the existing Director frame/video artifact structure.

## System Boundary

This module lives inside Rook.

Ownership is split as follows:

- Companion owns proposal graph creation, GH solve coordination, export
  discovery, schema validation, and extraction.
- Python/MCP owns orchestration, project-root policy, canonical JSON
  persistence, spec IDs, spec hashes, compilation, and run setup.
- Native owns only public `/director/canvas/...` facades plus the existing
  Director capture/video primitives.

Native remains the sole public HTTP surface. The managed Companion remains
internal and owns GH runtime behavior because Grasshopper state, scheduled
solutions, slider mutation, canvas metadata, and export component inspection are
managed/GH responsibilities.

## Runtime Truth Model

The canonical chain is:

```text
CanvasProposal
  -> CanvasExportState
  -> Project DirectorAuthoringSpec
  -> Run input copy
  -> DirectorTrack
  -> DirectorRunArtifacts
```

Definitions:

- `CanvasProposal` is the editable GH graph created from CanvasDirector
  templates. It is disposable authoring state.
- `CanvasExportState` is a signed snapshot of typed declared exports. It is not
  a replay substrate.
- `DirectorAuthoringSpec` is project-local durable intent. It can regenerate a
  GH proposal graph later, but regeneration is an editor view of the spec, not
  proof that the previous canvas is authoritative.
- `DirectorTrack` and `DirectorRunArtifacts` are deterministic execution data.
  They must be reproducible without the original GH canvas being open.

**A run must be reproducible from its copied spec and run artifacts without the
original GH canvas open, but the project spec may be used to regenerate an
editable GH proposal graph later.**

Load-bearing invariants:

- `CanvasExportState` is a signed snapshot of typed exports, not a replay
  substrate.
- `DirectorAuthoringSpec` is project-local durable intent and can regenerate a
  proposal graph later.
- `DirectorTrack` and run artifacts must be reproducible without the original GH
  canvas being open.

## Persistence Model

Python/MCP writes project artifacts under the active project `.rook` folder:

```text
<project>/.rook/director/
  exports/
    <export_id>.json
  specs/
    <spec_id>.json
```

`<project>/.rook/director/exports/<export_id>.json` stores the exact
`CanvasExportState` returned by Companion.

`<project>/.rook/director/specs/<spec_id>.json` stores reusable
`DirectorAuthoringSpec` intent. This file is project-local and durable.

Each capture run copies the exact resolved spec into the run folder:

```text
<run_root>/<run_id>/inputs/director_authoring_spec.json
```

The run input copy is immutable evidence of exactly what was executed. It must
include, when applicable:

- `source_spec_id`;
- `source_spec_sha256`;
- `canvas_export_state_sha256`;
- `template_version`.

Project spec writes must use replace-by-write/atomic semantics. Specs and
exports must carry a simple `schema_version` so future templates and compilers
can migrate old documents cleanly.

The Director output root remains run/product-oriented. It is not the only place
to store reusable authoring intent.

## Extraction Route

The first public route is:

```text
POST /director/canvas/extract
```

Native behavior:

- parse the request body as a JSON object;
- reject malformed JSON or wrong body kind with `invalid_input`;
- inject an op discriminator, initially `extract`;
- forward through one managed `canvas_director_dispatch` callback;
- return the managed response as-is;
- return `canvas_director_unavailable` when the managed callback is not
  registered or cannot be invoked.

Companion behavior:

- resolve the active or explicitly specified GH document;
- optionally require proposal/export identity to avoid extracting the wrong
  canvas;
- optionally request a solve without synchronous solver re-entry;
- wait for verified solve completion before reading outputs;
- discover only declared CanvasDirector export components;
- validate declared export schemas and template metadata;
- return canonical `CanvasExportState`, `sha256`, diagnostics, and optionally a
  `suggested_spec_id`;
- include `read_only: true` in the response.

Extraction is read-only with respect to project artifacts. Persistence begins
only after Python/MCP accepts and writes the returned `CanvasExportState`.

If multiple export components exist and no `export_id` is specified, extraction
fails with `multiple_exports_ambiguous`. Automation should pass explicit
document, proposal, and export identity whenever possible.

## CanvasExportState Contract

`CanvasExportState` contains:

- `schema_version`;
- `export_id`;
- `created_utc`;
- Rhino document identity;
- Grasshopper document identity, such as file path plus runtime identity where
  available;
- `proposal_id` when available;
- `template_id` and `template_version`;
- `export_components[]` with component GUIDs, nicknames, schema versions, and
  diagnostics;
- typed payloads such as timeline, actors, object motions, camera, display, and
  capture intent;
- GH warnings and errors visible to the export surface;
- solve metadata: requested, completed, duration, timeout, and solution serial
  when available;
- `read_only: true`;
- `sha256` over canonical JSON.

The hash contract is canonical, not advisory. The canonical JSON rule is:

- UTF-8 encoding;
- sorted object keys;
- no insignificant whitespace;
- stable string escaping;
- stable number encoding: finite JSON numbers only, invariant-culture decimal
  rendering, no leading plus sign, no leading zero except `0`, integer-valued
  numbers rendered without a fractional part, and floating-point values rendered
  with a shortest round-trip representation;
- no `NaN`, `Infinity`, or non-JSON numeric values.

Companion computes `sha256` over that canonical JSON. Python/MCP recomputes the
same hash before writing the export. A mismatch fails with
`export_hash_mismatch`.

Nondeterminism diagnostics are limited to declared CanvasDirector
export/template metadata or explicit export-component diagnostics. The first
slice does not promise global analysis of arbitrary components upstream on the
canvas.

## Compile Path

The first prototype uses GH as a frame-evaluation and authoring engine, not as a
capture renderer.

Flow:

1. User describes an animation.
2. Rook creates or refreshes a GH proposal graph from versioned CanvasDirector
   templates.
3. User edits the proposal graph.
4. Python/MCP calls `/director/canvas/extract`.
5. Companion returns `CanvasExportState`.
6. Python/MCP writes the export and compiles it into `DirectorAuthoringSpec`.
7. Python/MCP compiles the spec into existing Director-compatible track data.
8. Existing Director capture, evidence, video assembly, and publish machinery
   produce the artifact.

Approach 1 is the selected first slice: compile typed GH exports into baked
Director tracks and use existing Director capture.

Approach 2, GH-preview viewport capture, is a later explicit capture mode, not a
fallback path. It changes the truth model because preview visibility, GH display
state, and canvas-side render behavior become part of execution evidence.

## Failure Model

Native/facade failures:

- `invalid_input`;
- `canvas_director_unavailable`.

Companion extraction failures:

- `grasshopper_not_ready`;
- `document_mismatch`;
- `solve_locked`;
- `solve_timeout`;
- `solve_failed`;
- `export_not_found`;
- `multiple_exports_ambiguous`;
- `export_schema_mismatch`;
- `export_component_error`;
- `nondeterministic_component_detected`;
- `unsupported_template_version`.

Python/MCP persistence and compile failures:

- `project_root_missing`;
- `export_hash_mismatch`;
- `spec_write_failed`;
- `spec_compile_failed`;
- `director_run_setup_failed`.

Extraction must not synchronously call back into Native capture or video routes
from inside the managed dispatch callback. The first slice keeps extraction,
persistence, compilation, and capture as separate stages to avoid callback
re-entry, route-thread exhaustion, and deadlock-prone control flow.

## Evidence Requirements

Minimum export evidence:

- GH document identity;
- Rhino document identity;
- proposal/export identity;
- template ID and template version;
- export component IDs and schema versions;
- canonical export hash;
- solve requested/completed status;
- solve timing and timeout;
- GH warnings/errors visible to export components;
- `read_only: true`.

Minimum run evidence:

- copied `director_authoring_spec.json`;
- `source_spec_id`;
- `source_spec_sha256`;
- `canvas_export_state_sha256`;
- template version where applicable;
- compiled Director track identity/hash;
- standard Director frame manifest and frame evidence;
- video manifest from existing assembly.

## First Slice

The first implementation slice should prove the round trip with one narrow
template family:

- timeline controls;
- one actor/group selection export;
- one object motion export;
- one camera export;
- one compile path to existing Director track data;
- existing Director capture and video assembly.

Acceptance criteria:

- Rook can create or refresh a proposal graph from known templates.
- Companion can extract a selected or explicit CanvasDirector export.
- Extraction is side-effect-free with respect to `.rook` project artifacts.
- Python/MCP writes export and spec files under `.rook/director/...`.
- Python/MCP recomputes and verifies the export hash before writing.
- Python/MCP compiles the spec into a Director-compatible track.
- A Director run copies the exact spec into `inputs/director_authoring_spec.json`.
- The run can be reasoned about without the GH canvas open.
- Existing Director video assembly remains the video path.

## Test Strategy

Unit tests:

- canonical JSON hash stability;
- export hash mismatch rejection;
- spec atomic write helper behavior;
- route op injection and malformed-body `invalid_input`;
- managed-dispatch unavailable response;
- compile validation from sample `CanvasExportState` to
  `DirectorAuthoringSpec`.

Managed tests:

- export discovery ignores non-export components;
- ambiguous exports fail without explicit `export_id`;
- unsupported template versions fail;
- declared export component diagnostics are carried into the response;
- extraction response includes `read_only: true`.

Live Rhino/GH smoke:

- create a minimal proposal graph;
- extract from the active GH document;
- verify one completed solve before output read;
- write project export/spec through Python/MCP;
- compile and run a short Director capture;
- assemble video through the existing Director assembler.

## Open Design Pressure

GH-preview capture may still be needed for workflows where Grasshopper preview
display is the visual truth. That should be designed as an explicit later
capture mode with its own evidence and display-state contract, not as an
implicit fallback when baked Director tracks are incomplete.
