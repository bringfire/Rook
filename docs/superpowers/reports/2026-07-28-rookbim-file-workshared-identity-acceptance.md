# RookBIM file-workshared identity acceptance report

**Result: PASS — release approval supported**

The exact reviewed implementation commit completed one uninterrupted diagnostics-enabled Revit/MCP matrix, diagnostics-disabled parity, final diagnostic and journal scans, installed-inventory verification, and fixture restoration. The original file-workshared `WorksharingCentralGUID` failure did not recur. No production source changed during this final acceptance run.

## Provenance

- Execution base: `9024f043b0d52aad1f94414d8e21c495c6bbfafd`.
- Policy commit: `d75642cf`.
- Atomic implementation commit deployed and tested: `051c5a9ad6ef27ff6eb60540d7f032727ff39385`.
- Acceptance-report-only predecessor: `1335c0c0`.
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
- The final reviewed implementation worktree was clean and contained exactly the approved two implementation commits above the execution base.

The exact commit was built and deployed from a clean detached worktree. The deployment wrapper exceeded its outer time limit after the child deployment finished; independent transaction verification established that the child exited and that every installed artifact matched the committed build. No intermediate binary was loaded.

Final installed inventories matched the exact committed build with stale-extra detection:

| Inventory | Expected | Installed | Differences |
| --- | ---: | ---: | ---: |
| managed `net8.0` | 14 | 14 | 0 |
| managed `net7.0` | 17 | 17 | 0 |
| managed `net48` | 19 | 19 | 0 |
| MCP application source | 285 | 285 | 0 |
| MCP site-packages | 285 | 285 | 0 |

Python imported `rook.server` from the installed `%LOCALAPPDATA%\Rook\venv\Lib\site-packages\rook` tree. Final installed hashes were:

- net8 `Rook.rhp`: `D79E44E6B769A702CB4925DF80CD6DFD77E254DF1B008D8177EB9BC0EC950454`.
- net7 `Rook.rhp`: `788623632B859BECABDF8F1B7DF1B058D9538014C5BE85DC68960068B5BC7E72`.
- net48 `Rook.rhp`: `0767E94D230838CD32966AE4507BC865A2916B92B56D110352BF858749B93A79`.
- net48 `RookBim.dll`: `D25475756EE96ABCFF55EAEBEE6A1A42947976A0096DEFE43EFCF091C696AF88`.

Both enabled and disabled `/bim/status` calls reported the exact core and module commit. At final shutdown, Revit, Rhino, and exact `python -m rook` process counts were zero.

## Diagnostics-enabled live matrix

The following passed through the installed public MCP boundary where applicable:

- File-workshared central, a newly created and synchronized local, and reopening that same local used `revit_creation_guid_central_path_v1`. Their versioned keys matched and all four identity consumers—element information, parameters, selection, and identity-list export—succeeded.
- A same-lineage copied central at a different authoritative path did not match the original identity.
- A same-lineage copy later occupying the original authoritative path matched by the documented v1 lineage-at-location semantics.
- A different-lineage central occupying the original authoritative path produced a different key. The original identity failed all four consumers with `document_mismatch`; the replacement identity passed all four.
- A saved non-workshared project and its reopen used `revit_creation_guid_document_path_v1` and retained a stable key through all four consumers.
- A different-lineage saved project replacing the same path produced a different key. The original identity failed all four consumers with `document_mismatch`; the replacement identity passed all four.
- Saved family, fresh unsaved project, fresh unsaved family, and detached document emitted `documentKey = null` with source `unavailable`. Caller-supplied identities failed closed with `document_identity_unavailable` before lookup, selection, or output.
- Rejected selection calls left selection at zero. Rejected identity-list exports created no `.3dm`, sidecar, or validation artifact.
- Trusted same-operation selector and preset exports succeeded on the unsaved-project and detached-project fixtures, proving that unavailable durable identity does not disable trusted live-element export paths.
- Revit document ownership checks exercised the corrected local `Document.Equals` helper. The earlier CLR wrapper-reference failure did not recur.

The complete detached validation table matched the approved precedence and comparison contract:

- Null entry: `document_identity_invalid`.
- Any linked evidence: `linked_element_unsupported`.
- Whitespace key, key with unavailable source, missing key with strong source, conflicting legacy evidence, and malformed key: `document_identity_invalid`.
- Unknown `documentKeySource`: transport binding returned HTTP-400-equivalent `invalid_scope`, which the approved contract permits without a custom enum deserializer.
- Exact non-empty legacy GUID in `D` form against the conclusively non-server detached document: `document_mismatch`.
- Braced, `N`-format, whitespace-padded, empty, and malformed legacy GUID text: `document_identity_invalid`.
- A two-entry batch whose first coherent identity was unavailable and whose later identity was malformed returned `document_identity_unavailable` for index 0. The same precedence held for selection and export; no lookup, selection, or output occurred.

The two final harness mismatches from the earlier partial session required no production-code change: first failing batch entry wins, and valid server GUID evidence against a conclusively non-server document is a mismatch. The earlier Revit wrapper-ownership correction is already part of `051c5a9a` and is not being described as absent.

