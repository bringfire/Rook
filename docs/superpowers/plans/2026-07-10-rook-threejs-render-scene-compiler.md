# Rook Three.js Render Scene Compiler Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Slice 1 of the approved Rook Three.js Render Scene Compiler: explicit Create, Update, Relink, customization, recovery, and browser-preview workflows that preserve the authoritative Rhino model, maintain an inspectable derived Rhino render scene, and publish a deterministic Three.js package under the evidence-backed `balanced@1` profile.

**Architecture:** Rook MCP Python owns orchestration, deterministic compilation, transaction journals, local-storage enforcement, and recovery. RookNative remains the sole HTTP server and performs every Rhino SDK operation on Rhino's main thread. The managed Rook companion hosts the embedded WebView2 preview and exposes one versioned native callback. A production-owned Three.js client renders the promoted GLB and returns hash-bound prepare/commit/rollback evidence. Publication uses an acyclic artifact hash graph, two ordered Windows mutexes, optimistic token revalidation, crash-safe retained-conflict storage, and preview-last pointer commit.

**Tech Stack:** Python 3.10+ standard library and existing MCP dependencies; C++17/Rhino 8 C++ SDK; C# targeting `net8.0`, `net7.0`, and `net48`; Microsoft WebView2 `1.0.1938.49`; Node `22.20.0`; npm `10.9.3`; Three.js `0.181.2`; Vite `8.1.4`; Vitest `4.1.10`; Windows Win32 file and mutex APIs.

## Global Constraints

- The approved source of truth is `docs/superpowers/specs/2026-07-10-rook-threejs-render-scene-compiler-design.md` at or after commit `a1330565`. If implementation pressure conflicts with the spec, stop and amend the spec before changing behavior.
- Slice 1 is Windows-only and local-storage-only. Reject UNC paths, mapped remote drives, remote reparse targets, and any project/source/bookkeeping/derived destination not proven to reside on fixed local storage.
- RookNative remains the sole HTTP server. The managed companion is an internal capability provider and must not open a second listener.
- All Rhino SDK reads and writes run on Rhino's main thread. Python never edits `.3dm` bytes directly.
- The authoritative source document is never changed, saved, or closed by the compiler. Create and Update require it to be saved and unmodified.
- The derived Rhino document is inspectable user state. Update requires it saved and closed; failed publication must preserve a saved customization draft exactly.
- Acquire all required destination mutexes in ascending lock-ID order before all required scene mutexes in ascending lock-ID order, and release everything in reverse order. Normal Create/Update/recovery use one destination and one scene lock; Relink acquires old and new destination locks before the scene lock. No code may acquire a destination lock while holding a scene lock.
- The destination mutex ID is `SHA-256(comparisonPathUtf8)`, where `comparisonPath` is the case-insensitive canonical comparison path. Never hash the display path. For a nonexistent first-Create destination, resolve the final target of the deepest existing parent, append every normalized nonexistent component including the filename, normalize separators and case, and hash that result.
- Hold exclusive source protection continuously through every destructive rollback transition. Rehash the protected handle and replace/rename while that handle remains open; there must be no close–rehash–replace interval.
- Implement durable writes with documented Windows primitives. File content is written through a `CreateFileW` handle using `FILE_FLAG_WRITE_THROUGH`, followed by `FlushFileBuffers`; same-directory promotion uses `MoveFileExW` with `MOVEFILE_WRITE_THROUGH`. Do not claim or emulate POSIX directory `fsync`. See [CreateFile](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilea) and [MoveFileEx](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexa).
- Cross-volume conflict retention is copy-first: copy to a temporary file on the conflict volume, flush it, verify its hash, atomically rename it inside `conflicts/`, durably create the retained-data record, durably update the journal, and only then replace the original.
- Implement RFC 8785-compatible canonical JSON in the existing Python package without adding a dependency. Self-hashed records omit their own hash field while hashing.
- The publication hash graph stays acyclic and uses the spec's exact order: execution envelope, profile descriptor, candidate render document, GLB, scene manifest, compilation report, prepared preview evidence, visible preview evidence, scene link, then current pointer. No upstream artifact refers to a downstream hash.
- Preserve exact direct browser dependencies and the tested fixed camera/scene protocol from `codex/threejs-rhino-stress-harness`. Promote code into production-owned modules; production code must not import from `experiments/`.
- Before the first `npm ci`, create `src/Rook/UI/ThreeScene/Client/.gitignore` and prove `node_modules/` is ignored with `git check-ignore`.
- No new Python, native, or managed third-party dependency is authorized by this plan.
- Every task uses red-green-refactor TDD, runs the narrow test first, runs the affected layer before commit, and commits only that task's coherent change.
- Implementation must remain sequential. When using subagents, use a fresh implementation subagent per task, then a specification review and code-quality review gate before beginning the next task. Finish with one whole-branch review.

## Execution Preflight: Isolated Feature Worktree

Before Task 1, invoke `superpowers:using-git-worktrees`. Create the implementation branch from the verified `main`, then merge the reviewed stress-harness branch into the feature branch only:

```text
branch: codex/threejs-render-scene-compiler
worktree: C:/Users/aryan/source/repos/Rook/.worktrees/threejs-render-scene-compiler
reviewed harness branch: codex/threejs-rhino-stress-harness at b707761c
```

- [ ] Verify isolation and create the worktree.

```powershell
cd C:\Users\aryan\source\repos\Rook
git status --short
git check-ignore -v .worktrees/probe
git worktree add .worktrees/threejs-render-scene-compiler -b codex/threejs-render-scene-compiler main
git -C .worktrees/threejs-render-scene-compiler status --short
```

Expected: both status outputs are empty and the ignore probe exits `0`.

- [ ] Merge the reviewed harness history and verify its exact head is present.

```powershell
cd C:\Users\aryan\source\repos\Rook\.worktrees\threejs-render-scene-compiler
git merge --no-ff codex/threejs-rhino-stress-harness -m "merge: include reviewed Three.js stress harness"
git merge-base --is-ancestor b707761c HEAD
git status --short
```

Expected: the ancestor check exits `0`; status is empty. Resolve no semantic conflict by guessing—if a conflict occurs, stop and compare both approved documents before continuing.

All subsequent commands run in the compiler worktree.

## Planned File Structure

