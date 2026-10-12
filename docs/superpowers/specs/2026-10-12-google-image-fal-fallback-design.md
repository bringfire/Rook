# Google image generation through AI Studio with fal fallback

Date: 2026-10-12
Status: Proposed for user review; implementation has not started.
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

Register two additional logical models under the existing fal image provider. Select the editing endpoint whenever admitted resolved media is present; otherwise the provider uses the corresponding text-to-image endpoint.

| Requested AI Studio model | fal logical model | fal editing endpoint ID |
|---|---|---|
| `gemini-3.1-flash-image-preview` | `fal-ai/nano-banana-2` | `fal-ai/nano-banana-2/edit` |
| `gemini-3-pro-image-preview` | `fal-ai/nano-banana-pro` | `fal-ai/nano-banana-pro/edit` |

fal documents these models and file inputs in its [Nano Banana 2 generation](https://fal.ai/models/fal-ai/nano-banana-2/api), [Nano Banana 2 editing](https://fal.ai/models/fal-ai/nano-banana-2/edit/api), [Pro generation](https://fal.ai/models/fal-ai/nano-banana-pro/api), and [Pro editing](https://fal.ai/models/fal-ai/nano-banana-pro/edit/api) schemas, reviewed 2026-10-12.

Use the existing synchronous `fal.run` transport pattern and `FalApiClient`, returning the existing `SyncSubmitOutcome` and remote image materialization path. Keep the new models synchronous; this feature does not introduce fal queue/poll/cancel machinery for them. Do not confuse the HTTP invocation method with the payload's `sync_mode`: leave `sync_mode` false/omitted so output remains the documented HTTPS image result rather than an unsupported data-URI result.

Translate the request explicitly:

- Preserve prompt text and one-image output; send `num_images: 1` and `limit_generations: true`.
- Preserve the primary source image followed by reference images in the caller's original reference order. Send documented `image_urls` as MIME-qualified base64 data URIs. Reuse already-resolved bytes; do not reread mutable paths between attempts. Do not include a reference twice or discard an input.
- Map Rook's Nano Banana 2 resolution `512` to fal's `0.5K`; preserve `1K`, `2K`, and `4K`. Pro supports `1K`, `2K`, and `4K`.
- Preserve a supported explicit aspect ratio and map Rook's automatic aspect selection to fal's `auto`. fal Pro does not document Rook's four extreme ratios (`1:4`, `4:1`, `1:8`, `8:1`). Validate the effective fal capability before submission and return an explicit aspect-ratio error when incompatible. Do not resize, downgrade, substitute models, or silently omit the ratio.
- Use PNG output. Retain the existing Rook input caps (10 MiB per image, 15 MiB aggregate, up to eight references) and generated-image materialization cap (25 MiB). The reference count is a Rook admission limit, not a newly asserted fal guarantee.
- Use the provider's default moderation policy; do not change safety tolerance or work around a policy refusal.

No new external dependency, storage service, or input-upload lifecycle is required. New model pricing must follow the existing unavailable-price pattern until a reviewed fal price is supplied. Do not label a fallback with Gemini's pricing source or present an unknown cost as free.

## Shared execution and route ownership

Add a small image-specific submission executor shared by `VisionHandler` and `ImageJobManager`, constructed from the existing registry in `RookSubsystemRoot`. It owns the closed two-model fallback map and returns the provider outcome together with effective request/model context and a local routing receipt. This is not a modality-neutral retry framework.

The receipt contains only requested provider/model, effective provider/logical model, effective endpoint ID, and a fixed reason (`gemini_key_missing` or `gemini_key_rejected`). Build it from Rook's admitted route, never from provider-returned arbitrary metadata. Existing requests without fallback need no receipt.

Execution order:

1. Validate the requested model/options and resolved input set using existing admission.
2. Submit through the requested provider. Missing credentials already fail locally without network work.
3. If the requested route is an admitted Gemini model and the failure is in the closed credential set, resolve the mapped fal model and translate/validate its request.
4. Check cancellation, and prepare the effective route before fal dispatch. Manager-backed jobs must persist the effective provider/model under their existing guarded transition before any fal generation request; failed persistence or a terminal job aborts dispatch.
5. Submit to fal once using the same cancellation/deadline budget and the same resolved media. Do not reset the caller's timeout or add a retry loop.
6. Return the effective context and outcome for normal materialization/error handling. Keep publication guards attached to the actual provider; Enterprise jobs never enter this fallback path.

The synchronous handler uses effective context for artifact metadata and error attribution. Manager-backed execution keeps the original request for lineage while using the effective provider/model for the remaining lifecycle and materialization. Both paths must pass through this executor so panel and native/MCP callers have identical fallback semantics. The native bridge and Python MCP forwarding need no routing policy of their own.

Use the existing image-ledger schema: initial entries can record the requested Gemini route; the pre-fal transition and terminal entry record the effective fal logical model/provider. The existing JSONL reader accepts those fields and returns the latest entry. Do not change schema version or retroactively rewrite old records. Add the optional effective-route argument to the existing guarded transition, ensuring its in-memory candidate and persisted entry agree. Cancellation and terminal-state protection still win over a late provider result. If cancellation wins after the final local check, remote submission may already have started; do not promise remote cancellation or exactly-once cloud execution.

Successful fallback artifact metadata records `provider: fal`, the effective logical `model`, `provider_endpoint`, `requested_provider`, `requested_model`, and `fallback_reason`, in addition to existing prompt, output, and parent-artifact metadata. The complete original lineage remains intact. The terminal job's provider/model and the resulting artifact agree. A failed fal attempt is attributed to fal and does not produce a misleading Google-success artifact.

## Catalog, credentials, and UI

Keep Gemini and fal secret settings independent in the existing store. Model availability for the two Gemini choices considers both providers:

- Gemini configured: selectable, with fal fallback availability disclosed when configured.
- Gemini missing and fal configured: selectable, with "Uses fal.ai when Gemini key is missing" information.
- Both missing: disabled with "Configure a Gemini or fal.ai key" information.

Return structured fallback availability on those model descriptors rather than pretending that a fal key makes the Gemini key valid. Include the mapped provider/model and effective credential availability; keep actual secret values/previews in their existing settings projection. Other Gemini/custom and Vertex descriptors do not acquire this fallback metadata.

Update descriptor normalization, dropdown disabling, Generate/Studio validation, and result notices to consume that metadata. The session's key-test overlay must not disable a model with an available fallback or initiate a UI retry. The backend remains authoritative. Saving/clearing either key refreshes model availability using existing settings refresh behavior. The settings Test action stays a standalone probe; this feature does not automatically run billed probes or redesign prompt enhancement.

## Verification and acceptance

Use real request encoding, providers, executor, handlers, registry, manager, ledger, and artifact store with HTTP replaced at the transport boundary. Isolate filesystem state through the repository's test path conventions. Provider success fixtures and downloaded artifacts are synthetic; no test consumes a real credential or sends live media requests.

Acceptance cases:

1. Both model families with missing/blank Gemini keys succeed through exactly one fal generation request and zero Google HTTP requests.
2. The admitted invalid-key and authentication responses produce exactly one Google attempt and one fal attempt. A valid Google success produces zero fal attempts.
3. The negative error cases above, including generic 400/403, malformed bodies, spoofed invalid-key reasons in 5xx, cancellation, and text-probe failure, never trigger fallback.
4. Missing fal credentials and fal failure terminate clearly without a fallback loop or a third generation submission. A replaced Gemini credential works on the next request.
5. Endpoint, model, resolution translation, automatic/explicit aspect, MIME-qualified source bytes, reference order, and one-image output are correct. An unsupported Pro aspect fails before fal dispatch and loses no inputs.
6. Both synchronous and manager-backed paths publish the effective provider/model and original requested context; source/reference parent IDs survive. The JSONL round trip and fresh manager read retain the effective fal route without a schema migration.
7. A failed route-ledger append prevents fal dispatch. Deterministic cancellation/terminal-state tests cover the interval before fallback and late completion; canceled jobs publish no new result.
8. Executable UI behavior tests prove the Gemini options remain selectable with only fal configured, are blocked with neither credential, and submit once without client-side retry. Backend catalog and settings refresh tests cover either credential changing.
9. Existing Gemini, fal FLUX/GPT, Replicate, image-manager, native bridge, and Enterprise dispatch/publication tests remain applicable and pass, with failures and unavailable prerequisites reported explicitly.

The implementation plan will specify fresh build/test commands and relevant regression filters. Build the managed companion for the supported targets and run the affected managed and UI suites. No native C++ change/build is expected. Deployment, cloud-account setup, and live billed qualification are separate user requests; mocked verification does not establish actual fal access, quota, billing, or image quality.

## Review checklist and implementation boundary

Review these proposed decisions before planning:

- Only missing keys and the closed credential-rejection set trigger fallback.
- Existing Nano Banana choices retain their model family and input content.
- fal compatibility failures are explicit; no silent output substitution.
- Both submission paths use one shared policy, with effective provider attribution before dispatch.
- Enterprise, video, text, Enhance Prompt, and live deployment stay outside this change.

Expected implementation areas: `Services/Vision/Image` (executor, Gemini classification, fal capabilities/options/provider/registration), `VisionProviderRegistrations`, `RookSubsystemRoot`, `VisionHandler`, `ImageJobManager` and its transition helper, `UI/Vision/Resources/app.js`, and focused tests in `Rook.Tests`. Existing contracts are extended locally; no `.vcxproj`, `.vcxproj.filters`, Revit references, new public native route, or external dependency is required.
