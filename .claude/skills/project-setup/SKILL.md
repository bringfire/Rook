---
name: project-setup
description: |
  Set up a project folder for use with Rook and Claude Code. Copies the Rook
  CLAUDE.md, interviews the user about their project, and generates a
  project-tailored configuration. Triggers: "project setup", "setup project",
  "initialize project", "set up rook", "configure rook for this project",
  "new project", or when the SessionStart hook detects missing Rook context.
---

# Project Setup

Set up the current working directory as a Rook-enabled project. Copies the
Rook CLAUDE.md from the install folder, interviews the user about their
project, and generates a tailored CLAUDE.md with project-specific context.

## When to Use

- User opens Claude Code in a project folder that has no Rook CLAUDE.md
- User explicitly asks to set up or initialize a project for Rook
- SessionStart hook suggests running `/project-setup`

## Workflow

### Step 0: Preflight

1. **Check for existing CLAUDE.md.** Read `./CLAUDE.md` if it exists.
   - If it contains the marker `rhino_execute_intent` — Rook context already
     present. Ask: "This project already has Rook context. Update it, or
     start fresh?" Branch accordingly.
   - If it exists but has NO Rook marker — we'll append Rook context to it
     (preserve the user's existing content).
   - If it doesn't exist — fresh setup.

2. **Locate the Rook install CLAUDE.md.** Check in order:
   - `$ROOK_INSTALL_ROOT/../CLAUDE.md` (env var from MCP config)
   - `$LOCALAPPDATA/Rook/CLAUDE.md` (Windows default install path)
   - `$HOME/.local/share/rook/CLAUDE.md` (future Linux/macOS path)

   If not found, fetch the canonical version from GitHub:
   `https://raw.githubusercontent.com/bringfire/Rook/main/installer/CLAUDE.md`
   If that also fails, generate a minimal Rook reference section from the
   tool names and patterns you know (rhino_execute_intent, gh_execute_intent,
   knowledge_query, the Critical Rules). Warn the user that the install
   CLAUDE.md was not found and the reference may be incomplete.

3. **Scan the project directory.** Use `Glob` to detect:
   - `.3dm` files → Rhino models present
   - `.gh` / `.ghx` files → Grasshopper definitions present
   - `.py` files → Python scripts present
   - `docs/` or `plans/` → existing documentation structure
   - `.git/` → version controlled

   Note findings for context in the interview.

### Step 1: Interview

Ask questions **one at a time**. Prefer multiple-choice. Keep it brief —
the user wants to get to work, not fill out a form.

<HARD-GATE>
Do NOT generate the CLAUDE.md until the interview is complete and the user
has confirmed the summary. Rushing past the interview defeats the purpose.
</HARD-GATE>

**Q1: Project description**
> "What are you working on in this folder? A sentence or two is fine."

*(Open-ended. This becomes the project header.)*

**Q2: Domain** *(multiple choice)*
> Pick the closest match, or say "other":
> 1. Architecture / Building Design
> 2. Landscape / Urban Design
> 3. Product / Industrial Design
> 4. Jewelry / Small-Scale Fabrication
> 5. Infrastructure / Civil Engineering
> 6. Digital Fabrication / CNC / 3D Printing
> 7. Computational Design / Research
> 8. Other (describe briefly)

**Q3: Primary workflow** *(multiple choice)*
> How do you primarily work?
> 1. Rhino modeling (direct geometry)
> 2. Grasshopper parametric definitions
> 3. Mixed Rhino + Grasshopper
> 4. Scripting and automation
> 5. Not sure yet / exploring

**Q4: AI behavior** *(multiple choice)*
> How should Claude behave in this project?
> 1. Conservative — ask before any geometry changes
> 2. Balanced — execute routine tasks, ask before destructive changes (recommended)
> 3. Autonomous — execute and report, only ask when ambiguous

**Q5: Project conventions** *(optional, open-ended)*
> "Any conventions I should know? Layer naming, units, file organization,
> team standards? (Skip if none.)"

*(If the user says "skip" or "none", move on. Don't press.)*

### Step 2: Confirm

Present a summary of what will be generated:

```
Project: [their description]
Domain: [their choice]
Workflow: [their choice]
AI Behavior: [their choice]
Conventions: [their answer or "none specified"]

I'll create a CLAUDE.md in this folder with:
- Rook tool reference (how to use Rhino/GH via MCP)
- Your project context and conventions
- AI behavior guidelines

[If existing CLAUDE.md without Rook]: Your existing CLAUDE.md content
will be preserved at the top.

Ready to generate?
```

Wait for confirmation. If they want changes, go back to the relevant question.

### Step 3: Generate CLAUDE.md

Build the file with this structure. Use the installer CLAUDE.md as the Rook
reference section — read it from the install path found in Step 0.

```markdown
# [Project Name derived from description]

> [User's description from Q1]

---

## Project Context

- **Domain:** [Q2 answer]
- **Workflow:** [Q3 answer]
- **Conventions:** [Q5 answer, or "None specified"]

## AI Behavior

[Generated from Q4:]

[If Conservative:]
Always ask before creating, modifying, or deleting geometry. Describe what
you plan to do and wait for approval. For Grasshopper, describe component
changes before executing.

[If Balanced:]
Execute routine geometry operations (create, transform, query) without
asking. Ask before: deleting objects, major canvas restructuring, running
scripts that modify existing geometry, or any operation that can't be
undone with Ctrl+Z. When in doubt, ask.

[If Autonomous:]
Execute tasks and report results. Only ask when the intent is genuinely
ambiguous or when multiple valid approaches exist. Use `rhino_execute_intent`
and `gh_execute_intent` freely. Report what was created/modified after each
operation.

---

[Read the full installer CLAUDE.md from the install path found in Step 0
and insert its contents here verbatim, starting from "## Start Here".
If fetched from GitHub instead, use that content. If neither source was
available, generate a minimal reference covering: Start Here (rhino_ping),
Primary Tools (rhino_execute_intent, gh_execute_intent), Knowledge Store
(knowledge_query depths), and Critical Rules (never say "I can't", use
MCP tools not HTTP, no keyboard automation, prefer typed routes).]
```

**If the user had an existing CLAUDE.md without Rook context:**
Place their original content first, then add a `---` separator, then the
Rook section starting from `## Project Context`.

### Step 4: Write and Verify

1. Write the generated CLAUDE.md to `./CLAUDE.md` using the Write tool.
2. If the project directory scan (Step 0) found NO `docs/` folder and the
   user's workflow involves Grasshopper or mixed work, suggest:
   > "Want me to create a `docs/plans/` folder for design documents?
   > Skills like `/design-grasshopper` save plans there."
   Create only if the user says yes.
3. Print next steps:
   > "Project setup complete. Your CLAUDE.md will load automatically in
   > future Claude Code sessions from this folder.
   >
   > Quick start:
   > - `rhino_ping` — verify Rhino connection
   > - `rhino_execute_intent` — create/modify geometry
   > - `gh_execute_intent` — build Grasshopper definitions
   > - `/design-grasshopper` — collaborative GH design workflow"

## Handling Edge Cases

- **User says "just copy the basics":** Skip Q2-Q5, generate with just Q1
  and the Rook reference. Default to Balanced behavior.
- **User wants to update an existing Rook CLAUDE.md:** Re-run the interview,
  regenerate the project-specific sections, preserve the Rook reference.
  Don't duplicate the Rook section.
- **No Rook install found:** Fetch the canonical CLAUDE.md from GitHub
  (`https://raw.githubusercontent.com/bringfire/Rook/main/installer/CLAUDE.md`).
  If that also fails, generate a minimal Rook reference from the tool names
  and rules you know. Warn: "Rook install directory not found — reference
  section may be incomplete. Run the installer for the full experience."
- **User is in the Rook install directory:** Warn that this is the install
  folder, not a project folder. Suggest they `cd` to their project first.

## Key Principles

- **One question at a time.** Never present all questions at once.
- **Multiple choice when possible.** Lower friction than open-ended questions.
- **Fast path available.** User can skip to basics at any point.
- **Preserve existing content.** Never overwrite user's non-Rook CLAUDE.md content.
- **No git assumptions.** Works whether or not the folder is a git repo.
- **Idempotent.** Running twice updates rather than duplicates.