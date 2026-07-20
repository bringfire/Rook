# Rook — AI Agents for Rhino & Grasshopper

> Rook lets AI agents inspect and operate Rhino 3D and Grasshopper through
> 400+ MCP tools. It supports multiple cloud and local models through LiteLLM.

> **Using this file:** If your working directory is the Rook install folder
> (`%LOCALAPPDATA%\Rook`), this file loads automatically. Otherwise, copy it
> to your project root so Codex can use it as context when working with Rook.
> You can customize the copy with project-specific conventions such as units
> and layer naming.

---

## Start Here

```text
1. Run /mcp and look for "rook".
2. Call rhino_ping; it should return "pong".
3. Inspect the current Rhino document or Grasshopper definition before mutating it.
```

The active MCP profile may advertise a compact tool set. When the exact tool you
need is not visible, use `rook_tools_search` → `rook_tools_read` →
`rook_tools_call`. These gateways discover and invoke admitted tools through the
normal policy path.

**Key docs (load only when needed):**

- `docs/ONBOARDING_NEW_CLAUDE.md` — quick tool-selection reference
- `docs/CURRENT_ARCHITECTURE.md` — current runtime architecture
- `docs/AGENT_ARCHITECTURE.md` — agent loops, tool admission, and chat service
- `docs/TROUBLESHOOTING.md` — common issues and recovery

---

## Operating Model

Keep the primary model as the actor and use explicit tools as bounded operations:

1. **Inspect live state** — identify the active document, definition, objects,
   components, errors, and relevant constraints.
2. **Discover the admitted tool** — search when necessary and read its current
   schema instead of guessing names or arguments.
3. **Act explicitly** — call the smallest typed or structured tool that performs
   the intended operation.
4. **Verify** — inspect the returned receipt and the resulting Rhino or
   Grasshopper state, including solve errors and outputs.
5. **Recover deliberately** — undo or clean up only state created or changed by
   the attempted operation; ask before destructive or unrestorable action.

The knowledge store is **optional advisory context**. It can provide component
facts, patterns, and known failure modes, but it does not authorize mutation,
replace live inspection, or prove that a result succeeded. Do not make knowledge
lookup a mandatory hop before ordinary supported operations.

Record durable knowledge only when a correction has been reproduced and
validated and the record contains no sensitive user content. Do not record
routine successes or guessed explanations automatically.

---

## Primary Workflows

### Grasshopper canvas — `gh_snapshot` → `gh_edit`

This is the default path for inspecting and changing a definition:

1. `gh_snapshot` reads the canvas in one call and returns components, wires,
   groups, diagnostics, data previews, short IDs, and an `epoch`.
2. `gh_edit` submits a batch of explicit changes using that `epoch`:
   create → disconnect → delete → set values → connect → groups.

```python
snap = gh_snapshot()
gh_edit(
    epoch=snap["epoch"],
    create=[...],
    connect=["T1.O0>C2.I1"],
    set_values=[...],
)
```

Treat this as an epoch-validated batched write, not as proof of all-or-nothing
transactionality. Inspect the returned result, then call `gh_snapshot` and
`gh_errors` to verify topology, solve state, and outputs.

`gh_undo` reverses the most recent Grasshopper undo event. A compound workflow
may create more than one undo event, so verify after each undo and call it again
only when the remaining state is known to belong to the attempted operation.

Progressive discovery searches Rook tools, not Grasshopper components. For an
unfamiliar component, use `gh_library` for exact component identity and
`gh_batch_component_info` for SDK-backed input/output metadata. If those tools
are hidden, use progressive discovery to locate and read their MCP schemas. Use
`gh_knowledge_query` only when advisory component knowledge would materially help.

### Grasshopper Python and C# scripts

- Create a RhinoCode script component with `gh_create_script`, setting
  `language` to `python` or `csharp`.
- Use `gh_update_script` for ordinary source edits.
- When the component's inputs or outputs must change, call
  `gh_set_script_pins` before `gh_update_script`.
- Use `gh_set_script` when exact raw replacement or a legacy script component
  requires it.

These tools may be hidden by a compact profile; discover them with
`rook_tools_search`, inspect them with `rook_tools_read`, and invoke them with
`rook_tools_call`. After every script mutation, solve the definition and verify
source, pins, errors, warnings, and output data.

