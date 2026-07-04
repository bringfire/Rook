#!/usr/bin/env python
"""LM5P direct Ollama think/format diagnostic spike.

Manual live diagnostic only. It renders real LM5N prompt envelopes, calls
Ollama's local /api/chat endpoint with selected think/format modes, and writes
bounded local evidence under probe_runs/.
"""

from __future__ import annotations

import argparse
import hashlib
import copy
import subprocess
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _path in (str(_SCRIPT_DIR), str(_REPO_ROOT), str(_MCP_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from rook.agent.local_worker_prompt_artifact import (
    render_local_worker_prompt_artifact,
)
from rook.agent.local_worker_turn_response import (
    load_local_worker_turn_response_payload,
)
from rook.agent.local_worker_turn_request import (
    render_local_worker_turn_request_payload,
)
from lm5k_worker_probe import _SCENARIOS, build_probe_context

SCRIPT_SCHEMA = "rook.lm5p_ollama_think_format_spike:v1"
DEFAULT_MODELS = ("gemma4:12b-it-qat",)
SCENARIO_NAMES = ("evidence_absent_like", "evidence_present_like")
DEFAULT_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_ATTEMPTS = 1
DEFAULT_TEMPERATURE = 0
DEFAULT_TIMEOUT_S = 120
EXCERPT_CHARS = 500

_MODES = {
    "free_default": {"format": False, "think": "omitted"},
    "free_think_true": {"format": False, "think": True},
    "format_default": {"format": True, "think": "omitted"},
    "format_think_true": {"format": True, "think": True},
    "format_think_false": {"format": True, "think": False},
}

_SCENARIO_MAP = {
    "evidence_absent_like": "evidence_absent",
    "evidence_present_like": "evidence_present",
}


def _response_union_schema() -> dict[str, Any]:
    def schema_prop() -> dict[str, str]:
        return {"const": "rook.local_worker_turn_response:v1"}

    return {
        "oneOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema", "kind", "action_id", "rationale", "input"],
                "properties": {
                    "schema": schema_prop(),
                    "kind": {"const": "action_request"},
                    "action_id": {"type": "string"},
                    "rationale": {"type": "string"},
                    "input": {"type": "object"},
                },
            },
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema", "kind", "question", "rationale"],
                "properties": {
                    "schema": schema_prop(),
                    "kind": {"const": "clarification_request"},
                    "question": {"type": "string"},
                    "rationale": {"type": ["string", "null"]},
                },
            },
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema", "kind", "category", "reason"],
                "properties": {
                    "schema": schema_prop(),
                    "kind": {"const": "refusal"},
                    "category": {
                        "enum": [
                            "unsafe",
                            "insufficient_context",
                            "unsupported_action",
                            "out_of_scope",
                        ]
                    },
                    "reason": {"type": "string"},
                },
            },
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema", "kind", "message", "data"],
                "properties": {
                    "schema": schema_prop(),
                    "kind": {"const": "observation"},
                    "message": {"type": "string"},
                    "data": {"type": ["object", "null"]},
                },
            },
        ]
    }


def _build_request_body(
    model: str,
    messages: list[dict[str, Any]],
    mode_name: str,
    temperature: float,
) -> dict[str, Any]:
    try:
        mode = _MODES[mode_name]
    except KeyError as exc:
        raise ValueError(f"unknown LM5P mode: {mode_name}") from exc

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if mode["format"]:
        body["format"] = copy.deepcopy(_response_union_schema())
    if mode["think"] != "omitted":
        body["think"] = mode["think"]
    return body


def _messages_for_scenario(scenario_name: str) -> list[dict[str, str]]:
    try:
        probe_scenario_name = _SCENARIO_MAP[scenario_name]
    except KeyError as exc:
        raise ValueError(f"unknown LM5P scenario: {scenario_name}") from exc

    context = build_probe_context(_SCENARIOS[probe_scenario_name])
    request_payload = render_local_worker_turn_request_payload(context)
    prompt_artifact = render_local_worker_prompt_artifact(request_payload)
    return [dict(message) for message in prompt_artifact["messages"]]


def _excerpt(value: str | None) -> str | None:
    if value is None:
        return None
    return value[:EXCERPT_CHARS]


