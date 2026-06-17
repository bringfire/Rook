# Two-Machine Rook Dev Setup — Plan (Desktop provisioning + laptop continuity)

> **Status:** Direction approved 2026-06-17; decisions locked (below). No step executes until
> the user explicitly approves that phase. Machine-mutating steps are tagged **[APPROVE]**. Steps
> I cannot perform from this desktop (laptop actions, cross-machine copy) are tagged **[USER]**.
>
> **Locked decisions:** (1) OCCT acquisition = **copy verified tree from laptop**. (2) Desktop
> OCCT path = **`C:\OCCT\build-rook`**. (3) Phase 2 vcxproj-default change = **SKIP for now**
> (later, separate tiny PR; only after both machines prove native build/deploy via `OCCT_ROOT`).
> (4) Sequencing = **laptop Phase 0 first**.
>
> **⚠ BRANCH HYGIENE (hard rule):** This provisioning work must NOT contaminate the chat-selector
> branch `feat/rookllm-chooser-slice2.1-panel-selector`. This doc is currently an **untracked**
> file there — that is fine temporarily, but it must NEVER be `git add`ed/committed alongside the
> selector work. When provisioning reaches a commit, move it to its own branch/worktree
> (e.g. `chore/two-machine-dev-setup`) first. Any selector commit must add only the specific
> selector files — never `git add .`.
>
> **`setx` caveat:** `setx` only affects **new** shells. Every phase that sets `OCCT_ROOT` must
> open a **fresh shell** before verifying or building.

## Goal

Make this desktop (`bring`) a first-class Rook dev machine equal to the laptop (`aryan`), able to
build + deploy the full suite (native `RookNative.rhp` w/ OCCT, C# companion `Rook.rhp`, RookBim
for Revit, Python chat runtime). Maximize continuity between the two machines and **never break
the laptop's existing build/deploy.**

## Core principle (why this is robust)

OCCT location is currently resolved by `RookNative.vcxproj` / `OcctPrimitiveTests.vcxproj` as:
`/p:OcctRoot=` → `OCCT_ROOT` env var → hardcoded default `C:\Users\aryan\source\repos\OCCT\build-rook`.

The laptop works today because that hardcoded default *is* the laptop's path. That coupling is the
root fragility. The fix: **set `OCCT_ROOT` explicitly on every machine and stop relying on the
hardcoded user path.** Once both machines set `OCCT_ROOT`, they are decoupled, and the hardcoded
default becomes irrelevant (and safe to neutralize later).

## Desktop readiness (verified 2026-06-17)

