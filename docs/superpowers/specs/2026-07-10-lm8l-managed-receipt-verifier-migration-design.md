# LM8L/LM8M Managed-Receipt Affine Verifier Migration Design

Status: design checkpoint for review

Date: 2026-07-10

## 1. Purpose

LM8K established a product-level Grasshopper solve-readiness receipt:

```text
gh_set_value
-> pending managed receipt
-> correlated solution start/end
-> ready receipt
-> one receipt-fenced gh_inspect_output
```

LM8J established the affine scalar baseline over twenty independent scheduled
attempts:

```text
20/20 accepted
20/20 worker value = 3.0
20/20 observed Addition R = 7.5
11/20 accepted on the first verifier read
9/20 required a second verifier read
```

The worker and scalar path were stable, but verification still depended on a
probe-owned bounded settle loop. LM8L migrates only that post-worker verifier
to the LM8K product receipt. LM8M repeats the LM8J N=20 sample with the managed
verifier profile.

Core question:

```text
Does the LM8J affine path remain 20/20 accepted when probe-owned settle reads
are replaced by one managed readiness wait and exactly one freshness-fenced
output read?
```

LM8L is the managed verifier-profile implementation identity. LM8M is the
post-merge N=20 evidence and comparison identity. Neither requires a new probe
script.

## 2. Baseline And Intervention

The controlled comparison is:

```text
LM8J baseline:
  LM8I verifier_profile = settle_v1
  gh_set_value
  -> gh_solve
  -> up to three unfenced gh_inspect_output reads

LM8M intervention:
  LM8I verifier_profile = managed_receipt_v2
  gh_set_value
  -> exactly one gh_wait_for_solve_readiness
  -> exactly one receipt-fenced gh_inspect_output
```

Held constant:

- affine fixture topology and setup
- fixture readiness behavior
- worker model gemma4:12b-it-qat
- direct Ollama worker path
- worker prompt and evidence packets
- publication support policy
- worker action draft_gh_set_value_params {"value": number}
- trusted GUID binding in the scalar applier
- expected output 7.5
- scalar tolerance 1e-9
- twenty scheduled attempts
- no replacement attempts
- child process timeout 600 seconds

Changed:

```text
post-worker verification mechanism only
```

LM8L/LM8M consume the shipped LM8K contract. They do not reopen the product
receipt design.

## 3. Design Decision

LM8L extends the existing LM8I script with a verifier profile:

```text
scripts/lm8i_affine_publication_shape_support_probe.py

--verifier-profile settle_v1
--verifier-profile managed_receipt_v2
```

settle_v1 remains the default. Its command, live sequence, artifact schemas,
summary shapes, and terminal behavior remain compatible with historical
LM8I/LM8J.

LM8M extends the existing LM8J wrapper with the same explicit profile selector:

```text
scripts/lm8j_affine_support_repeatability_probe.py

--verifier-profile settle_v1
--verifier-profile managed_receipt_v2
```

The default wrapper path remains LM8J. The managed path writes an LM8M run
identity and LM8M schemas.

Rejected alternatives:

1. A new LM8L sibling live script would copy approximately 85 KB of LM8I and
   create long-term safety drift.
2. A new LM8M wrapper would duplicate LM8J scheduling and accounting.
3. Extracting a shared affine live engine would add a broad refactor variable
   to a mechanism-only comparison.

Behavioral replayability, proven by preservation tests, is sufficient. Source
files do not need to remain byte-for-byte frozen.

## 4. Scope

In scope:

- one verifier profile in LM8I
- one profile selector and LM8M run identity in LM8J
- managed-only bounded stage artifacts
- independent LM8M child-artifact auditing
- deterministic fake-tool and fake-child tests
- one post-merge canonical LM8M N=20 run
- a later doc-only evidence summary

Out of scope:

- no new LM8L or LM8M Python script
- no fixture setup or fixture-readiness migration
- no affine source-packet changes
- no worker prompt, protocol, or action changes
- no publication-support changes or forcing
- no scalar applier changes
- no Planner model
- no retry or replacement attempts
- no gh_edit
- no worker-authored topology or wiring
- no LM8K registry or public-contract changes
- no fallback from managed receipts to settle reads
- no removal of settle_v1
- no live run in the implementation PR
- no raw probe_runs artifacts committed

