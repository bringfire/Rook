"""Offline tests only: no packaged Prime or provider may run here."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from acp.schema import AgentMessageChunk, AgentThoughtChunk, PromptResponse, TextContentBlock

from rook.agent.chat.acp_client import RookChatAcpClient
from rook.agent.chat.acp_conversation import PreparedDirectAcpLaunch
from rook.agent.chat.acp_process import InitializedAcp, RetirementResult
from scripts.qualification import rookchat_prime_acp_slice_c as slice_c
from scripts.qualification.rookchat_prime_acp_common import QualificationRefused
from .test_chat_acp_conversation import _contract


REPO = Path(__file__).resolve().parents[2]
IMAGE = REPO / "scripts/qualification/fixtures/slice-c-image-01.png"
PROMPT = REPO / "scripts/qualification/fixtures/slice-c-prompt.txt"
REAL_CONNECT = socket.socket.connect
REAL_POPEN = subprocess.Popen


@pytest_asyncio.fixture(autouse=True)
async def no_external_contact(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("external process/network boundary reached")
    async def refuse_async(*args, **kwargs):
        refuse()
    monkeypatch.setattr(subprocess, "Popen", refuse)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", refuse_async)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", refuse_async)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    yield
    monkeypatch.undo()


@pytest.fixture
def inputs(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    image = repo / "image.png"
    image.write_bytes(IMAGE.read_bytes())
    prompt = repo / "prompt.txt"
    prompt.write_bytes(PROMPT.read_bytes())
    auth = tmp_path / "private-auth"
    auth.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    contract = _contract(runtime)
    def row(path):
        data = path.read_bytes()
        return {"path": path.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest().upper()}
    protocol = {
        "schemaVersion": 1, "executionVersion": 1,
        "implementationCommit": "25d54050f87ba31357e37a414f437f02995729ac",
        "sourceInputs": [], "runtime": {"installRoot": str(runtime), "runtimeId": contract.runtime_id},
        "model": "openai-codex/gpt-5.4-mini", "reasoning": "low",
        "authDir": str(auth), "executionRoot": str(tmp_path / "work"),
        "evidenceRoot": str(tmp_path / "evidence"),
        "conversationId": "cccccccccccc4ccc8ccccccccccccccc",
        "image": row(image), "prompt": row(prompt),
        "limits": {"operationSeconds": 180, "initializeSeconds": 60, "promptSeconds": 90,
                   "cancelSeconds": 10, "cleanupSeconds": 60, "answerBytes": 64,
                   "evidenceFiles": 16, "evidenceFileBytes": 1048576, "evidenceTotalBytes": 4194304},
    }
    return protocol, repo, contract


def test_preparation_uses_product_launch_and_exact_image_without_creating_roots(inputs):
    protocol, repo, contract = inputs
    prepared = slice_c.prepare(protocol, repo, contract)
    launch = prepared.launch.launch
    assert isinstance(prepared.launch, PreparedDirectAcpLaunch)
    assert launch.argv[0] == str(contract.executable_path)
    assert launch.argv[launch.argv.index("--model") + 1] == protocol["model"]
    assert launch.argv[launch.argv.index("--thinking") + 1] == "low"
    assert "--no-approve" in launch.argv and "--no-daemon" in launch.argv
    assert "--offline" not in launch.argv
    assert launch.environment["PRIME_AGENT_CODING_AGENT_DIR"] == protocol["authDir"]
    assert launch.environment["PYTHONDONTWRITEBYTECODE"] == "1"
    assert "PI_OFFLINE" not in launch.environment
    assert launch.cwd == Path(protocol["executionRoot"]) / "project"
    assert str(prepared.paths.session_path(protocol["conversationId"])) in launch.argv
    assert prepared.blocks[0].text.encode() == PROMPT.read_bytes()
    assert base64.b64decode(prepared.blocks[1].data) == IMAGE.read_bytes()
    assert prepared.blocks[1].mime_type == "image/png"
    assert not Path(protocol["executionRoot"]).exists()
    assert not Path(protocol["evidenceRoot"]).exists()


@pytest.mark.parametrize("target", ["image", "prompt"])
def test_input_substitution_refuses_before_roots(inputs, target):
    protocol, repo, contract = inputs
    (repo / protocol[target]["path"]).write_bytes(b"substitution")
    with pytest.raises(QualificationRefused):
        slice_c.prepare(protocol, repo, contract)
    assert not Path(protocol["executionRoot"]).exists()


@pytest.mark.parametrize("target", ["executionRoot", "evidenceRoot"])
def test_existing_generation_and_auth_overlap_refuse(inputs, target):
    protocol, repo, contract = inputs
    protocol[target] = protocol["authDir"]
    with pytest.raises(QualificationRefused):
        slice_c.prepare(protocol, repo, contract)


class FakeProcess:
    def __init__(self, launch, claim, *, answer="blue", reason="end_turn", image=True,
                 clean=True, hang=False, usage=None):
        self.launch, self.claim = launch, claim
        self.answer, self.reason, self.image, self.clean, self.hang = answer, reason, image, clean, hang
        self.usage = usage
        self.client = RookChatAcpClient()
        self.session_id = None
        self.transport_failure = asyncio.Event()
        self.calls = []
        self.cancelled = asyncio.Event()

    async def initialize(self):
        self.calls.append("initialize")
        return InitializedAcp(image_supported=self.image)

    async def new_session(self, *, cwd, mcp_servers):
        assert mcp_servers == []
        assert cwd == self.launch.cwd
        self.calls.append("session")
        self.session_id = "ephemeral-acp-not-a-durable-id"
        self.client.reset_for_session(launch_generation=1, acp_session_id=self.session_id)
        return self.session_id

    async def prompt(self, blocks, *, generation, projection):
        self.calls.append("prompt")
        assert base64.b64decode(blocks[1].data) == IMAGE.read_bytes()
        assert blocks[0].text.encode() == PROMPT.read_bytes()
        if self.hang:
            await self.cancelled.wait()
        self.client.activate_prompt(generation, projection, asyncio.Event())
        await self.client.session_update(self.session_id,
            AgentMessageChunk(session_update="agent_message_chunk",
                              content=TextContentBlock(type="text", text=self.answer)))
        self.client.clear_prompt(generation)
        response = PromptResponse(stop_reason=self.reason)
        if self.usage is not None:
            response = SimpleNamespace(stop_reason=self.reason, usage=self.usage)
        return response

    async def cancel(self):
        self.calls.append("cancel")
        self.cancelled.set()

    async def retire(self, **kwargs):
        self.calls.append("retire")
        if self.clean:
            self.claim.release_after_observed_exit()
        return RetirementResult(self.clean, self.clean, 0, False, None)


async def run_fake(inputs, monkeypatch, **options):
    protocol, repo, contract = inputs
    prepared = slice_c.prepare(protocol, repo, contract)
    observed = []
    async def start(self, claim, *, launch_generation):
        assert launch_generation == 1
        process = FakeProcess(self.launch, claim, **options)
        observed.append(process)
        return process
    monkeypatch.setattr(PreparedDirectAcpLaunch, "start", start)
    Path(protocol["executionRoot"]).mkdir()
    result = await slice_c.run_image(protocol, prepared)
    return result, observed[0]


@pytest.mark.asyncio
async def test_exact_answer_empty_mcp_and_observed_cleanup(inputs, monkeypatch):
    result, process = await run_fake(inputs, monkeypatch)
    assert result["outcome"] == "passed"
    assert result["usage"] is None
    assert result["cleanup"]["child_exit_observed"] is True
    assert process.calls == ["initialize", "session", "prompt", "retire"]
    assert not process.claim.path.exists()


@pytest.mark.parametrize("options", [
    {"answer": "red"}, {"answer": "blue" * 22}, {"reason": "max_tokens"},
    {"reason": "cancelled"}, {"answer": ""}, {"image": False}, {"clean": False},
])
@pytest.mark.asyncio
async def test_failed_application_or_cleanup_cannot_pass(inputs, monkeypatch, options):
    result, process = await run_fake(inputs, monkeypatch, **options)
    assert result["outcome"] == "failed"
    assert process.calls[-1] == "retire"
    if options.get("image") is False:
        assert "prompt" not in process.calls
    if options.get("clean") is False:
        assert process.claim.path.exists()


@pytest.mark.asyncio
async def test_timeout_cancels_once_retires_and_never_accepts_late_answer(inputs, monkeypatch):
    inputs[0]["limits"]["promptSeconds"] = .01
    result, process = await run_fake(inputs, monkeypatch, hang=True)
    assert result["outcome"] == "failed"
    assert result["failure"] == "deadline"
    assert process.calls == ["initialize", "session", "prompt", "cancel", "retire"]


@pytest.mark.asyncio
async def test_only_returned_numeric_usage_is_retained(inputs, monkeypatch):
    usage = {"input_tokens": 12, "output_tokens": 3, "secret": "NEVER_RETAIN"}
    result, _ = await run_fake(inputs, monkeypatch, usage=usage)
    assert result["usage"] == {"input_tokens": 12, "output_tokens": 3}
    assert "NEVER_RETAIN" not in json.dumps(result)


def write_protocol(inputs):
    protocol, repo, _ = inputs
    path = repo / "scripts/qualification/protocols/rookchat-prime-acp-slice-c-v1.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(slice_c.canonical_json_bytes(protocol))
    return path


@pytest.mark.parametrize("damage", ["extra", "duplicate", "mismatch", "noncanonical", "limit", "mcp", "model"])
def test_protocol_rejects_nonclosed_or_unfrozen_policy(inputs, damage):
    protocol = inputs[0]
    if damage == "extra":
        protocol["unknown"] = True
    if damage == "mismatch":
        protocol["executionVersion"] = 2
    if damage == "limit":
        protocol["limits"]["answerBytes"] = 0
    if damage == "mcp":
        protocol["mcpServers"] = ["rook"]
    if damage == "model":
        protocol["model"] = "other/model"
    path = write_protocol(inputs)
    if damage == "duplicate":
        path.write_bytes(path.read_bytes().replace(b'{', b'{"schemaVersion":1,', 1))
    if damage == "noncanonical":
        path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(QualificationRefused):
        slice_c.load_protocol(path, inputs[1])
    assert not Path(protocol["executionRoot"]).exists()


@pytest.mark.asyncio
async def test_wrong_protocol_hash_stops_before_git_runtime_or_roots(inputs, monkeypatch):
    path = write_protocol(inputs)
    def forbidden(*args, **kwargs):
        raise AssertionError("runtime verification reached before protocol hash")
    monkeypatch.setattr(slice_c, "load_and_verify_runtime", forbidden)
    with pytest.raises(QualificationRefused, match="protocol hash"):
        await slice_c.admit(path, inputs[1], "a" * 40, "0" * 64)
    assert not Path(inputs[0]["executionRoot"]).exists()


def test_canonical_protocol_is_admitted_without_credential_reads(inputs, monkeypatch):
    path = write_protocol(inputs)
    assert slice_c.load_protocol(path, inputs[1]) == inputs[0]
    original = Path.open
    auth = Path(inputs[0]["authDir"])
    def open_file(path, *args, **kwargs):
        assert not path.is_relative_to(auth), "credential read attempted"
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", open_file)
    slice_c.prepare(inputs[0], inputs[1], inputs[2])


def test_isolated_cli_help_and_wrong_hash_have_no_contact(inputs, monkeypatch):
    path = write_protocol(inputs)
    prefix = [sys.executable, "-I", str(REPO / slice_c.RUNNER_PATH)]
    commands = [prefix + ["--help"], prefix + ["--protocol", str(path),
        "--expected-qualification-commit", "a" * 40, "--expected-protocol-sha256", "0" * 64, "--admit-only"]]
    def admitted_popen(argv, *args, **kwargs):
        assert argv in commands and "--execute" not in argv
        return REAL_POPEN(argv, *args, **kwargs)
    monkeypatch.setattr(subprocess, "Popen", admitted_popen)
    for command, code in zip(commands, (0, 1)):
        completed = subprocess.run(command, cwd=inputs[1], capture_output=True, timeout=15)
        assert completed.returncode == code
        assert len(completed.stdout) + len(completed.stderr) < 8192
    assert not Path(inputs[0]["executionRoot"]).exists()
    assert not Path(inputs[0]["evidenceRoot"]).exists()


@pytest.mark.asyncio
async def test_execution_seals_failure_without_raw_errors_or_credentials(inputs, monkeypatch):
    protocol, repo, contract = inputs
    prepared = slice_c.prepare(protocol, repo, contract)
    async def admission(*args):
        return protocol, prepared
    async def bad_start(*args, **kwargs):
        raise RuntimeError("DO_NOT_RETAIN_AUTHORIZATION_OR_TOKEN")
    monkeypatch.setattr(slice_c, "admit", admission)
    monkeypatch.setattr(PreparedDirectAcpLaunch, "start", bad_start)
    result = await slice_c.execute(Path("unused"), repo, "a" * 40, "B" * 64)
    assert result["outcome"] == "failed"
    root = Path(protocol["evidenceRoot"])
    assert (root / "SEALED").is_file()
    retained = b"".join(p.read_bytes() for p in root.iterdir())
    assert b"DO_NOT_RETAIN" not in retained
    assert Path(protocol["executionRoot"]).exists()
    assert Path(protocol["authDir"]).is_dir()


def install_fake_sdk(monkeypatch, *, scenario="settled", answer="blue", reason="end_turn"):
    from rook.agent.chat import acp_process
    from acp import PROTOCOL_VERSION
    observed = {"calls": []}
    waiting = asyncio.get_running_loop().create_future()
    class Child:
        returncode = None
        stderr = asyncio.StreamReader()
        async def wait(self):
            return self.returncode
    child = Child()
    child.stderr.feed_eof()
    class Connection:
        async def initialize(self, **kwargs):
            return SimpleNamespace(protocol_version=PROTOCOL_VERSION, agent_capabilities=SimpleNamespace(
                session_capabilities=SimpleNamespace(close=True), prompt_capabilities=SimpleNamespace(image=True)))
        async def new_session(self, **kwargs):
            observed["session"] = kwargs
            return SimpleNamespace(session_id="ephemeral-real-transport")
        async def prompt(self, session_id, blocks):
            observed["blocks"] = blocks
            observed["calls"].append("prompt")
            await observed["client"].session_update(session_id, AgentThoughtChunk(
                session_update="agent_thought_chunk", content=TextContentBlock(type="text", text="PRIVATE_THOUGHT")))
            await observed["client"].session_update(session_id, AgentMessageChunk(
                session_update="agent_message_chunk", content=TextContentBlock(type="text", text=answer)))
            if scenario == "transport_failure":
                raise ConnectionError("PRIVATE_PROVIDER_ERROR")
            if scenario == "protocol_failure":
                raise ValueError("PRIVATE_PROTOCOL_ERROR")
            if scenario.startswith("cancel_"):
                await waiting
                return PromptResponse(stop_reason="cancelled")
            if scenario.startswith("transport_signal"):
                observed["owner"].transport_failure.set()
                if scenario == "transport_signal_pending":
                    await waiting
            return PromptResponse(stop_reason=reason)
        async def cancel(self, session_id):
            observed["calls"].append("cancel")
            if scenario == "cancel_failure":
                raise ConnectionError("PRIVATE_CANCEL_ERROR")
            if scenario == "cancel_settled":
                waiting.set_result(None)
        async def close_session(self, session_id):
            observed["calls"].append("close_session")
            observed["closed"] = session_id
    class Context:
        async def __aenter__(self):
            return Connection(), child
        async def __aexit__(self, *args):
            observed["calls"].append("context_exit")
            if not waiting.done():
                waiting.cancel()
            child.returncode = 0
    def spawn(client, *argv, **kwargs):
        observed.update(client=client, argv=argv, **kwargs)
        return Context()
    # Replace only the external SDK spawn boundary, retaining real product owners.
    original = acp_process.OwnedAcpProcess.start.__func__
    async def start(cls, *args, **kwargs):
        owner = await original(cls, *args, spawn_context_factory=spawn, **kwargs)
        observed["owner"] = owner
        return owner
    monkeypatch.setattr(acp_process.OwnedAcpProcess, "start", classmethod(start))
    return observed


@pytest.mark.asyncio
async def test_real_factory_and_owned_transport_receive_exact_empty_mcp(inputs, monkeypatch):
    observed = install_fake_sdk(monkeypatch)
    protocol, repo, contract = inputs
    prepared = slice_c.prepare(protocol, repo, contract)
    Path(protocol["executionRoot"]).mkdir()
    result = await slice_c.run_image(protocol, prepared)
    assert result["outcome"] == "passed"
    assert observed["session"] == {"cwd": str(prepared.launch.launch.cwd), "mcp_servers": []}
    assert observed["argv"] == prepared.launch.launch.argv
    assert observed["cwd"] == prepared.launch.launch.cwd
    assert observed["env"]["PRIME_AGENT_CODING_AGENT_DIR"] == protocol["authDir"]
    assert observed["blocks"][1].data == base64.b64encode(IMAGE.read_bytes()).decode()
    assert observed["closed"] == "ephemeral-real-transport"


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario,answer,expected_calls", [
    ("cancel_failure", "", ["prompt", "cancel", "context_exit"]),
    ("cancel_timeout", "", ["prompt", "cancel", "context_exit"]),
    ("transport_failure", "partial", ["prompt", "context_exit"]),
    ("protocol_failure", "partial", ["prompt", "context_exit"]),
    ("transport_signal_pending", "partial", ["prompt", "context_exit"]),
    ("transport_signal_settled", "blue", ["prompt", "context_exit"]),
    ("settled", "blue", ["prompt", "close_session", "context_exit"]),
    ("settled", "red", ["prompt", "close_session", "context_exit"]),
    ("cancel_settled", "", ["prompt", "cancel", "close_session", "context_exit"]),
])
async def test_real_owner_close_requires_confirmed_settlement(inputs, monkeypatch, scenario, answer, expected_calls):
    protocol, repo, contract = inputs
    protocol["limits"].update(promptSeconds=.02, cancelSeconds=.02)
    observed = install_fake_sdk(monkeypatch, scenario=scenario, answer=answer)
    prepared = slice_c.prepare(protocol, repo, contract)
    prepared.execution_root.mkdir()
    result = await slice_c.run_image(protocol, prepared)
    assert observed["calls"] == expected_calls
    assert result["cleanup"]["child_exit_observed"] is True
    assert not observed["owner"].claim.path.exists()
    assert result["outcome"] == ("passed" if scenario == "settled" and answer == "blue" else "failed")
    expected_stop = "end_turn" if scenario in ("settled", "transport_signal_settled") else (
        "cancelled" if scenario == "cancel_settled" else None)
    assert result["stopReason"] == expected_stop


@pytest.mark.asyncio
@pytest.mark.parametrize("answer,reason,scenario", [
    (" blue\n", "end_turn", "settled"),
    ("red", "end_turn", "settled"),
    ("blue", "max_tokens", "settled"),
    ("", "refusal", "settled"),
    ("\u00e9" * 32, "end_turn", "settled"),
    ("\u00e9" * 32 + "x", "end_turn", "settled"),
    ("partial", None, "transport_failure"),
])
async def test_sealed_result_retains_bounded_observed_answer_and_stop_reason(inputs, monkeypatch, answer, reason, scenario):
    protocol, repo, contract = inputs
    install_fake_sdk(monkeypatch, scenario=scenario, answer=answer, reason=reason)
    prepared = slice_c.prepare(protocol, repo, contract)
    async def admission(*args):
        return protocol, prepared
    monkeypatch.setattr(slice_c, "admit", admission)
    await slice_c.execute(Path("unused"), repo, "a" * 40, "B" * 64)
    root = Path(protocol["evidenceRoot"])
    assert (root / "SEALED").is_file()
    raw = (root / "result.json").read_bytes()
    result = json.loads(raw)
    length = len(answer.encode("utf-8"))
    assert result["assistantAnswer"] == (answer if length <= 64 else None)
    assert result["assistantAnswerBytes"] == length
    assert result["assistantAnswerOmitted"] is (length > 64)
    assert result["stopReason"] == reason
    assert result["outcome"] == ("passed" if answer.strip() == "blue" and reason == "end_turn" else "failed")
    assert len(raw) <= protocol["limits"]["evidenceFileBytes"]
    assert b"PRIVATE_" not in raw


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", [None, "bad_nonce", "bad_image"])
async def test_frozen_panel_wire_through_real_http_validation_manager_and_acp(tmp_path, monkeypatch, damage):
    from aiohttp.test_utils import TestClient, TestServer
    from rook.agent.chat import server
    from .test_chat_acp_conversation import FakeProcessFactory, _manager
    from .test_chat_server import _create_body
    factory = FakeProcessFactory()
    manager, store, _, _, _ = _manager(tmp_path, factory=factory)
    client = TestClient(TestServer(server.create_chat_app(manager, expected_nonce="slice-c-fixture-nonce")))
    await client.start_server()
    endpoint = ("127.0.0.1", client.server.port)
    def connect(sock, address):
        assert address == endpoint, "nonfixture network refused"
        return REAL_CONNECT(sock, address)
    monkeypatch.setattr(socket.socket, "connect", connect)
    captured = []
    try:
        headers = {"X-Rook-Session": "slice-c-fixture-nonce"}
        response = await client.post("/agent/chat/conversations", json=_create_body(), headers=headers)
        assert response.status == 201
        conversation_id = (await response.json())["conversationId"]
        process = factory.processes[0]
        original_prompt = process.prompt
        async def prompt(blocks, **kwargs):
            captured.extend(blocks)
            return await original_prompt(blocks, **kwargs)
        process.prompt = prompt
        body = json.loads((REPO / "scripts/qualification/fixtures/slice-c-http-request.json").read_bytes())
        if damage == "bad_image":
            body["images"][0]["base64Data"] = "%%%"
        if damage == "bad_nonce":
            headers["X-Rook-Session"] = "wrong"
        response = await client.post(f"/agent/chat/conversations/{conversation_id}/prompt", json=body, headers=headers)
        raw = await response.text()
        if damage:
            assert response.status in (400, 403)
            assert not captured and process.prompt_count == 0
        else:
            assert response.status == 200
            assert json.loads(raw.splitlines()[-1])["outcome"] == "settled"
            assert len(captured) == 2
            assert captured[0].text == PROMPT.read_text()
            assert base64.b64decode(captured[1].data) == IMAGE.read_bytes()
            assert captured[1].mime_type == "image/png"
            # The deterministic manager still supplied Rook MCP to its fake process.
            assert process.new_session_calls == 1
            assert store.get(conversation_id).prime_session_id != process.session_id
    finally:
        await client.close()
