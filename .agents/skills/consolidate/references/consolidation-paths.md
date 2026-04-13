# Consolidation Paths Reference

Detailed instructions for each consolidation target. All paths read the model from `DSPY_MODEL` env var via `dspy_config.py`.

---

## Path 1: GH Component Consolidation

**When:** After bulk cataloging 10+ new GH components via `gh_explore_component`.

**What it does:** Discovers families, shared behaviors, similar component pairs, and I/O patterns across all cataloged GH components.

**MCP tool:**
```python
gh_consolidate()
```

**Python API:**
```python
from rook.learning.gh_consolidator import consolidate_gh_components
structure = consolidate_gh_components()
```

**Pipeline (4 steps):**
1. `IdentifyComponentFamilies` — Groups components by function (primitives, curves, surface_ops, transforms, etc.). Respects existing family assignments; only classifies `family="unknown"` components.
2. `FindSharedBehaviors` — Finds gotchas/behaviors that apply across multiple components (e.g., "enum params must be 0-2"). Now includes runtime observations from `component_observations.json` as evidence alongside gotchas/errors.
3. `IdentifySimilarComponents` — Links components with shared I/O patterns (e.g., Pipe ↔ Sweep1). Searches within-family first, then cross-family.
4. `IdentifyIOPatterns` — Extracts common parameter patterns (curve_input, radius_param, brep_output).

**Input files:**
- `knowledge/gh/tiered_knowledge.json` — Component definitions with params, gotchas
- `knowledge/gh/component_observations.json` — Runtime observations (462 entries, name-keyed list; resolved to GUIDs at load time)

**Output files:**
- `knowledge/gh/component_structure.json` — Full structural analysis with `component_metadata` (GUID → name + stable_key)
- UnifiedStore notes (`knowledge/gh/notes/*.json`) — Updated with `family` and `similar_to` in `type_data` (primary target)
- `knowledge/gh/tiered_knowledge.json` — Updated with `family` and `similar_to` fields (derived cache)

**Verification:**
```python
# Check structure overview
gh_structure_query()

# Check a specific component by GUID, name, or stable_key
gh_structure_query(guid="<some-guid>")
gh_structure_query(name="Sphere")
gh_structure_query(stable_key="primitives|surfaces|sphere")

# Test intent resolution
gh_execute_intent(intent="create a circle with center and radius")
```

**Batch size:** 15 components per DSPy call.

---

## Path 2: Rhino Command Consolidation

**When:** After learning many new Rhino commands, or when `rhino_execute_intent` picks wrong targets.

**What it does:** Two sub-paths — structural consolidation (families + relationships) and tiering (condensed knowledge).

### Path 2a: Structural Consolidation

**MCP tool:** Not directly exposed. Run via Python:
```python
from rook.learning.command_consolidator import consolidate_commands
structure = consolidate_commands()
```

**Pipeline (4 steps):**
1. `IdentifyCommandFamilies` — Groups commands by function (primitives, curves, surfaces, transforms, booleans, annotations, editing, analysis).
2. `FindSharedGotchas` — Finds gotchas that apply across commands (e.g., "curve must be closed" for surface creation commands).
3. `IdentifySimilarCommands` — Links similar commands (e.g., Sphere ↔ Ellipsoid, Move ↔ Copy).
4. `IdentifyModePatterns` — Extracts mode patterns (center, 3point, diameter) with typical syntax.

**Input:** `knowledge/commands/command_knowledge.json`
**Output:** `knowledge/commands/command_structure.json`

### Path 2b: Command Tiering

**Prerequisite:** Run Path 2a first (needs `command_structure.json`).

```python
from rook.learning.command_consolidator import tier_commands
store = tier_commands()
```

**What it does:** For each command, generates:
- **QUICK** (~20 tokens): `_-Sphere center radius | Collinear points fail in 3Point`
- **CONTEXT** (~50 tokens per mode): Mode-specific syntax, options, gotchas
- **ERRORS** (~30 tokens): What fails and why

Uses `GenerateAllTiers` DSPy signature — one call per command.

**Input:** `command_knowledge.json` + `command_structure.json`
**Output:** `knowledge/commands/condensed_command_knowledge.json`

**Token reduction:** ~95% for quick queries, ~87% for context queries.

### Reconsolidation

The `ReconsolidationManager` tracks new commands and failures. It triggers incremental reconsolidation after 10 new commands or 3+ failures on a related command. Creates versioned backups with rollback support.

```python
from rook.learning.command_consolidator import CommandConsolidator, ReconsolidationManager

manager = ReconsolidationManager(
    structure_path='knowledge/commands/command_structure.json',
    knowledge_path='knowledge/commands/command_knowledge.json'
)

if manager.should_reconsolidate():
    result = manager.reconsolidate()
```

---

## Path 3: Pattern Knowledge Tiering

**When:** After overnight learning runs that produce 100+ raw patterns, or when pattern retrieval is returning too many tokens.

**What it does:** Takes raw patterns from the knowledge graph and transforms them into tiered, contextual knowledge.

```python
from rook.learning.consolidator import consolidate_all_tools

knowledge = consolidate_all_tools(
    knowledge_path="knowledge/local.json",
    output_path="knowledge/condensed_knowledge.json",
    min_patterns=5,  # Skip tools with fewer than 5 patterns
)
```

**Pipeline (5 steps per tool):**
1. `IdentifyContexts` — Discovers usage contexts from pattern sample (e.g., basic, nested, colored for `rhino_layer_create`).
2. `ClassifyPattern` — Assigns each pattern to a context.
3. `ConsolidateContext` — Distills patterns per context into summary, required/optional params, gotchas, example.
4. `ExtractErrorCategories` — Groups antipatterns into error categories with avoidance strategies.
5. `GenerateQuickSummary` — Creates 30-word-or-less quick tier.

**Output tiers:**
- **QUICK** (~20 tokens): Essential facts
- **CONTEXT** (~50 tokens per context): Context-specific rules
- **ERRORS** (~30 tokens): What fails and why
- **RAW** (500+ tokens): Full patterns — only when debugging

**Input:** `knowledge/local.json` (knowledge graph with patterns/antipatterns)
**Output:** `knowledge/condensed_knowledge.json`

**Single-tool consolidation:**
```python
from rook.learning.consolidator import consolidate_single_tool

tool = consolidate_single_tool(
    tool_name="rhino_layer_create",
    knowledge_path="knowledge/local.json",
)
```

---

## Decision Matrix

| Scenario | Path | Command |
|----------|------|---------|
| Bulk cataloged GH components | Path 1 | `gh_consolidate()` |
| Learned new Rhino commands | Path 2a | `consolidate_commands()` |
| Need condensed command tiers | Path 2b | `tier_commands()` |
| 10+ new commands accumulated | Path 2 (auto) | `manager.reconsolidate()` |
| Overnight learning produced patterns | Path 3 | `consolidate_all_tools(...)` |
| Single tool has many patterns | Path 3 (single) | `consolidate_single_tool(...)` |
| Intent resolution picks wrong target | Path 1 or 2a | Re-run structural consolidation |
