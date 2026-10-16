# Google image generation through AI Studio with fal fallback

Date: 2026-10-12
Status: Revised after reviewer feedback; proposed for user review. Implementation has not started.
Baseline: `a6f63be8` on Rook `main`; Enterprise Google arrived in `2d70282c` / PR #613.

## Intent and agreed requirements

The office currently generates images using the departing employee's personal Google AI Studio API key. Employees need to continue using the existing Nano Banana choices if that key is removed or Google rejects it, without depending on completion of Enterprise Google administration.

The user explicitly requested automatic fallback to Google's image models on fal.ai when the Gemini API key is invalid, and subsequently confirmed that an unset Gemini key must also trigger fallback. Preserve the chosen model family and submitted content. The office must supply a funded fal credential through the existing local settings.

This document proposes the details beyond those two confirmed triggers. Billing/quota failures, broader outages, and Enterprise authorization failures do not trigger fallback in this scope. Approval of this spec precedes a separate implementation plan and its review.

## Existing implementation

- `VisionProviderRegistrations.CreateImageRegistrations` registers separate Gemini, fal, Replicate, and Vertex providers. Gemini defaults remain first.
- Gemini registers `gemini-3.1-flash-image-preview` and `gemini-3-pro-image-preview`, also reached through `nano-banana-2` and `nano-banana-pro`. This change does not migrate those upstream model IDs.
- fal currently registers FLUX Schnell and GPT Image 2 Edit, with no Google image models.
- `VisionHandler.GenerateAsync` performs synchronous generation for the panel and the native `/vision/generate` callback. `ImageJobManager` separately submits provider requests for panel image jobs. Both use the shared image registry.
- The provider currently returns a missing-key failure before contacting Google. It maps HTTP 400 to `InvalidRequest` and authentication/network failures to `DependencyUnavailable`; those classifications alone cannot identify a credential rejection.
- The image catalog advertises credential availability for one provider. The UI disables a Gemini model when its key is missing. Merely adding backend fallback would leave those choices unusable in the panel.
- Image jobs write provider/model into the initial record and ledger before submission. Artifacts and completion must reflect the provider actually used after a fallback.
- Current transition and cancellation helpers update the in-memory record before independently appending JSONL. The reader keeps the last physical entry per job. A delayed earlier append can therefore overwrite the durable view of a later cancellation; the fallback cannot rely on that ordering without a local fix.
- Synchronous generation failures currently return strings. Job status omits provider/model, and the UI drops routing context when creating an error and infers credential failure from its message and selected provider. These projections must carry effective-route information for fallback errors.
- The synchronous panel has a 180-second operation token. Background image jobs link execution only to shutdown, while each provider has its own five-minute HTTP timeout. An aggregate background deadline does not currently exist.
- Gemini and fal credentials use the existing DPAPI store under the Windows user. The settings key test uses text generation and classifies every unsuccessful probe as invalid. It is not authoritative evidence for image fallback.
- Enterprise Google is explicit and has authorization-bound dispatch/publication guards. Its credential lifecycle is owned by Python. The new fallback does not participate in that authorization lifecycle.

## Scope and user-visible behavior

Only the two existing AI Studio Nano Banana models have automatic fallback. Their aliases resolve before routing. Unknown/custom Gemini model IDs retain their current behavior; an unknown Vertex model continues to fail rather than enter the Gemini path.

| Selected route and condition | Required behavior |
|---|---|
| Nano Banana 2 or Pro; Gemini key present and generation succeeds | Use Google directly; no fal generation request |
| Nano Banana 2 or Pro; Gemini key null, empty, or whitespace | Skip Google HTTP and submit once to the corresponding fal model |
| Nano Banana 2 or Pro; confirmed Gemini credential rejection | Submit once to the corresponding fal model after the rejected Google attempt |
| Fallback needed; fal key missing | Return an actionable error identifying the missing fal credential; no fal HTTP request |
| Neither key present | The catalog reports the model unavailable and the panel explains that a Gemini or fal key is needed |
| fal rejects or cannot complete the fallback | Return the fal failure; no return to Google and no automatic resubmission |
| Selected Google Enterprise model | Retain the existing explicit Vertex behavior and authorization guards |
| Selected other provider/model | Retain its current route |

