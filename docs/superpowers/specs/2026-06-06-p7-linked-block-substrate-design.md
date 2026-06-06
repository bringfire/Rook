# P7 Linked-Block Substrate Slice — Design

> **Status:** design approved (brainstorm); pending spec review → writing-plans.
> **Plane:** router / P7 fan-in, **pre-execution substrate**.
> **Shape:** additive **read-only** native decoration + **pure** Python naming helper + Rhino-gated live observation. No merge executor in this slice.

---

## 1. Context & Motivation

P7's fan-in intent ladder is complete on `main` (`f9cb84a`): `declared_targets` → `planned_merge_contracts` → strict `merge_contracts`. The next slice was to be the **first merge execution**, and the likely first executable `merge_kind` is `linked_block` (programmatic, preserves live references, matches `refresh_policy`) rather than `import` (one-shot `RunScript`, duplicates geometry, makes `refresh_policy` meaningless).

Codex surfaced a blocker: **raw `rhino_block_link` is not idempotent enough for contract execution.** A future Python executor cannot safely answer "does this target doc already contain the correct linked block for this source, or is the name occupied by something else?" — so it cannot re-run a merge without duplicating or clobbering.

This slice builds the **narrow substrate** that unblocks an idempotent executor *later*. It does **not** execute merges.

### 1.1 Grounding facts (verified against the tree at `f9cb84a`)

- **`/block/info` (`HandleBlockInfo`) already exposes linkage:** `blockType` (`"Embedded"` / `"Linked"` / `"EmbeddedAndLinked"`, from `InstanceDefinitionType()`) and `sourceArchive` (raw `pIdef->LinkedFilePath()`). `server.py` forwards it unmodified.
- **`/blocks` (`SerializeBlockDef`) does NOT:** only `index / id / name / description / objectCount / instanceCount`. So a coordinator can't scan link-state in one call.
- **Naming inconsistency exists today:** the *write* handlers already emit `sourcePath` — `/block/link` (line 4240) and `/block/refresh` (line 4308) — while the *read* handler `/block/info` emits `sourceArchive` (line 1788), for the same `LinkedFilePath()` value.
- **`LinkedFilePath()` is raw.** RhinoCommon may store linked references relative to the host `.3dm` after a save; the post-save form is unknown until observed live.
- **Block-name lookup is case-insensitive:** `FindDefByName` → `FindInstanceDefinition(wName)`.
- **No name-length cap** exists in the block handlers.
- **`rhino_block_link` throws on collision:** `invalid_argument("Block definition '<name>' already exists")` (line 4103) — an opaque error string, the only collision signal today.

---

## 2. Goal & Non-Goals

**Goal:** Make linked-block identity **observable and comparable by the Python coordinator**, and provide a **deterministic block-naming helper**, so a future P7 merge executor can ensure linked blocks idempotently.

**Non-Goals (explicitly out of this slice):**

- No merge executor, comparator, or "ensure linked block" logic.
- No change to `/block/link` failure semantics (read-only classify; see §4).
- No path normalization or `artifact_id` computation in C++ (native reports Rhino facts; Python/P6 owns path identity).
- No P7 registry or schema change — `work_units.py` is untouched.
- No human-legible block names; no `updateType` field.

---

## 3. § 1 — Native read decoration (C++, additive, read-only)

A single new static helper in `src/RookNative/Handlers/BlocksHandler.cpp`. The name avoids "identity" deliberately: **C++ reports raw linked-block facts; identity is the Python coordinator's job.**

```cpp
// Decorate a block-definition JSON with raw linked-block facts.
// No normalization, no identity — those belong to the Python coordinator.
static void DecorateLinkedBlockFields(nlohmann::json& j,
                                      const CRhinoInstanceDefinition* pIdef)
{
    ON_InstanceDefinition::IDEF_UPDATE_TYPE updateType = pIdef->InstanceDefinitionType();

    // EXACT strings — preserve existing /block/info contract. Default "Embedded".
    std::string blockType = "Embedded";
    if (updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::Linked)
        blockType = "Linked";
    else if (updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::LinkedAndEmbedded)
        blockType = "EmbeddedAndLinked";

    ON_wString linked = pIdef->LinkedFilePath();          // raw — no normalization
    bool isLinked =
        (updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::Linked ||
         updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::LinkedAndEmbedded)
        && !linked.IsEmpty();

    std::string rawPath = WideToUtf8(linked);             // "" when not linked

    j["blockType"]     = blockType;
    j["isLinked"]      = isLinked;
    j["sourcePath"]    = rawPath;   // canonical (matches /block/link, /block/refresh)
    j["sourceArchive"] = rawPath;   // backward-compatible alias, identical value
}
```

