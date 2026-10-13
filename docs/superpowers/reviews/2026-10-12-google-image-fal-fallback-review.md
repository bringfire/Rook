# Google image fal fallback — implementation and final review

Implemented the approved revised plan on branch codex/google-image-fal-fallback in the existing isolated worktree. Product implementation was executed inline in this chat. No implementation subagents were used.

The independent reviewer used a fresh gpt-6-astra context and reviewed a3cab49dc50667f32d43d0ca9fcfe9d39851bcb7 through 08525a85df77a171d13cbf78f588b7888eea52df. The reviewer independently ran 83 managed tests and 31 actual app.js tests, all passing, and reproduced the UI findings against the real managed projection fixtures.

The reviewer found no Critical issues, two Important UI issues, and two Minor issues. Both Important issues were fixed in one pass at 6ada3fb3931109aaaadb5e087c44e038ba237448:

- Mapped Gemini options and settings now disclose automatic fal fallback and its credential configuration. Both missing credentials produce “Configure a Gemini or fal.ai key” guidance.
- Structured image failure messages show the actual provider/fallback. Compatibility failures say “before sending” only when the trusted dispatch state is NotStarted; restored IntentRecorded uncertainty never implies no send.

Five actual Generate/Studio JavaScript assertions failed before these changes and passed afterward. The concurrency coverage finding was promoted to acceptance work: two transports are held simultaneously, then cancellation or deadline expiry stops only the fal job while the Google job remains in flight and completes with its own attribution. The new fixture interface failed compilation first; both deterministic cases passed after adding the transport controls. Production isolation code required no change.

No second review was dispatched. Fix verification used the regression tests and a green available full suite.

## Validation

- Debug managed builds succeeded for net48, net7.0, and net8.0, including after the review fixes.
- Final available managed suite: 4,413 passed, zero failed or skipped.
- Final executable actual app.js suite: 36 passed, zero failed or skipped.
- Earlier focused acceptance gate: 978 passed; Enterprise/video regressions: 134 passed.
- The full run before the final coverage additions had 4,411 passing tests and the same two missing prerequisites as the baseline: SupersededSolverRaceSpec_LinksToTheNormativeLifecycleDesign lacked an ignored GH design document, and Task7_original_producer_values_survive_managed_http_parser lacked its unrelated Python producer fixture. Only these two named tests were excluded from the final available-suite gate.
- Managed fixture generation was explicit and its environment flag was removed in finally. Default tests compare fresh normalized real handler/job projections without writing the fixture.
- Working-tree whitespace checks passed. A branch-range whitespace check identifies the deferred EOF blank line below.
- Provider and download requests used injected transports and synthetic credentials. Live funded account qualification, native builds, installation, deployment, merging and pushing were outside this execution.

## Rulings, in execution order

1. The later approved human-reviewed amendments bind over the older spec: independent direct-fal credential evidence and durable dispatch state. Cost if wrong: recovery could misrepresent an uncertain request as unsent.
2. Preserve the unrelated baseline prerequisite failures and compare final results against them. Cost if wrong: those failures remain unresolved; generating unrelated fixtures could affect other work.
3. Update the additional Nano Banana missing-key parity assertion to the approved fal fallback failure. Cost if wrong: strict consumers of the former Gemini-only string must adopt structured image errors.
4. Consolidate illustrative scenario names into parameterized tests under the prescribed owning-layer filters. Cost if wrong: an omitted parameter boundary could reduce acceptance coverage.
5. Generate the opt-in managed fixture before the JavaScript RED run so executable tests use actual envelopes. Cost if wrong: a stale fixture could mask drift; default managed comparison guards this.
6. Promote concurrent-route coverage to Important acceptance work because deterministic overlap and stop isolation were explicitly required. Cost if wrong: extra hermetic test infrastructure and test time.
7. Leave funded account access and live image quality outside acceptance, as the approved plan requires. Cost if wrong: live behavior remains unqualified.
8. Leave native build/deployment outside acceptance because there are no native changes and deployment was excluded. Cost if wrong: installed runtime behavior remains unverified.
9. Keep the branch and worktree local instead of soliciting an unrequested integration decision. Cost if wrong: integration waits for a later user request.

## Originally deferred minor

The original review deferred an extra blank line at EOF in FalImageProvider.cs. The queued-stop fix pass below removed it; the full branch whitespace check now passes.

The reviewer’s “Declined to judge” items were funded account/image-quality qualification and native build/deployment; rulings 7 and 8 above explicitly retain those scope limits.

