"""OCCT corresponding-source bundle: build it from the pinned commit, and validate it (#598).

Rook ships 11 OCCT DLLs (LGPL-2.1 with the Open CASCADE exception) next to RookNative.
The exact corresponding source is published beside each installer as a separate zip,
never inside the installer. ``third_party/occt/occt-provenance.json`` is the pin:
the upstream commit, the digest of that commit's full file listing, the build recipe,
and the sha256 of every shipped DLL.

    build     archive the pinned commit (byte-exact blobs) + recipe + licences into the
              source bundle, and write its manifest
    validate  fail closed unless the DLLs ISCC will package, the .iss, the installed
              notices, and the source bundle all match the pin

Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROVENANCE = REPO_ROOT / "third_party" / "occt" / "occt-provenance.json"
MANIFEST_NAME = "rook-occt-source-bundle-manifest.json"
# Fixed zip timestamp: the same inputs always produce the same bundle bytes.
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
# Files copied from this repository into the bundle beside the source archive.
BUNDLE_REPO_FILES = {
    "occt-provenance.json": "third_party/occt/occt-provenance.json",
    "LICENSE_LGPL_21.txt": "third_party/occt/LICENSE_LGPL_21.txt",
    "OCCT_LGPL_EXCEPTION.txt": "third_party/occt/OCCT_LGPL_EXCEPTION.txt",
    "SOURCE.OCCT.txt": "third_party/occt/SOURCE.OCCT.txt",
    "rook-occt-configure.txt": "scripts/occt/rook-occt-configure.txt",
    "occt-build.md": "docs/rook_docs/occt-build.md",
}
NOTICE_DEST = r"{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\notices\occt"


class BundleError(Exception):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def listing_digest(entries: list[tuple[str, str, str]]) -> str:
    """sha256 over sorted ``<mode> <blob-sha1> <path>`` lines: the commit's file content."""
    lines = "".join(f"{mode} {blob} {path}\n" for mode, blob, path in sorted(entries, key=lambda e: e[2]))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "core.autocrlf=false", *args],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        raise BundleError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def commit_listing(repo: Path, commit: str) -> list[tuple[str, str, str]]:
    entries = []
    for line in git(repo, "ls-tree", "-r", "--full-tree", commit).splitlines():
        meta, path = line.split("\t", 1)
        mode, kind, blob = meta.split()
        if kind != "blob":
            raise BundleError(f"unsupported tree entry {kind} at {path}")
        entries.append((mode, blob, path))
    return entries


def archive_listing(archive: zipfile.ZipFile, prefix: str) -> list[tuple[str, str, str]]:
    """Recompute ``(mode, blob, path)`` from a source zip's members, independently of git."""
    entries = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        if not info.filename.startswith(prefix):
            raise BundleError(f"source archive member outside {prefix}: {info.filename}")
        unix_mode = info.external_attr >> 16
        if stat.S_ISLNK(unix_mode):
            mode = "120000"
        else:
            mode = "100755" if unix_mode & 0o111 else "100644"
        entries.append((mode, git_blob_sha1(archive.read(info)), info.filename[len(prefix):]))
    return entries


def load_provenance(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError(f"cannot read OCCT provenance {path}: {exc}") from exc


def source_prefix(provenance: dict) -> str:
    return f"occt-{provenance['version']}/"


def deterministic_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=ZIP_EPOCH)
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, members[name])


# --- build -------------------------------------------------------------------------


