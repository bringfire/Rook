# RookChat Prime ACP Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ChatRunner with one product implementation in which the existing RookChat panel talks through the Python chat service to one directly owned, daemon-free Prime ACP process per open conversation, while preserving Rook's target, mutation, receipt, readiness, and evidence authority.

**Architecture:** C# remains the user-input and presentation client of the authenticated local HTTP service. The Python service uses the official Python ACP SDK to own one Prime process/ACP connection, a complete durable association, a non-expiring `open.claim`, and bounded disposable presentation history; Prime remains the sole conversation and reasoning authority, and Rook remains the sole host-operation authority. Standard ACP MCP injection supplies a manifest-bound Markdown-only `rook-full` skill and the service-owned `rook` stdio server; no private Prime RPC, daemon topology, backend abstraction, or ChatRunner fallback survives cutover.

**Tech Stack:** C#/.NET 8, 7, and 4.8 with Eto/WebView2; Python 3.10+ with `aiohttp` and exact `agent-client-protocol==0.12.1`; ACP 1.3 as implemented by the pinned Prime artifact; MCP 1.28.1; Rhino 8 C++ SDK; Grasshopper managed bridge; PowerShell/Inno Setup release tooling; pytest/xUnit.

**Spec:** `docs/superpowers/specs/2026-09-01-rookchat-prime-acp-replacement-design.md` at frozen baseline `7c876d5c34f8d557ebd8cd06b93c07307c730234` (SHA-256 `676340C3CAFA75A10B1DEFBA38B722B66279E13BEC27B169FFE1DA230B1E3E4C`).

## Global Constraints

- This plan is authored against frozen specification baseline `7c876d5c34f8d557ebd8cd06b93c07307c730234`. Implementation begins from the later exact approved plan commit named in the implementation `/goal`; its lineage must contain that baseline. Do not reset to the baseline or replay superseded RPC Tasks 0-7.
- Prime commit `9c25468b62c79fc4b1419d7800740e8e41e30467` is the reviewed daemon-free precursor over upstream `c718bf3c30fd8da206ed551837cbb54f7ad15948`. Before the Task 10 release build, amend that precursor into one final independently reviewed commit whose parent remains the exact upstream baseline and whose only additional production changes are platform-aware kernel-interpreter resolution and inclusion of `dist/prime-agent-runtime` in Prime's standalone artifact. Do not create a patch stack or make any other Prime change.
- Preserve every quarantined Task 7 worktree and retained evidence byte-for-byte. Never copy product code from those worktrees.
- Pin `agent-client-protocol==0.12.1` exactly and use its public `spawn_agent_process`, `ClientSideConnection`, schema models, cancellation notification, and close APIs.
- Launch the exact installed Prime executable with an argument array and `--mode acp --no-daemon`; never use a shell, global npm, a daemon socket, PID discovery, PowerShell probing, process scanning, or process-name cleanup. The Prime and Rook MCP executable paths are absolute and never selected through `PATH`. The sole intentional exception is upstream Prime's supported kernel bootstrap lookup for `uv`: RookChat prepends the exact manifest-bound `tools/uv` directory, and qualification proves that executable was selected before any ambient entry.
- Persist associations, not broker lifecycle. Prime JSONL is the only authoritative transcript/goal/settings/compaction store.
- A durable association is create-only, complete, materialized, has a nonempty Prime header ID, and is reopenable only when no `open.claim` exists and custody checks pass.
- The atomic non-expiring `open.claim` has no metadata or recovery logic. Remove it only after the directly owned Prime child is observed exited, or when launch positively proves no child was created.
- Never replay an interrupted prompt, tool call, or mutation. Re-observe authentic Rook state after every reopen before dependent work.
- Keep all current-turn and presentation representations within the exact limits in the approved spec; persist no thoughts, raw ACP events, image bytes, unrestricted `_meta`, or credentials.
- Prime owns authentication. RookChat never accepts `--api-key`, reads `auth.json`, or forwards credentials loaded from Rook's installed `.env`.
- New conversations may pass a fully qualified `--model` and one of `off|minimal|low|medium|high|xhigh|max`; reopen passes neither override.
- The installed `rook-full` package is Markdown-only. Do not add a Rook-owned Python facade or contract-specific kernel.
- The immutable Prime runtime carries official `uv` 0.12.3 at fixed relative path `tools/uv/uv.exe` and the final Prime build's complete `dist/prime-agent-runtime` subtree. Source, license, executable, and subtree custody share the same closed manifest. Prime remains the sole owner of its ordinary mutable kernel environment. Remove every inherited `UV_*` key case-insensitively and insert only the six product-owned values derived from `ROOK_DATA_DIR`; no ambient kernel override, package-root override, virtual environment, uv policy, or Rook-venv `uv` is runtime authority.
- Prime release builds use only the separately provisioned MSYS2 20260611 artifact at `C:/UDEV/RookBuildTools/prime-acp/msys2-20260611-v1/`, containing manifested `root/**` and sibling `build-toolchain-contract.json`. No build may reach `npm ci` until an independent review supplies the exact `ExpectedBuildToolchainContractSha256`; the shared `C:/msys64` and customer installations are never involved.
- One service-owned ACP MCP declaration named exactly `rook` uses the installed service's already verified exact `sys.executable -m rook` boundary without `PATH` fallback. Its closed environment, profile, and immutable host/Rhino binding come from installed service configuration and the durable association, not from the portable Prime runtime manifest. The verified association working directory is supplied through `session/new.cwd` because ACP stdio declarations have no working-directory field.
- Prime's accepted MCP operating limits remain 20 seconds for server startup and 60 seconds for a tool call. Representative Rook operations must qualify within them; this plan adds no facade or Prime timeout patch.
- Preserve full Rook authoring. Grasshopper uses dynamic document context with centrally advertised and enforced `expectedGhDocumentId` optimistic concurrency, not permanent GH binding or hostile-code containment.
- ChatRunner is deleted at cutover. Do not add a backend registry, selector, common backend interface, feature flag, or runtime fallback.
- Qualification code and evidence remain external to product runtime. No live slice executes without its explicit review gate and separate authorization.
- Before live Slice D, promote one exact clean implementation commit through the existing MSVC 14.44 native build, managed build, local deployment, and installed-artifact hash verifier. Slices D and E reverify those installed identities before contact.
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
    rook_skill_system_prompt: str
    uv_version: str
    uv_executable_path: Path
    prime_agent_runtime_path: Path
    prime_agent_runtime_manifest_sha256: str
    claim_key_version: int

def load_and_verify_runtime(install_root: Path, runtime_id: str) -> PrimeRuntimeContract:
    raise NotImplementedError
def build_prime_argv(contract: PrimeRuntimeContract, session_path: Path,
                     requested_model: str | None,
                     requested_reasoning: str | None,
                     reopen: bool) -> tuple[str, ...]:
    raise NotImplementedError
def validate_windows_launch_argv(argv: tuple[str, ...]) -> None:
    raise NotImplementedError
def build_prime_child_env(base_environment: Mapping[str, str],
                          contract: PrimeRuntimeContract) -> dict[str, str]:
    raise NotImplementedError
def build_rook_mcp_server(binding: RookBinding) -> McpServerStdio:
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
    saved_document_directory: str | None
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

@dataclass
class ActivePromptSupervisor:
    generation: PromptGeneration
    result_task: asyncio.Task[PromptResult] = field(init=False)
    def request_cancel(self, source: str) -> bool:
        """Set one absorbing cancellation signal; return True only for the first caller."""
        raise NotImplementedError

class AcpConversationManager:
    async def create(self, request: CreateConversationRequest) -> ConversationView:
        raise NotImplementedError
    async def reopen(self, conversation_id: str) -> ConversationView:
        raise NotImplementedError
    async def start_prompt(self, conversation_id: str, prompt: PromptInput,
                           sink: PresentationSink) -> ActivePromptSupervisor:
        raise NotImplementedError
    async def request_cancel(self, conversation_id: str, source: str) -> bool:
        """Signal the active prompt once; return False when no active prompt exists."""
        raise NotImplementedError
    async def close(self, conversation_id: str) -> CloseResult:
        raise NotImplementedError
    async def delete(self, conversation_id: str) -> DeleteResult:
        raise NotImplementedError
    async def shutdown(self) -> tuple[CloseResult, ...]:
        raise NotImplementedError
