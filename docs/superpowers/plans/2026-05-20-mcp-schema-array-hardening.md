# MCP Schema Array Hardening Implementation Plan

> **PARTIALLY SUPERSEDED — Director MCP retirement (2026-07-13):** The general
> non-Director architecture and dated evidence in this document remain available.
> All `rhino_director_*`, `/director`, VisionDirector, and Director-domain examples,
> allowlist entries, count assumptions, acceptance criteria, and positive dispatch
> tests are superseded as of 2026-07-13. Replace those examples with
> non-Director fixtures when maintaining or replaying this work. This document must
> not be used to restore a Director MCP tool. See the
> [Director MCP Surface Retirement Design][director-mcp-retirement].

[director-mcp-retirement]: ../specs/2026-07-13-director-mcp-surface-retirement-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every registered MCP tool input schema structurally explicit wherever an array is permitted, including union types that include `"array"`.

**Architecture:** Keep the change local to Python MCP schema declarations in `mcp_server/src/rook/server.py` and schema contract tests in `mcp_server/tests/test_server_contract_hardening.py`. Add small schema helper functions that return fresh dictionaries, then mechanically replace missing array item declarations with typed helpers. Use `copy.deepcopy` for item schemas so nested helper output cannot accidentally share mutable schema content.

**Tech Stack:** Python, MCP `Tool` schemas, `pytest`, `nlohmann/json` and Rhino native code are out of scope for this PR.

---

## File Structure

- Modify `mcp_server/tests/test_server_contract_hardening.py`
  - Add a recursive schema walker that reports every registered tool schema path where arrays are permitted without `items`.
  - Keep existing `rhino_create` regression tests intact.

- Modify `mcp_server/src/rook/server.py`
  - Add local schema helper functions near the existing schema constants.
  - Replace current missing `items` schemas with point/vector/list/object/color helpers.
  - Do not alter runtime dispatch or validation logic.

- No native C++ or managed C# files should change.

## Current Violation Inventory

The implementation should remove all 74 current violations. Use this inventory for replacement targeting, but the regression must assert zero violations, not count 74.

Coordinate or vector arrays:

```text
rhino_transform: vector, axis, center, planeOrigin, planeNormal
rhino_copy: offset
rhino_measure_distance: from, to
rhino_create_loft: startPoint, endPoint
rhino_create_sweep1: roadlikeUp
rhino_create_revolve: axisStart, axisEnd
rhino_annotation_text: point
rhino_annotation_dot: location
rhino_annotation_dim_angle: center, start, end, point
rhino_annotation_dim_radius: point
rhino_annotation_dim_diameter: point
rhino_annotation_dim_aligned: start, end
rhino_annotation_dim_linear: start, end, direction
rhino_array_linear: direction
rhino_array_polar: center, axis
rhino_extrude: direction
rhino_block_create: basePoint, point, insertionPoint
rhino_block_insert: point, insertionPoint, basePoint
rhino_block_link: insertionPoint
rhino_text: point
rhino_dimension: start, end, anglePoint, center, dimLocation
rhino_curve_ops: point
rhino_intersect_plane: planeOrigin, planeNormal
rhino_project_curve: direction
rhino_split_brep: planeOrigin, planeNormal
rhino_trim_brep: planeOrigin, planeNormal
rhino_subd_box: origin
rhino_subd_sphere: center
rhino_subd_cylinder: center
rhino_mesh_box: origin
rhino_mesh_sphere: center
rhino_mesh_cylinder: center
rhino_mesh_cone: center
rhino_draft_angle: direction
rhino_closest_point: point
```

Nested coordinate arrays:

```text
rhino_annotation_leader: points.items
```

Union color schemas:

```text
rhino_create_edge_srf: color
rhino_create_patch: color
rhino_create_network_srf: color
rhino_blend_curves: color
rhino_curve_boolean_union: color
rhino_curve_boolean_difference: color
rhino_curve_boolean_intersection: color
```

Object arrays:

```text
gh_explore_workflow.workflow.components
gh_explore_workflow.workflow.wiring
rc_build_profile.features
rc_build_profile.observations
rc_build_profile.surfaces
rc_build_profile.elements
```

## Task 1: Add Failing Recursive Schema Regression

