# New Claude Onboarding Guide

> **Purpose:** Get a newly-instantiated Claude productive in Rook within 30 seconds.

---

## Step 1: Verify Connection (Required)

```python
# Run these immediately on first engagement:
rhino_ping()        # Should return "pong"
rhino_document()    # Should return document info
gh_status()         # Should return GH canvas info (if using Grasshopper)
```

If any fail, the user needs to restart Rhino or run `/mcp` to reconnect.

---

## Step 2: Understand the Primary Tools

### For Rhino Geometry

**USE THIS:** `rhino_execute_intent`
```python
rhino_execute_intent(intent="create a box from 0,0,0 to 10,10,0 with height 5")
rhino_execute_intent(intent="create a sphere at origin with radius 5")
```

**Why:** It automatically queries learned knowledge, selects best syntax via DSPy/MAB, and executes correctly.

**DO NOT use:** `rhino_command` directly (bypasses knowledge system, likely wrong syntax).

### For Grasshopper Components

**USE THIS:** `gh_execute_intent`
```python
gh_execute_intent(intent="create a sphere with radius slider")
```

**Why:** It looks up correct component GUIDs from knowledge and auto-wires inputs.

**DO NOT use:** Direct component creation tools (they're hidden for a reason).

---

## Step 3: Knowledge Graph Status

The A-MEM knowledge graph is **active and linked**:

| Metric | Value |
|--------|-------|
| Total notes | ~1,230 (component, recipe, teaching, struggle) |
| Linked notes | ~95% |
| Graph edges | ~9,100 |
| GH Components cataloged | ~945 (full I/O params) |
| GUIDs in sparse index | ~942 |
| Component families | ~90 |
| Intent mappings | ~1,533 |

Follow links between notes to discover related primitives and composable patterns.

## Step 4: Knowledge Systems Overview

There are **three main knowledge systems**. Know which to query:

| System | Purpose | Query Tool |
|--------|---------|------------|
| **Command Knowledge** | Rhino command syntax, modes, gotchas | `knowledge_query(intent="...")` |
| **Unified Store** | A-MEM patterns, recipes, struggles | Queried automatically by `gh_execute_intent` |
| **GH Knowledge** | Component GUIDs, wiring patterns | `gh_knowledge_query(intent="...")` |

### When to Query Knowledge

1. **Before unknown commands** - Query first, then execute
2. **After failures** - Use `depth="errors"` to see gotchas
3. **When exploring** - Use `depth="raw"` for full details

```python
# Before trying a command you're not confident about:
knowledge_query(intent="create cone", depth="context")  # ~80 tokens
# Returns: syntax templates, modes, gotchas

# After a failure:
knowledge_query(intent="create cone", depth="errors")   # ~40 tokens
# Returns: common failures and what to avoid
```

---

## Step 5: Decision Tree

```
Need to CREATE geometry?
├─ Rhino → rhino_execute_intent(intent="...")
└─ Grasshopper → gh_execute_intent(intent="...")

Need to QUERY objects?
├─ Document info → rhino_document()
├─ Object list → rhino_objects()
├─ Specific geometry → rhino_geometry(id="...")
└─ GH canvas → gh_snapshot()

Need to TRANSFORM?
├─ Simple → rhino_transform(ids=[...], operation="move", ...)
├─ Complex → rhino_execute_intent(intent="move X by 10,0,0")
├─ Interactive → rhino_gumball_activate() (persistent AI Gumball)
└─ Delete → rhino_delete(ids=[...])

Need to MEASURE?
├─ Distance → rhino_measure_distance(...)
├─ Area → rhino_measure_area(...)
├─ Volume → rhino_measure_volume(...)
└─ Bounding box → rhino_measure_bbox(...)

Need to UNDERSTAND the scene?
├─ Scene graph → scene_graph() (spatial index of all objects)
├─ Scene context → scene_context() (what's near a point/object)
└─ Scene stats → scene_stats() (document summary)

Need LLM-POWERED GH components?
└─ Chirp → chirp_create(category="...", ...)

Something FAILED?
├─ Query knowledge → knowledge_query(intent="...", depth="errors")
├─ Check GH errors → gh_errors()
└─ Read CLAUDE.md → Look for gotchas section
```

---

## Step 6: What NOT to Do

1. **Never use `rhino_command` directly** - Bypasses knowledge system, likely wrong syntax
2. **Never guess component GUIDs** - Use `gh_execute_intent` which looks them up
3. **Never say "I can't"** - The tool exists, you just haven't found it yet
4. **Never record routine successes** - Only record when `correction_detected: true`
5. **Never use curl/HTTP directly** - Always use MCP tools

---

## Step 7: When You're Stuck

1. **Re-read tool descriptions** - The answer is usually in the parameters
2. **Query knowledge with `depth="errors"`** - See what commonly fails
3. **Check `gh_errors()`** - For Grasshopper issues
4. **Read CLAUDE.md** - Comprehensive reference

---

## Quick Reference Card

| Task | Tool | Example |
|------|------|---------|
| Create Rhino geometry | `rhino_execute_intent` | `intent="create sphere radius 5"` |
| Create GH components | `gh_execute_intent` | `intent="sphere with slider"` |
| Set GH Python script | `gh_set_script` | `guid="...", script="import Rhino..."` |
| Query before unknown command | `knowledge_query` | `intent="...", depth="context"` |
| Check document state | `rhino_document` | - |
| List objects | `rhino_objects` | - |
| Check GH canvas | `gh_snapshot` | - |
| Check GH errors | `gh_errors` | - |
| Transform objects | `rhino_transform` | `operation="move"` |
| AI Gumball (interactive) | `rhino_gumball_activate` | Persistent mode, captures drags |
| Measure | `rhino_measure_*` | Various |
| Metrics dashboard | `metrics_dashboard` | Web dashboard on :8855 |
| Record correction | `knowledge_record` | Only when `correction_detected: true` |

---

## The Golden Rule

**Use `rhino_execute_intent` and `gh_execute_intent` for everything.** They query knowledge, select best approaches, and execute correctly. Only drop to lower-level tools when these fail.

---

*Last updated: 2026-06-05*
