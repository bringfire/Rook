# Grasshopper / Rhino.Inside.Revit lifecycle acceptance

Date: 2026-07-27

Split-branch amendment: 2026-07-28

Decision: **PASS**. The reviewed atomic lifecycle and solver-ownership build passed standalone Rhino and Rhino.Inside.Revit live acceptance. No rollback was invoked.

## Acceptance layers

This report contains two distinct acceptance layers:

1. The original full standalone/RiR lifecycle matrix ran against implementation commit `1bc62c35c04290ad54614f180a0ed1c8077af58b` on `codex/rir-grasshopper-document-lifecycle`.
2. PR #508 replayed the accepted Grasshopper production paths onto current `origin/main`, added the Python scheduling-consumer correction, deployed replacement head `63ce9c2c`, and passed a real MCP `gh_update_script` smoke.

The Grasshopper production paths indexed in the [normative design](../specs/2026-07-26-rir-grasshopper-document-lifecycle-design.md#appendix-a-rook2-reimplementation-index) were verified byte-for-byte equal between the original accepted tree (whose report commit was `23122e79`) and replacement head `63ce9c2c`. The replacement therefore relies on the original full host matrix only for those equal Grasshopper paths; the Python boundary has its own live MCP evidence below.

RookBIM was a host/test fixture during the original RiR matrix. Its availability and build provenance helped establish that the Revit-hosted environment was coherent, but PR #508 contains no RookBIM production or test changes and makes no acceptance claim about RookBIM identity, diagnostics, route payloads, or selection/export behavior.

## Provenance

### Original full RiR matrix

- Branch: `codex/rir-grasshopper-document-lifecycle`
- Implementation commit: `1bc62c35c04290ad54614f180a0ed1c8077af58b`
- Report commit: `23122e79cab82a70b80e2deedfaa0771877928c6`
- RookNative: `1.5.16.0`
- Rook: `1.5.16.0`, commit `1bc62c35c04290ad54614f180a0ed1c8077af58b`
- RookBIM fixture: `1.5.16.0`, commit `1bc62c35c04290ad54614f180a0ed1c8077af58b`; availability/provenance only, not RookBIM content acceptance
- Rhino / Grasshopper: `8.33.26188.13001`
- Revit: file version `24.3.40.26`, product build `20250918_1515(x64)`
- RevitAPI: `24.3.40.0`
- Rhino.Inside.Revit: `1.35.9651.15514`
- Standalone Rhino PID: `45048`; observed window `2026-07-27T20:07:02Z` through the transition to the Revit run.
- Revit-hosted Rhino PID: `28936`; process start `2026-07-27T20:15:47.9425725Z`; observed through `2026-07-27T20:26:26.3667777Z`.

The committed deploy was performed through `scripts/deploy-local-testing.ps1 -Configuration Release`. Installed roots were `%LOCALAPPDATA%\Rook\app`, `%LOCALAPPDATA%\Rook\data`, `%LOCALAPPDATA%\Rook\app\chirp`, and `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative`.

The deploy-contract inventories matched exactly: `net8.0` 14/14 files, `net7.0` 17/17, and `net48` 19/19, with no missing files, stale extras, or hash mismatches. Installed `net48/RookBim.dll` SHA-256 was `3EDC02FCFDD2AF0A2FA4AB79B7B2B12DB4F4A6A75C0D17364C67C3D87D5C5689`. Installed native plug-in SHA-256 was `64C9A45BAABBB27535743153B6B66E00A5AD5223C05086FF855605906E78E792`, matching the reviewed build.

The RookBIM hash above proves only which fixture binary was installed for the original matrix. It does not validate any RookBIM behavior for PR #508.

### PR #508 replacement deployment and MCP smoke

- Branch: `codex/rir-grasshopper-lifecycle-python-contract`
- Deployed replacement commit: `63ce9c2c`
- Deployment: `scripts/deploy-local-testing.ps1 -UseRepoVenv`
- Effective MCP runtime: the branch-local locked environment and `mcp_server/src/rook/server.py` from `63ce9c2c`
- Host: standalone Rhino/Grasshopper 8.33 on one disposable empty template document
- MCP path: fresh stdio `ClientSession` → `rook_tools_call(gh_update_script)` → managed `/gh/script` → MCP `/gh/errors` verification
- Disposable component: created for the smoke, updated once, then deleted; the test host was closed without retaining a user document

The exact accepted/verified result was:

```text
schedule_classification=async_schedule_requested
schedule_acceptance=accepted
schedule_failure_code=null
solve_scheduled=true
verification_deferred=true          # managed callback completion unverified
component_errors=[]
script_receipt.verification.status=passed
script_receipt.verification.method=gh_errors
script_receipt.artifact_status=usable
```

This proves the corrected cross-boundary behavior: managed completion remains unverified at callback return, but accepted scheduling no longer causes the Python consumer to skip its own error verification or emit solver-unlock instructions.

## Method

For the original full matrix, the MCP transport was intentionally stopped before deployment and did not reconnect inside the existing Codex client. That matrix therefore used the freshly deployed native HTTP surface directly. Routes exercised were `GET /ping`, `GET /capabilities`, `GET /gh/status`, `POST /gh/snapshot`, `POST /gh/document/new`, `POST /gh/document/open`, `POST /gh/edit`, `GET /gh/errors`, `POST /execute`, and `GET /bim/status`. The `/bim/status` call checked fixture availability/provenance only.

The PR #508 replacement smoke used a fresh branch-local MCP stdio session and invoked the public MCP gateway, not the direct HTTP shortcut. It first bound the discovered Rhino instance, then created a disposable C# component and called `gh_update_script` with `check_errors=true`.

No model path, Grasshopper fixture path, document title, arbitrary exception message, raw object identifier, or component instance name is retained in this report. Documents and fixtures below use bounded aliases.

## Standalone matrix

1. **Empty new document — pass.** Starting from one registered document, `/gh/document/new` increased the server count by exactly one. `ghdoc-001` was empty, registered at a non-negative index, active by reference, and distinct from the prior canvas document.
2. **Configured template isolation — pass.** A verified non-empty seven-object fixture was temporarily configured as Grasshopper's template. `/new` still created an empty registered active document. The prior template setting was restored immediately.
3. **Open registration — pass.** Opening `ghfixture-001` increased the server count from three to four, activated the returned document, registered it at a non-negative index, and observed seven objects.
4. **Duplicate open — pass.** Reopening `ghfixture-001` returned the exact same document reference and left server count at four. The response reported duplicate reuse.
5. **Controlled activation failure — pass.** A one-shot canvas callback safely restored the prior document during candidate activation. The route returned `gh_document_activation_failed`, reported rollback attempted and complete, restored the prior reference, and left server count unchanged at five.
6. **Volatile output — pass.** A two-node numeric-to-display edit produced downstream volatile value `7.25` after the scheduled solution.
7. **Standalone suspension ordering — pass.** Instrumentation observed the document disabled during mutation, restored enabled before the accepted scheduled solution, and no global solver transition. The productive `SolutionStart` occurred after the client recorded the response; only one productive post-response solution occurred in the bounded observation window.
8. **Wire contract — pass.** The response contained `schedule_classification=async_schedule_requested`, `schedule_acceptance=accepted`, `schedule_failure_code=null`, and `solve_scheduled=true`. Registration evidence was known/true; standalone restoration was attempted/succeeded; deprecated post-mutation repair fields were present and neutral. No camel-case duplicate schedule keys appeared.

## Rhino.Inside.Revit matrix

1. **Lifecycle parity — pass.** A new document increased server count from one to two. Opening `ghfixture-001` increased it to three. Duplicate open reused the exact reference and kept the count at three.
2. **Disabled-instance scheduling — pass.** Before edit, the registered active document reported instance `Enabled=false` while the global gate was true. The response returned `rir_mediated_schedule_requested`, `accepted`, `solve_scheduled=true`, no standalone suspension attempt, and no repair attempt.
3. **Asynchronous productive solve — pass.** Disabled-document start/end notifications before response were no-work pairs. The productive solution began with the document enabled approximately 27 ms after response receipt and produced volatile value `6`.
4. **Temporary global disable — pass.** During RiR's registration gate, edit returned `global_solver_unavailable`, `not_attempted`, `solve_scheduled=false`, and no repair or retry. RiR restored the global gate to true and later produced volatile value `4`.
5. **Solver ownership — pass.** Live stack classification attributed solver-gate transitions to Rhino.Inside.Revit. The one activation transition was performed by Grasshopper's canvas-document setter. Rook performed no direct document `Enabled` or global `EnableSolutions` write. No five-second handoff or second Rook scheduler was observed.
6. **Seven-component computation — pass.** After correcting two initially miswired optional filter inputs in the test harness, the planned seven RiR components finished with zero Grasshopper errors and zero warnings. Output counts in plan order were populated, including aggregate query counts of 54 and 350.
7. **Truthful deferral language — pass.** Responses used `rir_mediated_schedule_requested` and `verification_deferred`; none claimed actual RiR deferral before a proving solution event.

## Notes and cleanup

- The initial two filter-input conversion errors were caused by the acceptance harness, not the production route. Removing those two wires produced the final zero-error/zero-warning state.
- The global-disable path used no Rook retry. Later output was evidence of RiR's own gate restoration.
- All temporary event handlers and process-local sticky state were removed after observation.
- Original-matrix `/bim/status` reported the RookBIM fixture available, diagnostics disabled, and exact core/module provenance. No RookBIM route content or identity semantics were accepted by this report.
- PR #508 retains the existing 300 ms best-effort settle before `/gh/errors`. A solve slower than that window could be observed before completion. This residual risk is documented rather than expanded into a solve-completion protocol in the lifecycle repair.
- The replacement MCP smoke component was deleted and its disposable Rhino/Grasshopper host was closed.
- No live rollback was required. The atomic implementation remains the installed candidate.
