# wasp-hierarchy — Hierarchical Part Assembly

Hierarchical aggregation nests assemblies inside assemblies — sub-parts aggregate into
macro parts, macro parts aggregate at a higher level, then sub-parts are extracted and
re-aggregated to fill in detail. This is how real architectural systems work:
building → floor → bay → component.

## When to Use

- When the user mentions **hierarchical**, **multi-scale**, **nested**, **modules within modules**
- For nested-module projects: building = aggregation of units, each unit = aggregation of rooms
- When different scales of detail need different aggregation logic
- **Requires AdvancedPart** for sub-parts

## Inputs Required

| Input | Source | Notes |
|-------|--------|-------|
| Sub-part geometry | Rhino breps/meshes | Small-scale components |
| Sub-part connections | Connection planes | How sub-parts mate with each other |
| Macro-part connections | Connection planes | How macro-parts mate at higher level |
| Sub-part transforms | Transform list | How sub-parts arrange into a macro-part |

## Architecture Pattern

```
Level 0 (Macro): Building
  ├── Floor Module    ← macro-part (aggregation of sub-parts)
  │     ├── Column    ← sub-part
  │     ├── Beam      ← sub-part
  │     └── Slab      ← sub-part
  └── Core Module     ← macro-part
        ├── Elevator  ← sub-part
        └── Stair     ← sub-part
```

**Two aggregation levels:**
1. **Macro aggregation** — macro-parts snap together (building layout)
2. **Micro aggregation** — sub-parts fill detail within each placed macro-part

## Recipe References

| Concept | Recipe ID | Curriculum Steps | Components |
|---------|-----------|-----------------|------------|
| Hierarchical aggregation | `18156490` | 13 steps | 80 |
| Hierarchical LEGO | `0c7d6f00` | 8 steps | 109 |

## Tool Call Pattern

### Phase 1: Define Sub-Parts (uses wasp-parts pattern)

```python
# BATCH: Sub-Part Definition

# Step 1-N: Define sub-parts using wasp-parts pattern
# MUST use AdvancedPart (not basic Part)
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "guid": "$GUID_WASP_ADVANCED_PART", "pos": [300, 200]},
        {"temp_id": "T2", "guid": "$GUID_WASP_ADVANCED_PART", "pos": [300, 400]},
    ],
)
# Record T1/T2 as $SUB_PART_A (column) and $SUB_PART_B (beam).
# ... wire geometry, connections, name per wasp-parts pattern
```

### Phase 2: Define Macro-Part Envelope

```python
# BATCH: Macro-Part Definition

# Steps 1-3: transforms, macro connection, and macro AdvancedPart
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "guid": "$GUID_TRANSFORM_COMPONENT", "pos": [600, 300]},
        {"temp_id": "T2", "guid": "$GUID_WASP_CONNECTION_FROM_DIRECTION", "pos": [600, 500]},
        {"temp_id": "T3", "guid": "$GUID_WASP_ADVANCED_PART", "pos": [800, 400]},
    ],
)
# Record T1-T3 as $MACRO_TRANSFORMS, $MACRO_CONN, and $MACRO_PART.
# Wire: placeholder geometry → AdvancedPart.GEO (macro geometry is placeholder)
# Wire: $MACRO_CONN → AdvancedPart.CONN
# Wire: sub-parts → AdvancedPart.SUB (hierarchy input)
# Wire: $MACRO_TRANSFORMS → AdvancedPart.T (sub-part transforms)
```

### Phase 3: Macro Aggregation

```python
# BATCH: Macro-Level Aggregation (uses wasp-rules + wasp-aggregate pattern)

# Generate rules and aggregate at macro level
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "guid": "$GUID_WASP_RULE_GENERATOR", "pos": [1000, 300]},
        {"temp_id": "T2", "guid": "$GUID_WASP_AGGREGATION", "pos": [1200, 300]},
    ],
)
# Record T1/T2 as $MACRO_RULES/$MACRO_AGG.
# Wire: $MACRO_PART → RuleGenerator.PART
# Wire: $MACRO_PART → Aggregation.PART
# Wire: $MACRO_RULES → Aggregation.RULE
# Wire: part count, seed, reset per wasp-aggregate pattern
```

### Phase 4: Extract and Re-Aggregate Sub-Parts

```python
# BATCH: Sub-Part Extraction + Micro Aggregation

# Steps 1-3: extract sub-parts, generate micro rules, aggregate
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "guid": "$GUID_WASP_EXTRACT_SUB_PARTS", "pos": [1400, 300]},
        {"temp_id": "T2", "guid": "$GUID_WASP_RULE_GENERATOR", "pos": [1400, 500]},
        {"temp_id": "T3", "guid": "$GUID_WASP_AGGREGATION", "pos": [1600, 400]},
    ],
)
# Record T1-T3 as $EXTRACTED, $MICRO_RULES, and $MICRO_AGG.
# Wire: $MACRO_AGG → Extract.AGG
# Wire: sub-parts merged list → RuleGenerator.PART
# Wire: sub-parts → Aggregation.PART
# Wire: $MICRO_RULES → Aggregation.RULE
# Wire: $EXTRACTED → Aggregation.PREV (continue from extracted positions)

# CHECKPOINT
# Bounded-poll gh_status until ready_for_edit is true, solverEnabled is true,
# and solutionState is PostProcess; stop on timeout or disabled/unknown state.
gh_errors()
```

## Gotchas

1. **Sub-parts MUST use AdvancedPart** — basic Part does not support hierarchy.
   This is the most common error in hierarchical setups.
2. **Macro-part geometry is placeholder only** — the actual geometry comes from sub-parts.
   Only the macro-part's connections matter for macro-level aggregation.
3. **Always RESET when changing levels** — macro and micro aggregations are coupled.
   Changing sub-parts invalidates the macro aggregation and vice versa.
4. **Two separate RuleGenerators** — one for macro-parts, one for sub-parts.
   Don't mix them. Each operates at its own level.
5. **Attributes carry through hierarchy** — Smart Attributes (`a8db9228`) survive
   the extraction process. Useful for per-module metadata (unit type, floor number).
6. **Performance scales multiplicatively** — 10 macro-parts x 20 sub-parts each = 200
   total parts. Start small (3 macro x 5 sub) and scale up.
7. **Solve order matters** — macro aggregation must solve BEFORE micro extraction.
   The GH solver handles this via data dependencies, but verify with checkpoint.

## Combined: Grammar + Hierarchy

The most powerful Wasp mode — grammar drives macro structure, hierarchy fills micro:

```
Grammar rule:  Building → {Core, Unit, Unit, Unit, Circulation}
Hierarchy:     Each Unit is itself an aggregation of sub-parts
Result:        Deterministic macro layout + organic micro detail
```

Use **wasp-grammar-aggregate** instead of wasp-aggregate for Phase 3 (macro level)
when deterministic construction sequence is needed.

## Outputs

- `$MACRO_AGG` — macro-level aggregation
- `$MICRO_AGG` — micro-level aggregation (final detailed geometry)
- `$EXTRACTED` — extracted sub-part positions
- Ready for post-processing: wasp-save-load, wasp-disco-export, Datasmith
