from __future__ import annotations

import pytest

from rook.agent.chat.acp_rook_results import parse_rook_envelope


@pytest.mark.parametrize(
    "payload",
    [
        '{"toolStatus":"completed"}',
        '"{\\"success\\":true,\\"data\\":{}}"',
        '{"success":true}',
        '{"success":"true","data":{}}',
        "not-json",
        "[]",
    ],
)
def test_non_envelopes_never_certify_a_rook_result(payload: str) -> None:
    assert parse_rook_envelope(payload) is None


@pytest.mark.parametrize("data", [{"receipt": "r-1"}, [1, 2], "target_unavailable", 7, True, None])
def test_exact_rook_envelope_preserves_every_json_data_shape(data: object) -> None:
    import json

    parsed = parse_rook_envelope(json.dumps({"success": True, "data": data}))

    assert parsed is not None
    assert parsed.success is True
    assert parsed.data == data


def test_exact_rook_failure_envelope_remains_failure() -> None:
    parsed = parse_rook_envelope('{"success":false,"data":"target_unavailable"}')

    assert parsed is not None
    assert parsed.success is False
    assert parsed.data == "target_unavailable"


def test_rook_envelope_allows_additional_public_fields_without_changing_authority() -> None:
    parsed = parse_rook_envelope(
        '{"success":true,"data":{"receipt":"r-1"},"requestId":"request-9"}'
    )

    assert parsed is not None
    assert parsed.success is True
    assert parsed.data == {"receipt": "r-1"}
