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
    # Replicate-only: selects which submission contract to use. Other probes ignore this.
    # - "versioned": POST /v1/predictions with {"version": "<hash>", "input": {...}}
    # - "official-model": POST /v1/models/{owner}/{name}/predictions with {"input": {...}}
    # - "unified-model-id": POST /v1/predictions with {"version": "owner/name", "input": {...}}
    replicate_mode: str | None


def base_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--endpoint-url", required=True)
    parser.add_argument("--catalog-url", required=True)
    parser.add_argument("--price-observed", required=True)
    parser.add_argument("--poll-url")
    parser.add_argument("--result-url")
    parser.add_argument("--cancel-url")
    parser.add_argument(
        "--replicate-mode",
        choices=["versioned", "official-model", "unified-model-id"],
        default="versioned",
        help="Replicate-only: submission contract. Ignored by other probes.",
    )
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
        replicate_mode=args.replicate_mode,
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
        # Notes preserve original case (evidence: fal uses UPPERCASE state names; Replicate uses lowercase).
        # Comparison is case-insensitive so providers using different casing all match the canonical
        # terminal set.
        append_notes(probe_id, f"- poll {index}: state={state}, status_code={response.status_code}")
        if state.lower() in terminal:
            return last_body
        sleep(interval_seconds)
    raise SystemExit(f"{probe_id}: polling did not reach terminal state after {max_polls} polls")


def detect_provider(endpoint_url: str) -> str:
    """Classify provider from the endpoint URL host.

    Robust replacement for substring-matching `catalog_url`, which would misclassify a
    Replicate model whose owner/slug contained `fal`. Endpoint hosts are stable per provider:
    - Replicate API → api.replicate.com (or *.replicate.com)
    - fal.ai → *.fal.ai (e.g. api.fal.ai) or *.fal.run (e.g. queue.fal.run)
    """
    host = urlsplit(endpoint_url).netloc.lower()
    if not host:
        raise SystemExit(f"Could not parse host from endpoint URL: {endpoint_url}")
    if host == "api.replicate.com" or host.endswith(".replicate.com"):
        return "replicate"
    if host == "fal.ai" or host.endswith(".fal.ai") or host == "fal.run" or host.endswith(".fal.run"):
        return "fal.ai"
    raise SystemExit(
        f"Could not classify provider from endpoint host: {host}. "
        "Expected api.replicate.com, *.replicate.com, *.fal.ai, or *.fal.run."
    )


def is_signed_artifact_url(url: str) -> bool:
    """Return True if the URL has signed-URL token query params (S3/CDN/blob)."""
    parts = urlsplit(url)
    if not parts.query:
        return False
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        if TOKEN_QUERY_RE.search(key):
            return True
    return False


def is_artifact_url(url: str, original_endpoint: str | None) -> bool:
    """Return True if the URL is an external artifact (signed token, or cross-origin from the API).

    Artifact URLs are HEAD-only: we never GET them, because they may serve mp4/mesh/archive
    binaries with missing or misleading content-type metadata. Provider API URLs (same host
    as the submit endpoint, no signed-URL tokens) are still GET-eligible.
    """
    if is_signed_artifact_url(url):
        return True
    if original_endpoint:
        if urlsplit(url).netloc.lower() != urlsplit(original_endpoint).netloc.lower():
            return True
    return False


def _strip_auth(headers: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() != "authorization"}


def _result_headers_for(url: str, *, original_endpoint: str | None, headers: dict[str, str]) -> dict[str, str]:
    """Decide whether to forward Authorization to a result URL.

    Strip auth for any artifact URL (signed query tokens or cross-origin from the API host).
    Forward headers only for provider API URLs (e.g. Replicate /v1/predictions/{id}).
    """
    if is_artifact_url(url, original_endpoint):
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


