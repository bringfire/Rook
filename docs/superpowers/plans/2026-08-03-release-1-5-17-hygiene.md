# Rook 1.5.17 Release Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the private release surface truthful and mechanically ready for a separate `1.5.17` version-bump pull request without changing runtime behavior or producing release artifacts.

**Architecture:** Add one bounded PowerShell contract guard, then correct the exact metadata, active-guidance, and mirrored build-release files it owns. Keep `.agents/skills/build-release` authoritative, copy its two changed files byte-for-byte to `.claude`, and make future public promotion start from immutable private bytes and current public `main`.

**Tech Stack:** Markdown, JSON, PowerShell 5.1, TOML/XML/resource-text inspection, Git, `uv`, Claude plugin CLI.

## Global Constraints

- Approved specification: `3c213689` with parent `905c0ed1`; baseline private `main`: `6eacc2e1fc2a77c73dda0f54b5dd6558a0cd9465`.
- Do not bump any release surface to `1.5.17`; this branch normalizes the current value `1.5.16` only.
- Do not change runtime routing, tool schemas, Grasshopper behavior, RookBIM behavior, dependencies, or lock resolution.
- Do not build, install, deploy, tag a release, publish artifacts, or modify `bringfire/rook-release`.
- Preserve historical specifications, plans, reports, dormant RoadCreator/native compatibility code, Wasp content, and the already accepted RUI and Grasshopper-cascade implementations.
- User-facing downloads, support, updates, and plugin installation point to `https://github.com/bringfire/rook-release`; private `bringfire/Rook` links remain only for source development or immutable provenance.
- `.agents/skills/build-release/SKILL.md` and its `references/version-locations.md` are authoritative; their `.claude` counterparts must be byte-identical after editing.
- The Windows installer bundles CPython 3.11.9. Active release guidance must not require system Python.
- The normative `gh_edit` wording is: “One request, ordered non-transactional mutations, at most one post-mutation solve request—not an all-or-nothing transaction.”
- No repository-wide test suite or host test is required. Run only the focused file-contract gates in this plan.
- Stop on any changed path outside the final allowlist in Task 4. Do not fold unrelated `main` changes into this branch.

---

### Task 0: Pin the approved plan and verify the isolated branch

**Files:**
- Read: `docs/superpowers/specs/2026-08-03-release-1-5-17-hygiene-design.md`
- Read: `docs/superpowers/plans/2026-08-03-release-1-5-17-hygiene.md`

**Interfaces:**
- Consumes: annotated tag `plan/release-1-5-17-hygiene-2026-08-03-approved` created only after plan approval.
- Produces: a clean, provenance-pinned execution checkout; no file changes.

- [ ] **Step 1: Require the approved tag, exact plan head, and approved spec parent**

```powershell
$ErrorActionPreference = 'Stop'
$approvedTag = 'plan/release-1-5-17-hygiene-2026-08-03-approved'
$approvedSpec = '3c213689'
$baselineMain = '6eacc2e1fc2a77c73dda0f54b5dd6558a0cd9465'

git cat-file -e "$approvedTag^{tag}"
if ($LASTEXITCODE -ne 0) { throw "Missing annotated approval tag $approvedTag" }

$approvedPlan = (git rev-parse "$approvedTag^{}").Trim()
$head = (git rev-parse HEAD).Trim()
$parent = (git rev-parse HEAD^).Trim()
$mergeBase = (git merge-base HEAD origin/main).Trim()

if ($head -ne $approvedPlan) { throw "HEAD $head is not approved plan $approvedPlan" }
if ($parent -ne (git rev-parse $approvedSpec).Trim()) { throw "Plan parent is not approved spec $approvedSpec" }
if ($mergeBase -ne $baselineMain) { throw "Unexpected private-main merge base $mergeBase" }
if (git status --porcelain) { git status --short; throw 'Worktree is dirty' }
```

Expected: all checks succeed and the worktree remains clean.

- [ ] **Step 2: Require the pre-implementation two-document scope**

