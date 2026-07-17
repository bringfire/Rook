from __future__ import annotations

import argparse
import asyncio
import contextlib
import copy
import hashlib
import importlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from rook.tool_lifecycle import (
    DispatchOrigin,
    contained_names,
    containment_envelope,
    resolve_contained_identity,
)


EXPECTED_RED = "EXPECTED_RED:T7:INSTALLED_HARNESS"
RUN_ID = "0123456789abcdef0123456789abcdef"
CONTAINED = (
    "gh_execute_intent",
    "rhino_execute_intent",
    "plan_and_execute",
    "spawn_agent",
    "gh_explore_workflow",
    "gh_replay_recipe",
)
STAGES = (
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
PATCHPOINTS = (
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
ARBITRARY_SEAMS = (
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
CONSTANT_SEAMS = {
    "server._handle_spawn_agent": "spawn_agent",
    "server._handle_plan_and_execute": "plan_and_execute",
}


try:
    acceptance = importlib.import_module("rook.containment_acceptance")
except ModuleNotFoundError as exc:
    if exc.name != "rook.containment_acceptance":
        raise
    acceptance = None


requires_contract = pytest.mark.skipif(
    acceptance is None,
    reason="installed containment acceptance module is not implemented",
)


def test_installed_containment_acceptance_contract_is_available() -> None:
    assert acceptance is not None, (
        f"{EXPECTED_RED} rook.containment_acceptance is not implemented"
    )


@requires_contract
def test_literal_contract_tables_are_exact_and_closed() -> None:
    assert acceptance.SCHEMA_VERSION == 1
    assert acceptance.PROFILE_VALUES == ("full", "lean", "readonly")
    assert acceptance.CONTAINED_TOOL_NAMES == CONTAINED
    assert acceptance.STAGE_NAMES == STAGES
    assert acceptance.ARBITRARY_INTERNAL_SEAMS == ARBITRARY_SEAMS
    assert acceptance.CONSTANT_INTERNAL_SEAMS == CONSTANT_SEAMS
    assert tuple(
        (spec.identifier, spec.stage, spec.kind)
        for spec in acceptance.PATCHPOINT_SPECS
    ) == PATCHPOINTS

    assert len(acceptance.PATCHPOINT_SPECS) == 18
    assert len({spec.identifier for spec in acceptance.PATCHPOINT_SPECS}) == 18
    assert set(acceptance.CONTAINED_TOOL_NAMES) == set(contained_names())
    assert len(acceptance._expected_internal_pairs()) == 164


@requires_contract
def test_cli_parser_has_only_the_pinned_modes_and_arguments(tmp_path: Path) -> None:
    parser = acceptance._build_parser()
    artifact_dir = str(tmp_path / "artifacts")
    spy_path = str((tmp_path / "spy.json").resolve())

    for profile in acceptance.PROFILE_VALUES:
        parsed = parser.parse_args(
            [
                "transport-profile",
                "--profile",
                profile,
                "--artifact-dir",
                artifact_dir,
            ]
        )
        assert vars(parsed) == {
            "command": "transport-profile",
            "profile": profile,
            "artifact_dir": artifact_dir,
        }

    for command in (
        "discovery-default",
        "discovery-interactive",
        "internal-matrix",
    ):
        parsed = parser.parse_args([command, "--artifact-dir", artifact_dir])
        assert vars(parsed) == {
            "command": command,
            "artifact_dir": artifact_dir,
        }

    parsed = parser.parse_args(
        [
            "_transport-child",
            "--profile",
            "readonly",
            "--run-id",
            RUN_ID,
            "--spy-path",
            spy_path,
        ]
    )
    assert vars(parsed) == {
        "command": "_transport-child",
        "profile": "readonly",
        "run_id": RUN_ID,
        "spy_path": spy_path,
    }

    rejected = (
        ["transport-profile", "--artifact-dir", artifact_dir],
        [
            "transport-profile",
            "--profile",
            "unknown",
            "--artifact-dir",
            artifact_dir,
        ],
        ["discovery-default", "--profile", "full", "--artifact-dir", artifact_dir],
        [
            "_transport-child",
            "--profile",
            "full",
            "--run-id",
            "not-32-hex",
            "--spy-path",
            spy_path,
        ],
        [
            "_transport-child",
            "--profile",
            "full",
            "--run-id",
            RUN_ID,
            "--spy-path",
            "relative.json",
        ],
        [
            "_transport-child",
            "--profile",
            "full",
            "--run-id",
            RUN_ID,
            "--spy-path",
            spy_path,
            "--handler",
            "caller.module:handler",
        ],
        [
            "internal-matrix",
            "--artifact-dir",
            artifact_dir,
            "--tool",
            "safe_tool",
        ],
        ["bypass", "--artifact-dir", artifact_dir],
    )
    for argv in rejected:
        with pytest.raises(SystemExit):
            parser.parse_args(argv)

    option_strings = {
        option
        for action in _all_parser_actions(parser)
        for option in action.option_strings
    }
    assert not {
        "--spy-module",
        "--handler",
        "--tool",
        "--tool-list",
        "--bypass",
        "--hook",
        "--module",
        "--callable",
    }.intersection(option_strings)


def _all_parser_actions(parser: argparse.ArgumentParser):
    yield from parser._actions
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                yield from _all_parser_actions(child)


@requires_contract
def test_environment_sanitizer_is_case_insensitive_and_command_owned(
    tmp_path: Path,
) -> None:
    install_root = tmp_path / "installed" / "app"
    data_root = tmp_path / "installed" / "data"
    dspy_cache = data_root / "dspy-cache"
    chirp_home = tmp_path / "installed" / "chirp"
    for path in (install_root, data_root, dspy_cache, chirp_home):
        path.mkdir(parents=True, exist_ok=True)

    hostile = {
        "Path": os.environ.get("PATH", ""),
        "SAFE_UNRELATED": "preserved",
        "PYTHONPATH": "C:/source-shadow",
        "pythonhome": "C:/bad-python",
        "PyThOnUsErBaSe": "C:/hostile-user-base",
        "pYtHoNnOuSeRsItE": "0",
        "DSPY_MODEL": "hostile/model",
        "dspy_cachedir": "C:/hostile-cache",
        "CHIRP_HOME": "C:/source/chirp",
        "ROOK_INSTALL_ROOT": "C:/wrong",
        "rook_data_dir": "C:/wrong-data",
        "Rook_Mode": "dev",
        "ROOK_DSPY_RESTRICT_PICKLE": "0",
        "ROOK_MCP_TOOL_PROFILE": "lean",
        "rook_enable_interactive_command_learning": "1",
        "ROOK_TARGET": "hostile-target",
        "ROOK_PROCESS_ID": "123",
        "ROOK_DOCUMENT_ID": "secret-doc",
        "ROOK_RHINO_PORT": "9999",
        "ROOK_RHINO_EXECUTABLE": "C:/Rhino.exe",
        "ROOK_HARNESS_MODE": "unsafe",
        "ROOK_BRIDGE_OVERRIDE": "unsafe",
        "ROOK_MODEL": "unsafe-model",
    }

    clean = acceptance._sanitized_child_environment(
        hostile,
        install_root=install_root,
        data_root=data_root,
        dspy_cache=dspy_cache,
        chirp_home=chirp_home,
        profile="readonly",
        interactive=False,
    )

    assert clean["SAFE_UNRELATED"] == "preserved"
    assert clean["PYTHONNOUSERSITE"] == "1"
    assert clean["ROOK_INSTALL_ROOT"] == str(install_root.resolve())
    assert clean["ROOK_DATA_DIR"] == str(data_root.resolve())
    assert clean["ROOK_MODE"] == "release"
    assert clean["ROOK_DSPY_RESTRICT_PICKLE"] == "1"
    assert clean["DSPY_CACHEDIR"] == str(dspy_cache.resolve())
    assert clean["CHIRP_HOME"] == str(chirp_home.resolve())
    assert clean["ROOK_MCP_TOOL_PROFILE"] == "readonly"
    assert "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING" not in clean

    folded = {key.casefold(): value for key, value in clean.items()}
    assert "pythonpath" not in folded
    assert "pythonhome" not in folded
    assert "pythonuserbase" not in folded
    assert "dspy_model" not in folded
    assert folded["pythonnousersite"] == "1"
    assert folded["dspy_cachedir"] == str(dspy_cache.resolve())
    allowed_rook = {
        "rook_install_root",
        "rook_data_dir",
        "rook_mode",
        "rook_dspy_restrict_pickle",
        "rook_mcp_tool_profile",
    }
    assert {
        key for key in folded if key.startswith("rook_")
    } == allowed_rook

    default = acceptance._sanitized_child_environment(
        hostile,
        install_root=install_root,
        data_root=data_root,
        dspy_cache=dspy_cache,
    )
    default_folded = {key.casefold(): value for key, value in default.items()}
    assert "rook_mcp_tool_profile" not in default_folded
    assert "rook_enable_interactive_command_learning" not in default_folded
    assert "chirp_home" not in default_folded

    interactive = acceptance._sanitized_child_environment(
        hostile,
        install_root=install_root,
        data_root=data_root,
        dspy_cache=dspy_cache,
        profile="full",
        interactive=True,
    )
    interactive_folded = {
        key.casefold(): value for key, value in interactive.items()
    }
    assert interactive_folded["rook_mcp_tool_profile"] == "full"
    assert (
        interactive_folded["rook_enable_interactive_command_learning"] == "1"
    )


@requires_contract
def test_user_site_tripwires_cannot_execute_under_sanitized_environment(
    tmp_path: Path,
) -> None:
    install_root = tmp_path / "app"
    data_root = tmp_path / "data"
    dspy_cache = data_root / "dspy-cache"
    owned_base = tmp_path / "hostile-user-base"
    version = f"Python{sys.version_info.major}{sys.version_info.minor}"
    user_site = owned_base / version / "site-packages"
    for path in (install_root, data_root, dspy_cache, user_site):
        path.mkdir(parents=True, exist_ok=True)

    tripwire_code = (
        "from pathlib import Path; "
        "Path(__file__).with_suffix('.hit').write_text("
        "'executed', encoding='ascii')"
    )
    for filename in ("sitecustomize.py", "usercustomize.py"):
        (user_site / filename).write_text(tripwire_code, encoding="utf-8")

    clean = acceptance._sanitized_child_environment(
        {
            **os.environ,
            "PyThOnUsErBaSe": str(owned_base),
            "pYtHoNnOuSeRsItE": "0",
        },
        install_root=install_root,
        data_root=data_root,
        dspy_cache=dspy_cache,
    )
    completed = subprocess.run(
        [sys.executable, "-c", "import site; print('ok')"],
        cwd=tmp_path,
        env=clean,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"
    assert not (user_site / "sitecustomize.hit").exists()
    assert not (user_site / "usercustomize.hit").exists()


def _process_evidence(
    install_root: Path,
    *,
    sys_path: list[str] | None = None,
    origins: dict[str, str] | None = None,
    cwd: Path | None = None,
    data_root: Path | None = None,
    dspy_cache: Path | None = None,
    chirp_home: Path | None = None,
    profile: str | None = None,
    interactive: bool = False,
) -> dict[str, object]:
    package_root = install_root / "mcp_server" / "src" / "rook"
    package_root.mkdir(parents=True, exist_ok=True)
    data_root = data_root or install_root.parent / "data"
    dspy_cache = dspy_cache or data_root / "dspy-cache"
    environment = {
        "PYTHONNOUSERSITE": "1",
        "ROOK_INSTALL_ROOT": str(install_root.resolve()),
        "ROOK_DATA_DIR": str(data_root.resolve()),
        "ROOK_MODE": "release",
        "ROOK_DSPY_RESTRICT_PICKLE": "1",
        "DSPY_CACHEDIR": str(dspy_cache.resolve()),
    }
    if chirp_home is not None:
        environment["CHIRP_HOME"] = str(chirp_home.resolve())
    if profile is not None:
        environment["ROOK_MCP_TOOL_PROFILE"] = profile
    if interactive:
        environment["ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING"] = "1"
    return {
        "executable": str((install_root / "python" / "python.exe").resolve()),
        "installed_root": str(install_root.resolve()),
        "cwd": str((cwd or install_root.parent / "run").resolve()),
        "environment": environment,
        "sys_path": sys_path
        or [
            str((install_root.parent / "run").resolve()),
            str((install_root / "fixture-site-packages").resolve()),
            str((install_root / "mcp_server" / "src").resolve()),
        ],
        "rook_origins": origins
        or {
            "rook": str((package_root / "__init__.py").resolve()),
            "rook.server": str((package_root / "server.py").resolve()),
        },
        "process_id": os.getpid(),
        "process_start_token": "a" * 32,
    }


_PROCESS_ENV_CASES = (
    ("transport-full-parent", "full", False, False),
    ("transport-lean-parent", "lean", False, False),
    ("transport-readonly-parent", "readonly", False, False),
    ("transport-full-private-child", "full", False, True),
    ("transport-lean-private-child", "lean", False, False),
    ("transport-readonly-private-child", "readonly", False, False),
    ("discovery-default", None, False, False),
    ("discovery-interactive", "full", True, False),
    ("internal-matrix", None, False, False),
)


@requires_contract
@pytest.mark.parametrize(
    "command,profile,interactive,with_chirp",
    _PROCESS_ENV_CASES,
)
def test_process_environment_is_exact_and_closed_for_every_installed_mode(
    tmp_path: Path,
    command: str,
    profile: str | None,
    interactive: bool,
    with_chirp: bool,
) -> None:
    install_root = tmp_path / command / "app"
    data_root = tmp_path / command / "data"
    dspy_cache = data_root / "dspy-cache"
    chirp_home = tmp_path / command / "chirp" if with_chirp else None
    evidence = _process_evidence(
        install_root,
        data_root=data_root,
        dspy_cache=dspy_cache,
        chirp_home=chirp_home,
        profile=profile,
        interactive=interactive,
    )
    expected = {
        "expected_data_root": data_root,
        "expected_dspy_cache": dspy_cache,
        "expected_chirp_home": chirp_home,
        "expected_profile": profile,
        "expected_interactive": interactive,
    }

    acceptance._validate_process_evidence(
        evidence,
        expected_install_root=install_root,
        **expected,
    )

    mutations = {
        "target": ("ROOK_TARGET", "hostile-target"),
        "process": ("ROOK_PROCESS_ID", "123"),
        "document": ("ROOK_DOCUMENT_ID", "secret-doc"),
        "rhino-port": ("ROOK_RHINO_PORT", "9999"),
        "rhino-executable": ("ROOK_RHINO_EXECUTABLE", "C:/Rhino.exe"),
        "bridge": ("ROOK_BRIDGE_OVERRIDE", "unsafe"),
        "harness": ("ROOK_HARNESS_MODE", "unsafe"),
        "model": ("ROOK_MODEL", "unsafe-model"),
        "data-root": ("ROOK_DATA_DIR", str(tmp_path / "wrong-data")),
        "dspy-cache": ("DSPY_CACHEDIR", str(tmp_path / "wrong-cache")),
        "profile": (
            "ROOK_MCP_TOOL_PROFILE",
            "lean" if profile != "lean" else "full",
        ),
        "interactive": (
            "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING",
            "0" if interactive else "1",
        ),
        "chirp": (
            "CHIRP_HOME",
            str(tmp_path / ("wrong-chirp" if chirp_home else "unexpected-chirp")),
        ),
    }
    for label, (name, value) in mutations.items():
        drifted = copy.deepcopy(evidence)
        drifted["environment"][name] = value
        with pytest.raises(
            acceptance.AcceptanceError,
            match="environment",
        ):
            acceptance._validate_process_evidence(
                drifted,
                expected_install_root=install_root,
                **expected,
            )


@requires_contract
def test_current_process_validation_rejects_foreign_process_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = _fake_release_runtime(tmp_path)
    evidence = _process_evidence(runtime.install_root)
    evidence["process_id"] = os.getpid() + 1
    monkeypatch.setattr(acceptance, "resolve_runtime_paths", lambda: runtime)
    monkeypatch.setattr(
        acceptance,
        "_collect_process_evidence",
        lambda: evidence,
    )

    with pytest.raises(
        acceptance.AcceptanceError,
        match="current process identity",
    ):
        acceptance._validate_current_installed_process(
            required_rook_modules=("rook", "rook.server"),
        )


@requires_contract
def test_process_evidence_rejects_source_like_cwd_before_command_allowlist(
    tmp_path: Path,
) -> None:
    install_root = tmp_path / "fixture-install" / "app"
    source_cwd = tmp_path / "development" / ".worktrees" / "branch" / "run"
    source_cwd.mkdir(parents=True)
    contaminated = _process_evidence(
        install_root,
        cwd=source_cwd,
        sys_path=[
            str(source_cwd.resolve()),
            str((install_root / "mcp_server" / "src").resolve()),
        ],
    )

    with pytest.raises(
        acceptance.AcceptanceError,
        match="cwd.*source|source.*cwd",
    ):
        acceptance._validate_process_evidence(
            contaminated,
            expected_install_root=install_root,
            allowed_command_roots=(source_cwd,),
        )

    isolated_cwd = (
        tmp_path / "isolated" / "rook-containment" / RUN_ID / "full"
    )
    isolated_cwd.mkdir(parents=True)
    legitimate = _process_evidence(
        install_root,
        cwd=isolated_cwd,
        sys_path=[
            str(isolated_cwd.resolve()),
            str((install_root / "mcp_server" / "src").resolve()),
        ],
    )
    acceptance._validate_process_evidence(
        legitimate,
        expected_install_root=install_root,
        allowed_command_roots=(isolated_cwd,),
    )


def _structural_rook_checkout(
    root: Path,
    *,
    git_marker_kind: str,
) -> Path:
    checkout = root / f"source-checkout-{git_marker_kind}"
    if git_marker_kind == "directory":
        (checkout / ".git").mkdir(parents=True)
    else:
        checkout.mkdir(parents=True)
        (checkout / ".git").write_text(
            "gitdir: detached-metadata\n",
            encoding="utf-8",
        )
    (checkout / "Rook.sln").write_text("fixture\n", encoding="utf-8")
    (checkout / "mcp_server" / "src" / "rook").mkdir(parents=True)
    (checkout / "docs").mkdir()
    return checkout


@requires_contract
@pytest.mark.parametrize(
    "git_marker_kind,relative_cwd",
    [
        ("directory", Path(".")),
        ("file", Path("docs")),
    ],
    ids=("checkout-root", "ordinary-descendant"),
)
def test_process_evidence_rejects_structural_rook_checkout_cwd(
    tmp_path: Path,
    git_marker_kind: str,
    relative_cwd: Path,
) -> None:
    install_root = tmp_path / "fixture-install" / "app"
    checkout = _structural_rook_checkout(
        tmp_path,
        git_marker_kind=git_marker_kind,
    )
    source_cwd = (checkout / relative_cwd).resolve()
    contaminated = _process_evidence(
        install_root,
        cwd=source_cwd,
        sys_path=[
            str(source_cwd),
            str((install_root / "mcp_server" / "src").resolve()),
        ],
    )

    with pytest.raises(acceptance.AcceptanceError, match="cwd.*source|source.*cwd"):
        acceptance._validate_process_evidence(
            contaminated,
            expected_install_root=install_root,
            allowed_command_roots=(source_cwd,),
        )


def _actual_main_checkout_root() -> Path:
    checkout = Path(__file__).resolve().parents[2]
    git_marker = checkout / ".git"
    if git_marker.is_dir():
        return checkout
    pointer = git_marker.read_text(encoding="utf-8").strip()
    prefix = "gitdir:"
    if not pointer.casefold().startswith(prefix):
        raise AssertionError("worktree .git pointer is malformed")
    git_dir = Path(pointer[len(prefix):].strip())
    if not git_dir.is_absolute():
        git_dir = checkout / git_dir
    return git_dir.resolve().parents[2]


@requires_contract
def test_actual_main_checkout_root_and_docs_are_source_like() -> None:
    checkout = _actual_main_checkout_root()
    assert (checkout / "Rook.sln").is_file()
    assert (checkout / "mcp_server" / "src" / "rook").is_dir()
    assert acceptance._path_looks_like_development_source(checkout)
    assert acceptance._path_looks_like_development_source(checkout / "docs")


@requires_contract
def test_structural_checkout_detection_preserves_installed_and_named_rook_cwds(
    tmp_path: Path,
) -> None:
    install_root = tmp_path / "fixture-install" / "app"
    installed_cwd = install_root / "run"
    arbitrary_named_rook_cwd = tmp_path / "unrelated" / "rook" / "docs"
    installed_cwd.mkdir(parents=True)
    arbitrary_named_rook_cwd.mkdir(parents=True)

    for cwd in (installed_cwd, arbitrary_named_rook_cwd):
        legitimate = _process_evidence(
            install_root,
            cwd=cwd,
            sys_path=[
                str(cwd.resolve()),
                str((install_root / "mcp_server" / "src").resolve()),
            ],
        )
        acceptance._validate_process_evidence(
            legitimate,
            expected_install_root=install_root,
            allowed_command_roots=(cwd,),
        )


def _fake_release_runtime(tmp_path: Path) -> SimpleNamespace:
    runtime_root = tmp_path / "installed-runtime"
    install_root = runtime_root / "app"
    data_root = runtime_root / "data"
    temp_root = runtime_root / "temp"
    for path in (install_root, data_root, temp_root):
        path.mkdir(parents=True)
    return SimpleNamespace(
        mode="release",
        install_root=install_root,
        data_root=data_root,
        runtime_root=runtime_root,
        temp_root=temp_root,
    )


def _set_exact_acceptance_environment(
    monkeypatch: pytest.MonkeyPatch,
    runtime: SimpleNamespace,
    *,
    profile: str | None = None,
    interactive: bool = False,
) -> None:
    for name in tuple(os.environ):
        if (
            name.upper() in acceptance._RELEVANT_NON_ROOK_ENV
            or name.casefold().startswith("rook_")
        ):
            monkeypatch.delenv(name, raising=False)
    expected = acceptance._expected_relevant_environment(
        install_root=runtime.install_root,
        data_root=runtime.data_root,
        dspy_cache=runtime.data_root / "dspy-cache",
        chirp_home=None,
        profile=profile,
        interactive=interactive,
    )
    for name, value in expected.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("TEMP", str(runtime.temp_root))
    monkeypatch.setenv("TMP", str(runtime.temp_root))


def _install_forbidden_acceptance_work(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, int]:
    from mcp.client import stdio as mcp_stdio
    from rook import server

    calls = {"refresh": 0, "list": 0, "probe": 0, "child": 0}

    async def forbidden_refresh(_server: object) -> None:
        calls["refresh"] += 1
        raise acceptance.AcceptanceError("acceptance work started")

    async def forbidden_list_tools():
        calls["list"] += 1
        raise acceptance.AcceptanceError("acceptance work started")

    @contextlib.contextmanager
    def forbidden_probe(*_args, **_kwargs):
        calls["probe"] += 1
        raise acceptance.AcceptanceError("acceptance work started")
        yield

    @contextlib.asynccontextmanager
    async def forbidden_child(*_args, **_kwargs):
        calls["child"] += 1
        raise acceptance.AcceptanceError("acceptance work started")
        yield

    monkeypatch.setattr(
        acceptance,
        "_refresh_installed_catalog",
        forbidden_refresh,
    )
    monkeypatch.setattr(server, "list_tools", forbidden_list_tools)
    monkeypatch.setattr(
        acceptance,
        "_prepare_internal_probe",
        forbidden_probe,
    )
    monkeypatch.setattr(mcp_stdio, "stdio_client", forbidden_child)
    return calls


def _invoke_acceptance_command(
    command: str,
    *,
    tmp_path: Path,
    profile: str | None = None,
) -> None:
    artifact_dir = tmp_path / f"artifacts-{command}-{profile or 'none'}"
    if command == "transport-profile":
        assert profile is not None
        asyncio.run(
            acceptance._transport_profile(
                profile=profile,
                artifact_dir=artifact_dir,
            )
        )
    elif command == "_transport-child":
        assert profile is not None
        asyncio.run(
            acceptance._transport_child(
                profile=profile,
                run_id=RUN_ID,
                spy_path=(tmp_path / f"spy-{profile}.json").resolve(),
            )
        )
    elif command in {"discovery-default", "discovery-interactive"}:
        asyncio.run(
            acceptance._discovery_command(
                command=command,
                artifact_dir=artifact_dir,
            )
        )
    elif command == "internal-matrix":
        acceptance._internal_matrix(artifact_dir=artifact_dir)
    else:
        raise AssertionError(f"unsupported test command: {command}")


@requires_contract
@pytest.mark.parametrize(
    "command,profile,interactive",
    [
        ("transport-profile", "full", False),
        ("_transport-child", "full", False),
        ("discovery-default", None, False),
        ("internal-matrix", None, False),
    ],
)
def test_bad_installed_origin_aborts_before_refresh_list_probe_or_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
    profile: str | None,
    interactive: bool,
) -> None:
    calls = _install_forbidden_acceptance_work(monkeypatch)
    runtime = _fake_release_runtime(tmp_path)
    _set_exact_acceptance_environment(
        monkeypatch,
        runtime,
        profile=profile,
        interactive=interactive,
    )
    monkeypatch.setattr(acceptance, "resolve_runtime_paths", lambda: runtime)

    def reject_bad_origin(**_kwargs):
        raise acceptance.AcceptanceError("bad installed origin")

    monkeypatch.setattr(
        acceptance,
        "_validate_current_installed_process",
        reject_bad_origin,
    )

    with pytest.raises(acceptance.AcceptanceError, match="bad installed origin"):
        _invoke_acceptance_command(
            command,
            tmp_path=tmp_path,
            profile=profile,
        )
    assert calls == {"refresh": 0, "list": 0, "probe": 0, "child": 0}


@requires_contract
@pytest.mark.parametrize(
    "command,profile,interactive,mismatch_name,mismatch_value",
    [
        ("transport-profile", "full", False, "ROOK_MCP_TOOL_PROFILE", "lean"),
        ("transport-profile", "lean", False, "ROOK_MCP_TOOL_PROFILE", "full"),
        (
            "transport-profile",
            "readonly",
            False,
            "ROOK_MCP_TOOL_PROFILE",
            "full",
        ),
        (
            "_transport-child",
            "full",
            False,
            "ROOK_TARGET",
            "hostile-target",
        ),
        (
            "discovery-default",
            None,
            False,
            "ROOK_MCP_TOOL_PROFILE",
            "readonly",
        ),
        (
            "discovery-interactive",
            "full",
            True,
            "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING",
            None,
        ),
        (
            "internal-matrix",
            None,
            False,
            "ROOK_TARGET",
            "hostile-target",
        ),
    ],
)
def test_acceptance_commands_reject_startup_environment_mismatch_before_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
    profile: str | None,
    interactive: bool,
    mismatch_name: str,
    mismatch_value: str | None,
) -> None:
    calls = _install_forbidden_acceptance_work(monkeypatch)
    runtime = _fake_release_runtime(tmp_path)
    _set_exact_acceptance_environment(
        monkeypatch,
        runtime,
        profile=profile,
        interactive=interactive,
    )
    if mismatch_value is None:
        monkeypatch.delenv(mismatch_name)
    else:
        monkeypatch.setenv(mismatch_name, mismatch_value)
    monkeypatch.setattr(acceptance, "resolve_runtime_paths", lambda: runtime)

    with pytest.raises(acceptance.AcceptanceError, match="environment"):
        _invoke_acceptance_command(
            command,
            tmp_path=tmp_path,
            profile=profile,
        )
    assert calls == {"refresh": 0, "list": 0, "probe": 0, "child": 0}


@requires_contract
def test_installed_origin_and_source_free_evidence_validation(
    tmp_path: Path,
) -> None:
    install_root = tmp_path / "fixture-install" / "app"
    source_root = tmp_path / "development" / "mcp_server" / "src"
    source_root.mkdir(parents=True)
    evidence = _process_evidence(install_root)

    acceptance._validate_process_evidence(
        evidence,
        expected_install_root=install_root,
        forbidden_source_roots=(source_root,),
        allowed_command_roots=(install_root.parent,),
    )

    contaminated_path = copy.deepcopy(evidence)
    contaminated_path["sys_path"].append(str(source_root.resolve()))
    with pytest.raises(acceptance.AcceptanceError, match="source"):
        acceptance._validate_process_evidence(
            contaminated_path,
            expected_install_root=install_root,
            forbidden_source_roots=(source_root,),
            allowed_command_roots=(install_root.parent,),
        )

    contaminated_origin = copy.deepcopy(evidence)
    contaminated_origin["rook_origins"]["rook.server"] = str(
        (source_root / "rook" / "server.py").resolve()
    )
    with pytest.raises(acceptance.AcceptanceError, match="origin"):
        acceptance._validate_process_evidence(
            contaminated_origin,
            expected_install_root=install_root,
            forbidden_source_roots=(source_root,),
            allowed_command_roots=(install_root.parent,),
        )

    missing_origin = copy.deepcopy(evidence)
    del missing_origin["rook_origins"]["rook.server"]
    with pytest.raises(acceptance.AcceptanceError, match="rook.server"):
        acceptance._validate_process_evidence(
            missing_origin,
            expected_install_root=install_root,
            forbidden_source_roots=(source_root,),
            allowed_command_roots=(install_root.parent,),
            required_rook_modules=("rook", "rook.server"),
        )


@requires_contract
def test_patchpoint_table_resolves_with_exact_kinds_and_descriptors() -> None:
    acceptance._assert_patchpoint_table_contract()
    resolved = acceptance._resolve_patchpoints()
    assert tuple(item.spec for item in resolved) == acceptance.PATCHPOINT_SPECS
    for item in resolved:
        assert item.owner is not None
        assert item.attribute
        assert item.descriptor is not None
        assert inspect.iscoroutinefunction(item.original) is (
            item.spec.kind == "async"
        )


@requires_contract
@pytest.mark.parametrize("identifier", [item[0] for item in PATCHPOINTS])
def test_each_missing_patchpoint_aborts_setup(
    monkeypatch: pytest.MonkeyPatch,
    identifier: str,
) -> None:
    spec = next(
        item for item in acceptance.PATCHPOINT_SPECS
        if item.identifier == identifier
    )
    resolved = acceptance._resolve_one_patchpoint(spec)
    monkeypatch.delattr(resolved.owner, resolved.attribute)

    with pytest.raises(acceptance.AcceptanceError, match=re.escape(identifier)):
        acceptance._resolve_patchpoints()


@requires_contract
@pytest.mark.parametrize("identifier", [item[0] for item in PATCHPOINTS])
def test_each_patchpoint_kind_replacement_aborts_setup(
    monkeypatch: pytest.MonkeyPatch,
    identifier: str,
) -> None:
    spec = next(
        item for item in acceptance.PATCHPOINT_SPECS
        if item.identifier == identifier
    )
    resolved = acceptance._resolve_one_patchpoint(spec)

    if spec.kind == "async":
        replacement = lambda *args, **kwargs: None
    else:
        async def replacement(*args, **kwargs):
            return None

    monkeypatch.setattr(resolved.owner, resolved.attribute, replacement)
    with pytest.raises(acceptance.AcceptanceError, match="kind"):
        acceptance._resolve_patchpoints()


@requires_contract
def test_patchpoint_table_drift_or_duplicates_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = acceptance.PATCHPOINT_SPECS

    monkeypatch.setattr(acceptance, "PATCHPOINT_SPECS", original[:-1])
    with pytest.raises(acceptance.AcceptanceError, match="patchpoint table"):
        acceptance._assert_patchpoint_table_contract()

    monkeypatch.setattr(
        acceptance,
        "PATCHPOINT_SPECS",
        original + (original[0],),
    )
    with pytest.raises(acceptance.AcceptanceError, match="patchpoint table"):
        acceptance._assert_patchpoint_table_contract()

    changed = acceptance.PatchpointSpec(
        original[0].identifier,
        "http",
        original[0].kind,
    )
    monkeypatch.setattr(
        acceptance,
        "PATCHPOINT_SPECS",
        (changed, *original[1:]),
    )
    with pytest.raises(acceptance.AcceptanceError, match="patchpoint table"):
        acceptance._assert_patchpoint_table_contract()


@requires_contract
@pytest.mark.asyncio
async def test_wrapper_factory_scoped_and_unscoped_contract() -> None:
    result = await acceptance._run_wrapper_factory_self_test()
    assert result == {
        "sync_scoped_trip": True,
        "sync_unscoped_passthrough": True,
        "async_scoped_trip": True,
        "async_unscoped_passthrough": True,
    }


@requires_contract
@pytest.mark.asyncio
async def test_every_installed_wrapper_sentinel_reports_its_declared_stage() -> None:
    async with acceptance._installed_spy_scope() as installed:
        assert installed.self_test["patchpoints"] == {
            identifier: True for identifier, _stage, _kind in PATCHPOINTS
        }
        assert installed.self_test["wrapper_factory"] == {
            "sync_scoped_trip": True,
            "sync_unscoped_passthrough": True,
            "async_scoped_trip": True,
            "async_unscoped_passthrough": True,
        }
        assert installed.counters == {stage: 0 for stage in STAGES}


class _NestedArgumentsPoison(dict):
    def __getitem__(self, key):
        if key == "arguments":
            raise AssertionError("nested arguments must not be read")
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key == "arguments":
            raise AssertionError("nested arguments must not be read")
        return super().get(key, default)


class _DirectParamsPoison:
    name = "spawn_agent"

    @property
    def arguments(self):
        raise AssertionError("direct arguments must not be read by wrapper")


@requires_contract
def test_acceptance_request_classification_reads_raw_name_before_arguments() -> None:
    direct = SimpleNamespace(params=_DirectParamsPoison())
    assert acceptance._classify_call_tool_request(direct) == (
        "direct",
        "spawn_agent",
        DispatchOrigin.PUBLIC_MCP,
    )

    progressive = SimpleNamespace(
        params=SimpleNamespace(
            name="rook_tools_call",
            arguments={
                "name": "gh_execute_intent",
                "arguments": _NestedArgumentsPoison(),
            },
        )
    )
    assert acceptance._classify_call_tool_request(progressive) == (
        "progressive",
        "gh_execute_intent",
        DispatchOrigin.PROGRESSIVE_META,
    )


@requires_contract
@pytest.mark.parametrize(
    "call_request",
    [
        SimpleNamespace(params=SimpleNamespace(name="safe_tool", arguments={})),
        SimpleNamespace(
            params=SimpleNamespace(name="rook_tools_call", arguments=None)
        ),
        SimpleNamespace(
            params=SimpleNamespace(
                name="rook_tools_call",
                arguments={"name": "safe_tool"},
            )
        ),
        SimpleNamespace(
            params=SimpleNamespace(
                name="rook_tools_call",
                arguments={"name": "spawn_agent "},
            )
        ),
        SimpleNamespace(
            params=SimpleNamespace(
                name="rook_tools_call",
                arguments=SimpleNamespace(name="spawn_agent"),
            )
        ),
    ],
)
def test_unexpected_call_tool_requests_are_harness_errors(
    call_request: object,
) -> None:
    with pytest.raises(acceptance.AcceptanceError, match="call-tool"):
        acceptance._classify_call_tool_request(call_request)


def _event(tool: str, origin: str, index: int = 1) -> dict[str, str]:
    return {
        "tool": tool,
        "disposition": (
            "retired"
            if tool in {"gh_execute_intent", "rhino_execute_intent"}
            else "suspended"
        ),
        "origin": origin,
        "timestamp": f"2026-07-16T12:34:56.{index:06d}Z",
    }


def _snapshot(
    events: list[dict[str, str]],
    *,
    pid: int = 1234,
    token: str = "a" * 32,
) -> dict[str, object]:
    return {
        "process_id": pid,
        "process_start_token": token,
        "events": events,
    }


@requires_contract
def test_ring_delta_accepts_tail_append_and_capacity_head_eviction() -> None:
    appended = _event("spawn_agent", "public_mcp")
    before = _snapshot([_event("gh_execute_intent", "public_mcp", 0)])
    after = _snapshot([*before["events"], appended])
    assert acceptance._one_event_ring_delta(
        before,
        after,
        expected_tool="spawn_agent",
        expected_origin="public_mcp",
    ) == appended

    full = [
        _event("spawn_agent", "internal_handler", index)
        for index in range(50)
    ]
    evicted_append = _event("gh_replay_recipe", "rook_agent", 51)
    before_full = _snapshot(full)
    after_full = _snapshot([*full[1:], evicted_append])
    assert acceptance._one_event_ring_delta(
        before_full,
        after_full,
        expected_tool="gh_replay_recipe",
        expected_origin="rook_agent",
    ) == evicted_append


@requires_contract
@pytest.mark.parametrize(
    "mutator,match",
    [
        (lambda before, after: after.update(process_id=999), "process"),
        (
            lambda before, after: after.update(process_start_token="b" * 32),
            "token",
        ),
        (lambda before, after: after["events"].clear(), "exactly one"),
        (
            lambda before, after: after["events"].append(
                _event("spawn_agent", "public_mcp", 2)
            ),
            "exactly one",
        ),
        (
            lambda before, after: after["events"][-1].update(tool="safe_tool"),
            "tool",
        ),
        (
            lambda before, after: after["events"][-1].update(
                origin="server_dispatch"
            ),
            "origin",
        ),
    ],
)
def test_ring_delta_rejects_identity_entry_and_payload_drift(
    mutator,
    match: str,
) -> None:
    before = _snapshot([])
    after = _snapshot([_event("spawn_agent", "public_mcp")])
    mutator(before, after)
    with pytest.raises(acceptance.AcceptanceError, match=match):
        acceptance._one_event_ring_delta(
            before,
            after,
            expected_tool="spawn_agent",
            expected_origin="public_mcp",
        )


def _spy_record(
    *,
    adapter: str = "direct",
    tool: str = "spawn_agent",
    origin: str = "public_mcp",
    index: int = 0,
) -> dict[str, object]:
    before = _snapshot([])
    after = _snapshot([_event(tool, origin)])
    stages = {stage: 0 for stage in STAGES}
    stages["recording_attempt"] = 1
    stages["format_result"] = 1
    return {
        "schema_version": 1,
        "run_id": RUN_ID,
        "process_id": 1234,
        "process_start_token": "a" * 32,
        "self_test": {
            "patchpoints": {
                identifier: True for identifier, _stage, _kind in PATCHPOINTS
            },
            "wrapper_factory": {
                "sync_scoped_trip": True,
                "sync_unscoped_passthrough": True,
                "async_scoped_trip": True,
                "async_unscoped_passthrough": True,
            },
        },
        "probe": {
            "index": index,
            "adapter": adapter,
            "tool": tool,
            "origin": origin,
            "telemetry_before": before,
            "telemetry_after": after,
            "stages": stages,
        },
    }


@requires_contract
def test_spy_record_closed_schema_and_stage_contract() -> None:
    direct = _spy_record()
    acceptance._validate_spy_record(
        direct,
        expected_run_id=RUN_ID,
        expected_index=0,
        expected_adapter="direct",
        expected_tool="spawn_agent",
        expected_origin="public_mcp",
    )

    progressive = _spy_record(
        adapter="progressive",
        tool="gh_execute_intent",
        origin="progressive_meta",
        index=1,
    )
    acceptance._validate_spy_record(
        progressive,
        expected_run_id=RUN_ID,
        expected_index=1,
        expected_adapter="progressive",
        expected_tool="gh_execute_intent",
        expected_origin="progressive_meta",
    )


@requires_contract
@pytest.mark.parametrize(
    "mutator,match",
    [
        (lambda record: record.update(extra="forbidden"), "keys"),
        (lambda record: record.update(run_id="b" * 32), "run"),
        (lambda record: record.update(process_id=999), "process"),
        (
            lambda record: record.update(process_start_token="b" * 32),
            "token",
        ),
        (
            lambda record: record["self_test"]["patchpoints"].pop(
                PATCHPOINTS[0][0]
            ),
            "patchpoint",
        ),
        (
            lambda record: record["self_test"]["wrapper_factory"].update(
                sync_scoped_trip=False
            ),
            "wrapper",
        ),
        (
            lambda record: record["probe"].update(arguments={"secret": True}),
            "keys",
        ),
        (
            lambda record: record["probe"]["stages"].update(secret_stage=1),
            "stage",
        ),
        (
            lambda record: record["probe"]["stages"].update(
                argument_access=1
            ),
            "stage",
        ),
        (
            lambda record: record["probe"]["telemetry_after"]["events"].clear(),
            "exactly one",
        ),
    ],
)
def test_spy_record_rejects_schema_self_test_stage_and_telemetry_drift(
    mutator,
    match: str,
) -> None:
    record = _spy_record()
    mutator(record)
    with pytest.raises(acceptance.AcceptanceError, match=match):
        acceptance._validate_spy_record(
            record,
            expected_run_id=RUN_ID,
            expected_index=0,
            expected_adapter="direct",
            expected_tool="spawn_agent",
            expected_origin="public_mcp",
        )


@requires_contract
def test_spy_record_never_serializes_sensitive_payload_fields() -> None:
    record = _spy_record()
    serialized = json.dumps(record, sort_keys=True)
    for forbidden in (
        '"arguments"',
        '"prompt"',
        '"content"',
        '"user"',
        '"document"',
        '"stack"',
        '"traceback"',
    ):
        assert forbidden not in serialized.casefold()


def _canonical_denial_tool_message(tool: str, call_id: str) -> dict[str, str]:
    entry = resolve_contained_identity(tool)
    assert entry is not None
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": json.dumps(
            containment_envelope(entry),
            separators=(",", ":"),
        ),
    }


