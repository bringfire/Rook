# Acceptance Semantic Manifest Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qualify, entirely offline and in disposable artifacts, that one closed semantic manifest can drive strict contract admission and static expression compilation for the bounded point-row Phase A vocabulary.

**Architecture:** One stdlib-only disposable Python owner strict-parses the canonical manifest, typed contract, marked specification examples, and isolated mutation corpus. It performs schema, reference, role/value-type, field, operation, quantifier, authority, precision, and budget checks without evaluating runtime evidence. It writes a create-new, hash-correlated qualification result and evidence manifest, then stops for independent no-contact review.

**Tech Stack:** Windows PowerShell 7, repository Python 3.12 virtual environment, Python standard library (`json`, `hashlib`, `math`, `pathlib`, `re`, `unittest`), Markdown, JSON.

## Global Constraints

- Authoritative specification baseline exactly `4ec4929d8a351b022d8735c8bb9340d1968f63f0`.
- Authoritative specification exactly `docs/superpowers/specs/2026-08-15-rook-prime-acceptance-workflow-router-design.md` at that baseline.
- At execution, that baseline must be an ancestor of clean `HEAD`; the only path changed after it may be this Phase A plan, and the specification blob must remain byte-identical.
- Disposable root exactly `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator`.
- V1, V2, and V3 are preserved byte-for-byte as rejected evidence lanes. V1
  exposed root-ownership drift; V2 exposed manifest-authority,
  repository-custody, budget, mutation-diff, and manifest-audit gaps; V3
  exposed a hidden literal-only tolerance rule and an inaccurate negative
  tolerance diagnostic. None authorizes Phase B.
- If that root already exists, stop. Do not delete, overwrite, repair, or reuse it.
- Use exactly `C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe`; record its version and SHA-256 before qualification.
- Add no production module, endpoint, schema, tool, router, profile, evaluator behavior, or dependency.
- Do not modify `rook.validation_kernel`, the suspended seven-stage router plan, Prime, Rook product source, tests, or deployment state.
- Do not contact Ollama, any hosted model/provider, Prime, Rook MCP, Rhino, Grasshopper, or the network.
- Phase A compiles expressions only. It does not fabricate runtime values, evaluate claims, call a Reviewer, or claim semantic adequacy.
- `kind` identifies role binding; `valueType` identifies semantic meaning. Neither is inferred from role IDs, descriptions, claims, or intent text.
- Authority is exactly `deterministic_required | judgment_allowed | judgment_required | user_required` with the specification's exact expression-compatibility matrix.
- Unknown syntax is `invalid`; a known manifest entry with `availability=unavailable` is `unsupported`; neither is silently widened or guessed.
- The valid specification-example marker contract is exact and line-oriented:
  `<!-- phase-a-valid-json id=ID kind=expression|claim -->`, one JSON fence, then `<!-- /phase-a-valid-json -->`.
- All generated evidence uses create-new writes, flush, and `fsync`. Failure to write a closed result leaves an incomplete evidence prefix; it never authorizes Phase B.
- The only review gate is after the complete offline qualification. Phase B design, Reviewer calls, grid/helix work, and production planning remain blocked.

---

## File And Ownership Map

| File | Responsibility |
|---|---|
| `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator/phase_a.py` | Strict JSON ownership, manifest admission, static compiler, marked-example extraction, mutation application, qualification sealing, and audit |
| `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator/test_phase_a.py` | All causal Phase A tests; no network, model, host, or production imports |
| `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator/semantic-manifest.json` | The one canonical semantic authority for types, roles, fields, operations, quantifiers, authorities, precision, errors, and budgets |
| `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator/contract.schema.json` | Closed typed contract shape; references the manifest ID/hash but does not redefine operation semantics |
| `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator/point-row.valid.json` | One coherent compiler-only point-row contract |
| `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator/mutation-corpus.json` | Ordered one-change mechanical mutations and their exact expected diagnostics |
| `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator/run.ps1` | One no-contact test, prepare, qualify, and audit entry point |
| `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator/authoritative-spec.md` | Exact byte copy of the authoritative specification at the pinned baseline |
| `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator/participant-inputs.json` | Generated proof that Constructor template, Reviewer template, validator, and corpus consume identical manifest bytes/hash |
| `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator/execution-ledger.json` | Generated, independently derived baseline, interpreter, source-spec, no-contact boundary, and artifact identities |
| `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator/source-manifest.json` | Generated exact size/hash inventory of every frozen input and source |
| `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator/qualification-result.json` | Generated closed result containing valid examples, coherent compilation, and every mutation outcome |
| `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator/evidence-manifest.json` | Generated exact size/hash inventory of the retained qualification evidence |

