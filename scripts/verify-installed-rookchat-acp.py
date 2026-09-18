"""Read-only installed ACP identity check; publishes diagnostics only on success."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

from rook.agent.chat import prime_runtime_artifact as artifact


MAX_JSON_BYTES = 64 * 1024
MAX_PYTHON_MANIFEST_BYTES = 16 * 1024 * 1024
ORIGIN_PROBE = """
import importlib.util, json, pathlib, sys
def origin(name):
    spec = importlib.util.find_spec(name)
    if spec is None or spec.origin is None:
        raise SystemExit('required installed module is unavailable')
    return str(pathlib.Path(spec.origin).resolve())
print(json.dumps({'pythonExecutable':str(pathlib.Path(sys.executable).resolve()),
 'rookOrigin':origin('rook'), 'serviceOrigin':origin('rook.agent.chat.service_main'),
 'verifierOrigin':origin('rook.agent.chat.prime_runtime_artifact')}))
"""


def read_json(path: Path, max_bytes: int = MAX_JSON_BYTES) -> dict:
    artifact.require_direct_path(path)
    with path.open("rb") as stream:
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise artifact.RuntimeUnavailable("installed metadata exceeds byte limit")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise artifact.RuntimeUnavailable("duplicate installed metadata key")
            value[key] = item
        return value

    value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=unique)
    if type(value) is not dict:
        raise artifact.RuntimeUnavailable("installed metadata is not an object")
    return value


def git(source: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(source), *args], shell=False, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise artifact.RuntimeUnavailable("source Git custody refused")
    return result.stdout.strip()


def matches_blob(source: Path, commit: str, relative: str, actual: Path) -> bool:
    artifact.require_direct_path(actual)
    return git(source, "hash-object", "--no-filters", str(actual)) == git(source, "rev-parse", f"{commit}:{relative}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for key in ("rook-worktree", "install-root", "chat-service-manifest", "output"):
        parser.add_argument("--" + key, required=True, type=Path)
    parser.add_argument("--expected-rook-commit", required=True)
    parser.add_argument("--expected-verifier-commit", help="Reviewed verifier checkout; defaults to the product commit")
    args = parser.parse_args(argv)
    try:
        source = artifact.require_direct_path(args.rook_worktree, directory=True)
        installed = artifact.require_direct_path(args.install_root, directory=True)
        expected = args.expected_rook_commit
        verifier_commit = args.expected_verifier_commit or expected
        if (not re.fullmatch("[a-f0-9]{40}", expected) or not re.fullmatch("[a-f0-9]{40}", verifier_commit)
                or git(source, "rev-parse", "HEAD") != verifier_commit or git(source, "status", "--porcelain")
                or git(source, "rev-parse", f"{expected}^{{commit}}") != expected):
            raise artifact.RuntimeUnavailable("reviewed source identity or cleanliness differs")
        if args.output.exists() or args.output.is_symlink():
            raise artifact.RuntimeUnavailable("identity report already exists")
        for relative in ("mcp_server/src/rook", "installer/agent-assets/prime-skills/rook-full"):
            if git(source, "rev-parse", f"{expected}:{relative}") != git(source, "rev-parse", f"{verifier_commit}:{relative}"):
                raise artifact.RuntimeUnavailable("product or skill tree differs between reviewed commits")
        # Verify the Rook verifier itself against the admitted checkout before
        # using its result to attest to an incoming/installed Prime payload.
        if not matches_blob(source, verifier_commit, "scripts/verify-installed-rookchat-acp.py", Path(__file__)):
            raise artifact.RuntimeUnavailable("verifier implementation differs from reviewed source")
        if artifact.file_row(Path(artifact.__file__), "file") != artifact.file_row(source / "mcp_server/src/rook/agent/chat/prime_runtime_artifact.py", "file"):
            raise artifact.RuntimeUnavailable("verifier implementation differs from reviewed source")
        chat = read_json(args.chat_service_manifest)
        if set(chat) != {"pythonPath", "workingDirectory", "module", "owner", "pythonPathEntries", "environment"}:
            raise artifact.RuntimeUnavailable("chat-service manifest keys differ")
        if chat["module"] != "rook.agent.chat.service_main" or chat["owner"] != "rhino-panel" or chat["pythonPathEntries"] != []:
            raise artifact.RuntimeUnavailable("chat-service launch contract differs")
        python = artifact.require_direct_path(installed.parent / "venv/Scripts/python.exe")
        cwd = artifact.require_direct_path(installed / "mcp_server", directory=True)
        if Path(chat["pythonPath"]) != python or Path(chat["workingDirectory"]) != cwd:
            raise artifact.RuntimeUnavailable("installed interpreter or working directory differs")
        environment = chat["environment"]
        if type(environment) is not dict or not all(type(k) is str and type(v) is str for k, v in environment.items()):
            raise artifact.RuntimeUnavailable("chat environment is invalid")
        if (environment.get("ROOK_MODE") != "release" or Path(environment.get("ROOK_INSTALL_ROOT", "")) != installed
                or Path(environment.get("ROOK_DATA_DIR", "")) != installed.parent / "data"
                or any(v for k, v in environment.items() if k.upper() in {"PYTHONPATH", "PYTHONHOME"})):
            raise artifact.RuntimeUnavailable("chat runtime paths or Python overrides differ")
        wheel = read_json(installed / "python-runtime-manifest.json", MAX_PYTHON_MANIFEST_BYTES)
        release_version = tomllib.loads(git(source, "show", f"{expected}:mcp_server/pyproject.toml"))["project"]["version"]
        if wheel.get("rook_git_sha") != expected or wheel.get("release_version") != release_version:
            raise artifact.RuntimeUnavailable("installed wheel source identity differs")
        probe_env = {k: v for k, v in os.environ.items() if k.upper() not in {"PYTHONHOME", "PYTHONPATH"}}
        probe_env.update({k: v for k, v in environment.items() if k.upper() not in {"PYTHONHOME", "PYTHONPATH"}})
        probe = subprocess.run([str(python), "-I", "-B", "-c", ORIGIN_PROBE], shell=False, cwd=cwd,
                               env=probe_env, capture_output=True, text=True, timeout=10)
        if probe.returncode != 0 or len(probe.stdout.encode("utf-8")) > MAX_JSON_BYTES:
            raise artifact.RuntimeUnavailable("installed import-origin probe failed")
        origins = json.loads(probe.stdout)
        site = python.parent.parent / "Lib/site-packages"
        expected_origins = {
            "pythonExecutable": python, "rookOrigin": site / "rook/__init__.py",
            "serviceOrigin": site / "rook/agent/chat/service_main.py",
            "verifierOrigin": site / "rook/agent/chat/prime_runtime_artifact.py",
        }
        if type(origins) is not dict or set(origins) != set(expected_origins):
            raise artifact.RuntimeUnavailable("installed origin response is incomplete")
        for key, path in expected_origins.items():
            if type(origins[key]) is not str or Path(origins[key]) != artifact.require_direct_path(path):
                raise artifact.RuntimeUnavailable("installed module origin differs")
        source_files = git(source, "ls-tree", "-r", "--name-only", "-z", expected, "--", "mcp_server/src/rook").split("\0")
        for relative in filter(None, source_files):
            target = site / Path(relative).relative_to("mcp_server/src")
            if artifact.file_row(source / relative, "file") != artifact.file_row(target, "file"):
                raise artifact.RuntimeUnavailable("installed Rook package differs from source")
        prime = installed / "prime"
        runtime_id = artifact.read_current_runtime_id(prime)
        verified = artifact.verify_runtime_payload(prime / "runtimes" / runtime_id, runtime_id)
        skill_rows = artifact.payload_rows(source / "installer/agent-assets/prime-skills/rook-full")
        installed_skill = artifact.payload_rows(verified.root / "skills/rook-full")
        if skill_rows != installed_skill:
            raise artifact.RuntimeUnavailable("installed Rook skill differs from reviewed source")
        if artifact.read_current_runtime_id(prime) != runtime_id or git(source, "rev-parse", "HEAD") != verifier_commit or git(source, "status", "--porcelain"):
            raise artifact.RuntimeUnavailable("identity changed during installed verification")
        report = {
            "sourceCommit": expected, "verifierCommit": verifier_commit,
            "pointer": {"runtimeId": runtime_id}, "runtimeId": runtime_id,
            "manifestSha256": runtime_id, "paths": {
                "chatServiceManifest": str(args.chat_service_manifest.absolute()), "pythonExecutable": str(python),
                "rookOrigin": origins["rookOrigin"], "serviceOrigin": origins["serviceOrigin"],
                "primeExecutable": str(verified.root / "pi.exe"), "goalSkill": str(verified.root / "skills/goal"),
                "rookSkill": str(verified.root / "skills/rook-full"), "uvExecutable": str(verified.root / "tools/uv/uv.exe"),
                "pythonRuntime": str(verified.root / "dist/prime-agent-runtime"),
                "primeNotice": str(verified.root / "notices/prime-agent/LICENSE"),
            },
        }
        data = artifact.canonical_json_bytes(report)
        if len(data) > MAX_JSON_BYTES:
            raise artifact.RuntimeUnavailable("identity report exceeds byte limit")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        artifact.require_direct_path(args.output.parent, directory=True)
        with args.output.open("xb") as stream:
            stream.write(data)
        return 0
    except (OSError, ValueError, TypeError, KeyError, artifact.RuntimeUnavailable, subprocess.SubprocessError) as exc:
        print(f"installed_verification_refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
