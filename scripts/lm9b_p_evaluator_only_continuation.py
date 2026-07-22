#!/usr/bin/env python3
"""No-contact preflight for the LM9B-P evaluator-only continuation."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence


_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _import_path in (_SCRIPTS_DIR, _MCP_SRC):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

import lm9b_p_evaluator_only_continuation_artifacts as CONT_ARTIFACTS
import lm9b_p_planner_recipe_transfer_probe as PLANNER_PROBE


CORRECTED_RUBRIC_PATH = (
    _SCRIPTS_DIR / "lm9b_p_fixtures" / "planner_evaluation_rubric.json"
)


@dataclass(frozen=True)
class PreflightConfig:
    output_dir: Path
    reviewed_commit_sha: str
    attempt_id: str
    derivative_root: Path
    destination: Path
    launch_eligibility: Literal[
        "development_non_operational",
        "operator_review_candidate",
    ]


def _git_checkout_state() -> tuple[str, bool]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return head, not bool(status.strip())


def _build_evaluator_provider() -> object:
    """Construct the existing evaluator adapter; preflight never calls this."""

    return PLANNER_PROBE.build_planner_evaluator_provider(
        model=CONT_ARTIFACTS.EVALUATOR_MODEL,
        temperature=CONT_ARTIFACTS.EVALUATOR_TEMPERATURE,
    )


def emit_no_contact_preflight(
    config: PreflightConfig,
) -> CONT_ARTIFACTS.VerifiedContinuationPreflight:
    head, clean = _git_checkout_state()
    if not clean or head != config.reviewed_commit_sha:
        raise RuntimeError("preflight requires the clean reviewed commit")
    source = CONT_ARTIFACTS.verify_historical_source()
    corrected_rubric_bytes = CORRECTED_RUBRIC_PATH.read_bytes()
    instrument = CONT_ARTIFACTS.assemble_continuation_instrument(
        source,
        corrected_rubric_bytes=corrected_rubric_bytes,
        reviewed_commit_sha=head,
    )
    attempt = CONT_ARTIFACTS.bind_attempt(
        instrument_fingerprint=instrument.instrument_fingerprint,
        attempt_id=config.attempt_id,
        derivative_root=config.derivative_root,
        destination=config.destination,
    )
    return CONT_ARTIFACTS.write_preflight_archive(
        output_dir=config.output_dir,
        reviewed_commit_sha=head,
        launch_eligibility=config.launch_eligibility,
        instrument=instrument,
        attempt=attempt,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LM9B-P evaluator-only derivative continuation"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser(
        "preflight",
        help="emit a content-addressed preflight without provider contact",
    )
    preflight.add_argument("--output-dir", type=Path, required=True)
    preflight.add_argument("--reviewed-commit-sha", required=True)
    preflight.add_argument("--attempt-id", required=True)
    preflight.add_argument("--derivative-root", type=Path, required=True)
    preflight.add_argument("--destination", type=Path, required=True)
    eligibility = preflight.add_mutually_exclusive_group(required=True)
    eligibility.add_argument("--development-witness", action="store_true")
    eligibility.add_argument("--operator-review-candidate", action="store_true")

    verify = subparsers.add_parser(
        "verify-preflight",
        help="verify a closed preflight archive",
    )
    verify.add_argument("--preflight-dir", type=Path, required=True)
    verify.add_argument("--expected-fingerprint", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "preflight":
        launch_eligibility = (
            "operator_review_candidate"
            if args.operator_review_candidate
            else "development_non_operational"
        )
        verified = emit_no_contact_preflight(
            PreflightConfig(
                output_dir=args.output_dir,
                reviewed_commit_sha=args.reviewed_commit_sha,
                attempt_id=args.attempt_id,
                derivative_root=args.derivative_root,
                destination=args.destination,
                launch_eligibility=launch_eligibility,
            )
        )
    elif args.command == "verify-preflight":
        verified = CONT_ARTIFACTS.verify_preflight_archive(
            args.preflight_dir,
            expected_preflight_fingerprint=args.expected_fingerprint,
        )
    else:  # pragma: no cover - argparse closes this vocabulary.
        raise AssertionError(f"unsupported command: {args.command}")
    print(
        json.dumps(
            {
                "preflight_fingerprint": verified.preflight_fingerprint,
                "instrument_fingerprint": verified.instrument_fingerprint,
                "attempt_fingerprint": verified.attempt_fingerprint,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = (
    "CORRECTED_RUBRIC_PATH",
    "PreflightConfig",
    "_build_evaluator_provider",
    "_git_checkout_state",
    "emit_no_contact_preflight",
    "main",
)
