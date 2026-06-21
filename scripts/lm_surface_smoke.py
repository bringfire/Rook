#!/usr/bin/env python3
"""LM live-smoke diagnostic (pre-LM2E).

Proves the DEPLOYED rook runtime (site-packages, empty PYTHONPATH) contains the
merged LM2A-D modules, and that the LM2A->D surface chain is sane against the
deployed runtime's own advertised catalog. Diagnostic only: it deploys nothing,
starts/stops nothing, writes nothing to the deployed runtime, and never adds
repo src to sys.path.

Run with the DEPLOYED venv interpreter and an empty PYTHONPATH, e.g. (PowerShell):
  $env:PYTHONPATH=""; & "<...>/Rook/venv/Scripts/python.exe" scripts/lm_surface_smoke.py coherence
"""
from __future__ import annotations

import argparse
import os
import sys


def pythonpath_clean(env_value: str) -> bool:
    """True iff PYTHONPATH is empty/whitespace-only."""
    return not env_value.strip()


def module_origin_ok(module_file: str, site_packages_root: str) -> bool:
    """True iff module_file is contained under site_packages_root.

    Real path containment via os.path.commonpath (not string startswith, which
    would false-pass a sibling like '.../site-packages2/rook'). Case-insensitive
    for Windows via normcase.
    """
    module_path = os.path.normcase(os.path.abspath(module_file))
    root_path = os.path.normcase(os.path.abspath(site_packages_root))
    try:
        return os.path.commonpath([module_path, root_path]) == root_path
    except ValueError:
        return False


def classify_cache(cache_keys, built_keys, required) -> str:
    """Cache tri-state vs. the in-process built catalog.

    - cache_keys is None        -> "absent"
    - no symmetric difference   -> "current"
    - difference touches required -> "fail"
    - otherwise                 -> "warning"
    """
    if cache_keys is None:
        return "absent"
    delta = set(cache_keys) ^ set(built_keys)
    if not delta:
        return "current"
    if delta & set(required):
        return "fail"
    return "warning"


def degenerate_activation_failures(group_failed_tools, catalog_group_names) -> tuple[str, ...]:
    """Groups that failed to activate despite being present in the catalog.

    A group genuinely absent from the catalog is allowed to fail; only a group
    with >=1 catalog member that still failed is the degenerate signal.
    """
    return tuple(sorted(set(group_failed_tools) & set(catalog_group_names)))


def format_surface_evidence(
    *,
    catalog_count: int,
    profile_name: str,
    intended_count: int,
    active_count: int,
    finding_histogram: dict,
    profile_findings_count: int,
) -> str:
    """Deterministic evidence block (histogram rendered in sorted code order)."""
    lines = [
        f"  catalog tools: {catalog_count}",
        f"  profile: {profile_name}",
        f"  intended: {intended_count}",
        f"  active: {active_count}",
        f"  profile_findings: {profile_findings_count}",
        "  registry_findings by code:",
    ]
    for code in sorted(finding_histogram):
        lines.append(f"    {code}: {finding_histogram[code]}")
    return "\n".join(lines)