Generate and Studio retain the selected Nano Banana model. Show that fal fallback is available in model/settings information, and show "Generated with fal.ai" after a successful fallback. Choosing Generate authorizes the documented fallback; there is no extra confirmation between a definitive key rejection and fal submission.

Preserve existing source-image requirements and admitted workflows. This change does not add a new prompt-only panel workflow, alter video generation, or change Enhance Prompt, Chirp, text generation, Enterprise configuration, installation, or deployment.

## Definitive credential classification

Normalize credential rejection inside `GeminiImageProvider`, where the HTTP status and parsed Google response are available. Carry a fixed, typed/local marker through `GenerationError.ProviderErrorCode`; the image executor must never inspect human-readable error messages or the UI's validation overlay.

The closed trigger set is:

1. The provider's local missing/blank-key outcome.
2. An HTTP 400, 401, or 403 response with a valid `google.rpc.ErrorInfo` entry, domain `googleapis.com`, and reason `API_KEY_INVALID`. If the entry supplies a service, it must be `generativelanguage.googleapis.com`.
3. An HTTP 401 response whose parsed Google status is `UNAUTHENTICATED`.

Google's [GenerateContent error reference](https://ai.google.dev/gemini-api/docs/generate-content/api-errors) documents HTTP 400 with `API_KEY_INVALID`. Google's [error-reason contract](https://github.com/googleapis/googleapis/blob/master/google/api/error_reason.proto) defines that reason to include invalid, missing, or expired keys. The HTTP 401 rule above is a proposed conservative authentication rule for this implementation, not a claim that all invalid keys return 401.

Do not trigger on a generic 400 or 403, key restriction/project-permission errors without the admitted invalid-key reason, model-not-found, billing failures, exhausted credits, rate limits, content-policy outcomes, malformed output, HTTP 5xx, timeouts, transport exceptions, cancellation, or unreadable local ciphertext. A reason embedded in a 5xx or malformed/unrecognized error envelope cannot admit fallback. Preserve useful existing error information without persisting credentials or raw error payloads in routing receipts.

Each deliberately new request re-evaluates the current credentials. Do not persist a provider switch or permanently mark the stored key invalid. A replacement Gemini key takes effect on the next request. This scope introduces no health cache or circuit breaker.

## Model mapping and payload fidelity

Register two additional logical models under the existing fal image provider. They intentionally appear as separate catalog choices labelled Nano Banana 2 / Pro with the fal.ai provider. Selecting one uses fal directly, even when a Gemini key is configured; it never tries Google or switches providers. Existing Gemini defaults and automatic-fallback choices remain first. There is no hidden-target filtering or new prompt-only panel workflow.

Select the editing endpoint whenever admitted resolved media is present; otherwise the provider uses the corresponding text-to-image endpoint.

| Requested AI Studio model | fal logical model | fal editing endpoint ID |
|---|---|---|
| `gemini-3.1-flash-image-preview` | `fal-ai/nano-banana-2` | `fal-ai/nano-banana-2/edit` |
| `gemini-3-pro-image-preview` | `fal-ai/nano-banana-pro` | `fal-ai/nano-banana-pro/edit` |

fal documents these models and file inputs in its [Nano Banana 2 generation](https://fal.ai/models/fal-ai/nano-banana-2/api), [Nano Banana 2 editing](https://fal.ai/models/fal-ai/nano-banana-2/edit/api), [Pro generation](https://fal.ai/models/fal-ai/nano-banana-pro/api), and [Pro editing](https://fal.ai/models/fal-ai/nano-banana-pro/edit/api) schemas, reviewed 2026-10-12.

Use the existing synchronous `fal.run` transport pattern and `FalApiClient`, returning the existing `SyncSubmitOutcome` and remote image materialization path. Keep the new models synchronous; this feature does not introduce fal queue/poll/cancel machinery for them. Do not confuse the HTTP invocation method with the payload's `sync_mode`: leave `sync_mode` false/omitted so output remains the documented HTTPS image result rather than an unsupported data-URI result.

Translate the request explicitly:

- Preserve prompt text and one-image output; send `num_images: 1` and `limit_generations: true`.
- Preserve the primary source image followed by reference images in the caller's original reference order, including explicitly repeated references. Send documented `image_urls` as MIME-qualified base64 data URIs. Reuse already-resolved bytes; do not reread mutable paths between attempts. For example, source A with references `[B, B, C]` produces `[A, B, B, C]`. Do not deduplicate caller input, discard an occurrence, or accidentally append another copy while enumerating the resolved-media dictionary. Repeated occurrences continue to count toward existing count/aggregate admission limits; sharing their resolved bytes does not change payload multiplicity.
- Map Rook's Nano Banana 2 resolution `512` to fal's `0.5K`; preserve `1K`, `2K`, and `4K`. Pro supports `1K`, `2K`, and `4K`.
- Preserve a supported explicit aspect ratio and map Rook's automatic aspect selection to fal's `auto`. fal Pro does not document Rook's four extreme ratios (`1:4`, `4:1`, `1:8`, `8:1`). Validate the effective fal capability before submission and return an explicit aspect-ratio error when incompatible. Do not resize, downgrade, substitute models, or silently omit the ratio.
- Use PNG output. Retain the existing Rook input caps (10 MiB per image, 15 MiB aggregate, up to eight references) and generated-image materialization cap (25 MiB). The reference count is a Rook admission limit, not a newly asserted fal guarantee.
- Use the provider's default moderation policy; do not change safety tolerance or work around a policy refusal.

No new external dependency, storage service, or input-upload lifecycle is required. New model pricing must follow the existing unavailable-price pattern until a reviewed fal price is supplied. Do not label a fallback with Gemini's pricing source or present an unknown cost as free.

## Shared execution and route ownership

Add a small image-specific submission executor shared by `VisionHandler` and `ImageJobManager`, constructed from the existing registry in `RookSubsystemRoot`. It owns the closed two-model fallback map and returns the provider outcome together with effective request/model context and a local routing receipt. This is not a modality-neutral retry framework.

The receipt contains only requested provider/model, effective provider/logical model, effective endpoint ID, a fixed reason (`gemini_key_missing` or `gemini_key_rejected`), execution phase, and whether a generation dispatch was attempted. Build it from Rook's admitted route, never from provider-returned arbitrary metadata. A selected effective target is not evidence that it accepted a request. Existing requests without fallback need no receipt.

Execution order:

1. Validate the requested model/options and resolved input set using existing admission.
2. Submit through the requested provider. Missing credentials already fail locally without network work.
3. If the requested route is an admitted Gemini model and the failure is in the closed credential set, create the local fallback receipt and resolve the mapped fal model. Translation/compatibility validation and missing-fal-key failures retain that receipt with no generation dispatch attempted.
4. Check cancellation/deadline, and prepare the effective route before fal dispatch. Manager-backed jobs must durably persist effective provider/model and receipt in the ordered transition described below; failed persistence or a terminal job aborts dispatch.
5. Submit to fal once under the execution budget defined below, using the same resolved media. Do not restart the deadline or add a retry loop. Mark dispatch attempted at the local provider send boundary; this does not promise remote acceptance or completion.
6. Return the effective context and outcome for normal materialization/error handling. Keep publication guards attached to the actual provider; Enterprise jobs never enter this fallback path.

The synchronous handler uses effective context for artifact metadata and error attribution. Manager-backed execution keeps the original request for lineage while using the effective provider/model for the remaining lifecycle and materialization. Both paths must pass through this executor so panel and native/MCP callers have identical fallback semantics. The native bridge and Python MCP forwarding need no routing policy of their own.

Initial ledger entries record the requested Gemini route. Once fallback is selected, route-preparation/failure and terminal entries record the effective fal logical model/provider and optional local `image_route` receipt. Preserve schema version 1 with additive optional `image_route` and `credential_failure` fields: legacy entries without them remain readable and are not rewritten. Validate these optional objects against their closed contracts; malformed new values produce a ledger-read error rather than invented attribution. Retain them through subsequent transitions, error sanitization, restart reconciliation, and response projection. Persisting only effective provider/model is insufficient to reconstruct requested-route context after restart.

Successful fallback artifact metadata records `provider: fal`, the effective logical `model`, `provider_endpoint`, `requested_provider`, `requested_model`, and `fallback_reason`, in addition to existing prompt, output, and parent-artifact metadata. The complete original lineage remains intact. The terminal job's provider/model and the resulting artifact agree. A failed fal attempt is attributed to fal and does not produce a misleading Google-success artifact.

## Durable transition ordering

Use one per-job serialization boundary for all state-changing writes that can race with fallback: route preparation, ordinary state transitions, local cancellation, deadline interruption, completion, publication cleanup, and append-failure handling. Reuse the manager's existing transition methods with this bounded ordering fix; do not add a second ledger or a cross-provider job subsystem. Do not hold this boundary during provider HTTP work or artifact downloads.

Under that boundary, re-read the latest committed state, reject a stale transition over a terminal winner, build its in-memory/durable candidates, append the durable entry, and then publish the committed in-memory state. A successful route preparation cannot dispatch fal until its append has succeeded. A successful cancellation/terminal response cannot be reported before its durable terminal append succeeds. A delayed transition cannot append behind an already committed terminal winner; memory, the running job, and a fresh manager reading JSONL must agree on that winner. The admitted terminal transition has exclusive commit ownership while its append is in progress; a later cancellation/deadline waits for settlement and cannot delete an artifact belonging to a successfully committed completion.

For the affected synchronous jobs, a local cancellation/deadline request signals execution cancellation promptly even if it must wait for an in-progress ledger write. After route persistence finishes, recheck the signal and terminal state before fal dispatch. Disk-write failure aborts further dispatch/publication and returns an explicit persistence failure; do not claim durable cancellation when its append failed. Record the existing append-failure diagnostic as far as possible. This does not provide atomicity across disk, the artifact store, and a cloud provider, and a crash before durable terminal persistence may still require restart interruption.

Deterministic scheduling tests must cover both orderings. If cancellation commits first, pause a stale route attempt before its serialization boundary, finish cancellation, then release the route and prove no nonterminal append or fal dispatch follows. If route persistence holds the boundary first, pause its append, request cancellation, prove cancellation cannot report durable success prematurely, release persistence, and prove cancellation becomes the last committed entry and fal does not dispatch. Check the running manager, physical ledger order, and a fresh manager. Append failures and late publication must not bypass the same boundary.

## Failure and outward route contract

Fallback-aware synchronous failures return a structured object in the existing `ApiResponse.Data` slot with `code`, safe `message`, `retryable`, `field`, optional `credential_failure`, and `image_route`. Preserve `.message` presentation in existing callers; unrelated legacy string failures may retain their shape. Use existing HTTP status mappings and the existing native/managed envelope forwarding, with no new native route.

The allowlisted `image_route` projection contains `requested_provider`, `requested_model`, `effective_provider`, `effective_model`, `provider_endpoint`, `fallback_reason`, `phase`, and `generation_dispatch_attempted`. Provider/model/endpoint values come from the closed local catalog, not free-form upstream responses. Phases are `validation`, `submission`, `materialization`, `publication`, or `interruption`. The receipt never includes a key, prompt, media bytes, input/output URL, account identifier, or raw provider error payload. An endpoint ID is a catalog path such as `fal-ai/nano-banana-2/edit`, not a URL.

Create the receipt as soon as fallback is selected, and keep it on compatibility validation, missing fal credential, fal HTTP/result failure, materialization/publication failure, timeout, and cancellation responses. Set `generation_dispatch_attempted` false until the local send boundary is crossed; true means an attempt started, not that generation was accepted or billed. Pre-dispatch compatibility/missing-key failure identifies fal as the selected effective target without claiming that content was sent.

`credential_failure`, when present, contains an allowlisted `provider` and `kind` (`missing` or `rejected`) derived from that provider's local key absence or normalized credential-rejection classification. Generic provider, compatibility, policy, download, and timeout failures omit it. Do not infer this evidence from a message or merely from a `DependencyUnavailable` error. Persist only this safe optional classification with a job's routing context so restart projection has the same meaning.

Relevant image-job status/list and result responses carry the safe receipt when available, including terminal errors and successful results; failed start responses carry it when fallback preparation occurs before a job is accepted. Preserve the original requested route and the effective route after restart, even on failure. Legacy jobs without a receipt continue to expose their existing provider/model without fabricating a requested route or fallback reason.

`bridgeCall` must retain structured route/credential information on thrown errors, and `awaitImageJobResult` must retain it when converting a terminal status into an error. Generate and Studio use the actual effective route in their displayed failure context. For an error with this structured context, remove selected-provider/message-based invalidation: only an explicit `credential_failure` may update the named provider's session warning. A fal rejection must not mark Gemini invalid just because Gemini remains selected; a generic fal failure marks neither credential invalid. `missing` is a missing-configuration warning, not proof of an invalid credential. Unrelated legacy error handling is not broadly redesigned here.

Both Generate and Studio, in synchronous and manager-backed result rendering, show "Generated with fal.ai" when the backend's successful route identifies fal fallback. Test this notice through actual handler/bridge projections rather than source-string checks alone. Materialization failure must retain fal attribution even though no successful artifact exists.

The current panel timeout wrapper can overwrite a structured handler failure with a string. For these fallback-aware generation failures, preserve the allowlisted route/credential projection while replacing the error code/message with the timeout classification. Once a handler has routing context, translate cancellation/deadline into a failure carrying it rather than allowing a bare exception to erase it. A timeout before routing context exists has no receipt. Other domains retain their existing wrapper behavior.

## Execution deadlines

Synchronous panel/native calls keep their existing caller-owned operation deadline (180 seconds in the current panel/native generation paths). The primary attempt, fallback preparation/submission, materialization, and final publication checks consume that same remaining budget. No second provider gets a fresh caller deadline.

Manager-backed jobs for the two fallback-capable Gemini models and the two new direct fal choices get a manager-owned **180-second execution deadline**. Start it immediately after acquiring the concurrency slot, before the first `Submitting` transition. Queue wait is excluded. The deadline covers primary submission, route persistence/validation, fallback submission, result materialization/download, and artifact publication/terminal-commit admission. It is not attached to the short-lived `SubmitAsync` call token; the manager owns and disposes it, linked to job cancellation and shutdown. Other existing models retain their present timeout behavior.

Every phase checks the same deadline/cancellation signal. A key rejection near expiry leaves fal only the remaining time. Expiry before fal dispatch causes no fal request. Expiry after dispatch stops local processing and prevents late result publication/resubmission, although remote work may continue. When expiry wins before final completion admission, commit `Interrupted` with a fixed deadline-exceeded diagnostic, nonretryable, and the available route/dispatch context. User cancellation retains `Cancelled`; completion already admitted for its terminal commit under the per-job boundary before the deadline signal wins remains terminal if that commit succeeds. Use the durable ordering rules above to settle races.

The deadline is an execution/final-publication-admission cutoff, not a promise that blocked local filesystem I/O stops at exactly 180 seconds. Recheck it after route persistence and artifact creation, and inside the final transition boundary immediately before admitting a completion append. If expiration wins before that admission, remove the unpublished artifact through existing cleanup and durably interrupt. A completion append admitted before expiry may finish later because disk I/O is not cancelable; wait for its success/failure and preserve that winning outcome rather than claiming a hard wall-clock bound or rewriting a committed completion. Do not count a late provider return as success just because the provider ignored cancellation.

Tests use controlled deadline/cancellation scheduling, without a real 180-second sleep: primary rejection just before expiry, expiry before route/send, late fal result, expiry during materialization, publication cleanup after expiry, both orderings of expiry versus final completion admission, and expiry during queued work (the execution timer must not start yet). Canceling or disposing the submit-call token after an accepted job must not cancel that background job.

## Catalog, credentials, and UI

Keep Gemini and fal secret settings independent in the existing store. Model availability for the two Gemini choices considers both providers:

- Gemini configured: selectable, with fal fallback availability disclosed when configured.
- Gemini missing and fal configured: selectable, with "Uses fal.ai when Gemini key is missing" information.
- Both missing: disabled with "Configure a Gemini or fal.ai key" information.

Return structured fallback availability on those Gemini model descriptors rather than pretending that a fal key makes the Gemini key valid. Include the mapped provider/model and effective credential availability; keep actual secret values/previews in their existing settings projection. The explicit new fal choices use their own fal credential availability. Other Gemini/custom and Vertex descriptors do not acquire this fallback metadata.

Update descriptor normalization, dropdown disabling, Generate/Studio validation, and result notices to consume that metadata. The session's key-test overlay must not disable a model with an available fallback or initiate a UI retry. The backend remains authoritative. Saving/clearing either key refreshes model availability using existing settings refresh behavior. The settings Test action stays a standalone probe; this feature does not automatically run billed probes or redesign prompt enhancement.

## Verification and acceptance

Use real request encoding, providers, executor, handlers, registry, manager, ledger, and artifact store with HTTP replaced at the transport boundary. Isolate filesystem state through the repository's test path conventions. Provider success fixtures and downloaded artifacts are synthetic; no test consumes a real credential or sends live media requests.

Acceptance cases:

1. Both model families with missing/blank Gemini keys succeed through exactly one fal generation request and zero Google HTTP requests.
2. The admitted invalid-key and authentication responses produce exactly one Google attempt and one fal attempt. A valid Google success produces zero fal attempts.
3. The negative error cases above, including generic 400/403, malformed bodies, spoofed invalid-key reasons in 5xx, cancellation, and text-probe failure, never trigger fallback.
4. Missing fal credentials and fal failure terminate clearly without a fallback loop or a third generation submission. A replaced Gemini credential works on the next request.
5. Endpoint, model, resolution translation, automatic/explicit aspect, MIME-qualified source bytes, reference order/multiplicity, and one-image output are correct. Source A plus `[B, B, C]` must produce `[A, B, B, C]`, with no extra dictionary-enumeration copies. An unsupported Pro aspect fails before fal dispatch and loses no inputs.
6. Both synchronous and manager-backed paths publish the effective provider/model and original requested context; source/reference parent IDs survive. The JSONL round trip and fresh manager read retain safe requested/effective context and credential classification, including terminal failures. Legacy version-1 records without optional route data remain readable; malformed new route data is rejected.
7. A failed route-ledger append prevents fal dispatch. The two deterministic paused-transition orderings in Durable transition ordering prove agreement between memory, physical append order, and a fresh manager. Include cancellation/terminal append failure, late completion, and publication cleanup; canceled/interrupted jobs publish no new result.
8. Executable UI behavior tests prove the Gemini options remain selectable with only fal configured, are blocked with neither credential, and submit once without client-side retry. Backend catalog and settings refresh tests cover either credential changing. Explicit fal choices appear intentionally and bypass Google even with a Gemini key present.
9. Drive a generic fal HTTP error through the actual synchronous handler and UI projection with Gemini missing: fal attribution survives, no credential is marked invalid, and no extra submission occurs. Drive a normalized fal credential rejection through both handler/UI paths: only fal gets a rejection warning. Cover missing fal key, compatibility validation, materialization failure, and a structured timeout, including job status-to-error conversion. Test "Generated with fal.ai" in both Generate and Studio for sync and job results.
10. Deterministic deadline tests cover Google rejection near expiry, no fal dispatch after expiry, a late fal result, expiry during materialization/publication, queue-wait exclusion, and independence from the short-lived accepted-submit token. A fallback uses the same 180-second budget rather than two provider timeouts.
11. Existing Gemini, fal FLUX/GPT, Replicate, image-manager, native bridge, and Enterprise dispatch/publication tests remain applicable and pass, with failures and unavailable prerequisites reported explicitly.

The implementation plan will specify fresh build/test commands and relevant regression filters. Build the managed companion for the supported targets and run the affected managed and UI suites. No native C++ change/build is expected. Deployment, cloud-account setup, and live billed qualification are separate user requests; mocked verification does not establish actual fal access, quota, billing, or image quality.

## Review checklist and implementation boundary

Review these proposed decisions before planning:

- Only missing keys and the closed credential-rejection set trigger fallback.
- Existing Nano Banana choices retain their model family and input content.
- fal compatibility failures are explicit; no silent output substitution.
- Both submission paths use one shared policy, with effective provider attribution before dispatch.
- All image-job transitions that can race with fallback preserve terminal winners in physical ledger order and memory.
- Fallback failures carry safe requested/effective context through handler, job, bridge, and UI projections.
- The affected background jobs have one manager-owned 180-second execution budget starting after concurrency admission, including materialization/publication.
- New direct fal choices are visible intentionally; caller reference multiplicity is preserved.
- Enterprise, video, text, Enhance Prompt, and live deployment stay outside this change.

Expected implementation areas: `Services/Vision/Image` (executor, Gemini classification, fal capabilities/options/provider/registration, job result/receipt types and backward-compatible ledger projection), `VisionProviderRegistrations`, `RookSubsystemRoot`, `VisionHandler`, `ImageJobManager` and its transition/timeout helpers, `ImageJobOpHandler`, fallback-aware timeout handling in `VisionWebSurface`, `UI/Vision/Resources/app.js`, and focused tests in `Rook.Tests`. Existing contracts are extended locally; no `.vcxproj`, `.vcxproj.filters`, Revit references, new public native route, or external dependency is required.
