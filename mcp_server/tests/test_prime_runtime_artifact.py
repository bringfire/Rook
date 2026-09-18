from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from rook.agent.chat import prime_runtime_artifact as artifact


PAYLOAD = {
    "pi.exe": b"fixture executable, never launched",
    "package.json": b'{"name":"prime-agent"}\n',
    "README.md": b"readme\n",
    "CHANGELOG.md": b"changes\n",
    "assets/icon.bin": b"asset",
    "docs/acp.md": b"docs",
    "examples/example.txt": b"example",
    "skills/goal/SKILL.md": b"# Goal\n",
    "skills/rook-full/SKILL.md": b"# Rook Full\n",
    "skills/rook-full/references/gh.md": b"# GH\n",
    "dist/prime-agent-runtime/pyproject.toml": b"[project]\n",
    "dist/prime-agent-runtime/prime_agent_runtime/__init__.py": b"# fixture\n",
    "tools/uv/uv.exe": b"fixture uv, never launched",
    "tools/uv/LICENSE-APACHE": b"fixture Apache license\n",
    "tools/uv/LICENSE-MIT": b"fixture MIT license\n",
    "notices/prime-agent/LICENSE": b"fixture Prime notice\n",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def subtree_id(files: dict[str, bytes], prefix: str) -> str:
    return digest(json_bytes({"files": [
        {"path": name[len(prefix):], "bytes": len(data), "sha256": digest(data)}
        for name, data in sorted(files.items()) if name.startswith(prefix)
    ]}))


def write_payload(root: Path, files: dict[str, bytes] | None = None) -> Path:
    for relative, data in (PAYLOAD if files is None else files).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def metadata(files: dict[str, bytes] | None = None):
    return artifact.RuntimeManifestMetadata(1, "0.12.1", subtree_id(PAYLOAD if files is None else files, "skills/rook-full/"))


def materialize(root: Path) -> tuple[Path, str]:
    write_payload(root)
    return root, artifact.create_runtime_manifest(root, metadata())


def rewrite(root: Path, mutate) -> str:
    path = root / "runtime-manifest.json"
    value = json.loads(path.read_bytes())
    mutate(value)
    path.write_bytes(json_bytes(value))
    return digest(path.read_bytes())


def test_canonical_bytes_have_one_independent_unicode_oracle():
    assert artifact.canonical_json_bytes({"z": "\u00e9\U0001f642", "a": '"\\/\n\x01'}) == (
        b'{"a":"\\"\\\\/\\n\\u0001","z":"\xc3\xa9\xf0\x9f\x99\x82"}\n'
    )


def test_manifest_roundtrip_public_cli_and_closed_payload(tmp_path):
    root, runtime_id = materialize(tmp_path / "runtime")
    verified = artifact.verify_runtime_payload(root, runtime_id)
    assert verified.root == root.resolve()
    assert verified.runtime_id == runtime_id
    assert set(verified.manifest) == {
        "schemaVersion", "platform", "architecture", "upstreamCommit", "compatibilityPatchCommit",
        "acpProtocolVersion", "pythonAcpSdkVersion", "executable", "goalSkill", "rookSkill",
        "rookSkillManifestSha256", "claimKeyVersion", "uv", "pythonRuntime", "files",
    }
    assert verified.manifest["compatibilityPatchCommit"] == "08c2610b4822af1b37350c8f03f3281a19311b59"
    assert verified.manifest["platform"] == "windows"
    assert verified.manifest["architecture"] == "amd64"
    assert verified.manifest["pythonRuntime"] == {
        "root": "dist/prime-agent-runtime",
        "sourceCommit": "08c2610b4822af1b37350c8f03f3281a19311b59",
        "manifestSha256": subtree_id(PAYLOAD, "dist/prime-agent-runtime/"),
    }
    assert verified.manifest["files"] == [
        {"path": name, "bytes": len(data), "sha256": digest(data)} for name, data in sorted(PAYLOAD.items())
    ]
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert artifact.main(["verify", "--runtime-root", str(root), "--expected-runtime-id", runtime_id]) == 0
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("change", [
    lambda m: m.update(extra=True),
    lambda m: m.pop("uv"),
    lambda m: m.update(schemaVersion=True),
    lambda m: m.update(platform="linux"),
    lambda m: m.update(architecture="x64"),
    lambda m: m.update(compatibilityPatchCommit="9c25468b"),
    lambda m: m.update(upstreamCommit="F" * 40),
    lambda m: m.update(upstreamCommit=None),
    lambda m: m.update(acpProtocolVersion=True),
    lambda m: m.update(pythonAcpSdkVersion="0.12.2"),
    lambda m: m["uv"].update(extra=True),
    lambda m: m["uv"].update(source="https://invalid.example/uv.zip"),
    lambda m: m["uv"].update(version=True),
    lambda m: m["uv"].update(version="01.2.3"),
    lambda m: m["uv"].update(sourceArchiveSha256=None),
    lambda m: m["uv"].update(sourceArchiveSha256="a" * 64),
    lambda m: m["uv"].update(licenses=["tools/uv/LICENSE-MIT"]),
    lambda m: m["pythonRuntime"].update(manifestSha256="0" * 64),
    lambda m: m["pythonRuntime"].pop("sourceCommit"),
    lambda m: m["pythonRuntime"].update(sourceCommit="3" * 40),
    lambda m: m["files"][0].update(extra=True),
    lambda m: m["files"][0].update(bytes=True),
    lambda m: m["files"].reverse(),
    lambda m: m["files"].append(dict(m["files"][0])),
    lambda m: m["files"][0].update(path="../escape"),
    lambda m: m["files"][0].update(path="C:/escape"),
    lambda m: m["files"][0].update(path="dir//name"),
    lambda m: m["files"][0].update(path="nul.txt"),
])
def test_schema_or_identity_mutation_refuses_even_with_matching_manifest_hash(tmp_path, change):
    root, _ = materialize(tmp_path / "runtime")
    runtime_id = rewrite(root, change)
    assert artifact.main(["verify", "--runtime-root", str(root), "--expected-runtime-id", runtime_id]) != 0


@pytest.mark.parametrize("change", [
    lambda b: b"\xef\xbb\xbf" + b,
    lambda b: b[:-1],
    lambda b: b + b"\n",
    lambda b: b.replace(b'{"acpProtocolVersion":1,', b'{"acpProtocolVersion":1,"acpProtocolVersion":1,'),
    lambda b: b.replace(b'"version":"0.12.3"', b'"version":"0.12.3","version":"0.12.3"'),
    lambda b: b.replace(b'"windows"', b'"\xff"'),
    lambda b: json.dumps(json.loads(b), indent=2).encode() + b"\n",
])
def test_noncanonical_wire_bytes_refuse(tmp_path, change):
    root, _ = materialize(tmp_path / "runtime")
    path = root / "runtime-manifest.json"
    path.write_bytes(change(path.read_bytes()))
    with pytest.raises(artifact.RuntimeUnavailable):
        artifact.verify_runtime_payload(root, digest(path.read_bytes()))


@pytest.mark.parametrize("change", ["missing", "extra", "changed", "directory", "wrong_id"])
def test_payload_tamper_refuses(tmp_path, change):
    root, runtime_id = materialize(tmp_path / "runtime")
    file = root / "pi.exe"
    if change == "missing": file.unlink()
    elif change == "extra": (root / "extra.bin").write_bytes(b"extra")
    elif change == "changed": file.write_bytes(b"substituted")
    elif change == "directory": file.unlink(); file.mkdir()
    else: runtime_id = "A" * 64
    with pytest.raises(artifact.RuntimeUnavailable):
        artifact.verify_runtime_payload(root, runtime_id)


def test_runtime_relocation_preserves_identity(tmp_path):
    root, runtime_id = materialize(tmp_path / "first")
    relocated = tmp_path / "elsewhere" / runtime_id
    relocated.parent.mkdir()
    root.rename(relocated)
    assert artifact.verify_runtime_payload(relocated, runtime_id).runtime_id == runtime_id


def test_manifest_creation_is_create_only(tmp_path):
    root, _ = materialize(tmp_path / "runtime")
    original = (root / "runtime-manifest.json").read_bytes()
    with pytest.raises(artifact.RuntimeUnavailable):
        artifact.create_runtime_manifest(root, metadata())
    assert (root / "runtime-manifest.json").read_bytes() == original


@pytest.mark.parametrize("skill_bytes,error", [(b"\xff", "root_skill_invalid_utf8"), (b"x" * 16385, "root_skill_too_large")], ids=["invalid-utf8", "over-limit"])
def test_manifest_creation_requires_launchable_root_skill(tmp_path, skill_bytes, error):
    files = {**PAYLOAD, "skills/rook-full/SKILL.md": skill_bytes}
    root = write_payload(tmp_path / "runtime", files)
    with pytest.raises(artifact.RuntimeUnavailable, match=error):
        artifact.create_runtime_manifest(root, metadata(files))
    assert not (root / "runtime-manifest.json").exists()


@pytest.mark.parametrize("skill_bytes,error", [(b"\xff", "root_skill_invalid_utf8"), (b"x" * 16385, "root_skill_too_large")], ids=["invalid-utf8", "over-limit"])
def test_truthfully_hashed_invalid_skill_cannot_verify_or_advance_pointer(tmp_path, skill_bytes, error):
    prime = tmp_path / "prime"
    root, _ = materialize(prime / ".incoming" / "invalid-skill")
    (root / "skills/rook-full/SKILL.md").write_bytes(skill_bytes)
    files = {**PAYLOAD, "skills/rook-full/SKILL.md": skill_bytes}

    def rehash(manifest):
        for row in manifest["files"]:
            if row["path"] == "skills/rook-full/SKILL.md":
                row.update(bytes=len(skill_bytes), sha256=digest(skill_bytes))
        manifest["rookSkillManifestSha256"] = subtree_id(files, "skills/rook-full/")

    runtime_id = rewrite(root, rehash)
    pointer = prime / "current.json"
    pointer.write_bytes(b'old selection\n')
    with pytest.raises(artifact.RuntimeUnavailable, match=error):
        artifact.verify_runtime_payload(root, runtime_id)
    assert artifact.main(["promote", "--incoming-root", str(root), "--prime-root", str(prime)]) == 1
    assert pointer.read_bytes() == b'old selection\n'
    assert not (prime / "runtimes").exists()


def test_shared_verification_retains_exact_decoded_skill_at_byte_limit(tmp_path):
    skill = "\u00e9" * 8192
    files = {**PAYLOAD, "skills/rook-full/SKILL.md": skill.encode("utf-8")}
    root = write_payload(tmp_path / "runtime", files)
    runtime_id = artifact.create_runtime_manifest(root, metadata(files))
    verified = artifact.verify_runtime_payload(root, runtime_id)
    assert verified.rook_skill_system_prompt == skill


def test_unreadable_payload_stays_inside_runtime_unavailable_boundary(tmp_path, monkeypatch):
    root, runtime_id = materialize(tmp_path / "runtime")
    real_open = Path.open

    def denied(path, *args, **kwargs):
        if path == root / "pi.exe": raise PermissionError("fixture denial")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(artifact.RuntimeUnavailable): artifact.verify_runtime_payload(root, runtime_id)


def test_promotion_public_cli_selects_verified_runtime_and_preserves_history(tmp_path, monkeypatch):
    prime = tmp_path / "prime"
    incoming, runtime_id = materialize(prime / ".incoming" / "first")
    historical = prime / "runtimes" / ("A" * 64)
    historical.mkdir(parents=True)
    (historical / "keep").write_bytes(b"historical")
    replacements = []
    real_replace = os.replace

    def replace(source, destination):
        assert Path(source).parent == Path(destination).parent == prime
        assert artifact.verify_runtime_payload(prime / "runtimes" / runtime_id, runtime_id)
        replacements.append((source, destination))
        real_replace(source, destination)

    monkeypatch.setattr(artifact.os, "replace", replace)
    assert artifact.main(["promote", "--incoming-root", str(incoming), "--prime-root", str(prime)]) == 0
    assert not incoming.exists()
    assert (prime / "current.json").read_bytes() == ('{"runtimeId":"' + runtime_id + '"}\n').encode()
    assert artifact.read_current_runtime_id(prime) == runtime_id
    assert len(replacements) == 1
    assert (historical / "keep").read_bytes() == b"historical"
    second = prime / ".incoming" / "second"
    shutil.copytree(prime / "runtimes" / runtime_id, second)
    assert artifact.promote_incoming_runtime(second, prime) == runtime_id
    assert second.exists()  # Identical input is reusable, never repaired or overlaid.


@pytest.mark.parametrize("damage", ["incoming", "existing", "outside"])
def test_failed_promotion_does_not_change_pointer_or_authority(tmp_path, damage):
    prime = tmp_path / "prime"
    incoming, runtime_id = materialize(prime / ".incoming" / "attempt")
    pointer = prime / "current.json"
    pointer.write_bytes(b'old pointer remains\n')
    if damage == "incoming": (incoming / "pi.exe").write_bytes(b"corrupt")
    elif damage == "existing":
        installed = prime / "runtimes" / runtime_id
        shutil.copytree(incoming, installed)
        (installed / "pi.exe").write_bytes(b"corrupt")
    else:
        outside = tmp_path / "outside"
        incoming.rename(outside)
        incoming = outside
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert artifact.main(["promote", "--incoming-root", str(incoming), "--prime-root", str(prime)]) != 0
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("wire", [b"", b"{}\n", b'{"runtimeId":"abc"}\n', b'{"runtimeId":null}\n',
    b'{"runtimeId":"' + b"A" * 64 + b'","extra":1}\n',
    b'{"runtimeId":"' + b"a" * 64 + b'"}\n', b"x" * 257])
def test_pointer_refuses_without_fallback(tmp_path, wire):
    materialize(tmp_path / "runtimes" / ("A" * 64))
    (tmp_path / "current.json").write_bytes(wire)
    with pytest.raises(artifact.RuntimeUnavailable): artifact.read_current_runtime_id(tmp_path)


def test_cross_volume_promotion_refuses_before_publication(tmp_path, monkeypatch):
    prime = tmp_path / "prime"
    incoming, _ = materialize(prime / ".incoming/attempt")
    real_stat = Path.stat

    def changed_volume(path, *args, **kwargs):
        result = real_stat(path, *args, **kwargs)
        if path == incoming and kwargs.get("follow_symlinks", True):
            values = list(result)
            values[2] += 1
            return os.stat_result(values)
        return result

    monkeypatch.setattr(Path, "stat", changed_volume)
    assert artifact.main(["promote", "--incoming-root", str(incoming), "--prime-root", str(prime)]) != 0
    assert incoming.exists()
    assert not (prime / "current.json").exists()
    assert not (prime / "runtimes").exists()


def test_directory_junction_cannot_supply_payload(tmp_path):
    root, runtime_id = materialize(tmp_path / "runtime")
    external = tmp_path / "external"
    (root / "assets").rename(external)
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(external), str(root / "assets"))
    else:
        (root / "assets").symlink_to(external, target_is_directory=True)
    with pytest.raises(artifact.RuntimeUnavailable):
        artifact.verify_runtime_payload(root, runtime_id)

