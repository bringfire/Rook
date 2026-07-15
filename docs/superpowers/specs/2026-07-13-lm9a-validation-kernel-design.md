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

> One untrusted bounded raw recipe artifact and one trusted-host-assembled
> bounded validation bundle can be parsed into owned transitively immutable
> values, evaluated by one sealed declarative validation program under fixed
> kernel-controlled limits and trusted fingerprinted rule code, and reduced to
> a deterministic report without retaining mutable caller state or duplicating
> phase authority.

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
report_projection:
  projection_id: ...
  required_for_compile_phases: []

implementation_sources: []
runtime_dependencies: []
program_fingerprint: sha256:...
```

`report_projection` is itself closed and names one projection ID, implementation
fingerprint, output schema ID/fingerprint, report-fingerprint field and
exclusion rule, the exact immutable input envelope it consumes, and the exact
set-like `required_for_compile_phases` allowlist. That input envelope is limited
to captured program identity, admitted invocation evidence, ordered phase
specifications, and accepted immutable phase results. The projection emits an
owned report body through a kernel-metered builder before budget freeze; it does
not receive or author the budget receipt, outer report fingerprint, or other
kernel-owned seal fields. A projection cannot request an ambient registry or
arbitrary callable. Program
sealing rejects an unknown or duplicate required phase name. The allowlist is
normalized by exact `phase_name` under RFC 8785 UTF-16 code-unit ordering before
program fingerprinting.

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

The kernel validator accepts a `SealedValidationProgram` created by the trusted
composition path. It rejects an unsealed builder, a mutable registry, or a
program whose manifest/runtime binding check fails. The program reference and
fingerprint are captured once in the immutable invocation and used through
report sealing. Dispatch never re-resolves a callable from a registry or plugin
map, so replacing those containers after seal cannot change the selected
binding. Malicious in-place mutation of Python function objects, globals, or the
interpreter remains outside the trusted in-process boundary stated in Section
4.2; sealing is not misrepresented as process isolation.

## 3. Invocation Trust Boundary

The formal internal validation entrypoint is:

```text
validate_artifacts(
  program: SealedValidationProgram,
  raw_recipe_bytes: bytes,
  trusted_validation_bundle: TrustedValidationBundleInput,
)
```

The two artifact principals are intentionally different:

```text
raw_recipe_bytes
  untrusted Planner-authored artifact

trusted_validation_bundle.raw_bytes
  authority context assembled by a trusted host/ingress principal
```

`TrustedValidationBundleInput` is a kernel-owned, transitively immutable carrier
containing exact built-in `bytes`, one exact sealed assembler profile, and a
non-serializable issuer-capability binding to that profile:

```yaml
schema: rook.trusted_bundle_assembler_profile:v1
profile_id: ...
assembler_kind: trusted_host_ingress | deterministic_fixture
assembler_id: ...
assembler_version: ...
implementation_fingerprint: sha256:...
permitted_program_ids: []
permitted_clock_sources:
  - trusted_system_clock | deterministic_fixture
profile_fingerprint: sha256:...
```

The fixed kernel host boundary owns
`rook.trusted_bundle_assembler_profile_seal:v1`. Trusted application composition
or deterministic fixture setup builds a candidate profile, the fixed seal path
validates and transitively freezes it, computes `profile_fingerprint` over exact
`rook.canonical_json:v1` bytes excluding that field, and returns a
`SealedTrustedBundleAssemblerProfile`. The final canonical profile bytes are
retained in the trusted immutable artifact store under that fingerprint.

Only a sealed profile can issue `TrustedValidationBundleInput`. Issuance adds an
opaque in-process capability binding to the exact sealed profile object. The
kernel verifies that binding before reading either artifact. A plain JSON object,
a matching profile fingerprint, or a caller-constructed lookalike cannot issue a
carrier. No ambient profile registry is consulted during validation.

The profile permits one or more exact `program_id` values and one or more closed
clock-source values. Preflight requires the selected sealed program ID to appear
in `permitted_program_ids`; after bundle parsing it requires the captured
`trusted_clock_source` to appear in `permitted_clock_sources`. In v1,
`deterministic_fixture` assembler profiles permit only
`deterministic_fixture`, and `trusted_host_ingress` profiles permit only
`trusted_system_clock`.

Profile arrays are nonempty, reject duplicates, and sort by RFC 8785 UTF-16
code-unit order before fingerprinting. `profile_id`, `assembler_id`, and
`assembler_version` are ASCII machine identifiers of at most 128 characters
each. `implementation_fingerprint` and `profile_fingerprint` are exactly
`sha256:` plus 64 lowercase hexadecimal characters. Invalid profile or carrier
metadata fails preflight before either artifact is copied or hashed.

These profile fields come from the sealed invocation principal, never from JSON
inside the bundle, and the kernel captures them once for validation-context
evidence. The profile is separate from `program_fingerprint`: changing it moves
validation-context/report identity and invalidates conformance evidence without
redefining validator behavior. The issuer capability and fixed profile seal are
the authority; serialized profile fields alone are not authentication. Code able
to forge those kernel capabilities is already inside the trusted host boundary.

A future public endpoint may accept an untrusted recipe or task request, but it
must assemble the validation bundle internally from authenticated sessions,
trusted registries, policies, and companion receipts. It must never expose
`raw_validation_bundle_bytes` as a client-controlled authority argument. Tests
use one explicitly sealed deterministic fixture assembler profile whose exact
profile and implementation fingerprints are recorded. Fixture assembly follows
the same bundle
schema, companion validation, and authority-resolution path as production; it
does not bypass semantic checks.

Both underlying byte strings receive identical hostile-input parsing defenses.
Trust in bundle assembly establishes which principal selected the authority
context; it does not assert that the bytes are well formed, internally
consistent, fresh, or schema valid.

The trusted application composition path supplies `program`; the artifact
caller controls only `raw_recipe_bytes`. The entrypoint rejects a builder,
mutable manifest, unsealed contribution, fingerprint-inconsistent program, or
untrusted/malformed bundle carrier before it examines either artifact. It
captures the sealed program object, program fingerprint, and assembler profile
once. No phase may replace them.

The recipe argument and `TrustedValidationBundleInput.raw_bytes` must be exact
built-in `bytes` values. A caller cannot pass a `Mapping`, custom container,
parsed JSON graph, phase index, registry, budget, report projection, unsealed
assembler profile, or self-asserted assembler descriptor.

Byte admission has this exact order:

```text
1. validate the sealed program, sealed assembler profile, and carrier issuer binding
2. check both underlying artifact values are exact built-in `bytes`
3. read both byte lengths without scanning content
4. compare both lengths to the sealed budget manifest
5. if either is over limit, stop without copying or hashing either input
6. otherwise copy and hash both admitted byte strings exactly once
7. parse the validation bundle
8. establish report constructability and trusted context
9. parse the recipe
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
| aggregate tokenizer/parser work units across both artifacts | 500,000 |
| registered semantic references | 25,000 |
| aggregate schema-evaluation conservative work-shape units | 16,000,000 |
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
- `schema_nodes` is the parsed-node count of the complete immutable schema
  document selected for an evaluation, including its root, all reachable and
  unreachable `$defs`, annotations, and every other admitted keyword value;
  object member names are not nodes, matching the general parsed-node rule;
