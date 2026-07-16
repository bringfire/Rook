---
name: rhino-command-safety
enabled: true
event: PreToolUse
tool_matcher: mcp__rook__rhino_command
action: warn
---

**Rhino safety: prefer explicit typed routes**

`rhino_command` goes through RunScript and can still leave Rhino waiting for
input or trigger modal UI when the command path is wrong.

Use it only when no typed route exists.

Before continuing, check:
- Have you rediscovered the admitted Rhino tools and inspected current state?
- Is there a typed tool such as `rhino_create`, `rhino_transform`, `rhino_boolean`, `rhino_loft`, or `rhino_sweep`?
- Is the command fully scripted with no interactive prompt path?

If you do use `rhino_command`, prefer underscored scripted forms like `_-Box`
and verify the result carefully.
