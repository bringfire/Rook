from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
MCP_SRC = ROOT / "mcp_server" / "src"
for entry in (SCRIPTS, MCP_SRC):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))


import lm9b_p_governed_resolution_archive_evidence as ARCHIVE_EVIDENCE
import lm9b_p_governed_resolution_artifacts as ARTIFACTS


PROFILE_PATH = (
    SCRIPTS
    / "lm9b_p_governed_resolution_contracts"
    / "archive_evidence_resource_profile.json"
)


def _profile() -> object:
    return ARCHIVE_EVIDENCE.admit_resolution_archive_resource_profile(
        PROFILE_PATH.read_bytes()
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_task1_profile_is_closed_and_matches_checkpoint_member_map() -> None:
    profile = _profile()
    value = ARCHIVE_EVIDENCE.consume_resolution_archive_resource_profile(profile)

    assert value["profile_fingerprint"] == ARCHIVE_EVIDENCE.PROFILE_FINGERPRINT
    assert {
        row["path"]: row["role"] for row in value["members"]
    } == dict(ARTIFACTS.RESOLUTION_ARCHIVE_MEMBERS)
    assert ARCHIVE_EVIDENCE.resolution_member_ceiling(
        path="call-ledger.json",
        profile=profile,
        preparse=True,
    ) == 345_068_924
    with pytest.raises(TypeError, match="closure-issued"):
        ARCHIVE_EVIDENCE.VerifiedResolutionArchiveResourceProfile()


def test_task1_call_ledger_issues_shape_for_dependent_member_parsing() -> None:
    profile = _profile()
    row = {
        "schema": "rook.lm9b_p.governed_resolution_call:v1",
        "call_index": 0,
        "role": "planner",
        "request_raw_sha256": "sha256:request",
        "preceding_transcript_fingerprint": "sha256:transcript",
        "provider_timeout_s": 180.0,
        "controller_deadline_state": {"turn_index": 1},
        "role_contract_fingerprint": "sha256:role",
        "dispatch_marker_raw_sha256": "sha256:dispatch",
        "canonical_request_json": "{}",
        "provider_claimed_raw_request_b64": "e30=",
        "provider_claimed_raw_request_sha256": "sha256:adapter",
        "provider_raw_error_b64": None,
        "provider_raw_error_sha256": None,
        "raw_response_b64": "e30=",
        "raw_response_sha256": "sha256:response",
        "assistant_message": {"role": "assistant"},
        "usage": {},
        "provider_metadata": {},
        "outcome": "returned",
        "exception_type": None,
        "failure_type": None,
        "elapsed_ms": 1,
        "terminal": True,
    }
    ledger, shape = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        _canonical_bytes(
            {
                "schema": "rook.lm9b_p.governed_resolution_call_ledger:v1",
                "calls": [row],
            }
        ),
        profile=profile,
    )
    snapshot = ARCHIVE_EVIDENCE.consume_resolution_call_shape(
        shape,
        profile=profile,
    )

    assert len(ledger["calls"]) == 1
    assert snapshot["planner_count"] == 1
    assert snapshot["evaluator_count"] == 0
    assert ARCHIVE_EVIDENCE.parse_resolution_archive_member(
        _canonical_bytes({"calls": [{}]}),
        path="planner-session.json",
        profile=profile,
        call_shape=shape,
    ) == {"calls": [{}]}
    with pytest.raises(TypeError, match="closure-issued"):
        ARCHIVE_EVIDENCE.VerifiedResolutionCallShape()
