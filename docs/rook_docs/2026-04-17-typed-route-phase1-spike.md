# Typed Route Phase 1 Empirical Spike

**Date:** 2026-04-17
**Stage:** Plan input
**Purpose:** Ground the Phase 1 typed-route plan in observed Rhino behavior, not intuition.
**Binding basis:** `rook_docs/2026-04-15-typed-route-gap-analysis.md` (`## Decision Record`)

---

## What This Spike Produces

The spike is a **verification and prioritization tool**, not a schema-design
input. Typed-route design is driven by RhinoCommon API docs, existing handler
patterns, and the Decision Record — not by observing Rhino's command UI.

What the spike provides:

1. **Verification** that our current-state model holds — does each Phase 1
   command actually fall back to `/command` today, or does it already run
   cleanly via scripted prefix?
2. **Prioritization evidence** — sequencing for Phase 1 PRs based on which
   operations are genuinely stuck vs. which work-but-ugly.
3. **Escape-hatch candidates** — for operations that stall on picker-driven
   ambiguity (not command-UI artifacts), which qualify for the Decision
   Record's (b) carve-out (narrow interactive survival).

What the spike does **not** provide:

- Route schema design (use RhinoCommon API docs + the Decision Record)
- Response contract definition (already known — the current shape is fixed
  and documented below)
- Architectural rules (already codified in the Decision Record)

The runnable artifact is:

- [typed-route-phase1-spike.ps1](</c:/Users/aryan/source/repos/rook_docs/typed-route-phase1-spike.ps1>)

That script:

- discovers the live `RookNative` HTTP instance
- creates repeatable setup geometry via existing typed routes
- runs the current `/command`-based command strings
- writes a JSON report to:
  `rook_docs/typed-route-phase1-spike-report.json`

This document is the manual capture sheet that sits on top of that JSON report.

---

## Run Procedure

1. Start Rhino 8 with `RookNative` loaded and a blank document open.
2. From the repo root, run:

```powershell
powershell -ExecutionPolicy Bypass -File ..\rook_docs\typed-route-phase1-spike.ps1
```

3. Open:

- `rook_docs/typed-route-phase1-spike-report.json`
- this file

4. Share the generated JSON report plus any runtime observations — unexpected
   dialogs, commands that hung past auto-cancel, geometry that looked wrong,
   any surprises. Claude fills the capture sheet from the JSON + your
   observations.

---

## Conclusion Labels

Use exactly one per command:

- `typed route urgent`
- `typed route useful`
- `command fallback acceptable`

Interpretation:

- `typed route urgent`: command path stalled, was ambiguous, or returned data too weak for reliable chaining
- `typed route useful`: command path ran, but contract quality is still materially worse than a typed route
- `command fallback acceptable`: scripted path ran cleanly and returned enough signal that Phase 1 does not need to prioritize it

---

## Provenance Labels

Each command string in the script carries one of:

- `repo-backed`: sequence is supported by in-repo command-learning examples
- `docs-derived`: sequence is derived from current official Rhino 8 command docs

This matters because a `docs-derived` failure may still be a valid spike result: it tells us the current command fallback is brittle enough that even a docs-aligned scripted attempt is not robust.

Official Rhino 8 docs used for command-step derivation:

- Loft: <https://docs.mcneel.com/rhino/8/help/en-us/commands/loft.htm>
- Sweep1: <https://docs.mcneel.com/rhino/8/help/en-us/commands/sweep1.htm>
- Sweep2: <https://docs.mcneel.com/rhino/8/help/en-us/commands/sweep2.htm>
- Pipe: <https://docs.mcneel.com/rhino/8/help/en-us/commands/pipe.htm>
- Revolve: <https://docs.mcneel.com/rhino/8/help/en-us/commands/revolve.htm>
- Array / ArrayLinear / ArrayPolar: <https://docs.mcneel.com/rhino/8/help/en-us/commands/array.htm>

---

## Reference: `/command` Response Shape (known prior to spike)

This shape is fixed and well-known — the spike doesn't need to verify it. Kept
here as reference for interpreting the JSON report.

Clean execution:

```json
{ "success": true,
  "data": { "command": "...", "executed": true,
            "objectsCreated": 1, "objectIds": ["..."] } }
```

Interactive stall (auto-cancelled):

```json
{ "success": false,
  "data": { "command": "...", "executed": false,
            "error": "Command went interactive...",
            "waitingFor": "...",
            "objectsCreated": 0, "objectIds": [] } }
```

