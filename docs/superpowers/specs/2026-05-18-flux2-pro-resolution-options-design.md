# Flux 2 Pro Resolution Options Design

Date: 2026-05-18

## Context

Rook currently advertises only `1MP` for Replicate Flux 2 Pro image generation. Replicate's Flux 2 Pro API schema, reviewed on 2026-05-18, documents the `resolution` input as megapixel choices with default `1 MP`, support up to `4 MP`, and a recommendation to stay at `2 MP` or below. The same schema says `width` and `height` are only used for `aspect_ratio=custom`.

Source: https://replicate.com/black-forest-labs/flux-2-pro/versions/f558a59a8bf126d892ab219846966674f6acc616940c17841aeb242e245952ff/api

## Scope

This slice corrects the Flux 2 Pro resolution dropdown and request validation for the existing prompt-only workflow.

In scope:

- Advertise Flux 2 Pro prompt-only resolutions as provider-shaped values: `1 MP`, `2 MP`, and `4 MP`.
- Accept legacy `1MP` at the backend boundary as a compatibility alias for `1 MP`.
- Always send provider JSON using the provider-shaped spaced value.
- Preserve source-image Flux 2 Pro behavior: when an input image is present, send `aspect_ratio: "match_input_image"` and `resolution: "match_input_image"`.
- Add regression tests for catalog metadata, prompt-only `2 MP` or `4 MP`, legacy `1MP` normalization, and source-image `match_input_image`.

Out of scope:

- `aspect_ratio: "custom"`.
- `width` or `height`.
- New UI controls for custom dimensions.
- A broader image-model settings redesign.

## Design

Flux 2 Pro capability metadata will list `1 MP`, `2 MP`, and `4 MP`. The Vision UI already populates the resolution dropdown from `supported_resolutions`, so catalog correction should be sufficient for the dropdown.

Backend validation should normalize only known legacy Flux 2 Pro resolution spellings before capability validation and request serialization. `1MP` is accepted as an alias for `1 MP`; new catalog values should use the spaced spelling. Unsupported compact values such as `2MP` and `4MP` are not required in this slice because they were never emitted by Rook.

Provider request construction should use normalized provider values. Prompt-only Flux 2 Pro should pass through `1 MP`, `2 MP`, or `4 MP`. If prompt-only resolution is empty or `match_input_image`, Rook should default to `1 MP`.

Source-image Flux 2 Pro remains independent of the dropdown value. If `input_images` are present, Rook continues to send:

```json
{
  "aspect_ratio": "match_input_image",
  "resolution": "match_input_image"
}
```

That preserves Replicate's source-image semantics and avoids turning the prompt-only dropdown into a misleading source-image control.

## Testing

Add focused managed tests:

- Provider registration advertises Flux 2 Pro resolutions as `1 MP`, `2 MP`, `4 MP`.
- Prompt-only Flux 2 Pro request with `2 MP` serializes `resolution: "2 MP"`.
- Prompt-only Flux 2 Pro request with `4 MP` validates and serializes `resolution: "4 MP"`.
- Legacy prompt-only `1MP` validates and serializes as `1 MP`.
- Source-image Flux 2 Pro still serializes `resolution: "match_input_image"` even if the request resolution came from the dropdown.

Run the Replicate image provider and registration test slice after implementation. A local deploy is required before manual RookVision UI verification.

## Acceptance Criteria

- The Generate tab shows `1 MP`, `2 MP`, and `4 MP` for Flux 2 Pro.
- Prompt-only Flux 2 Pro can submit `2 MP` and `4 MP`.
- Stale clients that submit `1MP` continue to work and send `1 MP` to Replicate.
- Source-image Flux 2 Pro roundtrips still use `match_input_image`.
- No custom width/height behavior is added.
