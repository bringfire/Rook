# LM9B-P Resolution Archive-Evidence Resource Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one governed-resolution-only archive-evidence resource profile that lets bounded cumulative six-turn evidence seal and publicly reconstruct, then use that repaired verifier to publish one separate no-contact forensic report over the exact retained replacement candidate without changing the original attempt.

**Architecture:** Add a pure profile/parser/budget helper selected only by the governed-resolution checkpoint schema and closed member map, integrate it into the existing checkpoint writer/verifier and call capture path, and add a separate forensics module for historical-preflight compatibility, exact retained-source reconstruction, and no-clobber report publication. Preserve the shared 1 MiB parser and every model-facing or decision contract; the original `e81b12cc` attempt remains `post_dispatch_unsealed` and can never issue a checkpoint or ready proof.

**Tech Stack:** Python 3.12.12 from `C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe`, Python standard library, existing `jsonschema==4.26.0`, pytest, Git object reads, Windows non-following filesystem checks, and same-filesystem `Path.rename()` publication.

## Global Constraints

- Work only in `C:/UDEV/Rook/.worktrees/lm9b-p-resolution-archive-evidence-profile-design` on `codex/lm9b-p-resolution-archive-evidence-profile-design`; never modify, clean, reset, or rebase the primary checkout or the operational merge-SHA checkout.
- Base implementation on `e81b12cca0eb750a7f3e730d2376085a915d43dd` and reviewed design commit `90de3972f721e28a1f9d92a11d868f275bdedde4`.
- Treat `C:/Users/bring/rook-lm9b-p-attempts/2026-07-27-governed-resolution-operational/.governed-resolution-e81b12cca0eb-replacement-01.staging` as immutable source evidence. Do not delete, rename, reseal, promote, repair, mark, or write anywhere below it.
- Treat reserved checkpoint destination `C:/Users/bring/rook-lm9b-p-attempts/2026-07-27-governed-resolution-operational/governed-resolution-e81b12cca0eb-replacement-01` as required-absent historical state.
- Pin historical replacement preflight `C:/Users/bring/rook-lm9b-p-attempts/2026-07-27-governed-resolution-operational/governed-resolution-e81b12cca0eb-replacement-01-preflight` and identity `sha256:897337de3d20e126a143576de707ec3b1377033eab49465ac38d793afd97a856`.
- Pin historical instrument `sha256:0b57f30954c375df34b28ba394f2ef281c09388c209e688586187d8759f26d11`, attempt ID `governed-resolution-e81b12cca0eb-replacement-01`, attempt fingerprint `sha256:bd350d895f0e34a67aa7ebe59e1e8c4b3b5b3f4e715aa6d81d5874561af10e42`, marker SHA-256 `sha256:c307db9cf7220df203086c2ce348cdad4bf2def1029653d2125ba6341632a501`, and candidate `checksums.json` SHA-256 `sha256:ee01977cce93887f48cc6a2f13cc33a8e24d00a38ab002f59519c67b03a97999`.
- Make no readiness, Planner, evaluator, compiler, Rhino, Grasshopper, or mutation-provider contact. All execution-path tests use fake providers and fake readiness evidence.
- Do not change `MAX_RECIPE_BYTES`, `parse_strict_json()`, `parse_archive_json()`, their source identities, recipe admission, call/model/token/time/cost limits, prompts, rubric, mechanical gate, isolation gate, classifier, readiness protocol, retry policy, or checkpoint membership.
- Do not add a profile registry, plugins, arbitrary caller limits, executable formula strings, sharding, compression, truncation, omission, lossy summaries, normalization, repair, or a new evidence taxonomy.
- `rook.archive_evidence_resource_profile:lm9b_resolution_v1` is selected only from `rook.lm9b_p.governed_resolution_checkpoint:v1` plus the exact existing member path/role map.
- Writer, public checkpoint verifier, and forensic verifier consume the same exact profile bytes, formula helper, serializer identity, and call-shape carrier.
- For inputs at or below 1 MiB, the new parser must delegate to `parse_archive_json()` and return the identical value or raise the identical exception type and stable rejection ID. Message text is not contractual.
- Post-dispatch raw response/error capture precedes profile admission. Oversized captured evidence remains exact opaque staging evidence and makes the attempt unsealed; it is never discarded.
- The future resource-profile identity constructively changes future instrument, attempt, and preflight identities. Never describe the original `e81b12cc` instrument as containing this profile.
- Feature-HEAD verification of the retained staging is read-only and publishes no report. Actual report publication occurs only after merge, from a clean merge-SHA checkout, at a fresh no-clobber destination bound to that merge SHA.
- The forensic report never seals the original checkpoint, changes `post_dispatch_unsealed`, issues a ready proof, authorizes retry, or creates compiler eligibility.
- Use TDD with valid red states: imports and real symbol ownership must succeed before a test is accepted as failing for missing behavior.
- Use `apply_patch` for edits, non-interactive Git, small commits, and an independent review stop after Task 1’s vertical witness.

---

## File and Ownership Map

### New files

- `scripts/lm9b_p_governed_resolution_contracts/archive_evidence_resource_profile.json`
  - Exact closed profile bytes, member/path roles, formula IDs, integer constants, serializer identities, and self-fingerprint.
- `scripts/lm9b_p_governed_resolution_archive_evidence.py`
  - Pure profile admission, strict JSON parsing with a profile-derived ceiling, indexed formulas, structural call-ledger validation, closure-issued call-shape capability, and field/member checks. No I/O or semantic verification.
- `scripts/lm9b_p_governed_resolution_forensics.py`
  - Historical-preflight compatibility, immutable physical-source loading, independent retained-candidate reconstruction, forensic report writing/reconciliation/public verification, and CLI. No execution, provider, sealing, ready-proof, or compiler imports.
- `mcp_server/tests/test_lm9b_p_governed_resolution_archive_evidence.py`
  - Parser equivalence, profile admission, formula, exact-bound, call-shape capability, and cross-checkout tests.
- `mcp_server/tests/test_lm9b_p_governed_resolution_forensics.py`
  - Historical compatibility, source custody, reconstruction, report identity, mutation, publication, and exact retained-specimen tests.

### Existing files to modify

- `scripts/lm9b_p_governed_resolution_artifacts.py`
  - Re-export the helper-owned member map; bind the profile into future instrument/preflight identity; use profile parsing in checkpoint writing/public verification; expose one shared pure attempt-reconstruction result; keep preflight/default parsers unchanged.
- `scripts/lm9b_p_governed_resolution_probe.py`
  - Apply pre-dispatch request field checks and post-capture field checks without changing provider/model/controller behavior; retain exact opaque evidence on overflow.
- `mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py`
  - Future instrument/preflight identity, archive membership equality, member parsing, and proof-carrier rejection tests.
- `mcp_server/tests/test_lm9b_p_governed_resolution_probe.py`
  - Six-turn future seal/reconstruct witness and pre-/post-dispatch overflow retention.
- `.gitattributes`
  - Pin LF for both new raw-identity-bearing Python modules.
- `docs/superpowers/plans/2026-07-27-lm9b-p-resolution-archive-evidence-resource-profile.md`
  - Track completed implementation steps only after their commands pass.

## Constructive Transition Ledger

| Transition | Authoritative producer | Accepted shape | Re-verifying consumer | Durable evidence |
|---|---|---|---|---|
| Profile | Reviewed contract bytes plus fixed helper constants | Exact closed profile/fingerprint | Instrument assembly, writer, public verifier, forensics | Instrument/profile rows |
| Call cardinality | Strictly parsed call ledger plus closed structural validator | Closure-issued `VerifiedResolutionCallShape` | Planner-session/evaluator member parsers | Recomputed `P/E` and ordered branch projection |
| Future checkpoint | Existing fake/real controller capture | Existing members under role-specific ceilings | Existing provenance verifier plus profile checks | Existing sealed checkpoint identity |
| Historical preflight | Physical preflight plus pinned `e81b12cc` Git blobs | Closure-issued historical compatibility carrier | Forensic source loader only | Observed-instrument report row |
| Retained candidate | Immutable marker/candidate/staging snapshot | Profile-parsed root evidence | Shared attempt reconstruction and isolation gate | Reconstruction report row |
| Forensic report | Five substantive evidence records | Content fingerprint, destination-bound record, six-member checksum ledger | Public forensic verifier | Separate forensic report identity |

---

### Task 1: Prove the Future Six-Turn Checkpoint Vertical

**Review gate:** Stop for independent review after this task. Later hardening must not proceed until the vertical witness proves the real writer and public verifier share the new resource path.

**Files:**
- Create: `scripts/lm9b_p_governed_resolution_contracts/archive_evidence_resource_profile.json`
- Create: `scripts/lm9b_p_governed_resolution_archive_evidence.py`
- Modify: `scripts/lm9b_p_governed_resolution_artifacts.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_probe.py`
- Create: `mcp_server/tests/test_lm9b_p_governed_resolution_archive_evidence.py`
- Modify: `.gitattributes`

