# LM9A Validation Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the reusable, model-free LM9A validation kernel that accepts untrusted recipe bytes plus a trusted host-issued validation bundle, executes one sealed validation program over owned immutable values, and emits either a deterministic report or the earliest honest typed control failure.

**Architecture:** Add a new `rook.validation_kernel` package with four explicit layers: bounded byte ingress and canonical identity, a sealed immutable `ValidationProgram`, a typed phase engine with exact named dataflow, and deterministic report/conformance sealing. The kernel knows no Planner recipe semantics. LM9A semantic schemas, phase runners, fixtures, and report projection remain a later contribution and a separate implementation plan.

**Tech Stack:** Python 3.10, pytest, standard-library hashing/tokenization/introspection, exact RFC 8785 JSON canonicalization implemented in-repo, and the already-installed schema stack pinned directly as `jsonschema==4.26.0`, `referencing==0.37.0`, and `jsonschema-specifications==2025.9.1`.

## Global Constraints

- Design authority is [2026-07-13-lm9a-validation-kernel-design.md](../specs/2026-07-13-lm9a-validation-kernel-design.md). If this plan conflicts with that spec, stop and amend the spec before implementation.
- This plan implements LM9A-Kernel only. Do not implement `rook.planner_graph_recipe:v1`, recipe authority rules, assumptions, clauses, capabilities, worker slots, radial fixtures, the layer-control fixture, or the semantic validation report.
- Do not write the LM9A-Semantics implementation plan during this execution slice.
- The only untrusted artifact argument is exact built-in recipe `bytes`. Validation-bundle bytes enter only through a host-issued `TrustedValidationBundleInput` capability.
- No public MCP tool, HTTP route, `server.py` dispatch, model, worker, compiler, Rhino process, Grasshopper process, or live run is part of this plan.
- The kernel executes reviewed, fingerprinted Python runners and the schema library in process. It must not claim OS-enforced CPU, memory, file, or network isolation.
- Kernel-controlled limits are exact and inclusive. Every limit has an exact-boundary and limit-plus-one test.
- The parser must not use `json.loads`, `ast.literal_eval`, YAML, or a third-party parser. It owns tokenization, limits, duplicate detection, and iterative tree construction before a host object graph can grow without accounting.
- `rook.canonical_json:v1` is exact RFC 8785/JCS. It is a new artifact regime and must not import, copy, or call `_fingerprint_normalized_contract` or any LM4X/LM5/LM8 fingerprint helper.
- Product safe-integer validation is separate from JCS serialization. The canonicalizer must support the full finite RFC 8785 number domain, including integer-form `9007199254740992` in embedded schemas.
- The fixed program seal uses its own reference canonicalizer binding. A candidate program's runtime canonicalizer cannot certify its own manifest.
- There is one invocation-owned budget ledger. Runners cannot author, refund, replace, or report work counts.
- A `SealedValidationProgram`, `SealedTrustedBundleAssemblerProfile`, and `SealedConformanceGateProfile` are immutable runtime capabilities, not deserializable claims.
- Runtime dispatch never rediscovers callables, schemas, profiles, issue codes, or report projections from global registries after sealing.
- Every phase input names one exact producer and output. A promised output missing from a passed or blocked provider is `validator_integrity_failure`, not ordinary dependency suppression.
- No partial semantic report or conformance report is published after an integrity, constructability, or report-seal failure.
- The conformance campaign can require a release-owned gate profile fingerprint but cannot select or construct the gate that certifies it.
- Unrelated local knowledge drift and untracked roadmap/probe files remain untouched and unstaged.
- No new third-party package is introduced. The three schema packages already exist in `uv.lock`; this plan makes their current versions exact direct dependencies so runtime identity is intentional.

## Fixed Budget Profile

Implement `rook.validation_budget:lm9a_v1` exactly:

| Dimension | Inclusive limit |
|---|---:|
| recipe input bytes | 1,048,576 |
| validation-bundle input bytes | 4,194,304 |
| JSON container depth per artifact | 64 |
| JSON number-token characters | 1,024 |
| aggregate parsed nodes | 100,000 |
| members in one object | 16,384 |
| items in one array | 16,384 |
| aggregate decoded UTF-8 string bytes | 2,097,152 |
| aggregate tokenizer/parser work units | 500,000 |
| registered semantic references | 25,000 |
| aggregate schema-evaluation shape units | 16,000,000 |
| diagnostics | 1,024 |
| compile blockers | 1,024 |
| kernel/cooperative phase work units | 1,000,000 |
| report canonical bytes | 2,097,152 |
| report projection fields | 131,072 |
| fixed report-seal allowance work units | 262,144 |

## File Structure

**Create: `mcp_server/src/rook/validation_kernel/__init__.py`**

Exports only the stable composition, trust-carrier, validation, and conformance APIs. Internal builders, issuer tokens, mutable ledgers, parser frames, and seal meters remain private.

**Create: `mcp_server/src/rook/validation_kernel/owned_json.py`**

Owns transitively immutable `JsonNull`, `JsonBoolean`, `JsonString`, `JsonNumber`, `JsonArray`, and `JsonObject` values; read-only mapping/sequence behavior; iterative node counting; exact JSON Pointer lookup; and trusted internal conversion from closed built-in JSON values.

**Create: `mcp_server/src/rook/validation_kernel/canonical_json.py`**

Owns RFC 8785 UTF-16 key ordering, ECMAScript-compatible finite-number formatting, exact canonical UTF-8 bytes, prefixed SHA-256 fingerprints, and LF-normalized source/distribution hashing primitives.

**Create: `mcp_server/src/rook/validation_kernel/budget.py`**

Owns the fixed budget manifest, one mutable invocation ledger, checked schema-shape reservations, immutable snapshots/receipts, and the separate fixed-allowance `SealMeter`.

**Create: `mcp_server/src/rook/validation_kernel/control.py`**

Owns the six stable kernel control codes, closed artifact/stage/dimension vocabularies, deterministic 512-code-point message bounding, variable-detail hashing, and the immutable `ValidationControlFailure` union used before a principal report can exist.

**Create: `mcp_server/src/rook/validation_kernel/parser.py`**

Owns strict bounded UTF-8 tokenization and iterative JSON parsing. It produces only owned JSON values or bounded parse evidence and charges the invocation ledger before allocation/attachment.

**Create: `mcp_server/src/rook/validation_kernel/schema_profile.py`**

Owns core/payload schema-profile admission, local-reference graph checks, exact schema/instance node accounting, the immutable schema registry, the no-retrieval Draft 2020-12 adapter, and schema-evaluation receipts.

**Create: `mcp_server/src/rook/validation_kernel/phase_contract.py`**

Owns closed `PhaseSpec`, input/output binding, issue vocabulary, export type, runner binding, constructability-shell, and report-projection declarations used by program sealing and the engine.

**Create: `mcp_server/src/rook/validation_kernel/kernel_schemas.py`**

Owns the fixed bootstrap schemas and fingerprints for program manifests, trusted assembler profiles, conformance gate profiles, campaigns, generic conformance fixture manifests, and aggregate reports. These are kernel/release schemas only, never Planner recipe or companion schemas.

**Create: `mcp_server/src/rook/validation_kernel/program.py`**

Owns fixed bootstrap seal authority, source/runtime dependency identity, candidate contribution validation, one-shot composition, canonical manifest construction, and `SealedValidationProgram`.

**Create: `mcp_server/src/rook/validation_kernel/invocation.py`**

Owns trusted assembler-profile sealing, bundle-carrier issuance, byte admission, bundle-first parsing, report-constructability preflight, immutable `ValidationInvocation`, and pre-report control failures.

**Create: `mcp_server/src/rook/validation_kernel/phase_engine.py`**

Owns DAG derivation from exact bindings, deterministic scheduling, runner dispatch, issue/output integrity, immutable phase results, and engine-derived status/work deltas.

**Create: `mcp_server/src/rook/validation_kernel/reporting.py`**

Owns projection-envelope construction, fixed seal reservation, one-shot report fingerprinting, final canonical bytes, and published-report carriers.

**Create: `mcp_server/src/rook/validation_kernel/api.py`**

Owns the formal `validate_artifacts(...)` orchestration entrypoint and its closed result union.

**Create: `mcp_server/src/rook/validation_kernel/conformance.py`**

Owns release gate-profile sealing, campaign admission, earliest-honest gate failures, trusted artifact resolution, case execution, exact schema-attempt accounting, aggregate completeness, report sealing, and `TrustedConformanceGateResult`.

**Modify: `mcp_server/pyproject.toml`**

Pins the existing schema runtime as exact direct dependencies.

**Modify: `mcp_server/uv.lock`**

Records those direct dependency edges without changing their resolved versions.

**Create: `mcp_server/tests/fixtures/validation_kernel/jcs_vectors.json`**

Contains checked-in RFC 8785 canonicalization vectors and boundary vectors, including UTF-16 key order, escapes, `-0`, exponent formatting, and finite integer-form values beyond the product safe-integer range.

**Create: `mcp_server/tests/fixtures/validation_kernel/jcs_number_vectors.jsonl`**

Contains a deterministic cross-runtime corpus of finite binary64 bit patterns and their ECMAScript `JSON.stringify` number spellings.

