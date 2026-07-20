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

Rediscover the admitted Rhino tools, inspect the document, and call the exact
typed operation:

```python
rhino_create(type="BOX", origin=[0, 0, 0], width=10, depth=10, height=5)
rhino_create(type="SPHERE", center=[0, 0, 0], radius=5)
rhino_objects()  # verify the host result
```

Use `knowledge_query` before an unfamiliar scripted command. `rhino_command`
must be fully scripted and preflighted; `rhino_execute` must be short and
non-interactive. Both are fallbacks when no typed route fits.

### For Grasshopper Components

Inspect, resolve, edit, verify:

```python
snap = gh_snapshot()
gh_library(search="Sphere", exact=True)
gh_edit(
    epoch=snap["epoch"],
    create=[
        {"temp_id": "T1", "type": "slider", "nick": "R", "min": 0, "max": 10, "value": 5, "pos": [100, 100]},
        {"temp_id": "T2", "name": "Sphere", "pos": [400, 100]},
    ],
    connect=["T1.O0>T2.I1"],
)
gh_snapshot()
```

Use `gh_knowledge_query` when the library name is unclear. Inspect
`edit_summary.errors`, `gh_errors`, and the follow-up snapshot; undo or clean up
before retrying a partially committed edit.

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
| **Unified Store** | A-MEM patterns, recipes, struggles | `gh_knowledge_query(intent="...")` |
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
├─ Rhino → inspect state, then use an explicit typed `rhino_*` route
└─ Grasshopper → gh_snapshot → resolve component → gh_edit → gh_snapshot

Need to QUERY objects?
├─ Document info → rhino_document()
├─ Object list → rhino_objects()
├─ Specific geometry → rhino_geometry(id="...")
└─ GH canvas → gh_snapshot()

Need to TRANSFORM?
├─ Simple → rhino_transform(ids=[...], operation="move", ...)
├─ Complex → rediscover a matching typed transform route or use a bounded non-interactive script
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

1. **Never send an unverified interactive command** - Query knowledge and preflight a fully scripted form
2. **Never guess component GUIDs** - Resolve them with `gh_library` or `gh_knowledge_query`
3. **Never assume a tool exists** - Rediscover the admitted surface before selecting a route
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
| Create Rhino geometry | `rhino_create` | `type="SPHERE", center=[0,0,0], radius=5` |
| Create GH components | `gh_edit` | `epoch=..., create=[...], connect=[...]` |
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

**Rediscover, inspect, execute explicitly, and verify.** Prefer typed Rhino routes
and bounded `gh_edit` batches. Use knowledge lookup before unfamiliar operations,
and restore partial mutations before retrying.

---

*Last updated: 2026-06-05*
