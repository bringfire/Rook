# LM9B-P Planner Recipe Transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run one offline, two-checkpoint probe that preserves a frontier Planner's raw `rook.planner_graph_recipe:v1`, scores authorship independently, and conditionally passes the same bytes through the landed LM9B-C compiler path.

**Architecture:** Build the slice vertically. First prove without models that one non-R01 canonical recipe and the exact ratified companions traverse the mechanical gate, reconcile the ratified and historical fingerprints, cross an R01-free handoff, render through unchanged LM9B-C code, and reach a fake compiler provider. Then replace recorded inputs at that proven boundary with one bounded Planner session and zero or one independent evaluator session. Probe classifications remain experimental; this plan does not implement LM9A semantic authority.

**Tech Stack:** Python 3.10 and 3.12, pytest, `jsonschema==4.26.0`, the landed `rook.validation_kernel` JCS primitives, LiteLLM through the existing LM9B-C adapter, and the existing LM9B-C compiler-sufficiency probe.

**Checkpoint Counter-Hypotheses:**
- Checkpoint 1: a frontier Planner cannot author a mechanically admissible and semantically faithful candidate without leakage or repair.
- Checkpoint 2: a mechanically admissible and semantically faithful model-authored candidate cannot enter the proven compiler path unchanged.

An honest `probe_candidate_blocked` supports neither counter-hypothesis. R01 is a matched historical control, not a strict single-variable control.

## File Map

| File | Responsibility |
| --- | --- |
| `scripts/lm9b_p_planner_recipe_transfer_support.py` | Strict parsing, one normalization profile, mechanical gate, fingerprint handshake, session records, and classifications |
| `scripts/lm9b_p_planner_recipe_transfer_artifacts.py` | Allowlisted input loading, rendering, R01-free LM9B-C handoff, and evidence writing |
| `scripts/lm9b_p_planner_recipe_transfer_probe.py` | Two-checkpoint orchestration, conditional join, aggregate classification, and CLI |
| `scripts/lm9b_p_fixtures/**` | Brief, exact ratified companions, probe schema/profile, authoring contract, exclusion policy, and rubric |
| `mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json` | Test-only constructive witness; never rendered to the Planner |
| `mcp_server/tests/fixtures/lm9b_p/non_r01_blocked_recipe.json` | Test-only honest unresolved witness; never enters LM9B-C |
| `mcp_server/tests/test_lm9b_p_constructive_witness.py` | No-model proof of the joined handoff |
| `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py` | Parser, profile, gate, session, and classification tests |
| `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_artifacts.py` | Isolation, renderer, handoff, and archive tests |
| `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py` | Orchestration and outcome-attribution tests |

## Admitted-Language Closure Ledger

The probe schema defines one finite workerless subset of the ratified recipe
language. Tests construct each positive carrier before applying one-property
boundary mutations. This table, the schema, normalization profile, structural
checker, Task 3 authoring contract, and Task 3 rubric must agree; none may
silently broaden another.

| Recipe carrier | Admitted kind or code | Mechanical boundary |
| --- | --- | --- |
| all common-clause `source_refs` | `artifact_value` | policy rules reject as source truth |
| clause `assumption_refs` / `derived_fact_refs` | matching typed local reference | per-kind namespace resolution |
| clause `synthesis.kind` | exact clause-kind synthesis code | another clause kind's code rejects |
| assumption `typed_value.unit_context_ref` | null or `artifact_value` | policy rules reject |
| assumption `basis_refs` | ratified non-receipt semantic-reference union | exact variant shape and typed target resolution |
| assumption authorization policy refs | `policy_rule` | artifact values reject |
| derived-fact operator and inputs | `multiply`; `artifact_value` inputs | unknown operators and policy inputs reject |
| unresolved authorization and unit context | `policy_rule`; null or `artifact_value` | reversed authority roles reject |
| homogeneous clause/projection links | field-declared target namespace | missing or wrong-kind targets reject |
| shape, capability, value, and materiality codes | supplied finite vocabularies | unknown or context-invalid codes reject |
| worker slots and confirmation receipts | absent in this profile | nonempty or attached forms reject |
| all set-like collections | normalization-profile row | duplicates or noncanonical order reject |

### Relational Invariants

Carrier-valid fields form an admitted recipe only when these cross-field
equations also hold:

```text
for every clause:
  source_refs != []
  or assumption_refs != []
  or permitted derived_fact_refs != []
  or synthesis != null

for every nested canonicalization:
  applies_to_clause_ids == [containing maintains clause ID]
  inherited_support_from == []
  or inherited_support_from == [containing maintains clause ID]

for every nested postcondition:
  inherited_support_from == []
  or inherited_support_from == [containing maintains clause ID]
```

Inherited parent support does not satisfy the direct-support-or-synthesis
equation. Parameterized tests cover all six clause kinds, the valid synthesis
branch, absent inheritance, exact parent inheritance, a valid sibling
substitution, and a missing-parent substitution.

This is an executable design ledger, not a new production artifact or schema
generator. Any newly admitted field must add its positive witness, nearest
one-property boundary mutation, relational equation where applicable, and
normalization/namespace rule in the same change.

## Global Constraints

