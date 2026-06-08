# Rook public-release readiness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a clean, non-stale public `rook-release` (docs site + working Claude plugin + a fresh 1.5.10 installer) to the McNeel team, with the public/private boundary made real.

**Architecture:** Two repos. Public `bringfire/rook-release` (`C:\UDEV\rook-release`) holds the website + curated plugin + release assets only. Private `bringfire/Rook` (`C:\UDEV\Rook`) holds source, the installer build (`RookSetup.iss`), full dev skills, and the installer-bundled docs. The release pipeline is unchanged; the installer is built privately and its finished assets are **mirrored** (copied) to `rook-release`.

**Tech Stack:** Astro + Starlight (docs), Claude Code plugin (`.claude-plugin`/skills/hooks), Inno Setup (`RookSetup.iss`), `gh` CLI (releases/visibility/Pages), `claude plugin validate`.

**Spec:** `docs/superpowers/specs/2026-06-07-rook-release-public-readiness-design.md`

**Two working directories:**
- Public: `C:\UDEV\rook-release` (git remote `origin` = `bringfire/rook-release`)
- Private: `C:\UDEV\Rook` (git remote `origin` = `bringfire/Rook`, branch `docs/public-release-site-and-eula`)

---

## Phase A — `rook-release` public repo (docs + plugin)

> All Phase A work is in `C:\UDEV\rook-release`.

### Task A1: Fix plugin manifest paths + validate

**Files:**
- Modify: `C:\UDEV\rook-release\.claude-plugin\plugin.json:11-12`

- [ ] **Step 1: Change the `..` paths to plugin-root-relative `./` paths**

In `plugin.json`, change:
```json
  "skills": "../.claude/skills/",
  "hooks": "../hooks/hooks.json"
```
to:
```json
  "skills": "./.claude/skills/",
  "hooks": "./hooks/hooks.json"
```

- [ ] **Step 2: Validate BOTH manifests (plugin.json must be validated directly)**

Run:
```bash
claude plugin validate C:\UDEV\rook-release\.claude-plugin\plugin.json
claude plugin validate C:\UDEV\rook-release\.claude-plugin\marketplace.json
```
Expected: both report valid (no `Path contains ".."`, no invalid `skills`/`hooks`).
If `claude plugin validate` is unavailable in the environment, note it and fall back to a manual check that no path in either manifest contains `..` and that `./.claude/skills/` and `./hooks/hooks.json` exist relative to the repo root.

- [ ] **Step 3: Commit**

```bash
cd /c/UDEV/rook-release && git add .claude-plugin/plugin.json && git commit -m "fix(plugin): plugin-root-relative skill/hook paths so manifest validates"
```

### Task A2: Correct docs to match shipped reality (11 user skills, no subagents)

**Files:**
- Modify: `C:\UDEV\rook-release\site\src\content\docs\plugin\overview.md`
- Modify: `C:\UDEV\rook-release\site\src\content\docs\plugin\skills.md`

- [ ] **Step 1: Fix `overview.md`**

Open `plugin/overview.md`. In the "What's in the plugin" table:
- Change the Skills row to: `| **Skills** | 11 guided workflows you invoke with \`/\` — see [Skills That Ship](/rook-release/plugin/skills/) |`
- **Delete the Subagents row** entirely (knowledge-auditor / native-reviewer are not shipped publicly).
Search the page for any other "15" or "subagent" mention and remove/correct it.

- [ ] **Step 2: Fix `skills.md`**

Open `plugin/skills.md`:
- Change the intro count from "15" to "**11**".
- **Delete the entire "## Maintenance" section** (the table containing `/build-release`, `/test`, `/validate-security`, `/consolidate`) — these are not shipped in the public plugin.
- Confirm the remaining skill groups list exactly the 11 shipped skills: design-grasshopper, plan-grasshopper, execute-grasshopper, chirp, chirp-cascade, design-road, masterplan-roads, capture-convention, clean-layers, project-setup, twisted-column.

- [ ] **Step 3: Verify against disk**

Run:
```bash
ls /c/UDEV/rook-release/.claude/skills | wc -l   # expect 11
grep -rin "subagent\|knowledge-auditor\|native-reviewer\|/build-release\|/validate-security\|/test\b\|/consolidate" /c/UDEV/rook-release/site/src/content/docs/plugin/ || echo "clean"
```
Expected: `11`, and `clean`.

- [ ] **Step 4: Commit**