**Interfaces:**
- Consumes:
  - `lm9b_p_planner_recipe_transfer_support.parse_archive_json(raw: bytes) -> object`
  - `lm9b_p_governed_resolution_artifacts.RESOLUTION_ARCHIVE_MEMBERS`
  - `lm9b_p_governed_resolution_artifacts.seal_resolution_checkpoint(...)`
  - `lm9b_p_governed_resolution_artifacts.verify_sealed_resolution_checkpoint(...)`
  - existing fake-provider helpers in `test_lm9b_p_governed_resolution_probe.py`
- Produces:
  - `VerifiedResolutionArchiveResourceProfile` as a closure-issued exact type
  - `VerifiedResolutionCallShape` as a closure-issued exact type
  - `admit_resolution_archive_resource_profile(raw: bytes) -> VerifiedResolutionArchiveResourceProfile`
  - `consume_resolution_archive_resource_profile(value: object) -> Mapping[str, object]`
  - `parse_resolution_call_ledger(raw: bytes, *, profile: object) -> tuple[Mapping[str, object], VerifiedResolutionCallShape]`
  - `consume_resolution_call_shape(value: object, *, profile: object) -> Mapping[str, object]`
  - `parse_resolution_archive_member(raw: bytes, *, path: str, profile: object, call_shape: object | None = None) -> object`
  - `resolution_member_ceiling(*, path: str, profile: object, call_shape: object | None = None, preparse: bool) -> int`

- [x] **Step 1: Write the failing six-turn seal/reconstruct witness against the existing instrument**

Add `test_archive_profile_six_turn_vertical_seals_and_publicly_reconstructs`
to `test_lm9b_p_governed_resolution_probe.py` before creating the profile or
helper module. Use the real fake readiness verifier, preflight, reservation,
existing mechanical feedback, and six fake Planner responses. Make turns 1–5
mechanically rejected. For turn 6, derive a mechanically accepted but
isolation-rejected candidate from the reviewed isolated fixture by adding only
the two forbidden `minimum_height` and `maximum_height` postcondition
references and independently recomputing its recipe fingerprint. Do not add a
new production fixture or dispatch the evaluator.

Add deterministic valid padding to the fake Planner response evidence. The
padding size is an explicit test parameter below the planned per-response and
assistant-projection ceilings; it must make both aggregate candidate members
larger than `MAX_RECIPE_BYTES` by construction. The test must assert the
computed padded sizes before executing the attempt rather than relying on the
retained specimen's incidental size.

Invoke `_run_resolution_attempt()` before inspecting provider call counts.
The current orchestrator catches the sealing parser failure. Keep one test
whose failure branch first proves the exact current state, then fails because
the desired sealed state is unavailable:

```python
result = _run_resolution_attempt(...)
if result.state != "sealed":
    assert result.state == "post_dispatch_unsealed"
    assert result.classification is None
    assert result.sealed_checkpoint is None
    assert len(planner_provider.requests) == 6
    assert len(evaluator_provider.requests) == 0
    assert not destination.exists()

    candidate = staging / ".archive-candidate"
    assert len((candidate / "call-ledger.json").read_bytes()) > (
        PLANNER_SUPPORT.MAX_RECIPE_BYTES
    )
    assert len((candidate / "planner-session.json").read_bytes()) > (
        PLANNER_SUPPORT.MAX_RECIPE_BYTES
    )
    marker = PLANNER_SUPPORT.parse_archive_json(
        (staging / "post_dispatch_unsealed.json").read_bytes()
    )
    assert marker["failure_locus"] == "checkpoint_seal_failure:StrictJsonError"
    pytest.fail("archive evidence profile must seal the bounded six-turn witness")

assert result.classification == "probe_resolution_isolation_failure"
```

`.resolution-runtime` contains per-call evidence, not the aggregate ledger.
The aggregate `call-ledger.json` and `planner-session.json` exist only in
`.archive-candidate` after the seal writer has constructed them.

- [x] **Step 2: Run and record the exact red state**

Run:

```powershell
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_lm9b_p_governed_resolution_probe.py::test_archive_profile_six_turn_vertical_seals_and_publicly_reconstructs -q
```

Expected red: the assertions above observe `post_dispatch_unsealed` and
`checkpoint_seal_failure:StrictJsonError`; the test fails only because the
expected sealed result is not produced. An import/attribute error, an assumed
provider-call count, or an exception escaping `_run_resolution_attempt()` is
not valid RED evidence.

- [x] **Step 3: Add the exact profile contract and import-valid helper surface**

Add a canonical one-line JSON contract with these top-level fields only:

```json
{
  "schema": "rook.archive_evidence_resource_profile:v1",
  "profile_id": "rook.archive_evidence_resource_profile:lm9b_resolution_v1",
  "checkpoint_schema_id": "rook.lm9b_p.governed_resolution_checkpoint:v1",
  "formula_ids": ["call_ledger_v1", "evaluator_member_v1", "fixed_member_v1", "planner_session_v1", "recipe_member_v1"],
  "constants": {
    "absolute_member_ceiling_bytes": 345068924,
    "adapter_request_overhead_bytes": 131072,
    "base64_denominator": 3,
    "base64_numerator": 4,
    "evaluator_assistant_projection_bytes": 1048576,
    "evaluator_canonical_request_bytes": 4194304,
    "evaluator_member_framing_bytes": 262144,
    "evaluator_parsed_result_bytes": 1048576,
    "evaluator_raw_error_bytes": 524288,
    "evaluator_raw_response_bytes": 1048576,
    "json_string_escape_multiplier": 6,
    "ledger_framing_bytes": 262144,
    "max_evaluator_calls": 1,
    "max_planner_calls": 6,
    "max_recipe_bytes": 1048576,
    "planner_assistant_projection_bytes": 2097152,
    "planner_canonical_request_base_bytes": 262144,
    "planner_feedback_projection_bytes": 262144,
    "planner_request_turn_framing_bytes": 65536,
    "planner_raw_error_bytes": 524288,
    "planner_raw_response_bytes": 2097152,
    "planner_session_framing_bytes": 262144,
    "provider_metadata_bytes": 262144,
    "row_framing_bytes": 65536,
    "turn_summary_bytes": 262144,
    "usage_bytes": 65536
  },
  "serializer": {
    "base64": "rfc4648_standard_padded:v1",
    "canonical_json": "python_json_dumps.ensure_ascii_false.sort_keys_true.separators_comma_colon:utf8:v1",
    "json_string_escaping": "json_worst_case_six_bytes_per_input_byte:v1",
    "utf8": "strict_no_bom:v1"
  },
  "members": [
    {"path":"authority.json","role":"authority","formula_id":"fixed_member_v1","fixed_ceiling_bytes":4194304},
    {"path":"boundary.json","role":"boundary","formula_id":"fixed_member_v1","fixed_ceiling_bytes":1048576},
    {"path":"call-ledger.json","role":"calls","formula_id":"call_ledger_v1"},
    {"path":"candidate-recipe.json","role":"candidate","formula_id":"recipe_member_v1"},
    {"path":"checkpoint-gate.json","role":"candidate","formula_id":"fixed_member_v1","fixed_ceiling_bytes":2097152},
    {"path":"checksums.json","role":"checksums","formula_id":"fixed_member_v1","fixed_ceiling_bytes":1048576},
    {"path":"classification.json","role":"outcome","formula_id":"fixed_member_v1","fixed_ceiling_bytes":1048576},
    {"path":"correspondence.json","role":"correspondence","formula_id":"fixed_member_v1","fixed_ceiling_bytes":2097152},
    {"path":"evaluator.json","role":"evaluator","formula_id":"evaluator_member_v1"},
    {"path":"instrument.json","role":"instrument","formula_id":"fixed_member_v1","fixed_ceiling_bytes":2097152},
    {"path":"isolation.json","role":"isolation","formula_id":"fixed_member_v1","fixed_ceiling_bytes":4194304},
    {"path":"launch.json","role":"launch","formula_id":"fixed_member_v1","fixed_ceiling_bytes":1048576},
    {"path":"migration.json","role":"migration","formula_id":"fixed_member_v1","fixed_ceiling_bytes":4194304},
    {"path":"planner-session.json","role":"planner","formula_id":"planner_session_v1"},
    {"path":"readiness.json","role":"readiness","formula_id":"fixed_member_v1","fixed_ceiling_bytes":1048576},
    {"path":"record.json","role":"identity","formula_id":"fixed_member_v1","fixed_ceiling_bytes":1048576},
    {"path":"source.json","role":"source","formula_id":"fixed_member_v1","fixed_ceiling_bytes":1048576}
  ],
  "profile_fingerprint": "sha256:271d641d5b7cebc1ffa7e2f8c924eb7a9f5d0d55f36d69f91995a597af23909b"
}
```