**Create: `mcp_server/tests/fixtures/validation_kernel/generate_jcs_number_vectors.mjs`**

Regenerates the corpus with the checked-in seed and Node's ECMAScript serializer. Node is a fixture-generation/review oracle only, never a product or runtime dependency.

**Create: `mcp_server/tests/fixtures/validation_kernel/parser_corpus.jsonl`**

Contains bounded accepted/rejected raw JSON cases with expected canonical fingerprints or stable parser categories.

**Create: `mcp_server/tests/_validation_kernel_fakes.py`**

Contains module-level, no-closure synthetic runners, export validators, report projections, immutable artifact-store fakes, and composition helpers. It contains no LM9A domain terms.

**Create: `mcp_server/tests/_validation_kernel_replay_driver.py`**

Builds the exact synthetic sealed program used by the boundary campaign and emits one canonical single-line replay bundle containing the exact program-manifest, validation-report, campaign-report, and fingerprint evidence. It is a subprocess-test driver only and contains no clock, process ID, temporary path, or other ambient process data.

**Create tests:**

- `mcp_server/tests/test_validation_kernel_owned_json.py`
- `mcp_server/tests/test_validation_kernel_canonical_json.py`
- `mcp_server/tests/test_validation_kernel_budget.py`
- `mcp_server/tests/test_validation_kernel_parser.py`
- `mcp_server/tests/test_validation_kernel_schema_profile.py`
- `mcp_server/tests/test_validation_kernel_program.py`
- `mcp_server/tests/test_validation_kernel_invocation.py`
- `mcp_server/tests/test_validation_kernel_phase_engine.py`
- `mcp_server/tests/test_validation_kernel_reporting.py`
- `mcp_server/tests/test_validation_kernel_api.py`
- `mcp_server/tests/test_validation_kernel_conformance.py`
- `mcp_server/tests/test_validation_kernel_boundaries.py`

**Dependency direction:**

```text
owned_json <- canonical_json
owned_json + canonical_json <- control + budget + parser
owned_json + budget <- schema_profile
owned_json + canonical_json <- kernel_schemas
phase_contract + schema_profile + kernel_schemas + canonical_json <- program
program + parser + control + budget <- invocation
program + invocation + phase_contract <- phase_engine
program + invocation + phase_engine + canonical_json <- reporting
invocation + phase_engine + reporting <- api
api + schema_profile + program + canonical_json <- conformance
```

No lower layer imports `api`, `conformance`, `rook.agent`, or product server code. `__init__.py` re-exports completed public symbols only and contains no runtime registry.

---

### Task 1: Build Owned JSON Values And Exact RFC 8785 Canonicalization

**Files:**
- Create: `mcp_server/src/rook/validation_kernel/__init__.py`
- Create: `mcp_server/src/rook/validation_kernel/owned_json.py`
- Create: `mcp_server/src/rook/validation_kernel/canonical_json.py`
- Create: `mcp_server/tests/fixtures/validation_kernel/jcs_vectors.json`
- Create: `mcp_server/tests/fixtures/validation_kernel/jcs_number_vectors.jsonl`
- Create: `mcp_server/tests/fixtures/validation_kernel/generate_jcs_number_vectors.mjs`
- Create: `mcp_server/tests/test_validation_kernel_owned_json.py`
- Create: `mcp_server/tests/test_validation_kernel_canonical_json.py`

**Interfaces:**

```python
JsonValue = Union[
    JsonNull,
    JsonBoolean,
    JsonString,
    JsonNumber,
    JsonArray,
    JsonObject,
]

def own_trusted_json(value: object) -> JsonValue: ...
def _seal_object_members(members: tuple[tuple[JsonString, JsonValue], ...]) -> JsonObject: ...
def lookup_json_pointer(root: JsonValue, pointer: str) -> JsonValue: ...
def count_json_nodes(root: JsonValue) -> int: ...

def utf16_sort_key(value: str) -> bytes: ...
class CanonicalByteSink(Protocol):
    def write(self, chunk: bytes) -> None: ...

def write_canonical_json(value: JsonValue, sink: CanonicalByteSink) -> None: ...
def canonical_json_bytes(value: JsonValue, *, max_bytes: int | None = None) -> bytes: ...
def canonical_fingerprint(value: JsonValue) -> str: ...
def sha256_prefixed(data: bytes) -> str: ...
def normalized_source_fingerprint(source_bytes: bytes) -> str: ...
```

- [ ] **Step 1: Write failing owned-value tests**

Cover exact built-in input types, immutable tuples, read-only mapping/sequence access, no mutable storage reachable through public attributes, iterative node count, valid RFC 6901 lookup, invalid escapes, and pointer-not-found behavior. An exact built-in `dict` cannot represent duplicate keys after construction, so `own_trusted_json` has no pretend duplicate-key test. Test duplicate member rejection through the private pair-oriented `_seal_object_members(...)` boundary used by the parser; Task 3 separately proves duplicate rejection from raw JSON bytes.

```python
def test_owned_tree_is_transitively_immutable():
    value = own_trusted_json({"a": [{"b": 1}]})
    assert isinstance(value, JsonObject)
    assert isinstance(value["a"], JsonArray)
    with pytest.raises(TypeError):
        value["a"][0]["b"] = 2


def test_trusted_conversion_rejects_non_json_host_scalars():
    for value in (Decimal("1"), b"x", bytearray(b"x"), {1, 2}):
        with pytest.raises(OwnedJsonTypeError):
            own_trusted_json(value)
```

- [ ] **Step 2: Run the owned-value tests and confirm the intended failure**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_owned_json.py -q
```

Expected: FAIL because `rook.validation_kernel.owned_json` does not exist.

- [ ] **Step 3: Implement the immutable value graph**

Use exact closed types. `JsonObject` stores UTF-16-key-sorted `(JsonString, JsonValue)` tuples and performs lookup by binary search over a parallel immutable key tuple; it contains no hidden `dict`. `JsonArray` stores a tuple. `JsonString` is immutable and preserves exact code points. `JsonNumber` stores one finite IEEE-754 binary64 value plus source-token classification for parser evidence; it does not enforce product safe-integer policy.

`own_trusted_json` is for trusted composition only. It accepts exact `dict`, `list`, `tuple`, `str`, `bool`, `int`, `float`, and `None`, walks iteratively, rejects aliases/cycles, non-finite values, non-string object keys, unsupported subclasses, and non-JSON scalar types, then creates an owned graph. It is not exposed as validation ingress.

- [ ] **Step 4: Add official and boundary JCS tests before implementing serialization**

The checked-in vector table must include at least:

```json
[
  {"name":"negative_zero","input":"-0","canonical":"0"},
  {"name":"fraction","input":"4.50","canonical":"4.5"},
  {"name":"small_decimal","input":"2e-3","canonical":"0.002"},
  {"name":"small_exponent","input":"1e-27","canonical":"1e-27"},
  {"name":"large_exponent","input":"1E30","canonical":"1e+30"},
  {"name":"rounded_binary64","input":"333333333.33333329","canonical":"333333333.3333333"},
  {"name":"schema_integer_above_product_safe_range","input":"9007199254740992","canonical":"9007199254740992"}
]
```

Also test RFC 8785 UTF-16 object-key ordering with BMP and supplementary-plane keys, JSON control escaping, UTF-8 output without BOM, lowercase `sha256:` fingerprints, and rejection of `NaN`/infinities. Assert that NFC normalization is not silently performed by the canonicalizer.

Generate and check in 20,000 deterministic finite binary64 cases from exact 64-bit patterns, including signed zero, subnormals, normal exponent boundaries, maximum finite values, and a fixed-seed pseudorandom sample. Each row stores the hexadecimal bit pattern and exact `JSON.stringify` spelling. Pytest consumes the checked-in corpus without invoking Node.

The corpus must also contain named directed groups, not merely values that happen to occur in the pseudorandom sample. For each finite threshold value, include its exact binary64 representation and the adjacent finite values from `nextDown` and `nextUp` where they exist:

```text
decimal fixed/exponent transition: 1e-6
large fixed/exponent transition: 1e21
integer precision transition: 2^53
minimum subnormal and its next value
maximum subnormal, minimum normal, and both sides of that boundary
maximum finite value and its previous value
shortest-round-trip halfway/tie cases from the RFC 8785 number corpus
```

The generator assigns a stable `group` and `case_id` to every directed vector. Pytest asserts every required group and neighbor relation is present before checking spellings, so a generator regression cannot silently leave only the random corpus.

The generator must reproduce the file byte-for-byte under the installed Node runtime:

```powershell
node mcp_server/tests/fixtures/validation_kernel/generate_jcs_number_vectors.mjs --check
```

- [ ] **Step 5: Implement exact JCS serialization**

Implement a non-recursive serializer over owned values that writes bounded chunks to `CanonicalByteSink`. Object keys use RFC 8785 section 3.2.3 UTF-16 code-unit order. Strings use the RFC escaping rules. Numbers use an in-repo ECMAScript-compatible binary64 formatter proven by the fixture vectors; do not call `json.dumps` for final number or object serialization. Integers supplied by trusted composition enter the finite binary64 domain before serialization, so integer and float host forms with the same RFC value serialize identically. `canonical_json_bytes(..., max_bytes=N)` charges/checks before appending each chunk and never builds an over-limit full buffer.

Keep product-domain validation out of this module. `canonical_json_bytes(own_trusted_json(9007199254740992))` must succeed.

- [ ] **Step 6: Run the focused tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_owned_json.py mcp_server/tests/test_validation_kernel_canonical_json.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```powershell
git add mcp_server/src/rook/validation_kernel/__init__.py mcp_server/src/rook/validation_kernel/owned_json.py mcp_server/src/rook/validation_kernel/canonical_json.py mcp_server/tests/fixtures/validation_kernel/jcs_vectors.json mcp_server/tests/fixtures/validation_kernel/jcs_number_vectors.jsonl mcp_server/tests/fixtures/validation_kernel/generate_jcs_number_vectors.mjs mcp_server/tests/test_validation_kernel_owned_json.py mcp_server/tests/test_validation_kernel_canonical_json.py
git commit -m "feat: add immutable JSON and JCS kernel"
```

---

### Task 2: Implement The Fixed Budget Manifest And Single-Owned Ledger

**Files:**
- Create: `mcp_server/src/rook/validation_kernel/budget.py`
- Create: `mcp_server/src/rook/validation_kernel/control.py`
- Create: `mcp_server/tests/test_validation_kernel_budget.py`
- Modify: `mcp_server/src/rook/validation_kernel/__init__.py`

**Interfaces:**

```python
LM9A_BUDGET_PROFILE_ID = "rook.validation_budget:lm9a_v1"
KERNEL_CONTROL_CODES = (
    "validation_input_invalid",
    "validation_budget_exceeded",
    "validation_constructability_failed",
    "validator_identity_unavailable",
    "validator_integrity_failure",
    "validator_internal_failure",
)

