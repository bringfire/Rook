# Multi-Provider Generation Spike — Phase 0 Evidence

**Date:** 2026-04-27
**Status:** complete — all six contract decisions bound; gate satisfied per design Section 1
**Branch:** `spike/multi-provider-phase0` (multi-commit history; harness + curated evidence land in `7550e56` … `73c2f89`, with subsequent commits adding this doc and its review-pass corrections — see `git log main..spike/multi-provider-phase0` for the full sequence)

**Related:**
- `docs/plans/2026-04-27-multi-provider-phase0-spike-design.md` — Phase 0 spike design doc. **Local-only per Rook convention** (`docs/plans/` is gitignored at `.gitignore:5`); not committed and not browsable in the PR. The substantive design constraints from that file (probe matrix, six contract decisions, strict gate, 3D carve-out) are summarized in the Methodology and Decision sections below; reviewers should read this committed doc as the canonical record.
- [`2026-04-26-generation-provider-framework.md`](2026-04-26-generation-provider-framework.md) — v0.1 strategic frame; this spike feeds its v0.2 update
- [`2026-04-22-v3-video-decisions.md`](2026-04-22-v3-video-decisions.md) — V1c video provider abstraction (the template generalized)
- [`2026-04-08-sa-banana-integration.md`](2026-04-08-sa-banana-integration.md) — RookVision image-track architecture (refactor target)
- Curated evidence: [`artifacts/2026-04-27-multi-provider-spike/`](artifacts/2026-04-27-multi-provider-spike/) (12 probe directories, ~200 KB content across 140 files; provider request/prediction IDs normalized to `<REQUEST_ID>` / `<PREDICTION_ID>` / `<JOB_ID>` / `<STREAM_TOKEN>` placeholders so URL patterns are evidence-bearing without enumerating past requests)

---

## TL;DR

Phase 0 collected real provider-contract evidence across **five distinct provider/invocation paths** (fal sync, fal queue, Replicate prediction, Gemini direct, Tencent docs+SDK audit). All six contract decisions bound with explicit Phase 1 recommendations. Total spike spend ~$1.13 of the $25 hard stop. Strict go/no-go gate is satisfied; 3D-specific capability detail provisionally deferred under the design's carve-out (Hunyuan evidence captured; Phase 1 must not freeze 3D semantics beyond opaque modality/capability descriptors).

---

## Methodology

