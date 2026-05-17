# GH Python Geometry Output Contract Design

## Context

GitHub issue #155 tracks user feedback that generated Grasshopper Python components can output opaque Python blobs instead of usable Rhino/Grasshopper geometry. The first slice should improve generation quality without adding broad runtime enforcement.

Existing Rook behavior:

- `gh_create_script(language="python", ...)` and the `gh_create_python_script` alias normalize `pins_in` / `pins_out` in `mcp_server/src/rook/server.py`.
- Pin `type`, `access`, `optional`, `description`, and related metadata are forwarded to `/gh/script-params`.
- The managed `/gh/script-params` handler creates RhinoCode script pins through the component's `CreateParameter` path and sets access/name/description metadata, but it does not enforce output runtime values.
- Python input coercion already handles geometry wrappers through a generated preamble. This issue is about output behavior, not input coercion.
- Persona guidance lives in `mcp_server/src/rook/agent/personas/*/role.md` and the display prompt snapshot in `mcp_server/src/rook/agent/prompts/WORKER.md`.

## Goal

When Rook or a Rook agent generates a Grasshopper Python component whose semantic output is geometry, the tool contract and prompts should steer the agent to:

- declare geometry outputs with explicit GH/Rhino type and access metadata,
- assign real RhinoCommon geometry objects to those output variables,
- avoid coordinate dictionaries, JSON strings, debug objects, or arbitrary Python wrapper blobs unless explicitly requested by the user.

The first regression should prove the behavior with one point-list component. Curves, Breps, meshes, and runtime enforcement remain follow-ups.

## Scope

Update guidance in:

- `mcp_server/src/rook/server.py`
  - `gh_create_script` description and examples.
  - `gh_create_python_script` alias description and examples.
  - Pin schema descriptions if needed.
- `mcp_server/src/rook/agent/personas/scripter/role.md`
- `mcp_server/src/rook/agent/personas/worker/role.md`
- `mcp_server/src/rook/agent/personas/architect/role.md`
- `mcp_server/src/rook/agent/prompts/WORKER.md`

Add one live regression in the existing live GH script test area, preferably `mcp_server/tests/test_gh_create_script_live.py`.

## Design

### Tool Contract Guidance

For Python geometry outputs, describe the contract directly in the tool text:

- Use rich pin objects for geometry outputs, for example:
  - `{"name": "Points", "type": "Point3d", "access": "list"}`
  - `{"name": "Curves", "type": "Curve", "access": "list"}`
  - `{"name": "Breps", "type": "Brep", "access": "list"}`
  - `{"name": "Meshes", "type": "Mesh", "access": "list"}`
- Assign RhinoCommon values from `Rhino.Geometry`, for example:
  - `Points = [rg.Point3d(0, 0, 0), rg.Point3d(1, 0, 0)]`
- Do not assign dicts such as `{"x": 0, "y": 0, "z": 0}` for geometry outputs.
- Do not assign JSON strings, debug dictionaries, arbitrary custom Python objects, or wrapper blobs for geometry outputs.

The examples should model the desired shape. The current examples already use a scalar `Point3d`; add or change one Python example to a `Point3d` list with rich output pin metadata.

### Persona Guidance

Add a short script-output contract to the scripter persona and mirror the essential instruction in worker/architect prompt surfaces:

- Geometry outputs must be real RhinoCommon geometry values.
- Use `import Rhino.Geometry as rg`.
- For geometry lists, a plain Python list of RhinoCommon geometry objects is the first-choice output for a list-access output pin.
- Only use `DataTree[object]` when the output is intentionally tree-structured. Do not wrap every Python list in `DataTree[object]`.
- Verify with a downstream consumer or bake/inspection, not only by seeing that the script component exists.

This explicitly corrects over-broad guidance in the current scripter persona that says Python lists must be wrapped in `DataTree[object]()` for GH to display each item. That rule is too blunt for this bug: list-access geometry outputs should be plain lists of RhinoCommon geometry unless tree topology is required.

### Regression

Preferred live test:

1. Use `gh_create_script` with:
   - `language: "python"`
   - `pins_in: []`
   - `pins_out: [{"name": "Points", "type": "Point3d", "access": "list"}]`
   - code:
     ```python
     import Rhino.Geometry as rg
     Points = [rg.Point3d(0, 0, 0), rg.Point3d(1, 0, 0), rg.Point3d(2, 0, 0)]
     ```
2. Use a downstream geometry consumer as the anchor. Preferred path is `gh_bake_output` against the `Points` output because it consumes GH volatile data and creates Rhino geometry in the document.
3. Assert `gh_bake_output` succeeds and reports the expected concrete bake shape:
   - `success is True`
   - `data.totalBaked == 3`
   - `data.perTarget[0].bakedCount == 3`
   - `geometryTypes` includes the baked point representation returned by `BakeService` for `Point3d`
4. Optionally call `gh_inspect_output` for diagnostics, but do not rely on serialized preview text alone as the proof.

The assertion must fail if `Points` is changed to:

- `[{"x": 0, "y": 0, "z": 0}]`
- `"[(0,0,0)]"`
- a debug dict/list of metadata,
- an arbitrary Python wrapper object.

If `gh_bake_output` cannot reliably consume RhinoCode `Point3d` list output in the current live harness, the implementation should preserve the guidance changes but record that as evidence for a follow-up runtime/handler slice. Do not expand this first slice into broad output coercion.

## Non-Goals

- No broad runtime validation of every script output.
- No output-value coercion layer in `/gh/script-params`.
- No managed handler refactor unless the live regression proves the current path cannot carry real geometry.
- No curve/Brep/mesh matrix in the first slice.
- No changes to C# script output behavior except avoiding conflicting guidance.

## Test Plan

- Python contract tests for tool descriptions and persona prompt text:
  - `gh_create_script` / `gh_create_python_script` descriptions mention RhinoCommon geometry output values and explicitly discourage dict/string/blob style geometry outputs.
  - scripter persona no longer says all Python lists must be wrapped in `DataTree[object]`.
  - worker/architect prompt surfaces include the essential geometry-output contract or refer to the scripter rule.
- One live Rhino test for the `Point3d` list output path, using a downstream geometry consumer or bake as the anchor.
- Existing `gh_create_script` alias compatibility tests remain unchanged.

## Acceptance

- The tool and persona guidance clearly define usable geometry output: explicit geometry `pins_out` metadata plus real RhinoCommon values assigned to matching output variables.
- The live regression proves a declared `Point3d` list output is consumed as GH/Rhino geometry downstream.
- The live regression assertions fail if the Python output is replaced with dicts, strings, wrapper objects, or debug blobs.
- Runtime enforcement is not added in this slice unless the live regression reveals that the current output path cannot carry real RhinoCommon geometry at all; if that happens, stop and write the follow-up evidence instead of widening scope.
