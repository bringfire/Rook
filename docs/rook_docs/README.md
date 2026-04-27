# rook_docs

Rook's architecture notes, design memos, scope passes, post-mortems, and
shareable framing docs. Formerly a sibling repo at `~/source/repos/rook_docs`;
imported into the Rook tree on 2026-04-26 so docs diff alongside the code
they describe.

## What's here

- **Date-prefixed design docs** (`2026-MM-DD-<topic>.md`) — per-topic memos
  written before, during, or after a PR cycle. Each is self-contained and
  references the PR(s) it applies to. The naming convention is firm:
  date-first lets `ls` sort chronologically.
- **`work-queue.md`** — the rolling triage list. Updated after each ship.
- **`POSITIONING.md`** — collaborator-facing version of the positioning
  thesis. Kept aligned with the `project_positioning_thesis.md` memory entry.
- **`script-reference/`** — see the README inside; only `promoted/` (our
  adapted scripts) and the README itself are tracked. The 9 external clones
  (`rhino-developer-samples`, `rhinoscriptsyntax`, etc.) live under
  `.gitignore`.
- **`1284_74915_en.pdf`** — Tencent agent paper, kept as a small reference.
  The extracted-text directory `tencent_api_md/` is gitignored.
- **`typed-route-phase1-spike.*`** — the empirical spike artifacts that
  fed the Phase 1 typed-route gap analysis.

## Editing convention

Treat these docs like code: scope-pass them before a substantive rewrite,
diff them in the PR they're paired with, and reference them by relative
path (`docs/rook_docs/<file>.md`) from CLAUDE.md, memory entries, and
commit messages. Don't rewrite locked docs (e.g. `2026-04-22-v3-video-
decisions.md` v3.1 contract) — append a Changelog or supersede with a
new dated doc that links back.

## What's NOT here

Plans/post-mortems that touch private knowledge stores or Engram-internal
work live under `docs/plans/` and `docs/engram-reference/` (gitignored —
they describe ongoing experiments with private data shapes). These rook_docs
are the publicly-shareable architecture surface.
