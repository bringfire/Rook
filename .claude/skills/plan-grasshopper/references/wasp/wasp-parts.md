# wasp-parts — Define Parts with Connections

The foundation of every Wasp workflow. Parts wrap geometry with connection planes
that define where pieces mate. Choose Part (basic) or AdvancedPart (constraints,
hierarchy, smart attributes).

## When to Use

- **Every Wasp workflow starts here** — prerequisite for all other sub-skills
- After Rhino geometry exists (breps or meshes) that will become discrete parts
- After Rhino scene has been prepared via the scaffold protocol (see `wasp-rhino-scaffold.md`)
- Before wasp-rules (Parts must exist before RuleGenerator can process them)

## Inputs Required

| Input | Source | Notes |
|-------|--------|-------|
| Geometry | Rhino brep/mesh on `Wasp::Parts::<PartName>` layers | One geometry per part type, organized by scaffold |
| Connection locations | Planes on geometry faces (from scaffold Step 4) | Direction vector = mating normal |
| Connection types | Text labels (optional) | Only needed if using typed rules |
| Part name | String matching layer name | Must be unique within definition |

## Part vs AdvancedPart Decision

| Need | Use |
|------|-----|
| Basic stochastic aggregation | Part |
| Constraints (supports, colliders, adjacency) | **AdvancedPart** |
| Hierarchy (sub-parts, macro parts) | **AdvancedPart** |
| Smart attributes | **AdvancedPart** |
| Additional colliders | **AdvancedPart** |
| DisCo VR export | Either (but AdvancedPart if constrained) |

**Cannot upgrade later** — switching Part→AdvancedPart requires full rewire.
Choose AdvancedPart when in doubt for structural/architectural workflows.

## Recipe References

| Concept | Recipe ID | Curriculum Steps |
|---------|-----------|-----------------|
| Basic part definition | `098491b7` | Steps 1-3 |
| Part with attributes | `16f4319f` | Steps 1-3 |
| AdvancedPart (for constraints) | `0780962c` | Steps 1-2 |
| Transform start point | `fba88cfa` | Steps 1-3 |
| Geometry replacement | `2fe5805e` | Steps 1-3 |

## Tool Call Pattern

```python
# BATCH: Part Definition (repeat per part type)

# Step 1: Create the exact resolved geometry-reference parameter/pipeline
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[{"temp_id": "T1", "guid": "$GUID_GEOMETRY_REFERENCE_PIPELINE", "pos": [100, 200]}],
)
# Record T1 as $PART_A_GEO, then set its Rhino reference with the explicit
# parameter-reference tool using the approved objects on Wasp::Parts::<PartName>.
# Note: Layer name comes from scaffold Step 3 — geometry was validated and organized there

# Step 2: Define connection planes
# Option A: From direction vectors (most common)
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[{"temp_id": "T1", "guid": "$GUID_WASP_CONNECTION_FROM_DIRECTION", "pos": [300, 200]}],
)
# Record T1 as $CONN_A_1.
# Wire: direction vector → Connection.DIR, geometry → Connection.GEO

# Option B: From plane directly
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[{"temp_id": "T1", "guid": "$GUID_WASP_CONNECTION_FROM_PLANE", "pos": [300, 350]}],
)
# Record T1 as $CONN_A_2.
# Wire: plane → Connection.PLN, geometry → Connection.GEO

# Step 3: Merge connections if multiple
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[{"temp_id": "T1", "guid": "$GUID_MERGE_COMPONENT", "pos": [500, 275]}],
)
# Record T1 as $CONN_A_MERGE.
# Wire: $CONN_A_1 → Merge.D1, $CONN_A_2 → Merge.D2

# Step 4: Create Part (or AdvancedPart)
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[{"temp_id": "T1", "guid": "$GUID_WASP_PART", "pos": [700, 250]}],
)
# Record T1 as $PART_A.
# Wire: $PART_A_GEO → Part.GEO
# Wire: $CONN_A_MERGE → Part.CONN
# Wire: part name panel → Part.NAME

# Step 4 (alternative): Create AdvancedPart
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[{"temp_id": "T1", "guid": "$GUID_WASP_ADVANCED_PART", "pos": [700, 250]}],
)
# Record T1 as $PART_A.
# Wire: same as Part, plus:
# Wire: supports → AdvancedPart.SUP (if constrained)
# Wire: collider → AdvancedPart.COL (if additional colliders needed)
```

### Seeding with TransformPart

When the aggregation needs a specific starting position/orientation:

```python
# After Part is created, add TransformPart
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[{"temp_id": "T1", "guid": "$GUID_WASP_TRANSFORM_PART", "pos": [900, 250]}],
)
# Record T1 as $TRANSFORM_PART.
# Wire: $PART_A → TransformPart.PART
# Wire: base plane → TransformPart.PLN
```

## Gotchas

1. **Connection direction matters** — the direction vector determines which face mates.
   Reversed direction = no valid placements during aggregation
2. **Part names must be unique** — duplicate names cause silent rule conflicts
3. **AdvancedPart vs Part is irreversible** — cannot upgrade without full rewire
4. **Geometry must be mesh for DisCo** — if VR export is planned, mesh the brep first
5. **Connection planes must be ON the geometry** — floating connections cause placement errors
6. **All parts must be defined before RuleGenerator** — adding parts later requires
   regenerating rules (wire all Parts into RuleGenerator as a merged list)

## Outputs

- `$PART_A`, `$PART_B`, ... — Part/AdvancedPart component GUIDs for plan registry
- `$TRANSFORM_PART` (optional) — seeded starting part for aggregation
- Ready for: **wasp-rules** (next in composition order)
