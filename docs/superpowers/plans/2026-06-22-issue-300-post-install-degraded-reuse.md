# #300 post_install Degraded-Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `deploy-local-testing.ps1` (release) complete without a manual source mirror when the bundled private CPython is absent but a usable release venv already exists — by reusing that venv (after a liveness probe) instead of aborting.

**Architecture:** A single degraded-reuse branch in `installer/post_install.py` `_install_from_wheelhouse`, plus a minimal `_venv_python_is_usable` liveness probe. No PowerShell, runtime, or venv-creation changes; the existing release flow already runs `Install-ReleaseSourceIntoVenv` + `Test-EffectiveRuntime` after post_install.

**Tech Stack:** Python 3.12, pytest.

## Global Constraints

- **Reuse-only.** Do NOT create a venv from `sys.executable` / system Python; do NOT recreate or modify the existing venv.
- **Probe before reuse (watchpoint 1):** an existing `python.exe` is "usable" only if it runs a trivial command successfully — guard against a corrupt/half-deleted venv.
- **Unmistakable warning (watchpoint 2):** the degraded log/print must say this is degraded local-deploy reuse because bundled-runtime inputs are missing, and that the downstream source mirror + runtime verification must still prove coherence.
- Do NOT bootstrap post_install with the target venv (unchanged — PS `Resolve-BootstrapPython`). Do NOT weaken `Test-EffectiveRuntime`. Success = "mirror ran + verification proved current `rook.server` imports", not "post_install exit 0".
- No changes to `_create_venv`, `_ensure_private_runtime_inputs`, `python_runtime_install.py`, or any `rook/agent/*` module. No LM/runtime behavior change.
- Test commands run from the repo root (`C:\UDEV\Rook`) with the repo venv: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider ...`.

## File Structure

- `installer/post_install.py` (modify) — add `_venv_python_is_usable`; add the degraded-reuse branch in `_install_from_wheelhouse`.
- `mcp_server/tests/test_post_install_degraded_reuse.py` (new) — probe + branch tests.

---

### Task 1: Degraded-reuse with liveness probe

**Files:**
- Modify: `installer/post_install.py` (`_install_from_wheelhouse` opens at line 402; `_run_install_command` at 159; `get_venv_python` at 141; `_INSTALL_LOGGER` at 37)
- Create: `mcp_server/tests/test_post_install_degraded_reuse.py`

**Interfaces:**
- Consumes: `_run_install_command`, `get_venv_python`, `_record_venv_rebuild_summary`, `_read_install_summary`, `python_runtime_install.{RuntimeLayout, build_sanitized_python_env}`, `PRIVATE_PYTHON_VERSION`.
- Produces: `_venv_python_is_usable(venv_python: Path) -> bool`; degraded-reuse behavior in `_install_from_wheelhouse` (returns the existing venv python with summary outcome `"reused_existing"` when inputs incomplete + venv usable; `None`/`"failed"` otherwise).

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_post_install_degraded_reuse.py`:

```python
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

    result = module._install_from_wheelhouse(
        "rook-mcp", layout, layout.rook_venv, layout.rook_lock, "rook"
    )
    assert result == sentinel
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_post_install_degraded_reuse.py -v`
Expected: `test_probe_true_...` fails with `AttributeError: module ... has no attribute '_venv_python_is_usable'`; `test_degraded_reuse_...` fails (current code returns `None` / records `"failed"`, not `"reused_existing"`). `test_unusable_or_absent_...` may already pass (current code returns `None`/`"failed"`). `test_inputs_present_...` likely passes already (happy path unchanged) — that's fine; it's a guard against regression.

- [ ] **Step 3: Implement the probe + degraded-reuse branch**

In `installer/post_install.py`, add `_venv_python_is_usable` just above `_install_from_wheelhouse` (after `_collect_rebuild_guard_health`, before `_install_from_wheelhouse_once` is fine — place it directly above `_install_from_wheelhouse`):