```

```csharp
// src/Rook/UI/Chat/AgentChatClient.cs
public sealed record CreateConversationRequest(
    uint DocumentSerialNumber,
    string CapabilityProfile,
    string? SavedDocumentDirectory,
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

## Execution-Custody Table

| Boundary | Producer -> exact artifact/value -> consumer | Lifetime owner | Failure behavior | Causal proof |
| --- | --- | --- | --- | --- |
| Product contract | Runtime manifest verifier -> the same retained `SKILL.md` byte buffer, strict UTF-8 decoded once -> Prime's single `--append-system-prompt <body>` argument; `--skill <verified-directory>` remains separate | `PrimeRuntimeContract` for one launch | Missing/hash-mismatched/non-UTF-8/oversized bytes or oversized rendered Windows argv refuse before spawn | Launch test asserts exact body equality, proves neither filename nor path is substituted, and covers both size bounds |
| ACP process | Python service -> absolute manifest-bound argv plus explicit piped stdin/stdout/stderr -> official SDK transport and Prime | `OwnedAcpProcess`; one bounded stderr drain task for the child's lifetime | Drain cannot start or fails: no retry, mark transport failed, retire exact child; normal/forced retirement awaits or cancels the drain only after child exit handling | Fake agent writes beyond normal pipe capacity while prompt and clean EOF still settle |
| Prompt | Authenticated HTTP handler -> `ActivePromptSupervisor` generation/result -> ACP prompt owner | Python service resident map, independent of HTTP task | Waiter cancellation/disconnect signals idempotent cancel once; it never cancels or clears the supervisor; uncertain settlement retires exact child | Cancel HTTP waiter during hanging fake prompt; prove one ACP cancel, bounded settlement/retirement, no orphan, no premature idle |
| Retirement | Resident map -> atomic detach under the admission lock -> one locally retained resident/process handle | Close, live Delete, or service shutdown operation | Once detached, prompt/reopen admission refuses; only the detached generation is cancelled and retired | Barriers prove close-first refusal, prompt-first capture, shared Delete/shutdown detachment, and stale-generation isolation |
| First turn | Provisional in-memory association -> materialized Prime header -> create-only complete association -> immutable projected turn | Prompt supervisor through settlement; association store and presentation cache after publication | Invalid/missing file or failed association publication leaves no durable association/cache; no adoption or replay | Failure injection at file creation, header validation, association publish, and cache publish boundaries |
| Installed product | Exact clean implementation commit -> MSVC 14.44 native build + managed build + existing local deployment -> installed native/managed/Python/skill/Prime hash set -> Slices D/E | Existing deployment workflow; external promotion evidence after deployment | Any build/deploy/hash mismatch refuses live authorization; source identity alone earns no credit | Hash source outputs against installed destinations and reverify all identities immediately before D/E |
| Rook evidence | ACP-delivered tool content -> successfully parsed exact Rook `{success, data}` JSON envelope -> bounded presentation/evidence classification | Current prompt projection only; Rook receipts/evidence remain authoritative | Enclosing IPython/tool-card completion without a parsed envelope certifies nothing; transport loss before envelope is unknown and never replayed | Completed tool card without envelope remains non-authoritative; exact success/refusal envelopes survive projection |

---

### Task 1: Pin The ACP SDK And Build The Model-Free Agent Fixture

**Files:**
- Modify: `mcp_server/pyproject.toml`
- Modify: `mcp_server/uv.lock`
- Create: `mcp_server/tests/fixtures/fake_acp_agent.py`
- Create: `mcp_server/tests/test_chat_acp_sdk_contract.py`

**Interfaces:**
- Produces: exact Python SDK dependency and a deterministic ACP process fixture supporting `initialize`, `session/new`, `session/prompt`, `session/cancel`, `session/close`, source-ordered concurrent updates, permissions, image capture, MCP declaration capture, controlled hangs, configurable stderr volume, and clean EOF.
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

@pytest.mark.asyncio
async def test_fake_agent_can_emit_ordered_updates_and_more_than_pipe_capacity(fake_agent_process):
    result = await fake_agent_process.run_script(
        updates=[{"kind": "agent_message_chunk", "text": str(i)} for i in range(64)],
        stderr_bytes=2 * 1024 * 1024,
        stop_reason="end_turn",
    )
    assert result.received_message_text == [str(i) for i in range(64)]
    assert result.stderr_bytes_written == 2 * 1024 * 1024
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

The fixture writes configured stderr in fixed chunks before and during prompt handling, journals the exact source order of updates it emits, and never imports Rook product modules, contacts a network endpoint, or spawns descendants. Task 4 owns the consuming drain test; this task only proves the fixture can generate the pressure deterministically.

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
- Produces: `AcpDataPaths`, `RookBinding`, `PrimeSessionHeader`, `ConversationAssociation`, `ProvisionalAssociation`, `AssociationStore`, `OpenClaim`, `atomic_publish_noreplace(final_path: Path, payload: bytes) -> None`, and stable error codes `session_unavailable`, `runtime_unavailable`, `working_directory_unavailable`, `session_recovery_required`, `initialization_failed`, and `publication_unsupported`.
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

def test_atomic_publish_noreplace_preserves_existing_bytes(tmp_path):
    destination = tmp_path / "association.json"
    destination.write_bytes(b"original")
    with pytest.raises(PublicationAlreadyExists):
        atomic_publish_noreplace(destination, b"replacement")
    assert destination.read_bytes() == b"original"
```

Also cover canonical root containment, bounded first physical line, strict UTF-8, object/type/version/nonempty-ID/cwd checks, symlink and Windows reparse refusal, generated UUID/path ownership, atomic complete publication, re-read after claim, Delete ordering, two-process no-replace contention, unsupported-platform refusal, and byte preservation on every refusal.

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

All association and immutable turn-file publication goes through `atomic_publish_noreplace`. The product's supported implementation is explicitly Windows-only: write canonical UTF-8 JSON plus LF to a same-directory temporary file opened create-only, flush and `fsync` it, then use Windows same-volume `os.rename`, whose no-replacement behavior is proven by a two-process causal test. Catch `FileExistsError`, remove only the owned temporary file, and preserve destination bytes. When `os.name != "nt"`, raise `PublicationUnsupported` before creating the temporary file; do not silently assume POSIX `os.rename` has no-replace semantics. A future platform requires its own tested primitive.

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
- Create: `mcp_server/src/rook/agent/chat/acp_rook_results.py`
- Create: `mcp_server/tests/test_chat_acp_presentation.py`
- Create: `mcp_server/tests/test_chat_acp_images.py`
- Create: `mcp_server/tests/test_chat_acp_rook_results.py`

**Interfaces:**
- Produces: `PromptGeneration`, `ProjectedEvent`, `BoundedPromptProjection`, `PresentationQueue`, `PresentationSink`, `PresentationCache`, `ValidatedImage`, `validate_images`, `map_stop_reason`, `ParsedRookResult`, and `parse_rook_envelope`.
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
async def test_projection_preserves_sequential_source_order_and_timeout_as_overflow():
    queue = PresentationQueue(max_events=256, max_utf8_bytes=4 * 1024 * 1024)
    projection = BoundedPromptProjection(generation=PromptGeneration(3, "acp-1", "prompt-9"), queue=queue)
    for value in range(20):
        await projection.accept(message_chunk("m", str(value)))
    assert [row.text for row in await queue.drain()] == [str(value) for value in range(20)]

def test_turn_file_is_create_only_and_evicts_complete_oldest_turns(cache):
    for sequence in range(1, 258):
        cache.publish(turn(sequence=sequence, size=260_000))
    loaded = cache.load()
    assert len(loaded.turns) <= 256
    assert loaded.earlier_history_omitted is True

def test_completed_tool_card_without_exact_rook_envelope_certifies_nothing():
    assert parse_rook_envelope('{"toolStatus":"completed"}') is None

def test_exact_rook_failure_envelope_remains_failure():
    parsed = parse_rook_envelope('{"success":false,"data":"target_unavailable"}')
    assert parsed is not None
    assert parsed.success is False
    assert parsed.data == "target_unavailable"
```

Add explicit tests for queue 256-event/4-MiB boundaries, the one-second whole callback deadline, generation fencing, allowed message/thought coalescing only, no tool coalescing, prompt-owner overflow signal, panel disconnect, independent cache and drain results, user/assistant accumulator limits, fallback publication, immutable-until-eviction files, corruption, sequence derivation without a ledger, and the exact `_meta` limits. This module proves deterministic projection behavior only; Task 4 proves ACP callback source order through the real SDK path and the fake agent's journal.

`ParsedRookResult` retains the Boolean `success` and the JSON `data` value without narrowing `data` to an object; current Rook results legitimately use objects, arrays, strings, numbers, Booleans, and null. `parse_rook_envelope` accepts only ACP-delivered tool content that decodes as a JSON object containing a Boolean `success` and a `data` key. Malformed, truncated, non-object, or merely quoted/reflected text returns `None`. Tool-specific receipts inside object data earn authority only after their existing closed Rook validators accept them. A `success: false` envelope remains a Rook failure even when ACP reports the enclosing IPython/tool card as completed. Tool-card state is presentation-only and never certifies a mutation, receipt, or Rook success.

- [ ] **Step 2: Run RED**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_chat_acp_presentation.py tests/test_chat_acp_images.py tests/test_chat_acp_rook_results.py -q
```

Expected: all three product modules are missing.

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

The ACP `session_update` callback owns the source ordinal. Its first statement synchronously resolves the fenced prompt projection and increments that projection's counter; its first `await` is entry into the same projection's ordering gate:

```python
async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
    projection, source_ordinal = self._assign_source_ordinal(session_id)
    await projection.accept_source_update(source_ordinal, update)
```

No HTTP caller, fake agent, or test supplies the ordinal. The ordering gate is acquired immediately after assignment; callback work that can suspend occurs only after acquisition. Every callback acquires that one per-prompt gate, projects, coalesces, and admits within the same one-second deadline. On timeout it sets one absorbing overflow flag and returns; it never calls ACP. Preserve partial assistant text on cancellation. Every truncated user, assistant, tool, or metadata field includes a visible marker and original UTF-8 byte count. If normal projection fails, the cache must attempt one create-only fallback no larger than 8 KiB with sequence, stop reason, available original counts, and the exact approved sentence: `Turn presentation was unavailable. Prime retains the authoritative conversation state.` A missing, stale, or corrupt cache renders `presentation history unavailable` without affecting Prime reopen. Reset known goal/compaction indicators to unknown for every process/session replacement, and record omitted unknown-`_meta` record/key/value counters after the closed limits.

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
./.venv/Scripts/python.exe -m pytest tests/test_chat_acp_presentation.py tests/test_chat_acp_images.py tests/test_chat_acp_rook_results.py -q

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add mcp_server/src/rook/agent/chat/acp_presentation.py mcp_server/src/rook/agent/chat/acp_images.py mcp_server/src/rook/agent/chat/acp_rook_results.py mcp_server/tests/test_chat_acp_presentation.py mcp_server/tests/test_chat_acp_images.py mcp_server/tests/test_chat_acp_rook_results.py
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
- Produces: verified `PrimeRuntimeContract`, exact bounded launch argv/environment/MCP declaration, stable `runtime_command_line_too_long`, `RookChatAcpClient`, and `OwnedAcpProcess` with `initialize`, `new_session`, `prompt`, `cancel`, `close_session`, and `retire`.
- Consumes: Task 1 official SDK, Task 2 claim, Task 3 projection; never imports or shells into Prime.

- [ ] **Step 1: Write RED runtime-custody tests**

```python
def test_new_launch_uses_exact_flags_and_reopen_has_no_model_override(contract, association):
    new = build_prime_argv(contract, Path(association.session_path), "anthropic/claude-x", "high", reopen=False)
    assert new[:3] == (str(contract.executable_path), "--mode", "acp")
    assert "--no-daemon" in new
    assert "--no-skills" in new
    assert pairs(new, "--skill") == [str(contract.goal_skill_path), str(contract.rook_skill_path)]
    assert pair(new, "--append-system-prompt") == contract.rook_skill_system_prompt
    assert str(contract.rook_skill_path / "SKILL.md") not in new
    assert pair(new, "--resume") == association.session_path
    assert pair(new, "--model") == "anthropic/claude-x"
    assert pair(new, "--thinking") == "high"
    reopened = build_prime_argv(contract, Path(association.session_path), None, None, reopen=True)
    assert "--model" not in reopened and "--thinking" not in reopened
    assert pair(reopened, "--append-system-prompt") == contract.rook_skill_system_prompt
    assert str(contract.rook_skill_path / "SKILL.md") not in reopened

def test_prime_child_environment_uses_pre_dotenv_snapshot(pre_dotenv_env, contract):
    os.environ["ROOK_INSTALLED_DOTENV_SENTINEL"] = "must-not-pass"
    child = build_prime_child_env(pre_dotenv_env, contract)
    assert "ROOK_INSTALLED_DOTENV_SENTINEL" not in child
    assert "ANTHROPIC_API_KEY" not in child or child["ANTHROPIC_API_KEY"] == pre_dotenv_env.get("ANTHROPIC_API_KEY")

def test_complete_rendered_windows_argv_refuses_before_spawn(contract, association):
    oversized = dataclasses.replace(
        contract,
        rook_skill_system_prompt="x" * MAX_WINDOWS_COMMAND_LINE_UTF16_UNITS,
    )
    with pytest.raises(PrimeLaunchError, match="runtime_command_line_too_long"):
        build_prime_argv(oversized, Path(association.session_path), None, None, reopen=False)
```

Use these closed Windows launch bounds:

```python
MAX_ROOT_SKILL_UTF8_BYTES = 16 * 1024
MAX_WINDOWS_COMMAND_LINE_UTF16_UNITS = 30_000  # includes terminating NUL
```

`load_and_verify_runtime` resolves the root `SKILL.md`, reads its bytes once, and uses that same retained byte buffer for the individual length/hash check and complete package-manifest replay. Refuse when it exceeds `MAX_ROOT_SKILL_UTF8_BYTES`. It then decodes those bytes with strict UTF-8 and stores the resulting text in `PrimeRuntimeContract.rook_skill_system_prompt`. `build_prime_argv` passes that text as one `--append-system-prompt` argument; Prime's flag accepts literal prompt text, not a filename. Keep `--skill <verified-directory>` as the separate skill-advertisement argument. Invalid UTF-8, byte-length drift, hash drift, or root-skill overflow refuses before spawn.

After rendering the complete argument tuple, `validate_windows_launch_argv` uses `subprocess.list2cmdline(argv)` and computes `len(rendered.encode("utf-16-le")) // 2 + 1`. Refuse with stable `runtime_command_line_too_long` before `spawn_agent_process` when the result exceeds 30,000 UTF-16 code units. This deliberately stays below Windows `CreateProcessW`'s 32,767-character ceiling and binds executable path, session path, skill paths, literal system prompt, model, reasoning, and every quoted separator exactly as launched. Tests cover the actual normal rendered argv, a root skill one byte over 16 KiB, and a complete-argv overflow.

Also prove exact manifest reproduction; regular-file-only traversal; ordinal forward-slash paths; raw length/hash binding; manifest self-exclusion; path-under-root checks; required Prime/goal/rook skill/license files; exact ACP SDK version; closed reasoning enum; exact `--no-skills`, pinned goal skill, pinned Rook skill, and literal root-skill system-prompt body; no `--api-key`, `--provider`, shell, ambient skill, or reopen overrides; MCP server name exactly `rook`; only contract-owned MCP env keys; and association `working_directory` delivery through `session/new.cwd` rather than a nonexistent stdio-server field. The launched Prime executable and service-owned Rook MCP interpreter are absolute, manifest- or service-bound paths and never resolve through `PATH`; the bundled `uv` executable is the single intentional `PATH` resolution, from the manifest-verified directory prepended by RookChat. No fallback executable is accepted.

- [ ] **Step 2: Write RED direct-process tests against the fake ACP agent**

Cover initialization protocol and `session/close` capability refusal, `promptCapabilities.image`, one ACP session per process, permission choice ordering and unique/nonempty IDs, callback generation fencing, cancellation outside callbacks, stop-reason mapping, clean close, `session/close` failure, uncertain prompt retirement, positively failed spawn claim release, uncertain spawn claim preservation, bounded optional Prime `_meta` goal/compaction projection, and reset-to-unknown on every process/session replacement. Missing or unknown `_meta` must never block standard ACP operation.

Add three causal process-boundary tests. First, launch the fake agent through the actual `OwnedAcpProcess` path and have it retain its received argv; prove the exact decoded `SKILL.md` body arrives as one `--append-system-prompt` value on new and reopen, while the skill path appears only under `--skill`. Second, the fake agent sends updates in a retained wire order; an injected test projection/sink stalls the first callback only after it assigns its prompt-local ordinal and acquires the ordering gate, forcing later SDK callback tasks to overlap without adding a production test hook. Assert the final projection reproduces the fake agent's wire journal exactly. If the pinned public SDK path cannot establish this, stop implementation rather than accepting externally supplied ordinals or adding a private transport. Third, the fake agent writes at least 2 MiB to stderr before and during a prompt; initialize, prompt settlement, `session/close`, EOF, and clean child exit must all complete without a full pipe blocking Prime.

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

Use the public SDK process helper and transport context directly, with stderr explicitly piped:

```python
validate_windows_launch_argv(self._launch.argv)
self._spawn_context = spawn_agent_process(
    self._client,
    *self._launch.argv,
    env=self._launch.environment,
    transport_kwargs={"stderr": asyncio.subprocess.PIPE},
)
self.connection, self.process = await self._spawn_context.__aenter__()
if self.process.stderr is None:
    raise AcpLaunchError("stderr_unavailable")
self._stderr_task = asyncio.create_task(self._drain_stderr(self.process.stderr))
```

The official Python ACP SDK 0.12.1 defaults stderr to `PIPE` but does not drain it. `OwnedAcpProcess` therefore owns exactly one drain task from immediately after process creation until retirement. Use fixed `STDERR_READ_CHUNK_BYTES = 8 * 1024` and retain only a private rolling `STDERR_TAIL_BYTES = 64 * 1024`. Raw stderr is never logged, serialized, cached, projected, or exposed to the panel; diagnostics may report only total bytes read, whether truncation occurred, and one closed drain-failure code. Clear the tail during retirement.

If the drain cannot be started, fail launch and retire the exact child. If the drain raises later, mark the transport failed and signal the process owner to retire it; do not retry or continue using the connection. On normal or forced retirement, perform bounded `close_session` when allowed, SDK connection/transport close, stdin EOF through the SDK, one process wait, and termination of only `self.process` through the SDK/direct-handle fallback. After child-exit handling, boundedly await stderr EOF; cancel the drain only after that point. Set `child_exit_observed` only after `await self.process.wait()` returns. Do not enumerate descendants.

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
    view = await manager.create(CreateConversationRequest(
        binding=rook_binding,
        saved_document_directory=str(fake_agent.saved_document_directory),
        requested_initial_model=None,
        requested_initial_reasoning=None,
    ))
    assert manager.store.list() == ()
    first = await manager.start_prompt(view.conversation_id, PromptInput("hello", ()), NullSink())
    with pytest.raises(ConversationBusy):
        await manager.start_prompt(view.conversation_id, PromptInput("second", ()), NullSink())
    fake_agent.materialize_valid_session()
    assert (await first.result_task).outcome == "settled"
    assert manager.store.get(view.conversation_id).prime_session_id == fake_agent.prime_session_id

@pytest.mark.asyncio
async def test_failed_first_publication_is_never_adopted_or_replayed(manager, fake_agent, rook_binding):
    view = await manager.create(CreateConversationRequest(
        binding=rook_binding,
        saved_document_directory=None,
        requested_initial_model=None,
        requested_initial_reasoning=None,
    ))
    fake_agent.finish_without_session_file()
    supervisor = await manager.start_prompt(view.conversation_id, PromptInput("hello", ()), NullSink())
    result = await supervisor.result_task
    assert result.outcome == "error"
    assert manager.store.list() == ()
    assert fake_agent.prompt_count == 1
```

The create request never contains a runtime ID. `AcpConversationManager.create` calls `RuntimeCatalog.latest()` exactly once, retains that verified contract for the provisional generation, and records its ID only when publishing the complete durable association. Callers cannot select an installed runtime or substitute a path.

Working-directory selection is equally closed. A non-null `saved_document_directory` must be absolute, canonical, exist, and be a directory. For an unsaved Rhino document, after generating the service-owned conversation ID, create and use exactly `ROOK_DATA_DIR/rookchat/acp/v1/workspaces/<conversation-id>/`. Persist the resulting absolute path immutably. Reopen requires that exact persisted directory to remain canonical and present; it never falls back to the service cwd, repository root, user profile, or another open document. Missing or mismatched custody returns `working_directory_unavailable` before Prime starts.

Cover saved and unsaved working directories, deleted directories, nonabsolute input, reopen mismatch, create-only conversation/session paths, target required for creation, internal latest-runtime selection, no association before materialization, exact bounded header promotion, failure after file creation but before publication, no automatic adoption, and no second prompt before publication.

The first settled turn may be published to the presentation cache only after the complete association publication succeeds. A failed association publication leaves both the durable registry and presentation cache empty even if bounded live text was displayed.

- [ ] **Step 2: Write RED tests for reopen and target independence**

Prove this exact order with spies:

```text
read locator -> acquire claim -> re-read association -> validate header/runtime -> launch
```

Target unavailability must allow Prime reopen but make the MCP environment retain the original immutable binding so target-dependent Rook calls return `target_unavailable`. Reopen must create a fresh ephemeral ACP session ID, reset optional `_meta` presentation to unknown, and send no prompt.

Add a model-free goal-projection case in which the fake agent reports an active Prime goal, Stop cancels only the current prompt, and the projected goal remains active until fresh Prime metadata says otherwise. Native `/goal status`, `/goal pause`, `/goal resume`, and `/goal clear` text passes through the ordinary settled prompt route; the manager exposes no parallel goal endpoint or persisted goal record.

- [ ] **Step 3: Write RED contention, retirement-barrier, and owner-crash tests**

Start two independent `AcpConversationManager` instances over the same temporary data root. Exactly one may create the claim and call the fake launcher. After an owner service subprocess exits without its close path, wait for its fake child to observe EOF and exit, then prove the claim still refuses Reopen and Delete. Do not inspect any PID.

Add deterministic barrier tests for the resident admission boundary:

```text
Close detaches its resident, pauses at a barrier, then a concurrent prompt refuses before ACP dispatch.
A prompt admitted before Close is captured by the detached resident and cancelled exactly once.
Live Delete calls the same detach primitive before cancellation, process retirement, or artifact work.
Service shutdown stops HTTP admission, detaches every resident, then retires only those detached handles.
A late completion or cleanup from an older launch generation cannot clear or retire a newer resident object.
```

- [ ] **Step 4: Implement one resident handle map and one single-flight gate**

```python
class AcpConversationManager:
    def __init__(self, store: AssociationStore, runtime_catalog: RuntimeCatalog,
                 process_factory: AcpProcessFactory, cache: PresentationCache):
        self._resident: dict[str, ResidentConversation] = {}
        self._launch_generation = itertools.count(1)
        self._admission_lock = asyncio.Lock()

    async def start_prompt(self, conversation_id: str, prompt: PromptInput,
                           sink: PresentationSink) -> ActivePromptSupervisor:
        async with self._admission_lock:
            resident = self._resident.get(conversation_id)
            if resident is None:
                raise ConversationNotOpen(conversation_id)
            if resident.active_prompt is not None:
                raise ConversationBusy(conversation_id)
            supervisor = ActivePromptSupervisor(generation=resident.next_prompt_generation())
            resident.active_prompt = supervisor
            supervisor.result_task = asyncio.create_task(
                self._run_supervised_prompt(resident, supervisor, prompt, sink)
            )
            return supervisor

    async def _run_supervised_prompt(self, resident, supervisor, prompt, sink):
        try:
            return await self._run_prompt(resident, supervisor, prompt, sink)
        finally:
            async with self._admission_lock:
                if resident.active_prompt is supervisor:
                    resident.active_prompt = None

    async def detach_resident_for_retirement(
        self, conversation_id: str
    ) -> ResidentConversation:
        async with self._admission_lock:
            resident = self._resident.pop(conversation_id, None)
            if resident is None:
                raise ConversationNotOpen(conversation_id)
            return resident

    async def request_cancel(self, conversation_id: str, source: str) -> bool:
        async with self._admission_lock:
            resident = self._resident.get(conversation_id)
            supervisor = None if resident is None else resident.active_prompt
        return False if supervisor is None else supervisor.request_cancel(source)
```

All resident insertion, prompt admission, detachment, and identity-checked prompt cleanup passes through `_admission_lock`. Detachment itself is the absorbing boundary: after the resident is removed, a new prompt sees `ConversationNotOpen`, while Reopen still fails on the retained `open.claim` until child exit is observed. The detached object remains the retirement operation's local authority; no later cleanup performs another map removal or touches a resident with a different launch generation.

The service-owned supervisor, not the HTTP waiter, owns prompt correlation, cancellation, final projection, cache publication, and clearing the active reference on its own resident object. Cancelling any observer of `result_task` must not cancel the underlying task; only `request_cancel` sets its one absorbing event. No caller and no stale generation may clear a newer prompt. `close`, live `delete`, and `shutdown` all begin with `detach_resident_for_retirement`; shutdown first stops HTTP admission and then detaches each captured resident before retiring it. This is ephemeral handle ownership, not a durable lifecycle state. Do not persist states for `idle`, `materializing`, `suspended`, `interrupted`, cancellation races, or goals.

- [ ] **Step 5: Implement exact cancellation and close branches**

The prompt owner, not an update callback or HTTP waiter, observes the absorbing cancellation event, sends `session/cancel` once, and awaits the original ACP prompt task. If it settles, classify that actual stop reason. If it does not, send no further ACP request and retire the exact process. `AcpConversationManager.request_cancel(conversation_id, source)` briefly acquires `_admission_lock`, snapshots the current supervisor, and invokes its synchronous idempotent `request_cancel`; it does not await ACP settlement while holding the lock.

Only a `ParsedRookResult` produced by Task 3 from exact ACP-delivered Rook JSON content establishes an authentic Rook result or receipt. Enclosing IPython/tool-card completion never does. Such a parsed result remains authoritative for that Rook operation even when the enclosing prompt later returns `error` or becomes uncertain. If transport fails before an exact envelope is parsed, record the operation outcome as unknown, freshly inspect Rook state, and never replay it automatically.

Close follows, using only the detached handle after admission has stopped:

```python
detached = await self.detach_resident_for_retirement(conversation_id)
captured_prompt = detached.active_prompt
if captured_prompt is not None:
    captured_prompt.request_cancel("close")
    settled = await detached.await_captured_prompt(captured_prompt, prompt_settlement_deadline)
    if not settled:
        return await detached.retire_without_more_acp()
await detached.process.close_session(close_deadline)
await detached.process.retire(process_exit_deadline)
detached.claim.release_after_observed_exit()
```

A forced termination after observed process exit may release the claim but returns `unclean`; inability to observe exit leaves the claim. Live Delete detaches through the same primitive, retains that resident's claim through bounded association deletion and artifact cleanup, and reports cleanup failures without claiming atomic erasure. Delete of a nonresident conversation acquires the existing claim before revalidation as already specified. No retirement path retries detachment.

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

Add one causal disconnect test with a hanging fake ACP prompt. Cancel the HTTP waiter/stream writer and prove: the service-owned `ActivePromptSupervisor.result_task` is not cancelled; exactly one absorbing cancellation signal is set; the prompt owner sends at most one ACP `session/cancel`; the owner either observes the original prompt settlement or boundedly retires the exact child; no child remains; and the resident active-prompt reference is cleared only by the supervisor's own `finally`, never by the HTTP handler.

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

The prompt endpoint prepares `web.StreamResponse` inside subscription cleanup custody, starts one service-owned supervisor, and observes it through `asyncio.shield` so cancellation of the aiohttp request task cannot cancel the ACP prompt owner:

```python
supervisor = await manager.start_prompt(conversation_id, prompt, sink)
try:
    result = await asyncio.shield(supervisor.result_task)
except (asyncio.CancelledError, ConnectionResetError):
    supervisor.request_cancel(source="http_waiter")
    raise
```

The cancel endpoint awaits the manager's bounded in-memory lookup, which calls the same idempotent supervisor signal and returns whether an active prompt accepted it; it does not wait for ACP settlement. The stream writer emits bounded projected NDJSON rows and independently records the terminal Prime outcome and presentation-stream outcome. A disconnected response uses its already captured supervisor to signal the prompt owner exactly once; it never clears the resident prompt reference, awaits cleanup recursively from a callback, or owns process retirement.

Service shutdown first stops the aiohttp site from admitting requests and waits for its bounded handler shutdown, then calls `AcpConversationManager.shutdown()`. That manager operation detaches each remaining resident through the same admission primitive used by Close/Delete and retires only the returned handles. It never enumerates processes or reopens a detached conversation.

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

Cover all terminal mappings, bounded error parsing, tool cards as presentation only, partial text on cancellation, omitted-history markers, image metadata history, target unavailable status, and the create-request working-directory field. A saved bound Rhino document contributes only its canonical parent directory; an unsaved document contributes `null`. No arbitrary browser or user payload may set this field.

- [ ] **Step 2: Write RED panel lifecycle tests**

Prove model/reasoning controls are editable only before create, reopen renders the presentation cache without feeding it to Prime, Stop calls `/cancel`, closing a tab queues `/close` to an owner that survives tab disposal, and deleting requires explicit confirmation and calls only `/delete`.

- [ ] **Step 3: Replace persona selection with Prime conversation creation**

`RookChatPanel`'s add action opens a compact creation dialog with optional configured fully qualified model and exact reasoning enum. It always creates an ACP conversation with the shipped `full` profile; no profile selector is shown. The temporary `readonly` profile is admitted only by the external Slice D qualification entry point. Remove persona names/colors and backend concepts. Existing durable conversations appear in a reopen list returned by the service.

At creation, resolve the exact bound document with `RhinoDoc.FromRuntimeSerialNumber`. When `RhinoDoc.Path` is nonempty, canonicalize and send `Path.GetDirectoryName(doc.Path)` as `SavedDocumentDirectory`; when the document is unsaved, send `null` and let the Python service create the deterministic product workspace. Refuse if the captured runtime serial no longer resolves. The panel never sends its process cwd, repository path, selected-file dialog path, or a caller-authored workspace.

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

### Task 10: Reconcile And Package One Complete Prime Runtime

**Files:**
- Modify in the clean Prime compatibility worktree: `packages/coding-agent/src/core/kernel/bootstrap.ts`
- Modify in the clean Prime compatibility worktree: `packages/coding-agent/test/kernel-bootstrap.test.ts`
- Modify in the clean Prime compatibility worktree: `scripts/build-binaries.sh`
- Modify in the clean Prime compatibility worktree: `packages/coding-agent/test/builtin-skills.test.ts`
- Create: `scripts/provision-prime-build-toolchain.ps1`
- Create: `scripts/verify-prime-build-toolchain.py`
- Create: `scripts/package-prime-acp-runtime.ps1`
- Create: `scripts/verify-prime-acp-runtime.py`
- Create: `scripts/verify-installed-rookchat-acp.py`
- Create: `scripts/tests/prime-build-toolchain.tests.ps1`
- Create: `scripts/tests/prime-acp-runtime.tests.ps1`
- Modify: `mcp_server/src/rook/agent/chat/prime_runtime.py`
- Modify: `mcp_server/src/rook/agent/chat/acp_conversation.py`
- Modify: `mcp_server/tests/test_chat_prime_runtime.py`
- Modify: `mcp_server/tests/test_chat_acp_conversation.py`
- Modify: `scripts/deploy-local-testing.ps1`
- Modify: `scripts/tests/deploy-local-testing-guards.tests.ps1`
- Modify: `installer/RookSetup.iss`
- Modify: `scripts/tests/release-installer-guards.tests.ps1`
- Modify: `installer/post_install.py`
- Create: `mcp_server/tests/test_verify_installed_rookchat_acp.py`
- Generate together for release staging, never commit separately: `installer/runtime/prime/staging/**`, including the complete payload and `runtime-manifest.json`
- Generate outside source and product trees, never commit or ship: `C:/UDEV/RookBuildTools/prime-acp/msys2-20260611-v1/root/**` plus sibling `build-toolchain-contract.json`
- Add: Prime-required license/notice files to the generated installer payload

**Interfaces:**
- Produces: one final independently reviewed Prime compatibility commit directly over `c718bf3c30fd8da206ed551837cbb54f7ad15948`; one independently reviewed non-self-referential MSYS2 build-tool artifact for this machine whose sibling contract binds complete `root/**`; official-shape immutable runtime at `ROOK_INSTALL_ROOT/prime/runtimes/<runtime-id>/`; an atomically replaced qualified-runtime pointer `current.json`; one portable closed manifest packaged with every byte it binds; manifest-bound official `uv` at `tools/uv/uv.exe`; manifest-bound matching Prime Python runtime at `dist/prime-agent-runtime`; an exact service-owned `sys.executable -m rook` MCP launch boundary; persistent data under `ROOK_DATA_DIR/rookchat/acp/v1/`; and one bounded installed-product identity report.
- Consumes: reviewed Prime precursor `9c25468b62c79fc4b1419d7800740e8e41e30467`, upstream parent `c718bf3c30fd8da206ed551837cbb54f7ad15948`, Prime's supported `scripts/build-binaries.sh --platform windows-x64 --skip-deps` path, the complete extracted `packages/coding-agent/binaries/windows-x64/` artifact, Task 8 skill, and Task 4 runtime verifier.

The Prime builder performs `npm ci` before compilation even with `--skip-deps`.
Task 10 authorizes that exact lockfile restoration on the release machine. It
may download packages pinned by Prime's committed `package-lock.json`, but it
must not update the lockfile, change package metadata, add dependencies, or
contact any provider/model service. Record the lockfile hash before and after;
any change refuses promotion. Generated ignored `node_modules`, `dist`, and
`binaries` output is allowed, but the Prime worktree must have no tracked or
untracked source changes after the build.

`runtime-manifest.json` is the single canonical executable contract. Its
canonical bytes hash to `runtime-id`; the installed runtime directory is named
by that identity, and `current.json` contains only `{"runtimeId":"..."}`.
There is no second runtime schema. The manifest contains only relative paths
beneath its runtime root and no machine-specific Rook MCP command, arguments,
or environment. The generated manifest and complete staged payload are one
release artifact: they are produced, verified, installed, and retained
together, and neither is committed as a substitute for the release artifact.

Prime's Python kernel remains Prime-owned mutable state, not part of this
content-addressed runtime. The immutable artifact carries both bootstrap
prerequisites: official `uv` 0.12.3 for `x86_64-pc-windows-msvc` at fixed
relative path `tools/uv/uv.exe`, and the complete matching Prime-built source
package at `dist/prime-agent-runtime`. Prime resolves `uv` because
`build_prime_child_env()` prepends that exact manifest-verified directory to
`PATH`, and resolves the Python source through its existing package-root lookup.
RookChat creates no contract-specific kernel and installs no Python package. On
first session creation Prime may begin background prewarm; the first IPython
operation waits for Prime to download Python, install its local matching runtime
source, and resolve default packages. This requires internet access and may take
time, but requires no separate user installation.

- [ ] **Step 1: Reconcile one final Prime compatibility commit and stop for review**

Work only in the clean Prime compatibility worktree at precursor
`9c25468b62c79fc4b1419d7800740e8e41e30467`; first prove its parent is exactly
`c718bf3c30fd8da206ed551837cbb54f7ad15948` and its worktree is clean.

Execution record, 2026-09-03: a pre-amendment focused run omitted the coding-agent
Vitest configuration. Its POSIX-only kernel fixture was bypassed on Windows and
ambient `C:/Users/bring/AppData/Local/hermes/bin/uv.exe` was selected. During
that failed window, ambient uv refreshed existing managed-Python junctions for
3.11 and 3.12; no new Python installation or surviving process was observed.
This is incident evidence, not a baseline pass. Deleting or rewriting shared uv
state is not authorized.

Before adding Task 10 feature assertions or editing production, repair only the
existing `kernel-bootstrap.test.ts` process fixture. Intercept subprocess
creation at the test boundary while leaving production executable resolution
real. Create a marker named `uv.exe` on Windows and `uv` elsewhere in one
fixture-only executable directory. Maintain a closed registry of canonical fake
executable paths and deterministic handlers; reject every spawn whose canonical
path is absent. No admitted fake uses a shell, network installer, or real child
process. Set `PATH` to that fixture directory only (`PATHEXT=.EXE` on Windows),
and isolate `HOME`, `USERPROFILE`, and `XDG_DATA_HOME` beneath the test root. Set
`PRIME_AGENT_INSTALL_UV=0`; set `UV_CACHE_DIR` and
`UV_PYTHON_INSTALL_DIR` beneath the same test root. Restore the original process
environment after each test. Any unexpected executable, network attempt,
user-home access, unaccounted fake spawn, or additional baseline failure is a
terminal stop.

With no Task 10 feature assertions or production edits yet, run the corrected
pre-existing tests through the package configuration and require green:

```powershell
Set-Location D:/prime-agent/.worktrees/prime-acp-no-daemon
if (-not (Test-Path -LiteralPath './node_modules/.bin/vitest.cmd' -PathType Leaf)) {
    throw 'Prime test dependencies are absent; stop for separately authorized lockfile restoration.'
}
./node_modules/.bin/vitest.cmd --config ./packages/coding-agent/vitest.config.ts run packages/coding-agent/test/kernel-bootstrap.test.ts packages/coding-agent/test/builtin-skills.test.ts
```

Do not generate workspace `dist`, run `npm run build`, invoke model-catalog
generation, run `npm ci`, restore dependencies, or contact the network to obtain
this baseline. Only after the corrected existing suite passes with every fake
spawn accounted for, add these RED feature assertions before production edits:

```typescript
expect(getKernelPythonPath("C:/kernel", "win32")).toBe("C:\\kernel\\Scripts\\python.exe");
expect(getKernelPythonPath("/kernel", "linux")).toBe("/kernel/bin/python");
```

The kernel test must also prove that both the pre-bootstrap readiness path and
the `uv pip install --python` path consume the same helper. Extend the existing
standalone packaging test to require this exact builder-owned copy:

```bash
mkdir -p binaries/$platform/dist
cp -r dist/prime-agent-runtime binaries/$platform/dist/
```

The Prime static test requires one recursive builder-owned subtree copy and
refuses a selected-file list. Step 2's Rook packaging tests inspect the built
result and require `pyproject.toml`, `uv.lock`, `src/**`, and every other regular
file emitted by Prime's existing `copy-assets` build. Run the same focused gate
and require only the new Task 10 assertions to fail before changing production:

```powershell
Set-Location D:/prime-agent/.worktrees/prime-acp-no-daemon
if (-not (Test-Path -LiteralPath './node_modules/.bin/vitest.cmd' -PathType Leaf)) {
    throw 'Prime test dependencies are absent; stop for separately authorized lockfile restoration.'
}
./node_modules/.bin/vitest.cmd --config ./packages/coding-agent/vitest.config.ts run packages/coding-agent/test/kernel-bootstrap.test.ts packages/coding-agent/test/builtin-skills.test.ts
```

Implement one helper in `bootstrap.ts`:

```typescript
export function getKernelPythonPath(
	venv: string,
	platform: NodeJS.Platform = process.platform,
): string {
	const pathApi = platform === "win32" ? path.win32 : path.posix;
	return platform === "win32"
		? pathApi.join(venv, "Scripts", "python.exe")
		: pathApi.join(venv, "bin", "python");
}
```

Use it at both existing interpreter decision points. Make the minimal
`build-binaries.sh` copy above so Prime, not the Rook packager, produces its
complete supported artifact. Run the focused tests and `npm run check` without
launching Prime or a kernel. Stage only the four Prime files listed for this
task and amend the precursor rather than adding a second commit:

```powershell
Set-Location D:/prime-agent/.worktrees/prime-acp-no-daemon
if (-not (Test-Path -LiteralPath './node_modules/.bin/vitest.cmd' -PathType Leaf)) {
    throw 'Prime test dependencies are absent; stop for separately authorized lockfile restoration.'
}
./node_modules/.bin/vitest.cmd --config ./packages/coding-agent/vitest.config.ts run packages/coding-agent/test/kernel-bootstrap.test.ts packages/coding-agent/test/builtin-skills.test.ts
npm run check
git add packages/coding-agent/src/core/kernel/bootstrap.ts packages/coding-agent/test/kernel-bootstrap.test.ts scripts/build-binaries.sh packages/coding-agent/test/builtin-skills.test.ts
git commit --amend -m "feat(coding-agent): complete daemon-free ACP runtime"
git rev-parse HEAD^
git diff --name-only c718bf3c30fd8da206ed551837cbb54f7ad15948..HEAD
git diff --check c718bf3c30fd8da206ed551837cbb54f7ad15948..HEAD
git status --short
```

The parent must remain exactly `c718bf3c30fd8da206ed551837cbb54f7ad15948`,
the worktree must be clean, and the complete one-commit diff may contain only
the already reviewed daemon-free ACP surfaces plus these four bounded files.
Stop for independent review of that exact final commit. The reviewer-supplied
commit identity becomes `ExpectedPrimeCommit`; no release dependency restore,
standalone build, packaging, or Rook product edit is admitted before that
review.

- [ ] **Step 2: Write RED packaging guard tests**

Tests must assert:

```text
official Prime standalone Windows builder is invoked from the exact reviewed Prime commit
Prime package-lock hash is unchanged by the build
the complete windows-x64 artifact directory is staged; no selected-file copy exists
the Prime-produced artifact contains a byte-identical complete dist/prime-agent-runtime subtree
the manifest binds that subtree and refuses a missing, extra, or changed runtime-source file
the npm release-tarball packer is not used
the builder target is fixed as windows-x64 and maps exactly to manifest platform windows and architecture amd64
runtime-manifest.json records the fixed platform pair, upstream commit, patch commit,
ACP protocol, Python SDK, goal skill, rook skill, and claim-key version
official uv 0.12.3 is obtained only from its pinned upstream archive, never from PATH, Hermes, the Rook venv, or another installation
the uv archive checksum, version, source URL, extracted executable bytes, fixed relative path, and both license files are manifest-bound
the Prime child PATH begins with the manifest-verified tools/uv directory
child-environment keys are removed case-insensitively for PI_PACKAGE_DIR, PRIME_AGENT_KERNEL_PYTHON, PRIME_AGENT_KERNEL_VENV, PRIME_AGENT_INSTALL_UV, VIRTUAL_ENV, PYTHONHOME, and PYTHONPATH
every inherited UV_* key is removed case-insensitively before the six fixed product-owned UV values are inserted
the fixed UV cache and managed-Python paths derive only from the verified Rook data root
runtime-manifest.json contains no rookMcpCommand, rookMcpArgs, rookMcpEnvironment, or other machine-local path
canonical runtime-manifest.json bytes produce the runtime ID
the unchanged manifest and payload verify after relocation beneath two different install roots
runtime-manifest.json is accepted by the updated production load_and_verify_runtime()
the manifest-selected pi.exe becomes argv[0]
the service-owned rook MCP declaration uses the exact current sys.executable, fixed -m rook arguments, and no PATH lookup
no second runtime schema exists or is consulted
runtime paths are immutable siblings, never an in-place overwrite
an existing runtime ID is reused only after complete byte-for-byte verification
installed executable is resolved only from the recorded runtime
current.json selects that exact verified runtime ID
sessions, presentation, and claims are outside replaceable app payloads
upgrade and rollback preserve historical runtimes and ACP data
uninstall with data retention does not remove ACP data
Prime licenses/notices are installed
installed verifier compares reviewed build outputs and source payloads with every installed consumer
installed identity report binds implementation commit, native/managed/Python/skill/Prime hashes, and chat-service paths
tampering, extra authority files, missing assets, or manifest mismatch refuse before publication
the complete release builder toolchain is validated before npm ci, and a missing or mismatched tool is terminal without installation or fallback
the provisioner receives OutputRoot, its exact PowerShell interpreter, NodeRoot, GitRoot, BunExecutable, PrimeWorktree, cmd.exe, and every expected version as explicit arguments and never discovers them from PATH or ambient state
the provisioner creates one fresh MSYS2 20260611 staging sibling from the exact base, zip 3.0-5, and unzip 6.0-3 inputs without consulting or changing C:/msys64
the published parent contains exactly manifested root/** plus sibling build-toolchain-contract.json; the contract is absent from the root manifest and changing either side invalidates the appropriate identity
the complete provisioned MSYS2 root and sorted pacman inventory are manifest-bound before release use
the toolchain includes direct custody for dirname, git, cmd.exe, npm configuration, and the pinned MSYS2 root; every tool row is source-root-relative and resolves identically before and after publication
every CommandRow retains literal {staging} only in its frozen positions, expands exactly once immediately before process creation, and rejects alternate tokens, materialized contract paths, repeated expansion, or path escape
Node, npm, Git, Bun, cmd.exe, and PowerShell version evidence is produced by the exact resolved executable later admitted for use; a second file beneath the same source root cannot supply it
download uses one bounded HttpClient request per source; SFX extraction, login initialization, and local pacman installation use the exact documented executable, argv, working directory, environment, and deadline
every MSYS2, zip, unzip, uv, and uv-license download rejects oversized Content-Length before body transfer and independently enforces its fixed byte ceiling while streaming; a header at or below the limit cannot authorize an oversized body; exact-limit succeeds and one-byte-over refuses
pacman uses the provisioner-authored repository-free config and explicit LocalFileSigLevel policy; no package URL, repository refresh, or package-manager network access is possible
unexpected SFX layout, initialization writes outside staging, incomplete package identities, or any pre-publication failure leaves the final destination absent
a retained failed staging tree is never resumed or adopted, while a later invocation with the same pinned inputs may start from a different empty staging sibling and publish successfully
same-volume publication refuses an occupied destination without changing either the destination or failed staging evidence
the packager requires an independently approved ExpectedBuildToolchainContractSha256 before any probe, network access, or npm ci
all inherited NPM_CONFIG_* keys are removed case-insensitively before empty user/global files and exact cmd.exe script-shell values are inserted
the exact final npm userconfig, globalconfig, script-shell, ComSpec, PATH, command resolution, and whole-root MSYS2 manifest are verified before npm ci and unchanged after the build
BuildToolchainContract rejects missing, extra, and duplicate keys and noncanonical ordering/encoding/LF; PowerShell producer and Python verifier reconstruct identical canonical bytes and contract SHA-256 for the complete frozen Unicode corpus without normalization or optional escaping
each package invocation owns a unique empty same-volume scratch outside source, installed-product, runtime, and toolchain roots; all profile/temp paths remain beneath it and no generation is reused
scratch and the exact final build environment are validated for the current invocation but are not persisted as a second build-report authority
the Prime build has a mandatory 1800-second deadline and 30-second process-handle cleanup deadline; timeout forbids packaging or verification of partial output
the exact package-prime-acp-runtime.ps1 invocation receives the approved Prime commit, published contract, independently approved contract hash, and fresh staging output before any staged-runtime verification
```

Run the new static/fake tests before implementing either script and require RED
without downloading or executing MSYS2:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
$pwsh = 'C:/Program Files/PowerShell/7/pwsh.exe'
& $pwsh -NoProfile -File scripts/tests/prime-build-toolchain.tests.ps1
$buildToolchainRedExit = $LASTEXITCODE
& $pwsh -NoProfile -File scripts/tests/prime-acp-runtime.tests.ps1
$primeRuntimeRedExit = $LASTEXITCODE
if ($buildToolchainRedExit -eq 0 -or $primeRuntimeRedExit -eq 0) {
    throw 'Both new Task 10 test surfaces must demonstrate their named RED assertions.'
}
```

Both scripts must exist and load their intended test harnesses. Each nonzero
result must be caused solely by the named missing Task 10 behavior; a missing
script, syntax/import error, unrelated failure, or ambient executable contact is
a terminal stop rather than acceptable RED evidence.

- [ ] **Step 3: Provision one disposable MSYS2 build root and stop for review**

Implement `provision-prime-build-toolchain.ps1` and
`verify-prime-build-toolchain.py` from the RED tests. This development machine's
shared `C:/msys64` contains Bash and coreutils but no `zip.exe` or `unzip.exe`;
neither script may inspect, update, or copy from it. The provisioner has this
closed interface; no parameter has a default or ambient fallback:

```powershell
param(
  [Parameter(Mandatory=$true)][string]$OutputRoot,
  [Parameter(Mandatory=$true)][string]$PowerShellExecutable,
  [Parameter(Mandatory=$true)][string]$ExpectedPowerShellVersion,
  [Parameter(Mandatory=$true)][string]$NodeRoot,
  [Parameter(Mandatory=$true)][string]$ExpectedNodeVersion,
  [Parameter(Mandatory=$true)][string]$ExpectedNpmVersion,
  [Parameter(Mandatory=$true)][string]$GitRoot,
  [Parameter(Mandatory=$true)][string]$ExpectedGitVersion,
  [Parameter(Mandatory=$true)][string]$BunExecutable,
  [Parameter(Mandatory=$true)][string]$ExpectedBunVersion,
  [Parameter(Mandatory=$true)][string]$PrimeWorktree,
  [Parameter(Mandatory=$true)][string]$CmdExecutable,
  [Parameter(Mandatory=$true)][string]$ExpectedCmdFileVersion
)
```

Before creating staging, canonicalize and validate every explicit path. Require
`NodeRoot`, `GitRoot`, and `PrimeWorktree` to be existing absolute directories;
the other path inputs must be existing absolute regular files. Require
`node.exe`, `npm.cmd`, and `node_modules/npm/package.json` beneath `NodeRoot`,
`cmd/git.exe` beneath `GitRoot`, `.npmrc` beneath `PrimeWorktree`, and
`CmdExecutable` to canonically equal `C:/Windows/System32/cmd.exe`, and
`PowerShellExecutable` to equal the current process executable. Construct each
candidate tool path only from these explicit roots/files; version evidence is
accepted only after that candidate is recorded as the exact ToolRow resolved
by the shared resolver below. Npm's package JSON may corroborate the expected
package version but cannot substitute for executing resolved `tools.npm`.
Manifest the complete Node and Git roots plus the exact Bun, Prime `.npmrc`, and
`cmd.exe` files before staging. Reverify the same bytes after provisioning. The
script never calls `Get-Command`, searches `PATH`, reads npm user/global
configuration, or invents a machine path.

The provisioner publishes only this versioned build-only artifact, outside every
source and product directory:

```text
C:/UDEV/RookBuildTools/prime-acp/msys2-20260611-v1/
  root/
  build-toolchain-contract.json
```

Only `root/**` belongs to the recursive MSYS2 file manifest. The contract is its
sibling and contains the complete root file rows, root-manifest SHA-256, and
sorted `pacman -Q` inventory. It identifies the MSYS root only by relative path
`root`; it never manifests or hashes itself as a root member.

The fixed download inputs are:

```text
base: https://github.com/msys2/msys2-installer/releases/download/2026-06-11/msys2-base-x86_64-20260611.sfx.exe
baseSha256: C105946E64E08F099AC0E4647461CE762B95333AD211777666476A9A41451D65
baseMaxBytes: 268435456
zip: https://mirror.msys2.org/msys/x86_64/zip-3.0-5-x86_64.pkg.tar.zst
zipSha256: 874E20BF625FBE577949444FAF30AB9A725DBD4886EC9BFF26459152DA7F831C
zipMaxBytes: 4194304
unzip: https://mirror.msys2.org/msys/x86_64/unzip-6.0-3-x86_64.pkg.tar.zst
unzipSha256: C98EBAC31EA92A63CF61C6190ED3E8284CCC0C29C43973F1B2C0DE2874E5ACFE
unzipMaxBytes: 4194304
```

The final output parent must be absent. Create a unique empty same-volume sibling
named `msys2-20260611-v1.staging.<guid>` with temporary `downloads/`, `extract/`,
and `scratch/` children. Download each source exactly once per invocation using
`System.Net.Http.HttpClientHandler` with redirects enabled and a maximum of five
redirects, plus one `HttpClient` with `Timeout = [TimeSpan]::FromMinutes(5)`.
Call `GetAsync(uri, ResponseHeadersRead)` once, require a successful status, and
check `Content-Length` when present. Refuse before opening the destination body
file when that value is negative, invalid, or greater than the source's fixed
maximum. Copy the response in fixed 64 KiB chunks to a create-new file using
`FileMode.CreateNew`, `FileAccess.Write`, and `FileShare.None`; before every
write, checked-add the chunk length to a 64-bit counter and refuse if it would
exceed the same maximum. Exact-limit content succeeds. Missing or false
`Content-Length` cannot bypass the streaming counter. An oversized or failed
partial remains quarantined only under the failed staging generation and has no
authority. Dispose response, streams, client, and handler deterministically.
There is no range request, resume, alternate URL, or application retry. Hash
each completed download before it can be executed, extracted, or copied into
the MSYS root.

All provisioner child processes use `UseShellExecute = $false`,
`CreateNoWindow = $true`, `WindowStyle = Hidden`, a cleared environment,
concurrent bounded stdout/stderr drains, one retained process handle, and the
following exact calls. This table is also the literal unexpanded CommandRow
content serialized into the canonical contract:

| Phase | `executable` | `arguments` | `workingDirectory` | `timeoutSeconds` |
| --- | --- | --- | --- | --- |
| Base extraction | `{staging}/downloads/msys2-base-x86_64-20260611.sfx.exe` | `["-y", "-o{staging}/extract"]` | `{staging}/downloads` | `300` |
| First login | `{staging}/root/usr/bin/bash.exe` | `["-lc", " "]` | `{staging}/root` | `120` |
| Local package install | `{staging}/root/usr/bin/pacman.exe` | `["-U", "--noconfirm", "--needed", "--config", "/etc/rook-local-pacman.conf", "/var/cache/rook-provision/zip-3.0-5-x86_64.pkg.tar.zst", "/var/cache/rook-provision/unzip-6.0-3-x86_64.pkg.tar.zst"]` | `{staging}/root` | `180` |

For extraction, the cleared environment contains only the validated
`SystemRoot`, `WINDIR`, and staging-owned `TEMP`/`TMP`. The SFX must exit zero and
produce exactly one top-level `extract/msys64/` directory beneath the current
staging generation; no sibling entry is accepted. Move that directory to the
current generation's `root/` before any initialization. For login and pacman,
add only `CHERE_INVOKING=1`, `MSYSTEM=MSYS`,
`HOME={staging}/root/home/rookbuild`, `USERPROFILE` at the same staging-owned
home, and `PATH={staging}/root/usr/bin;C:/Windows/System32` to the stored
environment template before its one execution-time expansion.

Copy the two hash-verified package archives to
`root/var/cache/rook-provision/` beneath the current staging generation under
their exact filenames. Before pacman runs, write
`/etc/rook-local-pacman.conf` with these exact UTF-8/LF bytes:

```ini
[options]
Architecture = auto
SigLevel = Required DatabaseOptional
LocalFileSigLevel = Never
RemoteFileSigLevel = Required
```

The file has no repository section. The exact approved archive SHA-256 values,
not an inherited keyring policy, authorize these two local unsigned package
files. Pacman's arguments contain only local MSYS paths and no URL. Missing base
dependencies fail the operation; no sync database refresh, package download, or
network fallback is admitted. A nonzero exit or deadline kills only the retained
child and its directly owned descendants, awaits settlement, and fails the
staging attempt without publishing.

The login shell and pacman may write only beneath the unique staging tree.
External Node, Git, Bun, Prime, and Windows inputs are read-only and must retain
their preflight manifests. After pacman exits, require exact package identities
for `zip 3.0-5`, `unzip 6.0-3`, `bash`, and `libbz2`; remove the two temporary
package copies and all `downloads/`, `extract/`, and `scratch/` content. Create
distinct zero-byte `root/etc/rook-user.npmrc` and
`root/etc/rook-global.npmrc`. Only after every initialization write and cleanup
is complete, record every regular file beneath `root/**` with forward-slash
relative path, raw byte length, and uppercase SHA-256; reject
symlinks/reparse-point escapes. The canonical `BuildToolchainContract` has
exactly six top-level keys and no optional fields:

```text
schemaVersion: integer exactly 1
kind: string exactly "rook-prime-build-toolchain"
msys2:
  release: string exactly "20260611"
  root: string exactly "root"
  files: FileRow[1..n]
  manifestSha256: uppercase 64-hex string
  packages: PackageRow[1..n]
  sources: {base: SourceRow, zip: SourceRow, unzip: SourceRow}
  provisioning:
    download: {attemptsPerSource: 1, maxRedirects: 5, timeoutSeconds: 300}
    extract: CommandRow
    initialize: CommandRow
    install: CommandRow
    extractEnvironment: exactly SystemRoot, TEMP, TMP, WINDIR
    msysEnvironment: exactly CHERE_INVOKING, HOME, MSYSTEM, PATH,
      SystemRoot, TEMP, TMP, USERPROFILE, WINDIR
    pacmanConfig: FileRow
externalInputs:
  powershell: VersionedFileRow
  node: {root, files, manifestSha256, expectedNodeVersion,
    observedNodeVersion, expectedNpmVersion, observedNpmVersion}
  git: {root, files, manifestSha256, expectedVersion, observedVersion}
  bun: VersionedFileRow
  prime: {worktree, npmrc: FileRow}
  cmd: VersionedFileRow
tools: ToolRow[15]
npm: {userConfig: FileRow, globalConfig: FileRow, scriptShell, comSpec}
```

`FileRow` has exactly `path: string`, `length: nonnegative integer`, and
`sha256: uppercase 64-hex string`. `VersionedFileRow` adds exactly nonempty
`expectedVersion` and `observedVersion`. `PackageRow` has exactly nonempty
`name` and `version`. `SourceRow` has exactly `url`, `sha256`, and positive
integer `maxBytes`; its three values are the frozen source rows and ceilings
above. `ToolRow` has exactly `name`, `source`, `path`, `length`, and `sha256`.
`source` is one of `msys2`, `node`, `git`, `bun`, or `cmd`; `path` is a nonempty
forward-slash relative path with no empty, `.`, or `..` segment; `length` is a
nonnegative integer; and `sha256` is uppercase 64-hex. `CommandRow` has exactly
`executable`, `arguments`, `workingDirectory`, and positive integer
`timeoutSeconds`; its values are the frozen extraction/login/install rows above.

Every path-bearing CommandRow string stores literal `{staging}` in exactly the
table positions: extraction `executable`, zero-based `arguments[1]`, and
`workingDirectory`; initialization `executable` and `workingDirectory`; and
installation `executable` and `workingDirectory`. No other CommandRow field may
contain it. Reject `<staging>`, unknown brace tokens, a wrong occurrence count
or position, or an absolute materialized staging path stored in the contract.
Immediately before each process creation, one shared function performs exactly
one nonrecursive expansion pass over that row, replacing every permitted token
with the canonical current staging path. Reject an already expanded row,
residual token, repeated expansion, or any expanded executable, working
directory, or host path-bearing argument outside the current staging
generation. Pass the exact expanded executable, argument array, and working
directory to `ProcessStartInfo`; canonical serialization and hashing always use
the unexpanded row.

The `node` and `git` `root` values are absolute nonempty strings, each `files`
array contains one or more root-relative `FileRow` values, each manifest hash is
uppercase 64-hex, and every version field is nonempty. `prime.worktree` and its
`.npmrc` path are absolute. Npm user/global config paths are relative beneath
`root/etc`, have length zero, and match root file rows. `scriptShell` and
`comSpec` both equal the verified absolute cmd path. The `pacmanConfig` path is
exactly `root/etc/rook-local-pacman.conf` and its length/hash match the exact
UTF-8/LF bytes above.

The contract stores these exact environment templates:

```text
extractEnvironment = {"SystemRoot":"C:/Windows","TEMP":"{staging}/scratch/temp","TMP":"{staging}/scratch/temp","WINDIR":"C:/Windows"}
msysEnvironment = {"CHERE_INVOKING":"1","HOME":"{staging}/root/home/rookbuild","MSYSTEM":"MSYS","PATH":"{staging}/root/usr/bin;C:/Windows/System32","SystemRoot":"C:/Windows","TEMP":"{staging}/scratch/temp","TMP":"{staging}/scratch/temp","USERPROFILE":"{staging}/root/home/rookbuild","WINDIR":"C:/Windows"}
```

File rows are unique and sorted by path using ordinal code-point order. Package
rows are unique by name and sorted by name then version. Tool rows are unique,
sorted by name, and have exactly these name/source pairs:

```text
msys2: bash, cp, dirname, ls, mkdir, mv, rm, tar, unzip, zip
node: node, npm
git: git
bun: bun
cmd: cmd
```

Command argument arrays retain their declared order. Strings must be valid
Unicode scalar sequences without unpaired surrogates. Reject every missing,
extra, or duplicate key at every depth.

The one ToolRow resolver selects the canonical contract parent for `msys2`,
`externalInputs.node.root` for `node`, `externalInputs.git.root` for `git`, the
canonical parent of `externalInputs.bun.path` for `bun`, or the canonical parent
of `externalInputs.cmd.path` for `cmd`. An MSYS2 path begins with `root/`.
Combine the selected root and relative path, canonicalize the result, require it
to remain beneath that root, and then verify regular-file type, length, and
hash. Use this same resolver while the contract is in its GUID staging parent
and after create-only publication. No tool may resolve through another source
or installation.

Bind every version observation to the exact path that this resolver admits and
the build later consumes. Resolved `tools.node`, `tools.npm`, and `tools.git`
produce `observedNodeVersion`, `observedNpmVersion`, and Git's
`observedVersion`. Resolved `tools.bun` must canonically equal
`externalInputs.bun.path` and produces Bun's `observedVersion`. Resolved
`tools.cmd` must canonically equal `externalInputs.cmd.path` and supplies the
recorded file version. The explicitly supplied PowerShell path must canonically
equal `externalInputs.powershell.path` and produces PowerShell's
`observedVersion`. Probe by canonical resolved path, never by tool name or a
separately located candidate. If a resolved tool is a script requiring the
manifest-bound Bash interpreter, pass its exact path as the interpreter operand
and do not rediscover it through `PATH`. A mismatched version source refuses
even when both files are under the same Node, Git, Bun, cmd, or PowerShell
source root.

Serialize strict UTF-8 without BOM and perform no Unicode normalization.
Preserve each code-point sequence exactly, including distinct composed and
decomposed forms. Sort object keys lexicographically by Unicode scalar value,
not by UTF-16 code unit. Arrays retain their required semantic order. Escape
quotation mark as `\"`, reverse solidus as `\\`, and never escape `/`. Use
`\b`, `\t`, `\n`, `\f`, and `\r` only for U+0008, U+0009, U+000A, U+000C, and
U+000D; encode every other U+0000 through U+001F scalar with lowercase
`\u00xx`. Emit every other scalar, including supplementary-plane characters,
literally as UTF-8 with no optional escaping. Use compact separators and exactly
one terminal LF. Each `manifestSha256` hashes the canonical UTF-8 representation
of its `files` array plus one LF. Hash the entire exact contract file for
`ExpectedBuildToolchainContractSha256`. The Python verifier parses with a
duplicate-key-detecting `object_pairs_hook`, validates the complete closed
schema, reconstructs canonical bytes, requires byte equality with the stored
file, and only then compares the independently approved hash. Producer/verifier
parity tests cover duplicate and unknown keys, missing fields, reordered arrays,
BOM/non-UTF-8, pretty-printing, missing/extra terminal LF, non-ASCII and
supplementary-plane scalars, quotes, backslashes, unescaped slashes, every
specified control-character class, and composed/decomposed sequences proving no
normalization. One valid contract must produce byte-identical PowerShell and
Python canonical bytes and SHA-256.
Run only model-free provisioner/verifier tests and bounded version probes. Fake
process/download tests must prove exact argv, working directories, environments,
deadlines, expected extracted layout, hash-before-use ordering, local signature
policy, and manifest-after-initialization ordering. CommandRow parity tests
require identical unexpanded producer/verifier bytes and exact execution-time
materialization of executable, argument array, and working directory. They
reject `<staging>`, unknown tokens, wrong token count or position, a stored
absolute staging path, repeated expansion, residual tokens, and path escape.
Version-binding tests place a second executable under each source root and prove
that no Node, npm, Git, Bun, cmd, or PowerShell observation can come from a path
other than the exact resolved file later admitted for use. For each of the
MSYS2 base, zip, and unzip sources, fake HTTP tests cover refusal before body
read for oversized `Content-Length`, absent `Content-Length` with an oversized
stream, a header at or below the limit followed by an oversized body,
exact-limit success, and one-byte-over stream refusal; no partial file can enter
a manifest. Causal publication tests must prove: the contract is absent from the
root manifest; changing contract bytes changes the contract hash without
recursively changing the root manifest;
changing a root byte breaks contract verification; an occupied output remains
unchanged; concurrent publishers admit at most one completed parent; and a
failed staging generation is never resumed or adopted while a later new staging
generation with the same pinned inputs may succeed.

After verification, require the staging parent to contain exactly `root/` and
`build-toolchain-contract.json`. Publish with one same-volume create-only
`Directory.Move(<completed-staging-parent>, <OutputRoot>)`; an existing
destination refuses without alteration. Print the canonical contract SHA-256
and stop. The
provisioner does not invoke Prime's builder or `npm ci`.

After the fake tests pass, perform the one real provisioning operation from an
absent root:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
$root = 'C:/UDEV/RookBuildTools/prime-acp/msys2-20260611-v1'
if (Test-Path -LiteralPath $root) {
    throw 'The versioned build-tool root already exists; do not repair or overwrite it.'
}
$pwsh = 'C:/Program Files/PowerShell/7/pwsh.exe'
& $pwsh -NoProfile -File scripts/provision-prime-build-toolchain.ps1 `
    -OutputRoot $root `
    -PowerShellExecutable $pwsh `
    -ExpectedPowerShellVersion '7.6.5' `
    -NodeRoot 'C:/Program Files/nodejs' `
    -ExpectedNodeVersion '24.11.1' `
    -ExpectedNpmVersion '11.6.2' `
    -GitRoot 'C:/Program Files/Git' `
    -ExpectedGitVersion '2.53.0.windows.2' `
    -BunExecutable 'C:/Users/bring/.bun/bin/bun.exe' `
    -ExpectedBunVersion '1.3.14' `
    -PrimeWorktree 'D:/prime-agent/.worktrees/prime-acp-no-daemon' `
    -CmdExecutable 'C:/Windows/System32/cmd.exe' `
    -ExpectedCmdFileVersion '10.0.26100.1'
if ($LASTEXITCODE -ne 0) {
    throw "Build-tool provisioning failed with exit code $LASTEXITCODE. The failed staging tree has no authority."
}
$python = 'C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server/.venv/Scripts/python.exe'
& $python scripts/verify-prime-build-toolchain.py --contract "$root/build-toolchain-contract.json"
if ($LASTEXITCODE -ne 0) {
    throw "Build-tool verification failed with exit code $LASTEXITCODE. Do not build."
}
Get-FileHash -LiteralPath "$root/build-toolchain-contract.json" -Algorithm SHA256
git add scripts/provision-prime-build-toolchain.ps1 scripts/verify-prime-build-toolchain.py scripts/tests/prime-build-toolchain.tests.ps1
git commit -m "build(chat): provision pinned Prime build tools"
```

Stop for independent review of the complete package inventory, root manifest,
tool/configuration rows, exact source commit, and contract hash. The
reviewer-supplied hash becomes `ExpectedBuildToolchainContractSha256`. A failed
or partial staging generation has no authority and is never repaired, resumed,
promoted, or adopted. It may be retained as diagnostic evidence. A later
invocation may create a different empty staging sibling with the same fixed
inputs; every download, input, command, and output is then reverified from the
beginning. The final output parent remains create-only and immutable after
publication. No release build is authorized before its exact contract hash is
approved.

- [ ] **Step 4: Implement Prime's supported standalone packager**

`package-prime-acp-runtime.ps1` receives these mandatory parameters:

```powershell
param(
  [Parameter(Mandatory=$true)][string]$PrimeWorktree,
  [Parameter(Mandatory=$true)][string]$ExpectedPrimeCommit,
  [Parameter(Mandatory=$true)][string]$OutputRoot,
  [Parameter(Mandatory=$true)][string]$BuildToolchainContract,
  [Parameter(Mandatory=$true)][string]$ExpectedBuildToolchainContractSha256
)
```

Before any version probe, network access, or `npm ci`, hash the unchanged
canonical contract bytes and require the independently supplied expected hash.
Require `BuildToolchainContract` to be the published sibling
`C:/UDEV/RookBuildTools/prime-acp/msys2-20260611-v1/build-toolchain-contract.json`
and resolve its relative `root` only beneath that parent.
Then run `verify-prime-build-toolchain.py` to replay the complete MSYS2 root
manifest and `pacman -Q` inventory, the complete Node/npm and Git root manifests,
every external tool/configuration file hash, and every bounded version
expectation. Verify that Bash reports the expected MSYS environment rather than
WSL and that the two npmrc files remain zero-byte.
Missing, malformed, substituted, or changed inputs are terminal; the package
script never discovers, installs, updates, retries, or falls back to another
build tool.

Canonicalize `OutputRoot`, derive its volume root, and fix the scratch parent to
`<volume-root>/UDEV/RookBuildScratch/prime-acp`; the Task 10 command therefore
uses `C:/UDEV/RookBuildScratch/prime-acp`. Generate one new
`package.<32-lowercase-hex-guid>` leaf and create it create-only. Refuse if that
leaf already exists or is not empty. Require the canonical leaf to be on the
same volume as `OutputRoot` and outside the Prime/Rook source worktrees, every
installed-product or immutable runtime root, and the published immutable
build-toolchain parent. Never search for, select, resume, or clean an earlier
scratch generation. A failed generation has no authority; a later invocation
uses a different newly generated empty leaf. Keep the actual canonical leaf only
as an invocation-local diagnostic; do not persist it in
`BuildToolchainContract`, the packaged runtime, or a separate build report. This
plan defines no build-report artifact or downstream build-report consumer.
Path-injection tests use a deterministic GUID source and prove that a
pre-existing generated leaf refuses without alteration, a leaf inside any
forbidden root refuses, all six profile/temp variables canonicalize beneath the
accepted leaf, and a second invocation after failure receives a different empty
leaf rather than reopening the first.

Construct a fresh build environment rather than modifying the caller's map.
Remove every inherited `NPM_CONFIG_*` key case-insensitively. The closed result
contains only `SystemRoot`, `TEMP`, `TMP`, `HOME`, `USERPROFILE`, `APPDATA`,
`LOCALAPPDATA`, `PATH`, `PATHEXT`, `CHERE_INVOKING`, `MSYSTEM`, and these
npm/shell values. Tool, shell, and system values come from the verified
contract; the six profile/temp values come only from the current scratch leaf:

```text
NPM_CONFIG_USERCONFIG=<manifest-bound empty rook-user.npmrc>
NPM_CONFIG_GLOBALCONFIG=<manifest-bound empty rook-global.npmrc>
NPM_CONFIG_SCRIPT_SHELL=C:/Windows/System32/cmd.exe
ComSpec=C:/Windows/System32/cmd.exe
```

The exact scratch-derived values are `HOME=<scratch>/home`,
`USERPROFILE=<scratch>/profile`,
`APPDATA=<scratch>/profile/AppData/Roaming`,
`LOCALAPPDATA=<scratch>/profile/AppData/Local`, and
`TEMP=TMP=<scratch>/temp`. Create those directories create-only as part of the
new leaf and re-canonicalize every value to prove containment before launch.
`CHERE_INVOKING=yes` and `MSYSTEM=MSYS` are fixed. No proxy, `NODE_OPTIONS`, npm
configuration, or other caller variable is inherited. If this machine later
requires a build proxy, that value needs a newly versioned and independently
reviewed toolchain contract; it is not discovered at execution time.

Set `PATH` only from the declared tool directories. From inside the exact
`bash --noprofile --norc` process, require every command to resolve to its
contract row. Through the declared npm executable and that same environment,
require `npm config get userconfig`, `globalconfig`, and `script-shell` to equal
the three fixed paths. Prime's source-controlled project `.npmrc` and npm's
bound built-in configuration are the only other configuration sources.
`dirname` is verified before invoking Prime's script because line 23 consumes it
before `npm ci`; `git` is verified because `bundle.mjs` consumes it for build
provenance. Revalidate the exact final build environment's closed nonsecret
key/value map in memory immediately before process creation. It is
invocation-local and is not persisted as package authority or consumed by a
later gate.

The script has no caller-selectable platform or architecture. It fixes the
Prime builder target to `windows-x64` and the portable runtime-manifest values
to `platform: "windows"` and `architecture: "amd64"`. It verifies that clean
`HEAD` equals the exact final Prime commit independently approved in Step 1,
that its parent is `c718bf3c30fd8da206ed551837cbb54f7ad15948`, and that the
approved one-commit diff contains the required artifact and Windows-kernel
corrections. It hashes Prime's committed `package-lock.json` and invokes the
exact existing builder through the declared Bash path and final closed build
environment:

```powershell
$start = [System.Diagnostics.ProcessStartInfo]::new()
$start.FileName = $bashPath
$start.WorkingDirectory = $PrimeWorktree
$start.UseShellExecute = $false
$start.CreateNoWindow = $true
$start.Environment.Clear()
foreach ($entry in $buildEnvironment.GetEnumerator()) {
    $start.Environment.Add($entry.Key, $entry.Value)
}
foreach ($argument in @('--noprofile', '--norc', 'scripts/build-binaries.sh', '--platform', 'windows-x64', '--skip-deps')) {
    [void]$start.ArgumentList.Add($argument)
}
$process = [System.Diagnostics.Process]::new()
$process.StartInfo = $start
if (-not $process.Start()) { throw 'Prime standalone builder did not start.' }
$buildTimedOut = -not $process.WaitForExit(1_800_000)
if ($buildTimedOut) {
    $killFailure = $null
    try {
        $process.Kill($true)
    }
    catch {
        $killFailure = $_.Exception.Message
    }
    $cleanupSettled = $process.WaitForExit(30_000)
    if (-not $cleanupSettled) {
        throw 'Prime standalone builder timed out and direct-handle cleanup did not settle within 30 seconds.'
    }
    if ($null -ne $killFailure) {
        throw "Prime standalone builder timed out; direct-handle cleanup reported: $killFailure"
    }
    throw 'Prime standalone builder exceeded the mandatory 1800-second deadline.'
}
if ($process.ExitCode -ne 0) {
    throw "Prime standalone builder failed with exit code $($process.ExitCode)"
}
```

The 1800-second build deadline and 30-second cleanup deadline are mandatory and
not caller-selectable. Timeout is a failed build and cannot enter artifact
assembly, manifest generation, staged-runtime verification, or installation.
Cleanup uses only that directly retained process handle and
`Kill(entireProcessTree: true)`. It never uses a shell wrapper, process
discovery, kill by name, PID scanning, identity probes, timeout adjustment,
automatic retry, or a second launch. A fake-process causal test holds the build
open through the deadline, requires exactly one handle-owned process-tree kill
and one bounded cleanup wait, and proves packaging and verification callbacks
were never reached.

The builder's own `npm ci` is the only dependency restoration. After the build,
the package script requires the same lockfile hash, no source change, identical
empty npmrc files, and a complete replay of the unchanged MSYS2, Node/npm, and
Git root manifests plus package inventory. A cache or network failure is terminal; the package
script does not retry, change dependency inputs, or substitute another Prime
checkout.

The package script separately fetches the product dependency `uv` into its own
temporary directory from the exact official archive:

```text
version: 0.12.3
source: https://github.com/astral-sh/uv/releases/download/0.12.3/uv-x86_64-pc-windows-msvc.zip
archive SHA-256: B23350C79E8AD0192B8124AF13A0F17E8D4E4549524785E1AEF389AE5A06990E
archive maximum: 134217728 bytes
LICENSE-APACHE source: https://raw.githubusercontent.com/astral-sh/uv/0.12.3/LICENSE-APACHE
LICENSE-APACHE SHA-256: C71D239DF91726FC519C6EB72D318EC65820627232B2F796219E87DCF35D0AB4
LICENSE-APACHE maximum: 1048576 bytes
LICENSE-MIT source: https://raw.githubusercontent.com/astral-sh/uv/0.12.3/LICENSE-MIT
LICENSE-MIT SHA-256: 860E3D7A86B84E6A7012C7A635FC64DF475CEBC6CCE34DFEB73A5982EC58176C
LICENSE-MIT maximum: 1048576 bytes
```

Each download uses the same five-minute `HttpClient` deadline, redirect limit,
create-new destination, supplied-`Content-Length` precheck, and independent
64 KiB streaming counter as the MSYS2 sources. Apply the corresponding fixed
ceiling before each write; exact-limit content succeeds and one byte over
refuses. An incomplete file remains only beneath the failed invocation-owned
scratch and has no authority. Each download is single-attempt and hash-checked
before use; a cache or network failure is terminal. For each of the uv archive,
LICENSE-APACHE, and LICENSE-MIT sources, fake HTTP tests exercise oversized
`Content-Length`, absent `Content-Length` with oversized streaming, a header at
or below the limit followed by an oversized body, exact-limit success, and
one-byte-over refusal. Extract `uv.exe` with .NET archive APIs into
`tools/uv/uv.exe`, require its bounded version output to identify exactly
`uv 0.12.3`, and place both verified license files under
`licenses/uv/`. Never inspect or copy an ambient `uv`, including the Hermes
installation visible on this development machine.

Treat `packages/coding-agent/binaries/windows-x64/` as one indivisible
Prime-produced artifact. Copy that complete directory wholesale into a fresh
disposable staging root. Do not select files, reconstruct its layout, rename
`pi.exe`, create a wrapper, or invoke the npm release-tarball packer. Before the
copy, require the builder-produced
`packages/coding-agent/binaries/windows-x64/dist/prime-agent-runtime` subtree
to be byte-identical to
`packages/coding-agent/dist/prime-agent-runtime`, including every regular file
and no symlink/reparse-point escape. The package script does not append that
subtree itself. Add the exact manifest-bound Rook skill and pinned Prime root
`LICENSE`; include any notice files already carried by the standalone artifact.
The reviewed Prime baseline has no separate root `NOTICE` file. Call
`verify-prime-acp-runtime.py` against the complete staged root without launching
`pi.exe`.

The package script writes `runtime-manifest.json` into that same fresh staging
root only after the payload is complete, then verifies the pair. The entire
`installer/runtime/prime/staging/` tree remains ignored build output. Task 10
commits the reproducible build, verification, deployment, and installer logic;
it does not commit either the generated manifest or an incomplete payload. This
step implements the package operation; Step 7 invokes it only after Steps 5 and
6 have implemented its verifier and installed-product consumers.

- [ ] **Step 5: Implement the closed manifest algorithm**

For every admitted regular file except `runtime-manifest.json`, record forward-slash relative path, raw byte length, and uppercase SHA-256; sort paths ordinally. Refuse symlinks/reparse points and path escapes. Hash canonical UTF-8 JSON with sorted keys, compact separators, and LF to obtain `runtime_id`. Verify the unchanged packaged `pi.exe`, complete Prime artifact, complete matching `dist/prime-agent-runtime` subtree, exact Prime goal skill subtree, exact Rook skill subtree, manifest-bound `tools/uv/uv.exe`, both uv licenses, and required Prime licenses/notices are included. Every manifest path is relative to its runtime root. The schema removes `rookMcpCommand`, `rookMcpArgs`, and `rookMcpEnvironment`; absolute build-machine or install-machine paths are invalid.

Add one closed `uv` object to `runtime-manifest.json` with exact keys
`version`, `executable`, `source`, `sourceArchiveSha256`, and `licenses`.
Require the exact values above, require `executable` to equal
`tools/uv/uv.exe`, and require `licenses` to name the two verified relative
license paths. The ordinary `files` rows bind the installed executable and
license bytes; the `uv` object binds version and provenance without creating a
second manifest.

Add one closed `pythonRuntime` object with exact keys `root`,
`manifestSha256`, and `sourceCommit`. Require `root` to equal
`dist/prime-agent-runtime`, `sourceCommit` to equal the final reviewed Prime
compatibility commit, and `manifestSha256` to be the canonical recursive
manifest of every regular file under that root using the same path/length/hash
algorithm as the outer manifest. The outer `files` rows remain the executable
authority; this subtree hash is a diagnostic identity and cannot replace or
exclude any outer row. Missing, extra, changed, escaped, or non-regular Python
runtime content returns `runtime_unavailable`.

The manifest's `executable` field points to the packaged `pi.exe`. The verifier
must place the staged bytes and the unchanged manifest into a disposable
`runtimes/<runtime-id>/` layout, pass them through the existing production
`load_and_verify_runtime()`, and prove `build_prime_argv()` selects that exact
file as `argv[0]`.

Update `PrimeRuntimeContract` and `load_and_verify_runtime()` to remove the
three Rook MCP launch fields and retain the exact verified uv version/path plus
the verified Prime Python-runtime path/subtree hash. Update
`DirectAcpProcessFactory` to receive the already validated `ROOK_DATA_DIR`, and
pass it as the mutable runtime root to `build_prime_child_env()`. That function
first validates every inherited key/value, then removes these keys by
case-insensitive exact-name comparison:

```text
PI_PACKAGE_DIR
PRIME_AGENT_KERNEL_PYTHON
PRIME_AGENT_KERNEL_VENV
PRIME_AGENT_INSTALL_UV
VIRTUAL_ENV
PYTHONHOME
PYTHONPATH
```

Also remove every inherited key whose case-insensitive name starts with `UV_`,
including unknown future names. Then insert exactly these six product-owned
values:

```text
UV_CACHE_DIR=<ROOK_DATA_DIR>/rookchat/acp/v1/prime-uv/cache
UV_PYTHON_INSTALL_DIR=<ROOK_DATA_DIR>/rookchat/acp/v1/prime-uv/python
UV_PYTHON_PREFERENCE=only-managed
UV_PYTHON_NO_REGISTRY=1
UV_PYTHON_INSTALL_REGISTRY=0
UV_NO_CONFIG=1
```

Prepend the parent of the manifest-bound uv executable to the remaining `PATH`.
Tests seed every forbidden exact name plus representative and unknown-future
`UV_*` names in canonical, lowercase, and mixed-case forms; none may survive,
only the six derived values may exist, and an unrelated environment entry must
survive. Verify the complete final child environment immediately before spawn,
not only the input transformation. A missing, changed, non-regular, or escaped
uv or Python-runtime path returns `runtime_unavailable` before Prime starts.
Update
`build_rook_mcp_server()` and its caller so
the declaration uses the running service's resolved exact `sys.executable`,
fixed arguments `-m rook`, and the product-owned closed environment plus the
association's immutable target/profile fields. The command is validated as the
current absolute executable and is never resolved through `PATH`. A relocation
test copies the identical manifest-bound tree beneath two distinct product
roots and proves that both produce the same runtime ID and valid contract while
their service-owned MCP command remains local to the interpreting service.

The authority chain is fixed:

```text
canonical runtime-manifest.json bytes
-> uppercase SHA-256 runtime ID
-> prime/runtimes/<runtime-id>/
-> current.json containing only {"runtimeId":"..."}
-> InstalledRuntimeCatalog
-> load_and_verify_runtime()
-> DirectAcpProcessFactory
```

- [ ] **Step 6: Extend deploy and installer contracts**

Do not add `primeRuntimeRoot` or `primeCurrentContract` to the chat service
manifest. The installed service already derives `prime/current.json` from its
verified `ROOK_INSTALL_ROOT`, and its persistent ACP root from
`ROOK_DATA_DIR`. Local deploy stages a new sibling runtime and verifies it
before writing `current.json`; it never overlays an existing runtime. Inno
Setup copies the complete generated staging artifact but does not list
`ROOK_DATA_DIR/rookchat/acp/v1` in `[InstallDelete]`, `[UninstallDelete]`, or
replacement cleanup.

Deployment and installation copy the complete staged payload and unchanged
manifest into a fresh temporary sibling, verify the result, atomically publish
the runtime-ID directory, and only then replace `current.json`. If that
runtime-ID directory already exists, they may reuse it only after complete
manifest and byte-for-byte verification. Any mismatch, missing file, or extra
authority file refuses without overlay, repair, or pointer replacement.

Keep Prime credentials/settings/kernel in Prime's supported mutable user locations. Do not relocate or parse them into the immutable runtime.

The installed product and documentation state the first-use behavior plainly:
users install only Rook, and bundled `uv` plus the matching local
`prime-agent-runtime` source require no separate setup. Prime may begin kernel
prewarm during first session creation; the first Prime IPython/Rook operation
may take longer while Prime downloads Python, creates its normal kernel,
installs the local runtime source, and resolves default packages. A failed
download or install surfaces as a Prime-owned tool failure and is never
converted into a RookChat installer, retry loop, or alternate kernel.

Implement `verify-installed-rookchat-acp.py` as a read-only deployment-custody verifier, not a qualification runner. It receives the exact clean implementation commit, worktree root, installed Rook root, installed chat-service manifest, and output path. It fails closed unless all of the following match:

```text
source Release RookNative.rhp -> installed RookNative.rhp
source managed net8.0/net7.0/net48 Rook.rhp payloads -> installed runtime payloads
closed source mcp_server/src/rook tree -> installed chat-service Rook tree selected by its manifest
installed rook-full manifest and literal SKILL.md bytes -> installed runtime-manifest.json
installed Prime executable, dist/prime-agent-runtime subtree, bundled uv, and complete runtime manifest -> current runtime pointer
chat-service manifest Python executable/source/install/data roots -> exact installed service and derived runtime/data paths
```

The verifier uses the same closed regular-file manifest rules as the product contracts, refuses symlinks/reparse-point escapes and unexpected extra authority files, and writes one bounded canonical JSON identity report only after every comparison succeeds. It does not launch the installed Python, Prime, Rhino, or any plugin. A later live gate rechecks this report and records actual service import origins separately.

- [ ] **Step 7: Invoke the approved package build, then run static gates**

The execution turn must receive the exact 40-hex `ApprovedPrimeCommit` named by
the Step 1 review and exact 64-hex `ApprovedBuildToolchainContractSha256` named
by the Step 3 review. They are literal approval inputs: do not derive either
from `HEAD`, the contract contents, a report, or the filesystem. Bind those two
values in the current PowerShell process, then run this command exactly once
from a fresh output root:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
$pwsh = 'C:/Program Files/PowerShell/7/pwsh.exe'
$prime = 'D:/prime-agent/.worktrees/prime-acp-no-daemon'
$contract = 'C:/UDEV/RookBuildTools/prime-acp/msys2-20260611-v1/build-toolchain-contract.json'
$output = 'C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/installer/runtime/prime/staging'
if ($ApprovedPrimeCommit -notmatch '^[0-9a-f]{40}$') {
    throw 'Step 1 review must supply the exact approved Prime commit.'
}
if ($ApprovedBuildToolchainContractSha256 -notmatch '^[0-9A-F]{64}$') {
    throw 'Step 3 review must supply the exact approved build-toolchain contract SHA-256.'
}
if (Test-Path -LiteralPath $output) {
    throw 'Prime staging output must be absent before packaging.'
}
& $pwsh -NoProfile -File scripts/package-prime-acp-runtime.ps1 `
    -PrimeWorktree $prime `
    -ExpectedPrimeCommit $ApprovedPrimeCommit `
    -OutputRoot $output `
    -BuildToolchainContract $contract `
    -ExpectedBuildToolchainContractSha256 $ApprovedBuildToolchainContractSha256
if ($LASTEXITCODE -ne 0) {
    throw "Prime packaging failed with exit code $LASTEXITCODE. Do not verify or install its staging output."
}

& $pwsh -NoProfile -File scripts/tests/prime-build-toolchain.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'Build-toolchain tests failed.' }
& $pwsh -NoProfile -File scripts/tests/prime-acp-runtime.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'Prime runtime tests failed.' }
& $pwsh -NoProfile -File scripts/tests/deploy-local-testing-guards.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'Deployment guard tests failed.' }
& $pwsh -NoProfile -File scripts/tests/release-installer-guards.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'Installer guard tests failed.' }
$python = 'C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server/.venv/Scripts/python.exe'
& $python scripts/verify-prime-acp-runtime.py --runtime-root $output --manifest "$output/runtime-manifest.json" --verify-only
if ($LASTEXITCODE -ne 0) { throw 'Staged Prime runtime verification failed.' }
& $python -m pytest mcp_server/tests/test_chat_prime_runtime.py mcp_server/tests/test_chat_acp_conversation.py mcp_server/tests/test_verify_installed_rookchat_acp.py -q
if ($LASTEXITCODE -ne 0) { throw 'Prime packaging Python tests failed.' }
```

The packaging invocation is the sole producer of
`installer/runtime/prime/staging/`; every subsequent verifier and installer test
consumes that exact tree. The verifier reads bytes only. Building the standalone artifact is allowed, but
`pi.exe`, providers, models, Rhino, Grasshopper, Rook MCP, and the installer are
not launched. The tests prove the npm release-tarball path is absent, the whole
standalone directory and manifest travel together, no generated runtime
authority is committed alone, no second runtime schema exists, relocation does
not change runtime identity, the production loader accepts the manifest, the
service owns its local MCP command, bundled uv is the first and only qualified
kernel-bootstrap executable, forbidden package/kernel/Python environment
overrides and every ambient `UV_*` key are removed case-insensitively, the six
product-owned uv values are exact in the final child environment, the artifact's
local Python runtime exactly matches the reviewed Prime build, the release build
cannot reach `npm ci` without the independently approved build-contract hash,
whole-root MSYS2 parity, empty npm user/global configuration, and exact
`cmd.exe` lifecycle shell, and ACP data remains outside every
replaceable runtime and installer cleanup path. Task 10 does not launch Prime
or qualify kernel creation; that single first-use runtime proof belongs to
Slice B.

- [ ] **Step 8: Commit Task 10**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add scripts/package-prime-acp-runtime.ps1 scripts/verify-prime-acp-runtime.py scripts/verify-installed-rookchat-acp.py scripts/tests/prime-acp-runtime.tests.ps1 mcp_server/src/rook/agent/chat/prime_runtime.py mcp_server/src/rook/agent/chat/acp_conversation.py mcp_server/tests/test_chat_prime_runtime.py mcp_server/tests/test_chat_acp_conversation.py scripts/deploy-local-testing.ps1 scripts/tests/deploy-local-testing-guards.tests.ps1 installer/RookSetup.iss scripts/tests/release-installer-guards.tests.ps1 installer/post_install.py mcp_server/tests/test_verify_installed_rookchat_acp.py
git commit -m "build(chat): package immutable Prime ACP runtime"
```

### Task 11: Complete The ChatRunner Non-Port And Installed-Product Static Gate

**Files:**
- Delete: `mcp_server/src/rook/agent/chat/conversation_store.py`
- Delete: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Delete: `mcp_server/src/rook/agent/chat/model_status.py`
- Delete: `mcp_server/src/rook/agent/chat/prompt_builder.py`
- Delete: `mcp_server/src/rook/agent/worker_first_csharp_application.py`
- Delete: `scripts/chatrunner_headless_qualification.py`
- Delete: `mcp_server/tests/test_chatrunner_headless_qualification.py`
- Delete: `mcp_server/tests/test_chatrunner_mcp_capability_gateway.py`
- Delete: `mcp_server/tests/test_model_override_options.py`
- Delete: `mcp_server/tests/test_rookchat_worker_first_csharp_integration.py`
- Delete: `mcp_server/tests/test_worker_first_csharp_application.py`
- Modify: `mcp_server/src/rook/agent/capability_inventory.py`
- Modify: `mcp_server/src/rook/agent/chat/tool_contracts.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/tests/test_capability_inventory.py`
- Modify: `mcp_server/tests/test_containment_agent_protocols.py`
- Modify: `mcp_server/tests/test_containment_catalogs.py`
- Modify: `mcp_server/tests/test_containment_guidance.py`
- Modify: `mcp_server/tests/test_dispatcher_safety.py`
- Modify: `mcp_server/tests/test_persona_prompt_schema.py`
- Modify: `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`
- Modify: `mcp_server/tests/test_rookchat_tool_contracts.py`
- Modify: `mcp_server/tests/test_rookchat_tool_schema_golden.py`
- Modify: `mcp_server/tests/test_rookchat_visible_dispatchability.py`
- Modify: `mcp_server/tests/test_rookchat_tool_transcripts.py`
- Modify: `mcp_server/tests/test_vertex_runtime_integration.py`
- Modify: `scripts/vertex_oauth_acceptance.py`
- Modify: `mcp_server/tests/test_vertex_acceptance_harness.py`
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

The audit must classify every current import or path reference before deleting the four production modules. The closed disposition is:

| Current caller | Disposition in Task 11 |
| --- | --- |
| `test_chatrunner_headless_qualification.py` | Delete with its obsolete qualification script. |
| `test_chatrunner_mcp_capability_gateway.py` | Delete; standard ACP MCP delivery and Rook gateway tests replace this private chat loop. |
| `test_rookchat_worker_first_csharp_integration.py` | Delete; worker-first chat execution is explicitly non-ported. |
| `test_model_override_options.py` | Delete; Prime owns model/authentication validation and RookChat retains only the closed creation-time reasoning enum. |
| `test_containment_agent_protocols.py` | Preserve internal-agent and plan-graph containment coverage; remove only the ChatRunner loop helpers/test. |
| `test_containment_catalogs.py` | Preserve MCP and internal-agent catalog containment; remove only ChatRunner projection assertions. |
| `test_dispatcher_safety.py` | Preserve dispatcher safety; replace fallback-ChatRunner catalog assertions with authoritative MCP/profile exposure assertions. |
| `test_persona_prompt_schema.py` | Preserve planner/spawn persona guidance by loading the shared persona source directly; do not retain `PromptBuilder`. |
| `test_rookchat_gh_script_creation_parity.py` | Preserve dispatcher and script-schema parity; obtain schemas from the authoritative Rook MCP surface rather than ChatRunner catalog builders. |
| `test_rookchat_tool_contracts.py` | Preserve shared schema/result normalization; replace its one ChatRunner catalog fixture with an authoritative MCP schema fixture. |
| `test_rookchat_tool_schema_golden.py` | Rewrite around the actual profiled Rook MCP schemas delivered through ACP; no local/fallback ChatRunner catalog remains. |
| `test_rookchat_tool_transcripts.py` | Rewrite around fake-ACP updates, bounded presentation, and structured Rook result projection; no LiteLLM/Conversation/ChatRunner loop remains. |
| `test_rookchat_visible_dispatchability.py` | Rewrite around ACP-visible Rook MCP schemas and shared dispatch/profile ownership; remove ChatRunner intercept classifications. |
| `test_vertex_runtime_integration.py` | Preserve BaseAgent, guardian, worker, DSPy, runtime-health, and provider-auth tests; remove ChatRunner/model-status/model-tool cases because ACP authentication and model selection belong to Prime. |

`test_containment_guidance.py` is not an importer but directly names the deleted `prompt_builder.py`; remove only that path from its scan and retain the shared persona/guidance assertions. The audit must report exactly zero remaining imports or path references to the four deleted modules before commit.

`scripts/vertex_oauth_acceptance.py` is the one non-test Python caller outside the obsolete headless qualification script. Remove only its ChatRunner acceptance operation and corresponding assertions in `test_vertex_acceptance_harness.py`; retain the separately supported DSPy and Chirp Vertex acceptance paths. Prime-owned ACP authentication is qualified by Slices B and C, not by adapting this legacy script into another chat client.

`worker_first_csharp_application.py` has no retained production caller after Task 6 and implements the removed RookChat worker-first mode directly. Delete it and its dedicated `test_worker_first_csharp_application.py`; preserve lower-level planner/worker modules that have independent non-chat ownership unless the audit separately proves them unowned.

Shared production cleanup is equally explicit. Remove the ChatRunner-only `list_chat_models`, `set_chat_model`, and `ui_block` pseudo-tool sentinels and their tool-group memberships. Retain internal-agent interceptions such as `request_tools`, `search_tools`, and the MCP capability gateway, but rename shared dispatchability terminology from `chatrunner_intercepted` to owner-neutral internal-agent terminology. Keep the capability inventory, dispatcher, gateway profile intersection, `tool_result_view`, `tool_contracts`, `execution_policy`, persona infrastructure used by planner/spawn, knowledge routes, authenticated HTTP middleware, service discovery, and generic panel rendering. The `server.py` gateway profile helper remains shared; only its obsolete ChatRunner wording changes.

If the audit finds another production owner or test caller beyond this closed classification, stop for plan correction instead of broadening deletion opportunistically.

- [ ] **Step 3: Update architecture and user docs**

Document one Prime ACP implementation, Prime-owned login via interactive `/login`, new-conversation model/reasoning selection, reopen behavior, target-unavailable behavior, image-history limits, release-level rollback, preserved data roots, and the explicit `session_recovery_required` limitation after service crash. State that Rook installs the required Prime executable and `uv` bootstrap tool with no separate software installation, while first IPython/Rook use may require an internet download and take longer as Prime creates its normal mutable kernel. Do not advertise compaction or IPython restoration guarantees.

- [ ] **Step 4: Run static and full offline unit gates**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_rookchat_acp_cutover.py tests/test_chat_acp_sdk_contract.py tests/test_chat_acp_storage.py tests/test_chat_acp_presentation.py tests/test_chat_acp_images.py tests/test_chat_acp_rook_results.py tests/test_chat_prime_runtime.py tests/test_chat_acp_client.py tests/test_chat_acp_process.py tests/test_chat_acp_conversation.py tests/test_chat_acp_two_service.py tests/test_chat_server.py tests/test_chat_integration.py tests/test_rook_full_skill_contract.py tests/test_rook_host_generation_targeting.py tests/test_gh_document_custody.py tests/test_verify_installed_rookchat_acp.py -q

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore
C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server/.venv/Scripts/python.exe scripts/verify-rookchat-acp-cutover.py --root C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
```

- [ ] **Step 5: Commit Task 11**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add mcp_server/src/rook/agent/chat/conversation_store.py mcp_server/src/rook/agent/chat/chat_runner.py mcp_server/src/rook/agent/chat/model_status.py mcp_server/src/rook/agent/chat/prompt_builder.py mcp_server/src/rook/agent/worker_first_csharp_application.py scripts/chatrunner_headless_qualification.py mcp_server/src/rook/agent/capability_inventory.py mcp_server/src/rook/agent/chat/tool_contracts.py mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/server.py mcp_server/tests/test_chatrunner_headless_qualification.py mcp_server/tests/test_chatrunner_mcp_capability_gateway.py mcp_server/tests/test_model_override_options.py mcp_server/tests/test_rookchat_worker_first_csharp_integration.py mcp_server/tests/test_worker_first_csharp_application.py mcp_server/tests/test_capability_inventory.py mcp_server/tests/test_containment_agent_protocols.py mcp_server/tests/test_containment_catalogs.py mcp_server/tests/test_containment_guidance.py mcp_server/tests/test_dispatcher_safety.py mcp_server/tests/test_persona_prompt_schema.py mcp_server/tests/test_rookchat_gh_script_creation_parity.py mcp_server/tests/test_rookchat_tool_contracts.py mcp_server/tests/test_rookchat_tool_schema_golden.py mcp_server/tests/test_rookchat_visible_dispatchability.py mcp_server/tests/test_rookchat_tool_transcripts.py mcp_server/tests/test_vertex_runtime_integration.py scripts/vertex_oauth_acceptance.py mcp_server/tests/test_vertex_acceptance_harness.py mcp_server/tests/test_rookchat_acp_cutover.py docs/CURRENT_ARCHITECTURE.md README.md QUICK_START.md AGENT_SETUP.md scripts/verify-rookchat-acp-cutover.py
git commit -m "refactor(chat): remove ChatRunner product path"
```

### Task 12: Build The External A-E Qualification Ladder With Hard Review Stops

**Files:**
- Create: `scripts/qualification/rookchat_prime_acp_common.py`
- Create: `scripts/qualification/rookchat_prime_acp_precontact.py`
- Create: `scripts/qualification/rookchat_prime_acp_slice_c.py`
- Create: `scripts/qualification/rookchat_prime_acp_slice_d.py`
- Create: `scripts/qualification/rookchat_prime_acp_slice_e.py`
- Create: `scripts/qualification/fixtures/deterministic_provider.py`
- Create: `scripts/qualification/protocols/rookchat-prime-acp-precontact-v1.json`
- Create: `scripts/qualification/protocols/rookchat-prime-acp-slice-c-v1.json`
- Create: `scripts/qualification/protocols/rookchat-prime-acp-promotion-v1.json`
- Create: `scripts/qualification/protocols/rookchat-prime-acp-slice-d-v1.json`
- Create: `scripts/qualification/protocols/rookchat-prime-acp-slice-e-v1.json`
- Create: `mcp_server/tests/test_rookchat_prime_acp_qualification.py`
- Create after each authorized execution: `docs/superpowers/reports/<date>-rookchat-prime-acp-<gate>.md`

**Interfaces:**
- Produces: external, create-only, finite qualification artifacts for combined model-free pre-contact A+B and separately authorized C, D, and E.
- Consumes: installed artifacts and public product boundaries only; no qualification module is imported by `mcp_server/src/rook`.

- [ ] **Step 1: Write RED protocol-custody tests**

Each protocol must contain exact schema/version, clean implementation commit, installed runtime/skill manifests, prompt/input hashes, wall-clock/token/process-close limits, target/profile identity, evaluator identity when applicable, fresh evidence root, and a one-execution version. The A+B pre-contact protocol additionally binds the fresh `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, and `ROOK_DATA_DIR`; the product-derived `UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR`; the derived absent-before kernel path; the complete six-key product-owned `UV_*` map; the exact seeded ambient `UV_*` and proxy-key cases; Prime's required `--offline` flag; the deny-by-default outbound-proxy identity and exact inserted `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY` values; the complete expected final Prime child-environment map and hash; and the exact admitted host set `github.com`, `api.github.com`, `objects.githubusercontent.com`, `release-assets.githubusercontent.com`, `releases.astral.sh`, `pypi.org`, and `files.pythonhosted.org`. The promotion protocol additionally binds MSVC toolset `14.44.35207`, Release configuration, the exact deployment command, expected source/installed artifact paths, and installed-verifier identity. The runner refuses existing evidence roots, hash drift, missing limits, mismatched commits, or any product import of `scripts/qualification`.

Each frozen live version executes once and its result is immutable. Any correction requires a newly versioned protocol, fresh evidence root, and separate authorization; the runner never retries or overwrites a failed version.

- [ ] **Step 2: Implement one finite common runner**

`rookchat_prime_acp_common.py` may hash inputs, create evidence roots, write bounded JSON results, and own directly launched qualification processes. It must not poll the Windows process table, use PowerShell process probes, kill by name/PID discovery, retry, alter a timeout after failure, or become a product dependency.

- [ ] **Step 3: Implement Slice A against the fake ACP agent**

Exercise the exact C#-equivalent HTTP boundary and all model-free cases listed in spec section 15.1: protocol/capability admission, literal verified system-contract bytes and rendered-Windows-argv bounds, bounded stderr drainage under pipe pressure, service-owned prompt survival after HTTP waiter cancellation, close/delete/shutdown detach-before-retirement races, first-turn publication, saved/unsaved working-directory custody, internal latest-runtime selection, two-service claim contention, crash claim preservation, failed/uncertain spawn, SDK-callback source-ordinal preservation, generation fences, overflow cancellation, permission policy, cache/image/model arguments, MCP injection, strict Rook envelope projection, GH schemas, bounds, 20-second startup/60-second call contract projection, and close failures.

- [ ] **Step 4: Implement Slice B against the installed Prime artifact and deterministic provider**

Use a fresh evidence root containing exact isolated `PRIME_AGENT_CODING_AGENT_DIR`,
`HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, and `ROOK_DATA_DIR` paths.
The production child-environment builder must derive `UV_CACHE_DIR` and
`UV_PYTHON_INSTALL_DIR` beneath that fresh Rook data root and insert the other
four fixed uv settings. Before `session/new`, prove that every isolated root is
fresh, the kernel root derived from `USERPROFILE` is absent, and no managed
Python or uv cache exists. Use a local deterministic provider and a unique
daemon-socket tripwire. The final environment must neither discover nor register
a system Python or consume ambient uv configuration.

Construct the admitted environment without ambient `uv`, Hermes, WSL, Git Bash,
or the Rook worktree venv on `PATH`; the manifest-bound runtime `tools/uv`
directory must be first. Seed canonical, lowercase, and mixed-case variants of
every forbidden exact key from Task 10 plus representative index, mirror,
find-links, config-file, offline, Python-download, and unknown-future `UV_*`
names into the harness's ambient input. Prove the production child-environment
builder removes every inherited `UV_*` key and emits only the exact six
product-owned values. Do not seed a kernel or reuse a warm Prime home.

Before constructing the qualification launch environment, remove inherited
`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY` variables
case-insensitively, including lowercase and mixed-case variants. Insert only the
protocol-owned deny-by-default proxy URL and loopback bypass. Pass that map
through the production process factory, then compare the complete final
nonsecret child environment and its canonical hash with the frozen protocol
before spawn.

Launch the installed Prime artifact with `--offline` so Prime's updater,
catalog, and unrelated startup network operations remain disabled. This flag
does not make the separately admitted uv bootstrap offline. Route all
non-loopback traffic through a qualification-owned deny-by-default proxy; the
frozen protocol admits only `github.com`, `api.github.com`,
`objects.githubusercontent.com`, `release-assets.githubusercontent.com`,
`releases.astral.sh`, `pypi.org`, and `files.pythonhosted.org`, and the evidence
retains a bounded request ledger. Any required destination outside that set is
a terminal result for this protocol version. Loopback remains available only to
the deterministic provider and Rook MCP double. No proxy or network policy
enters product runtime.

Prime may start kernel prewarm during `session/new`; do not attribute bootstrap
initiation to the first prompt. Prove the actual sequence:

```text
kernel root, uv cache, and uv-managed Python absent before session/new
-> Prime creates its ordinary mutable kernel through manifest-bound uv
-> uv installs the manifest-bound local dist/prime-agent-runtime source
-> first deterministic prompt executes real IPython and mcp.call_tool("rook", ...)
```

The installed runtime must execute
`initialize -> session/new -> session/prompt -> session/close -> EOF`,
materialize the assigned file, reopen the same file, and answer consistently
using prior context. Exercise lazy MCP start, representative Rook calls
completing inside Prime's fixed 20-second startup and 60-second call limits,
cancellation, MCP cleanup, fresh MCP establishment after reopen, manifest
identity, required flags, zero tripwire contact, and clean direct-child exit.
Retain the bundled uv path/hash/version, absent-before/present-after kernel
root/cache/managed-Python paths, bounded bootstrap output, local Python-runtime
source identity, resulting `Scripts/python.exe` path, complete final child-
environment map/hash, and the bounded admitted network ledger. Product code
still reads only the first-line header envelope.

The pre-contact artifact makes no external provider/model, Rook, Rhino, or
Grasshopper contact. It is intentionally not network-disconnected: first-time
Prime kernel setup downloads Python and resolves default packages through the
bundled uv, while the matching Prime runtime itself comes from the installed
manifest-bound local subtree. The frozen protocol gives that one bootstrap a
predeclared wall-clock bound; failure is terminal for that protocol version,
with no retry or timeout adjustment. The bounded proxy ledger supports only
this gate's admitted-download claim, not a general product network-containment
claim.

The combined model-free pre-contact gate also runs the static installed-product verifier against a staged install, proves the source-to-installed hash map is complete, and proves the deployment/installer guards preserve ACP data. This is not permission to deploy into Rhino's live plugin directories.

- [ ] **Step 5: Run only model-free tests, then commit the frozen qualification code**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_rookchat_prime_acp_qualification.py -q

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add scripts/qualification mcp_server/tests/test_rookchat_prime_acp_qualification.py
git commit -m "test(chat): freeze ACP qualification ladder"
```

- [ ] **Step 6: STOP at the combined A+B pre-contact review gate**

Do not execute `rookchat_prime_acp_precontact.py` yet. Present the frozen runner/protocol hashes, implementation commit, installed runtime manifest, tests, and proof that evidence roots are absent. Independent approval must explicitly authorize one A+B execution.

- [ ] **Step 7: After authorization, execute A+B exactly once and stop**

Run the exact independently reviewed command only. Whether it passes or fails, make the evidence root read-only, hash every bounded evidence file, write the A+B report, commit only that report, and stop for independent review. Do not continue to Slice C automatically.

- [ ] **Step 8: Prepare and review Slice C without executing it**

Freeze one tiny image whose answer depends on visible content, its SHA-256, prompt, a known vision-capable fully qualified subscription model, reasoning value, exact installed runtime, time/token/close limits, and fresh evidence root. The product does not inspect `auth.json`; external evidence may claim OAuth only if separate nonsecret Prime-owned metadata proves it. Otherwise report a Prime-managed authenticated subscription call.

STOP for explicit Slice C authorization. After one authorized execution, seal evidence and stop for review. No Rook/Rhino/GH server participates.

- [ ] **Step 9: Promote one exact reviewed implementation into the installed product and stop**

Only after sealed Slice C evidence is independently accepted, freeze the promotion protocol with the exact clean implementation commit, source and runtime manifests, verifier hash, absent evidence root, Release configuration, MSVC `14.44.35207`, and this exact existing deployment command:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
pwsh -NoProfile -File scripts/deploy-local-testing.ps1 -Configuration Release -VCToolsVersion 14.44.35207 -SkipChirpInstall
```

Do not use `-SkipBuild`; native and managed outputs must be built from the frozen commit. Do not use `-UseRepoVenv`; the deployed chat-service manifest and installed Python payload must be the product consumers qualified for Slices D and E. Before execution, stop for explicit promotion authorization and perform the deployment script's normal user-controlled Rhino/Rook shutdown prerequisites. Do not add process discovery or cleanup to the qualification runner.

After the one authorized deployment, run `verify-installed-rookchat-acp.py` against the exact clean commit and installed paths. Seal its bounded identity report under the fresh promotion evidence root, commit only the report, and stop for independent review. A deployment or verification failure is immutable evidence for that protocol version; do not repair in place or proceed. Slice D remains unauthorized until the promotion report is approved.

- [ ] **Step 10: Prepare and review Slice D without executing it**

Freeze one deterministic Rhino/GH fixture and one readonly prompt. Rehash the installed native, managed, Python-service, Rook skill, and Prime runtime identities immediately before contact and require exact equality with the approved promotion report. Record those installed identities, actual service import origins, before/after structural snapshots, target identity, absence of mutation receipts, exact profile, and one prompt only. Fresh-MCP-after-reopen and readonly mutation refusal remain model-free; do not add a second stochastic prompt. Any installed drift refuses before Prime or Rook contact.

STOP for explicit Slice D authorization. After one authorized execution, seal evidence and stop for review.

- [ ] **Step 11: Prepare and review Slice E without executing it**

Rehash the same installed identities against the approved promotion report before contact; any drift refuses. Seed the established adjustable X-axis point-row defect before conversation creation. Freeze the user prompt, baseline identities, full profile, model/reasoning, installed identities, limits, evaluator source/hash, and fresh evidence root. The Actor's exact ending is:

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

- [ ] **Step 12: Run final source gates after the ladder is authored**

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
3. Review Tasks 10-12's authored packaging, replacement, data-retention, and qualification code as one model-free pre-contact gate covering technical Slices A and B. Build verification may produce artifacts but must not launch Prime.
4. Review the frozen combined A+B package, then authorize at most one execution.
5. Review sealed A+B evidence before authorizing Slice C.
6. Review sealed C evidence before authorizing one installed-product promotion.
7. Review the sealed promotion identity report before authorizing Slice D.
8. Review sealed D evidence before authorizing Slice E.
9. Review sealed E evidence before any release cutover decision.

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
- [ ] The installed Prime artifact, Markdown skill, and pinned official uv bootstrap executable/licenses are closed-manifest verified; the Prime child resolves bundled uv before ambient tools; historical runtimes/data survive update, rollback, and data-retaining uninstall.
- [ ] One approved source commit is built with MSVC 14.44, deployed through the existing product path, and rehashed at every installed consumer before Slices D and E.
- [ ] ChatRunner, backend selection, private RPC, daemon topology, worker auth, leases, process probes, kernel RPC, and Task 7 code are absent.
- [ ] Combined model-free pre-contact A+B and separately authorized C/D/E gates preserve immutable, bounded evidence without retries or overwrite.
