# Slice 3 Video Poster Sidecar Producer Design

Date: 2026-05-12

## Context

RookVision generated-video artifacts currently persist the MP4 as a
`generated_video` artifact with a `video` blob. Gallery already prefers a
`poster` blob for video tiles when one exists, and the generated-video frame
picker already excludes `poster` and `video` from frame-input choices.

The completed roadmap substrate is:

- `poster`, `start_frame`, and `end_frame` role semantics are defined.
- `poster` is display-only and picker-ineligible.
- `FfmpegPosterFrameExtractor` can extract a JPEG poster candidate from a
  local MP4 by invoking a replaceable external `ffmpeg.exe`.
- `ArtifactStore.AppendBlob(...)` owns atomic append-style sidecar writes.
- `VideoSidecarPublisher` owns generated-video sidecar policy and treats
  duplicate sidecar roles as idempotent skips.

Slice 3 adds production poster creation for newly completed generated videos.
It does not add frame-exact sidecars, existing-video backfill, provider-payload
poster ingestion, installer packaging changes, public/native routes, MCP
surface area, or Grasshopper NLE token work.

## Decision

Poster creation runs synchronously in the generated-video save/finalization
path before the job appends its `Complete` transition, but it is strictly
best-effort after the MP4 artifact exists.

`ArtifactStore.Create(kind: "generated_video", blobs: video)` is the durable
success boundary. Once that call succeeds, the video job must complete with the
artifact id. Poster extraction, publication failure, timeout, missing ffmpeg,
invalid output, duplicate poster, post-artifact local I/O failure, unexpected
producer failure, and cancellation observed during poster work must not convert
that paid/saved video into `Error` or `Cancelled`.

This avoids a fire-and-forget background race while keeping `Complete` meaning
"the video artifact was successfully saved," not "all derivative sidecars were
created."

## Architecture

Add a small managed video-subsystem service named
`VideoPosterSidecarProducer`.

Responsibilities:

- Resolve the final MP4 path with
  `ArtifactStore.GetBlobAbsolutePath(artifact.Id, VideoMediaRoles.Video)`.
- Resolve `ffmpeg.exe` through a testable resolver seam backed by
  `FfmpegBinaryResolver`.
- Extract one JPEG poster using a testable extraction seam backed by
  `FfmpegPosterFrameExtractor`.
- Write extraction output only to a temp path, never directly to the artifact
  directory.
- Publish poster bytes only through
  `VideoSidecarPublisher.Publish(artifact.Id, VideoMediaRoles.Poster, bytes,
  "jpg")`.
- Delete the temp poster file best-effort after success or failure.
- Return a typed result object instead of throwing into job finalization.
- Catch post-artifact local I/O failures and unexpected producer exceptions,
  converting them to typed results with bounded diagnostics.

`VideoJobManager` should extract shared generated-video finalization logic used
by both completion paths:

1. The polled provider completion path in `RunJobAsync`.
2. The synchronous result path in `CompleteSyncSubmitAsync`.

The shared helper performs:

1. Materialized MP4 bytes -> `ArtifactStore.Create(...)`.
2. Best-effort poster sidecar production.
3. Append `Complete` with the generated-video artifact id.

This keeps both paths from drifting on cancellation, poster, and terminal-state
semantics.

## Cancellation Contract

Cancellation before artifact creation keeps the existing behavior and can still
stop submit, polling, fetch, or materialization.

After the generated-video artifact exists, poster production may observe
cancellation, timeout, local I/O failure, unexpected producer failure, or
extraction/publish errors, but it must convert those outcomes into warnings or
no-op results and return control so `VideoJobManager` appends `Complete`.

Implementation can satisfy this either by using a non-job-cancelling token for
poster work after artifact creation or by catching `OperationCanceledException`
inside the poster finalizer. The important contract is that poster-stage
cancellation after artifact creation must not escape to `VideoJobManager`'s
outer cancellation catch.

## Result Codes

Use a boring, testable result type named `VideoPosterSidecarResult`, with these
codes:

- `Published`
- `SkippedAlreadyExists`
- `SkippedFfmpegMissing`
- `TimedOut`
- `ExtractionFailed`
- `InvalidOutput`
- `PublishFailed`
- `VideoBlobUnavailable`
- `TempPathUnavailable`
- `PosterReadFailed`
- `FinalizerFailed`
- `CancelledAfterArtifactCreated`

`SkippedAlreadyExists` is idempotent success/no-op, not a warning. Other
non-published outcomes are warnings for diagnostics, but they are not durable
video job failures.

`VideoBlobUnavailable` covers inability to resolve or access the final saved
`video` blob through `ArtifactStore.GetBlobAbsolutePath(...)`.
`TempPathUnavailable` covers failure to create or reserve the poster temp output
path. `PosterReadFailed` covers failure to read extracted poster bytes before
publication. `FinalizerFailed` is the catch-all for any unexpected producer
exception after artifact creation. Cleanup exceptions are swallowed and captured
as bounded diagnostic warnings; they must not replace a successful
`Published`/`SkippedAlreadyExists` primary result or escape to the manager.

Diagnostics must be bounded. The result can include a short message, an error
code, and truncated stderr, but it must not retain unbounded ffmpeg output.

## Gallery And Picker Behavior

No Gallery rewrite is required for this slice. Existing JavaScript already:

- displays `/blob/{artifact_id}/poster` for generated-video tiles when a
  `poster` role exists;
- falls back to a non-preloading video tile when no poster exists;
- excludes `poster` and `video` from generated-video frame-picker choices.

Slice 3 should preserve those behaviors with narrow source-level tests if
nearby coverage exists. It should not introduce a completed-video state that
requires Gallery to wait for a background poster task.

## Test Plan

`VideoPosterSidecarProducer` unit tests should not invoke real ffmpeg. Provide
seams for:

- ffmpeg resolution;
- extraction;
- temp path creation;
- sidecar publication.

Reserve real ffmpeg coverage for the existing extraction tests and manual spike.

Producer tests should cover:

- successful extraction publishes `poster.jpg` through `VideoSidecarPublisher`;
- duplicate poster returns `SkippedAlreadyExists` as idempotent no-op;
- missing ffmpeg returns `SkippedFfmpegMissing`;
- timeout returns `TimedOut`;
- extraction process failure returns `ExtractionFailed`;
- invalid image output returns `InvalidOutput`;
- sidecar publish failure returns `PublishFailed`;
- final video blob resolution/access failure returns `VideoBlobUnavailable`;
- temp output path failure returns `TempPathUnavailable`;
- poster byte read failure returns `PosterReadFailed`;
- unexpected producer exception returns `FinalizerFailed`;
- cleanup failure is swallowed with bounded diagnostics and does not override a
  successful publish/idempotent primary result;
- cancellation during poster work after artifact creation returns
  `CancelledAfterArtifactCreated`;
- temp output cleanup is attempted after success and failure;
- stderr/diagnostics are truncated.

`VideoJobManager` tests should inject a fake poster finalizer so they remain
deterministic and process-free. Manager tests should cover:

- when poster production succeeds, completed video finalization writes both
  `video` and `poster` before the final `Complete` record is visible;
- poster failure still completes the job with a valid generated-video artifact
  id and only the `video` blob;
- duplicate poster/no-op still completes the job;
- cancellation before artifact creation still behaves normally;
- poster-stage `OperationCanceledException` or cancelled result after artifact
  creation does not append `Cancelled` and does not prevent `Complete`;
- both `RunJobAsync` and `CompleteSyncSubmitAsync` use the same finalization
  behavior.

No live Rhino test is required for this slice.

## Out Of Scope

- Producing `start_frame` or `end_frame`.
- Backfilling old generated-video artifacts.
- Provider/model payload poster ingestion.
- ffmpeg installer packaging, notices, LGPL/source-compliance work.
- New native, public HTTP, MCP, or Grasshopper surfaces.
- Durable ledger schema changes for poster warnings.
