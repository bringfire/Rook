#!/usr/bin/env python
"""Disposable LM9B-P readiness probe. Owns provider contact via the production
LiteLLMProvider; imports the pure contract for all identity and verification
logic. The clock is injected so timestamp ordering is deterministic in tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_MCP_SRC = _SCRIPTS_DIR.parent / "mcp_server" / "src"
for _p in (_SCRIPTS_DIR, _MCP_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import lm9b_p_readiness_contract as CONTRACT
import lm9b_c_compiler_sufficiency_probe as LM9BC
from rook.agent.model_profiles import api_key_env_for_model

HELPER = api_key_env_for_model


def system_clock() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def credential_presence(manifest, environ) -> dict:
    return {
        route.route_fingerprint: any(
            bool(environ.get(name)) for name in route.credential_source
        )
        for route in manifest.routes
    }


def default_provider_factory(route):
    return LM9BC.LiteLLMProvider(
        model=route.model, temperature=CONTRACT.CANARY_TEMPERATURE
    )


def run_canary(route, provider, *, clock) -> dict:
    request = CONTRACT.build_canary_request(route)
    base = {
        "route_fingerprint": route.route_fingerprint,
        "member_roles": list(route.member_roles),
        "request_fingerprint": CONTRACT.request_fingerprint(route),
    }
    try:
        turn = provider(request)
    except LM9BC.ProviderCallFailure as exc:
        base["observed_at"] = clock()  # stamped AFTER the call resolves
        base["outcome"] = {
            "kind": "transport_failure",
            "classification": exc.failure_type,
            "detail_hash": "sha256:"
            + hashlib.sha256(exc.message.encode("utf-8")).hexdigest(),
        }
        return base
    base["observed_at"] = clock()  # stamped AFTER the call resolves
    message = turn.assistant_message
    # Observed, not authored: an attributable assistant message must actually be
    # present in the response.
    assistant_present = isinstance(message, dict) and bool(message)
    source = message if assistant_present else {}
    tool_calls = [
        {
            "name": (call.get("function") or {}).get("name"),
            "arguments": (call.get("function") or {}).get("arguments"),
        }
        for call in (source.get("tool_calls") or [])
    ]
    base["outcome"] = {
        "kind": "model_response",
        "assistant_present": assistant_present,
        "tool_calls": tool_calls,
        "raw_response_fingerprint": "sha256:"
        + hashlib.sha256(turn.raw_response).hexdigest(),
    }
    return base


def assemble_record(*, manifest, head_sha, completed_at, route_rows) -> dict:
    record = {
        "schema_id": CONTRACT.SCHEMA_ID,
        "reviewed_commit_sha": head_sha,
        "route_manifest_fingerprint": manifest.manifest_fingerprint,
        "canary_protocol_fingerprint": CONTRACT.canary_protocol_fingerprint(),
        "max_age_seconds": CONTRACT.FROZEN_MAX_AGE_S,
        "completed_at": completed_at,
        "routes": list(route_rows),
    }
    record["record_fingerprint"] = CONTRACT.record_fingerprint(record)
    return record


def run_readiness(
    *,
    run_root,
    head_sha,
    environ,
    authenticate,
    provider_factory,
    clock=system_clock,
    models=None,
) -> dict:
    models = dict(models or CONTRACT.CANONICAL_ROLE_MODELS)
    manifest = CONTRACT.derive_routes(
        CONTRACT.role_routes_from_models(models), HELPER
    )
    presence = credential_presence(manifest, environ)
    # Credential check BEFORE creating the readiness root, so correcting a
    # credential does not leave an unusable empty directory behind.
    if authenticate and not all(presence.values()):
        raise CONTRACT.ReadinessError("preflight failed: credential absent")
    run_root = Path(run_root)
    run_root.mkdir(parents=True, exist_ok=False)
    rows = []
    if authenticate:
        for route in manifest.routes:
            rows.append(run_canary(route, provider_factory(route), clock=clock))
    completed_at = clock()  # AFTER all route observations
    record = assemble_record(
        manifest=manifest,
        head_sha=head_sha,
        completed_at=completed_at,
        route_rows=rows,
    )
    (run_root / "readiness_record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True), encoding="utf-8"
    )
    (run_root / "preflight.json").write_text(
        json.dumps({"credential_present": presence}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return record


def main(argv=None) -> int:
    import os

    parser = argparse.ArgumentParser(
        description="LM9B-P readiness probe",
        epilog=(
            "For the evaluator-only continuation, select exactly "
            "--role planner_evaluator --authenticate."
        ),
    )
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--reviewed-commit-sha", required=True)
    parser.add_argument("--authenticate", action="store_true")
    parser.add_argument(
        "--role",
        action="append",
        choices=tuple(CONTRACT.CANONICAL_ROLE_MODELS),
        help="limit readiness to a canonical member role; repeatable",
    )
    args = parser.parse_args(argv)
    selected_models = (
        {
            role: CONTRACT.CANONICAL_ROLE_MODELS[role]
            for role in dict.fromkeys(args.role)
        }
        if args.role
        else dict(CONTRACT.CANONICAL_ROLE_MODELS)
    )
    record = run_readiness(
        run_root=args.run_root,
        head_sha=args.reviewed_commit_sha,
        environ=dict(os.environ),
        authenticate=args.authenticate,
        provider_factory=default_provider_factory,
        clock=system_clock,
        models=selected_models,
    )
    ready = bool(record["routes"]) and all(
        CONTRACT.route_ready(row) for row in record["routes"]
    )
    print(
        json.dumps(
            {"authenticated": args.authenticate, "ready": ready}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
