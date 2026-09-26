"""Installed licence and third-party notices (#598), checked against installer/RookSetup.iss.

These checks read the .iss and the committed notice files. They resolve what a
`pluginsonly` selection installs, but they do not compile or run the installer: the
packaged payload itself is checked at the release smoke (installed files present).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

REPO = Path(__file__).resolve().parents[2]
ISS = REPO / "installer" / "RookSetup.iss"
INDEX = REPO / "installer" / "THIRD_PARTY_NOTICES.txt"
NOTICES = r"{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\notices"
# How the index spells installed locations for people, and the .iss constants behind them.
LOCATION_PREFIXES = [
    ("%LOCALAPPDATA%\\Rook\\app\\", "{app}\\"),
    ("%LOCALAPPDATA%\\", "{localappdata}\\"),
    ("%APPDATA%\\", "{userappdata}\\"),
]
SOURCE_ROOTS = {"{#RepoRoot}": REPO, "{#FfmpegDir}": REPO / "third_party" / "ffmpeg"}


@dataclass(frozen=True)
class FileEntry:
    source: str
    dest_dir: str
    components: frozenset[str]
    flags: str

    @property
    def installed_path(self) -> str:
        return self.dest_dir + "\\" + PureWindowsPath(self.source).name


def sections(text: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if re.fullmatch(r"\[\w+\]", line):
            current = line[1:-1]
            result.setdefault(current, [])
        elif current and line and not line.startswith(";"):
            result[current].append(line)
    return result


def field(line: str, name: str) -> str | None:
    match = re.search(rf'(?:^|;\s*){name}:\s*("([^"]*)"|[^;]*)', line)
    if not match:
        return None
    return match.group(2) if match.group(2) is not None else match.group(1).strip()


def parse_iss() -> tuple[dict[str, list[str]], list[FileEntry]]:
    parsed = sections(ISS.read_text(encoding="utf-8-sig"))
    files = [
        FileEntry(
            source=field(line, "Source") or "",
            dest_dir=field(line, "DestDir") or "",
            components=frozenset((field(line, "Components") or "").split()),
            flags=field(line, "Flags") or "",
        )
        for line in parsed["Files"]
        if line.startswith("Source:")
    ]
    return parsed, files


def components_for_type(parsed: dict[str, list[str]], install_type: str) -> set[str]:
    selected = set()
    for line in parsed["Components"]:
        if install_type in (field(line, "Types") or "").split():
            selected.add(field(line, "Name"))
    return selected


def installs_under(entry: FileEntry, selected: set[str]) -> bool:
    return not entry.components or bool(entry.components & selected)


def index_notices() -> list[tuple[str, str]]:
    notices = []
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"\s+Notice:\s+(\S.*?)\s+\[(.+)\]", line)
        if match:
            notices.append((match.group(1), match.group(2)))
    return notices


def to_iss_location(path: str) -> str:
    for human, constant in LOCATION_PREFIXES:
        if path.startswith(human):
            return constant + path[len(human):]
    raise AssertionError(f"index location has no known installed root: {path}")


def resolve_source(entry: FileEntry) -> Path:
    for constant, root in SOURCE_ROOTS.items():
        if entry.source.startswith(constant + "\\"):
            return root / Path(*PureWindowsPath(entry.source[len(constant) + 1:]).parts)
    raise AssertionError(f"notice Source is not under a known root: {entry.source}")


def direct_notice_entries(files: list[FileEntry]) -> list[FileEntry]:
    return [
        entry for entry in files
        if entry.dest_dir.startswith(NOTICES)
        or entry.installed_path in (r"{app}\LICENSE", r"{app}\THIRD_PARTY_NOTICES.txt")
        or (entry.dest_dir.endswith(r"RookNative\ffmpeg") and re.search(r"(LICENSE|NOTICE|SOURCE)\.FFmpeg\.txt$", entry.source))
    ]


# --- the index <-> the .iss --------------------------------------------------------


def test_every_direct_index_entry_is_an_iss_file_with_the_stated_component() -> None:
    _, files = parse_iss()
    by_path = {entry.installed_path: entry for entry in files}
    direct = [(p, label) for p, label in index_notices() if not label.startswith("when installed")]
    assert direct, "the index lists no directly installed notices"
    for path, label in direct:
        entry = by_path.get(to_iss_location(path))
        assert entry is not None, f"index entry {path} is not installed by any .iss Source"
        if label == "every installation":
            assert not entry.components, f"{path} must install with every installation"
        else:
            assert label == "plugins" and entry.components == {"plugins"}, f"{path}: label [{label}] vs {sorted(entry.components)}"
        assert resolve_source(entry).is_file(), f"{entry.source} does not exist in the repository"


def test_every_direct_notice_file_in_the_iss_is_listed_in_the_index() -> None:
    _, files = parse_iss()
    listed = {to_iss_location(path) for path, _ in index_notices()}
    for entry in direct_notice_entries(files):
        if entry.installed_path == r"{app}\THIRD_PARTY_NOTICES.txt":
            continue  # the index itself
        assert entry.installed_path in listed, f"{entry.installed_path} is installed but missing from the index"


def test_when_installed_entries_are_backed_by_their_payload_mechanisms() -> None:
    parsed, files = parse_iss()
    prime_source = (REPO / "mcp_server/src/rook/agent/chat/prime_runtime_artifact.py").read_text(encoding="utf-8")
    prime_required = set(re.findall(r'"([^"]+)"', re.search(r"required = \{(.*?)\}", prime_source, re.S).group(1)))
    seen = set()
    for path, label in index_notices():
        if not label.startswith("when installed"):
            continue
        mechanism = label.split(":", 1)[1].strip()
        seen.add(mechanism)
        if mechanism == "Prime runtime payload":
            relative = path.split("<runtime-id>\\", 1)[1].replace("\\", "/")
            assert relative in prime_required, f"{relative} is not a required Prime runtime artifact file"
        elif mechanism == "private Python runtime":
            location = to_iss_location(path)
            if location.endswith(r"\python-runtime-manifest.json"):
                # A preprocessor define, not a path: match the define and its destination.
                manifest = next(e for e in files if e.source == "{#PythonRuntimeManifest}")
                assert manifest.dest_dir + r"\python-runtime-manifest.json" == location
                assert 'PythonRuntimeManifest RepoRoot + "\\installer\\runtime\\python-runtime-manifest.json"' in ISS.read_text(encoding="utf-8-sig")
            else:
                runtime = next(e for e in files if e.source == r"{#PythonRuntimeDir}\*")
                assert location.startswith(runtime.dest_dir + "\\") and "recursesubdirs" in runtime.flags
        else:
            raise AssertionError(f"unknown 'when installed' mechanism: {mechanism}")
    assert seen == {"Prime runtime payload", "private Python runtime"}


# --- pluginsonly selection and deletion rules -----------------------------------------


def test_a_pluginsonly_selection_installs_every_rook_and_plugin_notice() -> None:
    parsed, files = parse_iss()
    selected = components_for_type(parsed, "pluginsonly")
    assert selected == {"plugins"}, selected
    for entry in direct_notice_entries(files):
        assert installs_under(entry, selected), f"{entry.installed_path} is not installed by a pluginsonly install"
        assert "skipifsourcedoesntexist" not in entry.flags and "nocompression" not in entry.flags


def test_no_install_time_deletion_removes_an_installed_notice() -> None:
    parsed, files = parse_iss()
    targets = [entry.installed_path.lower() for entry in direct_notice_entries(files)]
    for line in parsed["InstallDelete"]:
        name = (field(line, "Name") or "").lower()
        for target in targets:
            assert not (target == name or target.startswith(name.rstrip("\\") + "\\")), f"[InstallDelete] {name} removes {target}"
    code = "\n".join(parsed.get("Code", []))
    for call in re.findall(r"\b(?:DelTree|DeleteFile|RemoveDir)\s*\(([^)]*)\)", code):
        assert "notices" not in call.lower() and "license" not in call.lower(), f"[Code] deletes {call}"


# --- the notice files' contents --------------------------------------------------------


def test_rook_license_installs_from_the_repository_root() -> None:
    _, files = parse_iss()
    entry = next(e for e in files if e.installed_path == r"{app}\LICENSE")
    assert resolve_source(entry) == REPO / "LICENSE"
    assert (REPO / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")


def test_vendored_mit_licences_are_the_upstream_files() -> None:
    expected = {
        "src/RookNative/vendor/httplib/LICENSE": ("4b45cbe16d7b71b89ae6127e26e0d90a029198ca5e958ad8e3d0b8bbed364d8b", "Copyright (c) 2017 yhirose"),
        "src/RookNative/vendor/nlohmann/LICENSE.MIT": ("86b998c792894ccb911a1cb7994f7a9652894e7a094c0b5e45be2f553f45cf14", "Copyright (c) 2013-2022 Niels Lohmann"),
    }
    for relative, (sha256, copyright_line) in expected.items():
        data = (REPO / relative).read_bytes()
        assert hashlib.sha256(data).hexdigest() == sha256, f"{relative} is not the upstream file"
        text = data.decode("utf-8")
        assert copyright_line in text and "Permission is hereby granted, free of charge" in text


def test_occt_licence_texts_match_the_provenance_pins() -> None:
    provenance = json.loads((REPO / "third_party/occt/occt-provenance.json").read_text(encoding="utf-8"))
    for name in ("LICENSE_LGPL_21.txt", "OCCT_LGPL_EXCEPTION.txt"):
        digest = hashlib.sha256((REPO / "third_party/occt" / name).read_bytes()).hexdigest()
        assert digest == provenance["notice_files"][name].lower(), name


def test_font_licences_ship_for_every_embedded_font_family() -> None:
    _, files = parse_iss()
    fonts_dir = REPO / "src/Rook/UI/Vision/Resources/fonts"
    installed = {PureWindowsPath(e.source).name for e in files if e.dest_dir == NOTICES + r"\fonts"}
    assert installed == {p.name for p in fonts_dir.glob("OFL-*.txt")} | {"SOURCES.md"}
    for ofl in fonts_dir.glob("OFL-*.txt"):
        assert "SIL OPEN FONT LICENSE" in ofl.read_text(encoding="utf-8").upper()


def test_release_skill_validates_and_compiles_the_same_occt_runtime_root() -> None:
    for skill in (REPO / ".claude/skills/build-release/SKILL.md", REPO / ".agents/skills/build-release/SKILL.md"):
        text = skill.read_text(encoding="utf-8")
        assert "--occt-runtime-root $OcctRuntimeRoot" in text, f"{skill}: validator must use $OcctRuntimeRoot"
        assert '"/DOcctRuntimeRoot=$OcctRuntimeRoot"' in text, f"{skill}: ISCC must receive the same $OcctRuntimeRoot"
