# Rook Mesh2Splat Export Pipeline Design

Date: 2026-06-29

## Context

We verified the local companion repositories:

- `C:/Users/aryan/source/repos/mesh2splat` uses `bringfire/mesh2splat` as `origin`; GitHub reports it as a fork of `electronicarts/mesh2splat`.
- `C:/Users/aryan/source/repos/ve_engine` uses `bringfire/ve_engine` as `origin`; GitHub reports it as a fork of `vercidium-patreon/ve`.

The first Rhino test document, `H:/AI EXPERIMENTS/Pearson/mesh2splat_test.3dm`, contains one 1m mesh cube with UVs. Direct Rhino GLB export preserved geometry attributes but did not reliably preserve the checker/PBR texture. A Rook-generated GLB from the saved `.3dm` mesh embedded the checker bitmap as PNG and converted successfully through `mesh2splat`.

Observed `mesh2splat` behavior:

- Headless CLI input is binary `.glb`.
- Output `.ply` succeeds with `compressed-pbr` and `standard`.
- At `--resolution 1024`, the cube produces `6,291,456` splats.
- `standard` output is about 1.56 GB for this cube because it includes full SH fields.
- `compressed-pbr` output is about 302 MB and is the better default for early capture/display loops.
- The CLI currently writes exactly one JSON object to stdout on success/failure, with logs on stderr. The first implementation should preserve tolerant parsing in case future builds emit extra stdout lines.
- The GUI already has a sampling-density path: `effectiveResolution = minRes + quality * (maxRes - minRes)`, with `minRes = 16`. With GUI default `quality = 0.5` and `maxRes = 1024`, effective resolution is about `520`.
- The current headless CLI bypasses GUI density and directly uses `opts.resolution`.
- The conversion shader emits one splat per rasterized fragment until the hard cap is reached. Sampling resolution is therefore the primary splat-count lever; PLY format primarily changes bytes per splat.

## Goal

Build a deterministic Rook-owned first-slice capture pipeline for selected, small Rhino mesh exports. The tool converts supported selected mesh geometry and materials into a strict mesh2splat-compatible GLB, runs the headless `Mesh2Splat` CLI, validates the resulting PLY, and records all artifacts for display or downstream use.

The reliable contract must not depend on Rhino's built-in GLB exporter preserving materials correctly.

## Non-Goals

- Do not replace `mesh2splat` conversion logic inside Rook.
- Do not implement a full splat renderer in RookNative.
- Do not require Rhino's built-in GLB exporter for the core pipeline.
- Do not support arbitrary Rhino procedural materials in the first implementation slice.
- Do not move Grasshopper or managed companion responsibilities across the current Rook architecture boundary.
- Do not add new external dependencies.

## Authority Rule

Each requirement has exactly one source-of-truth section. Later sections may reference that requirement by section name, but must not restate it with different wording or extra conditions.

- **Contract Invariants and Happy Path** owns operation ordering, first-slice scope, request option enumeration, and large-output policy.
- **Native Capture Contract** owns Rhino UI-thread capture, selection semantics, Rhino mesh/material metadata extraction, and native-owned caps.
- **Python GLB/Process Pipeline Contract** owns GLB writing, unit conversion, texture byte conversion, `mesh2splat` invocation, stdout/stderr parsing, and PLY byte parsing.
- **Filesystem/Artifact/Process Safety Contract** owns filesystem mutation, cleanup, executable trust and lookup, child environment policy, working-directory trust, texture path trust, texture caps, and artifact provenance.
- **Validation and Error Matrix** owns GLB/PLY validator rules and failure-code mapping.
- **Test Plan and Acceptance Criteria** owns verification coverage.

## Contract Invariants and Happy Path

First-slice scope:

- Input is selected Rhino mesh objects or explicit `object_ids`.
- Output is a strict GLB and a `compressed-pbr` or `standard` PLY.
- Default conversion format is `compressed-pbr`. The default `samplingResolution` must be chosen only after the live sizing matrix below; until then, implementation planning should assume a provisional `samplingResolution: 256`.
- Valid first-slice `samplingResolution` range is integer `16..4096`. Any other value fails request validation with `invalid_request`.
- `samplingResolution > 512` or `format: standard` requires `allowLargeOutput: true`, otherwise fail with `large_output_requires_opt_in`.
- `format: pbr` remains a later-slice format until its PLY property layout and stride are pinned by tests.
- `Mesh2Splat` currently accepts only `1024`, `2048`, and `4096` through headless `--resolution`. The next `bringfire/mesh2splat` fork prerequisite is stronger than adding `512`: expose canonical deterministic headless `--sampling-resolution <int>` over `16..4096`, keep legacy `--resolution` compatibility only if needed, and report the effective sampling resolution in JSON. `--effective-resolution` is not a first-slice CLI flag.
- `compressed-pbr` is the first-slice storage/transport default because it is materially smaller than `standard`. Preview/display depends on a matching compressed-PBR loader path; otherwise first-slice display must request `format: standard` with `allowLargeOutput: true`.

Request options in the first slice:

- `outputDirectory`
- `format`
- `samplingResolution`
- `unitsMode`
- `allowLargeOutput`
- `allowNetworkTextures`
- `preserveDebugArtifacts`
- `object_ids`
- `allowPartial`
- `mesh2splatPath`
- `mesh2splatWorkingDirectory`
- `mesh2splatTimeoutSeconds`

Hard ordering invariants:

- Request validation and executable resolution happen before native capture.
- No run directory, GLB, PLY, or artifact registration is created when request validation, executable resolution, or native capture fails.
- Native capture owns Rhino API access and pre-serialization mesh-size caps only.
- Python orchestration owns texture file-size checks, decoded-image caps, post-expansion GLB caps, PNG conversion, GLB writing, process execution, PLY validation, cleanup, and artifact registration.
- Explicit `object_ids` are strict by default. Current-selection mode may skip unsupported selections with warnings.
- Output-size prediction is not deterministic before `mesh2splat` runs. First-slice pre-run guards include format/sampling-resolution opt-in policy and a conservative capacity estimate; actual byte validation happens after conversion.
- Pre-run output-size checks are conservative capacity reports, not promises. They fail before launching `mesh2splat` only when configured policy caps or future Mesh2Splat limits make the estimate exceed policy; post-run PLY byte validation remains authoritative.