## 5. Profile Contracts

### 5.1 settle_v1

settle_v1 is the historical verifier behavior:

```text
gh_set_value
-> gh_solve
-> up to three gh_inspect_output reads
-> bounded delay between reads
```

The bare LM8I and LM8J commands continue to select this profile. Existing LM8J
run prefixes, schemas, summaries, commands, and comparison key remain
unchanged.

Managed-only fields and files are absent from settle_v1. Their absence is the
baseline contract, not an LM8L failure.

### 5.2 managed_receipt_v2

managed_receipt_v2 changes only verification after a valid worker action has
been applied and gh_set_value has been dispatched.

Required sequence:

```text
extract the LM8K readiness receipt from the worker mutation result
-> validate the bounded pending receipt shape
-> wait once for that opaque receipt ID with timeout_ms = 10000
-> require wait_status == ready
-> perform one gh_inspect_output with the same readiness_receipt_id
-> validate exact provenance and output
-> decide
```

After the worker mutation, the managed profile must not call:

- gh_solve
- immediate readiness status polling
- a second readiness wait
- an unfenced gh_inspect_output
- the existing settle loop
- asyncio.sleep as readiness policy

There is no fallback. Missing, malformed, timed-out, stale, superseded, unknown,
or document-replaced receipts terminate the child as receipted evidence.

### 5.3 Fixture readiness remains legacy

LM8L does not migrate deterministic fixture setup. Initial fixture creation,
prechecks, initial solve behavior, and initial Addition output inspection remain
the existing LM8I behavior.

Every managed child manifest and decision records:

```text
fixture_readiness_profile: lm8i_legacy_setup_v1
verifier_profile: managed_receipt_v2
verifier_mechanism: managed_solve_readiness_receipt
readiness_wait_timeout_ms: 10000
```

Fixture setup failures retain existing classifications and artifacts. No
receipt wait occurs before a valid worker action is dispatched.

## 6. CLI And Run Identity

### 6.1 LM8I

LM8I gains:

```text
--verifier-profile
  choices: settle_v1 | managed_receipt_v2
  default: settle_v1
```

LM8L v1 does not expose a readiness-timeout override. The managed timeout is a
fixed comparison constant:

```text
readiness_wait_timeout_ms: 10000
```

The existing worker provider timeout remains separate.

### 6.2 LM8J/LM8M

Historical LM8J command:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm8j_affine_support_repeatability_probe.py
```

LM8M command:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm8j_affine_support_repeatability_probe.py --verifier-profile managed_receipt_v2
```

The wrapper forwards managed_receipt_v2 to every LM8I child. It does not
forward or invent a readiness-timeout argument.

Run identity:

```text
settle_v1:
  run prefix = lm8j-
  schema = rook.lm8j_affine_support_repeatability_probe:v1

managed_receipt_v2:
  run prefix = lm8m-
  schema = rook.lm8m_affine_managed_receipt_repeatability_probe:v1
```

Both profiles continue to store children under lm8i_runs. Child discovery
remains filesystem-delta based.

## 7. Canonical Configuration

LM8M canonical configuration is:

```text
attempts: 20
model: gemma4:12b-it-qat
verifier_profile: managed_receipt_v2
readiness_wait_timeout_ms: 10000
child_attempt_timeout_s: 600
replacement_attempts: false
publication support: available, not forced
```

The clocks are independent:

```text
readiness_wait_timeout_ms = 10000
  managed product wait for one child mutation receipt

child_attempt_timeout_s = 600
  subprocess budget for the complete child attempt
```

canonical_evidence describes configuration identity, not outcome. A canonical
red run remains canonical evidence.

For managed mode, canonical_evidence is true only when every value above is
exact. The default LM8J canonical predicate remains unchanged.

## 8. Managed Verification Flow

### 8.1 Mutation stage

