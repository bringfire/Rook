from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rook.agent.chat import prime_runtime_artifact as artifact
from .test_prime_runtime_artifact import PAYLOAD, materialize


REPO = Path(__file__).resolve().parents[2]


def load_verifier():
    spec = importlib.util.spec_from_file_location("task10_installed_verifier", REPO / "scripts/verify-installed-rookchat-acp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(tmp_path, monkeypatch, *, windows_checkout=False):
    module = load_verifier()
    source = tmp_path / "source"
    installed = tmp_path / "Rook/app"
    site = tmp_path / "Rook/venv/Lib/site-packages"
    python = tmp_path / "Rook/venv/Scripts/python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"fake process boundary, never executed")
    package = source / "mcp_server/src/rook"
    (package / "agent/chat").mkdir(parents=True)
    for relative in ("__init__.py", "__main__.py", "agent/__init__.py", "agent/chat/__init__.py", "agent/chat/service_main.py", "agent/chat/prime_runtime_artifact.py"):
        original = REPO / "mcp_server/src/rook" / relative
        (package / relative).write_bytes(original.read_bytes())
    (source / "scripts").mkdir()
    shutil.copyfile(REPO / "scripts/verify-installed-rookchat-acp.py", source / "scripts/verify-installed-rookchat-acp.py")
    shutil.copyfile(REPO / ".gitattributes", source / ".gitattributes")
    skill = source / "installer/agent-assets/prime-skills/rook-full"
    for name, data in PAYLOAD.items():
        if name.startswith("skills/rook-full/"):
            path = skill / name.removeprefix("skills/rook-full/")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    (source / "mcp_server/pyproject.toml").write_text('[project]\nversion="1.2.3"\n')
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "config", "core.autocrlf", "true" if windows_checkout else "false"], check=True)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    (source / "scripts/verify-installed-rookchat-acp.py").unlink()
    subprocess.run(["git", "-C", str(source), "checkout-index", "--", "scripts/verify-installed-rookchat-acp.py"], check=True)
    if windows_checkout:
        (package / "__main__.py").unlink()
        subprocess.run(["git", "-C", str(source), "checkout-index", "--", "mcp_server/src/rook/__main__.py"], check=True)
    (installed / "mcp_server").mkdir(parents=True)
    shutil.copytree(package, site / "rook")
    incoming, runtime_id = materialize(installed / "prime/.incoming/fixture")
    artifact.promote_incoming_runtime(incoming, installed / "prime")
    (installed / "python-runtime-manifest.json").write_text(json.dumps({"rook_git_sha": commit, "release_version": "1.2.3"}))
    chat = tmp_path / "plugin/net8.0/RookChatService.json"
    chat.parent.mkdir(parents=True)
    chat.write_text(json.dumps({
        "pythonPath": str(python), "workingDirectory": str(installed / "mcp_server"),
        "module": "rook.agent.chat.service_main", "owner": "rhino-panel", "pythonPathEntries": [],
        "environment": {"ROOK_INSTALL_ROOT": str(installed), "ROOK_DATA_DIR": str(tmp_path / "Rook/data"),
                        "ROOK_MODE": "release", "PYTHONHOME": "", "PYTHONPATH": ""},
    }))
    result = {
        "pythonExecutable": str(python), "rookOrigin": str(site / "rook/__init__.py"),
        "serviceOrigin": str(site / "rook/agent/chat/service_main.py"),
        "verifierOrigin": str(site / "rook/agent/chat/prime_runtime_artifact.py"),
    }
    real_run = subprocess.run
    calls = []

    def run(argv, **kwargs):
        if str(argv[0]).lower().endswith("python.exe"):
            assert Path(argv[0]) == python
            assert argv[1:4] == ["-I", "-B", "-c"]
            assert kwargs["shell"] is False and kwargs["timeout"] > 0
            assert Path(kwargs["cwd"]) == installed / "mcp_server"
            assert not any(key.upper() in {"PYTHONPATH", "PYTHONHOME"} for key in kwargs["env"])
            calls.append("installed-python-origin-probe")
            return subprocess.CompletedProcess(argv, 0, json.dumps(result), "")
        assert argv[0] == "git"
        return real_run(argv, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", run)
    report = tmp_path / "evidence/identity.json"
    argv = ["--rook-worktree", str(source), "--expected-rook-commit", commit, "--install-root", str(installed),
            "--chat-service-manifest", str(chat), "--output", str(report)]
    return module, argv, source, installed, chat, report, result, calls, runtime_id


def test_real_verifier_entrypoint_reports_complete_installed_identity(tmp_path, monkeypatch):
    module, argv, source, installed, chat, report, _, calls, runtime_id = fixture(tmp_path, monkeypatch)
    assert module.main(argv) == 0
    data = json.loads(report.read_bytes())
    assert data["sourceCommit"] == argv[3]
    assert data["runtimeId"] == runtime_id == data["manifestSha256"]
    assert data["pointer"] == {"runtimeId": runtime_id}
    assert data["paths"]["primeExecutable"] == str(installed / "prime/runtimes" / runtime_id / "pi.exe")
    assert len(report.read_bytes()) <= 64 * 1024
    assert calls == ["installed-python-origin-probe"]
    original = report.read_bytes()
    assert module.main(argv) != 0
    assert report.read_bytes() == original


@pytest.mark.parametrize("damage", ["wrong_commit", "dirty", "pointer", "interpreter", "origin", "pythonpath", "wheel_commit",
    "missing", "changed", "extra", "relocated", "substituted_skill", "notice", "python_code", "linked"])
def test_failed_comparison_never_publishes_report(tmp_path, monkeypatch, damage):
    module, argv, source, installed, chat, report, origins, calls, runtime_id = fixture(tmp_path, monkeypatch)
    runtime = installed / "prime/runtimes" / runtime_id
    if damage == "wrong_commit": argv[3] = "a" * 40
    elif damage == "dirty": (source / "mcp_server/pyproject.toml").write_text("changed")
    elif damage == "pointer": (installed / "prime/current.json").write_text('{"runtimeId":"other"}')
    elif damage in {"interpreter", "pythonpath"}:
        value = json.loads(chat.read_bytes())
        if damage == "interpreter": value["pythonPath"] = str(tmp_path / "other/python.exe")
        else: value["pythonPathEntries"] = [str(source / "mcp_server/src")]
        chat.write_text(json.dumps(value))
    elif damage == "origin": origins["serviceOrigin"] = str(source / "mcp_server/src/rook/agent/chat/service_main.py")
    elif damage == "wheel_commit": (installed / "python-runtime-manifest.json").write_text('{"rook_git_sha":"wrong","release_version":"1.2.3"}')
    elif damage == "missing": (runtime / "pi.exe").unlink()
    elif damage == "changed": (runtime / "tools/uv/uv.exe").write_bytes(b"changed")
    elif damage == "extra": (runtime / "extra.exe").write_bytes(b"extra")
    elif damage == "relocated": runtime.rename(runtime.parent / ("F" * 64))
    elif damage == "substituted_skill": (runtime / "skills/rook-full/SKILL.md").write_bytes(b"substituted")
    elif damage == "notice": (runtime / "notices/prime-agent/LICENSE").unlink()
    elif damage == "linked":
        import _winapi
        external = tmp_path / "outside-uv"
        (runtime / "tools/uv").rename(external)
        _winapi.CreateJunction(str(external), str(runtime / "tools/uv"))
    else: Path(origins["serviceOrigin"]).write_bytes(b"stale installed code")
    assert module.main(argv) != 0
    assert not report.exists()


def large_manifest(installed):
    path = installed / "python-runtime-manifest.json"
    value = json.loads(path.read_bytes())
    value["wheelhouse"] = [{"path": f"package-{index}.whl", "bytes": 123456,
                           "sha256": "A" * 64} for index in range(2300)]
    path.write_bytes(json.dumps(value).encode("utf-8"))
    assert 280_000 < path.stat().st_size < 340_000
    return path


@pytest.mark.parametrize("damage", [None, "identity", "content"])
def test_large_python_manifest_reaches_remaining_checks(tmp_path, monkeypatch, capsys, damage):
    module, argv, source, installed, chat, report, origins, calls, runtime_id = fixture(tmp_path, monkeypatch)
    path = large_manifest(installed)
    if damage == "identity":
        value = json.loads(path.read_bytes())
        value["rook_git_sha"] = "a" * 40
        path.write_text(json.dumps(value))
    elif damage == "content":
        Path(origins["serviceOrigin"]).write_bytes(b"incorrect installed source")
    assert module.main(argv) == (0 if damage is None else 1)
    if damage is None:
        assert json.loads(report.read_bytes())["runtimeId"] == runtime_id
        assert calls == ["installed-python-origin-probe"]
    else:
        assert not report.exists()
        expected = "wheel source identity differs" if damage == "identity" else "Rook package differs"
        assert expected in capsys.readouterr().err


@pytest.mark.parametrize("kind", ["python", "chat", "origin", "report"])
def test_metadata_limits_remain_specific(tmp_path, monkeypatch, capsys, kind):
    module, argv, source, installed, chat, report, origins, calls, runtime_id = fixture(tmp_path, monkeypatch)
    if kind == "python":
        (installed / "python-runtime-manifest.json").write_bytes(b" " * (16 * 1024 * 1024 + 1))
    elif kind == "chat":
        chat.write_bytes(b" " * (64 * 1024 + 1))
    elif kind == "origin":
        origins["serviceOrigin"] = "x" * (64 * 1024)
    else:
        canonical = module.artifact.canonical_json_bytes
        monkeypatch.setattr(module.artifact, "canonical_json_bytes",
                            lambda value: b"x" * (64 * 1024 + 1) if "sourceCommit" in value else canonical(value))
    assert module.main(argv) == 1
    assert not report.exists()
    assert ("origin probe failed" if kind == "origin" else "byte limit") in capsys.readouterr().err


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{}\xff', b'[]'])
def test_python_manifest_strict_json_admission(tmp_path, monkeypatch, raw):
    module, argv, source, installed, chat, report, *_ = fixture(tmp_path, monkeypatch)
    (installed / "python-runtime-manifest.json").write_bytes(raw)
    assert module.main(argv) == 1
    assert not report.exists()


@pytest.mark.parametrize("limit", [64 * 1024, 16 * 1024 * 1024])
def test_json_byte_ceiling_is_inclusive(tmp_path, limit):
    module = load_verifier()
    path = tmp_path / "metadata.json"
    raw = b'{"value":"' + b"x" * (limit - 12) + b'"}'
    assert len(raw) == limit
    path.write_bytes(raw)
    assert module.read_json(path, limit)["value"] == "x" * (limit - 12)
    path.write_bytes(raw + b" ")
    with pytest.raises(artifact.RuntimeUnavailable, match="byte limit"):
        module.read_json(path, limit)


@pytest.mark.parametrize("damage", [None, "verifier_commit", "verifier_bytes", "product_bytes", "product_manifest", "product_tree", "skill_tree"])
def test_separate_reviewed_verifier_and_product_commits(tmp_path, monkeypatch, capsys, damage):
    module, argv, source, installed, chat, report, origins, calls, runtime_id = fixture(tmp_path, monkeypatch)
    product_commit = argv[3]
    # Verifier-only generations may not change either product tree.
    (source / "review.txt").write_text("verifier review generation\n")
    if damage == "product_tree":
        (source / "mcp_server/src/rook/agent/chat/service_main.py").write_text("# later product, not installed\n")
    elif damage == "skill_tree":
        (source / "installer/agent-assets/prime-skills/rook-full/SKILL.md").write_text("changed skill\n")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "-qm", "reviewed verifier generation"], check=True)
    verifier_commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    argv += ["--expected-verifier-commit", verifier_commit]
    if damage == "verifier_commit":
        argv[-1] = product_commit
    elif damage == "verifier_bytes":
        fake = tmp_path / "substituted-verifier.py"
        fake.write_bytes(b"# not the reviewed verifier")
        monkeypatch.setattr(module, "__file__", str(fake))
    elif damage == "product_bytes":
        Path(origins["serviceOrigin"]).write_text("# later product, not installed\n")
    elif damage == "product_manifest":
        path = installed / "python-runtime-manifest.json"
        value = json.loads(path.read_bytes())
        value["rook_git_sha"] = verifier_commit
        path.write_text(json.dumps(value))
    assert module.main(argv) == (0 if damage is None else 1)
    if damage is None:
        value = json.loads(report.read_bytes())
        assert value["sourceCommit"] == product_commit
        assert value["verifierCommit"] == verifier_commit != product_commit
    else:
        assert not report.exists()
        if damage in {"product_tree", "skill_tree"}:
            assert calls == []
        if damage == "verifier_bytes":
            assert calls == []
            assert "verifier implementation differs from reviewed source" in capsys.readouterr().err


