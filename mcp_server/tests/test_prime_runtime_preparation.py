from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from rook.agent.chat.prime_process import PrimeRpcProcess
from rook.agent.chat.prime_registry import TargetFingerprintV2
from rook.agent.chat.prime_rpc_protocol import (
    IpythonRuntimePreparation,
    parse_ipython_runtime_preparation,
    parse_rlm_max_depth_status,
)
from rook.agent.chat.prime_runtime_contract import (
    PrimeRuntimeContractOwner,
    build_runtime_contract,
    stage_product_package,
)


PRIME_ROOT = Path("D:/prime-agent/.worktrees/rookchat-primary-backend")
ROOK_ROOT = Path(__file__).parents[2]
ROOK_PACKAGE_SOURCE = ROOK_ROOT / "integrations" / "prime" / "skills" / "rook-full"
GOAL_ROOT = PRIME_ROOT / "packages" / "coding-agent" / "skills" / "goal"
CLI_PATH = PRIME_ROOT / "packages" / "coding-agent" / "dist" / "cli.js"
PRIME_BUNDLE_MANIFEST = PRIME_ROOT / "package-lock.json"
GH_ID = "12345678-1234-1234-1234-1234567890ab"
_CREDENTIAL = re.compile(
    r"(API_KEY|OAUTH_TOKEN|ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN|"
    r"BEARER_TOKEN_BEDROCK|WEB_IDENTITY_TOKEN_FILE|GITHUB_TOKEN|GH_TOKEN|"
    r"HF_TOKEN|COPILOT_GITHUB_TOKEN|AWS_PROFILE|"
    r"GOOGLE_APPLICATION_CREDENTIALS)$",
    re.IGNORECASE,
)


def _prime_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=PRIME_ROOT,
        text=True,
    ).strip()


def _owner(
    tmp_path: Path,
    *,
    source: Path,
    product_root: Path,
    kernel_root: Path,
) -> PrimeRuntimeContractOwner:
    package = stage_product_package(source, product_root=product_root)
    bundle_sha = hashlib.sha256(PRIME_BUNDLE_MANIFEST.read_bytes()).hexdigest().upper()
    commit = _prime_commit()
    contract = build_runtime_contract(
        prime_bundle_manifest_sha256=bundle_sha,
        prime_git_commit_provenance=commit,
        goal_skill_root=GOAL_ROOT,
        goal_skill_path_identity="packages/coding-agent/skills/goal",
        rook_package=package,
        capability_profile="readonly",
        kernel_root=kernel_root,
        runtime_compatibility_version=1,
    )
    data_root = tmp_path / "data"
    dspy_root = data_root / "dspy-cache"
    chirp_root = tmp_path / "chirp"
    dspy_root.mkdir(parents=True, exist_ok=True)
    chirp_root.mkdir(parents=True, exist_ok=True)
    return PrimeRuntimeContractOwner(
        contract=contract,
        prime_root=PRIME_ROOT,
        prime_bundle_manifest_path=PRIME_BUNDLE_MANIFEST,
        prime_git_commit_provenance=commit,
        goal_skill_root=GOAL_ROOT,
        product_root=product_root,
        kernel_root=kernel_root,
        product_environment={
            "ROOK_MCP_PYTHON_EXECUTABLE": str(
                ROOK_ROOT / "mcp_server" / ".venv" / "Scripts" / "python.exe"
            ),
            "ROOK_MCP_WORKING_DIRECTORY": str(ROOK_ROOT / "mcp_server"),
            "ROOK_INSTALL_ROOT": str(ROOK_ROOT),
            "ROOK_DATA_DIR": str(data_root),
            "DSPY_CACHEDIR": str(dspy_root),
            "CHIRP_HOME": str(chirp_root),
            "ROOK_MODE": "release",
            "ROOK_DSPY_RESTRICT_PICKLE": "1",
        },
    )


def _process(
    tmp_path: Path,
    *,
    generation: int,
    owner: PrimeRuntimeContractOwner,
) -> PrimeRpcProcess:
    node = shutil.which("node")
    assert node is not None
    target = TargetFingerprintV2(
        2468,
        "638918000000000000",
        42,
        GH_ID,
    )
    return PrimeRpcProcess(
        node_path=node,
        cli_path=CLI_PATH,
        session_dir=tmp_path / "sessions" / str(generation),
        generation=generation,
        launch_configuration=owner.launch_configuration(target),
        control_timeout_seconds=120.0,
    )


