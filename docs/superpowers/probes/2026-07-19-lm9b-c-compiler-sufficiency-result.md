# LM9B-C Compiler Sufficiency Result

## Preserved Run

```text
run: lm9b-c-20260719T073319Z-bfe46886
commit: bfe46886
model: gemini/gemini-3.1-pro-preview
compiler turns: 2
historical outcome: bounded_lowering_demonstrated
tokens: 77,055
cost: approximately $0.347
execution: none
```

The original run directory remains unchanged. Its 38 files total 1,120,445
bytes. The complete raw evidence is preserved at:

```text
C:/Users/bring/.rook/probe-archives/lm9b-c-20260719T073319Z-bfe46886/
```

The committed checksum manifest is
`evidence/lm9b-c-20260719T073319Z-bfe46886.SHA256SUMS`. It is sorted by
forward-slash relative path, LF-terminated, and hashes to:

```text
sha256:39bae8d4ab37c6f941c605ddc010c6641463c184cda6dab90034adc75a68a871
```

## Reviewed Interpretation

```text
semantic lowering demonstrated
representation validity not demonstrated
```

R01 carried enough meaning for the compiler model to derive the intended grid,
boxes, spacing, placement, radial profile, height bounds, and verification
obligations without an obvious invented material value. Mechanical trace
feedback changed the trajectory inside the same bounded attempt: turn one
failed on trace/reference encoding, and turn two produced schema-valid and
trace-valid evidence.

The candidate was not mechanically valid for Rook's RhinoCode C# boundary. It
emitted:

```csharp
public class Script_Instance
{
    public void RunScript(out object Boxes)
```

Rook requires a `Script_Instance : GH_ScriptInstance` class with exactly one
`private void RunScript` method and `ref object` output parameters matching the
declared pins. The first probe's preflight intentionally recognized only a broad
full-source shape and did not certify this contract.

The evaluator used a separate invocation of the same model family and accepted
`representation_coherence` despite the mismatch. Its acceptance is useful
semantic-review evidence but cannot certify mechanical representation validity.

## Key Evidence

```text
manifest.json
sha256:df8c0c9b3fa2c8dd396749f3ec8d4e24e6722d7146d226e73841c915679fe41d

compiler/terminal_result.json
sha256:78c1989f52d20089a796fdda560b8f883981b480fe178dc2c5c5c4e1ddfe75b8

deterministic_trace_check.json
sha256:e9fbd64c3647582ac68bb2c26a7b2cca6c19f29d1189d018a4a0ad502ccccdad

evaluator/report.json
sha256:ee970ff9695442c591e31961598b97dc0111bce59ce352091e26fc0eeed6ff7e
```

## What Worked

- Semantic lowering from the frozen recipe and referenced authority artifacts.
- Same-attempt response to deterministic structural feedback.
- Terminal schema validation and material trace validation.
- Isolation from product-agent state, mutation, retrieval, Rhino, and GH tools.
- Complete visible transcript, usage, timing, token, and cost capture.

## Follow-Up Boundary

The next attempt adds the exact Rook RhinoCode source/signature check and an
R01-derived legal trace-reference catalog. Final success requires deterministic
mechanical validity before independent evaluation. If that attempt passes, its
exact unmodified source is tested once through a disposable live Grasshopper
document; no repair occurs inside either attempt.

## Follow-Up Attempt

```text
run: lm9b-c-20260719T081304Z-ac521961
commit: ac521961
model: gemini/gemini-3.1-pro-preview
compiler turns: 1
outcome: bounded_lowering_demonstrated
compiler tokens: 26,750
evaluator tokens: 20,746
total tokens: 47,496
compiler cost: $0.166010
evaluator cost: $0.088012
total cost: $0.254022
```

The follow-up used the same R01 and authority bytes as the first attempt. The
implementation context added the exact RhinoCode contract and the compiler
request added an R01-derived legal trace-reference catalog. No prior candidate
source, expected topology, or evaluator rubric entered the compiler request.

The compiler submitted one candidate on its first turn. Deterministic checks
reported:

```text
terminal schema valid: true
trace valid: true
broad C# preflight: true
exact representation contract: true
representation contract errors: []
actual C# compilation at probe time: not attempted
```

