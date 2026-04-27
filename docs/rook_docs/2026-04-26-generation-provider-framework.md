# Generation Provider Framework: Aggregators, Multi-Modality, and the 2D→3D Foundation

**Date:** 2026-04-27 (v0.2)
**Status:** v0.2 — Phase 0 evidence folded in; Phase 1 unblocked
**Related:**
- [`2026-04-27-multi-provider-spike.md`](2026-04-27-multi-provider-spike.md) — **Phase 0 spike evidence** (six contract decisions bound, all probes complete, gate satisfied)
- [`2026-04-22-v3-video-decisions.md`](2026-04-22-v3-video-decisions.md) — v3.1 video contract; the seam shapes (`IVideoProvider`, `IPricingModel`, `IProviderOptionsCodec`, `ResolvedVideoModel`) that this doc proposes to generalize.
- [`2026-04-26-video-nle-bridge-design.md`](2026-04-26-video-nle-bridge-design.md) — the NLE realization roadmap; this framework's outputs feed the NLE's "swap models per node" capability.
- [`2026-04-08-sa-banana-integration.md`](2026-04-08-sa-banana-integration.md) — image-track architecture; the visual-subsystem pattern that this framework extends across modalities.
- [`2026-04-09-grasshopper-video-nle.md`](2026-04-09-grasshopper-video-nle.md) — original NLE vision; the "cheap GH preview, expensive Veo hero shot" pattern is unlocked by multi-provider routing.
- [fal.ai docs](https://fal.ai/docs) — first candidate aggregator; serverless inference with per-call billing.
- [Replicate docs](https://replicate.com/docs) — second candidate aggregator; mature catalog, prediction-API model.
- [Tencent Hunyuan3D-2 on Hugging Face](https://huggingface.co/tencent/Hunyuan3D-2) — anchor 2D→3D model; available on fal.ai, Replicate, and direct.

---

## TL;DR

RookVision today is locked to **two providers from one vendor:** Gemini (image) and Veo (video), both Google. That's a single-vendor risk, a coverage gap (no 2D→3D, no upscaling, no specialized image models like SDXL/FLUX), and a future bottleneck for the GH NLE's "use the right model for each shot" promise.

The V1c video work shipped a clean per-model abstraction (`IVideoProvider`, `IPricingModel`, `IProviderOptionsCodec`, `ResolvedVideoModel`) that already supports multi-provider registration in principle — the registry just hasn't seen anyone but Veo. **The strategic move is to generalize that abstraction across modalities (image, video, 3D, future) and add aggregator-backed providers (fal.ai, Replicate) so we get hundreds of models without per-vendor integration work.**

The non-obvious framing: aggregators are not a separate concept from "providers." They are providers that happen to register many models from one HTTP surface. The architectural delta is small if the abstraction is right; the work is mostly catalog construction, options-codec authoring, and UX for choosing among many models.

This doc proposes a phased path from "Veo + Gemini hardcoded" to "Veo + Gemini + fal.ai + Replicate + Tencent direct + (whatever comes next), with consistent UX, cost estimation, and per-model capability discovery."

---

## Why this matters now

Three pressures converging:

1. **The GH NLE design depends on it.** The NLE bridge doc explicitly anticipates "use Veo for the hero shot, SDXL for thumbnail mockups, Hunyuan for previz" — that promise is empty without multi-provider routing. The NLE Tier 4 cache-index design (clip_hash → artifact_id) gets simpler if every model maps onto the same `ResolvedModel` abstraction.
2. **The 2D→3D pipeline is next on the roadmap.** Per the script library / image-to-CAD memory, the 2D→3D capability is a distinct product surface that will ship in the next quarter. If we wait until then to design the multi-provider framework, we'll repeat the per-vendor copy-paste from V1, which the V1c review rounds explicitly tried to avoid.
3. **Single-vendor risk is real.** Google can deprecate Gemini-2-flash-image (already happened to earlier variants), can rate-limit, can change pricing, can refuse policy categories. A user whose architectural visualization workflow depends on Rook needs at least one fallback model per capability.

The cost of doing this now vs. later is roughly inverted: now is a couple of weeks of focused refactor work; later is the same refactor plus migration of every per-modality stack we accreted in the meantime.

---

## What V3/V4 actually shipped (load-bearing inventory)

Verified against `main` at commit `f4ecb4e`:

### Video provider abstraction (V1c, the template we'll generalize)

- **`IVideoProvider`** + **`VeoProvider`** — submit/cancel methods, returns typed result envelopes. The abstraction works; Veo is currently the only impl.
- **`IVideoProviderRegistry`** + **`DefaultVideoProviderRegistry`** — resolves `model_id → ResolvedVideoModel`. Build-time invariants: non-empty model id, cap.Id matches dictionary key, no duplicate model ids across registrations, **but duplicate provider names are allowed** (already aggregator-friendly).
- **`ResolvedVideoModel { ModelId, ProviderName, Provider, Capability, PricingModel, OptionsCodec }`** — the per-model bundle. Every field is per-model, not per-provider.
- **`IPricingModel`** + **`PerSecondPricingModel`** — bound at the resolved-model edge. One concrete impl shipped; aggregators will need their own (`PerCallPricingModel`, `PerComputeSecondPricingModel`, etc.).
- **`ProviderOptions`** abstract record + **`VeoOptions`** sealed record + **`IProviderOptionsCodec`** — typed options per provider, validated/serialized through a codec. Already extensible to N providers.
- **`ModelCapability`** — encodes `{Modes, Resolutions, Durations, AspectRatios, SupportsReferenceImages, MaxReferenceImages, Must8sWith}`. Video-shaped today; would need a sibling `ImageCapability` / `ThreeDCapability`.

### Image provider state (no abstraction yet)

- **`VisionHandler.cs`** dispatches `generate` and `enhance_prompt` ops. The provider client is hardcoded — there is no `IImageProvider` interface and no provider registry.
- **Models are configured via short-name → full-id mapping** (`nano-banana-2`, `nano-banana-pro`, etc., all Gemini variants).
- **Settings:** single Gemini API key in DPAPI'd `VisionSecretStore`. No multi-provider key support.
- **Capability validation** is hardcoded against Gemini's known matrix (per-model resolutions, etc.).
- **No equivalent of `IPricingModel`** — pricing for image generation is mentioned in the SA_Banana plan but not formally surfaced.

### What does NOT exist yet

- **No image provider interface.** A future `IImageProvider` would mirror `IVideoProvider`'s shape but with image-specific request/response types.
- **No 3D provider interface.** A future `IThreeDProvider` for image-to-mesh, text-to-mesh, etc.
- **No aggregator client classes.** No `FalApiClient`, no `ReplicateApiClient`.
- **No multi-key settings UI.** Settings v1 assumes one provider per modality.
- **No catalog persistence beyond hardcoded registries.** Adding a model means a code change.
- **No model-picker UX beyond a flat dropdown.** Won't scale past ~20 entries; aggregator catalogs have hundreds.

**The gap, stated precisely:** the video-side abstraction is correctly shaped for multi-provider/multi-aggregator extension, but it has only ever been exercised with one provider. The image side has none of the abstraction. The 3D side doesn't exist. Aggregator support — the keystone — is wholly absent. Phase 0 scratch harnesses do not count as production provider implementations.

> **Phase 0 update (2026-04-27):** the spike captured live evidence against four providers (fal.ai sync, fal.ai queue, Replicate prediction, Gemini direct) plus a Tencent direct-API documentation+SDK audit. Phase 1's design now has empirically grounded bindings for all six contract decisions; see Phase 0 Evidence Summary below and the [spike doc](2026-04-27-multi-provider-spike.md).

---

## Phase 0 Evidence Summary (added v0.2)

Phase 0's spike (commits `7550e56` → `73c2f89` on `spike/multi-provider-phase0`; ~$1.13 of $25 hard stop spent) captured ground-truth contracts and produced testable Phase 1 bindings for all six contract decisions:

| Decision | Phase 1 binding (from spike) |
|---|---|
| **1. Provider lifecycle** | Sync ≠ async — `IGenerationProvider` submit must encode invocation mode discriminately. Provider adapters normalize state-name casing (Replicate lowercase, fal queue UPPERCASE). fal queue's `COMPLETED` is *terminal not success* — fetch step is where success/failure is discriminated; lifecycle adapter must inspect fetch HTTP status + body shape. Cancellation methods vary (`PUT` for fal Hunyuan, `POST` for Replicate). |
| **2. Capability schema** | Per-route capability flags (not flat per-provider booleans). **Image and video capability schema is bound; 3D capability shape is constrained-not-bound** — 3D evidence is captured (P4 + P5) for Phase 4 to consume, but Phase 1 must not name 3D-specific fields beyond opaque modality/capability descriptors. Advanced 3D features (segmentation, retopology, UV editing — Tencent-direct only) deferred to Phase 4. |
| **3. Pricing estimate shape** | Five distinct patterns documented (per-MP, per-output-second × tier, per-call flat + add-ons, per-compute-second, per-token-by-modality). Two metadata locations (response header vs body). fal alone uses three different per-unit rates for the same `x-fal-billable-units` header, so the header is not a portable cost signal. `IPricingModel` is per-provider, possibly per-model, with `CostEstimate { Min, Max, IsExact, Provenance }` typed return. |
| **4. Options codec boundaries** | At least five distinct submission contracts captured. Replicate has dual-endpoint variation (community vs official); fal has per-model input field name variation (`image` vs `image_url` vs `input_image_url`). Tencent direct is an SDK-mediated category, structurally different from raw-HTTP providers. Per-provider, per-route options codec — no shared shape. |
| **5. Result/artifact roles** | Five fundamentally different envelope shapes. Critical structural axis: **URL-referenced (fal/Replicate) vs inline-bytes (Gemini)** delivery. Phase 1's `ResultArtifact` must support both delivery models from day one. Error envelope (FastAPI-style `detail` array) is distinct from result envelope and discriminated at fetch step. **3D multi-format result evidence is captured for Phase 4** — Phase 1 should compose `ResultArtifact` rather than seal it, but must not name 3D-specific fields. |
| **6. Secret-key namespace** | Three distinct auth header conventions (`Authorization: Key/Token/...`, `x-goog-api-key`). Tencent introduces paired-credential signature-scheme providers (SecretId+SecretKey, TC3-HMAC-SHA256 via SDK). `ISecretStore` must support both single-token and multi-key shapes; header construction is per-provider, not a shared formatter. |

**Strict gate verdict (per design Section 1):** satisfied. All four hard-no-defer decisions (lifecycle, pricing shape, options codec, secret-key namespace) bound with evidence. 3D-specific carve-out applied (Hunyuan evidence captured via P4 + P5; Phase 1 not to freeze 3D abstractions).

**Phase 4 strategic finding:** Tencent's direct Hunyuan service exposes substantially more functionality (Rapid tier, Part Segmentation, Smart Topology, UV Unwrapping, Texture Editing, Format Conversion) than fal's hosted endpoint. If 3D becomes a flagship product surface, Tencent direct should be the primary backend with fal as a lighter alternative. Phase 4 starter kit assembled (SDK pattern, env vars, endpoint, sample code, Quickstart PDF).

See the spike doc for full evidence rows, side-by-side cross-provider comparison tables, and per-Decision "what would reopen this" conditions.

---

## Strategic question: aggregator vs. direct integration

Aggregators (fal.ai, Replicate, also Sieve, Together, Modal, etc.) provide a uniform HTTP API that fronts many model-hosting backends. Tradeoffs are real and orthogonal to "is the aggregator any good":

### Aggregator pros

- **One integration covers many models.** A single `FalApiClient` registers as N `ResolvedVideoModel` / `ResolvedImageModel` / `ResolvedThreeDModel` entries.
- **Authentication is one key per service**, not one per model. Reduces settings-UX surface area significantly.
- **Aggregator handles billing.** No per-model account creation, no per-vendor invoicing.
- **Catalog growth is free.** When fal.ai adds a model, we can pick it up via a config tweak rather than a code release (if we design for dynamic catalog discovery; see Phase 5).
- **Reliable async pattern.** Most aggregators have polling + webhook flows; we already have polling infrastructure from V2/V3.

### Aggregator cons

- **Margin on top of raw cost.** fal.ai is typically 20–40% above raw GPU cost; Replicate similar. Materially affects cost estimation precision.
- **Latency.** Aggregator queues add seconds to minutes under load. Veo direct is faster than Veo via fal.ai (when fal.ai hosts it, which it currently does not).
- **Model coverage gaps.** Veo, Gemini, OpenAI, Claude — none of these are on aggregators. We still need direct integrations for vendor-specific models.
- **Trust surface.** A third party sees prompts and (for image-to-X) input images. Matters for some user contexts; not for others.
- **Aggregator can deprecate.** When fal.ai removes a model, our users lose access mid-workflow.
- **Less control.** Per-model HTTP behavior tuning isn't available.

### The hybrid posture (recommended)

**Both, deliberately.** Direct providers for vendor-specific or trust-sensitive flows; aggregators for everything else. The framework must be agnostic to which is which — both implement the same provider interface, both register the same `ResolvedModel` shape. The user picks a model; the framework dispatches to the right backend.

This is the explicit non-decision: we do NOT pick fal.ai over Replicate (or vice versa) at the framework level. Both can be supported. The choice of "which aggregator first" is a Phase 2 scope decision, not a framework decision.

---

## The capability lattice

The current video-only abstraction has one capability axis: video generation modes (T2V, I2V, Interp). Generalizing requires explicitly modeling capabilities as a lattice across modalities.

| Modality | Sub-capability | Current Rook coverage | Example providers |
|---|---|---|---|
| **Image generation** | text-to-image | Gemini (Nano Banana) | fal.ai (FLUX, SDXL, SDXL Lightning), Replicate (SDXL, Playground), direct (Stability, OpenAI) |
| | image-to-image | Gemini (Nano Banana) | fal.ai (FLUX, SDXL inpaint), Replicate (FLUX) |
| | upscale | none | fal.ai (Real-ESRGAN, AuraSR), Replicate (Real-ESRGAN, Topaz) |
| | depth/segmentation | none | fal.ai (Depth Anything, SAM 2), Replicate (depth, segmentation) |
| **Video generation** | text-to-video | Veo | fal.ai (Kling, Mochi, Runway, eventually Veo via partner) |
| | image-to-video | Veo | fal.ai (Kling I2V, Mochi I2V), Replicate (Stable Video Diffusion) |
| | frame interpolation | Veo | fal.ai (FILM, RIFE) |
| | upscale | none | fal.ai (video upscalers), Topaz direct |
| **3D generation** | image-to-mesh | none | fal.ai (Hunyuan3D-2, TripoSR), Replicate (Hunyuan, Meshy), direct (Tencent Studio) |
| | text-to-mesh | none | fal.ai (Hunyuan3D-2 T2M variant), Replicate (Shap-E) |
| | depth-to-3D | none | implementation-specific (Marigold + depth + lift) |
| **Other** | speech (TTS / STT) | none | fal.ai, Replicate, ElevenLabs direct |
| | translation, embedding, etc. | none | (out of scope for RookVision but conceptually adjacent) |

**The framework needs to encode capability such that the picker UI can sensibly group, filter, and recommend.** A flat `ModelCapability` record per model is insufficient. Likely shape:

```csharp
public sealed record ModelCapability(
    string Modality,        // "image" | "video" | "3d"
    string[] SubCapabilities, // e.g. ["text_to_image", "image_to_image"]
    // ... modality-specific structured fields ...
)
```

Or a discriminated-union approach with `ImageCapability : ModelCapability`, etc. Decision deferred to Phase 1 design.

---

## Product / UX dimensions

The framework's success metric is not "the abstraction is clean" — it's "a user with no ML background can pick the right model for their task and run it without fighting the UI." This section explores what that means in practice.

### Model selection UX

**Today:** flat dropdown, ~5 entries, all Gemini.
**Future:** ~50–500 entries across providers and modalities. Flat dropdown breaks at ~20.

Required surfaces:

- **Capability-first browsing.** The user is picking "I want a depth map" or "I want a 3D mesh from this image"; they shouldn't need to know that "Hunyuan3D-2" is the model name. Filter by sub-capability.
- **Recommended / Featured / Recent.** Most users will use a small subset of models repeatedly. Surface those.
- **Per-model badges.** At minimum: cost tier (low/med/high), speed tier (seconds/minutes/hours), provider, license. Optional: quality tier (subjective; needs careful framing).
- **Search by model name.** Power users who know they want "FLUX.1 [pro]" should be able to type that in.
- **Capability mismatch warning.** If the user has selected "image-to-3D" workflow and switches to a model that's text-to-3D only, the UI should flag this before they hit Submit.

### Provider transparency

**The question:** does the user see "fal.ai/fal-ai/flux-pro" or "FLUX [Pro]" with provider as a secondary attribute?

**Recommendation:** the latter. Model identity is what the user cares about. The aggregator/provider is metadata that affects cost and routing but shouldn't dominate the picker.

**Exception:** the settings UI absolutely must show provider — it's where the user manages keys. And the per-job confirmation modal should disclose provider for cost transparency ("This job will run via fal.ai; estimated $0.12 plus aggregator margin").

### API key management

Settings UI grows to support per-provider keys:

```
Vision Settings
├── Direct providers
│   ├── Gemini API key       [••••••••AIza] [Test]
│   ├── Veo API key          [••••••••AIza] [Test]
│   └── Tencent Studio key   [••••••••    ] [Test]
└── Aggregators
    ├── fal.ai key           [••••••••    ] [Test]
    └── Replicate key        [••••••••    ] [Test]
```

Each key is independently optional. Models become available based on which keys are configured. Models with no key configured are visible in the picker but disabled with a "configure key" affordance.

The DPAPI-backed `VisionSecretStore` already handles per-key encryption; needs extension to a per-provider keyspace (currently single-slot).

### Cost estimation across heterogeneous pricing

Pricing models vary materially:

- **Veo:** per output second (deterministic; estimator exact within rounding).
- **Gemini image:** per image, with size tiering (deterministic).
- **fal.ai per-call models:** flat per inference (deterministic).
- **fal.ai per-second models:** $X/GPU-second on Y GPU class (estimator approximate; depends on actual inference time).
- **Replicate:** per CPU/GPU second on declared hardware (estimator approximate).
- **Aggregator margin:** typically 20–40% on top of underlying GPU cost.

UX implications:

- **Estimator must distinguish "exact" from "estimate within ±X%"** and label clearly.
- **Confirmation modal shows the range** ("$0.04–$0.07") for aggregator routes, exact figures for direct.
- **Post-job actual cost** should be surfaced when the aggregator returns it (most do), so users build intuition for which models cost what in practice.

`IPricingModel` already supports per-provider implementation; aggregator-specific pricing models slot in cleanly.

### Capability discovery

**The dynamic-vs-static catalog question:**

- **Static (current):** hardcoded `DefaultVideoProviderRegistry`. Predictable, version-controlled, no network at startup. **But:** every new fal.ai model requires a Rook release.
- **Dynamic:** query fal.ai's `/models` endpoint at startup; build the catalog on the fly. Flexible, no Rook releases needed. **But:** network dependency, schema drift risk, security (do we trust what the aggregator returns?).
- **Hybrid (recommended):** ship a known-good baseline catalog with the Rook installer. Allow opt-in dynamic discovery via a settings toggle or `.rook/models.yaml` override file. Power users get bleeding edge; default users get a vetted catalog.

### Failure / retry UX

Aggregators surface real failure modes the direct providers don't:

- **Queue full.** "fal.ai is busy; retry in 30s" or "try a less popular model."
- **Model unavailable.** Aggregator removed the model or it's temporarily down.
- **Cold-start latency.** First request to a model may take 60+ seconds while the GPU spins up; subsequent requests are fast.
- **Variable inference time.** Same model, same input, different runtime (varies 2-3x with GPU contention).

UX should:

- **Surface aggregator-specific error codes** as typed errors (not raw HTTP).
- **Suggest similar-capability alternatives** on persistent failure ("Hunyuan3D-2 is queued; try TripoSR for similar quality at 1/3 the wait?").
- **Display cold-start indicator** on first call to a model in a session.
- **Show actual vs. estimated time** post-job to calibrate user expectations.

---

## Implementation framework

The proposed architecture, layered:

### Layer 1: Generalized provider interfaces

```csharp
// Base — all generation providers conform
public interface IGenerationProvider
{
    string ProviderName { get; }    // "veo" | "gemini" | "fal" | "replicate" | ...
}

// Per-modality interfaces inherit
public interface IImageProvider : IGenerationProvider
{
    Task<ProviderResult<ImageGenResponse>> SubmitAsync(ImageGenRequest req, ProviderOptions options, CancellationToken ct);
    // image-specific async lifecycle
}

public interface IVideoProvider : IGenerationProvider { /* existing V1c shape */ }

public interface IThreeDProvider : IGenerationProvider
{
    Task<ProviderResult<ThreeDGenResponse>> SubmitAsync(ThreeDGenRequest req, ProviderOptions options, CancellationToken ct);
}
```

### Layer 2: Aggregator clients (shared HTTP infrastructure)

```csharp
public sealed class FalApiClient
{
    // One HTTP client, one auth, one polling implementation
    // Used by FalImageProvider, FalVideoProvider, FalThreeDProvider
}

public sealed class FalImageProvider : IImageProvider { /* dispatches via FalApiClient */ }
public sealed class FalVideoProvider : IVideoProvider { /* dispatches via FalApiClient */ }
public sealed class FalThreeDProvider : IThreeDProvider { /* dispatches via FalApiClient */ }
```

Each modality-specific class is thin — it serializes the modality-specific request to the fal.ai endpoint shape and parses the response. The shared `FalApiClient` handles auth, polling, retries, error mapping.

### Layer 3: Multi-modal registry

```csharp
public interface IGenerationRegistry
{
    IReadOnlyList<ResolvedImageModel> EnumerateImageModels();
    IReadOnlyList<ResolvedVideoModel> EnumerateVideoModels();
    IReadOnlyList<ResolvedThreeDModel> Enumerate3DModels();

    bool TryResolveImage(string modelId, out ResolvedImageModel m);
    bool TryResolveVideo(string modelId, out ResolvedVideoModel m);
    bool TryResolve3D(string modelId, out ResolvedThreeDModel m);

    // Cross-modality search for picker UI
    IReadOnlyList<ResolvedModelBase> FindByCapability(string subCapability);
}
```

`ResolvedImageModel` / `ResolvedVideoModel` / `ResolvedThreeDModel` all share a common base (`ResolvedModelBase`) with `{ModelId, ProviderName, Capability, PricingModel, OptionsCodec}`. Modality-specific subclasses add the typed `Provider` reference.

### Layer 4: Settings extension

`VisionSecretStore` extends to a keyed namespace:

```csharp
public interface ISecretStore
{
    string? GetSecret(string key);              // e.g. "vision.gemini.apiKey"
    void SetSecret(string key, string value);
    void RemoveSecret(string key);
}
```

Each provider declares which key(s) it needs. Registry initialization filters out providers whose keys aren't configured (with a hook to surface "configure key" UX in the picker).

### Layer 5: Catalog source

For Phase 1–4: hardcoded `Default*Registry` classes per provider. Each registry declares its model list at construction.

For Phase 5: opt-in dynamic catalog. A `IModelCatalogSource` interface with `LoadAsync()` that returns `IEnumerable<ModelDescriptor>`. Implementations: `HardcodedCatalogSource` (default), `FalDynamicCatalogSource`, `ReplicateDynamicCatalogSource`, `YamlOverrideCatalogSource` (loads `.rook/models.yaml`).

### Layer 6: UI / picker plumbing

The model picker needs new MCP routes:
- `rhino_vision_models` (already exists for video) → generalize to `rhino_generation_models?modality=image|video|3d&capability=text_to_image`
- `rhino_generation_capabilities` → enumerate all sub-capabilities for picker filtering
- `rhino_settings_provider_keys` → get/set per-provider keys

Settings UI is a new tab or expanded section in the Vision panel.

---

## Phased rollout

### Phase 0: Audit + spike (✅ COMPLETE 2026-04-27)

- ✅ V1c provider abstraction read in detail; seam shapes documented.
- ✅ Live fal.ai calls captured (FLUX schnell sync + queue, Wan v2.7 video, Hunyuan3D Pro v3.1 3D — both validation rejection and successful run).
- ✅ Live Replicate call captured (FLUX schnell official-model endpoint).
- ✅ Live Gemini call captured (gemini-3.1-flash-image-preview — establishes inline-bytes delivery axis).
- ✅ Tencent Hunyuan3D-2 direct API audit (docs + SDK pattern; live call deferred to Phase 4 kickoff).
- ✅ Differences documented: error envelopes (FastAPI `detail` for fal queue; structurally different per provider), polling cadences, auth shapes (four distinct), result delivery (URL vs inline-bytes).
- ✅ **Output:** [`2026-04-27-multi-provider-spike.md`](2026-04-27-multi-provider-spike.md). All six contract decisions bound. Strict gate satisfied. Phase 1 unblocked.

### Phase 1: Generalize the abstraction

- Extract `IGenerationProvider` base from `IVideoProvider`.
- Define `IImageProvider` mirroring V1c shape.
- Refactor existing Gemini/Nano Banana code to implement `IImageProvider` and register via a new `DefaultImageProviderRegistry`.
- Tests proving image generation still works end-to-end.
- **No behavior change for users; this is pure refactor.**

### Phase 2: Add fal.ai as first aggregator

- `FalApiClient`, `FalImageProvider`, `FalVideoProvider` (3D deferred to Phase 4).
- `FalCatalog` — hardcoded baseline of ~10–20 well-known models (FLUX schnell, FLUX pro, SDXL Lightning, Kling I2V, Mochi T2V, etc.).
- `FalPerCallPricingModel` and `FalPerSecondPricingModel` for the two main billing shapes.
- Settings UI: fal.ai key entry.
- Picker UI: provider badges, capability filter.
- Live smoke test against real fal.ai API.
- **First user-visible win: ~15 new image and video models available.**

### Phase 3: Add Replicate as second aggregator

- `ReplicateApiClient`, providers analogous to Phase 2.
- Validates that the aggregator pattern is right (or surfaces what needs to change).
- Models: SDXL, FLUX, Stable Video Diffusion, etc.
- **If Phase 3 requires architectural changes that weren't anticipated in Phase 2, that's the signal to revise the framework before Phase 4.**

### Phase 4: 2D→3D capability via Hunyuan

- Define `IThreeDProvider` (now informed by what Phases 2–3 taught us).
- Add `FalThreeDProvider` and `ReplicateThreeDProvider` for Hunyuan3D-2.
- Add direct `TencentStudioThreeDProvider` for users who want lower latency / no aggregator margin.
- Define artifact roles for 3D output: `mesh`, `texture`, `mesh_preview_render`, etc.
- Hand off to a separate "2D→3D pipeline" doc when one exists; this doc is just the framework that enables 3D providers, not the pipeline itself.

### Phase 5: Dynamic catalog discovery (defer until usage tells us)

- Implement `*DynamicCatalogSource` for fal.ai and Replicate.
- Settings toggle to enable/disable dynamic discovery per provider.
- Catalog refresh cadence + caching.
- User-customizable model list via `.rook/models.yaml` override.

---

## Open questions / audits needed

1. ~~**fal.ai response shape for video gen?**~~ → **Resolved (Phase 0 P2 spike).** fal queue submit returns `{request_id, status_url, response_url, cancel_url, status: "IN_QUEUE", queue_position, metrics: {}}`. Polled status returns same envelope with `metrics.inference_time` added at terminal `COMPLETED`. Result body lives at `response_url` (separate fetch): `{video: {url, content_type, duration, fps, num_frames, ...}, seed, actual_prompt}`. Billing in `x-fal-billable-units` response header. See spike doc Decision 1, 3, 5.
2. ~~**Replicate response shape for prediction-style API?**~~ → **Resolved (Phase 0 P3 spike).** Polling-based; submit returns `{id, status: "starting", urls.{get, cancel, stream, web}}`; terminal poll body includes `output: [<url>]`. Lifecycle states `starting → processing → succeeded`. `metrics.predict_time` for cost. Streaming endpoint exists (`urls.stream`) but not exercised; webhook delivery model not exercised.
3. ~~**Tencent Hunyuan3D-2 direct API: is it available, pricing, auth?**~~ → **Resolved (Phase 0 P5 audit).** Yes — Tencent Cloud Hunyuan service v20230901 with seven endpoint pairs covering Pro/Rapid/Part/SmartTopology/TextureEdit/UV/FormatConvert. Auth via paired SecretId+SecretKey + TC3-HMAC-SHA256 signing (handled by `tencentcloud-sdk-python`). Pricing public per-product on Tencent docs; live call deferred to Phase 4 kickoff (CAM sub-user setup ~30–60 min).
4. **Aggregator margin numbers.** Still open — Phase 2 cost estimator UX needs concrete margin observations vs raw provider pricing.
5. **Cold-start latency:** Still open — Phase 0 observed multi-minute cold-starts on fal Wan + Hunyuan3D Pro but didn't measure systematically. Phase 2 should profile across providers.
6. **Capability schema: discriminated union or polymorphic record?** → **Constrained by spike evidence; not bound.** Per-route capability flags are required (image+video+3D structurally differ); flat per-provider booleans are insufficient. The exact C# shape (discriminated union vs polymorphic base + modality-specific subclasses) remains a Phase 1 design call — and importantly, 3D-specific subclass content must NOT land in Phase 1 per the design carve-out. Image/video capability schema is bound to "per-route flags;" 3D shape is opaque-route-descriptors-only until Phase 4. See spike Decision 2.
7. ~~**Per-modality capability mismatch:** where does validation live?~~ → **Resolved.** Provider adapters validate at registration time (capability flags declare what's supported) and at submit time (request shape vs declared capability). See spike Decision 4.
8. **Catalog identity stability:** Still open. Phase 2 will need explicit handling for "model renamed/removed" — Phase 0 didn't observe a rename mid-spike but the risk is real for long-lived NLE cache references.
9. **Trust posture:** Still open. Phase 2 UX question — per-prompt warning, per-session toggle, or settings opt-in for "send to third-party aggregator." Spike captured the privacy axis (URL vs inline-bytes delivery) which is relevant input.
10. **Local models (e.g., via Ollama):** Still deferred — out of Phase 0 scope. Conceptually a provider; no compelling case observed in spike.
11. **Cross-aggregator price comparison:** Still open. With pricing now shape-mapped (Decision 3), Phase 2 picker UX can decide whether to surface both entries side-by-side or de-dupe to "cheapest provider for this model."
12. **MCP tool surface (`rhino_render_view` rename?):** Still deferred — Phase 2 product/UX decision. Spike doesn't change the calculus.

---

## Roadblocks

- **(a) Gemini and Veo aren't on aggregators.** **Confirmed (Phase 0).** Aggregator-only is not a viable product posture; we always need direct integrations for Google models. Hybrid posture preserved in framework.
- **(b) Aggregator margin invalidates per-second precision.** **Confirmed in shape (Phase 0); specific numbers still TBD.** Five distinct pricing patterns mapped (per-MP, per-output-second × tier, per-call flat + add-ons, per-compute-second, per-token-by-modality). `IPricingModel` returns `CostEstimate { Min, Max, IsExact, Provenance }` per Phase 0 binding for Decision 3.
- **(c) Catalog drift.** Still open. Phase 0 didn't observe a rename mid-spike but the risk for long-lived references (NLE cache_index) is real. Phase 2 explicit handling needed.
- **(d) Settings sprawl.** Still open (Phase 2 UX scope). Phase 0's secret-key namespace work (Decision 6) confirmed at least four credential shapes — single-token providers + paired-credential signature-scheme providers (Tencent). Phase 2's settings UI must accommodate both.
- **(e) Picker scaling.** Still open (Phase 2 UX scope). Phase 0 didn't change the calculus.
- **(f) Multi-provider key validation.** Still open (Phase 1 implementation). Phase 0's `verify_credentials.py` probe surfaced a useful subtlety: some providers' "list" endpoints are public (fal `/models` returns 308/200 without validating the key — `auth_only_unproven` outcome). Phase 1's `TestKeyAsync` should distinguish "key present and validates" from "key present but endpoint can't prove it" — first paid call is sometimes the only real check.
- **(g) Prompt/image leakage to aggregators.** Still open (Phase 2 UX/trust). Phase 0 surfaced an additional axis: **delivery mechanism** (URL on provider CDN vs inline-bytes in API response). Different trust postures.
- **(h) Cost estimation across heterogeneous pricing surfaces.** **Confirmed (Phase 0); five distinct shapes documented.** Phase 1 binding: `IPricingModel` is per-provider, possibly per-model. Cost estimator must read both response headers AND response body depending on provider. See spike Decision 3.
- **(i) MCP tool naming.** Still deferred (Phase 2 product question). Phase 0 doesn't change the calculus.
- **(j) Provider-specific OptionsCodec proliferation.** **Confirmed (Phase 0); at least five distinct codecs documented.** Replicate has internal dual-endpoint variation (community vs official); fal has per-model input field name variation; Tencent introduces SDK-mediated providers as a structurally distinct category. Phase 1 binding: per-provider, per-route options codec — no shared shape. See spike Decision 4.

---

## Edges to explore

- **"Best price" routing.** If FLUX is on both fal.ai and Replicate, the picker could show both with a price comparison and let users pick. Or auto-route to cheaper. UX consequences unclear.
- **Fallback routing.** "If Veo direct is unavailable, fall back to Veo via fal.ai (when fal.ai eventually hosts it)." Adds resilience but blurs the cost-estimation contract.
- **Local models as providers.** Ollama for image embedding, Stable Diffusion locally via ComfyUI integration. Same `IImageProvider` interface, different `LocalProvider` impl. Major UX implication: "local" is a special trust tier (no third-party leakage).
- **Per-job provider override.** Even when a model has a default provider (e.g., "FLUX schnell on fal.ai"), allow a per-job override ("just this once, run on Replicate"). Useful for debugging and benchmarking.
- **Community catalog.** Users publish their `.rook/models.yaml` to a shared registry; others import. Forward-compat with collaborative model discovery.
- **GH NLE per-node provider routing.** A render sink could specify "render this clip on the cheapest available provider for the requested capability." Powerful for cost-conscious workflows.
- **Capability composition.** "Generate an image with FLUX, then upscale with Real-ESRGAN, then convert to 3D with Hunyuan" — a pipeline expressed as chained provider calls, materialized as artifacts at each stage with `parent_ids` chaining provenance. The framework should make this composable without GH (but GH is the natural UI for it).
- **Provider health monitoring.** Background pings to each configured provider, surface "fal.ai is degraded" indicators in the picker. Probably out of v1.

---

## Paths to success

1. **Phase 0 spike** (1 session, low risk): real API calls against fal.ai, Replicate, Tencent. Document concrete payloads. Output: a payload-spike doc.
2. **Phase 1 refactor** (1–2 PRs, no behavior change): generalize `IGenerationProvider`, extract `IImageProvider`, refactor Gemini code. Tests prove image generation still works.
3. **Phase 2 fal.ai** (1 medium PR + smoke): aggregator pattern lands with first user-visible model expansion (~15 new models). Picker UI gets capability filter + provider badges.
4. **Phase 3 Replicate** (1 small-medium PR): validates aggregator pattern. If this requires significant rework, that's the signal to revisit the framework.
5. **Phase 4 3D** (own scope-pass cycle): Hunyuan3D-2 via aggregator + direct Tencent. Hand off to the 2D→3D pipeline doc.
6. **Phase 5 dynamic catalog** (defer until usage tells us): only ship if the static catalog becomes a real friction point.

Each phase ships independently. If we stop after Phase 2, users have ~15 new models; if we stop after Phase 4, the 2D→3D foundation is in place. Phase 5 is opportunistic.

---

## What this doc is NOT trying to decide yet

- Which aggregator to ship first (fal.ai vs. Replicate). Phase 2 scope decision.
- The 2D→3D pipeline architecture. Separate doc when Phase 4 is scoped.
- Picker UI implementation specifics. Phase 2 spike + design.
- Dynamic catalog persistence format. Phase 5.
- Local-model support. Out of scope unless Phase 0 spike surfaces a compelling case.
- Multi-tenant or shared-key scenarios. Single-user is the v1 model.
- Provider health monitoring / status dashboard. Out of scope.
- Renaming `rhino_render_view` to `rhino_generate_image`. Backward compatibility decision deferred to Phase 2.
- Whether the existing `VisionHandler` becomes a `GenerationHandler` or stays vision-scoped. Refactor decision in Phase 1.

---

## Iteration log

- **v0.1 (2026-04-26):** Initial draft. Captures the strategic framing (aggregator-aware, multi-modal, hybrid direct + aggregator), the V1c-as-template observation, the capability lattice, product/UX dimensions, implementation framework layered design, and a five-phase rollout. Open for review.
- **v0.2 (2026-04-27):** Phase 0 spike folded in. All six contract decisions resolved with empirical evidence; gate satisfied; Phase 1 unblocked. Open Questions 1–3 + 6–7 resolved (with citations to spike doc); 4, 5, 8, 9, 11 still open (Phase 2 scope); 10 + 12 deferred. Roadblocks (a)/(b)/(h)/(j) confirmed in shape with Phase 1 bindings; (c)/(d)/(e)/(f)/(g)/(i) still open. New "Phase 0 Evidence Summary" section near top with one-line Phase 1 binding per decision. Phase 0 bullet in Phased Rollout flipped to ✅ complete with evidence pointers. Tencent direct identified as Phase 4 priority backend (substantially more capability than fal-hosted Hunyuan). See [spike doc](2026-04-27-multi-provider-spike.md) for full evidence rows + side-by-side cross-provider comparison tables.
