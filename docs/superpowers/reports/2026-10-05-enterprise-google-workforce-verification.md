# Workforce federation verification

Implementation uses the approved MSAL public desktop and Google auth STS assertion contract. Credentials remain Python-owned, with DPAPI-protected persistence; workforce media reuses the existing RookVision providers, managers, ledger and artifact pipeline.

Automated implementation evidence and installed live acceptance are separate gates. Tasks 1–9 are complete, including the earlier independent review's four fixes, the user's subsequent seven findings, and corrected-source packaged qualification. Task 10 has not started. No real Entra/Google exchange or workforce media generation has been run, and the qualified payload has not been deployed into installed Rook.

Final production source tested and packaged: `32a4fe5100c75d4bb85fc92a1d53624dc418a03a`, branch `codex/enterprise-google-media`. Matching clean Chirp source: `12230c7a9ce71104a4de31f9bc29b444cbc0b135`. This final evidence update changes documentation only; the packaged source includes the reproducible SDK/DPAPI/local-TLS smoke fixture.

| Gate | Current result |
|---|---|
| Focused Python auth/configuration/Chirp tests at `e96f9899` | 372 passed; 11 existing DSPy deprecation warnings |
| Focused managed configuration tests at `e96f9899` | 216 passed with the external Prime producer case excluded |
| Unexcluded managed configuration tests | 216 passed, 1 failed: `Task7_original_producer_values_survive_managed_http_parser`, “Stage B requires the real producer fixture from its Python gate.” |
| Final expanded Python auth/Vertex/Chirp/text/DSPy/configuration suite | 582 passed, 5 deselected; 11 existing DSPy deprecation warnings; exact missing external prerequisites below |
| Final managed configuration suite | 25 passed, including committed activation failure/cancellation display, bounded-disconnect deletion and recovery-status reconciliation |
| Fresh Debug and Release managed Rebuild | Rook and then RookBim rebuilt in each configuration; all four builds passed with 0 errors |
| Historical unexcluded whole managed suite | 4,253 passed, 2 prerequisite failures; detailed below |
| Final whole managed suite scoped to available prerequisites | 4,261 passed; excludes exactly the two documented absent prerequisites |
| Python runtime packaging / wheelhouse policy tests | Both passed against the actual final staged payload; release validator passed 1.6.1 with 109 wheels |
| Authority CPython runtime input | Official CPython 3.11.9 Windows x64 NuGet SHA-256 verified: `9283876d58c017e0e846f95b490da3bca0fc0a6ee1134b2870677cfb7eec3c67` |
| Historical packaged runtime build attempt | At clean `53dcd439`, offline verification passed, but required dependency audit failed; replaced by the qualified final-source build below |
| Qualified final packaged Python/MSAL payload | Passed at clean `32a4fe51`: both isolated offline installs/imports, exact lock matching, `pip check`, cache removal and dependency audits; no broker extras |
| Packaged auth smoke on CPython 3.11.9 | Passed: actual MSAL with synthetic signed ID tokens, actual Google SDK STS wire, forced refresh, missing-oid refusal/cache preservation and Windows DPAPI/disconnect tombstone and actual loopback TLS certificate verification; zero cloud traffic |
| Independent authentication/whole-branch review | Fresh independent review of `bc19d4af..53dcd439`: 137 focused Python tests passed; four Important findings, no Critical/Minor findings; all four fixed with failing-then-passing regressions and fresh source suites |
| Installed firm sign-in and media acceptance | Not run; administrator setup, two approved identities and spend approval required |
| Private resource/user/quota billing attribution | Pending live observation |

## Independent review fixes

- Committed activation failure and post-commit cancellation retain the newly active generation, cleared pending/legacy state and retirement block. A closed failed configuration response carries local status to C#; UI cancellation reconciles local status without retrying authorization or claiming success.
- Every deliberate disconnect persists an authorization-epoch tombstone, including an empty profile. A browser held in a different configuration-service instance cannot restore the first legacy authorization afterward.
- Initial metadata, browser and post-browser deadlines reach the asynchronous configuration caller. Expired workers remain retained and revoked until they settle, and cannot activate late. Entra `read1` and unaggregated STS reads yield between network chunks; real local slow-response tests exercise both transports without cloud traffic.
- Legacy save/disconnect release the credential mutex before Chirp recycling. Deterministic concurrent tests use the actual launch guard and replacement lock; neither test starts a child process.

The first broader Python run overlapped the heavy package build and failed one existing Windows child-process startup handshake before its mutex test could begin. The final plan suite passed twice without changing or weakening that test's timeout. The final managed unexcluded failures are `Task7_original_producer_values_survive_managed_http_parser` (missing real external Prime producer fixture: “Stage B requires the real producer fixture from its Python gate”) and `SupersededSolverRaceSpec_LinksToTheNormativeLifecycleDesign` (absent historical `2026-06-13-rir-gh-solver-enabled-race-design.md`, also absent in the primary checkout). Their fixtures/documents were not fabricated, and the unexcluded gate is not described as passed.

