# RookVision Provider Media Policy Design

Date: 2026-05-18

## Goal

Remove arbitrary Rook-side image upload limits from provider paths where those
limits do not represent the provider API, starting with Replicate Flux 2 Pro.

The first implementation milestone is Replicate Flux 2 Pro only. It should
replace Rook's current 1 MiB data URI source-image cap with provider-appropriate
media transport and explicit model/media policy. The policy scaffolding should
be small and typed, with immediate consumers in image work-item validation,
media resolution limits, and provider submit validation.

This design intentionally separates:

- model input policy: what a model accepts and how it constrains inputs;
- transport policy: how Rook is allowed to deliver media to the provider;
- Rook safety policy: local memory, bridge, and UX guardrails that are not
  provider limits.

## Current Problem

Replicate Flux 2 Pro is artificially constrained in Rook:

- `ReplicateImageSourcePayload.MaxRawBytes` hard-caps raw source bytes at
  `1024 * 1024`.
- `ReplicateImageProvider.BuildFlux2ProRequestJson` sends `input_images` as
  data URIs.
- Rook's current Replicate Flux 2 Pro provider path requires exactly one input
  image, rejects references, and omits GIF support.
- Rook's capability metadata under-models Flux 2 Pro's API surface.

Raising or removing the byte cap while keeping data URI transport is not the
right fix. Replicate's current documentation recommends hosted URLs for larger
files and treats data URIs as a small-file convenience.

`VisionHandler.MaxInputImageBytes` and `VisionHandler.MaxAggregateImageBytes`
are also global image generation work-item caps. They may be valid for Gemini
inline payloads, but they are not reliable provider limits for URL-upload
providers such as fal and Replicate.

## Source Evidence

Reviewed on 2026-05-18:

- Replicate input files:
  https://replicate.com/docs/topics/predictions/input-files/
- Replicate HTTP API:
  https://replicate.com/docs/reference/http/
- Replicate JavaScript client file upload docs:
  https://github.com/replicate/replicate-javascript/blob/main/README.md
- Replicate Flux 2 Pro overview:
  https://replicate.com/black-forest-labs/flux-2-pro
- Replicate Flux 2 Pro schema:
  https://replicate.com/black-forest-labs/flux-2-pro/versions/f558a59a8bf126d892ab219846966674f6acc616940c17841aeb242e245952ff/api
- fal GPT Image 2 Edit:
  https://fal.ai/models/openai/gpt-image-2/edit
- fal Seedance I2V:
  https://fal.ai/models/bytedance/seedance-2.0/image-to-video
- fal Kling v3 Standard:
  https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-v3-standard

Provider docs drift. Any policy value taken from provider docs must carry a
retrieval date in code comments or tests. Unknown provider limits must be
reported as "Rook guard, provider limit unverified", not as provider max.

## Non-Goals

- No broad dynamic provider schema discovery.
- No generic cross-modality policy framework.
- No video policy unification in this first milestone.
- No native route, MCP, or public HTTP expansion.
- No edits under `src/RookNative/**`.
- No new external dependencies.
- No live provider calls in normal tests.
- No automatic resize or compression in the first milestone.
- No public temporary hosting service owned by Rook.
- No durable image job ledger schema change.
- No provider URL, source file URL, upload URL, request JSON, data URI, or token
  leakage in bridge responses, artifact metadata, durable ledgers, or errors.

## Policy Model

Add a small image-only policy abstraction. It should not try to solve every
future media case. The first version should be shaped around current image
generation and editing flows.

The policy should represent three distinct layers.

### Model Input Policy

Model input policy describes what the model accepts:

- supported roles: input image, reference image, mask when supported;
- supported MIME types;
- maximum image count;
- dimension and pixel limits;
- whether prompt-only generation is supported;
- whether source-image editing is supported;
- provider documentation provenance.

For Flux 2 Pro, model policy should state:

- provider: `replicate`;
- model id: `black-forest-labs/flux-2-pro`;
- input field: `input_images`;
- supported MIME types: JPEG, PNG, GIF, WebP;
- maximum input images: 8;
- total input size policy: 9 megapixels across input images;
- output resolution policy: up to 4 MP, with 2 MP or below recommended;
- width/height custom-output bounds: 256 to 2048, multiples of 16;
- supports text-to-image: true;
- supports image-to-image/editing: true.

