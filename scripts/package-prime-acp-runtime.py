"""Assemble one verified upstream Windows ZIP using preadmitted local inputs."""

from __future__ import annotations

import argparse
import hashlib
import io
import shutil
import stat
import sys
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path

from rook.agent.chat.prime_runtime_artifact import (
    ID_PATTERN, UV, RuntimeManifestMetadata, RuntimeUnavailable, create_runtime_manifest,
    payload_rows, publish_runtime_directory, require_direct_path, safe_relative_path,
    subtree_sha256, verify_runtime_payload,
)


MAX_PRIME_ZIP_BYTES = 2 * 1024**3
MAX_EXTRACTED_BYTES = 8 * 1024**3
MAX_ARCHIVE_ENTRIES = 100_000
MAX_UV_ZIP_BYTES = 128 * 1024**2
MAX_LICENSE_BYTES = 1024**2
PRIME_LICENSE_SHA256 = "B288615FB31DC504623582FB790A28E6D86BC2F5C1396845AF555E43386DA5A0"
UV_LICENSE_APACHE_SHA256 = "C71D239DF91726FC519C6EB72D318EC65820627232B2F796219E87DCF35D0AB4"
UV_LICENSE_MIT_SHA256 = "860E3D7A86B84E6A7012C7A635FC64DF475CEBC6CCE34DFEB73A5982EC58176C"
RESERVED = ("runtime-manifest.json", "skills/rook-full", "tools/uv", "notices/prime-agent")


def bounded_file(path: Path, limit: int) -> Path:
    path = require_direct_path(path)
    if not 0 < path.stat().st_size <= limit:
        raise RuntimeUnavailable("assembly input exceeds byte limit or is empty")
    return path


def verified_input_bytes(path: Path, limit: int, expected_sha256: str) -> bytes:
    with bounded_file(path, limit).open("rb") as stream:
        data = stream.read(limit + 1)
    if not 0 < len(data) <= limit:
        raise RuntimeUnavailable("assembly input exceeds byte limit or is empty")
    if hashlib.sha256(data).hexdigest().upper() != expected_sha256:
        raise RuntimeUnavailable(f"{path.name} SHA-256 differs")
    return data


def admitted_entries(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    entries = archive.infolist()
    if not 0 < len(entries) <= MAX_ARCHIVE_ENTRIES:
        raise RuntimeUnavailable("ZIP entry count is invalid")
    seen = {}
    explicit = set()
    files = set()
    total = 0
    for item in entries:
        if item.orig_filename != item.filename:
            raise RuntimeUnavailable("ZIP path was normalized by the reader")
        name = safe_relative_path(item.filename[:-1] if item.is_dir() else item.filename)
        mode = item.external_attr >> 16
        if (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}
                or bool(item.external_attr & 0x400) or item.flag_bits & 1):
            raise RuntimeUnavailable("ZIP contains a link, special file, or encryption")
        if name.casefold() in explicit:
            raise RuntimeUnavailable("ZIP contains duplicate paths")
        explicit.add(name.casefold())
        parts = name.split("/")
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            folded = prefix.casefold()
            if folded in seen and seen[folded] != prefix:
                raise RuntimeUnavailable("ZIP contains case-colliding paths")
            if folded in files and index < len(parts):
                raise RuntimeUnavailable("ZIP file collides with a directory")
            seen[folded] = prefix
        if not item.is_dir():
            if any(key.startswith(name.casefold() + "/") for key in seen):
                raise RuntimeUnavailable("ZIP file collides with a directory")
            files.add(name.casefold())
        total += item.file_size
        if item.file_size < 0 or total > MAX_EXTRACTED_BYTES:
            raise RuntimeUnavailable("ZIP expanded byte ceiling exceeded")
    return entries


def copy_stream(source, target: Path, limit: int) -> None:
    count = 0
    with target.open("xb") as output:
        while block := source.read(1024 * 1024):
            count += len(block)
            if count > limit:
                raise RuntimeUnavailable("expanded input exceeds byte limit")
            output.write(block)


