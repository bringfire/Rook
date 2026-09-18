# A+B Precontact v1: Failed In Slice A

## Ruling

The single authorized execution **failed**. The first Slice A command reported
**504 passed, 19 failed, 11 warnings in 86.17 seconds**. The harness exited 1,
published one failed terminal result, and sealed its evidence. No repair, retry,
acceptance change, diagnostic rerun, or cleanup of the generation was performed.
This version has no passing qualification authority and must never be reused.

Slice B was not reached. The remaining four Slice A commands (managed panel,
browser composer, cutover verifier, installer source guard) were not run.
No Slice C, promotion, deployment, or installed-product qualification occurred.

## Frozen Identities

| Input | Identity |
| --- | --- |
| Qualification HEAD | `4201ce06ad9e1b6c27600d8f689751c82f0114fe` |
| Product implementation baseline | `0900d913c1cc0e4bd76c2df018fbe0ac4fccac2e` |
| Protocol SHA-256 | `0C7C2D4998B2C2CFFD2A3B815F24AB08CF7FA136593B6E117F1570994C3DB27E` |
| Runtime ID / manifest SHA-256 | `4BFA4A0500FECEAAEC737563623521562C5F4FDF2592EA443C956E0063A12579` |
| Prime HEAD | `b71badc503f650cd7c10c4acd1206a8406aa0a0b` |
| Chirp HEAD | `1f954c27f796ecfe830d02a76497deffcf31cfc2` |

The protocol is the tracked
`scripts/qualification/protocols/rookchat-prime-acp-precontact-v1.json` at the
qualification HEAD. Both roots were confirmed absent before invocation:

- Evidence: `C:/UDEV/RookQualification/rookchat-prime-acp-precontact-v1`
- Execution: `C:/UDEV/RookQualification/rookchat-prime-acp-precontact-v1-workspace`

The runner's complete admission passed before creating either generation.
The wall-clock limit remained 1,800 seconds, process-close limit 30 seconds,
and all protocol inputs, environment policy, and acceptance predicates were
unchanged. No timeout or output-bound failure was reported.

## Operator Command

Working directory:
`C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset`.

```powershell
Write-Output "EXECUTION_STARTED_UTC=$([DateTime]::UtcNow.ToString('o'))"
& 'C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server/.venv/Scripts/python.exe' -I 'C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/scripts/qualification/rookchat_prime_acp_precontact.py' --repo-root 'C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset' --protocol 'C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/scripts/qualification/protocols/rookchat-prime-acp-precontact-v1.json' --expected-qualification-commit '4201ce06ad9e1b6c27600d8f689751c82f0114fe'
$qualificationExit = $LASTEXITCODE
Write-Output "QUALIFICATION_EXIT=$qualificationExit"
Write-Output "EXECUTION_FINISHED_UTC=$([DateTime]::UtcNow.ToString('o'))"
exit $qualificationExit
```

Observed operator output:

```text
EXECUTION_STARTED_UTC=2026-09-06T02:11:00.3222398Z
precontact_refused: Slice A command failed: python-acp-boundary
QUALIFICATION_EXIT=1
EXECUTION_FINISHED_UTC=2026-09-06T02:12:31.7237520Z
```

The first child used that exact worktree Python with `-m pytest`, all 21 files
from `inputs.sliceATestFiles` in protocol order, and `-q`, with cwd
`C:/UDEV/Rook/.worktrees/rookchat-prime-acp-reset/mcp_server`. It received the
unchanged reviewed Slice A environment. No additional pytest/plugin flags or
ambient PATH entries were supplied by the operator.

## Retained Failures

The following three tests in `tests/test_gh_status_contract.py` failed:

- `test_gh_status_success_means_endpoint_executed_not_ready`: expected
  `payload["success"] is True`, observed False.
- `test_gh_snapshot_fails_closed_when_not_ready`: expected
  `grasshopper_not_ready`, observed `no_rhino_instance` with an empty instance list.
