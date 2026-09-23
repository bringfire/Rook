"""Live-Rhino contract tests for /vision/video/* (PR-V2 + PR-V4).

Scope:
- Skip cleanly when the native plugin is not discoverable.
- Pin the X-Rook-Vision-Op header on every video route (V2 + V4).
- Pin the V4 limit-grammar matrix for GET /vision/video/jobs:
  canonical integer strings forward as JSON numbers; everything else
  forwards as strings so managed VideoOpHandler.TryGetOptionalPositiveInt
  rejects with the typed `field:"limit"` envelope.
- Pin GET /vision/video/models response shape.
- Pin V2 negative paths (well-formed nonexistent job_id, missing
  required submit/estimate fields).

Assertion philosophy (per Codex review of scope v3):
- status, X-Rook-Vision-Op header, body.success, and for typed
  rejections body.data.code + body.data.field.
- Avoid brittle full-message-text assertions — managed messages may
  evolve; the wire codes are the contract.

Does NOT cover:
- Actual Veo API calls (no live submit happy-path; submit always
  resolves media via ArtifactStore which requires real artifacts).
- Job lifecycle end-to-end (would mint Veo charges).
- C# / Python unit-test coverage of VideoOpHandler internals.

Run:
    pytest mcp_server/tests/test_video_routes_live.py
"""

from __future__ import annotations

from typing import Any

from rook.bridge import native_client
import pytest


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


# 30 s covers every validation path. Submit/cancel routes are async
# (180 s ceiling on the bridge) but every test in this file lands at
# the managed validation boundary before any provider call, so 30 s
# is plenty.
_DEFAULT_TIMEOUT_S = 30.0

# A well-formed GUID that will never exist. Used for cancel/status/
# result negative paths.
_NONEXISTENT_JOB_ID = "00000000-0000-0000-0000-deadbeefdead"


def _require_host() -> str:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")
    return base_url  # type: ignore[return-value]