All reusable behavior remains in the single disposable `phase_a.py` because it
has one qualification owner and will not ship. Split nothing into production
packages. Static data remains separate so tests can mutate data without adding
claim-ID or role-ID dispatch to the compiler.

---

### Task 1: Offline Shared-Semantics Compiler Qualification

**Files:**
- Create: every disposable file in the ownership map above
- Read only: `docs/superpowers/specs/2026-08-15-rook-prime-acceptance-workflow-router-design.md`
- Modify: none outside the disposable root
- Test: `C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator/test_phase_a.py`

**Interfaces:**
- Produces: `strict_loads(raw: bytes | str) -> object` with duplicate-key, nonfinite, invalid UTF-8, and trailing-data refusal.
- Produces: `canonical_bytes(value: object) -> bytes` and `sha256_bytes(raw: bytes) -> str`.
- Produces: `load_manifest(raw: bytes) -> SemanticManifest`; closed defects raise `CompileFailure`.
- Produces: `compile_expression(node: object, roles: Mapping[str, RoleType], binders: tuple[Binder, ...], manifest: SemanticManifest, budget: CompileBudget) -> str`; closed defects raise `CompileFailure`.
- Produces: `compile_claim(claim: object, roles: Mapping[str, RoleType], manifest: SemanticManifest) -> CompiledClaim`; closed defects raise `CompileFailure`.
- Produces: `compile_contract(raw: bytes, manifest: SemanticManifest) -> dict[str, object]` with exact `compiled | unsupported | invalid` status.
- Produces: `extract_valid_spec_examples(raw: bytes) -> tuple[MarkedExample, ...]`.
- Produces: `apply_corpus_mutation(base: object, mutation: object) -> bytes` without mutating the base object.
- Produces: `qualify(root: Path) -> dict[str, object]` and `audit(root: Path) -> dict[str, object]`.

- [ ] **Step 1: Create a new empty disposable root and write only the RED test owner.**

First prove the root is new:

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator'
if (Test-Path -LiteralPath $root) {
  throw "Disposable Phase A root already exists: $root"
}
New-Item -ItemType Directory -Path $root | Out-Null
```

Create `test_phase_a.py` with `unittest`. Import `phase_a` at module scope so
the first run fails before any data or compiler exists. Organize the cases into
the exact classes `StrictJsonTests`, `ManifestContractTests`,
`ExpressionCompilerTests`, `AuthorityCompatibilityTests`,
`SpecificationExampleTests`, `MutationCorpusTests`,
`QualificationCustodyTests`, and `NoContactSurfaceTests`.

The RED suite must name every required behavior rather than using one broad
smoke test. At minimum include:

```text
test_duplicate_json_key_refuses
test_nonfinite_json_number_refuses
test_manifest_bytes_are_canonical
test_manifest_has_exact_top_level_sections
test_every_role_kind_entry_is_closed
test_every_field_entry_is_closed
test_every_operation_entry_is_closed
test_role_kind_value_type_matrix_is_exact
test_role_expression_never_unwraps_value
test_field_projection_owns_scalar_and_collection_values
test_quantifier_binder_is_lexical_and_cannot_shadow
test_authority_expression_matrix_is_exhaustive
test_valid_spec_markers_are_closed_and_unique
test_every_marked_valid_spec_example_strict_parses_and_compiles
test_coherent_point_row_contract_compiles
test_each_mutation_changes_exactly_one_declared_property
test_each_mutation_returns_its_exact_diagnostic
test_mechanically_invalid_contract_produces_no_reviewer_request
test_compiler_source_has_no_claim_or_role_dispatch
test_no_network_model_prime_rook_or_host_surface_exists
test_result_and_evidence_manifests_audit_exactly
```

- [ ] **Step 2: Run the RED suite and retain the expected missing-owner failure.**

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator'
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
& $python "$root/test_phase_a.py" -v
if ($LASTEXITCODE -eq 0) { throw 'RED suite unexpectedly passed' }
```