def test_complete_manifest_matches_hand_frozen_oracle(tmp_path, monkeypatch):
    # Preserve this historical byte/hash vector independently of the new-build pin.
    monkeypatch.setattr(artifact, "PRIME_COMMIT", "b71badc503f650cd7c10c4acd1206a8406aa0a0b")
    # All fourteen files contain the single byte x. This vector is independent
    # of the production serializer, file walker, and subtree implementation.
    names = ["CHANGELOG.md","README.md","assets/a","dist/prime-agent-runtime/p.py","docs/a","examples/a","notices/prime-agent/LICENSE","package.json","pi.exe","skills/goal/SKILL.md","skills/rook-full/SKILL.md","tools/uv/LICENSE-APACHE","tools/uv/LICENSE-MIT","tools/uv/uv.exe"]
    root = write_payload(tmp_path / "oracle", {name: b"x" for name in names})
    expected = (
        b"{\"acpProtocolVersion\":1,\"architecture\":\"amd64\",\"claimKeyVersion\":1,\"compatibilityPatchCommit\":\"b71ba"
        b"dc503f650cd7c10c4acd1206a8406aa0a0b\",\"executable\":\"pi.exe\",\"files\":[{\"bytes\":1,\"path\":\"CHANGELOG.md\""
        b",\"sha256\":\"2D711642B726B04401627CA9FBAC32F5C8530FB1903CC4DB02258717921A4881\"},{\"bytes\":1,\"path\":\"REA"
        b"DME.md\",\"sha256\":\"2D711642B726B04401627CA9FBAC32F5C8530FB1903CC4DB02258717921A4881\"},{\"bytes\":1,\"pat"
        b"h\":\"assets/a\",\"sha256\":\"2D711642B726B04401627CA9FBAC32F5C8530FB1903CC4DB02258717921A4881\"},{\"bytes\":"
        b"1,\"path\":\"dist/prime-agent-runtime/p.py\",\"sha256\":\"2D711642B726B04401627CA9FBAC32F5C8530FB1903CC4DB0"
        b"2258717921A4881\"},{\"bytes\":1,\"path\":\"docs/a\",\"sha256\":\"2D711642B726B04401627CA9FBAC32F5C8530FB1903CC"
        b"4DB02258717921A4881\"},{\"bytes\":1,\"path\":\"examples/a\",\"sha256\":\"2D711642B726B04401627CA9FBAC32F5C8530"
        b"FB1903CC4DB02258717921A4881\"},{\"bytes\":1,\"path\":\"notices/prime-agent/LICENSE\",\"sha256\":\"2D711642B726"
        b"B04401627CA9FBAC32F5C8530FB1903CC4DB02258717921A4881\"},{\"bytes\":1,\"path\":\"package.json\",\"sha256\":\"2D"
        b"711642B726B04401627CA9FBAC32F5C8530FB1903CC4DB02258717921A4881\"},{\"bytes\":1,\"path\":\"pi.exe\",\"sha256\""
        b":\"2D711642B726B04401627CA9FBAC32F5C8530FB1903CC4DB02258717921A4881\"},{\"bytes\":1,\"path\":\"skills/goal/"
        b"SKILL.md\",\"sha256\":\"2D711642B726B04401627CA9FBAC32F5C8530FB1903CC4DB02258717921A4881\"},{\"bytes\":1,\"p"
        b"ath\":\"skills/rook-full/SKILL.md\",\"sha256\":\"2D711642B726B04401627CA9FBAC32F5C8530FB1903CC4DB022587179"
        b"21A4881\"},{\"bytes\":1,\"path\":\"tools/uv/LICENSE-APACHE\",\"sha256\":\"2D711642B726B04401627CA9FBAC32F5C853"
        b"0FB1903CC4DB02258717921A4881\"},{\"bytes\":1,\"path\":\"tools/uv/LICENSE-MIT\",\"sha256\":\"2D711642B726B04401"
        b"627CA9FBAC32F5C8530FB1903CC4DB02258717921A4881\"},{\"bytes\":1,\"path\":\"tools/uv/uv.exe\",\"sha256\":\"2D711"
        b"642B726B04401627CA9FBAC32F5C8530FB1903CC4DB02258717921A4881\"}],\"goalSkill\":\"skills/goal\",\"platform\":"
        b"\"windows\",\"pythonAcpSdkVersion\":\"0.12.1\",\"pythonRuntime\":{\"manifestSha256\":\"074DF15105791ADD7FA19F1C"
        b"8B08B43F19BEEB308847CF3351AB5E5FCDB5E9C3\",\"root\":\"dist/prime-agent-runtime\",\"sourceCommit\":\"b71badc5"
        b"03f650cd7c10c4acd1206a8406aa0a0b\"},\"rookSkill\":\"skills/rook-full\",\"rookSkillManifestSha256\":\"CABB2CD"
        b"872B5F088C893201D19864D5DF41F84CB784B884E8C49A7BCB9965FD1\",\"schemaVersion\":1,\"upstreamCommit\":\"c718b"
        b"f3c30fd8da206ed551837cbb54f7ad15948\",\"uv\":{\"executable\":\"tools/uv/uv.exe\",\"licenses\":[\"tools/uv/LICE"
        b"NSE-APACHE\",\"tools/uv/LICENSE-MIT\"],\"source\":\"https://github.com/astral-sh/uv/releases/download/0.12"
        b".3/uv-x86_64-pc-windows-msvc.zip\",\"sourceArchiveSha256\":\"B23350C79E8AD0192B8124AF13A0F17E8D4E4549524"
        b"785E1AEF389AE5A06990E\",\"version\":\"0.12.3\"}}\n"
    )
    expected_id = "9A035791EF3CB160EF93B2BCD15AA136D7E9B065A7D45A008B3E8DB92284618F"
    result = artifact.create_runtime_manifest(root, artifact.RuntimeManifestMetadata(
        1, "0.12.1", "CABB2CD872B5F088C893201D19864D5DF41F84CB784B884E8C49A7BCB9965FD1",
    ))
    assert (root / "runtime-manifest.json").read_bytes() == expected
    assert result == expected_id
    assert artifact.verify_runtime_payload(root, expected_id).runtime_id == expected_id
