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
6. Update `THIRD_PARTY_NOTICES.md` if the OCCT version string changes.

## Licensing

OCCT is LGPL-2.1 + the OCCT exception, used unmodified + **dynamically linked**. See
`THIRD_PARTY_NOTICES.md`.
