from __future__ import annotations

import argparse
from dataclasses import dataclass
from time import monotonic, sleep
from typing import Any, Callable

import httpx

from harness.capture import CaptureContext, append_notes, write_redacted


@dataclass(frozen=True)
class ProbeArgs:
    model_id: str
    endpoint_url: str
    catalog_url: str
    price_observed: str
    poll_url: str | None
    result_url: str | None
    cancel_url: str | None


def base_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--endpoint-url", required=True)
    parser.add_argument("--catalog-url", required=True)
    parser.add_argument("--price-observed", required=True)
    parser.add_argument("--poll-url")
    parser.add_argument("--result-url")
    parser.add_argument("--cancel-url")
    return parser


def parse_probe_args(description: str) -> ProbeArgs:
    args = base_parser(description).parse_args()
    return ProbeArgs(
        model_id=args.model_id,
        endpoint_url=args.endpoint_url,
        catalog_url=args.catalog_url,
        price_observed=args.price_observed,
        poll_url=args.poll_url,
        result_url=args.result_url,
        cancel_url=args.cancel_url,
    )


def timed_request(send: Callable[[], httpx.Response]) -> tuple[httpx.Response, float]:
    start = monotonic()
    response = send()
    return response, monotonic() - start


def poll_json(
    client: httpx.Client,
    *,
    probe_id: str,
    ctx: CaptureContext,
    url: str,
    headers: dict[str, str],
    status_getter: Callable[[dict[str, Any]], str],
    terminal: set[str],
    max_polls: int = 30,
    interval_seconds: float = 2.0,
) -> dict[str, Any]:
    last_body: dict[str, Any] = {}
    for index in range(1, max_polls + 1):
        response = client.get(url, headers=headers)
        write_redacted(
            f"status_{index:03d}",
            {"method": "GET", "url": url, "headers": headers},
            response,
            ctx,
        )
        try:
            last_body = response.json()
        except ValueError:
            last_body = {"raw_text": response.text}
        state = status_getter(last_body)
        append_notes(probe_id, f"- poll {index}: state={state}, status_code={response.status_code}")
        if state in terminal:
            return last_body
        sleep(interval_seconds)
    raise SystemExit(f"{probe_id}: polling did not reach terminal state after {max_polls} polls")


def capture_fetch_or_result(
    client: httpx.Client,
    *,
    probe_id: str,
    ctx: CaptureContext,
    headers: dict[str, str],
    result_url: str | None,
    terminal_body: dict[str, Any] | None,
) -> None:
    if result_url:
        response = client.get(result_url, headers=headers)
        write_redacted(
            "fetch",
            {"method": "GET", "url": result_url, "headers": headers},
            response,
            ctx,
        )
        append_notes(probe_id, f"- fetch via result_url status_code={response.status_code}")
        return

    if terminal_body is not None:
        write_redacted(
            "fetch",
            {
                "method": "none",
                "url": None,
                "headers": {},
                "source": "terminal response body",
            },
            {"status_code": None, "headers": {}, "body": terminal_body},
            ctx,
        )
        append_notes(probe_id, "- fetch represented by terminal response body; no separate result URL observed")


def write_cancel_evidence(probe_id: str, ctx: CaptureContext, text: str) -> None:
    from harness.env import CAPTURE_ROOT

    probe_dir = CAPTURE_ROOT / probe_id
    probe_dir.mkdir(parents=True, exist_ok=True)
    (probe_dir / "cancel_evidence.md").write_text(text.rstrip() + "\n", encoding="utf-8")
    append_notes(probe_id, "- cancel evidence recorded in cancel_evidence.md")
