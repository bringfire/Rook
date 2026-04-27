# Multi-Provider Phase 0 Spike Harness

This is reviewable spike tooling for the Phase 0 generation-provider contract probe. It is not production Rook code and must not be referenced by production projects.

## Runtime State

Raw runtime state lives under `.scratch/multi-provider-spike/`:

- `.scratch/multi-provider-spike/.env`
- `.scratch/multi-provider-spike/.venv/`
- `.scratch/multi-provider-spike/captures/`
- `.scratch/multi-provider-spike/outputs/`

Only curated redacted evidence is committed under `docs/rook_docs/artifacts/$SPIKE_DATE-multi-provider-spike/`.

## Environment

Create `.scratch/multi-provider-spike/.env` with the keys available for this run:

```text
FAL_KEY=
REPLICATE_API_TOKEN=
GOOGLE_API_KEY=
TENCENT_KEY=
```

The harness reads only this local `.env` file. It does not read shell environment variables, repo-root `.env`, or user-home `.env` files.

## Setup

```powershell
py -m venv .scratch\multi-provider-spike\.venv
.scratch\multi-provider-spike\.venv\Scripts\python.exe -m pip install -r tools\spikes\multi-provider-phase0\requirements.txt
```

## Execution Order

1. Confirm provider credentials with non-generating endpoints or list-model endpoints.
2. Run `p1_fal_image.py`.
3. Run `p3_replicate_prediction.py`.
4. Run `p2_aggregator_video.py`.
5. Run `p4_hunyuan3d.py`.
6. Run `b1_gemini_image.py` if `GOOGLE_API_KEY` is available and the call is low-cost.
7. Fill in `probes/p5_tencent_audit.md` after a 30-minute direct-API availability audit.
8. Run `harness/curate.py`.
9. Run the C# shape probe.
10. Write the spike evidence doc and v0.2 framework update.

## Safety Rules

- Use only synthetic prompts from `harness.fixtures.SYNTHETIC_PROMPTS`.
- Use only synthetic or probe-generated input images.
- Do not commit raw captures, provider binaries, `.env`, or `.venv`.
- Do not add production abstractions in this PR.
