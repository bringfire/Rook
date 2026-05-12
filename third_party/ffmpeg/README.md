# Bundled FFmpeg Payload

Rook bundles a vetted LGPL-only Windows `ffmpeg.exe` so generated-video
`poster`, `start_frame`, and `end_frame` sidecars work without user setup.

This payload is third-party software. Rook invokes `ffmpeg.exe` as a subprocess
and does not link FFmpeg libraries.

Release packaging must run `scripts\validate-ffmpeg-bundle.ps1` before building
the installer. The release guard must fail closed if:

- `ffmpeg-provenance.json` is missing or malformed;
- `ffmpeg.exe` is missing;
- the binary checksum does not match metadata;
- `ffmpeg.exe -version` cannot be read;
- the configure line is missing;
- the configure line contains `--enable-gpl`;
- the configure line contains `--enable-nonfree`;
- the dependency manifest does not cover the bundled binary's enabled
  configure flags;
- compliance files are missing;
- the bundled binary cannot extract poster, first-frame, and last-frame JPEGs
  from the smoke fixture.

Development builds may use PATH/configured FFmpeg. Release validation may not.
