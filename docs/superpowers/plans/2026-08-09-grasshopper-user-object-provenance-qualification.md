# Grasshopper User-Object Provenance Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for Inline Execution, implementing this plan task-by-task and stopping at every review gate. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture one bounded, metadata-only Grasshopper qualification that determines which host-owned identity and provenance fields are available for six already-retained `.ghuser` component types.

**Architecture:** A disposable Python probe runs once through Rook's existing `/execute` endpoint. It resolves six exact proxies, observes their user-object and base-assembly metadata without inserting anything into the canvas, writes one compact create-new artifact, and prints a hash-bound sentinel. A PowerShell launcher owns target/listener custody and separately retains the exact outer response. No production module changes.

**Tech Stack:** Python 3.11, Python.NET, Grasshopper 1.0 SDK, PowerShell 7, Rook's deployed `/execute` endpoint, `unittest`, SHA-256 JSON evidence.

## Global constraints

- Production code, prompts, schemas, endpoints, and tools remain unchanged.
- The disposable root is exactly `C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification`.
- No Rhino, Grasshopper, MCP, model, or provider contact occurs in Task 1.
- Task 2 may perform discovery/listener corroboration only; it must not call `/execute`.
- Task 3 consumes exactly one separately authorized `/execute` request. There is no rerun, retry, fallback, cleanup, search, or second host call.
- The six selectors, order, retained paths, and source-evidence hash remain exact.
- The probe continues after specimen-local failures and reports them; it never substitutes a selector or lookup path.
- Raw `GH_UserObject.Data` bytes never enter an evidence payload, log, exception, or test diagnostic.
- The implementation stops if it needs archive parsing, inferred package identity, product changes, another host request, a registry, or canvas mutation.
- All operator-owned fallible preparation completes before `/execute`.
- Probe-local repository preparation occurs immediately after entry and before Rhino/Grasshopper imports, target access, or specimen operations.
- Representable specimen observations accumulate monotonically: later projection failures append errors and mark incompleteness without replacing earlier fields. Artifact serialization or writing may still leave only an unsuccessful evidence prefix; no fallback artifact is permitted.
- Do not amend the production discovery specification until Task 3 evidence has been independently reviewed.

## File map

Repository files:

- Create: `docs/superpowers/plans/2026-08-09-grasshopper-user-object-provenance-qualification.md`
- Create after the authorized capture: `docs/superpowers/reports/2026-08-09-grasshopper-user-object-provenance-qualification.md`
- Modify during execution: this plan's ledger only.

Disposable files:

- Create: `C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/probe.py`
- Create: `C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/run.ps1`
- Create: `C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/test_probe.py`
- Create: `C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/manifest.json`
- Create in Task 2: `C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/target.json`
- Produced once in Task 3: `user-object-provenance.json`, `invoke-result.json`, and `stderr.txt`

---

## Task 1: Build and inertly qualify the disposable lane

**Files:**

- Create: `C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/test_probe.py`
- Create: `C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/probe.py`
- Create: `C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/run.ps1`
- Create: `C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/manifest.json`
- Modify: `docs/superpowers/plans/2026-08-09-grasshopper-user-object-provenance-qualification.md`

### Step 1: Create the fresh lane and write failing contract tests

- [ ] Confirm the disposable root does not exist. If it exists, stop; do not reuse or erase it.
- [ ] Create only the root and `test_probe.py`.
- [ ] In `test_probe.py`, load `probe.py` without importing Rhino or Grasshopper. Inject causal fake component-server, proxy, user-object, instance, assembly-info, document, writer, and launcher boundaries.
- [ ] Add these exact test groups and cases:

