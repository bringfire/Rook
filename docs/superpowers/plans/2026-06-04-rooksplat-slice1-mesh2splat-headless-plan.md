# RookSplat — Slice 1: mesh2splat Headless Converter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the forked `mesh2splat` a one-shot headless CLI mode (`--input <glb> --output <ply>`) that renders on an offscreen GL context, exports a 3DGS `.ply` synchronously, prints exactly one JSON result object, and exits with a typed code.

**Architecture:** Four additive units behind a CLI branch in `main()`; the existing ImGui GUI path is left byte-for-byte unchanged. Pure logic (arg parsing, format mapping, JSON, exit codes) lives in a new GL-free `cli/CliOptions` unit that is unit-tested with doctest. The GL-bound glue (offscreen context factory, synchronous export, `HeadlessConverter`) mirrors the existing GUI batch path and is verified by a cross-process Python integration test that runs the real binary against a committed fixture.

**Tech Stack:** C++17, OpenGL 4.5 (GLFW + GLEW), CMake + MSVC (Visual Studio multi-config generator), doctest (vendored single header) for unit tests, Python 3 stdlib for the integration driver, trimesh (throwaway venv, one-time) for fixture generation.

**Implementation repo:** `bringfire/mesh2splat` — local `C:\Users\aryan\source\repos\mesh2splat`. **No Rook code is touched by this slice.** This plan document lives in the Rook repo.

**Source spec:** `Rook/docs/superpowers/specs/2026-06-03-rooksplat-slice1-mesh2splat-headless-design.md`, committed on the Rook branch **`docs/rooksplat-slice1-design`** (commit `aaf6746`). This plan is committed on that same branch so the two travel together — the spec is **not** on `main`, so checking out that branch (or a worktree of it) is required to see both.

---

## Shell conventions