After scalar applier validation, LM8I dispatches the existing mutation:

```text
gh_set_value(editable slider GUID, worker-authored value)
```

Managed mode extracts only the nested LM8K receipt from that exact result.

Required mutation receipt properties:

```text
schema == rook.gh_solve_readiness_receipt:v1
status == pending
receipt_id is a non-empty opaque string
document_session_id is present
mutation_epoch is a positive integer
solution_run_epoch is null
completed_solution_run_epoch is a non-negative integer representing the most
recent completed run before the new mutation's scheduled run
```

The outer gh_set_value success bit remains diagnostic. The valid pending
receipt is the authority for proceeding. A tool-call exception remains an
existing live-mutation rejection.

The opaque ID exists only in memory for the wait and fenced read. Persisted
artifacts store a canonical hash:

```text
sha256:<lowercase hex over exact UTF-8 receipt ID>
```

### 8.2 Wait stage

LM8I calls exactly once:

```json
{
  "readiness_receipt_id": "opaque-id",
  "timeout_ms": 10000
}
```

Required outcome:

```text
wait_status == ready
receipt.status == ready
receipt.schema == rook.gh_solve_readiness_receipt:v1
```

The ready receipt supplies authoritative completed provenance. Epoch comparison
uses it, not the initially pending receipt, whose solution run may be unbound.

A timeout does not trigger status polling, another wait, gh_solve, an unfenced
read, or a settle read. The registry receipt may remain pending. The child
records the outcome and terminates rejected.

### 8.3 Fenced read stage

After one ready wait, LM8I calls exactly once:

```json
{
  "guid": "trusted Addition GUID held by the probe",
  "param": "R",
  "readiness_receipt_id": "same opaque-id"
}
```

The response must report readiness_fenced true and one scalar output value.
The worker never sees or authors the Addition GUID or receipt ID.

## 9. Child Acceptance Invariants

A managed child may report accepted only when all conditions hold:

```text
live_set_value_dispatched == true
wait_status == ready
readiness_wait_count == 1
fenced_output_read_count == 1
settle_read_count == 0
readiness_fenced == true
observed output == 7.5 within tolerance 1e-9
```

The same opaque receipt ID must flow unchanged through:

```text
gh_set_value emitted receipt
-> gh_wait_for_solve_readiness request and result
-> receipt-fenced gh_inspect_output request and response
```

Persisted equality is checked through the canonical receipt ID hash.

Mutation, ready-wait, and fenced-read provenance must exactly match on:

```text
receipt_id_sha256
document_session_id
mutation_epoch
```

The ready run must prove post-mutation advancement:

```text
pending.solution_run_epoch is null
ready.solution_run_epoch > pending.completed_solution_run_epoch
```

The completed ready run must then be identical across wait and read:

```text
wait.solution_run_epoch
== wait.completed_solution_run_epoch
== read.solution_run_epoch
== read.completed_solution_run_epoch
```

An output of 7.5 cannot override a count, mechanism, or provenance mismatch.

These invariants apply only after live_set_value_dispatched is true. A worker
decline, publication failure, preflight failure, or fixture gate failure
legitimately has zero waits and reads.

## 10. Terminal Mapping

LM8I keeps its top-level vocabulary.

If a valid worker action reached live mutation, readiness failures use:

```text
decision: rejected
phase: verifier_readiness
```

Pinned readiness reasons:

```text
readiness_receipt_missing
readiness_receipt_malformed
readiness_wait_timeout
readiness_receipt_superseded
readiness_receipt_stale_solution_run
readiness_receipt_document_replaced
readiness_receipt_solver_locked
readiness_receipt_unknown
readiness_receipt_expired
readiness_receipt_not_found_or_evicted_or_process_restarted
readiness_receipt_not_ready
readiness_wait_already_active
managed_verifier_invariant_failed
```

LM8I preserves shipped LM8K distinctions:

```text
wait_status == terminal, receipt.status == unknown,
receipt.reason == receipt_expired
  -> readiness_receipt_expired

failed wait operation with error
readiness_receipt_not_found_or_evicted_or_process_restarted
  -> readiness_receipt_not_found_or_evicted_or_process_restarted

fenced read rejected because the receipt is still pending
  -> readiness_receipt_not_ready
```

