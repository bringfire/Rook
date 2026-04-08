# RookNative — Rhino 8 C++ Plugin

## Environment
- Windows-only
- Visual Studio 2022, v143 toolset
- MFC dynamic DLL project
- Rhino 8 C++ SDK required
- `cpp-httplib` and `nlohmann/json` are vendored in-repo
- This project cannot be compiled in generic sandbox/Linux environments
- On this machine, `v143` may resolve to `VCToolsVersion=14.38.33130`, which has an incomplete MFC payload
- Native builds should use the newer installed MSVC toolset (`14.44.35207`) when MFC is required

## Working Rules
- You may read and edit `src/RookNative/**/*.h` and `src/RookNative/**/*.cpp`
- You may also read and edit `src/Rook/**/*.cs` when the task targets the managed companion, Grasshopper callback bridge, block-definition mutation routes that remain managed, the chat panel, or RhinoCommon-only behavior
- You may also read and edit `mcp_server/src/rook/**/*.py` and `mcp_server/tests/**/*.py` when the task targets the Python server, DSPy pipeline, or test coverage
- Follow existing patterns in neighboring handlers before introducing new code
- Do not guess Rhino SDK APIs; verify usage from existing files in this repo
- Do not add new external dependencies
- Do not modify `.vcxproj` or `.vcxproj.filters` unless explicitly asked
- Do not claim build verification unless you actually have the Rhino/MFC toolchain
- If a change crosses the native/managed boundary, keep both sides consistent and state that dependency explicitly

## Project Structure
- `src/RookNative/RookNativePlugin.cpp` — plugin entry point
- `src/RookNative/RookServer.cpp` / `.h` — HTTP server and route registration
- `src/RookNative/Handlers/` — route handler free functions, usually one `.h/.cpp` pair per area
- `src/RookNative/Threading/` — main-thread dispatch utilities
- `src/RookNative/SceneGraph/` — scene graph code
- `src/RookNative/Interactive/` — prompts, gumball, session recording
- `src/RookNative/vendor/` — vendored third-party headers

## Current Architecture
- `RookNative` is the only public Rhino plugin and public HTTP surface
- The managed companion is internal, not a separate public plugin surface
- Grasshopper remains companion-backed by design through the native callback bridge
- The managed companion also still owns these non-GH block-definition mutation routes:
  - `/block/set-layers`
  - `/block/set-materials`
  - `/block/set-object-colors`
  - `/block/set-object-names`
  - `/block/set-object-user-strings`
  - `/block/replace-object-geometry`
  - `/block/transform-object`
- `docs/CURRENT_ARCHITECTURE.md` is the short canonical architecture description
- `docs/plans/2026-03-08-companion-boundary-audit.md` explains why the block-definition mutation routes remain managed; if that document conflicts with `docs/CURRENT_ARCHITECTURE.md`, prefer `docs/CURRENT_ARCHITECTURE.md` and the live route wiring
- Do not assume the old public `Rook`/`localhost:9876` architecture is still current
- Do not assume all non-GH work belongs in native code; verify route ownership before moving behavior across the boundary

## Code Patterns
- HTTP routes are registered in `RookServer.cpp`
- Most handler implementations are free functions in `Rook::Handlers`, not class hierarchies
- JSON uses `nlohmann::json`
- HTTP transport uses `httplib`
- Rhino-affecting work must follow existing main-thread dispatch patterns
- Match existing string conventions:
  - Rhino SDK types often use `ON_wString`
  - HTTP/JSON-facing code generally uses `std::string`
- If you are asked to build `RookNative`, prefer a fresh developer shell and explicitly select the working MSVC toolset, for example:
  - `cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"`

## Safety Constraints
- Do not assume a header or helper exists; confirm it in the tree first
- Do not invent new architectural patterns when an existing handler pattern already fits
- Prefer small, local changes over broad refactors unless explicitly requested
- If native code depends on managed/C# behavior, state that dependency explicitly