The fingerprint is over the canonical object without `profile_fingerprint`. Reject reordered `members`, any duplicate path/role row, any unknown formula, a changed constant, or a member map unequal to the existing closed map.

Add these import-valid constants and signatures to the new helper. Bodies may raise `NotImplementedError("task1 walking vertical")` only until Step 3:

```python
PROFILE_SCHEMA_ID = "rook.archive_evidence_resource_profile:v1"
PROFILE_ID = "rook.archive_evidence_resource_profile:lm9b_resolution_v1"
CHECKPOINT_SCHEMA_ID = "rook.lm9b_p.governed_resolution_checkpoint:v1"
PROFILE_FINGERPRINT = "sha256:271d641d5b7cebc1ffa7e2f8c924eb7a9f5d0d55f36d69f91995a597af23909b"
MAX_PLANNER_CALLS = 6
MAX_EVALUATOR_CALLS = 1

class ResolutionArchiveEvidenceError(ValueError):
    pass
```

Pin LF in `.gitattributes`:

```gitattributes
scripts/lm9b_p_governed_resolution_archive_evidence.py text eol=lf
scripts/lm9b_p_governed_resolution_forensics.py text eol=lf
```

- [x] **Step 4: Implement the minimum closure-issued profile and call-shape path**

Build both capabilities with closure-local classes and `weakref.WeakKeyDictionary` snapshots. Public classes have only `__weakref__` storage; direct construction, `object.__new__`, copying, replacement, subclassing, and instance mutation cannot register or alter a snapshot.

Use this structural call snapshot:

```python
@dataclass(frozen=True)
class _CallShapeSnapshot:
    profile_fingerprint: str
    planner_count: int
    evaluator_count: int
    ordered_roles: tuple[str, ...]
    ordered_indexes: tuple[int, ...]
    branch_kinds: tuple[str, ...]
    terminal_flags: tuple[bool, ...]
```

`parse_resolution_call_ledger()` must:

1. apply `call_ledger_v1` with `P=6`, `E=1` before parsing;
2. parse strict JSON;
3. require schema `rook.lm9b_p.governed_resolution_call_ledger:v1` and exact row fields;
4. require contiguous zero-based call indexes, Planner rows before the optional evaluator row, `1..6` Planner rows, `0..1` evaluator rows, exclusive response/error branches, recognized outcomes, and complete per-call terminal/quiescent evidence;
5. issue the carrier only after all structural checks pass;
6. reapply the actual-count ledger ceiling before returning.

This capability proves parser-budget shape only. A row's `terminal` flag means its owned adapter execution completed; it does not terminate the whole attempt. Request/transcript/provider provenance, derived attempt termination, and the ban on calls after an attempt terminal remain the later artifact verifier's responsibility.

- [x] **Step 5: Integrate the walking path into the real writer and verifier**

In `lm9b_p_governed_resolution_artifacts.py`:

```python
RESOLUTION_ARCHIVE_MEMBERS = ARCHIVE_EVIDENCE.RESOLUTION_ARCHIVE_MEMBERS
ARCHIVE_EVIDENCE_PROFILE_PATH = (
    _SCRIPTS_DIR
    / "lm9b_p_governed_resolution_contracts"
    / "archive_evidence_resource_profile.json"
)
```

Add the `archive_resource` section to `assemble_task1_resolution_instrument()` with raw profile SHA-256, profile fingerprint, member-map fingerprint, formula/constants fingerprint, helper source fingerprint, evaluator report/parser/limits fingerprint, writer/verifier fingerprints, and reviewed commit. This section must participate in `instrument_fingerprint`, so every future attempt/preflight identity moves.

In `_verify_resolution_checkpoint_archive()`:

```text
verify independently supplied preflight and profile identity
-> parse call-ledger.json and issue VerifiedResolutionCallShape
-> parse every other present member by exact path/role
-> use the carrier for planner-session.json and evaluator.json
-> run existing provenance/mechanical/isolation/evaluator/classification reconstruction
```

In `seal_resolution_checkpoint()`, write the candidate, reread it through that same private verifier, then perform the existing no-clobber rename. Do not change membership, record identity, finalization, or ready-proof equations.

- [x] **Step 6: Run the vertical and focused compatibility tests**

Run:

```powershell
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py::test_archive_profile_six_turn_vertical_seals_and_publicly_reconstructs `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py `
  -q
```

Expected: PASS. Existing one-/two-turn fake checkpoints still reconstruct, recipe members remain limited to 1 MiB, and evaluator-less checkpoints retain no `evaluator.json`.

The GREEN vertical additionally inspects the sealed destination rather than
staging:

```python
assert result.state == "sealed"
assert result.classification == "probe_resolution_isolation_failure"
assert len((result.sealed_checkpoint.archive_dir / "call-ledger.json").read_bytes()) > (
    PLANNER_SUPPORT.MAX_RECIPE_BYTES
)
assert len((result.sealed_checkpoint.archive_dir / "planner-session.json").read_bytes()) > (
    PLANNER_SUPPORT.MAX_RECIPE_BYTES
)
verified = ARTIFACTS.verify_sealed_resolution_checkpoint(
    result.sealed_checkpoint.archive_dir,
    expected_identity=result.sealed_checkpoint.checkpoint_identity,
    preflight_archive=preflight.archive_dir,
    expected_preflight_fingerprint=preflight.preflight_fingerprint,
)
assert verified.classification == "probe_resolution_isolation_failure"
```

- [x] **Step 7: Commit and stop for independent Task 1 review**

```powershell
git add .gitattributes `
  scripts/lm9b_p_governed_resolution_contracts/archive_evidence_resource_profile.json `
  scripts/lm9b_p_governed_resolution_archive_evidence.py `
  scripts/lm9b_p_governed_resolution_artifacts.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_archive_evidence.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py `
  docs/superpowers/plans/2026-07-27-lm9b-p-resolution-archive-evidence-resource-profile.md
git commit -m "feat: add resolution archive evidence vertical"
```

Stop. Independent review must verify the profile is in the real instrument/preflight identity and that the >1 MiB cumulative members traverse the public writer/verifier rather than a test-only parser.

---

### Task 2: Close Parser Equivalence, Formula Arithmetic, and Call-Shape Capability

**Files:**
- Modify: `scripts/lm9b_p_governed_resolution_archive_evidence.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_archive_evidence.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py`

**Interfaces:**
- Consumes Task 1 profile/call-shape interfaces.
- Produces:
  - `resolution_call_row_ceiling(*, role: str, ordinal: int, profile: object) -> int`
  - `resolution_evaluator_member_ceiling(*, evaluator_count: int, profile: object) -> int`
  - `validate_resolution_call_field_bounds(*, row: Mapping[str, object], profile: object) -> None`
  - stable `ResolutionArchiveEvidenceError` rejection IDs for profile/resource failures

- [x] **Step 1: Write the under-limit parser equivalence corpus**

Parameterize valid and invalid raw bytes through both parsers:

```python
@pytest.mark.parametrize(
    "raw",
    [
        b"{}",
        b"[]",
        b'{"float":0.0,"unicode":"\\u03bb"}',
        b'{"a":1,"a":2}',
        b"\xef\xbb\xbf{}",
        b"\xff",
        b'{"n":NaN}',
        b'{"n":1e999}',
        b'{"n":' + b"1" * 1025 + b"}",
        b'{"unterminated":',
    ],
)
def test_under_limit_parser_is_behaviorally_identical(raw: bytes) -> None:
    assert_same_value_or_exception_type_and_rejection_id(
        lambda: PLANNER_SUPPORT.parse_archive_json(raw),
        lambda: ARCHIVE_EVIDENCE.parse_resolution_archive_member(
            raw,
            path="source.json",
            profile=_profile(),
        ),
    )
```

Add generated depth-bound vectors and exact 1 MiB valid/invalid vectors. The assertion compares returned values or `(type(exc), str(exc))`; it never compares incidental chained messages.

Run the new test and require a valid red caused by missing equivalence behavior, then implement direct delegation:

```python
ceiling = resolution_member_ceiling(
    path=path,
    profile=profile,
    call_shape=call_shape,
    preparse=call_shape is None,
)
if len(raw) > ceiling:
    raise ResolutionArchiveEvidenceError(
        "resolution_archive_member_bytes_exceeded"
    )
if len(raw) <= PLANNER_SUPPORT.MAX_RECIPE_BYTES:
    value = PLANNER_SUPPORT.parse_archive_json(raw)
else:
    value = _parse_larger_archive_member_with_existing_grammar(raw, ceiling)
```

Do not edit `lm9b_p_planner_recipe_transfer_support.py`.

- [x] **Step 2: Add the explicit over-limit boundary-divergence table**

Create a valid JSON value of exactly `MAX_RECIPE_BYTES + 1` bytes and assert the historical parser rejects it. Use `instrument.json` for the positive profile-selected case because its ceiling exceeds 1 MiB, and use `candidate-recipe.json` for the preserved 1 MiB refusal:

```python
with pytest.raises(PLANNER_SUPPORT.StrictJsonError, match="recipe_input_bytes_exceeded"):
    PLANNER_SUPPORT.parse_archive_json(raw)

assert ARCHIVE_EVIDENCE.parse_resolution_archive_member(
    raw,
    path="instrument.json",
    profile=_profile(),
) == expected

with pytest.raises(
    ARCHIVE_EVIDENCE.ResolutionArchiveEvidenceError,
    match="resolution_archive_member_bytes_exceeded",
):
    ARCHIVE_EVIDENCE.parse_resolution_archive_member(
        raw,
        path="candidate-recipe.json",
        profile=_profile(),
    )
```

No equivalence claim applies above 1 MiB.

- [x] **Step 3: Implement and test the fixed formula IDs**

Implement these exact helpers:

```python
def _base64_ceiling(size: int) -> int:
    return 4 * ((size + 2) // 3)

def _json_string_ceiling(size: int, *, escape_multiplier: int) -> int:
    return 2 + escape_multiplier * size

def _planner_canonical_request_ceiling(turn: int, constants) -> int:
    if turn == 1:
        return constants["planner_canonical_request_base_bytes"]
    return (
        _planner_canonical_request_ceiling(turn - 1, constants)
        + constants["planner_assistant_projection_bytes"]
        + constants["planner_feedback_projection_bytes"]
        + constants["planner_request_turn_framing_bytes"]
    )

def _planner_row_ceiling(turn: int, constants) -> int:
    request = _planner_canonical_request_ceiling(turn, constants)
    adapter = request + constants["adapter_request_overhead_bytes"]
    return (
        constants["row_framing_bytes"]
        + _json_string_ceiling(
            request,
            escape_multiplier=constants["json_string_escape_multiplier"],
        )
        + _base64_ceiling(adapter)
        + max(
            _base64_ceiling(constants["planner_raw_response_bytes"]),
            _base64_ceiling(constants["planner_raw_error_bytes"]),
        )
        + constants["planner_assistant_projection_bytes"]
        + constants["usage_bytes"]
        + constants["provider_metadata_bytes"]
    )
```

Implement the evaluator row with its evaluator constants. Then use indexed sums:

```python
call_ledger_ceiling(P, E) = ledger_framing + sum(
    planner_row_ceiling(i) for i in range(1, P + 1)
) + sum(evaluator_row_ceiling(j) for j in range(1, E + 1))

planner_session_ceiling(P) = planner_session_framing + sum(
    planner_row_ceiling(i) + turn_summary_bytes
    for i in range(1, P + 1)
)

evaluator_member_ceiling(1) = (
    evaluator_member_framing
    + evaluator_row_ceiling(1)
    + evaluator_parsed_result_bytes
)
```

The recurrence is a closure equation, not an estimate fitted to the retained
specimen. Before constructing Planner request `i + 1`, validate the exact
canonical bytes of admitted assistant projection `i` and deterministic
mechanical-feedback projection `i` against their respective constants. The
fixed framing constant covers the exact message-array separators, role/tool
fields, and JSON framing introduced by appending those two messages. Thus:

```text
R(1) = planner_canonical_request_base_bytes
R(i + 1) =
  R(i)
  + planner_assistant_projection_bytes
  + planner_feedback_projection_bytes
  + planner_request_turn_framing_bytes
```

No response admitted at turn `i` can make the next request exceed `R(i + 1)`.
If the assistant or generated feedback exceeds its own bound after a dispatch,
the attempt retains evidence and becomes unsealed; the oversized projection
never expands or enters a later request.

Require every derived ceiling to be at most
`absolute_member_ceiling_bytes`. With the exact contract constants above, the
maximum authenticated aggregate is
`call_ledger_ceiling(6, 1) == 345068924`, which is also the absolute ceiling.
Test:

- `R(i + 1) == R(i) + assistant + feedback + framing` for every `i=1..5`;
- a maximum admitted assistant plus maximum admitted feedback constructs the
  next request at or below `R(i + 1)` for every turn;
- one byte over either contributing bound refuses before constructing or
  dispatching the next request;
- exact bound and bound plus one for every turn, evaluator row, aggregate
  member, and path-specific fixed member.

- [x] **Step 4: Close evaluator presence and branch equations**

Test both reachable cases:

```text
E=0 -> evaluator.json absent from resolution_archive_member_paths()
E=1 -> evaluator.json present and exactly projects authenticated evaluator row 1
```

For `E=1`, fully reclose mutations of canonical request, adapter request, response/error branch, assistant projection, termination, recommendation, evidence, quiescence, usage, and metadata. Each mutation must parse under the resource ceiling and then fail the existing provenance verifier.

Test mutually exclusive response/error branches. Both present, both absent for a returned terminal row, contradictory outcome/termination, partial evidence, and an unrecognized branch must fail before a call-shape carrier is issued.

- [x] **Step 5: Prove the capability cannot be forged or reclosed**

Add parameterized refusals for:

- a plain dictionary containing `planner_count`/`evaluator_count`;
- direct exact-class construction;
- `object.__new__` construction;
- subclassing;
- `copy.copy()` and `copy.deepcopy()`;
- a carrier from a changed/reclosed profile;
- mutation of the original parsed ledger after issuance;
- replacement of role/index/branch/terminal projections;
- use with `planner-session.json` or `evaluator.json` from another ledger.

Consumption must rederive the immutable registered snapshot and compare it to the current profile identity. No raw issuer or registry object may appear in module globals or `__all__`.

- [x] **Step 6: Run focused tests and commit**

```powershell
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_lm9b_p_governed_resolution_archive_evidence.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py `
  -q
git diff --check
git add scripts/lm9b_p_governed_resolution_archive_evidence.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_archive_evidence.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py `
  docs/superpowers/plans/2026-07-27-lm9b-p-resolution-archive-evidence-resource-profile.md
git commit -m "test: close resolution evidence resource equations"
```

---

### Task 3: Enforce Future Dispatch and Capture Bounds Without Losing Evidence

**Files:**
- Modify: `scripts/lm9b_p_governed_resolution_archive_evidence.py`
- Modify: `scripts/lm9b_p_planner_recipe_transfer_support.py`
- Modify: `scripts/lm9b_p_governed_resolution_probe.py`
- Modify: `scripts/lm9b_p_governed_resolution_artifacts.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_archive_evidence.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_probe.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py`

**Interfaces:**
- Consumes Task 2 field/member ceiling functions.
- Produces:
  - `validate_resolution_dispatch_request(*, role: str, ordinal: int, canonical_request_bytes: bytes, adapter_request_bytes: bytes, profile: object) -> None`
  - `validate_resolution_captured_turn(*, row: Mapping[str, object], profile: object) -> None`
  - `materialize_resolution_provider_call_request(*, role: str, ordinal: int, raw_bytes: bytes, profile: object) -> dict[str, object]`
  - `ResolutionArchiveEvidenceOverflow(field: str, observed_bytes: int, ceiling_bytes: int, rejection_id: str)`
  - `ReconstructedResolutionAttempt` shared by public checkpoint and forensic verification
  - `reconstruct_resolution_attempt_evidence(*, preflight, call_ledger, candidate_recipe_bytes) -> ReconstructedResolutionAttempt`

- [x] **Step 1: Write pre-dispatch overflow refusals**

Parameterize Planner turn 1, Planner turns 2–6, and evaluator call 1. For the initial Planner request, assert an over-bound canonical or adapter request refuses before reservation/dispatch and leaves the attempt unconsumed. For a later request after one completed dispatch, assert exact prior evidence remains and the attempt becomes `post_dispatch_unsealed` without entering the next adapter.

Every test must use explicit call counters:

```python
assert planner_provider.call_count == expected_completed_calls
assert evaluator_provider.call_count == 0
assert not destination.exists()
assert (staging / ".resolution-runtime").is_dir()
```

- [x] **Step 2: Validate exact request bytes before every dispatch**

In `_StagedCallLedger`, after canonical request construction and fresh materialization but before `dispatch_started`:

```text
canonical request bytes
+ shared LiteLLM adapter request projection bytes
+ role and one-based ordinal
-> validate_resolution_dispatch_request()
```

Only after the check passes may the ledger persist/reread bytes and write `dispatch_started`. Do not change the request builder, timeout derivation, model, profile, temperature, tool schema, or call sequence.

- [x] **Step 3: Write post-dispatch raw-capture overflow tests**

Use fake providers returning exact-bound and bound-plus-one:

- Planner raw response;
- Planner raw error via `ProviderCallFailure`;
- evaluator raw response;
- evaluator raw error;
- assistant projection;
- usage;
- provider metadata.