These outcomes must not collapse into readiness_receipt_unknown.

Structural, count, and provenance mismatches use:

```text
reason: managed_verifier_invariant_failed
failed_invariants: [bounded stable reason codes]
actual_counts:
  readiness_wait_count
  fenced_output_read_count
  settle_read_count
```

A valid fenced read with exact provenance but a scalar mismatch remains
rejected / verify_scalar_output_failed in phase verify_scalar_output.

A valid fenced read with exact provenance and matching output is
accepted / verify_scalar_output_succeeded.

## 11. Managed Artifacts

### 11.1 Compatibility and safety

Managed-only fields and files are absent from settle_v1. Managed mode uses
existing stage filenames plus one wait artifact:

```text
live_set_value_summary.json
readiness_wait_summary.json
verify_scalar_output_summary.json
decision.json
```

No raw receipt ID or unbounded tool result is persisted. Every managed record
carries a managed-profile schema/version.

### 11.2 Mutation summary

Managed live_set_value_summary.json includes:

```json
{
  "managed_mutation": {
    "schema": "rook.lm8l_managed_mutation_summary:v1",
    "receipt_schema": "rook.gh_solve_readiness_receipt:v1",
    "receipt_status": "pending",
    "receipt_id_sha256": "sha256:<hex>",
    "document_session_id": "...",
    "mutation_epoch": 13,
    "solution_run_epoch": null,
    "completed_solution_run_epoch": 41
  }
}
```

Existing bounded set-value diagnostics may remain. The full result and opaque
receipt ID are forbidden.

### 11.3 Wait summary

readiness_wait_summary.json exists only after managed mode attempts a wait:

```json
{
  "schema": "rook.lm8l_readiness_wait_summary:v1",
  "requested_timeout_ms": 10000,
  "readiness_wait_count": 1,
  "wait_status": "ready",
  "receipt_status": "ready",
  "receipt_id_sha256": "sha256:<hex>",
  "document_session_id": "...",
  "mutation_epoch": 13,
  "solution_run_epoch": 42,
  "completed_solution_run_epoch": 42
}
```

Failure records remain bounded and carry the normalized readiness reason.

### 11.4 Verification summary

Managed verify_scalar_output_summary.json uses:

```json
{
  "schema": "rook.lm8l_fenced_output_verification_summary:v1",
  "verifier_profile": "managed_receipt_v2",
  "readiness_wait_timeout_ms": 10000,
  "readiness_wait_count": 1,
  "fenced_output_read_count": 1,
  "settle_read_count": 0,
  "readiness_fenced": true,
  "receipt_id_sha256": "sha256:<hex>",
  "document_session_id": "...",
  "mutation_epoch": 13,
  "solution_run_epoch": 42,
  "completed_solution_run_epoch": 42,
  "expected_output_value": 7.5,
  "observed_output_value": 7.5,
  "tolerance": 1e-9,
  "matched": true
}
```

Managed mode has no verifier-attempt list because exactly one fenced read is
permitted.

### 11.5 Decision metadata

Managed decisions retain the LM8I envelope and add:

```json
{
  "managed_verifier": {
    "schema": "rook.lm8l_managed_verifier_decision:v1",
    "verifier_profile": "managed_receipt_v2",
    "verifier_mechanism": "managed_solve_readiness_receipt",
    "fixture_readiness_profile": "lm8i_legacy_setup_v1",
    "readiness_wait_timeout_ms": 10000,
    "readiness_wait_count": 1,
    "fenced_output_read_count": 1,
    "settle_read_count": 0,
    "failed_invariants": []
  }
}
```

Child aggregate booleans may be diagnostic, but LM8M must not use them as
authority.

## 12. LM8M Independent Audit

LM8M reads child artifacts independently. It does not trust:

- child decision alone
- child provenance_match
- child managed_verifier_invariants_valid
- observed scalar value alone