The text-to-image flag is an intentional capability correction. Because it can
change routing and UI behavior, tests must prove prompt-only async image jobs
continue to route cleanly for Flux 2 Pro, or the corrected capability must be
gated behind UI behavior that already supports prompt-only async models.

### Transport Policy

Transport policy describes how Rook sends media:

- inline data URI;
- provider-hosted file upload and provider-returned HTTPS URL;
- fal CDN/storage upload;
- caller-provided HTTPS URL;
- unsupported.

For Replicate Flux 2 Pro, Rook should upload local source bytes to
Replicate-hosted file storage or another Replicate-accepted HTTPS URL, then pass
HTTPS URLs in `input_images`. The design must not describe the C# layer as
using `replicate.files.create` unless the implementation actually calls a JS
client. The protocol requirement is provider-accepted HTTPS URL transport.

If the current C# HTTP layer cannot access a documented public raw HTTP file
upload endpoint equivalent to Replicate client file uploads, that is a design
risk and implementation blocker for large local files. Do not fall back to
silently raising the data URI cap. The acceptable fallback is to keep Flux 2 Pro
source-image submission blocked with a precise error that says the provider file
upload transport is unavailable.

For fal GPT Image 2 Edit, fal CDN/storage upload remains the correct direction:
source bytes are uploaded first and `image_urls` receives URLs.

For Seedance, fal documents JPEG/PNG/WebP source images up to 30 MB. Rook's
current 30 MB source-frame policy is provider-aligned.

For Kling v3 Standard, fal documents URL fields, but the reviewed reference did
not expose the same explicit 30 MB image-source line. Rook may keep the current
30 MB policy as a Rook guard, but it must not be labeled as a proven provider
maximum until a current source is found.

### Rook Safety Policy

Rook safety policy describes local protections that are not provider limits:

- maximum bytes read into memory for local images;
- aggregate bytes read for a single request;
- bridge response/request guardrails;
- maximum dimensions Rook is willing to decode;
- failure messages for unknown or unverified provider limits.

Gemini can keep inline-payload byte limits because it sends inline content.
URL-upload providers should not inherit Gemini's aggregate inline cap by
default. They should have their own transport safety cap, with provenance that
says it is a Rook guard unless a provider source proves otherwise.

## Replicate Flux 2 Pro Flow

The first implementation milestone should update only Replicate Flux 2 Pro.

1. Resolve request model and load its image media policy.
2. Validate prompt/source/reference shape against model input policy.
3. Resolve local media bytes using resolver limits derived from transport and
   Rook safety policy, not the old global Gemini-oriented caps.
4. Decode image headers or dimensions before submit.
5. Validate MIME from bytes and declared MIME consistency.
6. Validate total megapixels across `input_images` before provider submit.
7. Upload each local source/reference image to provider-accepted HTTPS file
   storage.
8. Build the Replicate prediction input with `input_images` as HTTPS URLs.
9. Submit, poll, fetch, and materialize through the existing image job flow.

Dimension validation is required. Byte size is not sufficient for Flux 2 Pro:
a highly compressed 12 MP JPEG can be below a byte cap while violating the
model's megapixel policy.

The provider should not persist provider-upload URLs. They are request-time
transport details and should be treated like existing provider URLs: usable in
memory only, sanitized from bridge responses and durable records.

## Capability And UI Impact

Flux 2 Pro should be modeled as both text-to-image and image-to-image/editing.
That is a provider capability correction, not just a metadata tweak.

Tests must cover the routing consequences:

- prompt-only `image_generate_start` works for async Flux 2 Pro if the UI and
  backend already support it for async image models;
- source-image Flux 2 Pro works with one or more input images within policy;
- references are allowed up to the model's policy count once the UI and bridge
  can express them safely;
- sync `generate` still fails closed for async image job providers;
- Studio and Generate do not enable controls that the backend will reject.

If reference-image UI support cannot be done safely in the first implementation
milestone, the backend policy may support up to 8 while UI exposure remains
narrow. In that case, tests must make the distinction explicit: provider model
policy is broader than the current UI affordance.

## Error Handling

Errors should distinguish the policy layer:

- model policy failures: unsupported MIME, too many images, total megapixels
  exceeded, output dimensions invalid;
- transport policy failures: provider file upload unavailable, upload rejected,
  provider-accepted HTTPS URL missing;
- Rook safety failures: local byte guard exceeded, dimension decode guard
  exceeded, aggregate local read guard exceeded.

