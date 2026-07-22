#!/usr/bin/env python
"""Run the bounded LM9B-P Planner recipe-transfer probe."""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Literal, Mapping


_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _import_path in (_SCRIPTS_DIR, _MCP_SRC):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

_PLANNER_EVALUATOR_SYSTEM_PROMPT = (
    "Evaluate the submitted Planner recipe only against the visible brief, exact "
    "authority, deterministic findings, and frozen rubric. Do not infer compiler "
    "behavior, use hidden context, repair the recipe, or classify the probe. Submit "
    "exactly one evidence-backed recommendation through submit_planner_evaluation."
)

import lm9b_p_readiness_contract as READINESS
import lm9b_p_planner_recipe_transfer_artifacts as ARTIFACTS
from lm9b_p_planner_recipe_transfer_support import (
    PLANNER_COST_STOP_THRESHOLD_USD,
    PLANNER_EVALUATOR_MAX_COMPLETION_TOKENS,
    PLANNER_EVALUATOR_PROVIDER_TIMEOUT_S,
    PLANNER_MAX_COMPLETION_TOKENS,
    PLANNER_MAX_TURNS,
    PLANNER_OVERALL_DEADLINE_S,
    PLANNER_PROVIDER_TIMEOUT_S,
    PLANNER_TOKEN_STOP_THRESHOLD,
    PlannerEvaluationResult,
    PlannerSessionResult,
    ProviderTurn,
    fingerprint,
    run_planner_evaluation,
    run_planner_session,
    sha256_prefixed,
)


_PLANNER_FIXTURES = _SCRIPTS_DIR / "lm9b_p_fixtures"
_COMPILER_FIXTURES = _SCRIPTS_DIR / "lm9b_c_fixtures"
_ARCHIVED_COMPILER_MODEL = "gemini/gemini-3.1-pro-preview"
_FROZEN_TEMPERATURE = 0.0
_PLANNER_PROVIDER_PROFILE_ID = "litellm.completion.tool_calling.no_parallel:v1"
_COMPILER_CONTROL_FILES = (
    "implementation_context.json",
    "exclusion_policy.json",
    "evaluation_rubric.json",
)
PRODUCTION_SCOPE_FILES = (
    _SCRIPTS_DIR / "lm9b_p_planner_recipe_transfer_support.py",
    _SCRIPTS_DIR / "lm9b_p_planner_recipe_transfer_artifacts.py",
    Path(__file__).resolve(),
)
_FORBIDDEN_IMPORT_PREFIXES = (
    "rook.agent.base_agent",
    "Rhino",
    "Grasshopper",
    "gh" + "_" + "edit",
)
_MATCHED_CONTROL_TOKEN = "r" + "01"
_FORBIDDEN_TOOL_TOKEN = "gh" + "_" + "edit"
_POST_FREEZE_COMPARISON = "compare_sealed_checkpoint_with_" + _MATCHED_CONTROL_TOKEN


@dataclass(frozen=True)
class GitCheckoutState:
    commit_sha: str
    clean: bool


@dataclass(frozen=True)
class CliAttemptConfig:
    planner_model: str
    planner_evaluator_model: str
    compiler_model: str
    compiler_evaluator_model: str
    planner_temperature: float
    planner_evaluator_temperature: float
    compiler_temperature: float
    compiler_evaluator_temperature: float
    run_root: Path
    transmit: bool
    readiness_record: Path | None = None


@dataclass(frozen=True)
class CompilerControlRecord:
    relative_path: str
    raw_bytes: bytes
    raw_sha256: str


@dataclass(frozen=True)
class PreparedTransmission:
    config: CliAttemptConfig
    git_sha: str
    planner_inputs: ARTIFACTS.FrozenPlannerInputs
    planner_request: ARTIFACTS.RenderedRequest
    compiler_controls: tuple[CompilerControlRecord, ...]
    summary: Mapping[str, object]


@dataclass(frozen=True)
class PlannerCheckpointResult:
    classification: Literal[
        "probe_mechanically_rejected",
        "probe_inconclusive",
        "probe_candidate_blocked",
        "probe_planner_failure",
        "probe_candidate_ready",
    ]
    planner_session: PlannerSessionResult
    evaluator: PlannerEvaluationResult | None
    final_recipe_bytes: bytes | None
    checkpoint_2: Literal["not_evaluated"]
    sealed_archive: ARTIFACTS.SealedPlannerCheckpointArchive | None = None
    planner_inputs: ARTIFACTS.FrozenPlannerInputs | None = None
    gate_result: ARTIFACTS.MechanicalGateResult | None = None
    planner_provider_attempts: tuple[ARTIFACTS.ProviderAttemptEvidence, ...] = ()
    evaluator_provider_attempts: tuple[ARTIFACTS.ProviderAttemptEvidence, ...] = ()
    control_failure: Mapping[str, object] | None = None


@dataclass(frozen=True)
class JoinedProbeResult:
    checkpoint_1: PlannerCheckpointResult
    checkpoint_2: Literal[
        "not_evaluated",
        "bounded_lowering_demonstrated",
        "contract_gap_demonstrated",
        "candidate_failure",
        "inconclusive",
    ]
    aggregate_outcome: str
    handoff: ARTIFACTS.Lm9bcHandoff | None
    lm9bc_result: object | None
    pre_session_failure: Mapping[str, object] | None
    sealed_aggregate: ARTIFACTS.SealedJoinedAggregate | None
    compiler_provider_attempts: tuple[ARTIFACTS.ProviderAttemptEvidence, ...] = ()
    compiler_evaluator_provider_attempts: tuple[
        ARTIFACTS.ProviderAttemptEvidence, ...
    ] = ()
    control_failure: Mapping[str, object] | None = None


