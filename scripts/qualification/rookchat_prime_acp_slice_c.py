"""One externally approved image exchange, not a live panel/manager qualification."""
from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import json
import re
import stat
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Match the isolated operator entrypoint without consulting ambient Python paths.
REPO = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "mcp_server/src"))

from acp.schema import TextContentBlock
from rook.agent.chat.acp_conversation import DirectAcpProcessFactory, PreparedDirectAcpLaunch
from rook.agent.chat.acp_images import validate_images
from rook.agent.chat.acp_presentation import BoundedPromptProjection, PresentationQueue, PromptGeneration
from rook.agent.chat.acp_storage import OpenClaim, ProvisionalAssociation, RookBinding
from rook.agent.chat.prime_runtime import load_and_verify_runtime
from rook.runtime_paths import AcpDataPaths, RuntimePaths
from scripts.qualification.rookchat_prime_acp_common import (
    EvidenceRoot, QualificationRefused, canonical_json_bytes, sha256_bytes,
    _closed, _unique_object, _git, verify_source_custody,
)


LIMITS = {"operationSeconds": 180, "initializeSeconds": 60, "promptSeconds": 90,
          "cancelSeconds": 10, "cleanupSeconds": 60, "answerBytes": 64,
          "evidenceFiles": 16, "evidenceFileBytes": 1048576, "evidenceTotalBytes": 4194304}
RUNNER_PATH = "scripts/qualification/rookchat_prime_acp_slice_c.py"
COMMON_PATH = "scripts/qualification/rookchat_prime_acp_common.py"
TEST_PATH = "mcp_server/tests/test_rookchat_prime_acp_slice_c.py"


def load_protocol(path: Path, repo: Path) -> dict:
    path = checked_path(str(path), regular=True)
    match = re.fullmatch(r"rookchat-prime-acp-slice-c-v([1-9][0-9]*)\.json", path.name)
    if not match or path.parent != repo / "scripts/qualification/protocols":
        raise QualificationRefused("protocol origin differs")
    with path.open("rb") as stream:
        raw = stream.read(131073)
    if len(raw) > 131072:
        raise QualificationRefused("protocol too large")
    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError) as exc:
        raise QualificationRefused("invalid protocol JSON") from exc
    _closed(value, {"schemaVersion", "executionVersion", "implementationCommit", "sourceInputs",
                    "runtime", "model", "reasoning", "authDir", "executionRoot", "evidenceRoot",
                    "conversationId", "image", "prompt", "limits"}, "Slice C")
    if (canonical_json_bytes(value) != raw or type(value["schemaVersion"]) is not int
            or value["schemaVersion"] != 1 or type(value["executionVersion"]) is not int
            or str(value["executionVersion"]) != match.group(1)
            or value["model"] != "openai-codex/gpt-5.4-mini" or value["reasoning"] != "low"
            or not isinstance(value["implementationCommit"], str)
            or not re.fullmatch(r"[0-9a-f]{40}", value["implementationCommit"])
            or not isinstance(value["conversationId"], str)
            or not re.fullmatch(r"[0-9a-f]{32}", value["conversationId"])):
        raise QualificationRefused("protocol identity or policy differs")
    _closed(value["limits"], set(LIMITS), "limits")
    if value["limits"] != LIMITS or any(type(v) is not int for v in value["limits"].values()):
        raise QualificationRefused("unfrozen limits")
    _closed(value["runtime"], {"installRoot", "runtimeId"}, "runtime")
    if not isinstance(value["runtime"]["runtimeId"], str) or not re.fullmatch(r"[A-F0-9]{64}", value["runtime"]["runtimeId"]):
        raise QualificationRefused("invalid runtime identity")
    for label in ("authDir", "executionRoot", "evidenceRoot"):
        if not isinstance(value[label], str):
            raise QualificationRefused("invalid root")
        checked_path(value[label])
    checked_path(value["runtime"]["installRoot"])
    if type(value["sourceInputs"]) is not list or len(value["sourceInputs"]) > 128:
        raise QualificationRefused("invalid source rows")
    for row in [*value["sourceInputs"], value["image"], value["prompt"]]:
        _closed(row, {"path", "bytes", "sha256"}, "input")
        if (type(row["path"]) is not str or Path(row["path"]).is_absolute()
                or ".." in Path(row["path"]).parts or "\\" in row["path"]
                or type(row["bytes"]) is not int or not 0 < row["bytes"] <= 4 * 1024 * 1024
                or type(row["sha256"]) is not str or not re.fullmatch(r"[A-F0-9]{64}", row["sha256"])):
            raise QualificationRefused("invalid input row")
    names = [row["path"] for row in value["sourceInputs"]]
    if names != sorted(set(names)):
        raise QualificationRefused("source rows must be unique and ordered")
    return value


