from __future__ import annotations

import asyncio
import contextlib
import hashlib
import http.client
import importlib
import json
import os
import socket
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO = Path(__file__).resolve().parents[2]
COMMON = REPO / "scripts/qualification/rookchat_prime_acp_common.py"
PRECONTACT = REPO / "scripts/qualification/rookchat_prime_acp_precontact.py"
PROVIDER = REPO / "scripts/qualification/fixtures/deterministic_provider.py"
sys.path.insert(0, str(REPO))


def _common():
    return importlib.import_module("scripts.qualification.rookchat_prime_acp_common")


def _provider():
    assert PROVIDER.is_file(), "MISSING_BEHAVIOR: deterministic provider and Rook MCP double"
    return importlib.import_module("scripts.qualification.fixtures.deterministic_provider")


def _precontact():
    assert PRECONTACT.is_file(), "MISSING_BEHAVIOR: combined A+B pre-contact runner"
    return importlib.import_module("scripts.qualification.rookchat_prime_acp_precontact")


def _symbol(module, name: str):
    assert hasattr(module, name), f"MISSING_BEHAVIOR: {name}"
    return getattr(module, name)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _runtime_source_identity_oracle(root: Path) -> str:
    files = [root / "pyproject.toml", *sorted((root / "src/rlm").rglob("*.py"))]
    digest = hashlib.sha256()
    for path in sorted(files):
        relative = path.relative_to(root).as_posix().replace("/", "\\")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _content(text: str) -> dict[str, str]:
    return {"text": text, "sha256": _sha(text.encode("utf-8"))}


