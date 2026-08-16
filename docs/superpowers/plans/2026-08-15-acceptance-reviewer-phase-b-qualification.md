# Acceptance Reviewer Phase B Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qualify, in six fresh and blinded local-model sessions, whether the frozen Reviewer configuration shows restraint on one coherent compiler-valid point-row contract and sensitivity to five isolated residual semantic defect classes.

**Architecture:** A disposable public bundle owns the six compiler-valid artifacts, exact Reviewer inputs, closed response admission, model custody, one-call-per-case collection, and evidence-prefix sealing. A mechanically separate private bundle owns the blinded oracle, structural-diff approval, deterministic adjudication, and post-contact audit. The public runner cannot import, name, or receive the private bundle; all model calls are stateless and tool-free.

**Tech Stack:** Windows PowerShell 7, repository Python 3.12 virtual environment, Python standard library, installed `jsonschema`, local Ollama `/api/chat`, Qwen3.8:27b, canonical JSON, SHA-256, Markdown.

## Global Constraints

- Authoritative specification commit exactly `bd28e3e9dd6e571380f21fabcb9eb2e116d6f95f`.
- Authoritative specification exactly `docs/superpowers/specs/2026-08-15-acceptance-reviewer-phase-b-qualification-design.md` with SHA-256 `BA58D0684BA3CE6483D1E7A75E5C3EC14CD56D890693577C74D3497D6A38B630`.
- Disposable root exactly `C:/Users/bring/AppData/Local/Temp/rook-acceptance-reviewer-phase-b-v1`.
- If that disposable root already exists, stop. Do not delete, overwrite, repair, or reuse it.
- Retain Phase A V4 at `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator` byte-for-byte. Never run its `prepare` mode again.
- The copied V4 semantic manifest must hash to `D80D10393BFA7250B217C8636739EF4287E3AFBBE6E3C6A63834D99D4D51B30C`.
- The copied V4 compiler must hash to `4A759FBF6CCA456583CD5FBD6BF633A7F0BA7AD955D06A1AB9F05A78D4610826`.
- The copied V4 contract schema must hash to `DBE02ED96D91F801E9EB27BCDAEAA1F1491280E3EA105A85DC26CA7A0F5F6CFA`.
- Use exactly `C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe`; record its version and SHA-256.
- Add no production module, schema, router, prompt, profile, model configuration, evidence operation, Rook tool, Rhino behavior, Grasshopper behavior, or dependency.
- Do not contact Prime, Rook MCP, Rhino, Grasshopper, a hosted provider, or external network.
- Before the explicit campaign authorization, do not contact Ollama or start any model inference.
- The campaign is exactly six direct loopback Ollama calls in the frozen order. There is no Constructor, repair, continuation, retry, fallback, prompt tuning, or shared model context.
- Every Reviewer request has exactly one system message and one user message. The `tools` field is absent.
- Run all later cases after semantic misses, false positives, `uncertain`, or malformed Reviewer artifacts. Stop only for public custody drift, model/runtime identity drift, an unclosed prior call prefix, provider transport/runtime failure, or evidence-write failure.
- Public and private source manifests are independent. The public collector has no private-root parameter, import, path, digest, case meaning, expected category, or expected affected-ID tuple.
- Each source manifest inventories every frozen sibling in its own bundle except itself. Its own SHA-256 is retained externally in `precontact-review.json`, this plan's execution ledger, and the explicit authorization; self-hashing is forbidden.
- All writes are create-new, strict UTF-8, flushed, and `fsync`ed. Never overwrite a retained source or evidence artifact.
- No aggregate score is permitted. Each case reports response admission, sensitivity, restraint, and residual recognition independently.
- Passing qualifies only the frozen corpus and Qwen3.8:27b Reviewer configuration. It does not authorize production implementation.

---

## File And Ownership Map