The harness lives at [`tools/spikes/multi-provider-phase0/`](../../tools/spikes/multi-provider-phase0/) (Python probes + curation + a `net7.0` C# shape probe). Raw runtime captures stayed under `.scratch/multi-provider-spike/` (gitignored). Curated, redacted, schema-shape-bearing evidence was generated via `harness.curate --spike-date 2026-04-27` and committed under [`docs/rook_docs/artifacts/2026-04-27-multi-provider-spike/`](artifacts/2026-04-27-multi-provider-spike/).

Redaction is multi-layered: structured key/value rules (`Authorization` headers, `*_token`/`*secret` field names, signed-URL query tokens, `data:` URIs, JWT-shaped values, base64 blobs), markdown URL-token sweeping, response-body size cap (8 KB) with no preview emitted, and binary-content-type detection that drops body bytes. The C# shape probe validates that captures round-trip through typed `System.Text.Json` models with separate success-result and error-envelope predicates.

**Kickoff prereq status (recorded before first live probe):**
- `FAL_KEY` present; auth status `auth_only_unproven` (the catalog endpoint we hit is public; first paid probe P1 was the actual auth proof)
- `REPLICATE_API_TOKEN` present; auth `complete` via `api.replicate.com/v1/models`
- `GOOGLE_API_KEY` present; auth `complete` via `generativelanguage.googleapis.com/v1beta/models`
- `TENCENT_KEY` not used; P5 ran as docs-only audit per design Section 2

**Cost discipline:** target `<$10`, hard stop `$25 without explicit approval`. Final spike spend ~$1.13 (P1 ×2 ~$0.006 + P3 ~$0.003 + P2 ~$0.75 + P4 ~$0.375 + B1 ~$0.05). One validation-failed P4 attempt cost $0 because fal returns `x-fal-billable-units: 0` for input-validation rejections.

**Bug-find-and-patch cycles during execution** (folded into the spike's evidence rather than treated as setbacks):
1. P3 official-model endpoint required body-shape variation — patched `--replicate-mode {versioned, official-model, unified-model-id}`
2. fal queue uppercase state names + separate `response_url` for fetch — patched case-insensitive terminal check + `response_url` discovery in `capture_fetch_or_result`
3. Hunyuan3D required ≥128px input — patched `fixtures.write_red_cube_png` to 256×256 stdlib-built PNG
4. Hunyuan3D used `input_image_url` not `image` — patched `--image-field` flag on P4
5. Probe outcome was based on submit status only; fixed to use combined submit+fetch via `determine_outcome` helper

Each is itself contract evidence and is cited under the relevant Decision row below.

---

## Probe Inventory

| ID | Route | Type | Outcome | Curated path | Notes |
|---|---|---|---|---|---|
| **B1** | Gemini `gemini-3.1-flash-image-preview` | Live (sync) | complete | `b1/` | Inline-bytes result delivery; per-token-by-modality usageMetadata |
| **B2** | Veo (existing Rook integration) | Code-read baseline | n/a | n/a | Anchored V1c lifecycle reference; no live call per design |
| **P1** | fal `fal-ai/flux/schnell` @ `fal.run` (sync) | Live | complete | `p1/`, `p1_sync/` | Single-shot; `images: [{url, ...}]` array result; `x-fal-billable-units` header |
| **P1q** | fal `fal-ai/flux/schnell` @ `queue.fal.run` (async) | Live | complete (submit only) | `p1_queue/` | Captured queue submit envelope; harness's pre-Decision-1 contract proof |
| **P3** | Replicate `black-forest-labs/flux-schnell` (official-model) | Live | complete | `p3/`, `p3_official_model/` | Lowercase states; `output: [<url>]`; `metrics.predict_time` body field |
| **P2** | fal `fal-ai/wan/v2.7/text-to-video` @ `queue.fal.run` | Live | complete | `p2/` | UPPERCASE states; `video: {url, duration, fps, ...}` singular result; 35-poll lifecycle |
| **P4** | fal `fal-ai/hunyuan-3d/v3.1/pro/image-to-3d` @ `queue.fal.run` | Live | complete | `p4/` | **Gating successful 3D evidence**; multi-format `model_urls` envelope; 49-poll lifecycle (250s GPU) |
| **P4-err** | (same model, 1×1 input PNG) | Live | validation_failed | `p4_validation_rejection/` | **Error-envelope evidence ONLY**; FastAPI `detail: [{loc, msg, type, url}]`; does NOT contribute to gate beyond Decision 1 split + Decision 5 error-shape |
| **P5** | Tencent Cloud Hunyuan v20230901 | Docs + SDK audit | complete (live call deferred to Phase 4) | n/a | Full API surface enumerated; SDK pattern captured; tencentcloud-sdk-python integration plan |

P4 vs P4-err separation per the operator's review-pass note: **`p4/` is the gating successful 3D evidence; `p4_validation_rejection/` contributes only to error-shape (Decision 5) and input-validation (Decision 1 success-vs-terminal split) findings, not to the go/no-go gate.**

---

## C# Shape Check

`tools/spikes/multi-provider-phase0/csharp-probe/` (`net7.0`, captures-only — never makes live calls) deserialized JSON captures from the **three risky-shape probe directories (p2, p3, p4)** through typed `CaptureEnvelope` / `CaptureHttpResponse` / `ProviderBodyShape` records. Round-trip serialize check confirmed `response` payload survived end-to-end. The other 9 committed directories (`auth_*`, `b1`, `p1*`, `p3_official_model`, `p4_validation_rejection`) are covered by:
- the secret/JWT scan (zero matches across the entire 12-directory tree),
- the curated artifact review (each directory's `manifest.json` + a representative payload reviewed),
- and the C# probe's same-shape coverage of `p4` (which exercises the success path) plus the `p4_validation_rejection` deliberate exclusion (it's marked error-evidence-only and not a gating capture).

The probe was hardened twice during the review pass:
1. Added recognized fields for modality-specific result envelopes: `images`, `video`, `audio`, `model_glb`, `model_urls`, `candidates`. Without these, p2/fetch.json (`{video: {...}}`) and p4/fetch.json (`{model_glb, model_urls, ...}`) failed because the original signal predicate looked for `Status`/`Output`/etc. only.
2. Split `Detail` (FastAPI error envelope) out of the success-signal predicate. New `HasErrorSignal()` and `IsRecognizedShape() = HasLifecycleOrResultSignal() || HasErrorSignal()`. Probe now logs an explicit "matches an ERROR envelope" note when only `HasErrorSignal()` fires, distinguishing captured-success from captured-error in reviewer-visible output.

Result: passes for the required risky shapes (P2/P3/P4). The split predicate cleanly distinguishes a successful result envelope from an error envelope so that future probe data with `detail` arrays is explicitly classified as error evidence, not silently accepted as success.

---

## The Six Contract Decisions

### Decision 1 — Provider Lifecycle

**Statement:** Phase 1 must abstract over multiple lifecycle shapes that differ in invocation mode, terminal-state semantics, state-name casing, fetch-from-where, and error/success discrimination.

**Evidence:**

| Provider/Path | Invocation | Terminal-state name | Result location | Cancel | HTTP status pattern |
|---|---|---|---|---|---|
| **B2 Veo** (code-read) | Async polling | (operation-style) | Fetch URL | Supported | (per code) |
| **B1 Gemini** | Sync inline | n/a (no polling) | Submit response body | n/a | 200 throughout |
| **P1 fal sync** | Sync inline | n/a | Submit response body | n/a | 200 throughout |
| **P1q fal queue** | Async polling | `COMPLETED` (UPPERCASE) | **Separate `response_url` GET** | `cancel_url` exposed (PUT method per Hunyuan schema) | **202** non-terminal, 200 terminal |
| **P2 fal queue video** | Async polling | `COMPLETED` (UPPERCASE) | **Separate `response_url` GET** | `cancel_url` exposed | **202** non-terminal, 200 terminal |
| **P4 fal queue 3D** | Async polling | `COMPLETED` (UPPERCASE) | **Separate `response_url` GET** | `cancel_url` exposed | **202** non-terminal, 200 terminal |
| **P3 Replicate** | Async polling | `succeeded` (lowercase) | Terminal poll body INCLUDES `output` (no separate fetch) | `urls.cancel` (POST) | 200 throughout |
| **P5 Tencent direct** (docs) | Async via SDK Submit+Query method pairs | (per-endpoint typed responses) | SDK Query call returns typed result | (per-endpoint cancel docs; not exercised) | (handled by SDK) |

**Key sub-findings from the spike:**
- **fal queue's `COMPLETED` is TERMINAL not SUCCESS.** P4_validation_rejection captured a `COMPLETED` lifecycle whose `response_url` then returned HTTP 422 with a FastAPI `detail` envelope. The success/failure split happens at the **fetch step**, not the queue state. The spike harness now computes manifest outcome via `determine_outcome(submit_response, fetch_status)` reflecting this.
- **Case-insensitivity matters.** Veo + Replicate use lowercase state names; fal queue uses UPPERCASE. The harness's terminal-state check originally lowercased only at the canonical set (Replicate-shaped); patched to also lowercase the observed value at comparison time. Original case is preserved in `notes.md` for evidence.
- **fal queue requires a separate fetch step** from `response_url`; the polled status body has only metrics, no result. Replicate embeds `output` in the terminal poll. Different I/O shapes for the "give me the result" operation.

**Phase 1 binding (testable):**
- `IGenerationProvider.SubmitAsync` must return a discriminated result encoding the invocation mode (sync vs queued). Exact shape — `Sync(result) | Queued(handles)` discriminated union vs uniform job-record where sync providers produce already-terminal jobs — is a Phase 1 design decision; the constraint is that **sync and async paths cannot share a single submit-then-poll-then-fetch contract.**
- Provider adapters normalize state names (case-insensitive, mapped to a canonical set: `pending | running | completed | failed | canceled`).
- Lifecycle adapters distinguish "terminal state reached" from "operation succeeded" — for fal queue, success/failure discrimination requires inspecting fetch HTTP status and body shape, not just queue-state name.
- Cancellation method varies (`PUT` for fal Hunyuan, `POST` for Replicate) — adapters encapsulate.

**What would reopen this:** Discovery of a provider whose lifecycle doesn't fit "submit → 0..N polls → fetch (or terminal-body-yields-result)" — e.g., a streaming-only provider, webhook-callback-only provider (we noted Replicate has `urls.stream` but didn't probe it), or stateful conversation-style provider (Anthropic Messages?). All defer to Phase 2+.

---

### Decision 2 — Capability Schema

**Statement:** Phase 1's capability flags must accommodate per-route feature flags that vary even within a single provider; flat "is image-capable" booleans are insufficient.

**Evidence (image/video — fully bound):**
- **Image** (B1, P1, P3): all probed routes accept text-to-image with synthetic prompt; image-to-image is documented per provider but not separately probed
- **Video** (P2): text-to-video probed (Wan v2.7); image-to-video and frame-interpolation documented per provider catalog but not separately probed
- **Capability subdivisions matter for Phase 1 routing**: a model that supports T2I but not I2I is a different capability than a multi-mode model. fal alone has both.

**Evidence (3D — provisional under carve-out):**
- **Hunyuan3D Pro v3.1 on fal (P4 gating success):** image-to-3D, optional 8-view multi-input, configurable face_count (40K–1.5M, default 500K), optional PBR materials, geometry-only mode, multi-format output (GLB/OBJ/FBX/USDZ/MTL/texture)
- **Hunyuan3D direct on Tencent (P5 docs only):** image-to-3D Pro tier + Rapid tier, Part Segmentation, Smart Topology (retopology), UV Unwrapping, Texture Editing, Format Conversion — **none of these advanced features are available via fal**

**Phase 1 binding (testable):**
- **Image and video capability schema is bound.** Per-route capability flags (text-to-image, image-to-image, text-to-video, image-to-video, frame interpolation, etc.) are required. Flat per-provider booleans are insufficient because a single provider hosts multiple modes per model.
- **3D evidence is captured but stored as opaque route descriptors only.** Per the design carve-out, Phase 1 must not freeze 3D semantics beyond opaque `modality: "3d"` + capability-name strings. The detailed 3D feature list (multi-view input, PBR, geometry-only, face_count, segmentation, retopology, UV editing, texture editing, format dispatch) is captured in this spike doc (P4 + P5 evidence) for Phase 4's `IThreeDProvider` work to consume — Phase 1's image/video capability schema must not preclude future 3D-specific descriptor types, but must not name them either.

**What would reopen this:** Phase 4 implementing `IThreeDProvider` will need to revisit and bind 3D-specific capability detail. Until then, image+video capability schema is bound; 3D-specific shape is **constrained-not-bound** — the spike's evidence rows above describe what 3D providers actually expose, but Phase 1 should treat 3D as `modality + opaque capability strings` only.

---

### Decision 3 — Pricing Estimate Shape

**Statement:** No shared pricing formula exists across providers. `IPricingModel` must support multiple metric units (megapixel, output-second, compute-second, token, call), multiple metadata locations (response header vs. body), and per-model-class per-unit rates within a single provider.

**Evidence — five distinct pricing patterns across the spike:**

| Provider/Model | Pricing model | Where reported |
|---|---|---|
| fal `fal-ai/flux/schnell` (sync image) | per-megapixel (`$0.003/MP`) | header `x-fal-billable-units` |
| fal `fal-ai/wan/v2.7/text-to-video` (queue) | per-output-second × resolution multiplier (`$0.10/sec @720p, $0.15/sec @1080p`; ratio = 1.5× for 1080p) | header `x-fal-billable-units` (per-unit rate `$0.10` for video) |
| fal `fal-ai/hunyuan-3d/v3.1/pro/image-to-3d` (queue) | flat per-call (`$0.375`) plus optional add-on surcharges (`+$0.15` PBR, `+$0.15` multi-view, `+$0.15` custom face_count) | header `x-fal-billable-units: 25` (per-unit rate `$0.015` for 3D) |
| Replicate `black-forest-labs/flux-schnell` | per-compute-second on declared hardware | body `metrics.predict_time` (0.507s observed) and `metrics.total_time` (0.543s) |
| Gemini `gemini-3.1-flash-image-preview` | per-token-by-modality | body `usageMetadata.{promptTokenCount, candidatesTokenCount, *TokensDetails: [{modality, tokenCount}]}` |

Critical observation: **fal alone uses three different per-unit rates** for the `x-fal-billable-units` header (`$0.003/MP`, `$0.10/output-second-equivalent`, `$0.015/per-call-unit`), so the header is not a portable cost signal — Phase 1 must record the per-model rate alongside model registration.

**Phase 1 binding (testable):**
- `IPricingModel` is per-provider, possibly per-model. No shared base class beyond a `CostEstimate { Min, Max, IsExact, Provenance }` typed return.
- Cost estimator must read both **response headers** AND **response body** depending on provider.
- Estimator must distinguish `IsExact` (Veo per-second, fal flat-call) from `IsEstimate` (Replicate predict-time depends on hardware contention; aggregator margin not measured).
- Provider implementations declare the rate at registration (fal sync FLUX = $0.003/MP, fal Wan = $0.10/output-second × {tier_multiplier}, fal Hunyuan Pro = $0.375/call + add-ons, Replicate FLUX = whatever per-second hardware rate Replicate publishes, Gemini = published per-token rates).

**What would reopen this:** A sixth provider with a structurally different shape (subscription credits, request quotas with overage, per-conversation rates, etc.) would expand the model. None observed in this spike.

---

### Decision 4 — Options Codec Boundaries

**Statement:** Submission contracts vary by provider, and within a single provider by model class (Replicate community vs official, fal raw HTTP vs fal queue, etc.). `ProviderOptions` is genuinely per-provider and per-route.

**Evidence — five+ distinct submission contracts:**

| Provider/Path | Submission contract |
|---|---|
| fal sync (FLUX schnell) | `POST /{model}` with body `{prompt: ...}` (flat) |
| fal queue (Wan, Hunyuan3D) | `POST /{model}` with body containing model-specific required+optional fields (e.g., Hunyuan: `input_image_url` required, 7 optional view URLs, `face_count`, `enable_pbr`, `generate_type`) |
| Replicate **community** | `POST /v1/predictions` with body `{version: <hash>, input: {...}}` — version field required |
| Replicate **official-model** | `POST /v1/models/{owner}/{name}/predictions` with body `{input: {...}}` — no version field; model in URL |
| Gemini | `POST /v1beta/models/{model}:generateContent` with body `{contents: [{parts: [{text, inlineData}]}], generationConfig: {responseModalities: [...], imageConfig: {imageSize: ...}}}` — multi-part content with modality-aware response config |
| Tencent direct (docs) | SDK-mediated: typed request classes per endpoint (`SubmitHunyuanTo3DProJobRequest`) populated via attribute assignment or `from_json_string`, dispatched via `HunyuanClient.SubmitHunyuanTo3DProJob(req)`, returns typed response. Auth via paired credentials + TC3-HMAC-SHA256 signing handled by `tencentcloud-sdk-python` |

**Replicate's dual-endpoint reality** is itself Decision 4 evidence: the same provider exposes two submission contracts (community via `/v1/predictions` requires version hash, official via `/v1/models/{owner}/{name}/predictions` doesn't). Phase 1's Replicate provider implementation has to model both at provider/route configuration level.

**Field name variation within fal alone**: `image` for some endpoints, `image_url` for others, `input_image_url` for Hunyuan. The spike's harness exposed `--image-field` flag to handle this; Phase 1's fal provider needs a per-route input mapping.

**Phase 1 binding (testable):**
- Per-provider `ProviderOptions` records (no shared shape beyond an opaque base type).
- Per-route input field mapping config — fal Hunyuan ≠ fal FLUX ≠ fal Wan in input field names.
- Replicate provider must support endpoint+body-shape selection (community vs official); modeled as route configuration, not user-facing.
- Tencent direct is a structurally different category from raw-HTTP providers (SDK-mediated). Phase 1 should accommodate SDK-wrapped providers as a first-class kind, distinct from raw-HTTP providers.

**What would reopen this:** New provider with a contract genuinely incompatible with the patterns above (e.g., gRPC-only, non-JSON submission, websocket-streamed input). None observed.

---

### Decision 5 — Result/Artifact Roles

**Statement:** Result envelope shape varies fundamentally by provider — including delivery mechanism (URL-referenced vs inline-bytes), single-vs-array, structured-metadata-vs-flat, and multi-format dispatch for 3D.

**Evidence — five fundamentally different success-result envelope shapes:**

```
fal sync image       -> { images: [{url, content_type, width, height}], has_nsfw_concepts, prompt, seed, timings }
fal queue video      -> { actual_prompt, seed, video: {url, content_type, duration, fps, num_frames, width, height, file_size, file_name} }
fal queue 3D         -> { model_glb: {url, ...}, model_urls: {glb, obj, fbx, mtl, texture, usdz} (each File or null), thumbnail, seed }
Replicate prediction -> { id, status, output: [<url>], urls.{get, cancel, stream, web}, metrics.predict_time, ... }
Gemini               -> { candidates: [{content: {parts: [{inlineData: {data: <base64>, mimeType, thoughtSignature}}], role: "model"}, finishReason}], modelVersion, responseId, usageMetadata }
```

**Critical finding — delivery mechanism axis:**
- **fal, Replicate**: result is **URL-referenced** on a separate CDN host (`v3b.fal.media`, `replicate.delivery`); client follows URL to fetch bytes
- **Gemini**: result bytes are **inline** in the JSON response (`inlineData.data: <base64>`); no follow-up fetch

This is a structural axis that Phase 1's result envelope abstraction must support. Trust posture differs:
- URL-based: bytes live on provider CDN, fetched on demand, may have signed-URL TTL
- Inline-based: bytes arrive in API response, no follow-up GET, payload size is much larger

**Multi-format dispatch (3D-only — Phase 4 evidence, not Phase 1 binding):**
- Hunyuan3D's `model_urls` returns up to 6 format variants per call (GLB, OBJ, FBX, USDZ, MTL, texture). Some are `null` per call (FBX, USDZ were null in P4 success). Per the design carve-out, this captures what 3D providers actually return — Phase 4's `IThreeDProvider` work will need to model "output formats are possibly null per call" rather than a guaranteed set.
- `model_glb` and `model_urls.glb` are duplicate references to the same File. Phase 4's 3D result handling will need to deduplicate to avoid double-counting storage.

**Error envelope shape (P4-err):**
- fal queue (Hunyuan3D) returns FastAPI-style `detail: [{loc, msg, type, url}]` array on validation rejection
- HTTP 422 status; `x-fal-billable-units: 0`; `x-fal-needs-retry: false` headers
- This is documented as **error-envelope evidence only**, not result evidence; the C# probe distinguishes via `HasErrorSignal()` vs `HasLifecycleOrResultSignal()`

**Phase 1 binding (testable):**
- **Image and video result envelopes are bound.** Provider adapters normalize their native shape into a canonical Phase 1 result type. Each result is either `Url`-referenced or `Bytes`-inline (Phase 1's `ResultArtifact` type carries one or the other, never both).
- **Result delivery axis (URL-referenced vs inline-bytes) must be supported from day one.** Gemini's inline-bytes pattern is not exotic; future text-output providers will likely use it too. Phase 1's `ResultArtifact` should NOT assume URL delivery.
- **Error envelope discrimination at fetch step.** Provider adapters classify response as `Result` vs `Error` based on HTTP status + body shape; canonical error type carries `provider_error_code`, `loc_path`, `human_message`, `is_retryable` derived from headers like `x-fal-needs-retry`.
- **3D multi-format result delivery is captured here as evidence for Phase 4.** Phase 1 must not preclude future multi-format result descriptors (so the `ResultArtifact` shape should compose, not be a sealed enum), but Phase 1 should NOT name `IThreeDProvider`, `model_glb`, `model_urls`, or any 3D-specific result fields.

**What would reopen this:** A provider returning streaming chunks (Replicate `urls.stream` not yet probed), partial results, or async webhook delivery of artifacts. None observed in the spike.

---

### Decision 6 — Secret-Key Namespace

**Statement:** Secret store must support both single-token providers and paired-credential signature-scheme providers, with provider-specific header conventions.

**Evidence — four distinct auth header conventions:**

| Provider | Auth header | Credential shape |
|---|---|---|
| fal | `Authorization: Key <token>` | Single token |
| Replicate | `Authorization: Token <token>` | Single token |
| Gemini | `x-goog-api-key: <token>` | Single token |
| Tencent direct (P5 docs) | TC3-HMAC-SHA256 signed `Authorization` header per request | **Paired**: `SecretId` + `SecretKey` (env: `TENCENTCLOUD_SECRET_ID` + `TENCENTCLOUD_SECRET_KEY`); optional STS Token third arg |

Phase 1 must accommodate both single-token and paired-credential models, plus per-provider header naming. The `x-goog-api-key` form rules out an `Authorization`-only assumption.

Tencent's signed-request model means Phase 1's secret store can't simply hand the credential pair to an HTTP client — Tencent provider must use `tencentcloud-sdk-python` (or implement the signature scheme manually, which is ~50 LOC of error-prone HMAC chaining and not recommended).

**Phase 1 binding (testable):**
- `ISecretStore` keys must be per-provider, supporting both single-token (`fal.api_key`, `replicate.api_token`, `gemini.api_key`) and multi-key shapes (`tencent.secret_id` + `tencent.secret_key`, optional `tencent.sts_token`).
- Header construction is per-provider implementation, not a shared formatter.
- Tencent (and likely future Aliyun, AWS Bedrock providers) is a **SDK-mediated** kind: provider implementation invokes a vendor SDK rather than constructing HTTP requests directly. Phase 1 should accommodate this category, not assume all providers are HTTP-direct.

**What would reopen this:** A provider with rotating credentials, OAuth2, or mTLS. Not observed in the spike, but Tencent's STS Token support hints that ephemeral-credential support is on the roadmap.

---

## Go/No-Go Assessment

Per design Section 1 strict gate:

| Required for Phase 1 | Status |
|---|---|
| Provider lifecycle | ✅ bound |
| Image/video capability schema sufficient for Phase 1 | ✅ bound |
| Pricing estimate shape | ✅ bound (5 distinct patterns mapped) |
| Options codec boundaries | ✅ bound (per-provider, per-route) |
| Image/video result+artifact roles | ✅ bound (URL vs inline-bytes; per-provider envelopes) |
| Secret-key namespace | ✅ bound (single-token + paired-credential, per-provider header) |

**Allowed deferral (3D carve-out):** ✅ Hunyuan evidence captured via P4 + P5; Phase 1 must NOT introduce public `IThreeDProvider` / `ResolvedThreeDModel` / shared base fields encoding 3D semantics beyond opaque modality/capability descriptors. 3D-specific advanced features (segmentation, retopology, UV editing) deferred to Phase 4.

**Hard "no defer":** lifecycle ✅, pricing ✅, options codec ✅, secret-key namespace ✅ — all four Phase-1-load-bearing decisions are bound with evidence and testable bindings.

**Verdict: gate satisfied. Phase 1 is unblocked.**

---

## Phase 2 Implications (informational; not gating)

The spike surfaced operational characteristics that inform Phase 2 (UX + multi-aggregator) scope:

- **Cold-start latency.** First-call to a fal model can take 60+ seconds while a worker spins up (observed ~0.34s warm submit, but 2-3 minute cold-start for Wan v2.7 and Hunyuan3D Pro). Phase 2 picker UX should display a "first call may be slower" indicator.
- **Polling cadence per-model.** Replicate FLUX schnell completed in 0.5s GPU compute, but the harness's 2s polling interval dominated wall-clock. Phase 2's polling strategy needs per-model tuning (or exponential backoff).
- **HTTP status code conventions differ.** fal queue uses `202 Accepted` for in-flight polls and `200 OK` for terminal; Replicate is `200` throughout. Phase 1 should not key off HTTP status alone — body status field is the canonical signal.
- **Server-side request IDs.** Every probed provider exposes one in headers (`x-fal-request-id`, `replicate-prediction-id`, Gemini's `responseId`). Phase 2's debug UX should surface these for support escalation.
- **Aggregator margin.** Both fal and Replicate add margin over raw GPU cost; specific numbers not measured this spike (would require comparing fal-hosted vs direct prices). Phase 2's cost estimator should disclose `IsEstimate` for aggregator-routed costs.

---

## Phase 4 Implications (Tencent direct + advanced 3D)

P5's audit revealed that **Tencent's direct Hunyuan service exposes substantially more functionality than fal's hosted endpoint**:

| Capability | fal `fal-ai/hunyuan-3d/v3.1/pro/image-to-3d` | Tencent direct |
|---|---|---|
| Pro tier image-to-3D | ✅ | ✅ |
| Rapid tier (faster, lower quality) | ❌ | ✅ |
| Part segmentation | ❌ | ✅ |
| Smart retopology | ❌ | ✅ |
| Texture editing | ❌ | ✅ |
| UV unwrapping (standalone job) | ❌ | ✅ |
| Format conversion | ❌ | ✅ |

**Phase 4 priority:** if 3D becomes a flagship product surface for Rook (image-to-CAD, scene-from-photo, parts-based modeling workflows), **Tencent direct should be the primary backend**, with fal's Hunyuan3D Pro as the lighter/cheaper option for users who only need basic Pro-tier generation.

**Phase 4 design inputs from this spike (Phase 1 should not bind these, but Phase 4 will):**
- 3D result envelopes use **multi-format dispatch** as a first-class concept — Hunyuan returns up to six format variants per call (GLB, OBJ, FBX, USDZ, MTL, texture), some null per call. `IThreeDProvider` results need a typed multi-format container, not a single URL or array.
- 3D capability flags need to model: input view count (1–8), PBR support, geometry-only mode, polygon density control (face_count range), and the advanced-features matrix from P5 (Pro/Rapid tier, segmentation, retopology, UV editing, texture editing, format conversion).
- Input field name varies even for image-input 3D models (`image` vs `image_url` vs `input_image_url`); per-route input-mapping config is required.
- Tencent direct uses Submit + Query method pairs **per job type** (one pair per endpoint), not a unified queue — `IThreeDProvider` for Tencent must dispatch by job type internally.

**Phase 4 starter kit (already gathered):**
- `tencentcloud-sdk-python` package (single dep)
- Module path `tencentcloud.hunyuan.v20230901`
- Endpoint `hunyuan.intl.tencentcloudapi.com`
- Auth env vars `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`
- SDK sample code at `docs/rook_docs/tencent_api_md/sample_python_75e13ea8-df6b-43d2-a3d8-71125b9a7f4e/` (gitignored, local-only)
- Quickstart PDF at `docs/rook_docs/tencent_api_md/1281_74125_en.pdf` (gitignored)

Live API call deferred from Phase 0 because CAM sub-user setup with Hunyuan-scoped permissions is ~30–60 minutes of work that's better done at Phase 4 kickoff with concrete product surface to validate against.

---

## Open Follow-Ons

Items the spike could not fully answer; track for Phase 2+ or Phase 4:

1. **Aggregator margin numbers.** Phase 2's cost estimator UX needs concrete margin observations vs raw provider pricing.
2. **Cold-start latency distribution.** Per-model first-call vs warm-call timing across all providers.
3. **Cancellation actually exercised.** Documented for fal, Replicate; not live-tested on a probe.
4. **Replicate community-model endpoint probed.** We did official only; community-style with version hash captured documentarily but not run.
5. **Replicate streaming endpoint** (`urls.stream`) — present in P3 capture, not exercised.
6. **fal queue I2V path probed.** P2 was T2V; image-to-video is documented but not separately captured.
7. **Per-modality polling cadence guidance** for Phase 1 (related to point #2 in Phase 2 implications above).
8. **Error retry classification.** `x-fal-needs-retry` header observed; haven't established a comprehensive map of retryable vs permanent across providers.

---

## Iteration Log

- **v1.0 (2026-04-27):** Initial spike-results doc. Six contract decisions all bound; gate satisfied; 3D-specific capability detail deferred under design carve-out (Hunyuan evidence captured via P4 + P5). Phase 1 unblocked; Phase 4 starter kit assembled. Total cost ~$1.13 of $25 hard stop.
