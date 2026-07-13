# LM9A Validation Kernel Design

Status: design draft for review

Date: 2026-07-13

## 1. Purpose

LM9A validation is split into two implementation slices:

```text
LM9A-Kernel
  bounded byte ingress
  owned immutable JSON values
  one invocation-owned kernel ledger
  typed phase engine
  immutable phase results
  non-circular deterministic report sealing

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
is composed with the kernel before validation into one sealed validation
program. No registry remains open during an invocation.

The controlled kernel claim is:

> Two bounded raw JSON artifacts can be parsed into owned transitively
> immutable values, evaluated by one sealed declarative validation program
> under fixed kernel-controlled limits and trusted fingerprinted rule code, and
> reduced to a deterministic report without retaining mutable caller state or
> duplicating phase authority.

## 2. Sealed Validation Program

The only executable extension unit is:

```text
SealedValidationProgram
```

It is constructed once by a trusted composition function before any validation
invocation. Construction has a mutable local builder, but that builder never
escapes and cannot validate input. `seal()` validates the complete program,
converts every collection and runtime binding into transitively immutable
storage, computes the program fingerprint, and irreversibly closes the builder.
A failed seal produces no program.

The canonical program manifest contains:

```yaml
schema: rook.validation_program_manifest:v1
program_id: lm9a.planner_graph_recipe:v1
kernel_abi_version: rook.validation_kernel:v1
kernel_build_fingerprint: sha256:...
program_seal_profile: rook.validation_program_seal:v1
program_seal_implementation_fingerprint: sha256:...

budget_manifest: {}

parser_profile:
  tokenizer_version: ...
  parser_version: ...
  owned_value_abi: ...
  canonicalization_version: rook.canonical_json:v1

schema_evaluator_profiles: []

schemas: []
phases: []
runners: []
issue_vocabulary: []
export_types: []
report_projection: {}

