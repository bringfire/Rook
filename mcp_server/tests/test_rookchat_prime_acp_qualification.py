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


@pytest.fixture(autouse=True)
def _local_contact_only(monkeypatch):
    connect = socket.socket.connect
    resolve = socket.getaddrinfo
    popen = subprocess.Popen

    def guarded_connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1", "localhost"}:
            raise AssertionError(f"external network forbidden: {address}")
        return connect(sock, address)

    class GuardedPopen(popen):
        def __init__(self, argv, *args, **kwargs):
            executable = Path(argv[0]) if isinstance(argv, (list, tuple)) else Path(str(argv))
            if kwargs.get("shell") or (executable != Path(sys.executable) and executable.name.lower() not in {"git", "git.exe"}):
                raise AssertionError(f"unadmitted test process: {executable}")
            super().__init__(argv, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    def guarded_resolve(host, *args, **kwargs):
        if host not in {"127.0.0.1", "::1", "localhost", None}:
            raise AssertionError(f"external DNS forbidden: {host}")
        return resolve(host, *args, **kwargs)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_resolve)
    monkeypatch.setattr(subprocess, "Popen", GuardedPopen)


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
    execution_root = tmp_path / "execution"
    proxy = "http://127.0.0.1:48761"
    final_environment = {
        "ALL_PROXY": proxy,
        "APPDATA": str(execution_root / "appdata"),
        "HOME": str(execution_root / "home"),
        "HTTPS_PROXY": proxy,
        "HTTP_PROXY": proxy,
        "LOCALAPPDATA": str(execution_root / "localappdata"),
        "NO_PROXY": "127.0.0.1,localhost",
        "PATH": str(actual_root / "tools/uv"),
        "PRIME_AGENT_CODING_AGENT_DIR": str(execution_root / "prime-agent"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "ROOK_DATA_DIR": str(execution_root / "rook-data"),
        "TEMP": str(execution_root / "temp"),
        "TMP": str(execution_root / "temp"),
        "USERPROFILE": str(execution_root / "user-profile"),
        "UV_CACHE_DIR": str(execution_root / "rook-data/rookchat/acp/v1/prime-uv/cache"),
        "UV_NO_CONFIG": "1",
        "UV_PYTHON_INSTALL_DIR": str(execution_root / "rook-data/rookchat/acp/v1/prime-uv/python"),
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
                "appData": str(execution_root / "appdata"),
                "home": str(execution_root / "home"),
                "localAppData": str(execution_root / "localappdata"),
                "primeAgentDir": str(execution_root / "prime-agent"),
                "projectLaunch": str(execution_root / "project-launch"),
                "projectResume": str(execution_root / "project-resume"),
                "rookDataDir": str(execution_root / "rook-data"),
                "sessions": str(execution_root / "rook-data/rookchat/acp/v1/sessions"),
                "temp": str(execution_root / "temp"),
                "userProfile": str(execution_root / "user-profile"),
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
        "executionRoot": str(execution_root),
        "qualificationConversationId": "11111111111141118111111111111111",
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
            "pythonPath": str(execution_root / "user-profile/.prime/agent/kernel-venv/Scripts/python.exe"),
            "runtimeSourceManifestSha256": "D" * 64,
            "runtimeSourcePath": str(actual_root / "dist/prime-agent-runtime"),
            "uvCachePath": final_environment["UV_CACHE_DIR"],
            "uvPythonInstallPath": final_environment["UV_PYTHON_INSTALL_DIR"],
            "venvPath": str(execution_root / "user-profile/.prime/agent/kernel-venv"),
        },
        "launch": {
            "managedHelperAcquisitionReachable": False,
            "mcpServerName": "rook",
            "model": "qualification/test-model",
            "productionForbiddenArguments": ["--offline"],
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
            "maxEvidenceTotalBytes": 67108864,
            "maxEvidenceFiles": 64,
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


def test_correction_slice_a_environment_is_explicit(tmp_path, monkeypatch):
    protocol, source, _ = _valid_protocol(tmp_path)
    poison = ("ANTHROPIC_API_KEY", "HtTp_PrOxY", "PI_OFFLINE", "UV_INDEX", "PYTHONHOME", "PYTHONPATH",
              "NODE_OPTIONS", "NPM_CONFIG_USERCONFIG", "PYTEST_ADDOPTS", "PRIME_AGENT_KERNEL_VENV")
    for key in poison:
        monkeypatch.setenv(key, "must-not-reach-child")
    for _, spec in _precontact().ProductPrecontactOperations._slice_a_commands(protocol, source):
        assert not set(poison).intersection(spec.environment)
        assert Path(spec.argv[0]).is_absolute()
        assert spec.environment["HOME"] != os.environ.get("HOME")


@pytest.mark.parametrize("damage", [None, "relative", "missing-directory", "Eto.dll", "Eto.Wpf.dll",
                                    "Microsoft.WindowsAPICodePack.dll", "Microsoft.WindowsAPICodePack.Shell.dll",
                                    "Xceed.Wpf.Toolkit.dll", "assembly-directory"])
def test_slice_a_managed_assembly_admission(tmp_path, monkeypatch, damage):
    precontact = _precontact()
    protocol, source, _ = _valid_protocol(tmp_path)
    system = tmp_path / "Rhino 8" / "System"
    system.mkdir(parents=True)
    names = ("Eto.dll", "Eto.Wpf.dll", "Microsoft.WindowsAPICodePack.dll",
             "Microsoft.WindowsAPICodePack.Shell.dll", "Xceed.Wpf.Toolkit.dll")
    for name in names:
        (system / name).write_bytes(b"fixture assembly")
    if damage in names:
        (system / damage).unlink()
    elif damage == "assembly-directory":
        (system / "Eto.dll").unlink()
        (system / "Eto.dll").mkdir()
    candidate = Path("relative/System") if damage == "relative" else (
        tmp_path / "absent" if damage == "missing-directory" else system)
    monkeypatch.setattr(precontact, "SLICE_A_RHINO_SYSTEM_DIR", candidate, raising=False)

    def no_launch(*args, **kwargs):
        pytest.fail("assembly admission must occur before any child launch")

    monkeypatch.setattr(subprocess, "Popen", no_launch)
    if damage is not None:
        with pytest.raises(_common().QualificationRefused, match="Rhino.*(directory|assembly)"):
            precontact.ProductPrecontactOperations._slice_a_commands(protocol, source)
    else:
        commands = precontact.ProductPrecontactOperations._slice_a_commands(protocol, source)
        for label, spec in commands:
            properties = [arg for arg in spec.argv if arg.startswith("-p:RhinoSystemDir=")]
            assert properties == ([f"-p:RhinoSystemDir={system.resolve()}"] if label == "managed-chat-panel" else [])
            assert not {"programfiles", "programfiles(x86)", "programw6432"}.intersection(
                key.lower() for key in spec.environment)


@pytest.mark.asyncio
async def test_slice_a_python_child_resolves_selected_git_not_ambient_tools(tmp_path, monkeypatch):
    import shutil
    from dataclasses import replace
    protocol, source, _ = _valid_protocol(tmp_path)
    ambient = tmp_path / "ambient"
    ambient.mkdir()
    (ambient / "unrelated-ambient.exe").write_bytes(b"not executable")
    monkeypatch.setenv("PATH", str(ambient) + os.pathsep + os.environ["PATH"])
    selected_git = Path(_precontact()._required_executable("git"))
    assert shutil.which("unrelated-ambient") is not None
    _, generated = _precontact().ProductPrecontactOperations._slice_a_commands(protocol, source)[0]
    generated.cwd.mkdir(parents=True, exist_ok=True)
    probe = "import json,shutil; print(json.dumps([shutil.which('git'),shutil.which('unrelated-ambient')]))"
    result = await _common().run_bounded_process(replace(generated, argv=(generated.argv[0], "-I", "-c", probe)))
    assert result.exit_code == 0 and result.direct_child_exit_observed
    git, unrelated = json.loads(result.stdout)
    assert git is not None, "Slice A child cannot resolve its required Git executable"
    assert Path(git).resolve() == selected_git
    assert unrelated is None
    assert str(ambient) not in generated.environment["PATH"].split(os.pathsep)


def test_correction_evidence_reserves_terminal_budget(tmp_path):
    common = _common()
    evidence = common.EvidenceRoot.create(tmp_path / "evidence", max_file_bytes=1024,
                                          max_total_bytes=4096, max_files=4)
    evidence.write_bytes("log", b"x" * 1024)
    with pytest.raises(common.QualificationRefused, match="limit"):
        evidence.write_bytes("extra", b"x")
    evidence.write_json("result.json", {"outcome": "failed"})
    evidence.seal()
    assert len(list(evidence.root.iterdir())) == 4
    _make_writable(evidence.root)


def test_correction_evidence_does_not_adopt_unknown_or_workspace_files(tmp_path):
    common = _common()
    evidence = common.EvidenceRoot.create(tmp_path / "evidence", max_file_bytes=1024)
    workspace = tmp_path / "execution"
    workspace.mkdir()
    (workspace / "cache").write_bytes(b"x" * 4096)
    (evidence.root / "unowned").write_bytes(b"bad")
    with pytest.raises(common.QualificationRefused, match="unknown"):
        evidence.seal()
    assert not (evidence.root / "SEALED").exists()
    (evidence.root / "unowned").unlink()
    evidence.write_json("result.json", {})
    evidence.seal()
    assert b"cache" not in (evidence.root / "evidence-index.json").read_bytes()
    assert (workspace / "cache").stat().st_size == 4096
    _make_writable(evidence.root)


@pytest.mark.asyncio
async def test_correction_caller_cancellation_retires_exact_sleeping_child(tmp_path, monkeypatch):
    common = _common()
    started = asyncio.Event()
    processes = []
    spawn = asyncio.create_subprocess_exec

    async def capture(*args, **kwargs):
        process = await spawn(*args, **kwargs)
        processes.append(process)
        started.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)
    spec = common.ProcessSpec((sys.executable, "-I", "-c", "import time; time.sleep(30)"),
                              tmp_path, {"SYSTEMROOT": os.environ["SYSTEMROOT"]}, 5, .2, 1024)
    task = asyncio.create_task(common.run_bounded_process(spec))
    try:
        await asyncio.wait_for(started.wait(), 3)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=1)
        observed = processes[0].returncode is not None
        assert task in done and observed, "caller cancellation did not retire the exact child"
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        for process in processes:
            if process.returncode is None:
                process.kill()
            await asyncio.wait_for(process.wait(), 3)
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 3)


