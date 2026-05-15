# GH Legacy Route Readiness Boundary Design

Date: 2026-05-14

## Context

The `gh_edit` partial-failure contract work closes the main agent-facing failure
path from the RookChat post-mortem, but it does not close every Grasshopper
runtime-readiness escape hatch. Rook still registers a wider set of public
`/gh/*` HTTP routes through the native plugin and managed callback bridge. Some
of those routes inspect or mutate the active Grasshopper canvas directly, and
some older Python workflows still call legacy mutation endpoints such as
`/gh/create-slider`, `/gh/connect`, and `/gh/value`.

The follow-up risk is not primarily whether a Python MCP tool is currently
exposed. The containment layer is the public route boundary. Any registered
`/gh/*` route that can mutate the canvas or depend on a real active canvas must
have the same fail-closed readiness semantics regardless of whether the caller
is RookChat, direct MCP, native HTTP, a test harness, or an internal workflow.

This design defines a route-boundary audit and readiness contract for the
legacy Grasshopper route surface. It intentionally stays separate from the
reviewed `gh_edit` contract implementation branch.

## Goals

- Start the audit from registered public `/gh/*` routes, not from Python MCP
  tools.
- Classify every registered route by readiness requirements and allowed side
  effects.
- Preserve `/gh/query` as a guarded managed/native compatibility route without
  adding it back to the Python agent surface.
- Make representative legacy mutation routes fail closed when Grasshopper is
  not ready.
- Explicitly review lifecycle routes before deciding whether they may change
  readiness by side effect.
- Define tests and live Rhino validation that prove phantom-canvas behavior is
  not still reachable through legacy routes.

## Non-Goals

- Do not remove public legacy routes in the first pass.
- Do not add a Python-facing `gh_query` tool.
- Do not make every lifecycle or canvas-navigation route fail closed without
  first classifying its intended behavior.
- Do not replace the live Rhino harness with unit tests; both are required.
- Do not broaden this work into unrelated Grasshopper API redesign.

## Source Of Truth

The audit starts from route registration and bridge wiring:

- `src/RookNative/RookServer.cpp`
- `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`
- `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
- `src/Rook/Handlers/GrasshopperHandler.cs`

Python exposure is a secondary audit dimension:

- `mcp_server/src/rook/server.py`
- `mcp_server/src/rook/agent/tool_dispatcher.py`
- `mcp_server/src/rook/agent/tool_groups.py`
- `mcp_server/src/rook/agent/chat/chat_runner.py`

## Route Categories

### Read-Only Status/Library

These routes may execute without `ready_for_edit` when they do not require an
active document/canvas and do not create one by side effect.

Examples include status and library/category discovery routes. The response
must clearly distinguish endpoint execution from Grasshopper readiness. For
example, `/gh/status` may return `success: true` when the status endpoint ran,
while `data.ready_for_edit` remains `false`.

### Read-Only Canvas Inspection

These routes require a real active editable canvas/document because their
result describes canvas state. If `ready_for_edit` is false, they fail closed:

```json
{
  "success": false,
  "verified": false,
  "error": "Grasshopper is not ready for gh_query: no active document.",
  "data": {
    "error": "grasshopper_not_ready",
    "ready_for_edit": false
  }
}
```

Examples include `/gh/query`, `/gh/snapshot`, `/gh/connections`,
`/gh/component`, `/gh/errors`, `/gh/selection`, `/gh/groups`,
`/gh/inspect-output`, `/gh/value` `GET`, and `/gh/canvas/image` if it captures
the real canvas.

### Mutation

These routes mutate the active Grasshopper document, canvas object state,
connections, persistent references, preview flags, script state, solution state,
or bake output. If `ready_for_edit` is false, they fail closed with
`success: false`, `verified: false`, actionable `error` or `errors`, and a
structured `data.error` machine value such as `grasshopper_not_ready`.

Examples include `/gh/create-slider`, `/gh/create-panel`,
`/gh/create-component`, `/gh/connect`, `/gh/disconnect`, `/gh/value` with
`POST`, `/gh/script`, `/gh/script-params`, `/gh/set-reference`,
`/gh/clear-reference`, `/gh/delete`, `/gh/preview`, `/gh/move`, `/gh/group`,
`/gh/group-resize`, `/gh/cluster`, `/gh/solve`, `/gh/bake`, `/gh/edit`, and
`/gh/undo`.

### Imperative Lifecycle

These routes are explicitly allowed to change readiness only when their name
and documentation say they are lifecycle operations. They must report what they
changed and verify postconditions.

Lifecycle routes need separate review before implementation, especially:

- `/gh/document/new`
- `/gh/document/open`
- `/gh/clear`
- `/gh/canvas/focus`
- `/gh/canvas/zoom`
- `/gh/canvas/image`

`/gh/document/new` and `/gh/document/open` may intentionally move from
`ready_for_edit: false` to `ready_for_edit: true`. `/gh/clear` mutates an
existing document but may also be treated by users as a reset operation. Canvas
focus, zoom, and image capture depend on UI visibility and may be navigation,
inspection, or lifecycle-adjacent depending on implementation details. The
implementation plan must classify each of these explicitly before changing its
behavior.

## Readiness Gate

Routes in the read-only canvas inspection and mutation categories require
`ready_for_edit: true`.

`ready_for_edit` means:

```text
available && has_active_canvas && has_active_document && (canvas_visible != false)
```

If visibility cannot be detected, the status payload should include
`visibility_unknown: true`. A route may proceed with `visibility_unknown: true`
only if the operation can still prove it is using a real active document and
canvas. If `canvas_visible` is detectably false, canvas inspection and mutation
routes fail closed.

The not-ready response is part of the agent-visible and direct HTTP contract:

```json
{
  "success": false,
  "verified": false,
  "error": "Grasshopper is not ready for gh_create_slider: no active canvas.",
  "errors": ["Grasshopper is not ready for gh_create_slider: no active canvas."],
  "verification_note": "Call gh_status to inspect readiness. Use an explicit lifecycle tool only if Grasshopper is the intended substrate.",
  "data": {
    "error": "grasshopper_not_ready",
    "operation": "gh_create_slider",
    "ready_for_edit": false,
    "available": true,
    "has_active_canvas": false,
    "has_active_document": false,
    "canvas_visible": null,
    "visibility_unknown": true
  }
}
```

`data.error` is the compatibility machine-code field established by the
current `gh_edit` readiness branch. A future implementation may also add
`data.code` as a duplicate machine-code alias, but the follow-up plan must not
replace `data.error` or require callers to migrate to `data.code` unless that
contract change is explicitly reviewed.

Direct MCP and chat/agent dispatcher paths must preserve top-level
`verified: false`, `error`/`errors`, and `verification_note` when wrapping or
hoisting this response.

## `/gh/query` Policy

`/gh/query` remains a managed/native compatibility route. It is not added to
the Python agent-facing tool surface.

The Python dispatcher should not reference `gh_query` in defensive hoist sets or
tool-group metadata unless a real Python-facing dispatcher route exists. Agents
should use:

```text
gh_status -> gh_snapshot
```

for canvas inspection. The managed `/gh/query` handler still requires
`ready_for_edit` and fails closed because native HTTP callers may still use it.

## Legacy Mutation Policy

The first containment step is managed-side guarding of public route handlers.
That protects native HTTP callers, direct MCP callers that still map to legacy
routes, RookChat internal workflows, and future callers that bypass the Python
tool groups.

After managed guards are in place, Python callers should be audited:

- Agent-facing canvas mutation should prefer `gh_edit`.
- Internal workflows may keep legacy calls only when they first check
  readiness and can prove they are not creating a phantom document/canvas.
- Compatibility calls may remain, but their tool descriptions should point
  agents toward `gh_edit` for normal create/connect/set/delete workflows.

Blind retries are not allowed after a failed or partial mutation route. Callers
must inspect the response and current canvas state, then remediate
incrementally, undo, clean up, or issue a deliberately de-duplicated retry.

## Route Inventory Table

The implementation plan must create and complete a route inventory table before
changing behavior. The table starts from native registered public routes and
adds Python exposure as a secondary column.

| Route | Native handler | Managed callback / handler | Category | Requires `ready_for_edit` | Side effects allowed | Python tool exposure | Expected not-ready response | Test coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/gh/status` | `RookServer.cpp` -> `HandleGrasshopperStatus` | `NativeGhBridgeRegistrar.HandleStatus` -> `Core.GetStatus` | Read-only status/library | No | Status query only; no document/canvas creation | `gh_status` | `success: true` means endpoint executed; `data.ready_for_edit: false` allowed | Unit test for no document creation; live GH-closed harness |
| `/gh/query` | `RookServer.cpp` -> `HandleGrasshopperQuery` | `NativeGhBridgeRegistrar.HandleQuery` -> query document method | Read-only canvas inspection | Yes | None | No Python agent tool | `success: false`, `verified: false`, `data.error: grasshopper_not_ready` | Managed callback test; live GH-closed harness |
| `/gh/snapshot` | `RookServer.cpp` -> `HandleGrasshopperSnapshot` | `NativeGhBridgeRegistrar.HandleSnapshot` -> `Handler.TakeSnapshot` | Read-only canvas inspection | Yes | None | `gh_snapshot` | `success: false`, `verified: false`, `data.error: grasshopper_not_ready` | Dispatcher/MCP unit tests; live GH-closed harness |
| `/gh/edit` | `RookServer.cpp` -> `HandleGrasshopperEdit` | `NativeGhBridgeRegistrar.HandleEdit` -> `Handler.ApplyEdit` | Mutation | Yes | Batch canvas mutation only after readiness | `gh_edit` | `success: false`, `verified: false`, `data.error: grasshopper_not_ready` | Contract tests; live GH-closed harness |
| `/gh/create-slider` | `RookServer.cpp` -> `HandleGrasshopperCreateSlider` | `NativeGhBridgeRegistrar.HandleCreateSlider` -> `Handler.CreateSlider` | Mutation | Yes | Create slider only after readiness | Legacy direct MCP/internal callers if present | `success: false`, `verified: false`, `data.error: grasshopper_not_ready` | New managed guard test; live representative mutation harness |
| `/gh/connect` | `RookServer.cpp` -> `HandleGrasshopperConnect` | `NativeGhBridgeRegistrar.HandleConnect` -> `Handler.ConnectComponents` | Mutation | Yes | Add wire only after readiness | Legacy direct MCP/internal callers if present | `success: false`, `verified: false`, `data.error: grasshopper_not_ready` | New managed guard test; live representative mutation harness |
| `/gh/value` `POST` | `RookServer.cpp` -> `HandleGrasshopperSetValue` | `NativeGhBridgeRegistrar.HandleSetValue` -> `Handler.SetValue` | Mutation | Yes | Set slider/panel/toggle value only after readiness | `gh_set_value` or internal callers if present | `success: false`, `verified: false`, `data.error: grasshopper_not_ready` | New managed guard test; live representative mutation harness |
| `/gh/document/new` | `RookServer.cpp` -> `HandleGrasshopperNewDocument` | `NativeGhBridgeRegistrar.HandleNewDocument` -> `Handler.NewDocument` | Imperative lifecycle | Requires lifecycle review | May create active document if retained as lifecycle | `gh_document_new` if exposed | Lifecycle-specific response with postcondition status | Lifecycle review test before behavior change |
| `/gh/document/open` | `RookServer.cpp` -> `HandleGrasshopperOpenDocument` | `NativeGhBridgeRegistrar.HandleOpenDocument` -> `Handler.OpenDocument` | Imperative lifecycle | Requires lifecycle review | May open active document if retained as lifecycle | `gh_document_open` if exposed | Lifecycle-specific response with postcondition status | Lifecycle review test before behavior change |
| `/gh/clear` | `RookServer.cpp` -> `HandleGrasshopperClear` | `NativeGhBridgeRegistrar.HandleClear` -> `Handler.ClearCanvas` | Imperative lifecycle or mutation after review | Requires lifecycle review | Clear active document only after classification | `gh_clear` if exposed | Classification-specific response; must be explicit | Lifecycle review test before behavior change |
| `/gh/canvas/focus` | `RookServer.cpp` -> `HandleGrasshopperCanvasFocus` | `NativeGhBridgeRegistrar.HandleCanvasFocus` -> `Handler.FocusCanvas` | Imperative lifecycle/navigation after review | Requires lifecycle review | UI navigation only if canvas exists; no document creation unless explicitly approved | `gh_canvas_focus` if exposed | Classification-specific response; must be explicit | Lifecycle/navigation review test |
| `/gh/canvas/zoom` | `RookServer.cpp` -> `HandleGrasshopperCanvasZoom` | `NativeGhBridgeRegistrar.HandleCanvasZoom` -> `Handler.ZoomCanvas` | Imperative lifecycle/navigation after review | Requires lifecycle review | UI navigation only if canvas exists; no document creation unless explicitly approved | `gh_canvas_zoom` if exposed | Classification-specific response; must be explicit | Lifecycle/navigation review test |
| `/gh/canvas/image` | `RookServer.cpp` -> `HandleGrasshopperCanvasImage` | `NativeGhBridgeRegistrar.HandleCanvasImage` -> `Handler.CaptureCanvasImage` | Read-only canvas inspection or lifecycle/navigation after review | Requires lifecycle review | Capture only; no document creation unless explicitly approved | `gh_canvas_image` if exposed | Classification-specific response; must be explicit | Lifecycle/navigation review test |