implementation_sources: []
runtime_dependencies: []
program_fingerprint: sha256:...
```

`report_projection` is itself closed and names one projection ID, implementation
fingerprint, output schema ID/fingerprint, report-fingerprint field and
exclusion rule, and the exact immutable input envelope it consumes. That input
envelope is limited to captured program identity, admitted invocation evidence,
the frozen budget receipt, ordered phase specifications, and accepted immutable
phase results. A projection cannot request an ambient registry or arbitrary
callable.

Program sealing has a deliberately smaller trust bootstrap. The fixed kernel
composition code owns `rook.validation_program_seal:v1`, the manifest schema,
SHA-256, and the reference `rook.canonical_json:v1` implementation used to hash
the candidate manifest. The candidate program cannot select or replace this
seal implementation. Its runtime parser/canonicalizer/evaluator bindings are
validated and fingerprinted as manifest data; they do not certify themselves.
Every JSON component fingerprint placed in the manifest is independently
computed by this seal path from the supplied immutable component, never trusted
from a candidate's claimed hash. Raw source/distribution fingerprints use direct
SHA-256 under the source-normalization rule above.
The trusted application build/deployment verifies and supplies the kernel build
and seal-source fingerprints; the candidate contribution cannot author them.
Those fields make replay identity visible, while trust in their initial
assignment remains anchored outside the candidate manifest.

The build retains the final canonical manifest bytes as an immutable content-
addressed artifact under `program_fingerprint`. Reports need only carry
`program_id` and that fingerprint; auditors can resolve the complete manifest
without validation-time registry discovery. Failure to retain the manifest is a
deployment/evidence defect, not permission to reconstruct it from loaded
modules.

`program_fingerprint` is `rook.canonical_json:v1` over the complete normalized
manifest excluding only that field. Schema payloads are represented by exact
schema fingerprints. Every parser, canonicalizer, schema evaluator, runner,
export validator, and report projection has a stable implementation ID plus a
fingerprint of its normalized production source or immutable implementation
artifact. Runtime package names, exact versions, and applicable metaschema
fingerprints are included.

`implementation_sources` is a closed transitive allowlist of every behavior-
bearing product module used by runners, export validators, evaluator adapters,
and report projection. A runner cannot cite only its entry function while
leaving imported rule helpers outside program identity. Seal-time source/import
guards reject undeclared product modules and bind each declared module's UTF-8,
LF-normalized source hash. `runtime_dependencies` binds the Python
implementation/version plus exact package versions and installed distribution
or source hashes. Standard-library behavior is therefore bound through the
Python runtime identity; third-party behavior is bound directly. Any behavior-
bearing source or runtime change creates a different program fingerprint.

The sealed runtime object holds immutable bindings from every manifest
tokenizer, parser, canonicalizer, ledger implementation, schema payload,
schema evaluator, runner, export type, and projection ID to the exact trusted
callable or value used at runtime. Sealing verifies a one-to-one match: no
missing, extra, duplicate, or fingerprint-mismatched binding is allowed.
Runtime callables and schemas are never discovered from a global registry after
sealing.

V1 callable bindings are module-level functions with no closure cells, or
kernel-defined immutable callable records whose entire state is in the manifest.
Bound methods on mutable service objects and arbitrary callable instances are
rejected. Per-invocation evaluator or ledger state is created from immutable
program constants and retained only by the invocation; it is never stored back
into the sealed program.

Every manifest collection has schema-declared ordering and is closed with
`additionalProperties: false`. Program identity is computed only after schema,
dataflow, binding, and fingerprint checks pass. The mutable builder and sealed
program are different runtime types; `seal()` consumes the builder state, and
the builder exposes no method that can reopen or mutate the returned program.

The public validator accepts a `SealedValidationProgram` created by the trusted
composition path. It rejects an unsealed builder, a mutable registry, or a
program whose manifest/runtime binding check fails. The program reference and
fingerprint are captured once in the immutable invocation and used through
report sealing. Dispatch never re-resolves a callable from a registry or plugin
map, so replacing those containers after seal cannot change the selected
binding. Malicious in-place mutation of Python function objects, globals, or the
interpreter remains outside the trusted in-process boundary stated in Section
4.2; sealing is not misrepresented as process isolation.

## 3. Invocation Trust Boundary

The formal validation entrypoint is:

```text
validate_artifacts(
  program: SealedValidationProgram,
  raw_recipe_bytes: bytes,
  raw_validation_bundle_bytes: bytes,
)
```

The trusted application composition path supplies `program`; an artifact caller
controls only the two byte strings. The entrypoint rejects a builder, mutable
manifest, unsealed contribution, or fingerprint-inconsistent program before it
examines either artifact. It captures the sealed program object and fingerprint
once. No phase may replace them.

The byte arguments must be exact built-in `bytes` values. A caller cannot pass a
`Mapping`, custom container, parsed JSON graph, phase index, registry, budget, or
report projection.

Byte admission has this exact order:

```text
1. check both argument types
2. read both byte lengths without scanning content
3. compare both lengths to the sealed budget manifest
4. if either is over limit, stop without copying or hashing either input
5. otherwise copy and hash both admitted byte strings exactly once
6. parse the validation bundle
7. establish report constructability and trusted context
8. parse the recipe
```

An over-limit control result records each observed byte length, the applicable
limit, and `null` raw-input hashes. It never scans an arbitrarily oversized
argument merely to produce evidence about it. Exact-limit inputs are admitted,
copied, hashed, and parsed. This rule deliberately sacrifices an optional hash
of the other bounded artifact in favor of one simple bounded admission path.

The bundle is parsed first because it carries the authority needed to decide
whether a semantic report can exist. Both parses use the same invocation-owned
kernel ledger and fixed order from the sealed program.

```text
admitted exact bytes
-> bounded bundle tokenizer and iterative parser
-> validation-bundle constructability preflight
-> bounded recipe tokenizer and iterative parser
-> owned immutable JSON values or bounded recipe parse evidence
-> typed phase engine
-> deterministic report seal
```

Custom mappings, aliases, concurrent caller mutation, enumeration instability,
and repeated thawing do not exist at this boundary. JSON object member order is
semantically irrelevant. Two objects with the same members in different source
orders have different raw-byte hashes but the same canonical value fingerprint.

## 4. Kernel-Controlled Budget And Trust Model

### 4.1 Fixed Limits

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
| aggregate schema-evaluation shape units | 16,000,000 |
| diagnostics | 1,024 |
| compile blockers | 1,024 |
| kernel/cooperative phase work units | 1,000,000 |
| report canonical bytes | 2,097,152 |
| report projection fields | 131,072 |
| fixed report-seal allowance work units | 262,144 |

The bounded parser charges a node, member or item, decoded-string bytes, and
kernel work before allocation or attachment. It may not call `json.loads` and
reject only after an unbounded host graph exists.

Accounting for kernel-controlled work is normative:

- a parsed node is each JSON value, including each object and array; object keys
  are not nodes;
- object and array width are measured before construction;
- decoded-string bytes are the UTF-8 length of every decoded key and string
  value before schema-directed normalization, counted at every occurrence;
- a semantic reference is charged when a runner asks the kernel to record one
  discriminated reference in an invocation-owned resolution index;
- before each schema evaluation, the engine reserves
  `schema_nodes * instance_nodes` from the aggregate schema-shape counter and
  never refunds that reservation;
- each issue is charged before insertion, including an issue later rejected as
  duplicate or unauthorized;
- lexical work charges one unit per token;
- parse work charges one unit per node and per member/item attachment;
- graph and identity helpers charge one unit per node, edge, insertion, or
  lookup they expose;
- sorting `n` set-like items reserves
  `n * ceil(log2(max(n, 2)))` units before sorting;
- canonical serialization and hashing reserve one unit per started 64-byte
  output block;
- report projection charges one unit per emitted phase row, descriptor, issue,
  blocker, and fingerprint-projection field.

These units bound operations performed through kernel APIs. A runner cannot
author, refund, or replace ledger values, and a private counter never becomes
report evidence.

### 4.2 Honest Trusted-Code Boundary

LM9A v1 executes trusted, reviewed, fingerprinted Python phase runners and a
trusted fingerprinted schema-evaluator library in process. The fixed budget is a
hard limit for kernel-controlled allocation, parsing, collection cardinality,
kernel helper calls, issue/output insertion, scheduling, and report sealing. It
is not an OS-enforced time or memory sandbox for arbitrary Python instructions
inside trusted code.

The runner interface supplies no file, network, clock, provider, or mutation
handle. Source/import guards, deterministic replay tests, algorithm review, and
the sealed implementation fingerprints constrain runner behavior. Those are
architecture and supply-chain controls, not proof that Python bytecode cannot
read ambient process state. The spec therefore does not claim that a malicious
or defective in-process runner is hard-budgeted or sandboxed.

A non-returning runner, process termination, or memory failure may therefore
produce no kernel result at all. The kernel cannot honestly receipt an event
after its own process stops making progress. An external host watchdog may
receipt that operational failure, but it is not an LM9A semantic validation
report or proof that in-process work was bounded.

Any future untrusted extension surface, or any requirement to hard-limit all
runner CPU and memory, requires a separate process boundary with authenticated
IPC, no ambient file/network authority, and OS-enforced time and memory limits.
That isolation architecture is outside LM9A.

Schema evaluation follows the same trust statement. Static schema-profile
limits bound accepted schema shape and conservative evaluation size; the
underlying library's internal instructions are trusted program code rather than
pretended work-ledger events.

### 4.3 Non-Circular Budget Receipt

The engine owns the only ledger. It snapshots the ledger before and after each
runner invocation and derives the phase's kernel/cooperative delta. A runner
result contains no `work_units_consumed` field. The engine places the derived
`kernel_work_units_delta` in that phase's report row; it remains evidence about
kernel API usage, not elapsed time or total Python instructions.

After all immutable phase results are accepted, report sealing proceeds once:

```text
1. reserve the full fixed 262,144-unit report-seal allowance
2. freeze the budget receipt, including that fixed reservation
3. build the normalized report with `report_fingerprint` omitted
4. canonicalize that projection and compute its SHA-256 under a separate
   SealMeter