- Use `docs/superpowers/specs/2026-07-19-lm9b-p-planner-recipe-transfer-design.md` as normative.
- Do not modify `mcp_server/src/rook/validation_kernel/**`, `scripts/lm9b_c_compiler_sufficiency_*.py`, `scripts/lm9b_c_fixtures/**`, or existing LM9B-C tests.
- Do not add LM9A semantic validation, recipe syntax, semantic codes, policy outcomes, representations, product-agent behavior, mutation, retrieval, Rhino, or Grasshopper execution.
- Existing Rook artifact identities are imported exactly. Probe simplifications use probe-specific IDs and cannot support a full-contract claim.
- Mechanical checks establish only bounded JSON, frozen probe-schema conformance, reference/hash integrity, canonical normal form, exclusion compliance, and byte equality.
- Mechanical checks do not infer policy authorization, semantic fidelity, assumption quality, official `valid`, or official `compile_ready`.
- R01, its path, hashes, and manifest row are unavailable to production probe code and the canonical pre-freeze path. Post-freeze comparison may read R01 only after aggregate classification is sealed.
- The join may content-address and wrap accepted bytes. It may not parse, reserialize, normalize, translate, enrich, repair, or rewrite them.
- No model call occurs until deterministic work is committed and independently reviewed.
- The campaign is exactly one Planner session, zero or one Planner-evaluator session, zero or one compiler session, and zero or one compiler-evaluator session. None may be retried.
- Preserve complete visible evidence. Do not request or persist hidden reasoning.
- Planner-evaluator and compiler results never return to the Planner. The compiler receives no brief, Planner evaluation, Planner transcript, R01, or post-submission semantic hint.
- Use this worktree-safe interpreter in every test command:

```powershell
$RookPython = 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe'
& $RookPython --version
```

Expected: `Python 3.12.12`. Use `py -3.10 -m py_compile` for Python 3.10 compatibility. Never use a worktree-relative `.venv`.

---

### Task 1: Prove The Constructive Joined Witness Without Models

**Files:**
- Create: `scripts/lm9b_p_fixtures/task_envelope.json`
- Create: `scripts/lm9b_p_fixtures/environment_snapshot.json`
- Create: `scripts/lm9b_p_fixtures/attempt_context.json`
- Create: `scripts/lm9b_p_fixtures/planning_policy.json`
- Create: `scripts/lm9b_p_fixtures/payload_schema_registry.json`
- Create: `scripts/lm9b_p_fixtures/capability_registry.json`
- Create: `scripts/lm9b_p_fixtures/semantic_authority_code_vocabulary.json`
- Create: `scripts/lm9b_p_fixtures/semantic_capability_code_vocabulary.json`
- Create: `scripts/lm9b_p_fixtures/worker_slot_code_vocabulary.json`
- Create: `scripts/lm9b_p_fixtures/semantic_materiality_code_vocabulary.json`
- Create: `scripts/lm9b_p_fixtures/semantic_value_schema_registry.json`
- Create: `scripts/lm9b_p_fixtures/planner_recipe_probe_schema.json`
- Create: `scripts/lm9b_p_fixtures/recipe_normalization_profile.json`
- Create: `mcp_server/tests/fixtures/lm9b_p/non_r01_ready_recipe.json`
- Create: `mcp_server/tests/fixtures/lm9b_p/non_r01_blocked_recipe.json`
- Create: `scripts/lm9b_p_planner_recipe_transfer_support.py`
- Create: `scripts/lm9b_p_planner_recipe_transfer_artifacts.py`
- Create: `mcp_server/tests/test_lm9b_p_constructive_witness.py`
- Create: `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py`
- Create: `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_artifacts.py`

**Interfaces:**
- Support produces `StrictJsonDocument`, `NormalizationProfile`, `MechanicalGateResult`, `parse_strict_json()`, `normalize_recipe()`, and `evaluate_mechanical_gate()`.
- Artifacts produces `FrozenPlannerAuthority`, `Lm9bcHandoff`, `load_planner_authority_context()`, and `build_lm9bc_handoff()`.
- The witness consumes public LM9B-C `load_frozen_inputs`, `render_compiler_request`, `run_probe`, `COMPILER_RENDERER_ID`, `ProviderTurn`, and `ProviderCallFailure`.
- Task 1 production code cannot read `r01_recipe.json` or LM9B-C's `input_manifest.json`.
- The fixed `evaluated_at`, deterministic clock source, and three session IDs
  enter through `attempt_context.json`; ambient wall time is forbidden.

- [ ] **Step 1: Add the failing vertical witness**

```python
def test_non_r01_ready_recipe_reaches_unchanged_fake_compiler_provider(
    tmp_path: Path,
) -> None:
    authority = ARTIFACTS.load_planner_authority_context(PLANNER_FIXTURES)
    recipe_bytes = NON_R01_READY_RECIPE.read_bytes()
    gate = SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=recipe_bytes,
        authority=authority,
        recipe_schema=authority.recipe_schema,
        normalization_profile=authority.normalization_profile,
    )
    assert gate.status == "mechanically_accepted"
    assert gate.final_recipe_bytes == recipe_bytes
    assert gate.ratified_recipe_fingerprint == gate.historical_recipe_fingerprint

    handoff = ARTIFACTS.build_lm9bc_handoff(
        accepted_recipe_bytes=recipe_bytes,
        accepted_recipe_fingerprint=gate.ratified_recipe_fingerprint,
        planner_fixture_dir=PLANNER_FIXTURES,
        compiler_fixture_dir=LM9B_C_FIXTURES,
        destination=tmp_path / "handoff",
    )
    assert handoff.archived_recipe_bytes == recipe_bytes
    assert handoff.compiler_renderer_id == LM9B_C_ARTIFACTS.COMPILER_RENDERER_ID
    assert "r01" not in json.dumps(handoff.manifest).lower()

    loaded = LM9B_C_ARTIFACTS.load_frozen_inputs(handoff.fixture_dir)
    rendered = LM9B_C_ARTIFACTS.render_compiler_request(loaded)
    assert rendered.renderer_id == LM9B_C_ARTIFACTS.COMPILER_RENDERER_ID

    calls: list[dict[str, object]] = []

    def fake_compiler(payload: dict[str, object]) -> ProviderTurn:
        calls.append(payload)
        raise ProviderCallFailure(
            failure_type="constructive_witness_stop",
            message="constructive witness stop",
            raw_request=b"",
            raw_error=b"constructive witness stop",
        )

    result = LM9B_C_PROBE.run_probe(
        run_root=tmp_path / "compiler-run",
        fixture_dir=handoff.fixture_dir,
        compiler_provider=fake_compiler,
        evaluator_provider=lambda payload: (_ for _ in ()).throw(
            AssertionError("evaluator must not run")
        ),
        compiler_identity={"provider": "fake", "model": "constructive-witness"},
        evaluator_identity={"provider": "fake", "model": "unused"},
        git_sha="constructivewitness",
    )
    assert len(calls) == 1
    assert result.decision.outcome == "inconclusive"
```

