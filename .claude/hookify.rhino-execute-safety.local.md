---
name: rhino-execute-safety
enabled: true
event: PreToolUse
tool_matcher: mcp__rook__rhino_execute
action: warn
---

**Rhino safety: `rhino_execute` is last resort only**

Direct Rhino Python is still the highest-risk path for blocking Rhino.

Use it only when no typed route or `rhino_execute_intent` path fits.

Before continuing, check:
- Can this be expressed with a typed Rhino tool instead?
- Can `rhino_execute_intent` route the request safely?
- Does the script avoid `rhinoscriptsyntax.Get*`, `Rhino.Input`, dialogs, or any other interactive UI?

If you proceed, keep the script short, non-interactive, and easy to inspect on failure.
