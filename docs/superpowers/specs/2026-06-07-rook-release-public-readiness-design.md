# Rook public-release readiness — blocker pass + clean 1.5.10

**Date:** 2026-06-07
**Status:** Approved design (brainstorming complete)
**Goal:** Get `rook-release` ready to share publicly with the McNeel team — a polished
docs site + a working Claude plugin + a fresh **1.5.10** installer — with the public/
private boundary made real, so nothing stale, source-leaking, or unfinished ships.

This design responds to a Codex review (verdict: NO-GO until a blocker pass). Each
Codex finding was verified against the files before inclusion here.

---

## 1. Decisions (locked)

- **D1 — Source messaging.** The installer ships the MCP server as readable Python
  (`mcp_server/src/rook/*`) plus Chirp; the C++/C# parts are compiled. We **reframe
  and ship as-is** (no packaging hardening now). Approved language:
  > The public release repository does not publish Rook's source code. The installer
  > includes runtime implementation files required for the local MCP server and
  > Python-based components to run on the user's machine.

  Never say "no source is shipped." Use "the source repository remains private" /
  "the public repo contains docs, plugin metadata, and release assets only."

- **D2 — Installer license screen.** Replace the EULA accept-gate with a short
  **INFO notices page** (no forced agreement). Exact text in §4.2.

- **D3 — Docs polish for the McNeel send.** Tighten now; screenshots/examples are a
  fast-follow. Remove every `Placeholder` banner, hide the empty Showcase/Gallery
  from the sidebar, keep RookSplat clearly "coming soon," and make every shipped
  page a concise "what it does / what to try / requirements" page.

---

## 2. Architecture — one source of truth per surface (the "tidy")

Root cause of the blockers: docs/plugin existed in two places and drifted. Fix the
boundary so it can't recur.

| Surface | Sole home |
|---|---|
| Website docs (`site/`) | **`rook-release` only** |
| Public (curated, user-only) plugin: `.claude-plugin/`, `.claude/skills/`, `hooks/` | **`rook-release`** |
| Installer-bundled docs (`installer/CLAUDE.md`, `AGENTS.md`, `QUICK_START.md`, `AGENT_SETUP.md`) | **private `Rook`** |
| Source, build tooling, full dev skill set, installer (`.iss`) | **private `Rook`** |
| Release assets (installer `.exe`, FFmpeg bundle, manifests) | built in private `Rook`, **mirrored** to `rook-release` |

Verified: neither `RookSetup.iss` nor the `build-release` skill references `site/`,
so removing the website from the private repo is safe.

---

## 3. Changes — `rook-release` (public docs + plugin)

- **B1 — Plugin manifest paths.** `.claude-plugin/plugin.json` currently uses
  `"skills": "../.claude/skills/"` and `"hooks": "../hooks/hooks.json"` (lines 11-12),
  which fail validation (`Path contains ".."`). Change to plugin-root-relative
  `"./.claude/skills/"` and `"./hooks/hooks.json"`.
- **B2 — Docs vs. shipped reality.** `plugin/overview.md` and `plugin/skills.md`
  claim 15 skills + subagents + maintainer skills. Correct to **11 user-facing
  skills**; remove all subagent claims; remove the maintainer-skill section
  (`/build-release`, `/test`, `/validate-security`, `/consolidate`).
- **B5 — Install page.** `start/install.mdx` — remove the placeholder banner; write
  exact steps: Rhino 8 / Windows / Python 3.10+ / clients (Claude Code, Codex,
  MCP-capable). Source the specifics from the (cleaned) `AGENT_SETUP.md`.
- **D3 — Polish.** Remove `:::caution[Placeholder]` banners from `modules/grasshopper.md`,
  `modules/chirp.md`, `modules/rookbim.md`. Remove **Showcase/Gallery** from the
  sidebar (keep the file as a draft). Keep RookSplat's "coming soon" note. Ensure
  each shipped page reads as a real, concise capability page.
- **D1 — Messaging.** Update `README.md` and `deeper/under-the-hood.md` to the D1
  language. Scan the whole site for any "no source" phrasing and remove it.
- **S2 — Tool count.** Unify to **"nearly 400 MCP tools"** (verified ~396 active:
  403 `Tool(...)` entries minus 7 deprecated interactive tools filtered). Use
  `250+` only where explicitly scoped to Rhino geometry (`modules/rhino-geometry.md`).
  Update `astro.config.mjs` description and `README.md`.
- **S1 — Version.** Bump `plugin.json` + `marketplace.json` to **1.5.10** (after the
  build), matching the mirrored release.

**Validation (rook-release):** run `claude plugin validate` against the **actual
`plugin.json`** (the marketplace manifest passed while `plugin.json` failed — both
must be validated). Then `npm run build` must be green.

---

## 4. Changes — private `Rook` (installer + bundled docs)

### 4.1 Installer URLs (S3)
`RookSetup.iss`:
- `MyAppURL` (line 18) `https://github.com/bringfire/Rook` → `.../rook-release`.
- Stale **`bringfire/Rhino_AI`** registry `WebSite` / `UpdateURL` (lines 185-186,
  207-208, and the verification array 476-478) → `.../rook-release`.

