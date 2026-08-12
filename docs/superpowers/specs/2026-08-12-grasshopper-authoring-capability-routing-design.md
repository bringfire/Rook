# Grasshopper Authoring Capability Routing

**Status:** Approved production design
**Baseline:** `ad4d3b2798ab38b2245d7d9d12fdadd344b16de5`
**Scope:** Model-facing component creation only

## Objective

Make the authoring route match the requested capability before Grasshopper is
mutated:

```text
ordinary composition
-> gh_edit

custom computation, source, or caller-declared pins
-> gh_create_script

existing script correction
-> gh_update_script / gh_set_script_pins

Chirp generation
-> chirp_create
```

If an ordinary model-facing route selects either supported modern RhinoCode
script component, it must return a structured handoff to `gh_create_script`
before target mutation. It must not create a default script component, retry,
redispatch, or guess code and pins.

## Ownership Boundary

```text
model-facing authoring API
-> classify the requested component identity
-> enforce the authoring-route policy
-> dispatch an admitted request

internal /gh/create-component
-> capability-neutral host primitive
```

Raw `/gh/create-component` remains unchanged. It cannot distinguish an unsafe
ordinary creation from `gh_create_script` legitimately creating its backing
component. Caller flags, exemption tokens, and policy inside that primitive are
prohibited.

One shared Python contract owner holds:

- the existing two-language script creation configuration;
- the reverse GUID/name selector classification;
- the structured handoff constructor; and
- the admitted model-facing caller classification.

The managed and native bridges gain no script GUID registry or policy. There is
no copied schema, dispatch table, cache, or fallback.

## Supported Script Identities

The policy is deliberately limited to the two types that `gh_create_script`
can construct:

| Language | Component GUID | Canonical name | Host nickname |
|---|---|---|---|
| Python | `719467e6-7cf5-4848-99b0-c5dd57e5442c` | `Python 3 Script` | `Py3` |
| C# | `b6ba1144-02d6-4a2d-b53c-ec62e290eeb7` | `C# Script` | `C#` |

GUID matching is case-insensitive across the .NET `Guid` N, D, B, P, and X
text forms for these two known identities. The classifier generates those
forms from the existing canonical GUIDs; it does not become a second general
GUID parser. Name and nickname matching is exact and case-insensitive,
matching the ordinary creation surface rather than adding fuzzy aliases.
Legacy GhPython and legacy C# components remain outside this handoff because
the recommended tool cannot create them.

Every supplied GUID and name selector is checked. If either identifies a
supported script component, the contradictory request fails closed with the
handoff. This prevents an invalid or unrelated GUID from masking a script name.
Non-script component creation is unchanged.

## Structured Handoff

Every refusal uses one constructor and returns:

```json
{
  "success": false,
  "data": {
    "code": "script_component_requires_dedicated_tool",
    "handoff_required": true,
    "source_tool": "gh_edit",
    "selector": {"kind": "guid", "value": "719467e6-7cf5-4848-99b0-c5dd57e5442c"},
    "component_guid": "719467e6-7cf5-4848-99b0-c5dd57e5442c",
    "recommended_tool": "gh_create_script",
    "recommended_language": "python",
    "alias_tool": "gh_create_python_script",
    "request": {
      "epoch": 7,
      "create": [{
        "temp_id": "T1",
        "guid": "719467e6-7cf5-4848-99b0-c5dd57e5442c"
      }]
    },
    "message": "handoff_required: gh_edit selected a python script component (719467e6-7cf5-4848-99b0-c5dd57e5442c). Call gh_create_script with language=\"python\" so source and pins are created through the dedicated authoring pipeline."
  }
}
```

`request` is the exact admitted tool argument object. The internal
`_is_handoff` marker may exist before public projection, but it is never part of
the public response. Public MCP projection remains the existing truthful failed
result: unchanged legacy text, `structuredContent.success=false`, and
`isError=true`.

## Closed Caller Audit

### Active model-facing ordinary creation

| Route | Caller-selected identity | Required policy |
|---|---|---|
| `gh_edit` | name or GUID in each `create` item | shared handoff before `/gh/edit` |
| `gh_explore_component` | GUID when no `instanceGuid` is used | shared handoff before creation |
| `gh_explore_deep` | GUID | shared handoff before creation |
| `gh_investigate` | GUID | shared handoff before creation |

An `instanceGuid` supplied to `gh_explore_component` refers to an existing
canvas object and does not enter the creation policy.

### Active dedicated creation

`gh_create_script`, `gh_create_python_script`, and `gh_create_csharp_script`
already use the same `_execute_gh_create_script` owner. `chirp_create` is also a
dedicated script-authoring route and must delegate its generated C# source and
pin declarations to that helper instead of calling `/gh/create-component`
itself.

### Internal and contained paths

- `gh_create_component` is internal, absent from public schemas, targeting, and
  direct ToolDispatcher routes.
- `gh_execute_intent` is retired. Its existing post-resolution handoff stays in
  place for defense in depth.
- `gh_explore_workflow` and `gh_replay_recipe` are suspended and cannot be
  reached through canonical MCP or direct ChatRunner dispatch.
- Fixed non-script support components created inside deep exploration are not
  caller-selected component identities and remain unchanged.

A structural regression must enumerate literal production callers of
`/gh/create-component` and `/gh/edit`, correlate them with this classification,
and fail when a new unclassified model-facing caller appears.

## Skill Contract

The reviewed `execute-grasshopper` skill must say explicitly:

- use `gh_edit` for ordinary graph composition;
- use `gh_create_script` for custom computation, source, or caller-declared
  pins;
- use `gh_update_script` and `gh_set_script_pins` for an existing script; and
- treat a handoff as a routing correction, not permission to repeat the refused
  ordinary call.

The skill does not prescribe task topology or witness-specific source.

## Alternatives Considered

1. **Shared model-facing contract owner — selected.** One classifier and one
   handoff constructor serve canonical and direct paths before target dispatch.
2. **Policy inside `/gh/create-component` — rejected.** It inverts ownership and
   requires exemptions for legitimate script creation.
3. **Route-specific guards or prose only — rejected.** They drift, miss callers,
   and do not causally prevent mutation.

## Verification Contract

Test-first coverage must prove:

- Python and C# refuse by canonical name, host nickname, and GUID;
- name and GUID produce the same recommended tool/language;
- a mixed `gh_edit` batch refuses before one target call or partial mutation;
- canonical MCP and direct ToolDispatcher expose the same handoff;
- `gh_explore_component`, `gh_explore_deep`, and `gh_investigate` refuse a
  selected script GUID before target dispatch;
- `gh_explore_component(instanceGuid=...)` remains unchanged;
- non-script `gh_edit` and exploration creation remain unchanged;
- `chirp_create` reaches raw creation only through
  `_execute_gh_create_script`;
- the existing four-input Point3d-list script request reaches the canonical
  helper without source or pin rewriting;
- `gh_create_script` remains discoverable and readable;
- `gh_update_script` and `gh_set_script_pins` remain unchanged; and
- the structural caller classification is complete.

## Explicit Exclusions

- no raw endpoint change;
- no managed/native policy or GUID registry;
- no new tool, runner, compiler, evaluator, or catalog;
- no acceptance role-binding change;
- no retry or budget framework;
- no prompt or task-topology tuning; and
- no Rhino, Grasshopper, model, or other live contact during implementation.

Post-merge live qualification is separately authorized and uses the unchanged
XY-grid intent, deterministic evaluator, Qwen/Prime/gateway stack, and at most
one repair.
