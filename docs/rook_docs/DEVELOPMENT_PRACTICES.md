# Rook Development Practices

**Derived from:** Rook v1.4.5 public release audit session (April 2026)
**Audience:** Future maintainers of `bringfire/Rook` (including future-self, collaborators, and eventual outside contributors)
**Purpose:** Canonical reference for ongoing public-repo development after the initial public launch. Captures the workflow, discipline, and specific practices that emerged from the three-round audit + cleanup that produced the first public commit.

This document is intentionally long. It's meant to be read once end-to-end, then used as a lookup reference. The table of contents below is structured so you can jump to specific sections when you need to recall a specific practice.

---

## Table of contents

1. [Mental model: the four eras of Rook development](#mental-model)
2. [The three key shifts at public flip](#three-key-shifts)
3. [Git workflow — branch-and-PR discipline](#git-workflow)
4. [Commit hygiene and commit messages](#commit-hygiene)
5. [Never force-push main](#no-force-push)
6. [Branch protection rules](#branch-protection)
7. [CI/CD setup](#ci-cd)
8. [Secret management](#secret-management)
9. [Dependency updates](#dependency-updates)
10. [Release management — semver, CHANGELOG, release flow](#release-management)
11. [The `release.yml` workflow disposition](#release-yml-disposition)
12. [Documentation discipline](#documentation-discipline)
13. [Knowledge store evolution](#knowledge-store)
14. [Issue triage](#issue-triage)
15. [The Claude + Codex review pattern](#claude-codex)
16. [Local directory rename (post-launch housekeeping)](#directory-rename)
17. [Preserving audit artifacts](#audit-artifacts)
18. [Soak period checklist](#soak-checklist)
19. [First week after public launch checklist](#first-week)
20. [Your first N public commits](#first-commits)
21. [Summary — the one-page answer](#summary)
22. [Meta-principle](#meta-principle)

---

## 1. Mental model: the four eras of Rook development <a id="mental-model"></a>

Before concrete practices, it helps to name the eras you've moved through and the one you're entering:

| Era | Period | Git discipline | Risk profile |
|---|---|---|---|
| **Pre-audit private** | Dec 2025 – Apr 2026 | Whatever worked; force-push freely; messy commit messages OK | Only you saw it |
| **Audit cleanup** | April 2026 | Single-concern amends, force-push safe because single-owner | Only you saw it |
| **Soak** | Between force-push and public flip | No force-push needed; repo frozen | Only you see it |
| **Public (pre-contributor)** | 0 to N users after flip | New commits welcome; force-push strongly discouraged; commit messages written for strangers | Strangers can see it |
| **Public (contributor)** | N users + active contributors | Full PR workflow, code review, CI gates, issue triage, release cadence | Strangers depend on it |

The practices in this document are for the **public (pre-contributor)** era — the first several weeks or months after launch. The jump to **public (contributor)** happens when you start accepting PRs or have people waiting for features. At that point you add more discipline (formal release process, deprecation notices, etc.) that isn't covered here.

---

## 2. The three key shifts at public flip <a id="three-key-shifts"></a>

### Shift 1: Your commit history becomes part of the product

In the private era, a messy `git log` was a dev artifact — nobody read it except you. In the public era, it's visible to anyone who visits `github.com/bringfire/Rook/commits`, it's searchable by GitHub code search, it appears in `git blame` when users investigate bugs, and it becomes the canonical audit trail for "why does this line of code exist." **Every commit is now a message to future readers you don't know yet.**

### Shift 2: Force-pushing becomes hazardous

During the audit, force-push was safe because only you had a clone of `bringfire/Rook`. After launch, anyone who stars, forks, or clones the repo has their own copy that references specific commit SHAs. If you force-push over a commit they've already pulled, you invalidate their git state and they have to do unnatural recovery operations. **As soon as you have any outside consumer, force-pushing to `main` becomes strongly discouraged.**

### Shift 3: Security scanning runs continuously

GitHub's secret scanning, CodeQL, and Dependabot will look at every commit you push. If you accidentally commit a secret, you get an email within minutes. If CodeQL finds a vulnerability, you get an alert. If a dependency has a CVE, Dependabot opens a PR. This creates a feedback loop that makes some kinds of mistakes self-correcting, but it also means **you need to be prepared to respond to these signals — ignoring them is a bad look on a public repo.**

---

## 3. Git workflow — branch-and-PR discipline <a id="git-workflow"></a>

### Stop developing directly on `main`

During the audit session, `main` was the only working branch because the staging repo was a one-shot clean snapshot. For ongoing development, this changes.

**Going forward:**
- `main` is the "known-good public branch" — always shippable, always matches what users see
- All actual work happens on topic branches: `feature/chirp-improvements`, `fix/crash-on-unload`, `docs/contributor-guide`, etc.
- Topic branches merge into `main` via pull request (even if you're solo)
- Never `git commit` directly on `main`. If you catch yourself typing that, stop and create a branch first.

### The workflow in concrete steps

```powershell
cd <repo>   # (or Rook-public-staging until renamed)

# Start a feature branch for whatever you're working on
git checkout -b feat/new-mcp-tool-rhino-annotations
# ...make changes, commit...
git add .
git commit -m "feat(mcp): add rhino_annotation_* tools for Dot, TextDot, Leader"
git push -u origin feat/new-mcp-tool-rhino-annotations
```

Then on GitHub, open a PR from your feature branch to `main`, review your own diff in the PR view, and merge.

### Why PRs matter even when you're solo

- **You review your own work with different eyes.** The GitHub PR view is designed for code review — side-by-side diffs, inline comments, easy navigation. Looking at your own diff through that UI catches things you'd miss in a terminal.
- **CI runs before merge.** Once you have CodeQL and other checks enabled, they run on every PR, so you find out about problems before the change lands on `main`.
- **Atomic history.** Each PR merge is a clear "this change happened" boundary, which makes `git bisect` and `git blame` much more useful than a stream of direct-to-main commits.
- **Rollback primitive.** If a PR turns out to be bad, `git revert` on the merge commit is a clean, non-destructive rollback.
- **Muscle memory** for when contributors show up and you *have* to use PRs because they can't push directly.

**Exception:** tiny fixes that are unambiguous (a typo in a comment, a broken link in a doc) can still go direct to main. But the threshold for "direct to main" should be higher than it was during private development.

---

## 4. Commit hygiene and commit messages <a id="commit-hygiene"></a>

### One logical change per commit

- `feat: add gh_export_to_usd tool` is a good commit
- `feat: add gh_export_to_usd tool + fix chirp race condition + update readme` is bad
- The test for "one logical change": can you describe this commit in one sentence without using "and" or "also"?

### Conventional Commits format

Use this structured format:

```
<type>(<scope>): <short summary in imperative mood, <72 chars>

<body: why this change exists, what problem it solves, any context a
future reader would need. Wrap at 72 chars. Can be several paragraphs.>

<optional: Fixes #123, Closes #456, Refs #789>
```

Where `<type>` is one of:

| Type | Use for |
|---|---|
| `feat` | New features |
| `fix` | Bug fixes |
| `docs` | Documentation changes only |
| `refactor` | Code restructuring without behavior change |
| `perf` | Performance improvements |
| `chore` | Maintenance tasks (deps, config, tooling) |
| `test` | Test additions or changes |
| `build` | Build system or dependency changes |
| `ci` | CI/CD pipeline changes |
| `revert` | Reverting a previous commit |

This is the [Conventional Commits](https://www.conventionalcommits.org/) convention. It enables tools like `git-cliff` or `release-please` to auto-generate changelogs from git history.

### The "why" matters more than the "what"

Your diff already shows what changed. Your commit message should explain *why*. The best commit messages answer:

1. Why is this change needed? (the problem, not the solution)
2. Why this particular solution and not alternatives?
3. What side-effects or caveats does the reader need to know about?

### Example bad commit message (private era)

```
fix: update post_install.py
```

### Example good commit message (public era)

```
fix(installer): flatten skill install targets to ~/.claude/skills/<skill>

Claude Code's user-skills loader scans ~/.claude/skills/<skill>/SKILL.md
one level deep. The previous installer nested skills under an extra
rook/ namespace directory which made them undiscoverable.

Applied the same flattening to ~/.agents/skills/ for Codex CLI
compatibility. Fix also applied to install.ps1, install.sh, and
mcp_server/src/rook/doctor.py for consistency.

Validated on a fresh Windows user account: all 13 Rook skills now
appear in Claude Code's skill autocomplete.
```

The good version tells a stranger everything they need to understand the change. Six months from now when you're debugging a similar issue, this is the commit message you'll thank yourself for.

### Pragmatic note

Don't let perfect be the enemy of good. If you're making a genuinely trivial change, a one-line commit is fine. The structured format is for changes that future readers will want to understand.

---

## 5. Never force-push main <a id="no-force-push"></a>

This is the biggest behavioral change from the audit era. In the audit, `git push --force-with-lease origin main` ran multiple times because there was only one consumer (this dev machine). After public flip, **assume there are people with clones you don't know about** — stargazers, potential contributors, downstream projects pinned to specific commits.

If you force-push over their commits, their next `git fetch` shows their local `main` has "diverged" from `origin/main`, and they have to do recovery dances. For a popular project this is a significant trust hit.

### What NOT to do after public flip

- ❌ `git push --force origin main`
- ❌ `git push --force-with-lease origin main`
- ❌ `git commit --amend` on a commit that's already been pushed to `main`
- ❌ `git reset --hard <old-sha>` + push on `main`
- ❌ `git rebase main` + push on `main`

### What to do instead

When you need to "undo" a bad commit on `main`, use `git revert`:

```powershell
# Revert creates a NEW commit that undoes the bad commit
# — this is a non-destructive forward operation, not a history rewrite
git revert <bad-commit-sha>
git push origin main
```

This is the fundamental difference between **history rewriting** (force-push, amend, reset) and **forward revert** (`git revert` creates a new commit). For public branches, only forward revert is safe.

### Feature branches are different

Force-pushing to feature branches (before you merge the PR) is still fine. You can amend, rebase, squash, whatever you want, as long as the feature branch only has your work on it. The moment it lands on `main` via merge/squash-merge, that history becomes immutable.

---

## 6. Branch protection rules <a id="branch-protection"></a>

In GitHub Settings → Branches → Branch protection rules, add a rule for `main` with:

- ✅ **Require a pull request before merging** — forces you through the PR workflow
- ✅ **Require status checks to pass before merging** — set this up once CI is running; prevents merging PRs with failing checks
- ✅ **Require linear history** — prevents merge commits from cluttering history; forces squash-merge or rebase-merge
- ✅ **Require conversation resolution before merging** — PR comments must be resolved before merge
- ✅ **Restrict who can push to matching branches** → just you (or no one, if strictly enforcing PR path)
- ❌ **Allow force pushes** — leave OFF
- ❌ **Allow deletions** — leave OFF

### The "Allow bypassing" toggle

This is the escape hatch to think carefully about:

- **Bypass ON**: you can force-push or commit directly as admin when truly needed (e.g., real emergency fix). Every bypass is logged.
- **Bypass OFF**: even you cannot force-push or commit directly — you have to use the PR flow always. Maximum discipline.

**Recommendation:** Turn it **ON** for the first few months. You're still the only committer, and occasional bypass saves you from learning the hard way that you really need emergency push capability. Once contributors show up, tighten the screws.

---

## 7. CI/CD setup <a id="ci-cd"></a>

You already have `.github/workflows/release.yml` — which is for releases, not validation (and is currently broken). You need a separate workflow for **validation** that runs on every PR.

### Minimal validation workflow (`.github/workflows/ci.yml`)

```yaml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  python-tests:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install mcp_server
        run: |
          cd mcp_server
          pip install -e .
      - name: Run non-Rhino pytest
        run: |
          cd mcp_server
          pytest -m "not requires_rhino" --tb=short
```

This won't catch everything (it can't run the Rhino-requiring tests, can't build the C++ plugin without the Rhino SDK), but it catches **Python import errors, basic test failures, and pytest collection errors** — the class of bug that would otherwise embarrass you by slipping into `main`.

### More ambitious CI (add as you find pain points)

- **CodeQL** analysis (Security tab → Code scanning → Set up → Default → CodeQL) — catches common vulnerability patterns automatically
- **Linting** (`ruff check` for Python, `dotnet format --verify-no-changes` for C#) — catches style regressions
- **Dependency checks** (`pip-audit` or similar) — catches dependencies with known CVEs
- **markdown-link-check** — catches broken internal/external links in docs (would have caught the `docs/FEATURE_ROADMAP.md` broken link from the audit)

### Recommended starting point

Start with just the Python tests and CodeQL. Add more as you find pain points. Don't try to front-load the perfect CI setup — let it grow organically from "thing I wish I'd caught before it happened."

---

## 8. Secret management <a id="secret-management"></a>

The April 2026 audit caught a leaked Anthropic API key that had been committed to `autonomous_dev/.env` for ~2 months in the private repo. Going forward, make accidental secret commits impossible.

### Local pre-commit hook

Install [gitleaks](https://github.com/gitleaks/gitleaks) as a pre-commit hook. Every time you `git commit`, gitleaks scans the staged files for secret patterns and blocks the commit if it finds one.

```powershell
cd <repo>

# Create a pre-commit hook
@"
#!/bin/sh
gitleaks protect --staged --redact --no-banner
"@ | Set-Content .git\hooks\pre-commit

# Make it executable (git-bash)
chmod +x .git/hooks/pre-commit
```

This catches leaks at the earliest possible point, before they reach any git server.

### GitHub secret scanning + push protection

Enable these in repo Settings → Code security:

- **Secret scanning** — GitHub scans every commit ever in the repo for known secret patterns and alerts you
- **Secret scanning push protection** — GitHub rejects `git push` that introduces new secrets. This is different from scanning-after-the-fact — it blocks the push at the server before the secret ever lands in history.

These are free for public repos. Enable both.

### The `.env.example` pattern

Keep the pattern already established in the repo:

- `mcp_server/.env.example` — template, committed, contains only placeholders like `ANTHROPIC_API_KEY=your-key-here`
- `.env` — real values, gitignored, never committed

If you add new env vars, update the example file at the same time so contributors know what's expected.

### Rotate keys on a schedule

Even without leaks, rotating long-lived credentials on a schedule (e.g., every 90 days for API keys) is good hygiene. Set a calendar reminder.

### If a secret is ever committed anyway

1. **Rotate the credential immediately** at its source (console.anthropic.com, AWS IAM, etc.)
2. **Do not** try to force-push history rewriting to remove it — it's already been cloned, forked, and cached by GitHub's infrastructure. Treat the credential as permanently exposed.
3. Commit a fix that removes the credential from the working tree (using placeholder or env var)
4. File a GitHub security advisory noting the incident
5. If the credential granted access to production resources, audit the access logs for unauthorized use

**The critical insight:** rotation is the actual security fix. Removing the file from history is cosmetic.

---

## 9. Dependency updates <a id="dependency-updates"></a>

### Enable Dependabot (free on public repos)

In Settings → Code security:

- **Dependabot alerts** — notifies you when dependencies have known CVEs
- **Dependabot security updates** — automatically opens PRs with security fixes
- **Dependabot version updates** (optional) — opens PRs to keep dependencies current even without security issues

For Rook specifically, Dependabot will monitor:

- Python dependencies in `mcp_server/pyproject.toml`
- .NET NuGet packages referenced by `src/Rook/Rook.csproj`
- GitHub Actions used in `.github/workflows/*.yml`

**Suggested starting point:** security-only updates. Add version updates later if you want more currency at the cost of more PR noise.

### The LiteLLM incident as a case study

Per the Rook README, LiteLLM PyPI versions `1.82.7` and `1.82.8` were compromised with a credential-stealing payload. The Rook dependency pin explicitly excludes them.

**That exclusion is a model for how to handle future supply-chain incidents:** when you hear about a compromised package, add an exclusion pin immediately rather than waiting for the package maintainers to yank it. Dependabot won't catch this kind of thing proactively — it's a manual response to security news.

Subscribe to security advisory feeds for your critical dependencies so you hear about these incidents early.

---

## 10. Release management — semver, CHANGELOG, release flow <a id="release-management"></a>

### Semantic versioning

Rook is at `v1.4.5`. Going forward, follow [SemVer](https://semver.org/):

- **MAJOR** (`1.x.y` → `2.0.0`) — breaking changes. API renames, removed tools, config format changes that break existing users. Use sparingly.
- **MINOR** (`1.4.y` → `1.5.0`) — new features, backward-compatible. Users can upgrade safely.
- **PATCH** (`1.4.5` → `1.4.6`) — bug fixes only. No new features, no breaking changes. Users should always upgrade.

The discipline this creates: **before releasing, classify your changes and pick a version.**

- Added a new MCP tool without removing any old ones? **Minor.**
- Changed the default behavior of an existing tool? **Major** (users relying on old behavior will break).
- Only fixed bugs? **Patch.**

**Note:** v1.4.5 being the first public release is a bit of an oddity (would normally be `v1.0.0` for a first public release), but there's precedent for "the public release is the first stable after private iteration." Don't re-number retroactively.

### CHANGELOG.md

Create a `CHANGELOG.md` in the repo root with a section for every release. Format like [Keep a Changelog](https://keepachangelog.com/en/1.1.0/):

```markdown
# Changelog

All notable changes to Rook will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- ...

### Changed
- ...

### Fixed
- ...

## [1.5.0] - 2026-05-15

### Added
- `scene_query` MCP tool for topology inspection (#47)
- Support for Rhino 8.10 render mesh changes

### Changed
- `gh_execute_intent` now returns `correction_detected` field (non-breaking addition)

### Fixed
- Block definition geometry editing now correctly invalidates preview cache (#52)

## [1.4.5] - 2026-04-09

### Added
- Initial public release of Rook
- 300+ MCP tools for Rhino geometry and Grasshopper automation
- Intent-based execution with DSPy-powered routing
- Self-improving knowledge graph (924 GH components, 196 Rhino commands)
- Multi-agent system with planner, workers, and critic roles
- LLM-powered Chirp components
- Scene graph spatial intelligence
```

Every PR that's user-visible adds a line under `[Unreleased]`. When you cut a release, move the `[Unreleased]` items into a new versioned section.

This habit is annoying to start and invaluable after 6 months. It becomes the canonical "what's new in this version" document that release notes can be generated from.

### Release flow (until release.yml is fixed)

**Never** `git push origin v1.5.0` — it triggers the broken workflow. Use `gh release create` exclusively:

```powershell
# 1. Merge all release-bound PRs into main
# 2. Update CHANGELOG.md (move Unreleased → v1.5.0 section)
# 3. Update version numbers in:
#    - .claude-plugin/plugin.json
#    - .claude-plugin/marketplace.json
#    - installer/RookSetup.iss (#define MyAppVersion)
# 4. Merge the version-bump PR to main
# 5. Build the installer EXE locally from main
cd <repo>
.\build_native.ps1 -Configuration Release
dotnet build src/Rook -c Release -p:Platform=x64
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\RookSetup.iss

# 6. Create the release with gh CLI (creates tag server-side — doesn't fire the workflow)
gh release create v1.5.0 `
    --target main `
    --title "Rook v1.5.0" `
    --notes-file release-notes-v1.5.0.md `
    installer/output/Rook-Setup-1.5.0.exe

# 7. Verify no workflow fired
gh run list --repo bringfire/Rook --limit 5   # should be empty or only show CI runs
```

The `--target main` flag tells GitHub to create the tag at `main`'s current commit via the Releases API. This does NOT emit a push event, so the `on.push.tags: 'v*'` trigger in `release.yml` does NOT fire.

---

## 11. The `release.yml` workflow disposition <a id="release-yml-disposition"></a>

**This is a ticking time bomb in the repo.** If anyone ever runs `git push origin v*` with any tag name, the current `release.yml` workflow will fire and build a broken ZIP (missing RookNative binary) and publish it as a GitHub release.

### Three options

#### Option A: Delete the workflow (recommended short-term)

Rename `.github/workflows/release.yml` to `.github/workflows/release.yml.disabled` or delete it outright. Without the file, there's no trigger, and you can't accidentally fire the broken release. Then you handle all releases manually via `gh release create --target main`.

**This is the safest option.** It eliminates an entire class of footgun with zero risk.

#### Option B: Narrow the trigger to workflow_dispatch only

Change the trigger from `on: push: tags: 'v*'` to `on: workflow_dispatch:` (manual only). Tagging doesn't auto-fire anything, but the workflow still exists if you want to invoke it manually for some reason.

**Middle ground** — keeps the workflow code around for reference without auto-firing risk.

#### Option C: Fix the workflow properly (long-term)

The workflow needs to:
1. Build the C++ native plugin (requires Rhino SDK headers, which has licensing questions for GitHub Actions runners)
2. Build the C# companion
3. Run Inno Setup to produce the EXE
4. Attach the EXE to the release

This is a real engineering project — probably a day or two of work — and it requires figuring out how to handle the Rhino SDK dependency in GitHub Actions (license files, reference assemblies, etc.). Once done, tagging becomes the canonical release flow.

### Recommendation

**Delete the workflow now (Option A).** Bring it back later as a new implementation (Option C) when you have time to invest in proper CI. The current broken workflow gives you nothing that a manual `gh release create` doesn't, and removing it eliminates the footgun entirely.

**Do this as one of the first post-launch commits**, ideally as a PR so it exercises the new PR workflow.

---

## 12. Documentation discipline <a id="documentation-discipline"></a>

Documentation in a public repo is read by people you've never met. They assume everything you write is authoritative and current. **Stale docs are worse than missing docs because they cause confusion.**

### Keep the documentation "tier" structure

Rook already has it:

- **Tier 0:** `CLAUDE.md` / `AGENTS.md` (root) — loaded automatically by agents, routes to other tiers
- **Tier 1:** `README.md`, `QUICK_START.md`, `AGENT_SETUP.md` — first-contact docs for users and agents
- **Tier 2:** `docs/ONBOARDING_NEW_CLAUDE.md`, `docs/CURRENT_ARCHITECTURE.md`, `docs/AGENT_ARCHITECTURE.md`, `docs/TROUBLESHOOTING.md` — deeper references

This tier structure is sophisticated for a solo-dev project. Don't abandon it.

### When you add a feature

- **User-visible capability** → update README
- **Setup change** → update QUICK_START and AGENT_SETUP
- **Architectural change** → update `docs/CURRENT_ARCHITECTURE.md`

### The "docs for every PR" rule

For every PR that changes user-facing behavior, require a docs update in the same PR. Not a separate PR later (which will get forgotten). **Same PR.** This is the only way to prevent docs rot.

For internal refactors or bug fixes that don't change behavior, no docs update needed. The test is: "would a user notice this change?" If yes, docs update. If no, skip.

### Don't let the README lie

The April 2026 audit caught the "No Python installation required" lie in README.md — a claim that was true for the source bootstrap path but false for the EXE installer. That's the kind of thing that creeps in when someone updates one part of the install flow without updating the docs.

**Mental rule:** if your commit touches an installer file (`install.ps1`, `install.sh`, `installer/post_install.py`, `installer/RookSetup.iss`), it should probably also touch a docs file. If it doesn't, you're probably creating another "README lies" situation.

Grep for references when you change installer logic:

```powershell
grep -rn 'old-behavior-keyword' README.md QUICK_START.md AGENT_SETUP.md docs/
```

Update every hit in the same PR.

---

## 13. Knowledge store evolution <a id="knowledge-store"></a>

Rook has a self-improving knowledge store (`knowledge/gh/notes/`, `knowledge/commands/command_knowledge.json`, etc.) that agents update at runtime. This is a Rook-specific version-control challenge.

### The problem

Users running Rook will generate new observations and learn new patterns. Their local knowledge stores will drift from the shipped canonical one. If they clone the public repo and overwrite their local store with the repo's version, they lose their learnings. If you accept PRs that include knowledge store changes, those PRs might include user-specific observations that don't generalize.

### Suggested patterns

1. **Ship a canonical knowledge store baseline in `knowledge/`** — the version everyone starts from.
2. **Treat runtime updates as a separate overlay** — user-specific learnings go somewhere like `%LOCALAPPDATA%\Rook\knowledge_overlay\`, never written back to the source tree.
3. **Only accept knowledge PRs that add generic patterns.** If a PR adds an observation like "in my specific model this happens," reject. Accept patterns like "when using Boolean Union, edges can fail if coincident vertices exist."
4. **Use a consolidation tool** to merge high-value runtime observations back into the canonical store. The `consolidate` skill is designed for this — it's a developer-side workflow you run periodically to curate what's worth shipping.

This is a harder problem than it looks. Don't rush to solve it — let a few contributions land first and adjust based on what you see.

---

## 14. Issue triage <a id="issue-triage"></a>

As soon as the repo is public, users will open issues. The first 48 hours after public launch are critical — if a user opens an issue and gets no response for a week, they assume the project is dead.

### Core discipline

- **Respond to every issue within 72 hours**, even if it's just "thanks, I'll look at this next week." Silence signals abandoned project.
- **Use labels** — GitHub has built-in labels (`bug`, `enhancement`, `question`, `documentation`). Add more as you need.
- **Close decisively.** Not every feature request should become a feature. Not every bug report is reproducible. Closing with a clear reason ("this is by design because X", "can't reproduce, please reopen if you find a way to trigger it") is kinder than letting issues linger.
- **Use issue templates** — Settings → Features → Issues → Set up templates. Having a "Bug report" template that asks for Rhino version, OS, reproduction steps, etc. dramatically improves the signal-to-noise ratio.

### Label taxonomy

Set up a small, consistent label set:

**Type:**
- `bug` — something is broken
- `enhancement` — new feature or improvement
- `documentation` — docs-only change
- `question` — user support question
- `help-wanted` — contribution welcome

**Priority:**
- `priority/p0-critical` — broken, blocks users, fix ASAP
- `priority/p1-high` — important, fix this sprint
- `priority/p2-normal` — queue it
- `priority/p3-low` — nice to have

**Area:**
- `area/installer`
- `area/grasshopper`
- `area/knowledge-store`
- `area/chat-panel`
- `area/mcp-tools`
- `area/native-plugin`
- etc.

Every issue gets labeled within 24 hours of opening. This turns a chaotic queue into a sortable list.

### Issue templates

Create `.github/ISSUE_TEMPLATE/bug_report.yml` and `.github/ISSUE_TEMPLATE/feature_request.yml`. A minimal bug report template:

```yaml
name: Bug report
description: Something isn't working
labels: [bug]
body:
  - type: input
    id: rhino-version
    attributes:
      label: Rhino version
      placeholder: "Rhino 8.10 or newer"
    validations:
      required: true
  - type: input
    id: rook-version
    attributes:
      label: Rook version
      description: Check %LOCALAPPDATA%\Rook\app or the installer filename
    validations:
      required: true
  - type: textarea
    id: steps
    attributes:
      label: Steps to reproduce
      description: What did you do? What did you expect? What actually happened?
    validations:
      required: true
  - type: textarea
    id: logs
    attributes:
      label: Logs
      description: Paste relevant output from %LOCALAPPDATA%\Rook\logs\ or the MCP client
      render: text
```

### Stale bot (optional)

For a solo-maintainer project, set up [stale bot](https://github.com/actions/stale) to auto-close issues that have been inactive for 60 days without a response from the reporter. Prevents the issue tracker from accumulating dead weight.

---

## 15. The Claude + Codex review pattern <a id="claude-codex"></a>

This is a Rook-specific practice because it's how the April 2026 audit session was conducted, and it proved exceptionally effective. **Make it explicit in your workflow.**

### The pattern

1. **Plan or explore with Claude** (in a conversation like the audit session)
2. **Write the code with Claude**, step by step, with insights
3. **Commit the work-in-progress state** to a feature branch
4. **Hand the branch to Codex for independent review** with a short brief explaining what you did and what you're uncertain about
5. **Codex finds issues Claude missed** (different context, different tools, different prompt, different blind spots)
6. **Back to Claude to fix the issues**
7. **Second Codex review** on the fixed state if the fix set was large
8. **Merge when Codex signs off**

### Why it works

Claude and Codex are both LLM coding assistants but they have different strengths and different blind spots. Claude in a long conversation accumulates context and momentum — useful for holding state across many steps but also creates confirmation bias ("I already decided this is the right approach"). Codex coming in cold doesn't have that bias.

### What it caught in the April 2026 audit

Over five review rounds, Codex caught issues Claude had missed:

- **Round 1:** broken root `tests/` imports (referenced deleted `rhinoclaude` module), dead `ClaudeBridge` command references, internal state files in `.claude/explorations/` that shouldn't ship
- **Round 2:** `installer/post_install.py:390` flat-install bug (CRITICAL — would have shipped with skills broken for every user), C# config path check for deprecated `~/.claude/.mcp.json`, `QUICK_START.md` stale paths, plugin.json version drift
- **Round 3:** `release.yml` missing `scripts/` directory copy + hooks mkdir bug
- **Round 4:** `RookSetup.iss:126` stale `KNOWLEDGE_SYSTEMS_ARCHITECTURE.md` reference (gitignored file)
- **Round 5:** the actual flat-install root cause for the missed-skills report — Claude Code's user-skills loader expects `~/.claude/skills/<skill>/SKILL.md` one level deep, not the `~/.claude/skills/rook/<skill>/` namespaced path the installer was creating

**Five bug classes at five different review rounds, all caught by a reviewer that wasn't primed by Claude's earlier analysis.** Without the Codex partnership, several of those would have shipped. This is not hypothetical — the skills bug in particular would have broken the very first public user experience.

### Make it a habit

For any PR that's non-trivial, run it through Codex before merging:

1. Write a brief in a file (e.g., `.review-brief.md` or in a PR comment) explaining what changed and what you're uncertain about
2. Ask Codex to review against that brief
3. Codex writes findings to a response file or PR comment
4. You read the findings and decide what to apply

You can automate this eventually with a bot, but even the manual flow is valuable.

### When to skip Codex review

- Trivial changes (typo fix, version bump, changelog update)
- Changes you're 100% confident about AND have a small blast radius
- Emergency hotfixes where speed matters more than thoroughness (but review after the fact)

### When NOT to skip Codex review

- Any change to installer logic (`install.ps1`, `install.sh`, `installer/`)
- Any change to the release workflow
- Any change that touches user-facing paths or configuration
- Any change that deletes files or renames things
- Any change that modifies knowledge store structure
- Any change affecting security (auth, permissions, CORS, secrets handling)
- Any change you're uncertain about

---

## 16. Local directory rename (post-launch housekeeping) <a id="directory-rename"></a>

After the public flip is stable (say, a week after launch), clean up the local directory names to match the GitHub repo names.

### Current state

```
<repo>\                    ← original private dev clone
  remote: bringfire/Rook (redirects to bringfire/Rook-private-archive)
  614 commits, at d5d93e64

<repos>\Rook-public-staging\     ← the clean snapshot
  remote: bringfire/Rook (directly)
  1 commit, at afa94303 (current as of launch)
```

### Target state

```
<repo>\                    ← public dev (the canonical ongoing dir)
  remote: bringfire/Rook (the public repo)

<repos>\Rook-private-archive\    ← frozen archive (read-only reference)
  remote: bringfire/Rook-private-archive
```

### Steps

```powershell
cd <repos>

# Rename the original dev clone to match the archive repo name
Rename-Item Rook Rook-private-archive

# Update the renamed clone's remote to point at the actual archive URL (stop relying on redirect)
cd Rook-private-archive
git remote set-url origin git@github.com:bringfire/Rook-private-archive.git
git remote -v
git fetch

# Rename the staging directory to be the canonical Rook
cd ..
Rename-Item Rook-public-staging Rook

# Verify the renamed directory still works
cd Rook
git log -1 --format='%H %s'
git remote -v
# Expected: origin git@github.com:bringfire/Rook.git
```

**The filesystem rename does NOT affect the git state.** `git remote` is stored inside `.git/config`, which stores the remote URL as an absolute reference. Renaming the directory doesn't touch `.git/config`.

### Optional: delete the archive dir entirely

If you don't need the historical working tree on your local machine, you can delete `Rook-private-archive` after confirming the archive repo on GitHub has all the branches and tags you need. GitHub still has the full history at `bringfire/Rook-private-archive`.

**Recommendation:** keep the local archive for at least a year. Disk space is cheap. The archive gives you fast local access to old versions if you ever need them.

---

## 17. Preserving audit artifacts <a id="audit-artifacts"></a>

The April 2026 audit directory at `%USERPROFILE%\rook-audit-2026-04-07\` contains the full session state:

- `SUMMARY.md` — original security audit findings
- `STAGING_REPORT.md` — final cutover report with all fixes
- `CODEX_REVIEW_BRIEF.md` — brief sent to Codex for round 1 review
- `CODEX_REVIEW_RESPONSE.md` — Codex's round 1 response
- `b7_structural_edits.py` — Python script that performed JSON entry removals
- `iss_reverse_audit.py` — script that audited .iss file references
- `gitleaks-history.json`, `trufflehog-history.jsonl`, `large-blobs.txt` — scanner outputs

**Don't delete this directory.** It is:

- Historical reference for how the public repo came to exist
- Documentation of what was scrubbed and why
- A template for how to do future audit passes
- Evidence of due diligence if anyone ever questions the provenance of the public repo

### Where to keep it

- **Leave it local** (simplest) — at `%USERPROFILE%\rook-audit-2026-04-07\`
- **Move to a private archive location** (OneDrive, external drive, Time Machine) — if you want an off-machine backup
- **Commit it to a separate private repo** for "Rook administrative history" — if you want it versioned

**Don't commit it to the public Rook repo.** Most of the value of the audit was proving the public repo is free of that information.

---

## 18. Soak period checklist (after private force-push, before public flip) <a id="soak-checklist"></a>

Things you can productively do during the soak period without risking the launch:

- [ ] Browse the private repo in the GitHub web UI. See how it looks as a first-time visitor.
- [ ] **Enable Dependabot** (Settings → Code security → Dependabot alerts + security updates)
- [ ] **Enable secret scanning + push protection** (Settings → Code security → Secret scanning)
- [ ] **Enable CodeQL** (Settings → Code security → Code scanning → Set up → Default → CodeQL)
- [ ] **Enable private vulnerability reporting** (Settings → Code security → Private vulnerability reporting)
- [ ] **Set up branch protection rules** for `main` (Settings → Branches → Add rule)
- [ ] **Create issue templates** (Settings → Features → Issues → Set up templates)
- [ ] **Draft a `CONTRIBUTING.md`** with the PR flow for outside contributors (expand the stub created during the audit)
- [ ] **Create your first CI workflow** (`.github/workflows/ci.yml`) as a feature branch + PR + merge cycle (this exercises the PR flow before public)
- [ ] **Decide on `release.yml` disposition** — keep, delete, or fix (see section 11)
- [ ] **Review the README, QUICK_START, AGENT_SETUP through a first-time-visitor lens** — does it actually make sense?
- [ ] **Verify the built EXE is accessible** — `installer/output/Rook-Setup-1.4.5.exe` should be ready to upload to the release
- [ ] **Draft release notes** for v1.4.5 — what to put in the `gh release create --notes` field
- [ ] **Check your email/notification settings** on the GitHub account so you'll see alerts after the flip

None of these require waiting for the public flip. All of them make the public launch cleaner.

---

## 19. First week after public launch checklist <a id="first-week"></a>

- **Day 0 (flip day):** Monitor GitHub notifications closely. Respond to any issue or PR within 4 hours if possible. First impressions matter.
- **Day 1:** Check GitHub Insights → Traffic. See how many clones you're getting, which pages are being visited. Post about the release on your chosen channels (Twitter, LinkedIn, relevant Discord/Slack, Rhino forums, Hacker News, Reddit r/programming, r/rhino, etc.).
- **Day 2-3:** Review any first issues. Label them. Respond. Don't promise timelines you can't keep.
- **Day 4:** Check for new GitHub security alerts, Dependabot alerts, secret scanning alerts. Address anything that came in.
- **Day 5:** Review the PR backlog (will probably be empty in the first week). Check that CI is running on any PRs that did come in.
- **Day 6:** Write a short "first week of Rook being public" retrospective for yourself — what worked, what surprised you, what you want to change.
- **Day 7:** Decide whether to ship a point release (v1.4.6) addressing any critical issues found in the first week, or wait longer for a proper v1.5.0.

**Watch for these signals of trouble:**

- Issues about installation failures on Windows versions or configurations you didn't test
- Issues about Rhino plugin load failures
- Reports that skills aren't discovered (re-validation that the flat-install fix works across configurations)
- Dependabot alerts or secret scanning alerts
- Any mention of Rook on security news sites (unlikely but worth knowing)

---

## 20. Your first N public commits <a id="first-commits"></a>

To build the muscle memory for the PR workflow, make the first post-launch commits extra deliberate. Suggested sequence:

1. **First commit: `docs: fix README badge links`** or some tiny doc fix. Just to exercise the PR flow end-to-end. Branch → PR → review → merge.
2. **Second commit: `ci: add pytest validation workflow`** — the `.github/workflows/ci.yml` from section 7. Gives you automation foundation.
3. **Third commit: `chore: remove broken release.yml workflow`** — Option A from section 11. Eliminates the footgun.
4. **Fourth commit: `docs: add CHANGELOG.md with v1.4.5 entry`** — establishes the changelog habit (see section 10).
5. **Fifth commit: `docs: add status banner to README`** — something like "🚧 v1.4.5 is the initial public release. APIs and MCP tools may change before v2.0." This sets expectations with early adopters.
6. **Sixth commit and beyond:** real feature work, bug fixes, whatever you want to work on.

Each goes through: feature branch → PR → self-review → merge. After ~5 of these, the workflow becomes automatic.

---

## 21. Summary — the one-page answer <a id="summary"></a>

For ongoing development on public `bringfire/Rook`:

1. **Always use feature branches + PRs**, even as solo maintainer
2. **Never force-push `main`**, only `git revert` for rollbacks
3. **Write commit messages for strangers**, use Conventional Commits format
4. **Enable branch protection** on `main` immediately
5. **Run CI on every PR**, starting with `pytest -m "not requires_rhino"` + CodeQL
6. **Use pre-commit gitleaks** + enable GitHub secret scanning push protection
7. **Enable Dependabot** for security updates
8. **Commit to semver** — MAJOR for breaking, MINOR for features, PATCH for fixes
9. **Maintain CHANGELOG.md** with per-version entries
10. **Triage issues within 72 hours**, use labels, close decisively
11. **Delete or fix `release.yml`** before something accidentally triggers it
12. **Run non-trivial PRs through Codex** before merging
13. **Update docs in the same PR** as the code change
14. **Preserve audit artifacts** locally or in a private archive, not in the public repo
15. **Rename local directories** after launch so they match GitHub names

---

## 22. Meta-principle <a id="meta-principle"></a>

**Treat every commit as a permanent public statement.**

Even if you're the only person who'll look at it this week, someone might read it in six months to understand why a line of code exists, or to figure out whether a feature existed at a certain point, or to find a regression introduced by a particular change. Writing commits for that future reader is a small cost that pays off massively over time.

The single biggest difference between private-repo development and public-repo development is **accountability for the past**. In a private repo, history is a working draft you can rewrite freely. In a public repo, history is a ledger of decisions you've committed to. Every practice in this document exists to make that ledger coherent, readable, and trustworthy to people who weren't there when the decisions were made.

The audit that produced v1.4.5 was, in part, an act of cleaning up private-era history so it could survive public scrutiny. That audit should be the *last* time you ever need to do that kind of cleanup. From here forward, commit as though an outside reviewer is already watching — because eventually, they will be.

---

## Appendix: Derivation provenance

This document was derived from the Rook v1.4.5 public release audit session conducted in April 2026, specifically the post-launch best-practices discussion. The session worked through five rounds of independent Codex review that caught bugs Claude had missed:

- **Round 1:** broken root `tests/` imports, dead `ClaudeBridge` refs, internal `.claude/explorations/` state
- **Round 2:** `post_install.py:390` flat-install bug (HIGH), C# config path checks, `QUICK_START.md` stale paths, plugin metadata version drift
- **Round 3:** `release.yml` missing `scripts/` copy + hooks mkdir bug
- **Round 4:** `RookSetup.iss:126` stale `KNOWLEDGE_SYSTEMS_ARCHITECTURE.md` reference
- **Round 5:** flat-install root cause for missed skills discovery in Claude Code

The Claude + Codex partnership pattern documented in section 15 emerged from this session's pragmatic use of two independent LLM reviewers with different context windows. It is the single most important process recommendation in this document, because it is the only thing that reliably catches bugs that a single reviewer's momentum would have carried past.

**Final commit of the v1.4.5 release candidate:** `afa943030f09c3549d4bd55a3a181196c2d0089b`

**Audit artifacts location:** `%USERPROFILE%\rook-audit-2026-04-07\`
