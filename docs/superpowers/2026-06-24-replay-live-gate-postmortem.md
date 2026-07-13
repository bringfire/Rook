# RookVisionDirector Native Replay — Live-Gate Post-Mortem (2026-06-24)

> **DIRECTOR HISTORICAL EVIDENCE — classified 2026-07-13:** Director routes,
> tool names, and workflows below are retained only as dated evidence. They are not
> current instructions and must not be used to restore a Director MCP tool. See the
> [Director MCP Surface Retirement Design][director-mcp-retirement].

[director-mcp-retirement]: specs/2026-07-13-director-mcp-surface-retirement-design.md

> ## ✅ RESOLVED — Task 6 live gate is GREEN. The "garbage `req`" diagnosis below was a GHOST.
>
> **Final outcome (2026-06-24, later same day):** `test_director_replay_live.py` passes **6/6**
> on a fully clean from-scratch build. The blocking "garbage `req` reference (UB)" characterized
> in §2 was **never a source defect** — it was **incremental/native build nondeterminism** (MSVC
> incremental LTCG codegen). The original sections are preserved below for the diagnostic trail;
> read this banner + §9 (Resolution) for the truth. Do **not** act on §2–§4 as if the bug is open.
>
> **What cracked it:** a *hardened, crash-safe* boundary probe — log `&req`/`&res` and
> `req.body.size()` at **both** the RookServer call site **and** the handler entry, each value
> `fflush`'d, and **never touch `req.path`/`method`/`headers`** (walking those on a corrupt `req`
> is what produced the earlier 15 s hang → hard crash). The trace showed **matching `&req`,
> `&res`, and `body.size()` at both boundaries across every real request** → `req` passing is
> flawless. The earlier `SIZE_MAX`/`0`/crash trio came from three successive **incremental**
> builds: the front-end `obj/` was wiped between them but the **LTCG cache (`.iobj`/`.ipdb` in
> `bin/`) was carried forward**, so `HandleDirectorReplay`'s machine code was a stale/miscompiled
> artifact. Forcing a full clean rebuild (`"Previous IPDB not found, fall back to full
> compilation — all 43367 functions compiled"`) → correct codegen → 6/6 green.
>
> **Durable lesson (native-debugging rule):** before diagnosing ABI / ODR / request-boundary
> corruption in the native plugin, **force a fully clean rebuild** (wipe both `obj/` **and** the
> LTCG `.iobj`/`.ipdb` in `bin/`) and redeploy. **Do not trust incremental-build behavior for this
> class of issue.** A symptom that *changes across rebuilds* (`0` → `SIZE_MAX` → crash) is the
> signature of build nondeterminism, not deterministic source UB.

---

## ORIGINAL HAND-OFF (preserved for the diagnostic trail — superseded by the banner above)

**(Historical — the bug described here is RESOLVED.)** PR2 "native replay" is code-complete and
reviewed (Tasks 1–5). At the time of writing it appeared **BLOCKED at the live gate (Task 6)** by
what looked like a garbage `req` reference. That characterization was wrong; see the banner.

---

## — Historical state at original handoff (NOT current — see banner + §9) —

> Everything from here through §8 describes the workspace **as it was at the original (wrong)
> hand-off**. It is retained only as the diagnostic trail. The "BLOCKED", "garbage `req`", and
> "working tree DIRTY / [DIAG]" claims below are **resolved**: the gate is 6/6 green, the [DIAG]
> was reverted, and the root cause was build nondeterminism (banner) — read §9 for the truth.

## 1. Where we are