```powershell
$expected = @(
  'docs/superpowers/plans/2026-08-03-release-1-5-17-hygiene.md',
  'docs/superpowers/specs/2026-08-03-release-1-5-17-hygiene-design.md'
) | Sort-Object
$actual = @(git diff --name-only "${baselineMain}...HEAD") | Sort-Object
if (($actual -join "`n") -ne ($expected -join "`n")) {
  throw "Unexpected bootstrap scope:`n$($actual -join "`n")"
}
```

Expected: exactly the approved specification and plan.

- [ ] **Step 3: Fetch current `main` and stop only on real path overlap or merge conflict**

```powershell
git fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Could not fetch origin/main' }

$mainPaths = @(git diff --name-only "${baselineMain}..origin/main")
$plannedImplementationPaths = @(
  '.agents/skills/build-release/SKILL.md',
  '.agents/skills/build-release/references/version-locations.md',
  '.claude-plugin/marketplace.json',
  '.claude-plugin/plugin.json',
  '.claude/skills/build-release/SKILL.md',
  '.claude/skills/build-release/references/version-locations.md',
  'AGENT_SETUP.md',
  'BUILDING.md',
  'CLAUDE.md',
  'QUICK_START.md',
  'README.md',
  'docs/roadmaps/2026-07-31-release-surface-hardening-roadmap.md',
  'installer/pre-install-readme.txt',
  'mcp_server/README.md',
  'scripts/python-runtime/build-rook-python-wheelhouse.ps1',
  'scripts/register-companion.ps1',
  'scripts/register-rooknative-suite.ps1',
  'scripts/tests/release-installer-guards.tests.ps1',
  'scripts/tests/release-surface-hygiene.tests.ps1',
  'src/Rook/Properties/AssemblyInfo.cs',
  'src/RookNative/RookNativePlugin.cpp'
)
$overlap = @($mainPaths | Where-Object { $plannedImplementationPaths -contains $_ })
if ($overlap) { throw "origin/main overlaps planned paths:`n$($overlap -join "`n")" }

git merge-tree --write-tree HEAD origin/main | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Synthetic merge with current origin/main is not clean' }
```

Expected at planning time: no overlap and a clean synthetic merge. Do not rebase merely because `main` advanced.

---

### Task 1: Add the focused guard and normalize release metadata

**Files:**
- Create: `scripts/tests/release-surface-hygiene.tests.ps1`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `scripts/python-runtime/build-rook-python-wheelhouse.ps1:1-8`
- Modify: `src/RookNative/RookNativePlugin.cpp:42-52`
- Modify: `src/Rook/Properties/AssemblyInfo.cs:12`
- Modify: `scripts/register-rooknative-suite.ps1:72-75`
- Modify: `scripts/register-companion.ps1:186-187`

**Interfaces:**
- Consumes: the ten version-bearing surfaces and the exact metadata fields named by the specification.
- Produces: `scripts/tests/release-surface-hygiene.tests.ps1 [-Area All|Metadata|Guidance|Workflow]`, defaulting to `All`, with no filesystem or network mutation.

- [ ] **Step 1: Write the complete guard before changing release surfaces**

Create a direct PowerShell test runner following `scripts/tests/release-installer-guards.tests.ps1`, with `Assert-True`, `Assert-Contains`, and `Assert-NotContains`. Its metadata area must extract and compare these exact fields:

```powershell
param(
  [ValidateSet('All', 'Metadata', 'Guidance', 'Workflow')]
  [string]$Area = 'All'
)

$expectedVersion = '1.5.16'
$expectedPublicRepo = 'https://github.com/bringfire/rook-release'
$expectedPublicReleases = "$expectedPublicRepo/releases"

# The returned keys are fixed contract names, not a repository-wide version scan.
$versions = [ordered]@{
  pyproject = Get-SingleRegexGroup 'mcp_server/pyproject.toml' '(?m)^version = "([^"]+)"$'
  uv_lock = Get-RookLockVersion 'mcp_server/uv.lock' 'rook-mcp'
  installer = Get-SingleRegexGroup 'installer/RookSetup.iss' '(?m)^#define MyAppVersion "([^"]+)"$'
  companion = Get-SingleRegexGroup 'src/Rook/Rook.csproj' '<Version>([^<]+)</Version>'
  bim = Get-SingleRegexGroup 'src/RookBim/RookBim.csproj' '<Version>([^<]+)</Version>'
  native_resource = Get-NativeResourceVersion 'src/RookNative/RookNative.rc'
  native_plugin = Get-SingleRegexGroup 'src/RookNative/RookNativePlugin.cpp' 'm_plugin_version\(L"([^"]+)"\)'
  native_server = Get-SingleRegexGroup 'src/RookNative/RookServer.cpp' 'kRookNativePluginVersion = "([^"]+)"'
  claude_plugin = (Get-Content '.claude-plugin/plugin.json' -Raw | ConvertFrom-Json).version
  claude_marketplace_metadata = (Get-Content '.claude-plugin/marketplace.json' -Raw | ConvertFrom-Json).metadata.version
  claude_marketplace_plugin = (Get-Content '.claude-plugin/marketplace.json' -Raw | ConvertFrom-Json).plugins[0].version
}

foreach ($entry in $versions.GetEnumerator()) {
  Assert-True ($entry.Value -eq $expectedVersion) "$($entry.Key) version '$($entry.Value)' must equal $expectedVersion"
}
```

`Get-NativeResourceVersion` must require all four resource values to encode `1.5.16`; `Get-RookLockVersion` must read only the `[[package]]` block whose `name = "rook-mcp"`. The same area must require:

- plugin `skills == './.claude/skills/'` and `hooks == './hooks/hooks.json'`;
- both plugin repositories equal `$expectedPublicRepo`;
- plugin descriptions omit `RoadCreator`, `RookRoads`, `3D road design`, and `3D roads`;
- the wheelhouse `Version` parameter has `Parameter(Mandatory = $true)`, has a semantic-version validator, and has no default expression;
- only the named website/update fields in the four metadata-owner files use `$expectedPublicRepo` or `$expectedPublicReleases`, with no `bringfire/Rhino_AI`.

Add the Guidance and Workflow assertions described in Tasks 2 and 3 now, but select tests by `$Area` so each task has a focused RED/GREEN cycle. Default `All` runs every area.

- [ ] **Step 2: Run the metadata area and verify the intended RED failures**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-surface-hygiene.tests.ps1 -Area Metadata
```

Expected: FAIL because the Claude versions are `1.5.9`, component paths use `../`, descriptions advertise roads, metadata uses `bringfire/Rhino_AI`, and the wheelhouse version defaults to `1.5.10`. If it fails for parsing or an unrelated field, correct the test before implementation.

- [ ] **Step 3: Apply the minimal metadata corrections**

Use these exact values:

```json
{
  "version": "1.5.16",
  "repository": "https://github.com/bringfire/rook-release",
  "skills": "./.claude/skills/",
  "hooks": "./hooks/hooks.json"
}
```

Set both marketplace version fields to `1.5.16`, use the same public repository, and describe Rook as a client-neutral Rhino/Grasshopper MCP bridge with skills and hooks—without road claims. Change the wheelhouse parameter to:

```powershell
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9]+\.[0-9]+\.[0-9]+$')]
    [string]$Version,
    [string]$RepoRoot = '',
    [string]$ChirpRoot = '',
    [string]$RuntimeRoot = '',
    [string]$OutputRoot = '',
    [string]$BuildRoot = '',
    [int]$CommandTimeoutSeconds = 1800
)
```

Change only the exact metadata fields to:

```text
Web site:  https://github.com/bringfire/rook-release
Update URL: https://github.com/bringfire/rook-release/releases
```

Do not change native behavior, registry ownership, or unrelated descriptions.

- [ ] **Step 4: Verify GREEN metadata, strict Claude validity, and unchanged lock data**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-surface-hygiene.tests.ps1 -Area Metadata
if ($LASTEXITCODE -ne 0) { throw 'Metadata guard failed' }

claude plugin validate --strict .
if ($LASTEXITCODE -ne 0) { throw 'Strict Claude plugin validation failed' }

Push-Location mcp_server
try { uv lock --check; if ($LASTEXITCODE -ne 0) { throw 'uv lock check failed' } }
finally { Pop-Location }

git diff --exit-code 6eacc2e1 -- mcp_server/uv.lock
if ($LASTEXITCODE -ne 0) { throw 'uv.lock changed in hygiene work' }
```