def _valid_protocol(tmp_path: Path) -> tuple[dict, Path, Path]:
    source = tmp_path / "source"
    source.mkdir()
    source_input = source / "authority.txt"
    source_input.write_text("reviewed\n", encoding="utf-8", newline="\n")

    install_root = tmp_path / "installed-prime"
    runtime_root = install_root / "runtimes" / ("A" * 64)
    (runtime_root / "skills/rook-full").mkdir(parents=True)
    executable = runtime_root / "pi.exe"
    skill = runtime_root / "skills/rook-full/SKILL.md"
    runtime_source = runtime_root / "dist/prime-agent-runtime"
    (runtime_source / "src/rlm").mkdir(parents=True)
    executable.write_bytes(b"prime")
    skill.write_text("# Rook\n", encoding="utf-8", newline="\n")
    (runtime_source / "pyproject.toml").write_text(
        '[project]\nname = "prime-agent-runtime"\n', encoding="utf-8", newline="\n"
    )
    (runtime_source / "src/rlm/__init__.py").write_text("def run():\n    return None\n", encoding="utf-8", newline="\n")
    manifest = {
        "acpProtocolVersion": 1,
        "compatibilityPatchCommit": "b" * 40,
        "files": [
            {
                "bytes": (runtime_source / "pyproject.toml").stat().st_size,
                "path": "dist/prime-agent-runtime/pyproject.toml",
                "sha256": _sha((runtime_source / "pyproject.toml").read_bytes()),
            },
            {
                "bytes": (runtime_source / "src/rlm/__init__.py").stat().st_size,
                "path": "dist/prime-agent-runtime/src/rlm/__init__.py",
                "sha256": _sha((runtime_source / "src/rlm/__init__.py").read_bytes()),
            },
            {"bytes": 5, "path": "pi.exe", "sha256": _sha(b"prime")},
            {"bytes": 7, "path": "skills/rook-full/SKILL.md", "sha256": _sha(b"# Rook\n")},
        ],
        "pythonRuntime": {"manifestSha256": "D" * 64},
        "rookSkillManifestSha256": "C" * 64,
    }
    manifest_bytes = _canonical(manifest)
    runtime_id = _sha(manifest_bytes)
    actual_root = install_root / "runtimes" / runtime_id
    runtime_root.rename(actual_root)
    manifest_path = actual_root / "runtime-manifest.json"
    manifest_path.write_bytes(manifest_bytes)

    evidence_root = tmp_path / "evidence"
    proxy = "http://127.0.0.1:48761"
    final_environment = {
        "ALL_PROXY": proxy,
        "APPDATA": str(evidence_root / "live/appdata"),
        "HOME": str(evidence_root / "live/home"),
        "HTTPS_PROXY": proxy,
        "HTTP_PROXY": proxy,
        "LOCALAPPDATA": str(evidence_root / "live/localappdata"),
        "NO_PROXY": "127.0.0.1,localhost",
        "PATH": str(actual_root / "tools/uv"),
        "PRIME_AGENT_CODING_AGENT_DIR": str(evidence_root / "live/prime-agent"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "ROOK_DATA_DIR": str(evidence_root / "live/rook-data"),
        "TEMP": str(evidence_root / "live/temp"),
        "TMP": str(evidence_root / "live/temp"),
        "USERPROFILE": str(evidence_root / "live/user-profile"),
        "UV_CACHE_DIR": str(evidence_root / "live/rook-data/rookchat/acp/v1/prime-uv/cache"),
        "UV_NO_CONFIG": "1",
        "UV_PYTHON_INSTALL_DIR": str(evidence_root / "live/rook-data/rookchat/acp/v1/prime-uv/python"),
        "UV_PYTHON_INSTALL_REGISTRY": "0",
        "UV_PYTHON_NO_REGISTRY": "1",
        "UV_PYTHON_PREFERENCE": "only-managed",
    }
    protocol = {
        "environment": {
            "expectedFinal": final_environment,
            "expectedFinalSha256": _sha(_canonical(final_environment)),
            "productOwnedUv": {
                "UV_CACHE_DIR": final_environment["UV_CACHE_DIR"],
                "UV_NO_CONFIG": "1",
                "UV_PYTHON_INSTALL_DIR": final_environment["UV_PYTHON_INSTALL_DIR"],
                "UV_PYTHON_INSTALL_REGISTRY": "0",
                "UV_PYTHON_NO_REGISTRY": "1",
                "UV_PYTHON_PREFERENCE": "only-managed",
            },
            "proxy": {
                "admittedHosts": [
                    "api.github.com",
                    "files.pythonhosted.org",
                    "github.com",
                    "objects.githubusercontent.com",
                    "pypi.org",
                    "release-assets.githubusercontent.com",
                    "releases.astral.sh",
                ],
                "values": {
                    "ALL_PROXY": proxy,
                    "HTTPS_PROXY": proxy,
                    "HTTP_PROXY": proxy,
                    "NO_PROXY": "127.0.0.1,localhost",
                },
            },
            "roots": {
                "appData": str(evidence_root / "live/appdata"),
                "home": str(evidence_root / "live/home"),
                "localAppData": str(evidence_root / "live/localappdata"),
                "primeAgentDir": str(evidence_root / "live/prime-agent"),
                "projectLaunch": str(evidence_root / "live/project-launch"),
                "projectResume": str(evidence_root / "live/project-resume"),
                "rookDataDir": str(evidence_root / "live/rook-data"),
                "sessions": str(evidence_root / "live/sessions"),
                "temp": str(evidence_root / "live/temp"),
                "userProfile": str(evidence_root / "live/user-profile"),
            },
            "seededAmbientKeys": [
                "ALL_PROXY",
                "HtTp_PrOxY",
                "PI_OFFLINE",
                "PI_PACKAGE_DIR",
                "PRIME_AGENT_INSTALL_UV",
                "PRIME_AGENT_KERNEL_PYTHON",
                "PRIME_AGENT_KERNEL_VENV",
                "PYTHONDONTWRITEBYTECODE",
                "PYTHONHOME",
                "PYTHONPATH",
                "PYTHONPYCACHEPREFIX",
                "UV_CONFIG_FILE",
                "UV_DEFAULT_INDEX",
                "UV_EXTRA_INDEX_URL",
                "UV_FIND_LINKS",
                "UV_INDEX",
                "UV_OFFLINE",
                "UV_PYTHON_DOWNLOADS",
                "VIRTUAL_ENV",
                "all_proxy",
                "https_proxy",
                "pi_offline",
                "uv_no_config",
                "uv_unknown_future",
            ],
        },
        "evaluator": None,
        "evidenceRoot": str(evidence_root),
        "executionVersion": 1,
        "implementationCommit": "a" * 40,
        "inputs": {
            "sliceAPrompt": _content("exercise fake ACP boundary"),
            "sliceATestFiles": ["tests/test_chat_acp_process.py"],
            "sliceBCancelPrompt": _content("CANCEL_ME"),
            "sliceBFirstPrompt": _content("CREATE_AND_CALL_ROOK"),
            "sliceBReopenPrompt": _content("PROVE_CONTEXT"),
        },
        "kernel": {
            "pythonPath": str(evidence_root / "live/user-profile/.prime/agent/kernel-venv/Scripts/python.exe"),
            "runtimeSourceManifestSha256": "D" * 64,
            "runtimeSourcePath": str(actual_root / "dist/prime-agent-runtime"),
            "uvCachePath": final_environment["UV_CACHE_DIR"],
            "uvPythonInstallPath": final_environment["UV_PYTHON_INSTALL_DIR"],
            "venvPath": str(evidence_root / "live/user-profile/.prime/agent/kernel-venv"),
        },
        "launch": {
            "managedHelperAcquisitionReachable": False,
            "mcpServerName": "rook",
            "model": "qualification/test-model",
            "productionForbiddenArguments": ["--offline", "--no-managed-tool-downloads"],
            "productionRequiredArguments": ["--mode", "acp", "--no-daemon", "--no-approve"],
            "qualificationOnlyArguments": [
                "--offline",
                "--daemon-socket",
                r"\\.\pipe\rook-prime-acp-precontact-v1",
            ],
            "reasoning": "off",
        },
        "limits": {
            "maxEvidenceFileBytes": 1_048_576,
            "maxProcessOutputBytes": 1_048_576,
            "maxProxyLedgerBytes": 262_144,
            "maxProxyLedgerRecords": 256,
            "processCloseSeconds": 30,
            "tokenLimit": 4096,
            "wallClockSeconds": 1800,
        },
        "network": {
            "daemonSocket": r"\\.\pipe\rook-prime-acp-precontact-v1",
            "providerUrl": "http://127.0.0.1:48760/v1",
            "proxyUrl": proxy,
        },
        "protocolId": "rookchat-prime-acp-precontact",
        "runtime": {
            "acpCompatibilityVersion": 1,
            "installRoot": str(install_root),
            "manifestPath": str(manifest_path),
            "manifestSha256": runtime_id,
            "primeExecutableSha256": _sha(b"prime"),
            "rookSkillManifestSha256": "C" * 64,
            "runtimeId": runtime_id,
        },
        "schemaVersion": 1,
        "sourceInputs": [
            {"path": "authority.txt", "sha256": _sha(source_input.read_bytes())},
        ],
        "target": {
            "hostGenerationId": "11111111-1111-1111-1111-111111111111",
            "profile": "full",
            "rhinoDocumentSerial": 1,
            "routeProcessId": 1,
        },
    }
    return protocol, source, evidence_root


def test_external_common_runner_exists_outside_product_runtime() -> None:
    assert COMMON.is_file(), "MISSING_BEHAVIOR: finite external qualification runner"
    assert not COMMON.is_relative_to(REPO / "mcp_server/src/rook")


def test_canonical_json_has_exact_utf8_and_terminal_lf() -> None:
    common = _common()
    encode = _symbol(common, "canonical_json_bytes")
    assert encode({"z": "雪", "a": 1}) == b'{"a":1,"z":"\xe9\x9b\xaa"}\n'


@pytest.mark.parametrize("damage", ["duplicate", "unknown", "noncanonical", "missing_limit", "missing_launch"])
def test_protocol_wire_and_closed_schema_refuse_damage(tmp_path: Path, damage: str) -> None:
    common = _common()
    load = _symbol(common, "load_precontact_protocol")
    protocol, _, _ = _valid_protocol(tmp_path)
    path = tmp_path / "protocol.json"
    if damage == "duplicate":
        wire = _canonical(protocol).decode("utf-8").replace('{"environment":', '{"schemaVersion":1,"environment":', 1)
        path.write_text(wire, encoding="utf-8", newline="")
    elif damage == "unknown":
        protocol["unknown"] = True
        path.write_bytes(_canonical(protocol))
    elif damage == "noncanonical":
        path.write_text(json.dumps(protocol, indent=2), encoding="utf-8", newline="\n")
    elif damage == "missing_limit":
        del protocol["limits"]["processCloseSeconds"]
        path.write_bytes(_canonical(protocol))
    else:
        del protocol["launch"]
        path.write_bytes(_canonical(protocol))
    with pytest.raises(_symbol(common, "QualificationRefused")):
        load(path)


def test_protocol_admission_binds_runtime_source_and_fresh_evidence(tmp_path: Path) -> None:
    common = _common()
    admit = _symbol(common, "admit_precontact_protocol")
    protocol, source, evidence_root = _valid_protocol(tmp_path)
    path = tmp_path / "protocol.json"
    path.write_bytes(_canonical(protocol))

    admitted = admit(path, source, verify_git=False)
    assert admitted["runtime"]["runtimeId"] == protocol["runtime"]["runtimeId"]

    (source / "authority.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(_symbol(common, "QualificationRefused"), match="source input"):
        admit(path, source, verify_git=False)
    (source / "authority.txt").write_text("reviewed\n", encoding="utf-8", newline="\n")
    evidence_root.mkdir()
    with pytest.raises(_symbol(common, "QualificationRefused"), match="evidence root"):
        admit(path, source, verify_git=False)


def test_source_custody_requires_clean_descendant_and_unchanged_product(tmp_path: Path) -> None:
    common = _common()
    verify = _symbol(common, "verify_source_custody")
    repo = tmp_path / "repo"
    (repo / "mcp_server/src/rook").mkdir(parents=True)
    (repo / "mcp_server/src/rook/product.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Rook", "-c", "user.email=rook@example.invalid", "commit", "-qm", "base"],
        check=True,
    )
    base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    (repo / "qualification.txt").write_text("external\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "qualification.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Rook", "-c", "user.email=rook@example.invalid", "commit", "-qm", "qualification"],
        check=True,
    )
    verify(repo, base)

    (repo / "mcp_server/src/rook/product.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(_symbol(common, "QualificationRefused"), match="clean"):
        verify(repo, base)


def test_product_source_cannot_import_external_qualification(tmp_path: Path) -> None:
    common = _common()
    inspect_imports = _symbol(common, "assert_no_product_qualification_imports")
    product = tmp_path / "mcp_server/src/rook"
    product.mkdir(parents=True)
    clean = product / "clean.py"
    clean.write_text("import json\n", encoding="utf-8")
    inspect_imports(tmp_path)
    clean.write_text("from scripts.qualification import runner\n", encoding="utf-8")
    with pytest.raises(_symbol(common, "QualificationRefused"), match="product import"):
        inspect_imports(tmp_path)


def test_evidence_is_create_only_bounded_and_sealed(tmp_path: Path) -> None:
    common = _common()
    evidence_type = _symbol(common, "EvidenceRoot")
    root = tmp_path / "evidence"
    evidence = evidence_type.create(root, max_file_bytes=1024)
    evidence.write_json("result.json", {"ok": True})
    with pytest.raises(_symbol(common, "QualificationRefused"), match="exists"):
        evidence.write_json("result.json", {"ok": False})
    with pytest.raises(_symbol(common, "QualificationRefused"), match="byte limit"):
        evidence.write_bytes("large.bin", b"x" * 1025)
    index = evidence.seal()
    assert index.is_file()
    assert (root / "SEALED").is_file()
    assert not os.stat(root / "result.json").st_mode & stat.S_IWRITE
    with pytest.raises(_symbol(common, "QualificationRefused"), match="sealed"):
        evidence.write_json("later.json", {})

    for path in sorted(root.rglob("*"), reverse=True):
        path.chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
    root.chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)


@pytest.mark.asyncio
async def test_bounded_process_captures_output_and_timeout_cleans_direct_child(tmp_path: Path) -> None:
    common = _common()
    run = _symbol(common, "run_bounded_process")
    spec_type = _symbol(common, "ProcessSpec")
    ok = await run(
        spec_type(
            argv=(sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)"),
            cwd=tmp_path,
            environment=dict(os.environ),
            timeout_seconds=5,
            close_seconds=1,
            max_output_bytes=1024,
        )
    )
    assert ok.exit_code == 0
    assert ok.stdout == b"out\r\n" or ok.stdout == b"out\n"
    assert b"err" in ok.stderr

    timed = await run(
        spec_type(
            argv=(sys.executable, "-c", "import time; time.sleep(60)"),
            cwd=tmp_path,
            environment=dict(os.environ),
            timeout_seconds=0.05,
            close_seconds=1,
            max_output_bytes=1024,
        )
    )
    assert timed.timed_out
    assert timed.direct_child_exit_observed


@pytest.mark.asyncio
async def test_bounded_process_refuses_output_overflow(tmp_path: Path) -> None:
    common = _common()
    run = _symbol(common, "run_bounded_process")
    spec_type = _symbol(common, "ProcessSpec")
    result = await run(
        spec_type(
            argv=(sys.executable, "-c", "print('x' * 2048)"),
            cwd=tmp_path,
            environment=dict(os.environ),
            timeout_seconds=5,
            close_seconds=1,
            max_output_bytes=64,
        )
    )
    assert result.output_overflow
    assert result.direct_child_exit_observed


def test_deterministic_provider_drives_real_ipython_and_rook_mcp_call(tmp_path: Path) -> None:
    provider = _provider()
    plan = _symbol(provider, "plan_openai_response")
    assigned = tmp_path / "assigned.txt"
    chunks = plan(
        {
            "messages": [{"role": "user", "content": "CREATE_AND_CALL_ROOK"}],
            "tools": [{"type": "function", "function": {"name": "ipython"}}],
        },
        assigned,
    )
    call = chunks[0]["choices"][0]["delta"]["tool_calls"][0]
    assert call["function"]["name"] == "ipython"
    arguments = json.loads(call["function"]["arguments"])
    assert repr(str(assigned)) in arguments["code"]
    assert 'mcp.call_tool("rook", "qualification_echo"' in arguments["code"]
    assert chunks[-1]["choices"][0]["finish_reason"] == "tool_calls"


def test_deterministic_provider_requires_tool_result_and_prior_context(tmp_path: Path) -> None:
    provider = _provider()
    plan = _symbol(provider, "plan_openai_response")
    assigned = tmp_path / "assigned.txt"
    first = plan(
        {
            "messages": [
                {"role": "user", "content": "CREATE_AND_CALL_ROOK"},
                {"role": "assistant", "tool_calls": [{"id": "qualification-call-1"}]},
                {"role": "tool", "tool_call_id": "qualification-call-1", "content": "echo:alpha"},
            ]
        },
        assigned,
    )
    assert first[0]["choices"][0]["delta"]["content"] == "FIRST_OK:alpha"

    reopened_request = {
        "messages": [
            {"role": "user", "content": "CREATE_AND_CALL_ROOK"},
            {"role": "assistant", "content": "FIRST_OK:alpha"},
            {"role": "user", "content": "PROVE_CONTEXT"},
        ]
    }
    reopened = plan(reopened_request, assigned)
    assert reopened[0]["choices"][0]["delta"]["tool_calls"][0]["function"]["name"] == "ipython"
    reopened_request["messages"].append({"role": "tool", "content": "reopen MCP result"})
    settled = plan(reopened_request, assigned)
    assert settled[0]["choices"][0]["delta"]["content"] == "REOPEN_OK:FIRST_OK:alpha"

    missing_request = {"messages": [{"role": "user", "content": "PROVE_CONTEXT"}]}
    plan(missing_request, assigned)
    missing_request["messages"].append({"role": "tool", "content": "reopen MCP result"})
    missing = plan(missing_request, assigned)
    assert missing[0]["choices"][0]["delta"]["content"] == "CONTEXT_MISSING"


def test_provider_journal_projects_contract_markers_without_retaining_prompt_bytes(tmp_path: Path) -> None:
    provider = _provider()
    journal = _symbol(provider, "BoundedJsonlJournal")(tmp_path / "provider.jsonl", max_records=8, max_bytes=8192)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    server = _symbol(provider, "DeterministicProviderServer")(
        f"http://127.0.0.1:{port}/v1",
        tmp_path / "assigned.txt",
        journal,
    )
    body = _canonical(
        {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "ROOK_QUALIFICATION_GLOBAL_SYSTEM # RookChat Operating Contract "
                        "completion_budget_report"
                    ),
                },
                {"role": "user", "content": "CREATE_AND_CALL_ROOK"},
            ],
            "stream": True,
        }
    )
    with server:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request("POST", "/v1/chat/completions", body=body, headers={"Content-Length": str(len(body))})
        response = connection.getresponse()
        response.read()
        connection.close()
    assert response.status == 200
    rows = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    request = next(row for row in rows if row["event"] == "provider_request")
    assert request["globalSystemPresent"] is True
    assert request["goalSkillPresent"] is True
    assert request["rookContractPresent"] is True
    assert request["hostileMarkerPresent"] is False
    assert "messages" not in request