```text
mcp_server/src/rook/threejs_scene/
  __init__.py
  canonical.py             # RFC 8785 JSON and hash helpers
  contracts.py             # enums, typed records, error codes
  paths.py                 # display/comparison paths and local-storage policy
  windows_io.py            # injectable Win32 adapter and durable operations
  locks.py                 # destination/scene mutex identities and ordering
  storage.py               # artifact layout, retained conflicts, durable JSON
  journal.py               # promotion phases and deterministic recovery
  profiles.py              # balanced@1 descriptor/envelope validation
  source_client.py         # native source/open-document calls
  semantic.py              # source classification and material signatures
  glb.py                   # deterministic GLB writer
  compiler.py              # derived/GLB/manifest/report candidate construction
  preview_client.py        # native-to-managed preview calls
  orchestrator.py          # Create/Update/Relink/customization/status workflow
  tools.py                 # MCP schemas and thin tool handlers
  resources/
    balanced-1.profile.json
    execution-envelope.json
mcp_server/tests/threejs_scene/
  test_canonical.py
  test_paths.py
  test_windows_io.py
  test_locks.py
  test_storage.py
  test_journal.py
  test_profiles.py
  test_semantic.py
  test_glb.py
  test_compiler.py
  test_preview_client.py
  test_orchestrator.py
  test_tools.py
  test_live.py
mcp_server/tools/threejs_scene_live_harness.py
mcp_server/src/rook/bridge.py

src/RookNative/Handlers/
  ThreeSceneHandler.h
  ThreeSceneHandler.cpp
src/RookNative/RookServer.cpp
src/RookNative/RookNative.vcxproj
src/RookNative/RookNative.vcxproj.filters
src/RookNative/Handlers/GrasshopperProxyHandler.cpp

src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs
src/Rook/UI/ThreeScene/
  ThreeSceneBridgeContracts.cs
  ThreeSceneRuntimeCoordinator.cs
  ThreeSceneWebSurface.cs
  ThreeScenePanel.cs
  Resources/
    index.html
    app.js
    styles.css
  Client/
    .gitignore
    package.json
    package-lock.json
    vite.config.js
    vitest.config.js
    src/
      actor-index.js
      disposal.js
      evidence.js
      glb-loader.js
      preview-state.js
      renderer.js
      main.js
      styles.css
    tests/
      actor-index.test.js
      disposal.test.js
      evidence.test.js
      preview-state.test.js
      renderer.test.js
src/Rook/Rook.csproj
src/Rook/RookPlugin.cs
src/Rook.Tests/UI/ThreeScene/
  ThreeSceneBridgeContractsTests.cs
  ThreeSceneRuntimeCoordinatorTests.cs

scripts/build-threejs-scene-client.ps1
scripts/build_threejs_execution_envelope.py
scripts/run_rhino_runtime_harness.py
scripts/tests/threejs-scene-packaging-guards.tests.ps1
docs/threejs-render-scene.md
```

## Stable Interfaces

Implement these names once and keep later tasks aligned with them:

Runtime artifact layout is exact:

```text
.rook/render-scenes/<sceneId>/
  scene-link.json
  current.json
  promotion.json
  conflicts/<conflictId>/
    preserved.3dm
    conflict-record.json
  runs/<runId>/
    candidate.render.3dm
    candidate.scene-link.json
    profile-descriptor.json
    execution-envelope.json
    scene.glb
    scene.manifest.json
    compilation-report.json
    preview-prepared-evidence.json
    preview-visible-evidence.json
```

Completed run directories are immutable. The user-facing derived path is a replaceable working copy of `candidate.render.3dm`; it may diverge only as an explicit saved customization draft.

```python
# contracts.py
class Operation(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    RELINK = "relink"

class JournalPhase(str, Enum):
    PREPARED = "prepared"
    CONFLICT_RETAINED = "conflict_retained"
    RENDER_PROMOTED = "render_promoted"
    RENDER_OPEN_CONFLICT = "render_open_conflict"
    PREVIEW_EVIDENCED = "preview_evidenced"
    LINK_FINALIZED = "link_finalized"
    LINK_PROMOTED = "link_promoted"
    CURRENT_READY = "current_ready"
    CURRENT_PROMOTED = "current_promoted"

@dataclass(frozen=True)
class CanonicalPath:
    display: str
    comparison: str
    volume_root: str

@dataclass(frozen=True)
class BaseTokens:
    current_run_id: str | None
    scene_link_hash: str | None
    source_fingerprint: str
    working_document_hash: str | None
    draft_id: str | None
    draft_revision: int | None
    draft_base_run_id: str | None

class ThreeSceneError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Mapping[str, object] | None = None):
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})
```

```cpp
// ThreeSceneHandler.h
class ThreeSceneHandler {
public:
  static httplib::Response OpenDocuments(const httplib::Request& request);
  static httplib::Response CaptureSource(const httplib::Request& request);
  static httplib::Response BuildCandidate(const httplib::Request& request);
  static httplib::Response ApplyCustomization(const httplib::Request& request);
  static httplib::Response Preview(const httplib::Request& request);
};
```

```csharp
// NativeGhBridgeRegistrar.cs and ThreeSceneBridgeContracts.cs
internal const int BridgeAbiVersion = 18;
internal delegate IntPtr ThreeSceneDispatchDelegate(IntPtr requestJsonUtf8);

internal sealed record PreviewRequest(
    string Operation,
    string SceneId,
    string RunId,
    string? ManifestPath,
    string? ManifestHash,
    string? PriorRunId);

internal sealed record PreviewEvidence(
    bool Ok,
    string Operation,
    string SceneId,
    string? RunId,
    string? ManifestHash,
    string? VisibleGlbHash,
    string? ErrorCode,
    string? ErrorMessage);
```

Native HTTP contract:

```text
GET  /three-scene/open-documents
POST /three-scene/capture-source
POST /three-scene/build-candidate
POST /three-scene/customization
POST /three-scene/preview
```

MCP tool contract:

```text
rook_create_render_scene
rook_update_render_scene
rook_relink_render_scene
rook_stage_render_customization
rook_get_render_scene_status
rook_recover_render_scene
rook_review_preserved_conflict
rook_acknowledge_preserved_conflict
rook_delete_preserved_conflict
```

## Task 1: Canonical Contracts, Hashes, and the `balanced@1` Envelope

**Files:**

- Create: `mcp_server/src/rook/threejs_scene/__init__.py`
- Create: `mcp_server/src/rook/threejs_scene/contracts.py`
- Create: `mcp_server/src/rook/threejs_scene/canonical.py`
- Create: `mcp_server/src/rook/threejs_scene/profiles.py`
- Create: `mcp_server/src/rook/threejs_scene/resources/balanced-1.profile.json`
- Create: `mcp_server/src/rook/threejs_scene/resources/execution-envelope.json`
- Create: `mcp_server/tests/threejs_scene/test_canonical.py`
- Create: `mcp_server/tests/threejs_scene/test_profiles.py`
- Create: `scripts/build_threejs_execution_envelope.py`