Expected: all commands pass; `uv.lock` remains byte-unchanged.

- [ ] **Step 5: Commit the metadata boundary**

```powershell
git add -- `
  .claude-plugin/plugin.json `
  .claude-plugin/marketplace.json `
  scripts/python-runtime/build-rook-python-wheelhouse.ps1 `
  scripts/register-companion.ps1 `
  scripts/register-rooknative-suite.ps1 `
  scripts/tests/release-surface-hygiene.tests.ps1 `
  src/Rook/Properties/AssemblyInfo.cs `
  src/RookNative/RookNativePlugin.cpp
git commit -m "fix(release): align package and repository metadata"
```

---

### Task 2: Correct the exact active guidance and roadmap ledger

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md:48-72,256`
- Modify: `QUICK_START.md`
- Modify: `AGENT_SETUP.md`
- Modify: `mcp_server/README.md`
- Modify: `installer/pre-install-readme.txt`
- Modify: `BUILDING.md:294-298`
- Modify: `docs/roadmaps/2026-07-31-release-surface-hardening-roadmap.md`

**Interfaces:**
- Consumes: the shipped installer contract, lifecycle/profile contract, and accepted `gh_edit` response fields.
- Produces: client-neutral, profile-aware active guidance and an evidence ledger that does not overstate unfinished public promotion or live acceptance.

- [ ] **Step 1: Run the previously written guidance guard and verify RED**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-surface-hygiene.tests.ps1 -Area Guidance
```

