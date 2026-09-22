"""The tracked Prime runtime pin must agree with the commits the chat runtime pins.

scripts/prime/rook-prime-runtime-source.json is what a source build downloads;
rook.agent.chat.prime_runtime_artifact is what the installed verifier trusts.
If either moves without the other, RookChat fails closed with runtime_unavailable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from rook.agent.chat import prime_runtime_artifact as artifact

REPO_ROOT = Path(__file__).resolve().parents[2]
PIN_PATH = REPO_ROOT / "scripts" / "prime" / "rook-prime-runtime-source.json"
FETCH_PATH = REPO_ROOT / "scripts" / "prime" / "fetch-prime-runtime.ps1"
SHA256 = re.compile(r"[A-F0-9]{64}\Z")
COMMIT = re.compile(r"[a-f0-9]{40}\Z")


def _pin() -> dict:
    return json.loads(PIN_PATH.read_text(encoding="utf-8"))


def test_pin_matches_code_pinned_commits() -> None:
    pin = _pin()
    assert pin["prime_commit"] == artifact.PRIME_COMMIT
    assert pin["upstream_base_commit"] == artifact.UPSTREAM_COMMIT
    assert pin["uv_version"] == artifact.UV["version"]


def test_pin_identities_are_well_formed() -> None:
    pin = _pin()
    assert pin["schema_version"] == 1
    for key in ("prime_commit", "prime_parent_commit", "upstream_base_commit"):
        assert COMMIT.fullmatch(pin[key]), key
    for key in ("runtime_asset_sha256", "runtime_id", "prime_zip_sha256"):
        assert SHA256.fullmatch(pin[key]), key
    assert isinstance(pin["runtime_asset_bytes"], int) and pin["runtime_asset_bytes"] > 0


def test_pin_release_coordinates_are_consistent() -> None:
    pin = _pin()
    repo = pin["prime_repository"].rstrip("/")
    tag = pin["release_tag"]
    assert tag.endswith(pin["prime_commit"][:8])
    assert pin["release_url"] == f"{repo}/releases/tag/{tag}"
    assert pin["runtime_asset_url"] == f"{repo}/releases/download/{tag}/{pin['runtime_asset']}"
    assert pin["runtime_asset"].endswith(".zip")


def test_pin_points_at_tracked_scripts() -> None:
    pin = _pin()
    for key in ("rebuild_script", "assembly_script", "fetch_script"):
        assert (REPO_ROOT / pin[key]).is_file(), pin[key]
    text = FETCH_PATH.read_text(encoding="utf-8")
    assert "rook-prime-runtime-source.json" in text
    assert "prime_runtime_artifact verify" in text