**Files:**
- Modify: `mcp_server/tests/test_server_contract_hardening.py`

- [ ] **Step 1: Add schema walker helpers and the failing test**

Add this block near `test_rhino_create_coordinate_schema_advertises_numeric_arrays`, before the existing `rhino_create` test:

```python
def _schema_type_permits_array(schema_type):
    return schema_type == "array" or (
        isinstance(schema_type, list) and "array" in schema_type
    )


def _find_array_schemas_missing_items(value, path="$"):
    findings = []
    if isinstance(value, dict):
        if _schema_type_permits_array(value.get("type")) and "items" not in value:
            findings.append(path)
        for key, child in value.items():
            findings.extend(_find_array_schemas_missing_items(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_find_array_schemas_missing_items(child, f"{path}[{index}]"))
    return findings


@pytest.mark.asyncio
async def test_all_mcp_array_schemas_declare_items():
    tools = await server.list_tools()
    findings = []
    for tool in tools:
        for path in _find_array_schemas_missing_items(tool.inputSchema or {}):
            findings.append(f"{tool.name}: {path}")

    assert findings == [], (
        "MCP input schemas that permit arrays must declare an 'items' schema:\n"
        + "\n".join(findings)
    )
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```powershell
python -m pytest mcp_server/tests/test_server_contract_hardening.py::test_all_mcp_array_schemas_declare_items -q
```

Expected: FAIL. The failure message should include schema paths such as:

```text
rhino_transform: $.properties.vector
rhino_create_edge_srf: $.properties.color
rc_build_profile: $.properties.features
```

- [ ] **Step 3: Keep this as a local red checkpoint**

Do not commit the intentionally failing test by itself unless the final PR will be squashed. Leave it as a local red checkpoint, then continue to the helper and schema replacement tasks until the regression passes.

## Task 2: Add Local Schema Helpers

**Files:**
- Modify: `mcp_server/src/rook/server.py`

- [ ] **Step 1: Add helper functions near existing schema constants**

Add `import copy` near the existing top-level imports, then insert this helper block above `_GH_SCRIPT_PIN_OBJECT_SCHEMA`:

```python
def _array_schema(
    item_schema: dict[str, Any],
    description: str,
    *,
    min_items: int | None = None,
    max_items: int | None = None,
    schema_type: str | list[str] = "array",
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": schema_type,
        "items": copy.deepcopy(item_schema),
        "description": description,
    }
    if min_items is not None:
        schema["minItems"] = min_items
    if max_items is not None:
        schema["maxItems"] = max_items
    return schema


def _number_array_schema(
    description: str,
    *,
    min_items: int | None = None,
    max_items: int | None = None,
) -> dict[str, Any]:
    return _array_schema(
        {"type": "number"},
        description,
        min_items=min_items,
        max_items=max_items,
    )


def _integer_array_schema(
    description: str,
    *,
    min_items: int | None = None,
    max_items: int | None = None,
) -> dict[str, Any]:
    return _array_schema(
        {"type": "integer"},
        description,
        min_items=min_items,
        max_items=max_items,
    )


def _point3_schema(description: str) -> dict[str, Any]:
    return _number_array_schema(description, min_items=3, max_items=3)


def _vector3_schema(description: str) -> dict[str, Any]:
    return _number_array_schema(description, min_items=3, max_items=3)


def _point3_list_schema(
    description: str,
    *,
    min_items: int | None = None,
) -> dict[str, Any]:
    return _array_schema(
        {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 3,
            "maxItems": 3,
        },
        description,
        min_items=min_items,
    )


def _string_array_schema(
    description: str,
    *,
    min_items: int | None = None,
) -> dict[str, Any]:
    return _array_schema({"type": "string"}, description, min_items=min_items)


def _object_array_schema(
    description: str,
    *,
    min_items: int | None = None,
) -> dict[str, Any]:
    return _array_schema({"type": "object"}, description, min_items=min_items)


def _color_schema(description: str) -> dict[str, Any]:
    return _array_schema(
        {"type": "integer"},
        description,
        min_items=3,
        max_items=3,
        schema_type=["string", "array", "object"],
    )
