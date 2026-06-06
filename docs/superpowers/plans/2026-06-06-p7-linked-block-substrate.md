# P7 Linked-Block Substrate Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make linked-block identity observable and comparable by the Python coordinator (additive read-only native fields), and add a pure deterministic block-naming helper — the substrate a future P7 merge executor needs to ensure linked blocks idempotently.

**Architecture:** One C++ helper (`DecorateLinkedBlockFields`) decorates block JSON with raw linked facts on both `/blocks` and `/block/info` (single source of truth). One pure Python helper (`linked_blocks.block_def_name`) mints a deterministic, versioned, opaque block-definition name. A held live-Rhino test verifies the fields and records the post-save linked-path form. No merge executor, no `/block/link` change, no C++ normalization, no P7-registry change.

**Tech Stack:** C++ (Rhino 8 C++ SDK, MFC, `nlohmann/json`) in `src/RookNative/`; Python 3 (`hashlib`, `pytest`, `pytest-asyncio`) in `mcp_server/`.

**Spec:** `docs/superpowers/specs/2026-06-06-p7-linked-block-substrate-design.md` (on `main` at `9f096da`).

---

## Branch setup

Spec + this plan are already on `main`/`origin`. Implementation goes on a feature branch.

```powershell
cd C:\Users\aryan\source\repos\Rook
git checkout main
git pull origin main
git checkout -b feature/p7-linked-block-substrate
```

**Standing rules for every commit in this plan:**
- Before each commit, restore generated knowledge artifacts if a test run dirtied them: `git checkout -- knowledge/` and (if present) `Remove-Item -Recurse -Force knowledge/selectors -ErrorAction SilentlyContinue`. Stage files explicitly — never `git add -A`.
- End every commit message with the trailer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Pytest entrypoint: `mcp_server\.venv\Scripts\python.exe -m pytest`.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `mcp_server/src/rook/linked_blocks.py` | Pure P7 linked-block coordinator helpers — currently `block_def_name`; future home of the executor/comparator. No server/Rhino/registry imports. | Create |
| `mcp_server/tests/test_linked_blocks.py` | Unit tests for `block_def_name` (offline). | Create |
| `src/RookNative/Handlers/BlocksHandler.cpp` | Add `DecorateLinkedBlockFields`; call it from `SerializeBlockDef` and `HandleBlockInfo`. | Modify |
| `mcp_server/tests/test_linked_block_fields_live.py` | Held live-Rhino verification of the four fields + post-save path-form observation. | Create |

---

## Task 1: Pure Python naming helper (`block_def_name`)

Fully offline TDD. This is the only behavior-bearing logic that runs without Rhino.

**Files:**
- Create: `mcp_server/src/rook/linked_blocks.py`
- Test: `mcp_server/tests/test_linked_blocks.py`

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_linked_blocks.py`:

```python
from __future__ import annotations

import pytest

from rook.linked_blocks import block_def_name

# A valid canonical artifact id is 64 lowercase hex chars (SHA-256). These
# fixtures pad a recognizable 16-hex prefix out to full length.
_AID = "a1b2c3d4e5f67890" + "0" * 48
_AID2 = "ffffffffffffffff" + "0" * 48
_ALPHABET = set("abcdefghijklmnopqrstuvwxyz0123456789_-")


def test_deterministic_same_inputs_same_output():
    assert block_def_name("mc-abc", _AID) == block_def_name("mc-abc", _AID)


def test_prefix_and_shape():
    name = block_def_name("mc-abc", _AID)
    parts = name.split("_")
    assert parts[:2] == ["rook", "p7lb"]
    assert len(parts[2]) == 8 and all(c in "0123456789abcdef" for c in parts[2])
    assert parts[3] == "a1b2c3d4e5f67890"  # first 16 hex of the artifact id
    assert set(name) <= _ALPHABET


def test_case_stability_lowercase_output():
    lower = block_def_name("mc-abc", _AID)
    upper = block_def_name("mc-abc", ("A1B2C3D4E5F67890" + "0" * 48))
    assert lower == upper == lower.lower()


def test_illegal_looking_contract_id_still_restricted_alphabet():
    name = block_def_name("contract with spaces / Ünîçødé / ../x", _AID)
    assert set(name) <= _ALPHABET
    assert name.startswith("rook_p7lb_")


def test_distinct_contracts_distinct_names():
    assert block_def_name("mc-aaa", _AID) != block_def_name("mc-bbb", _AID)


def test_distinct_sources_distinct_names():
    assert block_def_name("mc-abc", _AID) != block_def_name("mc-abc", _AID2)