Every child claiming accepted must have:

```text
live_set_value_summary.json
readiness_wait_summary.json
verify_scalar_output_summary.json
decision.json
```

LM8M validates every managed schema, type, count, timeout, status, scalar value,
and cross-stage field.

It recomputes:

```text
mutation:
  receipt schema == rook.gh_solve_readiness_receipt:v1
  receipt status == pending
  mutation_epoch > 0
  solution_run_epoch is null
  completed_solution_run_epoch is a non-negative integer

wait:
  readiness_wait_count == 1
  wait_status == ready
  receipt status == ready
  requested_timeout_ms == 10000

read:
  fenced_output_read_count == 1
  settle_read_count == 0
  readiness_fenced == true
  observed output == 7.5 within 1e-9
```

It independently compares:

```text
receipt_id_sha256 across mutation, wait, read
document_session_id across mutation, wait, read
mutation_epoch across mutation, wait, read
wait solution_run_epoch > mutation completed_solution_run_epoch
wait solution_run_epoch == wait completed_solution_run_epoch
wait solution_run_epoch == read solution_run_epoch
read solution_run_epoch == read completed_solution_run_epoch
```

If the child correctly reports an invariant failure as rejected, LM8M keeps
rejected and records audit details.

If a child reports accepted while an artifact is missing, malformed,
wrong-schema, wrong-profile, or inconsistent, LM8M classifies it:

```text
terminal_category: wrapper_error
failure_reason: accepted_child_managed_verifier_audit_failed
managed_verifier_audit_failures: [exact stable failures]
```

LM8M must not silently rewrite contradictory acceptance as rejected. The
contradiction means the child accounting contract is broken.

## 13. LM8M Attempt Rows

LM8M preserves existing LM8J fields and adds:

```text
verifier_profile
verifier_mechanism
fixture_readiness_profile
readiness_wait_timeout_ms
child_attempt_timeout_s
readiness_wait_count
readiness_wait_status
readiness_failure_reason
fenced_output_read_count
settle_read_count
readiness_fenced
managed_verifier_audit_performed
managed_verifier_audit_valid
managed_verifier_audit_failures
receipt_id_hashes_match
document_session_ids_match
mutation_epochs_match
solution_run_epochs_match
post_mutation_solution_run_advanced
```

Receipt hashes and bounded provenance may be included. Raw receipt IDs are
forbidden.

Children that do not dispatch gh_set_value may have zero counts and audit
marked not applicable. A clean worker decline is not an invariant failure.

Every managed attempt row records the requested readiness timeout 10000 ms and
child process timeout 600 seconds.

## 14. LM8M Summary

LM8M retains terminal, worker, publication-support, action-value,
observed-output, child-directory, and leak accounting. It adds:

```text
verifier_profile
verifier_mechanism
fixture_readiness_profile
readiness_wait_timeout_ms
child_attempt_timeout_s
readiness_ready_count
readiness_failure_reason_counts
total_readiness_wait_count
total_fenced_output_read_count
total_settle_read_count
managed_verifier_audit_pass_count
managed_verifier_audit_failure_count
managed_verifier_invariant_violation_count
post_mutation_run_advance_failure_count
accepted_child_audit_contradiction_count
```

Readiness reason counts keep timeout, superseded, stale-run,
document-replaced, solver-locked, expired,
not-found-or-evicted-or-process-restarted, not-ready, unknown, malformed, and
missing-receipt outcomes distinct.

The summary continues to record worker_action_values,
observed_output_values_after, support counts, and leak_marker_match_count.

## 15. Success And Interpretation

LM8M canonical comparison success requires:

```text
scheduled_attempts == 20
accepted_count == 20
managed_verifier_audit_pass_count == 20
total_readiness_wait_count == 20
total_fenced_output_read_count == 20
total_settle_read_count == 0
accepted_child_audit_contradiction_count == 0
all worker action values == 3.0
all observed outputs == 7.5 within tolerance
leak_marker_match_count == 0
```

Publication support remains available but is not forced. Attempted and
recovered counts stay explicit. A support intervention does not change
verifier invariants, but must be disclosed in the A/B interpretation.

