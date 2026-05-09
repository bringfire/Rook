# Product UX Spec — Prompt Memory + Palette

## Core jobs
1. Recover recent prompts.
2. Reuse frequent prompts quickly.
3. Refine prompts into variants.
4. Understand why suggestions rank high.

## Surfaces
- Vision prompt field
- Chat composer
- Shared prompt palette

## UX model
- Segments: `Recent | Frequent | Pinned | All`
- Type-to-search with blended ranking
- Actions per row: Insert, Insert+Run, Pin/Unpin, Create Variant
- Provenance chips: Human / Agent
- Context chips: Vision / Chat / Project

## Interaction rules
- Selecting a prompt inserts into input by default (no auto-run).
- Deduplicate text internally while preserving display text.
- Always allow pre-run editing.

## Ranking explainability
Show rank reasons, e.g.:
- “Used 8 times this week”
- “Last used in Vision yesterday”
- “Pinned”

## Empty/error states
- Empty: “Your recent prompts will appear here.”
- Error: non-blocking inline retry.

## Privacy & control
- Clear history.
- Session privacy toggle (don’t persist prompts).
- Secret-like text detection warning.
