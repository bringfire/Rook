# FFmpeg Bundling Policy for Video Sidecars

Date: 2026-05-12

## Purpose

Rook now derives generated-video `poster`, `start_frame`, and `end_frame`
sidecars from saved local MP4 files by invoking `ffmpeg.exe` as a subprocess.
That path works in development, but it currently depends on whatever FFmpeg
binary is available through local configuration or `PATH`.

This slice makes the shippable dependency explicit: Rook will bundle a vetted
LGPL-only Windows FFmpeg executable so users do not need to install anything
extra.

This is an engineering and release-policy design, not legal advice. The policy
is intentionally conservative because Rook is closed-source.

## Sources

- FFmpeg legal guidance: https://www.ffmpeg.org/legal.html
- FFmpeg download page: https://ffmpeg.org/download.html

The relevant constraints from FFmpeg's own guidance are:

- FFmpeg is LGPL by default, but optional GPL parts make GPL apply to FFmpeg.
- LGPL compliance guidance calls for builds without `--enable-gpl` and without
  `--enable-nonfree`.
- FFmpeg publishes source code and points Windows users to third-party binary
  builds; a familiar download source is not sufficient provenance by itself.

## Decisions

### 1. Release packages bundle FFmpeg

The Rook installer/release payload must include a vetted Windows `ffmpeg.exe`.
Users must not need to install FFmpeg, modify `PATH`, or configure an FFmpeg
path for generated-video thumbnails and frame sidecars to work.

### 2. Bundled FFmpeg must be LGPL-only

Release packaging must fail closed unless the bundled FFmpeg payload is proven
acceptable. The gate must reject:

- missing FFmpeg metadata;
- missing `ffmpeg.exe`;
- checksum mismatch;
- unreadable or failing `ffmpeg -version`;
- missing or unreadable configure line;
- configure line containing `--enable-gpl`;
- configure line containing `--enable-nonfree`;
- unknown binary provenance;
- missing compliance payload files.

The release gate must never accept a GPL-enabled or nonfree FFmpeg build because
it is easier to obtain.

### 3. Bundled FFmpeg must be functionally acceptable

License/provenance validation is necessary but not sufficient. Release
packaging must also prove the bundled binary can execute the exact command
families Rook depends on for video sidecars.

The release gate must run a deterministic smoke against a tiny checked-in or
generated fixture MP4 and verify:

- display-poster extraction succeeds with Rook's poster command shape;
- first-frame extraction succeeds with Rook's frame-index command shape;
- last-frame extraction succeeds with Rook's last-frame command shape;
- each output is a readable JPEG image;
- each output is non-empty and has nonzero dimensions;
- failures are reported as release-blocking diagnostics.

This smoke must use the bundled FFmpeg payload under validation. It must not use
PATH lookup or a developer-machine FFmpeg.

### 4. Subprocess only

This slice packages `ffmpeg.exe` for subprocess invocation only. Rook must not
link `libav*` libraries or package FFmpeg DLLs as a linked dependency in this
slice.

If Rook ever links FFmpeg libraries later, that must be a separate reviewed
slice that revisits LGPL dynamic-linking requirements explicitly.

### 5. Dev convenience is separate from release policy

Development and tests may continue using a configured FFmpeg path or PATH lookup.
That is useful for local smoke tests and fake-release development.

Release validation is different: it must prove the bundled payload is the one
being packaged. A PATH-discovered FFmpeg, even if usable locally, must never
satisfy release validation.

### 6. Compliance artifacts are first-class payload

The installer/release payload must include FFmpeg compliance materials alongside
the binary. These are product artifacts, not internal notes.

At minimum, the payload must include:

- FFmpeg license text;
- Rook FFmpeg notice text;
- FFmpeg source URL;
- exact corresponding FFmpeg source archive identity;
- source archive checksum;
- binary URL or build-source identity;
- binary checksum;
- FFmpeg version;
- configure line;
- build/provenance notes;
- attribution text suitable for Rook About, EULA, and download/release docs.

## Proposed Repository Shape

Use a repository-owned third-party payload directory that is explicit enough for
release tooling to inspect and installer tooling to package.

Proposed shape:

```text
third_party/
  ffmpeg/
    README.md
    ffmpeg.exe
    ffmpeg-provenance.json
    LICENSE.FFmpeg.txt
    NOTICE.FFmpeg.txt
    SOURCE.FFmpeg.txt
```

The exact directory can be adjusted during implementation only if the release
tooling already has a stronger convention. The payload must remain separate
from Rook source code and clearly identified as third-party software.

### `ffmpeg-provenance.json`

The provenance file must be structured so tests can parse it instead of
scraping prose.

Required fields:

- `name`: must identify FFmpeg;
- `version`;
- `license`: must indicate LGPL-only policy;
- `binary_path`: repository-relative path to `ffmpeg.exe`;
- `binary_sha256`;
- `binary_url` or `build_source`;
- `source_url`;
- `source_archive`;
- `source_sha256`;
- `configure_line`;
- `validated_command_surfaces`: must include `poster`, `first_frame`, and
  `last_frame`;
- `verified_at`;
- `verified_by`;
- `notes`.

The implementation plan can refine field names, but it must keep the file
machine-readable, release-gate owned, and complete enough to identify exact
corresponding FFmpeg source.

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

The Inno installer must package the bundled FFmpeg payload when the plugins
component is installed.

The release workflow must run a fail-closed validation step before invoking
Inno Setup or producing a release artifact. That step must:

1. load `ffmpeg-provenance.json`;
2. verify required fields are present;
3. verify `ffmpeg.exe` exists at the declared path;
4. verify `ffmpeg.exe` SHA-256 matches metadata;
5. execute declared `ffmpeg.exe -version`;
6. extract the runtime configure line;
7. reject missing configure output;
8. reject `--enable-gpl`;
9. reject `--enable-nonfree`;
10. verify required compliance files exist;
11. run the functional command smoke with the bundled binary;
12. reject poster extraction failure;
13. reject first-frame extraction failure;
14. reject last-frame extraction failure;
15. reject missing, empty, or unreadable JPEG outputs;
16. verify installer script includes the FFmpeg payload;
17. report the accepted version, path, checksum, configure line, and smoke
    result.

The release guard must be deterministic and easy to run locally. A PowerShell
test or script fits the existing Windows release guard style.

## User-Facing Notice Surfaces

This slice must add or update text in the release payload so users can inspect
the FFmpeg attribution and source-compliance information.

Minimum target surfaces:

- installed FFmpeg notice/source files;
- exact corresponding FFmpeg source archive shipped as a release asset or
  otherwise made available from the same release/download surface;
- release/build documentation that explains FFmpeg is bundled;
- installer guard tests proving the payload is included.

If the current Rook product has an About/EULA surface, add the FFmpeg notice
there. If it does not, include the exact text in installed docs and make the
future UI surface a separate follow-up.

## Testing

Unit tests must focus on policy. The release guard must include the functional
extraction smoke against the bundled FFmpeg payload.

Required coverage:

- release validation accepts a fixture metadata/configure line with no GPL or
  nonfree flags;
- release validation rejects `--enable-gpl`;
- release validation rejects `--enable-nonfree`;
- release validation rejects missing configure line;
- release validation rejects checksum mismatch;
- release validation rejects missing compliance files;
- release validation rejects a bundled binary that cannot run the poster command
  shape against the fixture MP4;
- release validation rejects a bundled binary that cannot run the first-frame
  command shape against the fixture MP4;
- release validation rejects a bundled binary that cannot run the last-frame
  command shape against the fixture MP4;
- release validation rejects missing, empty, or unreadable JPEG smoke outputs;
- installer guard proves the FFmpeg payload is included;
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
- Downloading FFmpeg during install.
- Requiring users to install FFmpeg manually.
- Building FFmpeg from source inside the normal Rook release build.
- Replacing the existing poster/frame extraction commands except as needed by a
  later reviewed extraction-quality slice.
- Legal advice or final legal review.

## Implementation Plan Decisions

These questions must be resolved in the implementation plan, not by weakening
the policy:

1. Which LGPL-only Windows FFmpeg build will be used for the first payload?
2. Will the first slice commit the binary directly, or stage it as a release
   asset pulled into the installer build by a deterministic script?
3. Where will Rook's installed FFmpeg live relative to `RookNative.rhp`,
   `Rook.rhp`, and `{app}`?
4. Does Rook currently have an About/EULA surface that will receive the
   attribution text immediately, or will the installed notice files carry the
   compliance text for this slice?

## Acceptance Criteria

- Rook release packaging fails closed for missing, GPL-enabled, nonfree,
  checksum-mismatched, or unknown-provenance FFmpeg payloads.
- Rook release packaging fails closed if the bundled FFmpeg cannot produce
  readable JPEGs for Rook's poster, first-frame, and last-frame command shapes
  against the release smoke fixture.
- The installer includes the bundled LGPL-only `ffmpeg.exe` and compliance
  files.
- Runtime sidecar extraction prefers the bundled installed `ffmpeg.exe`.
- Development configured/PATH fallback remains possible but cannot satisfy
  release validation.
- Sidecar producers continue invoking FFmpeg as a subprocess and do not link
  FFmpeg libraries.
- The slice does not introduce provider-payload mappings or GH NLE behavior.
