#!/usr/bin/env python
"""LM7C deterministic offline Planner authoring probe."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
if str(_MCP_SRC) not in sys.path:
    sys.path.insert(0, str(_MCP_SRC))

from lm7_planner_authoring_prompt_support import (  # noqa: E402
    PROBE_SCHEMA,
    INTENT_COMPLETE_BRIEF_VERSION,
    INTENT_INCOMPLETE_BRIEF_VERSION,
    INTENT_CORRECT,
    INTENT_INVENTED,
    INTENT_NOT_CLASSIFIABLE,
    INTENT_OVER_DECLARED,
    PARSE_FAILED,
    PARSE_PARSED,
    PLANNER_AUTHORING_PROMPT_VERSION,
    PROMPT_PROFILE_SHAPE_GUIDANCE_V2,
    PROMPT_PROFILE_SPARSE_V1,
    PROMPT_PROFILES,
    SCENARIOS,
    SHAPE_GUIDANCE_PROMPT_VERSION,
    SPARSE_PROMPT_VERSION,
    TEMPLATE_MENU_VERSION,
    IntentDecisionResult,
    ParseResult,
    canonical_json as _canonical_json,
    classify_intent_decision as _classify_intent_decision,
    fingerprint_json as _fingerprint_json,
    planner_authoring_prompt as _planner_authoring_prompt,
    prompt_call_payload as _prompt_call_payload,
    prompt_version as _prompt_version,
    scenario_brief as _scenario_brief,
    strict_parse_model_output as _strict_parse_model_output,
    template_menu as _template_menu,
    write_prompt_artifacts as _write_prompt_artifacts,
)
from rook.agent.workflow_validate import (  # noqa: E402
    validate_planner_worker_contract_request,
)

VALIDATION_VALID = "workflow_validate_valid"
VALIDATION_FAILED = "workflow_validate_failed"
VALIDATION_NOT_EVALUATED = "not_evaluated"

_PLACEHOLDER_PROVIDERS = {"fake", "ceiling-provider"}
_PLACEHOLDER_MODELS = {
    "fake-planner",
    "ceiling-planner-model",
}
_REJECTED_LOCAL_MODEL_PAIR = ("ollama", "gemma4:12b-it-qat")
HIDDEN_MARKER_SCAN_TERMS = (
    "PROBE_REPAIR_CODE",
    "A = 42.0",
    "A = 0.0",
    "A = 1.0",
    "BindStepSpec.base_params",
    "repair_same_component.bind.base_params",
)


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM7C deterministic offline Planner authoring probe."
    )
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--provider", default="ceiling-provider")
    parser.add_argument("--provider-command", default=None)
    parser.add_argument("--provider-timeout-s", type=float, default=120)
    parser.add_argument("--model", default="ceiling-planner-model")
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--run-dir", default="probe_runs")
    parser.add_argument("--output-excerpt-chars", type=int, default=1200)
    parser.add_argument(
        "--prompt-profile",
        choices=PROMPT_PROFILES,
        default=PROMPT_PROFILE_SPARSE_V1,
    )
    parser.add_argument("--canonical-evidence", action="store_true")
    args = parser.parse_args(argv)
    if args.attempts <= 0:
        parser.error("attempts_must_be_positive")
    if args.output_excerpt_chars < 0:
        parser.error("output_excerpt_chars_must_be_non_negative")
    return args
def _hidden_marker_matches(
    rows: Sequence[Mapping[str, Any]],
    *,
    prompt_profile: str,
) -> list[dict[str, str]]:
    artifacts: list[tuple[str, str]] = [
        (
            "prompts/planner_authoring_prompt.txt",
            _planner_authoring_prompt(prompt_profile),
        ),
        ("prompts/template_menu.json", _canonical_json(_template_menu())),
        ("prompts/intent_complete_brief.txt", _scenario_brief("intent_complete")["text"]),
        (
            "prompts/intent_incomplete_brief.txt",
            _scenario_brief("intent_incomplete")["text"],
        ),
    ]
    artifacts.extend(
        (
            f"rows[{index}].output_excerpt",
            str(row.get("output_excerpt") or ""),
        )
        for index, row in enumerate(rows)
    )

    matches: list[dict[str, str]] = []
    for artifact, text in artifacts:
        for marker in HIDDEN_MARKER_SCAN_TERMS:
            if marker in text:
                matches.append({"artifact": artifact, "marker": marker})
    return matches


def _workflow_failure_reason(report: Mapping[str, Any]) -> str:
    codes: list[str] = []
    phases = report.get("phases")
    if isinstance(phases, Mapping):
        for phase in phases.values():
            if not isinstance(phase, Mapping):
                continue
            diagnostics = phase.get("diagnostics")
            if not isinstance(diagnostics, list):
                continue
            for diagnostic in diagnostics:
                if isinstance(diagnostic, Mapping) and isinstance(
                    diagnostic.get("code"),
                    str,
                ):
                    codes.append(diagnostic["code"])
    code_summary = ",".join(codes) if codes else "unknown"
    return f"workflow_validate_failed:{code_summary}"


def _base_row(
    *,
    scenario: str,
    attempt_index: int,
    provider: str,
    model: str,
    temperature: float,
    prompt_profile: str,
    raw_output: str,
    output_excerpt_chars: int,
) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "attempt_index": attempt_index,
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "prompt_profile": prompt_profile,
        "prompt_version": _prompt_version(prompt_profile),
        "template_menu_version": TEMPLATE_MENU_VERSION,
        "brief_version": _scenario_brief(scenario)["version"],
        "parse_status": PARSE_FAILED,
        "validation_status": VALIDATION_NOT_EVALUATED,
        "intent_decision": INTENT_NOT_CLASSIFIABLE,
        "canonical_success": False,
        "request_fingerprint": None,
        "workflow_validate_report_fingerprint": None,
        "failure_reason": None,
        "output_excerpt": raw_output[:output_excerpt_chars],
        "output_sha256": _fingerprint_json(raw_output),
    }


def _score_model_output(
    *,
    scenario: str,
    attempt_index: int,
    provider: str,
    model: str,
    temperature: float,
    prompt_profile: str,
    raw_output: str,
    output_excerpt_chars: int,
) -> dict[str, Any]:
    row = _base_row(
        scenario=scenario,
        attempt_index=attempt_index,
        provider=provider,
        model=model,
        temperature=temperature,
        prompt_profile=prompt_profile,
        raw_output=raw_output,
        output_excerpt_chars=output_excerpt_chars,
    )

    parsed = _strict_parse_model_output(raw_output)
    row["parse_status"] = parsed.parse_status
    if parsed.parse_status != PARSE_PARSED or parsed.payload is None:
        row["failure_reason"] = parsed.failure_reason
        return row

    payload = parsed.payload
    report = validate_planner_worker_contract_request(payload)
    valid = report.get("valid") is True
    row["validation_status"] = VALIDATION_VALID if valid else VALIDATION_FAILED
    row["request_fingerprint"] = report.get("request_fingerprint") or _fingerprint_json(
        payload
    )
    row["workflow_validate_report_fingerprint"] = (
        report.get("report_fingerprint") or _fingerprint_json(report)
    )

    intent = _classify_intent_decision(scenario, payload)
    row["intent_decision"] = intent.intent_decision
    row["canonical_success"] = (
        row["parse_status"] == PARSE_PARSED
        and row["validation_status"] == VALIDATION_VALID
        and row["intent_decision"] == INTENT_CORRECT
    )

    if not valid and intent.intent_decision == INTENT_CORRECT:
        row["failure_reason"] = _workflow_failure_reason(report)
    elif intent.intent_decision != INTENT_CORRECT:
        row["failure_reason"] = intent.failure_reason
    else:
        row["failure_reason"] = None
    return row


def _git_short_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _new_run_dir(root: Path, sha: str | None = None) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = sha if sha is not None else _git_short_sha()
    run_dir = root / f"lm7c-{timestamp}-{suffix}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), sort_keys=True, default=str) + "\n")


def _scenario_count(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "total_rows": len(rows),
        "parse_success_count": sum(
            1 for row in rows if row.get("parse_status") == PARSE_PARSED
        ),
        "workflow_validate_valid_count": sum(
            1 for row in rows if row.get("validation_status") == VALIDATION_VALID
        ),
        "correct_intent_count": sum(
            1 for row in rows if row.get("intent_decision") == INTENT_CORRECT
        ),
        "canonical_success_count": sum(
            1 for row in rows if row.get("canonical_success") is True
        ),
        "over_declared_count": sum(
            1 for row in rows if row.get("intent_decision") == INTENT_OVER_DECLARED
        ),
        "invented_count": sum(
            1 for row in rows if row.get("intent_decision") == INTENT_INVENTED
        ),
        "not_classifiable_count": sum(
            1 for row in rows if row.get("intent_decision") == INTENT_NOT_CLASSIFIABLE
        ),
    }


def _summarize_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    attempts: int,
    provider: str,
    model: str,
    temperature: float,
    canonical_evidence: bool,
    prompt_profile: str,
) -> dict[str, Any]:
    counts = _scenario_count(rows)
    marker_matches = _hidden_marker_matches(rows, prompt_profile=prompt_profile)
    return {
        "schema": PROBE_SCHEMA,
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "prompt_profile": prompt_profile,
        "prompt_version": _prompt_version(prompt_profile),
        "scheduled_attempts_per_scenario": attempts,
        **counts,
        "scenario_counts": {
            scenario: _scenario_count(
                [row for row in rows if row.get("scenario") == scenario]
            )
            for scenario in SCENARIOS
        },
        "canonical_evidence": canonical_evidence,
        "hidden_marker_match_count": len(marker_matches),
        "hidden_marker_matches": marker_matches,
    }


def _manifest(
    *,
    provider: str,
    model: str,
    temperature: float,
    attempts: int,
    canonical_evidence: bool,
    prompt_profile: str,
) -> dict[str, Any]:
    return {
        "schema": PROBE_SCHEMA,
        "git_commit": _git_short_sha(),
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "scheduled_attempts_per_scenario": attempts,
        "scenarios": list(SCENARIOS),
        "prompt_profile": prompt_profile,
        "prompt_version": _prompt_version(prompt_profile),
        "template_menu_version": TEMPLATE_MENU_VERSION,
        "brief_versions": {
            scenario: _scenario_brief(scenario)["version"] for scenario in SCENARIOS
        },
        "canonical_evidence": canonical_evidence,
        "raw_artifacts": "local evidence under probe_runs; do not commit",
    }


def _provider_error_row(
    *,
    scenario: str,
    attempt_index: int,
    provider: str,
    model: str,
    temperature: float,
    prompt_profile: str,
    output_excerpt_chars: int,
    exc: Exception,
) -> dict[str, Any]:
    row = _base_row(
        scenario=scenario,
        attempt_index=attempt_index,
        provider=provider,
        model=model,
        temperature=temperature,
        prompt_profile=prompt_profile,
        raw_output="",
        output_excerpt_chars=output_excerpt_chars,
    )
    row["failure_reason"] = f"provider_error:{type(exc).__name__}"
    return row


def _run_probe(
    *,
    run_root: Path,
    provider: str,
    model: str,
    temperature: float,
    attempts: int,
    canonical_evidence: bool,
    output_excerpt_chars: int,
    prompt_profile: str,
    call_provider: Callable[[Mapping[str, Any]], str],
) -> Path:
    run_dir = _new_run_dir(Path(run_root))
    _write_prompt_artifacts(run_dir, prompt_profile)
    _write_json(
        run_dir / "manifest.json",
        _manifest(
            provider=provider,
            model=model,
            temperature=temperature,
            attempts=attempts,
            canonical_evidence=canonical_evidence,
            prompt_profile=prompt_profile,
        ),
    )

    rows: list[dict[str, Any]] = []
    rows_path = run_dir / "rows.jsonl"
    for scenario in SCENARIOS:
        for attempt_index in range(attempts):
            payload = _prompt_call_payload(
                scenario=scenario,
                attempt_index=attempt_index,
                provider=provider,
                model=model,
                temperature=temperature,
                prompt_profile=prompt_profile,
            )
            try:
                raw_output = call_provider(payload)
            except Exception as exc:
                row = _provider_error_row(
                    scenario=scenario,
                    attempt_index=attempt_index,
                    provider=provider,
                    model=model,
                    temperature=temperature,
                    prompt_profile=prompt_profile,
                    output_excerpt_chars=output_excerpt_chars,
                    exc=exc,
                )
            else:
                row = _score_model_output(
                    scenario=scenario,
                    attempt_index=attempt_index,
                    provider=provider,
                    model=model,
                    temperature=temperature,
                    prompt_profile=prompt_profile,
                    raw_output=raw_output,
                    output_excerpt_chars=output_excerpt_chars,
                )
            rows.append(row)
            _append_jsonl(rows_path, row)

    _write_json(
        run_dir / "summary.json",
        _summarize_rows(
            rows,
            attempts=attempts,
            provider=provider,
            model=model,
            temperature=temperature,
            canonical_evidence=canonical_evidence,
            prompt_profile=prompt_profile,
        ),
    )
    return run_dir


def _call_provider_command(
    command: str,
    call_payload: Mapping[str, Any],
    timeout_s: float,
) -> str:
    result = subprocess.run(
        command,
        input=json.dumps(dict(call_payload), sort_keys=True),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        shell=True,
        check=False,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            command,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result.stdout


def _canonical_evidence_is_valid(args: argparse.Namespace) -> bool:
    if not args.canonical_evidence:
        return True
    if args.attempts != 5:
        return False
    if args.prompt_profile != PROMPT_PROFILE_SHAPE_GUIDANCE_V2:
        return False
    if args.provider in _PLACEHOLDER_PROVIDERS:
        return False
    if args.model in _PLACEHOLDER_MODELS:
        return False
    if (args.provider, args.model) == _REJECTED_LOCAL_MODEL_PAIR:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    if args.provider_command is None:
        print("provider_command_required", file=sys.stderr)
        raise SystemExit(2)
    if not _canonical_evidence_is_valid(args):
        print("invalid_canonical_evidence", file=sys.stderr)
        raise SystemExit(2)

    run_dir = _run_probe(
        run_root=Path(args.run_dir),
        provider=args.provider,
        model=args.model,
        temperature=args.temperature,
        attempts=args.attempts,
        canonical_evidence=args.canonical_evidence,
        output_excerpt_chars=args.output_excerpt_chars,
        prompt_profile=args.prompt_profile,
        call_provider=lambda call_payload: _call_provider_command(
            args.provider_command,
            call_payload,
            args.provider_timeout_s,
        ),
    )
    print(f"LM7C planner authoring probe complete run_dir={run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