@dataclass(frozen=True)
class ValidationControlFailure:
    failure_stage: str
    code: str
    artifact_role: str
    program_id: str | None
    program_fingerprint: str | None
    subject_path: str | None
    message: str
    detail_sha256: str | None

@dataclass(frozen=True)
class BudgetExceededFailure(ValidationControlFailure):
    budget_dimension: str
    limit: int
    observed_lower_bound: int

@dataclass(frozen=True)
class BudgetManifest:
    profile_id: str
    limits: JsonObject
    limits_fingerprint: str

@dataclass(frozen=True)
class BudgetSnapshot: ...

@dataclass(frozen=True)
class BudgetReceipt: ...

@dataclass(frozen=True)
class SchemaShapeReservation:
    accepted: bool
    shape_metric_id: str
    schema_nodes: int
    evaluation_expansion_units: int
    shape_basis_units: int
    instance_nodes: int
    attempted_shape_units: int | None
    aggregate_before: int
    aggregate_after: int | None
    rejection_reason: str | None

class BudgetLedger:
    def charge(self, dimension: BudgetDimension, amount: int, *, artifact_role: str, subject_path: str | None) -> None: ...
    def reserve_schema_shape(self, *, schema_nodes: int, evaluation_expansion_units: int, instance_nodes: int, per_evaluation_limit: int) -> SchemaShapeReservation: ...
    def snapshot(self) -> BudgetSnapshot: ...
    def reserve_report_seal_and_freeze(self) -> BudgetReceipt: ...

class SealMeter:
    def charge_canonical_bytes(self, byte_count: int) -> None: ...
    def charge_projection_fields(self, field_count: int) -> None: ...
```

- [ ] **Step 1: Write the complete parameterized boundary tests**

Build one table from the fixed profile and prove every inclusive limit accepts its exact value and rejects its first greater value. For counters that aggregate across calls, split the exact value across several charges before the final `+1` call.

Add checked schema-product tests:

```python
def test_schema_reservation_rejects_without_changing_aggregate():
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
    before = ledger.snapshot().schema_evaluation_shape_units
    result = ledger.reserve_schema_shape(
        schema_nodes=4_001,
        instance_nodes=500,
        per_evaluation_limit=2_000_000,
    )
    assert result.accepted is False
    assert result.aggregate_before == before
    assert result.aggregate_after is None
    assert ledger.snapshot().schema_evaluation_shape_units == before
```

Cover per-evaluation rejection, invocation-aggregate rejection, checked-product overflow classification, repeated reservation charging, no refund, negative amount rejection, issue charging before duplicate rejection, fixed report reservation exactly once, and mutation after freeze.

Also prove every public control failure uses one registered kernel code, NFC-normalizes and caps `message` at 512 Unicode code points, excludes raw exception/input text, and preserves variable detail only through the closed hash field.

- [ ] **Step 2: Run and observe failure**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_budget.py -q
```

Expected: FAIL because `budget.py` does not exist.

- [ ] **Step 3: Implement the manifest, ledger, and non-circular seal budget**

Use checked nonnegative Python integer arithmetic before multiplication. `reserve_schema_shape` first compares `instance_nodes` to both floor divisions named in the spec, then computes/reserves the product only when both checks pass. Rejected reservations never change the ledger.

The ledger is mutable but invocation-private. Snapshots and the final receipt are owned immutable values. `reserve_report_seal_and_freeze()` atomically reserves exactly `262_144`, freezes all observed counters, and makes later charges fail with `BudgetLedgerFrozen`.

`SealMeter` starts after receipt freeze and cannot mutate the receipt. It enforces the fixed allowance and per-serialization 2 MiB canonical-byte limit.

- [ ] **Step 4: Run focused tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_budget.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```powershell
git add mcp_server/src/rook/validation_kernel/budget.py mcp_server/src/rook/validation_kernel/control.py mcp_server/src/rook/validation_kernel/__init__.py mcp_server/tests/test_validation_kernel_budget.py
git commit -m "feat: add validation kernel budget ledger"
```

---

### Task 3: Implement Bounded Byte Admission And The Iterative JSON Parser

**Files:**
- Create: `mcp_server/src/rook/validation_kernel/parser.py`
- Create: `mcp_server/tests/fixtures/validation_kernel/parser_corpus.jsonl`
- Create: `mcp_server/tests/test_validation_kernel_parser.py`
- Modify: `mcp_server/src/rook/validation_kernel/__init__.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class ParsedJsonValue:
    value: JsonValue
    value_fingerprint: str

@dataclass(frozen=True)
class JsonParseEvidence:
    artifact_role: str
    category: str
    subject_path: str | None
    bounded_message: str
    detail_sha256: str

def parse_owned_json(raw: bytes, *, artifact_role: str, ledger: BudgetLedger) -> ParsedJsonValue: ...
```

- [ ] **Step 1: Write hostile-ingress and exact-boundary tests**

Cover:

- exact built-in `bytes` only;
- strict UTF-8 and no BOM;
- duplicate object members;
- unpaired and incorrectly paired surrogates;
- exact container depth 64 and depth 65;
- object/array width exact and plus one;
- shared node, decoded-string, and parser-work exhaustion;
- exactly 1,024-character finite token (`"0." + "0" * 1022`) and a 1,025-character token;
- `1e10000`, `-1e10000`, and a 5,000-digit integer;
- literal `NaN`, `Infinity`, and `-Infinity`;
- escaped strings, surrogate pairs, and all JSON structural tokens;
- object source-order independence of canonical identity.

Keep the checked-in hand-curated corpus for named regressions, and add a deterministic grammar differential in the test module. Use `random.Random(0x4C4D3941)` to generate exactly 5,000 valid documents with maximum depth 8 and width 8 across every scalar, container, escape, Unicode, and finite-number production. Derive exactly 15,000 additional candidates through named mutation families: delimiter deletion, truncation, trailing comma, colon/comma substitution, duplicate-key insertion, invalid escape, malformed exponent/leading zero, extra root token, and invalid/truncated UTF-8. Assert every mutation family contributes cases and at least one oracle rejection.

The strict oracle is test-only and must:

```text
decode UTF-8 strictly and reject BOM
call json.loads with parse_constant rejection
use object_pairs_hook to reject duplicate names before dict construction
walk the result iteratively to reject non-finite values and unpaired surrogates
```

For every generated byte string, require the kernel and oracle to agree on accept/reject. For accepted values, convert the oracle's closed built-in tree through `own_trusted_json` and require byte-identical canonical JSON and equal node counts. The generated cases stay below kernel resource limits so this test measures grammar/semantic agreement; the separate boundary tests own budget rejection. Production parser source must not import or call the oracle, `json.loads`, or the grammar generator.

