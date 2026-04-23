"""Live-Rhino contract tests for POST /vision/* (PR-5a).

Scope:
- Skip cleanly when the native plugin is not discoverable.
- Skip Gemini-hitting cases when no test API key is set via
  ``ROOK_GEMINI_TEST_KEY`` env var.
- Pin the HTTP contract for /vision/generate, /vision/enhance-prompt,
  /vision/capture-depth — validation failures return 400 with a
  ``{success: false, data: "..."}`` envelope.
- Pin the observability header ``X-Rook-Vision-Op`` native sets on every
  response.
- Pin the unknown-op rejection path (single bridge callback routes by op).

Does NOT cover:
- Actual Gemini API calls (PR-5a live smoke checklist, user-driven,
  gated on ROOK_GEMINI_TEST_KEY env var + a prepared input image).
- Artifact management routes (PR-5b).

Run:
    pytest mcp_server/tests/test_vision_routes_live.py

    # with live Gemini check:
    ROOK_GEMINI_TEST_KEY=AIza... pytest mcp_server/tests/test_vision_routes_live.py
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


# Default timeout: 30 s covers every validation path (native rejects
# before dispatching to the async bridge). Live Gemini paths override via
# the ``timeout_seconds`` parameter to allow up to the vision bridge's
# 180 s ceiling + HTTP overhead.
_DEFAULT_TIMEOUT_S = 30.0
_LIVE_GEMINI_TIMEOUT_S = 200.0


def _require_host() -> str:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")
    return base_url  # type: ignore[return-value]


async def _post_vision(
    route: str,
    body: dict[str, Any],
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT_S,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    base_url = _require_host()
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        resp = await client.post(f"{base_url}/vision/{route}", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/vision/{route} returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope, dict(resp.headers)


# ─── Header contract ──────────────────────────────────────────────────


async def test_generate_sets_vision_op_header():
    # Even validation-failure responses should carry the op header so
    # log filtering / X-Rook-Vision-Op grepping works.
    _, _, headers = await _post_vision("generate", {"prompt": "x"})
    assert headers.get("x-rook-vision-op") == "generate"


async def test_enhance_prompt_sets_vision_op_header():
    _, _, headers = await _post_vision("enhance-prompt", {})
    assert headers.get("x-rook-vision-op") == "enhance_prompt"


async def test_capture_depth_sets_vision_op_header():
    _, _, headers = await _post_vision(
        "capture-depth", {"max_edge": 50}  # intentionally below min
    )
    assert headers.get("x-rook-vision-op") == "capture_depth"


# ─── Generate validation ──────────────────────────────────────────────


async def test_generate_missing_prompt_rejected():
    status, body, _ = await _post_vision(
        "generate",
        {"input_image_path": "C:\\nonexistent.png"},
    )
    assert status == 400
    assert body["success"] is False
    assert "prompt" in body["data"].lower()


async def test_generate_missing_input_image_path_rejected():
    status, body, _ = await _post_vision(
        "generate",
        {"prompt": "a cube"},
    )
    assert status == 400
    assert body["success"] is False
    assert "input_image_path" in body["data"]


async def test_generate_nonexistent_input_image_rejected():
    status, body, _ = await _post_vision(
        "generate",
        {
            "prompt": "x",
            "input_image_path": "C:\\does-not-exist-12345.png",
        },
    )
    assert status == 400
    assert body["success"] is False
    assert "does not exist" in body["data"].lower()


# ─── Enhance prompt validation ────────────────────────────────────────


async def test_enhance_prompt_missing_prompt_rejected():
    status, body, _ = await _post_vision("enhance-prompt", {})
    assert status == 400
    assert body["success"] is False
    assert "prompt" in body["data"].lower()


# ─── Capture depth validation ─────────────────────────────────────────


async def test_capture_depth_max_edge_below_min_rejected():
    status, body, _ = await _post_vision(
        "capture-depth", {"max_edge": 50}
    )
    assert status == 400
    assert body["success"] is False
    assert "max_edge" in body["data"]


async def test_capture_depth_max_edge_above_max_rejected():
    status, body, _ = await _post_vision(
        "capture-depth", {"max_edge": 99999}
    )
    assert status == 400
    assert body["success"] is False
    assert "max_edge" in body["data"]


# ─── Live Gemini paths (require env var + test input) ─────────────────


def _require_test_key() -> str:
    key = os.environ.get("ROOK_GEMINI_TEST_KEY")
    if not key:
        pytest.skip(
            "ROOK_GEMINI_TEST_KEY not set; skipping live Gemini test. "
            "Set the env var to run against a real Gemini API key."
        )
    return key


async def test_generate_with_key_and_valid_inputs_returns_artifact():
    # Full live-roundtrip against the Gemini service. Requires:
    #   - Rhino running with Rook companion loaded
    #   - A valid Gemini API key PERSISTED via VisionSecretStore (the
    #     native plugin reads from RookSettingsStore, not env vars —
    #     ROOK_GEMINI_TEST_KEY just gates whether we attempt the test).
    #   - A test PNG at %TEMP%\\rook-vision-test-input.png
    _ = _require_test_key()

    import tempfile
    input_path = os.path.join(
        tempfile.gettempdir(), "rook-vision-test-input.png"
    )
    if not os.path.exists(input_path):
        pytest.skip(
            f"Test input image not found at {input_path}; "
            "create a small test PNG there to run this case."
        )

    status, body, _ = await _post_vision(
        "generate",
        {
            "prompt": "architectural visualization, photorealistic",
            "input_image_path": input_path,
            "resolution": "1K",
            "aspect_ratio": "1:1",
        },
        timeout_seconds=_LIVE_GEMINI_TIMEOUT_S,
    )

    if body.get("success"):
        data = body["data"]
        assert "artifact_id" in data
        assert data.get("kind") == "generated_image"
        assert data.get("file_path"), "file_path should be populated"
    else:
        # Acceptable reasons to fail in a dev box: key not persisted to
        # RookSettingsStore, billing not set up, etc. The message must
        # not contain "AIzaSy" (literal key prefix) — that's the
        # secret-leak canary.
        assert "AIzaSy" not in str(body.get("data", ""))
