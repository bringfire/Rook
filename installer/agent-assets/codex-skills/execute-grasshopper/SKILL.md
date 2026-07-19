---
name: execute-grasshopper
description: |
  Execute a Grasshopper implementation plan by running MCP tool calls in
  batches with solve/error checkpoints between each batch. Use after
  /plan-grasshopper produces a plan doc, or when the user has an exact
  step-by-step tool call sequence to execute on the GH canvas.
argument-hint: "<path to plan doc>"
---

# Execute Grasshopper Definition

Execute an implementation plan by calling MCP tools in batches with verification checkpoints. This skill assumes all decisions have been made — it follows the plan exactly, adapting only when errors require course correction.

## The Process

### 1. Pre-flight Check

Before executing any tool calls:

```python
# Confirm Grasshopper is running
gh_status()

# Capture baseline canvas state
gh_snapshot()
```

Read the plan document from the argument path (resolve to absolute path first — `Read` requires absolute paths). Parse:
- The gotchas section (load into working memory for error handling)
- Each batch with its steps
- Checkpoint expectations
- Rollback strategy
- Success criteria

If the plan references an existing canvas state that doesn't match reality, stop and report the mismatch.

### 2. Initialize Component Registry

Create a mapping from plan variable names to committed component IDs:

```
Component Registry:
  $RADIUS_SLIDER → (not yet assigned)
  $SPHERE        → (not yet assigned)
  ...
```

Within a `gh_edit` batch, use plan-defined `T1`, `T2`, ... temp IDs in create,
connect, and group entries. After the call, read `edit_summary.temp_id_map` and
the returned committed topology, then update the registry before any later batch
references those components.

### 3. Execute Batches

For each batch in the plan:

**Before the batch:**
- Announce: "Starting Batch N: <description> (N steps)"

**For each step:**

1. Capture a fresh `gh_snapshot`. Compare its components, flows, and groups with
   the plan's structural baseline. If they match, use that fresh snapshot's epoch
   for the immediate `gh_edit`. Never compare or persist epoch numbers across
   snapshots.
2. Execute the exact bounded `gh_edit` batch from the plan. Slider/panel/toggle
   values belong in their create entries; updates to existing controls belong in
   `set_values`.
3. Inspect `partial_success`, `verified`, `edit_summary.errors`,
   `edit_summary.temp_id_map`, and the returned topology. Update the component
   registry only for committed creations.
4. If creation or wiring fails, inspect the affected components, attempt ONE
   documented fix using a fresh epoch, and retry only the missing/incorrect
   operations. Do not replay an already committed batch.
5. Read solved output data with a follow-up `gh_snapshot` or
   `gh_inspect_output` after the solve settles.

**At each checkpoint:**

The preceding `gh_edit` schedules the solution. After it reports
`edit_summary.solve_scheduled`, bounded-poll `gh_status` to a fixed timeout.
Continue only when `ready_for_edit` is true, `solverEnabled` is `true`, and
`solutionState` is `PostProcess`; then inspect errors:

```python
status = gh_status()
# Repeat only until the fixed checkpoint timeout while readiness is false.
errors = gh_errors()
```

Stop and report instead of continuing if the timeout expires, the solver is
disabled, or the solution state is unknown.

- **No errors:** Continue to next batch
- **Warnings only:** Note them, continue (warnings are usually acceptable)
- **Errors on a component:**
  1. Check if the error matches a gotcha from the plan
  2. If yes: apply the documented fix
  3. If no: inspect with `gh_batch_component_info(names=[<component_name>])`
  4. Attempt ONE fix (reconnect, change parameter, insert converter)
  5. Re-run checkpoint
  6. If error persists: log it and continue (unless it blocks downstream)

**After the batch:**
- Report: "Batch N complete: X components created, Y connections made, Z errors"

### 4. Error Escalation

Track consecutive errors. If **2 or more consecutive batches** have unresolved errors:
- Stop execution
- Report all accumulated errors to the user
- Suggest: which batch to roll back, what might fix the issue
- Wait for user guidance before continuing

### 5. Post-Execution

After all batches complete:

```python
# Auto-organize the canvas layout
gh_canvas_cleanup()

# Create visual groups as specified in the plan
gh_edit(epoch=<current>, groups=[
  {"action": "create", "nick": "Inputs", "colour": "#3366FF", "members": [...]},
  {"action": "create", "nick": "Processing", "colour": "#33AA66", "members": [...]},
  {"action": "create", "nick": "Output", "colour": "#FF8833", "members": [...]}
])

# Final verification after the grouping edit's scheduled solution settles
final_status = gh_status()
# Apply the same bounded readiness predicate before reading errors.
final_errors = gh_errors()
final_state = gh_snapshot()
```

**Report to user:**
```
Execution complete:
- Components created: 12
- Connections made: 15
- Groups created: 3
- Final errors: 0
- Canvas organized: yes

The definition should now show <success criteria from plan>.
```

### 6. Handoff to Consolidate

After reporting results:

**REQUIRED:** Invoke consolidate to record what was learned:
```python
Skill(skill="consolidate")
```

## Invariants

- **Never skip a checkpoint** — every batch must verify solved readiness + errors
- **Maintain the component registry** — plan variable → committed ID, updated from every batch result
- **If creation errors, don't wire** — skip connections to failed components
- **One fix attempt per error** — don't loop on the same error
- **2+ consecutive batch errors = stop** — ask user for guidance
- **Always canvas_cleanup before finishing** — even if there were errors
- **Report every batch** — the user should see progress, not just the final result

## Integration

**Cascades into:**
- **consolidate** (REQUIRED) — automatically invoked after execution completes

**Called by:**
- **plan-grasshopper** — after plan document is saved
- Direct user invocation (`/execute-grasshopper`)

## References

- See [checkpoint-protocol.md](./references/checkpoint-protocol.md) for error classification and recovery
