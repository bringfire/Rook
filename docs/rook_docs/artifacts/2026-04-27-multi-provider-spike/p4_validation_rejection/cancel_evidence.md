P4 first attempt: input validation rejection. The submit succeeded (HTTP 200, queued) and the queue lifecycle reached COMPLETED in 0.094 seconds because fal rejected the input image (1×1 PNG below Hunyuan's 128px minimum). Cancellation was not applicable because the job was already terminal by the time the harness's first poll observed COMPLETED.

The cancel URL was captured in the submit envelope (`https://queue.fal.run/.../{request_id}/cancel`) but exercising it on an already-terminal job is documented per the Hunyuan v3.1 OpenAPI schema as accepting PUT and returning whether cancellation succeeded — moot here since the job was complete.

For the canonical successful 3D run, see p4/cancel_evidence.md. Cancellation as a Phase 1 binding consideration is unaffected by this validation rejection.
