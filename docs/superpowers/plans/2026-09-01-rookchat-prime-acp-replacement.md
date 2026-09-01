# RookChat Prime ACP Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ChatRunner with one product implementation in which the existing RookChat panel talks through the Python chat service to one directly owned, daemon-free Prime ACP process per open conversation, while preserving Rook's target, mutation, receipt, readiness, and evidence authority.

**Architecture:** C# remains the user-input and presentation client of the authenticated local HTTP service. The Python service uses the official Python ACP SDK to own one Prime process/ACP connection, a complete durable association, a non-expiring `open.claim`, and bounded disposable presentation history; Prime remains the sole conversation and reasoning authority, and Rook remains the sole host-operation authority. Standard ACP MCP injection supplies a manifest-bound Markdown-only `rook-full` skill and the service-owned `rook` stdio server; no private Prime RPC, daemon topology, backend abstraction, or ChatRunner fallback survives cutover.

**Tech Stack:** C#/.NET 8, 7, and 4.8 with Eto/WebView2; Python 3.10+ with `aiohttp` and exact `agent-client-protocol==0.12.1`; ACP 1.3 as implemented by the pinned Prime artifact; MCP 1.28.1; Rhino 8 C++ SDK; Grasshopper managed bridge; PowerShell/Inno Setup release tooling; pytest/xUnit.

**Spec:** `docs/superpowers/specs/2026-09-01-rookchat-prime-acp-replacement-design.md` at frozen baseline `712228ec47baffe250e299d9eacdb31b1448a945` (SHA-256 `1B1D8AD96B03320668E364EFB906CD9E1A4CEADE518411F44C65D396E73A1695`).

## Global Constraints

- This plan is authored against frozen specification baseline `712228ec47baffe250e299d9eacdb31b1448a945`. Implementation begins from the later exact approved plan commit named in the implementation `/goal`; its lineage must contain that baseline. Do not reset to the baseline or replay superseded RPC Tasks 0-7.
- Treat Prime commit `9c25468b62c79fc4b1419d7800740e8e41e30467` as the sole removable compatibility patch over upstream `c718bf3c30fd8da206ed551837cbb54f7ad15948`; do not edit Prime in this plan.
- Preserve every quarantined Task 7 worktree and retained evidence byte-for-byte. Never copy product code from those worktrees.
- Pin `agent-client-protocol==0.12.1` exactly and use its public `spawn_agent_process`, `ClientSideConnection`, schema models, cancellation notification, and close APIs.
- Launch the exact installed Prime executable with an argument array and `--mode acp --no-daemon`; never use a shell, `PATH`, global npm, a daemon socket, PID discovery, PowerShell probing, process scanning, or process-name cleanup.
- Persist associations, not broker lifecycle. Prime JSONL is the only authoritative transcript/goal/settings/compaction store.
- A durable association is create-only, complete, materialized, has a nonempty Prime header ID, and is reopenable only when no `open.claim` exists and custody checks pass.
- The atomic non-expiring `open.claim` has no metadata or recovery logic. Remove it only after the directly owned Prime child is observed exited, or when launch positively proves no child was created.
- Never replay an interrupted prompt, tool call, or mutation. Re-observe authentic Rook state after every reopen before dependent work.
- Keep all current-turn and presentation representations within the exact limits in the approved spec; persist no thoughts, raw ACP events, image bytes, unrestricted `_meta`, or credentials.
- Prime owns authentication. RookChat never accepts `--api-key`, reads `auth.json`, or forwards credentials loaded from Rook's installed `.env`.
- New conversations may pass a fully qualified `--model` and one of `off|minimal|low|medium|high|xhigh|max`; reopen passes neither override.
- The installed `rook-full` package is Markdown-only. Do not add a Rook-owned Python facade or contract-specific kernel.
- One service-owned ACP MCP declaration named exactly `rook` supplies its executable, arguments, closed environment, profile, and immutable host/Rhino binding from the verified runtime contract. The verified association working directory is supplied through `session/new.cwd` because ACP stdio declarations have no working-directory field.
- Prime's accepted MCP operating limits remain 20 seconds for server startup and 60 seconds for a tool call. Representative Rook operations must qualify within them; this plan adds no facade or Prime timeout patch.
- Preserve full Rook authoring. Grasshopper uses dynamic document context with centrally advertised and enforced `expectedGhDocumentId` optimistic concurrency, not permanent GH binding or hostile-code containment.
- ChatRunner is deleted at cutover. Do not add a backend registry, selector, common backend interface, feature flag, or runtime fallback.
- Qualification code and evidence remain external to product runtime. No live slice executes without its explicit review gate and separate authorization.
- Use the implementation worktree Python for every Python test: `C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server/.venv/Scripts/python.exe` after `uv sync --frozen --extra test` has established it.
- Use the existing Rhino/MFC toolchain rules in `AGENTS.md`; managed-only test gates do not imply native build verification.

## Execution Admission

After independent review, the implementation `/goal` must name the exact approved commit containing this plan. Before Task 1, the executor compares clean `HEAD` with that literal commit and stops on any mismatch or uncommitted change. This authorization is supplied by the implementation goal, not an environment variable and not a self-referential hash inside this document. Every later task begins from the clean commit produced by the preceding task and stages only the exact files listed for that task.

## Interface Ledger

These names are fixed for this plan so independently implemented tasks compose without reinterpretation.

```python
# mcp_server/src/rook/agent/chat/acp_storage.py
@dataclass(frozen=True)
class RookBinding:
    profile: Literal["readonly", "full"]
    host_generation_id: str
    rhino_document_serial: int
    route_process_id: int  # routing hint only

@dataclass(frozen=True)
class ConversationAssociation:
    schema_version: int
    conversation_id: str
    session_path: str
    prime_session_id: str
    working_directory: str
    runtime_id: str
    binding: RookBinding
    requested_initial_model: str | None
    requested_initial_reasoning: str | None
    created_at_utc: str

class AssociationStore:
    def reserve_provisional(self, binding: RookBinding, runtime_id: str,
                            working_directory: Path, requested_model: str | None,
                            requested_reasoning: str | None) -> ProvisionalAssociation:
        raise NotImplementedError
    def publish(self, provisional: ProvisionalAssociation,
                header: PrimeSessionHeader) -> ConversationAssociation:
        raise NotImplementedError
    def get(self, conversation_id: str) -> ConversationAssociation:
        raise NotImplementedError
    def list(self) -> tuple[ConversationAssociation, ...]:
        raise NotImplementedError
    def delete_record(self, association: ConversationAssociation) -> None:
        raise NotImplementedError

class OpenClaim:
    @classmethod
    def acquire(cls, claims_root: Path, canonical_session_path: str) -> "OpenClaim":
        raise NotImplementedError
    def release_after_observed_exit(self) -> None:
        raise NotImplementedError
    def release_no_child_created(self) -> None:
        raise NotImplementedError

@dataclass(frozen=True)
class ProvisionalAssociation:
    conversation_id: str
    session_path: str
    working_directory: str
    runtime_id: str
    binding: RookBinding
    requested_initial_model: str | None
    requested_initial_reasoning: str | None

@dataclass(frozen=True)
class PrimeSessionHeader:
    version: int
    session_id: str
    working_directory: str
```

```python
# mcp_server/src/rook/agent/chat/prime_runtime.py
@dataclass(frozen=True)
class PrimeRuntimeContract:
    schema_version: int
    runtime_id: str
    platform: str
    architecture: str
    upstream_commit: str
    compatibility_patch_commit: str | None
    manifest_sha256: str
    acp_protocol_version: int
    python_acp_sdk_version: str
    executable_path: Path
    goal_skill_path: Path
    rook_skill_path: Path
    rook_skill_manifest_sha256: str
    rook_mcp_command: Path
    rook_mcp_args: tuple[str, ...]
    claim_key_version: int

def load_and_verify_runtime(install_root: Path, runtime_id: str) -> PrimeRuntimeContract:
    raise NotImplementedError
def build_prime_argv(contract: PrimeRuntimeContract, session_path: Path,
                     requested_model: str | None,
                     requested_reasoning: str | None,
                     reopen: bool) -> tuple[str, ...]:
    raise NotImplementedError
def build_prime_child_env(base_environment: Mapping[str, str],
                          contract: PrimeRuntimeContract) -> dict[str, str]:
    raise NotImplementedError
def build_rook_mcp_server(contract: PrimeRuntimeContract,
                          binding: RookBinding) -> McpServerStdio:
    raise NotImplementedError

class RuntimeCatalog(Protocol):
    def latest(self) -> PrimeRuntimeContract:
        raise NotImplementedError
    def get(self, runtime_id: str) -> PrimeRuntimeContract:
        raise NotImplementedError
```

```python
# mcp_server/src/rook/agent/chat/acp_conversation.py
@dataclass(frozen=True)
class PromptInput:
    text: str
    images: tuple[ValidatedImage, ...]

@dataclass(frozen=True)
class PromptResult:
    outcome: Literal["settled", "cancelled", "incomplete", "refused", "error"]
    stop_reason: str | None
    presentation_outcome: Literal["delivered", "stream_failed", "disconnected"]
    cache_published: bool

@dataclass(frozen=True)
class CreateConversationRequest:
    binding: RookBinding
    working_directory: str
    requested_initial_model: str | None
    requested_initial_reasoning: str | None

@dataclass(frozen=True)
class ConversationView:
    conversation_id: str
    durable: bool
    target_available: bool

@dataclass(frozen=True)
class CloseResult:
    outcome: Literal["clean", "unclean", "interrupted"]
    child_exit_observed: bool

@dataclass(frozen=True)
class DeleteResult:
    association_removed: bool
    artifacts_removed: bool

@dataclass(frozen=True)
class ValidatedImage:
    file_name: str
    mime_type: str
    binary_bytes: int
    width: int
    height: int
    sha256: str
    acp_block: ImageContentBlock

@dataclass(frozen=True)
class PromptGeneration:
    launch_generation: int
    acp_session_id: str
    prompt_id: str

class PresentationSink(Protocol):
    async def write(self, event: ProjectedEvent) -> None:
        raise NotImplementedError
    async def drain(self, deadline_seconds: float) -> bool:
        raise NotImplementedError

class AcpProcessFactory(Protocol):
    async def launch(self, contract: PrimeRuntimeContract,
                     association: ProvisionalAssociation | ConversationAssociation,
                     claim: OpenClaim, reopen: bool) -> OwnedAcpProcess:
        raise NotImplementedError

class AcpConversationManager:
    async def create(self, request: CreateConversationRequest) -> ConversationView:
        raise NotImplementedError
    async def reopen(self, conversation_id: str) -> ConversationView:
        raise NotImplementedError
    async def prompt(self, conversation_id: str, prompt: PromptInput,
                     sink: PresentationSink) -> PromptResult:
        raise NotImplementedError
    async def cancel(self, conversation_id: str) -> None:
        raise NotImplementedError
    async def close(self, conversation_id: str) -> CloseResult:
        raise NotImplementedError
    async def delete(self, conversation_id: str) -> DeleteResult:
        raise NotImplementedError
```

