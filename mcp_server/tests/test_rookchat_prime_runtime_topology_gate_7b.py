import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[2] / "scripts" / "run_rookchat_prime_runtime_topology_gate_7b.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "run_rookchat_prime_runtime_topology_gate_7b",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _configuration(gate, tmp_path: Path):
    rook = tmp_path / "rook"
    prime = tmp_path / "prime"
    rook.mkdir()
    prime.mkdir()
    harness_path = rook / "harness.py"
    frozen_path = rook / "frozen.json"
    harness_path.write_bytes(b"harness")
    frozen_path.write_bytes(b"frozen")
    return gate.Gate7BConfiguration(
        rook_root=rook,
        prime_root=prime,
        approved_rook_commit="a" * 40,
        approved_prime_commit="b" * 40,
        harness=gate.FrozenFile(
            harness_path,
            hashlib.sha256(b"harness").hexdigest().upper(),
        ),
        frozen_files=(
            gate.FrozenFile(
                frozen_path,
                hashlib.sha256(b"frozen").hexdigest().upper(),
            ),
        ),
        lease_root=tmp_path / "lease",
        direct_root=tmp_path / "direct",
    )


def test_gate_7b_uses_one_versioned_admission_wrapper() -> None:
    assert SCRIPT.is_file()


def test_gate_wrapper_defaults_creation_flags_to_zero_off_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(subprocess, "CREATE_NO_WINDOW", raising=False)

    gate = _load()

    assert gate.CREATE_NO_WINDOW == 0


def test_gate_7b_v3_uses_recovery_worktrees_and_fresh_evidence_roots() -> None:
    gate = _load()

    assert gate.ROOK_ROOT.name == "task7-runtime-topology-recovery"
    assert gate.PRIME_ROOT.name == "task7-runtime-topology-recovery"
    assert "gate-7b-v3" in str(gate.LEASE_ROOT)
    assert "gate-7b-v3" in str(gate.DIRECT_ROOT)
    assert gate.LEASE_ROOT != gate.DIRECT_ROOT


def test_gate_7b_refuses_commit_or_hash_drift_before_any_entry_runs(tmp_path: Path) -> None:
    gate = _load()
    config = _configuration(gate, tmp_path)
    calls = []

    with pytest.raises(gate.Gate7BFailure, match="Rook commit"):
        gate.execute_gate_7b(
            config,
            inspect_repo=lambda root: (("c" * 40, "") if root == config.rook_root else ("b" * 40, "")),
            hash_file=lambda path: hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            run_entry=lambda entry, root: calls.append((entry, root)),
        )

    assert calls == []
    assert not config.lease_root.exists()
    assert not config.direct_root.exists()


def test_gate_7b_stops_after_a_failed_lease_result(tmp_path: Path) -> None:
    gate = _load()
    config = _configuration(gate, tmp_path)
    calls = []

    def run_entry(entry: str, root: Path):
        calls.append((entry, root))
        return 1, {"result": {"status": "failed"}}

    with pytest.raises(gate.Gate7BFailure, match="lease-sequence"):
        gate.execute_gate_7b(
            config,
            inspect_repo=lambda root: (
                (config.approved_rook_commit, "")
                if root == config.rook_root
                else (config.approved_prime_commit, "")
            ),
            hash_file=lambda path: hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            run_entry=run_entry,
        )

    assert calls == [("lease-sequence", config.lease_root)]
    assert not config.direct_root.exists()


def test_gate_7b_stops_after_a_raised_lease_failure(tmp_path: Path) -> None:
    gate = _load()
    config = _configuration(gate, tmp_path)
    calls = []

    def run_entry(entry: str, root: Path):
        calls.append((entry, root))
        raise RuntimeError("lease initialization failed")

    with pytest.raises(RuntimeError, match="lease initialization failed"):
        gate.execute_gate_7b(
            config,
            inspect_repo=lambda root: (
                (config.approved_rook_commit, "")
                if root == config.rook_root
                else (config.approved_prime_commit, "")
            ),
            hash_file=lambda path: hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            run_entry=run_entry,
        )

    assert calls == [("lease-sequence", config.lease_root)]
    assert not config.direct_root.exists()


def test_gate_7b_runs_direct_only_after_a_passing_lease_result(tmp_path: Path) -> None:
    gate = _load()
    config = _configuration(gate, tmp_path)
    calls = []

    def run_entry(entry: str, root: Path):
        calls.append((entry, root))
        return 0, {"result": {"status": "passed", "entryPoint": entry}}

    result = gate.execute_gate_7b(
        config,
        inspect_repo=lambda root: (
            (config.approved_rook_commit, "")
            if root == config.rook_root
            else (config.approved_prime_commit, "")
        ),
        hash_file=lambda path: hashlib.sha256(path.read_bytes()).hexdigest().upper(),
        run_entry=run_entry,
    )

    assert calls == [
        ("lease-sequence", config.lease_root),
        ("direct-vertical", config.direct_root),
    ]
    assert result["lease"]["result"]["status"] == "passed"
    assert result["direct"]["result"]["status"] == "passed"


def test_gate_7b_rechecks_custody_after_lease_before_direct(tmp_path: Path) -> None:
    gate = _load()
    config = _configuration(gate, tmp_path)
    calls = []
    rook_checks = 0

    def inspect_repo(root: Path):
        nonlocal rook_checks
        if root == config.rook_root:
            rook_checks += 1
            commit = config.approved_rook_commit if rook_checks == 1 else "c" * 40
            return commit, ""
        return config.approved_prime_commit, ""

    def run_entry(entry: str, root: Path):
        calls.append((entry, root))
        return 0, {"result": {"status": "passed"}}

    with pytest.raises(gate.Gate7BFailure, match="Rook commit"):
        gate.execute_gate_7b(
            config,
            inspect_repo=inspect_repo,
            hash_file=lambda path: hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            run_entry=run_entry,
        )

    assert calls == [("lease-sequence", config.lease_root)]
    assert not config.direct_root.exists()


def test_reviewed_entry_uses_exact_root_and_reads_retained_result(tmp_path: Path) -> None:
    gate = _load()
    run_root = tmp_path / "run"
    observed = []

    def harness_main(argv):
        observed.append(tuple(argv))
        result_path = run_root / "evidence" / "result.json"
        result_path.parent.mkdir(parents=True)
        result_path.write_text('{"result":{"status":"passed"}}', encoding="utf-8")
        return 0

    code, result = gate.run_reviewed_entry(
        harness_main,
        ("--frozen", "value"),
        "lease-sequence",
        run_root,
    )

    assert code == 0
    assert result == {"result": {"status": "passed"}}
    assert observed == [
        (
            "lease-sequence",
            "--run-root",
            str(run_root),
            "--frozen",
            "value",
        )
    ]