Expected: import failure naming `phase_a`. No test may skip because a file is
absent.

- [ ] **Step 3: Add the canonical semantic manifest and closed contract schema.**

The manifest has exactly these top-level keys:

```json
[
  "schema", "id", "version", "types", "roleKinds", "fields",
  "operations", "quantifiers", "authorityCompatibility",
  "precisionRules", "errorRules", "budgetRules"
]
```

Use `schema="rook.acceptance_semantic_manifest:v1"`,
`id="rook.acceptance_expression.phase_a:v1"`, and `version=1`. Admit exactly
the public value types `integer`, `finite_scalar`, `point3`, and
`collection<point3>`, plus compiler-internal `boolean3` and
`role_ref<kind,valueType>`.

`roleKinds` contains the four specification kinds. The exact available pairs
are:

```text
grasshopper_number_control + integer
grasshopper_number_control + finite_scalar
grasshopper_output         + collection<point3>
```

`geometry_collection` and `external_evidence` are present with
`availability="unavailable"`. Every role-kind object has exactly `id`,
`availability`, `allowedValueTypes`, `bindingType`, `availableFields`,
`unavailableOutcome`, and `incompatibleOutcome`.

`fields` contains exactly these available projections:

```text
role_ref<grasshopper_number_control,integer>.value       -> integer
role_ref<grasshopper_number_control,finite_scalar>.value -> finite_scalar
role_ref<grasshopper_output,collection<point3>>.value    -> collection<point3>
point3.x                                                   -> finite_scalar
point3.y                                                   -> finite_scalar
point3.z                                                   -> finite_scalar
```

Every field object has exactly `sourceTypePattern`, `name`,
`resultTypeExpression`, `availability`, `missingBehavior`, `errorBehavior`,
and `budgetCost`.

`operations` contains available entries for `literal`, `role`, `field`,
`current_item`, `collection_count`, `coordinate`, `equal`, `approx_equal`,
`and`, and `for_all`. Add `phase` and `external_evidence` as explicitly known
but unavailable entries so `unsupported` is causally distinguishable from
`invalid/operation_unknown`. Every operation object has exactly `op`,
`availability`, `arity`, `inputTypePatterns`, `outputTypeExpression`,
`precision`, `missingBehavior`, `unsupportedBehavior`, `errorBehavior`, and
`budgetCost`.

The `approx_equal` entry uses exact input patterns:

```text
same_numeric
same_numeric
finite_nonnegative_literal
finite_nonnegative_literal
```

The shared pattern means a `finite_scalar` literal whose value is finite and
greater than or equal to zero. A negative finite literal is
`invalid/tolerance_negative`; any role, field, binder, or computed expression
at either tolerance position is `invalid/tolerance_source_invalid`.

`authorityCompatibility` is exactly:

```json
{
  "deterministic_required": {"expression":"required","requiredType":"boolean3","additionalAuthority":"none"},
  "judgment_allowed": {"expression":"required","requiredType":"boolean3","additionalAuthority":"on_unproven"},
  "judgment_required": {"expression":"optional","requiredType":"boolean3","additionalAuthority":"always_judgment"},
  "user_required": {"expression":"optional","requiredType":"boolean3","additionalAuthority":"always_user"}
}
```

`budgetRules` pins raw contract bytes `131072`, expression nodes `128`, depth
`16`, quantifier depth `4`, collection visits `4096`, and static compile work
cost `64`. Operation costs are exact: `literal`, `role`, and `current_item` cost
1; `field`, `collection_count`, and `coordinate` cost 2; `equal` and `and` cost
3; `approx_equal` costs 4; and `for_all` costs 8. Known-unavailable entries
cost zero because they terminate compilation before executable work exists.
Booleans are never integers. `precisionRules` pins exact integers, finite
scalars, no implicit widening, and mandatory explicit nonnegative finite
absolute and relative tolerances. `errorRules` maps schema/reference/type/
authority/binder/nonfinite/budget defects to `invalid`, and known unavailable
operations/kinds to `unsupported`.