This proves provider contact after unchanged load/render. It does not claim compiler success.

- [ ] **Step 2: Add exact-contract fixture tests**

Require these exact identities and complete v1 entries:

| Schema | Version | Complete entries |
| --- | --- | --- |
| `rook.semantic_authority_code_vocabulary:v1` | `rook.semantic_authority_codes:v1` | `select_representation`, `construct_topology`, `lower_verification`, `instantiate_worker_slot` |
| `rook.semantic_capability_code_vocabulary:v1` | `rook.semantic_capability_codes:v1` | `construct_parametric_geometry`, `manage_document_layers` |
| `rook.worker_slot_code_vocabulary:v1` | `rook.worker_slot_codes:v1` | `author_formula_realization` |
| `rook.semantic_materiality_code_vocabulary:v1` | `rook.semantic_materiality_codes:v1` | `tool_arguments`, `geometry_state`, `document_state`, `target_identity`, `topology`, `execution_branching`, `verifier_predicate`, `verifier_threshold`, `fingerprint`, `canonicalization`, `capability_authority`, `mutation_authority` |
| `rook.semantic_value_schema_registry:v1` | `rook.semantic_value_schemas:v1` | `rook.semantic_integer:v1`, `rook.semantic_scalar:v1`, `rook.semantic_string:v1`, `rook.semantic_boolean:v1`, `rook.semantic_unit_context:v1` |

Assert closed entry fields:

```python
EXPECTED_ENTRY_FIELDS = {
    "rook.semantic_authority_code_vocabulary:v1": {
        "code", "allowed_shape_sections", "allowed_delegate_kinds",
        "requires_worker_slot",
    },
    "rook.semantic_capability_code_vocabulary:v1": {
        "code", "permitted_supporting_clause_kinds",
    },
    "rook.worker_slot_code_vocabulary:v1": {
        "code", "allowed_output_schemas", "allowed_input_kinds",
        "required_shape_authority_code",
    },
    "rook.semantic_materiality_code_vocabulary:v1": {"code"},
    "rook.semantic_value_schema_registry:v1": {"schema"},
}
```

Pin the three compile codes to `compile_phase`; `instantiate_worker_slot` to a required slot; both capabilities to `maintains` and `manage_document_layers` also to `invariants`; and `author_formula_realization` to `rook.worker_formula_realization:v1`, the four ratified input kinds, and `instantiate_worker_slot`. Assert witness `worker_slots.entries == []` independently.

Add payload-authority tests proving that task and environment payload values
remain semantically equal to the historical LM9B-C fixtures; every
`typed_value_fingerprint` equals the canonical fingerprint of
`{schema: value_schema, value: resolved_payload_value}`; each payload-schema
fingerprint matches one complete registry entry; task, environment, and
registry fingerprints recompute exactly; and corrected task/environment bytes
differ from the historical placeholder-bearing fixtures.

Add deterministic admission tests proving the fixed probe time falls inside
the environment, planning-policy, and capability-registry validity intervals;
the task, environment, and capability sessions exactly match the attempt
context; and stale or wrong-session mutations fail before handoff.

- [ ] **Step 3: Add normalization-profile and strict-parser tests**

The committed profile is the only row inventory. It contains exactly 32 recipe-side rows covering authority artifacts; all clause, nested clause, semantic-reference, policy-reference, goal-projection, clause-link, assumption, materiality, derived-fact, unresolved-authority, shape, capability, and worker-slot collections from the ratified ordering table. That explicitly includes `applies_to_clause_ids`, `inherited_support_from`, `affected_clause_ids`, both policy-reference paths, and both unresolved-authority lists.

Tests assert the profile schema, ID, row count, and reviewed canonical fingerprint. They then parameterize directly over its rows. For every `ordered_set` row, the test rotates a populated valid collection, proves parsed-value identities differ, normalizes through the profile, and proves normalized recipes and ratified fingerprints match. `empty_only` worker rows receive zero-only tests. No Python test or production module contains a second path inventory.

The probe schema uses the exact discriminated reference union.
`assumption_refs` contains `{kind: assumption, assumption_id: ...}` records and
`derived_fact_refs` contains `{kind: derived_fact, derived_fact_id: ...}`
records. Both profile rows use `semantic_reference`, and a focused schema test
rejects bare string IDs.

Strict parser tests cover duplicate key, BOM, invalid UTF-8, depth 65, a 1,025-character integer token, `1e10000`, `1.5`, and `NaN`.

- [ ] **Step 4: Run and observe failure**

```powershell
$RookPython = 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe'
& $RookPython -m pytest mcp_server\tests\test_lm9b_p_constructive_witness.py mcp_server\tests\test_lm9b_p_planner_recipe_transfer_support.py mcp_server\tests\test_lm9b_p_planner_recipe_transfer_artifacts.py -q
```

Expected: import or fixture-not-found failure.

- [ ] **Step 5: Create exact companions and the single profile**

Create LM9B-P task and environment artifacts from the same payload facts,
binding IDs, semantic keys, authority kinds, sessions, freshness, and issuer
facts as LM9B-C. Replace every placeholder typed-value and payload-schema
fingerprint with its exact canonical value, then recompute each complete
artifact fingerprint. Copy `planning_policy.json` byte-for-byte only after its
existing artifact fingerprint is independently recomputed.

Create `payload_schema_registry.json` with schema
`rook.payload_schema_registry:v1`, registry ID `payload_schema_registry`,
version `lm9a.payload_schemas:v1`, Draft 2020-12 dialect, profile
`rook.json_schema_profile:lm9a_payload_v1`, and exactly two sorted entries:
`rook.lm9b_c.r01_task_payload:v1` and
`rook.lm9b_c.r01_environment_payload:v1`. Each entry contains a complete
closed schema document for the preserved payload shape and its exact canonical
fingerprint. Recompute the complete registry fingerprint.

