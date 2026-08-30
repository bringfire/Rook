from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


class RuntimeContractError(ValueError):
    pass


_MANIFEST_NAME = "package-manifest.json"
_EXCLUDED_DIRECTORIES = frozenset({"__pycache__", ".pytest_cache", "build", "dist"})
_ROOT_KEYS = frozenset({"files", "schemaVersion"})
_FILE_KEYS = frozenset({"path", "sha256", "size"})
_PRIME_BUNDLE_SUBTREES = ("bundle", "skills")
_PRIME_BUNDLE_ROOT_KEYS = frozenset(
    {
        "entryCount",
        "entries",
        "manifestSha256",
        "schemaVersion",
        "subtrees",
        "totalBytes",
    }
)


@dataclass(frozen=True)
class VerifiedPackage:
    root: Path
    manifest: dict[str, Any]
    manifest_bytes: bytes
    manifest_sha256: str
    skill_sha256: str
    adapter_sha256: str
    project_metadata_sha256: str


@dataclass(frozen=True)
class VerifiedPrimeBundle:
    root: Path
    entries: dict[str, dict[str, int | str]]
    manifest_sha256: str
    entry_count: int
    total_bytes: int
    cli_path: Path


@dataclass(frozen=True)
class RuntimeContract:
    record: dict[str, Any]
    canonical_bytes: bytes
    fingerprint: str
    kernel_environment_path: Path
    goal_manifest_sha256: str
    rook_package: VerifiedPackage


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise RuntimeContractError(f"value is not canonical JSON: {exc}") from exc


def _iter_prime_bundle_files(root: Path) -> list[tuple[str, Path]]:
    resolved_root = _require_regular_package_root(root)
    files: list[tuple[str, Path]] = []

    def visit(directory: Path) -> None:
        try:
            children = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise RuntimeContractError(
                f"cannot enumerate Prime bundle directory {directory}: {exc}"
            ) from exc
        for child in children:
            path = Path(child.path)
            relative = path.relative_to(root).as_posix()
            if _is_reparse_point(path):
                raise RuntimeContractError(
                    f"Prime bundle contains a symlink or reparse point: {relative}"
                )
            if child.is_dir(follow_symlinks=False):
                visit(path)
                continue
            if not child.is_file(follow_symlinks=False):
                raise RuntimeContractError(
                    f"Prime bundle contains a non-regular file: {relative}"
                )
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(resolved_root)
            except (OSError, ValueError) as exc:
                raise RuntimeContractError(
                    f"Prime bundle entry escapes its root: {relative}"
                ) from exc
            files.append((_validate_relative_path(relative), path))

    for subtree_name in _PRIME_BUNDLE_SUBTREES:
        subtree = root / subtree_name
        if not subtree.is_dir() or _is_reparse_point(subtree):
            raise RuntimeContractError(
                f"Prime bundle subtree is missing or unsafe: {subtree_name}"
            )
        visit(subtree)

    files.sort(key=lambda item: item[0])
    folded: set[str] = set()
    for relative, _path in files:
        normalized = relative.casefold()
        if normalized in folded:
            raise RuntimeContractError(
                f"duplicate normalized Prime bundle path: {relative}"
            )
        folded.add(normalized)
    return files


def build_prime_bundle_manifest(root: Path) -> VerifiedPrimeBundle:
    root = Path(root)
    entries: dict[str, dict[str, int | str]] = {}
    total_bytes = 0
    for relative, path in _iter_prime_bundle_files(root):
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise RuntimeContractError(
                f"cannot read Prime bundle file {relative}: {exc}"
            ) from exc
        entries[relative] = {"bytes": len(raw), "sha256": _sha256_bytes(raw)}
        total_bytes += len(raw)

    if "bundle/cli.js" not in entries:
        raise RuntimeContractError("Prime bundle requires bundle/cli.js")
    manifest_sha256 = _sha256_bytes(canonical_json_bytes(entries))
    resolved_root = root.resolve(strict=True)
    return VerifiedPrimeBundle(
        root=resolved_root,
        entries=entries,
        manifest_sha256=manifest_sha256,
        entry_count=len(entries),
        total_bytes=total_bytes,
        cli_path=(resolved_root / "bundle" / "cli.js"),
    )


def _prime_bundle_descriptor(bundle: VerifiedPrimeBundle) -> dict[str, Any]:
    return {
        "entryCount": bundle.entry_count,
        "entries": bundle.entries,
        "manifestSha256": bundle.manifest_sha256,
        "schemaVersion": 1,
        "subtrees": list(_PRIME_BUNDLE_SUBTREES),
        "totalBytes": bundle.total_bytes,
    }