def test_goal_skill_marker_cannot_be_satisfied_by_rook_contract_alone() -> None:
    provider = _provider()
    markers = _symbol(provider, "project_context_markers")(
        "# RookChat Operating Contract await goal.get() await goal.complete()"
    )
    assert markers["rookContractPresent"] is True
    assert markers["goalSkillPresent"] is False
    markers = _symbol(provider, "project_context_markers")(
        "# RookChat Operating Contract completion_budget_report"
    )
    assert markers["goalSkillPresent"] is True


def test_deterministic_cancellation_uses_waiting_rook_tool(tmp_path: Path) -> None:
    provider = _provider()
    chunks = _symbol(provider, "plan_openai_response")(
        {"messages": [{"role": "user", "content": "CANCEL_ME"}]},
        tmp_path / "assigned.txt",
    )
    arguments = json.loads(chunks[0]["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"])
    assert 'mcp.call_tool("rook", "qualification_wait"' in arguments["code"]


def test_provider_sse_and_rook_envelope_are_closed() -> None:
    provider = _provider()
    wire = _symbol(provider, "encode_sse")(
        [{"id": "one", "choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": "stop"}]}]
    )
    assert wire.endswith(b"data: [DONE]\n\n")
    assert b"data: {\"choices\"" in wire
    assert _symbol(provider, "qualification_echo")({"value": "alpha"}) == {
        "success": True,
        "data": {"echo": "alpha"},
    }
    with pytest.raises(ValueError):
        _symbol(provider, "qualification_echo")({"value": 1})


