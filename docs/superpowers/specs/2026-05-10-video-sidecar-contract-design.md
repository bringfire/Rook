# RookVision Video Sidecar Contract Design

Date: 2026-05-10

Status: approved design, pre-implementation planning

## Purpose

RookVision generated-video artifacts need a clean path toward thumbnail previews and future Grasshopper video chaining. The current shipped code already has most of the right contract shape:

- `generated_video` artifacts are persisted in `ArtifactStore`.
- `ArtifactStore` supports multiple `files[]` entries per artifact.
- `VideoMediaRoles` already defines `video`, `poster`, `start_frame`, and `end_frame`.
- Gallery already prefers `poster` for generated-video display when that role exists.
- Video submit already accepts media references shaped as `{ kind: "artifact_id", artifact_id, role }`.

The missing piece is production and consumption discipline. Completed video jobs currently publish only the `video` blob. This slice locks the semantics of optional sidecar roles before any provider-poster ingestion or frame extraction work lands.

## Load-Bearing Semantics

The sidecar roles are not interchangeable.

- `video` is the generated clip payload.
- `poster` is display-only thumbnail metadata for Gallery and preview surfaces.
- `start_frame` is a frame-exact reusable media input representing the generated clip's opening frame.
- `end_frame` is a frame-exact reusable media input representing the generated clip's terminal frame.

`poster` must not be used as a video-chaining input. Provider posters may be representative, cropped, provider-selected, or otherwise not frame-exact. If a future workflow lets a user derive a reusable input from a poster-like image, it must create or select a distinct frame-eligible role or image artifact. The `poster` role itself remains picker-ineligible.

## Selected Slice

This slice is Option A: substrate-first.

It makes the RookVision UI and tests honor the sidecar contract before adding any code that creates new video sidecars. Newly generated videos may still lack thumbnails after this slice. That is acceptable: the success criterion is that later thumbnail/frame producers cannot accidentally undermine the future NLE contract.

## Scope

### 1. Pin Role Semantics

Add source/test coverage and documentation around the role contract:

- `poster` is display-only.
- `start_frame` and `end_frame` are reusable frame inputs.
- `poster` is never picker-eligible as a generated-video frame input.
- `video` is never picker-eligible as a frame input.

### 2. Role-Level Picker Eligibility

Generated-video picker eligibility is role-level, not artifact-level.

The video frame picker must not make an entire `generated_video` artifact selectable with an inferred or default role. It must consider each file role independently:

- `generated_video` with `video` only: no picker choices.
- `generated_video` with `video` + `poster`: no picker choices.
- `generated_video` with `video` + `start_frame`: one picker choice for `start_frame`.
- `generated_video` with `video` + `end_frame`: one picker choice for `end_frame`.
- `generated_video` with `video` + `start_frame` + `end_frame`: two picker choices, one for each frame role.

Each picker choice emits the existing wire shape:

```json
{
  "kind": "artifact_id",
  "artifact_id": "<uuid>",
  "role": "start_frame"
}
```

or:

```json
{
  "kind": "artifact_id",
  "artifact_id": "<uuid>",
  "role": "end_frame"
}
```

The picker must not infer frame input from `poster`, `video`, file extension, artifact kind, or display role fallback.

### 3. Pin Gallery Behavior

Gallery remains a display surface:

- Generated-video tiles prefer `poster` when present.
- If `poster` is absent, Gallery keeps the current graceful fallback behavior.
- Gallery must not eagerly preload MP4s.
- Modal playback continues to use the playback role selected by the existing video display logic, not the poster role.

### 4. Add Audit-Ready Provider Payload Procedure

This slice prepares for provider-payload evidence but does not run live generations.

Add a documented audit procedure for capturing sanitized provider completion/result payloads. The procedure must include:

- How to run one Veo and one fal capture later as an explicit, cost-approved verification task.
- Which provider lifecycle responses should be captured.
- Where sanitized fixtures or findings should be recorded.
- How the findings feed the next decision: provider-poster ingestion if a trustworthy display asset exists, or extraction if frame-exact sidecars must be derived from MP4.

The procedure must include redaction rules:

- No API keys.
- No signed URLs.
- No provider-private queue/status/result/cancel tokens.
- No local filesystem paths.
- No raw video or image bytes.
- No sensitive prompts.
- No account, project, bucket, or tenant identifiers that are not needed for structural analysis.

Add placeholder sanitized fixtures or sample payload-shape examples that show how findings should be represented without implying real provider support.

