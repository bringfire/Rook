from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


def load_runtime_install():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "installer" / "python_runtime_install.py"
    spec = importlib.util.spec_from_file_location("rook_python_runtime_install", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_post_install():
    repo_root = Path(__file__).resolve().parents[2]
    installer_dir = repo_root / "installer"
    sys.path.insert(0, str(installer_dir))
    try:
        module_path = installer_dir / "post_install.py"
        spec = importlib.util.spec_from_file_location("rook_post_install", module_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(installer_dir))


def test_pip_command_is_offline_and_hash_locked(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    command = runtime.build_offline_pip_install_command(
        tmp_path / "venv" / "Scripts" / "python.exe",
        tmp_path / "wheelhouse",
        tmp_path / "requirements-rook-lock.txt",
    )

    assert command[:4] == [
        str(tmp_path / "venv" / "Scripts" / "python.exe"),
        "-m",
        "pip",
        "--isolated",
    ]
    assert "install" in command
    assert "--no-index" in command
    assert "--find-links" in command
    assert "--require-hashes" in command
    assert "--index-url" not in command
    assert "--extra-index-url" not in command


def test_bootstrap_pip_command_is_offline_and_hash_locked(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    command = runtime.build_offline_pip_bootstrap_command(
        tmp_path / "venv" / "Scripts" / "python.exe",
        tmp_path / "wheelhouse",
        tmp_path / "requirements-bootstrap-lock.txt",
    )

    runtime.assert_offline_pip_command(command)
    assert "requirements-bootstrap-lock.txt" in command[-1]
    assert "--no-index" in command
    assert "--find-links" in command
    assert "--require-hashes" in command


def test_bootstrap_tool_requirements_pin_patched_pip_and_setuptools() -> None:
    runtime = load_runtime_install()

    assert runtime.BOOTSTRAP_TOOL_REQUIREMENTS == (
        "pip==26.2.1",
        "setuptools==83.0.0",
    )


@pytest.mark.parametrize("module", ["rook", "chirp"])
def test_bootstrap_wheel_lock_reaches_temp_and_customer_installs(
    tmp_path: Path, monkeypatch, module: str,
) -> None:
    runtime = load_runtime_install()
    post_install = load_post_install()
    repo = Path(__file__).resolve().parents[2]
    builder = repo / "scripts/python-runtime/build-rook-python-wheelhouse.ps1"
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")
    layout.wheelhouse.mkdir(parents=True)
    pip_bytes = b"fixture-only reviewed pip wheel"
    (layout.wheelhouse / "pip-26.2.1-py3-none-any.whl").write_bytes(pip_bytes)
    (layout.wheelhouse / "pip-26.1.2-py3-none-any.whl").write_bytes(b"obsolete wheel")
    (layout.wheelhouse / "setuptools-83.0.0-py3-none-any.whl").write_bytes(b"setuptools")

    # Run the real selection/lock statements, replacing only the two download calls.
    # No wheel, venv, network, audit or product process is executed by this fixture.
    ps = r"""
$ErrorActionPreference = 'Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:TEST_BUILDER,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Builder syntax failure' }
$statements=@($ast.EndBlock.Statements)
$start=@($statements | Where-Object { $_ -is [System.Management.Automation.Language.AssignmentStatementAst] -and $_.Left.Extent.Text -ceq '$bootstrapToolPackages' })
$end=@($statements | Where-Object { $_ -is [System.Management.Automation.Language.AssignmentStatementAst] -and $_.Left.Extent.Text -ceq '$lockScript' })
if ($start.Count -ne 1 -or $end.Count -ne 1) { throw 'Bootstrap boundary differs' }
$hashFn=@($ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq 'Get-Sha256'},$true))
if ($hashFn.Count -ne 1) { throw 'Hash function differs' }
. ([scriptblock]::Create($hashFn[0].Extent.Text))
function Fail { param($Message) throw $Message }
$calls=[System.Collections.Generic.List[object]]::new()
function Invoke-CheckedProcess {
    param($FilePath, $Arguments, $Label)
    if ($Label -notin @('bootstrap tool wheel download','dependency wheel download')) { throw 'Unexpected process' }
    $calls.Add(@{file=$FilePath; argv=@($Arguments); label=$Label})
}
$OutputRoot=$env:TEST_OUTPUT
$wheelhouse=Join-Path $OutputRoot 'python-wheelhouse'
$pythonExe=Join-Path $OutputRoot 'private-python.exe'
$buildPythonExe=Join-Path $OutputRoot 'build-python.exe'
$rookWheel=@{FullName='fixture-rook.whl'}; $chirpWheel=@{FullName='fixture-chirp.whl'}
$text=$ast.Extent.Text.Substring($start[0].Extent.StartOffset,$end[0].Extent.StartOffset-$start[0].Extent.StartOffset)
. ([scriptblock]::Create($text))
$calls | ConvertTo-Json -Depth 4 -Compress
"""
    env = os.environ | {"TEST_BUILDER": str(builder), "TEST_OUTPUT": str(layout.app_dir)}
    observed = subprocess.run(
        ["C:/Program Files/PowerShell/7/pwsh.exe", "-NoProfile", "-Command", ps],
        env=env, text=True, capture_output=True, timeout=30, check=True,
    )
    calls = json.loads(observed.stdout)
    assert len(calls) == 2
    assert calls[0]["argv"][-2:] == ["pip==26.2.1", "setuptools==83.0.0"]
    assert all(call["file"] == str(layout.app_dir / "build-python.exe") for call in calls)
    lock_text = layout.bootstrap_lock.read_text(encoding="utf-8-sig")
    assert f"pip==26.2.1 --hash=sha256:{hashlib.sha256(pip_bytes).hexdigest()}" in lock_text
    assert "26.1.2" not in lock_text

    # Execute the actual generated verification entrypoint with subprocess.run faked.
    source = builder.read_text(encoding="utf-8-sig")
    scripts = [body for body, name in re.findall(
        r"(?ms)^@'\n(.*?)\n'@ \| Set-Content -LiteralPath \$(\w+)", source,
    ) if name == "verificationScript"]
    assert len(scripts) == 1
    ns = {"__name__": "bootstrap_verification_fixture"}
    exec(compile(scripts[0], str(builder) + ":verificationScript", "exec"), ns)
    venv = tmp_path / "verification"
    site = venv / "Lib/site-packages"
    package_lock = layout.rook_lock if module == "rook" else layout.chirp_lock
    package_lock.write_text(f"{module}==0.0.0 --hash=sha256:fixture\n", encoding="utf-8")
    selected = []

    def fake_run(command, **kwargs):
        if command[1:3] == ["-m", "venv"]:
            Path(command[3]).mkdir()
            output = ""
        elif "-r" in command:
            assert {"--isolated", "--no-index", "--require-hashes"} <= set(command)
            path = Path(command[command.index("-r") + 1])
            selected.append((path, path.read_bytes()))
            output = "Looking in links: fixture-wheelhouse"
        elif command[1:4] == ["-m", "pip", "check"]:
            output = "No broken requirements found."
        elif command[1] == "-c":
            code = command[2]
            if "sysconfig" in code:
                output = str(site)
            elif "configure_secure_dspy_cache" in code:
                output = json.dumps({"restrict_pickle": True, "disk_cache_dir": str(venv / "cache")})
            elif ".__file__" in code:
                output = json.dumps({f"{module}.__file__": str(site / module / "__init__.py")})
            elif code == "import rook.server":
                output = ""
            else:
                pytest.fail(f"Unexpected Python command: {command}")
        else:
            pytest.fail(f"Unexpected subprocess: {command}")
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["verify", "--base-python", "fixture-python", "--wheelhouse", str(layout.wheelhouse),
        "--bootstrap-lock", str(layout.bootstrap_lock), "--lockfile", str(package_lock),
        "--venv-dir", str(venv), "--module", module, "--output", str(tmp_path / "verification.json")])
    assert ns["main"]() == 0
    assert selected == [(layout.bootstrap_lock, layout.bootstrap_lock.read_bytes()), (package_lock, package_lock.read_bytes())]

    selected.clear()
    installed_venv = layout.rook_venv if module == "rook" else layout.chirp_venv
    installed_python = installed_venv / "Scripts/python.exe"
    monkeypatch.setattr(post_install, "_create_venv", lambda *_: installed_python)
    monkeypatch.setattr(post_install, "_run_install_command", fake_run)
    assert post_install._install_from_wheelhouse_once(
        module, layout, installed_venv, package_lock, module, "fixture-python", "fixture-lock",
    ) == (installed_python, None)
    assert selected == [(layout.bootstrap_lock, layout.bootstrap_lock.read_bytes()), (package_lock, package_lock.read_bytes())]


def test_sanitized_install_env_removes_python_and_pip_index_state(monkeypatch) -> None:
    runtime = load_runtime_install()
    monkeypatch.setenv("PYTHONHOME", "C:/bad")
    monkeypatch.setenv("PYTHONPATH", "C:/bad")
    monkeypatch.setenv("PIP_INDEX_URL", "https://bad.example/simple")
    monkeypatch.setenv("PIP_EXTRA_INDEX_URL", "https://bad.example/extra")

    env = runtime.build_sanitized_python_env(require_virtualenv=True)

    assert "PYTHONHOME" not in env
    assert "PYTHONPATH" not in env
    assert "PIP_INDEX_URL" not in env
    assert "PIP_EXTRA_INDEX_URL" not in env
    assert env["PIP_NO_INDEX"] == "1"
    assert env["PIP_DISABLE_PIP_VERSION_CHECK"] == "1"
    assert env["PIP_REQUIRE_VIRTUALENV"] == "1"


def test_venv_invalidates_on_python_or_lock_hash_change(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    state = {
        "schema_version": 1,
        "python": {"identity_hash": "old-python"},
        "rook": {"python_identity_hash": "old-python", "lockfile_sha256": "old-lock"},
    }

    assert runtime.needs_venv_recreate(state, "rook", "new-python", "old-lock")
    assert runtime.needs_venv_recreate(state, "rook", "old-python", "new-lock")
    assert not runtime.needs_venv_recreate(state, "rook", "old-python", "old-lock")


def test_venv_invalidates_per_runtime_when_rook_installs_before_chirp(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    post_install = load_post_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")
    old_runtime_hash = "0" * 64
    new_runtime_hash = "1" * 64
    old_lock_hash = "2" * 64

    runtime.write_install_state(
        layout.install_state,
        {
            "python": {"identity_hash": old_runtime_hash},
            "rook": {
                "python_identity_hash": old_runtime_hash,
                "lockfile_sha256": old_lock_hash,
            },
            "chirp": {
                "python_identity_hash": old_runtime_hash,
                "lockfile_sha256": old_lock_hash,
            },
        },
    )

    post_install._record_install_state(
        layout=layout,
        runtime_name="rook",
        venv_dir=layout.rook_venv,
        venv_python=layout.rook_venv / "Scripts" / "python.exe",
        lock=layout.rook_lock,
        python_identity_hash=new_runtime_hash,
        lockfile_sha256=old_lock_hash,
        pip_check_output="No broken requirements found.",
    )

    updated_state = runtime.read_install_state(layout.install_state)

    assert updated_state["rook"]["python_identity_hash"] == new_runtime_hash
    assert updated_state["chirp"]["python_identity_hash"] == old_runtime_hash
    assert runtime.needs_venv_recreate(
        updated_state,
        "chirp",
        new_runtime_hash,
        old_lock_hash,
    )


def test_import_origin_must_be_site_packages(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    site_packages = tmp_path / "venv" / "Lib" / "site-packages" / "rook" / "__init__.py"
    source_tree = tmp_path / "app" / "mcp_server" / "src" / "rook" / "__init__.py"

    assert runtime.is_site_packages_import(site_packages)
    assert not runtime.is_site_packages_import(source_tree)


def test_install_state_has_schema_version(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    path = tmp_path / "data" / "install-state.json"
    runtime.write_install_state(
        path,
        {
            "python": {"path": "C:/Rook/python/cpython-3.11.9/python.exe"},
            "rook": {"venv_path": "C:/Rook/venv"},
            "chirp": {"venv_path": "C:/Rook/app/chirp/.venv"},
        },
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["python"]["path"].endswith("python.exe")


def test_post_install_extends_seeded_summary(tmp_path: Path) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"
    logs = runtime_root / "logs"
    logs.mkdir(parents=True)
    summary = logs / "post_install_summary.json"
    summary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "phase_reached": "preflight",
                "preflight": {"server_count": 5, "owners": ["Claude", "Codex"]},
            }
        ),
        encoding="utf-8",
    )

    post_install._configure_install_logging(runtime_root)
    post_install._update_install_summary(
        runtime_root, phase_reached="finalizer-started", final_outcome="running"
    )

    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["preflight"]["server_count"] == 5
    assert payload["phase_reached"] == "finalizer-started"
    assert payload["final_outcome"] == "running"


def test_post_install_summary_schema_version_is_pinned_to_one(tmp_path: Path) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"
    logs = runtime_root / "logs"
    logs.mkdir(parents=True)
    summary = logs / "post_install_summary.json"
    summary.write_text(
        json.dumps(
            {
                "schema_version": 99,
                "phase_reached": "preflight",
                "preflight": {"server_count": 5},
            }
        ),
        encoding="utf-8",
    )

    post_install._update_install_summary(runtime_root, final_outcome="running")

    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["phase_reached"] == "preflight"
    assert payload["preflight"]["server_count"] == 5
    assert payload["final_outcome"] == "running"


def test_rebuild_guard_health_promotes_top_level_warnings(tmp_path: Path) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"
    logs = runtime_root / "logs"
    logs.mkdir(parents=True)
    summary = logs / "post_install_summary.json"
    summary.write_text(
        json.dumps({"schema_version": 1, "phase_reached": "preflight"}),
        encoding="utf-8",
    )

    post_install._record_venv_rebuild_summary(
        runtime_root,
        runtime_name="rook",
        label="rook-mcp",
        retry_count=0,
        outcome="success",
        guard_close_failures=["rook-mcp: failed to terminate pid 10"],
        guard_thread_died_unexpectedly=True,
    )

    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["venv_rebuilds"]["rook"]["outcome"] == "success"
    assert payload["warnings"] == [
        "rook-mcp rebuild guard close failure: rook-mcp: failed to terminate pid 10",
        "rook-mcp rebuild guard sweep thread died unexpectedly",
    ]


def test_last_gasp_handler_writes_traceback(tmp_path: Path, monkeypatch) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"

    def boom() -> int:
        raise RuntimeError("forced install failure")

    monkeypatch.setattr(post_install, "main", boom)

    result = post_install._run_with_last_gasp(runtime_root=runtime_root)

    assert result == 1
    log = (runtime_root / "logs" / "post_install.log").read_text(encoding="utf-8")
    assert "forced install failure" in log
    assert "Traceback" in log


def test_last_gasp_records_success_outcome(tmp_path: Path, monkeypatch) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"

    def ok() -> int:
        post_install._update_install_summary(
            runtime_root, phase_reached="finalizer-started", final_outcome="running"
        )
        return 0

    monkeypatch.setattr(post_install, "main", ok)

    result = post_install._run_with_last_gasp(runtime_root=runtime_root)

    assert result == 0
    summary = json.loads(
        (runtime_root / "logs" / "post_install_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["phase_reached"] == "finalizer-complete"
    assert summary["final_outcome"] == "success"


def test_last_gasp_records_normal_failure_outcome(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"

    def fail() -> int:
        post_install._update_install_summary(
            runtime_root, phase_reached="finalizer-started", final_outcome="running"
        )
        return 1

    monkeypatch.setattr(post_install, "main", fail)

    result = post_install._run_with_last_gasp(runtime_root=runtime_root)

    assert result == 1
    summary = json.loads(
        (runtime_root / "logs" / "post_install_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["phase_reached"] == "finalizer-failed"
    assert summary["final_outcome"] == "failed"


def test_uninstall_cleanup_runs_without_install_log_handler(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"
    post_install._configure_install_logging(runtime_root)

    def assert_logging_closed() -> None:
        assert post_install._INSTALL_LOGGER.handlers == []

    monkeypatch.setattr(post_install, "uninstall_cleanup", assert_logging_closed)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_install.py",
            "--uninstall",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert post_install.main() == 0


def test_last_gasp_uses_runtime_root_from_argv(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    default_parent = tmp_path / "default-local-appdata"
    default_root = default_parent / "Rook"
    custom_root = tmp_path / "custom-runtime"

    def boom() -> int:
        raise RuntimeError("custom runtime failure")

    monkeypatch.setenv("LOCALAPPDATA", str(default_parent))
    monkeypatch.setattr(post_install, "main", boom)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_install.py",
            "--runtime-root",
            str(custom_root),
        ],
    )

    result = post_install._run_with_last_gasp()

    assert result == 1
    custom_log = custom_root / "logs" / "post_install.log"
    custom_summary = custom_root / "logs" / "post_install_summary.json"
    assert "custom runtime failure" in custom_log.read_text(encoding="utf-8")
    assert json.loads(custom_summary.read_text(encoding="utf-8"))["final_outcome"] == "failed"
    assert not (default_root / "logs" / "post_install.log").exists()
    assert not (default_root / "logs" / "post_install_summary.json").exists()


def test_post_install_recreates_stale_venv_and_writes_install_state(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = load_runtime_install()
    post_install = load_post_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")

    layout.private_python.parent.mkdir(parents=True)
    layout.private_python.write_text("private python", encoding="utf-8")
    layout.wheelhouse.mkdir(parents=True)
    layout.bootstrap_lock.parent.mkdir(parents=True, exist_ok=True)
    layout.bootstrap_lock.write_text("pip==26.2.1 --hash=sha256:abc\n", encoding="utf-8")
    layout.rook_lock.write_text("rook-mcp==1.5.10 --hash=sha256:def\n", encoding="utf-8")
    layout.runtime_manifest.write_text('{"schema_version":1}', encoding="utf-8")

    stale_python = post_install.get_venv_python(layout.rook_venv)
    stale_python.parent.mkdir(parents=True)
    stale_python.write_text("stale", encoding="utf-8")
    stale_marker = layout.rook_venv / "stale-package.txt"
    stale_marker.write_text("orphaned package", encoding="utf-8")
    runtime.write_install_state(
        layout.install_state,
        {
            "python": {"identity_hash": "old-runtime"},
            "rook": {"lockfile_sha256": "old-lock"},
        },
    )

    def fake_run(command, *, env, timeout=post_install.INSTALL_COMMAND_TIMEOUT_SECONDS):
        if command[:3] == [str(layout.private_python), "-m", "venv"]:
            created_python = post_install.get_venv_python(Path(command[3]))
            created_python.parent.mkdir(parents=True, exist_ok=True)
            created_python.write_text("fresh", encoding="utf-8")
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="Looking in links: C:/Rook/app/python-wheelhouse\nNo broken requirements found.",
            stderr="",
        )

    monkeypatch.setattr(post_install, "_run_install_command", fake_run)

    venv_python = post_install._install_from_wheelhouse(
        "rook-mcp",
        layout,
        layout.rook_venv,
        layout.rook_lock,
        "rook",
    )

    assert venv_python == stale_python
    assert not stale_marker.exists()
    install_state = json.loads(layout.install_state.read_text(encoding="utf-8"))
    assert install_state["schema_version"] == 1
    assert install_state["python"]["path"] == str(layout.private_python)
    assert install_state["python"]["identity_hash"]
    assert install_state["rook"]["venv_path"] == str(layout.rook_venv)
    assert install_state["rook"]["python_identity_hash"] == install_state["python"]["identity_hash"]
    assert install_state["rook"]["lockfile_sha256"]


def test_install_mcp_server_seeds_discovery_directory(tmp_path: Path, monkeypatch) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"
    managed_python = runtime_root / "venv" / "Scripts" / "python.exe"

    def fake_install(*args, **kwargs):
        managed_python.parent.mkdir(parents=True)
        managed_python.write_text("fake", encoding="utf-8")
        return managed_python

    monkeypatch.setattr(post_install, "_install_from_wheelhouse", fake_install)

    result = post_install.install_mcp_server(tmp_path / "app" / "mcp_server", runtime_root)

    assert result == managed_python
    assert (runtime_root / "discovery").is_dir()


def test_post_install_fails_closed_when_stale_venv_cannot_be_deleted(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    runtime = load_runtime_install()
    post_install = load_post_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")

    layout.private_python.parent.mkdir(parents=True)
    layout.private_python.write_text("private python", encoding="utf-8")
    layout.wheelhouse.mkdir(parents=True)
    layout.bootstrap_lock.parent.mkdir(parents=True, exist_ok=True)
    layout.bootstrap_lock.write_text("pip==26.2.1 --hash=sha256:abc\n", encoding="utf-8")
    layout.rook_lock.write_text("rook-mcp==1.5.10 --hash=sha256:def\n", encoding="utf-8")
    layout.runtime_manifest.write_text('{"schema_version":1}', encoding="utf-8")

    stale_python = post_install.get_venv_python(layout.rook_venv)
    stale_python.parent.mkdir(parents=True)
    stale_python.write_text("stale", encoding="utf-8")
    runtime.write_install_state(
        layout.install_state,
        {
            "python": {"identity_hash": "old-runtime"},
            "rook": {"lockfile_sha256": "old-lock"},
        },
    )

    install_commands: list[list[str]] = []

    def locked_delete(path):
        raise PermissionError("venv file is locked")

    def fake_run(command, *, env, timeout=post_install.INSTALL_COMMAND_TIMEOUT_SECONDS):
        install_commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(post_install.shutil, "rmtree", locked_delete)
    monkeypatch.setattr(post_install, "_run_install_command", fake_run)

    result = post_install._install_from_wheelhouse(
        "rook-mcp",
        layout,
        layout.rook_venv,
        layout.rook_lock,
        "rook",
    )

    assert result is None
    assert install_commands == []
    assert "Close Rhino/Revit" in capsys.readouterr().out


def test_post_install_requires_runtime_manifest_input(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    post_install = load_post_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")

    layout.private_python.parent.mkdir(parents=True)
    layout.private_python.write_text("private python", encoding="utf-8")
    layout.wheelhouse.mkdir(parents=True)
    layout.bootstrap_lock.parent.mkdir(parents=True, exist_ok=True)
    layout.bootstrap_lock.write_text("pip==26.2.1 --hash=sha256:abc\n", encoding="utf-8")
    layout.rook_lock.write_text("rook-mcp==1.5.10 --hash=sha256:def\n", encoding="utf-8")

    assert post_install._install_from_wheelhouse(
        "rook-mcp",
        layout,
        layout.rook_venv,
        layout.rook_lock,
        "rook",
    ) is None


def test_post_install_main_fails_when_selected_chirp_install_fails(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    install_dir = tmp_path / "app"
    mcp_server_dir = install_dir / "mcp_server"
    chirp_dir = install_dir / "chirp"
    mcp_server_dir.mkdir(parents=True)
    chirp_dir.mkdir()
    managed_python = tmp_path / "Rook" / "venv" / "Scripts" / "python.exe"
    managed_python.parent.mkdir(parents=True)
    managed_python.write_text("fake", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_install.py",
            "--install-dir",
            str(install_dir),
            "--mcp-server-dir",
            str(mcp_server_dir),
            "--runtime-root",
            str(tmp_path / "Rook"),
            "--chirp-dir",
            str(chirp_dir),
            "--skip-validation",
        ],
    )
    monkeypatch.setattr(post_install, "install_mcp_server", lambda *args, **kwargs: managed_python)
    monkeypatch.setattr(post_install, "install_chirp", lambda *args, **kwargs: False)
    monkeypatch.setattr(post_install, "configure_claude_code", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "configure_claude_desktop", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "configure_codex", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "install_user_assets", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "write_chat_service_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(post_install, "create_env_examples", lambda *args, **kwargs: None)

    assert post_install.main() == 1


def test_post_install_main_fails_when_chat_manifest_write_fails(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    install_dir = tmp_path / "app"
    mcp_server_dir = install_dir / "mcp_server"
    mcp_server_dir.mkdir(parents=True)
    managed_python = tmp_path / "Rook" / "venv" / "Scripts" / "python.exe"
    managed_python.parent.mkdir(parents=True)
    managed_python.write_text("fake", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_install.py",
            "--install-dir",
            str(install_dir),
            "--mcp-server-dir",
            str(mcp_server_dir),
            "--runtime-root",
            str(tmp_path / "Rook"),
            "--skip-validation",
        ],
    )
    monkeypatch.setattr(post_install, "install_mcp_server", lambda *args, **kwargs: managed_python)
    monkeypatch.setattr(post_install, "configure_claude_code", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "configure_claude_desktop", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "configure_codex", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "install_user_assets", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "write_chat_service_manifest", lambda *args, **kwargs: False)
    monkeypatch.setattr(post_install, "create_env_examples", lambda *args, **kwargs: None)

    assert post_install.main() == 1


def test_post_install_main_fails_when_selected_codex_assets_fail(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    install_dir = tmp_path / "app"
    mcp_server_dir = install_dir / "mcp_server"
    mcp_server_dir.mkdir(parents=True)
    managed_python = tmp_path / "Rook" / "venv" / "Scripts" / "python.exe"
    managed_python.parent.mkdir(parents=True)
    managed_python.write_text("fake", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_install.py",
            "--install-dir",
            str(install_dir),
            "--mcp-server-dir",
            str(mcp_server_dir),
            "--runtime-root",
            str(tmp_path / "Rook"),
            "--codex",
            "--skip-validation",
        ],
    )
    monkeypatch.setattr(post_install, "install_mcp_server", lambda *args, **kwargs: managed_python)
    monkeypatch.setattr(post_install, "configure_codex", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "install_user_assets", lambda *args, **kwargs: False)
    monkeypatch.setattr(post_install, "write_chat_service_manifest", lambda *args, **kwargs: True)
    monkeypatch.setattr(post_install, "create_env_examples", lambda *args, **kwargs: None)

    assert post_install.main() == 1


def test_post_install_validation_invokes_doctor_fix_for_selected_clients(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    install_dir = tmp_path / "Rook" / "app"
    runtime_root = tmp_path / "Rook"
    mcp_server_dir = install_dir / "mcp_server"
    mcp_server_dir.mkdir(parents=True)
    (runtime_root / "venv").mkdir(parents=True)
    (runtime_root / "data").mkdir()
    (runtime_root / "logs").mkdir()
    chirp_python = install_dir / "chirp" / ".venv" / "Scripts" / "python.exe"
    chirp_python.parent.mkdir(parents=True)
    chirp_python.write_text("fake", encoding="utf-8")
    python_path = str(runtime_root / "venv" / "Scripts" / "python.exe")
    commands = []

    class Completed:
        returncode = 0
        stdout = json.dumps(
            {
                "checks": [
                    {"name": "Claude Code config", "ok": True},
                    {"name": "Codex config", "ok": True},
                    {"name": "Codex skills installed", "ok": True},
                ],
                "warnings": [],
                "fixes_applied": [
                    "updated C:/Users/test/.claude.json",
                    "updated C:/Users/test/.codex/config.toml",
                ],
            }
        )
        stderr = ""

    def fake_run(command, **kwargs):
        commands.append(command)
        return Completed()

    monkeypatch.setattr(post_install.subprocess, "run", fake_run)

    assert post_install.validate(
        install_dir=install_dir,
        runtime_root=runtime_root,
        python_path=python_path,
        install_plugins=False,
        install_claude=True,
        install_codex=True,
        chirp_dir=install_dir / "chirp",
    )

    doctor_command = next(command for command in commands if "-m" in command and "rook" in command)
    assert "--fix" in doctor_command
    assert "--claude" in doctor_command
    assert "--codex" in doctor_command


def test_release_chat_manifest_has_no_source_pythonpath_entries(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    manifest = runtime.build_chat_service_manifest(
        mcp_server_dir=tmp_path / "app" / "mcp_server",
        rook_venv_python=tmp_path / "venv" / "Scripts" / "python.exe",
        release_mode=True,
    )

    assert manifest["pythonPath"].endswith("venv\\Scripts\\python.exe") or manifest[
        "pythonPath"
    ].endswith("venv/Scripts/python.exe")
    assert manifest["workingDirectory"].endswith("mcp_server")
    assert manifest["pythonPathEntries"] == []
    assert manifest["environment"]["DSPY_CACHEDIR"].endswith("data/dspy-cache")
    assert manifest["environment"]["ROOK_DSPY_RESTRICT_PICKLE"] == "1"


def test_write_chat_service_manifest_writes_root_and_existing_child_manifests(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    post_install = load_post_install()
    appdata = tmp_path / "AppData" / "Roaming"
    plugin_dir = appdata / "McNeel" / "Rhinoceros" / "8.0" / "Plug-ins" / "RookNative"
    plugin_dir.mkdir(parents=True)
    for runtime in ("net8.0", "net7.0", "net48", "net9.0"):
        (plugin_dir / runtime).mkdir()
    mcp_server_dir = tmp_path / "Rook" / "app" / "mcp_server"
    mcp_server_dir.mkdir(parents=True)
    python_path = tmp_path / "Rook" / "venv" / "Scripts" / "python.exe"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("fake", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(appdata))

    assert post_install.write_chat_service_manifest(mcp_server_dir, str(python_path)) is True

    root_payload = (plugin_dir / "RookChatService.json").read_text(encoding="utf-8")
    for runtime in ("net8.0", "net7.0", "net48"):
        child_payload = (plugin_dir / runtime / "RookChatService.json").read_text(
            encoding="utf-8"
        )
        assert child_payload == root_payload
        assert json.loads(child_payload)["module"] == "rook.agent.chat.service_main"
    assert not (plugin_dir / "net9.0" / "RookChatService.json").exists()
    assert "unknown managed runtime child directory" in capsys.readouterr().out


def test_write_chat_service_manifest_child_write_failure_returns_false_without_summary(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    post_install = load_post_install()
    appdata = tmp_path / "AppData" / "Roaming"
    plugin_dir = appdata / "McNeel" / "Rhinoceros" / "8.0" / "Plug-ins" / "RookNative"
    plugin_dir.mkdir(parents=True)
    for runtime in ("net8.0", "net7.0", "net48"):
        (plugin_dir / runtime).mkdir()
    mcp_server_dir = tmp_path / "Rook" / "app" / "mcp_server"
    mcp_server_dir.mkdir(parents=True)
    python_path = tmp_path / "Rook" / "venv" / "Scripts" / "python.exe"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("fake", encoding="utf-8")
    summary_path = tmp_path / "Rook" / "logs" / "post_install_summary.json"
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text(
        json.dumps({"schema_version": 1, "phase_reached": "preflight"}),
        encoding="utf-8",
    )
    failed_path = plugin_dir / "net7.0" / "RookChatService.json"
    original_write_text = Path.write_text

    def fail_child_manifest_write(self, *args, **kwargs):
        if self == failed_path:
            raise PermissionError("locked child manifest")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(Path, "write_text", fail_child_manifest_write)

    assert post_install.write_chat_service_manifest(mcp_server_dir, str(python_path)) is False

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["phase_reached"] == "preflight"
    assert "chat_service_manifest_paths" not in summary
    output = capsys.readouterr().out
    assert str(failed_path) in output
    assert "Failed to write chat service manifest" in output


def test_mcp_env_points_to_chirp_home_and_clears_python_paths(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    env = runtime.build_release_mcp_env(
        install_dir=tmp_path / "app",
        data_dir=tmp_path / "data",
        chirp_dir=tmp_path / "app" / "chirp",
    )

    assert env["ROOK_INSTALL_ROOT"].endswith("app")
    assert env["ROOK_DATA_DIR"].endswith("data")
    assert env["ROOK_MODE"] == "release"
    assert env["PYTHONHOME"] == ""
    assert env["PYTHONPATH"] == ""
    assert env["DSPY_CACHEDIR"].endswith("data/dspy-cache")
    assert env["ROOK_DSPY_RESTRICT_PICKLE"] == "1"
    assert env["CHIRP_HOME"].endswith("app/chirp")


def test_post_install_codex_toml_sets_lean_profile_only_in_codex_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    post_install = load_post_install()
    env = post_install._build_mcp_env(
        install_dir=tmp_path / "app",
        data_dir=tmp_path / "data",
        mode="release",
        chirp_dir=tmp_path / "app" / "chirp",
    )

    assert post_install.PROFILE_ENV_VAR not in env

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert post_install.configure_codex(
        install_dir=tmp_path / "app",
        data_dir=tmp_path / "data",
        python_path="C:/Rook/venv/Scripts/python.exe",
        mcp_server_dir=tmp_path / "app" / "mcp_server",
        chirp_dir=tmp_path / "app" / "chirp",
    )
    toml = (tmp_path / ".codex" / "config.toml").read_text(encoding="utf-8")

    assert 'ROOK_MCP_TOOL_PROFILE = "lean"' in toml


def test_runtime_layout_uses_private_python_and_two_venvs(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")

    assert (
        layout.private_python
        == tmp_path / "Rook" / "python" / "cpython-3.11.9" / "python.exe"
    )
    assert layout.rook_venv == tmp_path / "Rook" / "venv"
    assert layout.chirp_venv == tmp_path / "Rook" / "app" / "chirp" / ".venv"
    assert layout.wheelhouse == tmp_path / "Rook" / "app" / "python-wheelhouse"
    assert (
        layout.bootstrap_lock
        == tmp_path / "Rook" / "app" / "requirements-bootstrap-lock.txt"
    )


def test_pip_output_evidence_rejects_index_lookup() -> None:
    runtime = load_runtime_install()
    runtime.assert_local_wheelhouse_output(
        "Looking in links: C:/Rook/app/python-wheelhouse\nProcessing rook_mcp.whl"
    )

    try:
        runtime.assert_local_wheelhouse_output("Looking in indexes: https://pypi.org/simple")
    except ValueError as exc:
        assert "network index" in str(exc)
    else:
        raise AssertionError("expected network index output to be rejected")


def test_public_install_ignores_user_python_and_pip_contamination(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = load_runtime_install()
    fake_user_python = tmp_path / "UserPython" / "python.exe"
    fake_user_python.parent.mkdir()
    fake_user_python.write_text("not real", encoding="utf-8")

    monkeypatch.setenv("PATH", str(fake_user_python.parent))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "source-shadow"))
    monkeypatch.setenv("PYTHONHOME", str(tmp_path / "bad-pythonhome"))
    monkeypatch.setenv("PIP_INDEX_URL", "https://bad.example/simple")
    monkeypatch.setenv("PIP_EXTRA_INDEX_URL", "https://bad.example/extra")

    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")
    env = runtime.build_sanitized_python_env(require_virtualenv=True)
    command = runtime.build_offline_pip_install_command(
        layout.rook_venv / "Scripts" / "python.exe",
        layout.wheelhouse,
        layout.rook_lock,
    )
    bootstrap_command = runtime.build_offline_pip_bootstrap_command(
        layout.rook_venv / "Scripts" / "python.exe",
        layout.wheelhouse,
        layout.bootstrap_lock,
    )

    runtime.assert_offline_pip_command(command)
    runtime.assert_offline_pip_command(bootstrap_command)
    assert str(fake_user_python) not in " ".join(command)
    assert str(fake_user_python) not in " ".join(bootstrap_command)
    assert command[0] == str(layout.rook_venv / "Scripts" / "python.exe")
    assert bootstrap_command[0] == str(layout.rook_venv / "Scripts" / "python.exe")
    assert env["PIP_NO_INDEX"] == "1"
    assert "PIP_INDEX_URL" not in env
    assert "PIP_EXTRA_INDEX_URL" not in env
    assert "PYTHONPATH" not in env
    assert "PYTHONHOME" not in env


def test_install_from_wheelhouse_uses_guard_and_retries_full_rebuild(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = load_runtime_install()
    post_install = load_post_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")

    layout.private_python.parent.mkdir(parents=True)
    layout.private_python.write_text("private python", encoding="utf-8")
    layout.wheelhouse.mkdir(parents=True)
    layout.bootstrap_lock.parent.mkdir(parents=True, exist_ok=True)
    layout.bootstrap_lock.write_text("pip==26.2.1 --hash=sha256:abc\n", encoding="utf-8")
    layout.rook_lock.write_text("rook-mcp==1.5.10 --hash=sha256:def\n", encoding="utf-8")
    layout.runtime_manifest.write_text('{"schema_version":1}', encoding="utf-8")
    summary = layout.rook_root / "logs" / "post_install_summary.json"
    summary.parent.mkdir(parents=True)
    summary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "phase_reached": "preflight",
                "preflight": {"server_count": 5},
            }
        ),
        encoding="utf-8",
    )
    stale_python = post_install.get_venv_python(layout.rook_venv)
    stale_python.parent.mkdir(parents=True)
    stale_python.write_text("stale", encoding="utf-8")

    guard_events: list[str] = []

    class FakeGuard:
        def __init__(self, label, **kwargs):
            self.label = label

        def __enter__(self):
            guard_events.append(f"enter:{self.label}")
            return self

        def __exit__(self, exc_type, exc, tb):
            guard_events.append(f"exit:{self.label}")
            return False

    monkeypatch.setattr(
        post_install, "_make_rebuild_guard", lambda label, runtime_root: FakeGuard(label)
    )

    attempts = {"install": 0}

    def fake_run(command, *, env, timeout=post_install.INSTALL_COMMAND_TIMEOUT_SECONDS):
        if command[:3] == [str(layout.private_python), "-m", "venv"]:
            created_python = post_install.get_venv_python(Path(command[3]))
            created_python.parent.mkdir(parents=True, exist_ok=True)
            created_python.write_text("fresh", encoding="utf-8")
        if (
            "-m" in command
            and "pip" in command
            and "install" in command
            and str(layout.rook_lock) in command
        ):
            attempts["install"] += 1
            if attempts["install"] == 1:
                return subprocess.CompletedProcess(
                    command, 1, stdout="", stderr="access denied"
                )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Looking in links: C:/Rook/app/python-wheelhouse\nNo broken requirements found.",
            stderr="",
        )

    monkeypatch.setattr(post_install, "_run_install_command", fake_run)

    venv_python = post_install._install_from_wheelhouse(
        "rook-mcp",
        layout,
        layout.rook_venv,
        layout.rook_lock,
        "rook",
    )

    assert venv_python == stale_python
    assert attempts["install"] == 2
    assert guard_events == [
        "enter:rook-mcp",
        "exit:rook-mcp",
        "enter:rook-mcp",
        "exit:rook-mcp",
    ]
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["preflight"]["server_count"] == 5
    assert payload["venv_rebuilds"]["rook"]["guard_label"] == "rook-mcp"
    assert payload["venv_rebuilds"]["rook"]["retry_count"] == 1
    assert payload["venv_rebuilds"]["rook"]["outcome"] == "success"


def test_install_from_wheelhouse_records_guard_health_signals(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = load_runtime_install()
    post_install = load_post_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")

    layout.private_python.parent.mkdir(parents=True)
    layout.private_python.write_text("private python", encoding="utf-8")
    layout.wheelhouse.mkdir(parents=True)
    layout.bootstrap_lock.parent.mkdir(parents=True, exist_ok=True)
    layout.bootstrap_lock.write_text("pip==26.2.1 --hash=sha256:abc\n", encoding="utf-8")
    layout.rook_lock.write_text("rook-mcp==1.5.10 --hash=sha256:def\n", encoding="utf-8")
    layout.runtime_manifest.write_text('{"schema_version":1}', encoding="utf-8")
    summary = layout.rook_root / "logs" / "post_install_summary.json"
    summary.parent.mkdir(parents=True)
    summary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "phase_reached": "preflight",
                "preflight": {"server_count": 5},
            }
        ),
        encoding="utf-8",
    )

    class FakeGuard:
        close_failures = ["rook-mcp: failed to terminate pid 123 error=5"]
        thread_died_unexpectedly = True

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_run(command, *, env, timeout=post_install.INSTALL_COMMAND_TIMEOUT_SECONDS):
        if command[:3] == [str(layout.private_python), "-m", "venv"]:
            created_python = post_install.get_venv_python(Path(command[3]))
            created_python.parent.mkdir(parents=True, exist_ok=True)
            created_python.write_text("fresh", encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Looking in links: C:/Rook/app/python-wheelhouse\nNo broken requirements found.",
            stderr="",
        )

    logged_errors: list[tuple[str, tuple[object, ...]]] = []

    def fake_error(message, *args, **kwargs):
        del kwargs
        logged_errors.append((message, args))

    monkeypatch.setattr(
        post_install, "_make_rebuild_guard", lambda label, runtime_root: FakeGuard()
    )
    monkeypatch.setattr(post_install, "_run_install_command", fake_run)
    monkeypatch.setattr(post_install._INSTALL_LOGGER, "error", fake_error)

    venv_python = post_install._install_from_wheelhouse(
        "rook-mcp",
        layout,
        layout.rook_venv,
        layout.rook_lock,
        "rook",
    )

    assert venv_python == post_install.get_venv_python(layout.rook_venv)
    payload = json.loads(summary.read_text(encoding="utf-8"))
    rebuild = payload["venv_rebuilds"]["rook"]
    assert payload["preflight"]["server_count"] == 5
    assert rebuild["guard_label"] == "rook-mcp"
    assert rebuild["guard_close_failures"] == [
        "rook-mcp: failed to terminate pid 123 error=5"
    ]
    assert rebuild["guard_thread_died_unexpectedly"] is True
    assert logged_errors
    assert logged_errors[0][0] == "%s rebuild guard close failure: %s"
    assert logged_errors[0][1] == (
        "rook-mcp",
        "rook-mcp: failed to terminate pid 123 error=5",
    )
    assert (
        "%s rebuild guard sweep thread died unexpectedly",
        ("rook-mcp",),
    ) in logged_errors


def test_install_from_wheelhouse_logs_pip_check_failure_without_retry(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = load_runtime_install()
    post_install = load_post_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")

    layout.private_python.parent.mkdir(parents=True)
    layout.private_python.write_text("private python", encoding="utf-8")
    layout.wheelhouse.mkdir(parents=True)
    layout.bootstrap_lock.parent.mkdir(parents=True, exist_ok=True)
    layout.bootstrap_lock.write_text("pip==26.2.1 --hash=sha256:abc\n", encoding="utf-8")
    layout.rook_lock.write_text("rook-mcp==1.5.10 --hash=sha256:def\n", encoding="utf-8")
    layout.runtime_manifest.write_text('{"schema_version":1}', encoding="utf-8")

    guard_events: list[str] = []

    class FakeGuard:
        def __init__(self, label, **kwargs):
            self.label = label

        def __enter__(self):
            guard_events.append(f"enter:{self.label}")
            return self

        def __exit__(self, exc_type, exc, tb):
            guard_events.append(f"exit:{self.label}")
            return False

    monkeypatch.setattr(
        post_install, "_make_rebuild_guard", lambda label, runtime_root: FakeGuard(label)
    )

    attempts = {"install": 0, "pip_check": 0}
    logged_errors: list[tuple[str, tuple[object, ...]]] = []

    def fake_error(message, *args, **kwargs):
        del kwargs
        logged_errors.append((message, args))

    def fake_run(command, *, env, timeout=post_install.INSTALL_COMMAND_TIMEOUT_SECONDS):
        if command[:3] == [str(layout.private_python), "-m", "venv"]:
            created_python = post_install.get_venv_python(Path(command[3]))
            created_python.parent.mkdir(parents=True, exist_ok=True)
            created_python.write_text("fresh", encoding="utf-8")
        if command[-2:] == ["pip", "check"]:
            attempts["pip_check"] += 1
            return subprocess.CompletedProcess(
                command,
                1,
                stdout="",
                stderr="rook-mcp 1.5.10 has requirement bad-package, but you have none",
            )
        if (
            "-m" in command
            and "pip" in command
            and "install" in command
            and str(layout.rook_lock) in command
        ):
            attempts["install"] += 1
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Looking in links: C:/Rook/app/python-wheelhouse\n",
            stderr="",
        )

    monkeypatch.setattr(post_install, "_run_install_command", fake_run)
    monkeypatch.setattr(post_install._INSTALL_LOGGER, "error", fake_error)

    result = post_install._install_from_wheelhouse(
        "rook-mcp",
        layout,
        layout.rook_venv,
        layout.rook_lock,
        "rook",
    )

    assert result is None
    assert attempts == {"install": 1, "pip_check": 1}
    assert guard_events == ["enter:rook-mcp", "exit:rook-mcp"]
    assert logged_errors
    assert logged_errors[0][0] == "%s pip check failed with exit code %s"
    assert logged_errors[0][1] == ("rook-mcp", 1)
    payload = json.loads(
        (layout.rook_root / "logs" / "post_install_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["venv_rebuilds"]["rook"]["retry_count"] == 0
    assert payload["venv_rebuilds"]["rook"]["failure_stage"] == "pip-check"


def test_chirp_install_uses_separate_guard_window(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"
    chirp_dir = runtime_root / "app" / "chirp"
    chirp_dir.mkdir(parents=True)
    labels: list[str] = []

    monkeypatch.setattr(
        post_install,
        "_install_from_wheelhouse",
        lambda label, layout, venv_dir, lock, runtime_name: labels.append(label)
        or (venv_dir / "Scripts" / "python.exe"),
    )

    assert post_install.install_chirp(chirp_dir, runtime_root) is True
    assert labels == ["Chirp"]


def test_retired_skill_migration_replaces_selected_rook_skill_root_exactly(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    install_dir = tmp_path / "install"
    packaged = install_dir / ".agents" / "skills" / "design-grasshopper"
    installed = tmp_path / ".codex" / "skills" / "design-grasshopper"
    sibling = tmp_path / ".codex" / "skills" / "user-sibling"

    (packaged / "references").mkdir(parents=True)
    (packaged / "SKILL.md").write_text("current", encoding="utf-8")
    (packaged / "references" / "wasp-admission.md").write_text(
        "admitted", encoding="utf-8"
    )
    (installed / "references").mkdir(parents=True)
    (installed / "SKILL.md").write_text("old", encoding="utf-8")
    (installed / "references" / "wasp-rhino-scaffold.md").write_text(
        "obsolete", encoding="utf-8"
    )
    sibling.mkdir()
    (sibling / "SKILL.md").write_text("user-owned", encoding="utf-8")

    assert post_install.install_user_assets(
        install_dir, install_claude=False, install_codex=True
    )

    def inventory(root: Path) -> dict[str, bytes]:
        return {
            item.relative_to(root).as_posix(): item.read_bytes()
            for item in root.rglob("*")
            if item.is_file()
        }

    assert inventory(installed) == inventory(packaged)
    assert (sibling / "SKILL.md").read_text(encoding="utf-8") == "user-owned"


def test_retired_codex_skill_cleanup_removes_only_exact_targets(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runtime_root = tmp_path / "runtime"
    skills = tmp_path / ".codex" / "skills"
    claude = tmp_path / ".claude" / "skills" / "design-road"
    sibling = skills / "design-grasshopper"
    retired_dir = skills / "design-road"
    retired_file = skills / "masterplan-roads"
    retired_consolidate = skills / "consolidate"

    (retired_dir / "nested").mkdir(parents=True)
    (retired_dir / "nested" / "payload.txt").write_text(
        "retired", encoding="utf-8"
    )
    retired_file.write_text("retired-file", encoding="utf-8")
    (retired_consolidate / "nested").mkdir(parents=True)
    (retired_consolidate / "nested" / "payload.txt").write_text(
        "retired", encoding="utf-8"
    )
    sibling.mkdir()
    (sibling / "SKILL.md").write_text("supported", encoding="utf-8")
    claude.mkdir(parents=True)
    (claude / "SKILL.md").write_text("claude-owned", encoding="utf-8")

    first = post_install.cleanup_retired_codex_skills(runtime_root)
    second = post_install.cleanup_retired_codex_skills(runtime_root)

    assert [item["outcome"] for item in first] == [
        "removed_directory",
        "removed_file",
        "removed_directory",
    ]
    assert [item["outcome"] for item in second] == ["absent", "absent", "absent"]
    assert not retired_dir.exists()
    assert not retired_file.exists()
    assert not retired_consolidate.exists()
    assert (sibling / "SKILL.md").read_text(encoding="utf-8") == "supported"
    assert (claude / "SKILL.md").read_text(encoding="utf-8") == "claude-owned"


def test_retired_codex_skill_cleanup_unlinks_link_without_following_target(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runtime_root = tmp_path / "runtime"
    skills = tmp_path / ".codex" / "skills"
    skills.mkdir(parents=True)
    external = tmp_path / "external-road-data"
    external.mkdir()
    sentinel = external / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    target = skills / "consolidate"

    if sys.platform == "win32":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(external)],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        target.symlink_to(external, target_is_directory=True)

    outcomes = post_install.cleanup_retired_codex_skills(runtime_root)

    assert outcomes[2]["outcome"] == "unlinked_reparse_point"
    assert not target.exists()
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_retired_cleanup_does_not_follow_nested_reparse_point(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runtime_root = tmp_path / "runtime"
    retired = tmp_path / ".codex" / "skills" / "masterplan-roads"
    retired.mkdir(parents=True)
    external = tmp_path / "external-nested-data"
    external.mkdir()
    sentinel = external / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    nested_link = retired / "nested-link"

    if sys.platform == "win32":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(nested_link), str(external)],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        nested_link.symlink_to(external, target_is_directory=True)

    outcomes = post_install.cleanup_retired_codex_skills(runtime_root)

    assert outcomes[1]["outcome"] == "removed_directory"
    assert not retired.exists()
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_retired_cleanup_failure_is_nonfatal_and_records_incomplete_summary(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runtime_root = tmp_path / "runtime"
    skills = tmp_path / ".codex" / "skills"
    design = skills / "design-road"
    masterplan = skills / "masterplan-roads"
    consolidate = skills / "consolidate"
    design.mkdir(parents=True)
    masterplan.write_text("remove me", encoding="utf-8")
    consolidate.mkdir()
    post_install._update_install_summary(
        runtime_root,
        phase_reached="finalizer-started",
        final_outcome="running",
    )

    real_rmtree = post_install.shutil.rmtree

    def fail_consolidate(path):
        if Path(path) == consolidate:
            raise PermissionError("blocked consolidate")
        return real_rmtree(path)

    monkeypatch.setattr(post_install.shutil, "rmtree", fail_consolidate)
    outcomes = post_install.cleanup_retired_codex_skills(runtime_root)
    summary = json.loads(
        (runtime_root / "logs" / "post_install_summary.json").read_text(
            encoding="utf-8"
        )
    )

    assert [item["outcome"] for item in outcomes] == [
        "removed_directory",
        "removed_file",
        "failed",
    ]
    assert not design.exists()
    assert not masterplan.exists()
    assert consolidate.exists()
    assert summary["retired_codex_skill_cleanup"]["complete"] is False
    assert summary["retired_codex_skill_cleanup"]["targets"] == outcomes
    assert summary["final_outcome"] == "running"
    assert any(
        "retired-skill containment is incomplete" in item.lower()
        for item in summary["warnings"]
    )


def _run_main_for_retired_skill_migration(
    post_install,
    tmp_path: Path,
    monkeypatch,
    codex_selected: bool,
    cleanup_outcomes: list[dict[str, str]] | None = None,
) -> tuple[list[Path], list[bool]]:
    install_dir = tmp_path / "app"
    mcp_server_dir = install_dir / "mcp_server"
    runtime_root = tmp_path / "runtime"
    mcp_server_dir.mkdir(parents=True)
    managed_python = runtime_root / "venv" / "Scripts" / "python.exe"
    managed_python.parent.mkdir(parents=True)
    managed_python.write_text("fake", encoding="utf-8")
    argv = [
        "post_install.py",
        "--install-dir",
        str(install_dir),
        "--mcp-server-dir",
        str(mcp_server_dir),
        "--runtime-root",
        str(runtime_root),
        "--skip-validation",
    ]
    if codex_selected:
        argv.append("--codex")
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(
        post_install, "install_mcp_server", lambda *_args: managed_python
    )
    monkeypatch.setattr(post_install, "configure_codex", lambda *_args: True)
    monkeypatch.setattr(
        post_install, "write_chat_service_manifest", lambda *_args: True
    )
    monkeypatch.setattr(post_install, "create_env_examples", lambda *_args: None)
    cleanup_calls = []
    asset_calls = []
    monkeypatch.setattr(
        post_install,
        "cleanup_retired_codex_skills",
        lambda runtime: cleanup_calls.append(runtime)
        or list(cleanup_outcomes or []),
    )
    monkeypatch.setattr(
        post_install,
        "install_user_assets",
        lambda _install_dir, install_claude, install_codex: (
            asset_calls.append(install_codex) or True
        ),
    )
    assert post_install.main() == 0
    return cleanup_calls, asset_calls


@pytest.mark.parametrize("codex_selected", [False, True])
def test_main_runs_retired_skill_migration_regardless_of_codex_selection(
    tmp_path: Path, monkeypatch, codex_selected: bool
) -> None:
    post_install = load_post_install()
    cleanup_calls, asset_calls = _run_main_for_retired_skill_migration(
        post_install, tmp_path, monkeypatch, codex_selected
    )
    assert cleanup_calls == [tmp_path / "runtime"]
    assert asset_calls == [codex_selected]


def test_cleanup_failure_does_not_block_selected_codex_skill_copy(
    tmp_path: Path, monkeypatch
) -> None:
    post_install = load_post_install()
    cleanup_calls, asset_calls = _run_main_for_retired_skill_migration(
        post_install,
        tmp_path,
        monkeypatch,
        codex_selected=True,
        cleanup_outcomes=[
            {"name": "design-road", "outcome": "removed_directory"},
            {"name": "masterplan-roads", "outcome": "removed_file"},
            {"name": "consolidate", "outcome": "failed"},
        ],
    )
    assert cleanup_calls == [tmp_path / "runtime"]
    assert asset_calls == [True]