```csharp
// src/Rook/UI/Chat/AgentChatClient.cs
public sealed record CreateConversationRequest(
    uint DocumentSerialNumber,
    string CapabilityProfile,
    string? RequestedInitialModel,
    string? RequestedInitialReasoning);

public sealed record ChatImageInput(
    string FileName,
    string MimeType,
    string Base64Data);

public Task<ConversationInfo> CreateAsync(CreateConversationRequest request, CancellationToken ct);
public Task<ConversationInfo> ReopenAsync(string conversationId, CancellationToken ct);
public Task<IReadOnlyList<ConversationInfo>> ListAsync(CancellationToken ct);
public Task<PresentationHistory> GetHistoryAsync(string conversationId, CancellationToken ct);
public IAsyncEnumerable<ChatEvent> PromptAsync(
    string conversationId, string text, IReadOnlyList<ChatImageInput> images,
    CancellationToken ct);
public Task CancelAsync(string conversationId, CancellationToken ct);
public Task<CloseConversationResult> CloseAsync(string conversationId, CancellationToken ct);
public Task<DeleteConversationResult> DeleteAsync(string conversationId, CancellationToken ct);
```

---

### Task 1: Pin The ACP SDK And Build The Model-Free Agent Fixture

**Files:**
- Modify: `mcp_server/pyproject.toml`
- Modify: `mcp_server/uv.lock`
- Create: `mcp_server/tests/fixtures/fake_acp_agent.py`
- Create: `mcp_server/tests/test_chat_acp_sdk_contract.py`

**Interfaces:**
- Produces: exact Python SDK dependency and a deterministic ACP process fixture supporting `initialize`, `session/new`, `session/prompt`, `session/cancel`, `session/close`, concurrent updates, permissions, image capture, MCP declaration capture, controlled hangs, and clean EOF.
- Consumes: public `acp.Agent`, `acp.Client`, `acp.PROTOCOL_VERSION`, schema models, and stdio transport only.

- [ ] **Step 1: Add RED dependency and fixture-contract tests**

```python
def test_python_acp_sdk_is_exactly_pinned():
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert "agent-client-protocol==0.12.1" in project["project"]["dependencies"]

@pytest.mark.asyncio
async def test_fake_agent_runs_initialize_new_prompt_close_and_eof(fake_agent_process):
    result = await fake_agent_process.run_script(
        updates=[{"kind": "agent_message_chunk", "text": "hello"}],
        stop_reason="end_turn",
    )
    assert result.methods == ["initialize", "session/new", "session/prompt", "session/close"]
    assert result.exit_code == 0
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
uv sync --frozen --extra test --check
./.venv/Scripts/python.exe -m pytest tests/test_chat_acp_sdk_contract.py -q
```

Expected: the pin assertion fails and the fake agent fixture is missing; no Prime process launches.

- [ ] **Step 3: Add the exact dependency and deterministic fake ACP agent**

Add this direct dependency and regenerate the lock from the worktree:

```toml
"agent-client-protocol==0.12.1",
```

Implement the fixture as a normal Python ACP agent selected only by tests. Its scenario file is JSON, its event journal is create-only, and every behavior is explicit:

```python
class FakeAgent(Agent):
    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(
                prompt_capabilities=PromptCapabilities(image=True),
                session_capabilities=SessionCapabilities(
                    close=SessionCloseCapabilities()
                ),
            ),
            agent_info=Implementation(
                name="rook-fake-acp-agent",
                title="Rook Fake ACP Agent",
                version="1.0.0",
            ),
        )

    async def new_session(
        self,
        cwd: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[HttpMcpServer | SseMcpServer | AcpMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        servers = mcp_servers or []
        self.journal("session/new", cwd=cwd, mcp_servers=[m.model_dump() for m in servers])
        return NewSessionResponse(session_id=self.scenario.session_id)

    async def prompt(
        self,
        session_id: str,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
            | EmbeddedResourceContentBlock
        ],
        **kwargs: Any,
    ) -> PromptResponse:
        await self.emit_configured_updates(session_id)
        return PromptResponse(stop_reason=self.scenario.stop_reason)

    async def close_session(self, session_id: str, **kwargs: Any) -> CloseSessionResponse:
        self.journal("session/close", session_id=session_id)
        return CloseSessionResponse()
```

The fixture must never import Rook product modules, contact a network endpoint, or spawn descendants.

- [ ] **Step 4: Sync offline-capable dependencies and run GREEN**

Run:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
uv lock
uv sync --frozen --extra test
./.venv/Scripts/python.exe -m pytest tests/test_chat_acp_sdk_contract.py -q
```

Expected: all fixture tests pass and `uv.lock` contains exact `agent-client-protocol` 0.12.1.

- [ ] **Step 5: Commit Task 1**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add mcp_server/pyproject.toml mcp_server/uv.lock mcp_server/tests/fixtures/fake_acp_agent.py mcp_server/tests/test_chat_acp_sdk_contract.py
git commit -m "test(chat): add pinned ACP client fixture"
```

### Task 2: Add Durable Association, Header Envelope, And Crash Claim Custody

**Files:**
- Create: `mcp_server/src/rook/agent/chat/acp_storage.py`
- Create: `mcp_server/tests/test_chat_acp_storage.py`
- Modify: `mcp_server/src/rook/runtime_paths.py`
- Modify: `mcp_server/tests/test_runtime_paths.py`

**Interfaces:**
- Produces: `AcpDataPaths`, `RookBinding`, `PrimeSessionHeader`, `ConversationAssociation`, `ProvisionalAssociation`, `AssociationStore`, `OpenClaim`, and stable error codes `session_unavailable`, `runtime_unavailable`, `session_recovery_required`, and `initialization_failed`.
- Consumes: existing `RuntimePaths.data_root`; no process identity or Prime transcript parser.

- [ ] **Step 1: Write the complete RED custody table**

```python
@pytest.mark.parametrize("bad_first_line", [
    b"", b"[]\n", b'{"type":"other"}\n', b"{not-json}\n",
])
def test_header_envelope_refuses_invalid_first_line(tmp_path, bad_first_line):
    session = tmp_path / "sessions" / "one.jsonl"
    session.parent.mkdir()
    session.write_bytes(bad_first_line)
    with pytest.raises(SessionUnavailable):
        validate_prime_session_header(session, expected_id=None, expected_cwd=tmp_path)

def test_open_claim_is_non_expiring_and_create_exclusive(paths):
    first = OpenClaim.acquire(paths.claims_root, paths.canonical_session("one.jsonl"))
    with pytest.raises(SessionRecoveryRequired):
        OpenClaim.acquire(paths.claims_root, paths.canonical_session("one.jsonl"))
    assert first.path.read_bytes() == b""

def test_association_publication_is_create_only(store, provisional, valid_header):
    published = store.publish(provisional, valid_header)
    with pytest.raises(AssociationAlreadyExists):
        store.publish(provisional, valid_header)
    assert store.get(published.conversation_id) == published
```