**Field contract (4 fields, one helper, both surfaces):**

| Field | Type | Value |
|-------|------|-------|
| `blockType` | string | exactly `"Embedded"` \| `"Linked"` \| `"EmbeddedAndLinked"` (else → `"Embedded"`) |
| `isLinked` | bool | `(blockType ∈ {Linked, EmbeddedAndLinked}) ∧ LinkedFilePath() non-empty` |
| `sourcePath` | string | raw `LinkedFilePath()` (canonical key) — **always populated**, `""` when not linked |
| `sourceArchive` | string | identical raw value (compat alias) — **always populated** |

**Mismatch contract (precise):** `isLinked` is the **conjunction** of type-is-linked AND path-present. In an anomalous state — a linked-ish `blockType` with an empty path, or a non-linked type carrying a path — `isLinked` resolves `false`, but `blockType` and `sourcePath`/`sourceArchive` still carry the **raw facts** so Python can *detect* the anomaly rather than have it hidden. The Python comparator treats `isLinked` as authoritative and ignores the path aliases when it is `false`.

**Call sites (single source of truth → drift impossible):**

- `SerializeBlockDef` (the `/blocks` list serializer, one caller) — call `DecorateLinkedBlockFields(j, pIdef)` before `return j;`. Net: **+4 fields**.
- `HandleBlockInfo` (`/block/info`) — replace its inline `blockType` block (lines ~1771–1777) and inline `sourceArchive` assignment (line ~1788) with a `DecorateLinkedBlockFields` call. Net: **+2 fields** (`isLinked`, `sourcePath`); `blockType` and `sourceArchive` keep identical values; all other fields (`url`, `urlDescription`, `objects`, counts) unchanged.

**Safety:** purely additive; both responses become supersets, nothing removed or re-spelled. The **write path is not touched** — `/block/link` and `/block/refresh` already emit `sourcePath`, so they are already consistent with the new canonical key.

---

## 4. § 2 — Python deterministic-name helper (pure, unit-tested)

New module `mcp_server/src/rook/linked_blocks.py` — the future home for the executor/comparator. **Pure:** no `server` imports, no Rhino calls, no P7-registry dependency.

```python
import hashlib

# Versioned/purpose prefix so the scheme can evolve unambiguously.
_SCHEME = "rook_p7lb"


def block_def_name(contract_id: str, source_artifact_id: str) -> str:
    """Deterministic Rhino block-definition NAME for a P7 linked-block merge.

    A stable idempotency ADDRESS, not a human explanation — Rhino's Block
    Manager already shows each linked block's source path in its own column.

    - contract_id is HASHED first (generated ids may not be restricted-alphabet).
    - source_artifact_id is the canonical SHA-256 hex from artifacts.artifact_id_for;
      it is already lowercase hex, so slicing 16 chars is safe.
    - Output is lowercase [a-z0-9_-] only; ~35 chars, far under Rhino limits.
    """
    contract_hash = hashlib.sha256(contract_id.encode("utf-8")).hexdigest()[:8]
    artifact_hash = source_artifact_id.lower()[:16]
    return f"{_SCHEME}_{contract_hash}_{artifact_hash}"
```

Example: `block_def_name("mc-...", "a1b2c3d4e5f67890...")` → `rook_p7lb_3f9a1c0b_a1b2c3d4e5f67890`.

**Properties:** pure, deterministic, lowercase restricted alphabet, versioned prefix; identity derives from hashes only; per-`(contract, source)` pair. **This naming scheme is a durable forever-contract** — the executor must reproduce identical names on re-run, so the scheme is frozen once shipped. A future legible scheme would be a *new* prefixed scheme, never a mutation of `rook_p7lb`.

---

## 5. § 3 — Executor-consumes contract (documented here, NOT built)

Documented so this slice's read surface is provably **sufficient** for the future executor; this is contract text, not code in this slice.