For bound plus one, prove raw bytes are written and reread in staging before `validate_resolution_captured_turn()` fails. Assert the marker/hash inventory names the captured bytes and no derived sealed archive is issued.

- [x] **Step 4: Make raw capture precede profile admission**

Refactor terminal publication to this order:

```text
adapter returns/raises with evidence
-> join owned execution context
-> serialize exact raw response/error as opaque bytes
-> persist and reread raw bytes plus hashes
-> project assistant/tool/usage/metadata
-> validate individual field bounds
-> publish immutable terminal ledger row
```

An unexpected exception before complete adapter evidence remains unsealed under the existing semantics. A bounds exception after dispatch is never converted to `probe_inconclusive`.

- [x] **Step 5: Extract one shared attempt reconstruction result**

Replace the private seven-value tuple from `_reconstruct_attempt_results()` with:

```python
@dataclass(frozen=True)
class ReconstructedResolutionAttempt:
    planner_session: PLANNER_SUPPORT.PlannerSessionResult
    checkpoint_gate: PLANNER_SUPPORT.MechanicalGateResult | None
    isolation_result: SUPPORT.IsolationGateResult | None
    evaluator_result: PLANNER_SUPPORT.PlannerEvaluationResult | None
    classification: str
    derived_stop_cause: str
    candidate_recipe_bytes: bytes | None
```

Expose `reconstruct_resolution_attempt_evidence()` and make the public checkpoint verifier its only existing consumer. Preserve all current classifications and evidence identities except commit/source-derived instrument/preflight identities that must move.

- [x] **Step 5A: Keep governed request materialization under profile custody**

Add one governed-resolution materializer that selects the request ceiling from
the closure-issued profile by exact role and ordinal, strictly parses under
that ceiling, reruns the existing Planner or evaluator request builder, and
requires canonical byte equality. Route all governed-resolution controller,
adapter-boundary, call-ledger, public-verifier, and attempt-reconstruction
materialization through it. Keep the existing Planner controller's historical
materializer as the default for first-authorship callers; resolution supplies
the profile-aware callback explicitly.

The shared controller must canonically serialize every non-`None` callback
result and require exact equality with its own `PlannerProviderCallPlan`
request bytes before entering the provider. A substituted callback value is an
instrument error with zero provider calls. The historical no-callback path
continues to use the existing 1 MiB materializer and must remain byte-equal to
the controller call plan.

Prove the transition with genuine, builder-produced requests rather than a
patched admission decision:

- a turn-2 Planner request above 1 MiB crosses the real bounded controller,
  staged adapter boundary, sealing, public verification, and attempt
  reconstruction;
- an evaluator request above 1 MiB crosses the conditional evaluator call,
  sealing, public verification, and attempt reconstruction;
- both remain inside their profile-derived ceilings, while the existing
  pre-dispatch and post-dispatch overflow outcomes remain unchanged.

- [x] **Step 6: Test future instrument/preflight drift closure**

Fully reclose each mutation and require `verify_resolution_preflight()` refusal:

- profile raw SHA or fingerprint;
- member map/role/formula/constants;
- helper/formula source fingerprint;
- serializer/escaping/base64 identity;
- evaluator member/report/parser/limit fingerprint;
- writer/public verifier source fingerprint;
- reviewed implementation commit.

Also assert the current feature instrument and development preflight identities differ from the historical `e81b12cc` identities; this is intentional and must not alter the historical preflight bytes.

- [x] **Step 7: Run focused tests and commit**

```powershell
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_archive_evidence.py `
  -q
git diff --check
git add scripts/lm9b_p_governed_resolution_archive_evidence.py `
  scripts/lm9b_p_planner_recipe_transfer_support.py `
  scripts/lm9b_p_governed_resolution_probe.py `
  scripts/lm9b_p_governed_resolution_artifacts.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_archive_evidence.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py `
  docs/superpowers/plans/2026-07-27-lm9b-p-resolution-archive-evidence-resource-profile.md
git commit -m "fix: retain bounded resolution provider evidence"
```

---

### Task 4: Verify the Consumed Historical Preflight and Load Immutable Forensic Source

**Files:**
- Create: `scripts/lm9b_p_governed_resolution_forensics.py`
- Create: `mcp_server/tests/test_lm9b_p_governed_resolution_forensics.py`
- Modify: `scripts/lm9b_p_governed_resolution_artifacts.py`

**Interfaces:**
- Consumes:
  - pinned `e81b12cc` Git tree and physical preflight
  - Task 3 `reconstruct_resolution_attempt_evidence()`
  - Task 2 profile parser/call-shape interfaces
- Produces:
  - closure-issued `VerifiedHistoricalResolutionPreflightForensics`
  - closure-issued `VerifiedResolutionForensicSource`
  - closure-issued `VerifiedRuntimeCallProjection`
  - immutable `ResolutionForensicReconstruction`
  - `verify_historical_resolution_preflight_forensics(*, repo_root: Path, preflight_archive: Path, expected_preflight_fingerprint: str) -> VerifiedHistoricalResolutionPreflightForensics`
  - `load_verified_resolution_forensic_source(*, historical_preflight: object, staging_dir: Path, expected_marker_sha256: str, expected_candidate_checksums_sha256: str) -> VerifiedResolutionForensicSource`
  - `reconstruct_resolution_forensic_candidate(*, source: object, repo_root: Path, forensic_commit_sha: str) -> ResolutionForensicReconstruction`

- [x] **Step 1: Add import-valid forensic types with no operational imports**

The new module may import pure support/artifact reconstruction and profile helpers. It must not import `lm9b_p_governed_resolution_probe`, provider construction, checkpoint sealing, ready-proof issuance/consumption, or compiler continuation.

Define:

```python
@dataclass(frozen=True)
class ResolutionForensicReconstruction:
    observed_commit_sha: str
    forensic_commit_sha: str
    planner_call_count: int
    evaluator_call_count: int
    mechanical_status: str
    isolation_status: str
    reconstructed_classification: str
    candidate_recipe_raw_sha256: str
    runtime_call_projection_fingerprint: str
    authored_operational_accounting_fingerprint: str
    controller_conformance: str
    exact_timing_accounting: str
    cost_accounting: str
    cost_stop_compliance: str
    classification_scope: str
    original_attempt_state: str
    official_scientific_checkpoint: str
    ready_proof: str
    compiler_eligibility: bool
    gate_fingerprint: str
    isolation_fingerprint: str
    reconstruction_fingerprint: str

@dataclass(frozen=True)
class ForensicSourceSnapshot:
    staging_path: Path
    destination_path: Path
    preflight_members: Mapping[str, bytes]
    marker_bytes: bytes
    candidate_members: Mapping[str, bytes]
    before_identity: tuple[object, ...]
```

The two verified types must use closure-owned weak registries and immutable external snapshots exactly like the call-shape capability. Forensic execution/sealing/ready/compiler APIs must reject both by exact type.

- [x] **Step 2: Write a historical-preflight substitution table**

Use the pinned physical historical preflight at its canonical path, read-only,
for the positive witness. Capture a non-following before/after physical
snapshot and require exact equality. The historical preflight binds its own
canonical location, so an unchanged copy under `tmp_path` is a required
location-refusal case and is never a positive baseline.

Exercise deeper provenance substitutions through the private pure
reconstruction boundary. The physical loader first verifies and freezes the
actual preflight bytes and the closed Git-blob map. Tests may then pass a
controlled in-memory replacement blob/projection to that pure function and
fully reclose one mutation at a time without writing the pinned source:

- reviewed commit;
- instrument/preflight/attempt fingerprints;
- initial request bytes/hash;
- canonical preflight/destination/staging paths;
- member checksums;
- any source fingerprint;
- raw execution/provider module hash;
- policy/rubric/tool/report/ready-proof/readiness identity;
- missing/extra/reparse member.

Every mutation must fail even after every authored downstream
fingerprint/checksum is recomputed. The public physical verifier accepts no
caller-supplied blob reader or mutation hook; only the private pure
reconstruction helper receives the immutable byte map produced by the real
loader. Copying, relocating, or editing the official preflight is never part of
this test path.

- [x] **Step 3: Implement the separate historical compatibility verifier**

Hard-pin:

```python
OBSERVED_COMMIT_SHA = "e81b12cca0eb750a7f3e730d2376085a915d43dd"
OBSERVED_PREFLIGHT_FINGERPRINT = (
    "sha256:897337de3d20e126a143576de707ec3b1377033eab49465ac38d793afd97a856"
)
OBSERVED_INSTRUMENT_FINGERPRINT = (
    "sha256:0b57f30954c375df34b28ba394f2ef281c09388c209e688586187d8759f26d11"
)
OBSERVED_ATTEMPT_FINGERPRINT = (
    "sha256:bd350d895f0e34a67aa7ebe59e1e8c4b3b5b3f4e715aa6d81d5874561af10e42"
)
```

`verify_historical_resolution_preflight_forensics()` is a separate function, never a flag on `verify_resolution_preflight()`. It must:

1. non-followingly read the exact three physical preflight members;
2. require public path equality and the independently supplied fingerprint;
3. verify the record fingerprint and two-member checksum ledger;
4. read required bytes with `git show e81b12cc:<path>`, never import historical code;
5. derive a closed Git-object manifest of path, Git blob ID, byte length, and SHA-256;
6. reconstruct every source/raw-file/policy/schema/request/decision identity in the historical instrument;
7. recompute the initial request, instrument, attempt, preflight record, and preflight fingerprint;
8. issue a registered carrier only after exact equality.

The closed source-fingerprint binding table must cover these callables:

```text
lm9b_p_governed_resolution_artifacts:
  verify_sealed_resolution_checkpoint
  seal_resolution_checkpoint
  verify_resolution_call_ledger
  build_resolution_invocation_binding
  verify_resolution_invocation_binding
  verify_resolution_preflight
  reserve_resolution_staging
  write_resolution_preflight
  issue_resolution_ready_proof
  consume_resolution_ready_proof
  _load_verified_resolution_sources_unsealed
  _verify_historical_carrier_qualification_compatibility_unsealed