| File | Responsibility |
|---|---|
| `public/phase_a.py` | Exact copied V4 compiler; never modified |
| `public/semantic-manifest.json` | Exact copied V4 semantic authority |
| `public/contract.schema.json` | Exact copied V4 contract schema |
| `public/reviewer-response.schema.json` | Exact response JSON Schema extracted from the approved Phase B specification |
| `public/intent.txt` | Exact original point-row request |
| `public/requirement-registry.json` | Exact R1-R4 authoritative meaning, including Start/Step/Count semantics |
| `public/evidence-vocabulary.json` | Closed Reviewer-visible facts derived from the V4 role, field, operation, precision, error, and budget contract |
| `public/reviewer-authority.json` | Closed category ontology, authority boundary, residual meaning, and citation rules |
| `public/reviewer-system.txt` | One frozen Reviewer system prompt |
| `public/settings.json` | Six-call order and exact model/generation/transport limits |
| `public/model-identity.json` | Frozen Ollama executable, tag manifest, digests, sizes, and blob-presence custody |
| `public/execution-order.json` | Exact opaque order `c04,c01,c06,c02,c05,c03` |
| `public/cases/phaseb.c01.json` through `phaseb.c06.json` | One control and five blinded compiler-valid artifacts |
| `public/protocol.py` | The one oracle-free owner for strict parsing, canonicalization, response-schema validation, and response-consistency validation |
| `public/collector.py` | Public-only request construction, runtime custody, one-call execution, prefix sealing, and public audit; consumes `protocol.py` |
| `public/test_phase_b_public.py` | Public contract, request, runtime, and evidence-custody causal tests with fake transport |
| `public/run-public.ps1` | `test | prepare | execute | audit-prefix` entry point; never reads private files |
| `public/source-manifest.json` | Frozen public source size/hash inventory; absent until prepare |
| `private/oracle.json` | Opaque-case mapping, primary category, acceptable categories, affected IDs, residual expectations, and empty supported-additional lists |
| `private/structural-diff.json` | Exact reviewed RFC 6901 changes against the control |
| `private/category-review.json` | Independent pre-contact primary-category and ambiguity decision |
| `private/adjudicator.py` | Consistency validation, per-case scoring, private audit, and final result sealing |
| `private/test_phase_b_private.py` | Oracle isolation, diff, consistency, scoring, and prefix-audit tests |
| `private/run-private.ps1` | `test | prepare | adjudicate | audit` entry point; never performs provider contact |
| `private/source-manifest.json` | Frozen private source size/hash inventory; absent until prepare |
| `precontact-review.json` | Independent no-contact review result; absent until review |
| `evidence/` | Create-new requests, responses, parsed artifacts, validation records, call ledger, campaign state, adjudication result, and evidence manifest; absent before authorization |

Disposable files are not committed to Git. Their two independent frozen
manifests, retained test output, and independent review replace source-control
custody. Repository changes remain documentation-only.

---

### Task 1: Frozen Corpus, Oracle, And Deterministic Adjudication

**Files:**
- Create: the disposable root, all static `public` inputs, all six cases, all static `private` inputs, `private/adjudicator.py`, and both test owners
- Read only: the approved Phase B specification and retained Phase A V4 root
- Modify: none outside the new disposable root

**Interfaces:**
- Produces in `public/protocol.py`: `strict_loads(raw: bytes | str) -> object` with duplicate-key, nonfinite, invalid-UTF-8, and trailing-data refusal.
- Produces in `public/protocol.py`: `canonical_bytes(value: object) -> bytes` and `sha256_bytes(raw: bytes) -> str`.
- Produces in `public/protocol.py`: `validate_response_contract(raw: bytes, schema: object) -> object`; strict/schema defects raise `ResponseContractFailure`.
- Produces in `public/protocol.py`: `validate_response_consistency(response: object, case: object, request_identity: RequestIdentity) -> object`; cross-field defects raise `ResponseConsistencyFailure`.
- Produces: `canonical_diff(control: object, sibling: object) -> tuple[DiffRecord, ...]` where `DiffRecord` contains exact RFC 6901 pointer, operation, old value presence/value, and new value presence/value.
- Produces: `adjudicate_case(case_record: object, oracle_case: object) -> CaseAdjudication` with independent response, sensitivity, restraint, and residual outcomes.
- Produces: `adjudicate_campaign(public_root: Path, private_root: Path, evidence_root: Path) -> dict[str, object]` without provider or host contact.

