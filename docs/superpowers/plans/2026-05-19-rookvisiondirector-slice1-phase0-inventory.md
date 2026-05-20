# RookVisionDirector Slice 1 Phase 0 Inventory

Date: 2026-05-19

## Existing Patterns To Reuse

- View capture:
  - `src/RookNative/Handlers/ViewportHandler.cpp` contains the native legacy `_ViewCaptureToFile` path and active-view capture setup.
  - `src/Rook/Handlers/ViewportHandler.cs` contains managed Tier 3 `CaptureToBitmap` behavior and a stronger viewport restore pattern. Use it as a reference only if native SDK usage is unclear; slice 1 should stay native unless a specific existing managed API is required.

- View/camera state:
  - `src/RookNative/Handlers/ViewportHandler.cpp` snapshots `ON_Viewport savedVP = vp.VP()` and restores with `vp.SetVP(savedVP, true)`.
  - `src/RookNative/Handlers/DocumentOpsHandler.cpp` saves/restores named views through `ON_3dmView` and `SetVP`.
  - `src/Rook/Handlers/ViewportHandler.cs` uses `ViewportInfo`, `SetViewProjection`, and `SetCameraLocations`; this is a useful reference for restoration evidence but not a reason to move slice 1 orchestration into managed code.

- Display mode:
  - `src/RookNative/Handlers/DisplayModeHandler.cpp` enumerates display modes with `CRhinoDisplayAttrsMgr` and applies a mode to the active viewport with `ActiveViewport().SetDisplayMode(targetId)`.

- Object transform:
  - `src/RookNative/Handlers/GeometryOpsHandler.cpp` applies document transforms through `CRhinoDoc::TransformObject(...)` and redraws after document mutation.
  - `src/RookNative/Interactive/GumballManager.cpp` has additional transform usage, but the director route should reuse handler-style document mutation patterns rather than interactive gumball state.

- Object bounds/source state:
  - `src/RookNative/Models/DocumentHelpers.h` and `src/RookNative/Handlers/MeasureHandler.cpp` use `obj->BoundingBox()`.
  - `src/RookNative/Handlers/BlocksHandler.cpp` often prefers `GetTightBoundingBox(...)` with `BoundingBox()` fallback for block internals. Slice 1 moves top-level objects only, so bbox validation can start with the existing top-level object snapshot/bounds pattern.

- Document units:
  - `src/RookNative/Handlers/DocumentOpsHandler.cpp` has `UnitSystemToString(...)` for `ON::LengthUnitSystem`. It is file-local, so the director implementation should either add a local equivalent or extract a shared helper only if a neighboring pattern already supports it.

- MCP tool registration:
  - `mcp_server/src/rook/server.py` registers tools in `list_tools()` and dispatches in `call_tool()`.
  - `mcp_server/src/rook/agent/tool_groups.py` defines visible tool groups and MCP-only groups.
  - `mcp_server/src/rook/agent/tool_dispatcher.py` has direct bridge route patterns, but `rhino_director_run` must remain Python-orchestrated rather than a direct bridge route.

- Live Rhino tests:
  - `mcp_server/tests/conftest.py` provides live-Rhino markers and fixtures.
  - `mcp_server/tests/test_video_routes_live.py` is the closest pattern for live route smoke tests that skip when Rhino/RookNative is unavailable.

## Native Routes To Add

- `POST /director/object-states`
- `POST /director/view-state`
- `POST /director/frame-capture`

## Validation Strength Enum

Slice 1 accepts exactly:

- `bbox_only`: bbox min/max comparison within tolerance; degraded validation, not proof.

No stronger source-state token is accepted in slice 1. The inventory did not identify an existing, stable Rook/Rhino helper that already exposes a transform-relevant source-state hash. Do not add `runtime_serial_and_bbox` or another enum value until a later implementation phase verifies the token source, lifetime, and failure semantics.

Evidence must record `validation_strength: "bbox_only"` and must describe the validation result as degraded source-state validation.

## Parallel Camera Decision

- `parallel_supported`: no for slice 1 implementation.
- Evidence:
  - Existing native patterns confirm active/named viewport access through `ON_Viewport`/`SetVP`, but this inventory did not verify the complete parallel scale/frustum field set and apply/restore behavior needed for faithful deterministic execution.
- Behavior:
  - `/director/view-state` may report that a source view is parallel if discovered.
  - Python must reject a resolved parallel camera for slice 1 before manifest execution.
  - Native `/director/frame-capture` must reject `camera.projection = "parallel"` with `unsupported_projection` before mutation.

## Shared Director Output Root Contract

Python and native use the same root contract:

1. If `ROOK_DIRECTOR_OUTPUT_ROOT` is set, canonicalize it and use it as the only allowed director output root.
2. Otherwise use `%LOCALAPPDATA%/Rook/rookvision_director`.
3. Python-created `run_root` values must be descendants of this root.
4. Native independently reads the same native-side environment/default contract and rejects any `run_root` or `output_path` outside it.
5. `runtime.data_root / "rookvision_director"` is not the slice 1 default because the dev fallback currently resolves to `repo/knowledge`, which native should not implicitly allow for frame output.
