# LM9 Generic Task-Local Typed-Fact Carrier Implementation Plan

> **For the implementation coder:** REQUIRED SUB-SKILL: Use superpowers:executing-plans and execute this plan inline in one continuous coder context. Stop at the mandatory independent-review checkpoint after Task 1. Do not use subagent-driven development for this slice. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qualify one generic, task-local typed-fact carrier that admits open machine-keyed facts across four closed value variants, binds every fact bijectively to authority evidence, preserves the exact blocked LM9B-P observation, and emits a checksum-closed no-contact scientific witness.

**Architecture:** Add one pure neutral typed-value module under `scripts/` and one probe-owned composition module around it. The neutral module seals the JSON Schema profile, registry, type policy, budgets, typed-value equations, and proof-carrying unit-context index. The composition module owns strict byte loading, forward task-envelope validation, read-only historical reconstruction, migration/authority partitions, and deterministic fixtures. It validates recipe typed values before delegating unchanged recipe bytes to the existing mechanical gate; it does not replace or duplicate that gate. A separate qualification writer/verifier reconstructs every claim from code-owned contracts, production-pinned source evidence, the official derivative verifier, and deterministic witnesses. No product or validation-kernel code imports the scientific helper.

**Tech Stack:** Python 3.12.12 qualification environment, Python standard library (`argparse`, `dataclasses`, `hashlib`, `importlib.metadata`, `json`, `pathlib`, `platform`, `re`, `shutil`, `subprocess`, `sys`, `types`), `jsonschema==4.26.0` with `Draft202012Validator`, existing Rook canonical JSON and LM9B-P artifact/gate/verifier modules, pytest.

## Global Constraints

- Work only in `C:/UDEV/Rook/.worktrees/lm9b-p-governed-resolution-design` on `codex/lm9b-p-governed-resolution-design`; never modify, clean, reset, or rebase the primary checkout.
- Use Inline Execution. Preserve one coder's complete transition state across all tasks; do not delegate layer implementation to separate agents.
- Do not contact a model/provider, run readiness, construct a Planner/evaluator/compiler, enter checkpoint 2, or invoke Rhino/Grasshopper. All work in this plan is deterministic and no-contact.
- Preserve `C:/Users/bring/rook-lm9b-p-attempts/2026-07-22-visibility-intervention` and `C:/Users/bring/rook-lm9b-p-attempts/2026-07-22-evaluator-only-continuation/derivatives/visibility-evaluator-01` as immutable read-only evidence.
- Bind source-manifest SHA-256 `sha256:ac7716b7d5a61e2e6359bc0e01e145d7d17e0871ff03d1d5329710541d274c90`, recipe raw SHA-256 `sha256:5c5dba9def1ffc3002240f3154f02f36e60134019659d5e6a9d546b0317965af`, recipe fingerprint `sha256:eb70994fa9ead99fbe75f6f25e81327045258389d46e91474cc5b581befc068a`, and derivative identity `sha256:48bcdcb36fb3ccee49fe358335f577ffabcb83b0f74e9f84d96951d6b3950b94`.
- Keep the historical semantic-value registry and task envelope byte-for-byte unchanged. Do not add a permanent historical/legacy compatibility profile.
- Pin contracts `rook.semantic_value_schema_registry:v2`, `rook.semantic_value_schemas:v2`, `rook.planner_task_typed_facts_payload:v1`, `rook.json_schema_profile:lm9_typed_fact_v1`, `rook.lm9.semantic_typed_values:v1`, and `rook.lm9.typed_fact_carrier_qualification:v1`.
- The semantic-value registry owns value shape only. Authority/provenance remain binding-only; semantic keys remain open task-local join identities.
- Forward task facts use exactly the string, safe-integer, Boolean, and unit-sensitive scalar variants. `rook.semantic_unit_context:v1` remains separately authenticated environment authority, not a fifth fact variant.
- Do not coerce, normalize, repair, default, convert units, interpret domain keys, or compare semantic equivalence. Reject noncanonical lexical values and compare canonical bytes of exact parsed values.
- Use 1..245 machine-identifier characters for fact keys so `task-value.` plus the key never exceeds the ratified 256-character binding-ID bound.
- Keep all radial and annotation keys/values in fixture/test sources. Neutral helper and forward contract sources must contain none of them.
- The exact blocked-parent disposition is established only by the production-pinned source, official derivative verifier, unchanged mechanical gate, and shared classifier. Synthetic controls establish representation compatibility only.
- The qualification is scientific evidence, not LM9A validity, product authority, compile readiness, product compatibility, or cross-runtime portability.
- Do not modify `mcp_server/src/rook/validation_kernel/**`, `mcp_server/src/rook/**`, historical fixtures, or existing LM9B-P behavior. The sole permitted existing-script change is a tested read-only exposure of the recommendation already reconstructed by the public derivative verifier, and only if Task 5 proves its current return type cannot carry that evidence. Any broader change requires design review.

---

## File Map

- Create `scripts/lm9_semantic_typed_values.py`: pure scientific profile, registry, evaluator, typed-value, fingerprint, budget, and verified unit-context mechanics; no I/O or environment access.
- Create `scripts/lm9_typed_fact_carrier_artifacts.py`: strict byte-loading composition, code-owned contract loading, forward envelope/binding validation, historical reconstruction, authority partitioning, and witness construction.
- Create `scripts/lm9_typed_fact_carrier_qualification.py`: no-contact qualification staging, closed membership, checksum/identity sealing, independent verification, and CLI.
- Create `scripts/lm9_typed_fact_carrier_contracts/semantic_value_schema_registry.json`: exact four-entry v2 registry with self-contained schema documents and computed fingerprints.
- Create `scripts/lm9_typed_fact_carrier_contracts/planner_task_typed_facts_payload_schema.json`: exact open-key, four-field-shell forward payload schema.
- Create `scripts/lm9_typed_fact_carrier_fixtures/radial_successor_task_envelope.json`: retained historical facts represented exactly plus the five frozen radial user facts.
- Create `scripts/lm9_typed_fact_carrier_fixtures/annotation_task_envelope.json`: unrelated four-variant drawing-annotation witness.
- Create `mcp_server/tests/test_lm9_semantic_typed_values.py`: compact profile/registry/evaluator/type/unit-proof suite.
- Create `mcp_server/tests/test_lm9_typed_fact_carrier.py`: forward envelope, binding, migration, radial/annotation, source-neutrality, and outcome-neutral parent tests.
- Create `mcp_server/tests/test_lm9_typed_fact_carrier_qualification.py`: qualification closure, adversarial reclosure, no-contact boundary, and CLI tests.
- Conditionally modify `scripts/lm9b_p_evaluator_only_continuation_artifacts.py` and `mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py` only to expose the parser-derived semantic recommendation already verified inside the public derivative verifier.

### Import boundary

The new tests load scripts in this order using the established `_load_script()` pattern:

```python
SUPPORT = _load_script("lm9b_p_planner_recipe_transfer_support")
PLANNER_ARTIFACTS = _load_script("lm9b_p_planner_recipe_transfer_artifacts")
CONTINUATION = _load_script("lm9b_p_evaluator_only_continuation_artifacts")
TYPED_VALUES = _load_script("lm9_semantic_typed_values")
CARRIER = _load_script("lm9_typed_fact_carrier_artifacts")
QUALIFICATION = _load_script("lm9_typed_fact_carrier_qualification")
```