- [ ] **Step 2: Run and observe failure**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_parser.py -q
```

Expected: FAIL because `parser.py` does not exist.

- [ ] **Step 3: Implement a bounded tokenizer**

Tokenize the admitted byte buffer directly; do not decode the complete artifact into one host `str`. JSON structural syntax, whitespace, literals, and numbers are ASCII. For each string token, validate/decode UTF-8 and escapes incrementally, compute the decoded UTF-8 size, charge that size, and only then allocate the final `JsonString`. Tokenization uses explicit index/state, charges each started 64-byte block and token, and enforces number-token length while scanning. Number conversion uses bounded ASCII token strings and rejects non-finite binary64 results before constructing `JsonNumber`. The parser computes only canonical value identity; raw byte length/hash evidence is computed exactly once by paired invocation admission in Task 6.

String decoding must combine valid surrogate pairs and reject isolated halves. Object keys are retained long enough to detect duplicates before UTF-16 sorting.

- [ ] **Step 4: Implement iterative construction**

Use an explicit stack of object/array frames. Charge nodes, members/items, decoded UTF-8 bytes, depth, and attachment work before constructing or attaching each value. Do not recurse and do not create a mutable host tree to freeze afterward.

Local parse categories remain bounded internal evidence. Aggregate parsed-node/string/parser-work exhaustion raises the shared `validation_budget_exceeded` control result rather than a recipe-local schema issue.

- [ ] **Step 5: Add the production source guard**

```python
def test_production_parser_does_not_delegate_to_host_json_decoder():
    source = inspect.getsource(PARSER_MODULE)
    assert "json.loads" not in source
    assert "literal_eval" not in source
```

- [ ] **Step 6: Run focused tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_owned_json.py mcp_server/tests/test_validation_kernel_canonical_json.py mcp_server/tests/test_validation_kernel_budget.py mcp_server/tests/test_validation_kernel_parser.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```powershell
git add mcp_server/src/rook/validation_kernel/parser.py mcp_server/src/rook/validation_kernel/__init__.py mcp_server/tests/fixtures/validation_kernel/parser_corpus.jsonl mcp_server/tests/test_validation_kernel_parser.py
git commit -m "feat: add bounded owned JSON parser"
```

---

### Task 4: Add The Closed Draft 2020-12 Schema Adapter

**Files:**
- Modify: `mcp_server/pyproject.toml`
- Modify: `mcp_server/uv.lock`
- Create: `mcp_server/src/rook/validation_kernel/schema_profile.py`
- Create: `mcp_server/tests/test_validation_kernel_schema_profile.py`
- Modify: `mcp_server/src/rook/validation_kernel/__init__.py`

**Interfaces:**

```python
PAYLOAD_SCHEMA_PROFILE_ID = "rook.json_schema_profile:lm9a_payload_v1"
CORE_SCHEMA_PROFILE_ID = "rook.json_schema_profile:lm9a_core_v1"

@dataclass(frozen=True)
class SchemaProfile: ...

@dataclass(frozen=True)
class AdmittedSchema:
    schema_id: str
    schema_fingerprint: str
    profile_id: str
    schema_nodes: int
    local_reference_count: int
    maximum_reference_depth: int
    evaluation_expansion_units: int
    value: JsonObject

@dataclass(frozen=True)
class SchemaEvaluationReceipt:
    reservation: SchemaShapeReservation
    evaluator_invoked: bool
    evaluation_passed: bool | None
    bounded_errors: tuple[SchemaIssue, ...]
    failure_code: str | None

def admit_schema(schema_id: str, value: JsonObject, profile: SchemaProfile) -> AdmittedSchema: ...
def evaluate_schema(schema: AdmittedSchema, instance: JsonValue, *, instance_binding: InstanceBinding, ledger: BudgetLedger) -> SchemaEvaluationReceipt: ...
```

- [ ] **Step 1: Pin the existing runtime dependencies directly**

Add exactly:

```toml
"jsonschema==4.26.0",
"referencing==0.37.0",
"jsonschema-specifications==2025.9.1",
```

Run from `mcp_server`:

```powershell
uv lock
```

Assert the lock keeps those exact versions. This is a direct-dependency declaration, not a package upgrade.

- [ ] **Step 2: Write failing profile-admission tests**

Parameterize every allowed and forbidden keyword from the spec. Prove unknown keywords fail instead of being ignored. Prove payload `$ref` accepts only local RFC 6901 pointers, rejects URI-fragment/remote/dynamic references, rejects cycles, and enforces node/reference/depth limits. Prove core combinator count/nesting and core limits separately.

Add the embedded-schema numeric proof:

```python
def test_schema_fingerprint_accepts_finite_integer_outside_product_safe_range():
    schema = owned_schema({"type": "integer", "maximum": 9007199254740992})
    admitted = admit_schema("schema.large", schema, CORE_PROFILE)
    assert admitted.schema_fingerprint.startswith("sha256:")
```

- [ ] **Step 3: Write failing evaluator tests**

Cover exact owned-value type checking, no format callbacks, no retrieval callback, full schema-node count including unreachable `$defs` and annotations, admitted reference/combinator expansion, exact selected instance-root count, repeated evaluation charging, pre-evaluation reservation rejection, schema rejection, evaluator exception, and cache-independent shape units. Add a combined boundary where individually admitted fan-out and collection width exceed the per-evaluation limit only after `max(schema_nodes, evaluation_expansion_units) * instance_nodes`; assert rejection before evaluator construction.

Assert the installed versions and the Draft 2020-12 metaschema fingerprint are included in the profile identity.

- [ ] **Step 4: Run and observe failure**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_schema_profile.py -q
```

Expected: FAIL because the schema adapter does not exist.

- [ ] **Step 5: Implement static schema admission**

Walk owned schema values iteratively. Reject unknown/forbidden keywords before library construction. Build the local-reference graph from exact pointers, resolve without retrieval, check acyclicity/depth, and count complete schema nodes independently of evaluator caching.

Implement a custom `jsonschema` type checker for the six owned JSON value types. The adapter may expose read-only owned mappings/sequences to `jsonschema`; it must not create mutable `dict`/`list` copies of the instance. Configure the referencing registry with no retrieval function.

- [ ] **Step 6: Implement metered evaluation**

Under metric `rook.schema_evaluation_shape:max_schema_or_expansion_times_instance:v1`, derive `shape_basis_units = max(schema_nodes, evaluation_expansion_units)` and compute/reserve `shape_basis_units * instance_nodes` before invoking the library. Bind the metric ID, both source factors, derived basis, instance count, and product into the immutable reservation and conformance attempt row. Bind metric identity/formula into the profile and observed expansion into every sealed-program schema descriptor.

Each reservation also carries one private, nonserialized origin capability bound to the exact invocation ledger that issued it. Return a private kernel-issued immutable receipt for reservation rejection, completed evaluation, or evaluator failure; public construction of a receipt with matching fields is not authoritative. The receipt's private signed state binds the exact admitted-schema identity and exactly one evaluation subject: the immutable instance plus exact `InstanceBinding`, or the exact kernel-issued pre-evaluation candidate. Audit entry construction receives the expected invocation ledger and requires the kernel-issued receipt, its exact ledger-origin reservation, exact schema/instance factors, and matching private schema/subject bindings. A copied reservation, an equal-basis reservation with different factors, a same-factor reservation replayed from another ledger, a genuine same-ledger receipt replayed for another equal-shaped schema/sibling instance/candidate, or a caller-fabricated receipt fails before audit publication. The adapter records bounded deterministic paths/codes and hashes variable exception detail; it never forwards unbounded `str(exc)`.

Make nested authority validation transitive on every use: audit-entry authentication reauthenticates its receipt, and receipt authentication reauthenticates the reservation issuer/origin/signature. Add post-issuance tamper regressions for receipt issuer/signature and reservation issuer/origin; each must invalidate the receipt and enclosing audit entry and stop conformance projection.

Add regressions at the schema helper and conformance projection boundaries for cross-ledger same-factor replay, same-ledger equal-factor schema/instance replay, pre-evaluation candidate replay, and fabricated success receipts. Assert that private ledger/receipt schema/subject capabilities do not appear in public evidence projections, attempt rows, reports, fingerprints, or conformance artifacts.

- [ ] **Step 7: Run focused tests and dependency checks**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_schema_profile.py -q
.\mcp_server\.venv\Scripts\python.exe -c "import importlib.metadata as m; assert m.version('jsonschema') == '4.26.0'; assert m.version('referencing') == '0.37.0'; assert m.version('jsonschema-specifications') == '2025.9.1'"
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

```powershell
git add mcp_server/pyproject.toml mcp_server/uv.lock mcp_server/src/rook/validation_kernel/schema_profile.py mcp_server/src/rook/validation_kernel/__init__.py mcp_server/tests/test_validation_kernel_schema_profile.py
git commit -m "feat: add closed validation schema profile"
```

---

### Task 5: Seal One Immutable Validation Program

**Files:**
- Create: `mcp_server/src/rook/validation_kernel/phase_contract.py`
- Create: `mcp_server/src/rook/validation_kernel/kernel_schemas.py`
- Create: `mcp_server/src/rook/validation_kernel/program.py`
- Create: `mcp_server/tests/_validation_kernel_fakes.py`
- Create: `mcp_server/tests/test_validation_kernel_program.py`
- Modify: `mcp_server/src/rook/validation_kernel/__init__.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class InputBinding:
    input_name: str
    source_kind: Literal["invocation_input", "program_constant", "phase_output"]
    source_input: str | None
    source_constant: str | None
    source_phase: str | None
    source_output: str | None
    expected_type: str
    cardinality: Literal["exactly_one", "zero_or_one", "many"]

@dataclass(frozen=True)
class ProvidedOutput: ...

@dataclass(frozen=True)
class PhaseSpec:
    phase_name: str
    ordering_after: tuple[str, ...]
    input_bindings: tuple[InputBinding, ...]
    provided_outputs: tuple[ProvidedOutput, ...]
    runner_id: str
    permitted_diagnostic_codes: tuple[str, ...]
    permitted_blocker_codes: tuple[str, ...]

@dataclass(frozen=True)
class ValidationProgramContribution: ...

@dataclass(frozen=True)
class SealedValidationProgram:
    program_id: str
    program_fingerprint: str
    manifest_bytes: bytes
    phases: tuple[PhaseSpec, ...]
    # private immutable runtime bindings

def compose_and_seal_program(contribution: ValidationProgramContribution) -> SealedValidationProgram: ...
```

