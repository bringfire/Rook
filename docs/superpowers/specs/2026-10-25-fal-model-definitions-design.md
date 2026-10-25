# RookVision fal model definitions and adapters

Date: 2026-10-25

Status: Approved by the user on 2026-10-25. Detailed implementation planning authorized; runtime implementation has not started.

Source baseline: `807bfed4` in `C:/UDEV/Rook`.

Builder review: a fresh read-only reviewer reported no material unanswered planning questions on 2026-10-25. Human design approval received on 2026-10-25.

## 1. Intent and accepted requirements

RookVision should accept new fal image and video endpoints and expose their controls without repeated changes to shared execution code. Model definitions are maintained by the Rook team initially. The architecture leaves a future path for user-maintained definitions.

The user selected the hybrid approach: declarative definitions for ordinary endpoint differences, with reusable compiled adapters for behavior the definition format cannot express.

The user set the first release acceptance test: add **one new image endpoint and one new video endpoint**, with their controls usable through **both the RookVision UI and MCP**, using **configuration changes only**. The runtime must be frozen before those additions. Merely listing a model, rendering controls, or accepting an ignored options object does not pass.

The detailed boundaries and scope below are the approved engineering interpretation of these requirements.

## 2. Approaches and decision

| Approach | Benefit | Tradeoff |
| --- | --- | --- |
| A compiled module for every model | Local implementation changes and unrestricted model behavior | Every endpoint still requires code and a build |
| An unrestricted schema interpreter | Broad automatic field exposure | Media semantics, lifecycle differences, and complex workflows turn configuration into a programming language |
| Definitions with reusable adapters | Routine differences are data; exceptional behavior has an explicit extension point | Coverage is bounded by the adapters, mappings, and workflows shipped in a runtime version |

The hybrid approach was selected because it meets the configuration-only acceptance test while keeping execution behavior testable. The intended promise is: **a compatible endpoint needs a definition, not a shared-code edit**. Adding a new workflow primitive can require a runtime release; subsequent models using that primitive can be configured.

## 3. First release scope

Support the existing single-result image and video workflows: text-to-image, image editing with an optional ordered reference set, text-to-video, image-to-video, and generation between first and last frames. Reference-only video generation remains a separately qualified operation; it is not enabled merely because an endpoint schema contains a reference field.

Support boolean, integer, decimal number, string, and string-enum controls, bounded conditional constraints, scalar field mappings, ordered media mappings, and a single primary image or MP4 result. Image invocation can be synchronous or queued. Configured video invocation uses the queue. All newly configured image models use the existing asynchronous image-job experience in Rook, even when their provider invocation is synchronous.

Include model discovery, control rendering, MCP submission, validation, cost estimates, normal job management, artifact metadata, catalog packaging, and a generic acceptance harness.

Use the current FLUX Schnell and Kling v3 Standard payload/lifecycle fixtures as reference cases for synchronous image generation and queued video generation with uploaded frames. Exercise the new executor under test-only synthetic identities; do not replace these public registrations in the first release. Queue-backed image execution is also exercised with synthetic protocol fixtures before the runtime is frozen. The two acceptance endpoints become the first new production definitions. Current providers and fal models retain their existing implementation and public contracts.

Out of scope: user-authored catalogs in the product, automatic OpenAPI import, arbitrary nested control editors, mask drawing, motion-path editors, video-to-video, draft completion, streaming inference, model training, multiple generated outputs per request, reconstruction migration, and redesign of Google-to-fal fallback. Existing Google fallback and framing contracts remain applicable to their current models.

## 4. Current code and required integration work

The implementation already has useful boundaries:

- `Generation/IProviderOptionsCodec.cs` and `IPricingModel.cs` attach validation and pricing to resolved models.
- `Image/DefaultImageProviderRegistry.cs` and `Video/DefaultVideoProviderRegistry.cs` resolve models from registrations.
- `Fal/FalApiClient.cs` supplies HTTP and upload transport.
- Existing managers own jobs, artifacts, cancellation, and publication.
- `ReconstructionModelCatalog.cs`, its option validator, and the reconstruction panel already provide a local precedent for JSON input and control descriptors. Reuse the vocabulary and suitable small helpers without merging reconstruction into this project.