@pytest.mark.asyncio
async def test_rook_mcp_double_uses_real_stdio_protocol(tmp_path: Path) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    journal = tmp_path / "mcp.jsonl"
    server = StdioServerParameters(
        command=sys.executable,
        args=[
            str(PROVIDER),
            "--rook-mcp",
            "--journal",
            str(journal),
            "--max-records",
            "16",
            "--max-bytes",
            "4096",
        ],
        cwd=str(REPO),
        env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"},
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
            result = await session.call_tool("qualification_echo", {"value": "wire"})

    assert [tool.name for tool in listed.tools] == ["qualification_echo", "qualification_wait"]
    assert result.isError is False
    assert result.structuredContent == {"success": True, "data": {"echo": "wire"}}
    rows = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert [row["event"] for row in rows] == [
        "mcp_process_started",
        "mcp_list_tools",
        "mcp_call_started",
        "mcp_call_finished",
    ]


def test_bounded_journal_refuses_overflow_and_is_create_only(tmp_path: Path) -> None:
    provider = _provider()
    journal_type = _symbol(provider, "BoundedJsonlJournal")
    journal = journal_type(tmp_path / "journal.jsonl", max_records=2, max_bytes=256)
    journal.append({"event": "one"})
    journal.append({"event": "two"})
    with pytest.raises(RuntimeError, match="record limit"):
        journal.append({"event": "three"})
    with pytest.raises(FileExistsError):
        journal_type(tmp_path / "journal.jsonl", max_records=2, max_bytes=256)


@pytest.mark.parametrize(
    ("authority", "expected"),
    [
        ("github.com:443", ("github.com", 443)),
        ("PYPI.ORG:443", ("pypi.org", 443)),
    ],
)
def test_proxy_authority_is_canonical_and_allowlisted(authority: str, expected: tuple[str, int]) -> None:
    provider = _provider()
    parsed = _symbol(provider, "admit_connect_authority")(authority, set(_common().ADMITTED_BOOTSTRAP_HOSTS))
    assert parsed == expected


@pytest.mark.parametrize("authority", ["evil.example:443", "github.com:80", "user@github.com:443", "github.com"])
def test_proxy_authority_refuses_unadmitted_or_malformed_targets(authority: str) -> None:
    provider = _provider()
    with pytest.raises(ValueError):
        _symbol(provider, "admit_connect_authority")(authority, set(_common().ADMITTED_BOOTSTRAP_HOSTS))


def test_deny_proxy_records_and_refuses_unadmitted_connect(tmp_path: Path) -> None:
    provider = _provider()
    journal = _symbol(provider, "BoundedJsonlJournal")(
        tmp_path / "proxy.jsonl",
        max_records=16,
        max_bytes=4096,
    )
    proxy = _symbol(provider, "ConnectProxyServer")(
        "http://127.0.0.1:0",
        set(_common().ADMITTED_BOOTSTRAP_HOSTS),
        journal,
    )
    with proxy:
        with socket.create_connection(("127.0.0.1", proxy.port), timeout=2) as client:
            client.sendall(b"CONNECT evil.example:443 HTTP/1.1\r\nHost: evil.example:443\r\n\r\n")
            response = client.recv(4096)
    assert b"403" in response
    rows = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    refusal = next(row for row in rows if row["event"] == "proxy_refused")
    assert refusal["authority"] == "evil.example:443"


def test_daemon_tripwire_counts_only_external_connections(tmp_path: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("named-pipe tripwire is Windows-only")
    provider = _provider()
    path = rf"\\.\pipe\rook-qualification-{os.getpid()}-{tmp_path.name}"
    tripwire = _symbol(provider, "NamedPipeTripwire")(path)
    with tripwire:
        from multiprocessing.connection import Client

        connection = Client(path, family="AF_PIPE", authkey=None)
        connection.close()
        tripwire.wait_for_contacts(1, timeout_seconds=2)
        assert tripwire.contact_count == 1
    assert tripwire.contact_count == 1


def _make_protocol_file(tmp_path: Path) -> tuple[Path, Path, Path]:
    protocol, source, evidence_root = _valid_protocol(tmp_path)
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_bytes(_canonical(protocol))
    return protocol_path, source, evidence_root


def _make_writable(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), reverse=True):
        path.chmod(stat.S_IREAD | stat.S_IWRITE | (stat.S_IEXEC if path.is_dir() else 0))
    root.chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)


@dataclass
class _FakePrecontactOperations:
    fail_slice: str | None = None

    def __post_init__(self) -> None:
        self.calls: list[str] = []

    async def run_slice_a(self, protocol: dict, repo_root: Path, evidence) -> dict:
        del protocol, repo_root, evidence
        self.calls.append("A")
        if self.fail_slice == "A":
            raise RuntimeError("configured Slice A failure")
        return {"outcome": "passed", "slice": "A"}

    async def run_slice_b(self, protocol: dict, repo_root: Path, evidence) -> dict:
        del protocol, repo_root, evidence
        self.calls.append("B")
        if self.fail_slice == "B":
            raise RuntimeError("configured Slice B failure")
        return {"outcome": "passed", "slice": "B"}


@pytest.mark.asyncio
async def test_precontact_admits_before_evidence_and_runs_a_then_b_once(tmp_path: Path) -> None:
    precontact = _precontact()
    protocol_path, source, evidence_root = _make_protocol_file(tmp_path)
    operations = _FakePrecontactOperations()
    try:
        result = await _symbol(precontact, "execute_precontact")(
            protocol_path,
            source,
            operations=operations,
            verify_git=False,
        )
        assert operations.calls == ["A", "B"]
        assert result == {"outcome": "passed", "sliceA": "passed", "sliceB": "passed"}
        assert (evidence_root / "slice-a.json").is_file()
        assert (evidence_root / "slice-b.json").is_file()
        assert (evidence_root / "result.json").is_file()
        assert (evidence_root / "SEALED").read_bytes() == b"sealed\n"
    finally:
        _make_writable(evidence_root)


