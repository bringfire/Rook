# RookBIM file-workshared identity acceptance report

**Result: INCOMPLETE — no release approval claimed**

The diagnostics-enabled live matrix passed every production case exercised through the detached-document case. The run was then stopped and rolled back because two validation outcomes were initially judged incorrect. A subsequent line-by-line check of the authoritative specification, plan, policy, and tests proved that both production outcomes were correct and the acceptance-harness expectations were wrong. Because rollback occurred before diagnostics-disabled parity and the final post-matrix checks, this report records evidence and containment but does not convert the incomplete run into a pass.

## Provenance

- Execution base: `9024f043b0d52aad1f94414d8e21c495c6bbfafd`.
- Policy commit: `d75642cf`.
- Atomic implementation commit deployed and tested: `051c5a9ad6ef27ff6eb60540d7f032727ff39385`.
- Deployed Rook/RookBIM product provenance: `1.5.16+051c5a9ad6ef27ff6eb60540d7f032727ff39385`.
- Revit: 2024, file version `24.3.40.26`, build `20250918_1515(x64)`.
- Rhino/Grasshopper: `8.33.26188.13001` (`Rhino 8.33`).
- Rhino.Inside.Revit: `1.35.9651+e1d9c58a9fc2770aa8c977b09f44338d3955057f`.

Pre-deployment verification passed:

- Focused core policy/contract tests: 359/359.
- RookBIM tests: 100/100.
- Full managed core tests: 3,598/3,598.
- Focused MCP tests: 51/51.
- Rook Release build: 264 pre-existing warnings, zero errors.
- RookBIM Release build: zero warnings and zero errors.
- Final reviewed worktree was clean and contained exactly two implementation commits above the execution base.

The reviewed deployment completed successfully. Installed inventories matched the committed build with stale-extra detection: 14 net8 files, 17 net7 files, 19 net48 files, and 285 files in each MCP source/application/site-packages inventory. `/bim/status` reported the deployed commit for core and module before acceptance began.

## Diagnostics-enabled live results

The following passed through the public MCP boundary where applicable:

- Active document, category listing, and active-view query on a file-workshared model.
- File-workshared central, new local after synchronization, and reopening the same local. Central and local used the approved central-path composite and matched across element information, parameters, selection, and identity-list export.
- A same-lineage copied central at a different authoritative path did not match the original identity.
- A same-lineage copy later occupying the original authoritative path matched by the documented v1 lineage-at-location semantics.
- A different-lineage central at the original authoritative path did not match the original identity.
- A saved non-workshared project and its reopen used the approved document-path composite and matched through all four identity consumers.
- A different-lineage saved project replacing the same path did not match the original saved-project identity.
- Saved family, unsaved project, unsaved family, and detached document emitted unavailable document identity and rejected caller-supplied identity operations before lookup, output, or selection side effects.
- Trusted same-operation selector/preset exports remained available for the tested unsaved-project and detached-project cases.
- The corrected RookBIM ownership checks successfully exercised Revit `Document.Equals`; the prior CLR wrapper-reference failure did not recur.
- Unknown `documentKeySource` text was rejected at transport binding as permitted. Individually malformed, whitespace, source-incoherent, conflicting-legacy, and invalid legacy envelopes produced the required invalid-evidence result. Rejected selection requests left selection unchanged.

Revit Server and cloud infrastructure were unavailable, so no new live claim is made for those classes. The initial release still emits no new server/cloud versioned key.

## Acceptance-harness expectation errors

The run was stopped after these two results:

1. On a detached document, a two-entry batch contained an earlier coherent identity whose document comparison was unavailable and a later malformed key. Production returned `document_identity_unavailable` for the earlier entry. This is correct: the specification says the first failing entry by input order determines the response, and the plan requires `PreflightBatch` to return the first failure by input index. The later entry cannot outrank the earlier failure. No lookup or side effect occurred.
2. A syntactically valid retained Revit Server GUID against the detached document returned `document_mismatch`. This is correct under the exact comparison table: valid server evidence against a conclusively non-server active class is a mismatch. The executable policy test encodes the same rule.

The initial harness expected `document_identity_invalid` and `document_identity_unavailable`, respectively. Those expectations were not the approved contract. No production-code defect was established by either result, and no corrective code was written.

## Diagnostic and journal evidence

Raw evidence remains outside Git under `%LOCALAPPDATA%\Rook\acceptance-evidence\rookbim-file-workshared-identity\blocked-051c5a9a-20260729`.

- JSONL SHA-256: `46107503375824B20008E2755A3728365E0C4013BBEA566CD56373A871D1CA75`.
- Revit journal SHA-256: `51DB8C26D16F2F049F81BCD2CA5A9EE05D81F3EB85AFC4D14BD24B5F1A16CB43`.
- Worker journal SHA-256: `32D8067B4B783DBD1268745267FE93B688D354D4C6873F54547EC66284261763`.

The diagnostic file contained 2,065 valid JSONL records and zero invalid lines across 118 correlations. Core provenance was the deployed commit throughout; module provenance was the deployed commit or the bounded `unavailable` value. Maximum dropped count was zero and no record reported an incomplete trace. A privacy scan found no RVT extension, known fixture title, drive path, or UNC path. GUID-shaped strings occurred only in the intended correlation-ID field.

The Revit journal contained zero `ADocument::getModelGUID_`/`WorksharingCentralGUID` failure signatures and zero `internal error` text. This supports the specific claim that the original file-workshared central-GUID crash did not recur during the enabled run.

## Rollback and fixture containment

Rollback was performed conservatively before the harness expectations were corrected. Revit, Rhino, and Grasshopper were closed; exactly six verified `python -m rook` processes were stopped.

- Artifact: `%LOCALAPPDATA%\Rook\rollback\rookbim-file-workshared-identity\rookbim-identity-predeploy-051c5a9ad6ef27ff6eb60540d7f032727ff39385.zip`.
- Artifact SHA-256: `44CB9CBB1D237BD1FB9FA53099EA7FF2BD27F75174C3AE9E27E563F1C1301E02`.
- Restored manifest: all 905 paths, lengths, hashes, and total count verified.
- Restored Rook/RookBIM product provenance: `1.5.16+ca90a4287f873186f437bc3729e9ff5d4e1a3234`.
- Independent checks confirmed archive equality for net8/net7/net48 `Rook.rhp` and net48 `RookBim.dll`.
- `ROOK_BIM_DIAGNOSTICS` is absent at process, user, and machine scope; host and exact Rook Python process counts are zero.

The different-lineage central that temporarily occupied the disposable original path and its backup directory were preserved under the acceptance fixture directory. The original central file was restored byte-for-byte from its preserved backup; the different-lineage backup directory is no longer adjacent to it.

No post-rollback Revit smoke was run, so no fresh runtime claim is made for the restored baseline. The restored baseline is containment only and retains the diagnosed pre-release identity behavior.

## Final decision

The enabled-mode evidence is positive and contains no proven production failure. Nevertheless, acceptance is incomplete because diagnostics-disabled parity and the final post-matrix checks were not executed before rollback. A future completion run should redeploy the same reviewed implementation (or an independently reviewed descendant), use the corrected truth-table expectations above, repeat the required live matrix from the approved starting point, and finish disabled-mode parity before approval.
