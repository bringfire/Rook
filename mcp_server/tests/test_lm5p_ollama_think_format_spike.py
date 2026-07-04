from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm5p_ollama_think_format_spike.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm5p_ollama_think_format_spike", path
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


SPIKE = _load_script()


def test_constants_and_modes_are_pinned() -> None:
    assert SPIKE.DEFAULT_MODELS == ("gemma4:12b-it-qat",)
    assert SPIKE.DEFAULT_ATTEMPTS == 1
    assert SPIKE.SCENARIO_NAMES == (
        "evidence_absent_like",
        "evidence_present_like",
    )
    assert SPIKE._MODES == {
        "free_default": {"format": False, "think": "omitted"},
        "free_think_true": {"format": False, "think": True},
        "format_default": {"format": True, "think": "omitted"},
        "format_think_true": {"format": True, "think": True},
        "format_think_false": {"format": True, "think": False},
    }


def test_args_custom_model_replaces_defaults() -> None:
    args = SPIKE._args(["--model", "custom:model"])
    assert args.models == ["custom:model"]


def test_args_gemma_challenger_remains_explicitly_selectable() -> None:
    args = SPIKE._args(["--model", "gemma4:12b"])
    assert args.models == ["gemma4:12b"]


def test_args_no_model_uses_default_models() -> None:
    args = SPIKE._args([])
    assert args.models == list(SPIKE.DEFAULT_MODELS)
    assert args.models is not SPIKE.DEFAULT_MODELS
    assert args.scenarios == list(SPIKE.SCENARIO_NAMES)
    assert args.modes == list(SPIKE._MODES)


def test_args_default_excerpt_chars() -> None:
    args = SPIKE._args([])

    assert args.excerpt_chars == SPIKE.EXCERPT_CHARS


def test_args_custom_excerpt_chars() -> None:
    args = SPIKE._args(["--excerpt-chars", "1200"])

    assert args.excerpt_chars == 1200


def test_args_invalid_excerpt_chars_fails_during_parse() -> None:
    with pytest.raises(SystemExit):
        SPIKE._args(["--excerpt-chars", "0"])


def test_args_invalid_scenario_fails_during_parse() -> None:
    with pytest.raises(SystemExit):
        SPIKE._args(["--scenario", "bad"])


def test_args_invalid_mode_fails_during_parse() -> None:
    with pytest.raises(SystemExit):
        SPIKE._args(["--mode", "bad"])


def test_response_union_schema_root_and_variants() -> None:
    schema = SPIKE._response_union_schema()
    assert set(schema) == {"oneOf"}
    variants = schema["oneOf"]
    assert len(variants) == 4
    assert [variant["properties"]["kind"]["const"] for variant in variants] == [
        "action_request",
        "clarification_request",
        "refusal",
        "observation",
    ]

    for variant in variants:
        assert variant["type"] == "object"
        assert variant["additionalProperties"] is False
        assert (
            variant["properties"]["schema"]["const"]
            == "rook.local_worker_turn_response:v1"
        )


def test_response_union_schema_lm5g_field_shapes() -> None:
    variants = {
        variant["properties"]["kind"]["const"]: variant
        for variant in SPIKE._response_union_schema()["oneOf"]
    }

    action = variants["action_request"]
    assert action["required"] == [
        "schema",
        "kind",
        "action_id",
        "rationale",
        "input",
    ]
    assert action["properties"]["input"]["type"] == "object"

    clarification = variants["clarification_request"]
    assert clarification["required"] == [
        "schema",
        "kind",
        "question",
        "rationale",
    ]
    assert clarification["properties"]["rationale"]["type"] == ["string", "null"]

    refusal = variants["refusal"]
    assert refusal["required"] == ["schema", "kind", "category", "reason"]
    assert refusal["properties"]["category"]["enum"] == [
        "unsafe",
        "insufficient_context",
        "unsupported_action",
        "out_of_scope",
    ]

    observation = variants["observation"]
    assert observation["required"] == ["schema", "kind", "message", "data"]
    assert observation["properties"]["data"]["type"] == ["object", "null"]