def _sha256_text(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _empty_result_fields() -> dict[str, Any]:
    return {
        "provider_status": "ok",
        "provider_json_valid": False,
        "content_json_valid": False,
        "content_is_mapping": False,
        "schema_literal": None,
        "lm5g_loadable": False,
        "response_kind": None,
        "message_content_excerpt": None,
        "message_content_sha256": None,
        "thinking_present": False,
        "thinking_chars": 0,
        "thinking_excerpt": None,
        "thinking_sha256": None,
        "prompt_eval_count": None,
        "eval_count": None,
        "total_duration": None,
        "load_duration": None,
        "prompt_eval_duration": None,
        "eval_duration": None,
        "done_reason": None,
        "failure_reason": None,
    }


def _classify_provider_text(
    provider_text: str,
    base_row: Mapping[str, Any],
) -> dict[str, Any]:
    row = {**base_row, **_empty_result_fields()}
    try:
        provider_payload = json.loads(provider_text)
    except json.JSONDecodeError as exc:
        row["provider_status"] = "error"
        row["provider_json_valid"] = False
        row["failure_reason"] = f"provider_json_invalid:{type(exc).__name__}"
        return row

    if not isinstance(provider_payload, Mapping):
        row["provider_status"] = "error"
        row["provider_json_valid"] = False
        row["failure_reason"] = "provider_json_invalid:not_mapping"
        return row

    row["provider_json_valid"] = True
    for key in (
        "prompt_eval_count",
        "eval_count",
        "total_duration",
        "load_duration",
        "prompt_eval_duration",
        "eval_duration",
        "done_reason",
    ):
        row[key] = provider_payload.get(key)

    message = provider_payload.get("message")
    if not isinstance(message, Mapping):
        row["failure_reason"] = "message_missing"
        return row

    content = message.get("content")
    if isinstance(content, str):
        row["message_content_excerpt"] = _excerpt(content)
        row["message_content_sha256"] = _sha256_text(content)

    thinking = message.get("thinking")
    if isinstance(thinking, str) and thinking:
        row["thinking_present"] = True
        row["thinking_chars"] = len(thinking)
        row["thinking_excerpt"] = _excerpt(thinking)
        row["thinking_sha256"] = _sha256_text(thinking)

    if not isinstance(content, str) or not content:
        row["failure_reason"] = "content_missing"
        return row

    try:
        parsed_content = json.loads(content)
    except json.JSONDecodeError as exc:
        row["content_json_valid"] = False
        row["failure_reason"] = f"content_json_invalid:{type(exc).__name__}"
        return row

    row["content_json_valid"] = True
    row["content_is_mapping"] = isinstance(parsed_content, Mapping)
    if not isinstance(parsed_content, Mapping):
        row["failure_reason"] = "content_json_not_mapping"
        return row

    schema_literal = parsed_content.get("schema")
    row["schema_literal"] = schema_literal if isinstance(schema_literal, str) else None
    response_kind = parsed_content.get("kind")
    row["response_kind"] = response_kind if isinstance(response_kind, str) else None

    try:
        load_local_worker_turn_response_payload(parsed_content)
    except (TypeError, ValueError) as exc:
        row["failure_reason"] = f"lm5g_load_failed:{type(exc).__name__}"
        return row

    row["lm5g_loadable"] = True
    row["failure_reason"] = None
    return row


def _git_short_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    value = result.stdout.strip()
    return value or "unknown"


def _ollama_version() -> str:
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return f"unavailable:{type(exc).__name__}"
    if result.returncode != 0:
        return "unknown"
    value = result.stdout.strip() or result.stderr.strip()
    return value or "unknown"


def _extract_labeled_value(text: str, labels: tuple[str, ...]) -> str | None:
    normalized_labels = tuple(label.casefold() for label in labels)
    for line in text.splitlines():
        stripped = line.strip()
        folded = stripped.casefold()
        for label, folded_label in zip(labels, normalized_labels):
            if folded.startswith(folded_label):
                value = stripped[len(label) :].strip()
                if value:
                    return value
    return None


def _parse_show_metadata(text: str) -> dict[str, str | None]:
    return {
        "model_id": _extract_labeled_value(text, ("model id",)),
        "model_quantization": _extract_labeled_value(text, ("quantization",)),
    }


def _model_metadata(model: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["ollama", "show", model],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return {
            "model": model,
            "model_id": None,
            "model_quantization": None,
            "ollama_show_status": f"unavailable:{type(exc).__name__}",
            "ollama_show_excerpt": None,
        }

    text = result.stdout if result.stdout else result.stderr
    parsed = _parse_show_metadata(text)
    status = "ok" if result.returncode == 0 else f"error:{result.returncode}"
    return {
        "model": model,
        **parsed,
        "ollama_show_status": status,
        "ollama_show_excerpt": _excerpt(text),
    }


def _post_ollama_chat(endpoint: str, body: dict[str, Any], timeout_s: float) -> str:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return response.read().decode("utf-8")


def _build_manifest(
    *,
    git_commit: str,
    ollama_version: str,
    models: list[dict[str, Any]],
    scenarios: list[str],
    modes: list[str],
    endpoint: str,
    temperature: float,
    attempts_per_cell: int,
) -> dict[str, Any]:
    return {
        "script_schema": SCRIPT_SCHEMA,
        "git_commit": git_commit,
        "ollama_version": ollama_version,
        "models": models,
        "scenarios": scenarios,
        "modes": modes,
        "endpoint": endpoint,
        "temperature": temperature,
        "attempts_per_cell": attempts_per_cell,
        "raw_artifacts": "local evidence under probe_runs; do not commit",
    }


def _base_row(
    *,
    model: str,
    scenario: str,
    mode: str,
    attempt: int,
) -> dict[str, Any]:
    try:
        mode_config = _MODES[mode]
    except KeyError as exc:
        raise ValueError(f"unknown LM5P mode: {mode}") from exc
    think = mode_config["think"]
    if think == "omitted":
        think_requested = "omitted"
    elif think is True:
        think_requested = "true"
    else:
        think_requested = "false"
    return {
        "model": model,
        "scenario": scenario,
        "mode": mode,
        "attempt": attempt,
        "format_enabled": bool(mode_config["format"]),
        "think_requested": think_requested,
    }


def _run_matrix(
    *,
    models: list[str],
    scenarios: list[str],
    modes: list[str],
    endpoint: str,
    temperature: float,
    attempts_per_cell: int,
    timeout_s: float,
) -> Path:
    git_commit = _git_short_sha()
    model_metadata = [_model_metadata(model) for model in models]
    manifest = _build_manifest(
        git_commit=git_commit,
        ollama_version=_ollama_version(),
        models=model_metadata,
        scenarios=scenarios,
        modes=modes,
        endpoint=endpoint,
        temperature=temperature,
        attempts_per_cell=attempts_per_cell,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = _REPO_ROOT / "probe_runs" / f"lm5p-{timestamp}-{git_commit}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    counts = {"ok": 0, "error": 0, "loadable": 0}
    attempts_path = run_dir / "attempts.jsonl"
    with attempts_path.open("w", encoding="utf-8") as attempts_file:
        for model in models:
            for scenario in scenarios:
                messages = _messages_for_scenario(scenario)
                for mode in modes:
                    for attempt in range(1, attempts_per_cell + 1):
                        base_row = _base_row(
                            model=model,
                            scenario=scenario,
                            mode=mode,
                            attempt=attempt,
                        )
                        body = _build_request_body(
                            model,
                            messages,
                            mode,
                            temperature,
                        )
                        try:
                            provider_text = _post_ollama_chat(
                                endpoint,
                                body,
                                timeout_s,
                            )
                        except urllib.error.HTTPError as exc:
                            row = {**base_row, **_empty_result_fields()}
                            row["provider_status"] = "error"
                            row["failure_reason"] = f"http_error:{exc.code}"
                        except Exception as exc:
                            row = {**base_row, **_empty_result_fields()}
                            row["provider_status"] = "error"
                            row["failure_reason"] = (
                                f"provider_error:{type(exc).__name__}"
                            )
                        else:
                            row = _classify_provider_text(provider_text, base_row)

                        if row["provider_status"] == "ok":
                            counts["ok"] += 1
                        else:
                            counts["error"] += 1
                        if row["lm5g_loadable"]:
                            counts["loadable"] += 1
                        attempts_file.write(json.dumps(row, sort_keys=True) + "\n")

    print(
        "LM5P matrix complete: "
        f"run_dir={run_dir} ok={counts['ok']} "
        f"error={counts['error']} loadable={counts['loadable']}"
    )
    return run_dir


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM5P Ollama think/format diagnostic spike scaffold."
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", action="append", dest="models", default=None)
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        choices=SCENARIO_NAMES,
        default=None,
    )
    parser.add_argument(
        "--mode",
        action="append",
        dest="modes",
        choices=list(_MODES),
        default=None,
    )
    parser.add_argument("--attempts", type=_positive_int, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    args = parser.parse_args(argv)
    if args.models is None:
        args.models = list(DEFAULT_MODELS)
    if args.scenarios is None:
        args.scenarios = list(SCENARIO_NAMES)
    if args.modes is None:
        args.modes = list(_MODES)
    return args


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    _run_matrix(
        models=args.models,
        scenarios=args.scenarios,
        modes=args.modes,
        endpoint=args.endpoint,
        temperature=args.temperature,
        attempts_per_cell=args.attempts,
        timeout_s=args.timeout_s,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