- `instance_nodes` is the parsed-node count of the exact immutable instance root
  passed to the evaluator. Whole-artifact evaluation counts the complete
  artifact. Subtree evaluation counts that complete selected subtree and records
  the immutable source binding plus its exact RFC 6901 pointer; the empty pointer
  is allowed here only to identify the whole evaluation root and does not change
  the nonempty semantic-reference rule;
- a semantic reference is charged when a runner asks the kernel to record one
  discriminated reference in an invocation-owned resolution index;
- every admitted schema records `evaluation_expansion_units` from the bounded
  acyclic reference/combinator graph. Before each schema evaluation, the engine
  derives `shape_basis_units = max(schema_nodes, evaluation_expansion_units)`
  and computes `attempted_shape_units = shape_basis_units * instance_nodes`
  under metric
  `rook.schema_evaluation_shape:max_schema_or_expansion_times_instance:v1`.
  With `shape_basis_units > 0`, it first tests `instance_nodes` against both
  `floor(per_evaluation_limit / shape_basis_units)` and
  `floor(aggregate_remaining / shape_basis_units)` using checked nonnegative
  integer arithmetic. An over-limit or host-integer-overflow condition becomes
  `validation_budget_exceeded` before evaluator construction; multiplication
  occurs only after both guards pass. A valid schema and its expansion measure
  each contribute at least one unit;
- the checked product is reserved in full from both the applicable
  per-evaluation limit and the invocation-wide schema-shape counter and is never
  refunded. Repeating an evaluation reserves the full product again, even for
  identical schema/instance fingerprints. Schema compilation, `$ref` resolution,
  evaluator memoization, or other caching cannot reduce evidence units;
- each schema-shape reservation and evaluation meter row records the metric ID,
  `schema_nodes`, `evaluation_expansion_units`, derived `shape_basis_units`,
  `instance_nodes`, and the checked shape-unit product, in addition to its
  contiguous zero-based `evaluation_index`, schema ID/fingerprint, immutable
  instance binding and pointer, instance fingerprint, applicable per-evaluation
  limit, and aggregate total after reservation. Rejected reservations retain the
  metric and factors while the uncomputed product remains `null`;
- each issue is charged before insertion, including an issue later rejected as
  duplicate or unauthorized;
- tokenizer/parser work charges one unit per started 64-byte raw-input block,
  one unit per token, one unit per node, and one unit per member/item attachment;
  this invocation-wide counter spans the bundle and recipe and is never refunded;
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
1. invoke the sealed projection once into a kernel-owned report-body builder;
   charge every body field before attachment
2. validate the owned body and charge the fixed outer-envelope and budget-
   receipt field shape
3. reserve the full fixed 262,144-unit report-seal allowance
4. freeze the budget receipt, including body/envelope field counts and that
   fixed reservation
5. attach the frozen receipt and kernel-owned envelope without changing the
   already charged shape; leave `report_fingerprint` omitted
6. canonicalize that projection and compute its SHA-256 under a separate
   SealMeter
7. attach the resulting fingerprint and canonicalize the final artifact
8. publish only if both serializations together stay within the work allowance
   and each serialization stays within the canonical-byte limit
```

`report_fingerprint` is defined over step 6 only, excluding itself. `SealMeter`
can stop construction but cannot mutate the frozen receipt. Actual seal work is
intentionally not written back into the artifact; the fingerprinted receipt
records the fixed reservation. This removes the cycle in which hashing a report
would change a count embedded in that report. Exceeding either seal limit in
either serialization produces a validation-stage invocation failure and no
partial report.

The sealed output schema and projection declaration identify the exact object
path occupied by the kernel-owned budget receipt. The body builder rejects that
path and every other kernel-owned field. Kernel attachment replaces no body
value and adds exactly the precharged fixed shape. That fixed count includes the
eventual `report_fingerprint` field even though its value is omitted from the
first canonical projection. A projection exception,
duplicate field, over-budget insertion, wrong body type, or attempt to author a
kernel field produces no report.

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
  parser_work_units: 0
  semantic_references: 0
  schema_evaluation_shape_units: 0
  diagnostics: 0
  compile_blockers: 0
  kernel_phase_work_units: 0
  report_projection_fields: 0
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
                  decoded_string_bytes | parser_work_units |
                  semantic_references |
                  schema_evaluation_shape_units |
                  diagnostics | compile_blockers | kernel_phase_work_units |
                  report_canonical_bytes | report_projection_fields |
                  report_seal_work_units
limit: 100000
observed_lower_bound: 100001
subject_path: /bounded/path | null
message: bounded text
```

