# Automatic video source framing and actionable preflight

Date: 2026-10-15

Status: Written design for human review. This document does not approve an implementation plan, product changes, deployment, or enabling fal Veo.

Source baseline: `4978b44418509cb2bb99c1a0472b7d8be9e1e9ca`, merged into `main` and locally deployed as a managed companion/UI update. Draft branch: `codex/vision-video-framing-spec`.

Related design: [Google video fal fallback](2026-10-14-google-video-fal-fallback-design.md). This design supersedes that document's section 6 prohibition on local resizing/padding/cropping **when the caller explicitly chooses the new framing behavior**. The earlier routing, lifecycle, pricing, cancellation, publication, and production-admission requirements remain in force.

## 1. User intent and observed defects

Rook must accept an ordinary image and prepare it for the selected video shape inside Rook. Users must not be sent away to crop or resize their image. The user approved two selectable preview cards beneath Aspect ratio: **Fit — keep whole image**, selected by default, and **Fill — crop to frame**.

The motivating image is 1166x912, used as the start frame for Veo 3.1 I2V, 1080p, eight seconds, with 16:9 output. The current panel reports a framing incompatibility in the cost strip and then replaces it with “Cost estimate is out of date — adjust a field to retry.” Meanwhile, the fal route is disabled, so preparing another image cannot make that route available. These are separate states and must be presented separately.

Fal documents cropping inputs outside 16:9/9:16; it does not document refusing every differently shaped image. The exact selected-ratio rejection was Rook's conservative policy. The two native output shapes are a different constraint. [Fal I2V schema](https://fal.ai/models/fal-ai/veo3.1/image-to-video/api), [Google Veo guide](https://ai.google.dev/gemini-api/docs/veo).

Success means the user can select Fit or Fill, see what Rook will send, and continue through ordinary cost confirmation without editing the source elsewhere. If no provider route is available, Rook states the actual reason before submission and offers the appropriate Settings action. A new framing control cannot make a disabled provider available.

## 2. Scope and design decision

Add framing to I2V and interpolation for the three affected Google Veo 3.1 models and corresponding fal Veo tiers. Use the existing panel, managed video subsystem, artifact resolver/store, and bundled FFmpeg infrastructure. Do not add an external dependency, provider SDK, HTTP server, or native ABI change.

**Proposed decision for review:** Rook prepares both Fit and Fill locally. Preview cards display the actual prepared images, not a CSS approximation of an unspecified provider crop. Fal receives an already framed image. Google receives the same framed pixels when that explicit choice is used. Providers may still change the scene during generation; this is a guarantee about the submitted source, not every frame of the resulting video.

Alternatives considered:

- Passing the original to fal and labeling its crop preview approximate is smaller, but cannot promise that the displayed crop is what is submitted. It is not the selected approach.
- Requiring manual preparation or merely improving the rejection text does not meet the user's request.

Not included: arbitrary output aspect ratios, freehand crop editing, crop-position controls, generative outpainting, background generation/blur, new video models, reference-image reframing, video extension, changes to image generation/prompt enhancement, or enabling production fal Veo submissions.

## 3. Panel behavior

Place **Framing** immediately beneath Aspect ratio whenever an affected I2V/interpolation request has source frames. Show two selectable cards with the same source:

| Card | Copy | Behavior |
| --- | --- | --- |
| **Fit — keep whole image** | “Adds padding automatically. Nothing is cut off.” | Default on first entry; preserve all visible image content. |
| **Fill — crop to frame** | “Fills the output shape. Some edges may be cropped.” | Center-crop automatically after scaling; no manual crop step. |

Use a checkmark, radio semantics, keyboard navigation, visible focus, and text as well as the thumbnail to identify selection. Both cards show the chosen output shape. With interpolation, each card shows the prepared start and end frames, labeled separately. Apply the same mode to both frames, preparing each independently.