- [ ] **Step 1: Create the new root and write RED public/private test owners.**

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/rook-acceptance-reviewer-phase-b-v1'
if (Test-Path -LiteralPath $root) { throw "Disposable root already exists: $root" }
New-Item -ItemType Directory -Path "$root/public/cases" -Force | Out-Null
New-Item -ItemType Directory -Path "$root/private" -Force | Out-Null
```

`test_phase_b_public.py` initially imports only `protocol` and `phase_a`.
Task 2 adds the `collector` import when that owner enters scope. Its initial
named tests are:

```text
test_exact_v4_compiler_manifest_and_schema_hashes
test_all_six_cases_compile_with_exact_v4_owner
test_response_schema_accepts_control_and_material_correction
test_response_schema_refuses_material_adequate
test_response_schema_refuses_correction_without_material
test_response_schema_refuses_uncertain_with_material
test_response_schema_refuses_empty_or_out_of_domain_citations
test_requirement_registry_owns_start_step_count_and_adjustability
test_case_names_and_execution_order_are_opaque
test_protocol_is_the_only_response_admission_owner
```

`test_phase_b_private.py` imports `adjudicator`. Its initial named tests are:

```text
test_structural_diff_is_exact_for_every_case
test_each_mutation_has_one_predeclared_primary_category
test_initial_acceptable_category_sets_are_singletons
test_supported_additional_findings_are_empty
test_control_requires_two_acknowledged_residuals
test_finding_and_residual_overlap_is_consistency_invalid
test_duplicate_finding_or_residual_ids_are_consistency_invalid
test_uncertain_never_satisfies_sensitivity
test_category_and_affected_id_are_both_required
test_unsupported_additional_finding_fails_restraint_independently
```

- [ ] **Step 2: Run both RED owners and retain the missing-module failures.**

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/rook-acceptance-reviewer-phase-b-v1'
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
& $python "$root/public/test_phase_b_public.py" -v
if ($LASTEXITCODE -eq 0) { throw 'Public RED suite unexpectedly passed' }
& $python "$root/private/test_phase_b_private.py" -v
if ($LASTEXITCODE -eq 0) { throw 'Private RED suite unexpectedly passed' }
```

Expected: public import failure naming `collector`, then private import failure
naming `adjudicator`. No test skips because data is absent.

- [ ] **Step 3: Copy and verify the exact Phase A authority.**

Copy only `phase_a.py`, `semantic-manifest.json`, and `contract.schema.json`
from the retained V4 root into `public`. Before using them, require the three
Global Constraints hashes. Extract the one JSON block whose `$id` is
`rook.acceptance_reviewer.phase_b.response:v1` from the approved specification,
strict-parse it, run `Draft202012Validator.check_schema`, and write its canonical
bytes as `reviewer-response.schema.json`.

The extraction must find exactly one matching JSON block. A second block,
missing block, invalid schema, or specification-hash mismatch refuses.

- [ ] **Step 4: Write the exact shared Reviewer inputs.**

`intent.txt` is exactly:

```text
Create a Grasshopper definition that generates a row of points along the X axis using adjustable Start, Step, and Count controls, with Y and Z fixed at zero.
```

`requirement-registry.json` contains exactly R1-R4 and the specification's
authoritative text. `reviewer-authority.json` contains exactly the five closed
categories, precedence order, four response classifications, finding versus
residual ownership, and the rule that semantic wording is not scored.

