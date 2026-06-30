# Rook Mesh2Splat Export Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a gated, deterministic first-slice pipeline that captures selected Rhino mesh data through Rook, writes a strict Mesh2Splat-compatible GLB, runs the forked headless Mesh2Splat CLI, validates the PLY, and registers artifacts.

**Architecture:** The plan is intentionally sequenced as prerequisite milestones. Mesh2Splat must first expose deterministic sampling density and capacity reporting; then a repeatable sizing fixture and live matrix choose Rook's default; only after that does Rook implement native capture, Python GLB/process orchestration, filesystem safety, and artifact registration.

**Tech Stack:** C++17/CMake/doctest/OpenGL in `C:/Users/aryan/source/repos/mesh2splat`; Rhino 8 C++ SDK/native HTTP handlers in `C:/Users/aryan/source/repos/Rook/src/RookNative`; Python 3/pytest/Pillow/SQLite in `C:/Users/aryan/source/repos/Rook/mcp_server`.

---

## Gate Rules

- Do not start Milestone 3 Rook tool implementation until Milestone 1 Mesh2Splat fork work and Milestone 2 fixture/sizing work are complete.
- Keep all first-slice safety guarantees from `C:/Users/aryan/source/repos/Rook/docs/superpowers/specs/2026-06-29-rook-mesh2splat-export-pipeline-design.md`.
- Work on dedicated branches:
  - Rook: `codex/mesh2splat-export-pipeline`
  - Mesh2Splat: `codex/sampling-resolution-cli`
- Commit after each task group that leaves tests passing in that repository.

## File Map

Mesh2Splat fork:

- Modify `C:/Users/aryan/source/repos/mesh2splat/src/cli/CliOptions.hpp`: rename the headless density field to `samplingResolution`, expose parser names, and extend result schema fields.
- Modify `C:/Users/aryan/source/repos/mesh2splat/src/cli/CliOptions.cpp`: add `--sampling-resolution`, keep `--resolution` as a compatibility alias, reject `--effective-resolution`, and emit required JSON fields.
- Modify `C:/Users/aryan/source/repos/mesh2splat/src/cli/HeadlessConverter.hpp`: return attempted/capacity diagnostics.
- Modify `C:/Users/aryan/source/repos/mesh2splat/src/cli/HeadlessConverter.cpp`: use `samplingResolution`, detect capacity overflow after conversion and before PLY export, and avoid writing PLY on overflow.
- Create `C:/Users/aryan/source/repos/mesh2splat/src/renderer/renderPasses/ConversionCapacity.hpp`: single source for the Mesh2Splat conversion capacity formula.
- Modify `C:/Users/aryan/source/repos/mesh2splat/src/renderer/renderPasses/ConversionPass.cpp`: use the shared capacity helper for GL buffer allocation and `u_maxGaussians`.
- Modify `C:/Users/aryan/source/repos/mesh2splat/tests/unit/test_cli_options.cpp`: unit-test parsing, aliases, help text, JSON schema, and capacity JSON.
- Modify `C:/Users/aryan/source/repos/mesh2splat/tests/integration/test_headless.py`: live/local conversion assertions for `--sampling-resolution`.
- Modify `C:/Users/aryan/source/repos/mesh2splat/tests/fixtures/generate_fixture.py`: generate both cube and building fixtures.
- Create `C:/Users/aryan/source/repos/mesh2splat/tests/integration/run_sampling_matrix.py`: live/local matrix runner that records density evidence.
- Create `C:/Users/aryan/source/repos/mesh2splat/tests/fixtures/building_lowpoly_textured_v1.glb`: deterministic generated sizing fixture.
- Create `C:/Users/aryan/source/repos/mesh2splat/tests/fixtures/building_lowpoly_textured_v1.meta.json`: fixture contract metadata.

Rook:

- Modify `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/artifacts.py`: add `mesh2splat_capture` source rank and owned-rerun metadata replacement.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/__init__.py`: package marker.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/contracts.py`: request/result dataclasses, constants, error envelopes, and cap defaults.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/output_safety.py`: output directory, run manifest, exclusive file creation, and cleanup rules.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/executable.py`: Mesh2Splat executable/config lookup and working-directory validation.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/textures.py`: texture path trust, byte/pixel/decode caps, scalar fallback decisions, PNG conversion.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/glb_writer.py`: strict binary GLB writer and in-memory GLB validator helpers.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/process.py`: sanitized child environment, argv execution, tolerant JSON parsing, timeout/process-tree termination.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/ply.py`: format-specific PLY header/count/byte validation.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/pipeline.py`: orchestration from request validation through artifact registration.
- Modify `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/server.py`: register the MCP tool and call `pipeline.export_mesh2splat_capture`.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_mesh2splat_contracts.py`: request validation tests.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_mesh2splat_output_safety.py`: output directory, manifest, exclusive write, and cleanup tests.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_mesh2splat_executable.py`: executable/config lookup and working-directory tests.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_mesh2splat_process.py`: subprocess environment, argv, timeout, and stdout parsing tests.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_mesh2splat_textures.py`: texture trust, decode caps, and fallback tests.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_mesh2splat_glb_writer.py`: GLB writer and GLB validator tests.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_mesh2splat_ply.py`: PLY estimate and validator tests.
- Create `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_mesh2splat_pipeline.py`: orchestration tests.
- Modify `C:/Users/aryan/source/repos/Rook/src/RookNative/Handlers/MeshHandler.h`: add the mesh2splat capture handler declaration to an already compiled handler header.
- Modify `C:/Users/aryan/source/repos/Rook/src/RookNative/Handlers/MeshHandler.cpp`: implement the Rhino UI-thread capture route in an already compiled translation unit.
- Modify `C:/Users/aryan/source/repos/Rook/src/RookNative/RookServer.cpp`: register `POST /mesh2splat/capture`.

## Milestone 1: Mesh2Splat Fork CLI, Schema, And Capacity Contract

### Task 1: Prepare Mesh2Splat Branch

**Files:**
- Repository: `C:/Users/aryan/source/repos/mesh2splat`

- [ ] **Step 1: Verify origin and branch**

Run:

```powershell
git -C C:/Users/aryan/source/repos/mesh2splat remote -v
git -C C:/Users/aryan/source/repos/mesh2splat status --short --branch
```

Expected: `origin` points at `https://github.com/bringfire/mesh2splat.git` or `git@github.com:bringfire/mesh2splat.git`.

- [ ] **Step 2: Create or switch to the feature branch**

Run:

```powershell
git -C C:/Users/aryan/source/repos/mesh2splat switch -c codex/sampling-resolution-cli
```

If the branch already exists, run:

```powershell
git -C C:/Users/aryan/source/repos/mesh2splat switch codex/sampling-resolution-cli
```

Expected: branch is `codex/sampling-resolution-cli`.

### Task 2: Add Failing CLI Unit Tests For Sampling Resolution

**Files:**
- Modify: `C:/Users/aryan/source/repos/mesh2splat/tests/unit/test_cli_options.cpp`

- [ ] **Step 1: Replace the fixed-resolution tests with sampling-resolution tests**

Patch the old `parseResolution` tests to this shape:

```cpp
TEST_CASE("parseSamplingResolution accepts deterministic integer range") {
    int r = 0;
    CHECK((cli::parseSamplingResolution("16", r) && r == 16));
    CHECK((cli::parseSamplingResolution("64", r) && r == 64));
    CHECK((cli::parseSamplingResolution("128", r) && r == 128));
    CHECK((cli::parseSamplingResolution("256", r) && r == 256));
    CHECK((cli::parseSamplingResolution("512", r) && r == 512));
    CHECK((cli::parseSamplingResolution("1024", r) && r == 1024));
    CHECK((cli::parseSamplingResolution("4096", r) && r == 4096));
}

TEST_CASE("parseSamplingResolution rejects outside range and non-integers") {
    int r = 0;
    CHECK_FALSE(cli::parseSamplingResolution("15", r));
    CHECK_FALSE(cli::parseSamplingResolution("4097", r));
    CHECK_FALSE(cli::parseSamplingResolution("0", r));
    CHECK_FALSE(cli::parseSamplingResolution("-1", r));
    CHECK_FALSE(cli::parseSamplingResolution("128.5", r));
    CHECK_FALSE(cli::parseSamplingResolution("abc", r));
    CHECK_FALSE(cli::parseSamplingResolution("", r));
}
```

- [ ] **Step 2: Update default and parse tests**

Patch the default/full-args tests to assert canonical and compatibility behavior:

```cpp
TEST_CASE("ConvertOptions has headless defaults") {
    cli::ConvertOptions o;
    CHECK(o.format == cli::ExportFormat::Standard);
    CHECK(o.samplingResolution == 1024);
}

TEST_CASE("parseCli: minimal valid args use defaults") {
    auto r = cli::parseCli({"--input", "a.glb", "--output", "a.ply"});
    REQUIRE(r.ok);
    CHECK(r.options.inputPath == "a.glb");
    CHECK(r.options.outputPath == "a.ply");
    CHECK(r.options.format == cli::ExportFormat::Standard);
    CHECK(r.options.samplingResolution == 1024);
}

TEST_CASE("parseCli: canonical sampling-resolution parsed") {
    auto r = cli::parseCli({"--input", "in.glb", "--output", "out.ply",
                            "--format", "compressed-pbr", "--sampling-resolution", "256"});
    REQUIRE(r.ok);
    CHECK(r.options.format == cli::ExportFormat::CompressedPbr);
    CHECK(r.options.samplingResolution == 256);
}

TEST_CASE("parseCli: legacy resolution alias maps to samplingResolution") {
    auto r = cli::parseCli({"--input", "in.glb", "--output", "out.ply",
                            "--resolution", "512"});
    REQUIRE(r.ok);
    CHECK(r.options.samplingResolution == 512);
}

TEST_CASE("parseCli: effective-resolution is report-only, not a flag") {
    auto r = cli::parseCli({"--input", "a.glb", "--output", "a.ply",
                            "--effective-resolution", "256"});
    CHECK_FALSE(r.ok);
    CHECK(r.errorCode == "BAD_ARGS");
}
```

- [ ] **Step 3: Update JSON schema tests**

Patch success/failure JSON tests to assert both compatibility and forked schema:

```cpp
TEST_CASE("makeSuccessJson contains required forked schema fields") {
    cli::ConvertOptions o;
    o.inputPath = "a.glb";
    o.outputPath = "a.ply";
    o.format = cli::ExportFormat::Standard;
    o.samplingResolution = 256;
    cli::ConvertResult r;
    r.ok = true;
    r.gaussianCount = 123456;
    r.attemptedGaussianCount = 123456;
    r.maxGaussianCapacity = 393216;
    r.durationMs = 812.4;
    const std::string j = cli::makeSuccessJson(o, r);
    CHECK(j.find("\"ok\":true") != std::string::npos);
    CHECK(j.find("\"format\":\"standard\"") != std::string::npos);
    CHECK(j.find("\"samplingResolution\":256") != std::string::npos);
    CHECK(j.find("\"effectiveResolution\":256") != std::string::npos);
    CHECK(j.find("\"resolution\":256") != std::string::npos);
    CHECK(j.find("\"gaussianCount\":123456") != std::string::npos);
    CHECK(j.find("\"attemptedGaussianCount\":123456") != std::string::npos);
    CHECK(j.find("\"maxGaussianCapacity\":393216") != std::string::npos);
    CHECK(j.find("\"durationMs\":812") != std::string::npos);
}

TEST_CASE("makeFailureJson echoes capacity fields when present") {
    cli::ConvertOptions o;
    o.inputPath = "a.glb";
    o.outputPath = "a.ply";
    o.format = cli::ExportFormat::CompressedPbr;
    o.samplingResolution = 1024;
    cli::ConvertResult r;
    r.ok = false;
    r.errorCode = "CAPACITY_EXCEEDED";
    r.message = "attempted gaussian count exceeds capacity";
    r.attemptedGaussianCount = 7000001;
    r.maxGaussianCapacity = 7000000;
    const std::string j = cli::makeFailureJson(&o, r);
    CHECK(j.find("\"ok\":false") != std::string::npos);
    CHECK(j.find("\"errorCode\":\"CAPACITY_EXCEEDED\"") != std::string::npos);
    CHECK(j.find("\"samplingResolution\":1024") != std::string::npos);
    CHECK(j.find("\"attemptedGaussianCount\":7000001") != std::string::npos);
    CHECK(j.find("\"maxGaussianCapacity\":7000000") != std::string::npos);
}
```

- [ ] **Step 4: Add exit-code and usage assertions**

Patch the related tests:

```cpp
TEST_CASE("exitCodeFor maps the error taxonomy") {
    CHECK(cli::exitCodeFor("") == 0);
    CHECK(cli::exitCodeFor("BAD_ARGS") == 2);
    CHECK(cli::exitCodeFor("INPUT_NOT_FOUND") == 3);
    CHECK(cli::exitCodeFor("GLB_PARSE_FAILED") == 4);
    CHECK(cli::exitCodeFor("GL_CONTEXT_INIT_FAILED") == 5);
    CHECK(cli::exitCodeFor("CONVERSION_FAILED") == 6);
    CHECK(cli::exitCodeFor("OUTPUT_WRITE_FAILED") == 7);
    CHECK(cli::exitCodeFor("CAPACITY_EXCEEDED") == 8);
    CHECK(cli::exitCodeFor("SOMETHING_ELSE") == 1);
}

TEST_CASE("usageString mentions canonical sampling flag and legacy alias") {
    const std::string u = cli::usageString();
    CHECK(u.find("--input") != std::string::npos);
    CHECK(u.find("--output") != std::string::npos);
    CHECK(u.find("--format") != std::string::npos);
    CHECK(u.find("--sampling-resolution") != std::string::npos);
    CHECK(u.find("16..4096") != std::string::npos);
    CHECK(u.find("--resolution") != std::string::npos);
}
```

- [ ] **Step 5: Run unit tests and confirm they fail before implementation**

Run:

```powershell
cmake --build C:/Users/aryan/source/repos/mesh2splat/build --target Mesh2SplatTests --config Debug
ctest --test-dir C:/Users/aryan/source/repos/mesh2splat/build -C Debug --output-on-failure -R unit
```

Expected before implementation: compile or test failure for `parseSamplingResolution`, `samplingResolution`, and the new `makeFailureJson` overload.

### Task 3: Implement Sampling Resolution CLI And JSON Schema

**Files:**
- Modify: `C:/Users/aryan/source/repos/mesh2splat/src/cli/CliOptions.hpp`
- Modify: `C:/Users/aryan/source/repos/mesh2splat/src/cli/CliOptions.cpp`

- [ ] **Step 1: Update the CLI header**

Change the resolution declarations and structs to:

```cpp
// samplingResolution is the deterministic headless density lever, valid 16..4096.
bool parseSamplingResolution(const std::string& s, int& out);

struct ConvertOptions {
    std::string  inputPath;
    std::string  outputPath;
    ExportFormat format             = ExportFormat::Standard;
    int          samplingResolution = 1024;
};

struct ConvertResult {
    bool        ok                     = false;
    uint64_t    gaussianCount          = 0;
    uint64_t    attemptedGaussianCount = 0;
    uint64_t    maxGaussianCapacity    = 0;
    double      durationMs             = 0.0;
    std::string errorCode;
    std::string message;
};

std::string makeFailureJson(const ConvertOptions* o, const ConvertResult& r);
```