Write `contract.schema.json` as a Draft 2020-12 JSON Schema with
`additionalProperties:false` on every object. The root keys are exactly
`schema`, `contractId`, `contractVersion`, `intentSummary`, `vocabulary`,
`roles`, `dependencies`, `probes`, `claims`, and `policy`. Reuse one `$defs.roleId`
with regex `^[a-z][A-Za-z0-9]*$` and `maxLength:64` at every declaration and
reference site. In Phase A, `dependencies` and `probes` are exact empty arrays.
The schema constrains expression containers and lexical IDs, but does not enum
role kinds or operation IDs. The manifest alone distinguishes available,
known-unavailable, and unknown entries. The compiler uses the selected
manifest entry to enforce the exact node-key set, arity, and type signature, so
an absent operation reaches `invalid/operation_unknown` instead of being
misclassified as a generic schema failure.

Mechanically rewrite both JSON files to compact sorted-key UTF-8, then require:

```python
raw == canonical_bytes(strict_loads(raw))
```

- [ ] **Step 4: Add the coherent point-row fixture and isolated mutation corpus.**

`point-row.valid.json` declares exactly `startControl`, `stepControl`,
`countControl`, and `points` with the approved kinds/value types. It has three
required claims:

```text
point_count_equals_count
all_y_zero
all_z_zero
```

The count expression projects both values explicitly:

```json
{
  "op": "equal",
  "args": [
    {
      "op": "collection_count",
      "args": [
        {"op":"field","source":{"op":"role","role":"points"},"name":"value"}
      ]
    },
    {"op":"field","source":{"op":"role","role":"countControl"},"name":"value"}
  ]
}
```

Each coordinate claim uses `for_all` over the projected points collection,
one binder named `point`, `coordinate(current_item(point), y|z)`, and
`approx_equal` to a finite-scalar zero literal with explicit absolute and
relative tolerance literals. The fixture states the Start/Step indexed
relationship only in `intentSummary`; it does not fabricate a claim because
indexed access is unavailable.

After `semantic-manifest.json` is canonical, compute its actual SHA-256 and
place that full lowercase 64-hex value in the fixture's `vocabulary.sha256`.
Put the same manifest ID and hash in `contract.schema.json`; no sentinel,
abbreviation, or placeholder hash is admitted.

`mutation-corpus.json` has exact root keys `schema`, `baseSha256`, and `cases`.
Each case has exactly `id`, `mutation`, and `expected`. The mutation is one
owned `replace`, `remove`, or `raw_token_replace`; expected has exactly
`status`, `code`, and `path`. Include separate causal cases for:

```text
undeclared role reference                    invalid/reference_unknown
incompatible role kind/valueType             invalid/role_type_incompatible
unprojected control role comparison           invalid/type_mismatch
coordinate applied to collection              invalid/type_mismatch
unbound quantifier variable                   invalid/binder_invalid
shadowed quantifier variable                  invalid/binder_invalid
out-of-scope quantifier variable              invalid/binder_invalid
null deterministic_required expression        invalid/authority_expression_incompatible
null judgment_allowed expression              invalid/authority_expression_incompatible
missing approximate absolute tolerance        invalid/tolerance_required
missing approximate relative tolerance        invalid/tolerance_required
negative absolute tolerance literal            invalid/tolerance_negative
negative relative tolerance literal            invalid/tolerance_negative
nonliteral absolute tolerance source            invalid/tolerance_source_invalid
nonliteral relative tolerance source            invalid/tolerance_source_invalid
nonfinite literal token 1e999                 invalid/nonfinite
expression node limit exceeded                invalid/budget_exceeded
expression depth limit exceeded               invalid/budget_exceeded
quantifier depth limit exceeded               invalid/budget_exceeded
work-cost limit exceeded                      invalid/budget_exceeded
known unavailable operation                   unsupported/operation_unavailable
known unavailable role kind                   unsupported/role_kind_unavailable
unknown operation                             invalid/operation_unknown
```

