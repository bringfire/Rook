# RookSplat — Slice 1: mesh2splat Headless Converter — Design

- **Date:** 2026-06-03
- **Status:** Design approved (senior-reviewer sign-off on Option A + boundary X+, with three required revisions folded in). Ready for implementation-plan authoring. **No code written yet.**
- **Author:** Claude (synthesis of a Rook ⇄ user ⇄ senior-reviewer brainstorm)
- **Implementation target repo:** `bringfire/mesh2splat` fork — local `C:\Users\aryan\source\repos\mesh2splat` (origin = fork; upstream = `electronicarts/mesh2splat`; fork `main` `c3d3d52` mirrors EA `main`).
- **Touches no Rook code.** This slice only makes mesh2splat invokable; the Rook-side provider adapter is a later slice.

## 0. Repositories

| Repo | Local path | Role in this slice |
|---|---|---|
| mesh2splat (fork) | `C:\Users\aryan\source\repos\mesh2splat` | **Implementation target.** glb → 3DGS ply converter |
| Rook | `C:\Users\aryan\source\repos\Rook` | Orchestration plane that will *invoke* the converter (later slice). Owns this spec |
| ve_engine (fork) | `C:\Users\aryan\source\repos\ve_engine` | Downstream consumer of the `.ply`. Latest splat code on branch `new_forest_stub`. Used here only for a non-gating cross-repo smoke |
| RhinoMCP | `C:\Users\aryan\source\repos\RhinoMCP` | Reference for fourth-plane provider patterns (not modified) |

## 1. Goal & context

Give the forked mesh2splat a **command-line conversion mode**: one `.glb` in → one 3DGS `.ply` out, rendered on an **offscreen (hidden-window) GL context**, with **synchronous export** and a single **structured JSON result**, then exit. This makes mesh2splat usable as a **stateless, artifact-mediated converter-provider** that Rook's orchestration plane can invoke.

Relationship to the approved program architecture (all in `Rook/docs/superpowers/specs/`):
- `2026-06-02-rook-rhinomcp-architecture-assessment.md` — the **fourth plane** (external/local-orchestration) and the invariant: RookNative is the sole *in-Rhino* surface. mesh2splat connects on the fourth plane; it is **not absorbed** into RookNative or ve.
- `2026-06-03-rook-north-star-topology.md` — work-allocation + recomposition. mesh2splat is a **disposable converter-provider**; per §4 (separate compute lifecycle from artifact lifecycle), the process is throwaway and the `.ply` is the durable **artifact currency**. **Fan-out (which/how many files) lives in Rook, not the provider.**
- ve-side context (`ve_engine/docs/superpowers/specs/2026-05-27-rook-ve-bridge-v0-design.md`, `2026-05-28-rhino-splat-voxel-ve-integration.md`) — the splat→ve consumption pipeline these docs assume takes a `.ply` as input; this slice produces that input via the *synthetic* (mesh-derived) path.

## 2. Scope & non-goals

**In scope:**
- A CLI path in the existing mesh2splat executable: `--input <glb> --output <ply> [--format …] [--resolution …]`.
- A GUI-independent conversion unit, an offscreen GL context, synchronous export with real write verification, one JSON object on stdout.

**Out of scope (explicit non-goals):**
- Batch mode (Option B) and persistent serve mode (Option C) — deferred until per-invocation GL/shader-compile startup is *measured* to dominate real workloads.
- `.ply` input / re-export / format transcoding (GLB input only).
- GUI rewire onto the new core (Option Y) — the existing ImGui batch path is left byte-for-byte unchanged.
- Any Rook-side code; any ve change; PBR relighting tuning.
- True EGL/OSMesa headless. This is GLFW-backed hidden-window offscreen GL (see §6 naming).

## 3. Decision summary

- **Invocation model = A (one-shot CLI, one conversion per process).** Rook owns fan-out by spawning N processes. Reviewer concurred: mesh2splat should behave like a disposable compiler; B/C would push lifecycle/queue/health/cancellation into the provider with no evidence of need.
- **Code boundary = X+ (minimal additive headless driver behind a small unit; GUI untouched).** New `HeadlessConverter` unit; only the CLI wires to it. Option Y (shared `ConversionService` + GUI rewire) is the natural *future* destination but is the wrong first slice (changes working behavior, expands the test matrix, makes "headless exists" depend on "GUI refactor succeeded"). Option Z (drive the ImGui batch state machine headlessly) is rejected — it preserves the worst coupling and adds fake UI state.

