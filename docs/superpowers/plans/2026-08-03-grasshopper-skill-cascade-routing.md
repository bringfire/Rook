# Grasshopper Skill Cascade Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Replace the mandatory four-stage Grasshopper cascade with accurate routed design, optional planning, and owned execution skills; retire consolidate from user skill surfaces; and admit Wasp only through live evidence.

**Architecture:** Routing remains skill guidance. The three retained skill roots are authored once under .agents and copied byte-for-byte to .claude and the installer payload; focused contracts prevent drift. Private implementation and installed Codex-lean acceptance complete before a separate rook-release promotion based on the accepted private SHA.

**Tech Stack:** Markdown agent skills, Rook MCP 1.5.16, Python 3.11.9, MCP SDK 1.28.1, pytest, Windows PowerShell, Inno Setup 6, Codex CLI, Rhino 8, Grasshopper, and Astro for the later public site promotion.

## Global Constraints

- Pinned base: 93fe02e58836934edf836c13a3a92439328616b8.
- Approved specification: 96f42a2b082f7c213c5071a746aa00c2454a88e9.
- Approved plan ref after review: refs/tags/plan/grasshopper-skill-cascade-routing-2026-08-03-approved. Execution must begin at the exact tagged plan commit, whose parent is the approved specification.
- Task 0 RED evidence must finish before any skill, guidance, test, installer, or runtime file is edited.
- Routing is prose guidance. Add no runtime dispatcher, orchestration service, state machine, or skill generator.
- Frontmatter descriptions contain trigger conditions only. Routing and completion choices live in skill bodies.
- The design stage is read-only. The plan stage is read-only. Execution owns all mutation.
- A direct build or edit request authorizes its bounded mutations. Ask again only for ambiguity, destruction, changes to pre-existing content, or meaningful scope expansion.
- Execution always obtains a fresh gh_snapshot epoch immediately before mutation. No durable plan stores an epoch.
- In-memory drift adaptation is limited to refreshed identities or ports and already-satisfied operations. Semantic, topology, ownership, or preservation changes require approval.
- Do not replay committed operations after gh_edit partial success.
- Do not run unconditional global gh_canvas_cleanup. Group, move, retry, disconnect, or delete only execution-owned components unless identified pre-existing content is explicitly authorized.
- Remove consolidate only as a user skill and product workflow. Do not change gh_consolidate, DSPy modules, knowledge stores, developer maintenance tooling, or full/progressive tool access.
- Keep internal gh_delete and gh_set_value dispatcher compatibility cases. Remove only their false use as declared MCP calls in active skills.
- Replace active Wasp recipes with one compact admission reference. Do not implement, upgrade, or broadly verify Wasp.
- For each retained skill, .agents, .claude, and installer/agent-assets/codex-skills must have identical recursive relative-file sets and byte-identical contents.
- Extend the existing exact retired-Codex-skill migration; do not add a cleanup framework, glob, prefix match, parent deletion, Claude cleanup, or sibling cleanup.
- Rook version remains 1.5.16. Python remains 3.11.9. mcp remains 1.28.1. jsonschema remains 4.26.0. Do not change dependencies or locks.
- Chirp release provenance remains the clean commit 2eedab6c9aaa19e458cbd939889e980f781445f3.
- Do not touch native C++, managed Rhino/RookBIM code, bridge routes, FFmpeg sources or artifacts, knowledge data, historical evidence, or unrelated skills.
- Run focused gates only. Do not run the known non-green repository-wide suite.
- Public rook-release work is Gate 2. It cannot block acceptance or merge of the private Rook PR.
- The accepted private SHA is public-promotion provenance. Do not claim Git ancestry between the two repositories.

## File and Commit Structure

1. Design-skill commit: read-only design contract, compact Wasp admission, exact mirrors, and design-focused tests.
2. Plan-skill commit: optional durable planning contract, no volatile epoch, current tool patterns, stale Wasp recipe removal, and plan-focused tests.
3. Execute-skill commit: strict ownership, partial-success recovery, no consolidation, truthful gh_edit descriptions, and execute-focused tests.
4. Retirement/migration commit: remove consolidate skill roots, correct active guidance, extend exact installer cleanup, and add focused retirement tests.
5. Evidence-only private acceptance commit after installed and live gates pass.
6. Separate public promotion commit and PR after the private commit is accepted.

---

### Task 0: Capture the immutable RED cascade baseline

