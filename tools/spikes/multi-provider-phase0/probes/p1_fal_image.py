from __future__ import annotations

import httpx

from harness.capture import CaptureContext, append_notes, write_manifest, write_redacted
from harness.env import load_keys, require_key
from harness.fixtures import assert_synthetic_prompt, synthetic_prompt
from probes._common import capture_fetch_or_result, parse_probe_args, timed_request, write_cancel_evidence


def main() -> None:
    args = parse_probe_args("P1 fal.ai image probe")
    key = require_key("FAL_KEY", load_keys().fal)
    prompt = synthetic_prompt("red_cube")
    assert_synthetic_prompt(prompt)
    headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    body = {"prompt": prompt}
    ctx = CaptureContext("p1", "fal.ai", args.model_id, args.catalog_url, args.price_observed)
    with httpx.Client(timeout=300) as client:
        response, elapsed = timed_request(
            lambda: client.post(args.endpoint_url, headers=headers, json=body)
        )
        write_redacted("submit", {"method": "POST", "url": args.endpoint_url, "headers": headers, "json": body}, response, ctx)
        try:
            terminal_body = response.json()
        except ValueError:
            terminal_body = {"raw_text": response.text}
        capture_fetch_or_result(
            client,
            probe_id="p1",
            ctx=ctx,
            headers=headers,
            result_url=args.result_url,
            terminal_body=terminal_body,
        )
    write_cancel_evidence(
        "p1",
        ctx,
        "P1 image route completed synchronously or as a single submit/result exchange. "
        "No separate low-cost cancellation attempt was run; cancellation behavior is not load-bearing for synchronous image generation.",
    )
    write_manifest(ctx, "complete" if response.is_success else "incomplete", {"elapsed_seconds": elapsed})
    append_notes("p1", f"- submit elapsed_seconds={elapsed:.2f}; status_code={response.status_code}")


if __name__ == "__main__":
    main()
