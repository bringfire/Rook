# FFmpeg Bundling Policy for Video Sidecars

Date: 2026-05-12

## Purpose

Rook derives generated-video `poster`, `start_frame`, and `end_frame`
sidecars from saved local video files by invoking `ffmpeg.exe` as a subprocess.
Users should not need to install or configure FFmpeg for those sidecars to work
in a packaged Rook build.

This slice defines the shippable FFmpeg policy for a closed-source Rook release:
Rook will ship an LGPL-only, Rook-owned, minimal Windows FFmpeg build that
matches Rook's actual sidecar command surface. Release packaging must fail
closed when the bundled binary, build recipe, source metadata, source bundle, or
functional smoke is missing or inconsistent.

This is an engineering and release-policy design, not legal advice. The policy
is intentionally conservative.

## Sources

- FFmpeg legal guidance: https://www.ffmpeg.org/legal.html
- FFmpeg download page: https://ffmpeg.org/download.html

The relevant constraints from FFmpeg's own guidance are:

- FFmpeg is LGPL by default, but optional GPL parts make GPL apply to FFmpeg.
- LGPL compliance guidance calls for builds without `--enable-gpl` and without
  `--enable-nonfree`.
- FFmpeg compliance guidance calls for corresponding source, configure notes,
  `changes.diff`, source hosting beside the distributed binary, notice/EULA
  language, and repeating the checklist for LGPL external libraries compiled
  into FFmpeg.
- FFmpeg publishes source code and points Windows users to third-party binary
  builds; a familiar third-party binary is not sufficient provenance by itself.

## Core Decisions

### 1. PR #148 remains draft until the payload model changes

The current broad BtbN static build must not be treated as shippable merely
because it is LGPL-labeled and passes Rook's functional smoke. PR #148 must stay
draft until the broad BtbN payload is either removed from the shippable payload
or quarantined as explicitly non-shippable development input.

### 2. Rook owns the shippable FFmpeg build recipe

The target implementation is a Rook-owned minimal FFmpeg build from official
FFmpeg source. The repository must own:

- the pinned FFmpeg source version and verification metadata;
- the exact configure recipe;
- the Windows build script or repeatable build instructions;
- release validation logic;
- the expected generated binary/source-bundle contract.

The repository must not rely on broad third-party static-build scripts as a
compliance substitute for the binary Rook distributes.

### 3. The build is LGPL-only and minimal

The Rook FFmpeg build must use `--disable-everything` and enable only the
components Rook needs for video sidecar extraction.

The first minimal build should target:

- `ffmpeg` program only;
- `file` protocol;
- MP4/MOV demuxing for provider MP4 outputs;
- WebM/Matroska demuxing for provider WebM outputs;
- native video decoders needed by expected provider outputs;
- matching native parsers where FFmpeg requires them;
- `select` and `reverse` filters;
- MJPEG encoding;
- `image2` JPEG output.

It must not include:

- `--enable-gpl`;
- `--enable-nonfree`;
- optional external codec libraries by default;
- broad hardware, subtitle, audio, network, device, or font stacks unless a
  concrete Rook sidecar fixture proves they are required.

Validation must reject unexpected `--enable-lib*` flags by default. If a future
Rook slice intentionally adds an external library, that slice must add a
release-blocking source/license manifest for that library.

### 4. Codec support is locked by evidence, not convenience

Before the minimal configure line is locked, implementation must perform a
codec/container reality check against Rook's expected provider outputs. Since
Rook only extracts video frames, audio decoding should remain disabled unless a
real fixture proves it is required for demuxing.

The first release smoke set must include at least:

- H.264 MP4;
- one WebM/VP9 fixture or one AV1 fixture.

If provider outputs are expected to include HEVC, AV1 MP4, or VP9 WebM, the
plan should add a tiny synthetic fixture for each expected codec/container or
document why a representative fixture is unavailable. Any additional configure
component must be justified by a failing or required fixture.

### 5. Recipe, binary payload, and source bundle are separate artifacts

The design intentionally separates three concerns:

- **Source recipe in repo:** committed build scripts, configure recipe, pinned
  source metadata, validation logic, and fixture inputs.
- **Binary payload included in installer:** the validated minimal
  `ffmpeg.exe` and installed compliance/notice files.