def write_prime_bundle_manifest(root: Path, manifest_path: Path) -> VerifiedPrimeBundle:
    bundle = build_prime_bundle_manifest(Path(root))
    manifest_path = Path(manifest_path)
    try:
        manifest_path.resolve(strict=False).relative_to(bundle.root)
    except ValueError:
        pass
    else:
        raise RuntimeContractError("Prime bundle manifest must be external to the dist root")

    raw = canonical_json_bytes(_prime_bundle_descriptor(bundle))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    pending = manifest_path.parent / f".{manifest_path.name}.{uuid.uuid4().hex}.pending"
    try:
        with pending.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, manifest_path)
    finally:
        pending.unlink(missing_ok=True)
    return bundle


def verify_prime_bundle_manifest(
    root: Path,
    manifest_path: Path,
    *,
    expected_manifest_sha256: str,
) -> VerifiedPrimeBundle:
    expected_manifest_sha256 = _require_upper_sha256(
        expected_manifest_sha256,
        "Prime bundle manifest",
    )
    manifest_path = Path(manifest_path)
    if not manifest_path.is_file() or _is_reparse_point(manifest_path):
        raise RuntimeContractError("Prime bundle manifest is missing or unsafe")
    raw = manifest_path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or raw.endswith((b"\n", b"\r")):
        raise RuntimeContractError("Prime bundle manifest has a BOM or trailing newline")
    try:
        parsed = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_no_duplicate_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeContractError(
            f"Prime bundle manifest is not strict UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(parsed, dict) or set(parsed) != _PRIME_BUNDLE_ROOT_KEYS:
        raise RuntimeContractError("Prime bundle manifest root schema is invalid")
    if canonical_json_bytes(parsed) != raw:
        raise RuntimeContractError("Prime bundle manifest bytes are not canonical")

    actual = build_prime_bundle_manifest(Path(root))
    expected = _prime_bundle_descriptor(actual)
    if parsed != expected:
        raise RuntimeContractError("Prime bundle manifest does not match present bytes")
    if actual.manifest_sha256 != expected_manifest_sha256:
        raise RuntimeContractError("Prime bundle manifest SHA-256 does not match admitted identity")
    return actual


def _is_reparse_point(path: Path) -> bool:
    try:
        value = path.lstat()
    except OSError as exc:
        raise RuntimeContractError(f"cannot inspect package path {path}: {exc}") from exc
    attributes = getattr(value, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _require_regular_package_root(root: Path) -> Path:
    if not root.is_absolute():
        raise RuntimeContractError("package root must be absolute")
    if not root.exists() or not root.is_dir():
        raise RuntimeContractError("package root must be an existing directory")
    if _is_reparse_point(root):
        raise RuntimeContractError("package root must not be a symlink or reparse point")
    return root.resolve(strict=True)


def _validate_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise RuntimeContractError("manifest path must be a nonempty forward-slash string")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts) or path.as_posix() != value:
        raise RuntimeContractError("manifest path is not canonical and relative")
    return value


def _iter_authority_files(root: Path) -> list[tuple[str, Path]]:
    resolved_root = _require_regular_package_root(root)
    files: list[tuple[str, Path]] = []

    def visit(directory: Path) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise RuntimeContractError(f"cannot enumerate package directory {directory}: {exc}") from exc
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            if entry.name in _EXCLUDED_DIRECTORIES and entry.is_dir(follow_symlinks=False):
                continue
            if relative == _MANIFEST_NAME or entry.name.endswith(".pyc"):
                continue
            if _is_reparse_point(path):
                raise RuntimeContractError(f"package authority contains a symlink or reparse point: {relative}")
            if entry.is_dir(follow_symlinks=False):
                visit(path)
                continue
            if not entry.is_file(follow_symlinks=False):
                raise RuntimeContractError(f"package authority contains a non-regular file: {relative}")
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(resolved_root)
            except (OSError, ValueError) as exc:
                raise RuntimeContractError(f"package authority escapes its root: {relative}") from exc
            files.append((_validate_relative_path(relative), path))

    visit(root)
    files.sort(key=lambda item: item[0])
    folded: set[str] = set()
    for relative, _path in files:
        normalized = relative.casefold()
        if normalized in folded:
            raise RuntimeContractError(f"duplicate normalized package path: {relative}")
        folded.add(normalized)
    return files


def build_package_manifest(root: Path) -> dict[str, Any]:
    root = Path(root)
    members: list[dict[str, object]] = []
    for relative, path in _iter_authority_files(root):
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise RuntimeContractError(f"cannot read package file {relative}: {exc}") from exc
        members.append({"path": relative, "sha256": _sha256_bytes(raw), "size": len(raw)})
    return {"files": members, "schemaVersion": 1}


def _no_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_manifest_bytes(raw: bytes) -> dict[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf") or raw.endswith((b"\n", b"\r")):
        raise RuntimeContractError("package manifest has a BOM or trailing newline")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=_no_duplicate_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeContractError(f"package manifest is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeContractError("package manifest root must be an object")
    if canonical_json_bytes(value) != raw:
        raise RuntimeContractError("package manifest bytes are not canonical")
    _validate_manifest_value(value)
    return value


def _validate_manifest_value(value: dict[str, Any]) -> None:
    if set(value) != _ROOT_KEYS or type(value.get("schemaVersion")) is not int or value["schemaVersion"] != 1:
        raise RuntimeContractError("package manifest root schema is invalid")
    files = value.get("files")
    if not isinstance(files, list):
        raise RuntimeContractError("package manifest files must be an array")
    paths: list[str] = []
    folded: set[str] = set()
    for member in files:
        if not isinstance(member, dict) or set(member) != _FILE_KEYS:
            raise RuntimeContractError("package manifest member schema is invalid")
        path = _validate_relative_path(member.get("path"))
        digest = member.get("sha256")
        size = member.get("size")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789ABCDEF" for character in digest)
        ):
            raise RuntimeContractError("package manifest hash is invalid")
        if type(size) is not int or size < 0:
            raise RuntimeContractError("package manifest size is invalid")
        normalized = path.casefold()
        if normalized in folded:
            raise RuntimeContractError(f"duplicate normalized package path: {path}")
        folded.add(normalized)
        paths.append(path)
    if paths != sorted(paths):
        raise RuntimeContractError("package manifest paths are not sorted ordinally")


def _diagnostic_hash(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file() or _is_reparse_point(path):
        raise RuntimeContractError(f"required package file is missing or unsafe: {relative}")
    return _sha256_bytes(path.read_bytes())


def verify_package(root: Path, *, expected_manifest_sha256: str | None = None) -> VerifiedPackage:
    root = Path(root)
    _require_regular_package_root(root)
    manifest_path = root / _MANIFEST_NAME
    if not manifest_path.is_file() or _is_reparse_point(manifest_path):
        raise RuntimeContractError("package manifest is missing or unsafe")
    raw = manifest_path.read_bytes()
    digest = _sha256_bytes(raw)
    if expected_manifest_sha256 is not None and digest != expected_manifest_sha256:
        raise RuntimeContractError("package manifest SHA-256 does not match the admitted identity")
    manifest = _parse_manifest_bytes(raw)
    actual = build_package_manifest(root)
    if canonical_json_bytes(actual) != raw:
        raise RuntimeContractError("package manifest does not match present package files")
    return VerifiedPackage(
        root=root.resolve(strict=True),
        manifest=manifest,
        manifest_bytes=raw,
        manifest_sha256=digest,
        skill_sha256=_diagnostic_hash(root, "SKILL.md"),
        adapter_sha256=_diagnostic_hash(root, "src/rook_full/__init__.py"),
        project_metadata_sha256=_diagnostic_hash(root, "pyproject.toml"),
    )


def write_package_manifest(root: Path) -> VerifiedPackage:
    root = Path(root)
    _require_regular_package_root(root)
    raw = canonical_json_bytes(build_package_manifest(root))
    pending = root / f".{_MANIFEST_NAME}.{uuid.uuid4().hex}.pending"
    try:
        with pending.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, root / _MANIFEST_NAME)
    finally:
        pending.unlink(missing_ok=True)
    return verify_package(root, expected_manifest_sha256=_sha256_bytes(raw))


def _require_upper_sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789ABCDEF" for character in value)
    ):
        raise RuntimeContractError(f"{label} must be an uppercase SHA-256")
    return value


def _require_absolute_root(path: Path, label: str, *, create: bool) -> Path:
    path = Path(path)
    if not path.is_absolute():
        raise RuntimeContractError(f"{label} must be absolute")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_dir() or _is_reparse_point(path):
            raise RuntimeContractError(f"{label} must be a non-reparse directory")
        return path.resolve(strict=True)
    return path.resolve(strict=False)


def _write_closed_file(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def stage_product_package(source_root: Path, *, product_root: Path) -> VerifiedPackage:
    source_root = Path(source_root)
    source_manifest = build_package_manifest(source_root)
    manifest_bytes = canonical_json_bytes(source_manifest)
    manifest_sha256 = _sha256_bytes(manifest_bytes)
    admitted_root = _require_absolute_root(Path(product_root), "product root", create=True)
    contract_root = admitted_root / manifest_sha256
    final_root = contract_root / "rook-full"

    if final_root.exists():
        return verify_package(final_root, expected_manifest_sha256=manifest_sha256)

    pending_contract = admitted_root / f".{manifest_sha256}.{uuid.uuid4().hex}.pending"
    pending_package = pending_contract / "rook-full"
    try:
        pending_package.mkdir(parents=True, exist_ok=False)
        for member in source_manifest["files"]:
            relative = _validate_relative_path(member["path"])
            source = source_root / Path(*PurePosixPath(relative).parts)
            destination = pending_package / Path(*PurePosixPath(relative).parts)
            _write_closed_file(destination, source.read_bytes())
        _write_closed_file(pending_package / _MANIFEST_NAME, manifest_bytes)
        verify_package(pending_package, expected_manifest_sha256=manifest_sha256)

        try:
            os.rename(pending_contract, contract_root)
        except OSError:
            if not final_root.exists():
                raise
        return verify_package(final_root, expected_manifest_sha256=manifest_sha256)
    finally:
        if pending_contract.exists():
            shutil.rmtree(pending_contract, ignore_errors=True)


_RUNTIME_ROOT_KEYS = frozenset(
    {
        "capabilityProfile",
        "goalSkill",
        "prime",
        "rlmMaxDepth",
        "rookPackage",
        "runtimeCompatibilityVersion",
        "schemaVersion",
    }
)
_RUNTIME_PRIME_KEYS = frozenset({"bundleManifestSha256", "gitCommitProvenance"})
_RUNTIME_GOAL_KEYS = frozenset({"manifestSha256", "pathIdentity"})
_RUNTIME_ROOK_KEYS = frozenset(
    {"adapterSha256", "packageManifestSha256", "projectMetadataSha256", "skillSha256"}
)


def _validate_runtime_record(record: object) -> dict[str, Any]:
    if not isinstance(record, dict) or set(record) != _RUNTIME_ROOT_KEYS:
        raise RuntimeContractError("runtime contract root schema is invalid")
    if type(record.get("schemaVersion")) is not int or record["schemaVersion"] != 1:
        raise RuntimeContractError("runtime contract schemaVersion is invalid")
    if (
        type(record.get("runtimeCompatibilityVersion")) is not int
        or record["runtimeCompatibilityVersion"] != 1
    ):
        raise RuntimeContractError("runtime compatibility version is invalid")
    if record.get("capabilityProfile") not in {"readonly", "full"}:
        raise RuntimeContractError("runtime capability profile is invalid")
    if type(record.get("rlmMaxDepth")) is not int or record["rlmMaxDepth"] != 0:
        raise RuntimeContractError("runtime RLM max depth is invalid")

    prime = record.get("prime")
    goal = record.get("goalSkill")
    rook = record.get("rookPackage")
    if not isinstance(prime, dict) or set(prime) != _RUNTIME_PRIME_KEYS:
        raise RuntimeContractError("runtime Prime schema is invalid")
    if not isinstance(goal, dict) or set(goal) != _RUNTIME_GOAL_KEYS:
        raise RuntimeContractError("runtime goal-skill schema is invalid")
    if not isinstance(rook, dict) or set(rook) != _RUNTIME_ROOK_KEYS:
        raise RuntimeContractError("runtime Rook-package schema is invalid")

    _require_upper_sha256(prime.get("bundleManifestSha256"), "Prime bundle manifest")
    if not isinstance(prime.get("gitCommitProvenance"), str) or not prime["gitCommitProvenance"]:
        raise RuntimeContractError("Prime git provenance must be nonempty")
    _require_upper_sha256(goal.get("manifestSha256"), "goal-skill manifest")
    if not isinstance(goal.get("pathIdentity"), str) or not goal["pathIdentity"]:
        raise RuntimeContractError("goal-skill path identity must be nonempty")
    for key in _RUNTIME_ROOK_KEYS:
        _require_upper_sha256(rook.get(key), f"Rook package {key}")
    return record


def parse_runtime_contract_bytes(raw: bytes) -> dict[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf") or raw.endswith((b"\n", b"\r")):
        raise RuntimeContractError("runtime contract has a BOM or trailing newline")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=_no_duplicate_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeContractError(f"runtime contract is not strict UTF-8 JSON: {exc}") from exc
    record = _validate_runtime_record(value)
    if canonical_json_bytes(record) != raw:
        raise RuntimeContractError("runtime contract bytes are not canonical")
    return record


def build_runtime_contract(
    *,
    prime_bundle_manifest_sha256: str,
    prime_git_commit_provenance: str,
    goal_skill_root: Path,
    goal_skill_path_identity: str,
    rook_package: VerifiedPackage,
    capability_profile: str,
    kernel_root: Path,
    runtime_compatibility_version: int,
) -> RuntimeContract:
    _require_upper_sha256(prime_bundle_manifest_sha256, "Prime bundle manifest")
    if not isinstance(prime_git_commit_provenance, str) or not prime_git_commit_provenance:
        raise RuntimeContractError("Prime git provenance must be nonempty")
    if not isinstance(goal_skill_path_identity, str) or not goal_skill_path_identity:
        raise RuntimeContractError("goal-skill path identity must be nonempty")
    if capability_profile not in {"readonly", "full"}:
        raise RuntimeContractError("runtime capability profile is invalid")
    if type(runtime_compatibility_version) is not int or runtime_compatibility_version != 1:
        raise RuntimeContractError("runtime compatibility version is invalid")

    verified_rook = verify_package(
        rook_package.root,
        expected_manifest_sha256=rook_package.manifest_sha256,
    )
    goal_manifest_bytes = canonical_json_bytes(build_package_manifest(Path(goal_skill_root)))
    goal_manifest_sha256 = _sha256_bytes(goal_manifest_bytes)
    record: dict[str, Any] = {
        "capabilityProfile": capability_profile,
        "goalSkill": {
            "manifestSha256": goal_manifest_sha256,
            "pathIdentity": goal_skill_path_identity,
        },
        "prime": {
            "bundleManifestSha256": prime_bundle_manifest_sha256,
            "gitCommitProvenance": prime_git_commit_provenance,
        },
        "rlmMaxDepth": 0,
        "rookPackage": {
            "adapterSha256": verified_rook.adapter_sha256,
            "packageManifestSha256": verified_rook.manifest_sha256,
            "projectMetadataSha256": verified_rook.project_metadata_sha256,
            "skillSha256": verified_rook.skill_sha256,
        },
        "runtimeCompatibilityVersion": runtime_compatibility_version,
        "schemaVersion": 1,
    }
    _validate_runtime_record(record)
    raw = canonical_json_bytes(record)
    fingerprint = _sha256_bytes(raw)
    admitted_kernel_root = _require_absolute_root(Path(kernel_root), "kernel root", create=False)
    return RuntimeContract(
        record=record,
        canonical_bytes=raw,
        fingerprint=fingerprint,
        kernel_environment_path=admitted_kernel_root / fingerprint,
        goal_manifest_sha256=goal_manifest_sha256,
        rook_package=verified_rook,
    )


def verify_runtime_contract(
    contract: RuntimeContract,
    *,
    product_root: Path,
    goal_skill_root: Path,
    kernel_root: Path,
) -> RuntimeContract:
    record = _validate_runtime_record(contract.record)
    raw = canonical_json_bytes(record)
    if raw != contract.canonical_bytes or _sha256_bytes(raw) != contract.fingerprint:
        raise RuntimeContractError("runtime contract bytes or fingerprint drifted")

    admitted_product_root = _require_absolute_root(Path(product_root), "product root", create=False)
    package_root = contract.rook_package.root.resolve(strict=True)
    try:
        relative_package = package_root.relative_to(admitted_product_root)
    except ValueError as exc:
        raise RuntimeContractError("runtime package path escaped the installed product root") from exc
    if relative_package.parts != (contract.rook_package.manifest_sha256, "rook-full"):
        raise RuntimeContractError("runtime package path does not match its manifest identity")

    expected = build_runtime_contract(
        prime_bundle_manifest_sha256=record["prime"]["bundleManifestSha256"],
        prime_git_commit_provenance=record["prime"]["gitCommitProvenance"],
        goal_skill_root=goal_skill_root,
        goal_skill_path_identity=record["goalSkill"]["pathIdentity"],
        rook_package=contract.rook_package,
        capability_profile=record["capabilityProfile"],
        kernel_root=kernel_root,
        runtime_compatibility_version=record["runtimeCompatibilityVersion"],
    )
    if expected != contract:
        raise RuntimeContractError("runtime contract no longer matches its admitted sources")
    return contract