@pytest.mark.parametrize("kind", ["provider", "proxy"])
def test_correction_unobserved_service_thread_refuses_close(tmp_path, kind):
    provider = _provider()
    journal = provider.BoundedJsonlJournal(tmp_path / "journal", max_records=10, max_bytes=1024)
    service = (provider.DeterministicProviderServer("http://127.0.0.1:1234/v1", tmp_path / "assigned", journal)
               if kind == "provider" else provider.ConnectProxyServer("http://127.0.0.1:1234", {"pypi.org"}, journal))
    service._server = SimpleNamespace(shutdown=lambda: None, server_close=lambda: None)
    thread = SimpleNamespace(ident=1, join=lambda **_: None, is_alive=lambda: True)
    service._thread = thread
    with pytest.raises(RuntimeError, match="thread"):
        service.close()
    assert service._thread is thread
    assert b"stopped" not in journal.path.read_bytes()


def test_correction_session_path_admitted_without_product_roots(tmp_path, monkeypatch):
    protocol, source, evidence_root = _valid_protocol(tmp_path)
    from rook.agent.chat.acp_storage import AssociationStore
    import rook.runtime_paths as runtime_paths
    monkeypatch.setattr(runtime_paths, "resolve_runtime_paths", lambda: pytest.fail("ambient data discovery"))
    path_builder = _symbol(_precontact(), "qualification_data_paths")
    paths = path_builder(protocol)
    canonical = runtime_paths.AcpDataPaths.from_runtime_paths(SimpleNamespace(
        data_root=Path(protocol["environment"]["roots"]["rookDataDir"])))
    assert paths == canonical
    admitted = paths.session_path(protocol["qualificationConversationId"])
    assert not Path(protocol["executionRoot"]).exists()
    monkeypatch.setattr(AssociationStore, "reserve_provisional", lambda *_a, **_k: pytest.fail("second allocation"))
    evidence = _common().EvidenceRoot.create(evidence_root, max_file_bytes=1048576)
    workspace = _precontact().prepare_slice_b_workspace(protocol, source, evidence)
    assert Path(workspace.provisional_association.session_path) == admitted
    assert workspace.provisional_association.conversation_id == protocol["qualificationConversationId"]