def test_build_request_body_free_default_omits_format_and_think() -> None:
    messages = [{"role": "user", "content": "hello"}]
    body = SPIKE._build_request_body(
        "gemma4:12b-it-qat", messages, "free_default", 0
    )
    assert body == {
        "model": "gemma4:12b-it-qat",
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0},
    }
    assert "format" not in body
    assert "think" not in body


def test_build_request_body_free_think_true_sets_think_and_no_format() -> None:
    body = SPIKE._build_request_body(
        "gemma4:12b-it-qat",
        [{"role": "user", "content": "hello"}],
        "free_think_true",
        0,
    )
    assert body["think"] is True
    assert "format" not in body


def test_build_request_body_format_think_false_includes_fresh_schema() -> None:
    messages = [{"role": "user", "content": "hello"}]
    body = SPIKE._build_request_body(
        "gemma4:12b-it-qat", messages, "format_think_false", 0
    )
    second = SPIKE._build_request_body(
        "gemma4:12b-it-qat", messages, "format_think_false", 0
    )
    assert body["think"] is False
    assert body["format"] == SPIKE._response_union_schema()
    assert body["format"] is not second["format"]
    body["format"]["oneOf"][0]["properties"]["input"]["type"] = "mutated"
    assert second["format"]["oneOf"][0]["properties"]["input"]["type"] == "object"


def test_build_request_body_unknown_mode_raises() -> None:
    with pytest.raises(ValueError, match="unknown LM5P mode"):
        SPIKE._build_request_body(
            "gemma4:12b-it-qat",
            [{"role": "user", "content": "hello"}],
            "missing",
            0,
        )


def _request_envelope_for_scenario(name: str) -> dict:
    messages = SPIKE._messages_for_scenario(name)
    assert [message["role"] for message in messages] == ["system", "user"]
    return json.loads(messages[1]["content"])


def test_messages_for_evidence_absent_like_renders_real_lm5j_prompt() -> None:
    envelope = _request_envelope_for_scenario("evidence_absent_like")

    assert envelope["schema"] == "rook.local_worker_turn_request:v1"
    context = envelope["context"]
    assert context["current_node"]["node_id"] == "repair_same_component"
    assert [packet["packet_id"] for packet in context["knowledge"]] == [
        "script_body_gotcha"
    ]
    assert context["current_node"]["has_execution_params"] is False


def test_messages_for_evidence_present_like_adds_evidence_packet() -> None:
    envelope = _request_envelope_for_scenario("evidence_present_like")

    packets = envelope["context"]["knowledge"]
    assert [packet["packet_id"] for packet in packets] == [
        "script_body_gotcha",
        "lm5n_repair_evidence",
    ]
    evidence = packets[1]
    assert evidence["kind"] == "evidence"
    assert evidence["content"]["state"] == "post_verify_pre_bind"


def test_messages_for_unknown_scenario_raises() -> None:
    with pytest.raises(ValueError, match="unknown LM5P scenario"):
        SPIKE._messages_for_scenario("missing")


def test_excerpt_and_sha256_text_handle_text_and_none() -> None:
    text = "abcdef" * 120

    assert SPIKE._excerpt(text) == text[:500]
    assert (
        SPIKE._sha256_text(text)
        == "a774b01707c1f8c098d7f16731417bc41f269298ffb4a896b716ce5829c8ce7d"
    )
    assert SPIKE._excerpt(None) is None
    assert SPIKE._sha256_text(None) is None


def test_excerpt_uses_configured_limit() -> None:
    text = "abcdef" * 120

    assert SPIKE._excerpt(text, 12) == "abcdefabcdef"
    assert SPIKE._excerpt(None, 12) is None