For every ordinary case, clone the coherent object and change exactly the one
declared JSON pointer. The raw nonfinite case replaces only the selected
numeric token after canonical encoding. Generated budget expressions replace
only one complete claim expression. The base object and prior cases must be
byte-identical after every mutation.

- [ ] **Step 5: Implement strict ownership and manifest admission in `phase_a.py`.**

Use exact concrete container types after `json.loads`; reject subclasses and
booleans at integer sites. The strict hooks are:

```python
def _pairs(pairs):
    owned = {}
    for key, value in pairs:
        if type(key) is not str or key in owned:
            raise CompileFailure("invalid", "schema", "$")
        owned[key] = value
    return owned

def _finite_float(token):
    value = float(token)
    if not math.isfinite(value):
        raise CompileFailure("invalid", "nonfinite", "$")
    return value

def strict_loads(raw):
    text = raw.decode("utf-8", errors="strict") if type(raw) is bytes else raw
    return json.loads(
        text,
        object_pairs_hook=_pairs,
        parse_float=_finite_float,
        parse_constant=lambda _: (_ for _ in ()).throw(
            CompileFailure("invalid", "nonfinite", "$")
        ),
    )
```

Define frozen, slotted `RoleType(kind: str, value_type: str)`,
`Binder(name: str, value_type: str)`, `CompileBudget(nodes: int, depth: int,
quantifier_depth: int, work_cost: int)`, `MarkedExample(id: str, kind: str,
line: int, value: object, sha256: str)`, and `CompiledClaim(id: str,
authority: str, result_type: str)` records. `SemanticManifest` owns immutable
maps for all admitted sections. `CompileFailure` carries exact `status`,
`code`, and `path`; its string form is only `status/code:path`.

`load_manifest()` validates every exact key set, section membership,
ID uniqueness, availability value, type reference, strict integer budget, and
cross-reference before returning immutable owned tables. It must not contain
special handling for any task role or claim ID.

The versioned manifest is immutable. `load_manifest()` verifies its exact
canonical SHA-256 against the compiler's pinned Phase A manifest identity.
The compiler obtains operation arity, input patterns, output type, and work
cost from each admitted manifest entry; field result types come only from the
selected field entry. The digest seal owns precision, missing, unsupported,
and error metadata that compile-only Phase A cannot execute. Causal tests
mutate each operation field independently and require refusal, while
owned-entry tests prove the four compile-relevant fields control compilation.

- [ ] **Step 6: Run the strict-JSON and manifest-only tests to GREEN.**

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator'
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
& $python "$root/test_phase_a.py" `
  StrictJsonTests ManifestContractTests -v
if ($LASTEXITCODE -ne 0) { throw 'Phase A manifest seam failed' }
```

- [ ] **Step 7: Implement bounded static expression and claim compilation.**

First walk the owned AST to charge nodes, depth, quantifier depth, and manifest
operation cost before returning success. Dispatch only by manifest operation
ID. Use exact node-key sets:

```text
literal          op, valueType, value
role             op, role
field            op, source, name
current_item     op, name
collection_count op, args
coordinate       op, source, axis
equal            op, args
approx_equal     op, args, absoluteTolerance, relativeTolerance
and              op, args
for_all          op, source, variable, expression
```

Compilation returns only type expressions. Required rules:

```text
role -> role_ref<kind,valueType>; never valueType
field(role_ref, value) -> manifest-declared role valueType
field(point3, x|y|z) -> finite_scalar
current_item(name) -> innermost exact lexical binder element type
collection_count(collection<T>) -> integer
coordinate(point3, x|y|z) -> finite_scalar
equal(T,T) -> boolean3 only for manifest exact-comparable T
approx_equal(T,T,finite_scalar,finite_scalar) -> boolean3 for identical numeric T
and(boolean3...) -> boolean3, arity 2..8
for_all(collection<T>, binder, boolean3 body) -> boolean3
```

Unknown operation IDs are `invalid/operation_unknown`. Manifest-known
unavailable IDs are `unsupported/operation_unavailable`. Unbound,
out-of-scope, or shadowing binders are `invalid/binder_invalid`. Missing either
approximate tolerance is `invalid/tolerance_required`. No Python exception
text enters result evidence.

