"""Execute one frozen, external RookChat Prime ACP pre-contact qualification."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence
from urllib.parse import urlparse
from uuid import uuid4

# Direct script execution must resolve the reviewed worktree, not an ambient scripts package.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.qualification.rookchat_prime_acp_common import (
    EvidenceRoot,
    ProcessResult,
    ProcessSpec,
    QualificationRefused,
    admit_precontact_protocol,
    run_bounded_process,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)


DEFAULT_RLM_EXTRA_UV_ARGS = (
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
)
MAX_BOOTSTRAP_VERSION_BYTES = 64 * 1024


class PrecontactOperations(Protocol):
    def prepare_admission(self, protocol: dict[str, Any], repo_root: Path) -> None: ...
    async def run_slice_a(self, protocol: dict[str, Any], repo_root: Path, evidence: EvidenceRoot) -> dict[str, Any]: ...

    async def run_slice_b(self, protocol: dict[str, Any], repo_root: Path, evidence: EvidenceRoot) -> dict[str, Any]: ...


async def execute_precontact(
    protocol_path: Path,
    repo_root: Path,
    *,
    operations: PrecontactOperations | None = None,
    verify_git: bool = True,
    expected_qualification_commit: str | None = None,
) -> dict[str, str]:
    protocol = await admit_precontact_protocol(protocol_path, repo_root, verify_git=verify_git,
                                        expected_qualification_commit=expected_qualification_commit)
    runner = operations or ProductPrecontactOperations()
    runner.prepare_admission(protocol, repo_root)
    root = EvidenceRoot.create(
        Path(protocol["evidenceRoot"]),
        max_file_bytes=protocol["limits"]["maxEvidenceFileBytes"],
        max_total_bytes=protocol["limits"]["maxEvidenceTotalBytes"],
        max_files=protocol["limits"]["maxEvidenceFiles"],
    )
    active_slice = "A"
    failure: BaseException | None = None
    try:
        root.write_json("admission.json", {
            "qualificationCommit": expected_qualification_commit,
            "implementationCommit": protocol["implementationCommit"],
            "protocolSha256": sha256_file(protocol_path),
            "runtimeId": protocol["runtime"]["runtimeId"],
        })
        Path(protocol["executionRoot"]).mkdir(parents=True, exist_ok=False)
        async with asyncio.timeout(protocol["limits"]["wallClockSeconds"]):
            slice_a = await runner.run_slice_a(protocol, repo_root, root)
            root.write_json("slice-a.json", slice_a)
            if slice_a.get("outcome") != "passed":
                raise QualificationRefused("Slice A did not pass")
            active_slice = "B"
            slice_b = await runner.run_slice_b(protocol, repo_root, root)
            root.write_json("slice-b.json", slice_b)
            if slice_b.get("outcome") != "passed":
                raise QualificationRefused("Slice B did not pass")
        result = {"outcome": "passed", "sliceA": "passed", "sliceB": "passed"}
    except BaseException as exc:
        failure = exc
        result = {"error": str(exc)[:4096], "errorType": type(exc).__name__,
                  "failedSlice": active_slice, "outcome": "failed"}
    # Retain the workspace on every outcome; uncertain owners must never lose it.
    for label, finalize in (("result", lambda: root.write_json("result.json", result)), ("seal", root.seal)):
        try:
            finalize()
        except BaseException as exc:
            print(f"qualification_{label}_failed: {str(exc)[:2048]}", file=sys.stderr)
            if failure is None:
                failure = exc
            else:
                failure.add_note(f"{label} finalization failed: {type(exc).__name__}")
    if failure is not None:
        raise failure
    return result


ProcessRunner = Callable[[ProcessSpec], Awaitable[ProcessResult]]
RuntimeLoader = Callable[[Path, str], Any]
ArgvBuilder = Callable[[Any, Path, str | None, str | None, bool], tuple[str, ...]]
EnvironmentBuilder = Callable[[dict[str, str], Any], dict[str, str]]


@dataclass(frozen=True)
class PreparedSliceB:
    contract: Any
    environment: dict[str, str]
    initial_argv: tuple[str, ...]
    product_initial_argv: tuple[str, ...]
    product_reopen_argv: tuple[str, ...]
    reopen_argv: tuple[str, ...]
    session_path: Path


@dataclass(frozen=True)
class SliceBWorkspace:
    association_store: Any
    assigned_file: Path
    claims_root: Path
    global_system_path: Path
    hostile_hashes: dict[str, str]
    mcp_journal_paths: tuple[Path, Path]
    models_path: Path
    provisional_association: Any


@dataclass(frozen=True)
class SliceBServices:
    daemon_tripwire: Any
    provider_journal: Any
    proxy_journal: Any


SliceBPreparer = Callable[..., PreparedSliceB]
SliceBRunner = Callable[
    [dict[str, Any], Path, EvidenceRoot, PreparedSliceB, SliceBWorkspace],
    Awaitable[dict[str, Any]],
]
ProcessStarter = Callable[[tuple[str, ...], dict[str, str], Any, int, Path], Awaitable[Any]]
ServicesFactory = Callable[[dict[str, Any], SliceBWorkspace, EvidenceRoot], Any]


def _load_product_runtime_functions(repo_root: Path) -> tuple[RuntimeLoader, ArgvBuilder, EnvironmentBuilder]:
    source = str((repo_root / "mcp_server/src").resolve(strict=True))
    if source not in sys.path:
        sys.path.insert(0, source)
    from rook.agent.chat.prime_runtime import build_prime_argv, build_prime_child_env, load_and_verify_runtime

    return load_and_verify_runtime, build_prime_argv, build_prime_child_env


def _slice_b_base_environment(protocol: dict[str, Any]) -> dict[str, str]:
    environment = {key: "ambient-must-be-removed" for key in protocol["environment"]["seededAmbientKeys"]}
    proxy_names = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}
    environment = {key: value for key, value in environment.items() if key.upper() not in proxy_names}
    roots = protocol["environment"]["roots"]
    system_root = Path(os.environ.get("SystemRoot", "C:/Windows")).resolve(strict=True)
    environment.update(
        {
            "APPDATA": roots["appData"],
            "CI": "1",
            "COMSPEC": str(system_root / "System32/cmd.exe"),
            "HOME": roots["home"],
            "LOCALAPPDATA": roots["localAppData"],
            "PATH": str(system_root / "System32"),
            "PATHEXT": ".COM;.EXE;.BAT;.CMD",
            "PRIME_AGENT_CODING_AGENT_DIR": roots["primeAgentDir"],
            "ROOK_DATA_DIR": roots["rookDataDir"],
            "SYSTEMROOT": str(system_root),
            "TEMP": roots["temp"],
            "TMP": roots["temp"],
            "USERPROFILE": roots["userProfile"],
            "WINDIR": str(system_root),
        }
    )
    environment.update(protocol["environment"]["proxy"]["values"])
    return environment


def _contains_subsequence(values: tuple[str, ...], expected: list[str]) -> bool:
    cursor = 0
    for value in values:
        if cursor < len(expected) and value == expected[cursor]:
            cursor += 1
    return cursor == len(expected)


def qualification_data_paths(protocol: dict[str, Any]):
    from rook.runtime_paths import AcpDataPaths, RuntimePaths

    roots = protocol["environment"]["roots"]
    execution = Path(protocol["executionRoot"])
    repo = Path(__file__).resolve().parents[2]
    paths = AcpDataPaths.from_runtime_paths(RuntimePaths(
        mode="dev", install_root=repo, data_root=Path(roots["rookDataDir"]),
        logs_root=execution / "logs", runtime_root=execution,
        mcp_server_dir=repo / "mcp_server", repo_root=repo))
    if Path(roots["sessions"]).resolve(strict=False) != paths.sessions_root:
        raise QualificationRefused("qualification session topology differs from the product")
    return paths


def prepare_slice_b(
    protocol: dict[str, Any],
    repo_root: Path,
    *,
    runtime_loader: RuntimeLoader | None = None,
    argv_builder: ArgvBuilder | None = None,
    environment_builder: EnvironmentBuilder | None = None,
    session_path: Path | None = None,
) -> PreparedSliceB:
    if runtime_loader is None or argv_builder is None or environment_builder is None:
        default_loader, default_argv, default_environment = _load_product_runtime_functions(repo_root)
        runtime_loader = runtime_loader or default_loader
        argv_builder = argv_builder or default_argv
        environment_builder = environment_builder or default_environment

    runtime = protocol["runtime"]
    contract = runtime_loader(Path(runtime["installRoot"]), runtime["runtimeId"])
    runtime_root = Path(runtime["manifestPath"]).parent
    if (
        contract.runtime_id != runtime["runtimeId"]
        or contract.manifest_sha256 != runtime["manifestSha256"]
        or Path(contract.executable_path) != runtime_root / "pi.exe"
        or contract.rook_skill_manifest_sha256 != runtime["rookSkillManifestSha256"]
        or Path(contract.prime_agent_runtime_path) != Path(protocol["kernel"]["runtimeSourcePath"])
        or contract.prime_agent_runtime_manifest_sha256 != protocol["kernel"]["runtimeSourceManifestSha256"]
    ):
        raise QualificationRefused("verified runtime contract differs from the frozen protocol")

    admitted_path = qualification_data_paths(protocol).session_path(protocol["qualificationConversationId"]).resolve(strict=False)
    if session_path is not None and session_path != admitted_path:
        raise QualificationRefused("qualification session path differs")
    session_path = admitted_path
    launch = protocol["launch"]
    product_initial = argv_builder(contract, session_path, launch["model"], launch["reasoning"], False)
    product_reopen = argv_builder(contract, session_path, None, None, True)
    forbidden = set(launch["productionForbiddenArguments"])
    for product_argv in (product_initial, product_reopen):
        if product_argv[0] != str(contract.executable_path):
            raise QualificationRefused("product argv selects a different executable")
        if not _contains_subsequence(product_argv, launch["productionRequiredArguments"]):
            raise QualificationRefused("product argv omits required selectors")
        if forbidden.intersection(product_argv):
            raise QualificationRefused("product argv contains a qualification-only selector")
    if any(token in product_reopen for token in ("--model", "--thinking", "--provider", "--api-key")):
        raise QualificationRefused("reopen argv contains a model or credential override")

    qualification = tuple(launch["qualificationOnlyArguments"])
    environment = environment_builder(_slice_b_base_environment(protocol), contract)
    if environment != protocol["environment"]["expectedFinal"]:
        raise QualificationRefused("Prime child environment differs from the frozen protocol")
    expected_hash = protocol["environment"]["expectedFinalSha256"]
    if sha256_bytes(canonical_json_bytes(environment)) != expected_hash:
        raise QualificationRefused("Prime child environment hash differs from the frozen protocol")
    return PreparedSliceB(
        contract=contract,
        environment=environment,
        initial_argv=product_initial + qualification,
        product_initial_argv=product_initial,
        product_reopen_argv=product_reopen,
        reopen_argv=product_reopen + qualification,
        session_path=session_path,
    )


def _write_create_only(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(data)
    except FileExistsError as exc:
        raise QualificationRefused(f"Slice B fixture already exists: {path}") from exc


def prepare_slice_b_workspace(
    protocol: dict[str, Any],
    repo_root: Path,
    evidence: EvidenceRoot,
) -> SliceBWorkspace:
    del repo_root
    roots = {name: Path(value) for name, value in protocol["environment"]["roots"].items()}
    execution_root = Path(protocol["executionRoot"]).resolve(strict=False)
    for name, path in roots.items():
        if path.exists() or path.is_symlink():
            raise QualificationRefused(f"Slice B isolated root is not fresh: {name}")
        parent = path.parent.resolve(strict=False)
        if execution_root not in (parent, *parent.parents):
            raise QualificationRefused(f"Slice B isolated root escapes workspace: {name}")

    cold_paths = (
        Path(protocol["kernel"]["venvPath"]),
        Path(protocol["kernel"]["pythonPath"]),
        Path(protocol["kernel"]["uvCachePath"]),
        Path(protocol["kernel"]["uvPythonInstallPath"]),
    )
    if any(path.exists() or path.is_symlink() for path in cold_paths):
        raise QualificationRefused("Slice B cold-kernel path is not fresh")

    for path in roots.values():
        path.mkdir(parents=True, exist_ok=False)

    from rook.agent.chat.acp_storage import AssociationStore, ProvisionalAssociation, RookBinding

    data_paths = qualification_data_paths(protocol)
    association_store = AssociationStore(data_paths)
    target = protocol["target"]
    provisional = ProvisionalAssociation(
        conversation_id=protocol["qualificationConversationId"],
        session_path=str(data_paths.session_path(protocol["qualificationConversationId"]).resolve(strict=False)),
        binding=RookBinding(
            profile=target["profile"],
            host_generation_id=target["hostGenerationId"],
            rhino_document_serial=target["rhinoDocumentSerial"],
            route_process_id=target["routeProcessId"],
        ),
        runtime_id=protocol["runtime"]["runtimeId"],
        working_directory=str(roots["projectResume"].resolve(strict=True)),
        requested_initial_model=protocol["launch"]["model"],
        requested_initial_reasoning=protocol["launch"]["reasoning"],
    )

    models_path = roots["primeAgentDir"] / "models.json"
    models = {
        "providers": {
            "qualification": {
                "api": "openai-completions",
                "apiKey": "qualification-local-nonsecret",
                "baseUrl": protocol["network"]["providerUrl"],
                "models": [
                    {
                        "id": protocol["launch"]["model"],
                        "input": ["text"],
                        "maxTokens": protocol["limits"]["tokenLimit"],
                        "reasoning": False,
                    }
                ],
            }
        }
    }
    _write_create_only(models_path, canonical_json_bytes(models))
    global_system_path = roots["primeAgentDir"] / "SYSTEM.md"
    _write_create_only(global_system_path, b"ROOK_QUALIFICATION_GLOBAL_SYSTEM\n")

    hostile_marker = "ROOK_QUALIFICATION_HOSTILE_PROJECT_RESOURCE"
    hostile_files = {
        ".agents/skills/hostile-agent/SKILL.md": hostile_marker + "\n",
        ".claude/commands/hostile.md": hostile_marker + "\n",
        ".prime/agent/APPEND_SYSTEM.md": hostile_marker + "\n",
        ".prime/agent/SYSTEM.md": hostile_marker + "\n",
        ".prime/agent/commands/hostile.md": hostile_marker + "\n",
        ".prime/agent/extensions/hostile.ts": f"export default '{hostile_marker}';\n",
        ".prime/agent/prompts/hostile.md": hostile_marker + "\n",
        ".prime/agent/settings.json": json.dumps(
            {"defaultModel": "hostile/model", "marker": hostile_marker},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        ".prime/agent/skills/hostile/SKILL.md": hostile_marker + "\n",
        ".prime/agent/themes/hostile.json": json.dumps(
            {"marker": hostile_marker, "name": "hostile"},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        "AGENTS.md": hostile_marker + "\n",
        "CLAUDE.md": hostile_marker + "\n",
    }
    hostile_hashes: dict[str, str] = {}
    live_root = execution_root
    for project_name in ("projectLaunch", "projectResume"):
        project = roots[project_name]
        for relative, text in hostile_files.items():
            path = project / Path(relative)
            data = text.encode("utf-8", "strict")
            _write_create_only(path, data)
            hostile_hashes[path.relative_to(live_root).as_posix()] = sha256_bytes(data)

    return SliceBWorkspace(
        association_store=association_store,
        assigned_file=live_root / "assigned.txt",
        claims_root=data_paths.claims_root,
        global_system_path=global_system_path,
        hostile_hashes=hostile_hashes,
        mcp_journal_paths=(live_root / "mcp-first.jsonl", live_root / "mcp-reopen.jsonl"),
        models_path=models_path,
        provisional_association=provisional,
    )


def _read_bounded_jsonl(path: Path, *, max_records: int, max_bytes: int) -> list[dict[str, Any]]:
    if not path.is_file() or path.is_symlink():
        raise QualificationRefused(f"qualification journal is unavailable: {path}")
    with path.open("rb") as stream:
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise QualificationRefused(f"qualification journal exceeds byte limit: {path}")
    rows: list[dict[str, Any]] = []
    try:
        for raw in data.splitlines():
            if not raw:
                continue
            value = json.loads(raw.decode("utf-8", "strict"))
            if type(value) is not dict:
                raise ValueError("journal row is not an object")
            rows.append(value)
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise QualificationRefused(f"qualification journal is invalid: {path}") from exc
    if len(rows) > max_records:
        raise QualificationRefused(f"qualification journal exceeds record limit: {path}")
    return rows


async def _wait_for_journal_event(
    path: Path,
    *,
    event: str,
    name: str | None,
    timeout_seconds: float,
    max_records: int,
    max_bytes: int,
) -> None:
    async with asyncio.timeout(timeout_seconds):
        while True:
            if path.is_file():
                rows = _read_bounded_jsonl(path, max_records=max_records, max_bytes=max_bytes)
                if any(row.get("event") == event and (name is None or row.get("name") == name) for row in rows):
                    return
            await asyncio.sleep(0.05)


def _build_qualification_mcp_server(protocol: dict[str, Any], repo_root: Path, journal_path: Path) -> Any:
    from acp.schema import EnvVariable, McpServerStdio

    fixture = (repo_root / "scripts/qualification/fixtures/deterministic_provider.py").resolve(strict=True)
    limits = protocol["limits"]
    environment = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    return McpServerStdio(
        name=protocol["launch"]["mcpServerName"],
        command=str(Path(sys.executable).resolve(strict=True)),
        args=[
            str(fixture),
            "--rook-mcp",
            "--journal",
            str(journal_path),
            "--max-records",
            str(limits["maxProxyLedgerRecords"]),
            "--max-bytes",
            str(limits["maxProxyLedgerBytes"]),
        ],
        env=[EnvVariable(name=key, value=value) for key, value in sorted(environment.items())],
    )


async def _start_owned_process(
    argv: tuple[str, ...],
    environment: dict[str, str],
    claim: Any,
    generation: int,
    cwd: Path,
) -> Any:
    from rook.agent.chat.acp_conversation import PreparedDirectAcpLaunch
    from rook.agent.chat.acp_process import PrimeLaunch

    return await PreparedDirectAcpLaunch(
        PrimeLaunch(argv=argv, environment=environment, cwd=cwd),
    ).start(claim, launch_generation=generation)


@contextmanager
def _start_slice_b_services(
    protocol: dict[str, Any],
    workspace: SliceBWorkspace,
    evidence: EvidenceRoot,
):
    from scripts.qualification.fixtures.deterministic_provider import (
        BoundedJsonlJournal,
        ConnectProxyServer,
        DeterministicProviderServer,
        NamedPipeTripwire,
    )

    limits = protocol["limits"]
    provider_journal = BoundedJsonlJournal(
        Path(protocol["executionRoot"]) / "provider.jsonl",
        max_records=limits["maxProxyLedgerRecords"],
        max_bytes=limits["maxProxyLedgerBytes"],
    )
    proxy_journal = BoundedJsonlJournal(
        Path(protocol["executionRoot"]) / "proxy.jsonl",
        max_records=limits["maxProxyLedgerRecords"],
        max_bytes=limits["maxProxyLedgerBytes"],
    )
    services = SliceBServices(
        daemon_tripwire=NamedPipeTripwire(protocol["network"]["daemonSocket"]),
        provider_journal=provider_journal,
        proxy_journal=proxy_journal,
    )
    with contextlib.ExitStack() as stack:
        stack.enter_context(
            DeterministicProviderServer(
                protocol["network"]["providerUrl"],
                workspace.assigned_file,
                provider_journal,
                goal_skill_path=Path(protocol["runtime"]["manifestPath"]).parent / "skills/goal/SKILL.md",
            )
        )
        stack.enter_context(
            ConnectProxyServer(
                protocol["network"]["proxyUrl"],
                set(protocol["environment"]["proxy"]["admittedHosts"]),
                proxy_journal,
            )
        )
        stack.enter_context(services.daemon_tripwire)
        yield services


async def _prompt_once(process: Any, text: str, *, launch_generation: int, prompt_id: str) -> tuple[str, str]:
    from acp.schema import TextContentBlock
    from rook.agent.chat.acp_presentation import BoundedPromptProjection, PresentationQueue, PromptGeneration

    if process.session_id is None:
        raise QualificationRefused("ACP session was not established")
    generation = PromptGeneration(launch_generation, process.session_id, prompt_id)
    projection = BoundedPromptProjection(
        generation=generation,
        queue=PresentationQueue(),
        user_text=text,
    )
    try:
        response = await process.prompt(
            [TextContentBlock(type="text", text=text)],
            generation=generation,
            projection=projection,
        )
    finally:
        projection.close_producer()
    if projection.overflowed:
        raise QualificationRefused("Slice B presentation overflowed")
    turn = projection.finalize(response.stop_reason)
    return turn.assistant_text, response.stop_reason


async def _retire_required(process: Any) -> dict[str, Any]:
    result = await process.retire(send_close=True, release_claim=True)
    if not result.clean or not result.child_exit_observed or result.stderr_failure_code is not None:
        raise QualificationRefused("Slice B Prime process did not retire cleanly")
    return {
        "childExitObserved": result.child_exit_observed,
        "clean": result.clean,
        "stderrFailureCode": result.stderr_failure_code,
        "stderrTotalBytes": result.stderr_total_bytes,
        "stderrTruncated": result.stderr_truncated,
    }


def _runtime_source_identity(source_root: Path) -> str:
    source_root = source_root.resolve(strict=True)
    pyproject = source_root / "pyproject.toml"
    rlm_root = source_root / "src/rlm"
    if not pyproject.is_file() or pyproject.is_symlink() or not rlm_root.is_dir() or rlm_root.is_symlink():
        raise QualificationRefused("manifest-bound Prime Python runtime source is unavailable")
    files = [pyproject, *(path for path in rlm_root.rglob("*.py") if path.is_file() and not path.is_symlink())]
    files.sort(key=str)
    digest = hashlib.sha256()
    for path in files:
        relative = str(path.relative_to(source_root))
        digest.update(relative.encode("utf-8", "strict"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _read_bootstrap_version(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise QualificationRefused("Slice B kernel bootstrap version is unavailable")
    with path.open("rb") as stream:
        data = stream.read(MAX_BOOTSTRAP_VERSION_BYTES + 1)
    if len(data) > MAX_BOOTSTRAP_VERSION_BYTES:
        raise QualificationRefused("Slice B kernel bootstrap version is oversized")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate bootstrap-version key")
            result[key] = value
        return result

    try:
        value = json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=unique_object,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise QualificationRefused("Slice B kernel bootstrap version is invalid") from exc
    if type(value) is not dict or set(value) != {"extraUvArgs", "pythonSkills", "runtime", "schema", "snapshot"}:
        raise QualificationRefused("Slice B kernel bootstrap version schema differs")
    return value


def _kernel_result(protocol: dict[str, Any], runtime_source: Path) -> dict[str, Any]:
    venv = Path(protocol["kernel"]["venvPath"])
    python = Path(protocol["kernel"]["pythonPath"])
    cache = Path(protocol["kernel"]["uvCachePath"])
    managed = Path(protocol["kernel"]["uvPythonInstallPath"])
    if not venv.is_dir() or not python.is_file() or python.is_symlink() or not cache.is_dir() or not managed.is_dir():
        raise QualificationRefused("Slice B cold kernel was not materialized")
    managed_pythons = sorted(path for path in managed.rglob("python.exe") if path.is_file() and not path.is_symlink())
    if not managed_pythons or len(managed_pythons) > 32:
        raise QualificationRefused("Slice B managed Python inventory is invalid")
    bootstrap_path = venv / ".bootstrap-version"
    bootstrap = _read_bootstrap_version(bootstrap_path)
    runtime_identity = _runtime_source_identity(runtime_source)
    if (
        bootstrap["schema"] != 9
        or bootstrap["runtime"] != runtime_identity
        or bootstrap["snapshot"] != "dill"
        or bootstrap["extraUvArgs"] != list(DEFAULT_RLM_EXTRA_UV_ARGS)
        or type(bootstrap["pythonSkills"]) is not list
    ):
        raise QualificationRefused("Slice B kernel did not install the manifest-bound runtime source")
    return {
        "bootstrapVersionSha256": sha256_file(bootstrap_path),
        "cachePath": str(cache),
        "kernelPythonPath": str(python),
        "managedPythonPaths": [str(path) for path in managed_pythons],
        "runtimeSourceIdentity": runtime_identity,
        "uvPythonInstallPath": str(managed),
        "venvPath": str(venv),
    }


def _verify_hostile_fixtures(evidence: EvidenceRoot, workspace: SliceBWorkspace) -> None:
    live = workspace.assigned_file.parent
    for relative, expected in workspace.hostile_hashes.items():
        path = live / Path(relative)
        if not path.is_file() or path.is_symlink() or sha256_file(path) != expected:
            raise QualificationRefused(f"Slice B hostile fixture changed: {relative}")


async def run_installed_slice_b(
    protocol: dict[str, Any],
    repo_root: Path,
    evidence: EvidenceRoot,
    prepared: PreparedSliceB,
    workspace: SliceBWorkspace,
    *,
    process_starter: ProcessStarter = _start_owned_process,
    services_factory: ServicesFactory = _start_slice_b_services,
) -> dict[str, Any]:
    from rook.agent.chat.acp_storage import OpenClaim, validate_prime_session_header

    cold_paths = [
        Path(protocol["kernel"]["venvPath"]),
        Path(protocol["kernel"]["pythonPath"]),
        Path(protocol["kernel"]["uvCachePath"]),
        Path(protocol["kernel"]["uvPythonInstallPath"]),
    ]
    if any(path.exists() or path.is_symlink() for path in cold_paths):
        raise QualificationRefused("Slice B kernel was not cold before ACP establishment")
    verify_no_managed_helpers(protocol, prepared.environment)
    if prepared.session_path.exists() or workspace.assigned_file.exists():
        raise QualificationRefused("Slice B output existed before ACP establishment")

    limits = protocol["limits"]
    first_text = ""
    reopen_text = ""
    cancel_stop = ""
    retirements: list[dict[str, Any]] = []
    session_ids: list[str] = []
    with services_factory(protocol, workspace, evidence) as services:
        first_claim = OpenClaim.acquire(workspace.claims_root, str(prepared.session_path.resolve(strict=False)))
        first = await process_starter(
            prepared.initial_argv,
            prepared.environment,
            first_claim,
            1,
            Path(workspace.provisional_association.working_directory),
        )
        try:
            initialized = await first.initialize()
            if not initialized.image_supported:
                raise QualificationRefused("installed Prime did not advertise ACP image support")
            session_ids.append(
                await first.new_session(
                    cwd=Path(protocol["environment"]["roots"]["projectResume"]),
                    mcp_servers=[_build_qualification_mcp_server(protocol, repo_root, workspace.mcp_journal_paths[0])],
                )
            )
            first_text, first_stop = await _prompt_once(
                first,
                protocol["inputs"]["sliceBFirstPrompt"]["text"],
                launch_generation=1,
                prompt_id="slice-b-first",
            )
            if first_text != "FIRST_OK:alpha" or first_stop != "end_turn":
                raise QualificationRefused("Slice B first prompt result differs")
            header = validate_prime_session_header(
                prepared.session_path,
                expected_id=None,
                expected_cwd=Path(workspace.provisional_association.working_directory),
                sessions_root=workspace.association_store.paths.sessions_root,
            )
            association = workspace.association_store.publish(workspace.provisional_association, header)
            if workspace.association_store.get(association.conversation_id) != association:
                raise QualificationRefused("Slice B association publication differs")
            cancel_task = asyncio.create_task(
                _prompt_once(
                    first,
                    protocol["inputs"]["sliceBCancelPrompt"]["text"],
                    launch_generation=1,
                    prompt_id="slice-b-cancel",
                )
            )
            try:
                await _wait_for_journal_event(
                    workspace.mcp_journal_paths[0],
                    event="mcp_call_started",
                    name="qualification_wait",
                    timeout_seconds=20,
                    max_records=limits["maxProxyLedgerRecords"],
                    max_bytes=limits["maxProxyLedgerBytes"],
                )
                await first.cancel()
                _cancel_text, cancel_stop = await cancel_task
            except BaseException:
                cancel_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await cancel_task
                raise
            if cancel_stop != "cancelled":
                raise QualificationRefused("Slice B cancellation did not settle as cancelled")
        finally:
            retirements.append(await _retire_required(first))

        if any(workspace.claims_root.glob("*.open.claim")):
            raise QualificationRefused("Slice B first claim remained after observed exit")
        if not prepared.session_path.is_file() or prepared.session_path.is_symlink():
            raise QualificationRefused("Slice B Prime session was not persisted")

        reopen_claim = OpenClaim.acquire(workspace.claims_root, str(prepared.session_path.resolve(strict=True)))
        try:
            reopened_association = workspace.association_store.get(association.conversation_id)
            if reopened_association != association:
                raise QualificationRefused("Slice B durable association changed before reopen")
            if reopened_association.runtime_id != protocol["runtime"]["runtimeId"]:
                raise QualificationRefused("Slice B durable runtime changed before reopen")
            validate_prime_session_header(
                Path(reopened_association.session_path),
                expected_id=reopened_association.prime_session_id,
                expected_cwd=Path(reopened_association.working_directory),
                sessions_root=workspace.association_store.paths.sessions_root,
            )
        except BaseException:
            reopen_claim.release_no_child_created()
            raise
        reopened = await process_starter(
            prepared.reopen_argv,
            prepared.environment,
            reopen_claim,
            2,
            Path(reopened_association.working_directory),
        )
        try:
            initialized = await reopened.initialize()
            if not initialized.image_supported:
                raise QualificationRefused("reopened Prime did not advertise ACP image support")
            session_ids.append(
                await reopened.new_session(
                    cwd=Path(protocol["environment"]["roots"]["projectResume"]),
                    mcp_servers=[_build_qualification_mcp_server(protocol, repo_root, workspace.mcp_journal_paths[1])],
                )
            )
            reopen_text, reopen_stop = await _prompt_once(
                reopened,
                protocol["inputs"]["sliceBReopenPrompt"]["text"],
                launch_generation=2,
                prompt_id="slice-b-reopen",
            )
            if reopen_text != "REOPEN_OK:FIRST_OK:alpha" or reopen_stop != "end_turn":
                raise QualificationRefused("Slice B reopened context differs")
        finally:
            retirements.append(await _retire_required(reopened))

        if services.daemon_tripwire.contact_count != 0:
            raise QualificationRefused("Slice B contacted the daemon tripwire")

    if any(workspace.claims_root.glob("*.open.claim")):
        raise QualificationRefused("Slice B reopen claim remained after observed exit")
    if workspace.assigned_file.read_bytes() != b"qualified\n":
        raise QualificationRefused("Slice B assigned file differs")
    _verify_hostile_fixtures(evidence, workspace)

    provider_rows = _read_bounded_jsonl(
        services.provider_journal.path,
        max_records=limits["maxProxyLedgerRecords"],
        max_bytes=limits["maxProxyLedgerBytes"],
    )
    verify_slice_b_provider_journal(protocol, provider_rows)

    proxy_rows = _read_bounded_jsonl(
        services.proxy_journal.path,
        max_records=limits["maxProxyLedgerRecords"],
        max_bytes=limits["maxProxyLedgerBytes"],
    )
    transport_abort_count = verify_proxy_observations(proxy_rows, set(protocol["environment"]["proxy"]["admittedHosts"]))
    verify_no_managed_helpers(protocol, prepared.environment)

    mcp_rows = [
        _read_bounded_jsonl(
            path,
            max_records=limits["maxProxyLedgerRecords"],
            max_bytes=limits["maxProxyLedgerBytes"],
        )
        for path in workspace.mcp_journal_paths
    ]
    verify_slice_b_mcp_journals(mcp_rows)

    kernel = _kernel_result(protocol, Path(prepared.contract.prime_agent_runtime_path))
    for name, path in (("provider", services.provider_journal.path), ("proxy", services.proxy_journal.path),
                       ("mcp-first", workspace.mcp_journal_paths[0]), ("mcp-reopen", workspace.mcp_journal_paths[1])):
        evidence.copy_file(f"slice-b/{name}.jsonl", path)
    with prepared.session_path.open("rb") as stream:
        header_bytes = stream.readline(65537)
    if len(header_bytes) > 65536:
        raise QualificationRefused("session header evidence exceeds limit")
    evidence.write_bytes("slice-b/session-header.json", header_bytes)
    return {
        "assignedFileSha256": sha256_file(workspace.assigned_file),
        "associationSha256": sha256_file(
            workspace.association_store.paths.conversation_path(workspace.provisional_association.conversation_id)
        ),
        "conversationId": workspace.provisional_association.conversation_id,
        "cancelStopReason": cancel_stop,
        "childEnvironment": prepared.environment,
        "childEnvironmentSha256": sha256_bytes(canonical_json_bytes(prepared.environment)),
        "daemonContacts": services.daemon_tripwire.contact_count,
        "firstAssistantText": first_text,
        "kernel": kernel,
        "mcpJournalSha256": [sha256_file(path) for path in workspace.mcp_journal_paths],
        "outcome": "passed",
        "providerJournalSha256": sha256_file(services.provider_journal.path),
        "proxyJournalSha256": sha256_file(services.proxy_journal.path),
        "observedTransportAbortCount": transport_abort_count,
        "transportAbortAssessment": "observed transport aborts, cause undetermined" if transport_abort_count else None,
        "reopenAssistantText": reopen_text,
        "retirements": retirements,
        "runtimeId": protocol["runtime"]["runtimeId"],
        "runtimePythonSourceManifestSha256": prepared.contract.prime_agent_runtime_manifest_sha256,
        "sessionIds": session_ids,
        "sessionSha256": sha256_file(prepared.session_path),
        "uv": {
            "executablePath": str(prepared.contract.uv_executable_path),
            "sha256": sha256_file(Path(prepared.contract.uv_executable_path)),
            "version": prepared.contract.uv_version,
        },
    }


SLICE_A_RHINO_SYSTEM_DIR = Path("C:/Program Files/Rhino 8/System")
SLICE_A_MANAGED_TEST_COUNT = 97
MANAGED_TRX_MAX_BYTES = 1_048_576


def _restored_managed_nuget_root(repo_root: Path) -> Path:
    try:
        project = repo_root / "src/Rook.Tests/Rook.Tests.csproj"
        assets = json.loads((project.parent / "obj/project.assets.json").read_text(encoding="utf-8-sig"))
        restore = assets["project"]["restore"]
        root = Path(restore["packagesPath"])
        if (not root.is_absolute() or not root.is_dir()
                or root.as_posix().rstrip("/").casefold() not in {
                    Path(folder).as_posix().rstrip("/").casefold() for folder in assets["packageFolders"]}
                or Path(restore["projectPath"]).resolve() != project.resolve()):
            raise ValueError("restored project/package root differs")
        rows = [(key, row) for key, row in assets["libraries"].items()
                if key.startswith("xunit.runner.visualstudio/") and row["type"] == "package"]
        if len(rows) != 1:
            raise ValueError("one restored xUnit adapter is required")
        key, row = rows[0]
        if row["path"] != key:
            raise ValueError("adapter package path differs")
        package = (root / row["path"]).resolve(strict=True)
        if not package.is_relative_to(root.resolve(strict=True)):
            raise ValueError("adapter package escapes cache")
        metadata = json.loads((package / ".nupkg.metadata").read_text(encoding="utf-8-sig"))
        if metadata["contentHash"] != row["sha512"]:
            raise ValueError("restored adapter identity differs")
        for name in ("xunit.runner.visualstudio.props", "xunit.runner.visualstudio.testadapter.dll",
                     "xunit.abstractions.dll", "xunit.runner.reporters.net452.dll", "xunit.runner.utility.net452.dll"):
            path = package / "build/net462" / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("restored adapter file is unavailable")
        return root.resolve(strict=True)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise QualificationRefused(f"managed NuGet admission failed: {exc}") from exc


def _validate_managed_trx(directory: Path) -> bytes:
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("results directory is unavailable")
        entries = directory.iterdir()
        path = next(entries, None)
        if (path is None or next(entries, None) is not None or path.name != "managed.trx"
                or path.is_symlink() or not path.is_file() or path.stat().st_size > MANAGED_TRX_MAX_BYTES):
            raise ValueError("exactly one bounded regular managed.trx is required")
        with path.open("rb") as stream:
            data = stream.read(MANAGED_TRX_MAX_BYTES + 1)
        if len(data) > MANAGED_TRX_MAX_BYTES:
            raise ValueError("TRX exceeds byte limit")
        text = data.decode("utf-8-sig", errors="strict")
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            raise ValueError("DTD/entities are forbidden")
        tree = ET.fromstring(text)  # ElementTree does not fetch external resources.
        ns = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}"
        summaries = tree.findall(ns + "ResultSummary")
        results = tree.findall(ns + "Results")
        if tree.tag != ns + "TestRun" or len(summaries) != 1 or len(results) != 1:
            raise ValueError("TRX structure differs")
        counters = summaries[0].findall(ns + "Counters")
        if len(counters) != 1 or summaries[0].get("outcome") not in {"Passed", "Completed"}:
            raise ValueError("TRX summary did not pass")
        values = counters[0].attrib
        if not {"total", "executed", "passed", "failed", "aborted", "notExecuted"}.issubset(values):
            raise ValueError("TRX counters are missing")
        for key, value in values.items():
            expected = SLICE_A_MANAGED_TEST_COUNT if key in {"total", "executed", "passed"} else 0
            if not value.isascii() or not value.isdecimal() or int(value) != expected:
                raise ValueError("TRX counters differ from the frozen nonzero count")
        rows = list(results[0])
        if len(rows) != SLICE_A_MANAGED_TEST_COUNT:
            raise ValueError("TRX result count differs")
        for key in ("executionId", "testId"):
            ids = [row.get(key) for row in rows]
            if any(not value for value in ids) or len(set(ids)) != len(rows):
                raise ValueError("TRX contains missing or duplicate identities")
        if any(row.tag != ns + "UnitTestResult" or row.get("outcome") != "Passed"
               or not row.get("testName", "").startswith("Rook.Tests.UI.Chat.") for row in rows):
            raise ValueError("TRX contains an unexecuted, failing, or unselected test")
        return data
    except (OSError, ValueError, ET.ParseError) as exc:
        raise QualificationRefused(f"managed TRX refused: {exc}") from exc


def _required_executable(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise QualificationRefused(f"required qualification executable is unavailable: {name}")
    return str(Path(path).resolve(strict=True))


def verify_slice_b_provider_journal(protocol: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    # Two first-turn requests, one cancelled request, then two reopen requests.
    if [row.get("event") for row in rows] != ["provider_started", *(["provider_request"] * 5), "provider_stopped"]:
        raise QualificationRefused("Slice B provider journal event sequence differs")
    url = urlparse(protocol["network"]["providerUrl"])
    if rows[0] != {"event": "provider_started", "host": url.hostname, "port": url.port} or rows[-1] != {"event": "provider_stopped"}:
        raise QualificationRefused("Slice B provider journal lifecycle differs")
    expected = [("sliceBFirstPrompt", []), ("sliceBFirstPrompt", ["assistant", "tool"]),
                ("sliceBCancelPrompt", []), ("sliceBReopenPrompt", []),
                ("sliceBReopenPrompt", ["assistant", "tool"])]
    for row, (prompt, following_roles) in zip(rows[1:-1], expected, strict=True):
        roles = row.get("messageRoles")
        if (type(roles) is not list or "user" not in roles
                or any(role not in ("system", "developer", "user", "assistant", "tool") for role in roles)):
            raise QualificationRefused("Slice B provider journal message roles differ")
        last_user = len(roles) - 1 - roles[::-1].index("user")
        if (row.get("path") != "/v1/chat/completions"
                or row.get("lastUserSha256") != protocol["inputs"][prompt]["sha256"]
                or roles[last_user + 1:] != following_roles
                or row.get("hostileMarkerPresent") is not False
                or row.get("globalSystemPresent") is not True
                or row.get("goalSkillPresent") is not True
                or row.get("rookContractPresent") is not True):
            raise QualificationRefused("Slice B provider journal ordered request properties differ")


def verify_slice_b_mcp_journals(journals: list[list[dict[str, Any]]]) -> None:
    expected = []
    for value in ("alpha", "reopen"):
        rows = [
            {"event": "mcp_process_started"},
            {"event": "mcp_list_tools"},
            {"event": "mcp_call_started", "name": "qualification_echo", "arguments": {"value": value}},
            {"event": "mcp_call_finished", "name": "qualification_echo"},
        ]
        if value == "alpha":
            rows.append({"event": "mcp_call_started", "name": "qualification_wait", "arguments": {"value": "cancel"}})
        expected.append(rows)
    if journals != expected:
        raise QualificationRefused("Slice B MCP journal sequence differs")


def verify_proxy_observations(rows: list[dict[str, Any]], allowed: set[str]) -> int:
    if any(type(row) is not dict or type(row.get("event")) is not str or row["event"] not in {
        "proxy_started", "proxy_stopped", "proxy_admitted", "proxy_transport_aborted",
    } for row in rows):
        raise QualificationRefused("Slice B proxy recorded a refusal or connection failure")
    admissions = [row for row in rows if row.get("event") == "proxy_admitted"]
    if not admissions or any(type(row.get("host")) is not str or row["host"] not in allowed or type(row.get("port")) is not int
                             or row["port"] != 443 for row in admissions):
        raise QualificationRefused("Slice B proxy has no valid cold-bootstrap admission")
    admitted = set()
    abort_count = 0
    for row in rows:
        if row["event"] == "proxy_admitted":
            authority = f"{row['host']}:443"
            if row.get("authority", authority) != authority:
                raise QualificationRefused("Slice B proxy admission authority differs")
            admitted.add(authority)
        elif row["event"] == "proxy_transport_aborted":
            keys = {"event", "authority", "detail", "operation", "socketSide", "direction",
                    "exceptionType", "errno", "winerror", "pendingBytes", "eof", "writeClosed", "stopping"}
            if (set(row) != keys or type(row["authority"]) is not str or row["authority"] not in admitted
                    or row["operation"] not in ("send", "recv", "shutdown_write")
                    or row["socketSide"] not in ("client", "upstream")
                    or row["exceptionType"] not in ("ConnectionError", "ConnectionAbortedError", "ConnectionResetError",
                                                     "ConnectionRefusedError", "BrokenPipeError")
                    or row["stopping"] is not False
                    or type(row["detail"]) is not str or len(row["detail"]) > 512
                    or any(row[key] is not None and type(row[key]) is not int for key in ("errno", "winerror"))):
                raise QualificationRefused("Slice B proxy transport diagnostic is invalid")
            side = row["socketSide"]
            peer = "upstream" if side == "client" else "client"
            direction = f"{side}_to_{peer}" if row["operation"] == "recv" else f"{peer}_to_{side}"
            if row["direction"] != direction:
                raise QualificationRefused("Slice B proxy transport direction differs")
            pending = row["pendingBytes"]
            if (type(pending) is not dict or set(pending) != {"toClient", "toUpstream"}
                    or any(type(value) is not int or not 0 <= value <= 65536 for value in pending.values())):
                raise QualificationRefused("Slice B proxy pending-byte evidence is invalid")
            for key in ("eof", "writeClosed"):
                states = row[key]
                if (type(states) is not dict or set(states) != {"client", "upstream"}
                        or any(type(value) is not bool for value in states.values())):
                    raise QualificationRefused("Slice B proxy socket-state evidence is invalid")
            abort_count += 1
    return abort_count


def verify_no_managed_helpers(protocol: dict[str, Any], environment: dict[str, str]) -> None:
    roots = protocol["environment"]["roots"]
    for path in (Path(roots["primeAgentDir"]) / "bin", Path(roots["userProfile"]) / ".prime/agent/bin"):
        if path.exists() or path.is_symlink():
            raise QualificationRefused("managed helper download directory was created")
    for directory in environment["PATH"].split(os.pathsep):
        for name in ("fd", "fd.exe", "rg", "rg.exe"):
            path = Path(directory) / name
            if path.exists() or path.is_symlink():
                raise QualificationRefused("managed helper executable is present")


class ProductPrecontactOperations:
    def __init__(
        self,
        *,
        process_runner: ProcessRunner = run_bounded_process,
        slice_b_preparer: SliceBPreparer = prepare_slice_b,
        slice_b_runner: SliceBRunner = run_installed_slice_b,
    ) -> None:
        self._process_runner = process_runner
        self._slice_b_preparer = slice_b_preparer
        self._slice_b_runner = slice_b_runner
        self._prepared: PreparedSliceB | None = None
        self._commands: list[tuple[str, ProcessSpec]] | None = None

    def prepare_admission(self, protocol: dict[str, Any], repo_root: Path) -> None:
        self._prepared = self._slice_b_preparer(protocol, repo_root,
            session_path=qualification_data_paths(protocol).session_path(protocol["qualificationConversationId"]).resolve(strict=False))
        self._commands = self._slice_a_commands(protocol, repo_root)

    @staticmethod
    def _slice_a_commands(protocol: dict[str, Any], repo_root: Path) -> list[tuple[str, ProcessSpec]]:
        limits = protocol["limits"]
        python = str(Path(sys.executable).resolve(strict=True))
        tools = {name: _required_executable(name) for name in ("dotnet", "node", "pwsh", "git")}
        rhino_system = SLICE_A_RHINO_SYSTEM_DIR
        if not rhino_system.is_absolute() or not rhino_system.is_dir():
            raise QualificationRefused("required Rhino System directory is unavailable")
        rhino_system = rhino_system.resolve(strict=True)
        for name in ("Eto.dll", "Eto.Wpf.dll", "Microsoft.WindowsAPICodePack.dll",
                     "Microsoft.WindowsAPICodePack.Shell.dll", "Xceed.Wpf.Toolkit.dll"):
            assembly = rhino_system / name
            if assembly.is_symlink() or not assembly.is_file():
                raise QualificationRefused(f"required Rhino managed assembly is unavailable: {name}")
        test_root = Path(protocol["executionRoot"]) / "slice-a"
        nuget_root = _restored_managed_nuget_root(repo_root)
        managed_results = test_root / f"managed-results-{uuid4().hex}"
        roots = {key: str(test_root / key) for key in ("home", "userProfile", "appData", "localAppData", "temp")}
        windows = Path(protocol["environment"]["expectedFinal"].get("SYSTEMROOT", "C:/Windows"))
        environment = {
            "SYSTEMROOT": str(windows), "WINDIR": str(windows),
            "COMSPEC": str(windows / "System32/cmd.exe"), "PATHEXT": ".COM;.EXE;.BAT;.CMD",
            "PATH": os.pathsep.join(dict.fromkeys([str(Path(python).parent),
                      *(str(Path(path).parent) for path in tools.values()), str(windows / "System32")])),
            "HOME": roots["home"], "USERPROFILE": roots["userProfile"],
            "APPDATA": roots["appData"], "LOCALAPPDATA": roots["localAppData"],
            "TEMP": roots["temp"], "TMP": roots["temp"], "CI": "1", "PYTHONDONTWRITEBYTECODE": "1",
        }
        tests = tuple(protocol["inputs"]["sliceATestFiles"])
        common = {
            "environment": environment,
            "timeout_seconds": limits["wallClockSeconds"],
            "close_seconds": limits["processCloseSeconds"],
            "max_output_bytes": limits["maxProcessOutputBytes"],
        }
        return [
            (
                "python-acp-boundary",
                ProcessSpec(
                    argv=(python, "-m", "pytest", *tests, "-q"),
                    cwd=repo_root / "mcp_server",
                    **common,
                ),
            ),
            (
                "managed-chat-panel",
                ProcessSpec(
                    argv=(
                        tools["dotnet"],
                        "test",
                        "src/Rook.Tests/Rook.Tests.csproj",
                        "--no-restore",
                        f"-p:RhinoSystemDir={rhino_system}",
                        f"-p:NuGetPackageRoot={nuget_root}{os.sep}",
                        "--logger", "trx;LogFileName=managed.trx",
                        "--results-directory", str(managed_results),
                        "--filter",
                        "FullyQualifiedName~Rook.Tests.UI.Chat",
                    ),
                    cwd=repo_root,
                    **common,
                ),
            ),
            (
                "browser-image-composer",
                ProcessSpec(
                    argv=(
                        tools["node"],
                        "--test",
                        "src/Rook.Tests/UI/Chat/composer-images.test.cjs",
                    ),
                    cwd=repo_root,
                    **common,
                ),
            ),
            (
                "cutover-verifier",
                ProcessSpec(
                    argv=(python, str(repo_root / "scripts/verify-rookchat-acp-cutover.py"), "--root", str(repo_root)),
                    cwd=repo_root,
                    **common,
                ),
            ),
            (
                "installer-source-guard",
                ProcessSpec(
                    argv=(
                        tools["pwsh"],
                        "-NoProfile",
                        "-File",
                        str(repo_root / "scripts/tests/release-installer-guards.tests.ps1"),
                        "-SkipBuiltPayloadCheck",
                    ),
                    cwd=repo_root,
                    **common,
                ),
            ),
        ]

    async def run_slice_a(self, protocol: dict[str, Any], repo_root: Path, evidence: EvidenceRoot) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        commands = self._commands if self._commands is not None else self._slice_a_commands(protocol, repo_root)
        for index, (label, spec) in enumerate(commands, start=1):
            for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
                Path(spec.environment[key]).mkdir(parents=True, exist_ok=True)
            if label == "managed-chat-panel":
                if spec.argv.count("--results-directory") != 1:
                    raise QualificationRefused("managed TRX results path is required")
                managed_results = Path(spec.argv[spec.argv.index("--results-directory") + 1])
                if (not managed_results.is_absolute() or managed_results.is_symlink()
                        or managed_results.parent.resolve() != (Path(protocol["executionRoot"]) / "slice-a").resolve()):
                    raise QualificationRefused("managed TRX results path escapes Slice A")
                try:
                    managed_results.mkdir(exist_ok=False)
                except OSError as exc:
                    raise QualificationRefused("managed TRX results directory must be fresh") from exc
            result = await self._process_runner(spec)
            prefix = f"slice-a/{index:02d}-{label}"
            evidence.write_bytes(prefix + ".stdout", result.stdout)
            evidence.write_bytes(prefix + ".stderr", result.stderr)
            row = {
                "argv": list(spec.argv),
                "cwd": str(spec.cwd),
                "exitCode": result.exit_code,
                "label": label,
                "outputOverflow": result.output_overflow,
                "stderrBytes": len(result.stderr),
                "stderrSha256": sha256_bytes(result.stderr),
                "stdoutBytes": len(result.stdout),
                "stdoutSha256": sha256_bytes(result.stdout),
                "timedOut": result.timed_out,
            }
            rows.append(row)
            if (
                result.exit_code != 0
                or result.timed_out
                or result.output_overflow
                or not result.direct_child_exit_observed
            ):
                raise QualificationRefused(f"Slice A command failed: {label}")
            if label == "managed-chat-panel":
                trx = _validate_managed_trx(managed_results)
                evidence.write_bytes(prefix + ".trx", trx)
                row["managedTestsPassed"] = SLICE_A_MANAGED_TEST_COUNT
                row["managedTrxSha256"] = sha256_bytes(trx)
        return {"commands": rows, "outcome": "passed"}

    async def run_slice_b(self, protocol: dict[str, Any], repo_root: Path, evidence: EvidenceRoot) -> dict[str, Any]:
        if self._prepared is None:
            raise QualificationRefused("Slice B has no admitted preparation")
        workspace = prepare_slice_b_workspace(protocol, repo_root, evidence)
        if Path(workspace.provisional_association.session_path) != self._prepared.session_path:
            raise QualificationRefused("Slice B workspace changed the admitted session path")
        return await self._slice_b_runner(protocol, repo_root, evidence, self._prepared, workspace)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--expected-qualification-commit", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        asyncio.run(execute_precontact(args.protocol, args.repo_root,
                                      expected_qualification_commit=args.expected_qualification_commit))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"precontact_refused: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