`evidence-vocabulary.json` copies the complete admitted V4 manifest semantics
needed by the Reviewer. It must state explicitly that V4 can count complete
collections and quantify point coordinates, but has no indexed-element
operation and no deterministic structural-adjustability fact. It must not add
an operation or imply that judgment is deterministic proof.

`reviewer-system.txt` requires one schema-only JSON response, fresh independent
review, direct comparison with the intent/registry, categorized material
findings, explicit recognition of honestly disclosed residuals, no topology
preference, no replacement artifact, and no invented evidence.

- [ ] **Step 5: Write the coherent control and five sibling cases.**

Build the control in the specification's exact claim order. Use V4 expressions
for count equality and quantified Y/Z zero; use null expressions with
`judgment_required` for indexed X progression and independent adjustability.
List all five IDs in `policy.requiredClaimIds`.

Derive the five siblings by deep copy and only these semantic mutations:

```text
c02 remove claims[4] and policy.requiredClaimIds[4]
c03 append count_must_equal_five and its policy ID
c04 replace claims[1] absolute tolerance value 1e-9 -> 1.0
c05 replace claims[4] authority -> user_required and expression -> null
c06 replace claims[2] authority -> deterministic_required,
    expression -> the count-equality expression,
    and intentSummary -> text falsely claiming indexed-X coverage
```

Give every artifact only its opaque `phaseb.c0N` identity. Canonicalize every
file. Compile all six through copied V4 `compile_contract`; require `compiled`.

- [ ] **Step 6: Write the private oracle and structural-difference audit.**

`oracle.json` uses the specification's exact c01-c06 mapping. Every mutation
has a singleton acceptable-category set containing its primary category,
empty `supportedAdditionalFindings`, and exact affected requirement/claim IDs.
The control expects no defect category and exactly the two disclosed residual
claim IDs.

The primary mapping is exact:

```text
c02 requirement_omission
c03 invented_assumption
c04 material_weakening
c05 authority_misrouting
c06 hidden_unresolved_risk
```

Implement `canonical_diff` recursively over dictionaries and arrays without
stringifying values. Escape RFC 6901 `~` as `~0` and `/` as `~1`. Require
`/contractId` plus only the exact case-specific pointer set in the
specification. Write the complete old/new values to `structural-diff.json`.

- [ ] **Step 7: Implement the one public protocol owner and private adjudication.**

Create `public/protocol.py`. It alone uses
`jsonschema.Draft202012Validator`; do not duplicate schema enums or response
admission logic in `collector.py` or `adjudicator.py`. After schema admission,
it enforces exact request case/hash correlation, unique finding IDs, unique
residual claim IDs, current-artifact claim citations,
judgment-required/null/disclosed residual ownership, and no finding/residual
claim overlap.

The admitted response reads defects only from `findings` and honest limitations
only from `acknowledgedResiduals`. Neither array may be inferred from prose,
provider reasoning, or the disposition field.

`collector.py` imports the public protocol owner and records its exact
classification. `private/adjudicator.py` imports the same public module and
consumes that classification; it may compare an admitted response with the
private oracle but may not parse, validate, or reclassify the response itself.
AST/source tests must refuse a second `Draft202012Validator`, duplicate-key
hook, nonfinite parser, or response-consistency implementation outside
`public/protocol.py`.

Return exactly one response classification:

```python
RESPONSE_CLASSIFICATIONS = {
    "response_contract_invalid",
    "response_consistency_invalid",
    "reviewer_uncertain",
    "admitted",
}
```

Adjudicate every case independently. Sensitivity requires admitted,
`correction_required`, a material finding with an acceptable category, and an
affected-ID citation. Restraint independently refuses every oracle-unsupported
additional finding. Control success additionally requires `adequate` and the
exact two residual IDs. Produce no aggregate field.

