"""Install-time management for Rook's private Python runtime.

Stdlib-only. Imported by post_install.py after the installer has copied files.
"""

from __future__ import annotations

import json
import os
import hashlib
import io
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path


SCHEMA_VERSION = 1
BOOTSTRAP_TOOL_REQUIREMENTS = ("pip==26.2.1", "setuptools==83.0.0")
# The installer's own tools: extracted from their hash-locked wheels at install
# time and never installed into either venv (#595).
INSTALLER_TOOL_REQUIREMENTS = ("uv==0.12.5",)


@dataclass(frozen=True)
class RuntimeLayout:
    rook_root: Path
    app_dir: Path
    data_dir: Path
    private_python: Path
    rook_venv: Path
    chirp_venv: Path
    wheelhouse: Path
    bootstrap_lock: Path
    installer_tools_lock: Path
    rook_lock: Path
    chirp_lock: Path
    runtime_manifest: Path
    install_state: Path

    @classmethod
    def from_rook_root(cls, rook_root: Path, python_version: str) -> "RuntimeLayout":
        app_dir = rook_root / "app"
        data_dir = rook_root / "data"
        return cls(
            rook_root=rook_root,
            app_dir=app_dir,
            data_dir=data_dir,
            private_python=rook_root
            / "python"
            / f"cpython-{python_version}"
            / "python.exe",
            rook_venv=rook_root / "venv",
            chirp_venv=app_dir / "chirp" / ".venv",
            wheelhouse=app_dir / "python-wheelhouse",
            bootstrap_lock=app_dir / "requirements-bootstrap-lock.txt",
            installer_tools_lock=app_dir / "requirements-installer-tools-lock.txt",
            rook_lock=app_dir / "requirements-rook-lock.txt",
            chirp_lock=app_dir / "requirements-chirp-lock.txt",
            runtime_manifest=app_dir / "python-runtime-manifest.json",
            install_state=data_dir / "install-state.json",
        )

    def uv_cache_dir(self, runtime_name: str) -> Path:
        """Per-venv uv cache under the runtime root.

        Same volume as the venvs, so ``--link-mode hardlink`` never falls back to
        copying; one cache per venv, so the Rook and Chirp venvs share no files.
        The installer deletes it once that venv is installed.
        """
        return self.installer_cache / f"uv-{runtime_name}"

    @property
    def installer_cache(self) -> Path:
        """Scratch root for the finalizer (uv caches, extracted tools); removed after."""
        return self.rook_root / "installer-cache"


def _is_under_user_profile(entry: str) -> bool:
    profile = os.environ.get("USERPROFILE")
    if not profile or not entry:
        return False
    try:
        return os.path.normcase(os.path.normpath(entry)).startswith(
            os.path.normcase(os.path.normpath(profile)) + os.sep
        )
    except (TypeError, ValueError):
        return False


def sanitized_path_entries(path_value: str) -> list[str]:
    """PATH entries pip may see: everything outside the user profile.

    pip resolves every PATH entry (``Path(i).resolve()``) when it checks whether
    installed scripts are on PATH. On Windows 11 25H2 that traversal is refused
    for junctions under the user profile (e.g. scoop's ``apps\\<tool>\\current``)
    with ``[WinError 448] The path cannot be traversed because it contains an
    untrusted mount point``, which aborted the Rook venv install for a user with
    scoop on PATH. Nothing pip runs here needs a user-profile PATH entry: the
    interpreter, wheelhouse and lockfiles are all passed as absolute paths.
    """
    return [entry for entry in path_value.split(os.pathsep) if entry and not _is_under_user_profile(entry)]