- [ ] Write failing canonicalization tests covering sorted object keys, UTF-8 text, escaped controls, integer/finite-float formatting, rejection of NaN/infinity, and self-hash omission.

```python
def test_self_hash_omits_only_declared_field() -> None:
    payload = {"schemaVersion": 1, "overrides": {"actor-1": "mat-1"}, "registrySha256": "old"}
    digest = hash_canonical_object(payload, omit=frozenset({"registrySha256"}))
    assert digest == hashlib.sha256(
        canonical_bytes({"schemaVersion": 1, "overrides": {"actor-1": "mat-1"}})
    ).hexdigest()

@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_are_rejected(value: float) -> None:
    with pytest.raises(CanonicalJsonError, match="finite"):
        canonical_bytes({"value": value})
```

- [ ] Run the tests and observe the import failure.

```powershell
python -m pytest mcp_server/tests/threejs_scene/test_canonical.py -q
```

Expected: `ModuleNotFoundError` or missing-symbol failures.

- [ ] Implement deterministic canonical bytes and SHA-256 helpers. Encode each string with `json.dumps(value, ensure_ascii=False, separators=(",", ":"))`; recursively sort object keys by Unicode code point; reject non-string keys and non-finite values; format numeric values according to the RFC 8785/ECMAScript number rules exercised by the test vectors. `hash_canonical_object` must construct a new mapping without the named top-level fields and must never mutate its caller.

- [ ] Write failing profile tests asserting exact `balanced@1` content, immutable profile/envelope hashes, Node/npm/Three/Vite/Vitest versions, renderer color/tone/camera settings, static-context-only optimization, and ordinary meshes for actors.

```python
def test_balanced_profile_rejects_any_component_drift(tmp_path: Path) -> None:
    descriptor, envelope = load_bundled_profile()
    changed = dataclasses.replace(envelope, three_version="0.181.3")
    with pytest.raises(ThreeSceneError) as error:
        verify_execution_contract(descriptor, changed)
    assert error.value.code == "execution_envelope_mismatch"
```

- [ ] Implement `ProfileDescriptor`, `ExecutionEnvelope`, `load_bundled_profile()`, and `verify_execution_contract()`. Generate the two checked-in JSON resources with `scripts/build_threejs_execution_envelope.py`; generation must take explicit version inputs, serialize canonically, embed component hashes, and produce identical bytes on two runs.

- [ ] Run the narrow suite and reproducibility probe.

```powershell
python -m pytest mcp_server/tests/threejs_scene/test_canonical.py mcp_server/tests/threejs_scene/test_profiles.py -q
$before = (Get-FileHash mcp_server/src/rook/threejs_scene/resources/*.json -Algorithm SHA256).Hash
python scripts/build_threejs_execution_envelope.py --node 22.20.0 --npm 10.9.3 --three 0.181.2 --vite 8.1.4 --vitest 4.1.10
$after = (Get-FileHash mcp_server/src/rook/threejs_scene/resources/*.json -Algorithm SHA256).Hash
Compare-Object $before $after
```

Expected: tests pass and `Compare-Object` prints nothing.

- [ ] Commit.

```powershell
git add mcp_server/src/rook/threejs_scene mcp_server/tests/threejs_scene scripts/build_threejs_execution_envelope.py
git commit -m "feat: define Three.js scene contracts and profile"
```

## Task 2: Canonical Windows Paths, Local Storage, and Ordered Mutexes

**Files:**

- Create: `mcp_server/src/rook/threejs_scene/paths.py`
- Create: `mcp_server/src/rook/threejs_scene/windows_io.py`
- Create: `mcp_server/src/rook/threejs_scene/locks.py`
- Create: `mcp_server/tests/threejs_scene/test_paths.py`
- Create: `mcp_server/tests/threejs_scene/test_windows_io.py`
- Create: `mcp_server/tests/threejs_scene/test_locks.py`

- [ ] Write failing path tests for existing files, mixed case, `.`/`..`, symlink/junction final targets, long-path prefixes, a nonexistent filename under an existing parent, multiple nonexistent parent components, UNC input, mapped remote drives, and remote reparse targets.

```python
def test_first_create_mutex_hashes_comparison_path_not_display_path(fake_win32) -> None:
    fake_win32.final_path = r"C:\Project"
    upper = canonicalize_target(r"C:\Project\Render\Scene.3dm", fake_win32)
    lower = canonicalize_target(r"c:\project\render\scene.3DM", fake_win32)
    assert upper.display != lower.display
    assert upper.comparison == lower.comparison
    assert destination_mutex_name(upper) == destination_mutex_name(lower)
    material = canonical_bytes({
        "contract": "derived-path-lock@2",
        "derivedPath": upper.comparison,
    })
    assert destination_mutex_name(upper).endswith(hashlib.sha256(material).hexdigest())
```

- [ ] Implement `canonicalize_target(path, win32) -> CanonicalPath` by walking upward to the deepest existing parent, resolving that parent's final target through a handle, appending normalized missing components, applying Windows separator and extended-prefix normalization, and deriving a case-folded comparison string separately from the user-facing display string. Implement `require_local_fixed_storage()` with drive type, UNC, volume, and reparse-target checks; every rejection must use `shared_scene_storage_unsupported` and occur before capture or candidate construction.

- [ ] Write failing mutex tests proving all of the following:

  - two projects and two provisional scene IDs targeting the same path get the same destination mutex;
  - display-case variants and nonexistent filenames get the same destination mutex;
  - different destinations do not collide;
  - scene locks differ by canonical project root plus scene ID;
  - acquisition order is destination then scene and release is scene then destination;
  - Relink sorts and acquires both destination locks before its scene lock;
  - recovery uses the same destination lock;
  - concurrent first Creates serialize even with different scene IDs;
  - concurrent recovery and Update serialize.

- [ ] Implement named mutexes through an injectable Win32 adapter using `CreateMutexW`, `WaitForSingleObject`, `ReleaseMutex`, and `CloseHandle`. Use these identities exactly:

```python
def destination_mutex_name(path: CanonicalPath) -> str:
    material = canonical_bytes({
        "contract": "derived-path-lock@2",
        "derivedPath": path.comparison,
    })
    return rf"Global\Rook.ThreeScene.Destination.{hashlib.sha256(material).hexdigest()}"

def scene_mutex_name(project_root: CanonicalPath, scene_id: str) -> str:
    material = canonical_bytes({
        "contract": "render-scene-lock@1",
        "projectRoot": project_root.comparison,
        "sceneId": scene_id,
    })
    return rf"Global\Rook.ThreeScene.Scene.{hashlib.sha256(material).hexdigest()}"
```

