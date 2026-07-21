"""Launch-verifier refusal matrix: one refusal case per equation, plus the
happy path. Every mutation re-seals record_fingerprint so the case exercises the
intended equation rather than the record-integrity check."""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


C = _load_script("lm9b_p_readiness_contract")
HEAD = "d" * 40
MODELS = dict(C.CANONICAL_ROLE_MODELS)


def _manifest():
    return C.derive_routes(C.role_routes_from_models(MODELS), lambda _m: None)


def _fresh(now="2026-07-21T12:00:10Z", observed="2026-07-21T12:00:05Z"):
    m = _manifest()
    rows = [
        {
            "route_fingerprint": r.route_fingerprint,
            "member_roles": list(r.member_roles),
            "observed_at": observed,
            "request_fingerprint": C.request_fingerprint(r),
            "outcome": {
                "kind": "model_response",
                "assistant_present": True,
                "tool_calls": [{"name": "ack", "arguments": '{"ok": true}'}],
                "raw_response_fingerprint": "sha256:resp",
            },
        }
        for r in m.routes
    ]
    rec = {
        "schema_id": C.SCHEMA_ID,
        "reviewed_commit_sha": HEAD,
        "route_manifest_fingerprint": m.manifest_fingerprint,
        "canary_protocol_fingerprint": C.canary_protocol_fingerprint(),
        "max_age_seconds": 600,
        "completed_at": now,
        "routes": rows,
    }
    rec["record_fingerprint"] = C.record_fingerprint(rec)
    return rec


def _reseal(rec):
    rec["record_fingerprint"] = C.record_fingerprint(rec)
    return rec


def _verify(rec, now="2026-07-21T12:00:15Z", present=None):
    present = present or {r["route_fingerprint"]: True for r in rec["routes"]}
    return C.verify_launch_readiness(
        record=rec, manifest=_manifest(), head_sha=HEAD, now_iso=now,
        credential_present=present,
    ).ok


def test_happy_path_permits():
    assert _verify(_fresh()) is True


def test_schema_id_mismatch_refuses():
    r = _fresh()
    r["schema_id"] = "lm9b_p.readiness_record:v2"
    assert _verify(_reseal(r)) is False


def test_sha_mismatch_refuses():
    r = _fresh()
    r["reviewed_commit_sha"] = "e" * 40
    assert _verify(_reseal(r)) is False


def test_manifest_fp_mismatch_refuses():
    r = _fresh()
    r["route_manifest_fingerprint"] = "sha256:x"
    assert _verify(_reseal(r)) is False


def test_record_fp_mismatch_refuses():
    r = _fresh()
    r["record_fingerprint"] = "sha256:x"
    assert _verify(r) is False


def test_protocol_fp_mismatch_refuses():
    r = _fresh()
    r["canary_protocol_fingerprint"] = "sha256:x"
    assert _verify(_reseal(r)) is False


def test_max_age_field_mismatch_refuses():
    r = _fresh()
    r["max_age_seconds"] = 1200
    assert _verify(_reseal(r)) is False


def test_missing_route_refuses():
    r = _fresh()
    r["routes"] = r["routes"][:1]
    assert _verify(_reseal(r)) is False


def test_duplicate_route_refuses():
    r = _fresh()
    r["routes"] = [r["routes"][0], copy.deepcopy(r["routes"][0])]
    assert _verify(_reseal(r)) is False


def test_extra_route_refuses():
    r = _fresh()
    extra = copy.deepcopy(r["routes"][0])
    extra["route_fingerprint"] = "sha256:not-in-manifest"
    r["routes"] = r["routes"] + [extra]
    assert _verify(_reseal(r)) is False


def test_member_roles_mismatch_refuses():
    r = _fresh()
    r["routes"][0]["member_roles"] = ["planner"]
    assert _verify(_reseal(r)) is False


def test_request_binding_mismatch_refuses():
    r = _fresh()
    r["routes"][0]["request_fingerprint"] = "sha256:x"
    assert _verify(_reseal(r)) is False


def test_stale_record_refuses():
    assert _verify(_fresh(now="2026-07-21T12:00:00Z"), now="2026-07-21T12:20:00Z") is False


def test_future_record_refuses():
    assert _verify(_fresh(now="2026-07-21T12:10:00Z"), now="2026-07-21T12:00:00Z") is False


def test_stale_route_observed_at_refuses():
    assert _verify(_fresh(now="2026-07-21T12:00:10Z", observed="2026-07-21T11:40:00Z")) is False


def test_completed_precedes_observed_refuses():
    r = _fresh(now="2026-07-21T12:00:00Z", observed="2026-07-21T12:00:30Z")
    assert _verify(_reseal(r), now="2026-07-21T12:00:31Z") is False


def test_credential_absent_refuses():
    r = _fresh()
    pres = {row["route_fingerprint"]: True for row in r["routes"]}
    pres[r["routes"][0]["route_fingerprint"]] = False
    assert _verify(r, present=pres) is False


def test_route_unready_refuses():
    r = _fresh()
    r["routes"][0]["outcome"]["kind"] = "transport_failure"
    assert _verify(_reseal(r)) is False