- **Branch:** `feature/rookvisiondirector-replay-native` (off `main`).
- **Last commit:** `4ffc6472` (`fix(director): replay loop contract fixes + redraw cleanup; add live tests`).
- **Working tree is DIRTY:** `src/RookNative/Handlers/DirectorReplayHandler.cpp` has **uncommitted temporary `[DIAG ...]` diagnostics** in the payload-cap and JSON-parse error branches of `HandleDirectorReplay` (around lines 84–105). **These MUST be reverted before any commit/PR.** Nothing else is uncommitted. *(Historical — the [DIAG] was reverted; tree is clean.)*
- **Spec:** `docs/superpowers/specs/2026-06-24-rookvisiondirector-replay-native-design.md`
- **Plan:** `docs/superpowers/plans/2026-06-24-rookvisiondirector-replay-native.md`
- **SDD ledger:** `.superpowers/sdd/progress.md` (Tasks 1–5 marked complete + the live-gate notes).

### Tasks 1–5: DONE + reviewed clean (commits)
| Task | Commit | Reviewer | What |
|---|---|---|---|
| 1 | `d67ef636` | opus | Extract shared `DirectorFrame.{h,cpp}` (parsers, `ValidateFrameObjects`, `SetCameraFromFrame`, the real `DirectorObjectPoseGuard` + `DirectorViewportGuard` with `Disarm()` + deleted copy/move, full viewport-guard helper closure). Behavior-preserving; frame-capture refactored to call them. `.vcxproj`/`.filters` updated. |
| 2 | `7788c602` | sonnet | `DirectorReplayHandler.{cpp,h}`: single active-slot registry (`Slot()`, `ReserveReplaySlot`/`ReleaseReplaySlot`/`ReplaySlotReservation` all non-copyable/non-movable) + worker-thread `HandleDirectorReplayCancel` (no Dispatch, type-safe session id, idempotent, no leak). `/director/replay` + `/director/replay/cancel` registered in `RookServer.cpp` (L991–996). |
| 3 | `64a617f4` | opus | `HandleDirectorReplay`: worker-phase pre-parse + validate EVERY frame before Dispatch; one `DispatchDrainSuspension` + one `DirectorViewportGuard`; `std::optional<DirectorObjectPoseGuard>` reseated via `emplace`; restore ordering; error remapping. |
| 4 | `454f76ca` | sonnet | Python `director.run_replay`/`cancel_replay` (thin resolver; track path/inline; uuid session id). |
| 5 | `76705e77` | sonnet | MCP tools `rhino_director_replay` / `rhino_director_replay_cancel`. |
| fix | `4ffc6472` | (live-gate) | P1 cancel-before-frame-0; P1 in-loop `frame_apply_failed`+`frame_index`; P2 relaxed `.Apply()` test + cancel-before-emplace assertion; P3 `SetCameraFromFrame` caller-owns-redraw + drop `SendCodeFrame` + `makeCancelled`; **added `mcp_server/tests/test_director_replay_live.py`**. |

- Source-analysis + Python + MCP tests all green (73 passed cumulatively, plus a pre-existing-unrelated `test_director_publish_video_native_route_is_thin_vision_proxy` failure that predates this branch).
- Native build clean (MSVC `14.44.35207`). Deployed via `scripts/deploy-native.bat`.

---

## 2. THE BLOCKING BUG (Task 6 live gate)

**Symptom:** every `POST /director/replay` fails before doing any replay work — the handler reads an empty/garbage request body. The Python live suite (`test_director_replay_live.py`) is 6/6 failing as a result; it has **not** validated any real replay behavior yet.

**Root characterization (confirmed): `HandleDirectorReplay` receives a garbage/invalid `req` reference — undefined behavior.**

Evidence, via a temporary diagnostic that echoes `req.body.size()` from inside `HandleDirectorReplay`:
- **Build A** (commit-`4ffc6472` deploy): `POST /director/replay {"x":1}` → `payload_too_large [DIAG size=0]` … then after a rebuild,
- **Build B** (same source + expanded DIAG): `POST /director/replay {"x":1}` → `payload_too_large [DIAG size=18446744073709551615]`.
- `18446744073709551615 == SIZE_MAX == (size_t)-1`. **`req.body.size()` returned different garbage across rebuilds for the identical request** → the `req` reference is not pointing at a valid `httplib::Request`. (A genuinely empty body would deterministically be `0`, never `SIZE_MAX`.)

