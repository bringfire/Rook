# wasp-aggregate — Stochastic Aggregation

The primary aggregation engine. Places parts randomly from valid options defined by
rules, optionally biased by fields and filtered by constraints. Non-deterministic
unless a fixed seed is provided.

## When to Use

- **After wasp-rules** (or wasp-learn) — rules must exist before aggregation
- When the user wants **exploratory form-finding** or **organic patterns**
- When deterministic construction sequence is NOT required
  (use wasp-grammar-aggregate for deterministic)
- Default choice unless user explicitly mentions grammar, sequence, or construction order

## Inputs Required

| Input | Source | Notes |
|-------|--------|-------|
| Parts | wasp-parts output (merged list) | All parts for this aggregation |
| Rules | wasp-rules output | Generated or extracted rules |
| Part count (N) | Integer slider | Target number of parts to place |
| Previous aggregation | wasp-save-load (optional) | Resume from saved state |
| Fixed seed | Integer slider (optional) | For reproducibility |
| Constraints mode | Integer (0/1/2) | 0=none, 1=local, 2=global |
| Field | wasp-field output (optional) | Biases placement probability |
| Part catalog | wasp-catalog output (optional) | Controls distribution ratios |
| Reset toggle | Boolean toggle | MUST be wired — reset after any change |

## Recipe References

| Concept | Recipe ID | Curriculum Steps |
|---------|-----------|-----------------|
| Basic aggregation | `098491b7` | Steps 4-6 |
| Fixed seed | `17ccaf31` | Steps 1-4 |
| Transform start point | `fba88cfa` | Steps 4-6 |
| Aggregation graph | `48a1b9fb` | Steps 1-3 |

## Tool Call Pattern

```python
# BATCH: Stochastic Aggregation

# Steps 1-5: create controls and the resolved Wasp Aggregation component
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "type": "slider", "nick": "PartCount", "min": 1, "max": 500, "value": 50, "pos": [1100, 100]},
        {"temp_id": "T2", "type": "slider", "nick": "Seed", "min": 0, "max": 9999, "value": 42, "pos": [1100, 200]},
        {"temp_id": "T3", "type": "toggle", "value": False, "pos": [1100, 300]},
        {"temp_id": "T4", "type": "slider", "nick": "ConstraintMode", "min": 0, "max": 2, "value": 0, "pos": [1100, 400]},
        {"temp_id": "T5", "guid": "$GUID_WASP_AGGREGATION", "pos": [1400, 200]},
    ],
)
# Resolve $GUID_WASP_AGGREGATION during planning. Record T1-T5 from
# edit_summary.temp_id_map as $PART_COUNT, $SEED, $RESET,
# $CONSTRAINT_MODE, and $AGGREGATION. Mode: 0=none, 1=local, 2=global.

# Step 6: Wire inputs
gh_connect(sourceGuid=$PARTS_MERGE, targetGuid=$AGGREGATION, targetParam="PART")
gh_connect(sourceGuid=$RULE_GEN, targetGuid=$AGGREGATION, targetParam="RULE")
gh_connect(sourceGuid=$PART_COUNT, targetGuid=$AGGREGATION, targetParam="N")
gh_connect(sourceGuid=$SEED, targetGuid=$AGGREGATION, targetParam="SEED")
gh_connect(sourceGuid=$RESET, targetGuid=$AGGREGATION, targetParam="RESET")
gh_connect(sourceGuid=$CONSTRAINT_MODE, targetGuid=$AGGREGATION, targetParam="MODE")

# Step 7 (optional): Wire field
# gh_connect(sourceGuid=$FIELD, targetGuid=$AGGREGATION, targetParam="FIELD")

# Step 8 (optional): Wire part catalog
# gh_connect(sourceGuid=$CATALOG, targetGuid=$AGGREGATION, targetParam="CATA")

# Step 9 (optional): Wire TransformPart for seeded start
# gh_connect(sourceGuid=$TRANSFORM_PART, targetGuid=$AGGREGATION, targetParam="PREV")

# CHECKPOINT — aggregation solve can be slow
gh_solve(delay=2000)
gh_errors()
# → Expected: aggregation geometry visible in viewport
# → If "no valid placements": check connection directions, rule compatibility
```

### Extracting Results

```python
# Geometry output
# $AGGREGATION output "GEO" → aggregated geometry (list of transformed parts)

# Aggregation graph (for analysis)
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[{"temp_id": "T1", "guid": "$GUID_WASP_AGGREGATION_GRAPH", "pos": [1700, 200]}],
)
# Record T1 as $AGG_GRAPH, then wire $AGGREGATION → AggregationGraph.AGG.
# Wire: $AGGREGATION → AggregationGraph.AGG
```

## Gotchas

1. **RESET after any change** — changing parts, rules, constraints, or fields requires
   toggling the RESET boolean (false→true→false). Without reset, stale state persists
2. **Non-deterministic without seed** — every solve produces different results.
   Always wire a Fixed Seed slider for reproducible outputs
3. **Solve can be slow** — use `delay=2000` or higher for large aggregations (>100 parts).
   Consider starting with low N (10-20) for testing, then scaling up
4. **"No valid placements" error** — usually means:
   - Connection directions are reversed (most common)
   - Rules are too restrictive (grammar filters too aggressively)
   - Constraints reject all candidates (relax or check Mode setting)
5. **Constraint Mode is an integer** — Mode 0=none, 1=local, 2=global. Default is 0.
   Must explicitly set to 1 or 2 when constraints are needed
6. **Fields don't filter, they bias** — a field makes some placements more likely but
   doesn't prevent placements outside field influence

## Outputs

- `$AGGREGATION` — Aggregation component GUID, output "GEO" = transformed geometry
- Aggregation graph (optional) — topology for analysis
- Ready for post-processing: **wasp-save-load**, **wasp-learn**, **wasp-disco-export**,
  or Datasmith export pipeline