def build_sanitized_python_env(require_virtualenv: bool) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(sanitized_path_entries(env.get("PATH", "")))
    for key in (
        "PYTHONHOME",
        "PYTHONPATH",
        "PIP_INDEX_URL",
        "PIP_EXTRA_INDEX_URL",
        "PIP_CONFIG_FILE",
    ):
        env.pop(key, None)
    env["PIP_NO_INDEX"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    if require_virtualenv:
        env["PIP_REQUIRE_VIRTUALENV"] = "1"
    else:
        env.pop("PIP_REQUIRE_VIRTUALENV", None)
    return env


# uv install contract (#595). Hardlinking from the per-venv cache writes each file
# once instead of twice; on Windows each new file costs a Defender scan, which is
# what made the pip install slow. Bytecode is compiled at install because the MCP
# server runs with sys.dont_write_bytecode (#579).
UV_LINK_MODE = "hardlink"
# Plain output: FORCE_COLOR / CLICOLOR_FORCE would otherwise wrap uv's summary in
# ANSI escapes and fail assert_uv_install_output on a successful install.
UV_COLOR = "never"
UV_INSTALL_SWITCHES = (
    "--offline",
    "--no-index",
    "--no-build",
    "--require-hashes",
    "--no-config",
    "--compile-bytecode",
    "--no-progress",
)
# Options that take a value; every path-valued one must be absolute.
UV_INSTALL_PATH_OPTIONS = ("--python", "--find-links", "--cache-dir", "-r")
UV_INSTALL_FIXED_OPTIONS = {"--link-mode": UV_LINK_MODE, "--color": UV_COLOR}
UV_INSTALL_OPTIONS = UV_INSTALL_PATH_OPTIONS + tuple(UV_INSTALL_FIXED_OPTIONS)
_UV_OUTPUT_SUMMARY = re.compile(r"^(Resolved|Checked|Audited) \d+ packages?\b", re.MULTILINE)


def build_offline_uv_install_command(
    uv_exe: Path,
    venv_python: Path,
    wheelhouse_dir: Path,
    requirements_lock: Path,
    cache_dir: Path,
) -> list[str]:
    return [
        str(uv_exe),
        "pip",
        "install",
        "--python",
        str(venv_python),
        "--offline",
        "--no-index",
        "--find-links",
        str(wheelhouse_dir),
        "--no-build",
        "--require-hashes",
        "--no-config",
        "--compile-bytecode",
        "--cache-dir",
        str(cache_dir),
        "--link-mode",
        UV_LINK_MODE,
        "--no-progress",
        "--color",
        UV_COLOR,
        "-r",
        str(requirements_lock),
    ]


def assert_offline_uv_command(command: list[str]) -> None:
    """Reject any uv command that is not exactly the sealed-wheelhouse contract.

    An allowlist, not a denylist: every token must be a known switch or a known
    option with its value, each exactly once, so an index URL, a relative path or
    a stray flag cannot slip in through any spelling.
    """
    if len(command) < 3 or command[1:3] != ["pip", "install"]:
        raise ValueError("uv command must be '<uv.exe> pip install ...'")
    uv_exe = Path(command[0])
    if not uv_exe.is_absolute() or uv_exe.name.lower() != "uv.exe":
        raise ValueError(f"uv command must start with an absolute uv.exe path: {command[0]}")

    switches: list[str] = []
    options: dict[str, str] = {}
    tokens = iter(command[3:])
    for token in tokens:
        if token in UV_INSTALL_SWITCHES:
            if token in switches:
                raise ValueError(f"uv command repeats {token}")
            switches.append(token)
        elif token in UV_INSTALL_OPTIONS:
            if token in options:
                raise ValueError(f"uv command repeats {token}")
            value = next(tokens, None)
            if value is None or value.startswith("-"):
                raise ValueError(f"uv command option {token} has no value")
            options[token] = value
        else:
            raise ValueError(f"uv command contains a token outside the offline contract: {token}")

    missing = [s for s in UV_INSTALL_SWITCHES if s not in switches]
    missing += [o for o in UV_INSTALL_OPTIONS if o not in options]
    if missing:
        raise ValueError(f"offline uv command missing required flags: {missing}")
    for option in UV_INSTALL_PATH_OPTIONS:
        if not Path(options[option]).is_absolute():
            raise ValueError(f"uv command {option} must be an absolute path: {options[option]}")
    for option, required in UV_INSTALL_FIXED_OPTIONS.items():
        if options[option] != required:
            raise ValueError(f"uv command {option} must be {required}")


def build_sanitized_uv_env() -> dict[str, str]:
    """Environment for uv: the pip sanitisation plus no UV_*, colour or active-venv state.

    ``--no-config`` already ignores uv.toml files; dropping every ``UV_*`` variable
    covers the environment half (UV_INDEX_URL, UV_CACHE_DIR, UV_LINK_MODE, ...).
    ``--color never`` wins over the colour variables; dropping them is belt and braces.
    """
    env = build_sanitized_python_env(require_virtualenv=True)
    dropped = {"VIRTUAL_ENV", "CONDA_PREFIX", "FORCE_COLOR", "CLICOLOR_FORCE"}
    for key in list(env):
        if key.upper().startswith("UV_") or key.upper() in dropped:
            del env[key]
    return env


_LOCK_ROW = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9.!+_-]+) --hash=sha256:([0-9a-fA-F]{64})$"
)


def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_hash_lock(lock: Path) -> list[tuple[str, str, str]]:
    """``(name, version, sha256)`` rows; any row that is not hash-pinned is an error."""
    rows: list[tuple[str, str, str]] = []
    for line in lock.read_text(encoding="utf-8-sig").splitlines():
        row = line.strip()
        if not row or row.startswith("#"):
            continue
        match = _LOCK_ROW.match(row)
        if not match:
            raise ValueError(f"{lock.name}: not a hash-pinned requirement: {row}")
        rows.append((match[1], match[2], match[3].lower()))
    return rows


@dataclass(frozen=True)
class BundledTool:
    name: str
    version: str
    wheel: str
    wheel_sha256: str
    executable: Path

    def evidence(self) -> dict[str, str]:
        return {
            "name": self.name,
            "version": self.version,
            "wheel": self.wheel,
            "wheel_sha256": self.wheel_sha256,
        }


