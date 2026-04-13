# Knowledge System Integration

Skills can leverage the Rook knowledge system for intelligent command execution.

## Primary Tool: `rhino_execute_intent`

**Always prefer this over raw `rhino_command`.**

```python
rhino_execute_intent(intent="create a sphere at origin with radius 5")
```

This tool automatically:
1. Searches `command_knowledge.json` for matching commands
2. Uses DSPy to resolve intent to best command + mode
3. Uses MABWiser to select among candidates based on history
4. Builds the correct syntax with proper parameter order
5. Applies gotchas (e.g., Box corner Z values must match)
6. Executes and returns result

### Response Format

```json
{
  "success": true,
  "command": "-Sphere",
  "mode": "default",
  "syntax_used": "_-Sphere 0,0,0 5",
  "objects_created": 1,
  "reasoning_trace": ["Found 3 candidate commands", "Selected -Sphere (score: 0.95)"]
}
```

## Query Knowledge Before Custom Operations

For operations not covered by `rhino_execute_intent`:

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

If `rhino_execute_intent` fails and you find a workaround:

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

1. **Use `rhino_execute_intent` for geometry creation** - It handles knowledge lookup automatically

2. **Query knowledge for complex operations** - Before multi-step workflows, check gotchas

3. **Record corrections** - When you discover workarounds, record them

4. **Reference gotchas in skill docs** - Include known issues in skill's references/

5. **Trust the MAB** - The system learns from successes/failures over time