```

- [ ] **Step 2: Run the existing `rhino_create` schema test**

Run:

```powershell
python -m pytest mcp_server/tests/test_server_contract_hardening.py::test_rhino_create_coordinate_schema_advertises_numeric_arrays -q
```

Expected: PASS. The helpers are added but not yet used.

- [ ] **Step 3: Keep helper addition as a local green-building checkpoint**

Do not commit the helper addition by itself. Keep this as a local checkpoint, then continue to schema replacements so the first implementation commit leaves the branch with passing tests.

## Task 3: Replace Missing Array Item Schemas

**Files:**
- Modify: `mcp_server/src/rook/server.py`

- [ ] **Step 1: Replace coordinate point schemas**

For point/location/origin/center/base/corner/start/end/planeOrigin/axisStart/axisEnd style fields, replace inline schemas like:

```python
{"type": "array", "description": "Start point [x, y, z]"}
```

with:

```python
_point3_schema("Start point [x, y, z]")
```

Use `_point3_schema` for these fields:

```text
rhino_transform.center
rhino_transform.planeOrigin
rhino_measure_distance.from
rhino_measure_distance.to
rhino_create_loft.startPoint
rhino_create_loft.endPoint
rhino_create_revolve.axisStart
rhino_create_revolve.axisEnd
rhino_annotation_text.point
rhino_annotation_dot.location
rhino_annotation_dim_angle.center
rhino_annotation_dim_angle.start
rhino_annotation_dim_angle.end
rhino_annotation_dim_angle.point
rhino_annotation_dim_radius.point
rhino_annotation_dim_diameter.point
rhino_annotation_dim_aligned.start
rhino_annotation_dim_aligned.end
rhino_annotation_dim_linear.start
rhino_annotation_dim_linear.end
rhino_array_polar.center
rhino_block_create.basePoint
rhino_block_create.point
rhino_block_create.insertionPoint
rhino_block_insert.point
rhino_block_insert.insertionPoint
rhino_block_insert.basePoint
rhino_block_link.insertionPoint
rhino_text.point
rhino_dimension.start
rhino_dimension.end
rhino_dimension.anglePoint
rhino_dimension.center
rhino_dimension.dimLocation
rhino_curve_ops.point
rhino_intersect_plane.planeOrigin
rhino_split_brep.planeOrigin
rhino_trim_brep.planeOrigin
rhino_subd_box.origin
rhino_subd_sphere.center
rhino_subd_cylinder.center
rhino_mesh_box.origin
rhino_mesh_sphere.center
rhino_mesh_cylinder.center
rhino_mesh_cone.center
rhino_closest_point.point
```

Preserve each existing description string exactly when practical. If an existing schema already has `minItems` and `maxItems`, replacing it with `_point3_schema(...)` is intended.

- [ ] **Step 2: Replace vector schemas**

For direction/axis/normal/vector/offset fields, replace inline schemas like:

```python
{"type": "array", "description": "Projection direction [x, y, z]"}
```

with:

```python
_vector3_schema("Projection direction [x, y, z]")
```

Use `_vector3_schema` for these fields:

```text
rhino_transform.vector
rhino_transform.axis
rhino_transform.planeNormal
rhino_copy.offset
rhino_create_sweep1.roadlikeUp
rhino_annotation_dim_linear.direction
rhino_array_linear.direction
rhino_array_polar.axis
rhino_extrude.direction
rhino_intersect_plane.planeNormal
rhino_project_curve.direction
rhino_split_brep.planeNormal
rhino_trim_brep.planeNormal
rhino_draft_angle.direction
```

Prefer `_point3_schema` for descriptions that say point/origin, and `_vector3_schema` for descriptions that say vector/axis/normal/direction.

- [ ] **Step 3: Replace nested point-list schema**

Replace the nested `rhino_annotation_leader.points.items` schema with:

```python
"points": _point3_list_schema(
    "Polyline points [[x,y,z], ...] — first is arrow tip, last is text anchor. Minimum 2 points. Input Z behavior in the resulting geometry is SDK-governed, not pinned by Rook's contract.",
    min_items=2,
),
```

Expected resulting schema: `points` has `type: "array"`, `items.type: "array"`, nested `items: {"type": "number"}`, and top-level `minItems: 2`.

- [ ] **Step 4: Replace union color schemas**

For each union color field in the inventory, replace:

```python
{
    "type": ["string", "array", "object"],
    "description": "Object color — accepts hex string '#rrggbb', array [r,g,b] (ints 0-255), or object {r,g,b}",
}
```

with:

```python
_color_schema(
    "Object color — accepts hex string '#rrggbb', array [r,g,b] (ints 0-255), or object {r,g,b}"
)
```

Do this for:

```text
rhino_create_edge_srf.color
rhino_create_patch.color
rhino_create_network_srf.color
rhino_blend_curves.color
rhino_curve_boolean_union.color
rhino_curve_boolean_difference.color
rhino_curve_boolean_intersection.color
```

- [ ] **Step 5: Replace object collection schemas**

For `gh_explore_workflow.workflow.components` and `.wiring`, replace:

```python
{"type": "array", "description": "..."}
```

with:

```python
_object_array_schema("...")
```

For `rc_build_profile.features`, `observations`, `surfaces`, and `elements`, replace:

```python
{"type": "array", "description": "..."}
```

with:

```python
_object_array_schema("...")
```

Keep the existing descriptions. Do not introduce deep object property schemas for these collections in this PR.

- [ ] **Step 6: Run the focused recursive regression**

Run:

```powershell
python -m pytest mcp_server/tests/test_server_contract_hardening.py::test_all_mcp_array_schemas_declare_items -q
```

Expected: PASS.

- [ ] **Step 7: Run a direct recursive scan**

Run:

```powershell
@'
import asyncio
import sys
sys.path.insert(0, r'mcp_server\src')
from rook import server