Cleanup of this plan's ignored execution workspace was rejected by automatic approval review with “blocked by policy.” Its execution logs remain in place; the committed implementation and review record are complete.

## Follow-up review fixes (2026-10-13)

The later human-provided review identified a Cancel path that overwrote an already observed execution stop and six unreadable model-label separators. Both findings were reproduced before product edits and fixed inline.

- In commit 5e769bf1, Cancel and the worker began deriving terminal state and diagnostics from the same first-observed execution-budget reason. At that stage, the budget was published under the job's transition gate after queue admission. Four deterministic cases hold the worker before its terminal commit, issue a later Cancel, and verify deadline/shutdown attribution through direct fal and Gemini fallback, the physical ledger, and a fresh manager. All four failed with Cancelled before that fix and pass afterward. Existing user cancellation and terminal-winner coverage remained green.
- The six separator bytes were invalid single-byte middle dots within an otherwise UTF-8 resource. They now use valid UTF-8 middle dots. Five real app.js renderer cases failed before correction and pass afterward, covering provider, configured/unconfigured fallback, credential warning, and missing-key labels.
- Focused managed cancellation/budget/manager tests: 84 passed. Real app.js suite: 41 passed. Debug builds for net48, net7.0, and net8.0 succeeded.
- Full managed run excluding LiveSmoke: 4,417 passed, two failed, zero skipped. The failures are the same two missing prerequisite tests named above; no new managed failures occurred.
- Follow-up whitespace checks passed. No new independent review was dispatched; this pass verifies the supplied findings with regression tests. Live providers, billing, image quality, native builds, deployment, merging, and pushing remain unverified.

## Independent branch review and queued-stop fixes (2026-10-13)

At the user's request, a fresh independent reviewer examined commit 5e769bf1 and the full branch range a6f63be8..5e769bf1. The reviewer found no Critical issues and reproduced one remaining P2 defect: an observed shutdown could be overwritten by later Cancel while an affected job was queued, before its execution budget existed. The extra EOF blank line was also reported as P3.

The fix creates the affected job's single stop latch before queue waiting. Queue cancellation links to that latch, so the worker wakes only after provenance is recorded. The same budget survives queue admission; its deadline is attached only after acquiring a concurrency slot. Both terminal paths consume the latch without recomputing from raw cancellation flags. Budget registrations and timer ownership are released at worker settlement, including queued stops.

- Eight real-JSONL regression cases cover both stop orderings for all four affected models. The four shutdown-before-Cancel cases failed with Cancelled before product edits; the four user-before-shutdown controls passed. All eight pass after the fix, including live status, Cancel response, and fresh-manager recovery, with no queue timers, HTTP requests, or published artifacts.
- The implementer reran the independent reviewer's original probes against fresh binaries: all six active Google/direct-fal/fallback controls and all six queued cases pass, with zero mismatches.
- Focused managed gate including subsystem wiring: 96 passed. Real app.js suite: 41 passed. Fresh Debug builds for net48, net7.0, and net8.0 succeeded. Working-tree and full-branch whitespace checks passed.
- Final full managed rerun excluding LiveSmoke: 4,425 passed, two failed, zero skipped. The failures remain SupersededSolverRaceSpec_LinksToTheNormativeLifecycleDesign (missing GH spec) and Task7_original_producer_values_survive_managed_http_parser (missing Python producer fixture).
- The first full run overlapped compilation and also hit five timing failures: GhSolveReceiptRegistryTests.ReplaceDocument_TombstonesReceiptAndSignalsWaiter; GhSolveReceiptRegistryTests.Wait_EvictedSignaledReceipt_ReturnsCapturedTerminalResult; VideoStopSubmissionRaceTests.StopReadingBeforeHandleCommit_PreservesLatestOperationAndBinding; ReplicateImageJobManagerTests.Flux2_job_materializes_with_uploaded_source_url_without_leaking_transport_payloads; VideoJobManagerTests.Cancel_in_flight_when_BG_just_wrote_terminal_short_circuits_without_provider_call. All five passed in isolation and in the subsequent full run without compilation. Their code and timeouts were not changed.
- The original independent reviewer then verified the frozen targeted product/test diff read-only. Both original findings are resolved, with no additional actionable issues. The reviewer independently reran 96 focused managed tests and all 12 original probes, with zero failures/mismatches, and confirmed both whitespace checks. The assessment is ready to merge within the earlier live/deployment verification limits. This verification did not repeat the full branch review, builds, full suite, or live tests.

Live providers, billing, image quality, native builds and deployed behavior remain outside this fix pass. No merge or push was performed.
