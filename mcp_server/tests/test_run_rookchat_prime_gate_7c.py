from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_rookchat_prime_gate_7c as wrapper


STARTED_AT = "2026-08-30T12:00:00.000000Z"
ENDED_AT = "2026-08-30T12:00:01.000000Z"


def test_default_loader_loads_actual_reviewed_harness() -> None:
    harness_path = (
        Path(__file__).parents[2]
        / "scripts"
        / "rookchat_prime_gate_7c_broker_harness.py"
    )

    loaded = wrapper._load_harness(harness_path)

    assert loaded.__file__ == str(harness_path)
    assert callable(loaded.main)


def _configuration_payload(tmp_path: Path) -> dict[str, object]:
    evidence = tmp_path / "evidence"
    source_root = tmp_path / "rook" / "mcp_server" / "src"
    return {
        "schemaVersion": 2,
        "evidenceRoot": str(evidence),
        "deadlines": {
            "runtimePreparationSeconds": 150.0,
            "outerWrapperSeconds": None,
        },
        "hostPython": {
            "interpreterPath": str(
                tmp_path
                / "rook"
                / "mcp_server"
                / ".venv"
                / "Scripts"
                / "python.exe"
            ),
            "sourceRoot": str(source_root),
        },
        "admittedEnvironment": {
            "APPDATA": "C:/Users/test/AppData/Roaming",
            "COMSPEC": "C:/Windows/System32/cmd.exe",
            "LOCALAPPDATA": "C:/Users/test/AppData/Local",
            "PATHEXT": ".COM;.EXE;.BAT;.CMD",
            "PROGRAMDATA": "C:/ProgramData",
            "SystemRoot": "C:/Windows",
            "TEMP": "C:/Users/test/AppData/Local/Temp",
            "TMP": "C:/Users/test/AppData/Local/Temp",
            "USERPROFILE": "C:/Users/test",
            "WINDIR": "C:/Windows",
        },
        "node": {
            "path": str(tmp_path / "node.exe"),
            "sha256": "1" * 64,
        },
        "prime": {
            "distRoot": str(tmp_path / "prime" / "dist"),
            "bundleManifestPath": str(tmp_path / "prime-bundle.json"),
            "bundleManifestSha256": "2" * 64,
            "commit": "prime-head",
            "goalSkillRoot": str(tmp_path / "prime" / "goal"),
        },
        "rookPackageRoot": str(tmp_path / "rook" / "rook-full"),
        "runtime": {
            "productRoot": str(evidence / "runtime" / "product"),
            "kernelRoot": str(evidence / "runtime" / "kernels"),
            "registryRoot": str(evidence / "runtime" / "registry"),
            "sessionDirectory": str(evidence / "runtime" / "sessions"),
            "agentRoot": str(evidence / "runtime" / "agent"),
        },
        "uv": {
            "path": str(tmp_path / "uv.exe"),
            "sha256": "3" * 64,
        },
        "model": {
            "provider": "openai-codex",
            "id": "gpt-5.6-sol",
            "thinking": "xhigh",
        },
        "capabilityProfile": "readonly",
        "target": {
            "rhinoPid": 7101,
            "processStartUtcTicks": "638920000000000000",
            "documentRuntimeSerial": 42,
            "grasshopperDocumentId": "01234567-89ab-cdef-0123-456789abcdef",
        },
        "conversationId": "conv_0123456789abcdef0123456789abcdef",
    }


