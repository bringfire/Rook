from __future__ import annotations

import argparse
import base64

import httpx

from harness.capture import CaptureContext, append_notes, write_manifest, write_redacted
from harness.env import load_keys, require_key
from harness.fixtures import write_red_cube_png
from probes._common import base_parser, capture_fetch_or_result, detect_provider, determine_outcome, poll_json, safe_submit_data, timed_request, write_cancel_evidence
from probes._common import ProbeArgs


def _parse() -> tuple[ProbeArgs, str]:
    parser = base_parser("P4 Hunyuan3D-2 image-to-mesh probe")
    # Per-probe extension: fal 3D models vary on the input image field name
    # (`image`, `image_url`, `input_image_url`, `input_image_urls`). Default to
    # `image` for backward compat with simple fal models; override per spike.
    parser.add_argument(
        "--image-field",
        default="image",
        help="JSON body field name for the input image. fal 3D models often use 'image_url' or 'input_image_url'.",
    )
    args = parser.parse_args()
    return ProbeArgs(
        model_id=args.model_id,
        endpoint_url=args.endpoint_url,
        catalog_url=args.catalog_url,
        price_observed=args.price_observed,
        poll_url=args.poll_url,
        result_url=args.result_url,
        cancel_url=args.cancel_url,
        replicate_mode=args.replicate_mode,
    ), args.image_field


def main() -> None:
    args, image_field = _parse()
    keys = load_keys()
    provider = detect_provider(args.endpoint_url)
    key_name = "FAL_KEY" if provider == "fal.ai" else "REPLICATE_API_TOKEN"
    key = require_key(key_name, keys.fal if provider == "fal.ai" else keys.replicate)
    image_path = write_red_cube_png()
    image_base64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    headers = _headers(provider, key)
    image_data_uri = f"data:image/png;base64,{image_base64}"
    if provider == "fal.ai":
        body = {image_field: image_data_uri}
    else:  # replicate prediction-style envelope
        body = {"version": args.model_id, "input": {image_field: image_data_uri}}
    ctx = CaptureContext("p4", provider, args.model_id, args.catalog_url, args.price_observed)
    terminal_body = None
    with httpx.Client(timeout=900) as client:
        response, elapsed = timed_request(
            lambda: client.post(args.endpoint_url, headers=headers, json=body)
        )
        write_redacted("submit", {"method": "POST", "url": args.endpoint_url, "headers": headers, "json": body}, response, ctx)
        data = safe_submit_data(response, probe_id="p4", ctx=ctx)
        if data is None:
            return
        poll_url = args.poll_url or data.get("status_url") or data.get("urls", {}).get("get")
        if poll_url:
            terminal_body = poll_json(
                client,
                probe_id="p4",
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
        # `response_url` is fal queue's canonical "fetch result here when terminal" URL.
        # Listed alongside `result_url` / `output_url` for cross-provider compatibility.
        result_url = args.result_url or data.get("result_url") or data.get("output_url") or data.get("response_url")
        fetch_status = capture_fetch_or_result(
            client,
            probe_id="p4",
            ctx=ctx,
            headers=headers,
            result_url=result_url,
            terminal_body=terminal_body,
            original_endpoint=args.endpoint_url,
        )
    write_cancel_evidence(
        "p4",
        ctx,
        "Cancellation evidence must be filled from either a low-cost cancel attempt "
        "or provider API docs. P4 does not block Phase 1 except where its lifecycle evidence affects shared abstractions.",
    )
    outcome = determine_outcome(response, fetch_status)
    write_manifest(ctx, outcome, {"submit_elapsed_seconds": elapsed, "submit_status_code": response.status_code, "fetch_status_code": fetch_status})
    append_notes("p4", f"- submit elapsed_seconds={elapsed:.2f}; status_code={response.status_code}; fetch_status_code={fetch_status}; outcome={outcome}")


def _headers(provider: str, key: str) -> dict[str, str]:
    if provider == "fal.ai":
        return {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    return {"Authorization": f"Token {key}", "Content-Type": "application/json"}


if __name__ == "__main__":
    main()
