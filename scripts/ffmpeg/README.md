# Rook Minimal FFmpeg Build

Rook ships `ffmpeg.exe` for generated-video sidecars and still-image framing. The build
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

The video framing profile adds native PNG/WebP still decoding, PNG encoding, and
fixed orientation, alpha compositing, Fit/Fill filters. zlib 1.3.2 is built from
the checksum-pinned official source in rook-zlib-source.json into an owned static
prefix. Its archive, metadata, license and static archive checksum are included
in the generated source bundle. No installed MSYS2 zlib library is selected.
The production runner installs a Windows Job Object memory ceiling before decode;
profile qualification is recorded separately with real fixtures on each runtime.
