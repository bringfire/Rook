# RookVision Video Thumbnail and Frame Sidecar Roadmap

Last updated: 2026-05-11

## Purpose

This roadmap tracks the slices required to get from the current generated-video artifact contract to full RookVision video thumbnail support and future Grasshopper video chaining.

Full support means:

- Generated videos show reliable Gallery thumbnails.
- Generated videos can carry frame-exact `start_frame` and `end_frame` sidecars.
- `poster` remains display-only and is never used as a frame input.
- Provider payload evidence and extraction decisions are made explicitly, not inferred from plausible field names.
- Later Grasshopper NLE work consumes stable artifact roles rather than inventing a parallel media model.

## Current State

The substrate-first sidecar contract is complete and merged to `main`.

Done:

- `poster`, `start_frame`, `end_frame`, and `video` semantics are documented.
- Generated-video picker eligibility is role-level.
- `poster` and `video` are excluded from frame-picker input paths.
- Unknown provider payload fields are inert.
- The provider payload audit procedure and sanitized placeholder fixtures exist.

Current next slice:

- Run the live provider payload audit as an explicitly cost-approved verification task.

## Slice Tracker

| Slice | Status | Goal | Exit Criteria |
| --- | --- | --- | --- |
| 0. Sidecar contract substrate | Done | Lock role semantics and role-level picker consumption before producing sidecars. | `poster` stays display-only; `start_frame` / `end_frame` are the only generated-video picker roles; provider fields are not inferred. |
| 1. Provider payload audit | Next | Run one approved Veo job and one approved fal job, sanitize payloads, and record evidence. | Findings state whether either provider returns a trustworthy display poster and whether any provider output can supply frame-exact sidecars. |
| 2. Producer strategy decision | Pending | Choose provider-poster ingestion, MP4 extraction, or both. | A reviewed decision names which roles each producer may create and which roles remain extraction-only. |
| 3. Extraction tooling design | Pending | Select and design the frame extraction mechanism. | Windows Media Foundation, ffmpeg, or another path is chosen with packaging, licensing, failure, and threading implications documented. |
| 4. ArtifactStore sidecar append API | Pending | Add a safe way to attach new role files to an existing generated-video artifact. | Appends are atomic, manifest/index updates are recoverable, and role collisions are deterministic. |
| 5. Poster thumbnail producer | Pending | Produce `poster` for completed generated videos. | New completed videos show Gallery thumbnails without eager MP4 preload; `poster` remains picker-ineligible. |
| 6. Frame-exact sidecar producer | Pending | Produce `start_frame` and `end_frame` for completed generated videos. | Generated videos expose distinct role-level picker choices for frame sidecars; extracted frames are not confused with posters. |
| 7. Existing-video reconcile/backfill | Pending | Populate missing sidecars for older video artifacts when possible. | Reconcile is idempotent, bounded, observable, and does not rerun provider jobs. |
| 8. Grasshopper NLE integration | Pending | Introduce `VideoClip` / `VideoFrame` token behavior and chaining workflows. | GH NLE components consume artifact ids and explicit roles; no whole-artifact default frame inference is introduced. |

## Sequencing Rules

- Do not implement provider-poster ingestion before Slice 1 produces evidence and Slice 2 approves the mapping.
- Do not implement MP4 extraction before Slice 3 chooses the tooling path.
- Do not produce sidecars in `VideoJobManager` until Slice 4 defines the append semantics.
- Do not treat `poster` as a frame source in any slice.
- Do not start GH NLE token work until generated-video `start_frame` and `end_frame` production exists or a deliberate fixture-only spike is approved.

## References

- `docs/superpowers/specs/2026-05-10-video-sidecar-contract-design.md`
- `docs/superpowers/plans/2026-05-10-video-sidecar-contract.md`
- `docs/rook_docs/video-provider-payload-audit.md`
- `docs/rook_docs/2026-04-08-sa-banana-integration.md`
