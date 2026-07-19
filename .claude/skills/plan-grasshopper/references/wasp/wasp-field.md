# wasp-field — Field Creation and Configuration

Fields bias aggregation placement probability based on spatial conditions. They make
some placements more likely (near attractors, along curves, within surfaces) but do
NOT prevent placements outside their influence. Fields are optional and independent
of rules — they layer on top of rule-based compatibility.

## When to Use

- When the user wants **density variation** across the aggregation
- When placement should respond to **attractors**, **gradients**, or **boundaries**
- After wasp-rules, before wasp-aggregate (fields must exist before aggregation queries them)
- Skip when uniform distribution is acceptable

## Inputs Required

| Input | Source | Notes |
|-------|--------|-------|
| Field source | Geometry or expression | Varies by source type (see below) |
| Field strength/falloff | Number slider | Controls influence radius and decay |
| Channel (multi-channel) | Integer | For multi-objective setups |

## Field Source Types

Select based on what drives the density variation:

| Source Type | When to Use | Recipe ID |
|-------------|-------------|-----------|
| **Points/attractors** | Density around specific locations | `7bb677d9` |
| **Curves** | Density along paths or edges | `9d5169fc` |
| **Surfaces** | Density across a surface region | `084bb2d5` |
| **Expression** | Mathematical function (sin, distance, etc.) | `da63ff29` |
| **Kangaroo** | Physics-driven (spring, pressure, etc.) | `8f250f41` |
| **Multi-channel** | Multiple independent fields combined | `35afaaf5` |
| **Orientable** | Field with directional component | `fdf0db8a` |
| **Volumetric** | 3D field filling a volume | `e1e6f130` |
| **Combining** | Merge/blend multiple fields | `9fdfcd0f` |

### Supporting Recipes

| Concept | Recipe ID | Notes |
|---------|-----------|-------|
| Field boundaries | `fa2528c3` | Limit field influence to a region |
| Save/load fields | `4e918d2c` | Persist field data to disk |

## Tool Call Pattern

### Pattern A: Field from Points (Most Common)

```python
# BATCH: Field Setup

# Steps 1-3: point parameter, initialized strength slider, and resolved field component
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "guid": "$GUID_POINT_PARAMETER", "pos": [1100, 500]},
        {"temp_id": "T2", "type": "slider", "nick": "FieldStrength", "min": 0.0, "max": 5.0, "value": 1.0, "pos": [1100, 600]},
        {"temp_id": "T3", "guid": "$GUID_WASP_FIELD_POINT", "pos": [1300, 550]},
    ],
)
# Record T1-T3 as $ATTRACTOR_PTS, $FIELD_STRENGTH, and $FIELD.
# Wire: $ATTRACTOR_PTS → Field.PTS
# Wire: $FIELD_STRENGTH → Field.STR

# Step 4: Wire to aggregation
gh_connect(sourceGuid=$FIELD, targetGuid=$AGGREGATION, targetParam="FIELD")
```

### Pattern B: Field from Curves

```python
# Steps 1-2: curve parameter + resolved curve field component
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "guid": "$GUID_CURVE_PARAMETER", "pos": [1100, 500]},
        {"temp_id": "T2", "guid": "$GUID_WASP_FIELD_CURVE", "pos": [1300, 550]},
    ],
)
# Record T1/T2 as $FIELD_CURVE/$FIELD.
# Wire: $FIELD_CURVE → Field.CRV
```

### Pattern C: Field from Expression

```python
# Steps 1-2: expression panel + resolved expression field component
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "type": "panel", "content": "sin(x) * cos(y)", "pos": [1100, 500]},
        {"temp_id": "T2", "guid": "$GUID_WASP_FIELD_EXPRESSION", "pos": [1300, 550]},
    ],
)
# Record T1/T2 as $FIELD_EXPR/$FIELD.
# Wire: $FIELD_EXPR → Field.EXPR
```

### Pattern D: Multi-Channel Field

```python
# Create two separate fields (e.g., point + curve)
# ... (use patterns A/B/C above for each)

# Combine into multi-channel
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[{"temp_id": "T1", "guid": "$GUID_WASP_MULTI_CHANNEL_FIELD", "pos": [1500, 550]}],
)
# Record T1 as $MULTI_FIELD.
# Wire: $FIELD_A → MultiField.F1
# Wire: $FIELD_B → MultiField.F2

# Wire combined field to aggregation
gh_connect(sourceGuid=$MULTI_FIELD, targetGuid=$AGGREGATION, targetParam="FIELD")
```

## Gotchas

1. **Fields bias, they don't filter** — a field makes some placements more likely but
   cannot prevent placements in low-field regions. Use constraints for hard boundaries.
2. **Fields must exist before aggregation** — wire field to Aggregation before solving.
   Adding a field after aggregation has solved requires RESET.
3. **Strength controls falloff, not hard boundary** — higher strength = sharper falloff
   from the source geometry, not a larger influence radius.
4. **Multi-channel fields need matching part catalog** — each channel maps to a part type.
   Without a catalog, multi-channel has no effect on part selection.
5. **Expression syntax** — uses standard math notation. Variables `x`, `y`, `z` are
   world coordinates. Test expression on a simple grid before full aggregation.
6. **Save/load fields** — field data can be persisted to disk (`4e918d2c`). Useful for
   expensive Kangaroo or volumetric fields that take time to compute.

## Outputs

- `$FIELD` or `$MULTI_FIELD` — Field component GUID
- Wire to Aggregation's FIELD input
- Ready for: **wasp-aggregate** (fields compose with rules and constraints)
