"""Live GH readiness boundary harness.

Run only against a local Rhino/Rook instance. By default it verifies response
shapes for the current runtime state. With --prepare-gh-open, it explicitly
opens Grasshopper and creates a new blank document before gh-open checks.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
from urllib.parse import urlparse

import httpx


DISCOVERY_FAILURE = (
    "Could not discover a local RookNative endpoint. Start Rhino with "
    "RookNative loaded and check %TEMP%\\rook\\instance-*-native.json, "
    "or pass --base-url explicitly."
)
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
HARNESS_PORT_ENV_KEYS = ("ROOK_RHINO_PORT", "NATIVE_PORT")


def _ensure_import_path() -> None:
    src = Path(__file__).resolve().parents[1] / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _is_loopback_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in LOOPBACK_HOSTS


def _base_url_from_harness_env() -> str | None:
    for key in HARNESS_PORT_ENV_KEYS:
        raw = os.environ.get(key)
        if not raw:
            continue
        try:
            port = int(raw)
        except ValueError:
            continue
        if port > 0:
            return f"http://127.0.0.1:{port}"
    return None


def resolve_base_url(explicit_base_url: str | None) -> str:
    if explicit_base_url:
        if not _is_loopback_url(explicit_base_url):
            raise AssertionError(
                "Explicit --base-url must use a local loopback host "
                "(127.0.0.1, localhost, or ::1)."
            )
        return explicit_base_url

    harness_base_url = _base_url_from_harness_env()
    if harness_base_url:
        return harness_base_url

    _ensure_import_path()
    from rook.bridge import get_rhino_host

    discovered = get_rhino_host(endpoint="/gh/status")
    if discovered is None:
        raise AssertionError(DISCOVERY_FAILURE)
    if not _is_loopback_url(discovered):
        raise AssertionError(
            f"Discovered non-loopback RookNative endpoint {discovered!r}; refusing."
        )
    return discovered


def call(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    _ensure_import_path()
    from rook.bridge import NATIVE_CLIENT_HEADERS  # the native server requires X-Rook-Client

    with httpx.Client(timeout=30.0, headers=NATIVE_CLIENT_HEADERS) as client:
        try:
            if method == "GET":
                response = client.get(url, params=payload or {})
            else:
                response = client.request(method, url, json=payload or {})
        except httpx.HTTPError as exc:
            return {
                "success": False,
                "error": (
                    f"HTTP request to {url} failed: {exc}. Check that Rhino is "
                    "running with RookNative loaded, discovery is current, and "
                    "--base-url points at the local native Rook endpoint."
                ),
            }
    try:
        return response.json()
    except json.JSONDecodeError:
        return {
            "success": False,
            "error": response.text,
            "http_status": response.status_code,
        }


def assert_not_ready(name: str, result: dict[str, Any]) -> None:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    if result.get("success") is not False:
        raise AssertionError(f"{name}: expected success=false, got {result}")
    if data.get("error") != "grasshopper_not_ready":
        raise AssertionError(
            f"{name}: expected data.error=grasshopper_not_ready, got {result}"
        )
    verified = result.get("verified", data.get("verified"))
    if verified is not False:
        raise AssertionError(
            f"{name}: expected verified=false at top level or data level, got {result}"
        )
    note = (
        result.get("verification_note")
        or result.get("message")
        or data.get("verification_note")
        or data.get("message")
    )
    if not isinstance(note, str) or not note.strip():
        raise AssertionError(
            f"{name}: expected actionable verification_note or message, got {result}"
        )


def _ready_for_edit(data: dict[str, Any]) -> bool:
    return data.get("ready_for_edit") is True or data.get("readyForEdit") is True


def _count_if_list_or_count(value: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def assert_blank_snapshot(snapshot: dict[str, Any]) -> None:
    data = snapshot.get("data") if isinstance(snapshot.get("data"), dict) else {}
    diagnostics = (
        data.get("diagnostics") if isinstance(data.get("diagnostics"), dict) else {}
    )
    candidates = {
        "components": data.get("components"),
        "groups": data.get("groups"),
        "relays": data.get("relays"),
        "flows": data.get("flows"),
        "objects": data.get("objects"),
        "object_count": data.get("object_count"),
        "objectCount": data.get("objectCount"),
        "diagnostics.total": diagnostics.get("total"),
        "count": data.get("count"),
    }
    observed = {
        key: count
        for key, value in candidates.items()
        if (count := _count_if_list_or_count(value)) is not None
    }
    non_empty = {key: count for key, count in observed.items() if count != 0}
    if non_empty:
        raise AssertionError(
            "gh-open mutation requires a blank GH document before creating "
            f"ReadinessProbe; snapshot reported non-empty fields: {non_empty}"
        )
    if not observed:
        print(
            "blank_document_precheck",
            json.dumps(
                {
                    "verified": False,
                    "message": (
                        "Snapshot response did not expose object/component "
                        "counts or lists; proceeding only because no nonzero "
                        "count could be observed."
                    ),
                },
                indent=2,
            ),
        )


def wait_for_status(
    base_url: str,
    *,
    predicate: Any,
    description: str,
    call_fn: Any = call,
    sleep_fn: Any = time.sleep,
    poll_attempts: int = 20,
    poll_seconds: float = 0.5,
) -> dict[str, Any]:
    last: dict[str, Any] | None = None
    for _ in range(poll_attempts):
        last = call_fn(base_url, "GET", "/gh/status")
        if predicate(last):
            return last
        sleep_fn(poll_seconds)
    raise AssertionError(f"Timed out waiting for {description}: {last}")


def prepare_gh_open(
    base_url: str,
    *,
    call_fn: Any = call,
    sleep_fn: Any = time.sleep,
    poll_attempts: int = 20,
    poll_seconds: float = 0.5,
) -> dict[str, Any]:
    open_gh = call_fn(base_url, "POST", "/command", {"command": "_Grasshopper"})
    command_timeout = (
        open_gh.get("success") is False
        and "timed out" in str(open_gh.get("error", "")).lower()
    )
    if open_gh.get("success") is not True and not command_timeout:
        raise AssertionError(f"Explicit _Grasshopper command failed: {open_gh}")

    try:
        wait_for_status(
            base_url,
            predicate=lambda status: (
                status.get("success") is True
                and isinstance(status.get("data"), dict)
                and status["data"].get("available") is True
            ),
            description="Grasshopper runtime availability",
            call_fn=call_fn,
            sleep_fn=sleep_fn,
            poll_attempts=poll_attempts,
            poll_seconds=poll_seconds,
        )
    except AssertionError as exc:
        if command_timeout:
            raise AssertionError(
                f"Explicit _Grasshopper command timed out and GH did not become available: {open_gh}"
            ) from exc
        raise

    document_new = call_fn(base_url, "POST", "/gh/document/new", {})
    data = document_new.get("data") if isinstance(document_new.get("data"), dict) else {}
    if document_new.get("success") is not True and data.get("created") is not True:
        raise AssertionError(f"gh_document_new failed: {document_new}")

    return wait_for_status(
        base_url,
        predicate=lambda status: (
            status.get("success") is True
            and isinstance(status.get("data"), dict)
            and _ready_for_edit(status["data"])
        ),
        description="Grasshopper ready_for_edit after document creation",
        call_fn=call_fn,
        sleep_fn=sleep_fn,
        poll_attempts=poll_attempts,
        poll_seconds=poll_seconds,
    )


def run_gh_closed_checks(base_url: str) -> None:
    status = call(base_url, "GET", "/gh/status")
    print("gh_status", json.dumps(status, indent=2))
    if status.get("success") is not True:
        raise AssertionError(f"gh_status endpoint did not execute: {status}")
    data = status.get("data") if isinstance(status.get("data"), dict) else {}
    if _ready_for_edit(data):
        raise AssertionError("Expected GH to be not ready for gh-closed mode")

    checks = [
        ("gh_document", "GET", "/gh/document", None),
        ("gh_query", "GET", "/gh/query", None),
        ("gh_snapshot", "POST", "/gh/snapshot", {}),
        ("gh_edit", "POST", "/gh/edit", {"epoch": 0, "create": []}),
        (
            "gh_create_slider",
            "POST",
            "/gh/create-slider",
            {"nickname": "ReadinessProbe"},
        ),
        (
            "gh_connect",
            "POST",
            "/gh/connect",
            {"source": "missing", "target": "missing"},
        ),
        (
            "gh_set_value",
            "POST",
            "/gh/value",
            {"guid": "missing", "value": 1},
        ),
    ]
    for name, method, path, payload in checks:
        result = call(base_url, method, path, payload)
        print(name, json.dumps(result, indent=2))
        assert_not_ready(name, result)


def run_gh_open_checks(base_url: str, *, allow_mutation: bool) -> None:
    status = call(base_url, "GET", "/gh/status")
    print("gh_status", json.dumps(status, indent=2))
    data = status.get("data") if isinstance(status.get("data"), dict) else {}
    if not _ready_for_edit(data):
        raise AssertionError("Expected GH to be ready for gh-open mode")
    if not allow_mutation:
        raise AssertionError(
            "gh-open mode creates a temporary ReadinessProbe slider. Re-run with "
            "--allow-mutation only against a blank GH document."
        )

    snapshot = call(base_url, "POST", "/gh/snapshot", {})
    print("gh_snapshot", json.dumps(snapshot, indent=2))
    if snapshot.get("success") is not True:
        raise AssertionError(f"gh_snapshot failed while GH ready: {snapshot}")
    assert_blank_snapshot(snapshot)

    create_slider = call(
        base_url,
        "POST",
        "/gh/create-slider",
        {
            "nickname": "ReadinessProbe",
            "min": 0,
            "max": 10,
            "value": 5,
            "x": 100,
            "y": 100,
        },
    )
    print("gh_create_slider", json.dumps(create_slider, indent=2))
    if create_slider.get("success") is not True:
        raise AssertionError(f"create-slider failed while GH ready: {create_slider}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            "Optional local native Rook URL. If omitted, the harness discovers "
            "the OS-assigned RookNative port from %%TEMP%%/rook."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("gh-closed", "gh-open", "full"),
        required=True,
        help="Expected Grasshopper runtime state before running this harness.",
    )
    parser.add_argument(
        "--allow-mutation",
        action="store_true",
        help=(
            "Required for gh-open mode because the harness creates a temporary "
            "ReadinessProbe slider. Use only against a blank GH document."
        ),
    )
    parser.add_argument(
        "--prepare-gh-open",
        action="store_true",
        help=(
            "Before gh-open checks, explicitly run _Grasshopper and "
            "/gh/document/new to create a blank editable document."
        ),
    )
    args = parser.parse_args()
    base_url = resolve_base_url(args.base_url)

    if args.mode == "gh-closed":
        if args.prepare_gh_open:
            raise AssertionError("--prepare-gh-open is only valid with gh-open or full")
        run_gh_closed_checks(base_url)
        return 0

    if args.mode == "full":
        run_gh_closed_checks(base_url)
        prepare_gh_open(base_url)
        run_gh_open_checks(base_url, allow_mutation=args.allow_mutation)
        return 0

    if args.prepare_gh_open:
        prepare_gh_open(base_url)
    run_gh_open_checks(base_url, allow_mutation=args.allow_mutation)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