- [ ] Write failing Win32 durability tests around a recording fake. Require call order `CreateFileW(FILE_FLAG_WRITE_THROUGH) → WriteFile → FlushFileBuffers → CloseHandle → MoveFileExW(MOVEFILE_WRITE_THROUGH)`. Add a negative test that fails closed when file write-through, file flush, or write-through rename is unavailable; no test may require or claim POSIX directory `fsync`. If a filesystem rejects `FlushFileBuffers` on a directory handle opened with `FILE_FLAG_BACKUP_SEMANTICS`, use the documented write-through rename plus reopen/hash verification and record directory flushing as unsupported rather than pretending it succeeded.

- [ ] Implement the narrow `Win32Io` adapter with `ctypes`, typed handle ownership, last-error propagation, write-through temporary-file creation, file flushing, same-directory write-through rename, protected-handle rename through `SetFileInformationByHandle`, final-path lookup, volume identity, and local-drive checks. Keep OS calls behind the adapter so pure tests run without Rhino.

- [ ] Run the layer.

```powershell
python -m pytest mcp_server/tests/threejs_scene/test_paths.py mcp_server/tests/threejs_scene/test_windows_io.py mcp_server/tests/threejs_scene/test_locks.py -q
```

Expected: all tests pass.

- [ ] Commit.

```powershell
git add mcp_server/src/rook/threejs_scene/paths.py mcp_server/src/rook/threejs_scene/windows_io.py mcp_server/src/rook/threejs_scene/locks.py mcp_server/tests/threejs_scene
git commit -m "feat: enforce local Windows scene storage locks"
```

## Task 3: Durable Artifact Storage, Retained Conflicts, and Recovery Journal

**Files:**

- Create: `mcp_server/src/rook/threejs_scene/storage.py`
- Create: `mcp_server/src/rook/threejs_scene/journal.py`
- Create: `mcp_server/tests/threejs_scene/test_storage.py`
- Create: `mcp_server/tests/threejs_scene/test_journal.py`

- [ ] Write failing tests for the exact project layout, create-new attempt directories, durable canonical JSON, draft-registry self-hash omission, acyclic publication finalization, retained-user-data classification, and cleanup exclusion.

- [ ] Define the acyclic finalization order in executable code and tests:

```text
1. execution-envelope.json, whose `executionEnvelopeSha256` field is omitted from its own canonical hash input
2. profile descriptor, whose `descriptorSha256` field is omitted from its own canonical hash input and which records the envelope identity
3. candidate.3dm, containing stable IDs/source/version/committed bookkeeping but no downstream publication hash
4. scene.glb, containing scene identity but no downstream publication hash
5. scene-manifest.json, recording descriptor, envelope, candidate-document, and GLB hashes
6. compilation-report.json, recording the manifest hash
7. preview-prepared-evidence.json, recording the report and all finalized content hashes through the report
8. preview-visible-evidence.json, created only after preview commit and recording the prepared-evidence hash plus run/package/profile/envelope identities
9. candidate.scene-link.json, recording every finalized hash through visible evidence but never its own hash
10. current.json, recording only `sceneId`, `runId`, and the finalized scene-link hash
```

No artifact may point forward or to itself. The candidate render document is finalized before the GLB and is hashed by the later manifest and scene link; it therefore must not embed the scene-link hash. Preview evidence, scene link, and current pointer have no self-hash field. The draft customization registry is separate publication input and computes `registrySha256` with that field omitted.

- [ ] Write cross-volume retained-conflict fault-injection tests after each transition: temporary created, copy flushed, hash verified, retained file renamed, retained record flushed, journal flushed, original replacement begun, original replacement complete. Before the journal reaches `CONFLICT_RETAINED`, recovery must leave the original untouched and may delete only incomplete temporary copies. At and after `CONFLICT_RETAINED`, recovery must preserve both the retained bytes and record until explicit user acknowledgement.

- [ ] Implement `retain_conflict()` using this order and no cross-volume move:

```text
open original with `GENERIC_READ | DELETE`, share only `FILE_SHARE_READ`, and keep that handle open
copy bytes to CREATE_NEW temp on conflicts volume
FlushFileBuffers(temp)
hash temp and compare with hash read from protected source handle
MoveFileExW(temp, retained, MOVEFILE_WRITE_THROUGH)
write-through retained-record.json and verify its hash
write-through promotion.json with retained path/hash/record hash
rehash the still-open source handle
rename the protected original to an attempt quarantine name through that same handle
MoveFileExW the exact prior bytes into the destination with MOVEFILE_WRITE_THROUGH
reopen and hash the restored destination
close the protected handle only after replacement and postcondition checks
```

Using the original handle for the first rename avoids granting a close–rehash–replace window. The injected adapter test must assert `close(protected_source)` occurs after `rename_open_file`, `replace_destination`, and restored-byte verification; any implementation that closes before the destructive transition finishes fails. Fault injection between protected rename and prior-byte installation must recover from the journal/quarantine state without losing the verified retained copy.

- [ ] Implement `PromotionJournal`, `JournalPhase`, `PublicationHashes`, `RetainedConflict`, `write_durable_json()`, `advance_phase()`, `recover_transaction()`, and explicit cleanup classes: `attempt_temporary`, `promoted_publication`, and `retained_user_data`. Automatic cleanup may delete only `attempt_temporary` files proven to belong to the attempt.

- [ ] Add table-driven Create and Update recovery tests for every durable phase. Each case must converge to either the complete candidate publication or the exact prior state; first Create restores absence, while Update restores exact prior working bytes, pointers, and preview. Recovery must reacquire destination then scene locks.

- [ ] Run the tests.

```powershell
python -m pytest mcp_server/tests/threejs_scene/test_storage.py mcp_server/tests/threejs_scene/test_journal.py -q
```

Expected: all tests pass, including every fault point.

- [ ] Commit.

```powershell
git add mcp_server/src/rook/threejs_scene/storage.py mcp_server/src/rook/threejs_scene/journal.py mcp_server/tests/threejs_scene
git commit -m "feat: add crash-safe scene publication storage"
```

## Task 4: Native Open-Document Discovery and Immutable Source Capture

**Files:**

- Create: `src/RookNative/Handlers/ThreeSceneHandler.h`
- Create: `src/RookNative/Handlers/ThreeSceneHandler.cpp`
- Modify: `src/RookNative/RookServer.cpp`
- Modify: `src/RookNative/RookNative.vcxproj`
- Modify: `src/RookNative/RookNative.vcxproj.filters`
- Create: `mcp_server/src/rook/threejs_scene/source_client.py`
- Modify: `mcp_server/src/rook/bridge.py`
- Create: `mcp_server/tests/threejs_scene/test_source_client.py`
- Modify: `mcp_server/tests/test_server.py`