Existing modules do not import the new modules, so the current LM9B-P dynamic-loader order and provider path remain unchanged.

---

## Constructive Reachability Ledger

Shared value validation never implies that every occurrence admits the same
shape, producer, authority, or provenance. This ledger is the closed supported
surface for the slice:

| Occurrence | Real producer | Accepted shape | Authority proof | Re-verifying consumer | Final evidence |
|---|---|---|---|---|---|
| Forward fact | probe-owned deterministic fixture issuer standing in for later trusted successor ingress | exactly four fields; one of the four forward registry variants | task-envelope binding plus reverified unit-context proof for scalars | forward carrier validator | qualification radial/annotation result |
| Recipe assumption | exact existing accepted recipe bytes | exactly the current four-field assumption shape | current assumption authorization plus unchanged mechanical gate authority | shared value validator plus current recipe schema and occurrence check | compatibility result |
| Recipe derived fact | exact existing accepted recipe bytes | exactly `schema` and `value`; only registry variants admitting that two-field shape | existing derivation evidence plus unchanged mechanical gate authority | shared value validator plus current recipe schema and occurrence check | compatibility result |
| Historical task fact | exact production-pinned sealed parent task-envelope bytes | only the observed raw string/integer shapes under the exact historical payload-schema ID/fingerprint | historical value binding and artifact fingerprint | probe-local read-only reconstruction | exact migration comparison |

Anything without a complete truthful row is out of scope. In particular:

- no current scalar-derived recipe occurrence is admitted;
- no historical scalar reconstruction path exists;
- no generic value-schema membership bypasses the occurrence schema;
- no proof carrier is trusted without consumption-time reconstruction.

---

### Task 1: Walk the smallest complete no-contact qualification transaction

**Files:**
- Create: `scripts/lm9_semantic_typed_values.py`
- Create: `scripts/lm9_typed_fact_carrier_artifacts.py`
- Create: `scripts/lm9_typed_fact_carrier_qualification.py`
- Create: `scripts/lm9_typed_fact_carrier_contracts/semantic_value_schema_registry.json`
- Create: `scripts/lm9_typed_fact_carrier_contracts/planner_task_typed_facts_payload_schema.json`
- Create: `scripts/lm9_typed_fact_carrier_fixtures/radial_successor_task_envelope.json`
- Create: `scripts/lm9_typed_fact_carrier_fixtures/annotation_task_envelope.json`
- Create: `mcp_server/tests/test_lm9_typed_fact_carrier_qualification.py`

**Walking-witness interfaces:**

```python
def derive_verified_unit_context_index(...) -> VerifiedUnitContextIndex: ...
def validate_forward_task_envelope(...) -> VerifiedForwardTaskEnvelope: ...
def reconstruct_observed_historical_task_values(...) -> Mapping[str, VerifiedTypedValue]: ...
def derive_authority_partition(...) -> AuthorityPartition: ...
def build_outcome_neutral_parent_witness(...) -> OutcomeNeutralParentWitness: ...
def required_negative_case_ids() -> tuple[str, ...]: ...
def run_required_negative_cases(...) -> tuple[NegativeCaseResult, ...]: ...
def write_qualification_archive(*, repo_root: Path, destination: Path) -> VerifiedQualification: ...
def verify_qualification_archive(
    archive_dir: Path, *, expected_identity: str | None = None
) -> VerifiedQualification: ...
```

- [ ] **Step 1: Write the failing Task-1 walking witness through the real public boundary**

Create one test, `test_task1_walks_real_transition_and_publicly_verifies`, that
uses the exact production-pinned source and official derivative. It must walk
this order through the real qualification entry point:

```text
exact historical source bytes
-> code-owned registry/profile admission
-> opaque unit-context proof issuance
-> consumption-time proof re-verification
-> exact historical string/integer reconstruction
-> committed radial forward envelope validation
-> migration and authority-delta derivation
-> unchanged mechanical gate and official derivative verification
-> qualification staging/write/checksum close
-> public qualification read/reconstruction/location verification
```

Assert the returned qualification binds:

- exact historical source/recipe and derivative identities;
- `probe_candidate_blocked` and the exact unresolved-key set;
- one validated radial successor envelope;
- one validated unrelated annotation envelope through the identical carrier path;
- exact migration keys and authority delta;
- one result for every code-owned required negative-case ID, with later tasks
  independently hardening each refusal;
- false model/provider/readiness/evaluator-dispatch/compiler/Rhino/Grasshopper activity;
- physical archive location and aggregate qualification identity.

Patch actual Planner/evaluator/provider/compiler entry points to raise. The test
must still pass once implemented.

Because Task-1 code is necessarily uncommitted while its red/green test runs,
patch only the checkout-state reader to a deterministic clean test snapshot.
Do not patch source, derivative, contract, transition, archive, checksum, or
public-verifier derivations. The temporary archive is discarded and makes no
development/post-merge qualification claim. Task 6 later runs the same entry
point against a real clean committed checkout.

- [ ] **Step 2: Run the walking witness and capture the intended red state**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src')
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest mcp_server/tests/test_lm9_typed_fact_carrier_qualification.py::test_task1_walks_real_transition_and_publicly_verifies -q
```

Expected: FAIL because none of the walking-witness modules or artifacts exist.

- [ ] **Step 3: Add the thinnest code-owned contracts that admit only the reviewed happy path**

Create the exact v2 registry and forward payload schema with their final
identities and fingerprints. Implement only enough sealed-profile admission to
verify those exact code-owned documents and enforce the final four forward
value shapes. Do not add permissive fallback behavior that later tests must
remove.

- [ ] **Step 4: Implement opaque unit-context issuance and consumption-time verification first**

`VerifiedUnitContextIndex` is a non-dataclass, final, slotted opaque class:

```python
class VerifiedUnitContextIndex:
    __slots__ = ("__snapshot", "__entries", "__proof_fingerprint", "__consume")

    def __new__(cls, *args, **kwargs):
        raise TypeError("VerifiedUnitContextIndex is module-issued only")

    def __init_subclass__(cls, **kwargs):
        raise TypeError("VerifiedUnitContextIndex cannot be subclassed")

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self

    def __reduce_ex__(self, protocol):
        raise TypeError("VerifiedUnitContextIndex is not serializable")
```

The private issuer uses `object.__new__`, freezes canonical source snapshot
bytes and entries, and installs a private consumption closure bound to that
specific issued object's identity:

```python
issued = object.__new__(VerifiedUnitContextIndex)

def consume(
    candidate: VerifiedUnitContextIndex,
    _issued: VerifiedUnitContextIndex = issued,
) -> VerifiedUnitContextIndex:
    if candidate is not _issued:
        raise ValueError("unit-context proof carrier was not issued")
    return _rederive_and_compare_unit_context_index(candidate)