@pytest.mark.asyncio
async def test_precontact_failure_is_sealed_and_never_advances(tmp_path: Path) -> None:
    precontact = _precontact()
    protocol_path, source, evidence_root = _make_protocol_file(tmp_path)
    operations = _FakePrecontactOperations(fail_slice="A")
    try:
        with pytest.raises(RuntimeError, match="configured Slice A failure"):
            await _symbol(precontact, "execute_precontact")(
                protocol_path,
                source,
                operations=operations,
                verify_git=False,
            )
        assert operations.calls == ["A"]
        failure = json.loads((evidence_root / "result.json").read_text(encoding="utf-8"))
        assert failure["outcome"] == "failed"
        assert failure["failedSlice"] == "A"
        assert (evidence_root / "SEALED").is_file()
    finally:
        _make_writable(evidence_root)


@pytest.mark.asyncio
async def test_precontact_admission_refusal_creates_no_evidence(tmp_path: Path) -> None:
    precontact = _precontact()
    protocol_path, source, evidence_root = _make_protocol_file(tmp_path)
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol["implementationCommit"] = "invalid"
    protocol_path.write_bytes(_canonical(protocol))
    operations = _FakePrecontactOperations()
    with pytest.raises(_symbol(_common(), "QualificationRefused")):
        await _symbol(precontact, "execute_precontact")(
            protocol_path,
            source,
            operations=operations,
            verify_git=False,
        )
    assert operations.calls == []
    assert not evidence_root.exists()


@pytest.mark.asyncio
async def test_slice_a_uses_the_frozen_public_model_free_commands(tmp_path: Path) -> None:
    precontact = _precontact()
    common = _common()
    protocol, source, evidence_root = _valid_protocol(tmp_path)
    evidence = _symbol(common, "EvidenceRoot").create(evidence_root, max_file_bytes=1_048_576)
    captured = []

    async def run(spec):
        captured.append(spec)
        return _symbol(common, "ProcessResult")(
            exit_code=0,
            stdout=b"passed\n",
            stderr=b"",
            timed_out=False,
            output_overflow=False,
            direct_child_exit_observed=True,
        )

    operations = _symbol(precontact, "ProductPrecontactOperations")(process_runner=run)
    result = await operations.run_slice_a(protocol, source, evidence)
    assert result["outcome"] == "passed"
    assert [row["label"] for row in result["commands"]] == [
        "python-acp-boundary",
        "managed-chat-panel",
        "browser-image-composer",
        "cutover-verifier",
        "installer-source-guard",
    ]
    assert captured[0].argv == (
        sys.executable,
        "-m",
        "pytest",
        "tests/test_chat_acp_process.py",
        "-q",
    )
    assert captured[0].cwd == source / "mcp_server"
    assert captured[1].argv[-1] == "FullyQualifiedName~Rook.Tests.UI.Chat"
    assert "src/Rook.Tests/UI/Chat/composer-images.test.cjs" in captured[2].argv
    assert captured[3].argv[-2:] == ("--root", str(source))
    assert captured[4].argv[-1] == "-SkipBuiltPayloadCheck"
    assert all(spec.environment == dict(os.environ) for spec in captured)


@pytest.mark.asyncio
async def test_slice_a_stops_on_first_failed_public_command(tmp_path: Path) -> None:
    precontact = _precontact()
    common = _common()
    protocol, source, evidence_root = _valid_protocol(tmp_path)
    evidence = _symbol(common, "EvidenceRoot").create(evidence_root, max_file_bytes=1_048_576)
    calls = 0

    async def fail(spec):
        nonlocal calls
        del spec
        calls += 1
        return _symbol(common, "ProcessResult")(
            exit_code=1,
            stdout=b"",
            stderr=b"failed\n",
            timed_out=False,
            output_overflow=False,
            direct_child_exit_observed=True,
        )

    operations = _symbol(precontact, "ProductPrecontactOperations")(process_runner=fail)
    with pytest.raises(_symbol(common, "QualificationRefused"), match="python-acp-boundary"):
        await operations.run_slice_a(protocol, source, evidence)
    assert calls == 1


def test_slice_b_preparation_uses_product_runtime_argv_and_environment(tmp_path: Path) -> None:
    precontact = _precontact()
    common = _common()
    protocol, source, _ = _valid_protocol(tmp_path)
    runtime_root = Path(protocol["runtime"]["manifestPath"]).parent
    contract = SimpleNamespace(
        runtime_id=protocol["runtime"]["runtimeId"],
        manifest_sha256=protocol["runtime"]["manifestSha256"],
        executable_path=runtime_root / "pi.exe",
        rook_skill_manifest_sha256=protocol["runtime"]["rookSkillManifestSha256"],
        uv_executable_path=runtime_root / "tools/uv/uv.exe",
        uv_version="0.12.3",
        prime_agent_runtime_path=runtime_root / "dist/prime-agent-runtime",
        prime_agent_runtime_manifest_sha256="D" * 64,
    )
    argv_calls = []

    def load_runtime(install_root: Path, runtime_id: str):
        assert install_root == Path(protocol["runtime"]["installRoot"])
        assert runtime_id == protocol["runtime"]["runtimeId"]
        return contract

    def build_argv(received, session_path, model, reasoning, reopen):
        assert received is contract
        argv_calls.append((session_path, model, reasoning, reopen))
        values = [str(contract.executable_path), "--mode", "acp", "--no-daemon", "--no-approve", "--resume", str(session_path)]
        if model is not None:
            values.extend(("--model", model))
        if reasoning is not None:
            values.extend(("--thinking", reasoning))
        return tuple(values)

    def build_env(base, received):
        assert received is contract
        assert base["PI_OFFLINE"] == "ambient-must-be-removed"
        assert base["uv_unknown_future"] == "ambient-must-be-removed"
        assert base["HTTP_PROXY"] == protocol["environment"]["proxy"]["values"]["HTTP_PROXY"]
        assert "HtTp_PrOxY" not in base
        return dict(protocol["environment"]["expectedFinal"])

    prepared = _symbol(precontact, "prepare_slice_b")(
        protocol,
        source,
        runtime_loader=load_runtime,
        argv_builder=build_argv,
        environment_builder=build_env,
    )
    qualification_arguments = tuple(protocol["launch"]["qualificationOnlyArguments"])
    assert prepared.initial_argv[-len(qualification_arguments) :] == qualification_arguments
    assert prepared.reopen_argv[-len(qualification_arguments) :] == qualification_arguments
    assert "--offline" not in prepared.product_initial_argv
    assert "--offline" not in prepared.product_reopen_argv
    assert prepared.environment == protocol["environment"]["expectedFinal"]
    assert argv_calls == [
        (
            Path(protocol["environment"]["roots"]["sessions"]) / "qualification-session.jsonl",
            "qualification/test-model",
            "off",
            False,
        ),
        (
            Path(protocol["environment"]["roots"]["sessions"]) / "qualification-session.jsonl",
            None,
            None,
            True,
        ),
    ]


