"""Vertical readiness witness: one complete readiness->launch transaction walked
through the REAL experiment transmit entry point with fake providers and an
injected clock. A valid record must reach allocation + provider construction;
manifest-binding drift, staleness, and credential absence must each refuse
before allocation."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
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
P = _load_script("lm9b_p_readiness_probe")
LM9BC = _load_script("lm9b_c_compiler_sufficiency_probe")
EXP = _load_script("lm9b_p_planner_recipe_transfer_probe")

FAKE_SHA = "d" * 40
FULL_ENV = {"OPENAI_API_KEY": "x", "GEMINI_API_KEY": "y"}


class _FakeClock:
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


def _seal_record_file(tmp_path) -> tuple[Path, dict]:
    readiness_root = tmp_path / "readiness"
    record = P.run_readiness(
        run_root=readiness_root,
        head_sha=FAKE_SHA,
        environ=FULL_ENV,
        authenticate=True,
        provider_factory=_ok_provider,
        clock=_FakeClock(),
    )
    return readiness_root / "readiness_record.json", record


def _canonical_argv(attempt_root, rec_path, *, planner="gpt-5.4"):
    return [
        "--planner-model", planner,
        "--planner-evaluator-model", planner,
        "--compiler-model", "gemini/gemini-3.1-pro-preview",
        "--compiler-evaluator-model", "gemini/gemini-3.1-pro-preview",
        "--planner-temperature", "0.0",
        "--planner-evaluator-temperature", "0.0",
        "--compiler-temperature", "0.0",
        "--compiler-evaluator-temperature", "0.0",
        "--run-root", str(attempt_root),
        "--transmit",
        "--readiness-record", str(rec_path),
    ]


def _drive_transmit(monkeypatch, rec_path, *, now_iso, environ, attempt_root):
    calls = {"provider": 0}

    def exploding(*args, **kwargs):
        calls["provider"] += 1
        raise RuntimeError("SENTINEL_PROVIDER_CONSTRUCTED")

    monkeypatch.setattr(EXP, "_build_provider", exploding)
    monkeypatch.setattr(
        EXP, "_git_checkout_state",
        lambda: EXP.GitCheckoutState(commit_sha=FAKE_SHA, clean=True),
    )
    monkeypatch.setattr(EXP, "_readiness_now_iso", lambda: now_iso)
    monkeypatch.setattr(os, "environ", dict(environ))
    config = EXP.parse_cli_args(_canonical_argv(attempt_root, rec_path))
    prepared = EXP.prepare_pretransmission(config)
    return EXP._execute_transmitted_attempt(prepared), calls


def test_valid_record_reaches_allocation_and_provider_construction(monkeypatch, tmp_path):
    rec_path, _ = _seal_record_file(tmp_path)
    attempt = tmp_path / "attempt"
    result, calls = _drive_transmit(
        monkeypatch, rec_path, now_iso="2026-07-21T12:00:30Z",
        environ=FULL_ENV, attempt_root=attempt,
    )
    assert isinstance(result, EXP.TerminalControlFailureResult)
    assert result.control_failure["locus"] == "provider_construction"
    assert result.control_failure["role"] == "planner"
    assert calls["provider"] == 1
    assert attempt.exists()  # allocation happened past the gate


def test_manifest_binding_drift_refuses_before_allocation(monkeypatch, tmp_path):
    rec_path, record = _seal_record_file(tmp_path)
    record["route_manifest_fingerprint"] = "sha256:tampered"
    record["record_fingerprint"] = C.record_fingerprint(record)
    rec_path.write_text(json.dumps(record), encoding="utf-8")
    attempt = tmp_path / "attempt"
    with pytest.raises(RuntimeError, match="readiness gate refused"):
        _drive_transmit(
            monkeypatch, rec_path, now_iso="2026-07-21T12:00:30Z",
            environ=FULL_ENV, attempt_root=attempt,
        )
    assert not attempt.exists()


def test_stale_record_refuses_before_allocation(monkeypatch, tmp_path):
    rec_path, _ = _seal_record_file(tmp_path)
    attempt = tmp_path / "attempt"
    with pytest.raises(RuntimeError, match="readiness gate refused"):
        _drive_transmit(
            monkeypatch, rec_path, now_iso="2026-07-21T12:30:00Z",  # ~30 min later
            environ=FULL_ENV, attempt_root=attempt,
        )
    assert not attempt.exists()


def test_credential_absent_refuses_before_allocation(monkeypatch, tmp_path):
    rec_path, _ = _seal_record_file(tmp_path)
    attempt = tmp_path / "attempt"
    with pytest.raises(RuntimeError, match="readiness gate refused"):
        _drive_transmit(
            monkeypatch, rec_path, now_iso="2026-07-21T12:00:30Z",
            environ={"OPENAI_API_KEY": "x"},  # gemini credentials absent
            attempt_root=attempt,
        )
    assert not attempt.exists()


def test_canonical_planner_pin_rejects_non_gpt54(tmp_path):
    with pytest.raises(SystemExit):
        EXP.parse_cli_args(
            _canonical_argv(tmp_path / "a", tmp_path / "r.json", planner="gpt-4o")
        )


def test_transmit_without_readiness_record_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        EXP.parse_cli_args([
            "--planner-model", "gpt-5.4",
            "--planner-evaluator-model", "gpt-5.4",
            "--compiler-model", "gemini/gemini-3.1-pro-preview",
            "--compiler-evaluator-model", "gemini/gemini-3.1-pro-preview",
            "--planner-temperature", "0.0",
            "--planner-evaluator-temperature", "0.0",
            "--compiler-temperature", "0.0",
            "--compiler-evaluator-temperature", "0.0",
            "--run-root", str(tmp_path / "run"),
            "--transmit",  # no --readiness-record
        ])


def test_direct_execution_without_record_refuses_before_allocation(monkeypatch, tmp_path):
    attempt = tmp_path / "attempt"
    config = EXP.CliAttemptConfig(
        planner_model="gpt-5.4",
        planner_evaluator_model="gpt-5.4",
        compiler_model="gemini/gemini-3.1-pro-preview",
        compiler_evaluator_model="gemini/gemini-3.1-pro-preview",
        planner_temperature=0.0,
        planner_evaluator_temperature=0.0,
        compiler_temperature=0.0,
        compiler_evaluator_temperature=0.0,
        run_root=attempt,
        transmit=True,
        readiness_record=None,
    )
    inputs = EXP.ARTIFACTS.load_planner_inputs(EXP._PLANNER_FIXTURES)
    prepared = EXP.PreparedTransmission(
        config=config,
        git_sha=FAKE_SHA,
        planner_inputs=inputs,
        planner_request=EXP.ARTIFACTS.render_planner_request(inputs),
        compiler_controls=EXP._freeze_compiler_controls(),
        summary={},
    )
    monkeypatch.setattr(
        EXP, "_git_checkout_state",
        lambda: EXP.GitCheckoutState(commit_sha=FAKE_SHA, clean=True),
    )
    with pytest.raises(RuntimeError, match="no readiness record supplied"):
        EXP._execute_transmitted_attempt(prepared)
    assert not attempt.exists()


def test_dry_run_requires_no_readiness_record(tmp_path):
    config = EXP.parse_cli_args([
        "--planner-model", "gpt-5.4",
        "--planner-evaluator-model", "gpt-5.4",
        "--compiler-model", "gemini/gemini-3.1-pro-preview",
        "--compiler-evaluator-model", "gemini/gemini-3.1-pro-preview",
        "--planner-temperature", "0.0",
        "--planner-evaluator-temperature", "0.0",
        "--compiler-temperature", "0.0",
        "--compiler-evaluator-temperature", "0.0",
        "--run-root", str(tmp_path / "run"),  # no --transmit, no --readiness-record
    ])
    assert config.transmit is False
    assert config.readiness_record is None


def test_import_isolation_experiment_cli_pulls_no_provider_contact_module():
    code = (
        "import sys; "
        f"sys.path.insert(0, r'{ROOT / 'scripts'}'); "
        f"sys.path.insert(0, r'{ROOT / 'mcp_server' / 'src'}'); "
        "import lm9b_p_planner_recipe_transfer_probe; "
        "assert 'lm9b_p_readiness_probe' not in sys.modules, 'canary module leaked'; "
        "print('ok')"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "ok" in out.stdout