lm9b_p_governed_resolution_support:
  render_planner_revision_request
  render_planner_revision_evaluation_request
  evaluate_resolution_isolation
  assemble_verified_resolution_inputs

lm9b_p_planner_recipe_transfer_support:
  run_planner_session
  build_planner_provider_call_request
  build_planner_provider_call_plan
  build_planner_mechanical_feedback_message
  evaluate_mechanical_gate
  derive_planner_evaluation_result
  build_planner_evaluator_provider_call_request

lm9b_p_planner_recipe_transfer_artifacts:
  derive_probe_explicit_blockers
  derive_evaluated_recipe_classification

lm9b_p_readiness_contract:
  verify_launch_readiness

lm9b_c_compiler_sufficiency_probe:
  build_litellm_completion_request_bytes
  LiteLLMProvider.__call__
```

Also verify the governed-resolution probe raw blob, provider module raw blob, isolation/rubric/fixture bytes, typed-fact registry/payload schema, carrier qualification bindings, and every non-source fingerprint in `instrument_contracts`. Use AST line spans over Git blobs to reproduce `inspect.getsource()` bytes; do not execute those blobs.

- [x] **Step 4: Test physical source custody before reconstruction**

Create a temp forensic source tree shaped like the retained staging. Add mutations for:

- wrong marker bytes/hash or failure locus;
- wrong candidate checksum member/hash;
- unexpected file/directory;
- reparse component;
- destination present;
- staging or candidate movement between snapshots;
- wrong attempt/path binding;
- missing runtime/candidate/marker evidence.

The loader must capture exact bytes and non-following `(path, type, size, device/file identity, SHA-256)` rows before issuing `VerifiedResolutionForensicSource`. It must not trust the candidate's `record.json`, `classification.json`, or `checksums.json` as outcome authority.

- [x] **Step 5: Reconstruct a copied six-turn candidate from root evidence**

Use a temp copy of the retained candidate plus the carrier issued from the
actual pinned physical preflight. A copied preflight is a location-refusal
case and can never issue that carrier. The reconstruction order is:

```text
consume historical preflight carrier
-> consume immutable source carrier
-> admit repaired profile under forensic commit
-> derive each causal call row from retained runtime dispatch markers,
   canonical requests, adapter requests, and raw responses
-> compare those derived rows to the authored call ledger while excluding
   only calls[*].elapsed_ms and calls[*].usage.cost_usd
-> preserve the excluded authored timing/cost values as unverified accounting
-> issue a closure-owned VerifiedRuntimeCallProjection
-> parse/authenticate the six-row authored call ledger and issue call-shape carrier
-> parse remaining members under actual P=6, E=0 ceilings
-> derive assistant/tool projections from raw responses
-> rebuild all Planner requests, submissions, mechanical gates, and feedback
-> prove turn 6 mechanically accepted
-> independently rerun isolation
-> derive probe_resolution_isolation_failure
-> compare authored gate/isolation/classification only after derivation
```

Assert:

```python
assert reconstruction.planner_call_count == 6
assert reconstruction.evaluator_call_count == 0
assert reconstruction.mechanical_status == "accepted"
assert reconstruction.isolation_status == "isolation_rejected"
assert reconstruction.reconstructed_classification == (
    "probe_resolution_isolation_failure"
)
assert reconstruction.controller_conformance == "not_verified"
assert reconstruction.exact_timing_accounting == "not_verified"
assert reconstruction.cost_accounting == "preserved_unverified"
assert reconstruction.cost_stop_compliance == "not_verified"
assert reconstruction.classification_scope == (
    "candidate_level_deterministic_projection"
)
assert reconstruction.original_attempt_state == "post_dispatch_unsealed"
assert reconstruction.official_scientific_checkpoint == "absent"
assert reconstruction.ready_proof == "prohibited"
assert reconstruction.compiler_eligibility is False
```

The authored aggregate is a comparison target, never the causal source. The
forensic reconstruction does not call the existing full-ledger verifier with
invented timing or cost. Six physical dispatches, exact requests/responses,
submission/feedback progression, the accepted turn-six candidate, and its
isolation failure are verified. Full controller conformance, exact elapsed
time, cost accounting, and cost-stop compliance are explicitly not verified.

Future governed-resolution attempts must persist terminal per-call evidence
that binds elapsed time and either exact cost plus calculator/pricing identity,
or immutable inputs sufficient to recompute the cost decision. This forward
requirement does not manufacture missing evidence for the retained attempt.

- [x] **Step 6: Prove read-only snapshot equality and type isolation**

For temp evidence, capture a recursive non-following before snapshot, reconstruct, capture after, and require exact equality. Patch checkpoint sealing, ready-proof issuance, retry, provider construction, and compiler entry points to raise; reconstruction must never touch them.

Pass both forensic carrier types to:

- `reserve_resolution_staging()`;
- `seal_resolution_checkpoint()`;
- `issue_resolution_ready_proof()`;
- `consume_resolution_ready_proof()`.

Each must reject by exact type before filesystem or provider behavior.

- [x] **Step 7: Run focused tests and commit**

```powershell
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_lm9b_p_governed_resolution_forensics.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_archive_evidence.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py `
  -q
git diff --check
git add scripts/lm9b_p_governed_resolution_forensics.py `
  scripts/lm9b_p_governed_resolution_artifacts.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_forensics.py `
  docs/superpowers/plans/2026-07-27-lm9b-p-resolution-archive-evidence-resource-profile.md
git commit -m "feat: verify retained resolution evidence provenance"
```

---

### Task 5: Publish and Publicly Verify a Separate Forensic Derivative

**Files:**
- Modify: `scripts/lm9b_p_governed_resolution_forensics.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_forensics.py`

**Interfaces:**
- Consumes Task 4 source/reconstruction carriers.
- Produces:
  - exact-type `VerifiedResolutionForensicReport`
  - control-only `ForensicReportPublicationResult`
  - `write_resolution_forensic_report(*, destination: Path, source: object, reconstruction: ResolutionForensicReconstruction, repo_root: Path, forensic_commit_sha: str) -> ForensicReportPublicationResult`
  - `verify_resolution_forensic_report(archive_dir: Path, *, expected_identity: str, expected_historical_preflight_fingerprint: str) -> VerifiedResolutionForensicReport`
  - `reconcile_resolution_forensic_publication(*, candidate_dir: Path, destination: Path, expected_identity: str, expected_historical_preflight_fingerprint: str) -> ForensicReportPublicationResult`

Use this exact official report carrier:

```python
@dataclass(frozen=True, eq=False)
class VerifiedResolutionForensicReport:
    archive_dir: Path
    report_identity: str
    original_attempt_state: str
    reconstructed_classification: str
    observed_instrument_fingerprint: str
    forensic_instrument_fingerprint: str
    _snapshot_members: Mapping[str, bytes]
```

It is closure-issued only after public path-bound reconstruction. It has no checkpoint, recipe, ready-proof, retry, or compiler field.

- [x] **Step 1: Write a failing synthetic report vertical**

Build a temp verified historical preflight, six-turn forensic source, and reconstruction through public Task 4 APIs. Choose a fresh direct-child destination under a temp forensic root. Require:

```python
published = FORENSICS.write_resolution_forensic_report(
    destination=destination,
    source=source,
    reconstruction=reconstruction,
    repo_root=REPO_ROOT,
    forensic_commit_sha=_head(),
)
assert published.state == "published"
assert published.report is not None
verified = FORENSICS.verify_resolution_forensic_report(
    destination,
    expected_identity=published.report.report_identity,
    expected_historical_preflight_fingerprint=(
        FORENSICS.OBSERVED_PREFLIGHT_FINGERPRINT
    ),
)
assert verified.reconstructed_classification == (
    "probe_resolution_isolation_failure"
)
```