### 4.2 Installer license screen (D2)
`RookSetup.iss`:
- Remove `LicenseFile={#RepoRoot}\LICENSE` (line 59) and the line copying `LICENSE`
  to `{app}` (line 155).
- Add `InfoBeforeFile={#RepoRoot}\installer\NOTICES.txt`.
- Create `installer/NOTICES.txt`:
  ```text
  © 2026 Bringfire Games, LLC. All rights reserved.

  Rook is provided as a free public release. The Rook source repository remains
  private. This installer includes runtime implementation files required for the
  local MCP server and related Python-based components.

  Rook includes third-party open-source components, including FFmpeg, which are
  provided under their own licenses and notices.

  Rook is local-first and bring-your-own-key. See the Privacy Policy for details:
  https://github.com/bringfire/rook-release/blob/main/PRIVACY.md
  ```
- The FFmpeg LGPL `LICENSE.FFmpeg.txt` copy (line 117) stays — LGPL compliance.

### 4.3 Installer-bundled docs (B3/B4 + refinement #2)
- `QUICK_START.md`, `AGENT_SETUP.md`: remove the source-bootstrap / `git clone
  bringfire/Rook` / "Option B: Source" framing; present the public story (download
  the installer, connect your assistant). Point repo URLs at `rook-release`.
- `BUILDING.md` (installer-copied at line 154): **stop copying it** from the
  installer — it is a from-source dev guide irrelevant to an installed user. Public
  troubleshooting/support is already covered by `docs/TROUBLESHOOTING.md` (copied to
  `{localappdata}\Rook\docs`) and the docs-site Troubleshooting page.
- Confirm the already-made `installer/CLAUDE.md`, `installer/AGENTS.md` edits
  (tool-path rebalance, open-source removal, EULA wording) are committed to `main`
  so the 1.5.10 build bundles them.

### 4.4 EULA / LICENSE in the private repo
Out of scope to change the private `LICENSE` file itself (monetization undecided;
prior decision was "site only"). It simply stops being **shipped** by the installer
(§4.2). The private repo retains the EULA as an internal draft.

---

## 5. PR #230 cleanup
Drop `site/` from PR #230 (the website now lives only in `rook-release`). Keep the
installer/`CLAUDE.md`/`AGENTS.md`/legal changes in that PR. Verified safe: nothing
in the build consumes `site/`.

---

## 6. Sequencing (nothing public until the end)

1. Apply all `rook-release` fixes (§3) → `claude plugin validate plugin.json` +
   `npm run build` both green.
2. Apply private-repo fixes (§4) + drop `site/` from PR #230 (§5); merge the doc/
   installer branch to private `main`.
3. Run the **full `build-release 1.5.10`** from private `main` — pipeline unchanged.
4. **Mirror** 1.5.10 installer + FFmpeg source bundle + manifests → `rook-release`
   release; bump `rook-release` `plugin.json`/`marketplace.json` to 1.5.10.
5. Re-validate: plugin install loads the 11 skills + hook; docs build; no broken
   links; installer smoke test from the build passes.
6. Flip `rook-release` public; enable Pages (Actions); deploy.
7. Send McNeel: docs URL (`https://bringfire.github.io/rook-release/`) +
   `https://github.com/bringfire/rook-release/releases/latest`.

The release pipeline stays **unchanged** until 1.5.10 proves clean; mirroring is a
file copy, not a build step.

---

## 7. Validation gates (must pass before §6.6 flip)
- `claude plugin validate` on **`plugin.json`** AND `marketplace.json` — both pass.
- `npm run build` green; spot-check internal links resolve under `/rook-release/`.
- Installer: built 1.5.10 runs the smoke test in `build-release`; the INFO page
  shows (no EULA gate); no `bringfire/Rook` or `Rhino_AI` URLs remain in the `.iss`.
- Grep the public repo for: `bringfire/Rook` (bare), `Rhino_AI`, "open source",
  "no source", "Placeholder", `1.5.9`, `1.4.5` — all clean.

---

## 8. Out of scope / fast-follow (after the McNeel send)
- Screenshots, example `.gh`/`.3dm` files, populated Showcase/Gallery.
- Python packaging hardening (bytecode/obfuscation) for a broad public launch.
- CI: `claude plugin validate` + `npm run build` on PRs to `rook-release`.
- Automating the release mirror (separate publish step *after* private release
  validation — never entangled with the build).

## 9. Risks
- **Drift recurrence** — mitigated by the §2 single-source-of-truth split.
- **Installer build breakage** — mitigated by keeping the pipeline unchanged; the
  `.iss` edits are content-only (URLs, license screen) and the `build-release` step
  that verifies `.iss` source paths must be re-run after removing the `LICENSE`/
  `BUILDING.md` copy lines.
- **Plugin install fails for users** — mitigated by validating `plugin.json`
  directly and a real install test before the public flip.
