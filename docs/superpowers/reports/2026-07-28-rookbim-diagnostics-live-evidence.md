# RookBIM Gated Diagnostics Live Evidence

**Date:** 2026-07-28

**Status:** Diagnostic mechanism verified on a controlled file-workshared Revit 2024.3 fixture; original-model acceptance unavailable

**Implementation commit:** `ca90a4287f873186f437bc3729e9ff5d4e1a3234`

## Scope and conclusion

The enabled diagnostic build ran in Revit 2024.3 with Rhino.Inside.Revit and a controlled file-workshared local model. The run proved the original RookBIM failure boundary exactly:

> Rook calls `Document.WorksharingCentralGUID` for every workshared document, but Revit 2024 defines that property only for qualifying Revit Server models. On the file-workshared fixture, Revit's native `ADocument::getModelGUID_()` implementation blocked the Rhino.Inside Idling callback and threw `Autodesk.Revit.Exceptions.InternalException`.

This is a latent document-identity defect introduced with `RevitIdentitySerializer` in commit `fd153b9f5f7bedefe91551d219cea9729a752dac` on 2026-05-27. It was not introduced by the Grasshopper lifecycle release, the `ActiveGraphicalView` correction, or the gated diagnostic implementation.

The run also disproved the suspected active-view regression. For every focus-matrix query described below, the Revit-thread trace completed the `ActiveGraphicalView` read before entering the uninstrumented query/result path.

The unavailable original incident model prevents a claim that the original-model gate passed. The controlled fixture nevertheless reproduces the same documented-invalid getter and exact Revit exception boundary.

## Runtime provenance

- Revit: 2024.3.4, build `20250918_1515(x64)`; loaded Revit API `24.3.40.0`.
- Rhino.Inside.Revit: `1.35.9651.15514`.
- Loaded RhinoCommon: `8.33.26188.13001`.
- Rook/RookBIM version: `1.5.16.0`.
- Rook/RookBIM commit: `ca90a4287f873186f437bc3729e9ff5d4e1a3234`.
- Revit process ID: `40864`.
- Native Rook port: `59845`.
- Diagnostics gate: exact process-scoped `ROOK_BIM_DIAGNOSTICS=1`; no user, machine, or surviving parent-process value after shutdown.

`GET /bim/status` returned HTTP 200 with diagnostics enabled, sink state `ready`, zero drops, a complete trace, and matching core/module provenance.

## Exact failure evidence

Three independently correlated requests persisted the same production failure:

| Route operation | Correlation ID | Stage | Exception | HResult |
|---|---|---|---|---:|
| `active_document` | `860582e7-ada1-4db3-8d8c-c3de26badbab` | `revit.document.central_guid` | `Autodesk.Revit.Exceptions.InternalException` | `-2146233088` |
| `list_categories` | `ac7357a9-f741-4bb7-877d-62c7e6d9cbce` | `revit.document.central_guid` | `Autodesk.Revit.Exceptions.InternalException` | `-2146233088` |
| `list_categories` | `0445c3d0-9038-41ab-9450-a26df2f1092c` | `revit.document.central_guid` | `Autodesk.Revit.Exceptions.InternalException` | `-2146233088` |

The captured managed stack begins at `Autodesk.Revit.DB.Document.get_WorksharingCentralGUID()`.

The Revit journal independently records, at the corresponding local timestamp `2026-07-28 15:04:19.582`, that Revit threw an application exception from native function `ADocument::getModelGUID_()` at `RevitDB/Document/Document.cpp:3545`. The local installed Revit 2024 API XML states that `WorksharingCentralGUID` is the central GUID of a server-based model and that a file-based central cannot provide it.

The source chain is unconditional for this fixture:

1. `RevitIdentitySerializer.DocumentIdentity` calls `GetWorksharingCentralGUID`.
2. `GetWorksharingCentralGUID` reads `Document.IsWorkshared`.
3. A file-workshared local returns `true`.
4. Rook therefore calls `Document.WorksharingCentralGUID` without first proving Revit Server classification.
5. The method catches `InapplicableDataException` and Revit `InvalidOperationException`, but Revit 2024.3 emitted `InternalException` in this state.

The category iterator itself reached item index `380` before final document-identity serialization invoked the invalid getter. No category property or iterator boundary was the first failure.

## Focus-matrix timeout evidence

