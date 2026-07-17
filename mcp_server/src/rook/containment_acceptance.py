"""Acceptance-only certification for installed containment boundaries.

This module is intentionally a command-line harness, not an MCP tool or an
authorization surface.  It observes the existing installed runtime through
fixed probes and refuses caller-supplied hooks, handlers, or tool identities.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import contextvars
import hashlib
import importlib
import inspect
import json
import os
import re
import sys
import tempfile
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any, AsyncIterator, Callable, Iterator, Literal

from .runtime_paths import resolve_runtime_paths
from .tool_lifecycle import (
    DispatchOrigin,
    contained_names,
    containment_envelope,
    resolve_contained_identity,
)


SCHEMA_VERSION = 1
PROFILE_VALUES = ("full", "lean", "readonly")
CONTAINED_TOOL_NAMES = (
    "gh_execute_intent",
    "rhino_execute_intent",
    "plan_and_execute",
    "spawn_agent",
    "gh_explore_workflow",
    "gh_replay_recipe",
)
STAGE_NAMES = (
    "recording_attempt",
    "format_result",
    "argument_access",
    "profile",
    "capability",
    "knowledge",
    "model",
    "target",
    "http",
    "host",
    "observation",
    "adaptation",
    "receipt",
)
ARBITRARY_INTERNAL_SEAMS = (
    "server._call_tool_dispatch",
    "server._mcp_tool_executor",
    "ToolDispatcher.dispatch",
    "ToolDispatcher._dispatch_inner",
    "ToolDispatcher._call_local",
    "ToolDispatcher._dispatch_with_knowledge",
    "RookAgent._run_loop",
    "RookAgent._execute_tool",
    "RookAgent._execute_local_tool",
    "ChatRunner.run_turn",
    "rook.agent.plan_graph_live.apply_live_producer_node",
    "BootstrapRunner.run_test",
    "BootstrapRunner._mock_executor",
    "bootstrap.HttpExecutor.execute",
    "bootstrap.create_mock_executor.callable",
    "learning.create_tool_executor.callable",
    "Investigator.investigate_tool",
    "Investigator.investigate_gap",
    "Investigator.investigate_workflow",
    "Investigator._run_experiment",
    "HybridInvestigator.investigate_tool",
    "HybridInvestigator.investigate_gap",
    "LearningSession.run_investigation_cycle.tool_target",
    "explorer.HttpExecutor.execute",
    "explorer.HttpExecutor.execute_sync",
    "explorer.MockExecutor.execute",
    "explorer.MockExecutor.execute_sync",
)
CONSTANT_INTERNAL_SEAMS = MappingProxyType(
    {
        "server._handle_spawn_agent": "spawn_agent",
        "server._handle_plan_and_execute": "plan_and_execute",
    }
)

_RUN_ID_RE = re.compile(r"^[0-9a-f]{32}$", re.ASCII)
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$", re.ASCII)
_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$",
    re.ASCII,
)
_PROFILE_COUNTS = MappingProxyType(
    {"full": 422, "lean": 20, "readonly": 148}
)
_DISCOVERY_COUNTS = MappingProxyType(
    {"discovery-default": 422, "discovery-interactive": 425}
)
_CONTROLLED_EXACT_NAMES = frozenset(
    {
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONUSERBASE",
        "PYTHONNOUSERSITE",
        "DSPY_MODEL",
        "DSPY_CACHEDIR",
        "CHIRP_HOME",
    }
)
_RELEVANT_NON_ROOK_ENV = frozenset(
    {
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONUSERBASE",
        "PYTHONNOUSERSITE",
        "DSPY_MODEL",
        "DSPY_CACHEDIR",
        "CHIRP_HOME",
    }
)


class AcceptanceError(RuntimeError):
    """The installed runtime did not satisfy the acceptance contract."""


def _bounded_exception_summary(exc: BaseException) -> str:
    """Preserve nested task-group causes without emitting a traceback."""
    if isinstance(exc, BaseExceptionGroup):
        children = [
            _bounded_exception_summary(child)
            for child in exc.exceptions[:4]
        ]
        if len(exc.exceptions) > 4:
            children.append(f"... {len(exc.exceptions) - 4} more")
        detail = " | ".join(children)
    else:
        detail = str(exc)
    summary = f"{type(exc).__name__}: {detail}"
    return summary if len(summary) <= 1000 else summary[:997] + "..."


class InstalledSpyTripped(AcceptanceError):
    """A forbidden stage was reached while an acceptance probe was active."""

    def __init__(self, stage: str):
        self.stage = stage
        super().__init__(f"installed acceptance spy tripped: {stage}")


@dataclass(frozen=True)
class PatchpointSpec:
    identifier: str
    stage: str
    kind: Literal["sync", "async"]


_EXPECTED_PATCHPOINT_TRIPLES = (
    (
        "rook.tool_lifecycle_runtime._record_containment_denial",
        "recording_attempt",
        "sync",
    ),
    ("rook.server._format_tool_result", "format_result", "sync"),
    ("rook.server.validate_arguments", "argument_access", "sync"),
    (
        "mcp.server.lowlevel.server.Server._get_cached_tool_definition",
        "argument_access",
        "async",
    ),
    (
        "mcp.server.lowlevel.server.jsonschema.validate",
        "argument_access",
        "sync",
    ),
    ("rook.server.tool_blocked", "profile", "sync"),
    ("rook.server._get_capability_index", "capability", "async"),
    ("rook.server.inject_knowledge", "knowledge", "async"),
    ("rook.agent.base_agent.RookAgent._call_model", "model", "async"),
    ("rook.server.targeting.policy_for_tool", "target", "sync"),
    ("httpx.AsyncClient.get", "http", "async"),
    ("httpx.AsyncClient.post", "http", "async"),
    ("httpx.AsyncClient.request", "http", "async"),
    (
        "rook.bootstrap.executor.urllib.request.urlopen",
        "http",
        "sync",
    ),
    ("rook.server.call_rhino", "host", "async"),
    ("rook.server._record_observation", "observation", "sync"),
    ("rook.server.get_phase_tracker", "adaptation", "sync"),
    ("rook.server.build_script_receipt", "receipt", "sync"),
)
PATCHPOINT_SPECS = tuple(
    PatchpointSpec(*values) for values in _EXPECTED_PATCHPOINT_TRIPLES
)


@dataclass(frozen=True)
class ResolvedPatchpoint:
    spec: PatchpointSpec
    owner: object
    attribute: str
    descriptor: object
    original: Callable[..., Any]


@dataclass(frozen=True)
class InternalProbeSpec:
    seam: str
    tool: str
    origin: str
    adapter: str


@dataclass(frozen=True)
class _PreparedInternalProbe:
    invoke: Callable[[], object]
    is_async: bool
    primary_model_calls: Callable[[], int]


def _origin_for_seam(seam: str) -> str:
    if seam.startswith("server._call_tool_dispatch") or seam.startswith(
        "server._mcp_tool_executor"
    ):
        return DispatchOrigin.SERVER_DISPATCH.value
    if seam.startswith("ToolDispatcher."):
        return DispatchOrigin.TOOL_DISPATCHER.value
    if seam.startswith("RookAgent."):
        return DispatchOrigin.ROOK_AGENT.value
    if seam == "ChatRunner.run_turn":
        return DispatchOrigin.ROOK_CHAT.value
    if seam == "rook.agent.plan_graph_live.apply_live_producer_node":
        return DispatchOrigin.PLAN_GRAPH.value
    return DispatchOrigin.INTERNAL_HANDLER.value


def _expected_internal_pairs() -> list[InternalProbeSpec]:
    pairs = [
        InternalProbeSpec(
            seam=seam,
            tool=tool,
            origin=_origin_for_seam(seam),
            adapter=seam,
        )
        for seam in ARBITRARY_INTERNAL_SEAMS
        for tool in CONTAINED_TOOL_NAMES
    ]
    pairs.extend(
        InternalProbeSpec(
            seam=seam,
            tool=tool,
            origin=DispatchOrigin.INTERNAL_HANDLER.value,
            adapter=seam,
        )
        for seam, tool in CONSTANT_INTERNAL_SEAMS.items()
    )
    return pairs


def _validate_internal_pair_set(
    pairs: Iterable[InternalProbeSpec],
) -> None:
    actual_list = list(pairs)
    expected = {
        (seam, tool)
        for seam in ARBITRARY_INTERNAL_SEAMS
        for tool in CONTAINED_TOOL_NAMES
    } | set(CONSTANT_INTERNAL_SEAMS.items())
    actual = {(item.seam, item.tool) for item in actual_list}
    if (
        len(actual_list) != 164
        or len(actual) != 164
        or actual != expected
    ):
        raise AcceptanceError("installed internal seam set drift")
    for item in actual_list:
        if item.origin != _origin_for_seam(item.seam):
            raise AcceptanceError(
                f"installed internal seam origin drift: {item.seam}"
            )


def _absolute_spy_path(raw: str) -> str:
    path = Path(raw)
    if not path.is_absolute() or path.suffix.casefold() != ".json":
        raise argparse.ArgumentTypeError(
            "--spy-path must be a fresh absolute .json path"
        )
    return str(path.resolve())


def _run_id(raw: str) -> str:
    if _RUN_ID_RE.fullmatch(raw) is None:
        raise argparse.ArgumentTypeError("--run-id must be exactly 32 lowercase hex")
    return raw


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m rook.containment_acceptance",
        description="Certify installed legacy semantic containment.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    transport = subparsers.add_parser("transport-profile")
    transport.add_argument(
        "--profile",
        choices=PROFILE_VALUES,
        required=True,
    )
    transport.add_argument("--artifact-dir", required=True)

    for command in (
        "discovery-default",
        "discovery-interactive",
        "internal-matrix",
    ):
        child = subparsers.add_parser(command)
        child.add_argument("--artifact-dir", required=True)

    private = subparsers.add_parser(
        "_transport-child",
        help=argparse.SUPPRESS,
    )
    private.add_argument("--profile", choices=PROFILE_VALUES, required=True)
    private.add_argument("--run-id", type=_run_id, required=True)
    private.add_argument("--spy-path", type=_absolute_spy_path, required=True)
    return parser


def _canonical_path(
    raw: str | os.PathLike[str],
    *,
    label: str,
    require_directory: bool = True,
) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise AcceptanceError(f"{label} must be absolute")
    path = path.resolve()
    if require_directory and not path.is_dir():
        raise AcceptanceError(f"{label} must be an existing directory: {path}")
    return path


def _sanitized_child_environment(
    source: Mapping[str, str],
    *,
    install_root: Path,
    data_root: Path,
    dspy_cache: Path,
    chirp_home: Path | None = None,
    profile: str | None = None,
    interactive: bool = False,
) -> dict[str, str]:
    install_root = _canonical_path(
        install_root,
        label="installed root",
    )
    data_root = _canonical_path(data_root, label="data root")
    dspy_cache = _canonical_path(dspy_cache, label="DSPy cache")
    if profile is not None and profile not in PROFILE_VALUES:
        raise AcceptanceError(f"invalid acceptance profile: {profile!r}")
    if interactive and profile != "full":
        raise AcceptanceError("interactive discovery requires profile full")
    if chirp_home is not None:
        chirp_home = _canonical_path(chirp_home, label="Chirp home")

    cleaned: dict[str, str] = {}
    for raw_name, value in source.items():
        name = str(raw_name)
        folded = name.casefold()
        if (
            name.upper() in _CONTROLLED_EXACT_NAMES
            or folded.startswith("rook_")
        ):
            continue
        cleaned[name] = str(value)

    cleaned.update(
        {
            "PYTHONNOUSERSITE": "1",
            "ROOK_INSTALL_ROOT": str(install_root),
            "ROOK_DATA_DIR": str(data_root),
            "ROOK_MODE": "release",
            "ROOK_DSPY_RESTRICT_PICKLE": "1",
            "DSPY_CACHEDIR": str(dspy_cache),
        }
    )
    if chirp_home is not None:
        cleaned["CHIRP_HOME"] = str(chirp_home)
    if profile is not None:
        cleaned["ROOK_MCP_TOOL_PROFILE"] = profile
    if interactive:
        cleaned["ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING"] = "1"
    return cleaned


def _relevant_environment(
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source = os.environ if source is None else source
    relevant = {
        key: value
        for key, value in source.items()
        if key.upper() in _RELEVANT_NON_ROOK_ENV
        or key.casefold().startswith("rook_")
    }
    return dict(sorted(relevant.items(), key=lambda item: item[0].casefold()))


def _expected_relevant_environment(
    *,
    install_root: Path,
    data_root: Path,
    dspy_cache: Path,
    chirp_home: Path | None,
    profile: str | None,
    interactive: bool,
) -> dict[str, str]:
    if profile is not None and profile not in PROFILE_VALUES:
        raise AcceptanceError(f"invalid expected profile: {profile!r}")
    if interactive and profile != "full":
        raise AcceptanceError("interactive environment requires profile full")
    expected = {
        "PYTHONNOUSERSITE": "1",
        "DSPY_CACHEDIR": str(Path(dspy_cache).expanduser().resolve()),
        "ROOK_INSTALL_ROOT": str(Path(install_root).expanduser().resolve()),
        "ROOK_DATA_DIR": str(Path(data_root).expanduser().resolve()),
        "ROOK_MODE": "release",
        "ROOK_DSPY_RESTRICT_PICKLE": "1",
    }
    if chirp_home is not None:
        expected["CHIRP_HOME"] = str(
            Path(chirp_home).expanduser().resolve()
        )
    if profile is not None:
        expected["ROOK_MCP_TOOL_PROFILE"] = profile
    if interactive:
        expected["ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING"] = "1"
    return expected


def _validate_relevant_environment(
    environment: object,
    *,
    install_root: Path,
    data_root: Path,
    dspy_cache: Path,
    chirp_home: Path | None,
    profile: str | None,
    interactive: bool,
) -> None:
    if not isinstance(environment, Mapping) or not all(
        type(key) is str and type(value) is str
        for key, value in environment.items()
    ):
        raise AcceptanceError("environment evidence is malformed")
    folded = {
        key.casefold(): value
        for key, value in environment.items()
    }
    if len(folded) != len(environment):
        raise AcceptanceError("environment evidence has duplicate keys")
    expected = {
        key.casefold(): value
        for key, value in _expected_relevant_environment(
            install_root=install_root,
            data_root=data_root,
            dspy_cache=dspy_cache,
            chirp_home=chirp_home,
            profile=profile,
            interactive=interactive,
        ).items()
    }
    if folded != expected:
        missing = sorted(set(expected).difference(folded))
        unexpected = sorted(set(folded).difference(expected))
        changed = sorted(
            key
            for key in set(expected).intersection(folded)
            if expected[key] != folded[key]
        )
        raise AcceptanceError(
            "environment closed allowlist drift: "
            f"missing={missing}, unexpected={unexpected}, changed={changed}"
        )


def _loaded_rook_origins() -> dict[str, str]:
    origins: dict[str, str] = {}
    for name, module in sorted(sys.modules.items()):
        evidence_name = name
        if name == "__main__":
            spec = getattr(module, "__spec__", None)
            spec_name = getattr(spec, "name", None)
            if type(spec_name) is str:
                evidence_name = spec_name
        if (
            evidence_name != "rook"
            and not evidence_name.startswith("rook.")
        ):
            continue
        raw_file = getattr(module, "__file__", None)
        if raw_file is None:
            continue
        origins[evidence_name] = str(Path(raw_file).resolve())
    return origins


def _normalized_sys_path() -> list[str]:
    cwd = Path.cwd()
    normalized: list[str] = []
    for raw in sys.path:
        path = cwd if raw == "" else Path(raw)
        try:
            normalized.append(str(path.expanduser().resolve()))
        except (OSError, RuntimeError):
            normalized.append(str(path))
    return normalized


def _collect_process_evidence() -> dict[str, object]:
    from .learning.metrics_store import get_metrics_store

    runtime = resolve_runtime_paths()
    snapshot = get_metrics_store().get_containment_denials_snapshot()
    return {
        "executable": str(Path(sys.executable).resolve()),
        "installed_root": str(runtime.install_root.resolve()),
        "cwd": str(Path.cwd().resolve()),
        "environment": _relevant_environment(),
        "sys_path": _normalized_sys_path(),
        "rook_origins": _loaded_rook_origins(),
        "process_id": snapshot["process_id"],
        "process_start_token": snapshot["process_start_token"],
    }


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _path_looks_like_development_source(path: Path) -> bool:
    resolved = Path(path).expanduser().resolve()
    normalized = str(resolved).replace("\\", "/").casefold()
    if (
        "/.worktrees/" in normalized
        or normalized.endswith("/mcp_server/src")
        or "/source/repos/rook/mcp_server/src/" in normalized
    ):
        return True
    return any(
        (
            (candidate / ".git").is_file()
            or (candidate / ".git").is_dir()
        )
        and (candidate / "Rook.sln").is_file()
        and (candidate / "mcp_server" / "src" / "rook").is_dir()
        for candidate in (resolved, *resolved.parents)
    )


def _validate_process_evidence(
    evidence: Mapping[str, object],
    *,
    expected_install_root: Path,
    expected_data_root: Path | None = None,
    expected_dspy_cache: Path | None = None,
    expected_chirp_home: Path | None = None,
    expected_profile: str | None = None,
    expected_interactive: bool = False,
    forbidden_source_roots: Iterable[Path] = (),
    allowed_command_roots: Iterable[Path] = (),
    required_rook_modules: Iterable[str] = ("rook",),
) -> None:
    expected_keys = {
        "executable",
        "installed_root",
        "cwd",
        "environment",
        "sys_path",
        "rook_origins",
        "process_id",
        "process_start_token",
    }
    if set(evidence) != expected_keys:
        raise AcceptanceError("process evidence keys drift")

    install_root = expected_install_root.expanduser().resolve()
    if Path(str(evidence["installed_root"])).resolve() != install_root:
        raise AcceptanceError("installed root drift")
    executable = Path(str(evidence["executable"]))
    if not executable.is_absolute():
        raise AcceptanceError("installed executable is not absolute")
    raw_cwd = Path(str(evidence["cwd"])).expanduser()
    if not raw_cwd.is_absolute():
        raise AcceptanceError("installed cwd is not absolute")
    cwd = raw_cwd.resolve()
    if type(evidence["process_id"]) is not int:
        raise AcceptanceError("process identity is malformed")
    token = evidence["process_start_token"]
    if type(token) is not str or _TOKEN_RE.fullmatch(token) is None:
        raise AcceptanceError("process start token is malformed")

    data_root = (
        install_root.parent / "data"
        if expected_data_root is None
        else Path(expected_data_root)
    ).expanduser().resolve()
    dspy_cache = (
        data_root / "dspy-cache"
        if expected_dspy_cache is None
        else Path(expected_dspy_cache)
    ).expanduser().resolve()
    _validate_relevant_environment(
        evidence["environment"],
        install_root=install_root,
        data_root=data_root,
        dspy_cache=dspy_cache,
        chirp_home=expected_chirp_home,
        profile=expected_profile,
        interactive=expected_interactive,
    )

    command_roots = [
        Path(root).expanduser().resolve() for root in allowed_command_roots
    ]
    forbidden_roots = [
        Path(root).expanduser().resolve() for root in forbidden_source_roots
    ]
    if not _is_relative_to(cwd, install_root) and (
        any(_is_relative_to(cwd, root) for root in forbidden_roots)
        or _path_looks_like_development_source(cwd)
    ):
        raise AcceptanceError(f"source cwd contamination: {cwd}")
    raw_sys_path = evidence["sys_path"]
    if type(raw_sys_path) is not list or not all(
        type(item) is str for item in raw_sys_path
    ):
        raise AcceptanceError("sys.path evidence is malformed")
    for raw_path in raw_sys_path:
        path = Path(raw_path).expanduser().resolve()
        if _is_relative_to(path, install_root):
            continue
        if (
            any(_is_relative_to(path, root) for root in forbidden_roots)
            or _path_looks_like_development_source(path)
        ):
            raise AcceptanceError(f"source path contamination: {path}")
        if any(_is_relative_to(path, root) for root in command_roots):
            continue

    origins = evidence["rook_origins"]
    if not isinstance(origins, Mapping):
        raise AcceptanceError("rook origin evidence is malformed")
    for required in required_rook_modules:
        if required not in origins:
            raise AcceptanceError(f"missing loaded rook origin: {required}")
    for name, raw_origin in origins.items():
        if type(name) is not str or type(raw_origin) is not str:
            raise AcceptanceError("rook origin evidence is malformed")
        origin = Path(raw_origin).expanduser().resolve()
        if not _is_relative_to(origin, install_root):
            raise AcceptanceError(
                f"rook module origin escaped installed root: {name}={origin}"
            )


def _atomic_write_json(path: Path, payload: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_patchpoint_table_contract() -> None:
    actual = tuple(
        (spec.identifier, spec.stage, spec.kind)
        for spec in PATCHPOINT_SPECS
    )
    if (
        actual != _EXPECTED_PATCHPOINT_TRIPLES
        or len({item[0] for item in actual}) != len(actual)
        or any(item[1] not in STAGE_NAMES for item in actual)
    ):
        raise AcceptanceError("immutable patchpoint table drift")


def _resolve_owner_path(identifier: str) -> tuple[object, str]:
    parts = identifier.split(".")
    for boundary in range(len(parts) - 1, 0, -1):
        module_name = ".".join(parts[:boundary])
        try:
            owner: object = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name and not module_name.startswith(
                f"{exc.name}."
            ):
                raise
            continue
        for part in parts[boundary:-1]:
            if not hasattr(owner, part):
                raise AcceptanceError(
                    f"missing patchpoint owner: {identifier}"
                )
            owner = getattr(owner, part)
        return owner, parts[-1]
    raise AcceptanceError(f"could not import patchpoint owner: {identifier}")


def _resolve_one_patchpoint(spec: PatchpointSpec) -> ResolvedPatchpoint:
    owner, attribute = _resolve_owner_path(spec.identifier)
    try:
        descriptor = inspect.getattr_static(owner, attribute)
        original = getattr(owner, attribute)
    except AttributeError as exc:
        raise AcceptanceError(
            f"missing patchpoint target: {spec.identifier}"
        ) from exc
    if not callable(original):
        raise AcceptanceError(
            f"patchpoint target is not callable: {spec.identifier}"
        )
    actual_kind = "async" if inspect.iscoroutinefunction(original) else "sync"
    if actual_kind != spec.kind:
        raise AcceptanceError(
            f"patchpoint kind drift: {spec.identifier} "
            f"expected={spec.kind} actual={actual_kind}"
        )
    return ResolvedPatchpoint(
        spec=spec,
        owner=owner,
        attribute=attribute,
        descriptor=descriptor,
        original=original,
    )


def _resolve_patchpoints() -> tuple[ResolvedPatchpoint, ...]:
    _assert_patchpoint_table_contract()
    resolved = tuple(_resolve_one_patchpoint(spec) for spec in PATCHPOINT_SPECS)
    if tuple(item.spec for item in resolved) != PATCHPOINT_SPECS:
        raise AcceptanceError("patchpoint resolution order drift")
    return resolved


def _descriptor_with_callable(descriptor: object, wrapper: Callable[..., Any]):
    if isinstance(descriptor, staticmethod):
        return staticmethod(wrapper)
    if isinstance(descriptor, classmethod):
        return classmethod(wrapper)
    return wrapper


_TRIP_SENTINEL = object()


class _SpyController:
    def __init__(self) -> None:
        self._phase = contextvars.ContextVar[
            str | None
        ]("rook_containment_acceptance_phase", default=None)
        self.counters = {stage: 0 for stage in STAGE_NAMES}

    @property
    def phase_name(self) -> str | None:
        return self._phase.get()

    @contextlib.contextmanager
    def phase(self, name: str) -> Iterator[None]:
        token = self._phase.set(name)
        try:
            yield
        finally:
            self._phase.reset(token)

    def reset(self) -> None:
        for stage in STAGE_NAMES:
            self.counters[stage] = 0

    def trip(self, stage: str) -> None:
        self.counters[stage] += 1
        raise InstalledSpyTripped(stage)


def _is_trip_sentinel(args: tuple[Any, ...], kwargs: dict[str, Any]) -> bool:
    return len(args) == 1 and args[0] is _TRIP_SENTINEL and not kwargs


def _make_spy_wrapper(
    spec: PatchpointSpec,
    original: Callable[..., Any],
    controller: _SpyController,
) -> Callable[..., Any]:
    if spec.kind == "async":
        async def async_wrapper(*args, **kwargs):
            phase = controller.phase_name
            if phase is None:
                return await original(*args, **kwargs)
            if _is_trip_sentinel(args, kwargs):
                controller.trip(spec.stage)
            if spec.stage in {"recording_attempt", "format_result"}:
                controller.counters[spec.stage] += 1
                return await original(*args, **kwargs)
            controller.trip(spec.stage)

        return async_wrapper

    def sync_wrapper(*args, **kwargs):
        phase = controller.phase_name
        if phase is None:
            return original(*args, **kwargs)
        if _is_trip_sentinel(args, kwargs):
            controller.trip(spec.stage)
        if spec.stage in {"recording_attempt", "format_result"}:
            controller.counters[spec.stage] += 1
            return original(*args, **kwargs)
        controller.trip(spec.stage)

    return sync_wrapper


async def _run_wrapper_factory_self_test() -> dict[str, bool]:
    marker = object()

    def sync_original(value):
        return marker if value is _TRIP_SENTINEL else value

    async def async_original(value):
        return marker if value is _TRIP_SENTINEL else value

    sync_controller = _SpyController()
    sync_spec = PatchpointSpec("self-test.sync", "argument_access", "sync")
    sync_wrapper = _make_spy_wrapper(
        sync_spec,
        sync_original,
        sync_controller,
    )
    sync_unscoped = (
        sync_wrapper(_TRIP_SENTINEL) is marker
        and sync_controller.counters == {stage: 0 for stage in STAGE_NAMES}
    )
    sync_scoped = False
    sync_controller.reset()
    try:
        with sync_controller.phase("direct"):
            sync_wrapper(_TRIP_SENTINEL)
    except InstalledSpyTripped as exc:
        sync_scoped = (
            exc.stage == "argument_access"
            and sync_controller.counters["argument_access"] == 1
            and sum(sync_controller.counters.values()) == 1
        )

    async_controller = _SpyController()
    async_spec = PatchpointSpec("self-test.async", "model", "async")
    async_wrapper = _make_spy_wrapper(
        async_spec,
        async_original,
        async_controller,
    )
    async_unscoped = (
        await async_wrapper(_TRIP_SENTINEL) is marker
        and async_controller.counters
        == {stage: 0 for stage in STAGE_NAMES}
    )
    async_scoped = False
    async_controller.reset()
    try:
        with async_controller.phase("direct"):
            await async_wrapper(_TRIP_SENTINEL)
    except InstalledSpyTripped as exc:
        async_scoped = (
            exc.stage == "model"
            and async_controller.counters["model"] == 1
            and sum(async_controller.counters.values()) == 1
        )

    result = {
        "sync_scoped_trip": sync_scoped,
        "sync_unscoped_passthrough": sync_unscoped,
        "async_scoped_trip": async_scoped,
        "async_unscoped_passthrough": async_unscoped,
    }
    if not all(result.values()):
        raise AcceptanceError("wrapper factory self-test failed")
    return result


@dataclass
class _InstalledSpies:
    controller: _SpyController
    self_test: dict[str, object]

    @property
    def counters(self) -> dict[str, int]:
        return dict(self.controller.counters)

    @contextlib.contextmanager
    def phase(self, name: str) -> Iterator[None]:
        with self.controller.phase(name):
            yield

    def reset(self) -> None:
        self.controller.reset()


@contextlib.asynccontextmanager
async def _installed_spy_scope() -> AsyncIterator[_InstalledSpies]:
    resolved = _resolve_patchpoints()
    controller = _SpyController()
    wrapper_factory = await _run_wrapper_factory_self_test()
    installed: list[ResolvedPatchpoint] = []
    wrappers: dict[str, Callable[..., Any]] = {}
    try:
        for item in resolved:
            wrapper = _make_spy_wrapper(
                item.spec,
                item.original,
                controller,
            )
            setattr(
                item.owner,
                item.attribute,
                _descriptor_with_callable(item.descriptor, wrapper),
            )
            installed.append(item)
            wrappers[item.spec.identifier] = wrapper

        patchpoint_results: dict[str, bool] = {}
        for item in resolved:
            controller.reset()
            wrapper = wrappers[item.spec.identifier]
            caught: InstalledSpyTripped | None = None
            try:
                with controller.phase("self-test"):
                    if item.spec.kind == "async":
                        await wrapper(_TRIP_SENTINEL)
                    else:
                        wrapper(_TRIP_SENTINEL)
            except InstalledSpyTripped as exc:
                caught = exc
            expected = {stage: 0 for stage in STAGE_NAMES}
            expected[item.spec.stage] = 1
            passed = (
                caught is not None
                and caught.stage == item.spec.stage
                and controller.counters == expected
            )
            if not passed:
                raise AcceptanceError(
                    f"installed wrapper self-test failed: {item.spec.identifier}"
                )
            patchpoint_results[item.spec.identifier] = True

        controller.reset()
        yield _InstalledSpies(
            controller=controller,
            self_test={
                "patchpoints": patchpoint_results,
                "wrapper_factory": wrapper_factory,
            },
        )
    finally:
        for item in reversed(installed):
            setattr(item.owner, item.attribute, item.descriptor)


def _validate_snapshot_shape(snapshot: Mapping[str, object]) -> None:
    if set(snapshot) != {"process_id", "process_start_token", "events"}:
        raise AcceptanceError("telemetry snapshot keys drift")
    if type(snapshot["process_id"]) is not int:
        raise AcceptanceError("telemetry process identity is malformed")
    token = snapshot["process_start_token"]
    if type(token) is not str or _TOKEN_RE.fullmatch(token) is None:
        raise AcceptanceError("telemetry process start token is malformed")
    events = snapshot["events"]
    if type(events) is not list or len(events) > 50:
        raise AcceptanceError("telemetry events ring is malformed")


def _one_event_ring_delta(
    before: Mapping[str, object],
    after: Mapping[str, object],
    *,
    expected_tool: str,
    expected_origin: str,
) -> dict[str, str]:
    _validate_snapshot_shape(before)
    _validate_snapshot_shape(after)
    if before["process_id"] != after["process_id"]:
        raise AcceptanceError("telemetry process identity replacement")
    if before["process_start_token"] != after["process_start_token"]:
        raise AcceptanceError("telemetry process start token replacement")
    before_events = before["events"]
    after_events = after["events"]
    assert isinstance(before_events, list)
    assert isinstance(after_events, list)
    if len(before_events) < 50:
        if (
            len(after_events) != len(before_events) + 1
            or after_events[:-1] != before_events
        ):
            raise AcceptanceError("telemetry did not append exactly one event")
    else:
        if (
            len(after_events) != 50
            or after_events[:-1] != before_events[1:]
        ):
            raise AcceptanceError(
                "telemetry did not append exactly one event with head eviction"
            )
    event = after_events[-1]
    if not isinstance(event, Mapping):
        raise AcceptanceError("telemetry event is malformed")
    if set(event) != {"tool", "disposition", "origin", "timestamp"}:
        raise AcceptanceError("telemetry event keys drift")
    if event["tool"] != expected_tool:
        raise AcceptanceError("telemetry tool drift")
    if event["origin"] != expected_origin:
        raise AcceptanceError("telemetry origin drift")
    entry = resolve_contained_identity(expected_tool)
    if entry is None or event["disposition"] != entry.disposition.value:
        raise AcceptanceError("telemetry disposition drift")
    timestamp = event["timestamp"]
    if type(timestamp) is not str or _TIMESTAMP_RE.fullmatch(timestamp) is None:
        raise AcceptanceError("telemetry timestamp drift")
    return dict(event)


def _validate_denial_result(tool: str, result: object) -> None:
    entry = resolve_contained_identity(tool)
    if entry is None or result != containment_envelope(entry):
        raise AcceptanceError(f"denial result drift for {tool}")


def _expected_stage_counts(adapter: str) -> dict[str, int]:
    if adapter not in {"direct", "progressive"}:
        raise AcceptanceError(f"unexpected transport adapter: {adapter}")
    expected = {stage: 0 for stage in STAGE_NAMES}
    expected["recording_attempt"] = 1
    expected["format_result"] = 1
    return expected


def _validate_spy_record(
    record: Mapping[str, object],
    *,
    expected_run_id: str,
    expected_index: int,
    expected_adapter: str,
    expected_tool: str,
    expected_origin: str,
) -> None:
    if set(record) != {
        "schema_version",
        "run_id",
        "process_id",
        "process_start_token",
        "self_test",
        "probe",
    }:
        raise AcceptanceError("spy record keys drift")
    if record["schema_version"] != SCHEMA_VERSION:
        raise AcceptanceError("spy schema version drift")
    if record["run_id"] != expected_run_id:
        raise AcceptanceError("spy run mismatch")
    if type(record["process_id"]) is not int:
        raise AcceptanceError("spy process identity drift")
    token = record["process_start_token"]
    if type(token) is not str or _TOKEN_RE.fullmatch(token) is None:
        raise AcceptanceError("spy process start token drift")

    self_test = record["self_test"]
    if not isinstance(self_test, Mapping) or set(self_test) != {
        "patchpoints",
        "wrapper_factory",
    }:
        raise AcceptanceError("spy self-test keys drift")
    expected_patchpoints = {
        spec.identifier: True for spec in PATCHPOINT_SPECS
    }
    if self_test["patchpoints"] != expected_patchpoints:
        raise AcceptanceError("spy patchpoint self-test drift")
    expected_factory = {
        "sync_scoped_trip": True,
        "sync_unscoped_passthrough": True,
        "async_scoped_trip": True,
        "async_unscoped_passthrough": True,
    }
    if self_test["wrapper_factory"] != expected_factory:
        raise AcceptanceError("spy wrapper factory self-test drift")

    probe = record["probe"]
    if not isinstance(probe, Mapping) or set(probe) != {
        "index",
        "adapter",
        "tool",
        "origin",
        "telemetry_before",
        "telemetry_after",
        "stages",
    }:
        raise AcceptanceError("spy probe keys drift")
    expected_fields = {
        "index": expected_index,
        "adapter": expected_adapter,
        "tool": expected_tool,
        "origin": expected_origin,
    }
    for key, expected in expected_fields.items():
        if probe[key] != expected:
            raise AcceptanceError(f"spy probe {key} drift")
    stages = probe["stages"]
    if (
        type(stages) is not dict
        or set(stages) != set(STAGE_NAMES)
        or any(type(value) is not int or value < 0 for value in stages.values())
        or stages != _expected_stage_counts(expected_adapter)
    ):
        raise AcceptanceError("spy stage counters drift")
    before = probe["telemetry_before"]
    after = probe["telemetry_after"]
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        raise AcceptanceError("spy telemetry is malformed")
    if record["process_id"] != before.get("process_id"):
        raise AcceptanceError("spy process identity mismatch")
    if record["process_start_token"] != before.get("process_start_token"):
        raise AcceptanceError("spy process token mismatch")
    _one_event_ring_delta(
        before,
        after,
        expected_tool=expected_tool,
        expected_origin=expected_origin,
    )


def _classify_call_tool_request(
    req: object,
) -> tuple[str, str, DispatchOrigin]:
    try:
        raw_name = req.params.name
    except AttributeError as exc:
        raise AcceptanceError("unexpected call-tool request shape") from exc
    if resolve_contained_identity(raw_name) is not None:
        return "direct", raw_name, DispatchOrigin.PUBLIC_MCP
    if raw_name != "rook_tools_call":
        raise AcceptanceError(
            f"unexpected call-tool request: {raw_name!r}"
        )
    raw_outer = req.params.arguments
    if type(raw_outer) is not dict:
        raise AcceptanceError(
            "unexpected call-tool request: progressive arguments must be dict"
        )
    raw_target = raw_outer.get("name")
    if resolve_contained_identity(raw_target) is None:
        raise AcceptanceError(
            f"unexpected call-tool request target: {raw_target!r}"
        )
    return "progressive", raw_target, DispatchOrigin.PROGRESSIVE_META


def _tool_record(tool: object) -> dict[str, object]:
    if isinstance(tool, Mapping):
        record = dict(tool)
    elif hasattr(tool, "model_dump"):
        record = tool.model_dump(
            by_alias=True,
            exclude_none=True,
        )
    else:
        record = {
            "name": getattr(tool, "name", None),
            "description": getattr(tool, "description", None),
            "inputSchema": getattr(tool, "inputSchema", None),
        }
    if type(record.get("name")) is not str:
        raise AcceptanceError("discovery tool name is malformed")
    if "input_schema" in record and "inputSchema" not in record:
        record["inputSchema"] = record.pop("input_schema")
    return record


def _catalog_record(tools: Iterable[object]) -> dict[str, object]:
    records = [_tool_record(tool) for tool in tools]
    return {"count": len(records), "tools": records}


def _validate_catalog(
    catalog: Mapping[str, object],
    *,
    expected_count: int,
    profile: str,
) -> None:
    if set(catalog) != {"count", "tools"}:
        raise AcceptanceError("discovery catalog keys drift")
    if catalog["count"] != expected_count:
        raise AcceptanceError(
            f"discovery count drift for {profile}: "
            f"expected={expected_count} actual={catalog['count']}"
        )
    tools = catalog["tools"]
    if type(tools) is not list or len(tools) != expected_count:
        raise AcceptanceError("discovery tool list count drift")
    names: list[str] = []
    for record in tools:
        if not isinstance(record, Mapping):
            raise AcceptanceError("discovery tool schema is malformed")
        name = record.get("name")
        if type(name) is not str:
            raise AcceptanceError("discovery tool name is malformed")
        names.append(name)
    if len(set(names)) != len(names):
        raise AcceptanceError("discovery tool names are duplicated")
    leaked = set(names).intersection(CONTAINED_TOOL_NAMES)
    if leaked:
        raise AcceptanceError(
            f"contained names leaked into discovery: {sorted(leaked)}"
        )


def _validate_discovery_contract(
    *,
    command: str,
    profile_env_present: bool,
    interactive_env_present: bool,
    catalog: Mapping[str, object],
    telemetry_before: Mapping[str, object],
    telemetry_after: Mapping[str, object],
) -> None:
    if command not in _DISCOVERY_COUNTS:
        raise AcceptanceError(f"unexpected discovery command: {command}")
    if command == "discovery-default":
        if profile_env_present:
            raise AcceptanceError(
                "default discovery profile environment must be absent"
            )
        if interactive_env_present:
            raise AcceptanceError(
                "default discovery interactive environment must be absent"
            )
    else:
        if not profile_env_present or not interactive_env_present:
            raise AcceptanceError(
                "interactive discovery requires explicit full profile and gate"
            )
    _validate_catalog(
        catalog,
        expected_count=_DISCOVERY_COUNTS[command],
        profile=command,
    )
    _validate_snapshot_shape(telemetry_before)
    _validate_snapshot_shape(telemetry_after)
    if telemetry_before != telemetry_after:
        raise AcceptanceError("discovery containment telemetry changed")


def _litellm_schema(tool: object) -> dict[str, object]:
    record = _tool_record(tool)
    return {
        "type": "function",
        "function": {
            "name": record["name"],
            "description": record.get("description") or "",
            "parameters": record.get("inputSchema")
            or {"type": "object", "properties": {}},
        },
    }


class _AllSchemasRegistry:
    def __init__(self, schemas: list[dict[str, object]]) -> None:
        self._schemas = schemas

    def get_active_schemas(self) -> list[dict[str, object]]:
        return list(self._schemas)

    def is_meta_tool(self, _name: str) -> bool:
        return False

    def get_group_names(self) -> list[str]:
        return []

    def get_active_count(self) -> int:
        return len(self._schemas)


def _projection_names(schemas: Iterable[object]) -> list[str]:
    names: list[str] = []
    for schema in schemas:
        if not isinstance(schema, Mapping):
            raise AcceptanceError("model projection schema is malformed")
        function = schema.get("function")
        if not isinstance(function, Mapping):
            raise AcceptanceError("model projection function is malformed")
        name = function.get("name")
        if type(name) is not str:
            raise AcceptanceError("model projection name is malformed")
        names.append(name)
    return sorted(names)


def _collect_model_projection_evidence_from_tools(
    tools: Iterable[object],
) -> dict[str, object]:
    from .agent.base_agent import RookAgent
    from .agent.chat.chat_runner import ChatRunner
    from .agent.config import AgentConfig

    schemas = [_litellm_schema(tool) for tool in tools]

    async def inert_executor(_name: str, _params: dict) -> dict[str, object]:
        raise AcceptanceError("model projection executor must not run")

    agent = RookAgent(
        config=AgentConfig(
            knowledge_injection=False,
            parameter_correction=False,
            observation_recording=False,
            tool_surface_adaptation=False,
        ),
        tool_executor=inert_executor,
        tool_schemas=schemas,
    )
    chat = ChatRunner(
        tool_executor=inert_executor,
        registry=_AllSchemasRegistry(schemas),
    )
    agent_names = _projection_names(agent._get_tool_schemas())
    chat_names = _projection_names(chat._active_schemas())
    for consumer, names in (
        ("rook_agent", agent_names),
        ("rook_chat", chat_names),
    ):
        leaked = set(names).intersection(CONTAINED_TOOL_NAMES)
        if leaked:
            raise AcceptanceError(
                f"contained names leaked into {consumer}: {sorted(leaked)}"
            )
    return {
        "rook_agent": {"count": len(agent_names), "names": agent_names},
        "rook_chat": {"count": len(chat_names), "names": chat_names},
    }


def _collect_model_projection_evidence() -> dict[str, object]:
    from . import server

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        tools = asyncio.run(server.list_tools())
    else:
        raise AcceptanceError(
            "synchronous model projection collection inside active event loop"
        )
    return _collect_model_projection_evidence_from_tools(tools)


def _parse_wire_denial(tool: str, result: object) -> dict[str, object]:
    contents = getattr(result, "content", None)
    if type(contents) is not list or len(contents) != 1:
        raise AcceptanceError("transport result must contain one content item")
    content = contents[0]
    if getattr(content, "type", None) != "text":
        raise AcceptanceError("transport result must contain TextContent")
    text = getattr(content, "text", None)
    if type(text) is not str or not text.startswith("Error: "):
        raise AcceptanceError("transport denial wire payload is malformed")
    try:
        payload = json.loads(text[len("Error: "):])
    except json.JSONDecodeError as exc:
        raise AcceptanceError("transport denial payload is not JSON") from exc
    envelope = {"success": False, "data": payload}
    _validate_denial_result(tool, envelope)
    return envelope


def _validate_transport_artifact(
    artifact: Mapping[str, object],
    *,
    expected_profile: str,
    expected_count: int,
    expected_install_root: Path,
    expected_data_root: Path,
    expected_dspy_cache: Path,
    expected_chirp_home: Path | None = None,
    forbidden_source_roots: Iterable[Path] = (),
    allowed_command_roots: Iterable[Path] = (),
) -> None:
    expected_keys = {
        "schema_version",
        "command",
        "profile",
        "run_id",
        "process",
        "child_environment",
        "catalog",
        "model_projections",
        "probes",
        "child_process_id",
        "child_process_start_token",
        "final_spy_path",
        "final_spy_sha256",
        "final_spy",
    }
    if set(artifact) != expected_keys:
        raise AcceptanceError("transport artifact keys drift")
    if (
        artifact["schema_version"] != SCHEMA_VERSION
        or artifact["command"] != "transport-profile"
        or artifact["profile"] != expected_profile
    ):
        raise AcceptanceError("transport artifact identity drift")
    run_id = artifact["run_id"]
    if type(run_id) is not str or _RUN_ID_RE.fullmatch(run_id) is None:
        raise AcceptanceError("transport artifact run id drift")
    process = artifact["process"]
    if not isinstance(process, Mapping):
        raise AcceptanceError("transport process evidence is malformed")
    _validate_process_evidence(
        process,
        expected_install_root=expected_install_root,
        expected_data_root=expected_data_root,
        expected_dspy_cache=expected_dspy_cache,
        expected_chirp_home=expected_chirp_home,
        expected_profile=expected_profile,
        forbidden_source_roots=forbidden_source_roots,
        allowed_command_roots=allowed_command_roots,
        required_rook_modules=(
            "rook",
            "rook.containment_acceptance",
            "rook.server",
        ),
    )
    _validate_relevant_environment(
        artifact["child_environment"],
        install_root=expected_install_root,
        data_root=expected_data_root,
        dspy_cache=expected_dspy_cache,
        chirp_home=expected_chirp_home,
        profile=expected_profile,
        interactive=False,
    )
    catalog = artifact["catalog"]
    if not isinstance(catalog, Mapping):
        raise AcceptanceError("transport catalog is malformed")
    _validate_catalog(
        catalog,
        expected_count=expected_count,
        profile=expected_profile,
    )
    projections = artifact["model_projections"]
    if not isinstance(projections, Mapping) or set(projections) != {
        "rook_agent",
        "rook_chat",
    }:
        raise AcceptanceError("transport model projections are malformed")
    for value in projections.values():
        if not isinstance(value, Mapping) or set(value) != {"count", "names"}:
            raise AcceptanceError("transport model projection keys drift")
        if value["count"] != len(value["names"]):
            raise AcceptanceError("transport model projection count drift")
        if set(value["names"]).intersection(CONTAINED_TOOL_NAMES):
            raise AcceptanceError(
                "contained name leaked into transport model projection"
            )

    probes = artifact["probes"]
    if type(probes) is not list or len(probes) != 12:
        raise AcceptanceError("transport probe count drift")
    expected_order = [
        *[("direct", tool) for tool in CONTAINED_TOOL_NAMES],
        *[("progressive", tool) for tool in CONTAINED_TOOL_NAMES],
    ]
    child_pid = artifact["child_process_id"]
    child_token = artifact["child_process_start_token"]
    if type(child_pid) is not int:
        raise AcceptanceError("transport child process identity drift")
    if type(child_token) is not str or _TOKEN_RE.fullmatch(child_token) is None:
        raise AcceptanceError("transport child start token drift")
    for index, (probe, expected) in enumerate(zip(probes, expected_order)):
        if not isinstance(probe, Mapping) or set(probe) != {
            "index",
            "adapter",
            "tool",
            "origin",
            "result",
            "transport",
            "spy",
        }:
            raise AcceptanceError("transport probe keys drift")
        adapter, tool = expected
        origin = (
            DispatchOrigin.PUBLIC_MCP.value
            if adapter == "direct"
            else DispatchOrigin.PROGRESSIVE_META.value
        )
        if (
            probe["index"] != index
            or probe["adapter"] != adapter
            or probe["tool"] != tool
            or probe["origin"] != origin
        ):
            raise AcceptanceError("transport probe order drift")
        _validate_denial_result(tool, probe["result"])
        if probe["transport"] != {
            "content_count": 1,
            "content_types": ["text"],
            "is_error": False,
        }:
            raise AcceptanceError("transport content contract drift")
        spy = probe["spy"]
        if not isinstance(spy, Mapping):
            raise AcceptanceError("transport spy record is malformed")
        _validate_spy_record(
            spy,
            expected_run_id=run_id,
            expected_index=index,
            expected_adapter=adapter,
            expected_tool=tool,
            expected_origin=origin,
        )
        if (
            spy["process_id"] != child_pid
            or spy["process_start_token"] != child_token
        ):
            raise AcceptanceError("transport child identity changed")

    final_spy = artifact["final_spy"]
    if final_spy != probes[-1]["spy"]:
        raise AcceptanceError("transport final spy mismatch")
    final_path = Path(str(artifact["final_spy_path"]))
    if not final_path.is_absolute() or not final_path.is_file():
        raise AcceptanceError("transport final spy artifact is missing")
    if artifact["final_spy_sha256"] != _sha256_file(final_path):
        raise AcceptanceError("transport final spy SHA-256 drift")
    if json.loads(final_path.read_text(encoding="utf-8")) != final_spy:
        raise AcceptanceError("transport final spy contents drift")


def _validate_discovery_artifact(
    artifact: Mapping[str, object],
    *,
    expected_command: str,
    expected_count: int,
    expected_install_root: Path,
    expected_data_root: Path,
    expected_dspy_cache: Path,
    expected_chirp_home: Path | None = None,
    forbidden_source_roots: Iterable[Path] = (),
    allowed_command_roots: Iterable[Path] = (),
) -> None:
    if set(artifact) != {
        "schema_version",
        "command",
        "process",
        "profile_env_present",
        "interactive_env_present",
        "catalog",
        "telemetry_before",
        "telemetry_after",
        "model_projections",
    }:
        raise AcceptanceError("discovery artifact keys drift")
    if (
        artifact["schema_version"] != SCHEMA_VERSION
        or artifact["command"] != expected_command
    ):
        raise AcceptanceError("discovery artifact identity drift")
    process = artifact["process"]
    if not isinstance(process, Mapping):
        raise AcceptanceError("discovery process evidence is malformed")
    _validate_process_evidence(
        process,
        expected_install_root=expected_install_root,
        expected_data_root=expected_data_root,
        expected_dspy_cache=expected_dspy_cache,
        expected_chirp_home=expected_chirp_home,
        expected_profile=(
            "full" if expected_command == "discovery-interactive" else None
        ),
        expected_interactive=(
            expected_command == "discovery-interactive"
        ),
        forbidden_source_roots=forbidden_source_roots,
        allowed_command_roots=allowed_command_roots,
        required_rook_modules=(
            "rook",
            "rook.containment_acceptance",
            "rook.server",
        ),
    )
    catalog = artifact["catalog"]
    before = artifact["telemetry_before"]
    after = artifact["telemetry_after"]
    if (
        not isinstance(catalog, Mapping)
        or not isinstance(before, Mapping)
        or not isinstance(after, Mapping)
    ):
        raise AcceptanceError("discovery artifact payload is malformed")
    _validate_discovery_contract(
        command=expected_command,
        profile_env_present=artifact["profile_env_present"] is True,
        interactive_env_present=(
            artifact["interactive_env_present"] is True
        ),
        catalog=catalog,
        telemetry_before=before,
        telemetry_after=after,
    )
    if catalog["count"] != expected_count:
        raise AcceptanceError("discovery artifact count drift")
    projections = artifact["model_projections"]
    if not isinstance(projections, Mapping):
        raise AcceptanceError("discovery model projections are malformed")
    for value in projections.values():
        if set(value["names"]).intersection(CONTAINED_TOOL_NAMES):
            raise AcceptanceError(
                "contained name leaked into discovery model projection"
            )


def _validate_internal_artifact(
    artifact: Mapping[str, object],
    *,
    expected_install_root: Path,
    expected_data_root: Path,
    expected_dspy_cache: Path,
    expected_chirp_home: Path | None = None,
    forbidden_source_roots: Iterable[Path] = (),
    allowed_command_roots: Iterable[Path] = (),
) -> None:
    if set(artifact) != {
        "schema_version",
        "command",
        "process",
        "expected_pairs",
        "probes",
        "model_projections",
    }:
        raise AcceptanceError("internal matrix artifact keys drift")
    if (
        artifact["schema_version"] != SCHEMA_VERSION
        or artifact["command"] != "internal-matrix"
    ):
        raise AcceptanceError("internal matrix artifact identity drift")
    process = artifact["process"]
    if not isinstance(process, Mapping):
        raise AcceptanceError("internal matrix process evidence malformed")
    _validate_process_evidence(
        process,
        expected_install_root=expected_install_root,
        expected_data_root=expected_data_root,
        expected_dspy_cache=expected_dspy_cache,
        expected_chirp_home=expected_chirp_home,
        forbidden_source_roots=forbidden_source_roots,
        allowed_command_roots=allowed_command_roots,
        required_rook_modules=(
            "rook",
            "rook.containment_acceptance",
            "rook.server",
        ),
    )
    expected_specs = _expected_internal_pairs()
    expected_pairs = [
        {
            "seam": item.seam,
            "tool": item.tool,
            "origin": item.origin,
            "adapter": item.adapter,
        }
        for item in expected_specs
    ]
    if artifact["expected_pairs"] != expected_pairs:
        raise AcceptanceError("internal seam expected-pair set drift")
    probes = artifact["probes"]
    if type(probes) is not list or len(probes) != 164:
        raise AcceptanceError("internal seam probe count drift")
    seen: list[InternalProbeSpec] = []
    for index, (probe, expected) in enumerate(zip(probes, expected_specs)):
        if not isinstance(probe, Mapping) or set(probe) != {
            "index",
            "seam",
            "adapter",
            "tool",
            "origin",
            "result",
            "telemetry_before",
            "telemetry_after",
            "stages",
            "primary_model_calls",
        }:
            raise AcceptanceError("internal seam probe keys drift")
        if (
            probe["index"] != index
            or probe["seam"] != expected.seam
            or probe["adapter"] != expected.adapter
            or probe["tool"] != expected.tool
            or probe["origin"] != expected.origin
        ):
            raise AcceptanceError("internal seam probe order drift")
        _validate_denial_result(expected.tool, probe["result"])
        before = probe["telemetry_before"]
        after = probe["telemetry_after"]
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            raise AcceptanceError("internal seam telemetry malformed")
        _one_event_ring_delta(
            before,
            after,
            expected_tool=expected.tool,
            expected_origin=expected.origin,
        )
        stages = probe["stages"]
        expected_stages = {stage: 0 for stage in STAGE_NAMES}
        expected_stages["recording_attempt"] = 1
        if stages != expected_stages:
            raise AcceptanceError("internal seam stage drift")
        expected_model_calls = (
            2
            if expected.seam
            in {"RookAgent._run_loop", "ChatRunner.run_turn"}
            else 0
        )
        if probe["primary_model_calls"] != expected_model_calls:
            raise AcceptanceError("internal primary model call drift")
        seen.append(expected)
    _validate_internal_pair_set(seen)
    projections = artifact["model_projections"]
    if not isinstance(projections, Mapping):
        raise AcceptanceError("internal model projections malformed")
    for value in projections.values():
        if set(value["names"]).intersection(CONTAINED_TOOL_NAMES):
            raise AcceptanceError(
                "contained name leaked into internal model projection"
            )


def _code_owned_chirp_home(install_root: Path) -> Path | None:
    candidate = install_root / "chirp"
    return candidate.resolve() if candidate.is_dir() else None


def _code_owned_dspy_cache(data_root: Path) -> Path:
    cache = (data_root / "dspy-cache").resolve()
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _validate_current_installed_startup_environment(
    *,
    expected_profile: str | None = None,
    expected_interactive: bool = False,
):
    runtime = resolve_runtime_paths()
    if runtime.mode != "release":
        raise AcceptanceError(
            f"acceptance commands require release mode, got {runtime.mode!r}"
        )
    if _path_looks_like_development_source(runtime.install_root):
        raise AcceptanceError(
            f"startup install root is source-like: {runtime.install_root}"
        )
    _validate_relevant_environment(
        _relevant_environment(),
        install_root=runtime.install_root,
        data_root=runtime.data_root,
        dspy_cache=(runtime.data_root / "dspy-cache").resolve(),
        chirp_home=_code_owned_chirp_home(runtime.install_root),
        profile=expected_profile,
        interactive=expected_interactive,
    )
    return runtime


def _validate_current_installed_process(
    *,
    required_rook_modules: Iterable[str],
    allowed_command_roots: Iterable[Path] = (),
    expected_profile: str | None = None,
    expected_interactive: bool = False,
) -> dict[str, object]:
    runtime = resolve_runtime_paths()
    if runtime.mode != "release":
        raise AcceptanceError(
            f"acceptance commands require release mode, got {runtime.mode!r}"
        )
    evidence = _collect_process_evidence()
    _validate_process_evidence(
        evidence,
        expected_install_root=runtime.install_root,
        expected_data_root=runtime.data_root,
        expected_dspy_cache=(runtime.data_root / "dspy-cache").resolve(),
        expected_chirp_home=_code_owned_chirp_home(runtime.install_root),
        expected_profile=expected_profile,
        expected_interactive=expected_interactive,
        allowed_command_roots=(
            runtime.install_root,
            runtime.runtime_root,
            *allowed_command_roots,
        ),
        required_rook_modules=required_rook_modules,
    )
    if evidence["process_id"] != os.getpid():
        raise AcceptanceError("current process identity drift")
    return evidence


async def _refresh_installed_catalog(server: object) -> None:
    from .agent.tool_registry import refresh_catalog_at_startup

    result = await refresh_catalog_at_startup(server._all_live_tools)
    if result.status not in {"fresh", "degraded"}:
        raise AcceptanceError(
            f"installed catalog startup refresh failed: {result.status}"
        )


async def _transport_child(
    *,
    profile: str,
    run_id: str,
    spy_path: Path,
) -> None:
    if profile not in PROFILE_VALUES:
        raise AcceptanceError(f"invalid private transport profile: {profile}")
    if _RUN_ID_RE.fullmatch(run_id) is None:
        raise AcceptanceError("private transport run id is malformed")
    spy_path = Path(spy_path)
    if not spy_path.is_absolute() or spy_path.suffix.casefold() != ".json":
        raise AcceptanceError("private transport spy path is malformed")
    if spy_path.exists():
        raise AcceptanceError("private transport spy path must be fresh")
    _validate_current_installed_startup_environment(
        expected_profile=profile,
    )

    from mcp import types as mcp_types
    from mcp.server.stdio import stdio_server

    from . import server
    from .learning.metrics_store import get_metrics_store

    process_evidence = _validate_current_installed_process(
        required_rook_modules=(
            "rook",
            "rook.containment_acceptance",
            "rook.server",
            "rook.tool_lifecycle_runtime",
        ),
        allowed_command_roots=(spy_path.parent,),
        expected_profile=profile,
    )
    await _refresh_installed_catalog(server)
    retained_handler = server.mcp.request_handlers[mcp_types.CallToolRequest]
    probe_index = 0

    async with _installed_spy_scope() as installed:
        async def acceptance_handler(req):
            nonlocal probe_index
            adapter, tool, origin = _classify_call_tool_request(req)
            if probe_index >= 12:
                raise AcceptanceError("unexpected extra call-tool request")
            expected_adapter, expected_tool = (
                [
                    *[
                        ("direct", name)
                        for name in CONTAINED_TOOL_NAMES
                    ],
                    *[
                        ("progressive", name)
                        for name in CONTAINED_TOOL_NAMES
                    ],
                ][probe_index]
            )
            if adapter != expected_adapter or tool != expected_tool:
                raise AcceptanceError(
                    "unexpected call-tool request ordering"
                )

            installed.reset()
            store = get_metrics_store()
            before = store.get_containment_denials_snapshot()
            try:
                with installed.phase(adapter):
                    result = await retained_handler(req)
            finally:
                after = store.get_containment_denials_snapshot()
            stages = installed.counters
            if stages != _expected_stage_counts(adapter):
                raise AcceptanceError(
                    f"installed stage counters drift for {adapter}: {stages}"
                )
            _one_event_ring_delta(
                before,
                after,
                expected_tool=tool,
                expected_origin=origin.value,
            )
            record = {
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "process_id": before["process_id"],
                "process_start_token": before["process_start_token"],
                "self_test": installed.self_test,
                "probe": {
                    "index": probe_index,
                    "adapter": adapter,
                    "tool": tool,
                    "origin": origin.value,
                    "telemetry_before": before,
                    "telemetry_after": after,
                    "stages": stages,
                },
            }
            _validate_spy_record(
                record,
                expected_run_id=run_id,
                expected_index=probe_index,
                expected_adapter=adapter,
                expected_tool=tool,
                expected_origin=origin.value,
            )
            _atomic_write_json(spy_path, record)
            probe_index += 1
            return result

        server.mcp.request_handlers[
            mcp_types.CallToolRequest
        ] = acceptance_handler
        try:
            async with stdio_server() as (read_stream, write_stream):
                await server.mcp.run(
                    read_stream,
                    write_stream,
                    server.mcp.create_initialization_options(),
                )
        finally:
            server.mcp.request_handlers[
                mcp_types.CallToolRequest
            ] = retained_handler

    if probe_index != 12:
        raise AcceptanceError(
            f"private transport ended after {probe_index} probes"
        )
    final_process_evidence = _validate_current_installed_process(
        required_rook_modules=(
            "rook",
            "rook.containment_acceptance",
            "rook.server",
            "rook.tool_lifecycle_runtime",
        ),
        allowed_command_roots=(spy_path.parent,),
        expected_profile=profile,
    )
    if (
        final_process_evidence["process_id"]
        != process_evidence["process_id"]
        or final_process_evidence["process_start_token"]
        != process_evidence["process_start_token"]
    ):
        raise AcceptanceError("private transport process identity drift")


async def _transport_profile(
    *,
    profile: str,
    artifact_dir: Path,
) -> Path:
    if profile not in PROFILE_VALUES:
        raise AcceptanceError(f"invalid transport profile: {profile}")
    runtime = _validate_current_installed_startup_environment(
        expected_profile=profile,
    )

    from . import server

    _validate_current_installed_process(
        required_rook_modules=(
            "rook",
            "rook.containment_acceptance",
            "rook.server",
        ),
        expected_profile=profile,
    )
    artifact_dir = Path(artifact_dir).expanduser().resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    data_root = runtime.data_root.resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    spy_path = artifact_dir / f"transport-{profile}-{run_id}-spy.json"
    if spy_path.exists():
        raise AcceptanceError("transport spy path collision")

    dspy_cache = _code_owned_dspy_cache(data_root)
    chirp_home = _code_owned_chirp_home(runtime.install_root)
    child_environment = _sanitized_child_environment(
        os.environ,
        install_root=runtime.install_root,
        data_root=data_root,
        dspy_cache=dspy_cache,
        chirp_home=chirp_home,
        profile=profile,
    )
    temp_root = Path(
        child_environment.get("TEMP")
        or child_environment.get("TMP")
        or tempfile.gettempdir()
    ).resolve()
    child_cwd = temp_root / "rook-containment" / run_id / profile
    child_cwd.mkdir(parents=True, exist_ok=False)

    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    server_parameters = StdioServerParameters(
        command=str(Path(sys.executable).resolve()),
        args=[
            "-m",
            "rook.containment_acceptance",
            "_transport-child",
            "--profile",
            profile,
            "--run-id",
            run_id,
            "--spy-path",
            str(spy_path),
        ],
        env=child_environment,
        cwd=str(child_cwd),
        encoding_error_handler="replace",
    )

    probes: list[dict[str, object]] = []
    child_pid: int | None = None
    child_token: str | None = None
    stderr_text = ""
    with tempfile.TemporaryFile(
        mode="w+",
        encoding="utf-8",
        errors="replace",
    ) as errlog:
        async with stdio_client(
            server_parameters,
            errlog=errlog,
        ) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                catalog = _catalog_record(tools_result.tools)
                _validate_catalog(
                    catalog,
                    expected_count=_PROFILE_COUNTS[profile],
                    profile=profile,
                )

                ordered = [
                    *[
                        ("direct", tool)
                        for tool in CONTAINED_TOOL_NAMES
                    ],
                    *[
                        ("progressive", tool)
                        for tool in CONTAINED_TOOL_NAMES
                    ],
                ]
                for index, (adapter, tool) in enumerate(ordered):
                    if adapter == "direct":
                        result = await session.call_tool(tool, {})
                        origin = DispatchOrigin.PUBLIC_MCP.value
                    else:
                        result = await session.call_tool(
                            "rook_tools_call",
                            {"name": tool, "arguments": {}},
                        )
                        origin = DispatchOrigin.PROGRESSIVE_META.value
                    denial = _parse_wire_denial(tool, result)
                    if not spy_path.is_file():
                        raise AcceptanceError(
                            "private transport spy artifact is missing"
                        )
                    try:
                        spy = json.loads(
                            spy_path.read_text(encoding="utf-8")
                        )
                    except (OSError, json.JSONDecodeError) as exc:
                        raise AcceptanceError(
                            "private transport spy artifact is malformed"
                        ) from exc
                    _validate_spy_record(
                        spy,
                        expected_run_id=run_id,
                        expected_index=index,
                        expected_adapter=adapter,
                        expected_tool=tool,
                        expected_origin=origin,
                    )
                    if child_pid is None:
                        child_pid = spy["process_id"]
                        child_token = spy["process_start_token"]
                    elif (
                        child_pid != spy["process_id"]
                        or child_token != spy["process_start_token"]
                    ):
                        raise AcceptanceError(
                            "private transport child identity changed"
                        )
                    contents = result.content
                    probes.append(
                        {
                            "index": index,
                            "adapter": adapter,
                            "tool": tool,
                            "origin": origin,
                            "result": denial,
                            "transport": {
                                "content_count": len(contents),
                                "content_types": [
                                    getattr(content, "type", None)
                                    for content in contents
                                ],
                                "is_error": bool(result.isError),
                            },
                            "spy": spy,
                        }
                    )
        errlog.seek(0)
        stderr_text = errlog.read()

    if child_pid is None or child_token is None:
        raise AcceptanceError("private transport emitted no probe evidence")
    if stderr_text and "Traceback (most recent call last)" in stderr_text:
        raise AcceptanceError("private transport child emitted a traceback")
    final_spy = json.loads(spy_path.read_text(encoding="utf-8"))

    parent_tools = await server.list_tools()
    projections = _collect_model_projection_evidence_from_tools(parent_tools)
    process = _validate_current_installed_process(
        required_rook_modules=(
            "rook",
            "rook.containment_acceptance",
            "rook.server",
        ),
        allowed_command_roots=(artifact_dir, child_cwd),
        expected_profile=profile,
    )
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "command": "transport-profile",
        "profile": profile,
        "run_id": run_id,
        "process": process,
        "child_environment": _relevant_environment(child_environment),
        "catalog": catalog,
        "model_projections": projections,
        "probes": probes,
        "child_process_id": child_pid,
        "child_process_start_token": child_token,
        "final_spy_path": str(spy_path),
        "final_spy_sha256": _sha256_file(spy_path),
        "final_spy": final_spy,
    }
    output_path = artifact_dir / f"transport-{profile}.json"
    _atomic_write_json(output_path, artifact)
    _validate_transport_artifact(
        artifact,
        expected_profile=profile,
        expected_count=_PROFILE_COUNTS[profile],
        expected_install_root=runtime.install_root,
        expected_data_root=runtime.data_root,
        expected_dspy_cache=dspy_cache,
        expected_chirp_home=chirp_home,
        allowed_command_roots=(
            runtime.runtime_root,
            artifact_dir,
            child_cwd,
        ),
    )
    return output_path


async def _discovery_command(
    *,
    command: str,
    artifact_dir: Path,
) -> Path:
    if command not in _DISCOVERY_COUNTS:
        raise AcceptanceError(f"invalid discovery command: {command}")
    interactive = command == "discovery-interactive"
    profile = "full" if interactive else None
    runtime = _validate_current_installed_startup_environment(
        expected_profile=profile,
        expected_interactive=interactive,
    )

    from . import server
    from .learning.metrics_store import get_metrics_store

    _validate_current_installed_process(
        required_rook_modules=(
            "rook",
            "rook.containment_acceptance",
            "rook.server",
        ),
        expected_profile=profile,
        expected_interactive=interactive,
    )
    await _refresh_installed_catalog(server)
    store = get_metrics_store()
    before = store.get_containment_denials_snapshot()
    tools = await server.list_tools()
    after = store.get_containment_denials_snapshot()
    catalog = _catalog_record(tools)
    profile_present = "ROOK_MCP_TOOL_PROFILE" in os.environ
    interactive_present = (
        "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING" in os.environ
    )
    _validate_discovery_contract(
        command=command,
        profile_env_present=profile_present,
        interactive_env_present=interactive_present,
        catalog=catalog,
        telemetry_before=before,
        telemetry_after=after,
    )
    projections = _collect_model_projection_evidence_from_tools(tools)
    artifact_dir = Path(artifact_dir).expanduser().resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    process = _validate_current_installed_process(
        required_rook_modules=(
            "rook",
            "rook.containment_acceptance",
            "rook.server",
        ),
        allowed_command_roots=(artifact_dir,),
        expected_profile=profile,
        expected_interactive=interactive,
    )
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "process": process,
        "profile_env_present": profile_present,
        "interactive_env_present": interactive_present,
        "catalog": catalog,
        "telemetry_before": before,
        "telemetry_after": after,
        "model_projections": projections,
    }
    output_path = artifact_dir / f"{command}.json"
    _atomic_write_json(output_path, artifact)
    _validate_discovery_artifact(
        artifact,
        expected_command=command,
        expected_count=_DISCOVERY_COUNTS[command],
        expected_install_root=runtime.install_root,
        expected_data_root=runtime.data_root,
        expected_dspy_cache=(runtime.data_root / "dspy-cache").resolve(),
        expected_chirp_home=_code_owned_chirp_home(runtime.install_root),
        allowed_command_roots=(
            runtime.runtime_root,
            artifact_dir,
        ),
    )
    return output_path


class _InternalPoison:
    def __init__(self, label: str) -> None:
        self._label = label

    def _fail(self, action: str) -> None:
        raise AcceptanceError(
            f"internal probe reached forbidden {self._label} via {action}"
        )

    def __getattr__(self, name: str):
        self._fail(f"attribute {name}")

    def __call__(self, *args, **kwargs):
        self._fail("call")

    def __bool__(self) -> bool:
        self._fail("truth test")

    def __iter__(self):
        self._fail("iteration")

    def __len__(self) -> int:
        self._fail("length")

    def __getitem__(self, key: object):
        self._fail(f"item {key!r}")


class _InternalPoisonMapping(Mapping[str, object]):
    def __init__(self, label: str = "parameters") -> None:
        self._label = label

    def _fail(self, action: str):
        raise AcceptanceError(
            f"internal probe reached forbidden {self._label} via {action}"
        )

    def __getitem__(self, key: str) -> object:
        return self._fail(f"item {key!r}")

    def __iter__(self):
        return self._fail("iteration")

    def __len__(self) -> int:
        return self._fail("length")

    def __bool__(self) -> bool:
        return self._fail("truth test")

    def get(self, key: str, default: object = None) -> object:
        return self._fail(f"get {key!r}")

    def items(self):
        return self._fail("items")

    def keys(self):
        return self._fail("keys")

    def values(self):
        return self._fail("values")

    def copy(self):
        return self._fail("copy")

    def __copy__(self):
        return self._fail("shallow copy")

    def __deepcopy__(self, _memo):
        return self._fail("deep copy")


class _InternalToolOnly:
    def __init__(self, tool: str, label: str) -> None:
        self._tool = tool
        self._label = label

    @property
    def tool(self) -> str:
        return self._tool

    def __getattr__(self, name: str):
        raise AcceptanceError(
            f"internal probe read {self._label}.{name} after tool identity"
        )


def _extract_internal_denial(tool: str, result: object) -> dict[str, object]:
    candidate: object = result
    if not isinstance(candidate, Mapping):
        for attribute in ("containment_denial", "response"):
            value = getattr(candidate, attribute, None)
            if value is not None:
                candidate = value
                break
    if not isinstance(candidate, Mapping):
        raise AcceptanceError(
            f"internal probe returned no denial envelope for {tool}"
        )
    denial = dict(candidate)
    _validate_denial_result(tool, denial)
    return denial


def _require_causal_denial_history(
    history: object,
    *,
    tool: str,
    call_id: str,
    adapter: Literal["rook_agent", "rook_chat"],
) -> None:
    if adapter not in {"rook_agent", "rook_chat"}:
        raise AcceptanceError(f"unsupported causal history adapter: {adapter}")
    entry = resolve_contained_identity(tool)
    if entry is None:
        raise AcceptanceError(f"causal history tool is not contained: {tool}")
    expected = {
        "role": "tool",
        "tool_call_id": call_id,
        "content": json.dumps(
            containment_envelope(entry),
            separators=(",", ":"),
        ),
    }
    if type(history) is not list or sum(
        type(message) is dict and message == expected
        for message in history
    ) != 1:
        raise AcceptanceError(
            f"{adapter} primary continuation lacks exact causal denial history"
        )


def _internal_agent_response(
    *,
    tool: str | None = None,
    call_id: str = "",
    content: str | None = None,
) -> SimpleNamespace:
    tool_calls: list[SimpleNamespace] = []
    if tool is not None:
        tool_calls.append(
            SimpleNamespace(
                id=call_id,
                type="function",
                function=SimpleNamespace(
                    name=tool,
                    arguments='{"acceptance_private":"must_not_decode"}',
                ),
            )
        )
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    role="assistant",
                    content=content,
                    tool_calls=tool_calls,
                )
            )
        ],
        usage=None,
    )


def _internal_chat_tool_stream(tool: str, call_id: str):
    async def stream():
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id=call_id,
                                function=SimpleNamespace(
                                    name=tool,
                                    arguments=(
                                        '{"acceptance_private":'
                                        '"must_not_decode"}'
                                    ),
                                ),
                            )
                        ],
                    )
                )
            ],
            usage=None,
        )
        yield SimpleNamespace(
            choices=[],
            usage=SimpleNamespace(
                prompt_tokens=0,
                completion_tokens=0,
            ),
        )

    return stream()


def _internal_chat_text_stream():
    async def stream():
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content="continued after containment",
                        tool_calls=None,
                    )
                )
            ],
            usage=None,
        )
        yield SimpleNamespace(
            choices=[],
            usage=SimpleNamespace(
                prompt_tokens=0,
                completion_tokens=0,
            ),
        )

    return stream()


def _internal_agent_config():
    from .agent.config import AgentConfig

    return AgentConfig(
        max_turns=3,
        max_tool_calls_per_turn=2,
        knowledge_injection=False,
        parameter_correction=False,
        observation_recording=False,
        tool_surface_adaptation=False,
    )


@contextlib.contextmanager
def _prepare_internal_probe(
    spec: InternalProbeSpec,
    *,
    loop: asyncio.AbstractEventLoop,
    server: object,
) -> Iterator[_PreparedInternalProbe]:
    seam = spec.seam
    tool = spec.tool
    poison = _InternalPoisonMapping()
    no_model_calls = lambda: 0

    async def inert_executor(_name: str, _params: object):
        raise AcceptanceError("internal probe reached its inert executor")

    with contextlib.ExitStack() as stack:
        if seam == "server._call_tool_dispatch":
            async def invoke():
                return _extract_internal_denial(
                    tool,
                    await server._call_tool_dispatch(tool, poison),
                )

            yield _PreparedInternalProbe(invoke, True, no_model_calls)
            return

        if seam == "server._mcp_tool_executor":
            async def invoke():
                return _extract_internal_denial(
                    tool,
                    await server._mcp_tool_executor(tool, poison),
                )

            yield _PreparedInternalProbe(invoke, True, no_model_calls)
            return

        if seam.startswith("ToolDispatcher."):
            from .agent.tool_dispatcher import ToolDispatcher

            dispatcher = ToolDispatcher()
            method_name = seam.split(".", 1)[1]

            async def invoke():
                method = getattr(dispatcher, method_name)
                if method_name == "dispatch":
                    result = await method(tool, poison)
                else:
                    result = await method(tool, poison, None)
                return _extract_internal_denial(tool, result)

            yield _PreparedInternalProbe(invoke, True, no_model_calls)
            return

        if seam in {
            "RookAgent._execute_tool",
            "RookAgent._execute_local_tool",
        }:
            from .agent.base_agent import RookAgent

            agent = RookAgent(
                config=_internal_agent_config(),
                tool_executor=inert_executor,
            )
            method_name = seam.split(".", 1)[1]

            async def invoke():
                result = await getattr(agent, method_name)(tool, poison)
                return _extract_internal_denial(tool, result)

            yield _PreparedInternalProbe(invoke, True, no_model_calls)
            return

        if seam == "RookAgent._run_loop":
            from .agent.base_agent import RookAgent

            agent = RookAgent(
                config=_internal_agent_config(),
                tool_executor=inert_executor,
            )
            agent.messages.append(
                {"role": "user", "content": "exercise installed containment"}
            )
            call_id = f"acceptance-agent-{tool}"
            calls = {"count": 0}
            causal_history_validated = {"value": False}

            async def primary_model(context):
                calls["count"] += 1
                if calls["count"] == 1:
                    return _internal_agent_response(
                        tool=tool,
                        call_id=call_id,
                    )
                if calls["count"] == 2:
                    _require_causal_denial_history(
                        context,
                        tool=tool,
                        call_id=call_id,
                        adapter="rook_agent",
                    )
                    causal_history_validated["value"] = True
                    return _internal_agent_response(
                        content="continued after containment"
                    )
                raise AcceptanceError(
                    "RookAgent primary model exceeded two calls"
                )

            agent._call_model = primary_model
            agent._track_usage = lambda _response: None

            async def invoke():
                await agent._run_loop()
                if calls["count"] != 2:
                    raise AcceptanceError(
                        "RookAgent primary model call count drift"
                    )
                if not causal_history_validated["value"]:
                    raise AcceptanceError(
                        "RookAgent causal denial history was not validated"
                    )
                messages = [
                    message
                    for message in agent.messages
                    if message.get("role") == "tool"
                    and message.get("tool_call_id") == call_id
                ]
                if len(messages) != 1:
                    raise AcceptanceError(
                        "RookAgent containment result message drift"
                    )
                try:
                    result = json.loads(messages[0]["content"])
                except (KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise AcceptanceError(
                        "RookAgent containment result is malformed"
                    ) from exc
                return _extract_internal_denial(tool, result)

            yield _PreparedInternalProbe(
                invoke,
                True,
                lambda: calls["count"],
            )
            return

        if seam == "ChatRunner.run_turn":
            from .agent.chat import chat_runner as chat_runner_module
            from .agent.chat.chat_runner import ChatRunner
            from .agent.chat.conversation_store import Conversation

            runner = ChatRunner(
                tool_executor=inert_executor,
                registry=_AllSchemasRegistry([]),
            )
            conversation = Conversation(
                id=f"acceptance-chat-{uuid.uuid4().hex[:8]}",
                persona="worker",
                model="acceptance-model",
            )
            call_id = f"acceptance-chat-{tool}"
            calls = {"count": 0}
            causal_history_validated = {"value": False}

            async def primary_provider(**kwargs):
                calls["count"] += 1
                if calls["count"] == 1:
                    return _internal_chat_tool_stream(tool, call_id)
                if calls["count"] == 2:
                    _require_causal_denial_history(
                        kwargs.get("messages"),
                        tool=tool,
                        call_id=call_id,
                        adapter="rook_chat",
                    )
                    causal_history_validated["value"] = True
                    return _internal_chat_text_stream()
                raise AcceptanceError(
                    "ChatRunner primary model exceeded two calls"
                )

            async def runtime_facts(**_kwargs):
                return {
                    "rhino": {"connected": False},
                    "prompt": {"available": False},
                    "verified_runtime_facts": [],
                }

            original_provider = chat_runner_module.litellm.acompletion
            original_facts = chat_runner_module.collect_runtime_facts
            chat_runner_module.litellm.acompletion = primary_provider
            chat_runner_module.collect_runtime_facts = runtime_facts
            stack.callback(
                setattr,
                chat_runner_module.litellm,
                "acompletion",
                original_provider,
            )
            stack.callback(
                setattr,
                chat_runner_module,
                "collect_runtime_facts",
                original_facts,
            )

            async def invoke():
                async for _event in runner.run_turn(
                    conversation,
                    "exercise installed containment",
                    system_prompt="acceptance",
                ):
                    pass
                if calls["count"] != 2:
                    raise AcceptanceError(
                        "ChatRunner primary model call count drift"
                    )
                if not causal_history_validated["value"]:
                    raise AcceptanceError(
                        "ChatRunner causal denial history was not validated"
                    )
                messages = [
                    message
                    for message in conversation.messages
                    if message.get("role") == "tool"
                    and message.get("tool_call_id") == call_id
                ]
                if len(messages) != 1:
                    raise AcceptanceError(
                        "ChatRunner containment result message drift"
                    )
                try:
                    result = json.loads(messages[0]["content"])
                except (KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise AcceptanceError(
                        "ChatRunner containment result is malformed"
                    ) from exc
                return _extract_internal_denial(tool, result)

            yield _PreparedInternalProbe(
                invoke,
                True,
                lambda: calls["count"],
            )
            return

        if seam == "rook.agent.plan_graph_live.apply_live_producer_node":
            from .agent.plan_graph_live import (
                EXECUTION_PARAMS_KEY,
                apply_live_producer_node,
            )
            from .learning.plan_graph import PlanGraph, PlanGraphNode
            from .learning.plan_graph_projection import (
                OUTCOME_PROJECTION_ROLE_KEY,
            )

            node_id = "acceptance-producer"
            node = PlanGraphNode(
                id=node_id,
                intent="exercise installed containment",
                execution_ref=f"{tool}:v1",
                metadata={
                    OUTCOME_PROJECTION_ROLE_KEY: "artifact_producer",
                    EXECUTION_PARAMS_KEY: poison,
                },
            )
            node.status = "ready"
            graph = PlanGraph(nodes={node_id: node})

            async def forbidden_dispatch(_name: str, _params: dict):
                raise AcceptanceError(
                    "plan graph containment reached dispatch"
                )

            async def invoke():
                result = await apply_live_producer_node(
                    graph,
                    node_id,
                    forbidden_dispatch,
                )
                if (
                    result.graph is not graph
                    or result.applied is not False
                    or result.node_id != node_id
                    or result.tool_name != tool
                    or result.outcome_status is not None
                    or result.reason != "tool_lifecycle_denied"
                ):
                    raise AcceptanceError(
                        "plan graph containment result drift"
                    )
                entry = resolve_contained_identity(tool)
                if entry is None:
                    raise AcceptanceError(
                        "plan graph tool identity is not contained"
                    )
                return _extract_internal_denial(
                    tool,
                    containment_envelope(entry),
                )

            yield _PreparedInternalProbe(invoke, True, no_model_calls)
            return

        if seam in CONSTANT_INTERNAL_SEAMS:
            method = getattr(server, seam.split(".", 1)[1])

            async def invoke():
                return _extract_internal_denial(
                    tool,
                    await method(poison),
                )

            yield _PreparedInternalProbe(invoke, True, no_model_calls)
            return

        if seam in {
            "BootstrapRunner.run_test",
            "BootstrapRunner._mock_executor",
        }:
            from .bootstrap.runner import BootstrapRunner

            runner = object.__new__(BootstrapRunner)
            runner.tool_executor = _InternalPoison(
                "bootstrap tool executor"
            )
            runner.completed_tests = set()

            if seam == "BootstrapRunner.run_test":
                def invoke():
                    result = runner.run_test(
                        _InternalToolOnly(tool, "bootstrap test")
                    )
                    return _extract_internal_denial(tool, result)
            else:
                def invoke():
                    return _extract_internal_denial(
                        tool,
                        runner._mock_executor(tool, poison),
                    )

            yield _PreparedInternalProbe(invoke, False, no_model_calls)
            return

        if seam == "bootstrap.HttpExecutor.execute":
            from .bootstrap.executor import HttpExecutor

            executor = HttpExecutor(base_url="http://127.0.0.1:9")

            def invoke():
                return _extract_internal_denial(
                    tool,
                    executor.execute(tool, poison),
                )

            yield _PreparedInternalProbe(invoke, False, no_model_calls)
            return

        if seam == "bootstrap.create_mock_executor.callable":
            from .bootstrap.executor import create_mock_executor

            executor = create_mock_executor()

            def invoke():
                return _extract_internal_denial(
                    tool,
                    executor(tool, poison),
                )

            yield _PreparedInternalProbe(invoke, False, no_model_calls)
            return

        if seam == "learning.create_tool_executor.callable":
            from .learning.agent import create_tool_executor

            executor = loop.run_until_complete(create_tool_executor())

            async def invoke():
                return _extract_internal_denial(
                    tool,
                    await executor(tool, poison),
                )

            yield _PreparedInternalProbe(invoke, True, no_model_calls)
            return

        if seam.startswith("Investigator."):
            from .learning.investigator import Investigator

            investigator = object.__new__(Investigator)
            investigator.kg = _InternalPoison("investigator knowledge graph")
            investigator.executor = _InternalPoison(
                "investigator executor"
            )
            investigator.context = _InternalPoison(
                "investigator exploration context"
            )
            investigator._current_phase = _InternalPoison(
                "investigator phase"
            )
            method_name = seam.split(".", 1)[1]

            async def invoke():
                if method_name == "investigate_tool":
                    result = await investigator.investigate_tool(tool)
                elif method_name == "investigate_gap":
                    result = await investigator.investigate_gap(
                        _InternalToolOnly(tool, "investigator gap")
                    )
                elif method_name == "investigate_workflow":
                    result = await investigator.investigate_workflow(
                        [
                            ("rhino_ping", poison),
                            (tool, poison),
                        ],
                        "exercise installed containment",
                    )
                else:
                    result = await investigator._run_experiment(
                        tool,
                        poison,
                    )
                return _extract_internal_denial(tool, result)

            yield _PreparedInternalProbe(invoke, True, no_model_calls)
            return

        if seam.startswith("HybridInvestigator."):
            from .learning.hybrid_investigator import HybridInvestigator

            investigator = object.__new__(HybridInvestigator)
            investigator.kg = _InternalPoison(
                "hybrid investigator knowledge graph"
            )
            investigator.executor = _InternalPoison(
                "hybrid investigator executor"
            )
            investigator.use_dspy = True
            investigator.use_visual_verification = True
            investigator.verifier = _InternalPoison(
                "hybrid viewport verifier"
            )
            investigator._geometry_ids = _InternalPoisonMapping(
                "hybrid geometry ids"
            )
            investigator._init_dspy_modules = _InternalPoison(
                "hybrid DSPy initialization"
            )
            investigator.hypothesis_selector = _InternalPoison(
                "hybrid hypothesis selector"
            )
            investigator.fix_selector = _InternalPoison(
                "hybrid fix selector"
            )
            investigator.training_buffer = _InternalPoison(
                "hybrid training buffer"
            )
            method_name = seam.split(".", 1)[1]

            async def invoke():
                if method_name == "investigate_tool":
                    result = await investigator.investigate_tool(tool)
                else:
                    result = await investigator.investigate_gap(
                        _InternalToolOnly(tool, "hybrid gap")
                    )
                return _extract_internal_denial(tool, result)

            yield _PreparedInternalProbe(invoke, True, no_model_calls)
            return

        if seam == "LearningSession.run_investigation_cycle.tool_target":
            from .learning.session import LearningSession

            session = object.__new__(LearningSession)
            session.use_hybrid = False
            session.progress = _InternalPoison("learning progress")
            session.reporter = _InternalPoison("learning reporter")
            session.investigator = _InternalPoison(
                "learning investigator"
            )
            session.hybrid_investigator = _InternalPoison(
                "hybrid learning investigator"
            )
            session.kg = _InternalPoison("learning knowledge graph")

            async def invoke():
                result = await session.run_investigation_cycle(
                    f"tool:{tool}"
                )
                return _extract_internal_denial(tool, result)

            yield _PreparedInternalProbe(invoke, True, no_model_calls)
            return

        if seam.startswith("explorer."):
            from .explorer.executor import (
                HttpExecutor,
                MockExecutor,
            )

            executor = (
                HttpExecutor(base_url="http://127.0.0.1:9")
                if ".HttpExecutor." in seam
                else MockExecutor()
            )
            method_name = seam.rsplit(".", 1)[1]
            if method_name == "execute":
                async def invoke():
                    return _extract_internal_denial(
                        tool,
                        await executor.execute(tool, poison),
                    )

                yield _PreparedInternalProbe(
                    invoke,
                    True,
                    no_model_calls,
                )
            else:
                def invoke():
                    return _extract_internal_denial(
                        tool,
                        executor.execute_sync(tool, poison),
                    )

                yield _PreparedInternalProbe(
                    invoke,
                    False,
                    no_model_calls,
                )
            return

        raise AcceptanceError(f"unsupported internal seam adapter: {seam}")


def _invoke_prepared_internal_probe(
    loop: asyncio.AbstractEventLoop,
    prepared: _PreparedInternalProbe,
) -> dict[str, object]:
    if prepared.is_async:
        result = loop.run_until_complete(prepared.invoke())
    else:
        result = prepared.invoke()
    if inspect.isawaitable(result):
        raise AcceptanceError(
            "synchronous internal adapter returned an awaitable"
        )
    if not isinstance(result, Mapping):
        raise AcceptanceError("internal adapter result is malformed")
    return dict(result)


def _internal_matrix(*, artifact_dir: Path) -> Path:
    runtime = _validate_current_installed_startup_environment()
    artifact_dir = Path(artifact_dir).expanduser().resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    from . import server
    from .learning.metrics_store import get_metrics_store

    _validate_current_installed_process(
        required_rook_modules=(
            "rook",
            "rook.containment_acceptance",
            "rook.server",
        ),
        allowed_command_roots=(artifact_dir,),
    )
    pairs = _expected_internal_pairs()
    _validate_internal_pair_set(pairs)
    probes: list[dict[str, object]] = []
    loop = asyncio.new_event_loop()
    installed_scope = _installed_spy_scope()
    installed: _InstalledSpies | None = None
    try:
        loop.run_until_complete(_refresh_installed_catalog(server))
        installed = loop.run_until_complete(installed_scope.__aenter__())
        try:
            for index, spec in enumerate(pairs):
                with _prepare_internal_probe(
                    spec,
                    loop=loop,
                    server=server,
                ) as prepared:
                    installed.reset()
                    store = get_metrics_store()
                    before = store.get_containment_denials_snapshot()
                    with installed.phase("internal"):
                        result = _invoke_prepared_internal_probe(
                            loop,
                            prepared,
                        )
                    after = store.get_containment_denials_snapshot()
                    stages = installed.counters

                    _validate_denial_result(spec.tool, result)
                    _one_event_ring_delta(
                        before,
                        after,
                        expected_tool=spec.tool,
                        expected_origin=spec.origin,
                    )
                    expected_stages = {
                        stage: 0 for stage in STAGE_NAMES
                    }
                    expected_stages["recording_attempt"] = 1
                    if stages != expected_stages:
                        raise AcceptanceError(
                            f"internal stage counters drift for "
                            f"{spec.seam}: {stages}"
                        )
                    primary_model_calls = prepared.primary_model_calls()
                    expected_model_calls = (
                        2
                        if spec.seam
                        in {"RookAgent._run_loop", "ChatRunner.run_turn"}
                        else 0
                    )
                    if primary_model_calls != expected_model_calls:
                        raise AcceptanceError(
                            f"internal primary model count drift for "
                            f"{spec.seam}: {primary_model_calls}"
                        )
                    probes.append(
                        {
                            "index": index,
                            "seam": spec.seam,
                            "adapter": spec.adapter,
                            "tool": spec.tool,
                            "origin": spec.origin,
                            "result": result,
                            "telemetry_before": before,
                            "telemetry_after": after,
                            "stages": stages,
                            "primary_model_calls": primary_model_calls,
                        }
                    )
        finally:
            if installed is not None:
                loop.run_until_complete(
                    installed_scope.__aexit__(None, None, None)
                )

        tools = loop.run_until_complete(server.list_tools())
        projections = _collect_model_projection_evidence_from_tools(tools)
    finally:
        loop.close()

    process = _validate_current_installed_process(
        required_rook_modules=(
            "rook",
            "rook.containment_acceptance",
            "rook.server",
        ),
        allowed_command_roots=(artifact_dir,),
    )
    expected_pairs = [
        {
            "seam": item.seam,
            "tool": item.tool,
            "origin": item.origin,
            "adapter": item.adapter,
        }
        for item in pairs
    ]
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "command": "internal-matrix",
        "process": process,
        "expected_pairs": expected_pairs,
        "probes": probes,
        "model_projections": projections,
    }
    output_path = artifact_dir / "internal-matrix.json"
    _atomic_write_json(output_path, artifact)
    _validate_internal_artifact(
        artifact,
        expected_install_root=runtime.install_root,
        expected_data_root=runtime.data_root,
        expected_dspy_cache=(runtime.data_root / "dspy-cache").resolve(),
        expected_chirp_home=_code_owned_chirp_home(runtime.install_root),
        allowed_command_roots=(
            runtime.runtime_root,
            artifact_dir,
        ),
    )
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "transport-profile":
            asyncio.run(
                _transport_profile(
                    profile=args.profile,
                    artifact_dir=Path(args.artifact_dir),
                )
            )
        elif args.command == "discovery-default":
            asyncio.run(
                _discovery_command(
                    command=args.command,
                    artifact_dir=Path(args.artifact_dir),
                )
            )
        elif args.command == "discovery-interactive":
            asyncio.run(
                _discovery_command(
                    command=args.command,
                    artifact_dir=Path(args.artifact_dir),
                )
            )
        elif args.command == "internal-matrix":
            _internal_matrix(artifact_dir=Path(args.artifact_dir))
        elif args.command == "_transport-child":
            asyncio.run(
                _transport_child(
                    profile=args.profile,
                    run_id=args.run_id,
                    spy_path=Path(args.spy_path),
                )
            )
        else:
            raise AcceptanceError(
                f"unsupported acceptance command: {args.command}"
            )
    except AcceptanceError as exc:
        print(f"containment acceptance failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("containment acceptance interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(
            f"containment acceptance failed: "
            f"{_bounded_exception_summary(exc)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
