# Video Provider Payload Audit Procedure

Status: audit-ready procedure, no live capture performed in the sidecar-contract slice

## Purpose

This procedure records how to capture sanitized provider completion/result payloads for deciding whether Rook can ingest provider-supplied video posters, or whether Rook must derive frame sidecars through MP4 extraction.

This procedure does not authorize live provider generations. Live Veo and fal captures require explicit cost approval, model selection, credential confirmation, and a named verification task.

## Capture Targets

Capture exactly the provider responses needed to answer the sidecar question:

- Veo: completed operation payload returned by the poll/status request.
- Veo: downloaded video URI shape only, not downloaded bytes.
- fal: result payload returned by the queue response endpoint.
- fal: model identity used for the request, such as Seedance or Kling, without provider-private transport URLs.

## Redaction Rules

Sanitized payloads and findings must not contain:

- No API keys.
- No signed URLs.
- No provider-private queue/status/result/cancel tokens.
- No local filesystem paths.
- No raw video bytes.
- No raw image bytes.
- No sensitive prompts.
- No account, project, bucket, tenant, or organization identifiers that are not needed for structural analysis.

Replace sensitive values with stable placeholders:

- `https://provider.invalid/redacted-video.mp4`
- `https://provider.invalid/redacted-poster.jpg`
- `<REDACTED_PROMPT>`
- `<REDACTED_PROVIDER_JOB_ID>`
- `<REDACTED_ACCOUNT>`

## Non-Inference Rule

Unknown provider fields are inert. Fields named `thumbnail`, `preview`, `image`, `frame`, `firstFrame`, `lastFrame`, `posterUrl`, or similar do not imply `poster`, `start_frame`, or `end_frame` support until a provider-specific mapping is designed, reviewed, and tested.

## Sanitized Fixtures

Example sanitized shapes live under:

- `docs/rook_docs/fixtures/video-provider-payload-audit/veo-completion.sanitized.example.json`
- `docs/rook_docs/fixtures/video-provider-payload-audit/fal-result.sanitized.example.json`

These files are placeholders for structure only. They are not evidence that any provider returns trustworthy posters or frame-exact sidecars.

## Cost-Gated Follow-Up Checklist

Before running live captures:

- Confirm the provider credentials are intentionally available for this task.
- Confirm the exact Veo model and fal model.
- Confirm the maximum number of jobs: one Veo job and one fal job.
- Confirm the cost ceiling in writing.
- Confirm where sanitized findings will be recorded.
- Confirm raw payloads will remain local and temporary until redacted.

After live captures:

- Redact payloads using the rules above.
- Update sanitized findings with only structural evidence.
- Decide whether provider-poster ingestion is viable for display-only thumbnails.
- Decide whether MP4 extraction is required for `start_frame` and `end_frame`.
- Keep extraction tooling decisions in a separate Tier 3 design.