@requires_contract
@pytest.mark.parametrize("adapter", ["rook_agent", "rook_chat"])
def test_primary_continuation_requires_exact_causal_denial_history(
    adapter: str,
) -> None:
    validator = getattr(
        acceptance,
        "_require_causal_denial_history",
        None,
    )
    assert callable(validator), "causal denial history validator is missing"
    validator(
        [_canonical_denial_tool_message("spawn_agent", "call-1")],
        tool="spawn_agent",
        call_id="call-1",
        adapter=adapter,
    )


@requires_contract
@pytest.mark.parametrize("adapter", ["rook_agent", "rook_chat"])
@pytest.mark.parametrize(
    "history",
    [
        [],
        [
            {
                "role": "assistant",
                "tool_call_id": "call-1",
                "content": _canonical_denial_tool_message(
                    "spawn_agent",
                    "call-1",
                )["content"],
            }
        ],
        [_canonical_denial_tool_message("spawn_agent", "wrong-call")],
        [
            {
                **_canonical_denial_tool_message("spawn_agent", "call-1"),
                "content": json.dumps(
                    containment_envelope(
                        resolve_contained_identity("spawn_agent")
                    )
                ),
            }
        ],
    ],
    ids=("count-only", "fake-role", "fake-call-id", "noncanonical-content"),
)
def test_primary_continuation_rejects_count_only_or_fake_history(
    adapter: str,
    history: list[dict[str, str]],
) -> None:
    validator = getattr(
        acceptance,
        "_require_causal_denial_history",
        None,
    )
    assert callable(validator), "causal denial history validator is missing"
    with pytest.raises(acceptance.AcceptanceError, match="causal|denial|history"):
        validator(
            history,
            tool="spawn_agent",
            call_id="call-1",
            adapter=adapter,
        )