```text
FrozenSpecimenTests
  test_prior_artifact_hash_is_exact
  test_six_ordered_guid_path_pairs_match_prior_artifact

ProjectionSchemaTests
  test_exact_top_level_and_nested_key_sets
  test_description_projection_is_closed
  test_unexpected_text_type_records_property_error_and_is_incomplete
  test_exposure_numeric_failure_is_explicit_and_incomplete
  test_assembly_projection_uses_direct_assembly_description
  test_reflection_objects_never_reach_json

DataProjectionTests
  test_null_data_is_complete
  test_byte_array_records_only_type_length_and_hash
  test_unexpected_data_type_records_only_type_name_and_is_incomplete
  test_not_observed_data_is_incomplete

IdentityCustodyTests
  test_happy_specimen_uses_exact_proxy_once
  test_guid_mismatch_refuses_specimen
  test_kind_mismatch_refuses_specimen
  test_normalized_path_mismatch_refuses_specimen
  test_base_guid_and_component_guid_are_observed_without_equality_rule

AssemblyObservationTests
  test_proxy_guid_and_instance_overloads_are_recorded_separately
  test_found_and_not_found_are_complete
  test_assembly_error_is_incomplete
  test_author_contact_description_and_assembly_description_are_exact

PrefixAndBudgetTests
  test_one_specimen_failure_does_not_stop_other_five
  test_any_incomplete_specimen_forces_probe_incomplete
  test_canvas_mismatch_forces_probe_incomplete
  test_budget_mismatch_forces_probe_incomplete
  test_no_search_insert_solution_retry_or_cleanup_is_reachable

PhaseOrderingTests
  test_repository_failure_precedes_all_host_operations
  test_document_mismatch_consumes_entry_but_zero_specimen_operations
  test_data_hash_failure_preserves_prior_fields_and_continues
  test_returned_envelope_refusal_preserves_one_shot_prefix

WriterTests
  test_full_write_flush_fsync_precede_sentinel
  test_serialization_failure_emits_no_sentinel
  test_open_failure_emits_no_sentinel
  test_short_write_emits_no_sentinel
  test_flush_or_fsync_failure_emits_no_sentinel
  test_sentinel_hashes_exact_encoded_artifact

LauncherTests
  test_target_requires_exact_int64_shape
  test_manifest_accepts_exact_three_entry_pre_target_phase
  test_manifest_accepts_exact_four_entry_post_target_phase
  test_evidence_exists_refuses_before_transport
  test_invalid_target_refuses_before_transport
  test_outer_envelope_requires_zero_created_objects
  test_outer_envelope_requires_exact_sentinel_and_hash
  test_stderr_marker_precedes_the_only_post
```

- [ ] Make the unexpected-text regression causal with a non-string sentinel whose `__str__` and `__repr__` fail if invoked; assert one property error, an incomplete specimen, and zero coercion calls.
- [ ] Make serialization- and open-failure writer regressions inject failures before any artifact bytes exist; assert no sentinel, no reopen, and no retry.
- [ ] Make the tests import the exact Task 0 V2 source artifact and assert SHA-256 `254A9BF5A8EEE5DCCA72A37AD08DF20EDF63271F55E2F14AC4587BC180481988` before extracting the six frozen selector records.
- [ ] Run the direct test-file command and confirm RED because `probe.py` and `run.ps1` do not exist:

```powershell
$Python = 'C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe'
$Root = 'C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification'
& $Python "$Root/test_probe.py" -v
```

Expected: test failure caused only by the absent implementation artifacts.

### Step 2: Implement the closed probe projections

- [ ] Create `probe.py` with inert imports at module load. Import `clr`, `System`, Rhino, and Grasshopper only inside the authorized `main()` path.
- [ ] Define immutable constants for the source artifact, its hash, the six ordered selectors, the schema string, artifact path, and every closed key set.
- [ ] Use these exact projection owners:

```python
def _strict_text(
    value: object | None,
    property_name: str,
    property_errors: list[dict],
) -> tuple[str | None, bool]: ...
def _stage_error(stage: str, exc: BaseException | None = None, message: str | None = None) -> dict | None: ...
def _property_error(property_name: str, exc: BaseException) -> dict: ...
def _normalize_path(value: str) -> str: ...
def _paths_equal(left: str, right: str) -> bool: ...
def _description_projection(description: object | None) -> tuple[dict, bool]: ...
def _data_projection(value: object, observed: bool) -> tuple[dict, bool]: ...
def _assembly_projection(info: object | None, attempted: bool) -> tuple[dict, bool]: ...
def _instance_projection(instance: object | None, attempted: bool) -> tuple[dict, bool]: ...
def _observe_specimen(server: object, selector: dict, counters: dict, host: object) -> dict: ...
```