The first release must remove these obstacles for configured models:

- `FalImageProvider.cs` and `FalVideoProvider.cs` dispatch through explicit model-ID branches.
- `VisionHandler.BuildImageGenerationWorkItem` calls the options codec with an empty object. Image options cannot currently flow from a caller.
- The panel does not render general image/video option descriptors; fal video submission builds an empty options object.
- `rhino_render_view` has a legacy image contract requiring a source path, with no model-options property. Image model discovery and image job operations currently exist in the managed panel path but are not exposed as equivalent native/MCP routes.
- Video quote/framing/fallback selection contains model-specific decisions. Configured direct-fal execution needs a general contract alongside that existing routing path.
- Image ledgers currently lack a complete durable binding and options snapshot. Some video recovery depends on resolving the current catalog.

These are one-time infrastructure changes in the implementation project. The acceptance additions happen only after they are complete.

## 5. Ownership boundaries

| Component | Owns | Must delegate |
| --- | --- | --- |
| Definition | Model identity, operation bindings, scalar controls, input roles, constraints, field mappings, output mapping, pricing data, documentation evidence | Network calls, executable transforms, credentials, job state |
| Catalog compiler | Load validation, duplicate detection, semantic validation, immutable resolved definitions, compatibility projections | Paid calls and inference about missing model semantics |
| Model adapter | Pure request/result translation and operation-specific validation; selection of supported preparation instructions | HTTP, retries, credentials, file access, job persistence, UI rendering |
| Fal executor and transport | Shared synchronous/queue protocol, validated lifecycle handles, uploads through approved services, provider-error normalization | Model-ID-specific dispatch, arbitrary payload options, publication |
| Rook managers and services | Media resolution, execution admission, deadlines, cost confirmation, cancellation, persistence, artifact publication | Decisions based on individual configured model IDs |
| UI and MCP adapters | Present published descriptors and submit typed values | Independent defaults, endpoint selection, pricing arithmetic |

The generic image/video provider wrappers implement the existing provider interfaces and use an immutable resolved operation binding. Their adapter selection uses a compiled adapter ID and version, not a chain of model-name checks. The per-model codec and pricing strategy can be supplied through separate registrations with the same provider name; registration names need not imply shared codecs.

Adapters are a small compiled catalog selected by ID. The initial declarative image and video adapters share mapping helpers and the fal executor. A specialized adapter may add a pure validator or translation that the finite mapping vocabulary cannot express. It must satisfy the same job, pricing, media, and publication contracts. A future multi-stage workflow is a new workflow capability, not permission for an adapter to start independent jobs behind the manager.

## 6. Logical model and operation bindings

A definition describes one logical public model with one or more explicit operation bindings. A binding names the exact fal submit endpoint. It does not derive endpoint paths by concatenating guessed suffixes.

For example, a logical image model may bind `text_to_image` and `image_to_image` to different fal endpoints. A video model may bind `image_to_video` and `first_last_frame_to_video` to the same submit endpoint with different required roles.

The public `model_id` remains the stable API identity. Each binding has an `operation_id`, exact endpoint ID, protocol mode, adapter ID/version, and independent controls/constraints. Shared file fragments or inheritance are deferred; explicit definitions are easier to review initially.

New requests may name the operation explicitly. Image calls infer it from the presence of the primary input image when unambiguous, and existing video modes map to the corresponding operation. Ambiguous requests fail before upload. Existing model IDs and short-name compatibility remain intact. A configured model cannot replace a legacy registered model accidentally. A future migration must remove the exact legacy registration in the same runtime release; version one makes no such replacements.

## 7. Definition format

Use JSON and the existing `System.Text.Json` dependency. Implement a documented, closed format with bounded validation; do not add a general JSON Schema or YAML dependency. Fal OpenAPI can later generate drafts of this format, but it is not a runtime authority in version one.

