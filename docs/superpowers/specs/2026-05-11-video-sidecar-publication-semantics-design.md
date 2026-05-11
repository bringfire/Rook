# Video Sidecar Publication Semantics Design

Date: 2026-05-11

Status: draft design for review

## Purpose

RookVision now has two completed prerequisites for video thumbnails and future video chaining:

- The generated-video sidecar role contract is locked: `poster` is display-only, while `start_frame` and `end_frame` are frame-exact reusable inputs.
- The local MP4 extraction spike proved that a replaceable external `ffmpeg.exe` can extract a poster candidate from an existing generated-video MP4.

The next risk is publication. Rook needs a safe way to add sidecar blobs to an existing generated-video artifact after the primary `video` blob has already been published.

This matters because video generation should remain successful once the MP4 is stored. Thumbnail or frame extraction can fail later without turning a completed video job into a failed video job. Existing-video backfill also cannot use create-time multi-blob publication, so the storage primitive must support appending sidecars to existing artifacts.

## Primary Principle

Sidecar publication uses an append-style primitive.

`ArtifactStore.Create(...)` already supports multiple blobs at initial artifact creation, but production video sidecars should not depend on all blobs being ready before the `generated_video` artifact exists. New-video sidecars and future backfill should both use the same append primitive.

The load-bearing invariant is:

Never publish a manifest entry before the referenced blob exists at its final path.

An orphan sidecar file without a manifest entry is acceptable and ignored by readers. A manifest entry pointing to a missing blob is not acceptable.

## Selected Slice

Slice 2 designs the sidecar publication semantics only.

It defines:

- a generic `ArtifactStore.AppendBlob(...)` storage primitive;
- a video-specific sidecar policy wrapper, named here as `VideoSidecarPublisher`;
- result codes and failure behavior;
- atomicity and crash-recovery rules;
- tests and acceptance criteria for implementation planning.

This slice does not run extraction in production and does not wire sidecar publication into `VideoJobManager`.

## Architecture

### 1. Generic Storage Primitive

`ArtifactStore.AppendBlob(...)` is a generic artifact-file operation. It should not know RookVision video role semantics.

Conceptual shape:

```csharp
AppendBlob(
    Guid artifactId,
    string role,
    byte[] content,
    string fileExtension)
```

Storage-level responsibilities:

- validate the artifact exists;
- load and validate the current manifest;
- validate the blob role string using the same storage role rules as `Create(...)`;
- validate the file extension using the same storage extension rules as `Create(...)`;
- reject duplicate roles already present in the manifest;
- reject final-file collisions even if the manifest does not mention the role;
- stage the blob before manifest mutation;
- publish the final blob before manifest mutation;
- update `manifest.json` using the existing `File.Replace(...)` style;
- return structured results for expected publication failures.

The storage layer treats `role` only as a blob role string. It does not know whether `poster`, `start_frame`, or `end_frame` are video sidecars.

Per-sidecar metadata and provenance are deferred. The current artifact manifest file entry model is `role + path`, so Slice 2 does not add file-level metadata, source labels, or provenance fields.

### 2. Video Policy Wrapper

`VideoSidecarPublisher` is the video-domain wrapper around `ArtifactStore.AppendBlob(...)`.

It validates video-specific policy:

- target artifact must exist;
- target artifact must have `kind == "generated_video"`;
- allowed roles are exactly:
  - `VideoMediaRoles.Poster`
  - `VideoMediaRoles.StartFrame`
  - `VideoMediaRoles.EndFrame`
- `VideoMediaRoles.Video`, `VideoMediaRoles.Image`, and arbitrary roles are rejected;
- `poster` remains display-only;
- `start_frame` and `end_frame` remain frame-exact reusable inputs;
- duplicate storage roles are translated to an idempotent domain-level skip result.

This wrapper is the first production-facing abstraction for both future new-video sidecars and future existing-video backfill.

## Atomicity And Recovery

`AppendBlob(...)` should follow the existing store posture:

- `Create(...)` hides unfinished artifacts in `.tmp` directories.
- `SetFlag(...)` writes a temp manifest and swaps it with `File.Replace(...)`.

Proposed append sequence:

1. Resolve the finalized artifact directory for `artifactId`.
2. Load and validate `manifest.json`.
3. Reject if `role` already exists in the manifest.
4. Compute the deterministic final filename from role and extension, for example `poster.jpg`.
5. Reject if that final filename already exists on disk but is not present in the manifest.
6. Write the blob to a collision-resistant staged filename inside the artifact directory, for example `poster.<guid>.jpg.tmp`.
7. Move the staged blob to the final filename with overwrite disabled.
8. Build an updated manifest that includes the new role/path entry.
9. Write `manifest.json.tmp`.
10. Atomically replace `manifest.json` with `File.Replace(...)`.

Observable recovery behavior:

- If artifact lookup or manifest load fails, no writes happen.
- If role validation or extension validation fails, no writes happen.
- If a duplicate role is found in the manifest, no writes happen.
- If final-file collision is found, no writes happen.
- If staged write fails, the manifest remains unchanged.
- If staged-to-final move fails, the manifest remains unchanged.
- If manifest replacement fails, the original manifest remains valid and does not reference the new blob. The final blob may remain as an orphan file.
- After success, the manifest references a blob that exists at the referenced path.
- Readers continue to trust only manifest entries, not loose files.

This recovery posture prefers ignored orphan files over broken manifest references.

## Result Model

### ArtifactStore Append Result

`ArtifactStore.AppendBlob(...)` should return a structured result for expected outcomes. It should not collapse all expected failures into a single ambiguous failure.

Recommended storage result codes:

- `Succeeded`
- `ArtifactNotFound`
- `ManifestReadFailed`
- `InvalidRole`
- `InvalidExtension`
- `DuplicateRole`
- `FinalFileCollision`
- `StagedWriteFailed`
- `FinalizeBlobFailed`
- `ManifestReplaceFailed`

The implementation plan may choose exact type names, but the result must preserve this level of signal.

Unexpected exceptions may still bubble or be wrapped in an implementation-specific failure if that better matches the surrounding `ArtifactStore` pattern.

### Video Sidecar Publisher Result

`VideoSidecarPublisher` should expose video-domain outcomes:

- `Succeeded`
- `SkippedAlreadyExists`
- `RejectedUnsupportedRole`
- `RejectedWrongArtifactKind`
- `ArtifactNotFound`
- `StorageFailed`

Storage `DuplicateRole` maps to `SkippedAlreadyExists`. For extraction and backfill workflows, an existing sidecar is an idempotent skip, not an operational failure.

Other storage failures map to `StorageFailed` unless they have a clearer domain outcome.

## Duplicate And Replacement Policy

Slice 2 is strict append only.

If a role already exists in the manifest:

- `ArtifactStore.AppendBlob(...)` returns `DuplicateRole`;
- no blob or manifest write occurs;
- no replacement is attempted.

If the final role filename exists on disk but the manifest does not reference the role:

- `ArtifactStore.AppendBlob(...)` returns `FinalFileCollision`;
- the loose file is not overwritten;
- the manifest remains unchanged.

There is no `replace: true` flag, no delete/remove sidecar path, and no repair API in Slice 2.

Future replacement should be a separate API with explicit audit/provenance semantics, likely including old-blob handling and reason metadata.

## Future Consumer Behavior

### New Video Sidecars

Future production wiring should create the `generated_video` artifact with the `video` blob first. After that succeeds, sidecar extraction and publication may run.

If sidecar publication fails after the video artifact exists:

- video generation remains successful;
- the video job must not be converted to `Error`;
- the failure may be logged or reported as sidecar publication skipped/failed;
- Gallery and picker behavior continue to depend on manifest roles that actually exist.

This spec does not decide the exact future UI or job-status surface for sidecar publication diagnostics.

### Existing Video Backfill

Future backfill should use `VideoSidecarPublisher`, not a separate storage path.

Backfill should be idempotent:

- missing roles can be appended;
- existing roles are skipped;
- no roles are overwritten;
- provider jobs are not rerun.

Backfill execution is out of scope for Slice 2.

## Out Of Scope

