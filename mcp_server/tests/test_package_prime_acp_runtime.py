from __future__ import annotations

import hashlib
import importlib.util
import stat
import zipfile
from pathlib import Path

import pytest

from .test_prime_runtime_artifact import PAYLOAD, digest


REPO = Path(__file__).resolve().parents[2]


def load_packager():
    spec = importlib.util.spec_from_file_location("rook_prime_packager", REPO / "scripts/package-prime-acp-runtime.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def zip_bytes(path, files):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items(): archive.writestr(name, data)


def inputs(tmp_path):
    prime = tmp_path / "prime.zip"
    files = {name: data for name, data in PAYLOAD.items()
             if not name.startswith(("tools/uv/", "notices/", "skills/rook-full/"))}
    zip_bytes(prime, files)
    skill = tmp_path / "rook-full"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_bytes(b"# Rook\n")
    (skill / "references/gh.md").write_bytes(b"reference\n")
    uv = tmp_path / "uv.zip"
    zip_bytes(uv, {"uv.exe": b"synthetic uv", "uvx.exe": b"not installed"})
    apache, mit = tmp_path / "LICENSE-APACHE", tmp_path / "LICENSE-MIT"
    apache.write_bytes(b"Apache fixture\n")
    mit.write_bytes(b"MIT fixture\n")
    return [
        "--prime-zip", str(prime), "--expected-prime-zip-sha256", digest(prime.read_bytes()),
        "--rook-skill", str(skill), "--uv-zip", str(uv), "--uv-license-apache", str(apache),
        "--uv-license-mit", str(mit), "--prime-license", str(REPO / "third_party/prime-agent/LICENSE"),
        "--output-runtimes-root", str(tmp_path / "runtimes"),
    ]


def value(argv, key): return Path(argv[argv.index(key) + 1])
def runtime_dirs(tmp_path): return list((tmp_path / "runtimes").glob("[A-F0-9]" * 64))


def test_packager_complete_zip_public_cli_and_identical_reuse(tmp_path):
    argv = inputs(tmp_path)
    packager = load_packager()
    assert packager.main(argv) == 0
    roots = runtime_dirs(tmp_path)
    assert len(roots) == 1
    root = roots[0]
    with zipfile.ZipFile(value(argv, "--prime-zip")) as source:
        for item in source.infolist(): assert (root / item.filename).read_bytes() == source.read(item)
    assert (root / "skills/rook-full/references/gh.md").read_bytes() == b"reference\n"
    assert (root / "tools/uv/uv.exe").read_bytes() == b"synthetic uv"
    assert not (root / "tools/uv/uvx.exe").exists()
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert packager.main(argv) == 0
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_wrong_archive_hash_refuses_before_extraction(tmp_path):
    argv = inputs(tmp_path)
    argv[argv.index("--expected-prime-zip-sha256") + 1] = "A" * 64
    assert load_packager().main(argv) != 0
    assert not (tmp_path / "runtimes").exists()


@pytest.mark.parametrize("name", ["../escape", "/rooted", "C:/rooted", "a//b", "./file", "a/../file", "bad\\file", "NUL.txt"])
@pytest.mark.parametrize("which", ["--prime-zip", "--uv-zip"])
def test_archive_path_refusal(tmp_path, name, which):
    argv = inputs(tmp_path)
    info = zipfile.ZipInfo("placeholder")
    info.filename = name
    with zipfile.ZipFile(value(argv, which), "a") as archive: archive.writestr(info, b"escape")
    argv[argv.index("--expected-prime-zip-sha256") + 1] = digest(value(argv, "--prime-zip").read_bytes())
    assert load_packager().main(argv) != 0
    assert not runtime_dirs(tmp_path)
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize("which", ["--prime-zip", "--uv-zip"])
@pytest.mark.parametrize("damage", ["empty", "link", "case"])
def test_archive_shape_refusal(tmp_path, which, damage):
    argv = inputs(tmp_path)
    path = value(argv, which)
    if damage == "empty": zip_bytes(path, {})
    else:
        with zipfile.ZipFile(path, "a") as archive:
            if damage == "case": archive.writestr("PI.EXE" if which == "--prime-zip" else "UV.EXE", b"other")
            else:
                link = zipfile.ZipInfo("linked")
                link.create_system = 3
                link.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(link, b"pi.exe")
    argv[argv.index("--expected-prime-zip-sha256") + 1] = digest(value(argv, "--prime-zip").read_bytes())
    assert load_packager().main(argv) != 0
    assert not runtime_dirs(tmp_path)


@pytest.mark.parametrize("reserved", ["runtime-manifest.json", "skills/rook-full/SKILL.md", "tools/uv/existing", "notices/prime-agent/LICENSE"])
def test_reserved_collision_preserves_extracted_prime_without_additions(tmp_path, reserved):
    argv = inputs(tmp_path)
    prime = value(argv, "--prime-zip")
    with zipfile.ZipFile(prime, "a") as archive: archive.writestr(reserved, b"upstream owns this")
    argv[argv.index("--expected-prime-zip-sha256") + 1] = digest(prime.read_bytes())
    assert load_packager().main(argv) != 0
    assert not runtime_dirs(tmp_path)
    staged = list((tmp_path / "runtimes").glob(".incoming-*"))
    assert len(staged) == 1
    with zipfile.ZipFile(prime) as source:
        assert {p.relative_to(staged[0]).as_posix(): p.read_bytes() for p in staged[0].rglob("*") if p.is_file()} == {
            name: source.read(name) for name in source.namelist()
        }


def test_changed_published_runtime_is_never_repaired(tmp_path):
    argv = inputs(tmp_path)
    packager = load_packager()
    assert packager.main(argv) == 0
    root = runtime_dirs(tmp_path)[0]
    (root / "pi.exe").write_bytes(b"tamper")
    assert packager.main(argv) != 0
    assert (root / "pi.exe").read_bytes() == b"tamper"


def test_tracked_prime_notice_identity():
    data = (REPO / "third_party/prime-agent/LICENSE").read_bytes()
    assert len(data) == 1105
    assert hashlib.sha256(data).hexdigest().upper() == "B288615FB31DC504623582FB790A28E6D86BC2F5C1396845AF555E43386DA5A0"