Happy path sequence:

1. Validate request shape and all first-slice request options.
2. Enforce sampling resolution, format, and large-output policy.
3. Resolve `Mesh2Splat.exe` using the executable lookup rules in **Filesystem/Artifact/Process Safety Contract**.
4. Call the RookNative capture route on the Rhino UI thread.
5. Native filters requested/selected objects, extracts source mesh/material metadata, enforces native caps, and returns the JSON-safe payload.
6. Create the requested `outputDirectory` if needed, create a unique run output directory under it, initialize a run manifest, and choose output names.
7. Python validates captured texture paths and texture caps before image conversion.
8. Python expands vertices across position/normal/UV/material seams, converts units, converts supported source images to embedded PNG bytes, enforces post-expansion GLB caps, and writes the strict GLB.
9. Validate the GLB.
10. Register the GLB artifact.
11. Run `mesh2splat` with an argv list, `shell=False`, sanitized child environment, requested `samplingResolution`, captured stdout/stderr, timeout, and known-output tracking.
12. Parse tolerant stdout JSON and validate the PLY.
13. Register the PLY artifact.
14. Return run directory, output names, paths, artifact ids, source units, counts, output-size estimate metadata, actual bytes, warnings, and CLI metadata.

## Native Capture Contract

Boundary:

- RookNative performs all Rhino document access on the Rhino UI thread using existing main-thread dispatch patterns.
- Python calls a native capture route and receives a JSON-safe payload. Python does not call Rhino SDK APIs directly.
- The native route captures mesh/material source data only; it does not write GLB, read texture files, run `mesh2splat`, register artifacts, or mutate the filesystem.

Selection semantics:

- The tool supports explicit `object_ids` and current Rhino selection.
- Explicit ids are strict by default: malformed ids, missing ids, hidden/deleted/reference/locked objects, and unsupported geometry fail with the appropriate native error.
- `allowPartial: true` may skip unsupported explicit ids with warnings, but the result must fail if no supported mesh objects remain.
- Current-selection mode may skip unsupported selected objects with warnings and fails only when no supported meshes remain.

Geometry contract:

- First slice supports mesh objects only.
- Breps, extrusions, SubD, curves, points, and blocks are unsupported unless already represented by selected mesh objects.
- Hidden, deleted, reference, and locked objects are not captured unless a later explicit option changes that behavior.
- Native capture returns world-space source vertices after applying object instance transforms, normals when available, channel-1 UVs and UV-validity metadata when available, faces, object ids, object/material assignment, source material metadata, document units, and transform diagnostics needed for traceability.
- Native capture triangulates quads as two triangles for cap accounting. Ngons are unsupported in the first slice.

Material metadata contract:

- Native capture reports enough material metadata for Python to resolve first-slice base color: classic diffuse color, classic diffuse bitmap path when exposed, render-content/PBR scalar base color when exposed, render-content/PBR base-color bitmap path when exposed, and mapping channel information when exposed.
- Mapping channel support is channel 1 only in the first slice. Non-default channels or texture transforms are reported as warnings and ignored.
- Procedural/noise/checker materials without file-backed bitmaps are not baked in the first slice. They fall back to scalar color with warnings when scalar fallback is available.
- Normal, occlusion, emissive, and metallic-roughness textures are not exported in the first slice. Detected unsupported texture slots warn and are ignored.

Native-owned numeric caps:

| Name | Default | Unit | Formula / measured value | Enforced when |
| --- | ---: | --- | --- | --- |
| `maxObjects` | `8` | selected mesh candidates | Count of candidate Rhino objects before geometry extraction. | Before serializing capture payload. |
| `maxSourceVertices` | `200000` | Rhino mesh vertices | Sum of source mesh vertex counts before glTF seam splitting. | Before serializing capture payload. |
| `maxSourceTriangles` | `300000` | triangles | Sum of triangles after native face conversion, counting triangles as `1` and quads as `2`. | Before serializing capture payload. |
| `maxEstimatedJsonBytes` | `50000000` | bytes | Conservative pre-seam-split estimate: `4096 * objectCount + 2048 * materialCount + 96 * sourceVertexCount + 24 * sourceTriangleCount + totalStringBytes`. It estimates the native JSON payload before Python vertex expansion and must be reported as `estimatedJsonBytes`. | Before serializing full mesh arrays. |

## Python GLB/Process Pipeline Contract

Boundary:

- Python orchestration calls native capture, writes and validates GLB, normalizes/encodes supported texture images, runs `Mesh2Splat.exe`, validates PLY, and registers artifacts.
- The GLB writer and material normalization are Rook-owned. Rhino's built-in GLB exporter is not part of the reliable path.
- There is no existing Rook Python GLB writer. The first implementation must add a focused `glb_writer` unit with tests for GLB chunk framing, JSON padding, 4-byte alignment, bufferViews, accessors, accessor bounds, index width selection, image bufferViews, embedded PNG payloads, and Mesh2Splat parse validation.

GLB writer contract:

- Binary GLB only.
- One scene with one or more nodes/meshes from the selected source meshes.
- Vertex positions are converted by `unitsMode`: `meters` is the default and converts Rhino document units to meters; `raw` preserves Rhino numeric model coordinates.
- The result records `unitsMode`, source document units, `unitScaleToMeters`, and `upAxis: "Z"`.
- Coordinate basis remains Rhino's right-handed Z-up coordinate frame. General glTF orientation compatibility for non-Rook consumers is out of first-slice scope. Any viewer-side conversion must happen after this export contract.
- Faces are triangles. Triangle winding is preserved from Rhino mesh face orientation.
- Python generates normals if missing. Generated normals are per-face unless a stable source vertex normal exists.
- Python splits vertices across position, normal, UV, and material seams so every glTF vertex record has exactly one normal, UV, and material assignment.
- Textured materials require valid channel-1 UVs. If an otherwise supported bitmap material has missing or invalid channel-1 UVs, the first slice must fall back to scalar `baseColorFactor` with a warning and must not emit `baseColorTexture`.
- Scalar-only materials may emit deterministic dummy `TEXCOORD_0` values of `(0, 0)` for every vertex, but only after a Mesh2Splat smoke test proves that scalar-material GLBs with dummy UVs convert successfully. Until that test exists, scalar-only meshes without valid UVs fail GLB validation rather than relying on Mesh2Splat defaults.
- The GLB uses accessors with correct `min`/`max`, 4-byte buffer alignment, valid bufferView ranges, and one binary chunk.
- Material output uses glTF PBR fields: `baseColorTexture` for supported embedded PNG images or `baseColorFactor` for scalar fallback. Metallic defaults to `0`; roughness defaults to `0.5`; opacity is opaque unless source transparency is explicit and exportable.
- Intentional black materials are valid. Black-material warnings are validation-owned and depend on source/export consistency in **Validation and Error Matrix**.

Texture conversion contract:

- Texture path trust and size/decode caps are owned by **Filesystem/Artifact/Process Safety Contract**.
- Supported source image formats are whatever Pillow can read on the machine after the source passes the safety contract.
- All supported first-slice images are converted to embedded PNG bytes to avoid MIME/path ambiguity.
- The first slice emits embedded PNG bytes only. It does not write sidecar baked PNG files and therefore does not return or register texture artifact ids.

Mesh2Splat execution contract:

- Python runs the requested first-slice format and sampling resolution, provisionally defaulting to:

```text
Mesh2Splat --input <capture.glb> --output <capture.ply> --format compressed-pbr --sampling-resolution 256
```

- Executable lookup, trust semantics, working-directory validation, child environment policy, timeout defaults, and process-tree termination are owned by **Filesystem/Artifact/Process Safety Contract**.
- The Mesh2Splat fork may keep `--resolution` as a compatibility alias, but Rook's contract is `samplingResolution` mapped to canonical CLI flag `--sampling-resolution` because it is the deterministic density lever.
- Mesh2Splat JSON must report the effective sampling resolution used for conversion.
- Capacity overflow detection is part of the Mesh2Splat fork prerequisite. Current Mesh2Splat increments the conversion atomic counter before discard and then reads that counter into `numberOfGaussians`; the fork must treat that value as `attemptedGaussianCount`. After conversion and before PLY readback/export, if `attemptedGaussianCount > maxGaussianCapacity`, return parseable JSON with `errorCode: "CAPACITY_EXCEEDED"`, `attemptedGaussianCount`, `maxGaussianCapacity`, and `samplingResolution`, and do not write a PLY.
- Python captures stdout and stderr separately.
- Stdout parsing is tolerant: prefer the last non-empty stdout line that parses as JSON.
- Required forked success schema includes `ok`, `input`, `output`, `format`, `samplingResolution`, `effectiveResolution`, `gaussianCount`, and `durationMs`.
- Return `exitCode`, parsed JSON payload when present, `stderrTail` capped by `stderrTailBytes`, and any CLI `errorCode`.
- Map CLI `GL_CONTEXT_INIT_FAILED` to a user-facing OpenGL context failure that includes `stderrTail`, executable path, and working directory.
- Map CLI `GLB_PARSE_FAILED` or exit code `4` to `mesh2splat_glb_parse_failed`, because it most likely means the Rook GLB writer emitted invalid input.

Python-owned numeric caps:

| Name | Default | Unit | Formula / measured value | Enforced when |
| --- | ---: | --- | --- | --- |
| `maxExpandedVertices` | `1000000` | glTF vertex records | Count after splitting by position, normal, UV, and material assignment. | After seam splitting and before GLB buffer creation. |
| `maxGlbBytes` | `268435456` | bytes | Estimated GLB size after expansion: JSON chunk bytes plus BIN chunk bytes, including 4-byte padding and embedded PNG bytes. | Before writing GLB. |
| `maxEstimatedPlyBytesGuard` | `2147483648`, or `8589934592` with `allowLargeOutput: true` | bytes | Mesh2Splat-grounded estimate before CLI launch: `headerAllowance + min(samplingResolution * samplingResolution * 6 * mesh2splatLoadedMeshCount, mesh2splatMaxGaussians) * formatStride`, where `headerAllowance = 1048576`, `mesh2splatLoadedMeshCount` is the GLB writer's emitted primitive-instance count expected to become `renderContext.dataMeshAndGlMesh.size()`, `mesh2splatMaxGaussians = 7000000` from current `MAX_GAUSSIANS_TO_SORT`, `compressed-pbr formatStride = 48`, and `standard formatStride = 248`. With current Mesh2Splat limits, this is primarily a reported capacity estimate and future-proof guard; it may not reject any first-slice request unless the cap or Mesh2Splat limit changes. | After native capture and before launching `mesh2splat`. |

## Filesystem/Artifact/Process Safety Contract

Output directory and run isolation:

- `outputDirectory` is required in the first slice.
- Request validation for `outputDirectory` is side-effect free. It must not create directories or files during request validation or before executable resolution and native capture both succeed.
- `outputDirectory` must be absolute. Relative paths, shell variables, shell expansions, and path fragments such as `..` that cannot be safely canonicalized are rejected.
- Python resolves/canonicalizes the path before use. For a missing `outputDirectory`, canonicalize the nearest existing parent during validation and defer creating the requested directory until after native capture succeeds. On Windows, canonicalization must account for symlinks/reparse points where the standard library exposes them.
- If the path exists and is a file, fail with `invalid_output_directory`.
- If the path does not exist, create it only as the explicit requested `outputDirectory` after native capture succeeds. Failure to create it is `invalid_output_directory`.
- If Python creates the requested missing `outputDirectory` and later run-directory or manifest creation fails, retain that newly-created `outputDirectory`. Parent output directories are never deleted in the first slice.
- Every run writes into a unique child directory under the resolved `outputDirectory`, named `mesh2splat-YYYYMMDD-HHMMSS-<shortRunId>`. The resolved run directory must remain inside the resolved `outputDirectory`.
- Output filenames inside the run directory are fixed for the first slice: `capture.glb`, `capture.ply`, and `manifest.json`.
- Use exclusive file creation for `manifest.json`, `capture.glb`, and `capture.ply`; alternatively write to exclusive temp files inside the run directory and atomically publish only if the destination is still absent. If a generated path already exists at create/publish time, fail with `invalid_output_directory`.

