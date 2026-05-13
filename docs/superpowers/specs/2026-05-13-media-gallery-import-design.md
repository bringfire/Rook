# RookVision Media Gallery Import Design

Date: 2026-05-13

## Context

RookVision currently has no durable path for adding local user media to the
Gallery as reusable source material. Existing Gallery and picker flows are
artifact-oriented:

- Gallery lists generated image and video artifacts and renders blobs through
  `/blob/{artifact_id}/{role}`.
- The video picker already consumes artifact roles, including generated-video
  `start_frame` and `end_frame` sidecars.
- The video generation backend already has an artifact-only media resolver.

The new feature should be durable media ingestion, not direct Gallery references
to arbitrary local files. Local media should enter RookVision through import,
become normal `ArtifactStore` artifacts, and then be selected by Gallery,
pickers, and generation paths through artifact refs.

## Decision

Add an artifact-backed async media import job system to the managed RookVision
stack.

The Gallery tab gets an `Add Media to Gallery` button. The button invokes a
managed UI op that opens an Eto multi-select picker, creates an import job
inside C#, and returns only job-safe UI state. Full selected paths stay inside
the managed import subsystem.

Imported media uses first-class artifact kinds:

- `imported_image`
- `imported_video`

Do not reuse `generated_image` or `generated_video`; those names encode
provenance and should remain provider-output kinds.

The central invariant is:

> `ArtifactStore` contains only complete imported artifacts; failed imports live
> only as import job item results.

V1 import generates only the existing `ArtifactStore` `manifest.json` plus
technical metadata. Semantic manifests, captions, tags, prompt suggestions, and
other model-generated enrichment are future work and are not part of import
correctness.

## Architecture

The import subsystem lives in `src/Rook` with the managed RookVision UI and
service stack. It is bridge-only in v1 and is not added to native HTTP or MCP
public allowlists.

New bridge-only ops:

- `start_media_import`: UI-routed. Opens the picker, validates selection count,
  creates a job, and returns a job summary without full paths.
- `get_media_import_job`: off-UI status polling by `job_id`.
- `list_media_import_jobs`: off-UI recent-job recovery for panel reloads.

No cancel op is included in v1. The internal state model may reserve
cancel-related states for a later slice, but the v1 UI does not expose
cancellation.

`start_media_import` returns a shape like:

```json
{
  "job_id": "...",
  "files": [
    { "import_item_id": "...", "basename": "clip.mp4", "status": "queued" }
  ]
}
```

If the user cancels or selects nothing, no job is created and the response is
neutral, for example:

```json
{ "created": false, "reason": "empty_selection" }
```

Selecting more than 20 files is a start-level validation error
(`too_many_files`) and creates no job. The 20-file cap is enforced server-side,
not only in UI code.

Core managed components:

- `MediaImportOpHandler`: validates op payloads and shapes bridge responses.
- `MediaImportJobManager`: owns job state, bounded queue, per-file transaction
  orchestration, recent-job listing, and v1 concurrency policy.
- `MediaImportProcessor`: runs one selected file as an isolated transaction and
  publishes either one complete artifact or a failure result.
- Image/video importer helpers: validate, probe/decode, prepare staged files,
  and return technical metadata. They do not publish partial artifacts.

Import jobs are local and deterministic. They do not call AI providers. Images
also use the async path so the UI has one behavior for all media. Video
processing concurrency is `1` in v1.

Recent job state is bounded in memory. Active and completed jobs stay available
for polling, tab switches, and panel reloads during the current plugin session,
up to an implementation-defined count cap. When the cap is exceeded, oldest
terminal jobs are dropped first. Published artifacts remain durable in
`ArtifactStore`.

## Artifact Publishing

Media import requires a staged, file-backed artifact creation path. Existing
`ArtifactStore.Create` accepts `byte[]` blobs, which is not suitable for large
user-selected videos.

Add a file-backed publish API, such as `CreateFromFiles` / `BlobFileInput`, or
an equivalent import-specific staging flow. The publishing path must preserve
current artifact store guarantees:

- stage files in a temp artifact directory;
- use flat role-derived blob filenames;
- write `manifest.json`;
- atomically publish the finalized artifact directory;
- remove the temp directory on failure;
- never publish an incomplete import artifact.

Large source media is copied as files into the artifact temp directory. It is
not read fully into managed memory, and the user's original local file is never
moved or deleted by import. Only Rook-controlled temporary sidecar files may be
moved within Rook staging directories.

Blob filenames remain role-derived:

- `image.png`
- `image.jpg`
- `image.webp`
- `video.mp4`
- `video.mov`
- `video.webm`
- `poster.jpg`
- `start_frame.jpg`
- `end_frame.jpg`

Original filenames are preserved only in metadata. They are not used as artifact
blob filenames.

## Artifact Kinds And Roles

`imported_image` publishes:

- `image`: copied original image, or a normalized image only if a later design
  explicitly chooses normalization.

`imported_video` publishes:

- `video`: copied original video, used for Gallery playback and reveal.
- `poster`: display-only Gallery thumbnail.
- `start_frame`: picker-selectable source role.
- `end_frame`: picker-selectable source role.

For v1, all four imported-video roles are required. If poster, start frame, or
end frame extraction fails, that file import fails and no `imported_video`
artifact is published. The end frame means the last decodable primary stream
frame found by the extractor, not necessarily a timestamp exactly equal to
container duration.

## Metadata

V1 metadata is technical only.

Common metadata:

- `imported: true`
- `import_source: "local_file"`
- `original_filename`
- `original_extension`
- `mime_type`
- `byte_size`
- `imported_at`

Do not include full source paths in routine artifact metadata, UI state, or
job logs. `source_path_hash` is omitted in v1 unless a later explicit decision
enables it; even derived local path data should be treated as privacy-sensitive.

Image metadata:

- `width`
- `height`
- `pixel_format` when reliable
- `normalized: false`

Video metadata:

- `duration_seconds`
- `width`
- `height`
- `frame_rate` when reliable
- `poster_timestamp_seconds`
- `start_frame_timestamp_seconds`
- `end_frame_timestamp_seconds`
- `sidecars: { "poster": "ok", "start_frame": "ok", "end_frame": "ok" }`

`pixel_format` and `frame_rate` are best-effort metadata. Missing values do not
block publication when required dimensions, duration, and sidecars succeed.

## Supported Formats And Limits

V1 supported image formats:

- `png`
- `jpg`
- `jpeg`
- `webp`

`bmp` is not included in the baseline v1 format matrix. It can be added in a
later slice after decode and downstream provider behavior are explicitly tested.

V1 supported video formats:

- `mp4`
- `mov`
- `webm`

Reject `gif`, `tiff`, `heic`, `heif`, `svg`, raw camera formats, PDFs, and all
other formats in v1.

Extension allowlists are only the first gate. Images require successful decode
or probe. Videos require accepted extension plus successful FFmpeg probe and
sidecar extraction.

V1 also defines explicit per-file size caps for images and videos. Exact limits
are selected during implementation, but they must be enforced before copy/probe
where possible. Oversized files fail as `file_too_large`.

Each selected item must exist, be accessible, and be a regular file. Missing
files, directories, and inaccessible files fail before decode, probe, or copy.

## UI And Picker Contract

Gallery is the import doorway. Add `Add Media to Gallery` to the Gallery
toolbar. Gallery empty copy should mention generated and imported media.

The import status UI shows per-file rows with:

- basename;
- status;
- stable failure code when failed;
- concise message;
- artifact link or open action when published.

The panel should survive tab switches and panel reloads by calling
`list_media_import_jobs`. Gallery refreshes incrementally as each artifact
publishes. Imported and generated artifacts sort together by `created_at`, with
the existing deterministic tie-breaker.

Gallery lists these kinds explicitly:

- `generated_image`
- `generated_video`
- `imported_image`
- `imported_video`