Create the five vocabularies with exact IDs, complete entries, and closed shapes from Step 2. Compute `vocabulary_fingerprint` over each full canonical object excluding that field using `canonical_fingerprint(own_trusted_json(value))`. Tests independently recompute all fingerprints.

Create a valid `rook.environment_capability_registry:v1` with `construct_parametric_geometry` available and one opaque generic implementation reference, `manage_document_layers` unavailable with no implementation references, and exact session, freshness, constraints, and fingerprint fields.

```python
EXPECTED_CAPABILITY_REGISTRY_FIELDS = {
    "schema",
    "registry_id",
    "registry_session_id",
    "observed_at",
    "expires_at",
    "entries",
    "registry_fingerprint",
}
EXPECTED_CAPABILITY_ENTRY_FIELDS = {
    "capability_code",
    "availability",
    "implementation_refs",
    "constraints_fingerprint",
}
```

The available entry has at least one implementation reference; the unavailable entry has none. Entries sort by `capability_code`, and the registry fingerprint is recomputed over the complete registry excluding `registry_fingerprint`.

Create `recipe_normalization_profile.json` as the only production declaration
of Step 3 paths. Rows use `field`, `semantic_reference`, or `scalar_utf16`
sort kinds; `ordered_set` or `empty_only` admission; and
`required_container` or `zero_or_more` matching. Top-level required
collections use `required_container`. Nested and parent-optional collections
use `zero_or_more`. Production Python contains no second path list.

- [ ] **Step 6: Implement bounded parsing and profile-driven normalization**

```python
MAX_RECIPE_BYTES = 1_048_576
MAX_JSON_DEPTH = 64
MAX_INTEGER_TOKEN_CHARS = 1_024


def _parse_int(token: str) -> int:
    if len(token) > MAX_INTEGER_TOKEN_CHARS:
        raise ValueError("integer_token_too_long")
    return int(token)


def _reject_float(token: str) -> NoReturn:
    raise ValueError("non_integer_json_number")


def _reject_constant(token: str) -> NoReturn:
    raise ValueError("non_finite_json_number")
```

`parse_strict_json` rejects over-byte input before decode, strict-decodes UTF-8, rejects duplicate keys, calls `json.loads` with all three hooks, catches `json.JSONDecodeError`, `UnicodeError`, `RecursionError`, and `ValueError`, then checks depth iteratively.

```python
value = json.loads(
    decoded,
    object_pairs_hook=_reject_duplicate_pairs,
    parse_int=_parse_int,
    parse_float=_reject_float,
    parse_constant=_reject_constant,
)
```

`normalize_recipe` loads the profile, rejects duplicate sort identities, and
uses UTF-16 ordering plus the ratified semantic-reference rank. Unknown rows,
an unmatched `required_container`, and a nonempty `empty_only` collection
fail. An unmatched `zero_or_more` pattern is valid and cannot create a
collection absent from the recipe.

Ratified fingerprinting and canonical-normal-form checking use this normalizer. Historical compatibility uses `canonical_fingerprint(own_trusted_json(recipe_without_fingerprint))` without set sorting.

- [ ] **Step 7: Create the schema and non-R01 fixture**

Create a closed Draft 2020-12 schema with `$id = rook.lm9b_p.planner_recipe_probe_schema:v1`, `schema = rook.planner_graph_recipe:v1`, complete admitted workerless structure, ratified references and vocabulary IDs, null confirmation refs, null worker links, and `worker_slots.entries.maxItems = 0`. The closed unresolved-intent and invariant contracts remain admitted; workerless admission does not mean R01-shaped empty collections.

The required top-level fields are `schema`, `source_task`,
`authority_artifacts`, `goal`, `requires`, `maintains`, `assumptions`,
`derived_facts`, `unresolved_intent`, `invariants`, `shape`,
`required_capabilities`, `worker_slots`, and `recipe_fingerprint`.
`additionalProperties` is false at every object boundary. The schema reuses the
ratified discriminated semantic-reference shapes and exact vocabulary binding
objects; it does not simplify entries to strings.

Create a hand-authored non-R01 ready recipe that uses the matched radial authority, exact codes and fingerprints, no workers or receipts, canonical normal form, and equal ratified/historical fingerprints. It uses different local IDs and is never Planner-visible.

Create a matched non-R01 blocked recipe by replacing only the spacing assumption and its support references with one closed `unresolved_intent` entry. Prove it passes the mechanical gate. Its real no-compiler routing proof belongs to Task 5, where `probe_candidate_blocked` first exists; Task 1/2 must not invent semantic classification inside the gate.

- [ ] **Step 8: Implement the R01-free handoff**

`build_lm9bc_handoff`:
1. accepts final recipe bytes and checked fingerprint;
2. revalidates frozen-time freshness and session admission and binds the exact
   attempt-context fingerprint into the generated handoff manifest;
3. reads corrected authority only from its explicit `planner_fixture_dir` and
   copies corrected LM9B-P task, environment, and policy bytes plus unchanged
   LM9B-C implementation context, exclusion policy, and evaluation rubric;
4. writes accepted bytes once and proves read-back equality;
5. builds `rook.lm9b_c.input_manifest:v1` directly from those seven files, fixed roles, and exported `COMPILER_RENDERER_ID`;
6. computes hashes from copied bytes;
7. never opens or stats source `input_manifest.json` or `r01_recipe.json`.

Add a read-audit test instrumenting `Path.read_bytes`, `Path.open`, and `Path.stat`.

- [ ] **Step 9: Run the witness**

```powershell
$RookPython = 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe'
& $RookPython -m pytest mcp_server\tests\test_lm9b_p_constructive_witness.py mcp_server\tests\test_lm9b_p_planner_recipe_transfer_support.py mcp_server\tests\test_lm9b_p_planner_recipe_transfer_artifacts.py -q
```

