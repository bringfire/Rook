"""Readiness probe behavior: discriminated canary capture, approval/cardinality,
timestamp ordering, credential-before-root, and canary content exclusion. All
providers are fakes; no real provider is contacted."""

from __future__ import annotations

import importlib.util
import json
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


# Load dependencies before the probe so the probe reuses these exact module
# instances (shared exception/class identity for pytest.raises and isinstance).
C = _load_script("lm9b_p_readiness_contract")
LM9BC = _load_script("lm9b_c_compiler_sufficiency_probe")
P = _load_script("lm9b_p_readiness_probe")

FULL_ENV = {"OPENAI_API_KEY": "x", "GEMINI_API_KEY": "y"}


class _Clock:
    def __init__(self) -> None:
        self.n = 0

    def __call__(self) -> str:
        self.n += 1
        return f"2026-07-21T12:00:{self.n:02d}Z"


def _ok_provider(route):
    def _call(request):
        return LM9BC.ProviderTurn(
            raw_request=b"{}",
            raw_response=b'{"id":"x"}',
            assistant_message={
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "1",
                        "type": "function",
                        "function": {"name": "ack", "arguments": '{"ok": true}'},
                    }
                ],
            },
            usage={},
            provider_metadata={},
        )

    return _call


def _raising_provider(route):
    def _call(request):
        raise LM9BC.ProviderCallFailure(
            failure_type="InternalServerError",
            message="boom",
            raw_request=b"{}",
            raw_error=b"{}",
        )

    return _call


def _route0():
    return C.derive_routes(
        C.role_routes_from_models(C.CANONICAL_ROLE_MODELS), lambda m: None
    ).routes[0]


def test_success_row_ready_and_bound():
    route = _route0()
    row = P.run_canary(route, _ok_provider(route), clock=_Clock())
    assert row["outcome"]["kind"] == "model_response"
    assert C.route_ready(row) is True
    assert row["request_fingerprint"] == C.request_fingerprint(route)


def test_transport_failure_row():
    route = _route0()
    row = P.run_canary(route, _raising_provider(route), clock=_Clock())
    assert row["outcome"]["kind"] == "transport_failure"
    assert row["outcome"]["classification"] == "InternalServerError"
    assert C.route_ready(row) is False


def test_no_authenticate_no_contact(tmp_path):
    made = []

    def factory(route):
        made.append(route)
        return _ok_provider(route)

    rec = P.run_readiness(
        run_root=tmp_path / "r", head_sha="d" * 40, environ=FULL_ENV,
        authenticate=False, provider_factory=factory, clock=_Clock(),
    )
    assert made == []
    assert rec["routes"] == []


def test_authenticate_contacts_each_route_once_and_orders_time(tmp_path):
    manifest = C.derive_routes(
        C.role_routes_from_models(C.CANONICAL_ROLE_MODELS), lambda m: None
    )
    contact_counts = {route.route_fingerprint: 0 for route in manifest.routes}

    def factory(route):
        base = _ok_provider(route)

        def _counting(request):
            contact_counts[route.route_fingerprint] += 1
            return base(request)

        return _counting

    rec = P.run_readiness(
        run_root=tmp_path / "r", head_sha="d" * 40, environ=FULL_ENV,
        authenticate=True, provider_factory=factory, clock=_Clock(),
    )
    assert len(rec["routes"]) == len(manifest.routes)
    # Exactly one actual provider invocation for every manifest route.
    assert contact_counts == {route.route_fingerprint: 1 for route in manifest.routes}
    assert rec["completed_at"] >= max(row["observed_at"] for row in rec["routes"])


def test_absent_assistant_message_records_absence(tmp_path):
    route = _route0()

    def _no_assistant(request):
        return LM9BC.ProviderTurn(
            raw_request=b"{}", raw_response=b'{"id":"x"}',
            assistant_message=None, usage={}, provider_metadata={},
        )

    row = P.run_canary(route, _no_assistant, clock=_Clock())
    assert row["outcome"]["kind"] == "model_response"
    assert row["outcome"]["assistant_present"] is False  # observed, not authored
    assert C.route_ready(row) is False


def test_missing_credential_leaves_no_directory(tmp_path):
    root = tmp_path / "r"
    with pytest.raises(C.ReadinessError):
        P.run_readiness(
            run_root=root, head_sha="d" * 40, environ={"OPENAI_API_KEY": "x"},
            authenticate=True, provider_factory=_ok_provider, clock=_Clock(),
        )
    assert not root.exists()


def test_canary_request_excludes_experiment_content():
    blob = json.dumps(C.build_canary_request(_route0())).lower()
    for forbidden in ("brief", "authority", "r01", "rubric", "recipe", "planner_graph"):
        assert forbidden not in blob


@pytest.mark.parametrize(("authenticate", "expected_calls"), [(False, 0), (True, 1)])
def test_planner_evaluator_role_reuses_one_route_readiness(
    tmp_path: Path,
    authenticate: bool,
    expected_calls: int,
) -> None:
    calls = 0

    def factory(route):
        base = _ok_provider(route)

        def count(request):
            nonlocal calls
            calls += 1
            return base(request)

        return count

    models = {"planner_evaluator": "gpt-5.4"}
    manifest = C.derive_routes(C.role_routes_from_models(models), P.HELPER)
    record = P.run_readiness(
        run_root=tmp_path / f"readiness-{authenticate}",
        head_sha="e" * 40,
        environ={"OPENAI_API_KEY": "x"},
        authenticate=authenticate,
        provider_factory=factory,
        clock=_Clock(),
        models=models,
    )
    assert len(manifest.routes) == 1
    assert manifest.routes[0].member_roles == ("planner_evaluator",)
    assert record["schema_id"] == C.SCHEMA_ID
    assert record["route_manifest_fingerprint"] == manifest.manifest_fingerprint
    assert record["canary_protocol_fingerprint"] == C.canary_protocol_fingerprint()
    assert record["max_age_seconds"] == C.FROZEN_MAX_AGE_S
    assert calls == expected_calls


def test_cli_role_selects_one_model_and_omission_retains_all_roles(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected: list[dict[str, str]] = []

    def fake_run_readiness(**kwargs):
        selected.append(dict(kwargs["models"]))
        return {"routes": []}

    monkeypatch.setattr(P, "run_readiness", fake_run_readiness)
    assert P.main(
        [
            "--run-root",
            str(tmp_path / "one"),
            "--reviewed-commit-sha",
            "f" * 40,
            "--role",
            "planner_evaluator",
        ]
    ) == 0
    assert P.main(
        [
            "--run-root",
            str(tmp_path / "all"),
            "--reviewed-commit-sha",
            "f" * 40,
        ]
    ) == 0
    assert selected == [
        {"planner_evaluator": "gpt-5.4"},
        C.CANONICAL_ROLE_MODELS,
    ]