**Critically — it is replay-SPECIFIC.** On the *same* native instance / port, with the *same* httpx/urllib client:
- `POST /director/object-states {"object_ids":["x"]}` → reads body fine (`"Invalid object id: x"`).
- `POST /director/frame-capture {"hello":"world"}` → reads body fine (`"schema_version must be 1"`).
- `POST /director/replay/cancel {"replay_session_id":"abc"}` → reads body fine (`no_active_replay`).
- `POST /director/replay {...}` → garbage `req.body`.

`HandleDirectorReplay` and `HandleDirectorReplayCancel` are in the **same .cpp**, declared in the **same header**, **registered identically** in `RookServer.cpp` — yet only `replay` gets a bad `req`.

---

## 3. What is RULED OUT (don't re-investigate)

- **Client / httpx:** reproduced identically with httpx `json=`, httpx raw `content=` + explicit `Content-Length`, and stdlib `urllib`. Server-side.
- **Multiple/stale native instances:** only one `pluginType:"native"` instance (port 62592, pid 47012). The roadcreator instance (62601) is a different plugin. All probes hit the one native port.
- **Stale build:** the deployed `RookNative.rhp` mtime is newer than the `.cpp` edits; `DirectorReplayHandler.obj` recompiled (mtime newer than source). `cancel` returns the *current* code's reason strings, so the loaded binary is current.
- **Registration shape:** exactly one `m_server->Post("/director/replay", [this](const httplib::Request& req, httplib::Response& res){ Rook::Handlers::HandleDirectorReplay(req, res); });` at `RookServer.cpp:991`. No duplicate, no content-reader (3-arg) form, no wildcard/regex route shadowing it. Identical form to the working `frame-capture` (L988) and `cancel` (L994).
- **Header signature / forward-decl:** `DirectorReplayHandler.h` declares `void HandleDirectorReplay(const httplib::Request& req, httplib::Response& res);` and forward-declares `namespace httplib { struct Request; struct Response; }` — **byte-identical** to the working `DirectorHandler.h`. The `.cpp` definition signature matches the declaration exactly.
- **The payload-cap math:** `kMaxPayloadBytes = 8u*1024u*1024u`, `if (req.body.size() > kMaxPayloadBytes)` — correct. The earlier "spurious payload_too_large on a 3 KB body" was this same garbage-`req` bug (garbage size happened to exceed 8 MiB), NOT a wrong constant.

---

## 4. Hypotheses to test next (ordered)

The bug is a garbage `req` reference reaching `HandleDirectorReplay` while identical neighbors are fine. Leading theories:

1. **ABI / stack-frame issue from the very large function.** `HandleDirectorReplay` is large with a big Dispatched lambda capturing many locals (`perFrameObjects`, `perFrameCameras`, `std::optional<DirectorObjectPoseGuard>`, etc.). `req` is read at the top (before the lambda), so this is a long shot, but a corrupted prologue / calling-convention mismatch would fit "garbage at entry." **Test:** add a diagnostic that prints `&req` (the address) and compare to what the RookServer.cpp lambda passes (`printf("%p")` at both the call site and the entry). If the addresses differ, it's an ABI/calling-convention mismatch.
2. **Two `httplib::Request` types / ODR or PCH inconsistency.** `DirectorReplayHandler.cpp` includes `stdafx.h` (PCH) FIRST, then the forward-declaring `DirectorReplayHandler.h`, then `RookServer.h` (the real httplib). If `stdafx.h` pulls a *different* httplib than `RookServer.h`, or the layout of `httplib::Request` seen when compiling `HandleDirectorReplay`'s body differs from the layout at the call site, `req.body` reads at the wrong offset → garbage. **Test:** compare the include graph / httplib include of `DirectorReplayHandler.cpp` vs `DirectorHandler.cpp` (the working one). Make `DirectorReplayHandler.cpp`'s httplib include order match `DirectorHandler.cpp` exactly. Check whether `DirectorHandler.cpp` includes `RookServer.h` before or after the handler header, and whether it includes httplib directly.
3. **A clean rebuild (`/t:Rebuild` or delete `src/RookNative/obj/`).** Incremental builds have already produced one confirmed staleness symptom this session. A guaranteed-clean rebuild rules out a stale object that a header change should have invalidated but didn't. Cheap; do this FIRST before deep ABI spelunking.
4. **`Rook::Handlers::` qualification vs the others.** `replay`/`cancel` use `Rook::Handlers::HandleDirectorReplay(req,res)`; `frame-capture` uses unqualified `HandleDirectorFrameCapture(req,res)`. `cancel` works with the qualified call, so this is unlikely — but if all else fails, try matching `frame-capture`'s unqualified style (add `using namespace Rook::Handlers;` or move the registration into the namespace) to see if it changes anything.

