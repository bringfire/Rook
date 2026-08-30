from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from rook.agent.chat import prime_runtime_contract


SCRIPT = Path(__file__).parents[2] / "scripts" / "rookchat_prime_runtime_topology_harness.py"


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


def test_cleanup_admission_requires_exact_generation_and_identity() -> None:
    harness = _load()
    owner = harness.ProcessSnapshot(101, 55, "638880485801234567", "node.exe")

    assert harness.admit_cleanup_target(owner, owner, expected_generation=7, generation=7) is owner
    with pytest.raises(harness.HarnessFailure, match="generation"):
        harness.admit_cleanup_target(owner, owner, expected_generation=7, generation=8)
    with pytest.raises(harness.HarnessFailure, match="identity"):
        harness.admit_cleanup_target(
            owner,
            harness.ProcessSnapshot(101, 55, "638880485801234568", "node.exe"),
            expected_generation=7,
            generation=7,
        )


def test_phase_observations_require_exact_uv_and_one_steady_kernel(tmp_path: Path) -> None:
    harness = _load()
    uv = (tmp_path / "uv.exe").resolve()
    python = (tmp_path / "kernel" / "Scripts" / "python.exe").resolve()
    uv.write_bytes(b"uv")
    python.parent.mkdir(parents=True)
    python.write_bytes(b"python")
    observations = (
        harness.ProcessObservation(
            "cold_preparation",
            harness.ProcessSnapshot(201, 101, "2", str(uv)),
        ),
        harness.ProcessObservation(
            "cold_preparation",
            harness.ProcessSnapshot(202, 101, "3", str(python)),
        ),
        harness.ProcessObservation(
            "steady_state",
            harness.ProcessSnapshot(202, 101, "3", str(python)),
        ),
    )

    harness.validate_phase_observations(
        observations,
        uv_path=uv,
        uv_sha256=hashlib.sha256(b"uv").hexdigest().upper(),
        interpreter=python,
    )
    with pytest.raises(harness.HarnessFailure, match="uv"):
        harness.validate_phase_observations(
            observations,
            uv_path=uv,
            uv_sha256="A" * 64,
            interpreter=python,
        )
    with pytest.raises(harness.HarnessFailure, match="steady"):
        harness.validate_phase_observations(
            observations
            + (
                harness.ProcessObservation(
                    "steady_state",
                    harness.ProcessSnapshot(203, 101, "4", "daemon-worker.exe"),
                ),
            ),
            uv_path=uv,
            uv_sha256=hashlib.sha256(b"uv").hexdigest().upper(),
            interpreter=python,
        )


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
