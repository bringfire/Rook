"""Archive-evidence JSON contract.

The Planner-authored recipe ingress rejects every float; archive evidence
(harness-written provider metadata such as temperature and cost_usd) legitimately
carries finite floats. These tests pin that dedicated boundary: the writer and
reader admit finite numbers while rejecting duplicates and non-finite values, and
a full mechanically-rejected session seals and verifies with real-shaped floats."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "scripts" / "lm9b_p_fixtures"


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Dependency order so shared classes (ProviderTurn, StrictJsonError) are identical.
SUPPORT = _load_script("lm9b_p_planner_recipe_transfer_support")
ARTIFACTS = _load_script("lm9b_p_planner_recipe_transfer_artifacts")
PROBE = _load_script("lm9b_p_planner_recipe_transfer_probe")

ARCHIVE_IDENTITY = {
    "git_commit_sha": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip(),
    "planner_model_identity": "gpt-5.4",
    "evaluator_model_identity": "gpt-5.4",
    "provider_profile_identity": "litellm.completion.tool_calling.no_parallel:v1",
}

# Real-shaped provider evidence: temperature (metadata) and cost_usd (usage) are floats.
_PROVIDER_METADATA = {
    "model_identity": "gpt-5.4",
    "profile_identity": "litellm.completion.tool_calling.no_parallel:v1",
    "temperature": 0.0,
}
_USAGE = {"cost_usd": 0.0012, "prompt_tokens": 100, "completion_tokens": 8}


class _Provider:
    identity = {"provider": "fake"}

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _float_turn():
    return SUPPORT.ProviderTurn(
        raw_request=b'{"planner":"request"}',
        raw_response=b'{"planner":"response"}',
        assistant_message={"role": "assistant", "tool_calls": []},
        usage=dict(_USAGE),
        provider_metadata=dict(_PROVIDER_METADATA),
    )


# ── 1 & 2: finite provider floats survive write -> readback ──────────────────

def test_archive_boundary_accepts_finite_temperature_and_cost():
    payload = {"provider_metadata": dict(_PROVIDER_METADATA), "usage": dict(_USAGE)}
    raw = ARTIFACTS._archive_json_bytes(payload)
    assert SUPPORT.parse_archive_json(raw) == payload
    assert SUPPORT.parse_archive_json(raw)["provider_metadata"]["temperature"] == 0.0
    assert SUPPORT.parse_archive_json(raw)["usage"]["cost_usd"] == 0.0012


# ── 3: duplicates and non-finite fail (reader and writer) ────────────────────

@pytest.mark.parametrize("raw", [
    b'{"a": 1, "a": 2}',
    b'{"x": NaN}',
    b'{"x": Infinity}',
    b'{"x": -Infinity}',
    b'{"x": 1e999}',
])
def test_archive_reader_rejects_duplicate_and_non_finite(raw):
    with pytest.raises(SUPPORT.StrictJsonError):
        SUPPORT.parse_archive_json(raw)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_archive_writer_refuses_non_finite(value):
    with pytest.raises(ValueError):
        ARTIFACTS._archive_json_bytes({"x": value})


# ── 5: recipe ingress stays strict (floats rejected) ─────────────────────────

def test_recipe_ingress_still_rejects_floats():
    with pytest.raises(SUPPORT.StrictJsonError):
        SUPPORT.parse_strict_json(b'{"temperature": 0.0}')


# ── 6: full mechanically-rejected session seals and verifies with floats ─────

def test_mechanically_rejected_session_seals_and_verifies_with_provider_floats(tmp_path):
    archive_dir = tmp_path / "checkpoint-1"
    planner = _Provider([_float_turn() for _ in range(SUPPORT.PLANNER_MAX_TURNS)])
    evaluator = _Provider([RuntimeError("evaluator must not run")])
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=planner,
        evaluator_provider=evaluator,
        archive_destination=archive_dir,
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert result.classification == "probe_mechanically_rejected"
    assert result.sealed_archive is not None  # seal succeeded despite provider floats
    # The float evidence actually landed in the archive.
    capture = json.loads((archive_dir / "planner/attempts/000/capture.json").read_bytes())
    assert capture["provider_metadata"]["temperature"] == 0.0
    usage = json.loads((archive_dir / "planner/attempts/000/usage.json").read_bytes())
    assert usage["cost_usd"] == 0.0012
    # Independent verification of the sealed archive succeeds.
    sealed = ARTIFACTS.verify_sealed_planner_checkpoint_archive(
        archive_dir, expected_aggregate_identity=result.sealed_archive.aggregate_identity
    )
    assert sealed.aggregate_identity == result.sealed_archive.aggregate_identity


# ── 4: tampering a sealed archive is still detected ──────────────────────────

def test_tampered_archive_bytes_still_fail(tmp_path):
    archive_dir = tmp_path / "checkpoint-1"
    planner = _Provider([_float_turn() for _ in range(SUPPORT.PLANNER_MAX_TURNS)])
    evaluator = _Provider([RuntimeError("evaluator must not run")])
    result = PROBE.run_planner_checkpoint(
        fixture_dir=FIXTURES,
        planner_provider=planner,
        evaluator_provider=evaluator,
        archive_destination=archive_dir,
        archive_identity=ARCHIVE_IDENTITY,
    )
    assert result.sealed_archive is not None
    capture_path = archive_dir / "planner/attempts/000/capture.json"
    tampered = capture_path.read_bytes().replace(b'"temperature": 0.0', b'"temperature": 0.5')
    assert tampered != capture_path.read_bytes()
    capture_path.write_bytes(tampered)
    with pytest.raises(ValueError):
        ARTIFACTS.verify_sealed_planner_checkpoint_archive(
            archive_dir, expected_aggregate_identity=result.sealed_archive.aggregate_identity
        )
