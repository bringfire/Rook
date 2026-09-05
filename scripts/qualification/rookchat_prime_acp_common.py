"""Finite, external custody helpers for RookChat Prime ACP qualification."""

from __future__ import annotations

import ast
import asyncio
import contextlib
import hashlib
import json
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID


MAX_PROTOCOL_BYTES = 512 * 1024
SHA256_PATTERN = re.compile(r"[A-F0-9]{64}")
COMMIT_PATTERN = re.compile(r"[a-f0-9]{40}")
ADMITTED_BOOTSTRAP_HOSTS = (
    "api.github.com",
    "files.pythonhosted.org",
    "github.com",
    "objects.githubusercontent.com",
    "pypi.org",
    "release-assets.githubusercontent.com",
    "releases.astral.sh",
)
PRODUCT_UV_KEYS = frozenset(
    {
        "UV_CACHE_DIR",
        "UV_NO_CONFIG",
        "UV_PYTHON_INSTALL_DIR",
        "UV_PYTHON_INSTALL_REGISTRY",
        "UV_PYTHON_NO_REGISTRY",
        "UV_PYTHON_PREFERENCE",
    }
)
PRODUCT_SOURCE_PATHS = (
    "installer",
    "mcp_server/src/rook",
    "src/Rook",
    "src/RookNative",
)


class QualificationRefused(RuntimeError):
    """A frozen qualification precondition was not satisfied."""


def canonical_json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise QualificationRefused("value is not canonical JSON") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            digest = hashlib.sha256()
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise QualificationRefused(f"cannot hash input: {path}") from exc
    return digest.hexdigest().upper()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise QualificationRefused(f"duplicate protocol key: {key}")
        result[key] = value
    return result


