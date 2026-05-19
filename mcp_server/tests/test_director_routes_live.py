from __future__ import annotations

from typing import Any

import httpx
import pytest


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


def _require_host() -> str:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")
    return base_url  # type: ignore[return-value]


async def _post_director(route: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    base_url = _require_host()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{base_url}/director/{route}", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/director/{route} returned non-JSON: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def test_director_view_state_active_view_contract():
    _, envelope = await _post_director("view-state", {"source": {"kind": "active_view"}})
    assert envelope["success"] is True
    camera = envelope["data"]["camera"]
    assert camera["projection"] in {"perspective", "parallel"}
    assert len(camera["location"]) == 3
    assert len(camera["target"]) == 3
    assert len(camera["up"]) == 3
    assert "aspect" in camera
    assert envelope["data"]["provenance"]["source"] == "active_view"


async def test_director_object_states_rejects_empty_ids():
    _, envelope = await _post_director("object-states", {"object_ids": []})
    assert envelope["success"] is False
    assert "object_ids" in str(envelope["data"])