Every kernel control-failure `message` is NFC-normalized, contains at most 512
Unicode code points, and contains no raw input, raw exception text, or secret
capability value. Variable detail is represented only by a lowercase prefixed
SHA-256 field in the applicable closed failure envelope. Truncation is by
Unicode code point before canonical serialization, so all implementations
produce the same bounded text.

`observed_lower_bound` is the first value known to exceed the limit; validation
does not continue to compute a larger total. Oversized raw bytes fail during
admission with no raw hash. After admission, a recipe-local depth, object-width,
array-width, number-token, numeric-domain, UTF-8, Unicode, or JSON-syntax failure
may become schema evidence when the already parsed bundle is constructable.
There is no second recipe-local byte limit after admission.

The `parsed_nodes`, `decoded_string_bytes`, and `parser_work_units` limits are
invocation-wide across both artifacts. Exhausting any of them at either parse
stage is therefore a `preflight / validation_budget_exceeded` invocation failure
with `artifact_role: combined`, even when the first artifact had already become
constructable. It never becomes recipe-local schema evidence. Validation-bundle,
phase-engine, or report-seal exhaustion likewise produces an invocation failure
because the complete semantic report cannot be constructed. No path publishes a
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
| conservative max(schema nodes, expansion units) x payload nodes | 2,000,000 |
| instance JSON Pointer UTF-8 code units (bytes) | 4,096 |
| schema evaluation expansion units | 32,768 |

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
combinator nesting depth 8, at most 65,536 schema evaluation expansion units,
an inclusive 4,096-byte instance JSON Pointer, and
`max(schema_nodes, evaluation_expansion_units) * instance_nodes <= 8,000,000`.
Identity grammar, duplicate IDs,
and semantic set uniqueness are checked by linear trusted runners rather than
potentially expensive schema regex or `uniqueItems` behavior. Changing either
profile, a core schema, evaluator package, metaschema, or type checker moves the
program fingerprint.

Expansion units are checked at admission over the acyclic schema graph. A leaf
contributes one unit, a single structural or reference edge forwards its
target's units, and branching edges sum with saturation at the profile limit
plus one. The profile identity binds the limit and each admitted schema records
its exact observed expansion units. Limit-plus-one rejection precedes schema
library construction. The profile identity also binds the exact conservative
shape metric ID and formula. Every sealed-program schema descriptor binds its
observed expansion units so a different expansion result moves program identity.
Expansion is not an independent admission-only allowance: it is coupled to the
exact evaluated instance cardinality through the checked reservation above.

The applicable per-evaluation bounds and the invocation-wide 16,000,000-unit
schema-shape counter are reserved before evaluation. They bound accepted problem
shape; they are not misrepresented as instruction counters for the schema
library. A need for richer behavior requires a reviewed profile version, not an
ad hoc keyword exception.

### 7.1 Sealed-Program Feasibility Release Gate

The kernel does not claim that every syntactically admissible maximum-size
schema/instance combination must fit the aggregate invocation cap. Aggregate
budget rejection is a valid bounded outcome. It does require positive evidence
that the exact sealed program and its required conformance campaign are usable.

#### Release-Owned Gate Authority

Trusted release composition supplies one independently sealed gate profile:

```yaml
schema: rook.validation_conformance_gate_profile:v1
gate_profile_id: rook.validation_conformance_gate:lm9a_v1
gate_profile_version: v1
gate_implementation_fingerprint: sha256:...
budget_profile: rook.validation_budget:lm9a_v1
limits_fingerprint: sha256:...
campaign_input_byte_limit: 4194304
referenced_case_content_byte_limit: 4194304
gate_profile_fingerprint: sha256:...
```

The fixed release host seals this closed profile together with the exact gate
callable binding and returns a `SealedConformanceGateProfile`. Its fingerprint
is `rook.canonical_json:v1` over the normalized profile excluding only
`gate_profile_fingerprint`. The sealed runtime binding must match
`gate_implementation_fingerprint`; no registry or campaign lookup occurs after
seal. The release invocation captures this sealed object before it reads the
campaign.

`campaign_input_byte_limit` is an exact inclusive gate-admission limit owned by
the independently selected profile. LM9A v1 fixes it at 4,194,304 bytes. The
gate checks the exact built-in byte length before copying or hashing campaign
content. A limit-plus-one campaign returns
`campaign_admission_failed` with a null campaign hash. The field participates
in `gate_profile_fingerprint`; the campaign cannot override it. It is separate
from the validation invocation's recipe/bundle counters even though v1 uses the
same numeric cap as the validation-bundle input.

`referenced_case_content_byte_limit` is a separate exact inclusive cap for each
artifact-store object resolved by a campaign case, including a core positive
instance, fixture manifest, raw fixture recipe, and raw fixture validation
bundle. The gate obtains the exact built-in `bytes` object and checks `len()`
before copying or hashing it. An over-cap case object fails that row as
`case_content_unavailable` with no schema-attempt row and no content hash. Raw
fixture recipe/bundle bytes remain subject to their stricter validation-
invocation caps after this gate-level admission. V1 fixes the case-content cap
at 4,194,304 bytes and fingerprints it in the gate profile.

Campaign JSON, fixture-manifest JSON, and each core positive instance use the
same bounded owned parser and the parser/depth/width/node/string limits from the
profile's exact `budget_profile`. The campaign has one fresh gate-admission
ledger; each referenced JSON object has its own fresh gate-admission ledger.
Those control-plane parser counters are not merged into a fixture validation
report's invocation budget and cannot reduce or enlarge its limits. Raw fixture
recipe and validation-bundle bytes are not parsed by the gate; after bounded
content resolution they enter `validate_artifacts` and are metered there.