Caller-supplied `CompileBudget` values are optional lower ceilings only.
Every provided value is a strict positive integer with booleans refused. A
value above its manifest ceiling is `invalid/budget_override`; it is never
silently admitted or clamped upward.

`compile_claim()` applies the four-row authority matrix before accepting the
expression's compiled `boolean3` type. `compile_contract()` validates the
closed schema, unique role/claim IDs, vocabulary ID/hash, required claim set,
strict policy integers, and every role/expression reference. It returns one
ordered outcome per claim only for `compiled`; the first deterministic
`unsupported` or `invalid` prefix closes compilation.

- [ ] **Step 8: Run compiler and authority tests to GREEN.**

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator'
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
& $python "$root/test_phase_a.py" `
  ExpressionCompilerTests AuthorityCompatibilityTests -v
if ($LASTEXITCODE -ne 0) { throw 'Phase A compiler seam failed' }
```

- [ ] **Step 9: Implement marked-specification-example extraction and compilation.**

Use a line-oriented state machine, not a permissive whole-file regex. An open
marker must be followed by exactly one `json` fence, one JSON value, its fence,
and the close marker. Reject nested, duplicate, unclosed, empty, unknown-kind,
or repeated-ID examples. Inline prose containing the marker text is not a
marker because it is not the complete trimmed line.

For `kind=expression`, call `compile_expression()` under the exact four-role
environment from `point-row.valid.json` and require `boolean3`. For
`kind=claim`, call `compile_claim()` under that same environment. Retain each
example ID, kind, source line, canonical JSON SHA-256, and compiled type in the
qualification result.

Add hostile tests that mutate a temporary copy of `authoritative-spec.md` with
one bad projected collection expression, duplicate ID, malformed JSON, and
missing close marker. None may reach a successful qualification.

- [ ] **Step 10: Prove every marked valid example and the coherent fixture compile.**

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator'
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
& $python "$root/test_phase_a.py" `
  SpecificationExampleTests -v
if ($LASTEXITCODE -ne 0) { throw 'Specification example conformance failed' }
```

Expected retained IDs are exactly `point-count-expression` and
`point-count-claim`; both compile to `boolean3`. The test derives this set from
the frozen specification markers and separately asserts the reviewed expected
set, so silently deleting a marker also fails.

- [ ] **Step 11: Implement corpus execution, participant correlation, and sealed evidence.**

`prepare()` performs this create-new-only order after all source tests pass:

```text
verify specification baseline ancestry, exact one-plan delta, and clean worktree
-> verify the working specification blob matches the baseline blob
-> copy exact authoritative specification bytes
-> record exact Python path, version, and SHA-256
-> build all four participant inputs from the same manifest bytes/hash
-> encode execution-ledger.json
-> encode source-manifest.json over the complete frozen source set
-> flush/fsync each new artifact
```

Repository custody is derived, never accepted as CLI evidence. `prepare()`
receives only the repository root, exact baseline, exact specification path,
and pinned Python path. A fixed-argument, `shell=False` local Git runner
derives HEAD, ancestry, changed paths, porcelain status, baseline and working
specification blob IDs, and exact baseline blob bytes. Any mismatch refuses
before the first generated write. Tests inject a hostile fake runner and prove
that callers cannot assert clean status, ancestry, HEAD, path scope, or blob
identity. `subprocess` is permitted only inside this Git custody owner; all
network/model/Prime/Rook/Rhino/Grasshopper surfaces remain absent.

`qualify()` performs this order:

```text
verify frozen source manifest
-> load one manifest instance from exact bytes
-> verify Constructor-template and Reviewer-template inputs retain those exact bytes/hash
-> pass the same owned manifest instance to validator/corpus
-> compile every marked valid specification example
-> compile coherent fixture
-> apply and compile every isolated mutation
-> prove no Reviewer request was constructed
-> encode qualification-result.json
-> create-new write + flush + fsync
-> encode evidence-manifest.json
-> create-new write + flush + fsync
-> print exact success sentinel with result and evidence SHA-256
```

`participant-inputs.json` records exactly four ordered participants:
`constructor_template`, `reviewer_template`, `validator`, and `corpus`. Each
entry records identical manifest ID, byte length, and SHA-256. The first two
also retain the exact canonical manifest object they would receive. They do
not contain model messages or make calls.

