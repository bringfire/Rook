# Reconstruction 2D→3D — One-Click Import (Slice 2) Design

**Date:** 2026-06-22
**Status:** Approved design, ready for implementation plan
**Base:** `origin/main` @ `b0564bb8` (worktree `.worktrees/reconstruction-import`, branch `feature/reconstruction-ui-import-slice2`)
**Builds on:** Slice 1 (PR #310, merge `ee74eca1`) — the Reconstruct view, which currently shows a completed package + a *handoff* to the agent tool `rhino_2d_to_3d_import` but has no import button.

---

## 1. Problem & framing

Slice 1 deferred one-click import because the actual geometry import is **native-C++-only** ([ImportExportHandler.cpp](../../../src/RookNative/Handlers/ImportExportHandler.cpp) `HandleReconstructionImport`, route `POST /reconstruction/2d-to-3d/import`): it runs `RhinoApp().RunScript("_-Import …")` + object-diff + layer + user-text on the Rhino UI thread, behind the native HTTP surface. The Reconstruct tab is **Pattern A** (in-process WebView, `connect-src 'none'`, no network), so it cannot reach that route.

This slice gives the tab a one-click **Import to Rhino** button by adding a *managed bridge adapter over the existing native importer*: a companion-side op the WebView calls, which delegates to the live-proven native route on the WebView's behalf. The native importer stays authoritative and unchanged — this is **UI access to the already-proven importer, not a new importer and not an import manager.**

It also closes the slice-1 follow-up: the result panel's "Preferred: model_glb" is misleading when the delivered package is an OBJ bundle. We relabel it and surface the *actual* resolved role from the import response.

## 2. Goal (one sentence)

Add a one-click **Import to Rhino** button to the Reconstruct view that imports a completed reconstruction package into the active document by routing `{package_id}` through a new async/off-UI managed `import_package` bridge op → a narrow native-import client (HTTP loopback to the fixed native route) → the unchanged native importer, then drives the UI copy from the native response.

## 3. Architecture (C1 — HTTP loopback adapter)

```
Reconstruct view  ──window.rookBridge.invoke("reconstruction",{op:"import_package",package_id})──▶
VisionWebSurface.HandleReconstructionBridgeCallAsync   [import_package routed ASYNC through DispatchWithTimeoutAsync, domainLabel "Reconstruction"]
        │  (runs OFF the UI thread — the deadlock invariant)
        ▼
ReconstructionOpHandler.DispatchAsync   [new import_package case — keeps reconstruction-domain routing out of the web surface; thin adapter, NOT an importer]
        ▼
NativeReconstructionImportClient  (injected; the ONLY component that does loopback)
        │  1. discover active native endpoint (port) — pluginType "native" AND processId == current process
        │  2. HTTP POST {package_id} to the FIXED route /reconstruction/2d-to-3d/import (no arbitrary URL)
        ▼
Native importer (UNCHANGED)  —  RunScript _-Import + diff + layer + user-text + record + cleanup
        ▼
response { package_id, asset_role (RESOLVED), path, imported_ids[], associated }  → UI copy
```

**Why the off-UI invariant is load-bearing (reentrancy audit, verified on `ee74eca1`):** native HTTP is served on a `ThreadPool(8)` worker (not the UI thread); the import handler runs `_-Import` inside `MainThreadDispatcher::Dispatch(...)`, which **blocks the worker thread on a `std::future` until the UI thread pumps `WM_ROOK_DISPATCH` and runs it**. If the companion's `import_package` op ran on the UI thread and blocked on the loopback response, the UI thread couldn't pump → the native worker's `future.get()` never completes → **deadlock**. The companion op never touches the dispatcher queue, so there is **no shared blocking lock** — the *only* failure mode is a UI-thread-classified import op. Therefore `import_package` **MUST** be async/off-UI, pinned by a source-assertion test.

**Pattern A preserved:** the WebView makes no network calls; only the managed companion performs loopback. CSP `connect-src 'none'` is untouched.

**Native authoritative:** zero change to native import behavior. MCP (`rhino_2d_to_3d_import`) and the UI now use the same route. If native gains auth later, **only `NativeReconstructionImportClient` needs adjustment.**

## 4. Components

### 4.1 `NativeReconstructionImportClient` (new, managed) — the narrow adapter
- **Endpoint discovery:** read native discovery file(s) from `RookPaths.SharedDiscoveryFolder` (fallback `DiscoveryFolder`); select the entry with `pluginType == "native"` **AND `processId == Process.GetCurrentProcess().Id`** (the native discovery file's field is **`processId`**, not `rhinoProcessId`; native and companion share the OS process, so the current process id matches). This filter is load-bearing: in a multi-Rhino setup it prevents looping back into a *different* instance's native server. If no matching entry → structured failure (`native_unavailable`), **no import attempted**.
- **Request:** HTTP POST to the **fixed** path `/reconstruction/2d-to-3d/import` on the discovered `127.0.0.1:{port}` with body `{ "package_id": "<guid>" }` only. No arbitrary URL, no other routes.
- **Response mapping (the native route uses its own `{success,data}` envelope):** parse the native JSON; **require `success == true`** and return the inner **`data`** object (`package_id, job_id?, asset_role, path, imported_ids[], associated`) as the op payload — do **not** double-wrap the native envelope. If `success == false` (e.g. `association_failed`, see §6) or non-2xx, return a structured failure carrying the native `data.{code,message,details}` when present; on transport fault / no endpoint, `native_unavailable`.
- **Auth isolation:** the no-auth reliance lives *only* here. (Today the native server enforces no bearer/token auth on `127.0.0.1` routes — verified on `ee74eca1`.)
- Injected `HttpClient` for testability (fake transport in tests).

### 4.2 Bridge op `import_package` — routed through `ReconstructionOpHandler`
- `VisionWebSurface.HandleReconstructionBridgeCallAsync` routes the new op `"import_package"` **async/off-UI** through `DispatchWithTimeoutAsync(op, AsyncOpTimeout, ct => RookSubsystemRoot.Instance.Reconstruction.DispatchAsync(body, ct), domainLabel: "Reconstruction")` — the **same async lane** the existing reconstruction async ops use. The web surface stays thin; reconstruction-domain routing lives in the handler.
- `ReconstructionOpHandler.DispatchAsync` gains an `import_package` case that delegates to an **injected `NativeReconstructionImportClient`**. The handler *does* gain an `import_package` op, but **no importer** — it is a thin adapter to the native route; native remains authoritative.
- `package_id` parsing: missing/invalid → structured `invalid_request` failure (no loopback). Reuse the handler's existing GUID/arg validation.
- The client is injected into `ReconstructionOpHandler` via the shared `RookSubsystemRoot` wiring, consistent with the catalog/manager/store dependencies.

### 4.3 Reconstruct view UI (`app.js`, `index.html`, `styles.css`)
- **Import button** in the result panel (`#reconstruct-result-panel`), shown when a completed package is loaded (fresh job completion *or* a job-history click that loaded `job_result`).
- **States / copy:**
  - idle: **Import to Rhino**
  - in-flight: **Importing…** (button disabled)
  - success: status **Imported N object(s) as `{asset_role}`** (button re-enabled); N from `imported_ids.length`, role from `asset_role`.
  - failure: show the structured native failure message if present, else a generic "Import failed."
- **Re-import allowed:** button disabled only while in flight; after success it re-enables. Re-import duplicates geometry — consistent with native behavior. No idempotency guard.
- **Relabel:** the result panel's `Preferred:` line becomes **`Catalog preferred:`** so it reads as the catalog's preference, not a claim that the role is in the delivered package.

## 5. Contracts

- **Bridge request:** `{ op: "import_package", package_id: "<guid>" }`
- **Bridge success:** the **unwrapped inner `data`** from the native envelope — `{ package_id, job_id?, asset_role, path, imported_ids[], associated }` — re-wrapped once by the bridge as `{success:true, data:…}`. The client strips the native `{success,data}` first, so the UI reads `asset_role`/`imported_ids` at the top level of the bridge `data`, not nested twice.
- **Bridge failure:** `{success:false, data:{ code, message, ... }}` — unwrapped by the existing `reconstructionBridgeCall` into `errorToText`.
- **Native route (unchanged):** `POST /reconstruction/2d-to-3d/import`, body `{ package_id, targetLayer?, assetRole? }`. This slice sends only `package_id`.

## 6. Error handling
- **No matching native endpoint** (discovery empty/ambiguous, or no `processId` match) → `native_unavailable` structured failure; **no import attempted**; UI shows the message.
- **Loopback transport fault / native non-2xx** → propagate native `{code,message}` if present, else `import_failed`; UI status shows it.
- **Association failure is NOT a success today.** Native sets `wr.success = associated`; when user-string association fails it records history and then returns a structured **`association_failed` failure** (HTTP 500, `success:false`) — *not* a 2xx success. The client maps it to a bridge failure and the UI shows the structured native message. `details` may carry the imported ids, but the UI must **not** present it as a clean import unless/until native changes that contract.
- **Off-UI invariant** is a *correctness* guard, not a runtime check — enforced by the routing classification + its test.

## 7. Testing strategy
- **Routing invariant (C# source assertion, like slice-1 Task 1):** assert `import_package` is async/off-UI — `HandleReconstructionBridgeCallAsync` routes it through `DispatchWithTimeoutAsync` into `Reconstruction.DispatchAsync` (the async lane), and it is **not** in any UI/off-UI-sync branch. A future edit that makes it UI-thread fails this test. This is the deadlock gate.
- **Native-import client request/response mapping (C# unit, fake `HttpClient`/transport):**
  - POSTs only to the fixed `/reconstruction/2d-to-3d/import` path with body `{package_id}` (assert no other route, no arbitrary URL).
  - native `{success:true, data:{asset_role, imported_ids,…}}` → **unwraps** and returns `data` (assert no double-wrap; `asset_role` at the top level of the result).
  - native `{success:false, data:{code:"association_failed",…}}` or non-2xx → mapped structured failure; transport fault / no endpoint → `native_unavailable`.
- **Discovery selection (C# unit) — load-bearing:** given multiple native discovery entries, selects the one whose **`processId == Process.GetCurrentProcess().Id`**; rejects entries for other PIDs; missing/ambiguous → `native_unavailable` (no endpoint returned). Multi-Rhino must never select the wrong server. (Field is `processId`, **not** `rhinoProcessId`.)
- **JS panel-dark gate** (per slice-1 discipline): `node --check`, no duplicate IDs, every Reconstruct-module `$()` id exists in `index.html`, no stale symbols.
- **Manual Rhino smoke (merge gate):** deploy the managed build (Release → DeployToRhino), open Reconstruct, load a completed package, click **Import to Rhino** → objects appear in the active doc, status reads "Imported N object(s) as model_obj", re-import duplicates. Failure path: stop the native server / force a bad package id → structured failure shown.
- Full managed suite green (`dotnet test -c Debug`).

## 8. Out of scope (deferred)
- **Target-layer UI** and any layer-grouping/auto-layer policy (pulls on naming convention, reuse-vs-create, failure explanation — design separately).
- **`assetRole` override UI** (the MCP marks it advanced/discouraged).
- **Select / zoom-to-imported** (response returns `imported_ids` — easy later add).
- **Duplicate-import confirmation / idempotency guard** ("already imported once — again?").
- **Pre-import "will import model_obj" preview** — would need a *non-mutating* resolver op; do **not** call `prepare_import` (it stages temp bundles for OBJ) just to render preview copy.
- **C2 in-process P/Invoke convergence** and the broader **Approach A managed-importer migration** — a separate "native import API convergence" slice if still wanted after this ships.

## 9. Verify-before-relying checklist (carried into the plan)
1. Native discovery file **schema CONFIRMED** (`RookServer.cpp:2238-2244`): `host`, `port`, `pluginType:"native"`, **`processId`** (= `GetCurrentProcessId()`), `startTime`, `pluginVersion`. Client matches `pluginType=="native"` AND `processId == Process.GetCurrentProcess().Id`. (`rhinoProcessId` is a *chat/MCP* discovery field — NOT in the native file.)
2. Native import **envelope CONFIRMED** (`ImportExportHandler.cpp`): success = `{success:true, data:{package_id, asset_role, path, imported_ids[], associated}}` (HTTP 200, line ~614); association failure = structured `association_failed` (`success:false`, HTTP 500). Re-confirm on the build base.
3. `NativeReconstructionImportClient` is injected into `ReconstructionOpHandler` via `RookSubsystemRoot`, mirroring the catalog/manager/store wiring; `VisionWebSurface` just routes `import_package` into the existing async lane.
4. `DispatchWithTimeoutAsync` + `domainLabel` reuse (from slice 1) is intact on the base.