The campaign may bind `required_gate_profile_fingerprint`, but that field is a
compatibility requirement, not a selector. It cannot name an implementation,
construct a gate profile, or cause release composition to choose a different
gate. A mismatch is evaluated by the already selected sealed gate and fails
closed.

#### Earliest Honest Gate Result

Some failures occur before a content-addressed conformance report can truthfully
exist. The kernel therefore has one typed, non-artifact runtime result:

```yaml
type_name: ConformanceGateInvocationFailure
stage: gate_authority | program_authority | campaign_admission | campaign_parse | campaign_schema | campaign_identity | gate_execution | report_seal
code: ...
gate_profile_fingerprint: sha256:... | null
program_fingerprint: sha256:... | null
campaign_input_size: 0
campaign_input_sha256: sha256:... | null
bounded_detail_sha256: sha256:...
report_emitted: false
trusted_gate_result_issued: false
```

This value is bounded process evidence, not a schema-governed artifact, is not
stored as a conformance report, has no artifact fingerprint, and cannot satisfy
a deployment gate. `campaign_input_size` is the observed length when available.
The input hash is `null` when content is unavailable or rejected by the byte cap;
after bounded admission it is the exact raw-byte hash even if parsing or schema
validation fails. `bounded_detail_sha256` covers a fixed-size internal detail
record and never exposes raw campaign content. Its closed codes are:

```text
gate_profile_not_sealed
gate_profile_runtime_binding_invalid
program_not_sealed
program_runtime_binding_invalid
campaign_content_unavailable
campaign_admission_failed
campaign_parse_failed
campaign_schema_failed
campaign_fingerprint_mismatch
campaign_case_set_fingerprint_mismatch
gate_execution_failed
gate_budget_exceeded
gate_report_seal_failed
```

The earliest-honest-result matrix is normative:

| Earliest established boundary | Result | Report | Trusted gate-result capability |
|---|---|---|---|
| sealed gate profile or sealed program authority is absent/invalid | `ConformanceGateInvocationFailure` | none | none |
| campaign bytes are unavailable, over limit, malformed, schema-invalid, duplicate-keyed, or fingerprint-inconsistent | `ConformanceGateInvocationFailure` | none | none |
| campaign is constructable, but its program/profile binding or core-schema coverage is wrong | failed aggregate report with `campaign_integrity.passed=false` and zero case rows | yes | yes |
| campaign integrity passes, but case content is unavailable or fingerprint-mismatched | failed case row with zero schema-attempt rows | yes | yes |
| schema reservation is rejected before evaluator invocation | failed case row with one `reservation_rejected` attempt row | yes | yes |
| reservation succeeds | completed or evaluator-failed attempt row with exact reservation evidence | yes | yes |
| a caught gate-integrity/budget failure or aggregate report-seal failure prevents a complete report after campaign identity exists | `ConformanceGateInvocationFailure` | none | none |

Report authority begins only after the independently supplied sealed gate
profile, sealed program, and one schema-valid, fingerprint-consistent campaign
identity all exist. A constructable campaign-wide failure does not need a false
`case_id`; it is represented by `campaign_integrity`. No invocation failure is
silently promoted into a report.

`gate_execution_failed` is reserved for caught trusted-gate integrity failures
that prevent a structurally complete aggregate report; ordinary case failures
remain result rows. `gate_budget_exceeded` covers gate-controlled parser,
collection, or report-projection limits after campaign identity exists.
`gate_report_seal_failed` covers either canonical serialization exceeding the
profile-bound report byte/work limit. These failures retain the already captured
program/profile/campaign hashes when available, expose no partial row ledger or
report bytes, and cannot issue `TrustedConformanceGateResult`.

A required campaign is one closed content-addressed artifact:

```yaml
schema: rook.validation_conformance_campaign:v1
campaign_id: ...
campaign_version: ...

program_id: ...
program_fingerprint: sha256:...
required_gate_profile_fingerprint: sha256:...

required_cases:
  - case_id: ...
    case_kind: core_schema_positive
    schema_case:
      schema_id: ...
      schema_fingerprint: sha256:...
      instance_fingerprint: sha256:...
      instance_content_ref: artifact:...
    fixture_case: null
    case_fingerprint: sha256:...

  - case_id: ...
    case_kind: semantic_fixture
    schema_case: null
    fixture_case:
      fixture_fingerprint: sha256:...
      fixture_content_ref: artifact:...
      recipe_input_payload_sha256: sha256:...
      validation_bundle_input_payload_sha256: sha256:...
      assembler_profile_fingerprint: sha256:...
    case_fingerprint: sha256:...

required_case_set_fingerprint: sha256:...
campaign_fingerprint: sha256:...
```

`required_cases` is a set-like collection sorted by exact `case_id`; duplicate
IDs or fingerprints are invalid. Each variant is closed and rejects fields from
the other variant. A case fingerprint is `rook.canonical_json:v1` over its
complete normalized case descriptor excluding only `case_fingerprint`.
`required_case_set_fingerprint` covers the normalized sorted array of exact
`{case_id, case_fingerprint}` pairs.

The campaign schema sets `required_cases.maxItems` to exactly 256. The sealed
256-row proof fits the unchanged 4 MiB report-canonicalization allowance and
131,072-field projection budget; this schema cap does not weaken the separate
16,384-item parser budget.
`campaign_fingerprint` covers the complete normalized campaign excluding only
that field, so it includes the required-case-set and required-gate-profile
fingerprints.