def test_classifies_lm5g_loadable_response_with_thinking() -> None:
    content = json.dumps(
        {
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "clarification_request",
            "question": "Which curve should I use?",
            "rationale": "Need a target curve before editing.",
        }
    )
    thinking = "checking contract"
    provider_text = json.dumps(
        {
            "message": {
                "content": content,
                "thinking": thinking,
            },
            "prompt_eval_count": 123,
            "eval_count": 45,
            "total_duration": 1000,
            "load_duration": 200,
            "prompt_eval_duration": 300,
            "eval_duration": 400,
            "done_reason": "stop",
        }
    )

    row = SPIKE._classify_provider_text(provider_text, {"scenario": "demo"})

    assert row["scenario"] == "demo"
    assert row["provider_status"] == "ok"
    assert row["provider_json_valid"] is True
    assert row["content_json_valid"] is True
    assert row["content_is_mapping"] is True
    assert row["schema_literal"] == "rook.local_worker_turn_response:v1"
    assert row["lm5g_loadable"] is True
    assert row["response_kind"] == "clarification_request"
    assert row["thinking_present"] is True
    assert row["thinking_chars"] == len(thinking)
    assert row["prompt_eval_count"] == 123
    assert row["eval_count"] == 45
    assert row["total_duration"] == 1000
    assert row["load_duration"] == 200
    assert row["prompt_eval_duration"] == 300
    assert row["eval_duration"] == 400
    assert row["done_reason"] == "stop"
    assert row["failure_reason"] is None


def test_classifies_provider_text_uses_configured_excerpt_chars() -> None:
    content = json.dumps(
        {
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "observation",
            "message": "x" * 80,
            "data": None,
        }
    )
    thinking = "thinking-" * 20
    provider_text = json.dumps(
        {
            "message": {
                "content": content,
                "thinking": thinking,
            }
        }
    )

    row = SPIKE._classify_provider_text(
        provider_text,
        {"scenario": "demo"},
        excerpt_chars=40,
    )

    assert row["message_content_excerpt"] == content[:40]
    assert row["thinking_excerpt"] == thinking[:40]


def test_classifies_provider_json_parse_failure() -> None:
    row = SPIKE._classify_provider_text("{not json", {})

    assert row["provider_status"] == "error"
    assert row["provider_json_valid"] is False
    assert row["failure_reason"] == "provider_json_invalid:JSONDecodeError"


def test_classifies_missing_message_preserves_provider_telemetry() -> None:
    provider_text = json.dumps(
        {
            "done_reason": "stop",
            "total_duration": 123,
            "eval_count": 45,
        }
    )

    row = SPIKE._classify_provider_text(provider_text, {})

    assert row["provider_status"] == "ok"
    assert row["provider_json_valid"] is True
    assert row["done_reason"] == "stop"
    assert row["total_duration"] == 123
    assert row["eval_count"] == 45
    assert row["failure_reason"] == "message_missing"


def test_classifies_free_text_content_as_row_evidence() -> None:
    provider_text = json.dumps({"message": {"content": "not json"}})

    row = SPIKE._classify_provider_text(provider_text, {})

    assert row["provider_status"] == "ok"
    assert row["provider_json_valid"] is True
    assert row["content_json_valid"] is False
    assert row["lm5g_loadable"] is False
    assert row["failure_reason"] == "content_json_invalid:JSONDecodeError"


def test_parse_show_metadata_extracts_model_id_and_quantization() -> None:
    text = """
architecture        gemma3
quantization        Q4_K_M
model id            abcdef123456
"""

    assert SPIKE._parse_show_metadata(text) == {
        "model_id": "abcdef123456",
        "model_quantization": "Q4_K_M",
    }


def test_build_manifest_records_run_contract_and_model_metadata() -> None:
    models = [
        {
            "model": "gemma4:12b",
            "model_id": "abcdef123456",
            "model_quantization": "Q4_K_M",
            "ollama_show_status": "ok",
            "ollama_show_excerpt": "quantization        Q4_K_M",
        }
    ]

    manifest = SPIKE._build_manifest(
        git_commit="abc1234",
        ollama_version="ollama version is 0.9.0",
        models=models,
        scenarios=["evidence_absent_like", "evidence_present_like"],
        modes=list(SPIKE._MODES),
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        attempts_per_cell=3,
    )

    assert manifest["script_schema"] == "rook.lm5p_ollama_think_format_spike:v1"
    assert manifest["git_commit"] == "abc1234"
    assert manifest["models"] == models
    assert manifest["scenarios"] == [
        "evidence_absent_like",
        "evidence_present_like",
    ]
    assert manifest["modes"] == list(SPIKE._MODES)
    assert (
        manifest["raw_artifacts"] == "local evidence under probe_runs; do not commit"
    )