@requires_contract
def test_internal_pair_matrix_is_exact_164_with_pinned_origins() -> None:
    pairs = acceptance._expected_internal_pairs()
    expected = {
        (seam, tool)
        for seam in ARBITRARY_SEAMS
        for tool in CONTAINED
    } | set(CONSTANT_SEAMS.items())

    assert len(pairs) == 164
    assert len({(item.seam, item.tool) for item in pairs}) == 164
    assert {(item.seam, item.tool) for item in pairs} == expected

    by_seam = {item.seam: item.origin for item in pairs}
    assert by_seam["server._call_tool_dispatch"] == "server_dispatch"
    assert by_seam["ToolDispatcher.dispatch"] == "tool_dispatcher"
    assert by_seam["RookAgent._run_loop"] == "rook_agent"
    assert by_seam["ChatRunner.run_turn"] == "rook_chat"
    assert (
        by_seam["rook.agent.plan_graph_live.apply_live_producer_node"]
        == "plan_graph"
    )
    assert (
        by_seam["bootstrap.HttpExecutor.execute"] == "internal_handler"
    )

    acceptance._validate_internal_pair_set(pairs)
    with pytest.raises(acceptance.AcceptanceError, match="internal seam"):
        acceptance._validate_internal_pair_set(pairs[:-1])
    with pytest.raises(acceptance.AcceptanceError, match="internal seam"):
        acceptance._validate_internal_pair_set([*pairs, pairs[0]])
    unexpected = acceptance.InternalProbeSpec(
        seam="unexpected.extra.seam",
        tool="spawn_agent",
        origin="internal_handler",
        adapter="unexpected",
    )
    with pytest.raises(acceptance.AcceptanceError, match="internal seam"):
        acceptance._validate_internal_pair_set([*pairs[:-1], unexpected])


