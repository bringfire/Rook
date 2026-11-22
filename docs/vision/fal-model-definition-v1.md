# fal model definitions, version 1

This is the closed contract for team-maintained RookVision definitions. Definitions are metadata for compiled adapters, never executable configuration. Version 1 has no imports, inheritance, expressions, HTTP headers, credentials, service hosts, DLL paths, user override directories, automatic OpenAPI import, network refresh, or hot reload. An unknown member at any object level fails admission. Object keys, IDs, enum values, field names and JSON pointers are case-sensitive.

The production manifest initially registers **no configured models**:

```json
{ "schema_version": 1, "definitions": [] }
```

Files in the source tree live beside `catalog.json` under `src/Rook/Services/Vision/Fal/Models/`. Installed files live under `<loaded companion assembly directory>/vision-models/fal/`. `FalCatalogLoader.Load(assemblyDirectory, reservedModelIds)` always uses that assembly directory; the caller supplies the directory of the loaded companion assembly, and tests inject a temporary directory. It never searches the current working directory. Subsystem initialization owns loading once; this compiler/loader does not change legacy registrations or install providers.

The manifest has exactly `schema_version: 1` and `definitions`, an array of relative JSON filenames. Empty is valid. Rooted, UNC, drive-relative, alternate-stream, parent (`..`), empty, dot, trailing-dot/space and invalid filename segments fail admission. Files must remain within the manifest root under Windows case-insensitive containment rules. Duplicate paths differing only by case fail. Reparse points (including junctions) anywhere in a referenced file's ancestry are rejected rather than followed. The manifest itself is subject to these reparse checks.

Compilation is atomic: every listed definition is validated before any snapshot is returned. A failed `FalCatalogLoadResult` contains a nonempty diagnostic list and no catalog; a successful result contains a catalog and no diagnostics. Each diagnostic includes file, JSON pointer (the root is `/`), and explanation. Missing files and invalid JSON disable configured-model admission. Legacy factories remain independently usable. No previous configured version is silently substituted.

## Admission bounds and identity

Each JSON file, including the manifest, is at most 1,048,576 bytes (1 MiB); parsing depth is at most 32. A manifest lists at most 64 definitions. A definition contains 1–16 operations; each operation contains at most 128 fields, 256 constraints, 128 constants and 16 semantic media declarations. Enum lists, membership/restriction lists and pricing rate tables contain at most 256 entries; each nonempty constraint guard contains at most 128 predicates. Exceeded bounds are diagnostics. Duplicate JSON members are rejected through `JsonDocument` before conversion to nodes can hide them.

Definition root members are exactly:

| Member | Meaning |
| --- | --- |
| `schema_version` | Required integer value `1`. |
| `definition_id` | Required unique maintainer identity. |
| `revision` | Required nonempty readable revision. |
| `model_id` | Required unique public API identity, also checked against all reserved legacy IDs across modalities. |
| `display_name` | Required plain-text label. |
| `provider` | Required literal `fal`. |
| `status` | Required `available`, `experimental` or `disabled`. |
| `operations` | Required nonempty array of explicit operation bindings. |

`definition_id`, `model_id` and endpoint IDs are at most 200 characters. Segments match `[a-z0-9][a-z0-9_.-]*`, separated by `/`; dot and parent segments are forbidden. Model identity does not imply an operation or endpoint suffix. `GetOperation(modelId, operationId)` resolves only an admitted exact pair; `TryGetOperation` supports caller validation. Snapshots retain identity, revision, source file and a SHA-256 hash of the whole definition. Constructors and JSON/list boundaries copy state; returned JSON is detached and cannot mutate the snapshot.

Canonical hashing sorts object properties ordinally, preserves array order, writes strings as JSON, and normalizes numeric lexemes without binary floating-point conversion. Equivalent spellings such as `1`, `1.0` and `1e0` hash identically; negative zero becomes zero. Nonzero numeric encoding is a signed integer coefficient without leading/trailing zeros, followed by `e` and its decimal exponent only when that exponent is nonzero. Thus `10` is encoded as `1e1`. Hashes are lowercase 64-character hex.

## Operation and adapter vocabulary

Each operation has required `operation_id`, `endpoint_id`, `invocation`, `adapter`, `fields`, `media`, `constraints`, `constants`, `result` and `evidence`; `pricing` is optional. `lifecycle_root` is required for queue invocation and forbidden for sync invocation. All arrays are explicit, including empty arrays.