| Field group | Required meaning |
| --- | --- |
| `schema_version` | Definition-format version; initially 1 |
| `definition_id`, `revision` | Maintainer identity and readable revision; canonical content hash is computed by the loader |
| `model_id`, `display_name`, `provider`, `status` | Stable public ID, label, `fal`, and available/experimental/disabled state |
| `operations` | Explicit bindings with `operation_id`, `endpoint_id`, `invocation`, and `adapter` |
| `fields` | Canonical common fields and provider-specific options, including type, bounds, defaults, UI metadata, and payload mapping |
| `media` | Required/optional semantic roles, ordering/cardinality, source preparation and transport profile, destination fields |
| `constraints` | Finite cross-field and media-presence rules |
| `constants` | Fixed provider values; cannot collide with mapped controls |
| `result` | Primary artifact role, expected MIME family, and JSON-pointer paths for URL and optional MIME |
| `pricing` | Supported strategy, rates, selectors, rounding rule when applicable, provenance, and review date |
| `evidence` | Official documentation URL, review date, and maintainer qualification status |

The format exposes only behavior implemented by the named adapter and schema version. Unknown fields, unknown enum values, unsupported adapters, conflicting destinations, invalid defaults, duplicate operations, and inconsistent constraints fail definition admission. A definition cannot configure arbitrary HTTP headers, credential material, executable code, DLL paths, shell commands, or service hosts.

### Field example

This is an illustrative fragment, not a registered model or an assertion about a specific fal endpoint:

```json
{
  "key": "generate_audio",
  "scope": "options",
  "type": "boolean",
  "default": false,
  "label": "Generate audio",
  "description": "Include generated audio in the video.",
  "ui": { "group": "basic", "order": 30 },
  "payload": { "pointer": "/generate_audio", "conversion": "identity" }
}
```

Common fields use `scope: "request"` and existing names such as `prompt`, `resolution`, `aspect_ratio`, `duration_seconds`, and `seed`. Provider-specific controls use `scope: "options"`. Keys cannot shadow common fields. Definitions are the single source for both these fields and the legacy capability projection; do not maintain a second independent duration/resolution matrix.

## 8. Validation and mapping semantics

Apply the same normalization pipeline for UI, MCP, estimate, and submission:

1. Resolve a model and operation from one immutable catalog snapshot.
2. Validate supplied keys and JSON types. Explicit null is invalid unless a future schema version supports it; absence and null are distinct.
3. Fill declared defaults for absent values. Preserve the originally supplied values separately from the effective values.
4. Apply constraints against that effective value set and media-role presence.
5. Produce the effective options, selected media instructions, pricing inputs, and payload mapping plan together.

First-release types are boolean, signed integer with explicit bounds, finite decimal number with bounds/step, bounded string, and string enum. Following the 2026-10-25 implementation-plan review, v1 user-facing integers are restricted to the JavaScript safe-integer range [-9007199254740991, 9007199254740991]; number controls have absolute value at most 1000000000 and at most six fractional decimal places after removing trailing zeros. Defaults, bounds, steps, condition operands, and submitted common fields/options follow the same policy. Labels/descriptions are plain text. Boolean strings and numeric strings are not implicitly coerced. The panel validates raw input text before numeric conversion; admitted values travel as ordinary JSON numbers without loss. Values needing greater range/precision require a future format change. `step` is both a validation rule and a UI hint; define its origin as `min` when supplied, otherwise zero. All numeric calculation uses deterministic invariant-culture decimal arithmetic. Internal pricing rates/calculation retain .NET decimal precision; the public confirmation ceiling rounds upward to six fractional USD places, while precise pricing provenance is serialized as decimal text where needed.

Supported constraints are `required_when`, `allowed_when`, conditional `allowed_values`, and `omit_when`, using equality or membership tests over declared scalar fields and role-presence predicates. Conditions read the default-filled values; they do not mutate other fields. Multiple active restrictions intersect. Contradictory combinations fail. Conditions cannot call functions or evaluate arbitrary expressions.