1. Compute `name = block_def_name(contract_id, source_artifact_id)`; attempt `rhino_block_link(name, source)`.
2. On **any** failure (the error is an opaque string today, so do not branch on its text), re-read `block_info(name)` (or scan `rhino_blocks`) and classify from actual document state:
   - **exists** + `isLinked` + `normalize_path(sourcePath)` → `artifact_id` **== expected** → idempotent existing link; `rhino_block_refresh` if stale.
   - **exists** + `isLinked` + **different** `artifact_id` → `conflict_different_source` (fail closed).
   - **exists** + `isLinked:false` → `conflict_nonlinked` (fail closed).
   - **absent** → the link genuinely failed for another reason (source unreadable / unsupported geometry) → surface the original failure.
3. Path identity is computed in Python only, via `artifacts.normalize_path()` + SHA-256 (`artifact_id_for`) — the same identity P6 already uses.

The re-read-after-**any**-failure rule (not only collision-looking failures) is required precisely because today's error is opaque.

---

## 6. § 4 — Live observation (Rhino-gated evidence, not a merge blocker)

A live smoke, **held for Rhino** per the established pattern (#218/#222). On a **throwaway document confirmed in chat first** (never the user's default document):

1. Create a linked block from a temporary `.3dm`.
2. Read `/block/info` and `/blocks`; assert the four fields present and mutually consistent (`isLinked` matches `blockType` + non-empty `sourcePath`; `sourcePath == sourceArchive`).
3. **Save + reopen** the throwaway doc; re-read; **record what `LinkedFilePath()` / `sourcePath` returns post-save** — absolute, relative, or drive-rooted.

The recorded post-save form is the input to the future executor's relative→absolute resolution rule. **Honesty discipline:** if the native build and non-live tests are green but the save/reopen step is blocked by local Rhino state, report it as **blocked**, do not pretend it ran. This observation is *gated evidence*, not a gate on shipping the slice.

---

## 7. § 5 — Testing & Parity

**Python unit tests** (`mcp_server/tests/test_linked_blocks.py`) for `block_def_name`:
- determinism — same inputs → byte-identical output;
- case stability — output is lowercase regardless of input case;
- restricted alphabet under an **illegal-looking `contract_id`** (spaces / unicode / path-like) → output still `[a-z0-9_-]` (contract id is hashed);
- distinct `(contract, source)` pairs → distinct names; same pair → same name;
- versioned prefix `rook_p7lb_` present; expected length.

**Native:** field decoration verified by a live-Rhino test (assert the four fields on both `/blocks` and `/block/info` for a linked and a non-linked def). **Build** with the known-good MFC toolset (AGENTS.md): `cmd /c "scripts\build-native.bat Debug 14.44.35207"` (bare `v143` may resolve to `14.38.33130`, which has an incomplete MFC payload). Do not claim build verification without the Rhino/MFC toolchain.

**Baseline parity:** the blessed non-live gate, compared **both directions** via `comm` against `main` (= 64 failed / 41 errors):
`mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests -m "not requires_rhino" -p no:cacheprovider -q -rfE --tb=no`
Additive native fields and a new pure Python module must not move the Python suite.

---

## 8. Risks & open questions (for the executor slice, not this one)

- **Relative-vs-absolute path resolution.** The executor must resolve a possibly-relative `sourcePath` against the host doc's directory before normalizing. The §4 live observation produces the evidence for that rule; it is not solved here.
- **Contract-scoped vs source-scoped naming.** `block_def_name` includes the contract hash, so two contracts linking the same source into the same target produce two linked blocks. Whether a merge should instead reuse one source-scoped link is **executor policy**, deferred.
- **Structured collision code.** If post-hoc state inspection proves insufficient in the executor slice, hardening `/block/link` with a structured `code` remains available as a follow-up — explicitly out of this slice.

---

## 9. Acceptance Criteria

- [ ] `DecorateLinkedBlockFields` exists in `BlocksHandler.cpp`, sets exactly the four fields with the pinned `blockType` strings and conjunction `isLinked`, performs no normalization.
- [ ] Both `/blocks` and `/block/info` emit `blockType`, `isLinked`, `sourcePath`, `sourceArchive` from that one helper; `/block/info`'s pre-existing fields and values are unchanged.
- [ ] `/block/link` and `/block/refresh` are unmodified.
- [ ] `linked_blocks.block_def_name` is pure (no `server`/Rhino/registry imports) and passes all §7 unit tests.
- [ ] Baseline parity holds both directions (64 failed / 41 errors unchanged).
- [ ] Live observation attempted with honest blocked/green reporting; post-save `LinkedFilePath()` form recorded when it runs.
- [ ] No change to `work_units.py` or any P7 registry/schema.