The campaign schema and every nested object are closed with
`additionalProperties: false`. `null`, absent, and empty collections remain
distinct. Trusted release composition supplies the campaign as an immutable
input distinct from the eventual report and captures the expected
`campaign_id`, `campaign_version`, `campaign_fingerprint`, and
`required_case_set_fingerprint` before the gate runs. Neither a result row nor
the aggregate report may nominate or replace that authority. A reviewed change
to the mandatory case set therefore changes both campaign fingerprints and the
release input that pins them.

Every `content_ref` resolves through the trusted immutable artifact store and
must match its bound fingerprint. A semantic fixture manifest resolves the full
raw recipe bytes, full raw validation-bundle bytes, expected terminal/status
claims, and the exact sealed assembler-profile fingerprint. A core-schema case
resolves the complete positive instance. Fingerprints without resolvable content
do not make a campaign executable.

The semantic fixture manifest is one closed generic kernel artifact:

```yaml
schema: rook.validation_conformance_fixture:v1
fixture_id: ...

recipe_input:
  content_ref: artifact:...
  input_payload_sha256: sha256:...

validation_bundle_input:
  content_ref: artifact:...
  input_payload_sha256: sha256:...

assembler_profile_fingerprint: sha256:...

expected_result:
  result_kind: published_report
  report_schema_id: ...
  report_fingerprint: sha256:...
  control_failure_stage: null
  control_failure_code: null
  control_failure_artifact_role: null

fixture_fingerprint: sha256:...
```

`expected_result.result_kind` is exactly `published_report` or
`control_failure`. For `published_report`, `report_schema_id` and
`report_fingerprint` are nonnull and all three control-failure fields are null.
For `control_failure`, the report fields are null and the three closed control-
failure fields are nonnull. The gate compares the complete result identity; it
does not trust fixture-authored `valid`, `compile_ready`, phase-status, or
outcome booleans. Scenario-specific expected semantic fields are already bound
by the expected report fingerprint. `fixture_fingerprint` covers the normalized
manifest excluding only itself.

Trusted release composition also supplies one immutable
`TrustedConformanceFixtureContext` before campaign inspection. It contains one
issuer-capability-bound immutable artifact store and an immutable set of exact
`SealedTrustedBundleAssemblerProfile` objects keyed by profile fingerprint. The
campaign and fixture may require one of those fingerprints but cannot construct,
register, or replace a profile or store. The gate resolves content and assembler
authority only from this captured context. A missing content object is
`case_content_unavailable`; a missing or mismatched sealed assembler profile is
`case_execution_failed`. Both produce a failed fixture row with zero schema-
attempt rows when no schema evaluation was reached.

The trusted gate emits one aggregate content-addressed report:

```yaml
schema: rook.validation_conformance_report:v1

program_id: ...
program_fingerprint: sha256:...
campaign_id: ...
campaign_fingerprint: sha256:...
required_case_set_fingerprint: sha256:...

gate:
  gate_profile_id: rook.validation_conformance_gate:lm9a_v1
  gate_profile_version: v1
  gate_implementation_fingerprint: sha256:...
  budget_profile: rook.validation_budget:lm9a_v1
  limits_fingerprint: sha256:...
  campaign_input_byte_limit: 4194304
  referenced_case_content_byte_limit: 4194304
  gate_profile_fingerprint: sha256:...

campaign_integrity:
  program_binding_matches: true
  gate_profile_binding_matches: true
  core_schema_coverage_matches_program: true
  missing_core_schema_case_ids: []
  extra_core_schema_case_ids: []
  failure_codes: []
  passed: true

result_rows:
  - result_index: 0
    case_id: ...
    case_kind: core_schema_positive
    case_fingerprint: sha256:...
    outcome: passed

    schema_case_result:
      instance_schema_valid: true

    fixture_case_result: null

    schema_evaluations:
      - evaluation_index: 0
        schema_id: ...
        schema_fingerprint: sha256:...
        instance_binding:
          artifact_id: ...
          artifact_fingerprint: sha256:...
        instance_pointer: ""
        instance_fingerprint: sha256:...
        attempt_status: evaluation_completed
        shape_metric_id: rook.schema_evaluation_shape:max_schema_or_expansion_times_instance:v1
        schema_nodes: 1
        evaluation_expansion_units: 1
        shape_basis_units: 1
        instance_nodes: 1
        attempted_shape_units: 1
        per_evaluation_limit: 2000000
        aggregate_before_reservation: 0
        aggregate_after_reservation: 1
        evaluator_invoked: true
        evaluation_passed: true
        failure_code: null

    aggregate_schema_evaluation_shape_units: 1
    invocation_shape_limit: 16000000
    within_every_per_evaluation_limit: true
    within_invocation_limit: true
    failure_code: null

completeness:
  required_case_count: 1
  result_row_count: 1
  missing_case_ids: []
  extra_case_ids: []
  duplicate_case_ids: []
  case_kind_mismatch_ids: []
  case_fingerprint_mismatch_ids: []
  complete: true

all_case_outcomes_passed: true
decision: passed
report_fingerprint: sha256:...
```

For a `semantic_fixture` row, `schema_case_result` is null and the closed
`fixture_case_result` is:

```yaml
expected_result_kind: published_report | control_failure
expected_report_schema_id: ... | null
expected_result_fingerprint: sha256:... | null
expected_control_failure_stage: ... | null
expected_control_failure_code: ... | null
expected_control_failure_artifact_role: ... | null

actual_result_kind: published_report | control_failure | unavailable
actual_report_schema_id: ... | null
actual_result_fingerprint: sha256:... | null
actual_control_failure_stage: ... | null
actual_control_failure_code: ... | null
actual_control_failure_artifact_role: ... | null

result_identity_matches: true
```

The same variant/null rules used by the fixture manifest apply to expected and
actual fields. `unavailable` requires every actual detail field to be null and
`result_identity_matches=false`. The gate derives every actual field and the
match boolean from the trusted runtime result. A fixture row passes only when
its content/profile bindings resolve, the exact expected result identity
matches, and every reached schema evaluation remains within its applicable
bounds.

