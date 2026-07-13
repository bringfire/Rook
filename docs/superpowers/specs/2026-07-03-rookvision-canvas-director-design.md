# RookVision CanvasDirector Design

> **PARTIALLY SUPERSEDED — Director MCP retirement (2026-07-13):** The general
> non-Director architecture and dated evidence in this document remain available.
> All `rhino_director_*`, `/director`, VisionDirector, and Director-domain examples,
> allowlist entries, count assumptions, acceptance criteria, and positive dispatch
> tests are superseded as of 2026-07-13. Replace those examples with
> non-Director fixtures when maintaining or replaying this work. This document must
> not be used to restore a Director MCP tool. See the
> [Director MCP Surface Retirement Design][director-mcp-retirement].

[director-mcp-retirement]: 2026-07-13-director-mcp-surface-retirement-design.md

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

- Companion owns GH mutation/validation primitives for proposal graph creation,
  GH solve coordination, export discovery, schema validation, and extraction.
- Python/MCP owns proposal template orchestration, project-root policy,
  canonical JSON persistence, spec IDs, spec hashes, compilation, and run setup.
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

`<project>/.rook/director/exports/<export_id>.json` stores the full extraction
envelope returned by Companion:

```json
{
  "canvas_export_state": {},
  "canvas_export_state_sha256": "<sha256>",
  "diagnostics": [],
  "suggested_spec_id": "optional",
  "read_only": true
}
```

The durable export artifact is the envelope, not only the inner
`canvas_export_state`. The hash covers only `canvas_export_state`, so volatile
envelope fields such as route timing diagnostics can differ between retries
without changing the exported runtime state.

`<project>/.rook/director/specs/<spec_id>.json` stores reusable
`DirectorAuthoringSpec` intent. This file is project-local and durable.

Each capture run copies the exact resolved spec into the Director run directory:

```text
<run_directory>/inputs/director_authoring_spec.json
<run_directory>/inputs/provenance.json
```

`run_directory` means the existing Director run directory. It is usually
`<director_output_root>/<run_id>`, but callers that already hold a run directory
must not append the run ID a second time.

`director_authoring_spec.json` is an exact copy of the resolved project spec. It
must not be mutated with run-time provenance fields. `provenance.json` stores
run-time identity and hash facts, including when applicable:

- `source_spec_id`;
- `source_spec_sha256`;
- `canvas_export_state_sha256`;
- `template_version`;
- `copied_spec_sha256`.

Project spec writes must use replace-by-write/atomic semantics. Specs and
exports must carry a simple `schema_version` so future templates and compilers
can migrate old documents cleanly.

The Director output root remains run/product-oriented. It is not the only place
to store reusable authoring intent.

### ID And Path Policy

Python/MCP owns generated export and spec IDs. If a caller supplies an ID, it
must be strictly validated before it is used as a filename.

Allowed ID grammar:

```text
^[a-z0-9][a-z0-9_-]{0,79}$
```

IDs must not contain path separators, `.` segments, drive prefixes, UNC prefixes,
URL encodings that decode to separators, or platform-reserved filename tokens.
Writers resolve paths only by joining the validated ID as `<id>.json` under the
known project directory:

```text
<project>/.rook/director/exports/<export_id>.json
<project>/.rook/director/specs/<spec_id>.json
```

The resolved canonical path must stay under `<project>/.rook/director`.

Export collision behavior:

- if the export file does not exist, write the full extraction envelope
  atomically;
- if the export file exists and its canonical `canvas_export_state` bytes and
  `canvas_export_state_sha256` match the new envelope, treat the write as an
  idempotent retry and do not overwrite the existing file;
- volatile envelope differences such as `diagnostics`, `suggested_spec_id`, or
  route timing do not make a same-state retry fail and do not update the stored
  envelope;
- if the export file exists and the inner canonical state or state hash differs,
  fail with `id_collision`.