Expected: all pass, including fake-provider contact through unchanged LM9B-C.

- [ ] **Step 10: Commit and request mandatory review**

```powershell
git add scripts/lm9b_p_fixtures scripts/lm9b_p_planner_recipe_transfer_support.py scripts/lm9b_p_planner_recipe_transfer_artifacts.py mcp_server/tests/fixtures/lm9b_p mcp_server/tests/test_lm9b_p_constructive_witness.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_artifacts.py
git commit -m "test(lm9b): prove planner recipe joined witness"
```

Stop if this needs recipe translation, R01 metadata, approximated vocabularies, duplicate normalization tables, a host parser escape, or LM9B-C modification.

---

### Task 2: Complete The Mechanical Gate And Fingerprint Handshake

**Files:**
- Modify: `scripts/lm9b_p_fixtures/planner_recipe_probe_schema.json`
- Modify: `scripts/lm9b_p_fixtures/recipe_normalization_profile.json`
- Modify: `scripts/lm9b_p_planner_recipe_transfer_support.py`
- Create: `mcp_server/tests/fixtures/lm9b_p/non_r01_blocked_recipe.json`
- Modify: `mcp_server/tests/test_lm9b_p_constructive_witness.py`
- Modify: `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py`

**Interfaces:**
- Consumes Task 1 parsing and normalization.
- Produces `MechanicalDiagnostic`, `MechanicalGateResult`, and final mechanically accepted model-submitted bytes.

- [ ] **Step 1: Add the rejection matrix**

Add one named test for each: invalid UTF-8, invalid JSON, duplicate key, oversized integer, float overflow, ordinary non-integer number, non-finite constant, missing required field, unknown field, unknown artifact, missing pointer, artifact hash mismatch, vocabulary fingerprint mismatch, noncanonical collection, nonempty worker slots, forbidden marker, and claimed fingerprint mismatch. Add one finite typed symbol-table pass with one shared clause namespace and separate assumption, derived-fact, unresolved-intent, shape, capability, and worker-slot namespaces. It validates target kinds, unresolved affected-clause links, descriptor joins, exact policy-rule roots, machine grammar, and vocabulary membership without performing semantic LM9A validation.

```python
@dataclass(frozen=True)
class MechanicalDiagnostic:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class MechanicalGateResult:
    status: Literal[
        "probe_mechanically_rejected",
        "fingerprint_resubmission_required",
        "mechanically_accepted",
    ]
    diagnostics: tuple[MechanicalDiagnostic, ...]
    final_recipe_bytes: bytes | None
    recipe_value_fingerprint: str | None
    ratified_recipe_fingerprint: str | None
    historical_recipe_fingerprint: str | None
```

- [ ] **Step 2: Add handshake tests**

Prove an incorrect claimed fingerprint returns the exact computed value; the model may resubmit in the same session; accepted bytes are model-submitted bytes; the gate never patches or serializes; semantic changes move the hash; and noncanonical ordering cannot be cleared by supplying a hash.

- [ ] **Step 3: Implement the fixed gate order**

```text
byte bound
strict parse
probe schema
authority descriptor, hash, and reference resolution
vocabulary identity matching
canonical-normal-form comparison
ratified fingerprint
historical compatibility fingerprint
exclusion policy
```

Fingerprint mismatch is the sole sealing handshake. Other feedback identifies container defects only and never suggests semantics.
Canonical normal form constrains schema-designated set ordering and duplicate
identity only. It does not require a particular object-key order, indentation,
or insignificant-whitespace encoding.

- [ ] **Step 4: Run and commit**

```powershell
$RookPython = 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe'
& $RookPython -m pytest mcp_server\tests\test_lm9b_p_planner_recipe_transfer_support.py -q
git add scripts/lm9b_p_planner_recipe_transfer_support.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py
git commit -m "feat(lm9b): complete planner recipe mechanical gate"
```

---

### Task 3: Render The Frozen Planner Boundary

**Files:**
- Create: `scripts/lm9b_p_fixtures/radial_brief.txt`
- Create: `scripts/lm9b_p_fixtures/planner_authoring_contract.json`
- Create: `scripts/lm9b_p_fixtures/planner_exclusion_policy.json`
- Create: `scripts/lm9b_p_fixtures/planner_evaluation_rubric.json`
- Modify: `scripts/lm9b_p_planner_recipe_transfer_support.py`
- Modify: `scripts/lm9b_p_planner_recipe_transfer_artifacts.py`
- Modify: `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py`
- Modify: `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_artifacts.py`

**Interfaces:**
- Produces `load_planner_inputs() -> FrozenPlannerInputs`, `render_planner_request() -> RenderedRequest`, and `render_planner_evaluator_request() -> RenderedRequest`.
- Planner sees brief, exact trusted authority, authoring contract, and terminal schema.
- Planner request identity includes the exact frozen attempt-context
  fingerprint and renders its evaluation time and session bindings.
- Planner evaluator sees brief, authority, final recipe, deterministic findings, and rubric.

- [ ] **Step 1: Add visibility and whole-process read-isolation tests**

Assert planning policy remains byte-identical; task and environment payload
facts remain semantically equal while corrected fingerprints differ from the
historical placeholder bytes; payload-schema registry, all five vocabularies,
and capability registry are present; Planner sees no rubric, R01 marker,
compiler context, expected recipe, C#, or compiler schema; evaluator sees no
Planner transcript, compiler output, R01, or expected answer; pre-freeze reads
exclude R01, LM9B-C's source manifest, and the non-R01 witness; and
fresh-process hashes match under `PYTHONHASHSEED=1` and `8675309`.
The exclusion-policy test passes the content-addressed policy into the
mechanical gate, changes one forbidden marker, and proves both gate behavior
and rendered request identity move. No hardcoded production marker remains.
Task 3 also parses the authoring contract and evaluator rubric in tests and
checks every authority/reference role they describe against the admitted-
language closure ledger. Prose may explain the language but cannot admit a
reference kind, code, or outcome absent from the executable gate.

