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
- You may also read and edit `src/RookBim/**/*.cs` and `src/RookBim.Tests/**/*.cs` when the task targets RookBIM, Rhino.Inside.Revit behavior, Revit API dispatch, BIM contracts, or RookBIM packaging/deploy/release behavior
- You may also read and edit `mcp_server/src/rook/**/*.py` and `mcp_server/tests/**/*.py` when the task targets the Python server, DSPy pipeline, or test coverage
- Follow existing patterns in neighboring handlers before introducing new code
- Do not guess Rhino SDK APIs; verify usage from existing files in this repo
- Do not add new external dependencies
- Do not modify `.vcxproj` or `.vcxproj.filters` unless explicitly asked
- Do not claim build verification unless you actually have the Rhino/MFC toolchain
- If a change crosses the native/managed boundary, keep both sides consistent and state that dependency explicitly
- Revit API references must remain isolated to `src/RookBim`; do not add Autodesk/Revit references to `src/Rook`
- `src/RookBim/RookBim.csproj` is a net48 module that copies `RookBim.dll` into `src/Rook/bin/<Configuration>/net48`; release/local deploy workflows must build it after `src/Rook/Rook.csproj`

## Codex App Notes
- When emitting Codex app directives in final responses, use forward-slash absolute Windows paths, for example `<repo>`. Do not use backslash paths like `C:\Users\...` inside directive attributes; they can be parsed as invalid escapes by the app after task completion.

## Project Structure
- `src/RookNative/RookNativePlugin.cpp` — plugin entry point
- `src/RookNative/RookServer.cpp` / `.h` — HTTP server and route registration
- `src/RookNative/Handlers/` — route handler free functions, usually one `.h/.cpp` pair per area
- `src/RookNative/Threading/` — main-thread dispatch utilities
- `src/RookNative/SceneGraph/` — scene graph code
- `src/RookNative/Interactive/` — prompts, gumball, session recording
- `src/RookNative/vendor/` — vendored third-party headers

## Current Architecture
- `RookNative` is the sole Rhino plugin and sole HTTP server
- The native HTTP surface currently has 263 unique routes, 292 route registrations, and 42 handler files
- The Python MCP server exposes its lifecycle-admitted surface through full, lean, and readonly profiles; `test_server_tool_profiles.py` is the authoritative count contract
- Director is retired from MCP discovery, profiles, meta-tools, targeting, and internal-agent dispatch. Native `/director/*` routes and implementation modules remain temporarily preserved for disposition review; they are not a public or agent-callable capability.
- The managed companion is internal, has no HTTP server, and is not a separate public plugin surface
- Grasshopper remains companion-backed by design through the native callback bridge
- The managed companion owns the chat panel
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
