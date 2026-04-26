# GH Script-Component Routing + Language Disambiguation — Design Pass

**Date:** 2026-04-21
**Stage:** design pass (memo locked; ready for PR-1 scope pass when promoted)
**Basis:**
- Live agent failure 2026-04-21 (chat transcript) — agent pivoted to `rhino_execute` reflection workaround while trying to read a C# Script component's source
- Codex pre-implementation review 2026-04-21 — identified the incident as cross-surface contract mismatch, not description drift
- Claude synthesis 2026-04-21 — confirmed surface inventory + proposed scope-pass checklist addition

**Trigger:** already fired. This is not a hypothetical — a live agent failure routed around the correct tool and reached a genuine dead-end, exactly as the `gh_set_script` description's *"prefer this over rhino_execute workarounds"* sentence was written to prevent.

---

## TL;DR

The 2026-04-21 incident was initially triaged as a narrow "`gh_set_script` MCP description drift" item. **It is not.** The incident exposed a cross-surface contract mismatch affecting seven agent-facing surfaces that tell four inconsistent stories about script-component routing. The correct fix is a design pass across MCP descriptions, persona prompts, tool-catalog ownership claims, and knowledge-store metadata — executed as a 3-PR campaign, not a one-line doc cleanup.

**What Phase 3's PR-2 kill and this item share structurally:** both are "capability metadata drifting" cases where the agent-facing secondary surface evolved independently of the primary surface (handler / RhinoCommon API). Phase 3 PR-2's `AlignWithSurface` was killed by API surface auditing at implementation time; this item is the analogous catch at agent-contract time.

---

## The Incident (2026-04-21)

**Context:** Agent working in a live Grasshopper session needed to read a C# Script component's source code.

**Decision chain the agent followed:**

