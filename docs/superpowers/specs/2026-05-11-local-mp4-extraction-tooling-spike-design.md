# Local MP4 Extraction Tooling Spike Design

Date: 2026-05-11

Status: draft design for review

## Purpose

RookVision video thumbnails and frame sidecars should be produced from the local MP4 after Rook downloads and persists the generated video. Provider payloads may eventually provide useful display-poster hints, but they are optional optimizations. They are not the foundation for `poster`, `start_frame`, or `end_frame` production.

This slice answers one practical question before production design:

Can Rook reliably extract a still frame from a local generated-video MP4 with acceptable dependencies?

## Primary Principle

Local MP4 extraction is the default producer for generated-video sidecars:

- `poster` is a display-only thumbnail.
- `start_frame` is a frame-exact reusable opening-frame input.
- `end_frame` is a frame-exact reusable terminal-frame input.

The spike extracts only one poster candidate frame. It does not implement `start_frame` or `end_frame` production, but the chosen tooling path must plausibly support those later roles.

## Selected Slice

Slice 1 is a design plus small executable spike.

The spike should evaluate `ffmpeg.exe` as the primary candidate by invoking it as an external process. If practical, it should compare Windows Media Foundation feasibility, but a complete WMF implementation is not required for this slice.

This slice chooses a production extraction path from evidence, not from preference.

## Scope

### 1. ffmpeg External-Process Spike

Evaluate `ffmpeg.exe` by running it against a local MP4 input and extracting one poster candidate frame to scratch/temp output.

The starting command shape is:

```powershell
ffmpeg -hide_banner -y -ss 00:00:00.100 -i input.mp4 -frames:v 1 -q:v 2 poster.jpg
```

The spike may adjust this command if the fixture requires it, but it must record the final command and why it changed.

### 2. Binary Discovery Behavior

Binary discovery is tested separately from extraction behavior. The spike must cover:

- explicit configured ffmpeg path;
- `PATH` lookup;
- missing-binary failure.

The implementation must not hardcode a development-machine path. Discovery behavior should be designed so a later packaged binary, admin-installed binary, or user-configured binary can all fit without changing the extraction code.

### 3. Local MP4 Input Only

The spike uses local MP4 input only. The implementation plan must choose the fixture policy before any code is written or any binary file is added. The input may be:

- a small checked-in or generated test fixture, if suitable for repository policy; or
- an existing local generated-video artifact copied/read from the developer machine for manual spike execution.

The design and results must identify which input was used. Provider calls are out of scope.

### 4. Spike Output And Measurements

For each attempted extraction path, record:

- input path shape, sanitized if needed;
- extraction command or API call shape;
- exit code or exception;
- stderr or diagnostic summary;
- output path;
- whether the output image exists;
- output image dimensions;
- elapsed time;
- any dependency or environment assumptions.

The committed findings document must be enough for a reviewer to understand whether the path is production-worthy.

### 5. WMF Feasibility Check

Compare Windows Media Foundation if practical within the spike budget.

The WMF check can be a documented feasibility result rather than a full implementation. It should answer whether the managed companion can realistically use WMF for MP4 frame extraction without adding fragile native interop, COM threading risk, or UI-thread pressure.

If WMF cannot be tested quickly, the spike should explicitly state what blocked it and why ffmpeg remains the recommended path or not.

## Out Of Scope

- No `ArtifactStore` writes.
- No `VideoJobManager` integration.
- No generated-video sidecar production.
- No `poster`, `start_frame`, or `end_frame` manifest updates.
- No Gallery UI changes.
- No Rhino UI-thread work.
- No provider calls.
- No live Veo or fal generation.
- No provider-payload ingestion.
- No installer/package changes.
- No committed ffmpeg binaries.
- No production ffmpeg packaging decision.
- No GH NLE work.

## Dependency And Licensing Constraints

This slice does not package ffmpeg.