object.__setattr__(issued, "_VerifiedUnitContextIndex__consume", consume)
```

Every scalar consumer requires exact class and invokes that self-bound
capability. It reconstructs entries from retained environment/payload-schema/
attempt-context bytes, compares canonical entries, and recomputes the proof
fingerprint. Copying every private slot to a different exact-class object
retains a closure bound to the original and therefore fails. Neither a type
marker nor a stored fingerprint is trusted alone.

- [ ] **Step 5: Implement the thin forward/historical/migration composition**

Validate the committed radial and annotation envelopes through the same real
forward payload, registry, binding bijection, and opaque proof consumer. Bind historical
reconstruction to the exact production task-payload schema ID/fingerprint and
reject every raw type except the observed exact `str` and exact `int` shapes.
Derive migration/delta keys mechanically from authenticated parent bindings,
successor bindings, and parent unresolved rows.

- [ ] **Step 6: Implement thin outcome and qualification write/read verification**

Use `verify_historical_source()`, the unchanged mechanical gate, the official
derivative verifier, and the shared classifier. Write the final closed
qualification member names immediately; the public verifier independently
reloads contracts and source evidence and reruns the same transition. Use
sibling staging, checksum closure, location binding, and no-clobber
`Path.rename()`. Execute and record one result for every final code-owned
negative-case ID even though later tasks supply the adversarial tests that
harden those refusals. The initial public verifier reconstructs every recorded
happy-path and negative-case result; it must never trust authored result
fields.

- [ ] **Step 7: Run the walking witness green and audit the actual call order**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src')
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest mcp_server/tests/test_lm9_typed_fact_carrier_qualification.py::test_task1_walks_real_transition_and_publicly_verifies -q
git diff --check
```

Expected: one real-source, no-contact qualification write/read path passes.
Inspect the test trace/call ledger and confirm every arrow in the Task-1
transition is exercised.

- [ ] **Step 8: Commit the vertical witness and stop at the mandatory review checkpoint**

```powershell
git add scripts/lm9_semantic_typed_values.py scripts/lm9_typed_fact_carrier_artifacts.py scripts/lm9_typed_fact_carrier_qualification.py scripts/lm9_typed_fact_carrier_contracts scripts/lm9_typed_fact_carrier_fixtures mcp_server/tests/test_lm9_typed_fact_carrier_qualification.py
git commit -m "feat: walk LM9 typed-fact qualification"
git status --short --branch
```

Stop for independent review of the Task-1 evidence graph before implementing
Task 2. Do not treat a passing happy path as hardened proof closure.

---

### Task 2: Harden the JSON Schema profile and semantic-value registry

**Files:**
- Modify: `scripts/lm9_semantic_typed_values.py`
- Modify: `scripts/lm9_typed_fact_carrier_contracts/semantic_value_schema_registry.json`
- Modify: `scripts/lm9_typed_fact_carrier_contracts/planner_task_typed_facts_payload_schema.json`
- Create: `mcp_server/tests/test_lm9_semantic_typed_values.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class RuntimeIdentity:
    implementation_name: str
    implementation_cache_tag: str | None
    implementation_version: tuple[int, int, int, str, int]
    implementation_hexversion: int
    version_info: tuple[int, int, int, str, int]
    version: str
    jsonschema_version: str
    validator_class: str

@dataclass(frozen=True)
class ProfileIdentity:
    value: Mapping[str, object]
    fingerprint: str

@dataclass(frozen=True)
class AdmittedSchema:
    schema_id: str
    schema_fingerprint: str
    schema_document: Mapping[str, object]
    schema_nodes: int
    expansion_units: int

@dataclass(frozen=True)
class VerifiedSemanticValueRegistry:
    value: Mapping[str, object]
    fingerprint: str
    entries: Mapping[str, AdmittedSchema]
    profile: ProfileIdentity

def runtime_identity_from_values(
    *,
    implementation_name: str,
    implementation_cache_tag: str | None,
    implementation_version: tuple[int, int, int, str, int],
    implementation_hexversion: int,
    version_info: tuple[int, int, int, str, int],
    version: str,
    jsonschema_version: str,
) -> RuntimeIdentity: ...
def build_profile_identity(runtime: RuntimeIdentity) -> ProfileIdentity: ...
def admit_schema_document(
    value: Mapping[str, object], *, profile: ProfileIdentity
) -> AdmittedSchema: ...
def verify_semantic_value_registry(
    value: Mapping[str, object],
    *,
    raw_registry_byte_count: int,
    runtime: RuntimeIdentity,
) -> VerifiedSemanticValueRegistry: ...
def validate_schema_instance(
    instance: object,
    *,
    schema: AdmittedSchema,
    aggregate_budget: "EvaluationBudget",
    instance_path: str,
) -> tuple["ValidationIssue", ...]: ...
```

- [ ] **Step 1: Add the failing profile identity and schema-admission table**

Write one parameterized table that starts from the four reviewed schema documents and mutates one admission condition at a time:

```python
@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda s: s.update({"$schema": "https://example.invalid/schema"}), "dialect"),
        (lambda s: s.update({"$id": "rook.semantic_unknown:v1"}), "document identity"),
        (lambda s: s.update({"$ref": "#/anything"}), "keyword"),
        (lambda s: s.update({"$defs": {}}), "keyword"),
        (lambda s: s.update({"format": "decimal"}), "keyword"),
        (lambda s: s.update({"pattern": "^.*$"}), "pattern"),
    ],
)
def test_schema_profile_rejects_unsealed_documents(mutation, expected):
    schema = copy.deepcopy(_string_schema())
    mutation(schema)
    with pytest.raises(ValueError, match=expected):
        TYPED_VALUES.admit_schema_document(schema, profile=_profile())
```

Add exact assertions for profile ID/dialect, keyword sets, both patterns, no format/resolver, runtime projection, validator identity, and the exact Boolean-versus-integer type policy.

The profile manifest also pins the Draft 2020-12 metaschema fingerprint, exact structural-admission and expansion algorithm IDs, issue projection/order/truncation policy, every resource limit, `rook.schema_evaluation_shape:max_schema_or_expansion_times_instance:v1`, and the helper contract ID. No field is caller-selectable.

- [ ] **Step 2: Add failing structural budget and expansion tests**

Construct schemas at and just over each relevant bound. Pin the child-edge calculation:

```python
def test_expansion_counts_only_structural_child_schemas() -> None:
    schema = {
        "$schema": DIALECT,
        "$id": "rook.test:shape",
        "type": "object",
        "properties": {
            "a": {"type": "string", "pattern": MACHINE_KEY_PATTERN},
            "b": {"type": "string", "not": {"const": "x"}},
        },
        "propertyNames": {"pattern": MACHINE_KEY_PATTERN},
        "additionalProperties": False,
    }
    admitted = TYPED_VALUES.admit_schema_document(schema, profile=_profile())
    assert admitted.expansion_units == 4
```

Test schema depth 32/33, nodes 4,096/4,097, collection 256/257, schema string 65,536/65,537 UTF-8 bytes, canonical embedded schema bytes 65,536/65,537, expansion 32,768/32,769, per-evaluation shape 2,000,000/2,000,001, aggregate shape 16,000,000/16,000,001, and issue count 1,024/1,025. Budget exhaustion raises `InstrumentFailure`; it never returns truncated issues.