- [ ] Write Python contract tests first. `GET /three-scene/open-documents` must return every document open in that Rhino process with canonical saved path, runtime serial, modified flag, scene ID, and published run ID. `POST /three-scene/capture-source` must reject untitled/modified/path-mismatched documents and return a versioned capture path, SHA-256, source fingerprint, units, absolute tolerance, object/layer/material metadata, stable Rhino object UUIDs, and main-thread evidence.

- [ ] Add source-level guard tests that locate all five routes in `RookServer.cpp`, assert `ThreeSceneHandler` is included in both project files, and assert each Rhino-touching handler enters the repository's main-thread invocation helper before accessing `CRhinoDoc`.

- [ ] Implement the handler registration and C++ DTO validation. Add the explicit `.vcxproj` and `.filters` entries because this task intentionally introduces a focused native handler. Do not change unrelated project settings.

- [ ] Implement open-document enumeration and source capture on Rhino's main thread. Capture immutable JSON metadata and a save-copy/source snapshot into the caller-supplied attempt directory without changing the source path, modified flag, selection, undo stack, or active document. Record pre/post source identity in the response and fail if either changes.

- [ ] Extend the existing `bridge.py` native request boundary and implement `NativeSceneClient` over it. Reuse current discovery, authentication, timeout, and HTTP error normalization. It must query every discovered Rhino instance for open documents, not only the active port, and normalize native errors to `ThreeSceneError` codes.

- [ ] Run unit/source guards, then build native.

```powershell
python -m pytest mcp_server/tests/threejs_scene/test_source_client.py mcp_server/tests/test_server.py -q
.\build_native.ps1 -Configuration Debug
```

Expected: Python tests pass and `RookNative.rhp` builds successfully.

- [ ] Commit.

```powershell
git add src/RookNative mcp_server/src/rook/bridge.py mcp_server/src/rook/threejs_scene/source_client.py mcp_server/tests
git commit -m "feat: capture immutable Rhino scene sources"
```

## Task 5: Native Derived Candidate Sync and Customization Staging

**Files:**

- Modify: `src/RookNative/Handlers/ThreeSceneHandler.cpp`
- Create: `mcp_server/tests/threejs_scene/test_candidate_contract.py`
- Create: `src/Rook.Tests/UI/ThreeScene/ThreeSceneNativeContractSourceTests.cs`

- [ ] Write contract/source tests for `POST /three-scene/build-candidate` and `POST /three-scene/customization`. Candidate construction must consume the captured source, prior closed working derived file, base run, and draft registry; return a new attempt-owned `.3dm`, object mapping, material mapping, pivot/units evidence, and candidate hash; and never write the publication destination. Customization must validate active canonical path and base run, apply markers plus draft registry in one undo record, mark the derived document modified/stale, and never save it or edit committed scene-link files.

- [ ] Add integration seams for an injected `CandidateFaultPoint` after source import, identity mapping, customization application, and candidate save. Every failure must delete only attempt-owned candidate state and leave source/working/publication bytes unchanged.

- [ ] Implement main-thread sync with stable source UUID identity. Preserve one source object to one ordinary actor object, preserve governed layer/material semantics, apply explicit tombstones and material overrides only when their marker/draft/base-run contracts match, and keep unsupported edits out of the candidate with a structured diagnostic.

- [ ] Implement customization actions `set_material_override`, `clear_material_override`, `adopt_material_override`, `remove_actor`, and `restore_actor`. Validate duplicate/malformed IDs with detailed object paths and IDs. Wrap registry plus object-user-string changes in one Rhino undo record.

- [ ] Add source tests that reject direct `WriteFile`/publication-path replacement in the native candidate handler and reject any Rhino SDK access outside the main-thread block.

- [ ] Run tests and native/managed builds.

```powershell
python -m pytest mcp_server/tests/threejs_scene/test_candidate_contract.py -q
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Release -f net8.0 --filter ThreeSceneNativeContractSourceTests
.\build_native.ps1 -Configuration Debug
```

Expected: all tests and builds pass.

- [ ] Commit.

```powershell
git add src/RookNative/Handlers/ThreeSceneHandler.cpp src/Rook.Tests/UI/ThreeScene mcp_server/tests/threejs_scene
git commit -m "feat: build derived Rhino scene candidates"
```

## Task 6: Semantic Classification, Deterministic GLB, and Package Compiler

**Files:**

- Create: `mcp_server/src/rook/threejs_scene/semantic.py`
- Create: `mcp_server/src/rook/threejs_scene/glb.py`
- Create: `mcp_server/src/rook/threejs_scene/compiler.py`
- Create: `mcp_server/tests/threejs_scene/test_semantic.py`
- Create: `mcp_server/tests/threejs_scene/test_glb.py`
- Create: `mcp_server/tests/threejs_scene/test_compiler.py`

- [ ] Write semantic tests for actors, static context, excluded objects, repeated geometry evidence, batchable-report-only evidence, canonical material signatures, layer/material overrides, tombstones, malformed/duplicate actor IDs, and unsupported Rhino data. Classification must be deterministic under source enumeration shuffles.

- [ ] Write GLB tests that parse the output independently, assert `extras.rook.actorId` identity, one ordinary Three.js actor node per actor, shared geometry evidence where legal, equal visual material parameters per source signature, units/axis transforms, source/rebase/applied-render-offset separation, off-axis pivot preservation, and byte-identical repeated generation.

- [ ] Implement a standards-oriented GLB writer in `rook.threejs_scene.glb`; do not reuse the purpose-specific `mesh2splat` writer. Emit JSON and BIN chunks with deterministic ordering, four-byte alignment, normalized accessors, explicit bounds, and no runtime-network references.

- [ ] Write package compiler tests proving:

  - static context is actually merged by compatible material while actor meshes remain ordinary nodes;
  - merged and unbatched context render equivalently in the fixed-camera pixel comparator promoted from the stress harness;
  - fixed-camera coordinate precision meets the approved threshold;
  - manifest/report/actor map/profile/envelope hashes follow the approved acyclic chain;
  - descriptor, envelope, and customization-draft self-hash fields are omitted from their own canonical hash inputs;
  - the scene link hashes the already-final candidate derived document and every finalized artifact through visible evidence, but never hashes itself, the current pointer, journal, temporary files, or backups;
  - arbitrary local GLBs report pivot validation `unavailable`, while synthetic fixtures require it;
  - compiler cancellation/failure stops immediately and disposes attempt allocations.