The full implementation audit must add rows for every remaining registered
`/gh/*` route, including `/gh/document`, `/gh/selection`, `/gh/categories`,
`/gh/library`, `/gh/value` `GET`, `/gh/script`, `/gh/script-params`,
`/gh/connections`, `/gh/delete`, `/gh/preview`, `/gh/move`, `/gh/group`,
`/gh/groups`, `/gh/group-resize`, `/gh/cluster`, exploration routes,
`/gh/batch-component-info`, `/gh/create-component`, `/gh/create-panel`,
`/gh/component`, `/gh/inspect-output`, `/gh/errors`, `/gh/disconnect`,
reference routes, `/gh/solve`, `/gh/bake`, and `/gh/undo`.

## Testing Requirements

Unit and integration-style tests must cover:

- Managed readiness guard helper returns the pinned not-ready shape.
- `/gh/query` remains guarded but is not exposed as a Python agent tool.
- Dispatcher no longer includes stale `gh_query` hoist metadata when no
  dispatcher route exists.
- `gh_query` is absent from Python agent-facing route/tool registries,
  including `BRIDGE_ROUTES` and `TOOL_GROUPS`.
- Representative legacy mutation routes fail closed when not ready:
  `/gh/create-slider`, `/gh/connect`, and `/gh/value` `POST`.
