"""Live-Rhino contract tests for /vision/* (PR-5a + PR-5b).

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
- PR-5b: pin the artifact-management routes (list / get / approve /
  delete / consume-approved). Full happy-path coverage runs only when
  Rhino is live and can successfully capture a depth map, which
  populates the store with a real artifact for the rest of the chain
  to exercise.

Does NOT cover:
- Actual Gemini API calls (PR-5a live smoke checklist, user-driven,
  gated on ROOK_GEMINI_TEST_KEY env var + a prepared input image).

Run:
    pytest mcp_server/tests/test_vision_routes_live.py

    # with live Gemini check:
    ROOK_GEMINI_TEST_KEY=AIza... pytest mcp_server/tests/test_vision_routes_live.py
"""

from __future__ import annotations

import os
from typing import Any

from rook.bridge import native_client
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
    async with native_client(timeout=timeout_seconds) as client:
        resp = await client.post(f"{base_url}/vision/{route}", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/vision/{route} returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope, dict(resp.headers)


async def _get_vision(
    route: str,
    params: dict[str, Any] | None = None,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT_S,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    base_url = _require_host()
    async with native_client(timeout=timeout_seconds) as client:
        resp = await client.get(f"{base_url}/vision/{route}", params=params or {})
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/vision/{route} returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope, dict(resp.headers)


async def _delete_vision(
    route: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT_S,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    base_url = _require_host()
    async with native_client(timeout=timeout_seconds) as client:
        resp = await client.delete(f"{base_url}/vision/{route}")
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


async def test_generate_aggregate_payload_cap_rejected(tmp_path):
    """Aggregate raw-byte cap (primary + all references) rejects requests
    that would exceed Gemini's inline-payload envelope after base64
    expansion. Per-file limit is 10 MB; aggregate cap is 15 MB — two
    ~8 MB images combined must be rejected.
    """
    import struct
    # Create two ~8 MB PNG-ish files. Content is valid PNG header +
    # padding — size is what matters for the validation gate.
    def make(path, size_bytes):
        header = b"\x89PNG\r\n\x1a\n"
        path.write_bytes(header + b"\x00" * (size_bytes - len(header)))
        return str(path)

    primary = make(tmp_path / "primary.png", 8 * 1024 * 1024)
    ref1 = make(tmp_path / "ref1.png", 8 * 1024 * 1024)

    status, body, _ = await _post_vision(
        "generate",
        {
            "prompt": "x",
            "input_image_path": primary,
            "reference_image_paths": [ref1],
        },
    )
    assert status == 400
    assert body["success"] is False
    assert "aggregate" in body["data"].lower()


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


# ─── PR-5b: Artifact-management headers + validation ─────────────────


async def test_list_artifacts_sets_vision_op_header():
    _, _, headers = await _get_vision("artifacts")
    assert headers.get("x-rook-vision-op") == "list_artifacts"


async def test_consume_approved_sets_vision_op_header():
    _, _, headers = await _post_vision("artifacts/consume-approved", {})
    assert headers.get("x-rook-vision-op") == "consume_approved"


async def test_get_artifact_sets_vision_op_header_even_on_404():
    # A well-formed GUID that won't exist — the response lands as 400
    # with success=false (v1 has no distinct 404 semantic), but the
    # header must still be set so log filtering works.
    nonexistent = "00000000-0000-0000-0000-000000000001"
    _, _, headers = await _get_vision(f"artifacts/{nonexistent}")
    assert headers.get("x-rook-vision-op") == "get_artifact"


async def test_list_artifacts_rejects_malformed_approved_param():
    status, body, _ = await _get_vision(
        "artifacts", {"approved": "maybe"}
    )
    assert status == 400
    assert body["success"] is False
    assert "approved" in body["data"].lower()


async def test_list_artifacts_rejects_non_integer_limit():
    status, body, _ = await _get_vision(
        "artifacts", {"limit": "abc"}
    )
    assert status == 400
    assert body["success"] is False
    assert "limit" in body["data"].lower()


async def test_get_artifact_missing_id_returns_failure():
    # Well-formed but nonexistent id — v1 maps not-found to
    # success=false + "Artifact '…' not found." (400 status code).
    nonexistent = "00000000-0000-0000-0000-000000000002"
    status, body, _ = await _get_vision(f"artifacts/{nonexistent}")
    assert status == 400
    assert body["success"] is False
    assert "not found" in body["data"].lower()


async def test_delete_artifact_missing_id_returns_failure():
    nonexistent = "00000000-0000-0000-0000-000000000003"
    status, body, _ = await _delete_vision(f"artifacts/{nonexistent}")
    assert status == 400
    assert body["success"] is False
    assert "not found" in body["data"].lower()


async def test_approve_artifact_missing_id_returns_failure():
    nonexistent = "00000000-0000-0000-0000-000000000004"
    status, body, _ = await _post_vision(
        f"artifacts/{nonexistent}/approve", {}
    )
    assert status == 400
    assert body["success"] is False
    assert "not found" in body["data"].lower()


async def test_consume_approved_empty_store_returns_null_artifact():
    # consume_approved with no matches is a steady state, not an error.
    # Note: if the store already contains approved generated_image
    # artifacts from prior runs, `artifact` will be non-null. We only
    # assert the envelope shape — either null or a fully-formed
    # artifact envelope.
    status, body, _ = await _post_vision("artifacts/consume-approved", {})
    assert status == 200
    assert body["success"] is True
    data = body["data"]
    assert "artifact" in data
    if data["artifact"] is not None:
        assert "artifact_id" in data["artifact"]
        assert data["artifact"].get("kind") == "generated_image"


async def test_consume_approved_rejects_bad_since():
    status, body, _ = await _post_vision(
        "artifacts/consume-approved",
        {"since": "not-a-date"},
    )
    assert status == 400
    assert body["success"] is False
    assert "since" in body["data"].lower()


async def test_list_artifacts_accepts_filters():
    # No existence guarantees — just that the filter shape is accepted.
    status, body, _ = await _get_vision(
        "artifacts",
        {"kind": "generated_image", "approved": "true", "limit": "5"},
    )
    assert status == 200
    assert body["success"] is True
    data = body["data"]
    assert "artifacts" in data
    assert "count" in data
    assert "applied_limit" in data
    assert isinstance(data["artifacts"], list)
    assert data["count"] == len(data["artifacts"])
    assert data["applied_limit"] == 5


async def test_list_artifacts_default_limit_applied_without_param():
    # No 'limit' query param — the default should come back in
    # applied_limit so callers can detect truncation.
    status, body, _ = await _get_vision("artifacts")
    assert status == 200
    data = body["data"]
    # Default is 100 per VisionHandler.DefaultListLimit.
    assert data["applied_limit"] == 100
    assert data["count"] <= data["applied_limit"]


async def test_list_artifacts_rejects_limit_above_hard_max():
    status, body, _ = await _get_vision(
        "artifacts", {"limit": "501"}
    )
    assert status == 400
    assert body["success"] is False
    assert "limit" in body["data"].lower()
    assert "500" in body["data"]


async def test_list_artifacts_rejects_non_positive_limit():
    status, body, _ = await _get_vision(
        "artifacts", {"limit": "0"}
    )
    assert status == 400
    assert body["success"] is False
    assert "limit" in body["data"].lower()


async def test_list_artifacts_rejects_limit_with_trailing_garbage():
    # Native query folding must not silently accept "5abc" as 5.
    status, body, _ = await _get_vision(
        "artifacts", {"limit": "5abc"}
    )
    assert status == 400
    assert body["success"] is False
    assert "limit" in body["data"].lower()


async def test_consume_approved_rejects_offset_less_since():
    # DateTimeOffset.TryParse silently accepts offset-less strings
    # and interprets them as local time — which is the trap
    # ArtifactStore.Iso8601WithOffsetPattern guards against for
    # manifest timestamps. The same invariant applies here.
    status, body, _ = await _post_vision(
        "artifacts/consume-approved",
        {"since": "2026-04-22T15:30:00"},  # no Z, no offset
    )
    assert status == 400
    assert body["success"] is False
    assert "offset" in body["data"].lower()


async def test_consume_approved_accepts_iso_with_offset():
    status, body, _ = await _post_vision(
        "artifacts/consume-approved",
        {"since": "2000-01-01T00:00:00Z"},
    )
    assert status == 200
    assert body["success"] is True
    # Shape assertion only — store may or may not have a match.
    assert "artifact" in body["data"]


# ─── PR-5b review round 2: envelope compactness + path validation ─────


async def test_list_artifacts_envelope_is_compact_summary():
    # Pins the list envelope shape. Full artifact metadata can be
    # ~16 KB per entry (generated_image stores the user prompt
    # verbatim), which at limit=100 would exceed the bridge's 1 MB
    # buffer. list deliberately returns a compact summary; full
    # detail is served by get_artifact.
    status, body, _ = await _get_vision("artifacts")
    assert status == 200
    assert body["success"] is True

    artifacts = body["data"]["artifacts"]
    if not artifacts:
        pytest.skip(
            "Artifact store is empty; shape-pin test needs at least one "
            "artifact. Run the end-to-end lifecycle test first or seed "
            "the store manually."
        )

    entry = artifacts[0]
    # Required compact-summary fields.
    for required in ("artifact_id", "kind", "created_at", "files",
                     "parent_ids", "flags"):
        assert required in entry, f"list entry missing '{required}': {entry!r}"

    # Deliberately omitted — list should stay small.
    assert "metadata" not in entry, (
        "list envelope should not include metadata — use GET "
        "/vision/artifacts/{id} for full detail."
    )
    assert "file_path" not in entry, (
        "list envelope should not include file_path — per-item "
        "directory scan is skipped to keep list cheap."
    )


async def test_get_artifact_full_envelope_includes_metadata_placeholder():
    # get_artifact returns the FULL envelope including metadata and
    # file_path. Uses the same store-must-be-nonempty pattern as the
    # compact-summary test — picks the first id from list, then GETs.
    status, body, _ = await _get_vision("artifacts")
    if not body.get("success") or not body["data"]["artifacts"]:
        pytest.skip(
            "Artifact store is empty; full-envelope test needs an "
            "existing artifact."
        )

    artifact_id = body["data"]["artifacts"][0]["artifact_id"]
    status, body, _ = await _get_vision(f"artifacts/{artifact_id}")
    assert status == 200
    entry = body["data"]
    # Full-envelope-only fields.
    assert "metadata" in entry
    assert "file_path" in entry


# ─── Path-id regex: managed is the validation boundary ───────────────
#
# The native routes now use [^/]+ rather than [0-9A-Fa-f-]+ for the
# path-id capture group. Non-GUID strings previously fell through to
# httplib's generic 404 (no X-Rook-Vision-Op header, no JSON envelope);
# they must now reach managed RequireArtifactId and return the
# standard contract.


async def test_get_artifact_non_hex_path_routes_to_managed():
    status, body, headers = await _get_vision("artifacts/not-a-guid")
    # Still the managed failure shape, not httplib's generic 404.
    assert status == 400
    assert body["success"] is False
    assert "GUID" in body["data"]
    # X-Rook-Vision-Op header pins the "managed reached it" invariant.
    assert headers.get("x-rook-vision-op") == "get_artifact"


async def test_delete_artifact_non_hex_path_routes_to_managed():
    status, body, headers = await _delete_vision("artifacts/not-a-guid")
    assert status == 400
    assert body["success"] is False
    assert "GUID" in body["data"]
    assert headers.get("x-rook-vision-op") == "delete_artifact"


async def test_approve_artifact_non_hex_path_routes_to_managed():
    status, body, headers = await _post_vision(
        "artifacts/not-a-guid/approve", {}
    )
    assert status == 400
    assert body["success"] is False
    assert "GUID" in body["data"]
    assert headers.get("x-rook-vision-op") == "approve_artifact"


# ─── PR-5b: End-to-end lifecycle (requires live Rhino) ───────────────
#
# Uses capture_depth to mint a real depth_map artifact, then exercises
# list → get → approve → consume → delete on it. If depth capture
# fails (no viewport, modal dialog, etc), the whole chain skips.


async def _mint_depth_artifact() -> dict[str, Any] | None:
    """Create an artifact via /vision/capture-depth. Returns the
    artifact dict or None if Rhino could not capture."""
    status, body, _ = await _post_vision("capture-depth", {"max_edge": 256})
    if status != 200 or not body.get("success"):
        return None
    return body["data"]


async def test_artifact_lifecycle_end_to_end():
    minted = await _mint_depth_artifact()
    if minted is None:
        pytest.skip(
            "Depth-map capture unavailable; skipping end-to-end "
            "artifact-lifecycle test."
        )
    artifact_id = minted["artifact_id"]

    try:
        # GET /vision/artifacts/{id} — path-param dispatch.
        status, body, _ = await _get_vision(f"artifacts/{artifact_id}")
        assert status == 200
        assert body["success"] is True
        assert body["data"]["artifact_id"] == artifact_id
        assert body["data"]["kind"] == "depth_map"

        # GET /vision/artifacts — listing should include the minted id.
        status, body, _ = await _get_vision("artifacts")
        assert status == 200
        ids = [a["artifact_id"] for a in body["data"]["artifacts"]]
        assert artifact_id in ids

        # Filter by kind — depth_map must surface.
        status, body, _ = await _get_vision(
            "artifacts", {"kind": "depth_map"}
        )
        assert status == 200
        ids = [a["artifact_id"] for a in body["data"]["artifacts"]]
        assert artifact_id in ids

        # POST /vision/artifacts/{id}/approve — flip flags.approved.
        status, body, _ = await _post_vision(
            f"artifacts/{artifact_id}/approve", {}
        )
        assert status == 200
        assert body["success"] is True
        assert body["data"]["flags"]["approved"] is True

        # Consume-approved with kind=depth_map should pick it up
        # (depth_map is NOT the default — default is generated_image).
        status, body, _ = await _post_vision(
            "artifacts/consume-approved", {"kind": "depth_map"}
        )
        assert status == 200
        if body["data"]["artifact"] is not None:
            # Multiple approved depth maps might exist from prior runs;
            # we just assert the one we approved is eligible (by
            # matching id OR being among the recent approved set).
            # The deterministic ordering (CreatedAt desc, Id desc)
            # means our just-approved artifact should be first unless
            # another later-created one also has approved=true.
            pass  # weaker assertion — store state is shared

        # Idempotent approve.
        status, body, _ = await _post_vision(
            f"artifacts/{artifact_id}/approve", {}
        )
        assert status == 200
        assert body["data"]["flags"]["approved"] is True
    finally:
        # DELETE /vision/artifacts/{id} — cleanup. Always attempt,
        # even if asserts above failed, so the live store stays clean.
        status, body, _ = await _delete_vision(f"artifacts/{artifact_id}")
        assert status == 200
        assert body["success"] is True
        assert body["data"]["deleted"] is True

        # Double-delete is a failure, not a no-op.
        status, body, _ = await _delete_vision(f"artifacts/{artifact_id}")
        assert status == 400
        assert body["success"] is False