5. attach the resulting fingerprint and canonicalize the final artifact
6. publish only if both serializations together stay within the work allowance
   and each serialization stays within the canonical-byte limit
```

`report_fingerprint` is defined over step 4 only, excluding itself. `SealMeter`
can stop construction but cannot mutate the frozen receipt. Actual seal work is
intentionally not written back into the artifact; the fingerprinted receipt
records the fixed reservation. This removes the cycle in which hashing a report
would change a count embedded in that report. Exceeding either seal limit in
either serialization produces a validation-stage invocation failure and no
partial report.

A completed report contains:

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
  schema_evaluation_shape_units: 0
  diagnostics: 0
  compile_blockers: 0
  kernel_phase_work_units: 0
  report_seal_reserved_work_units: 262144
```

`limits_fingerprint` binds the exact table, admission order, accounting rules,
and seal algorithm in this section. All observed fields are engine-authored and
fingerprinted.

The seal allowance is intentionally separate from the 2 MiB output cap and must
be proven sufficient for two maximum-size canonical byte traversals plus the
maximum schema-permitted report-field projection. If that proof fails, the
budget profile is internally invalid and the program cannot seal; an
implementation may not discover an unreachable advertised output boundary only
at runtime.

Budget exhaustion uses one stable external code:

```yaml
kind: invocation_failure
failure_stage: preflight | validation
code: validation_budget_exceeded
artifact_role: validation_program | recipe | validation_bundle | combined |
               phase_engine | report_seal
program_id: ... | null
program_fingerprint: sha256:... | null
recipe_input_payload_sha256: sha256:... | null
validation_bundle_input_payload_sha256: sha256:... | null
budget_dimension: input_bytes | container_depth | number_token_chars |
                  parsed_nodes | object_members | array_items |
                  decoded_string_bytes | semantic_references |
                  schema_evaluation_shape_units |
                  diagnostics | compile_blockers | kernel_phase_work_units |
                  report_canonical_bytes | report_projection_fields |
                  report_seal_work_units
limit: 100000
observed_lower_bound: 100001
subject_path: /bounded/path | null
message: bounded text
```

