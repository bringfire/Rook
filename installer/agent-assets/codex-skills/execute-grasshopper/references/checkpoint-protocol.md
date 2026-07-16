# Checkpoint Protocol Reference

## The Checkpoint Sequence

After every batch of 3-5 tool calls:

```python
# 1. The preceding gh_edit schedules the solution. Poll only to a fixed timeout.
status = gh_status()
# Repeat while readiness is false. Continue only when ready_for_edit is true,
# solverEnabled is true, and solutionState is PostProcess.

# 2. Check for errors and warnings
gh_errors()
# Returns: list of components with error/warning messages
```

Stop and report if the timeout expires, `solverEnabled` is false, or
`solutionState` is unknown. Do not infer completion from elapsed time alone.

## Error Classification

### Green (No Message) — Success
Component computed without issues. Proceed.

### Yellow (Warning) — Usually Acceptable
Common warnings and how to handle:

| Warning | Meaning | Action |
|---------|---------|--------|
| "Empty geometry" | Component produced no output | Check if inputs are connected |
| "Null data" | One input is null | May be intentional (optional input) |
| "Cast warning" | Implicit type conversion | Usually fine, verify output type |

### Orange (Error) — Needs Attention
The component failed to compute. Common errors:

| Error | Cause | Fix |
|-------|-------|-----|
| "Data conversion failed" | Wrong param type wired | Check sourceParam/targetParam names |
| "Null value on input X" | Missing required input | Wire the missing input |
| "Index out of range" | List/tree mismatch | Insert Flatten or Graft between components |
| "Path mismatch" | Data tree structure conflict | Use Path Mapper or Graft/Flatten |

### Red (Solution Exception) — Critical
The component crashed during computation:

| Error | Cause | Fix |
|-------|-------|-----|
| "1. Solution exception" | Bad parameter value | Check value ranges, try different input |
| "Object reference null" | Internal component error | Delete and recreate component |
| "Recursive data structure" | Circular wiring | Check connection graph for loops |

## Recovery Procedure

When a checkpoint finds errors:

```
1. READ the error message carefully
2. CHECK the gotchas section of the plan — is this a known issue?
3. If known: APPLY the documented fix
4. If unknown: INSPECT the failing component:
   gh_batch_component_info(names=[<component_name>])
5. IDENTIFY the cause (missing input, wrong type, bad value)
6. APPLY one fix:
   - Reconnect: gh_edit(disconnect=[...], connect=[...]) with correct flow strings
   - Change value: gh_set_value()
   - Insert converter: resolve the exact converter with gh_library or
     gh_knowledge_query, then add and wire it in one bounded gh_edit batch
7. RE-RUN checkpoint:
   bounded-poll gh_status to the fixed timeout and require solved readiness
   gh_errors()
8. If error persists: LOG it and move to next batch
   (unless it blocks downstream connections)
```

## Rollback Procedure

When a batch is unrecoverable:

```python
# Delete all components created in the failing batch
gh_delete(guids=[$COMP_FROM_THIS_BATCH_1, $COMP_FROM_THIS_BATCH_2, ...])

# Verify canvas is clean
gh_snapshot()

# Option A: Re-attempt the batch with modifications
# Option B: Skip the batch and continue (if downstream can work without it)
# Option C: Stop and report to user
```

**When to rollback vs continue:**
- Rollback if the failed components are in the critical path (downstream components depend on them)
- Continue if the failed components are in a side branch (optional feature, visualization only)

## Consecutive Error Threshold

Track **consecutive batches that each have at least one unresolved error**. Fixed errors reset the counter.

```
Batch 1: 0 errors                    → counter = 0 ✓
Batch 2: 1 error, fixed in-place     → counter = 0 ✓ (fixed resets counter)
Batch 3: 1 error, NOT fixed          → counter = 1 ⚠
Batch 4: 2 errors, NOT fixed         → counter = 2 ✗ → STOP
```

A batch with errors that are all resolved resets the counter to 0. Only unresolved errors count.

After 2 consecutive batches with unresolved errors:
1. Stop execution
2. List all accumulated errors with their component GUIDs
3. Show what was completed successfully
4. Ask the user: "Should I rollback the last N batches and try a different approach, or continue despite these errors?"

## Performance Considerations

- **Simple definitions (< 20 components):** Use a short bounded status-poll timeout
- **Medium definitions (20-50 components):** Allow a longer bounded timeout
- **Large definitions (50+ components):** Allow a longer bounded timeout and consider checkpointing every 3 components instead of 5
- **Heavy computation (mesh operations, large lists):** Individual component inspection with `gh_batch_component_info(names=[...])` to check output size before continuing
