# Slice 4 Video Frame Sidecar Producer Design

Date: 2026-05-12

## Context

RookVision generated-video artifacts now have the substrate needed for video
thumbnails and future video chaining:

- `poster`, `start_frame`, `end_frame`, and `video` role semantics are
  documented.
- `poster` is display-only and picker-ineligible.
- Generated-video frame picker eligibility is role-level and limited to
  `start_frame` and `end_frame`.
- Unknown provider payload fields are inert.
- Local MP4 extraction is the default producer path for video derivatives.
- `ArtifactStore.AppendBlob(...)` owns atomic append-style sidecar writes.
- `VideoSidecarPublisher` owns generated-video sidecar publication policy.
- Slice 3 produces display-only `poster` sidecars from the saved local MP4 as
  best-effort derivative work after durable video artifact creation.

Slice 4 produces frame-exact `start_frame` and `end_frame` sidecars for newly
completed generated videos. These roles describe temporal boundaries of the
produced video, not the original request's input shape. Therefore every newly
completed generated video should attempt both roles, regardless of whether the
request was T2V, I2V, interpolation, or another mode.

## Decision

Add a reusable frame-exact local MP4 extraction primitive and a narrow generated
video sidecar producer.

The extractor contract is frame-based:

```csharp
VideoFrameSelector.First
VideoFrameSelector.Last
VideoFrameSelector.FrameIndex(long index)
```

Frame indices are zero-based decoded frames from the primary video stream.
`First` means decoded frame index `0`. `Last` means the final decodable frame of
the primary video stream. `FrameIndex(index)` means the decoded frame at the
given zero-based index, and negative indices are invalid before invoking
`ffmpeg`.

Timestamp selectors are out of scope for Slice 4. The Slice 3 poster timestamp
seek remains valid for display thumbnails, but it is not valid for reusable
frame inputs.

The frame extractor is intentionally reusable for future Grasshopper NLE
arbitrary-frame work, but Slice 4 does not expose or implement any GH-facing API,
token behavior, component behavior, route, or MCP surface.

## Architecture

Add two focused managed video services.

### `VideoFrameExtractor`

`VideoFrameExtractor` extracts one JPEG frame from an already-local MP4 path to
a caller-provided temp output path. It accepts a resolved `ffmpeg.exe` path from
its caller; it does not own production ffmpeg discovery for sidecar generation.

It owns:

- frame selector validation;
- `ffmpeg.exe` command construction for frame-exact selectors;
- defensive validation of the resolved executable path;
- process execution and timeout handling;
- output-image validation;
- role-agnostic extraction result codes and bounded diagnostics.

It does not know about:

- artifacts;
- video jobs;
- sidecar roles;
- production ffmpeg resolution policy;
- Gallery;
- providers;
- Grasshopper.

`First` can normalize internally to `FrameIndex(0)`. `Last` remains its own
selector and strategy. The API says `Last`, not "duration minus epsilon" and not
"reverse filter." The ffmpeg implementation can choose a reliable strategy
behind the seam.

For Slice 4, the expected implementation strategy is:

- `First` / `FrameIndex(n)`: select decoded frame index `n` from the primary
  video stream and write exactly one JPEG.
- `Last`: use an internal ffmpeg strategy that returns the final decodable frame
  without exposing that strategy as API.

If `Last` uses a reverse-filter strategy, the design accepts that it may decode
or buffer more of the clip. That is acceptable for short generated-video clips
in Slice 4. If a future implementation changes to frame counting, it must not
quietly introduce a new `ffprobe` packaging assumption without its own reviewed
slice.

### `VideoFrameSidecarProducer`

`VideoFrameSidecarProducer` owns artifact-aware frame sidecar publication.

It:

- resolves the saved generated-video artifact's `video` blob path;
- resolves `ffmpeg.exe` once for the derivative attempt;
- creates one temp output path per role;
- calls the extractor for `VideoFrameSelector.First` and
  `VideoFrameSelector.Last`;
- maps `First` to `VideoMediaRoles.StartFrame`;
- maps `Last` to `VideoMediaRoles.EndFrame`;
- reads each extracted JPEG;
- publishes each sidecar independently through `VideoSidecarPublisher`;
- deletes temp files best-effort;
- returns per-role results instead of throwing for expected failures.

Attempt order is deterministic:

1. `start_frame` from `VideoFrameSelector.First`
2. `end_frame` from `VideoFrameSelector.Last`

Duplicate `start_frame` must not prevent attempting `end_frame`, and duplicate
`end_frame` must not change the already-completed `start_frame` result.

`VideoPosterSidecarProducer` remains poster-shaped and display-oriented. Slice 4
does not merge poster and frame sidecar production into a generic derivative
pipeline.

## Finalization Flow

`VideoJobManager` keeps the durable success boundary introduced in Slice 3.

The generated-video finalization sequence is:

1. Materialize provider MP4 bytes.
2. Create the durable `generated_video` artifact with the `video` blob.
3. Run best-effort derivative producers after artifact creation:
   `poster`, `start_frame`, and `end_frame`.
4. Append terminal `Complete` with the generated-video artifact id.

Whether poster runs before frame sidecars or after them is less important than
the boundary: all derivative work runs after durable MP4 artifact creation and
before the terminal `Complete` record.

`ArtifactStore.Create(kind: "generated_video", blobs: video)` remains the
durable success boundary. Once that call succeeds, derivative extraction,
publication, cleanup, missing ffmpeg, invalid output, timeout, unexpected
producer exception, and derivative-stage cancellation must not convert the saved
video job into `Error` or `Cancelled`.

## Results And Errors

Extractor results are role-agnostic. Expected result codes should include:

- `Succeeded`
- `FfmpegMissing`
- `TimedOut`
- `ExtractionFailed`
- `InvalidOutput`
- `Cancelled`

The extractor can include bounded diagnostics such as selector, command, exit
code, elapsed time, and a truncated stderr excerpt. It must not mention
`start_frame` or `end_frame`.

Producer results are role-specific. The sidecar producer converts extractor,
byte-read, publish, temp-path, cleanup, and unexpected exception outcomes into
per-role results. Expected result codes should distinguish at least:

- published;
- duplicate already exists;
- ffmpeg missing;
- extraction timeout;
- extraction failure;
- invalid output;
- local video blob unavailable;
- temp path unavailable;
- extracted bytes unreadable;
- publish failure;
- cleanup failure as diagnostic-only;
- cancelled during derivative work after artifact creation;
- unexpected failure.

The combined producer result is non-throwing for expected failures. Partial
success is valid:

- If first succeeds and last fails, publish only `start_frame`.
- If first fails and last succeeds, publish only `end_frame`.
- If both fail, publish neither and still allow the saved video job to complete.
- If a one-frame video makes `First` and `Last` resolve to the same visual
  frame, both roles should still publish as distinct sidecars when both
  extractions succeed.

If `ffmpeg.exe` is missing, the producer should short-circuit extraction after a
single resolver check while still reporting per-role `FfmpegMissing` results for
both `start_frame` and `end_frame`.

The extractor can still return `FfmpegMissing` when it is called directly with
an absent or invalid executable path. That defensive result supports extractor
tests and future direct reuse without moving production sidecar ffmpeg discovery
out of `VideoFrameSidecarProducer`.

## Cancellation Contract

Cancellation before durable artifact creation keeps existing job behavior and
can still stop submit, polling, fetch, or materialization.

Cancellation observed during derivative work after artifact creation means
"cancelled while producing sidecars for an already-saved video." It is reported
as per-role derivative failure and does not escape into `VideoJobManager`'s
outer cancellation handling.

The manager should not pass a cancellation token that can still abort the whole
finalization helper after the `video` artifact exists unless that cancellation
is deliberately caught and converted inside the derivative producer.

## Gallery And Picker Behavior

No Gallery rewrite is required for Slice 4.

Existing generated-video picker behavior should continue to be role-level:

- `start_frame` is picker-eligible.
- `end_frame` is picker-eligible.
- `poster` remains display-only and picker-ineligible.
- `video` remains picker-ineligible.

Generated-video tiles still use `poster` for display thumbnails when present.
The new frame sidecars are reusable media inputs, not display posters.

## Test Plan

Extractor tests should prove selector semantics and command intent without
overfitting to full command strings unless the existing ffmpeg wrapper pattern
already asserts full argv.

Extractor tests should cover:

- `VideoFrameSelector.FrameIndex(-1)` is rejected before invoking ffmpeg.
- `First` normalizes to frame index `0`.
- `FrameIndex(n)` targets zero-based decoded frame index `n`.
- `Last` uses the chosen internal last-frame strategy while preserving the
  selector contract.
- missing input MP4 returns failure;
- missing ffmpeg returns `FfmpegMissing`;
- timeout returns `TimedOut`;
- process failure returns `ExtractionFailed`;
- success without output image returns failure;
- corrupt or unreadable output image returns `InvalidOutput`;
- zero-frame or undecodable video returns failure, not a bogus end frame;
- diagnostics are bounded.

Producer tests should not invoke real ffmpeg. They should use fake extractor,
resolver, temp-file, byte-reader, and publisher seams.

Producer tests should cover:

- successful extraction publishes `start_frame` then `end_frame`;
- each role uses its own temp output path;
- publication goes only through `VideoSidecarPublisher`;
- duplicate `start_frame` does not prevent attempting `end_frame`;
- duplicate `end_frame` does not alter a successful `start_frame`;
- first succeeds / last fails publishes only `start_frame`;
- first fails / last succeeds publishes only `end_frame`;
- missing ffmpeg reports per-role `FfmpegMissing` without invoking extraction;
- temp path failure for one role does not prevent the other role;
- byte-read failure for one role does not prevent the other role;
- publish failure for one role does not prevent the other role;
- cancellation during derivative work becomes per-role failure;
- unexpected exception during one role becomes per-role failure and does not
  prevent attempting the other role;
- cleanup failure is diagnostic-only and does not override successful publish or
  duplicate skip;
- one-frame video behavior can publish both distinct roles when both
  extractions succeed.

Manager tests should inject a fake frame sidecar producer and remain process
free. They should cover:

- completed video finalization attempts frame sidecars after durable video
  artifact creation and before terminal `Complete`;
- partial frame sidecar failure still completes the job;
- total frame sidecar failure still completes the job;
- derivative-stage cancellation after artifact creation does not append
  `Cancelled`;
- both polled completion and synchronous completion paths share the same
  finalization behavior.

Existing source-level UI tests should continue to pin Gallery poster display and
generated-video frame picker role eligibility.

No live Rhino test is required for this slice.

## Out Of Scope

- Existing-video reconcile/backfill.
- Provider payload frame or poster mappings.
- Provider payload inference from fields named `thumbnail`, `preview`,
  `image`, `frame`, `firstFrame`, `lastFrame`, `posterUrl`, or similar.
- Installer ffmpeg packaging, notices, LGPL/source-compliance work, or shippable
  binary decisions.
- Grasshopper NLE tokens, components, routes, or UI.
- Timestamp-based extraction selectors.
- Generic derivative media pipeline.
- New native, public HTTP, MCP, or Grasshopper surfaces.