**Fastest path:** (3) clean rebuild → if still broken, (1) print `&req` at the RookServer call site and at `HandleDirectorReplay` entry. Same address but garbage contents ⇒ type-layout/ODR (theory 2). Different address ⇒ calling-convention/ABI (theory 1).

---

## 5. The temporary diagnostic currently in the working tree (REVERT before commit)

In `src/RookNative/Handlers/DirectorReplayHandler.cpp`, `HandleDirectorReplay`:
- the `payload_too_large` branch message has `+ " [DIAG size=" + std::to_string(req.body.size()) + "]"`,
- the JSON-parse `catch` message has the expanded `[DIAG bodysize=… method=… CL=… CT=… nhdr=… path=… params=…]`.

`git diff src/RookNative/Handlers/DirectorReplayHandler.cpp` shows exactly these. Revert them (restore the plain `"Request body exceeds 8 MiB limit"` and `"Request body is not valid JSON"` strings) once the root cause is fixed. The committed `4ffc6472` version has the clean strings.

---

## 6. How to resume the live loop (Rhino dance)

The user controls Rhino launch ([[feedback_user_controls_rhino_launch]]). Routes are **always-on** (no env flag — that was the old throwaway spike). `fresh_document` tests reset the doc — confirm the open doc is throwaway first ([[feedback_destructive_fixtures]]).

1. Make a code change. Rebuild+deploy needs **Rhino closed** (the `.rhp` is file-locked while open): `cmd /c "scripts\deploy-native.bat"` **via the PowerShell tool** (Git Bash `cmd /c` emits only a banner — confirm `Build succeeded` + `Deploy succeeded`).
2. Ask the user to launch: `& "C:\Program Files\Rhino 8\System\Rhino.exe"`, open a throwaway doc.
3. `rhino_ping` → `pong`.
4. Probe one route via a short python `httpx` script using `bridge.discover_instances()` → the `pluginType=="native"` port, or run `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_director_replay_live.py -v`.

The live suite (`test_director_replay_live.py`): `test_replay_completes_and_restores`, `…restore_on_finish_false_leaves_final_frame`, **`test_replay_cancel_mid_replay` (the load-bearing gate)**, `…already_active`, `…validation_errors_live`, `…malformed_later_frame_rejected_without_mutation`. It builds a real track from a created line via `/director/object-states`.

> Note: `test_replay_malformed_later_frame_rejected_without_mutation` also expects `track_invalid` but an earlier probe showed `invalid_input` for a wrong-object-id frame — once the body bug is fixed, re-check whether the worker-phase set-equality check emits `track_invalid` for that case (it should, with the offending `frame_index`); may need a small remap tweak.

---

## 7. Deferred Minors (for the eventual final whole-branch review / PR polish)

