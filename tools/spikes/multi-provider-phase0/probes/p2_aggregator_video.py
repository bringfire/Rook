from __future__ import annotations

import httpx

from harness.capture import CaptureContext, append_notes, write_manifest, write_redacted
from harness.env import load_keys, require_key
from harness.fixtures import assert_synthetic_prompt, synthetic_prompt
from probes._common import capture_fetch_or_result, parse_probe_args, poll_json, safe_submit_data, timed_request, write_cancel_evidence


def main() -> None:
    args = parse_probe_args("P2 aggregator-hosted video probe")
    keys = load_keys()
    provider = "fal.ai" if "fal" in args.catalog_url.lower() else "replicate"
    key_name = "FAL_KEY" if provider == "fal.ai" else "REPLICATE_API_TOKEN"
    key = require_key(key_name, keys.fal if provider == "fal.ai" else keys.replicate)
    prompt = synthetic_prompt("white_arch")
    assert_synthetic_prompt(prompt)
    headers = _headers(provider, key)
    body = {"prompt": prompt}
    ctx = CaptureContext("p2", provider, args.model_id, args.catalog_url, args.price_observed)
    terminal_body = None
    with httpx.Client(timeout=900) as client:
        response, elapsed = timed_request(
            lambda: client.post(args.endpoint_url, headers=headers, json=body)
        )
        write_redacted("submit", {"method": "POST", "url": args.endpoint_url, "headers": headers, "json": body}, response, ctx)
        data = safe_submit_data(response, probe_id="p2", ctx=ctx)
        if data is None:
            return
        poll_url = args.poll_url or data.get("status_url") or data.get("urls", {}).get("get")
        if poll_url:
            terminal_body = poll_json(
                client,
                probe_id="p2",
                ctx=ctx,
                url=poll_url,
                headers=headers,
                status_getter=lambda payload: str(payload.get("status") or payload.get("state") or "unknown"),
                terminal={"completed", "succeeded", "failed", "canceled", "cancelled"},
                max_polls=90,
                interval_seconds=5.0,
            )
        else:
            terminal_body = data
        result_url = args.result_url or data.get("result_url") or data.get("output_url")
        capture_fetch_or_result(
            client,
            probe_id="p2",
            ctx=ctx,
            headers=headers,
            result_url=result_url,
            terminal_body=terminal_body,
            original_endpoint=args.endpoint_url,
        )
    write_cancel_evidence(
        "p2",
        ctx,
        "Cancellation evidence must be filled from either a second low-cost video cancel attempt "
        "or provider API docs. Decision 1 is incomplete until this file states supported/unsupported and billing semantics.",
    )
    write_manifest(ctx, "complete" if response.is_success else "incomplete", {"submit_elapsed_seconds": elapsed})
    append_notes("p2", f"- submit elapsed_seconds={elapsed:.2f}; status_code={response.status_code}")


def _headers(provider: str, key: str) -> dict[str, str]:
    if provider == "fal.ai":
        return {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    return {"Authorization": f"Token {key}", "Content-Type": "application/json"}


if __name__ == "__main__":
    main()
