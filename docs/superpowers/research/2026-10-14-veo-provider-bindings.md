# Veo provider binding admission — 2026-10-14

Status: **No fal Veo binding is admitted for new production submissions.** The approved offline implementation path may be tested with injected fixtures. Published retirement notices remain unresolved; successful HTTP/generation probes would not establish continuity.

## Official evidence

All links below were read on 2026-10-14. API documentation describes candidate contracts, not continuing support after retirement. No authoritative successor or continued-support commitment resolving these notices was found in the inspected official sources. No credentials, live generation, or external messages were used.

| Tier | Mode | Candidate application (relative to `fal-ai/veo3.1`) | API evidence | New-submission cutoff | Admission |
| --- | --- | --- | --- | --- | --- |
| Standard | T2V | root | [API](https://fal.ai/models/fal-ai/veo3.1/api) | 2026-11-17T00:00:00Z | unverified continuity |
| Fast | T2V | `/fast` | [API](https://fal.ai/models/fal-ai/veo3.1/fast/api) | 2026-11-17T00:00:00Z | unverified continuity |
| Lite | T2V | `/lite` | [API](https://fal.ai/models/fal-ai/veo3.1/lite/api) | 2026-11-17T00:00:00Z | unverified continuity |
| Standard | I2V | `/image-to-video` | [API](https://fal.ai/models/fal-ai/veo3.1/image-to-video/api) | 2026-11-17T00:00:00Z | unverified continuity |
| Fast | I2V | `/fast/image-to-video` | [API](https://fal.ai/models/fal-ai/veo3.1/fast/image-to-video/api) | 2026-11-17T00:00:00Z | unverified continuity |
| Lite | I2V | `/lite/image-to-video` | [API](https://fal.ai/models/fal-ai/veo3.1/lite/image-to-video/api) | 2026-11-17T00:00:00Z | unverified continuity |
| Standard | Interp | `/first-last-frame-to-video` | [API](https://fal.ai/models/fal-ai/veo3.1/first-last-frame-to-video/api) | not independently extracted | unverified |
| Fast | Interp | `/fast/first-last-frame-to-video` | [API](https://fal.ai/models/fal-ai/veo3.1/fast/first-last-frame-to-video/api) | not independently extracted | unverified |
| Lite | Interp | `/lite/first-last-frame-to-video` | [API](https://fal.ai/models/fal-ai/veo3.1/lite/first-last-frame-to-video/api) | not independently extracted | unverified |
| Standard | References | `/reference-to-video` | [API](https://fal.ai/models/fal-ai/veo3.1/reference-to-video/api) | not independently extracted | unverified |
| Fast | References | `/fast/reference-to-video` | [API](https://fal.ai/models/fal-ai/veo3.1/fast/reference-to-video/api) | not independently extracted | unverified |

The actual Fast I2V page now says November 17. The earlier October 22 search excerpt is superseded by this directly read page; it was never admission evidence. Remaining rows require independent notice, framing, pricing, and lifecycle verification before enablement, even if another mode of the same tier is verified.

## Profiles and lifecycle

`fal-veo-candidate-v1` is the spec's conservative offline profile: explicit selected aspect, duration string, audio on, auto-fix off, moderation `"4"`, no seeded references. The T2V schemas publish these controls; `auto_fix` defaults true upstream, so explicit false is necessary. Do not infer reference framing behavior from I2V. Reference preprocessing remains unverified and production reference bindings remain disabled for that additional reason.

Candidate submit transport is `https://queue.fal.run/{application}`. The [official queue contract](https://fal.ai/docs/documentation/model-apis/inference/queue) defines asynchronous submission/status/result/cancel, server retry opt-out, and cancellation acknowledgement. The per-binding lifecycle root and returned URL/request-ID association still require verification before admission. Offline fixtures use explicit allowlisted roots and are not evidence for production URLs. In particular, do not blindly append lifecycle paths to mode suffixes.

Pricing revision `fal-veo-candidate-rates-2026-10-14` preserves the **spec's dated candidate rates**, USD/sec with audio: Standard .40/.40/.60; Fast .15/.15/.35; Lite .05/.08 for 720p/1080p/4k respectively (Lite has no 4k). These are not a freshly qualified per-endpoint production rate card. Unknown/unverified per-binding prices cannot admit a generation or become zero. All enabled replacements must carry official pricing evidence and updated revisions.

## Google primary

The [Google Veo guide](https://ai.google.dev/gemini-api/docs/veo) documents the three approved preview model IDs and still contains REST `predictLongRunning` examples, followed by operation polling and media download. Its broader [video landing page](https://ai.google.dev/gemini-api/docs/video) describes `generateContent` instead. Preserve the existing primary transport during this offline feature work; record this documentation inconsistency and do not claim live primary qualification or silently switch protocols. Google remote cancellation is not established by these examples.

## Enabling a binding

Require an authoritative continuity resolution, exact submit/lifecycle identities and trusted HTTPS origins, source-framing/preprocessing policy, current required schema fields, and per-endpoint pricing evidence with verification date/revisions. Revise and reapprove the design if identity or semantics change. Expired/unverified bindings cannot send uploads or generation; known historical handles retain separately validated lifecycle cleanup without enabling new work.

## Offline implementation verification (2026-10-14)

Managed Release build succeeded with zero errors (481 compiler/platform/analyzer warnings). The hermetic managed run passed 4,558 tests with the plan’s exact LiveSmoke and two fixture exclusions; Node passed 55 UI tests; Python passed 89 video contract/profile tests. Deterministic tests cover held-response JSONL restore, blocked/failed stop and intent commits, frozen-media A→B→A admission, actual fal upload bytes/repeated references, primary/fallback concurrency, completed-marker repair, and all-role direct blob visibility. Authenticated fal upload-initiation 401 carries credential evidence; a rejected signed CDN upload URL does not invalidate the API key. These are offline fixtures and are not production admission evidence. All continuity flags remain false; no live/billed requests, native builds, merge, or deployment occurred.