For `omit_when`, explicit user values that become inapplicable fail with a field-specific explanation. An inapplicable default is omitted from the effective payload and exposed as inactive in discovery/validation output. This prevents a submitted value from being silently discarded. Hidden or advanced controls are still validated.

Payload construction supports explicit JSON pointers, literal constants, identity mapping, integer-to-string conversion, declared enum lookup, and ordered media-array construction. Each destination has exactly one writer. No template expressions or general scripting. Optional absent values are omitted. The runtime verifies all accepted options are either mapped or explicitly consumed by a named built-in policy.

## 9. Media and result boundaries

Media uses semantic roles: primary image, ordered reference images, start frame, and end frame. The definition maps these roles to provider field names and cardinality. A provider option cannot smuggle a URL or local path past the media resolver. New image APIs use artifact ID plus role; the existing path-based image tool remains a compatibility entry point using current path validation.

Reuse the current bounded readers, MIME detection, immutable media snapshots, upload transport, and frame validation. Definition limits may tighten runtime ceilings. They cannot relax process resource limits or choose executable paths. Initial preparation profiles support validated original still images and existing explicitly qualified preparation behaviors; a new model does not automatically inherit the Veo Fit/Fill profile.

The definition selects `data_uri` or fal CDN upload only where supported by the operation profile. The executor materializes media after validation and quote checks. The adapter receives prepared media values rather than reading files itself. Ordered references retain their order through UI, MCP, preparation, and payload construction.

Result mapping uses JSON pointers such as `/images/0/url` or `/video/url` and normalizes into the existing `ProviderResultEnvelope`. A configured operation produces exactly one primary result with role `image` or `video`. Array mappings require cardinality one; additional generated results are an error, not silent truncation. MIME/type validation, bounded download, and artifact publication stay in existing services. Provider completion is not generation success until the result response is validated.

## 10. Execution and persistence

Synchronous image calls and queue-backed calls share normal Rook job ownership. Queued requests use the status/result/cancel URLs returned by fal, validated against the expected service and declared lifecycle root. The submit endpoint and lifecycle root are separate binding fields. No generic helper assumes that appending `/requests` to a full submit endpoint is correct.

Compiled execution profiles preserve current deadlines, stop/publication fences, and request-outcome handling. The new configured path records dispatch intent before the paid submission, records accepted provider IDs durably, and treats a lost response after dispatch as an unknown submission. Unknown submissions are never automatically replayed. Poll retries cannot trigger a fresh submission. Cancellation reports local stop and remote cancellation separately where the provider outcome differs.

At estimate time capture the definition hash, operation binding, adapter version, effective controls, media identities/digests, and pricing revision. At submit time verify the accepted quote against the same information. At job creation pin an immutable execution binding. Persist the minimum sufficient snapshot for the permitted later operations, including validated provider handle, controls, binding identifiers/hash, result mapping, pricing snapshot, and media provenance. Do not persist credentials or temporary uploaded-media URLs as reusable source authority.

Existing ledgers remain readable. Video can use a versioned extension. Image requires an additive durable execution record and compatible reader/writer work; its current fields are insufficient. A snapshot version that cannot be interpreted must not silently resolve to the latest model definition.

Preserve current restart semantics: interrupted jobs are not automatically resumed or resubmitted. The snapshot supports accurate history and permitted explicit remote cleanup after reload. Removing or changing a catalog entry must not cause an old job to use the replacement endpoint. A definition hash freezes Rook's configuration, not a remote model's weights or future provider behavior.

## 11. Pricing and confirmation

Configured models use a shared declarative pricing implementation selected by strategy: fixed per output, per output-second, or per output-megapixel. A finite rate table may select rates by declared values such as resolution and audio. Units and rounding are explicit. Megapixel quantities require a declared dimension mapping or a conservative bounded estimate; no inferred rate from the model name.

Every supported configuration must yield an exact estimate or a bounded range with a source/revision. Missing rates or unsupported combinations make that operation unavailable for new paid work. Unknown cost is not represented as zero. The first-release acceptance endpoints must use supported pricing strategies.