Spec writes are atomic replace-by-write only for an explicit update of the same
`spec_id`; accidental collisions fail.

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
- apply the requested solve mode without synchronous solver re-entry;
- wait for verified solve completion before reading outputs when the solve mode
  requires it;
- discover only declared CanvasDirector export components;
- validate declared export schemas and template metadata;
- return an extraction envelope:

```json
{
  "canvas_export_state": {},
  "canvas_export_state_sha256": "<sha256>",
  "diagnostics": [],
  "suggested_spec_id": "optional",
  "read_only": true
}
```

Extraction is read-only with respect to project artifacts. Persistence begins
only after Python/MCP accepts and writes the returned extraction envelope.

If multiple export components exist and no `export_id` is specified, extraction
fails with `multiple_exports_ambiguous`. Automation should pass explicit
document, proposal, and export identity whenever possible.

### Solve Modes

Extraction supports explicit solve modes:

- `require_fresh_solve` is the default. Companion schedules one safe GH solve,
  waits for verified completion, and reads export outputs only after that solve
  finishes. A locked solver, timeout, or solve error fails extraction.
- `reuse_verified_solution` does not schedule a solve. The request must include
  an expected solution serial, watermark, or equivalent document/export freshness
  token. Companion reads outputs only if the current GH document and export
  components prove they match that token. If the runtime cannot verify the token,
  it fails with `unsupported_solve_mode`; if the token is missing, it fails with
  `freshness_token_required`; if the token is present but no longer matches, it
  fails with `solution_stale`.

The first implementation slice should use `require_fresh_solve`. Any no-solve
path without an expected freshness token is out of scope.

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
  compile-affecting diagnostics;
- typed payloads such as timeline, actors, object motions, camera, display, and
  capture intent;
- compile-affecting diagnostics exposed by declared export components;
- GH warnings and errors visible to the export surface when they affect compile
  or runtime truth;
- solve metadata: requested, completed, duration, timeout, and solution serial
  when available.

`CanvasExportState` does not contain its own hash. The extraction envelope
contains `canvas_export_state_sha256`, computed over the canonical
`canvas_export_state` value only, excluding all envelope fields. The persisted
export file stores the envelope so `read_only`, `suggested_spec_id`, and
volatile diagnostics remain available as extraction evidence without changing
the runtime hash.

Volatile extraction diagnostics, such as UI readiness notes, route timing, and
non-compile-affecting warnings, stay outside the hashed snapshot in the envelope
`diagnostics` field. Diagnostics that affect compile/runtime truth belong inside
`CanvasExportState`.

The hash contract is canonical, not advisory. The canonicalizer is RFC 8785 JSON
Canonicalization Scheme (JCS), not a homegrown "shortest round-trip" formatter:

- UTF-8 encoded canonical JSON bytes;
- recursively sorted object properties per JCS;
- no insignificant whitespace;
- JCS string escaping;
- JCS number serialization;
- no `NaN`, `Infinity`, `-0`, or non-JSON numeric values.

Both C# and Python must pass shared JCS test vectors before the hash is treated
as a cross-runtime contract. If either runtime cannot implement JCS exactly for a
numeric payload class, that payload class must encode its exported numeric values
as validated decimal strings produced by a shared formatter before
canonicalization.

Companion computes `canvas_export_state_sha256` over that canonical JSON.
Python/MCP recomputes the same hash before writing the export. A mismatch fails with
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
   templates using existing GH edit/canvas operations orchestrated by
   Python/MCP.
3. User edits the proposal graph.
4. Python/MCP calls `/director/canvas/extract`.
5. Companion returns a side-effect-free extraction envelope.
6. Python/MCP writes the export and compiles it into `DirectorAuthoringSpec`.
7. Python/MCP compiles the spec into existing Director-compatible track data.
8. Existing Director capture, evidence, video assembly, and publish machinery
   produce the artifact.

Approach 1 is the selected first slice: compile typed GH exports into baked
Director tracks and use existing Director capture.