Later `query_elements` requests produced HTTP 503 responses classified as `not_rhino_inside`. That classification is misleading: Rhino.Inside was loaded, the request was enqueued, and execution began on Revit thread 1.

For correlations `9c8b8dce-db34-4064-9545-25a98c7c11a2`, `73477e50-7c5a-4da7-ae27-59cecba97298`, `a81c7bd2-d807-4b13-9737-95e873996c97`, and `0537f135-a102-4b68-ad52-320fcbc51678`, the trace proves:

- `revit.dispatch.enqueue/success`;
- `revit.dispatch.execute/start` on Revit thread 1;
- three successful active-document acquisition reads;
- the two suppressed observation sequence positions for `ActiveGraphicalView` start/success;
- no dispatch completion before the HTTP-side terminal failure.

The Revit journal reports that the matching Idling callbacks used 12 seconds. Rook's ordinary dispatch timeout is five seconds. Once a work item has entered `Running`, `Abandon()` cannot cancel it, so the handler can return a timeout response while the Revit-thread operation completes late.

The current trace does not instrument statements between successful active-view resolution and query-result completion. It therefore does **not** establish a per-instruction stack for each later 12-second callback. The prior query response, the exact native getter failure, and the unconditional result-identity source path all implicate the same document-identity read, but this report does not substitute that inference for a captured stack. The exact proven timeout defect is the combination of a 12-second Revit Idling callback, a five-second Rook wait, non-cancellable running work, and incorrect mapping of the timeout to `not_rhino_inside`.

Dispatcher timeout/taxonomy cleanup remains a separate track. It is not part of the identity fix or this diagnostic implementation.

## JSONL integrity and privacy

Private local artifact:

`%LOCALAPPDATA%\Rook\diagnostics\rookbim-20260728T190327980Z-40864.jsonl`

- SHA-256: `AC30C20C977E7CC0F93B1744396DA3CDA3FF6EC4FF63645B8E7BDE60B5EFF5B9`.
- Size: 160,646 bytes.
- Records: 203 valid JSON objects on 203 physical lines; zero invalid lines.
- Maximum record size: 1,073 UTF-8 bytes.
- Sequence: strictly increasing.
- Request correlations: 11.
- Terminal records: exactly 11, one per request.
- Trace completeness: all terminal records `traceComplete=true`.
- Request and sink drops: zero.
- Persisted production failures: three, all at `revit.document.central_guid`.

Literal scans found zero occurrences of the controlled model title, `.rvt`, the test category name, the model-directory name, the Windows user name, or the Revit exception message. The JSONL contains no raw request or HTTP payload. The Revit journal and raw HTTP responses can contain model data and remain private, uncommitted evidence.

## Build, deployment, and repository state

- Managed tests before deployment: 3,492/3,492 `Rook.Tests`; 118/118 `RookBim.Tests`.
- Guarded Release builds: `Rook` completed with 264 pre-existing warnings and zero errors; `RookBim` completed with zero warnings and zero errors.
- Deployment used `scripts/deploy-local-testing.ps1 -Configuration Release` from committed head `ca90a428` with all Revit/Rhino hosts closed.
- Installed `net8.0`, `net7.0`, and `net48` runtime inventories matched the committed build with no missing, extra, or mismatched runtime-bearing files.
- Installed `RookBim.dll` SHA-256 matched the build: `3A207FF688806D2A95106BABF2F97DB8413D3415A6D42CFE4322231FC8763CE7`.
- After the run, the Revit/Rhino hosts are closed and the diagnostic environment variable is absent at process, user, and machine scope.
- The diagnostic implementation worktree remains clean at `ca90a428`; the original checkout still contains only its two pre-existing FFmpeg modifications.

## Acceptance decision

The diagnostic architecture passed its live operational, correlation, persistence, bounds, provenance, and privacy checks on the controlled fixture. It identified the exact document-property failure without changing it.

Strict Task 10 acceptance is **not claimed** because the original incident model was unavailable. The result is a precise substitute-fixture evidence report, not an assertion about an inaccessible file.

The next corrective release is the separately approved class-limited document-identity resolver. It must stop calling the Revit Server getter for file-workshared documents, derive the approved `CreationGUID + canonical authoritative path` keys once per operation, remove fail-open matching, and pass its own two-document live acceptance gate.