```bash
cd /c/UDEV/rook-release && git add site/src/content/docs/plugin/overview.md site/src/content/docs/plugin/skills.md && git commit -m "docs(plugin): correct to 11 user skills; drop subagent + maintainer-skill claims"
```

### Task A3: Real install page (remove placeholder)

**Files:**
- Modify: `C:\UDEV\rook-release\site\src\content\docs\start\install.mdx`

- [ ] **Step 1: Replace the placeholder body with real steps**

Replace the `:::caution[Placeholder]` block and the rest of the body with concrete content. Keep the frontmatter and the `import { Steps }` line. Use this body:

```mdx
Getting set up is a one-time thing. Afterwards, you just talk to your assistant.

## What you'll need

- **Windows** with **Rhino 8**
- An **AI assistant that supports MCP** — **Claude Code** (CLI, desktop, or VS Code
  extension), **Codex**, or another MCP-capable client (Cursor, Windsurf)
- **Python 3.10+** available on your system (the installer uses it to set up the
  local server)
- An account or API key for the AI model you want to use (Claude, GPT, or a local
  model via Ollama / LM Studio)

You don't need to be a programmer, and you don't need to know any Rhino commands.

## Step 1 — Install the plugin

<Steps>

1. Download the latest installer from the
   [Releases](https://github.com/bringfire/rook-release/releases/latest) page.

2. Run it. The installer adds Rook to Rhino and Grasshopper and sets up the local
   MCP server.

3. Start (or restart) Rhino. Rook loads automatically.

</Steps>

## Step 2 — Connect your assistant

Rook talks to your AI assistant through **MCP** — the doorway that lets your
assistant reach into Rhino. You point your assistant at Rook once.

<Steps>

1. Open your assistant's settings and find where it lists **MCP servers**.

2. Add **Rook** (the installer registers it for Claude Code, Claude Desktop, and
   Codex automatically; you mostly just enable it).

3. Tell your assistant which AI model and key to use, if it asks.

</Steps>

See [Claude Code & Desktop](/rook-release/plugin/claude/) and
[Codex & Other Clients](/rook-release/plugin/codex/) for per-client details.

## Step 3 — Verify

Hand your agent the [Set Up & Verify](/rook-release/start/setup-verify/) page — it
checks the connection, the live Rhino bridge, and the skills.

→ Next: [Your First Conversation](/rook-release/start/first-conversation/)
```

- [ ] **Step 2: Verify no placeholder remains**

Run: `grep -in "placeholder" /c/UDEV/rook-release/site/src/content/docs/start/install.mdx || echo "clean"`
Expected: `clean`.

- [ ] **Step 3: Commit**

```bash
cd /c/UDEV/rook-release && git add site/src/content/docs/start/install.mdx && git commit -m "docs(install): real setup steps; remove placeholder"
```

### Task A4: Remove placeholder banners; hide empty Gallery; keep RookSplat coming-soon

**Files:**
- Modify: `C:\UDEV\rook-release\site\src\content\docs\modules\grasshopper.md`
- Modify: `C:\UDEV\rook-release\site\src\content\docs\modules\chirp.md`
- Modify: `C:\UDEV\rook-release\site\src\content\docs\modules\rookbim.md`
- Modify: `C:\UDEV\rook-release\site\astro.config.mjs` (sidebar)

- [ ] **Step 1: Delete the `:::caution[Placeholder]` blocks**

In each of `grasshopper.md`, `chirp.md`, `rookbim.md`, delete the entire
`:::caution[Placeholder] … :::` aside (the lines from `:::caution[Placeholder]`
through its closing `:::`). Leave the surrounding prose intact.

- [ ] **Step 2: Remove the Showcase/Gallery group from the sidebar**