def test_rejects_too_short_source_artifact_id():
    with pytest.raises(ValueError):
        block_def_name("mc-abc", "a1b2c3")


def test_rejects_non_hex_source_artifact_id():
    with pytest.raises(ValueError):
        block_def_name("mc-abc", "z" * 64)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_linked_blocks.py -v`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'rook.linked_blocks'`.

- [ ] **Step 3: Write the minimal implementation**

Create `mcp_server/src/rook/linked_blocks.py`:

```python
"""P7 linked-block coordinator helpers.

Pure module: no server imports, no Rhino calls, no P7-registry dependency.
Currently hosts the deterministic block-definition naming helper; future
home for the linked-block merge executor + comparator.
"""
from __future__ import annotations

import hashlib

# Versioned/purpose prefix so the scheme can evolve unambiguously.
_SCHEME = "rook_p7lb"
_HEX_DIGITS = frozenset("0123456789abcdef")


def block_def_name(contract_id: str, source_artifact_id: str) -> str:
    """Deterministic Rhino block-definition NAME for a P7 linked-block merge.

    A stable idempotency ADDRESS, not a human explanation — Rhino's Block
    Manager already shows each linked block's source path in its own column.

    contract_id is HASHED (generated ids may not be restricted-alphabet).
    source_artifact_id is the canonical SHA-256 hex from
    artifacts.artifact_id_for and is validated fail-closed (>=16 lowercase-hex
    chars) so a malformed id raises rather than silently minting a
    wrong-but-valid durable address.

    Output: lowercase [a-z0-9_-], ~35 chars, far under Rhino name limits.
    """
    sid = source_artifact_id.lower()
    if len(sid) < 16 or any(c not in _HEX_DIGITS for c in sid):
        raise ValueError(
            "source_artifact_id must be SHA-256 hex (>=16 hex chars); "
            f"got {source_artifact_id!r}"
        )
    contract_hash = hashlib.sha256(contract_id.encode("utf-8")).hexdigest()[:8]
    return f"{_SCHEME}_{contract_hash}_{sid[:16]}"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_linked_blocks.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```powershell
git add mcp_server/src/rook/linked_blocks.py mcp_server/tests/test_linked_blocks.py
git commit -m @'
feat(p7): linked_blocks.block_def_name deterministic naming helper

Pure module (no server/Rhino/registry imports). rook_p7lb_<contract8>_<artifact16>;
contract id hashed, artifact id validated fail-closed (>=16 lowercase-hex).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

---

## Task 2: C++ `DecorateLinkedBlockFields` helper + wire both serializers

Native, additive, read-only. There is no local C++ unit test — the compile is the local gate; behavior is verified live in Task 3. Do **not** claim build verification without the Rhino/MFC toolchain (AGENTS.md).

**Files:**
- Modify: `src/RookNative/Handlers/BlocksHandler.cpp` (helper near line ~258; `SerializeBlockDef` ~260–276; `HandleBlockInfo` ~1771–1791)

- [ ] **Step 1: Add the helper above `SerializeBlockDef`**

Find `static nlohmann::json SerializeBlockDef(CRhinoDoc* pDoc,` (≈ line 260). Immediately **above** it, insert:

```cpp
// Decorate a block-definition JSON with raw linked-block facts. No
// normalization, no identity — those belong to the Python coordinator.
// Shared by SerializeBlockDef (/blocks) and HandleBlockInfo (/block/info)
// so the two surfaces can never drift. Additive: callers keep their fields.
static void DecorateLinkedBlockFields(nlohmann::json& j,
                                      const CRhinoInstanceDefinition* pIdef)
{
    ON_InstanceDefinition::IDEF_UPDATE_TYPE updateType = pIdef->InstanceDefinitionType();

    // EXACT strings — preserve the existing /block/info contract. Default "Embedded".
    std::string blockType = "Embedded";
    if (updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::Linked)
        blockType = "Linked";
    else if (updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::LinkedAndEmbedded)
        blockType = "EmbeddedAndLinked";

    ON_wString linked = pIdef->LinkedFilePath();   // raw — no normalization
    bool isLinked =
        (updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::Linked ||
         updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::LinkedAndEmbedded)
        && !linked.IsEmpty();

    std::string rawPath = WideToUtf8(linked);   // "" when not linked

    j["blockType"]     = blockType;
    j["isLinked"]      = isLinked;
    j["sourcePath"]    = rawPath;   // preferred raw field (matches /block/link, /block/refresh)
    j["sourceArchive"] = rawPath;   // backward-compatible alias, identical value
}
```

