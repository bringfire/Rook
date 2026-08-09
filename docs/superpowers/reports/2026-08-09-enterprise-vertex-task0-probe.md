# Enterprise Vertex Provider Task 0 Dependency Probe

**Date:** 2026-08-09
**Status:** Blocked pending reviewer direction; no dependency is admitted
**Approved plan:** `5a2d1d7288f15f150f3f2d31afdd7e97d5cebb02`
**Approval tag:** `plan/enterprise-vertex-provider-2026-08-09-approved`
**Specification:** `4a16658b77bbb00a29146b7d2853c5484add044b`
**Rook base:** `a867f8e06ae8aca904102104c47780d02d5640b8`
**Chirp base:** `c7b1aacec6b1ae23514cb9fb0d2a365e1fb7a468`

## Outcome

`google-auth==2.56.3` resolved cleanly in Rook's locked project copy, but the
planned Chirp probe did not preserve the shipped LiteLLM version. A fresh
editable install from Chirp's source metadata selected `litellm==1.96.0`, while
the plan requires and the installed product uses `litellm==1.89.4`. The exact
planned assertion therefore failed.

This is a reproducibility problem in the Chirp probe boundary, not evidence of
a `google-auth` incompatibility. Task 0 does not admit `2.56.3`, Task 1 did not
begin, and no implementation file was changed. The reviewer must decide whether
the Chirp probe should consume the sealed release constraints or whether Chirp
must first gain an independently reviewed dependency constraint.

## Provenance and installed-state checks

- The approval tag is annotated and resolves exactly to the approved plan.
- The specification-to-plan diff contains only the plan document.
- `origin/main` remained at the recorded Rook base; no synchronization merge was
  required and no planned-path overlap existed.
- The clean Chirp worktree was created at the exact pinned base.
- Installed Rook and Chirp both reported `litellm==1.89.4`.
- `google.auth` was absent from both installed environments.
- Installed LiteLLM source contains the required
  `google.oauth2.credentials`, `google.auth.transport.requests`, and
  `vertex_credentials` seams.

## Candidate and direct/transitive resolution

The prior reviewed candidate was `google-auth==2.56.0`. The probe used
`google-auth==2.56.3` because it is the current patch in the same `2.56.x` line
at execution time. That current-patch rationale is not an approval and did not
permit an automatic fallback to `2.56.0`.

### Rook disposable resolution

The probe used CPython `3.11.9` and `uv 0.11.3`.

| Role | Package | Resolved version | Result |
|---|---|---:|---|
| Direct | `google-auth` | `2.56.3` | Added |
| Transitive | `pyasn1-modules` | `0.4.2` | Added |
| Transitive | `pyasn1` | `0.6.4` | Added |
| Reused prerequisite | `cryptography` | `49.0.0` | Existing lock entry satisfied `google-auth` |
| Existing integration | `litellm` | `1.89.4` | Unchanged |
| Existing integration | `dspy` | `3.2.1` | Unchanged |

The normal lock regeneration added exactly `google-auth`, `pyasn1-modules`, and
`pyasn1`. It removed no package and changed no existing package version, source,
wheel, sdist, or artifact hash. Only the local `rook-mcp` record changed as
expected to declare the new direct dependency. Imports passed and `uv pip check`
reported all 108 installed packages compatible. The planned
`python -m pip check` form was unavailable because the `uv` environment does not
install `pip`; the non-mutating `uv pip check --python <venv>` equivalent was
used and recorded rather than changing the environment.

Added wheel records:

| Package | Wheel SHA-256 |
|---|---|
| `google-auth==2.56.3` | `8ec438808f813ad034535000261eed1067475d229d05bbf4216e78c3f2362e53` |
| `pyasn1-modules==0.4.2` | `29253a9207ce32b64c3ac6600edc75368f98473906e8fd1043bd6b5b1de2c14a` |
| `pyasn1==0.6.4` | `deda9277cfd454080ec40b207fb6df82206a3a2688735233cdcd8d3d565f088b` |

### Chirp disposable resolution

| Role | Package | Installed product | Fresh source resolution |
|---|---|---:|---:|
| Direct candidate | `google-auth` | absent | `2.56.3` |
| Transitive | `pyasn1-modules` | absent | `0.4.2` |
| Transitive | `pyasn1` | absent | `0.6.4` |
| Transitive | `cryptography` | absent | `50.0.0` |
| Existing integration | `dspy` | `3.3.0` | `3.3.0` |
| Existing integration | `litellm` | `1.89.4` | `1.96.0` |

The Chirp environment imported `google.auth` successfully and `pip check`
reported no broken requirements. It nevertheless failed the required
`litellm==1.89.4` assertion. Chirp's source metadata admits `dspy>=2.6`, whose
fresh resolution currently admits the newer LiteLLM; the installed release
payload obtains its narrower version from Rook's sealed release constraints.
No source constraint was changed during this probe.

## Pinned implementation contracts

- Google auth candidate: `2.56.3` in Rook and Chirp; admission is pending.
- LiteLLM kwargs: `vertex_project`, `vertex_location`, and
  `vertex_credentials`.
- Credential shape: an in-memory `authorized_user` dictionary.
- Model admission: only `vertex_ai/gemini-*`; only the `vertex_ai/` provider
  prefix is removed when constructing the Google publisher-model URL.
- Unsupported Vertex model families receive the stable closed rejection.
- Passive health and model enumeration remain local and network-free.
- Explicit **Test Vertex** and installed acceptance may call `countTokens` with
  constant Rook-owned text; admitted inference may refresh authorization and
  contact Vertex as required.
- Mutex: `Local\BringFire.Rook.VertexAuth.v1`, bounded to `10000` ms.
- Event: `Local\BringFire.Rook.Chirp.VertexGenerationChanged.v1`, manual reset.
- Every Rook-launched Chirp child uses `--rook-managed` for cooperative
  retirement. `--rook-vertex-bootstrap-stdin` is reserved for Vertex credential
  bootstrap. Force termination requires exact current-manager live-process
  ownership; rediscovery alone never grants it.
- Packaging must use recorded immutable Rook and Chirp merge SHAs, not branch
  tips.
- Technical acceptance remains distinct from production OAuth verification,
  enterprise-admin guidance, and managed-business validation.

## Cleanup and stop state

Automated removal of the disposable probe directory was blocked by the safety
layer after exact-path validation. The remaining bounded cleanup target is:

`C:\Users\aryan\AppData\Local\Temp\rook-vertex-dependency-30605fa2da6545089f7aabfb5805124d`

No client material, credential value, provider response body, Google identity,
Google Cloud project identity, model prompt, token, or service-account path is
recorded here.

Task 0 stops at this report. The exact dependency and Chirp reproducibility
boundary require reviewer admission or amendment before any implementation.
