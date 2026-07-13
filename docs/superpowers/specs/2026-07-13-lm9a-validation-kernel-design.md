# LM9A Validation Kernel Design

Status: design draft for review

Date: 2026-07-13

## 1. Purpose

LM9A validation is split into two implementation slices:

```text
LM9A-Kernel
  bounded byte ingress
  owned immutable JSON values
  one validation-budget ledger
  typed phase engine
  immutable phase results
  deterministic report construction

LM9A-Semantics
  Planner graph recipe schemas
  companion authority rules
  provenance and clauses
  assumptions and unresolved intent
  shape, capabilities, and worker slots
  scenario fixtures
```

The kernel is generic. It knows nothing about radial fields, boxes, layers,
Planner assumptions, Grasshopper, or recipe-specific authority. LM9A semantics
register schemas, phases, issue codes, and report projections through the
kernel's closed extension surface.

The controlled kernel claim is:

> Two bounded raw JSON artifacts can be parsed into owned transitively
> immutable values, evaluated by one declarative phase graph under one fixed
> budget, and reduced to a deterministic report without retaining mutable
> caller state or duplicating phase authority.

## 2. Trust Boundary

The public validation arguments are exactly:

```text
raw_recipe_bytes: bytes
raw_validation_bundle_bytes: bytes
```

The public caller cannot pass a `Mapping`, mutable object graph, custom
container, parsed JSON value, phase index, or caller-selected budget. The
entrypoint binds `rook.validation_budget:lm9a_v1` into the invocation context.
Both byte strings are hashed before parsing and copied into invocation-owned
storage.

After exact per-artifact byte caps are checked, parsing order is fixed:

```text
1. validation bundle
2. recipe
```

The bundle is first because it is the authority needed to decide whether a
semantic report can exist. Both parses charge the same aggregate ledger; the
order is part of the kernel ruleset fingerprint.

The kernel performs:

```text
exact bytes
-> bounded tokenizer
-> bounded iterative parser
-> owned immutable JSON value or bounded parse failure
-> validation-bundle constructability preflight
-> typed phase engine
-> deterministic report builder
```

Custom mappings, aliases, concurrent caller mutation, enumeration instability,
and repeated thawing do not exist at this boundary. JSON object member order is
semantically irrelevant. Two objects with the same members in different source
orders have different raw-byte hashes but the same canonical value fingerprint.

## 3. Fixed Validation Budget

`rook.validation_budget:lm9a_v1` has these exact inclusive limits:

| Dimension | Limit |
|---|---:|
| recipe input bytes | 1,048,576 |
| validation-bundle input bytes | 4,194,304 |
| JSON container depth per artifact | 64 |
| JSON number-token characters | 1,024 |
| aggregate parsed nodes across both artifacts | 100,000 |
| members in one object | 16,384 |
| items in one array | 16,384 |
| aggregate decoded UTF-8 string bytes across keys and values | 2,097,152 |
| registered semantic references | 25,000 |
| diagnostics | 1,024 |
| compile blockers | 1,024 |
| aggregate phase work units | 1,000,000 |

Limits are enforced while tokenizing, parsing, registering references, and
adding phase results. The parser must charge a node, member/item, decoded-string
bytes, and work before allocating or appending that value. It may not call
`json.loads` and reject only after a complete unbounded host graph exists.

Accounting is normative:

- a parsed node is each JSON value, including each object and array; object keys
  are not nodes;
- object width is the number of distinct members before canonical sorting;
- array width is the number of items;
- decoded-string bytes are the UTF-8 byte length of every decoded object key and
  string value before schema-directed normalization, counted at every
  occurrence;
- a semantic reference is charged when a semantic extension registers one
  discriminated reference entry for resolution;
- each diagnostic or blocker is charged before insertion, including one later
  rejected as duplicate or unauthorized;
- lexical work charges one unit per JSON token;
- parse work charges one unit per node and one unit per member/item attachment;
- schema work charges one unit per schema keyword evaluation against one value;
- graph work charges one unit per node or edge examined;
- identity work charges one unit per ID insertion or lookup;
- sorting `n` set-like items reserves
  `n * ceil(log2(max(n, 2)))` work units before sorting;
- canonical serialization and hashing reserve one work unit per started 64-byte
  output block;
- report work charges one unit per phase row, descriptor, issue, blocker, and
  fingerprint-projection field emitted.

The extension API exposes only these charge operations. A semantic runner may
not define a cheaper private unit. Reserved work is consumed even when the
operation later finds an error.

A completed report records one closed budget receipt:

```yaml
budget_profile: rook.validation_budget:lm9a_v1
limits_fingerprint: sha256:...
observed:
  recipe_input_bytes: 0
  validation_bundle_input_bytes: 0
  maximum_container_depth: 0
  maximum_number_token_chars: 0
  parsed_nodes: 0
  maximum_object_members: 0
  maximum_array_items: 0
  decoded_string_bytes: 0
  semantic_references: 0
  diagnostics: 0
  compile_blockers: 0
  phase_work_units: 0
```

