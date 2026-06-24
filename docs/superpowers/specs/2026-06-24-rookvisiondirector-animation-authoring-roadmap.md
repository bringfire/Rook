# RookVisionDirector Animation Authoring Roadmap

Date: 2026-06-24
Status: proposed post-PR2 roadmap

## Purpose

PR #346 adds native live replay for baked Director animation tracks:
guarded, cancellable, display-only playback of coordinated object transforms
and camera frames in Rhino. That makes replay a reliable preview substrate, but
it does not by itself make animation authoring ergonomic for agents.

This roadmap defines the next slices after PR2. The goal is for Codex, Claude,
and other Rook agents to author, preview, revise, persist, and eventually publish
coordinated animation sequences without hand-writing giant per-frame JSON blobs.

## Relationship To Existing Roadmaps

This document extends, rather than replaces,
`docs/superpowers/specs/2026-05-20-rookvisiondirector-camera-video-roadmap.md`.

The May roadmap established the deterministic frame spine:

- camera planning contract extraction;
- timeline FPS/duration/frame-count normalization;
- native curve sampling;
- platform-native MP4 assembly;
- planned `curve_follow_target` camera strategy;
- later artifact and RookVision publishing.

PR2 adds a different but complementary capability: live replay of a fully baked
track before capture or export. The post-PR2 roadmap should now treat replay as
the fast preview loop and frame capture/video assembly as the durable output
loop. Both should consume the same authored animation semantics wherever
possible.

## Current Baseline After PR2

After PR #346 lands, Rook has:

- native `POST /director/replay` for synchronous display-only replay;
- native `POST /director/replay/cancel` for worker-thread cancellation;
- Python and MCP replay tools;
- shared `DirectorFrame` primitives used by frame capture and replay;
- a live replay gate covering completion, restoration, cancel-mid-replay,
  already-active rejection, validation, and no-mutation-on-late-malformed-frame;
- existing Director frame capture and MP4 assembly for durable outputs.

The replay contract is intentionally bounded:

- max 256 animated objects;
- max 3000 frames;
- `transform_semantics == "absolute_from_source"`;
- transform-based object animation, not arbitrary geometry deformation;
- full baked track input, not a high-level keyframe language;
- synchronous live preview, not a persistent timeline editor.

Those limits are acceptable for PR2. The next work should add authoring layers
above the baked track contract before expanding replay's native surface.

## Design Principle

Agents should author intent, not raw frame payloads.

The durable authoring model should be:

```text
storyboard / animation intent
  -> structured animation plan
  -> validated baked track
  -> live replay preview
  -> revise
  -> capture / assemble / publish
```

The baked replay track remains the low-level interchange format consumed by
native replay. It should not become the primary format agents manipulate for
complex work.

## Roadmap

### PR3: Replay Handler Decomposition

Decompose `HandleDirectorReplay` onto the same request-envelope shape used by
frame-capture and neighboring Director handlers.

Deliverables:

- typed `ReplayRequest` / `ReplayTrack` parsing helpers;
- `ParseBodyAndDocSn(req)` or equivalent shared request parsing at the handler
  boundary;
- smaller validation helpers for session id, replay options, caps, and track
  envelope consistency;
- a smaller UI-thread dispatch payload;
- no behavior changes to replay outcomes or error codes.

Why first:

- PR2's live gate proves the feature works;
- the replay handler remains the architectural outlier;
- decomposition is hardening and maintainability work, not a PR2 bugfix;
- doing it in its own PR keeps the regression surface easy to review.

Acceptance:

- existing PR2 replay source, unit, MCP, and live tests remain green;
- live replay gate remains 6/6 on a fully clean native build;
- `/director/frame-capture` remains behaviorally unchanged;
- no new replay capability is added in this slice.

### PR4: Animation Compiler

Add a high-level animation authoring layer that compiles agent-friendly
instructions into the baked replay track shape.

The input should describe animation intent:

- object groups;
- keyframes;
- timing;
- easing;
- camera shots;
- camera targets;
- simple shot types such as hold, orbit, dolly, pan, truck, and curve-follow;
- restore policy and preview/export intent.