- [ ] **Step 2: Create frozen authoring inputs**

`radial_brief.txt` contains exactly:

```text
Create a 10 x 10 array of boxes whose heights are lowest near the center and rise with radial distance from the center.
```

`planner_authoring_contract.json` explains the admitted production recipe grammar without an example recipe. `planner_exclusion_policy.json` is a closed,
fingerprinted probe artifact containing the exact forbidden recipe markers and
request exclusions. It becomes an explicit input to `evaluate_mechanical_gate`;
Task 3 removes Task 2's temporary constant. `planner_evaluation_rubric.json`
freezes scenario-specific fidelity, provenance, material-authority,
unresolved-intent, and implementation-leakage checks without R01 or a solved
recipe.

- [ ] **Step 3: Implement fixed-role loading and rendering**

```python
@dataclass(frozen=True)
class PlannerInputRecord:
    role: str
    relative_path: str
    raw_sha256: str
    canonical_fingerprint: str
    raw_bytes: bytes
    value: object


@dataclass(frozen=True)
class FrozenPlannerInputs:
    records: tuple[PlannerInputRecord, ...]
    brief: str
    authority_context: Mapping[str, object]
    recipe_schema: Mapping[str, object]
    normalization_profile: Mapping[str, object]
    authoring_contract: Mapping[str, object]
    exclusion_policy: Mapping[str, object]
    evaluation_rubric: Mapping[str, object]
```

Load a fixed filename-to-role tuple; do not discover files. Fingerprint original and rendered bytes.
The Planner request and gate both bind the same verified exclusion-policy
fingerprint. A policy object not loaded from the frozen input set cannot be
substituted by a caller.

- [ ] **Step 4: Run and commit**

```powershell
$RookPython = 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe'
& $RookPython -m pytest mcp_server\tests\test_lm9b_p_planner_recipe_transfer_artifacts.py -q
git add scripts/lm9b_p_fixtures scripts/lm9b_p_planner_recipe_transfer_artifacts.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_artifacts.py
git commit -m "feat(lm9b): freeze planner authoring boundary"
```

---

### Task 4: Add The Bounded Planner Session

**Files:**
- Modify: `scripts/lm9b_p_planner_recipe_transfer_support.py`
- Modify: `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py`

**Interfaces:**
- Reuses public LM9B-C `ProviderTurn` and provider-call records.
- Produces `PlannerSessionResult` containing every visible turn, submission, feedback item, usage record, and final accepted bytes.

- [ ] **Step 1: Add protocol tests**

Test exactly one `submit_planner_recipe` tool, at most one call per turn, mechanical feedback for unknown, duplicate, parallel, malformed, and absent calls, fingerprint resubmission, immediate valid termination, free-text rejection, normal turn-limit mechanical rejection, provider failure, timeout, and no post-terminal retry.

The tool has one closed argument object:

```python
PLANNER_TOOL_PARAMETERS = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "recipe_json": {"type": "string", "minLength": 1, "maxLength": 1_048_576}
    },
    "required": ["recipe_json"],
}
```

The adapter must preserve the exact UTF-8 argument string bytes. A provider representation that exposes only a reconstructed mapping is mechanically rejected.

- [ ] **Step 2: Implement bounded records**

```python
PLANNER_MAX_TURNS = 6
PLANNER_MAX_COMPLETION_TOKENS = 16_384
PLANNER_PROVIDER_TIMEOUT_S = 180.0
PLANNER_OVERALL_DEADLINE_S = 600.0
PLANNER_TOKEN_STOP_THRESHOLD = 120_000
PLANNER_COST_STOP_THRESHOLD_USD = 10.0
PLANNER_EVALUATOR_MAX_COMPLETION_TOKENS = 8_192


@dataclass(frozen=True)
class PlannerTurnRecord:
    turn_index: int
    raw_response: bytes
    tool_arguments: bytes | None
    gate_result: MechanicalGateResult | None
    usage: Mapping[str, object]
    elapsed_ms: int


@dataclass(frozen=True)
class PlannerSessionResult:
    termination: Literal[
        "mechanically_accepted",
        "mechanically_rejected",
        "provider_failure",
        "timeout",
    ]
    turns: tuple[PlannerTurnRecord, ...]
    final_recipe_bytes: bytes | None
```

No external retry or controller-authored recipe edit is permitted.
Cumulative token and cost figures are recorded stop thresholds evaluated after
each response, not falsely described as pre-enforced hard caps. Maximum turns,
per-call completion tokens, monotonic deadline, and provider timeout are
pre-enforced.

- [ ] **Step 3: Run and commit**

```powershell
$RookPython = 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe'
& $RookPython -m pytest mcp_server\tests\test_lm9b_p_planner_recipe_transfer_support.py -q
git add scripts/lm9b_p_planner_recipe_transfer_support.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py
git commit -m "feat(lm9b): add bounded planner authoring session"
```

---

### Task 5: Add Independent Planner Evaluation And Checkpoint 1

**Files:**
- Modify: `scripts/lm9b_p_planner_recipe_transfer_support.py`
- Modify: `scripts/lm9b_p_planner_recipe_transfer_artifacts.py`
- Create: `scripts/lm9b_p_planner_recipe_transfer_probe.py`
- Modify: `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py`
- Create: `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py`

**Interfaces:**
- Produces one evaluator recommendation and one mechanically derived Checkpoint 1 classification.
- `probe_candidate_ready` permits experimental compiler entry only; it is not product authority.

- [ ] **Step 1: Add evaluator and classification tests**

Evaluator recommendations are `faithful_ready`, `faithful_blocked`, or `planner_failure`. Controller mapping is:

```text
mechanical rejection                     -> probe_mechanically_rejected
provider, timeout, malformed evaluator   -> probe_inconclusive
faithful blocked unresolved intent       -> probe_candidate_blocked
evaluator planner_failure                -> probe_planner_failure
mechanically accepted + faithful_ready   -> probe_candidate_ready
```

