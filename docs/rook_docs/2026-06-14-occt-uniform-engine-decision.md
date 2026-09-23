# Spatial Adjacency — Uniform-OCCT Engine Decision & Spike Campaign

> **⚠ Extraction note (Slice A, `feature/occt-adjacency-engine`):** On this clean OCCT extraction
> branch the shipping engine is **OCCT-only**. The Clipper2 vendor code (`vendor/clipper2/`) and the
> legacy `PlanarAdjacencyEngine` that the text below describes as "vendored/shelved" were **pruned**
> from this branch (archived on `feature/spatial-intelligence`); the `IExactAdjacencyEngine` seam is
> retained. Mentions of Clipper2 are historical Gate-4 context.

> **Status (2026-06-14): DECISION MADE and EMPIRICALLY VALIDATED end-to-end (lab + in-plugin).**
> Adopt a **uniform OCCT adjacency engine** behind the existing pluggable seam.
> Spikes A–E (Python/OCP on real geometry) + Spike G (OCCT linked & running inside
> RookNative) all PASS. Remaining = bounded engineering, not open questions.
> Nothing merged to `main`. All work on branch `feature/spatial-intelligence`
> (worktree `<repos>/rook-spatial`).

---

## 0. START HERE (fresh-instance resume guide)

**What this is:** the decision record + evidence + reproduction guide for replacing
Rook's hand-rolled planar adjacency engine (Gate 4) with a single OCCT-based engine
that handles planar + curved + open + closed geometry uniformly.

> ## ✅ RESOLVED (2026-06-15) — the in-Rhino heisenbug was an ODR VIOLATION. Root-caused by inspection, fixed by a namespace, live + offline verified. The long debug saga below is kept for the record but is SUPERSEDED by this block.
>
> **Root cause:** the **legacy** `ExactAdjacencyTypes.h` and the **new** `OcctAdjacencyTypes.h`
> each define structs with the SAME names directly in `namespace Rook`
> (`ExactEdge` / `ExactCandidate` / `ExactAdjacencyCore` / `Capability` / `FacePair`) with
> **different layouts** (the new `ExactEdge` adds a `std::vector<FacePair> facePairs` →
> 128 bytes vs the legacy 104). Both are linked into `RookNative.rhp`
> (`SceneGraphHandler.cpp` uses the legacy contract for the production
> `/scene/graph/adjacency/exact` route; the engine + dev route use the new one). The C++
> mangled name of `std::vector<Rook::ExactEdge>::push_back/_Reallocate/~` depends only on
> the **type name**, not its layout, so the two instantiations collide and the linker
> (aggressively under `/GL`/LTCG COMDAT-folding) keeps ONE — the engine then drives the
> vector with the **wrong element stride**, advancing `_Mylast` incorrectly → dropped edge
> (`edges=4`) + heap/`_Mylast` corruption → teardown crash. Classic cross-TU **ODR UB**,
> which is exactly why every optimizer / thread / stack-layout / executor change *moved*
> the symptom instead of fixing it.
>
> **Why only `core.edges` (not `core.candidates`):** `ExactCandidate` is byte-identical (40)
> in both headers; `ExactEdge` differs by 24. **Why ASan-clean offline:** the offline harness
> never links the legacy TU, so only one `ExactEdge` exists there — no collision.
>
> **The earlier "ODR refuted" claim was INVALID** (see the "sizeof probe ... IDENTICAL"
> and "ODR/ABI layout mismatch REFUTED" notes below): that probe compared the **engine TU**
> vs the **validate-handler TU**, and **both include the NEW header** (`OcctAdjacencyTypes.h`),
> so by construction it could only ever print identical sizes. It never compared the **legacy**
> `Rook::ExactEdge` (104) against the new one (128). ODR was never actually tested, let alone refuted.
>
> **Fix:** move the entire new OCCT contract into a dedicated nested namespace **`Rook::occt`**
> (types + constants + `CapabilityToString` + `IExactAdjacencyEngine` + the engine class), so
> `std::vector<Rook::occt::ExactEdge>` has a DISTINCT mangled name and both contracts coexist
> until Task 8 strips the legacy one. Consumers (`OcctAdjacencyEngine.{h,cpp}`,
> `OcctSharedFaceArea.cpp` [`CapabilityToString` only; `SharedFaceArea` stays in `Rook`],
> `OcctAdjacencyValidateHandler.cpp` via `namespace ro = ::Rook::occt;` + explicit qualification,
> `occt_offline_repro.cpp`) updated. `OcctPrimitiveTests.cpp` unchanged (uses only `Rook::SharedFaceArea`).
>
> **Verification (production shape — stack `core` + `OcctExecutor::Instance().Run`, Release `/O2 /GL`):**
> live `POST /scene/occt_validate_adjacency` (`08d4dedf` × 5 abutments) = **8/8 runs, 5/5 exact edges**
> (3311.978 / 5440.438 / 5423.437 / 1040.005 / 1055.000 in²), Rhino survives, no trace recreated
> (probes removed). Offline: `OcctPrimitiveTests` 17/17 PASS; `OcctOfflineRepro` (ASan) `edges=5`, clean.
>
> **All diagnostics from the saga were reverted** (heap-`core`, inline-bypass, `/GL`-off-this-TU,
> `OcctTrace`/`_heapchk`/sizeof/EDGE-PUSH/handler-split probes). The `GetCV`→`ControlPoint`
> change (`360ba57a`) was kept (genuine improvement). Task 8 strips the legacy engine-contract
> types — at which point the ODR hazard is gone, but **`Rook::occt` is KEPT permanently**
> (user decision): it's cheap insurance and an explicit ownership boundary. Do NOT flatten it back into bare `Rook`.
>
> ### ✅ PRODUCTION INTEGRATION DONE (2026-06-15) — Tasks 8 / 9a / 10 shipped on `feature/spatial-intelligence`
> - **Task 8** (`5c233641`): production route `/scene/graph/adjacency/exact` flipped from the legacy
>   Clipper `PlanarAdjacencyEngine` to `Rook::occt::OcctAdjacencyEngine`. `ExactAdjacencyService` now
>   extracts move-only `ObjectBrepPayload`s and runs the OCCT shared-face engine; `ExactAdjacencyTypes.h`
>   stripped to broad-phase query types (legacy engine/result types deleted → ODR hazard gone at the source);
>   3 dev routes + `PlanarAdjacencyEngine` + `OcctAdjacencyValidateHandler` retired; `OcctProbe` reduced to
>   the `OcctProbeInit` SE-translation installer (STEP probe removed → no STEP in any C++ TU). −988 LOC.
> - **Task 9a** (`1db747ad`): build productionized on the **verified V8_0_0** — `$(OcctRoot)` property
>   (OCCT_ROOT env override), trimmed non-DataExchange link list, **measured runtime closure = 11 TK DLLs /
>   20.6 MB** (no tbb), LGPL attribution (`THIRD_PARTY_NOTICES.md`), build doc (`docs/rook_docs/occt-build.md`).
>   **Task 9b (pin OCCT 7.9.3) is DEFERRED** (documented; use a separate OCCT worktree/build dir, do NOT switch
>   the shared checkout off V8_0_0).
> - **Task 10** (`d28c36bb`): live-verified the production route on `SpatialTest.3dm` with the **trimmed
>   11-DLL closure** — 5/5 abutments exact (3311.978/5440.438/5423.437/1040.005/1055.000 in²), 9 real edges,
>   `exact_brep` / `inches^2`, cache 50ms→1ms, Rhino stable; the trimmed closure is runtime-complete.
>   Verify script: `docs/rook_docs/occt-spike/live_verify_occt_adjacency.py`.
> - **NEXT:** Task 9b (7.9.3 pin, when chosen) + the graph slice **"Exact Adjacency Projection v1"** (project
>   the production `adjacent_exact` edges into the scene-graph/networkx mirror as typed IFC-aligned relationship
>   edges) — its own brainstorm → spec → plan; see `2026-06-14-spatial-graph-projection-design.md`.

