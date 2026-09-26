# OCCT Build & Deploy (RookNative exact-adjacency engine)

> Status (2026-06-15): **Task 9a done** — build parameterized on `$(OcctRoot)`, runtime DLL
> closure trimmed + measured, LGPL attribution added. **Task 9b (pin OCCT 7.9.3) is DEFERRED**
> (see below). The currently shipped + live-verified OCCT is **V8_0_0**.

## What RookNative links

RookNative's exact-adjacency engine (`Rook::occt::OcctAdjacencyEngine`) uses the OCCT
**modeling kernel only** — surface/curve geometry + boolean `Common` for shared-face area.
**No DataExchange (STEP/IGES/XCAF)** is linked or loaded: the STEP oracle was computed once,
offline, in Python; no C++ TU includes a `STEPControl_*`/DataExchange header.

### `$(OcctRoot)` (build parameterization)

Both `RookNative.vcxproj` and `OcctPrimitiveTests.vcxproj` resolve OCCT via the `OcctRoot`
MSBuild property:

1. `/p:OcctRoot=<path>` on the msbuild command line, else
2. the `OCCT_ROOT` environment variable.

There is no hardcoded fallback in the project files. A missing OCCT root fails
the build with a clear MSBuild error.

Include path = `$(OcctRoot)\inc`; lib path = `$(OcctRoot)\win64\vc14\lib`.

### Link list (non-DataExchange modeling closure)

`AdditionalDependencies`: `TKernel TKMath TKG2d TKG3d TKGeomBase TKGeomAlgo TKBRep TKTopAlgo
TKPrim TKBO TKBool TKShHealing TKMesh`. Dropped vs. the Spike-G tracer:
`TKDESTEP TKXSBase TKDE TKDECascade TKCAF TKLCAF TKXCAF TKCDF TKExpress` (all DataExchange/XCAF).

### Measured runtime DLL closure (deploy this next to RookNative.rhp)

`dumpbin /DEPENDENTS` transitive closure of `RookNative.rhp` (OCCT V8_0_0), **11 DLLs ≈ 20.6 MB**
(down from the 23-DLL/34.4 MB STEP-path closure). No `tbb*.dll` (this OCCT build has no TBB dep):

```
TKernel TKMath TKG2d TKG3d TKGeomBase TKGeomAlgo TKBRep TKTopAlgo TKPrim TKShHealing TKBO
```
(The linker references 9 directly; `TKGeomAlgo` + `TKPrim` are pulled in transitively. `TKBool`,
`TKMesh`, and DataExchange are linked-but-not-loaded → not in the runtime closure.)

Rhino loads these from **next to `RookNative.rhp`** in the plugin dir (no `AddDllDirectory`
needed — Spike-G finding). Deploy = copy the 11 DLLs from `$(OcctRoot)\win64\vc14\bin` into
`%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\` alongside the `.rhp`.

## Task 9b — pin OCCT 7.9.3 (DEFERRED, not skipped)

The production target is a **pinned, reproducible** OCCT release. The team's decision is
**7.9.3** (stable; avoids OCCT 8.0's master-tracking API churn we worked around). It is
deferred only because the build is a 30-60 min external compile and the migration was already
proven on the known-good V8_0_0.

When picked up:
1. **Do NOT switch the shared `<repos>/OCCT` checkout off `V8_0_0`.** Use a
   separate OCCT **source worktree** (or clone) at `V7_9_3`, built into a separate dir
   (e.g. `build-rook-793`). This keeps the verified V8_0_0 tree intact as a manual fallback.
2. `git fetch` the `V7_9_3` tag (not present locally today), checkout in the worktree.
3. cmake **modeling modules only** (no DataExchange) → Release build.
4. Point `OCCT_ROOT` (or `/p:OcctRoot=`) at `build-rook-793`; no vcxproj edit needed (already
   parameterized). Rebuild `RookNative.rhp`, re-measure the DLL closure (`dumpbin`), update the
   numbers above.
5. Re-run the live verification (Task 10) on the 7.9.3 artifact.
6. Re-pin `third_party/occt/occt-provenance.json` (commit, file-listing digest, recipe,
   toolchain, DLL sha256 values), copy the new tag's `LICENSE_LGPL_21.txt` and
   `OCCT_LGPL_EXCEPTION.txt`, update the version in `NOTICE.OCCT.txt`, `SOURCE.OCCT.txt`,
   `installer/THIRD_PARTY_NOTICES.txt` and `THIRD_PARTY_NOTICES.md`, and rename the source
   bundle.

## Licensing and corresponding source (#598)

OCCT is LGPL-2.1 with the Open CASCADE exception, and RookNative links it
**dynamically**. The 11 DLLs above are installed beside RookNative together with the
licence, the exception, `NOTICE.OCCT.txt` and `SOURCE.OCCT.txt`
(`RookNative\notices\occt\`, plugins component).

### Build provenance (reconstructed)

`third_party/occt/occt-provenance.json` is the pin: tag `V8_0_0`, commit
`d3056ef80c9668f395da40f5fd7be186cae4501f`, the sha256 of the commit's full file listing,
the toolchain (VS 2022 17.8, MSVC 14.38.33130, x64, Release, shared), and the sha256 of each
shipped DLL. The configure recipe is `scripts/occt/rook-occt-configure.txt`.

This provenance was **reconstructed on 2026-09-26**, not recorded at build time. The
evidence:
- The DLLs installed by Rook 1.6.0 are byte-identical to `<OCCT>\build-rook\win64\vc14\bin`.
- The checkout's only reflog entry is the clone at the tag commit, its tree is clean, and no
  source file was modified after the clone.
- The recipe is read from that build directory's `CMakeCache.txt` and
  `CMakeCXXCompiler.cmake`.

**Limitation:** a clean tree and a clone-only reflog cannot exclude edits that were made
and reverted during the June build. No such edits are known.

### Source bundle, published with every release

Rook publishes the corresponding source **beside the installer**, as a separate download:
`rook-occt-8.0.0-source-bundle.zip` plus `rook-occt-source-bundle-manifest.json`. It is
never packaged inside the installer. `scripts/occt/rook_occt_bundle.py`:

- **`build`** refuses unless the tag still names the pinned commit. It archives that commit
  from a private bare clone with every line-ending conversion disabled; OCCT's
  `.gitattributes` sets `eol=crlf` on some files, and a plain `git archive` on a
  `core.autocrlf=true` machine would rewrite them. It then adds the recipe, provenance,
  licences and this document, and writes a deterministic zip and its manifest.
- **`validate`** fails closed on any of these:
  - a DLL in the exact `OcctRuntimeRoot` passed to ISCC differs from its pinned hash;
  - the `.iss` ships a different DLL set;
  - a licence text differs from its pin;
  - a notice isn't installed with the plugins component;
  - the bundle's bytes, commit or members differ;
  - any source file differs from the pinned commit. It recomputes every file's git blob
    hash and mode from the archive and checks the listing digest, independently of git.

The release validator (`scripts/validate-release-artifacts.ps1`) binds the published
bundle file to the provenance commit and records its sha256 in the release manifest.

**Why not a written offer?** LGPL-2.1 §6(c) also allows accompanying the binaries with a
written offer to supply the source. That offer has to stay valid for at least three years
and be fulfilled on request, which is an ongoing administrative commitment. Publishing the
source next to every binary download (§6(d), and §4's "equivalent access to copy the
source code from the same place") avoids it. Recipients are not required to download the
bundle.