Approach 2, GH-preview viewport capture, is a later explicit capture mode, not a
fallback path. It changes the truth model because preview visibility, GH display
state, and canvas-side render behavior become part of execution evidence.

### Proposal Graph Creation

The first slice does not add a public `/director/canvas/create-proposal` route.
Proposal graph creation is implemented as Python/MCP template orchestration over
the existing GH bridge operations, such as `gh_edit`, canvas focus/zoom, and
snapshot tools. The Companion still owns the GH mutation primitives and runtime
validation behind those existing routes.

CanvasDirector templates should be versioned repo assets or generated template
descriptions consumed by Python/MCP. A later slice may promote proposal creation
to a dedicated `/director/canvas/...` route if the repeated orchestration proves
stable enough to deserve a first-class route.

## Failure Model

Native/facade failures:

- `invalid_input`;
- `canvas_director_unavailable`.

Companion extraction failures:

- `grasshopper_not_ready`;
- `document_mismatch`;
- `unsupported_solve_mode`;
- `freshness_token_required`;
- `solution_stale`;
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
- `invalid_export_id`;
- `invalid_spec_id`;
- `id_collision`;
- `export_write_failed`;
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
- `canvas_export_state_sha256`;
- solve requested/completed status;
- solve mode;
- solve timing and timeout;
- GH warnings/errors visible to export components;
- `read_only: true`.

Minimum run evidence:

- copied `director_authoring_spec.json`;
- `inputs/provenance.json`;
- `source_spec_id`;
- `source_spec_sha256`;
- `canvas_export_state_sha256`;
- `copied_spec_sha256`;
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

- Rook can create or refresh a proposal graph from known templates using
  existing GH edit/canvas operations.
- Companion can extract a selected or explicit CanvasDirector export.
- Extraction is side-effect-free with respect to `.rook` project artifacts.
- Python/MCP writes extraction envelopes and spec files under
  `.rook/director/...`.
- Python/MCP recomputes and verifies `canvas_export_state_sha256` before
  writing.
- Python/MCP compiles the spec into a Director-compatible track.
- A Director run copies the exact spec into `inputs/director_authoring_spec.json`
  and writes run provenance into `inputs/provenance.json`.
- The run can be reasoned about without the GH canvas open.
- Existing Director video assembly remains the video path.

## Test Strategy

Unit tests:

- JCS canonical JSON hash stability from shared C# and Python test vectors;
- export hash mismatch rejection;
- persisted export file shape is the full extraction envelope while the hash
  covers only `canvas_export_state`;
- same-state export ID retries are idempotent and do not overwrite volatile
  envelope diagnostics;
- different-state export ID reuse fails with `id_collision`;
- spec atomic write helper behavior;
- route op injection and malformed-body `invalid_input`;
- managed-dispatch unavailable response;
- ID grammar, path normalization, collision behavior, and under-root checks;
- `export_write_failed`, `spec_write_failed`, and `id_collision` surfaces;
- compile validation from sample `CanvasExportState` to
  `DirectorAuthoringSpec`.

Managed tests:

- export discovery ignores non-export components;
- ambiguous exports fail without explicit `export_id`;
- unsupported template versions fail;
- declared export component diagnostics are carried into the response;
- default `require_fresh_solve` waits for a verified solve before output read;
- `reuse_verified_solution` fails with `freshness_token_required`,
  `solution_stale`, or `unsupported_solve_mode` as appropriate;
- extraction response includes `read_only: true`.

Live Rhino/GH smoke:

- create a minimal proposal graph;
- extract from the active GH document with `require_fresh_solve`;
- verify one completed solve before output read;
- write project export/spec through Python/MCP;
- compile and run a short Director capture;
- assemble video through the existing Director assembler.

## Open Design Pressure

GH-preview capture may still be needed for workflows where Grasshopper preview
display is the visual truth. That should be designed as an explicit later
capture mode with its own evidence and display-state contract, not as an
implicit fallback when baked Director tracks are incomplete.
