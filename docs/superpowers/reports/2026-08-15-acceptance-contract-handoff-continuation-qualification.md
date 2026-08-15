# Acceptance Contract Handoff Continuation Qualification

**Date:** 2026-08-15

**Classification:** Completed offline qualification

**Product changes:** None

**Rook documentation baseline:** `274e7d4726c6c3120d4870a641db24286b5f15a6`

## Result

The point-row-only V2 qualification completed both admitted model calls:

```text
V1 Constructor artifact
-> exact mechanical diagnostic
-> one same-conversation Constructor continuation
-> unchanged mechanical validation: pass
-> one fresh Reviewer session
-> unchanged mechanical validation: pass
```

The continuation repaired the V1 cross-reference defect. Every role reference now uses one of the declared role IDs `start`, `step`, `count`, or `points`. The unchanged constructor validator accepted the complete replacement artifact.

The fresh Reviewer returned:

```text
disposition: adequate
findings: []
all five dimensions: adequate
```

This proves that Qwen3.8:27b can consume an exact compiler-style diagnostic and serialize a mechanically coherent full replacement artifact in one bounded continuation. Reviewer transport and envelope validity passed; semantic sensitivity failed on this specimen.

## Frozen Inputs And Isolation

The V2 Constructor request reconstructed the exact V1 conversation:

| Message | Role | Content SHA-256 |
|---|---|---|
| 1 | `system` | `044EF95E9CD1AD09C6F40B850137D19B4ED13DE0C9D8E9D6E25ACC780868F88A` |
| 2 | `user` | `74CE7D60BD40BBBEC7ACE398D78F0A914134168865CEC16EC17E4405E91E2126` |
| 3 | `assistant` | `2B6973A30EAA456C93205230417CF60978E50C57A01FF3FA9F3348E631781DA5` |
| 4 | `user` | `0E5FE2F59EABCE98E024E75E480CD37A14912E596FE8B8BF86C438B8A5D289A9` |

The fourth message contained only:

```text
$/requirements/0/roleIds:unknown_refs=['points_output', 'start_control', 'step_control', 'count_control']

Return one complete replacement artifact. Do not return a patch.
```

The Reviewer was a fresh two-message session. It received only its frozen system prompt and a user message containing the original intent, accepted artifact and hash, frozen evidence vocabulary, and reviewer schema. It did not receive Constructor reasoning, the original invalid artifact, or the continuation diagnostic.

Critically, the Reviewer also did not receive `_expression_semantics()`. The Constructor received that operation contract, while the Reviewer received only the evidence vocabulary and JSON schema. Its retained reasoning consequently said it would “assume” the operations were valid. The empty adequate review is therefore a causal Reviewer-input defect as well as an observed false negative; it must not be interpreted as evidence that a fully informed Reviewer would behave the same way.

The constructor schema, reviewer schema, evidence vocabulary, system prompts, original point-row intent, and retained V1 source artifacts were byte-identical to V1. The V1 evidence directory was not changed.

## Prefix Closure Repair

Before contact, the V2 disposable harness made terminal evidence-prefix closure first-class:

- A mechanically refused Constructor replacement closes and audits as a one-call `incomplete` prefix.
- A mechanically accepted replacement may admit exactly one fresh Reviewer call.
- A completed Constructor plus Reviewer closes and audits as a two-call `completed` prefix.
- Every started call must have exactly one terminal `call_result` or `call_failure` event.
- The final manifest covers the retained prefix and detects post-closure size, hash, or membership drift.

The no-contact suite passed **30/30** tests. It included causal coverage for an expected Constructor refusal, successful conditional Reviewer admission, malformed provider response closure, later-call refusal after an early Constructor failure, and post-closure evidence mutation.

The V2 precontact manifest contained 19 entries with zero mismatches:

```text
002FF78530A46CDF86D8B5E31FDA605E3AC4E05F341CBD93FD35CCCBCE4C2651
```

## Calls And Telemetry

| Sequence | Call | Result | Prompt tokens | Generated tokens | Provider duration |
|---:|---|---|---:|---:|---:|
| 1 | `point_row.constructor_continuation` | HTTP 200, mechanically accepted | 5,790 | 2,345 | 22.196 s |
| 2 | `point_row.reviewer` | HTTP 200, mechanically accepted | 9,006 | 181 | 44.405 s |

Totals are 14,796 prompt tokens, 2,526 generated tokens, and 66.601 seconds of provider-reported duration. These are observational Ollama telemetry, not a quality score.

