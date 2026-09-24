"""uv install contract for the sealed wheelhouse (#595).

Unit tests pin the command, its allowlist check and the sanitised environment.
The live tests run the real ``uv`` against a one-file wheel built here, proving
the contract installs hash-locked wheels offline and fails closed otherwise.
"""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from tests.test_python_runtime_install import load_post_install, load_runtime_install

REPO = Path(__file__).resolve().parents[2]
STAGED_RUNTIME = REPO / "installer" / "runtime"


def _command(runtime, root: Path) -> list[str]:
    return runtime.build_offline_uv_install_command(
        root / "tools" / "uv.exe",
        root / "venv" / "Scripts" / "python.exe",
        root / "wheelhouse",
        root / "requirements-rook-lock.txt",
        root / "installer-cache" / "uv-rook",
    )


def test_uv_command_is_the_offline_hash_locked_contract(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    command = _command(runtime, tmp_path)

    runtime.assert_offline_uv_command(command)
    assert command[:3] == [str(tmp_path / "tools" / "uv.exe"), "pip", "install"]
    assert command[command.index("--python") + 1] == str(tmp_path / "venv" / "Scripts" / "python.exe")
    assert command[command.index("--find-links") + 1] == str(tmp_path / "wheelhouse")
    assert command[command.index("--cache-dir") + 1] == str(tmp_path / "installer-cache" / "uv-rook")
    assert command[command.index("--link-mode") + 1] == "hardlink"
    assert command[command.index("--color") + 1] == "never"
    assert command[-2:] == ["-r", str(tmp_path / "requirements-rook-lock.txt")]
    for switch in ("--offline", "--no-index", "--no-build", "--require-hashes", "--no-config", "--compile-bytecode"):
        assert switch in command


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda c: c + ["--index-url", "https://pypi.org/simple"], id="index-url"),
        pytest.param(lambda c: c + ["--index-url=https://pypi.org/simple"], id="index-url-equals"),
        pytest.param(lambda c: c + ["--default-index", "https://pypi.org/simple"], id="default-index"),
        pytest.param(lambda c: c + ["--extra-index-url", "https://pypi.org/simple"], id="extra-index"),
        pytest.param(lambda c: c + ["--offline"], id="repeated-switch"),
        pytest.param(lambda c: c + ["-r", c[-1]], id="second-lock"),
        pytest.param(lambda c: [t for t in c if t != "--offline"], id="missing-offline"),
        pytest.param(lambda c: [t for t in c if t != "--require-hashes"], id="missing-hashes"),
        pytest.param(lambda c: [t for t in c if t != "--no-build"], id="missing-no-build"),
        pytest.param(lambda c: [t for t in c if t != "--no-config"], id="missing-no-config"),
        pytest.param(lambda c: [t for t in c if t != "--compile-bytecode"], id="missing-compile"),
        pytest.param(lambda c: [t if t != "hardlink" else "copy" for t in c], id="copy-link-mode"),
        pytest.param(lambda c: [t if t != "never" else "always" for t in c], id="color-always"),
        pytest.param(lambda c: [t for i, t in enumerate(c) if t != "--color" and c[i - 1] != "--color"], id="missing-color"),
        pytest.param(lambda c: c[:-1] + ["requirements-rook-lock.txt"], id="relative-lock"),
        pytest.param(lambda c: ["uv.exe"] + c[1:], id="relative-uv"),
        pytest.param(lambda c: [c[0].replace("uv.exe", "pip.exe")] + c[1:], id="not-uv"),
        pytest.param(lambda c: c[:1] + ["pip", "sync"] + c[3:], id="not-install"),
        pytest.param(lambda c: c[:-1], id="option-without-value"),
    ],
)
def test_uv_command_check_rejects_everything_outside_the_contract(tmp_path: Path, mutate) -> None:
    runtime = load_runtime_install()

    with pytest.raises(ValueError):
        runtime.assert_offline_uv_command(mutate(_command(runtime, tmp_path)))