- [ ] **Step 2: Implement parsing and canonical flags**

Replace `parseResolution`, `isKnownFlag`, and the resolution parse branch with:

```cpp
bool parseSamplingResolution(const std::string& s, int& out) {
    if (s.empty()) return false;
    int value = 0;
    for (char c : s) {
        if (c < '0' || c > '9') return false;
        value = value * 10 + (c - '0');
        if (value > 4096) return false;
    }
    if (value < 16 || value > 4096) return false;
    out = value;
    return true;
}

static bool isKnownFlag(const std::string& s) {
    return s == "--input" || s == "--output" || s == "--format" ||
           s == "--sampling-resolution" || s == "--resolution";
}
```

In `parseCli`, use:

```cpp
std::string in, out, fmt, sampling;
bool haveIn = false, haveOut = false, haveFmt = false, haveSampling = false;
```

and map both flags:

```cpp
else if (tok == "--sampling-resolution" || tok == "--resolution") {
    sampling = val;
    haveSampling = true;
}
```

then validate:

```cpp
if (haveSampling && !parseSamplingResolution(sampling, o.samplingResolution)) {
    return fail("invalid --sampling-resolution (expected integer 16..4096)");
}
```

- [ ] **Step 3: Emit required JSON**

Update `makeSuccessJson` and add the structured failure overload:

```cpp
std::string makeSuccessJson(const ConvertOptions& o, const ConvertResult& r) {
    std::ostringstream s;
    s << "{\"ok\":true"
      << ",\"input\":\""       << jsonEscape(o.inputPath)  << "\""
      << ",\"output\":\""      << jsonEscape(o.outputPath) << "\""
      << ",\"format\":\""      << formatToString(o.format) << "\""
      << ",\"samplingResolution\":" << o.samplingResolution
      << ",\"effectiveResolution\":" << o.samplingResolution
      << ",\"resolution\":"    << o.samplingResolution
      << ",\"gaussianCount\":" << r.gaussianCount
      << ",\"attemptedGaussianCount\":" << r.attemptedGaussianCount
      << ",\"maxGaussianCapacity\":" << r.maxGaussianCapacity
      << ",\"durationMs\":"    << static_cast<long long>(r.durationMs)
      << "}";
    return s.str();
}

std::string makeFailureJson(const ConvertOptions* o, const ConvertResult& r) {
    std::ostringstream s;
    s << "{\"ok\":false"
      << ",\"errorCode\":\"" << jsonEscape(r.errorCode) << "\""
      << ",\"message\":\""   << jsonEscape(r.message)   << "\"";
    if (o) {
        s << ",\"input\":\""    << jsonEscape(o->inputPath)  << "\""
          << ",\"output\":\""   << jsonEscape(o->outputPath) << "\""
          << ",\"format\":\""   << formatToString(o->format) << "\""
          << ",\"samplingResolution\":" << o->samplingResolution
          << ",\"effectiveResolution\":" << o->samplingResolution
          << ",\"resolution\":" << o->samplingResolution;
    }
    if (r.attemptedGaussianCount > 0 || r.maxGaussianCapacity > 0) {
        s << ",\"attemptedGaussianCount\":" << r.attemptedGaussianCount
          << ",\"maxGaussianCapacity\":" << r.maxGaussianCapacity;
    }
    s << "}";
    return s.str();
}
```

Keep the existing string overload by delegating:

```cpp
std::string makeFailureJson(const ConvertOptions* o, const std::string& errorCode,
                            const std::string& message) {
    ConvertResult r;
    r.errorCode = errorCode;
    r.message = message;
    return makeFailureJson(o, r);
}
```

- [ ] **Step 4: Map capacity exit and update help**

Patch:

```cpp
if (e == "CAPACITY_EXCEEDED") return 8;
```

and:

```cpp
std::string usageString() {
    return
        "Usage: Mesh2Splat --input <a.glb> --output <a.ply>\n"
        "                  [--format standard|pbr|compressed-pbr]  (default: standard)\n"
        "                  [--sampling-resolution 16..4096]        (default: 1024)\n"
        "                  [--resolution 16..4096]                 (legacy alias)\n"
        "With no arguments, Mesh2Splat launches the GUI.";
}
```

- [ ] **Step 5: Run CLI unit tests**

Run:

```powershell
cmake --build C:/Users/aryan/source/repos/mesh2splat/build --target Mesh2SplatTests --config Debug
ctest --test-dir C:/Users/aryan/source/repos/mesh2splat/build -C Debug --output-on-failure -R unit
```

Expected: all `Mesh2SplatTests` pass.

### Task 4: Implement Capacity Overflow Detection Before PLY Export

**Files:**
- Modify: `C:/Users/aryan/source/repos/mesh2splat/src/cli/HeadlessConverter.hpp`
- Modify: `C:/Users/aryan/source/repos/mesh2splat/src/cli/HeadlessConverter.cpp`
- Modify: `C:/Users/aryan/source/repos/mesh2splat/src/cli/CliOptions.hpp`
- Modify: `C:/Users/aryan/source/repos/mesh2splat/src/cli/CliOptions.cpp`
- Create: `C:/Users/aryan/source/repos/mesh2splat/src/renderer/renderPasses/ConversionCapacity.hpp`
- Modify: `C:/Users/aryan/source/repos/mesh2splat/src/renderer/renderPasses/ConversionPass.cpp`

- [ ] **Step 1: Add a shared capacity helper**

Create `ConversionCapacity.hpp` so GL buffer allocation and headless capacity reporting use the same formula:

```cpp
#pragma once
#include <algorithm>
#include <cstdint>

constexpr uint64_t kMesh2SplatMaxGaussians = 7000000ull;

inline uint64_t conversionCapacityForSamplingResolution(int samplingResolution, uint64_t meshCount) {
    const uint64_t count = std::max<uint64_t>(1, meshCount);
    const uint64_t requested =
        static_cast<uint64_t>(samplingResolution) *
        static_cast<uint64_t>(samplingResolution) *
        6ull * count;
    return std::min(requested, kMesh2SplatMaxGaussians);
}
```

- [ ] **Step 2: Use the helper in `ConversionPass.cpp`**

Include the helper and replace the local capacity arithmetic:

```cpp
#include "ConversionCapacity.hpp"
```

```cpp
unsigned int meshCount = static_cast<unsigned int>(std::max(size_t(1), renderContext.dataMeshAndGlMesh.size()));
uint64_t capacity = conversionCapacityForSamplingResolution(
    static_cast<int>(renderContext.resolutionTarget),
    static_cast<uint64_t>(meshCount));
unsigned int maxGaussians = static_cast<unsigned int>(capacity);
```

- [ ] **Step 3: Use `samplingResolution` consistently**

Replace:

```cpp
renderer.gaussianBufferFromSize(opts.resolution * opts.resolution);
renderer.setViewportResolutionForConversion(opts.resolution);
```

with:

```cpp
renderer.gaussianBufferFromSize(opts.samplingResolution * opts.samplingResolution);
renderer.setViewportResolutionForConversion(opts.samplingResolution);
```

- [ ] **Step 4: Detect overflow after conversion and before export**

In `HeadlessConverter.cpp`, include the shared helper:

```cpp
#include "renderer/renderPasses/ConversionCapacity.hpp"
```

After `renderer.renderFrame();`, compute capacity and return a parseable failure before `exportPlySync`:

```cpp
const auto loadedMeshCount = renderer.getRenderContext()->dataMeshAndGlMesh.size();
const uint64_t maxCapacity =
    conversionCapacityForSamplingResolution(
        opts.samplingResolution,
        static_cast<uint64_t>(loadedMeshCount));

const int count = renderer.getRenderContext()->numberOfGaussians;
r.attemptedGaussianCount = count > 0 ? static_cast<uint64_t>(count) : 0;
r.maxGaussianCapacity = maxCapacity;

if (r.attemptedGaussianCount > maxCapacity) {
    r.ok = false;
    r.errorCode = "CAPACITY_EXCEEDED";
    r.message = "attempted gaussian count exceeds capacity";
    return r;
}
```

Keep the zero-gaussian failure after this block, and on success set:

```cpp
r.gaussianCount = static_cast<uint64_t>(count);
r.attemptedGaussianCount = static_cast<uint64_t>(count);
r.maxGaussianCapacity = maxCapacity;
```

- [ ] **Step 5: Update the CLI main call site if it still uses the string failure overload**

Search:

```powershell
rg -n "makeFailureJson|ConvertResult" C:/Users/aryan/source/repos/mesh2splat/src
```

If `src/main.cpp` prints failures from a `ConvertResult`, make sure it calls:

```cpp
std::cout << cli::makeFailureJson(&opts, result) << std::endl;
```

For parse failures, keep:

```cpp
std::cout << cli::makeFailureJson(nullptr, parse.errorCode, parse.message) << std::endl;
```

- [ ] **Step 6: Run tests**

Run:

```powershell
cmake --build C:/Users/aryan/source/repos/mesh2splat/build --config Debug
ctest --test-dir C:/Users/aryan/source/repos/mesh2splat/build -C Debug --output-on-failure -R unit
```

Expected: unit tests pass and the main executable builds.

- [ ] **Step 7: Commit Mesh2Splat CLI/capacity work**

Run:

```powershell
git -C C:/Users/aryan/source/repos/mesh2splat add src/cli src/renderer/renderPasses tests/unit
git -C C:/Users/aryan/source/repos/mesh2splat commit -m "feat: expose deterministic sampling resolution"
```

## Milestone 2: Repeatable Fixture, Live Sizing Matrix, And Default Selection

### Task 5: Generate `building_lowpoly_textured_v1`

**Files:**
- Modify: `C:/Users/aryan/source/repos/mesh2splat/tests/fixtures/generate_fixture.py`
- Create: `C:/Users/aryan/source/repos/mesh2splat/tests/fixtures/building_lowpoly_textured_v1.glb`
- Create: `C:/Users/aryan/source/repos/mesh2splat/tests/fixtures/building_lowpoly_textured_v1.meta.json`

- [ ] **Step 1: Extend the fixture generator with a deterministic building fixture**

Add a `make_building_fixture()` function that creates:

- approximate bounds `20m x 12m x 9m`
- `120..250` triangles
- `3..6` simple materials
- one file-backed facade/window atlas texture
- valid channel-1 UVs for every textured primitive
- scalar fallback colors for all materials

Use this concrete metadata writer at the end of the generator:

```python
import json

def write_metadata(path, *, name, bounds_m, triangle_count, material_count, texture_size):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "name": name,
            "version": 1,
            "boundsMeters": bounds_m,
            "triangleCount": triangle_count,
            "materialCount": material_count,
            "textureSize": texture_size,
            "uvChannel": 1,
            "intendedUse": "early architectural massing/building-scale export",
        }, f, indent=2, sort_keys=True)
        f.write("\n")
```

- [ ] **Step 2: Generate fixtures**

Run:

```powershell
cd C:/Users/aryan/source/repos/mesh2splat
python -m venv .scratch/fixture-venv
.scratch/fixture-venv/Scripts/python -m pip install trimesh pillow numpy
.scratch/fixture-venv/Scripts/python tests/fixtures/generate_fixture.py
```

Expected: `cube_textured.glb`, `building_lowpoly_textured_v1.glb`, and `building_lowpoly_textured_v1.meta.json` exist.

- [ ] **Step 3: Verify fixture contract**

Run:

```powershell
Get-Content C:/Users/aryan/source/repos/mesh2splat/tests/fixtures/building_lowpoly_textured_v1.meta.json
Get-Item C:/Users/aryan/source/repos/mesh2splat/tests/fixtures/building_lowpoly_textured_v1.glb | Select-Object FullName,Length
```

Expected: metadata reports `triangleCount` between `120` and `250`, `materialCount` between `3` and `6`, and texture size is recorded.

### Task 6: Update Live Headless Integration Test For Sampling Resolution

**Files:**
- Modify: `C:/Users/aryan/source/repos/mesh2splat/tests/integration/test_headless.py`

- [ ] **Step 1: Replace `--resolution` success path with canonical flag**

Patch the first run to:

```python
rc, so, se = run(["--input", FIXTURE, "--output", out,
                  "--format", "standard", "--sampling-resolution", "1024"])
```

and assert:

```python
check("samplingResolution echoed", j.get("samplingResolution") == 1024)
check("effectiveResolution echoed", j.get("effectiveResolution") == 1024)
check("legacy resolution echoed", j.get("resolution") == 1024)
check("attemptedGaussianCount present", j.get("attemptedGaussianCount", 0) >= j.get("gaussianCount", 0))
check("maxGaussianCapacity present", j.get("maxGaussianCapacity", 0) >= j.get("gaussianCount", 0))
```

- [ ] **Step 2: Add a low-resolution smoke conversion**

Inside the temporary directory block, add:

```python
out64 = os.path.join(d, "out64.ply")
rc64, so64, _ = run(["--input", FIXTURE, "--output", out64,
                     "--format", "compressed-pbr", "--sampling-resolution", "64"])
j64 = parse_single_json(so64)
check("sampling 64 rc 0", rc64 == 0)
check("sampling 64 ok", j64.get("ok") is True)
check("sampling 64 echoed", j64.get("samplingResolution") == 64)
check("sampling 64 ply exists", os.path.exists(out64))
check("sampling 64 gaussianCount > 0", j64.get("gaussianCount", 0) > 0)
```

- [ ] **Step 3: Keep legacy alias covered**

Patch the determinism run to continue using `--resolution` as the legacy alias:

```python
rc2, so2, _ = run(["--input", FIXTURE, "--output", out2, "--resolution", "1024"])
```

- [ ] **Step 4: Run live/local test**

Run with the built binary path:

```powershell
python C:/Users/aryan/source/repos/mesh2splat/tests/integration/test_headless.py C:/Users/aryan/source/repos/mesh2splat/bin/Debug/Mesh2Splat.exe
```

Expected: `ALL PASSED`. If the machine lacks an OpenGL context, record the exact failure and do not mark Milestone 2 complete.

### Task 7: Add Live Sizing Matrix Runner

**Files:**
- Create: `C:/Users/aryan/source/repos/mesh2splat/tests/integration/run_sampling_matrix.py`

- [ ] **Step 1: Add the matrix runner**

Create this script:

```python
#!/usr/bin/env python3
import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = [
    {
        "name": "cube_textured_1m_v1",
        "version": 1,
        "path": os.path.join(ROOT, "tests", "fixtures", "cube_textured.glb"),
        "contract": {
            "triangleCount": 12,
            "boundsMeters": [1.0, 1.0, 1.0],
            "intendedUse": "textured unit cube baseline",
        },
    },
    {
        "name": "building_lowpoly_textured_v1",
        "version": 1,
        "path": os.path.join(ROOT, "tests", "fixtures", "building_lowpoly_textured_v1.glb"),
        "metadataPath": os.path.join(ROOT, "tests", "fixtures", "building_lowpoly_textured_v1.meta.json"),
    },
]
RESOLUTIONS = [64, 128, 256, 512, 1024]

def find_binary():
    if len(sys.argv) > 1:
        return sys.argv[1]
    for cand in (
        os.path.join(ROOT, "bin", "Release", "Mesh2Splat.exe"),
        os.path.join(ROOT, "bin", "Debug", "Mesh2Splat.exe"),
    ):
        if os.path.exists(cand):
            return cand
    raise SystemExit("Mesh2Splat binary not found; pass path as first argument")

def parse_last_json(stdout):
    for line in reversed([ln.strip() for ln in stdout.splitlines() if ln.strip()]):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            pass
    raise AssertionError(f"no JSON object found in stdout: {stdout!r}")

def read_fixture_metadata(fixture):
    metadata = {
        "name": fixture["name"],
        "version": fixture["version"],
        **fixture.get("contract", {}),
    }
    metadata_path = fixture.get("metadataPath")
    if metadata_path:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata.update(json.load(f))
    return metadata

def read_glb(path):
    with open(path, "rb") as f:
        data = f.read()
    magic, version, total_length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or total_length != len(data):
        raise AssertionError(f"invalid GLB header for {path}")
    offset = 12
    json_chunk = None
    bin_chunk = b""
    while offset < len(data):
        chunk_length, chunk_type = struct.unpack_from("<I4s", data, offset)
        offset += 8
        chunk_data = data[offset:offset + chunk_length]
        offset += chunk_length
        if chunk_type == b"JSON":
            json_chunk = json.loads(chunk_data.decode("utf-8").rstrip(" \x00"))
        elif chunk_type == b"BIN\x00":
            bin_chunk = chunk_data
    if json_chunk is None:
        raise AssertionError(f"missing JSON chunk for {path}")
    return json_chunk, bin_chunk

def accessor_triangle_count(gltf):
    total = 0
    for mesh in gltf.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            index_accessor = primitive.get("indices")
            if index_accessor is not None:
                total += int(gltf["accessors"][index_accessor]["count"]) // 3
            else:
                position_accessor = primitive["attributes"]["POSITION"]
                total += int(gltf["accessors"][position_accessor]["count"]) // 3
    return total

def primitive_instance_count(gltf):
    nodes = gltf.get("nodes", [])
    meshes = gltf.get("meshes", [])
    count = 0
    for node in nodes:
        mesh_index = node.get("mesh")
        if mesh_index is not None:
            count += len(meshes[mesh_index].get("primitives", []))
    if count == 0:
        count = sum(len(mesh.get("primitives", [])) for mesh in meshes)
    return count

def texture_dimensions(gltf, bin_chunk):
    dims = []
    for image in gltf.get("images", []):
        buffer_view = image.get("bufferView")
        if buffer_view is None:
            continue
        view = gltf["bufferViews"][buffer_view]
        start = int(view.get("byteOffset", 0))
        length = int(view["byteLength"])
        with Image.open(io.BytesIO(bin_chunk[start:start + length])) as img:
            dims.append({"width": img.width, "height": img.height, "mimeType": image.get("mimeType")})
    return dims

def inspect_glb(path):
    gltf, bin_chunk = read_glb(path)
    return {
        "triangleCount": accessor_triangle_count(gltf),
        "emittedPrimitiveInstanceCount": primitive_instance_count(gltf),
        "materialCount": len(gltf.get("materials", [])),
        "textureDimensions": texture_dimensions(gltf, bin_chunk),
    }

def read_vertex_count(path):
    with open(path, "rb") as f:
        data = f.read(8192)
    head = data.split(b"end_header")[0].decode("ascii", "ignore")
    for line in head.splitlines():
        if line.startswith("element vertex"):
            return int(line.split()[-1])
    return None

def main():
    binary = find_binary()
    rows = []
    with tempfile.TemporaryDirectory() as d:
        for fixture in FIXTURES:
            fixture_name = fixture["name"]
            fixture_path = fixture["path"]
            if not os.path.exists(fixture_path):
                raise SystemExit(f"missing fixture: {fixture_path}")
            metadata = read_fixture_metadata(fixture)
            glb_stats = inspect_glb(fixture_path)
            for sampling in RESOLUTIONS:
                out = os.path.join(d, f"{fixture_name}-{sampling}.ply")
                t0 = time.perf_counter()
                p = subprocess.run([
                    binary, "--input", fixture_path, "--output", out,
                    "--format", "compressed-pbr",
                    "--sampling-resolution", str(sampling),
                ], capture_output=True, text=True)
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                payload = parse_last_json(p.stdout)
                rows.append({
                    "fixture": fixture_name,
                    "fixtureVersion": metadata.get("version"),
                    "fixturePath": fixture_path,
                    "fixtureMetadata": metadata,
                    "triangleCount": glb_stats["triangleCount"],
                    "emittedPrimitiveInstanceCount": glb_stats["emittedPrimitiveInstanceCount"],
                    "materialCount": glb_stats["materialCount"],
                    "textureDimensions": glb_stats["textureDimensions"],
                    "samplingResolution": sampling,
                    "format": "compressed-pbr",
                    "returnCode": p.returncode,
                    "ok": payload.get("ok"),
                    "gaussianCount": payload.get("gaussianCount"),
                    "attemptedGaussianCount": payload.get("attemptedGaussianCount"),
                    "maxGaussianCapacity": payload.get("maxGaussianCapacity"),
                    "effectiveResolution": payload.get("effectiveResolution"),
                    "actualPlyBytes": os.path.getsize(out) if os.path.exists(out) else None,
                    "headerVertexCount": read_vertex_count(out) if os.path.exists(out) else None,
                    "durationMs": payload.get("durationMs", elapsed_ms),
                    "errorCode": payload.get("errorCode"),
                    "stderrTail": p.stderr[-2000:],
                })
    print(json.dumps({"binary": binary, "rows": rows}, indent=2))
    if any(not row["ok"] for row in rows):
        sys.exit(1)

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the matrix and save evidence**

Run:

```powershell
python C:/Users/aryan/source/repos/mesh2splat/tests/integration/run_sampling_matrix.py C:/Users/aryan/source/repos/mesh2splat/bin/Debug/Mesh2Splat.exe > C:/Users/aryan/source/repos/Rook/docs/superpowers/audits/2026-06-29-mesh2splat-sampling-matrix.json
```

Expected: JSON contains ten successful rows: two fixtures times five sampling resolutions. Every row must include `fixtureVersion`, `triangleCount`, `emittedPrimitiveInstanceCount`, `materialCount`, `textureDimensions`, `samplingResolution`, `gaussianCount`, `actualPlyBytes`, `durationMs`, `attemptedGaussianCount`, and `maxGaussianCapacity`. `emittedPrimitiveInstanceCount` is the value Rook later uses as `mesh2splatLoadedMeshCount` for the pre-run PLY estimate.

- [ ] **Step 3: Choose the Rook default**

Use these rules:

- Choose `64` only if `128` exceeds acceptable time or file size for `building_lowpoly_textured_v1`.
- Choose `128` if the building fixture is useful and materially smaller/faster than `256`.
- Choose `256` only if `64` and `128` are visibly or numerically too sparse and the file size is acceptable.
- Do not choose a default above `256` for the first slice.

Record the chosen default in `C:/Users/aryan/source/repos/Rook/docs/superpowers/audits/2026-06-29-mesh2splat-sampling-matrix.md` with fixture metadata, command, rows, rationale, and a line exactly like:

```text
chosenDefaultSamplingResolution: 128
```

The number may be `64`, `128`, or `256`; it must be the actual selected value from the matrix, not the provisional value from the spec.

- [ ] **Step 4: Commit Mesh2Splat fixture and matrix tooling**

Run:

```powershell
git -C C:/Users/aryan/source/repos/mesh2splat add tests/fixtures tests/integration
git -C C:/Users/aryan/source/repos/mesh2splat commit -m "test: add mesh2splat sampling fixtures and matrix"
```

- [ ] **Step 5: Commit Rook matrix evidence**

Run:

```powershell
git -C C:/Users/aryan/source/repos/Rook add docs/superpowers/audits/2026-06-29-mesh2splat-sampling-matrix.json docs/superpowers/audits/2026-06-29-mesh2splat-sampling-matrix.md
git -C C:/Users/aryan/source/repos/Rook commit -m "docs: record mesh2splat sampling matrix"
```

## Milestone 3: Rook GLB, Process, Artifact Pipeline

### Task 8: Add Artifact Registry Provenance Tests And Implementation

**Files:**
- Modify: `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_artifacts.py`
- Modify: `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/artifacts.py`

- [ ] **Step 1: Add failing tests for mesh2splat source rank and rerun metadata**

Add tests that create a temp registry and assert:

```python
def test_mesh2splat_capture_promotes_over_explicit_and_replaces_metadata(tmp_path):
    path = tmp_path / "capture.glb"
    path.write_bytes(b"glb")
    norm = artifacts.normalize_path(str(path))
    now = 100
    reg = _reg(tmp_path)
    assert reg.upsert(norm, source="explicit", file_state="present", size=3, mtime=1,
                      document_name="old.3dm", origin_session_id="old", label="old", now=now) == "created"
    assert reg.upsert(norm, source="mesh2splat_capture", file_state="present", size=3, mtime=2,
                      document_name="mesh2splat_test.3dm", origin_session_id="run-1",
                      label="capture.glb", now=now + 1) == "updated"
    row = reg.get(path=norm)
    assert row.source == "mesh2splat_capture"
    assert row.document_name == "mesh2splat_test.3dm"
    assert row.origin_session_id == "run-1"
    assert row.label == "capture.glb"
    reg.close()

