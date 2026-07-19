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