Assert the evaluator cannot issue public classifications and never feeds back to the Planner.
Use the committed `non_r01_blocked_recipe.json` as the constructive blocked input. When its frozen evaluator recommendation is `faithful_blocked`, assert Checkpoint 1 derives `probe_candidate_blocked`, never calls `build_lm9bc_handoff`, never contacts a compiler provider, and records Checkpoint 2 as `not_evaluated`.

- [ ] **Step 2: Implement one evaluator attempt**

Expose only `submit_planner_evaluation` with a closed schema. The evaluator gets brief, exact authority, final recipe, deterministic findings, and rubric. It gets no Planner transcript, compiler input or output, R01, or expected answer. Provider failure, timeout, malformed output, or missing evidence yields `probe_inconclusive` without retry.

- [ ] **Step 3: Implement Checkpoint 1**

`run_planner_checkpoint` loads inputs, renders one request, runs one Planner session, conditionally runs zero or one evaluator, derives one classification, and retains final model-submitted bytes. Honest `probe_candidate_blocked` is legitimate and leaves Checkpoint 2 unevaluated.

- [ ] **Step 4: Run and commit**

```powershell
$RookPython = 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe'
& $RookPython -m pytest mcp_server\tests\test_lm9b_p_planner_recipe_transfer_support.py mcp_server\tests\test_lm9b_p_planner_recipe_transfer_artifacts.py mcp_server\tests\test_lm9b_p_planner_recipe_transfer_probe.py -q
git add scripts/lm9b_p_planner_recipe_transfer_support.py scripts/lm9b_p_planner_recipe_transfer_artifacts.py scripts/lm9b_p_planner_recipe_transfer_probe.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py
git commit -m "feat(lm9b): score planner authorship checkpoint"
```

---

### Task 6: Preserve Complete Checkpoint Evidence

**Files:**
- Modify: `scripts/lm9b_p_planner_recipe_transfer_artifacts.py`
- Modify: `scripts/lm9b_p_planner_recipe_transfer_probe.py`
- Modify: `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_artifacts.py`
- Modify: `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py`

**Interfaces:**
- Produces a content-addressed Checkpoint 1 archive and sealed classification before any join.
- Post-freeze R01 comparison requires the sealed aggregate identity.

- [ ] **Step 1: Add archive completeness and tamper tests**

Require original inputs and manifest, Planner request, every raw response, every tool argument, every feedback record, usage, timing, identity, final recipe bytes and hashes, evaluator request, response and report, Checkpoint 1 classification, and ordered checksum manifest. Delete and mutate each required file in parameterized tests and require verification failure.

- [ ] **Step 2: Implement atomic evidence writing**

Write to a temporary sibling, calculate and verify `checksums.json`, then rename once. Never overwrite. Record committed git SHA, exact model and profile identities, all bounds, and `execution_permitted = false`.

- [ ] **Step 3: Enforce the pre-freeze read allowlist**

Instrument complete Checkpoint 1 and assert no access resolves to R01, LM9B-C's source manifest, or the non-R01 witness. Post-freeze comparison is a separate function requiring a sealed aggregate path and cannot rewrite prior evidence.

- [ ] **Step 4: Run and commit**

```powershell
$RookPython = 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe'
& $RookPython -m pytest mcp_server\tests\test_lm9b_p_planner_recipe_transfer_artifacts.py mcp_server\tests\test_lm9b_p_planner_recipe_transfer_probe.py -q
git add scripts/lm9b_p_planner_recipe_transfer_artifacts.py scripts/lm9b_p_planner_recipe_transfer_probe.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_artifacts.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py
git commit -m "feat(lm9b): archive planner checkpoint evidence"
```

---

### Task 7: Join Ready Bytes Into LM9B-C And Classify The Aggregate

**Files:**
- Modify: `scripts/lm9b_p_planner_recipe_transfer_artifacts.py`
- Modify: `scripts/lm9b_p_planner_recipe_transfer_probe.py`
- Modify: `mcp_server/tests/test_lm9b_p_constructive_witness.py`
- Modify: `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_artifacts.py`
- Modify: `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py`

**Interfaces:**
- Reuses Task 1 `build_lm9bc_handoff`.
- Produces Checkpoint 2 and aggregate outcomes without modifying LM9B-C.

- [ ] **Step 1: Add joined attribution tests**

```text
probe_candidate_ready + bounded_lowering_demonstrated
  -> joined_transfer_demonstrated

probe_candidate_ready + explicit accepted contract_insufficient
  -> contract_gap_demonstrated

probe_candidate_ready + malformed candidate, C# preflight failure, or evaluator rejection
  -> candidate_failure

probe_candidate_ready + pre-session load or render failure
  -> inconclusive

probe_candidate_ready + provider, timeout, or budget failure
  -> inconclusive

any non-ready Checkpoint 1 result
  -> Checkpoint 2 not_evaluated
```

`contract_gap_demonstrated` requires the explicit LM9B-C terminal variant and evaluator acceptance. It is never inferred from candidate failure.

- [ ] **Step 2: Prove byte equality and compatibility**

Assert final Planner bytes equal handoff archive bytes and LM9B-C loaded `recipe_bytes`. Assert the join never parses or serializes. Disclose that compiler-visible input is unchanged LM9B-C's parsed projection plus legal-trace catalog and terminal schema. A reordered set-like input fails Checkpoint 1 rather than being rewritten.

- [ ] **Step 3: Implement aggregate orchestration**

After Checkpoint 1 sealing:
1. publish `not_evaluated` when not ready;
2. build the direct R01-free handoff;
3. classify load, index, or render failure as `inconclusive` without compiler contact;
4. otherwise run one compiler session and zero or one evaluator;
5. preserve and bind the LM9B-C archive;
6. derive aggregate from both checkpoints;
7. seal aggregate before optional matched-control comparison.

- [ ] **Step 4: Run and commit**