In `astro.config.mjs`, delete the sidebar group:
```js
        {
          label: 'Showcase',
          items: [{ label: 'Gallery', slug: 'showcase/gallery' }],
        },
```
(Leave the `showcase/gallery.mdx` file in place as a draft; it just won't be linked.)

- [ ] **Step 3: Verify**

Run:
```bash
grep -rin "Placeholder" /c/UDEV/rook-release/site/src/content/docs/modules/ || echo "no placeholder banners"
grep -n "Showcase" /c/UDEV/rook-release/site/astro.config.mjs || echo "gallery unlinked"
```
Expected: `no placeholder banners` and `gallery unlinked`.

- [ ] **Step 4: Commit**

```bash
cd /c/UDEV/rook-release && git add site/src/content/docs/modules/grasshopper.md site/src/content/docs/modules/chirp.md site/src/content/docs/modules/rookbim.md site/astro.config.mjs && git commit -m "docs: drop placeholder banners; unlink empty Showcase/Gallery"
```

### Task A5: Source-messaging reframe (D1)

**Files:**
- Modify: `C:\UDEV\rook-release\README.md`
- Modify: `C:\UDEV\rook-release\site\src\content\docs\deeper\under-the-hood.md`

- [ ] **Step 1: Scan for forbidden phrasing**

Run: `grep -rin "no source" /c/UDEV/rook-release/README.md /c/UDEV/rook-release/site/src || echo "none"`
Note every hit; each must be removed/reworded in the next step.

- [ ] **Step 2: Apply the approved D1 language**

Ensure `README.md` and `deeper/under-the-hood.md` describe the boundary as:
> The public release repository does not publish Rook's source code. The installer
> includes runtime implementation files required for the local MCP server and
> Python-based components to run on the user's machine.

Use "the source repository remains private" / "the public repo contains docs,
plugin metadata, and release assets only." Remove any "no source is shipped"
phrasing. (The current `under-the-hood.md` "Questions & support" section is already
close — adjust wording to match; add a one-line note that the installer carries
runtime implementation files.)

- [ ] **Step 3: Verify**

Run: `grep -rin "no source" /c/UDEV/rook-release/README.md /c/UDEV/rook-release/site/src && echo "STILL PRESENT — fix" || echo "clean"`
Expected: `clean`.

- [ ] **Step 4: Commit**

```bash
cd /c/UDEV/rook-release && git add README.md site/src/content/docs/deeper/under-the-hood.md && git commit -m "docs: reframe source messaging (private source repo; installer carries runtime files)"
```

### Task A6: Unify tool-count phrasing (S2)

**Files:**
- Modify: `C:\UDEV\rook-release\site\astro.config.mjs` (description)
- Modify: `C:\UDEV\rook-release\README.md`
- Modify: `C:\UDEV\rook-release\site\src\content\docs\start\what-is-rook.md`

- [ ] **Step 1: Replace count phrases**

Canonical phrase everywhere: **"nearly 400 MCP tools"**. Update:
- `astro.config.mjs` `description:` — change "392 MCP tools" → "nearly 400 MCP tools".
- `README.md` — change "close to 400" → "nearly 400 MCP tools" where it describes the tool count.
- `what-is-rook.md` — change "close to 400 specialized tools" → "nearly 400 specialized tools".
Leave `250+` only where scoped to Rhino geometry (`modules/rhino-geometry.md` — do not change).

- [ ] **Step 2: Verify**

Run: `grep -rin "392\|close to 400" /c/UDEV/rook-release/site /c/UDEV/rook-release/README.md && echo "fix remaining" || echo "unified"`
Expected: `unified`.

- [ ] **Step 3: Commit**

```bash
cd /c/UDEV/rook-release && git add site/astro.config.mjs README.md site/src/content/docs/start/what-is-rook.md && git commit -m "docs: unify tool count to 'nearly 400 MCP tools'"
```

### Task A7: Build + public-repo grep gate; push

**Files:** none (validation)

- [ ] **Step 1: Build the docs**

Run: `cd /c/UDEV/rook-release/site && npm run build`
Expected: "Complete!", no errors.

- [ ] **Step 2: Public-repo cleanliness grep**

Run:
```bash
cd /c/UDEV/rook-release
grep -rIn -e 'bringfire/Rook\b' -e 'Rhino_AI' -e 'open source' -e 'no source' -e 'Placeholder' -e '1\.4\.5' site README.md .claude-plugin | grep -v 'rook-release' | grep -v node_modules || echo "clean"
```
Expected: `clean` (note: `1.5.9` is still expected until Task D1 bumps to 1.5.10; everything else must be clean).

- [ ] **Step 3: Push**

```bash
cd /c/UDEV/rook-release && git push
```

---

## Phase B — private `Rook` installer + bundled docs

> All Phase B work is in `C:\UDEV\Rook` on branch `docs/public-release-site-and-eula`.

### Task B1: Installer URLs → rook-release; kill stale Rhino_AI

**Files:**
- Modify: `C:\UDEV\Rook\installer\RookSetup.iss` (lines 18, 185-186, 207-208, 476-478)

- [ ] **Step 1: Replace URLs**

Run:
```bash
cd /c/UDEV/Rook
sed -i -e 's#https://github.com/bringfire/Rhino_AI#https://github.com/bringfire/rook-release#g' \
       -e 's#https://github.com/bringfire/Rook\b#https://github.com/bringfire/rook-release#g' \
       installer/RookSetup.iss
```

- [ ] **Step 2: Verify no stale URLs remain**

Run: `grep -nE 'bringfire/Rook\b|Rhino_AI' installer/RookSetup.iss && echo "STILL PRESENT" || echo "clean"`
Expected: `clean`.

- [ ] **Step 3: Commit**

```bash
cd /c/UDEV/Rook && git add installer/RookSetup.iss && git commit -m "installer: point all URLs at rook-release; remove stale Rhino_AI"
```

### Task B2: Installer license screen → INFO notices page; drop EULA + BUILDING from payload

**Files:**
- Create: `C:\UDEV\Rook\installer\NOTICES.txt`
- Modify: `C:\UDEV\Rook\installer\RookSetup.iss` (lines 59, 154, 155)

- [ ] **Step 1: Create `installer/NOTICES.txt`**

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

- [ ] **Step 2: Edit `RookSetup.iss`**

- Line 59: replace `LicenseFile={#RepoRoot}\LICENSE` with `InfoBeforeFile={#RepoRoot}\installer\NOTICES.txt`
- Delete line 154: `Source: "{#RepoRoot}\BUILDING.md"; DestDir: "{app}"; Flags: ignoreversion`
- Delete line 155: `Source: "{#RepoRoot}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion`
- Leave the FFmpeg `LICENSE.FFmpeg.txt` copy (line 117) untouched (LGPL compliance).

- [ ] **Step 3: Verify**

Run:
```bash
cd /c/UDEV/Rook
grep -n "InfoBeforeFile" installer/RookSetup.iss     # expect 1 hit -> NOTICES.txt
grep -nE 'LicenseFile|RepoRoot}\\LICENSE|BUILDING\.md' installer/RookSetup.iss || echo "EULA+BUILDING removed from payload"
```
Expected: `InfoBeforeFile` present; `EULA+BUILDING removed from payload`.

- [ ] **Step 4: Commit**

```bash
cd /c/UDEV/Rook && git add installer/NOTICES.txt installer/RookSetup.iss && git commit -m "installer: INFO notices page instead of EULA gate; stop shipping LICENSE + BUILDING.md"
```

### Task B3: Sanitize installer-copied docs (exclude BUILDING.md — no longer shipped)

**Files:**
- Modify: `C:\UDEV\Rook\QUICK_START.md`
- Modify: `C:\UDEV\Rook\AGENT_SETUP.md`
- Modify: `C:\UDEV\Rook\installer\CLAUDE.md`
- Modify: `C:\UDEV\Rook\installer\AGENTS.md`
- Modify: `C:\UDEV\Rook\docs\TROUBLESHOOTING.md`

- [ ] **Step 1: Repoint URLs in the shipped docs**

Run:
```bash
cd /c/UDEV/Rook
sed -i 's#github.com/bringfire/Rook#github.com/bringfire/rook-release#g' \
  QUICK_START.md AGENT_SETUP.md installer/CLAUDE.md installer/AGENTS.md docs/TROUBLESHOOTING.md
```

- [ ] **Step 2: Remove source-bootstrap framing from QUICK_START.md and AGENT_SETUP.md**

Manually edit `QUICK_START.md` and `AGENT_SETUP.md`: remove the "Source Bootstrap" /
"Option B: Source" / `git clone` install paths and any "build from source" steps.
Keep only the **release-installer** path (download the `.exe`, run it, connect your
assistant). These docs ship to people who installed via the `.exe`; a source-clone
story is wrong for them.

- [ ] **Step 3: Grep gate over installer-copied docs (BUILDING.md excluded — dropped from payload)**

Run:
```bash
cd /c/UDEV/Rook
grep -nEi 'bringfire/Rook\b|Rhino_AI|git clone|source bootstrap|option b: source' \
  QUICK_START.md AGENT_SETUP.md installer/CLAUDE.md installer/AGENTS.md \
  docs/TROUBLESHOOTING.md docs/ONBOARDING_NEW_CLAUDE.md docs/CURRENT_ARCHITECTURE.md \
  docs/AGENT_ARCHITECTURE.md mcp_server/README.md \
  | grep -v 'rook-release' || echo "all shipped docs clean"
```
Expected: `all shipped docs clean`. (BUILDING.md is intentionally NOT in this set — it is removed from the payload in Task B2.)

- [ ] **Step 4: Commit**

```bash
cd /c/UDEV/Rook && git add QUICK_START.md AGENT_SETUP.md installer/CLAUDE.md installer/AGENTS.md docs/TROUBLESHOOTING.md && git commit -m "docs: sanitize installer-shipped docs (rook-release URLs; drop source-bootstrap story)"
```

### Task B4: Verify the .iss still has valid source paths

**Files:** none (validation)

- [ ] **Step 1: Confirm every `Source:` path in the .iss exists**

Run (lists any `Source:` file under `{#RepoRoot}` that is missing — should print nothing):
```bash
cd /c/UDEV/Rook
grep -oE 'Source: "\{#RepoRoot\}\\[^"]+"' installer/RookSetup.iss | sed -E 's/Source: "\{#RepoRoot\}\\//; s/"$//; s#\\#/#g' | while read p; do [ -e "$p" ] || echo "MISSING: $p"; done || true
echo "iss source-path check done"
```
Expected: no `MISSING:` lines (the removed `LICENSE`/`BUILDING.md` lines are gone, so they won't be checked).

---

## Phase C — merge + build 1.5.10

### Task C1: Drop the entire `site/` tree from the private branch

**Files:**
- Delete: `C:\UDEV\Rook\site\` (whole tree, incl. `site/drafts/eula.md`)

- [ ] **Step 1: Remove `site/` from the private repo branch**

Run:
```bash
cd /c/UDEV/Rook && git rm -r site && git commit -m "chore: drop site/ from private repo — website now lives only in rook-release"
```
(The canonical EULA remains as the private root `LICENSE`; the markdown draft under
`site/drafts/` is intentionally not preserved.)

- [ ] **Step 2: Verify**

Run: `ls /c/UDEV/Rook/site 2>/dev/null && echo "STILL PRESENT" || echo "site/ removed"`
Expected: `site/ removed`.

### Task C2: Merge the branch to private `main`

**Files:** none (git)

- [ ] **Step 1: Confirm everything is committed**

Run: `cd /c/UDEV/Rook && git status --short`
Expected: empty (clean tree).

- [ ] **Step 2: Merge PR #230 (or the branch) into `main`**

Either merge PR #230 on GitHub (`gh pr merge 230 --repo bringfire/Rook --merge`) or
fast-forward locally:
```bash
cd /c/UDEV/Rook && git switch main && git merge --no-ff docs/public-release-site-and-eula -m "merge: public-release docs/installer prep" && git push origin main
```
Expected: `main` updated on origin.

### Task C3: Build 1.5.10 via the build-release skill

**Files:** none (invokes `/build-release`)

- [ ] **Step 1: Run the release build from `main`**

Invoke the **`/build-release 1.5.10`** skill (REQUIRED — do not hand-run the
pipeline). It bumps versions (`RookSetup.iss`, `mcp_server/pyproject.toml`,
`.claude-plugin/*` in the private repo), builds the C++/C# plugins, compiles the
installer with ISCC, runs the smoke test, and creates the `v1.5.10` GitHub release
on the **private** repo.

- [ ] **Step 2: Confirm the private release exists with assets**

Run: `gh release view v1.5.10 --repo bringfire/Rook --json assets --jq '.assets[].name'`
Expected: includes `Rook-Setup-1.5.10.exe` and `rook-ffmpeg-*-source-bundle.zip`.

---

## Phase D — mirror + publish

### Task D1: Mirror 1.5.10 assets to rook-release; bump manifests

**Files:**
- Modify: `C:\UDEV\rook-release\.claude-plugin\plugin.json` (version)
- Modify: `C:\UDEV\rook-release\.claude-plugin\marketplace.json` (2 version fields)

- [ ] **Step 1: Bump rook-release manifest versions to 1.5.10**

In `plugin.json` set `"version": "1.5.10"`. In `marketplace.json` set both version
fields (`metadata.version` and `plugins[0].version`) to `1.5.10`.

- [ ] **Step 2: Commit + push the bump**

```bash
cd /c/UDEV/rook-release && git add .claude-plugin/plugin.json .claude-plugin/marketplace.json && git commit -m "chore: bump plugin/marketplace to 1.5.10" && git push
```

- [ ] **Step 3: Mirror the release assets**

```bash
TMP=/c/Users/bring/AppData/Local/Temp/rook-rel-1510
rm -rf "$TMP"; mkdir -p "$TMP"
gh release download v1.5.10 --repo bringfire/Rook --dir "$TMP"
gh release create v1.5.10 "$TMP"/* --repo bringfire/rook-release --title "Rook v1.5.10" \
  --notes "Rook v1.5.10 — Windows installer for Rhino 8 + Grasshopper.

Getting started: https://bringfire.github.io/rook-release/

- Rook-Setup-1.5.10.exe — the installer
- rook-ffmpeg-*-source-bundle.zip — corresponding LGPL source for bundled FFmpeg"
```

- [ ] **Step 4: Verify assets on rook-release**

Run: `gh release view v1.5.10 --repo bringfire/rook-release --json assets --jq '.assets[].name'`
Expected: installer + ffmpeg bundle + manifests present.

### Task D2: Final validation gates (before going public)

**Files:** none (validation)

- [ ] **Step 1: Plugin validates (both manifests)**

Run:
```bash
claude plugin validate C:\UDEV\rook-release\.claude-plugin\plugin.json
claude plugin validate C:\UDEV\rook-release\.claude-plugin\marketplace.json
```
Expected: both valid.

- [ ] **Step 2: Docs build clean**

Run: `cd /c/UDEV/rook-release/site && npm run build`
Expected: "Complete!".

- [ ] **Step 3: Final cleanliness grep (now 1.5.9 must also be gone)**

Run:
```bash
cd /c/UDEV/rook-release
grep -rIn -e 'bringfire/Rook\b' -e 'Rhino_AI' -e 'open source' -e 'no source' -e 'Placeholder' -e '1\.4\.5' -e '1\.5\.9' site README.md .claude-plugin | grep -v 'rook-release' | grep -v node_modules || echo "clean"
```
Expected: `clean`.

- [ ] **Step 4: Plugin install smoke (manual)**

In a scratch Claude Code session: `/plugin marketplace add bringfire/rook-release`
then `/plugin install rook@rook`; confirm the 11 skills appear (`/design-grasshopper`
etc.). (This requires the repo to be reachable; if it must be public first, run this
immediately after Task D3 and before sending McNeel.)

### Task D3: Flip public, enable Pages, deploy

**Files:** none (gh)

- [ ] **Step 1: Make the repo public**

Run: `gh repo edit bringfire/rook-release --visibility public --accept-visibility-change-consequences`

- [ ] **Step 2: Enable Pages (Actions builder) and re-enable the push trigger**

In `C:\UDEV\rook-release\.github\workflows\deploy.yml`, uncomment the `push:`/
`branches: [main]` trigger; commit + push. Then:
```bash
gh api -X POST repos/bringfire/rook-release/pages -f build_type=workflow
gh workflow run "Deploy docs to GitHub Pages" --repo bringfire/rook-release
```

- [ ] **Step 3: Verify the live site + release**

Run: `gh run list --repo bringfire/rook-release --workflow "Deploy docs to GitHub Pages" --limit 1`
Then open `https://bringfire.github.io/rook-release/` (expect 200, not 404) and
`https://github.com/bringfire/rook-release/releases/latest` (expect v1.5.10).

### Task D4: Hand off to McNeel

- [ ] **Step 1: Provide the user the two links to send**

- Docs: `https://bringfire.github.io/rook-release/`
- Download: `https://github.com/bringfire/rook-release/releases/latest`

(The actual email is the user's to send.)

---

## Self-Review notes
- **Spec coverage:** A1↔B1; A2↔B2(docs); A3↔B5; A4↔D3(docs); A5↔D1; A6↔S2; B1↔S3; B2↔D2; B3↔B3/B4/refinement#2; C1↔§5; C2/C3↔sequencing; D1↔mirror; D2↔§7 gates; D3↔flip. RookSplat coming-soon retained (A4 leaves its note). BUILDING.md excluded from the grep set per the user's planning note (B3 Step 3).
- **No placeholders:** NOTICES.txt, install.mdx body, plugin.json change, and all greps are concrete.
- **Consistency:** version `1.5.10` used uniformly in Phase C/D; `1.5.9` allowed only until D1, then must be absent (D2 Step 3).