- [ ] **Step 1: Write static phase-contract tests**

Cover duplicate phase/input/output names, missing producers, unknown outputs, cycles, type/cardinality mismatch, unknown runner/export/issue IDs, invalid required/permitted status relationships, unknown `required_for_compile_phases`, ambiguous binding fields, and a valid synthetic DAG with one ordering-only edge.

Also validate the fixed program-manifest and assembler-profile schemas as recursively closed documents. Unknown nested fields, duplicate identities, and claimed component fingerprints that disagree with fixed-seal recomputation must fail composition.

Validate the report declaration's kernel-owned field paths, exact budget-receipt path, report-fingerprint exclusion, and fixed outer-envelope field count. Reject overlap between a projection-writable body path and any kernel-owned path before program seal.

- [ ] **Step 2: Write seal identity and runtime-binding tests**

Prove:

- the candidate runtime canonicalizer cannot choose the program fingerprint;
- changing any budget, parser, profile, schema, phase, binding, ordering edge, runner, issue, export, source, runtime dependency, or projection moves the fingerprint;
- missing/extra/duplicate/mismatched runtime bindings fail seal;
- closures, mutable callable instances, and bound methods fail seal;
- module-level functions and immutable callable records pass;
- replacing a candidate registry after seal cannot change invocation bindings;
- final manifest bytes resolve to `program_fingerprint` and cannot be reconstructed from ambient modules.

- [ ] **Step 3: Run and observe failure**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_program.py -q
```

Expected: FAIL because phase/program composition does not exist.

- [ ] **Step 4: Implement closed phase declarations**

All IDs use the spec's ASCII machine grammar. Normalize set-like fields with RFC 8785 UTF-16 order. Derive data dependencies only from `input_bindings`; union `ordering_after` only for scheduling. Store the validated topological graph in immutable tuples/maps inside the sealed program.

- [ ] **Step 5: Implement source and runtime identity**

Normalize behavior-bearing Python source as UTF-8 with LF line endings before hashing. Parse imports with `ast`, reject undeclared in-package behavior modules, and reject dynamic `__import__`/`importlib.import_module` calls in sealed behavior modules. Fingerprint each exact third-party distribution by a stable, path-relative projection of installed distribution records and direct hashes for behavior-bearing files; exclude generated cache files and machine-specific absolute paths. Bind Python implementation/version/cache tag separately.

The fixed bootstrap seal owns the manifest schema, reference JCS callable, SHA-256, kernel build fingerprint, and program-seal implementation fingerprint. Candidate runtime bindings are manifest data only.

- [ ] **Step 6: Implement one-shot composition**

Keep `_ValidationProgramBuilder` private to `compose_and_seal_program`. Validate schemas, profiles, dataflow, runtime bindings, transitive implementation sources, dependency identities, report projection, and fixed seal sufficiency before canonicalizing. Consume builder state and return only `SealedValidationProgram`; failed composition returns no partial program.

- [ ] **Step 7: Run focused tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_program.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 5**

```powershell
git add mcp_server/src/rook/validation_kernel/phase_contract.py mcp_server/src/rook/validation_kernel/kernel_schemas.py mcp_server/src/rook/validation_kernel/program.py mcp_server/src/rook/validation_kernel/__init__.py mcp_server/tests/_validation_kernel_fakes.py mcp_server/tests/test_validation_kernel_program.py
git commit -m "feat: seal validation program identity"
```

---

### Task 6: Establish Trusted Bundle Issuance And Report Constructability

**Files:**
- Create: `mcp_server/src/rook/validation_kernel/invocation.py`
- Create: `mcp_server/tests/test_validation_kernel_invocation.py`
- Modify: `mcp_server/tests/_validation_kernel_fakes.py`
- Modify: `mcp_server/src/rook/validation_kernel/__init__.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class SealedTrustedBundleAssemblerProfile: ...

class TrustedValidationBundleInput:
    @property
    def raw_bytes(self) -> bytes: ...

@dataclass(frozen=True)
class ValidationInvocation:
    program: SealedValidationProgram
    assembler_profile: SealedTrustedBundleAssemblerProfile
    raw_recipe_bytes: bytes
    raw_validation_bundle_bytes: bytes
    recipe_input_payload_sha256: str
    validation_bundle_input_payload_sha256: str
    validation_bundle: JsonObject
    recipe_value: JsonValue | None
    recipe_parse_evidence: JsonParseEvidence | None
    invocation_inputs: JsonObject

class _ValidationExecutionContext:
    # Private kernel carrier: immutable invocation plus engine-owned mutable ledger.
    invocation: ValidationInvocation
    ledger: BudgetLedger

def seal_trusted_bundle_assembler_profile(candidate: JsonObject) -> SealedTrustedBundleAssemblerProfile: ...
def issue_trusted_validation_bundle(profile: SealedTrustedBundleAssemblerProfile, raw_bytes: bytes) -> TrustedValidationBundleInput: ...
def _build_validation_execution_context(program: SealedValidationProgram, raw_recipe_bytes: bytes, trusted_bundle: TrustedValidationBundleInput) -> _ValidationExecutionContext | ValidationControlFailure: ...
```

- [ ] **Step 1: Write capability and principal tests**

Prove that plain profile JSON, copied serialized fields, an unsealed candidate, a carrier lookalike, wrong program ID, and wrong clock source cannot issue or validate a bundle. Prove both `trusted_host_ingress` and `deterministic_fixture` profiles enforce their exact permitted clock kind.

- [ ] **Step 2: Write admission-order tests**

Use spy byte subclasses/lookalikes to prove exact built-in `bytes` checking occurs before length/copy/hash. Prove over-cap input records observed lengths and null hashes without scanning either artifact. Prove exact-cap inputs are copied and hashed once.

- [ ] **Step 3: Write constructability tests**

The synthetic report projection declares mandatory descriptor shells by exact JSON Pointer and container kind. Cover:

- constructable bundle plus valid recipe;
- constructable bundle plus malformed admitted recipe;
- missing/wrong-container mandatory shell;
- malformed content inside a present shell;
- malformed bundle;
- malformed recipe plus malformed companion content;
- aggregate parse-budget exhaustion while parsing either artifact;
- mutation/replacement of source variables after carrier issuance cannot affect captured exact bytes.

The expected boundary is:

```text
bundle cannot establish constructability -> control failure, no report-capable invocation
bundle establishes shells, inner content malformed -> invocation exists; phases may receipt companion errors
recipe malformed under local bounds -> invocation exists with recipe parse evidence
shared aggregate parse budget exhausted -> control failure, no invocation
```

- [ ] **Step 4: Run and observe failure**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_invocation.py -q
```

Expected: FAIL because trusted invocation support does not exist.

- [ ] **Step 5: Implement fixed profile sealing and opaque issuance**

The profile seal uses a private module-owned issuer token and returns an object that cannot be constructed through public fields. `TrustedValidationBundleInput` stores the exact built-in immutable `bytes` object without scanning or copying it and carries one identity-bound issuer capability. Paired admission validates both lengths first, then makes the invocation-owned copies and hashes both admitted artifacts. Validation checks object identity and profile fingerprint; it never consults a registry.

- [ ] **Step 6: Implement byte admission and bundle-first preflight**

Follow the nine-step admission order in the spec exactly. Construct an immutable `ValidationInvocation` only after the bundle is owned, fingerprinted, and satisfies the sealed projection's mandatory shell list and trusted context projection. Keep the one mutable `BudgetLedger` solely in `_ValidationExecutionContext`; phases never receive that carrier or ledger directly. Keep malformed inner companion content for later phase evidence.

- [ ] **Step 7: Run focused tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_invocation.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 6**

```powershell
git add mcp_server/src/rook/validation_kernel/invocation.py mcp_server/src/rook/validation_kernel/__init__.py mcp_server/tests/_validation_kernel_fakes.py mcp_server/tests/test_validation_kernel_invocation.py
git commit -m "feat: add trusted validation invocation boundary"
```

---

### Task 7: Execute Exact Phase Dataflow With Immutable Results

