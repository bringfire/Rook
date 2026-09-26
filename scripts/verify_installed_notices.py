"""Release smoke: verify the licence and notice files an installation actually carries (#598).

Reads installer/THIRD_PARTY_NOTICES.txt (the installed index) and installer/RookSetup.iss.
Every directly installed notice ("every installation" / "plugins") must exist at its
installed location with exactly the bytes of the repository file the .iss packages.
"when installed" entries (Prime runtime payload, private Python runtime) must exist
when their payload is present. Writes a JSON evidence record; exits 1 on any failure.

Stdlib only; run with the staged private Python: python -I scripts/verify_installed_notices.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

REPO_ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def iss_sources(iss_text: str) -> dict[str, str]:
    """installed location ({app}\\LICENSE, ...) -> .iss Source for single-file entries."""
    sources = {}
    for line in iss_text.splitlines():
        match = re.match(r'Source:\s*"([^"]+)";\s*DestDir:\s*"([^"]+)"', line.strip())
        if match and "*" not in match.group(1):
            sources[match.group(2) + "\\" + PureWindowsPath(match.group(1)).name] = match.group(1)
    return sources


def index_notices(index_text: str) -> list[tuple[str, str]]:
    return [
        (m.group(1), m.group(2))
        for m in (re.fullmatch(r"\s+Notice:\s+(\S.*?)\s+\[(.+)\]", line) for line in index_text.splitlines())
        if m
    ]


def verify(repo_root: Path, appdata: Path, localappdata: Path) -> dict:
    iss_text = (repo_root / "installer" / "RookSetup.iss").read_text(encoding="utf-8-sig")
    index_text = (repo_root / "installer" / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    sources = iss_sources(iss_text)
    roots = {"{#RepoRoot}": repo_root, "{#FfmpegDir}": repo_root / "third_party" / "ffmpeg"}
    human_to_iss = [("%LOCALAPPDATA%\\Rook\\app\\", "{app}\\"), ("%LOCALAPPDATA%\\", "{localappdata}\\"),
                    ("%APPDATA%\\", "{userappdata}\\")]
    human_to_disk = [("%LOCALAPPDATA%\\", localappdata), ("%APPDATA%\\", appdata)]

    def on_disk(human: str) -> Path:
        for prefix, base in human_to_disk:
            if human.startswith(prefix):
                return base.joinpath(*PureWindowsPath(human[len(prefix):]).parts)
        raise ValueError(f"unknown installed root: {human}")

    results = []
    # The index itself is installed too; check it like any other direct notice.
    entries = [("%LOCALAPPDATA%\\Rook\\app\\THIRD_PARTY_NOTICES.txt", "every installation"), *index_notices(index_text)]
    for human, label in entries:
        record = {"installed": human, "label": label}
        if label.startswith("when installed"):
            mechanism = label.split(":", 1)[1].strip()
            if mechanism == "Prime runtime payload":
                runtimes = on_disk(human.split("<runtime-id>")[0].rstrip("\\"))
                suffix = human.split("<runtime-id>\\", 1)[1]
                present = sorted(runtimes.glob("*")) if runtimes.is_dir() else []
                found = [str(d.joinpath(*PureWindowsPath(suffix).parts)) for d in present
                         if d.joinpath(*PureWindowsPath(suffix).parts).is_file()]
                record.update(payload_present=bool(present), found=found,
                              status="ok" if found or not present else "missing")
            elif mechanism == "private Python runtime":
                # Keyed on the runtime itself: the manifest's folder ({app}) exists even
                # on a plugins-only install, which has no Python runtime at all.
                path = on_disk(human)
                present = on_disk("%LOCALAPPDATA%\\Rook\\python\\cpython-3.11.9\\python.exe").is_file()
                record.update(payload_present=present,
                              status="ok" if path.is_file() or not present else "missing")
            else:
                record["status"] = f"unknown mechanism: {mechanism}"
            results.append(record)
            continue
        iss_location = next(
            (iss + human[len(h):] for h, iss in human_to_iss if human.startswith(h)), None)
        source = sources.get(iss_location or "")
        if source is None:
            results.append({**record, "status": "not-in-iss"})
            continue
        constant, relative = source.split("\\", 1)
        expected = roots[constant].joinpath(*PureWindowsPath(relative).parts)
        installed = on_disk(human)
        record.update(source=str(expected), expected_sha256=sha256(expected))
        if not installed.is_file():
            record["status"] = "missing"
        else:
            record["installed_sha256"] = sha256(installed)
            record["status"] = "ok" if record["installed_sha256"] == record["expected_sha256"] else "differs"
        results.append(record)

    return {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "appdata": str(appdata),
        "localappdata": str(localappdata),
        "ok": all(r["status"] == "ok" for r in results),
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True, help="evidence JSON, kept with the release smoke")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--appdata", type=Path, default=Path(os.environ.get("APPDATA", "")))
    parser.add_argument("--localappdata", type=Path, default=Path(os.environ.get("LOCALAPPDATA", "")))
    args = parser.parse_args(argv)
    evidence = verify(args.repo_root, args.appdata, args.localappdata)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    for result in evidence["results"]:
        if result["status"] != "ok":
            print(f"installed notice {result['status']}: {result['installed']}", file=sys.stderr)
    print(f"installed notices {'verified' if evidence['ok'] else 'FAILED'}: {args.output}")
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