For a `core_schema_positive` row, `schema_case_result` is always the closed
object shown above and `fixture_case_result` is null.
`instance_schema_valid` is `true` or `false` only after one
`evaluation_completed` attempt and equals that attempt's
`evaluation_passed`; it is null when content/admission/reservation/evaluator
failure prevented a completed boolean result. A passing core row requires it to
be `true`.

Before scheduling cases, the independently selected gate derives
`campaign_integrity` against the sealed program and gate profile. Its closed
failure codes are `campaign_program_binding_mismatch`,
`campaign_gate_profile_binding_mismatch`,
`campaign_core_schema_coverage_missing`, and
`campaign_core_schema_coverage_extra`. The ID lists are unique and sorted. If
any integrity check fails, `passed=false`, `result_rows=[]`, and the report is a
constructable failed gate result; no case is executed.

When campaign integrity passes, the v1 gate visits campaign cases sequentially
in the campaign's sorted `case_id` order, intends to schedule each required case
once, records its terminal outcome, and continues after an ordinary case
failure. It never creates a replacement attempt. The report schema nevertheless
permits zero or more indexed execution rows, including duplicate case IDs, so a
gate defect remains receiptable. `result_rows` is an ordered execution ledger
with contiguous zero-based `result_index`, not a set. Retaining every row lets a
conforming failed report receipt duplicate execution instead of becoming
structurally invalid.
Each row's `schema_evaluations` is likewise an ordered, contiguous zero-based
sequence in actual invocation order; it is never sorted by schema identity after
execution. Missing, extra, duplicate, case-kind-mismatched, or fingerprint-
mismatched cases remain visible in the derived completeness object and force
`complete=false`. `complete=true` requires exactly one matching row for every
required case and no missing, extra, duplicate, kind-mismatched, or fingerprint-
mismatched row. Exact-once is therefore a passing completeness condition, not a
schema restriction on failed reports.

The gate copies the exact program, campaign, gate-profile, budget, case, and
assembler-profile fingerprints from resolved immutable artifacts. The kernel
meter authors all node/unit counts and the gate derives all booleans,
completeness lists, `outcome`, and `decision`; cases cannot submit those values
as claims. `all_case_outcomes_passed=true` exactly when `complete=true` and every
row outcome is `passed`; it is false for a campaign-integrity failure or
incomplete execution. `decision=passed` exactly when
`campaign_integrity.passed=true`, `all_case_outcomes_passed=true`, every per-
evaluation bound passed, and every case invocation remained within the aggregate
bound. Otherwise it is `failed`.

For semantic fixtures, the gate invokes a package-private audited form of the
same fixed kernel validation entrypoint. The kernel returns one immutable,
non-serializable execution-audit capability alongside the ordinary public
report/control result. That audit contains the exact ordered schema-evaluation
receipts authored by the adapter and ledger, including rejected reservations.
The public `validate_artifacts` surface does not accept or expose a caller-
constructable audit argument, and the gate never reconstructs attempts from a
semantic report or fixture claim. A missing, forged, or program-mismatched audit
is `gate_execution_failed` and prevents an aggregate report.

The campaign and report schemas and every nested object are closed with
`additionalProperties: false`. The case-level `failure_code` is exactly `null`
for a passing row; a failed row uses one of `case_content_unavailable`,
`case_fingerprint_mismatch`, `case_execution_failed`,
`schema_evaluation_failed`, or `validation_budget_exceeded`. Gate-wide failures
belong to `campaign_integrity` or `ConformanceGateInvocationFailure`, never a
synthetic case row. `instance_binding` identifies the exact immutable
artifact root from which the evaluated instance was selected; its fingerprint
must resolve, and `instance_pointer` selects the exact root or subtree under the
Section 4 counting rule.

`schema_evaluations` contains an attempt row only after the case reaches the
schema-evaluation boundary. Content-unavailable and content-fingerprint failures
have zero rows. Every attempt row records the aggregate counter before
reservation. The three attempt statuses have exact field rules:

- `reservation_rejected`: `evaluator_invoked=false`,
  `attempted_shape_units=null`, `aggregate_after_reservation=null`,
  `evaluation_passed=null`, and `failure_code` is exactly one of
  `per_evaluation_limit_exceeded`, `invocation_shape_limit_exceeded`, or
  `shape_product_overflow`; the aggregate counter remains unchanged;
- `evaluation_completed`: checked multiplication and reservation succeeded,
  `attempted_shape_units` is the nonnegative checked product,
  `aggregate_after_reservation` equals `aggregate_before_reservation` plus that
  product, `evaluator_invoked=true`, and `evaluation_passed` is boolean;
  `failure_code` is `null` when true and `instance_schema_failed` when false;
- `evaluator_failed`: reservation succeeded with the same nonnull product and
  aggregate equation, `evaluator_invoked=true`, `evaluation_passed=null`, and
  `failure_code=schema_evaluator_failed`.

Reservations are never refunded. The case-level
`aggregate_schema_evaluation_shape_units` equals the last successful
`aggregate_after_reservation`, or zero when no reservation succeeded. A rejected
reservation makes the applicable limit boolean false without pretending that a
reservation completed.

Every status retains the metric ID and all four factor fields. Deterministic
validation recomputes `shape_basis_units` and the accepted product rather than
trusting receipt claims. A missing, mismatched, or unsupported metric identity is
an integrity failure, not an ordinary over-budget outcome.

Projection also requires the exact ledger-issued reservation capability. Every
reservation carries a private origin capability for the one invocation ledger
that issued it. That origin is never serialized, fingerprinted as public
evidence, or reconstructible from metric factors. Audit projection receives the
expected invocation ledger and rejects a genuine reservation issued by any
other ledger, including one with identical factors, limits, and aggregate
values. The reservation's schema-node, expansion, and instance-node factors
must also equal the admitted schema and source-bound instance; an otherwise
equal product or basis cannot substitute for those identities.

