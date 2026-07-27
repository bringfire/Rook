# Grasshopper / Rhino.Inside.Revit lifecycle acceptance

Date: 2026-07-27

Decision: **PASS**. The reviewed atomic lifecycle and solver-ownership build passed standalone Rhino and Rhino.Inside.Revit live acceptance. No rollback was invoked.

## Provenance

- Branch: `codex/rir-grasshopper-document-lifecycle`
- Implementation commit: `1bc62c35c04290ad54614f180a0ed1c8077af58b`
- RookNative: `1.5.16.0`
- Rook / RookBIM: `1.5.16.0`; both reported commit `1bc62c35c04290ad54614f180a0ed1c8077af58b`
- Rhino / Grasshopper: `8.33.26188.13001`
- Revit: file version `24.3.40.26`, product build `20250918_1515(x64)`
- RevitAPI: `24.3.40.0`
- Rhino.Inside.Revit: `1.35.9651.15514`
- Standalone Rhino PID: `45048`; observed window `2026-07-27T20:07:02Z` through the transition to the Revit run.
- Revit-hosted Rhino PID: `28936`; process start `2026-07-27T20:15:47.9425725Z`; observed through `2026-07-27T20:26:26.3667777Z`.

The committed deploy was performed through `scripts/deploy-local-testing.ps1 -Configuration Release`. Installed roots were `%LOCALAPPDATA%\Rook\app`, `%LOCALAPPDATA%\Rook\data`, `%LOCALAPPDATA%\Rook\app\chirp`, and `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative`.

The deploy-contract inventories matched exactly: `net8.0` 14/14 files, `net7.0` 17/17, and `net48` 19/19, with no missing files, stale extras, or hash mismatches. Installed `net48/RookBim.dll` SHA-256 was `3EDC02FCFDD2AF0A2FA4AB79B7B2B12DB4F4A6A75C0D17364C67C3D87D5C5689`. Installed native plug-in SHA-256 was `64C9A45BAABBB27535743153B6B66E00A5AD5223C05086FF855605906E78E792`, matching the reviewed build.

## Method

The MCP transport was intentionally stopped before deployment and did not reconnect inside the existing Codex client. Acceptance therefore used the same freshly deployed native HTTP surface directly. Routes exercised were `GET /ping`, `GET /capabilities`, `GET /gh/status`, `POST /gh/snapshot`, `POST /gh/document/new`, `POST /gh/document/open`, `POST /gh/edit`, `GET /gh/errors`, `POST /execute`, and `GET /bim/status`.

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
- Final `/bim/status` reported RookBIM available, diagnostics disabled, and exact core/module commit provenance.
- No live rollback was required. The atomic implementation remains the installed candidate.