Cleanup:

- Python records every file it creates in a run manifest before or immediately after creation.
- Cleanup may delete only files listed in the manifest, created by the current run, whose resolved paths are inside the resolved run directory.
- Cleanup must re-resolve each manifest path at cleanup time and verify it is still a regular file inside the resolved run directory before deletion. If a path now resolves outside the run directory, is a directory, or is a symlink/reparse-point swap, cleanup must skip it and report a warning.
- Cleanup must not recursively delete the run directory in the first slice.
- Cleanup must never delete caller-provided input files, source bitmap files, executable files, config files, parent output directories, or files that are not in the manifest.
- `preserveDebugArtifacts: true` keeps generated files but still reports which manifest paths would otherwise have been cleanup candidates.
- `manifest.json` is diagnostic output, not a registered artifact in the first slice. Once the run directory exists, keep `manifest.json` on success and on all failures after run-directory creation. Update it with final status, warnings, selected executable, output names, and cleanup decisions.

Executable lookup and trust:

- Python must not hardcode a developer-local repo path.
- Resolve the executable in this order:
  1. explicit tool parameter `mesh2splatPath`
  2. environment variable `ROOK_MESH2SPLAT_EXE`
  3. mutable Rook Python runtime config `get_mutable_knowledge_root() / "config" / "mesh2splat.json"`
  4. bundled Rook Python runtime config `get_bundled_knowledge_root() / "config" / "mesh2splat.json"`
  5. bundled release install location, when packaging later provides one
  6. `PATH` lookup for `Mesh2Splat.exe`
- Runtime config file shape:

```json
{
  "mesh2splat": {
    "executable": "C:/path/to/Mesh2Splat.exe"
  }
}
```

- Missing, unreadable, or malformed mutable config is diagnostic-only and must not block bundled config fallback. Missing, unreadable, or malformed bundled config is also diagnostic-only.
- Candidate executable paths must resolve/canonicalize and exist as files.
- `mesh2splatPath` is an explicit user-trusted override and may point to an executable whose basename is not `Mesh2Splat.exe`; the selected path and source must be reported.
- Executables from `ROOK_MESH2SPLAT_EXE`, runtime config, bundled location, or `PATH` must have basename `Mesh2Splat.exe` case-insensitively.
- Invalid explicit `mesh2splatPath` fails hard with `invalid_executable`.
- Invalid `ROOK_MESH2SPLAT_EXE`, runtime config, bundled-location, or `PATH` candidates are rejected with diagnostics and lookup continues.
- Return `mesh2splat_not_found` only when lookup exhausts all sources without a valid executable.
- Diagnostics must include the selected executable path, selected source, rejected candidate paths with reasons, working directory, and whether an explicit trusted override was used.

Process execution:

- Launch `mesh2splat` with an argv list and `shell=False`; never compose a command string through a shell.
- Use a sanitized child-process environment by default. It must not inherit the full Rook MCP process environment or secrets such as API keys.
- The first-slice sanitized environment allowlist is `SystemRoot`, `windir`, `TEMP`, and `TMP`.
- Include `PATH` only when the selected executable came from `PATH` lookup or when a later implementation proves it is required for Mesh2Splat runtime DLL loading; if included, report that reason in diagnostics.
- Explicit user-trusted `mesh2splatPath` or `mesh2splatWorkingDirectory` overrides do not automatically allow full environment inheritance. If a future option permits inherited environment, it must be explicit, user-trusted, and reported in diagnostics.
- Default working directory is the executable parent directory.
- `mesh2splatWorkingDirectory` is an explicit user-trusted execution-context override because it can affect DLL search order and relative file behavior. If provided, it must be an absolute existing directory after canonicalization. Shell expansion is not performed. Invalid caller-provided working directories fail with `invalid_working_directory`, and valid overrides must be reported as user-trusted in diagnostics.
- Default timeout is 300 seconds for `compressed-pbr` with `samplingResolution <= 512`, and 900 seconds for `format: standard` or explicitly allowed `samplingResolution > 512`. A positive explicit `mesh2splatTimeoutSeconds` overrides the computed default.
- On timeout, terminate the process tree where possible. On Windows, use a job object or equivalent process-tree termination strategy when available. If only direct-child termination is available, report that limitation in diagnostics before cleanup.
- `stderrTailBytes` is `8192` bytes.

Texture path trust and texture caps:

- Rhino material texture paths are model-controlled input.
- First slice accepts only local filesystem texture paths by default.
- URL schemes such as `http:`, `https:`, `file:`, `ftp:`, and `data:` are rejected as texture sources and should fall back to scalar color with a warning when fallback is available.
- UNC/network paths are skipped with warnings by default and must not be read unless the caller sets `allowNetworkTextures: true`.
- Relative texture paths are not resolved against the process working directory. They are unsupported in the first slice unless Rhino provides a canonical local file path.
- Accepted texture paths must resolve/canonicalize to regular local files. Directories, device paths, missing files, and symlink/reparse targets that resolve to network locations are rejected unless `allowNetworkTextures: true` covers the network target.
- If `allowNetworkTextures: true` is used, treat network texture access as user-trusted and report the resolved network path in warnings/diagnostics.
- Texture path rejection happens before `os.stat`, image decode, or PNG conversion. Rejected fallback-capable texture paths are warnings and do not make `baseColorTexture` expected.
- `maxTextureBytesPerSource` is `67108864` source file bytes, measured by `os.stat(resolvedTexturePath).st_size` before Pillow opens the image.
- `maxTexturePixels` is `16777216` decoded pixels, measured as `width * height` after opening the image header.
- `maxDecodedTextureBytes` is `67108864` decoded bytes, measured as `width * height * channelCount`, where `channelCount` is the converted output channel count, normally `4` for RGBA.
- Pillow must be configured so decompression-bomb warnings/errors fail as `texture_decode_too_large`.
- Missing, unreadable, or unsupported bitmap files fall back to scalar color and emit a validation warning when the source material has a scalar fallback. These fallback-capable cases must not raise `texture_read_failed`.