- **Source bundle published with release:** generated during release prep and
  published beside the installer, not committed to Git unless a future release
  policy explicitly chooses that.

The repo should not commit generated source archives such as
`ffmpeg-source-bundle.zip` by default. Release validation must instead require a
generated source-bundle path, manifest, and SHA-256 in the release staging area.

### 6. Broad third-party static builds fail closed by default

Release packaging must reject a broad third-party static FFmpeg build unless
every external library compiled into that binary has complete source/license
provenance.

For this slice, the preferred path is not to complete such a broad manifest.
The preferred path is to remove the BtbN binary from the shippable payload and
replace it with the Rook-owned minimal build.

### 7. Subprocess only

This slice packages `ffmpeg.exe` for subprocess invocation only. Rook must not
link `libav*` libraries or package FFmpeg DLLs as linked dependencies in this
slice.

If Rook ever links FFmpeg libraries later, that must be a separate reviewed
slice that revisits LGPL dynamic-linking requirements explicitly.

### 8. Dev convenience is separate from release policy

Development and tests may continue using a configured FFmpeg path or PATH
lookup. That is useful for local smoke tests and development.

Release validation is different: it must prove the bundled minimal payload is
the one being packaged. A PATH-discovered FFmpeg, even if usable locally, must
never satisfy release validation.

## Repository Shape

The repository should contain the release recipe and the installable binary
payload. The source bundle is generated for release and published as a release
asset beside the installer.

Proposed shape:

```text
scripts/
  ffmpeg/
    README.md
    build-rook-ffmpeg.ps1
    rook-ffmpeg-configure.txt
    rook-ffmpeg-source.json
third_party/
  ffmpeg/
    README.md
    ffmpeg.exe
    ffmpeg-provenance.json
    LICENSE.FFmpeg.txt
    NOTICE.FFmpeg.txt
    SOURCE.FFmpeg.txt
    fixtures/
      sidecar-smoke-h264.mp4
      sidecar-smoke-vp9.webm
```

`third_party/ffmpeg/ffmpeg.exe` may be committed through Git LFS only if it was
produced by the Rook recipe and passes release validation. A broad third-party
binary must not live in the shippable payload directory.

## Build Recipe Contract

The build recipe must:

1. download or consume the pinned official FFmpeg source archive;
2. verify the source archive SHA-256;
3. record PGP verification when available on the build machine;
4. apply no local patches unless they are recorded;
5. generate `changes.diff`, even when empty;
6. run the exact committed configure recipe;
7. build `ffmpeg.exe`;
8. compute the binary SHA-256;
9. write machine-readable provenance;
10. create a release source bundle containing source, build notes,
    `changes.diff`, configure line, license text, and provenance metadata.

The normal Rook application build does not need to rebuild FFmpeg. The release
process may use a previously generated minimal `ffmpeg.exe`, but packaging must
validate that the binary, recipe metadata, and generated source bundle all
match.

## Provenance Metadata

`third_party/ffmpeg/ffmpeg-provenance.json` must be structured so release tests
can parse it instead of scraping prose.

Required fields:

- `name`: must identify FFmpeg;
- `version`;
- `license`: must indicate LGPL-only policy;
- `binary_path`: repository-relative path to `ffmpeg.exe`;
- `binary_sha256`;
- `source_url`;
- `source_archive`;
- `source_sha256`;
- `source_signature_url`;
- `source_signature_status`: for example `verified`, `unavailable`, or
  `not-checked`;
- `build_recipe_path`;
- `configure_recipe_path`;
- `configure_line`;
- `changes_diff_path`;
- `source_bundle_manifest_name`: expected release-staging manifest filename;
- `validated_command_surfaces`: must include `poster`, `first_frame`, and
  `last_frame`;
- `validated_fixtures`: fixture names/codecs/containers used by the smoke;
- `verified_at`;
- `verified_by`;
- `notes`.

The implementation plan can refine field names, but it must keep the file
machine-readable and complete enough to identify exact corresponding FFmpeg
source and the generated release source bundle.

## Release Source Bundle Manifest

Release prep must generate a source-bundle manifest in the release staging area.
This manifest is not committed as a generated artifact. It records the concrete
source bundle that will be published beside the installer.

