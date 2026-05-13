# Rook Minimal FFmpeg Payload

This directory contains the validated Rook-owned minimal LGPL-only FFmpeg
binary used for generated-video sidecar extraction.

The binary is built from official FFmpeg source using:

- `scripts/ffmpeg/rook-ffmpeg-source.json`
- `scripts/ffmpeg/rook-ffmpeg-configure.txt`
- `scripts/ffmpeg/build-rook-ffmpeg.ps1`

Rook invokes `ffmpeg.exe` only as a subprocess. It does not link FFmpeg
libraries.

The matching source bundle is generated during release prep and published
beside the Rook installer. Release validation must be run with the generated
`rook-ffmpeg-source-bundle-manifest.json`.