`qualification-result.json` has exact root keys `schema`, `classification`,
`manifest`, `specification`, `coherentArtifact`, `mutations`, `contactBudget`,
and `nonclaims`. `classification` is `completed` only when every check passes.
`contactBudget` is exactly:

```json
{
  "modelCalls": 0,
  "providerCalls": 0,
  "primeCalls": 0,
  "rookMcpCalls": 0,
  "rhinoCalls": 0,
  "grasshopperCalls": 0,
  "networkCalls": 0
}
```

The nonclaims state that Phase A does not establish intent adequacy, Reviewer
sensitivity, runtime evaluation, evidence collection, router ownership,
provider behavior, or live-system behavior.

`evidence-manifest.json` contains exactly 12 entries: the ten paths in
`source-manifest.json`, `source-manifest.json` itself, and
`qualification-result.json`. It excludes itself to avoid self-hash
circularity. Every entry has exactly `path`, `bytes`, and uppercase SHA-256;
membership, size, and hash are all closed.

`audit()` independently rehashes the frozen sources and evidence, reparses all
JSON strictly, recompiles examples/fixture/corpus, and compares the complete
result object. It performs no writes.

- [ ] **Step 12: Add causal corpus, custody, and prohibited-surface tests.**

For each corpus case, assert the base still compiles, independently diff the
base and mutated structures to the declared JSON pointer, require exactly that
one changed site, and reconstruct the base from the retained pre-mutation
value to recover its exact hash. The raw-token case independently proves one
selected byte-token replacement and exact byte reversal. No helper may return
`1` merely because the corpus declares a pointer. Add mutations to the test
itself proving a wrong expected code, second changed pointer, open result key,
changed participant hash, changed manifest byte, changed specification
example, post-result evidence edit, and missing evidence entry all refuse.

`verify_file_manifest()` requires the exact expected schema. `audit()`
requires strict canonical bytes for both manifests before checking membership,
size, and hash. Fabricated schemas or trailing bytes refuse even if every entry
still matches.

Parse `phase_a.py` and `run.ps1` to prohibit network/model/host surfaces. The
closed forbidden set includes Python imports/calls `socket`, `urllib`,
`requests`, `httpx`, `aiohttp`, `ollama`, `anthropic`, `openai`,
`rook`, and PowerShell tokens `Invoke-WebRequest`, `Invoke-RestMethod`,
`Start-Process`, `rook_tools_`, `/execute`, `/gh/`, `localhost`, and `http`.
The AST test permits `subprocess` only inside the fixed Git custody function
and requires list arguments, `shell=False`, and executable token `git`.
This is a no-contact surface proof, not an OS sandbox claim.

Assert `phase_a.py` contains none of these task-local dispatch strings:

```text
point_count_equals_count
all_y_zero
all_z_zero
startControl
stepControl
countControl
points
```

Static data and tests may contain them; compiler source may not.

