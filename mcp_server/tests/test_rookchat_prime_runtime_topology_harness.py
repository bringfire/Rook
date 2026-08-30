from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from rook.agent.chat import prime_runtime_contract


SCRIPT = Path(__file__).parents[2] / "scripts" / "rookchat_prime_runtime_topology_harness.py"


class _FakeStdin:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakePopen:
    def __init__(self, *, pid: int = 701) -> None:
        self.pid = pid
        self.returncode = None
        self.stdin = _FakeStdin()
        self.stdout = None
        self.stderr = None
        self.wait_calls = 0
        self.terminate_calls = 0
        self.kill_calls = 0

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls += 1
        self.returncode = 0
        return 0

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1


def _load():
    spec = importlib.util.spec_from_file_location(
        "rookchat_prime_runtime_topology_harness",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_harness_exposes_only_the_two_reviewed_entry_points() -> None:
    harness = _load()

    parser = harness.build_parser()
    assert harness.entry_point_names(parser) == ("direct-vertical", "lease-sequence")


def test_child_environment_is_closed_credential_free_and_uv_first(tmp_path: Path) -> None:
    harness = _load()
    uv = tmp_path / "uv-bin" / "uv.exe"
    uv.parent.mkdir()
    uv.write_bytes(b"uv")
    roots = harness.HarnessRoots.create(tmp_path / "run")
    base = {
        "SystemRoot": "C:/Windows",
        "WINDIR": "C:/Windows",
        "ComSpec": "C:/Windows/System32/cmd.exe",
        "PATHEXT": ".COM;.EXE",
        "TEMP": str(tmp_path / "temp"),
        "TMP": str(tmp_path / "temp"),
        "USERPROFILE": str(tmp_path / "user"),
        "LOCALAPPDATA": str(tmp_path / "local"),
        "APPDATA": str(tmp_path / "roaming"),
        "OPENAI_API_KEY": "secret",
        "SERPER_API_KEY": "secret",
        "PRIME_AGENT_INTERNAL_SESSION_LEASES": "1",
        "PRIME_AGENT_INTERNAL_SESSION_LEASE_OWNER_ID": "external-owner",
        "ROOK_UNRELATED": "ambient",
    }

    environment = harness.build_child_environment(
        base,
        roots=roots,
        uv_path=uv,
        support_path_entries=(Path("C:/Windows/System32"),),
    )

    assert environment["PATH"].split(";")[0] == str(uv.parent.resolve())
    assert environment["PRIME_AGENT_CODING_AGENT_DIR"] == str(roots.agent)
    assert environment["PRIME_AGENT_SESSION_DIR"] == str(roots.sessions)
    assert environment["PRIME_AGENT_KERNEL_VENV"] == str(roots.kernel)
    assert environment["PRIME_AGENT_INSTALL_UV"] == "0"
    assert environment["XDG_DATA_HOME"] == str(roots.data)
    assert "OPENAI_API_KEY" not in environment
    assert "SERPER_API_KEY" not in environment
    assert "PRIME_AGENT_INTERNAL_SESSION_LEASES" not in environment
    assert "PRIME_AGENT_INTERNAL_SESSION_LEASE_OWNER_ID" not in environment
    assert "ROOK_UNRELATED" not in environment


def test_prime_argv_is_exact_offline_direct_and_resume_is_literal(tmp_path: Path) -> None:
    harness = _load()
    session_root = (tmp_path / "sessions").resolve()
    session_root.mkdir()
    session_file = session_root / "session.jsonl"
    session_file.write_text("", encoding="utf-8")
    goal = (tmp_path / "goal" / "SKILL.md").resolve()
    rook = (tmp_path / "rook-full" / "SKILL.md").resolve()

    argv = harness.build_prime_argv(
        node_path=Path("D:/prime/node.exe"),
        cli_path=Path("D:/prime/dist/bundle/cli.js"),
        session_root=session_root,
        model_selector="offline/catalog-model",
        goal_skill_path=goal,
        rook_skill_path=rook,
        resume_session_file=session_file,
    )

    assert argv == (
        str(Path("D:/prime/node.exe")),
        str(Path("D:/prime/dist/bundle/cli.js")),
        "--mode",
        "rpc",
        "--rpc-runtime",
        "in-process",
        "--offline",
        "--model",
        "offline/catalog-model",
        "--tools",
        "ipython",
        "--no-extensions",
        "--no-skills",
        "--skill",
        str(goal),
        "--skill",
        str(rook),
        "--no-context-files",
        "--no-prompt-templates",
        "--session-dir",
        str(session_root),
        "--resume",
        str(session_file),
    )
    assert "--api-key" not in argv


def test_session_file_must_be_the_exact_existing_file_beneath_root(tmp_path: Path) -> None:
    harness = _load()
    root = (tmp_path / "sessions").resolve()
    root.mkdir()
    session = root / "saved.jsonl"
    session.write_text("", encoding="utf-8")

    assert harness.admit_session_file(root, str(session)) == session.resolve()
    with pytest.raises(harness.HarnessFailure, match="sessionFile"):
        harness.admit_session_file(root, str(tmp_path / "outside.jsonl"))
    with pytest.raises(harness.HarnessFailure, match="sessionFile"):
        harness.admit_session_file(root, str(root / "missing.jsonl"))


def test_session_file_is_admitted_only_after_prime_flushes_it(tmp_path: Path) -> None:
    harness = _load()
    root = (tmp_path / "sessions").resolve()
    root.mkdir()
    session = root / "saved.jsonl"
    calls = []

    class Child:
        def command(self, command, _timeout):
            calls.append(command["type"])
            if command["type"] == "get_state":
                return {
                    "type": "response",
                    "id": command["id"],
                    "success": True,
                    "command": "get_state",
                    "data": {
                        "sessionFile": str(session),
                        "sessionId": "persisted-session-id",
                    },
                }
            session.write_text("persisted\n", encoding="utf-8")
            return {
                "type": "response",
                "id": command["id"],
                "success": True,
                "command": "set_rlm_max_depth",
                "data": {"maxDepth": 0, "source": "chat"},
            }

    state, depth, admitted = harness.persist_session_file(Child(), root)

    assert calls == ["get_state", "set_rlm_max_depth"]
    assert state["sessionFile"] == str(session)
    assert depth == {"maxDepth": 0, "source": "chat"}
    assert admitted == {
        "sessionId": "persisted-session-id",
        "sessionFile": str(session.resolve()),
    }


def test_isolated_agent_root_refuses_daemon_artifacts(tmp_path: Path) -> None:
    harness = _load()
    agent = tmp_path / "agent"
    (agent / "logs").mkdir(parents=True)

    harness.require_no_daemon_artifacts(agent)

    (agent / "daemon-workers").mkdir()
    with pytest.raises(harness.HarnessFailure, match="daemon artifact"):
        harness.require_no_daemon_artifacts(agent)

    (agent / "daemon-workers").rmdir()
    (agent / "logs" / "prime-agent-daemon.test.log").write_text("started", encoding="utf-8")
    with pytest.raises(harness.HarnessFailure, match="daemon artifact"):
        harness.require_no_daemon_artifacts(agent)

    (agent / "logs" / "prime-agent-daemon.test.log").unlink()
    (agent / "daemon-update-restart.json").write_text("{}", encoding="utf-8")
    with pytest.raises(harness.HarnessFailure, match="daemon artifact"):
        harness.require_no_daemon_artifacts(agent)


def test_harness_has_no_continuous_process_monitor() -> None:
    harness = _load()

    assert not hasattr(harness, "ProcessMonitor")


def test_harness_defaults_creation_flags_to_zero_off_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(subprocess, "CREATE_NO_WINDOW", raising=False)

    harness = _load()

    assert harness.CREATE_NO_WINDOW == 0


def test_lease_sequence_is_finite_uses_one_session_and_settles_every_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _load()
    roots = harness.HarnessRoots.create(tmp_path / "run")
    session = roots.sessions / "saved.jsonl"
    resumes = []
    children = []
    sleeps = []

    class Process:
        def __init__(self, generation: int) -> None:
            self.pid = 700 + generation
            self.returncode = None

        def wait(self, timeout=None) -> int:
            assert self.returncode is not None
            return self.returncode

    class Child:
        def __init__(self, generation: int, resume: Path | None) -> None:
            self.generation = generation
            self.resume = resume
            self.argv = ("node.exe", "cli.js") + (("--resume", str(resume)) if resume else ())
            self.process = Process(generation)
            self.rows = []
            self.stderr = []
            self.close_record = None

        def start(self) -> None:
            pass

        def command(self, command, _timeout):
            if self.generation == 2:
                self.process.returncode = 12
                self.stderr.append(
                    json.dumps(
                        {
                            "type": "rpc_startup_error",
                            "code": "session_already_active",
                            "sessionPath": str(session.resolve()),
                        }
                    )
                )
                raise harness.HarnessFailure("lease refused")
            command_type = command["type"]
            if command_type == "set_rlm_max_depth":
                session.write_text("persisted\n", encoding="utf-8")
                data = {"maxDepth": 0, "source": "chat"}
            else:
                data = {
                    "sessionFile": str(session),
                    "sessionId": "original-session-id",
                }
            response = {
                "type": "response",
                "id": command["id"],
                "success": True,
                "command": command_type,
                "data": data,
            }
            self.rows.append(response)
            return response

        def close(self):
            if self.close_record is None:
                if self.process.returncode is None:
                    self.process.returncode = 0
                self.close_record = {
                    "result": "already_exited" if self.process.returncode else "graceful",
                    "returnCode": self.process.returncode,
                }
            return dict(self.close_record)

    def launch(_config, _environment, generation, resume):
        resumes.append(resume)
        child = Child(generation, resume)
        children.append(child)
        return child

    monkeypatch.setattr(harness, "_build_runtime_environment", lambda _config: {})
    monkeypatch.setattr(harness, "_launch", launch)
    monkeypatch.setattr(harness.time, "sleep", lambda seconds: sleeps.append(seconds))
    config = SimpleNamespace(entry_point="lease-sequence", roots=roots)

    result = harness.run_lease_sequence(config)

    assert resumes == [
        None,
        session.resolve(),
        session.resolve(),
    ]
    assert [record["phase"] for record in result["records"]] == [
        "first_session_persisted",
        "live_owner_refusal",
        "first_close",
        "graceful_reopen_close",
    ]
    assert sleeps == []
    assert all(child.process.returncode is not None for child in children)
    assert all(child.close_record is not None for child in children)


def test_lease_sequence_revalidates_bundle_before_reopen_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _load()
    roots = harness.HarnessRoots.create(tmp_path / "run")
    node = tmp_path / "node.exe"
    uv = tmp_path / "uv.exe"
    node.write_bytes(b"node")
    uv.write_bytes(b"uv")
    dist = tmp_path / "dist"
    (dist / "bundle").mkdir(parents=True)
    (dist / "skills").mkdir()
    cli = dist / "bundle" / "cli.js"
    cli.write_text("export {};\n", encoding="utf-8")
    bundle_manifest = tmp_path / "prime-bundle-manifest.json"
    bundle = prime_runtime_contract.write_prime_bundle_manifest(dist, bundle_manifest)

    def stage(name: str):
        source = tmp_path / f"{name}-source"
        (source / "src" / name.replace("-", "_")).mkdir(parents=True)
        (source / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
        (source / "pyproject.toml").write_text(
            f"[project]\nname='{name}'\nversion='0.0.0'\n",
            encoding="utf-8",
        )
        return harness.stage_skill_package(source / "SKILL.md", roots.packages / name)

    goal = stage("goal")
    rook = stage("rook-full")
    config = harness.HarnessConfiguration(
        entry_point="lease-sequence",
        roots=roots,
        node_path=node.resolve(),
        node_sha256=hashlib.sha256(b"node").hexdigest().upper(),
        prime_dist_root=dist.resolve(),
        bundle_manifest_path=bundle_manifest.resolve(),
        bundle_manifest_sha256=bundle.manifest_sha256,
        uv_path=uv.resolve(),
        uv_sha256=hashlib.sha256(b"uv").hexdigest().upper(),
        model_selector="offline/catalog-model",
        goal_skill_path=goal.skill_path,
        rook_skill_path=rook.skill_path,
        goal_skill_manifest_sha256=goal.manifest_sha256,
        rook_skill_manifest_sha256=rook.manifest_sha256,
    )
    session = roots.sessions / "saved.jsonl"
    starts: list[int] = []

    class Process:
        def __init__(self, generation: int) -> None:
            self.pid = 900 + generation
            self.returncode = None

    class Child:
        def __init__(self, *, argv, environment, cwd, generation) -> None:
            self.argv = argv
            self.environment = environment
            self.cwd = cwd
            self.generation = generation
            self.process = Process(generation)
            self.rows = []
            self.stderr = []
            self.close_record = None

        def start(self) -> None:
            starts.append(self.generation)

        def command(self, command, _timeout):
            if self.generation == 2:
                self.process.returncode = 12
                self.stderr.append(
                    json.dumps(
                        {
                            "type": "rpc_startup_error",
                            "code": "session_already_active",
                            "sessionPath": str(session.resolve()),
                        }
                    )
                )
                raise harness.HarnessFailure("lease refused")
            if command["type"] == "set_rlm_max_depth":
                session.write_text("persisted\n", encoding="utf-8")
                data = {"maxDepth": 0, "source": "chat"}
            else:
                data = {"sessionFile": str(session), "sessionId": "original-session-id"}
            response = {
                "type": "response",
                "id": command["id"],
                "success": True,
                "command": command["type"],
                "data": data,
            }
            self.rows.append(response)
            return response

        def close(self):
            if self.close_record is None:
                if self.generation == 1:
                    cli.write_text("export const drift = true;\n", encoding="utf-8")
                if self.process.returncode is None:
                    self.process.returncode = 0
                self.close_record = {
                    "result": "already_exited" if self.process.returncode else "graceful",
                    "returnCode": self.process.returncode,
                }
            return dict(self.close_record)

    monkeypatch.setattr(harness, "OwnedPrimeProcess", Child)
    monkeypatch.setattr(harness, "_build_runtime_environment", lambda _config: {})

    with pytest.raises(harness.HarnessFailure, match="Prime bundle manifest"):
        harness.run_lease_sequence(config)

    assert starts == [1, 2]


def test_lease_refusal_requires_exact_code_and_canonical_session(tmp_path: Path) -> None:
    harness = _load()
    session = (tmp_path / "session.jsonl").resolve()
    session.write_text("persisted\n", encoding="utf-8")

    class Child:
        generation = 2
        process = SimpleNamespace(returncode=12)

        def __init__(
            self,
            row: dict[str, object],
            close_record: dict[str, object] | None = None,
        ) -> None:
            self.stderr = [json.dumps(row)]
            self.close_record = close_record or {
                "result": "already_exited",
                "returnCode": 12,
            }

        def command(self, _command, _timeout):
            raise harness.HarnessFailure("startup refused")

        def close(self):
            return dict(self.close_record)

    accepted = Child(
        {
            "type": "rpc_startup_error",
            "code": "session_already_active",
            "sessionPath": str(session),
        }
    )
    assert harness._expect_lease_refusal(accepted, session)["refused"] is True
    refused_during_close = Child(
        {
            "type": "rpc_startup_error",
            "code": "session_already_active",
            "sessionPath": str(session),
        },
        {"result": "graceful", "returnCode": 12},
    )
    assert harness._expect_lease_refusal(refused_during_close, session)["refused"] is True

    for row in (
        {"type": "rpc_startup_error", "code": "bootstrap_failed", "sessionPath": str(session)},
        {
            "type": "rpc_startup_error",
            "code": "session_already_active",
            "sessionPath": str(tmp_path / "different.jsonl"),
        },
        {"type": "parser_error", "code": "session_already_active", "sessionPath": str(session)},
    ):
        with pytest.raises(harness.HarnessFailure, match="exact session lease refusal"):
            harness._expect_lease_refusal(Child(row), session)


def test_session_continuity_requires_same_id_and_file(tmp_path: Path) -> None:
    harness = _load()
    session = (tmp_path / "session.jsonl").resolve()
    session.write_text("persisted\n", encoding="utf-8")
    expected = {"sessionId": "session-a", "sessionFile": str(session)}

    assert harness.require_session_continuity(expected, expected, tmp_path) == expected
    with pytest.raises(harness.HarnessFailure, match="sessionId"):
        harness.require_session_continuity(
            {"sessionId": "session-b", "sessionFile": str(session)},
            expected,
            tmp_path,
        )
    with pytest.raises(harness.HarnessFailure, match="sessionFile"):
        other = tmp_path / "other.jsonl"
        other.write_text("persisted\n", encoding="utf-8")
        harness.require_session_continuity(
            {"sessionId": "session-a", "sessionFile": str(other)},
            expected,
            tmp_path,
        )


def test_qualifying_close_requires_graceful_zero() -> None:
    harness = _load()

    class Child:
        def __init__(self, close_record: dict[str, object]) -> None:
            self.close_record = close_record

        def close(self):
            return dict(self.close_record)

    assert harness.require_graceful_close(
        Child({"result": "graceful", "returnCode": 0}), "owner"
    ) == {"result": "graceful", "returnCode": 0}
    for record in (
        {"result": "terminated_direct_handle", "returnCode": 1},
        {"result": "killed_direct_handle", "returnCode": -9},
        {"result": "already_exited", "returnCode": 0},
    ):
        with pytest.raises(harness.HarnessFailure, match="gracefully"):
            harness.require_graceful_close(Child(record), "owner")


def test_control_sequence_is_closed_and_contains_no_prompt() -> None:
    harness = _load()

    commands = harness.runtime_control_commands()

    assert tuple(command["type"] for command in commands) == (
        "get_state",
        "set_rlm_max_depth",
        "get_rlm_max_depth_status",
        "prepare_ipython_runtime",
    )
    assert commands[1] == {
        "id": "task7-set-depth",
        "type": "set_rlm_max_depth",
        "maxDepth": 0,
        "global": False,
    }
    assert all("prompt" not in command["type"] for command in commands)


def test_runtime_preparation_uses_prime_reported_interpreter_and_import_origins(
    tmp_path: Path,
) -> None:
    harness = _load()
    kernel = (tmp_path / "kernel").resolve()
    interpreter = kernel / "Scripts" / "python.exe"
    goal_skill = (tmp_path / "packages" / "goal" / "SKILL.md").resolve()
    rook_skill = (tmp_path / "packages" / "rook-full" / "SKILL.md").resolve()
    goal_file = goal_skill.parent / "src" / "goal" / "__init__.py"
    rook_file = rook_skill.parent / "src" / "rook_full" / "__init__.py"
    for path in (interpreter, goal_skill, rook_skill, goal_file, rook_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    preparation = {
        "interpreterPath": str(interpreter),
        "goalFile": str(goal_file),
        "rookFullFile": str(rook_file),
        "callables": {"search": True, "read": True, "call": True},
    }

    assert harness.validate_runtime_preparation(
        preparation,
        kernel_root=kernel,
        goal_skill_path=goal_skill,
        rook_skill_path=rook_skill,
    ) == {
        "interpreter": interpreter.resolve(),
        "goalFile": goal_file.resolve(),
        "rookFullFile": rook_file.resolve(),
    }
    with pytest.raises(harness.HarnessFailure, match="Rook import"):
        harness.validate_runtime_preparation(
            {**preparation, "rookFullFile": str(tmp_path / "outside.py")},
            kernel_root=kernel,
            goal_skill_path=goal_skill,
            rook_skill_path=rook_skill,
        )


def test_skill_staging_uses_closed_bytes_under_the_unique_package_root(
    tmp_path: Path,
) -> None:
    harness = _load()
    source = tmp_path / "source"
    (source / "src" / "sample").mkdir(parents=True)
    (source / "__pycache__").mkdir()
    (source / "SKILL.md").write_text("---\nname: sample\n---\n", encoding="utf-8")
    (source / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
    (source / "src" / "sample" / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    (source / "__pycache__" / "ignored.pyc").write_bytes(b"cache")
    destination = tmp_path / "run" / "packages" / "sample"

    staged = harness.stage_skill_package(source / "SKILL.md", destination)

    assert staged.skill_path == (destination / "SKILL.md").resolve()
    assert staged.manifest_sha256 == hashlib.sha256(staged.manifest_bytes).hexdigest().upper()
    assert not (destination / "__pycache__").exists()
    assert (destination / "src" / "sample" / "__init__.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_configuration_refuses_custody_drift_before_creating_the_run_root(
    tmp_path: Path,
) -> None:
    harness = _load()
    node = tmp_path / "node.exe"
    uv = tmp_path / "uv.exe"
    node.write_bytes(b"node")
    uv.write_bytes(b"uv")
    dist = tmp_path / "dist"
    (dist / "bundle").mkdir(parents=True)
    (dist / "skills").mkdir()
    (dist / "bundle" / "cli.js").write_text("export {};\n", encoding="utf-8")
    bundle_manifest = tmp_path / "prime-bundle-manifest.json"
    bundle = prime_runtime_contract.write_prime_bundle_manifest(dist, bundle_manifest)

    def skill(name: str) -> Path:
        root = tmp_path / name
        (root / "src" / name.replace("-", "_")).mkdir(parents=True)
        path = root / "SKILL.md"
        path.write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
        (root / "pyproject.toml").write_text(
            f"[project]\nname='{name}'\nversion='0.0.0'\n",
            encoding="utf-8",
        )
        return path

    run_root = tmp_path / "run"
    goal_skill = skill("goal")
    rook_skill = skill("rook-full")
    namespace = SimpleNamespace(
        run_root=str(run_root),
        node_path=str(node),
        node_sha256=hashlib.sha256(b"node").hexdigest().upper(),
        prime_dist_root=str(dist),
        prime_bundle_manifest=str(bundle_manifest),
        prime_bundle_sha256=bundle.manifest_sha256,
        uv_path=str(uv),
        uv_sha256="A" * 64,
        model="offline/catalog-model",
        goal_skill=str(goal_skill),
        goal_skill_manifest_sha256=hashlib.sha256(
            prime_runtime_contract.canonical_json_bytes(
                prime_runtime_contract.build_package_manifest(goal_skill.parent)
            )
        ).hexdigest().upper(),
        rook_skill=str(rook_skill),
        rook_skill_manifest_sha256=hashlib.sha256(
            prime_runtime_contract.canonical_json_bytes(
                prime_runtime_contract.build_package_manifest(rook_skill.parent)
            )
        ).hexdigest().upper(),
        entry_point="direct-vertical",
    )

    with pytest.raises(harness.HarnessFailure, match="uv SHA-256"):
        harness._configuration(namespace)

    assert not run_root.exists()

    namespace.uv_sha256 = hashlib.sha256(b"uv").hexdigest().upper()
    namespace.goal_skill_manifest_sha256 = "A" * 64
    with pytest.raises(harness.HarnessFailure, match="goal skill manifest"):
        harness._configuration(namespace)

    assert not run_root.exists()


def test_owned_process_start_closes_the_retained_child_when_reader_start_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _load()
    process = _FakePopen()
    monkeypatch.setattr(harness.subprocess, "Popen", lambda *_args, **_kwargs: process)

    class FailingThread:
        ident = None

        def __init__(self, *args, **kwargs):
            pass

        def start(self) -> None:
            raise RuntimeError("reader start failed")

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr(harness.threading, "Thread", FailingThread)

    child = harness.OwnedPrimeProcess(
        argv=("node.exe", "cli.js"),
        environment={},
        cwd=tmp_path,
        generation=1,
    )

    with pytest.raises(RuntimeError, match="reader start failed"):
        child.start()

    assert process.stdin.closed is True
    assert process.wait_calls == 1
    assert child.close() == {"result": "graceful", "returnCode": 0}


def test_owned_process_close_escalates_only_the_direct_handle(tmp_path: Path) -> None:
    harness = _load()

    class StubbornPopen(_FakePopen):
        def wait(self, timeout: float | None = None) -> int:
            self.wait_calls += 1
            if self.wait_calls < 3:
                raise harness.subprocess.TimeoutExpired("node.exe", timeout)
            self.returncode = -9
            return -9

    process = StubbornPopen()
    child = harness.OwnedPrimeProcess(
        argv=("node.exe", "cli.js"),
        environment={},
        cwd=tmp_path,
        generation=1,
    )
    child.process = process

    assert child.close() == {"result": "killed_direct_handle", "returnCode": -9}
    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert process.wait_calls == 3
    assert not hasattr(child, "_taskkill_fallback")


def test_owned_process_evidence_retains_generation_argv_pid_rows_and_close() -> None:
    harness = _load()
    child = SimpleNamespace(
        generation=4,
        argv=("node.exe", "cli.js", "--resume", "C:/sessions/exact.jsonl"),
        process=SimpleNamespace(pid=701, returncode=1),
        rows=[{"type": "response", "id": "state", "success": True}],
        stderr=["lease refused"],
        close_record={"result": "already_exited", "returnCode": 1},
    )

    assert harness.owned_process_evidence(child) == {
        "generation": 4,
        "argv": ["node.exe", "cli.js", "--resume", "C:/sessions/exact.jsonl"],
        "pid": 701,
        "returnCode": 1,
        "rows": [{"type": "response", "id": "state", "success": True}],
        "stderr": ["lease refused"],
        "close": {"result": "already_exited", "returnCode": 1},
    }
