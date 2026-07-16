# wasp-disco-export — DisCo VR Export

Export Wasp aggregation definitions to DisCo (Discrete Collaboration), a Unity-based
VR application for interactive assembly. Produces JSON setup files that DisCo loads
for multiplayer design sessions with physics and connection rules.

## When to Use

- When the user mentions **VR**, **DisCo**, **multiplayer design**, **interactive assembly**
- When a Wasp aggregation should be explored interactively in virtual reality
- Post-aggregation workflow — the definition must be complete before export
- Can be combined with Datasmith export (VR design review + UE5 production viz)

## Inputs Required

| Input | Source | Notes |
|-------|--------|-------|
| Parts | wasp-parts output | All parts for DisCo scene |
| Rules | wasp-rules output | Connection rules for DisCo's rule engine |
| Constraints | wasp-constraints output (optional) | Carried into DisCo |
| Export path | Text panel | Directory for output JSON files |
| Rule groups | Text/panel (optional) | Group rules for DisCo's rule filtering UI |
| Environment settings | Various (optional) | Game world parameters |
| Player settings | Various (optional) | Multiplayer configuration |

## Critical Requirements

1. **Units MUST be meters** — DisCo works in meters. Rhino file must be in meters.
   If Rhino is in millimeters, scale geometry before export.
2. **Geometry must be mesh** — DisCo is mesh-based, not NURBS. Brep geometry must be
   meshed before Wasp2DisCo export (use Rhino's Mesh command or GH mesh component).

## Recipe References

| Concept | Recipe ID | Curriculum Steps | Components |
|---------|-----------|-----------------|------------|
| DisCo VR export | `d3a3bfc0` | 11 steps | 115 |

## Tool Call Pattern

```python
# BATCH: DisCo Export Setup

# Steps 1-3: mesh conversion, export path, and resolved Wasp2DisCo component
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "guid": "$GUID_MESH_BREP_COMPONENT", "pos": [100, 800]},
        {"temp_id": "T2", "type": "panel", "content": "C:/path/to/disco_export/", "pos": [1700, 600]},
        {"temp_id": "T3", "guid": "$GUID_WASP_TO_DISCO", "pos": [1900, 600]},
    ],
)
# Record T1-T3 as $MESH_CONVERT, $DISCO_PATH, and $WASP2DISCO.
# Wire: part geometry → MeshBrep.B; use meshed output for Part geometry.
# Wire: parts → Wasp2DisCo.PART
# Wire: rules → Wasp2DisCo.RULE
# Wire: $DISCO_PATH → Wasp2DisCo.PATH

# Step 4 (optional): Rule groups for DisCo UI
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[{"temp_id": "T1", "type": "panel", "content": "<rule group definitions>", "pos": [1700, 700]}],
)
# Record T1 as $RULE_GROUPS.
# Wire: $RULE_GROUPS → Wasp2DisCo.RG

# Step 5 (optional): Environment settings
# Wire: gravity, boundaries, etc. to Wasp2DisCo environment inputs

# Step 6 (optional): Player settings
# Wire: player count, roles, etc. to Wasp2DisCo player inputs

# Step 7: Export trigger
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[{"temp_id": "T1", "type": "toggle", "value": False, "pos": [1700, 800]}],
)
# Record T1 as $EXPORT_TRIGGER.
# Wire: $EXPORT_TRIGGER → Wasp2DisCo.SAVE

# CHECKPOINT
# Bounded-poll gh_status until ready_for_edit is true, solverEnabled is true,
# and solutionState is PostProcess; stop on timeout or disabled/unknown state.
gh_errors()
```

### Loading DisCo Results Back

```python
# BATCH: Import DisCo Aggregation

# Steps 1-2: result path + resolved LoadFromDisCo component
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "type": "panel", "content": "C:/path/to/disco_aggregation.json", "pos": [100, 900]},
        {"temp_id": "T2", "guid": "$GUID_WASP_LOAD_FROM_DISCO", "pos": [300, 900]},
    ],
)
# Record T1/T2 as $DISCO_RESULT_PATH/$LOAD_DISCO.
# Wire: $DISCO_RESULT_PATH → LoadFromDisCo.PATH

# Loaded aggregation can feed into:
# - wasp-learn (extract rules from VR-designed arrangement)
# - wasp-save-load (checkpoint for further iteration)
# - Datasmith export (VR design → production visualization)
```

## Dual Export Paths

A Wasp aggregation can flow through BOTH export paths simultaneously:

```
                    ┌── Wasp2DisCo ──→ DisCo (Unity VR)
                    │   Interactive design, physics, multiplayer
Wasp Aggregation ───┤
                    │
                    └── Datasmith ──→ UE5 (Engram)
                        Nanite, Lumen, production visualization
                        (via rhino_prepare_for_game_export pipeline)
```

For Datasmith export, use the existing Rook pipeline (not a Wasp-specific tool):
1. `rhino_tag_object_semantic` — tag aggregated parts with game metadata
2. `rhino_validate_export` — pre-flight geometry checks
3. `rhino_export_with_manifest` — export .3dm + manifest.json

## Gotchas

1. **Units MUST be meters** — the #1 DisCo failure mode. Check Rhino document units
   before export. If millimeters, add a Scale component (factor 0.001) before Part geometry.
2. **Mesh geometry required** — DisCo cannot use NURBS/Brep. Insert MeshBrep component
   in the geometry pipeline before Part creation.
3. **Rule groups affect DisCo UI** — in DisCo, players can toggle rule groups on/off.
   Group rules logically (e.g., "structural rules", "facade rules") for intuitive VR interaction.
4. **Export trigger is one-shot** — toggle true to export, then back to false.
   Leaving true causes repeated exports on every solve.
5. **Two output files** — `_setup.json` (parts, rules, constraints, environment) and
   `_player.json` (multiplayer configuration). Both must be in the same directory for DisCo.
6. **LoadFromDisCo imports VR results** — DisCo-designed assemblies can return to GH for
   structural analysis, rule extraction (wasp-learn), or production export (Datasmith).

## Outputs

- `$WASP2DISCO` — Wasp2DisCo component GUID
- `_setup.json` + `_player.json` files in export directory
- `$LOAD_DISCO` (optional) — LoadFromDisCo component for importing VR results
- Composes with: wasp-learn (extract rules from VR design), Datasmith pipeline