Messages should be user-actionable without leaking internals. Example:

- "Flux 2 Pro accepts up to 8 input images; got 9."
- "Flux 2 Pro input images must total 9 megapixels or less."
- "Replicate file upload transport is unavailable, so large local Flux 2 Pro
  source images cannot be submitted."
- "Image exceeded Rook's local safety limit before provider upload."

Provider upload URLs, data URIs, source paths, request bodies, and token-bearing
details must not appear in persisted errors.

## Tests

Provider and transport tests:

- Flux 2 Pro no longer builds `input_images` as data URIs for local source
  images.
- Flux 2 Pro uploads source bytes through the Replicate media transport seam.
- Submit body contains HTTPS URLs returned by the transport seam.
- Provider upload URLs are not persisted in job ledgers, bridge responses,
  artifact metadata, provider handles, or sanitized errors.
- If transport is unavailable, the provider fails closed before prediction
  creation.

Policy tests:

- policy distinguishes model, transport, and Rook safety limits;
- Flux 2 Pro accepts PNG, JPEG, GIF, and WebP by byte detection;
- unsupported image MIME fails before provider submit;
- declared MIME mismatch fails before provider submit;
- more than 8 input images fails before provider submit;
- total input megapixels over 9 MP fails before provider submit;
- compressed high-pixel-count images fail based on dimensions, not bytes;
- provider documentation provenance and retrieval date are present for
  provider-derived policy values;
- unknown or unverified limits are labeled as Rook guards, not provider maxes.

Routing and UI-facing tests:

- Flux 2 Pro descriptor correction is visible in `list_image_models`;
- prompt-only async routing remains correct if `supports_text_to_image` is
  enabled;
- source-image async routing remains correct;
- sync `generate` rejects async Flux 2 Pro;
- existing Gemini inline behavior and caps remain unchanged;
- fal GPT Image 2 Edit still uses fal upload and URL input behavior;
- Seedance still enforces its documented 30 MB policy;
- Kling 30 MB policy is labeled as a Rook guard unless a provider citation is
  added.

Regression scans:

- no new native route exposure;
- no MCP exposure;
- no provider URLs or data URIs in durable image job records;
- no hard-coded `1024 * 1024` Flux 2 Pro source cap remains.

## Acceptance Criteria

- Replicate Flux 2 Pro local source media no longer uses data URI transport.
- Replicate Flux 2 Pro source and reference images are transported through
  provider-accepted HTTPS URLs.
- If Replicate file upload transport is not implementable from the current C#
  layer, large local Flux 2 Pro image submission fails closed with a precise
  transport-unavailable error.
- Flux 2 Pro policy models up to 8 input images, JPEG/PNG/GIF/WebP, and 9 MP
  total input limit.
- Flux 2 Pro validates decoded dimensions before submit.
- Capability metadata is corrected deliberately and covered by routing tests.
- Gemini inline media caps remain intact.
- URL-upload providers do not inherit Gemini's aggregate inline cap by default.
- fal GPT Image 2 Edit, Seedance, and Kling behavior is not regressed.
- Provider-derived limits carry source URLs and retrieval dates.
- Unknown provider limits are labeled as Rook guards.
- No provider transport internals leak into persisted or bridge-visible data.
- Normal tests use fake HTTP and fake transport seams only.

## Risks

The main risk is Replicate upload protocol availability from the C# layer. The
JavaScript client documents `replicate.files.create`, automatic file uploads,
100 MiB upload size, 24-hour file expiration, and using `urls.get` as model
input. If the public raw HTTP equivalent is unavailable or unsuitable for this
project's direct `HttpClient` substrate, implementation should stop at a
transport-unavailable failure rather than reintroducing large data URIs.

Correcting Flux 2 Pro to support text-to-image can alter UI and routing. This
must be treated as a capability correction with explicit tests, not as incidental
metadata churn.

The policy abstraction can grow too large. Keep the first slice image-only and
only wire immediate consumers. Video can remain on its existing fal source-frame
policy until a later unification is justified.

## Self-Review

- No placeholders remain.
- Scope is Replicate Flux 2 Pro first, not a broad media framework.
- Model input, transport, and Rook safety policy are distinct.
- The design does not claim an unverified C# Replicate file upload endpoint.
- Pixel/megapixel validation is required before submit.
- Provider source freshness and unverified-limit labeling are explicit.
- Gemini and existing fal paths are protected from accidental behavior changes.