New configured image and video submission paths accept a quote fingerprint and maximum estimated cost. The panel displays the quote and submits those values on generation; MCP uses estimate then submit. This contract is additive for configured models and does not silently change existing legacy tool requirements. The fingerprint includes effective controls and binding/pricing revisions; changing an audio toggle or model definition requires a new quote.

Generalize the current quote projection for direct configured models without inventing Google fallback candidates. Preserve the existing routed quote behavior for Google/Veo. Replace concrete pricing-class classification for configured models with declared unit metadata. Retain decimal quantities for calculations and durable generic pricing; do not truncate them through the legacy video integer-quantity representation. Existing legacy fields can remain as compatibility projections where their units are representable.

Actual spend remains distinct from estimates. A compiled metadata strategy may interpret fal billable-unit headers using the selected rate contract. Absence of actual billing evidence remains unknown actual spend and does not retroactively label an estimate as an invoice.

## 12. Catalog loading and distribution

Repository definitions live under `src/Rook/Services/Vision/Fal/Models/`. Package external JSON alongside each managed runtime under `vision-models/fal/`, with `catalog.json` listing relative definition filenames. Use the loaded companion assembly's directory as the installed root, not the current working directory. Allow a test-only injected root. Version one has no user override search path or automatic network refresh.

Load once at subsystem initialization. An operator can deploy changed JSON and restart Rhino without rebuilding Rook. Hot reload is deferred. The catalog is one validated immutable snapshot. Invalid managed catalogs disable configured-model admission with actionable file/field diagnostics; legacy providers remain usable. Do not partially activate an invalid catalog or silently fall back to an older definition for the same configured ID.

Validate the whole catalog in CI and package verification. Definition hashes use canonical JSON with stable key ordering and normalized number encoding. Duplicate IDs against either configured or legacy models fail admission. A manifest cannot reference outside its packaged root.

Add generic JSON-directory inclusion to managed build output, local deployment, and installer payload validation once. The two acceptance additions may change JSON files and the JSON catalog manifest only. Deployment can copy those files and restart Rhino; it must not rebuild or replace DLLs, JavaScript, Python, native binaries, or adapter assemblies.

Expose catalog source and definition identity in descriptors. This provides a future extension point for a separate user catalog with its own admission and collision policy. Do not activate that policy in the first release.

## 13. UI and MCP contract

Publish one operation descriptor containing fields, options, constraints, media roles, capability projections, pricing availability, definition revision/hash, and validation errors. The panel and MCP read the same managed result. Stable top-level MCP schemas accept an `options` object; model-specific keys are discovered from descriptors and validated by the managed service. Do not regenerate the MCP tool inventory per model.

The panel keeps existing common controls and adds a reusable option renderer for the supported scalar types. For configured models, common-control visibility, types, defaults and requiredness come from the operation descriptor; legacy dropdown defaults must not become supplied configured values. Omitted/defaulted common fields must work through both panel and MCP capability gateway. Shared video outer schemas require only model; mode, duration, resolution, aspect ratio and options are optional at that outer boundary, with configured definition requirements and existing legacy requirements enforced in managed code. Use basic and advanced groups with stable ordering. Model/operation changes clear incompatible values; revision changes invalidate cached descriptors and estimates. Do not carry a value to another model just because its label matches. Invalid combinations receive field-specific explanations. UI tests must verify serialization and provider payloads, including numeric round trips, not only visible labels.

Add generic image model/job/estimate routes through the existing native Vision dispatch callback, plus their MCP tools:

| MCP tool | Native route | Managed responsibility |
| --- | --- | --- |
| `rhino_image_models` | `GET /vision/image/models` | Image descriptor discovery |
| `rhino_image_estimate` | `POST /vision/image/estimate` | Configured image quote |
| `rhino_generate_image` | `POST /vision/image/jobs` | Submit through `ImageJobOpHandler` |
| `rhino_image_status` | `GET /vision/image/jobs/{job_id}` | Existing image job status |
| `rhino_image_result` | `GET /vision/image/jobs/{job_id}/result` | Existing image artifact result |
| `rhino_image_cancel` | `POST /vision/image/jobs/{job_id}/cancel` | Existing image cancellation |
| `rhino_image_jobs` | `GET /vision/image/jobs` | Existing image job history |