`observed_lower_bound` is the first value known to exceed the limit; validation
does not continue to compute a larger total. Oversized raw bytes fail during
admission with no raw hash. A bounded recipe parse failure may become schema
evidence when the already parsed bundle is constructable. A validation-bundle,
phase-engine, or report-seal exhaustion produces an invocation failure because
the complete semantic report cannot be constructed. No path publishes a
partial report.

Every inclusive and limit-plus-one boundary has a deterministic proof.

## 5. Owned Immutable JSON Values

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
entries use RFC 8785 UTF-16 key order. Arrays preserve source order. Strings
reject unpaired surrogates. Numbers retain source-token classification and a
finite RFC 8785 numeric value. Non-finite conversion is rejected during parse.

The value graph is transitively immutable:

- no mutable `dict`, `list`, `set`, or arbitrary object is stored;
- no public method returns mutable internal storage;
- indexes contain immutable identities, paths, and references to immutable
  kernel values only;
- phase outputs use sealed-program export types only;
- report assembly never exposes a mutable intermediate to a phase.

`JsonObject` and `JsonArray` may implement read-only `Mapping` and `Sequence`
interfaces over tuples. Schema type checkers are configured for those exact
types. The kernel never thaws them to mutable host containers for validation.

Semantic indexes are accepted only through export validators sealed into the
program. A frozen dataclass containing a mutable mapping is not deeply
immutable and fails program/result integrity.

## 6. Parsing And Canonical Identity

Both artifacts require strict UTF-8 without BOM. The bounded parser rejects:

- invalid UTF-8;
- duplicate object members;
- unpaired Unicode surrogates;
- literal or overflow-produced non-finite numbers;
- overlong number tokens;
- depth, width, node, string, or parser-work exhaustion.

For admitted inputs, the kernel records:

```yaml
recipe_input_payload_sha256: sha256:...
validation_bundle_input_payload_sha256: sha256:...
recipe_value_fingerprint: sha256:... | null
validation_bundle_fingerprint: sha256:... | null
```

Canonical fingerprints use `rook.canonical_json:v1`. Raw hashes remain distinct
evidence. Reordering identical object members moves the raw hash but not the
canonical fingerprint. Changing any key or value moves canonical identity.

Malformed admitted recipe bytes may yield a report only when the validation
bundle parsed and its constructability envelope is present. Malformed or
over-limit validation-bundle bytes cannot yield a semantic report. An input
rejected by the initial byte cap has no raw hash because it was never admitted.