def test_producer_contract_rejects_nonproduct_session_topology(tmp_path):
    protocol, _, _ = _valid_protocol(tmp_path)
    protocol["environment"]["roots"]["sessions"] = str(Path(protocol["executionRoot"]) / "invented-sessions")
    with pytest.raises(_common().QualificationRefused, match="session.*topology"):
        _precontact().qualification_data_paths(protocol)
    assert not Path(protocol["executionRoot"]).exists()


@pytest.mark.parametrize("mode", ["help", "wrong-head"])
def test_producer_contract_real_operator_cli(tmp_path, mode):
    import shutil
    environment = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR")}
    environment.update(HOME=str(tmp_path), USERPROFILE=str(tmp_path), PYTHONDONTWRITEBYTECODE="1",
                       GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
                       PATH=os.pathsep.join([str(Path(shutil.which("git")).parent), str(Path(os.environ["SYSTEMROOT"]) / "System32")]))
    roots = [tmp_path / "evidence", tmp_path / "execution"]
    args = ["--help"]
    if mode == "wrong-head":
        repo = tmp_path / "repo"
        protocol_path = repo / "scripts/qualification/protocols/rookchat-prime-acp-precontact-v1.json"
        protocol_path.parent.mkdir(parents=True)
        protocol = json.loads((REPO / protocol_path.relative_to(repo)).read_bytes())
        protocol.update(evidenceRoot=str(roots[0]), executionRoot=str(roots[1]))
        protocol_path.write_bytes(_canonical(protocol))
        for command in (["git", "init", "-q", str(repo)],
                        ["git", "-C", str(repo), "-c", "user.name=Rook", "-c", "user.email=rook@example.invalid",
                         "commit", "--allow-empty", "-qm", "fixture"]):
            subprocess.run(command, env=environment, capture_output=True, check=True, timeout=15)
        args = ["--repo-root", str(repo), "--protocol", str(protocol_path),
                "--expected-qualification-commit", "0" * 40]
    assert all(not root.exists() for root in roots)
    result = subprocess.run([sys.executable, "-I", str(PRECONTACT), *args], cwd=REPO,
                            env=environment, capture_output=True, text=True, timeout=15)
    assert result.returncode == (0 if mode == "help" else 1), result.stderr
    expected = "--expected-qualification-commit" if mode == "help" else "precontact_refused: qualification HEAD differs"
    assert expected in result.stdout, result.stderr
    assert all(not root.exists() for root in roots)


@pytest.mark.parametrize("kind,failure", [(kind, failure) for kind in ("provider", "proxy")
                                         for failure in ("thread-start", "journal")])
def test_producer_contract_partial_service_startup(tmp_path, monkeypatch, kind, failure):
    provider = _provider()
    journal = provider.BoundedJsonlJournal(tmp_path / "journal", max_records=20, max_bytes=4096)
    service = (provider.DeterministicProviderServer("http://127.0.0.1:0/v1", tmp_path / "assigned", journal)
               if kind == "provider" else provider.ConnectProxyServer("http://127.0.0.1:0", {"pypi.org"}, journal))
    resources, threads = [], []
    name = "_ProviderServer" if kind == "provider" else "_ThreadingProxyServer"
    factory = getattr(provider, name)
    def capture(*args, **kwargs):
        resource = factory(*args, **kwargs)
        resources.append(resource)
        return resource
    monkeypatch.setattr(provider, name, capture)
    start = provider.threading.Thread.start
    error = RuntimeError("injected partial startup")
    def start_thread(thread):
        threads.append(thread)
        if failure == "thread-start":
            raise error
        return start(thread)
    monkeypatch.setattr(provider.threading.Thread, "start", start_thread)
    append = journal.append
    def append_record(row):
        if row["event"].endswith("_started"):
            raise error
        append(row)
    if failure == "journal":
        monkeypatch.setattr(journal, "append", append_record)
    try:
        with pytest.raises(RuntimeError) as raised:
            with service:
                pytest.fail("partial startup entered service body")
        assert raised.value is error
        assert all(not thread.is_alive() for thread in threads)
        assert resources[0].socket.fileno() == -1
    finally:
        # Exact test-owned handles must be reclaimed even while the regression is RED.
        for resource in resources:
            if any(thread.is_alive() for thread in threads):
                resource.shutdown()
            resource.server_close()
        for thread in threads:
            if thread.ident is not None:
                thread.join(timeout=2)