async def admit(path: Path, repo: Path, expected_commit: str, expected_hash: str) -> tuple[dict, PreparedImage]:
    repo = checked_path(str(repo))
    path = checked_path(str(path), regular=True)
    with path.open("rb") as stream:
        raw = stream.read(131073)
    if len(raw) > 131072 or sha256_bytes(raw) != expected_hash:
        raise QualificationRefused("protocol hash differs")
    protocol = load_protocol(path, repo)
    if not re.fullmatch(r"[a-f0-9]{40}", expected_commit):
        raise QualificationRefused("expected qualification commit required")
    if (await _git(repo, "rev-parse", "HEAD")).stdout.strip() != expected_commit:
        raise QualificationRefused("qualification HEAD differs")
    await verify_source_custody(repo, protocol["implementationCommit"])
    rows = protocol["sourceInputs"]
    names = {row["path"] for row in rows}
    required = {RUNNER_PATH, COMMON_PATH, TEST_PATH,
                "src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs"}
    # Include the loaded Rook modules, not an independently invented dependency list.
    for name, module in list(sys.modules.items()):
        if name == "rook" or name.startswith("rook."):
            origin = getattr(module, "__file__", None)
            if origin is None:
                raise QualificationRefused("product import origin unavailable")
            origin = checked_path(origin, regular=True)
            if not origin.is_relative_to(repo / "mcp_server/src/rook"):
                raise QualificationRefused("product import origin differs")
            required.add(origin.relative_to(repo).as_posix())
    if not required <= names or Path(__file__).resolve() != repo / RUNNER_PATH:
        raise QualificationRefused("qualification source set differs")
    common = sys.modules["scripts.qualification.rookchat_prime_acp_common"]
    if Path(common.__file__).resolve() != repo / COMMON_PATH:
        raise QualificationRefused("common module origin differs")
    for row in rows:
        input_bytes(repo, row)
    # As in precontact admission, executable qualification bytes use raw Git
    # identity; existing product inputs retain their explicitly frozen byte hashes.
    relatives = [path.relative_to(repo).as_posix(), RUNNER_PATH, COMMON_PATH, TEST_PATH,
                 "src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs",
                 protocol["image"]["path"], protocol["prompt"]["path"]]
    for relative in sorted(set(relatives)):
        local = checked_path(str(repo / relative), regular=True)
        actual = (await _git(repo, "hash-object", "--no-filters", str(local))).stdout.strip()
        recorded = (await _git(repo, "rev-parse", f"{expected_commit}:{relative}")).stdout.strip()
        if actual != recorded:
            raise QualificationRefused("raw qualification blob differs")
    contract = load_and_verify_runtime(Path(protocol["runtime"]["installRoot"]), protocol["runtime"]["runtimeId"])
    prepared = prepare(protocol, repo, contract)
    return protocol, prepared


@dataclass(frozen=True)
class PreparedImage:
    launch: PreparedDirectAcpLaunch
    paths: AcpDataPaths
    blocks: list[Any]
    execution_root: Path


def checked_path(value: str, *, regular: bool = False) -> Path:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise QualificationRefused("noncanonical path")
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise QualificationRefused("linked path")
    if regular and not path.is_file():
        raise QualificationRefused("regular input required")
    return path.resolve(strict=regular)


