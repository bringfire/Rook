# Grasshopper Execution

Use this reference only for Grasshopper inspection, authoring, repair, or
verification through the bound Rook target.

## Orientation

1. Inspect the current definition, diagnostics, and the smallest relevant
   structure before mutation.
2. Resolve exact component identities, parameter indices, and required tool
   arguments for the next intended mutation. Stop discovery when those facts
   are known.
3. Preserve useful existing components and controls. Prefer local repair over a
   wholesale reset.

Choose native components or an admitted script component according to the
request and the smallest reliable implementation. A strategy may change when
live evidence makes another path preferable; preserve unaffected committed
work during the pivot.

## Mutation And Repair

- Read each authoring contract before its first use and retain it for the
  session.
- Treat every structured success or failure envelope as the authoritative
  outcome of that invocation.
- Retain every committed mutation receipt. Do not claim a no-op as a mutation.
- After refusal or failure, refresh only the fact implicated by the failure and
  make a bounded local repair.
- Never automatically replay a mutation whose commit outcome is uncertain.
- After a mutation batch, wait for solve readiness and inspect diagnostics or
  geometry before deciding the next action.

Use viewport captures when visual quality, arrangement, or resemblance is
material. Quantitative and structural evidence remain useful, but do not claim
visual inspection when an image was not actually available to you.

## Completion

The Actor-owned ending for goal-backed Grasshopper work is:

```text
last actual committed mutation R leaves selected defaults restored
-> await solve readiness for R
-> inspect a fresh snapshot fenced to the same receipt R
-> resolve only a named material uncertainty that could change completion
-> reason from the retained evidence without another tool call
-> run await goal.complete() in a dedicated final IPython cell
-> emit final text only
```

Greater precision, repeated confirmation, or reassurance is not material
investigation when it cannot change the completion decision. No later tool call
is permitted after `goal.complete()`. If evidence remains contradictory,
missing, blocked, or uncertain, report that honestly instead of completing the
goal.