Schema evaluation results are likewise kernel-issued immutable receipts. Their
private issuer capability binds the reservation, evaluator-invocation status,
bounded issues, result status, failure code, exact admitted-schema identity, and
exact evaluation-subject identity. An evaluated subject binding includes the
immutable instance identity and the exact `InstanceBinding` identity and fields.
A rejected pre-evaluation report candidate instead binds the exact kernel-issued
candidate identity. Exactly one subject variant is permitted.

Public callers cannot construct an authoritative success or failure receipt by
reproducing serialized fields. Audit entry construction first verifies the
receipt issuer, then its reservation against the exact expected ledger, then its
private schema and subject bindings against the source-bound schema/instance or
pre-evaluation candidate being projected. A genuine same-ledger receipt cannot
be reused for a different equal-shaped schema, sibling instance, equivalent but
different binding object, or equal-valued candidate identity. None of these
private capabilities enters an attempt row, report, fingerprint, or other
content-addressed public artifact.

Authentication remains transitive after issuance. Revalidating an audit entry
must revalidate its embedded receipt, and revalidating that receipt must
revalidate the reservation's issuer, origin, and signed state. Post-issuance
mutation or invalidation of any nested issuer, signature, or reservation-origin
capability invalidates the enclosing receipt and audit entry before projection.

Each case or semantic validation invocation starts its aggregate chain at zero.
For an accepted reservation, deterministic conformance proves the product is
within the applicable per-evaluation limit and the resulting aggregate is within
the invocation limit.
For a rejected reservation, conformance replays the ledger's fail-closed decision
order exactly: checked-integer overflow, then per-evaluation excess, then
invocation-aggregate excess. A rejection code without the corresponding
mathematical condition, or an accepted row that exceeds either limit, is a gate
integrity failure.

For `per_evaluation_limit_exceeded`, only
`within_every_per_evaluation_limit=false` is forced by that attempt. For
`invocation_shape_limit_exceeded`, only `within_invocation_limit=false` is
forced. `shape_product_overflow` makes both booleans false because neither bound
can be certified. Other attempt rows contribute normally to the aggregate case
booleans.

A `reservation_rejected` attempt maps the case-level failure to
`validation_budget_exceeded`. A completed schema rejection or evaluator failure
maps it to `schema_evaluation_failed`. Earlier case failures retain zero or any
already completed attempt rows; no summary erases work that actually occurred.

Completeness ID lists contain unique IDs and sort by RFC 8785 UTF-16 code-unit
order. The report's
`required_case_set_fingerprint` must equal the independently selected campaign
value. The report fingerprint is `rook.canonical_json:v1` over the complete
normalized report excluding only `report_fingerprint`. The final canonical
campaign and report bytes are retained under their fingerprints.

Trusted release composition invokes the callable already bound inside the
independently supplied `SealedConformanceGateProfile` and receives a kernel-owned
immutable `TrustedConformanceGateResult`. That carrier contains the final
canonical report bytes and an opaque issuer capability bound to the exact sealed
profile and implementation. The report's `gate` object is copied from that
profile, not from the campaign. As with the validation-bundle carrier, matching
serialized fields or a matching report fingerprint do not forge the issuer
capability.

The gate requires:

- at least one valid positive conformance instance for every registered core
  schema within that schema evaluation's exact limit;
- every required semantic campaign fixture to complete under the invocation-wide
  schema-shape cap using the exact sealed program; and
- observed per-evaluation and aggregate shape units for every case.

A registered core schema with no fitting positive instance, or a required
fixture that exceeds either bound, fails release. The semantic contribution
names its required campaign cases in the campaign artifact; prose or discovered
test files cannot add or remove cases at execution time. The campaign remains
separate from `program_fingerprint`, but its exact case set is content-addressed.

Deployment requires one `rook.validation_conformance_report:v1` from the trusted
build/release gate whose report fingerprint recomputes, whose program fingerprint
matches the artifact being deployed, whose campaign and required-case-set
fingerprints match the independently supplied campaign, whose gate profile and
implementation fingerprints match the independently supplied sealed gate
profile, and whose decision is `passed`. The release path accepts the report
only from the trusted gate result capability, not from caller-supplied report
JSON. A missing aggregate report or any `ConformanceGateInvocationFailure` is a
failed gate. A set of individually passing case rows is never a substitute.

## 8. Report-Constructability Preflight

After the validation bundle is parsed, preflight checks the fixed descriptor
shells required by the selected program's report projection. Missing or
wrong-container shells produce a typed invocation failure. Malformed content
inside present shells remains reportable companion evidence.

Preflight establishes:

- sealed program identity and exact runtime bindings;
- sealed validation-bundle assembler profile captured from the host-issued
  carrier rather than parsed bundle content;
- raw hashes for both admitted inputs;
- the complete immutable bundle and canonical fingerprint;
- either an immutable recipe or bounded recipe parse evidence for `schema`;
- fixed budget identity and the live engine-owned ledger;
- mandatory descriptor shells;
- trusted validation time and session projection.

Only this immutable `ValidationInvocation` enters the phase engine. It retains
the sealed program, sealed assembler profile, and owned artifact values, with
no caller-owned value.

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
- immutable declared phase specifications and accepted results.

It derives the program-owned report body, including phase status, `valid`,
`compile_ready`, issue ordering, and validation-context identity. The kernel
owns budget-receipt attachment and report fingerprinting. The projection never
calls a runner, rereads bytes, performs registry discovery, or reconstructs
authority from prose.