| Adapter ID | Version | Operations | Invocation |
| --- | --- | --- | --- |
| `fal.image.declarative` | `1` | `text_to_image`, `image_to_image` | `sync` or `queue` |
| `fal.video.declarative` | `1` | `text_to_video`, `image_to_video`, `first_last_frame_to_video` | `queue` |

`adapter` contains exactly `id` and `version`. Unknown IDs, versions, operations, or modality mismatches fail admission. `endpoint_id` is the exact fal owner/model path, containing at least two segments; it is never a URL, host, query, fragment or percent-encoded route. `lifecycle_root` is separate metadata and must be the endpoint or its complete segment ancestor. For example, root `fal-ai/example` is valid for `fal-ai/example/frames`; `fal-ai/exam` is invalid. Nothing derives lifecycle roots by truncating or guessing endpoint paths.

## Fields and scalar values

Each field contains required `key`, `scope`, `type`, `label`, `payload`; optional `required` (default false), `default`, `description`, `ui`, and type-specific metadata below. Keys match `[a-z][a-z0-9_]*`; qualified field references are `request.<key>` or `options.<key>`.

`request` is limited to `prompt` (string), `resolution` and `aspect_ratio` (enum), `duration_seconds` (integer or number), and `seed` (integer). Provider controls, including `negative_prompt`, use `options`. Option keys cannot shadow common request keys. A key is unique in its scope. There are no undeclared arbitrary option bags, implicit defaults or implicit coercions.

| Type | Admitted JSON and metadata |
| --- | --- |
| `boolean` | JSON boolean; no numeric/string/enum metadata. |
| `integer` | Integral JSON number; required `min` and `max`, optional positive `step`. |
| `number` | Finite decimal JSON number; required `min` and `max`, optional positive `step`. |
| `string` | JSON string; required `max_length`, optional `min_length` (default 0), each 0–1,048,576 UTF-16 code units. |
| `enum` | JSON string from required nonempty unique string `values`. |

Integers must lie within **[-9007199254740991, 9007199254740991]**. Numbers have absolute value at most **1000000000** and at most **six fractional places after trailing zeros are removed**. Defaults, bounds, steps, equality/membership operands and allowed-value operands obey the same control policy. Parsing uses exact invariant decimal arithmetic and Int64 metadata; out-of-range or excess-precision lexemes are rejected before conversion can round them. `9007199254740993`, `0.1234567890123456789012345678`, nonfinite values and numeric strings are invalid controls. `0.1000000`, integral `1.0` and `1e0` are exact admitted numeric spellings. Positive steps must be representable under the control policy. Step origin is the declared minimum; defaults/operands must lie on that grid and within bounds. Required numeric bounds make that origin explicit in v1. Pricing decimal rates have a separate server-side precision policy below.

`default` must match the field type and restrictions; explicit null is never a default. Absent values and explicit null are distinct. `required` is unconditional; a required field without a default is valid because the caller supplies it. Text admitted by this format, including string defaults and labels/descriptions, contains no control characters. `ui` contains only optional `group` (`basic` or `advanced`, default `basic`), `order` (integer -1,000,000 to 1,000,000, default 0), and `hidden` (boolean, default false). Hidden/advanced controls retain validation.

`payload` contains exactly `pointer`, `conversion`, and optional `lookup`. Field conversions are `identity`, `integer_to_string` (integer controls only), and `enum_lookup` (enum controls only). An enum lookup is an object whose keys cover the declared enum choices exactly; its values are non-null scalar literals. It is forbidden for other conversions. Every field has one mapping. No field consumes data through a configurable executable policy in v1.