```powershell
$RookPython = 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe'
& $RookPython -m pytest mcp_server\tests\test_lm9b_p_constructive_witness.py mcp_server\tests\test_lm9b_p_planner_recipe_transfer_artifacts.py mcp_server\tests\test_lm9b_p_planner_recipe_transfer_probe.py -q
git add scripts/lm9b_p_planner_recipe_transfer_artifacts.py scripts/lm9b_p_planner_recipe_transfer_probe.py mcp_server/tests/test_lm9b_p_constructive_witness.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_artifacts.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py
git commit -m "feat(lm9b): join planner recipe into compiler probe"
```

---

### Task 8: Add CLI, Final Guards, And One Reviewed Attempt

**Files:**
- Modify: `scripts/lm9b_p_planner_recipe_transfer_probe.py`
- Modify: `mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py`
- Create after run: `docs/superpowers/probes/2026-07-20-lm9b-p-planner-recipe-transfer-result.md`
- Create after run: `docs/superpowers/probes/lm9b-p-runs/2026-07-20-canonical/**`

**Interfaces:**
- CLI runs one campaign only after committed deterministic review.
- Result separates observations, probe classifications, limitations, and non-claims.

- [ ] **Step 1: Add CLI and scope guards**

Require `--transmit`, committed clean HEAD, exact model/profile arguments, one unused run root, and refusal to overwrite. Reject imports of `rook.agent.base_agent`, `Rhino`, `Grasshopper`, `gh_edit`, and private validation-kernel names. Reject production R01 references outside the post-freeze comparison function.

Pin compiler and compiler-evaluator identity to
`gemini/gemini-3.1-pro-preview` at temperature `0.0`. Assert the joined call
uses the unchanged LM9B-C constants: 6 turns, 16,384 completion tokens per
compiler call, 180-second provider timeout, 600-second deadline, 120,000-token
stop threshold, USD 10 cost stop threshold, and 8,192 evaluator completion
tokens. Planner model/profile choices are recorded separately and cannot
overwrite the compiler controls.

- [ ] **Step 2: Implement pre-transmission summary**

Print git SHA; all four model identities and bounds; Planner request bytes and hash; authority manifest fingerprint; normalization-profile fingerprint; compiler renderer identity; `R01 pre-freeze access = forbidden`; and `execution permitted = false`. Without `--transmit`, exit before provider contact.

- [ ] **Step 3: Run deterministic verification**

```powershell
$RookPython = 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe'
& $RookPython -m pytest mcp_server\tests\test_lm9b_p_constructive_witness.py mcp_server\tests\test_lm9b_p_planner_recipe_transfer_support.py mcp_server\tests\test_lm9b_p_planner_recipe_transfer_artifacts.py mcp_server\tests\test_lm9b_p_planner_recipe_transfer_probe.py -q
& $RookPython -m pytest mcp_server\tests\test_lm9b_c_compiler_sufficiency_support.py mcp_server\tests\test_lm9b_c_compiler_sufficiency_artifacts.py mcp_server\tests\test_lm9b_c_compiler_sufficiency_probe.py mcp_server\tests\test_validation_kernel_canonical_json.py mcp_server\tests\test_validation_kernel_owned_json.py -q
py -3.10 -m py_compile scripts\lm9b_p_planner_recipe_transfer_support.py scripts\lm9b_p_planner_recipe_transfer_artifacts.py scripts\lm9b_p_planner_recipe_transfer_probe.py
git diff --check
git status --short
```

Expected: tests and compile checks pass; only reviewed LM9B-P scope remains.

- [ ] **Step 4: Commit before transmission**

```powershell
git add scripts/lm9b_p_fixtures scripts/lm9b_p_planner_recipe_transfer_support.py scripts/lm9b_p_planner_recipe_transfer_artifacts.py scripts/lm9b_p_planner_recipe_transfer_probe.py mcp_server/tests/fixtures/lm9b_p mcp_server/tests/test_lm9b_p_constructive_witness.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_artifacts.py mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py
git commit -m "feat(lm9b): implement planner recipe transfer probe"
```

Request independent review of the exact SHA. No transmission occurs before approval.

- [ ] **Step 5: Run exactly one approved attempt**

```powershell
$RookPython = 'C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe'
& $RookPython scripts\lm9b_p_planner_recipe_transfer_probe.py --planner-model gpt-5.4 --planner-evaluator-model gpt-5.4 --compiler-model gemini/gemini-3.1-pro-preview --compiler-evaluator-model gemini/gemini-3.1-pro-preview --planner-temperature 0.0 --planner-evaluator-temperature 0.0 --compiler-temperature 0.0 --compiler-evaluator-temperature 0.0 --run-root docs\superpowers\probes\lm9b-p-runs\2026-07-20-canonical --transmit
```

Do not retry, repair, edit, or rerun toward success.

- [ ] **Step 6: Verify and commit the scientific record**

Recompute all checksums, verify aggregate bindings, prove final Planner bytes equal LM9B-C input bytes when joined, and prove R01 comparison occurred only after aggregate sealing.

The result report contains: question and counter-hypotheses, frozen configuration, Checkpoint 1 observation, Checkpoint 2 observation or `not_evaluated`, aggregate classification, matched historical-control comparison, evidence bindings, limitations, non-claims, and next falsifiable experiment.

```powershell
git add docs/superpowers/probes/2026-07-20-lm9b-p-planner-recipe-transfer-result.md docs/superpowers/probes/lm9b-p-runs/2026-07-20-canonical
git commit -m "docs(lm9b): record planner recipe transfer result"
git diff --check origin/main..HEAD
git status --short
```

Expected: archive checks pass, branch diff is clean, and worktree is clean.

## Review Checkpoints

Fresh review is mandatory:
1. after Task 1, because the vertical witness is the architectural falsifier;
2. after Task 7, because checkpoint attribution and byte transfer are complete;
3. after Task 8 Step 4, before transmission;
4. after the scientific record is committed, before PR creation.

Task 1 review stops the plan if it finds a ratified-contract approximation, hidden R01 read, duplicated normalization mechanics, host parser escape, recipe translation, or LM9B-C modification.