def _write_configuration(tmp_path: Path) -> Path:
    path = tmp_path / "gate-7c-config.json"
    path.write_text(
        json.dumps(
            _configuration_payload(tmp_path),
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="ascii",
    )
    return path


def _admission(tmp_path: Path) -> wrapper.Gate7CAdmission:
    harness = tmp_path / "harness.py"
    harness.write_text("# reviewed\n", encoding="utf-8")
    wrapper_path = tmp_path / "wrapper.py"
    wrapper_path.write_text("# admitted\n", encoding="utf-8")
    configuration = _write_configuration(tmp_path)
    return wrapper.Gate7CAdmission(
        rook_root=tmp_path / "rook",
        prime_root=tmp_path / "prime",
        approved_rook_commit="rook-head",
        approved_prime_commit="prime-head",
        wrapper_path=wrapper_path,
        harness_path=harness,
        harness_sha256=wrapper._sha256_file(harness),
        configuration_path=configuration,
        configuration_sha256=wrapper._sha256_file(configuration),
    )


def _clean_repository(root: Path) -> tuple[str, str]:
    return ("rook-head", "") if root.name == "rook" else ("prime-head", "")


def _host_runtime(tmp_path: Path) -> wrapper.HostRuntimeCustody:
    source_root = tmp_path / "rook" / "mcp_server" / "src"
    return wrapper.HostRuntimeCustody(
        interpreter_path=str(
            tmp_path
            / "rook"
            / "mcp_server"
            / ".venv"
            / "Scripts"
            / "python.exe"
        ),
        source_root=str(source_root),
        isolated=True,
        runtime_preparation_timeout_seconds=150.0,
        module_origins={
            "rook": str(source_root / "rook" / "__init__.py"),
            "rook.agent.chat.prime_backend": str(
                source_root / "rook" / "agent" / "chat" / "prime_backend.py"
            ),
            "rook.agent.chat.prime_process": str(
                source_root / "rook" / "agent" / "chat" / "prime_process.py"
            ),
        },
    )


def _expected_arguments(tmp_path: Path) -> tuple[str, ...]:
    evidence = tmp_path / "evidence"
    return (
        "--node-path",
        str(tmp_path / "node.exe"),
        "--node-sha256",
        "1" * 64,
        "--prime-dist-root",
        str(tmp_path / "prime" / "dist"),
        "--prime-bundle-manifest",
        str(tmp_path / "prime-bundle.json"),
        "--prime-bundle-sha256",
        "2" * 64,
        "--prime-commit",
        "prime-head",
        "--goal-skill-root",
        str(tmp_path / "prime" / "goal"),
        "--rook-package-root",
        str(tmp_path / "rook" / "rook-full"),
        "--product-root",
        str(evidence / "runtime" / "product"),
        "--kernel-root",
        str(evidence / "runtime" / "kernels"),
        "--registry-root",
        str(evidence / "runtime" / "registry"),
        "--session-dir",
        str(evidence / "runtime" / "sessions"),
        "--agent-root",
        str(evidence / "runtime" / "agent"),
        "--uv-path",
        str(tmp_path / "uv.exe"),
        "--uv-sha256",
        "3" * 64,
        "--base-environment-json",
        (
            '{"APPDATA":"C:/Users/test/AppData/Roaming",'
            '"COMSPEC":"C:/Windows/System32/cmd.exe",'
            '"LOCALAPPDATA":"C:/Users/test/AppData/Local",'
            '"PATHEXT":".COM;.EXE;.BAT;.CMD",'
            '"PROGRAMDATA":"C:/ProgramData","SystemRoot":"C:/Windows",'
            '"TEMP":"C:/Users/test/AppData/Local/Temp",'
            '"TMP":"C:/Users/test/AppData/Local/Temp",'
            '"USERPROFILE":"C:/Users/test","WINDIR":"C:/Windows"}'
        ),
        "--result",
        str(evidence / "result.json"),
        "--provider",
        "openai-codex",
        "--model",
        "gpt-5.6-sol",
        "--thinking",
        "xhigh",
        "--profile",
        "readonly",
        "--rhino-pid",
        "7101",
        "--process-start-ticks",
        "638920000000000000",
        "--document-serial",
        "42",
        "--grasshopper-document-id",
        "01234567-89ab-cdef-0123-456789abcdef",
        "--conversation-id",
        "conv_0123456789abcdef0123456789abcdef",
    )


def test_wrapper_builds_only_the_frozen_invocation_and_seals_success(
    tmp_path: Path,
) -> None:
    admitted = _admission(tmp_path)
    calls: list[tuple[Path, tuple[str, ...]]] = []

    def invoke(path: Path, arguments) -> int:
        calls.append((path, tuple(arguments)))
        result = tmp_path / "evidence" / "result.json"
        result.write_text('{"status":"passed"}', encoding="ascii")
        return 0

    timestamps = iter((STARTED_AT, ENDED_AT))
    result = wrapper.execute_gate_7c(
        admitted,
        repository_inspector=_clean_repository,
        harness_invoker=invoke,
        host_runtime_verifier=lambda _config: _host_runtime(tmp_path),
        utc_now=lambda: next(timestamps),
    )

    expected_arguments = _expected_arguments(tmp_path)
    assert result == {"status": "passed"}
    assert calls == [(admitted.harness_path, expected_arguments)]
    retained = json.loads(
        (tmp_path / "evidence" / "admission.json").read_text(encoding="ascii")
    )
    assert retained == {
        "approvedCommits": {"prime": "prime-head", "rook": "rook-head"},
        "configurationSha256": admitted.configuration_sha256,
        "admittedEnvironment": _configuration_payload(tmp_path)[
            "admittedEnvironment"
        ],
        "admittedEnvironmentSha256": (
            "2C4062472525FA37FA225FA3D1C9C8369D2BFBFDE40ED1C5182F867E592EA9B4"
        ),
        "constructedInvocation": {
            "arguments": list(expected_arguments),
            "harnessPath": str(admitted.harness_path),
            "pythonExecutable": str(Path(wrapper.sys.executable).resolve()),
            "wrapperPath": str(admitted.wrapper_path),
        },
        "endedAtUtc": ENDED_AT,
        "failure": None,
        "harnessExitCode": 0,
        "harnessSha256": admitted.harness_sha256,
        "deadlineCustody": {
            "outerWrapperSeconds": None,
            "runtimePreparationSeconds": 150.0,
        },
        "hostRuntime": {
            "interpreterPath": str(
                tmp_path
                / "rook"
                / "mcp_server"
                / ".venv"
                / "Scripts"
                / "python.exe"
            ),
            "isolated": True,
            "runtimePreparationTimeoutSeconds": 150.0,
            "moduleOrigins": _host_runtime(tmp_path).module_origins,
            "sourceRoot": str(tmp_path / "rook" / "mcp_server" / "src"),
        },
        "outcome": "passed",
        "resultPath": str(tmp_path / "evidence" / "result.json"),
        "resultSha256": wrapper._sha256_file(
            tmp_path / "evidence" / "result.json"
        ),
        "kernelRootAbsentBeforeExecution": True,
        "schemaVersion": 2,
        "startedAtUtc": STARTED_AT,
        "wrapperExitCode": 0,
        "wrapperSha256": wrapper._sha256_file(admitted.wrapper_path),
    }


@pytest.mark.parametrize(
    "failure",
    ("config_hash", "harness_hash", "dirty", "existing", "existing_kernel"),
)
def test_wrapper_refuses_before_invocation(tmp_path: Path, failure: str) -> None:
    admitted = _admission(tmp_path)
    if failure == "config_hash":
        admitted = wrapper.Gate7CAdmission(
            **{**admitted.__dict__, "configuration_sha256": "0" * 64}
        )
    elif failure == "harness_hash":
        admitted = wrapper.Gate7CAdmission(
            **{**admitted.__dict__, "harness_sha256": "0" * 64}
        )
    elif failure == "existing":
        (tmp_path / "evidence").mkdir(parents=True)
    elif failure == "existing_kernel":
        (tmp_path / "evidence" / "runtime" / "kernels").mkdir(parents=True)

    def inspect(root: Path) -> tuple[str, str]:
        if failure == "dirty" and root.name == "rook":
            return "rook-head", " M source.py\n"
        return _clean_repository(root)

    calls = 0

    def invoke(_path: Path, _arguments) -> int:
        nonlocal calls
        calls += 1
        return 0

    with pytest.raises(wrapper.Gate7CAdmissionFailure):
        wrapper.execute_gate_7c(
            admitted,
            repository_inspector=inspect,
            harness_invoker=invoke,
            host_runtime_verifier=lambda _config: _host_runtime(tmp_path),
        )
    assert calls == 0


def test_wrapper_failure_is_absorbing_and_seals_failure(tmp_path: Path) -> None:
    admitted = _admission(tmp_path)
    calls = 0

    def invoke(_path: Path, _arguments) -> int:
        nonlocal calls
        calls += 1
        return 7

    timestamps = iter((STARTED_AT, ENDED_AT))
    with pytest.raises(wrapper.Gate7CAdmissionFailure, match="do not retry"):
        wrapper.execute_gate_7c(
            admitted,
            repository_inspector=_clean_repository,
            harness_invoker=invoke,
            host_runtime_verifier=lambda _config: _host_runtime(tmp_path),
            utc_now=lambda: next(timestamps),
        )

    assert calls == 1
    retained = json.loads(
        (tmp_path / "evidence" / "admission.json").read_text(encoding="ascii")
    )
    assert retained["outcome"] == "failed"
    assert retained["wrapperExitCode"] == 1
    assert retained["harnessExitCode"] == 7
    assert retained["failure"] == (
        "Gate 7C harness failed with exit code 7; do not retry"
    )
    assert retained["resultSha256"] is None


def test_command_line_accepts_only_the_reviewed_rook_commit() -> None:
    parsed = wrapper.build_parser().parse_args(
        ["--approved-rook-commit", "rook-head"]
    )

    assert vars(parsed) == {"approved_rook_commit": "rook-head"}
    with pytest.raises(SystemExit):
        wrapper.build_parser().parse_args(
            [
                "--approved-rook-commit",
                "rook-head",
                "--node-path",
                "unreviewed-node.exe",
            ]
        )


def _host_modules(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    interpreter = (
        tmp_path
        / "rook"
        / "mcp_server"
        / ".venv"
        / "Scripts"
        / "python.exe"
    )
    interpreter.parent.mkdir(parents=True, exist_ok=True)
    interpreter.touch()
    source_root = tmp_path / "rook" / "mcp_server" / "src"
    paths = {
        "rook": source_root / "rook" / "__init__.py",
        "rook.agent.chat.prime_backend": (
            source_root / "rook" / "agent" / "chat" / "prime_backend.py"
        ),
        "rook.agent.chat.prime_process": (
            source_root / "rook" / "agent" / "chat" / "prime_process.py"
        ),
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    return interpreter, paths


def _module_loader(
    paths: dict[str, Path],
    *,
    preparation_timeout_seconds: float = 150.0,
):
    def load(name: str):
        values = {"__file__": str(paths[name])}
        if name == "rook.agent.chat.prime_backend":
            values["RUNTIME_PREPARATION_TIMEOUT_SECONDS"] = (
                preparation_timeout_seconds
            )
        return SimpleNamespace(**values)

    return load


def test_host_runtime_refuses_wrong_interpreter(tmp_path: Path) -> None:
    _expected, paths = _host_modules(tmp_path)
    wrong = tmp_path / "wrong-python.exe"
    wrong.touch()
    config = wrapper.load_frozen_configuration(_write_configuration(tmp_path))

    with pytest.raises(wrapper.Gate7CAdmissionFailure, match="interpreter"):
        wrapper.verify_host_runtime(
            config,
            executable=wrong,
            isolated=True,
            environment={},
            module_loader=_module_loader(paths),
        )


@pytest.mark.parametrize("override", ("PYTHONPATH", "PYTHONHOME"))
def test_host_runtime_refuses_python_overrides(
    tmp_path: Path,
    override: str,
) -> None:
    interpreter, paths = _host_modules(tmp_path)
    config = wrapper.load_frozen_configuration(_write_configuration(tmp_path))

    with pytest.raises(wrapper.Gate7CAdmissionFailure, match=override):
        wrapper.verify_host_runtime(
            config,
            executable=interpreter,
            isolated=True,
            environment={override: "C:/unreviewed"},
            module_loader=_module_loader(paths),
        )


def test_host_runtime_refuses_nonisolated_python(tmp_path: Path) -> None:
    interpreter, paths = _host_modules(tmp_path)
    config = wrapper.load_frozen_configuration(_write_configuration(tmp_path))

    with pytest.raises(wrapper.Gate7CAdmissionFailure, match="isolated"):
        wrapper.verify_host_runtime(
            config,
            executable=interpreter,
            isolated=False,
            environment={},
            module_loader=_module_loader(paths),
        )


def test_host_runtime_refuses_wrong_rook_import_origin(tmp_path: Path) -> None:
    interpreter, paths = _host_modules(tmp_path)
    paths["rook.agent.chat.prime_process"] = tmp_path / "other" / "prime_process.py"
    paths["rook.agent.chat.prime_process"].parent.mkdir(parents=True)
    paths["rook.agent.chat.prime_process"].touch()
    config = wrapper.load_frozen_configuration(_write_configuration(tmp_path))

    with pytest.raises(wrapper.Gate7CAdmissionFailure, match="import origin"):
        wrapper.verify_host_runtime(
            config,
            executable=interpreter,
            isolated=True,
            environment={},
            module_loader=_module_loader(paths),
        )


def test_host_runtime_refuses_wrong_preparation_deadline(tmp_path: Path) -> None:
    interpreter, paths = _host_modules(tmp_path)
    config = wrapper.load_frozen_configuration(_write_configuration(tmp_path))

    with pytest.raises(wrapper.Gate7CAdmissionFailure, match="preparation deadline"):
        wrapper.verify_host_runtime(
            config,
            executable=interpreter,
            isolated=True,
            environment={},
            module_loader=_module_loader(
                paths,
                preparation_timeout_seconds=149.0,
            ),
        )


def test_configuration_refuses_outer_wrapper_deadline(tmp_path: Path) -> None:
    payload = _configuration_payload(tmp_path)
    payload["deadlines"]["outerWrapperSeconds"] = 149.0
    path = tmp_path / "gate-7c-config.json"
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="ascii",
    )

    with pytest.raises(wrapper.Gate7CAdmissionFailure, match="outer wrapper"):
        wrapper.load_frozen_configuration(path)


def test_wrapper_refuses_changed_admitted_environment(tmp_path: Path) -> None:
    admitted = _admission(tmp_path)
    payload = json.loads(admitted.configuration_path.read_text(encoding="ascii"))
    payload["admittedEnvironment"]["TEMP"] = "C:/unreviewed"
    admitted.configuration_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="ascii",
    )
    calls = 0

    def invoke(_path: Path, _arguments) -> int:
        nonlocal calls
        calls += 1
        return 0

    with pytest.raises(
        wrapper.Gate7CAdmissionFailure,
        match="configuration differs from review",
    ):
        wrapper.execute_gate_7c(
            admitted,
            repository_inspector=_clean_repository,
            harness_invoker=invoke,
            host_runtime_verifier=lambda _config: _host_runtime(tmp_path),
        )

    assert calls == 0
    assert not (tmp_path / "evidence").exists()