def test_producer_contract_partial_tripwire_startup(tmp_path, monkeypatch):
    provider = _provider()
    import uuid
    service = provider.NamedPipeTripwire(r"\\.\pipe\rook-test-partial-" + uuid.uuid4().hex)
    listeners = []
    factory = provider.Listener
    def capture(*args, **kwargs):
        listener = factory(*args, **kwargs)
        listeners.append(listener)
        return listener
    monkeypatch.setattr(provider, "Listener", capture)
    def fail_start(_):
        raise RuntimeError("injected tripwire thread start")
    monkeypatch.setattr(provider.threading.Thread, "start", fail_start)
    try:
        with pytest.raises(RuntimeError, match="injected tripwire"):
            with service:
                pytest.fail("partial startup entered tripwire body")
        assert listeners[0]._listener is None
        assert service._listener is None
    finally:
        for listener in listeners:
            listener.close()


def test_producer_contract_service_composition_unwinds_partial_proxy(tmp_path, monkeypatch):
    provider = _provider()
    protocol, _, _ = _valid_protocol(tmp_path)
    execution = Path(protocol["executionRoot"])
    execution.mkdir()
    protocol["network"].update(providerUrl="http://127.0.0.1:0/v1", proxyUrl="http://127.0.0.1:0")
    threads = []
    start = provider.threading.Thread.start
    def capture(thread):
        threads.append(thread)
        return start(thread)
    monkeypatch.setattr(provider.threading.Thread, "start", capture)
    append = provider.BoundedJsonlJournal.append
    def fail_proxy(journal, row):
        if row["event"] == "proxy_started":
            raise RuntimeError("proxy publication failed")
        append(journal, row)
    monkeypatch.setattr(provider.BoundedJsonlJournal, "append", fail_proxy)
    monkeypatch.setattr(provider.NamedPipeTripwire, "start", lambda _: pytest.fail("tripwire started after proxy failure"))
    with pytest.raises(RuntimeError, match="proxy publication failed"):
        with _precontact()._start_slice_b_services(protocol, SimpleNamespace(assigned_file=execution / "assigned"), None):
            pytest.fail("incomplete services reached the lifecycle")
    assert len(threads) == 2 and all(not thread.is_alive() for thread in threads)
    assert b"provider_stopped" in (execution / "provider.jsonl").read_bytes()
    assert b"proxy_stopped" in (execution / "proxy.jsonl").read_bytes()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["admission_write", "seal"])
async def test_correction_finalization_attempted_once_preserves_failure(tmp_path, monkeypatch, capsys, failure):
    protocol_path, source, evidence_root = _make_protocol_file(tmp_path)
    common = _common()
    writes = []
    original = common.EvidenceRoot.write_json

    def write(self, name, value):
        writes.append(name)
        if name == "admission.json" and failure == "admission_write":
            raise OSError("original admission failure")
        return original(self, name, value)

    def fail_seal(self):
        raise OSError("seal failure")

    monkeypatch.setattr(common.EvidenceRoot, "write_json", write)
    monkeypatch.setattr(common.EvidenceRoot, "seal", fail_seal)
    with pytest.raises((OSError, RuntimeError), match="original admission failure|configured Slice A failure"):
        await _precontact().execute_precontact(protocol_path, source,
                    operations=_FakePrecontactOperations(fail_slice="A"), verify_git=False)
    assert writes.count("result.json") == 1
    assert "seal failure" in capsys.readouterr().err
    assert not (evidence_root / "SEALED").exists()


@pytest.mark.asyncio
async def test_correction_full_preparation_precedes_roots_and_slice_a(tmp_path):
    path, source, evidence_root = _make_protocol_file(tmp_path)
    protocol = json.loads(path.read_bytes())
    operations = _FakePrecontactOperations()

    def refuse(*_):
        assert not evidence_root.exists()
        assert not Path(protocol["executionRoot"]).exists()
        raise _common().QualificationRefused("full runtime refusal")

    operations.prepare_admission = refuse
    with pytest.raises(_common().QualificationRefused, match="full runtime refusal"):
        await _precontact().execute_precontact(path, source, operations=operations, verify_git=False)
    assert operations.calls == []
    assert not evidence_root.exists()


@pytest.mark.parametrize("rows", [[], [{"event": "proxy_started"}],
    [{"event": "proxy_admitted", "host": "evil.invalid", "port": 443}],
    [{"event": "proxy_admitted", "host": "pypi.org", "port": 80}],
    [{"event": "proxy_admitted", "host": "pypi.org", "port": 443}, {"event": "proxy_refused"}],
    [{"event": "proxy_admitted", "host": "pypi.org", "port": 443}, {"event": "proxy_connect_failed"}]])
