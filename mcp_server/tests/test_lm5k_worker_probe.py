from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "lm5k_worker_probe.py"
    spec = importlib.util.spec_from_file_location("lm5k_worker_probe", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PROBE = _load_script()


def test_slot_vocabulary() -> None:
    assert PROBE.SLOT_LABELS == {
        "local": "local_worker_candidate",
        "cheap": "cheap_cloud_worker_candidate",
        "ceiling": "ceiling_worker_candidate",
    }
    assert PROBE.ENV_VARS == {
        "local": "ROOK_PROBE_LOCAL_WORKER",
        "cheap": "ROOK_PROBE_CHEAP_CLOUD_WORKER",
        "ceiling": "ROOK_PROBE_CEILING_WORKER",
    }
    assert PROBE.GENERATION_PARAMS == {"temperature": 0}


def test_parse_candidate_spec() -> None:
    assert PROBE.parse_candidate_spec("ollama_chat/qwen3:8b") == (
        "ollama_chat/qwen3:8b",
        None,
    )
    assert PROBE.parse_candidate_spec(
        "openai/lmstudio-model@http://localhost:1234/v1"
    ) == ("openai/lmstudio-model", "http://localhost:1234/v1")
    with pytest.raises(ValueError):
        PROBE.parse_candidate_spec("@http://x")


def test_profile_inference_local_only_for_local_shaped_models() -> None:
    assert PROBE.profile_inferred_local("ollama_chat/qwen3:8b", None) == (
        "ollama_chat/qwen3:8b",
        None,
    )
    assert PROBE.profile_inferred_local(
        "openai/lmstudio-model", "http://localhost:1234/v1"
    ) == ("openai/lmstudio-model", "http://localhost:1234/v1")
    # openai/* WITHOUT api_base is ambiguous -> not safely inferable
    assert PROBE.profile_inferred_local("openai/lmstudio-model", None) is None
    # cloud models are never a local inference
    assert (
        PROBE.profile_inferred_local("anthropic/claude-haiku-4-5", None) is None
    )


def test_resolve_slot_order_cli_env_profile_none() -> None:
    cli = PROBE.resolve_slot(
        "local",
        cli_value="ollama_chat/a:1",
        env_value="ollama_chat/b:1",
        profile_worker="ollama_chat/c:1",
        profile_api_base=None,
        skipped=False,
    )
    assert (cli["model"], cli["source"], cli["status"]) == (
        "ollama_chat/a:1",
        "cli",
        None,
    )
    env = PROBE.resolve_slot(
        "local",
        cli_value=None,
        env_value="ollama_chat/b:1",
        profile_worker="ollama_chat/c:1",
        profile_api_base=None,
        skipped=False,
    )
    assert (env["model"], env["source"]) == ("ollama_chat/b:1", "env")
    prof = PROBE.resolve_slot(
        "local",
        cli_value=None,
        env_value=None,
        profile_worker="ollama_chat/c:1",
        profile_api_base=None,
        skipped=False,
    )
    assert (prof["model"], prof["source"]) == ("ollama_chat/c:1", "profile")
    none = PROBE.resolve_slot(
        "local",
        cli_value=None,
        env_value=None,
        profile_worker="anthropic/claude-haiku-4-5",
        profile_api_base=None,
        skipped=False,
    )
    assert (none["model"], none["source"], none["status"]) == (
        None,
        "none",
        "unavailable",
    )


def test_cheap_and_ceiling_never_profile_inferred() -> None:
    for slot in ("cheap", "ceiling"):
        resolution = PROBE.resolve_slot(
            slot,
            cli_value=None,
            env_value=None,
            profile_worker="ollama_chat/c:1",
            profile_api_base=None,
            skipped=False,
        )
        assert resolution["status"] == "unavailable"
        assert resolution["source"] == "none"


def test_skipped_slot() -> None:
    resolution = PROBE.resolve_slot(
        "ceiling",
        cli_value="anthropic/claude-sonnet-5",
        env_value=None,
        profile_worker="x",
        profile_api_base=None,
        skipped=True,
    )
    assert resolution["status"] == "skipped"
    assert resolution["model"] is None


def test_candidate_status_classification() -> None:
    assert PROBE.classify_candidate_status(
        ["transport_error", "transport_error"]
    ) == "transport_error"
    assert PROBE.classify_candidate_status(
        ["transport_error", "raw_output_invalid"]
    ) == "ran"
    assert PROBE.classify_candidate_status(["response_loaded"]) == "ran"
    with pytest.raises(ValueError):
        PROBE.classify_candidate_status([])


def test_attempt_metrics_pair() -> None:
    loaded_passed = {"adapter_status": "response_loaded", "evaluation_passed": True}
    loaded_failed = {"adapter_status": "response_loaded", "evaluation_passed": False}
    invalid = {"adapter_status": "raw_output_invalid", "evaluation_passed": None}
    assert PROBE.attempt_metrics(loaded_passed) == (True, True)
    assert PROBE.attempt_metrics(loaded_failed) == (True, False)
    assert PROBE.attempt_metrics(invalid) == (False, False)
