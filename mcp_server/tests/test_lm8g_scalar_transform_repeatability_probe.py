from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm8g_scalar_transform_repeatability_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm8g_scalar_transform_repeatability_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical_lm8g_shape():
    args = PROBE._args([])

    assert args.attempts == 5
    assert args.model == "gemma4:12b-it-qat"
    assert args.run_dir == "probe_runs"
    assert args.attempt_timeout_s == 600
    assert PROBE._canonical_evidence(attempts=args.attempts, model=args.model) is True


def test_cli_rejects_non_positive_attempts():
    for value in ("0", "-1"):
        with pytest.raises(SystemExit):
            PROBE._args(["--attempts", value])


def test_canonical_evidence_only_for_five_gemma_attempts():
    assert PROBE._canonical_evidence(attempts=5, model="gemma4:12b-it-qat") is True
    assert PROBE._canonical_evidence(attempts=1, model="gemma4:12b-it-qat") is False
    assert PROBE._canonical_evidence(attempts=5, model="qwen3:14b") is False


def test_cli_rejects_non_lm8g_surfaces():
    forbidden = (
        ["--retry-clean-observation"],
        ["--planner-provider-command", "x"],
        ["--prompt-profile", "shape_guidance_v2"],
        ["--request-json", "request.json"],
        ["--gh-edit"],
        ["--phase", "receipt_recon"],
    )
    for argv in forbidden:
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_manifest_records_lm8g_identity():
    manifest = PROBE._manifest(attempts=5, model="gemma4:12b-it-qat")

    assert manifest["schema"] == "rook.lm8g_scalar_transform_repeatability_probe:v1"
    assert manifest["attempts"] == 5
    assert manifest["model"] == "gemma4:12b-it-qat"
    assert manifest["canonical_evidence"] is True


def test_lm8f_command_uses_sys_executable_and_child_run_dir(tmp_path: Path, monkeypatch):
    runs_dir = tmp_path / "lm8f_runs"
    monkeypatch.chdir(tmp_path)

    command = PROBE._lm8f_command(
        model="gemma4:12b-it-qat",
        lm8f_runs_dir=runs_dir,
    )

    assert command == [
        sys.executable,
        str(PROBE._REPO_ROOT / "scripts" / "lm8f_scalar_transform_depth_probe.py"),
        "--model",
        "gemma4:12b-it-qat",
        "--run-dir",
        str(runs_dir),
    ]
    assert "--retry-clean-observation" not in command
    assert "--gh-edit" not in command
