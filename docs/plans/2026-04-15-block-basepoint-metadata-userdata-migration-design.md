# Block basePoint metadata — Rook-owned symmetric UserData channel

**Issue:** [#28](https://github.com/bringfire/Rook/issues/28)
**Supersedes plan for:** migrate `rook_block_base_point` storage to `InstanceDefinition.UserDictionary` (no longer viable — see "Why the original framing didn't survive research").
**Status:** Design approved via brainstorming skill (2026-04-15), ready for implementation-plan generation.

---

## 1. Reframed scope

**Old framing:** migrate `rook_block_base_point` from `ON_Object::SetUserString` to `InstanceDefinition.UserDictionary`.

**New framing:** introduce a **Rook-owned symmetric `ON_UserData` metadata channel** for block-definition basePoint, with legacy user-string fallback for pre-migration `.3dm` files. Native and managed sides share one Rook-owned UUID and a versioned binary contract we fully own. Retires PR #30's non-public `InstanceDefinition._GetUserString` reflection bridge via a dual-read/dual-write transition window.

### Why the original framing didn't survive research

- `Rhino.DocObjects.Custom.UserDictionary` (the managed backing for `InstanceDefinition.UserDictionary`) has GUID `171E831F-7FEF-40E2-9857-E5CCD39446F0` and is a RhinoCommon-private `ON_UserData` subclass.
- Writing to "the same slot" from C++ native would require replicating RhinoCommon's private binary format — the exact hidden-compat-trap class we're trying to exit.
- `ON_ArchivableDictionary` exists in `opennurbs_archivable_dictionary.h` but has no symmetric native-attach-point on `ON_InstanceDefinition` that's interoperable with managed's `idef.UserDictionary`.
- Rejected paths: hijack private UUID (fragile), managed-only-writer (leaves native blind), do-nothing (retains non-public API dependency).

### Architectural positioning

This PR introduces the **first custom `UserData` pattern in the repo**. Future metadata cases (scaleReference, alignmentPlane, Rook layer conventions) can follow the same pattern — so this pays off beyond just basePoint. Intentionally NOT building a generic "Rook metadata framework" abstraction on this pass; one concrete type, generalize later if a second case appears.

### Non-goals

- **No one-shot upgrader** for existing `.3dm` files. Migration is incremental and narrower than "any touch": the new slot is written **only on paths that write a new basePoint value** — create, rebase, rebase-recursive, duplicate. Geometry-mutation paths (add-objects, remove-objects, replace-geometry, replace-object-geometry) preserve existing metadata but do not promote legacy-only definitions to the new slot. Pre-migration definitions that are only ever geometry-modified stay on the legacy slot through the transition window.
- **No `InstanceDefinition.UserDictionary` use.** RhinoCommon-private; we own our slot.
- **No MCP tool surface changes.** Public tool contracts unchanged.
- **No retirement of the legacy slot** in this PR. Follow-up PR after ≥1 release window.
- **No Issue #26 overlap.** Local-frame-mutation helper refactor inherits clean API; separate PR.

---

## 2. Components

### 2.1 Load-bearing constant — UUID

**`0CD9F899-C9AA-4FC5-8F45-E081409245E9`** — Rook-owned, both sides MUST use this value verbatim.

- C++ consumption: `const ON_UUID kRookBlockBasePointUserDataId = { 0x0CD9F899, 0xC9AA, 0x4FC5, { 0x8F, 0x45, 0xE0, 0x81, 0x40, 0x92, 0x45, 0xE9 } };`
- C# consumption: `[Guid("0CD9F899-C9AA-4FC5-8F45-E081409245E9")]` on the class

### 2.2 C++ class — `CRookBlockBasePointUserData`

**File:** `src/RookNative/UserData/RookBlockBasePointUserData.h` + `.cpp` (new directory — first occupant of metadata-infrastructure).

```cpp
class CRookBlockBasePointUserData : public ON_UserData
{
    ON_OBJECT_DECLARE(CRookBlockBasePointUserData);

public:
    CRookBlockBasePointUserData();
    CRookBlockBasePointUserData(const ON_3dPoint& basePoint);
    virtual ~CRookBlockBasePointUserData();

    // ON_Object overrides (exact signatures per OpenNURBS SDK):
    bool Archive() const override;                          // returns true (persist to .3dm)
    bool Write(ON_BinaryArchive& binary_archive) const override;
    bool Read(ON_BinaryArchive& binary_archive) override;
    bool GetDescription(ON_wString& description) override;  // "Rook block basePoint metadata"

    // Payload:
    ON_3dPoint m_base_point = ON_3dPoint::Origin;

    // Scoped helpers (InstanceDefinition only — no ON_Object overload).
    static bool Attach(ON_InstanceDefinition& idef, const ON_3dPoint& basePoint);
    static bool TryRead(const ON_InstanceDefinition& idef, ON_3dPoint& out);
    static bool Remove(ON_InstanceDefinition& idef);
};
```

**Copy/duplicate behavior:**

- Default copy ctor + assignment on `m_base_point` is sufficient (ON_3dPoint is POD).
- In constructor: set `m_userdata_copycount = 1` (enable duplication).
- **Transform semantic (the "not_transformed" invariant).** Rhino 8's C++ OpenNURBS SDK does NOT expose an `m_userdata_xformage` field or an `ON_UserData::not_transformed` enum (verified via grep across the full SDK tree during implementation). The semantic is instead expressed by overriding `virtual bool Transform(const ON_Xform&)` to ignore the incoming xform and return true. Payload `m_base_point` is never derived from the inherited `m_userdata_xform` tracking field, so no additional setup is needed. On managed, the `Rhino.DocObjects.Custom.UserData.Transform` property is inherited but never consulted — same net effect. This is **load-bearing**: basePoint is definition metadata, not geometry in model space; without the override, SDK object-level xform propagation could corrupt the stored value.

**Registration:** `ON_OBJECT_IMPLEMENT(CRookBlockBasePointUserData, ON_UserData, "0CD9F899-C9AA-4FC5-8F45-E081409245E9");` in `.cpp`. OpenNURBS global class registry discovers at plugin load.

### 2.3 C# class — `RookBlockBasePointUserData`

**File:** `src/Rook/UserData/RookBlockBasePointUserData.cs` (new directory, first occupant).

```csharp
[Guid("0CD9F899-C9AA-4FC5-8F45-E081409245E9")]  // MUST match C++ constant
public class RookBlockBasePointUserData : Rhino.DocObjects.Custom.UserData
{
    public Point3d BasePoint { get; set; } = Point3d.Origin;

    public override string Description => "Rook block basePoint metadata";
    public override bool ShouldWrite => true;

    protected override void OnDuplicate(UserData source)
    {
        if (source is RookBlockBasePointUserData other)
            BasePoint = other.BasePoint;   // exact-copy semantics
    }

    protected override bool Read(BinaryArchiveReader archive)  { /* symmetric to C++ Read */ }
    protected override bool Write(BinaryArchiveWriter archive) { /* symmetric to C++ Write */ }

    // Scoped helpers (InstanceDefinition only):
    public static bool Attach(InstanceDefinition idef, Point3d basePoint);
    public static bool TryRead(InstanceDefinition idef, out Point3d basePoint);
    public static bool Remove(InstanceDefinition idef);
}
```

Registration via `[Guid]` attribute only — RhinoCommon's UserData loader discovers registered managed types at archive-load time via reflection.

### 2.4 Binary serialization format (versioned chunk)

Format inside a single chunk:

```
BeginWrite3dmChunk(TCODE_ANONYMOUS_CHUNK, major=1, minor=0)
    WriteDouble(base_point.x)
    WriteDouble(base_point.y)
    WriteDouble(base_point.z)
EndWrite3dmChunk
```

**Version policy:**

- `major=1, minor=0` today.
- Minor bump = additive (new optional fields appended inside the chunk; older readers ignore trailing bytes).
- Major bump = breaking (field order / required-field change). Older readers see unknown-major, treat as missing, fall through to legacy fallback. No log (forward-compat is expected, not erroneous).

### 2.5 Key name stability

The **logical key** `rook_block_base_point` stays stable across the storage change — it's still the legacy string key, and `Description` references it. Consumers reading the design doc or logs continue to see the same string they saw under the PR #25 / #30 storage.

---

## 3. Data flow

### 3.1 Native — write path (dual-write during transition window)

Sole native writer helper — `StoreDefinitionBasePoint(ON_InstanceDefinition&, const ON_3dPoint&)`:

```cpp
void StoreDefinitionBasePoint(ON_InstanceDefinition& idef, const ON_3dPoint& basePoint)
{
    // Detach any pre-existing payload to guarantee post-condition invariant #1.
    CRookBlockBasePointUserData::Remove(idef);

    // Attach fresh.
    CRookBlockBasePointUserData* ud = new CRookBlockBasePointUserData(basePoint);
    idef.AttachUserData(ud);

    // Transition-window legacy write (retired in a follow-up PR).
    wchar_t buf[128];
    swprintf_s(buf, 128, L"%.17g,%.17g,%.17g", basePoint.x, basePoint.y, basePoint.z);
    idef.SetUserString(kRookBlockBasePointKey, buf);
}
```

**Strong post-condition.** After this helper returns successfully, the live `idef` satisfies **all three**:

1. **Exactly one** `CRookBlockBasePointUserData` attached — not zero, not stale, not duplicated.
2. That instance's `m_base_point` equals the supplied `basePoint` value (bitwise on doubles, round-tripping through `ON_BinaryArchive`).
3. Legacy user-string `rook_block_base_point` holds the same value formatted as `%.17g,%.17g,%.17g`.

Detach-then-attach is the chosen policy (vs reuse-if-present / update-in-place) — cleaner invariants, marginally slower, no ambiguity through opaque SDK semantics.

`UpdateDefinitionBasePoint` (rebase helper) inherits the same post-condition. Implementation should attach directly to the live table entry post-`ModifyInstanceDefinition`, not rely on the slice-copy carrying UserData through.

### 3.2 Native — read path (new first, legacy second)

```cpp
static ON_3dPoint LookupDefinitionBasePoint(const CRhinoInstanceDefinition* pDef)
{
    if (!pDef) return ON_3dPoint::Origin;

    // Prefer new Rook-owned slot.
    ON_3dPoint fromUserData;
    if (CRookBlockBasePointUserData::TryRead(*pDef, fromUserData))
        return fromUserData;

    // Fall back to legacy user-string (pre-migration .3dm compatibility).
    ON_wString value;
    if (!pDef->GetUserString(kRookBlockBasePointKey, value))
        return ON_3dPoint::Origin;
    double x = 0, y = 0, z = 0;
    if (swscanf_s(value, L"%lf,%lf,%lf", &x, &y, &z) != 3)
        return ON_3dPoint::Origin;
    return ON_3dPoint(x, y, z);
}
```

### 3.3 Managed — read path (new first, reflection bridge second)

`TryReadDefinitionBasePoint` in `src/Rook/Handlers/BlocksHandler.cs` (current line ~4577) is rewritten to prefer the new slot via `RookBlockBasePointUserData.TryRead(idef, out Point3d)`, falling through to the PR #30 reflection bridge only when the new slot is absent or unreadable.

**Critical invariant:** **once the new slot is present and valid, the reflection bridge is never consulted.** The tri-state return (`Origin` / `Found` / `BridgeFailure`) collapses: `BridgeFailure` is only reachable if the new-slot read also returned empty. After reflection-bridge retirement (follow-up PR), `BridgeFailure` and the `basepoint_bridge_unavailable` batch error code are removed.

**Native vs managed during the transition window.** The new-first read semantic is genuinely active on the native side — `LookupDefinitionBasePoint` (native) hits the real `ON_UserData` slot directly, so whenever the slot is populated it wins over the legacy user-string. Verified by live-Rhino test 9 (`test_disagreement_new_slot_wins`) which clobbers legacy to a divergent value and observes native read return the new-slot value.

On the **managed** side, RhinoCommon 8.0.23304's `InstanceDefinition.UserData` collection does not surface plugin-defined custom `ON_UserData` subclasses to managed callers — diagnosed during Phase C: `idef.UserData.Contains(uuid)` returns `true` (payload is present on native), but `idef.UserData[i]` returns `null` and `idef.UserData.Add(managedUd)` returns `false`. `UserData.RegisterType` (internal, tried via reflection) did not change this. Consequence: the managed `TryReadDefinitionBasePoint`'s new-first branch is **graceful-degrade** code — it always returns "not found" on the new-slot lookup and falls through to the reflection-bridge legacy-string path. Zero behavior change vs PR #30 on managed side during this PR. The new-first shape is retained so the day RhinoCommon exposes the missing surface, managed reads upgrade automatically without a code change. Follow-up #33 (reflection-bridge retirement + legacy-slot-write retirement) carries the "actually read the new slot on managed" requirement as a hard gate.

### 3.4 Mutation-site audit

| Site | File:line | Category | Required action | Notes |
|---|---|---|---|---|
| `HandleBlockCreate` | `BlocksHandler.cpp:920` (`AddInstanceDefinition:1011`) | **Write** | Call `StoreDefinitionBasePoint` on newly-added idef | Existing call site; helper body swap sufficient |
| `UpdateDefinitionBasePoint` helper | `BlocksHandler.cpp:338` | **Write** | Attach directly to live table entry post-modify; maintain strong post-condition | Avoid slice-copy carry-through ambiguity |
| `HandleBlockDuplicate` | `BlocksHandler.cpp:3720` (`AddInstanceDefinition:3753`) | **Write** (explicit) | **Do NOT rely on SDK duplication hooks.** Explicitly read source's basePoint, then `StoreDefinitionBasePoint` on new idef | Safer than assuming copy semantics through opaque duplicate path |
| `HandleBlockRebase` | `BlocksHandler.cpp:3783` | **Write** (via helper) | Inherits `UpdateDefinitionBasePoint` guarantees | `ModifyInstanceDefinitionGeometry:3948` is UserData-neutral |
| `HandleBlockRebaseRecursive` | `BlocksHandler.cpp:4232` | **Write** (per-leaf) | Same | Geometry mutations at `:4458, :4512` UserData-neutral |
| `HandleBlockAddObjects` | `BlocksHandler.cpp:1474` (`:1558`) | **Preserve** | **Verify** SDK preserves UserData through `ModifyInstanceDefinitionGeometry` (assumption, not fact) | Covered by test 10 (`test_preserve_sites_retain_basepoint`) |
| `HandleBlockRemoveObjects` | `BlocksHandler.cpp:1603` (`:1654`) | **Preserve** | Same | Same test |
| `HandleBlockReplaceGeometry` | `BlocksHandler.cpp:1680` (`:1752`) | **Preserve** | Same | Same test |
| `HandleBlockRename` | `BlocksHandler.cpp:1261` (`ModifyInstanceDefinition:1287, 1360`) | **Mask audit** | Confirm userdata-settings mask preserves our payload | Most likely already does; verify + note |
| `HandleBlockUnlink` | `BlocksHandler.cpp:3598` (`:3626`) | **Mask audit** | Confirm UserData survives linked→local conversion | Any present basePoint should survive |
| `HandleBlockLink` | `BlocksHandler.cpp:3477` | **No write** | Externally-authored linked defs do NOT get synthetic origin-basePoint written. Absence = origin via fallback; provenance preserved | Writing origin would blur "known origin" from "inferred origin" |
| `HandleBlockRefresh` | `BlocksHandler.cpp:3551` | **Observed-behavior audit** | Audit whether refresh replaces or preserves existing definition metadata; document observed behavior; ensure no duplicate/stale payloads | Don't promise preservation before verifying |
| `HandleBlockMerge` | `BlocksHandler.cpp:4639` | **Intended rule stated** | Surviving target retains its metadata; discarded source metadata goes with the definition; merge must not create duplicate payloads on survivor | Explicit during implementation |

### 3.5 Managed write policy

**This PR stays read-only on the managed side.** Reflection bridge retained but consulted only as fallback. The companion's `BlocksHandler.CreateBlock` (Issue #29) is the next natural managed-writer, but that belongs in #29's PR, not this one.

Future managed writers (post-#29) must use `RookBlockBasePointUserData.Attach(idef, point)`. Default recommendation for post-#29 managed writers: **do NOT dual-write the legacy string** — managed has no reflection-based writer for the legacy user-string, and forward-only writes from managed are acceptable.

### 3.6 Lifecycle operations

- **Duplicate:** `HandleBlockDuplicate` explicitly reattaches, does not rely on SDK hooks.
- **Copy:** C# `OnDuplicate(UserData source)` does exact-copy of `BasePoint`. C++ default copy ctor suffices; `m_userdata_copycount = 1` enables SDK-level duplication.
- **Rename:** preserved via `ModifyInstanceDefinition` userdata mask.
- **Delete:** freed automatically by SDK on `InstanceDefinitions.Delete` (standard ON_Object lifetime).
- **Save/load .3dm:** `Archive() = true` + `Read`/`Write` implementations serialize through the standard archive pipeline.

### 3.7 Round-trip guarantees

This PR commits to:

1. `.3dm` save/load round-trip: basePoint survives close/reopen.
2. Rebase round-trip: `rhino_block_rebase` updates new slot; legacy string stays synchronized during transition.
3. Duplicate round-trip: `rhino_block_duplicate` produces new idef with source's basePoint.
4. Preserve-path survival: basePoint metadata attached to a definition survives `ModifyInstanceDefinitionGeometry` calls (add-objects, remove-objects, replace-geometry).
5. Mixed-era reads (scoped to this PR): **legacy-only defs read correctly via fallback**, and **both-present prefers new**. **New-only read is the intended post-retirement behavior** and will be exercised as part of follow-up #33 where legacy removal is the actual goal; this PR verifies dual-write and legacy-fallback coexistence, not the standalone new-only state (which isn't a production state this PR produces).

---

## 4. Error handling, coexistence, observability

### 4.1 Read-failure policy

| Condition | Behavior | Rationale |
|---|---|---|
| No UserData attached (slot empty) | Fall through to legacy; origin if legacy absent | Expected pre-migration state; NOT a failure |
| UserData present, **unknown major version** | Ignore new slot; fall through to legacy; no log | Forward-compat for older builds reading newer files |
| UserData present, **known major, malformed/truncated** | Debug-build log; fall through to legacy | Runtime continuity over strict failure; logging surfaces anomaly without noise |

Never fail-loud on read. This is persistence compatibility, not request validation.

### 4.2 Coexistence + disagreement policy

| Slots present | Action | Authoritative value |
|---|---|---|
| New only | Read new | UserData's basePoint |
| New + legacy (agree) | Read new; ignore legacy | UserData's basePoint |
| New + legacy (disagree) | **Read new; debug-log mismatch** | UserData's basePoint wins |
| Legacy only | Read legacy (fallback) | Legacy's basePoint |
| Neither | Return origin | `ON_3dPoint::Origin` |

Debug-build mismatch warning:
```
[Rook] basePoint disagreement on idef '<name>': UserData=(1,0,0), legacy=(2,0,0). UserData wins.
```

Disagreement is expected during the transition window if a third-party tool or older Rook build mutates one slot without the other. Logging lets us verify the transition is clean before retiring legacy.

### 4.3 Logging scope

**Debug-only for this PR.** Release builds stay silent on read-side anomalies. If real-world drift appears in logs / bug reports, specific cases can be promoted to always-on in follow-ups.

### 4.4 Observability

Minimum to diagnose field failures:

- Debug-build warning on **malformed/truncated payload for a known major version** and on **slot disagreement**.
- **No log on unknown major version** — forward-compat with newer builds is expected, not an anomaly (matches §4.1).
- Class `Description` returns `"Rook block basePoint metadata"` — surfaces in RhinoCommon's object-inspection UI for anyone debugging an idef interactively.

---

## 5. Testing + reviewable checkpoints

### 5.1 Test additions

Everything verified through live Rhino pytest harness from PR #32. No in-process C++/C# unit-test scaffolding for this PR (setup cost exceeds value for a storage-layer change).

**Critical — dual-write shadows naive behavior tests.** While legacy dual-write is active, a behavior-based "read back basePoint" assertion can't distinguish "new slot working" from "legacy fallback filled in." Without an explicit new-slot-presence check, tests 5-8 would pass even if the new slot were silently broken. Fix: add a narrowly-scoped test-only introspection helper (see §5.2) and use it as an additional assertion in the tests that claim new-slot behavior.

**New tests** in `mcp_server/tests/test_block_replace_object_geometry_live.py` (each marked `@pytest.mark.requires_rhino`):

| # | Test | Verifies |
|---|---|---|
| 5 | `test_new_slot_populated_on_block_create` | After `rhino_block_create` with basePoint=(5,0,0): behavior-based read returns (5,0,0) **AND** introspection helper confirms exactly one `RookBlockBasePointUserData` is attached to the idef with `BasePoint == (5,0,0)`. |
| 6 | `test_save_load_roundtrip_preserves_basepoint` | Create non-origin-basePoint def, save `.3dm`, close, reopen, verify basePoint survives via behavior read **AND** introspection helper confirms the new slot survived the archive round-trip. Proves `Archive()` + binary contract end-to-end. |
| 7 | `test_block_duplicate_carries_basepoint` | Create basePoint=(5,0,0) def, duplicate it, verify new def's basePoint matches via behavior read **AND** introspection helper confirms the duplicate has its own attached UserData instance (not shared). Exercises `HandleBlockDuplicate`'s explicit reattach. |
| 8 | `test_block_rebase_updates_new_slot` | Create def, rebase, verify new basePoint reflects the rebase via behavior read **AND** introspection helper confirms the UserData's `BasePoint` field now holds the updated value (proves `UpdateDefinitionBasePoint`'s strong post-condition invariant #2, not just legacy fallback). |
| 9 | `test_disagreement_new_slot_wins` | Write new-slot basePoint=(5,0,0) via normal `rhino_block_create` (which dual-writes both slots), then clobber ONLY the legacy user-string to `"99,0,0"` via a test-only native debug route (`POST /block/_debug/set-legacy-basepoint`, off the MCP grid). Confirm the **native** read path resolves to (5,0,0) — test exercises `rhino_block_replace_geometry` (native-backed, routes through `LookupDefinitionBasePoint`) specifically because of the §3.3 managed-side SDK limitation: a companion-path test cannot prove "new slot wins" during this transition window (managed always falls through to the legacy path). Follow-up #33 adds managed-path coverage when that SDK surface is resolved. **This test does not need the introspection helper — the disagreement itself isolates new-slot behavior.** |
| 10 | `test_preserve_sites_retain_basepoint` | Single test exercising all three native preserve paths in sequence. Create basePoint=(5,0,0) def, then: (a) `rhino_block_add_objects` → introspection assert slot still attached with value (5,0,0); (b) `rhino_block_remove_objects` → assert again; (c) `rhino_block_replace_geometry` (the native full-set replacement) → assert again. Proves `ModifyInstanceDefinitionGeometry` does not silently drop attached UserData during geometry mutations. |

**Mandatory in this PR:** all six tests above.

**Existing 4 tests** from PR #32 stay unchanged. They're the transparency regression check — they pass if the migration is correct end-to-end.

### 5.2 Test-only introspection helper (mandatory, not optional)

**Per finding 2 resolution — without this helper, tests 5-8 cannot actually prove the new slot works during the dual-write window.**

Helper `assert_new_slot` lives in `mcp_server/tests/conftest.py` and hits a **native-internal HTTP debug route** (`POST /block/_debug/basepoint-userdata`) directly via `httpx`, bypassing the MCP tool layer entirely. The route reads the `CRookBlockBasePointUserData` off the live `ON_InstanceDefinition` and returns `{attached: bool, basePoint: [x,y,z]}` — it's an internal/test-only hook, never registered as an MCP tool, no stable contract, product code must not depend on it.

Why native HTTP instead of managed reflection (as originally proposed): RhinoCommon 8.0.23304's `InstanceDefinition.UserData` collection does not surface plugin-defined `ON_UserData` subclasses to managed callers (see §3.3 native-vs-managed note) — a managed-reflection helper cannot observe the slot. Reading directly on the native side, where the `ON_UserData::GetUserData(uuid)` lookup is the real API, avoids the SDK limitation. The `POST /block/_debug/set-legacy-basepoint` sibling route is used by test 9 to clobber the legacy user-string in isolation (leaving the new slot untouched) — likewise off the MCP grid.

```python
async def assert_new_slot(block_name: str, expected_base_point: tuple[float, float, float]):
    """Test-only. Assert a RookBlockBasePointUserData is attached to the named
    idef, with BasePoint matching expected value. Hits native `/block/_debug/
    basepoint-userdata` directly; not exposed as product MCP tool."""
```

**Constraints (enforced by placement + naming):**

- Helper lives in test-support code only. Never imported from product modules.
- Hits an internal native HTTP debug route that is deliberately NOT registered as an MCP tool. No stable contract; safe to remove after follow-up #33 lands legacy retirement.
- Fails the test with a clear message (not a silent pass) if the route is absent — signals Rhino is running a pre-Phase-B native build.

**Disagreement test (9) justification for not needing the helper:** test 9 writes a deliberately-different legacy value, so if the read returned the legacy value the assertion would fail. That structural fact proves new-slot preference without needing direct introspection.

### 5.3 Behavior-vs-introspection balance

Behavior-based read is the primary assertion; introspection is a secondary proof-of-new-slot. Don't let the introspection helper become the ONLY assertion — if RhinoCommon changes how UserData is surfaced, the helper's reflection path can silently break. The behavior read catches that regression; the introspection catches "new slot silently unpopulated." **Both are needed; each test uses both.**

### 5.4 Reviewable checkpoints (single PR, five commits)

One PR. Sequential commits, each passes the full test suite at its boundary. Squash-merge at end.

| # | Commit | Scope | Test state at end |
|---|---|---|---|
| **A** | `feat(blocks): scaffold Rook-owned basePoint UserData class on both sides` | New files + UUID + registration. **No integration anywhere else.** | Existing tests pass; new class compiles + loads |
| **B** | `feat(blocks): dual-write basePoint to new UserData slot in native` | `StoreDefinitionBasePoint` + `UpdateDefinitionBasePoint` updated. Test 5 added — verifies **population only**, not runtime behavior change | Existing tests pass (still reading via legacy); test 5 confirms new slot populated |
| **C** | `feat(blocks): prefer new UserData slot over legacy on read path (native + managed)` | `LookupDefinitionBasePoint` + `TryReadDefinitionBasePoint` new-first. Test 9 added | All tests pass. Behavior switch lands here. |
| **D** | `feat(blocks): explicit basePoint carry-through on duplicate + audit preserve sites` | `HandleBlockDuplicate` explicit reattach. Mask / preserve audits documented inline. Tests 6, 7, 8, 10 | All tests pass including save/load + duplicate + rebase + preserve-site round-trips |
| **E** | `docs(blocks): update design doc + changelog` | Final observations, any last observability logging. Collapsible into D if truly small | Docs only |

**Between commits:** if Codex review flags something, fixes amend the relevant commit (not a new commit) before moving forward.

### 5.5 Acceptance

1. All existing PR #32 live tests pass unchanged.
2. All 6 new tests pass, each with both a behavior assertion AND the introspection-helper assertion where listed.
3. Native compiles clean, no new warnings.
4. Managed compiles clean, no new warnings.
5. Reflection bridge reachable as fallback; not deleted in this PR.
6. No MCP tool surface changes.
7. Follow-up issue (`#33`) filed for reflection-bridge retirement.

### 5.6 Follow-ups after this PR lands

- **#33** (new) — retire reflection bridge + legacy user-string write, gated on ≥1 release window with no mismatch-warning evidence.
- **#29** — now trivial; managed writer uses `RookBlockBasePointUserData.Attach`.
- **#26** — helper refactor targets the clean public API.

---

## 6. Allocated identifiers

| Identifier | Value | Where used |
|---|---|---|
| Rook-owned UserData UUID | `0CD9F899-C9AA-4FC5-8F45-E081409245E9` | Native `ON_OBJECT_IMPLEMENT`, C# `[Guid]` attribute |
| Legacy user-string key | `rook_block_base_point` | Unchanged from PR #25 / #30; transition-window write + fallback read |

---

## 7. Open questions resolved during brainstorming

| Question | Resolution |
|---|---|
| Can native cleanly write to `InstanceDefinition.UserDictionary`? | No — backed by RhinoCommon-private `ON_UserData` (GUID `171E831F-...`). Reframed to Rook-owned slot. |
| 3 doubles vs DoubleArray vs string for payload? | 3 doubles + versioned chunk. Typed, no parse failures, explicit schema. |
| Storage slot attached to what? | `ON_InstanceDefinition` only. No generic `ON_Object` overload. |
| xformage setting? | Rhino 8's OpenNURBS SDK does not expose an `m_userdata_xformage` field or `ON_UserData::not_transformed` enum (verified via grep during Phase A). Semantic is expressed by overriding `virtual bool Transform(const ON_Xform&)` to ignore the xform and return true. Managed side inherits but never consults the equivalent property. Same net effect: basePoint is definition metadata, not model-space geometry. |
| Managed access to plugin-defined UserData on `InstanceDefinition`? | **Unavailable in RhinoCommon 8.0.23304** (diagnosed during Phase C). `idef.UserData.Contains(uuid)=true` but `UserData[i]=null` and `UserData.Add(managedUd)=false`. Managed new-first reads are graceful-degrade code during this transition window — always fall through to the reflection-bridge legacy path. Follow-up #33 blocks on this being resolved. Test-only introspection therefore hits a native internal HTTP route instead. |
| Coexistence disagreement rule? | New UserData wins. Debug-log the mismatch. |
| Managed writes in this PR? | No — read-only on managed side. #29 introduces first managed writer. |
| Reflection bridge lifetime? | Retained as fallback path. Retirement gated on follow-up #33 after ≥1 release window. |
| HandleBlockLink synthetic-origin write? | No. Absence = origin via fallback preserves provenance distinction. |
| Unit tests for C++/C# classes? | Deferred. Live-Rhino coverage is higher value for this change class. |
| Commit granularity? | Single PR, five sequential commits, squash at end. |

---

## Next step

Implementation plan generated via `superpowers:writing-plans` skill, then implementation begins at Commit A.