All commands target **PowerShell 7** (the project's environment). Notes for the executor:
- Exit codes: use `$LASTEXITCODE` (not Bash `$?`). Run an exe then read it, e.g. `& .\bin\Release\Mesh2Splat.exe --input; "exit: $LASTEXITCODE"`.
- Run a local exe with the call operator and backslashes: `& .\bin\Release\Mesh2Splat.exe ...`.
- `cmake`, `ctest`, `git`, and `python` invocations are identical across shells and are written once.
- If you prefer Git Bash, the Bash forms (`./bin/...`, `$?`, `mkdir -p`) work there instead — pick one shell and stay in it.

---

## Grounding: verified facts about the current code (read 2026-06-04)

All line numbers/signatures below were verified against the working tree at `mesh2splat` `main` (`c3d3d52`):

| Fact | Location |
|---|---|
| `main()` ignores `argc` entirely; constructs `GlewGlfwHandler` on the stack, runs GUI loop | `src/main.cpp:11-64` |
| GUI default gaussian std-dev = **0.65f** (`ImGuiUI ImGuiUI(0.65f, 0.5f)`) | `src/main.cpp:26` |
| `GlewGlfwHandler` ctor calls **`exit(-1)`** on `glfwInit` and `glfwCreateWindow` failure; no `GLFW_VISIBLE` hint; `init()` returns `-1` on GLEW failure (no exit) | `src/glewGlfwHandlers/glewGlfwHandler.cpp:8-49` |
| `InputParser` exists and works (token-based `getCmdOption`/`cmdOptionExists`) but is argc/argv-bound | `src/utils/argparser.{hpp,cpp}` |
| Export switch: `savePlyVector(FORMAT)` → `0`=`writeBinaryPlyStandardFormat` (standard 3DGS, ve-ready), `1`=`writePbrPLY`, `2`=`writeCompressedPbrPLY` | `src/parsers/parsers.cpp:631-651` |
| `writeBinaryPlyStandardFormat` opens an `ofstream` and **never checks stream state** (swallows write errors) — spec R4 | `src/parsers/parsers.cpp:431-466` |
| `exportPly` does synchronous readback but writes on a **detached `std::thread`** (race against process exit) | `src/utils/SceneManager.cpp:651-678` |
| GUI batch sequence to mirror: `resetModelMatrices()` → `setFormatType(0)` → `loadModel(path,parent)` → `gaussianBufferFromSize(res*res)` → `setViewportResolutionForConversion(res)` → `enableRenderPass(conversionPassName)`; `updateTransformations()` runs each frame **before** `renderFrame()` | `src/renderer/guiRendererConcreteMediator.cpp:134-251`, `src/main.cpp:51-53` |
| `renderFrame()` runs enabled passes then **self-disables each** ("Default to false for next frame") → one frame is deterministic | `src/renderer/renderer.cpp:145-160` |
| `numberOfGaussians` (type `GLint`) is set by the conversion pass after `renderFrame()` | `src/renderer/renderPasses/ConversionPass.cpp:59`; field at `RenderContext.hpp:83` |
| `setViewportResolutionForConversion(int)` sets `renderContext.resolutionTarget`; export `scaleMultiplier = gaussianStd / resolutionTarget` | `src/renderer/renderer.cpp:240-243`, `src/utils/SceneManager.cpp:668` |
| `gaussianStd` is set **only** via `setStdDevFromImGui()`; headless it value-inits to `0.0f` → `scaleMultiplier = 0` → all splats collapse to zero scale (**must seed 0.65f**) | `src/renderer/renderer.cpp:258-260` |
| `conversionPassName` is a global `static std::string ... = "conversion"` (usable anywhere that includes the header) | `src/renderer/RenderPasses.hpp:22` |
| ImGui format labels/options and resolution set `{1024,2048,4096}` confirm the spec's name↔enum and resolution sets | `src/imGuiUi/ImGuiUi.hpp:116-122` |
| Renderer/SceneManager method signatures used below | `src/renderer/renderer.hpp:24-47`, `src/utils/SceneManager.hpp:18-20` |
| CMake uses `file(GLOB_RECURSE SOURCES src/*.cpp)` into a **single executable**; no test target exists | `CMakeLists.txt:29-70` |
| Build = `cmake -S . -B build` then `cmake --build build --config Release` (MSVC multi-config) | `run_build_release.bat` |
| `.gitignore` ignores `*.ply` (outputs transient — fine) and `build/`; `tests/`, `thirdParty/doctest/`, and `*.glb` fixtures are committable (verified via `git check-ignore`) | `.gitignore:406,33` |
| 16 stray `std::cout`/`printf` sites in the conversion path (parsers, xatlas progress, SceneManager) would pollute stdout | grep across `src/` |

**Spec ↔ code reconciliation notes:**
- The spec calls `argparser.cpp` "stubbed"; it is actually a working `InputParser`. We do **not** modify it. The new pure parser operates on a `std::vector<std::string>` so it is unit-testable without `argv`. `InputParser` is left untouched.
- `setFormatType(0)` is the **render-context** axis (`RenderContext.format`), retained for batch-path parity — **not** the export format. The export format is passed independently to `exportPlySync`. (Spec §5/§8.)
- The PLY writer cannot surface stream failures (R4), so `exportPlySync` verifies the write **externally** (temp file exists + non-empty) rather than changing the writer's signature (which would ripple into the GUI/async path). This satisfies the spec's "temp-write → verify → rename" mitigation while honoring boundary X+ (shared code untouched).

---

## Test strategy (two gating tiers, per spec §10)

**Tier 1 — unit (TDD, fast, no GPU):** doctest exercises the GL-free `cli::` functions — format name↔enum, resolution validation, `parseCli` (defaults / missing / invalid), `isCliInvocation`, JSON serialization/escaping, exit-code mapping. New target `Mesh2SplatTests` compiles only `tests/unit/*.cpp` + `src/cli/CliOptions.cpp` (links no GL/GLFW/ImGui).

**Tier 2 — integration (needs the built binary + a GPU/GL context):** `tests/integration/test_headless.py` (stdlib only) runs the real binary against a committed fixture and asserts exit codes, single-JSON stdout, PLY header validity, `gaussianCount > 0`, determinism, overwrite, and every failure path. This is gating for the slice but, being GPU-bound, runs as an explicit step (not in a headless unit-CI box).

The GL-bound C++ units (Tasks 6–9) cannot be unit-tested without a GPU; their immediate gate is **compilation**, and their behavioral gate is Tier 2 (Tasks 11–12). This is called out honestly rather than faking GL unit tests.

---

## File structure

**New files (in `mesh2splat`):**
- `src/cli/CliOptions.hpp` — `ExportFormat`, `ConvertOptions`, `ConvertResult`, `ParseOutcome`, and pure free functions. GL-free.
- `src/cli/CliOptions.cpp` — implementations. (Globbed into the main exe **and** compiled into the test exe.)
- `src/cli/HeadlessConverter.hpp` / `.cpp` — `HeadlessConverter::convert(GLFWwindow*, const ConvertOptions&)`. GL-bound.
- `thirdParty/doctest/doctest.h` — vendored single-header test framework (MIT).
- `tests/unit/test_main.cpp` — doctest entry point.
- `tests/unit/test_cli_options.cpp` — Tier-1 unit tests.
- `tests/fixtures/generate_fixture.py` — one-time fixture generator (trimesh).
- `tests/fixtures/cube_textured.glb` — committed fixture used by Tier 2.
- `tests/fixtures/README.md` — provenance note for the fixture.
- `tests/integration/test_headless.py` — Tier-2 cross-process driver.

**Modified files (in `mesh2splat`):**
- `src/glewGlfwHandlers/glewGlfwHandler.hpp` / `.cpp` — add non-exiting `createOffscreen` factory + private adopting ctor. GUI ctor unchanged.
- `src/utils/SceneManager.hpp` / `.cpp` — add `exportPlySync`. `exportPly` unchanged.
- `src/main.cpp` — `argc` branch → `runHeadlessCli` / `runGui`; stdout-contract redirect. GUI body preserved verbatim inside `runGui`.
- `CMakeLists.txt` — `enable_testing()` + `Mesh2SplatTests` target + `add_test`.
- `README.md` — short headless-CLI usage section.

---

## Task 0: Branch the mesh2splat repo

**Files:** none (git only).

- [ ] **Step 1: Create the feature branch**

All work happens in the mesh2splat repo. Run from `C:\Users\aryan\source\repos\mesh2splat`:

```bash
git switch -c feature/headless-cli
git status
```
Expected: on branch `feature/headless-cli`, clean tree (off `main` = `c3d3d52`).

---

## Task 1: Vendor doctest and stand up the unit-test target

**Files:**
- Create: `thirdParty/doctest/doctest.h`
- Create: `tests/unit/test_main.cpp`
- Create: `tests/unit/test_cli_options.cpp`
- Modify: `CMakeLists.txt` (append after the `set_target_properties(Mesh2Splat ...)` block, i.e. after line 103)

- [ ] **Step 1: Vendor the doctest single header**

Download the doctest v2.4.11 single header into the new path (it is one self-contained file, MIT-licensed). From the mesh2splat root (PowerShell):

```powershell
New-Item -ItemType Directory -Force -Path thirdParty/doctest | Out-Null
curl.exe -L -o thirdParty/doctest/doctest.h https://raw.githubusercontent.com/doctest/doctest/v2.4.11/doctest/doctest.h
```
Expected: `thirdParty/doctest/doctest.h` exists and is ~200KB. Verify the first lines contain `// doctest.h - the lightest feature-rich C++ single-header testing framework`.

If network access is unavailable, obtain `doctest.h` (v2.4.x) by any means and place it at exactly that path; nothing else in the plan depends on the version.

- [ ] **Step 2: Create the doctest entry point**

Create `tests/unit/test_main.cpp`:

```cpp
#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include "doctest.h"
```

- [ ] **Step 3: Create a smoke test**

Create `tests/unit/test_cli_options.cpp`:

```cpp
#include "doctest.h"

TEST_CASE("doctest harness is alive") {
    CHECK(1 + 1 == 2);
}
```

- [ ] **Step 4: Add the test target to CMake**

Append to `CMakeLists.txt` (after line 103, the end of `set_target_properties(Mesh2Splat ...)`):

```cmake

# ---------------------------------------------------------------------------
# Unit tests: headless CLI pure logic only (no GL / GLFW / ImGui linkage).
# ---------------------------------------------------------------------------
enable_testing()

add_executable(Mesh2SplatTests
    ${CMAKE_SOURCE_DIR}/tests/unit/test_main.cpp
    ${CMAKE_SOURCE_DIR}/tests/unit/test_cli_options.cpp
    ${CMAKE_SOURCE_DIR}/src/cli/CliOptions.cpp
)

target_include_directories(Mesh2SplatTests PRIVATE
    ${CMAKE_SOURCE_DIR}/src
    ${THIRD_PARTY_DIR}/doctest
)

add_test(NAME unit COMMAND Mesh2SplatTests)
```

> NOTE: `Mesh2SplatTests` references `src/cli/CliOptions.cpp`, created in Task 2. So this task's configure step will fail to find that file until Task 2. To keep Task 1 self-contained and green, create a placeholder now (it is fleshed out in Task 2):

Create `src/cli/CliOptions.cpp` with a placeholder:
```cpp
// Headless CLI pure logic. Implementations added incrementally (see plan).
#include "cli/CliOptions.hpp"
```
Create `src/cli/CliOptions.hpp` with the include guard only (fleshed out in Task 2):
```cpp
#pragma once
```

- [ ] **Step 5: Configure, build, and run the smoke test**

From the mesh2splat root:
```bash
cmake -S . -B build
cmake --build build --config Release --target Mesh2SplatTests
ctest --test-dir build -C Release --output-on-failure
```
Expected: configure succeeds, `Mesh2SplatTests` builds, `ctest` reports `1 test ... Passed` (the "doctest harness is alive" case).

- [ ] **Step 6: Commit**

```bash
git add thirdParty/doctest/doctest.h tests/unit CMakeLists.txt src/cli/CliOptions.hpp src/cli/CliOptions.cpp
git commit -m "test(cli): vendor doctest and add Mesh2SplatTests unit target"
```

---

## Task 2: ExportFormat enum + format name↔enum mapping

**Files:**
- Modify: `src/cli/CliOptions.hpp`
- Modify: `src/cli/CliOptions.cpp`
- Modify: `tests/unit/test_cli_options.cpp`

- [ ] **Step 1: Write the failing tests**

Replace the smoke-test body in `tests/unit/test_cli_options.cpp` with:

```cpp
#include "doctest.h"
#include "cli/CliOptions.hpp"

using cli::ExportFormat;

TEST_CASE("parseFormat accepts canonical names") {
    ExportFormat f;
    CHECK((cli::parseFormat("standard", f) && f == ExportFormat::Standard));
    CHECK((cli::parseFormat("pbr", f) && f == ExportFormat::Pbr));
    CHECK((cli::parseFormat("compressed-pbr", f) && f == ExportFormat::CompressedPbr));
}

TEST_CASE("parseFormat accepts numeric aliases") {
    ExportFormat f;
    CHECK((cli::parseFormat("0", f) && f == ExportFormat::Standard));
    CHECK((cli::parseFormat("1", f) && f == ExportFormat::Pbr));
    CHECK((cli::parseFormat("2", f) && f == ExportFormat::CompressedPbr));
}

TEST_CASE("parseFormat rejects junk") {
    ExportFormat f;
    CHECK_FALSE(cli::parseFormat("ply", f));
    CHECK_FALSE(cli::parseFormat("3", f));
    CHECK_FALSE(cli::parseFormat("", f));
}

TEST_CASE("formatToString round-trips canonical names") {
    CHECK(cli::formatToString(ExportFormat::Standard) == "standard");
    CHECK(cli::formatToString(ExportFormat::Pbr) == "pbr");
    CHECK(cli::formatToString(ExportFormat::CompressedPbr) == "compressed-pbr");
}

TEST_CASE("ExportFormat integer values match savePlyVector switch") {
    CHECK(static_cast<unsigned int>(ExportFormat::Standard) == 0u);
    CHECK(static_cast<unsigned int>(ExportFormat::Pbr) == 1u);
    CHECK(static_cast<unsigned int>(ExportFormat::CompressedPbr) == 2u);
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cmake --build build --config Release --target Mesh2SplatTests
```
Expected: **compile/link failure** — `parseFormat`, `formatToString`, `ExportFormat` are undeclared.

- [ ] **Step 3: Declare the types and functions**

Set `src/cli/CliOptions.hpp` to:

```cpp
#pragma once
#include <string>
#include <vector>
#include <cstdint>

namespace cli {

// Integer values are load-bearing: they are passed verbatim to
// parsers::savePlyVector(FORMAT) (0=standard 3DGS, 1=pbr, 2=compressed-pbr).
enum class ExportFormat : unsigned int {
    Standard      = 0,
    Pbr           = 1,
    CompressedPbr = 2,
};

// Accepts "standard|pbr|compressed-pbr" and numeric "0|1|2".
bool parseFormat(const std::string& s, ExportFormat& out);
std::string formatToString(ExportFormat f);

} // namespace cli
```

- [ ] **Step 4: Implement the functions**

Set `src/cli/CliOptions.cpp` to:

```cpp
// Headless CLI pure logic. GL-free; unit-tested via Mesh2SplatTests.
#include "cli/CliOptions.hpp"

namespace cli {

bool parseFormat(const std::string& s, ExportFormat& out) {
    if (s == "standard"       || s == "0") { out = ExportFormat::Standard;      return true; }
    if (s == "pbr"            || s == "1") { out = ExportFormat::Pbr;           return true; }
    if (s == "compressed-pbr" || s == "2") { out = ExportFormat::CompressedPbr; return true; }
    return false;
}

std::string formatToString(ExportFormat f) {
    switch (f) {
        case ExportFormat::Standard:      return "standard";
        case ExportFormat::Pbr:           return "pbr";
        case ExportFormat::CompressedPbr: return "compressed-pbr";
    }
    return "standard";
}

} // namespace cli
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cmake --build build --config Release --target Mesh2SplatTests
ctest --test-dir build -C Release --output-on-failure
```
Expected: all format test cases pass.

- [ ] **Step 6: Commit**

```bash
git add src/cli/CliOptions.hpp src/cli/CliOptions.cpp tests/unit/test_cli_options.cpp
git commit -m "feat(cli): ExportFormat enum + format name<->enum mapping"
```

---

## Task 3: Resolution validation, option/result structs, CLI-mode detection

**Files:**
- Modify: `src/cli/CliOptions.hpp`
- Modify: `src/cli/CliOptions.cpp`
- Modify: `tests/unit/test_cli_options.cpp`

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_cli_options.cpp`)

```cpp
TEST_CASE("parseResolution accepts the fixed set") {
    int r = 0;
    CHECK((cli::parseResolution("1024", r) && r == 1024));
    CHECK((cli::parseResolution("2048", r) && r == 2048));
    CHECK((cli::parseResolution("4096", r) && r == 4096));
}

TEST_CASE("parseResolution rejects everything else") {
    int r = 0;
    CHECK_FALSE(cli::parseResolution("512", r));
    CHECK_FALSE(cli::parseResolution("1025", r));
    CHECK_FALSE(cli::parseResolution("abc", r));
    CHECK_FALSE(cli::parseResolution("", r));
}

TEST_CASE("ConvertOptions has spec defaults") {
    cli::ConvertOptions o;
    CHECK(o.format == cli::ExportFormat::Standard);
    CHECK(o.resolution == 1024);
}

TEST_CASE("isCliInvocation: any args => CLI, none => GUI") {
    CHECK_FALSE(cli::isCliInvocation(1)); // program name only
    CHECK(cli::isCliInvocation(2));
    CHECK(cli::isCliInvocation(7));
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cmake --build build --config Release --target Mesh2SplatTests
```
Expected: compile failure — `parseResolution`, `ConvertOptions`, `ConvertResult`, `isCliInvocation` undeclared.

- [ ] **Step 3: Add declarations** (append inside `namespace cli` in `src/cli/CliOptions.hpp`, before the closing `}`)

```cpp
// resolution must be one of {1024, 2048, 4096}.
bool parseResolution(const std::string& s, int& out);

struct ConvertOptions {
    std::string  inputPath;
    std::string  outputPath;
    ExportFormat format     = ExportFormat::Standard;
    int          resolution = 1024;
};

struct ConvertResult {
    bool        ok            = false;
    uint64_t    gaussianCount = 0;
    double      durationMs    = 0.0;
    std::string errorCode;   // "" on success
    std::string message;
};

// any args => CLI mode; no args (argc == 1) => GUI.
bool isCliInvocation(int argc);
```

- [ ] **Step 4: Add implementations** (append inside `namespace cli` in `src/cli/CliOptions.cpp`)

```cpp
bool parseResolution(const std::string& s, int& out) {
    if (s == "1024") { out = 1024; return true; }
    if (s == "2048") { out = 2048; return true; }
    if (s == "4096") { out = 4096; return true; }
    return false;
}

bool isCliInvocation(int argc) { return argc > 1; }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cmake --build build --config Release --target Mesh2SplatTests
ctest --test-dir build -C Release --output-on-failure
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/cli/CliOptions.hpp src/cli/CliOptions.cpp tests/unit/test_cli_options.cpp
git commit -m "feat(cli): resolution validation, Convert{Options,Result}, isCliInvocation"
```

---

## Task 4: `parseCli` — argv tokens → options with validation

**Files:**
- Modify: `src/cli/CliOptions.hpp`
- Modify: `src/cli/CliOptions.cpp`
- Modify: `tests/unit/test_cli_options.cpp`

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_cli_options.cpp`)

