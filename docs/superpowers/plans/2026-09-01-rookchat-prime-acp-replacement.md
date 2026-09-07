# RookChat Prime ACP Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ChatRunner with one product implementation in which the existing RookChat panel talks through the Python chat service to one directly owned, daemon-free Prime ACP process per open conversation, while preserving Rook's target, mutation, receipt, readiness, and evidence authority.

**Architecture:** C# remains the user-input and presentation client of the authenticated local HTTP service. The Python service uses the official Python ACP SDK to own one Prime process/ACP connection, a complete durable association, a non-expiring `open.claim`, and bounded disposable presentation history; Prime remains the sole conversation and reasoning authority, and Rook remains the sole host-operation authority. Standard ACP MCP injection supplies a manifest-bound Markdown-only `rook-full` skill and the service-owned `rook` stdio server; no private Prime RPC, daemon topology, backend abstraction, or ChatRunner fallback survives cutover.

**Tech Stack:** C#/.NET 8, 7, and 4.8 with Eto/WebView2; Python 3.10+ with `aiohttp` and exact `agent-client-protocol==0.12.1`; ACP 1.3 as implemented by the pinned Prime artifact; MCP 1.28.1; Rhino 8 C++ SDK; Grasshopper managed bridge; Ubuntu 24.04 Bash release builds with local WSL2 selection; PowerShell/Inno Setup installation tooling; pytest/xUnit.

**Spec:** `docs/superpowers/specs/2026-09-01-rookchat-prime-acp-replacement-design.md` at the revision carried by this documentation amendment (SHA-256 `93D3E964A5F217B03BA6A3B31D01D5DDEC2068B302532634FC58F6E07C21BA2D`).

## Global Constraints

- This plan is authored against the exact specification hash above. Implementation begins only from the exact approved documentation commit later named by review. Do not reset to an older specification or replay superseded RPC Tasks 0-7.
- Prime upstream remains `c718bf3c30fd8da206ed551837cbb54f7ad15948`. Commit `1b9dfabb04901de4823d259c88b39dfc78ec3b34` is the reviewed implementation precursor, not release authority. Before another build, organize the five approved concerns as the short ordered patch series in the specification, independently review every commit and parent, and freeze one exact final head as runtime identity. Do not add unrelated Prime behavior or another runtime contract.
- Preserve every quarantined Task 7 worktree and retained evidence byte-for-byte. Never copy product code from those worktrees.
- Pin `agent-client-protocol==0.12.1` exactly and use its public `spawn_agent_process`, `ClientSideConnection`, schema models, cancellation notification, and close APIs.
- Launch the exact installed Prime executable with an argument array and `--mode acp --no-daemon --no-approve`; never use production `--offline`, a shell, global npm, a daemon socket, PID discovery, PowerShell probing, process scanning, or process-name cleanup. Scrub inherited `PI_OFFLINE` case-insensitively from the Prime child environment. The Prime and Rook MCP executable paths are absolute and never selected through `PATH`. The sole intentional exception is upstream Prime's supported kernel bootstrap lookup for `uv`: RookChat prepends the exact manifest-bound `tools/uv` directory, and qualification proves that executable was selected before any ambient entry. At the reviewed Prime baseline, the direct ACP composition cannot reach managed `fd`/`rg` acquisition; the causal source-composition test owns that invariant. Slice B separately checks managed-helper artifact absence and observed configured proxy destinations, without claiming encrypted URL visibility or exhaustive network containment.
- Persist associations, not broker lifecycle. Prime JSONL is the only authoritative transcript/goal/settings/compaction store.
- A durable association is create-only, complete, materialized, has a nonempty Prime header ID, and is reopenable only when no `open.claim` exists and custody checks pass.
- The atomic non-expiring `open.claim` has no metadata or recovery logic. Remove it only after the directly owned Prime child is observed exited, or when launch positively proves no child was created.
- Never replay an interrupted prompt, tool call, or mutation. Re-observe authentic Rook state after every reopen before dependent work.
- Keep all current-turn and presentation representations within the exact limits in the approved spec; persist no thoughts, raw ACP events, image bytes, unrestricted `_meta`, or credentials.
- Prime owns authentication. RookChat never accepts `--api-key`, reads `auth.json`, or forwards credentials loaded from Rook's installed `.env`.
- New conversations may pass a fully qualified `--model` and one of `off|minimal|low|medium|high|xhigh|max`; reopen passes neither override.
- The installed `rook-full` package is Markdown-only. Do not add a Rook-owned Python facade or contract-specific kernel.
- The immutable Prime runtime carries official `uv` 0.12.3 at fixed relative path `tools/uv/uv.exe` and the final Prime build's complete `dist/prime-agent-runtime` subtree. Source, license, executable, and subtree custody share the same closed manifest. Prime remains the sole owner of its ordinary mutable kernel environment. Remove every inherited `UV_*` key case-insensitively and insert only the six product-owned values derived from `ROOK_DATA_DIR`; no ambient kernel override, package-root override, virtual environment, uv policy, or Rook-venv `uv` is runtime authority.
- Prime release builds use the portable `scripts/build-prime-acp-runtime.sh` entrypoint in Ubuntu 24.04 on a Linux-native filesystem. Local Windows release work selects the installed `Ubuntu-24.04` WSL2 distribution; CI may invoke the same Bash entrypoint directly. WSL, Node, npm, Bun, Git, `zip`, and `unzip` are release-machine dependencies only and never enter the Rook installer or customer runtime.
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

### Task 10: Build, Manifest, And Promote One Complete Prime Runtime

**Files:**
- Delete before writing replacement tests: `scripts/tests/prime-build-toolchain.tests.ps1`
- Delete before writing replacement tests: `scripts/tests/prime-acp-runtime.tests.ps1`
- Create: `scripts/build-prime-acp-runtime.sh`
- Create: `scripts/tests/prime-wsl-build.tests.sh`
- Create: `mcp_server/src/rook/agent/chat/prime_runtime_artifact.py`
- Create: `mcp_server/tests/test_prime_runtime_artifact.py`
- Create: `scripts/package-prime-acp-runtime.py`
- Create: `mcp_server/tests/test_package_prime_acp_runtime.py`
- Create: `third_party/prime-agent/LICENSE`
- Modify: `mcp_server/src/rook/agent/chat/prime_runtime.py`
- Modify: `mcp_server/src/rook/agent/chat/service_main.py`
- Modify: `mcp_server/src/rook/agent/chat/acp_conversation.py`
- Modify: `mcp_server/tests/test_chat_prime_runtime.py`
- Modify: `mcp_server/tests/test_chat_integration.py`
- Modify: `mcp_server/tests/test_chat_acp_conversation.py`
- Modify: `installer/post_install.py`
- Create: `mcp_server/tests/test_post_install_prime_runtime.py`
- Modify: `scripts/deploy-local-testing.ps1`
- Modify: `scripts/tests/deploy-local-testing-guards.tests.ps1`
- Modify: `installer/RookSetup.iss`
- Modify: `scripts/tests/release-installer-guards.tests.ps1`
- Modify: `.agents/skills/build-release/SKILL.md`
- Modify: `.claude/skills/build-release/SKILL.md`
- Modify: `.agents/skills/build-release/references/iss-source-paths.md`
- Modify: `.claude/skills/build-release/references/iss-source-paths.md`
- Create: `scripts/verify-installed-rookchat-acp.py`
- Create: `mcp_server/tests/test_verify_installed_rookchat_acp.py`
- Generate after the implementation review, never commit: `installer/runtime/prime/staging/<assembly-attempt-generation>/runtimes/<runtime-id>/**`
- Retain outside source and product trees: the Git bundle, WSL build record, transferred Prime ZIP, downloaded `uv` inputs, and artifact review hashes

**Interfaces:**
- Consumes: the exact specification SHA-256 named in this plan header; Prime upstream `c718bf3c30fd8da206ed551837cbb54f7ad15948`; reviewed implementation precursor `1b9dfabb04901de4823d259c88b39dfc78ec3b34`; the independently approved final ordered Prime patch series; Prime's `scripts/build-binaries.sh --platform windows-x64 --frozen-model-catalog`; Task 8's tracked `installer/agent-assets/prime-skills/rook-full`; the installed Rook Python service; and the existing installer/local-deployment entrypoints.
- Produces: one portable Ubuntu build entrypoint; one complete upstream `pi-windows-x64.zip`; one Rook-owned runtime-manifest implementation; one offline Windows packager; one shared promotion function used by installer and local deployment; one closed `current.json` selector; one installed-product verifier; and an ignored, complete installer runtime payload.
- Does not produce: a build-toolchain contract, MSYS2 root, per-tool executable manifest, private-helper test loader, product WSL dependency, Prime lifecycle execution, project-trust database, permission UI, helper-download facade, or release-time patch registry.

The bounded Prime compatibility corrections must be organized and independently
approved before another real build is authorized. Their initial read-only
precondition is:

```text
Prime HEAD = 1b9dfabb04901de4823d259c88b39dfc78ec3b34 (reviewed precursor only)
Prime base = c718bf3c30fd8da206ed551837cbb54f7ad15948
Prime tracked and untracked status = clean
```

The precursor contains the first four reviewed behaviors, including the public
`--frozen-model-catalog` selector. Step 7 converts those concerns and the two
new product-security selectors into the short ordered series defined by the
specification, proves each public seam causally, records the `5c2750bd`
adoption or deferral decision, and stops before creating another build attempt.
The real Windows binary checks remain part of the later post-build review and
are not inferred from focused source tests.

All generated release payloads remain ignored. Customers receive the completed
Windows runtime through the Rook installer and never need WSL, Node, npm, Bun,
Git, `zip`, `unzip`, or a separate Prime installation.

The Task 10 consumer trace is normative. At each review boundary, replay it in
this order without inserting another authority artifact:

```text
approved Rook implementation
-> exact reviewed build entrypoint
-> isolated WSL builder
-> independently reviewed ZIP hash
-> exact reviewed Windows packager and verifier
-> one verified Prime payload
-> sealed Rook wheel and verification venv
```

Then follow the applicable consumer branch:

```text
Release:
verified payload + sealed wheel
-> ISCC
-> installer stages incoming payload
-> post_install invokes shared promotion
-> installed verification

Local deployment:
verified payload + sealed wheel
-> deployment stages incoming payload
-> post_install invokes shared promotion
-> installed verification
```

The concrete handoffs are:

| Producer | Exact handoff | Consumer and working directory | Admission and failure rule |
| --- | --- | --- | --- |
| Clean Prime Git worktree | Build-attempt-scoped Git bundle advertising exactly the reviewed `refs/heads/codex/rookchat-prime-final-series` ref | Exact-branch `git clone --no-checkout` beneath the Linux-native WSL build-attempt root, followed by detached checkout of the approved SHA | Exact approved final head, named-ref resolution, direct parent, complete ordered series, and clean tracked source before the bundle; a failed build attempt is retained and never reused. |
| `scripts/build-prime-acp-runtime.sh` from the exact independently approved clean Rook implementation | WSL `pi-windows-x64.zip` and diagnostic build record | Windows transfer step; build runs with the Prime worktree as cwd | Rook identity is checked before and after execution; post-build Prime commit/clean/lockfile checks precede ZIP authority; WSL and Windows archive hashes must match. |
| `scripts/package-prime-acp-runtime.py` and `prime_runtime_artifact` from the same exact independently approved clean Rook implementation | One assembly-attempt-scoped `runtimes/<runtime-id>` payload | Build-release and local-deploy consumers receive the same canonical payload path | Rook identity is checked before and after assembly; closed manifest verification precedes either consumer; failure leaves only that assembly attempt non-authoritative. |
| Existing private-runtime and wheelhouse release scripts from the exact Rook source | Sealed Python runtime, wheelhouse, verification venv, and source manifest | Installer or local `post_install.py` before it invokes promotion | Exact release version and final implementation commit must match; the verifier imports from the sealed wheel only; stale payloads refuse before promotion. |
| Build-release skill from the Rook repo root | Verified payload plus `/DPrimeRuntimePayload=<exact-path>` | Exact `verify-rook-venv/Scripts/python.exe -I -m rook.agent.chat.prime_runtime_artifact verify` from repo-root cwd, then `installer/RookSetup.iss` | Exactly one payload is verified by the sealed wheel before ISCC; ISCC failure cannot publish a runtime. |
| `scripts/deploy-local-testing.ps1` from the Rook repo root | Exact verified payload copied to one unique incoming directory | The same installed `post_install.py` promotion path used by the installer | Promotion alone may create runtime siblings or `current.json`; failed incoming generations are never selected. |
| Rook-owned promotion code | Verified immutable runtime sibling and atomic `current.json` | New-conversation runtime selection | Pointer and payload verify before argv construction; invalid authority refuses without scanning for an alternative. |

- [ ] **Step 1: Replace the abandoned RED matrix with one portable build-entrypoint test**