def permits_array(schema):
    schema_type = schema.get("type") if isinstance(schema, dict) else None
    return schema_type == "array" or (
        isinstance(schema_type, list) and "array" in schema_type
    )

def walk(tool, schema, path="$"):
    if isinstance(schema, dict):
        if permits_array(schema) and "items" not in schema:
            yield f"{tool}\t{path}"
        for key, value in schema.items():
            yield from walk(tool, value, f"{path}.{key}")
    elif isinstance(schema, list):
        for index, value in enumerate(schema):
            yield from walk(tool, value, f"{path}[{index}]")

async def main():
    findings = []
    for tool in await server.list_tools():
        findings.extend(walk(tool.name, tool.inputSchema or {}))
    for finding in findings:
        print(finding)
    print("count=", len(findings))

asyncio.run(main())
'@ | python -
```

Expected:

```text
count= 0
```

- [ ] **Step 8: Commit passing schema hardening changes**

```powershell
git add mcp_server/src/rook/server.py mcp_server/tests/test_server_contract_hardening.py
git commit -m "fix: declare MCP array schema item types"
```

## Task 4: Full Focused Verification

**Files:**
- No new files.
- Verify: `mcp_server/src/rook/server.py`
- Verify: `mcp_server/tests/test_server_contract_hardening.py`
- Verify: `mcp_server/tests/test_director_mcp_tools.py`

- [ ] **Step 1: Run focused MCP schema tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_server_contract_hardening.py mcp_server/tests/test_director_mcp_tools.py -q
```

Expected: PASS. This protects the new global array invariant, existing `rhino_create` schema protection, and Director's OpenAI-compatible schema constraints.

- [ ] **Step 2: Run diff whitespace check**

Run:

```powershell
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 3: Inspect the changed file list**

Run:

```powershell
git status --short
git diff --stat
```

Expected: either a clean tree if each task commit has been made, or only these implementation files if commits were deferred:

```text
mcp_server/src/rook/server.py
mcp_server/tests/test_server_contract_hardening.py
```

The already-approved design commit `f1c4623` is separate and should not be amended unless explicitly requested.

- [ ] **Step 4: Optional installed-runtime preflight**

Only run this if the user asks for installed AppData runtime verification or if the implementation session already includes a payload-only deploy step. Do not claim this verification unless it actually runs.

Run the same direct recursive scan from Task 3 Step 7 against the installed AppData MCP runtime path after payload-only deploy.

- [ ] **Step 5: Final implementation summary**

Report:

```text
Implemented MCP array schema hardening in mcp_server/src/rook/server.py.
Added recursive regression in mcp_server/tests/test_server_contract_hardening.py.
Verified focused pytest and git diff --check.
No native build verification claimed.
```