## User review follow-up — 2026-10-06

The user's review of `404747c4` reproduced seven remaining findings and confirmed the earlier source/runtime evidence. All seven were addressed before any merge, deployment or live acceptance. Follow-up product commits are `b07d49d0`, `c7af620d`, `dc6ef668` and `6f918209`; the reviewed runtime security patch is `32a4fe51`.

| Finding | Regression evidence and resulting behavior |
|---|---|
| Dispatch after disconnect | Five stale delivered-lease cases failed with an HTTP call before the fix, then passed with zero calls. Owned binding validation now runs after request construction immediately before the transport's dispatch callback/send for image submission and video submit/poll/fetch. Accepted submissions retain their original binding and ambiguity rules. |
| Slow blocking input exceeds deadlines | Eight actual loopback slow-header/body cases failed before the fix, then passed with absolute cutoff and cancellation. An owned socket guard interrupts callback parsing, response headers, bodies and TLS handshake. STS rechecks cancellation/deadline after transport setup and before dispatch. Local trusted/untrusted certificate checks pass on development Python 3.12.9 and packaged Python 3.11.9; redirects and retries remain disabled. |
| Busy disconnect hangs in recycler | Held-recycler and managed committed-deletion regressions failed before the fix. Disconnect now confirms local deletion before a bounded retirement wait; timeout/failure returns closed deletion status with `vertex_restart_required`. The recycler remains tracked until it settles, blocking overlapping mutations. |
| Recovery leaves stale restart warning | Both successful recovery and recovery superseded during status reading failed before the fix, then passed. The view refreshes firm status after the check and uses its existing epoch guard; a later disconnect cannot be overwritten by the old check or status response. |
| Uncorrelated workforce refresh counts | Old count-only evidence, including an arbitrary Entra count of 99, passed before the fix and is now rejected. Closed generation context and ordered Entra-refresh/STS/poll records must share operation, binding, employee and project labels, match provenance/case timestamps and substantiate each count. These remain operator evidence, not independent cloud observation. |
| Missing approval masks excess submissions | Four submitted videos without approval returned `not_run` and actual CLI exit zero before the fix. Invalid/over-budget evidence now remains `failed` and the CLI exits one, including when installed verification is absent. No extra submission is authorized. |
| STS outage misclassified as denial | 429/500/503 failed classification regressions before the fix. These now use the sanitized `vertex_request_failed` service-unavailable path; 400/403 remain exchange denial. Every exchange still makes only one attempt and exposes no provider body. |

The focused follow-up gates passed: 103 Python I/O/lifecycle/exchange cases, 54 acceptance-validator cases and 25 managed configuration cases. Managed evidence was freshly rebuilt/tested at the seven-fix source; the later dependency-only commit changes none of those managed bytes. The expanded final gates passed 582 Python tests (five documented external Prime cases deselected; 11 existing warnings) and 4,261 managed tests (the same two documented external prerequisites excluded). The seven product fixes introduced no new dependency, audit exception, exchange protocol, cloud permission or media budget. Requalification subsequently required the reviewed existing multidict security patch described below. Final packaging at clean `32a4fe51` passed both isolated offline verifiers, lock matching, cache checks, audits, staged release validation and packaging-policy suites. The packaged SDK/DPAPI smoke also passes actual local TLS certificate verification. The packaged C-extension reference-leak probes pass for both dictionary types and affected operators with intersection controls. Task 10 remains unrun; actual tenant policy, model access, playback and billing remain unverified.

## Packaged qualification and resolved audit failure

The source-build authority used clean Rook `53dcd439`, clean Chirp `12230c7a9ce71104a4de31f9bc29b444cbc0b135`, accepted hash-locked dependency wheels and the exact MSAL 1.39.0 wheel (`2d2577886906cd7293850dffa2da29119966c213bfc6ec0cecf8bf7621e1ca77`). No broker extras were admitted. Both offline verifiers imported Rook/Chirp from isolated site-packages, confirmed MSAL 1.39.0 and Google auth 2.56.3, matched installed versions to the locks, removed installation caches before checks, and reported no broken requirements. These are partial runtime-input results for that build source, not qualification of the final source.

The audit reported LiteLLM 1.89.4 (`PYSEC-2026-4066`) and PyJWT 2.14.0 (`PYSEC-2026-4141`). No new vulnerability ignore was added, no release manifest was fabricated, and the attempted payload was not installed. The first invocation also exposed an operator error from a relative BuildRoot; the corrected absolute-path invocation reached the separate audit failure.