def input_bytes(repo: Path, row: dict) -> bytes:
    relative = Path(row["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise QualificationRefused("input escapes source")
    path = checked_path(str(repo / relative), regular=True)
    if not path.is_relative_to(repo):
        raise QualificationRefused("input escapes source")
    with path.open("rb") as stream:
        data = stream.read(row["bytes"] + 1)
    if len(data) != row["bytes"] or sha256_bytes(data) != row["sha256"]:
        raise QualificationRefused("frozen input changed")
    return data


def prepare(protocol: dict, repo: Path, contract: Any) -> PreparedImage:
    execution = checked_path(protocol["executionRoot"])
    evidence = checked_path(protocol["evidenceRoot"])
    auth = checked_path(protocol["authDir"])
    if execution.exists() or evidence.exists():
        raise QualificationRefused("generation already exists")
    if not auth.is_dir():
        raise QualificationRefused("approved private directory unavailable")
    protected = (auth, repo.resolve(), checked_path(protocol["runtime"]["installRoot"]))
    for writable in (execution, evidence):
        for other in (*protected, evidence if writable == execution else execution):
            if writable.is_relative_to(other) or other.is_relative_to(writable):
                raise QualificationRefused("qualification roots overlap")
    if contract.runtime_id != protocol["runtime"]["runtimeId"]:
        raise QualificationRefused("runtime identity differs")
    data = input_bytes(repo, protocol["image"])
    text = input_bytes(repo, protocol["prompt"]).decode("utf-8", "strict")
    image = {"file_name": "slice-c-image-01.png", "mime_type": "image/png",
             "base64_data": base64.b64encode(data).decode("ascii")}
    wire = canonical_json_bytes({"text": text, "images": [image]})
    (validated,) = validate_images([image], encoded_http_body_bytes=len(wire))
    paths = AcpDataPaths.from_runtime_paths(RuntimePaths(
        mode="dev", install_root=repo, data_root=execution / "rook-data",
        logs_root=execution / "logs", runtime_root=execution,
        mcp_server_dir=repo / "mcp_server", repo_root=repo))
    # This inert binding only satisfies the existing launch value type. No manager
    # or Rook server consumes it; the ACP declaration below is explicitly empty.
    association = ProvisionalAssociation(
        protocol["conversationId"], str(paths.session_path(protocol["conversationId"])),
        str(execution / "project"), contract.runtime_id,
        RookBinding("readonly", "11111111-1111-1111-1111-111111111111", 1, 1),
        protocol["model"], protocol["reasoning"])
    environment = {
        "SYSTEMROOT": "C:/Windows", "WINDIR": "C:/Windows",
        "COMSPEC": "C:/Windows/System32/cmd.exe", "PATH": "C:/Windows/System32",
        "PATHEXT": ".COM;.EXE;.BAT;.CMD", "CI": "1",
        "HOME": str(execution / "home"), "USERPROFILE": str(execution / "profile"),
        "APPDATA": str(execution / "appdata"), "LOCALAPPDATA": str(execution / "localappdata"),
        "TEMP": str(execution / "temp"), "TMP": str(execution / "temp"),
        "ROOK_DATA_DIR": str(execution / "rook-data"),
        "PRIME_AGENT_CODING_AGENT_DIR": str(auth),
    }
    launch = DirectAcpProcessFactory(environment).prepare(contract, association, False)
    if launch.launch.environment["PRIME_AGENT_CODING_AGENT_DIR"] != str(auth):
        raise QualificationRefused("private directory handoff differs")
    return PreparedImage(launch, paths, [TextContentBlock(type="text", text=text), validated.acp_block], execution)


def returned_usage(response: Any) -> dict | None:
    usage = getattr(response, "usage", None)
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    if not isinstance(usage, dict):
        return None
    selected = {key: usage[key] for key in ("input_tokens", "output_tokens", "total_tokens")
                if key in usage and type(usage[key]) is int and 0 <= usage[key] < 2**63}
    return selected or None


async def run_image(protocol: dict, prepared: PreparedImage) -> dict:
    limits = protocol["limits"]
    result = {"outcome": "failed", "failure": None, "usage": None, "answerAccepted": False,
              "cleanup": {"clean": False, "child_exit_observed": False}, "cancelAttempted": False,
              "assistantAnswer": None, "assistantAnswerBytes": 0, "assistantAnswerOmitted": False,
              "stopReason": None}
    process = None
    pending = None
    projection = None
    claim = None
    settled = False
    protocol_failed = False
    try:
        async with asyncio.timeout(limits["operationSeconds"]):
            prepared.paths.create_roots()
            for name in ("home", "profile", "appdata", "localappdata", "temp", "project"):
                (prepared.execution_root / name).mkdir(exist_ok=False)
            session_path = prepared.paths.session_path(protocol["conversationId"])
            claim = OpenClaim.acquire(prepared.paths.claims_root, str(session_path))
            async with asyncio.timeout(limits["initializeSeconds"]):
                process = await prepared.launch.start(claim, launch_generation=1)
                initialized = await process.initialize()
                if not initialized.image_supported:
                    raise QualificationRefused("image capability unavailable")
                await process.new_session(cwd=prepared.launch.launch.cwd, mcp_servers=[])
            generation = PromptGeneration(1, process.session_id, "slice-c-image-1")
            projection = BoundedPromptProjection(generation=generation, queue=PresentationQueue(),
                                                 user_text=prepared.blocks[0].text)
            pending = asyncio.create_task(process.prompt(prepared.blocks, generation=generation, projection=projection))
            response = await asyncio.wait_for(asyncio.shield(pending), limits["promptSeconds"])
            result["stopReason"] = response.stop_reason
            settled = True
            result["usage"] = returned_usage(response)
            projection.close_producer()
            turn = projection.finalize(response.stop_reason)
            if (process.transport_failure.is_set() or projection.overflowed
                    or response.stop_reason != "end_turn" or turn.tool_cards
                    or turn.assistant_original_bytes > limits["answerBytes"]
                    or turn.assistant_text.strip() != "blue"):
                raise QualificationRefused("image result refused")
            result["answerAccepted"] = True
    except (TimeoutError, asyncio.CancelledError):
        result["failure"] = "deadline"
    except QualificationRefused:
        result["failure"] = "application_refused"
    except BaseException:
        # Exception text and raw protocol/provider output may contain credentials.
        protocol_failed = True
        result["failure"] = "execution_failed"
    finally:
        if process is not None:
            if pending is not None and not settled and not protocol_failed and not process.transport_failure.is_set():
                try:
                    async with asyncio.timeout(limits["cancelSeconds"]):
                        if not pending.done():
                            result["cancelAttempted"] = True
                            await process.cancel()
                        response = await asyncio.shield(pending)
                        result["stopReason"] = response.stop_reason
                        settled = True
                        result["usage"] = returned_usage(response)
                except BaseException:
                    result["failure"] = "cancellation_uncertain"
            # Only a confirmed prompt response permits another ACP request.
            # Observing child exit later cannot establish prompt settlement.
            send_close = settled and not protocol_failed and not process.transport_failure.is_set()
            try:
                retired = await asyncio.wait_for(process.retire(send_close=send_close), limits["cleanupSeconds"])
                result["cleanup"] = asdict(retired)
                if not retired.clean or not retired.child_exit_observed or retired.stderr_failure_code:
                    result["failure"] = result["failure"] or "cleanup_uncertain"
            except BaseException:
                result["failure"] = result["failure"] or "cleanup_uncertain"
        elif claim is not None and claim.path.exists():
            result["failure"] = "startup_cleanup_uncertain"
        if pending is not None:
            if not pending.done():
                pending.cancel()
            with contextlib.suppress(BaseException):
                await asyncio.wait_for(pending, 1)
        if projection is not None:
            projection.close_producer()
            # Snapshot partial assistant text too, without inventing a stop reason
            # when no response arrived. Thoughts and raw exceptions are excluded.
            turn = projection.finalize(result["stopReason"] or "")
            result["assistantAnswerBytes"] = turn.assistant_original_bytes
            result["assistantAnswerOmitted"] = turn.assistant_original_bytes > limits["answerBytes"]
            if not result["assistantAnswerOmitted"]:
                result["assistantAnswer"] = turn.assistant_text
    if result["failure"] is None and result["answerAccepted"] and result["cleanup"]["clean"]:
        result["outcome"] = "passed"
    # Keep the workspace even on success; never delete private state or an uncertain owner.
    return result


async def execute(path: Path, repo: Path, expected_commit: str, expected_hash: str) -> dict:
    protocol, prepared = await admit(path, repo, expected_commit, expected_hash)
    limits = protocol["limits"]
    evidence = EvidenceRoot.create(Path(protocol["evidenceRoot"]), max_file_bytes=limits["evidenceFileBytes"],
        max_total_bytes=limits["evidenceTotalBytes"], max_files=limits["evidenceFiles"])
    result = {"outcome": "failed", "failure": "workspace_creation_failed"}
    try:
        prepared.execution_root.mkdir(parents=True, exist_ok=False)
        evidence.write_json("admission.json", {"qualificationCommit": expected_commit,
            "protocolSha256": expected_hash, "implementationCommit": protocol["implementationCommit"],
            "runtimeId": protocol["runtime"]["runtimeId"], "requestedModel": protocol["model"],
            "requestedReasoning": protocol["reasoning"], "mcpServers": [],
            "livePanelRoundTrip": False, "providerTokenCap": None})
        result = await run_image(protocol, prepared)
    finally:
        evidence.write_json("result.json", result)
        evidence.seal()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--expected-qualification-commit", required=True)
    parser.add_argument("--expected-protocol-sha256", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--admit-only", action="store_true", help="Read-only admission; no Prime launch")
    mode.add_argument("--execute", action="store_true", help="Requires separate one-execution authorization")
    args = parser.parse_args(argv)
    try:
        if args.admit_only:
            asyncio.run(admit(args.protocol, REPO, args.expected_qualification_commit, args.expected_protocol_sha256))
            print("Slice C read-only admission passed; execution not performed.")
            return 0
        result = asyncio.run(execute(args.protocol, REPO, args.expected_qualification_commit, args.expected_protocol_sha256))
        print("Slice C " + result["outcome"] + "; inspect sealed nonsecret evidence.")
        return 0 if result["outcome"] == "passed" else 1
    except BaseException:
        print("Slice C refused or finalization failed; no retry. Preserve any created roots.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
