# RookChat Prime Primary Backend Slices 1-2 Live Smoke

**Date:** 2026-08-28
**Status:** Qualified for the exact opt-in, text-only product path described below

## Result

The first RookChat-to-Prime product vertical completed one authenticated turn
through the installed RookChat panel and returned to its durable `idle`
lifecycle state.

```text
prompt:   Reply with exactly PRIME_ROOKCHAT_SMOKE_OK and nothing else.
response: PRIME_ROOKCHAT_SMOKE_OK
```

The panel displayed the response and selected model, the Stop control was
disabled after settlement, and the retained Prime session records a normal
`stop` result. The Rhino document remained empty.

**Disposition:** pass for Slices 1-2 on this exact path.

## Frozen implementation

| Owner | Commit |
| --- | --- |
| Rook | `964594b00f1983d275faf03a44d0698f45984ca4` |
| Prime | `7690c18479c909ddea67a34e86114f7f982179a8` |

Both source worktrees were clean after the smoke.

The live configuration was:

```text
backend:   prime, opt-in
provider:  openai-codex
model:     gpt-5.6-sol
reasoning: low
mode:      rpc
```

Prime was launched with tools, extensions, skills, context files, and prompt
templates disabled. ChatRunner remained the default backend. No API key was
supplied by Rook; `openai-codex` used the previously authenticated ChatGPT
subscription OAuth route. No authentication file, token, environment value, or
other credential is retained in this evidence bundle.

## Retained evidence

Evidence root:

```text
C:/UDEV/RookEvidence/2026-08-28-rookchat-prime-primary-backend-slices-1-2-live-smoke
```

The bundle contains only:

- the RookChat panel screenshot;
- the exact durable conversation-registry record; and
- the exact Prime session JSONL.

The selected source records were inspected for common credential fields before
copying. Their bytes were preserved unchanged.

| Artifact | SHA-256 |
| --- | --- |
| `operator/rookchat-prime-smoke-panel.png` | `578648A9A4A86EF98DE706BDF02EEF30D17DBEB7F84A306C6ADD20C901BED1DA` |
| `operator/conversation-registry.json` | `DD168717C6CC6F6FBBB1637B009A7E62615E6B0C2CF9F81F902297E9F09C0B3D` |
| `operator/prime-session.jsonl` | `240A40C6FCC8F016E52813B4A4E20E1FFD146C039917003CA42372B1F3952729` |
| `evidence-manifest.json` | `89423187ACFB6DD52D92F0DA4FF62895A2AAB2BFB312730312A3CEF3ADDB273E` |

The non-self-referential manifest independently verified all `3/3` entries with
zero missing files, size mismatches, or hash mismatches.

## Runtime facts

The durable registry binds the conversation to:

```text
conversation:   conv_626657b086934c06833ad2ae782aa409
Rhino PID:      21340
process start:  639235155943745535 UTC ticks
document serial: 268435457
lifecycle:      idle
```

The retained assistant message records:

```text
provider:    openai-codex
model:       gpt-5.6-sol
API:         openai-codex-responses
stop reason: stop
input:       892 tokens
output:      12 tokens
total:       904 tokens
```

A read-only `/objects` observation after settlement returned `count: 0` and
`totalCount: 0`. No Rhino or Grasshopper mutation occurred.

## UI note

The panel still labels the conversation `Architect` and says `Connected to
Architect agent`. This is a cosmetic legacy-label mismatch because Prime is the
active backend. It is recorded as a nonblocking P3 and does not affect routing,
settlement, or retained model identity.

## Qualification boundary

This smoke qualifies only:

```text
RookChat panel
-> local chat service
-> opt-in Prime RPC backend
-> subscription-authenticated openai-codex/gpt-5.6-sol:low
-> one text prompt
-> correlated settled response
-> durable idle registry state
```

It does not qualify:

- Prime as the default RookChat backend;
- any Rook, Rhino, or Grasshopper tool call;
- IPython, skills, extensions, context files, or prompt templates;
- mutation, images, steering, cancellation, or model switching in the live UI;
- multi-turn residency, restart recovery, or packaging outside this installed
  development configuration; or
- semantic correctness beyond the exact-response smoke prompt.

Rhino and the completed panel conversation were intentionally left open after
evidence preservation.
