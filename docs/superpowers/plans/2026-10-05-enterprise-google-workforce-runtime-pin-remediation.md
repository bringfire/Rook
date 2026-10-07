# Workforce runtime security-pin maintenance

Status: deliberate maintenance within Task 9's required audit/qualification work. The exact two-package metadata/hash/advisory changes were reviewed before admission; other dependency versions and extras remain unchanged. The workforce implementation and its final regression fixes are committed at `c9540cd6b624555f6fd1ec6fb0d70652cbba5bfe`. Runtime qualification and installation are separate later gates.

## Concrete blocker

The approved federation spec requires preserving the existing development and packaged transitive pins. The authority wheelhouse build at clean `53dcd4395ea0d3aa789dd9d771dfee5a9ebba647` completed both isolated offline installations, imports and `pip check`, then stopped at its required `pip-audit` gate. It reported:

| Accepted package | Advisory | Proposed version |
|---|---|---|
| LiteLLM 1.89.4 | `PYSEC-2026-4066` / `CVE-2026-84377` / `GHSA-3cv6-jpf6-8222` | 1.89.7 |
| Packaged PyJWT 2.14.0; development PyJWT 2.13.0 is also within the affected range | `PYSEC-2026-4141` / `CVE-2026-101918` / `GHSA-42vr-xj54-vc7v` | 2.15.0 |

LiteLLM's advisory concerns its proxy's request routing. This audit result does not establish that Rook's direct client calls expose that proxy path. PyJWT's advisory concerns an uncaught parsing exception; Rook independently bounds and validates assertions and catches validation failures. These observations do not waive the release audit gate. Maintainer references: [LiteLLM advisory and patch versions](https://github.com/BerriAI/litellm/security/advisories/GHSA-3cv6-jpf6-8222), [PyJWT advisory and released correction](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-42vr-xj54-vc7v).

## Reviewed scope and inputs

Update the two existing libraries only, in their development and packaged locks. Preserve MSAL 1.39.0, Google auth 2.56.3, Requests 2.34.2 and the existing distinct Cryptography pins. Select no new extras. Keep the accepted cache exception and audit policy unchanged. Authentication, billing, federation scope and credential ownership remain as approved.

Public PyPI metadata and downloaded universal wheels were checked without installation. Verified SHA-256 values:

| Proposed wheel | SHA-256 |
|---|---|
| `litellm-1.89.7-py3-none-any.whl` | `4a11bdeaec66b3bd64f7606bf59e238875867678f320e70dd38d8767fddde11b` |
| `pyjwt-2.15.0-py3-none-any.whl` | `7a3742debf6b879e912dbb9819ceec1594be812452b78c5f2e2dfc56564954f8` |

Their Python requirements permit packaged CPython 3.11.9. A targeted `pip-audit==2.10.0 --no-deps --disable-pip` check of exactly these two proposed versions returned zero known vulnerabilities. This establishes proposal evidence only; it does not establish full graph compatibility, source tests or final packaged qualification.

## Execution and gates

1. Amend the spec's dependency preservation rule to permit these deliberate security updates. Update Rook's exact LiteLLM requirement, the development UV lock and packaged third-party hash lock. Verify the resolver changes only these reviewed packages; stop and review any additional change. Do not modify the separate Chirp checkout incidentally.
2. Update version-sensitive acceptance fixtures/proof validation for packaged PyJWT 2.15.0. Add regression evidence for malformed/deeply nested assertion rejection and preserve real MSAL/STS synthetic wire checks. Run all Vertex/Chirp tests and the repository's dependency/runtime policy checks under the new pins.
3. Perform fresh Debug and Release rebuilds and whole managed verification. Preserve the two documented unrelated missing prerequisites as explicit unexcluded failures.
4. Commit a clean source state, then rebuild through the authority wheelhouse script with the accepted CPython runtime, matching clean Chirp source and newly reviewed hash-verified wheels. Require both offline installations/imports/version checks, `pip check`, dependency audit, provenance/licenses, the final manifest and wheelhouse validation. Record the exact source commit and sanitized artifact hashes.
5. Proceed to the installed workforce pilot only after packaged qualification succeeds and private administrator setup, two approved identities and media spend are available. The pilot remains separately responsible for refresh, disconnect/restart behavior, image dimensions/video playback and resource/user/quota billing attribution.

The execution ledger records this deliberate correction and its cost: text-library behavior could regress, so both auth/media and existing text/DSPy/configuration tests must run under the updated pins. No new audit exception or installation of the failing payload is allowed. Final qualification results belong in the workforce verification report.

## 2026-10-06 corrected-source audit follow-up

The authority rebuild at clean `6f91820902123326a7f1e13b498bc6970aa58160` completed both isolated offline verifiers, then failed the Rook audit on multidict 6.8.0, `CVE-2026-104874` / `GHSA-54p9-h82j-f925`. The development lock's 6.7.1 is also affected. The [maintainer advisory](https://github.com/aio-libs/multidict/security/advisories/GHSA-54p9-h82j-f925) identifies a C-extension reference leak in reflected items-view union and subtraction, fixed in 6.9.1. This does not establish that Rook exposes the affected operators to remote callers; the required audit gate still applies. The prior qualified payload and its hashes are historical evidence, not qualification of corrected source.

Deliberately update this existing package only, with no new dependencies/extras or audit exceptions. Public PyPI metadata requires Python >=3.10 and adds no dependency on supported 3.11/3.12 runtimes. Downloads were independently SHA-256 checked:

| Wheel | SHA-256 |
|---|---|
| `multidict-6.9.1-cp311-cp311-win_amd64.whl` | `5f89dad732280e7a10b74d40b91364f88e13c3f2c08c2ef83a8cd42f7a61af2e` |
| `multidict-6.9.1-cp312-cp312-win_amd64.whl` | `a16a1dc8529f9e734a41c3b856f3eae7ebacdc061dde3f8a844e0c7889c97203` |

The complete UV package-object diff changes only multidict 6.7.1 to 6.9.1; dependency declarations and the package set are identical. A targeted no-deps audit of 6.9.1 returned zero known vulnerabilities. Small 32-element C-extension probes reproduced 32 leaked references for each affected operator in both MultiDict and CIMultiDict on development 6.7.1 and packaged 6.8.0; intersection controls leaked zero. The same probes under a hash-verified development overlay of 6.9.1 all leak zero. The shared environment remains unchanged. Add these ownership checks to the packaged smoke fixture, run the expanded source regressions under reviewed pins, then commit and rerun the full authority build, both audits, manifest and packaging-policy checks. The prior fresh managed rebuilds/tests remain evidence for unchanged managed bytes; this update changes no C# or native source. Installed live acceptance remains separate and unrun.