def determine_outcome(submit_response: httpx.Response, fetch_status: int | None) -> str:
    """Compute manifest outcome from submit + fetch HTTP status.

    Returns one of:
      - "complete":          submit ok AND (fetch ok OR terminal-body fallback)
      - "validation_failed": submit ok AND fetch returned 4xx (e.g. fal queue
                             COMPLETED + response_url 422 with FastAPI detail)
      - "incomplete":        submit failed, fetch failed with 5xx, or other
                             non-success path

    fetch_status=None signals the terminal-body fallback path (sync providers
    that return result inline; no separate fetch URL was hit).
    """
    if not submit_response.is_success:
        return "incomplete"
    if fetch_status is None:
        return "complete"
    if 200 <= fetch_status < 300:
        return "complete"
    if 400 <= fetch_status < 500:
        return "validation_failed"
    return "incomplete"


def capture_fetch_or_result(
    client: httpx.Client,
    *,
    probe_id: str,
    ctx: CaptureContext,
    headers: dict[str, str],
    result_url: str | None,
    terminal_body: dict[str, Any] | None,
    original_endpoint: str | None = None,
) -> int | None:
    """Capture the fetch/result stage. Returns the HTTP status code observed,
    or None if the terminal-body fallback path was taken (no real fetch).

    The returned status flows into `determine_outcome` so that probe manifests
    distinguish between "submit succeeded but the result fetch failed" (e.g.,
    fal queue COMPLETED state with response_url returning 4xx) and "everything
    worked end-to-end".
    """
    if result_url:
        fetch_headers = _result_headers_for(result_url, original_endpoint=original_endpoint, headers=headers)
        is_artifact = is_artifact_url(result_url, original_endpoint)

        if is_artifact:
            # External artifact (signed URL or cross-origin host). HEAD-only — never GET.
            # Servers can return 200 with missing/incorrect content-type for binary blobs;
            # a full GET would download mp4/mesh/archive into memory before capture.py drops it.
            try:
                head_response = client.head(result_url, headers=fetch_headers, follow_redirects=True)
                write_redacted(
                    "fetch_head",
                    {"method": "HEAD", "url": result_url, "headers": fetch_headers},
                    head_response,
                    ctx,
                )
                append_notes(
                    probe_id,
                    f"- fetch (HEAD only — artifact URL) status_code={head_response.status_code} content_type={head_response.headers.get('content-type', '')} content_length={head_response.headers.get('content-length', '')}",
                )
                return head_response.status_code
            except httpx.HTTPError as exc:
                append_notes(
                    probe_id,
                    f"- HEAD on artifact result_url raised {type(exc).__name__}: {exc}; no body capture attempted (artifact URLs are HEAD-only)",
                )
                write_redacted(
                    "fetch_head",
                    {"method": "HEAD", "url": result_url, "headers": fetch_headers, "error": f"{type(exc).__name__}: {exc}"},
                    {"status_code": None, "headers": {}, "body": {"<head_failed>": True}},
                    ctx,
                )
                return None

        # Provider API URL (same host as submit endpoint, no signed-URL tokens).
        # GET is appropriate; capture.py guards binary bodies and caps text length.
        response = client.get(result_url, headers=fetch_headers)
        write_redacted(
            "fetch",
            {"method": "GET", "url": result_url, "headers": fetch_headers},
            response,
            ctx,
        )
        append_notes(probe_id, f"- fetch via provider API result_url status_code={response.status_code} content_type={response.headers.get('content-type', '')}")
        return response.status_code

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
        return None
    return None


def write_cancel_evidence(probe_id: str, ctx: CaptureContext, text: str) -> None:
    from harness.env import CAPTURE_ROOT

    probe_dir = CAPTURE_ROOT / probe_id
    probe_dir.mkdir(parents=True, exist_ok=True)
    (probe_dir / "cancel_evidence.md").write_text(text.rstrip() + "\n", encoding="utf-8")
    append_notes(probe_id, "- cancel evidence recorded in cancel_evidence.md")