- [ ] **Step 8: Run both suites GREEN and compile all Python.**

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/rook-acceptance-reviewer-phase-b-v1'
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
& $python "$root/public/test_phase_b_public.py" -v
if ($LASTEXITCODE -ne 0) { throw 'Public suite failed' }
& $python "$root/private/test_phase_b_private.py" -v
if ($LASTEXITCODE -ne 0) { throw 'Private suite failed' }
& $python -m py_compile "$root/public/phase_a.py" "$root/private/adjudicator.py" "$root/public/test_phase_b_public.py" "$root/private/test_phase_b_private.py"
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed' }
```

Expected: every named test passes; no model, network, or host evidence exists.

---

### Task 2: Public-Only Collector And Evidence-Prefix Custody

**Files:**
- Create: `public/collector.py`, `public/settings.json`, `public/execution-order.json`, `public/run-public.ps1`, `private/run-private.ps1`
- Modify: both test owners
- Create later: `public/model-identity.json`, both source manifests
- Test: fake transport only; no Ollama contact

**Interfaces:**
- Produces: `verify_public_manifest(public_root: Path) -> ManifestRecord`.
- Produces: `verify_model_identity(public_root: Path) -> ModelIdentity` using filesystem/process evidence without inference.
- Produces: `build_user_message(public_root: Path, case_id: str) -> str` from exact frozen inputs.
- Produces: `build_wire_payload(public_root: Path, case_id: str) -> bytes` with the exact Ollama field names and values.
- Produces: `execute_case(public_root: Path, evidence_root: Path, case_id: str, transport: Transport) -> CasePrefix`.
- Produces: `run_campaign(public_root: Path, evidence_root: Path, transport: Transport) -> CampaignPrefix`.
- Produces: `audit_prefix(public_root: Path, evidence_root: Path) -> CampaignPrefix`.

- [ ] **Step 1: Add RED tests for request identity, oracle exclusion, call count, and prefix closure.**

Add exact public tests:

```text
test_collector_source_has_no_private_or_oracle_owner
test_request_has_two_messages_and_no_tools
test_request_wire_shape_and_snake_case_options_are_exact
test_request_wire_has_think_medium_and_keep_alive
test_requests_share_prompt_settings_manifest_vocabulary_authority_and_schema
test_requests_differ_only_by_case_identity_artifact_and_hash
test_request_bytes_exclude_oracle_digest_meaning_and_expected_tuple
test_fake_transport_receives_exactly_one_request_per_case
test_schema_invalid_model_artifact_closes_case_and_continues
test_uncertain_model_artifact_closes_case_and_continues
test_transport_failure_stops_before_next_case
test_public_custody_drift_stops_before_next_case
test_model_identity_drift_stops_before_next_case
test_create_new_writer_flushes_and_fsyncs
test_complete_and_incomplete_prefixes_audit_exactly
```

Add private tests proving the private auditor can consume complete and stopped
prefixes without changing public evidence.

- [ ] **Step 2: Run the targeted RED tests.**

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/rook-acceptance-reviewer-phase-b-v1'
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
& $python "$root/public/test_phase_b_public.py" -v
if ($LASTEXITCODE -eq 0) { throw 'Collector RED tests unexpectedly passed' }
```

Expected: missing `collector` interfaces or missing evidence-custody behavior.

- [ ] **Step 3: Freeze exact settings and execution order.**

Use exactly:

```json
{
  "endpoint": "http://127.0.0.1:11434/api/chat",
  "externalNetworkForbidden": true,
  "keepAlive": "5m",
  "maximumCalls": 6,
  "maximumResponseBytes": 131072,
  "model": "qwen3.8:27b",
  "numCtx": 32768,
  "numPredict": 8192,
  "reasoning": "medium",
  "retryLimit": 0,
  "seed": 2026081502,
  "stream": false,
  "temperature": 0.0,
  "timeoutSecondsPerCall": 900,
  "topP": 0.9
}
```

`execution-order.json` is exactly the six opaque IDs in the specification's
order. Reject duplicate, missing, extra, or reordered IDs.

The internal settings file is configuration input only. The effective compact
UTF-8 `/api/chat` request payload is constructed exactly as:

```python
payload = {
    "model": "qwen3.8:27b",
    "messages": [
        {
            "role": "system",
            "content": load_text(public_root / "reviewer-system.txt"),
        },
        {
            "role": "user",
            "content": build_user_message(public_root, case_id),
        },
    ],
    "stream": False,
    "think": "medium",
    "keep_alive": "5m",
    "options": {
        "seed": 2026081502,
        "temperature": 0.0,
        "top_p": 0.9,
        "num_ctx": 32768,
        "num_predict": 8192,
    },
}
wire_bytes = canonical_bytes(payload)
```

No camelCase setting name reaches the wire. Fake-transport tests compare the
complete decoded payload and causally refuse missing, renamed, defaulted,
duplicated, or extra wire fields.

- [ ] **Step 4: Implement request construction without private inputs.**

`build_request` receives only `public_root` and `case_id`. It strict-loads and
rehashes every public input, recompiles the case, and emits compact JSON for
Ollama `/api/chat`. The user message includes the intent, requirement registry,
artifact/hash, semantic manifest/hash, evidence vocabulary, Reviewer authority,
and response schema. It includes no expected result, case meaning, prior
response, hidden mutation description, tools, or third message.

The six captured fake requests must become byte-identical after removing only:

```text
artifact bytes
artifact SHA-256
opaque caseId/contractId
```

- [ ] **Step 5: Implement filesystem-owned model/runtime custody.**

Before contact, record the exact Ollama executable path/hash/version, tag
manifest path/hash, content-addressed config/layer digests, exact sizes, and
blob presence. Do not hash 17 GB model blobs unless the retained identity says
that was performed. State the nonclaim explicitly.

Before every call, recheck executable hash, tag manifest hash, digest list,
sizes, and blob presence. Require the endpoint scheme/host/port/path exactly
`http`, `127.0.0.1`, `11434`, `/api/chat`. Do not contact Ollama during
`prepare` or tests.

- [ ] **Step 6: Implement one-call collection and prefix sealing.**

For each case, write the exact request before contact; call the injected
transport once; retain exact status/headers/body; extract only
`message.content`; pass it once through `public.protocol` for strict parsing and
schema/consistency validation; then append one terminal call-ledger event.
Flush/fsync every file before advancing.

Schema/semantic outcomes continue to the next case. Transport/runtime,
identity, public custody, or evidence-write failures close an incomplete prefix
and stop. Never retry or regenerate a request.

- [ ] **Step 7: Implement public and private PowerShell entry points.**

`run-public.ps1` has exact modes:

```text
test         run public inert tests only
prepare      derive model identity and create source-manifest.json
execute      require frozen public custody and perform the six-call campaign
audit-prefix verify retained public evidence without private inputs
```

`run-private.ps1` has exact modes:

```text
test         run private inert tests only
prepare      create private/source-manifest.json after diff/category review
adjudicate   consume closed public evidence and create final results
audit        independently verify private sources and final results
```

Neither script delegates to the other. `run-public.ps1` contains no private
path or oracle term.

