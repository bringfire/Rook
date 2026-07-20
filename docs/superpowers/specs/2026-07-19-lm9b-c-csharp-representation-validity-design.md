# LM9B-C C# Representation Validity Design

## Purpose

Preserve the first LM9B-C run unchanged, correct its scientific interpretation,
and run one narrow follow-up that tests the actual Rook RhinoCode C# boundary.

The preserved result is:

```text
semantic lowering demonstrated
representation validity not demonstrated
```

This slice does not reopen LM9A-S, the validation kernel, recipe schemas,
capability vocabularies, or the full conformance campaign.

## Historical Evidence

Run `lm9b-c-20260719T073319Z-bfe46886` remains immutable. Its original
`decision.json`, terminal result, evaluator report, transcript, and raw evidence
are not amended.

A committed human-readable report records the later interpretation. A sorted,
LF-terminated `SHA256SUMS` records every one of the 38 original files using:

```text
sha256:<lowercase digest>  <forward-slash relative path>\n
```

The checksum file is stored outside the original run directory and must hash to
`sha256:39bae8d4ab37c6f941c605ddc010c6641463c184cda6dab90034adc75a68a871`.
The complete raw run is copied unchanged to a durable local evidence archive;
the committed report and checksum manifest do not replace it.

## Exact Mechanical Boundary

Rook already defines the RhinoCode C# wrapper contract in
`mcp_server/src/rook/server.py`. The follow-up adds a narrow reusable validator
for full-source candidates:

```text
public class Script_Instance : GH_ScriptInstance
private void RunScript(<declared parameters>)
```

Rules:

- exactly one `Script_Instance` class inheriting `GH_ScriptInstance`;
- exactly one `private void RunScript` method;
- each input parameter is `object <pin-name>`;
- each output parameter is `ref object <pin-name>`;
- parameter names and order exactly match the declared input pins followed by
  the declared output pins;
- `out` output parameters and `GH_Component` subclasses are rejected;
- the candidate pin declarations remain exact, including name, type, access,
  and order.

This is a contract recognizer for one known Rook boundary, not a general C#
parser or proof of language correctness. Actual compilation remains the
language truth.

The existing broad `preflight_csharp_script` behavior remains compatible for
normal product body and full-source handling. The exact check is an additional
gate used by this probe.

## Trace Catalog

The compiler request includes an exact legal trace-reference catalog derived
mechanically from the unchanged R01 recipe. It exposes only stable reference
identities grouped by their allowed trace roles. It contains no source code,
topology, expected solution, task-specific example, or evaluator rubric.

The deterministic trace checker and the rendered catalog consume the same
derived index. The model no longer has to infer identifier syntax.

## Decision Flow

```text
one bounded compiler session
-> terminal schema and trace checks
-> exact RhinoCode representation-contract check
-> independent evaluator only when all deterministic checks pass
-> conservative observation classification
```

Evaluator acceptance cannot override a mechanical representation failure.
The historical broad preflight result is retained only as evidence about the
first run; it is not sufficient for follow-up success.

## Follow-Up Attempt

Run exactly once with:

- unchanged R01 and authority artifacts;
- the same compiler and evaluator model family;
- the same turn, token, cost, timeout, and deadline bounds;
- corrected generic implementation context;
- a new commit-bound attempt identity;
- no retry, repair, mutation, retrieval, or execution.

The previous candidate source is a negative test fixture only. It is never
supplied to the model or repaired for the new attempt.

## Live Grounding

If and only if the new candidate passes the exact mechanical gate, inject its
unmodified source into one disposable RhinoCode C# component through Rook's
existing Grasshopper path. Verify:

- compilation has no component errors;
- exactly 100 boxes are produced;
- X/Y centers are `-9, -7, ..., 9` with spacing `2`;
- footprints are `1 x 1`;
- boxes extend in positive Z;
- heights equal `1 + 9 * radius / maximum_sampled_radius`;
- corner heights equal `10`;
- heights are nondecreasing with radial distance.

Because the grid is even, the nearest sampled boxes have height `2`; no sampled
box is required to have height `1`.

Any compile or runtime failure is preserved without repair.

## Tests

The preserved first candidate must fail for missing `GH_ScriptInstance`
inheritance and use of `out object`. Tests also cover a conforming generic
source; wrong visibility; missing, extra, reordered, or renamed parameters;
wrong modifiers; `GH_Component`; exact pin binding; evaluator non-override;
and a catalog derived from R01 with no solution, code, topology, or rubric.

## Stop Conditions

Stop and report if actual RhinoCode compilation requires a new platform, R01
semantics must change, expected topology leaks into compiler context, production
code becomes scenario-specific, or this slice starts designing a generalized
IR, backend, or representation selector.