**Read these first, in order:**
1. This doc (decision + spikes + numbers + remaining work).
2. `docs/rook_docs/2026-06-13-spatial-intelligence-foundation.md` (the gated roadmap; this supersedes its Gate-4 narrow-phase choice).
3. Memory: `project_spatial_intelligence_topology` (lineage), `project_gh_edit_deferred_solve` (unrelated), `project_freecad_bim_architecture` (kernel licensing matrix).
4. Gate 4 spec/plan: `docs/superpowers/specs/2026-06-14-gate4-exact-adjacency-design.md`, `docs/superpowers/plans/2026-06-14-gate4-exact-adjacency.md`.

**Verify branch before EVERY commit:** `git -C <repos>/rook-spatial branch --show-current` must print `feature/spatial-intelligence` (the primary `Rook` dir bounces between Codex worktrees; a prior commit once mis-landed).

**Immediate next work (the two strengtheners the user wants, then productionize):**
- **Strengthener 1 — direct converter** (`ON_Brep`→OCCT, off-disk, off-main-thread, ~15 MB footprint). Surface translation already proven; remaining = trims (pcurves→wire→`MakeFace`+`ShapeFix`) + face assembly.
- **Strengthener 2 — messier/varied-geometry coverage** (meshes/open polysurfaces/SubD/dirty → honest degradation; the "any user" guarantee).
- Then the **real `OcctAdjacencyEngine`** behind `IExactAdjacencyEngine`, the **build-system productionization** (pin 7.9.3, env-var paths, deploy subset), and **Spike F** (construction tier → zones).