Use existing managed operation discriminators where available (`image_generate_start`, `image_job_status`, `image_job_result`, `image_job_cancel`, `image_jobs`). Extend the callback's explicit operation admission/routing to those handlers with their existing async/off-UI split. Native handlers remain thin; no new server or callback ABI is needed. This is an explicit native/managed dependency in the first runtime release.

Keep `rhino_render_view` and its current response shape for compatibility. New configured models are driven through the new image-job contract; the legacy synchronous image entry point must return an explicit handoff for registered configured models, never silently substitute a Gemini model. Both image entry points reject all unresolved model IDs after recognized legacy alias resolution, including IDs removed from the catalog or unavailable because a catalog is missing/invalid. Do not synthesize a Gemini binding for an arbitrary unknown ID; rejection precedes media preparation, secret lookup and provider calls. Persisted-job cleanup remains independent of catalog admission. The panel chooses the job path from descriptor metadata. Existing video model/estimate/submit/status/result/cancel tools carry the enriched descriptors and validated options without adding one tool per model. Update descriptions to distinguish legacy and configured paths and remove stale provider-only wording where touched.

The new generation tool accepts model/operation, prompt and common fields as applicable, an options object, artifact media references, and quote confirmation. Required fields are resolved from the operation rather than globally requiring an image or prompt for every model. Native route tests, Python forwarding/schema tests, live capability declarations, tool profiles, and authoritative count contracts change together. Discovery/status/result/history/estimate remain read-only; submit and cancel follow existing mutation classifications. Follow the established profile admission policy rather than putting every tool in every profile.

## 14. Migration and compatibility

Introduce the configured path alongside existing integrations. Keep all existing public registrations, including FLUX Schnell and Kling v3 Standard, in their current implementations for this release. Their wire fixtures supply reference cases for the new executor. Deferred migration of existing public IDs requires payload, media, lifecycle, pricing, entry-point, and result parity tests plus an explicit cutover; remove the old registration only at that cutover.

Registrations that share provider name `fal` cannot rely on first-registration-wins recovery for configured jobs. Running and persisted configured jobs use their pinned binding and handle. Legacy recovery retains its current behavior. Factory construction and generic dispatch need one-time changes to make that distinction explicit.

Do not route new definitions through the existing Nano Banana or Veo hard-coded fallback maps. Fallback equivalence and source-framing qualification remain explicit existing policy. A schema declaring compatible fields does not establish semantic fallback equivalence.

Reference tests compare representative existing wire contracts against declarative execution, including defaults, invalid combinations, media order, cancellation, dispatch uncertainty, and output artifact roles. This demonstrates reusable behavior without changing old clients' submission/confirmation requirements. Any later intentional behavior change requires a documented design update rather than being hidden inside a migration.

## 15. Acceptance protocol

### Freeze and additions

1. Complete the runtime, generic test harness, descriptor consumers, package rules, and reference conformance fixtures. Record the runtime commit and hashes of deployed native, managed, JavaScript, and Python artifacts.
2. Select one image endpoint and one video endpoint absent from the shipped catalog and compiled model branches. Select them after the runtime freeze from officially documented endpoints compatible with the declared version-one workflows and pricing strategies. Prefer text-to-image plus image-to-video so the pair covers source-free and uploaded-media execution. Selection cannot be justified by silently narrowing controls after a failed run.
3. Each endpoint must expose at least two useful provider controls beyond prompt/model and the ordinary resolution/aspect/duration selectors. Across the pair exercise at least a numeric and a boolean or enum control. Select and record the concrete control names before onboarding. This threshold is the proposed engineering interpretation of the user's controls requirement.
4. Add only model-definition JSON and catalog-manifest entries. Record official schema/pricing evidence and test requests as data in a separate acceptance report. No production code, UI assets, MCP schemas, adapters, or endpoint-specific test functions may change. The generic harness predates the freeze.
5. Copy the JSON to the existing installation and restart Rhino. Verify binary and UI/MCP hashes are unchanged and the new models are absent when those definitions are removed.

