# Chirp inference-timeout follow-up acceptance

Date: 2026-08-06

Decision: **PASS for the bounded harness follow-up and installed slow-inference acceptance.** The installed candidate completed a deliberately delayed inference after the former 30-second boundary, retried only the exact transient Grasshopper callback-timeout response, verified the result, and restored the owned canvas to its empty baseline.

## Provenance and scope

- Chirp timeout release commit: `c7b1aacec6b1ae23514cb9fb0d2a365e1fb7a468`.
- Rook timeout implementation merge: `facce0f2` (PR #548).
- Harness follow-up base: `2187bbcee26b6eaf94007dc400a60203203f86ae`.
- Reviewed harness follow-up head: `ab4577a0739e4208ae2b8f8718d5543eba13b740`.
- Harness follow-up merge: `490dadc7317ebab0432126afbedb240102b117b6` (PR #550).
- Merge parents: first `2187bbcee26b6eaf94007dc400a60203203f86ae`; second `ab4577a0739e4208ae2b8f8718d5543eba13b740`.

The follow-up changed only `mcp_server/src/rook/local_testing_proof.py` and `mcp_server/tests/test_local_testing_proof.py`. It did not change Chirp timeout policy, models, dependencies, managed or native callback behavior, or the shared `RhinoHarnessResult.success` contract.

## Focused implementation gates

- Exact callback-timeout retry and owned-cleanup tests: 16 passed, 78 deselected.
- Complete `test_local_testing_proof.py`: 94 passed.
- `git diff --check`: passed.
- Review found no remaining critical, important, or minor defect after the component-identity and strict-integer corrections.

The harness retries only the exact response `{success: false, data: "GH callback request timed out."}` during slow-output inspection, retains the 250 ms interval and 1,860-second watchdog, and fails every other response. The acceptance-specific forced-cleanup admission remains local and requires successful smoke evidence, exact owned-component removal, empty baseline equality, PID/discovery ownership, process termination, and discovery-record removal. The successful final run exited gracefully, so forced-cleanup admission was not exercised as the final disposition.

## Sealed payload and installation

The sealed payload was generated from detached clean checkouts at the immutable Rook and Chirp commits above.

- Runtime: CPython 3.11.9.
- Wheelhouse: 103 wheels.
- Installed Rook: 1.5.17.
- Installed MCP: 1.28.1.
- Installed JSON Schema: 4.26.0.
- Installed Chirp: 0.1.0.
- Installed LiteLLM: 1.89.4.
- Temporary clean-runtime imports, audits, and both `pip check` paths: passed.
- Source and installed wheelhouse inventories and hashes: identical.
- Installed `local_testing_proof.py` SHA-256 matched the detached source: `B68BE73B007F448AC3EC19250D57CE6EDA68509B7901CB11B721A02E281F073A`.
- The existing installed Chirp `.env` remained byte-identical: `B15A06A74CF1354A622B2014C77BDBB50518467F6D4308A8775464C11A5D9EEA`.

The four source/installed control-file hashes matched:

| File | SHA-256 |
|---|---|
| `requirements-bootstrap-lock.txt` | `A868AE1AD2A0AA83A5902A762F95C0887BF69B2C40F7AF475F038546EE38AFF2` |
| `requirements-rook-lock.txt` | `14A5249CA437134444403F6CEA4B8D83F99142E162DE21EE244A566D402DE93F` |
| `requirements-chirp-lock.txt` | `D2FA62318CB36FDBA81624888E48D883A702EAEC85501B399327D49EBDB8336D` |
| `python-runtime-manifest.json` | `175C3A3FB36FFCA266947A42B90589EEA7FE3F5BB0C4B80E22B74D51DD623D25` |

The canonical payload-only deployment synchronized and verified the payload, rebuilt both installed virtual environments offline, imported the installed packages, and passed both dependency checks. Its final client-configuration guard returned nonzero because an active Claude desktop process rewrote `claude_desktop_config.json` during deployment and removed the newly written `type` and `cwd` fields. The pre-deployment backup contained the correct fields, and the installed `post_install.py` matched its source producer. No Claude process was terminated, no config was hand-edited, and no guard was weakened. This environment-owned client-config result is not reported as a deployment pass and is separate from the installed payload and live product acceptance below.

## Installed slow-inference acceptance

The installed Rook and Chirp runtimes launched an owned Rhino/Grasshopper session and a loopback-only fake provider. The provider deliberately delayed its only response by 35 seconds.

- Harness result: success.
- Watchdog: 1,860 seconds; not reached.
- Slow-operation elapsed time: 53.375 seconds.
- Provider requests: exactly 1.
- First `gh_inspect_output`: exact `GH callback request timed out.` response.
- Transient callback retries: exactly 1.
- Second `gh_inspect_output`: success with `slow-ok`.
- Component errors: 0.
- Owned component: observed and removed.
- Canvas baseline/final object counts: 0 / 0.
- Chirp sidecar cleanup: success without force.
- Rhino cleanup: `graceful_exit`.
- Warnings: 0.
- Owned Rhino PID after cleanup: absent.
- Owned discovery record after cleanup: absent.
- Rhino, Revit, and Grasshopper processes after cleanup: 0.

Evidence:

- Result: `C:/Users/aryan/AppData/Local/Temp/rook-chirp-timeout-followup-release-490dadc7-ab4577a0/Rook/.scratch/chirp-inference-timeout-followup-live/result.json`
- Manifest: `C:/Users/aryan/AppData/Local/Temp/rook-chirp-timeout-followup-release-490dadc7-ab4577a0/Rook/.scratch/chirp-inference-timeout-followup-live/rhino-runtime-20260806-094841-8a5ff1d8/manifest.json`
- Provider request: `C:/Users/aryan/AppData/Local/Temp/rook-chirp-timeout-followup-release-490dadc7-ab4577a0/Rook/.scratch/chirp-inference-timeout-followup-live/rhino-runtime-20260806-094841-8a5ff1d8/slow-provider-request.json`

## Final disposition

The reviewer-authorized harness correction is accepted. It addresses the two acceptance-mechanics failures without altering the timeout product behavior: the exact transient read failure is safely retried, and forced shutdown remains a narrowly admitted, honestly reported fallback for this owned acceptance only. The final installed run required neither the 1,860-second watchdog nor forced cleanup.

The active-Claude config rewrite remains separate local configuration/deployment-hygiene evidence. It does not invalidate the installed payload hashes or the owned live acceptance, but the canonical deployment wrapper's final client-config guard is not claimed green for this run.