def test_uv_env_drops_uv_and_active_venv_state(monkeypatch) -> None:
    runtime = load_runtime_install()
    for key, value in {
        "UV_INDEX_URL": "https://bad.example/simple",
        "UV_DEFAULT_INDEX": "https://bad.example/simple",
        "UV_CACHE_DIR": "C:/elsewhere",
        "UV_LINK_MODE": "copy",
        "UV_OFFLINE": "0",
        "FORCE_COLOR": "1",
        "CLICOLOR_FORCE": "1",
        "VIRTUAL_ENV": "C:/someone-elses-venv",
        "CONDA_PREFIX": "C:/conda",
        "PYTHONPATH": "C:/vray/python",
        "PIP_INDEX_URL": "https://bad.example/simple",
    }.items():
        monkeypatch.setenv(key, value)

    env = runtime.build_sanitized_uv_env()

    assert not [key for key in env if key.upper().startswith("UV_")]
    for key in ("VIRTUAL_ENV", "CONDA_PREFIX", "FORCE_COLOR", "CLICOLOR_FORCE", "PYTHONPATH", "PIP_INDEX_URL"):
        assert key not in env
    assert env["PIP_NO_INDEX"] == "1"


@pytest.mark.parametrize(
    "output",
    [
        "Using Python 3.11.9 environment at: C:\\Rook\\venv\nResolved 99 packages in 219ms\nInstalled 99 packages in 7.40s",
        "Using Python 3.11.9 environment at: C:\\Rook\\venv\nChecked 71 packages in 829ms",
        "Resolved 1 package in 7ms",
    ],
)
def test_uv_output_evidence_accepts_resolved_or_checked_locks(output: str) -> None:
    load_runtime_install().assert_uv_install_output(output)


@pytest.mark.parametrize(
    "output",
    ["", "Installed 3 packages", "Resolved 2 packages in 4ms\nDownloading https://files.pythonhosted.org/numpy.whl"],
)
def test_uv_output_evidence_rejects_missing_summary_or_urls(output: str) -> None:
    with pytest.raises(ValueError):
        load_runtime_install().assert_uv_install_output(output)


