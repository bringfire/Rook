# LM9A-Kernel Final Review Fix Report

Date: 2026-07-14

Base commit: `e48832d55bfbf3e41452fa98ed597c730590720c`

Final status: `DONE`

## Scope And Contract Check

All seven review findings were independently reproduced against the live tree.
None conflicts with the frozen kernel design, frozen implementation plan, or the
semantic boundary specification. No narrower artifact was required.

The correction stays inside `mcp_server/src/rook/validation_kernel`, its
validation-kernel tests, shared validation-kernel fakes, and this report. It
adds no LM9A semantics, model behavior, live integration, dependency, registry,
plugin dispatch, or unrelated refactor. Frozen specs, the plan, dependency
files, and adjacent workflow implementation remain unchanged.

## Finding Results

### 1. Restricted schema admission can be forged

Status: `CONFIRMED`, corrected.

Verification: an `AdmittedSchema` assembled with `object.__new__` and a normally
forbidden `pattern` keyword sealed successfully. Forged
`local_reference_count` and `maximum_reference_depth` values also survived
composition.

RED:

```powershell
$env:PYTHONPATH='mcp_server/src;mcp_server/tests'
& 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server/tests/test_validation_kernel_schema_profile.py::test_admitted_schema_private_factory_requires_issuer_capability `
  mcp_server/tests/test_validation_kernel_program.py::test_program_seal_rejects_forged_schema_that_bypassed_profile_admission `
  mcp_server/tests/test_validation_kernel_program.py::test_program_seal_rederives_all_schema_reference_metadata -q
```

Result: exit 1, 4 failed. The private factory did not require an issuer and all
three forged candidates were accepted.

Correction:

- `AdmittedSchema._create` now requires a module-private issuer capability.
- Evaluation rejects values without that capability.
- Composition independently re-admits every schema with the exact fixed
  `PAYLOAD_PROFILE` or `CORE_PROFILE`.
- Composition compares the fingerprint, profile, node count, local-reference
  count, maximum reference depth, and exact owned value identity.

GREEN: the focused authority group passed 5 tests, including the fixed-budget
tests grouped with it, in 4.28 seconds. The final 613-test kernel gate also
passed.

### 2. Authenticated schema evidence can claim the wrong source

Status: `CONFIRMED`, corrected.

Verification: phase evaluation accepted an all-zero root fingerprint, a missing
pointer, a pointer to an equal-content wrong subtree, and a detached equal
instance. The audit retained the runner-authored false binding. The conformance
row builder also fingerprinted only the supplied instance and never resolved
the claimed root.

RED:

```powershell
$env:PYTHONPATH='mcp_server/src;mcp_server/tests'
& 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server/tests/test_validation_kernel_phase_engine.py::test_schema_helper_rejects_unresolved_or_mismatched_instance_binding `
  mcp_server/tests/test_validation_kernel_conformance.py::test_conformance_attempt_row_resolves_exact_root_pointer_and_instance -q
```

Result: exit 1, 5 failed. Four phase cases published accepted receipts and the
conformance helper lacked the required captured-root arguments.

Correction:

- Added one package-private, capability-issued resolved-binding proof.
- Phase evaluation searches only the captured immutable recipe and validation
  bundle roots and their parser-derived fingerprints.
- The resolver uses the shared RFC 6901 owned-value lookup, requires the
  selected object to be the exact evaluated object, and derives subtree
  fingerprint and node evidence inside the kernel.
- Binding resolution occurs before evaluator invocation, so invalid claims
  produce no shape receipt or audit entry.
- Conformance core cases pass the parsed immutable root and parser-derived root
  fingerprint through the same resolver.
- Final report evaluation reuses the canonical final bytes and non-circular
  report fingerprint rather than trusting projection-authored evidence.

GREEN: the combined phase, conformance, accounting, and report-audit group
passed 20 tests in 30.04 seconds. The final kernel gate and post-edit boundary
gate passed.

### 3. Program sealing accepts a budget invocation rejects

Status: `CONFIRMED`, corrected.

Verification: a self-consistent `synthetic.budget:v2` manifest sealed while
`_program_is_valid` rejected the resulting program. An equal-value copied LM9A
manifest also lacked the singleton authority required by `BudgetLedger`.

RED evidence is included in the 23-test complete focused RED run below. The
dedicated test observed both non-fixed candidates sealing.

Correction: `_validate_budget` now requires exact object identity with
`LM9A_BUDGET_MANIFEST` before validating its fixed values. Every successfully
sealed program therefore satisfies the invocation budget identity check.

GREEN: `test_program_seal_requires_the_exact_fixed_lm9a_budget_manifest`
passed, and `_program_is_valid(compose_and_seal_program(...))` is explicitly
asserted true.

### 4. Admitted `$ref` syntax and projection resolution disagree

Status: `CONFIRMED`, corrected.

Verification: admission accepted `/$defs/body`, but composition's report-path
resolver required a `#` prefix and rejected the same schema.