def test_correction_proxy_requires_observed_admission(rows):
    verify = _symbol(_precontact(), "verify_proxy_observations")
    with pytest.raises(_common().QualificationRefused):
        verify(rows, {"pypi.org"})
    verify([{"event": "proxy_admitted", "host": "pypi.org", "port": 443}], {"pypi.org"})


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["common", "runner", "provider", "protocol", "later_commit", "alternate_protocol", "hidden_blob", "module_origin"])
async def test_correction_exact_qualification_identity_rejects_drift(tmp_path, monkeypatch, damage):
    common = _common()
    verify = _symbol(common, "verify_qualification_custody")
    repo = tmp_path / "repo"
    paths = {
        "common": "scripts/qualification/rookchat_prime_acp_common.py",
        "runner": "scripts/qualification/rookchat_prime_acp_precontact.py",
        "provider": "scripts/qualification/fixtures/deterministic_provider.py",
        "protocol": "scripts/qualification/protocols/rookchat-prime-acp-precontact-v1.json",
    }
    for name, relative in paths.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"{}\n" if name == "protocol" else b"# reviewed\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "core.autocrlf", "false"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    commit = ["git", "-C", str(repo), "-c", "user.name=Rook", "-c", "user.email=rook@example.invalid", "commit", "-qm", "reviewed"]
    subprocess.run(commit, check=True)
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    for name, module in (("common", common), ("runner", _precontact()), ("provider", _provider())):
        monkeypatch.setattr(module, "__file__", str(repo / paths[name]))
    protocol_path = repo / paths["protocol"]
    await verify(repo, protocol_path, head)
    if damage in paths:
        (repo / paths[damage]).write_bytes(b"changed\n")
    elif damage == "later_commit":
        (repo / "extra").write_bytes(b"new\n")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(commit, check=True)
    elif damage == "alternate_protocol":
        protocol_path = tmp_path / "alternate.json"
        protocol_path.write_bytes((repo / paths["protocol"]).read_bytes())
    elif damage == "hidden_blob":
        subprocess.run(["git", "-C", str(repo), "update-index", "--assume-unchanged", paths["runner"]], check=True)
        (repo / paths["runner"]).write_bytes(b"# hidden change\n")
        assert not subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True)
    else:
        alternate = tmp_path / "alternate.py"
        alternate.write_bytes((repo / paths["provider"]).read_bytes())
        monkeypatch.setattr(_provider(), "__file__", str(alternate))
    with pytest.raises(common.QualificationRefused):
        await verify(repo, protocol_path, head)
    operations = _FakePrecontactOperations()
    with pytest.raises(common.QualificationRefused, match="qualification"):
        await _precontact().execute_precontact(protocol_path, repo, expected_qualification_commit=head, operations=operations)
    assert operations.calls == []
    assert not (tmp_path / "execution").exists()
    assert not (tmp_path / "evidence").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("uncertain", [False, True])
async def test_correction_git_admission_uses_shared_bounded_process(tmp_path, monkeypatch, uncertain):
    common = _common()
    calls = []
    async def run(spec):
        calls.append(spec)
        return common.ProcessResult(0, b"head\n", b"", False, False, not uncertain)
    def forbidden(*_, **__):
        pytest.fail("Git admission bypassed shared bounded process ownership")
    monkeypatch.setattr(common, "run_bounded_process", run)
    monkeypatch.setattr(subprocess, "run", forbidden)
    if uncertain:
        with pytest.raises(common.QualificationRefused, match="Git custody"):
            await common._git(tmp_path, "rev-parse", "HEAD")
    else:
        result = await common._git(tmp_path, "rev-parse", "HEAD")
        assert result.stdout == "head\n"
    assert len(calls) == 1
    spec = calls[0]
    assert Path(spec.argv[0]).is_absolute()
    assert spec.argv[1:] == ("-C", str(tmp_path), "rev-parse", "HEAD")
    assert spec.timeout_seconds == 10 and spec.close_seconds == 30
    assert spec.max_output_bytes == 1_048_576


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