## 7. Closed Schema-Evaluator Profile

The sealed program binds an exact schema evaluator, package versions,
metaschema fingerprints, type checker, format policy, reference registry, and
two separately fingerprinted schema profiles:

1. trusted core schemas under `rook.json_schema_profile:lm9a_core_v1`; and
2. bundle-supplied payload schemas under
   `rook.json_schema_profile:lm9a_payload_v1`.

The payload profile uses Draft 2020-12 syntax but is deliberately not arbitrary
Draft 2020-12 execution. Its allowed keywords are:

```text
$schema $defs $ref
$comment title description default examples deprecated readOnly writeOnly
type enum const
properties required additionalProperties
items prefixItems minItems maxItems minProperties maxProperties
minLength maxLength
minimum maximum exclusiveMinimum exclusiveMaximum multipleOf
```

`$ref` must be a local JSON Pointer into the same schema document. Reference
graphs are acyclic. Remote retrieval and these features are forbidden in v1:

```text
$id $anchor $dynamicAnchor $dynamicRef $recursiveRef
pattern patternProperties propertyNames format
allOf anyOf oneOf not if then else
contains dependentSchemas unevaluatedItems unevaluatedProperties
contentEncoding contentMediaType contentSchema
custom keywords and executable callbacks
```

Annotation keywords are fingerprinted but never mutate an instance, supply a
semantic value, or affect authorization. In particular, JSON Schema `default`
is descriptive metadata and cannot become a Planner or policy default.

Static admission limits are sealed into the profile:

| Dimension | Limit |
|---|---:|
| nodes in one embedded schema | 4,096 |
| local references in one embedded schema | 256 |
| local reference depth | 16 |
| conservative schema-nodes x payload-nodes product | 2,000,000 |

The evaluator is configured with no retrieval callback. Unknown keywords fail
profile validation rather than being ignored. Trusted core schemas may use only
the payload keywords plus this exact bounded set:

```text
allOf anyOf oneOf not if then else dependentRequired
```

Core schemas remain acyclic and forbid regex/format callbacks, dynamic or remote
references, `uniqueItems`, `contains`, unevaluated/dependent-schema behavior,
and custom keywords. Their sealed limits are 32,768 schema nodes, 1,024 local
references, local reference depth 32, at most 16 alternatives per combinator,
combinator nesting depth 8, and
`schema_nodes * instance_nodes <= 8,000,000`. Identity grammar, duplicate IDs,
and semantic set uniqueness are checked by linear trusted runners rather than
potentially expensive schema regex or `uniqueItems` behavior. Changing either
profile, a core schema, evaluator package, metaschema, or type checker moves the
program fingerprint.

The applicable per-evaluation bounds and the invocation-wide 16,000,000-unit
schema-shape counter are reserved before evaluation. They bound accepted problem
shape; they are not misrepresented as instruction counters for the schema
library. These profiles are sufficient for LM9A schemas and fixture payloads. A
need for richer behavior requires a reviewed profile version, not an ad hoc
keyword exception.

## 8. Report-Constructability Preflight

After the validation bundle is parsed, preflight checks the fixed descriptor
shells required by the selected program's report projection. Missing or
wrong-container shells produce a typed invocation failure. Malformed content
inside present shells remains reportable companion evidence.

Preflight establishes:

- sealed program identity and exact runtime bindings;
- raw hashes for both admitted inputs;
- the complete immutable bundle and canonical fingerprint;
- either an immutable recipe or bounded recipe parse evidence for `schema`;
- fixed budget identity and the live engine-owned ledger;
- mandatory descriptor shells;
- trusted validation time and session projection.

Only this immutable `ValidationInvocation` enters the phase engine. It retains
the sealed program and no caller-owned value.

## 9. Typed Phase Program And Exact Dataflow

Every phase is declared once inside the sealed program:

```yaml
phase_name: provenance
ordering_after: []

input_bindings:
  - input_name: parsed_recipe
    source_kind: phase_output
    source_phase: schema
    source_output: parsed_recipe
    expected_type: kernel.json_object:v1
    cardinality: exactly_one

  - input_name: companion_index
    source_kind: phase_output
    source_phase: companion_artifacts
    source_output: companion_index
    expected_type: lm9a.companion_index:v1
    cardinality: exactly_one

provided_outputs:
  - output_name: recipe_semantic_index
    output_type: lm9a.recipe_semantic_index:v1
    cardinality: exactly_one
    permitted_on_statuses:
      - passed
      - blocked
    required_on_statuses:
      - passed
      - blocked

runner_id: lm9a.phase.provenance:v1
permitted_diagnostic_codes: []
permitted_blocker_codes: []
```

Closed `source_kind` values are:

```text
invocation_input
program_constant
phase_output
```

Input source identity is discriminated exactly:

| `source_kind` | Required identity fields |
|---|---|
| `invocation_input` | `source_input` |
| `program_constant` | `source_constant` |
| `phase_output` | `source_phase`, `source_output` |

Each binding also names its expected sealed type and cardinality
(`exactly_one`, `zero_or_one`, or `many`). Each provided output names its type,
cardinality, permitted statuses, and the subset of permitted statuses on which
it is mandatory. An output on an unpermitted status is an integrity failure.
`ordering_after` expresses sequencing with no data dependency; it may not be
used as a substitute for an input binding.

There is no separately authored `dependencies` list. The engine derives data
dependencies from `input_bindings`, unions them with `ordering_after`, validates
the DAG at program seal, and derives execution order, report rows, and tests from
that one declaration. If more than one phase is ready, the scheduler selects the
smallest `phase_name` under RFC 8785 UTF-16 code-unit ordering. Programs may use
`ordering_after` to make an evidence-relevant order explicit; ordering edges
never suppress execution after an earlier semantic failure.

Program sealing rejects:

- duplicate phases, inputs, or outputs;
- missing producers or output names;
- cycles;
- producer/consumer type or cardinality disagreement;
- a required status absent from an output's permitted statuses;
- an output type absent from the sealed export vocabulary;
- unknown runners or issue codes;
- extra runtime bindings;
- ambiguous use of ordering where a data binding is required.

Phase execution is mechanical:

```text
provider omits an output required for its derived status
  -> validator_integrity_failure; no report

provider failed/not_evaluated
  -> dependent input unavailable; consumer not_evaluated

provider passed/blocked and output is not required for that status
  -> legitimately absent input; consumer not_evaluated

all bound inputs available + evaluated error
  -> failed

all bound inputs available + evaluated blocker, no error
  -> blocked

all bound inputs available + no error/blocker
  -> passed
```

A passed or blocked provider can therefore support later evaluation, but it
cannot silently omit a promised index and make corruption look like ordinary
dependency suppression.

## 10. Immutable Phase Results And Integrity

Every runner returns only:

```yaml
diagnostics: []
compile_blockers: []
outputs:
  - output_name: recipe_semantic_index
    values: []
```

The engine derives phase identity, status, and budget delta. The result contains
no status claim, dependency claim, phase-name authority, or work count.

Before insertion, the engine verifies:

- every issue is permitted for that phase and classification;
- output names are unique and declared;
- output cardinality and sealed export validators pass;
- every output required for the derived status is present;
- no output or issue collection exceeds the program budget;
- every accepted value is transitively immutable.

Unknown, duplicate, mutable, wrong-typed, wrong-cardinality, extra, or missing
mandatory output is `validator_integrity_failure`, not a semantic diagnostic.
No partial report is published.

LM9A runner code is trusted program code under Section 4.2. It receives only
immutable bound inputs, a restricted kernel helper interface, and no product
mutation handle. Tests and source guards verify that the reviewed runners do not
use ambient I/O, clocks, providers, or mutable module registries. The guarantee
is replayability of the sealed trusted implementation, not an in-process
security boundary.

## 11. Issue Vocabulary

Kernel control failures use this small stable vocabulary:

```text
validation_input_invalid
validation_budget_exceeded
validation_constructability_failed
validator_identity_unavailable
validator_integrity_failure
validator_internal_failure
```

Each carries closed artifact role, stage, subject path, and bounded metadata.
Variable detail is hashed rather than promoted into a permanent public code.

