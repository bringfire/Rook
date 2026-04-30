# PR-9 Provider Settings And Picker Design

Date: 2026-04-30

## Goal

PR-9 adds the managed/UI credential and picker UX needed after fal image and video support:

- Render provider credential requirements in Settings as provider cards.
- Add canonical provider-aware set, test, and clear secret bridge ops.
- Add a canonical provider-aware image model catalog bridge op.
- Surface fal availability without hiding fal models when the fal key is missing.
- Keep provider identity secondary to model identity in the picker.
- Preserve Gemini key migration, preview, persistence, and legacy UI compatibility.

This design is managed/UI-only. It does not add native credential routes, native trampoline exposure for credential ops, Replicate, Tencent, dynamic catalog discovery, 3D models, or new fal generation models.

## Non-Goals

- No paid or generation-based fal Settings validation.
- No visible provider/filter picker redesign.
- No persisted credential validation cache.
- No native public HTTP route shape changes.
- No changes under `src/RookNative/**`.
- No generalized legacy `set_api_key` or `test_api_key` semantics.
- No Replicate or Tencent controls, except where existing metadata types remain future-compatible.

## Architecture

PR-9 keeps all credential UX inside the managed Vision panel bridge.

`VisionWebSurface.OpRoutes` adds bridge-only entries for:

- `set_provider_secret`
- `test_provider_secret`
- `clear_provider_secret`
- `list_image_models`

These route to `VisionHandler`. They are not added to native route registration or the native `vision_dispatch` public allowlist. If an existing native allowlist test can cover this boundary, it should pin absence there; otherwise the implementation review must treat it as an explicit boundary assertion.

`set_api_key` and `test_api_key` remain Gemini-only compatibility shims. They internally map to:

```json
{
  "provider_name": "gemini",
  "secret_key": "gemini.api_key"
}
```

They must not accept optional provider semantics, and tests must prove they cannot set or test fal secrets.

`VisionHandler` becomes the provider credential composition point for the Vision panel. It must consume credential metadata through an explicit access path because today's `DefaultImageProviderRegistry` and `DefaultVideoProviderRegistry` flatten models and discard registration-level `SecretRequirements`.

PR-9 should add one of these managed-only metadata seams:

- `EnumerateProviderSecretRequirements()` on the image and video registries; or
- a small provider credential metadata catalog built from the same registration arrays used to construct the registries.

The implementation plan should pick the smaller local fit after inspecting constructor ownership. Either way, provider summaries merge by `provider_name` across image and video registrations. Secret requirements de-duplicate by secret `key`; conflicting display metadata for the same key is a registration invariant failure and must be rejected or pinned by tests.

`list_image_models` becomes the canonical image catalog transport. It returns provider-aware descriptors with local persisted credential presence. `get_settings_overview.available_models` remains only as a Gemini-compatible legacy alias for transitional image dropdown fallback.

## Provider Credential Data Flow

### Settings Load

`get_settings_overview` continues to return:

- Artifact counts.
- Legacy Gemini fields: `has_api_key`, `api_key_preview`, `default_model`.
- `available_models` as a legacy Gemini-shaped compatibility alias.
- Provider credential summaries for the Settings Credentials section.

Provider credential summaries are generated from provider metadata and `IGenerationSecretStore.HasSecret` / `GetPreview`. This is local metadata only. It must not perform provider network validation.

### Credential Cards

The Settings view replaces the single hard-coded Google AI API card with a provider-driven Credentials section rendered as per-provider cards.

Expected cards in PR-9:

- Gemini first, preserving the current visual treatment and Google AI Studio help copy.
- fal.ai second, rendered by the same component and using fal-specific help copy.

The UI should feel like the existing Settings area, not like a generic credential table. Provider identity is primary in Settings because Settings is where the user manages provider keys.

### Set And Clear

`set_provider_secret(provider_name, secret_key, value)`:

- Requires `provider_name`, `secret_key`, and a non-empty value.
- Validates that `provider_name` is known.
- Validates that `secret_key` is declared by that provider's merged `SecretRequirements`.
- Rejects cross-provider writes, unknown keys, and arbitrary DPAPI slot writes.
- Saves through `IGenerationSecretStore.SetSecret`.
- Returns presence and preview metadata, never the secret value.

