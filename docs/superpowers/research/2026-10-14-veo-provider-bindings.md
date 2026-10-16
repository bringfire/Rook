# Veo provider binding admission — 2026-10-14

## Current admission amendment — 2026-10-16

The user explicitly authorized current endpoint enablement, Google-primary routing with missing/revoked-key and proven-non-acceptance fallback, live testing, and removal of the November 17 automatic cutoff. This supersedes the historical disabled-binding status recorded below. The notice remains unresolved maintenance evidence; this amendment does not claim a provider support commitment or an automatic future migration.

Nine bindings (Standard/Fast/Lite × T2V/I2V/interpolation) are admitted by their current documented contracts, with `SubmissionVerified` rather than a claim of continuing support. No date-derived shutdown or agent-imposed dollar cap is added. Reference modes remain unqualified and unavailable through fal; valid Google reference requests retain their primary route.

On 2026-10-16 all eleven mode-specific official API pages and queue OpenAPI schemas were retrieved. Captures and SHA-256 hashes are in ignored `artifacts/fal-veo-enablement/binding-contracts.json`. Standard and Fast support 720p/1080p/4k; Lite supports 720p/1080p. All nine admitted schemas accept the unchanged explicit profile: duration `4s`/`6s`/`8s`, selected `16:9`/`9:16`, audio on, auto-fix off, safety `4`, optional seed and mode-specific image fields. Rook's existing capability rules still restrict incompatible resolution/duration combinations. Prepared Fit/Fill inputs retain the approved immutable preview/quote/dispatch identity and resource bounds.