Expected: FAIL on the stale system-Python prerequisites, Claude-required wording, global exact tool counts, atomic `gh_edit` wording, private user-facing download/support URLs, the RookRoads build command, or stale MCP README claims.

- [ ] **Step 2: Apply only these document corrections**

| File | Required correction |
|---|---|
| `README.md` | Point download/release links to `bringfire/rook-release`; say any compatible MCP client is supported; say the installer bundles CPython 3.11.9; say it installs curated Codex skills while Claude skills/hooks come from the public marketplace plugin; remove Claude-agent-copy claims and mutable global tool counts. Preserve private links only in source-development instructions. |
| `CLAUDE.md` | Replace “ONE atomic call” and “one atomic write” with the normative ordered/non-transactional contract; require inspection of `success`, `partial_success`, `edit_summary`, scheduling fields, a fresh `gh_snapshot`, and `gh_errors`; point user support to `bringfire/rook-release/issues`. Do not change runtime architecture guidance. |
| `QUICK_START.md` | Remove system-Python prerequisite/troubleshooting; describe Claude and Codex as supported client choices; avoid a global tool count; keep release downloads public; replace the installed-invalid `CLAUDE.md` next-step link with `AGENT_SETUP.md` plus the public marketplace instructions. |
| `AGENT_SETUP.md` | Make Rhino 8 plus a compatible MCP client the release prerequisites; move Python requirements to source development; remove “Claude Code: Yes” and global-count claims; replace the atomic `gh_edit` row with the normative contract and verification instruction. |
| `mcp_server/README.md` | Make the package client-neutral; distinguish source installation from the bundled release runtime; make model-provider credentials optional/provider-specific; remove the `113 tools` claim and describe lifecycle/profile admission. |
| `installer/pre-install-readme.txt` | State that CPython 3.11.9 is bundled; retain truthful Codex-skill and Claude-marketplace ownership; do not add source-development prerequisites. |
| `BUILDING.md` | Delete only the `dotnet build ..\RookRoads\RookRoads.csproj -f net48 -c Release` command. Keep the Rook and SA_Banana commands unchanged. |

The Guidance guard must inspect only these seven documents and the exact claims above. It must not scan historical evidence or reject legitimate private source-development links.

- [ ] **Step 3: Update the roadmap without declaring unfinished work complete**

Add evidence rows for:

- RoadCreator/RookRoads containment: PR `#521`, merge `3ba27ebe`, verified at user/agent surfaces while Wasp remains separate.
- Legacy RUI suppression: PR `#531`, merge `2428dca8`, verified without absorbing RS-02 panel repair.
- Grasshopper routed skill cascade: PR `#538`, merge `6eacc2e1`, with installed-runtime acceptance at `ccdd2807` and final reviewed contracts at `0ff3c080`.
- This release-hygiene work: leave RS-06, RS-07, RS-08, RS-10, and RS-11 `in_progress` until the private PR merges and the later public promotion/release gates pass.

