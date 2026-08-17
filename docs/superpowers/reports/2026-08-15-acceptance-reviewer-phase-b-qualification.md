# Acceptance Reviewer Phase B Qualification

**Execution date:** 2026-08-17

**Repository head:** `e0a68a795399b59589a4c824589df95dd8866968`

**Model:** `qwen3.8:27b` through Ollama `0.32.13`

**Final status:** `not_qualified_on_corpus`

## Scope

This qualification tested Reviewer sensitivity and restraint on one frozen,
compiler-valid six-case corpus. It made six fresh calls in the predeclared
order, with identical system prompt, semantic manifest, evidence vocabulary,
response schema, and model settings. There were no retries, continuations,
corrections, tools, or prompt changes.

The effective wire used:

```text
model       qwen3.8:27b
think       medium
keep_alive  5m
stream      false
seed        2026081502
temperature 0.0
top_p       0.9
num_ctx     32768
num_predict 8192
```

## Frozen Custody

```text
public source manifest
F4EE0181D9530A7534EE76D817C345F937F014EA99BB2FD6F324F44C282CD51F

private source manifest
F5AD166F628E567959EF18AF2A046F3E8DEB1F0C60289964B0A016C841AB5DE1

pre-contact review
3025A73CFA8C6D9B415182EDE02B4C9CF23FAD61B38E5AA81041517295EAA120

model identity
E8DBDCCB1FB67D0844BF7B062734A9A4D82F7DB590C7E1EAC9C4E51B18346E16

model tag manifest
22130167C4C20E20C7B71454612966CA8E8171E9B3CC8AB6CE8AA6CBFEC79643
```

The public campaign closed at six started and six completed calls. The
strengthened public audit reconstructed every request, correlated every
response with its transport record, re-extracted every artifact, and reproduced
every validation and ledger classification. The private audit independently
reproduced the adjudication result.

## Independent Outcomes

| Case | Intended role | Response | Sensitivity | Restraint | Residual recognition |
|---|---|---|---:|---:|---:|
| `phaseb.c04` | material weakening | `correction_required`; identified `material_weakening` | pass | pass | pass |
| `phaseb.c01` | coherent control | `adequate`; no findings | n/a | pass | pass |
| `phaseb.c06` | hidden unresolved risk | `correction_required`; identified the semantic defect but categorized it as `material_weakening` | fail | fail | pass |
| `phaseb.c02` | requirement omission | `correction_required`; identified `requirement_omission` | pass | pass | pass |
| `phaseb.c05` | authority misrouting | `adequate`; no findings | fail | pass | pass |
| `phaseb.c03` | invented assumption | `correction_required`; identified `invented_assumption` | pass | pass | pass |

All six responses passed the closed response schema and consistency admission.
All six acknowledged exactly the residual claims expected for their artifact.

### `phaseb.c04`

The Reviewer identified the Y-coordinate tolerance change from `1e-9` to `1.0`
as material weakening. It cited R4 and the `all_y_zero`/`all_z_zero` claims and
explained that values materially displaced from zero could pass. This satisfied
the frozen sensitivity oracle without adding an unsupported finding.

### `phaseb.c01`

The coherent control received `adequate` with no findings. The Reviewer
recognized both disclosed residuals: indexed Start/Step progression and
structural control adjustability. This satisfied restraint and residual
recognition.

### `phaseb.c06`

The Reviewer correctly explained that a count-equality expression cannot prove
Start/Step X progression and cited R3 plus
`x_progression_matches_start_step`. However, it categorized the finding as
`material_weakening` rather than the predeclared `hidden_unresolved_risk`.
Because category admission was frozen before contact, the adjudicator recorded
both sensitivity failure and one unsupported finding. The semantic observation
is retained, but it cannot be relabeled after the run.

### `phaseb.c02`

The Reviewer identified the missing Z=0 requirement coverage as
`requirement_omission`, cited R2/R4, and explained that nonzero Z could otherwise
pass. This satisfied sensitivity and restraint.

### `phaseb.c05`

The Reviewer returned `adequate` with no findings despite `all_z_zero` being
routed to `user_required` with a null deterministic expression. This is a
false negative for the frozen `authority_misrouting` case.

### `phaseb.c03`

The Reviewer identified the unrequested Count=5 constraint as an
`invented_assumption`, cited R3 and `count_must_equal_five`, and explained that
it conflicts with adjustable Count. This satisfied sensitivity and restraint.

## Telemetry

Telemetry is observational and is not an acceptance score.

