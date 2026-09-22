"""Inline Python must never be passed to python.exe as a `-c` native argument.

Windows PowerShell 5.1 re-quotes native command arguments and splits an inline
script at its embedded double quotes, so `"No broken requirements found."` leaks
`requirements` into sys.argv and the sealed-wheel origin probe fails with
FileNotFoundError. The probe is written to a temp file and run as a script instead.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARDED = (
    "scripts/deploy-local-testing.ps1",
    ".claude/skills/build-release/SKILL.md",
    ".agents/skills/build-release/SKILL.md",
)
INLINE_PROBE = re.compile(r"&\s+\$\w+\s+-I\s+-c\s+\$\w*[Pp]robe\b")


def test_no_inline_probe_passed_as_native_argument() -> None:
    for relative in GUARDED:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert INLINE_PROBE.search(text) is None, relative


def test_probe_runs_from_temp_file_and_is_cleaned_up() -> None:
    for relative in GUARDED:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "$originProbePath" in text, relative
        assert "[IO.File]::WriteAllText($originProbePath, $originProbe)" in text, relative
        assert "-I $originProbePath" in text, relative
        assert "[IO.File]::Delete($originProbePath)" in text, relative
        assert "if ($originProbeExit -ne 0)" in text, relative


def test_release_skill_mirrors_stay_identical() -> None:
    a = (REPO_ROOT / ".claude/skills/build-release/SKILL.md").read_bytes()
    b = (REPO_ROOT / ".agents/skills/build-release/SKILL.md").read_bytes()
    assert a == b