- `gh_status` remains read-only and does not create a document/canvas.
- Lifecycle routes have explicit classification tests before behavior changes.
- Python wrappers preserve `verified: false`, `error`/`errors`, and
  `verification_note` for not-ready results.

Live Rhino validation must cover:

1. GH closed: `/gh/status` executes without creating a document/canvas.
2. GH closed: `/gh/query`, `gh_snapshot`, and `gh_edit` fail closed.
3. GH closed: representative legacy mutation routes fail closed:
   `/gh/create-slider`, `/gh/connect`, and `/gh/value` `POST`.
4. GH open with a blank document: `gh_snapshot` and `gh_edit` work normally.
5. GH open with a blank document: representative legacy mutation routes work
   normally or are intentionally deprecated with explicit responses.

## Rollout

1. Write the route inventory and classify each registered public `/gh/*` route.
2. Remove stale Python `gh_query` references from dispatcher metadata if no
   Python-facing `gh_query` route exists.
3. Add managed fail-closed guards to representative legacy mutation routes.
4. Expand guards to all canvas inspection and mutation routes based on the
   completed inventory.
5. Review lifecycle routes separately and decide whether each remains
   imperative, becomes guarded mutation/inspection, or is deprecated.
6. Update Python tool descriptions and internal workflows to prefer `gh_edit`
   where practical.
7. Run targeted tests, managed bridge tests/build, and the live Rhino harness.

## Review Gate

This spec is complete when reviewers agree on:

- The four route categories.
- The `ready_for_edit` gate and not-ready response shape.
- `/gh/query` staying guarded but not agent-facing.
- The route inventory table format.
- The explicit lifecycle-route review requirement.
- Representative live harness coverage for legacy mutation routes.

Implementation planning should not start until this spec is reviewed.