- [ ] **Step 3: Add the failing registry identity and reclosure table**

Load the code-owned registry as strict JSON and reconstruct each entry and the registry. Parameterize fully reclosed mutations for duplicate schema ID, unsorted entries, wrong schema fingerprint, wrong profile fingerprint, extra field, unknown fifth entry, and registry fingerprint drift. Recompute all caller-authored outer fingerprints so rejection depends on the code-owned contract rather than stale checksums.

Assert the entry set is exactly:

```python
{
    "rook.semantic_boolean:v1",
    "rook.semantic_integer:v1",
    "rook.semantic_scalar:v1",
    "rook.semantic_string:v1",
}
```

- [ ] **Step 4: Run the focused test and observe red**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src')
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest mcp_server/tests/test_lm9_semantic_typed_values.py -q
```

Expected: FAIL because the Task-1 walking implementation admits only the fixed
happy path and does not yet enforce the complete mutation/budget matrix.

- [ ] **Step 5: Implement sealed profile admission and work accounting**

Implement exact constants rather than caller configuration:

```python
PROFILE_ID = "rook.json_schema_profile:lm9_typed_fact_v1"
HELPER_CONTRACT_ID = "rook.lm9.semantic_typed_values:v1"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
MACHINE_KEY_PATTERN = r"^[a-z0-9]+(?:[._:-][a-z0-9]+)*$"
SCALAR_PATTERN = r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$"
ALLOWED_KEYWORDS = frozenset({
    "$schema", "$id", "type", "const", "properties", "required",
    "additionalProperties", "propertyNames", "pattern", "not",
    "minProperties", "maxProperties", "minLength", "maxLength",
    "minimum", "maximum",
})
FORBIDDEN_REFERENCE_KEYWORDS = frozenset({
    "$ref", "$dynamicRef", "$recursiveRef", "$defs", "definitions",
    "$anchor", "$dynamicAnchor",
})
```

Walk parsed schema trees with exact JSON types. Count every JSON node; treat only schema-valued `properties` members, schema-valued `additionalProperties`, `propertyNames`, and `not` as child-schema edges. Use reverse structural reachability:

```python
def _expansion(node: Mapping[str, object]) -> int:
    children = _schema_children(node)
    total = max(1, sum(_expansion(child) for child in children))
    return min(total, MAX_EXPANSION_UNITS + 1)
```

`pattern` remains an ordinary JSON node and creates no child edge or synthetic expansion. Reserve `max(schema_nodes, expansion_units) * instance_nodes` before evaluator invocation.

- [ ] **Step 6: Implement the exact evaluator/type/issue policy**

Build an explicit validator class:

```python
TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine_many({
    "object": lambda _c, value: type(value) is dict,
    "array": lambda _c, value: type(value) is list,
    "string": lambda _c, value: type(value) is str,
    "integer": lambda _c, value: type(value) is int,
    "boolean": lambda _c, value: type(value) is bool,
    "null": lambda _c, value: value is None,
})
SEALED_VALIDATOR = validators.extend(
    Draft202012Validator,
    type_checker=TYPE_CHECKER,
)
```

Instantiate with no format checker and no resolver. Project issues to bounded code-owned records sorted by instance JSON Pointer, schema JSON Pointer, failed keyword, and bounded-detail fingerprint. Raise on issue 1,025.

- [ ] **Step 7: Add exact registry and payload-schema contract files**

The registry contains four self-contained closed Draft 2020-12 documents:

- string: `schema` plus string `value`; optional unit fields must be null;
- safe integer: exact integer in `-9007199254740991..9007199254740991`; same null-unit rule;
- Boolean: exact Boolean; same null-unit rule;
- scalar: all four fields, canonical scalar pattern/maxLength/not-`-0`, `unit: model_unit`, and exact closed `artifact_value` reference.

The forward payload schema requires one `facts` member, 1..256 properties, key length 1..245, the exact key pattern, and a closed four-field minimum shell. It does not duplicate type-specific constraints or enumerate fixture keys.

Compute entry, profile, registry, and payload-schema fingerprints through canonical JSON, paste exact values into code-owned JSON, and make the loader refuse mismatch instead of repairing it.

- [ ] **Step 8: Run Task 2 green and commit**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src')
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest mcp_server/tests/test_lm9_semantic_typed_values.py -q
git diff --check
git add scripts/lm9_semantic_typed_values.py scripts/lm9_typed_fact_carrier_contracts mcp_server/tests/test_lm9_semantic_typed_values.py
git commit -m "feat: seal LM9 typed-value contracts"
```

---

### Task 3: Harden occurrence admissibility and opaque unit-context authority

**Files:**
- Modify: `scripts/lm9_semantic_typed_values.py`
- Modify: `mcp_server/tests/test_lm9_semantic_typed_values.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class VerifiedUnitContextEntry:
    artifact_id: str
    json_pointer: str
    value_schema: str
    canonical_value_bytes: bytes
    typed_value_fingerprint: str
    environment_session_id: str
    observed_at: str
    expires_at: str

class VerifiedUnitContextIndex:
    """Opaque module-issued carrier; public construction is forbidden."""

    @property
    def entries(self) -> Mapping[tuple[str, str], VerifiedUnitContextEntry]: ...

    @property
    def proof_fingerprint(self) -> str: ...

    @property
    def evaluated_at(self) -> str: ...

@dataclass(frozen=True)
class VerifiedTypedValue:
    value: Mapping[str, object]
    canonical_bytes: bytes
    fingerprint: str
    schema: AdmittedSchema

def derive_verified_unit_context_index(
    *,
    environment_artifact: Mapping[str, object],
    registered_payload_schema: Mapping[str, object],
    attempt_context: Mapping[str, object],
    expected_artifact_fingerprint: str,
    expected_environment_session_id: str,
    expected_task_session_id: str,
    evaluated_at: str,
) -> VerifiedUnitContextIndex: ...

def validate_typed_value(
    value: Mapping[str, object],
    *,
    registry: VerifiedSemanticValueRegistry,
    unit_context_index: VerifiedUnitContextIndex | None,
    required_presence: Literal["forward_fact", "recipe_assumption", "recipe_derived"],
    aggregate_budget: EvaluationBudget,
    instance_path: str,
) -> VerifiedTypedValue: ...
```

- [ ] **Step 1: Add one positive typed-value table covering every occurrence profile**

Include forward string/integer/Boolean/scalar, recipe-assumption four-field
string/scalar, and recipe-derived two-field string/integer/Boolean rows. Assert
canonical bytes/fingerprint equal existing Rook canonical JSON and validation
never changes the supplied mapping. Add two explicit unreachable-form tests:

- two-field scalar fails the scalar registry document;
- four-field scalar passes value-shape validation but fails
  `recipe_derived` occurrence admission and the current recipe schema.

No scalar-derived positive row exists.

- [ ] **Step 2: Add one parameterized lexical/type/presence mutation table**

Cover wrong type, `True` as integer, unsafe integer, unknown discriminator, extra field, inappropriate unit, missing forward fields, and:

```python
@pytest.mark.parametrize(
    "lexeme",
    ["-0", "2.0", "2.50", "02", "+2", ".5", "2.", "1e3", " 2"],
)
def test_scalar_rejects_noncanonical_lexemes(lexeme):
    with pytest.raises(ValueError):
        _validate(_scalar(lexeme))
```

Add positive `0`, `2`, `-2`, `0.5`, `-0.5`, `2.5` and 1,024/1,025-character boundary cases.

- [ ] **Step 3: Add the proof-carrying unit-context table**

Build the index from the frozen environment artifact, historical payload-schema registry entry, and attempt context. Parameterize wrong artifact fingerprint, payload schema ID/fingerprint, environment session, issuer, stale/future observation, duplicate/missing binding, wrong pointer/schema, and wrong typed-value fingerprint.

```python
def test_scalar_rejects_caller_authored_authority_dictionary():
    with pytest.raises(TypeError, match="VerifiedUnitContextIndex"):
        TYPED_VALUES.validate_typed_value(
            _scalar("2"),
            registry=_registry(),
            unit_context_index={
                ("environment_snapshot", "/document/unit_context"): {"fresh": True}
            },
            required_presence="forward_fact",
            aggregate_budget=_budget(),
            instance_path="/facts/grid_spacing",
        )

def test_exact_class_cannot_be_constructed_publicly():
    with pytest.raises(TypeError, match="module-issued"):
        TYPED_VALUES.VerifiedUnitContextIndex()

def test_unit_context_carrier_is_final_and_copy_is_identity():
    with pytest.raises(TypeError):
        class Forged(TYPED_VALUES.VerifiedUnitContextIndex):
            pass
    issued = _unit_context_index()
    assert copy.copy(issued) is issued
    assert copy.deepcopy(issued) is issued
    with pytest.raises(TypeError):
        dataclasses.replace(issued)

def test_exact_slot_clone_fails_self_bound_consumption_capability():
    cloned = _manually_allocate_exact_class_clone(_unit_context_index())
    with pytest.raises(ValueError, match="was not issued"):
        _validate(_scalar("2"), unit_context_index=cloned)

@pytest.mark.parametrize("mutation", ["entries", "proof_fingerprint", "snapshot"])
def test_consumption_rederives_opaque_carrier(mutation):
    forged = _manually_allocate_exact_class_clone(_unit_context_index())
    _force_private_slot_mutation(forged, mutation)
    with pytest.raises(ValueError, match="unit-context proof"):
        _validate(_scalar("2"), unit_context_index=forged)
```

- [ ] **Step 4: Run focused tests and observe red**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src')
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest mcp_server/tests/test_lm9_semantic_typed_values.py -q
```

Expected: new typed-value and unit-context tests FAIL.

- [ ] **Step 5: Implement occurrence-aware validation without a second representation**

Validate the exact object through its registry document, then apply only occurrence presence:

```python
if required_presence in {"forward_fact", "recipe_assumption"}:
    _require_exact_fields(value, {"schema", "value", "unit", "unit_context_ref"})
elif required_presence == "recipe_derived":
    _require_exact_fields(value, {"schema", "value"})
    if value["schema"] == "rook.semantic_scalar:v1":
        raise ValueError(
            "current recipe-derived occurrence cannot carry scalar fields"
        )
else:
    raise ValueError("unknown occurrence profile")
```

Serialize only after validation. Do not fill nulls or normalize lexemes.

- [ ] **Step 6: Implement constructive unit-context proof derivation**

Require exact artifact shape/fingerprint, registered environment payload
schema/fingerprint, payload validation, frozen sessions, trusted issuer, and
`observed_at <= evaluated_at < expires_at`. Resolve each binding pointer and
recompute its value fingerprint. Issue `VerifiedUnitContextIndex` only through
the private constructor described in Task 1.

Every scalar consumption requires exact class, immutable mapping/entry types,
the self-bound consumption capability, and full reconstruction from the retained canonical
environment/payload-schema/attempt-context snapshot. It compares rebuilt
entries and proof fingerprint before dereference. Manually allocated exact
class instances, altered private slots, copied-as-new values, replacement, and
serialization all fail or preserve object identity. The consumer never
converts `model_unit` to `millimeter`.

- [ ] **Step 7: Run Task 3 green and commit**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src')
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest mcp_server/tests/test_lm9_semantic_typed_values.py -q
git diff --check
git add scripts/lm9_semantic_typed_values.py mcp_server/tests/test_lm9_semantic_typed_values.py
git commit -m "feat: prove typed-value unit authority"
```

---

### Task 4: Harden forward envelopes, exact migration, and two unrelated witnesses

**Files:**
- Modify: `scripts/lm9_typed_fact_carrier_artifacts.py`
- Modify: `scripts/lm9_typed_fact_carrier_fixtures/radial_successor_task_envelope.json`
- Modify: `scripts/lm9_typed_fact_carrier_fixtures/annotation_task_envelope.json`
- Create: `mcp_server/tests/test_lm9_typed_fact_carrier.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class VerifiedForwardTaskEnvelope:
    envelope: Mapping[str, object]
    facts: Mapping[str, TYPED_VALUES.VerifiedTypedValue]
    bindings: Mapping[str, Mapping[str, object]]
    artifact_fingerprint: str

@dataclass(frozen=True)
class AuthorityPartition:
    parent_keys: tuple[str, ...]
    successor_keys: tuple[str, ...]
    migration_keys: tuple[str, ...]
    authority_delta_keys: tuple[str, ...]
    required_delta_keys: tuple[str, ...]
    partition_fingerprint: str

def validate_forward_task_envelope(
    raw_bytes: bytes,
    *,
    payload_schema_raw_bytes: bytes,
    registry_raw_bytes: bytes,
    unit_context_index: TYPED_VALUES.VerifiedUnitContextIndex,
    runtime: TYPED_VALUES.RuntimeIdentity,
) -> VerifiedForwardTaskEnvelope: ...

def issue_fixture_task_envelope(
    *,
    task_session_id: str,
    facts: Mapping[str, Mapping[str, object]],
    authority_by_key: Mapping[str, Mapping[str, object]],
    payload_schema: Mapping[str, object],
) -> bytes: ...

def reconstruct_observed_historical_task_values(
    source: CONTINUATION.VerifiedHistoricalSource,
    *,
    registry: TYPED_VALUES.VerifiedSemanticValueRegistry,
    unit_context_index: TYPED_VALUES.VerifiedUnitContextIndex,
) -> Mapping[str, TYPED_VALUES.VerifiedTypedValue]: ...

def derive_authority_partition(
    *,
    parent_values: Mapping[str, TYPED_VALUES.VerifiedTypedValue],
    parent_bindings: Mapping[str, Mapping[str, object]],
    successor: VerifiedForwardTaskEnvelope,
    parent_recipe: Mapping[str, object],
) -> AuthorityPartition: ...

def verify_exact_migration(
    *,
    parent_values: Mapping[str, TYPED_VALUES.VerifiedTypedValue],
    parent_bindings: Mapping[str, Mapping[str, object]],
    successor: VerifiedForwardTaskEnvelope,
    partition: AuthorityPartition,
) -> tuple[Mapping[str, object], ...]: ...

def required_negative_case_ids() -> tuple[str, ...]: ...
def run_required_negative_cases(
    *,
    runtime: TYPED_VALUES.RuntimeIdentity,
    registry_raw_bytes: bytes,
    payload_schema_raw_bytes: bytes,
    unit_context_index: TYPED_VALUES.VerifiedUnitContextIndex,
    parent_task_envelope: Mapping[str, object],
    parent_recipe: Mapping[str, object],
    radial_envelope_bytes: bytes,
    annotation_envelope_bytes: bytes,
) -> tuple["NegativeCaseResult", ...]: ...
```