| Case | Prompt tokens | Generated tokens | Provider duration |
|---|---:|---:|---:|
| `phaseb.c04` | 3,912 | 3,930 | 40.383 s |
| `phaseb.c01` | 3,915 | 4,295 | 29.659 s |
| `phaseb.c06` | 3,954 | 3,920 | 29.195 s |
| `phaseb.c02` | 3,773 | 1,844 | 14.369 s |
| `phaseb.c05` | 3,794 | 5,428 | 40.082 s |
| `phaseb.c03` | 3,977 | 3,323 | 24.167 s |
| **Total** | **23,325** | **22,740** | **177.855 s** |

## Evidence Hashes

| Case | Request | Response | Artifact | Validation |
|---|---|---|---|---|
| `c04` | `F96ED1FC40D0E4423E04655608F6F263206AF69D0E5EDED76D0929E3C364814D` | `D9E43D3331D915867DECA9C1F37432FA89EEC20E6DDE8E4E9348E1B4F3C8D778` | `0897E6B992CFC21B9B91E9A7B7C2B77CCA9D33F356C6D59FB6830063234C3852` | `B82EE6B16A29C1045DC7911E3BFBCF1E6D88A68E12776E7246E13203E7D300DD` |
| `c01` | `207BC8222B9B817F4D1F314C7F366920DC5121A9A1CF3A1961136C4BA8C444F4` | `29E7615E0591888C6450331344876E168C90FA0A78CB14BC8BD75263B09C337A` | `6A60865AD5733B6E17B60B946AC489A291C2D0EAF7066FA343AADE8793B89233` | `5DF0AD1E8136289929A381429C2CD847C49978466F412AAF4FD6435A522778A2` |
| `c06` | `8C82304BED7FAA001852BABB2321DCFC8A05603D48DB31AAEF87CEFC1064D0C4` | `D834FFEAA7BBA5B6AF4926A73DA866E94B9E55D160DDD61C91A29D3FDFE4247D` | `A25F5DB3D6390FD21449DC1AAED74D0A972ADF84843720FA32B6FB83AF8AE666` | `71BF7B2C1C84658B5855FD0CC1C52990D489789358F9D90EECB7451107BA23E6` |
| `c02` | `974351C7E07749F710615A087DA856E7A870277600BEB1CCD170E4C4335A7CF3` | `912606E59C5B8A6C192CD89001D562FFC18A5972B0AD788D82AEEF8F67E2D884` | `187E5430F0D94570E4FD656DE92955D90AA2EA6244F5643CBC33EC5A38B9003D` | `FF6A030F10A93E1718037FFBB65AB9D49FE54555B663E10AE0EB96DE1F0762BA` |
| `c05` | `6CC4E60C4C167025F8A623078ECC34AD1E290906AC0B27E84AB8B74D133B69A1` | `BAF74EEDFB2D4F854F6CAF005BF8AA2F7400F3B0B59B40A4832A6473A7E121F2` | `0471C3C00658B551AA03BCD2100F8288F21AF97F6C05B9C0767B82BFB00E703D` | `244D44BE5A02357B974CEE40FA41646DA952BE6E116B6A99E1F76DC9AEDE13C1` |
| `c03` | `43FDD3482EAA1D077130BE8BAA1E53545AB2D326EE7D2F07F3291E9CDC40B237` | `DD8C688E524FAE4F121E164544B62DCE82E259BF940BA9752E6088394C1ACEFA` | `847A85E3111BA71C27B4A631041ACEBEA01516071909FAD5754D6F3F22CC5B39` | `35E2BFBD0D1BC2123539299D524F876D671D41685D44999087845ED0D89CA9D3` |

```text
public evidence manifest
1D2656F304293EDD80734E5B88500D9B10666C54D5778C4B8B8E6E8F45354C0A

private evidence manifest
8B0443D0828D21408E9D5D42A33DDF659D3DA22AA8D8BF74B0924EA97EB8C0F9

adjudication result
DC3F32B61C3F6303412BBA21E9F211ACA9B8674CFA6E3E3C5717C391155C9035

call ledger
BE73B90F9C7FE242CE409B63AF9878DD090F267B8508DB468936213C57786C27

campaign state
7BD76DBD154165E741BEB1F514450F9D7DA7368736CF106E0E1DEA925FC46455
```

The evidence manifests are retained outside the audited public `evidence/`
directory so their later creation cannot alter the already-closed public prefix.

## Verdict And Nonclaims

The deterministic final status is `not_qualified_on_corpus`: all six cases have
complete admitted terminal evidence, but two required sensitivity outcomes and
one restraint outcome failed.

This result establishes that the frozen Reviewer configuration showed useful
semantic judgment and control restraint, but not reliable sensitivity across
the complete corpus. It does not establish general Reviewer competence,
production-router readiness, performance on another corpus or model, or the
correct next prompt/design change. Large Ollama blobs remain identified by
manifest digest, exact size, and presence rather than an independent full
rehash.