Replace the obsolete “Immediate next action” with: finish and merge the private hygiene PR; then create the separate ten-file `1.5.17` bump PR; only after its merge build, accept, and promote from the exact private release SHA. Do not mark public promotion or final live acceptance complete.

- [ ] **Step 4: Verify GREEN guidance**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-surface-hygiene.tests.ps1 -Area Guidance
if ($LASTEXITCODE -ne 0) { throw 'Guidance guard failed' }

rg -n "ONE atomic call|one atomic write|Modify the Grasshopper canvas atomically|Python 3\.10\+ required for the Windows installer|nearly 400 tools|113 tools" `
  README.md CLAUDE.md QUICK_START.md AGENT_SETUP.md mcp_server/README.md installer/pre-install-readme.txt BUILDING.md
if ($LASTEXITCODE -eq 0) { throw 'Stale active-guidance contract remains' }
```

Expected: focused guard passes and the exact stale phrases are absent.

- [ ] **Step 5: Commit the active-guidance boundary**

```powershell
git add -- `
  README.md CLAUDE.md QUICK_START.md AGENT_SETUP.md BUILDING.md `
  mcp_server/README.md installer/pre-install-readme.txt `
  docs/roadmaps/2026-07-31-release-surface-hardening-roadmap.md
git commit -m "docs: correct active release guidance"
```

---

### Task 3: Correct the mirrored build-release workflow

**Files:**
- Modify: `.agents/skills/build-release/SKILL.md`
- Modify: `.agents/skills/build-release/references/version-locations.md`
- Modify by exact copy: `.claude/skills/build-release/SKILL.md`
- Modify by exact copy: `.claude/skills/build-release/references/version-locations.md`
- Modify: `scripts/tests/release-installer-guards.tests.ps1:603-618`
- Modify: `scripts/tests/release-surface-hygiene.tests.ps1`

**Interfaces:**
- Consumes: ten version-bearing files, immutable private release SHA, staged artifact hashes, current public `main`, and exact public promotion inventory.
- Produces: a generic `build-release` workflow that bumps 10 files/14 edits and publishes only through a reviewed `bringfire/rook-release` promotion commit.

- [ ] **Step 1: Run the workflow guard and verify RED**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-surface-hygiene.tests.ps1 -Area Workflow
```

Expected: FAIL because the skill still says `7 files / 10 edits`, omits `uv.lock` and both Claude manifests, lacks immutable promotion-copy verification, and creates the release in the private repository.

- [ ] **Step 2: Update the authoritative version-location reference**

Replace the seven-file inventory with these ten files and fourteen edits:

```text
1  mcp_server/pyproject.toml                                  1 edit
2  mcp_server/uv.lock                                        1 local-project version edit
3  installer/RookSetup.iss                                   1 edit
4  src/Rook/Rook.csproj                                      1 edit
5  src/RookBim/RookBim.csproj                                1 edit
6  src/RookNative/RookNative.rc                               4 edits
7  src/RookNative/RookNativePlugin.cpp                        1 edit
8  src/RookNative/RookServer.cpp                              1 edit
9  .claude-plugin/plugin.json                                 1 edit
10 .claude-plugin/marketplace.json                            2 edits
```

Require `uv lock` after changing `pyproject.toml`, then fail unless `git diff -- mcp_server/uv.lock` changes only the `rook-mcp` local project version. Require both marketplace version fields, strict Claude validation, and the focused release-surface guard before the version-bump commit.

- [ ] **Step 3: Update the authoritative build-release skill**

Keep the current build order and artifact/live acceptance. Make only these workflow changes:

1. Pipeline Step 1 says `10 files / 14 edits`.
2. Preflight runs `scripts/tests/release-surface-hygiene.tests.ps1`, the existing installer guard, `claude plugin validate --strict .`, and `uv lock --check`.
3. Version-bump staging and verification use the ten-file inventory from the reference.
4. `build-rook-python-wheelhouse.ps1` is always invoked with explicit `-Version $Version`.
5. Replace private “GitHub Release” with “Public promotion PR and release.”
6. Preserve the accepted private release SHA and artifact hashes before promotion.
7. Create a detached private checkout from that exact SHA. Promotion bytes may come only from that checkout.
8. Fetch `bringfire/rook-release`, branch from its then-current `origin/main`, and stop on a dirty or non-fast-forward public checkout.
9. The byte-promoted inventory is exactly:

```powershell
$publicSkillNames = @(
  'capture-convention',
  'chirp',
  'chirp-cascade',
  'clean-layers',
  'design-grasshopper',
  'execute-grasshopper',
  'plan-grasshopper',
  'project-setup',
  'twisted-column'
)
$singletonPaths = @(
  '.claude-plugin/plugin.json',
  '.claude-plugin/marketplace.json',
  'hooks/hooks.json'
)
```

Copy every file beneath those nine private `.claude/skills/<name>` roots plus the three singleton paths. Exact-delete the two retired public skill roots `design-road` and `masterplan-roads`; do not enumerate or delete other public directories. Public-only README/site/release-note edits remain explicit reviewed changes in the public PR, not private-byte copies.

10. Generate source and candidate inventories with relative path, byte length, and SHA-256; require exact equality before opening the public PR.
11. Record private SHA, public base SHA, public promotion SHA, installer/source-bundle/smoke/release-manifest hashes, and the promotion inventory in the public PR.
12. Create `v$Version` in `bringfire/rook-release`, targeting the reviewed public promotion commit. Never call `gh release create` against the private repository.

- [ ] **Step 4: Synchronize the Claude mirror and update the existing stale guard**

```powershell
Copy-Item -LiteralPath .agents/skills/build-release/SKILL.md `
  -Destination .claude/skills/build-release/SKILL.md -Force
Copy-Item -LiteralPath .agents/skills/build-release/references/version-locations.md `
  -Destination .claude/skills/build-release/references/version-locations.md -Force
```

In `Test-BuildReleaseVersionBumpIncludesRookBim`, replace the stale `7 files / 10 edits` expectation with `10 files / 14 edits`, retain the RookBIM assertion, and add exact assertions for `mcp_server/uv.lock`, `.claude-plugin/plugin.json`, and both marketplace version fields. Do not refactor the rest of the existing guard suite.

- [ ] **Step 5: Verify GREEN workflow and mirror equality**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-surface-hygiene.tests.ps1 -Area Workflow
if ($LASTEXITCODE -ne 0) { throw 'Workflow guard failed' }

powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-installer-guards.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'Existing release installer guard failed' }

$pairs = @(
  @('.agents/skills/build-release/SKILL.md', '.claude/skills/build-release/SKILL.md'),
  @('.agents/skills/build-release/references/version-locations.md', '.claude/skills/build-release/references/version-locations.md')
)
foreach ($pair in $pairs) {
  $left = (Get-FileHash -LiteralPath $pair[0] -Algorithm SHA256).Hash
  $right = (Get-FileHash -LiteralPath $pair[1] -Algorithm SHA256).Hash
  if ($left -ne $right) { throw "Build-release mirror mismatch: $($pair -join ' <> ')" }
}
```

Expected: both guards pass and each mirror pair has identical hashes.

- [ ] **Step 6: Commit the release-workflow boundary**

```powershell
git add -- `
  .agents/skills/build-release/SKILL.md `
  .agents/skills/build-release/references/version-locations.md `
  .claude/skills/build-release/SKILL.md `
  .claude/skills/build-release/references/version-locations.md `
  scripts/tests/release-installer-guards.tests.ps1 `
  scripts/tests/release-surface-hygiene.tests.ps1
git commit -m "docs(release): require verified public promotion"
```

---

### Task 4: Run the complete focused acceptance and scope audit

**Files:**
- Verify only; no new files or acceptance-report commit.

**Interfaces:**
- Consumes: Tasks 1–3 commits.
- Produces: reproducible command output for the private PR description.

- [ ] **Step 1: Run all permanent focused gates**

```powershell
$ErrorActionPreference = 'Stop'

powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-surface-hygiene.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'Release-surface hygiene guard failed' }

powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/release-installer-guards.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'Release-installer guard failed' }

powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/python-runtime-packaging.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'Python runtime packaging guard failed' }

claude plugin validate --strict .
if ($LASTEXITCODE -ne 0) { throw 'Strict Claude plugin validation failed' }