@dataclass(frozen=True)
class TerminalControlFailureResult:
    """Unsealed in-memory result for a control failure outside provider calls."""

    checkpoint_1: PlannerCheckpointResult | None
    checkpoint_2: Literal["not_evaluated"]
    aggregate_outcome: Literal["inconclusive"]
    sealed_aggregate: None
    control_failure: Mapping[str, object]


def _checkpoint_classification(
    planner_session: PlannerSessionResult,
    evaluator: PlannerEvaluationResult | None,
    checkpoint_gate: ARTIFACTS.MechanicalGateResult | None = None,
) -> PlannerCheckpointResult:
    classification = ARTIFACTS.derive_checkpoint_classification(
        planner_session, evaluator, checkpoint_gate=checkpoint_gate
    )
    if classification == "probe_mechanically_rejected":
        return PlannerCheckpointResult(
            "probe_mechanically_rejected", planner_session, None, None, "not_evaluated"
        )
    if classification == "probe_inconclusive":
        return PlannerCheckpointResult(
            "probe_inconclusive",
            planner_session,
            evaluator,
            (
                planner_session.final_recipe_bytes
                if planner_session.termination == "mechanically_accepted"
                and evaluator is not None
                else None
            ),
            "not_evaluated",
        )
    return PlannerCheckpointResult(
        classification,
        planner_session,
        evaluator,
        planner_session.final_recipe_bytes,
        "not_evaluated",
    )