@requires_contract
@pytest.mark.parametrize("tool", CONTAINED)
def test_expected_denial_payload_is_exact(tool: str) -> None:
    entry = resolve_contained_identity(tool)
    assert entry is not None
    expected = containment_envelope(entry)
    acceptance._validate_denial_result(tool, expected)

    malformed = copy.deepcopy(expected)
    malformed["data"]["retryable"] = True
    with pytest.raises(acceptance.AcceptanceError, match="result"):
        acceptance._validate_denial_result(tool, malformed)


def _catalog(
    count: int,
    *,
    include_contained: bool = False,
) -> dict[str, object]:
    tools = [
        {
            "name": f"safe_tool_{index:03d}",
            "description": f"safe {index}",
            "inputSchema": {"type": "object", "properties": {}},
        }
        for index in range(count)
    ]
    if include_contained:
        tools[0]["name"] = "spawn_agent"
    return {"count": count, "tools": tools}


@requires_contract
@pytest.mark.parametrize(
    "profile,count",
    [("full", 422), ("lean", 20), ("readonly", 148)],
)
def test_profile_catalog_contract(profile: str, count: int) -> None:
    catalog = _catalog(count)
    acceptance._validate_catalog(
        catalog,
        expected_count=count,
        profile=profile,
    )

    drift = _catalog(count - 1)
    with pytest.raises(acceptance.AcceptanceError, match="count"):
        acceptance._validate_catalog(
            drift,
            expected_count=count,
            profile=profile,
        )

    contaminated = _catalog(count, include_contained=True)
    with pytest.raises(acceptance.AcceptanceError, match="contained"):
        acceptance._validate_catalog(
            contaminated,
            expected_count=count,
            profile=profile,
        )