Artifact registration:

- Python orchestration registers generated GLB and PLY files through `mcp_server/src/rook/artifacts.py`.
- Embedded-only textures do not create separate texture artifacts; the GLB artifact owns embedded texture bytes.
- Preferred implementation is direct `artifact_registry().upsert(...)` so generated artifacts can carry `source: "mesh2splat_capture"`, source Rhino `document_name`, `origin_session_id` when available, and labels `mesh2splat.glb` or `mesh2splat.ply`.
- Before using `mesh2splat_capture` provenance, update artifact registry semantics to add `_SOURCE_RANK["mesh2splat_capture"] = 2`, strictly greater than `_SOURCE_RANK["explicit"] = 1`, because `ArtifactRegistry.upsert()` promotes only on strict rank `>`.
- If mesh2splat-owned reruns need refreshed provenance, deliberately change `ArtifactRegistry.upsert()` so rows whose existing source is also `mesh2splat_capture` replace `document_name`, `origin_session_id`, and `label` instead of relying on the current `COALESCE` backfill behavior.
- If that registry change is not implemented in the same slice, fall back to the public `register_artifact()` helper and explicitly report that provenance is generic.
- Registration failures do not delete generated files. They are returned as explicit warnings with affected paths.

Tool result:

- input Rhino document path and document name
- captured object ids
- `unitsMode`, source document units, `unitScaleToMeters`, and `upAxis: "Z"`
- resolved `outputDirectory`
- run directory
- GLB file name, path, and artifact id
- PLY file name, path, and artifact id
- mesh counts, triangle counts, material counts, emitted primitive-instance count, and `mesh2splatLoadedMeshCount`
- `samplingResolution`, `effectiveResolution`, `estimatedPlyBytes`, `estimateBasis`, `estimateConfidence`, and `actualPlyBytes`
- mesh2splat stdout JSON
- mesh2splat `exitCode`, `errorCode` when present, and `stderrTail` on warnings/failures
- selected executable path, executable source, working directory, and child environment policy summary
- output manifest path
- validation warnings
- artifact registry warnings, if registration fails

## Validation and Error Matrix

GLB validator:

- Exactly one asset JSON chunk and one binary chunk.
- At least one triangle primitive.
- Required accessors for `POSITION`, `NORMAL`, and `TEXCOORD_0`.
- Accessor `min`/`max`, bufferView ranges, and 4-byte alignment are valid.
- Material has either `baseColorTexture` or `baseColorFactor`.
- Embedded image payload exists when a texture is expected.
- A texture is expected only after the source image passes texture-source trust policy, path resolution, source-byte cap, decoded-image caps, and supported-format checks.
- Fallback-capable texture failures before that point require scalar `baseColorFactor` and warning, not `baseColorTexture`.
- If the source material had a non-black scalar color, the GLB must not silently become black. Intentional black materials are valid.

PLY validator:

- CLI exit code is zero.
- Stdout contains a parseable JSON object with `ok: true`.
- Required forked success schema includes `ok`, `input`, `output`, `format`, `samplingResolution`, `effectiveResolution`, `gaussianCount`, and `durationMs`.
- `.ply` exists.
- PLY header starts with `ply`.
- `element vertex` equals `gaussianCount`.
- PLY properties match the selected format validator:
  - `compressed-pbr`: `x y z` floats, `red green blue opacity` uint8, `rot_0..rot_3` floats, `scale_0..scale_2` floats, `octa_nx octa_ny roughness metallic` uint8; 48 bytes per vertex after the header.
  - `standard`: `x y z`, `nx ny nz`, `f_dc_0..2`, `f_rest_0..44`, `opacity`, `scale_0..2`, `rot_0..3`; 62 floats / 248 bytes per vertex after the header.
- File size matches the format-specific stride after the exact header byte length. CRLF/LF variation must be handled by measuring the actual header bytes rather than assuming a fixed header length.
- `estimatedPlyBytes` is a low-confidence pre-run heuristic, not a pass/fail contract. It must include `estimateBasis` and `estimateConfidence`.
- The pre-run `maxEstimatedPlyBytesGuard` follows Mesh2Splat's current conversion capacity model: `min(samplingResolution^2 * 6 * mesh2splatLoadedMeshCount, mesh2splatMaxGaussians)`. `mesh2splatLoadedMeshCount` is derived from the GLB writer's emitted primitive instances, not selected Rhino object count. It uses the larger guard only when `allowLargeOutput: true`; the known 12-triangle, one-primitive cube at `standard`/`1024` must pass the guard. With current `mesh2splatMaxGaussians = 7000000`, even the largest first-slice `standard` estimate is below the normal `2 GiB` guard, so tests should treat this as a reported capacity estimate unless they inject a lower test cap. It must not be presented as predicted splat coverage or predicted `gaussianCount`.
- After conversion, `actualPlyBytes` is measured from the file system and validated against the selected format's PLY header and stride.

Sizing fixtures:

- `cube_textured_1m_v1`: the existing 1m cube fixture from `mesh2splat_test.3dm`, with valid channel-1 UVs and a file-backed checker/base-color bitmap.
- `building_lowpoly_textured_v1`: a deterministic generated fixture required before the live sizing matrix runs. It must exist as either a committed fixture/generator in the Mesh2Splat fork milestone or a small pre-implementation Rook fixture-only patch before Rook tool implementation planning starts. It represents a small building massing, approximately 20m x 12m x 9m, with 120-250 triangles, 3-6 simple facade/roof/trim materials, at least one file-backed facade/window-atlas bitmap, valid channel-1 UVs for every textured primitive, and scalar fallback colors for every material. The intended use case is early architectural massing/building-scale export, not a toy cube or high-detail production building.
- The live sizing matrix must record fixture version, triangle count, emitted primitive-instance count, material count, texture dimensions, `samplingResolution`, format, `gaussianCount`, `actualPlyBytes`, duration, and any capacity diagnostics.

Error matrix:

| Code | Owner | Happens before artifacts? | Cleanup behavior | Notes |
| --- | --- | --- | --- | --- |
| `invalid_request` | Python | Yes | None | Invalid option type/value, invalid output directory policy, unsupported format, unsupported `samplingResolution`, or unsupported option combination. |
| `invalid_output_directory` | Python | Yes, unless raised during post-capture directory creation | None before run directory creation; when a manifest exists, preserve `manifest.json` with failure state | Output path is missing, relative, resolves to a file, cannot be created intentionally, cannot be safely canonicalized, or collides at exclusive create/publish time. |
| `invalid_executable` | Python | Yes | None | Explicit `mesh2splatPath` is invalid. Invalid non-explicit candidates are rejected with diagnostics and lookup continues. |
| `invalid_working_directory` | Python | Yes | None | Caller-provided `mesh2splatWorkingDirectory` is not an absolute existing directory after canonicalization. |
| `large_output_requires_opt_in` | Python | Yes | None | Raised for `samplingResolution > 512` or `format: standard` unless `allowLargeOutput: true`. |
| `mesh2splat_not_found` | Python | Yes | None | Executable lookup exhausts all sources before native capture. Includes lookup diagnostics. |
| `selection_required` | Native | Yes | None | Neither explicit ids nor current selection produced candidate objects. |
| `invalid_object_id` | Native | Yes | None | Explicit id not found or malformed. |
| `unsupported_requested_object` | Native | Yes unless `allowPartial: true` | None | Explicit hidden/deleted/reference/locked/unsupported object. With `allowPartial`, object is skipped and warning is returned. |
| `no_supported_meshes` | Native | Yes | None | After allowed skips, no visible mesh objects remain. |
| `capture_too_large` | Native | Yes | None | Native source object/mesh/JSON estimate cap exceeded before serializing full mesh arrays. |
| `texture_too_large` | Python | Yes | None | Resolved source bitmap exceeds Python texture byte cap before image read/conversion. |
| `texture_decode_too_large` | Python | Yes for GLB/PLY | Remove only manifest-listed files inside the run directory | Pillow decompression-bomb warning/error, pixel cap, or decoded-byte cap exceeded before PNG conversion. |
| `texture_read_failed` | Python | Yes for GLB/PLY | Remove only manifest-listed files inside the run directory | Raised only when texture read/decode fails and no scalar fallback is allowed or available. |
| `glb_too_large` | Python | GLB/PLY are not created | Remove only manifest-listed files inside the run directory | Post-seam-split vertex count or estimated GLB byte count exceeds Python-owned cap before writing GLB. |
| `glb_write_failed` | Python | Partial GLB temp may exist | Remove only manifest-listed files inside the run directory | File-system, encoding, or payload expansion failure. |
| `glb_validation_failed` | Python | GLB may exist but is not registered | Preserve GLB only when `preserveDebugArtifacts: true`; otherwise remove manifest-listed generated files inside the run directory | Validation failure before `mesh2splat`; PLY is not attempted. |
| `artifact_registration_failed` | Python | Some files may already exist | Do not delete generated files | Non-fatal warning for GLB or PLY registration failures. |
| `mesh2splat_timeout` | Python | GLB may already be registered | Terminate process tree where possible; remove only manifest-listed partial PLY files inside the run directory; preserve stdout/stderr tail | Return timeout and stdout/stderr metadata. |
| `mesh2splat_glb_parse_failed` | Python | GLB may already be registered | Preserve or remove partial PLY according to `preserveDebugArtifacts` | CLI returned `GLB_PARSE_FAILED` or exit code `4`; treat as probable Rook GLB writer defect. |
| `mesh2splat_capacity_exceeded` | Python | GLB may already be registered; PLY is not created | No PLY cleanup expected; preserve stdout/stderr and capacity fields | CLI reported `CAPACITY_EXCEEDED` before PLY write/export. Result must include `attemptedGaussianCount`, `maxGaussianCapacity`, and `samplingResolution`. |
| `mesh2splat_failed` | Python | GLB may already be registered | Preserve or remove partial PLY according to `preserveDebugArtifacts` | Non-zero exit, CLI JSON `ok:false`, or OpenGL-context failure. |
| `ply_validation_failed` | Python | GLB may already be registered | Preserve PLY only when `preserveDebugArtifacts: true`; otherwise remove manifest-listed PLY files inside the run directory | Header/count/property/size mismatch after nominal CLI success. |

## Test Plan and Acceptance Criteria

Test plan:

- Unit-test GLB writer output for a simple textured cube.
- Unit-test the new `glb_writer` unit directly for chunk framing, JSON padding, 4-byte alignment, bufferViews/accessors, accessor `min`/`max`, index widths, embedded image bufferViews, and binary chunk layout.
- Unit-test GLB validator against textured, solid-color, missing-texture, and black-material cases.
- Unit-test selection filtering for explicit ids, current selection, invalid ids, hidden/locked objects, mixed unsupported selections, and empty selections.
- Unit-test `unitsMode: meters` and `unitsMode: raw`, including document unit conversion factors and recorded `unitScaleToMeters`.
- Unit-test native capture transform semantics: captured vertices are world-space after object instance transform application, and result metadata records transform diagnostics and `upAxis: "Z"`.
- Unit-test UV policy: textured materials with missing/invalid channel-1 UVs fall back to scalar `baseColorFactor` with warning; scalar-only materials without valid UVs fail until the Mesh2Splat dummy-UV smoke test is present, then emit deterministic `(0, 0)` `TEXCOORD_0`.
- Unit-test native capture cap decisions using `maxObjects`, `maxSourceVertices`, `maxSourceTriangles`, and `maxEstimatedJsonBytes`.
- Unit-test Python texture path trust decisions before file I/O: reject URL schemes, skip UNC/network paths unless `allowNetworkTextures: true`, reject relative paths, require accepted paths to resolve to regular local files, reject directories/device paths/network reparse targets by default, report user-trusted network access when allowed, and do not make rejected fallback-capable paths require `baseColorTexture`.
- Unit-test Python texture cap decisions using `os.stat(resolvedTexturePath).st_size` before image decoding.
- Unit-test decoded texture caps and Pillow decompression-bomb handling for over-pixel-limit and over-decoded-byte-limit images.
- Unit-test Python post-expansion caps for `maxExpandedVertices` and `maxGlbBytes`, including a seam-split case that exceeds source mesh ratios.
- Unit-test `Mesh2Splat.exe` lookup order: explicit parameter, `ROOK_MESH2SPLAT_EXE`, mutable config, bundled config, bundled executable location, and `PATH`.
- Unit-test executable validation: invalid explicit `mesh2splatPath` fails hard with `invalid_executable`; invalid env/config/bundled/PATH candidates are rejected while lookup continues; non-`Mesh2Splat.exe` basenames from non-explicit sources are rejected; explicit user-trusted nonstandard basename is accepted; selected source diagnostics, rejected candidate diagnostics, argv-list `shell=False` execution, and no shell command string are asserted.
- Unit-test child process environment policy: default launch uses only the pinned allowlist (`SystemRoot`, `windir`, `TEMP`, `TMP`, and `PATH` only when justified by lookup/runtime loading) and does not expose API keys or other Rook MCP secrets; explicit executable and working-directory overrides do not inherit the full environment unless a future explicit user-trusted option allows it and reports that policy.
- Unit-test config diagnostics for missing, unreadable, and malformed mutable `mesh2splat.json`; all continue to bundled config and later lookup sources rather than returning `invalid_request`.
- Unit-test output directory behavior: explicit `outputDirectory` is required, validation is side-effect free, must be absolute, rejects existing files, defers missing-directory creation until after native capture succeeds, retains a newly-created `outputDirectory` if later run-directory or manifest creation fails, canonicalizes symlinks/reparse points where available, creates a unique run directory inside it, uses fixed output names, and refuses collisions instead of overwriting.
- Unit-test exclusive/no-overwrite file creation for `manifest.json`, `capture.glb`, and `capture.ply`, including create/publish races where the destination appears after collision checks.
- Unit-test native capture failures assert no `outputDirectory` creation, no run directory, and no `manifest.json`.
- Unit-test cleanup safety: cleanup re-resolves manifest paths, deletes only regular manifest-listed files created by the current run whose resolved paths are still inside the run directory, refuses outside paths and symlink/reparse-point swaps, and does not recursively delete the run directory.
- Unit-test manifest lifecycle: `manifest.json` is retained and updated on success and all failures after run-directory creation, is not registered as an artifact, and is not created for pre-run-dir failures.
- Unit-test `mesh2splatWorkingDirectory`: absent defaults to executable parent, valid absolute existing directory is accepted as an explicit user-trusted override, relative/missing/file paths fail with `invalid_working_directory`, and shell expansion is not performed.
- Unit-test texture expectation semantics: fallback-capable texture failures produce warnings and scalar `baseColorFactor`; only images that pass trust/path/size/decode/format checks are required to produce `baseColorTexture`.
- Unit-test missing executable behavior to assert no native capture call, no GLB/PLY file creation, and `mesh2splat_not_found` lookup diagnostics.
- Unit-test Mesh2Splat fork prerequisite behavior in the `bringfire/mesh2splat` repo: CLI parsing accepts canonical deterministic `--sampling-resolution` integers over `16..4096`; compatibility `--resolution` behavior is covered if retained; `--effective-resolution` is rejected unless deliberately implemented as an alias; CLI help/default validation tests cover the new flag; success JSON reports effective resolution; and capacity overflow reports `CAPACITY_EXCEEDED` with `attemptedGaussianCount`, `maxGaussianCapacity`, and `samplingResolution`.
- Unit-test Rook `samplingResolution` validation: integers `16..4096` are valid; values outside that range fail with `invalid_request`.
- Unit-test large-output guards: `samplingResolution > 512` and `format: standard` fail without `allowLargeOutput`; both proceed with explicit opt-in.
- Unit-test pre-run PLY size guard from `mesh2splatLoadedMeshCount`, `samplingResolution`, Mesh2Splat's `samplingResolution^2 * 6 * loadedMeshCount` capacity model, `mesh2splatMaxGaussians`, format stride, and `allowLargeOutput`; verify the documented one-primitive cube at `standard`/`1024` passes with large-output opt-in, the value is reported as estimate metadata, and rejection behavior is tested only by injecting a lower test cap or future Mesh2Splat limit. Post-run byte validation remains authoritative.
- Unit-test timeout policy and cleanup: default 300 seconds for `compressed-pbr` at `samplingResolution <= 512`, default 900 seconds for `standard` or `samplingResolution > 512`, explicit timeout override, process-tree termination where available, stdout/stderr preservation, diagnostics when only direct-child termination is available, and manifest-bounded cleanup of partial PLY files from the current run.
- Unit-test execution args to assert requested `format` and `samplingResolution` are passed through, with `compressed-pbr` and the post-sizing-matrix default only as defaults.
- Unit-test artifact registration for embedded-only textures: first slice returns no texture artifact id and the GLB artifact owns embedded texture bytes.
- Unit-test artifact registry provenance: `_SOURCE_RANK["mesh2splat_capture"] = 2` promotes over `explicit`, mesh2splat-owned reruns replace `document_name`, `origin_session_id`, and `label`, and generic provenance fallback is reported if the registry change is absent.
- Unit-test `GLB_PARSE_FAILED` handling: Mesh2Splat exit code `4` or JSON `errorCode: "GLB_PARSE_FAILED"` maps to `mesh2splat_glb_parse_failed`.
- Integration-test `Mesh2Splat.exe` with the generated cube GLB and assert tolerant JSON stdout parsing, PLY header, vertex count, actual byte count, and format-specific file size.
- Live/local GPU integration-test Mesh2Splat with `cube_textured_1m_v1` at `samplingResolution` values `64`, `128`, `256`, `512`, and `1024` after the Mesh2Splat fork exposes the new density flag; assert success JSON, reported effective resolution, valid PLY, gaussian count, and actual bytes.
- Live/local GPU sizing matrix before implementation: run `cube_textured_1m_v1` and `building_lowpoly_textured_v1` at `64/128/256/512/1024` using `compressed-pbr`. Use this matrix to choose Rook's first default (`64`, `128`, or `256`) before coding the Rook tool.
- Live/local GPU smoke-test scalar-only GLB conversion with deterministic dummy `(0, 0)` `TEXCOORD_0` before enabling dummy UV emission for scalar-only no-UV meshes.
- Integration-test display handoff separately: compressed-PBR preview requires a matching loader path; otherwise preview/export uses `standard` with explicit large-output opt-in.
- Live Rhino smoke test against `mesh2splat_test.3dm` selected cube.

