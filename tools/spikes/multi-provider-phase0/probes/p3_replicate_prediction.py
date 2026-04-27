from __future__ import annotations

import httpx

from harness.capture import CaptureContext, append_notes, write_manifest, write_redacted
from harness.env import load_keys, require_key
from harness.fixtures import assert_synthetic_prompt, synthetic_prompt
from probes._common import capture_fetch_or_result, determine_outcome, parse_probe_args, poll_json, safe_submit_data, timed_request, write_cancel_evidence


def main() -> None:
    args = parse_probe_args("P3 Replicate prediction probe")
    key = require_key("REPLICATE_API_TOKEN", load_keys().replicate)
    prompt = synthetic_prompt("red_cube")
    assert_synthetic_prompt(prompt)
    headers = {"Authorization": f"Token {key}", "Content-Type": "application/json"}
    if args.replicate_mode == "official-model":
        # POST /v1/models/{owner}/{name}/predictions — model is in URL, not body.
        body = {"input": {"prompt": prompt}}
    else:
        # versioned or unified-model-id: POST /v1/predictions, version field carries
        # either a 64-char hash (versioned) or an owner/name slug (unified-model-id).
        body = {"version": args.model_id, "input": {"prompt": prompt}}
    ctx = CaptureContext("p3", "replicate", args.model_id, args.catalog_url, args.price_observed)
    terminal_body = None
    with httpx.Client(timeout=300) as client:
        response, elapsed = timed_request(
            lambda: client.post(args.endpoint_url, headers=headers, json=body)
        )
        write_redacted("submit", {"method": "POST", "url": args.endpoint_url, "headers": headers, "json": body}, response, ctx)
        data = safe_submit_data(response, probe_id="p3", ctx=ctx)
        if data is None:
            return
        poll_url = args.poll_url or data.get("urls", {}).get("get")
        if poll_url:
            terminal_body = poll_json(
                client,
                probe_id="p3",
                ctx=ctx,
                url=poll_url,
                headers=headers,
                status_getter=lambda payload: str(payload.get("status", "unknown")),
                terminal={"succeeded", "failed", "canceled"},
            )
        else:
            terminal_body = data
        result_url = args.result_url
        fetch_status = capture_fetch_or_result(
            client,
            probe_id="p3",
            ctx=ctx,
            headers=headers,
            result_url=result_url,
            terminal_body=terminal_body,
            original_endpoint=args.endpoint_url,
        )
    write_cancel_evidence(
        "p3",
        ctx,
        "Cancellation evidence must be filled from either a low-cost Replicate cancellation attempt "
        "or Replicate's prediction cancellation API docs before the spike doc binds Decision 1.",
    )
    outcome = determine_outcome(response, fetch_status)
    write_manifest(ctx, outcome, {"submit_elapsed_seconds": elapsed, "submit_status_code": response.status_code, "fetch_status_code": fetch_status})
    append_notes("p3", f"- submit elapsed_seconds={elapsed:.2f}; status_code={response.status_code}; fetch_status_code={fetch_status}; outcome={outcome}")


if __name__ == "__main__":
    main()
