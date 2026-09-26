"""#300 — post_install degraded-reuse when the bundled private CPython is absent.

When _ensure_private_runtime_inputs fails (no bundled runtime/wheelhouse) but a
usable release venv already exists, _install_from_wheelhouse must reuse it (after
a liveness probe) so a local source deploy can proceed to the canonical source
mirror + runtime verification instead of aborting.
"""

from __future__ import annotations

import contextlib
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
POST_INSTALL = REPO_ROOT / "installer" / "post_install.py"


def _load_post_install():
    if str(POST_INSTALL.parent) not in sys.path:
        sys.path.insert(0, str(POST_INSTALL.parent))
    spec = importlib.util.spec_from_file_location("rook_post_install", POST_INSTALL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _layout(module, tmp_path: Path):
    layout = module.python_runtime_install.RuntimeLayout.from_rook_root(
        tmp_path, module.PRIVATE_PYTHON_VERSION
    )
    (layout.rook_root / "logs").mkdir(parents=True, exist_ok=True)
    return layout


def test_probe_true_for_real_interpreter_false_for_bogus(tmp_path):
    module = _load_post_install()
    assert module._venv_python_is_usable(Path(sys.executable)) is True
    assert module._venv_python_is_usable(tmp_path / "nope.exe") is False


def test_degraded_reuse_returns_existing_venv(tmp_path, monkeypatch):
    module = _load_post_install()
    layout = _layout(module, tmp_path)
    monkeypatch.setattr(module, "_ensure_private_runtime_inputs", lambda *a, **k: False)
    monkeypatch.setattr(module, "_venv_python_is_usable", lambda p: True)

    result = module._install_from_wheelhouse(
        "rook-mcp", layout, layout.rook_venv, layout.rook_lock, "rook"
    )
    assert result == module.get_venv_python(layout.rook_venv)

    summary = module._read_install_summary(layout.rook_root)
    assert summary["venv_rebuilds"]["rook"]["outcome"] == "reused_existing"


def test_unusable_or_absent_venv_fails(tmp_path, monkeypatch):
    module = _load_post_install()
    layout = _layout(module, tmp_path)
    monkeypatch.setattr(module, "_ensure_private_runtime_inputs", lambda *a, **k: False)
    monkeypatch.setattr(module, "_venv_python_is_usable", lambda p: False)

    result = module._install_from_wheelhouse(
        "rook-mcp", layout, layout.rook_venv, layout.rook_lock, "rook"
    )
    assert result is None

    summary = module._read_install_summary(layout.rook_root)
    assert summary["venv_rebuilds"]["rook"]["outcome"] == "failed"


def test_inputs_present_bypasses_degraded_branch(tmp_path, monkeypatch):
    module = _load_post_install()
    layout = _layout(module, tmp_path)
    sentinel = layout.rook_venv / "Scripts" / "python.exe"
    monkeypatch.setattr(module, "_ensure_private_runtime_inputs", lambda *a, **k: True)
    # When inputs are "present", _install_from_wheelhouse hashes the runtime
    # manifest + lock before reaching the guard; stub those so the test needs no
    # real files and stays focused on the branch-bypass behavior.
    monkeypatch.setattr(
        module.python_runtime_install, "sha256_file", lambda p: "stub-hash"
    )
    monkeypatch.setattr(
        module, "_install_from_wheelhouse_once", lambda *a, **k: (sentinel, None)
    )

    class _StubGuard:
        close_failures: list = []
        thread_died_unexpectedly = False

    @contextlib.contextmanager
    def _noop_guard(label, root):
        yield _StubGuard()

    monkeypatch.setattr(module, "_make_rebuild_guard", _noop_guard)

    # Stub the pip check, freeze comparison and uv evidence that run after
    # _install_from_wheelhouse_once succeeds.
    stub_result = type('obj', (object,), {'returncode': 0, 'stdout': '', 'stderr': ''})()
    monkeypatch.setattr(module, "_run_install_command", lambda *a, **k: stub_result)
    monkeypatch.setattr(module.python_runtime_install, "freeze_mismatches", lambda *a, **k: [])
    stub_uv = type('uv', (object,), {'evidence': lambda self: {'name': 'uv'}})()
    monkeypatch.setattr(module, "_bundled_uv", lambda layout: stub_uv)

    result = module._install_from_wheelhouse(
        "rook-mcp", layout, layout.rook_venv, layout.rook_lock, "rook"
    )
    assert result == sentinel