`limits_fingerprint` binds the exact table and accounting rules in this section.
The observed fields are mechanically maintained by the ledger and are part of
the report fingerprint. Phase code cannot author them.

The ledger is monotonic and invocation-owned. A phase cannot refund work or
obtain a private budget. Derived indexes, schema traversal, reference
resolution, sorting, canonicalization, diagnostics, and report construction all
charge the same ledger under documented unit rules.

Budget exhaustion uses one stable external code:

```yaml
kind: invocation_failure
failure_stage: preflight | validation
code: validation_budget_exceeded
artifact_role: recipe | validation_bundle | combined | phase_engine
budget_dimension: input_bytes | container_depth | number_token_chars |
                  parsed_nodes | object_members | array_items |
                  decoded_string_bytes | semantic_references |
                  diagnostics | compile_blockers | phase_work_units
limit: 100000
observed_lower_bound: 100001
subject_path: /bounded/path | null
message: bounded text
```

`observed_lower_bound` is the first value known to exceed the limit; validation
does not continue merely to compute a larger exact total. The earliest honest
result depends on the exhausted role. Recipe-only parse exhaustion becomes
`schema / validation_budget_exceeded` in a conforming report when the validation
bundle is constructable. Validation-bundle exhaustion is a preflight invocation
failure because descriptor evidence cannot be built. Phase-engine or
report-construction exhaustion is a validation invocation failure because the
full semantic result is unknown. No path publishes a partial report.

Every inclusive boundary and limit-plus-one boundary has a deterministic test.
Cross-dimension tests prove that a wide shallow object, many short strings, and
many cheap-looking references cannot evade the aggregate ledger.

## 4. Owned Immutable JSON Values

The bounded parser produces only kernel-owned values:

```text
JsonNull
JsonBoolean
JsonString
JsonNumber
JsonArray(tuple[JsonValue, ...])
JsonObject(tuple[(JsonString, JsonValue), ...])
```

Objects reject duplicate member names before canonical ordering. Accepted
object entries are stored in RFC 8785 UTF-16 key order. Arrays preserve source
order. Strings reject unpaired surrogates. Numbers retain enough source-token
classification to distinguish integer-product rules while also carrying their
finite RFC 8785 numeric value. Non-finite conversion is rejected during parse.

The value graph is transitively immutable:

- no mutable `dict`, `list`, `set`, or arbitrary object is stored;
- no public method returns mutable internal storage;
- indexes contain immutable scalar identities, immutable paths, and references
  to immutable kernel values only;
- phase exports use registered immutable value types only;
- report assembly consumes immutable results and creates the final serialized
  artifact without exposing a mutable intermediate to another phase.

`JsonObject` and `JsonArray` may implement read-only `Mapping` and `Sequence`
interfaces over their tuples so schema tooling can inspect them. Schema type
checkers are explicitly configured for those kernel types. The kernel never
creates a mutable `dict`/`list` thaw merely to run a phase or schema validator.

`CompanionIndex` and `RecipeSemanticIndex` are semantic extension types, but
the kernel requires and tests their deep immutability before accepting them as
phase exports. A frozen dataclass containing a mutable mapping is not immutable.

## 5. Parsing And Canonical Identity

Both artifacts require strict UTF-8 without BOM. The bounded parser rejects:

- invalid UTF-8;
- duplicate object members;
- unpaired Unicode surrogates;
- literal or overflow-produced non-finite numbers;
- overlong number tokens;
- depth, width, node, string, or byte budget exhaustion.

The kernel records both identities:

```yaml
recipe_input_payload_sha256: sha256:...          # exact received bytes
validation_bundle_input_payload_sha256: sha256:... # exact received bytes
recipe_value_fingerprint: sha256:... | null      # canonical owned value
validation_bundle_fingerprint: sha256:... | null # canonical owned value
```

Canonical value fingerprints use `rook.canonical_json:v1`. Raw hashes remain
distinct evidence. Reordering identical object members moves the raw hash but
does not move the canonical fingerprint. Changing any key or value moves the
canonical fingerprint.

Malformed recipe bytes may still yield a report only when the validation bundle
has parsed successfully and its report-constructability envelope is present.
Malformed validation-bundle bytes cannot yield a semantic validation report,
because no trustworthy descriptor source exists.

## 6. Report-Constructability Preflight

After the validation bundle is parsed into one owned value, preflight checks the
fixed descriptor shells required by the LM9A report. Missing or wrong-container
shells produce a typed invocation failure. Malformed content inside present
shells remains reportable companion evidence.

Preflight establishes:

- exact validator and ruleset identity;
- both raw input hashes;
- the complete immutable validation-bundle value and fingerprint;
- either the complete immutable recipe value or one bounded recipe parse
  failure for the `schema` phase;
- fixed budget identity and consumed-budget receipt;
- mandatory descriptor shells;
- trusted validation time and session projection.

Only this `ValidationInvocation` enters the phase engine. It contains no
caller-owned value.

## 7. Declarative Phase Engine

Every phase is declared once:

```yaml
phase_name: provenance
dependencies:
  - schema
  - companion_artifacts
required_inputs:
  - parsed_recipe
  - companion_index
runner_id: lm9a.phase.provenance:v1
permitted_diagnostic_codes: []
permitted_blocker_codes: []
permitted_export_types:
  - lm9a.recipe_semantic_index:v1
```

The production `PhaseSpec` registry is the sole authority for dependencies,
required inputs, runner identity, issue codes, and export types. The engine,
ruleset fingerprint, phase table in the report, dependency tests, and runner
dispatch are derived from that registry. No second dependency dictionary or
prose-only dependency list controls execution.

Registry validation rejects duplicate names, missing dependencies, cycles,
unknown required inputs, unregistered runners, issue-code overlap, and unknown
export types before validation begins.

Phase execution rules are mechanical:

```text
dependency failed/not_evaluated -> phase not_evaluated
required input absent           -> phase not_evaluated
evaluated + error               -> failed
evaluated + blocker             -> blocked
otherwise                       -> passed
```

A blocked dependency remains evaluable unless its `PhaseSpec` says the required
input is absent. LM9A `provenance` requires both `parsed_recipe` and
`companion_index`, so its dependencies are exactly `schema` and
`companion_artifacts`.

## 8. Immutable Phase Results

Every runner returns:

```yaml
phase_name: ...
diagnostics: []
compile_blockers: []
exports: []
work_units_consumed: 0
```

The engine validates the result against the phase declaration before ledger
insertion. Diagnostics, blockers, and exports are immutable tuples of closed
registered values. A runner cannot mutate another result or an exported index.

The engine passes runners immutable inputs only. Tests attempt mutation through
the raw recipe value, companion index, semantic index, prior phase results, and
issue collections. Every mutation is structurally impossible or raises before
state changes. A later phase must observe the original value in every case.

Runners are pure with respect to product state. They receive trusted time,
session values, registries, and budget access only through immutable invocation
inputs. They cannot read wall-clock time, environment variables, files,
network/provider state, or mutable module globals, and they cannot write any
artifact or side effect. Report publication occurs only after the engine accepts
all results.

## 9. Issue Vocabulary

Kernel failures use a small stable external vocabulary:

```text
validation_input_invalid
validation_budget_exceeded
validation_constructability_failed
validator_identity_unavailable
validator_integrity_failure
validator_internal_failure
```

Each carries a closed `artifact_role`, `stage`, `subject_path`, and bounded
metadata object. Variable internal detail is hashed, not promoted into a new
public code.

Semantic extensions may register stable codes only when consumers need a
distinct programmatic response. Closely related schema branches share a stable
code plus bounded keyword/path metadata. The LM9A semantic plan must review and
reduce the draft 145-row registry before implementation; the existing draft
list is not frozen public API.

## 10. Deterministic Report Construction

The report builder consumes only:

- immutable invocation identity and budget receipt;
- the immutable phase registry;
- immutable phase results;
- semantic report-projection hooks registered by exact version.

It deterministically derives phase status, `valid`, `compile_ready`, issue
ordering, validation-context identity, and report fingerprint. It never calls a
phase runner, rereads input bytes, or reconstructs authority from prose.

If budget or integrity fails before the complete report is built, no partial
report is published. The public result is the typed kernel control failure.

## 11. Implementation Split

The existing combined LM9A implementation plan is withdrawn. After this spec is
reviewed, write two plans in order:

1. `LM9A-Kernel`: generic parser, budget ledger, immutable values, phase engine,
   issue registry, and report primitives. Kernel tests use synthetic phases and
   domain-neutral artifacts only.
2. `LM9A-Semantics`: recipe and companion schemas, semantic phase registrations,
   authority/provenance rules, and the radial/control fixtures. It imports the
   kernel and does not reimplement ingress, budgets, phase scheduling, or report
   assembly.

The semantics plan cannot begin execution until the kernel plan is implemented,
reviewed, and merged.

## 12. Deterministic Proof Targets

The kernel proof suite includes:

- exact and limit-plus-one cases for every budget dimension;
- wide shallow and deep narrow inputs;
- aggregate node/string/reference/work amplification;
- malformed validation-bundle bytes produce no semantic report;
- malformed recipe plus constructable bundle produces a report;
- malformed recipe plus malformed companion content receipts both independent
  failures;
- object member reordering preserves canonical identity;
- changed key/value content moves canonical identity;
- duplicate members fail before object construction;
- no mutable caller graph can enter the API;
- every accepted value and phase export is deeply immutable;
- mutation attempts through companion and semantic indexes cannot affect later
  phases;
- one `PhaseSpec` registry derives execution order, dependencies, issue
  authorization, and report rows;
- a schema-failed recipe leaves `provenance` not evaluated;
- diagnostic/blocker/work budget exhaustion yields one bounded control result;
- repeated runs over identical bytes, budget profile, ruleset, and trusted
  context produce identical reports.

No model, worker, compiler, tool, Rhino process, Grasshopper process, or live run
is part of LM9A-Kernel.
