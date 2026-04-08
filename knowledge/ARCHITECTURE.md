# GraphRAG Knowledge System Architecture

## Overview

The Rook Knowledge Graph is a persistent, portable learning system that captures successful patterns and anti-patterns discovered during Claude-Rhino interactions. Unlike Claude's ephemeral session memory, this graph persists across sessions and ships with the plugin.

## Core Insight

When Claude fails at a task, gets corrected, and succeeds, that failure→correction→success cycle represents learned knowledge. The knowledge graph captures:

1. **Intent**: What the user wanted to accomplish
2. **Action**: What tool/operation was attempted
3. **Pattern**: The correct approach that works
4. **Anti-pattern**: The incorrect approach that fails

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    PERSISTENT STATE                              │
│  ┌─────────────────────┐      ┌─────────────────────────────┐   │
│  │   Rhino Document    │      │    Knowledge Graph          │   │
│  │   (geometry, layers)│      │    (patterns, solutions)    │   │
│  └─────────────────────┘      └─────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                    ▲                        ▲
                    │                        │
         HTTP      │              MCP       │
         :9876     │              tools     │
                    │                        │
┌─────────────────────────────────────────────────────────────────┐
│                    EPHEMERAL AGENTS                              │
│  ┌─────────────────────┐      ┌─────────────────────────────┐   │
│  │    Claude Code      │◄────►│      MCP Server             │   │
│  │ (primary reasoning) │      │ (47 tools + knowledge)      │   │
│  └─────────────────────┘      └─────────────────────────────┘   │
│                                           │                      │
│                                           ▼                      │
│                               ┌─────────────────────────────┐   │
│                               │    Rhino Claude (C#)        │   │
│                               │    (embedded assistant)     │   │
│                               └─────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### 1. Query BEFORE Every Action

Claude is "born anew" each session with no memory of past failures. It has no concept of which queries are "uncertain." Therefore:

> **The knowledge graph must be queried BEFORE EVERY Rhino action, not just "uncertain" ones.**

This ensures Claude always has access to relevant patterns and anti-patterns before attempting any operation.

### 2. Token-Efficient Responses

Users speak in natural language, but Claude needs structured, terse responses to minimize token usage:

```json
{
  "intent": "create_nested_layer",
  "pattern": {
    "tool": "rhino_layer_create",
    "params": {"name": "child", "parent": "parent_name"},
    "note": "Use parent param, NOT :: in name"
  },
  "avoid": [
    {"params": {"name": "parent::child"}, "reason": "Creates literal name, not hierarchy"}
  ]
}
```

### 3. Two-Tier Knowledge

1. **Canonical Knowledge** (`canonical.json`): Ships with plugin, curated patterns
2. **Local Knowledge** (`local.json`): User-specific learnings from sessions

At query time, both are merged with local taking precedence for conflicts.

### 4. NetworkX-Compatible Format

Using NetworkX's `node_link_data` format for JSON serialization:

```json
{
  "directed": true,
  "multigraph": false,
  "nodes": [...],
  "links": [...]
}
```

This enables:
- Graph traversal algorithms (shortest path, neighbors)
- Semantic similarity on node labels
- Edge weighting for confidence/relevance

## Node Types

| Type | Purpose | Key Fields |
|------|---------|------------|
| `intent` | What user wants to accomplish | `labels`, `description` |
| `action` | MCP tool/operation | `tool`, `params_schema` |
| `pattern` | Correct approach | `params`, `note`, `weight` |
| `antipattern` | Incorrect approach | `params`, `reason`, `weight` |
| `context` | Environmental conditions | `conditions` |

## Edge Types

| Relation | Meaning | Example |
|----------|---------|---------|
| `solved_by` | Intent → Action | "create_nested_layer" → "rhino_layer_create" |
| `requires` | Action → Pattern | "rhino_layer_create" → "use_parent_param" |
| `avoid` | Action → Antipattern | "rhino_layer_create" → "colons_in_name" |
| `when` | Pattern → Context | "use_parent_param" → "parent_exists" |
| `supersedes` | Pattern → Pattern | Newer solution replaces older |

## MCP Tools

### knowledge_query

Called BEFORE every Rhino action to get relevant patterns.

**Input:**
```json
{
  "intent": "create nested layers in Rhino",
  "tool": "rhino_layer_create"
}
```

**Output:**
```json
{
  "patterns": [
    {"params": {"parent": "<parent_name>"}, "note": "Use parent parameter"}
  ],
  "avoid": [
    {"params": {"name": "parent::child"}, "reason": "Literal name, not hierarchy"}
  ],
  "confidence": 0.95
}
```

### knowledge_record

Called AFTER outcomes to record learnings.

**Input:**
```json
{
  "intent": "create nested layer",
  "action": {"tool": "rhino_layer_create", "params": {"name": "0", "parent": "bringfire"}},
  "outcome": "success",
  "correction_of": {"params": {"name": "bringfire::0"}, "error": "Created literal name"}
}
```

## File Structure

```
knowledge/
├── ARCHITECTURE.md          # This document
├── canonical.json           # Ships with plugin, curated patterns
├── local.json              # User learnings (gitignored)
├── schema.json             # JSON Schema for validation
├── knowledge_feature_list.json  # Pass/fail tests
└── graph.py                # NetworkX utilities (optional)
```

## Query Algorithm

1. Parse intent from user request (semantic labels)
2. Find matching intent nodes by label similarity
3. Traverse edges to find associated actions
4. For the relevant action, collect all patterns and anti-patterns
5. Weight by confidence, recency, edge weights
6. Return structured response

## Recording Algorithm

1. Receive outcome (success/failure) with context
2. If success following a correction:
   - Create or strengthen pattern node
   - Create or strengthen anti-pattern for the failed approach
   - Add `corrected_by` edge
3. Update edge weights based on outcome
4. Persist to local.json

## Evolution Strategy

1. **Bootstrap**: Seed canonical.json with known patterns (like nested layer fix)
2. **Learn**: Record outcomes during sessions to local.json
3. **Curate**: Periodically promote high-confidence local patterns to canonical
4. **Ship**: Updated canonical.json goes out with plugin releases

## Token Budget

Target: <500 tokens per knowledge query response

- Use terse field names
- Omit null/empty fields
- Return only top-N patterns by confidence
- Truncate long descriptions