**Files:**
- Create: `mcp_server/src/rook/validation_kernel/phase_engine.py`
- Create: `mcp_server/tests/test_validation_kernel_phase_engine.py`
- Modify: `mcp_server/tests/_validation_kernel_fakes.py`
- Modify: `mcp_server/src/rook/validation_kernel/__init__.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class KernelIssue:
    classification: Literal["diagnostic", "compile_blocker"]
    code: str
    severity: Literal["error", "warning", "information"] | None
    subject_id: str | None
    path: str | None
    related_paths: tuple[str, ...]
    bounded_message: str
    detail_sha256: str | None

@dataclass(frozen=True)
class RunnerResult:
    diagnostics: tuple[KernelIssue, ...]
    compile_blockers: tuple[KernelIssue, ...]
    outputs: tuple[NamedOutput, ...]

@dataclass(frozen=True)
class PhaseResult:
    phase_name: str
    status: Literal["passed", "blocked", "failed", "not_evaluated"]
    diagnostics: tuple[KernelIssue, ...]
    compile_blockers: tuple[KernelIssue, ...]
    outputs: tuple[NamedOutput, ...]
    kernel_work_units_delta: int

def execute_phase_program(context: _ValidationExecutionContext) -> tuple[PhaseResult, ...] | ValidationControlFailure: ...
```

- [ ] **Step 1: Write scheduler and binding tests**

Prove data dependencies derive from exact input bindings, ordering-only edges affect sequence but not availability, and simultaneously ready phases use UTF-16 `phase_name` order. Prove a failed/not-evaluated producer suppresses consumers, while a blocked producer can provide required outputs.

- [ ] **Step 2: Write integrity tests**

Inject runners that return:

- an unregistered or wrongly classified issue;
- warning/information severities through the public path;
- duplicate, extra, missing, wrong-type, mutable, and wrong-cardinality outputs;
- a promised output missing on passed and blocked status;
- an output present on an unpermitted status;
- an authored status/work count field;
- an exception with oversized text.

Every structural contradiction returns `validator_integrity_failure` before result insertion. Variable exception text is bounded and hashed.

- [ ] **Step 3: Write immutability and work-accounting tests**

Attempt cross-phase mutation through invocation inputs, companion-like indexes, semantic-like indexes, output tuples, and nested mappings. Assert no retained mutable path exists. Prove the engine snapshots the ledger around runner calls and computes the delta; runners have no work-count field.

- [ ] **Step 4: Run and observe failure**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_phase_engine.py -q
```

Expected: FAIL because the engine does not exist.

- [ ] **Step 5: Implement deterministic scheduling and binding**

Resolve each input only from the captured invocation, sealed constant, or exact prior output named by the binding. Validate expected type/cardinality before runner entry. Never pass the ledger itself; pass a restricted helper facade whose methods charge the engine-owned ledger. Schema evaluation is available only through that facade, which appends the adapter's exact immutable receipt to an engine-owned ordered audit ledger before returning the semantic pass/fail view to the runner.

- [ ] **Step 6: Implement result derivation and integrity**

Charge each issue before checking registration. Validate every output through the sealed export binding. Derive status with error precedence over blockers, then enforce `permitted_on_statuses` and `required_on_statuses`. Accept only transitively immutable outputs.

An ordinary missing optional input makes the consumer `not_evaluated`. A required promised output omitted by a passed/blocked provider is kernel corruption and aborts report publication.

- [ ] **Step 7: Run focused tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_phase_engine.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 7**

```powershell
git add mcp_server/src/rook/validation_kernel/phase_engine.py mcp_server/src/rook/validation_kernel/__init__.py mcp_server/tests/_validation_kernel_fakes.py mcp_server/tests/test_validation_kernel_phase_engine.py
git commit -m "feat: add typed validation phase engine"
```

---

### Task 8: Seal Deterministic Reports Without Circular Accounting

**Files:**
- Create: `mcp_server/src/rook/validation_kernel/reporting.py`
- Create: `mcp_server/tests/test_validation_kernel_reporting.py`
- Modify: `mcp_server/tests/_validation_kernel_fakes.py`
- Modify: `mcp_server/src/rook/validation_kernel/__init__.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class ReportProjectionEnvelope:
    program_id: str
    program_fingerprint: str
    invocation_evidence: JsonObject
    phase_specs: tuple[PhaseSpec, ...]
    phase_results: tuple[PhaseResult, ...]

@dataclass(frozen=True)
class PublishedValidationReport:
    schema_id: str
    report_fingerprint: str
    canonical_bytes: bytes
    value: JsonObject

class ReportBuilder:
    def put(self, path: str, value: JsonValue) -> None: ...
    def append(self, path: str, value: JsonValue) -> None: ...

def seal_validation_report(context: _ValidationExecutionContext, phase_results: tuple[PhaseResult, ...]) -> PublishedValidationReport | ValidationControlFailure: ...
```

- [ ] **Step 1: Write projection-authority tests**

Prove the projection receives only the exact immutable envelope plus a kernel-owned `ReportBuilder` and cannot access runners, raw mutable registries, clocks, files, providers, or a live ledger. Prove every builder insertion charges projection fields before attachment. Prove unknown projection fields, wrong output schema, direct return of an arbitrary host graph, and an unsealed projection binding fail before publication.

- [ ] **Step 2: Write non-circular seal tests**

Assert exact order:

```text
project once through metered body builder
-> charge fixed envelope/receipt field shape
-> reserve 262144 and freeze receipt
-> attach receipt/envelope without changing shape
-> canonicalize/hash
-> attach fingerprint
-> canonicalize final artifact
```

Prove the projection cannot author the budget receipt, report fingerprint, or another kernel-owned field. Prove the frozen receipt records all body/envelope field charges and the fixed reservation, but not actual serializer work. Repeated sealing of identical inputs produces identical bytes and fingerprint. Projection/canonical limit overflow returns a typed control failure and no partial bytes.

- [ ] **Step 3: Write compile-readiness projection tests**

Use the synthetic projection to derive:

```text
valid = no error diagnostics
compile_ready = valid and no blockers and every required_for_compile phase passed
```

Prove an optional not-evaluated phase does not affect readiness, while a required not-evaluated phase does. The kernel tests the mechanism only; no Planner-specific issue or phase names are introduced.

- [ ] **Step 4: Run and observe failure**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_reporting.py -q
```

Expected: FAIL because report sealing does not exist.

- [ ] **Step 5: Implement one-shot projection and seal**

Build the projection envelope from captured immutable values. Call only the report projection binding captured in the sealed program and require it to populate a kernel-owned `ReportBuilder`; the builder charges every body field before attachment and produces an owned immutable body. Charge the sealed schema's fixed outer-envelope and budget-receipt field shape, including the eventual fingerprint field, reserve/freeze the budget exactly once, attach the frozen receipt without replacing body content, stream both canonical serializations through a separate `SealMeter`, and publish only final canonical bytes plus an owned value.

- [ ] **Step 6: Run focused tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_reporting.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 8**

```powershell
git add mcp_server/src/rook/validation_kernel/reporting.py mcp_server/src/rook/validation_kernel/__init__.py mcp_server/tests/_validation_kernel_fakes.py mcp_server/tests/test_validation_kernel_reporting.py
git commit -m "feat: add deterministic validation report seal"
```

---

### Task 9: Compose The Public Validation Entry Point

**Files:**
- Create: `mcp_server/src/rook/validation_kernel/api.py`
- Create: `mcp_server/tests/test_validation_kernel_api.py`
- Modify: `mcp_server/tests/_validation_kernel_fakes.py`
- Modify: `mcp_server/src/rook/validation_kernel/__init__.py`

**Interfaces:**

```python
ValidationResult = Union[
    PublishedValidationReport,
    ValidationControlFailure,
]

class _ValidationExecutionAudit:
    # Kernel-issued, immutable, non-serializable; binds program fingerprint and
    # ordered schema receipts.
    pass

@dataclass(frozen=True)
class _AuditedValidationOutcome:
    public_result: ValidationResult
    audit: _ValidationExecutionAudit

def validate_artifacts(
    program: SealedValidationProgram,
    raw_recipe_bytes: bytes,
    trusted_validation_bundle: TrustedValidationBundleInput,
) -> ValidationResult: ...

def _validate_artifacts_with_audit(
    program: SealedValidationProgram,
    raw_recipe_bytes: bytes,
    trusted_validation_bundle: TrustedValidationBundleInput,
) -> _AuditedValidationOutcome: ...
```

- [ ] **Step 1: Write vertical terminal-path tests**

Walk each path from arguments to earliest honest result:

| Boundary | Expected result |
|---|---|
| unsealed/invalid program | control failure, no input scan |
| invalid bundle carrier | control failure, no input scan |
| either byte cap exceeded | preflight budget failure, no hashes/report |
| malformed bundle | control failure, no semantic report |
| constructability shell absent | control failure, no semantic report |
| constructable bundle plus malformed recipe | schema-like phase evidence in a report |
| constructable bundle plus malformed companion inner content | companion-like phase evidence in a report |
| both recipe and companion inner content malformed | both independent phase outcomes where dataflow permits |
| phase integrity failure | control failure, no report |
| report seal failure | control failure, no report |
| valid synthetic inputs | deterministic published report |

- [ ] **Step 2: Write replay and API-surface tests**

Run identical bytes/program/carrier twice and compare final canonical bytes. Reorder object members in either raw artifact and prove raw hashes move while canonical value fingerprints and semantic phase output remain stable.

Use `inspect.signature(validate_artifacts)` to prove there is no raw validation-bundle byte parameter. Inspect `rook.validation_kernel.__all__` to prove builders, issuer tokens, ledgers, and meters are not public.