Scalar controls are not media source inputs. `FalScalarLiteralPolicy.IsAllowed(JsonNode)` is the reusable lexical boundary for option defaults, enum choices/operands, enum-lookup outputs and constants. It accepts non-null scalar JSON values, with ordinary type/numeric validation still required separately. String literals cannot have a URI-scheme prefix (including HTTP(S), `data:`, `file:`, `blob:` and drive prefixes), any `/` or `\` path separator, the path aliases `.`, `..`, `~`, or bare filename syntax (a name followed by a dot and a nonempty ASCII letter/alphanumeric extension beginning with a letter, optionally followed by query/fragment text). Leading/trailing spaces are ignored for locator detection; control characters are forbidden. This is a conservative syntax rule: slash-containing labels and filename-like dotted labels must use scalar labels without locator syntax. It does not inspect a field's name or destination, open files, resolve URLs, or infer provider semantics.

`request.prompt` alone is free text and may mention or equal a URL; its declared semantic purpose is a prompt, never a media transport input. Other request scalars follow the same locator boundary. Documentation/evidence URLs are metadata and are unaffected. Media source bytes/locations are represented only by declared semantic roles resolved through bounded preparation services. **The shared normalizer applies this same `FalScalarLiteralPolicy.IsAllowed` check to every submitted option value and every non-prompt request scalar before payload mapping**, including supplied values on fields with no default, in addition to field types/bounds. Admission checks defaults, enum values, lookup values and constants; runtime payload construction preserves the same scalar/media boundary.

All destination pointers are non-root RFC 6901 pointers beginning with `/`, with nonempty segments and only `~0`/`~1` escapes. Each destination has one writer across fields, media and constants. Identical pointers and any parent/child overlap fail admission. Writers are case-sensitive. Optional absent fields are omitted by the shared normalizer and pure request adapter.

`constants` is an explicit array of objects containing only `pointer` and non-null scalar `value`. Strings, booleans and exactly representable invariant decimal numbers are supported; arrays/objects, expressions and executable transforms are not. Constants use the same single-writer rules. A fixed provider output-count constant is appropriate; output cardinality remains one even if an endpoint offers a count control.

## Media roles and mappings

Each media object contains required `role`, `min_count`, `max_count`, `ordered`, `preparation`, `transport`, `payload`; optional `max_bytes`. Semantic roles are distinct from stored artifact roles. Required media uses `min_count: 1`; optional media uses 0. Bounds satisfy `0 <= min_count <= max_count <= 16`, with `max_count >= 1`.

| Operation | Semantic roles |
| --- | --- |
| `text_to_image`, `text_to_video` | No media roles. |
| `image_to_image` | Required `primary_image`; optional ordered `reference_image` list. |
| `image_to_video` | Required `primary_image`. |
| `first_last_frame_to_video` | Required `start_frame` and `end_frame`. |

Roles are unique. `primary_image`, `start_frame`, `end_frame` have `max_count: 1`, `ordered: false` and payload conversion `identity`. `reference_image` has `min_count: 0`, `ordered: true` and conversion `ordered_array`, preserving caller order. Media payloads contain only `pointer` and `conversion`; no lookup.

The only preparation profile is `validated_original`. Image operations admit transport `data_uri` or `fal_upload`; video operations admit only `fal_upload`. These names select compiled media preparation and do not authorize network calls from definitions or adapters. Inline data URIs may be produced by bounded image preparation for semantic media roles; they cannot be supplied as scalar options, enum lookup outputs or constants. Optional `max_bytes` is a positive integer at most **31,457,280 (30 MiB)**, a conservative **Rook catalog admission policy**, not a provider-limit claim. Runtime preparation must intersect it with existing runtime/provider ceilings; configuration may only tighten those ceilings. This schema does not declare automatic Fit/Fill, source framing or reference-only video qualification.

`FalMediaSnapshot.Capture` acquires admission from the shared preparation pool before making source copies. At most two admitted owners may be active or retained at once. Synchronous capture never waits for a slot: unavailable capacity produces retryable `media_preparation_busy` validation, with no copied slots. Invalid or failed captures release their partial buffers and admission. Valid snapshots retain admission until disposed, so keeping an estimate snapshot also consumes capacity. Each admitted owner has the existing 128 MiB working-memory budget; copied originals also obey the existing 64 MiB bundle ceiling, and configured video still intersects the existing 8,000,000-byte upload ceiling.

`max_bytes` is only an upper cap. Before the first upload, preparation checks the entire request against a conservative memory reservation covering copied originals, conversion copies, UTF-16 data-URI text and concatenation, JSON escaping and serialization buffers, common fields/options, and UTF-8 HTTP content. This applies to mixed CDN/data-URI requests as well. Excess encoded size returns nonretryable `media_payload_limit` before any upload. The effective data-URI limit depends on aggregate media, encoded characters, JSON escaping, controls and other retained values; there is no independent per-file size guarantee beneath the catalog cap. Use smaller sources or shorter controls when that intersection rejects a request. Configured CDN transport values must also fit Rook's enforced 4,096-character URL allowance; this is a runtime policy, not a provider-limit claim.

The snapshot caller owns its lifetime. Estimate callers dispose after deriving quote inputs and digests. Submission callers keep it through `SubmitAsync` settlement, including a returned result, queued handle or unknown-dispatch outcome, then dispose before long polling. Compatibility byte copies and the prepared values returned by `PrepareAsync` borrow that snapshot's ownership and must not outlive it. The executor separately retains its complete encoded-payload reservation through serialization, the awaited paid HTTP call and accepted-handle persistence; cancellation or early snapshot disposal does not release an in-flight payload's admission prematurely. Every settled success/failure path releases that payload reservation. Snapshots and prepared values are transient: uploaded media URLs never become persisted reusable source authority.

## Conditions and constraints

Each constraint contains exactly required `kind`, `field`, `when`, and `values` only for `allowed_values`. `field` names a declared qualified scalar field. Kinds are `required_when`, `allowed_when`, `allowed_values`, `omit_when`.

`when` is a nonempty array with implicit AND; predicates have one of these exact shapes:

- `{ "field": "options.audio", "operator": "eq", "value": true }`
- `{ "field": "request.resolution", "operator": "in", "values": ["small", "large"] }`
- `{ "role": "start_frame", "present": true }`

Every reference must exist. Operands must match the referenced type, bounds, step and enum; lists are nonempty and unique. Role predicates require a declared role and boolean `present`. There is no nesting, OR, NOT, function call or general expression. `eq` forbids `values`; `in` forbids `value`. `allowed_values` declares a nonempty unique list matching the target field. Other kinds forbid `values`.

Conditions read the default-filled value set. Multiple active restrictions intersect during request validation. `allowed_when` limits when a supplied/effective field may exist; `required_when` adds conditional requiredness. `omit_when` makes an inapplicable default inactive; an explicitly supplied inapplicable value must fail with a field error. An unconditionally required field cannot also be conditionally omitted.

Admission rejects duplicate constraints, internally contradictory AND predicates, identical-guard restrictions whose intersection is empty, and invalid default-filled states where guard truth is determinable. A default omitted by an active `omit_when` does not violate an active value restriction; simultaneous active required/omit rules are contradictory. A field without a default and optional media presence leave predicates unknown for this check. This is not a whole-domain satisfiability proof: overlapping rules may describe an unsupported caller combination; the shared request validator rejects that combination. A definition need not support every hypothetical cross product of inputs.

## Results, pricing and evidence

`result` contains required `role`, `mime_family`, `url_pointer`, optional `mime_pointer`; array results also require `collection_pointer` and `cardinality: 1`. Image adapters require `generated_image`/`image`; video adapters require `generated_video`/`video`. **All result pointers are response-root pointers**, with no implicit item-relative interpretation. A collection pointer cannot contain numeric segments. An array URL pointer must traverse exactly that declared collection at index `0`, and cannot contain another numeric segment: e.g. collection `/images`, URL `/images/0/url`. MIME can traverse that same checked collection (`/images/0/content_type`) or use scalar root metadata (`/metadata/content_type`). An additional/nested array, another collection, a nonzero/zero-padded/signed index, an append-like `-`/`+` segment or a relative `/url` spelling is invalid. Scalar-object results omit collection/cardinality members and cannot use any numeric/append-like segment in URL or MIME pointers. Numeric-key object properties and append-like object keys are deliberately unsupported in v1 to keep array semantics unambiguous. The result adapter validates the collection exists and has exactly one item **before** extracting the response-root URL/MIME pointers; an array with additional outputs fails. Every pointer also obeys the pointer grammar above. Result MIME families are allowlisted independently of URLs; bounded retrieval, byte sniffing and artifact publication are enforced by the existing materialization services.

Omitted `pricing` means **unavailable for new paid admission**, never zero or inferred cost. Explicit pricing contains required `strategy`, `unit`, `revision`, nonempty `rates`, `rounding`, `source`, `reviewed_on`, with strategy-specific members:

| Strategy | Unit | Additional members |
| --- | --- | --- |
| `fixed_per_output` | `output` | No quantity/dimension members. Quantity is one output. |
| `per_output_second` | `second` | Required `quantity_field: "request.duration_seconds"`, whose minimum is positive. |
| `per_output_megapixel` | `megapixel` | Exactly one of `dimensions` or positive decimal `max_megapixels` (conservative bound). |

`dimensions` contains exactly `field` (declared enum qualified name) and `values`, an object covering every enum choice exactly. Each value contains only positive integer `width` and `height`, each at most 65,536. No dimension inference from model names or free-form resolution strings occurs.

Each rate contains only `selectors` and `rate_usd`. Selectors map declared boolean/enum qualified fields to valid scalar choices. All rates use the same selector-key set; duplicate combinations and wildcard-overlap tables fail admission. An empty selector object means one unconditional rate. Missing combinations remain unavailable at quotation; the compiler does not invent rates or claim that every combination is priced. A rate is a nonnegative exact .NET decimal, retaining up to its representable precision (not the editable control's six-place policy). The shared decimal calculator prices normalized effective controls; quotation rounds the public USD confirmation ceiling upward to six fractional places. `rounding` is explicitly `none` or `ceil_unit`, applied to the selected quantity before multiplying by the rate.

Pricing `revision` is nonempty provenance. `source` and evidence `url` are absolute HTTPS documentation links without embedded credentials; review dates are valid `yyyy-MM-dd`. `evidence` contains only required `url`, `reviewed_on`, `qualification`; qualification is `synthetic`, `unverified` or `qualified`. Synthetic examples demonstrate syntax and are never evidence of a working provider endpoint. Qualification is maintainer evidence, not executable policy or a network refresh instruction.

## Complete synthetic examples

The following complete image and video files are test data. Their names, prices and endpoints are invented, and neither is listed in the production manifest. The format-example test parses these fenced definitions through the production compiler.

```json
        {"schema_version":1,"definition_id":"synthetic-image","revision":"revision-1","model_id":"synthetic/image","display_name":"Synthetic image","provider":"fal","status":"experimental","operations":[{
          "operation_id":"text_to_image","endpoint_id":"fal-ai/synthetic/render","invocation":"sync","adapter":{"id":"fal.image.declarative","version":1},
          "fields":[
            {"key":"prompt","scope":"request","type":"string","required":true,"max_length":1000,"label":"Prompt","description":"Plain text","ui":{"group":"basic","order":0},"payload":{"pointer":"/prompt","conversion":"identity"}},
            {"key":"audio","scope":"options","type":"boolean","default":false,"label":"Audio","payload":{"pointer":"/audio","conversion":"identity"}},
            {"key":"count","scope":"options","type":"integer","min":1,"max":3,"default":1,"label":"Count","payload":{"pointer":"/count","conversion":"integer_to_string"}},
            {"key":"seed","scope":"request","type":"integer","min":-9007199254740991,"max":9007199254740991,"step":1,"default":0,"label":"Seed","payload":{"pointer":"/seed","conversion":"identity"}},
            {"key":"strength","scope":"options","type":"number","min":0,"max":1,"step":0.1,"default":0.1,"label":"Strength","payload":{"pointer":"/strength","conversion":"identity"}},
            {"key":"resolution","scope":"request","type":"enum","values":["small","large"],"default":"small","label":"Resolution","payload":{"pointer":"/size","conversion":"enum_lookup","lookup":{"small":"S","large":"L"}}}
          ],"media":[],"constraints":[{"kind":"omit_when","field":"options.audio","when":[{"field":"request.resolution","operator":"eq","value":"small"}]}],
          "constants":[{"pointer":"/num_images","value":1}],"result":{"role":"generated_image","mime_family":"image","collection_pointer":"/images","cardinality":1,"url_pointer":"/images/0/url","mime_pointer":"/images/0/content_type"},
          "pricing":{"strategy":"fixed_per_output","unit":"output","revision":"price-1","rates":[{"selectors":{},"rate_usd":0.01}],"rounding":"none","source":"https://fal.ai/models/synthetic","reviewed_on":"2026-10-25"},
          "evidence":{"url":"https://fal.ai/models/synthetic","reviewed_on":"2026-10-25","qualification":"synthetic"}
        }]}
