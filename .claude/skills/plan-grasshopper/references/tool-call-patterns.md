# Tool Call Patterns Reference

Common MCP tool call sequences for Grasshopper definition construction.

## Pattern: Slider-Controlled Component

The most common pattern — a number slider feeding into a component parameter.

```python
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "type": "slider", "nick": "Radius", "min": 0.1, "max": 50.0, "value": 5.0, "pos": [100, 100]},
        {"temp_id": "T2", "guid": "$SPHERE_TYPE_GUID", "pos": [400, 100]},
    ],
    connect=["T1.O0>T2.I0"],
)
# Record committed IDs from edit_summary.temp_id_map.
```

**Gotcha:** Define the slider value/range in the create entry before wiring.
Resolve `$SPHERE_TYPE_GUID` with `gh_library` or `gh_knowledge_query`.

## Pattern: Multi-Input Component

Component with several inputs from different sources.

```python
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "guid": "$POINT_PARAM_GUID", "pos": [100, 100]},
        {"temp_id": "T2", "type": "slider", "nick": "Radius", "min": 0.1, "max": 50.0, "value": 5.0, "pos": [100, 200]},
        {"temp_id": "T3", "type": "slider", "nick": "Height", "min": 1.0, "max": 100.0, "value": 10.0, "pos": [100, 300]},
        {"temp_id": "T4", "guid": "$CYLINDER_GUID", "pos": [400, 200]},
    ],
    connect=["T1.O0>T4.I0", "T2.O0>T4.I1", "T3.O0>T4.I2"],
)
```

## Pattern: Component Chain

Sequential processing: output of one feeds input of next.

```python
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "guid": "$CIRCLE_GUID", "pos": [100, 100]},
        {"temp_id": "T2", "guid": "$EXTRUDE_GUID", "pos": [400, 100]},
        {"temp_id": "T3", "guid": "$CAP_HOLES_GUID", "pos": [700, 100]},
    ],
    connect=["T1.O0>T2.I0", "T2.O0>T3.I0"],
)

# Checkpoint after chain
# The preceding gh_edit scheduled the solution. Bounded-poll gh_status until
# ready_for_edit is true, solverEnabled is true, and solutionState is PostProcess.
gh_errors()
```

## Pattern: Data Tree Manipulation

When components produce trees but downstream expects flat lists.

```python
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "guid": "$DIVIDE_CURVE_GUID", "pos": [400, 100]},
        {"temp_id": "T2", "guid": "$FLATTEN_GUID", "pos": [600, 100]},
    ],
    connect=["T1.O0>T2.I0", "T2.O0>$DOWNSTREAM.I0"],
)
```

**Gotcha:** Many components silently produce tree output. If downstream complains about "path mismatch", insert Flatten/Graft between them.

## Pattern: Boolean Toggle Control

For enabling/disabling parts of the definition.

```python
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "type": "toggle", "value": True, "pos": [100, 400]},
        {"temp_id": "T2", "guid": "$STREAM_FILTER_GUID", "pos": [400, 400]},
    ],
    connect=["T1.O0>T2.I0"],
)
```

## Pattern: Python Script Component

For custom logic that doesn't have a native component.

```python
script_result = gh_create_script(
    language="python",
    code="import Rhino.Geometry as rg\n\nA = x * 2\n",
    pins_in=[{"name": "x", "type": "double"}],
    pins_out=[{"name": "A", "type": "double"}],
    name="DoubleValue",
    x=400,
    y=300,
)
$SCRIPT = script_result["component_guid"]

# Wire inputs
snap = gh_snapshot()
gh_edit(epoch=snap["epoch"], connect=["$INPUT.O0>$SCRIPT.I0"])
```

## Checkpoint Protocol

After every 3-5 component creations:

```python
# 1. The preceding mutation scheduled the solution. Bounded-poll status.
status = gh_status()
# Continue only when ready_for_edit is true, solverEnabled is true,
# and solutionState is PostProcess; stop on timeout or disabled/unknown state.

# 2. Check for errors
gh_errors()
```

**Interpreting errors:**
- `"Null"` on an input — missing upstream connection
- `"Data conversion failed"` — wrong parameter type, check wiring
- `"1. Solution exception"` — component internal error, check parameter values
- Warnings (yellow) — usually acceptable, verify visually

**If errors found:**
1. Check if error matches a known gotcha from the plan
2. If yes: apply the documented fix
3. If no: inspect the failing component with `gh_batch_component_info(names=[<component_name>])`
4. If still failing after one fix attempt: stop and report to user

## Canvas Position Arithmetic

```
Input Column    Processing 1    Processing 2    Output
x=100           x=400           x=700           x=1000

y=100 ─── Slider ──── Component ──── Component ──── Output
y=250 ─── Slider ──── Component ──── Component
y=400 ─── Toggle ──── Gate
```

- **Horizontal spacing:** 300px between connected components
- **Vertical spacing:** 150px between parallel items
- **Group gap:** 100px between logical groups