```cpp
TEST_CASE("parseCli: minimal valid args use defaults") {
    auto r = cli::parseCli({"--input", "a.glb", "--output", "a.ply"});
    REQUIRE(r.ok);
    CHECK(r.options.inputPath == "a.glb");
    CHECK(r.options.outputPath == "a.ply");
    CHECK(r.options.format == cli::ExportFormat::Standard);
    CHECK(r.options.resolution == 1024);
}

TEST_CASE("parseCli: full args parsed") {
    auto r = cli::parseCli({"--input", "in.glb", "--output", "out.ply",
                            "--format", "pbr", "--resolution", "4096"});
    REQUIRE(r.ok);
    CHECK(r.options.format == cli::ExportFormat::Pbr);
    CHECK(r.options.resolution == 4096);
}

TEST_CASE("parseCli: missing --input or --output => BAD_ARGS") {
    CHECK(cli::parseCli({"--output", "a.ply"}).errorCode == "BAD_ARGS");
    CHECK(cli::parseCli({"--input", "a.glb"}).errorCode == "BAD_ARGS");
    CHECK_FALSE(cli::parseCli({"--output", "a.ply"}).ok);
}

TEST_CASE("parseCli: invalid --format => BAD_ARGS") {
    auto r = cli::parseCli({"--input", "a.glb", "--output", "a.ply", "--format", "ply"});
    CHECK_FALSE(r.ok);
    CHECK(r.errorCode == "BAD_ARGS");
}

TEST_CASE("parseCli: invalid --resolution => BAD_ARGS") {
    auto r = cli::parseCli({"--input", "a.glb", "--output", "a.ply", "--resolution", "999"});
    CHECK_FALSE(r.ok);
    CHECK(r.errorCode == "BAD_ARGS");
}

TEST_CASE("parseCli: unknown flag => BAD_ARGS") {
    auto r = cli::parseCli({"--input", "a.glb", "--output", "a.ply", "--bogus", "x"});
    CHECK_FALSE(r.ok);
    CHECK(r.errorCode == "BAD_ARGS");
}

TEST_CASE("parseCli: stray positional token => BAD_ARGS") {
    auto r = cli::parseCli({"--input", "a.glb", "--output", "a.ply", "junk"});
    CHECK_FALSE(r.ok);
    CHECK(r.errorCode == "BAD_ARGS");
}

TEST_CASE("parseCli: missing value after --input => BAD_ARGS") {
    auto r = cli::parseCli({"--input"});
    CHECK_FALSE(r.ok);
    CHECK(r.errorCode == "BAD_ARGS");
}

TEST_CASE("parseCli: flag value that looks like a flag => BAD_ARGS") {
    // '--input --output x.ply' must not silently treat '--output' as the input path.
    auto r = cli::parseCli({"--input", "--output", "x.ply"});
    CHECK_FALSE(r.ok);
    CHECK(r.errorCode == "BAD_ARGS");
}

TEST_CASE("parseCli: missing value after --format => BAD_ARGS") {
    auto r = cli::parseCli({"--input", "a.glb", "--output", "a.ply", "--format"});
    CHECK_FALSE(r.ok);
    CHECK(r.errorCode == "BAD_ARGS");
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cmake --build build --config Release --target Mesh2SplatTests
```
Expected: compile failure — `parseCli` and `ParseOutcome` undeclared.

- [ ] **Step 3: Add declarations** (append inside `namespace cli` in `src/cli/CliOptions.hpp`)

```cpp
struct ParseOutcome {
    bool           ok = false;
    ConvertOptions options;
    std::string    errorCode;  // "BAD_ARGS" on failure
    std::string    message;
};

// Parse argv[1..] tokens. Applies spec defaults; validates format/resolution.
ParseOutcome parseCli(const std::vector<std::string>& args);
```

- [ ] **Step 4: Add implementation** (append inside `namespace cli` in `src/cli/CliOptions.cpp`)

```cpp
static bool isKnownFlag(const std::string& s) {
    return s == "--input" || s == "--output" || s == "--format" || s == "--resolution";
}
static bool looksLikeFlag(const std::string& s) {
    return s.rfind("--", 0) == 0;  // starts with "--"
}

ParseOutcome parseCli(const std::vector<std::string>& args) {
    ParseOutcome r;
    auto fail = [&r](const std::string& msg) -> ParseOutcome {
        r.ok = false;
        r.errorCode = "BAD_ARGS";
        r.message = msg;
        return r;
    };

    std::string in, out, fmt, res;
    bool haveIn = false, haveOut = false, haveFmt = false, haveRes = false;

    // Strict walk: only known flags, each must be followed by a non-flag value,
    // no leftover/unknown tokens.
    for (size_t i = 0; i < args.size(); ++i) {
        const std::string& tok = args[i];
        if (!isKnownFlag(tok)) {
            return fail("unexpected argument: " + tok);
        }
        if (i + 1 >= args.size() || looksLikeFlag(args[i + 1])) {
            return fail("missing value for " + tok);
        }
        const std::string& val = args[i + 1];
        if      (tok == "--input")      { in  = val; haveIn  = true; }
        else if (tok == "--output")     { out = val; haveOut = true; }
        else if (tok == "--format")     { fmt = val; haveFmt = true; }
        else if (tok == "--resolution") { res = val; haveRes = true; }
        ++i;  // consume the value token
    }

    if (!haveIn || !haveOut) {
        return fail("both --input and --output are required");
    }

    ConvertOptions o;
    o.inputPath  = in;
    o.outputPath = out;

    if (haveFmt && !parseFormat(fmt, o.format)) {
        return fail("invalid --format (expected standard|pbr|compressed-pbr)");
    }
    if (haveRes && !parseResolution(res, o.resolution)) {
        return fail("invalid --resolution (expected 1024|2048|4096)");
    }

    r.ok = true;
    r.options = o;
    return r;
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cmake --build build --config Release --target Mesh2SplatTests
ctest --test-dir build -C Release --output-on-failure
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/cli/CliOptions.hpp src/cli/CliOptions.cpp tests/unit/test_cli_options.cpp
git commit -m "feat(cli): parseCli with defaults and BAD_ARGS validation"
```

---

## Task 5: JSON serialization, exit-code mapping, usage string

**Files:**
- Modify: `src/cli/CliOptions.hpp`
- Modify: `src/cli/CliOptions.cpp`
- Modify: `tests/unit/test_cli_options.cpp`

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_cli_options.cpp`)

```cpp
TEST_CASE("jsonEscape escapes quotes and backslashes (Windows paths)") {
    CHECK(cli::jsonEscape(R"(C:\a\b.glb)") == R"(C:\\a\\b.glb)");
    CHECK(cli::jsonEscape(R"(say "hi")") == R"(say \"hi\")");
}

