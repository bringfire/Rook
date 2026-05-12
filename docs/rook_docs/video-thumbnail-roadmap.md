# RookVision Video Thumbnail and Frame Sidecar Roadmap

Last updated: 2026-05-12

## Purpose

This roadmap tracks the slices required to get from the current generated-video artifact contract to full RookVision video thumbnail support and future Grasshopper video chaining.

Full support means:

- Generated videos show reliable Gallery thumbnails.
- Generated videos can carry frame-exact `start_frame` and `end_frame` sidecars.
- `poster` remains display-only and is never used as a frame input.
- Local extraction is the default producer for thumbnails and frame sidecars; provider payloads are optional display optimizations, not the foundation.
- Later Grasshopper NLE work consumes stable artifact roles rather than inventing a parallel media model.

## Current State

The substrate-first sidecar contract, local MP4 extraction tooling spike, and sidecar publication semantics are complete and merged to `main`.

Done:

- `poster`, `start_frame`, `end_frame`, and `video` semantics are documented.
- Generated-video picker eligibility is role-level.
- `poster` and `video` are excluded from frame-picker input paths.
- Unknown provider payload fields are inert.
- The provider payload audit procedure and sanitized placeholder fixtures exist.
- The local MP4 extraction spike proved `ffmpeg.exe` can extract a poster candidate from an existing generated-video MP4 as a replaceable external process.
- Spike findings are recorded in `docs/rook_docs/video-extraction-spike-findings.md`.
- `ArtifactStore.AppendBlob(...)` provides atomic append-style artifact blob publication.
- `VideoSidecarPublisher` provides generated-video sidecar policy for `poster`, `start_frame`, and `end_frame`.
- Duplicate sidecar roles are idempotent skips at the video layer, while storage remains strict append-only.
- New completed generated videos attempt frame-exact `start_frame` and `end_frame` sidecars from the saved local MP4.
- `start_frame` is decoded primary-video-stream frame index 0.
- `end_frame` is the final decodable primary-video-stream frame.
- Frame sidecar extraction is best-effort and non-fatal; partial role publication is allowed.
- Frame sidecars are produced separately from the display-only `poster` path.
- Startup performs one bounded, asynchronous best-effort pass over older eligible generated-video artifacts to populate missing `poster`, `start_frame`, and `end_frame` sidecars from local MP4 files.
- The startup backfill pass is capped, observable, non-fatal, guarded once per process once scheduling succeeds, and never reruns provider jobs or infers provider payloads.

Current next slice:

- Choose the next reviewed video-media slice. Open candidates are provider/model payload audit for optional display-poster ingestion, ffmpeg packaging/licensing, or Grasshopper NLE token behavior. Do not combine them.

## Slice Tracker

| Slice | Status | Goal | Exit Criteria |
| --- | --- | --- | --- |
| 0. Sidecar contract substrate | Done | Lock role semantics and role-level picker consumption before producing sidecars. | `poster` stays display-only; `start_frame` / `end_frame` are the only generated-video picker roles; provider fields are not inferred. |
| 1. Extraction tooling design + spike | Done | Decide whether Rook should use Windows Media Foundation, ffmpeg, or another local decoder path by proving one local MP4 poster extraction. | `ffmpeg.exe` external-process extraction produced a 1920x1080 poster candidate from a local generated-video MP4; no artifacts, providers, installer packaging, or production integrations were changed; findings recommend ffmpeg as the production extraction path candidate. |
| 2. Sidecar publication semantics | Done | Define how sidecar files are published: append to an existing artifact, atomic multi-blob creation at initial publish, a reconcile/backfill service, or a combination. | Publication is atomic, manifest/index updates are recoverable, role collisions are deterministic, and both new-video production and existing-video backfill have a supported path. |
| 3. Poster thumbnail producer | Done | Produce display-only `poster` from the local MP4 for completed generated videos. | New completed videos show Gallery thumbnails without eager MP4 preload; video generation still succeeds if poster extraction fails; `poster` remains picker-ineligible. |
| 4. Frame-exact sidecar producer | Done | Produce `start_frame` and `end_frame` from the local MP4 for completed generated videos. | Newly completed generated videos attempt both boundary frame sidecars; `start_frame` is decoded frame index 0; `end_frame` is the final decodable frame; partial failure is non-fatal; extracted frames are not confused with posters. |
| 5. Existing-video reconcile/backfill | Done | Populate missing sidecars for older video artifacts from local MP4 files when possible. | Startup schedules one bounded asynchronous best-effort pass over eligible generated-video artifacts; only missing roles are attempted; role failures are diagnostic-only; provider jobs are never rerun. |
| 6. Provider/model payload audit | Optional/Parallel | Audit provider/model-specific payloads only for opportunistic display-poster ingestion. | Findings are scoped only to the audited provider/model response shape; no provider payload is used for frame-exact chaining unless a future reviewed contract explicitly proves frame semantics. |
| 7. Grasshopper NLE integration | Pending | Introduce `VideoClip` / `VideoFrame` token behavior and chaining workflows. | GH NLE components consume artifact ids and explicit roles; no whole-artifact default frame inference is introduced. |

## Sequencing Rules

- Treat local MP4 extraction as the default producer for `poster`, `start_frame`, and `end_frame`.
- Do not implement production extraction before Slice 1 chooses the tooling path from spike evidence.
- Production sidecar writes must go through `VideoSidecarPublisher`; do not introduce a parallel storage path.
- Do not implement provider-poster ingestion without provider/model-specific evidence and an approved exact mapping.
- Do not treat `poster` as a frame source in any slice.
- Do not start GH NLE token work until generated-video `start_frame` and `end_frame` production exists or a deliberate fixture-only spike is approved.

## References

- `docs/superpowers/specs/2026-05-10-video-sidecar-contract-design.md`
- `docs/superpowers/plans/2026-05-10-video-sidecar-contract.md`
- `docs/superpowers/specs/2026-05-11-local-mp4-extraction-tooling-spike-design.md`
- `docs/superpowers/plans/2026-05-11-local-mp4-extraction-tooling-spike.md`
- `docs/superpowers/specs/2026-05-12-video-frame-sidecar-producer-design.md`
- `docs/superpowers/plans/2026-05-12-video-frame-sidecar-producer.md`
- `docs/superpowers/specs/2026-05-12-video-sidecar-backfill-design.md`
- `docs/superpowers/plans/2026-05-12-video-sidecar-backfill.md`
- `docs/rook_docs/video-extraction-spike-findings.md`
- `docs/rook_docs/video-provider-payload-audit.md`
- `docs/rook_docs/2026-04-08-sa-banana-integration.md`