- [ ] **Step 1: Add failing forward payload and bijection tests**

Create a minimal fixture-envelope builder in the test file. Assert strict duplicate JSON fact properties fail before schema validation. Parameterize invalid/246-character keys, missing/extra/duplicate bindings, unsorted UTF-16 order, binding-ID/pointer/schema/fingerprint mismatch, invalid authority/provenance, unbound fact, extra envelope field, wrong payload-schema fingerprint, and artifact-fingerprint mismatch.

Pin the maximum-key equation:

```python
def test_maximum_fact_key_produces_valid_binding_id():
    key = "a" * 245
    verified = CARRIER.validate_forward_task_envelope(
        _one_fact_envelope_bytes(key),
        payload_schema_raw_bytes=PAYLOAD_SCHEMA.read_bytes(),
        registry_raw_bytes=REGISTRY.read_bytes(),
        unit_context_index=_unit_context_index(),
        runtime=_runtime(),
    )
    binding = next(iter(verified.bindings.values()))
    assert len(binding["binding_id"]) == 256
```

- [ ] **Step 2: Add failing radial and annotation positive witnesses**

The radial fixture retains every historical task fact in exact typed form and adds only:

```python
RADIAL_DELTA = {
    "box_footprint_x": _scalar("1"),
    "box_footprint_y": _scalar("1"),
    "grid_spacing": _scalar("2"),
    "maximum_height": _scalar("10"),
    "minimum_height": _scalar("1"),
}
```

Every delta binding uses `authority_kind: user_fact`, fixture provenance, and the authenticated environment reference. This constant belongs in test/fixture data, never the production-neutral module.

The annotation fixture carries exact string, integer, Boolean, and scalar values. Assert both fixtures traverse the same `validate_forward_task_envelope()` and `validate_typed_value()` functions, and neither constructs a recipe, policy, Planner, evaluator, or provider object.

- [ ] **Step 3: Add failing migration and authority-partition tests**

Reconstruct the seven parent task facts from exact historical raw values plus bindings. Assert unitless reconstructions explicitly contain null unit fields and every reconstruction validates through registry v2.

Derive keys mechanically:

```python
assert partition.migration_keys == partition.parent_keys
assert set(partition.authority_delta_keys) == set(partition.required_delta_keys)
assert len(partition.authority_delta_keys) == 5  # fixture expectation only
```

Parameterize changed retained spelling/type/unit/context/authority/provenance, removed parent fact, extra delta key, omitted unresolved key, and delta authority changed to assumption/policy/receipt/derived. Reclose artifact fingerprints so failures prove the partition equation rather than stale identity.

Add a separate historical-adapter refusal table for a wrong payload-schema ID,
wrong payload-schema fingerprint, and injected Boolean, scalar, object, array,
or null historical value. Reclose copied outer evidence in temp directories;
the adapter must still refuse because its input must be the exact
production-pinned `VerifiedHistoricalSource` and observed raw shapes.

- [ ] **Step 4: Add the neutral-source scan and unrelated genericity check**

Scan only:

- `scripts/lm9_semantic_typed_values.py`;
- `scripts/lm9_typed_fact_carrier_artifacts.py`;
- `scripts/lm9_typed_fact_carrier_contracts/*.json`.

Reject every radial and annotation fixture key. Exclude fixtures/tests and do not scan product code. The annotation witness is the primary constructive proof; the scan is secondary.

- [ ] **Step 5: Run the carrier test and observe red**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src')
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest mcp_server/tests/test_lm9_typed_fact_carrier.py -q
```

Expected: FAIL because the Task-1 walking composition does not yet enforce the
complete binding, migration, unrelated-witness, and negative-case matrix.

- [ ] **Step 6: Implement strict byte loading and forward-envelope verification**

Reject raw registry input above 4,194,304 bytes and raw envelope input above 1,048,576 bytes before strict parsing. Then use the existing bounded strict parser, including duplicate-key refusal, and pass parsed objects into the pure helper. Validate, in order:

1. exact `rook.planner_task_envelope:v1` closed envelope shape;
2. reserved `artifact_id: task_envelope` and task session;
3. exact forward payload schema ID and code-owned fingerprint;
4. payload shell under the sealed profile;
5. every fact through registry v2 and the verified unit-context index;
6. exact binding bijection and UTF-16 order;
7. artifact fingerprint excluding only `artifact_fingerprint`.

`issue_fixture_task_envelope()` is probe-owned, accepts fully supplied facts/authority rows, selects nothing, and may issue only `deterministic_fixture` provenance. It never appears in the neutral helper.

- [ ] **Step 7: Implement read-only historical reconstruction and exact partitions**

The adapter takes a verified historical envelope and cannot write or return a successor. Reconstruct each unitless raw value:

```python
typed = {
    "schema": binding["value_schema"],
    "value": resolved_raw_value,
    "unit": None,
    "unit_context_ref": None,
}
```

Before reconstruction, require the exact production-pinned historical
task-payload schema ID and fingerprint. Admit only the exact raw `str` and exact
raw `int` fact shapes observed in that sealed envelope; reject Boolean, scalar,
object, array, null, alternate schema IDs, and every other payload schema.
There is no historical scalar branch. Validate reconstructed and successor
values independently, compare canonical bytes, then compare
authority/provenance separately.

Compute parent keys from authenticated parent bindings, successor keys from the verified successor, and required delta keys from `parent_recipe["unresolved_intent"][*]["semantic_key"]`. Never encode five or fixture keys in module logic.

- [ ] **Step 8: Harden the code-owned negative-case manifest**

Retain the stable IDs and executable builders introduced by Task 1 for every
row in Sections 17.1–17.5 of the approved design. Harden them with five
parameterized tables—registry/profile, typed value, fact/binding, unit context,
and migration/genericity—and require one exact result per ID. Every case must
demonstrate deterministic refusal after caller-authored outer identities are
reclosed. The qualification consumes this same manifest; it does not infer
coverage from pytest names.

- [ ] **Step 9: Materialize exact fixture JSON, run green, and commit**

Generate fixture candidates through `issue_fixture_task_envelope()`, inspect the diff, and commit exact closed JSON. Tests load committed bytes; they do not regenerate silently.

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src')
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest mcp_server/tests/test_lm9_semantic_typed_values.py mcp_server/tests/test_lm9_typed_fact_carrier.py -q
git diff --check
git add scripts/lm9_typed_fact_carrier_artifacts.py scripts/lm9_typed_fact_carrier_fixtures mcp_server/tests/test_lm9_typed_fact_carrier.py
git commit -m "feat: qualify generic task-local facts"
```