The [security-pin maintenance plan](../plans/2026-10-05-enterprise-google-workforce-runtime-pin-remediation.md) records deliberate Task 9 maintenance to LiteLLM 1.89.7 and PyJWT 2.15.0. Maintainer advisories, universal-wheel hashes, a clean targeted audit and the exact two-package resolver diff were reviewed before admission. All other versions and extras remain unchanged. A hash-verified test overlay exercises updated libraries without changing the shared development environment or installed Rook. The historical authority rebuild at `2c993d3a` passed both isolated runtime verifiers and both dependency audits. The audits retain only the pre-existing cache exception `CVE-2025-69872`; this work added no ignore.

The corrected-source authority rebuild at clean `6f918209` passed both isolated offline verifiers, then failed the required Rook audit on multidict 6.8.0 (`CVE-2026-104874` / `GHSA-54p9-h82j-f925`). Development 6.7.1 was also affected. The same maintenance plan records reviewed admission of multidict 6.9.1 only: maintainer advisory, independently checked CPython 3.11/3.12 Windows binary-wheel hashes, a targeted clean audit and an exact one-package UV graph diff with unchanged dependency declarations/extras. Small actual C-extension ownership probes failed on 6.7.1/6.8.0 and passed on 6.9.1; the expanded 582-test Python suite passed again under the checked overlay. Shared development and installed environments remain unchanged. The clean corrected-source authority rebuild at `32a4fe51` then passed both isolated verifiers and both audits; release validation, policy tests and the source-origin/exact-pin SDK/DPAPI/local-TLS/reference-leak smoke passed. No new audit ignore or runtime fallback was added.

Expanded text/DSPy/configuration/auth regression testing under these updated pins found five additional cases requiring the same absent real Prime checkout/Node loader: `test_task7_real_prime_writer_sdk_http_and_panel_fixture` and the four parameterizations of `test_real_prime_writes_refresh_and_replacement_preserve_acl`. The unexcluded expanded run passed 550 cases and failed those five prerequisite cases. The scoped rerun excludes exactly these two functions, with all available tests retained. They are not treated as a successful real Prime integration gate.

Final follow-up verification rebuilt Rook and then RookBim in Debug and Release before the managed tests, with zero build errors, then passed the scoped 582 Python and 4,261 managed tests and both packaging-policy suites. An operator-only Bash/PowerShell module-path issue and propagation of an intentionally failing negative test's exit code were corrected in the ignored verification runner. Product validators and negative tests were not weakened.

The authority build uses release version 1.6.1 and the verified CPython 3.11.9 input above. Qualified runtime pins include MSAL 1.39.0, Google auth 2.56.3, PyJWT 2.15.0, LiteLLM 1.89.7, Requests 2.34.2, packaged Cryptography 50.0.1 and multidict 6.9.1. The existing development Cryptography profile remains 50.0.0. The [packaged smoke fixture](../../../mcp_server/tests/fixtures/vertex_workforce_packaged_smoke.py) runs with the isolated installed-wheel interpreter and `-I`; it verifies module origins and production-source equality as well as the synthetic SDK/DPAPI lifecycle. It does not substitute for live identity, policy, model or billing checks.

| Qualified artifact | SHA-256 |
|---|---|
| Runtime manifest | `5650589ce015556fa482c73956039882c0b6a41a26321dfc04d365f75426f147` |
| Rook 1.6.1 wheel | `d6c4eb57f590257de032e2777abc5a3847389bb6a7b81cd0bd57a23820729974` |
| Chirp 0.1.0 wheel | `1cae4080a078daf8b9bed4e1d0d59eee470708abbdf72d40a6f9b329a918e14b` |
| Rook dependency audit JSON | `93d5b3a80421e05b3d714caecd97e26aa32c2f4c03a5d75b84a01651381d6e7f` |
| Chirp dependency audit JSON | `570604a91e8b7bb767818d456d60074284648a6dfd7a22e4b097cdd8363061b2` |

The full manifest, raw build logs and local staging paths remain uncommitted. Installed acceptance still requires private Entra/workforce-pool/project setup, two permitted identities and explicit approval of the one-image/three-video budget. No cloud application, IAM grant or Conditional Access change was made by this implementation.

No output parsing/allocation limits changed in this workforce implementation. The earlier inline-video memory measurements retain their original host/commit scope; they are not claimed as measurements of a new installed workforce pilot. Existing local-stop/publication and restart tests remain automated proof, distinct from the three-video live budget.

Actual settings, identifiers, caches, assertions, logs, account/project mappings and generated media remain outside all repositories/worktrees. Committed fixtures use synthetic identifiers. See the [administrator setup guide](../../guides/enterprise-google-workforce-setup.md).