def _summary_row(
    *,
    model: str = "gemma4:12b-it-qat",
    scenario: str = "evidence_absent_like",
    mode: str = "format_default",
    provider_status: str = "ok",
    lm5g_loadable: bool = True,
    response_kind: str | None = "action_request",
    thinking_present: bool = True,
    thinking_sha256: str | None = "think-a",
    thinking_chars: int = 100,
    message_content_sha256: str | None = "content-a",
    failure_reason: str | None = None,
) -> dict:
    return {
        "model": model,
        "scenario": scenario,
        "mode": mode,
        "provider_status": provider_status,
        "lm5g_loadable": lm5g_loadable,
        "response_kind": response_kind,
        "thinking_present": thinking_present,
        "thinking_sha256": thinking_sha256,
        "thinking_chars": thinking_chars,
        "message_content_sha256": message_content_sha256,
        "failure_reason": failure_reason,
    }


def test_build_summary_groups_rows_by_model_scenario_mode() -> None:
    rows = [
        _summary_row(
            mode="format_default",
            response_kind="action_request",
            thinking_sha256="think-a",
            message_content_sha256="content-a",
        ),
        _summary_row(
            mode="format_default",
            provider_status="error",
            lm5g_loadable=False,
            response_kind=None,
            thinking_present=False,
            thinking_sha256=None,
            message_content_sha256=None,
            failure_reason="provider_error:TimeoutError",
        ),
        _summary_row(
            mode="free_think_true",
            lm5g_loadable=False,
            response_kind="clarification_request",
            thinking_sha256="think-b",
            message_content_sha256="content-b",
            failure_reason="lm5g_load_failed:ValueError",
        ),
    ]

    summary = SPIKE._build_summary(
        run_id="lm5p-demo",
        git_commit="abc1234",
        models=["gemma4:12b-it-qat"],
        scenarios=["evidence_absent_like"],
        modes=["free_think_true", "format_default"],
        attempts_per_cell=5,
        rows=rows,
    )

    assert summary["run_id"] == "lm5p-demo"
    assert summary["git_commit"] == "abc1234"
    assert summary["models"] == ["gemma4:12b-it-qat"]
    assert summary["scenarios"] == ["evidence_absent_like"]
    assert summary["modes"] == ["free_think_true", "format_default"]
    assert summary["attempts_per_cell"] == 5
    assert summary["groups"] == [
        {
            "model": "gemma4:12b-it-qat",
            "scenario": "evidence_absent_like",
            "mode": "free_think_true",
            "attempts": 1,
            "provider_errors": 0,
            "lm5g_loadable_count": 0,
            "response_kind_counts": {"clarification_request": 1},
            "thinking_present_count": 1,
            "unique_thinking_hash_count": 1,
            "unique_content_hash_count": 1,
            "failure_reason_counts": {"lm5g_load_failed:ValueError": 1},
        },
        {
            "model": "gemma4:12b-it-qat",
            "scenario": "evidence_absent_like",
            "mode": "format_default",
            "attempts": 2,
            "provider_errors": 1,
            "lm5g_loadable_count": 1,
            "response_kind_counts": {"action_request": 1},
            "thinking_present_count": 1,
            "unique_thinking_hash_count": 1,
            "unique_content_hash_count": 1,
            "failure_reason_counts": {"provider_error:TimeoutError": 1},
        },
    ]


def test_build_summary_groups_exact_thinking_hashes_across_modes() -> None:
    rows = [
        _summary_row(
            mode="free_think_true",
            lm5g_loadable=False,
            response_kind="clarification_request",
            thinking_sha256="shared-think",
            thinking_chars=3361,
            failure_reason="lm5g_load_failed:ValueError",
        ),
        _summary_row(
            mode="format_default",
            lm5g_loadable=True,
            response_kind="action_request",
            thinking_sha256="shared-think",
            thinking_chars=3361,
            failure_reason=None,
        ),
        _summary_row(
            mode="format_think_true",
            lm5g_loadable=True,
            response_kind="action_request",
            thinking_sha256="shared-think",
            thinking_chars=3361,
            failure_reason=None,
        ),
        _summary_row(
            mode="format_think_false",
            lm5g_loadable=True,
            response_kind="clarification_request",
            thinking_present=False,
            thinking_sha256=None,
            thinking_chars=0,
            failure_reason=None,
        ),
    ]

    summary = SPIKE._build_summary(
        run_id="lm5p-demo",
        git_commit="abc1234",
        models=["gemma4:12b-it-qat"],
        scenarios=["evidence_absent_like"],
        modes=[
            "free_think_true",
            "format_default",
            "format_think_true",
            "format_think_false",
        ],
        attempts_per_cell=5,
        rows=rows,
    )

    assert summary["thinking_hash_groups"] == [
        {
            "model": "gemma4:12b-it-qat",
            "scenario": "evidence_absent_like",
            "thinking_sha256": "shared-think",
            "thinking_chars": 3361,
            "attempts": 3,
            "modes": [
                "free_think_true",
                "format_default",
                "format_think_true",
            ],
            "response_kind_counts": {
                "action_request": 2,
                "clarification_request": 1,
            },
            "lm5g_loadable_count": 2,
            "failure_reason_counts": {"lm5g_load_failed:ValueError": 1},
        }
    ]