---

## Capture Sheet

Filled 2026-04-17 from `typed-route-phase1-spike-report.json` + runtime observations.

| Command | Outcome | `waitingFor` (if stalled) | Stall class | Conclusion |
|---|---|---|---|---|
| Loft | stalled | HTTP timeout @ 15s (auto-cancel did not fire) | missing-parameter (multi-`_SelId` does not feed Loft's curve selection via `/command`) | `typed route urgent` |
| Sweep1 | stalled | HTTP 400 @ 8ms (auto-cancel → error envelope) | missing-parameter (multi-step `_SelId _Enter _SelId _Enter` form rejected) | `typed route urgent` |
| Sweep2 | ambiguous | — (`executed=true, objectsCreated=0`, silent no-op) | missing-parameter (command accepted syntactically, produced no geometry) | `typed route urgent` |
| Pipe | cleanly | — | — | `typed route useful` |
| Revolve | cleanly | — | — | `typed route useful` |
| ArrayRectangular | stalled | HTTP timeout @ 15s | missing-parameter (`_-Array _Rectangular` form does not run cleanly scripted) | `typed route urgent` |
| ArrayLinear | stalled | HTTP 400 @ 9ms | missing-parameter (`_-ArrayLinear` scripted form rejected; verify command name in Rhino 8) | `typed route urgent` |
| ArrayPolar | cleanly | — | — | `typed route useful` |

Legend:

- **Outcome:** `cleanly` / `stalled` / `ambiguous`
- **Stall class** (only if stalled): `missing-parameter` (scriptable with
  more explicit input) / `human-picker` (genuinely picker-driven ambiguity,
  escape-hatch candidate)
- **Conclusion:** `typed route urgent` / `typed route useful` /
  `command fallback acceptable`

### Pattern observed

Commands that worked have a single `_SelId <guid>` followed by numeric/option
args (Pipe, Revolve, ArrayPolar). Commands that failed require multi-step
selection (Loft's multiple curves, Sweep1's rail+profile across `_Enter`,
Sweep2's 2 rails + section). Under `/command` → `RunScript`, `_SelId`
reliably works as a single one-shot but not as a repeatable token across
command prompts.

### Substrate finding (surfaces a Decision Record implication)

Sweep2 returned `executed=true` with zero objects — a **silent failure**
where the command-string parser accepts the syntax but no geometry forms.
The current fallback path can lie about success. This reinforces Rule 2
(document-dependent validation on the UI thread before mutation) and the
choice to prefer typed routes with explicit pre-validation over
command-string substrates even for operations where the command path
"runs."

Provenance (`repo-backed` vs. `docs-derived`) is preserved per command in
the JSON report; all four failures happened regardless of provenance.

---

## Plan Inputs Insert Template

Paste a condensed version of the spike into the future Phase 1 plan doc under `## Plan Inputs`.

```md
### Empirical interactive-fallback matrix

Source: `rook_docs/2026-04-17-typed-route-phase1-spike.md` (2026-04-17).

| Command | Outcome | Key observation | Conclusion |
|---|---|---|---|
| Loft | stalled | 15s timeout; multi-`_SelId` not supported | `typed route urgent` |
| Sweep1 | stalled | HTTP 400; multi-step selection rejected | `typed route urgent` |
| Sweep2 | ambiguous | silent no-op; `executed=true` with 0 objects | `typed route urgent` |
| Pipe | cleanly | 1 object created | `typed route useful` |
| Revolve | cleanly | 1 object created | `typed route useful` |
| ArrayRectangular | stalled | 15s timeout; `_Rectangular` option form rejected | `typed route urgent` |
| ArrayLinear | stalled | HTTP 400; command form rejected | `typed route urgent` |
| ArrayPolar | cleanly | 5 objects created | `typed route useful` |

**Prioritization:** 5 urgent (Loft, Sweep1, Sweep2, ArrayRectangular, ArrayLinear), 3 useful (Pipe, Revolve, ArrayPolar).
```

---

## Acceptance Gate Before Templating Other Routes

After drafting the worked-example route plan (`Pipe` unless the spike changes that call), ask:

1. Did the worked example expose all fields needed in the per-route execution block?
2. Did any Decision Record rule prove too vague or too strong for a real route?
3. Did substrate reasoning hold up against actual code patterns and spike results?

Only template the remaining Phase 1 routes after those three questions are answered.