> ### ⏩ EXECUTION PROGRESS (2026-06-15) — engine build underway, branch `feature/spatial-intelligence`
> Spec + plan written and reviewer-gated: `docs/superpowers/specs/2026-06-15-occt-adjacency-engine-design.md`, `docs/superpowers/plans/2026-06-15-occt-adjacency-engine.md` (the live task list — RESUME FROM THE PLAN). Executing subagent-driven (Phase 1 additive → Phase 2 single integration commit). **Test venue decision: IN-PLUGIN** (dev route `POST /scene/occt_validate_converter` vs precomputed STEP-oracle constants; no standalone openNURBS console; no STEP in any C++ binary — oracle computed once offline via Python OCP).
> - **Task 1 ✅** `Rook::Legacy` engine freeze (`32a594be`). **Task 2 ✅** `OcctAdjacencyTypes.h` contract — 4-state `Capability`, move-only `ObjectBrepPayload`, structured `FacePair`/`facePairs`, `kEngineVersion=2` (`c2104bd2`).
> - **Task 4 ✅** `ON_Brep`→OCCT converter (surfaces) + dev route (`f88ef105`), live-validated.
> - **Task 5 ✅ — STRENGTHENER 1 IS NOW PROVEN IN C++** (`4e227975`). The trim/pcurve/orientation converter matches the STEP oracle **machine-exact across 8 real fixtures**: planar wall `71065f57` relErr 5.8e-13, **curved/periodic wall `7d55840d` 1.0e-11**, open floorplate 1.0e-8, Triage/I-WALL/sliver all <1.3e-7; every face converted, zero failures. This is the faithful trimmed-face proof the prior Python spike could NOT produce (rhino3dm exposes no pcurves).
>   - **Key converter insight (do not "fix"):** when building OCCT edges FROM openNURBS 2D pcurves, **do NOT apply `ON_BrepTrim::m_bRev3d`** — it is the 2d-pcurve-vs-3d-edge relationship, not loop traversal; the pcurve is already loop-oriented (outer CCW / inner CW in param space), so applying it double-accounts and inverts wires. Apply `ON_BrepFace::m_bRev` only at the face level (matches OCCT face normal to the ON_Brep oriented normal; doesn't change area). Vindicated by the machine-exact oracle.
>   - **Build/linkage finding:** an OCCT-only TU (NotUsing-PCH, no `RhinoSdk.h`) that includes `opennurbs.h` must `#define OPENNURBS_IMPORTS` first (makes `ON_` classes `dllimport`, matching `opennurbs.lib`) or LNK2005 on template instantiations. openNURBS headers live under `$(RhinoSdkDir)openNURBS`. OCCT 8.0 dropped the `TColgp_*`/`TopTools_*` aliases → use `NCollection_Array*`/`NCollection_List<TopoDS_Shape>`. Area scale = (length scale)² (inches → 645.16).
> - **Task 6 ✅ (code + offline matrix; in-plugin Evaluate validation pending deploy)** (`690d835b`). `OcctAdjacencyEngine::Evaluate` = serialized `Common(faceA,faceB).Area` over the converted faces, conservative bbox prefilter (`BRepBndLib`+`Enlarge(tol)`+`IsOut` — reviewer-confirmed never skips a touching pair), `facePairs` summing to edge `sharedArea`, capability rollup (ExactBrep/PartialExactBrep/Unsupported/Failed), `source:`/`cand:<id>:`/`engine:` diagnostics. **OCCT-only robustness matrix `OcctPrimitiveTests.exe` = 9/9 (17 checks) green** (abutting/gap/bridged/duplicate/interpenetration/far-origin/sliver/degenerate-rejected/curved-on-planar). Reviewer: SPEC PASS, QUALITY APPROVED.
>   - **Two architecture deviations (SOUND, load-bearing for Task 8):**
>     1. `OcctSharedFaceArea.cpp` — the OCCT-pure primitives (`SharedFaceArea` + `CapabilityToString`) split into their own TU compiled by BOTH the `.rhp` and the OCCT-only test, so the test links zero openNURBS (no offline-link conflict; single definition, no dup-symbol).
>     2. `Handlers/OcctAdjacencyValidateHandler.cpp` (route `POST /scene/occt_validate_adjacency`) — the dev Evaluate route lives in its OWN TU because the new `OcctAdjacencyTypes.h` and the legacy `ExactAdjacencyTypes.h` define the SAME `Rook::` names (`Capability`/`ExactEdge`/`ExactCandidate`/`ExactAdjacencyCore`/`FacePair`) → genuine ODR collision if combined. **This empirically PROVES Task 8 must strip the legacy engine-contract types from `ExactAdjacencyTypes.h` before the production handler can use the OCCT contract.** Until Task 8, the two type-worlds are kept in separate TUs.
>   - Minor nits (fix on next touch, non-blocking): duplicate `<ClInclude OcctAdjacencyTypes.h>` in `RookNative.vcxproj`; `FaceBox`'s `BRepBndLib::Add` not individually try-wrapped (route catch-all backstops it — document `Evaluate`'s exception contract if ever called outside a handler).
> ### ✅ ROOT-CAUSE NAILED via flush-trace + heap probe (2026-06-15, latest) — STACK/MEMORY CORRUPTION of the `core` object during source conversion. NOT OCCT geometry, NOT exceptions, NOT threading, NOT heap.
> Per-line flush trace (`%TEMP%/rook_occt_trace.log`, code in `OcctAdjacencyEngine.cpp` — commits `f694e7e5`/`55ed2d2f`, **REMOVE these probes once fixed**) on the real route (`08d4dedf` × 5 abutments) gave, repeatably:
> ```
> ENTER Evaluate ncand=5 srcHasBrep=1
> convert SOURCE begin
> convert SOURCE done faces=10 failed=0 HEAPCHK=-2(OK)        <- heap intact, source converts fine
> cand[0] begin hasBrep=1
> cand[0] preflight HEAPCHK=-2(OK) objId.size=36 candidates.cap=18446740579734284492   <- CORE STOMPED
> cand[0] before push_back                                     <- crashes IN push_back
> ```
> **Findings (evidence, not theory):** (1) `_heapchk()` returns `_HEAPOK` both before and after source conversion → **heap is NOT corrupted**. (2) `cand.objectId.size()==36` → the candidate string is **valid** (Copilot's "objectId corrupted" was wrong). (3) **`core.candidates.capacity()` reads garbage (≈2⁶⁴)** even though `core` is a freshly value-constructed stack local with nothing pushed → **`core` (stack object) has been memory-corrupted**, its `candidates` vector's internal pointers stomped. (4) `push_back` then trusts the garbage capacity → fault; the `0xC0000409` subcode **7** = `FAST_FAIL_FATAL_APP_EXIT` (`std::terminate`) reached via the C++ EH machinery (`__GSHandlerCheck_EH4`) once the smashed `core` makes a `std::` op throw and unwinding fails.
> **Window:** the corruption happens between `core`'s construction and the `cand[0]` preflight — i.e. **during the (Release-inlined) source `ConvertBrepFaces` region**. The converter's array code was **inspected and is correctly sized** (`ToOcctSurface`/`ToOcct2dCurve`/`BuildLoopWire` — all `NCollection`/`std::vector` heap-backed, sized to `.size()`, `ON_4dPoint` by value; no fixed-size stack buffer found). So the corrupting write is NOT obvious from inspection.
> **Why it never showed before:** offline proofs used STEP-read faces / the OCCT-only primitive matrix — neither exercises `ExactAdjacencyCore` + the converter together in one frame. Task 5 converted single objects (different stack layout) and only read AREA, so the stomp landed benignly.
> **DECISIVE NEXT STEP (do this, not more probe/deploy cycles):** build the converter path with **AddressSanitizer** (`/fsanitize=address` on the OCCT TUs, or — cleaner — in the standalone offline openNURBS harness running `Evaluate` on the real `ON_Brep`s) and run it once. ASan names the exact out-of-bounds write (file:line) immediately. Candidate areas to scrutinize under ASan: the `ON_4dPoint cp = ns.ControlPoint(i,j)` / `nc.GetCV(i, cp)` calls (does openNURBS write more than expected into `cp`?), `OcctFaceSet::Impl`/`OcctFaceAt` slot indexing, and any ABI/ODR subtlety from the per-file OCCT compile flags (`/EHa`, NotUsing-PCH) vs the PCH TUs (verify `_ITERATOR_DEBUG_LEVEL`/CRT consistency so `std::vector<ExactCandidate>` has one layout across all TUs). Then a likely one-line fix.
> **Deployed build = the trace/heap-probe build (`55ed2d2f`).** Remove the `OcctTrace`/`_heapchk` probes from `OcctAdjacencyEngine.cpp` once the corruption is fixed.
>
> **ELIMINATED so far (tested, not assumed):**
> - **Codex's `GetCV` lead — REFUTED (`360ba57a`).** Swapped `ON_4dPoint cp; nc.GetCV(i,cp)` → `ON_4dPoint cp = nc.ControlPoint(i)` in `ToOcct2dCurve` (good change, kept). Crash IDENTICAL — `core.candidates.cap` still garbage at `cand[0]` preflight. Not the corruptor.
> - **ODR/IDL container-layout mismatch — RULED OUT for the Release build.** `RookNative.vcxproj` Release = `NDEBUG` + `MultiThreadedDLL` (`/MD`) → `_ITERATOR_DEBUG_LEVEL=0` uniformly; no `_HAS_ITERATOR_DEBUGGING`/`_SECURE_SCL`/`#pragma pack` in `stdafx.h` or headers. The per-file OCCT TUs (`NotUsing` PCH) differ only by not including MFC/RhinoSdk — which doesn't change `std::vector`/`std::string` layout in Release. So `core.candidates` is NOT a cross-TU ABI artifact.
> - **The garbage capacity VALUE VARIES per run** (`…284492` then `…001794`) and is ≈2⁶⁴ (i.e. `_Myend_cap < _Myfirst` → negative pointer-diff → huge unsigned). That signature = a genuine **stack write of run-dependent data over `core.candidates`'s three pointers** during the inlined source `ConvertBrepFaces` — a real stack buffer overflow, just not in the GetCV loop or the (inspected, correctly-sized) poles/knots arrays.
> **ASan OFFLINE HARNESS RESULT (`1f45ba85`, `occt_offline_repro.cpp` + `OcctOfflineRepro.vcxproj`): NOREPRO + ENGINE EXONERATED + PROVEN CORRECT.** Built `/fsanitize=address /Zi /Od /MD NDEBUG` (GL off), compiling the REAL engine TUs, reading the real `SpatialTest.3dm` `ON_Brep`s, calling the real `Evaluate`. Ran CLEAN: **no ASan error**, `core` intact, and produced the **complete correct adjacency**: `71065f57`=3311.978, `5c12cc83`=5440.438, `be0ca730`=5423.437, `7e80db98`=1040.005, `26b2c012`=1055.000 in² — all 5 Spike-A abutments, exact. So the converter + `Common` + `Evaluate` are **memory-clean and correct**; the OOB write is NOT in the engine internals.
> **KEY:** the harness was `/Od`; the deployed plugin is Release **`/O2 /GL`**. The bug DISAPPEARED at `/Od`. ASan-clean at `/Od` ⇒ likely NOT a plain buffer overflow (redzones would catch it) ⇒ **optimization-sensitive UB** (strict-aliasing / use-after-scope / uninitialized-read→wild-write that `/O2` or `/GL`/LTCG exploits) OR a genuine Rhino-process-environment dependency. **NEXT EXPERIMENT (decisive, no Rhino):** rebuild the harness at `/O2` (keep ASan, GL off) and rerun — if it repros, ASan/UB names it; if `/O2`+ASan is still clean, try `/O2 /GL` ASan-OFF (matches the deployed build exactly) with the `OcctTrace` probes to see if `core` stomps offline. That bisects "our-code-UB-under-O2/GL" vs "Rhino-environment-specific."
>
> **`/O2` + `/O2 /GL /LTCG` OFFLINE (subagent `4ce66d80`): STILL NOREPRO.** Even at the EXACT deployed codegen the engine runs clean + correct (all 5 abutments, `core` cap probe sane `0,1,2,3,4`). So it is NOT optimization/LTCG-sensitive UB in our code. **`STATUS: RHINO_ENV` — the corruption only happens inside the Rhino process.**
> **Thread-stack hypothesis REFUTED:** `dumpbin /headers` shows Rhino.exe, the harness exe, AND `RookNative.rhp` all have an identical **1 MB** stack reserve (`0x100000`). The `OcctExecutor` worker gets the same stack offline and in-Rhino → not a stack-size overflow.
> **WHAT'S LEFT (Rhino-environment-only, can't repro offline):** the in-plugin path differs from the harness in exactly these ways — investigate THESE, not the engine:
>   1. **The `ON_Brep` comes from the LIVE `CRhinoDoc`** (`CRhinoObject::Geometry()`), not a file `ONX_Model`. A live-doc brep can carry cached render/analysis meshes, `ON_UserData`, or flags a file-deserialized brep lacks; the deep-copy `new ON_Brep(*b)` copies that state, and `ConvertBrepFaces`/openNURBS may walk it differently in-process.
>   2. **The main-thread dispatcher handoff:** in-plugin the brep deep-copy is made on Rhino's MAIN/UI thread (via `CMainThreadDispatcher`), returned through a `std::future` to the httplib worker, then read on the `OcctExecutor` worker — a 3-thread crossing vs the harness's 2. Possible openNURBS per-thread state / cross-module heap interaction.
>   3. Cross-module `operator new`/heap for the `ON_Brep` between the plugin, opennurbs.dll, and Rhino's CRT.
> **DEFINITIVE NEXT STEP (needs the LIVE Rhino process + a debugger — Codex's fallback):** attach VS to Rhino (or launch Rhino under VS), set a **DATA BREAKPOINT (write, 8 bytes ×3) on `core.candidates`'s `_Myfirst/_Mylast/_Myend` pointers** immediately after `core` is constructed in `Evaluate` (the deployed build `55ed2d2f` has the `OcctTrace` probes to hit the right spot), continue through the source `ConvertBrepFaces`, and the breakpoint fires AT the exact instruction that writes `core` — with the full call stack naming the culprit. That is the one thing that names it; the offline route cannot (proven 5×).
> ### 🧵 LIVE DEBUG SESSION RESULTS (2026-06-15, with user+Codex driving VS) — narrowed to an in-Rhino HEISENBUG in the Evaluate/OcctExecutor plumbing. NOT layout/ODR, NOT the engine math.
> Methodically eliminated, each by test:
> - **VS data breakpoint** on `core.candidates._Myfirst/_Mylast/_Myend` (needed Just-My-Code OFF + NATIVE attach + `RookNative.pdb`): at `/O2` `core` is optimized away (unwatchable). Built `/Od`-for-this-TU-only (`806ab060`) to make `core` watchable → the data breakpoint then fired only in **normal teardown** (`~ExactAdjacencyCore`), i.e. **`/Od` = NOREPRO** (clean run).
> - **Non-perturbing `/O2` bracket probe** (`c2dcbc75`, logs `core.candidates.capacity()`+`data()` at ENTER / post-source / cand[0]): **`core.candidates` is GARBAGE AT CONSTRUCTION** — `cap≈2^64`, `data=` a *module address* (`00007FF9…`), BEFORE `ConvertBrepFaces` or anything. So nothing "writes" it at runtime; it's wrong from the start.
> - **`sizeof` probe, engine TU vs handler TU** (`52158c77`): **IDENTICAL** (Core=192, vec=24, string=32, ExactCandidate=40). → **ODR/ABI layout mismatch REFUTED.** Not packing, not container-ABI. **⚠️ INVALID — see the RESOLVED banner at the top of §0:** both of those TUs include the NEW `OcctAdjacencyTypes.h`, so this probe could only ever print identical sizes. The real collision is the NEW `Rook::ExactEdge` (128) vs the LEGACY `Rook::ExactEdge` (104) in `SceneGraphHandler.cpp`/`ExactAdjacencyTypes.h`, which this probe never compared. ODR was the cause all along.
> - **`/O2` + `/GL`-off for the engine TU** (`dd07bfc4`): the hard crash mostly stops — `Evaluate` now **completes** (`LOOP DONE`) like `/Od`, BUT still **`edges=4` not 5** (all 5 candidates compute correct areas — 3311.978/5440.438/5423.437/1040.005/1055.000 — yet one `core.edges.push_back` is silently dropped) AND an **intermittent** post-completion error/crash (two identical fires → HTTPError then ConnectionReset).
> **PATTERN ⇒ HEISENBUG:** severity scales with optimization (`/O2/GL`→garbage-at-construction→crash; `/GL`-off/`/Od`→completes but drops one `core.edges` element + intermittent), **in-Rhino-only** (offline harness clean at every opt level — but it's a *different binary* that never compiled the PCH handler TU), **ASan-clean**, **intermittent**. That fingerprint = a **race or lifetime UB** in the `OcctAdjacencyEngine::Evaluate` → `OcctExecutor::Run` → `std::packaged_task<ExactAdjacencyCore()>` → `[&]`-lambda → worker-thread path (or a genuine LTCG miscompile of it).
> **NEXT EXPERIMENTS (fresh session — do NOT deploy-guess further at depth):**
>   1. **Executor-bypass isolation (decisive, cheap):** temporarily run `Evaluate`'s body INLINE (name the lambda, call it directly) instead of via `OcctExecutor::Instance().Run(...)`, at full `/O2 /GL`. If `core` is then clean (5 edges, no crash) → the bug is in the `OcctExecutor::Run`/`packaged_task`/thread-hop plumbing (a small, reviewable unit — scrutinize the `[&]` capture lifetimes, the `packaged_task<ExactAdjacencyCore()>` result move across threads, and whether the handler truly blocks for the whole worker run). If `core` still corrupts inline → it's the engine body under `/O2`-in-Rhino.
>   2. **ThreadSanitizer / careful review** of the 3-thread handoff (httplib worker → `CMainThreadDispatcher` main-thread extraction → `OcctExecutor` worker), looking for a data race on `core`/the shared state or a dangling `[&]` capture.
>   3. If it's a miscompile: the `/GL`-off-this-TU mitigation already halves it; a full fix may be restructuring `Evaluate` to NOT return `ExactAdjacencyCore` by value through `packaged_task` (use an out-param / `shared_ptr<ExactAdjacencyCore>`), or not wrapping the whole body in the executor lambda.
> **DEPLOYED BUILD = `dd07bfc4`** (`/O2` + `/GL`-off engine TU + all the `OcctTrace`/`_heapchk`/`sizeof` probes + the handler sizeof probe). **REVERT all of these once root-caused:** the `/Od`/`/GL`-off vcxproj flags, the probes in `OcctAdjacencyEngine.cpp` + `OcctAdjacencyValidateHandler.cpp`, and the GetCV note.
>
> **HEADLINE: the OCCT adjacency ENGINE IS DONE + CORRECT** (offline: 3311.978/5440.438/5423.437/1040.005/1055.000 in² — all 5 user-confirmed abutments, exact, memory-clean). Only the in-Rhino integration crash remains, and it gates Task 8 (the production path runs `Evaluate` on the executor thread the same way). Cleanup pending: remove `OcctTrace`/`_heapchk` probes (`55ed2d2f`) + the GetCV note once fixed; `git prune` (housekeeping). **AddressSanitizer is now the required tool** — it names the exact write in one run. Preferred venue: a **standalone offline openNURBS harness** (`ONX_Model::Read` SpatialTest.3dm → `ON_Brep`s → `OcctAdjacencyEngine().Evaluate(...)`) built with `/fsanitize=address`, run outside Rhino. (Task 4 already solved standalone-openNURBS linking: `OPENNURBS_IMPORTS` + `$(RhinoSdkDir)openNURBS`.) Then a likely one-line fix, remove probes, re-validate.
>
> ### ⚠️ (EARLIER, SUPERSEDED) DIAGNOSIS (2026-06-15) — the crash is a `std::terminate`/fail-fast, NOT an access violation. The SE-translation hypothesis below was WRONG.
> **Windows Event Log (Application Error / WER BEX64) on every crash: exception `0xC0000409` faulting in `ucrtbase.dll`** — that is a **fail-fast / `std::terminate` / CRT `_invalid_parameter`**, NOT `0xC0000005` (access violation). **Both the pre-executor build (`08118ba2`) and the post-executor build (`8d17ce4c`) crash with the SAME fault bucket `2285818568978638468`** → the crash is unaffected by `OSD::SetSignal`/per-thread translation AND by the executor. So:
> - The "per-thread SE-translation gap" hypothesis was **incorrect** (that explains 0xC0000005, not 0xC0000409). `OcctExecutor` (`8d17ce4c`) was built on it; it's a reasonable architectural improvement (off-UI-thread + serialization) so it's KEPT, but it is NOT the fix and is unproven-necessary until the real cause is found.
> - **The terminate is in the path COMMON to both builds**: `OcctAdjacencyEngine::Evaluate`'s narrow phase (multi-object `ConvertBrepFaces` + face-pair `SharedFaceArea` + `FacePair`/diagnostics assembly) and/or `OcctAdjacencyValidateHandler`'s 6× main-thread `ExtractPayload`. The prefilter is ALREADY removed (`08118ba2`) and it still crashed → NOT the prefilter.
> - **Why it doesn't reproduce offline:** the offline proof (3311.978 in², 0 faults) used STEP-read `TopoDS` faces fed straight to `Common` — it BYPASSES the `ON_Brep`→converter→`OcctFaceSet`→`OcctFaceAt`→engine C++ path. The terminate is somewhere in THAT path (or the handler), not in `Common` itself.
> - **0xC0000409 root-cause candidates (terminate/fail-fast):** an exception escaping a `noexcept` boundary (a destructor, a move ctor, a `std::thread`/`packaged_task` function); a `Standard_Failure` (which does **NOT** derive from `std::exception`) reaching a `noexcept`/`std::thread` boundary or a `catch(std::exception)`-only site then re-thrown into terminate; a CRT `_invalid_parameter` fail-fast (bad arg to a checked CRT call, e.g. a bad index/iterator); a pure-virtual call.
> - **CONCRETE NEXT-SESSION DIAGNOSTIC PLAN (do this BEFORE any more code changes — no more deploy-cycle guessing):**
>   1. **Read the crash dump's call stack.** WER saved dumps under `C:\ProgramData\Microsoft\Windows\WER\ReportArchive\AppCrash_Rhino.exe_*` (the temp `WER.*.tmp.dmp` gets purged — grab the archived one promptly after a repro). No `cdb`/WinDbg is installed at the standard Windows Kits path — install "Debugging Tools for Windows" (WDK/SDK) or use Visual Studio to open the `.dmp`, then `!analyze -v` + `k` → the faulting frame names the FILE:LINE. THIS is the definitive step.
>   2. **OR build the standalone offline harness** (the one deferred earlier — now justified): a console exe linking openNURBS that `ONX_Model::Read`s `SpatialTest.3dm`, pulls the `ON_Brep`s for `08d4dedf` + the 5 candidates, and calls `OcctAdjacencyEngine().Evaluate(...)` directly — reproduces the terminate WITHOUT Rhino, under a debugger. (Use `OPENNURBS_IMPORTS` + `$(RhinoSdkDir)openNURBS` per Task 4's findings.)
>   3. **OR add per-step disk logging** in `Evaluate`/`ExtractPayload` (open+write+flush+close a log file before each phase: "extract src", "extract cand i", "convert src", "convert cand i", "pair si×ci") — the last flushed line before the crash pinpoints the step. Cheap, survives the hard crash.
> - **Live-validation deploy loop crashed Rhino 3× this session.** Do NOT resume blind fix→deploy→crash cycles. Diagnose first (dump stack or offline harness), THEN fix.
>
> ### 🛑 (SUPERSEDED HYPOTHESIS — kept for the record) TASK 6 IN-PLUGIN `Evaluate` — originally mis-diagnosed as an OCCT threading/signal bug. Engine LOGIC proven correct; do NOT touch the adjacency math.
> Three issues surfaced validating `POST /scene/occt_validate_adjacency` (floorplate `08d4dedf` × 5 abutment candidates) in-plugin — exactly why we validated before the Task-8 flip:
> 1. **AV in the bbox prefilter** (`BRepBndLib::Add` unguarded) → **FIXED `40442ba8`** (guard) then the prefilter was **removed entirely `08118ba2`** (it's an optional perf nicety per Spike B; the narrow phase is guarded).
> 2. **EDEADLK "resource deadlock would occur"** — under the default `/EHsc`, an OCCT `OSD::SetSignal`-translated fault skipped the `lock_guard` destructor → `s_engineMutex` left permanently locked → next pooled request relocked → deadlock. **FIXED `08118ba2`**: `/EHa` on all OCCT TUs (`OnBrepToOcct.cpp`/`OcctAdjacencyEngine.cpp`/`OcctSharedFaceArea.cpp`/`OcctProbe.cpp`/`SceneGraphHandler.cpp`) so translated faults unwind C++ destructors.
> 3. **HARD CRASH (process death, connection reset)** — STILL OPEN. A raw access violation on an httplib worker thread takes Rhino down with no catchable exception.
>    - **DEFINITIVE OFFLINE DIAGNOSIS (no Rhino):** running the exact floorplate×wall face-pair `Common` over the STEP fixtures via OCP gives **3311.978 in² (= Spike A's ~3312), 1 contributing pair, 0 faults.** So the OCCT geometry + `Common` + adjacency LOGIC are CORRECT. The crash is NOT geometry/logic — it is the **in-plugin OCCT signal-handling/threading architecture**.
>    - **ROOT-CAUSE HYPOTHESIS (high confidence):** `OSD::SetSignal`/`_set_se_translator` is **PER-THREAD on Windows**. The dev route installs it via `std::call_once` on only ONE httplib pool thread; a request served by a DIFFERENT pool thread has no SE translation → a raw AV (instead of a catchable `Standard_Failure`) → instant process death. (The `/EHa` fix only helps once translation is active on the thread.)
>    - **FIX DIRECTION FOR NEXT SESSION (don't deploy-cycle-guess — design it):** route ALL OCCT work through a **single dedicated, serialized OCCT worker thread** that calls `OSD::SetSignal` ONCE at thread start. This simultaneously: (a) installs SE translation on the only thread that runs OCCT (kills the hard crash), (b) provides the v1 serialization cleanly (no cross-thread `static` mutex → no stale-lock/EDEADLK class at all), (c) keeps OCCT off the Rhino UI thread. The handler posts a job to this thread and waits on a future. Alternatively (weaker): install `OSD::SetSignal` at the top of every OCCT-touching handler invocation (per-call, per-thread) — simpler but leaves serialization to the existing mutex. Prefer the dedicated-thread design. Also add **per-face-pair disk logging** (flush before each `Common`) if needed to pinpoint any residual faulting pair — but offline says there is none, so this is likely unnecessary.
>    - **STATUS:** Task 6 code committed (`690d835b`,`40442ba8`,`08118ba2`); offline matrix 9/9; converter proven (Task 5). The ONLY gap is the in-plugin OCCT-thread/signal architecture above. Tasks 7–10 should NOT start until this is fixed (Task 8 wires this same engine into the production route — the crash would follow it in).
>
> - **(superseded) earlier next-step note:** deploy/validate Task 6's in-plugin `Evaluate` (`POST /scene/occt_validate_adjacency`, source `08d4dedf` + abutment candidates → expect edge to wall `71065f57` ~3312 in², facePairs summing, `exact_brep`). Then **Task 7** (engine diagnostic propagation — mostly landed in the kernel; validate mesh/SubD→unsupported in-plugin), **Task 8** (single-commit Phase-2 integration: freeze-out old engine, STRIP `ExactAdjacencyTypes.h`, migrate service+handler to `ObjectBrepPayload`+OCCT engine + `fuzzMm`, retire Clipper+`occt_probe`+dev routes), **Task 9** (pin OCCT 7.9.3, `$(OcctRoot)`, dumpbin-measured DLL closure, LGPL), **Task 10** (live verify on the real `/scene/graph/adjacency/exact` route).
> - **Validation loop is deploy-cycled:** build writes to `bin/` (Rhino may stay open); deploy (`scripts/deploy-native.bat`) needs Rhino CLOSED; live route test needs Rhino OPEN on `SpatialTest.3dm (a local test model)`. Native port per-session — find via Rhino pid's listening port answering `/scene/graph/stats`. HTTP via Python `urllib`, never curl.

---

## 1. The decision and why

**Decision:** one **uniform OCCT engine** computes adjacency for all geometry classes
(planar/curved × closed/open) via identity-keyed coincidence
(`BRepAlgoAPI_Common(faceA,faceB).Area` over cross-object face pairs), behind the
**existing `IExactAdjacencyEngine` seam** built in Gate 4. The hand-rolled Clipper2
planar engine (`PlanarAdjacencyEngine`) is **shelved behind that seam** as a possible
*measured-later* planar accelerator — not deleted, not the default.

**Why uniform, not a planar/curved split (the "chimera" question):** OCCT enters the
plugin the moment curved geometry is supported (it must, for arbitrary users). So
uniform pays the OCCT cost *once* and covers all quadrants; a split *adds* a second
engine + a planar↔curved seam + two tolerance models for speed we don't need (the
path is lazy + cached). Going uniform also **deletes** the opposing-normal predicate
and the `IsSolid()` gate — the exact things that made the hand-rolled engine blind to
open geometry. The split's only benefit (planar speed) is unnecessary: Spike B shows
lazy queries are tens of ms and full batch is ~3.7 s.

**Why this is not seesawing:** the through-line is stable — the pluggable engine seam
(designed in Gate 4) is correct; only the *default implementation behind it* changed,
from Clipper2-planar to OCCT-uniform, decided by **measurement on real geometry**, not
argument. Gate 4 was the necessary Phase 1 that built the chassis and taught us the
problem shape (the `IsSolid` gate failing on open geometry, the four quadrants).

---

## 2. Architecture: keep / replace ledger

The Gate 4 service architecture is engine-agnostic chassis — almost all of it stays.

**KEEP (unchanged):**
- `CSceneGraph` — bbox-only, background-thread, `ON_RTree`, broad-phase only. **OCCT never enters the scene graph.**
- `CSceneGraph::QueryCandidatesAsync` (SceneGraph.cpp) — processor-thread, deterministic scored+capped candidate query. Any engine needs this broad phase.
- `ExactAdjacencyService` (SceneGraph/ExactAdjacencyService.{h,cpp}) — orchestration + cache (key incl. graphSequence+engineVersion, drop-on-sequence-advance) + the three-thread-hop discipline.
- `IExactAdjacencyEngine` seam (SceneGraph/PlanarAdjacencyEngine.h) — the swap point.
- HTTP route `POST /scene/graph/adjacency/exact` + response DTO (SceneGraphHandler.cpp).
- Test fixtures/expected areas (re-point at the OCCT engine as its correctness spec).
- Clipper2 vendor code + legacy `PlanarAdjacencyEngine` — **removed from the Slice A OCCT extraction branch** (`feature/occt-adjacency-engine`); archived on `feature/spatial-intelligence`. The `IExactAdjacencyEngine` seam is retained, so a planar accelerator can be re-vendored if ever measured-necessary.

**REPLACE / SHELVE:**
- `PlanarAdjacencyEngine` (Clipper2 + opposing-normal + projection) → shelved behind the seam; a new `OcctAdjacencyEngine` becomes default.
- `IsSolid()` gate + opposing-normal predicate → **deleted** (OCCT `Common()` needs neither; identity-keying disambiguates).
- Main-thread extraction's per-face projection → becomes "deep-copy `ON_Brep` on main thread; convert + `Common()` on worker."

**NEW WORK:**
- `OcctAdjacencyEngine` (OCCT `Common().Area`, identity-keyed) behind the seam.
- `ON_Brep`→OCCT `TopoDS` conversion (direct converter, or temp-STEP v1).
- OCCT integration into the RookNative build (productionized).
- Fix the Gate-4 **diagnostic-propagation bug** (per-face reason codes — "curved"/"unoriented"/"mesh" — currently don't reach the HTTP response; the honest-degradation invariant requires they do).

**Threading (preserved from Gate 4, validated):**
- HTTP worker → `QueryCandidatesAsync` (processor thread, RTree) → **main thread**: deep-copy `ON_Brep` only (no Rhino SDK pointer crosses the boundary) → **worker thread**: `ON_Brep`→`TopoDS` convert + OCCT `Common()` (pure, off the UI thread) → cache → route. UI never blocks.

**Concurrency policy (Spike E + research):**
- **v1 = serialized OCCT** (single worker queue / mutex). Safe, correct (Spike E proved it), and lazy+cached makes it cheap. The tracer's `HandleOcctProbe` already serializes via a static mutex.
- **Later, if batch throughput demands multi-core:** prefer OCCT internal parallelism (`SetRunParallel`) on the big construction-tier ops, or a **process-pool** of single-threaded OCCT workers. **Hand-rolled shared-memory threading of OCCT booleans is explicitly OUT OF SCOPE** — OCCT booleans are documented not-thread-safe (static-init races, boolean non-thread-safety, allocator-mutex serialization).

---

## 3. Spike campaign — evidence

All spikes ran on the real model **`SpatialTest.3dm (a local test model)`** (61 active
objects: A-WALL/I-WALL/A-FLOR/A-DOOR/stairs/handrails/columns/slabs; the .3dm has 4506
objects incl. block instances). **Units = inches; STEP export = mm; in²→mm² = 645.16.**
Scripts: `docs/rook_docs/occt-spike/spike_*.py` (committed). STEP geometry under
`occt-spike/steps/` is **gitignored** (don't commit user geometry).

### Spike A — correctness — PASS (user-confirmed)
- Method: face-pair `BRepAlgoAPI_Common().Area` (NOTE: **solid-solid `Common` returns empty** for touching solids — measure-zero volume; must do **face-pair**).
- Exact agreement with the Gate-4 Clipper engine on 3 solid pairs (ratio 1.0000): e.g. wall×wall = 18651.672 in² = 12,033,312.7 mm².
- **Open floorplate `08d4dedf`** (Gate-4 engine: 0 edges, structurally blind) → OCCT recovered **5 real abutments the user confirmed by eye**: A-WALL `71065f57` (3312 in²), Triage `5c12cc83`/`be0ca730` (~5440/5423), I-WALL `7e80db98`/`26b2c012` (~1040/1055). Plus a 1.69 in² sliver `502898fc` (real, see C).
- Curved wall `7d55840d`: both engines found 0 shared face area (honest agreement; no positive curved-shared-face case in this model — curved `Common` itself was proven in Gate 3 synthetically).

### Spike B — latency/scale — PASS (accelerator unneeded)
OCP/Python = pessimistic upper bound (C++ faster). With a cheap coplanar prefilter
(→ ~22–34 `Common` calls/object): lazy per-object **46–111 ms**; **full-model batch
(61 obj/229 pairs) = 3.69 s**. Caveat: heavily-curved models prefilter less (more
`Common` calls), still seconds; lazy is the default.

### Spike C — tolerance — PASS
- **`fuzz=0` finds nothing** even for confirmed contacts (real coincident faces aren't exact to machine precision) → **a nonzero fuzzy is mandatory.**
- Real adjacencies **rock-stable across `[1e-4 mm, 0.1 in]`** (identical areas over 4+ orders) → tolerance tuning is trivial; default ~`1e-3`–`1e-2` mm.
- The 1.69 in² sliver is **stable across tolerances = a real small graze**, not noise. Surfacing trivial grazes is an **`areaTol` min-area policy** (a knob), not a correctness issue.

### Spike D — conversion — PASS / de-risked
- No off-the-shelf `ON_Brep`→`TopoDS` converter; Rhino **can't** export STEP to memory (`FileStp` file-based); OCCT side **can** `ReadStream`.
- STEP round-trip is **faithful** (Spike A exact areas). STEP read ~7–16 ms/object.
- **Direct converter surface translation proven machine-exact** (`spike_d_converter.py`): rebuilt real curved+planar NURBS surfaces from `rhino3dm` into OCCT `Geom_BSplineSurface`, max deviation **~8e-12 mm** — *after* fixing the gotcha that `rhino3dm` `Point4d` control points are **homogeneous** (divide by W for OCCT euclidean poles + weight) and that `rhino3dm` knot vectors need an end-knot prepended/appended for OCCT's flat-knot convention.
- Remaining (unspiked) = trims/pcurves→wire→`MakeFace`+`ShapeFix` + face assembly (same NURBS-curve mechanics; medium effort). Temp-STEP is the proven fallback.

### Spike E — thread-safety — PARTIAL PASS
8 threads × face-pair `Common`: 0 crashes, results identical to single-threaded — but
no speedup (OCP holds the GIL), so this **proves serialized-OCCT is safe/correct** (the
v1 policy) and does **not** prove true multi-core. Research confirms OCCT booleans are
not-thread-safe by default → serialize for v1 (see §2 concurrency policy).

### Spike G — OCCT in the C++ plugin — PASS (the gate)
- OCCT 8.0 (modeling+STEP, **source-built**) **compiles + links + initializes + runs inside RookNative**. `POST /scene/occt_probe` returned **12,033,312.694 mm²** — bit-identical to the Python baseline. (First call 2.2 s = cold OCCT static-init.)
- **DLL closure, measured:** 23 DLLs / **34.4 MB** (STEP path drags `TKDESTEP→TKXCAF→TKV3d/TKService/…`). **Direct converter (no STEP) ≈ 15 MB.** Full runtime = 65 MB.
- Rhino **finds OCCT DLLs next to the `.rhp`** (plugin loaded + `rhino_ping` green) → no `AddDllDirectory` needed.
- OCCT-only unit + plain interface compiles cleanly alongside the Rhino SDK (no header clash).
- **OCCT 8.0 API churn observed** (`TopTools_ListOfShape` alias deprecated → use `NCollection_List<TopoDS_Shape>`; `Standard_False` deprecated → `false`) → **pin 7.9.3 in production** (what A–E validated; has official wheels).

---

## 4. Key grounded numbers (decision inputs)

| Question | Answer (measured) |
|---|---|
| Correctness | OCCT == Gate-4 engine on solids (ratio 1.0000); recovers open geometry (user-confirmed) |
| Lazy latency | 46–111 ms/object (Python upper bound; C++ faster) |
| Batch latency | 3.69 s / 61 objects (Python upper bound) |
| Tolerance | nonzero fuzzy mandatory; stable over `[1e-4 mm, 0.1 in]`; default ~1e-3–1e-2 mm |
| Conversion fidelity | machine-exact (~1e-11 mm) incl. rational curved surfaces |
| Footprint (STEP path) | **34.4 MB** (23 DLLs) |
| Footprint (direct converter) | **~15 MB** |
| Footprint (full runtime) | 65 MB (not shipped) |
| Version to pin | **OCCT 7.9.3** (8.0 has API churn) |
| Concurrency | serialized v1; multi-core via internal-parallel/process-pool later |

---

## 5. Reproduction & current state

**Toolchain installed (system Python 3.13):** `cadquery-ocp` 7.9.3 (`import OCP`),
`rhino3dm`. (`pip install cadquery-ocp rhino3dm`.)

**OCCT source build (Spike G):**
- Source: `<repos>/OCCT` (shallow @ **V8_0_0** — for production, fetch/checkout **V7_9_3**).
- Configure (VS2022 cmake): modeling + DataExchange modules, viz/OCAF/Draw off, `BUILD_LIBRARY_TYPE=Shared`, all `USE_*` 3rd-party OFF. (DataExchange still pulled XCAF/viz toolkits transitively.)
- Build: `cmake --build build-rook --config Release --target install --parallel` (note: `INSTALL_DIR` var failed to expand → use the **build tree** directly).
- Outputs: headers `build-rook/inc`, libs `build-rook/win64/vc14/lib`, dlls `build-rook/win64/vc14/bin` (48 TK*.dll / 49 MB built).

**In-plugin probe (Spike G) — files (committed `e49d56bb`):**
- `src/RookNative/SceneGraph/OcctProbe.{h,cpp}` — OCCT-only unit (no Rhino/stdafx, NotUsing PCH, `/bigobj`, per-file OCCT include path). Plain interface; `OcctProbeInit()` (OSD::SetSignal) + `OcctProbeSharedArea(stepA, stepB, diag)`.
- `Handlers/SceneGraphHandler.cpp` — `HandleOcctProbe` (serialized via static mutex).
- `RookServer.cpp` (~:1796) — route `POST /scene/occt_probe`.
- `RookNative.vcxproj` — OcctProbe.cpp entry + Release Link `AdditionalLibraryDirectories`/`AdditionalDependencies` (TK* subset). **Hardcoded absolute OCCT path = tracer shortcut; productionize to a property/env var.**

**Build/deploy/run the probe:**
- Build: `cmd /c scripts\build-native.bat Release` (or `build_native.ps1 -Configuration Release`).
- Deploy: copy `.rhp` + the 23-DLL closure to `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\` (closure list in `spike` commit message / §3 G).
- Run: find native port (probe Rhino pid's listening ports for `GET /scene/graph/stats` → 200), then `POST /scene/occt_probe {stepA, stepB}` (paths to per-object STEP files). NOTE: native port changes per Rhino session.
- Native route HTTP is reached from Python `urllib` (NOT curl — user's security-software constraint allows direct HTTP, just not curl).

**Currently deployed:** the **tracer build** (adds `/scene/occt_probe`; everything else
unchanged & working; `rhino_ping` green). `main` untouched. Branch
`feature/spatial-intelligence`; latest commit `e49d56bb`. Gate-4 commits `3fceb52b..37fb9542`.

---

## 6. Remaining work (ordered)

1. **Strengthener 1 — direct converter** (`ON_Brep`→`TopoDS`): trims (pcurve→wire→`BRepBuilderAPI_MakeFace`+`ShapeFix`) + face assembly. Surface translation proven (`spike_d_converter.py`). Payoff: off-disk, off-main-thread, ~15 MB footprint, drops the STEP/XCAF/viz DLL chain.
   **OUTCOME (2026-06-14): BOUNDED — faithful validation folds into the engine build, not a separate spike.** `rhino3dm` does NOT expose pcurves/loops/trims (thin openNURBS subset), so the production pcurve-copy path can't be spiked in Python; the only Python-reachable strategy (rebuild face from 3D edges + `GeomProjLib` reproject) is fragile (wire failures + mis-trimmed areas — `spike_strengthener1_trimface.py`) and non-representative. Faithful proof = pcurve-copy from `ON_Brep` in C++ (exact, lower-risk than the reproject that failed). Cheapest venue: write it AS the `OcctAdjacencyEngine` (Step 5), validated in-plugin against a live `ON_Brep` (RookNative already links openNURBS+OCCT — zero new linking), OR a standalone openNURBS `ONX_Model` C++ test (offline, but costs standalone-openNURBS linking). **temp-STEP remains the proven v1 (Spike A + G), so nothing is blocked.**
2. **Strengthener 2 — messier/varied-geometry coverage**: **OUTCOME (2026-06-14): PASS — `spike_strengthener2_coverage.py`, 9/9 honest.** Functional-coverage matrix over the engine primitive (face-pair `Common`, fuzzy=1e-3): abutting→exact(100); gap>fuzzy→0 (no false adjacency); gap<fuzzy→bridged(100); coincident duplicate→full overlap(600), no crash; interpenetration→0 face-adjacency (honest: ≠ shared face, that's the `intersects` relation); **far-from-origin +1e6→exact(100), no precision collapse**; sliver→0 no crash; degenerate→rejected at construction (no silent bad face); **curved cylinder-on-planar→πr²(50.265), exact** (the curved positive case the real model lacked). Mesh/SubD→`unsupported` at extraction (Gate-4 smoke). Invariants hold: no crash, correct-where-real, no false-exact. Design note: a coincident-duplicate *object* honestly reports full-surface overlap → the `areaTol`/identity/semantic layer decides if a duplicate counts as "adjacent."
3. **Real `OcctAdjacencyEngine`** behind `IExactAdjacencyEngine`: identity-keyed cross-object `Common().Area`; deep-copy `ON_Brep` on main thread; convert + `Common` on worker (serialized); cache; **fix diagnostic propagation** (reason codes → response); `areaTol` min-area policy + nonzero-fuzzy tolerance policy (surfaced, not hidden).
4. **Build-system productionization**: pin **OCCT 7.9.3**; source-build with module selection; replace hardcoded vcxproj path with a property/env var; deploy only the measured DLL closure; LGPL compliance (dynamic-link + "Uses Open CASCADE Technology" attribution).
5. **Spike F (deferred)** — construction tier: `BOPAlgo_MakerVolume`/`CellsBuilder` → enclosed cells (zones/IfcSpace), shared-face adjacency by topological identity (`TopExp::MapShapesAndUniqueAncestors`+`IsSame`), apertures→circulation. This is the **next capability** (zones/circulation), not part of the adjacency engine. OCCT internal `SetRunParallel` is the parallelism lever here. **The graph/intelligence layer that consumes all this — projection model, IFC-aligned edge ontology, space-syntax analytics, open design forks — is captured in `2026-06-14-spatial-graph-projection-design.md` (the engine makes the edges; that doc is the graph those edges feed).**
6. **Merge**: after strengtheners + real engine + correctness spot-checks, the user pulls the merge trigger (per doctrine). Gate-4 planar engine stays shelved as a possible accelerator.

---

## 7. Open decisions / risks

- **Direct-converter trim half unproven** (medium effort/risk; temp-STEP fallback exists). Strengthener 1 closes it.
- **OCCT version pin** 7.9.3 vs 8.0.0 — recommend 7.9.3; confirm before productionizing (8.0 API churn already cost two fixes).
- **`areaTol` threshold** — product decision: do tiny grazes (e.g. 1.69 in²) count as adjacency?
- **Edge/angled contact** — face-area adjacency reports 0 for elements meeting at an edge (both Clipper and OCCT). If "edge contact = adjacency" is wanted, that's a *separate relation* (shared-edge / `DistShapeShape`), above either engine.
- **Far-from-origin** — model is −630..+505 (in); OCCT handled it in-plugin fine; extreme coordinates remain a watch item (local-origin handling).
- **Construction tier robustness/scale** (Spike F) — `MakerVolume` can silently drop faces (warnings, not errors); needs validation on real conditioned geometry.