def build(occt_repo: Path, output_dir: Path, provenance_path: Path, repo_root: Path) -> Path:
    provenance = load_provenance(provenance_path)
    source = provenance["source"]
    commit = source["commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise BundleError("provenance source.commit must be a full 40-character SHA")
    tagged = git(occt_repo, "rev-parse", f"{source['tag']}^{{commit}}").strip()
    if tagged != commit:
        raise BundleError(f"tag {source['tag']} resolves to {tagged}, not the pinned {commit}")
    if listing_digest(commit_listing(occt_repo, commit)) != source["tree_listing_sha256"]:
        raise BundleError("pinned commit's file listing no longer matches provenance tree_listing_sha256")

    prefix = source_prefix(provenance)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rook-occt-bundle-") as scratch:
        # A private bare clone with `* -text`: git archive then writes every blob
        # byte-for-byte, with no eol=crlf or core.autocrlf conversion.
        clone = Path(scratch) / "occt.git"
        subprocess.run(["git", "clone", "--bare", "--no-local", "--quiet", str(occt_repo), str(clone)], check=True)
        (clone / "info").mkdir(exist_ok=True)
        (clone / "info" / "attributes").write_text("* -text -ident -export-subst -export-ignore\n", encoding="utf-8")
        inner = Path(scratch) / source["archive_name"]
        subprocess.run(
            ["git", "-C", str(clone), "-c", "core.autocrlf=false", "archive", "--format=zip",
             f"--prefix={prefix}", "-o", str(inner), commit],
            check=True,
        )
        with zipfile.ZipFile(inner) as archive:
            if listing_digest(archive_listing(archive, prefix)) != source["tree_listing_sha256"]:
                raise BundleError("generated source archive does not reproduce the pinned commit listing")
        members = {source["archive_name"]: inner.read_bytes()}
        for name, relative in BUNDLE_REPO_FILES.items():
            members[name] = (repo_root / relative).read_bytes()

    bundle = output_dir / provenance["source_bundle_name"]
    deterministic_zip(bundle, members)
    manifest = {
        "schema_version": 1,
        "name": provenance["name"],
        "version": provenance["version"],
        "source_commit": commit,
        "tree_listing_sha256": source["tree_listing_sha256"],
        "bundle_path": str(bundle.resolve()),
        "bundle_sha256": sha256_file(bundle),
        "members": {name: sha256_bytes(data) for name, data in sorted(members.items())},
    }
    manifest_path = output_dir / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


# --- validate ----------------------------------------------------------------------


def iss_occt_dlls(iss_text: str) -> list[str]:
    return re.findall(r'^Source:\s*"\{#OcctRuntimeRoot\}\\(TK\w+\.dll)"', iss_text, re.MULTILINE)


def iss_notice_entry(iss_text: str, filename: str) -> str | None:
    for line in iss_text.splitlines():
        if line.startswith("Source:") and line.split(";")[0].rstrip('"').endswith("\\" + filename):
            return line
    return None


def validate(manifest_path: Path, occt_runtime_root: Path, iss_path: Path, provenance_path: Path, repo_root: Path) -> list[str]:
    """Return every failure; empty means the release may package and publish OCCT."""
    failures: list[str] = []
    provenance = load_provenance(provenance_path)
    source = provenance["source"]
    iss_text = iss_path.read_text(encoding="utf-8-sig")

    # 1. The DLLs ISCC will package (this exact OcctRuntimeRoot) are the pinned build.
    shipped = provenance["shipped_dlls"]
    listed = iss_occt_dlls(iss_text)
    if sorted(listed) != sorted(shipped):
        failures.append(f".iss OCCT DLL set {sorted(listed)} differs from provenance {sorted(shipped)}")
    for name, expected in shipped.items():
        dll = occt_runtime_root / name
        if not dll.is_file():
            failures.append(f"OCCT DLL missing from OcctRuntimeRoot: {dll}")
        elif sha256_file(dll) != expected.upper():
            failures.append(f"{name} in {occt_runtime_root} does not match the provenance sha256")

    # 2. Installed notices: pinned licence texts, shipped with the plugins component.
    for name, expected in provenance["notice_files"].items():
        path = repo_root / "third_party" / "occt" / name
        if not path.is_file():
            failures.append(f"OCCT notice file missing: {path}")
        elif expected and sha256_file(path) != expected.upper():
            failures.append(f"OCCT notice {name} differs from its pinned sha256")
        entry = iss_notice_entry(iss_text, name)
        if entry is None:
            failures.append(f".iss has no Source entry for OCCT notice {name}")
        elif f'DestDir: "{NOTICE_DEST}"' not in entry or "Components: plugins" not in entry:
            failures.append(f".iss entry for {name} must install to {NOTICE_DEST} with Components: plugins")

    # 3. The published source bundle is the pinned commit, byte for byte.
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return failures + [f"cannot read OCCT source-bundle manifest {manifest_path}: {exc}"]
    if manifest.get("source_commit") != source["commit"]:
        failures.append("source-bundle manifest commit differs from the provenance commit")
    bundle = Path(str(manifest.get("bundle_path", "")))
    if bundle.name != provenance["source_bundle_name"] or not bundle.is_file():
        return failures + [f"OCCT source bundle missing or misnamed: {bundle}"]
    if sha256_file(bundle) != str(manifest.get("bundle_sha256", "")).upper():
        failures.append("OCCT source bundle sha256 differs from its manifest")
    required = {source["archive_name"], *BUNDLE_REPO_FILES}
    try:
        with zipfile.ZipFile(bundle) as outer:
            names = set(outer.namelist())
            for missing in sorted(required - names):
                failures.append(f"OCCT source bundle is missing {missing}")
            for name, relative in BUNDLE_REPO_FILES.items():
                if name in names and outer.read(name) != (repo_root / relative).read_bytes():
                    failures.append(f"bundle member {name} differs from {relative}")
            if source["archive_name"] in names:
                with zipfile.ZipFile(io.BytesIO(outer.read(source["archive_name"]))) as inner:
                    digest = listing_digest(archive_listing(inner, source_prefix(provenance)))
                if digest != source["tree_listing_sha256"]:
                    failures.append("OCCT source archive content does not match the pinned commit listing")
    except (zipfile.BadZipFile, BundleError) as exc:
        failures.append(f"OCCT source bundle unreadable: {exc}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provenance", type=Path, default=DEFAULT_PROVENANCE)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--occt-repo", type=Path, required=True)
    b.add_argument("--output-dir", type=Path, default=REPO_ROOT / "artifacts" / "occt")
    v = sub.add_parser("validate")
    v.add_argument("--manifest", type=Path, required=True)
    v.add_argument("--occt-runtime-root", type=Path, required=True,
                   help="the same resolved directory passed to ISCC as /DOcctRuntimeRoot")
    v.add_argument("--iss", type=Path, default=REPO_ROOT / "installer" / "RookSetup.iss")
    args = parser.parse_args(argv)

    try:
        if args.command == "build":
            print(build(args.occt_repo, args.output_dir, args.provenance, args.repo_root))
            return 0
        failures = validate(args.manifest, args.occt_runtime_root, args.iss, args.provenance, args.repo_root)
    except BundleError as exc:
        print(f"OCCT bundle error: {exc}", file=sys.stderr)
        return 1
    for failure in failures:
        print(f"OCCT validation failed: {failure}", file=sys.stderr)
    if not failures:
        print("OCCT payload, notices and source bundle validated.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
