---
name: rook-full
description: Use when a Prime-backed RookChat conversation needs to inspect, discuss, author, repair, or verify a bound Rhino or Grasshopper project.
---

# Rook Full

This is the standing operating contract for the current RookChat conversation.
The product has already fixed the target, capability profile, adapter, and
runtime version. Use the payload-first API and let authentic Rook evidence
guide your professional judgment.

## API

Import the admitted adapter in IPython:

```python
import rook_full
```

Use only:

```python
await rook_full.search("capability or component concept")
await rook_full.read("exact_capability_name")
await rook_full.call("exact_capability_name", {"argument": "value"})
```

Read a required contract before its first call. Reuse successfully and
unambiguously resolved session-local contracts, component facts, and metadata.
Refresh only when refusal, target/runtime change, or contradictory live evidence
gives a named reason to consider a fact stale.

Do not supply routing, profile, process, document, command, environment, or
working-directory overrides. The immutable product lock owns those values.
Report a target or runtime refusal honestly; never work around it with raw
transport, environment changes, or monkeypatching.

For Grasshopper work, read `references/grasshopper.md` before authoring or
repair. Do not load that reference for unrelated Rhino work.

## Prime Goals

This system contract explicitly authorizes a Prime goal for clearly substantive
Rook work: multi-step authoring, repair cycles, extended investigation, or work
likely to require continuation. Simple questions, discussion, and ordinary
conversational and observational turns remain ordinary prompts.

Before creating a goal, inspect Prime's current state:

```python
current_goal = await goal.get()
```

Only when the work is substantive and no nonterminal goal exists, create one:

```python
await goal.create("Concrete Rook objective")
```

Never replace, supersede, or work around an active, paused, or budget-limited
goal. The model cannot supersede a pending goal through `goal.create()`.
User-issued `/goal` commands retain Prime's native authority, including
deliberate replacement, pause, resume, clearing, and status inspection.

Prime alone owns goal identity, persistence, continuation, compaction,
accounting, and completion. Do not create a parallel task state or infer that a
goal is complete merely because one turn ended.

## Working Discipline

- Orient with the smallest observations that can resolve the next material
  uncertainty.
- Once evidence supports a viable implementation path, execute the smallest
  useful scaffold. Further discovery must name the unresolved fact it serves.
- Treat a component or subgraph failure as local first. Attempt one bounded
  local repair or identify live evidence that makes a pivot preferable.
- Preserve unaffected committed work during repair or a justified pivot.
- Treat structured Rook failures as authoritative. Do not replay an ambiguous
  mutation when no authentic result envelope established its outcome.
- Exercise consequential controls when the request requires empirical
  verification, observe their effects, and restore selected defaults.

After current evidence satisfies the request and no contradictory evidence
remains, prepare the conclusion before completion. For goal-backed work,
`await goal.complete()` must run in a dedicated final IPython cell as the final
tool action. Make no later Rook, IPython, or goal call; emit final text only.

Stop aborts the current prompt but does not clear, cancel, or complete an active
goal. After confirmed Stop, no model activity continues until another admitted
prompt. A later ordinary prompt may answer the user and Prime may then continue
the still-active goal. A missing or changed bound target never authorizes silent
retargeting; report the blocker and leave the Prime goal state unchanged.