```python
def _venv_python_is_usable(venv_python: Path) -> bool:
    """Minimal liveness probe for degraded reuse (#300).

    An existing venv interpreter is only reusable if it actually runs. This
    guards against reusing a corrupt/half-deleted venv, which would otherwise
    let post_install continue and fail later with a confusing error.
    """
    if not venv_python.exists():
        return False
    try:
        result = _run_install_command(
            [str(venv_python), "-c", "import sys; sys.exit(0)"],
            env=python_runtime_install.build_sanitized_python_env(
                require_virtualenv=False
            ),
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _INSTALL_LOGGER.warning("venv liveness probe could not run %s: %r", venv_python, exc)
        return False
    return result.returncode == 0
```

Then replace the opening guard of `_install_from_wheelhouse` (currently):

```python
    if not _ensure_private_runtime_inputs(layout, lock):
        _record_venv_rebuild_summary(
            layout.rook_root, runtime_name, label, 0, "failed", "inputs"
        )
        return None
```

with:

```python
    if not _ensure_private_runtime_inputs(layout, lock):
        existing_python = get_venv_python(venv_dir)
        if _venv_python_is_usable(existing_python):
            _INSTALL_LOGGER.warning(
                "%s: DEGRADED local-deploy reuse -- bundled private runtime/"
                "wheelhouse inputs are missing; reusing the existing venv at %s "
                "WITHOUT rebuild or wheelhouse install. This is NOT a clean "
                "install. The downstream source mirror and runtime verification "
                "(Test-EffectiveRuntime) must still prove the deployed "
                "site-packages imports the current rook.server. See #300.",
                label,
                existing_python,
            )
            print(
                f"{label}: DEGRADED reuse of existing venv at {existing_python} "
                f"(bundled private runtime inputs incomplete; no rebuild, no "
                f"wheelhouse install). Source mirror + runtime verification still "
                f"required downstream. See #300."
            )
            _record_venv_rebuild_summary(
                layout.rook_root, runtime_name, label, 0, "reused_existing", "inputs"
            )
            return existing_python
        _record_venv_rebuild_summary(
            layout.rook_root, runtime_name, label, 0, "failed", "inputs"
        )
        return None
```

(`subprocess` and `python_runtime_install` are already imported in this module; `_run_install_command`, `get_venv_python`, `_record_venv_rebuild_summary`, and `_INSTALL_LOGGER` already exist.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_post_install_degraded_reuse.py -v`
Expected: all 4 PASS.

- [ ] **Step 5: Regression — installer tests + py_compile**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_post_install_degraded_reuse.py mcp_server/tests/test_post_install_encoding.py mcp_server/tests/test_python_runtime_install.py -v
mcp_server/.venv/Scripts/python.exe -m py_compile installer/post_install.py
```
Expected: all PASS; py_compile silent.

- [ ] **Step 6: Commit**

```bash
git add installer/post_install.py mcp_server/tests/test_post_install_degraded_reuse.py
git commit -m "fix(300): post_install degraded-reuse of existing venv when bundled cpython absent"
```

---

## Post-implementation (controller, not a task)

After Task 1 + the final whole-branch review:
- Open a PR `codex/issue-300-post-install-degraded-reuse` → `main`. **Stop before merge — explicit human approval required (no self-merge).**
- After merge, verify on this box (bundled CPython absent): run `scripts/deploy-local-testing.ps1 -Configuration Release -SkipBuild` and confirm it passes the MCP/post_install step via degraded reuse (no manual mirror) and reaches `Install-ReleaseSourceIntoVenv` + `Test-EffectiveRuntime`. Then re-run the LM deployed smoke (`coherence`/`surface`/`external`) — all PASS. (If the full deploy fails at an unrelated later step, that is out of #300 scope.)
- Close #300; update campaign memory (and correct the stale `chore/dev-infra` note).