def test_mesh2splat_capture_rerun_replaces_owned_metadata(tmp_path):
    path = tmp_path / "capture.ply"
    path.write_bytes(b"ply")
    norm = artifacts.normalize_path(str(path))
    reg = _reg(tmp_path)
    assert reg.upsert(norm, source="mesh2splat_capture", file_state="present", size=3, mtime=1,
                      document_name="first.3dm", origin_session_id="run-1",
                      label="old capture", now=100) == "created"
    assert reg.upsert(norm, source="mesh2splat_capture", file_state="present", size=3, mtime=2,
                      document_name="second.3dm", origin_session_id="run-2",
                      label="new capture", now=101) == "updated"
    row = reg.get(path=norm)
    assert row.source == "mesh2splat_capture"
    assert row.document_name == "second.3dm"
    assert row.origin_session_id == "run-2"
    assert row.label == "new capture"
    reg.close()
```

- [ ] **Step 2: Implement source rank and metadata replacement**

Patch:

```python
_SOURCE_RANK = {"owned_workbench": 0, "explicit": 1, "mesh2splat_capture": 2}
```

In `upsert`, compute:

```python
incoming_rank = _SOURCE_RANK.get(source, 0)
existing_rank = _SOURCE_RANK.get(existing.source, 0)
effective_source = source if incoming_rank > existing_rank else existing.source
mesh2splat_owned = source == "mesh2splat_capture" and existing.source == "mesh2splat_capture"
mesh2splat_promotes = source == "mesh2splat_capture" and incoming_rank >= existing_rank
```

and update metadata with explicit replacement when owned or promoted:

```python
new_document_name = document_name if (mesh2splat_owned or mesh2splat_promotes) else existing.document_name or document_name
new_origin_session_id = origin_session_id if (mesh2splat_owned or mesh2splat_promotes) else existing.origin_session_id or origin_session_id
new_label = label if (mesh2splat_owned or mesh2splat_promotes) else existing.label or label
```

Use those values in the `UPDATE` statement instead of `COALESCE`.

- [ ] **Step 3: Run artifact tests**

Run:

```powershell
cd C:/Users/aryan/source/repos/Rook/mcp_server
python -m pytest tests/test_artifacts.py -q
```

Expected: artifact tests pass.

### Task 9: Implement Python Contract Models And Request Validation

**Files:**
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/__init__.py`
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/contracts.py`
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_mesh2splat_contracts.py`

- [ ] **Step 1: Add tests for request validation**

Create tests that assert:

- `outputDirectory` is required and absolute.
- `format` accepts only `compressed-pbr` and `standard`.
- `samplingResolution` accepts integers `16..4096`.
- `samplingResolution > 512` requires `allowLargeOutput`.
- `format: standard` requires `allowLargeOutput`.
- `unitsMode` accepts `meters` and `raw`, defaulting to `meters`.
- all first-slice request options are parsed: `outputDirectory`, `format`, `samplingResolution`, `unitsMode`, `allowLargeOutput`, `allowNetworkTextures`, `preserveDebugArtifacts`, `object_ids`, `allowPartial`, `mesh2splatPath`, `mesh2splatWorkingDirectory`, `mesh2splatTimeoutSeconds`.

- [ ] **Step 2: Implement `contracts.py`**

Use dataclasses and plain dictionaries. Required constants:

```python
DEFAULT_FORMAT = "compressed-pbr"
DEFAULT_UNITS_MODE = "meters"
VALID_FORMATS = {"compressed-pbr", "standard"}
MIN_SAMPLING_RESOLUTION = 16
MAX_SAMPLING_RESOLUTION = 4096
LARGE_OUTPUT_SAMPLING_THRESHOLD = 512
MESH2SPLAT_MAX_GAUSSIANS = 7_000_000
FORMAT_STRIDES = {"compressed-pbr": 48, "standard": 248}
```

Expose `validate_request(raw: dict[str, object], *, default_sampling_resolution: int) -> Mesh2SplatRequest`. It returns a `Mesh2SplatRequest` dataclass on success and raises/returns the existing Rook error envelope on invalid input, matching the tests in Step 1.

Return structured errors as:

```python
{"success": False, "data": {"code": "invalid_request", "message": "samplingResolution must be an integer from 16 to 4096", "retryable": False}}
```

and:

```python
{"success": False, "data": {"code": "large_output_requires_opt_in", "message": "samplingResolution > 512 or format standard requires allowLargeOutput=true", "retryable": False}}
```

- [ ] **Step 3: Run contract tests**

Run:

```powershell
cd C:/Users/aryan/source/repos/Rook/mcp_server
python -m pytest tests/test_mesh2splat_contracts.py -q
```

Expected: tests pass.

### Task 10: Implement Output Safety And Manifest-Bounded Cleanup

**Files:**
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/output_safety.py`
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_mesh2splat_output_safety.py`

- [ ] **Step 1: Add tests for output directory and exclusive files**

Cover:

- validation is side-effect free before native capture
- relative paths fail
- existing file path fails
- missing requested output directory is created only after capture succeeds
- newly created parent output directory is retained after run-directory failure
- run directory name is `mesh2splat-YYYYMMDD-HHMMSS-<shortRunId>`
- fixed names are `manifest.json`, `capture.glb`, `capture.ply`
- exclusive creation refuses collisions
- initial `manifest.json` creation is exclusive; later manifest updates atomically replace only the owned manifest inside the run directory
- `capture.glb` and `capture.ply` remain exclusive/no-overwrite for the whole run
- cleanup re-resolves each manifest path and deletes only regular files inside the run directory
- cleanup refuses symlink/reparse swaps and outside paths
- no recursive run-directory deletion

- [ ] **Step 2: Implement output safety helpers**

Expose these functions with the listed contracts:

- `validate_output_directory(path: str) -> Path`: returns the resolved absolute path without creating it.
- `create_run_directory(output_directory: Path, *, now: datetime, run_id: str) -> RunPaths`: creates the requested output directory if needed, creates the unique run child, and returns fixed manifest/GLB/PLY paths.
- `exclusive_write_bytes(path: Path, data: bytes) -> None`: writes only when `path` does not already exist.
- `create_manifest(manifest: RunManifest) -> None`: creates `manifest.json` with exclusive text mode and fails if it already exists.
- `update_manifest(manifest: RunManifest) -> None`: writes a temp manifest inside the run directory and atomically replaces only the owned `manifest.json` path after re-resolving that it is still inside the run directory.
- `cleanup_manifest_files(manifest: RunManifest, *, preserve_debug_artifacts: bool) -> list[str]`: re-resolves and removes only current-run regular files inside the run directory, returning deleted paths.

Use Python exclusive file creation modes (`"xb"` for GLB/PLY bytes and `"x"` for initial manifest JSON). For GLB/PLY publish-from-temp behavior, create the temp file inside the run directory and fail if the destination exists before replace. Manifest updates are the only first-slice overwrite exception, and only for the manifest path created by this run.

- [ ] **Step 3: Run output safety tests**

Run:

```powershell
cd C:/Users/aryan/source/repos/Rook/mcp_server
python -m pytest tests/test_mesh2splat_output_safety.py -q
```

Expected: tests pass.

### Task 11: Implement Executable Lookup, Working Directory, And Process Environment

**Files:**
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/executable.py`
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/process.py`
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_mesh2splat_executable.py`
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_mesh2splat_process.py`

- [ ] **Step 1: Add executable lookup tests**

Cover lookup order:

1. explicit `mesh2splatPath`
2. `ROOK_MESH2SPLAT_EXE`
3. mutable config `config/mesh2splat.json`
4. bundled config `config/mesh2splat.json`
5. bundled executable location
6. `PATH`

Assert invalid explicit path fails with `invalid_executable`; invalid env/config/PATH candidates are rejected with diagnostics and lookup continues; non-explicit basename must be `Mesh2Splat.exe`; explicit nonstandard basename is accepted as user-trusted.

- [ ] **Step 2: Add process tests**

Cover:

- argv list is passed to `subprocess.Popen` with `shell=False`
- sanitized env includes only `SystemRoot`, `windir`, `TEMP`, `TMP`, and `PATH` only when selected source requires it
- no API-key-like environment variables are inherited
- invalid working directory fails with `invalid_working_directory`
- absent working directory defaults to executable parent
- timeout returns `mesh2splat_timeout`
- timeout attempts process-tree termination on Windows and records a diagnostic if only direct-child termination is available
- stdout parser uses the last non-empty JSON line
- exit code `4` or JSON `GLB_PARSE_FAILED` maps to `mesh2splat_glb_parse_failed`
- JSON `CAPACITY_EXCEEDED` maps to `mesh2splat_capacity_exceeded`

- [ ] **Step 3: Implement modules**

Implement these functions:

- `resolve_mesh2splat_executable(request_path: str | None, *, env: Mapping[str, str]) -> ExecutableResolution`
- `validate_working_directory(value: str | None, executable_path: Path) -> Path`
- `sanitized_child_environment(*, source_requires_path: bool, parent_env: Mapping[str, str]) -> dict[str, str]`
- `run_mesh2splat(argv: list[str], *, cwd: Path, env: dict[str, str], timeout_seconds: int) -> Mesh2SplatProcessResult`
- `parse_last_stdout_json(stdout: str) -> dict[str, object] | None`

- [ ] **Step 4: Run tests**

Run:

```powershell
cd C:/Users/aryan/source/repos/Rook/mcp_server
python -m pytest tests/test_mesh2splat_executable.py tests/test_mesh2splat_process.py -q
```

Expected: tests pass.

### Task 12: Implement Texture Trust, Decode Caps, And Fallback Decisions

**Files:**
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/textures.py`
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_mesh2splat_textures.py`

- [ ] **Step 1: Add texture safety tests**

Cover:

- reject URL schemes before file I/O
- reject relative paths
- skip UNC/network paths unless `allowNetworkTextures: true`
- accepted paths must resolve to regular local files
- directories, devices, and network reparse targets are rejected
- source byte cap uses `os.stat().st_size` before Pillow opens the image
- Pillow decompression-bomb handling fails with `texture_decode_too_large`
- pixel cap and decoded byte cap fail before PNG conversion
- fallback-capable texture failures produce warnings and scalar `baseColorFactor`
- only images passing trust/path/size/decode checks require `baseColorTexture`
- no sidecar PNG file is written

- [ ] **Step 2: Implement texture module**

Expose:

```python
MAX_TEXTURE_BYTES_PER_SOURCE = 64 * 1024 * 1024
MAX_TEXTURE_PIXELS = 16_777_216
MAX_TEXTURE_DECODED_BYTES = 64 * 1024 * 1024

resolve_texture_source(path: str, *, allow_network_textures: bool) -> TextureResolution
image_to_embedded_png(path: Path) -> bytes
normalize_material_texture(material: CapturedMaterial, *, allow_network_textures: bool) -> NormalizedMaterial
```

Set `PIL.Image.MAX_IMAGE_PIXELS = MAX_TEXTURE_PIXELS` while decoding and treat `Image.DecompressionBombWarning` as failure.

- [ ] **Step 3: Run texture tests**

Run:

```powershell
cd C:/Users/aryan/source/repos/Rook/mcp_server
python -m pytest tests/test_mesh2splat_textures.py -q
```

Expected: tests pass.

### Task 13: Implement Strict GLB Writer And Validator

**Files:**
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/glb_writer.py`
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_mesh2splat_glb_writer.py`

- [ ] **Step 1: Add GLB writer tests**

Cover:

- magic/version/length header
- JSON and BIN chunks use 4-byte padding
- one scene with nodes/meshes
- positions convert by `unitsMode`
- `upAxis: "Z"` and unit metadata are recorded
- triangle winding is preserved
- normals are generated when missing
- vertices split across position/normal/UV/material seams
- textured material with invalid UV falls back to scalar color warning
- scalar-only no-UV mesh fails until dummy-UV smoke test flag is enabled
- accessors include correct `min`/`max`
- index component type is `UNSIGNED_SHORT` under `65536`, otherwise `UNSIGNED_INT`
- images are embedded PNG bufferViews
- no sidecar files are emitted
- `mesh2splatLoadedMeshCount` equals emitted primitive-instance count

- [ ] **Step 2: Implement the writer**

Expose `write_glb(capture: CapturedPayload, *, units_mode: str, allow_dummy_scalar_uv: bool) -> GlbBuildResult` and `validate_glb_bytes(glb: bytes, *, source_expectations: SourceExpectations) -> list[ValidationWarning]`.

Use `struct.pack("<4sII", b"glTF", 2, total_length)` and chunk headers `struct.pack("<I4s", chunk_length, chunk_type)`. Pad JSON with spaces and BIN with zero bytes. Keep all buffers in one BIN chunk.

- [ ] **Step 3: Run GLB writer tests**

Run:

```powershell
cd C:/Users/aryan/source/repos/Rook/mcp_server
python -m pytest tests/test_mesh2splat_glb_writer.py -q
```

Expected: tests pass.

### Task 14: Implement PLY Validator And Size Estimate Reporting

**Files:**
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/ply.py`
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_mesh2splat_ply.py`

- [ ] **Step 1: Add PLY tests**

Cover:

- standard header contains `f_dc_0`, `scale_0`, `rot_0`
- compressed-PBR header matches the fork's compressed fields
- header vertex count equals CLI `gaussianCount`
- actual byte count matches header stride policy
- `estimatedPlyBytes` uses `1MiB + min(samplingResolution^2 * 6 * mesh2splatLoadedMeshCount, 7_000_000) * formatStride`
- one-primitive cube at `standard`/`1024` passes with `allowLargeOutput`
- rejection test injects a lower `maxEstimatedPlyBytesGuard`

- [ ] **Step 2: Implement PLY helpers**

Expose `estimate_ply_bytes(*, sampling_resolution: int, mesh2splat_loaded_mesh_count: int, fmt: str, max_gaussians: int = 7_000_000) -> PlyEstimate` and `validate_ply(path: Path, *, fmt: str, gaussian_count: int) -> PlyValidationResult`.

- [ ] **Step 3: Run PLY tests**

Run:

```powershell
cd C:/Users/aryan/source/repos/Rook/mcp_server
python -m pytest tests/test_mesh2splat_ply.py -q
```

Expected: tests pass.

### Task 15: Add Native Capture Route

**Files:**
- Modify: `C:/Users/aryan/source/repos/Rook/src/RookNative/Handlers/MeshHandler.h`
- Modify: `C:/Users/aryan/source/repos/Rook/src/RookNative/Handlers/MeshHandler.cpp`
- Modify: `C:/Users/aryan/source/repos/Rook/src/RookNative/RookServer.cpp`

- [ ] **Step 1: Add native handler declaration to `MeshHandler.h`**

Use the existing free-function handler pattern in the already compiled mesh handler header:

```cpp
#include "httplib.h"

namespace Rook::Handlers {
void HandleMesh2SplatCapture(const httplib::Request& req, httplib::Response& res);
}
```

- [ ] **Step 2: Implement capture behavior in `MeshHandler.cpp`**

Do not create `Mesh2SplatCaptureHandler.cpp` in this plan. `RookNative.vcxproj` uses explicit `ClCompile` entries, and the repo instructions prohibit project-file edits unless explicitly requested. Keeping the implementation in `MeshHandler.cpp` makes the route compile/link under the existing project file.

The handler must:

- dispatch Rhino document access through existing main-thread utilities
- support explicit `object_ids` and current selection
- enforce strict explicit-id semantics unless `allowPartial`
- capture mesh objects only
- return world-space vertices, normals, channel-1 UV data and validity, triangle indices, material assignment, source material metadata, document units, and transform diagnostics
- enforce `maxObjects`, `maxSourceVertices`, `maxSourceTriangles`, and `maxEstimatedJsonBytes`
- not read texture files, write files, run Mesh2Splat, or register artifacts

- [ ] **Step 3: Register route**

In `RookServer.cpp`, add:

```cpp
m_server->Post("/mesh2splat/capture", [this](const httplib::Request& req, httplib::Response& res) {
    Rook::Handlers::HandleMesh2SplatCapture(req, res);
});
```

- [ ] **Step 4: Build native plugin if the Rhino/MFC toolchain is available**

Run:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: build succeeds. If Rhino SDK/MFC is unavailable, record that native build was not verified.

### Task 16: Implement Python Pipeline Orchestration And MCP Tool

**Files:**
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/mesh2splat/pipeline.py`
- Modify: `C:/Users/aryan/source/repos/Rook/mcp_server/src/rook/server.py`
- Create: `C:/Users/aryan/source/repos/Rook/mcp_server/tests/test_mesh2splat_pipeline.py`

- [ ] **Step 1: Add pipeline tests**

Cover the happy path with fakes:

1. request validation succeeds
2. executable resolution happens before native capture
3. no output/run directory exists before native capture succeeds
4. native capture fake returns mesh/material payload
5. run directory and manifest are created
6. GLB is written and registered
7. Mesh2Splat argv contains requested `--format` and `--sampling-resolution`
8. PLY is validated and registered
9. result includes run directory, output names, artifact ids, source units, counts, estimate metadata, actual bytes, warnings, CLI metadata

Cover failure cases:

- missing executable calls no native capture and creates no files
- native failure creates no output directory/run directory/manifest
- GLB validation failure does not run Mesh2Splat
- timeout cleanup removes only manifest-listed partial PLY
- artifact registration failure is warning, not hard failure

- [ ] **Step 2: Implement orchestration sequence**

Expose `async def export_mesh2splat_capture(raw_request: dict[str, object]) -> dict[str, object]`.

The implementation order must exactly match the approved happy path:

1. validate request
2. resolve executable
3. call native capture
4. create output directory/run directory/manifest
5. validate/convert textures
6. build and validate GLB
7. register GLB
8. run Mesh2Splat
9. validate PLY
10. register PLY
11. return structured result

- [ ] **Step 3: Register MCP tool**

In `server.py`, add tool dispatch for:

```python
rhino_mesh2splat_export
```

Tool arguments are exactly the first-slice request options from the spec. The handler calls:

```python
result = await mesh2splat_pipeline.export_mesh2splat_capture(arguments)
```

- [ ] **Step 4: Run pipeline tests**

Run:

```powershell
cd C:/Users/aryan/source/repos/Rook/mcp_server
python -m pytest tests/test_mesh2splat_pipeline.py -q
```

Expected: tests pass.

### Task 17: Run Rook Test Slice

**Files:**
- All Rook files modified in Milestone 3

- [ ] **Step 1: Run focused Mesh2Splat pipeline tests**

Run:

```powershell
cd C:/Users/aryan/source/repos/Rook/mcp_server
python -m pytest tests/test_mesh2splat_*.py tests/test_artifacts.py -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run server import smoke**

Run:

```powershell
cd C:/Users/aryan/source/repos/Rook/mcp_server
python -c "import rook.server; import rook.mesh2splat.pipeline; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 3: Run live Rhino smoke against the test document**

With Rhino running and bound to `H:/AI EXPERIMENTS/Pearson/mesh2splat_test.3dm`, call the MCP tool with:

```json
{
  "outputDirectory": "H:/AI EXPERIMENTS/Pearson/mesh2splat_test",
  "format": "compressed-pbr",
  "samplingResolution": 128,
  "unitsMode": "meters",
  "allowLargeOutput": false,
  "allowNetworkTextures": false,
  "preserveDebugArtifacts": true
}
```

Before running this smoke test, replace `128` with the numeric `chosenDefaultSamplingResolution` recorded in `C:/Users/aryan/source/repos/Rook/docs/superpowers/audits/2026-06-29-mesh2splat-sampling-matrix.md` if that audit selected `64` or `256`. Expected: result contains registered GLB and PLY artifact ids, no sidecar texture artifact ids, and a valid run directory under the requested output directory.

- [ ] **Step 4: Commit Rook implementation**

Run:

```powershell
git -C C:/Users/aryan/source/repos/Rook add src/RookNative mcp_server/src/rook mcp_server/tests
git -C C:/Users/aryan/source/repos/Rook commit -m "feat: add rook mesh2splat export pipeline"
```

## Final Acceptance Checklist

- [ ] Mesh2Splat branch has passing CLI unit tests.
- [ ] Mesh2Splat live/local integration proves `--sampling-resolution 64` and `1024`.
- [ ] Mesh2Splat capacity overflow contract is implemented before PLY export.
- [ ] `building_lowpoly_textured_v1` exists before Rook tool implementation begins.
- [ ] Live sizing matrix has been recorded and Rook default is selected as `64`, `128`, or `256`.
- [ ] Rook focused Python tests pass.
- [ ] Native build is verified on the Rhino/MFC toolchain or recorded as not verified.
- [ ] Live Rhino cube smoke succeeds against `H:/AI EXPERIMENTS/Pearson/mesh2splat_test.3dm`.
- [ ] No implementation step starts from Rook's provisional `256` default after the sizing matrix has chosen the actual default.