## 4. Components & boundaries

Four small, additive units. Nothing existing is rewired.

1. **`HeadlessConverter`** (new, GUI-independent) — single entry `ConvertResult convert(const ConvertOptions&)`. Owns no UI. Instantiates `Renderer` and drives `SceneManager` on a GL context passed in (it does not create or own the context). Reproduces the mediator batch path's call sequence (§5) without the mediator or ImGui.
2. **`ConvertOptions` / `ConvertResult`** (new POD structs) — the typed boundary.
   - `ConvertOptions { std::string inputPath, outputPath; ExportFormat format; int resolution; }`
   - `ConvertResult { bool ok; uint64_t gaussianCount; double durationMs; std::string errorCode; std::string message; }`
3. **Offscreen GL context creation** — a **non-exiting** hidden-window context path (§6).
4. **CLI entry branch** in `main()` (§8) — parses args, creates the context, calls `HeadlessConverter::convert`, emits JSON, returns an exit code. The no-args path falls through to today's GUI loop unchanged.

## 5. Conversion sequence & determinism

`HeadlessConverter::convert` runs entirely on the calling thread:

1. `renderer.initialize()` on the offscreen context.
2. `renderer.setFormatType(0)` (existing render-context state retained for parity with the GUI load path — **not** an export-format selector; see §8 for the export-vs-render format distinction); `sceneManager.loadModel(glb, parentFolder)`; `renderer.gaussianBufferFromSize(res*res)`; `renderer.setViewportResolutionForConversion(res)`.
3. `renderer.enableRenderPass(conversionPassName)`.
4. **`renderer.updateTransformations()`** — *required revision #2*: the GUI batch path calls `UpdateTransforms` each cycle before the conversion frame renders (`guiRendererConcreteMediator.cpp` update loop). The headless path matches that ordering for behavioral parity.
5. **One** `renderer.renderFrame()` — runs the conversion pass exactly once; `renderFrame()` disables each executed pass immediately afterward (`renderer.cpp:155-159`, "Default to false for next frame"), so a single frame is deterministic.
6. **Synchronous export** via new `SceneManager::exportPlySync(path, format)` (§7).
7. Capture `gaussianCount` from `renderContext.numberOfGaussians`; capture wall-clock `durationMs` around steps 2–6.

Determinism notes: the conversion writes to the gaussian SSBO; `exportPly`'s existing `glMemoryBarrier` + the blocking `glGetBufferSubData` already synchronize the readback. The only async hazard in the current code is the **detached file-write thread**, removed in §7.

## 6. Offscreen GL context creation (required revision #1)

Today `GlewGlfwHandler` **`exit(-1)`s from its constructor** on `glfwInit` (`glewGlfwHandler.cpp:11`) and `glfwCreateWindow` failure (`:22-23`); only `init()` returns an error (GLEW, `:45`). A hard `exit()` bypasses the "every non-zero path emits one JSON object" contract.

