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

## Deferred minor

FalImageProvider.cs has one extra blank line at EOF. The branch-range whitespace check reports it; it has no runtime effect.

The reviewer’s “Declined to judge” items were funded account/image-quality qualification and native build/deployment; rulings 7 and 8 above explicitly retain those scope limits.