---

### Task 5: Prove registry migration is outcome-neutral on exact evidence

**Files:**
- Modify: `scripts/lm9_typed_fact_carrier_artifacts.py`
- Modify: `mcp_server/tests/test_lm9_typed_fact_carrier.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class OutcomeNeutralParentWitness:
    source_manifest_raw_sha256: str
    recipe_raw_sha256: str
    recipe_fingerprint: str
    typed_value_validation_fingerprint: str
    mechanical_gate_status: str
    unresolved_keys: tuple[str, ...]
    derivative_archive_identity: str
    evaluator_recommendation: str
    classification: str
    witness_fingerprint: str

@dataclass(frozen=True)
class ControlCompatibilityWitness:
    fixture_path: str
    recipe_raw_sha256: str
    assumption_count: int
    derived_fact_count: int
    gate_status: str
    typed_value_validation_fingerprint: str

def build_outcome_neutral_parent_witness(
    *,
    derivative_archive: Path,
    runtime: TYPED_VALUES.RuntimeIdentity,
) -> OutcomeNeutralParentWitness: ...

def build_control_compatibility_witness(
    recipe_path: Path,
    *,
    frozen_inputs: PLANNER_ARTIFACTS.FrozenPlannerInputs,
    registry: TYPED_VALUES.VerifiedSemanticValueRegistry,
    unit_context_index: TYPED_VALUES.VerifiedUnitContextIndex,
) -> ControlCompatibilityWitness: ...
```

- [ ] **Step 1: Add the failing exact-production parent witness**

The test calls, in order:

1. `CONTINUATION.verify_historical_source()`;
2. strict parse of exact `final_recipe_bytes` without rewriting;
3. registry-v2 validation of every assumption/derived occurrence and unresolved schema discriminator;
4. unchanged `SUPPORT.evaluate_mechanical_gate()` using frozen historical inputs;
5. `CONTINUATION.verify_sealed_derivative_archive()` at canonical destination and exact identity;
6. semantic evidence exposed by that public verifier;
7. shared `derive_evaluated_recipe_classification()` over exact recipe bytes.

Assert exact bytes/hash/fingerprint, `mechanically_accepted`, five unresolved rows, `semantically_faithful`, and `probe_candidate_blocked`. Patch provider constructors/entry points to raise and prove no provider behavior is reachable.

If the current public derivative return type does not expose its already verified parser-derived recommendation, first add a failing focused test, then add `semantic_recommendation: str | None` to `SealedDerivative` and populate it from the exact `PlannerEvaluationResult` reconstructed from captured tool arguments inside `_verify_sealed_derivative_archive()`. Do not populate it from `evaluator/result.json` and do not build a second archive verifier. This is the sole condition under which an existing LM9B-P module may be touched, and it changes no provider or classification behavior.

- [ ] **Step 2: Add accepted assumption/derived-value control witnesses**

Use `scripts/lm9b_c_fixtures/r01_recipe.json` plus one accepted non-R01 fixture containing derived facts. Assert every assumption uses `recipe_assumption`, every derived fact uses `recipe_derived`, historical two-field derived values remain admitted, and the existing gate disposition remains unchanged.

These controls prove representation compatibility only.

- [ ] **Step 3: Add adversarial source/derivative/typed-value binding tests**

Use temp copies only. Mutate copied recipe/authority/control evidence and reclose caller-authored fingerprints. Assert refusal because public source pins, official destination binding, exact bytes, v2 validation, or shared classification derivation fails. Never write either production archive.

- [ ] **Step 4: Run focused tests and observe red**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src')
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest mcp_server/tests/test_lm9_typed_fact_carrier.py -q
```

Expected: new outcome-neutral witness tests FAIL.

- [ ] **Step 5: Implement composition without changing or shadowing the gate**

The carrier validates typed values and packages evidence, then delegates the full recipe decision to the existing gate. Do not copy recipe schema, authority binding, normalization, fingerprint, blocker, or classification equations. Require gate `final_recipe_bytes` byte-equal to source.

The public derivative verifier remains the only semantic-result route. Any tiny read-only result exposure is tested in `mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py` and preserves archive verification equations exactly.

- [ ] **Step 6: Run Task 5 green and commit**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src')
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest mcp_server/tests/test_lm9_semantic_typed_values.py mcp_server/tests/test_lm9_typed_fact_carrier.py mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py -q
git diff --check
git add scripts/lm9_typed_fact_carrier_artifacts.py mcp_server/tests/test_lm9_typed_fact_carrier.py
git add scripts/lm9b_p_evaluator_only_continuation_artifacts.py mcp_server/tests/test_lm9b_p_evaluator_only_continuation.py
git commit -m "test: prove typed-fact migration neutrality"
```

If the conditional public-return exposure was unnecessary, the second `git add` has no paths to stage and must be omitted.

---

### Task 6: Harden and independently verify the no-contact qualification witness

**Files:**
- Modify: `scripts/lm9_typed_fact_carrier_qualification.py`
- Modify: `mcp_server/tests/test_lm9_typed_fact_carrier_qualification.py`

**Interfaces:**

```python
QUALIFICATION_SCHEMA_ID = "rook.lm9.typed_fact_carrier_qualification:v1"

@dataclass(frozen=True)
class QualificationSnapshot:
    commit_sha: str
    runtime: TYPED_VALUES.RuntimeIdentity
    helper_source_sha256: str
    profile_fingerprint: str
    registry_fingerprint: str
    payload_schema_fingerprint: str
    clean_checkout: bool
    snapshot_fingerprint: str

@dataclass(frozen=True)
class VerifiedQualification:
    archive_dir: Path
    qualification_identity: str
    snapshot: QualificationSnapshot
    record: Mapping[str, object]

def build_qualification_snapshot(*, repo_root: Path) -> QualificationSnapshot: ...
def write_qualification_archive(
    *, repo_root: Path, destination: Path
) -> VerifiedQualification: ...
def verify_qualification_archive(
    archive_dir: Path,
    *,
    expected_identity: str | None = None,
) -> VerifiedQualification: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

Closed membership:

```text
record.json
snapshot.json
contracts/profile.json
contracts/semantic-value-registry.json
contracts/task-payload-schema.json
source/historical-binding.json
source/derivative-binding.json
results/blocked-parent.json
results/control-compatibility.json
results/radial-witness.json
results/annotation-witness.json
results/negative-cases.json
boundary.json
checksums.json
```

- [ ] **Step 1: Extend the Task-1 walking witness with failing full-closure assertions**

Retain the Task-1 real entry-point/public-verifier test and add exact
schema/membership, commit/clean checkout, runtime/`jsonschema`, helper/profile/
registry/payload/source/derivative, parent, radial/annotation, complete negative
case, and boundary assertions. Boundary facts are false for model, provider,
readiness, evaluator dispatch, compiler, Rhino, Grasshopper, and product
authority; archived evaluator evidence verification remains present and is not
misreported as a dispatch.

- [ ] **Step 2: Add the adversarial fully reclosed qualification table**

For each mutation, recompute every affected record fingerprint, checksum, and aggregate identity, then require refusal:

- helper source fingerprint;
- profile/runtime/jsonschema/type-policy;
- registry/schema/payload schema;
- omitted or renamed negative case;
- parent classification or unresolved keys;
- radial/annotation result;
- migration/authority partition;
- official source/derivative identity;
- provider-activity flag;
- extra member;
- copied archive at a different physical path.

The verifier reconstructs from code-owned/current-checkout sources and public evidence verifiers; it never accepts a self-consistent checksum story.

- [ ] **Step 3: Add runtime drift, dirty-checkout, no-overwrite, and CLI tests**

Patch runtime after snapshot and require pre-evaluation refusal. Patch `git status --porcelain` nonempty. Precreate destination and require `FileExistsError`. Assert CLI accepts only `qualify` and `verify` and exposes no model/provider/readiness/evaluator/Planner/compiler/handoff argument.

Patch actual model/provider/compiler-specific entry points imported by LM9B-P to raise. Qualification remains green, proving behavioral isolation despite generic dependency locations.

- [ ] **Step 4: Run qualification tests and observe red**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src')
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest mcp_server/tests/test_lm9_typed_fact_carrier_qualification.py -q
```

