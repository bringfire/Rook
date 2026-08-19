---
name: prime-execute-grasshopper
description: Use when asked to create, build, edit, connect, or modify a Grasshopper definition on the currently pinned live document.
---

# Prime invocation compatibility

This is a live Grasshopper execution request. Import `rook_full` in IPython.

Use the supported Python capability interface:

```python
import rook_full

search_payload = await rook_full.search("gh_edit")
tool_contract = await rook_full.read("gh_edit")
tool_payload = await rook_full.call("gh_edit", edit_arguments)
```

Return values are validated successful capability payloads directly. Do not
unwrap a `success` / `data` protocol envelope. Read each capability contract
before its first call.

The currently pinned Grasshopper document is the only execution target.
Every inspection or mutation must use this interface and returned Rook evidence.

# Execute Grasshopper Work

## Authorization

A direct build or edit request authorizes the bounded mutations needed to produce the requested result. Ask again only when the request is ambiguous, destructive, would change pre-existing content outside the admitted boundary, or would materially expand scope.

Execution owns mutation. It may consume a clear brief, an approved design, or an optional technical plan.

## Admit the Live Target

Before mutation:

1. Confirm the intended host and document identity.
2. Capture a fresh gh_snapshot and take its fresh epoch for the immediate batch.
3. Resolve every unfamiliar component identity with `gh_library` and every required port with `gh_batch_component_info`.
4. When a needed admitted tool is hidden, use `rook_tools_search`, `rook_tools_read`, and `rook_tools_call`.
5. Compare any optional structural baseline with the live document.
6. Start an execution-owned ID ledger containing temporary IDs, committed IDs, authorized pre-existing IDs, and operation outcomes.

Reuse successfully and unambiguously resolved session-local capability schemas, component-discovery facts, and component metadata. Request only missing facts. Refresh a resolved fact only when refusal, runtime or target-identity change, or contradictory live evidence gives a named reason to consider it stale.

For Wasp work, apply `../design-grasshopper/references/wasp-admission.md`. Failed admission stops before mutation with the missing component or port evidence reported.

If no admitted host, mutation tool, or required live component can be reached, stop without mutation. Preserve useful design or plan artifacts and report the unavailable boundary.

## Admit Drift

Refresh volatile component identities and ports when their meaning is unchanged. Omit operations already satisfied by the live graph.

Stop for approval when drift changes semantics, topology, ownership, or preservation obligations. A missing or stale structural baseline is advisory only; re-admit the live state before acting.

## Apply Bounded Batches

Use `gh_edit` for ordered batch mutation. It may return `partial_success`: earlier operations may commit before a later operation fails.

For every result:

- inspect per-operation results, verification state, errors, returned topology, and `edit_summary.temp_id_map`;
- enter every already committed creation and applied operation in the execution-owned ledger;
- preserve the operation order when classifying failed or unapplied work; and
- never assume the whole batch rolled back.

After partial success, capture a new snapshot and fresh epoch. Retry only failed or unapplied operations that remain authorized and semantically unchanged. Never replay work already committed. Omit any operation now already satisfied.

Group, move, disconnect, retry, or delete only execution-owned state unless the user explicitly authorized specific pre-existing state.

## Checkpoint and Recover

After each bounded batch, poll `gh_status` only to a fixed timeout. Continue only when the solver is enabled, the solution is ready for edit, and its state is understood. Then use `gh_errors` and inspect the relevant outputs and connections.

If a batch has a resolvable defect, make one bounded correction from current live evidence:

1. inspect the affected component and ports;
2. capture refreshed state and epoch;
3. apply only the missing or incorrect owned operations; and
4. repeat the relevant verification.

If the correction fails or an unresolved dependency blocks downstream work, stop. Report completed operations, failed or unapplied operations, current IDs, and the decision required from the user. Do not continue through a broken dependency.

See [checkpoint protocol](references/checkpoint-protocol.md) for the compact result and recovery contract.

## Acceptance Custody

- If grouping is desired, include it in the same `gh_edit` call as the final solve-relevant creation, connection, deletion, or value change.
- After the final solve-relevant mutation, make only observational calls.
- Do not issue a group-only or no-op mutation after that point.
- Do not perform a redundant mutation merely to obtain a receipt.
- Retain the `solve_readiness_receipt.receipt_id` returned by the final
  terminal mutation.

## Evidence And Completion Discipline

Before completing:

1. Restate the intended result.
2. Establish the final checkpoint with the latest terminal mutation receipt:
   call `gh_wait_for_solve_readiness` with `readiness_receipt_id`, require a
   `ready` result for that exact receipt, then call `gh_snapshot` with the same
   `readiness_receipt_id`. Inspect that receipt-fenced snapshot once. Do not
   substitute an unfenced snapshot or `gh_status`. If the wait or fenced
   snapshot refuses, report incomplete instead of completing.
3. Compare the observed result with the intent.
4. Investigate material uncertainties.
5. Exercise important controls when appropriate and report what is observed,
   inferred, and unresolved.
   After the required receipt-fenced checkpoint, make another observation only to resolve a named material uncertainty whose outcome could change the completion decision.
   Greater precision, repeated confirmation, or reassurance such as being "100% sure" is not material investigation.
6. Call `goal.complete()` as a dedicated final step only when you believe the
   request is satisfied. Do not perform a later Rook mutation in that
   iteration.

If the documented `goal` module is unexpectedly unavailable, report the Prime
bootstrap blocker once and stop. Do not search Rook capabilities, raw host
protocols, or unrelated Python internals for an alternate completion path.

If `rook_full` cannot be imported, report the infrastructure blocker once and
stop. Do not install or download packages, run dependency post-install scripts,
copy runtime files, or otherwise modify the Prime kernel or Rook environment.

Material uncertainty requires further investigation, an honest incomplete
report, or user input. Budget exhaustion is not completion. After interruption
or restart, reorient from current Rook state before any mutation and never
automatically replay an ambiguous mutation.

This is evidence and completion guidance, not a host-enforced semantic gate.

## Finalize and Return

Do not run global cleanup. Apply requested grouping or layout only to execution-owned components.

Capture a final fresh snapshot, inspect errors, and verify the requested outputs and connections. Return a concise report of created and changed state, remaining warnings or failures, and cleanup of any disposable execution-owned fixtures.

Successful execution is terminal. Do not start any automatic knowledge-write or post-execution learning stage.