def _closed(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise QualificationRefused(f"{label} schema differs")
    return value


def _positive_int(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise QualificationRefused(f"{label} must be a positive integer")
    return value


def _absolute_path(value: object, label: str) -> Path:
    if type(value) is not str or not value or "\0" in value:
        raise QualificationRefused(f"{label} path is invalid")
    path = Path(value)
    if not path.is_absolute():
        raise QualificationRefused(f"{label} path is not absolute")
    return path


def _relative_path(value: object, label: str) -> PurePosixPath:
    if type(value) is not str or not value or "\\" in value or ":" in value:
        raise QualificationRefused(f"{label} path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        raise QualificationRefused(f"{label} path is not canonical")
    return path


def _hash(value: object, label: str) -> str:
    if type(value) is not str or SHA256_PATTERN.fullmatch(value) is None:
        raise QualificationRefused(f"{label} SHA-256 is invalid")
    return value


def _content_row(value: object, label: str) -> None:
    row = _closed(value, {"sha256", "text"}, label)
    if type(row["text"]) is not str:
        raise QualificationRefused(f"{label} text is invalid")
    if _hash(row["sha256"], label) != sha256_bytes(row["text"].encode("utf-8", "strict")):
        raise QualificationRefused(f"{label} hash differs")


def validate_precontact_protocol(protocol: object) -> dict[str, Any]:
    value = _closed(
        protocol,
        {
            "environment",
            "evaluator",
            "evidenceRoot",
            "executionVersion",
            "implementationCommit",
            "inputs",
            "kernel",
            "launch",
            "limits",
            "network",
            "protocolId",
            "runtime",
            "schemaVersion",
            "sourceInputs",
            "target",
        },
        "pre-contact protocol",
    )
    if value["schemaVersion"] != 1 or value["protocolId"] != "rookchat-prime-acp-precontact":
        raise QualificationRefused("protocol identity differs")
    _positive_int(value["executionVersion"], "execution version")
    if type(value["implementationCommit"]) is not str or COMMIT_PATTERN.fullmatch(value["implementationCommit"]) is None:
        raise QualificationRefused("implementation commit is invalid")
    _absolute_path(value["evidenceRoot"], "evidence root")
    if value["evaluator"] is not None:
        raise QualificationRefused("pre-contact evaluator must be null")

    limits = _closed(
        value["limits"],
        {
            "maxEvidenceFileBytes",
            "maxProcessOutputBytes",
            "maxProxyLedgerBytes",
            "maxProxyLedgerRecords",
            "processCloseSeconds",
            "tokenLimit",
            "wallClockSeconds",
        },
        "limits",
    )
    for key, item in limits.items():
        _positive_int(item, key)

    runtime = _closed(
        value["runtime"],
        {
            "acpCompatibilityVersion",
            "installRoot",
            "manifestPath",
            "manifestSha256",
            "primeExecutableSha256",
            "rookSkillManifestSha256",
            "runtimeId",
        },
        "runtime",
    )
    _positive_int(runtime["acpCompatibilityVersion"], "ACP compatibility version")
    install_root = _absolute_path(runtime["installRoot"], "runtime install root")
    runtime_id = _hash(runtime["runtimeId"], "runtime ID")
    if _hash(runtime["manifestSha256"], "runtime manifest") != runtime_id:
        raise QualificationRefused("runtime manifest identity differs")
    _hash(runtime["primeExecutableSha256"], "Prime executable")
    _hash(runtime["rookSkillManifestSha256"], "Rook skill manifest")
    manifest_path = _absolute_path(runtime["manifestPath"], "runtime manifest")
    expected_manifest = install_root / "runtimes" / runtime_id / "runtime-manifest.json"
    if manifest_path != expected_manifest:
        raise QualificationRefused("runtime manifest path differs")

    launch = _closed(
        value["launch"],
        {
            "managedHelperAcquisitionReachable",
            "mcpServerName",
            "model",
            "productionForbiddenArguments",
            "productionRequiredArguments",
            "qualificationOnlyArguments",
            "reasoning",
        },
        "launch",
    )
    if launch["managedHelperAcquisitionReachable"] is not False or launch["mcpServerName"] != "rook":
        raise QualificationRefused("launch authority differs")
    if (
        type(launch["model"]) is not str
        or launch["model"].count("/") != 1
        or any(not part for part in launch["model"].split("/"))
        or launch["reasoning"] != "off"
    ):
        raise QualificationRefused("qualification model selection differs")
    if launch["productionRequiredArguments"] != ["--mode", "acp", "--no-daemon", "--no-approve"]:
        raise QualificationRefused("required production arguments differ")
    if launch["productionForbiddenArguments"] != ["--offline", "--no-managed-tool-downloads"]:
        raise QualificationRefused("forbidden production arguments differ")

    inputs = _closed(
        value["inputs"],
        {"sliceAPrompt", "sliceATestFiles", "sliceBCancelPrompt", "sliceBFirstPrompt", "sliceBReopenPrompt"},
        "inputs",
    )
    for key in ("sliceAPrompt", "sliceBCancelPrompt", "sliceBFirstPrompt", "sliceBReopenPrompt"):
        _content_row(inputs[key], key)
    tests = inputs["sliceATestFiles"]
    if type(tests) is not list or not tests or tests != sorted(set(tests)):
        raise QualificationRefused("Slice A test files are not a unique ordered list")
    for test in tests:
        _relative_path(test, "Slice A test")

    target = _closed(
        value["target"],
        {"hostGenerationId", "profile", "rhinoDocumentSerial", "routeProcessId"},
        "target",
    )
    if target["profile"] != "full":
        raise QualificationRefused("pre-contact profile differs")
    try:
        generation = UUID(target["hostGenerationId"])
    except (ValueError, TypeError, AttributeError) as exc:
        raise QualificationRefused("host generation ID is invalid") from exc
    if str(generation) != target["hostGenerationId"] or generation.int == 0:
        raise QualificationRefused("host generation ID is not canonical")
    _positive_int(target["routeProcessId"], "route process ID")
    _positive_int(target["rhinoDocumentSerial"], "Rhino document serial")

    environment = _closed(
        value["environment"],
        {"expectedFinal", "expectedFinalSha256", "productOwnedUv", "proxy", "roots", "seededAmbientKeys"},
        "environment",
    )
    roots = _closed(
        environment["roots"],
        {
            "appData",
            "home",
            "localAppData",
            "primeAgentDir",
            "projectLaunch",
            "projectResume",
            "rookDataDir",
            "sessions",
            "temp",
            "userProfile",
        },
        "environment roots",
    )
    for key, item in roots.items():
        _absolute_path(item, key)
    evidence_root = Path(value["evidenceRoot"])
    expected_live_root = evidence_root / "live"
    if any(expected_live_root not in (Path(item), *Path(item).parents) for item in roots.values()):
        raise QualificationRefused("environment root escapes the evidence generation")
    uv = environment["productOwnedUv"]
    if type(uv) is not dict or set(uv) != PRODUCT_UV_KEYS or not all(type(k) is str and type(v) is str for k, v in uv.items()):
        raise QualificationRefused("product-owned uv map differs")
    seeded = environment["seededAmbientKeys"]
    if type(seeded) is not list or not seeded or len(seeded) != len(set(seeded)) or not all(type(k) is str and k for k in seeded):
        raise QualificationRefused("seeded ambient keys are invalid")
    proxy = _closed(environment["proxy"], {"admittedHosts", "values"}, "proxy")
    if tuple(proxy["admittedHosts"]) != ADMITTED_BOOTSTRAP_HOSTS:
        raise QualificationRefused("proxy host allowlist differs")
    proxy_values = proxy["values"]
    if type(proxy_values) is not dict or set(proxy_values) != {"ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"}:
        raise QualificationRefused("proxy environment differs")
    final = environment["expectedFinal"]
    if type(final) is not dict or not final or not all(type(k) is str and k and type(v) is str for k, v in final.items()):
        raise QualificationRefused("final child environment is invalid")
    if _hash(environment["expectedFinalSha256"], "final child environment") != sha256_bytes(canonical_json_bytes(final)):
        raise QualificationRefused("final child environment hash differs")
    final_uv = {key: item for key, item in final.items() if key.upper().startswith("UV_")}
    if final_uv != uv or final.get("PYTHONDONTWRITEBYTECODE") != "1":
        raise QualificationRefused("final product-owned environment differs")
    if any(key.upper() == "PI_OFFLINE" for key in final):
        raise QualificationRefused("final environment retains PI_OFFLINE")
    expected_root_environment = {
        "APPDATA": roots["appData"],
        "HOME": roots["home"],
        "LOCALAPPDATA": roots["localAppData"],
        "PRIME_AGENT_CODING_AGENT_DIR": roots["primeAgentDir"],
        "ROOK_DATA_DIR": roots["rookDataDir"],
        "TEMP": roots["temp"],
        "TMP": roots["temp"],
        "USERPROFILE": roots["userProfile"],
    }
    if any(final.get(key) != item for key, item in expected_root_environment.items()):
        raise QualificationRefused("final isolated roots differ")
    if any(final.get(key) != item for key, item in proxy_values.items()):
        raise QualificationRefused("final proxy environment differs")

    network = _closed(value["network"], {"daemonSocket", "providerUrl", "proxyUrl"}, "network")
    if not all(type(network[key]) is str and network[key] for key in network):
        raise QualificationRefused("network identity is invalid")
    if network["proxyUrl"] != proxy_values["HTTP_PROXY"]:
        raise QualificationRefused("proxy URL differs")
    if launch["qualificationOnlyArguments"] != ["--offline", "--daemon-socket", network["daemonSocket"]]:
        raise QualificationRefused("qualification-only arguments differ")

    kernel = _closed(
        value["kernel"],
        {
            "pythonPath",
            "runtimeSourceManifestSha256",
            "runtimeSourcePath",
            "uvCachePath",
            "uvPythonInstallPath",
            "venvPath",
        },
        "kernel",
    )
    _hash(kernel["runtimeSourceManifestSha256"], "kernel runtime source manifest")
    for key, item in kernel.items():
        if key == "runtimeSourceManifestSha256":
            continue
        _absolute_path(item, key)
    expected_venv = Path(roots["userProfile"]) / ".prime/agent/kernel-venv"
    expected_python = expected_venv / "Scripts/python.exe"
    expected_runtime_source = install_root / "runtimes" / runtime_id / "dist/prime-agent-runtime"
    if (
        Path(kernel["venvPath"]) != expected_venv
        or Path(kernel["pythonPath"]) != expected_python
        or Path(kernel["runtimeSourcePath"]) != expected_runtime_source
        or kernel["uvCachePath"] != uv["UV_CACHE_DIR"]
        or kernel["uvPythonInstallPath"] != uv["UV_PYTHON_INSTALL_DIR"]
    ):
        raise QualificationRefused("cold-kernel paths differ")

    source_inputs = value["sourceInputs"]
    if type(source_inputs) is not list or not source_inputs:
        raise QualificationRefused("source inputs are missing")
    paths: list[str] = []
    for item in source_inputs:
        row = _closed(item, {"path", "sha256"}, "source input")
        paths.append(_relative_path(row["path"], "source input").as_posix())
        _hash(row["sha256"], "source input")
    if paths != sorted(set(paths)):
        raise QualificationRefused("source inputs are not a unique ordered list")
    return value


def load_precontact_protocol(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_PROTOCOL_BYTES + 1)
    except OSError as exc:
        raise QualificationRefused("protocol is unavailable") from exc
    if len(data) > MAX_PROTOCOL_BYTES:
        raise QualificationRefused("protocol exceeds byte limit")
    try:
        value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=_unique_object)
    except QualificationRefused:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise QualificationRefused("protocol JSON is invalid") from exc
    validate_precontact_protocol(value)
    if canonical_json_bytes(value) != data:
        raise QualificationRefused("protocol is not canonical")
    return value


def _resolved_child(root: Path, relative: str) -> Path:
    base = root.resolve(strict=True)
    candidate = (base / Path(relative)).resolve(strict=True)
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise QualificationRefused("source input escapes the worktree") from exc
    return candidate


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            shell=False,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise QualificationRefused("source Git custody failed") from exc
    if check and result.returncode != 0:
        raise QualificationRefused("source Git custody failed")
    return result


def verify_source_custody(repo_root: Path, implementation_commit: str) -> None:
    root = repo_root.resolve(strict=True)
    if COMMIT_PATTERN.fullmatch(implementation_commit) is None:
        raise QualificationRefused("implementation commit is invalid")
    if _git(root, "status", "--porcelain").stdout:
        raise QualificationRefused("source worktree is not clean")
    if _git(root, "merge-base", "--is-ancestor", implementation_commit, "HEAD", check=False).returncode != 0:
        raise QualificationRefused("implementation commit is not an ancestor")
    changed = _git(root, "diff", "--name-only", implementation_commit, "HEAD", "--", *PRODUCT_SOURCE_PATHS).stdout
    if changed.strip():
        raise QualificationRefused("product source differs from implementation commit")


def assert_no_product_qualification_imports(repo_root: Path) -> None:
    product = repo_root.resolve(strict=True) / "mcp_server/src/rook"
    if not product.is_dir():
        return
    for path in sorted(product.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="strict"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise QualificationRefused(f"cannot inspect product import: {path}") from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(name == "scripts.qualification" or name.startswith("scripts.qualification.") for name in names):
                raise QualificationRefused(f"product import reaches qualification code: {path}")


def admit_precontact_protocol(path: Path, repo_root: Path, *, verify_git: bool = True) -> dict[str, Any]:
    protocol = load_precontact_protocol(path)
    root = repo_root.resolve(strict=True)
    evidence = Path(protocol["evidenceRoot"])
    if evidence.exists() or evidence.is_symlink():
        raise QualificationRefused("evidence root already exists")
    if verify_git:
        verify_source_custody(root, protocol["implementationCommit"])
    assert_no_product_qualification_imports(root)
    for row in protocol["sourceInputs"]:
        source = _resolved_child(root, row["path"])
        if not source.is_file() or source.is_symlink() or sha256_file(source) != row["sha256"]:
            raise QualificationRefused(f"source input differs: {row['path']}")

    runtime = protocol["runtime"]
    manifest_path = Path(runtime["manifestPath"])
    if not manifest_path.is_file() or manifest_path.is_symlink() or sha256_file(manifest_path) != runtime["manifestSha256"]:
        raise QualificationRefused("runtime manifest differs")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QualificationRefused("runtime manifest is invalid") from exc
    if type(manifest) is not dict or manifest.get("rookSkillManifestSha256") != runtime["rookSkillManifestSha256"]:
        raise QualificationRefused("runtime skill identity differs")
    if manifest.get("acpProtocolVersion") != runtime["acpCompatibilityVersion"]:
        raise QualificationRefused("runtime ACP compatibility differs")
    python_runtime = manifest.get("pythonRuntime")
    if (
        type(python_runtime) is not dict
        or python_runtime.get("manifestSha256") != protocol["kernel"]["runtimeSourceManifestSha256"]
    ):
        raise QualificationRefused("runtime Python source identity differs")
    runtime_root = Path(runtime["installRoot"]) / "runtimes" / runtime["runtimeId"]
    executable = runtime_root / "pi.exe"
    if not executable.is_file() or executable.is_symlink() or sha256_file(executable) != runtime["primeExecutableSha256"]:
        raise QualificationRefused("Prime executable differs")
    return protocol


class EvidenceRoot:
    def __init__(self, root: Path, max_file_bytes: int) -> None:
        self.root = root
        self.max_file_bytes = max_file_bytes
        self._sealed = False

    @classmethod
    def create(cls, root: Path, *, max_file_bytes: int) -> "EvidenceRoot":
        if not root.is_absolute() or max_file_bytes <= 0:
            raise QualificationRefused("evidence root arguments are invalid")
        root.parent.mkdir(parents=True, exist_ok=True)
        try:
            root.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise QualificationRefused("evidence root already exists") from exc
        return cls(root, max_file_bytes)

    def _target(self, relative: str) -> Path:
        if self._sealed:
            raise QualificationRefused("evidence root is sealed")
        path = _relative_path(relative, "evidence")
        target = self.root.joinpath(*path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        resolved_parent = target.parent.resolve(strict=True)
        if self.root.resolve(strict=True) not in (resolved_parent, *resolved_parent.parents):
            raise QualificationRefused("evidence path escapes root")
        return target

    def write_bytes(self, relative: str, data: bytes) -> Path:
        if type(data) is not bytes or len(data) > self.max_file_bytes:
            raise QualificationRefused("evidence byte limit exceeded")
        target = self._target(relative)
        try:
            with target.open("xb") as stream:
                stream.write(data)
        except FileExistsError as exc:
            raise QualificationRefused("evidence file already exists") from exc
        return target

    def write_json(self, relative: str, value: object) -> Path:
        return self.write_bytes(relative, canonical_json_bytes(value))

    def seal(self) -> Path:
        if self._sealed:
            raise QualificationRefused("evidence root is sealed")
        rows = []
        for path in sorted(item for item in self.root.rglob("*") if item.is_file()):
            relative = path.relative_to(self.root).as_posix()
            rows.append({"bytes": path.stat().st_size, "path": relative, "sha256": sha256_file(path)})
        index = self.write_json("evidence-index.json", {"files": rows})
        self.write_bytes("SEALED", b"sealed\n")
        self._sealed = True
        for path in sorted(self.root.rglob("*"), reverse=True):
            mode = stat.S_IREAD | (stat.S_IEXEC if path.is_dir() else 0)
            with contextlib.suppress(OSError):
                path.chmod(mode)
        with contextlib.suppress(OSError):
            self.root.chmod(stat.S_IREAD | stat.S_IEXEC)
        return index


@dataclass(frozen=True)
class ProcessSpec:
    argv: tuple[str, ...]
    cwd: Path
    environment: dict[str, str]
    timeout_seconds: float
    close_seconds: float
    max_output_bytes: int


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    output_overflow: bool
    direct_child_exit_observed: bool


async def _stop_direct_process(process: asyncio.subprocess.Process, close_seconds: float) -> bool:
    if process.returncode is not None:
        await process.wait()
        return True
    try:
        process.terminate()
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(process.wait(), timeout=close_seconds)
        return True
    except asyncio.TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.wait(), timeout=close_seconds)
            return True
        except asyncio.TimeoutError:
            return False


async def run_bounded_process(spec: ProcessSpec) -> ProcessResult:
    if (
        not spec.argv
        or any(type(item) is not str or not item or "\0" in item for item in spec.argv)
        or not spec.cwd.is_dir()
        or spec.timeout_seconds <= 0
        or spec.close_seconds <= 0
        or spec.max_output_bytes <= 0
    ):
        raise QualificationRefused("process specification is invalid")
    process = await asyncio.create_subprocess_exec(
        *spec.argv,
        cwd=spec.cwd,
        env=spec.environment,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if process.stdout is None or process.stderr is None:
        await _stop_direct_process(process, spec.close_seconds)
        raise QualificationRefused("qualification process pipes are unavailable")
    stdout = bytearray()
    stderr = bytearray()
    total = 0
    overflow = asyncio.Event()
    lock = asyncio.Lock()

    async def drain(stream: asyncio.StreamReader, target: bytearray) -> None:
        nonlocal total
        while chunk := await stream.read(8192):
            async with lock:
                remaining = max(0, spec.max_output_bytes - total)
                target.extend(chunk[:remaining])
                total += min(len(chunk), remaining)
                if len(chunk) > remaining:
                    overflow.set()

    readers = (asyncio.create_task(drain(process.stdout, stdout)), asyncio.create_task(drain(process.stderr, stderr)))
    wait_task = asyncio.create_task(process.wait())
    overflow_task = asyncio.create_task(overflow.wait())
    timed_out = False
    try:
        done, _ = await asyncio.wait(
            {wait_task, overflow_task}, timeout=spec.timeout_seconds, return_when=asyncio.FIRST_COMPLETED
        )
        if not done:
            timed_out = True
        if timed_out or overflow.is_set():
            exit_observed = await _stop_direct_process(process, spec.close_seconds)
        else:
            await wait_task
            exit_observed = True
    finally:
        overflow_task.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
        if not wait_task.done():
            wait_task.cancel()
        await asyncio.gather(wait_task, overflow_task, return_exceptions=True)
    return ProcessResult(
        exit_code=process.returncode,
        stdout=bytes(stdout),
        stderr=bytes(stderr),
        timed_out=timed_out,
        output_overflow=overflow.is_set(),
        direct_child_exit_observed=exit_observed,
    )