Expected red: report writer/verifier not implemented, not a source-verification failure.

- [x] **Step 2: Implement the seven-member non-circular report graph**

Write exactly these substantive records:

```text
observed-instrument.json
forensic-instrument.json
source-snapshot.json
reconstruction.json
boundary.json
```

Their schemas are respectively:

```text
rook.lm9b_p.governed_resolution_forensic_observed_instrument:v1
rook.lm9b_p.governed_resolution_forensic_instrument:v1
rook.lm9b_p.governed_resolution_forensic_source_snapshot:v1
rook.lm9b_p.governed_resolution_forensic_reconstruction:v1
rook.lm9b_p.governed_resolution_forensic_boundary:v1
```

Derive in this exact order:

```python
substantive_paths = (
    "boundary.json",
    "forensic-instrument.json",
    "observed-instrument.json",
    "reconstruction.json",
    "source-snapshot.json",
)
content_fingerprint = fingerprint(
    [
        {"path": path, "raw_sha256": sha256(members[path])}
        for path in substantive_paths
    ]
)
record = {
    "schema": "rook.lm9b_p.governed_resolution_forensic_report:v1",
    "canonical_destination": str(destination),
    "forensic_merge_sha": forensic_commit_sha,
    "content_fingerprint": content_fingerprint,
    "report_identity": fingerprint(
        {
            "content_fingerprint": content_fingerprint,
            "canonical_destination": str(destination),
            "forensic_merge_sha": forensic_commit_sha,
        }
    ),
}
checksum_paths = tuple(sorted((*substantive_paths, "record.json")))
checksums = {
    "schema": "rook.lm9b_p.governed_resolution_forensic_checksums:v1",
    "members": checksum_rows(checksum_paths, members),
}
```

`checksums.json` is never included in `content_fingerprint`, `record.json`, or its own member list.

- [x] **Step 3: Close observed and forensic instrument records**

`observed-instrument.json` must bind:

- `e81b12cc`;
- physical preflight path/fingerprint and exact member hashes;
- historical instrument and attempt fingerprints;
- staging and reserved destination;
- marker bytes/hash;
- all candidate member sizes/hashes and original checksum closure.

`forensic-instrument.json` must bind:

- current reviewed repair commit;
- exact profile raw SHA/fingerprint/member map/formulas/constants;
- helper source fingerprint;
- historical compatibility verifier source and Git-object manifest fingerprint;
- reconstruction/classifier/isolation source fingerprints;
- physical snapshot contract;
- five-member content, record, six-member checksum, writer, public verifier, and publication equations.

It must not state that the observed instrument contained the repaired profile.

- [x] **Step 4: Close boundary and reconstruction non-claims**

Require exact `boundary.json` values:

```json
{
  "schema": "rook.lm9b_p.governed_resolution_forensic_boundary:v1",
  "original_attempt_state": "post_dispatch_unsealed",
  "official_scientific_checkpoint": "absent",
  "reconstructed_candidate_classification": "probe_resolution_isolation_failure",
  "ready_proof": "prohibited",
  "compiler_eligibility": false,
  "provider_contact_by_forensic_instrument": false,
  "retry_authorized": false,
  "policy_recommendation_present": false
}
```

`reconstruction.json` contains derived call/gate/isolation/classification facts and exact fingerprints, not raw chain-of-thought, recommendations, or a retry identity.

- [x] **Step 5: Implement no-clobber atomic publication**

Require an absolute canonical direct-child destination beneath a supplied forensic root, no reparse ambiguity, same filesystem, absent destination, and absent sibling candidate. Publication is:

```text
atomically mkdir sibling .<report-name>.candidate with exist_ok=False
-> write seven members no-clobber
-> reread and privately verify candidate from immutable source snapshot
-> Path.rename(candidate, destination)
-> public verification
-> reconcile every ordinary exception
```

`ForensicReportPublicationResult` has:

```python
@dataclass(frozen=True)
class ForensicReportPublicationResult:
    state: Literal["published", "unpublished", "publication_indeterminate"]
    report: VerifiedResolutionForensicReport | None
    candidate_path: Path
    destination_path: Path
    failure_locus: str | None
```

Only `destination verifies AND candidate absent` yields `published` and a report carrier. Destination absent with retained candidate yields `unpublished`. Mixed, missing, reparse, or unverifiable states yield `publication_indeterminate`. Reconciliation never mutates a destination after rename begins.

- [x] **Step 6: Write report identity and reconciliation mutation tables**

Fully reclose:

- each substantive member;
- content fingerprint;
- record destination/merge SHA/identity;
- missing, extra, reordered, self-including, or circular checksum rows;
- copied archive at another path;
- changed source after report publication;
- report carrier forgery/copy/replacement;
- destination race;
- reported rename exception after successful publication;
- transient public verification error;
- destination plus candidate;
- destination absent plus candidate;
- candidate/destination loss;
- every ordinary verification exception.

Prove a later physically verified destination can issue a report carrier after a reported exception, while unresolved ambiguity issues none. No failure handler writes into the published destination.

- [x] **Step 7: Prove report types cannot cross checkpoint/ready/compiler boundaries**

Pass `VerifiedResolutionForensicReport`, `ForensicReportPublicationResult`, and `ResolutionForensicReconstruction` to checkpoint sealing, ready-proof issuance/consumption, retry/reservation, and compiler continuation. Patch downstream entry points to count calls. Require exact-type refusal and zero calls.

- [x] **Step 8: Run focused tests and commit**

```powershell
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_lm9b_p_governed_resolution_forensics.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_archive_evidence.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py `
  -q
git diff --check
git add scripts/lm9b_p_governed_resolution_forensics.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_forensics.py `
  docs/superpowers/plans/2026-07-27-lm9b-p-resolution-archive-evidence-resource-profile.md
git commit -m "feat: add resolution forensic derivative report"
```

---

### Task 6: Close CLI Boundaries, Exact Retained-Specimen Witness, and PR Verification

**Files:**
- Modify: `scripts/lm9b_p_governed_resolution_forensics.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_forensics.py`
- Modify: `mcp_server/tests/test_lm9b_p_governed_resolution_probe.py`
- Modify: `docs/superpowers/plans/2026-07-27-lm9b-p-resolution-archive-evidence-resource-profile.md`

**Interfaces:**
- Consumes all prior tasks.
- Produces:
  - `verify-candidate` read-only CLI command
  - `publish-report` post-merge-only CLI command
  - `verify-report` public read-only CLI command

- [ ] **Step 1: Add a closed no-contact forensic CLI**

Use subcommands with these exact arguments:

```text
verify-candidate
  --repo-root
  --preflight-archive
  --expected-preflight-fingerprint
  --staging-dir
  --expected-marker-sha256
  --expected-candidate-checksums-sha256
  --forensic-commit-sha

publish-report
  all verify-candidate arguments
  --destination

verify-report
  --archive-dir
  --expected-identity
  --expected-preflight-fingerprint
```

There is no profile path, numeric limit, model, provider, readiness, retry, checkpoint destination, ready-proof, or compiler argument. `verify-candidate` prints one canonical JSON summary and writes nothing. `publish-report` requires `HEAD == forensic_commit_sha`, a clean checkout, exact source snapshot, absent destination/candidate, and independently reconstructed `probe_resolution_isolation_failure` before writing. `verify-report` reopens both report and pinned source evidence.

- [ ] **Step 2: Write CLI structural and zero-contact tests**

Assert parser vocabulary is exact. Patch provider/readiness/controller/evaluator/compiler functions to raise if imported or called. Exercise all three commands with temp evidence and prove zero calls.

For `verify-candidate`, snapshot all source paths before and after and require equality. For `publish-report`, prove the only writes are beneath the fresh forensic report candidate/destination. For `verify-report`, prove read-only behavior.

- [ ] **Step 3: Run focused CLI tests before committing**

```powershell
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_lm9b_p_governed_resolution_forensics.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py `
  -k "cli or zero_contact or source_snapshot" `
  -q
```

Expected: PASS with no external source changes.

- [ ] **Step 4: Commit the identity-bearing implementation before qualification**

```powershell
git add .gitattributes `
  scripts/lm9b_p_governed_resolution_contracts/archive_evidence_resource_profile.json `
  scripts/lm9b_p_governed_resolution_archive_evidence.py `
  scripts/lm9b_p_governed_resolution_forensics.py `
  scripts/lm9b_p_governed_resolution_artifacts.py `
  scripts/lm9b_p_governed_resolution_probe.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_archive_evidence.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_forensics.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py `
  docs/superpowers/plans/2026-07-27-lm9b-p-resolution-archive-evidence-resource-profile.md
git commit -m "feat: complete resolution archive evidence repair"
```

Require a clean worktree. Every following feature-HEAD witness uses this exact committed identity; it must never qualify uncommitted source bytes.