- [ ] **Step 8: Run the full fake-backed GREEN seam.**

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/rook-acceptance-reviewer-phase-b-v1'
& pwsh -NoProfile -File "$root/public/run-public.ps1" -Mode test
if ($LASTEXITCODE -ne 0) { throw 'Public tests failed' }
& pwsh -NoProfile -File "$root/private/run-private.ps1" -Mode test
if ($LASTEXITCODE -ne 0) { throw 'Private tests failed' }
[scriptblock]::Create((Get-Content -LiteralPath "$root/public/run-public.ps1" -Raw)) | Out-Null
[scriptblock]::Create((Get-Content -LiteralPath "$root/private/run-private.ps1" -Raw)) | Out-Null
```

Expected: all tests pass, both PowerShell files parse, and `evidence/` remains
absent.

---

### Task 3: Freeze Both Bundles And Stop For Independent Pre-Contact Review

**Files:**
- Create: `public/model-identity.json`, `public/source-manifest.json`, `private/structural-diff.json`, `private/category-review.json`, `private/source-manifest.json`, root `precontact-review.json`
- Modify: none after manifest creation
- Evidence: no `evidence/` directory or provider request

**Interfaces:**
- Consumes: complete Task 1 and Task 2 disposable sources.
- Produces: two independently verifiable frozen manifests and one reviewed campaign authorization target.

- [ ] **Step 1: Run all inert tests and verify no contact surfaces were used.**

Run both test modes, Python compilation, PowerShell parsing, and source scans.
Require no `evidence` directory, request, response, call ledger, provider body,
or final result.

Source scans must prove:

```text
public collector has no import/path/parameter for private or oracle owners
no production Rook/Prime/Rhino/Grasshopper import
no endpoint except exact loopback Ollama /api/chat
no retry loop or fallback model
exact six-case execution order
```

- [ ] **Step 2: Prepare and freeze the public bundle.**

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/rook-acceptance-reviewer-phase-b-v1'
& pwsh -NoProfile -File "$root/public/run-public.ps1" -Mode prepare
if ($LASTEXITCODE -ne 0) { throw 'Public prepare failed' }
```

Require create-new `model-identity.json` and `source-manifest.json`. Immediately
rehash every entry independently. The public manifest inventories every frozen
public sibling except `source-manifest.json` itself. Require no other unlisted
public file except Python bytecode caches, which must be excluded from execution
and manifests. Retain the public manifest's own SHA-256 only in
`precontact-review.json`, this plan's execution ledger, and the later explicit
authorization.

- [ ] **Step 3: Complete the human category/diff review and freeze private custody.**

An independent reviewer must inspect the control, each complete sibling,
canonical pointer diff, category ontology, primary category, acceptable set,
affected IDs, supported-additional list, and control residual expectations.

The review must either:

```text
approve one singleton primary category for every mutation
and approve every pointer difference
```

or refuse the corpus. It cannot relabel cases after contact.

After approval:

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/rook-acceptance-reviewer-phase-b-v1'
& pwsh -NoProfile -File "$root/private/run-private.ps1" -Mode prepare
if ($LASTEXITCODE -ne 0) { throw 'Private prepare failed' }
```

The private manifest follows the identical non-self-referential rule: it
inventories every frozen private sibling except its own
`source-manifest.json`. Its own SHA-256 is retained externally beside the
public manifest hash.

- [ ] **Step 4: Perform one complete independent no-contact review.**

The reviewer independently reproduces:

```text
all inert tests
all six V4 compiler admissions
Draft 2020-12 schema validity and contradiction refusals
all structural pointer diffs
opaque naming/order and oracle isolation
public/private manifest membership, size, and SHA-256
model artifact identity and blob presence
zero provider/model/live evidence
```

Write `precontact-review.json` outside both frozen bundle manifests. It records
the two manifest hashes, test counts, category-review hash, structural-diff
hash, model manifest hash, reviewer verdict, and zero-contact statement.

- [ ] **Step 5: Commit only this plan's execution-ledger amendment and stop.**

Append the exact frozen root, both manifest hashes, test counts, review hash,
and authorization target to a `## Execution Ledger` section at the end of this
plan. Commit only this plan amendment:

```powershell
git add -- 'docs/superpowers/plans/2026-08-15-acceptance-reviewer-phase-b-qualification.md'
git commit -m 'docs: freeze phase b reviewer campaign'
```

Stop and request one explicit authorization identifying both frozen manifest
hashes for exactly six calls. No provider call is permitted yet.

---

### Task 4: One Authorized Six-Call Campaign, Adjudication, And Report

**Files:**
- Create under `evidence/`: six requests, up to six responses/artifacts/validation records, call ledger, campaign state, public evidence manifest, private adjudication result, and private evidence manifest
- Create: `docs/superpowers/reports/2026-08-15-acceptance-reviewer-phase-b-qualification.md`
- Modify: `docs/superpowers/2026-08-15-acceptance-workflow-router-architecture-status.md`
- Modify production code: none

