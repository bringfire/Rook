# Rook Minimal FFmpeg Build

Rook ships `ffmpeg.exe` only for generated-video sidecar extraction. The build
is LGPL-only, subprocess-only, and intentionally minimal.

The release recipe uses official FFmpeg source metadata from
`rook-ffmpeg-source.json`, configure arguments from
`rook-ffmpeg-configure.txt`, and the release validation allowlist from
`rook-ffmpeg-enable-allowlist.json`.

The repository commits the recipe and the validated `ffmpeg.exe` payload. It
does not commit generated source bundles. Release prep generates the matching
source bundle and publishes it beside the installer.

Normal release validation must reject:

- missing or unverified official source signature;
- `--enable-gpl`;
- `--enable-nonfree`;
- any runtime `--enable-*` flag not in the committed allowlist;
- missing generated source-bundle manifest;
- functional smoke failure for poster, first frame, or last frame.