There were no retries, repair calls, fallback models, external-provider calls, or Rhino, Grasshopper, or Rook contact.

## Semantic Assessment

The accepted replacement fixed identity consistency but otherwise remained substantively close to V1. It retained useful honesty:

- The exact indexed `Start + i * Step` relationship remains explicitly `unproven` because the flat expression vocabulary cannot represent indexed collection access.
- Structural adjustability remains explicitly `unsupported` by the frozen evidence vocabulary.
- The artifact does not prescribe Grasshopper component topology.

It also retains semantic questions that the fresh Reviewer did not report:

- The `coordinate` expressions for Y and Z are applied to the collection role without an explicit `for_all` or other qualified collection operator, while their statements claim every point.
- The count expression compares `collection_count(points)` directly with the `count` control role without a closed scalar-value projection.
- Adjustability is assigned `user` authority even though the eventual implemented property would still require attributed evidence or judgment.

The mechanical validator was not designed to decide those meanings, so its pass is correct. The underinformed Reviewer returned no findings. Therefore the supported Reviewer conclusion is:

> Reviewer transport and envelope validity passed; semantic sensitivity failed on this specimen. The missing expression semantic contract is a causal input confounder.

## Recorded Schema Pressure

V1 also exposed a lexical asymmetry: declared role IDs must match `^[a-z][A-Za-z0-9]*$`, while reference lists accept arbitrary nonempty strings. That mismatch plausibly increased serialization pressure when Qwen moved from underscore-form working names to camel-case-admitted declarations.

The schema was intentionally unchanged in V2. Any later schema design should give declarations and references one shared lexical ID definition. This qualification does not authorize that change.

## Evidence Custody

Root:

```text
C:/Users/bring/AppData/Local/Temp/rook-acceptance-contract-handoff-qualification-v2/operator
```

Headline SHA-256 values:

| Artifact | SHA-256 |
|---|---|
| V1 retained prefix manifest | `758E33DDD31DED0104EC67B25C7519C6B3296438B61898856A26F610F11E7433` |
| V2 precontact manifest | `002FF78530A46CDF86D8B5E31FDA605E3AC4E05F341CBD93FD35CCCBCE4C2651` |
| V2 evidence manifest | `38AC6B48947A0312593DF117D895D416F857938D4376B1AA329CCDCE44B8F81E` |
| V2 run status | `37EA91806B6A241409A6485CF9CDACF88F262DE4EE5AE3C78C238972743DEF7A` |
| V2 call ledger | `0A57EF8384A6FBDBEDCEF18A36CF2F8EB39243FCAC4D623E6D77F22F22F94AA2` |
| Continuation request | `FD700EF8FE30AE2735351C7DE4CE1076B343F99B8EBD0108EA60816D18D03C55` |
| Continuation response | `3642209158A73ACDCE9CA3F145095336796A97EAD7FED783EF1DBF56E8087593` |
| Accepted Constructor artifact | `5A2ECDD46AF3C8A6574B214019E5A7370B56BC5573D028277D94904653798B53` |
| Constructor validation | `B314D5C771E3B81A4B0E0BD0C3EA8B60F9ED4F4351193CF973D706C463C7662B` |
| Reviewer request | `D1066597743D3ED888BFC4D50DF68094A3AA95B592A8FA5A043E328BE92B73CB` |
| Reviewer response | `CECC99977411A35C18CCE4637107F2ED167A04AEA9C986EEE774269B88C9CFF6` |
| Reviewer artifact | `3B39A5256F2E2AA95DDD728DCA7BBD3FABD02A3F4EFB3009943CAE9794A884DE` |
| Reviewer validation | `AFDCB8E65DF1854D1B085981413F337572CEA2567AAE6F7AF96FC1E59E2393B2` |

The sealed evidence manifest contains 32 entries. A fresh `audit` reproduced:

```text
QUALIFICATION_AUDIT_OK classification=completed calls=2
```

## Bounded Conclusion

V2 answered both intended questions:

1. **Can intelligence consume exact mechanical feedback?** Yes. The Constructor corrected the identity defect in one continuation without schema changes or a patch response.
2. **Can the V2 Reviewer detect semantic weakness here?** No. Reviewer transport and envelope validity passed, but semantic sensitivity failed on this specimen. The Reviewer was underinformed because its request omitted the expression semantic contract.

No grid or helix call ran. No production compiler, router, schema, vocabulary, or model configuration changed. The next decision should concern Reviewer authority and criteria—not another model call hidden inside this completed slice.
