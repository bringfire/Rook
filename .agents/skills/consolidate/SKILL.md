---
name: consolidate
description: |
  Run DSPy-based knowledge consolidation on GH components, Rhino commands, or
  pattern knowledge. Use when user mentions: consolidate, consolidation, structural
  analysis, component families, shared behaviors, tier commands, condense knowledge,
  update knowledge structure, or wants to analyze relationships between components/commands
  after adding new entries to the knowledge store.
---

# Knowledge Consolidation

Run DSPy structural consolidation to discover families, shared behaviors, similar pairs,
and I/O patterns across components or commands. Uses the model set in `DSPY_MODEL` env var
(currently Opus).

## When to Consolidate

- After bulk cataloging new GH components (e.g., 10+ new entries)
- After learning many new Rhino commands
- When explicit component/tool discovery repeatedly resolves the wrong target (structure may be stale)
- On user request

## Quick Reference

| Target | Function | Output |
|--------|----------|--------|
| GH Components | `consolidate_gh_components()` | `component_structure.json` + updates UnifiedStore notes + `tiered_knowledge.json` (derived cache) |
| Rhino Commands | `consolidate_commands()` | `command_structure.json` |
| Command Tiers | `tier_commands()` | `condensed_command_knowledge.json` |
| Pattern Tiers | `consolidate_all_tools()` | `condensed_knowledge.json` |

## Configuration

All consolidation reads the model from `DSPY_MODEL` env var in `mcp_server/.env`.
To override for a single run, pass `model="..."` to the convenience functions.

```
# mcp_server/.env
DSPY_MODEL=<configured-model>       # Used by all consolidation paths
ANTHROPIC_API_KEY=sk-ant-...        # Required
```

Central config: `mcp_server/src/rook/learning/dspy_config.py`
- `configure_dspy(model=None)` reads `DSPY_MODEL` env var, falls back to `DEFAULT_MODEL`
- All consolidation convenience functions pass `model=None` by default

## Workflow

### Step 1: Check Current State

Before consolidating, understand what needs updating.

```python
# GH components — check how many are cataloged
gh_knowledge_query(intent="structure overview")

# Or query the structure directly
gh_structure_query()  # Shows families, pair counts, pattern counts
```

### Step 2: Choose Consolidation Target

See [consolidation-paths.md](./references/consolidation-paths.md) for detailed instructions
on each consolidation path (GH, Commands, Patterns).

**Most common:** After bulk component cataloging, run GH consolidation:

```python
# From MCP tool
gh_consolidate()
```

This calls `GHConsolidator.consolidate_full()` which runs the 4-step DSPy pipeline:
1. Identify component families
2. Find shared behaviors
3. Find similar component pairs
4. Extract I/O patterns

### Step 3: Verify Results

```python
# Check structure was created/updated
gh_structure_query()

# Verify a specific component by GUID, name, or stable_key
gh_structure_query(guid="<some-guid>")
gh_structure_query(name="Sphere")
gh_structure_query(stable_key="primitives|surfaces|sphere")

# Verify discovery still resolves the expected component and guidance
gh_library(search="Circle", exact=True)
gh_knowledge_query(intent="circle with center and radius", depth="context")
```

### Step 4: Record in Memory

After consolidation, update MEMORY.md with:
- Number of families discovered
- Number of shared behaviors / similar pairs
- Any issues found

## Gotchas

1. **Consolidation is expensive** — Each run makes many LLM calls. Don't run on every small change.
2. **Temperature is 0.3** — All consolidation uses low temperature for consistency (hardcoded in convenience functions).
3. **Batch size is 15** — Components/commands processed in batches of 15 to stay within token limits.
4. **Existing families preserved** — `GHConsolidator` respects existing family assignments, only classifying components with `family="unknown"`.
5. **Structure updates UnifiedStore AND tiered_knowledge** — `consolidate_full()` writes `family` and `similar_to` into UnifiedStore note `type_data` (primary), then updates `tiered_knowledge.json` as a derived cache.
6. **Observations from component_observations.json** — Runtime observations (462 entries, name-keyed) are resolved to GUIDs and wired into the shared behavior DSPy pass as evidence.
7. **stable_key in structure output** — `component_structure.json` includes a `component_metadata` section mapping GUID → `{name, stable_key}` for name-based queries.

## References

- [consolidation-paths.md](./references/consolidation-paths.md) — Detailed guide for each consolidation target