Prove the package-private audited path returns the same object identity as the public result plus one kernel-issued immutable audit whose schema receipts exactly match adapter invocation order. Plain tuples, copied fields, report JSON, and caller-created lookalikes cannot pass the audit capability check.

- [ ] **Step 3: Run and observe failure**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_api.py -q
```

Expected: FAIL because the orchestration entrypoint does not exist.

- [ ] **Step 4: Implement orchestration without fallback paths**

Capture program/carrier identity once, build the invocation, execute phases, and seal the report. The internal path also seals the ordered adapter receipts into `_ValidationExecutionAudit`; the public wrapper returns only `public_result`. Do not retry parsing, thaw/reparse inputs, poll ambient state, or turn a pre-report failure into a semantic report.

- [ ] **Step 5: Run the kernel path tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_owned_json.py mcp_server/tests/test_validation_kernel_canonical_json.py mcp_server/tests/test_validation_kernel_budget.py mcp_server/tests/test_validation_kernel_parser.py mcp_server/tests/test_validation_kernel_schema_profile.py mcp_server/tests/test_validation_kernel_program.py mcp_server/tests/test_validation_kernel_invocation.py mcp_server/tests/test_validation_kernel_phase_engine.py mcp_server/tests/test_validation_kernel_reporting.py mcp_server/tests/test_validation_kernel_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 9**

```powershell
git add mcp_server/src/rook/validation_kernel/api.py mcp_server/src/rook/validation_kernel/__init__.py mcp_server/tests/_validation_kernel_fakes.py mcp_server/tests/test_validation_kernel_api.py
git commit -m "feat: compose validation kernel entrypoint"
```

---

### Task 10: Implement The Independent Release Conformance Gate

**Files:**
- Create: `mcp_server/src/rook/validation_kernel/conformance.py`
- Modify: `mcp_server/src/rook/validation_kernel/kernel_schemas.py`
- Create: `mcp_server/tests/test_validation_kernel_conformance.py`
- Modify: `mcp_server/tests/_validation_kernel_fakes.py`
- Modify: `mcp_server/src/rook/validation_kernel/__init__.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class SealedConformanceGateProfile: ...

@dataclass(frozen=True)
class ConformanceGateInvocationFailure:
    stage: str
    code: str
    gate_profile_fingerprint: str | None
    program_fingerprint: str | None
    campaign_input_size: int
    campaign_input_sha256: str | None
    bounded_detail_sha256: str
    report_emitted: Literal[False]
    trusted_gate_result_issued: Literal[False]

class TrustedConformanceGateResult:
    @property
    def report_bytes(self) -> bytes: ...

class TrustedImmutableArtifactStore(Protocol):
    def resolve_exact_bytes(self, content_ref: str) -> bytes | None: ...

class TrustedConformanceFixtureContext:
    # Opaque release-issued capability over one store and sealed assembler profiles.
    pass

def seal_conformance_gate_profile(candidate: JsonObject, gate_callable: Callable[..., object]) -> SealedConformanceGateProfile: ...
def _issue_trusted_conformance_fixture_context(
    artifact_store: TrustedImmutableArtifactStore,
    assembler_profiles: tuple[SealedTrustedBundleAssemblerProfile, ...],
) -> TrustedConformanceFixtureContext: ...
def run_conformance_gate(
    gate_profile: SealedConformanceGateProfile,
    program: SealedValidationProgram,
    raw_campaign_bytes: bytes,
    fixture_context: TrustedConformanceFixtureContext,
) -> TrustedConformanceGateResult | ConformanceGateInvocationFailure: ...
```

`TrustedImmutableArtifactStore` and the exact sealed assembler-profile objects are supplied by trusted release composition, not by campaign JSON. The release host issues one immutable `TrustedConformanceFixtureContext` before campaign inspection. The gate captures that exact capability once, accepts only exact built-in `bytes` resolutions, verifies every bound fingerprint before use, and never interprets an unresolved reference as empty content. Serialized store/profile lookalikes cannot issue fixture bundles.

- [ ] **Step 1: Write independent gate-authority tests**

Prove the release call captures a sealed profile before campaign inspection. A campaign can require the selected profile fingerprint but cannot nominate a callable or cause profile replacement. Plain serialized profile/report JSON cannot forge either runtime capability.

- [ ] **Step 2: Write the earliest-honest-result matrix tests**

Cover every matrix row from the spec:

- invalid gate profile/program -> invocation failure, no report/capability;
- unavailable, over-cap, malformed, schema-invalid, duplicate-keyed, or fingerprint-inconsistent campaign -> invocation failure;
- constructable campaign with program/profile/core-coverage mismatch -> failed aggregate report, zero case rows;
- missing/fingerprint-mismatched case content -> failed row, zero schema attempts;
- reservation rejection -> one `reservation_rejected` attempt;
- successful reservation -> `evaluation_completed` or `evaluator_failed` attempt;
- caught gate-integrity or gate-budget failure after campaign identity -> `gate_execution_failed` or `gate_budget_exceeded`, no report/capability;
- either aggregate canonical serialization exceeding its profile-bound limit -> `gate_report_seal_failed`, no partial report/capability.

The campaign admission cap is the independently sealed gate profile's exact `campaign_input_byte_limit=4_194_304`. Each artifact-store resolution separately uses `referenced_case_content_byte_limit=4_194_304`. Neither is caller-selectable. Test 4,194,304 bytes admitted and 4,194,305 rejected before copying or hashing, with a null campaign/content hash on the applicable rejection. A raw fixture recipe still fails its stricter 1,048,576-byte validation cap even though it fit the gate-level case-content cap.

- [ ] **Step 3: Write exact schema-attempt accounting tests**

Assert all nullable and derived fields for the three statuses. In particular:

```python
assert rejected.aggregate_after_reservation is None
assert rejected.attempted_shape_units is None
assert rejected.evaluator_invoked is False
assert ledger_total_after == rejected.aggregate_before_reservation

assert completed.aggregate_after_reservation == (
    completed.aggregate_before_reservation + completed.attempted_shape_units
)
```

Prove repeated evaluations reserve full conservative products, all attempt rows expose and recompute the metric factors, and no attempt is invented before the evaluator boundary. Conformance starts each independent case/invocation chain at zero, proves accepted rows are within both limits, and replays the exact overflow -> per-evaluation -> invocation rejection precedence. Add adversarial rows for forged factors, accepted over-limit products, unjustified rejection codes, and nonzero initial aggregates.

- [ ] **Step 4: Write campaign completeness tests**

Use an indexed execution ledger that permits duplicate/extra rows in failed evidence. Derive completeness by stable `case_id`, not row index. Prove `complete=true` only for exactly one matching row per required case with no missing, extra, duplicate, kind-mismatched, or fingerprint-mismatched IDs.

Prove a passing report requires campaign integrity, complete exact-once rows, all passing outcomes, all per-evaluation limits, and the invocation aggregate limit. A list of individually passing rows without a passing aggregate report is not deployable evidence.

Force aggregate report projection, first serialization, and final serialization failures independently. Assert the gate preserves captured program/profile/campaign hashes in the typed invocation failure but exposes no partial report bytes or trusted result capability.

Validate campaign, case-variant, gate-profile, attempt-row, completeness, and aggregate-report schemas as recursively closed. A core row always has `schema_case_result` and a null fixture result; its boolean is null until a completed evaluation and must match `evaluation_passed`. A fixture row uses the inverse variant. Failed reports may contain duplicate indexed case rows by design; schema closure must not accidentally enforce passing completeness.

- [ ] **Step 5: Write content-addressed campaign/report tests**

The synthetic campaign includes core-schema-positive and domain-neutral fixture cases. Resolve every full payload through the release-issued fixture context and verify its fingerprint before execution. Assert campaign case-set, campaign, report, program, gate-profile, schema, fixture, and assembler-profile fingerprints all bind exactly.

Use the closed `rook.validation_conformance_fixture:v1` manifest. For `published_report`, compare exact report schema and fingerprint and require all control fields null. For `control_failure`, compare exact stage/code/artifact role and require report fields null. Record the gate-derived expected/actual identity in `fixture_case_result`; a field mismatch must fail the row even if a selected high-level status happens to agree. Kernel tests use only generic `fixture.report_pass` and `fixture.control_failure_expected` identities; worker-slot and confirmation campaign cases belong exclusively to the later LM9A-Semantics contribution.

For semantic fixtures, consume schema-attempt rows only from `_ValidationExecutionAudit` returned by the exact kernel invocation. A missing, lookalike, reordered, or program-mismatched audit must produce `gate_execution_failed`; report JSON and fixture fields are never counter authority.

- [ ] **Step 6: Run and observe failure**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_conformance.py -q
```

Expected: FAIL because the conformance gate does not exist.

- [ ] **Step 7: Implement gate/profile sealing and campaign admission**

Seal the profile and exact gate callable under fixed release authority. Issue and capture the fixture context before reading campaign bytes. Parse campaign JSON with one fresh gate-admission ledger and each fixture manifest/core instance with a separate fresh gate-admission ledger, all under the exact parser limits bound by the gate profile. Do not gate-parse raw fixture recipe/bundle bytes; pass them to `validate_artifacts` after bounded content resolution. Return only `ConformanceGateInvocationFailure` until a schema-valid, fingerprint-consistent campaign identity exists.

