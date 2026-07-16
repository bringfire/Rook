# wasp-rules — RuleGenerator Modes

RuleGenerator auto-generates valid aggregation rules from a set of Parts.
Eliminates manual rule enumeration — the primary scaling bottleneck in discrete
aggregation (2 parts x 3 connections = 36 rules; 5 parts x 4 connections = 400 rules).

## When to Use

- **After wasp-parts** — Parts must exist before rules can be generated
- **Before wasp-aggregate** or **wasp-grammar-aggregate** — rules feed into aggregation
- When the user does NOT want to manually specify every part-to-part connection rule
- Skip this sub-skill only when using **wasp-learn** (Rules From Aggregation extracts rules instead)

## Inputs Required

| Input | Source | Notes |
|-------|--------|-------|
| Parts | wasp-parts output | All Part/AdvancedPart components, merged into one list |
| Mode | Design decision | Basic (0), Typed (1), or Grammar (2) |
| Connection types | Part definitions | Only needed for Typed/Grammar modes |
| Grammar text | Panel/Chirp | Only needed for Grammar mode |

## RuleGenerator Modes

### Mode 0: Basic (All-to-All)
Every connection can mate with every other connection. Simplest, most permissive.

**Use when:** Part geometry naturally constrains valid placements (e.g., LEGO studs
only fit LEGO holes). No need for explicit filtering.

### Mode 1: Typed (Connection Types)
Connections with matching type labels can mate. Type = string label on each connection.

**Use when:** Parts have named connection types (e.g., "floor", "wall", "ceiling")
and only same-type connections should mate. Typical for architectural assemblies.

### Mode 2: Grammar
Explicit text grammar defining which connection types can mate with which.
Grammar syntax: `type_A > type_B` (A can connect to B).

**Use when:** Fine-grained control needed. E.g., "floor connects to ceiling but not
to wall". Also used when Chirp authoring cascade generates connection rules.

**Note:** This is **connection grammar** (filtering which connections mate), distinct from
**aggregation grammar** in wasp-grammar-aggregate (which governs placement sequence).

## Recipe References

| Concept | Recipe ID | Curriculum Steps |
|---------|-----------|-----------------|
| RuleGenerator basics | `c5ac8ffa` | Steps 1-3 |
| Connection types | `c9f10925` | Steps 1-4 |
| Rules grammar mode | `8487fbeb` | Steps 1-4 |
| Rules visualizer | `c46205e4` | Steps 1-8 |

## Tool Call Pattern

```python
# BATCH: Rule Generation

# Steps 1-2: resolved Merge and RuleGenerator components
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "guid": "$GUID_MERGE_COMPONENT", "pos": [800, 100]},
        {"temp_id": "T2", "guid": "$GUID_WASP_RULE_GENERATOR", "pos": [1000, 100]},
    ],
)
# Record T1/T2 as $PARTS_MERGE/$RULE_GEN.
# Wire: $PART_A → Merge.D1, $PART_B → Merge.D2, ...
# Wire: $PARTS_MERGE → RuleGenerator.PART

# Step 3 (Mode 1 — Typed): Set grammar mode
# Connection types are already defined in wasp-parts via Connection components
# RuleGenerator auto-filters by matching types — no extra wiring needed

# Step 3 (Mode 2 — Grammar): Add grammar text panel
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[{"temp_id": "T1", "type": "panel", "content": "floor > floor\nwall > wall\nceiling > ceiling", "pos": [800, 250]}],
)
# Record T1 as $GRAMMAR_PANEL.
# Wire: $GRAMMAR_PANEL → RuleGenerator.GRAMMAR

# CHECKPOINT
# Bounded-poll gh_status until ready_for_edit is true, solverEnabled is true,
# and solutionState is PostProcess; stop on timeout or disabled/unknown state.
gh_errors()
# → Expected: RuleGenerator produces a list of Rule objects
```

### Adding Rules Visualizer (Optional, for Debugging)

```python
# After RuleGenerator, add visualizer to inspect generated rules
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[{"temp_id": "T1", "guid": "$GUID_WASP_RULES_VISUALIZER", "pos": [1200, 100]}],
)
# Record T1 as $RULES_VIZ.
# Wire: $RULE_GEN → RulesVisualizer.RULES
# Wire: integer slider → RulesVisualizer.INDEX (to browse rules)
```

## Gotchas

1. **Wire ALL parts before generating** — RuleGenerator needs the complete part set.
   Adding a part later requires regenerating rules (rewire the merged list)
2. **Connection types are case-sensitive** — "Floor" != "floor"
3. **Grammar mode syntax** — each line is `type_A > type_B`. Use `>` not `→` or `->`
4. **Rules Visualizer is display-only** — it shows rules but doesn't filter them.
   To select specific rules by index, wire an integer slider to its INDEX input
5. **Two levels of grammar in Wasp** — connection grammar (this sub-skill, filtering)
   vs aggregation grammar (wasp-grammar-aggregate, directing sequence). Don't confuse them

## Outputs

- `$RULE_GEN` — RuleGenerator component GUID, output is a list of Rule objects
- Ready for: **wasp-aggregate** or **wasp-grammar-aggregate** (next in composition order)
- Optional: **wasp-field**, **wasp-constraints**, **wasp-catalog** can be composed in parallel
