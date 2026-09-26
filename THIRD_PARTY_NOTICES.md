# Third-Party Notices

Rook is licensed under the [MIT License](LICENSE). The Rook plugins bundle and/or
dynamically link the following third-party components. This list covers the components Rook
ships or links directly; it is not an exhaustive enumeration of transitive dependencies.

## Open CASCADE Technology (OCCT)

The RookNative plugin uses **Open CASCADE Technology** (https://www.opencascade.com) for
exact B-rep adjacency (shared-face-area) computation. OCCT is licensed under the
**GNU Lesser General Public License, version 2.1**, together with the Open CASCADE
exception to the LGPL.

- OCCT **8.0.0** (tag `V8_0_0`, commit `d3056ef80c9668f395da40f5fd7be186cae4501f`) is
  **dynamically linked**: RookNative loads 11 OCCT `TK*` DLLs from its plug-in folder at run
  time, and they can be replaced with another build of a compatible OCCT version.
- The shipped DLLs were built from that commit with no known source modifications. Their
  sha256 values, the build recipe and the toolchain are pinned in
  [`third_party/occt/occt-provenance.json`](third_party/occt/occt-provenance.json). That
  provenance is **reconstructed** from the build directory that produced the DLLs; the file
  records the evidence and its limitation.
- The LGPL-2.1 text and the Open CASCADE exception, verbatim from `V8_0_0`, are in
  [`third_party/occt/`](third_party/occt/) and are installed beside the DLLs
  (`RookNative\notices\occt\`).
- **Corresponding source:** every Rook release publishes `rook-occt-8.0.0-source-bundle.zip`
  beside the installer on the same release page. It contains the source at the pinned commit
  (verified byte for byte against that commit's file listing), the build recipe, the
  provenance and the licence texts. See `docs/rook_docs/occt-build.md`.
- The shipped closure is the non-DataExchange modeling subset (no STEP/IGES/XCAF); see
  `docs/rook_docs/occt-build.md` for the measured closure.

## openNURBS / Rhino SDK

RookNative builds against **openNURBS** and the **Rhino SDK** provided by Robert McNeel &
Associates as part of Rhino 3D, under McNeel's SDK license terms.

## FFmpeg

The bundled FFmpeg binary is covered by its own notice — see
[third_party/ffmpeg/NOTICE.FFmpeg.txt](third_party/ffmpeg/NOTICE.FFmpeg.txt).

## Other bundled components

- `third_party/prime-agent` — Prime agent runtime, MIT (see `third_party/prime-agent/LICENSE`).
- `src/RookNative/vendor/httplib` (cpp-httplib 0.18.3, with local changes listed in
  `ROOK-PATCHES.md`) and `src/RookNative/vendor/nlohmann` (nlohmann/json 3.11.3) — MIT. Their
  upstream licence files are `LICENSE` and `LICENSE.MIT` in those directories, and are
  installed under `RookNative\notices\`.
- `src/Rook/UI/Vision/Resources/fonts` — SIL Open Font License 1.1 (see `SOURCES.md` there).
  The fonts are embedded in `Rook.rhp`; their licence texts and `SOURCES.md` are installed under
  `RookNative\notices\fonts\`.

The installed product carries an index of every notice and its installed location:
`%LOCALAPPDATA%\Rook\app\THIRD_PARTY_NOTICES.txt` (source: `installer/THIRD_PARTY_NOTICES.txt`).
- Python wheels installed by the release runtime carry the licenses recorded in the release
  license/provenance manifests.