### Behavior required for each endpoint

- Discover it and its full declared controls through both the panel and MCP.
- Set non-default controls through each surface and demonstrate that the same normalized request reaches the fal boundary. Instrumented fixtures verify exact field values; live result content alone is not evidence that an option was transmitted.
- Reject an unknown option, wrong type, out-of-range value, and a supported conditional-invalid combination before upload or inference. A fixture may exercise the conditional rule when neither held-out model has a useful real condition.
- Estimate from effective controls, invalidate a stale quote, submit, observe job progress, fetch a valid artifact, and inspect saved definition/option/pricing provenance.
- Exercise synchronous/queue errors, unknown submission handling, cancellation races, and catalog-change recovery with the generic deterministic fixtures. Remote cancellation success is not a prerequisite for a provider that has already completed; its outcome must be reported accurately.
- Complete live generation through both UI and MCP: four successful jobs in total, one per surface per endpoint. The maintainer chooses economical settings and supplies a concrete total spend cap before that execution stage; this design does not authorize a paid probe now. Failure to run live tests is recorded as incomplete acceptance, never substituted with a fake-provider pass.

If either endpoint needs any code change, the attempt fails the configuration-only criterion. Correct the general implementation, freeze a new runtime, and repeat the proof with endpoints absent from that new freeze. Record failed attempts and their cause.

### Regression requirements

Legacy image/video jobs, Google-to-fal fallback, source framing, credential handling, and artifact publication remain covered by existing tests. New checks cover the definition compiler, options parity, catalog packaging, job snapshots, native bridge routing, and Python tool contracts. Build/test the affected managed targets and native changes using the Windows/Rhino toolchain; use MSVC `14.44.35207` for the native MFC build. No build or live verification is claimed by this design document.

## 16. Implementation planning boundaries

The implementation plan should organize work into independently reviewable stages: definition/compiler contracts; generic adapter/executor and persistent bindings; quotes and input plumbing; UI/MCP/native exposure; catalog deployment and reference conformance fixtures; then the frozen-runtime acceptance exercise. These are planning boundaries, not authorization to implement or a task-level implementation plan.

Likely change areas include the existing `Services/Vision` registries, factories, request/descriptor types, job ledgers, handlers, panel resources, native Vision route wiring, Python tool contracts, managed project asset-copy rules, and deployment/package validation. No `.vcxproj` or `.vcxproj.filters` changes are expected. Revit references remain isolated and this task does not alter BIM behavior. No new external dependency is required.

Leave class/file decomposition, test fixture names, and helper extraction details to the implementation plan. Before its first paid acceptance run, settle the exact endpoints/settings and spend cap. Broadening workflow support, enabling user catalogs, changing fallback equivalence, or replacing current restart semantics requires a separate design decision.

## 17. Sources and relevant contracts

- [Existing generation framework design](../../rook_docs/2026-04-26-generation-provider-framework.md) is historical context; current code controls runtime facts.
- [Google image fallback design](2026-10-12-google-image-fal-fallback-design.md).
- [Google video fallback design](2026-10-14-google-video-fal-fallback-design.md).
- [Video source framing design](2026-10-15-video-source-framing-design.md).
- [Fal model discovery and optional OpenAPI expansion](https://fal.ai/docs/platform-apis/v1/models) supports future import tooling; metadata/schema availability is not guaranteed for every endpoint.
- [Fal cost estimates](https://fal.ai/docs/platform-apis/v1/models/pricing/estimate) accept historical call quantities or expected billing units. Rook still needs a model-specific unit calculation.
- [Fal queue protocol](https://docs.fal.ai/model-apis/model-endpoints/queue) distinguishes submit endpoints from lifecycle URLs and requires fetching the result to determine its final outcome.