def test_run_matrix_writes_manifest_and_attempt_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured_bodies: list[dict] = []
    content = json.dumps(
        {
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "observation",
            "message": "ok",
            "data": {"source": "fake"},
        }
    )
    provider_text = json.dumps({"message": {"content": content}})

    def fake_post(endpoint: str, body: dict, timeout_s: float) -> str:
        assert endpoint == "http://fake.local/api/chat"
        assert timeout_s == 9
        captured_bodies.append(body)
        return provider_text

    monkeypatch.setattr(SPIKE, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(SPIKE, "_git_short_sha", lambda: "abc1234")
    monkeypatch.setattr(SPIKE, "_ollama_version", lambda: "ollama version is 0.9.0")
    monkeypatch.setattr(
        SPIKE,
        "_model_metadata",
        lambda model: {
            "model": model,
            "model_id": "model-123",
            "model_quantization": "Q4_K_M",
            "ollama_show_status": "ok",
            "ollama_show_excerpt": "model id            model-123",
        },
    )
    monkeypatch.setattr(
        SPIKE,
        "_messages_for_scenario",
        lambda scenario: [{"role": "user", "content": scenario}],
    )
    monkeypatch.setattr(SPIKE, "_post_ollama_chat", fake_post)

    run_dir = SPIKE._run_matrix(
        models=["gemma4:12b"],
        scenarios=["evidence_absent_like"],
        modes=["format_think_true"],
        endpoint="http://fake.local/api/chat",
        temperature=0,
        attempts_per_cell=2,
        timeout_s=9,
        excerpt_chars=SPIKE.EXCERPT_CHARS,
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["git_commit"] == "abc1234"
    assert manifest["models"] == [
        {
            "model": "gemma4:12b",
            "model_id": "model-123",
            "model_quantization": "Q4_K_M",
            "ollama_show_status": "ok",
            "ollama_show_excerpt": "model id            model-123",
        }
    ]

    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 2
    first = rows[0]
    assert first["model"] == "gemma4:12b"
    assert first["mode"] == "format_think_true"
    assert first["format_enabled"] is True
    assert first["think_requested"] == "true"
    assert first["lm5g_loadable"] is True
    assert first["response_kind"] == "observation"

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["run_id"] == run_dir.name
    assert summary["git_commit"] == "abc1234"
    assert summary["models"] == ["gemma4:12b"]
    assert summary["scenarios"] == ["evidence_absent_like"]
    assert summary["modes"] == ["format_think_true"]
    assert summary["attempts_per_cell"] == 2
    assert summary["groups"] == [
        {
            "model": "gemma4:12b",
            "scenario": "evidence_absent_like",
            "mode": "format_think_true",
            "attempts": 2,
            "provider_errors": 0,
            "lm5g_loadable_count": 2,
            "response_kind_counts": {"observation": 2},
            "thinking_present_count": 0,
            "unique_thinking_hash_count": 0,
            "unique_content_hash_count": 1,
            "failure_reason_counts": {},
        }
    ]
    assert summary["thinking_hash_groups"] == []

    assert len(captured_bodies) == 2
    assert "oneOf" in captured_bodies[0]["format"]
    assert captured_bodies[0]["think"] is True


def test_run_matrix_records_http_and_provider_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = 0

    def fake_post(endpoint: str, body: dict, timeout_s: float) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.HTTPError(endpoint, 503, "unavailable", {}, None)
        raise RuntimeError("boom")

    monkeypatch.setattr(SPIKE, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(SPIKE, "_git_short_sha", lambda: "abc1234")
    monkeypatch.setattr(SPIKE, "_ollama_version", lambda: "ollama version is 0.9.0")
    monkeypatch.setattr(
        SPIKE,
        "_model_metadata",
        lambda model: {
            "model": model,
            "model_id": None,
            "model_quantization": None,
            "ollama_show_status": "ok",
            "ollama_show_excerpt": "",
        },
    )
    monkeypatch.setattr(
        SPIKE,
        "_messages_for_scenario",
        lambda scenario: [{"role": "user", "content": scenario}],
    )
    monkeypatch.setattr(SPIKE, "_post_ollama_chat", fake_post)

    run_dir = SPIKE._run_matrix(
        models=["gemma4:12b"],
        scenarios=["evidence_absent_like"],
        modes=["free_default"],
        endpoint="http://fake.local/api/chat",
        temperature=0,
        attempts_per_cell=2,
        timeout_s=9,
        excerpt_chars=SPIKE.EXCERPT_CHARS,
    )

    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert [row["provider_status"] for row in rows] == ["error", "error"]
    assert [row["failure_reason"] for row in rows] == [
        "http_error:503",
        "provider_error:RuntimeError",
    ]


def test_run_matrix_propagates_summary_write_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider_text = json.dumps({"message": {"content": "not json"}})
    original_write_json_file = SPIKE._write_json_file

    def fake_write_json_file(path: Path, payload: dict) -> None:
        if path.name == "summary.json":
            raise RuntimeError("summary write failed")
        original_write_json_file(path, payload)

    monkeypatch.setattr(SPIKE, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(SPIKE, "_git_short_sha", lambda: "abc1234")
    monkeypatch.setattr(SPIKE, "_ollama_version", lambda: "ollama version is 0.9.0")
    monkeypatch.setattr(
        SPIKE,
        "_model_metadata",
        lambda model: {
            "model": model,
            "model_id": None,
            "model_quantization": None,
            "ollama_show_status": "ok",
            "ollama_show_excerpt": "",
        },
    )
    monkeypatch.setattr(
        SPIKE,
        "_messages_for_scenario",
        lambda scenario: [{"role": "user", "content": scenario}],
    )
    monkeypatch.setattr(
        SPIKE,
        "_post_ollama_chat",
        lambda endpoint, body, timeout_s: provider_text,
    )
    monkeypatch.setattr(SPIKE, "_write_json_file", fake_write_json_file)

    with pytest.raises(RuntimeError, match="summary write failed"):
        SPIKE._run_matrix(
            models=["gemma4:12b"],
            scenarios=["evidence_absent_like"],
            modes=["free_think_true"],
            endpoint="http://fake.local/api/chat",
            temperature=0,
            attempts_per_cell=1,
            timeout_s=9,
            excerpt_chars=SPIKE.EXCERPT_CHARS,
        )


def test_script_help_runs_from_repo_root() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    python = repo_root / "mcp_server" / ".venv" / "Scripts" / "python.exe"
    result = subprocess.run(
        [str(python), "scripts/lm5p_ollama_think_format_spike.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "LM5P Ollama think/format diagnostic spike scaffold." in result.stdout


def test_script_static_import_and_call_guards() -> None:
    tree = ast.parse(_script_path().read_text(encoding="utf-8"))
    forbidden_modules = {"requests", "httpx", "ollama", "litellm"}
    forbidden_names = {
        "run_probe",
        "run_candidate",
        "_default_transport_factory",
        "LiteLLMWorkerTransport",
        "run_local_worker_adapter",
        "run_local_worker_turn",
        "evaluate_local_worker_scenario_result",
    }

    imported_modules: set[str] = set()
    imported_names: set[str] = set()
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name.split(".", 1)[0])
                imported_names.add(alias.asname or alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module.split(".", 1)[0])
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                called_names.add(func.attr)

    assert imported_modules.isdisjoint(forbidden_modules)
    assert imported_names.isdisjoint(forbidden_names)
    assert called_names.isdisjoint(forbidden_names)
    assert {"_SCENARIOS", "build_probe_context"} <= imported_names