1. Read [`gh_set_script`'s MCP description](../Rook/mcp_server/src/rook/server.py#L6381-L6389) — three categorical claims that the tool is **only for Python 3 Script components**.
2. Concluded the tool doesn't apply to the C# case in front of it.
3. Reached for [`rhino_execute`](../Rook/mcp_server/src/rook/server.py) reflection as a fallback — exactly the path the description's *"prefer this over rhino_execute workarounds"* sentence was written to prevent.
4. `rhino_execute` is the **wrong substrate** for GH script work. It runs arbitrary Python via Rhino's `_-RunPythonScript` wrapper in-process (see [`CommandHandler.cpp:269-328`](../Rook/src/RookNative/Handlers/CommandHandler.cpp#L269-L328)), so it CAN technically reach GH via `Grasshopper` namespace imports — but the access is unsupported, brittle, unstructured (raw stdout, no typed response envelope), has no atomic rollback or structured error codes, and bypasses the duck-typed capability surface `gh_set_script` already provides. Using `rhino_execute` for GH script source/pin work is a policy violation, not a hard impossibility. **The result is a brittle workaround, not a dead-end.**

**What the agent should have done** (and what the tool would have handled correctly):
- Called `gh_set_script(guid=<c#_script_guid>)` — no `script` arg to trigger the read path
- Handler at [`GrasshopperHandler.cs:607-619`](../Rook/src/Rook/Handlers/GrasshopperHandler.cs#L607-L619) is duck-typed: accepts any component with `SetSource(string)` / `TryGetSource` methods (RhinoCode family) OR a `ScriptSource` property with `ScriptCode` sub-property (GH1 legacy). Python3Component, GhPythonComponent, CSharpScriptComponent, Component_CSNET_Script all satisfy.
- Returns `{Guid, Type, Action: "get", Script, ScriptLength}` — exactly what the agent needed.

**Why the fallback isn't a rescue:** the agent-visible contract (MCP description) was the only signal the agent used to decide. When categorical MUST-language in a description is wrong, the description doesn't just fail to help — it **actively routes the agent to a wrong escape hatch**.

---

## Structural Diagnosis: Seven Surfaces, Four Inconsistent Stories

The incident exposed that script-component routing is declared on seven agent-facing surfaces, each with independent evolution:

| # | Surface | Current claim | Reality |
|---|---------|---------------|---------|
| 1 | `gh_set_script` MCP description ([server.py:6381-6389](../Rook/mcp_server/src/rook/server.py#L6381-L6389)) | "Python 3 Script component" / "must be a Py3 component" / "Python source code" — **three categorical Py3-only claims** | Handler duck-types 4+ component types; Py3 gate is false |
| 2 | `gh_execute_intent` MCP description ([server.py:8142](../Rook/mcp_server/src/rook/server.py#L8142)) | *"This is the ONLY tool for creating GH components. All component creation MUST go through this tool."* | False. `gh_create_python_script` and `gh_create_csharp_script` are dedicated creation tools. AND `gh_execute_intent` is excluded from worker mode's preload per [tool_groups.py:37](../Rook/mcp_server/src/rook/agent/tool_groups.py#L37) — so the "ONLY tool" claim is inert in the mode where it's most likely to mislead. |
| 3 | `gh_create_python_script` MCP description ([server.py:6401](../Rook/mcp_server/src/rook/server.py#L6401)) | Creates Py3 component | Correct — but see #2, catalog says it doesn't exist as a creation path |
| 4 | `gh_create_csharp_script` MCP description ([server.py:6442](../Rook/mcp_server/src/rook/server.py#L6442)) | Creates C# RhinoCode component | Correct — but same contradiction as #3 |
| 5 | `WORKER.md` preloaded-tools list ([WORKER.md:13](../Rook/mcp_server/src/rook/agent/prompts/WORKER.md#L13)) | "`gh_set_script` — set Python 3 script source" | Replicates #1's Py3 lie at the persona layer. Does not mention `gh_create_python_script` / `gh_create_csharp_script` despite both being preloaded in `gh_canvas` per [tool_groups.py:289](../Rook/mcp_server/src/rook/agent/tool_groups.py#L289). |
| 6 | `scripter/role.md` ([role.md:1-7](../Rook/mcp_server/src/rook/agent/personas/scripter/role.md#L1-L7)) | Step 1: create via `gh_edit` with `{"component": "Python 3 Script"}` | Teaches a name-based creation path that [server.py:12092](../Rook/mcp_server/src/rook/server.py#L12092) warns can resolve to the legacy component. Bypasses both `gh_execute_intent` AND the dedicated create tools. 100% Python-shaped — the scripting specialist persona has no C# branch. |
| 7 | `tool_groups.py` worker preload ([tool_groups.py:37](../Rook/mcp_server/src/rook/agent/tool_groups.py#L37)) | Excludes `gh_execute_intent` | Directly contradicts #2's "ONLY tool" claim. Worker mode operates entirely through `gh_canvas` tools, which IS where the dedicated script-creation tools live ([tool_groups.py:289](../Rook/mcp_server/src/rook/agent/tool_groups.py#L289)) — but the persona (#6) never mentions them. |
| — | `GrasshopperHandler.cs::SetScript` (the actual handler at [:564-619](../Rook/src/Rook/Handlers/GrasshopperHandler.cs#L564-L619)) | **Duck-typed** on capability — accepts any component implementing RhinoCode (`SetSource` / `TryGetSource`) or GH1 legacy (`ScriptSource` property) patterns | Ground truth. Broader than the C# XML docstring's 4-type enumeration. |

**Four inconsistent mental models** an agent could build from these surfaces:
- From #1 + #5: "Script setting is Py3-only."
- From #2: "Creation goes through intent, never dedicated tools."
- From #3 + #4: "Creation goes through dedicated tools by language."
- From #6: "Creation goes through `gh_edit` with component-name strings."

Any one of them will misroute the agent. #1 is the one that fired in the 2026-04-21 incident; the others are dormant traps.

---

## Why This Isn't a Description Fix

Codex's reframe: *"The real issue is script-component routing discipline across MCP language, prompts, and tool ownership."*

Three reasons the narrow fix fails:

1. **Persona prompts (#5, #6) are read BEFORE tool descriptions.** An agent's mental model is shaped by WORKER.md and its role persona before it consults tool descriptions during task execution. Fixing #1 while leaving #5 and #6 unfixed still leaves the agent with the wrong initial framing.

2. **Catalog contradictions (#2 vs #3/#4/#7) are their own failure mode.** The agent cannot coherently reconcile "`gh_execute_intent` is the ONLY tool for creating GH components" with "these dedicated create tools also exist AND are the only ones preloaded in worker mode." Whichever claim it trusts, the other lies.

3. **Script components are operationally special** per [server.py:12092](../Rook/mcp_server/src/rook/server.py#L12092)'s warning about name-based resolution hitting legacy components. The dedicated tools create-by-GUID, set-pins, inject-code, and check-errors in one transaction ([server.py:11796](../Rook/mcp_server/src/rook/server.py#L11796) and [:11911](../Rook/mcp_server/src/rook/server.py#L11911)). Generic library/name-based creation (which #6's persona teaches) **is unsafe**. The script-component specialness is load-bearing, not cosmetic — and neither the prompts nor the catalog reflect that it exists.

---

## Policy Proposal

### Ownership Boundaries

The missing explicit rule set, promoted to durable policy:

- **`gh_execute_intent`** owns **generic component graphs** — components that compose into wiring diagrams without special creation semantics. Does NOT own script components.
- **`gh_create_python_script` / `gh_create_csharp_script`** (or a unified successor — see §Structural Surface below) own **programmable components**. These are the ONLY safe creation path for script components, because they create-by-fixed-GUID and avoid the name-collision trap at [server.py:12092](../Rook/mcp_server/src/rook/server.py#L12092).
- **`gh_set_script`** owns **reading and setting source on any script component** — duck-typed on capability (RhinoCode `SetSource`/`TryGetSource` family; GH1 `ScriptSource` family). Not Python-scoped.
- **`rhino_execute`** is **never a fallback for GH script source/pin work.** It runs arbitrary Python via Rhino's `_-RunPythonScript` wrapper in-process ([`CommandHandler.cpp:269-328`](../Rook/src/RookNative/Handlers/CommandHandler.cpp#L269-L328)); technically it CAN import `Grasshopper` and manipulate GH state, but the access is unsupported, brittle, unstructured (raw stdout / ObjectDiffTracker, not a typed response envelope), has no atomic rollback, and sidesteps the duck-typed capability detection `gh_set_script` already implements. Policy violation, not impossibility — but the policy exists because the workaround consistently produces worse outcomes than the dedicated tool. This must become an explicit rule in the persona prompts AND referenced in the `gh_set_script` description so the agent sees it on both surfaces.

### Language Disambiguation Policy

For creation of a new script component:

1. **If the user says "Python" or provides Python syntax** → `gh_create_python_script`.
2. **If the user says "C#" / "RhinoCode C#" or provides C# syntax** → `gh_create_csharp_script`.
3. **If the user says only "script component" AND syntax is not decisive** → ask the user, OR fail with a structured ambiguity message pointing at the two options. Do NOT default silently.
4. **When editing an existing script component** → inspect the component type via `gh_snapshot` / `gh_component` and do not ask. The language is already decided.

Rule 4 is important: the language-choice question only applies to creation. `gh_set_script` on an existing component should NEVER ask about language — the component's type determines it.

### When `gh_execute_intent` Must Hand Off

`gh_execute_intent` currently claims exclusive ownership of GH creation. The handoff rule: when the resolved intent would create a script component (by knowledge-store tag or by component-GUID match against the known script component set), `gh_execute_intent` must either:
- Refuse the intent with a pointer to the dedicated tools, OR
- Internally dispatch to the dedicated creation tool.

Either option ends the silent misrouting. The §Knowledge / Router Hooks section below describes the tagging needed to make this detection reliable.

---

## Structural Surface: Unified `gh_create_script`

**Problem with two sibling tools:** every agent decision about script creation is "Python or C#?" — a language axis. Having two separate tools embeds that axis in the tool-name space, which means:
- Agent has to load BOTH tools to cover the decision
- The decision is replicated across every planning surface
- Catalog descriptions for the two tools are almost-identical boilerplate that drifts independently

**Proposed end-state:** unified `gh_create_script(language="python"|"csharp", ...)`. Single tool, single decision axis, single description.

- Keep `gh_create_python_script` and `gh_create_csharp_script` as **aliases** to preserve existing agent knowledge and avoid churn in the persona prompts until they're ready for re-teaching.
- Unified tool's description says *explicitly* that `language` is required — no default — so the disambiguation policy is enforced at the API boundary, not just in persona prompts.
- If `language` is omitted, return a structured error naming the two choices. No silent fallback.

This matches the Phase 2 precedent for `/curve/boolean`, where three intent keys (union/difference/intersection) collapsed to one endpoint with an `operation` discriminator. Same pattern: collapse sibling-tool decision axes onto a discriminator param.

---

## Knowledge / Router Hooks

For `gh_execute_intent`'s handoff rule (§Ownership Boundaries) to work, the knowledge store needs to tag script components as special-creation-path.

### Tagging — split `editableBy` from `creationTool`

Two distinct metadata axes that the original memo draft conflated:

- **`editableBy` / `scriptLanguage` / `scriptRuntime`** — who CAN read/write source via `gh_set_script`. Broad set; covers all 4 component types because the handler duck-types on capability (RhinoCode `SetSource`/`TryGetSource` family OR GH1 `ScriptSource` property family).
- **`creationTool`** — who CAN instantiate this component type via a modern dedicated tool. Narrow set; only the 2 RhinoCode GUIDs at [`server.py:11816`](../Rook/mcp_server/src/rook/server.py#L11816) (`PY3_GUID = "719467e6-7cf5-4848-99b0-c5dd57e5442c"`) and [`:11931`](../Rook/mcp_server/src/rook/server.py#L11931) (`CS3_GUID = "b6ba1144-02d6-4a2d-b53c-ec62e290eeb7"`). The GH1 legacy component types (`GhPythonComponent`, `Component_CSNET_Script`) are **NOT** created by the dedicated tools — the tools only instantiate RhinoCode components by fixed GUID.

This split echoes existing precedent at [`gh_knowledge.py:1356-1357`](../Rook/mcp_server/src/rook/learning/gh_knowledge.py#L1356), which explicitly treats proxy GUID as the canonical creation identity for `GhPythonComponent` — already separated from the "can this be edited" question.

| Component type | `scriptLanguage` | `scriptRuntime` | `editableBy` (via `gh_set_script`) | `creationTool` |
|---|---|---|---|---|
| `Python3Component` | `python` | `rhinocode` | ✓ (SetSource/TryGetSource) | `gh_create_python_script` (via `PY3_GUID`) |
| `GhPythonComponent` | `python` | `gh1` | ✓ (ScriptSource property) | **none** — GH1 legacy, not created by modern tools. `gh_knowledge.py:1356-1357` treats proxy GUID as canonical creation identity here; modern creation is a distinct path not covered by this campaign. |
| `CSharpScriptComponent` | `csharp` | `rhinocode` | ✓ (SetSource/TryGetSource) | `gh_create_csharp_script` (via `CS3_GUID`) |
| `Component_CSNET_Script` | `csharp` | `gh1` | ✓ (ScriptSource property) | **none** — GH1 legacy, not created by modern tools. Same reasoning as GhPythonComponent row. |

**Practical consequence:** a user intent like *"create a C#/NET legacy script"* (if anyone actually types this) should be refused by `gh_execute_intent` with a message noting no dedicated creation tool exists for that type — the user would need the GhPython/proxy-GUID path or `gh_execute_intent`'s non-script generic create. The PR-3 handoff check keys on `creationTool` presence, so GH1 legacy components won't trigger a false handoff.

### Router check

`gh_execute_intent`'s pipeline is **separate** from the Rhino typed-route intent runtime. It resolves through [`GHIntentResolver`](../Rook/mcp_server/src/rook/learning/dspy_modules.py) (DSPy module) invoked directly from [`server.py:14724`](../Rook/mcp_server/src/rook/server.py#L14724) — NOT through `CapabilityRouter` in `intent_runtime.py` (which is the Rhino side, what Phase 1/2 hardened).

The handoff check belongs in `GHIntentResolver` (or in the `gh_execute_intent` case-arm at `server.py:14724` that invokes it), before the resolved component is dispatched to `/gh/create-component`. Check the resolved component's `creationTool` metadata: if set, the resolver must either (a) refuse and return a structured `handoff_required` error naming the dedicated tool, or (b) internally dispatch to the unified `gh_create_script` (or the appropriate alias). No changes to Rhino-side `CapabilityRouter` or `intent_runtime.py` — wrong surface.

This lives alongside the `special_creation_tool` marker Codex proposes. Same concept, concrete shape, on the GH intent pipeline specifically.

---

## Execution Shape — 3-PR Campaign

### PR-1 — Contract Hygiene

**Scope:** the agent-facing surface fixes. No behavior change in any handler.

**Changes:**

**This section is the authoritative PR-1 scope** — updated 2026-04-21 post-Codex-scope-review to incorporate four corrections: (a) `gh_execute_intent` description stays current-state only (no forward-anchoring of PR-3's `handoff_required` behavior); (b) runtime-source-of-truth for worker prompt is `personas/worker/role.md`, not `prompts/WORKER.md` (the latter is a display snapshot, not consumed at runtime — `prompt_builder.py:63-67` builds from `personas/<name>/role.md` via `load_persona()`); (c) `personas/architect/role.md` has the same Py3 drift on two sites and is in scope for the "contract hygiene across agent-facing surfaces" framing; (d) mock-based handler-duck-typing tests do not belong at the Python layer (tool_dispatcher just forwards to `/gh/script`; Python never inspects component type) — replaced with a parameterized persona-prompt regression test that covers the runtime surface PR-1 actually modifies.

### Changes (6 source files + 3 tests)

**Change 1 — [`mcp_server/src/rook/server.py:6381-6389`](../Rook/mcp_server/src/rook/server.py#L6381) — `gh_set_script` description rewrite**

Replace entirely with:
```
Set or read the source code on a Grasshopper script component.

To SET: pass guid + script (the source code — Python, C#, or GH1-legacy syntax
depending on the target component's runtime).
To GET: pass only guid (omit script).

Accepts any script component: RhinoCode Python 3 Script, RhinoCode C# Script,
GH1-legacy GhPython, GH1-legacy C#/.NET Script. The handler duck-types on
capability (SetSource/TryGetSource for RhinoCode, ScriptSource property for
GH1-legacy) — language is inferred from the component's type, not claimed
by the caller.

After setting, automatically triggers ExpireSolution so outputs recompute.

Prefer this over `rhino_execute` for ALL GH script source/pin work.
`rhino_execute` runs Python via RhinoCode's RunPythonScript in-process —
it can technically reach GH via Grasshopper namespace imports, but the
result is unstructured, unsupported, and bypasses the capability detection
this tool provides. This tool is the correct substrate.
```

**Change 2 — [`server.py:8142`](../Rook/mcp_server/src/rook/server.py#L8142) — `gh_execute_intent` description rewrite (CURRENT-STATE ONLY)**

Replace entirely with (current-state guidance only — NO forward-anchoring of PR-3's `handoff_required`):
```
Execute a Grasshopper intent - create and wire generic component graphs.

Owns generic component creation (sliders, math, geometry primitives, data
manipulation, etc.). Does NOT own script components — programmable
components (Python, C#) belong to `gh_create_python_script` /
`gh_create_csharp_script`, which create by fixed component GUID and invoke
a transactional create/set-pins/inject-code/check-errors pipeline that
this intent tool cannot replicate safely.

For script-component work, call the dedicated create tools directly —
do not route through this tool.

It automatically:
1. Queries the knowledge system for matching components (with gotchas and correct GUIDs)
2. Creates components using learned knowledge
3. Returns warnings about known pitfalls

Availability: excluded from worker-mode preload per tool_groups.py — worker
agents should compose via `gh_canvas` tools, which includes the dedicated
script creation tools.
```

**Change 3 — [`personas/worker/role.md:25`](../Rook/mcp_server/src/rook/agent/personas/worker/role.md#L25) — runtime worker prompt (PRIMARY)**

Current drift line: `` - `gh_set_script` -- set Python 3 script source ``

Replace with an expanded Canvas Management block that includes the dedicated create-script tools (preloaded via `gh_canvas` per [`tool_groups.py:289`](../Rook/mcp_server/src/rook/agent/tool_groups.py#L289) but currently unmentioned):

```markdown
### Canvas Management
- `gh_set_script` -- set/get source on any GH script component (Python 3, C#, or GH1-legacy — duck-typed on capability)
- `gh_create_python_script` -- create a Python 3 Script component with pins + code in one transaction
- `gh_create_csharp_script` -- create a RhinoCode C# Script component with pins + code in one transaction
- `gh_move` -- reposition components
- `gh_canvas_cleanup` -- auto-layout components
- `gh_clear` -- clear the canvas
```

**Change 4 — [`prompts/WORKER.md:13`](../Rook/mcp_server/src/rook/agent/prompts/WORKER.md#L13) — display snapshot (SECONDARY, consistency-only)**

Mirror the Change 3 edits in the display snapshot. Not load-bearing at runtime, but keeps greps/casual reads honest.

**Change 5 — [`personas/architect/role.md`](../Rook/mcp_server/src/rook/agent/personas/architect/role.md) — TWO drift sites**

- **[:25](../Rook/mcp_server/src/rook/agent/personas/architect/role.md#L25)** — identical preloaded-tools drift line; apply the same 3-tool rewrite as Change 3.
- **[:89](../Rook/mcp_server/src/rook/agent/personas/architect/role.md#L89)** — second drift site in tool-usage guidance: current text `"Script components: Use gh_set_script to set Python 3 code, not gh_edit set_values"`. Replace with: `"Script components: Use gh_set_script to set/get source on any script-component type (Python 3, C#, GH1-legacy); use gh_create_python_script / gh_create_csharp_script for creation — NOT gh_edit with component-name strings."`
- The existing correct rule at [:90](../Rook/mcp_server/src/rook/agent/personas/architect/role.md#L90) (`"Do NOT use rhino_execute for GH operations -- always use the gh_* tools"`) stays unchanged.

**Change 6 — [`personas/scripter/role.md`](../Rook/mcp_server/src/rook/agent/personas/scripter/role.md) — full rewrite**

Current role is 100% Python-shaped and teaches the dangerous `gh_edit`-with-component-name creation path. Rewrite structure:

```markdown
## Your Task

You write scripts for Grasshopper script components — either Python 3 or C#.

## Language Decision (do this first)

1. If the user says **Python** or provides Python syntax → use `gh_create_python_script`
2. If the user says **C#** / **RhinoCode C#** or provides C# syntax → use `gh_create_csharp_script`
3. If the user says only "script component" AND syntax is not decisive → **ask**, or fail with a structured message naming both options. Do NOT default silently.
4. When editing an **existing** component → inspect its type via `gh_snapshot`; the language is already decided. Don't ask.

## Workflow

### Creating a new script component
1. Pick the language per the decision above.
2. Call `gh_create_python_script(code, pins_in, pins_out, ...)` or `gh_create_csharp_script(code, pins_in, pins_out, ...)`.
   These create the component by fixed GUID, configure pins, inject the script, and check errors in one transaction.
   **Do NOT** use `gh_edit` with `{"component": "Python 3 Script"}` — that's a name-lookup path that can resolve to a legacy component (see server.py:12092 warning).
3. Wire inputs: use `gh_edit` to connect sliders/panels via flow strings like `C5.O0>C3.I0`.
4. Verify: `gh_errors` + `gh_inspect_output`.

### Editing an existing script component
1. Read current source: `gh_set_script(guid)` — omit `script` arg to trigger the read path. Works on ALL 4 script-component types (Python 3, C#, GhPython, CSNET).
2. Set new source: `gh_set_script(guid, script)` with the new code.
3. Edit pins: `gh_set_script_pins(guid, ...)`.
4. Verify: `gh_errors`.

## Forbidden Paths

- **`rhino_execute` is NEVER a fallback for GH script source/pin work.** It runs Python via Rhino's RunPythonScript in-process; technically it can import `Grasshopper` and manipulate GH state, but the result is unstructured, unsupported, and bypasses the capability detection `gh_set_script` provides. If `gh_set_script` doesn't seem to apply, read its description carefully — it accepts all 4 script component types via duck-typed capability detection, not just Python 3.
- **`gh_edit` with component-name strings for script components** — name lookup can resolve to legacy components. Use `gh_create_python_script` or `gh_create_csharp_script` instead.

## Script Component Patterns

### Python 3 — Imports
[preserve existing Python patterns from the current role.md — imports, DataTree output convention, etc.]

### C# — Boilerplate
[new section — document RunScript signature, object params enforcement, Script_Instance wrapper]
```

### Tests (3 total — two MCP-description regressions + one parameterized persona-prompt regression)

**Test 1 — `test_gh_set_script_description_does_not_claim_py3_only`** (in `mcp_server/tests/test_server_contract_hardening.py`)

Reads the registered `gh_set_script` tool description via `server.list_tools()`. Asserts absence of the drift strings:
- `"must be a Python 3 Script"` absent
- `"the full Python source code"` absent

**Test 2 — `test_gh_execute_intent_description_does_not_claim_only_tool`** (same file)

Asserts absence on `gh_execute_intent` description:
- `"This is the ONLY tool for creating GH components"` absent
- `"All component creation MUST go through this tool"` absent

**Test 3 — `test_persona_prompt_script_tool_language_is_capability_accurate`** (in `mcp_server/tests/test_chat_prompt_builder.py`, parameterized over `["worker", "architect", "scripter"]`)

This is the critical test for covering the runtime-prompt surface. Without it, the three `role.md` files have no CI signal against drift recurrence.

```python
import pytest
from rook.agent.chat.prompt_builder import PromptBuilder


@pytest.mark.parametrize("persona", ["worker", "architect", "scripter"])
def test_persona_prompt_script_tool_language_is_capability_accurate(persona):
    """Regression anchor per 2026-04-21 gh-script-component-routing design pass.

    Persona prompts build the live runtime system prompt (not the snapshot
    at prompts/WORKER.md). These three personas all touch GH scripting
    workflows — their prompts must not advertise gh_set_script as Py3-only
    (the drift that misrouted an agent to rhino_execute on 2026-04-21),
    and must name the dedicated script-creation tools which are preloaded
    via the gh_canvas group per tool_groups.py:289.

    See rook_docs/2026-04-21-gh-script-component-routing-design-pass.md.
    """
    builder = PromptBuilder()
    prompt = builder.build_system(persona)

    # Old Py3-only drift strings must not reappear on any of the three personas.
    assert "set Python 3 script source" not in prompt, (
        f"{persona}: Py3-only preloaded-tools drift — see design-pass memo"
    )
    assert "to set Python 3 code" not in prompt, (
        f"{persona}: Py3-only tool-usage guidance drift (architect:89 site today)"
    )

    # Dedicated script-creation tools must appear in the persona prompt.
    # They're preloaded in the gh_canvas group — absent mention is the same
    # class of drift that caused the 2026-04-21 incident.
    assert "gh_create_python_script" in prompt, (
        f"{persona}: missing gh_create_python_script; preloaded in gh_canvas "
        "but not mentioned in persona prompt"
    )
    assert "gh_create_csharp_script" in prompt, (
        f"{persona}: missing gh_create_csharp_script"
    )
```

### Git workflow

- Branch: `fix/gh-script-routing-pr1-contract-hygiene`
- Single commit
- PR title: `fix(gh): contract hygiene for script-component routing (design-pass PR-1)`
- Squash-merge per `feedback_pr_workflow`

### Acceptance gate (PR-1 opens after)

1. Six source rewrites per §Changes 1-6 (the 7th is the WORKER.md snapshot — display only; optional but included for consistency).
2. Three regression tests green (2 MCP-description + 1 parameterized persona-prompt = 3 test functions, 3 + 3 parameterized = 6 test cases).
3. Existing `test_server_contract_hardening.py` regression green (unchanged — no handler touch).
4. Existing `test_chat_prompt_builder.py` green (4 pre-existing tests unchanged).
5. Existing `test_intent_runtime.py` 45/45 regression green.
6. **Scope containment check:** `git diff --stat` of `src/Rook/**` and `src/RookNative/**` → empty (no handler change), no MCP schema change, no new route.

### Non-scope for PR-1 (explicit)

- **Unified `gh_create_script` tool** — PR-2.
- **`GHIntentResolver` handoff + knowledge-store metadata tags** — PR-3. PR-1's `gh_execute_intent` description describes current-state only; PR-3 adds the enforcement.
- **Handler-side duck-typing tests** — C# territory; the Python layer just forwards. Live coverage already exists via PRs #78-#81's script-pin suites on RhinoCode Python/C# types.
- **Other personas beyond worker / architect / scripter** — implementation-time grep will surface any additional drift sites; if the parametrize list needs extending, extend it. If grep is empty, done. No new source-code scope.
- **Live-Rhino regression test reproducing the 2026-04-21 scenario** — deferred to post-PR-3 when the handoff is complete; PR-1's text-anchored tests are the contract floor.

### Risk assessment

**Low-M.** Pure agent-facing surface; no handler behavior change. Four description/persona rewrites plus the parameterized test. The scripter/role.md full rewrite is the largest change by line-count but lowest risk-per-line (it's a specialist persona that had no C# coverage at all — more replacement than modification).

The real risk class is agent-behavior regression — hard to test without a reproducible agent harness. Mitigations:
1. Three regression tests anchor the text surfaces forward.
2. PR commit message documents the before/after decision chain so post-merge behavior anomalies on this surface can be traced against intent.

### PR-2 — Structural API Cleanup

**Scope:** introduce the unified `gh_create_script` tool.

**Changes:**

1. New MCP tool `gh_create_script(language, code, pins_in, pins_out, name, ...)` with `language: "python" | "csharp"` **required** — no default.
2. Existing `gh_create_python_script` / `gh_create_csharp_script` become aliases: they accept the same payload, internally set `language` and route to the new unified path. Descriptions updated to say "Convenience alias for `gh_create_script(language=...)`"; both tools remain callable for back-compat until persona prompts are fully re-taught.
3. Ambiguity: if `language` omitted or invalid on the unified tool, return structured `invalid_input` with message naming the two valid choices.
4. Normalize script-metadata on read surfaces (`gh_snapshot` / `gh_component`) to expose `scriptLanguage` / `scriptRuntime` fields derived from the component's typeName — so callers can inspect an existing component to decide edit-time routing without ambiguity.
5. Persona prompts (`scripter/role.md`) re-taught to prefer `gh_create_script` over the aliases.

**Risk:** M. Additive API surface + metadata normalization on read surfaces. Live test coverage: parallel to existing `gh_create_python_script` / `gh_create_csharp_script` live tests, routed through the unified tool.

### PR-3 — Planner / Knowledge Handoff

**Scope:** close the loop so `gh_execute_intent` doesn't silently instantiate script components via the wrong path.

**Changes:**

1. Knowledge-store metadata additions per §Knowledge / Router Hooks — tag all four script component types with `editableBy` / `scriptLanguage` / `scriptRuntime`, but ONLY the two RhinoCode types (`Python3Component`, `CSharpScriptComponent`) with `creationTool`. GH1 legacy types get no `creationTool` because the modern dedicated tools don't instantiate them (see §Tagging table).
2. Handoff check inside `GHIntentResolver` ([`mcp_server/src/rook/learning/dspy_modules.py`](../Rook/mcp_server/src/rook/learning/dspy_modules.py)) or equivalently in the `gh_execute_intent` case-arm at [`server.py:14724`](../Rook/mcp_server/src/rook/server.py#L14724) that invokes it — **NOT in `intent_runtime.py` or `CapabilityRouter`**, which are the Rhino-side typed-route machinery and don't see GH intents. Before resolving a create step, check the candidate component's `creationTool` metadata. If set, return structured `handoff_required` with the dedicated tool name, OR internally dispatch to the unified `gh_create_script`.
3. `GHWiringExecutor` (sibling DSPy module invoked alongside the resolver) must respect the handoff — if the plan includes a script-component creation step that bypasses the dedicated tool, the executor must refuse rather than fall through to generic `/gh/create-component` by GUID/name.
4. Tests: a scripted intent like `"create a python script that does X"` must land on `gh_create_python_script` (or `gh_create_script(language="python")`), not generic `gh_execute_intent` → `/gh/create-component` → RhinoCode-specific GUID path that skips the preamble/pin/error pipeline the dedicated tools provide.

**Risk:** M. Touches the GH DSPy pipeline (`GHIntentResolver` / `GHWiringExecutor`) — a different architectural surface than Phase 1/2's typed-route CapabilityRouter work. Testing pattern: mockable at the DSPy-module boundary (input: intent text → output: resolved plan); live-Rhino coverage via existing `gh_execute_intent` tests extended with the new handoff cases. Does NOT inherit Phase 1/2's `test_capability_router_phase*_coverage.py` pattern because the GH intent pipeline isn't covered by those tests.

---

## Scope-Pass Checklist Addition

Lands in `feedback_pr_scoping_rhythm.md` memory (or the equivalent project convention doc) — applies to all future PRs:

> **When a PR changes a handler's acceptance set** (adding types, broadening capability detection, changing duck-typed checks, adding a new component-type branch), audit FOUR surfaces for drift:
> 1. The MCP tool description in `server.py`
> 2. Any persona prompts that reference the tool (`mcp_server/src/rook/agent/prompts/*.md`, `mcp_server/src/rook/agent/personas/**/*.md`)
> 3. Tool-catalog claims that might now be false (e.g., "ONLY tool for X" / "MUST go through X" language elsewhere)
> 4. Knowledge-store hints about the affected component types / routes
>
> This is in addition to the existing "description matches handler" check. The 2026-04-21 incident demonstrated that fixing the MCP description alone is insufficient when persona prompts and tool-catalog contradictions reinforce the wrong model.

---

## Non-Goals / Explicit Parks

1. **Consolidating Python3Component vs GhPythonComponent handling** — `GrasshopperHandler.cs::SetScript` duck-types both; callers should not need to care which runtime a specific component uses. No change proposed. Future Rhino version changes might consolidate or split these types; handler adapts via reflection either way.

2. **Refactoring `rhino_execute` to reject GH-scoped payloads** — tempting (make the category error unrepresentable), but `rhino_execute` is legitimately used for non-GH Rhino scripting. A runtime check that "this script talks about GH" is brittle heuristic territory. The policy goes in the persona prompts + tool descriptions instead (at the agent decision layer, not the execution layer).

3. **A description-from-handler-capability build-time emitter** — originally proposed in Claude's analysis as an architectural end-state that eliminates drift by construction. Deferred: the unified `gh_create_script` approach (PR-2) solves a different and bigger problem (single decision axis, not just drift prevention). If, after this campaign, we see another description-drift incident on a different tool, revisit the emitter idea with fresh data.

4. **Auditing the `/rhino/*` tool family for similar drift** — 200+ tools. Claude's spot-check for hard-gate language ("must be", "only works with", etc.) surfaced mostly legitimate constraints (e.g., "must be a closed solid" for boolean ops — genuinely correct). A full audit is low-value if a spot-check finds no drift; deferred unless a `/rhino/*` tool surfaces its own incident.

5. **Changing `gh_execute_intent`'s scope for non-script GH creation** — out of this campaign. The intent-runtime's behavior for generic component graphs stays. Only the script-component handoff is added.

---

## Campaign Exit Criteria

Campaign completes when:

1. Four cross-surface inconsistencies (§Structural Diagnosis table) are all resolved:
   - Surface #1 (`gh_set_script` description): Py3 gate removed, capability-based description in place.
   - Surface #2 (`gh_execute_intent` description): "ONLY tool" claim removed, script-component handoff documented.
   - Surface #5 (`WORKER.md`): accurate preloaded-tool list including dedicated script-creation tools.
   - Surface #6 (`scripter/role.md`): dedicated-tool path taught, language disambiguation policy documented, `rhino_execute` explicitly forbidden for GH script work.
2. Unified `gh_create_script` shipped with language-required policy; existing tools aliased.
3. Knowledge-store metadata tags the 4 script-component types; router hands off correctly on script-creation intents.
4. Scope-pass checklist item landed in project memory.
5. Regression floor: the 2026-04-21 incident scenario (agent needs to read a C# script's source) must now resolve via `gh_set_script` with no fallback attempt. This is a behavioral test — would need a live reproduction or a carefully-crafted prompt harness to validate.

---

## Methodology Lessons Captured

Two lessons worth folding into durable memory beyond this specific campaign:

1. **Capability metadata drifts across secondary surfaces** — this is the same structural mechanism as HTTP_MAPPINGS drift (explorer registry), CATEGORIES / BRIDGE_ROUTES / TOOL_CATEGORIES per-PR backfill churn, and now script-routing surfaces. Primary surface (handler code) evolves; secondary surfaces are maintained by-hand and drift. The scope-pass checklist addition (above) is the lightweight preventive; the unified-tool pattern (PR-2) is the architectural one — collapse sibling surfaces onto a single discriminator.

2. **Categorical MUST-language in a description actively misroutes** — when the gate is correct, MUST is informative. When it's wrong, MUST transforms the description from "help the agent choose" into "route the agent AWAY from the correct tool." Description audits for drift should specifically hunt for MUST / ONLY / exclusively language — the hedged alternatives (TYPICALLY, ACCEPTS, PREFERS) fail safer when they drift. Consider this a pattern when writing new tool descriptions: hedge the gate unless you're certain the gate is binary AND won't expand.

Both lessons extend naturally from the methodology note in `rook_docs/2026-04-21-typed-route-phase3-spike.md` §Post-Hoc Finding: *API-surface-reflection audits should run at spike time, not implementation time.* That lesson was about RhinoCommon API surfaces; these two lessons extend it to agent-facing contract surfaces. Same principle, different surface class.