Keep the user's selection when changing output ratio, resolution, duration, prompt, or model within this supported flow. Recompute affected previews when sources, ratio, resolution, or framing change. Default to Fit on first entry; do not reset a deliberate Fill selection during ordinary edits. Hide the control and omit its wire field for T2V/reference-only requests and unaffected providers. Returning to I2V/interpolation may restore the last deliberate selection.

Show source dimensions and output shape separately; do not imply that an input must originally be 16:9 or 9:16. Changing the output ratio updates both previews. Show preparation progress in the preview area. A failed alternative card must not invalidate a successfully prepared selected card. Prevent confirmation until the selected preview matches the estimate. Never show an old preview as current while a newer request is pending.

Keep the existing source artifact and picker selection. Do not replace the original in the gallery, overwrite it, or create duplicate gallery entries for every edit. Cost confirmation identifies the selected framing mode alongside the effective provider and price. There is no additional crop-approval dialog or separate editing application.

## 4. Local preparation contract

Accept the existing artifact-based source references. Resolve and freeze original bytes before preparing either variant. Decode PNG/JPEG/WebP with the existing bundled FFmpeg infrastructure, including WebP rather than assuming Windows GDI+ supports it. Use a fixed, versioned CPU rendering/encoding profile; resolve and verify the bundled executable through existing helpers. No user-supplied paths, filters, commands, or encoder arguments are admitted.

Normalize EXIF orientation before geometry calculations and apply one documented orientation/color policy consistently to preparation and preview. Composite transparency onto opaque black. Strip metadata that can introduce timestamps, private source information, or nondeterministic output. Preserve the originals.

Prepared canvas sizes follow the selected video resolution and ratio:

| Resolution | 16:9 | 9:16 |
| --- | --- | --- |
| 720p | 1280x720 | 720x1280 |
| 1080p | 1920x1080 | 1080x1920 |
| 4k | 3840x2160 | 2160x3840 |

These are source-preparation sizes, not newly advertised model capabilities. Lite still cannot select 4k. Preparation may scale up or down as disclosed by Fit/Fill; choosing the new control expressly authorizes that operation. A low-resolution source can be prepared, with a quality hint if upscaled. Do not ask the user to upscale it manually. Requests outside existing resolver byte limits, undecodable inputs, decompression/resource limits, or provider capability limits can still fail with their actual reason.

For an oriented source `W x H` and canvas `Tw x Th`:

- **Fit:** scale by `min(Tw/W, Th/H)`, use Lanczos resampling, floor the scaled dimensions to positive integers, and center the complete image on an opaque black canvas. An odd padding pixel goes to the right/bottom. No visible source region is discarded.
- **Fill:** scale by `max(Tw/W, Th/H)`, ceil the scaled dimensions, and take the centered `Tw x Th` crop. An odd excess pixel is removed from the right/bottom. The preview shows the actual cropped result.

Apply the same declared geometry in all runtime targets. Proposed rendering profile `video-source-framing-v1` bounds decoding to 32,000,000 pixels and a 16,384-pixel maximum edge, without increasing existing resolver byte limits. Reject before allocating an unbounded raster. Encode PNG first; if it exceeds 8,000,000 bytes, use deterministic JPEG encoding with MJPEG quantizers 2, then 3, then 4, stopping at the first result within that bound. Record the selected format/quantizer. If none fits, return `source_preparation_failed`; do not silently change the selected resolution, framing mode, or output ratio. Planning must verify the bundled build supports this profile with real fixtures.

Validate the resulting bytes, MIME, dimensions, and size before use. Every derived source must exactly match the selected ratio and canvas. For explicit framing, provider size/dimension compatibility is checked against these prepared bytes; the former raw-image minimum-side rule must not reject an image that Rook successfully prepares to the admitted source profile. Other endpoint/option constraints remain intact.

No remote upload, provider validation request, generation, or billable call is permitted during preview or estimate preparation.

## 5. Request and compatibility contract