Revit Server and cloud infrastructure were unavailable. No new server/cloud versioned key is emitted, and no new live claim is made for those classes. The retained legacy Revit Server rule was exercised only as policy evidence against a conclusively non-server document.

## Diagnostics-disabled parity

Revit was relaunched normally with `ROOK_BIM_DIAGNOSTICS` absent at process, user, and machine scope. `/bim/status` reported diagnostics disabled, sink state `disabled`, zero drops, and exact `051c5a9a` core/module provenance.

Representative parity passed:

- The saved-project replacement produced the same versioned key observed in the enabled run and remained distinct from the original project key.
- Matching element information, parameters, selection, and identity-list export succeeded.
- The retained original-project identity failed all four consumers with `document_mismatch`; selection stayed empty and no rejected files were written.
- Whitespace-key evidence returned `document_identity_invalid` without a selection side effect.
- Trusted selector export succeeded.
- The saved-family producer returned unavailable identity and six reference-plane results. Information, parameters, selection, and identity-list export returned `document_identity_unavailable`; selection stayed empty and no rejected files were written.

No new JSONL file was created during the disabled run. The latest diagnostic file remained the preserved enabled file with unchanged SHA-256.

## Diagnostic and journal evidence

Raw evidence remains outside Git under `%LOCALAPPDATA%\Rook\acceptance-evidence\rookbim-file-workshared-identity\final-uninterrupted-051c5a9a-20260729`.

- Enabled JSONL SHA-256: `598D5D6CDECA21E4BCFB868E82E803CFC79A40C32CBA65BCE1ACBC95C36FCC93`.
- Enabled Revit journal SHA-256: `369F35612E4230A3CF6ABE792DDEF5B96D5AF3344CD130DC21007960831782C5`.
- Enabled worker journal SHA-256: `ED6F722B04A7DE2D488981059B5A8FCA951D230D2EC02D69EF5483AD76D4FFB7`.
- Disabled Revit journal SHA-256: `592FD0FDC5F4494188A43FF444E8093A1C8A727ADF02FE9117435FF9C01236D3`.
- Disabled worker journal SHA-256: `E231E4C0802075C64AA2EC18D7F8BDC5F8B0E369B913F687850240C7E8FDBDB9`.

The enabled diagnostic file contained 2,479 valid JSONL records and zero invalid lines. Sequence numbers were strictly increasing. There were 142 correlated requests and exactly 142 terminal records; every correlation had exactly one terminal. Every terminal reported a complete trace and the maximum request-dropped count was zero.

Core commit provenance was exact in every record. Module provenance was the designed literal `unavailable` for the first ten pre-activation records and exact `051c5a9a…` after module metadata registration. Failure records were bounded to the expected deserialization, identity-unavailable, invalid-evidence, and mismatch stages. Source/delegate tests enforce one identity classification read set per Revit operation; live 100-element query/export cases showed no per-element durable-key failure traffic.

Privacy scans found zero model titles, category/element names used by the fixtures, `.rvt` paths, drive paths, UNC paths, document keys, document GUID values, request identities, or exception messages. GUID-shaped strings occurred only in `correlationId`.

Enabled and disabled journals and worker logs contained zero occurrences of:

- `ADocument::getModelGUID_` or `WorksharingCentralGUID`;
- `Autodesk.Revit.Exceptions.InternalException`;
- `internal error`;
- RookBIM unhandled-exception signatures.

This establishes that the original file-workshared central-GUID crash did not recur in either mode.

## Rollback protection and fixture restoration

The pre-deployment rollback artifact was reused unchanged; it was not overwritten or recreated:

- Artifact: `%LOCALAPPDATA%\Rook\rollback\rookbim-file-workshared-identity\rookbim-identity-predeploy-051c5a9ad6ef27ff6eb60540d7f032727ff39385.zip`.
- SHA-256: `44CB9CBB1D237BD1FB9FA53099EA7FF2BD27F75174C3AE9E27E563F1C1301E02`.
- The archive was test-extracted before deployment. Manifest paths, lengths, hashes, and the 905-file total matched; its sidecar SHA still matches at final verification.

No final rollback was required because acceptance passed. The installed state remains exact `051c5a9a`.

The different-lineage central that temporarily occupied the controlled original path and its backup directory were moved into the disposable acceptance fixture. The preserved original central was restored to its original path with SHA-256 `D11FC9E5DCDD4B2D11EFF62CFCFD509A49E8D8DAC5B6A66FD12CB296E36B4326`. Its restored backup directory matched all 31 preserved files by relative path, length, and SHA-256.

## Final decision

PASS. The approved class-limited composite identity behaves correctly for file-workshared central/local documents and saved non-workshared projects; unsupported classes fail closed; the MCP identity envelope round-trips through every consumer; Revit ownership uses the live-proven `Document.Equals` rule; diagnostics are behavior-neutral; and the prior invalid central-GUID getter does not recur.

The implementation commit `051c5a9a` is eligible for integration, subject to the normal code-review and branch-integration process. Server/cloud versioned identity remains a separately gated future track.
