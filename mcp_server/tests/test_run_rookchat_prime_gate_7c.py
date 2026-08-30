from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_rookchat_prime_gate_7c as wrapper


def admission(tmp_path: Path) -> wrapper.Gate7CAdmission:
    harness = tmp_path / "harness.py"
    harness.write_text("# reviewed\n", encoding="utf-8")
    return wrapper.Gate7CAdmission(
        rook_root=tmp_path / "rook",
        prime_root=tmp_path / "prime",
        approved_rook_commit="rook-head",
        approved_prime_commit="prime-head",
        harness_path=harness,
        harness_sha256=wrapper._sha256_file(harness),
        result_path=tmp_path / "evidence" / "result.json",
    )


def clean_repository(root: Path) -> tuple[str, str]:
    return ("rook-head", "") if root.name == "rook" else ("prime-head", "")


def test_wrapper_authenticates_before_one_successful_invocation(tmp_path: Path) -> None:
    admitted = admission(tmp_path)
    calls: list[tuple[Path, tuple[str, ...]]] = []

    def invoke(path: Path, arguments) -> int:
        calls.append((path, tuple(arguments)))
        admitted.result_path.parent.mkdir(parents=True)
        admitted.result_path.write_text('{"status":"passed"}', encoding="ascii")
        return 0

    result = wrapper.execute_gate_7c(
        admitted,
        ("--node-path", "node.exe"),
        repository_inspector=clean_repository,
        harness_invoker=invoke,
    )

    assert result == {"status": "passed"}
    assert calls == [
        (
            admitted.harness_path,
            (
                "--node-path",
                "node.exe",
                "--result",
                str(admitted.result_path),
            ),
        )
    ]


@pytest.mark.parametrize("failure", ("hash", "dirty", "existing"))
def test_wrapper_refuses_before_invocation(tmp_path: Path, failure: str) -> None:
    admitted = admission(tmp_path)
    if failure == "hash":
        admitted = wrapper.Gate7CAdmission(
            **{**admitted.__dict__, "harness_sha256": "0" * 64}
        )
    elif failure == "existing":
        admitted.result_path.parent.mkdir(parents=True)
        admitted.result_path.write_text("{}", encoding="ascii")

    def inspect(root: Path) -> tuple[str, str]:
        if failure == "dirty" and root.name == "rook":
            return "rook-head", " M source.py\n"
        return clean_repository(root)

    calls = 0

    def invoke(_path: Path, _arguments) -> int:
        nonlocal calls
        calls += 1
        return 0

    with pytest.raises(wrapper.Gate7CAdmissionFailure):
        wrapper.execute_gate_7c(
            admitted,
            (),
            repository_inspector=inspect,
            harness_invoker=invoke,
        )
    assert calls == 0


def test_wrapper_refuses_caller_supplied_result_path(tmp_path: Path) -> None:
    admitted = admission(tmp_path)

    with pytest.raises(wrapper.Gate7CAdmissionFailure, match="wrapper-owned"):
        wrapper.execute_gate_7c(
            admitted,
            ("--result", str(tmp_path / "alternate.json")),
            repository_inspector=clean_repository,
        )


def test_wrapper_failure_is_absorbing_and_never_retries(tmp_path: Path) -> None:
    admitted = admission(tmp_path)
    calls = 0

    def invoke(_path: Path, _arguments) -> int:
        nonlocal calls
        calls += 1
        admitted.result_path.parent.mkdir(parents=True)
        admitted.result_path.write_text(
            json.dumps({"status": "failed"}), encoding="ascii"
        )
        return 1

    with pytest.raises(wrapper.Gate7CAdmissionFailure, match="do not retry"):
        wrapper.execute_gate_7c(
            admitted,
            (),
            repository_inspector=clean_repository,
            harness_invoker=invoke,
        )
    assert calls == 1