@pytest.mark.parametrize("damage", ["product_offline", "environment"])
def test_slice_b_preparation_refuses_authority_drift(tmp_path: Path, damage: str) -> None:
    precontact = _precontact()
    protocol, source, _ = _valid_protocol(tmp_path)
    runtime_root = Path(protocol["runtime"]["manifestPath"]).parent
    contract = SimpleNamespace(
        runtime_id=protocol["runtime"]["runtimeId"],
        manifest_sha256=protocol["runtime"]["manifestSha256"],
        executable_path=runtime_root / "pi.exe",
        rook_skill_manifest_sha256=protocol["runtime"]["rookSkillManifestSha256"],
        uv_executable_path=runtime_root / "tools/uv/uv.exe",
        uv_version="0.12.3",
        prime_agent_runtime_path=runtime_root / "dist/prime-agent-runtime",
        prime_agent_runtime_manifest_sha256="D" * 64,
    )

    def build_argv(_contract, session_path, model, reasoning, reopen):
        del model, reasoning, reopen
        values = [str(contract.executable_path), "--mode", "acp", "--no-daemon", "--no-approve", "--resume", str(session_path)]
        if damage == "product_offline":
            values.append("--offline")
        return tuple(values)

    def build_env(_base, _contract):
        result = dict(protocol["environment"]["expectedFinal"])
        if damage == "environment":
            result["AMBIENT"] = "leak"
        return result

    with pytest.raises(_symbol(_common(), "QualificationRefused")):
        _symbol(precontact, "prepare_slice_b")(
            protocol,
            source,
            runtime_loader=lambda *_: contract,
            argv_builder=build_argv,
            environment_builder=build_env,
        )


def test_frozen_precontact_protocol_admits_the_installed_runtime_without_creating_evidence() -> None:
    common = _common()
    path = REPO / "scripts/qualification/protocols/rookchat-prime-acp-precontact-v1.json"
    protocol = _symbol(common, "admit_precontact_protocol")(path, REPO, verify_git=False)
    assert protocol["implementationCommit"] == "0900d913c1cc0e4bd76c2df018fbe0ac4fccac2e"
    assert protocol["runtime"]["runtimeId"] == "4BFA4A0500FECEAAEC737563623521562C5F4FDF2592EA443C956E0063A12579"
    assert protocol["environment"]["expectedFinalSha256"] == "00B8C5282670B6A9FB9DC890CC38A4D08D7B2919B813A15D18DFBC0CD9938B61"
    assert not Path(protocol["evidenceRoot"]).exists()


def test_slice_b_workspace_is_fresh_and_binds_hostile_and_global_resources(tmp_path: Path) -> None:
    precontact = _precontact()
    common = _common()
    protocol, source, evidence_root = _valid_protocol(tmp_path)
    evidence = _symbol(common, "EvidenceRoot").create(evidence_root, max_file_bytes=1_048_576)
    workspace = _symbol(precontact, "prepare_slice_b_workspace")(protocol, source, evidence)

    assert workspace.models_path == Path(protocol["environment"]["roots"]["primeAgentDir"]) / "models.json"
    models = json.loads(workspace.models_path.read_text(encoding="utf-8"))
    model = models["providers"]["qualification"]["models"][0]
    assert model == {
        "id": "qualification/test-model",
        "input": ["text"],
        "maxTokens": protocol["limits"]["tokenLimit"],
        "reasoning": False,
    }
    assert models["providers"]["qualification"]["baseUrl"] == protocol["network"]["providerUrl"]
    assert workspace.assigned_file == evidence_root / "live/assigned.txt"
    assert not workspace.assigned_file.exists()
    assert Path(workspace.provisional_association.session_path).parent == Path(
        protocol["environment"]["roots"]["sessions"]
    )
    assert not Path(workspace.provisional_association.session_path).exists()
    assert not Path(protocol["kernel"]["venvPath"]).exists()
    assert not Path(protocol["kernel"]["uvCachePath"]).exists()
    assert not Path(protocol["kernel"]["uvPythonInstallPath"]).exists()
    assert workspace.hostile_hashes
    for relative, digest in workspace.hostile_hashes.items():
        path = evidence_root / "live" / relative
        assert path.is_file()
        assert _sha(path.read_bytes()) == digest
    assert "ROOK_QUALIFICATION_GLOBAL_SYSTEM" in (workspace.models_path.parent / "SYSTEM.md").read_text(encoding="utf-8")


def test_slice_b_workspace_refuses_any_preexisting_isolated_root(tmp_path: Path) -> None:
    precontact = _precontact()
    common = _common()
    protocol, source, evidence_root = _valid_protocol(tmp_path)
    evidence = _symbol(common, "EvidenceRoot").create(evidence_root, max_file_bytes=1_048_576)
    Path(protocol["environment"]["roots"]["projectResume"]).mkdir(parents=True)
    with pytest.raises(_symbol(common, "QualificationRefused"), match="not fresh"):
        _symbol(precontact, "prepare_slice_b_workspace")(protocol, source, evidence)


@pytest.mark.asyncio
async def test_slice_b_entrypoint_prepares_product_contract_and_runs_lifecycle_once(tmp_path: Path) -> None:
    precontact = _precontact()
    common = _common()
    protocol, source, evidence_root = _valid_protocol(tmp_path)
    evidence = _symbol(common, "EvidenceRoot").create(evidence_root, max_file_bytes=1_048_576)
    prepared = object()
    calls = []
    preparation_calls = []

    def prepare(received_protocol, received_root, *, session_path):
        preparation_calls.append((received_protocol, received_root, session_path))
        return prepared

    async def lifecycle(received_protocol, received_root, received_evidence, received_prepared, workspace):
        calls.append((received_protocol, received_root, received_evidence, received_prepared, workspace))
        return {"outcome": "passed", "slice": "B"}

    operations = _symbol(precontact, "ProductPrecontactOperations")(
        slice_b_runner=lifecycle,
        slice_b_preparer=prepare,
    )
    result = await operations.run_slice_b(protocol, source, evidence)
    assert result == {"outcome": "passed", "slice": "B"}
    assert len(calls) == 1
    assert calls[0][:4] == (protocol, source, evidence, prepared)
    assert calls[0][4].models_path.is_file()
    assert preparation_calls == [
        (protocol, source, Path(calls[0][4].provisional_association.session_path))
    ]


def test_kernel_result_binds_bootstrap_to_manifest_runtime_source(tmp_path: Path) -> None:
    precontact = _precontact()
    common = _common()
    protocol, _source, _evidence_root = _valid_protocol(tmp_path)
    runtime_source = Path(protocol["kernel"]["runtimeSourcePath"])
    venv = Path(protocol["kernel"]["venvPath"])
    kernel_python = Path(protocol["kernel"]["pythonPath"])
    kernel_python.parent.mkdir(parents=True)
    kernel_python.write_bytes(b"python")
    Path(protocol["kernel"]["uvCachePath"]).mkdir(parents=True)
    managed = Path(protocol["kernel"]["uvPythonInstallPath"])
    managed.mkdir(parents=True)
    (managed / "cpython-3.11/python.exe").parent.mkdir(parents=True)
    (managed / "cpython-3.11/python.exe").write_bytes(b"managed")
    expected_identity = _runtime_source_identity_oracle(runtime_source)
    bootstrap = {
        "extraUvArgs": [
            "requests",
            "httpx",
            "pyyaml",
            "tomli",
            "python-dotenv",
            "pandas",
            "numpy",
            "scipy",
            "beautifulsoup4",
            "lxml",
            "pydantic",
            "tyro",
        ],
        "pythonSkills": [],
        "runtime": expected_identity,
        "schema": 9,
        "snapshot": "dill",
    }
    (venv / ".bootstrap-version").write_bytes(_canonical(bootstrap))

    result = _symbol(precontact, "_kernel_result")(protocol, runtime_source)

    assert result["runtimeSourceIdentity"] == expected_identity
    assert result["bootstrapVersionSha256"] == _sha(_canonical(bootstrap))

    bootstrap["runtime"] = "prime-agent-runtime"
    (venv / ".bootstrap-version").write_bytes(_canonical(bootstrap))
    with pytest.raises(_symbol(common, "QualificationRefused"), match="manifest-bound runtime source"):
        _symbol(precontact, "_kernel_result")(protocol, runtime_source)