**Files:**
- Read: docs/superpowers/specs/2026-08-02-grasshopper-skill-cascade-routing-design.md
- Read: docs/superpowers/plans/2026-08-03-grasshopper-skill-cascade-routing.md
- Read: .agents/skills/design-grasshopper/**
- Read: .agents/skills/plan-grasshopper/**
- Read: .agents/skills/execute-grasshopper/**
- Read: .agents/skills/consolidate/**
- Create ignored evidence: .scratch/grasshopper-skill-cascade-routing/baseline/**

**Interfaces:**
- Consumes: approved spec, exact plan ref, and current skill assets.
- Produces: one immutable scenario fixture hash and five raw baseline evaluations for candidate replay.

- [ ] **Step 1: Verify the exact execution boundary**

~~~powershell
$base = '93fe02e58836934edf836c13a3a92439328616b8'
$spec = '96f42a2b082f7c213c5071a746aa00c2454a88e9'
$planRef = 'refs/tags/plan/grasshopper-skill-cascade-routing-2026-08-03-approved'
if ((git rev-parse "$spec^").Trim() -ne $base) { throw 'Approved specification parent changed.' }
git show-ref --verify --quiet $planRef
if ($LASTEXITCODE -ne 0) { throw 'Approved plan ref is missing.' }
$plan = (git rev-parse "$planRef^{commit}").Trim()
if ((git rev-parse HEAD).Trim() -ne $plan) { throw 'Execution must start at the exact approved plan commit.' }
if ((git rev-parse "$plan^").Trim() -ne $spec) { throw 'Approved plan parent changed.' }
if (@(git status --porcelain).Count -ne 0) { git status --short; throw 'Execution worktree is dirty.' }
if ((git -C C:\Users\aryan\source\repos\Chirp rev-parse HEAD).Trim() -ne '2eedab6c9aaa19e458cbd939889e980f781445f3') { throw 'Chirp provenance changed.' }
if (@(git -C C:\Users\aryan\source\repos\Chirp status --porcelain).Count -ne 0) { throw 'Chirp is dirty.' }
~~~

Expected: exit 0. Do not continue from the specification commit or an unreviewed plan commit.

- [ ] **Step 2: Create the single scenario fixture**

Create .scratch/grasshopper-skill-cascade-routing/scenarios.md with exactly this evaluator contract and the five prompts:

~~~markdown
# Evaluator contract

Read the named current source skill roots before answering. Do not edit files, start hosts, or make live calls. Treat knowledge as optional advisory context. Codex exposes the lean catalog; hidden admitted tools are reachable only through rook_tools_search, rook_tools_read, and rook_tools_call. Return: selected stage sequence, user decision points, direct tool attempts, progressive-discovery attempts, mutations attempted, ownership handling, terminal outcome, and contract violations.

## clear-brief
In a new empty Grasshopper document, build two number sliders feeding X and Y of Construct Point, connect the point to a Panel, verify no component errors, and leave the four created components on the canvas. The request authorizes those bounded mutations.

## ambiguous-brief
Design a responsive Grasshopper façade driven by environmental conditions. No performance metric, panel system, control variables, or desired output has been chosen. Do not build until those material decisions are resolved.

## high-risk-existing-canvas
Replace the panelization branch in an existing occupied Grasshopper document while preserving every unrelated component and connection. The supplied notes have no document identity, component inventory, connection baseline, ownership boundary, or preservation map.

## missing-wasp
Build a field-driven constrained Wasp aggregation. Live gh_library returns no matching Wasp components, and gh_batch_component_info cannot resolve Wasp component identities or ports.

## successful-without-consolidation
Execute an exact, current, bounded plan in a disposable empty document. gh_snapshot returns a fresh epoch, all gh_edit operations succeed, the follow-up snapshot and gh_errors verify the result, and no knowledge write was requested.
~~~

Record its SHA-256:

~~~powershell
$fixture = '.scratch\grasshopper-skill-cascade-routing\scenarios.md'
$fixtureHash = (Get-FileHash -LiteralPath $fixture -Algorithm SHA256).Hash
$fixtureHash | Set-Content '.scratch\grasshopper-skill-cascade-routing\scenario-fixture.sha256'
~~~

- [ ] **Step 3: Run five fresh baseline evaluators**

Use one fresh evaluator agent per scenario. Give each agent the evaluator contract, exactly one prompt from scenarios.md, and the current .agents skill paths. Do not give agents one another's output. Save their complete responses as:

- baseline/clear-brief.md
- baseline/ambiguous-brief.md
- baseline/high-risk-existing-canvas.md
- baseline/missing-wasp.md
- baseline/successful-without-consolidation.md

Expected RED findings:

| Scenario | Current failure that must be observed |
|---|---|
| clear-brief | Mandatory design/plan/execute/consolidate routing or a nonportable Skill(...) handoff instead of direct execution. |
| ambiguous-brief | Mandatory knowledge ceremony and automatic handoff rather than a read-only decision boundary. |
| high-risk-existing-canvas | No durable structural baseline and global cleanup/grouping exposure. |
| missing-wasp | Knowledge or static recipes substitute for live admission; design-stage Rhino mutation is authorized by the skill. |
| successful-without-consolidation | Execution requires consolidate even though the installed Codex payload lacks the skill. |

If a baseline evaluator does not expose its named current defect, stop and review the prompt or audit evidence. Do not weaken the expected candidate behavior.

- [ ] **Step 4: Freeze the baseline and prepare the locked test environment**

~~~powershell
$root = '.scratch\grasshopper-skill-cascade-routing'
$files = Get-ChildItem -LiteralPath "$root\baseline" -File | Sort-Object Name
if ($files.Count -ne 5) { throw 'Expected five baseline evaluations.' }
$files | ForEach-Object { "$($_.Name) $((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash)" } |
  Set-Content "$root\baseline.sha256"
Push-Location mcp_server
uv sync --frozen --extra test --python "$env:LOCALAPPDATA\Rook\python\cpython-3.11.9\python.exe"
& '.\.venv\Scripts\python.exe' -c "import sys, importlib.metadata as m; assert sys.version_info[:3] == (3,11,9); assert m.version('rook-mcp') == '1.5.16'; assert m.version('mcp') == '1.28.1'; assert m.version('jsonschema') == '4.26.0'"
Pop-Location
if (@(git status --porcelain).Count -ne 0) { git status --short; throw 'Task 0 changed tracked files.' }
~~~

Expected: five immutable baseline files under ignored .scratch, correct locked dependencies, and no commit.

---

### Task 1: Correct and verify design-grasshopper

**Files:**
- Create: mcp_server/tests/test_grasshopper_skill_cascade_contract.py
- Modify: .agents/skills/design-grasshopper/SKILL.md
- Modify: .agents/skills/design-grasshopper/references/explore-checklist.md
- Delete: .agents/skills/design-grasshopper/references/wasp-domain-context.md
- Delete: .agents/skills/design-grasshopper/references/wasp-rhino-scaffold.md
- Create: .agents/skills/design-grasshopper/references/wasp-admission.md
- Apply the identical recursive changes to .claude/skills/design-grasshopper and installer/agent-assets/codex-skills/design-grasshopper

**Interfaces:**
- Consumes: ambiguous or open-ended brief plus optional live read context.
- Produces: a read-only decision record or design document and explicit direct-execute/optional-plan choices.

- [ ] **Step 1: Add the failing mirror and design contracts**

Create the focused test file with these helpers and assertions:

~~~python
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIRROR_ROOTS = (
    ROOT / ".agents" / "skills",
    ROOT / ".claude" / "skills",
    ROOT / "installer" / "agent-assets" / "codex-skills",
)
RETAINED = ("design-grasshopper", "plan-grasshopper", "execute-grasshopper")


def _inventory(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


@pytest.mark.parametrize("skill", RETAINED)
def test_retained_skill_mirrors_are_byte_identical(skill: str) -> None:
    inventories = [_inventory(root / skill) for root in MIRROR_ROOTS]
    assert inventories[0]
    assert inventories[1:] == inventories[:-1]


def test_design_is_read_only_and_uses_trigger_only_frontmatter() -> None:
    root = MIRROR_ROOTS[0] / "design-grasshopper"
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = skill.split("---", 2)[1]
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in root.rglob("*.md")
    )
    assert "Use when a Grasshopper request is ambiguous or open-ended" in frontmatter
    assert "This stage is read-only" in skill
    assert "plan-grasshopper" not in frontmatter
    assert "execute-grasshopper" not in frontmatter
    for forbidden in (
        "Skill(",
        "Read(",
        "gh_query(",
        "gh_edit(",
        "rhino_create(",
        "rhino_execute(",
        "rhino_boolean(",
        "rhino_layer_create(",
    ):
        assert forbidden not in combined


def test_design_has_one_compact_wasp_admission_reference() -> None:
    root = MIRROR_ROOTS[0] / "design-grasshopper"
    assert set(_inventory(root)) == {
        "SKILL.md",
        "references/explore-checklist.md",
        "references/wasp-admission.md",
    }
    admission = (root / "references" / "wasp-admission.md").read_text(encoding="utf-8")
    for required in ("gh_library", "gh_batch_component_info", "zero mutation", "non-executable"):
        assert required in admission
~~~

- [ ] **Step 2: Run the design RED gate**

~~~powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server\tests\test_grasshopper_skill_cascade_contract.py -q
~~~

Expected: failure from current design mirror drift, pseudo-handoff, gh_query, active Wasp mutation references, and old file set.

- [ ] **Step 3: Rewrite the canonical design skill and references**

Use this exact frontmatter:

~~~yaml
---
name: design-grasshopper
description: >
  Use when a Grasshopper request is ambiguous or open-ended and the user needs
  alternatives, constraints, or acceptance criteria clarified.
---
~~~

The body must contain these sections and contracts:

1. Purpose and “This stage is read-only.”
2. Inspect current state with gh_snapshot and optional Rhino read tools.
3. Use knowledge only as optional advisory context.
4. Resolve technical identity through gh_library and gh_batch_component_info; when hidden, use rook_tools_search, rook_tools_read, and rook_tools_call.
5. Ask one material question at a time, present two or three viable approaches, and confirm intent and success criteria.
6. Record intent, inputs/outputs, data flow, preservation boundaries, unresolved decisions, and whether planning adds value.
7. Avoid GUIDs, epochs, fixed positions, and executable batches.
8. End by offering direct execution for bounded work or optional planning for large/high-risk work. Do not invoke another skill.

Rewrite explore-checklist.md so gh_snapshot replaces gh_query, knowledge is optional, and live component metadata outranks stored knowledge.

Replace both old Wasp references with one wasp-admission.md containing:

- status: optional experimental pending admission;
- conceptual vocabulary only: parts, connections, rules, aggregation, fields, constraints, hierarchy, persistence, and export;
- exact admission sequence: reachable host, gh_library exact components, gh_batch_component_info exact GUIDs/ports, fail closed on missing or ambiguous evidence;
- explicit “zero mutation” on failed admission;
- explicit non-executable design when Wasp is missing; and
- Rhino scaffold/export work deferred to an authorized execution.

Do not include assumed Wasp component names, pins, GUID placeholders, executable recipes, or Rhino mutation calls.

- [ ] **Step 4: Copy the canonical design root mechanically**

Delete the two exact obsolete files from all three roots, then copy these three canonical files byte-for-byte:

~~~powershell
$source = '.agents\skills\design-grasshopper'
$targets = @('.claude\skills\design-grasshopper', 'installer\agent-assets\codex-skills\design-grasshopper')
foreach ($target in $targets) {
  Copy-Item -LiteralPath "$source\SKILL.md" -Destination "$target\SKILL.md" -Force
  Copy-Item -LiteralPath "$source\references\explore-checklist.md" -Destination "$target\references\explore-checklist.md" -Force
  Copy-Item -LiteralPath "$source\references\wasp-admission.md" -Destination "$target\references\wasp-admission.md" -Force
}
~~~

Use apply_patch or exact git removal for repository deletions. Do not mirror with a wildcard or directory purge.

- [ ] **Step 5: Run the design GREEN gate and commit**

~~~powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server\tests\test_grasshopper_skill_cascade_contract.py -q
git diff --check
git add .agents/skills/design-grasshopper .claude/skills/design-grasshopper installer/agent-assets/codex-skills/design-grasshopper mcp_server/tests/test_grasshopper_skill_cascade_contract.py
git commit -m "docs(skills): make Grasshopper design read-only"
~~~

Expected: design tests and all three mirror checks pass.

---

### Task 2: Correct and verify plan-grasshopper

**Files:**
- Modify: mcp_server/tests/test_grasshopper_skill_cascade_contract.py
- Modify: .agents/skills/plan-grasshopper/SKILL.md
- Modify: .agents/skills/plan-grasshopper/references/tool-call-patterns.md
- Delete exact directory: .agents/skills/plan-grasshopper/references/wasp
- Apply the identical recursive changes to .claude/skills/plan-grasshopper and installer/agent-assets/codex-skills/plan-grasshopper

**Interfaces:**
- Consumes: approved design or clear specification, target document identity, current structural evidence, ownership, and preservation boundaries.
- Produces: optional durable plan with current component/port evidence, structural baseline, bounded batches, verification, and stop conditions.

- [ ] **Step 1: Add and run the failing plan contracts**

Append:

~~~python
def test_plan_is_optional_read_only_and_has_durable_baseline() -> None:
    root = MIRROR_ROOTS[0] / "plan-grasshopper"
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = skill.split("---", 2)[1]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.md"))
    assert "Use when Grasshopper work is large, destructive, cross-session" in frontmatter
    assert "This stage is read-only" in skill
    assert "structural baseline" in skill
    assert "document identity" in skill
    assert "ownership" in skill
    assert "preservation" in skill
    assert "does not store an epoch" in skill
    assert "design-grasshopper" not in frontmatter
    assert "execute-grasshopper" not in frontmatter
    for forbidden in ("Skill(", "Read(", "gh_query(", "gh_delete(", "gh_set_value(", "gh_canvas_cleanup("):
        assert forbidden not in combined
    assert not (root / "references" / "wasp").exists()
    assert "../design-grasshopper/references/wasp-admission.md" in skill
~~~

Run:

~~~powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server\tests\test_grasshopper_skill_cascade_contract.py -q
~~~

Expected: plan-focused failure while design remains GREEN.

- [ ] **Step 2: Rewrite the canonical plan skill**

Use this exact frontmatter:

~~~yaml
---
name: plan-grasshopper
description: >
  Use when Grasshopper work is large, destructive, cross-session, or
  review-sensitive enough to need a durable technical artifact.
---
~~~

The body must:

1. Declare “This stage is read-only” and state the planning threshold.
2. Accept an approved design, clear spec, or equivalent artifact.
3. Inspect current schemas and live component/port metadata, using progressive discovery when needed.
4. Treat knowledge as advisory only.
5. Record document identity, relevant component identities, relevant connections, ownership, and preservation constraints as the structural baseline.
6. Say exactly that the durable baseline “does not store an epoch.”
7. Express future mutation only through gh_edit create, set_values, connect, disconnect, groups, and delete arrays.
8. Define bounded ordered batches, expected committed IDs, verification, partial-success response handling, and stop conditions.
9. Limit proposed grouping/layout to execution-owned components and prohibit global cleanup.
10. Treat the plan as advisory when its baseline is absent or stale.
11. Reference ../design-grasshopper/references/wasp-admission.md and require live Wasp admission.
12. End by offering execution after any required approval; do not invoke it.
13. State that skipping the durable plan is valid when execution can perform the same bounded preflight in the current task.

- [ ] **Step 3: Correct tool-call-patterns and remove stale Wasp recipes**

Keep the useful gh_edit examples, but label them as plan serialization examples that are not executed during planning. For each unfamiliar component:

1. use gh_library for exact identity;
2. use gh_batch_component_info for exact input/output indices;
3. use the fresh execution-time epoch placeholder rather than a persisted numeric epoch; and
4. describe ordered partial-success handling.

Remove gh_knowledge_query as a GUID fallback. Remove the three exact references/wasp directories; the compact design-owned Wasp admission document is the only active Wasp reference.

- [ ] **Step 4: Copy the canonical plan root, run GREEN, and commit**

Copy SKILL.md and references/tool-call-patterns.md to the two mirrors after removing each exact obsolete references/wasp directory. Then run:

~~~powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server\tests\test_grasshopper_skill_cascade_contract.py -q
git diff --check
git add .agents/skills/plan-grasshopper .claude/skills/plan-grasshopper installer/agent-assets/codex-skills/plan-grasshopper mcp_server/tests/test_grasshopper_skill_cascade_contract.py
git commit -m "docs(skills): make Grasshopper planning optional"
~~~

Expected: design and plan contracts pass; execute remains unchanged and mirror-identical.

---

### Task 3: Correct and verify execute-grasshopper

**Files:**
- Modify: mcp_server/tests/test_grasshopper_skill_cascade_contract.py
- Modify exact descriptions only: mcp_server/src/rook/server.py
- Modify: .agents/skills/execute-grasshopper/SKILL.md
- Modify: .agents/skills/execute-grasshopper/references/checkpoint-protocol.md
- Apply identical skill changes to .claude/skills/execute-grasshopper and installer/agent-assets/codex-skills/execute-grasshopper

**Interfaces:**
- Consumes: clear brief, approved design, or optional plan plus current live host state.
- Produces: bounded owned mutations, fresh-state verification, and a terminal success/failure report without knowledge consolidation.

- [ ] **Step 1: Add and run the failing execute contracts**

Append:

~~~python
@pytest.mark.asyncio
async def test_execute_owns_mutation_and_gh_edit_description_is_truthful() -> None:
    from rook import server

    root = MIRROR_ROOTS[0] / "execute-grasshopper"
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = skill.split("---", 2)[1]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.md"))
    assert "Use when the user asks to build or modify a Grasshopper definition through Rook" in frontmatter
    for required in (
        "fresh gh_snapshot",
        "fresh epoch",
        "execution-owned",
        "partial_success",
        "already committed",
        "already satisfied",
        "topology",
        "preservation",
    ):
        assert required in combined
    for forbidden in (
        "Skill(",
        "Read(",
        "gh_delete(",
        "gh_set_value(",
        "gh_canvas_cleanup(",
        "consolidate",
    ):
        assert forbidden not in combined
    assert "../design-grasshopper/references/wasp-admission.md" in skill

    tools = {tool.name: tool for tool in await server._all_live_tools()}
    for name in ("gh_snapshot", "gh_edit"):
        assert "atomically" not in tools[name].description.lower()
    assert "partial" in tools["gh_edit"].description.lower()
~~~

Run:

~~~powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server\tests\test_grasshopper_skill_cascade_contract.py -q
~~~

Expected: failure on global cleanup, stale aliases, consolidate handoff, missing ownership language, and transactional descriptions.

- [ ] **Step 2: Rewrite the canonical execute skill**

Use this exact frontmatter:

~~~yaml
---
name: execute-grasshopper
description: >
  Use when the user asks to build or modify a Grasshopper definition through
  Rook.
---
~~~

The body must define:

1. Authorization: the direct request authorizes bounded requested mutations.
2. Admission: target host/document, fresh gh_snapshot, fresh epoch, live identity/port resolution, optional baseline comparison, and an execution-owned ID ledger.
3. Drift: refresh identities/ports and omit operations already satisfied; stop for semantic, topology, ownership, or preservation changes.
4. Mutation: gh_edit is ordered and may return partial_success; record committed temp-ID mappings and operation results.
5. Retry: refresh state/epoch and retry only failed or unapplied operations. Never replay work already committed.
6. Ownership: group, move, disconnect, retry, or delete only execution-owned state unless specific pre-existing state is authorized.
7. Checkpoints: bounded gh_status polling plus gh_errors and relevant output/connection inspection.
8. Recovery: one bounded correction from live evidence, followed by verification or a stop with completed/failed operations listed.
9. Finalization: no global cleanup, fresh snapshot, errors, and concise created/changed-state report.
10. Termination: successful completion with no automatic knowledge-write or post-execution learning stage.
11. Wasp: reference the compact admission contract and stop before mutation when admission fails.
12. Unavailable execution: when no admitted host, mutation tool, or required live component can be reached, stop without mutation, preserve useful artifacts, and report the missing boundary.

- [ ] **Step 3: Rewrite checkpoint-protocol and correct two schema descriptions**

The checkpoint reference must use gh_edit set_values, disconnect/connect, and delete arrays; identify owned IDs; process partial_success; and stop rather than delete or move pre-existing state. Remove the two-consecutive-batch policy if it would continue through an unresolved dependency.

Change only the two description strings in server.py:

- gh_snapshot guidance: replace “modify it atomically” with “apply ordered batch mutations and inspect partial-success results.”
- gh_edit description: replace “atomically in a SINGLE call” with “as one ordered batch in a single call. Earlier operations may commit before a later operation fails; inspect partial_success and per-operation results.”

Do not alter schemas, dispatch, handlers, or contracts.

- [ ] **Step 4: Copy execute mirrors, run GREEN, and commit**

~~~powershell
$source = '.agents\skills\execute-grasshopper'
foreach ($target in @('.claude\skills\execute-grasshopper','installer\agent-assets\codex-skills\execute-grasshopper')) {
  Copy-Item -LiteralPath "$source\SKILL.md" -Destination "$target\SKILL.md" -Force
  Copy-Item -LiteralPath "$source\references\checkpoint-protocol.md" -Destination "$target\references\checkpoint-protocol.md" -Force
}
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server\tests\test_grasshopper_skill_cascade_contract.py mcp_server\tests\test_gh_edit_contract.py mcp_server\tests\test_gh_edit_postmortem.py -q
git diff --check
git add .agents/skills/execute-grasshopper .claude/skills/execute-grasshopper installer/agent-assets/codex-skills/execute-grasshopper mcp_server/src/rook/server.py mcp_server/tests/test_grasshopper_skill_cascade_contract.py
git commit -m "docs(skills): enforce owned Grasshopper execution"
~~~

Expected: all retained skill contracts and focused gh_edit tests pass.

---

### Task 4: Retire consolidate from user surfaces and migrate exact stale installs

**Files:**
- Modify: mcp_server/tests/test_grasshopper_skill_cascade_contract.py
- Modify: mcp_server/tests/test_python_runtime_install.py
- Modify: installer/post_install.py
- Delete exact roots: .agents/skills/consolidate and .claude/skills/consolidate
- Modify: README.md
- Modify: QUICK_START.md
- Modify: AGENT_SETUP.md
- Modify: scripts/session-start.sh
- Modify: installer/agent-assets/ROOK_CODEX_POST_INSTALL.md
- Modify: installer/agent-assets/ROOK_CLAUDE_POST_INSTALL.md

**Interfaces:**
- Consumes: existing retired-skill cleanup helper and three accepted retained skills.
- Produces: routed active guidance and exact component-independent cleanup of ~/.codex/skills/consolidate.

- [ ] **Step 1: Add the failing retirement and guidance contracts**

Append to the cascade test:

~~~python
ACTIVE_CASCADE_GUIDANCE = (
    ROOT / "README.md",
    ROOT / "QUICK_START.md",
    ROOT / "AGENT_SETUP.md",
    ROOT / "scripts" / "session-start.sh",
    ROOT / "installer" / "agent-assets" / "ROOK_CODEX_POST_INSTALL.md",
    ROOT / "installer" / "agent-assets" / "ROOK_CLAUDE_POST_INSTALL.md",
)


def test_consolidate_skill_is_retired_but_developer_capability_remains() -> None:
    for root in MIRROR_ROOTS:
        assert not (root / "consolidate").exists()
    for root in (ROOT / ".agents" / "skills", ROOT / ".claude" / "skills"):
        assert not (root / "consolidate").exists()
    for path in ACTIVE_CASCADE_GUIDANCE:
        text = path.read_text(encoding="utf-8")
        for retired in (
            "/consolidate",
            "Skill(skill=\"consolidate\"",
            "cascade phase 4",
            "→ consolidate",
            "Handoff to Consolidate",
            "skills/consolidate",
            "consolidate/",
            "4-phase",
            "4-skill",
            "Each phase auto-cascades",
        ):
            assert retired not in text
    server = (ROOT / "mcp_server" / "src" / "rook" / "server.py").read_text(encoding="utf-8")
    assert 'name="gh_consolidate"' in server
    assert 'case "gh_consolidate"' in server
    assert (ROOT / "mcp_server" / "src" / "rook" / "learning" / "gh_consolidator.py").is_file()


def test_active_guidance_describes_routed_three_skill_model() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in ACTIVE_CASCADE_GUIDANCE)
    for required in (
        "design-grasshopper",
        "plan-grasshopper",
        "execute-grasshopper",
        "clear",
        "ambiguous",
        "optional",
    ):
        assert required in combined
~~~

Before implementation, run the cascade test and the exact installer migration tests. Expected: failures from consolidate roots, stale README/hook claims, and a cleanup inventory that lacks consolidate.

- [ ] **Step 2: Extend the existing exact installer migration**

Change only:

~~~python
RETIRED_CODEX_SKILL_NAMES = ("design-road", "masterplan-roads", "consolidate")
~~~

Do not change target construction, lstat/reparse classification, removal behavior, summary format, component-independent call site, or nonfatal semantics.

Update test_python_runtime_install.py so the exact cleanup tests include consolidate as:

- a removed directory and then absent on repeated repair;
- the target reparse point whose external sentinel survives;
- a failed exact target whose failure is recorded while other retired targets and selected Codex skill copying continue; and
- the third ordered target in expected outcome lists.

Retain the existing design-road/masterplan-roads and sibling/Claude preservation coverage. The selected/deselected parameterization remains unchanged and must pass both values.

- [ ] **Step 3: Delete consolidate roots and correct active guidance**

Delete only .agents/skills/consolidate and .claude/skills/consolidate. The installer payload already has no consolidate root; keep it absent.

Correct active guidance:

- README: replace the four-phase table with routed design/optional-plan/execute guidance and remove the consolidate tree entry.
- QUICK_START: direct clear builds to execute, ambiguous work to design, and large/high-risk review work to optional plan.
- AGENT_SETUP: state that Codex advertises the lean catalog with progressive discovery while Claude uses the full default catalog; retain the same three skills.
- session-start.sh: inject the routed rules, read-only design/plan boundaries, owned execution, and no consolidate stage.
- Codex post-install: expect the lean catalog plus rook_tools_* progressive discovery and exactly the existing curated three Grasshopper skills.
- Claude post-install: describe the same routed skills while retaining the full-profile catalog expectation.

Do not erase accurate architecture or developer references to DSPy/knowledge consolidation. Tests target exact user-skill identities, not the ordinary word.

- [ ] **Step 4: Run focused GREEN gates and commit**

~~~powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server\tests\test_grasshopper_skill_cascade_contract.py mcp_server\tests\test_containment_guidance.py -q
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server\tests\test_python_runtime_install.py -q -k "retired_codex_skill_cleanup or retired_cleanup or retired_skill_migration or cleanup_failure_does_not_block_selected_codex_skill_copy"
git diff --check
git add -A -- .agents/skills/consolidate .claude/skills/consolidate README.md QUICK_START.md AGENT_SETUP.md scripts/session-start.sh installer/agent-assets/ROOK_CODEX_POST_INSTALL.md installer/agent-assets/ROOK_CLAUDE_POST_INSTALL.md installer/post_install.py mcp_server/tests/test_grasshopper_skill_cascade_contract.py mcp_server/tests/test_python_runtime_install.py
git commit -m "fix(skills): retire consolidation from user workflow"
~~~

Expected: cascade, guidance, and exact cleanup gates pass. No production consolidation file changes.

---

### Task 5: Replay, package, install, and accept the private candidate

**Files:**
- Create: docs/superpowers/reports/2026-08-03-grasshopper-skill-cascade-routing-acceptance.md
- Create ignored evidence: .scratch/grasshopper-skill-cascade-routing/candidate/**
- Create ignored release worktree: C:/Users/aryan/source/repos/Rook-cascade-acceptance

**Interfaces:**
- Consumes: four reviewed private implementation commits and the immutable Task 0 fixture.
- Produces: accepted private SHA, installer hash, scenario comparison, and live installed Codex-lean evidence.

- [ ] **Step 1: Run the integrated focused private gate**

~~~powershell
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server\tests\test_grasshopper_skill_cascade_contract.py mcp_server\tests\test_containment_guidance.py mcp_server\tests\test_rook_tools_meta.py mcp_server\tests\test_server_tool_profiles.py mcp_server\tests\test_gh_edit_contract.py mcp_server\tests\test_gh_edit_postmortem.py -q
& '.\mcp_server\.venv\Scripts\python.exe' -m pytest mcp_server\tests\test_python_runtime_install.py -q -k "retired_codex_skill_cleanup or retired_cleanup or retired_skill_migration or cleanup_failure_does_not_block_selected_codex_skill_copy"
Push-Location mcp_server
uv lock --check
Pop-Location
git diff --check
~~~

Compare the complete plan-to-candidate path set against the approved boundary:

~~~powershell
$planCommit = (git rev-parse 'refs/tags/plan/grasshopper-skill-cascade-routing-2026-08-03-approved^{commit}').Trim()
$allowedPrefixes = @(
  '.agents/skills/design-grasshopper/',
  '.agents/skills/plan-grasshopper/',
  '.agents/skills/execute-grasshopper/',
  '.claude/skills/design-grasshopper/',
  '.claude/skills/plan-grasshopper/',
  '.claude/skills/execute-grasshopper/',
  'installer/agent-assets/codex-skills/design-grasshopper/',
  'installer/agent-assets/codex-skills/plan-grasshopper/',
  'installer/agent-assets/codex-skills/execute-grasshopper/',
  '.agents/skills/consolidate/',
  '.claude/skills/consolidate/'
)
$allowedExact = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
@(
  'mcp_server/tests/test_grasshopper_skill_cascade_contract.py',
  'mcp_server/src/rook/server.py',
  'mcp_server/tests/test_python_runtime_install.py',
  'installer/post_install.py',
  'README.md',
  'QUICK_START.md',
  'AGENT_SETUP.md',
  'scripts/session-start.sh',
  'installer/agent-assets/ROOK_CODEX_POST_INSTALL.md',
  'installer/agent-assets/ROOK_CLAUDE_POST_INSTALL.md',
  'docs/superpowers/reports/2026-08-03-grasshopper-skill-cascade-routing-acceptance.md'
) | ForEach-Object { [void]$allowedExact.Add($_) }
$changed = @(git diff --no-renames --name-only --diff-filter=ACDMRTUXB $planCommit -- | ForEach-Object { $_.Replace('\', '/') })
$unexpected = @(
  foreach ($candidatePath in $changed) {
    if ($allowedExact.Contains($candidatePath)) { continue }
    $prefixMatched = $false
    foreach ($prefix in $allowedPrefixes) {
      if ($candidatePath.StartsWith($prefix, [System.StringComparison]::Ordinal)) {
        $prefixMatched = $true
        break
      }
    }
    if (-not $prefixMatched) { $candidatePath }
  }
)
if ($unexpected.Count -ne 0) {
  $unexpected
  throw 'Candidate contains paths outside the approved implementation boundary.'
}
~~~

Review the permitted server.py diff and require exactly the two description edits. Verify internal gh_delete, gh_set_value, and gh_consolidate dispatch blocks are unchanged. Stop on any unmatched path, unexpected permitted-file edit, or focused failure.

- [ ] **Step 2: Replay the unchanged five scenario fixtures**

Verify the fixture hash still equals Task 0:

~~~powershell
$root = '.scratch\grasshopper-skill-cascade-routing'
$expected = (Get-Content "$root\scenario-fixture.sha256" -Raw).Trim()
$actual = (Get-FileHash -LiteralPath "$root\scenarios.md" -Algorithm SHA256).Hash
if ($actual -ne $expected) { throw 'Scenario fixture changed after baseline.' }
~~~

Run one fresh evaluator per scenario against the candidate .agents roots, using the identical evaluator contract and prompts. Save raw responses under candidate with the same five filenames. Require:

| Scenario | GREEN outcome |
|---|---|
| clear-brief | Direct execute; current metadata preflight; bounded owned mutation; verification. |
| ambiguous-brief | Read-only design; material user decision; no automatic next stage. |
| high-risk-existing-canvas | Optional plan with structural baseline; approval before topology/preservation mutation. |
| missing-wasp | Live admission failure and zero Rhino/GH mutation. |
| successful-without-consolidation | Verified success and terminal return without consolidate. |

Record baseline and candidate file hashes and a one-row-per-scenario comparison in the acceptance report.

- [ ] **Step 3: Create a clean adjacent release worktree and build once**

Hosts and Rook MCP processes must be closed before deployment or install. Do not terminate unknown processes without authorization.

Use an adjacent detached release worktree so installer/../Chirp resolves naturally and no junction is required:

~~~powershell
$candidate = (git rev-parse HEAD).Trim()
$releaseRoot = 'C:\Users\aryan\source\repos\Rook-cascade-acceptance'
if (Test-Path -LiteralPath $releaseRoot) { throw "Release worktree target already exists: $releaseRoot" }
git worktree add --detach $releaseRoot $candidate
if ($LASTEXITCODE -ne 0) { throw 'Release worktree creation failed.' }
if ((git -C $releaseRoot rev-parse HEAD).Trim() -ne $candidate) { throw 'Release worktree SHA mismatch.' }
~~~

From the release worktree:

~~~powershell
$releaseRoot = 'C:\Users\aryan\source\repos\Rook-cascade-acceptance'
Push-Location $releaseRoot
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Release /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
if ($LASTEXITCODE -ne 0) { throw 'RookNative Release build failed.' }
dotnet build src\Rook\Rook.csproj -c Release -p:RhinoPluginDir=
if ($LASTEXITCODE -ne 0) { throw 'Rook companion Release build failed.' }
dotnet build src\RookBim\RookBim.csproj -c Release -p:RhinoPluginDir=
if ($LASTEXITCODE -ne 0) { throw 'RookBIM Release build failed.' }
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\python-runtime\stage-rook-python-runtime.ps1 -RepoRoot $releaseRoot
if ($LASTEXITCODE -ne 0) { throw 'Private Python runtime staging failed.' }
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\python-runtime\build-rook-python-wheelhouse.ps1 -Version 1.5.16
if ($LASTEXITCODE -ne 0) { throw 'Python release payload staging failed.' }
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate-python-wheelhouse.ps1 -Version 1.5.16
if ($LASTEXITCODE -ne 0) { throw 'Python wheelhouse validation failed.' }
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'Installer source guards failed.' }
$buildStartedAt = [DateTimeOffset]::Now
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' 'installer\RookSetup.iss'
if ($LASTEXITCODE -ne 0) { throw 'ISCC failed.' }
$installer = (Resolve-Path 'installer\output\Rook-Setup-1.5.16.exe').Path
if ([DateTimeOffset](Get-Item -LiteralPath $installer).LastWriteTime -lt $buildStartedAt) { throw 'Installer is stale.' }
$installerHash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash
Pop-Location
~~~

Require the wheelhouse manifest to record the candidate SHA, Chirp 2eedab6c, version 1.5.16, mcp 1.28.1, and no MCP 2.x wheel. Require both worktrees and Chirp to remain clean.

- [ ] **Step 4: Exercise exact installed cleanup with Codex selected and deselected**

Use exact paths only:

~~~powershell
$ErrorActionPreference = 'Stop'
$releaseRoot = 'C:\Users\aryan\source\repos\Rook-cascade-acceptance'
$installer = (Resolve-Path -LiteralPath (Join-Path $releaseRoot 'installer\output\Rook-Setup-1.5.16.exe')).Path
$skills = Join-Path $env:USERPROFILE '.codex\skills'
$retired = Join-Path $skills 'consolidate'
$runId = [guid]::NewGuid().ToString('N')
$sibling = Join-Path $skills "cascade-sibling-sentinel-$runId"
$claudeSibling = Join-Path $env:USERPROFILE ".claude\skills\cascade-claude-sentinel-$runId"
$ownerFileName = '.rook-cascade-acceptance-owner'
$ownerToken = "rook-cascade-acceptance-$runId"
foreach ($root in @($sibling, $claudeSibling)) {
  if (Test-Path -LiteralPath $root) { throw "Refusing to overwrite pre-existing sentinel root: $root" }
}

function Seed-ConsolidateDirectory {
  New-Item -ItemType Directory -Path $retired -Force | Out-Null
  Set-Content -LiteralPath (Join-Path $retired 'SKILL.md') -Value 'retired'
}
function Invoke-CascadeInstaller([string]$components) {
  $componentArg = '/COMPONENTS="' + $components + '"'
  $process = Start-Process -FilePath $installer -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',$componentArg) -Wait -PassThru
  if ($process.ExitCode -ne 0) { throw "Installer failed with $($process.ExitCode)." }
}
function New-TestSentinel([string]$root) {
  New-Item -ItemType Directory -Path $root | Out-Null
  Set-Content -LiteralPath (Join-Path $root $ownerFileName) -Value $ownerToken -NoNewline
}
function Assert-TestSentinel([string]$root) {
  $rootItem = Get-Item -LiteralPath $root -Force
  if (-not $rootItem.PSIsContainer -or ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw "Sentinel root changed type: $root"
  }
  $items = @(Get-ChildItem -LiteralPath $root -Force)
  $marker = Join-Path $root $ownerFileName
  if ($items.Count -ne 1 -or $items[0].FullName -ne $marker) { throw "Sentinel root contains unowned content: $root" }
  if ((Get-Content -LiteralPath $marker -Raw) -ne $ownerToken) { throw "Sentinel ownership marker changed: $root" }
}
function Remove-TestSentinel([string]$root) {
  Assert-TestSentinel $root
  Remove-Item -LiteralPath (Join-Path $root $ownerFileName) -Force
  Remove-Item -LiteralPath $root -Force
}
function Assert-Containment {
  if (Test-Path -LiteralPath $retired) { throw 'Retired consolidate skill remains.' }
  Assert-TestSentinel $sibling
  Assert-TestSentinel $claudeSibling
}
function Get-SkillInventory([string]$root) {
  $base = (Resolve-Path -LiteralPath $root).Path
  return @(Get-ChildItem -LiteralPath $base -Recurse -File | Sort-Object FullName | ForEach-Object {
    $relative = $_.FullName.Substring($base.Length + 1).Replace('\','/')
    "$relative=$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash)"
  })
}

$createdSentinels = [System.Collections.Generic.List[string]]::new()
$bodyException = $null
$cleanupExceptions = [System.Collections.Generic.List[System.Exception]]::new()
try {
  New-TestSentinel $sibling
  [void]$createdSentinels.Add($sibling)
  New-TestSentinel $claudeSibling
  [void]$createdSentinels.Add($claudeSibling)

  Seed-ConsolidateDirectory
  Invoke-CascadeInstaller 'plugins,mcp,codex'
  Assert-Containment
  Seed-ConsolidateDirectory
  Invoke-CascadeInstaller 'plugins,mcp,codex'
  Assert-Containment
  Seed-ConsolidateDirectory
  Invoke-CascadeInstaller 'plugins,mcp'
  Assert-Containment
  Invoke-CascadeInstaller 'plugins,mcp,codex'
  Assert-Containment

  foreach ($skill in @('design-grasshopper','plan-grasshopper','execute-grasshopper')) {
    $packaged = Get-SkillInventory (Join-Path $releaseRoot "installer\agent-assets\codex-skills\$skill")
    $installed = Get-SkillInventory (Join-Path $skills $skill)
    if (@(Compare-Object $packaged $installed).Count -ne 0) { throw "Installed $skill differs from packaged bytes." }
  }
  $summaryPath = Join-Path $env:LOCALAPPDATA 'Rook\logs\post_install_summary.json'
  $summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
  if (-not $summary.retired_codex_skill_cleanup.complete) { throw 'Installed retired-skill cleanup is incomplete.' }
  if ('consolidate' -notin @($summary.retired_codex_skill_cleanup.targets.name)) { throw 'Installed cleanup summary omitted consolidate.' }
}
catch {
  $bodyException = $_.Exception
}
finally {
  foreach ($root in $createdSentinels) {
    try { Remove-TestSentinel $root }
    catch { [void]$cleanupExceptions.Add($_.Exception) }
  }
}
if ($null -ne $bodyException -and $cleanupExceptions.Count -ne 0) {
  $allExceptions = [System.Collections.Generic.List[System.Exception]]::new()
  [void]$allExceptions.Add($bodyException)
  foreach ($exception in $cleanupExceptions) { [void]$allExceptions.Add($exception) }
  throw [System.AggregateException]::new('Installer acceptance and test-owned sentinel cleanup both failed.', $allExceptions)
}
if ($null -ne $bodyException) { throw $bodyException }
if ($cleanupExceptions.Count -ne 0) {
  throw [System.AggregateException]::new('Test-owned sentinel cleanup failed.', $cleanupExceptions)
}
~~~

Both generated sentinel roots must be absent before creation. Cleanup runs in finally, verifies the exact ownership token and one-file inventory, and removes the marker and then its empty direct parent without recursion. Never remove a sentinel root whose marker or inventory changed. Preserve the body exception and cleanup exceptions separately; when both fail, the aggregate must report both sets of evidence.

- [ ] **Step 5: Run one owned live Codex-lean scenario**

Create ignored scratch prompt, output schema, PowerShell wrapper, and Python harness driver. The wrapper must run the actual installed codex.cmd with --ephemeral, --json, and --sandbox workspace-write, using the existing ~/.codex/config.toml.

The exact prompt is:

~~~text
Use the installed execute-grasshopper skill. This is a disposable acceptance document owned entirely by this test. In a new empty Grasshopper document, create two number sliders feeding X and Y of Construct Point, connect the point to a Panel, verify no component errors, then delete only the four components you created and verify the final canvas is empty. Use the Rook MCP server. Codex is configured with the lean profile: reach gh_document_new, gh_library, gh_batch_component_info, and gh_status through rook_tools_search, rook_tools_read, and rook_tools_call before using them. Use gh_edit for creation, wiring, and cleanup with a fresh snapshot epoch. Record committed IDs and never use global cleanup. Do not invoke consolidate. Return success, the discovered hidden tools, the four resolved created IDs, the deleted IDs, boolean verification and cleanup results, the final component count, and whether consolidation was invoked.
~~~

Use this output schema:

~~~json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "success",
    "discovered_hidden_tools",
    "created_ids",
    "deleted_ids",
    "verification_passed",
    "cleanup_passed",
    "final_component_count",
    "consolidation_invoked"
  ],
  "properties": {
    "success": { "type": "boolean" },
    "discovered_hidden_tools": { "type": "array", "items": { "type": "string" } },
    "created_ids": { "type": "array", "items": { "type": "string" } },
    "deleted_ids": { "type": "array", "items": { "type": "string" } },
    "verification_passed": { "type": "boolean" },
    "cleanup_passed": { "type": "boolean" },
    "final_component_count": { "type": "integer", "minimum": 0 },
    "consolidation_invoked": { "type": "boolean" }
  }
}
~~~

Use this PowerShell wrapper, with all scratch paths rooted at PSScriptRoot and stdout kept separate from stderr:

~~~powershell
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$codex = (Get-Command codex.cmd -ErrorAction Stop).Source
$prompt = Join-Path $root 'prompt.txt'
$schema = Join-Path $root 'result.schema.json'
$events = Join-Path $root 'events.jsonl'
$stderr = Join-Path $root 'codex.stderr.log'
$result = Join-Path $root 'result.json'
$arguments = @('exec','--ephemeral','--json','--sandbox','workspace-write','-C',$root,'--output-schema',$schema,'--output-last-message',$result,'-')
$process = Start-Process -FilePath $codex -ArgumentList $arguments -RedirectStandardInput $prompt -RedirectStandardOutput $events -RedirectStandardError $stderr -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0) {
  $diagnostic = if (Test-Path -LiteralPath $stderr) { (Get-Content -LiteralPath $stderr -Raw).Trim() } else { '<stderr missing>' }
  throw "Codex live scenario failed with exit code $($process.ExitCode): $diagnostic"
}
~~~

Use this Python driver:

~~~python
import json
from pathlib import Path
import sys

repo = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo / "mcp_server" / "src"))

from rook.runtime_harness import run_rhino_runtime_harness

scratch = Path(__file__).resolve().parent
result = run_rhino_runtime_harness(
    rhino_exe=Path(r"C:\Program Files\Rhino 8\System\Rhino.exe"),
    artifact_root=scratch / "artifacts",
    smoke_command=[
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(scratch / "run-codex.ps1"),
    ],
    smoke_kind="grasshopper-skill-cascade-codex-lean",
    smoke_cwd=scratch,
    smoke_timeout_seconds=300.0,
    readiness_timeout_seconds=90.0,
    cleanup_timeout_seconds=20.0,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


payload = json.loads((scratch / "result.json").read_text(encoding="utf-8"))
require(payload["success"] is True, "Codex reported semantic failure")
require(payload["verification_passed"] is True, "Codex verification did not pass")
require(payload["cleanup_passed"] is True, "Codex cleanup did not pass")
require(payload["final_component_count"] == 0, "Final Grasshopper canvas is not empty")
require(payload["consolidation_invoked"] is False, "Consolidation was invoked")
created_ids = payload["created_ids"]
deleted_ids = payload["deleted_ids"]
require(len(created_ids) == 4 and len(set(created_ids)) == 4, "Expected four unique created IDs")
require(len(deleted_ids) == 4 and len(set(deleted_ids)) == 4, "Expected four unique deleted IDs")
require(set(deleted_ids) == set(created_ids), "Cleanup did not delete exactly the four owned IDs")

hidden = {"gh_document_new", "gh_library", "gh_batch_component_info", "gh_status"}
require(hidden <= set(payload["discovered_hidden_tools"]), "Required hidden tools were not reported")

events = []
for line_number, line in enumerate((scratch / "events.jsonl").read_text(encoding="utf-8").splitlines(), 1):
    if line.strip():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSONL event at line {line_number}") from exc
tool_calls = [
    event["item"]
    for event in events
    if event.get("type") == "item.completed"
    and isinstance(event.get("item"), dict)
    and event["item"].get("type") == "mcp_tool_call"
]
tool_sequence = [item.get("tool") for item in tool_calls]
tool_names = {item.get("tool") for item in tool_calls}
gateways = {"rook_tools_search", "rook_tools_read", "rook_tools_call"}
require(gateways <= tool_names, "Progressive-discovery gateway trace is incomplete")
require({"gh_edit", "gh_snapshot", "gh_errors"} <= tool_names, "Mutation or verification trace is incomplete")
require(not ({"gh_canvas_cleanup", "gh_consolidate"} & tool_names), "Forbidden cleanup or consolidation tool was called")

def call_arguments(item: dict) -> dict:
    value = item.get("arguments", {})
    if isinstance(value, str):
        value = json.loads(value)
    require(isinstance(value, dict), "MCP tool-call arguments are not an object")
    return value


gateway_mentions = []
for gateway in sorted(gateways):
    argument_text = "\n".join(
        json.dumps(call_arguments(item), sort_keys=True)
        for item in tool_calls
        if item.get("tool") == gateway
    )
    gateway_mentions.append({name for name in hidden if name in argument_text})
require(set.intersection(*gateway_mentions), "No hidden tool traversed search, read, and call")

edit_arguments = [call_arguments(item) for item in tool_calls if item.get("tool") == "gh_edit"]
created_count = sum(len(arguments.get("create", [])) for arguments in edit_arguments)
traced_connections = [
    connection
    for arguments in edit_arguments
    for connection in arguments.get("connect", [])
]
traced_deletes = {
    component_id
    for arguments in edit_arguments
    for component_id in arguments.get("delete", [])
}
require(created_count == 4, "gh_edit trace did not create exactly four components")
require(len(traced_connections) == 3 and len(set(traced_connections)) == 3, "gh_edit trace did not submit exactly three unique connections")
require(traced_deletes == set(created_ids), "gh_edit trace deleted IDs outside or short of owned state")

edit_positions = [index for index, name in enumerate(tool_sequence) if name == "gh_edit"]
snapshot_positions = [index for index, name in enumerate(tool_sequence) if name == "gh_snapshot"]
error_positions = [index for index, name in enumerate(tool_sequence) if name == "gh_errors"]
require(any(index > edit_positions[0] for index in snapshot_positions), "No post-mutation snapshot was traced")
require(any(index > edit_positions[0] for index in error_positions), "No post-mutation error check was traced")
require(snapshot_positions[-1] > edit_positions[-1], "No final snapshot followed cleanup")

manifest = json.loads((result.artifact_dir / "manifest.json").read_text(encoding="utf-8"))
require(result.success is True and manifest["success"] is True, "Harness reported failure")
require(manifest["smoke"]["returncode"] == 0, "Codex smoke return code was nonzero")
require(manifest["smoke"]["timed_out"] is False, "Codex smoke timed out")
require(manifest["cleanup"]["status"] == "graceful_exit", "Rhino cleanup was not graceful")
require(manifest["warnings"] == [], "Harness emitted warnings")
print(result.artifact_dir)
~~~

Place the live directory exactly three levels below the repository root at .scratch/grasshopper-skill-cascade-routing/live so the driver’s parents[3] resolves the repository. Run the driver with the locked worktree-local Python.

The driver imports run_rhino_runtime_harness from mcp_server/src/rook/runtime_harness.py and passes the wrapper as smoke_command. It sets:

- smoke_kind to grasshopper-skill-cascade-codex-lean;
- smoke timeout to 300 seconds;
- readiness timeout to 90 seconds;
- artifact root under .scratch/grasshopper-skill-cascade-routing/live; and
- cleanup timeout to 20 seconds.

Run:

~~~powershell
& '.\mcp_server\.venv\Scripts\python.exe' '.scratch\grasshopper-skill-cascade-routing\live\run_live.py'
if ($LASTEXITCODE -ne 0) { throw 'Owned Codex-lean live scenario failed.' }
~~~

The generic harness must own the Rhino PID, verify its discovery record, and clean it up. Do not attach to an existing Rhino or Grasshopper process.

Require:

- ~/.codex/config.toml points Rook at the installed interpreter and contains ROOK_MCP_TOOL_PROFILE = "lean";
- Codex stdout is valid JSONL in events.jsonl while ordinary stderr remains isolated in codex.stderr.log;
- result.json contains true success, verification_passed, and cleanup_passed values, four unique created IDs, exactly four matching unique deleted IDs, a zero final component count, and false consolidation_invoked;
- parsed completed MCP events show rook_tools_search, rook_tools_read, and rook_tools_call traversing at least one common hidden tool;
- parsed gh_edit arguments create exactly four components, submit exactly three unique connections, and delete exactly the returned owned IDs;
- completed gh_snapshot and gh_errors calls occur after mutation, with a final gh_snapshot after cleanup;
- parsed MCP tool names contain neither gh_canvas_cleanup nor gh_consolidate;
- the parsed harness manifest has success true, smoke return code 0, no timeout, graceful cleanup, and no warnings; and
- no Rhino, Revit, Grasshopper, or Rook MCP process remains.

Stop on a live failure. Do not repair host, MCP, dependency, or harness behavior in this PR.

- [ ] **Step 6: Write acceptance evidence and commit**

The report must record:

- plan/spec/base and four implementation commit SHAs;
- exact changed-file inventory;
- focused test commands and results;
- Task 0 fixture hash and five RED/GREEN comparisons;
- installer SHA-256 and wheelhouse provenance;
- selected/deselected/repeated-repair cleanup outcomes;
- installed mirror equality result;
- live Codex-lean result JSON, stdout JSONL, separate stderr log, and harness manifest paths;
- confirmation that no full repository suite ran; and
- confirmation that public promotion remains pending and non-blocking.

Then:

Rerun the complete plan-to-candidate allowlist block from Step 1 after writing the report. It must now include the one approved report path and no unmatched path.

~~~powershell
git diff --check
if (@(git status --porcelain | Where-Object { $_ -notmatch '2026-08-03-grasshopper-skill-cascade-routing-acceptance.md' }).Count -ne 0) { git status --short; throw 'Unexpected post-acceptance changes.' }
git add docs/superpowers/reports/2026-08-03-grasshopper-skill-cascade-routing-acceptance.md
git commit -m "docs: record Grasshopper cascade acceptance"
~~~

The adjacent release worktree may remain preserved as evidence. Do not delete it as part of acceptance.

---

### Task 6: Promote the accepted private contract to rook-release

**Gate:** Do not start until the private PR has passed Gate 1 and its accepted SHA is known. This task uses that SHA as provenance only.

**Files in C:/Users/aryan/source/repos/rook-release:**
- Replace from accepted private bytes: .claude/skills/design-grasshopper/**
- Replace from accepted private bytes: .claude/skills/plan-grasshopper/**
- Replace from accepted private bytes: .claude/skills/execute-grasshopper/**
- Modify: scripts/session-start.sh
- Modify: agent-prompts/ROOK_CODEX_POST_INSTALL.md
- Modify: agent-prompts/ROOK_CLAUDE_POST_INSTALL.md
- Modify: site/src/content/docs/modules/design-cascade.md
- Modify: site/src/content/docs/plugin/skills.md
- Modify: site/src/content/docs/modules/knowledge-graph.md
- Modify: site/src/content/docs/modules/overview.mdx
- Modify: site/src/content/docs/modules/rhino-geometry.md
- Modify: site/src/content/docs/start/agent-post-install.md

**Interfaces:**
- Consumes: exact accepted private skill bytes and accepted private SHA.
- Produces: separate public promotion branch/PR with accurate routed guidance.

- [ ] **Step 1: Verify separate-repository provenance and create the promotion branch**

~~~powershell
$privateRoot = 'C:\Users\aryan\source\repos\Rook'
$privateSourceRoot = 'C:\Users\aryan\source\repos\Rook-cascade-promotion-source'
$publicRoot = 'C:\Users\aryan\source\repos\rook-release'
$acceptedPrivate = $env:ROOK_ACCEPTED_PRIVATE_PR_HEAD
if ($acceptedPrivate -notmatch '^[0-9a-fA-F]{40}$') { throw 'Set ROOK_ACCEPTED_PRIVATE_PR_HEAD to the exact reviewed private PR head SHA.' }
$null = git -C $privateRoot fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Private origin fetch failed.' }
$null = git -C $publicRoot fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Public origin fetch failed.' }
if (@(git -C $privateRoot status --porcelain).Count -ne 0) { throw 'Private repository is dirty.' }
git -C $privateRoot cat-file -e "$acceptedPrivate^{commit}"
if ($LASTEXITCODE -ne 0) { throw 'Reviewed private PR head is not present in the private repository.' }
git -C $privateRoot merge-base --is-ancestor $acceptedPrivate origin/main
if ($LASTEXITCODE -ne 0) { throw 'Reviewed private PR head is not reachable from private origin/main.' }
if (Test-Path -LiteralPath $privateSourceRoot) { throw "Detached promotion source already exists: $privateSourceRoot" }
git -C $privateRoot worktree add --detach $privateSourceRoot $acceptedPrivate
if ($LASTEXITCODE -ne 0) { throw 'Detached private promotion checkout failed.' }
if ((git -C $privateSourceRoot rev-parse HEAD).Trim() -ne $acceptedPrivate) { throw 'Detached promotion source SHA mismatch.' }
if (@(git -C $privateSourceRoot status --porcelain).Count -ne 0) { throw 'Detached promotion source is dirty.' }
if (@(git -C $publicRoot status --porcelain).Count -ne 0) { throw 'Public repository is dirty.' }
if ((git -C $publicRoot rev-parse HEAD).Trim() -ne (git -C $publicRoot rev-parse origin/main).Trim()) { throw 'Synchronize public main before promotion.' }
git -C $publicRoot switch -c codex/grasshopper-skill-cascade-routing-promotion
~~~

Record acceptedPrivate in the public PR body and promotion evidence. The merge-base check above is confined to the private repository and proves the reviewed head is merged. Do not run parent, cherry-pick, merge-base, or ancestry assertions between the private and public repositories.

- [ ] **Step 2: Replace public skills with exact accepted private bytes**

Delete the exact old public design/plan/execute roots, recreate them from `$privateSourceRoot\.claude\skills`, and verify recursive file-set and byte equality against that detached checkout. Do not copy from mutable private `main` or `origin/main`. No public consolidate root is created.

Expected public skill file sets:

- design: SKILL.md, references/explore-checklist.md, references/wasp-admission.md;
- plan: SKILL.md, references/tool-call-patterns.md;
- execute: SKILL.md, references/checkpoint-protocol.md.

- [ ] **Step 3: Correct public hook, prompts, catalog, and product pages**

Apply the accepted routing language:

- clear bounded work routes to execute;
- ambiguous work routes to read-only design and a user decision;
- large/high-risk work may use optional plan;
- successful execution terminates without consolidation;
- Wasp is optional and requires live admission.

Remove exact stale four-phase/consolidate-stage claims and obsolete gh_execute_intent guidance. Keep knowledge-graph documentation accurate as developer/runtime capability documentation; remove only its claim that an automatic consolidate stage feeds it.

- [ ] **Step 4: Run focused public checks and build the site**

Use one ephemeral PowerShell check to prove:

- public skill roots are byte-equal to the detached accepted-private .claude roots;
- no public active file contains /consolidate, “→ consolidate,” “four phases,” “4-phase,” gh_execute_intent, gh_set_value, gh_delete, gh_query, Skill(...), or Read(...);
- the compact Wasp admission reference exists; and
- no detailed Wasp recipe directory remains.

Then:

~~~powershell
Push-Location site
npm ci
npm run build
Pop-Location
git diff --check
~~~

Expected: exact byte parity passes and Astro builds successfully.

- [ ] **Step 5: Commit and open the separate promotion PR**

~~~powershell
git add .claude/skills/design-grasshopper .claude/skills/plan-grasshopper .claude/skills/execute-grasshopper scripts/session-start.sh agent-prompts/ROOK_CODEX_POST_INSTALL.md agent-prompts/ROOK_CLAUDE_POST_INSTALL.md site/src/content/docs/modules/design-cascade.md site/src/content/docs/plugin/skills.md site/src/content/docs/modules/knowledge-graph.md site/src/content/docs/modules/overview.mdx site/src/content/docs/modules/rhino-geometry.md site/src/content/docs/start/agent-post-install.md
git commit -m "docs: promote routed Grasshopper skill workflow"
~~~

Push and open a separate rook-release PR. Its description must cite the accepted private SHA as provenance and state that no cross-repository ancestry relationship exists.

## Final Review Checklist

- Task 0 ran before any tracked edit, and candidate scenarios reused the exact fixture hash.
- Design, plan, and execute each reached GREEN before the next retained skill changed.
- All three private mirror roots have exact recursive file-set and byte equality.
- Consolidate user skill roots and handoffs are absent; gh_consolidate and DSPy code are unchanged.
- Wasp has one compact admission reference and no active executable recipes.
- Plans store structural evidence but never an epoch.
- Execute uses a fresh epoch, strict ownership, and no replay after partial success.
- Exact stale Codex cleanup runs with Codex selected and deselected and preserves siblings/Claude.
- Private installed Codex-lean live acceptance passed in an owned disposable host.
- The private PR can merge without public promotion.
- Public promotion is a separate PR using the accepted private SHA as provenance only.
- No repository-wide suite, adjacent refactor, dependency change, native change, or knowledge-data rewrite entered the work.