@requires_contract
def test_discovery_default_and_interactive_contracts() -> None:
    before = _snapshot([])
    after = copy.deepcopy(before)

    acceptance._validate_discovery_contract(
        command="discovery-default",
        profile_env_present=False,
        interactive_env_present=False,
        catalog=_catalog(422),
        telemetry_before=before,
        telemetry_after=after,
    )
    acceptance._validate_discovery_contract(
        command="discovery-interactive",
        profile_env_present=True,
        interactive_env_present=True,
        catalog=_catalog(425),
        telemetry_before=before,
        telemetry_after=after,
    )

    with pytest.raises(acceptance.AcceptanceError, match="absent"):
        acceptance._validate_discovery_contract(
            command="discovery-default",
            profile_env_present=True,
            interactive_env_present=False,
            catalog=_catalog(422),
            telemetry_before=before,
            telemetry_after=after,
        )
    with pytest.raises(acceptance.AcceptanceError, match="telemetry"):
        acceptance._validate_discovery_contract(
            command="discovery-interactive",
            profile_env_present=True,
            interactive_env_present=True,
            catalog=_catalog(425),
            telemetry_before=before,
            telemetry_after=_snapshot(
                [_event("spawn_agent", "internal_handler")]
            ),
        )


@requires_contract
def test_atomic_canonical_json_replaces_complete_artifact(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "artifact.json"
    first = {"z": 1, "a": [3, 2, 1]}
    second = {"schema_version": 1, "complete": True}

    acceptance._atomic_write_json(target, first)
    first_bytes = target.read_bytes()
    assert first_bytes == (
        json.dumps(
            first,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))

    acceptance._atomic_write_json(target, second)
    second_bytes = target.read_bytes()
    assert json.loads(second_bytes) == second
    assert second_bytes != first_bytes
    assert acceptance._sha256_file(target) == hashlib.sha256(
        second_bytes
    ).hexdigest()
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


@requires_contract
def test_model_projection_evidence_omits_all_contained_names() -> None:
    evidence = acceptance._collect_model_projection_evidence()
    assert set(evidence) == {"rook_agent", "rook_chat"}
    for consumer, record in evidence.items():
        assert set(record) == {"count", "names"}
        assert record["count"] == len(record["names"])
        assert set(CONTAINED).isdisjoint(record["names"]), consumer


def _managed_dependency_site() -> Path | None:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return None
    candidate = (
        Path(local_appdata)
        / "Rook"
        / "venv"
        / "Lib"
        / "site-packages"
    )
    return candidate if candidate.is_dir() else None


@pytest.fixture(scope="session")
def synthetic_installed_runtime(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, Any]:
    if acceptance is None:
        raise RuntimeError(
            "Task 7 installed fixture infrastructure missing: "
            "rook.containment_acceptance could not be imported"
        )
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        raise RuntimeError(
            "Task 7 installed fixture infrastructure missing: "
            "LOCALAPPDATA is unset"
        )
    dependency_site = _managed_dependency_site()
    if dependency_site is None:
        expected_site = (
            Path(local_appdata)
            / "Rook"
            / "venv"
            / "Lib"
            / "site-packages"
        )
        raise RuntimeError(
            "Task 7 installed fixture dependency site is missing: "
            f"{expected_site}"
        )
    dependency_python = (
        dependency_site.parents[1] / "Scripts" / "python.exe"
    )
    if not dependency_python.is_file():
        raise RuntimeError(
            "Task 7 installed fixture interpreter is missing: "
            f"{dependency_python}"
        )

    root = tmp_path_factory.mktemp("t7-installed")
    install_root = root / "app"
    data_root = root / "data"
    dspy_cache = data_root / "dspy-cache"
    package_src = install_root / "mcp_server" / "src"
    artifact_root = root / "artifacts"
    run_root = root / "run"
    venv_root = root / "fixture-venv"
    for path in (
        package_src,
        data_root,
        dspy_cache,
        artifact_root,
        run_root,
    ):
        path.mkdir(parents=True, exist_ok=True)

    source_package = Path(importlib.import_module("rook").__file__).parent
    shutil.copytree(
        source_package,
        package_src / "rook",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    completed = subprocess.run(
        [
            str(dependency_python),
            "-m",
            "venv",
            "--without-pip",
            str(venv_root),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, (
        completed.stdout + "\n" + completed.stderr
    )
    python = venv_root / "Scripts" / "python.exe"
    fixture_site = venv_root / "Lib" / "site-packages"
    fixture_site.mkdir(parents=True, exist_ok=True)
    (fixture_site / "rook-t7-fixture.pth").write_text(
        "\n".join(
            [
                str(package_src.resolve()),
                (
                    "import site; site.addsitedir("
                    f"{str(dependency_site.resolve())!r})"
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )

    version_probe = subprocess.run(
        [
            str(python),
            "-c",
            (
                "import sys; "
                "print(f'Python{sys.version_info.major}{sys.version_info.minor}')"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert version_probe.returncode == 0, version_probe.stderr
    user_site = (
        root
        / "hostile-user-base"
        / version_probe.stdout.strip()
        / "site-packages"
    )
    user_site.mkdir(parents=True, exist_ok=True)
    tripwire_code = (
        "from pathlib import Path; "
        "Path(__file__).with_suffix('.hit').write_text("
        "'executed', encoding='ascii')"
    )
    for filename in ("sitecustomize.py", "usercustomize.py"):
        (user_site / filename).write_text(tripwire_code, encoding="utf-8")

    hostile_environment = {
        "PyThOnPaTh": str(source_package.parent.resolve()),
        "pYtHoNhOmE": str((root / "hostile-python-home").resolve()),
        "PyThOnUsErBaSe": str(user_site.parents[1].resolve()),
        "pYtHoNnOuSeRsItE": "0",
        "DSPY_MODEL": "hostile/model",
        "dspy_cachedir": str(source_package.resolve()),
        "CHIRP_HOME": str(source_package.resolve()),
        "ROOK_INSTALL_ROOT": str(source_package.resolve()),
        "rook_data_dir": str(source_package.resolve()),
        "Rook_mode": "dev",
        "ROOK_DSPY_RESTRICT_PICKLE": "0",
        "ROOK_MCP_TOOL_PROFILE": "readonly",
        "rook_enable_interactive_command_learning": "1",
        "ROOK_TARGET": "hostile-target",
        "ROOK_PROCESS_ID": "123",
        "ROOK_DOCUMENT_ID": "secret-doc",
        "ROOK_RHINO_PORT": "9999",
        "ROOK_RHINO_EXECUTABLE": "C:/Rhino.exe",
        "ROOK_BRIDGE_OVERRIDE": "unsafe",
        "ROOK_HARNESS_MODE": "unsafe",
        "ROOK_MODEL": "unsafe-model",
    }

    return {
        "root": root,
        "python": python,
        "install_root": install_root,
        "data_root": data_root,
        "dspy_cache": dspy_cache,
        "artifact_root": artifact_root,
        "run_root": run_root,
        "source_package": source_package,
        "dependency_site": dependency_site,
        "hostile_environment": hostile_environment,
        "sitecustomize_marker": user_site / "sitecustomize.hit",
        "usercustomize_marker": user_site / "usercustomize.hit",
    }


@pytest.mark.parametrize(
    "scenario,expected_fragment",
    [
        ("acceptance-missing", "rook.containment_acceptance"),
        ("localappdata-unset", "LOCALAPPDATA"),
        ("dependency-site-missing", "site-packages"),
        ("interpreter-missing", "python.exe"),
    ],
)
def test_installed_fixture_missing_infrastructure_is_a_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
    expected_fragment: str,
) -> None:
    module = sys.modules[__name__]
    if scenario == "acceptance-missing":
        monkeypatch.setattr(module, "acceptance", None)
    elif scenario == "localappdata-unset":
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
    else:
        local_appdata = tmp_path / "LocalAppData"
        monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
        if scenario == "interpreter-missing":
            (
                local_appdata
                / "Rook"
                / "venv"
                / "Lib"
                / "site-packages"
            ).mkdir(parents=True)

    fixture_body = synthetic_installed_runtime.__wrapped__
    unused_factory = SimpleNamespace(
        mktemp=lambda _name: pytest.fail(
            "fixture allocated temp state before dependency validation"
        )
    )
    try:
        fixture_body(unused_factory)
    except BaseException as exc:
        assert isinstance(exc, RuntimeError), (
            f"missing infrastructure must raise RuntimeError, got {type(exc)!r}"
        )
        assert expected_fragment.casefold() in str(exc).casefold()
    else:
        pytest.fail("missing installed fixture infrastructure was accepted")


def test_installed_fixture_contains_no_pytest_skip_path() -> None:
    fixture_source = inspect.getsource(
        synthetic_installed_runtime.__wrapped__
    )
    assert "pytest.skip" not in fixture_source


def _installed_command_environment(
    runtime: dict[str, Any],
    *,
    profile: str | None = None,
    interactive: bool = False,
) -> dict[str, str]:
    assert acceptance is not None
    inherited = {
        **os.environ,
        **runtime["hostile_environment"],
    }
    return acceptance._sanitized_child_environment(
        inherited,
        install_root=runtime["install_root"],
        data_root=runtime["data_root"],
        dspy_cache=runtime["dspy_cache"],
        profile=profile,
        interactive=interactive,
    )


def _run_installed_command(
    runtime: dict[str, Any],
    *args: str,
    profile: str | None = None,
    interactive: bool = False,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(runtime["python"]),
            "-m",
            "rook.containment_acceptance",
            *args,
        ],
        cwd=runtime["run_root"],
        env=_installed_command_environment(
            runtime,
            profile=profile,
            interactive=interactive,
        ),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _expected_installed_environment(
    runtime: dict[str, Any],
    *,
    profile: str | None = None,
    interactive: bool = False,
) -> dict[str, str]:
    expected = {
        "PYTHONNOUSERSITE": "1",
        "DSPY_CACHEDIR": str(runtime["dspy_cache"].resolve()),
        "ROOK_INSTALL_ROOT": str(runtime["install_root"].resolve()),
        "ROOK_DATA_DIR": str(runtime["data_root"].resolve()),
        "ROOK_MODE": "release",
        "ROOK_DSPY_RESTRICT_PICKLE": "1",
    }
    if profile is not None:
        expected["ROOK_MCP_TOOL_PROFILE"] = profile
    if interactive:
        expected["ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING"] = "1"
    return expected


def _assert_exact_installed_environment(
    actual: object,
    runtime: dict[str, Any],
    *,
    profile: str | None = None,
    interactive: bool = False,
) -> None:
    assert isinstance(actual, dict)
    assert actual == _expected_installed_environment(
        runtime,
        profile=profile,
        interactive=interactive,
    )


def _assert_hostile_startup_markers_absent(runtime: dict[str, Any]) -> None:
    assert not runtime["sitecustomize_marker"].exists()
    assert not runtime["usercustomize_marker"].exists()


@requires_contract
@pytest.mark.parametrize(
    "profile,expected_count",
    [("full", 422), ("lean", 20), ("readonly", 148)],
)
def test_private_child_runs_true_stdio_transport_end_to_end(
    synthetic_installed_runtime: dict[str, Any],
    profile: str,
    expected_count: int,
) -> None:
    runtime = synthetic_installed_runtime
    artifact_dir = runtime["artifact_root"] / f"transport-{profile}"
    completed = _run_installed_command(
        runtime,
        "transport-profile",
        "--profile",
        profile,
        "--artifact-dir",
        str(artifact_dir),
        profile=profile,
    )
    assert completed.returncode == 0, (
        completed.stdout + "\n" + completed.stderr
    )

    artifact_path = artifact_dir / f"transport-{profile}.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    run_id = artifact.get("run_id")
    assert type(run_id) is str and re.fullmatch(r"[0-9a-f]{32}", run_id)
    _assert_exact_installed_environment(
        artifact["process"]["environment"],
        runtime,
        profile=profile,
    )
    _assert_exact_installed_environment(
        artifact.get("child_environment"),
        runtime,
        profile=profile,
    )
    _assert_hostile_startup_markers_absent(runtime)
    acceptance._validate_transport_artifact(
        artifact,
        expected_profile=profile,
        expected_count=expected_count,
        expected_install_root=runtime["install_root"],
        expected_data_root=runtime["data_root"],
        expected_dspy_cache=runtime["dspy_cache"],
        forbidden_source_roots=(runtime["source_package"],),
        allowed_command_roots=(runtime["root"],),
    )
    assert len(artifact["probes"]) == 12
    assert [
        (probe["adapter"], probe["tool"])
        for probe in artifact["probes"]
    ] == [
        *[("direct", tool) for tool in CONTAINED],
        *[("progressive", tool) for tool in CONTAINED],
    ]
    assert {
        probe["spy"]["process_id"] for probe in artifact["probes"]
    } == {artifact["child_process_id"]}
    assert {
        probe["spy"]["run_id"] for probe in artifact["probes"]
    } == {run_id}
    assert artifact["final_spy_sha256"] == acceptance._sha256_file(
        Path(artifact["final_spy_path"])
    )
    assert all(
        probe["transport"] == {
            "content_count": 1,
            "content_types": ["text"],
            "is_error": False,
        }
        for probe in artifact["probes"]
    )

    mismatched_run = copy.deepcopy(artifact)
    mismatched_run["probes"][0]["spy"]["run_id"] = (
        "a" * 32 if run_id != "a" * 32 else "b" * 32
    )
    with pytest.raises(acceptance.AcceptanceError, match="run"):
        acceptance._validate_transport_artifact(
            mismatched_run,
            expected_profile=profile,
            expected_count=expected_count,
            expected_install_root=runtime["install_root"],
            expected_data_root=runtime["data_root"],
            expected_dspy_cache=runtime["dspy_cache"],
            forbidden_source_roots=(runtime["source_package"],),
            allowed_command_roots=(runtime["root"],),
        )

    for environment_key in ("process", "child_environment"):
        hostile = copy.deepcopy(artifact)
        environment = (
            hostile[environment_key]["environment"]
            if environment_key == "process"
            else hostile[environment_key]
        )
        environment["ROOK_TARGET"] = "late-hostile-target"
        with pytest.raises(acceptance.AcceptanceError, match="environment"):
            acceptance._validate_transport_artifact(
                hostile,
                expected_profile=profile,
                expected_count=expected_count,
                expected_install_root=runtime["install_root"],
                expected_data_root=runtime["data_root"],
                expected_dspy_cache=runtime["dspy_cache"],
                forbidden_source_roots=(runtime["source_package"],),
                allowed_command_roots=(runtime["root"],),
            )


@requires_contract
def test_discovery_commands_run_in_isolated_installed_children(
    synthetic_installed_runtime: dict[str, Any],
) -> None:
    runtime = synthetic_installed_runtime
    for command, expected_count in (
        ("discovery-default", 422),
        ("discovery-interactive", 425),
    ):
        artifact_dir = runtime["artifact_root"] / command
        interactive = command == "discovery-interactive"
        profile = "full" if interactive else None
        completed = _run_installed_command(
            runtime,
            command,
            "--artifact-dir",
            str(artifact_dir),
            profile=profile,
            interactive=interactive,
        )
        assert completed.returncode == 0, (
            completed.stdout + "\n" + completed.stderr
        )
        artifact = json.loads(
            (artifact_dir / f"{command}.json").read_text(encoding="utf-8")
        )
        _assert_exact_installed_environment(
            artifact["process"]["environment"],
            runtime,
            profile=profile,
            interactive=interactive,
        )
        _assert_hostile_startup_markers_absent(runtime)
        acceptance._validate_discovery_artifact(
            artifact,
            expected_command=command,
            expected_count=expected_count,
            expected_install_root=runtime["install_root"],
            expected_data_root=runtime["data_root"],
            expected_dspy_cache=runtime["dspy_cache"],
            forbidden_source_roots=(runtime["source_package"],),
            allowed_command_roots=(runtime["root"],),
        )
        hostile = copy.deepcopy(artifact)
        hostile["process"]["environment"]["ROOK_TARGET"] = (
            "late-hostile-target"
        )
        with pytest.raises(acceptance.AcceptanceError, match="environment"):
            acceptance._validate_discovery_artifact(
                hostile,
                expected_command=command,
                expected_count=expected_count,
                expected_install_root=runtime["install_root"],
                expected_data_root=runtime["data_root"],
                expected_dspy_cache=runtime["dspy_cache"],
                forbidden_source_roots=(runtime["source_package"],),
                allowed_command_roots=(runtime["root"],),
            )


@requires_contract
def test_internal_matrix_runs_exact_164_installed_seams(
    synthetic_installed_runtime: dict[str, Any],
) -> None:
    runtime = synthetic_installed_runtime
    artifact_dir = runtime["artifact_root"] / "internal-matrix"
    completed = _run_installed_command(
        runtime,
        "internal-matrix",
        "--artifact-dir",
        str(artifact_dir),
        timeout=240,
    )
    assert completed.returncode == 0, (
        completed.stdout + "\n" + completed.stderr
    )
    artifact = json.loads(
        (artifact_dir / "internal-matrix.json").read_text(encoding="utf-8")
    )
    _assert_exact_installed_environment(
        artifact["process"]["environment"],
        runtime,
    )
    _assert_hostile_startup_markers_absent(runtime)
    acceptance._validate_internal_artifact(
        artifact,
        expected_install_root=runtime["install_root"],
        expected_data_root=runtime["data_root"],
        expected_dspy_cache=runtime["dspy_cache"],
        forbidden_source_roots=(runtime["source_package"],),
        allowed_command_roots=(runtime["root"],),
    )
    assert len(artifact["probes"]) == 164
    assert {
        (probe["seam"], probe["tool"]) for probe in artifact["probes"]
    } == {
        (item.seam, item.tool)
        for item in acceptance._expected_internal_pairs()
    }
    assert all(
        probe["primary_model_calls"]
        == (
            2
            if probe["seam"]
            in {"RookAgent._run_loop", "ChatRunner.run_turn"}
            else 0
        )
        for probe in artifact["probes"]
    )
    hostile = copy.deepcopy(artifact)
    hostile["process"]["environment"]["ROOK_TARGET"] = "late-hostile-target"
    with pytest.raises(acceptance.AcceptanceError, match="environment"):
        acceptance._validate_internal_artifact(
            hostile,
            expected_install_root=runtime["install_root"],
            expected_data_root=runtime["data_root"],
            expected_dspy_cache=runtime["dspy_cache"],
            forbidden_source_roots=(runtime["source_package"],),
            allowed_command_roots=(runtime["root"],),
        )


@requires_contract
def test_acceptance_cli_is_not_model_or_mcp_visible() -> None:
    from rook import server

    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert "containment_acceptance" not in names
    assert not any("acceptance" in name for name in names)
    assert not hasattr(server, "containment_acceptance")