RED evidence is included in the complete focused RED run. The end-to-end test
failed during composition before report execution.

Correction:

- Removed the separate host-pointer implementation.
- Admission, composition, and report projection now use
  `lookup_json_pointer` over the exact owned schema root.
- `$ref` remains a raw RFC 6901 pointer.
- URI fragments remain rejected by admission and cannot resolve in composition.
- `$defs` is accepted as a non-evaluating sibling on a local reference node.

GREEN: the raw-pointer report schema composed and published successfully, 1
test passed in 1.59 seconds, and the final report fingerprint matched the
fingerprint projection.

### 5. Sealed runtime bindings differ from invoked implementations

Status: `CONFIRMED`, corrected.

Verification: the standard contribution sealed fake tokenizer, parser,
canonicalizer, and ledger targets while invocation directly instantiated
`BudgetLedger` and called the production parser.

RED evidence is included in the complete focused RED run. The fixed-target
test found `fake_tokenizer`, and the invocation binding spy recorded no parser
or ledger lookup.

An additional self-review RED was run after accounting implementation:

```powershell
$env:PYTHONPATH='mcp_server/src;mcp_server/tests'
& 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server/tests/test_validation_kernel_program.py::test_kernel_owned_runtime_profile_is_fixed_to_invoked_implementations -q
```

Result: exit 1, 1 failed. The profile still bound
`canonical_fingerprint` while parsing invoked
`canonical_fingerprint_metered`.

Correction:

- The fixed program derives one parser profile from the production
  `parse_owned_json`, `canonical_fingerprint_metered`, and
  `create_budget_ledger` functions.
- Candidate parser profiles must equal that fixed declaration; their ABI or
  component identity cannot vary independently.
- Invocation resolves the ledger factory and parser from the immutable sealed
  binding map and invokes those exact targets.
- Tokenizer and parser declarations both bind the production parse entrypoint,
  which owns the integrated bounded tokenizer/parser implementation.
- No registry, plugin architecture, or candidate-selected dispatch was added.

GREEN: the corrected runtime/accounting group passed 4 tests in 2.17 seconds.
The final 613-test gate proves the sealed fingerprint and runtime behavior move
together.

### 6. Canonical fingerprint work is omitted from accounting

Status: `CONFIRMED`, corrected.

Verification: parsing `null` consumed 3 parser work units instead of 4. A phase
schema helper call consumed 7 units while its canonical instance hash was
unmetered, and repeating the evaluation repeated unaccounted work.

RED evidence is included in the complete focused RED run. Exact parser and
phase counts, inclusive 64/65-byte boundaries, and repeated evaluations all
failed at their expected assertions.

Correction:

- Added streaming `canonical_fingerprint_metered` accounting.
- The hash sink reserves each newly started 64-byte canonical output block
  before hashing that block.
- Parser fingerprints charge `parser_work_units` with artifact role `combined`.
- Phase source evidence charges `kernel_phase_work_units` for source lookup,
  pointer lookup, and each canonical block.
- Repeated evaluations recompute and recharge their full fingerprint evidence.
- Report audits reuse the already metered second canonical serialization. On a
  final-schema rejection, the second canonical pass still occurs, preserving
  the frozen two-pass non-circular seal and avoiding an unmetered third hash.

Focused GREEN results:

- parser accounting: 4 passed in 0.24 seconds;
- source/accounting/report group: 20 passed in 30.04 seconds;
- complete accepted-finding focus set: 33 passed in 37.36 seconds.

### 7. Package root exports internal construction stages

Status: `CONFIRMED`, corrected.

Verification: package `__all__` and package attributes exposed
`ReportBuilder`, `ReportProjectionEnvelope`, `parse_owned_json`,
`execute_phase_program`, and `seal_validation_report`.

RED evidence is included in the complete focused RED run. Both exact public
surface and forbidden-authority tests failed.

Correction: removed only those five names from package imports and `__all__`.
Internal tests import stages from their implementation modules. Public value
types and stable composition, validation, trust-carrier, and conformance APIs
remain available.

GREEN: 2 focused boundary tests passed in 0.35 seconds; the final post-edit
boundary module passed 19 tests in 45.14 seconds.

## Complete RED Evidence

After all seven regression groups were written and before production edits, the
combined focused command selected the new schema, program, invocation, phase,
conformance, reporting, parser, and boundary nodes:

```powershell
$env:PYTHONPATH='mcp_server/src;mcp_server/tests'
& 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server/tests/test_validation_kernel_schema_profile.py::test_admitted_schema_private_factory_requires_issuer_capability `
  mcp_server/tests/test_validation_kernel_program.py::test_program_seal_rejects_forged_schema_that_bypassed_profile_admission `
  mcp_server/tests/test_validation_kernel_program.py::test_program_seal_rederives_all_schema_reference_metadata `
  mcp_server/tests/test_validation_kernel_program.py::test_program_seal_requires_the_exact_fixed_lm9a_budget_manifest `
  mcp_server/tests/test_validation_kernel_program.py::test_kernel_owned_runtime_profile_is_fixed_to_invoked_implementations `
  mcp_server/tests/test_validation_kernel_invocation.py::test_invocation_resolves_the_sealed_fixed_ledger_and_parser_bindings `
  mcp_server/tests/test_validation_kernel_phase_engine.py::test_schema_helper_rejects_unresolved_or_mismatched_instance_binding `
  mcp_server/tests/test_validation_kernel_conformance.py::test_conformance_attempt_row_resolves_exact_root_pointer_and_instance `
  mcp_server/tests/test_validation_kernel_reporting.py::test_raw_rfc6901_report_schema_reference_composes_and_publishes `
  mcp_server/tests/test_validation_kernel_parser.py::test_shared_parser_work_budget_counts_blocks_tokens_nodes_and_attachments `
  mcp_server/tests/test_validation_kernel_parser.py::test_parser_work_counts_started_raw_blocks_and_structural_attachments_exactly `
  mcp_server/tests/test_validation_kernel_parser.py::test_parser_fingerprint_charges_each_started_canonical_output_block `
  mcp_server/tests/test_validation_kernel_phase_engine.py::test_schema_helper_success_charges_exact_source_and_canonical_work `
  mcp_server/tests/test_validation_kernel_phase_engine.py::test_schema_helper_repeated_evaluation_charges_canonical_work_again `
  mcp_server/tests/test_validation_kernel_phase_engine.py::test_schema_helper_canonical_work_has_an_inclusive_64_byte_boundary `
  mcp_server/tests/test_validation_kernel_boundaries.py::test_package_exports_are_exactly_the_reviewed_public_surface `
  mcp_server/tests/test_validation_kernel_boundaries.py::test_public_surface_cannot_retrieve_private_kernel_authority -q
```

Result: exit 1, 23 failed in 25.06 seconds. Every failure was the expected
missing behavior; there were no collection or setup errors.

The report-seal reuse consequence was separately pinned before implementation:

```powershell
& 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server/tests/test_validation_kernel_reporting.py::test_final_report_uses_exact_admitted_schema_evaluator_and_publishes_nothing_on_failure -q
```

Result: exit 1, 10 failed in 14.81 seconds because schema-invalid reports made
only one canonical pass instead of reusing the required second pass for audit
identity.

## Final Verification

### Focused accepted-finding tests

The complete focused selection above, with the report-seal test included after
implementation, passed:

```text
33 passed in 37.36s
```

The final exact canonicalizer-binding correction then passed its parser,
invocation, and program targets:

```text
4 passed in 2.17s
```

### Every validation-kernel test

```powershell
$env:PYTHONPATH='mcp_server/src;mcp_server/tests'
$kernelTests = Get-ChildItem -LiteralPath mcp_server/tests -Filter 'test_validation_kernel_*.py' | Sort-Object FullName | Select-Object -ExpandProperty FullName
& 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe' -m pytest @kernelTests -q
```

Final result: exit 0, `613 passed in 379.77s`.

An earlier discovery run produced `611 passed, 2 failed in 385.67s`. Both
failures were stale tests: one monkeypatched the removed direct parser symbol,
and one exact import list omitted `collections.abc.Callable`. They were updated
to assert sealed parser dispatch and the narrow canonicalizer import boundary;
both targeted tests then passed before the authoritative full rerun.

### Boundary module after final edits

```powershell
& 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server/tests/test_validation_kernel_boundaries.py -q
```

Result: exit 0, `19 passed in 45.14s`.

### Adjacent Task 11 regressions

```powershell
& 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe' -m pytest `
  mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py `
  mcp_server/tests/test_plan_graph_workflow_contract.py `
  mcp_server/tests/test_workflow_validate.py `
  mcp_server/tests/test_planner_worker_contract_request.py -q
```

Result: exit 0, `148 passed in 0.38s`.

### JCS vectors

```powershell
node mcp_server/tests/fixtures/validation_kernel/generate_jcs_number_vectors.mjs --check
```

Result: exit 0, no output, no generated drift.

### Static and scope gates

```powershell
& 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe' -m compileall -q mcp_server/src/rook/validation_kernel
git diff --check
rg -n 'TO[D]O|FI[X]ME|T[B]D|pass$|Not[I]mplementedError' mcp_server/src/rook/validation_kernel mcp_server/tests -g 'test_validation_kernel_*.py'
rg -n -i 'radial|box array|grid spacing|grasshopper|rhino|ollama|worker model|gh_edit' mcp_server/src/rook/validation_kernel
```

Results:

- compileall: exit 0;
- `git diff --check`: exit 0;
- allowed-scope check: exit 0, only the 20 implementation/test files below
  plus this report;
- incomplete-marker scan: exit 1 from `rg`, meaning no matches;
- semantic-leak scan: exit 1 from `rg`, meaning no matches.

Git emitted Windows autocrlf warnings that LF would be replaced by CRLF if Git
rewrites the working-copy files. `git diff --check` remained clean; no line
ending or whitespace content was changed solely to suppress those warnings.

## Changed Files

Production:

- `mcp_server/src/rook/validation_kernel/__init__.py`
- `mcp_server/src/rook/validation_kernel/budget.py`
- `mcp_server/src/rook/validation_kernel/canonical_json.py`
- `mcp_server/src/rook/validation_kernel/conformance.py`
- `mcp_server/src/rook/validation_kernel/invocation.py`
- `mcp_server/src/rook/validation_kernel/parser.py`
- `mcp_server/src/rook/validation_kernel/phase_engine.py`
- `mcp_server/src/rook/validation_kernel/program.py`
- `mcp_server/src/rook/validation_kernel/reporting.py`
- `mcp_server/src/rook/validation_kernel/schema_profile.py`

Tests:

- `mcp_server/tests/_validation_kernel_fakes.py`
- `mcp_server/tests/test_validation_kernel_api.py`
- `mcp_server/tests/test_validation_kernel_boundaries.py`
- `mcp_server/tests/test_validation_kernel_conformance.py`
- `mcp_server/tests/test_validation_kernel_invocation.py`
- `mcp_server/tests/test_validation_kernel_parser.py`
- `mcp_server/tests/test_validation_kernel_phase_engine.py`
- `mcp_server/tests/test_validation_kernel_program.py`
- `mcp_server/tests/test_validation_kernel_reporting.py`
- `mcp_server/tests/test_validation_kernel_schema_profile.py`

Report:

- `.superpowers/sdd/final-review-fix-report.md`

## Concerns

None. All findings are corrected without a frozen-contract conflict, all
required gates pass, and the final change set remains within the allowed scope.