The compiler should produce:

- a validated baked track with `camera_frames` and `object_frames`;
- provenance connecting each generated frame back to the source plan;
- clear errors when an authored motion cannot be compiled into the current
  PR2 replay contract.

Python should own this layer. Native should continue consuming explicit
per-frame camera/object state.

Acceptance:

- agents can create a multi-object, multi-camera-shot animation from a compact
  structured request;
- generated tracks replay through PR2 without native contract changes;
- generated tracks can also feed existing frame capture / video assembly where
  compatible;
- tests cover keyframe interpolation, easing, object grouping, camera shot
  compilation, validation failure, and provenance.

### PR5: Preview, Critique, And Iterate Loop

Build an agent workflow around live replay and visual feedback.

The loop should be:

```text
generate plan -> compile track -> replay -> capture evidence -> critique -> edit plan
```

The evidence can start modestly:

- replay result metadata;
- sampled frame captures before/after replay;
- optional short preview video from the existing MP4 assembly path;
- structured notes about what changed between revisions.

The important product behavior is that the agent can revise the authored plan,
not patch individual low-level frame transforms by hand.

Acceptance:

- an agent can run at least one revise-and-preview cycle from a saved plan;
- preview failure leaves the Rhino document restored unless the plan explicitly
  asks to keep the final completed state;
- the workflow records enough evidence for a later agent to understand what was
  previewed and why it was revised.

### PR6: Persistent Animation Artifacts

Introduce a durable saved animation artifact format.

The artifact should store:

- the high-level animation plan;
- compiled track metadata or a compiled-track reference;
- source object ids and source-state fingerprints;
- timeline and FPS information;
- camera strategy provenance;
- preview/capture outputs;
- revision history or parent artifact id.

This should make animation authoring resumable across agent sessions. The saved
artifact is the editable source of truth; the baked track is a compiled output.

Acceptance:

- save/load named animation plans;
- recompile a saved plan and detect stale object/source-state assumptions;
- attach preview outputs and final videos without changing the editable plan;
- preserve enough provenance for review and debugging.

### PR7: Richer Scene Semantics

Expand what the high-level authoring layer can express after the plan/compile
and preview loops are stable.

Candidate capabilities:

- visibility and layer toggles over time;
- display mode and render setting changes per shot;
- material or color changes;
- path-following helpers;
- camera target tracking;
- orbit and turntable presets;
- assembly/disassembly sequences;
- exploded views;
- constraints between object groups;
- named shot libraries.

These should compile to explicit native operations only when the mutation and
restore semantics are clear. Avoid adding native replay features just because a
single authored demo wants them.

Acceptance:

- each new semantic has a clear compile target;
- validation can reject unsupported combinations before native replay;
- restore behavior is explicit and test-covered;
- frame capture and live replay remain aligned where both support the semantic.

## Deferred

The following are not immediate post-PR2 work:

- unlimited object/frame counts;
- concurrent live replays;
- arbitrary geometry deformation;
- physics simulation;
- audio;
- a visual timeline editor;
- a full NLE;
- direct UI/gallery publishing as part of replay hardening;
- expanding native replay before the high-level authoring layer proves the need.

## Recommended Order

1. Replay handler decomposition.
2. Animation compiler.
3. Preview/critique/iterate loop.
4. Persistent animation artifacts.
5. Richer scene semantics.

This order keeps the already-validated replay substrate stable, adds the agent
authoring layer where it belongs, and only expands native semantics after real
compiled-animation needs appear.

## PR2 Roll-In Guidance

This roadmap can be included in PR #346 as a doc-only follow-up because it does
not alter PR2 behavior, tests, native code, or MCP contracts. It clarifies the
deferred work created by PR2 and prevents the post-replay direction from living
only in chat history.

Do not include any implementation from this roadmap in PR #346. If PR #346 is
already under final review and maintainers prefer a minimal diff, land this as
a tiny follow-up docs PR instead. Otherwise, rolling in this single roadmap doc
is reasonable.
