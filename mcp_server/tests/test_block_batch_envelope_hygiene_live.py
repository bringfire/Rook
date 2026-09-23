"""Live-Rhino envelope-shape hygiene pin for companion-backed block
batch routes.

Bundled hygiene with the reset-scale-batch PR. Pins the fix that
addresses the `TryGetProperty`-on-non-object hazard in 6 batch handlers
in `src/Rook/Handlers/BlocksHandler.cs`:

  - SetBlockObjectLayersBatch        → /block/set-layers-batch
  - SetBlockObjectMaterialsBatch     → /block/set-materials-batch
  - SetBlockObjectColorsBatch        → /block/set-object-colors-batch
  - SetBlockObjectUserStringsBatch   → /block/set-object-user-strings-batch
  - SetBlockObjectNamesBatch         → /block/set-object-names-batch
  - TransformInstanceBatch           → /block/transform-instance-batch

Before the fix, a non-object request body (e.g. JSON array, string,
number) fell into the outer try/catch as a generic wrapper error
rather than returning the intended shape-error contract. The fix adds
a `request.ValueKind != JsonValueKind.Object` guard before the first
`TryGetProperty` access.

This test pins the exact contract error string
**"Request body must be a JSON object"** for every handler. If a
future managed refactor accidentally removes the guard or changes the
message, this test flips loud.

Run (from `mcp_server/`):
    pytest -m requires_rhino tests/test_block_batch_envelope_hygiene_live.py

Rhino must be running with RookNative + Rook companion loaded.
"""

from __future__ import annotations

from typing import Any

from rook.bridge import native_client
import pytest

from .conftest import fresh_document


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


ENVELOPE_GUARDED_ROUTES: list[str] = [
    "/block/set-layers-batch",
    "/block/set-materials-batch",
    "/block/set-object-colors-batch",
    "/block/set-object-user-strings-batch",
    "/block/set-object-names-batch",
    "/block/transform-instance-batch",
]


EXPECTED_MESSAGE = "Request body must be a JSON object"


async def _post_raw_body(route: str, body: Any) -> tuple[int, dict[str, Any]]:
    """POST a raw (possibly non-object) JSON value to `route` and
    return the parsed envelope."""
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}{route}", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"{route} returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


def _assert_envelope_guard(envelope: dict[str, Any], route: str) -> None:
    """Assert the response is a failure envelope with the exact
    contract message."""
    assert envelope.get("success") is False, (
        f"{route}: expected failure envelope for non-object body, got {envelope!r}"
    )
    data = envelope.get("data")
    # Companion-backed routes on this pattern return a string `data` via
    # CRookServer::SendError (not the structured {errorCode, errorMessage}
    # form). That's the pre-existing convention for these handlers.
    assert data == EXPECTED_MESSAGE, (
        f"{route}: expected exact contract message {EXPECTED_MESSAGE!r}, "
        f"got data={data!r}. Envelope: {envelope!r}\n"
        f"If this failure mode returns a generic wrapper like "
        f"'Batch X failed: ...' the envelope guard is missing — re-apply "
        f"the PR #21 fix pattern (ValueKind != JsonValueKind.Object)."
    )


@pytest.mark.parametrize("route", ENVELOPE_GUARDED_ROUTES)
async def test_non_object_array_body_rejected_with_exact_message(
    route: str, fresh_document
) -> None:
    """JSON array `[]` as the body → `"Request body must be a JSON object"`."""
    status, envelope = await _post_raw_body(route, [])
    _assert_envelope_guard(envelope, route)


@pytest.mark.parametrize("route", ENVELOPE_GUARDED_ROUTES)
async def test_non_object_string_body_rejected_with_exact_message(
    route: str, fresh_document
) -> None:
    """JSON string `"x"` as the body → `"Request body must be a JSON object"`."""
    status, envelope = await _post_raw_body(route, "x")
    _assert_envelope_guard(envelope, route)