@pytest.mark.asyncio
async def test_protocol_admission_binds_runtime_source_and_fresh_evidence(tmp_path: Path) -> None:
    common = _common()
    admit = _symbol(common, "admit_precontact_protocol")
    protocol, source, evidence_root = _valid_protocol(tmp_path)
    path = tmp_path / "protocol.json"
    path.write_bytes(_canonical(protocol))

    admitted = await admit(path, source, verify_git=False)
    assert admitted["runtime"]["runtimeId"] == protocol["runtime"]["runtimeId"]

    (source / "authority.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(_symbol(common, "QualificationRefused"), match="source input"):
        await admit(path, source, verify_git=False)
    (source / "authority.txt").write_text("reviewed\n", encoding="utf-8", newline="\n")
    evidence_root.mkdir()
    with pytest.raises(_symbol(common, "QualificationRefused"), match="evidence root"):
        await admit(path, source, verify_git=False)


@pytest.mark.asyncio
async def test_source_custody_requires_clean_descendant_and_unchanged_product(tmp_path: Path) -> None:
    common = _common()
    verify = _symbol(common, "verify_source_custody")
    repo = tmp_path / "repo"
    (repo / "mcp_server/src/rook").mkdir(parents=True)
    (repo / "mcp_server/src/rook/product.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "core.autocrlf", "false"], check=True)
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
    await verify(repo, base)

    (repo / "mcp_server/src/rook/product.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(_symbol(common, "QualificationRefused"), match="clean"):
        await verify(repo, base)


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
    assert request["lastUserSha256"] == _sha(b"CREATE_AND_CALL_ROOK")
    assert request["messageRoles"] == ["system", "user"]
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

    def prepare_admission(self, protocol, repo_root):
        assert not Path(protocol["evidenceRoot"]).exists()
        assert not Path(protocol["executionRoot"]).exists()

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
    assert all(spec.environment != dict(os.environ) for spec in captured)


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
            Path(protocol["environment"]["roots"]["sessions"]) / (protocol["qualificationConversationId"] + ".jsonl"),
            "qualification/test-model",
            "off",
            False,
        ),
        (
            Path(protocol["environment"]["roots"]["sessions"]) / (protocol["qualificationConversationId"] + ".jsonl"),
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


@pytest.mark.asyncio
async def test_frozen_precontact_protocol_prepares_staged_runtime_without_creating_roots() -> None:
    common = _common()
    path = REPO / "scripts/qualification/protocols/rookchat-prime-acp-precontact-v1.json"
    protocol = common.load_precontact_protocol(path)
    roots = [Path(protocol[key]) for key in ("executionRoot", "evidenceRoot")]

    def root_state():
        return {str(path): (path.lstat().st_mode, path.stat().st_size, path.stat().st_mtime_ns,
                           _sha(path.read_bytes()) if path.is_file() else None)
                for root in roots if root.exists() for path in [root, *root.rglob("*")]}

    before = root_state()
    assert protocol["implementationCommit"] == "0900d913c1cc0e4bd76c2df018fbe0ac4fccac2e"
    assert protocol["runtime"]["runtimeId"] == "4BFA4A0500FECEAAEC737563623521562C5F4FDF2592EA443C956E0063A12579"
    assert protocol["environment"]["expectedFinalSha256"] == "52C5F7829ECA0BCFA32733AA8D680E66E29BA0346F795B7F01CD7B747DAA0BA6"
    prepared = _precontact().prepare_slice_b(protocol, REPO)
    assert str(prepared.session_path) in prepared.initial_argv
    assert str(prepared.session_path) in prepared.reopen_argv
    assert root_state() == before


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
    assert workspace.assigned_file == Path(protocol["executionRoot"]) / "assigned.txt"
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
        path = Path(protocol["executionRoot"]) / relative
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
    prepared = SimpleNamespace(session_path=Path(protocol["environment"]["roots"]["sessions"]) /
                               (protocol["qualificationConversationId"] + ".jsonl"))
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
    operations.prepare_admission(protocol, source)
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
                        "id": "durable-prime-header-identity",
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
                stream.write(_canonical({"event": "mcp_call_started", "name": "qualification_wait", "arguments": {"value": "cancel"}}))
            await self._cancelled.wait()
            return SimpleNamespace(stop_reason="cancelled")
        if text == "CREATE_AND_CALL_ROOK":
            self.assigned_file.write_bytes(b"qualified\n")
            projection.accumulate_assistant_text("FIRST_OK:alpha")
            with self._mcp_journal.open("ab") as stream:
                stream.write(_canonical({"event": "mcp_call_started", "name": "qualification_echo", "arguments": {"value": "alpha"}}))
                stream.write(_canonical({"event": "mcp_call_finished", "name": "qualification_echo"}))
            return SimpleNamespace(stop_reason="end_turn")
        projection.accumulate_assistant_text("REOPEN_OK:FIRST_OK:alpha")
        with self._mcp_journal.open("ab") as stream:
            stream.write(_canonical({"event": "mcp_call_started", "name": "qualification_echo", "arguments": {"value": "reopen"}}))
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
@pytest.mark.parametrize("damage", [None, "provider-duplicate", "provider-missing", "provider-order", "provider-unexpected",
    *[f"mcp-{launch}-{change}" for launch in (0, 1) for change in ("start", "list", "extra", "order", "missing")]])
async def test_installed_slice_b_lifecycle_uses_exact_handles_and_reopens_with_fresh_mcp(tmp_path: Path, damage) -> None:
    precontact = _precontact()
    common = _common()
    protocol, source, evidence_root = _valid_protocol(tmp_path)
    admitted_path = precontact.qualification_data_paths(protocol).session_path(protocol["qualificationConversationId"])
    assert not Path(protocol["executionRoot"]).exists()
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
        initial_argv=("pi.exe", "--resume", str(admitted_path), "initial"),
        reopen_argv=("pi.exe", "--resume", str(admitted_path), "reopen"),
        session_path=Path(workspace.provisional_association.session_path),
    )
    prepared.contract.uv_executable_path.parent.mkdir(parents=True)
    prepared.contract.uv_executable_path.write_bytes(b"uv")
    calls: list[tuple] = []

    async def start(argv, environment, claim, generation, cwd):
        assert environment == prepared.environment
        assert Path(argv[2]) == admitted_path == prepared.session_path
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

    from urllib.parse import urlparse
    provider_url = urlparse(protocol["network"]["providerUrl"])
    provider_rows = [{"event": "provider_started", "host": provider_url.hostname, "port": provider_url.port}]
    for text, after_user in (("CREATE_AND_CALL_ROOK", []), ("CREATE_AND_CALL_ROOK", ["assistant", "tool"]),
                             ("CANCEL_ME", []), ("PROVE_CONTEXT", []), ("PROVE_CONTEXT", ["assistant", "tool"])):
        provider_rows.append({
            "event": "provider_request",
            "path": "/v1/chat/completions",
            "lastUserSha256": _sha(text.encode()),
            "messageRoles": ["system", "user", *after_user],
            "bodyBytes": 100,
            "bodySha256": "A" * 64,
            "globalSystemPresent": True,
            "goalSkillPresent": True,
            "hostileMarkerPresent": False,
            "rookContractPresent": True,
        })
    provider_rows.append({"event": "provider_stopped"})
    if damage == "provider-duplicate":
        provider_rows.insert(2, dict(provider_rows[1]))
    elif damage == "provider-missing":
        del provider_rows[2]
    elif damage == "provider-order":
        provider_rows[1], provider_rows[2] = provider_rows[2], provider_rows[1]
    elif damage == "provider-unexpected":
        provider_rows.insert(2, {"event": "unadmitted"})
    services = SimpleNamespace(
        daemon_tripwire=_FakeTripwire(),
        provider_journal=_FakeJournal(Path(protocol["executionRoot"]) / "provider.jsonl", provider_rows),
        proxy_journal=_FakeJournal(Path(protocol["executionRoot"]) / "proxy.jsonl", [{"event": "proxy_admitted", "host": "pypi.org", "port": 443}]),
    )

    @contextlib.contextmanager
    def service_factory(*_args):
        yield services
        if damage and damage.startswith("mcp-"):
            _, launch, change = damage.split("-")
            path = workspace.mcp_journal_paths[int(launch)]
            rows = [json.loads(line) for line in path.read_bytes().splitlines()]
            if change == "start":
                rows.insert(1, dict(rows[0]))
            elif change == "list":
                rows.insert(2, dict(rows[1]))
            elif change == "extra":
                rows.append({"event": "mcp_call_started", "name": "qualification_echo", "arguments": {"value": "extra"}})
            elif change == "order":
                rows[2], rows[3] = rows[3], rows[2]
            elif change == "missing":
                del rows[2]
            path.write_bytes(b"".join(_canonical(row) for row in rows))

    operation = _symbol(precontact, "run_installed_slice_b")(
        protocol,
        source,
        evidence,
        prepared,
        workspace,
        process_starter=start,
        services_factory=service_factory,
    )
    if damage:
        with pytest.raises(common.QualificationRefused, match="journal"):
            await operation
        assert not (evidence_root / "slice-b/session-header.json").exists()
        return
    result = await operation
    assert result["outcome"] == "passed"
    assert result["firstAssistantText"] == "FIRST_OK:alpha"
    assert result["reopenAssistantText"] == "REOPEN_OK:FIRST_OK:alpha"
    assert result["cancelStopReason"] == "cancelled"
    association = workspace.association_store.get(protocol["qualificationConversationId"])
    assert association.prime_session_id == "durable-prime-header-identity"
    assert result["sessionIds"] == ["acp-1", "acp-2"]
    assert Path(association.session_path) == admitted_path
    assert admitted_path.is_file()
    assert (evidence_root / "slice-b/session-header.json").read_bytes() == admitted_path.read_bytes().splitlines(keepends=True)[0]
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
        assert _sha((Path(protocol["executionRoot"]) / relative).read_bytes()) == digest


@pytest.mark.asyncio
async def test_correction_cancellation_during_cleanup_is_not_swallowed(tmp_path, monkeypatch):
    common = _common()
    entered = asyncio.Event()
    release = asyncio.Event()
    stop = common._stop_direct_process

    async def paused(process, seconds):
        entered.set()
        await release.wait()
        return await stop(process, seconds)

    monkeypatch.setattr(common, "_stop_direct_process", paused)
    spec = common.ProcessSpec((sys.executable, "-I", "-c", "pass"), tmp_path,
                              {"SYSTEMROOT": os.environ["SYSTEMROOT"]}, 3, .5, 1024)
    task = asyncio.create_task(common.run_bounded_process(spec))
    await asyncio.wait_for(entered.wait(), 3)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
async def test_correction_unexitable_child_does_not_wait_for_pipe_eof(tmp_path, monkeypatch):
    common = _common()
    calls = []
    class Stream:
        async def read(self, _):
            await asyncio.Event().wait()
    class Child:
        returncode = None
        stdout = Stream()
        stderr = Stream()
        async def wait(self):
            await asyncio.Event().wait()
        def terminate(self):
            calls.append("terminate")
        def kill(self):
            calls.append("kill")
    async def spawn(*_, **__):
        return Child()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    spec = common.ProcessSpec((sys.executable,), tmp_path, {}, .01, .1, 1024)
    result = await asyncio.wait_for(common.run_bounded_process(spec), .5)
    assert result.timed_out and not result.direct_child_exit_observed
    assert calls == ["terminate", "kill"]


@pytest.mark.parametrize("name", ["bin", "fd", "fd.exe", "rg", "rg.exe"])
def test_correction_managed_helper_artifact_is_refused(tmp_path, name):
    protocol, _, _ = _valid_protocol(tmp_path)
    environment = protocol["environment"]["expectedFinal"]
    _precontact().verify_no_managed_helpers(protocol, environment)
    path = (Path(protocol["environment"]["roots"]["primeAgentDir"]) / "bin" if name == "bin"
            else Path(environment["PATH"]) / name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if name == "bin":
        path.mkdir()
    else:
        path.write_bytes(b"unadmitted helper")
    with pytest.raises(_common().QualificationRefused, match="helper"):
        _precontact().verify_no_managed_helpers(protocol, environment)


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["extra", "missing", "altered"])
async def test_correction_real_runtime_loader_refuses_before_any_slice(tmp_path, damage):
    from rook.agent.chat.prime_runtime import load_and_verify_runtime, build_prime_argv, build_prime_child_env
    from rook.agent.chat.prime_runtime_artifact import RuntimeUnavailable
    spec = importlib.util.spec_from_file_location("runtime_payload_fixture", REPO / "mcp_server/tests/test_prime_runtime_artifact.py")
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    protocol, source, evidence = _valid_protocol(tmp_path)
    payload, runtime_id = fixture.materialize(tmp_path / "complete-payload")
    destination = Path(protocol["runtime"]["installRoot"]) / "runtimes" / runtime_id
    payload.rename(destination)
    manifest = json.loads((destination / "runtime-manifest.json").read_bytes())
    assert load_and_verify_runtime(destination.parent.parent, runtime_id).runtime_id == runtime_id
    protocol["runtime"].update(runtimeId=runtime_id, manifestSha256=runtime_id,
        manifestPath=str(destination / "runtime-manifest.json"), primeExecutableSha256=_sha((destination / "pi.exe").read_bytes()),
        rookSkillManifestSha256=manifest["rookSkillManifestSha256"])
    protocol["kernel"].update(runtimeSourcePath=str(destination / "dist/prime-agent-runtime"),
                            runtimeSourceManifestSha256=manifest["pythonRuntime"]["manifestSha256"])
    path = tmp_path / "protocol.json"
    path.write_bytes(_canonical(protocol))
    if damage == "extra":
        (destination / "extra.bin").write_bytes(b"extra")
    elif damage == "missing":
        (destination / "README.md").unlink()
    else:
        (destination / "README.md").write_bytes(b"changed")
    calls = []
    async def forbidden(*_):
        calls.append("contact")
        pytest.fail("runtime refusal came too late")
    def prepare(protocol, repo, **kwargs):
        return _precontact().prepare_slice_b(protocol, repo, runtime_loader=load_and_verify_runtime,
                                            argv_builder=build_prime_argv, environment_builder=build_prime_child_env, **kwargs)
    operations = _precontact().ProductPrecontactOperations(process_runner=forbidden, slice_b_runner=forbidden,
                                                          slice_b_preparer=prepare)
    with pytest.raises(RuntimeUnavailable, match="manifest file set or bytes differ"):
        await _precontact().execute_precontact(path, source, operations=operations, verify_git=False)
    assert calls == []
    assert not evidence.exists()
    assert not Path(protocol["executionRoot"]).exists()


@pytest.mark.parametrize("kind", ["provider", "proxy"])
def test_correction_request_thread_is_owned_through_service_close(tmp_path, monkeypatch, kind):
    provider = _provider()
    import threading
    entered = threading.Event()
    release = threading.Event()
    handler = provider._ProviderHandler if kind == "provider" else provider._ProxyHandler
    def wait_only(_self):
        entered.set()
        release.wait(timeout=3)
    monkeypatch.setattr(handler, "handle", wait_only)
    journal = provider.BoundedJsonlJournal(tmp_path / "journal", max_records=20, max_bytes=4096)
    service = (provider.DeterministicProviderServer("http://127.0.0.1:0/v1", tmp_path / "assigned", journal)
               if kind == "provider" else provider.ConnectProxyServer("http://127.0.0.1:0", {"pypi.org"}, journal))
    service.start()
    peer = socket.create_connection(service._server.server_address)
    try:
        assert entered.wait(timeout=2)
        threads = list(getattr(service._server, "request_threads", []))
        assert threads, "request thread was not retained by its server"
    finally:
        release.set()
        peer.close()
        service.close()
    assert all(not thread.is_alive() for thread, _ in threads)


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ["child", "provider-thread", "proxy-thread"])
async def test_correction_uncertain_owner_retains_complete_workspace(tmp_path, owner):
    path, source, evidence = _make_protocol_file(tmp_path)
    protocol = json.loads(path.read_bytes())
    execution = Path(protocol["executionRoot"])
    contents = {"session.jsonl": b"session", "open.claim": b"", "log": b"diagnostic"}
    operations = _FakePrecontactOperations()
    async def uncertain(*_):
        for name, data in contents.items():
            (execution / name).write_bytes(data)
        raise RuntimeError(f"{owner} exit unobserved")
    operations.run_slice_a = uncertain
    try:
        with pytest.raises(RuntimeError, match="exit unobserved"):
            await _precontact().execute_precontact(path, source, operations=operations, verify_git=False)
        assert {p.name: p.read_bytes() for p in execution.iterdir()} == contents
        with pytest.raises(_common().QualificationRefused, match="root already exists"):
            await _precontact().execute_precontact(path, source, operations=operations, verify_git=False)
    finally:
        _make_writable(evidence)


def test_correction_evidence_total_limit_and_bounded_copy(tmp_path):
    common = _common()
    evidence = common.EvidenceRoot.create(tmp_path / "evidence", max_file_bytes=2048,
                                         max_total_bytes=5127, max_files=64)
    evidence.write_bytes("exact", b"x" * 1024)
    with pytest.raises(common.QualificationRefused, match="total byte limit"):
        evidence.write_bytes("one-more", b"x")
    source = tmp_path / "oversized"
    source.write_bytes(b"x" * 2049)
    with pytest.raises(common.QualificationRefused, match="byte limit"):
        evidence.copy_file("copy", source)
    assert not (evidence.root / "copy").exists()


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
        provider_journal=_FakeJournal(Path(protocol["executionRoot"]) / "provider.jsonl", provider_rows),
        proxy_journal=_FakeJournal(Path(protocol["executionRoot"]) / "proxy.jsonl", [{"event": "proxy_admitted", "host": "pypi.org", "port": 443}]),
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
        provider_journal=_FakeJournal(Path(protocol["executionRoot"]) / "provider.jsonl", []),
        proxy_journal=_FakeJournal(Path(protocol["executionRoot"]) / "proxy.jsonl", []),
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