Before creating replacement tests, prove the two rejected scripts are the only
untracked files and remove only those exact paths:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
$expected = @(
    '?? scripts/tests/prime-acp-runtime.tests.ps1',
    '?? scripts/tests/prime-build-toolchain.tests.ps1'
)
$actual = @(git status --short | Sort-Object)
if (Compare-Object ($expected | Sort-Object) $actual) {
    throw 'The preserved RED-script boundary changed; stop.'
}
Remove-Item -LiteralPath scripts/tests/prime-acp-runtime.tests.ps1
Remove-Item -LiteralPath scripts/tests/prime-build-toolchain.tests.ps1
```

Create `scripts/tests/prime-wsl-build.tests.sh` as an ordinary Bash test that
creates a temporary Git repository on a Linux-native filesystem. Its fake Prime
tree contains a normal executable `scripts/build-binaries.sh`; that fake records
argv and environment, optionally changes the lockfile or tracked source, and
creates a synthetic `packages/coding-agent/binaries/pi-windows-x64.zip`.
Fixture-local fake tool commands provide deterministic version output and a
recording `timeout` boundary; the test does not depend on host Node, npm, Bun,
`zip`, or `unzip` behavior.

The test invokes only the public `scripts/build-prime-acp-runtime.sh` entrypoint,
passing the temporary repository's real commit and parent as the required
expected identities, and covers these cases:

```text
exact HEAD, parent, clean tree, and package-lock hash admit the fake build
missing, malformed, or extra entrypoint arguments refuse before tool use
an expected-commit mismatch refuses before the fake builder runs
a dirty tracked tree refuses before the fake builder runs
/mnt/c and /mnt/d build roots refuse without requiring a WSL marker
a findmnt result of drvfs, 9p, ntfs, or fuseblk refuses
absence of uname, findmnt, readlink, or head refuses during prerequisite admission
every admitted child tool command and canonical target is Linux-native and outside /mnt/*
the constructed child PATH contains only unique admitted Linux command directories in their original admitted PATH precedence
a fixture with conflicting same-name executables proves the final clean environment resolves the exact command path and canonical target admitted by preflight
any final-environment command-path, canonical-target, Node-version, or Bun-version mismatch refuses before the fake builder runs
the default fake builder sees only the six deliberate inputs plus Bash-generated PWD, SHLVL, and _
an explicit network fixture admits only HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, and NO_PROXY after ambient values are cleared
lowercase, mixed-case, unknown, or ambient network-setting names refuse; the build record contains admitted names but no values
ambient API keys, provider variables, PRIME_*, PI_*, and NPM_CONFIG_* are absent
argv is exactly ./scripts/build-binaries.sh --platform windows-x64 --frozen-model-catalog
the direct command is wrapped by timeout --kill-after=30s 1800s
post-build HEAD, clean-tree, and lockfile changes reject the ZIP
missing, linked, or non-regular ZIP output refuses
success records observed tool versions, exact command, times, outcome, and ZIP SHA-256
complete builder stdout and stderr are retained in one create-only attempt-owned build-console.log
an existing build-console.log refuses before the fake builder starts
test-harness failure is distinct from an expected product refusal
```

Run the test directly in Ubuntu. Local Windows execution selects WSL2; CI runs
the same test without the `wsl.exe` prefix:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
wsl.exe -d Ubuntu-24.04 --exec /bin/bash -lc 'cd /mnt/c/UDEV/Rook/.worktrees/rookchat-prime-acp-reset && bash scripts/tests/prime-wsl-build.tests.sh'
```

Expected RED: only the named `build_entrypoint_missing` case fails because
`scripts/build-prime-acp-runtime.sh` does not exist. Fixture, Git, and assertion
failures terminate with a different harness-error outcome.

Implement the public script with this fixed interface and constants:

```bash
scripts/build-prime-acp-runtime.sh \
  --prime-worktree /home/$USER/rook-prime-acp/prime-agent \
  --build-record /home/$USER/rook-prime-acp/build-record.txt \
  --expected-prime-commit "$approved_prime_head" \
  --expected-prime-parent c718bf3c30fd8da206ed551837cbb54f7ad15948

EXPECTED_BUN_VERSION=1.3.14
MINIMUM_NODE_VERSION=22.8.0
BUILD_TIMEOUT_SECONDS=1800
BUILD_KILL_AFTER_SECONDS=30
```

`approved_prime_head` is the exact 40-hex final series head supplied by the
independent Step 7 compatibility review. The public script receives and checks
that identity; it never discovers or chooses a Prime head.

The script resolves the worktree and rejects Windows-hosted filesystems. It
requires Ubuntu 24.04 but no WSL-specific marker. Before constructing the child
environment, resolve `bash`, `sh`, `node`, `npm`, `bun`, `git`, `zip`, `unzip`,
`dirname`, `rm`, `mkdir`, `cp`, `ls`, `env`, `timeout`, `sha256sum`, `uname`,
`findmnt`, `readlink`, and `head`. For
each command, require both the command path and its canonical target to be a
regular executable on a Linux-native filesystem and outside `/mnt/*`. Construct
`linux_build_path` from the unique parent directories of those admitted command
paths while preserving their order in the admitted input `PATH`; inherited
entries that contain no admitted command never flow into the child. Inside the
exact clean child environment and before the builder starts, resolve every
required command again and require its command path and canonical target to
equal the preflight pair. Recheck Node and Bun versions through that final
environment. Any conflict, changed precedence, or mismatch refuses. Only Bun is
exact and Node has the fixed minimum. Record observed Node, npm, Bun, Git,
`zip`, and `unzip` versions as diagnostic provenance, not authority.

For each invocation, the script creates one unique empty support root on the
same Linux-native filesystem but outside the Prime source. Fresh `home` and
`tmp` children supply `HOME` and `TMPDIR`; neither an existing support root nor
state from a failed invocation is reused.

Immediately before the build, require exact HEAD/parent, a clean tracked tree,
one regular `package-lock.json`, its SHA-256, and absent ignored build output.
Invoke Prime exactly through an invocation-local environment:

```bash
env -i \
  HOME="$fresh_home" \
  PATH="$linux_build_path" \
  LANG=C.UTF-8 \
  LC_ALL=C.UTF-8 \
  TMPDIR="$fresh_tmp" \
  CI=1 \
  timeout --kill-after=30s 1800s \
  ./scripts/build-binaries.sh --platform windows-x64 --frozen-model-catalog
```

Those six assignments are the only deliberate child-environment inputs. Bash
may add only `PWD`, `SHLVL`, and `_`; the fixture records the environment from
inside the fake builder and rejects every other key. No provider credential,
Prime override, `NPM_CONFIG_*` value, or other ambient variable is admitted.
The default network-input map is empty. A reviewed local or CI invocation may
explicitly add only uppercase `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and
`NO_PROXY` after clearing all ambient environment values; lowercase,
mixed-case, and other network-setting names refuse. The build record stores
only the admitted variable names, never values. The implementation keeps this
as a small invocation argument/map and does not create another manifest or
configuration subsystem.

After exit zero, recheck exact HEAD, clean tracked state, unchanged lockfile
hash, and one regular ZIP before hashing it. The build record is bounded plain
text, diagnostic only, and written create-only. A failed invocation never
adopts existing output and never retries automatically.

Rerun the Bash test and require all cases to pass. This step launches only the
fixture builder, never Prime's real builder.

- [ ] **Step 2: Implement one manifest core and the offline Windows packager through TDD**

Write `mcp_server/tests/test_prime_runtime_artifact.py` first. Fix these public
interfaces before implementation:

```python
# mcp_server/src/rook/agent/chat/prime_runtime_artifact.py
@dataclass(frozen=True)
class RuntimeManifestMetadata:
    acp_protocol_version: int
    python_acp_sdk_version: str
    rook_skill_manifest_sha256: str

@dataclass(frozen=True)
class VerifiedRuntimePayload:
    root: Path
    runtime_id: str
    manifest: Mapping[str, object]
    rook_skill_system_prompt: str

def canonical_json_bytes(value: object) -> bytes:
    raise NotImplementedError
def create_runtime_manifest(
    payload_root: Path,
    metadata: RuntimeManifestMetadata,
) -> str:
    raise NotImplementedError
def verify_runtime_payload(
    runtime_root: Path,
    expected_runtime_id: str | None = None,
) -> VerifiedRuntimePayload:
    raise NotImplementedError
def read_current_runtime_id(prime_root: Path) -> str:
    raise NotImplementedError
def promote_incoming_runtime(incoming_root: Path, prime_root: Path) -> str:
    raise NotImplementedError
def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError
```

The module CLI has only two subcommands. `verify --runtime-root
<path> --expected-runtime-id <id>` calls `verify_runtime_payload()` and emits no
authority file. `promote --incoming-root <path> --prime-root <path>` calls
`promote_incoming_runtime()`. Both return nonzero on any refusal. Tests invoke
these public subcommands rather than extracted private helpers.

The initial RED tests cover canonical UTF-8/no-BOM/sorted-key/compact/LF bytes,
the exact closed manifest schema from specification Section 12.5, ordinal file
rows, duplicate-normalized paths, non-regular/link/reparse paths, closed file
sets, runtime-ID equality, and the fixed Windows/AMD64/ACP compatibility.
New assembly retains the exact approved Prime/uv build pins. Historical loading
validates recorded provenance and internal source consistency as specified in
Section 12.5, without requiring the newest build pins. A two-release fixture
must promote the new runtime, then reopen both recorded IDs through the actual
loader and argv constructor without changing old bytes; tampering still refuses.
Shared verification rejects invalid UTF-8 and root-skill content above 16,384
bytes before manifest publication or pointer advancement, returning the exact
retained decoded text for launch. These are artifact checks, not just launch checks.

Add one hand-frozen oracle whose literal fixture rows, literal expected manifest
bytes, and literal uppercase runtime ID are reviewable constants. The test must
compare exact bytes and the exact ID; it must not derive its expected value by
calling production serialization or manifest helpers.

Write `mcp_server/tests/test_package_prime_acp_runtime.py` against the public
CLI before creating it. The complete synthetic ZIP contains the expected Prime
artifact shape, including `pi.exe`, `package.json`, `README.md`, `CHANGELOG.md`,
`skills/goal/SKILL.md`, assets, docs, examples, and
`dist/prime-agent-runtime`. The cases prove:

```text
the supplied ZIP SHA-256 must match before extraction
rooted, traversal, empty, noncanonical, link, and case-colliding ZIP entries refuse
extraction is whole-archive and never overlays an existing path
runtime-manifest.json, skills/rook-full, tools/uv, and notices/prime-agent must be absent
every Rook-owned addition is create-only
Prime ZIP bytes remain unchanged when a reserved collision refuses
rook-full is copied as one complete tracked subtree
the packager rechecks each frozen uv archive/license hash over bounded regular-file bytes
each wrong hash refuses before output creation; assembly consumes retained verified bytes
the uv ZIP receives the same traversal/link/collision checks and only uv.exe is selected
every installed uv and license byte is bound by the generated closed file rows
Prime's tracked notice requires 1,105 bytes and SHA-256 B288615FB31DC504623582FB790A28E6D86BC2F5C1396845AF555E43386DA5A0
the packager performs no network access
failure publishes no runtime directory
success creates and verifies exactly runtimes/<runtime-id>
an invalid existing destination is never overlaid or repaired
an existing identical verified destination may be reused
```

The CLI is fixed as:

```python
# scripts/package-prime-acp-runtime.py
def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError
```

The required CLI options are exactly `--prime-zip`,
`--expected-prime-zip-sha256`, `--rook-skill`, `--uv-zip`,
`--uv-license-apache`, `--uv-license-mit`, `--prime-license`, and
`--output-runtimes-root`; none has a default. Step 2 invokes that CLI only with
synthetic local inputs. The one real release invocation is frozen separately in
Step 8 after the ZIP hash review.

The packager uses a fresh same-volume sibling for extraction and assembly,
calls `create_runtime_manifest()`, immediately calls
`verify_runtime_payload()`, and only then renames create-only to
`runtimes/<runtime-id>`. It consumes already downloaded inputs and has no URL,
HTTP, retry, or test-mode option. Step 8 acquires and checks frozen `uv` inputs;
the offline packager independently repeats all three frozen hash checks, regular-
file checks, and byte ceilings before retaining and consuming those exact bytes.
Synthetic positive tests may substitute expected hashes only in the imported
test-local module context; no production CLI override is added. A production-pin
test must reject those synthetic inputs. This keeps tests offline without
claiming official provenance for unchecked inputs.

Copy Prime's exact root `LICENSE` from upstream baseline
`c718bf3c30fd8da206ed551837cbb54f7ad15948` to
`third_party/prime-agent/LICENSE`. Assert that the same bytes remain present at
the approved compatibility commit, then enforce the frozen 1,105-byte length
and SHA-256 in the packager tests.

Run RED before implementation and GREEN afterward:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_prime_runtime_artifact.py tests/test_package_prime_acp_runtime.py -q
```

- [ ] **Step 3: Route installer and local deployment through one promotion function**

Extend `test_prime_runtime_artifact.py` with causal promotion tests before
implementation:

```text
incoming runtime verifies before any final-directory or pointer write
incoming and final staging must be on the same volume
publication is a create-only directory move to runtimes/<runtime-id>
an identical existing destination is verified and reused without overlay
an invalid existing destination leaves both trees unchanged
current.json is exactly {"runtimeId":"<64 uppercase hex>"}\n
pointer publication uses a same-directory temporary and atomic replacement
invalid, missing, changing, or extra-key pointer data refuses without directory scan fallback
historical runtime siblings remain untouched
```

`promote_incoming_runtime()` is the only function allowed to create the final
runtime-ID directory or replace `current.json`. It requires a direct incoming
payload root beneath `prime/.incoming/`, verifies it, confirms it shares the
final runtime parent's volume, publishes it by directory move, verifies the
published destination again, then selects it. It never executes incoming code.

Add `mcp_server/tests/test_post_install_prime_runtime.py` and extend the two
existing PowerShell guard suites before changing consumers. The tests prove:

```text
installer post-install passes its exact incoming root and <install-dir>/prime to the public promotion entrypoint
the two build-release skill copies and their source-path references remain byte-identical
the release workflow admits exactly one verified assembly-attempt-scoped Prime payload before ISCC
the release workflow uses only artifacts/python-wheelhouse/verify-rook-venv/Scripts/python.exe with -I from the exact repo-root cwd
the verifier module imports from that exact venv's Lib/site-packages installation produced by the sealed wheelhouse, never mcp_server/src or an editable source installation
the release workflow invokes the exact prime_runtime_artifact verify argv before ISCC
PATH Python, the worktree .venv, PYTHONPATH, and source-tree import fallback cannot satisfy the release gate
the ISCC argv contains exactly /DPrimeRuntimePayload=<canonical admitted payload>
local deployment admits that same exact payload path and copies it into one unique <install-dir>/prime/.incoming generation
local deployment passes that exact generation to the same post-install/promotion path
neither Inno nor PowerShell writes prime/runtimes/<runtime-id> or prime/current.json
installer [Files] writes Prime bytes only beneath its unique incoming directory
InstallDelete and upgrade/repair cleanup exclude prime/runtimes/** and data/rookchat/acp/v1/**
neither release nor deployment can bypass the shared Rook-owned promotion entrypoint
```

Add one optional `--prime-incoming-dir` argument to `installer/post_install.py`.
When present, invoke the installed Rook package's public promotion entrypoint
through the newly established managed Python after the Rook venv is installed
and before the chat-service manifest is published:

```python
result = subprocess.run(
    [
        str(managed_python),
        "-I",
        "-m",
        "rook.agent.chat.prime_runtime_artifact",
        "promote",
        "--incoming-root",
        str(Path(args.prime_incoming_dir)),
        "--prime-root",
        str(install_dir / "prime"),
    ],
    shell=False,
    check=False,
)
if result.returncode != 0:
    return 1
```

The incoming Prime payload supplies no verification code. The invoked module
is the Rook-owned implementation already installed into the managed venv from
the signed/current Rook payload. Tests assert the exact executable and argument
array and require refusal before chat-service publication on nonzero exit.

`installer/RookSetup.iss` requires the release builder to define one exact
`PrimeRuntimePayload` directory. Its ordinary file table copies only that
payload's contents beneath one setup-owned incoming directory; the cached
`GetPrimeIncomingDir` scripted constant is created once under
`{app}\prime\.incoming` and passed to `post_install.py` as
`--prime-incoming-dir`. No file-table or Pascal path targets `runtimes` or
`current.json`.

Update both `.agents/skills/build-release/SKILL.md` and
`.claude/skills/build-release/SKILL.md` in lockstep. The release invocation
supplies one exact assembly-attempt-scoped `PrimeRuntimePayload`; before source-path
validation or ISCC, the workflow requires its `runtimes` parent to contain
exactly that one 64-uppercase-hex runtime directory. The existing wheelhouse
release step must already have produced and validated:

```text
artifacts/python-wheelhouse/verify-rook-venv/Scripts/python.exe
artifacts/python-wheelhouse/verification-rook.json
installer/runtime/python-runtime-manifest.json
```

The Python runtime manifest must name the exact release version and final Rook
implementation commit. `verification-rook.json` must prove that `rook` was
installed from the sealed wheelhouse and imported from that verification venv's
`Lib/site-packages`; its existing install and `pip check` results must be
successful. From the exact Rook repository root, with `PYTHONPATH` absent, the
release skill first uses that exact interpreter under `-I` to verify that
`rook.agent.chat.prime_runtime_artifact.__file__` resolves beneath the same
verification venv's `Lib/site-packages`. Reject resolution from `mcp_server/src`
or an editable source installation, not from the enclosing worktree directory:
the required verification venv itself resides beneath that worktree.
It then invokes exactly:

```powershell
& 'artifacts/python-wheelhouse/verify-rook-venv/Scripts/python.exe' -I `
    -m rook.agent.chat.prime_runtime_artifact verify `
    --runtime-root $PrimeRuntimePayload `
    --expected-runtime-id (Split-Path -Leaf $PrimeRuntimePayload)
```

Only after that command exits zero may the skill call ISCC with exactly
`/DPrimeRuntimePayload=<canonical verified directory>`. No `python` from
`PATH`, worktree `.venv`, `PYTHONPATH`, source fallback, or verifier from the
incoming Prime payload is admitted. The two synchronized
`references/iss-source-paths.md` files add the runtime payload,
`runtime-manifest.json`, `pi.exe`, `tools/uv/uv.exe`, `skills/rook-full`,
`dist/prime-agent-runtime`, and `notices/prime-agent` to the required source
boundary. Neither skill may discover or select a payload from installed runtime
siblings.

`scripts/deploy-local-testing.ps1` accepts the exact same
`-PrimeRuntimePayload` directory for a release-mode full deployment. Its
assembly-attempt-scoped `runtimes` parent must contain exactly that one verified runtime
directory. The script copies it create-only to one GUID-named
`$InstallRoot\prime\.incoming` directory and passes that direct incoming root
to `Invoke-PostInstallConfig`. It never selects from installed runtime siblings.
The release workflow and local deployment both verify the supplied payload;
only the shared installed `post_install.py` path invokes the Rook-owned
`promote` entrypoint that can publish `prime/runtimes/<runtime-id>` and
`prime/current.json`.

Run the focused promotion and consumer tests:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_prime_runtime_artifact.py tests/test_post_install_prime_runtime.py -q

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
pwsh -NoProfile -File scripts/tests/deploy-local-testing-guards.tests.ps1
pwsh -NoProfile -File scripts/tests/release-installer-guards.tests.ps1 -SkipBuiltPayloadCheck
```

Task 10 uses the release guard's source-only mode because this task does not
build Rook's native or managed Release outputs. This gate verifies installer
source wiring, the exact Prime payload argument, shared promotion ownership, and
retention behavior. The full guard without `-SkipBuiltPayloadCheck` remains
mandatory in the actual build-release workflow after the native and managed
Release builds have produced their payloads.

- [ ] **Step 4: Make the product runtime consume the new manifest and bundled uv**

Update `test_chat_prime_runtime.py`, `test_chat_integration.py`, and the affected
contract fixtures in `test_chat_acp_conversation.py` first. One complete valid
fixture must use the exact Section 12.5 schema and then mutate one boundary per
test.

The RED cases prove:

```text
load_and_verify_runtime delegates closed payload verification before returning paths
pi.exe, goal skill, rook-full, uv.exe, both uv licenses, Prime runtime subtree, and Prime notice are required
rookMcpCommand, rookMcpArgs, and rookMcpEnvironment are rejected manifest keys
the retained verified SKILL.md bytes are size-checked, strictly decoded once, and passed as prompt text
the complete rendered Windows argv remains bounded before spawn
build_rook_mcp_server uses the exact current sys.executable and fixed -m rook arguments
current.json is read once and no latest-directory fallback exists
the selected runtime ID is recorded before launch argv is constructed
```

Change `PrimeRuntimeContract` to the already frozen interface-ledger shape. Move
canonical manifest/file-set verification into `prime_runtime_artifact.py`; keep
launch-specific validation and `PrimeRuntimeContract` construction in
`prime_runtime.py`. `service_main.InstalledRuntimeCatalog` calls the shared
`read_current_runtime_id()` and `load_and_verify_runtime()` only.

`build_prime_child_env()` validates the complete input before transforming it.
It removes these names case-insensitively:

```text
PI_PACKAGE_DIR
PRIME_AGENT_KERNEL_PYTHON
PRIME_AGENT_KERNEL_VENV
PRIME_AGENT_INSTALL_UV
VIRTUAL_ENV
PYTHONHOME
PYTHONPATH
PYTHONDONTWRITEBYTECODE
PYTHONPYCACHEPREFIX
```

It removes every inherited key beginning with `UV_`, then inserts only:

```text
UV_CACHE_DIR=<ROOK_DATA_DIR>/rookchat/acp/v1/prime-uv/cache
UV_PYTHON_INSTALL_DIR=<ROOK_DATA_DIR>/rookchat/acp/v1/prime-uv/python
UV_PYTHON_PREFERENCE=only-managed
UV_PYTHON_NO_REGISTRY=1
UV_PYTHON_INSTALL_REGISTRY=0
UV_NO_CONFIG=1
```

The manifest-verified `tools/uv` directory is first on child `PATH`. Seed exact,
lowercase, and mixed-case variants of every forbidden key plus representative
future `UV_*` keys in tests. Assert the final map immediately before the fake
process factory consumes it. No test launches Prime or an ambient executable.

After scrubbing inherited bytecode-policy keys, insert
`PYTHONDONTWRITEBYTECODE=1`. Test an ordinary goal-style editable import with
the exact worktree Python in a disposable fixture and the projected environment,
then reverify the unchanged closed payload. A control import without this policy
must create bytecode that the verifier still rejects. Do not launch a kernel,
modify Prime, or ignore generated executable files in the manifest verifier.

Run the focused product-consumer gate:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_chat_prime_runtime.py tests/test_chat_integration.py tests/test_chat_acp_conversation.py -q
```

- [ ] **Step 5: Add the installed verifier and complete retention proofs**

Write `test_verify_installed_rookchat_acp.py` before the verifier. Invoke the
real CLI `main()` over a complete synthetic source/install fixture; do not test
an extracted private helper. Fix this public interface:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
$python = 'C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server/.venv/Scripts/python.exe'
& $python -I scripts/verify-installed-rookchat-acp.py `
    --rook-worktree C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset `
    --expected-rook-commit $ApprovedImplementationCommit `
    --install-root "$env:LOCALAPPDATA/Rook/app" `
    --chat-service-manifest "$env:APPDATA/McNeel/Rhinoceros/8.0/Plug-ins/RookNative/net8.0/RookChatService.json" `
    --output C:/RookEvidence/rookchat-prime-acp-installed/identity.json
```

The test fixture proves the public CLI refuses a dirty or wrong source commit,
invalid chat-service interpreter/import roots, invalid `current.json`, and any
missing, changed, extra, relocated, linked, or substituted runtime authority
file. It proves `pi.exe`, `rook-full`, `uv`, Prime's Python runtime subtree, and
Prime's notice all resolve beneath the recorded runtime. No success report may
exist after refusal. A success report is bounded, create-only diagnostic JSON
containing the source commit, pointer snapshot, runtime ID, manifest SHA-256,
and verified absolute consumer paths; it is not product authority.

Extend installer and deployment fixtures to simulate install, upgrade, repair,
release rollback, and data-retaining uninstall. Require:

```text
upgrade and repair preserve all existing prime/runtimes siblings
rollback does not rewrite or remove newer runtime siblings
current.json changes only through successful promotion
%LOCALAPPDATA%/Rook/data/rookchat/acp/v1 survives every fixture
normal uninstall may remove {app} and Prime runtimes but not ACP data
incoming or failed staging generations are never selected
```

Run:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_verify_installed_rookchat_acp.py tests/test_post_install_prime_runtime.py -q

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
pwsh -NoProfile -File scripts/tests/deploy-local-testing-guards.tests.ps1
pwsh -NoProfile -File scripts/tests/release-installer-guards.tests.ps1 -SkipBuiltPayloadCheck
```

- [ ] **Step 6: Run the complete model-free Task 10 gate, commit, and stop**

Run every public seam together. This gate may execute fixture Bash/Python and
PowerShell only. It does not build Prime, download dependencies, package the
real runtime, install Rook, or launch Prime/Rhino/Grasshopper/models.

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
wsl.exe -d Ubuntu-24.04 --exec /bin/bash -lc 'cd /mnt/c/UDEV/Rook/.worktrees/rookchat-prime-acp-reset && bash scripts/tests/prime-wsl-build.tests.sh'

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_prime_runtime_artifact.py tests/test_package_prime_acp_runtime.py tests/test_post_install_prime_runtime.py tests/test_chat_prime_runtime.py tests/test_chat_integration.py tests/test_chat_acp_conversation.py tests/test_verify_installed_rookchat_acp.py -q
./.venv/Scripts/python.exe -m compileall -q src/rook ../scripts/package-prime-acp-runtime.py ../scripts/verify-installed-rookchat-acp.py ../installer/post_install.py

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
pwsh -NoProfile -File scripts/tests/deploy-local-testing-guards.tests.ps1
pwsh -NoProfile -File scripts/tests/release-installer-guards.tests.ps1 -SkipBuiltPayloadCheck
git diff --check
git status --short
```

The status must contain no abandoned RED scripts and no generated runtime. Stage
only the explicit Task 10 source/test files and commit once:

```powershell
git add scripts/build-prime-acp-runtime.sh scripts/tests/prime-wsl-build.tests.sh mcp_server/src/rook/agent/chat/prime_runtime_artifact.py mcp_server/src/rook/agent/chat/prime_runtime.py mcp_server/src/rook/agent/chat/service_main.py mcp_server/src/rook/agent/chat/acp_conversation.py mcp_server/tests/test_prime_runtime_artifact.py mcp_server/tests/test_package_prime_acp_runtime.py mcp_server/tests/test_chat_prime_runtime.py mcp_server/tests/test_chat_integration.py mcp_server/tests/test_chat_acp_conversation.py mcp_server/tests/test_post_install_prime_runtime.py scripts/package-prime-acp-runtime.py third_party/prime-agent/LICENSE installer/post_install.py scripts/deploy-local-testing.ps1 scripts/tests/deploy-local-testing-guards.tests.ps1 installer/RookSetup.iss scripts/tests/release-installer-guards.tests.ps1 .agents/skills/build-release/SKILL.md .claude/skills/build-release/SKILL.md .agents/skills/build-release/references/iss-source-paths.md .claude/skills/build-release/references/iss-source-paths.md scripts/verify-installed-rookchat-acp.py mcp_server/tests/test_verify_installed_rookchat_acp.py
git commit -m "build: add Prime ACP runtime packaging"
```

STOP for independent review. Report the exact test outputs, commit and parent,
Prime's unchanged clean identity, and absence of generated release payloads.
That review must name the exact Task 10 implementation commit and issue the
Step 7 command with that literal identity before execution. Do not alter WSL
prerequisites or run the real builder before approval.

- [ ] **Step 7: Close Prime product policy, freeze the patch series, then run one approved v4 build**

This step has two hard gates. The source-policy and patch-series work completes
and stops for independent review before any build-attempt-v4 path is created.
Only the subsequent review command may authorize the real build.

**7A. Write focused RED tests before production changes**

Work from a new clean Prime implementation worktree rooted at
`c718bf3c30fd8da206ed551837cbb54f7ad15948`; retain the clean
`prime-acp-no-daemon` worktree at `1b9dfabb04901de4823d259c88b39dfc78ec3b34`
as reviewed precursor evidence. Use branch `codex/rookchat-prime-final-series`.
Do not copy ignored output or `node_modules` between worktrees.

The following concern-by-concern table is the closed Prime scope. Concerns 1-4
reproduce every file in the reviewed `c718bf3c...1b9dfabb` delta; concern 5 is
the new project-resource selector. If implementation requires a file outside
this table, stop for review instead of violating the scope or silently leaving
the consumer path incomplete.

| Concern | Production files | Focused test files | Documentation / release files |
| --- | --- | --- | --- |
| 1. Daemon-free ACP | `packages/coding-agent/src/cli/args.ts`<br>`packages/coding-agent/src/cli/command-registry.ts`<br>`packages/coding-agent/src/cli/daemon-launch.ts`<br>`packages/coding-agent/src/cli/no-daemon-args.ts`<br>`packages/coding-agent/src/main.ts` | `packages/coding-agent/test/acp-no-daemon-cli.test.ts`<br>`packages/coding-agent/test/args.test.ts`<br>`packages/coding-agent/test/daemon-launch.test.ts`<br>`packages/coding-agent/test/main-interactive-routing.test.ts`<br>`packages/coding-agent/test/no-daemon-argv-consistency.test.ts` | `packages/coding-agent/docs/acp.md`<br>`packages/coding-agent/.changes/acp-no-daemon.md`<br>Changelog: none |
| 2. Platform-aware kernel interpreter | `packages/coding-agent/src/core/kernel/bootstrap.ts` | `packages/coding-agent/test/kernel-bootstrap.test.ts` | Documentation/release: none |
| 3. Complete standalone Python runtime | `scripts/build-binaries.sh` | `packages/coding-agent/test/builtin-skills.test.ts` | Documentation/release: none |
| 4. Frozen model catalog | `packages/ai/scripts/generate-models.ts`<br>`packages/ai/scripts/model-catalog-build-mode.ts`<br>`scripts/build-binaries.sh` | `packages/ai/test/model-catalog-build-mode.test.ts`<br>`packages/coding-agent/test/build-binaries-frozen-catalog.test.ts` | Documentation: none<br>`packages/coding-agent/CHANGELOG.md` |
| 5. Project-resource denial | `packages/coding-agent/src/cli/args.ts`<br>`packages/coding-agent/src/cli/command-registry.ts`<br>`packages/coding-agent/src/main.ts`<br>`packages/coding-agent/src/migrations.ts`<br>`packages/coding-agent/src/core/agent-session-config.ts`<br>`packages/coding-agent/src/core/agent-session-services.ts`<br>`packages/coding-agent/src/core/settings-manager.ts`<br>`packages/coding-agent/src/core/package-manager.ts`<br>`packages/coding-agent/src/core/resource-loader.ts` | `packages/coding-agent/test/args.test.ts`<br>`packages/coding-agent/test/migrations.test.ts`<br>`packages/coding-agent/test/agent-session-config.test.ts`<br>`packages/coding-agent/test/agent-session-services.test.ts`<br>`packages/coding-agent/test/settings-manager.test.ts`<br>`packages/coding-agent/test/package-manager.test.ts`<br>`packages/coding-agent/test/resource-loader.test.ts`<br>`packages/coding-agent/test/no-approve-startup-composition.test.ts` | `packages/coding-agent/docs/acp.md`<br>`packages/coding-agent/.changes/acp-no-approve.md`<br>Changelog: none |

The optional `5c2750bd...` bounded-kernel-stderr backport is not part of those
five concern scopes. If independently adopted, its exact separate scope is:

| Scope | Production files | Focused test files | Release file |
| --- | --- | --- | --- |
| Upstream `5c2750bd...` backport | `packages/coding-agent/src/core/kernel/repl-manager.ts`<br>`packages/coding-agent/src/core/kernel/shared.ts`<br>`packages/coding-agent/src/core/tools/ipython.ts` | `packages/coding-agent/test/repl-kernel-shutdown.test.ts`<br>`packages/coding-agent/test/repl-kernel-startup.test.ts` | `packages/coding-agent/.changes/kernel-stderr-log.md` |

Use the concern-5 tests named above. The startup-composition test drives the
launch-cwd and resumed-cwd flow together through the same startup owner used by
`main()`. `model-registry.test.ts` and `prime-inference-auth.test.ts` remain
unchanged control gates proving that project-resource denial does not alter
model discovery or Prime authentication; they are not modified merely to make
the scope appear larger.

The `--no-approve` RED contract is:

```text
exact flag before -- parses true; the same token after -- remains prompt content
--no-approve=<value> and malformed attempted forms refuse before migrations
one immutable Boolean exists before runMigrations() and the first SettingsManager.create()
global migrations, global settings, and Prime authentication remain available
project commands-to-prompts migration is skipped without automatic reading or mutating the project tree
startup settings do not automatically read <launch-cwd>/.prime/agent/settings.json
resumed settings do not automatically read <session-cwd>/.prime/agent/settings.json
project packages, extensions, skills, prompts, themes, SYSTEM.md, APPEND_SYSTEM.md, AGENTS.md, and CLAUDE.md are not automatically discovered or loaded before model work
the user-global <agentDir>/SYSTEM.md remains eligible as Prime's base prompt; the explicit verified Rook body is appended separately
explicit --skill goal and --skill rook paths remain loaded
omitting --no-approve preserves current project behavior
after model work begins, admitted IPython and Rook tools may intentionally access project files; this selector is not a filesystem sandbox
```

Both cwd fixtures are hostile and instrument filesystem reads, directory walks,
renames, and writes by the automatic startup/resume resource pipeline. A test
fails on the first such access; absence is not inferred from an empty result.
Implement one immutable `allowProjectResources` decision and pass it into
`runMigrations`, every startup and resumed `SettingsManager.create`,
`AgentSessionRuntimeConfig`, `createAgentSessionServices`,
`DefaultPackageManager`, and `DefaultResourceLoader`. Global paths and explicit
CLI paths remain admitted.
Do not add trust persistence, approval prompts, permission state, Rook-side
directory scanning, special ACP behavior, or a claim that later tool-driven
filesystem access is denied.

The managed-helper RED contract is non-reachability, not a new selector:

```text
the actual direct main(["--mode", "acp", "--no-daemon", ...]) composition reaches runAcpMode(runtime)
the same composition never calls ensureTool() or ensureToolWithStatus()
with fd and rg absent, an acquisition-boundary spy that throws remains untouched through ACP initialization/session composition
the only production acquisition callers remain postinstall, interactive mode, and agents-view mode
no environment alias, module-global policy, facade, or helper-download selector is added
```

Drive this through the actual ACP startup/composition owner with the runtime and
transport mocked model-free; do not settle for a helper-unit test. Retain one
small static call-site inventory guard so a future ACP caller forces review.
Slice B separately checks that managed-helper artifacts were not created and
records allowlisted host/port destinations observed by its configured CONNECT
proxy. That ledger cannot identify encrypted URL paths or prove extractor
non-invocation or exhaustive network containment; it cannot substitute for the
source-composition test.

In Rook, extend `test_chat_prime_runtime.py` before changing
`prime_runtime.py`. Prove new and reopen argv contain exact `--no-approve`, do
not contain `--offline`, and the final child
environment removes every exact/lowercase/mixed-case `PI_OFFLINE` key. Preserve
every uv, bytecode, skill-content, and command-line bound. Slice B adds
`--offline` only in its isolated external protocol.

After the Prime series head exists, update only the new-assembly Prime identity
pin in `prime_runtime_artifact.py`, `package-prime-acp-runtime.py`, and their
existing tests. Historical runtime verification remains manifest-driven and
must not require the newest head. The resulting Rook commit is the identity the
independent build authorization supplies; do not edit it during the build.

**7B. Implement minimally, organize one concern per commit, and stop**

Make the tests green without changing Prime's default behavior. Recreate the
already reviewed precursor behavior and the one new selector as this exact
ordered concern series over the baseline:

```text
1 daemon-free ACP selection
2 platform-aware kernel interpreter
3 complete standalone Python-runtime payload
4 frozen model catalog build
5 project-resource denial
```

Each commit contains only the exact production, focused-test, and
documentation/release files assigned to it in the closed table above. The final
tree for concerns 1-4 must match the reviewed precursor behavior. Concern 5
remains independently removable. Do not create an in-product patch registry or
retain omnibus and series builds as competing release identities.

Before freezing the head, produce this concise upstream matrix:

```text
5c2750bdc3c99cc4225c1167a3484371a7a221ab | bounded kernel stderr | adopt or defer | conflict | focused test
7f21fa3435cd1c63724b6e427edb3a60a309c266 | native ACP MCP tools | defer | model-visible contract/cpython | future product decision
```

The `5c2750bd` row requires an explicit independent adopt-or-defer ruling. If
adopted, retain its upstream source identity and apply it as one separately
attributable backport immediately after concern 2 in the reviewed ancestry; if deferred, record the reason
and required later qualification. Do not merge or rebase current Prime main.
The `7f21fa3` deferral is fixed for this task.

Run the focused Prime tests with
`packages/coding-agent/vitest.config.ts`, the hostile cwd/resume cases, the
existing 45-test Step 1 gate, and `npm run check` with
`C:/Program Files/Git/usr/bin` prepended to `PATH`. Run the focused Rook runtime
tests. Verify every series commit and parent, final-tree scope, baseline
ancestry, `git show --check`, and clean Prime/Rook worktrees.

STOP for independent review. Report the ordered commit list, exact final Prime
head, exact Rook head, test outputs, the `5c2750bd` ruling, and confirmation that
no project fixture was touched and the ACP composition invoked no helper
acquisition/fetch/extractor boundary. Do not create
`build-attempt-v4`, transfer an artifact, or launch Prime.

**7C. Only after a fresh independent execution review, run one real build-attempt-v4**

`build-attempt-v3` is permanently failed and inadmissible. Its bounded retained
record is:

```text
outcome=failed
timestamp_utc=2026-09-05T14:35:55Z (attempt-root creation; failure followed immediately)
rook=42819aaf23a3251c3eb176f021d5eb4141d681a7
prime=b71badc503f650cd7c10c4acd1206a8406aa0a0b
parent=74b75df146090ec924fd3e185d522911738f14b7
command=git -C D:/prime-agent/.worktrees/rookchat-prime-final-series bundle create C:/UDEV/RookRelease/prime-acp/b71badc5/builds/build-attempt-v3/source/prime-b71badc5.bundle b71badc503f650cd7c10c4acd1206a8406aa0a0b
exit_code=1
stderr=fatal: Refusing to create empty bundle.
windows_attempt=C:/UDEV/RookRelease/prime-acp/b71badc5/builds/build-attempt-v3
windows_contents=empty source directory only
bundle=absent
wsl_attempt=absent
```

The v3 directory remains unchanged. This adjacent plan record does not grant it
authority, populate its `source/` directory, or permit reuse, repair, or resume.

The local command selects WSL2; the portable Bash entrypoint remains unaware of
WSL. Before creating a Windows release directory, Git bundle, WSL checkout,
build support root, or staging directory, complete every source/tool prerequisite
check. Version probes use a fresh prerequisite-only HOME/TMPDIR outside the build
attempt; npm may write its normal compile cache there. These probe directories
are diagnostics, not build inputs, and are never reused by the builder.
The independently approved v4 execution review must issue the Step 7C command with
the exact 40-hex Rook implementation commit, final Prime head, direct parent,
complete ordered Prime series, and full Prime bundle ref
`refs/heads/codex/rookchat-prime-final-series` assigned as literal local
PowerShell values.
They are never read from environment variables, inferred from `HEAD`, or
supplied by the build script. Verify the clean Rook implementation
and exact public build entrypoint first, then verify the clean Prime identity on
Windows and the distribution, version, Linux-native filesystem, and complete
required tool set in WSL. If either source identity differs, the Rook entrypoint
is absent, linked, or outside the checkout, Ubuntu is not 24.04, WSL is not
version 2, Node is below 22.8.0, Bun is not 1.3.14, or any required tool resolves
through `/mnt/*` or a Windows-hosted filesystem, stop before creating an
attempt. The product scripts never auto-install tools.

Use `--exec /bin/bash -lc` for every local WSL invocation. The alternative
`-- bash -lc` lost literal shell variables on this machine. Keep Bash text in
PowerShell single-quoted strings or single-quoted here-strings. Before any
mutating setup or release command, require this harmless transport probe:

```powershell
$wslTransportProbe = @'
set -euo pipefail
value='literal $HOME stays literal'
set -- 'argument with spaces' '' '$PATH'
test "$value" = 'literal $HOME stays literal'
test "$#" -eq 3
test "$1" = 'argument with spaces'
test -z "$2"
test "$3" = '$PATH'
printf 'TRANSPORT_PROBE=PASS\n'
'@
wsl.exe -d Ubuntu-24.04 --exec /bin/bash -lc $wslTransportProbe
if ($LASTEXITCODE -ne 0) { throw 'Literal WSL transport failed; stop before mutation.' }
```

The prepared local build-only tools are Node 22.23.2 with its supplied npm
10.9.8 and Bun 1.3.14 beneath `/home/bring/.local/share/rook-prime-build`, plus
Ubuntu zip/unzip in `/usr/bin`. The preflight and build commands below select
that same explicit Linux PATH; neither uses the interactive shell's PATH.
System Node 20 and Windows tools remain unchanged. These are release-machine
prerequisites only, not customer installation requirements. A differently
prepared release machine must explicitly select and preflight its own Linux
paths, preserving the portable builder's existing version contract.

```powershell
$rookRoot = (Resolve-Path -LiteralPath 'C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset').Path
$primeRoot = (Resolve-Path -LiteralPath 'D:/prime-agent/.worktrees/rookchat-prime-final-series').Path
# The independently reviewed Step 7C command assigns these literal values before
# execution; this body is not executable authority by itself.
if (-not (Test-Path Variable:approvedRookCommit) -or
    $approvedRookCommit -cnotmatch '^[0-9a-f]{40}$') {
    throw 'The reviewed Step 7 command must name the approved Rook commit literally.'
}
if (-not (Test-Path Variable:approvedPrimeHead) -or
    $approvedPrimeHead -cnotmatch '^[0-9a-f]{40}$' -or
    -not (Test-Path Variable:approvedPrimeParent) -or
    $approvedPrimeParent -cnotmatch '^[0-9a-f]{40}$' -or
    -not (Test-Path Variable:approvedPrimeSeries) -or
    @($approvedPrimeSeries).Count -lt 5 -or
    @($approvedPrimeSeries | Where-Object { $_ -cnotmatch '^[0-9a-f]{40}$' }).Count -ne 0 -or
    $approvedPrimeSeries[-1] -cne $approvedPrimeHead) {
    throw 'The reviewed Step 7 command must name the approved Prime series literally.'
}
if (-not (Test-Path Variable:approvedPrimeBundleRef) -or
    $approvedPrimeBundleRef -cne 'refs/heads/codex/rookchat-prime-final-series') {
    throw 'The reviewed Step 7 command must name the approved Prime bundle ref literally.'
}
$rookStatus = @(git -C $rookRoot status --short)
if ($LASTEXITCODE -ne 0 -or $rookStatus.Count -ne 0) { throw 'Rook worktree is not clean.' }
if ((git -C $rookRoot rev-parse HEAD) -cne $approvedRookCommit) { throw 'Rook HEAD differs.' }
$buildEntrypoint = Get-Item -LiteralPath "$rookRoot/scripts/build-prime-acp-runtime.sh" -Force
if ($buildEntrypoint.PSIsContainer -or
    ($buildEntrypoint.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
    -not $buildEntrypoint.FullName.StartsWith("$rookRoot\", [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Rook build entrypoint is not a regular file beneath the approved checkout.'
}

$primeStatus = @(git -C $primeRoot status --short)
if ($LASTEXITCODE -ne 0 -or $primeStatus.Count -ne 0) { throw 'Prime worktree is not clean.' }
if ((git -C $primeRoot rev-parse HEAD) -cne $approvedPrimeHead) { throw 'Prime HEAD differs.' }
if ((git -C $primeRoot rev-parse HEAD^) -cne $approvedPrimeParent) { throw 'Prime parent differs.' }
git -C $primeRoot show-ref --verify --quiet $approvedPrimeBundleRef
if ($LASTEXITCODE -ne 0) { throw 'Approved Prime bundle ref is absent.' }
$resolvedPrimeBundleHead = git -C $primeRoot rev-parse ($approvedPrimeBundleRef + '^{commit}')
if ($LASTEXITCODE -ne 0 -or $resolvedPrimeBundleHead -cne $approvedPrimeHead) {
    throw 'Approved Prime bundle ref does not resolve to the approved head.'
}
$baseline = 'c718bf3c30fd8da206ed551837cbb54f7ad15948'
$actualPrimeSeries = @(git -C $primeRoot rev-list --reverse --first-parent "$baseline..$approvedPrimeHead")
if ($LASTEXITCODE -ne 0 -or
    ($actualPrimeSeries -join "`n") -cne ($approvedPrimeSeries -join "`n")) {
    throw 'Prime compatibility series differs from independent approval.'
}

wsl.exe --list --verbose
if ($LASTEXITCODE -ne 0) { throw 'WSL distribution query failed.' }
$wslPreflight = @'
set -euo pipefail
tools=/home/bring/.local/share/rook-prime-build
build_path="$tools/node-v22.23.2-linux-x64/bin:$tools/bun-v1.3.14:/usr/bin"
probe_root=$(/usr/bin/mktemp -d "$tools/preflight.XXXXXXXX")
/usr/bin/mkdir "$probe_root/home" "$probe_root/tmp"
cd "$probe_root"
exec /usr/bin/env -i HOME="$probe_root/home" PATH="$build_path" LANG=C.UTF-8 LC_ALL=C.UTF-8 TMPDIR="$probe_root/tmp" CI=1 /bin/bash --noprofile --norc -s <<'PREFLIGHT'
set -euo pipefail
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
test "$(uname -s)" = Linux
case "$(uname -r)" in *microsoft-standard-WSL2*) ;; *) exit 1 ;; esac
for root in "$HOME" "$TMPDIR"; do
  test -d "$root"
  test -z "$(ls -A "$root")"
  case "$(findmnt -n -o FSTYPE -T "$root")" in ''|drvfs|9p|ntfs|ntfs3|fuseblk) exit 1 ;; esac
done
for tool in bash sh node npm bun git zip unzip dirname rm mkdir cp ls env timeout sha256sum uname findmnt readlink head; do
  p="$(type -P "$tool")"
  c="$(readlink -f "$p")"
  test -f "$p"; test -x "$p"
  test -f "$c"; test -x "$c"
  case "$p:$c" in /mnt/*:*|*:/mnt/*) exit 1 ;; esac
  for resolved in "$p" "$c"; do
    case "$(findmnt -n -o FSTYPE -T "$resolved")" in ''|drvfs|9p|ntfs|ntfs3|fuseblk) exit 1 ;; esac
  done
  printf 'TOOL %s=%s -> %s\n' "$tool" "$p" "$c"
done
node_version="$(node --version)"
[[ "$node_version" =~ ^v([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]
(( BASH_REMATCH[1] > 22 || (BASH_REMATCH[1] == 22 && BASH_REMATCH[2] >= 8) ))
test "$(bun --version)" = 1.3.14
printf 'NODE=%s\nNPM=%s\nBUN=%s\nGIT=%s\n' "$node_version" "$(npm --version)" "$(bun --version)" "$(git --version)"
zip_version="$(zip -v)"; printf '%s\n' "$zip_version" | head -n 2
unzip_version="$(unzip -v)"; printf '%s\n' "$unzip_version" | head -n 2
printf 'EFFECTIVE_ENVIRONMENT\n'; env
printf 'UBUNTU_BUILD_PREREQUISITES=PASS\n'
PREFLIGHT
'@
wsl.exe -d Ubuntu-24.04 --exec /bin/bash -lc $wslPreflight
if ($LASTEXITCODE -ne 0) { throw 'Ubuntu build prerequisites are not admitted.' }
$buildAttempt = 'build-attempt-v4'
$primeShort = $approvedPrimeHead.Substring(0, 8)
$releaseRoot = "C:/UDEV/RookRelease/prime-acp/$primeShort/builds/$buildAttempt"
if (Test-Path -LiteralPath $releaseRoot) { throw 'Windows build attempt root must be absent.' }
$wslAttemptAbsence = 'test ! -e "$HOME/rook-prime-acp-{primeShort}/builds/{buildAttempt}"'.Replace('{primeShort}', $primeShort).Replace('{buildAttempt}', $buildAttempt)
wsl.exe -d Ubuntu-24.04 --exec /bin/bash -lc $wslAttemptAbsence
if ($LASTEXITCODE -ne 0) { throw 'WSL build attempt root must be absent.' }
```

Only after that preflight succeeds, create one explicit build-attempt
generation. `build-attempt-v1`, `build-attempt-v2`, and `build-attempt-v3`
remain permanently preserved as inadmissible evidence under their original
Prime identities. They are never modified, normalized, repaired, transferred,
adopted, or used as inputs. The next authorized generation is exactly
`build-attempt-v4` under the independently approved final Prime head. A failed
generation is never repaired, resumed, or reused; any later build requires a
new absent generation and review.

```powershell
if ($buildAttempt -cnotmatch '^build-attempt-v[1-9][0-9]*$') { throw 'Invalid build attempt generation.' }
$bundle = "$releaseRoot/source/prime-$primeShort.bundle"
New-Item -ItemType Directory -Path "$releaseRoot/source" | Out-Null

git -C $primeRoot bundle create $bundle $approvedPrimeBundleRef
if ($LASTEXITCODE -ne 0) { throw 'Prime Git bundle creation failed.' }
git -C $primeRoot bundle verify $bundle
if ($LASTEXITCODE -ne 0) { throw 'Prime Git bundle verification failed.' }
$advertisedBundleHeads = @(git -C $primeRoot bundle list-heads $bundle)
$expectedBundleHead = "$approvedPrimeHead $approvedPrimeBundleRef"
if ($LASTEXITCODE -ne 0 -or
    $advertisedBundleHeads.Count -ne 1 -or
    $advertisedBundleHeads[0] -cne $expectedBundleHead) {
    throw 'Prime Git bundle does not advertise exactly the approved head and ref.'
}
```

Transfer only that Git bundle through `/mnt/c`, clone it beneath the matching
absent WSL attempt root, detach the approved commit, and run the public
entrypoint. The Prime checkout, support root, `HOME`, `TMPDIR`, build record,
and ZIP all remain inside that Linux-native attempt generation:

```powershell
$wslBuildCommand = @'
set -euo pipefail
tools=/home/bring/.local/share/rook-prime-build
export PATH="$tools/node-v22.23.2-linux-x64/bin:$tools/bun-v1.3.14:/usr/bin"
root="$HOME/rook-prime-acp-{primeShort}/builds/{buildAttempt}"
test ! -e "$root"
mkdir -p "$root/source"
cp "/mnt/c/UDEV/RookRelease/prime-acp/{primeShort}/builds/{buildAttempt}/source/prime-{primeShort}.bundle" "$root/source/"
git clone --no-checkout --branch codex/rookchat-prime-final-series \
  "$root/source/prime-{primeShort}.bundle" "$root/prime-agent"
git -C "$root/prime-agent" bundle verify "$root/source/prime-{primeShort}.bundle"
git -C "$root/prime-agent" checkout --detach {primeHead}
test "$(git -C "$root/prime-agent" rev-parse HEAD)" = {primeHead}
test "$(git -C "$root/prime-agent" rev-parse HEAD^)" = {primeParent}
test -z "$(git -C "$root/prime-agent" status --porcelain --untracked-files=no)"
test -f "$root/prime-agent/package-lock.json" -a ! -L "$root/prime-agent/package-lock.json"
lockfile_before="$(sha256sum "$root/prime-agent/package-lock.json")"
lockfile_before="${lockfile_before%% *}"
[[ "$lockfile_before" =~ ^[0-9a-f]{64}$ ]]
env -i HOME="$HOME" PATH="$PATH" LANG=C.UTF-8 LC_ALL=C.UTF-8 TMPDIR=/tmp CI=1 \
  /mnt/c/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/scripts/build-prime-acp-runtime.sh \
  --prime-worktree "$root/prime-agent" \
  --build-record "$root/build-record.txt" \
  --expected-prime-commit {primeHead} \
  --expected-prime-parent {primeParent}
binary="$root/prime-agent/packages/coding-agent/binaries/windows-x64/pi.exe"
test -f "$binary" -a ! -L "$binary"
node - "$binary" <<'NODE'
const bytes = require("fs").readFileSync(process.argv[2]);
if (!bytes.includes(Buffer.from("global.openai.gpt-5.6-sol")) ||
    bytes.includes(Buffer.from("anthropic.claude-fable-5-1"))) process.exit(1);
NODE
test "$(git -C "$root/prime-agent" rev-parse HEAD)" = {primeHead}
test "$(git -C "$root/prime-agent" rev-parse HEAD^)" = {primeParent}
test -z "$(git -C "$root/prime-agent" status --porcelain --untracked-files=no)"
lockfile_after="$(sha256sum "$root/prime-agent/package-lock.json")"
test "${lockfile_after%% *}" = "$lockfile_before"
'@.Replace('{primeShort}', $primeShort).Replace('{buildAttempt}', $buildAttempt).Replace('{primeHead}', $approvedPrimeHead).Replace('{primeParent}', $approvedPrimeParent)
wsl.exe -d Ubuntu-24.04 --exec /bin/bash -lc $wslBuildCommand
if ($LASTEXITCODE -ne 0) { throw 'Prime WSL build attempt failed.' }

$rookStatus = @(git -C $rookRoot status --short)
if ($LASTEXITCODE -ne 0 -or $rookStatus.Count -ne 0 -or
    (git -C $rookRoot rev-parse HEAD) -cne $approvedRookCommit) {
    throw 'Rook source identity changed during Step 7.'
}
$buildEntrypoint = Get-Item -LiteralPath "$rookRoot/scripts/build-prime-acp-runtime.sh" -Force
if ($buildEntrypoint.PSIsContainer -or
    ($buildEntrypoint.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
    -not $buildEntrypoint.FullName.StartsWith("$rookRoot\", [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Rook build entrypoint changed during Step 7.'
}
```

The command above is the default no-proxy invocation. A separately reviewed
local or CI command may add only uppercase `HTTP_PROXY`, `HTTPS_PROXY`,
`ALL_PROXY`, and `NO_PROXY` assignments to the outer `env -i` command. It must
name those assignments explicitly; it may not forward the caller's environment.
The entrypoint clears its builder environment again and inserts only those
reviewed names. Their names, never values, enter the diagnostic build record.

Do not run `npm audit` inside this build-admission command. The dependency
findings observed in v1 remain unclassified. A later diagnostic requires its own
authorization with an explicit deadline, output-byte ceiling, cleanup behavior,
and retained status; it remains non-authoritative for the build artifact. Do not
run `npm audit fix` or change dependencies in this task.

Any build or custody failure rejects this invocation. Do not repair or resume
its checkout or any sibling output. Preserve the complete build attempt and build
record as diagnostics. Report its exact ZIP SHA-256 and stop for independent
review; do not launch `pi.exe`.

- [ ] **Step 8: Transfer the one ZIP, assemble the installer payload, and stop**

Copy only the upstream ZIP into a fresh Windows directory and compare its hash
with the WSL result before extraction. The independently approved Step 8
command again names the exact Task 10 implementation commit and final Prime
series head as literal local PowerShell values. Before creating an assembly
attempt, require that clean Rook identity and the exact packager and verifier source files as regular,
non-reparse files beneath that checkout:

```powershell
Set-StrictMode -Version Latest
if (-not (Test-Path Variable:ApprovedWslZipSha256) -or
    $ApprovedWslZipSha256 -cnotmatch '^[0-9A-F]{64}$') {
    throw 'The independent Step 7 review must supply the approved ZIP SHA-256.'
}
$rookRoot = (Resolve-Path -LiteralPath 'C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset').Path
# The independently reviewed Step 8 command assigns the same approved commit
# here as a literal 40-hex string; it is not read from environment or HEAD.
if (-not (Test-Path Variable:approvedRookCommit) -or
    $approvedRookCommit -cnotmatch '^[0-9a-f]{40}$') {
    throw 'The reviewed Step 8 command must name the approved Rook commit literally.'
}
if (-not (Test-Path Variable:approvedPrimeHead) -or
    $approvedPrimeHead -cnotmatch '^[0-9a-f]{40}$') {
    throw 'The reviewed Step 8 command must name the approved Prime head literally.'
}
$rookStatus = @(git -C $rookRoot status --short)
if ($LASTEXITCODE -ne 0 -or $rookStatus.Count -ne 0 -or
    (git -C $rookRoot rev-parse HEAD) -cne $approvedRookCommit) {
    throw 'Rook worktree is not the approved clean Task 10 implementation.'
}
$packagerPath = "$rookRoot/scripts/package-prime-acp-runtime.py"
$verifierSource = "$rookRoot/mcp_server/src/rook/agent/chat/prime_runtime_artifact.py"
foreach ($entrypointPath in @($packagerPath, $verifierSource)) {
    $entrypoint = Get-Item -LiteralPath $entrypointPath -Force
    if ($entrypoint.PSIsContainer -or
        ($entrypoint.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        -not $entrypoint.FullName.StartsWith("$rookRoot\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Invalid Rook assembly entrypoint: $entrypointPath"
    }
}
$python = "$rookRoot/mcp_server/.venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Exact worktree Python is absent.' }
if (Test-Path Env:PYTHONPATH) { throw 'Step 8 does not admit PYTHONPATH.' }
$verifierOrigin = (& $python -I -c 'import pathlib, rook.agent.chat.prime_runtime_artifact as m; print(pathlib.Path(m.__file__).resolve())').Trim()
if ($LASTEXITCODE -ne 0 -or
    [IO.Path]::GetFullPath($verifierOrigin) -cne [IO.Path]::GetFullPath($verifierSource)) {
    throw 'Rook verifier does not import from the approved checkout.'
}

$approvedBuildAttempt = 'build-attempt-v4'
if ($approvedBuildAttempt -cnotmatch '^build-attempt-v[1-9][0-9]*$') { throw 'Invalid approved build attempt.' }
$assemblyAttempt = 'assembly-attempt-v1'
if ($assemblyAttempt -cnotmatch '^assembly-attempt-v[1-9][0-9]*$') { throw 'Invalid assembly attempt.' }
$primeShort = $approvedPrimeHead.Substring(0, 8)
$releaseRoot = "C:/UDEV/RookRelease/prime-acp/$primeShort/assemblies/$assemblyAttempt"
$windowsRoot = "$releaseRoot/windows"
if (Test-Path -LiteralPath $releaseRoot) { throw 'Assembly attempt root must be absent.' }
New-Item -ItemType Directory -Path $windowsRoot | Out-Null
$windowsZip = "$windowsRoot/pi-windows-x64.zip"
$wslTransferCommand = @'
set -euo pipefail
cp "$HOME/rook-prime-acp-{primeShort}/builds/{buildAttempt}/prime-agent/packages/coding-agent/binaries/pi-windows-x64.zip" \
  "/mnt/c/UDEV/RookRelease/prime-acp/{primeShort}/assemblies/{assemblyAttempt}/windows/pi-windows-x64.zip"
'@.Replace('{primeShort}', $primeShort).Replace('{buildAttempt}', $approvedBuildAttempt).Replace('{assemblyAttempt}', $assemblyAttempt)
wsl.exe -d Ubuntu-24.04 --exec /bin/bash -lc $wslTransferCommand
$windowsZipSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $windowsZip).Hash
if ($windowsZipSha256 -ne $ApprovedWslZipSha256) { throw 'WSL-to-Windows ZIP hash differs.' }
```

The WSL ZIP remains owned by its immutable build-attempt name. The Windows
transfer root, `uv` inputs, and ignored packager output carry a separate
assembly-attempt name. None may exist before its producer runs. Any assembly
failure preserves only that generation as non-authoritative; a later authorized
`assembly-attempt-v2` may consume the same independently approved build-attempt
and ZIP hash while repeating transfer, input acquisition, hashing, packaging,
and verification from the beginning. A build failure still requires a new
build attempt and separate review.

`ApprovedWslZipSha256` is the exact value independently read from the Step 7
build record at this review boundary. It is not self-supplied by the packager.

Acquire the three frozen `uv` inputs into a fresh release-input directory. The
release procedure owns network acquisition; the offline packager independently
rechecks each ceiling and SHA-256:

```powershell
$inputs = "$releaseRoot/inputs/uv-0.12.3"
if (Test-Path -LiteralPath $inputs) { throw 'uv input root must be absent.' }
New-Item -ItemType Directory -Path $inputs | Out-Null
curl.exe --fail --location --max-filesize 134217728 --output "$inputs/uv-x86_64-pc-windows-msvc.zip" https://github.com/astral-sh/uv/releases/download/0.12.3/uv-x86_64-pc-windows-msvc.zip
if ($LASTEXITCODE -ne 0) { throw 'uv archive download failed.' }
curl.exe --fail --location --max-filesize 1048576 --output "$inputs/LICENSE-APACHE" https://raw.githubusercontent.com/astral-sh/uv/0.12.3/LICENSE-APACHE
if ($LASTEXITCODE -ne 0) { throw 'uv Apache license download failed.' }
curl.exe --fail --location --max-filesize 1048576 --output "$inputs/LICENSE-MIT" https://raw.githubusercontent.com/astral-sh/uv/0.12.3/LICENSE-MIT
if ($LASTEXITCODE -ne 0) { throw 'uv MIT license download failed.' }

$approvedInputs = @(
    @{ Path = "$inputs/uv-x86_64-pc-windows-msvc.zip"; Maximum = 134217728; Sha256 = 'B23350C79E8AD0192B8124AF13A0F17E8D4E4549524785E1AEF389AE5A06990E' },
    @{ Path = "$inputs/LICENSE-APACHE"; Maximum = 1048576; Sha256 = 'C71D239DF91726FC519C6EB72D318EC65820627232B2F796219E87DCF35D0AB4' },
    @{ Path = "$inputs/LICENSE-MIT"; Maximum = 1048576; Sha256 = '860E3D7A86B84E6A7012C7A635FC64DF475CEBC6CCE34DFEB73A5982EC58176C' }
)
foreach ($input in $approvedInputs) {
    if (-not (Test-Path -LiteralPath $input.Path -PathType Leaf)) {
        throw "Missing release input: $($input.Path)"
    }
    $file = Get-Item -LiteralPath $input.Path -Force
    if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        $file.PSIsContainer -or $file.Length -gt $input.Maximum) {
        throw "Invalid release input: $($input.Path)"
    }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $input.Path).Hash -ne $input.Sha256) {
        throw "Release input hash differs: $($input.Path)"
    }
}
```

Invoke the offline packager against a fresh ignored release-staging root:

```powershell
Set-Location $rookRoot
$output = "installer/runtime/prime/staging/$assemblyAttempt/runtimes"
if (Test-Path -LiteralPath $output) { throw 'Prime runtime staging must be absent.' }
& $python -I $packagerPath `
    --prime-zip $windowsZip `
    --expected-prime-zip-sha256 $ApprovedWslZipSha256 `
    --rook-skill installer/agent-assets/prime-skills/rook-full `
    --uv-zip "$inputs/uv-x86_64-pc-windows-msvc.zip" `
    --uv-license-apache "$inputs/LICENSE-APACHE" `
    --uv-license-mit "$inputs/LICENSE-MIT" `
    --prime-license third_party/prime-agent/LICENSE `
    --output-runtimes-root $output
if ($LASTEXITCODE -ne 0) { throw 'Prime runtime packaging failed.' }
$rookStatus = @(git -C $rookRoot status --short)
if ($LASTEXITCODE -ne 0 -or $rookStatus.Count -ne 0 -or
    (git -C $rookRoot rev-parse HEAD) -cne $approvedRookCommit) {
    throw 'Rook source identity changed during packaging.'
}

$runtimeDirs = @(Get-ChildItem -LiteralPath $output -Directory -Force)
if ($runtimeDirs.Count -ne 1 -or $runtimeDirs[0].Name -cnotmatch '^[0-9A-F]{64}$') {
    throw 'Prime runtime staging must contain exactly one runtime-ID directory.'
}
$runtimeId = $runtimeDirs[0].Name
& $python -I -m rook.agent.chat.prime_runtime_artifact verify `
    --runtime-root $runtimeDirs[0].FullName `
    --expected-runtime-id $runtimeId
if ($LASTEXITCODE -ne 0) { throw 'Staged Prime runtime verification failed.' }

$rookStatus = @(git -C $rookRoot status --short)
if ($LASTEXITCODE -ne 0 -or $rookStatus.Count -ne 0 -or
    (git -C $rookRoot rev-parse HEAD) -cne $approvedRookCommit) {
    throw 'Rook source identity changed during Step 8.'
}
foreach ($entrypointPath in @($packagerPath, $verifierSource)) {
    $entrypoint = Get-Item -LiteralPath $entrypointPath -Force
    if ($entrypoint.PSIsContainer -or
        ($entrypoint.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        -not $entrypoint.FullName.StartsWith("$rookRoot\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Rook assembly entrypoint changed during Step 8: $entrypointPath"
    }
}
```

Rerun the complete Step 6 gate in its documented source-only installer-guard
mode and confirm Git has no new tracked or untracked files. The
installed-verifier entrypoint remains covered by its complete synthetic install
fixture; Task 10 does not pretend this release-staging root is already installed.
Prime runtime assembly and installer source/promotion wiring are the Task 10
claims. Full built-plugin payload qualification is deliberately deferred to the
installed-product promotion and release-build gate, where the unchanged full
guard runs after real Release outputs exist. Do not compile the installer,
deploy, install, or launch Prime in Task 10.

Report the exact approved Rook implementation commit, its pre/post clean
identity, build-attempt and assembly-attempt names, complete Prime series and final head,
pre/post lockfile hash, observed build-tool versions, explicit network-setting
names if any, exact build command, WSL and Windows ZIP hashes, runtime ID,
manifest SHA-256, complete output root, and all test results. STOP for
independent artifact review before Task 11 or any external Slice B lifecycle
execution.

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
- Delete: `src/Rook/UI/Chat/ClaudeCodeTab.cs`
- Delete: `src/Rook/UI/Chat/ClaudeCodeWrapper.cs`
- Delete: `src/Rook/UI/Chat/ClaudePanelMcpConfigBuilder.cs`
- Delete: `src/Rook/UI/Chat/SettingsDialog.cs`
- Delete: `src/Rook/UI/Chat/StreamJsonParser.cs`
- Delete: `src/Rook.Tests/UI/Chat/ClaudePanelMcpConfigBuilderTests.cs`
- Delete: `src/Rook/UI/Chat/Resources/prototype.html`
- Modify: `src/Rook/UI/Chat/ChatTab.cs`
- Modify: `src/Rook/UI/Chat/Resources/chat.html`
- Modify: `src/Rook/UI/Chat/Resources/chat.css`
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

The managed project uses SDK-default compile inclusion and embeds every file below
`src/Rook/UI/Chat/Resources`. Although `RookChatPanel` constructs only
`AgentChatTab`, the five legacy `ClaudeCode*`/settings/stream-parser source files
therefore remain compiled product code, and `prototype.html` remains shipped
content. Delete those five production files, their dedicated
`ClaudePanelMcpConfigBuilderTests.cs`, and the embedded prototype. Do not retain a
second direct-Claude subprocess, process restart/termination owner, temporary MCP
configuration path, stream protocol, or Claude-specific settings path merely
because no current constructor reaches it.

The removed server pseudo-tool also leaves an unowned `ui_block` presentation path.
Remove only that path from the retained generic panel surface:

- `ChatTab.cs`: remove `OnUIBlockSubmitAsync`, the `ui_block_submit` bridge
  registration and handler, and comments that claim an agent-tab owner;
- `chat.html`: remove stale-block submission, all `renderUIBlock`/
  `updateUIBlock` helpers and interactions, and their exported API entries;
- `chat.css`: remove the `.ui-block*` presentation and state rules;
- `prototype.html`: delete the obsolete embedded adaptive-UI prototype completely.

Keep `ChatTab`, its ordinary `submit` bridge, generic rendering, and
`AgentChatTab` intact. If another caller of any deleted class or `ui_block` symbol
appears, stop for plan correction instead of deleting or adapting it
opportunistically.

Shared production cleanup is equally explicit. Remove the ChatRunner-only `list_chat_models`, `set_chat_model`, and `ui_block` pseudo-tool sentinels and their tool-group memberships. Retain internal-agent interceptions such as `request_tools`, `search_tools`, and the MCP capability gateway, but rename shared dispatchability terminology from `chatrunner_intercepted` to owner-neutral internal-agent terminology. Keep the capability inventory, dispatcher, gateway profile intersection, `tool_result_view`, `tool_contracts`, `execution_policy`, persona infrastructure used by planner/spawn, knowledge routes, authenticated HTTP middleware, service discovery, and generic panel rendering. The `server.py` gateway profile helper remains shared; only its obsolete ChatRunner wording changes.

If the audit finds another production owner or test caller beyond this closed classification, stop for plan correction instead of broadening deletion opportunistically.

- [ ] **Step 3: Update architecture and user docs**

Document one Prime ACP implementation, Prime-owned login via interactive `/login`, new-conversation model/reasoning selection, reopen behavior, target-unavailable behavior, image-history limits, release-level rollback, preserved data roots, and the explicit `session_recovery_required` limitation after service crash. State that Rook installs the required Prime executable and `uv` bootstrap tool with no separate software installation, while first IPython/Rook use may require an internet download and take longer as Prime creates its normal mutable kernel. Do not advertise compaction or IPython restoration guarantees.

Keep uninstall custody exact: ACP data below
`%LOCALAPPDATA%\Rook\data\rookchat\acp\v1` survives a retained-data uninstall, but
a normal uninstall may remove `%LOCALAPPDATA%\Rook\app`, including installed Prime
runtimes. After reinstall, reopening a conversation whose recorded runtime is no
longer installed returns `runtime_unavailable`; there is no fallback scan or
substitution. Correct this wording in `docs/CURRENT_ARCHITECTURE.md` and
`AGENT_SETUP.md` without weakening upgrade, repair, or release-rollback retention.

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

Commit `7f69aa9edf4da0ad2f0868a7fb6e83629f85d8a9` is the preserved
Python ChatRunner-removal base. Independent review found the additional compiled
managed owner above, so Task 11 remains open until the following bounded correction
lands over that commit.

- [ ] **Step 6: Extend the RED non-port fixtures across every forbidden family**

Modify only `mcp_server/tests/test_rookchat_acp_cutover.py` first. Continue using
temporary product trees and `scan(root)`; no test may inspect the verifier's own
source text and count matching phrases as evidence. Expand every row below into one
separately parameterized behavioral case for each individual forbidden path, symbol,
or spelling. Every case contains exactly one planted violation and requires its
exact finding code; no fixture may combine alternative spellings and let one match
stand as evidence for the others. The complete matrix must exercise every finding
code independently:

| Family | Exact fixture paths or symbols | Finding |
| --- | --- | --- |
| Existing obsolete Python paths | `mcp_server/src/rook/agent/chat/conversation_store.py`, `mcp_server/src/rook/agent/chat/chat_runner.py`, `mcp_server/src/rook/agent/chat/model_status.py`, `mcp_server/src/rook/agent/chat/prompt_builder.py`, `mcp_server/src/rook/agent/worker_first_csharp_application.py`, `scripts/chatrunner_headless_qualification.py` | `obsolete_path` |
| Closed managed paths | `src/Rook/UI/Chat/ClaudeCodeTab.cs`, `src/Rook/UI/Chat/ClaudeCodeWrapper.cs`, `src/Rook/UI/Chat/ClaudePanelMcpConfigBuilder.cs`, `src/Rook/UI/Chat/SettingsDialog.cs`, `src/Rook/UI/Chat/StreamJsonParser.cs`, `src/Rook.Tests/UI/Chat/ClaudePanelMcpConfigBuilderTests.cs` | `obsolete_path` |
| Embedded prototype | `src/Rook/UI/Chat/Resources/prototype.html` | `obsolete_path` |
| Obsolete module imports | `rook.agent.chat.conversation_store`, `rook.agent.chat.chat_runner`, `rook.agent.chat.model_status`, `rook.agent.chat.prompt_builder`, `rook.agent.worker_first_csharp_application` | `obsolete_import` |
| Obsolete HTTP routes | `/agent/chat/personas`, `/agent/chat/model`, `/agent/chat/models`, `/agent/chat/start`, `/agent/chat/message`, `/agent/chat/stop`, `/agent/chat/ui-response`, `/agent/chat/worker-first` | `obsolete_route` |
| Direct-Claude implementation | `ClaudeCodeTab`, `ClaudeCodeWrapper`, `ClaudePanelMcpConfigBuilder` | `legacy_direct_claude` |
| Private Prime RPC | `PrimeRpcProcess`, `PrimeRpcClient`, `prime_rpc`, `AgentConnection` | `private_prime_transport` |
| Daemon/worker topology | `DaemonClient`, `PrimeDaemonClient`, `DaemonAgentConnection`, `daemonTransport`, `daemon_transport`, `daemonSocket`, `daemon_socket`, `--daemon-socket`, `PrimeWorkerProcess`, `workerProcess`, `worker_process`, `prime_worker` | `daemon_topology` |
| Process-start authority | `processStartUtcTicks`, `process_start_utc_ticks`, `processStartTicks`, `process_start_ticks` | `process_start_authority` |
| Backend registry/selector | `availableBackends`, `available_backends`, `backendRegistry`, `backend_registry`, `backendSelector`, `backend_selector`, `ChatRunnerBackend` | `backend_abstraction` |
| Process surveillance | PowerShell plus `Get-Process` in either order, `psutil.process_iter`, `CreateToolhelp32Snapshot`, `kill-by-name` | `process_surveillance` |
| C# ACP SDK ownership | `AgentClientProtocol`, `agent-client-protocol` | `csharp_acp_owner` |
| Other non-Python ACP SDK ownership | `AgentClientProtocol`, `agent-client-protocol` | `non_python_acp_sdk` |
| Runtime evaluator imports | import paths containing the exact segment `campaign`, `qualification`, or `evaluator` | `runtime_evaluator` |
| Obsolete adaptive UI | `ui_block`, `ui_block_submit`, `renderUIBlock`, `updateUIBlock`, `.ui-block` | `obsolete_ui_block` |
| Unreadable product source | one malformed UTF-8 product-source fixture written as bytes | `unreadable_product_source` |

Each symbol fixture lives under a Rook-owned chat source root. The scanner must not
apply these RookChat topology bans to the manifest-bound third-party Prime payload.
The test matrix declares its cases independently; it does not import the verifier's
patterns or forbidden-path constants as its expected oracle.
Add `.css` to the product text suffixes so `.ui-block` rules are observable. Keep
the existing repository fixture. It may remain green under the old verifier in
Step 6; after Step 7 strengthens the verifier and before product deletion, it must
fail on the closed managed paths and obsolete UI symbols.

Add one admitted fixture containing a retained non-chat
`mcp_server/src/rook/learning/agent.py` with ordinary Claude/LiteLLM/DSPy/Chirp
references and prove that it receives no finding. The exact production file remains
unchanged. The scanner forbids obsolete RookChat ownership, not supported non-chat
provider consumers.

Run:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_rookchat_acp_cutover.py -q
```

Expected RED boundary is intentionally mixed. Existing recognized cases remain
green, including `AgentConnection` with `private_prime_transport` and
`availableBackends`, `backendSelector`, and `ChatRunnerBackend` with
`backend_abstraction`. Every previously unsupported exact path or spelling is RED
because its required finding is absent; `--daemon-socket` is also RED for
`daemon_topology` while the old verifier still assigns it to
`private_prime_transport`. Record every individual case and its result. The real
repository test may remain green under the old verifier at this point; it does not
become authoritative until Step 7 strengthens the verifier. Any harness, fixture,
interpreter, or unrelated failure stops the correction.

- [ ] **Step 7: Strengthen the verifier while the real residue is still present**

Update `scripts/verify-rookchat-acp-cutover.py` to implement the exact closed paths,
suffixes, unmistakable legacy symbol families, and finding codes exercised in Step
6. `SettingsDialog` and `StreamJsonParser` are forbidden only through their exact
closed file paths; do not prohibit those generic class names elsewhere in future
RookChat code. Use bounded text scanning of Rook-owned product sources and the
existing AST import check. Do not add process inspection, compiled-assembly
reflection, a general policy engine, or a second manifest. Keep the scanner itself,
test directories, the manifest-bound third-party Prime payload, and retained
non-chat provider consumers outside symbol-policy scanning.

Run the adversarial fixtures independently, then the complete file:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_rookchat_acp_cutover.py -q -k "not repository_has_only_the_prime_acp_chat_product"
./.venv/Scripts/python.exe -m pytest tests/test_rookchat_acp_cutover.py -q
```

Expected: every individually parameterized adversarial fixture is green because the
strengthened verifier produces its exact finding for that one path or spelling,
while the complete file has exactly one RED test:
`test_repository_has_only_the_prime_acp_chat_product`. That failure must report the
actual legacy C# paths and `ui_block` residue still in the repository. Do not delete
that residue until this causal detection is retained.

- [ ] **Step 8: Delete the proven-unowned managed implementation and UI-block path**

Before deletion, run the closed ownership audit:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
rg -n -i "ClaudeCodeTab|ClaudeCodeWrapper|ClaudePanelMcpConfigBuilder|SettingsDialog|StreamJsonParser|ui_block|ui-block|renderUIBlock|updateUIBlock|prototype.html" src/Rook src/Rook.Tests
```

Delete exactly the seven closed files added to Task 11's file table. Apply the
symbol removals listed above to `ChatTab.cs`, `chat.html`, and `chat.css`. Do not
change `AgentChatTab`, `AgentChatClient`, `RookChatPanel`, service ownership, or any
non-chat Claude/LiteLLM/DSPy/Chirp consumer. Any additional production owner found
by the audit stops the correction.

The repository test and CLI now become green:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_rookchat_acp_cutover.py -q

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
mcp_server/.venv/Scripts/python.exe scripts/verify-rookchat-acp-cutover.py --root C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
```

Expected: all adversarial fixtures pass, the real repository has zero findings,
and the five deleted legacy C# files/classes cannot be reintroduced without failing
the gate.

- [ ] **Step 9: Correct uninstall/runtime-retention documentation**

Modify only `docs/CURRENT_ARCHITECTURE.md` and `AGENT_SETUP.md` as specified in
Step 3. Preserve the rest of the approved ACP ownership and recovery wording.

- [ ] **Step 10: Run the complete Task 11 correction gate**

Run the adapted 308-test Python suite and frozen 365-test ACP suite from Step 4,
then:

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore
mcp_server/.venv/Scripts/python.exe -m compileall -q mcp_server/src mcp_server/tests/test_rookchat_acp_cutover.py scripts/verify-rookchat-acp-cutover.py scripts/vertex_oauth_acceptance.py
mcp_server/.venv/Scripts/python.exe scripts/verify-rookchat-acp-cutover.py --root C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git diff --check
```

The managed suite must compile without the deleted classes and contain only
`AgentChatTab` as its conversation implementation. No build, deployment,
installation, Prime process, kernel, provider, model, Rhino, or Grasshopper runtime
is admitted by this gate.

- [ ] **Step 11: Commit the bounded Task 11 correction and stop**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add src/Rook/UI/Chat/ClaudeCodeTab.cs src/Rook/UI/Chat/ClaudeCodeWrapper.cs src/Rook/UI/Chat/ClaudePanelMcpConfigBuilder.cs src/Rook/UI/Chat/SettingsDialog.cs src/Rook/UI/Chat/StreamJsonParser.cs src/Rook.Tests/UI/Chat/ClaudePanelMcpConfigBuilderTests.cs src/Rook/UI/Chat/Resources/prototype.html src/Rook/UI/Chat/ChatTab.cs src/Rook/UI/Chat/Resources/chat.html src/Rook/UI/Chat/Resources/chat.css mcp_server/tests/test_rookchat_acp_cutover.py scripts/verify-rookchat-acp-cutover.py docs/CURRENT_ARCHITECTURE.md AGENT_SETUP.md
git commit -m "refactor(chat): finish ACP-only panel cutover"
```

Plan lineage before this correction is exact:
`347a2d9b3e963b66241ad356e01e22c3f0b61e80` ->
`641c4d7410be3c034f66e4bd46e9c255f21f8be6`. Implementation starts only
from the exact amended plan head subsequently approved by independent review; a
later plan-only correction supersedes `641c4d74` as that head. Verify that approved
plan head is the implementation correction commit's direct parent; do not reset to
or branch the correction directly from `7f69aa9e`. Also verify closed scope,
`git show --check`, and clean Rook/Prime/Chirp worktrees. Stop for independent Task
11 review. Task 12 remains unauthorized.

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
- Consumes: the assembled/staged Prime payload through the production runtime loader for A+B; installed-product authority begins at the later promotion gate. No qualification module is imported by `mcp_server/src/rook`.

**Current correction boundary:** Preserve the authored harness at `3594ff72`.
This documentation amendment must receive review before correcting those five
qualification files and their causal tests. A+B remains unexecuted; no
execution or evidence root is created during this correction. After the
harness correction, return to Step 6 for review of the exact qualification
commit and hashes before any execution authorization.

- [ ] **Step 1: Write RED protocol-custody tests**

Each protocol must contain exact schema/version, product implementation commit, runtime/skill manifests, prompt/input hashes, wall-clock/token/process-close limits, target/profile identity, evaluator identity when applicable, fresh separate `executionRoot` and `evidenceRoot` paths, and a one-execution version. Freeze evidence limits of 16,777,216 bytes per file, 67,108,864 total bytes (`maxEvidenceTotalBytes`), and 64 regular files (`maxEvidenceFiles`), including terminal/index/seal files. The A+B pre-contact protocol additionally binds the fresh `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, and `ROOK_DATA_DIR`; the product-derived `UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR`; the derived absent-before kernel path; the complete six-key product-owned `UV_*` map; the exact seeded ambient `UV_*` and proxy-key cases; Slice B's qualification-only `--offline` flag; the production `--no-approve` selector; the ACP source-composition non-reachability assertion; the CONNECT proxy identity and exact inserted `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY` values; the complete expected final Prime child-environment map and hash; and the exact admitted host set `github.com`, `api.github.com`, `objects.githubusercontent.com`, `release-assets.githubusercontent.com`, `releases.astral.sh`, `pypi.org`, and `files.pythonhosted.org`. The promotion protocol additionally binds MSVC toolset `14.44.35207`, Release configuration, the exact deployment command, expected source/installed artifact paths, and installed-verifier identity.

A+B execution authorization supplies the literal independently reviewed
qualification HEAD through mandatory `--expected-qualification-commit`, with
no default or inference from HEAD/protocol. Before any root creation, require
exact HEAD equality and a clean worktree. Require `--protocol` to resolve to
the exact tracked `scripts/qualification/protocols/rookchat-prime-acp-precontact-v1.json`
at that commit, and compare raw Git-blob bytes for it and the three loaded
qualification modules (common, pre-contact, deterministic provider). Resolve
those modules from the same worktree. Preserve the separate product baseline
and source-input checks; a clean descendant is not sufficient qualification
authority. No self-referential commit/hash field is added to the protocol.
Bounded, read-only Git subprocesses are allowed for this admission and use the
same exact-child cleanup path. Before admission succeeds, prohibit Prime, test,
provider/proxy, MCP, kernel, and other contact-capable processes/services, not
the Git commands establishing source custody.

Complete read-only preparation before `EvidenceRoot.create()` or execution
workspace creation: call production `load_and_verify_runtime()`, compare its
contract with the frozen protocol, construct initial/reopen argv through
`build_prime_argv()`, and compare the complete `build_prime_child_env()` result
and hash. Freeze `qualificationConversationId` in the A+B protocol as
`11111111111141118111111111111111` (32 lowercase UUID hex characters). Derive
`AcpDataPaths` from the explicit workspace-owned Rook data root without calling
`create_roots()` or constructing `AssociationStore`; use its existing
`session_path(qualificationConversationId)` for the prospective session path.
After admission and root creation, construct `ProvisionalAssociation` with
that same ID/path and admitted working directory, runtime, binding, and model
fields. Exercise the real header-validation and `AssociationStore.publish()`
path, not a fixture-only publication substitute. Slice A continues testing
ordinary `reserve_provisional()` allocation. Add no product allocator API and
do not duplicate its UUID/path logic. Pass the admitted preparation to Slice B.
A partial manifest/pi.exe check cannot replace closed-file runtime
verification. Missing/extra/altered payload bytes, identity drift, invalid
arguments/environment, existing roots, or product imports of qualification
code refuse with zero Slice A commands and neither root created.

Add separately parameterized causal tests for runner, common, provider, and
protocol drift (including a later clean commit and an alternate protocol),
and missing/extra/altered runtime files. Exercise the entrypoint's admission
order; allow only bounded read-only Git custody commands and assert zero
contact-capable operations and absent execution/evidence roots on refusal.
Add a causal case proving that the exact pre-admitted session path is supplied
to initial/reopen argv, ACP persistence, header validation, and real association
publication; no post-admission reservation may allocate a replacement ID/path.

During the separately approved harness correction, remove the nonexistent
managed-tool-download selector from the protocol's forbidden-argument list and
qualification assertions. Preserve the source-composition test and helper-artifact
checks as the actual evidence; add no absence assertion for an unimplemented flag.
The protocol JSON and tests remain untouched in this documentation-only amendment.

Each frozen live version executes once and its result is immutable. Any correction after execution requires a newly versioned protocol, fresh execution/evidence roots, and separate authorization; the runner never retries or overwrites a failed version. The unexecuted A+B draft is corrected and reviewed before its first authorization.

- [ ] **Step 2: Implement one finite common runner**

`rookchat_prime_acp_common.py` may hash admitted inputs, create the two fresh
roots, write bounded results, and own directly launched qualification
processes. Use one fresh disposable execution workspace, separate from and
not enclosing the evidence directory, source, or staged payload. Keep mutable
homes, sessions, claims, presentation, uv/cache/managed-Python/kernel files,
and temporary output there. Only explicitly selected bounded logs, results,
hashes, and first-line session-header evidence enter the evidence directory.
Do not recursively manifest or seal the workspace. Failed workspaces have no
qualification authority and are never adopted or reused.
Workspace deletion is permitted only after every exact owned process and thread
has been observed stopped. If cleanup remains uncertain, retain the complete
workspace unchanged as non-authoritative diagnostic state; never reuse or adopt
it. Cover unobserved child exit and unobserved service-thread shutdown with
before/after workspace assertions proving no deletion is attempted.

Enforce file-count, total-byte, and per-file evidence ceilings before each
write/copy, reserving capacity for terminal/index/seal files. Sealing indexes
only the known retained files and refuses unknown files or links. Test a
large workspace file and excess workspace entries that do not enter evidence,
plus exact-limit/over-limit evidence writes and create-only publication.

From successful spawn through observed exit, preserve ownership of the exact
process handle. On `BaseException`, including cancellation/outer timeout and
Ctrl+C, shield the same bounded retirement used for timeout/overflow, then
re-raise. Terminate, escalate to kill if needed, and observe exit within the
single 30-second cleanup deadline. If exit remains unobserved, report failure
and cancel/settle reader tasks boundedly; never wait indefinitely for EOF.
Test a real sleeping test-Python child cancelled after spawn, capturing that
same handle, plus a fake unexitable child with blocked readers. No PID lookup,
process table, PowerShell probe, kill-by-name, retry, or new product state.

Put admission-record writes and execution inside one protected finalization
path. Attempt one create-only `result.json`, then seal once. Preserve the
original failure if result publication or sealing also fails; report the
finalization failure separately in bounded stderr with a nonzero exit, without
recreating result.json or claiming a seal succeeded. Test admission-write and
seal failures, retaining the triggering exception and single result attempt.

- [ ] **Step 3: Implement Slice A against the fake ACP agent**

Exercise the exact C#-equivalent HTTP boundary and all model-free cases listed in spec section 15.1: protocol/capability admission, literal verified system-contract bytes and rendered-Windows-argv bounds, production inclusion of `--no-approve`, production exclusion of `--offline`, case-insensitive `PI_OFFLINE` removal, direct ACP composition non-reachability of managed helper acquisition, bounded stderr drainage under pipe pressure, service-owned prompt survival after HTTP waiter cancellation, close/delete/shutdown detach-before-retirement races, first-turn publication, saved/unsaved working-directory custody, internal latest-runtime selection, two-service claim contention, crash claim preservation, failed/uncertain spawn, SDK-callback source-ordinal preservation, generation fences, overflow cancellation, permission policy, cache/image/model arguments, MCP injection, strict Rook envelope projection, GH schemas, bounds, 20-second startup/60-second call contract projection, and close failures.

Resolve exact executable paths for the five existing commands before launch.
Construct one small test environment from explicit Windows/runtime essentials
and execution-workspace home/temp paths. PATH contains only required resolved
tool directories and Windows essentials. Do not pass `dict(os.environ)`:
provider credentials, proxy values, `PI_*`, `UV_*`, `PYTHONPATH`, `PYTHONHOME`,
Node/npm overrides, pytest controls, and arbitrary ambient execution policy
are absent. Required extra values must be explicit and nonsecret. Add causal
tests seeding representative credentials, mixed-case proxy/policy variables,
and Python/Node/test overrides, asserting the final environment at every
command boundary. No executable manifest or credential-scanning framework.

- [ ] **Step 4: Implement Slice B against the staged Prime payload and deterministic provider**

Use the admitted preparation and fresh execution workspace containing isolated `PRIME_AGENT_CODING_AGENT_DIR`,
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

Only this isolated Slice B launch adds `--offline` so Prime's updater, catalog,
and unrelated startup network operations remain disabled. The production argv
must omit it, and the protocol must add it externally after verifying the
product selectors. This qualification-only flag does not make the separately
admitted uv bootstrap offline. Configure the qualification-owned CONNECT
proxy for bootstrap clients; it admits only `github.com`, `api.github.com`,
`objects.githubusercontent.com`, `release-assets.githubusercontent.com`,
`releases.astral.sh`, `pypi.org`, and `files.pythonhosted.org`, and the evidence
retains a bounded host/port ledger. Require at least one `proxy_admitted`
event for cold bootstrap, every observed admission on an allowlisted host at
port 443. Admission/connect failures, internal forwarding faults, exceeded
bounds, malformed evidence, qualification-initiated interruption and unobserved
cleanup remain fatal. Catch `ConnectionError` only directly around socket
`send`, `recv`, or `shutdown(SHUT_WR)`; preserve the exact caught exception's
identity so selector/cleanup errors cannot inherit that classification. With
no stop request, retain it as `proxy_transport_aborted` with the admitted
authority and bounded operation, direction, exception/error, pending-byte,
EOF/write-shutdown and stop metadata. Validate that complete diagnostic before
counting it; do not classify by error number, byte count or presumed TLS contents.
It only allows subsequent checks to run. Every existing kernel/source-identity,
provider, MCP, filesystem, persistence, cancellation and cleanup validator must
execute and pass before success. Keep the full abort ledger in successful evidence
and report its count as "observed transport aborts, cause undetermined". No retry
or replay is introduced; historical failures (including V4) remain unchanged.
Require local real-proxy complete/truncated response controls and composed
acceptance tests with missing/failed application evidence and internal faults.
Empty and start/stop-only ledgers fail. The configured loopback bypass serves the local
provider/MCP double; it is not an enforced loopback or outbound firewall.
CONNECT cannot inspect encrypted URL paths, and proxy environment variables
do not prohibit direct traffic. Evidence supports only the destinations
observed by the configured proxy. No TLS interception or network enforcement
system is added to qualification or product runtime.

Use hostile project-resource fixtures under both the launch cwd and the resumed
session cwd. Prove no automatic project-resource discovery, loading,
project-settings access, or project migration occurs during startup/resume
before model work, while global Prime auth/settings and the explicit goal/Rook
skills remain available. State explicitly that this is not a filesystem sandbox
for later model-initiated tool access. Verify that managed `fd`/`rg` executables
and their Prime-owned download directories are absent before and after the
staged payload's ACP lifecycle. The Prime source composition test remains the
authority that ACP never invokes the managed acquisition boundary. Add cases
rejecting empty/start-only proxy ledgers, refused or unallowlisted admissions,
and created helper artifacts; include one allowlisted-admission control.

Provider/proxy shutdown must observe every exact owned thread stopped after a
bounded join. A still-live thread fails closure; copy final journals only
after shutdown is observed. Exercise a fake stuck owned thread for each
service and a real local start/stop control without enumerating threads.

Prime may start kernel prewarm during `session/new`; do not attribute bootstrap
initiation to the first prompt. Prove the actual sequence:

```text
kernel root, uv cache, and uv-managed Python absent before session/new
-> Prime creates its ordinary mutable kernel through manifest-bound uv
-> uv installs the manifest-bound local dist/prime-agent-runtime source
-> first deterministic prompt executes real IPython and mcp.call_tool("rook", ...)
```

The assembled/staged runtime payload must execute
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
bundled uv, while the matching Prime runtime itself comes from the staged
manifest-bound local subtree. The frozen protocol gives that one bootstrap a
predeclared wall-clock bound; failure is terminal for that protocol version,
with no retry or timeout adjustment. Retain only selected bounded bootstrap
diagnostics and source/path hashes; leave the mutable kernel/cache/session
tree in the execution workspace. The proxy ledger reports observed configured
destinations, not URL paths, complete download provenance, extractor behavior,
or exhaustive network containment.

The combined model-free pre-contact gate also exercises the static installed-product verifier against staged installation fixtures, the source-to-installed hash mapping, and deployment/installer data-retention guards. Reports identify these as source/fixture checks and the Prime payload as assembled/staged; installed-product qualification remains deferred to Step 9 promotion. This is not permission to deploy into Rhino's live plugin directories.

- [ ] **Step 5: Run only model-free tests, then commit the frozen qualification code**

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server
./.venv/Scripts/python.exe -m pytest tests/test_rookchat_prime_acp_qualification.py -q

Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
git add scripts/qualification mcp_server/tests/test_rookchat_prime_acp_qualification.py
git commit -m "test(chat): freeze ACP qualification ladder"
```

- [ ] **Step 6: STOP at the combined A+B pre-contact review gate**

Do not execute `rookchat_prime_acp_precontact.py` yet. Present the exact clean qualification HEAD, tracked protocol blob/hash, common/runner/provider hashes, separate product implementation commit, full production-loader verification of the staged runtime, focused causal results, and proof that execution and evidence roots are absent. Independent approval must explicitly authorize one A+B execution and supply the exact value for `--expected-qualification-commit`.

- [ ] **Step 7: After authorization, execute A+B exactly once and stop**

Run the exact independently reviewed command only. Repeat full admission before root creation or Slice A. Whether execution passes or fails, finalize one terminal result and seal only the selected bounded evidence; never recursively adopt the execution workspace. Report finalization failure separately if a seal cannot be completed. Write the A+B report, commit only that report, and stop for independent review. Do not continue to Slice C automatically.

- [ ] **Step 8: Prepare and review Slice C without executing it**

Propose the narrowed Slice C claim for approval before implementation. Keep two proofs separate:

1. Deterministic tests exercise the production panel -> authenticated local HTTP -> Python image validation -> exact ACP content-block handoff without live model or Rook/Rhino/GH contact.
2. One separately authorized live image test uses the existing `DirectAcpProcessFactory` / `PreparedDirectAcpLaunch` and `OwnedAcpProcess` official-SDK transport to reach the verified packaged Prime. Its `new_session()` call explicitly declares `mcp_servers=[]`. It does not invoke the panel, HTTP routes, or `AcpConversationManager`, and must not recreate their implementation.

The production manager's Rook MCP declaration remains unchanged. Do not strip it in a wrapper, depend on model restraint, or add a product test mode. Neither proof nor their combination establishes a live panel-to-model image round trip. Full product-path qualification with Rook enabled remains in later integration gates.

Retain the prepared image/prompt bytes and hashes (visible answer `blue`), proposed `openai-codex/gpt-5.4-mini` with reasoning `low`, and exact approved assembly-attempt-v1 runtime. This is the staged packaged runtime, not yet an installed release. Catalog presence and the reported successful developer login do not establish account/model access. Explicitly bind the future Prime child to `PRIME_AGENT_CODING_AGENT_DIR=C:/Users/bring/.prime-rook-slice-c-dev-auth-20260906-01`; never inspect/copy credentials or include their directory in evidence, logs, copied fixtures, or cleanup targets. Prime alone may perform normal token refresh.

Freeze fresh execution/evidence roots and time, retained-output, answer-length, cancellation, and close limits. The pinned Codex provider transmits no output-token cap; these limits are not token or subscription-usage ceilings. Record returned usage if available, otherwise unavailable. Do not assume cancellation immediately stops server-side processing or patch Prime to add a cap.

The proposed live operator command boundary is the qualification runner -> existing production ACP launch/transport -> packaged Prime with an empty MCP declaration, not a panel/service launch. Present its exact executable command only after bounded runner implementation and admission are reviewed; no command or protocol is currently authorized by this wording amendment. STOP first for approval of this narrowed claim. Later, stop for explicit one-execution Slice C authorization; after that authorized execution, seal evidence and stop for review. No preliminary model probe, repeated login, Rook MCP, Rhino, or Grasshopper contact is admitted. Accepted A+B evidence remains unchanged.

- [ ] **Step 9: Promote one exact reviewed implementation into the installed product and stop**

Only after sealed Slice C evidence is independently accepted, freeze the
promotion protocol with the exact clean final implementation commit, source and
runtime manifests, verifier hash, exact approved Task 10 Prime payload, absent
evidence root, Release configuration, and MSVC `14.44.35207`.

Before invoking deployment, require the product worktree to be clean at exactly
`$ApprovedImplementationCommit`. Rebuild and validate the private Python runtime
and sealed wheelhouse from that exact source using the existing release
pipeline. Explicitly select `C:/UDEV/Chirp` through the wheelhouse builder's
existing `-ChirpRoot` parameter. Before Python-runtime staging, require that
checkout's `pyproject.toml`, valid Git HEAD, and clean tracked/untracked source.
Do not use the builder's worktree-relative sibling default or modify Chirp to
satisfy these checks. The later `-SkipChirpInstall` flag does not bypass the
wheelhouse's Chirp prerequisite. This must happen before `post_install.py`:
local deployment installs the sealed wheel first and only mirrors current
source afterward, while Prime
promotion imports `prime_runtime_artifact` during post-install. A stale wheel
would therefore break or misdirect promotion even if the later mirror were
correct.

```powershell
Set-Location C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset
$status = @(git status --short)
if ($status.Count -ne 0) { throw 'Promotion source worktree must be clean.' }
if ((git rev-parse HEAD) -ne $ApprovedImplementationCommit) {
    throw 'Promotion source does not match the approved implementation commit.'
}

$chirpRoot = (Resolve-Path -LiteralPath 'C:/UDEV/Chirp' -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath "$chirpRoot/pyproject.toml" -PathType Leaf)) {
    throw 'The selected Chirp checkout is missing pyproject.toml.'
}
$chirpTop = git -C $chirpRoot rev-parse --show-toplevel
if ($LASTEXITCODE -ne 0 -or
    [IO.Path]::GetFullPath($chirpTop) -ine [IO.Path]::GetFullPath($chirpRoot)) {
    throw 'The selected Chirp path is not its Git checkout root.'
}
$chirpCommit = git -C $chirpRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $chirpCommit -cnotmatch '^[0-9a-f]{40}$') {
    throw 'Cannot resolve the selected Chirp source commit.'
}
$chirpStatus = @(git --no-optional-locks -C $chirpRoot status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $chirpStatus.Count -ne 0) {
    throw 'Chirp source worktree must be clean before Python-runtime staging.'
}

$version = '1.5.18'
pwsh -NoProfile -File scripts/python-runtime/stage-rook-python-runtime.ps1
if ($LASTEXITCODE -ne 0) { throw 'Private Python runtime staging failed.' }
pwsh -NoProfile -File scripts/python-runtime/build-rook-python-wheelhouse.ps1 -Version $version -ChirpRoot $chirpRoot
if ($LASTEXITCODE -ne 0) { throw 'Private wheelhouse build failed.' }
pwsh -NoProfile -File scripts/validate-python-wheelhouse.ps1 -Version $version
if ($LASTEXITCODE -ne 0) { throw 'Private wheelhouse validation failed.' }

$pythonManifest = Get-Content -LiteralPath installer/runtime/python-runtime-manifest.json -Raw | ConvertFrom-Json
if ([string]$pythonManifest.rook_git_sha -ne $ApprovedImplementationCommit) {
    throw 'Private wheelhouse source identity differs from the approved implementation commit.'
}
if ([string]$pythonManifest.chirp_git_sha -ne $chirpCommit) {
    throw 'Private wheelhouse Chirp identity differs from the selected clean source.'
}

$primePayload = (Resolve-Path -LiteralPath $ApprovedPrimeRuntimePayload).Path
pwsh -NoProfile -File scripts/deploy-local-testing.ps1 `
    -Configuration Release `
    -VCToolsVersion 14.44.35207 `
    -SkipChirpInstall `
    -PrimeRuntimePayload $primePayload
```

The wheelhouse validator must also confirm its release version and exact
`rook_git_sha` before deployment. Do not use `-SkipBuild`; native and managed
outputs must be built from the frozen commit. Do not use `-UseRepoVenv`; the
deployed chat-service manifest, installed wheel, and installed Python payload
must be the product consumers qualified for Slices D and E. Before execution,
stop for explicit promotion authorization and perform the deployment script's
normal user-controlled Rhino/Rook shutdown prerequisites. Do not add process
discovery or cleanup to the qualification runner.

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
3. Review Task 10 Steps 1-6 as one model-free public-seam implementation gate. No real Prime build, dependency download, installation, or Prime launch is authorized by this review.
4. Review and explicitly authorize Task 10 Step 7 as one named build-attempt WSL build from the literal approved Rook implementation commit. Review both Rook and Prime post-build Git custody and the ZIP hash before any transfer or assembly.
5. Review and explicitly authorize Task 10 Step 8 as one independently named assembly attempt from that same literal Rook implementation commit and approved build-attempt ZIP hash. Review the assembled runtime manifest, runtime ID, exact payload path, and consumer wiring before Task 11. A failed assembly may receive a new assembly-attempt name without repeating the approved build.
6. Review Task 11's ChatRunner non-port and installed-product static gate independently. It may consume the approved staged payload but may not launch Prime.
7. Review Task 12's authored qualification code as the single model-free pre-contact gate covering technical Slices A and B.
8. Review the frozen combined A+B package, then authorize at most one execution.
9. Review sealed A+B evidence before authorizing Slice C.
10. Review sealed C evidence before authorizing one installed-product promotion from the exact final implementation commit and its newly rebuilt sealed Python wheelhouse.
11. Review the sealed promotion identity report before authorizing Slice D.
12. Review sealed D evidence before authorizing Slice E.
13. Review sealed E evidence before any release cutover decision.

## Final Acceptance Checklist

- [ ] One product path exists: C# panel -> authenticated HTTP -> Python ACP SDK -> exact installed Prime `--mode acp --no-daemon --no-approve` -> standard ACP MCP `rook` -> Rook; production omits `--offline`, removes inherited `PI_OFFLINE`, and causally proves direct ACP cannot reach managed helper acquisition.
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
