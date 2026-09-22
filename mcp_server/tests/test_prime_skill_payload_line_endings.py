"""The packaged rook-full skill must check out as LF on every machine.

verify-installed-rookchat-acp.py compares the working-tree bytes of
installer/agent-assets/prime-skills/rook-full against the bytes packaged into the
Prime runtime (which are the LF git blobs). With core.autocrlf=true and no
attribute, Windows checkouts produce CRLF and the verifier refuses with
"installed Rook skill differs from reviewed source".
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO_ROOT / "installer" / "agent-assets" / "prime-skills"


def _tracked_skill_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--", "installer/agent-assets/prime-skills"],
        check=True, capture_output=True, text=True,
    ).stdout.split()
    assert out, "no tracked prime-skill files"
    return out


def test_prime_skill_payload_has_lf_attribute() -> None:
    files = _tracked_skill_files()
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "check-attr", "eol", "--", *files],
        check=True, capture_output=True, text=True,
    ).stdout
    for line in out.strip().splitlines():
        assert line.endswith(": eol: lf"), line


def test_prime_skill_payload_working_tree_is_lf() -> None:
    for relative in _tracked_skill_files():
        data = (REPO_ROOT / relative).read_bytes()
        assert b"\r" not in data, relative
