# rook_docs

Architecture notes and design decision records for shipped Rook subsystems.
Each dated memo (`2026-MM-DD-<topic>.md`) is self-contained and names the PR(s)
it applies to; date-first naming keeps `ls` chronological.

## What's here

- **Design records** for shipped systems: the WebUI substrate contract and
  module boundaries, the typed-route gap analysis that drove the typed geometry
  routes, the batch block/layer tool designs, GH script-component routing,
  capability routing, exotic-capability promotion doctrine, the generation
  provider framework, the video NLE bridge and v3 video decisions, the
  vision artifact model, the knowledge-graph visualizer, and the spatial
  intelligence foundation with its OCCT engine decision.
- **`DEVELOPMENT_PRACTICES.md`** — how changes are scoped, reviewed, and
  smoke-tested in this repo. Read it before opening a PR.
- **`occt-build.md`** — how the vendored OCCT subset is built; referenced from
  `THIRD_PARTY_NOTICES.md`.
- **`video-provider-payload-audit.md`** + `fixtures/video-provider-payload-audit/`
  — provider payload contract with sanitized examples; covered by tests.
- **`rookbim-export-spike/`** — live calibration and verification scripts for
  the RookBIM export path; `live_calibrate_containment_fixture.py` is exercised
  by the test suite.
- **`script-reference/`** — only `promoted/` (Rook-adapted scripts) and the
  README are tracked; external script clones are gitignored.

## Editing convention

Treat these docs like code: diff them in the PR they pair with and reference
them by relative path (`docs/rook_docs/<file>.md`) from `CLAUDE.md`, memory
entries, and commit messages. Don't rewrite locked decision records such as
`2026-04-22-v3-video-decisions.md`; append a changelog or supersede with a new
dated doc that links back.

## What's not here

Implementation plans, specs from the design-then-plan workflow, roadmaps,
spikes, and internal strategy notes are kept outside the public tree
(`docs/superpowers/`, `docs/plans/`, and `docs/roadmaps/` are gitignored).
Source docstrings that cite a `docs/superpowers/specs/...` path refer to that
private record.
