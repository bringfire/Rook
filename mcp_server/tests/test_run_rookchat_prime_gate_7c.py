from __future__ import annotations

import json
from pathlib import Path

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
    return {
        "schemaVersion": 1,
        "evidenceRoot": str(evidence),
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
        "outcome": "passed",
        "resultPath": str(tmp_path / "evidence" / "result.json"),
        "resultSha256": wrapper._sha256_file(
            tmp_path / "evidence" / "result.json"
        ),
        "schemaVersion": 1,
        "startedAtUtc": STARTED_AT,
        "wrapperExitCode": 0,
        "wrapperSha256": wrapper._sha256_file(admitted.wrapper_path),
    }


@pytest.mark.parametrize(
    "failure", ("config_hash", "harness_hash", "dirty", "existing")
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