def extract_bundled_uv(wheelhouse: Path, tools_lock: Path, dest_dir: Path) -> BundledTool:
    """Extract uv.exe from the one wheelhouse wheel whose bytes match the tools lock.

    The wheel is read once into memory, hashed, and unzipped from those same
    bytes, so the executable is exactly what the lock pins.
    """
    rows = read_hash_lock(tools_lock)
    if len(rows) != 1 or canonical_name(rows[0][0]) != "uv":
        raise ValueError(f"{tools_lock.name} must pin exactly one uv wheel")
    _name, version, digest = rows[0]
    for wheel in sorted(wheelhouse.glob(f"uv-{version}-*.whl")):
        payload = wheel.read_bytes()
        if hashlib.sha256(payload).hexdigest() == digest:
            break
    else:
        raise ValueError(f"no wheelhouse wheel matches the locked uv=={version} hash")

    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / "uv.exe"
    partial = dest_dir / "uv.exe.partial"
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        with archive.open(f"uv-{version}.data/scripts/uv.exe") as source, partial.open("wb") as sink:
            shutil.copyfileobj(source, sink, 1024 * 1024)
    os.replace(partial, target)
    return BundledTool("uv", version, wheel.name, digest, target)


def freeze_mismatches(freeze_output: str, locks: list[Path]) -> list[str]:
    """Differences between ``pip freeze --all`` and the union of the given locks."""
    expected = {canonical_name(name): version for lock in locks for name, version, _ in read_hash_lock(lock)}
    installed: dict[str, str] = {}
    for line in freeze_output.splitlines():
        row = line.strip()
        if not row:
            continue
        if "==" in row:
            name, version = row.split("==", 1)
            installed[canonical_name(name)] = version
        else:
            installed[row] = "<not a pinned release>"
    problems = [f"missing {name}=={version}" for name, version in expected.items() if name not in installed]
    problems += [f"unexpected {name}=={version}" for name, version in installed.items() if name not in expected]
    problems += [
        f"{name}: installed {installed[name]}, locked {version}"
        for name, version in expected.items()
        if name in installed and installed[name] != version
    ]
    return sorted(problems)


def assert_uv_install_output(output: str) -> None:
    """uv prints no index lines offline; require its summary and no URL at all."""
    if "http://" in output or "https://" in output:
        raise ValueError("uv output mentions a URL during an offline install")
    if not _UV_OUTPUT_SUMMARY.search(output):
        raise ValueError("uv output does not show a resolved or checked lock")


def needs_venv_recreate(
    install_state: dict,
    runtime_name: str,
    python_identity_hash: str,
    lockfile_sha256: str,
) -> bool:
    if install_state.get("schema_version") != SCHEMA_VERSION:
        return True
    runtime_state = install_state.get(runtime_name, {})
    return (
        runtime_state.get("python_identity_hash") != python_identity_hash
        or runtime_state.get("lockfile_sha256") != lockfile_sha256
    )


def read_install_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_site_packages_import(module_file: Path) -> bool:
    normalized = str(module_file).replace("\\", "/").lower()
    return "/site-packages/" in normalized


def write_install_state(path: Path, payload: dict) -> None:
    state = {"schema_version": SCHEMA_VERSION}
    state.update(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _slash(path: Path) -> str:
    return str(path).replace("\\", "/")


def build_release_mcp_env(
    install_dir: Path, data_dir: Path, chirp_dir: Path | None
) -> dict[str, str]:
    dspy_cache_dir = data_dir / "dspy-cache"
    env_vars = {
        "PYTHONPATH": "",
        "PYTHONHOME": "",
        "ROOK_INSTALL_ROOT": _slash(install_dir),
        "ROOK_DATA_DIR": _slash(data_dir),
        "ROOK_MODE": "release",
        "DSPY_CACHEDIR": _slash(dspy_cache_dir),
        "ROOK_DSPY_RESTRICT_PICKLE": "1",
    }
    if chirp_dir is not None:
        env_vars["CHIRP_HOME"] = _slash(chirp_dir)
    return env_vars


def build_chat_service_manifest(
    mcp_server_dir: Path,
    rook_venv_python: Path,
    release_mode: bool,
) -> dict:
    rook_root = rook_venv_python.parent.parent.parent
    app_dir = rook_root / "app"
    data_dir = rook_root / "data"
    chirp_dir = app_dir / "chirp"
    return {
        "pythonPath": str(rook_venv_python),
        "workingDirectory": str(mcp_server_dir),
        "module": "rook.agent.chat.service_main",
        "owner": "rhino-panel",
        "pythonPathEntries": [] if release_mode else [str(mcp_server_dir / "src")],
        "environment": build_release_mcp_env(app_dir, data_dir, chirp_dir)
        if release_mode
        else {},
    }