Per-endpoint published audio-on rates: Standard $.40/sec at 720p/1080p and $.60/sec at 4k; Fast $.15/sec at 720p/1080p and $.35/sec at 4k; Lite $.05/sec at 720p and $.08/sec at 1080p. The API pages independently repeat these rates for each admitted media mode. An authenticated read-only [pricing API](https://fal.ai/docs/platform-apis/v1/models/pricing) GET also confirmed base rates for all three tiers' T2V and I2V endpoints. No secret is recorded in evidence. Pricing revision is `2026-10-16`.

The official [fal-js queue implementation](https://github.com/fal-ai/fal-js/blob/main/libs/client/src/queue.ts) and [endpoint parser](https://github.com/fal-ai/fal-js/blob/main/libs/client/src/utils.ts) use the complete endpoint for submission, then owner/application only for status/result/cancel. This confirms lifecycle root `fal-ai/veo3.1` for all tiers/modes and `PUT` cancellation, despite generated OpenAPI paths including mode suffixes. Actual accepted URLs remain validated against the configured root and request ID. Live confirmation is pending and will be recorded separately.

New closed transport evidence: DNS failures and refused initial connections can route only when raised before response headers. A response-read failure cannot be reclassified even if its inner exception resembles DNS failure. Generic errors, reset/abort/timeout, cancellation, malformed acceptance and any accepted-job failure remain uncertain or terminal; no second generation is authorized. Credential warnings remain independent. The complete HTTP-call timeout is retained after separating response-header and body-read phases.

Observed red/green evidence: seven new managed regressions failed on the baseline (three missing-key admissions, four known connection failures); the new UI regression failed because it described a credential problem. After correction, 52 focused managed tests and 68 UI tests passed. A response-body timeout regression then failed before its fix; the broader video run passed 936 tests after it. Installed-runtime and paid provider qualification are pending. No claim of complete feature qualification is made by these offline results.

## Historical offline implementation record (2026-10-14)

The following sections describe the original disabled implementation and its former continuity gate, not the user-amended admission policy above.

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

Managed Release build succeeded with zero errors (481 compiler/platform/analyzer warnings). The hermetic managed run passed 4,580 tests with the plan’s exact LiveSmoke and two fixture exclusions; Node passed 55 UI tests; Python passed 89 video contract/profile tests. Deterministic tests cover held-response JSONL restore, blocked/failed stop and intent commits, frozen-media A→B→A admission, actual fal upload bytes/repeated references, primary/fallback concurrency, completed-marker repair, and all-role direct blob visibility. Authenticated fal upload-initiation 401 carries credential evidence; a rejected signed CDN upload URL does not invalidate the API key. These are offline fixtures and are not production admission evidence. All continuity flags remain false; no live/billed requests, native builds, merge, or deployment occurred.

## Independent final review and disposition

The fresh reviewer inspected the complete branch from `9057da3a` through `c4918547`, including retained prompt-enhancement fallback commits, and targeted fixes at `4fc34ade` and `0336d6de`. Six initial Important findings and the subsequent lifecycle-timeout finding are resolved with observed failing regressions followed by passing tests. Final verdict: ready conditionally as a disabled offline implementation; no remaining Important/Critical issue identified. The reviewer declined to judge no behaviors.

Resolved: trusted/bounded Google download redirects; initial-URL validation and a streaming 250 MiB ceiling; structural MP4 box/video-track/media validation using the tracked H.264 success fixture; safe affected Google polling/fetch errors; release of prepared source buffers; coordinated stop signalling/CTS disposal; and safe terminalization of provider-local timeouts without generation retry or fallback. Container validation is not full codec decoding or video-quality qualification.

Final commands: managed Release build and the exact full hermetic managed filter in the plan, 4,580 passed; both Vision Node files, 55 passed; Python video contract/profile files, 89 passed. Release has zero errors and 481 compiler/platform/analyzer warnings; no new video warning remains. The baseline timing failure passed in the final full runs. The two fixture exclusions still refer to the unavailable historical lifecycle document and absent `ROOK_TASK7_HTTP_FIXTURE`; LiveSmoke is excluded. No native/RookBIM build, deployment, live generation, billing, quality, or remote-cancellation qualification is claimed.

Deferred Minor findings:

- UI attribution: rejected Gemini evidence after an effective fal route does not update the Gemini warning; fallback notice reads `reason` rather than `fallback_reason`; the gallery reads `metadata.model` rather than the new effective/requested model fields.
- The `provider_timeout` detail code is missing from the outcome-adapter allowlist. Status/list retain safe messages and terminal state but lose this optional detail code.

## Follow-up corrections after `b870dedd`

The additional review reproduced three P2 defects with synthetic requests before fixes: the selected I2V/interpolation/reference endpoint borrowed T2V pricing ($3.20 instead of $7.20 for eight seconds at an injected $.90/second); a deferred worker failure overwrote a durably committed deadline; and a malformed successful Google operation name was accepted and polled. Regression tests also reproduced a completed record being overwritten by a deferred failure.

Pricing now selects the same endpoint binding as dispatch, including its source and missing-rate behavior. Real quote/manager tests cover all three media endpoints, direct estimation, initial missing-key routing, rejected-key fallback, cap rejection before fal dispatch, and the effective price retained in the durable record. Worker commits check the latched stop, cancellation, persistence failure and latest terminal state inside the transition gate; stop persistence retains its separate guarded append path so failed stops remain retryable. A barrier test checks the interval between selecting the stop and signalling cancellation.

Google acceptance validates relative `operations/{id}` and `models/{requested-model}/operations/{id}` resources before creating a handle. URLs, extra path segments, traversal, query strings, wrong-model names and malformed successful reply shapes become `submission_unknown`. Manager tests verify `Interrupted`, no handle, one submit request, no poll and no fal fallback. The corrective reviewer identified an additional legacy-submit parity gap for missing/non-string names and invalid JSON roots; observed failing tests drove the same unknown-outcome behavior at that seam.

Fresh verification after these corrections: 4,605 managed tests passed with the same LiveSmoke and two documented fixture exclusions; 55 Vision UI tests and 89 Python video/profile tests passed; managed Release built with zero errors and 481 warnings. An independent read-only corrective review reported no actionable findings and declined to judge no behaviors. Its ready verdict remains conditional on the disabled production continuity gate. No native/RookBIM build, merge, deployment or live provider request occurred in this correction pass. Earlier deferred Minor findings remain recorded above.

## Implementation rulings

- Ruling: Endpoint continuity remains unresolved; execute the approved disabled-binding offline implementation path — evidence cannot authorize new production fal Veo sends — cost if wrong: feature remains unavailable until authoritative support evidence is supplied.
- Baseline: 4469 passed, 1 timing failure GhSolveReceiptRegistryTests.Wait_BlocksUntilMatchingCompletionSignal (line 206); isolated unchanged rerun passed 1/1. Ruling: proceed with focused video TDD; retain this failure in final reporting and repeat full suite after implementation — unrelated scheduling sensitivity cannot establish a feature regression before any code edits.
- Task 4 Ruling: add a separate IFalVeoSourceFrameTransport beside the old interface, preserving existing third-party/fake source transport implementations — avoids breaking unrelated video adapters; new Veo dispatch requires the immutable prepared seam. Task 4 tests: 61 passed (new transport/classifier plus existing fal provider regression coverage).
- Task 7 Ruling: keep routed orchestration in a focused partial VideoJobManager.Routing.cs, sharing the same manager, ledger, concurrency semaphore, clock and artifact store — isolates new lifecycle fences from existing Vertex/legacy behavior without a second manager; cost if wrong: regression in shared result projection, covered by full provider suite.
- Task 8 Ruling: inject the same completion predicate in NativeGhBridgeRegistrar as well as the panel factory so HTTP and panel visibility agree; failed completion writes read the actual ledger asynchronously before rollback, quarantining unknown outcomes instead of deleting potentially durable output — cost if wrong: hidden provisional storage retained for later repair.
- Task 9 Ruling: expose an explicit confirmed-routing capability on the internal manager contract so legacy constructors/fakes retain their original parser and pricing behavior; use the shared manager for availability metadata — cost if wrong: legacy integrations could require migration, covered by existing handler tests.
- Task 12 Ruling: hydrate the committed cache in startup reconciliation, not the Lazy subsystem constructor, after the full suite demonstrated cached construction exceptions prevented retries — preserves the existing retry contract and fails artifact access closed before reconciliation — cost if wrong: old artifacts remain hidden until reconciliation succeeds.
- Task 12 Ruling: use existing GDI+ validation for PNG/JPEG and bounded RIFF/image-chunk validation for WebP, without adding a decoder dependency — Windows has no built-in GDI+ WebP codec — cost if wrong: a structurally valid but corrupt WebP bitstream may still be rejected by fal; no content is transformed.
