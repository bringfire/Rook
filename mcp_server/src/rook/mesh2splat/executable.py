from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from rook.runtime_paths import (
    get_bundled_knowledge_root,
    get_mutable_knowledge_root,
    resolve_runtime_paths,
)


MESH2SPLAT_EXE_NAME = "Mesh2Splat.exe"
MESH2SPLAT_ENV_VAR = "ROOK_MESH2SPLAT_EXE"
CONFIG_RELATIVE_PATH = Path("config") / "mesh2splat.json"
BUNDLED_EXECUTABLE_RELATIVE_PATH = (
    Path("tools") / "mesh2splat" / MESH2SPLAT_EXE_NAME
)


@dataclass(frozen=True)
class ExecutableResolution:
    path: Path
    source: str
    source_requires_path: bool
    diagnostics: dict[str, object] = field(default_factory=dict)


class Mesh2SplatExecutableError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        diagnostics: dict[str, object] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics or {}
        self.envelope: dict[str, object] = {
            "success": False,
            "data": {
                "code": code,
                "message": message,
                "retryable": code == "mesh2splat_not_found",
                "diagnostics": self.diagnostics,
            },
        }


def resolve_mesh2splat_executable(
    request_path: str | None, *, env: Mapping[str, str]
) -> ExecutableResolution:
    diagnostics = _empty_diagnostics(explicit_trusted_override=bool(request_path))

    if request_path:
        accepted = _accept_candidate(
            request_path,
            source="explicit",
            require_standard_basename=False,
            diagnostics=diagnostics,
        )
        if accepted is None:
            raise Mesh2SplatExecutableError(
                "invalid_executable",
                "mesh2splatPath must resolve to an existing executable file",
                diagnostics=diagnostics,
            )
        return _resolution(
            accepted,
            source="explicit",
            source_requires_path=False,
            diagnostics=diagnostics,
        )

    env_path = env.get(MESH2SPLAT_ENV_VAR)
    if env_path:
        accepted = _accept_candidate(
            env_path,
            source="environment",
            require_standard_basename=True,
            diagnostics=diagnostics,
        )
        if accepted is not None:
            return _resolution(
                accepted,
                source="environment",
                source_requires_path=False,
                diagnostics=diagnostics,
            )

    for source, config_path in (
        ("mutable_config", get_mutable_knowledge_root().joinpath(CONFIG_RELATIVE_PATH)),
        ("bundled_config", get_bundled_knowledge_root().joinpath(CONFIG_RELATIVE_PATH)),
    ):
        config_candidate = _read_config_candidate(config_path, source, diagnostics)
        if config_candidate is None:
            continue
        accepted = _accept_candidate(
            config_candidate,
            source=source,
            require_standard_basename=True,
            diagnostics=diagnostics,
        )
        if accepted is not None:
            return _resolution(
                accepted,
                source=source,
                source_requires_path=False,
                diagnostics=diagnostics,
            )

    bundled_candidate = bundled_mesh2splat_executable_path()
    accepted = _accept_candidate(
        bundled_candidate,
        source="bundled_location",
        require_standard_basename=True,
        diagnostics=diagnostics,
    )
    if accepted is not None:
        return _resolution(
            accepted,
            source="bundled_location",
            source_requires_path=False,
            diagnostics=diagnostics,
        )

    path_env = env.get("PATH")
    path_candidate = (
        shutil.which(MESH2SPLAT_EXE_NAME, path=path_env) if path_env else None
    )
    if path_candidate:
        accepted = _accept_candidate(
            path_candidate,
            source="path",
            require_standard_basename=True,
            diagnostics=diagnostics,
        )
        if accepted is not None:
            return _resolution(
                accepted,
                source="path",
                source_requires_path=True,
                diagnostics=diagnostics,
            )
    else:
        reason = "not_found_on_path" if path_env else "path_env_missing"
        _reject(diagnostics, "path", MESH2SPLAT_EXE_NAME, reason)

    raise Mesh2SplatExecutableError(
        "mesh2splat_not_found",
        "Mesh2Splat.exe was not found in explicit configuration, bundled location, or PATH",
        diagnostics=diagnostics,
    )


def bundled_mesh2splat_executable_path() -> Path:
    return resolve_runtime_paths().install_root / BUNDLED_EXECUTABLE_RELATIVE_PATH


def _empty_diagnostics(*, explicit_trusted_override: bool) -> dict[str, object]:
    return {
        "selected": None,
        "rejectedCandidates": [],
        "explicitTrustedOverride": explicit_trusted_override,
    }


def _resolution(
    path: Path,
    *,
    source: str,
    source_requires_path: bool,
    diagnostics: dict[str, object],
) -> ExecutableResolution:
    diagnostics["selected"] = {"source": source, "path": str(path)}
    return ExecutableResolution(
        path=path,
        source=source,
        source_requires_path=source_requires_path,
        diagnostics=diagnostics,
    )


def _read_config_candidate(
    config_path: Path, source: str, diagnostics: dict[str, object]
) -> str | None:
    if not config_path.exists():
        _reject(diagnostics, source, config_path, "config_missing")
        return None
    try:
        with config_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except json.JSONDecodeError:
        _reject(diagnostics, source, config_path, "config_malformed")
        return None
    except OSError:
        _reject(diagnostics, source, config_path, "config_unreadable")
        return None

    try:
        executable = payload["mesh2splat"]["executable"]
    except (KeyError, TypeError):
        _reject(diagnostics, source, config_path, "config_malformed")
        return None
    if not isinstance(executable, str) or not executable:
        _reject(diagnostics, source, config_path, "config_malformed")
        return None
    return executable


def _accept_candidate(
    candidate: str | Path,
    *,
    source: str,
    require_standard_basename: bool,
    diagnostics: dict[str, object],
) -> Path | None:
    candidate_path = Path(candidate)
    if (
        require_standard_basename
        and candidate_path.name.lower() != MESH2SPLAT_EXE_NAME.lower()
    ):
        _reject(diagnostics, source, candidate_path, "unexpected_basename")
        return None

    try:
        resolved = candidate_path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        _reject(diagnostics, source, candidate_path, "not_file")
        return None

    if not resolved.is_file():
        _reject(diagnostics, source, candidate_path, "not_file")
        return None
    if require_standard_basename and resolved.name.lower() != MESH2SPLAT_EXE_NAME.lower():
        _reject(diagnostics, source, resolved, "unexpected_basename")
        return None
    return resolved


def _reject(
    diagnostics: dict[str, object], source: str, path: str | Path, reason: str
) -> None:
    rejected = diagnostics["rejectedCandidates"]
    assert isinstance(rejected, list)
    rejected.append(
        {
            "source": source,
            "path": str(path),
            "reason": reason,
        }
    )