Required fields:

- `bundle_path`: release-staging path to the generated source bundle;
- `bundle_sha256`;
- `ffmpeg_source_archive`;
- `ffmpeg_source_sha256`;
- `configure_line`;
- `changes_diff_path`;
- `build_recipe_path`;
- `generated_at`;
- `generated_by`.

Release validation must load this staging manifest, verify the source bundle
exists, verify the source bundle checksum, and verify the manifest matches the
committed FFmpeg provenance and configure recipe.

## Runtime Resolution

Production runtime must prefer the bundled FFmpeg path installed with Rook.
The existing configured-path/PATH resolver behavior may remain available for
development and tests.

Recommended resolution order:

1. bundled installed FFmpeg path;
2. explicit configured path, if a future supported setting exists;
3. PATH lookup for development/test fallback.

The resolver result must make the source explicit so diagnostics can tell
whether sidecar extraction used bundled, configured, or PATH FFmpeg.

Release validation must not use this fallback chain. It must inspect the
repository/release payload directly.

## Installer and Release Tooling

The Inno installer must package the validated bundled FFmpeg payload when the
plugins component is installed.

The release workflow must run a fail-closed validation step before invoking
Inno Setup or producing a release artifact. That step must:

1. load `ffmpeg-provenance.json`;
2. verify required fields are present;
3. verify `ffmpeg.exe` exists at the declared path;
4. verify `ffmpeg.exe` SHA-256 matches metadata;
5. execute declared `ffmpeg.exe -version`;
6. extract the runtime version and configure line;
7. verify runtime version equals provenance version;
8. verify runtime configure line equals the committed configure recipe;
9. reject missing configure output;
10. reject `--enable-gpl`;
11. reject `--enable-nonfree`;
12. reject unexpected `--enable-lib*`;
13. verify source metadata and source checksum;
14. verify `changes.diff` exists;
15. verify the generated release source-bundle manifest exists;
16. verify the generated release source-bundle SHA-256 matches the staging
    manifest;
17. verify required installed compliance files exist;
18. run the functional command smoke with the bundled binary;
19. reject poster extraction failure;
20. reject first-frame extraction failure;
21. reject last-frame extraction failure;
22. reject missing, empty, or unreadable JPEG outputs;
23. verify installer script includes the FFmpeg payload files;
24. verify release packaging publishes the FFmpeg source bundle beside the
    installer;
25. report the accepted version, path, checksum, configure line, source bundle,
    and smoke result.

The release guard must be deterministic and easy to run locally. A PowerShell
script fits the existing Windows release guard style.

## Functional Smoke

License/provenance validation is necessary but not sufficient. Release
packaging must also prove the bundled binary can execute the exact command
families Rook depends on for video sidecars.

The smoke must use the bundled FFmpeg payload under validation. It must not use
PATH lookup or a developer-machine FFmpeg.

The smoke must verify:

- display-poster extraction succeeds with Rook's poster command shape;
- first-frame extraction succeeds with Rook's frame-index command shape;
- last-frame extraction succeeds with Rook's last-frame command shape;
- each output is a readable JPEG image;
- each output is non-empty and has nonzero dimensions;
- H.264 MP4 fixture coverage exists;
- WebM/VP9 or AV1 fixture coverage exists;
- failures are reported as release-blocking diagnostics.

## User-Facing Notice Surfaces

This slice must add or update text in the release payload so users can inspect
the FFmpeg attribution and source-compliance information.

Minimum target surfaces:

- installed FFmpeg notice/source files;
- exact corresponding FFmpeg source bundle published as a release asset beside
  the installer;
- release/build documentation that explains FFmpeg is bundled;
- installer guard tests proving the binary payload is included;
- release guard proving the source bundle is staged for publication.

If the current Rook product has an About/EULA surface, add the FFmpeg notice
there. If it does not, include the exact text in installed docs and make the
future UI surface a separate follow-up.

## Testing

Unit tests should focus on policy. The release guard must include the
functional extraction smoke against the bundled FFmpeg payload.

Required coverage:

- release validation accepts a minimal Rook-owned metadata/configure line with
  no GPL, nonfree, or unexpected external-library flags;