If ffmpeg is selected for production, later packaging work must use an external `ffmpeg.exe` that is replaceable by a user or administrator. The design target is a redistributable LGPL ffmpeg build, not a GPL or nonfree build.

The official FFmpeg legal page states that FFmpeg is LGPL 2.1-or-later by default, while optional GPL parts make the GPL apply to all of FFmpeg if used. Its LGPL checklist also calls out building without `--enable-gpl` and without `--enable-nonfree`.

Reference: https://www.ffmpeg.org/legal.html

This is an engineering constraint, not legal advice. Production packaging must revisit license notices and source-compliance requirements before shipping ffmpeg.

## Error Handling Expectations

The spike should classify these cases:

- ffmpeg path not configured and not found on `PATH`;
- configured ffmpeg path does not exist;
- configured path exists but is not executable;
- ffmpeg exits nonzero;
- output image is missing despite zero exit;
- output image exists but has invalid dimensions;
- input MP4 is missing, locked, empty, or corrupt;
- extraction exceeds a bounded timeout.

For production, sidecar extraction failures should not make the original video generation fail. That production behavior is not implemented in this slice, but the spike should preserve the design assumption.

## Acceptance Criteria

- A local MP4 can be tested without any provider call.
- The implementation plan chooses an explicit fixture policy before adding any binary fixture.
- ffmpeg discovery behavior is designed and tested separately from extraction behavior.
- The spike records command/API shape, exit code or exception, diagnostics, output path, dimensions, and elapsed time.
- A committed spike findings document records the input used, environment, final command/API shape, measurements, failure observations, and production-path recommendation.
- No hardcoded developer-machine ffmpeg path is introduced.
- No ffmpeg binary is committed.
- No installer/package behavior changes.
- No `ArtifactStore` or `VideoJobManager` production integration is added.
- The results recommend one production extraction path or clearly state why no path is ready.
- If ffmpeg is recommended, the recommendation includes external-process invocation, replaceability, LGPL-build target, and deferred packaging/license-compliance work.

## Senior Reviewer Focus

The reviewer should evaluate whether this spike gives enough evidence to choose the extraction path without accidentally becoming production integration.

Key review questions:

- Does the spec keep local MP4 extraction as the default sidecar producer?
- Does it test binary discovery independently from extraction?
- Does it avoid committing or packaging ffmpeg?
- Does it avoid `ArtifactStore`, `VideoJobManager`, provider, and installer work?
- Does it record enough diagnostics to make WMF vs ffmpeg reviewable?
- Does the ffmpeg licensing/packaging note avoid treating a dev-machine binary as a shippable dependency?

## Follow-Up After This Slice

If the spike selects ffmpeg or another extraction path, the next slice is sidecar publication semantics:

- decide append vs atomic multi-blob publish vs reconcile/backfill service;
- define manifest/index update behavior;
- define failure behavior and observability;
- only then integrate poster production for completed videos.

Provider/model payload audit remains optional and parallel. It is useful only for display-poster optimization and must not be used for frame-exact chaining unless a future reviewed provider contract explicitly proves frame semantics.

## Self-Review

Contradiction check:

- The spec says ffmpeg is the primary spike candidate, but explicitly keeps packaging and committed binaries out of scope. That is intentional.
- The spec asks to compare WMF if practical, but does not block Slice 1 on a full WMF implementation. That keeps the risky dependency decision evidence-based without expanding scope into a second implementation.
- The spec extracts one poster candidate frame only, while requiring the selected path to plausibly support `start_frame` and `end_frame` later. That is consistent with a tooling spike.

Scope check:

- The slice is small enough for one implementation plan: write spike harness/tests, run local extraction, document results, and recommend a path.
- Production sidecar publication and video-job integration are explicitly deferred.

Ambiguity check:

- Binary discovery has three explicit cases: configured path, `PATH`, and missing binary.
- Provider audit is optional/parallel, not a blocker.
- ffmpeg legal handling is deferred to packaging, but the design target is explicitly an LGPL, replaceable external binary.