- [ ] **Step 2: Call it from `SerializeBlockDef`**

In `SerializeBlockDef`, find the tail:

```cpp
    j["objectCount"] = pIdef->ObjectCount();
    j["instanceCount"] = refs.Count();
    return j;
```

Replace with:

```cpp
    j["objectCount"] = pIdef->ObjectCount();
    j["instanceCount"] = refs.Count();
    DecorateLinkedBlockFields(j, pIdef);
    return j;
```

- [ ] **Step 3: Call it from `HandleBlockInfo` (remove the inline duplication)**

In `HandleBlockInfo`, find the block that computes `blockType` and assigns it + `sourceArchive` (≈ lines 1771–1791):

```cpp
        // Block type
        std::string blockType = "Embedded";
        ON_InstanceDefinition::IDEF_UPDATE_TYPE updateType = pIdef->InstanceDefinitionType();
        if (updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::Linked)
            blockType = "Linked";
        else if (updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::LinkedAndEmbedded)
            blockType = "EmbeddedAndLinked";

        WriteResult wr;
        wr.success = true;
        wr.data["index"] = pIdef->Index();
        wr.data["id"] = UuidToString(pIdef->Id());
        wr.data["name"] = WideToUtf8(pIdef->Name());
        wr.data["description"] = WideToUtf8(pIdef->Description());
        wr.data["url"] = WideToUtf8(pIdef->URL());
        wr.data["urlDescription"] = WideToUtf8(pIdef->URL_Tag());
        wr.data["blockType"] = blockType;
        wr.data["sourceArchive"] = WideToUtf8(pIdef->LinkedFilePath());
        wr.data["objectCount"] = pIdef->ObjectCount();
        wr.data["instanceCount"] = refs.Count();
        wr.data["objects"] = std::move(objectInfos);
```

Replace with (drop the inline `blockType` computation and the two inline assignments; the helper supplies `blockType` + `sourceArchive` with identical values, plus `isLinked` + `sourcePath`):

```cpp
        WriteResult wr;
        wr.success = true;
        wr.data["index"] = pIdef->Index();
        wr.data["id"] = UuidToString(pIdef->Id());
        wr.data["name"] = WideToUtf8(pIdef->Name());
        wr.data["description"] = WideToUtf8(pIdef->Description());
        wr.data["url"] = WideToUtf8(pIdef->URL());
        wr.data["urlDescription"] = WideToUtf8(pIdef->URL_Tag());
        DecorateLinkedBlockFields(wr.data, pIdef);  // blockType, isLinked, sourcePath, sourceArchive
        wr.data["objectCount"] = pIdef->ObjectCount();
        wr.data["instanceCount"] = refs.Count();
        wr.data["objects"] = std::move(objectInfos);
```

- [ ] **Step 4: Build with the known-good MFC toolset**

Run (PowerShell):
`cmd /c "scripts\build-native.bat Debug 14.44.35207"`
Expected: build succeeds (`RookNative.rhp` produced). Bare `v143` may resolve to `14.38.33130`, which has an incomplete MFC payload — pass `14.44.35207` explicitly. If the toolchain is unavailable, mark the build **HELD** and stop here for that environment; do not fake it.

- [ ] **Step 5: Commit**

```powershell
git add src/RookNative/Handlers/BlocksHandler.cpp
git commit -m @'
feat(p7): expose raw linked-block facts on /blocks and /block/info

DecorateLinkedBlockFields adds blockType/isLinked/sourcePath/sourceArchive
from one shared helper on SerializeBlockDef + HandleBlockInfo. Additive,
read-only, raw path (no normalization). /block/link + /block/refresh untouched.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

---

## Task 3: Held live-Rhino verification + observation

Verifies the Task 2 fields against real Rhino and records the post-save linked-path form for the future executor. Skips cleanly when Rhino is unreachable (the `fresh_document` fixture), so an absent toolchain is a graceful skip — never a fake pass.

**Files:**
- Create: `mcp_server/tests/test_linked_block_fields_live.py`

- [ ] **Step 1: Write the live test module**

Create `mcp_server/tests/test_linked_block_fields_live.py`:

```python
"""Live-Rhino verification + observation for the P7 linked-block substrate.

Held for Rhino: requires a running Rhino with a freshly-built + deployed
RookNative (the DecorateLinkedBlockFields fields). Skips cleanly when Rhino
is unreachable (fresh_document), so an absent toolchain is a graceful skip,
never a fake pass — spec §6 honesty discipline.

Run (from repo root, with a throwaway Rhino session):
    mcp_server\\.venv\\Scripts\\python.exe -m pytest -m requires_rhino ^
        mcp_server/tests/test_linked_block_fields_live.py -s
IMPORTANT: replaces the active Rhino document; use a throwaway session.
"""
from __future__ import annotations