- `test_gh_edit_fails_closed_when_not_ready`: same expected/observed error mismatch.

The following sixteen tests in `tests/test_verify_installed_rookchat_acp.py`
failed with `FileNotFoundError: [WinError 2] The system cannot find the file
specified`. The retained traceback identifies the fixture's
`subprocess.run(["git", "init", "-q", str(source)], check=True)` at line 47:

- `test_real_verifier_entrypoint_reports_complete_installed_identity`
- `test_failed_comparison_never_publishes_report[wrong_commit]`
- `test_failed_comparison_never_publishes_report[dirty]`
- `test_failed_comparison_never_publishes_report[pointer]`
- `test_failed_comparison_never_publishes_report[interpreter]`
- `test_failed_comparison_never_publishes_report[origin]`
- `test_failed_comparison_never_publishes_report[pythonpath]`
- `test_failed_comparison_never_publishes_report[wheel_commit]`
- `test_failed_comparison_never_publishes_report[missing]`
- `test_failed_comparison_never_publishes_report[changed]`
- `test_failed_comparison_never_publishes_report[extra]`
- `test_failed_comparison_never_publishes_report[relocated]`
- `test_failed_comparison_never_publishes_report[substituted_skill]`
- `test_failed_comparison_never_publishes_report[notice]`
- `test_failed_comparison_never_publishes_report[python_code]`
- `test_failed_comparison_never_publishes_report[linked]`

These are observations from the existing output, not new diagnostic executions.
No failure is classified as proven pre-existing, waived, or reinterpreted as a
passing result. The suite's final summary contains 523 completed tests.

## Sealed Evidence

All paths below are relative to the evidence root. Each retained file was read
and checked against the existing index's byte count and SHA-256 after execution;
all comparisons passed. Neither the evidence nor workspace was modified.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| admission.json | 296 | `9E39ABA628A8EDBC394611D904F71FC2C341DB58F1D19305DD5CB61CEBEEC586` |
| result.json | 128 | `7092A5AC63F12D9C00F55256F898829C1DC928E7853FD73C699AAAB66D2C8257` |
| slice-a/01-python-acp-boundary.stdout | 132073 | `30CB2FD72669A6C7B211481A81602418A2ACC5AF530FA39B377F0984DA19275F` |
| slice-a/01-python-acp-boundary.stderr | 0 | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` |

Index SHA-256:
`43088017B68E3386A384E898D1943DD664DA45B4C0842739E1AB6139CB7FA74B`.
`SEALED` contains exactly `sealed` plus LF; its SHA-256 is
`24F2F924F16716EEAE930DFC7CA01DD50E4B58754997D9AC3C7E630A0C9D3B71`.

Terminal result:

```json
{"error":"Slice A command failed: python-acp-boundary","errorType":"QualificationRefused","failedSlice":"A","outcome":"failed"}
```

The first child's stdout/stderr were retained. There is no successful
`slice-a.json` or Slice B result. The runner exited normally with failure; no
finalization-error message was emitted. A separate successful child-retirement
receipt is not present in this failed result, so this report does not invent one.

## Contact, Preservation, And Stop

Only the admitted Slice A Python command was executed after admission. Its
existing tests exercised their test-local boundaries. The harness did not reach
Slice B service startup, Prime execution, cold-kernel bootstrap, or its bootstrap
proxy. No model/Rhino/Grasshopper launch, build, installation, or deployment was
issued by the operator. The output is not proof of exhaustive network containment.

The execution workspace remains present with its `slice-a` subtree and is never
reused or adopted. No process scanning or cleanup sweep was performed. Prior Prime
build/assembly generations, protocol, harness, and product source are unchanged.
Rook was clean at the qualification HEAD after execution and before this report;
Prime and Chirp remained clean at the heads recorded above.

This report is the only committed change after execution. Stop for independent
review. No second A+B execution or next slice is authorized by this report.