TEST_CASE("makeSuccessJson contains all fields") {
    cli::ConvertOptions o;
    o.inputPath = "a.glb"; o.outputPath = "a.ply";
    o.format = cli::ExportFormat::Standard; o.resolution = 1024;
    cli::ConvertResult r;
    r.ok = true; r.gaussianCount = 123456; r.durationMs = 812.4;
    const std::string j = cli::makeSuccessJson(o, r);
    CHECK(j.find("\"ok\":true") != std::string::npos);
    CHECK(j.find("\"format\":\"standard\"") != std::string::npos);
    CHECK(j.find("\"resolution\":1024") != std::string::npos);
    CHECK(j.find("\"gaussianCount\":123456") != std::string::npos);
    CHECK(j.find("\"durationMs\":812") != std::string::npos);
}

TEST_CASE("makeFailureJson with options echoes normalized fields") {
    cli::ConvertOptions o;
    o.inputPath = "a.glb"; o.outputPath = "a.ply";
    o.format = cli::ExportFormat::Pbr; o.resolution = 2048;
    const std::string j = cli::makeFailureJson(&o, "OUTPUT_WRITE_FAILED", "disk full");
    CHECK(j.find("\"ok\":false") != std::string::npos);
    CHECK(j.find("\"errorCode\":\"OUTPUT_WRITE_FAILED\"") != std::string::npos);
    CHECK(j.find("\"message\":\"disk full\"") != std::string::npos);
    CHECK(j.find("\"input\":\"a.glb\"") != std::string::npos);
    CHECK(j.find("\"format\":\"pbr\"") != std::string::npos);
    CHECK(j.find("\"resolution\":2048") != std::string::npos);
}

TEST_CASE("makeFailureJson without options omits normalized fields (BAD_ARGS)") {
    const std::string j = cli::makeFailureJson(nullptr, "BAD_ARGS", "missing --output");
    CHECK(j.find("\"ok\":false") != std::string::npos);
    CHECK(j.find("\"errorCode\":\"BAD_ARGS\"") != std::string::npos);
    CHECK(j.find("\"input\"") == std::string::npos);
    CHECK(j.find("\"resolution\"") == std::string::npos);
}

TEST_CASE("exitCodeFor maps the error taxonomy") {
    CHECK(cli::exitCodeFor("") == 0);
    CHECK(cli::exitCodeFor("BAD_ARGS") == 2);
    CHECK(cli::exitCodeFor("INPUT_NOT_FOUND") == 3);
    CHECK(cli::exitCodeFor("GLB_PARSE_FAILED") == 4);
    CHECK(cli::exitCodeFor("GL_CONTEXT_INIT_FAILED") == 5);
    CHECK(cli::exitCodeFor("CONVERSION_FAILED") == 6);
    CHECK(cli::exitCodeFor("OUTPUT_WRITE_FAILED") == 7);
    CHECK(cli::exitCodeFor("SOMETHING_ELSE") == 1);
}