Expected: FAIL because the Task-1 qualification path does not yet enforce the
complete adversarial reclosure, runtime-drift, membership, CLI, and fault
matrix.

- [ ] **Step 5: Implement frozen snapshot and no-clobber lifecycle**

The exact operation order is:

1. resolve repo/destination absolutely;
2. require designated runtime and clean `HEAD` snapshot;
3. recompute helper/profile/registry/payload/source/derivative identities;
4. atomically create sibling staging with `exist_ok=False`;
5. persist/reread `snapshot.json` exactly;
6. run deterministic witnesses from the verified snapshot and immutable public evidence paths;
7. write results/checksums/aggregate;
8. privately verify staging with location relaxation only;
9. finalize with Windows no-clobber `Path.rename()` on the same filesystem;
10. publicly verify at destination.

Never use `Path.replace()`. If destination appears before rename, retain staging and fail. With no dispatch, pre-seal failure makes no scientific claim.

- [ ] **Step 6: Implement constructive public verification**

Require physical location equality, closed membership, checksum closure, actual checkout/runtime/helper identity, exact code-owned contracts, official source/derivative public verification, and complete reconstruction of parent/control/radial/annotation/migration/negative results. Compare every derived record byte-for-byte.

- [ ] **Step 7: Run all new focused tests green**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src')
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest mcp_server/tests/test_lm9_semantic_typed_values.py mcp_server/tests/test_lm9_typed_fact_carrier.py mcp_server/tests/test_lm9_typed_fact_carrier_qualification.py -q
```

- [ ] **Step 8: Run existing LM9B-P regression family**

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src')
$lm9bPTests = Get-ChildItem 'mcp_server/tests' -Filter 'test_lm9b_p_*.py' | ForEach-Object FullName
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m pytest @lm9bPTests -q
```

Expected: all existing tests pass unchanged.

- [ ] **Step 9: Compile, inspect scope, and verify boundaries**

```powershell
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' -m py_compile scripts/lm9_semantic_typed_values.py scripts/lm9_typed_fact_carrier_artifacts.py scripts/lm9_typed_fact_carrier_qualification.py
rg -n "box_footprint_x|box_footprint_y|grid_spacing|minimum_height|maximum_height|annotation_text|annotation_count|leaders_enabled|text_height" scripts/lm9_semantic_typed_values.py scripts/lm9_typed_fact_carrier_artifacts.py scripts/lm9_typed_fact_carrier_contracts
rg -n "litellm|Provider|planner_session|compiler|handoff|Rhino|Grasshopper" scripts/lm9_semantic_typed_values.py scripts/lm9_typed_fact_carrier_artifacts.py scripts/lm9_typed_fact_carrier_qualification.py
git diff --check
git status --short
```

Expected: compilation/diff pass; fixture-key scan has no matches; boundary-word matches are refusal/non-claim data only.

- [ ] **Step 10: Commit the qualification implementation**

```powershell
git add scripts/lm9_typed_fact_carrier_qualification.py mcp_server/tests/test_lm9_typed_fact_carrier_qualification.py
git commit -m "feat: seal typed-fact qualification witness"
git status --short --branch
```

Expected: clean branch. The exact-production witness can now truthfully bind the committed feature `HEAD`.

- [ ] **Step 11: Emit and verify one exact-production development qualification**

Use an external development-only root and current feature `HEAD`:

```powershell
$env:PYTHONPATH = (Resolve-Path 'mcp_server/src')
$devRoot = 'C:/Users/bring/rook-lm9b-p-attempts/2026-07-23-typed-fact-carrier-development'
New-Item -ItemType Directory -Path $devRoot -Force | Out-Null
$devDestination = Join-Path $devRoot (git rev-parse HEAD)
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' scripts/lm9_typed_fact_carrier_qualification.py qualify --repo-root (Resolve-Path '.') --destination $devDestination
& 'C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe' scripts/lm9_typed_fact_carrier_qualification.py verify --archive $devDestination
```

Expected: one verified no-contact development qualification bound to exact production source/derivative evidence. Record identity in the PR description, not a product contract. If destination exists, use a new explicitly named development destination; never overwrite.

- [ ] **Step 12: Stop for independent review**

```powershell
git status --short --branch
```

Expected: clean branch and verified development witness. If the witness exposed a defect, fix it test-first, create a new commit, and emit a new witness at a new destination bound to that commit. Do not push, open a PR, merge, or begin governed resolution without explicit instruction.

---

## Final Review Ledger

| Claim | Authority source | Independent reconstruction |
|---|---|---|
| Profile identity | code-owned constants + exact runtime | rebuild manifest and fingerprint |
| Registry identity | code-owned schema documents | admit documents, recompute entry and registry fingerprints |
| Typed value | exact parsed object | sealed evaluator + canonical bytes |
| Unit authority | frozen environment artifact/bindings/session/time | rebuild `VerifiedUnitContextIndex` |
| Fact authority | successor fact + binding | bijection, pointer, schema, fingerprint, provenance |
| Representation migration | historical raw value/binding + successor typed value | validate both and compare canonical bytes |
| Authority delta | parent bindings + unresolved rows + successor bindings | derive all key sets and compare |
| Parent disposition | production source + official derivative + unchanged gate/classifier | public verifiers and shared equations |
| Genericity | radial + unrelated fixtures | identical carrier path plus neutral-source scan |
| Qualification identity | every reconstructed result | membership, checksums, aggregate, physical location |

Hard stop if a row is accepted only because one authored report field agrees with another authored report field.

## Post-Merge Boundary

After independent review and merge:

1. Create a clean worktree at the reviewed merge SHA.
2. Re-run the no-contact qualification under that exact interpreter/runtime.
3. Review its exact qualification identity and archive closure.
4. Do not perform model contact.
5. Resume separately scoped governed-resolution brainstorming from the locked immutable-parent, successor-envelope, one-Planner-attempt, and exact-isolation decisions.

The development qualification is never promoted as the post-merge qualification because its reviewed commit differs.