import os
import tempfile

import pytest

from rook.server import _mcp_tool_executor

from .conftest import fresh_document  # noqa: F401 — fixture used by name

pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


def _tmp(tag: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"rook_p7lb_{os.getpid()}_{tag}.3dm")


async def _save_one_box_source(src_path: str) -> None:
    """Save a single-box document to src_path to serve as a linked source."""
    await _mcp_tool_executor(
        "rhino_create",
        {"type": "BOX", "corner1": [0, 0, 0], "corner2": [1, 1, 1], "name": "srcbox"},
    )
    save = await _mcp_tool_executor("rhino_document_ops", {"action": "save", "path": src_path})
    assert save.get("success") is not False, f"save source failed: {save!r}"


def _find_block(blocks: list, name: str) -> dict:
    for b in blocks:
        if isinstance(b, dict) and b.get("name") == name:
            return b
    raise AssertionError(f"{name!r} not in /blocks: {[b.get('name') for b in blocks]}")


async def test_blocks_and_info_expose_linked_fields(fresh_document):
    src = _tmp("src")
    try:
        await _save_one_box_source(src)
        await _mcp_tool_executor("rhino_document_ops", {"action": "new"})

        link = await _mcp_tool_executor("rhino_block_link", {"path": src, "name": "lb_linked"})
        assert link.get("success") is not False, f"block_link failed: {link!r}"

        box = await _mcp_tool_executor(
            "rhino_create",
            {"type": "BOX", "corner1": [0, 0, 0], "corner2": [1, 1, 1], "name": "embbox"},
        )
        await _mcp_tool_executor(
            "rhino_block_create",
            {"name": "lb_embedded", "ids": [box["id"]], "basePoint": [0, 0, 0],
             "replaceWithInstance": True},
        )

        blocks = (await _mcp_tool_executor("rhino_blocks", {}))["blocks"]
        linked = _find_block(blocks, "lb_linked")
        embedded = _find_block(blocks, "lb_embedded")

        # Linked def: four fields present and consistent.
        assert linked["blockType"] in ("Linked", "EmbeddedAndLinked"), linked
        assert linked["isLinked"] is True, linked
        assert linked["sourcePath"], "linked sourcePath must be non-empty"
        assert linked["sourcePath"] == linked["sourceArchive"], linked

        # Embedded def: isLinked false, empty path aliases.
        assert embedded["blockType"] == "Embedded", embedded
        assert embedded["isLinked"] is False, embedded
        assert embedded["sourcePath"] == "", embedded
        assert embedded["sourceArchive"] == "", embedded

        # /block/info parity for the linked def (gains isLinked + sourcePath).
        info = await _mcp_tool_executor("rhino_block_info", {"name": "lb_linked"})
        assert info["isLinked"] is True, info
        assert info["sourcePath"] == info["sourceArchive"] and info["sourcePath"], info
        assert info["blockType"] == linked["blockType"], info
    finally:
        try:
            os.remove(src)
        except OSError:
            pass


async def test_post_save_linked_path_form_observation(fresh_document, capsys):
    """OBSERVATION (spec §6): record what sourcePath returns after the HOST
    doc is saved + reopened. Lenient — the purpose is to record the form
    (absolute / relative / drive-rooted) for the executor's resolution rule.
    """
    src = _tmp("src2")
    host = _tmp("host2")
    try:
        await _save_one_box_source(src)
        await _mcp_tool_executor("rhino_document_ops", {"action": "new"})
        await _mcp_tool_executor("rhino_block_link", {"path": src, "name": "lb_obs"})

        save = await _mcp_tool_executor("rhino_document_ops", {"action": "save", "path": host})
        assert save.get("success") is not False, f"save host failed: {save!r}"
        opened = await _mcp_tool_executor("rhino_document_ops", {"action": "open", "path": host})
        assert opened.get("success") is not False, f"open host failed: {opened!r}"

        info = await _mcp_tool_executor("rhino_block_info", {"name": "lb_obs"})
        with capsys.disabled():
            print(
                f"\n[P7-LB OBSERVATION] post-save linked sourcePath = "
                f"{info.get('sourcePath')!r}  (host={host!r}, source={src!r})"
            )
        assert info.get("isLinked") is True, info
        assert info.get("sourcePath"), info
    finally:
        for p in (src, host):
            try:
                os.remove(p)
            except OSError:
                pass