def test_uv_cache_dirs_are_per_venv_under_the_runtime_root(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")

    rook_cache = layout.uv_cache_dir("rook")
    chirp_cache = layout.uv_cache_dir("chirp")

    assert rook_cache != chirp_cache
    assert rook_cache.parent == chirp_cache.parent == tmp_path / "Rook" / "installer-cache"


# --- bundled uv extraction, lock reading, freeze comparison ----------------------


def _uv_wheel(wheelhouse: Path, version: str = "0.12.5", payload: bytes = b"bundled uv") -> Path:
    wheelhouse.mkdir(parents=True, exist_ok=True)
    wheel = wheelhouse / f"uv-{version}-py3-none-win_amd64.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"uv-{version}.data/scripts/uv.exe", payload)
        archive.writestr(f"uv-{version}.data/scripts/uvx.exe", b"not extracted")
    return wheel


def _tools_lock(root: Path, *rows: str) -> Path:
    lock = root / "requirements-installer-tools-lock.txt"
    lock.write_text("# generated\n" + "".join(f"{row}\n" for row in rows), encoding="utf-8")
    return lock


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_extract_bundled_uv_takes_the_wheel_the_lock_pins(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    wheel = _uv_wheel(tmp_path / "wheelhouse")
    lock = _tools_lock(tmp_path, f"uv==0.12.5 --hash=sha256:{_sha(wheel)}")
    dest = tmp_path / "tools"
    dest.mkdir()
    (dest / "uv.exe").write_bytes(b"stale uv from an interrupted run")

    tool = runtime.extract_bundled_uv(tmp_path / "wheelhouse", lock, dest)

    assert tool.executable == dest / "uv.exe"
    assert tool.executable.read_bytes() == b"bundled uv"
    assert sorted(p.name for p in dest.iterdir()) == ["uv.exe"]
    assert tool.evidence() == {
        "name": "uv", "version": "0.12.5", "wheel": wheel.name, "wheel_sha256": _sha(wheel),
    }


@pytest.mark.parametrize(
    "rows",
    [
        pytest.param(lambda digest: [f"uv==0.12.5 --hash=sha256:{'0' * 64}"], id="hash-mismatch"),
        pytest.param(lambda digest: [f"uv==0.12.6 --hash=sha256:{digest}"], id="version-without-wheel"),
        pytest.param(lambda digest: [f"uv==0.12.5 --hash=sha256:{digest}", f"pip==26.2.1 --hash=sha256:{digest}"], id="two-tools"),
        pytest.param(lambda digest: [f"ruff==0.12.5 --hash=sha256:{digest}"], id="not-uv"),
        pytest.param(lambda digest: ["uv==0.12.5"], id="unhashed"),
        pytest.param(lambda digest: [], id="empty"),
    ],
)
def test_extract_bundled_uv_refuses_anything_but_the_one_locked_wheel(tmp_path: Path, rows) -> None:
    runtime = load_runtime_install()
    wheel = _uv_wheel(tmp_path / "wheelhouse")
    lock = _tools_lock(tmp_path, *rows(_sha(wheel)))

    with pytest.raises(ValueError):
        runtime.extract_bundled_uv(tmp_path / "wheelhouse", lock, tmp_path / "tools")
    assert not (tmp_path / "tools" / "uv.exe").exists()


def test_read_hash_lock_accepts_bom_and_comments_and_rejects_loose_rows(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    lock = tmp_path / "lock.txt"
    lock.write_bytes(b"\xef\xbb\xbf# header\n\npip==26.2.1 --hash=sha256:" + b"A" * 64 + b"\n")
    assert runtime.read_hash_lock(lock) == [("pip", "26.2.1", "a" * 64)]

    for loose in ("pip>=26", "pip==26.2.1", "pip==26.2.1 --hash=md5:abc", "-e ./local"):
        lock.write_text(loose + "\n", encoding="utf-8")
        with pytest.raises(ValueError):
            runtime.read_hash_lock(lock)


def test_freeze_mismatches_compares_canonical_names_and_exact_versions(tmp_path: Path) -> None:
    runtime = load_runtime_install()
    bootstrap = tmp_path / "bootstrap.txt"
    bootstrap.write_text(f"pip==26.2.1 --hash=sha256:{'a' * 64}\n", encoding="utf-8")
    lock = tmp_path / "rook.txt"
    lock.write_text(
        f"typing-extensions==4.16.0 --hash=sha256:{'b' * 64}\nPyYAML==6.0.3 --hash=sha256:{'c' * 64}\n",
        encoding="utf-8",
    )

    exact = "pip==26.2.1\ntyping_extensions==4.16.0\npyyaml==6.0.3\n"
    assert runtime.freeze_mismatches(exact, [bootstrap, lock]) == []

    drifted = "pip==26.2.1\ntyping_extensions==4.15.0\nuv==0.12.5\nlocal @ file:///C:/src/local\n"
    assert runtime.freeze_mismatches(drifted, [bootstrap, lock]) == sorted([
        "missing pyyaml==6.0.3",
        "typing-extensions: installed 4.15.0, locked 4.16.0",
        "unexpected uv==0.12.5",
        "unexpected local @ file:///C:/src/local==<not a pinned release>",
    ])


@pytest.mark.parametrize("outcome", ["success", "failure", "crash"])
def test_finalizer_removes_the_installer_cache_on_every_exit(tmp_path: Path, monkeypatch, outcome: str) -> None:
    post_install = load_post_install()
    root = tmp_path / "Rook"
    (root / "installer-cache" / "tools").mkdir(parents=True)
    (root / "installer-cache" / "tools" / "uv.exe").write_bytes(b"uv")
    (root / "installer-cache" / "uv-rook").mkdir()

    def fake_main() -> int:
        if outcome == "crash":
            raise RuntimeError("boom")
        return 0 if outcome == "success" else 1

    monkeypatch.setattr(post_install, "main", fake_main)
    monkeypatch.setattr(sys, "argv", ["post_install.py", "--runtime-root", str(root)])

    post_install._run_with_last_gasp(root)

    assert not (root / "installer-cache").exists()


# --- live: the pinned uv binary ---------------------------------------------------


@pytest.fixture(scope="session")
def pinned_uv(tmp_path_factory) -> Path:
    """The exact uv the installer ships: extracted from the staged wheelhouse when a
    build has produced one, else a PATH uv only if it is the pinned version."""
    runtime = load_runtime_install()
    pinned = runtime.INSTALLER_TOOL_REQUIREMENTS[0].split("==", 1)[1]
    tools_lock = STAGED_RUNTIME / "requirements-installer-tools-lock.txt"
    if tools_lock.is_file():
        tool = runtime.extract_bundled_uv(
            STAGED_RUNTIME / "python-wheelhouse", tools_lock, tmp_path_factory.mktemp("pinned-uv")
        )
        assert tool.version == pinned, "staged wheelhouse uv differs from INSTALLER_TOOL_REQUIREMENTS"
        return tool.executable
    found = shutil.which("uv")
    if found is None:
        pytest.skip(f"no staged wheelhouse and no uv on PATH (pinned uv {pinned})")
    reported = subprocess.run([found, "--version"], capture_output=True, text=True, timeout=30).stdout.split()
    if reported[1:2] != [pinned]:
        pytest.skip(f"PATH uv {' '.join(reported)} is not the pinned uv {pinned}")
    return Path(found)


def _record_hash(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def _write_wheel(wheelhouse: Path, name: str = "rookfixture", version: str = "1.0") -> Path:
    dist_info = f"{name}-{version}.dist-info"
    files = {
        f"{name}/__init__.py": b"VALUE = 1\n",
        f"{dist_info}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode(),
        f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: rook-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record = "".join(f"{path},{_record_hash(data)},{len(data)}\n" for path, data in files.items())
    files[f"{dist_info}/RECORD"] = (record + f"{dist_info}/RECORD,,\n").encode()
    wheel = wheelhouse / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path, data in files.items():
            archive.writestr(path, data)
    return wheel


@pytest.fixture
def uv_fixture(tmp_path: Path, pinned_uv: Path):
    """A fresh venv per test: uv, like pip, never re-verifies an already-installed
    distribution against the lock hash ("Checked 1 package"), so a reused venv would
    mask a hash mismatch. The installer relies on needs_venv_recreate for that."""
    root = tmp_path
    wheelhouse = root / "wheelhouse"
    wheelhouse.mkdir()
    wheel = _write_wheel(wheelhouse)
    venv = root / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True, timeout=120)
    return {
        "root": root,
        "wheelhouse": wheelhouse,
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "python": venv / "Scripts" / "python.exe",
        "uv": pinned_uv,
    }


def _run_uv(runtime, fx, lock_text: str, name: str, *, env=None, cwd=None) -> subprocess.CompletedProcess[str]:
    lock = fx["root"] / f"{name}-lock.txt"
    lock.write_text(lock_text, encoding="utf-8")
    command = runtime.build_offline_uv_install_command(
        fx["uv"], fx["python"], fx["wheelhouse"], lock, fx["root"] / "cache" / name
    )
    runtime.assert_offline_uv_command(command)
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=120,
        env=runtime.build_sanitized_uv_env() if env is None else env,
        cwd=cwd,
    )


def test_live_uv_contract_installs_and_compiles_a_hash_locked_wheel(uv_fixture) -> None:
    runtime = load_runtime_install()
    result = _run_uv(runtime, uv_fixture, f"rookfixture==1.0 --hash=sha256:{uv_fixture['wheel_sha256']}\n", "ok")

    assert result.returncode == 0, result.stderr
    runtime.assert_uv_install_output(result.stdout + result.stderr)
    site_packages = uv_fixture["python"].parent.parent / "Lib" / "site-packages"
    assert (site_packages / "rookfixture" / "__init__.py").read_text() == "VALUE = 1\n"
    assert list((site_packages / "rookfixture" / "__pycache__").glob("__init__.*.pyc")), "bytecode not compiled"


def test_live_uv_contract_fails_closed_on_hash_mismatch(uv_fixture) -> None:
    runtime = load_runtime_install()
    result = _run_uv(runtime, uv_fixture, "rookfixture==1.0 --hash=sha256:" + "0" * 64 + "\n", "corrupt")

    assert result.returncode != 0
    assert "Hash mismatch" in result.stderr


def test_live_uv_contract_never_reaches_for_an_index(uv_fixture, monkeypatch) -> None:
    """A wheel missing from the wheelhouse fails, even with hostile index config.

    The environment is deliberately NOT sanitised and a uv.toml in the working
    directory names an index: --offline and --no-config alone must hold the line.
    """
    runtime = load_runtime_install()
    hostile_cwd = uv_fixture["root"] / "hostile"
    hostile_cwd.mkdir(exist_ok=True)
    (hostile_cwd / "uv.toml").write_text('index-url = "http://127.0.0.1:9/simple"\n', encoding="utf-8")
    monkeypatch.setenv("UV_INDEX_URL", "http://127.0.0.1:9/simple")
    monkeypatch.setenv("PIP_INDEX_URL", "http://127.0.0.1:9/simple")
    monkeypatch.delenv("UV_OFFLINE", raising=False)

    result = _run_uv(
        runtime,
        uv_fixture,
        "rookmissing==1.0 --hash=sha256:" + "1" * 64 + "\n",
        "missing",
        env=os.environ.copy(),
        cwd=hostile_cwd,
    )

    assert result.returncode != 0
    assert "rookmissing" in result.stderr
    assert "127.0.0.1" not in result.stdout + result.stderr


def test_live_uv_output_stays_plain_under_forced_color(uv_fixture, monkeypatch) -> None:
    """FORCE_COLOR / CLICOLOR_FORCE must not wrap the summary in ANSI escapes.

    The environment is deliberately NOT sanitised: --color never alone must hold.
    """
    runtime = load_runtime_install()
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    lock = f"rookfixture==1.0 --hash=sha256:{uv_fixture['wheel_sha256']}\n"

    result = _run_uv(runtime, uv_fixture, lock, "color", env=os.environ.copy())

    assert result.returncode == 0, result.stderr
    assert "\x1b[" not in result.stdout + result.stderr
    runtime.assert_uv_install_output(result.stdout + result.stderr)


def test_live_venv_stands_alone_after_its_cache_is_deleted(uv_fixture) -> None:
    """Hardlinked installs survive the cache: imports and compiled bytecode still work."""
    runtime = load_runtime_install()
    result = _run_uv(runtime, uv_fixture, f"rookfixture==1.0 --hash=sha256:{uv_fixture['wheel_sha256']}\n", "alone")
    assert result.returncode == 0, result.stderr
    shutil.rmtree(uv_fixture["root"] / "cache" / "alone")

    probe = subprocess.run(
        [str(uv_fixture["python"]), "-c",
         "import importlib.util, pathlib, rookfixture; "
         "print(rookfixture.VALUE, pathlib.Path(importlib.util.cache_from_source(rookfixture.__file__)).is_file())"],
        capture_output=True, text=True, timeout=60,
    )
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.split() == ["1", "True"]