The separate evaluator accepted source fidelity, material authority,
representation coherence, and verification fidelity. Mechanical validity did
not depend on that judgment: the exact product-contract check completed before
the evaluator ran.

The complete 30-file run totals 673,304 bytes and is archived unchanged at:

```text
C:/Users/bring/.rook/probe-archives/lm9b-c-20260719T081304Z-ac521961/
```

Its committed checksum manifest is
`evidence/lm9b-c-20260719T081304Z-ac521961.SHA256SUMS` and hashes to:

```text
sha256:278db343b41ef6011440aa84aff044935a61133643020bac4db29f43d5e84aa1
```

Key evidence:

```text
manifest.json
sha256:31f4051d513aacc44aa9b70cf1cc6c0ebd41cde5a7c603aab5111cac8393a992

compiler/terminal_result.json
sha256:22884b37948e5a8256dcef255a7958d0d710f3d3550d1d7cd0c86d1bff2573c7

deterministic_trace_check.json
sha256:9af0e85bef4522752ba41118fe0cd0313d03e67da86b10d9e3119184f259243c

evaluator/report.json
sha256:cfc135b1714cc3a60fa662b4ac88322280b6b11e83edc22097f52e652ab53f1c
```

## Post-Run Gate Review

Adversarial review after the attempt found that the `ac521961` recognizer could
mistake contract-shaped text in comments, literals, conditional compilation, or
another class for the live `Script_Instance` envelope. It also found that the
standalone outcome classifier did not independently require terminal schema and
trace validity, although the session controller enforced those conditions in
the observed run.

Commit `ea3b3453` closes both bypasses. It masks non-code text, binds the method
to the direct top-level `Script_Instance` class, rejects conditional-compilation
ambiguity, and makes classification require schema and trace validity. It also
replaces the simplified negative fixture with the exact archived 1,661-byte
first candidate:

```text
sha256:313e1fff5db8c28dd96ea5a7b21ece3c3ffb6cf8eee14973f6dbd0e1f2a221da
```

The exact follow-up candidate was rechecked against the corrected recognizer
and remained valid with no error codes. Neither the model attempt nor the live
smoke was rerun. The raw `ac521961` evidence remains unchanged and continues to
identify the code that actually performed the attempt.

## Live Grounding

The mechanically conforming candidate was inserted once, unmodified, into one
fresh disposable Grasshopper document through `gh_create_csharp_script`. The
live source readback exactly matched the 1,679-byte terminal candidate:

```text
sha256:fd654a4679714997b37373edf5be1aeffc41ac588f52759fe1e4b1a0eeaf374e
```

RhinoCode compiled and solved it with zero component errors and zero warnings.
The output was one list of 100 `Rhino.Geometry.Box` values. A disposable bake
materialized all 100 with no skips. Read-only bounding-box inspection proved:

- X and Y centers are exactly `-9, -7, -5, -3, -1, 1, 3, 5, 7, 9`.
- Every footprint is `1 x 1`, every base is at `Z = 0`, and every height is
  positive.
- The nearest sampled radius is `sqrt(2)` and its four boxes have height `2`.
- The four corner boxes have height `10`.
- Height is nondecreasing with radial distance.
- The maximum post-bake bounding-box deviation from
  `1 + 9 * radius / maximum_sampled_radius` is `4.699113755890494e-7`.

The live attempt used no candidate repair or rerun. The exact curated
observation is
`evidence/lm9b-c-20260719T081304Z-ac521961-live-smoke.json`:

```text
sha256:de7aaa161ba5ab458a2e5ac4593997fc5912bf52ac5231c541765239b198ebff
```

The record freezes the exact declared pins and the complete 10-by-10 baked
height matrix used for the geometric checks. Raw MCP tool-call transcripts were
not captured as files, so this record does not claim to be an authenticated raw
transcript.

## Result

The follow-up demonstrates that the unchanged R01 contract supported one
bounded, authority-traced lowering into an inert C# candidate that both passed
Rook's exact RhinoCode signature boundary and compiled through the actual live
Rook/RhinoCode path. The resulting geometry satisfied all four compiler-authored
verification obligations in this scenario.

This remains one controlled compiler attempt and one disposable live arrival.
It does not establish Planner authorship, general compiler reliability, or
authorization for product execution.
