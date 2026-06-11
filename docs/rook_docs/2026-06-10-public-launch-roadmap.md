# Public Launch Roadmap: June 14-15, 2026

Date: 2026-06-10
Status: Working roadmap for same-day iteration
Target public push: Sunday night 2026-06-14 or Monday morning 2026-06-15

## Purpose

Rook is now public through `rook-release`, but the broader public launch still
needs a clear story, a stable installer path, and at least one immediately
playable feature that makes the product feel alive.

This document captures the launch decision frame as of Wednesday 2026-06-10.
It is meant to be revised throughout the day as implementation, smoke testing,
and media capture clarify what can safely ship.

## Current Posture

The public `rook-release` repository is clean and already contains the earlier
public-readiness fixes:

- real install page
- post-install prompts for Claude and Codex
- curated 11-skill public plugin story
- `v1.5.10` release visible as the latest public release
- no open `rook-release` issues found during the scan

Release smoke status:

- The `v1.5.10` public installer was smoke-tested on the testing laptop on
  2026-06-09, and the reported result was that the release install was in order.
- Treat that as the current release confidence baseline unless a later check
  finds a regression.
- The remaining docs task is to preserve the smoke evidence in a durable note:
  installer asset, machine/date, major surfaces checked, and any skipped items.

The private Rook repo has uncommitted installer/post-install work in progress:

- `installer/RookSetup.iss`
- `installer/post_install.py`
- `scripts/tests/release-installer-guards.tests.ps1`
- untracked `docs/superpowers/specs/2026-06-08-pre-release-runtime-smoke-notes.md`
- untracked `mcp_server/tests/test_post_install.py`

Those changes are not automatically part of the public `v1.5.10` artifact. They
should be treated as next hardening unless the installer is rebuilt and
re-smoked. In particular, the current dirty installer edits appear to improve
first-time dependency-install visibility and timeout behavior; they do not mean
the already-published `v1.5.10` installer is invalidated.

Private/public alignment summary:

- `rook-release` is the public docs/plugin/release-asset surface.
- private `Rook` remains the source/build/release pipeline surface.
- The repos are aligned if the public docs describe the released artifact
  honestly and the private repo records which local changes are future
  hardening rather than already-shipped behavior.
- The stale issue to fix now is documentation wording, not necessarily a broken
  release artifact.

## Launch Goal

The launch should do three things:

1. Prove a normal user can install Rook and connect an agent without source-repo
   knowledge.
2. Give the first-session user something visible and memorable to try.
3. Avoid overclaiming features that are not stable enough for public testing.

The current leading "wow" candidates are:

- Director video from live Rhino model state.
- RookBIM workflow that produces a useful coordination deliverable, not merely
  selection.

The secondary candidates are:

- 2D-to-3D / Hunyuan-style mesh generation.
- RookSplat / mesh-to-splat conversion.
- North-star topology / multi-file recomposition.

Those secondary candidates are important, but they are less likely to be the
right launch-week bet unless quick validation proves they are already closer
than the docs scan suggests.

## Launch Lanes

### Lane 1: Release Foundation

This lane is non-negotiable.

Required outcomes:

- installer and post-install behavior are stable
- release validation passes or is already represented by the 2026-06-09 testing
  laptop smoke evidence
- public docs build
- plugin install path works
- user-facing install/update guidance is precise
- stale-session guidance is explicit until hot recovery is implemented

Known risks:

- long-lived MCP sessions can remain stale after install/update repair
  (`bringfire/Rook#187`)
- `_ShowRookChat` through generic `/command` can report a false-negative failure
  (`bringfire/Rook#188`)
- autonomous Rhino launch still has a weak bare-`Popen([Rhino.exe])` path
  (`bringfire/Rook#222`)

Launch posture:

- #187 can be mitigated in docs by saying directly: after install or update,
  restart Claude, Codex, or other MCP clients before judging Rook connectivity.
- #188 should be fixed or avoided in smoke scripts by using a dedicated health
  path instead of treating generic `/command` as proof.
- #222 is important for north-star workbench autonomy, but it should not block
  this launch if the public story uses already-running Rhino.

### Lane 2: Director Video Wow

This is the strongest near-term splash candidate.

Why it fits the launch:

- The deterministic frame spine is already done.
- Timeline authoring is already done.
- Native Windows MP4 assembly is already done.
- The next slice, `curve_follow_target`, has a concrete implementation plan.
- The demo is easy to understand: a model becomes a film.

Public demo story:

> "Follow this camera path, hold focus on the object, render the frames, and
> assemble an MP4."

Minimum compelling workflow:

1. User opens a Rhino model with a named object or visible design target.
2. Rook creates or uses a curve as the camera path.
3. Rook runs Director with a fixed target point and timeline.
4. Rook captures frames without leaving the Rhino document mutated.
5. Rook assembles a local MP4.
6. Docs show the resulting video and the prompt that created it.

Launch acceptance:

- `curve_follow_target` works in focused non-live tests.
- A live Rhino smoke produces a short MP4 from an actual model.
- The demo command is simple enough to paste into Claude or Codex.
- The generated MP4 is included in docs or release media.
- If `curve_follow_target` is not ready by 2026-06-12, fall back to keyframed
  Director video using named views rather than forcing the new slice.

What not to do before launch:

- do not add artifact/gallery publishing as part of the same slice
- do not change native frame-capture semantics
- do not add a broad video editor or GH NLE
- do not depend on autonomous Workbench launch

### Lane 3: RookBIM Workflow That Goes Beyond Selection

RookBIM cannot be presented as "select some elements" and stop. Selection is
only the evidence handle. The workflow needs to end with a useful coordination
artifact or decision aid.

Launch-grade RookBIM story:

> "Ask the live Revit model a coordination question, gather exact element
> evidence, select the affected elements, and produce a small audit packet the
> user can act on."

The first public RookBIM workflow should remain read-oriented unless a write path
is already proven. It can still feel complete if it produces a deliverable.

Candidate workflow A: Parameter completeness audit

Prompt:

```text
Find doors in the active Revit view with missing Mark, Fire Rating, or hardware
set parameters. Select the affected elements and give me a grouped audit summary
with element ids, type names, and missing fields.
```

End state:

- selected exact elements in Revit
- grouped markdown or JSON audit summary
- counts by missing parameter
- top example elements with stable identity
- suggested next action for the BIM manager

Why this is better than selection:

- selection shows evidence
- the audit packet is the deliverable
- the user can immediately verify and act

Candidate workflow B: Category inventory and model orientation

Prompt:

```text
List the available Revit categories in this document, identify the major model
categories in the active view, then inspect the largest or most relevant category
and summarize what kinds of elements are present.
```

End state:

- model inventory
- representative elements selected
- element/type/parameter evidence
- quick "what is in this file?" report

This is safer than parameter audit but less splashy.

Candidate workflow C: Issue-ready coordination packet

Prompt:

```text
Find walls in the active view whose fire rating parameter is empty. Select them,
summarize the affected wall types, and write a concise issue report I can paste
into the project tracker.
```

End state:

- selected exact elements
- issue-ready prose
- evidence table
- recommended assignee/question

This may be the best public demo because it clearly turns BIM query into work
product.

Launch acceptance:

- RookBIM tools work in RhinoInside/Revit on the local machine.
- `rookbim_status` reports available host evidence.
- `rookbim_list_categories` or equivalent runtime category listing works.
- `rookbim_query_elements` can run against active view or document scope.
- parameter inspection returns useful display/raw evidence.
- selection works for returned identities.
- at least one complete audit/report prompt has a captured screenshot or short
  screen recording.

What not to do before launch:

- do not add write transactions unless the path is already proven and bounded
- do not claim broad Revit authoring
- do not depend on Grasshopper canvas state for the core RookBIM demo
- do not make linked model support part of the public first impression unless it
  is already live-proven

### Lane 4: Docs And Media

The public docs need more real evidence.

Minimum media set:

- one Director MP4 or animated capture
- one RookVision screenshot
- one Grasshopper canvas screenshot
- one RookBIM screenshot if the Revit workflow is launch-ready
- one installer/setup screenshot only if it clarifies a confusing step

Docs to update:

- `rook-release/site/src/content/docs/modules/director.md`
- `rook-release/site/src/content/docs/modules/rookbim.md`
- `rook-release/site/src/content/docs/start/first-conversation.md`
- optional: unhide or partially populate `showcase/gallery.mdx` only after real
  assets exist

Docs claims checked on 2026-06-10:

- Hunyuan 3D in `rook-release` was softened to preview/roadmap language unless
  a verified 2D-to-3D path lands before launch.
- 3D Pipeline in `rook-release` was softened to preview/roadmap language unless
  retopology/segmentation/texturing are verified before launch.
- RookSplat is already marked coming soon and should stay that way unless the
  mesh2splat converter lands and is integrated.

## Candidate Schedule

### Wednesday 2026-06-10

- Finish this roadmap and decide launch wow priority.
- Audit current installer/post-install changes.
- Decide whether Director `curve_follow_target` is the primary implementation
  target.
- Define the exact RookBIM demo prompt and acceptance model.

### Thursday 2026-06-11

- Implement or validate the Director video path.
- Smoke the RookBIM workflow in RhinoInside/Revit.
- Fix any obvious public-doc overclaims around 3D.

### Friday 2026-06-12

- Capture media.
- Fix visible RookVision/RookBIM/Director UX blockers found during capture.
- Update public docs with real assets and concrete try-it prompts.

### Saturday 2026-06-13

- Run release validation.
- Run installer smoke.
- Run public docs build and plugin validation.
- Validate fresh agent post-install prompts.

### Sunday 2026-06-14

- Final smoke on the exact public artifact.
- Make the public docs/release page final.
- Publish Sunday night if confidence is high.

### Monday 2026-06-15

- Backup public push window.
- Send public links and McNeel-facing summary.

## Decision Points

### D1: Primary Wow

Current recommendation:

1. Director video as primary wow.
2. RookBIM audit/report workflow as secondary credibility demo.

Reason:

Director gives the strongest public visual artifact. RookBIM gives the strongest
professional credibility, but it needs a complete "question -> evidence ->
deliverable" workflow to avoid feeling like a raw API demo.

### D2: RookBIM End State

Recommended launch end state:

RookBIM should produce an audit packet, not stop at selection.

Acceptable outputs for launch:

- markdown report in the agent response
- JSON evidence table
- selected elements in Revit
- screenshot showing selected evidence

Deferred outputs:

- writing Revit parameters
- creating Revit views/sheets
- creating issue tracker tickets
- persistent model snapshots

### D3: 2D-to-3D Claim

Decision needed:

Either verify a minimal image-to-mesh path by 2026-06-12, or keep public docs
clear that Hunyuan/3D Pipeline are preview/roadmap capabilities rather than
current first-session promises.

### D4: Showcase

Decision needed:

Keep Showcase hidden unless it has real assets. A hidden draft is better than a
public "coming soon" gallery during launch week.

## Immediate Next Actions

1. Decide whether to execute the existing Director `curve_follow_target`
   implementation plan today.
2. Pick one RookBIM demo prompt:
   - parameter completeness audit
   - category inventory
   - issue-ready coordination packet
3. Verify whether the current RookBIM build can execute that prompt live.
4. Audit public docs for 3D overclaim risk.
5. Turn successful live outputs into screenshots/video for the public docs.