Push-Location mcp_server
try { uv lock --check; if ($LASTEXITCODE -ne 0) { throw 'uv lock check failed' } }
finally { Pop-Location }
```

Expected: every focused gate passes. Do not substitute the repository-wide Python suite or a host test.

- [ ] **Step 2: Require the exact final changed-path allowlist**

```powershell
$allowed = @(
  '.agents/skills/build-release/SKILL.md',
  '.agents/skills/build-release/references/version-locations.md',
  '.claude-plugin/marketplace.json',
  '.claude-plugin/plugin.json',
  '.claude/skills/build-release/SKILL.md',
  '.claude/skills/build-release/references/version-locations.md',
  'AGENT_SETUP.md',
  'BUILDING.md',
  'CLAUDE.md',
  'QUICK_START.md',
  'README.md',
  'docs/roadmaps/2026-07-31-release-surface-hardening-roadmap.md',
  'docs/superpowers/plans/2026-08-03-release-1-5-17-hygiene.md',
  'docs/superpowers/specs/2026-08-03-release-1-5-17-hygiene-design.md',
  'installer/pre-install-readme.txt',
  'mcp_server/README.md',
  'scripts/python-runtime/build-rook-python-wheelhouse.ps1',
  'scripts/register-companion.ps1',
  'scripts/register-rooknative-suite.ps1',
  'scripts/tests/release-installer-guards.tests.ps1',
  'scripts/tests/release-surface-hygiene.tests.ps1',
  'src/Rook/Properties/AssemblyInfo.cs',
  'src/RookNative/RookNativePlugin.cpp'
) | Sort-Object

$actual = @(git diff --name-only 6eacc2e1...HEAD) | Sort-Object
if (($actual -join "`n") -ne ($allowed -join "`n")) {
  throw "Final scope mismatch:`n$($actual -join "`n")"
}

git diff --check 6eacc2e1...HEAD
if ($LASTEXITCODE -ne 0) { throw 'git diff --check failed' }
if (git status --porcelain) { git status --short; throw 'Worktree is dirty' }
```

Expected: exactly 23 paths, no whitespace errors, clean worktree.

- [ ] **Step 3: Verify immutable surfaces and current-main integration**

```powershell
git diff --exit-code 6eacc2e1 -- mcp_server/uv.lock mcp_server/pyproject.toml installer/RookSetup.iss src/Rook/Rook.csproj src/RookBim/RookBim.csproj src/RookNative/RookNative.rc src/RookNative/RookServer.cpp
if ($LASTEXITCODE -ne 0) { throw 'A non-hygiene version/runtime surface changed' }

git fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Could not refresh origin/main' }
git merge-tree --write-tree HEAD origin/main | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Candidate no longer merges cleanly with origin/main' }
```

Expected: the seven already-correct version/runtime files and `uv.lock` remain unchanged; current `main` merges cleanly.

---

### Task 5: Push one focused private PR

**Files:**
- No file changes.

**Interfaces:**
- Consumes: clean accepted Task 4 head.
- Produces: one non-draft PR against current private `main`; no merge and no public-repository mutation.

- [ ] **Step 1: Push without rewriting reviewed commits**

```powershell
git push -u origin codex/release-1-5-17-hygiene
if ($LASTEXITCODE -ne 0) { throw 'Push failed' }
if ((git rev-parse HEAD).Trim() -ne (git rev-parse origin/codex/release-1-5-17-hygiene).Trim()) {
  throw 'Local and remote heads differ'
}
```

- [ ] **Step 2: Open the private PR against `main`**

The PR description must state:

- current `1.5.16` is normalized; `1.5.17` is not bumped here;
- exact 23-path scope and three implementation commits;
- strict Claude validation and all three focused PowerShell guards passed;
- `uv lock --check` passed and `uv.lock` stayed byte-unchanged;
- no runtime build, install, deployment, live host, release artifact, tag, or public-repository mutation occurred;
- repository-wide tests were intentionally excluded by the approved documentation/release-only plan;
- the next change is the separate ten-file `1.5.17` version-bump PR.

Use a regular merge commit later if preserving the specification, plan, and three implementation boundaries matters. Do not merge as part of this task.