`compile_ready` is true only when `valid` is true, no compile blocker exists,
and every phase named by the projection's sealed
`required_for_compile_phases` set has status `passed`. Phase completeness is
therefore explicit program identity, not an accidental consequence of the
current DAG. A future optional phase affects readiness only when the sealed
projection deliberately includes it.

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
- the Planner recipe remains the only untrusted artifact argument, while a
  trusted host or explicit deterministic fixture assembler profile issues the
  bundle carrier; plain profile JSON and bundle content cannot forge the issuer
  capability;
- profile sealing, permitted-program checks, and permitted-clock checks reject
  an unsealed, mismatched, or wrong-kind assembler before semantic validation;
- a public endpoint cannot forward client-selected validation-bundle bytes into
  the trusted carrier path;
- input byte limit checks occur before copying or hashing, exact-limit inputs are
  accepted, and over-limit failures contain no raw-input hash;
- exact and limit-plus-one cases cover every kernel-controlled dimension;
- recipe-local parse failures become schema evidence only for local dimensions,
  while aggregate node, decoded-string, or parser-work exhaustion returns one
  combined preflight invocation failure even when it occurs during recipe parse;
- wide-shallow, deep-narrow, aggregate node/string/reference, and report-size
  amplification are bounded;
- the restricted schema profile rejects every forbidden keyword, remote or
  dynamic reference, cycle, and complexity-limit excess before evaluation;
- schema evaluator package, metaschema, profile, and core schema changes move
  the program fingerprint;
- schema-shape units conservatively couple complete schema-node count and
  admitted reference/combinator expansion to the exact evaluated instance root,
  use checked multiplication, charge repeated evaluations in full, and remain
  invariant under evaluator/reference caching;
- a combined fan-out-plus-collection boundary proves that an individually
  admissible expansion graph and an individually admissible collection cannot
  bypass the per-evaluation or invocation reservation when their product exceeds
  the sealed limit; evaluator construction remains unobserved on rejection;
- copied reservations, ledger-issued reservations for different schema factors,
  same-factor reservations replayed from another invocation ledger, genuine
  same-ledger receipts replayed for another equal-shaped schema, sibling
  instance, or pre-evaluation candidate, fabricated evaluation receipts,
  accepted over-limit rows, unjustified rejection reasons, and nonzero initial
  aggregate claims all fail before conformance publication;
- the release-owned sealed gate profile is supplied before campaign inspection,
  and changing a campaign's required profile fingerprint cannot select or alter
  the bound gate implementation;
- the gate-owned campaign byte cap accepts exactly 4,194,304 bytes, rejects
  4,194,305 before copying or hashing, and moves gate identity when changed;
- the gate-owned referenced-case-content cap applies independently to every
  resolved object, rejects its limit-plus-one before copying or hashing, and
  does not weaken the recipe/bundle caps used by fixture validation;
- every gate-wide terminal path follows the earliest-honest-result matrix:
  pre-authority/constructability failures return only
  `ConformanceGateInvocationFailure`, while constructable campaign-integrity
  failures produce a failed aggregate report with zero case rows;
- a caught post-admission gate-integrity, budget, or report-seal failure returns
  the exact typed gate invocation failure with no partial aggregate report or
  trusted result capability;
- content-resolution failures produce zero schema-attempt rows, rejected
  reservations preserve `aggregate_before_reservation` with null attempted/after
  fields, and successful reservations preserve exact nonrefunded accounting;
- semantic-fixture attempt rows come only from the kernel-issued execution-audit
  capability; report JSON, fixture claims, and lookalike audit objects cannot
  author or replace them;
- semantic phase and report-seal schema helpers reject a schema receipt whose
  reservation belongs to another invocation ledger, even when every serialized
  factor and status field matches;
- semantic phase, report-seal, and conformance projection reject a genuine
  same-ledger receipt whose private schema or subject binding differs from the
  exact source-bound schema, immutable instance and binding, or rejected
  pre-evaluation candidate being projected;
- post-issuance receipt issuer/signature or reservation issuer/origin tampering
  invalidates the enclosing receipt and audit entry transitively before any
  conformance row can be projected;
- every registered core schema has a fitting positive instance, every required
  semantic fixture fits the aggregate schema-shape cap, and the content-addressed
  campaign binds every exact program/schema/fixture/assembler-profile fingerprint;
- conformance fixtures resolve bytes and sealed assembler authority only from
  the release-supplied `TrustedConformanceFixtureContext`; serialized profile
  lookalikes cannot issue trusted bundle carriers;
- every semantic fixture row records the exact expected and actual result
  identities, and a passing row requires their complete variant-correct match;
- a passing aggregate conformance report contains exactly one matching row per
  required campaign case, while a failed report can preserve duplicate indexed
  execution evidence; extra/duplicate/mismatched rows fail completeness, and the
  aggregate report is mandatory for deployment;
- changing a schema or required fixture so that it no longer fits fails the
  release gate rather than weakening a budget;
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
- the report projection runs once before freeze through the metered body builder,
  cannot author kernel-owned fields, and all body/envelope field counts are
  charged before the budget receipt is frozen;
- fixed report-seal reservation makes repeated report fingerprints independent
  of mutable counting during serialization;
- program sealing proves the fixed allowance can cover the budget profile's
  maximum report projection and two maximum-size canonical traversals;
- report seal work/size overflow publishes no report;
- `compile_ready` remains false when any projection-owned required phase is not
  `passed`, even if no diagnostic or blocker was emitted; an explicitly optional
  synthetic phase does not affect it;
- repeated runs over identical admitted bytes, sealed program, and trusted
  context produce identical reports.

The proof suite also states its limit: in-process tests and fingerprints do not
turn trusted Python runners or the schema library into a hostile-code sandbox.

No model, worker, compiler, tool, Rhino process, Grasshopper process, or live run
is part of LM9A-Kernel.