- [ ] `_strict_text()` accepts only `None` or an actual Python `str`. `None` returns `(None, True)`. A `str` must be strictly UTF-8 encodable and returns unchanged with `True`. Any other type or UTF-8 encoding failure appends one closed `propertyErrors` entry, returns `(None, False)`, and makes the containing specimen incomplete. It must never call `str()`, `repr()`, reflection, or serialization on an unexpected value.
- [ ] Keep every projection schema literal and closed. Reject or convert no arbitrary reflection object through generic JSON serialization.
- [ ] Project every description as exactly:

```text
name, nickName, description, category, subCategory, keywords, propertyErrors
```

- [ ] Project assembly evidence as exactly:

```text
status,
id, name, version, authorName, authorContact, description,
assemblyName, assemblyVersion, assemblyDescription, isCoreLibrary,
location, loadingMechanism,
runtimeAssemblyName, runtimeAssemblyFullName,
runtimeAssemblyVersion, runtimeAssemblyLocation,
propertyErrors, error
```

- [ ] Read `GH_AssemblyInfo.AssemblyDescription` directly. Do not use attributes or custom reflection.
- [ ] Implement `Data` projection with exactly these branches:

```python
if not observed:
    return not_observed_record, False
if value is None:
    return null_record, True
if value.GetType().FullName == "System.Byte[]":
    return injected_byte_length_and_sha_projection(value)
return unexpected_type_record_with_only_runtime_type, False
```

- [ ] Inject one live .NET-owned `System.Byte[]` projector using `LongLength` plus `System.Security.Cryptography.SHA256`; do not rely solely on Python `bytes(value)` projection.
- [ ] If length or hashing fails after the runtime type is observed, retain `status=bytes` and `runtimeType=System.Byte[]`, leave length/hash null, append one `Data` property error to the user-object block, preserve Path/BaseGuid/Description, mark the specimen incomplete, and continue later observations and specimens.
- [ ] Raw byte content exists only inside the hashing operation and is never returned, logged, serialized, or placed in an exception.

### Step 3: Implement exact specimen observation and budget custody

- [ ] Collect repository identity before importing Rhino or Grasshopper and before any host-dependent operation. A repository collection failure performs zero host operations.
- [ ] Implement `_observe_specimen()` with this sole lookup sequence:

```text
server.EmitObjectProxy(Guid(selector.guid))
-> verify selector GUID == proxy GUID
-> verify proxy Kind == UserObject
-> verify normalized retained path == normalized proxy Location
-> GH_UserObject(proxy.Location)
-> verify normalized proxy Location == normalized GH_UserObject.Path
-> project user object and Data
-> server.FindAssemblyByObject(Guid(selector.guid))
-> proxy.CreateInstance() exactly once
-> project temporary instance
-> server.FindAssemblyByObject(instance)
-> drop temporary references
```

- [ ] Never call `CreateComponentFromGuid`, `EmitObject`, `FindObjects`, `ObjectProxies`, canvas insertion, document solution, or a fallback path.
- [ ] Record `BaseGuid` and instance `ComponentGuid` independently without requiring equality.
- [ ] Preserve downstream blocks with `not_attempted` after a prerequisite failure.
- [ ] Catch specimen-local property, construction, and assembly-observation failures, retain their exact closed errors, mark that specimen incomplete, and continue to the next selector.
- [ ] Count every budgeted operation at delegate ingress so an exception remains an observed attempted call.
- [ ] Compute `probeComplete` only from:

```text
all six specimens complete
AND exact closed-budget equality
AND objectCountBefore == objectCountAfter
```