Gallery modals should display provenance clearly through the artifact kind.

Video picker behavior:

- `imported_image` is a direct image source choice.
- `imported_video.start_frame` and `imported_video.end_frame` are selectable
  frame inputs.
- `imported_video.poster` is display-only.
- `imported_video.video` is playback/reveal only.

Studio/image source behavior:

- New UI source selection uses artifact refs.
- A convenience `Load Image` flow may remain, but internally it imports first
  and then selects the resulting `imported_image`.
- Image generation needs explicit artifact-ref request support, either through
  new image-side source/reference fields or by extending its parser to accept
  the same artifact-ref shape used by video. The UI migrates to those fields and
  stops sending `input_image_path` / `reference_image_paths` for newly selected
  Gallery media.
- Direct local path generation, if still needed by backend compatibility code,
  is non-UI legacy. New RookVision UI paths must not form generation requests
  from arbitrary local paths.

## Generation And Lineage Contract

Generation consumes artifact-backed media refs, using the existing backend
`MediaRef` parser shape. The exact discriminator should match the current
parser contract, for example:

```json
{ "kind": "artifact_id", "artifact_id": "...", "role": "image" }
```

or:

```json
{ "kind": "artifact_id", "artifact_id": "...", "role": "start_frame" }
```

If provider payload construction still requires a filesystem path internally,
the server resolves it through `ArtifactStore.GetBlobAbsolutePath`. JS does not
pass arbitrary local paths to generation.

Generated outputs should record imported source artifact IDs in `parent_ids`
where the current generation path already supports lineage. This makes imported
source material auditable rather than only visually selectable.

## Error Handling

Start-level outcomes:

- `empty_selection`: neutral no-job response.
- `too_many_files`: validation error, no job created.

Per-file failure codes:

- `unsupported_media_type`
- `file_not_found`
- `not_regular_file`
- `file_inaccessible`
- `file_too_large`
- `decode_failed`
- `video_probe_failed`
- `sidecar_extraction_failed`
- `copy_failed`
- `publish_failed`

`publish_failed` means an internal storage or artifact publication failure after
validation or processing. UI copy should not imply the user media was invalid in
that case.

Full selected paths stay inside the managed import subsystem. They should not
be returned to JS or written to routine UI/job logs. UI-facing state uses
basenames.

## Testing

Focused automated tests should cover:

- ArtifactStore file-backed creation: flat role-derived filenames, atomic
  publish, cleanup on failure, no full-video byte load path.
- Import manager: bounded batch behavior, independent per-file transactions,
  too-many-files rejection, neutral empty selection, recent-job listing, bounded
  retention, and video concurrency `1`.
- Image import: supported/rejected extensions, decode failure, regular-file
  validation, metadata shape, artifact kind and role.
- Video import with fake FFmpeg/prober/extractor: required sidecars, failure
  before publish, metadata shape, and stable failure codes.
- Bridge routing: import ops are bridge-only and absent from native/MCP v1
  public allowlists.
- UI source behavior: Gallery includes imported kinds; picker includes imported
  image and imported-video sidecar roles; new UI generation paths use artifact
  refs.
- Lineage: generated outputs record imported source artifact IDs as parents
  wherever the generation path already supports parent IDs.

Manual smoke tests after implementation:

- Import multiple images and videos and observe incremental per-file status.
- Switch tabs or reload the panel mid-import and confirm status recovery.
- Confirm imported artifacts appear mixed with generated artifacts by
  `created_at`.
- Use an imported image as an image source.
- Use imported video `start_frame` and `end_frame` as video frame inputs.
- Delete and reveal imported artifacts from Gallery.

## Out Of Scope

- Semantic manifests, captions, tags, prompt generation, or model calls during
  import.
- Native HTTP or MCP public import endpoints.
- Path-referenced Gallery entries.
- Partial imported-video artifacts with missing required sidecars.
- Timeline-style sampled frame browsing.
- GIF animation semantics.
- Deduplication by content hash or source path.
