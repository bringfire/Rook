# wasp-save-load — Persistence and Round-Tripping

Save aggregation state to JSON files and reload as starting points for further growth.
Enables checkpoint/resume, sub-assembly composition, A/B comparison, and progressive
refinement workflows.

## When to Use

- When the user wants to **save progress** and resume later
- When building **sub-assembly libraries** (pre-build, save, compose later)
- When comparing alternative continuations (**A/B testing**)
- When doing **progressive refinement** (save coarse, reload with tighter constraints)
- Post-aggregation (save), or pre-aggregation (load as starting point)

## Inputs Required

| Input | Source | Notes |
|-------|--------|-------|
| Aggregation | wasp-aggregate output | Completed aggregation to save |
| File path | Text panel | Where to save the .json file |
| Save trigger | Boolean toggle | Triggers the save operation |
| Previous file | Text panel (for load) | Path to previously saved .json |

## Recipe References

| Concept | Recipe ID | Curriculum Steps |
|---------|-----------|-----------------|
| Save/load aggregation | `72d65814` | Steps 1-4 |

## Tool Call Pattern

### Pattern A: Save Aggregation

```python
# BATCH: Save Aggregation State

# Steps 1-3: save path, trigger, and resolved Wasp save component
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "type": "panel", "content": "C:/path/to/aggregation_state.json", "pos": [1700, 100]},
        {"temp_id": "T2", "type": "toggle", "value": False, "pos": [1700, 200]},
        {"temp_id": "T3", "guid": "$GUID_WASP_SAVE_AGGREGATION", "pos": [1900, 150]},
    ],
)
# Record T1-T3 as $SAVE_PATH, $SAVE_TRIGGER, and $SAVE.
# Wire: $AGGREGATION → Save.AGG
# Wire: $SAVE_PATH → Save.PATH
# Wire: $SAVE_TRIGGER → Save.SAVE

# To save: toggle $SAVE_TRIGGER true, solve, toggle back to false
```

### Pattern B: Load and Continue

```python
# BATCH: Load Previous Aggregation

# Steps 1-2: load path + resolved Wasp load component
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "type": "panel", "content": "C:/path/to/saved_aggregation.json", "pos": [900, 100]},
        {"temp_id": "T2", "guid": "$GUID_WASP_LOAD_AGGREGATION", "pos": [1100, 100]},
    ],
)
# Record T1/T2 as $LOAD_PATH/$LOAD.
# Wire: $LOAD_PATH → Load.PATH

# Step 3: Wire loaded aggregation as starting point for new aggregation
gh_connect(sourceGuid=$LOAD, targetGuid=$AGGREGATION, targetParam="PREV")
# The aggregation grows FROM the loaded state, not from scratch
```

### Pattern C: Save + Load Round-Trip (Checkpoint Workflow)

```python
# Combine A and B:
# 1. Aggregate → Save (checkpoint)
# 2. Modify rules/constraints
# 3. Load checkpoint → Continue aggregating with new rules
# This preserves previous work while allowing strategy changes
```

## Gotchas

1. **Save format is referential** — the JSON stores part transforms and connection states
   but references part definitions by name. Loading into a canvas with different parts
   than the original may fail or produce unexpected results.
2. **Save trigger is one-shot** — toggle true to save, then back to false. Leaving it
   true causes repeated saves on every solve.
3. **Load as PREV input** — loaded aggregation feeds into Aggregation's PREV parameter,
   treating it as a starting point. New parts grow from the loaded positions.
4. **File path must be absolute** — relative paths resolve unpredictably in GH.
   Use full Windows paths like `C:/Users/.../aggregation.json`.
5. **Attributes are preserved** — Smart Attributes survive the save/load round-trip.
6. **RESET after load** — loading a new file requires aggregation RESET before re-solving.

## Outputs

- `$SAVE` — Save component GUID
- `$LOAD` — Load component GUID (output feeds into Aggregation.PREV)
- Saved .json file on disk
- Composes with: wasp-aggregate (PREV input), wasp-learn (load → extract rules)
