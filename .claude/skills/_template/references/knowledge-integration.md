# Knowledge System Integration

Skills can leverage the Rook knowledge system for intelligent command execution.

## Primary Workflow: Discover, Inspect, Execute, Verify

Prefer an explicit typed Rhino route. Rediscover the admitted surface and inspect
current document state before choosing the operation:

```python
rhino_document()
rhino_objects()
rhino_create(type="SPHERE", center=[0, 0, 0], radius=5)
rhino_objects()  # verify the host state changed as expected
```

Typed tools validate inputs and return structured results. If no typed route
fits, query command knowledge, preflight a locale-independent fully scripted
`rhino_command`, or use a short non-interactive `rhino_execute` script as the
last resort. Verify every result and restore partial mutations before retrying.

## Query Knowledge Before Custom Operations

For unfamiliar operations or command fallback:

```python
knowledge_query(
    intent="loft through curves",
    tool="-Loft",           # Optional: specific command
    depth="context"         # "quick" | "context" | "errors" | "raw"
)
```

### Depth Tiers

| Tier | Tokens | Use Case |
|------|--------|----------|
| `quick` | ~20 | Essential facts, you know the tool |
| `context` | ~50 | Specific rules for your use case (default) |
| `errors` | ~30 | What fails and why, debugging |
| `raw` | ~500+ | Full patterns, deep investigation |

### Response Format

```json
{
  "tier": "context",
  "source": "consolidated",
  "data": {
    "summary": "Loft creates surface through profile curves...",
    "gotchas": ["Loft creates OPEN surfaces - use Cap for solid"]
  },
  "available_tiers": ["quick", "context", "errors", "raw"],
  "command_knowledge": {
    "-Loft": {
      "modes": {...},
      "gotchas": [...]
    }
  }
}
```

## Knowledge Store Contents

The knowledge system (`knowledge/commands/command_knowledge.json`) contains 89+ learned patterns:

- **Primitives**: Box, Sphere, Cylinder, Cone, Pyramid
- **Curves**: Circle, Arc, Line, Polyline, Ellipse
- **Surfaces**: Loft, Sweep1, Sweep2, Revolve, ExtrudeCrv, PlanarSrf
- **Solids**: BooleanUnion, BooleanDifference, BooleanIntersection
- **Transforms**: Move, Rotate, Scale, Mirror, Copy
- **Selection**: SelAll, SelNone, SelLast, SelPrev
- **Views**: Zoom, Pan, RotateView, SetView

Each command includes:
- **Modes**: Different ways to invoke (e.g., Box center vs corner)
- **Syntax**: Exact parameter order and format
- **Gotchas**: Known issues and workarounds
- **Preconditions**: Selection requirements

## Recording Corrections

If an explicit typed/scripted operation fails and you find a workaround:

```python
knowledge_record(
    intent="create cone with free direction",
    action={"tool": "rhino_command", "params": {"command": "_-Cone ..."}},
    outcome="success",
    correction_of={
        "params": {"command": "_-Cone _DirectionConstraint=None ..."},
        "error": "Invalid syntax"
    }
)
```

This improves the knowledge system for future executions.

## Best Practices for Skills

1. **Prefer explicit typed geometry tools** - Rediscover the admitted surface, inspect state, call the exact route, and verify

2. **Query knowledge for complex operations** - Before multi-step workflows, check gotchas

3. **Record corrections** - When you discover workarounds, record them

4. **Reference gotchas in skill docs** - Include known issues in skill's references/

5. **Treat retrieval as guidance, not authority** - Review knowledge output before it influences a command or script