class _FakeJournal:
    def __init__(self, path: Path, rows: list[dict]) -> None:
        self.path = path
        path.write_bytes(b"".join(_canonical(row) for row in rows))

    def append(self, value: dict) -> None:
        with self.path.open("ab") as stream:
            stream.write(_canonical(value))


class _FakeTripwire:
    contact_count = 0


class _FakeAcpProcess:
    def __init__(
        self,
        generation: int,
        claim,
        calls: list[tuple],
        cwd: Path,
        argv: tuple[str, ...],
        protocol: dict,
        assigned_file: Path,
        session_path: Path,
    ) -> None:
        self.generation = generation
        self.claim = claim
        self.calls = calls
        self.cwd = cwd
        self.argv = argv
        self.protocol = protocol
        self.assigned_file = assigned_file
        self.session_path = session_path
        self.session_id = None
        self._cancelled = asyncio.Event()
        self._mcp_journal = None

    async def initialize(self):
        self.calls.append((self.generation, "initialize"))
        return SimpleNamespace(image_supported=True)

    async def new_session(self, *, cwd, mcp_servers):
        self.calls.append((self.generation, "new_session", Path(cwd), tuple(mcp_servers)))
        self.session_id = f"acp-{self.generation}"
        args = list(mcp_servers[0].args)
        self._mcp_journal = Path(args[args.index("--journal") + 1])
        self._mcp_journal.write_bytes(
            _canonical({"event": "mcp_process_started"}) + _canonical({"event": "mcp_list_tools"})
        )
        if self.generation == 1:
            self.session_path.write_bytes(
                _canonical(
                    {
                        "cwd": self.protocol["environment"]["roots"]["projectResume"],
                        "id": self.session_id,
                        "type": "session",
                        "version": 3,
                    }
                )
            )
            Path(self.protocol["kernel"]["venvPath"]).mkdir(parents=True)
            kernel_python = Path(self.protocol["kernel"]["pythonPath"])
            kernel_python.parent.mkdir(parents=True)
            kernel_python.write_bytes(b"python")
            Path(self.protocol["kernel"]["uvCachePath"]).mkdir(parents=True)
            managed = Path(self.protocol["kernel"]["uvPythonInstallPath"])
            managed.mkdir(parents=True)
            (managed / "python.exe").write_bytes(b"managed")
            runtime_source = Path(self.protocol["kernel"]["runtimeSourcePath"])
            (Path(self.protocol["kernel"]["venvPath"]) / ".bootstrap-version").write_bytes(
                _canonical(
                    {
                        "extraUvArgs": [
                            "requests",
                            "httpx",
                            "pyyaml",
                            "tomli",
                            "python-dotenv",
                            "pandas",
                            "numpy",
                            "scipy",
                            "beautifulsoup4",
                            "lxml",
                            "pydantic",
                            "tyro",
                        ],
                        "pythonSkills": [],
                        "runtime": _runtime_source_identity_oracle(runtime_source),
                        "schema": 9,
                        "snapshot": "dill",
                    }
                )
            )
        return self.session_id

    async def prompt(self, blocks, *, generation, projection):
        text = blocks[0].text
        self.calls.append((self.generation, "prompt", text, generation))
        if text == "CANCEL_ME":
            with self._mcp_journal.open("ab") as stream:
                stream.write(_canonical({"event": "mcp_call_started", "name": "qualification_wait"}))
            await self._cancelled.wait()
            return SimpleNamespace(stop_reason="cancelled")
        if text == "CREATE_AND_CALL_ROOK":
            self.assigned_file.write_bytes(b"qualified\n")
            projection.accumulate_assistant_text("FIRST_OK:alpha")
            with self._mcp_journal.open("ab") as stream:
                stream.write(_canonical({"event": "mcp_call_finished", "name": "qualification_echo"}))
            return SimpleNamespace(stop_reason="end_turn")
        projection.accumulate_assistant_text("REOPEN_OK:FIRST_OK:alpha")
        with self._mcp_journal.open("ab") as stream:
            stream.write(_canonical({"event": "mcp_call_finished", "name": "qualification_echo"}))
        return SimpleNamespace(stop_reason="end_turn")

    async def cancel(self):
        self.calls.append((self.generation, "cancel"))
        self._cancelled.set()

    async def retire(self, *, send_close=True, release_claim=True):
        self.calls.append((self.generation, "retire", send_close, release_claim))
        if release_claim:
            self.claim.release_after_observed_exit()
        return SimpleNamespace(
            clean=True,
            child_exit_observed=True,
            stderr_failure_code=None,
            stderr_total_bytes=0,
            stderr_truncated=False,
        )


@pytest.mark.asyncio
async def test_installed_slice_b_lifecycle_uses_exact_handles_and_reopens_with_fresh_mcp(tmp_path: Path) -> None:
    precontact = _precontact()
    common = _common()
    protocol, source, evidence_root = _valid_protocol(tmp_path)
    evidence = _symbol(common, "EvidenceRoot").create(evidence_root, max_file_bytes=1_048_576)
    workspace = _symbol(precontact, "prepare_slice_b_workspace")(protocol, source, evidence)
    fixture = source / "scripts/qualification/fixtures/deterministic_provider.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("# fixture\n", encoding="utf-8", newline="\n")
    prepared = SimpleNamespace(
        contract=SimpleNamespace(
            prime_agent_runtime_manifest_sha256=protocol["kernel"]["runtimeSourceManifestSha256"],
            prime_agent_runtime_path=Path(protocol["kernel"]["runtimeSourcePath"]),
            uv_executable_path=Path(protocol["runtime"]["manifestPath"]).parent / "tools/uv/uv.exe",
            uv_version="0.12.3",
        ),
        environment=dict(protocol["environment"]["expectedFinal"]),
        initial_argv=("pi.exe", "initial"),
        reopen_argv=("pi.exe", "reopen"),
        session_path=Path(workspace.provisional_association.session_path),
    )
    prepared.contract.uv_executable_path.parent.mkdir(parents=True)
    prepared.contract.uv_executable_path.write_bytes(b"uv")
    calls: list[tuple] = []

    async def start(argv, environment, claim, generation, cwd):
        assert environment == prepared.environment
        calls.append((generation, "start", argv, cwd))
        return _FakeAcpProcess(
            generation,
            claim,
            calls,
            cwd,
            argv,
            protocol,
            workspace.assigned_file,
            prepared.session_path,
        )

    provider_rows = [
        {
            "event": "provider_request",
            "globalSystemPresent": True,
            "goalSkillPresent": True,
            "hostileMarkerPresent": False,
            "rookContractPresent": True,
        }
    ]
    services = SimpleNamespace(
        daemon_tripwire=_FakeTripwire(),
        provider_journal=_FakeJournal(evidence_root / "live/provider.jsonl", provider_rows),
        proxy_journal=_FakeJournal(evidence_root / "live/proxy.jsonl", [{"event": "proxy_started"}]),
    )

    @contextlib.contextmanager
    def service_factory(*_args):
        yield services

    result = await _symbol(precontact, "run_installed_slice_b")(
        protocol,
        source,
        evidence,
        prepared,
        workspace,
        process_starter=start,
        services_factory=service_factory,
    )
    assert result["outcome"] == "passed"
    assert result["firstAssistantText"] == "FIRST_OK:alpha"
    assert result["reopenAssistantText"] == "REOPEN_OK:FIRST_OK:alpha"
    assert result["cancelStopReason"] == "cancelled"
    assert [call[:2] for call in calls] == [
        (1, "start"),
        (1, "initialize"),
        (1, "new_session"),
        (1, "prompt"),
        (1, "prompt"),
        (1, "cancel"),
        (1, "retire"),
        (2, "start"),
        (2, "initialize"),
        (2, "new_session"),
        (2, "prompt"),
        (2, "retire"),
    ]
    assert calls[0][2] == prepared.initial_argv
    assert calls[7][2] == prepared.reopen_argv
    assert calls[2][2] == Path(protocol["environment"]["roots"]["projectResume"])
    assert calls[9][2] == Path(protocol["environment"]["roots"]["projectResume"])
    assert all(not path.exists() for path in workspace.claims_root.glob("*.open.claim"))
    for relative, digest in workspace.hostile_hashes.items():
        assert _sha((evidence_root / "live" / relative).read_bytes()) == digest