Acceptance criteria:

- A selected small Rhino mesh cube can be converted to GLB without Rhino's built-in GLB exporter.
- The generated GLB contains embedded texture data when the Rhino material has a bitmap base color.
- The Mesh2Splat fork exposes canonical deterministic `--sampling-resolution` over `16..4096`, reports effective resolution in JSON, fails clearly on capacity overflow before PLY write/export, and passes the live sizing matrix before Rook enables a default sampling resolution.
- Missing `Mesh2Splat.exe` fails before native capture and creates no artifacts.
- Native capture failures create no output directory, run directory, manifest, or artifacts.
- Invalid executable paths or working directories fail before native capture and create no artifacts. Invalid output-directory validation fails before native capture; deferred output-directory creation failures occur after capture but before artifact creation.
- The default conversion uses `compressed-pbr` at the sampling resolution chosen from the live sizing matrix; `samplingResolution` must be an integer `16..4096`; `samplingResolution > 512` or `format: standard` requires explicit large-output opt-in.
- `compressed-pbr` is treated as the storage/transport default; display uses it only when a matching loader path exists, otherwise display/export requests `standard` with explicit opt-in.
- Each run writes to a unique run directory with fixed output names, never overwrites existing GLB/PLY files, and cleanup deletes only manifest-listed files inside that run directory.
- `mesh2splat` is launched with argv-list execution, `shell=False`, and a sanitized child environment; timeout attempts process-tree termination; the result reports selected executable path/source, working directory, and environment policy.
- `mesh2splat` returns `ok: true` for the generated GLB.
- The resulting PLY passes header/count/size validation.
- GLB and PLY artifacts are registered and returned with artifact ids, or registration failures are explicitly reported. Embedded-only textures are represented by the GLB artifact; no texture sidecar artifacts are emitted in the first slice.
- The tool reports clear warnings for unsupported or degraded material paths.

## Preservation Checklist

This checklist maps the previously accumulated critical guarantees to the new source-of-truth sections:

| Critical guarantee | Source-of-truth section |
| --- | --- |
| Pre-capture executable resolution | **Contract Invariants and Happy Path**; executable details in **Filesystem/Artifact/Process Safety Contract** |
| No run directory before native capture succeeds | **Contract Invariants and Happy Path**; filesystem details in **Filesystem/Artifact/Process Safety Contract** |
| Explicit output directory and unique run dir | **Filesystem/Artifact/Process Safety Contract** |
| Exclusive/no-overwrite writes | **Filesystem/Artifact/Process Safety Contract** |
| Manifest-bounded cleanup | **Filesystem/Artifact/Process Safety Contract** |
| Subprocess `shell=False`, timeout, process-tree termination | **Filesystem/Artifact/Process Safety Contract** |
| Child environment policy | **Filesystem/Artifact/Process Safety Contract** |
| Executable trust/fallback semantics | **Filesystem/Artifact/Process Safety Contract** |
| Texture path trust and decode caps | **Filesystem/Artifact/Process Safety Contract** |
| Artifact provenance/fallback | **Filesystem/Artifact/Process Safety Contract** |
| Mesh2Splat sampling-resolution prerequisite | **Contract Invariants and Happy Path** |
| Live density sizing matrix | **Test Plan and Acceptance Criteria** |
| GLB writer implementation risk | **Python GLB/Process Pipeline Contract** |
| Coordinate convention and `upAxis` metadata | **Python GLB/Process Pipeline Contract** |
| Conservative pre-run PLY size guard | **Python GLB/Process Pipeline Contract**; validator treatment in **Validation and Error Matrix** |
| UV policy for textured and scalar-only meshes | **Python GLB/Process Pipeline Contract** |
| Embedded-only texture artifact behavior | **Python GLB/Process Pipeline Contract**; artifact registration in **Filesystem/Artifact/Process Safety Contract** |
| GLB/PLY validators | **Validation and Error Matrix** |
| Large-output guard | **Contract Invariants and Happy Path** |

## Later Slices

- File-backed native capture payloads for larger meshes.
- Stable default artifact output directory and cleanup policy so `outputDirectory` can become optional.
- Support for `pbr` PLY format after property layout and stride are pinned.
- Handoff to `ve_engine` `splat_v0` for display.
- General glTF orientation compatibility for non-Rook consumers.
- Performance controls for crop/selection and expected PLY size beyond the first capacity estimate.