```

- [ ] **Step 2: Verify the module imports cleanly (collection-safe for the parity gate)**

Run: `mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_linked_block_fields_live.py --collect-only -q`
Expected: 2 tests collected, no import/collection error. (They will be deselected by the `not requires_rhino` parity gate.)

- [ ] **Step 3: Commit**

```powershell
git add mcp_server/tests/test_linked_block_fields_live.py
git commit -m @'
test(p7): held live verification + post-save observation for linked-block fields

Asserts blockType/isLinked/sourcePath/sourceArchive on /blocks + /block/info
for a linked and an embedded def; records post-save linked sourcePath form
for the future executor. requires_rhino; skips cleanly when Rhino absent.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

- [ ] **Step 4: HELD — run live verification (checkpoint; deploy + throwaway Rhino)**

Deploy the Task 2 build and restart Rhino, then run the live test in a **throwaway** Rhino session:
```powershell
cmd /c "scripts\deploy-native.bat Debug"
# (restart Rhino so the new RookNative.rhp loads)
mcp_server\.venv\Scripts\python.exe -m pytest -m requires_rhino mcp_server/tests/test_linked_block_fields_live.py -s
```
Expected when Rhino present + rebuilt: 2 passed; the `[P7-LB OBSERVATION]` line prints the post-save `sourcePath`. **Honesty discipline (#218/#222):** if Rhino/toolchain is unavailable, report this step **BLOCKED with reason** — it is gated evidence, not a ship gate. Record the observed post-save form (or "blocked") in the PR description.

---

## Task 4: Baseline parity (both directions) + finish branch

**Files:** none (verification only).

- [ ] **Step 1: Restore any test-dirtied knowledge artifacts**

```powershell
git checkout -- knowledge/
Remove-Item -Recurse -Force knowledge/selectors -ErrorAction SilentlyContinue
git status -s
```
Expected: clean (only intended files committed).

- [ ] **Step 2: Run the blessed non-live gate and capture the named sets**

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests -m "not requires_rhino" -p no:cacheprovider -q -rfE --tb=no
```
Expected: **64 failed, 41 errors** (unchanged from `main`), plus the 8 new `test_linked_blocks.py` tests passing. The new `test_linked_block_fields_live.py` is deselected (`requires_rhino`).

- [ ] **Step 3: Prove parity both directions vs main**

Counts can coincide while sets differ. Capture the FAILED/ERROR test ids on this branch and on `main` and diff them **both ways** with `comm` (Git Bash) or `Compare-Object` (PowerShell):
```powershell
# feature set already captured above; regenerate main's set in a clean worktree
# or from a stashed checkout, then:
Compare-Object (Get-Content main_failed_errors.txt) (Get-Content feature_failed_errors.txt)
```
Expected: empty diff — the additive Python module and native fields introduce **no new** failures/errors. If anything appears, fix before proceeding.

- [ ] **Step 4: Finish the branch**

Announce: "I'm using the finishing-a-development-branch skill to complete this work." Then follow it: verify tests, push, open a PR (option 2). The PR body must end with:
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`
and must state the live-verification outcome honestly (passed / blocked-with-reason) plus the recorded post-save `sourcePath` form when available. **The user pulls the merge trigger** (`gh pr merge --squash --delete-branch`).

---

## Self-Review

**Spec coverage:**
- §1 native decoration → Task 2 (helper + both call sites, exact strings, conjunction `isLinked`, raw path). ✓
- §2 Python helper → Task 1 (pure module + validation). ✓
- §3 executor-consumes contract → documentation in the spec; correctly **not** built here. ✓
- §4 live observation → Task 3 (four-fields assertion + post-save observation, throwaway doc, honest blocked/green). ✓
- §5 testing/parity → Task 1 unit tests, Task 3 live test, Task 4 parity-both-directions + known-good build toolset. ✓
- §6 scope boundaries → no `/block/link` change, no normalization, no registry change (no task touches `work_units.py`, `/block/link`, or any `normalize`). ✓
- §9 acceptance criteria all map to a task. ✓

**Placeholder scan:** No TBD/TODO. Every code step shows complete code; every command is exact. Live verification is explicitly held with honest reporting (not a placeholder — it is the documented #218/#222 discipline).

**Type/name consistency:** `DecorateLinkedBlockFields`, `block_def_name`, `_SCHEME="rook_p7lb"`, field names `blockType`/`isLinked`/`sourcePath`/`sourceArchive`, and the `rook_p7lb_<contract8>_<artifact16>` shape are identical across the spec, Task 1, Task 2, and Task 3.