### Step 4: Implement create-new artifact custody

- [ ] Build the payload with exactly:

```text
schema, capturedAtUtc, repository, sourceEvidence, target,
canvas, budget, specimens, probeComplete
```

- [ ] Strictly UTF-8 encode compact deterministic JSON, compute its SHA-256, open `user-object-provenance.json` in exclusive create mode, require a full write, flush, and call `os.fsync()`.
- [ ] Only after successful fsync, print:

```text
ROOK_GHUSER_PROVENANCE_OK <UPPERCASE_SHA256>\n
```

- [ ] On serialization, open, short-write, flush, or fsync failure, print no success sentinel and perform no repair, reopen, or retry.

### Step 5: Implement the one-shot launcher

- [ ] Adapt only the reviewed Task 0 V2 launcher custody pattern into `run.ps1`.
- [ ] Require one `-TargetPath` and optional `-ValidateTargetOnly`. Allow no individual target overrides.
- [ ] Strictly decode `target.json` with exact keys and exact `[long]` values:

```text
process_id: positive Int64 <= UInt32.MaxValue
port: positive Int64 <= UInt16.MaxValue
document_serial_number: positive Int64 <= UInt32.MaxValue
```

- [ ] Verify manifest source hashes before any evidence creation or transport. Accept exactly three manifest entries before Task 2 and exactly four afterward; the only fourth entry is `target.json`.
- [ ] Refuse if any of `user-object-provenance.json`, `invoke-result.json`, or `stderr.txt` exists.
- [ ] Use Rook discovery plus `Get-NetTCPConnection` to prove the reviewed PID owns the reviewed native port. Current discovery does not expose document serial.
- [ ] Preserve the frozen document serial in the request. The probe checks it immediately inside `/execute`, after local repository preparation and before canvas/component-server access or any specimen operation.
- [ ] In validation-only mode, stop after custody checks with zero `/execute` calls and zero evidence files.
- [ ] In live mode, create empty `stderr.txt` exclusively immediately before the sole `PostAsync`, then retain the HTTP status plus exact response body in create-new `invoke-result.json` before interpreting it.
- [ ] Enforce these truthful boundaries:

```text
PID/port/listener mismatch -> zero /execute calls
document mismatch -> one unsuccessful /execute and zero specimen operations
```
- [ ] Require the outer result equation:

```text
HTTP 200
AND body.success == true
AND body.data.output == sentinel + "\n"
AND body.data.stderr == ""
AND body.data.objectsCreated == 0
AND body.data.objectIds == []
AND sentinel SHA-256 == independently computed artifact SHA-256
```

- [ ] Never issue a second request. A failed equation is an honest unsuccessful qualification with retained evidence.

### Step 6: Run inert and reflection verification

- [ ] Run all causal tests:

```powershell
& 'C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe' 'C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/test_probe.py' -v
```

- [ ] Compile the disposable Python files:

```powershell
& 'C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe' -m py_compile `
  'C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/probe.py' `
  'C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/test_probe.py'
```

- [ ] Perform no-contact CLR reflection against the installed assemblies and record the exact installed signatures/types for:

```text
GH_ComponentServer.EmitObjectProxy(System.Guid)
GH_ComponentServer.FindAssemblyByObject(System.Guid)
GH_ComponentServer.FindAssemblyByObject(IGH_DocumentObject)
GH_UserObject(System.String)
GH_UserObject.Data == System.Byte[]
GH_AssemblyInfo.AssemblyDescription == System.String
```

- [ ] The reflection check may load assemblies from disk but must not initialize Rook, discover a Rhino target, or call the host.
- [ ] Write `manifest.json` with exactly the uppercase SHA-256 values for `probe.py`, `run.ps1`, and `test_probe.py`.
- [ ] Rerun the tests after manifest creation and prove `target.json` and all evidence files are absent.
- [ ] Run the focused repository baseline:

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest `
  'mcp_server/tests/test_server_component_deprecation.py' -q
git diff --check
```

Expected: the known four focused tests pass; no production file changes.