@pytest.mark.asyncio
async def test_installed_slice_b_revalidates_durable_session_before_reopen(tmp_path: Path) -> None:
    precontact = _precontact()
    common = _common()
    protocol, source, evidence_root = _valid_protocol(tmp_path)
    evidence = _symbol(common, "EvidenceRoot").create(evidence_root, max_file_bytes=1_048_576)
    workspace = _symbol(precontact, "prepare_slice_b_workspace")(protocol, source, evidence)
    fixture = source / "scripts/qualification/fixtures/deterministic_provider.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("# fixture\n", encoding="utf-8", newline="\n")
    prepared = SimpleNamespace(
        contract=SimpleNamespace(
            prime_agent_runtime_manifest_sha256=protocol["kernel"]["runtimeSourceManifestSha256"],
            prime_agent_runtime_path=Path(protocol["kernel"]["runtimeSourcePath"]),
            uv_executable_path=Path(protocol["runtime"]["manifestPath"]).parent / "tools/uv/uv.exe",
            uv_version="0.12.3",
        ),
        environment=dict(protocol["environment"]["expectedFinal"]),
        initial_argv=("pi.exe", "initial"),
        reopen_argv=("pi.exe", "reopen"),
        session_path=Path(workspace.provisional_association.session_path),
    )
    prepared.contract.uv_executable_path.parent.mkdir(parents=True)
    prepared.contract.uv_executable_path.write_bytes(b"uv")
    calls: list[tuple] = []

    async def start(argv, environment, claim, generation, cwd):
        del environment
        calls.append((generation, "start", argv, cwd))
        process = _FakeAcpProcess(
            generation,
            claim,
            calls,
            cwd,
            argv,
            protocol,
            workspace.assigned_file,
            prepared.session_path,
        )
        if generation == 1:
            retire = process.retire

            async def retire_then_corrupt(*, send_close=True, release_claim=True):
                result = await retire(send_close=send_close, release_claim=release_claim)
                prepared.session_path.write_bytes(
                    _canonical(
                        {
                            "cwd": protocol["environment"]["roots"]["projectResume"],
                            "id": "substituted-session",
                            "type": "session",
                            "version": 3,
                        }
                    )
                )
                return result

            process.retire = retire_then_corrupt
        return process

    provider_rows = [
        {
            "event": "provider_request",
            "globalSystemPresent": True,
            "goalSkillPresent": True,
            "hostileMarkerPresent": False,
            "rookContractPresent": True,
        }
    ]
    services = SimpleNamespace(
        daemon_tripwire=_FakeTripwire(),
        provider_journal=_FakeJournal(evidence_root / "live/provider.jsonl", provider_rows),
        proxy_journal=_FakeJournal(evidence_root / "live/proxy.jsonl", [{"event": "proxy_started"}]),
    )

    @contextlib.contextmanager
    def service_factory(*_args):
        yield services

    with pytest.raises(Exception, match="header ID"):
        await _symbol(precontact, "run_installed_slice_b")(
            protocol,
            source,
            evidence,
            prepared,
            workspace,
            process_starter=start,
            services_factory=service_factory,
        )
    assert [call for call in calls if call[1] == "start"] == [calls[0]]
    assert all(not path.exists() for path in workspace.claims_root.glob("*.open.claim"))


@pytest.mark.asyncio
async def test_installed_slice_b_failure_retires_only_the_started_handle(tmp_path: Path) -> None:
    precontact = _precontact()
    common = _common()
    protocol, source, evidence_root = _valid_protocol(tmp_path)
    evidence = _symbol(common, "EvidenceRoot").create(evidence_root, max_file_bytes=1_048_576)
    workspace = _symbol(precontact, "prepare_slice_b_workspace")(protocol, source, evidence)
    fixture = source / "scripts/qualification/fixtures/deterministic_provider.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("# fixture\n", encoding="utf-8", newline="\n")
    prepared = SimpleNamespace(
        contract=SimpleNamespace(),
        environment=dict(protocol["environment"]["expectedFinal"]),
        initial_argv=("pi.exe", "initial"),
        reopen_argv=("pi.exe", "reopen"),
        session_path=Path(workspace.provisional_association.session_path),
    )
    calls: list[tuple] = []

    async def start(argv, environment, claim, generation, cwd):
        process = _FakeAcpProcess(
            generation,
            claim,
            calls,
            cwd,
            argv,
            protocol,
            workspace.assigned_file,
            prepared.session_path,
        )

        async def fail_initialize():
            calls.append((generation, "initialize"))
            raise RuntimeError("synthetic initialize failure")

        process.initialize = fail_initialize
        calls.append((generation, "start", argv, cwd))
        return process

    services = SimpleNamespace(
        daemon_tripwire=_FakeTripwire(),
        provider_journal=_FakeJournal(evidence_root / "live/provider.jsonl", []),
        proxy_journal=_FakeJournal(evidence_root / "live/proxy.jsonl", []),
    )

    @contextlib.contextmanager
    def service_factory(*_args):
        yield services

    with pytest.raises(RuntimeError, match="synthetic initialize failure"):
        await _symbol(precontact, "run_installed_slice_b")(
            protocol,
            source,
            evidence,
            prepared,
            workspace,
            process_starter=start,
            services_factory=service_factory,
        )
    assert [call[:2] for call in calls] == [(1, "start"), (1, "initialize"), (1, "retire")]
    assert all(not path.exists() for path in workspace.claims_root.glob("*.open.claim"))