TEST_CASE("usageString mentions the flags") {
    const std::string u = cli::usageString();
    CHECK(u.find("--input") != std::string::npos);
    CHECK(u.find("--output") != std::string::npos);
    CHECK(u.find("--format") != std::string::npos);
    CHECK(u.find("--resolution") != std::string::npos);
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cmake --build build --config Release --target Mesh2SplatTests
```
Expected: compile failure — `jsonEscape`, `makeSuccessJson`, `makeFailureJson`, `exitCodeFor`, `usageString` undeclared.

- [ ] **Step 3: Add declarations** (append inside `namespace cli` in `src/cli/CliOptions.hpp`)

```cpp
// Hand-rolled JSON (no dependency). Escapes quotes/backslashes/control chars.
std::string jsonEscape(const std::string& s);
std::string makeSuccessJson(const ConvertOptions& o, const ConvertResult& r);
// o == nullptr when args did not parse (BAD_ARGS) -> minimal object (no echoed fields).
std::string makeFailureJson(const ConvertOptions* o, const std::string& errorCode,
                            const std::string& message);

// errorCode -> process exit code (see error taxonomy). Unknown -> 1.
int exitCodeFor(const std::string& errorCode);

std::string usageString();
```

- [ ] **Step 4: Add implementations** (append inside `namespace cli` in `src/cli/CliOptions.cpp`; also add `#include <sstream>` at the top of the file)

```cpp
std::string jsonEscape(const std::string& s) {
    std::string out;
    out.reserve(s.size() + 8);
    for (char c : s) {
        switch (c) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n";  break;
            case '\r': out += "\\r";  break;
            case '\t': out += "\\t";  break;
            default:   out += c;      break;
        }
    }
    return out;
}

std::string makeSuccessJson(const ConvertOptions& o, const ConvertResult& r) {
    std::ostringstream s;
    s << "{\"ok\":true"
      << ",\"input\":\""       << jsonEscape(o.inputPath)  << "\""
      << ",\"output\":\""      << jsonEscape(o.outputPath) << "\""
      << ",\"format\":\""      << formatToString(o.format) << "\""
      << ",\"resolution\":"    << o.resolution
      << ",\"gaussianCount\":" << r.gaussianCount
      << ",\"durationMs\":"    << static_cast<long long>(r.durationMs)
      << "}";
    return s.str();
}

std::string makeFailureJson(const ConvertOptions* o, const std::string& errorCode,
                            const std::string& message) {
    std::ostringstream s;
    s << "{\"ok\":false"
      << ",\"errorCode\":\"" << jsonEscape(errorCode) << "\""
      << ",\"message\":\""   << jsonEscape(message)   << "\"";
    if (o) {
        s << ",\"input\":\""    << jsonEscape(o->inputPath)  << "\""
          << ",\"output\":\""   << jsonEscape(o->outputPath) << "\""
          << ",\"format\":\""   << formatToString(o->format) << "\""
          << ",\"resolution\":" << o->resolution;
    }
    s << "}";
    return s.str();
}

int exitCodeFor(const std::string& e) {
    if (e.empty())                     return 0;
    if (e == "BAD_ARGS")               return 2;
    if (e == "INPUT_NOT_FOUND")        return 3;
    if (e == "GLB_PARSE_FAILED")       return 4;
    if (e == "GL_CONTEXT_INIT_FAILED") return 5;
    if (e == "CONVERSION_FAILED")      return 6;
    if (e == "OUTPUT_WRITE_FAILED")    return 7;
    return 1;
}

std::string usageString() {
    return
        "Usage: Mesh2Splat --input <a.glb> --output <a.ply>\n"
        "                  [--format standard|pbr|compressed-pbr]  (default: standard)\n"
        "                  [--resolution 1024|2048|4096]           (default: 1024)\n"
        "With no arguments, Mesh2Splat launches the GUI.";
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cmake --build build --config Release --target Mesh2SplatTests
ctest --test-dir build -C Release --output-on-failure
```
Expected: every Tier-1 unit test passes. This completes the GL-free logic.

- [ ] **Step 6: Commit**

```bash
git add src/cli/CliOptions.hpp src/cli/CliOptions.cpp tests/unit/test_cli_options.cpp
git commit -m "feat(cli): JSON serialization, exit-code mapping, usage string"
```

---

## Task 6: Non-exiting offscreen GL context factory

**Files:**
- Modify: `src/glewGlfwHandlers/glewGlfwHandler.hpp`
- Modify: `src/glewGlfwHandlers/glewGlfwHandler.cpp`

This unit is GL-bound; its gate is compilation now and Tier-2 behavior later (Task 11). It adds a non-exiting path and **does not change** the existing visible-window constructor.

- [ ] **Step 1: Add the factory + result struct + private adopting ctor to the header**

Edit `src/glewGlfwHandlers/glewGlfwHandler.hpp`. Add `#include <memory>` and `#include <string>` after the existing includes, then replace the class body so it reads exactly:

```cpp
#include "renderer/IoHandler.hpp"
#include "utils/utils.hpp"
#include <memory>
#include <string>

class GlewGlfwHandler
{
public:
	GlewGlfwHandler(glm::ivec2 windowDimensions, std::string windowName);
	~GlewGlfwHandler() {};
	int init();
	void updateResize();

	static void framebuffer_size_callback(GLFWwindow* window, int width, int height)
	{
		glViewport(0, 0, width, height);
	}

	GLFWwindow* getWindow();

	// Non-exiting offscreen (hidden-window) context creation for the headless
	// CLI path. On any failure returns { handler == nullptr, errorCode, message }
	// instead of calling exit(). The GUI constructor above is unchanged.
	struct OffscreenContextResult {
		std::unique_ptr<GlewGlfwHandler> handler;  // null on failure
		std::string errorCode;                     // "" on success
		std::string message;
	};
	static OffscreenContextResult createOffscreen(glm::ivec2 windowDimensions);

private:
	// Adopts an already-created window without exit()/hints; used by createOffscreen.
	explicit GlewGlfwHandler(GLFWwindow* existingWindow);

	GLFWwindow* window;
};
```

- [ ] **Step 2: Implement the factory + adopting ctor in the .cpp**

Append to `src/glewGlfwHandlers/glewGlfwHandler.cpp` (after the existing `getWindow()` definition):

```cpp

GlewGlfwHandler::GlewGlfwHandler(GLFWwindow* existingWindow)
{
    this->window = existingWindow;
    updateResize();
}

GlewGlfwHandler::OffscreenContextResult GlewGlfwHandler::createOffscreen(glm::ivec2 windowDimensions)
{
    OffscreenContextResult result;

    if (!glfwInit()) {
        result.errorCode = "GL_CONTEXT_INIT_FAILED";
        result.message   = "glfwInit failed";
        return result;
    }

    glfwWindowHint(GLFW_DOUBLEBUFFER, GLFW_TRUE);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 4);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 5);
    glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
    glfwWindowHint(GLFW_VISIBLE, GLFW_FALSE);   // offscreen / hidden window

    GLFWwindow* w = glfwCreateWindow(windowDimensions.x, windowDimensions.y,
                                     "Mesh2Splat (headless)", NULL, NULL);
    if (!w) {
        glfwTerminate();
        result.errorCode = "GL_CONTEXT_INIT_FAILED";
        result.message   = "glfwCreateWindow failed";
        return result;
    }

    std::unique_ptr<GlewGlfwHandler> handler(new GlewGlfwHandler(w));
    if (handler->init() == -1) {   // makes context current + glewInit; returns -1 (no exit) on GLEW failure
        result.errorCode = "GL_CONTEXT_INIT_FAILED";
        result.message   = "glewInit failed";
        return result;
    }

    result.handler = std::move(handler);
    return result;
}
```

- [ ] **Step 3: Build the main target to verify it compiles**

```bash
cmake --build build --config Release --target Mesh2Splat
```
Expected: `Mesh2Splat` links (the GUI path is untouched; the new symbols compile). No behavior change yet — nothing calls `createOffscreen`.

- [ ] **Step 4: Commit**

```bash
git add src/glewGlfwHandlers/glewGlfwHandler.hpp src/glewGlfwHandlers/glewGlfwHandler.cpp
git commit -m "feat(gl): non-exiting offscreen context factory (createOffscreen)"
```

---

## Task 7: `SceneManager::exportPlySync` — synchronous, write-verified export

**Files:**
- Modify: `src/utils/SceneManager.hpp`
- Modify: `src/utils/SceneManager.cpp`

- [ ] **Step 1: Declare `exportPlySync`**

In `src/utils/SceneManager.hpp`, add the declaration directly below the existing `exportPly` line (after line 20):

```cpp
    void exportPly(const std::string outputFile, unsigned int exportFormat);
    // Synchronous, write-verified export for the one-shot CLI path. Writes to a
    // same-directory temp file, verifies it exists and is non-empty, then replaces
    // the destination (overwrite). Returns false on any readback/serialize/replace
    // failure (caller maps to OUTPUT_WRITE_FAILED). The async exportPly above is
    // left untouched (the GUI keeps using it).
    bool exportPlySync(const std::string& outputFile, unsigned int exportFormat);
```

- [ ] **Step 2: Implement `exportPlySync`**

In `src/utils/SceneManager.cpp`, add `#include <filesystem>` and `#include <string>` near the top (with the other includes), plus the platform header for the process id:

```cpp
#ifdef _WIN32
  #include <process.h>  // _getpid
#else
  #include <unistd.h>   // getpid
#endif
```

Then append this definition after the existing `exportPly` definition (after line 678):

```cpp

bool SceneManager::exportPlySync(const std::string& outputFile, unsigned int exportFormat)
{
    // --- synchronous GPU readback (identical to exportPly, minus the detached thread) ---
    glBindBuffer(GL_SHADER_STORAGE_BUFFER, renderContext.gaussianBuffer);

    std::vector<utils::GaussianDataSSBO> cpuData(renderContext.numberOfGaussians);

    glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT);

    glGetBufferSubData(
        GL_SHADER_STORAGE_BUFFER,
        0,
        renderContext.numberOfGaussians * sizeof(utils::GaussianDataSSBO),
        cpuData.data()
    );

    glBindBuffer(GL_SHADER_STORAGE_BUFFER, 0);

    const float scaleMultiplier =
        renderContext.gaussianStd / static_cast<float>(renderContext.resolutionTarget);

    namespace fs = std::filesystem;
    std::error_code ec;
    const fs::path finalPath(outputFile);

    // Same-directory, process-unique temp name so a stale/concurrent temp from
    // another invocation in the same directory cannot collide.
#ifdef _WIN32
    const auto pid = _getpid();
#else
    const auto pid = getpid();
#endif
    fs::path tempPath = finalPath;
    tempPath += "." + std::to_string(pid) + ".m2s.tmp";

    // Clear any stale temp from a previously aborted run.
    fs::remove(tempPath, ec);

    // --- serialize to the temp path on the calling thread ---
    try {
        parsers::savePlyVector(tempPath.string(), cpuData, exportFormat, scaleMultiplier);
    } catch (...) {
        fs::remove(tempPath, ec);
        return false;
    }

    // --- verify: the PLY writer does not surface ofstream failures, so we check
    //     externally. An unwritable / non-existent output directory leaves no temp
    //     file, which is caught here. Fail closed on any filesystem error (e.g.
    //     file_size returning uintmax_t(-1) with ec set). ---
    std::error_code existEc, sizeEc;
    const bool tempExists = fs::exists(tempPath, existEc);
    const auto tempSize = fs::file_size(tempPath, sizeEc);
    if (!tempExists || existEc || sizeEc || tempSize == 0) {
        fs::remove(tempPath, ec);
        return false;
    }

    // --- overwrite the destination: remove existing, then rename temp -> final.
    //     std::filesystem::rename does not reliably atomic-replace on Windows, so
    //     we remove-then-rename; the non-atomic replace is acceptable for v0. ---
    fs::remove(finalPath, ec);
    fs::rename(tempPath, finalPath, ec);
    if (ec) {
        fs::remove(tempPath, ec);
        return false;
    }

    return true;
}
```

- [ ] **Step 3: Build the main target to verify it compiles**

```bash
cmake --build build --config Release --target Mesh2Splat
```
Expected: links cleanly. Behavior verified in Tier-2 (Tasks 11–12).

- [ ] **Step 4: Commit**

```bash
git add src/utils/SceneManager.hpp src/utils/SceneManager.cpp
git commit -m "feat(export): SceneManager::exportPlySync (sync + temp-write/verify/overwrite)"
```

---

## Task 8: `HeadlessConverter` — drive the conversion on the offscreen context

**Files:**
- Create: `src/cli/HeadlessConverter.hpp`
- Create: `src/cli/HeadlessConverter.cpp`

This mirrors `GuiRendererConcreteMediator::startBatchJob` plus the per-frame `updateTransformations()` ordering, on the calling thread, exactly once.

- [ ] **Step 1: Create the header**

Create `src/cli/HeadlessConverter.hpp`:

```cpp
#pragma once
#include "cli/CliOptions.hpp"

struct GLFWwindow;  // forward declaration (GLFW typedefs struct GLFWwindow)

class HeadlessConverter {
public:
    // `context` must already be created and current (see GlewGlfwHandler::createOffscreen).
    // HeadlessConverter does not own or destroy the context.
    cli::ConvertResult convert(GLFWwindow* context, const cli::ConvertOptions& opts);
};
```

- [ ] **Step 2: Create the implementation**

Create `src/cli/HeadlessConverter.cpp`:

```cpp
#include "cli/HeadlessConverter.hpp"

#include "renderer/renderer.hpp"
#include "renderer/RenderPasses.hpp"   // conversionPassName
#include "utils/Camera.hpp"
#include <GLFW/glfw3.h>

#include <chrono>
#include <filesystem>

namespace {
// The GUI constructs ImGuiUI(0.65f, 0.5f) in main.cpp, i.e. the default gaussian
// std-dev is 0.65. Headless has no ImGui slider, so we seed the same default;
// otherwise scaleMultiplier = gaussianStd / resolutionTarget = 0 and every
// exported splat collapses to zero scale.
constexpr float kDefaultGaussianStd = 0.65f;
}  // namespace

cli::ConvertResult HeadlessConverter::convert(GLFWwindow* context, const cli::ConvertOptions& opts)
{
    using clock = std::chrono::steady_clock;
    cli::ConvertResult r;

    // Same camera the GUI uses (main.cpp).
    Camera camera(
        glm::vec3(0.0f, 0.0f, 5.0f),
        glm::vec3(0.0f, 1.0f, 0.0f),
        -90.0f,
        0.0f
    );

    Renderer renderer(context, camera);
    renderer.initialize();
    renderer.setStdDevFromImGui(kDefaultGaussianStd);

    const auto t0 = clock::now();

    // --- mirror GuiRendererConcreteMediator::startBatchJob ---
    renderer.resetModelMatrices();
    renderer.setFormatType(0);  // RENDER-context state for parity; NOT the export format.

    const std::string parentFolder =
        std::filesystem::path(opts.inputPath).parent_path().string();

    if (!renderer.getSceneManager().loadModel(opts.inputPath, parentFolder)) {
        r.ok = false;
        r.errorCode = "GLB_PARSE_FAILED";
        r.message = "failed to load glb: " + opts.inputPath;
        return r;
    }

    renderer.gaussianBufferFromSize(opts.resolution * opts.resolution);
    renderer.setViewportResolutionForConversion(opts.resolution);
    renderer.enableRenderPass(conversionPassName);

    // The GUI batch loop calls UpdateTransforms each frame before renderFrame().
    renderer.updateTransformations();
    // One frame runs the conversion pass; passes self-disable afterward (deterministic).
    renderer.renderFrame();

    const int count = renderer.getRenderContext()->numberOfGaussians;
    if (count <= 0) {
        r.ok = false;
        r.errorCode = "CONVERSION_FAILED";
        r.message = "conversion produced zero gaussians";
        return r;
    }

    if (!renderer.getSceneManager().exportPlySync(opts.outputPath,
                                                  static_cast<unsigned int>(opts.format))) {
        r.ok = false;
        r.errorCode = "OUTPUT_WRITE_FAILED";
        r.message = "failed to write output: " + opts.outputPath;
        return r;
    }

    const auto t1 = clock::now();
    r.ok = true;
    r.gaussianCount = static_cast<uint64_t>(count);
    r.durationMs = std::chrono::duration<double, std::milli>(t1 - t0).count();
    return r;
}
```

- [ ] **Step 3: Build the main target to verify it compiles**

`src/cli/HeadlessConverter.cpp` is picked up automatically by `GLOB_RECURSE` (it is under `src/`), so re-run configure first so CMake re-globs:

```bash
cmake -S . -B build
cmake --build build --config Release --target Mesh2Splat
```
Expected: links cleanly. Still no behavior change — `main()` does not call it yet.

- [ ] **Step 4: Commit**

```bash
git add src/cli/HeadlessConverter.hpp src/cli/HeadlessConverter.cpp
git commit -m "feat(cli): HeadlessConverter mirrors GUI batch path, one-shot on calling thread"
```

---

## Task 9: Wire the CLI branch into `main()`

**Files:**
- Modify: `src/main.cpp`

- [ ] **Step 1: Rewrite `main.cpp` with the argc branch and stdout-contract redirect**

Replace the entire contents of `src/main.cpp` with:

```cpp
///////////////////////////////////////////////////////////////////////////////
//         Mesh2Splat: fast mesh to 3D gaussian splat conversion             //
//        Copyright (c) 2025 Electronic Arts Inc. All rights reserved.       //
///////////////////////////////////////////////////////////////////////////////

#include "utils/normalizedUvUnwrapping.hpp"
#include "renderer/renderer.hpp"
#include "glewGlfwHandlers/glewGlfwHandler.hpp"
#include "renderer/guiRendererConcreteMediator.hpp"
#include "cli/CliOptions.hpp"
#include "cli/HeadlessConverter.hpp"

#include <iostream>
#include <vector>
#include <string>
#include <filesystem>
#include <cstdio>
#include <stdexcept>
#ifdef _WIN32
  #include <io.h>      // _dup, _dup2, _fileno, _close
#else
  #include <unistd.h>  // dup, dup2, fileno, close
#endif

namespace {
// RAII: redirect the process stdout FILE DESCRIPTOR to stderr for the guard's
// lifetime, so BOTH C++ std::cout and C printf/fprintf(stdout) from library code
// (glTF loader, xatlas progress, etc.) are kept off the real stdout. A std::cout
// rdbuf swap alone would NOT catch printf, which writes to fd 1 directly. The
// destructor restores stdout on every scope exit, including stack unwinding from
// an exception, so the one JSON object we print afterwards lands on real stdout.
// If the redirect cannot be established, the constructor throws (no partial state)
// and the caller's try/catch maps it to CONVERSION_FAILED rather than silently
// running the conversion with an unguarded stdout.
class StdoutToStderrRedirect {
public:
    StdoutToStderrRedirect() {
        std::cout.flush();
        std::fflush(stdout);
#ifdef _WIN32
        savedFd_ = _dup(_fileno(stdout));
        if (savedFd_ == -1) throw std::runtime_error("stdout redirect: _dup failed");
        if (_dup2(_fileno(stderr), _fileno(stdout)) == -1) {
            _close(savedFd_);
            savedFd_ = -1;
            throw std::runtime_error("stdout redirect: _dup2 failed");
        }
#else
        savedFd_ = dup(fileno(stdout));
        if (savedFd_ == -1) throw std::runtime_error("stdout redirect: dup failed");
        if (dup2(fileno(stderr), fileno(stdout)) == -1) {
            close(savedFd_);
            savedFd_ = -1;
            throw std::runtime_error("stdout redirect: dup2 failed");
        }
#endif
    }
    ~StdoutToStderrRedirect() {
        std::cout.flush();
        std::fflush(stdout);
        if (savedFd_ == -1) return;
#ifdef _WIN32
        _dup2(savedFd_, _fileno(stdout));
        _close(savedFd_);
#else
        dup2(savedFd_, fileno(stdout));
        close(savedFd_);
#endif
        savedFd_ = -1;
    }
    StdoutToStderrRedirect(const StdoutToStderrRedirect&) = delete;
    StdoutToStderrRedirect& operator=(const StdoutToStderrRedirect&) = delete;
private:
    int savedFd_ = -1;
};
}  // namespace

static int runGui();
static int runHeadlessCli(const std::vector<std::string>& args);

int main(int argc, char** argv) {
    if (cli::isCliInvocation(argc)) {                       // any args => CLI
        std::vector<std::string> args(argv + 1, argv + argc);
        return runHeadlessCli(args);
    }
    return runGui();                                        // no args => GUI
}

static int runHeadlessCli(const std::vector<std::string>& args) {
    namespace fs = std::filesystem;

    cli::ParseOutcome parsed = cli::parseCli(args);
    if (!parsed.ok) {
        std::cout << cli::makeFailureJson(nullptr, parsed.errorCode, parsed.message) << std::endl;
        std::cerr << cli::usageString() << std::endl;
        return cli::exitCodeFor(parsed.errorCode);          // 2 BAD_ARGS
    }

    const cli::ConvertOptions& opts = parsed.options;

    std::error_code ec;
    if (!fs::exists(opts.inputPath, ec)) {
        std::cout << cli::makeFailureJson(&opts, "INPUT_NOT_FOUND", "input file not found") << std::endl;
        return cli::exitCodeFor("INPUT_NOT_FOUND");         // 3
    }

    GlewGlfwHandler::OffscreenContextResult ctx =
        GlewGlfwHandler::createOffscreen(glm::ivec2(1, 1));
    if (!ctx.handler) {
        std::cout << cli::makeFailureJson(&opts, ctx.errorCode, ctx.message) << std::endl;
        return cli::exitCodeFor(ctx.errorCode);             // 5 GL_CONTEXT_INIT_FAILED
    }

    // Contract: stdout carries EXACTLY one JSON object. The conversion path prints
    // to both std::cout AND C printf (xatlas), so we redirect at the fd level
    // (StdoutToStderrRedirect). The guard restores stdout on scope exit even if
    // convert() throws; the surrounding try/catch maps any unexpected exception to
    // CONVERSION_FAILED so we always emit exactly one failure JSON.
    cli::ConvertResult result;
    try {
        StdoutToStderrRedirect guard;
        HeadlessConverter converter;
        result = converter.convert(ctx.handler->getWindow(), opts);
    } catch (const std::exception& e) {
        result.ok = false;
        result.errorCode = "CONVERSION_FAILED";
        result.message = std::string("unexpected error: ") + e.what();
    } catch (...) {
        result.ok = false;
        result.errorCode = "CONVERSION_FAILED";
        result.message = "unexpected error";
    }

    if (result.ok) {
        std::cout << cli::makeSuccessJson(opts, result) << std::endl;
    } else {
        std::cout << cli::makeFailureJson(&opts, result.errorCode, result.message) << std::endl;
    }

    glfwTerminate();
    return cli::exitCodeFor(result.errorCode);              // 0 / 4 / 6 / 7
}

static int runGui() {
    GlewGlfwHandler glewGlfwHandler(glm::ivec2(1080, 720), "Mesh2Splat");

    Camera camera(
        glm::vec3(0.0f, 0.0f, 5.0f),
        glm::vec3(0.0f, 1.0f, 0.0f),
        -90.0f,
        0.0f
    );

    IoHandler ioHandler(glewGlfwHandler.getWindow(), camera);
    if(glewGlfwHandler.init() == -1) return -1;

    ioHandler.setupCallbacks();

    ImGuiUI ImGuiUI(0.65f, 0.5f); //TODO: give a meaning to these params
    ImGuiUI.initialize(glewGlfwHandler.getWindow());

    Renderer renderer(glewGlfwHandler.getWindow(), camera);
    renderer.initialize();
    GuiRendererConcreteMediator guiRendererMediator(renderer, ImGuiUI);

    float deltaTime = 0.0f;
    float lastFrame = 0.0f;

    while (!glfwWindowShouldClose(glewGlfwHandler.getWindow())) {

        float currentFrame = static_cast<float>(glfwGetTime());
        deltaTime = currentFrame - lastFrame;
        lastFrame = currentFrame;

        glfwPollEvents();

        ioHandler.processInput(deltaTime);

        renderer.clearingPrePass(ImGuiUI.getSceneBackgroundColor());

        ImGuiUI.preframe();
        ImGuiUI.renderUI();

        guiRendererMediator.update();

        renderer.renderFrame();

        ImGuiUI.displayGaussianCounts(renderer.getTotalGaussianCount(), renderer.getVisibleGaussianCount());
        ImGuiUI.postframe();

        glfwSwapBuffers(glewGlfwHandler.getWindow());
    }

    glfwTerminate();

    return 0;
}
```

- [ ] **Step 2: Full build**

```bash
cmake --build build --config Release --target Mesh2Splat
```
Expected: `bin/Release/Mesh2Splat.exe` builds.

- [ ] **Step 3: Smoke the GUI path is untouched and the bad-args path works**

```powershell
& .\bin\Release\Mesh2Splat.exe --input; "exit: $LASTEXITCODE"
```
Expected: a single JSON line on stdout with `"errorCode":"BAD_ARGS"`, the usage string on stderr, and `exit: 2`. (Running with no args would open the GUI — skip in automation.)

- [ ] **Step 4: Commit**

```bash
git add src/main.cpp
git commit -m "feat(cli): wire headless CLI branch into main() with stdout-contract redirect"
```

---

## Task 10: Generate and commit the test fixture

**Files:**
- Create: `tests/fixtures/generate_fixture.py`
- Create: `tests/fixtures/cube_textured.glb` (generated, committed)
- Create: `tests/fixtures/README.md`

- [ ] **Step 1: Write the generator**

Create `tests/fixtures/generate_fixture.py`:

```python
#!/usr/bin/env python3
"""Generate the small textured-cube glb fixture used by the headless integration test.

Run ONCE and commit the resulting cube_textured.glb; the integration test consumes the
committed file (not this script). Self-owned content (repo license), no third-party asset.

Setup (throwaway venv per project convention):
    python -m venv .scratch/fixture-venv
    .scratch/fixture-venv/Scripts/pip install trimesh pillow numpy
    .scratch/fixture-venv/Scripts/python tests/fixtures/generate_fixture.py
"""
import os
import numpy as np
import trimesh
from PIL import Image

here = os.path.dirname(os.path.abspath(__file__))

# 64x64 checker baseColor texture so the conversion has color to bake into splats.
size, tile = 64, 8
img = np.zeros((size, size, 3), dtype=np.uint8)
for y in range(size):
    for x in range(size):
        hi = ((x // tile) + (y // tile)) % 2 == 0
        c = 230 if hi else 40
        img[y, x] = (c, 80, 255 - c)
texture = Image.fromarray(img, mode="RGB")

# Unit cube. mesh2splat re-unwraps UVs internally via xatlas, so simple planar UVs
# are sufficient; what matters is that a baseColorTexture is present.
mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
xy = mesh.vertices[:, :2].astype(np.float64)
rng = xy.max(axis=0) - xy.min(axis=0)
rng[rng == 0] = 1.0
uv = (xy - xy.min(axis=0)) / rng
mesh.visual = trimesh.visual.TextureVisuals(
    uv=uv,
    material=trimesh.visual.material.PBRMaterial(baseColorTexture=texture),
)

out = os.path.join(here, "cube_textured.glb")
mesh.export(out)
print("wrote", out, os.path.getsize(out), "bytes")
```

- [ ] **Step 2: Run the generator once**

```powershell
python -m venv .scratch/fixture-venv
& .scratch/fixture-venv/Scripts/python.exe -m pip install trimesh pillow numpy
& .scratch/fixture-venv/Scripts/python.exe tests/fixtures/generate_fixture.py
```
Expected: prints `wrote .../tests/fixtures/cube_textured.glb <N> bytes` and the `.glb` exists (a few KB).

- [ ] **Step 3: Sanity-check the fixture against the real binary**

```powershell
& .\bin\Release\Mesh2Splat.exe --input tests/fixtures/cube_textured.glb --output .scratch/probe.ply; "exit: $LASTEXITCODE"
```
Expected: one JSON line with `"ok":true` and `"gaussianCount"` > 0, and `exit: 0`. If `gaussianCount` is 0 or it fails, the fixture is the suspect — adjust the generator (ensure a baseColorTexture is present) and regenerate before proceeding. (`.scratch/probe.ply` is ignored by `*.ply`.)

- [ ] **Step 4: Write the provenance note**

Create `tests/fixtures/README.md`:

```markdown
# Test fixtures

`cube_textured.glb` — a unit cube with a 64×64 checker baseColor texture, generated by
`generate_fixture.py`. Self-owned content under the repository license; regenerate with
that script if it ever needs to change. Consumed by `tests/integration/test_headless.py`.
```

- [ ] **Step 5: Commit the fixture, generator, and note**

```bash
git add tests/fixtures/generate_fixture.py tests/fixtures/cube_textured.glb tests/fixtures/README.md
git commit -m "test(fixtures): committed textured-cube glb + generator for headless tests"
```

---

## Task 11: Integration test — success, determinism, overwrite

**Files:**
- Create: `tests/integration/test_headless.py`

- [ ] **Step 1: Write the integration driver (success cases)**

Create `tests/integration/test_headless.py`:

```python
#!/usr/bin/env python3
"""Tier-2 cross-process integration test for the mesh2splat headless CLI.

Requires a built Mesh2Splat binary and a working GPU/GL context. Run from the
mesh2splat repo root:
    python tests/integration/test_headless.py [path-to-binary]
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "cube_textured.glb")
failures = []


def find_binary():
    if len(sys.argv) > 1:
        return sys.argv[1]
    for cand in (
        os.path.join(ROOT, "bin", "Release", "Mesh2Splat.exe"),
        os.path.join(ROOT, "bin", "Debug", "Mesh2Splat.exe"),
        os.path.join(ROOT, "bin", "Release", "Mesh2Splat"),
    ):
        if os.path.exists(cand):
            return cand
    raise SystemExit("Mesh2Splat binary not found; pass the path as the first argument")


BIN = find_binary()


def run(args):
    p = subprocess.run([BIN] + args, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def parse_single_json(stdout):
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected exactly one stdout line, got {len(lines)}: {lines!r}"
    return json.loads(lines[0])


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    if not cond:
        failures.append(name)


def read_header(path):
    with open(path, "rb") as f:
        head = f.read(4096)
    return head


def header_text(head):
    return head.split(b"end_header")[0].decode("ascii", "ignore")


def vertex_count(path):
    txt = header_text(read_header(path))
    for line in txt.splitlines():
        if line.startswith("element vertex"):
            return int(line.split()[-1])
    return -1


with tempfile.TemporaryDirectory() as d:
    out = os.path.join(d, "out.ply")

    # 1. success path
    rc, so, se = run(["--input", FIXTURE, "--output", out,
                      "--format", "standard", "--resolution", "1024"])
    j = parse_single_json(so)
    check("success exit 0", rc == 0)
    check("ok true", j.get("ok") is True)
    check("gaussianCount > 0", j.get("gaussianCount", 0) > 0)
    check("format echoed", j.get("format") == "standard")
    check("resolution echoed", j.get("resolution") == 1024)
    check("output exists", os.path.exists(out))
    if os.path.exists(out):
        head = read_header(out)
        txt = header_text(head)
        check("ply magic", head[:3] == b"ply")
        check("standard 3dgs props", all(p in txt for p in
              ("element vertex", "f_dc_0", "scale_0", "rot_0")))
        check("vertex count == gaussianCount", vertex_count(out) == j.get("gaussianCount"))

    # 2. determinism: a second run gives the same gaussianCount and header vertex count
    out2 = os.path.join(d, "out2.ply")
    rc2, so2, _ = run(["--input", FIXTURE, "--output", out2, "--resolution", "1024"])
    j2 = parse_single_json(so2)
    check("determinism rc 0", rc2 == 0)
    check("determinism gaussianCount stable", j.get("gaussianCount") == j2.get("gaussianCount"))
    check("determinism vertex count stable", vertex_count(out) == vertex_count(out2))

    # 3. overwrite an existing output file
    rc3, so3, _ = run(["--input", FIXTURE, "--output", out])  # out already exists
    j3 = parse_single_json(so3)
    check("overwrite ok", rc3 == 0 and j3.get("ok") is True)

print()
if failures:
    print(f"{len(failures)} FAILED:", failures)
    sys.exit(1)
print("ALL PASSED")
sys.exit(0)
```

- [ ] **Step 2: Run the integration test**

Ensure the Release binary is current, then:
```bash
cmake --build build --config Release --target Mesh2Splat
python tests/integration/test_headless.py
```
Expected: every line `PASS`, final `ALL PASSED`, exit 0.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_headless.py
git commit -m "test(integration): headless success, determinism, overwrite"
```

---

## Task 12: Integration test — failure paths

**Files:**
- Modify: `tests/integration/test_headless.py`

- [ ] **Step 1: Append the failure-path assertions**

Insert the following block in `tests/integration/test_headless.py` immediately **before** the final `print()` / `if failures:` block (i.e. after the `with tempfile.TemporaryDirectory()` block closes):

```python
# 4. missing input -> exit 3 INPUT_NOT_FOUND (echoes normalized opts)
rc, so, se = run(["--input", "does_not_exist.glb", "--output", "x.ply"])
j = parse_single_json(so)
check("missing-input exit 3", rc == 3)
check("missing-input errorCode", j.get("errorCode") == "INPUT_NOT_FOUND")
check("missing-input echoes input", j.get("input") == "does_not_exist.glb")

# 5. bad args (no --output) -> exit 2 BAD_ARGS + usage on stderr, no echoed opts
rc, so, se = run(["--input", FIXTURE])
j = parse_single_json(so)
check("bad-args exit 2", rc == 2)
check("bad-args errorCode", j.get("errorCode") == "BAD_ARGS")
check("bad-args usage on stderr", "Usage:" in se)
check("bad-args omits echoed opts", "input" not in j)

# 6. unwritable output (parent dir does not exist) -> exit 7 OUTPUT_WRITE_FAILED
bad_out = os.path.join(ROOT, "tests", "fixtures", "no_such_dir", "out.ply")
rc, so, se = run(["--input", FIXTURE, "--output", bad_out])
j = parse_single_json(so)
check("unwritable exit 7", rc == 7)
check("unwritable errorCode", j.get("errorCode") == "OUTPUT_WRITE_FAILED")
```

- [ ] **Step 2: Run the full integration suite**

```bash
python tests/integration/test_headless.py
```
Expected: all `PASS` (success + determinism + overwrite + the three failure paths), `ALL PASSED`, exit 0.

> If `unwritable exit 7` instead reports a success or a different code, confirm `exportPlySync` is writing the temp into the (non-existent) destination directory — the temp must be same-dir as `--output`, so a missing parent directory yields no temp file and thus `OUTPUT_WRITE_FAILED`.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_headless.py
git commit -m "test(integration): INPUT_NOT_FOUND, BAD_ARGS+usage, OUTPUT_WRITE_FAILED paths"
```

---

## Task 13: Document the headless CLI in the README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a headless-CLI section**

Append to `README.md`:

```markdown
## Headless CLI (offscreen conversion)

Mesh2Splat runs headless when given any arguments (no arguments still opens the GUI):

```text
Mesh2Splat --input <a.glb> --output <a.ply>
           [--format standard|pbr|compressed-pbr]   (default: standard)
           [--resolution 1024|2048|4096]            (default: 1024)
```

One `.glb` in, one 3DGS `.ply` out, rendered on a hidden-window GL context, exported
synchronously. Exactly one JSON object is written to **stdout**; all logs go to **stderr**.

Success:
```json
{ "ok": true, "input": "a.glb", "output": "a.ply", "format": "standard",
  "resolution": 1024, "gaussianCount": 123456, "durationMs": 812 }
```

Failure (exit codes): `2` BAD_ARGS · `3` INPUT_NOT_FOUND · `4` GLB_PARSE_FAILED ·
`5` GL_CONTEXT_INIT_FAILED · `6` CONVERSION_FAILED · `7` OUTPUT_WRITE_FAILED.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document the headless conversion CLI"
```

---

## Task 14: Final gate — full clean build + both test tiers

**Files:** none (verification only).

- [ ] **Step 1: Clean configure + build both targets**

```bash
cmake -S . -B build
cmake --build build --config Release --target Mesh2Splat
cmake --build build --config Release --target Mesh2SplatTests
```
Expected: both binaries build with no errors.

- [ ] **Step 2: Run Tier-1 unit tests**

```bash
ctest --test-dir build -C Release --output-on-failure
```
Expected: the `unit` test passes (all doctest cases green).

- [ ] **Step 3: Run Tier-2 integration tests**

```bash
python tests/integration/test_headless.py
```
Expected: `ALL PASSED`.

- [ ] **Step 4: Confirm the working tree is clean and the branch is ready**

```bash
git status
git log --oneline main..HEAD
```
Expected: clean tree; the commit list shows Tasks 1–13. The branch `feature/headless-cli` is ready to push to `bringfire/mesh2splat` and open a PR.

> **Cross-repo acceptance smoke (non-gating, manual, NOT part of this CI):** load a produced `standard` `.ply` in ve (`new_forest_stub` `GaussianSplatPlyLoader`) and confirm it renders. This proves the product pipeline but must not block the converter's local loop (spec §10).

---

## Self-review (run against the spec)

**1. Spec coverage** — every section maps to a task:

| Spec § | Requirement | Task |
|---|---|---|
| §1, §4.4, §8 | CLI conversion mode; any-args⇒CLI / no-args⇒GUI | 3 (`isCliInvocation`), 9 (`main`) |
| §4.1, §5 | `HeadlessConverter` mirrors batch path, one frame, calling thread | 8 |
| §4.2 | `ConvertOptions` / `ConvertResult` POD structs | 3 |
| §4.3, §6 | Non-exiting hidden-window factory (unique_ptr, GLFW_VISIBLE=false, no exit) | 6 |
| §5 rev #2 | `updateTransformations()` before `renderFrame()` | 8 |
| §5 | `setFormatType(0)` parity, not export selector | 8 (comment), grounding note |
| §7 rev #3 | `exportPlySync` separate method; temp→verify→remove-then-rename overwrite | 7 |
| §8 | Named formats canonical + numeric alias; export-enum mapping | 2 |
| §8 | stdout = one JSON; logs→stderr | 9 (fd-level RAII redirect + try/catch), 11 (asserts exactly one stdout line) |
| §8 | success/failure JSON shapes; failure echoes opts when parsed | 5 |
| §9 | Typed error taxonomy + exit codes | 5 (`exitCodeFor`), wired in 8/9 |
| §10 | Gating unit tests (arg parse, options, json) | 2–5 |
| §10 | Gating integration (fixture, exit0, single JSON, gaussianCount>0, PLY header, determinism, failure paths) | 10–12 |
| §10 | Committed fixture | 10 |
| §10 | ve-load non-gating smoke | 14 (note, explicitly out of CI) |
| §11 | Same executable, behavior by argc; ImGui linked but unused on CLI | 9 |

**2. Placeholder scan** — no `TBD`/`later`/"add error handling"; every code step shows complete code; every test step shows real assertions and expected output. ✓

**3. Type consistency** — names are stable across tasks: `ExportFormat{Standard,Pbr,CompressedPbr}`, `ConvertOptions{inputPath,outputPath,format,resolution}`, `ConvertResult{ok,gaussianCount,durationMs,errorCode,message}`, `ParseOutcome{ok,options,errorCode,message}`, `parseCli`, `parseFormat`, `parseResolution`, `formatToString`, `isCliInvocation`, `jsonEscape`, `makeSuccessJson`, `makeFailureJson`, `exitCodeFor`, `usageString`, `GlewGlfwHandler::createOffscreen` / `OffscreenContextResult{handler,errorCode,message}`, `SceneManager::exportPlySync`, `HeadlessConverter::convert`. All consistent with the verified source signatures (`loadModel`, `gaussianBufferFromSize`, `setViewportResolutionForConversion`, `enableRenderPass`, `updateTransformations`, `renderFrame`, `getRenderContext()->numberOfGaussians`, `getSceneManager`, `setFormatType`, `resetModelMatrices`, `setStdDevFromImGui`). ✓

**Plan-discovered issues folded in (beyond the spec):**
- **gaussianStd default (0.65f)** — spec did not mention it; headless would otherwise collapse all splat scales to zero. Seeded in Task 8.
- **stdout pollution** — 16 stray `std::cout`/`printf` sites in the conversion path (incl. xatlas `printf` in `normalizedUvUnwrapping.cpp`) would break the "one JSON object" contract. Handled by a **file-descriptor-level** RAII redirect (`StdoutToStderrRedirect`) around the conversion in Task 9 — catches both `std::cout` and C `printf` (a `rdbuf` swap alone would miss `printf`), restores stdout on exception unwind, and a surrounding `try/catch` maps unexpected throws to `CONVERSION_FAILED`. No sweep of shared code, honoring boundary X+. (Both points raised by senior review, 2026-06-04.)
- **No test framework existed** — Task 1 vendors doctest and adds a separate, GL-free test target.
- **`argparser.cpp` is not a stub** — left untouched; a `vector<string>`-based parser is used for testability.

**Senior-review round 2 refinements folded in (2026-06-04):**
- **Checked redirect syscalls** — `StdoutToStderrRedirect`'s ctor now checks `_dup`/`_dup2` (and POSIX `dup`/`dup2`) return values and **throws** on failure (closing any half-acquired fd first), so the surrounding `try/catch` maps it to `CONVERSION_FAILED` instead of running the conversion with an unguarded stdout. (Task 9.)
- **Process-unique temp path** — `exportPlySync` now uses `<final>.<pid>.m2s.tmp` (same directory) instead of a fixed `.m2s.tmp` suffix, so it cannot collide with a stale/concurrent temp. (Task 7.)
- Reviewer confirmed the boundary-preserving choices (no shared `ConversionService` refactor; external file-size verification around the existing writer rather than changing the shared parser/export surface) are correct for Slice 1, and approved Subagent-Driven execution.

**Senior-review round 3 — applied during execution, reflected above (2026-06-04):**
- **Strict `parseCli`** (Task 4) — the original lenient parser accepted `--input --output x.ply` (treating `--output` as the input path) and silently ignored trailing positional tokens. The implementation above now walks argv strictly: known flags only, each must be followed by a non-flag value, no leftover/unknown tokens → `BAD_ARGS`. Six extra unit tests cover unknown flag, stray positional, missing value after `--input`, flag-shaped value, and missing value after `--format`.
- **Fail-closed write verification** (Task 7) — `exportPlySync` now checks the `error_code` of both `exists` and `file_size` (the latter returns `uintmax_t(-1)` with `ec` set on failure; the old `== 0`-only check let that pass).
- **Declined:** adding `glfwDestroyWindow(w)` on the GLEW-init-failure path in `createOffscreen` — `init()` already calls `glfwTerminate()`, which destroys all remaining windows; an explicit destroy afterward would be a use-after-terminate. No leak (the adopting `unique_ptr`'s `~GlewGlfwHandler(){}` never touches the window) and no double-free.

**Execution outcome (2026-06-04):** all 15 tasks implemented in `bringfire/mesh2splat` on branch `feature/headless-cli`; unit 25 cases / 81 assertions + Python integration all green; first real conversion produced 6,291,456 gaussians (1024²×6). Shipped as PR https://github.com/bringfire/mesh2splat/pull/1 (`feature/headless-cli → main`, within the fork).
