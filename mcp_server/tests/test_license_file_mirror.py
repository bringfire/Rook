"""The Python project ships a staged copy of the repository LICENSE.

Wheel metadata may only reference license files inside the project directory
(a parent-relative path such as ``../LICENSE`` yields ``License-File: ../LICENSE``,
which index tooling rejects), so ``mcp_server/LICENSE`` is a copy of the root
``LICENSE``. This test keeps the two from drifting.
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_python_project_license_is_a_byte_identical_copy_of_the_repo_license():
    root = (_ROOT / "LICENSE").read_bytes()
    staged = (_ROOT / "mcp_server" / "LICENSE").read_bytes()
    assert staged == root, "mcp_server/LICENSE must be byte-identical to the repository LICENSE"


def test_pyproject_declares_the_staged_license_file():
    text = (_ROOT / "mcp_server" / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = "MIT"' in text
    assert 'license-files = ["LICENSE"]' in text
    assert "../LICENSE" not in text