**Interfaces:**
- Consumes: the exact frozen public/private manifest hashes authorized by the user.
- Produces: six independent case outcomes or one truthfully closed incomplete prefix.

- [ ] **Step 1: Verify the explicit authorization and all pre-contact custody.**

Require the authorization to name both manifest SHA-256 values. Re-run public
manifest, private manifest, V4 compile, model identity, and precontact-review
verification. Require `evidence/` absent and zero earlier requests.

- [ ] **Step 2: Execute the public campaign exactly once.**

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/rook-acceptance-reviewer-phase-b-v1'
& pwsh -NoProfile -File "$root/public/run-public.ps1" -Mode execute
$campaignExit = $LASTEXITCODE
```

Do not invoke `execute` again for any exit code. Semantic outcomes continue
through all six; a custody/runtime/transport/write stop preserves its prefix.

- [ ] **Step 3: Audit the public prefix before private adjudication.**

```powershell
& pwsh -NoProfile -File "$root/public/run-public.ps1" -Mode audit-prefix
if ($LASTEXITCODE -ne 0) { throw 'Public prefix audit failed' }
```

Require exactly one request and at most one terminal response per started case,
the frozen order, no duplicate call, and no seventh request.

- [ ] **Step 4: Adjudicate once and audit private results.**

```powershell
& pwsh -NoProfile -File "$root/private/run-private.ps1" -Mode adjudicate
if ($LASTEXITCODE -ne 0) { throw 'Private adjudication failed' }
& pwsh -NoProfile -File "$root/private/run-private.ps1" -Mode audit
if ($LASTEXITCODE -ne 0) { throw 'Private audit failed' }
```

Report every case independently:

```text
response classification
disposition
material findings and citations
acknowledged residuals
intended-category sensitivity
unsupported-additional restraint
control restraint/residual recognition
prompt/generated tokens and duration
```

Do not create an aggregate result.

- [ ] **Step 5: Write the bounded result report and update architecture status.**

The report must include exact repository/model/settings identity, both frozen
manifest hashes, six request/response/artifact hashes, public/private evidence
manifest hashes, all independent outcomes, complete telemetry, failures, and
nonclaims. State whether sensitivity and restraint were observed only for this
frozen corpus/configuration.

The architecture status records exactly one of the three campaign statuses
below. It must not authorize the production router automatically.

The final campaign status is deterministic and exactly one of:

```text
qualified_on_corpus
  all six calls have complete admitted terminal evidence
  and every required sensitivity, restraint, and residual outcome passes

not_qualified_on_corpus
  all six calls have complete terminal evidence
  and at least one required sensitivity, restraint, or residual outcome fails

incomplete
  the six-case evidence prefix is incomplete for any reason
```

`response_contract_invalid`, `response_consistency_invalid`, or
`reviewer_uncertain` is a completed case outcome when its request and terminal
provider response are durably retained. Such an outcome therefore contributes
to `not_qualified_on_corpus`, not `incomplete`. Missing terminal evidence,
transport/runtime stop, or failed durable custody yields `incomplete`.

- [ ] **Step 6: Verify documentation and commit exactly two files.**

```powershell
git diff --check
git status --short
git add -- `
  'docs/superpowers/reports/2026-08-15-acceptance-reviewer-phase-b-qualification.md' `
  'docs/superpowers/2026-08-15-acceptance-workflow-router-architecture-status.md'
git commit -m 'docs: record phase b reviewer qualification'
git show --check --stat --oneline HEAD
```

Stop after the documentation commit. Do not tune the prompt, rerun a case,
repair an artifact, add corpus cases, implement the router, or contact another
model.

---

## Execution Ledger

Not yet executed. Task 3 must append exact frozen hashes and independent review
evidence here before any authorization request.
