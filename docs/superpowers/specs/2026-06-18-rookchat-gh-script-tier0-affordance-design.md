# RookChat GH Script Tier-0 Affordance Hotfix Design

## Problem

Live one-box smoke testing showed a weaker local model calling `gh_errors`
with script-creation arguments before it ever loaded `gh_canvas`:

```text
gh_errors(code=..., pins_out=..., name=...)
-> unexpected_arguments
```

The schema-contract work is behaving correctly:

- `gh_errors` is exposed as a zero-argument tool.
- the dispatcher rejects unexpected arguments.
- the error tells the model to call `gh_create_csharp_script` or
  `gh_create_script(language="csharp")`.

The remaining failure is initial affordance. At the start of an agent turn,
`gh_errors` is visible in Tier 0, but the correct script-creation tools are
hidden behind `request_tools("gh_canvas")`. That gives weaker models an obvious
bad move before the good move is available.

## Goal

Make the correct GH script-creation affordance visible in the initial
RookChat agent tool surface, without weakening schemas, adding model-specific
prompt hacks, or auto-routing malformed tool calls.

## Design

Add these tools to `AGENT_TIER_0` in `mcp_server/src/rook/agent/tool_groups.py`:

- `gh_create_script`
- `gh_create_python_script`
- `gh_create_csharp_script`
- `gh_update_script`

Keep `gh_errors` in Tier 0. It remains useful for verification, but it should
no longer be the only GH script-adjacent tool visible at turn start.

No dispatcher behavior changes are needed. Malformed `gh_errors` calls should
continue to return `unexpected_arguments`.

No schema changes are needed. Existing schema-contract normalization remains
the source of truth for closed, model-visible schemas.

## Tests

Add focused non-live tests proving the exposed initial active schema set, not
just set membership:

- default `ChatRunner` initial active schemas include `gh_create_csharp_script`;
- the exposed `gh_create_csharp_script` schema is closed and requires
  `["code", "pins_in", "pins_out"]`;
- `gh_errors` remains zero-argument;
- a non-live transcript can call `gh_create_csharp_script` in round one without
  a preceding `request_tools` call.

Run existing focused RookChat schema/transcript tests to make sure the
affordance change does not regress the stricter contract work.

## Non-Goals

- Do not remove `gh_errors` from Tier 0.
- Do not auto-route malformed `gh_errors` payloads to script-creation tools.
- Do not loosen tool schemas.
- Do not add broad prompt behavior changes.
- Do not tune for a single weak model at the expense of truthful tool
  contracts.
- Do not run live Rhino/deploy verification as an automated gate for this
  hotfix.