def extract_complete(archive: zipfile.ZipFile, entries, root: Path) -> None:
    for item in entries:
        target = root / item.filename
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source:
                copy_stream(source, target, item.file_size)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("prime-zip", "rook-skill", "uv-zip", "uv-license-apache", "uv-license-mit", "prime-license", "output-runtimes-root"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--expected-prime-zip-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if not ID_PATTERN.fullmatch(args.expected_prime_zip_sha256):
            raise RuntimeUnavailable("ZIP SHA-256 is invalid")
        prime_zip = bounded_file(args.prime_zip, MAX_PRIME_ZIP_BYTES)
        uv_bytes = verified_input_bytes(args.uv_zip, MAX_UV_ZIP_BYTES, UV["sourceArchiveSha256"])
        apache = verified_input_bytes(args.uv_license_apache, MAX_LICENSE_BYTES, UV_LICENSE_APACHE_SHA256)
        mit = verified_input_bytes(args.uv_license_mit, MAX_LICENSE_BYTES, UV_LICENSE_MIT_SHA256)
        notice = bounded_file(args.prime_license, MAX_LICENSE_BYTES)
        notice_data = notice.read_bytes()
        if len(notice_data) != 1105 or hashlib.sha256(notice_data).hexdigest().upper() != PRIME_LICENSE_SHA256:
            raise RuntimeUnavailable("Prime legal notice identity differs")
        skill = require_direct_path(args.rook_skill, directory=True)
        skill_rows = payload_rows(skill)
        if not any(row["path"] == "SKILL.md" for row in skill_rows):
            raise RuntimeUnavailable("root Rook skill is absent")
        # The file handle hashed here is also the ZIP input used for extraction.
        with prime_zip.open("rb") as stream:
            archive_hash = hashlib.file_digest(stream, "sha256").hexdigest().upper()
            if archive_hash != args.expected_prime_zip_sha256:
                raise RuntimeUnavailable("upstream ZIP hash differs before extraction")
            stream.seek(0)
            with zipfile.ZipFile(stream) as prime, zipfile.ZipFile(io.BytesIO(uv_bytes)) as uv:
                entries = admitted_entries(prime)
                uv_entries = admitted_entries(uv)
                uv_exe = [item for item in uv_entries if item.filename == "uv.exe" and not item.is_dir()]
                if len(uv_exe) != 1 or uv_exe[0].file_size > MAX_UV_ZIP_BYTES:
                    raise RuntimeUnavailable("uv archive lacks bounded Windows uv.exe")
                output = args.output_runtimes_root.absolute()
                output.mkdir(parents=True, exist_ok=True)
                require_direct_path(output, directory=True)
                stage = Path(tempfile.mkdtemp(prefix=".incoming-", dir=output))
                extract_complete(prime, entries, stage)
                if any((stage / path).exists() for path in RESERVED):
                    raise RuntimeUnavailable("reserved assembly destination already exists")
                names = {item.filename for item in entries if not item.is_dir()}
                if not {"pi.exe", "package.json", "README.md", "CHANGELOG.md", "skills/goal/SKILL.md"} <= names:
                    raise RuntimeUnavailable("upstream artifact shape is incomplete")
                for prefix in ("assets/", "docs/", "examples/", "dist/prime-agent-runtime/"):
                    if not any(name.startswith(prefix) for name in names):
                        raise RuntimeUnavailable("upstream artifact subtree is absent")
                shutil.copytree(skill, stage / "skills/rook-full")
                tools = stage / "tools/uv"
                tools.mkdir(parents=True)
                with uv.open(uv_exe[0]) as source:
                    copy_stream(source, tools / "uv.exe", MAX_UV_ZIP_BYTES)
                for data, destination in ((apache, tools / "LICENSE-APACHE"), (mit, tools / "LICENSE-MIT")):
                    with destination.open("xb") as output_stream:
                        output_stream.write(data)
                legal = stage / "notices/prime-agent"
                legal.mkdir(parents=True)
                with (legal / "LICENSE").open("xb") as output_stream:
                    output_stream.write(notice_data)
        rows = payload_rows(stage)
        runtime_id = create_runtime_manifest(stage, RuntimeManifestMetadata(1, "0.12.1", subtree_sha256(rows, "skills/rook-full/")))
        verify_runtime_payload(stage, runtime_id)
        destination = publish_runtime_directory(stage, output, runtime_id)
        print(destination)
        return 0
    except (OSError, RuntimeUnavailable, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        print(f"runtime_unavailable: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
