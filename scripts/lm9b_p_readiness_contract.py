#!/usr/bin/env python
"""Pure LM9B-P readiness contract. Stdlib only — no Git/filesystem/clock/env I/O,
no provider imports. Callers supply configuration, SHA, time, env observations.

This module is imported by both the disposable readiness probe (which owns
provider contact) and the experiment CLI (which uses only verification). It must
never import provider code so that importing the verifier stays a pure
operation."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

FROZEN_MAX_AGE_S: int = 600
SCHEMA_ID: str = "lm9b_p.readiness_record:v1"


class ReadinessError(ValueError):
    """Raised when a readiness contract invariant is violated."""


# Closed, reviewed credential-source map. Names only, never values. Verified
# against installed LiteLLM 1.89.4 (OpenAI: OPENAI_API_KEY; Gemini completion
# get_api_key: GOOGLE_API_KEY then GEMINI_API_KEY). Presence is satisfied when
# at least one declared name is set.
CREDENTIAL_SOURCE_DECLARATIONS: dict[tuple[str, str], tuple[str, ...]] = {
    ("openai", "gpt-5.4"): ("OPENAI_API_KEY",),
    ("gemini", "gemini/gemini-3.1-pro-preview"): ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
}

CANONICAL_ROLE_MODELS: dict[str, str] = {
    "planner": "gpt-5.4",
    "planner_evaluator": "gpt-5.4",
    "compiler": "gemini/gemini-3.1-pro-preview",
    "compiler_evaluator": "gemini/gemini-3.1-pro-preview",
}

CANARY_SYSTEM = "You are a readiness canary."
CANARY_USER = "Call the ack tool."
# Generous ceiling (billed per actual token) so reasoning models — gpt-5.4 and
# gemini-3.1-pro — can spend hidden thinking tokens and still emit the complete
# forced ack tool call. The original 16 truncated the tool-call arguments.
CANARY_MAX_COMPLETION_TOKENS = 2048
CANARY_PROVIDER_TIMEOUT_S = 30.0
CANARY_TEMPERATURE = 0.0
ACK_TOOL = {
    "type": "function",
    "function": {
        "name": "ack",
        "description": "Acknowledge readiness.",
        "parameters": {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
    },
}


def _strict_json_object(text: str) -> object:
    """Parse JSON, rejecting duplicate object keys (plain json.loads silently
    keeps the last), so "strict JSON" in route_ready is actually strict."""

    def reject_duplicates(pairs):
        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate object keys")
        return dict(pairs)

    return json.loads(text, object_pairs_hook=reject_duplicates)


def canonical_fingerprint(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def provider_of(model: str) -> str:
    if model.startswith("gemini/"):
        return "gemini"
    if model.startswith("openai/"):
        return "openai"
    if model.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    raise ReadinessError(f"cannot determine provider for model {model!r}")


def resolve_credential_source(
    provider: str, model: str, helper_result: str | None
) -> tuple[str, ...]:
    declaration = CREDENTIAL_SOURCE_DECLARATIONS.get((provider, model))
    if declaration is None:
        raise ReadinessError(
            f"no credential-source declaration for {provider}/{model}"
        )
    if helper_result is not None and helper_result not in declaration:
        raise ReadinessError(
            f"canonical helper {helper_result!r} not in declaration for "
            f"{provider}/{model}"
        )
    return declaration


@dataclass(frozen=True)
class RoleRoute:
    role: str
    adapter_path: str
    provider: str
    model: str


@dataclass(frozen=True)
class DistinctRoute:
    route_fingerprint: str
    adapter_path: str
    provider: str
    model: str
    credential_source: tuple[str, ...]
    member_roles: tuple[str, ...]


@dataclass(frozen=True)
class RouteManifest:
    routes: tuple[DistinctRoute, ...]
    manifest_fingerprint: str


def role_routes_from_models(models: dict) -> tuple[RoleRoute, ...]:
    return tuple(
        RoleRoute(role, "litellm.completion", provider_of(model), model)
        for role, model in models.items()
    )


def derive_routes(
    role_routes: Sequence[RoleRoute], helper: Callable[[str], str | None]
) -> RouteManifest:
    groups: dict[tuple, list[str]] = {}
    meta: dict[tuple, tuple[str, str, str, tuple[str, ...]]] = {}
    for route in role_routes:
        cred = resolve_credential_source(
            route.provider, route.model, helper(route.model)
        )
        key = (route.adapter_path, route.provider, route.model, cred)
        groups.setdefault(key, []).append(route.role)
        meta[key] = (route.adapter_path, route.provider, route.model, cred)
    distinct: list[DistinctRoute] = []
    for key, roles in groups.items():
        adapter_path, provider, model, cred = meta[key]
        identity = {
            "adapter_path": adapter_path,
            "provider": provider,
            "model": model,
            "credential_source": list(cred),
        }
        distinct.append(
            DistinctRoute(
                route_fingerprint=canonical_fingerprint(identity),
                adapter_path=adapter_path,
                provider=provider,
                model=model,
                credential_source=cred,
                member_roles=tuple(sorted(roles)),
            )
        )
    distinct.sort(key=lambda r: r.route_fingerprint)
    return RouteManifest(
        routes=tuple(distinct),
        manifest_fingerprint=canonical_fingerprint(
            [r.route_fingerprint for r in distinct]
        ),
    )


def canary_protocol() -> dict:
    # Deep-copy the tool: build_canary_request hands the tool to a provider, and
    # some providers (e.g. Gemini) mutate tool schemas in place. Sharing the
    # module-level ACK_TOOL would let that mutation corrupt every fingerprint
    # computed afterward and desynchronize the record from the launch gate's
    # pristine recomputation. Each call returns an independent tool.
    return {
        "system": CANARY_SYSTEM,
        "user": CANARY_USER,
        "tool": copy.deepcopy(ACK_TOOL),
        "max_completion_tokens": CANARY_MAX_COMPLETION_TOKENS,
        "provider_timeout_s": CANARY_PROVIDER_TIMEOUT_S,
        "temperature": CANARY_TEMPERATURE,
    }


def canary_protocol_fingerprint() -> str:
    return canonical_fingerprint(canary_protocol())


def build_canary_request(route: DistinctRoute) -> dict:
    p = canary_protocol()
    return {
        "model": route.model,
        "messages": [
            {"role": "system", "content": p["system"]},
            {"role": "user", "content": p["user"]},
        ],
        "tools": [p["tool"]],
        "tool_choice": {"type": "function", "function": {"name": "ack"}},
        "max_completion_tokens": p["max_completion_tokens"],
        "provider_timeout_s": p["provider_timeout_s"],
    }


def request_fingerprint(route: DistinctRoute) -> str:
    return canonical_fingerprint(build_canary_request(route))


def route_ready(row: dict) -> bool:
    outcome = row.get("outcome")
    if not isinstance(outcome, dict) or outcome.get("kind") != "model_response":
        return False
    if outcome.get("assistant_present") is not True:
        return False
    calls = outcome.get("tool_calls")
    if not isinstance(calls, list) or len(calls) != 1:
        return False
    call = calls[0]
    if not isinstance(call, dict) or call.get("name") != "ack":
        return False
    arguments = call.get("arguments")
    # The frozen contract permits either the exact argument string or an
    # already-parsed closed object; a string is parsed strictly (duplicate keys
    # rejected). A fingerprint-only stand-in (neither str nor dict) is refused.
    if isinstance(arguments, str):
        try:
            parsed = _strict_json_object(arguments)
        except (ValueError, TypeError):
            return False
    elif isinstance(arguments, dict):
        parsed = arguments
    else:
        return False
    return parsed == {"ok": True}


def record_fingerprint(record: dict) -> str:
    return canonical_fingerprint(
        {k: v for k, v in record.items() if k != "record_fingerprint"}
    )


@dataclass(frozen=True)
class LaunchDecision:
    ok: bool
    failures: tuple[str, ...]


def _parse_utc(value: object) -> datetime:
    # Require an exact `YYYY-MM-DDTHH:MM:SSZ` UTC datetime. strptime with a
    # literal trailing `Z` rejects embedded offsets (e.g. `...+03:00Z`),
    # date-only forms (e.g. `2026-07-21Z`), fractional seconds, and any other
    # offset designator, so a malformed value can never be reinterpreted as UTC.
    if not isinstance(value, str):
        raise ReadinessError(f"timestamp is not a string: {value!r}")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ReadinessError(f"timestamp not exact UTC Z form: {value!r}") from exc
    return parsed.replace(tzinfo=timezone.utc)


def verify_launch_readiness(
    *,
    record: dict,
    manifest: RouteManifest,
    head_sha: str,
    now_iso: str,
    credential_present: dict,
) -> LaunchDecision:
    failures: list[str] = []

    def fail(message: str) -> None:
        failures.append(message)

    if record.get("schema_id") != SCHEMA_ID:
        fail("schema_id mismatch")
    if record.get("reviewed_commit_sha") != head_sha:
        fail("commit sha mismatch")
    if record.get("route_manifest_fingerprint") != manifest.manifest_fingerprint:
        fail("route manifest fingerprint mismatch")
    if record.get("record_fingerprint") != record_fingerprint(record):
        fail("record fingerprint mismatch")
    if record.get("canary_protocol_fingerprint") != canary_protocol_fingerprint():
        fail("canary protocol fingerprint mismatch")
    if record.get("max_age_seconds") != FROZEN_MAX_AGE_S:
        fail("max_age_seconds != frozen constant")

    rows = record.get("routes") if isinstance(record.get("routes"), list) else []
    by_fp = {r.route_fingerprint: r for r in manifest.routes}
    row_fps = [row.get("route_fingerprint") for row in rows]
    if len(row_fps) != len(set(row_fps)):
        fail("duplicate route rows")
    if set(row_fps) != set(by_fp):
        fail("route set != manifest")

    try:
        now = _parse_utc(now_iso)
        completed = _parse_utc(record.get("completed_at"))
        if not 0 <= (now - completed).total_seconds() <= FROZEN_MAX_AGE_S:
            fail("record completed_at outside freshness window")
        for row in rows:
            observed = _parse_utc(row.get("observed_at"))
            if completed < observed:
                fail("completed_at precedes observed_at")
            if not 0 <= (now - observed).total_seconds() <= FROZEN_MAX_AGE_S:
                fail("route observed_at outside freshness window")
    except ReadinessError as exc:
        fail(str(exc))

    for row in rows:
        fp = row.get("route_fingerprint")
        route = by_fp.get(fp)
        if route is None:
            continue
        if tuple(row.get("member_roles") or ()) != route.member_roles:
            fail(f"member roles differ for {fp}")
        if row.get("request_fingerprint") != request_fingerprint(route):
            fail(f"request fingerprint mismatch for {fp}")
        if credential_present.get(fp) is not True:
            fail(f"credential absent for {fp}")
        if not route_ready(row):
            fail(f"route not ready for {fp}")

    return LaunchDecision(ok=not failures, failures=tuple(failures))
