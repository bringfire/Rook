from __future__ import annotations

import argparse
from dataclasses import dataclass
from time import monotonic, sleep
from typing import Any, Callable
from urllib.parse import parse_qsl, urlsplit

import httpx

from harness.capture import CaptureContext, append_notes, is_textual_content_type, write_manifest, write_redacted
from harness.redact import TOKEN_QUERY_RE


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


def is_signed_artifact_url(url: str) -> bool:
    """Return True if the URL has signed-URL token query params (S3/CDN/blob)."""
    parts = urlsplit(url)
    if not parts.query:
        return False
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        if TOKEN_QUERY_RE.search(key):
            return True
    return False


def _strip_auth(headers: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() != "authorization"}


def _result_headers_for(url: str, *, original_endpoint: str | None, headers: dict[str, str]) -> dict[str, str]:
    """Decide whether to forward Authorization to a result URL.

    Strip auth when:
      - URL has signed-URL token query params (S3/CDN/blob), OR
      - URL host differs from the original API endpoint host (cross-origin artifact).
    Otherwise forward headers (e.g. Replicate /v1/predictions/{id} on the same host).
    """
    if is_signed_artifact_url(url):
        return _strip_auth(headers)
    if original_endpoint:
        if urlsplit(url).netloc.lower() != urlsplit(original_endpoint).netloc.lower():
            return _strip_auth(headers)
    return headers


def safe_submit_data(
    response: httpx.Response,
    *,
    probe_id: str,
    ctx: CaptureContext,
    cancel_evidence_text: str = "Cancel evidence not collected: submit response was not parseable JSON.",
) -> dict[str, Any] | None:
    """Parse submit response as JSON, or fail-closed: write incomplete manifest + cancel evidence.

    Returns parsed dict on success. Returns None when probe should abort cleanly.
    """
    try:
        data = response.json()
    except ValueError:
        append_notes(
            probe_id,
            f"- submit response was not JSON; status={response.status_code}; aborting probe with incomplete manifest",
        )
        write_manifest(
            ctx,
            "incomplete",
            {"reason": "non_json_submit_response", "status_code": response.status_code},
        )
        write_cancel_evidence(probe_id, ctx, cancel_evidence_text)
        return None
    if not isinstance(data, dict):
        append_notes(
            probe_id,
            f"- submit response JSON was not an object (got {type(data).__name__}); aborting probe with incomplete manifest",
        )
        write_manifest(
            ctx,
            "incomplete",
            {"reason": "non_object_submit_response", "status_code": response.status_code},
        )
        write_cancel_evidence(probe_id, ctx, cancel_evidence_text)
        return None
    return data


def capture_fetch_or_result(
    client: httpx.Client,
    *,
    probe_id: str,
    ctx: CaptureContext,
    headers: dict[str, str],
    result_url: str | None,
    terminal_body: dict[str, Any] | None,
    original_endpoint: str | None = None,
) -> None:
    if result_url:
        fetch_headers = _result_headers_for(result_url, original_endpoint=original_endpoint, headers=headers)
        # HEAD first to avoid downloading binary artifacts (mp4 / mesh / image).
        try:
            head_response = client.head(result_url, headers=fetch_headers, follow_redirects=True)
            head_ok = True
        except httpx.HTTPError as exc:
            append_notes(probe_id, f"- HEAD on result_url raised {type(exc).__name__}: {exc}; falling back to GET-with-binary-guard")
            head_response = None
            head_ok = False

        content_type = ""
        if head_response is not None:
            content_type = head_response.headers.get("content-type", "").lower()
            write_redacted(
                "fetch_head",
                {"method": "HEAD", "url": result_url, "headers": fetch_headers},
                head_response,
                ctx,
            )

        if head_ok and head_response is not None and not is_textual_content_type(content_type):
            # Binary artifact — do NOT download body. HEAD metadata is the fetch evidence.
            append_notes(
                probe_id,
                f"- fetch (HEAD only, binary content_type={content_type or 'unknown'}) status_code={head_response.status_code}",
            )
            return

        # Textual or HEAD-failed: GET, but capture.py will guard binary by content-type and cap text size.
        response = client.get(result_url, headers=fetch_headers)
        write_redacted(
            "fetch",
            {"method": "GET", "url": result_url, "headers": fetch_headers},
            response,
            ctx,
        )
        append_notes(probe_id, f"- fetch via result_url status_code={response.status_code} content_type={response.headers.get('content-type', '')}")
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