### 5. Pin Unknown-Field Non-Inference

Add tests proving that unknown provider payload fields do not imply `poster`, `start_frame`, or `end_frame`.

Until an audited provider response is reviewed and a producer is explicitly implemented, provider payload fields are inert. The system must not infer sidecar roles from names such as `thumbnail`, `preview`, `image`, `frame`, `firstFrame`, `lastFrame`, `posterUrl`, or other plausible-looking fields without a deliberate provider-specific mapping.

## Out Of Scope

- No live Veo or fal generations.
- No provider-poster ingestion.
- No MP4 frame extraction.
- No ffmpeg or Windows Media Foundation dependency decision.
- No `ArtifactStore` append API.
- No backend ledger schema changes.
- No persistence of submitted input frames as generated-video `poster` sidecars.
- No copying I2V/interp source images into output artifacts.
- No generated-video sidecar production in `VideoJobManager`.
- No Grasshopper `.gha` plugin work.
- No `VideoClip` or `VideoFrame` token implementation.
- No NLE cache, timeline, trim, stitch, or render sink work.

## Acceptance Criteria

- Existing video jobs still publish only `video`.
- Gallery still displays `poster` when present and remains graceful when absent.
- Gallery does not introduce eager MP4 preload.
- Role-bearing generated-video test fixtures are selectable as frame inputs only through `start_frame` and `end_frame`.
- A generated-video artifact with `poster` + `video` remains picker-ineligible.
- A generated-video artifact with `video` + `start_frame` exposes only `start_frame`.
- A generated-video artifact with `video` + `end_frame` exposes only `end_frame`.
- A generated-video artifact with `video` + `start_frame` + `end_frame` exposes separate role-level choices, not a whole-artifact default choice.
- Picker output for generated-video frame roles uses `{ kind: "artifact_id", artifact_id, role }`.
- Tests assert `poster` is not picker-eligible.
- Tests assert `video` is not picker-eligible.
- Tests assert unknown provider payload fields do not create or imply sidecar roles.
- Audit docs include redaction rules and an explicit cost-gated follow-up checklist for live provider captures.

## Senior Reviewer Focus

The reviewer should evaluate whether this slice preserves the distinction between display thumbnails and reusable frame inputs.

Key review questions:

- Is `poster` kept display-only everywhere?
- Is generated-video picker eligibility role-level rather than artifact-level?
- Are `video` and `poster` excluded from frame-input paths?
- Does the picker emit explicit role refs without fallback inference?
- Does Gallery stay display-oriented and avoid eager MP4 preload?
- Does the audit procedure avoid live-provider cost and credential assumptions?
- Do unknown provider payload fields remain inert until a provider-specific mapping is explicitly implemented?

## Follow-Up Decision After This Slice

The next gated decision is not part of this slice.

After the audit harness/procedure lands, a separate cost-approved verification task should run one Veo and one fal generation, capture sanitized completion/result payloads, and update the findings.

Then choose:

- Provider-poster ingestion, if a provider returns a trustworthy display-only poster/thumbnail asset.
- Extraction, if providers do not return a trustworthy poster or if frame-exact `start_frame` / `end_frame` sidecars are needed.

Provider-poster ingestion may improve Gallery thumbnails but does not solve video chaining. Frame-exact chaining still requires `start_frame` and `end_frame` sidecars from a provider-supported frame output or deterministic extraction.

## Self-Review

Contradiction check:

- The design says existing video jobs still publish only `video`, and all production of `poster`, `start_frame`, or `end_frame` is out of scope. That is consistent with the substrate-first goal.
- The design allows role-bearing generated-video fixtures for picker tests while disallowing new production code. That is not a contradiction: fixtures can represent future or hand-authored artifacts to pin consumption behavior.
- The design keeps Gallery `poster` display separate from picker frame roles. No path treats `poster` as a reusable input.

Role ambiguity check:

- Picker eligibility is explicitly role-level, not artifact-level.
- `video` is playback media only and is not picker-eligible.
- `poster` is display media only and is not picker-eligible.
- `start_frame` and `end_frame` are the only generated-video roles that can become frame picker choices.
- Unknown provider fields remain inert until a future provider-specific mapping is designed and reviewed.

Scope creep check:

- The live provider audit is deferred to a separate cost-approved task.
- Media extraction, dependency selection, provider contract extension, ledger changes, and GH NLE work are all explicitly excluded.