Add optional top-level `source_framing: "fit" | "fill"` to estimate/submit for affected I2V/interpolation requests. It belongs to Rook's media handling, not provider-specific `options`. Unknown values and uses on unsupported modes/providers are typed field errors; do not ignore or translate them silently. The panel always supplies its selected value in the supported flow.

Preserve legacy Google requests that omit the field: send their original source bytes under the existing provider behavior. Do not impose fal's framing checks or the new local-renderer dependency on those requests. Legacy fal requests without the field retain unchanged-source behavior for already compatible images. If their source needs reframing, return `framing_choice_required` on `source_framing`, explaining that `fit`/`fill` makes Rook prepare it automatically. Do not claim fal refuses the image or ask the caller to crop it externally. Newly generated panel requests cannot enter this legacy branch.

T2V reference images remain unmodified under their separately reviewed endpoint profile. Do not apply the start/end-frame policy to references, discard slots, deduplicate repetitions, change tiers, or bypass explicit Google option incompatibilities.

An explicit Fit/Fill submission requires the current estimate fingerprint and numeric cost cap. This is an opt-in requirement for the new behavior; omitted-field legacy confirmation contracts remain as before. Source references continue to name original artifacts. Internal derived references never replace the user's original request or provenance.

Update managed parsing/projections, panel bridge, and Python video tool schemas/documentation consistently. Audit native forwarding for the additive fields. Keep HTTP ownership native and managed dispatch companion-backed; do not create a second public surface.

## 6. Preview ownership and lifetime

Add a panel bridge operation `preview_video_framing` to the existing video dispatcher. It shares the same preparation service as estimate/submit. It receives the affected model/mode, original source references, resolution, and output ratio; it returns per-mode/per-slot prepared-image references, dimensions, digests, and recipe metadata. It does not create a video job, quote, provider handle, or permission to generate. Do not add an MCP tool or native HTTP route solely to transport thumbnails.

Use owned, non-gallery prepared-image assets and the existing local blob mechanism for preview pixels. They must not be confused with generated-video artifacts or loosen the durable-completion fence for videos and sidecars. Preview URLs, tokens, artifact IDs, access timestamps, and cache insertion order are not content identity.

Bound retained encoded original/derived cache bytes to 256 MiB and 16 preparation bundles, including pinned entries. Expire unpinned entries after 30 minutes of inactivity, evicting least-recently-used unpinned bundles first. Pin admitted-job media until that job releases its execution buffers. If capacity cannot be obtained without evicting pinned work, return a retryable preparation-busy error; do not exceed the bounds. Clean up only assets owned by this feature. Private derived previews may expire after their jobs release them; durable digest/recipe evidence remains even if a preview asset expires. Never evict/delete original or historical input artifacts, durably completed videos, or unrelated gallery media. Reuse identical preparation work across edits and repeated slots without losing slot order or role identity.

Cache misses/expiry may transparently regenerate previews from frozen originals. If regeneration changes content digests or recipe identity, refresh the selected preview and estimate before confirmation. A preview token is an optimization, never authoritative evidence of source content. Fresh panel loads after restart can regenerate previews; they do not resume or replay video submissions.

Preview preparation has its own cancellation and a 15-second total preflight budget per bundle; it runs off the Rhino/UI thread with bounded concurrency. A newer request supersedes the older UI result and cancels its unneeded work. Cancellation must terminate the owned renderer process and clean up only its temporary files. No blocking local preparation is allowed on the Rhino main thread.

## 7. Bind confirmation to the pixels sent

Extend the existing immutable-media discipline rather than introducing a mutable file between confirmation and dispatch. Track the original snapshot and the selected prepared snapshot separately, for each ordered role:

- Original artifact/reference, original byte digest, byte length, MIME, decoded/oriented dimensions.
- Framing mode, target canvas, exact scale/pad/crop geometry, matte, renderer/profile revision, verified renderer identity, and encoding settings.
- Prepared byte digest, length, MIME, dimensions, and internal owned asset reference.