- [ ] Implement `compile_package(capture, candidate_evidence, profile, attempt) -> CompiledPackage`. Keep compiler results pure until storage promotes them. Include provenance, filename/size/SHA-256, actor/source IDs, geometry-sharing evidence, optimization decisions, precision evidence, exclusions, warnings, and exact execution-envelope identity.

- [ ] Run the full compiler suite twice and compare fixture hashes.

```powershell
python -m pytest mcp_server/tests/threejs_scene/test_semantic.py mcp_server/tests/threejs_scene/test_glb.py mcp_server/tests/threejs_scene/test_compiler.py -q
python -m pytest mcp_server/tests/threejs_scene/test_glb.py::test_fixture_is_byte_deterministic -q
git diff --check
```

Expected: all tests pass and the diff check is clean.

- [ ] Commit.

```powershell
git add mcp_server/src/rook/threejs_scene mcp_server/tests/threejs_scene
git commit -m "feat: compile deterministic Three.js scene packages"
```

## Task 7: Production Three.js Preview Client

**Files:**

- Create: `src/Rook/UI/ThreeScene/Client/.gitignore`
- Create: `src/Rook/UI/ThreeScene/Client/package.json`
- Create: `src/Rook/UI/ThreeScene/Client/package-lock.json`
- Create: `src/Rook/UI/ThreeScene/Client/vite.config.js`
- Create: `src/Rook/UI/ThreeScene/Client/vitest.config.js`
- Create: `src/Rook/UI/ThreeScene/Client/src/actor-index.js`
- Create: `src/Rook/UI/ThreeScene/Client/src/disposal.js`
- Create: `src/Rook/UI/ThreeScene/Client/src/evidence.js`
- Create: `src/Rook/UI/ThreeScene/Client/src/glb-loader.js`
- Create: `src/Rook/UI/ThreeScene/Client/src/preview-state.js`
- Create: `src/Rook/UI/ThreeScene/Client/src/renderer.js`
- Create: `src/Rook/UI/ThreeScene/Client/src/main.js`
- Create: `src/Rook/UI/ThreeScene/Client/src/styles.css`
- Create: `src/Rook/UI/ThreeScene/Client/tests/*.test.js`
- Create: `src/Rook/UI/ThreeScene/Resources/index.html`
- Create: `src/Rook/UI/ThreeScene/Resources/app.js`
- Create: `src/Rook/UI/ThreeScene/Resources/styles.css`

- [ ] Create `.gitignore` before installing anything:

```gitignore
node_modules/
coverage/
.vite/
```

- [ ] Prove the dependency directory is ignored.

```powershell
New-Item -ItemType Directory -Force src/Rook/UI/ThreeScene/Client/node_modules | Out-Null
New-Item -ItemType File -Force src/Rook/UI/ThreeScene/Client/node_modules/.probe | Out-Null
git check-ignore -v src/Rook/UI/ThreeScene/Client/node_modules/.probe
Remove-Item -LiteralPath src/Rook/UI/ThreeScene/Client/node_modules/.probe
Remove-Item -LiteralPath src/Rook/UI/ThreeScene/Client/node_modules
```

Expected: `git check-ignore` exits `0` and names the client `.gitignore`.

- [ ] Add exact package metadata: `packageManager: npm@10.9.3`, engines `node >=22.12.0 <23`, `three: 0.181.2`, `vite: 8.1.4`, `vitest: 4.1.10`. Only now run `npm install --package-lock-only`, followed by `npm ci`.

- [ ] Write failing tests for the state machine:

```text
empty -> prepared(candidate) -> committed(candidate)
committed(prior) -> prepared(candidate) -> discarded -> committed(prior)
committed(prior) -> prepared(candidate) -> committed(candidate) -> restored(prior)
empty -> prepared(candidate) -> committed(candidate) -> restoreEmpty -> empty
```

Require exact scene/run/manifest/GLB hashes on every transition. A stale, duplicate, or out-of-order request must fail without changing visible state.

- [ ] Promote and adapt reviewed harness primitives into production-owned modules. `GLTFLoader` must validate every expected actor ID, reject duplicates/malformed IDs with node paths, retain ordinary actor meshes, prove geometry sharing, use fixed renderer/color/tone/camera settings, dispose preview candidates before new trial allocation, and clear all GPU samples after a disjoint event. Do not import `experiments/`.

- [ ] Implement `window.chrome.webview` message handling for `prepare`, `commit`, `discard`, `restore`, `restoreEmpty`, and `status`. Load promoted files only through the managed virtual-resource mapping. Return evidence only after the requested scene is visibly rendered and a frame has completed.

- [ ] Run tests and production build.

```powershell
Push-Location src/Rook/UI/ThreeScene/Client
npm ci
npm test -- --run
npm run build
Pop-Location
```

Expected: tests pass and the deterministic Vite output contains no external URL/runtime fetch dependency.

- [ ] Commit source, lockfile, and generated embedded assets only; do not commit `node_modules`.

```powershell
git add src/Rook/UI/ThreeScene/Client src/Rook/UI/ThreeScene/Resources
git commit -m "feat: add production Three.js scene preview client"
```

## Task 8: Managed WebView2 Surface and Versioned Native Preview Bridge

**Files:**

- Create: `src/Rook/UI/ThreeScene/ThreeSceneBridgeContracts.cs`
- Create: `src/Rook/UI/ThreeScene/ThreeSceneRuntimeCoordinator.cs`
- Create: `src/Rook/UI/ThreeScene/ThreeSceneWebSurface.cs`
- Create: `src/Rook/UI/ThreeScene/ThreeScenePanel.cs`
- Modify: `src/Rook/Rook.csproj`
- Modify: `src/Rook/RookPlugin.cs`
- Modify: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`
- Modify: `src/RookNative/Handlers/ThreeSceneHandler.cpp`
- Create: `src/Rook.Tests/UI/ThreeScene/ThreeSceneBridgeContractsTests.cs`
- Create: `src/Rook.Tests/UI/ThreeScene/ThreeSceneRuntimeCoordinatorTests.cs`

- [ ] Write managed tests for strict JSON validation, main-UI-thread dispatch, panel-not-ready errors, timeouts, WebView process failure, hash-bound prepare/commit/rollback, candidate disposal, idempotent retry, and prior/empty restoration.

- [ ] Write ABI parity source tests that fail until both native and managed sides declare ABI `18`, append exactly one `ThreeSceneDispatch` callback without reordering prior ABI fields, and expose bridge readiness through existing capability diagnostics.

- [ ] Implement `ThreeSceneWebSurface` using the existing `RookWebSurface` embedded-resource, CSP, WebMessage, and process-failure patterns. Map only the selected run directory to a randomized virtual host; deny navigation/network beyond embedded resources and that mapping.

- [ ] Implement `ThreeSceneRuntimeCoordinator` as the sole managed state owner. It opens/focuses `ThreeScenePanel`, serializes requests, forwards messages to the browser, validates matching response IDs and hashes, and retains the prior committed descriptor until pointer commit allows cleanup.

- [ ] Register the panel in `RookPlugin`, embed `UI\ThreeScene\Resources\**\*` in `Rook.csproj`, bump ABI to 18 on both sides, and route `/three-scene/preview` through the native callback. The native side must return `companion_unavailable`, `bridge_abi_mismatch`, or structured preview evidence; it must not host WebView2 itself.

- [ ] Run managed tests, all target builds, and native build.

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Release -f net8.0 --filter ThreeScene
dotnet build src/Rook/Rook.csproj -c Release
.\build_native.ps1 -Configuration Debug
```