- [ ] **Step 13: Run the complete inert suite and require GREEN.**

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator'
$python = 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe'
& $python "$root/test_phase_a.py" -v
if ($LASTEXITCODE -ne 0) { throw 'Complete Phase A inert suite failed' }
& $python -m py_compile "$root/phase_a.py" "$root/test_phase_a.py"
if ($LASTEXITCODE -ne 0) { throw 'Phase A compilation failed' }
```

- [ ] **Step 14: Freeze the reviewed inputs without changing semantic bytes.**

Run `phase_a.py prepare`. It copies the exact authoritative specification bytes
into `authoritative-spec.md` and asserts its SHA-256 equals the specification
blob at baseline `4ec4929d8a351b022d8735c8bb9340d1968f63f0`. It records the exact execution
HEAD, baseline ancestry, exact post-baseline path list, clean-worktree status, Python
path/version/hash, specification source path/hash, manifest ID/hash/bytes, and
no-contact caps in `execution-ledger.json`.

`prepare` generates `participant-inputs.json`, then `source-manifest.json` over
exactly:

```text
authoritative-spec.md
contract.schema.json
execution-ledger.json
mutation-corpus.json
participant-inputs.json
phase_a.py
point-row.valid.json
run.ps1
semantic-manifest.json
test_phase_a.py
```

Re-run the complete suite after freezing. Do not change any listed file after
`source-manifest.json` is written. A required correction creates a fresh
successor disposable root; it does not amend frozen V1, V2, or V3 bytes.

- [ ] **Step 15: Add and run the one operator entry point.**

`run.ps1` accepts no target, model, endpoint, or credential arguments. It has
one `-Mode test|prepare|qualify|audit` parameter and invokes only the pinned
repository Python. Prepare supplies fixed repository, baseline, specification,
and Python paths; all claimed repository facts are derived by the Python
custody owner. Execute:

```powershell
$root = 'C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator'
& pwsh -NoProfile -File "$root/run.ps1" -Mode test
if ($LASTEXITCODE -ne 0) { throw 'Phase A test mode failed' }
& pwsh -NoProfile -File "$root/run.ps1" -Mode prepare
if ($LASTEXITCODE -ne 0) { throw 'Phase A prepare failed' }
& pwsh -NoProfile -File "$root/run.ps1" -Mode qualify
if ($LASTEXITCODE -ne 0) { throw 'Phase A qualification failed' }
& pwsh -NoProfile -File "$root/run.ps1" -Mode audit
if ($LASTEXITCODE -ne 0) { throw 'Phase A audit failed' }
```

The exact test sentinel is `PHASE_A_TESTS_OK`. Qualification and audit output
must match these regular languages:

```text
PHASE_A_QUALIFICATION_OK result=[0-9A-F]{64} evidence=[0-9A-F]{64}
PHASE_A_AUDIT_OK examples=2 mutations=23
```

Do not retry a failed qualification after it writes result evidence. Preserve
the prefix and stop.

- [ ] **Step 16: Perform final no-contact and repository-scope checks.**

```powershell
git -C 'C:/UDEV/Rook/.worktrees/acceptance-workflow-router-design' status --short
git -C 'C:/UDEV/Rook/.worktrees/acceptance-workflow-router-design' diff --check
Get-ChildItem Env: | Where-Object Name -Match 'ANTHROPIC|OPENAI|OLLAMA' |
  Select-Object Name
Get-ChildItem 'C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator' -Recurse -File |
  Sort-Object FullName |
  Get-FileHash -Algorithm SHA256
```

Environment-variable names may be reported; values must never be retained.
Verify no session, request, response, target, transport, PID, port, or host
artifact exists. The Rook worktree may differ from baseline only by the
already-reviewed documentation commits and this plan commit; Phase A creates
no repository diff.

- [ ] **Step 17: Stop for the single mandatory independent no-contact review.**

The reviewer independently reproduces:

```text
strict JSON and canonical-manifest admission
exact role-kind/valueType/field matrix
all ten available operation signatures
lexical quantifier custody
all four authority rows
precision, error, and budget refusal
both marked valid specification examples compiling
coherent point-row fixture compiling
all 23 isolated mutations returning exact outcomes
zero task-local compiler dispatch
zero model/provider/Prime/Rook/Rhino/Grasshopper/network surface
source and evidence manifest hashes
clean repository scope
```

No Phase B artifact, Reviewer corpus, model request, production compiler,
router plan execution, or live contact may begin from the implementer's own
result. Independent approval of Phase A authorizes only a later Phase B design
decision.

---

## Plan Self-Review Checklist

- [ ] Exactly one task and one post-qualification review gate exist.
- [ ] Every artifact outside documentation is disposable and outside the repository.
- [ ] No production file or test is named as a modification target.
- [ ] No model, provider, Prime, MCP, Rhino, Grasshopper, deployment, or network call exists.
- [ ] The manifest—not prose, claim IDs, or role IDs—owns type and operation semantics.
- [ ] The four authority modes remain distinct.
- [ ] Every specification example explicitly marked valid is executed through the same compiler.
- [ ] Every hostile case changes one declared property and asserts one exact outcome.
- [ ] `unsupported` is emitted only for a manifest-known unavailable capability.
- [ ] Phase A claims compiler coherence only, never semantic adequacy or Reviewer sensitivity.