@pytest.mark.parametrize("damage", [False, True])
def test_clean_crlf_checkout_compares_exact_installed_bytes(tmp_path, monkeypatch, capsys, damage):
    module, argv, source, installed, chat, report, origins, calls, runtime_id = fixture(
        tmp_path, monkeypatch, windows_checkout=True)
    relative = "mcp_server/src/rook/__main__.py"
    committed = subprocess.check_output(["git", "-C", str(source), "show", f"{argv[3]}:{relative}"])
    checkout = (source / relative).read_bytes()
    assert b"\r\n" not in committed and b"\n" in committed
    assert b"\r\n" in checkout and checkout != committed
    assert subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"]) == b""
    actual = Path(origins["rookOrigin"]).parent / "__main__.py"
    assert actual.read_bytes() == checkout
    verifier_relative = "scripts/verify-installed-rookchat-acp.py"
    verifier_blob = subprocess.check_output(["git", "-C", str(source), "show", f"{argv[3]}:{verifier_relative}"])
    verifier_checkout = (source / verifier_relative).read_bytes()
    assert b"\r\n" not in verifier_checkout
    assert verifier_checkout == verifier_blob == Path(module.__file__).read_bytes()
    if damage:
        actual.write_bytes(checkout + b"# changed installed bytes\r\n")
    assert module.main(argv) == (1 if damage else 0)
    assert calls == ["installed-python-origin-probe"]
    assert report.exists() is not damage
    if damage:
        assert "installed Rook package differs from source" in capsys.readouterr().err
    else:
        assert json.loads(report.read_bytes())["runtimeId"] == runtime_id