Expected: tests pass; `net8.0`, `net7.0`, and `net48` companion outputs build; native builds.

- [ ] Commit.

```powershell
git add src/Rook src/Rook.Tests/UI/ThreeScene src/RookNative/Handlers
git commit -m "feat: host transactional Three.js preview in Rook"
```

## Task 9: Transaction Orchestrator for Create and Update

**Files:**

- Create: `mcp_server/src/rook/threejs_scene/preview_client.py`
- Create: `mcp_server/src/rook/threejs_scene/orchestrator.py`
- Create: `mcp_server/tests/threejs_scene/test_preview_client.py`
- Create: `mcp_server/tests/threejs_scene/test_orchestrator.py`

- [ ] Write a fake-driven orchestrator test matrix for first Create, normal Update, no-op Update, construction failure, probe failure, cancellation, open derived document, modified source, source Save As, working-document drift, scene-link drift, draft drift, preview failure, pointer failure, and restart recovery at every journal phase.

- [ ] Add race tests that pause immediately before journaling, mutate each optimistic token, then resume. Under destination/scene locks, revalidate all of these immediately before writing the journal:

```text
current run ID
scene-link/current pointer hashes
source canonical path and fingerprint
source saved/modified state
working-derived document hash
customization draft ID, revision, base run ID, and hash
profile descriptor and execution-envelope hashes
open-document enumeration across every discovered Rhino instance
```

Every mutation must produce a specific conflict error and no publication change.

- [ ] Add the TOCTOU open-window test. Inject a Rhino open after the pre-promotion enumeration and before replacement. The orchestrator must perform the journaled post-replacement enumeration before preview/pointer commit; if the derived path is now open, it rolls back the exact prior bytes and preview under the same locks.

- [ ] Implement `PreviewClient` and `RenderSceneOrchestrator.create/update`. Lifecycle order is exact:

```text
recover under destination+scene locks
validate and capture source
construct candidate outside promotion locks
prepare preview candidate
acquire destination then scene locks
revalidate every base token and open-document state
write PREPARED journal with only currently final hashes
retain unexpected destination bytes if required
promote derived and package artifacts
repeat open-document enumeration; rollback if opened
commit preview and durably write preview-visible evidence
write current pointer last
mark journal complete and clean attempt temporaries
release scene then destination locks
```

Guard the initial protocol/capability probe inside the attempt lifecycle. Probe failure returns an aborted result with no candidate construction or disposal call. After abort/cancellation, return immediately and schedule no more scene work.

- [ ] Ensure preview-visible evidence is absent from the initial journal and is added only after browser commit. Ensure journal expected hashes are phase-local, not future-dependent.

- [ ] Run the tests with race repetitions.

```powershell
python -m pytest mcp_server/tests/threejs_scene/test_preview_client.py mcp_server/tests/threejs_scene/test_orchestrator.py -q
1..10 | ForEach-Object {
  python -m pytest mcp_server/tests/threejs_scene/test_orchestrator.py -q
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

- [ ] Commit.

```powershell
git add mcp_server/src/rook/threejs_scene mcp_server/tests/threejs_scene
git commit -m "feat: orchestrate atomic render scene publication"
```

## Task 10: Relink, Customization Actions, Status, and MCP Tools

**Files:**

- Create: `mcp_server/src/rook/threejs_scene/tools.py`
- Modify: `mcp_server/src/rook/threejs_scene/orchestrator.py`
- Modify: `mcp_server/src/rook/server.py`
- Create: `mcp_server/tests/threejs_scene/test_tools.py`
- Modify: `mcp_server/tests/test_server.py`

- [ ] Write tool-schema tests for the nine public tools named in Stable Interfaces. Require explicit project root and derived path on Create; require existing scene identity on Update; require explicit candidate source and UUID-intersection confirmation on Relink; require an operation enum plus scene/base-run/object/material identifiers for customization staging; and require conflict ID plus recorded hash for acknowledgement/deletion.

- [ ] Write behavior tests for case-only path equivalence, real Save As requiring Relink, zero UUID intersection rejection, open/modified candidate rejection, stale draft rejection, override adoption, source-material change preservation, override clearing back to source inheritance, actor tombstone/restore, and retained-conflict acknowledgement.

- [ ] Implement thin MCP handlers in `tools.py`; add registrations and dispatch cases in `server.py` following existing Director tool patterns. Keep orchestration in `RenderSceneOrchestrator`, not in the registry file.

- [ ] Return user-oriented structured status with `current`, `stale_source`, `saved_customization_draft`, `recovery_required`, `retained_conflict`, `preview_state`, hashes, and exact next action. Never report a failed publication as current merely because the working draft exists.

- [ ] Implement explicit retained-conflict acknowledgement. It records the acknowledgement durably before eligible cleanup; no automatic path may delete retained user data.

- [ ] Run the MCP layer.

```powershell
python -m pytest mcp_server/tests/threejs_scene/test_tools.py mcp_server/tests/test_server.py -q
```

Expected: tool schemas and dispatch tests pass.

- [ ] Commit.

```powershell
git add mcp_server/src/rook/threejs_scene mcp_server/src/rook/server.py mcp_server/tests
git commit -m "feat: expose render scene compiler tools"
```

## Task 11: Build, Packaging, and Installed-Runtime Guards

**Files:**

- Create: `scripts/build-threejs-scene-client.ps1`
- Create: `scripts/tests/threejs-scene-packaging-guards.tests.ps1`
- Modify: `scripts/deploy-local-testing.ps1`
- Modify: `install.ps1`
- Modify: `installer/RookSetup.iss`
- Modify: `scripts/tests/release-installer-guards.tests.ps1`
- Modify: `scripts/tests/deploy-local-testing-guards.tests.ps1`

- [ ] Write PowerShell guard tests first. They must require the client build before companion build/package, all generated preview resources embedded in each target, profile/envelope resources included in the installed MCP package, no `node_modules` in payloads, exact dependency versions, and installed-runtime—not repository-source—resolution.

- [ ] Implement `build-threejs-scene-client.ps1` with Node/npm version checks, `npm ci`, `npm test -- --run`, deterministic `npm run build`, copied outputs to `UI/ThreeScene/Resources`, and a dirty-output failure if a second build changes bytes.

- [ ] Wire client generation into source install, local testing deployment, and release packaging before `dotnet build`. Since resources are embedded in `Rook.rhp`, do not add a parallel loose web payload. Ensure the Python package resource JSON files are carried by the existing MCP directory packaging.

- [ ] Extend installer/deploy guards rather than weakening existing release checks. Do not change version numbers as part of this feature plan.

- [ ] Run packaging guards and builds.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/threejs-scene-packaging-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/deploy-local-testing-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-installer-guards.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-threejs-scene-client.ps1
dotnet build src/Rook/Rook.csproj -c Release
.\build_native.ps1 -Configuration Release
```