### Rhino geometry — inspect, then use explicit routes

Prefer typed routes such as `rhino_create`, `rhino_transform`, `rhino_boolean`,
`rhino_extrude`, `rhino_create_loft`, `rhino_create_sweep1`, and
`rhino_create_sweep2`. They provide bounded inputs and structured results.

When the operation is unfamiliar, inspect the document and discover the current
tool schema before choosing a route. If no typed route fits, use a sanctioned,
fully parameterized, non-interactive `rhino_command` after preflight, or a short
non-interactive `rhino_execute` script as the last resort. Verify the resulting
objects and geometry with the appropriate query tools.

### Other common needs

| Need | Tool |
|------|------|
| Query Rhino objects | `rhino_objects`, `rhino_geometry` |
| Inspect GH failures | `gh_errors` |
| Advisory knowledge | `knowledge_query`, `gh_knowledge_query` |
| Discover a tool | `rook_tools_search` |
| Read its schema | `rook_tools_read` |
| Invoke a discovered tool | `rook_tools_call` |

`/mcp` shows the tools advertised by the current profile; it is not necessarily
the complete admitted catalog.

### LLM-powered Grasshopper components — Chirp

Chirp components are Grasshopper nodes powered by language models. Use
`chirp_create` or the `/chirp` skill to create one. Available categories are
`planner`, `interpreter`, `critic`, `narrator`, `classifier`, `gate`, and
`editor`. Use `/chirp-cascade` when the user explicitly wants a multi-component
reasoning cascade.

Rook uses LiteLLM for model routing and can be configured for supported cloud or
local providers such as Anthropic, OpenAI, Ollama, and LM Studio. Provider and
model availability depends on the installed configuration and credentials;
never assume a particular model is available.

---

## Critical Rules

### Be persistent and honest

If the first tool choice does not work:

1. Inspect the returned error and current host state.
2. Re-read the tool schema and use progressive discovery for alternatives.
3. Query advisory knowledge when it is relevant to the failure.
4. Try another admitted, bounded path when evidence supports it.

Never invent a capability, claim unverified success, or silently expand the
requested scope. When completion genuinely requires a user action—such as
dismissing a modal dialog, selecting a target, saving user state, granting
authorization, or configuring credentials—explain the blocker and request only
that bounded action.

### Protect user state

Inspect before mutation. Operate only on the intended document or definition.
Do not delete, overwrite, close, or broadly clean user-owned state without clear
authorization. After mutation, verify the result; after a scratch test, restore
the declared observable pre-state.

### Use MCP tools, not direct HTTP

Do not use curl or direct HTTP calls to bypass Rook. MCP tools provide the
supported request, policy, and error-handling path.

### No keyboard automation

Do not use PowerShell SendKeys or `wscript.shell`. Keyboard automation is
unreliable, can target the wrong window, and may trigger security controls.

### Prefer typed routes over scripts

Typed routes validate structured inputs and return structured results. Use
`rhino_execute` or `rhino_command` only when a typed route does not fit and the
operation is short, non-interactive, preflighted, and verifiable. Stop if a
native dialog or unknown prompt blocks deterministic execution.

---

## Troubleshooting

### MCP tools not available

Run `/mcp` in Codex and look for `rook`. If it is missing, restart Codex from
the intended project directory and check the Rook MCP configuration.

### Rhino not responding

A modal dialog may be blocking Rhino. Ask the user to inspect and dismiss the
dialog, then retry `rhino_ping`. Do not use keyboard automation to dismiss it.

### Command creates zero objects

Inspect the structured error and verify coordinates, units, target document,
required options, and preconditions. Do not treat an empty result as success.

### Grasshopper component not found

Do not guess component names, GUIDs, or parameter layouts. Progressive discovery
searches Rook tools, not Grasshopper components. Use `gh_library` for exact
component identity and `gh_batch_component_info` for SDK-backed input/output
metadata. If those tools are hidden, locate and read them with
`rook_tools_search`/`rook_tools_read`. Then create the component by exact identity
and verify the solved graph with `gh_snapshot` and `gh_errors`.

### Still stuck?

File an issue at https://github.com/bringfire/rook-release/issues
