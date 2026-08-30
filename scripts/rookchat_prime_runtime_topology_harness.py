#!/usr/bin/env python3
"""One-shot model-free qualification for Prime's direct RPC runtime.

This file is intentionally not part of the repeatable test suite. Gate 7A reviews
its bytes before either entry point may be executed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from rook.agent.chat.prime_runtime_contract import (
    build_package_manifest,
    canonical_json_bytes,
    verify_prime_bundle_manifest,
)


CONTROL_TIMEOUT_SECONDS = 30.0
PREPARE_TIMEOUT_SECONDS = 900.0
CLOSE_TIMEOUT_SECONDS = 10.0
STALE_LEASE_RECOVERY_SECONDS = 12.0
MAX_RPC_ROW_BYTES = 64 * 1024 * 1024
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_ENTRY_POINTS = ("direct-vertical", "lease-sequence")
_INTERNAL_LEASE_NAMES = frozenset(
    {
        "PRIME_AGENT_INTERNAL_SESSION_LEASES",
        "PRIME_AGENT_INTERNAL_SESSION_LEASE_OWNER_ID",
    }
)
_BOOTSTRAP_ENV_NAMES = (
    "SystemRoot",
    "WINDIR",
    "ComSpec",
    "PATHEXT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOME",
    "LOCALAPPDATA",
    "APPDATA",
)


class HarnessFailure(RuntimeError):
    def __init__(self, message: str, *, evidence: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.evidence = dict(evidence) if evidence is not None else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _require_sha256(value: str, label: str) -> str:
    if len(value) != 64 or any(character not in "0123456789ABCDEF" for character in value):
        raise HarnessFailure(f"{label} must be an uppercase SHA-256")
    return value


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _require_absolute_file(path: Path, label: str) -> Path:
    path = Path(path)
    if not path.is_absolute() or not path.is_file():
        raise HarnessFailure(f"{label} must be an existing absolute file")
    if path.is_symlink():
        raise HarnessFailure(f"{label} must not be a symlink")
    return path.resolve(strict=True)


@dataclass(frozen=True)
class HarnessRoots:
    root: Path
    agent: Path
    sessions: Path
    data: Path
    packages: Path
    kernel: Path
    evidence: Path

    @classmethod
    def create(cls, root: Path) -> "HarnessRoots":
        root = Path(root)
        if not root.is_absolute():
            root = root.resolve(strict=False)
        if root.exists():
            raise HarnessFailure("run root must not already exist")
        root.mkdir(parents=True, exist_ok=False)
        roots = cls(
            root=root.resolve(strict=True),
            agent=(root / "agent").resolve(strict=False),
            sessions=(root / "sessions").resolve(strict=False),
            data=(root / "data").resolve(strict=False),
            packages=(root / "packages").resolve(strict=False),
            kernel=(root / "kernel").resolve(strict=False),
            evidence=(root / "evidence").resolve(strict=False),
        )
        for directory in (
            roots.agent,
            roots.sessions,
            roots.data,
            roots.packages,
            roots.evidence,
        ):
            directory.mkdir(parents=True, exist_ok=False)
        return roots


@dataclass(frozen=True)
class StagedSkill:
    skill_path: Path
    manifest_bytes: bytes
    manifest_sha256: str


def stage_skill_package(source_skill_path: Path, destination_root: Path) -> StagedSkill:
    source_skill_path = _require_absolute_file(Path(source_skill_path), "skill path")
    if source_skill_path.name != "SKILL.md":
        raise HarnessFailure("skill path must name SKILL.md")
    source_root = source_skill_path.parent
    manifest = build_package_manifest(source_root)
    manifest_bytes = canonical_json_bytes(manifest)
    destination_root = Path(destination_root).resolve(strict=False)
    if destination_root.exists():
        raise HarnessFailure("staged skill destination already exists")
    destination_root.mkdir(parents=True, exist_ok=False)
    try:
        for member in manifest["files"]:
            relative = Path(*member["path"].split("/"))
            destination = destination_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((source_root / relative).read_bytes())
        if canonical_json_bytes(build_package_manifest(destination_root)) != manifest_bytes:
            raise HarnessFailure("staged skill bytes do not reproduce the source manifest")
    except BaseException:
        shutil.rmtree(destination_root, ignore_errors=True)
        raise
    return StagedSkill(
        skill_path=(destination_root / "SKILL.md").resolve(strict=True),
        manifest_bytes=manifest_bytes,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest().upper(),
    )


@dataclass(frozen=True)
class HarnessConfiguration:
    entry_point: str
    roots: HarnessRoots
    node_path: Path
    node_sha256: str
    prime_dist_root: Path
    bundle_manifest_path: Path
    bundle_manifest_sha256: str
    uv_path: Path
    uv_sha256: str
    model_selector: str
    goal_skill_path: Path
    rook_skill_path: Path
    goal_skill_manifest_sha256: str
    rook_skill_manifest_sha256: str


def build_child_environment(
    base_environment: Mapping[str, str],
    *,
    roots: HarnessRoots,
    uv_path: Path,
    support_path_entries: Sequence[Path],
) -> dict[str, str]:
    uv_path = _require_absolute_file(Path(uv_path), "uv path")
    environment: dict[str, str] = {}
    for name in _BOOTSTRAP_ENV_NAMES:
        value = base_environment.get(name)
        if value:
            environment[name] = value

    path_entries = [uv_path.parent.resolve(strict=True)]
    for entry in support_path_entries:
        resolved = Path(entry).resolve(strict=False)
        if resolved not in path_entries:
            path_entries.append(resolved)
    environment.update(
        {
            "PATH": os.pathsep.join(str(path) for path in path_entries),
            "PRIME_AGENT_CODING_AGENT_DIR": str(roots.agent),
            "PRIME_AGENT_SESSION_DIR": str(roots.sessions),
            "PRIME_AGENT_KERNEL_VENV": str(roots.kernel),
            "PRIME_AGENT_INSTALL_UV": "0",
            "XDG_DATA_HOME": str(roots.data),
        }
    )
    if any(name in environment for name in _INTERNAL_LEASE_NAMES):
        raise HarnessFailure("Prime internal lease authority leaked into child environment")
    return environment


def build_prime_argv(
    *,
    node_path: Path,
    cli_path: Path,
    session_root: Path,
    model_selector: str,
    goal_skill_path: Path,
    rook_skill_path: Path,
    resume_session_file: Path | None = None,
) -> tuple[str, ...]:
    if not model_selector or model_selector.count("/") != 1:
        raise HarnessFailure("model selector must use provider/model syntax")
    argv = [
        str(Path(node_path)),
        str(Path(cli_path)),
        "--mode",
        "rpc",
        "--rpc-runtime",
        "in-process",
        "--offline",
        "--model",
        model_selector,
        "--tools",
        "ipython",
        "--no-extensions",
        "--no-skills",
        "--skill",
        str(Path(goal_skill_path)),
        "--skill",
        str(Path(rook_skill_path)),
        "--no-context-files",
        "--no-prompt-templates",
        "--session-dir",
        str(Path(session_root)),
    ]
    if resume_session_file is not None:
        argv.extend(["--resume", str(Path(resume_session_file))])
    if any(argument == "--api-key" or argument.startswith("--api-key=") for argument in argv):
        raise HarnessFailure("API-key launch arguments are prohibited")
    return tuple(argv)


def admit_session_file(session_root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value:
        raise HarnessFailure("sessionFile must be a nonempty absolute path")
    root = Path(session_root).resolve(strict=True)
    candidate = Path(value)
    if not candidate.is_absolute() or not candidate.is_file():
        raise HarnessFailure("sessionFile must be an existing absolute file")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise HarnessFailure("sessionFile must remain beneath the isolated session root") from exc
    return resolved


def runtime_control_commands() -> tuple[dict[str, Any], ...]:
    return (
        {"id": "task7-get-state", "type": "get_state"},
        {
            "id": "task7-set-depth",
            "type": "set_rlm_max_depth",
            "maxDepth": 0,
            "global": False,
        },
        {"id": "task7-get-depth", "type": "get_rlm_max_depth_status"},
        {"id": "task7-prepare", "type": "prepare_ipython_runtime"},
    )


def persist_session_file(
    child: "OwnedPrimeProcess",
    session_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    state = _success_data(
        child.command(runtime_control_commands()[0], CONTROL_TIMEOUT_SECONDS),
        "get_state",
    )
    depth = _success_data(
        child.command(runtime_control_commands()[1], CONTROL_TIMEOUT_SECONDS),
        "set_rlm_max_depth",
    )
    if depth != {"maxDepth": 0, "source": "chat"}:
        raise HarnessFailure("chat-local RLM depth zero was not persisted")
    session_file = admit_session_file(session_root, state.get("sessionFile"))
    session_id = state.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        raise HarnessFailure("get_state omitted a nonempty sessionId")
    return state, depth, {
        "sessionId": session_id,
        "sessionFile": str(session_file),
    }


def require_session_continuity(
    observed: Mapping[str, Any],
    expected: Mapping[str, Any],
    session_root: Path,
) -> dict[str, str]:
    observed_id = observed.get("sessionId")
    expected_id = expected.get("sessionId")
    if not isinstance(observed_id, str) or observed_id != expected_id:
        raise HarnessFailure("reopened sessionId does not match the original owner")
    observed_file = admit_session_file(session_root, observed.get("sessionFile"))
    expected_file = admit_session_file(session_root, expected.get("sessionFile"))
    if observed_file != expected_file:
        raise HarnessFailure("reopened sessionFile does not match the original owner")
    return {"sessionId": observed_id, "sessionFile": str(observed_file)}


def require_no_daemon_artifacts(agent_root: Path) -> None:
    agent_root = Path(agent_root)
    artifacts = [
        agent_root / "daemon-workers",
        agent_root / "daemon-update-restarts",
        agent_root / "daemon-update-restart.json",
    ]
    logs = agent_root / "logs"
    if logs.is_dir():
        artifacts.extend(logs.glob("prime-agent-daemon.*"))
    if any(path.exists() for path in artifacts):
        raise HarnessFailure("isolated agent root contains a daemon artifact")


class OwnedPrimeProcess:
    def __init__(
        self,
        *,
        argv: tuple[str, ...],
        environment: Mapping[str, str],
        cwd: Path,
        generation: int,
    ) -> None:
        self.argv = argv
        self.environment = dict(environment)
        self.cwd = cwd
        self.generation = generation
        self.process: subprocess.Popen[str] | None = None
        self.rows: list[dict[str, Any]] = []
        self.stderr: list[str] = []
        self._stdout_queue: queue.Queue[str | None] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._close_record: dict[str, Any] | None = None

    @property
    def close_record(self) -> dict[str, Any] | None:
        return dict(self._close_record) if self._close_record is not None else None

    def start(self) -> None:
        if self.process is not None:
            raise HarnessFailure("owned Prime process already started")
        self.process = subprocess.Popen(
            list(self.argv),
            cwd=str(self.cwd),
            env=self.environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            bufsize=1,
            creationflags=CREATE_NO_WINDOW,
        )
        try:
            def read_stdout() -> None:
                assert self.process is not None and self.process.stdout is not None
                try:
                    for line in self.process.stdout:
                        self._stdout_queue.put(line)
                finally:
                    self._stdout_queue.put(None)

            def read_stderr() -> None:
                assert self.process is not None and self.process.stderr is not None
                for line in self.process.stderr:
                    self.stderr.append(line.rstrip("\r\n"))

            self._threads = [
                threading.Thread(
                    target=read_stdout,
                    name=f"task7-stdout-{self.generation}",
                    daemon=True,
                ),
                threading.Thread(
                    target=read_stderr,
                    name=f"task7-stderr-{self.generation}",
                    daemon=True,
                ),
            ]
            for thread in self._threads:
                thread.start()
        except BaseException as start_error:
            try:
                self.close()
            except BaseException as cleanup_error:
                raise HarnessFailure(
                    f"Prime startup failed and exact child cleanup did not settle: {cleanup_error}"
                ) from start_error
            raise

    def command(self, command: Mapping[str, Any], timeout_seconds: float) -> dict[str, Any]:
        if self.process is None or self.process.stdin is None:
            raise HarnessFailure("Prime process is not running")
        request_id = command.get("id")
        if not isinstance(request_id, str) or not request_id:
            raise HarnessFailure("RPC command requires a fixed request id")
        encoded = _canonical_bytes(dict(command)) + b"\n"
        self.process.stdin.write(encoded.decode("ascii"))
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HarnessFailure(f"RPC command timed out: {command['type']}")
            try:
                line = self._stdout_queue.get(timeout=remaining)
            except queue.Empty as exc:
                raise HarnessFailure(f"RPC command timed out: {command['type']}") from exc
            if line is None:
                raise HarnessFailure(
                    f"Prime exited before RPC response: {command['type']}; stderr={self.stderr[-10:]}"
                )
            raw = line.encode("utf-8")
            if len(raw) > MAX_RPC_ROW_BYTES or not raw.endswith(b"\n"):
                raise HarnessFailure("Prime emitted an invalid or oversized JSONL row")
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise HarnessFailure("Prime emitted invalid JSON") from exc
            if not isinstance(row, dict):
                raise HarnessFailure("Prime RPC row must be an object")
            self.rows.append(row)
            if row.get("type") == "response" and row.get("id") == request_id:
                return row

    def close(self) -> dict[str, Any]:
        if self._close_record is not None:
            return dict(self._close_record)
        process = self.process
        if process is None:
            self._close_record = {"result": "not_started"}
            return dict(self._close_record)
        if process.returncode is not None:
            result = {"result": "already_exited", "returnCode": process.returncode}
        else:
            if process.stdin is not None and not process.stdin.closed:
                try:
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
            try:
                return_code = process.wait(timeout=CLOSE_TIMEOUT_SECONDS)
                result = {"result": "graceful", "returnCode": return_code}
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    return_code = process.wait(timeout=CLOSE_TIMEOUT_SECONDS)
                    result = {"result": "terminated_direct_handle", "returnCode": return_code}
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        return_code = process.wait(timeout=CLOSE_TIMEOUT_SECONDS)
                    except subprocess.TimeoutExpired as exc:
                        raise HarnessFailure("direct Prime child did not settle after kill") from exc
                    result = {"result": "killed_direct_handle", "returnCode": return_code}
        self._join_reader_threads()
        self._close_record = result
        return dict(result)

    def kill_without_disposal(self) -> dict[str, Any]:
        process = self.process
        if process is None:
            raise HarnessFailure("live lease holder is unavailable")
        process.kill()
        try:
            return_code = process.wait(timeout=CLOSE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            raise HarnessFailure("controlled owner crash did not settle")
        self._join_reader_threads()
        self._close_record = {
            "result": "controlled_crash_exit",
            "returnCode": return_code,
        }
        return dict(self._close_record)

    def _join_reader_threads(self) -> None:
        for thread in self._threads:
            if thread.ident is not None:
                thread.join(timeout=1.0)
        if any(thread.ident is not None and thread.is_alive() for thread in self._threads):
            raise HarnessFailure("Prime reader thread did not stop after child settlement")


def owned_process_evidence(child: OwnedPrimeProcess) -> dict[str, Any]:
    process = child.process
    return {
        "generation": child.generation,
        "argv": list(child.argv),
        "pid": process.pid if process is not None else None,
        "returnCode": process.returncode if process is not None else None,
        "rows": [dict(row) for row in child.rows],
        "stderr": list(child.stderr),
        "close": child.close_record,
    }


def _success_data(response: Mapping[str, Any], command: str) -> dict[str, Any]:
    if response.get("success") is not True or response.get("command") != command:
        raise HarnessFailure(f"Prime control failed: {command}: {response}")
    data = response.get("data")
    if not isinstance(data, dict):
        raise HarnessFailure(f"Prime control returned no data: {command}")
    return data


def validate_runtime_preparation(
    preparation: Mapping[str, Any],
    *,
    kernel_root: Path,
    goal_skill_path: Path,
    rook_skill_path: Path,
) -> dict[str, Path]:
    interpreter_value = preparation.get("interpreterPath")
    goal_value = preparation.get("goalFile")
    rook_value = preparation.get("rookFullFile")
    if not isinstance(interpreter_value, str):
        raise HarnessFailure("runtime preparation omitted interpreterPath")
    if not isinstance(goal_value, str):
        raise HarnessFailure("runtime preparation omitted goal import origin")
    if not isinstance(rook_value, str):
        raise HarnessFailure("runtime preparation omitted Rook import origin")
    interpreter = _require_absolute_file(Path(interpreter_value), "prepared interpreter")
    goal_file = _require_absolute_file(Path(goal_value), "goal import")
    rook_file = _require_absolute_file(Path(rook_value), "Rook import")
    try:
        interpreter.relative_to(Path(kernel_root).resolve(strict=True))
    except ValueError as exc:
        raise HarnessFailure("prepared interpreter escaped the contract kernel root") from exc
    for label, module_path, skill_path in (
        ("goal", goal_file, goal_skill_path),
        ("Rook", rook_file, rook_skill_path),
    ):
        try:
            module_path.relative_to(Path(skill_path).parent.resolve(strict=True))
        except ValueError as exc:
            raise HarnessFailure(f"{label} import resolved outside admitted package") from exc
    if preparation.get("callables") != {"search": True, "read": True, "call": True}:
        raise HarnessFailure("Rook payload-first callables were not all prepared")
    return {
        "interpreter": interpreter,
        "goalFile": goal_file,
        "rookFullFile": rook_file,
    }


def _launch(
    config: HarnessConfiguration,
    environment: Mapping[str, str],
    generation: int,
    resume: Path | None,
) -> OwnedPrimeProcess:
    return OwnedPrimeProcess(
        argv=build_prime_argv(
            node_path=config.node_path,
            cli_path=config.prime_dist_root / "bundle" / "cli.js",
            session_root=config.roots.sessions,
            model_selector=config.model_selector,
            goal_skill_path=config.goal_skill_path,
            rook_skill_path=config.rook_skill_path,
            resume_session_file=resume,
        ),
        environment=environment,
        cwd=config.roots.root,
        generation=generation,
    )


def require_graceful_close(child: OwnedPrimeProcess, label: str) -> dict[str, Any]:
    record = child.close()
    if record != {"result": "graceful", "returnCode": 0}:
        raise HarnessFailure(f"{label} did not close gracefully with exit code zero: {record}")
    return record


def _expect_lease_refusal(
    child: OwnedPrimeProcess,
    expected_session_file: Path,
) -> dict[str, Any]:
    try:
        response = child.command(
            {"id": f"task7-refusal-{child.generation}", "type": "get_state"},
            CONTROL_TIMEOUT_SECONDS,
        )
    except (HarnessFailure, BrokenPipeError, OSError) as exc:
        close_record = child.close()
        if close_record.get("result") not in {"already_exited", "graceful"} or not isinstance(
            close_record.get("returnCode"), int
        ) or close_record["returnCode"] == 0:
            raise HarnessFailure(
                f"lease contender did not terminate with a refusal: {close_record}"
            ) from exc
        expected = {
            "type": "rpc_startup_error",
            "code": "session_already_active",
            "sessionPath": str(Path(expected_session_file).resolve(strict=True)),
        }
        matches: list[dict[str, Any]] = []
        for line in child.stderr:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row == expected:
                matches.append(row)
        if len(matches) != 1:
            raise HarnessFailure(
                "contender did not emit the exact session lease refusal for the canonical session file"
            ) from exc
        return {
            "refused": True,
            "outcome": matches[0],
            "close": close_record,
            "stderr": list(child.stderr),
        }
    raise HarnessFailure(f"lease contender unexpectedly admitted get_state: {response}")


def run_direct_vertical(config: HarnessConfiguration) -> dict[str, Any]:
    environment = _build_runtime_environment(config)
    require_no_daemon_artifacts(config.roots.agent)
    child = _launch(config, environment, generation=1, resume=None)
    result: dict[str, Any] | None = None
    try:
        child.start()
        _state, set_depth, identity = persist_session_file(child, config.roots.sessions)
        session_file = Path(identity["sessionFile"])
        get_depth_response = child.command(runtime_control_commands()[2], CONTROL_TIMEOUT_SECONDS)
        get_depth = _success_data(get_depth_response, "get_rlm_max_depth_status")
        if set_depth != {"maxDepth": 0, "source": "chat"} or get_depth != set_depth:
            raise HarnessFailure("chat-local RLM depth zero was not retained")
        preparation_response = child.command(
            runtime_control_commands()[3],
            PREPARE_TIMEOUT_SECONDS,
        )
        prepared = _success_data(preparation_response, "prepare_ipython_runtime")
        imports = validate_runtime_preparation(
            prepared,
            kernel_root=config.roots.kernel,
            goal_skill_path=config.goal_skill_path,
            rook_skill_path=config.rook_skill_path,
        )
        require_no_daemon_artifacts(config.roots.agent)
        result = {
            "entryPoint": config.entry_point,
            "argv": child.argv,
            "environmentNames": sorted(environment),
            "session": identity,
            "responses": [dict(row) for row in child.rows],
            "imports": {key: str(value) for key, value in imports.items()},
        }
    finally:
        close_record = child.close()
        require_no_daemon_artifacts(config.roots.agent)
    if result is None:
        raise HarnessFailure("direct vertical produced no result")
    result["close"] = require_graceful_close(child, "direct vertical owner")
    result["process"] = owned_process_evidence(child)
    return result


def run_lease_sequence(config: HarnessConfiguration) -> dict[str, Any]:
    environment = _build_runtime_environment(config)
    require_no_daemon_artifacts(config.roots.agent)
    records: list[dict[str, Any]] = []
    owned: list[OwnedPrimeProcess] = []
    generation = 0
    session_file: Path | None = None
    session_identity: dict[str, str] | None = None
    sequence_error: BaseException | None = None

    def launch(resume: Path | None) -> OwnedPrimeProcess:
        nonlocal generation
        generation += 1
        child = _launch(config, environment, generation, resume)
        owned.append(child)
        child.start()
        return child

    try:
        first = launch(None)
        _state, depth, session_identity = persist_session_file(first, config.roots.sessions)
        session_file = Path(session_identity["sessionFile"])
        records.append(
            {
                "phase": "first_session_persisted",
                "session": dict(session_identity),
                "rlmMaxDepth": depth,
            }
        )
        contender = launch(session_file)
        records.append(
            {
                "phase": "live_owner_refusal",
                **_expect_lease_refusal(contender, session_file),
            }
        )
        records.append(
            {
                "phase": "first_close",
                **require_graceful_close(first, "first owner"),
            }
        )

        reopened = launch(session_file)
        reopened_state = _success_data(
            reopened.command({"id": "task7-reopen-state", "type": "get_state"}, CONTROL_TIMEOUT_SECONDS),
            "get_state",
        )
        require_session_continuity(reopened_state, session_identity, config.roots.sessions)
        records.append(
            {
                "phase": "graceful_reopen_close",
                **require_graceful_close(reopened, "reopened owner"),
            }
        )

        holder = launch(session_file)
        holder_state = _success_data(
            holder.command({"id": "task7-holder-state", "type": "get_state"}, CONTROL_TIMEOUT_SECONDS),
            "get_state",
        )
        require_session_continuity(holder_state, session_identity, config.roots.sessions)
        detached_contender = launch(session_file)
        records.append(
            {
                "phase": "detached_live_owner_refusal",
                **_expect_lease_refusal(detached_contender, session_file),
            }
        )
        records.append(
            {
                "phase": "controlled_crash_owner",
                **holder.kill_without_disposal(),
            }
        )
        time.sleep(STALE_LEASE_RECOVERY_SECONDS)
        records.append(
            {
                "phase": "stale_lease_wait",
                "seconds": STALE_LEASE_RECOVERY_SECONDS,
            }
        )

        recovered = launch(session_file)
        recovered_state = _success_data(
            recovered.command({"id": "task7-recovered-state", "type": "get_state"}, CONTROL_TIMEOUT_SECONDS),
            "get_state",
        )
        require_session_continuity(recovered_state, session_identity, config.roots.sessions)
        records.append(
            {
                "phase": "stale_owner_recovery_close",
                **require_graceful_close(recovered, "recovered owner"),
            }
        )
    except BaseException as exc:
        sequence_error = exc
    finally:
        cleanup_errors: list[str] = []
        for child in reversed(owned):
            try:
                child.close()
            except BaseException as exc:
                cleanup_errors.append(
                    f"generation {child.generation}: {type(exc).__name__}: {exc}"
                )
        try:
            require_no_daemon_artifacts(config.roots.agent)
        except BaseException as exc:
            cleanup_errors.append(f"daemon artifacts: {type(exc).__name__}: {exc}")
        for child in owned:
            process = child.process
            if process is None or process.returncode is None or child.close_record is None:
                cleanup_errors.append(
                    f"generation {child.generation}: direct child did not settle"
                )

    evidence = {
        "entryPoint": config.entry_point,
        "session": dict(session_identity) if session_identity is not None else None,
        "records": records,
        "environmentNames": sorted(environment),
        "launches": [owned_process_evidence(child) for child in owned],
    }
    if sequence_error is not None or cleanup_errors:
        reasons: list[str] = []
        if sequence_error is not None:
            reasons.append(f"{type(sequence_error).__name__}: {sequence_error}")
        reasons.extend(cleanup_errors)
        raise HarnessFailure(
            "lease sequence failed: " + "; ".join(reasons),
            evidence=evidence,
        ) from sequence_error
    return evidence


def _build_runtime_environment(config: HarnessConfiguration) -> dict[str, str]:
    system_root = Path(os.environ.get("SystemRoot", "C:/Windows"))
    environment = build_child_environment(
        os.environ,
        roots=config.roots,
        uv_path=config.uv_path,
        support_path_entries=(system_root / "System32",),
    )
    if (config.roots.agent / "auth.json").exists():
        raise HarnessFailure("isolated agent root unexpectedly contains auth.json")
    require_no_daemon_artifacts(config.roots.agent)
    return environment


def _configuration(namespace: argparse.Namespace) -> HarnessConfiguration:
    node_path = _require_absolute_file(Path(namespace.node_path), "Node path")
    expected_node_sha256 = _require_sha256(namespace.node_sha256, "Node executable")
    if _sha256_file(node_path) != expected_node_sha256:
        raise HarnessFailure("Node SHA-256 does not match the frozen executable")
    prime_dist_root = Path(namespace.prime_dist_root).resolve(strict=True)
    bundle_manifest_path = _require_absolute_file(
        Path(namespace.prime_bundle_manifest),
        "Prime bundle manifest",
    )
    bundle = verify_prime_bundle_manifest(
        prime_dist_root,
        bundle_manifest_path,
        expected_manifest_sha256=namespace.prime_bundle_sha256,
    )
    if bundle.cli_path != (prime_dist_root / "bundle" / "cli.js").resolve(strict=True):
        raise HarnessFailure("Prime launch entry drifted from bundle/cli.js")
    uv_path = _require_absolute_file(Path(namespace.uv_path), "uv path")
    observed_uv_sha256 = _sha256_file(uv_path)
    if observed_uv_sha256 != namespace.uv_sha256:
        raise HarnessFailure("uv SHA-256 does not match the frozen executable")
    goal_skill_path = _require_absolute_file(Path(namespace.goal_skill), "goal skill")
    rook_skill_path = _require_absolute_file(Path(namespace.rook_skill), "Rook skill")
    expected_goal_manifest = _require_sha256(
        namespace.goal_skill_manifest_sha256,
        "goal skill manifest",
    )
    expected_rook_manifest = _require_sha256(
        namespace.rook_skill_manifest_sha256,
        "Rook skill manifest",
    )
    source_goal_manifest = canonical_json_bytes(build_package_manifest(goal_skill_path.parent))
    source_rook_manifest = canonical_json_bytes(build_package_manifest(rook_skill_path.parent))
    if hashlib.sha256(source_goal_manifest).hexdigest().upper() != expected_goal_manifest:
        raise HarnessFailure("goal skill manifest does not match admitted bytes")
    if hashlib.sha256(source_rook_manifest).hexdigest().upper() != expected_rook_manifest:
        raise HarnessFailure("Rook skill manifest does not match admitted bytes")

    roots = HarnessRoots.create(Path(namespace.run_root))
    goal_skill = stage_skill_package(
        goal_skill_path,
        roots.packages / "goal",
    )
    rook_skill = stage_skill_package(
        rook_skill_path,
        roots.packages / "rook-full",
    )
    if goal_skill.manifest_sha256 != expected_goal_manifest:
        raise HarnessFailure("staged goal skill manifest changed")
    if rook_skill.manifest_sha256 != expected_rook_manifest:
        raise HarnessFailure("staged Rook skill manifest changed")
    return HarnessConfiguration(
        entry_point=namespace.entry_point,
        roots=roots,
        node_path=node_path,
        node_sha256=expected_node_sha256,
        prime_dist_root=prime_dist_root,
        bundle_manifest_path=bundle_manifest_path,
        bundle_manifest_sha256=namespace.prime_bundle_sha256,
        uv_path=uv_path,
        uv_sha256=observed_uv_sha256,
        model_selector=namespace.model,
        goal_skill_path=goal_skill.skill_path,
        rook_skill_path=rook_skill.skill_path,
        goal_skill_manifest_sha256=goal_skill.manifest_sha256,
        rook_skill_manifest_sha256=rook_skill.manifest_sha256,
    )


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--node-path", required=True)
    parser.add_argument("--node-sha256", required=True)
    parser.add_argument("--prime-dist-root", required=True)
    parser.add_argument("--prime-bundle-manifest", required=True)
    parser.add_argument("--prime-bundle-sha256", required=True)
    parser.add_argument("--uv-path", required=True)
    parser.add_argument("--uv-sha256", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--goal-skill", required=True)
    parser.add_argument("--goal-skill-manifest-sha256", required=True)
    parser.add_argument("--rook-skill", required=True)
    parser.add_argument("--rook-skill-manifest-sha256", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="entry_point", required=True)
    for name in _ENTRY_POINTS:
        child = subparsers.add_parser(name)
        _add_common_arguments(child)
    setattr(parser, "_rook_entry_points", _ENTRY_POINTS)
    return parser


def entry_point_names(parser: argparse.ArgumentParser) -> tuple[str, ...]:
    return tuple(sorted(getattr(parser, "_rook_entry_points", ())))


def _write_result(config: HarnessConfiguration, record: Mapping[str, Any]) -> None:
    result = {
        "schema": "rook.qualification.prime_runtime_topology:v3",
        "transactionId": uuid.uuid4().hex,
        "primeBundleManifestSha256": config.bundle_manifest_sha256,
        "node": {"path": str(config.node_path), "sha256": config.node_sha256},
        "skillManifests": {
            "goal": config.goal_skill_manifest_sha256,
            "rookFull": config.rook_skill_manifest_sha256,
        },
        "uv": {"path": str(config.uv_path), "sha256": config.uv_sha256},
        "result": dict(record),
    }
    raw = _canonical_bytes(result)
    destination = config.roots.evidence / "result.json"
    pending = destination.with_suffix(".json.pending")
    with pending.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, destination)


def main(argv: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(argv)
    config = _configuration(namespace)
    try:
        if config.entry_point == "direct-vertical":
            result = run_direct_vertical(config)
        elif config.entry_point == "lease-sequence":
            result = run_lease_sequence(config)
        else:  # pragma: no cover - argparse closes this shape
            raise HarnessFailure("unknown harness entry point")
    except BaseException as exc:
        failure_record: dict[str, Any] = {
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
        if isinstance(exc, HarnessFailure) and exc.evidence is not None:
            failure_record["evidence"] = exc.evidence
        _write_result(
            config,
            failure_record,
        )
        return 1
    _write_result(config, {"status": "passed", **result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