- release validation rejects `--enable-gpl`;
- release validation rejects `--enable-nonfree`;
- release validation rejects unexpected `--enable-lib*`;
- release validation rejects broad third-party static builds that lack complete
  external-library source/license manifests;
- release validation rejects missing configure line;
- release validation rejects stale runtime configure metadata;
- release validation rejects stale runtime version metadata;
- release validation rejects checksum mismatch;
- release validation rejects missing compliance files;
- release validation rejects missing `changes.diff`;
- release validation rejects missing source-bundle manifest/path/hash;
- release validation rejects a missing source bundle in release staging;
- release validation rejects a bundled binary that cannot run the poster command
  shape against the fixture set;
- release validation rejects a bundled binary that cannot run the first-frame
  command shape against the fixture set;
- release validation rejects a bundled binary that cannot run the last-frame
  command shape against the fixture set;
- release validation rejects missing, empty, or unreadable JPEG smoke outputs;
- release validation requires H.264 MP4 fixture coverage;
- release validation requires WebM/VP9 or AV1 fixture coverage;
- installer guard proves the FFmpeg binary payload is included;
- release guard proves the FFmpeg source bundle is staged for publication;
- runtime resolver prefers bundled FFmpeg over PATH when bundled exists;
- dev fallback can still resolve configured/PATH FFmpeg outside release
  validation;
- extraction producers continue to receive a resolved executable path and do
  not learn about licensing policy directly.

## Out of Scope

- Provider payload poster ingestion.
- Grasshopper NLE token behavior.
- Any use of `poster` as a frame source.
- Linking FFmpeg libraries.
- Bundling GPL or nonfree FFmpeg builds.
- Shipping a broad third-party static FFmpeg build without full
  external-library source/license provenance.
- Downloading FFmpeg during install.
- Requiring users to install FFmpeg manually.
- Rebuilding FFmpeg as part of every normal Rook application build.
- Committing generated FFmpeg source archives to Git by default.
- Replacing the existing poster/frame extraction commands except as needed by a
  later reviewed extraction-quality slice.
- Legal advice or final legal review.

## Implementation Plan Decisions

These questions must be resolved in the implementation plan, not by weakening
the policy:

1. Which Windows build environment will produce the minimal Rook FFmpeg binary?
2. Which exact FFmpeg source version will be pinned for the first Rook build?
3. Which native decoders, demuxers, parsers, muxers, filters, and protocols are
   required by the fixture reality check?
4. Will the first PR commit the generated minimal `ffmpeg.exe` through Git LFS,
   or will release packaging consume it from a deterministic release-staging
   directory?
5. Where will the generated source bundle live during release staging before it
   is published beside the installer?
6. Where will Rook's installed FFmpeg live relative to `RookNative.rhp`,
   `Rook.rhp`, and `{app}`?
7. Does Rook currently have an About/EULA surface that will receive the
   attribution text immediately, or will installed notice files carry the
   compliance text for this slice?

## Acceptance Criteria

- PR #148 does not mark ready while the broad BtbN binary remains the
  shippable FFmpeg payload.
- Rook has a committed minimal FFmpeg build recipe pinned to official FFmpeg
  source metadata.
- Rook release packaging fails closed for missing, GPL-enabled, nonfree,
  checksum-mismatched, stale-metadata, broad-third-party, or
  unknown-provenance FFmpeg payloads.
- Rook release packaging fails closed for unexpected `--enable-lib*` flags
  unless complete external-library source/license provenance is present.
- Rook release packaging fails closed if the generated FFmpeg source bundle is
  missing from release staging or does not match metadata.
- Rook release packaging fails closed if the bundled FFmpeg cannot produce
  readable JPEGs for Rook's poster, first-frame, and last-frame command shapes
  against the required fixture set.
- The installer includes the bundled LGPL-only minimal `ffmpeg.exe` and
  installed compliance files.
- The release publishes the matching FFmpeg source bundle beside the installer.
- Runtime sidecar extraction prefers the bundled installed `ffmpeg.exe`.
- Development configured/PATH fallback remains possible but cannot satisfy
  release validation.
- Sidecar producers continue invoking FFmpeg as a subprocess and do not link
  FFmpeg libraries.
- The slice does not introduce provider-payload mappings or GH NLE behavior.