- No production ffmpeg invocation.
- No `VideoJobManager` integration.
- No generated-video sidecar production.
- No backfill/reconcile execution.
- No Gallery thumbnail UI changes.
- No picker behavior changes.
- No installer or ffmpeg packaging changes.
- No provider-poster ingestion.
- No provider calls.
- No sidecar replacement.
- No sidecar deletion.
- No manifest index redesign.
- No cross-process locking.
- No GH NLE token/component work.

## Testing Expectations

Storage tests should pin:

- successful append persists a new manifest role and writes the blob;
- after success, the manifest references a blob that exists;
- duplicate role returns `DuplicateRole` and leaves manifest/files unchanged;
- invalid role and invalid extension reject before writes;
- missing artifact returns `ArtifactNotFound`;
- corrupt manifest returns `ManifestReadFailed` and writes nothing;
- final file collision returns `FinalFileCollision` and does not overwrite;
- simulated manifest replace failure leaves the original manifest valid and does not reference the new blob;
- loose files are ignored by readers unless present in the manifest.

Video wrapper tests should pin:

- `poster`, `start_frame`, and `end_frame` are accepted for `generated_video`;
- `video`, `image`, and arbitrary roles are rejected;
- non-`generated_video` artifacts are rejected;
- storage `DuplicateRole` maps to `SkippedAlreadyExists`;
- wrapper policy does not call extraction, providers, `VideoJobManager`, Gallery, picker, or GH NLE code.

## Acceptance Criteria

- The spec defines `ArtifactStore.AppendBlob(...)` semantics clearly enough for implementation planning.
- The spec defines video sidecar policy and result mapping clearly enough for implementation planning.
- The append contract is strict: no replacement, no deletion, no silent overwrite.
- The observable atomicity contract is clear: failed manifest replacement leaves the original manifest valid and not referencing the new blob; successful publication references an existing blob.
- The design supports future new-video sidecars and future existing-video backfill through the same primitive.
- Video completion remains independent from sidecar publication.
- The design does not introduce production extraction, UI thumbnails, provider ingestion, installer packaging, or GH NLE work.

## Senior Reviewer Focus

The reviewer should evaluate whether this slice provides the correct storage primitive without prematurely wiring production behavior.

Key review questions:

- Is `ArtifactStore.AppendBlob(...)` generic enough to avoid video-domain leakage?
- Does `VideoSidecarPublisher` carry the video-specific policy instead?
- Does the atomicity sequence avoid manifest entries that point at missing blobs?
- Are duplicate roles strict at the storage layer and idempotent at the video wrapper?
- Are final-file collisions handled without overwriting loose files?
- Does the design keep completed video jobs independent from sidecar publication failures?
- Is backfill supported by the same primitive without implementing backfill now?
- Are replacement, deletion, extraction, UI, provider, installer, and GH NLE work clearly out of scope?

## Follow-Up After This Slice

After Slice 2 is implemented, the next roadmap slice is poster thumbnail production:

- run local MP4 extraction after a completed video artifact exists;
- append `poster` through `VideoSidecarPublisher`;
- keep sidecar failures non-fatal to video jobs;
- keep `poster` picker-ineligible.

Frame-exact `start_frame` and `end_frame` production should follow after poster publication proves the append path in production.

## Self-Review

Contradiction check:

- The design selects append-style publication even though `ArtifactStore.Create(...)` already supports multi-blob creation. That is intentional because new-video sidecar production and existing-video backfill should share the same primitive.
- The storage layer rejects duplicate roles as a failure, while the video wrapper can treat duplicates as skipped. That is not a contradiction; it separates storage facts from domain idempotency.
- The spec allows an orphan blob after manifest replace failure, but readers ignore loose files. That is consistent with the invariant that only manifest entries are published.

Scope check:

- The slice is small enough for one implementation plan: add the append storage primitive, add the video wrapper, and pin tests.
- Production extraction, job integration, UI thumbnails, backfill execution, provider ingestion, installer work, replacement, deletion, and GH NLE are all excluded.

Ambiguity check:

- Allowed video sidecar roles are explicit.
- Duplicate-role behavior is explicit and strict.
- Final-file collision behavior is explicit and non-overwriting.
- The atomicity contract is stated in observable terms rather than relying on unobservable timing.