Expected: all guards and builds pass.

- [ ] Commit.

```powershell
git add scripts install.ps1 installer/RookSetup.iss src/Rook/UI/ThreeScene/Resources mcp_server/src/rook/threejs_scene/resources
git commit -m "build: package Three.js scene compiler runtime"
```

## Task 12: Owned-Rhino Integration Harness, Browser Acceptance, and Documentation

**Files:**

- Create: `mcp_server/tools/threejs_scene_live_harness.py`
- Create: `mcp_server/tests/threejs_scene/test_live.py`
- Modify: `mcp_server/src/rook/runtime_harness.py`
- Modify: `scripts/run_rhino_runtime_harness.py`
- Create: `docs/threejs-render-scene.md`

- [ ] Write harness routing tests for a `threejs-scene` mode that uses the existing owned-Rhino launch/readiness/cleanup contract. The harness must never attach destructive tests to an arbitrary user Rhino process.

- [ ] Implement deterministic Rhino fixtures covering static context, ordinary actors, repeated geometry, off-axis pivots, non-unit scale, layers, source materials, override materials, excluded objects, and stable UUIDs.

- [ ] Implement live assertions for source immutability; refusal of an existing first-Create destination; candidate sync; derived inspection; Create; a second Update that adds, modifies, and deletes source objects; Relink; customization draft success/failure; survival of render-only cameras, lights, environment, and registered overrides; open-document blocking before construction; first-Create races; recovery races; every fault point; exact rollback; shared-storage rejection before construction; preview prepare/commit/restore; missing MCP/native/managed/WebView2/WebGL capability errors; and console cleanliness.

- [ ] Add browser acceptance using the embedded WebView surface, not the experiment page. Validate the reviewed 338- and 1,000-actor tiers, full draw workloads, actor identity, geometry sharing, forward/reverse/shuffled seek checks, pixel-equivalent merged context, precision, Stop/Reset, and visible evidence hashes. Keep 10,000 actors as explicit opt-in and record any GPU disjoint event.

- [ ] Document user workflow, artifact ownership, local-only restriction, explicit Update behavior, status meanings, customization adoption/clearing, retained-conflict handling, and recovery. Clearly state that the Rhino render scene is derived and inspectable while the source Rhino model remains authoritative.

- [ ] Run all automated layers.

```powershell
python -m pytest mcp_server/tests/threejs_scene -q
python -m pytest mcp_server/tests/test_server.py -q
Push-Location src/Rook/UI/ThreeScene/Client
npm test -- --run
npm run build
Pop-Location
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Release -f net8.0
.\build_native.ps1 -Configuration Release
git diff --check
```

Expected: every command passes.

- [ ] Deploy only to the isolated local-testing runtime and execute the owned-Rhino acceptance harness.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy-local-testing.ps1 -Configuration Release
python scripts/run_rhino_runtime_harness.py threejs-scene
```

Expected: the harness reports owned Rhino PID/ports, all Slice 1 acceptance cases pass, source fixture hash is unchanged, browser console has no warnings/errors, and owned processes are closed by the harness.

- [ ] Perform the one manual OS file-picker check if the preview offers local diagnostic GLB loading. Record filename, size, and SHA-256 provenance; this diagnostic must not bypass published-package hash checks.

- [ ] Commit.

```powershell
git add mcp_server/tools mcp_server/tests/threejs_scene mcp_server/src/rook/runtime_harness.py scripts/run_rhino_runtime_harness.py docs/threejs-render-scene.md
git commit -m "test: verify Three.js render scene workflow"
```

## Final Verification and Review Gate

- [ ] Invoke `superpowers:verification-before-completion` and rerun the exact commands from Task 12 from a clean shell.
- [ ] Regenerate the profile, execution envelope, deterministic GLB fixture, and production client twice; prove hashes are unchanged and `git status --short` remains empty.
- [ ] Run `git diff main...HEAD --check` and inspect `git diff --stat main...HEAD` for unrelated production changes.
- [ ] Run `git log --oneline --decorate -15` and verify each task has a focused commit.
- [ ] Invoke `superpowers:requesting-code-review` for one final whole-branch review against the approved spec, explicitly asking the reviewer to audit:

  - canonical comparison-path mutex identity, including nonexistent first Create;
  - cross-project/same-destination and concurrent-recovery serialization;
  - local-only storage enforcement;
  - protected-handle lifetime across destructive rollback;
  - Windows write-through/flush behavior with no POSIX directory-fsync assumption;
  - cross-volume retained-conflict crash safety;
  - acyclic hashes and phase-correct journal hashes;
  - full base-token revalidation and open-document TOCTOU rollback;
  - source immutability, draft preservation, preview-last commit, and exact recovery;
  - production preview parity with the reviewed stress evidence.

- [ ] Address every finding with red-green TDD, rerun affected layers, and repeat review until no blocking findings remain.
- [ ] Invoke `superpowers:finishing-a-development-branch` only after fresh verification passes. Do not merge, push, or remove either worktree without the user's explicit choice.

## Plan Self-Review Checklist

- [ ] Every Slice 1 acceptance criterion in the approved spec maps to at least one named automated or live test above.
- [ ] Every new interface has one owner and a test seam; no Rhino SDK work appears in Python or managed browser code.
- [ ] No step introduces a dependency beyond the approved exact browser versions and existing repository dependencies.
- [ ] No placeholder, deferred transaction rule, future hash, or unspecified cleanup class remains.
- [ ] Create, Update, Relink, customization, preview, rollback, recovery, and acknowledgement each have explicit entry conditions and terminal states.
- [ ] The final branch can be reviewed and built without relying on uncommitted files from the earlier stress worktree.