The fingerprint includes the selected recipe and original/prepared content identities along with the existing request, routes, profiles, and endpoint-specific prices. Exclude ephemeral preview IDs/URLs/tokens. Changes to mode, source bytes, target geometry, renderer/profile, prepared bytes, candidate bindings, or prices require a fresh estimate. Identical content after cache regeneration does not become stale merely because an asset ID changed.

Estimate responses expose the selected mode, recipe revision, per-slot original/prepared digests, dimensions, and preview references in a `source_preparation` object. Request `source_framing` remains the scalar enum; clients cannot supply authoritative preparation evidence. The selected preview and accepted quote must refer to the same prepared digests; missing/mismatched metadata cannot authorize confirmation. At job admission, freeze/pin those prepared bytes and persist `source_preparation` evidence with the existing execution snapshot. Before generation dispatch, recheck original/derived identities, the confirmed fingerprint/cap, gate/credential eligibility, deadline, first stop, and latest terminal state. Validate the bytes held for the actual payload/upload, not a later re-read that could authorize different prepared content.

Send the immutable prepared bytes on both Google and fal paths when Fit/Fill was selected. Do not regenerate from mutable files after validation. Unchanged quoted fallback may reuse that prepared snapshot; changing the route cannot silently choose a different framing recipe. Persist `prepared_media` evidence for the bytes actually sent, while retaining original-source provenance separately. Keep complete ordered start/end roles and repeated reference positions.

After job admission all preparation/cache recovery, upload, submission, polling, download, and publication remain within the existing single 20-minute execution budget. Preview work does not authorize a fresh job budget, reset a running deadline, or weaken durable dispatch intent/acceptance ordering. Original stop latching, immediate execution cancellation, persistence-failure reporting/retry, restart uncertainty, bounded remote cleanup, and completed-artifact preservation stay unchanged.

## 8. Route availability before irrelevant compatibility errors

Keep all production fal Veo continuity flags disabled. This feature cannot override or reinterpret the release gate. No successful preview, build, estimate, or live probe constitutes endpoint-continuity approval.

Separate model/endpoint availability, credential presence, source preparation, and confirmed cost. A configured Google key keeps the Google primary usable even when fal is disabled or incompatible. Fal candidate incompatibility remains conditional evidence, not a fatal Google validation error.

When Google credentials are missing and fal is disabled, the panel must prominently say: **“Video generation needs a Google API key. Fal Veo fallback is currently disabled.”** Provide an **Open Settings** action. Do not ask the user to change their source, ratio, price confirmation, or API key for another unrelated provider. With a valid Google route, preserve that route and do not impose raw fal source restrictions.

Read-only model metadata may add aggregate `can_generate`/reason fields without repurposing `new_submission_available` to mean “credential valid.” Refresh availability after Settings changes and on returning to the panel. Presence is not validation; do not decrypt/probe an unused fal credential when Google can run. Secret-store failures remain distinct from missing keys.

Local previews remain usable without generation credentials. A route-unavailable result cannot become a fake price quote or enable submit. Check endpoint admission before reporting that endpoint's source compatibility. Disabled fal must not report a source-ratio error as the reason the current request cannot run.

## 9. Estimate and error state

Represent preview/preparation state and estimate state independently. Estimate states are idle, pending, ready, failed, or invalidated by a real input/quote change. A failed estimate is not automatically an out-of-date estimate.

Retain the actual current error with its request identity. On Generate, refresh/await the current estimate; if it fails, show that failure and its action. Never overwrite it with “adjust a field to retry.” Offer retry without requiring a dummy field edit. Keep source selections, framing choice, prompt, output controls, and previously accepted history intact.

Show framing/preparation errors beside the cards; route/credential availability above Generate with Settings guidance; prices in the cost strip. Genuine request/media/price changes invalidate confirmation and refresh previews/estimate as needed. Lost/late responses cannot overwrite newer state or open a cost modal for different inputs. No error recovery automatically submits or retries generation.