`clear_provider_secret(provider_name, secret_key)`:

- Performs the same provider/key validation.
- Removes through `IGenerationSecretStore.RemoveSecret`.
- For Gemini, this relies on the existing `DpapiGenerationSecretStore.RemoveSecret` behavior that also clears legacy Gemini slot state when applicable.

Saving, clearing, editing, or panel reload clears the JS session validation overlay for that secret.

### Test

`test_provider_secret(provider_name, secret_key, candidate_value?)`:

- Requires `provider_name` and `secret_key`.
- Validates that the key belongs to the provider's declared `SecretRequirements`.
- Reads the stored secret when `candidate_value` is omitted.
- Uses `candidate_value` only for the test when provided.
- Never saves `candidate_value`.
- Never returns `candidate_value`.
- Never persists validation state.

Gemini provider-secret testing reuses the existing prompt-enhancer probe. `test_api_key` is a shim over that same Gemini-only implementation.

fal provider-secret testing uses a non-generation, non-spend platform probe where possible. It must not call `fal.run` or `queue.fal.run` model work from Settings.

fal result mapping:

- Blank local candidate: local validation failure.
- Clear auth failure: `Invalid`.
- Clear authenticated API proof: `Valid`.
- Public endpoint, redirect, rate limit, provider outage, scope ambiguity, or any result that does not prove validity: `Inconclusive`.

Submit/generation remains the authoritative validation path.

## Validation State Model

Persisted settings store only encrypted secret value plus preview/presence.

Validation state is panel-session only:

- `MissingRequiredSecret`: derived from persisted secret presence.
- `AvailableButUnverified`: derived from persisted presence with no session validation.
- `InvalidCredential`: derived only from session validation, such as failed `test_provider_secret` or a submit-time auth failure observed in the open panel.
- `Available`: session-only result from a successful non-generation test.
- `AvailableWithInconclusiveValidation`: session-only result when validation cannot prove key validity.

`InvalidCredential` is warning-only in PR-9. It does not block submit by itself because non-generation validation can be scope-limited, stale, or ambiguous. The user can proceed; submit remains authoritative.

The only deterministic blockers are:

- `MissingRequiredSecret`.
- Known capability mismatch for the current request shape.

No validation state is written to `RookSettingsStore` or `generation_secrets`.

## Image Catalog

`list_image_models` is an off-UI bridge op. It enumerates local registry metadata and reads persisted credential presence only. It does not perform provider validation or network work.

Response shape:

```json
{
  "models": [
    {
      "model_id": "fal-ai/flux/schnell",
      "provider_name": "fal",
      "pricing_kind": "per_generation",
      "pricing_source": "fal-flux-schnell-rate-card-v1",
      "credential_availability": "missing_required_secret",
      "credential_message": "Missing required credential: fal API key.",
      "capability": {
        "id": "fal-ai/flux/schnell",
        "name": "FLUX.1 Schnell",
        "status": "available",
        "resolutions": ["1K"],
        "aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16"],
        "max_reference_images": 0,
        "supports_image_to_image": false,
        "supports_text_to_image": true
      }
    }
  ]
}
```

`pricing_source` is required. `pricing_kind` is optional in PR-9 unless the implementation adds an image pricing-kind classifier parallel to video's `PricingKindFor`. The descriptor must carry enough provider, pricing, capability, and credential-presence metadata for the picker without inventing pricing semantics the current image descriptor layer does not expose.

The UI joins `list_image_models` descriptors with its JS session validation overlay before rendering warnings or disabled states. The backend does not accept or persist the overlay for image catalog enumeration.

`get_settings_overview.available_models` remains a Gemini-shaped shim for existing dropdown fallback. New UI code prefers `list_image_models`. If `list_image_models` is unavailable or fails, the legacy image dropdown fallback can still read `available_models`.

## Picker Behavior

PR-9 does not add visible filter controls.

It adds provider-aware descriptors and internal compatibility behavior:

- Missing required credentials keep models visible but not submittable, with configure-key messaging.
- `InvalidCredential` shows a strong warning but does not block submit.
- `Available`, `AvailableButUnverified`, and `AvailableWithInconclusiveValidation` do not block submit.
- Capability mismatch disables or prevents submit because the request shape is known invalid.
- Image picker disables image-to-image-incompatible models when references or image inputs require image-to-image support.
- Video picker preserves current mode/reference compatibility behavior while treating capability rules as provider-neutral.

Provider identity stays secondary in model pickers:

- Model display name remains primary.
- Provider appears as a badge or adjacent hint.
- Pricing/source metadata remains lightweight and factual.

## Error Handling

Provider ops return structured failures for:

- Unknown provider.
- Unknown secret key.
- Secret key not declared by provider.
- Empty secret value.
- Missing stored secret when testing without a candidate.
- Provider test request or transport failure when no validation result can be produced.

Ambiguous fal provider proof should map to a success-style validation result with `validation_state: "inconclusive"`, not a generic failure. Request failures or transport failures are structured failures only when no validation result can be produced.

Credential operations must never include plaintext secret values in logs, exceptions returned to JS, previews beyond the existing first4-last4 pattern, or response bodies.

Submit-time auth failure may update the open panel's JS session overlay to `InvalidCredential`, but must not write validation state to settings.

## Testing Strategy

Backend and handler tests:

- Provider summaries merge by `provider_name` across image and video registrations.
- Provider credential metadata is exposed through an explicit registry enumeration method or a shared metadata catalog; implementation must not duplicate ad hoc registration lists in UI handlers.
- Secret requirements de-duplicate by key.
- Conflicting secret metadata for the same provider/key is rejected or pinned as an invariant failure.
- `set_provider_secret` rejects unknown provider, unknown secret key, cross-provider key, blank value, and arbitrary DPAPI slot writes.
- `clear_provider_secret` rejects unknown provider, unknown secret key, and cross-provider key.
- `clear_provider_secret` for Gemini clears through `DpapiGenerationSecretStore.RemoveSecret`, including legacy Gemini slot behavior it already owns.
- `test_provider_secret` with no `candidate_value` reads the stored secret for that provider/key.
- `test_provider_secret` with a candidate never persists or returns the candidate.
- `test_provider_secret` never persists validation state.
- fal testing maps auth failure to `Invalid`, clear authenticated proof to `Valid`, and ambiguous non-generation outcomes to `Inconclusive`.
- `set_api_key` remains Gemini-only and cannot set fal.
- `test_api_key` remains Gemini-only and cannot test fal.
- `get_settings_overview` preserves legacy Gemini fields and `available_models`.
- `list_image_models` includes Gemini and fal provider metadata without depending on `get_settings_overview`.
- `list_image_models` is off-UI/local metadata only.

UI and bridge tests:

- `VisionWebSurface.OpRoutes` includes the new provider-aware bridge ops with correct dispatcher routes.
- New credential ops are not exposed as native credential routes; cover through source/route registration tests where available, otherwise treat as a review boundary assertion.
- Settings renders provider cards from provider summaries.
- Gemini and fal cards are present, with Gemini retaining familiar card behavior and preview display.
- Gemini settings overview continues to work with legacy migrated keys.
- Saving, clearing, editing, or panel reload clears the JS session validation overlay.
- Missing fal key leaves fal models visible with configure-key annotation.
- `InvalidCredential` shows a strong warning but does not block submit by itself.
- Missing required secret blocks or disables only because persisted presence is missing.
- Known capability mismatch blocks or disables invalid request shapes.
- Legacy image dropdown fallback still works if `list_image_models` fails or is absent, using `available_models`.

No live fal validation is required for normal tests. Any network/spend smoke remains opt-in and outside PR-9's default verification.

## Review Invariants

- No native credential route exposure.
- Legacy `set_api_key` and `test_api_key` remain Gemini-only.
- `InvalidCredential` is warning-only.
- `MissingRequiredSecret` and capability mismatch are the only deterministic blockers.
- `list_image_models` is canonical; `available_models` is a shim.
- Validation state is not persisted.
