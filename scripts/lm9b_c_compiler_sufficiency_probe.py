#!/usr/bin/env python
"""Run one offline LM9B-C bounded compiler-sufficiency experiment."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _path in (_SCRIPT_DIR, _MCP_SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from lm9b_c_compiler_sufficiency_artifacts import (  # noqa: E402
    FrozenProbeInputs,
    RenderedRequest,
    load_frozen_inputs,
    render_compiler_request,
    render_evaluator_request,
    write_probe_evidence,
)
from lm9b_c_compiler_sufficiency_support import (  # noqa: E402
    CompilerSessionResult,
    EvaluatorAttemptResult,
    ObservationDecision,
    ProviderCallFailure,
    ProviderTurn,
    SessionLimits,
    classify_observation,
    run_compiler_session,
    run_evaluator_once,
)


MAX_TURNS = 6
MAX_COMPLETION_TOKENS = 16_384
PROVIDER_TIMEOUT_S = 180.0
OVERALL_DEADLINE_S = 600.0
TOKEN_STOP_THRESHOLD = 120_000
COST_STOP_THRESHOLD_USD = 10.0
EVALUATOR_MAX_COMPLETION_TOKENS = 8_192
TEMPERATURE = 0.0


@dataclass(frozen=True)
class ProbeRunResult:
    run_dir: Path
    inputs: FrozenProbeInputs
    compiler_session: CompilerSessionResult
    evaluator_result: EvaluatorAttemptResult | None
    decision: ObservationDecision


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One bounded, inert LM9B-C compiler-sufficiency probe."
    )
    parser.add_argument(
        "--compiler-model",
        default=os.environ.get("LM9B_C_COMPILER_MODEL"),
        help="LiteLLM model identifier for the compiler session.",
    )
    parser.add_argument(
        "--evaluator-model",
        default=os.environ.get("LM9B_C_EVALUATOR_MODEL"),
        help="LiteLLM model identifier for the independent evaluator.",
    )
    parser.add_argument(
        "--run-root",
        default="probe_runs",
        help="Parent directory for the immutable local evidence directory.",
    )
    parser.add_argument(
        "--fixture-dir",
        default=str(_SCRIPT_DIR / "lm9b_c_fixtures"),
    )
    parser.set_defaults(
        max_turns=MAX_TURNS,
        max_completion_tokens=MAX_COMPLETION_TOKENS,
        provider_timeout_s=PROVIDER_TIMEOUT_S,
        overall_deadline_s=OVERALL_DEADLINE_S,
        token_stop_threshold=TOKEN_STOP_THRESHOLD,
        cost_stop_threshold_usd=COST_STOP_THRESHOLD_USD,
        temperature=TEMPERATURE,
    )
    args = parser.parse_args(argv)
    if not args.compiler_model:
        parser.error("--compiler-model or LM9B_C_COMPILER_MODEL is required")
    if not args.evaluator_model:
        parser.error("--evaluator-model or LM9B_C_EVALUATOR_MODEL is required")
    return args


def _plain(value: object) -> object:
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump())
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    return str(value)


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(_plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def build_litellm_completion_request_bytes(
    *,
    model: str,
    temperature: float,
    provider_request: Mapping[str, object],
) -> bytes:
    """Project one Rook provider request to exact LiteLLM call kwargs."""

    if type(model) is not str or not model:
        raise ValueError("LiteLLM request model must be nonempty")
    if type(temperature) not in {int, float} or isinstance(temperature, bool):
        raise TypeError("LiteLLM request temperature must be numeric")
    if not isinstance(provider_request, Mapping):
        raise TypeError("Rook provider request must be a mapping")
    kwargs = {
        "model": model,
        "messages": provider_request["messages"],
        "tools": provider_request["tools"],
        "tool_choice": provider_request["tool_choice"],
        "parallel_tool_calls": False,
        "max_tokens": provider_request["max_completion_tokens"],
        "temperature": float(temperature),
        "timeout": provider_request["provider_timeout_s"],
        "stream": False,
    }
    return _json_bytes(kwargs)


def project_litellm_assistant_message(
    raw_response: bytes,
) -> dict[str, object]:
    """Derive the exact assistant projection from captured LiteLLM bytes."""

    if type(raw_response) is not bytes:
        raise TypeError("LiteLLM response bytes are required")
    try:
        response_value = json.loads(raw_response)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("LiteLLM response bytes are not valid JSON") from exc
    if _json_bytes(response_value) != raw_response:
        raise ValueError("LiteLLM response bytes are not canonical adapter evidence")
    if not isinstance(response_value, dict):
        raise ValueError("LiteLLM response is not an object")
    choices = response_value.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("LiteLLM response has no choices")
    choice = choices[0]
    if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
        raise ValueError("LiteLLM response has no assistant message")
    source_message = choice["message"]
    if source_message.get("role") != "assistant":
        raise ValueError("LiteLLM response message does not have assistant role")
    return {
        "role": source_message["role"],
        "content": source_message.get("content"),
        "tool_calls": source_message.get("tool_calls") or [],
    }


def _sanitized_provider_error(exc: Exception) -> str:
    message = str(exc)
    for name, value in os.environ.items():
        if (name.endswith("_API_KEY") or name.endswith("_TOKEN")) and value:
            message = message.replace(value, "<redacted-secret>")
    return message[:8000]


class LiteLLMProvider:
    """Small provider adapter; it exposes no retrieval or product-agent tools."""

    def __init__(self, *, model: str, temperature: float) -> None:
        self.model = model
        self.temperature = temperature

    @property
    def identity(self) -> dict[str, object]:
        return {
            "adapter": "litellm.completion",
            "model": self.model,
            "temperature": self.temperature,
            "transport_capture": "complete_litellm_objects_not_http_wire_bytes",
        }

    def __call__(self, request: dict[str, object]) -> ProviderTurn:
        import litellm

        raw_request = build_litellm_completion_request_bytes(
            model=self.model,
            temperature=self.temperature,
            provider_request=request,
        )
        kwargs = json.loads(raw_request)
        try:
            response = litellm.completion(**kwargs)
        except Exception as exc:
            failure_type = type(exc).__name__
            message = _sanitized_provider_error(exc)
            raise ProviderCallFailure(
                failure_type=failure_type,
                message=message,
                raw_request=raw_request,
                raw_error=_json_bytes(
                    {"failure_type": failure_type, "message": message}
                ),
            ) from exc
        response_value = _plain(response)
        raw_response = _json_bytes(response_value)

        def malformed_response(message: str) -> ProviderCallFailure:
            return ProviderCallFailure(
                failure_type="MalformedProviderResponse",
                message=message,
                raw_request=raw_request,
                raw_error=raw_response,
            )

        if not isinstance(response_value, dict):
            raise malformed_response("LiteLLM response is not an object")
        try:
            assistant_message = project_litellm_assistant_message(raw_response)
        except (TypeError, ValueError) as exc:
            raise malformed_response(str(exc)) from exc
        choices = response_value["choices"]
        choice = choices[0]
        usage = response_value.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        usage = dict(usage)
        try:
            usage["cost_usd"] = float(litellm.completion_cost(completion_response=response))
        except Exception:
            usage["cost_usd"] = None
        metadata = {
            **self.identity,
            "response_id": response_value.get("id"),
            "response_model": response_value.get("model"),
            "created": response_value.get("created"),
            "system_fingerprint": response_value.get("system_fingerprint"),
            "finish_reason": choice.get("finish_reason"),
        }
        return ProviderTurn(
            raw_request=raw_request,
            raw_response=raw_response,
            assistant_message=assistant_message,
            usage=usage,
            provider_metadata=metadata,
        )


def _run_id(now: datetime, git_sha: str) -> str:
    timestamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"lm9b-c-{timestamp}-{git_sha[:8]}"


def _git_short_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short=8", "HEAD"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _limits() -> SessionLimits:
    return SessionLimits(
        max_turns=MAX_TURNS,
        max_completion_tokens_per_call=MAX_COMPLETION_TOKENS,
        provider_timeout_s=PROVIDER_TIMEOUT_S,
        overall_deadline_s=OVERALL_DEADLINE_S,
        cumulative_token_stop_threshold=TOKEN_STOP_THRESHOLD,
        cumulative_cost_stop_threshold_usd=COST_STOP_THRESHOLD_USD,
    )


def run_probe(
    *,
    run_root: Path,
    fixture_dir: Path,
    compiler_provider: Callable[[dict[str, object]], ProviderTurn],
    evaluator_provider: Callable[[dict[str, object]], ProviderTurn],
    compiler_identity: Mapping[str, object],
    evaluator_identity: Mapping[str, object],
    git_sha: str,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> ProbeRunResult:
    """Execute exactly one compiler attempt and zero or one evaluator attempt."""

    inputs = load_frozen_inputs(fixture_dir)
    compiler_request = render_compiler_request(inputs)
    compiler_session = run_compiler_session(
        provider=compiler_provider,
        system_prompt=compiler_request.system_prompt.decode("utf-8"),
        user_prompt=compiler_request.user_prompt.decode("utf-8"),
        contract_index=inputs.contract_index,
        limits=_limits(),
    )

    evaluator_request: RenderedRequest | None = None
    evaluator_result: EvaluatorAttemptResult | None = None
    if (
        compiler_session.terminal_submission is not None
        and compiler_session.terminal_validation is not None
        and (
            compiler_session.terminal_submission["result_kind"]
            == "contract_insufficient"
            or compiler_session.terminal_validation.representation_contract_ok is True
        )
    ):
        evaluator_request = render_evaluator_request(
            inputs,
            compiler_session.terminal_submission,
            compiler_session.terminal_validation,
        )
        evaluator_result = run_evaluator_once(
            provider=evaluator_provider,
            system_prompt=evaluator_request.system_prompt.decode("utf-8"),
            user_prompt=evaluator_request.user_prompt.decode("utf-8"),
            evaluated_result_kind=compiler_session.terminal_submission["result_kind"],
            max_completion_tokens=EVALUATOR_MAX_COMPLETION_TOKENS,
            provider_timeout_s=PROVIDER_TIMEOUT_S,
        )
    decision = classify_observation(compiler_session, evaluator_result)

    run_id = _run_id(now(), git_sha)
    run_dir = Path(run_root) / run_id
    write_probe_evidence(
        run_dir=run_dir,
        inputs=inputs,
        compiler_request=compiler_request,
        compiler_session=compiler_session,
        evaluator_request=evaluator_request,
        evaluator_result=evaluator_result,
        decision=decision,
        run_metadata={
            "run_id": run_id,
            "git_sha": git_sha,
            "compiler": dict(compiler_identity),
            "evaluator": dict(evaluator_identity),
            "bounds": {
                "max_turns": MAX_TURNS,
                "max_completion_tokens_per_call": MAX_COMPLETION_TOKENS,
                "provider_timeout_s": PROVIDER_TIMEOUT_S,
                "overall_deadline_s": OVERALL_DEADLINE_S,
                "cumulative_token_stop_threshold": TOKEN_STOP_THRESHOLD,
                "cumulative_cost_stop_threshold_usd": COST_STOP_THRESHOLD_USD,
                "evaluator_max_completion_tokens": EVALUATOR_MAX_COMPLETION_TOKENS,
            },
            "execution_permitted": False,
        },
    )
    return ProbeRunResult(
        run_dir=run_dir,
        inputs=inputs,
        compiler_session=compiler_session,
        evaluator_result=evaluator_result,
        decision=decision,
    )


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    compiler = LiteLLMProvider(model=args.compiler_model, temperature=args.temperature)
    evaluator = LiteLLMProvider(model=args.evaluator_model, temperature=args.temperature)
    result = run_probe(
        run_root=Path(args.run_root),
        fixture_dir=Path(args.fixture_dir),
        compiler_provider=compiler,
        evaluator_provider=evaluator,
        compiler_identity=compiler.identity,
        evaluator_identity=evaluator.identity,
        git_sha=_git_short_sha(),
    )
    print(
        f"LM9B-C complete outcome={result.decision.outcome} "
        f"run_dir={result.run_dir}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = (
    "LiteLLMProvider",
    "ProbeRunResult",
    "run_probe",
)
