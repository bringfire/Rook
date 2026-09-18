"""Closed Prime payload verification and Rook-owned runtime publication.

This module uses only the standard library. Incoming runtime code is data,
never part of verification or promotion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


UPSTREAM_COMMIT = "c718bf3c30fd8da206ed551837cbb54f7ad15948"
PRIME_COMMIT = "dacbeab26b705e7d07b55ae6f8cd3e95ceb5458b"
UV_SOURCE = "https://github.com/astral-sh/uv/releases/download/0.12.3/uv-x86_64-pc-windows-msvc.zip"
UV_ARCHIVE_SHA256 = "B23350C79E8AD0192B8124AF13A0F17E8D4E4549524785E1AEF389AE5A06990E"
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_ROOT_SKILL_UTF8_BYTES = 16 * 1024
MAX_FILE_ROWS = 100_000
ID_PATTERN = re.compile(r"[A-F0-9]{64}\Z")
COMMIT_PATTERN = re.compile(r"[a-f0-9]{40}\Z")
# Compatibility constraints are independent of the pins used for new assembly.
FIXED_FIELDS = {
    "schemaVersion": 1, "platform": "windows", "architecture": "amd64",
    "acpProtocolVersion": 1, "pythonAcpSdkVersion": "0.12.1", "executable": "pi.exe",
    "goalSkill": "skills/goal", "rookSkill": "skills/rook-full", "claimKeyVersion": 1,
}
UV = {
    "version": "0.12.3", "executable": "tools/uv/uv.exe", "source": UV_SOURCE,
    "sourceArchiveSha256": UV_ARCHIVE_SHA256,
    "licenses": ["tools/uv/LICENSE-APACHE", "tools/uv/LICENSE-MIT"],
}


class RuntimeUnavailable(RuntimeError):
    code = "runtime_unavailable"

    def __init__(self, detail: str):
        super().__init__(f"{self.code}: {detail}")


@dataclass(frozen=True)
class RuntimeManifestMetadata:
    acp_protocol_version: int
    python_acp_sdk_version: str
    rook_skill_manifest_sha256: str


@dataclass(frozen=True)
class VerifiedRuntimePayload:
    root: Path
    runtime_id: str
    manifest: Mapping[str, object]
    rook_skill_system_prompt: str


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8", "strict")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def safe_relative_path(value: object) -> str:
    if type(value) is not str or not value or "\\" in value or ":" in value:
        raise RuntimeUnavailable("manifest path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise RuntimeUnavailable("manifest path is not canonical")
    for part in path.parts:
        if (part in {".", ".."} or part.rstrip(" .") != part
                or any(ord(c) < 32 or c in '<>"|?*' for c in part)
                or re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])", part.split(".")[0])):
            raise RuntimeUnavailable("manifest path is invalid on Windows")
    try:
        value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise RuntimeUnavailable("manifest path contains invalid Unicode") from exc
    return value


def require_direct_path(path: Path, *, directory: bool = False) -> Path:
    path = Path(os.path.abspath(path))
    try:
        for item in (*reversed(path.parents), path):
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise RuntimeUnavailable("runtime path is linked or a reparse point")
        mode = path.stat().st_mode
        if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
            raise RuntimeUnavailable("runtime path has wrong file type")
    except OSError as exc:
        raise RuntimeUnavailable("runtime path is unavailable") from exc
    return path


def file_row(path: Path, relative: str) -> dict[str, object]:
    require_direct_path(path)
    digest = hashlib.sha256()
    length = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            length += len(block)
            digest.update(block)
    return {"path": safe_relative_path(relative), "bytes": length, "sha256": digest.hexdigest().upper()}


def payload_rows(root: Path) -> list[dict[str, object]]:
    root = require_direct_path(root, directory=True)
    rows = []
    seen: set[str] = set()
    for item in root.rglob("*"):
        relative = safe_relative_path(item.relative_to(root).as_posix())
        folded = relative.casefold()
        if folded in seen:
            raise RuntimeUnavailable("duplicate-normalized runtime path")
        seen.add(folded)
        require_direct_path(item, directory=item.is_dir())
        if item.is_dir() or relative == "runtime-manifest.json":
            continue
        rows.append(file_row(item, relative))
        if len(rows) > MAX_FILE_ROWS:
            raise RuntimeUnavailable("runtime file count exceeds limit")
    return sorted(rows, key=lambda row: row["path"])


def subtree_sha256(rows: Sequence[Mapping[str, object]], prefix: str) -> str:
    subtree = [{**row, "path": str(row["path"])[len(prefix):]} for row in rows if str(row["path"]).startswith(prefix)]
    if not subtree:
        raise RuntimeUnavailable("required runtime subtree is empty")
    return sha256_bytes(canonical_json_bytes({"files": subtree}))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeUnavailable("duplicate JSON key")
        result[key] = value
    return result


def _read_canonical(path: Path, limit: int) -> tuple[dict, bytes]:
    require_direct_path(path)
    try:
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise RuntimeUnavailable("JSON exceeds byte limit")
        value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=_unique_object)
        if type(value) is not dict or canonical_json_bytes(value) != data:
            raise RuntimeUnavailable("JSON is not canonical")
        return value, data
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        raise RuntimeUnavailable("JSON is unreadable or noncanonical") from exc


def _validate_manifest(manifest: Mapping, rows: list[dict[str, object]]) -> None:
    if set(manifest) != set(FIXED_FIELDS) | {"upstreamCommit", "compatibilityPatchCommit", "rookSkillManifestSha256", "uv", "pythonRuntime", "files"}:
        raise RuntimeUnavailable("runtime manifest keys are invalid")
    for key, expected in FIXED_FIELDS.items():
        if type(manifest[key]) is not type(expected) or manifest[key] != expected:
            raise RuntimeUnavailable(f"runtime field {key} is unsupported")
    upstream, patch = manifest["upstreamCommit"], manifest["compatibilityPatchCommit"]
    if type(upstream) is not str or not COMMIT_PATTERN.fullmatch(upstream):
        raise RuntimeUnavailable("runtime upstreamCommit is invalid")
    if patch is not None and (type(patch) is not str or not COMMIT_PATTERN.fullmatch(patch)):
        raise RuntimeUnavailable("runtime compatibilityPatchCommit is invalid")
    uv = manifest["uv"]
    if type(uv) is not dict or set(uv) != {"version", "executable", "source", "sourceArchiveSha256", "licenses"}:
        raise RuntimeUnavailable("runtime uv keys are invalid")
    if (type(uv["version"]) is not str or not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", uv["version"])
            or uv["executable"] != "tools/uv/uv.exe"
            or uv["licenses"] != ["tools/uv/LICENSE-APACHE", "tools/uv/LICENSE-MIT"]
            or uv["source"] != f"https://github.com/astral-sh/uv/releases/download/{uv['version']}/uv-x86_64-pc-windows-msvc.zip"
            or type(uv["sourceArchiveSha256"]) is not str or not ID_PATTERN.fullmatch(uv["sourceArchiveSha256"])):
        raise RuntimeUnavailable("runtime uv contract differs")
    python_runtime = manifest["pythonRuntime"]
    if type(python_runtime) is not dict or set(python_runtime) != {"root", "sourceCommit", "manifestSha256"}:
        raise RuntimeUnavailable("runtime pythonRuntime keys are invalid")
    if python_runtime != {
        "root": "dist/prime-agent-runtime", "sourceCommit": patch or upstream,
        "manifestSha256": subtree_sha256(rows, "dist/prime-agent-runtime/"),
    }:
        raise RuntimeUnavailable("runtime Python subtree identity differs")
    if manifest["rookSkillManifestSha256"] != subtree_sha256(rows, "skills/rook-full/"):
        raise RuntimeUnavailable("Rook skill manifest identity differs")
    listed = manifest["files"]
    if type(listed) is not list or not 0 < len(listed) <= MAX_FILE_ROWS:
        raise RuntimeUnavailable("manifest file list is invalid")
    previous = ""
    folded = set()
    for row in listed:
        if type(row) is not dict or set(row) != {"path", "bytes", "sha256"}:
            raise RuntimeUnavailable("manifest entry is invalid")
        path = safe_relative_path(row["path"])
        if (path <= previous or path.casefold() in folded or type(row["bytes"]) is not int or row["bytes"] < 0
                or type(row["sha256"]) is not str or not ID_PATTERN.fullmatch(row["sha256"])):
            raise RuntimeUnavailable("manifest entry is not canonical")
        previous = path
        folded.add(path.casefold())
    if listed != rows:
        raise RuntimeUnavailable("manifest file set or bytes differ")
    names = {row["path"] for row in rows}
    required = {"pi.exe", "package.json", "README.md", "CHANGELOG.md", "skills/goal/SKILL.md",
                "skills/rook-full/SKILL.md", "tools/uv/uv.exe", "tools/uv/LICENSE-APACHE",
                "tools/uv/LICENSE-MIT", "notices/prime-agent/LICENSE"}
    if not required <= names or any(not any(str(n).startswith(p) for n in names) for p in ("assets/", "docs/", "examples/")):
        raise RuntimeUnavailable("required runtime artifact file is missing")


def _verified_root_skill(root: Path, rows: Sequence[Mapping[str, object]]) -> str:
    try:
        path = require_direct_path(root / "skills/rook-full/SKILL.md")
        with path.open("rb") as stream:
            data = stream.read(MAX_ROOT_SKILL_UTF8_BYTES + 1)
        if len(data) > MAX_ROOT_SKILL_UTF8_BYTES:
            raise RuntimeUnavailable("root_skill_too_large")
        row = next(row for row in rows if row["path"] == "skills/rook-full/SKILL.md")
        if len(data) != row["bytes"] or sha256_bytes(data) != row["sha256"]:
            raise RuntimeUnavailable("root Rook skill changed after verification")
        return data.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise RuntimeUnavailable("root_skill_invalid_utf8") from exc
    except OSError as exc:
        raise RuntimeUnavailable("root Rook skill is unavailable") from exc


def create_runtime_manifest(payload_root: Path, metadata: RuntimeManifestMetadata) -> str:
    root = require_direct_path(payload_root, directory=True)
    rows = payload_rows(root)
    manifest = {
        **FIXED_FIELDS, "upstreamCommit": UPSTREAM_COMMIT, "compatibilityPatchCommit": PRIME_COMMIT,
        "acpProtocolVersion": metadata.acp_protocol_version,
        "pythonAcpSdkVersion": metadata.python_acp_sdk_version,
        "rookSkillManifestSha256": metadata.rook_skill_manifest_sha256, "uv": UV,
        "pythonRuntime": {"root": "dist/prime-agent-runtime", "sourceCommit": PRIME_COMMIT or UPSTREAM_COMMIT,
                          "manifestSha256": subtree_sha256(rows, "dist/prime-agent-runtime/")},
        "files": rows,
    }
    _validate_manifest(manifest, rows)
    _verified_root_skill(root, rows)
    data = canonical_json_bytes(manifest)
    if len(data) > MAX_MANIFEST_BYTES:
        raise RuntimeUnavailable("runtime manifest exceeds byte limit")
    try:
        with (root / "runtime-manifest.json").open("xb") as stream:
            stream.write(data)
    except OSError as exc:
        raise RuntimeUnavailable("runtime manifest create-only publication failed") from exc
    return sha256_bytes(data)


def verify_runtime_payload(runtime_root: Path, expected_runtime_id: str | None = None) -> VerifiedRuntimePayload:
    try:
        root = require_direct_path(runtime_root, directory=True)
        manifest, data = _read_canonical(root / "runtime-manifest.json", MAX_MANIFEST_BYTES)
        runtime_id = sha256_bytes(data)
        if expected_runtime_id is not None and (type(expected_runtime_id) is not str
                or not ID_PATTERN.fullmatch(expected_runtime_id) or expected_runtime_id != runtime_id):
            raise RuntimeUnavailable("runtime_id differs from manifest")
        rows = payload_rows(root)
        _validate_manifest(manifest, rows)
        return VerifiedRuntimePayload(root, runtime_id, manifest, _verified_root_skill(root, rows))
    except OSError as exc:
        raise RuntimeUnavailable("runtime payload cannot be read") from exc


def read_current_runtime_id(prime_root: Path) -> str:
    value, _ = _read_canonical(prime_root / "current.json", 256)
    if set(value) != {"runtimeId"} or type(value["runtimeId"]) is not str or not ID_PATTERN.fullmatch(value["runtimeId"]):
        raise RuntimeUnavailable("current runtime pointer is invalid")
    return value["runtimeId"]


def publish_runtime_directory(incoming: Path, runtimes: Path, runtime_id: str) -> Path:
    """Windows directory rename is create-only; an existing sibling must verify."""
    verify_runtime_payload(incoming, runtime_id)
    runtimes.mkdir(parents=True, exist_ok=True)
    require_direct_path(runtimes, directory=True)
    if incoming.stat().st_dev != runtimes.stat().st_dev:
        raise RuntimeUnavailable("runtime publication must be same-volume")
    destination = runtimes / runtime_id
    if not destination.exists():
        try:
            incoming.rename(destination)
        except FileExistsError:
            pass
    verify_runtime_payload(destination, runtime_id)
    return destination


def promote_incoming_runtime(incoming_root: Path, prime_root: Path) -> str:
    prime = require_direct_path(prime_root, directory=True)
    incoming = require_direct_path(incoming_root, directory=True)
    if incoming.parent != prime / ".incoming":
        raise RuntimeUnavailable("incoming runtime is not a direct staging generation")
    verified = verify_runtime_payload(incoming)
    if incoming.stat().st_dev != prime.stat().st_dev:
        raise RuntimeUnavailable("runtime publication must be same-volume")
    runtime_id = verified.runtime_id
    publish_runtime_directory(incoming, prime / "runtimes", runtime_id)
    pointer = prime / "current.json"
    if pointer.exists() or pointer.is_symlink():
        require_direct_path(pointer)
    temporary = prime / f".current-{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(canonical_json_bytes({"runtimeId": runtime_id}))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, pointer)
    finally:
        temporary.unlink(missing_ok=True)
    return runtime_id


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", allow_abbrev=False)
    verify.add_argument("--runtime-root", type=Path, required=True)
    verify.add_argument("--expected-runtime-id", required=True)
    promote = commands.add_parser("promote", allow_abbrev=False)
    promote.add_argument("--incoming-root", type=Path, required=True)
    promote.add_argument("--prime-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            print(verify_runtime_payload(args.runtime_root, args.expected_runtime_id).runtime_id)
        else:
            print(promote_incoming_runtime(args.incoming_root, args.prime_root))
        return 0
    except (RuntimeUnavailable, OSError, ValueError) as exc:
        print(f"runtime_unavailable: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
