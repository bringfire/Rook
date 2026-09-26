"""OCCT corresponding-source bundle: build from the pinned commit, validate fail-closed (#598).

A throwaway git repository stands in for OCCT. It carries the attributes that make a
naive `git archive` diverge from the commit (an eol=crlf file under core.autocrlf=true)
and an executable file, so the tests prove the bundle is the commit byte for byte.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def load_bundle_tool():
    spec = importlib.util.spec_from_file_location("rook_occt_bundle", REPO / "scripts/occt/rook_occt_bundle.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


NOTICE_DEST = r"{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\notices\occt"
DLLS = {"TKernel.dll": b"kernel", "TKMath.dll": b"math"}


@pytest.fixture
def world(tmp_path: Path):
    tool = load_bundle_tool()
    occt = tmp_path / "OCCT"
    occt.mkdir()
    git(occt, "init", "-q")
    git(occt, "config", "core.autocrlf", "true")  # the trap this machine has
    git(occt, "config", "user.email", "fixture@example.invalid")
    git(occt, "config", "user.name", "fixture")
    (occt / ".gitattributes").write_bytes(b"*.bat eol=crlf\n*.txt eol=lf\n")
    (occt / "build.bat").write_bytes(b"@echo off\necho build\n")
    (occt / "LICENSE_LGPL_21.txt").write_bytes(b"LGPL text\n")
    (occt / "src").mkdir()
    (occt / "src" / "kernel.cxx").write_bytes(b"int kernel() { return 1; }\n")
    (occt / "gendoc").write_bytes(b"#!/bin/sh\necho doc\n")
    git(occt, "add", "-A")
    git(occt, "update-index", "--chmod=+x", "gendoc")
    git(occt, "commit", "-q", "-m", "fixture")
    git(occt, "tag", "V8_0_0")
    commit = git(occt, "rev-parse", "HEAD")

    root = tmp_path / "Rook"
    for relative in tool.BUNDLE_REPO_FILES.values():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes(b"fixture " + relative.encode() + b"\n")
    (root / "third_party/occt/LICENSE_LGPL_21.txt").write_bytes(b"LGPL text\n")
    runtime = tmp_path / "bin"
    runtime.mkdir()
    for name, data in DLLS.items():
        (runtime / name).write_bytes(data)
    listing = tool.commit_listing(occt, commit)
    provenance = {
        "name": "OCCT", "version": "8.0.0",
        "source": {"tag": "V8_0_0", "commit": commit, "tree_listing_sha256": tool.listing_digest(listing),
                   "archive_name": "occt-8.0.0-source.zip"},
        "source_bundle_name": "rook-occt-8.0.0-source-bundle.zip",
        "shipped_dlls": {name: hashlib.sha256(data).hexdigest().upper() for name, data in DLLS.items()},
        "notice_files": {"LICENSE_LGPL_21.txt": hashlib.sha256(b"LGPL text\n").hexdigest(), "SOURCE.OCCT.txt": ""},
    }
    provenance_path = root / "third_party/occt/occt-provenance.json"
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    iss = tmp_path / "RookSetup.iss"
    lines = [f'Source: "{{#OcctRuntimeRoot}}\\{name}"; DestDir: "x"; Components: plugins; Flags: ignoreversion' for name in DLLS]
    lines += [f'Source: "{{#RepoRoot}}\\third_party\\occt\\{name}"; DestDir: "{NOTICE_DEST}"; Components: plugins; Flags: ignoreversion'
              for name in provenance["notice_files"]]
    iss.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"tool": tool, "occt": occt, "root": root, "runtime": runtime, "iss": iss,
            "provenance": provenance_path, "out": tmp_path / "artifacts", "commit": commit}


def build(w) -> Path:
    return w["tool"].build(w["occt"], w["out"], w["provenance"], w["root"])


def validate(w, manifest: Path) -> list[str]:
    return w["tool"].validate(manifest, w["runtime"], w["iss"], w["provenance"], w["root"])


def rewrite_bundle(manifest: Path, change) -> None:
    """Rewrite the bundle through ``change(members)`` and re-seal the manifest's
    bundle sha256, so only the content checks can catch the tampering."""
    data = json.loads(manifest.read_text(encoding="utf-8"))
    bundle = Path(data["bundle_path"])
    with zipfile.ZipFile(bundle) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    change(members)
    with zipfile.ZipFile(bundle, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    data["bundle_sha256"] = hashlib.sha256(bundle.read_bytes()).hexdigest().upper()
    manifest.write_text(json.dumps(data), encoding="utf-8")


def test_bundle_is_the_pinned_commit_byte_for_byte_and_validates(world) -> None:
    manifest = build(world)
    assert validate(world, manifest) == []
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["source_commit"] == world["commit"]
    with zipfile.ZipFile(data["bundle_path"]) as outer:
        assert set(outer.namelist()) == {"occt-8.0.0-source.zip", *world["tool"].BUNDLE_REPO_FILES}
        with zipfile.ZipFile(io.BytesIO(outer.read("occt-8.0.0-source.zip"))) as inner:
            # eol=crlf + core.autocrlf=true must NOT leak CRLF into the published source.
            assert inner.read("occt-8.0.0/build.bat") == b"@echo off\necho build\n"
            assert (inner.getinfo("occt-8.0.0/gendoc").external_attr >> 16) & 0o111


def test_bundle_bytes_are_reproducible(world) -> None:
    first = Path(json.loads(build(world).read_text(encoding="utf-8"))["bundle_path"]).read_bytes()
    second = Path(json.loads(build(world).read_text(encoding="utf-8"))["bundle_path"]).read_bytes()
    assert first == second


def test_a_changed_source_file_fails_even_with_a_resealed_manifest(world) -> None:
    manifest = build(world)

    def edit_one_source_file(members):
        source = io.BytesIO(members["occt-8.0.0-source.zip"])
        edited = io.BytesIO()
        with zipfile.ZipFile(source) as inner, zipfile.ZipFile(edited, "w") as out:
            for info in inner.infolist():
                payload = inner.read(info)
                if info.filename == "occt-8.0.0/src/kernel.cxx":
                    payload = b"int kernel() { return 2; }\n"
                out.writestr(info, payload)
        members["occt-8.0.0-source.zip"] = edited.getvalue()

    rewrite_bundle(manifest, edit_one_source_file)
    assert any("does not match the pinned commit listing" in f for f in validate(world, manifest))


def test_an_added_source_file_fails(world) -> None:
    manifest = build(world)

    def add_file(members):
        edited = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(members["occt-8.0.0-source.zip"])) as inner, zipfile.ZipFile(edited, "w") as out:
            for info in inner.infolist():
                out.writestr(info, inner.read(info))
            out.writestr("occt-8.0.0/src/extra.cxx", b"// not in the commit\n")
        members["occt-8.0.0-source.zip"] = edited.getvalue()

    rewrite_bundle(manifest, add_file)
    assert any("pinned commit listing" in f for f in validate(world, manifest))


@pytest.mark.parametrize(
    ("damage", "expected"),
    [
        ("dll-bytes", "does not match the provenance sha256"),
        ("dll-missing", "OCCT DLL missing"),
        ("iss-extra-dll", ".iss OCCT DLL set"),
        ("iss-notice-component", "must install to"),
        ("licence-text", "differs from its pinned sha256"),
        ("manifest-commit", "manifest commit differs"),
        ("bundle-bytes", "bundle sha256 differs"),
        ("bundle-member-missing", "bundle is missing rook-occt-configure.txt"),
        ("bundle-member-stale", "bundle member occt-provenance.json differs"),
    ],
)
def test_validation_fails_closed(world, damage: str, expected: str) -> None:
    manifest = build(world)
    if damage == "dll-bytes":
        (world["runtime"] / "TKMath.dll").write_bytes(b"a different build")
    elif damage == "dll-missing":
        (world["runtime"] / "TKMath.dll").unlink()
    elif damage == "iss-extra-dll":
        world["iss"].write_text(world["iss"].read_text() + 'Source: "{#OcctRuntimeRoot}\\TKBO.dll"; DestDir: "x"\n')
    elif damage == "iss-notice-component":
        lines = world["iss"].read_text().splitlines()
        lines[-1] = lines[-1].replace("Components: plugins", "Components: mcp")  # SOURCE.OCCT.txt entry
        world["iss"].write_text("\n".join(lines) + "\n")
    elif damage == "licence-text":
        (world["root"] / "third_party/occt/LICENSE_LGPL_21.txt").write_bytes(b"LGPL text, edited\n")
    elif damage == "manifest-commit":
        data = json.loads(manifest.read_text())
        data["source_commit"] = "0" * 40
        manifest.write_text(json.dumps(data))
    elif damage == "bundle-bytes":
        bundle = Path(json.loads(manifest.read_text())["bundle_path"])
        bundle.write_bytes(bundle.read_bytes() + b"x")
    elif damage == "bundle-member-missing":
        rewrite_bundle(manifest, lambda members: members.pop("rook-occt-configure.txt"))
    elif damage == "bundle-member-stale":
        (world["root"] / "third_party/occt/occt-provenance.json").write_text(
            json.dumps({**json.loads(world["provenance"].read_text()), "note": "edited after bundling"}))
    failures = validate(world, manifest)
    assert any(expected in f for f in failures), failures


def test_build_refuses_when_the_tag_no_longer_names_the_pinned_commit(world) -> None:
    (world["occt"] / "src" / "kernel.cxx").write_bytes(b"int kernel() { return 3; }\n")
    git(world["occt"], "commit", "-q", "-am", "moved")
    git(world["occt"], "tag", "-f", "V8_0_0")
    with pytest.raises(world["tool"].BundleError, match="not the pinned"):
        build(world)


def test_committed_provenance_pins_the_real_occt_notices_and_dll_set() -> None:
    tool = load_bundle_tool()
    provenance = json.loads((REPO / "third_party/occt/occt-provenance.json").read_text(encoding="utf-8"))
    assert provenance["source"]["commit"] == "d3056ef80c9668f395da40f5fd7be186cae4501f"
    assert provenance["provenance"]["status"] == "reconstructed" and provenance["provenance"]["limitation"]
    for name in ("LICENSE_LGPL_21.txt", "OCCT_LGPL_EXCEPTION.txt"):
        assert tool.sha256_file(REPO / "third_party/occt" / name) == provenance["notice_files"][name].upper()
    iss = (REPO / "installer/RookSetup.iss").read_text(encoding="utf-8-sig")
    assert sorted(tool.iss_occt_dlls(iss)) == sorted(provenance["shipped_dlls"])
