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

`request.prompt` alone is free text and may mention or equal a URL; its declared semantic purpose is a prompt, never a media transport input. Other request scalars follow the same locator boundary. Documentation/evidence URLs are metadata and are unaffected. Media source bytes/locations are represented only by declared semantic roles resolved through bounded preparation services. **Task 2 normalization must apply this same `FalScalarLiteralPolicy.IsAllowed` check to every submitted option value and every non-prompt request scalar before payload mapping**, including supplied values on fields with no default, in addition to field types/bounds. Defaults and enum/lookup/constants are checked now; runtime payload construction must not interpret ordinary scalar text as media or bypass prepared roles.

All destination pointers are non-root RFC 6901 pointers beginning with `/`, with nonempty segments and only `~0`/`~1` escapes. Each destination has one writer across fields, media and constants. Identical pointers and any parent/child overlap fail admission. Writers are case-sensitive. Optional absent fields are omitted by later request construction; this task declares mappings and does not execute them.

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

The only preparation profile is `validated_original`. Image operations admit transport `data_uri` or `fal_upload`; video operations admit only `fal_upload`. These names select future compiled media services and do not authorize network calls from definitions or adapters. Inline data URIs may be produced by bounded image preparation for semantic media roles; they cannot be supplied as scalar options, enum lookup outputs or constants. Optional `max_bytes` is a positive integer at most **31,457,280 (30 MiB)**, a conservative **Rook catalog admission policy**, not a provider-limit claim. Runtime preparation must intersect it with existing runtime/provider ceilings; configuration may only tighten those ceilings. This schema does not declare automatic Fit/Fill, source framing or reference-only video qualification.

## Conditions and constraints

Each constraint contains exactly required `kind`, `field`, `when`, and `values` only for `allowed_values`. `field` names a declared qualified scalar field. Kinds are `required_when`, `allowed_when`, `allowed_values`, `omit_when`.

`when` is a nonempty array with implicit AND; predicates have one of these exact shapes:

- `{ "field": "options.audio", "operator": "eq", "value": true }`
- `{ "field": "request.resolution", "operator": "in", "values": ["small", "large"] }`
- `{ "role": "start_frame", "present": true }`

Every reference must exist. Operands must match the referenced type, bounds, step and enum; lists are nonempty and unique. Role predicates require a declared role and boolean `present`. There is no nesting, OR, NOT, function call or general expression. `eq` forbids `values`; `in` forbids `value`. `allowed_values` declares a nonempty unique list matching the target field. Other kinds forbid `values`.

Conditions read the default-filled value set. Multiple active restrictions intersect during request validation. `allowed_when` limits when a supplied/effective field may exist; `required_when` adds conditional requiredness. `omit_when` makes an inapplicable default inactive; an explicitly supplied inapplicable value must fail with a field error. An unconditionally required field cannot also be conditionally omitted.

Admission rejects duplicate constraints, internally contradictory AND predicates, identical-guard restrictions whose intersection is empty, and invalid default-filled states where guard truth is determinable. A default omitted by an active `omit_when` does not violate an active value restriction; simultaneous active required/omit rules are contradictory. A field without a default and optional media presence leave predicates unknown for this check. This is not a whole-domain satisfiability proof: overlapping rules may describe an unsupported caller combination; Task 2 request validation rejects that combination. A definition need not support every hypothetical cross product of inputs.

## Results, pricing and evidence

`result` contains required `role`, `mime_family`, `url_pointer`, optional `mime_pointer`; array results also require `collection_pointer` and `cardinality: 1`. Image adapters require `generated_image`/`image`; video adapters require `generated_video`/`video`. **All result pointers are response-root pointers**, with no implicit item-relative interpretation. A collection pointer cannot contain numeric segments. An array URL pointer must traverse exactly that declared collection at index `0`, and cannot contain another numeric segment: e.g. collection `/images`, URL `/images/0/url`. MIME can traverse that same checked collection (`/images/0/content_type`) or use scalar root metadata (`/metadata/content_type`). An additional/nested array, another collection, a nonzero/zero-padded/signed index, an append-like `-`/`+` segment or a relative `/url` spelling is invalid. Scalar-object results omit collection/cardinality members and cannot use any numeric/append-like segment in URL or MIME pointers. Numeric-key object properties and append-like object keys are deliberately unsupported in v1 to keep array semantics unambiguous. The later result adapter must validate the collection exists and has exactly one item **before** extracting the response-root URL/MIME pointers; an array with additional outputs must fail. Every pointer also obeys the pointer grammar above. Result MIME families are allowlisted independently of URLs; result translation/download safety belongs to later services.

Omitted `pricing` means **unavailable for new paid admission**, never zero or inferred cost. Explicit pricing contains required `strategy`, `unit`, `revision`, nonempty `rates`, `rounding`, `source`, `reviewed_on`, with strategy-specific members:

| Strategy | Unit | Additional members |
| --- | --- | --- |
| `fixed_per_output` | `output` | No quantity/dimension members. Quantity is one output. |
| `per_output_second` | `second` | Required `quantity_field: "request.duration_seconds"`, whose minimum is positive. |
| `per_output_megapixel` | `megapixel` | Exactly one of `dimensions` or positive decimal `max_megapixels` (conservative bound). |

`dimensions` contains exactly `field` (declared enum qualified name) and `values`, an object covering every enum choice exactly. Each value contains only positive integer `width` and `height`, each at most 65,536. No dimension inference from model names or free-form resolution strings occurs.

Each rate contains only `selectors` and `rate_usd`. Selectors map declared boolean/enum qualified fields to valid scalar choices. All rates use the same selector-key set; duplicate combinations and wildcard-overlap tables fail admission. An empty selector object means one unconditional rate. Missing combinations remain unavailable at quotation; the compiler does not invent rates or claim that every combination is priced. A rate is a nonnegative exact .NET decimal, retaining up to its representable precision (not the editable control's six-place policy). Pricing arithmetic and outward six-place USD ceiling rounding are later tasks. `rounding` is explicitly `none` or `ceil_unit`, applied to the selected quantity before multiplying by the rate.

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
4. Review finite conditions and default behavior. Test intended and invalid caller combinations through the shared normalizer when it is available.
5. Declare exact supported pricing with provenance and a review date. Ensure intended configurations are priced; missing pricing/combinations must stay unavailable.
6. Record documentation and qualification evidence. A new definition does not establish Google fallback equivalence, Veo framing qualification, or permission for paid probes.
7. Compile the complete manifest and run synthetic/definition tests. Deploy JSON alongside each managed runtime through the later packaging workflow and restart Rhino. This document does not implement packaging, submission, downloads or transport.