```

```json
        {"schema_version":1,"definition_id":"synthetic-video","revision":"revision-1","model_id":"synthetic/video","display_name":"Synthetic video","provider":"fal","status":"experimental","operations":[{
          "operation_id":"first_last_frame_to_video","endpoint_id":"fal-ai/synthetic/video/frames","lifecycle_root":"fal-ai/synthetic","invocation":"queue","adapter":{"id":"fal.video.declarative","version":1},
          "fields":[{"key":"duration_seconds","scope":"request","type":"integer","min":1,"max":10,"default":5,"label":"Seconds","payload":{"pointer":"/duration","conversion":"integer_to_string"}}],
          "media":[{"role":"start_frame","min_count":1,"max_count":1,"ordered":false,"preparation":"validated_original","transport":"fal_upload","payload":{"pointer":"/first_frame","conversion":"identity"}},{"role":"end_frame","min_count":1,"max_count":1,"ordered":false,"preparation":"validated_original","transport":"fal_upload","payload":{"pointer":"/last_frame","conversion":"identity"}}],
          "constraints":[],"constants":[],"result":{"role":"generated_video","mime_family":"video","url_pointer":"/video/url"},
          "pricing":{"strategy":"per_output_second","unit":"second","quantity_field":"request.duration_seconds","revision":"price-1","rates":[{"selectors":{},"rate_usd":0.1}],"rounding":"none","source":"https://fal.ai/models/synthetic","reviewed_on":"2026-10-25"},
          "evidence":{"url":"https://fal.ai/models/synthetic","reviewed_on":"2026-10-25","qualification":"synthetic"}
        }]}
