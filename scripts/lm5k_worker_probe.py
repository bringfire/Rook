#!/usr/bin/env python
"""LM5K first worker model probe — evidence harness, never a CI gate.

Runs the golden repair-workflow envelope against a three-slot model panel
through the production LiteLLMWorkerTransport and the LM5J adapter, then
evaluates loaded responses through the LM5B/C/D/F spine. Writes evidence
artifacts to a gitignored probe_runs/ directory.

Doctrine: probe results are evidence, not pass/fail. See
docs/superpowers/specs/2026-07-02-lm5k-first-worker-model-probe-design.md
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SLOTS = ("local", "cheap", "ceiling")
SLOT_LABELS = {
    "local": "local_worker_candidate",
    "cheap": "cheap_cloud_worker_candidate",
    "ceiling": "ceiling_worker_candidate",
}
ENV_VARS = {
    "local": "ROOK_PROBE_LOCAL_WORKER",
    "cheap": "ROOK_PROBE_CHEAP_CLOUD_WORKER",
    "ceiling": "ROOK_PROBE_CEILING_WORKER",
}
GENERATION_PARAMS = {"temperature": 0}
DEFAULT_ATTEMPTS = 5
SCENARIO_WORKFLOW_ID = "lm5k_first_probe"

_LOCAL_PREFIXES = ("ollama_chat/", "ollama/")


def parse_candidate_spec(spec: str) -> tuple[str, str | None]:
    """'model[@api_base]' -> (model, api_base or None)."""
    model, sep, api_base = spec.partition("@")
    if not model:
        raise ValueError(f"invalid candidate spec: {spec!r}")
    return model, (api_base if sep and api_base else None)


def profile_inferred_local(
    worker_model: str, profile_api_base: str | None
) -> tuple[str, str | None] | None:
    """Safe profile inference for the LOCAL slot only (spec 4.1 rule 3)."""
    if worker_model.startswith(_LOCAL_PREFIXES):
        return worker_model, profile_api_base
    if worker_model.startswith("openai/") and profile_api_base:
        return worker_model, profile_api_base
    return None


def resolve_slot(
    slot: str,
    cli_value: str | None,
    env_value: str | None,
    profile_worker: str,
    profile_api_base: str | None,
    skipped: bool,
) -> dict:
    """Resolve one panel slot. status None means resolved-and-runnable."""
    base = {"slot": slot, "label": SLOT_LABELS[slot]}
    if skipped:
        return {**base, "model": None, "api_base": None,
                "source": "skip", "status": "skipped"}
    if cli_value:
        model, api_base = parse_candidate_spec(cli_value)
        return {**base, "model": model, "api_base": api_base,
                "source": "cli", "status": None}
    if env_value:
        model, api_base = parse_candidate_spec(env_value)
        return {**base, "model": model, "api_base": api_base,
                "source": "env", "status": None}
    if slot == "local":
        inferred = profile_inferred_local(profile_worker, profile_api_base)
        if inferred is not None:
            model, api_base = inferred
            return {**base, "model": model, "api_base": api_base,
                    "source": "profile", "status": None}
    return {**base, "model": None, "api_base": None,
            "source": "none", "status": "unavailable"}


def classify_candidate_status(adapter_statuses: list) -> str:
    """For an attempted candidate: transport_error iff ALL attempts were.

    An attempted candidate has at least one attempt by definition —
    all([]) is vacuously true and would fabricate transport_error from
    zero evidence, so empty input is a caller error.
    """
    if not adapter_statuses:
        raise ValueError("attempted candidate requires at least one attempt")
    if all(status == "transport_error" for status in adapter_statuses):
        return "transport_error"
    return "ran"


def attempt_metrics(attempt: Mapping[str, Any]) -> tuple[bool, bool]:
    """(strict_loadable, spine_passed) for one attempt record."""
    strict = attempt["adapter_status"] == "response_loaded"
    spine = strict and attempt.get("evaluation_passed") is True
    return strict, spine