- [ ] **Step 8: Implement integrity, execution, and aggregate report sealing**

Derive `campaign_integrity` before scheduling cases. Execute sorted required cases sequentially with no replacement. Preserve all actual indexed result/attempt rows, compute completeness independently, and seal the aggregate report under the already selected gate profile. Issue `TrustedConformanceGateResult` only for constructable reports, including failed reports.

- [ ] **Step 9: Run focused tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_validation_kernel_conformance.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit Task 10**

```powershell
git add mcp_server/src/rook/validation_kernel/conformance.py mcp_server/src/rook/validation_kernel/kernel_schemas.py mcp_server/src/rook/validation_kernel/__init__.py mcp_server/tests/_validation_kernel_fakes.py mcp_server/tests/test_validation_kernel_conformance.py
git commit -m "feat: add validation conformance release gate"
```

---

### Task 11: Prove Kernel Boundaries And Finish The Implementation Branch

**Files:**
- Create: `mcp_server/tests/test_validation_kernel_boundaries.py`
- Create: `mcp_server/tests/_validation_kernel_replay_driver.py`
- Modify as needed for defects only: `mcp_server/src/rook/validation_kernel/*.py`
- Modify as needed for defects only: `mcp_server/tests/test_validation_kernel_*.py`

- [ ] **Step 1: Add architecture boundary guards**

Scan production kernel source and assert it does not import or mention:

```text
rook.agent
server.py
bridge.py
PlannerWorkerContractRequest
RookWorkflowContract
TaskSpec
gh_edit
Rhino
Grasshopper
Ollama
worker model
radial
box array
grid spacing
```

Also assert parser source contains no host JSON decoder and canonicalization source contains no legacy fingerprint helper import.

- [ ] **Step 2: Add public-surface and capability guards**

Assert `rook.validation_kernel.__all__` contains only reviewed public types/functions. Prove private issuer tokens, mutable ledgers, builders, parser frames, raw runtime binding maps, and `SealMeter` cannot be constructed or retrieved through that surface.

- [ ] **Step 3: Add the complete deterministic integration campaign**

Build one synthetic sealed program with:

- at least two phases with exact output dataflow;
- one ordering-only edge;
- one required and one optional compile-readiness phase;
- one core and one payload schema;
- one diagnostic and one blocker code;
- one immutable export type;
- one report projection;
- one trusted fixture assembler profile;
- one independently sealed conformance gate profile.

Run the exact same raw inputs twice and prove byte-identical program manifest, validation report, campaign report, and every fingerprint. Then change each behavior-bearing category individually and prove the expected identity moves.

Prove invocation isolation separately from ordinary replay with two tests over the same distinct case matrix. Mix successful, blocked, report-producing failure, local parse failure, and invocation-budget failure inputs. For each test, first produce a serial oracle, then reuse one `SealedValidationProgram` across eight simultaneous validations launched with `ThreadPoolExecutor(max_workers=8)`. Have the eight test workers wait on one harness-owned `threading.Barrier(8)` immediately before entering the selected validation call, and repeat the synchronized campaign for ten rounds.

The public concurrency test calls only `validate_artifacts(...)`. Compare each returned `ValidationResult` with its public serial oracle for terminal variant, public raw-input hashes, public budget receipt and counters, phase rows, and the exact presence or absence of report evidence. When a report exists, its bytes and fingerprint must match exactly. Inspect the public result and package exports to prove that `_ValidationExecutionAudit`, schema-attempt rows, or any equivalent audit capability is not exposed.

The private audit concurrency test calls `_validate_artifacts_with_audit(...)` directly from the package-private module. Compare `public_result` independently against the same public serial oracle, then compare the kernel-issued `_ValidationExecutionAudit` against a private serial audit oracle for ordered schema-attempt rows, adapter invocation order, and audit identity fields. Assert that case-specific public subjects, paths, failure codes, counters, report fingerprints, private schema receipts, and audit identity fields never appear in another case's outcome. The private test must not add audit fields to `ValidationResult`, package exports, report JSON, or another public type.

For both tests, the barrier and executor belong only to the test harness; no synchronization object or test-only mutable state may enter a runner, runtime binding, or sealed program.

- [ ] **Step 4: Prove cross-process determinism under hash randomization**

Implement `_validation_kernel_replay_driver.py` as a narrow executable test helper. It constructs the exact synthetic sealed program and trusted inputs from `_validation_kernel_fakes.py`, runs the fixed validation and conformance campaign, and writes one canonical UTF-8 JSON line to standard output. The line contains base64 encodings of the exact canonical bytes and their fingerprints for:

```text
sealed program manifest
validation report
conformance campaign manifest
conformance campaign report
```

It also records the exact terminal variant and budget/audit fingerprints needed to catch process-initialized state. The driver must write no nondeterministic timestamp, path, process ID, object representation, or unordered diagnostic data; standard error remains empty on success.

From `test_validation_kernel_boundaries.py`, invoke the driver through `sys.executable` in fresh processes with `PYTHONHASHSEED` values `0`, `1`, `42`, and `4294967295`. Give each process the same explicit working directory and minimal deterministic environment required for imports, and prohibit network or ambient-clock inputs. Compare standard-output bytes directly, rather than parsing and reserializing the line. Require zero exit status, empty standard error, and byte-identical output across all seeds. Repeat seed `42` in a second fresh process and require the same bytes, catching process-initialized drift even when hash seeding is fixed.

- [ ] **Step 5: Add fixed-profile feasibility proofs**

Under the exact sealed synthetic program, prove:

- every registered core schema has a positive instance within its per-evaluation limit;
- every mandatory synthetic campaign case fits the 16,000,000-unit invocation cap;
- observed shape metric identity, schema/expansion basis, and resulting units are bound to the exact program fingerprint;
- adding an over-budget schema/fixture makes the aggregate release decision fail;
- fixed report-seal allowance covers the maximum schema-permitted projection and two maximum-size canonical traversals.

- [ ] **Step 6: Run the full kernel gate**

```powershell
$kernelTests = Get-ChildItem -LiteralPath mcp_server/tests -Filter "test_validation_kernel_*.py" | Sort-Object FullName | Select-Object -ExpandProperty FullName
.\mcp_server\.venv\Scripts\python.exe -m pytest @kernelTests -q
node mcp_server/tests/fixtures/validation_kernel/generate_jcs_number_vectors.mjs --check
```

Expected: PASS.

- [ ] **Step 7: Run adjacent regression tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py mcp_server/tests/test_plan_graph_workflow_contract.py mcp_server/tests/test_workflow_validate.py mcp_server/tests/test_planner_worker_contract_request.py -q
```

Expected: PASS. The legacy fingerprint path remains behaviorally unchanged and separate.

- [ ] **Step 8: Compile and inspect the final diff**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m compileall -q mcp_server/src/rook/validation_kernel
git diff --check origin/main...HEAD
git diff --name-only origin/main...HEAD
```

Expected tracked implementation scope:

```text
mcp_server/pyproject.toml
mcp_server/uv.lock
mcp_server/src/rook/validation_kernel/
mcp_server/tests/_validation_kernel_fakes.py
mcp_server/tests/_validation_kernel_replay_driver.py
mcp_server/tests/fixtures/validation_kernel/
mcp_server/tests/test_validation_kernel_*.py
```

The existing LM9A specs/plan may also appear because this branch currently carries the reviewed design history. No knowledge-store, probe-run, live artifact, server, Planner, or unrelated docs may be staged.

- [ ] **Step 9: Run the incomplete-marker and semantic-leak scan**

```powershell
rg -n "TO[D]O|FI[X]ME|T[B]D|pass$|Not[I]mplementedError" mcp_server/src/rook/validation_kernel mcp_server/tests -g "test_validation_kernel_*.py"
rg -n -i "radial|box array|grid spacing|grasshopper|rhino|ollama|worker model|gh_edit" mcp_server/src/rook/validation_kernel
```

Expected: no matches. Test names may describe synthetic worker-slot/confirmation-shaped structural cases, but production kernel code remains domain-neutral.

- [ ] **Step 10: Request final code review**

Review explicitly against:

- sealed program authority and runtime binding closure;
- trusted recipe/bundle principal split;
- exact budget and parser boundaries;
- schema profile and runtime dependency identity;
- phase input/output integrity;
- non-circular report seal;
- earliest-honest conformance result matrix;
- exact attempt/completeness accounting;
- concurrent invocation isolation and fresh-process replay;
- absence of LM9A semantic implementation.

- [ ] **Step 11: Commit final review fixes only after rerunning the affected gates**

Use a narrow commit message describing the actual correction. Do not squash evidence-producing test commits merely to shorten history.

## Completion Boundary

This plan is complete when the generic kernel and its domain-neutral conformance proof pass deterministically. It does **not** make LM9A recipe validation available yet. The next artifact after merge is a separate LM9A-Semantics implementation plan that contributes schemas, runners, vocabularies, report projection, and the reviewed offline fixtures to this sealed kernel.

No live or model evidence is valid at the LM9A-Kernel boundary.
