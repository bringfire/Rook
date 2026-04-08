---
name: chirp-require-category
enabled: true
event: bash
tool_matcher: mcp__rook__chirp_create
action: warn
conditions:
  - field: tool_input
    operator: not_contains
    pattern: category
---

**Chirp: Missing category parameter**

The `chirp_create` tool requires a `category` parameter. Valid categories:
- `planner` — Brief → structured parameters
- `interpreter` — Upstream Reasoning → domain-specific parameters
- `critic` — Multiple Reasonings → conflict detection
- `narrator` — Multiple Reasonings → design narrative
- `classifier` — Data → categorical decision
- `gate` — Reasoning → boolean/enum rule activations
- `editor` — Reasoning + Correction → reconciled Reasoning

Use the `/chirp` skill to guide category selection, or specify `category` directly.

Also remember:
- Do NOT include "Correction" in pins_in (auto-added)
- Do NOT include "Reasoning" in pins_out (auto-added)