| Component | State |
|-----------|-------|
| dotnet | ✅ 10.0.204 (C# builds proven; 2646 tests green) |
| VS 2022 Community + C++ (`VC.Tools.x86.x64`) | ✅ installed (native toolchain present) |
| Revit 2024 + `RevitAPI.dll` | ✅ `C:\Program Files\Autodesk\Revit 2024` (RookBim builds) |
| Repo venv `mcp_server/.venv` (3.12.12) | ✅ working |
| AppData `.env` `ANTHROPIC_API_KEY` | ✅ present |
| Repo on `main` | ✅ `f47ed67` |
| **OCCT** | 🟥 **absent** — `OCCT_ROOT` unset, no `TK*.dll` deployed, default path is the laptop |
| AppData Python runtime | ⚠️ stale (Apr 29; no `model_status.py`) — refreshed in Phase 3 |
| Deployed plugins | ⚠️ Jun 8 (pre-OCCT native + old companion) — refreshed in Phase 3 |

**OCCT is the only true gap.** Everything else is present or auto-handled by the deploy script.

---

## Phase 0 — Laptop continuity (do FIRST; non-breaking) **[USER]**

Make the laptop explicit about OCCT before any repo default changes, so it can never be broken by
later phases.

1. On the **laptop**, set a persistent **user** env var pointing at its existing, verified tree:
   ```powershell
   setx OCCT_ROOT "C:\Users\aryan\source\repos\OCCT\build-rook"
   ```
   This is behaviorally a no-op today (it equals the hardcoded default) but makes the laptop
   independent of the default.
2. Open a **fresh** shell (so the env var is live) and confirm the native build still works:
   ```powershell
   .\build_native.ps1 -Configuration Release
   ```
   Expected: builds `src\RookNative\bin\Release\x64\RookNative.rhp` with no OCCT path errors.

**Gate:** Do not proceed to Phase 2 (repo default change) until the laptop is confirmed building
via its `OCCT_ROOT`.

---

## Phase 1 — Desktop OCCT acquisition + `OCCT_ROOT`

**Decision — acquisition method (recommend A for continuity):**

- **A. Copy the laptop's verified OCCT tree** **[USER copy + APPROVE env var]**
  Maximum continuity: identical OCCT **V8_0_0** artifact on both machines.

  > **CORRECTION (2026-06-17, learned the hard way):** Do **NOT** copy the cmake **build tree**
  > (`build-rook`). On Windows, OCCT's `build-rook\inc\*.hxx` are **forwarding headers** that
  > `#include` absolute paths into the laptop's **source** checkout
  > (`C:\Users\aryan\source\repos\OCCT\src\…`). 5764/5765 headers forward; the source tree is not
  > inside `build-rook`. A copied build tree therefore **cannot compile on another machine** — the
  > desktop native build failed with `C1083: Cannot open include file 'C:/Users/aryan/.../OSD.hxx'`.
  >
  > **Use a relocatable OCCT *install* tree instead.** On the laptop run `cmake --install` (the
  > INSTALL target) to a clean prefix → produces real `inc\` headers (copied, no forwarders) +
  > `win64\vc14\{lib,bin}` (OCCT's standard Windows install layout, which matches the vcxproj's
  > expected `$(OcctRoot)\inc` / `\win64\vc14\lib` / `\win64\vc14\bin`). Zip the **install** tree,
  > transfer, extract to `C:\OCCT\build-rook`, point `OCCT_ROOT` there. (The install MUST run on
  > the laptop, where the OCCT source exists — `cmake --install` from the desktop would also fail.)

  Destination on desktop (machine-neutral): `C:\OCCT\build-rook\`. I verify the tree on arrival:
  `inc\TKernel.hxx` is a **real header** (not a `#include "C:/Users/aryan/..."` forwarder),
  `win64\vc14\lib\TKernel.lib`, `win64\vc14\bin\TKernel.dll`, then a native build smoke.

- **B. Build OCCT V8_0_0 from source** (fallback if copy infeasible) — cmake, modeling modules
  only (no DataExchange), Release. ~30–60 min. Diverges from the laptop only if a different
  version is chosen, so build **V8_0_0** to stay continuous; defer the 7.9.3 pin to a joint
  later step on both machines.

Then **[APPROVE]** set the desktop user env var:
```powershell
setx OCCT_ROOT "C:\OCCT\build-rook"
```

**Gate:** new shell, then confirm `echo $env:OCCT_ROOT` resolves and the tree exists.

---

## Phase 2 — Repo hygiene: neutralize the hardcoded default — **SKIPPED FOR NOW (deferred)**

> **Decision:** Skip. Do **not** touch `.vcxproj` defaults until **both** machines have proven
> native build *and* deploy via `OCCT_ROOT`. If revisited later, it must be its own tiny PR —
> never folded into the chat-selector slice or the provisioning execution. Text below retained
> for when it's picked up.

Only after **both** machines set `OCCT_ROOT` (Phases 0 + 1 done). Change the 3rd-fallback default
in `src/RookNative/RookNative.vcxproj` and `src/RookNative/OcctPrimitiveTests.vcxproj` from the
laptop-specific `C:\Users\aryan\source\repos\OCCT\build-rook` to the neutral `C:\OCCT\build-rook`.

- Safe because both machines now resolve via `OCCT_ROOT` (fallback never reached).
- Improves any *future* machine that places OCCT at the conventional path.
- **Keep this as its own small commit/PR — do NOT fold it into the chat-selector slice branch.**
- Also update `docs/rook_docs/occt-build.md` step 3 to cite the neutral default.

If you'd rather not touch the repo yet, skip Phase 2 — the `OCCT_ROOT`-on-both convention already
fully decouples the machines. Phase 2 is cleanliness, not correctness.

---

## Phase 3 — Full build + deploy on desktop **[APPROVE]**

Close Rhino and any `python -m rook` first (the deploy script refuses otherwise). Then the
canonical local deploy (builds native via msbuild+OCCT, companion all TFMs, RookBim against Revit
2024; syncs the AppData Python runtime; deploys plugins + OCCT runtime DLLs):

```powershell
.\scripts\deploy-local-testing.ps1 -Configuration Release -RevitInstallDir "C:\Program Files\Autodesk\Revit 2024"
```

This also refreshes the stale AppData runtime so the chat server gains `/agent/chat/models` +
`allowed_model_overrides`, and copies the 11 OCCT `TK*.dll` next to `RookNative.rhp`.

Verify the OCCT DLL closure landed:
```
ls "$env:APPDATA\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\TK*.dll"
```

---

## Phase 4 — Verify on desktop **[USER + me]**

1. Launch Rhino; `rhino_ping` → `pong` (native + bridge up on this machine).
2. OCCT engine smoke: run the gated live-verify (e.g. `docs/rook_docs/occt-spike/live_verify_occt_adjacency.py`)
   to confirm the native scene-graph engine works here.
3. **Chat-selector manual checklist** (the slice's pending verification, now against a fully
   current, matching suite — no version-skew):
   (1) ClaudeCodeTab no gap/sliver; (2) selector shows active model; (3) change dropdown → Apply
   enabled, succeeds idle; (4) during streaming Apply disabled + selection preserved; (5) after
   streaming, pending choice stays selected + Apply re-enables; (6) 400 stale-model refresh sane;
   (7) 404 clears selector + restart prompt.

## Phase 5 — Document **[APPROVE]**

Update `AGENT_SETUP.md` with the multi-machine convention: "Set `OCCT_ROOT` on every dev machine;
desktop path `C:\OCCT\build-rook`; never rely on the hardcoded vcxproj default." Capture the
desktop's Revit 2024 path for RookBim builds. This makes the next machine/session reproducible.

---

## Open items — RESOLVED (2026-06-17)

1. **OCCT acquisition:** copy from laptop. *(Still need: the transfer method this desktop can use
   to reach the laptop's `build-rook` tree — network share / external drive / cloud.)*
2. **Desktop OCCT path:** `C:\OCCT\build-rook` — confirmed.
3. **Phase 2 repo change:** skip for now; later separate PR.
4. **Sequencing:** laptop Phase 0 first (user-executed).

## Constraints honored

- Laptop is never broken: Phase 0 makes it explicit before any repo change; Phase 2 only changes a
  fallback the laptop no longer uses.
- Continuity: same OCCT V8_0_0 artifact on both machines (copy), or same version if built.
- No execution until you approve; the chat-selector slice branch stays untouched by this work.