- [ ] **Step 5: Prove LF and cross-checkout identity stability**

From a fresh detached checkout of the same feature SHA with `core.autocrlf=true`, assert:

- profile raw SHA and profile fingerprint match;
- helper and forensics raw/source fingerprints match;
- `RESOLUTION_ARCHIVE_MEMBERS` equals the profile snapshot;
- a fake future preflight built in each checkout has identical instrument/preflight identity for an identical canonical destination;
- the read-only retained-candidate reconstruction fingerprint matches.

The test must resolve repository-relative source identities; no feature-worktree absolute path may enter profile or forensic instrument identity.

- [ ] **Step 6: Run the exact retained staging through feature-HEAD read-only verification**

First capture a non-following snapshot of:

```text
C:/Users/bring/rook-lm9b-p-attempts/2026-07-27-governed-resolution-operational/governed-resolution-e81b12cca0eb-replacement-01-preflight
C:/Users/bring/rook-lm9b-p-attempts/2026-07-27-governed-resolution-operational/.governed-resolution-e81b12cca0eb-replacement-01.staging
C:/Users/bring/rook-lm9b-p-attempts/2026-07-27-governed-resolution-operational/governed-resolution-e81b12cca0eb-replacement-01 (required absent)
```

Then run only:

```powershell
$headSha = git rev-parse HEAD
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe `
  scripts/lm9b_p_governed_resolution_forensics.py verify-candidate `
  --repo-root C:/UDEV/Rook/.worktrees/lm9b-p-resolution-archive-evidence-profile-design `
  --preflight-archive C:/Users/bring/rook-lm9b-p-attempts/2026-07-27-governed-resolution-operational/governed-resolution-e81b12cca0eb-replacement-01-preflight `
  --expected-preflight-fingerprint sha256:897337de3d20e126a143576de707ec3b1377033eab49465ac38d793afd97a856 `
  --staging-dir C:/Users/bring/rook-lm9b-p-attempts/2026-07-27-governed-resolution-operational/.governed-resolution-e81b12cca0eb-replacement-01.staging `
  --expected-marker-sha256 sha256:c307db9cf7220df203086c2ce348cdad4bf2def1029653d2125ba6341632a501 `
  --expected-candidate-checksums-sha256 sha256:ee01977cce93887f48cc6a2f13cc33a8e24d00a38ab002f59519c67b03a97999 `
  --forensic-commit-sha $headSha
```

Require canonical output containing:

```json
{
  "original_attempt_state": "post_dispatch_unsealed",
  "official_scientific_checkpoint": "absent",
  "planner_call_count": 6,
  "evaluator_call_count": 0,
  "mechanical_status": "accepted",
  "isolation_status": "isolation_rejected",
  "reconstructed_candidate_classification": "probe_resolution_isolation_failure",
  "ready_proof": "prohibited",
  "compiler_eligibility": false,
  "report_published": false
}
```

Capture the same physical snapshot after the command and require byte/type/path identity equality. Do not pass a report destination and do not publish, rename, copy, or promote anything.

- [ ] **Step 7: Run the complete deterministic regression**

```powershell
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_lm9b_p_governed_resolution_archive_evidence.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_forensics.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_artifacts.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_support.py `
  mcp_server/tests/test_lm9b_p_governed_resolution_probe.py `
  -q

& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest `
  mcp_server/tests/test_lm9b_p_planner_recipe_transfer_support.py `
  mcp_server/tests/test_lm9b_p_planner_recipe_transfer_artifacts.py `
  mcp_server/tests/test_lm9b_p_planner_recipe_transfer_probe.py `
  mcp_server/tests/test_lm9b_p_evaluator_authority_boundary.py `
  mcp_server/tests/test_lm9_typed_fact_carrier.py `
  -q

& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m py_compile `
  scripts/lm9b_p_governed_resolution_archive_evidence.py `
  scripts/lm9b_p_governed_resolution_forensics.py `
  scripts/lm9b_p_governed_resolution_artifacts.py `
  scripts/lm9b_p_governed_resolution_probe.py

git diff --check
git status --short
```

Expected: all tests and compilation pass; only reviewed branch files are changed; the operational worktree and retained evidence remain unchanged.

- [ ] **Step 8: Reconcile the plan ledger and commit the verification ledger**

Mark only commands actually completed. Then:

```powershell
git add docs/superpowers/plans/2026-07-27-lm9b-p-resolution-archive-evidence-resource-profile.md
git commit -m "docs: record resolution evidence verification"
```

Request independent PR review. Do not publish the forensic report from feature HEAD and do not contact a provider.

---

### Task 7: Post-Merge No-Contact Forensic Report Publication

**Execution gate:** This task runs only after the implementation PR is independently approved and merged. It never runs on feature HEAD and authorizes no readiness or model/provider/compiler contact.

**Files:**
- No repository edits.
- Creates one new external forensic report directory only.

- [ ] **Step 1: Create a clean detached merge-SHA checkout**

```powershell
git fetch origin
$repairMergeSha = gh pr view --json mergeCommit --jq '.mergeCommit.oid'
if (-not $repairMergeSha) {
    throw "merged PR did not provide a merge commit identity"
}
$reviewRoot = "C:/UDEV/Rook/.worktrees/lm9b-p-resolution-archive-evidence-post-merge-$($repairMergeSha.Substring(0,12))"
git worktree add --detach $reviewRoot $repairMergeSha
git -C $reviewRoot status --short
```

Require empty status and independently verify that the merge parents match the reviewed base/head.

- [ ] **Step 2: Re-run read-only reconstruction before publication**

Run `verify-candidate` from the merge-SHA checkout with the exact historical bindings from Task 6 and `--forensic-commit-sha $repairMergeSha`. Require the same six-call/mechanical/isolation/classification output and exact source before/after equality.

- [ ] **Step 3: Choose and verify a fresh no-clobber report destination**

```powershell
$reportRoot = 'C:/Users/bring/rook-lm9b-p-attempts/2026-07-27-governed-resolution-forensics'
if (-not (Test-Path -LiteralPath $reportRoot)) {
    New-Item -ItemType Directory -Path $reportRoot | Out-Null
}
$reportDestination = Join-Path $reportRoot (
    "governed-resolution-e81b12cc-replacement-01-forensic-" +
    $repairMergeSha.Substring(0,12)
)
if ([IO.File]::Exists($reportDestination) -or [IO.Directory]::Exists($reportDestination)) {
    throw "forensic report destination already exists"
}
```

Require direct-child canonical path, no reparse ambiguity, same filesystem as the sibling candidate, and no existing dangling entry.

- [ ] **Step 4: Publish exactly one forensic report**

```powershell
$publishResult = & C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe `
  "$reviewRoot/scripts/lm9b_p_governed_resolution_forensics.py" publish-report `
  --repo-root $reviewRoot `
  --preflight-archive C:/Users/bring/rook-lm9b-p-attempts/2026-07-27-governed-resolution-operational/governed-resolution-e81b12cca0eb-replacement-01-preflight `
  --expected-preflight-fingerprint sha256:897337de3d20e126a143576de707ec3b1377033eab49465ac38d793afd97a856 `
  --staging-dir C:/Users/bring/rook-lm9b-p-attempts/2026-07-27-governed-resolution-operational/.governed-resolution-e81b12cca0eb-replacement-01.staging `
  --expected-marker-sha256 sha256:c307db9cf7220df203086c2ce348cdad4bf2def1029653d2125ba6341632a501 `
  --expected-candidate-checksums-sha256 sha256:ee01977cce93887f48cc6a2f13cc33a8e24d00a38ab002f59519c67b03a97999 `
  --forensic-commit-sha $repairMergeSha `
  --destination $reportDestination | ConvertFrom-Json
if ($publishResult.state -ne 'published') {
    throw "forensic publication did not complete: $($publishResult.state)"
}
$reportIdentity = $publishResult.report_identity
```

Stop on `unpublished` or `publication_indeterminate`; preserve all material and do not retry automatically.

- [ ] **Step 5: Publicly verify and independently review the report**

Use the exact printed report identity:

```powershell
& C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe `
  "$reviewRoot/scripts/lm9b_p_governed_resolution_forensics.py" verify-report `
  --archive-dir $reportDestination `
  --expected-identity $reportIdentity `
  --expected-preflight-fingerprint sha256:897337de3d20e126a143576de707ec3b1377033eab49465ac38d793afd97a856
```

Independent review must confirm the seven-member closure, five-member content fingerprint, six-member checksum ledger, merge-SHA binding, original `post_dispatch_unsealed` state, reconstructed `probe_resolution_isolation_failure`, absent official checkpoint/ready proof/compiler eligibility, and unchanged source snapshots.

## Completion Boundary

Stop after the post-merge forensic report is independently verified. Do not run another Planner/evaluator attempt, alter the resolution prompt/gate/isolation contract, promote the original checkpoint, or enter LM9B-C as part of this plan.