Fix:
- Add a **non-exiting factory** for the CLI path — e.g. a `static` factory returning a small result object **plus a `std::unique_ptr<GlewGlfwHandler>`** (or a constructor variant that throws a caught exception). **Do not** return `GlewGlfwHandler` by value or `std::optional<GlewGlfwHandler>` unless the class is first made safely movable / non-copyable with explicit GLFW window ownership (it owns a raw `GLFWwindow*`); a `unique_ptr` sidesteps that ownership hazard. The factory sets `glfwWindowHint(GLFW_VISIBLE, GLFW_FALSE)` before `glfwCreateWindow`, and on `glfwInit`/`glfwCreateWindow`/GLEW failure returns an error / throws rather than `exit()`. `main()`'s CLI branch maps that to `GL_CONTEXT_INIT_FAILED` and emits the failure JSON.
- The existing visible-window constructor is **left unchanged** (GUI path keeps today's behavior exactly).
- **Naming guardrail:** name this *offscreen / hidden-window GL context creation*, **not** "headless" — it is GLFW-backed, not EGL/OSMesa. Reserve "headless" for the run mode (no GUI), not the GL strategy.

The hidden window is small (default/1×1); the conversion pass renders into its own viewport/FBO sized by `setViewportResolutionForConversion`, not the window backbuffer.

## 7. Synchronous export with write verification (required revision #3)

Today `SceneManager::exportPly` does a synchronous readback but writes the file on a **detached `std::thread`** (`SceneManager.cpp:671`) — a one-shot process would race exit against the write.

Add a new **`SceneManager::exportPlySync(path, format)`** (a *separate method*, not a `sync=true` flag on `exportPly` — the async GUI method and sync CLI method have genuinely different contracts; a boolean flag hides the footgun at the call site). It:
1. Does the existing `glMemoryBarrier` + `glGetBufferSubData` readback into CPU memory.
2. Calls `parsers::savePlyVector` **on the calling thread**.
3. **Verifies the write**, with **overwrite as the defined behavior** (an existing `--output` is replaced): write to a **unique temp path in the same directory** as `--output`, check stream/file state for success, then move it onto the final path. Note `std::filesystem::rename` does **not** reliably atomic-replace an existing destination on Windows, so do **not** rename onto an existing file — instead remove any existing final file, then rename temp→final (a non-atomic replace, acceptable for v0). Any failure at any step → `OUTPUT_WRITE_FAILED`. (Requires `savePlyVector`/the writer to surface stream failure — return/throw — rather than swallow it.)

Success is reported only after the final file is closed and renamed. The existing async `exportPly` is untouched (GUI keeps using it).

## 8. CLI & result contract

**Mode selection:** **any args means CLI.** No args opens the GUI. Bad/partial args emit a failure JSON on stdout **plus a usage string on stderr** — never a silent GUI fallback.

```text
mesh2splat --input <a.glb> --output <a.ply>
           --format standard|pbr|compressed-pbr   (default: standard)
           --resolution 1024|2048|4096            (default: 1024)
```

- **Named formats** are canonical and map to the **export** enum (`savePlyVector`, `parsers.cpp:631-649`; GUI `formatLabels`, `ImGuiUi.hpp:120-122`): `standard=0`, `pbr=1`, `compressed-pbr=2`. Numeric aliases accepted but discouraged. *Note: this is the export-format axis, distinct from `RenderContext.format` (the load/interpret axis) — they share integers but are not the same enum.* `standard` is the GraphDeco-style 3DGS PLY that ve loads today, and is the default.
- **Resolution** is the fixed set `{1024, 2048, 4096}` (`ImGuiUi.hpp:116-118`), default `1024`.
- **stdout = exactly one JSON object**, nothing else. All logs/progress/GL diagnostics → **stderr**.
- The stubbed `argparser.cpp` is implemented (or replaced by a minimal parser) to back this.

**Success JSON:**
```json
{ "ok": true, "input": "a.glb", "output": "a.ply", "format": "standard",
  "resolution": 1024, "gaussianCount": 123456, "durationMs": 812 }
```

**Failure JSON** (includes normalized `input`/`output`/`format`/`resolution` **whenever args parsed successfully**, so Rook can log a complete failed-job record):
```json
{ "ok": false, "errorCode": "GLB_PARSE_FAILED", "message": "...",
  "input": "a.glb", "output": "a.ply", "format": "standard", "resolution": 1024 }
```

## 9. Error taxonomy (typed)

Process exit code mirrors the class; `errorCode` carries specifics. Every non-zero path still emits the one failure JSON on stdout.

| Exit | errorCode | Meaning |
|---|---|---|
| 0 | — | success |
| 2 | `BAD_ARGS` | missing/invalid args (also prints usage to stderr) |
| 3 | `INPUT_NOT_FOUND` | input path missing/unreadable |
| 4 | `GLB_PARSE_FAILED` | glTF/glb load failed |
| 5 | `GL_CONTEXT_INIT_FAILED` | glfwInit / hidden-window / GLEW failure (§6) |
| 6 | `CONVERSION_FAILED` | conversion produced zero gaussians or pass error |
| 7 | `OUTPUT_WRITE_FAILED` | readback/serialize/rename failure (§7) |

## 10. Testing strategy

**Gating (mesh2splat local loop — must pass, no other repo needed):**
- **Arg parsing:** names↔enum, defaults, invalid values, "any-args⇒CLI" / "no-args⇒GUI" boundary, partial-args→failure JSON + usage.
- **`ConvertOptions`/`ConvertResult`** construction/serialization.
- **Integration:** convert a small `.glb` **test fixture committed to the repo for this purpose** (the README's SciFiHelmet is an external download, not bundled — add a small committed fixture if none exists) headlessly → assert exit `0`, exactly one valid JSON object on stdout, `gaussianCount > 0`, and a `.ply` whose header matches `standard` 3DGS layout.
- **Failure paths:** missing input → `INPUT_NOT_FOUND`; unwritable output dir → `OUTPUT_WRITE_FAILED`; (where feasible) a forced context failure → `GL_CONTEXT_INIT_FAILED`.
- **Determinism:** same input+args across runs → identical `gaussianCount` and a stable PLY header.

**Non-gating (cross-repo acceptance smoke — proves the product pipeline, must NOT block the converter's local CI):**
- The produced `standard` `.ply` loads in **ve** (`new_forest_stub` `GaussianSplatPlyLoader`) without error. This brings in another repo/branch and is a manual acceptance step, not mesh2splat CI.

## 11. Build / packaging

Same single executable; behavior selected by `argc`. No new build target, no separate binary. ImGui remains linked but uninitialized on the CLI path. Windows-first (matches Rook); the Linux build inherits the same `main()` branch for free.

## 12. Risks & verification items

- **R1 (low):** a `GLFW_VISIBLE=false` context still creates the GBuffers/SSBOs and runs the conversion pass into its own FBO — verify on first live run.
- **R2 (low):** one `renderFrame()` suffices — grounded in pass self-disable; confirm via `gaussianCount > 0` + the ve-load smoke.
- **R3 (contract):** named-format mapping is frozen against the **export** enum, not the render-format enum (§8) — locked.
- **R4 (write):** verify `savePlyVector`/the writer can actually surface a write failure; if it currently swallows errors, the temp-write-then-rename + stream-state check in §7 is the mitigation.

## 13. Grounding references (read from source 2026-06-03)

- GUI main loop / `argc` ignored: `mesh2splat/src/main.cpp:11-64`
- Batch convert→export sequence to mirror: `mesh2splat/src/renderer/guiRendererConcreteMediator.cpp:134-264` (esp. `startBatchJob` :234, Exporting :169)
- Pass self-disable (one-frame determinism): `mesh2splat/src/renderer/renderer.cpp:145-160`
- Async export hazard: `mesh2splat/src/utils/SceneManager.cpp:651-674`
- Export format switch: `mesh2splat/src/parsers/parsers.cpp:631-649`
- Export format labels/options: `mesh2splat/src/imGuiUi/ImGuiUi.hpp:116-122`
- PLY writers: `mesh2splat/src/parsers/parsers.hpp:18-24`
- `GlewGlfwHandler` hard-exit + no `GLFW_VISIBLE` hint: `mesh2splat/src/glewGlfwHandlers/glewGlfwHandler.cpp:8-49`
- argparser stub: `mesh2splat/src/utils/argparser.cpp`
- License (BSD-3 + EA marks clauses; integration permitted): `mesh2splat/LICENSE.txt`

## 14. Decision log

- **A — one-shot CLI, process-per-file, fan-out in Rook.** B/C deferred until startup cost is measured.
- **X+ — minimal additive headless driver behind a small `HeadlessConverter` unit; CLI-only wiring; GUI untouched.** Y deferred; Z rejected.
- **Named export formats** canonical (`standard|pbr|compressed-pbr`); numeric aliases only.
- **Synchronous export via a new `exportPlySync`** (not a flag), with same-dir temp-write→verify→overwrite (remove-then-rename; non-atomic replace acceptable on Windows for v0).
- **Non-exiting hidden-context factory**; GUI constructor unchanged; "context creation" naming, not "headless".
- **`updateTransformations()` before `renderFrame()`** for parity with the GUI batch path.
- **Any args ⇒ CLI; no args ⇒ GUI; bad args ⇒ failure JSON + usage**, never silent GUI fallback.
- **ve-load is a non-gating cross-repo smoke**, not mesh2splat CI.
