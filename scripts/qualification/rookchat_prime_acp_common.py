"""Finite, external custody helpers for RookChat Prime ACP qualification."""

from __future__ import annotations

import ast
import asyncio
import contextlib
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
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
QUALIFICATION_PROTOCOL_NAME = re.compile(r"rookchat-prime-acp-precontact-v([1-9][0-9]*)\.json")
QUALIFICATION_MODULES = {
    "scripts.qualification.rookchat_prime_acp_common": "scripts/qualification/rookchat_prime_acp_common.py",
    "scripts.qualification.rookchat_prime_acp_precontact": "scripts/qualification/rookchat_prime_acp_precontact.py",
    "scripts.qualification.fixtures.deterministic_provider": "scripts/qualification/fixtures/deterministic_provider.py",
}


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
            "executionRoot",
            "qualificationConversationId",
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
    execution_root = _absolute_path(value["executionRoot"], "execution root").resolve(strict=False)
    evidence_root = Path(value["evidenceRoot"]).resolve(strict=False)
    if execution_root.is_relative_to(evidence_root) or evidence_root.is_relative_to(execution_root):
        raise QualificationRefused("execution and evidence roots overlap")
    conversation_id = value["qualificationConversationId"]
    if type(conversation_id) is not str or re.fullmatch(r"[a-f0-9]{32}", conversation_id) is None:
        raise QualificationRefused("qualification conversation ID is invalid")
    if value["evaluator"] is not None:
        raise QualificationRefused("pre-contact evaluator must be null")

    limits = _closed(
        value["limits"],
        {
            "maxEvidenceFileBytes",
            "maxEvidenceTotalBytes",
            "maxEvidenceFiles",
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
    if launch["productionForbiddenArguments"] != ["--offline"]:
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
    if any(not Path(item).resolve(strict=False).is_relative_to(execution_root)
           or Path(item).resolve(strict=False) == execution_root for item in roots.values()):
        raise QualificationRefused("environment root escapes the execution generation")
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


async def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("git")
    if executable is None:
        raise QualificationRefused("source Git custody executable is unavailable")
    argv = (str(Path(executable).resolve(strict=True)), "-C", str(repo), *args)
    environment = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    try:
        captured = await run_bounded_process(ProcessSpec(argv, repo, environment, 10, 30, 1_048_576))
        if captured.timed_out or captured.output_overflow or not captured.direct_child_exit_observed:
            raise QualificationRefused("source Git custody process did not complete")
        result = subprocess.CompletedProcess(argv, captured.exit_code,
            captured.stdout.decode("utf-8", "strict"), captured.stderr.decode("utf-8", "strict"))
    except (OSError, UnicodeError) as exc:
        raise QualificationRefused("source Git custody failed") from exc
    if check and result.returncode != 0:
        raise QualificationRefused("source Git custody failed")
    return result


async def verify_source_custody(repo_root: Path, implementation_commit: str) -> None:
    root = repo_root.resolve(strict=True)
    if COMMIT_PATTERN.fullmatch(implementation_commit) is None:
        raise QualificationRefused("implementation commit is invalid")
    if (await _git(root, "status", "--porcelain")).stdout:
        raise QualificationRefused("source worktree is not clean")
    if (await _git(root, "merge-base", "--is-ancestor", implementation_commit, "HEAD", check=False)).returncode != 0:
        raise QualificationRefused("implementation commit is not an ancestor")
    changed = (await _git(root, "diff", "--name-only", implementation_commit, "HEAD", "--", *PRODUCT_SOURCE_PATHS)).stdout
    if changed.strip():
        raise QualificationRefused("product source differs from implementation commit")


def _qualification_protocol_identity(root: Path, protocol_path: Path) -> tuple[str, str]:
    candidate = protocol_path.absolute()
    match = QUALIFICATION_PROTOCOL_NAME.fullmatch(candidate.name)
    if (".." in protocol_path.parts or match is None
            or candidate.parent != root / "scripts/qualification/protocols"):
        raise QualificationRefused("qualification protocol path differs")
    try:
        # Check the file and each repository-local ancestor without following links.
        for path in (candidate, *candidate.parents):
            info = path.lstat()
            if (stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                    or not (stat.S_ISREG(info.st_mode) if path == candidate else stat.S_ISDIR(info.st_mode))):
                raise QualificationRefused("qualification protocol origin differs")
            if path == root:
                break
        if candidate.resolve(strict=True) != candidate:
            raise QualificationRefused("qualification protocol origin differs")
    except (OSError, ValueError) as exc:
        raise QualificationRefused("qualification protocol origin differs") from exc
    return candidate.relative_to(root).as_posix(), match.group(1)


async def verify_qualification_custody(repo_root: Path, protocol_path: Path, expected_commit: str | None) -> str:
    if type(expected_commit) is not str or COMMIT_PATTERN.fullmatch(expected_commit) is None:
        raise QualificationRefused("expected qualification commit is required")
    root = repo_root.resolve(strict=True)
    protocol_relative, version = _qualification_protocol_identity(root, protocol_path)
    if (await _git(root, "rev-parse", "HEAD")).stdout.strip() != expected_commit:
        raise QualificationRefused("qualification HEAD differs")
    if (await _git(root, "status", "--porcelain")).stdout:
        raise QualificationRefused("qualification worktree is not clean")
    for relative in (protocol_relative, *QUALIFICATION_MODULES.values()):
        path = root / relative
        if not path.is_file() or path.is_symlink() or path.resolve(strict=True) != path:
            raise QualificationRefused("qualification input origin differs")
        # Git hashes raw bytes here, with no checkout/eol filters.
        actual = (await _git(root, "hash-object", "--no-filters", str(path))).stdout.strip()
        expected = (await _git(root, "rev-parse", f"{expected_commit}:{relative}")).stdout.strip()
        if actual != expected:
            raise QualificationRefused("qualification blob bytes differ")
    from scripts.qualification.fixtures import deterministic_provider  # noqa: F401
    for name, relative in QUALIFICATION_MODULES.items():
        module = sys.modules.get(name)
        if module is None and name.endswith("rookchat_prime_acp_precontact"):
            module = sys.modules.get("__main__")
        if module is None or Path(module.__file__).resolve(strict=True) != root / relative:
            raise QualificationRefused("loaded qualification module origin differs")
    return version


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


async def admit_precontact_protocol(path: Path, repo_root: Path, *, verify_git: bool = True,
                              expected_qualification_commit: str | None = None) -> dict[str, Any]:
    if verify_git:
        version = await verify_qualification_custody(repo_root, path, expected_qualification_commit)
    protocol = load_precontact_protocol(path)
    if verify_git and version != str(protocol["executionVersion"]):
        raise QualificationRefused("qualification protocol filename/body version differs")
    root = repo_root.resolve(strict=True)
    evidence = Path(protocol["evidenceRoot"])
    if evidence.exists() or evidence.is_symlink():
        raise QualificationRefused("evidence root already exists")
    execution = Path(protocol["executionRoot"])
    if execution.exists() or execution.is_symlink():
        raise QualificationRefused("execution root already exists")
    for candidate in (execution.resolve(strict=False), evidence.resolve(strict=False)):
        for protected in (root, Path(protocol["runtime"]["installRoot"]).resolve(strict=True)):
            if candidate.is_relative_to(protected) or protected.is_relative_to(candidate):
                raise QualificationRefused("qualification root overlaps source or runtime")
    if verify_git:
        await verify_source_custody(root, protocol["implementationCommit"])
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
    def __init__(self, root: Path, max_file_bytes: int, max_total_bytes: int, max_files: int) -> None:
        self.root = root
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes
        self.max_files = max_files
        self._files: dict[str, dict[str, Any]] = {}
        self._reserved = {"result.json": min(max_file_bytes, 65536),
                          "evidence-index.json": min(max_file_bytes, 65536), "SEALED": 7}
        self._sealed = False

    @classmethod
    def create(cls, root: Path, *, max_file_bytes: int, max_total_bytes: int = 67108864,
               max_files: int = 64) -> "EvidenceRoot":
        if not root.is_absolute() or max_file_bytes < 7 or max_total_bytes <= 0 or max_files < 3:
            raise QualificationRefused("evidence root arguments are invalid")
        root.parent.mkdir(parents=True, exist_ok=True)
        try:
            root.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise QualificationRefused("evidence root already exists") from exc
        return cls(root, max_file_bytes, max_total_bytes, max_files)

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
        if type(data) is not bytes or len(data) > self._reserved.get(relative, self.max_file_bytes):
            raise QualificationRefused("evidence byte limit exceeded")
        if relative in self._files:
            raise QualificationRefused("evidence file already exists")
        remaining = {key: size for key, size in self._reserved.items() if key not in self._files and key != relative}
        if (len(self._files) + 1 + len(remaining) > self.max_files
                or sum(row["bytes"] for row in self._files.values()) + len(data) + sum(remaining.values()) > self.max_total_bytes):
            raise QualificationRefused("evidence count or total byte limit exceeded")
        target = self._target(relative)
        try:
            with target.open("xb") as stream:
                stream.write(data)
        except FileExistsError as exc:
            raise QualificationRefused("evidence file already exists") from exc
        self._files[relative] = {"bytes": len(data), "path": relative, "sha256": sha256_bytes(data)}
        return target

    def copy_file(self, relative: str, source: Path) -> Path:
        if source.is_symlink() or getattr(source.stat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise QualificationRefused("evidence source is a link")
        with source.open("rb") as stream:
            data = stream.read(self.max_file_bytes + 1)
        return self.write_bytes(relative, data)

    def write_json(self, relative: str, value: object) -> Path:
        return self.write_bytes(relative, canonical_json_bytes(value))

    def seal(self) -> Path:
        if self._sealed:
            raise QualificationRefused("evidence root is sealed")
        directories = {parent.as_posix() for name in self._files for parent in PurePosixPath(name).parents}
        for path in self.root.rglob("*"):
            relative = path.relative_to(self.root).as_posix()
            if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                raise QualificationRefused("unknown evidence link")
            if path.is_dir() and relative in directories:
                continue
            if relative not in self._files or not path.is_file():
                raise QualificationRefused("unknown evidence file or directory")
        rows = [self._files[name] for name in sorted(self._files)]
        for row in rows:
            with (self.root / row["path"]).open("rb") as stream:
                data = stream.read(self.max_file_bytes + 1)
            if len(data) != row["bytes"] or sha256_bytes(data) != row["sha256"]:
                raise QualificationRefused("retained evidence changed")
        index = self.write_json("evidence-index.json", {"files": rows})
        self.write_bytes("SEALED", b"sealed\n")
        self._sealed = True
        for path in [self.root / name for name in self._files]:
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
    deadline = asyncio.get_running_loop().time() + close_seconds
    if process.returncode is not None:
        await process.wait()
        return True
    try:
        process.terminate()
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(process.wait(), timeout=close_seconds / 2)
        return True
    except asyncio.TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.wait(), timeout=max(0, deadline - asyncio.get_running_loop().time()))
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
    exit_observed = False

    async def cleanup() -> None:
        nonlocal exit_observed
        deadline = asyncio.get_running_loop().time() + spec.close_seconds
        exit_observed = await _stop_direct_process(process, spec.close_seconds * .8)
        overflow_task.cancel()
        if not exit_observed:
            for reader in readers:
                reader.cancel()
        tasks = {*readers, wait_task, overflow_task}
        _, pending = await asyncio.wait(tasks, timeout=max(0, deadline - asyncio.get_running_loop().time()))
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.sleep(0)
        for task in tasks:
            if task.done() and not task.cancelled():
                task.exception()
        if any(not task.done() for task in tasks):
            raise QualificationRefused("qualification pipe cleanup remains uncertain")

    async def shield_cleanup() -> None:
        owned = asyncio.create_task(cleanup())
        interrupted = None
        while not owned.done():
            try:
                await asyncio.shield(owned)
            except asyncio.CancelledError as exc:
                interrupted = exc
                continue
        owned.result()
        if interrupted is not None:
            raise interrupted

    try:
        done, _ = await asyncio.wait(
            {wait_task, overflow_task}, timeout=spec.timeout_seconds, return_when=asyncio.FIRST_COMPLETED
        )
        if not done:
            timed_out = True
    except BaseException as exc:
        try:
            await shield_cleanup()
            if not exit_observed:
                exc.add_note("qualification child exit remains unobserved; retain workspace")
        except BaseException as cleanup_error:
            exc.add_note(f"qualification cleanup failed: {type(cleanup_error).__name__}")
        raise
    await shield_cleanup()
    return ProcessResult(
        exit_code=process.returncode,
        stdout=bytes(stdout),
        stderr=bytes(stderr),
        timed_out=timed_out,
        output_overflow=overflow.is_set(),
        direct_child_exit_observed=exit_observed,
    )
