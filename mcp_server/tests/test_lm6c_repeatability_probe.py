from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm6c_repeatability_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm6c_repeatability_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical() -> None:
    args = PROBE._args([])

    assert args.attempts == 5
    assert args.model == "gemma4:12b-it-qat"
    assert args.run_dir == "probe_runs"
    assert args.attempt_timeout_s == 600


def test_cli_rejects_non_positive_attempts() -> None:
    with pytest.raises(SystemExit):
        PROBE._args(["--attempts", "0"])


def test_canonical_evidence_only_for_five_gemma_qat_attempts() -> None:
    assert PROBE._canonical_evidence(attempts=5, model="gemma4:12b-it-qat") is True
    assert PROBE._canonical_evidence(attempts=1, model="gemma4:12b-it-qat") is False
    assert PROBE._canonical_evidence(attempts=5, model="qwen3:14b") is False