Semantic issue candidates are supplied during trusted program composition only
when consumers need distinct programmatic behavior. Once sealed, the program's
issue vocabulary is immutable and fingerprinted. No implementation-planning
error matrix is automatically public API; the LM9A-Semantics plan must define
the smallest reviewed external code set before composition.

## 12. Deterministic Report Construction

The sealed report projection consumes only:

- immutable invocation and program identity;
- the frozen budget receipt;
- immutable declared phase specifications and accepted results.

It derives phase status, `valid`, `compile_ready`, issue ordering,
validation-context identity, and report fingerprint. It never calls a runner,
rereads bytes, performs registry discovery, or reconstructs authority from
prose.

The report includes `program_id`, `program_fingerprint`, and the exact component
identities required by the semantic report schema. Component fingerprints are
diagnostic provenance; the sealed program fingerprint is the executable
validation authority.

Report construction follows the one-shot seal from Section 4.3. An integrity or
seal-limit failure returns a typed control failure and publishes no partial
artifact.

## 13. Implementation Split

After both specs are reviewed, write two plans in order:

1. `LM9A-Kernel`: sealed-program composition, bounded parser, immutable values,
   kernel ledger, restricted schema profile, typed phase engine, and report
   primitives. Tests use synthetic phases and domain-neutral artifacts only.
2. `LM9A-Semantics`: one declarative program contribution containing recipe and
   companion schemas, exact phase specs, runner bindings, export validators,
   issue vocabulary, report projection, and offline fixtures.

The trusted composition function combines the kernel base and semantic
contribution, validates them, and returns one `SealedValidationProgram`.
LM9A-Semantics does not mutate a running registry or reimplement kernel
mechanics. Its plan cannot begin execution until the kernel is merged.

## 14. Deterministic Proof Targets

The kernel proof suite includes:

- unsealed builders and mutable registries are rejected;
- the fixed bootstrap seal, not the candidate runtime canonicalizer, computes
  program identity; a candidate canonicalizer cannot self-certify;
- every manifest/runtime binding is exact and program fingerprint changes when
  any budget, parser, schema profile, phase, runner, issue, export, input binding,
  ordering edge, or report projection changes;
- replacing a builder, registry, or plugin map after seal cannot alter the
  callable binding selected for an invocation;
- input byte limit checks occur before copying or hashing, exact-limit inputs are
  accepted, and over-limit failures contain no raw-input hash;
- exact and limit-plus-one cases cover every kernel-controlled dimension;
- wide-shallow, deep-narrow, aggregate node/string/reference, and report-size
  amplification are bounded;
- the restricted schema profile rejects every forbidden keyword, remote or
  dynamic reference, cycle, and complexity-limit excess before evaluation;
- schema evaluator package, metaschema, profile, and core schema changes move
  the program fingerprint;
- malformed bundle bytes produce no semantic report;
- malformed admitted recipe plus constructable bundle produces schema evidence;
- malformed recipe plus malformed companion content receipts both independent
  failures;
- object reordering preserves canonical identity while changed content moves it;
- every owned value, phase input, and export is deeply immutable;
- exact input bindings derive the phase DAG with no second dependency map;
- independent ready phases use the pinned UTF-16 tie-break, and
  `ordering_after` changes sequence without becoming a data dependency;
- a passed or blocked provider missing a mandatory output produces
  `validator_integrity_failure`, never consumer `not_evaluated`;
- missing, duplicate, extra, wrong-typed, and wrong-cardinality outputs each fail
  program or result integrity deterministically;
- runners cannot author work counts; the engine derives phase deltas;
- fixed report-seal reservation makes repeated report fingerprints independent
  of mutable counting during serialization;
- program sealing proves the fixed allowance can cover the budget profile's
  maximum report projection and two maximum-size canonical traversals;
- report seal work/size overflow publishes no report;
- repeated runs over identical admitted bytes, sealed program, and trusted
  context produce identical reports.

The proof suite also states its limit: in-process tests and fingerprints do not
turn trusted Python runners or the schema library into a hostile-code sandbox.

No model, worker, compiler, tool, Rhino process, Grasshopper process, or live run
is part of LM9A-Kernel.