- Task 1: the `DirectorObjectPoseGuard::Apply()` internal `Redraw()` is still separate from the now caller-owned camera redraw — acceptable, noted.
- Task 4: a couple of tests assert `DirectorError` where `DirectorInputError` is raised (subtype, brief-mandated); `cancel_replay` non-string rejection isn't explicitly unit-tested (impl is correct).
- Task 5: the dispatch test doesn't assert the success/error envelope shape; the schema test uses `<=` subset rather than `==` exact on properties.
- Whole branch: still needs the final whole-branch code review + `superpowers:finishing-a-development-branch` once the live gate is green.

---

## 8. One-paragraph summary for a fresh context

PR2 native replay (synchronous, guarded, cancellable display-only replay of a baked
animation track) is implemented and reviewed across 5 tasks on
`feature/rookvisiondirector-replay-native` (tip `4ffc6472`, working tree has only
temporary `[DIAG]` edits to revert). The live gate is blocked: the native
`/director/replay` handler gets a **garbage `req` reference (UB)** — `req.body.size()`
returns nondeterministic garbage across rebuilds (`0`, then `SIZE_MAX`) — so the body
is never read, while `/director/replay/cancel`, `/director/frame-capture`, and
`/director/object-states` (same file/header/registration form) all read their bodies
fine. Ruled out: client, stale build, duplicate/content-reader registration, header
signature/forward-decl (all identical to working handlers). Next: clean rebuild, then
print `&req` at the RookServer call site vs the handler entry to distinguish an
ABI/calling-convention mismatch from an httplib type-layout/ODR/PCH inconsistency
(compare `DirectorReplayHandler.cpp`'s include order against the working
`DirectorHandler.cpp`).

---

## 9. Resolution (2026-06-24, authoritative)

The §8 summary above is **historical and wrong** — kept only to show what the next session
inherited. The actual resolution:

1. **The decisive experiment** (the `&req`-at-both-boundaries probe §4 recommended) was run, but
   **crash-safe**: file-logged `&req`/`&res` then `body.size()` (each `fflush`'d) at the call site
   and at handler entry, touching nothing else on `req`. Result — identical at both boundaries for
   every request (e.g. `&req=…E8B0`, `body.size=1784`; `…E550`, `1299`; `…E7F0`, `10306`; the
   cancel test's two in-flight requests both clean). **`req` is passed correctly. No ABI mismatch,
   no ODR/layout skew, no garbage reference.**
2. **Root cause:** MSVC **incremental LTCG codegen nondeterminism**. Across the three earlier
   builds the front-end `obj/` was wiped but the LTCG `.iobj`/`.ipdb` in `bin/` was not, so
   `HandleDirectorReplay`'s code was carried forward as a stale/miscompiled artifact whose
   manifestation flipped per build (`0` → `SIZE_MAX` → hard crash). The oversized 250-line handler
   was merely the most codegen-fragile surface for it to land on — **not** a logic defect.
3. **Fix:** a fully clean rebuild (wipe `obj/` **and** `bin/` so the LTCG cache is gone) → MSVC
   logs `"Previous IPDB not found, fall back to full compilation"` / `"all 43367 functions
   compiled"` → correct codegen. `test_director_replay_live.py` → **6/6 PASS**, confirmed on both
   the instrumented clean build and a clean from-scratch build. `cancel_mid_replay` and
   `malformed_later_frame_rejected_without_mutation` pass as-is (the §6 remap worry was moot).
4. **Deferred (reviewer call, not a blocker):** decompose `HandleDirectorReplay` onto the shared
   frame-capture request envelope (`ParseBodyAndDocSn` + a typed replay-request parser + a smaller
   dispatch lambda) in its own follow-up PR, guarded by the same 6-test live gate. This is
   maintainability/codegen-fragility hardening — the feature is behaviorally correct as shipped.
5. **Process lesson now durable:** see the banner's native-debugging rule. The previous session's
   error was trusting incremental-build evidence and theorizing UB from it; the cheap correct move
   (a forced clean rebuild) was deprioritized behind deep ABI/ODR spelunking.