Also cover canonical root containment, bounded first physical line, strict UTF-8, object/type/version/nonempty-ID/cwd checks, symlink and Windows reparse refusal, generated UUID/path ownership, atomic complete publication, re-read after claim, Delete ordering, and byte preservation on every refusal.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_chat_acp_storage.py tests/test_runtime_paths.py -q
```

Expected: imports for `acp_storage` and ACP data paths fail.

- [ ] **Step 3: Implement stable data roots and create-only storage**

Use these exact roots beneath `RuntimePaths.data_root`:

```text
rookchat/acp/v1/conversations/<conversation-id>.json
rookchat/acp/v1/sessions/<conversation-id>.jsonl
rookchat/acp/v1/presentation/<conversation-id>/<sequence>.json
rookchat/acp/v1/claims/<sha256(canonical-session-path)>.open.claim
```

Implement exclusive claim creation and explicit release methods; do not make `OpenClaim` a context manager because generic exception cleanup cannot prove child exit.

```python
fd = os.open(claim_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
os.close(fd)
```

Atomic association publication writes canonical UTF-8 JSON plus LF to a same-directory temporary file opened create-only, flushes and `fsync`s it, then calls Windows `os.rename(temp_path, final_path)`. On Windows this same-volume rename is atomic and refuses an existing destination; catch `FileExistsError`, delete only the owned temporary file, and preserve the existing association bytes. The two-process contention test must prove exactly one publisher succeeds.

- [ ] **Step 4: Prove crash-fence semantics model-free**

Add a subprocess fixture that acquires a claim and exits without cleanup. A second process must receive `session_recovery_required`; neither `AssociationStore.get`, reopen validation, nor Delete may remove the claim. Separately prove the owning service removes it only after a supplied `child_has_exited=True` observation, and that positively known pre-spawn failure may call `release_no_child_created()`.

- [ ] **Step 5: Run GREEN and commit**

Run:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_chat_acp_storage.py tests/test_runtime_paths.py -q

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add mcp_server/src/rook/agent/chat/acp_storage.py mcp_server/src/rook/runtime_paths.py mcp_server/tests/test_chat_acp_storage.py mcp_server/tests/test_runtime_paths.py
git commit -m "feat(chat): add ACP association and claim custody"
```

### Task 3: Build The Bounded ACP Projection And Disposable Presentation Cache

**Files:**
- Create: `mcp_server/src/rook/agent/chat/acp_presentation.py`
- Create: `mcp_server/src/rook/agent/chat/acp_images.py`
- Create: `mcp_server/tests/test_chat_acp_presentation.py`
- Create: `mcp_server/tests/test_chat_acp_images.py`

**Interfaces:**
- Produces: `PromptGeneration`, `ProjectedEvent`, `BoundedPromptProjection`, `PresentationQueue`, `PresentationSink`, `PresentationCache`, `ValidatedImage`, `validate_images`, and `map_stop_reason`.
- Consumes: the presentation root from `AcpDataPaths`; no authoritative Prime or Rook state.

- [ ] **Step 1: Write RED tests for every retained representation**

```python
def test_stop_reason_mapping_is_closed():
    assert map_stop_reason("end_turn") == "settled"
    assert map_stop_reason("cancelled") == "cancelled"
    assert map_stop_reason("max_tokens") == "incomplete"
    assert map_stop_reason("max_turn_requests") == "incomplete"
    assert map_stop_reason("refusal") == "refused"

@pytest.mark.asyncio
async def test_concurrent_callbacks_preserve_source_order_and_timeout_as_overflow():
    queue = PresentationQueue(max_events=256, max_utf8_bytes=4 * 1024 * 1024)
    projection = BoundedPromptProjection(generation=PromptGeneration(3, "acp-1", "prompt-9"), queue=queue)
    await asyncio.gather(*(projection.accept(i, message_chunk("m", str(i))) for i in range(20)))
    assert [row.ordinal for row in await queue.drain()] == list(range(20))

def test_turn_file_is_create_only_and_evicts_complete_oldest_turns(cache):
    for sequence in range(1, 258):
        cache.publish(turn(sequence=sequence, size=260_000))
    loaded = cache.load()
    assert len(loaded.turns) <= 256
    assert loaded.earlier_history_omitted is True
```

Add explicit tests for queue 256-event/4-MiB boundaries, the one-second whole callback deadline, generation fencing, allowed message/thought coalescing only, no tool coalescing, prompt-owner overflow signal, panel disconnect, independent cache and drain results, user/assistant accumulator limits, fallback publication, immutable-until-eviction files, corruption, sequence derivation without a ledger, and the exact `_meta` limits.

- [ ] **Step 2: Run RED**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_chat_acp_presentation.py tests/test_chat_acp_images.py -q
```

Expected: both product modules are missing.

- [ ] **Step 3: Implement the fixed bounds verbatim**

```python
MAX_QUEUE_EVENTS = 256
MAX_QUEUE_UTF8_BYTES = 4 * 1024 * 1024
CALLBACK_DEADLINE_SECONDS = 1.0
MAX_USER_TEXT_BYTES = 256 * 1024
MAX_ASSISTANT_TEXT_BYTES = 1024 * 1024
MAX_TOOL_CONTENT_BYTES_PER_CARD = 16 * 1024
MAX_TOOL_CONTENT_BYTES_PER_TURN = 1024 * 1024
MAX_CACHED_TURN_BYTES = 4 * 1024 * 1024
MAX_CONVERSATION_CACHE_BYTES = 64 * 1024 * 1024
MAX_CACHED_TURNS = 256
MAX_FALLBACK_PROJECTION_BYTES = 8 * 1024
MAX_UNKNOWN_META_RECORDS = 32
MAX_UNKNOWN_META_KEYS_PER_RECORD = 16
MAX_UNKNOWN_META_KEY_BYTES = 64
MAX_UNKNOWN_META_TOTAL_BYTES = 8 * 1024
```

Every callback acquires one per-prompt ordering gate, projects, coalesces, and admits within the same one-second deadline. On timeout it sets one absorbing overflow flag and returns; it never calls ACP. Preserve partial assistant text on cancellation. Every truncated user, assistant, tool, or metadata field includes a visible marker and original UTF-8 byte count. If normal projection fails, the cache must attempt one create-only fallback no larger than 8 KiB with sequence, stop reason, available original counts, and the exact approved sentence: `Turn presentation was unavailable. Prime retains the authoritative conversation state.` A missing, stale, or corrupt cache renders `presentation history unavailable` without affecting Prime reopen. Reset known goal/compaction indicators to unknown for every process/session replacement, and record omitted unknown-`_meta` record/key/value counters after the closed limits.

- [ ] **Step 4: Implement strict image admission**

```python
MAX_IMAGES_PER_TURN = 8
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_IMAGE_BYTES_PER_TURN = 32 * 1024 * 1024
MAX_HTTP_BODY_BYTES = 48 * 1024 * 1024
MAX_IMAGE_DIMENSION = 16_384
MAX_IMAGE_PIXELS = 40_000_000
```

Use `base64.b64decode(value, validate=True)`, verify PNG/JPEG/WebP magic bytes against MIME, read dimensions with Pillow without retaining decoded pixels, hash the original binary, and return only metadata to cache serialization. Never log the base64 or binary.

- [ ] **Step 5: Run GREEN and commit**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_chat_acp_presentation.py tests/test_chat_acp_images.py -q

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add mcp_server/src/rook/agent/chat/acp_presentation.py mcp_server/src/rook/agent/chat/acp_images.py mcp_server/tests/test_chat_acp_presentation.py mcp_server/tests/test_chat_acp_images.py
git commit -m "feat(chat): bound ACP presentation and images"
```

### Task 4: Verify Installed Prime Runtime And Own One Direct ACP Process

**Files:**
- Create: `mcp_server/src/rook/agent/chat/prime_runtime.py`
- Create: `mcp_server/src/rook/agent/chat/acp_client.py`
- Create: `mcp_server/src/rook/agent/chat/acp_process.py`
- Create: `mcp_server/tests/test_chat_prime_runtime.py`
- Create: `mcp_server/tests/test_chat_acp_client.py`
- Create: `mcp_server/tests/test_chat_acp_process.py`
- Modify: `mcp_server/src/rook/agent/chat/service_main.py`

**Interfaces:**
- Produces: verified `PrimeRuntimeContract`, exact launch argv/environment/MCP declaration, `RookChatAcpClient`, and `OwnedAcpProcess` with `initialize`, `new_session`, `prompt`, `cancel`, `close_session`, and `retire`.
- Consumes: Task 1 official SDK, Task 2 claim, Task 3 projection; never imports or shells into Prime.

- [ ] **Step 1: Write RED runtime-custody tests**

```python
def test_new_launch_uses_exact_flags_and_reopen_has_no_model_override(contract, association):
    new = build_prime_argv(contract, Path(association.session_path), "anthropic/claude-x", "high", reopen=False)
    assert new[:3] == (str(contract.executable_path), "--mode", "acp")
    assert "--no-daemon" in new
    assert "--no-skills" in new
    assert pairs(new, "--skill") == [str(contract.goal_skill_path), str(contract.rook_skill_path)]
    assert pair(new, "--append-system-prompt") == str(contract.rook_skill_path / "SKILL.md")
    assert pair(new, "--resume") == association.session_path
    assert pair(new, "--model") == "anthropic/claude-x"
    assert pair(new, "--thinking") == "high"
    reopened = build_prime_argv(contract, Path(association.session_path), None, None, reopen=True)
    assert "--model" not in reopened and "--thinking" not in reopened

def test_prime_child_environment_uses_pre_dotenv_snapshot(pre_dotenv_env, contract):
    os.environ["ROOK_INSTALLED_DOTENV_SENTINEL"] = "must-not-pass"
    child = build_prime_child_env(pre_dotenv_env, contract)
    assert "ROOK_INSTALLED_DOTENV_SENTINEL" not in child
    assert "ANTHROPIC_API_KEY" not in child or child["ANTHROPIC_API_KEY"] == pre_dotenv_env.get("ANTHROPIC_API_KEY")
```

Also prove exact manifest reproduction; regular-file-only traversal; ordinal forward-slash paths; raw length/hash binding; manifest self-exclusion; path-under-root checks; required Prime/goal/rook skill/license files; exact ACP SDK version; closed reasoning enum; exact `--no-skills`, pinned goal skill, pinned Rook skill, and raw root-skill system-prompt arguments; no `--api-key`, `--provider`, shell, `PATH`, ambient skill, or reopen overrides; MCP server name exactly `rook`; only contract-owned MCP env keys; and association `working_directory` delivery through `session/new.cwd` rather than a nonexistent stdio-server field.

- [ ] **Step 2: Write RED direct-process tests against the fake ACP agent**

Cover initialization protocol and `session/close` capability refusal, `promptCapabilities.image`, one ACP session per process, permission choice ordering and unique/nonempty IDs, callback generation fencing, cancellation outside callbacks, stop-reason mapping, clean close, `session/close` failure, uncertain prompt retirement, positively failed spawn claim release, uncertain spawn claim preservation, bounded optional Prime `_meta` goal/compaction projection, and reset-to-unknown on every process/session replacement. Missing or unknown `_meta` must never block standard ACP operation.

- [ ] **Step 3: Run RED without Prime**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_chat_prime_runtime.py tests/test_chat_acp_client.py tests/test_chat_acp_process.py -q
```

Expected: product modules are missing; only the fake ACP agent may be spawned.

- [ ] **Step 4: Capture the Prime base environment before loading Rook `.env`**

In `service_main.main`, take `prime_base_environment = dict(os.environ)` before `_load_env()`, then pass that immutable mapping into `start_chat_server`. Do not scan or redact it after `.env` loading; contract-owned exclusions and additions happen in `build_prime_child_env`.

```python
def main() -> None:
    prime_base_environment = dict(os.environ)
    loaded_env = _load_env()
    asyncio.run(_run_service(args, loaded_env, prime_base_environment))
```

`_run_service` keeps the existing `start_chat_server -> wait_for_chat_server -> stop_chat_server` ordering and passes `port`, `include_gh_health`, `owner`, `rhino_process_id`, and `prime_base_environment` by name.

ACP `McpServerStdio` has no per-server working-directory field. Its command, args, and env are contract-owned; the working directory is the verified association `working_directory` supplied as ACP `session/new.cwd`. The model and user cannot provide a different MCP cwd.

- [ ] **Step 5: Implement SDK-owned process lifetime**

Use the public SDK context manager directly:

```python
self._spawn_context = spawn_agent_process(
    self._client,
    *self._launch.argv,
    env=self._launch.environment,
)
self.connection, self.process = await self._spawn_context.__aenter__()
```

Retirement order is bounded `close_session` when allowed, SDK connection/transport close, stdin EOF through the SDK, one process wait, then termination of only `self.process` through the SDK/direct handle fallback. Set `child_exit_observed` only after `await self.process.wait()` returns. Do not enumerate descendants.

- [ ] **Step 6: Implement immediate trusted permission responses**

Validate every option has a unique nonempty ID and recognized kind. Select the first valid `allow_once`, else first valid `allow_always`. If neither exists, atomically set the prompt cancellation flag, notify the prompt owner, return ACP `cancelled`, and never approve a later request from that prompt generation.

- [ ] **Step 7: Run GREEN and commit**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_chat_prime_runtime.py tests/test_chat_acp_client.py tests/test_chat_acp_process.py -q

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add mcp_server/src/rook/agent/chat/prime_runtime.py mcp_server/src/rook/agent/chat/acp_client.py mcp_server/src/rook/agent/chat/acp_process.py mcp_server/src/rook/agent/chat/service_main.py mcp_server/tests/test_chat_prime_runtime.py mcp_server/tests/test_chat_acp_client.py mcp_server/tests/test_chat_acp_process.py
git commit -m "feat(chat): own daemon-free Prime ACP process"
```

### Task 5: Compose Provisional Materialization, Reopen, Prompt, Close, And Delete

**Files:**
- Create: `mcp_server/src/rook/agent/chat/acp_conversation.py`
- Create: `mcp_server/tests/test_chat_acp_conversation.py`
- Create: `mcp_server/tests/test_chat_acp_two_service.py`

**Interfaces:**
- Produces: the `AcpConversationManager` interface in the ledger and operation-result errors consumed by HTTP.
- Consumes: `AssociationStore`, `OpenClaim`, `PresentationCache`, `PrimeRuntimeContract`, and `OwnedAcpProcess`; adds no durable lifecycle record.

- [ ] **Step 1: Write RED tests for new-conversation materialization**

```python
@pytest.mark.asyncio
async def test_first_prompt_is_the_only_provisional_turn(manager, fake_agent, rook_binding):
    view = await manager.create(CreateConversationRequest(binding=rook_binding, runtime_id="runtime-a"))
    assert manager.store.list() == ()
    first = asyncio.create_task(manager.prompt(view.conversation_id, PromptInput("hello", ()), NullSink()))
    with pytest.raises(ConversationBusy):
        await manager.prompt(view.conversation_id, PromptInput("second", ()), NullSink())
    fake_agent.materialize_valid_session()
    assert (await first).outcome == "settled"
    assert manager.store.get(view.conversation_id).prime_session_id == fake_agent.prime_session_id

@pytest.mark.asyncio
async def test_failed_first_publication_is_never_adopted_or_replayed(manager, fake_agent, rook_binding):
    view = await manager.create(CreateConversationRequest(binding=rook_binding, runtime_id="runtime-a"))
    fake_agent.finish_without_session_file()
    result = await manager.prompt(view.conversation_id, PromptInput("hello", ()), NullSink())
    assert result.outcome == "error"
    assert manager.store.list() == ()
    assert fake_agent.prompt_count == 1
```

Cover create-only conversation/session paths, target required for creation, no association before materialization, exact bounded header promotion, failure after file creation but before publication, no automatic adoption, and no second prompt before publication.

The first settled turn may be published to the presentation cache only after the complete association publication succeeds. A failed association publication leaves both the durable registry and presentation cache empty even if bounded live text was displayed.

- [ ] **Step 2: Write RED tests for reopen and target independence**

Prove this exact order with spies:

```text
read locator -> acquire claim -> re-read association -> validate header/runtime -> launch
```

Target unavailability must allow Prime reopen but make the MCP environment retain the original immutable binding so target-dependent Rook calls return `target_unavailable`. Reopen must create a fresh ephemeral ACP session ID, reset optional `_meta` presentation to unknown, and send no prompt.

Add a model-free goal-projection case in which the fake agent reports an active Prime goal, Stop cancels only the current prompt, and the projected goal remains active until fresh Prime metadata says otherwise. Native `/goal status`, `/goal pause`, `/goal resume`, and `/goal clear` text passes through the ordinary settled prompt route; the manager exposes no parallel goal endpoint or persisted goal record.

- [ ] **Step 3: Write RED two-service contention and owner-crash tests**

Start two independent `AcpConversationManager` instances over the same temporary data root. Exactly one may create the claim and call the fake launcher. After an owner service subprocess exits without its close path, wait for its fake child to observe EOF and exit, then prove the claim still refuses Reopen and Delete. Do not inspect any PID.

- [ ] **Step 4: Implement one resident handle map and one single-flight gate**

```python
class AcpConversationManager:
    def __init__(self, store: AssociationStore, runtime_catalog: RuntimeCatalog,
                 process_factory: AcpProcessFactory, cache: PresentationCache):
        self._resident: dict[str, ResidentConversation] = {}
        self._launch_generation = itertools.count(1)

    async def prompt(self, conversation_id: str, prompt: PromptInput,
                     sink: PresentationSink) -> PromptResult:
        resident = self._require_resident(conversation_id)
        if resident.prompt_task is not None:
            raise ConversationBusy(conversation_id)
        resident.prompt_task = asyncio.create_task(
            self._run_prompt(resident, prompt, sink)
        )
        try:
            return await resident.prompt_task
        finally:
            resident.prompt_task = None
```

Do not persist states for `idle`, `materializing`, `suspended`, `interrupted`, cancellation races, or goals.

- [ ] **Step 5: Implement exact cancellation and close branches**

The prompt owner, not an update callback, sends `session/cancel` once and awaits the original prompt task. If it settles, classify that actual stop reason. If it does not, send no further ACP request and retire the exact process.

An authentic Rook result and receipt already received through the ACP tool projection remains authoritative for that Rook operation even when the enclosing prompt later returns `error` or becomes uncertain. If transport fails before a Rook result is observed, record the operation outcome as unknown, freshly inspect Rook state, and never replay it automatically.

Close follows:

```python
if resident.prompt_task is not None:
    settled = await resident.cancel_and_wait(prompt_settlement_deadline)
    if not settled:
        return await resident.retire_without_more_acp()
await resident.process.close_session(close_deadline)
await resident.process.retire(process_exit_deadline)
resident.claim.release_after_observed_exit()
```

A forced termination after observed process exit may release the claim but returns `unclean`; inability to observe exit leaves the claim. Delete holds the same claim through bounded association deletion and artifact cleanup and reports cleanup failures without claiming atomic erasure.

- [ ] **Step 6: Run the complete manager tests**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_chat_acp_conversation.py tests/test_chat_acp_two_service.py -q
```

Expected: all operation outcomes, contention, and crash fences pass without Prime, PowerShell, or PID lookup.

- [ ] **Step 7: Commit Task 5**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add mcp_server/src/rook/agent/chat/acp_conversation.py mcp_server/tests/test_chat_acp_conversation.py mcp_server/tests/test_chat_acp_two_service.py
git commit -m "feat(chat): compose durable ACP conversations"
```

### Task 6: Replace The Chat HTTP Surface With ACP Conversations

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/server.py`
- Modify: `mcp_server/src/rook/agent/chat/service_main.py`
- Rewrite: `mcp_server/tests/test_chat_server.py`
- Modify: `mcp_server/tests/test_chat_integration.py`
- Delete after reference proof: `mcp_server/src/rook/agent/chat/conversation_store.py`
- Delete after reference proof: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Delete after reference proof: `mcp_server/src/rook/agent/chat/model_status.py`
- Delete after reference proof: `mcp_server/src/rook/agent/chat/prompt_builder.py`
- Delete obsolete tests: `mcp_server/tests/test_chat_conversation_store.py`
- Delete obsolete tests: `mcp_server/tests/test_chat_runner.py`
- Delete obsolete tests: `mcp_server/tests/test_chat_runner_model_tools.py`
- Delete obsolete tests: `mcp_server/tests/test_chat_model_status.py`
- Delete obsolete tests: `mcp_server/tests/test_chat_prompt_builder.py`

**Interfaces:**
- Produces: one authenticated HTTP API for health, create, list, reopen, history, prompt stream, cancel, close, and delete.
- Consumes: `AcpConversationManager`; retains knowledge-graph routes and shared Rook modules.

- [ ] **Step 1: Freeze the replacement route contract in RED tests**

Use these routes and no backend discriminator:

```text
GET    /agent/chat/health
GET    /agent/chat/conversations
POST   /agent/chat/conversations
POST   /agent/chat/conversations/{conversation_id}/reopen
GET    /agent/chat/conversations/{conversation_id}/history
POST   /agent/chat/conversations/{conversation_id}/prompt
POST   /agent/chat/conversations/{conversation_id}/cancel
POST   /agent/chat/conversations/{conversation_id}/close
DELETE /agent/chat/conversations/{conversation_id}
```

Tests must assert the absence of `/personas`, `/models`, `/model`, `/start`, `/message`, `/stop`, `/ui-response`, and worker-first routes. Health reports service/version/runtime availability and `Prime-managed` authentication disclosure only; it does not read provider credentials.

- [ ] **Step 2: Add RED request/body refusal tests**

Cover non-object JSON, missing/extra conversation IDs, invalid profile, document serial, model, reasoning, image MIME/base64/size/dimensions, encoded-body size, busy prompt, image capability absence, target unavailable display, cache unavailable display, and every closed storage/ACP error envelope. Preserve the existing nonce/session middleware.

- [ ] **Step 3: Implement dependency-injected ACP routes**

Replace global store/builder/runner keys with one manager key:

```python
_ACP_MANAGER_KEY: web.AppKey[AcpConversationManager] = web.AppKey(
    "_acp_conversation_manager", AcpConversationManager
)

def create_chat_app(
    manager: AcpConversationManager,
    *,
    expected_nonce: str | None = None,
) -> web.Application:
    app = web.Application(middlewares=[cors_and_session_middleware])
    app[_ACP_MANAGER_KEY] = manager
    app[_EXPECTED_NONCE_KEY] = expected_nonce
    register_chat_routes(app)
    register_knowledge_routes(app)
    return app
```

The prompt endpoint prepares `web.StreamResponse` inside subscription cleanup custody, writes bounded projected NDJSON rows, and independently records the terminal Prime outcome and presentation-stream outcome. A disconnected response signals the prompt owner; it does not cancel from the writer callback itself.

- [ ] **Step 4: Prove shared modules before deleting ChatRunner files**

Run:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
rg -n "conversation_store|chat_runner|model_status|prompt_builder" mcp_server/src mcp_server/tests
rg -n "tool_result_view|tool_contracts|execution_policy|personas" mcp_server/src mcp_server/tests
```

Delete only the four ChatRunner-owned modules listed above after the first search shows no retained caller. Keep `tool_result_view.py`, `tool_contracts.py`, `execution_policy.py`, persona modules used by planners/spawn, and knowledge routes because current source inspection proves they have non-chat consumers.

- [ ] **Step 5: Run server GREEN tests**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_chat_server.py tests/test_chat_integration.py tests/test_chat_acp_conversation.py tests/test_chat_acp_presentation.py -q
```

- [ ] **Step 6: Commit Task 6**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add mcp_server/src/rook/agent/chat/server.py mcp_server/src/rook/agent/chat/service_main.py mcp_server/src/rook/agent/chat/conversation_store.py mcp_server/src/rook/agent/chat/chat_runner.py mcp_server/src/rook/agent/chat/model_status.py mcp_server/src/rook/agent/chat/prompt_builder.py mcp_server/tests/test_chat_server.py mcp_server/tests/test_chat_integration.py mcp_server/tests/test_chat_conversation_store.py mcp_server/tests/test_chat_runner.py mcp_server/tests/test_chat_runner_model_tools.py mcp_server/tests/test_chat_model_status.py mcp_server/tests/test_chat_prompt_builder.py
git commit -m "feat(chat): replace ChatRunner HTTP with ACP"
```

### Task 7: Cut The Existing C# Panel Over To The ACP Product API

**Files:**
- Rewrite: `src/Rook/UI/Chat/AgentChatClient.cs`
- Rewrite: `src/Rook/UI/Chat/AgentChatTab.cs`
- Modify: `src/Rook/UI/Chat/ChatTab.cs`
- Modify: `src/Rook/UI/Chat/RookChatPanel.cs`
- Create: `src/Rook/UI/Chat/ConversationCloseCoordinator.cs`
- Modify: `src/Rook/UI/Chat/ChatServiceManager.cs`
- Modify: `src/Rook/UI/Chat/Resources/chat.html`
- Modify: `src/Rook/UI/Chat/Resources/chat.css`
- Delete: `src/Rook/UI/Chat/PersonaPicker.cs`
- Rewrite: `src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs`
- Delete: `src/Rook.Tests/UI/Chat/AgentChatApplyEnableTests.cs`
- Modify: `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs`
- Modify: `src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs`
- Create: `src/Rook.Tests/UI/Chat/ConversationCloseCoordinatorTests.cs`
- Create: `src/Rook.Tests/UI/Chat/AgentChatImageAdmissionTests.cs`

**Interfaces:**
- Produces: one Prime ACP conversation tab with new/reopen/history, creation-time model/reasoning, text/images, streaming, cancel, close, delete, and target/presentation status.
- Consumes: Task 6 HTTP routes; C# never imports ACP.

- [ ] **Step 1: Write RED client contract tests**

```csharp
[Fact]
public async Task Reopen_does_not_send_model_or_reasoning_overrides()
{
    var handler = new RecordingHandler(Json("{\"conversationId\":\"c1\"}"));
    using var client = AgentChatClient.ForTests(handler);
    await client.ReopenAsync("c1", CancellationToken.None);
    Assert.Equal("{}", handler.LastBody);
}

[Fact]
public async Task Prompt_parser_keeps_prime_and_presentation_outcomes_separate()
{
    var rows = "{\"type\":\"text_delta\",\"text\":\"hi\"}\n" +
               "{\"type\":\"terminal\",\"outcome\":\"settled\",\"presentationOutcome\":\"stream_failed\"}\n";
    var events = await Parse(rows);
    Assert.Equal("settled", events.Last().Outcome);
    Assert.Equal("stream_failed", events.Last().PresentationOutcome);
}
```

Cover all terminal mappings, bounded error parsing, tool cards as presentation only, partial text on cancellation, omitted-history markers, image metadata history, and target unavailable status.

- [ ] **Step 2: Write RED panel lifecycle tests**

Prove model/reasoning controls are editable only before create, reopen renders the presentation cache without feeding it to Prime, Stop calls `/cancel`, closing a tab queues `/close` to an owner that survives tab disposal, and deleting requires explicit confirmation and calls only `/delete`.

- [ ] **Step 3: Replace persona selection with Prime conversation creation**

`RookChatPanel`'s add action opens a compact creation dialog with optional configured fully qualified model and exact reasoning enum. It always creates an ACP conversation with the shipped `full` profile; no profile selector is shown. The temporary `readonly` profile is admitted only by the external Slice D qualification entry point. Remove persona names/colors and backend concepts. Existing durable conversations appear in a reopen list returned by the service.

- [ ] **Step 4: Implement image capture and bounded HTTP payloads**

Change WebView-to-C# submit messages to the closed shape:

```json
{
  "type": "submit",
  "text": "Inspect this",
  "images": [
    {"fileName": "paste.png", "mimeType": "image/png", "base64Data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQ0sAAAAASUVORK5CYII="}
  ]
}
```

C# performs early count and encoded-body checks for responsiveness; Python remains authoritative for strict base64, magic bytes, dimensions, pixel count, and binary limits. Do not persist image bytes in WebView state or diagnostics.

- [ ] **Step 5: Give close delivery a service-lifetime owner**

`ConversationCloseCoordinator` retains bounded close tasks independently of `AgentChatTab` and uses a dedicated `AgentChatClient`. `AgentChatTab.OnTabClosed` detaches UI callbacks first, enqueues exactly one close, and disposes only tab-owned resources. `ChatServiceManager.Dispose` gives queued closes one bounded drain, then stops the Python service; it does not cancel a close merely because the tab vanished.

- [ ] **Step 6: Run focused managed tests**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
dotnet restore src/Rook.Tests/Rook.Tests.csproj
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "AgentChat|RookChatPanel|ChatServiceManager|ConversationCloseCoordinator" --no-restore
```

Expected: all focused tests pass. No Rhino or Python service launches.

- [ ] **Step 7: Commit Task 7**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add src/Rook/UI/Chat/AgentChatClient.cs src/Rook/UI/Chat/AgentChatTab.cs src/Rook/UI/Chat/ChatTab.cs src/Rook/UI/Chat/RookChatPanel.cs src/Rook/UI/Chat/ConversationCloseCoordinator.cs src/Rook/UI/Chat/ChatServiceManager.cs src/Rook/UI/Chat/Resources/chat.html src/Rook/UI/Chat/Resources/chat.css src/Rook/UI/Chat/PersonaPicker.cs src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs src/Rook.Tests/UI/Chat/AgentChatApplyEnableTests.cs src/Rook.Tests/UI/Chat/RookChatPanelTests.cs src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs src/Rook.Tests/UI/Chat/ConversationCloseCoordinatorTests.cs src/Rook.Tests/UI/Chat/AgentChatImageAdmissionTests.cs
git commit -m "feat(chat): cut panel over to Prime ACP"
```

### Task 8: Install The Markdown-Only Rook Skill And Rook-Owned Host Binding

**Files:**
- Create: `installer/agent-assets/prime-skills/rook-full/SKILL.md`
- Create: `installer/agent-assets/prime-skills/rook-full/references/grasshopper.md`
- Create: `installer/agent-assets/prime-skills/rook-full/references/receipts-and-evidence.md`
- Create: `mcp_server/tests/test_rook_full_skill_contract.py`
- Modify: `src/RookNative/RookServer.h`
- Modify: `src/RookNative/RookServer.cpp`
- Modify: `mcp_server/src/rook/targeting.py`
- Modify: `mcp_server/tests/test_multi_instance_targeting.py`
- Create: `mcp_server/tests/test_rook_host_generation_targeting.py`
- Modify: `src/Rook.Tests/Capabilities/CapabilityDiscoverySourceTests.cs`

**Interfaces:**
- Produces: immutable `hostGenerationId`, required panel-locked `RookBinding`, exact Markdown skill behavior, and stable `target_unavailable` refusal before native dispatch.
- Consumes: Task 4 MCP environment and existing discovery/capabilities endpoints; PID remains a routing hint only.

- [ ] **Step 1: Write RED host-generation tests**

Model-free tests must prove discovery and `/capabilities` publish the same nonempty canonical UUID for one plugin lifetime, a new plugin lifetime gets a different UUID, PID equality does not authorize a mismatched generation, missing/malformed generation refuses, and the exact Rhino document serial is injected into every target-dependent request.

```python
def test_same_pid_wrong_host_generation_refuses_before_http(monkeypatch):
    lock = PanelTargetLock(
        mode="panel_locked",
        host_generation_id="11111111-1111-1111-1111-111111111111",
        process_id=1234,
        document_serial_number=55,
    )
    discovered = target(process_id=1234, host_generation_id="22222222-2222-2222-2222-222222222222")
    with pytest.raises(TargetUnavailable):
        select_target(lock, [discovered])
    assert http_dispatch_count() == 0
```

- [ ] **Step 2: Generate one host UUID per native server lifetime**

Store a canonical lowercase `D`-format UUID in `RookServer` state during plugin/server initialization. Publish that stored value independently in `WriteDiscoveryFile` and `BuildRookCapabilitiesDocument`; never copy it from panel input or environment. Keep `processId` for routing and diagnostics.

- [ ] **Step 3: Replace PID authority in `PanelTargetLock`**

The panel-locked environment is exactly:

```text
ROOK_MCP_TARGET_MODE=panel_locked
ROOK_MCP_TARGET_HOST_GENERATION_ID=<canonical UUID>
ROOK_MCP_TARGET_PROCESS_ID=<positive routing hint>
ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER=<positive serial>
ROOK_MCP_TOOL_PROFILE=readonly|full
```

Selection first uses the PID to narrow loopback discovery candidates, then requires exact `hostGenerationId` equality before contacting the target. The live capabilities response must confirm the same generation before target-dependent dispatch. Missing, malformed, or mismatched authority returns one stable `target_unavailable` envelope.

- [ ] **Step 4: Write the compact root skill and on-demand references**

`SKILL.md` must contain the persistent product contract: ordinary chat versus substantive goal criteria, `goal.get()` before model-created goals, Stop semantics, fresh Rook observation after reopen, required `mcp.call_tool("rook", tool_name, tool_arguments)` usage limited to `rook_tools_search`, `rook_tools_read`, and `rook_tools_call`, explicit JSON parsing of `{success,data}`, receipts/readiness/fenced evidence, truthful no-ops, no ambiguous replay, and reading references through IPython only when relevant. It must not contain campaign steps, hard-coded installed paths, Python packaging, or a permanent readonly persona.

The same tests freeze Prime's current MCP constraints as accepted product limits: 20 seconds for lazy server startup and 60 seconds for a call. The skill must encourage bounded calls and structured repair, but neither the skill nor RookChat may claim to override those Prime limits.

- [ ] **Step 5: Run model-free skill/target tests**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_rook_full_skill_contract.py tests/test_multi_instance_targeting.py tests/test_rook_host_generation_targeting.py -q

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "NativeGhBridge|DocumentContext" --no-restore
```

The .NET gate covers only managed code; native publication requires the later native build gate.

- [ ] **Step 6: Commit Task 8**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add installer/agent-assets/prime-skills/rook-full/SKILL.md installer/agent-assets/prime-skills/rook-full/references/grasshopper.md installer/agent-assets/prime-skills/rook-full/references/receipts-and-evidence.md src/RookNative/RookServer.h src/RookNative/RookServer.cpp mcp_server/src/rook/targeting.py mcp_server/tests/test_rook_full_skill_contract.py mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_rook_host_generation_targeting.py src/Rook.Tests/Capabilities/CapabilityDiscoverySourceTests.cs
git commit -m "feat(rook): bind ACP sessions to host generation"
```

### Task 9: Add One Grasshopper Classification And Same-Document Mutation Fence

**Files:**
- Create: `mcp_server/src/rook/gh_document_custody.py`
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/mcp_tool_profiles.py`
- Create: `mcp_server/tests/test_gh_document_custody.py`
- Modify: `mcp_server/tests/test_rookchat_tool_schema_golden.py`
- Modify: `mcp_server/tests/test_mcp_tool_profiles.py`
- Modify: `src/Rook/DocumentContext.cs`
- Create: `src/Rook/InternalBridge/GrasshopperDispatchContext.cs`
- Modify: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
- Modify: `src/Rook/InternalBridge/GrasshopperCore.cs`
- Modify: `src/Rook/InternalBridge/GhSolveReceiptRegistry.cs`
- Modify: `src/Rook/Handlers/GrasshopperHandler.cs`
- Modify: `src/Rook/Handlers/GrasshopperHandler.Readiness.cs`
- Create: `src/Rook.Tests/InternalBridge/GrasshopperDispatchContextTests.cs`
- Modify: `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`
- Modify: `src/Rook.Tests/InternalBridge/GhSolveReceiptRegistryTests.cs`
- Modify: `src/Rook.Tests/Handlers/GrasshopperHandlerReadinessTests.cs`
- Modify: `src/Rook.Tests/Handlers/GrasshopperDocumentLifecycleSourceTests.cs`
- Modify: `src/Rook.Tests/Handlers/GrasshopperTerminalMutationReceiptTests.cs`
- Modify: `src/Rook.Tests/Handlers/GrasshopperBehavioralSnapshotTests.cs`

**Interfaces:**
- Produces: `GhToolClassification`, `classify_gh_tool`, schema augmentation, dispatcher enforcement, internal managed dispatch context, exact `ghDocumentId` on observations/receipts, and fenced readiness/observation.
- Consumes: existing `PUBLIC_READONLY_TOOL_NAMES`, tool schemas, `DocumentContext`, and solve-receipt machinery; creates no broker GH state.

- [ ] **Step 1: Write one RED classification truth table**

```python
@pytest.mark.parametrize(("name", "scope"), [
    ("gh_component_search", "document_independent"),
    ("gh_status", "observation"),
    ("gh_snapshot", "observation"),
    ("gh_set_value", "mutation"),
    ("gh_update_script", "mutation"),
    ("gh_document_open", "transition"),
    ("gh_document_new", "transition"),
    ("gh_learn_directory", "transition"),
])
def test_gh_classification_has_one_owner(name, scope):
    assert classify_gh_tool(name).value == scope
```

Use one shared function everywhere. The classifier may use the existing readonly profile set to distinguish observations from mutations, plus closed sets only for document-independent queries and explicit transitions. Do not create separate schema, nested-call, and dispatcher mutation lists.

- [ ] **Step 2: Write RED schema and dispatcher tests**

For every classified mutation, both direct list/read schemas and the nested schema returned by `rook_tools_read` must advertise:

```json
"expectedGhDocumentId": {
  "type": "string",
  "description": "Canonical Grasshopper DocumentID observed immediately before this mutation."
}
```

and include it in `required`. Transition and document-independent tools do not advertise it. Tests must prove `rook_tools_call` cannot bypass it, an invalid/noncanonical GUID returns `invalid_arguments`, missing returns `gh_target_required`, no active doc returns `gh_target_unavailable`, and mismatch returns `gh_target_changed` before HTTP/managed side effects.

- [ ] **Step 3: Implement reserved-field handling once at dispatch**

```python
classification = classify_gh_tool(name)
expected = pop_reserved_expected_gh_document_id(arguments, classification)
validate_existing_tool_schema(name, arguments)
dispatch_context = GhDispatchContext(expected_gh_document_id=expected)
return await dispatch_tool(name, arguments, dispatch_context=dispatch_context)
```

Reject model-supplied internal dispatch-envelope keys. Pass the validated expected ID to the managed callback in a service-owned internal envelope distinct from ordinary tool arguments. `rook_tools_call` re-enters this exact public dispatch path; `rook_tools_read` renders the schema from this exact classifier.

- [ ] **Step 4: Write RED managed same-object tests**

```csharp
[Fact]
public void GuardedMutation_UsesTheDocumentCapturedDuringValidation()
{
    var intended = FakeGhDocument.WithId(Guid.Parse("11111111-1111-1111-1111-111111111111"));
    var decoy = FakeGhDocument.WithId(Guid.Parse("22222222-2222-2222-2222-222222222222"));
    var source = new SwitchingCanvasSource(intended, decoy);
    object? operatedOn = null;

    var result = GrasshopperDispatchContext.Execute(
        source,
        intended.DocumentId.ToString("D"),
        guardedMutation: true,
        captured => operatedOn = captured.Document);

    Assert.True(result.Success);
    Assert.Same(intended, operatedOn);
    Assert.Equal(1, source.ResolveCount);
}
```

Also test empty/non-GUID IDs, canonical parsed equality, absent canvas, mismatch, transitions, document-independent calls, and context restoration after exception.

- [ ] **Step 5: Capture, validate, and execute indivisibly on the UI thread**

At `ExecuteApiResponseCallback` entry on Rhino's UI thread:

```text
capture Grasshopper.Instances.ActiveCanvas once
-> capture canvas.Document once
-> read exact GH_Document.DocumentID as nonempty Guid
-> validate expected ID when classification requires it
-> enter GrasshopperDispatchContext with the same canvas/document
-> invoke the existing handler
-> restore prior context
```

Change `GrasshopperCore.ResolveContext` and handler helpers to consume the active `GrasshopperDispatchContext` instead of resolving `ActiveCanvas` again. `DocumentContext.GetDocument` must fail rather than fall back to `ActiveDoc` when a nonzero locked Rhino serial no longer resolves.

- [ ] **Step 6: Add identity to observations and receipts**

Use exact `GH_Document.DocumentID`, parsed as `Guid`, formatted `D` lowercase. `gh_status`, `gh_snapshot`, and other document-scoped observations return `ghDocumentId`. Every committed mutation receipt stores the actual ID from the captured managed context. No-op and unknown-commit outcomes remain truthful.

Readiness lookup/wait and receipt-fenced `gh_snapshot` capture the current document once and refuse with `gh_target_changed` when it differs from the receipt's document. Explicit `gh_document_open`, `gh_document_new`, and `gh_learn_directory` return the final active ID and do not require an expected ID.

- [ ] **Step 7: Run Python and managed GREEN tests**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_gh_document_custody.py tests/test_rookchat_tool_schema_golden.py tests/test_mcp_tool_profiles.py -q

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "GrasshopperDispatchContext|GhSolveReceiptRegistry|GrasshopperHandler" --no-restore
```

- [ ] **Step 8: Commit Task 9**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add mcp_server/src/rook/gh_document_custody.py mcp_server/src/rook/server.py mcp_server/src/rook/mcp_tool_profiles.py mcp_server/tests/test_gh_document_custody.py mcp_server/tests/test_rookchat_tool_schema_golden.py mcp_server/tests/test_mcp_tool_profiles.py src/Rook/DocumentContext.cs src/Rook/InternalBridge/GrasshopperDispatchContext.cs src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs src/Rook/InternalBridge/GrasshopperCore.cs src/Rook/InternalBridge/GhSolveReceiptRegistry.cs src/Rook/Handlers/GrasshopperHandler.cs src/Rook/Handlers/GrasshopperHandler.Readiness.cs src/Rook.Tests/InternalBridge/GrasshopperDispatchContextTests.cs src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs src/Rook.Tests/InternalBridge/GhSolveReceiptRegistryTests.cs src/Rook.Tests/Handlers/GrasshopperHandlerReadinessTests.cs src/Rook.Tests/Handlers/GrasshopperDocumentLifecycleSourceTests.cs src/Rook.Tests/Handlers/GrasshopperTerminalMutationReceiptTests.cs src/Rook.Tests/Handlers/GrasshopperBehavioralSnapshotTests.cs
git commit -m "feat(grasshopper): fence mutations to observed document"
```

### Task 10: Package One Immutable Prime Runtime And Preserve ACP Data Across Releases

**Files:**
- Create: `scripts/package-prime-acp-runtime.ps1`
- Create: `scripts/verify-prime-acp-runtime.py`
- Create: `scripts/tests/prime-acp-runtime.tests.ps1`
- Modify: `scripts/deploy-local-testing.ps1`
- Modify: `scripts/tests/deploy-local-testing-guards.tests.ps1`
- Modify: `scripts/write-chat-service-manifest.ps1`
- Modify: `installer/RookSetup.iss`
- Modify: `scripts/tests/release-installer-guards.tests.ps1`
- Modify: `installer/post_install.py`
- Modify: `installer/python_runtime_install.py`
- Create generated staging contract: `installer/runtime/prime/runtime-contract.json`
- Create generated staging manifest: `installer/runtime/prime/runtime-manifest.json`
- Modify: `.gitignore` only if the official staged artifact directory is generated and ignored
- Add: Prime-required license/notice files to the generated installer payload

**Interfaces:**
- Produces: official-shape immutable runtime at `ROOK_INSTALL_ROOT/prime/runtimes/<runtime-id>/`, an atomically replaced qualified-runtime pointer `current.json`, exact closed manifest, installed paths in the chat service manifest, and persistent data under `ROOK_DATA_DIR/rookchat/acp/v1/`.
- Consumes: Prime `9c25468b62c79fc4b1419d7800740e8e41e30467`, its `npm run build` and `scripts/pack-prime-agent-release.mjs`, Task 8 skill, and Task 4 runtime verifier.

- [ ] **Step 1: Write RED packaging guard tests**

Tests must assert:

```text
official Prime release pack command is invoked from the exact reviewed Prime commit
the complete official package shape is staged; no selected dist-file copy exists
runtime contract records platform, architecture, upstream commit, patch commit,
manifest identity, ACP protocol, Python SDK, goal skill, rook skill, and claim-key version
runtime paths are immutable siblings, never an in-place overwrite
installed executable is resolved only from the recorded runtime
sessions, presentation, and claims are outside replaceable app payloads
upgrade and rollback preserve historical runtimes and ACP data
uninstall with data retention does not remove ACP data
Prime licenses/notices are installed
```

- [ ] **Step 2: Package Prime through its supported release script**

`package-prime-acp-runtime.ps1` receives these mandatory parameters:

```powershell
param(
  [Parameter(Mandatory=$true)][string]$PrimeWorktree,
  [Parameter(Mandatory=$true)][string]$ExpectedPrimeCommit,
  [Parameter(Mandatory=$true)][string]$OutputRoot,
  [Parameter(Mandatory=$true)][string]$Platform,
  [Parameter(Mandatory=$true)][string]$Architecture
)
```

It verifies clean `HEAD == 9c25468b62c79fc4b1419d7800740e8e41e30467`, runs Prime's package build, invokes `node scripts/pack-prime-agent-release.mjs` with an explicit local output, installs/extracts the complete release package shape into a fresh staging directory, copies the manifest-bound Rook skill and required notices, and calls `verify-prime-acp-runtime.py`. It never edits the Prime worktree or copies hand-selected `dist` files.

- [ ] **Step 3: Implement the closed manifest algorithm**

For every admitted regular file except `runtime-manifest.json`, record forward-slash relative path, raw byte length, and uppercase SHA-256; sort paths ordinally. Refuse symlinks/reparse points and path escapes. Hash canonical UTF-8 JSON with sorted keys, compact separators, and LF to obtain `runtime_id`. Verify the actual public Prime executable path, goal skill subtree, Rook skill subtree, and all notices are included.

- [ ] **Step 4: Extend deploy and installer contracts**

The chat service manifest gains exact `primeRuntimeRoot`, `primeCurrentContract`, and persistent ACP data roots. Local deploy stages a new sibling runtime and verifies it before writing `current.json`; it never overlays an existing runtime. Inno Setup copies generated immutable runtime directories but does not list `ROOK_DATA_DIR/rookchat/acp/v1` in `[InstallDelete]`, `[UninstallDelete]`, or replacement cleanup.

Keep Prime credentials/settings/kernel in Prime's supported mutable user locations. Do not relocate or parse them into the immutable runtime.

- [ ] **Step 5: Run packaging tests without launching Prime**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
pwsh -NoProfile -File scripts/tests/prime-acp-runtime.tests.ps1
pwsh -NoProfile -File scripts/tests/deploy-local-testing-guards.tests.ps1
pwsh -NoProfile -File scripts/tests/release-installer-guards.tests.ps1
C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server/.venv/Scripts/python.exe scripts/verify-prime-acp-runtime.py --contract installer/runtime/prime/runtime-contract.json --manifest installer/runtime/prime/runtime-manifest.json --verify-only
```

The verifier reads bytes only. No Prime executable, provider, Rhino, or installer launches.

- [ ] **Step 6: Commit Task 10**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add scripts/package-prime-acp-runtime.ps1 scripts/verify-prime-acp-runtime.py scripts/tests/prime-acp-runtime.tests.ps1 scripts/deploy-local-testing.ps1 scripts/tests/deploy-local-testing-guards.tests.ps1 scripts/write-chat-service-manifest.ps1 installer/RookSetup.iss scripts/tests/release-installer-guards.tests.ps1 installer/post_install.py installer/python_runtime_install.py installer/runtime/prime/runtime-contract.json installer/runtime/prime/runtime-manifest.json .gitignore
git commit -m "build(chat): package immutable Prime ACP runtime"
```

### Task 11: Complete The ChatRunner Non-Port And Installed-Product Static Gate

**Files:**
- Delete: `scripts/chatrunner_headless_qualification.py`
- Delete: `mcp_server/tests/test_chatrunner_headless_qualification.py`
- Delete: `mcp_server/tests/test_chatrunner_mcp_capability_gateway.py`
- Delete: `mcp_server/tests/test_rookchat_worker_first_csharp_integration.py`
- Modify: `mcp_server/tests/test_rookchat_visible_dispatchability.py`
- Modify: `mcp_server/tests/test_rookchat_tool_transcripts.py`
- Modify: `docs/CURRENT_ARCHITECTURE.md`
- Modify: `README.md`
- Modify: `QUICK_START.md`
- Modify: `AGENT_SETUP.md`
- Create: `scripts/verify-rookchat-acp-cutover.py`
- Create: `mcp_server/tests/test_rookchat_acp_cutover.py`

**Interfaces:**
- Produces: one shipped RookChat backend, explicit non-port guard, and truthful user/developer documentation.
- Consumes: Tasks 6-10; preserves non-chat Anthropic credential consumers until separately migrated.

- [ ] **Step 1: Write the RED non-port scanner**

The scanner fails if installed/source chat surfaces contain imports, routes, or launch paths for:

```text
ChatRunner
ConversationStore from rook.agent.chat.conversation_store
/agent/chat/personas
/agent/chat/model
ChatRunner credential-health routes or provider-key checks
worker-first chat execution
private Prime RPC or AgentConnection
Prime daemon or daemon socket product transport
PID/process-start/PowerShell process authority
backend registry, availableBackends, or backend selector
```

It also fails if any C# source imports ACP, any non-Python product source imports `agent-client-protocol`, or product runtime imports an external evaluator/campaign harness.

- [ ] **Step 2: Audit every candidate deletion before applying it**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
rg -n "ChatRunner|ConversationStore|model_status|prompt_builder|worker.first|/agent/chat/(personas|model|start|message|stop|ui-response)" src mcp_server installer scripts
rg -n "tool_result_view|tool_contracts|execution_policy|personas" mcp_server/src
```

The expected ChatRunner-only residue is the qualification script and three tests listed in this task; delete those after the audit proves they have no retained caller. Update the two generic RookChat contract tests to exercise ACP-projected tool data without importing ChatRunner. Retain shared `tool_result_view`, `tool_contracts`, `execution_policy`, persona infrastructure used by planner/spawn, knowledge routes, authenticated HTTP middleware, service discovery, and generic panel rendering. If the audit finds another production owner beyond this exact list, stop for plan correction instead of broadening deletion opportunistically.

- [ ] **Step 3: Update architecture and user docs**

Document one Prime ACP implementation, Prime-owned login via interactive `/login`, new-conversation model/reasoning selection, reopen behavior, target-unavailable behavior, image-history limits, release-level rollback, preserved data roots, and the explicit `session_recovery_required` limitation after service crash. Do not advertise compaction or IPython restoration guarantees.

- [ ] **Step 4: Run static and full offline unit gates**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_rookchat_acp_cutover.py tests/test_chat_acp_sdk_contract.py tests/test_chat_acp_storage.py tests/test_chat_acp_presentation.py tests/test_chat_acp_images.py tests/test_chat_prime_runtime.py tests/test_chat_acp_client.py tests/test_chat_acp_process.py tests/test_chat_acp_conversation.py tests/test_chat_acp_two_service.py tests/test_chat_server.py tests/test_chat_integration.py tests/test_rook_full_skill_contract.py tests/test_rook_host_generation_targeting.py tests/test_gh_document_custody.py -q

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore
C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server/.venv/Scripts/python.exe scripts/verify-rookchat-acp-cutover.py --root C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
```

- [ ] **Step 5: Commit Task 11**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add scripts/chatrunner_headless_qualification.py mcp_server/tests/test_chatrunner_headless_qualification.py mcp_server/tests/test_chatrunner_mcp_capability_gateway.py mcp_server/tests/test_rookchat_worker_first_csharp_integration.py mcp_server/tests/test_rookchat_visible_dispatchability.py mcp_server/tests/test_rookchat_tool_transcripts.py mcp_server/tests/test_rookchat_acp_cutover.py docs/CURRENT_ARCHITECTURE.md README.md QUICK_START.md AGENT_SETUP.md scripts/verify-rookchat-acp-cutover.py
git commit -m "refactor(chat): remove ChatRunner product path"
```

### Task 12: Build The External A-E Qualification Ladder With Hard Review Stops

**Files:**
- Create: `scripts/qualification/rookchat_prime_acp_common.py`
- Create: `scripts/qualification/rookchat_prime_acp_offline.py`
- Create: `scripts/qualification/rookchat_prime_acp_slice_c.py`
- Create: `scripts/qualification/rookchat_prime_acp_slice_d.py`
- Create: `scripts/qualification/rookchat_prime_acp_slice_e.py`
- Create: `scripts/qualification/fixtures/deterministic_provider.py`
- Create: `scripts/qualification/protocols/rookchat-prime-acp-offline-v1.json`
- Create: `scripts/qualification/protocols/rookchat-prime-acp-slice-c-v1.json`
- Create: `scripts/qualification/protocols/rookchat-prime-acp-slice-d-v1.json`
- Create: `scripts/qualification/protocols/rookchat-prime-acp-slice-e-v1.json`
- Create: `mcp_server/tests/test_rookchat_prime_acp_qualification.py`
- Create after each authorized execution: `docs/superpowers/reports/<date>-rookchat-prime-acp-<gate>.md`

**Interfaces:**
- Produces: external, create-only, finite qualification artifacts for combined offline A+B and separately authorized C, D, and E.
- Consumes: installed artifacts and public product boundaries only; no qualification module is imported by `mcp_server/src/rook`.

- [ ] **Step 1: Write RED protocol-custody tests**

Each protocol must contain exact schema/version, clean implementation commit, installed runtime/skill manifests, prompt/input hashes, wall-clock/token/process-close limits, target/profile identity, evaluator identity when applicable, fresh evidence root, and a one-execution version. The runner refuses existing evidence roots, hash drift, missing limits, mismatched commits, and any product import of `scripts/qualification`.

Each frozen live version executes once and its result is immutable. Any correction requires a newly versioned protocol, fresh evidence root, and separate authorization; the runner never retries or overwrites a failed version.

- [ ] **Step 2: Implement one finite common runner**

`rookchat_prime_acp_common.py` may hash inputs, create evidence roots, write bounded JSON results, and own directly launched qualification processes. It must not poll the Windows process table, use PowerShell process probes, kill by name/PID discovery, retry, alter a timeout after failure, or become a product dependency.

- [ ] **Step 3: Implement Slice A against the fake ACP agent**

Exercise the exact C#-equivalent HTTP boundary and all model-free cases listed in spec section 15.1: protocol/capability admission, first-turn publication, two-service claim contention, crash claim preservation, failed/uncertain spawn, concurrent update order, generation fences, overflow cancellation, permission policy, cache/image/model arguments, MCP injection, Rook envelope projection, GH schemas, bounds, 20-second startup/60-second call contract projection, and close failures.

- [ ] **Step 4: Implement Slice B against the installed Prime artifact and deterministic provider**

Use an isolated environment with exact `PRIME_AGENT_CODING_AGENT_DIR`, `HOME`, and `USERPROFILE` beneath the fresh evidence root; an isolated kernel path; a local deterministic provider; and a unique daemon-socket tripwire. The installed runtime must execute `initialize -> session/new -> session/prompt -> session/close -> EOF`, materialize the assigned file, reopen the same file, and answer consistently using prior context. Exercise lazy MCP start, representative Rook calls completing inside Prime's fixed 20-second startup and 60-second call limits, cancellation, MCP cleanup, fresh MCP establishment after reopen, manifest identity, required flags, zero tripwire contact, and clean direct-child exit. Product code still reads only the first-line header envelope.

- [ ] **Step 5: Run only model-free tests, then commit the frozen qualification code**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_rookchat_prime_acp_qualification.py -q

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add scripts/qualification mcp_server/tests/test_rookchat_prime_acp_qualification.py
git commit -m "test(chat): freeze ACP qualification ladder"
```

- [ ] **Step 6: STOP at the combined A+B pre-contact review gate**

Do not execute `rookchat_prime_acp_offline.py` yet. Present the frozen runner/protocol hashes, implementation commit, installed runtime manifest, tests, and proof that evidence roots are absent. Independent approval must explicitly authorize one A+B execution.

- [ ] **Step 7: After authorization, execute A+B exactly once and stop**

Run the exact independently reviewed command only. Whether it passes or fails, make the evidence root read-only, hash every bounded evidence file, write the A+B report, commit only that report, and stop for independent review. Do not continue to Slice C automatically.

- [ ] **Step 8: Prepare and review Slice C without executing it**

Freeze one tiny image whose answer depends on visible content, its SHA-256, prompt, a known vision-capable fully qualified subscription model, reasoning value, exact installed runtime, time/token/close limits, and fresh evidence root. The product does not inspect `auth.json`; external evidence may claim OAuth only if separate nonsecret Prime-owned metadata proves it. Otherwise report a Prime-managed authenticated subscription call.

STOP for explicit Slice C authorization. After one authorized execution, seal evidence and stop for review. No Rook/Rhino/GH server participates.

- [ ] **Step 9: Prepare and review Slice D without executing it**

Freeze one deterministic Rhino/GH fixture and one readonly prompt. Record before/after structural snapshots, target identity, absence of mutation receipts, exact profile, and one prompt only. Fresh-MCP-after-reopen and readonly mutation refusal remain model-free; do not add a second stochastic prompt.

STOP for explicit Slice D authorization. After one authorized execution, seal evidence and stop for review.

- [ ] **Step 10: Prepare and review Slice E without executing it**

Seed the established adjustable X-axis point-row defect before conversation creation. Freeze the user prompt, baseline identities, full profile, model/reasoning, limits, evaluator source/hash, and fresh evidence root. The Actor's exact ending is:

```text
last actual committed mutation/restoration receipt R
-> readiness bound to R
-> fenced observation bound to R
-> no further Rook calls
-> dedicated goal.complete() tool cell
-> final text only
-> ACP prompt settlement
-> seal Actor trace, R, and fenced evidence
-> separately identified silent evaluator
```

Evaluator receipts are separately namespaced and cannot satisfy Actor criteria. Any Actor tool call after `goal.complete()` makes the combined result incomplete.

STOP for explicit Slice E authorization. After one authorized execution, preserve an honest pass or incomplete result, seal evidence, and stop for review. Never prompt-repair or rerun the same frozen version.

- [ ] **Step 11: Run final source gates after the ladder is authored**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest -q

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore
git diff --check
git status --short
```

Native compilation, installed artifact execution, provider contact, Rhino contact, and GH mutation are credited only to their separately executed and sealed gates, never to these source tests.

## Implementation Review Sequence

1. Review Tasks 1-5 together as the Python ACP ownership foundation. No installed Prime execution is required for this review.
2. Review Tasks 6-9 as the product cutover and Rook/GH authority boundary. Run fake/model-free tests only.
3. Review Tasks 10-12's authored packaging, replacement, data-retention, and qualification code as one offline pre-contact gate covering technical Slices A and B. Build verification may produce artifacts but must not launch Prime.
4. Review the frozen combined A+B package, then authorize at most one execution.
5. Review sealed A+B evidence before authorizing Slice C.
6. Review sealed C evidence before authorizing Slice D.
7. Review sealed D evidence before authorizing Slice E.
8. Review sealed E evidence before any release cutover decision.

## Final Acceptance Checklist

- [ ] One product path exists: C# panel -> authenticated HTTP -> Python ACP SDK -> exact installed Prime `--mode acp --no-daemon` -> standard ACP MCP `rook` -> Rook.
- [ ] Every durable association is complete, materialized, create-only, and contains a validated Prime header ID.
- [ ] One metadata-free non-expiring claim fences launch/Delete; it is never reclaimed automatically.
- [ ] Cleanup uses only the SDK/directly owned process handle and preserves the claim unless child exit is observed.
- [ ] Prompt settlement, presentation delivery, Prime goals, Rook operation results, and semantic acceptance remain distinct.
- [ ] All live and cached representations meet the exact bounds and persistence rules.
- [ ] Prime owns credentials, settings, transcript, goals, compaction, IPython, and model context.
- [ ] Rook host generation and Rhino serial are authoritative; PID is routing-only.
- [ ] GH mutation schemas visibly require one centrally enforced optimistic document token; receipts and fenced reads bind the actual document ID.
- [ ] The installed Prime artifact and Markdown skill are closed-manifest verified and historical runtimes/data survive update, rollback, and data-retaining uninstall.
- [ ] ChatRunner, backend selection, private RPC, daemon topology, worker auth, leases, process probes, kernel RPC, and Task 7 code are absent.
- [ ] Combined offline A+B and separately authorized C/D/E gates preserve immutable, bounded evidence without retries or overwrite.
