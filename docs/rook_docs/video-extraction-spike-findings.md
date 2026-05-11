# Local MP4 Extraction Spike Findings

Date: 2026-05-11

## Fixture Policy

No MP4 fixture or ffmpeg binary is committed. The spike used a local MP4 path supplied by the runner or discovered from the local Rook artifact store.

## Environment

- OS: Microsoft Windows NT 10.0.26200.0
- .NET runtime: 4.0.30319.42000

## Input

- Input path shape: `...\1a7d8199-de75-4916-8846-53e980ac2514\video.mp4`
- Input exists: `True`
- Input bytes: `24292471`

## ffmpeg Discovery

- Success: `True`
- Source: `PathLookup`
- Error code: ``
- Resolved path shape: `...\bin\ffmpeg.exe`
- Message: Resolved ffmpeg.exe from PathLookup.

## Extraction Result

- Success: `True`
- Command/API shape: `"<FFMPEG_EXE>" -hide_banner -y -ss 00:00:00.100 -i "<INPUT_MP4>" -frames:v 1 -q:v 2 "<OUTPUT_IMAGE>"`
- Exit code: `0`
- Error code: ``
- Output path shape: `...\video-extraction-spike\poster-candidate.jpg`
- Output exists: `True`
- Output dimensions: `1920x1080`
- Elapsed ms: `1437`
- Diagnostic summary: Input #0, mov,mp4,m4a,3gp,3g2,mj2, from '<INPUT_MP4>':    Metadata:      major_brand     : isom      minor_version   : 512      compatible_brands: isomiso2avc1mp41      encoder         : Lavf58.76.100    Duration: 00:00:14.92, start: 0.000000, bitrate: 13028 kb/s    Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(progressive), 1920x1080, 13025 kb/s, 24 fps, 24 tbr, 12288 tbn (default)        Metadata:          handler_name    : VideoHandler          vendor_id       : [0][0][0][0]  Stream mapping:    Stream #0:0 -> #0:0 (h264 (native) -> mjpeg (native))  Press [q] to stop...

## WMF Feasibility

WMF was not implemented as code in this spike. The feasibility review remains documentation-level: using WMF from the managed companion would require new interop or package work and careful COM/threading design, while the ffmpeg external-process path keeps decoding out of the Rhino UI process and is directly testable from managed code.

## Failure Observations

- Missing ffmpeg is represented as a structured binary-discovery failure.
- Missing input fails before process start.
- Process-start failure is represented as a structured extraction failure for invalid or non-executable configured paths.
- Nonzero exit, timeout, missing output, and invalid image output are covered by unit tests.

## Recommendation

Use ffmpeg as the production extraction path candidate, invoked as a replaceable external process. Keep packaging, LGPL-build selection, notices, and source-compliance work in a later slice.