def run_planner_checkpoint(
    *,
    fixture_dir: Path,
    planner_provider: Callable[[dict[str, object]], ProviderTurn],
    evaluator_provider: Callable[[dict[str, object]], ProviderTurn],
    frozen_inputs: ARTIFACTS.FrozenPlannerInputs | None = None,
    frozen_planner_request: ARTIFACTS.RenderedRequest | None = None,
    archive_destination: Path | None = None,
    archive_identity: Mapping[str, object] | None = None,
) -> PlannerCheckpointResult:
    """Run one Planner session and at most one isolated evaluation attempt."""

    if archive_destination is None and archive_identity is not None:
        raise ValueError("archive identity requires an archive destination")
    if archive_destination is not None and archive_identity is None:
        raise ValueError("checkpoint archive identity is required")
    if (frozen_inputs is None) != (frozen_planner_request is None):
        raise ValueError("frozen Planner inputs and request must be supplied together")
    if frozen_inputs is None:
        inputs = ARTIFACTS.load_planner_inputs(Path(fixture_dir))
        planner_request = ARTIFACTS.render_planner_request(inputs)
    else:
        if type(frozen_inputs) is not ARTIFACTS.FrozenPlannerInputs:
            raise TypeError("FrozenPlannerInputs is required")
        if type(frozen_planner_request) is not ARTIFACTS.RenderedRequest:
            raise TypeError("RenderedRequest is required")
        inputs = frozen_inputs
        planner_request = frozen_planner_request
        if ARTIFACTS.render_planner_request(inputs) != planner_request:
            raise ValueError("frozen Planner request does not match frozen inputs")
    planner_provider_attempts: list[ARTIFACTS.ProviderAttemptEvidence] = []
    evaluator_provider_attempts: list[ARTIFACTS.ProviderAttemptEvidence] = []
    evaluator_request: ARTIFACTS.RenderedRequest | None = None
    evaluator_elapsed_ms: int | None = None
    checkpoint_gate: ARTIFACTS.MechanicalGateResult | None = None

    def provider_request_bytes(request: dict[str, object]) -> bytes:
        return json.dumps(
            request, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def recorded_planner_provider(request: dict[str, object]) -> ProviderTurn:
        attempt = ARTIFACTS.ProviderAttemptEvidence(
            provider_request_bytes=provider_request_bytes(request)
        )
        planner_provider_attempts.append(attempt)
        started_at = time.perf_counter()
        try:
            turn = planner_provider(request)
        except BaseException as exc:
            attempt.record_exception(exc, started_at)
            raise
        attempt.record_return(turn, started_at)
        return turn

    def finish(result: PlannerCheckpointResult) -> PlannerCheckpointResult:
        result = replace(
            result,
            planner_inputs=inputs,
            gate_result=checkpoint_gate,
            planner_provider_attempts=tuple(planner_provider_attempts),
            evaluator_provider_attempts=tuple(evaluator_provider_attempts),
        )
        if archive_destination is None:
            return result
        assert archive_identity is not None
        try:
            sealed = ARTIFACTS.seal_planner_checkpoint_archive(
                destination=archive_destination,
                inputs=inputs,
                planner_request=planner_request,
                planner_session=result.planner_session,
                evaluator=result.evaluator,
                evaluator_request=evaluator_request,
                planner_provider_attempts=planner_provider_attempts,
                evaluator_provider_attempts=evaluator_provider_attempts,
                evaluator_elapsed_ms=evaluator_elapsed_ms,
                classification=result.classification,
                archive_identity=archive_identity,
                checkpoint_gate=checkpoint_gate,
            )
        except Exception as exc:
            if not planner_provider_attempts and not evaluator_provider_attempts:
                raise
            return replace(
                result,
                classification="probe_inconclusive",
                sealed_archive=None,
                control_failure={
                    "locus": "checkpoint_1_seal",
                    "exception_type": type(exc).__name__,
                    "message": str(exc)[:2000],
                },
            )
        return replace(result, sealed_archive=sealed)

    planner_session = run_planner_session(
        provider=recorded_planner_provider,
        system_prompt=(
            "Author one governed Planner recipe using only the supplied request and "
            "submit it with submit_planner_recipe."
        ),
        user_prompt=planner_request.raw_bytes.decode("utf-8"),
        authority=inputs.authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.authority.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    if planner_session.termination != "mechanically_accepted":
        return finish(_checkpoint_classification(planner_session, None))

    final_recipe_bytes = planner_session.final_recipe_bytes
    if final_recipe_bytes is None:
        return finish(_checkpoint_classification(planner_session, None))
    gate_result = ARTIFACTS.evaluate_mechanical_gate(
        recipe_bytes=final_recipe_bytes,
        authority=inputs.authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.authority.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    checkpoint_gate = gate_result
    if type(gate_result) is not ARTIFACTS.MechanicalGateResult:
        return finish(_checkpoint_classification(planner_session, None))
    evaluator_request = ARTIFACTS.render_planner_evaluator_request(
        inputs, gate_result=gate_result
    )
    def recorded_evaluator_provider(request: dict[str, object]) -> ProviderTurn:
        attempt = ARTIFACTS.ProviderAttemptEvidence(
            provider_request_bytes=provider_request_bytes(request)
        )
        evaluator_provider_attempts.append(attempt)
        started_at = time.perf_counter()
        try:
            turn = evaluator_provider(request)
        except BaseException as exc:
            attempt.record_exception(exc, started_at)
            raise
        attempt.record_return(turn, started_at)
        return turn

    started_at = time.perf_counter()
    evaluator = run_planner_evaluation(
        provider=recorded_evaluator_provider,
        system_prompt=_PLANNER_EVALUATOR_SYSTEM_PROMPT,
        user_prompt=evaluator_request.raw_bytes.decode("utf-8"),
    )
    evaluator_elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    return finish(
        _checkpoint_classification(planner_session, evaluator, checkpoint_gate)
    )


def _load_lm9bc_modules() -> tuple[object, object]:
    return (
        importlib.import_module("lm9b_c_compiler_sufficiency_artifacts"),
        importlib.import_module("lm9b_c_compiler_sufficiency_probe"),
    )


def assert_frozen_compiler_controls() -> None:
    lm9bc_artifacts, lm9bc_probe = _load_lm9bc_modules()
    expected = {
        "MAX_TURNS": 6,
        "MAX_COMPLETION_TOKENS": 16_384,
        "PROVIDER_TIMEOUT_S": 180.0,
        "OVERALL_DEADLINE_S": 600.0,
        "TOKEN_STOP_THRESHOLD": 120_000,
        "COST_STOP_THRESHOLD_USD": 10.0,
        "EVALUATOR_MAX_COMPLETION_TOKENS": 8_192,
        "TEMPERATURE": 0.0,
    }
    observed = {name: getattr(lm9bc_probe, name, None) for name in expected}
    renderer = getattr(lm9bc_artifacts, "COMPILER_RENDERER_ID", None)
    if observed != expected or renderer != "lm9b_c.compiler_request_renderer:v2":
        raise RuntimeError("LM9B-C control drift from the archived compiler probe")


def assert_frozen_planner_controls() -> None:
    observed = {
        "PLANNER_MAX_TURNS": PLANNER_MAX_TURNS,
        "PLANNER_MAX_COMPLETION_TOKENS": PLANNER_MAX_COMPLETION_TOKENS,
        "PLANNER_PROVIDER_TIMEOUT_S": PLANNER_PROVIDER_TIMEOUT_S,
        "PLANNER_OVERALL_DEADLINE_S": PLANNER_OVERALL_DEADLINE_S,
        "PLANNER_TOKEN_STOP_THRESHOLD": PLANNER_TOKEN_STOP_THRESHOLD,
        "PLANNER_COST_STOP_THRESHOLD_USD": PLANNER_COST_STOP_THRESHOLD_USD,
        "PLANNER_EVALUATOR_MAX_COMPLETION_TOKENS": PLANNER_EVALUATOR_MAX_COMPLETION_TOKENS,
        "PLANNER_EVALUATOR_PROVIDER_TIMEOUT_S": PLANNER_EVALUATOR_PROVIDER_TIMEOUT_S,
    }
    expected = {
        "PLANNER_MAX_TURNS": 6,
        "PLANNER_MAX_COMPLETION_TOKENS": 16_384,
        "PLANNER_PROVIDER_TIMEOUT_S": 180.0,
        "PLANNER_OVERALL_DEADLINE_S": 600.0,
        "PLANNER_TOKEN_STOP_THRESHOLD": 120_000,
        "PLANNER_COST_STOP_THRESHOLD_USD": 10.0,
        "PLANNER_EVALUATOR_MAX_COMPLETION_TOKENS": 8_192,
        "PLANNER_EVALUATOR_PROVIDER_TIMEOUT_S": 180.0,
    }
    if observed != expected:
        raise RuntimeError("Planner control drift from the frozen probe contract")


class _ScopeVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.functions: list[str] = []

    def _inside_post_freeze_comparison(self) -> bool:
        return bool(self.functions and self.functions[-1] == _POST_FREEZE_COMPARISON)

    def _check_import(self, name: str) -> None:
        if any(name == prefix or name.startswith(prefix + ".") for prefix in _FORBIDDEN_IMPORT_PREFIXES):
            raise ValueError(f"forbidden import in {self.path}: {name}")
        if name.startswith("rook.validation_kernel."):
            tail = name.removeprefix("rook.validation_kernel.")
            if any(part.startswith("_") for part in tail.split(".")):
                raise ValueError(f"forbidden private validation-kernel import in {self.path}: {name}")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_import(alias.name)
            for symbol in (alias.name, alias.asname or ""):
                if _FORBIDDEN_TOOL_TOKEN in symbol.casefold():
                    raise ValueError(f"forbidden imported symbol in {self.path}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        self._check_import(module)
        if module.startswith("rook.validation_kernel") and any(
            alias.name.startswith("_") for alias in node.names
        ):
            raise ValueError(f"forbidden private validation-kernel name in {self.path}")
        if any(
            _FORBIDDEN_TOOL_TOKEN in symbol.casefold()
            for alias in node.names
            for symbol in (alias.name, alias.asname or "")
        ):
            raise ValueError(f"forbidden imported symbol in {self.path}")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)
        self.functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Name(self, node: ast.Name) -> None:
        if (
            _MATCHED_CONTROL_TOKEN in node.id.casefold()
            and not self._inside_post_freeze_comparison()
        ):
            raise ValueError(
                f"matched-control name outside post-freeze comparison in {self.path}"
            )

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if (
            _MATCHED_CONTROL_TOKEN in node.attr.casefold()
            and not self._inside_post_freeze_comparison()
        ):
            raise ValueError(
                f"matched-control attribute outside post-freeze comparison in {self.path}"
            )
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, str):
            return
        folded = node.value.casefold()
        if _FORBIDDEN_TOOL_TOKEN in folded:
            raise ValueError(f"forbidden tool reference in {self.path}")
        if (
            _MATCHED_CONTROL_TOKEN in folded
            and node.value != _POST_FREEZE_COMPARISON
            and not self._inside_post_freeze_comparison()
        ):
            raise ValueError(
                f"matched-control reference outside post-freeze comparison in {self.path}"
            )


def verify_scope_guards(paths: tuple[Path, ...]) -> None:
    for path in paths:
        source = Path(path).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        _ScopeVisitor(Path(path)).visit(tree)


def _readiness_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _launch_models(config: "CliAttemptConfig") -> dict:
    return {
        "planner": config.planner_model,
        "planner_evaluator": config.planner_evaluator_model,
        "compiler": config.compiler_model,
        "compiler_evaluator": config.compiler_evaluator_model,
    }


def _readiness_manifest(models: dict):
    # Deferred import keeps the experiment CLI module import light: importing
    # this module pulls no provider/model_profiles code (only the pure
    # readiness contract at top level).
    from rook.agent.model_profiles import api_key_env_for_model

    return READINESS.derive_routes(
        READINESS.role_routes_from_models(models), api_key_env_for_model
    )


def readiness_gate_ok(
    *, record, models, head_sha, now_iso, credential_present
) -> bool:
    manifest = _readiness_manifest(models)
    return READINESS.verify_launch_readiness(
        record=record,
        manifest=manifest,
        head_sha=head_sha,
        now_iso=now_iso,
        credential_present=credential_present,
    ).ok


def _git_checkout_state() -> GitCheckoutState:
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    commit_sha = head.stdout.strip()
    if head.returncode != 0 or len(commit_sha) != 40 or status.returncode != 0:
        raise RuntimeError("LM9B-P requires a committed git HEAD")
    return GitCheckoutState(commit_sha=commit_sha, clean=status.stdout == "")


def parse_cli_args(argv: list[str] | None = None) -> CliAttemptConfig:
    parser = argparse.ArgumentParser(
        description="One bounded, inert LM9B-P Planner recipe-transfer probe."
    )
    parser.add_argument("--planner-model", required=True)
    parser.add_argument("--planner-evaluator-model", required=True)
    parser.add_argument("--compiler-model", required=True)
    parser.add_argument("--compiler-evaluator-model", required=True)
    parser.add_argument("--planner-temperature", type=float, required=True)
    parser.add_argument("--planner-evaluator-temperature", type=float, required=True)
    parser.add_argument("--compiler-temperature", type=float, required=True)
    parser.add_argument("--compiler-evaluator-temperature", type=float, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--transmit", action="store_true")
    parser.add_argument("--readiness-record", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.planner_model != "gpt-5.4" or args.planner_evaluator_model != "gpt-5.4":
        parser.error(
            "canonical Planner pin: --planner-model and "
            "--planner-evaluator-model must both be gpt-5.4"
        )
    if args.compiler_model != _ARCHIVED_COMPILER_MODEL:
        parser.error(f"--compiler-model must be {_ARCHIVED_COMPILER_MODEL}")
    if args.compiler_evaluator_model != _ARCHIVED_COMPILER_MODEL:
        parser.error(f"--compiler-evaluator-model must be {_ARCHIVED_COMPILER_MODEL}")
    if args.transmit and args.readiness_record is None:
        parser.error("--transmit requires --readiness-record")
    temperatures = (
        args.planner_temperature,
        args.planner_evaluator_temperature,
        args.compiler_temperature,
        args.compiler_evaluator_temperature,
    )
    if any(value != _FROZEN_TEMPERATURE for value in temperatures):
        parser.error("all four temperatures must be exactly 0.0")
    return CliAttemptConfig(
        planner_model=args.planner_model,
        planner_evaluator_model=args.planner_evaluator_model,
        compiler_model=args.compiler_model,
        compiler_evaluator_model=args.compiler_evaluator_model,
        planner_temperature=args.planner_temperature,
        planner_evaluator_temperature=args.planner_evaluator_temperature,
        compiler_temperature=args.compiler_temperature,
        compiler_evaluator_temperature=args.compiler_evaluator_temperature,
        run_root=args.run_root.resolve(),
        transmit=args.transmit,
        readiness_record=(
            args.readiness_record.resolve()
            if args.readiness_record is not None
            else None
        ),
    )


def _authority_manifest_fingerprint(
    inputs: ARTIFACTS.FrozenPlannerInputs,
) -> str:
    return fingerprint(
        {
            "schema": "rook.lm9b_p.pretransmission_input_manifest:v1",
            "records": [
                {
                    "role": record.role,
                    "relative_path": record.relative_path,
                    "raw_sha256": record.raw_sha256,
                    "canonical_fingerprint": record.canonical_fingerprint,
                }
                for record in inputs.records
            ],
        }
    )


def _freeze_compiler_controls() -> tuple[CompilerControlRecord, ...]:
    records = []
    for relative_path in _COMPILER_CONTROL_FILES:
        raw = (_COMPILER_FIXTURES / relative_path).read_bytes()
        records.append(
            CompilerControlRecord(
                relative_path=relative_path,
                raw_bytes=raw,
                raw_sha256=sha256_prefixed(raw),
            )
        )
    return tuple(records)


def _bounds_summary() -> Mapping[str, object]:
    return {
        "planner": {
            "max_turns": PLANNER_MAX_TURNS,
            "max_completion_tokens_per_call": PLANNER_MAX_COMPLETION_TOKENS,
            "provider_timeout_s": PLANNER_PROVIDER_TIMEOUT_S,
            "overall_deadline_s": PLANNER_OVERALL_DEADLINE_S,
            "cumulative_token_stop_threshold": PLANNER_TOKEN_STOP_THRESHOLD,
            "cumulative_cost_stop_threshold_usd": PLANNER_COST_STOP_THRESHOLD_USD,
        },
        "planner_evaluator": {
            "max_attempts": 1,
            "max_completion_tokens": PLANNER_EVALUATOR_MAX_COMPLETION_TOKENS,
            "provider_timeout_s": PLANNER_EVALUATOR_PROVIDER_TIMEOUT_S,
        },
        "compiler": {
            "max_turns": 6,
            "max_completion_tokens_per_call": 16_384,
            "provider_timeout_s": 180.0,
            "overall_deadline_s": 600.0,
            "cumulative_token_stop_threshold": 120_000,
            "cumulative_cost_stop_threshold_usd": 10.0,
        },
        "compiler_evaluator": {
            "max_attempts": 1,
            "max_completion_tokens": 8_192,
            "provider_timeout_s": 180.0,
        },
    }


def prepare_pretransmission(config: CliAttemptConfig) -> PreparedTransmission:
    checkout = _git_checkout_state()
    if not checkout.clean:
        raise RuntimeError("LM9B-P requires a clean committed HEAD")
    if config.run_root.exists():
        raise FileExistsError(f"LM9B-P run root already exists: {config.run_root}")
    verify_scope_guards(PRODUCTION_SCOPE_FILES)
    assert_frozen_planner_controls()
    assert_frozen_compiler_controls()
    inputs = ARTIFACTS.load_planner_inputs(_PLANNER_FIXTURES)
    planner_request = ARTIFACTS.render_planner_request(inputs)
    compiler_controls = _freeze_compiler_controls()
    lm9bc_artifacts, _ = _load_lm9bc_modules()
    summary = {
        "schema": "rook.lm9b_p.pretransmission_summary:v1",
        "git_sha": checkout.commit_sha,
        "models": {
            "planner": {
                "model": config.planner_model,
                "temperature": config.planner_temperature,
            },
            "planner_evaluator": {
                "model": config.planner_evaluator_model,
                "temperature": config.planner_evaluator_temperature,
            },
            "compiler": {
                "model": config.compiler_model,
                "temperature": config.compiler_temperature,
            },
            "compiler_evaluator": {
                "model": config.compiler_evaluator_model,
                "temperature": config.compiler_evaluator_temperature,
            },
        },
        "provider_profiles": {
            "planner": _PLANNER_PROVIDER_PROFILE_ID,
            "planner_evaluator": _PLANNER_PROVIDER_PROFILE_ID,
            "compiler": "litellm.completion",
            "compiler_evaluator": "litellm.completion",
        },
        "bounds": _bounds_summary(),
        "planner_request": {
            "byte_length": len(planner_request.raw_bytes),
            "raw_sha256": planner_request.raw_sha256,
        },
        "authority_manifest_fingerprint": _authority_manifest_fingerprint(inputs),
        "normalization_profile_fingerprint": inputs.authority.normalization_profile.profile_fingerprint,
        "compiler_renderer_identity": lm9bc_artifacts.COMPILER_RENDERER_ID,
        "compiler_control_records": [
            {
                "relative_path": record.relative_path,
                "raw_sha256": record.raw_sha256,
                "byte_length": len(record.raw_bytes),
            }
            for record in compiler_controls
        ],
        f"{_MATCHED_CONTROL_TOKEN}_pre_freeze_access": "forbidden",
        "execution_permitted": False,
        "transmission_requested": config.transmit,
        "run_root": str(config.run_root),
    }
    return PreparedTransmission(
        config=config,
        git_sha=checkout.commit_sha,
        planner_inputs=inputs,
        planner_request=planner_request,
        compiler_controls=compiler_controls,
        summary=summary,
    )


def run_joined_probe(
    *,
    checkpoint_1: PlannerCheckpointResult,
    compiler_fixture_dir: Path,
    handoff_destination: Path,
    compiler_run_root: Path,
    aggregate_destination: Path,
    compiler_provider: Callable[[dict[str, object]], object],
    compiler_evaluator_provider: Callable[[dict[str, object]], object],
    compiler_identity: Mapping[str, object],
    compiler_evaluator_identity: Mapping[str, object],
    git_sha: str,
) -> JoinedProbeResult:
    """Join one sealed ready checkpoint to one unchanged LM9B-C session."""

    if type(checkpoint_1) is not PlannerCheckpointResult:
        raise TypeError("PlannerCheckpointResult is required")
    sealed_checkpoint = checkpoint_1.sealed_archive
    if sealed_checkpoint is None:
        raise ValueError("Checkpoint 1 must be sealed before the join")
    ARTIFACTS.verify_sealed_planner_checkpoint_archive(
        sealed_checkpoint.archive_dir,
        expected_aggregate_identity=sealed_checkpoint.aggregate_identity,
    )
    persisted_classification = ARTIFACTS.parse_archive_json(
        (
            sealed_checkpoint.archive_dir
            / "checkpoint"
            / "classification.json"
        ).read_bytes()
    )
    if (
        not isinstance(persisted_classification, dict)
        or persisted_classification.get("classification")
        != checkpoint_1.classification
    ):
        raise ValueError("Checkpoint 1 classification is not bound to its seal")

    compiler_provider_attempts: list[ARTIFACTS.ProviderAttemptEvidence] = []
    compiler_evaluator_provider_attempts: list[
        ARTIFACTS.ProviderAttemptEvidence
    ] = []

    def seal_result(
        *,
        checkpoint_2: str,
        aggregate_outcome: str,
        reason_codes: tuple[str, ...] = (),
        handoff: ARTIFACTS.Lm9bcHandoff | None = None,
        loaded_recipe_bytes: bytes | None = None,
        lm9bc_result: object | None = None,
        pre_session_failure: Mapping[str, object] | None = None,
    ) -> JoinedProbeResult:
        run_dir = getattr(lm9bc_result, "run_dir", None)
        sealed_aggregate = ARTIFACTS.seal_joined_aggregate(
            destination=aggregate_destination,
            checkpoint_1_archive=sealed_checkpoint,
            checkpoint_1_classification=checkpoint_1.classification,
            checkpoint_2_outcome=checkpoint_2,
            checkpoint_2_reason_codes=reason_codes,
            aggregate_outcome=aggregate_outcome,
            handoff=handoff,
            planner_recipe_bytes=checkpoint_1.final_recipe_bytes,
            lm9bc_loaded_recipe_bytes=loaded_recipe_bytes,
            lm9bc_run_dir=run_dir,
            pre_session_failure=pre_session_failure,
        )
        return JoinedProbeResult(
            checkpoint_1=checkpoint_1,
            checkpoint_2=checkpoint_2,
            aggregate_outcome=aggregate_outcome,
            handoff=handoff,
            lm9bc_result=lm9bc_result,
            pre_session_failure=pre_session_failure,
            sealed_aggregate=sealed_aggregate,
            compiler_provider_attempts=tuple(compiler_provider_attempts),
            compiler_evaluator_provider_attempts=tuple(
                compiler_evaluator_provider_attempts
            ),
        )

    if checkpoint_1.classification != "probe_candidate_ready":
        outcome = ARTIFACTS.derive_joined_aggregate_outcome(
            checkpoint_1_classification=checkpoint_1.classification,
            checkpoint_2_outcome="not_evaluated",
        )
        return seal_result(
            checkpoint_2="not_evaluated",
            aggregate_outcome=outcome,
        )

    planner_inputs = checkpoint_1.planner_inputs
    gate_result = checkpoint_1.gate_result
    final_recipe_bytes = checkpoint_1.final_recipe_bytes
    if (
        planner_inputs is None
        or type(gate_result) is not ARTIFACTS.MechanicalGateResult
        or type(final_recipe_bytes) is not bytes
        or gate_result.final_recipe_bytes is not final_recipe_bytes
    ):
        raise ValueError("ready Checkpoint 1 has no exact accepted gate transition")
    join_proof = ARTIFACTS.verify_ready_checkpoint_for_join(
        checkpoint_archive=sealed_checkpoint,
        checkpoint_classification=checkpoint_1.classification,
        planner_inputs=planner_inputs,
        gate_result=gate_result,
        final_recipe_bytes=final_recipe_bytes,
    )

    def finish_pre_session_failure(
        locus: str,
        exc: Exception,
        *,
        handoff: ARTIFACTS.Lm9bcHandoff | None = None,
        loaded_recipe_bytes: bytes | None = None,
    ) -> JoinedProbeResult:
        failure = {
            "locus": locus,
            "exception_type": type(exc).__name__,
            "message": str(exc)[:2000],
        }
        return seal_result(
            checkpoint_2="inconclusive",
            aggregate_outcome="inconclusive",
            reason_codes=(f"pre_session_{locus}_failed",),
            handoff=handoff,
            loaded_recipe_bytes=loaded_recipe_bytes,
            pre_session_failure=failure,
        )

    try:
        handoff = ARTIFACTS.build_lm9bc_handoff(
            join_proof=join_proof,
            compiler_fixture_dir=compiler_fixture_dir,
            destination=handoff_destination,
        )
    except Exception as exc:
        return finish_pre_session_failure("handoff", exc)
    lm9bc_artifacts, lm9bc_probe = _load_lm9bc_modules()

    try:
        loaded_inputs = lm9bc_artifacts.load_frozen_inputs(handoff.fixture_dir)
    except Exception as exc:
        return finish_pre_session_failure("load_or_index", exc, handoff=handoff)
    loaded_recipe_bytes = getattr(loaded_inputs, "recipe_bytes", None)
    if loaded_recipe_bytes != final_recipe_bytes:
        return finish_pre_session_failure(
            "load_or_index",
            ValueError("LM9B-C loaded different recipe bytes"),
            handoff=handoff,
            loaded_recipe_bytes=loaded_recipe_bytes,
        )
    try:
        lm9bc_artifacts.render_compiler_request(loaded_inputs)
    except Exception as exc:
        return finish_pre_session_failure(
            "render",
            exc,
            handoff=handoff,
            loaded_recipe_bytes=loaded_recipe_bytes,
        )

    def provider_request_bytes(request: dict[str, object]) -> bytes:
        return json.dumps(
            request, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def counted_compiler_provider(request: dict[str, object]) -> object:
        attempt = ARTIFACTS.ProviderAttemptEvidence(
            provider_request_bytes=provider_request_bytes(request)
        )
        compiler_provider_attempts.append(attempt)
        started_at = time.perf_counter()
        try:
            turn = compiler_provider(request)
        except BaseException as exc:
            attempt.record_exception(exc, started_at)
            raise
        attempt.record_return(turn, started_at)
        return turn

    def counted_evaluator_provider(request: dict[str, object]) -> object:
        attempt = ARTIFACTS.ProviderAttemptEvidence(
            provider_request_bytes=provider_request_bytes(request)
        )
        compiler_evaluator_provider_attempts.append(attempt)
        started_at = time.perf_counter()
        try:
            turn = compiler_evaluator_provider(request)
        except BaseException as exc:
            attempt.record_exception(exc, started_at)
            raise
        attempt.record_return(turn, started_at)
        return turn

    def finish_post_contact_failure(
        exc: Exception,
        *,
        lm9bc_result: object | None = None,
    ) -> JoinedProbeResult:
        failure = {
            "locus": "lm9b_c_session_or_evidence",
            "exception_type": type(exc).__name__,
            "message": str(exc)[:2000],
        }
        return JoinedProbeResult(
            checkpoint_1=checkpoint_1,
            checkpoint_2="inconclusive",
            aggregate_outcome="inconclusive",
            handoff=handoff,
            lm9bc_result=lm9bc_result,
            pre_session_failure=None,
            sealed_aggregate=None,
            compiler_provider_attempts=tuple(compiler_provider_attempts),
            compiler_evaluator_provider_attempts=tuple(
                compiler_evaluator_provider_attempts
            ),
            control_failure=failure,
        )

    try:
        lm9bc_result = lm9bc_probe.run_probe(
            run_root=compiler_run_root,
            fixture_dir=handoff.fixture_dir,
            compiler_provider=counted_compiler_provider,
            evaluator_provider=counted_evaluator_provider,
            compiler_identity=compiler_identity,
            evaluator_identity=compiler_evaluator_identity,
            git_sha=git_sha,
        )
    except Exception as exc:
        if not compiler_provider_attempts and not compiler_evaluator_provider_attempts:
            return finish_pre_session_failure(
                "load_or_index_or_render",
                exc,
                handoff=handoff,
                loaded_recipe_bytes=loaded_recipe_bytes,
            )
        return finish_post_contact_failure(exc)

    try:
        result_loaded_bytes = getattr(
            getattr(lm9bc_result, "inputs", None), "recipe_bytes", None
        )
        if result_loaded_bytes != final_recipe_bytes:
            raise ValueError("unchanged LM9B-C run loaded different recipe bytes")
        checkpoint_2 = lm9bc_result.decision.outcome
        aggregate_outcome = ARTIFACTS.derive_joined_aggregate_outcome(
            checkpoint_1_classification=checkpoint_1.classification,
            checkpoint_2_outcome=checkpoint_2,
            compiler_session=lm9bc_result.compiler_session,
            evaluator_result=lm9bc_result.evaluator_result,
        )
        return seal_result(
            checkpoint_2=checkpoint_2,
            aggregate_outcome=aggregate_outcome,
            reason_codes=tuple(lm9bc_result.decision.reason_codes),
            handoff=handoff,
            loaded_recipe_bytes=result_loaded_bytes,
            lm9bc_result=lm9bc_result,
        )
    except Exception as exc:
        return finish_post_contact_failure(exc, lm9bc_result=lm9bc_result)


class _PlannerProviderAdapter:
    def __init__(self, *, model: str, temperature: float) -> None:
        _, lm9bc_probe = _load_lm9bc_modules()
        self._delegate = lm9bc_probe.LiteLLMProvider(
            model=model, temperature=temperature
        )
        self.model = model
        self.temperature = temperature

    def __call__(self, request: dict[str, object]) -> ProviderTurn:
        turn = self._delegate(request)
        if type(turn) is not ProviderTurn:
            raise RuntimeError("Planner provider returned an incompatible turn")
        metadata = dict(turn.provider_metadata)
        metadata.update(
            {
                "model_identity": self.model,
                "profile_identity": _PLANNER_PROVIDER_PROFILE_ID,
            }
        )
        return replace(turn, provider_metadata=metadata)


def _build_provider(*, role: str, model: str, temperature: float) -> object:
    if role in ("planner", "planner_evaluator"):
        return _PlannerProviderAdapter(model=model, temperature=temperature)
    _, lm9bc_probe = _load_lm9bc_modules()
    return lm9bc_probe.LiteLLMProvider(model=model, temperature=temperature)


def _execute_transmitted_attempt(
    prepared: PreparedTransmission,
) -> JoinedProbeResult | TerminalControlFailureResult:
    config = prepared.config
    checkout = _git_checkout_state()
    if not checkout.clean or checkout.commit_sha != prepared.git_sha:
        raise RuntimeError("checkout changed after pre-transmission review")
    # Readiness gate: refuse before allocating an attempt identity if there is
    # no fresh, passing readiness record bound to this commit and route
    # manifest. This runs before mkdir, so a refusal consumes no attempt.
    if config.readiness_record is None:
        raise RuntimeError("readiness gate refused: no readiness record supplied")
    _readiness_record = json.loads(
        config.readiness_record.read_text(encoding="utf-8")
    )
    _readiness_models = _launch_models(config)
    _readiness_manifest_value = _readiness_manifest(_readiness_models)
    _readiness_presence = {
        route.route_fingerprint: any(
            bool(os.environ.get(name)) for name in route.credential_source
        )
        for route in _readiness_manifest_value.routes
    }
    if not READINESS.verify_launch_readiness(
        record=_readiness_record,
        manifest=_readiness_manifest_value,
        head_sha=prepared.git_sha,
        now_iso=_readiness_now_iso(),
        credential_present=_readiness_presence,
    ).ok:
        raise RuntimeError(
            "readiness gate refused: no fresh passing readiness record for this "
            "commit/route manifest; run scripts/lm9b_p_readiness_probe.py "
            "--authenticate first (no attempt was allocated)"
        )
    config.run_root.mkdir(parents=True, exist_ok=False)
    compiler_control_dir = config.run_root / "compiler-controls"
    compiler_control_dir.mkdir()
    if tuple(record.relative_path for record in prepared.compiler_controls) != _COMPILER_CONTROL_FILES:
        raise ValueError("prepared compiler control set is incomplete or out of order")
    for record in prepared.compiler_controls:
        if sha256_prefixed(record.raw_bytes) != record.raw_sha256:
            raise ValueError("prepared compiler control fingerprint mismatch")
        destination = compiler_control_dir / record.relative_path
        destination.write_bytes(record.raw_bytes)
        if destination.read_bytes() != record.raw_bytes:
            raise ValueError("compiler control snapshot write verification failed")
    def construction_failure(
        role: str,
        exc: Exception,
        *,
        checkpoint_1: PlannerCheckpointResult | None = None,
    ) -> TerminalControlFailureResult:
        return TerminalControlFailureResult(
            checkpoint_1=checkpoint_1,
            checkpoint_2="not_evaluated",
            aggregate_outcome="inconclusive",
            sealed_aggregate=None,
            control_failure={
                "locus": "provider_construction",
                "role": role,
                "exception_type": type(exc).__name__,
                "message": str(exc)[:2000],
            },
        )

    try:
        planner_provider = _build_provider(
            role="planner",
            model=config.planner_model,
            temperature=config.planner_temperature,
        )
    except Exception as exc:
        return construction_failure("planner", exc)
    try:
        planner_evaluator_provider = _build_provider(
            role="planner_evaluator",
            model=config.planner_evaluator_model,
            temperature=config.planner_evaluator_temperature,
        )
    except Exception as exc:
        return construction_failure("planner_evaluator", exc)
    checkpoint = run_planner_checkpoint(
        fixture_dir=_PLANNER_FIXTURES,
        frozen_inputs=prepared.planner_inputs,
        frozen_planner_request=prepared.planner_request,
        planner_provider=planner_provider,
        evaluator_provider=planner_evaluator_provider,
        archive_destination=config.run_root / "checkpoint-1",
        archive_identity={
            "git_commit_sha": prepared.git_sha,
            "planner_model_identity": config.planner_model,
            "evaluator_model_identity": config.planner_evaluator_model,
            "provider_profile_identity": _PLANNER_PROVIDER_PROFILE_ID,
        },
    )
    if (
        type(checkpoint) is PlannerCheckpointResult
        and checkpoint.control_failure is not None
    ):
        return JoinedProbeResult(
            checkpoint_1=checkpoint,
            checkpoint_2="not_evaluated",
            aggregate_outcome="inconclusive",
            handoff=None,
            lm9bc_result=None,
            pre_session_failure=None,
            sealed_aggregate=None,
            control_failure=checkpoint.control_failure,
        )
    try:
        compiler_provider = _build_provider(
            role="compiler",
            model=config.compiler_model,
            temperature=config.compiler_temperature,
        )
    except Exception as exc:
        return construction_failure("compiler", exc, checkpoint_1=checkpoint)
    try:
        compiler_evaluator_provider = _build_provider(
            role="compiler_evaluator",
            model=config.compiler_evaluator_model,
            temperature=config.compiler_evaluator_temperature,
        )
    except Exception as exc:
        return construction_failure(
            "compiler_evaluator", exc, checkpoint_1=checkpoint
        )
    return run_joined_probe(
        checkpoint_1=checkpoint,
        compiler_fixture_dir=compiler_control_dir,
        handoff_destination=config.run_root / "lm9b-c-handoff",
        compiler_run_root=config.run_root / "lm9b-c-runs",
        aggregate_destination=config.run_root / "joined-aggregate",
        compiler_provider=compiler_provider,
        compiler_evaluator_provider=compiler_evaluator_provider,
        compiler_identity=compiler_provider.identity,
        compiler_evaluator_identity=compiler_evaluator_provider.identity,
        git_sha=prepared.git_sha,
    )


def main(argv: list[str] | None = None) -> int:
    config = parse_cli_args(argv)
    prepared = prepare_pretransmission(config)
    print(json.dumps(prepared.summary, indent=2, sort_keys=True))
    if not config.transmit:
        return 0
    result = _execute_transmitted_attempt(prepared)
    checkpoint_1_classification = (
        result.checkpoint_1.classification
        if result.checkpoint_1 is not None
        else None
    )
    print(
        json.dumps(
            {
                "checkpoint_1": checkpoint_1_classification,
                "checkpoint_2": result.checkpoint_2,
                "aggregate_outcome": result.aggregate_outcome,
                "sealed_aggregate": (
                    result.sealed_aggregate.aggregate_identity
                    if result.sealed_aggregate is not None
                    else None
                ),
                "control_failure": result.control_failure,
            },
            sort_keys=True,
        )
    )
    return 0


__all__ = (
    "CliAttemptConfig",
    "CompilerControlRecord",
    "GitCheckoutState",
    "JoinedProbeResult",
    "PlannerCheckpointResult",
    "PreparedTransmission",
    "PRODUCTION_SCOPE_FILES",
    "assert_frozen_compiler_controls",
    "assert_frozen_planner_controls",
    "main",
    "parse_cli_args",
    "prepare_pretransmission",
    "run_joined_probe",
    "run_planner_checkpoint",
    "verify_scope_guards",
)


if __name__ == "__main__":
    raise SystemExit(main())