### Step 7: Reconcile, commit, and stop for mandatory pre-contact review

- [ ] Add Task 1 results and every disposable hash to the ledger below.
- [ ] Commit only the plan ledger update in Git; disposable artifacts remain outside both repositories.

```powershell
git add docs/superpowers/plans/2026-08-09-grasshopper-user-object-provenance-qualification.md
git commit -m "docs: prepare user object provenance probe"
```

- [ ] Stop for independent review. Report test count, reflection results, all three manifest hashes, source-evidence hash, absent target/evidence, exact Git scope, and worktree status.
- [ ] Do not begin Task 2 until Task 1 is independently approved.

---

## Task 2: Freeze one target and stop for authorization

**Files:**

- Create: `C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/target.json`
- Modify: `C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/manifest.json`
- Modify: `docs/superpowers/plans/2026-08-09-grasshopper-user-object-provenance-qualification.md`

### Step 1: Corroborate the fresh target without `/execute`

- [ ] Require a disposable Grasshopper document and an open Rook Chat panel.
- [ ] Use existing process discovery and OS listener inspection to obtain one exact Rhino PID and native port. Obtain the intended document serial from the open Rook Chat panel/document record; do not claim native discovery corroborates it.
- [ ] Confirm the listener owner PID equals the selected Rhino PID. Record the exact intended document serial for the first in-probe admission check.
- [ ] Confirm no probe evidence exists and the Git worktree is clean.

### Step 2: Create and hash the closed target

- [ ] Create `target.json` through `apply_patch` with exactly:

```json
{
  "process_id": 12345,
  "port": 54321,
  "document_serial_number": 268435457
}
```

Replace the illustrative positive integers with the corroborated values in the same edit; never write a zero or placeholder target.

- [ ] Add only `target.json` and its uppercase SHA-256 to `manifest.json`. Do not alter any reviewed source file or its hash.

### Step 3: Re-run the inert seam and validate custody only

- [ ] Run the direct test file, Python compilation, all manifest checks, and:

```powershell
& 'C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/run.ps1' `
  -TargetPath 'C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/target.json' `
  -ValidateTargetOnly
```

- [ ] Confirm zero `/execute` requests and absence of `user-object-provenance.json`, `invoke-result.json`, and `stderr.txt`.
- [ ] Record the exact target values, target SHA-256, four manifest hashes, test count, and validation result in the ledger.
- [ ] Commit the ledger update only and stop.

```powershell
git add docs/superpowers/plans/2026-08-09-grasshopper-user-object-provenance-qualification.md
git commit -m "docs: freeze user object provenance target"
```

- [ ] Request authorization in this exact bounded form:

```text
I authorize exactly one read-only user-object provenance qualification using frozen target <UPPERCASE_TARGET_SHA256>. No model call, canvas mutation, search, operator rerun, adapter retry, second /execute request, cleanup, or additional host call is authorized.
```

---

## Task 3: Execute once, review offline, and report

**Files:**

- Produce once: `C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/user-object-provenance.json`
- Produce once: `C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/invoke-result.json`
- Produce once: `C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/stderr.txt`
- Create: `docs/superpowers/reports/2026-08-09-grasshopper-user-object-provenance-qualification.md`
- Modify: `docs/superpowers/plans/2026-08-09-grasshopper-user-object-provenance-qualification.md`

### Step 1: Recheck the authorized boundary

- [ ] Confirm the authorization names the exact current target SHA-256.
- [ ] Reverify all four manifest entries, PID/port/listener custody, the frozen document serial value, absent evidence, source-evidence hash, clean Git worktree, and unchanged probe/test/launcher hashes. Do not claim external document-serial corroboration.
- [ ] Stop without contact on any mismatch.

### Step 2: Make the sole authorized request

- [ ] Run the launcher exactly once:

```powershell
& 'C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/run.ps1' `
  -TargetPath 'C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification/target.json'
