# Third-Party Notices

Rook is licensed under the [MIT License](LICENSE). The Rook plugins bundle and/or
dynamically link the following third-party components. This list covers the components Rook
ships or links directly; it is not an exhaustive enumeration of transitive dependencies.

## Open CASCADE Technology (OCCT)

The RookNative plugin uses **Open CASCADE Technology** (https://www.opencascade.com) for
exact B-rep adjacency (shared-face-area) computation. OCCT is licensed under the
**GNU Lesser General Public License, version 2.1**, together with the Open CASCADE
exception to the LGPL.

- OCCT is used **unmodified** and is **dynamically linked** (the plugin loads the OCCT
  `TK*` DLLs at runtime; OCCT is not statically folded into RookNative).
- The OCCT modeling-kernel DLL closure shipped with RookNative is the non-DataExchange
  subset (no STEP/IGES/XCAF). See `docs/rook_docs/occt-build.md` for the measured closure.
- LGPL-2.1 text: https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html
- OCCT licensing + exception: https://dev.opencascade.org/resources/licensing

If you received Rook in binary form, the corresponding OCCT source (and any OCCT
modifications, of which Rook makes none) is available from the Open CASCADE project at the
URL above, satisfying the LGPL-2.1 §6 relinking allowance via dynamic linking.

## openNURBS / Rhino SDK

RookNative builds against **openNURBS** and the **Rhino SDK** provided by Robert McNeel &
Associates as part of Rhino 3D, under McNeel's SDK license terms.

## FFmpeg

The bundled FFmpeg binary is covered by its own notice — see
[third_party/ffmpeg/NOTICE.FFmpeg.txt](third_party/ffmpeg/NOTICE.FFmpeg.txt).

## Other bundled components

- `third_party/prime-agent` — Prime agent runtime, MIT (see `third_party/prime-agent/LICENSE`).
- `src/RookNative/vendor/httplib`, `src/RookNative/vendor/nlohmann` — MIT (see the notices in each directory).
- `src/Rook/UI/Vision/Resources/fonts` — SIL Open Font License 1.1 (see `SOURCES.md` there).
- Python wheels installed by the release runtime carry the licenses recorded in the release
  license/provenance manifests.
