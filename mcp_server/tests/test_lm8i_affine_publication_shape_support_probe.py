from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm8i_affine_publication_shape_support_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm8i_affine_publication_shape_support_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical_lm8i_shape():
    args = PROBE._args([])

    assert args.model == "gemma4:12b-it-qat"
    assert args.endpoint == "http://localhost:11434/api/chat"
    assert args.temperature == 0
    assert args.timeout_s == 120
    assert args.excerpt_chars == 1200
    assert args.run_dir == "probe_runs"
    assert args.canonical_evidence is True


def test_cli_rejects_non_lm8i_surfaces():
    forbidden = [
        ["--phase", "receipt_recon"],
        ["--attempts", "5"],
        ["--retry-clean-observation"],
        ["--planner-provider-command", "x"],
        ["--prompt-profile", "shape_guidance_v2"],
        ["--request-json", "request.json"],
        ["--gh-edit"],
    ]
    for argv in forbidden:
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_manifest_records_lm8i_identity():
    manifest = PROBE._manifest(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        canonical_evidence=True,
    )

    assert manifest["schema"] == "rook.lm8i_affine_publication_shape_support_probe:v1"
    assert manifest["attempts"] == 1
    assert manifest["publication_support_enabled"] is True
    assert manifest["publication_support_budget"] == 1
    assert manifest["support_eligibility"] == "exact_skeletal_action_request_missing_action_id"
    assert manifest["worker_retry_enabled"] is False
    assert manifest["planner_model"] is None
    assert manifest["gh_edit_enabled"] is False