Reads:

```text
20/20 accepted with exact managed audits:
  Affine repeatability was preserved while settle polling was replaced by one
  authoritative wait and one fenced read.

readiness failures with correct child rejection:
  Product readiness/correlation evidence, not worker arithmetic evidence.

accepted child contradicted by artifacts:
  Wrapper error exposing a broken child accounting contract.

worker/publication failure before mutation:
  Worker-boundary evidence; managed verifier invariants do not apply.
```

Even a pass remains narrow: one affine fixture, one mutator, one worker model,
one scalar relationship, and no evidence for other mutators, Planner behavior,
worker topology authorship, or complexity scaling.

## 16. Artifact Safety

Managed artifacts must not persist:

- raw opaque receipt IDs
- unbounded LM8K tool results
- raw target GUIDs in decision, verifier, or wrapper artifacts
- hidden value 3.0 before worker authorship
- repair-era hidden markers

Receipt IDs use only canonical SHA-256 hashes. Existing trusted-GUID rules
remain unchanged. The report-only leak scan stays separate from managed audit.

## 17. Deterministic Proof Targets

### 17.1 Baseline preservation

Tests prove bare LM8I and LM8J retain:

- settle_v1 behavior
- existing gh_solve and bounded inspect sequence
- existing run prefixes
- existing schemas and summaries
- no managed-only artifacts or fields
- existing child command shape

### 17.2 Managed child flow

Fake-tool tests cover:

- pending receipt, ready wait, matching fenced read, accepted
- receipt hash continuity through all three stages
- no raw receipt ID in artifacts
- no gh_solve after worker mutation
- exactly one wait, one fenced read, and zero settle reads
- fixed timeout 10000
- ready-wait provenance used instead of pending run fields
- positive mutation epoch
- pending solution_run_epoch is null
- ready run strictly advances beyond pending completed_solution_run_epoch
- scalar match and mismatch
- missing and malformed receipts
- wrong receipt schema
- timeout with no follow-up calls
- superseded, stale-run, document-replaced, solver-locked, expired,
  not-found-or-evicted-or-process-restarted, not-ready, unknown, and
  wait-already-active outcomes
- fenced response without readiness_fenced true
- receipt hash, session, mutation epoch, and solution-run mismatches
- observed 7.5 with wrong provenance still rejected
- invariant failures record stable failures and actual counts
- pre-worker terminal outcomes make zero verifier calls

### 17.3 LM8M audit

Fake-child tests cover:

- accepted child with all exact managed artifacts
- accepted child missing each required artifact
- malformed JSON and wrong schemas
- wrong profile or timeout
- wrong wait/read/settle counts
- unfenced read
- scalar match with provenance mismatch
- scalar match with no post-mutation run advancement
- contradictory accepted child becomes wrapper_error
- properly rejected child remains rejected
- worker decline with zero calls is valid
- canonical predicate requires N=20, Gemma, managed profile, 10000 ms readiness
  timeout, and 600-second process timeout
- managed path writes lm8m identity and schemas
- default path retains lm8j identity and schemas
- summary counts and reason maps are exact

### 17.4 Drift guards

Static guards prove:

- no new LM8L or LM8M script
- no worker prompt/action changes
- no LM8K product-contract changes
- no fixture-readiness migration
- no managed fallback to settle reads
- no readiness-timeout override CLI in v1
- no raw receipt ID artifact field
- no retry, replacement, Planner, gh_edit, or support-forcing drift

## 18. Implementation And Evidence Sequence

```text
1. Review and approve this spec.
2. Write the implementation plan.
3. Implement deterministic profile and wrapper tests only.
4. Merge the deterministic implementation PR.
5. From synced main with Rhino/GH visibly ready, run one canonical LM8M N=20.
6. Inspect summary, attempts, and child managed stage artifacts.
7. Write a separate doc-only LM8M evidence summary PR.
```

No live run belongs in the implementation PR. Historical LM8J remains the A
baseline; the single post-merge LM8M N=20 run is the B sample.