Typed errors distinguish `video_route_unavailable`, `framing_choice_required`, `source_preparation_failed`, existing secret/credential failures, genuine `estimate_stale`, and cost-cap failures. Preserve safe messages and structured detail through the handler/UI. Do not expose raw provider/renderer output, filesystem paths, credentials, or signed upload URLs.

## 10. Acceptance and regression coverage

Deterministic fixtures and actual component tests must establish:

1. The 1166x912 source with 1080p/16:9 succeeds under Fit and Fill preparation; both yield actual 1920x1080 pixels, selectable in the panel, without a manual image-edit step.
2. Fit retains markers at every image edge and adds the specified matte; Fill produces the specified center crop. Portrait, square, already-matching, odd-dimension, and extreme-but-admitted inputs follow the declared geometry.
3. Start/end frames prepare independently under one selected mode with correct roles; original artifact bytes and picker identity remain unchanged.
4. JPEG/PNG/WebP, EXIF rotations/flips, transparency, upscaling, PNG-to-JPEG fallback, oversized/undecodable sources, resource limits, missing renderer, encoder failure, timeout and cancellation produce the specified results. No format is advertised as locally prepared without actual decoder/encoder fixtures.
5. The displayed selected preview is derived from exactly the prepared bytes handed to Google/fal, including actual upload and Google inline-payload capture. Provider-native cropping is not mistaken for an exact local preview.
6. Local previews succeed with no configured keys and with fal disabled, making zero provider/upload calls. The same state blocks generation with actionable Settings guidance, not a ratio or stale-cost error.
7. A configured Google primary can accept the source regardless of fal gate/framing incompatibility. Legacy Google omission retains original bytes and does not require the new renderer; explicit framing sends the selected derived bytes.
8. New UI requests always supply the selected Fit/Fill value. Unsupported modes/values are rejected explicitly; legacy fal requests receive automatic-preparation guidance rather than instructions to crop externally. Reference-only and unrelated-provider paths retain their behavior.
9. Fingerprints change for framing/source/recipe/renderer/prepared-byte/price changes, stay stable across equivalent cache regeneration, and enforce the selected endpoint's current price/cap.
10. A barrier test changes source A to B to A around preparation, quote, preview and dispatch admission. Another tampers with a cached prepared asset. Neither may authorize different sent bytes using a valid-looking fresh quote.
11. Cost/preview responses completed out of order, rapid ratio changes, Settings changes and selecting a different framing card cannot restore stale pixels, prices, errors or confirmation.
12. An estimate failure remains its actual failure after clicking Generate, retries without a field edit, and produces no submit request. Genuine stale confirmation still demands a fresh confirmed quote, without automatic generation replay.
13. Cache eviction/expiry, restart, repeated slots, simultaneous jobs with different framing, pinned-byte admission and renderer cancellation preserve ownership and bounds; no original or completed artifact is removed.
14. Deadline/user-stop/shutdown and blocked/failed ledger writes retain the winning stop, prevent dispatch, and cannot be overwritten by deferred failures. Existing held-submit uncertainty, completion/marker repair and direct-blob fencing tests still pass.
15. Production fal Veo defaults remain disabled in factories/catalogs and on the deployed byte-identical companion. A preview or framing choice cannot admit a gated upload/generation.

Run the existing managed/UI/Python regression checks with the previously documented live/unavailable-fixture exclusions, plus real local renderer fixtures. Preserve their limitations in the report. Implementation ends with independent final review. Local deployment, native/runtime qualification, provider billing/quality tests, and enabling a production binding remain separate explicit actions.

## 11. Review boundary

Only this specification is requested now. Approval of this written spec permits writing the implementation plan for review; product implementation follows approval of that plan and the chosen execution method. The focused behavior change is automatic framing inside Rook, accurate previews, and honest preflight/error states. It is not completion or enablement of fal Veo production support.