async def _prepare(
    process: PrimeRpcProcess,
    owner: PrimeRuntimeContractOwner,
) -> IpythonRuntimePreparation:
    set_response = await process.command(
        {"type": "set_rlm_max_depth", "maxDepth": 0, "global": False},
        expected_command="set_rlm_max_depth",
        timeout_seconds=120.0,
    )
    set_status = parse_rlm_max_depth_status(
        set_response,
        expected_command="set_rlm_max_depth",
    )
    assert (set_status.max_depth, set_status.source) == (0, "chat")
    get_response = await process.command(
        {"type": "get_rlm_max_depth_status"},
        expected_command="get_rlm_max_depth_status",
        timeout_seconds=120.0,
    )
    get_status = parse_rlm_max_depth_status(
        get_response,
        expected_command="get_rlm_max_depth_status",
    )
    assert (get_status.max_depth, get_status.source) == (0, "chat")
    prepare_response = await process.command(
        {"type": "prepare_ipython_runtime"},
        expected_command="prepare_ipython_runtime",
        timeout_seconds=300.0,
    )
    if prepare_response.get("success") is not True:
        raise AssertionError(
            f"Prime preparation failed: {prepare_response!r}; "
            f"stderr={process.stderr_tail!r}"
        )
    prepared = parse_ipython_runtime_preparation(prepare_response)
    owner.verify_prepared_runtime(prepared)
    return prepared


@pytest.mark.asyncio
async def test_real_prime_bootstrap_serializes_same_contract_and_isolates_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert PRIME_ROOT.is_dir()
    assert CLI_PATH.is_file()
    assert PRIME_BUNDLE_MANIFEST.is_file()
    assert GOAL_ROOT.is_dir()
    assert ROOK_PACKAGE_SOURCE.is_dir()
    for name in tuple(os.environ):
        if _CREDENTIAL.search(name):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    monkeypatch.setenv(
        "PRIME_AGENT_CODING_AGENT_DIR",
        str(tmp_path / "prime-agent"),
    )

    product_root = tmp_path / "contracts"
    kernel_root = tmp_path / "kernels"
    first_owner = _owner(
        tmp_path,
        source=ROOK_PACKAGE_SOURCE,
        product_root=product_root,
        kernel_root=kernel_root,
    )
    same_contract_processes = [
        _process(tmp_path, generation=index, owner=first_owner)
        for index in (1, 2)
    ]
    all_processes = list(same_contract_processes)
    try:
        for process in same_contract_processes:
            try:
                await process.start()
            except Exception as error:
                raise AssertionError(
                    f"Prime RPC startup failed: {error}; stderr={process.stderr_tail!r}"
                ) from error
        first_results = await asyncio.gather(
            *(_prepare(process, first_owner) for process in same_contract_processes)
        )
        assert len({result.interpreter_path for result in first_results}) == 1
        assert len({result.rook_full_file for result in first_results}) == 1

        changed_source = tmp_path / "changed-rook-full"
        shutil.copytree(ROOK_PACKAGE_SOURCE, changed_source)
        reference = changed_source / "references" / "grasshopper.md"
        reference.write_text(
            reference.read_text(encoding="utf-8") + "\nContract isolation fixture.\n",
            encoding="utf-8",
        )
        second_owner = _owner(
            tmp_path,
            source=changed_source,
            product_root=product_root,
            kernel_root=kernel_root,
        )
        assert second_owner.contract.fingerprint != first_owner.contract.fingerprint
        assert (
            second_owner.contract.kernel_environment_path
            != first_owner.contract.kernel_environment_path
        )

        old_process = _process(tmp_path, generation=3, owner=first_owner)
        new_process = _process(tmp_path, generation=4, owner=second_owner)
        all_processes.extend((old_process, new_process))
        await old_process.start()
        await new_process.start()
        old_result, new_result = await asyncio.gather(
            _prepare(old_process, first_owner),
            _prepare(new_process, second_owner),
        )
        assert old_result.interpreter_path != new_result.interpreter_path
        assert old_result.rook_full_file != new_result.rook_full_file
        assert Path(old_result.rook_full_file).is_relative_to(
            first_owner.contract.rook_package.root
        )
        assert Path(new_result.rook_full_file).is_relative_to(
            second_owner.contract.rook_package.root
        )
    finally:
        await asyncio.gather(
            *(process.retire(5.0) for process in all_processes),
            return_exceptions=True,
        )
    assert all(process._retired for process in all_processes)
