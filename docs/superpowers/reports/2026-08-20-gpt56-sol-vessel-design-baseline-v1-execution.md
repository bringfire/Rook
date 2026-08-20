# GPT-5.6 Sol Vessel Design Baseline V1 Execution

**Date:** 2026-08-20
**Disposition:** `incomplete - input_delivery_failed`
**Prime processes:** One
**Provider responses:** Two unintended responses; zero retries

## Result

V1 did not establish the intended GPT-5.6 Sol design-intelligence baseline.
The Prime process exited `0`, but the reference images and design prompt did
not reach the model in their admitted forms.

The launch passed `@<path>` image arguments through Git Bash. The retained
Prime session contains the first two LF-delimited PNG signature fragments as
two separate user text turns:

```text
\u0089PNG
\u001a
```

The intended prompt is absent, and there are no model-visible image blocks.
Sol responded twice by asking for a proper image attachment. No design
hypothesis was attempted, so no claim about Sol's architectural reasoning is
supported.

No retry or second launch occurred.

## Custody That Passed

```text
Prime commit       739400844f8f3f280414b0c7b9c65797208815d3
Prime tree         4d782187c6898aa8352045dd597bab6a3819029c
provider           openai-codex
model              gpt-5.6-sol
reasoning          xhigh
credential type    oauth
API-key argument   absent
API-key env child  absent
tools              disabled
skills             disabled
extensions         disabled
context files      disabled
prompt templates   disabled
Prime exit code    0
wall clock         15.435 seconds
tool events        0
owned processes    0 after verification
```

The retained runtime messages independently identify
`openai-codex/gpt-5.6-sol`. Prime recorded `xhigh`. The model catalog recorded
image support, a 272,000-token context window, and a 128,000-token maximum
output. Both frozen source images matched their admitted hashes before
contact.

Provider-reported usage across the two unintended responses was:

```text
input tokens       1,930
output tokens        177
total tokens       2,107
```

## Input Failure

The failure is localized to the shell launch boundary.

The exact argument list contained the two intended `@<path>` values. Prime's
branch-local argument parser and file processor, invoked directly through
Node without provider contact, accepted those same paths and produced two
`image/png` attachments with the expected byte counts. The live launch routed
through Git Bash instead produced the PNG line fragments as positional text
messages before the intended prompt.

The strongest supported diagnosis is that Git Bash/MSYS consumed the
`@<path>` values as response-file syntax before Prime's argument parser. A
future attempt would need a separately authorized V2 using Prime's bundled
Node entry point directly. This report does not authorize that attempt.

## Capture Observation

Capture custody completed and retained all 90 source rows, but this specimen
did not exercise compact retention successfully:

```text
source bytes                    60,017
retained bytes                  60,017
compacted message updates            0
raw-fallback message updates        73
```

The OpenAI event stream omits the `partial` member required by the current
compact-update grammar, so every cumulative `message_update` used raw
fallback. The intact terminal `message_end` records preserve both responses.

The existing strict terminal reconstruction also returns
`assistant_reconstruction_mismatch`: OpenAI adds `thinkingSignature` and
`textSignature` only to the terminal blocks, while the preceding partial
messages lack those fields. This is an OpenAI-provider capture compatibility
gap. It was observed and preserved; no capture or evaluator change was made.

## Interpretation

This is an experimental-boundary failure, not a Sol design failure. It proves
only that:

- the selected OAuth model route and authority restrictions worked;
- the Bash-mediated native file-argument path did not deliver the images;
- the current compact grammar does not reduce this OpenAI event shape; and
- no Rook, Rhino, Grasshopper, IPython, skill, or subagent activity occurred.

The saved session is not an admissible design baseline and must not be resumed
for implementation.

## Evidence

Evidence root:

```text
C:/UDEV/RookEvidence/2026-08-20-gpt56-sol-vessel-design-baseline-v1
```

Key SHA-256 values:

```text
evidence-manifest.json                    F31801A56EB7FACC3BCA3A0B49292A0067C65F54CACED8BDD7BEBAB7B2BCF4FB
operator/preflight.json                   732BD1780C4B761B2272D340014FD45988A204A4C97F873CA0E2E6CE2886176D
operator/process.json                     02F2F93840AC9A0C517998A23AC6B886ABCE9B90C920493E3E7F3C23FF8D1B60
operator/prime-event-capture-custody.json 88586A174526AEE516022A27D5717A73D52F7AA478A7FE111287B2F37E9F58B3
operator/prime.compact.jsonl              DDA14B9511D1B342D6E9899E9B45EE3052AE11F065760F8E5316B4ED1CB32D9D
operator/terminal-responses.json          BB0CFA1F570A72C00EB5D5F10954B80804732F6BF8BBDCE556D856DE7F7773A1
operator/diagnosis.json                   4AC954CE8553E0436138C1239A75C8D87656E56B819B75A46713BD56BE687498
```