```

## Maintainer checklist

1. Use a new stable public ID and unique definition ID; keep legacy registrations intact. Add only a relative filename to the team manifest.
2. Record the exact official submit endpoint and independent queue lifecycle root. Choose a supported adapter/version and explicit operation; do not infer suffixes.
3. Declare every common field, option, default, bound, step, enum lookup, media role and payload writer. Keep provider output count fixed at one. Check original bytes/order and tighter media limits against the existing preparation service.
4. Review finite conditions and default behavior. Test intended and invalid caller combinations through the shared normalizer, panel and MCP.
5. Declare exact supported pricing with provenance and a review date. Ensure intended configurations are priced; missing pricing/combinations must stay unavailable.
6. Record documentation and qualification evidence. A new definition does not establish Google fallback equivalence, Veo framing qualification, or permission for paid probes.
7. Compile the complete manifest and run synthetic/definition tests. Use the validation and JSON deployment procedure below, then restart Rhino.

## Normalization and pure mapping examples

`FalModelInput` keeps supplied `requestFields` and `options` separately from effective values. Its optional operation must match the already resolved binding; endpoint selection and operation inference belong to the caller resolving that binding. `OutputCount` is structural, defaults to 1, and any other value fails before a payload is built. Fixed provider constants do not repair an invalid caller count. Media inputs carry an existing artifact `MediaRef`, semantic role, and a zero-based ordinal within that role. Semantic roles are independent of stored artifact roles. Ordinals must be unique and consecutive. Configured inputs use artifact references; legacy path compatibility stays outside this contract.

For the complete synthetic image definition above, supplied request fields `{"prompt":"draw"}` and absent options normalize to:

- Effective request fields: `{"prompt":"draw","seed":0,"resolution":"small"}`.
- Effective options: `{"count":1,"strength":0.1}`.
- Inactive fields: `["options.audio"]`; its default `false` is omitted because the default-filled resolution is `small`.
- Provider payload: `{"prompt":"draw","count":"1","seed":0,"strength":0.1,"size":"S","num_images":1}`.

The raw supplied request still contains only `prompt`, and raw options remain empty. Explicit `{"audio":false}` with `small` resolution fails instead of silently dropping the caller's value. With supplied request `{"prompt":"draw","resolution":"large","seed":-9007199254740991}` and options `{"audio":false,"count":2,"strength":0.3}`, the effective options retain `audio:false`, and the payload is `{"prompt":"draw","audio":false,"count":"2","seed":-9007199254740991,"strength":0.3,"size":"L","num_images":1}`. The synthetic `count` option is a scalar conversion example; structural output count remains one independently. No real endpoint or model registration is implied.

For the complete synthetic video definition, empty common fields and artifact media bindings `start_frame:0`, `end_frame:0` normalize to `{"duration_seconds":5}`. When preparation supplies transport strings `first` and `last`, the pure adapter builds `{"duration":"5","first_frame":"first","last_frame":"last"}`. It never reads files, uploads, or derives URLs. Prepared values must match the normalized role/ordinal set exactly. Ordered reference arrays are sorted by their semantic ordinals, independently of the order in which preparation completes. Missing, duplicate or extra prepared entries fail mapping.

All conditions observe the same default-filled set, including defaults that become inactive. A nonempty `when` array is AND. Active value restrictions intersect; invalid caller combinations return field errors without changing values. `allowed_when` rejects an existing disallowed value; `omit_when` only removes an inapplicable default and never removes an explicit supplied value. Missing optional controls produce no payload writer. JSON numeric strings, explicit null, excess precision and out-of-range numbers remain invalid before any conversion. Exact numeric values survive JSON descriptor and payload serialization.

`FalDescriptorProjector.Describe(binding, validation)` publishes detached JSON with common `request_fields`, provider `options`, stable basic/advanced ordering, fully populated `required` and `ui` defaults, original scalar metadata, media, constraints, source/revision/hash, capability projections, evidence, inactive fields and field errors. Labels and descriptions are plain text. Configured images advertise `submission_contract:"image_job"`; video advertises `"video_job"`. Capability projections come from the same fields rather than a second resolution or duration matrix.

`pricing_available` indicates that pricing metadata exists. `pricing_status` distinguishes `available`, `requires_inputs`, `unavailable` and `unavailable_for_values`. Missing required selector input does not disable discovery or editing: `selectable` remains true unless the operation's model is disabled. `paid_admission_available` is only a descriptive readiness hint; disabled models, absent pricing, invalid normalized input, missing selector input, or an unmatched selected combination cannot advertise paid readiness. The shared quote/admission services enforce actual spending authorization; descriptor projection does not authorize transport or calculate prices.

Result mapping first checks the declared collection has exactly one element, then reads response-root URL/MIME pointers. For example `{"images":[{"url":"https://v3.fal.media/image.png","content_type":"image/png"}]}` becomes one URL-bodied artifact with role `image`. `{"video":{"url":"https://v3.fal.media/video.mp4"}}` becomes one role `video` artifact with no asserted MIME when the definition has no MIME pointer. Empty or multiple-output collections, malformed URL fields and an incompatible declared MIME fail with `FailedResultOutcome`; adapters do not download or publish results. Materialization services retain responsibility for bounded retrieval, byte sniffing and publication.

Legacy compatibility output is derived from each operation/media declaration: video `modes` use `t2v`, `i2v` or `interp`; image support flags reflect its operation; reference support/count reflects its declared `reference_image` role. Configured video `must_8s_with` is always empty and inherits no Veo-specific restriction. Legacy `durations` are enumerated only for a declared integer duration with Int32-representable bounds and step (default 1), at most 256 projected values, and no conditional duration restriction. Other cases expose `durations:[]` and `legacy_duration_projection_complete:false`. The 256-value limit bounds compatibility output only; it is not an additional catalog admission limit. Decimal or large canonical duration controls remain available through their original typed descriptors and the normalizer. Typed capability registration uses this same projection; the original typed controls remain authoritative for configured requests.

Pricing readiness matches rate selectors against the actual active default values during discovery, or the normalized effective values during validation; a default combination missing from a partial rate table is `unavailable_for_values`. Inactive defaults are excluded using the normalizer's same default-filled condition semantics. For discovery, required media roles are structurally present and optional roles have no default presence. Per-second pricing also requires its active quantity control; dimension-mapped megapixel pricing requires its active dimension control. Missing strategy inputs produce `requires_inputs` and preserve `selectable:true`; conservative `max_megapixels` pricing needs no dimension control. This only determines descriptor state and never computes a price or authorizes paid admission.

## Quotes and precise pricing provenance

Configured estimate and submit use the same normalizer and decimal pricing calculator. Estimate returns `quote_fingerprint` and numeric `max_estimated_cost_usd`. Submit requires that fingerprint and a numeric cap at least as large as the quoted upper bound. The fingerprint binds the definition/revision/hash, effective common fields and options, prepared media content digests, operation, and selected pricing. Changing any of them requires a fresh quote. The public cap is a nonnegative USD ceiling, rounded upward to six fractional places and at most 1,000,000,000; it is a confirmation ceiling, not a report of actual spend. `actual_usd` remains null without qualified billing evidence. Legacy submission contracts stay intact.

Catalog `rate_usd` and internal pricing snapshots retain exact .NET decimal JSON numbers. Do not round catalog rates to satisfy the editable-control policy. Public descriptor, quote and history pricing provenance projects a decimal to plain invariant decimal text when its absolute value exceeds 1,000,000,000 or it needs more than six fractional places. Other pricing values remain JSON numbers. This text projection is display/provenance only: it is never accepted as a numeric caller control or cost cap. User controls retain their declared JSON types, safe integer limits and six-place numeric policy.

## Build, validate and deploy external catalogs

The managed project includes one recursive JSON glob from `Services/Vision/Fal/Models/` into `vision-models/fal/` beside each runtime's `Rook.rhp`. Full local deployment and the installer include that directory for `net48`, `net7.0` and `net8.0`. Adding an endpoint requires no endpoint-specific build or installer line. The intentionally empty `catalog.json` is a complete valid package. Keep the output directories clean when removing definitions: release validation rejects extra, missing or changed JSON by source/package hash parity. The existing `-ManagedOnly` local deployment still replaces only `Rook.rhp` and available `Rook.pdb`; use the separate catalog copier for data changes.

Build the qualification host against the candidate runtime, without incidental installed deployment:

```powershell
dotnet build src/Rook.Vision.Qualification/Rook.Vision.Qualification.csproj -c Debug -f net48 -p:RhinoPluginDir=
src/Rook.Vision.Qualification/bin/Debug/net48/Rook.Vision.Qualification.exe validate-catalog --root src/Rook/Services/Vision/Fal/Models --report artifacts/fal-catalog-validation.json
```

`--root` is the actual catalog directory containing `catalog.json`, not the companion assembly directory. The CLI calls the production `FalCatalogCompiler` with `VisionProviderRegistrations.GetLegacyModelIds()`, including the real legacy aliases. It uses no separate schema and reads no credentials. Exit 0 admits the complete catalog; nonzero means failure. The report records file/pointer diagnostics, canonical definition hashes and SHA256 hashes of all recursively included JSON. Write reports outside the catalog directory. The host also targets net7.0/net8.0 and mirrors the companion to `Rook.dll` only inside its own tooling output, following the framing qualifier pattern.

Release validation requires the built Release/net48 qualifier by default, or an explicit `-VisionCatalogValidatorPath` pointing to the frozen host. It semantically validates the source and all three packaged runtime catalogs, checks the full relative JSON file set and raw SHA256 parity with source, and records `vision_catalogs` in the release manifest. Compiler validation checks manifest references, not merely directory presence. Build the Release qualifier with the same command using `-c Release`; keep the host and its companion/dependencies together.

For a JSON-only update, retain the frozen qualifier and record the runtime/code hashes before editing definitions. Validate the edited catalog, close Rhino, and run:

```powershell
powershell -NoProfile -File scripts/deploy-vision-model-catalog.ps1 -CatalogRoot "C:\candidate\vision-models\fal" -PluginRoot "$env:APPDATA\McNeel\Rhinoceros\8.0\Plug-ins\RookNative" -ValidatorPath "C:\frozen-tools\Rook.Vision.Qualification.exe"
```

The copier requires all three installed runtime directories and Rhino stopped. It validates before replacing anything, rejects overlapping roots and reparse paths, stages generic JSON in sibling directories, validates and hashes every stage, and then replaces each runtime catalog. Installed non-JSON catalog files cause rejection. On failure it restores each previous catalog, including restoring absence on a first deployment. It verifies the complete relative file/hash manifest of every unrelated payload, including native/managed assemblies, symbols, dependency metadata, UI and Python files within the selected plugin root. Any drift fails the proof and rolls catalogs back; unrelated concurrent edits are reported, not repaired. The returned receipt includes before/after manifests, catalog hashes and the restart requirement. It never builds, closes Rhino, changes secrets or regenerates installed artifacts.

Restart Rhino after a successful copy. Loading occurs once at subsystem initialization; there is no hot reload. Ordinary exception failures roll back. Abrupt process termination, power loss or a filesystem that refuses restoration require operator recovery from the retained sibling backup directories before starting Rhino; the script reports restoration failures and preserves those backups. Keep the installation idle throughout the transaction.

Deterministic copier tests use temporary directories and injected process/validator probes. To additionally exercise real compiler admission, missing references, legacy collisions and package hashes without installing anything:

```powershell
powershell -NoProfile -File scripts/tests/deploy-vision-model-catalog.tests.ps1 -QualificationPath src/Rook.Vision.Qualification/bin/Debug/net48/Rook.Vision.Qualification.exe
powershell -NoProfile -File scripts/tests/validate-release-artifacts.tests.ps1 -CatalogOnly -QualificationPath src/Rook.Vision.Qualification/bin/Debug/net48/Rook.Vision.Qualification.exe
```

These focused checks do not replace full release payload validation, installed restart checks or paid acceptance. Select held-out image/video endpoints only after the runtime and generic harness freeze. Acceptance additions may change only definition JSON and manifest entries; live runs still require a maintainer-selected spend cap.
