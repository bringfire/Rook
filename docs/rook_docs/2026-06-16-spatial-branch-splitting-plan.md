# Spatial Branch-Splitting & Integration Cleanup Plan

**Date:** 2026-06-16
**Author:** integration cleanup pass (audit only — no code modified)
**Branch under audit:** `feature/spatial-intelligence`
**Worktree:** `C:/Users/aryan/source/repos/rook-spatial`
**Status:** PLANNING / CHECKPOINT — no merge, rebase, cherry-pick, or split has been performed.

---

## 0. Why this document exists

`feature/spatial-intelligence` has accumulated **119 commits** ahead of `main`
(`main...HEAD` = 11 behind / 119 ahead). It now carries four independently-shippable
product tracks plus a fat foundation commit and some incidental drift. The branch is
too large to review or merge as a unit. This plan inventories the commits, maps the
file-touch / conflict surface, fixes the real dependency order, and proposes four
clean extraction branches off **current** `main`.

### Anchor facts (verified this pass)

| Fact | Value |
|------|-------|
| Branch (`git branch --show-current`) | `feature/spatial-intelligence` ✅ |
| Merge-base with `main` | `c020b9d9` (the #252 `gh_edit` deferred-solve merge) |
| Ahead / behind | 119 ahead, 11 behind |
| Dirty (DO NOT TOUCH) | `knowledge/contextual_mab.pkl`, `knowledge/gh/component_observations.json`, `src/Rook/Properties/launchSettings.json` |

### The 11 commits `main` gained after the branch forked (the "main drift" we must rebase onto)

```
8260dba7 docs: address chat model visibility review notes
5395a23b docs: plan chat model visibility slice
5b3bbd9a docs: specify chat model visibility contract
e14700c4 Harden GH canvas cleanup tooling (align / layout / sugiyama dispatch)
fa432329 release: bump versions to 1.5.13 (#256)
f5b24e7c Add Windows CLI-agent install note to AGENT_SETUP prerequisites
fc64ba8a Point Claude Code CLI not-found message at the native Windows installer
33323765 Restyle Vision panel to the docs-site folio aesthetic
9e29138e [codex] Delegate rhino_launch to owned workbench launcher (#255)
65dac048 Classify rhino vision presentation targeting policy (#254)   <-- TOUCHES targeting.py
dfbdac61 [codex] Fix Rhino workbench launch environment (#253)
```

Only **#254** (`65dac048`) intersects any extraction surface: it added **1 line** to
`mcp_server/src/rook/targeting.py`. That is the single known main-vs-slice conflict
seed and it is tiny. (This is the "pre-existing main/#254 policy drift" the task flagged —
it is **not** part of slices A–D; it is already in `main` and we extract *on top of* it.)

---

## 1. Commit inventory (grouped by slice, chronological)

Slices are contiguous in history (linear branch). Boundary hashes given for ranges.

### Slice A — OCCT exact adjacency engine `c020b9d9..ccfe2b88` (63 commits)
Includes the **superseded Clipper2 Gate-4 planar engine** (added, then retired in T8 but
the vendored source still sits in-tree — see §3 dead-code note) and a **fat foundation
commit** that also bundles the FreeCAD-BIM spike (see §5/E).

```
38fa3046 docs: spatial-intelligence foundation + Gate 0-3 grounding spikes   [FAT: also carries freecad-spike — see E]
b8d36c1d docs(spec): Gate 4 exact planar adjacency service design
fe4f98e5 docs(spec): Gate 4 revision — Codex findings 1-6
386c2d5f docs(spec): Gate 4 revision round 2 — Codex findings 7-10
108f230e docs(spec): Gate 4 round 3 — adopt Clipper2 + findings 1-4
5faf73df docs(spec): Gate 4 round 4 — fill-rule/winding, range-guard, capability precedence
155a749e docs(plan): Gate 4 exact-adjacency implementation plan
878145b8 docs(plan): Gate 4 plan revision — 6 plan-review findings
7fb9e910 docs(plan): Gate 4 plan rev 3 — PCH + test-project build
3fceb52b deps: vendor Clipper2 (BSL-1.0) + minimal compiled units      [SUPERSEDED vendor]
a5be8357 feat(scene): exact-adjacency plain DTOs
5db7354f test(scene): planar adjacency engine cases + standalone target (failing)
50c1c64e feat(scene): planar adjacency engine via Clipper2            [SUPERSEDED]
e106dad8 fix(scene): harden planar engine — Clipper2 exception/degenerate guards
d32ead9d feat(scene): deterministic action-queued candidate query
b526c0d6 feat(scene): ExactAdjacencyService orchestration + core cache
8af33985 feat(scene): main-thread Brep face-summary extraction
403cf1f9 feat(api): POST /scene/graph/adjacency/exact overlay route
5d5e9965 fix(scene): native-review follow-ups — busy diagnostic + teardown contract
37fb9542 docs(gate4): live-Rhino smoke results — §11 cases pass
e49d56bb spike(scene): OCCT-in-plugin tracer (Spike G) + A-E scripts
82ce48bb docs(spatial): OCCT uniform-engine decision + spike resume doc
587b4dde docs(spatial): spatial-graph projection/ontology/intelligence direction
efb682bb spike(scene): strengtheners 1 (bounded) + 2 (PASS)
2cfacbe5 spec(occt): OcctAdjacencyEngine production design
e37f68b3 spec(occt): reviewer amendments — orientation/STEP oracle/facePairs
c289a9e4 plan(occt): implementation plan (10 tasks, two-phase)
7bea892f plan(occt): reviewer amendments — buildable commits, RAII converter
7b7f68e8 plan(occt): nits — test-helper note, licenses-file lookup
32a594be refactor(scene): add Rook::Legacy planar engine unit (additive)
c2104bd2 feat(scene): OCCT adjacency contract types (4-state Capability...)
7ae10e7f test(scene): STEP oracle fixtures + gitignore
25e3032e plan(occt): amend Tasks 4-9 to in-plugin validation venue
f88ef105 feat(scene): ON_Brep->OCCT converter + dev validation route
4e227975 feat(scene): converter trims/pcurves + orientation fidelity
f6af82f0 docs(occt): converter PROVEN machine-exact (Tasks 1-5)
690d835b feat(scene): OcctAdjacencyEngine kernel + robustness matrix + Evaluate route
984c64d9 docs(occt): Task 6 engine kernel + 9/9 matrix + 2 deviations
40442ba8 fix(scene): Evaluate AV — unguarded bbox prefilter fault
08118ba2 fix(scene): Evaluate EDEADLK — drop bbox prefilter + /EHa
e99512b0 docs(occt): Task 6 BLOCKED — OCCT thread/signal hard-crash
8d17ce4c fix(scene): dedicated serialized OCCT worker thread (OSD::SetSignal once)
7d82be2d docs(occt): CORRECT crash diagnosis — 0xC0000409 fail-fast
f694e7e5 diag(scene): flush-per-line trace in Evaluate
55ed2d2f diag(scene): _heapchk + string-size probes
fd0ba14a docs(occt): root cause = stack/memory corruption of `core`
360ba57a fix(scene): converter 2D-curve CV read by-value ControlPoint(i)
f94fb867 docs(occt): GetCV lead refuted — stack OOB write, ASan next
1f45ba85 diag: standalone offline ASan repro harness
46c17430 docs(occt): ASan NOREPRO — engine exonerated; /O2-//GL-sensitive
4ce66d80 diag(occt): bisect repro flags — /O2 and /O2+/GL+LTCG NOREPRO
cf5ee21b docs(occt): RHINO_ENV confirmed — in-Rhino data-breakpoint next
806ab060 diag(build): /Od + GL-off for OcctAdjacencyEngine.cpp (TEMP)
c2dcbc75 diag(scene): revert /Od, add /O2 bracket probes
52158c77 diag(scene): sizeof probes (ODR layout mismatch test)
dd07bfc4 diag(build): /O2 + /GL-off — test LTCG-folding-miscompile
d38abad5 docs(occt): ODR refuted (sizeof identical) — Evaluate heisenbug
d09dc653 fix(occt): namespace OCCT contract as Rook::occt — KILLS ODR violation  [THE FIX]
eaa03816 docs(occt): refresh Tasks 7-10 plan for Rook::occt
5c233641 feat(scene): integrate OcctAdjacencyEngine into production route (Task 8)  [retires legacy wiring]
1db747ad build(occt): parameterize OCCT root, trim DLL closure, LGPL attribution (Task 9a)
d28c36bb test(scene): in-plugin live verification on SpatialTest.3dm (Task 10)
ccfe2b88 docs(occt): record Tasks 8/9a/10 done (production route live on OCCT)
```

> Note: the 63 commits above include ~30 diagnostic/`docs(occt)` heisenbug-hunt commits.
> History is faithful but noisy; see §6 for the squash-vs-preserve decision.

### Slice B — Exact Adjacency Projection v1 `ccfe2b88..d1162d09` (15 commits)
```
166c6fc4 docs(spatial): approved design for Exact Adjacency Projection v1
70a00dee docs(spatial): refine Projection v1 spec (cache invalidation, registration, scope)
6348e835 docs(spatial): implementation plan for Projection v1
7a26e157 docs(spatial): fold Codex pre-execution corrections into plan + spec
cfa174a8 feat(spatial): exact_projection module scaffold
b88e2b91 feat(spatial): canonical idempotent adjacent_exact edge upsert
83376e4b feat(spatial): prepare/commit per-source delta + bbox reconciliation
485dc9b6 feat(spatial): sequence-keyed prune + cache invalidation
6a23da7b feat(spatial): project() orchestration + per-source isolation + singleton
f335932f feat(spatial): render adjacent_exact edges in get_context
cf97fa1e feat(spatial): register scene_exact_neighbors (MCP schema+dispatch+group, agent-direct)
9b79c858 refactor(spatial): drop unused Any import (review nit)
2d9b3261 test(spatial): live projection smoke (gated on Rhino)
524f0986 fix(spatial): post-review hardening (findings 1-5)
d1162d09 test(spatial): correct live smoke — floorplate has 9 exact neighbors
```

### Slice C — Semantic Containment Refinement v1 `d1162d09..096372c5` (15 commits)
```
ada503b8 docs(spatial): approved design for Containment v1
b6487122 docs(spatial): refine spec (touching_exact, IFC, atomicity, cache key)
610475fa docs(spatial): implementation plan for Containment v1
70a5b644 docs(spatial): pre-execution wording fixes (native-interaction + grouping_hint)
7459f388 feat(spatial): containment_refinement scaffold
f9de093d feat(spatial): pure evidence functions
0800dd01 feat(spatial): verdict engine (two vetoes + additive ordinal confidence)
c2101313 docs(spatial): reconcile plan low-branch with verdict tests (>= 2 supports)
715e380c feat(spatial): refiner candidate collection + per-candidate eval (read-model only)
c9a23f3d feat(spatial): request-level prepare/commit delta (atomic)
38d320af feat(spatial): refine() orchestration + request cache + prune-on-advance
b8d2eb95 feat(spatial): render contains_semantic edges in get_context (with confidence)
5b1096eb feat(spatial): register scene_refine_containment (MCP schema+dispatch+group, targeting)
0a35ada1 refactor(spatial): drop unused WEAK_SOLID_TYPES (review nit)
096372c5 test(spatial): live wiring smoke (contract-only)
```

### Checkpoint doc (triage → E) `096372c5..dd404ccd` (1 commit)
```
dd404ccd docs(spatial): checkpoint intelligence-layer pivot
```
Touches only `docs/rook_docs/2026-06-14-spatial-graph-projection-design.md` and adds
`docs/rook_docs/2026-06-16-spatial-intelligence-pivot-checkpoint.md`. Pure narrative —
ride it along with whichever branch is most convenient, or park it. **Not load-bearing.**

### Slice D — RookBIM Revit→Rhino export v1 `dd404ccd..HEAD` (25 commits)
```
9b9ce901 docs: spec RookBIM Revit->Rhino export v1 (calibration fixtures)
894cd3df docs: fix RookBIM export targeting policy risk to "mutate"
883c21c2 docs: implementation plan
cb003ad4 docs: address plan review (green-per-task, build gates, path safety, live API)
96f26477 feat(bim): export request contract, error codes, result POCOs
c5e9c985 refactor(bim): Task 1 review (test naming, using, both-null, comment)
052eb6af docs: fold Task 1 review (units validation, RookBim* test naming)
20575b46 feat(bim): pure path-safety policy + units validation
91fed2d7 refactor(bim): harden export path policy (reject trailing-dot, escape regressions)
8114d112 feat(bim): add ExportElements to runtime interface + Unavailable impl
8ec09e43 feat(rookbim): Revit->Rhino geometry converter (brep/mesh/bbox)
e87caf71 refactor(rookbim): distinct 'none' for failed conversion
38c894cf feat(rookbim): provenance-tagged label extractor (level/host/room/space)
b2037942 refactor(rookbim): idiomatic PascalCase BimSemanticLabel props
b20600ed feat(rookbim): room/space reference exporter with per-room degrade
d730e458 feat(rookbim): export service (resolve/convert/assemble/write/verify)
2bc05857 refactor(rookbim): robustness (per-element isolation, honest counts, write-scoped cleanup)
c5cb1cf8 feat(rookbim): wire ExportElements through dispatcher (120s timeout)
910c4c6a feat(bim): BimHandler export_elements op, route, error mapping
44ad7768 feat(native): /bim/export-elements route forwarding export_elements op   [+10 LOC native]
f50fa786 feat(mcp): rookbim_export_elements tool, group, mutate targeting policy
16844eee test(rookbim): gated live-verify script + bijection
42d8a0e8 docs: Task 13 reconciliation — representation 'none' + plan delta
f3937a03 fix(rookbim): bijection accepts room keys + multiple objects/key
2580041d docs: spec §8 — bijection allows multiple objects/key + room-geometry keys
```

---

## 2. File-touch inventory & overlap map

### Per-slice primary files

| Slice | Primary code surface |
|-------|----------------------|
| **A** OCCT engine | `src/RookNative/SceneGraph/*` (OcctAdjacencyEngine, OcctExecutor, OnBrepToOcct, ExactAdjacencyService, SceneGraph), `Handlers/SceneGraphHandler.*`, `RookServer.cpp`, `RookNative.vcxproj(.filters)`, test vcxprojs (`ExactAdjacencyTests`, `OcctPrimitiveTests`, `OcctOfflineRepro`), `vendor/clipper2/*` (dead), `SceneGraph/legacy/*` (dead), `THIRD_PARTY_NOTICES.md`, `docs/rook_docs/occt-*`, `docs/superpowers/{specs,plans}/2026-06-14/15-*`. **No `mcp_server/` Python.** |
| **B** Projection | `mcp_server/src/rook/scene/exact_projection.py` (new), `scene/scene_graph.py`, **`server.py`, `targeting.py`, `agent/tool_groups.py`, `agent/tool_dispatcher.py`**, `mcp_server/tests/test_exact_projection.py`, `docs/.../exact-adjacency-projection-v1*`. |
| **C** Containment | `mcp_server/src/rook/scene/containment_refinement.py` (new), `scene/scene_graph.py`, **`server.py`, `targeting.py`, `agent/tool_groups.py`, `agent/tool_dispatcher.py`**, `mcp_server/tests/test_containment_refinement.py`, `docs/.../semantic-containment-refinement-v1*`. |
| **D** RookBIM | `src/Rook/Bim/*` (Contracts, BimExportBijection, BimExportPathPolicy, IRookBimRuntime, RookBimUnavailableRuntime), `src/Rook/Handlers/BimHandler.cs`, `src/RookBim/*` (RevitExportService, RevitGeometryConverter, RevitLabelExtractor, RevitRookBimRuntime, RevitRoomExporter, RookBim.csproj), `src/RookNative/Handlers/GrasshopperProxyHandler.*` (+1 op), `src/RookNative/RookServer.cpp` (+1 route), **`server.py`, `targeting.py`, `agent/tool_groups.py`, `agent/tool_dispatcher.py`**, `src/Rook.Tests/Bim/*`, `src/Rook.Tests/Handlers/*Bim*`, `src/RookBim.Tests/*`, `mcp_server/tests/test_rookbim_*.py`, `docs/.../rookbim-revit-rhino-export-v1*`. |

### Overlap / conflict zones (the whole cross-slice surface)

| File | A | B | C | D | main #254 | Nature |
|------|---|---|---|---|-----------|--------|
| `mcp_server/src/rook/server.py` | — | +42 | +33 | +54 | — | **append-only** tool-schema registration; same file region → textual collision when stacked |
| `mcp_server/src/rook/targeting.py` | — | +2 | +2 | +1 | **+1** | append-only policy entries; **4-way** incl. main #254 |
| `mcp_server/src/rook/agent/tool_groups.py` | — | ✓ | ✓ | ✓ | — | append-only group membership |
| `mcp_server/src/rook/agent/tool_dispatcher.py` | — | ✓ | ✓ | ✓ | — | append-only dispatch map |
| `mcp_server/src/rook/scene/scene_graph.py` | — | ✓ | ✓ | — | — | B & C both render new edge types in `get_context` |
| `src/RookNative/RookServer.cpp` | ✓ | — | — | ✓ (+1) | — | A adds adjacency route; D adds `/bim/export` route — **different regions**, low risk |
| `src/RookNative/Handlers/GrasshopperProxyHandler.*` | — | — | — | ✓ (+7/+1) | — | D-only; A doesn't touch it |

**Critical observation:** every B/C/D edit to the four registration files is **append-only**
(numstat shows `+N / 0`). There are **no semantic conflicts** — only line-adjacency
collisions if two slices are stacked onto the same file. Extracting each slice onto a
**separate** branch off `main` reduces the collision to *slice-vs-main-#254 on `targeting.py`
only*, which is 1–2 lines and almost certainly auto-mergeable (different dict key, same
neighborhood).

---

## 3. Dead-code / vendor note (Slice A)

`vendor/clipper2/*` and `SceneGraph/legacy/LegacyPlanarAdjacency.{cpp,h}` are **still in the
tree at HEAD** but carry **no production wiring** — `git grep` for `LegacyPlanarAdjacency`
/ `Clipper2` in `ExactAdjacencyService*`, `SceneGraphHandler*`, `RookServer.cpp` returns
nothing. Task 8 (`5c233641`) retired the *routes* but left the vendored source. Extracting
A is the natural moment to **prune Clipper2 + the legacy planar unit** (the ~988 LOC the
memory notes as "retired"). This is optional and additive-to-remove; keep it if a rebuild-
from-history is preferred over a clean tree. Flag, don't force.

---

## 4. Dependency order (verified, with corrections)

The task's *expected* order was: OCCT → Projection → Containment; RookBIM independent.
The code says something slightly different and **looser**:

```
            ┌─────────────────────────┐
            │  A · OCCT engine (C++)   │  produces /scene/graph/adjacency/exact
            │  → `adjacent_exact` edges│  + the OCCT runtime closure
            └────────────┬────────────┘
                         │ RUNTIME dep only (HTTP route), NOT a code/import dep
                         ▼
            ┌─────────────────────────┐
            │ B · Projection v1 (py)   │  reads OCCT exact edges → networkx mirror
            └─────────────────────────┘

   C · Containment v1 (py)  ── INDEPENDENT of A and B ──
        refines bbox `contains` edges (scene-graph derived, NOT OCCT);
        "pure read-model: only analytics.sync(), never the exact projector."

   D · RookBIM export (C#/native/py) ── FULLY INDEPENDENT ──
        only shares the 4 py registration files + targeting (main #254).
```

**Corrections to the assumed order:**

1. **B depends on A only at *runtime/live-verify*, not at compile/unit-test.** B's Python
   never imports A's C++; it calls the `/scene/graph/adjacency/exact` HTTP route. B's unit
   tests (`test_exact_projection.py`) drive the projector with synthetic edges and pass
   without A deployed. ⇒ **B can be its own PR**, but its *live-verify* and its *merge*
   should follow A landing, or the route 404s.

2. **C does NOT depend on B.** Containment refines bbox `contains` edges and is a pure
   read-model that never calls the exact projector (per the shipped design + memory). The
   only reason C came *after* B in history is sequencing, not dependency. ⇒ **C can extract
   and merge in parallel with B**, independent of A. The single coupling is that B and C
   both edit `scene_graph.py` `get_context` and the four registration files — a *textual*
   adjacency, not a logic dependency.

3. **D is fully independent** (C# + native + its own MCP tool). Its only shared surface is
   the four registration files and `targeting.py` (where it collides with main #254, not
   with A/B/C since they're on separate branches).

**Net merge-order constraint:** `A` before `B` (runtime). `C` and `D` have **no** ordering
constraint relative to anything. Recommended human merge sequence: **A → B → (C ∥ D)**.

---

## 5. Triage bucket E (unrelated / fold-in)

| Item | Where | Disposition |
|------|-------|-------------|
| FreeCAD-BIM spike (`docs/rook_docs/freecad-spike/*`, `2026-06-13-freecad-rook-bim-architecture.md`, ~5631 LOC of `.py`/`.FCStd`/`.step`/`.ifc`) | bundled inside `38fa3046` (A's foundation commit) | **DECIDED (2026-06-16): peel/omit from Slice A.** It is not part of the OCCT adjacency deliverable and would distract reviewers. Leave it parked on the archival `feature/spatial-intelligence` branch; if preservation is wanted, ship it later as a separate docs-only branch/PR `docs/freecad-bim-spike`. Because A is rebuilt from final state via curated commits (§7.1.1), this is simply "don't author a commit that adds `freecad-spike/*`" — no commit-split surgery needed. |
| Spatial-intelligence foundation + projection/ontology direction docs | `38fa3046`, `587b4dde`, `dd404ccd` | Narrative scaffolding. Carry **only the OCCT-relevant** foundation/decision docs into A's curated docs commit; B/C design docs already live in-slice. |
| `2026-06-16-spatial-intelligence-pivot-checkpoint.md` | `dd404ccd` | Park or attach to whichever branch ships last. |
| Dirty working-tree files (`contextual_mab.pkl`, `component_observations.json`, `launchSettings.json`) | uncommitted | **DO NOT touch.** Runtime/learning artifacts; out of scope for every slice. |

No genuine "unrelated feature drift" was found in committed history — the GH-cleanup,
release-bump, vision-restyle, and #253/#254/#255 work is all on **`main`**, already
accounted for in §0, and is *not* on this branch.

---

## 6. Verification gates per future clean branch

### A — `feature/occt-adjacency-engine`
- **Build:** `scripts/build-native.bat` (v143 toolset, `VCToolsVersion=14.44.35207`, `$(OcctRoot)` param pointing at the verified **OCCT `V8_0_0`** checkout). Trimmed 11-DLL / 20.6 MB non-DataExchange runtime closure must resolve.
- **Offline tests:** `OcctPrimitiveTests.vcxproj` (expect 17/17), `OcctOfflineRepro.vcxproj` ASan harness (NOREPRO / 5 exact edges), `ExactAdjacencyTests.vcxproj`.
- **Live:** deploy native, `POST /scene/graph/adjacency/exact` on `SpatialTest.3dm` → **5/5 abutments exact**, `exact_brep` / `inches²`, cache 50 ms→1 ms warm, Rhino stable.
- **Licensing:** `THIRD_PARTY_NOTICES.md` + `docs/rook_docs/occt-build.md` LGPL attribution present.
- **CAVEAT — Task 9b deferred:** do **NOT** pin/switch the shared OCCT checkout to 7.9.3; stays on verified `V8_0_0`. 9b is a separate worktree/build-dir effort.
- **If pruning dead vendor (§3):** confirm `RookNative.vcxproj` no longer references clipper2/legacy units and the build is still green.

### B — `feature/exact-adjacency-projection-v1`
- **Unit:** `pytest mcp_server/tests/test_exact_projection.py` (passes without A — synthetic edges).
- **Live (needs A deployed):** `docs/rook_docs/occt-spike/live_verify_exact_projection.py` → floorplate **9 exact neighbors** (dual-verified Claude + Codex).
- **Contract:** `scene_exact_neighbors` registered (schema + dispatch + group + agent-direct local handler); `get_context` renders `adjacent_exact` with shared-face area.
- **Gate:** do not merge ahead of A (route would 404 in live).

### C — `feature/semantic-containment-refinement-v1`
- **Unit:** `pytest mcp_server/tests/test_containment_refinement.py` (**32 tests**; **86** in the full scene suite).
- **Live (contract-only):** `docs/rook_docs/occt-spike/live_verify_containment_refinement.py`.
- **Contract:** `scene_refine_containment` registered; `contains_semantic` edges render with confidence; pure read-model (only `analytics.sync()`).
- **CAVEAT — calibration pending:** 27/28 positives on `SpatialTest` ⇒ verdict thresholds are **not calibrated**. Ship the mechanism, but **gate downstream reliance** until confidence thresholds are tuned. State this explicitly in the PR description.

### D — `feature/rookbim-revit-rhino-export-v1`
- **Managed build/test:** `Rook.Tests` (expect **2633** green) + `RookBim.Tests` (**35** green); `RookBim.csproj` builds against the Revit API references.
- **Native:** `/bim/export-elements` route + `GrasshopperProxyHandler` op compile into `RookNative`.
- **Python:** `pytest mcp_server/tests/test_rookbim_export_tool.py mcp_server/tests/test_rookbim_mcp_tools.py`; `rookbim_export_elements` tool registered with **`mutate`** targeting policy.
- **CAVEAT — live-verify still gated/pending:** `docs/rook_docs/rookbim-export-spike/live_verify_rookbim_export.py` requires a live **Rhino.Inside.Revit** session and has **not** been run. Branch ships code-complete; mark live-verify as an open gate in the PR. (This matches the parked status of the slice.)
- **CAVEAT — targeting vs main #254:** D adds a `mutate` entry to `targeting.py` near #254's vision-presentation classification line. Expect a 1-line conflict on extraction; resolve by re-applying D's entry above/below #254's. Read the rebuilt `targeting.py` to confirm no policy was dropped.

---

## 7. Proposed clean-branch extraction plan

All four branch off **current `main`** (which already contains #253/#254/#255, the release
bump, vision restyle, and chat-model-visibility docs). No branch touches `main` itself.

> Mechanics note: because the four slices are contiguous ranges on a linear branch, the
> cleanest extraction is **`git cherry-pick <first>^..<last>`** of each range onto a fresh
> branch, OR `git checkout -b … main && git cherry-pick A1..An`. Stacking (B on A, etc.)
> preserves exact provenance but re-introduces the registration-file line collisions;
> **independent branches off `main`** is recommended (see §2). Do this in a scratch worktree,
> never in-place on `feature/spatial-intelligence`. **Nothing below is executed by this pass.**

### 7.1 `feature/occt-adjacency-engine`  (Slice A)
- **Range:** `c020b9d9..ccfe2b88` (63 commits) — **do NOT mechanically cherry-pick the raw range.** Reconstruct a curated history from the *final tree state* (see §7.1.1) so reviewers get the OCCT deliverable, not the 30-commit debugging journey.
- **Expected conflicts vs current main:** **none likely** — A is native-C++/docs only and `main`'s 11 commits don't touch `src/RookNative/SceneGraph/*`; `THIRD_PARTY_NOTICES.md` is **absent on main** (clean add). Verify `RookServer.cpp` adjacency-route hunk still applies (main didn't touch it).
- **Verification:** §6-A.
- **Independent PR?** ✅ Yes — foundational, no upstream slice dependency. **Merge first.**
- **DECISIONS (resolved 2026-06-16, user):** (i) **squash** the heisenbug diagnostic history — keep the lesson in docs, not the 30 probe commits; (ii) **prune** dead Clipper2 + `LegacyPlanarAdjacency` (§3), conditioned only on build/test staying green after removal; (iii) **peel/omit** the FreeCAD spike (§5-E). No "keep raw range" option survives.

#### 7.1.1 Curated-history reconstruction for Slice A (the chosen mechanic)

Do **not** cherry-pick the 63-commit range. Create `feature/occt-adjacency-engine` from
current `main` and rebuild a reviewable history of **~5–8 logical commits from the final
tree state** (i.e. `git checkout ccfe2b88 -- <paths>` per group, stage, commit). Proposed
commit shape:

1. **docs(occt):** OCCT-only spec + plan + decision docs (`2026-06-14-occt-uniform-engine-decision.md`, `2026-06-15-occt-adjacency-engine-design.md` spec, the OCCT plan, `2026-06-13-spatial-intelligence-foundation.md` trimmed to OCCT-relevant scope). **Excludes** `freecad-spike/*` and the FreeCAD arch doc.
2. **feat(scene):** OCCT contract/types + `ON_Brep`→OCCT converter (`OcctAdjacencyTypes.h` under `Rook::occt`, `OnBrepToOcct*`).
3. **feat(scene):** OCCT engine/kernel/executor + `ExactAdjacencyService` + `SceneGraph`/`SceneGraphHandler` (`OcctAdjacencyEngine*`, `OcctExecutor*`, `OcctProbe*`, `OcctSharedFaceArea.cpp`).
4. **test(scene):** offline test targets + fixtures (`OcctPrimitiveTests.vcxproj`, `OcctOfflineRepro.vcxproj`, `ExactAdjacencyTests.vcxproj`, `tests/*`, STEP-oracle fixtures + `.gitignore`).
5. **feat(api):** production `POST /scene/graph/adjacency/exact` route integration (`RookServer.cpp`, the Task-8 wiring) — already OCCT-only; **no** legacy/Clipper paths carried in.
6. **build(occt):** `RookNative.vcxproj(.filters)` `$(OcctRoot)` param + trimmed DLL closure + `THIRD_PARTY_NOTICES.md` (LGPL) + `docs/rook_docs/occt-build.md`. Confirm **no** `vendor/clipper2/*` or `SceneGraph/legacy/*` is added (the prune is realized by simply never staging them).
7. **docs(occt):** distilled ODR-heisenbug postmortem (the *story*, one doc) + Tasks 8/9a/10 live-verification record. This is where the debugging lesson is preserved without the probe commits.

Net: the ~30 `diag/docs(occt)` commits collapse into commit 7's narrative; Clipper2/legacy
and FreeCAD never enter the tree because they are never staged. Build + run §6-A gates on
the reconstructed branch **before** opening the PR — a curated history must still produce a
byte-faithful OCCT engine and pass the live `SpatialTest.3dm` check.

### 7.2 `feature/exact-adjacency-projection-v1`  (Slice B)
- **Range:** `ccfe2b88..d1162d09` (15 commits incl. design docs). Cherry-pick the range as-is — it is clean and small.
- **Expected conflicts vs current main:** `targeting.py` (+2) brushes main #254 (+1) — trivial. `server.py` / `tool_groups.py` / `tool_dispatcher.py` / `scene_graph.py` are clean vs main (main didn't touch them).
- **Verification:** §6-B.
- **Independent PR?** ✅ Yes as a *PR*, but **merge after A** (runtime route dependency / live-verify). Note the dependency in the PR.

### 7.3 `feature/semantic-containment-refinement-v1`  (Slice C)
- **Range:** `d1162d09..096372c5` (15 commits incl. design docs). Cherry-pick as-is. Optionally also carry `dd404ccd` (pivot checkpoint doc).
- **Expected conflicts vs current main:** `targeting.py` (+2) vs #254 (+1) — trivial. If C is *stacked* on B, additionally expect `server.py`/`scene_graph.py`/`tool_groups.py`/`tool_dispatcher.py` line-adjacency collisions with B's appends — **avoid by branching C directly off `main`, not off B.** C does not need B's code.
- **Verification:** §6-C (ship-with-calibration-caveat).
- **Independent PR?** ✅ Yes — independent of A and B. Can merge in parallel.

### 7.4 `feature/rookbim-revit-rhino-export-v1`  (Slice D)
- **Range:** `dd404ccd..2580041d` (25 commits incl. spec/plan). Cherry-pick as-is. `dd404ccd` is a docs checkpoint — include or drop; harmless either way.
- **Expected conflicts vs current main:** `targeting.py` `mutate` entry vs #254 (1 line — resolve per §6-D). `server.py`/`tool_groups.py`/`tool_dispatcher.py` clean vs main. Native `RookServer.cpp`/`GrasshopperProxyHandler.*` clean vs main. C#/`RookBim` tree is net-new — no conflict.
- **Verification:** §6-D (live-verify remains an OPEN gate).
- **Independent PR?** ✅ Yes — fully independent. Can merge any time after its own gates pass; **does not** require A/B/C. Keep parked until the live Rhino.Inside.Revit verify is run if you want green-before-merge.

---

## 8. Recommended extraction order & high-risk summary

**Extraction order — lowest-risk first. Note A is a curated reconstruction (§7.1.1); B/C/D are cherry-picks of their ranges:**
1. **A** `feature/occt-adjacency-engine` — **curated 5–8 commits from final state** (squash diagnostics, prune dead vendor, omit FreeCAD); zero expected conflicts, foundational, unblocks B's live-verify. **Start here** and ship its §6-A gates before the others.
2. **D** `feature/rookbim-revit-rhino-export-v1` — cherry-pick range; disjoint surface (C#/native/own tool); only the 1-line `targeting.py` vs #254.
3. **C** `feature/semantic-containment-refinement-v1` — cherry-pick range; branch off `main` (not off B); trivial `targeting.py` overlap.
4. **B** `feature/exact-adjacency-projection-v1` — cherry-pick range; extract last so it can be **merged right after A** for a live route.

**Recommended merge order:** **A → B → (C ∥ D)**, with C and D parallelizable.

**High-risk / watch items:**
- **`targeting.py` is the one true conflict file** — 4-way touch (main #254 + B + C + D), but each is 1–2 append lines. After every extraction, **read the rebuilt `targeting.py`** and confirm no policy entry was dropped (especially D's `mutate` and #254's vision classification).
- **Do not stack B/C/D on each other** — their `server.py`/`tool_groups.py`/`tool_dispatcher.py`/`scene_graph.py` appends collide by line-adjacency. Branch each off `main`.
- **B merge-gating** — merging B before A ships a tool whose backing route 404s; enforce A-first.
- **C calibration** — mechanism ships, but verdict thresholds uncalibrated (27/28 positives); block downstream reliance.
- **D live-verify** — `live_verify_rookbim_export.py` is unrun (needs Rhino.Inside.Revit); treat as an open gate, not a regression.
- **OCCT 9b** — never repoint the shared OCCT checkout off the verified `V8_0_0`.
- **Dead vendor** — Clipper2 + `LegacyPlanarAdjacency.*` are unwired dead code; **prune from A** (decided) — realized by never staging them in the curated reconstruction; gate on green build/test.
- **Slice A history** — curated reconstruction, **not** a raw 63-commit cherry-pick (§7.1.1); the reconstructed branch must still build byte-faithfully and pass live `SpatialTest.3dm` before PR.
- **Dirty working files** — `contextual_mab.pkl`, `component_observations.json`, `launchSettings.json` stay untouched throughout.

---

## 9. Status of this pass

Audit/planning only. No merge, rebase, cherry-pick, branch creation, or destructive git was
performed. `main` untouched.

**Slice A cleanup decisions are RESOLVED (2026-06-16, user):** squash diagnostics, prune
dead Clipper2/legacy vendor, peel/omit the FreeCAD spike — implemented via the curated
reconstruction in §7.1.1, **not** a raw range cherry-pick. Commit counts patched to verified
values (A=63, B=15, C=15, D=25; checkpoint=1).

**Next action:** begin Slice A extraction — create `feature/occt-adjacency-engine` off
current `main` and reconstruct the §7.1.1 curated history in a scratch worktree, then run
the §6-A gates before opening the PR. B/C/D follow as range cherry-picks per §7; D waits on
its Rhino.Inside.Revit live-verify before merge.