```

- [ ] Do not rerun regardless of exit status, missing artifact, incomplete specimen, malformed envelope, or hash mismatch.
- [ ] Preserve all produced bytes unchanged. Do not repair or clean the disposable canvas.

### Step 3: Verify the retained evidence without host contact

- [ ] Strictly parse the compact artifact and outer invocation record from disk with duplicate-key rejection and strict UTF-8.
- [ ] Independently recompute all hashes and verify the full outer equation, exact schemas, six-entry order, identity equations, budget, and canvas equality.
- [ ] Report both assembly observations for every selector separately. Do not infer package identity from folder names, proxy GUIDs, `BaseGuid`, instance type, or base assembly.
- [ ] Treat `not_found` as complete host evidence and property/lookup/construction errors as incomplete evidence exactly as specified.
- [ ] Choose exactly one evidence conclusion:

```text
qualification incomplete
identity handoff closed with one shared provenance shape
identity handoff closed with source-kind-specific provenance variants
```

The conclusion is descriptive evidence for later specification work, not product behavior.

### Step 4: Write the bounded report

- [ ] Create the report with only these sections:

```text
Purpose and authorization
Artifacts and SHA-256 values
Target, call budget, and canvas equality
Six ordered specimen outcomes
Observed identity relationships
Proxy-GUID and temporary-instance assembly results
Available and unavailable provenance fields
Identity-handoff decision
Claims and non-claims
Next gate
```

- [ ] Explicitly state that the probe qualifies metadata available for a future endpoint and does not prove current `/gh/batch-component-info` output exposes it.
- [ ] Record that no package/author/family/version identity beyond direct host evidence is inferred.
- [ ] Record the unsuccessful prefix truthfully if the request, artifact, or correlation is incomplete. Do not fabricate missing rows or make another call.

### Step 5: Final verification, ledger reconciliation, and stop

- [ ] Run:

```powershell
git diff --check
git status --short --branch
git diff --name-only a867f8e06ae8aca904102104c47780d02d5640b8...HEAD
```

- [ ] Confirm no production file changed and no host contact occurred after the one request.
- [ ] Record final hashes, exact call counts, completeness, report path, and Git state in the ledger.
- [ ] Commit only the report and ledger update:

```powershell
git add `
  docs/superpowers/reports/2026-08-09-grasshopper-user-object-provenance-qualification.md `
  docs/superpowers/plans/2026-08-09-grasshopper-user-object-provenance-qualification.md
git commit -m "docs: record user object provenance qualification"
```

- [ ] Stop for independent evidence review. Do not amend the discovery specification or write a production implementation plan until that review approves the identity-handoff conclusion.

---

## Evidence ledger

```text
Baseline origin/main:
  a867f8e06ae8aca904102104c47780d02d5640b8

Approved specification commits:
  50e93811 docs: design user object provenance qualification
  1aebe9b9 docs: close provenance evidence custody
  904d06b8 docs: pin user object transport evidence

Authoritative source evidence:
  C:/Users/bring/AppData/Local/Temp/rook-gh-native-discovery-task0-v2/native-discovery.json
  SHA-256 254A9BF5A8EEE5DCCA72A37AD08DF20EDF63271F55E2F14AC4587BC180481988

