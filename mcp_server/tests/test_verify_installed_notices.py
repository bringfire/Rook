"""The release-smoke check of installed notices (scripts/verify_installed_notices.py, #598).

A fake %APPDATA% / %LOCALAPPDATA% is populated from the real .iss and index, so the
check runs against the real mapping of installed locations to repository sources.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path, PureWindowsPath

import pytest

REPO = Path(__file__).resolve().parents[2]


def load_checker():
    spec = importlib.util.spec_from_file_location("verify_installed_notices", REPO / "scripts/verify_installed_notices.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fake_install(tmp_path: Path, *, mcp: bool) -> tuple[Path, Path]:
    """Lay out every direct notice at its installed location, as the installer would."""
    checker = load_checker()
    appdata, localappdata = tmp_path / "Roaming", tmp_path / "Local"
    iss = (REPO / "installer/RookSetup.iss").read_text(encoding="utf-8-sig")
    roots = {"{app}": localappdata / "Rook" / "app", "{localappdata}": localappdata, "{userappdata}": appdata}
    source_roots = {"{#RepoRoot}": REPO, "{#FfmpegDir}": REPO / "third_party/ffmpeg"}
    index = (REPO / "installer/THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    wanted = {"{app}\\THIRD_PARTY_NOTICES.txt"}
    for human, label in checker.index_notices(index):
        if not label.startswith("when installed"):
            for prefix, constant in (("%LOCALAPPDATA%\\Rook\\app\\", "{app}\\"), ("%APPDATA%\\", "{userappdata}\\")):
                if human.startswith(prefix):
                    wanted.add(constant + human[len(prefix):])
    for location, source in checker.iss_sources(iss).items():
        if location not in wanted:
            continue
        constant, rest = location.split("\\", 1)
        target = roots[constant].joinpath(*PureWindowsPath(rest).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        src_constant, src_rest = source.split("\\", 1)
        shutil.copyfile(source_roots[src_constant].joinpath(*PureWindowsPath(src_rest).parts), target)
    if mcp:
        runtime = localappdata / "Rook/app/prime/runtimes" / ("A" * 64)
        for relative in ("notices/prime-agent/LICENSE", "tools/uv/LICENSE-MIT", "tools/uv/LICENSE-APACHE"):
            (runtime / relative).parent.mkdir(parents=True, exist_ok=True)
            (runtime / relative).write_text("licence\n", encoding="utf-8")
        python = localappdata / "Rook/python/cpython-3.11.9"
        python.mkdir(parents=True)
        (python / "python.exe").write_bytes(b"MZ")
        (python / "LICENSE.txt").write_text("PSF\n", encoding="utf-8")
        (localappdata / "Rook/app/python-runtime-manifest.json").write_text("{}", encoding="utf-8")
    return appdata, localappdata


@pytest.mark.parametrize("mcp", [True, False], ids=["full", "pluginsonly-layout"])
def test_a_complete_installation_verifies(tmp_path: Path, mcp: bool) -> None:
    checker = load_checker()
    appdata, localappdata = fake_install(tmp_path, mcp=mcp)
    evidence = checker.verify(REPO, appdata, localappdata)
    assert evidence["ok"], [r for r in evidence["results"] if r["status"] != "ok"]
    direct = [r for r in evidence["results"] if not r["label"].startswith("when installed")]
    # 15 indexed notices (Rook 1, OCCT 4, httplib 1, nlohmann 1, fonts 5, FFmpeg 3) + the index itself.
    assert len(direct) == 16 and all(r["installed_sha256"] == r["expected_sha256"] for r in direct)
    prime = [r for r in evidence["results"] if "Prime" in r["label"]]
    assert all(r["payload_present"] is mcp for r in prime)


@pytest.mark.parametrize("damage", ["missing", "differs", "prime-notice-missing"])
def test_a_missing_or_altered_notice_fails(tmp_path: Path, damage: str) -> None:
    checker = load_checker()
    appdata, localappdata = fake_install(tmp_path, mcp=True)
    occt = appdata / "McNeel/Rhinoceros/8.0/Plug-ins/RookNative/notices/occt/LICENSE_LGPL_21.txt"
    if damage == "missing":
        occt.unlink()
    elif damage == "differs":
        occt.write_bytes(occt.read_bytes().replace(b"\n", b"\r\n"))  # e.g. a CRLF-converted copy
    else:
        next((localappdata / "Rook/app/prime/runtimes").glob("*/notices/prime-agent/LICENSE")).unlink()
    output = tmp_path / "evidence.json"
    exit_code = checker.main(["--output", str(output), "--appdata", str(appdata), "--localappdata", str(localappdata)])
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1 and evidence["ok"] is False
    assert any(r["status"] in {"missing", "differs"} for r in evidence["results"])


def test_release_skill_runs_the_installed_notice_check_in_step_8() -> None:
    for skill in (REPO / ".claude/skills/build-release/SKILL.md", REPO / ".agents/skills/build-release/SKILL.md"):
        text = skill.read_text(encoding="utf-8")
        step8 = text.split("## Step 8", 1)[1].split("## Step 9", 1)[0]
        assert "scripts\\verify_installed_notices.py --output installer\\output\\installed-notices-" in step8
        assert "installed-notices-" in text.split("## Step 9", 1)[1], "the evidence must be kept with the release record"