async def _post_video(
    route: str,
    body: dict[str, Any],
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT_S,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    base_url = _require_host()
    async with native_client(timeout=timeout_seconds) as client:
        resp = await client.post(f"{base_url}/vision/video/{route}", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/vision/video/{route} returned non-JSON: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope, dict(resp.headers)


async def _get_video(
    route: str,
    params: dict[str, Any] | None = None,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT_S,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    base_url = _require_host()
    async with native_client(timeout=timeout_seconds) as client:
        resp = await client.get(
            f"{base_url}/vision/video/{route}", params=params or {}
        )
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/vision/video/{route} returned non-JSON: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope, dict(resp.headers)


# ─── Header contract (V2 + V4) ────────────────────────────────────────


async def test_submit_sets_vision_op_header():
    # Empty body; managed will reject — header must still be set.
    _, _, headers = await _post_video("jobs", {})
    assert headers.get("x-rook-vision-op") == "submit_video_job"


async def test_status_sets_vision_op_header():
    _, _, headers = await _get_video(f"jobs/{_NONEXISTENT_JOB_ID}")
    assert headers.get("x-rook-vision-op") == "get_video_job"


async def test_cancel_sets_vision_op_header():
    _, _, headers = await _post_video(f"jobs/{_NONEXISTENT_JOB_ID}/cancel", {})
    assert headers.get("x-rook-vision-op") == "cancel_video_job"


async def test_result_sets_vision_op_header():
    _, _, headers = await _get_video(f"jobs/{_NONEXISTENT_JOB_ID}/result")
    assert headers.get("x-rook-vision-op") == "get_video_job_result"


async def test_estimate_sets_vision_op_header():
    _, _, headers = await _post_video("estimate", {})
    assert headers.get("x-rook-vision-op") == "estimate_video_job"


async def test_jobs_list_sets_vision_op_header():
    _, _, headers = await _get_video("jobs")
    assert headers.get("x-rook-vision-op") == "list_video_jobs"


async def test_models_list_sets_vision_op_header():
    _, _, headers = await _get_video("models")
    assert headers.get("x-rook-vision-op") == "list_video_models"


# ─── GET /vision/video/models ─────────────────────────────────────────


async def test_models_list_returns_models_envelope():
    status, body, _ = await _get_video("models")
    assert status == 200
    assert body["success"] is True
    data = body["data"]
    assert "models" in data
    assert isinstance(data["models"], list)
    # The registry ships at least the Veo capability matrix.
    assert len(data["models"]) >= 1
    # Each entry has the documented shape — descriptor wire fields per
    # VideoOpHandler.ModelDescriptorToObj. Pick the first as the
    # exemplar; all entries share the shape.
    entry = data["models"][0]
    for required in (
        "model_id",
        "provider_name",
        "pricing_kind",
        "pricing_source",
        "capability",
    ):
        assert required in entry, (
            f"models entry missing '{required}': {entry!r}"
        )
    cap = entry["capability"]
    for required in (
        "id", "name", "status",
        "resolutions", "durations", "aspect_ratios",
        "modes", "supports_reference_images", "max_reference_images",
        # `must_8s_with` is part of the wire shape per
        # VideoOpHandler.CapabilityToObj — agents need the field even
        # when the value is null, so the schema has to surface it.
        "must_8s_with",
    ):
        assert required in cap, f"capability missing '{required}': {cap!r}"


# ─── GET /vision/video/jobs — default + happy path ───────────────────


async def test_jobs_list_default_limit_returns_jobs_envelope():
    status, body, _ = await _get_video("jobs")
    assert status == 200
    assert body["success"] is True
    data = body["data"]
    assert "jobs" in data
    assert "warnings" in data
    assert "applied_limit" in data
    assert isinstance(data["jobs"], list)
    assert isinstance(data["warnings"], list)
    # Default limit per VideoOpHandler.DefaultListJobsLimit.
    assert data["applied_limit"] == 50


async def test_jobs_list_explicit_int_limit_applied():
    status, body, _ = await _get_video("jobs", {"limit": "25"})
    assert status == 200
    assert body["success"] is True
    assert body["data"]["applied_limit"] == 25


# ─── GET /vision/video/jobs — V4 limit grammar matrix ────────────────
#
# Per scope v3 §[v3]: C++ folds canonical integer strings only,
# everything else forwards as raw JSON String for managed to reject
# with the typed `field:"limit"` envelope. Same envelope whether
# called via MCP, agent, or curl.
#
# Two managed rejection arms produce different MESSAGE text but the
# same CODE + FIELD:
#   - wrong-kind arm (TryGetOptionalPositiveInt sees a String) —
#     returns code=invalid_request, field=limit.
#   - value<1 arm (sees a Number ≤0) — same code/field, different
#     message. Negative values reach this arm because they match the
#     canonical integer grammar.


def _assert_invalid_limit_envelope(status: int, body: dict[str, Any]) -> None:
    """Pin the typed rejection contract: 400 + invalid_request + field=limit.
    Message text intentionally NOT asserted — it varies between the
    wrong-kind and value<1 arms."""
    assert status == 400, f"expected 400, got {status} body={body!r}"
    assert body["success"] is False
    data = body["data"]
    assert isinstance(data, dict), (
        f"expected typed error envelope dict, got {type(data).__name__}: {data!r}"
    )
    assert data.get("code") == "invalid_request", (
        f"expected code=invalid_request, got {data.get('code')!r}"
    )
    assert data.get("field") == "limit", (
        f"expected field=limit, got {data.get('field')!r}"
    )


async def test_jobs_list_rejects_negative_limit():
    # Matches canonical grammar → forwards as JSON Number → managed's
    # value<1 arm rejects.
    status, body, _ = await _get_video("jobs", {"limit": "-1"})
    _assert_invalid_limit_envelope(status, body)


async def test_jobs_list_rejects_zero_limit():
    # Matches canonical grammar → forwards as JSON Number → managed's
    # value<1 arm rejects.
    status, body, _ = await _get_video("jobs", {"limit": "0"})
    _assert_invalid_limit_envelope(status, body)


async def test_jobs_list_rejects_alpha_limit():
    # Bad shape → forwards as JSON String → managed's wrong-kind arm.
    status, body, _ = await _get_video("jobs", {"limit": "abc"})
    _assert_invalid_limit_envelope(status, body)


async def test_jobs_list_rejects_url_encoded_space_prefix():
    # "%20-prefixed" — std::stoi would accept this as 5; the
    # IsCanonicalIntegerString grammar must reject so it forwards
    # as String → wrong-kind arm.
    status, body, _ = await _get_video("jobs", {"limit": " 5"})
    _assert_invalid_limit_envelope(status, body)


async def test_jobs_list_rejects_plus_prefix():
    # std::stoi accepts "+5" as 5; the canonical grammar must reject.
    status, body, _ = await _get_video("jobs", {"limit": "+5"})
    _assert_invalid_limit_envelope(status, body)


async def test_jobs_list_rejects_empty_limit():
    # Empty string → bad shape → wrong-kind arm.
    status, body, _ = await _get_video("jobs", {"limit": ""})
    _assert_invalid_limit_envelope(status, body)


async def test_jobs_list_rejects_overflow_limit():
    # Beyond int32 range → either grammar fails (it doesn't — all
    # digits) or std::stoi throws out_of_range and the catch arm
    # forwards as String. Either way managed rejects.
    status, body, _ = await _get_video("jobs", {"limit": "99999999999"})
    _assert_invalid_limit_envelope(status, body)


async def test_jobs_list_rejects_fractional_limit():
    # Matches no canonical-integer grammar → forwards as String.
    status, body, _ = await _get_video("jobs", {"limit": "1.5"})
    _assert_invalid_limit_envelope(status, body)


# ─── V2 negative paths (well-formed nonexistent job) ─────────────────


async def test_status_unknown_job_id_returns_invalid_request():
    status, body, _ = await _get_video(f"jobs/{_NONEXISTENT_JOB_ID}")
    assert status == 400
    assert body["success"] is False
    data = body["data"]
    assert isinstance(data, dict)
    assert data.get("code") == "invalid_request"


async def test_cancel_unknown_job_id_returns_invalid_request():
    status, body, _ = await _post_video(f"jobs/{_NONEXISTENT_JOB_ID}/cancel", {})
    assert status == 400
    assert body["success"] is False
    assert body["data"].get("code") == "invalid_request"


async def test_result_unknown_job_id_returns_invalid_request():
    status, body, _ = await _get_video(f"jobs/{_NONEXISTENT_JOB_ID}/result")
    assert status == 400
    assert body["success"] is False
    assert body["data"].get("code") == "invalid_request"


async def test_status_malformed_job_id_returns_invalid_request_field_job_id():
    # Non-GUID string survives the [^/]+ native matcher and reaches
    # managed RequireJobId (TryParseJobId), which rejects with
    # field=job_id.
    status, body, headers = await _get_video("jobs/not-a-guid")
    assert status == 400
    assert body["success"] is False
    assert body["data"].get("code") == "invalid_request"
    assert body["data"].get("field") == "job_id"
    # Header pins the "managed reached it" invariant.
    assert headers.get("x-rook-vision-op") == "get_video_job"


# ─── Submit / estimate validation (parity check) ─────────────────────
#
# Submit and estimate share the same parser (ParseGenerationRequest);
# missing-required-field rejection should target the named field.


@pytest.mark.parametrize("missing_field", [
    "model", "mode", "duration_seconds",
    "resolution", "aspect_ratio", "options",
])
async def test_submit_missing_required_field_rejected_with_field_name(missing_field):
    body_in = {
        "model": "veo-3.0-fast-generate-001",
        "mode": "t2v",
        "duration_seconds": 8,
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "options": {"person_generation": "dont_allow"},
    }
    body_in.pop(missing_field)
    status, body, _ = await _post_video("jobs", body_in)
    assert status == 400
    assert body["success"] is False
    assert body["data"].get("code") == "invalid_request"
    # Field name surfaces directly. options.person_generation → bare
    # "options" since the dict-level key is missing entirely.
    field = body["data"].get("field", "")
    assert field.startswith(missing_field), (
        f"expected field starting with '{missing_field}', got {field!r}"
    )


async def test_submit_path_kind_media_ref_rejected():
    # V2 D2.1: the HTTP boundary rejects kind:"path" media refs to
    # prevent unauthenticated path exfiltration. Field name is the
    # bare "kind" per scope contract.
    body_in = {
        "model": "veo-3.0-fast-generate-001",
        "mode": "i2v",
        "duration_seconds": 8,
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "options": {"person_generation": "dont_allow"},
        "start_frame": {"kind": "path", "path": "C:\\anything.png"},
    }
    status, body, _ = await _post_video("jobs", body_in)
    assert status == 400
    assert body["success"] is False
    assert body["data"].get("code") == "invalid_request"
    assert body["data"].get("field") == "kind"


async def test_estimate_unknown_model_rejected_with_field_model():
    body_in = {
        "model": "veo-9000-not-a-model",
        "mode": "t2v",
        "duration_seconds": 8,
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "options": {"person_generation": "dont_allow"},
    }
    status, body, _ = await _post_video("estimate", body_in)
    assert status == 400
    assert body["success"] is False
    assert body["data"].get("code") == "invalid_request"
    assert body["data"].get("field") == "Model"


async def test_estimate_happy_path_returns_pricing():
    # Live registry resolution + pure-CPU pricing arithmetic. No Veo
    # API call. Uses a known-registered model id.
    #
    # The estimator runs the same CapabilityValidator as submit, so a
    # t2v body must include `prompt` (validator rejects with
    # field=Prompt otherwise — verified live, 2026-04-26 deploy).
    body_in = {
        "model": "veo-3.0-fast-generate-001",
        "mode": "t2v",
        "duration_seconds": 8,
        "resolution": "720p",
        "aspect_ratio": "16:9",
        # Veo 3 Fast requires PersonGeneration=AllowAll for t2v
        # (verified live, 2026-04-26: rejects 'dont_allow' with
        # code=unsupported_media field=PersonGeneration). The Veo
        # capability matrix is per-model + per-mode; consult
        # rhino_video_models for the agent-facing listing.
        "options": {"person_generation": "allow_all"},
        "prompt": "test prompt for cost estimate",
    }
    status, body, _ = await _post_video("estimate", body_in)

    # Tolerate ONE specific drift: the model id may have been retired
    # or renamed in the registry. In that case we expect a typed
    # InvalidRequest with field=Model, NOT a 500/503/etc. Anything
    # else is a real failure that this test must surface.
    if status == 400 and not body.get("success"):
        data = body.get("data", {})
        if isinstance(data, dict) and data.get("field") == "Model":
            pytest.skip(
                f"Model {body_in['model']!r} no longer registered — "
                f"shape-pin test inapplicable. Update model id when "
                f"the registry shifts."
            )
        # Some other 400 — fall through to the strict assertions
        # below, which will fail with the real envelope for diagnosis.

    assert status == 200, (
        f"expected 200, got {status} body={body!r}"
    )
    assert body["success"] is True
    data = body["data"]
    for required in (
        "dollars_usd", "model", "resolution", "duration_seconds",
        "number_of_videos", "breakdown", "pricing",
    ):
        assert required in data, f"estimate response missing '{required}'"
    assert isinstance(data["dollars_usd"], (int, float))
    assert data["dollars_usd"] >= 0