Task 1 disposable construction:
  prepared for mandatory independent review
  disposable root:
    C:/Users/bring/AppData/Local/Temp/rook-gh-user-object-provenance-qualification
  TDD RED:
    missing probe.py refused test import as intended
    six phase-ordering/projection regressions failed against the first frozen sources
  reviewed Task 1 repair:
    repository preparation precedes host access
    document mismatch admits zero specimen operations
    Data hashing failure preserves prior observations and later specimens
    returned-envelope refusal preserves invoke-result prefix
    stderr marker precedes the sole PostAsync
    exposure conversion and prohibited surfaces are causal
  inert seam:
    44/44 passed
  Python compilation:
    passed for probe.py and test_probe.py
  PowerShell parser:
    passed for run.ps1
  manifest phase:
    pre_target
  source files:
    probe.py      1CC562EE8CFADA09D26D27426015B6C856D69593D71982D510107F67ACA50B67
    run.ps1       FB15B1451D3CE408E19A5D4296152E2CCB1096C5D2AB00F3DFF98856928745A2
    test_probe.py B3D1EAACEEF3B01807C21257C112D9A5CD6D879DC40F3517DEFBACC0A5F9968F
    manifest.json 751EF9D1E6CB67210EB1FEA1BA3F85EA0FF11160A4EF1640856DB4631E155FD5
  installed reflection:
    EmitObjectProxy(System.Guid) -> IGH_ObjectProxy
    FindAssemblyByObject(System.Guid) -> GH_AssemblyInfo
    FindAssemblyByObject(IGH_DocumentObject) -> GH_AssemblyInfo
    GH_UserObject constructors include System.String
    GH_UserObject.Data -> System.Byte[]
    GH_AssemblyInfo.AssemblyDescription -> System.String
  focused repository baseline:
    4 passed, 11 existing warnings
  target and live evidence:
    absent
  external contact:
    none

Task 1 mandatory independent review:
  approved with no P0-P2 findings
  independent inert seam: 44/44 passed
  source hashes and worktree independently verified

Task 2 frozen target:
  corroborated without /execute:
    Rhino PID: 38672
    native port: 55902
    listener owner PID: 38672
    document serial: 268435457
    document serial custody: exact Rook Chat panel confirmation from the operator
  target.json SHA-256:
    63CE846465A22E03BD1DE9BCB074B3FA9E5A34FCA68BA5A2F619718EBBFE392A
  post-target manifest:
    exactly four entries; all hashes matched
    manifest.json SHA-256:
      0B0604E0B84A46EF109357C67FCA04AEA85834ED6649386F5E86008C45980027
  reviewed source hashes:
    unchanged from Task 1
  inert seam:
    44/44 passed
  Python compilation and PowerShell parser:
    passed
  validation-only launcher:
    exit 0; exact output `validated`
  live evidence:
    absent
  /execute calls:
    zero

Task 2 one-shot authorization:
  exact frozen-target authorization received
  authorized target SHA-256:
    63CE846465A22E03BD1DE9BCB074B3FA9E5A34FCA68BA5A2F619718EBBFE392A
  prohibitions retained:
    no model call, mutation, search, rerun, retry, second /execute, cleanup, or additional host call

Task 3 authorized /execute:
  launcher invocations: 1
  /execute requests: 1
  launcher exit: 0
  launcher output:
    completed C:\Users\bring\AppData\Local\Temp\rook-gh-user-object-provenance-qualification\user-object-provenance.json
  retained artifacts:
    user-object-provenance.json
      72D734E11E9E7CC1408020C7DA2CFD42F89712750713025D41C952BB22E4FB26
    invoke-result.json
      496BCD9A304C1E52B18A0A1EE5D16BDA734856C743F159BAFBF0DA4751CE17EB
    stderr.txt (empty)
      E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855
  outer transport:
    HTTP 200; success true; exact sentinel/hash correlation passed
    stderr empty; objectsCreated 0; objectIds empty
  call budget:
    exact reviewed budget matched
    six proxy emissions, constructions, temporary instances, and both assembly lookups
    two canvas count reads
    zero search, insertion, solution, model, retry, and cleanup calls
  canvas object count:
    0 before; 0 after
  specimen observations:
    six ordered selectors retained
    six identity/path equations passed
    proxy-GUID assembly not_found: 6/6
    temporary-instance assembly found as GhPython: 6/6
    Data projection errors: 6/6
  probeComplete:
    false
  conclusion:
    qualification incomplete
  post-request host contact:
    zero

Task 3 evidence review:
  local strict UTF-8 and duplicate-key checks passed
  exact schemas, selector order, identities, budget, canvas equality, and outer envelope verified
  report:
    docs/superpowers/reports/2026-08-09-grasshopper-user-object-provenance-qualification.md
  mandatory independent evidence review pending

Production files changed:
  none
```
