# Reconstruct UI Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the human input surface for the Reconstruct tab's Generate panel — `T3D`/`I3D`/`MV3D` mode switching, prompt, an enlarged front/source pane, and MV3D labeled slots with in-place pick — as a real, honest UI scaffold. Only the "filled slots → `reconstruction_view_set` artifact" step is deferred (the named Slice C).

**Architecture:** Pure front-end change to the Vision panel's embedded web assets (`src/Rook/UI/Vision/Resources/{index.html, app.js, styles.css}`). UI-only, **Pattern A** (WebView bridge only). No new backend/native/MCP routes; the picker reuses the **existing** artifact/gallery bridge + `/blob/{id}/image` preview, exactly as Video's picker does.

**Tech Stack:** Vanilla JS (the Reconstruct IIFE module in `app.js`), HTML, CSS. Tests are **C# source-assertion tests** (`src/Rook.Tests/UI/Vision/`, `ReadVisionResource` pattern) run via `dotnet test`, plus a **manual panel-dark scan** (Bash). Base: `origin/main` @ `c560ee88`. Worktree: `.worktrees/reconstruct-ui-scaffold`, branch `feature/reconstruct-ui-scaffold`.

**Spec:** `docs/superpowers/specs/2026-06-22-reconstruct-ui-scaffold-design.md` — implements it verbatim; read it.

## Global Constraints

- **Panel-dark discipline (blocking, every task):** every cached `$("reconstruct-…")` in `app.js` MUST exist as `id="…"` in `index.html`. **No task may add a cached id without its matching HTML in the same task.** Each task ends with the panel-dark scan green (below) AND the panel loading cleanly.
- **Pattern A / backend boundary:** no new endpoints; no `assemble_view_set` or provider-submit calls this slice. Reusing the existing artifact-listing / `/blob/{id}/image` / `models` bridge is allowed and expected.
- **Default mode = I3D**; I3D submit stays functional (no regression).
- **Uniform slot state:** `slots = { front, left, right, back, top?, three_quarter? }`, each `{ artifact_id, role, previewSrc, label, kind? }`. `front` is hero in the *view* only. Per-slot DOM queried by `[data-slot]`, not `$("id")`-cached.
- **Single front-pane pick control:** the existing `reconstruct-choose-source` button BECOMES the in-place `Pick` (opens the Reconstruct picker scoped to `front`); the only new front-pane id is `reconstruct-source-clear`. No `reconstruct-source-pick`.
- **Exact tooltip copy** (contract): T3D `"Text to 3D: generate a model from a text prompt."`; I3D `"Image to 3D: reconstruct from one source image."`; MV3D `"Multi-view 3D: reconstruct from labeled front/side/back images."`
- **Honesty:** no dead controls — T3D/MV3D actions visibly disabled with why/when notes; optional slots marked; model placeholders for provider-less modes.

## Panel-dark gate (run from `src/Rook/UI/Vision/Resources/`)

```bash
# 1. JS syntax
node --check app.js
# 2. Every cached $("id") in app.js exists as id="id" in index.html (output MUST be empty)
comm -23 \
  <(grep -oE '\$\("reconstruct-[a-z0-9-]+"\)' app.js | sed -E 's/.*\$\("([^"]+)"\).*/\1/' | sort -u) \
  <(grep -oE 'id="reconstruct-[a-z0-9-]+"' index.html | sed -E 's/.*id="([^"]+)".*/\1/' | sort -u)
# 3. No duplicate ids in index.html (output MUST be empty)
grep -oE 'id="[a-z0-9-]+"' index.html | sort | uniq -d
```
All three must pass before each task's commit. (Line 2 lists cached ids with no HTML home — the panel-dark cause.)

---

## File Structure

- `src/Rook/UI/Vision/Resources/index.html` — extend the `reconstruct-view` Generate panel (lines ~666-701): mode switcher, prompt, enlarged front pane + `Clear`, `reconstruct-mv-slots` section, action note, reconstruct picker modal markup.
- `src/Rook/UI/Vision/Resources/app.js` — extend the Reconstruct IIFE (the `re.*`/`$("reconstruct-…")` block ~3344+): mode state + gating, the `slots` map, in-place pick/clear (`[data-slot]`), a Reconstruct-owned picker modal, mode-driven model/action/prompt-hint, updated `presetSource`.
- `src/Rook/UI/Vision/Resources/styles.css` — mode switcher (reuse `seg-btn`), enlarged front pane, slot strip + optional affordance, reconstruct picker modal (reuse Video modal styles).
- `src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs` **(new)** — per-task source assertions (mirror `VisionWebSurfaceTests` `ReadVisionResource` pattern).

No C#, native, or Python production changes.

---

## Task 1: Mode switcher + mode-gating + prompt

Add the `T3D｜I3D｜MV3D` switcher, the prompt panel, and the `data-mode` gating skeleton. Body regions for source/slots don't exist yet — gating just toggles a `data-mode` attribute + prompt hint; default I3D. Panel stays clean.

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/index.html`, `app.js`, `styles.css`
- Create/Modify: `src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs`

**Interfaces (produced, used by later tasks):**
- HTML container `reconstruct-form-panel` gains a `data-mode` attribute (`t3d|i3d|mv3d`, default `i3d`).
- `re.modeSwitch = $("reconstruct-mode-radios")` (container; segments queried by `[data-mode]`), `re.prompt = $("reconstruct-prompt")`, `re.promptHint = $("reconstruct-prompt-hint")`.
- `function setReconstructMode(mode)` — sets `data-mode`, updates prompt hint, (later tasks: gates source/slots, model, action).

- [ ] **Step 1: Write the failing source assertions**

In `ReconstructScaffoldSourceTests.cs` (new file; copy the `ReadVisionResource`/`CountOccurrences` helpers from `VisionWebSurfaceTests.cs` or make them `internal static` and reuse):
```csharp
[Fact]
public void IndexHtml_ReconstructModeSwitcher_HasThreeModesWithExactTooltips()
{
    var html = ReadVisionResource("index.html");
    Assert.Contains("id=\"reconstruct-mode-radios\"", html);
    Assert.Contains("data-mode=\"t3d\"", html);
    Assert.Contains("data-mode=\"i3d\"", html);
    Assert.Contains("data-mode=\"mv3d\"", html);
    Assert.Contains("title=\"Text to 3D: generate a model from a text prompt.\"", html);
    Assert.Contains("title=\"Image to 3D: reconstruct from one source image.\"", html);
    Assert.Contains("title=\"Multi-view 3D: reconstruct from labeled front/side/back images.\"", html);
}

[Fact]
public void IndexHtml_ReconstructPrompt_Present()
{
    var html = ReadVisionResource("index.html");
    Assert.Contains("id=\"reconstruct-prompt\"", html);
    Assert.Contains("id=\"reconstruct-prompt-hint\"", html);
}

[Fact]
public void AppJs_ReconstructModeGating_DefaultsToI3d()
{
    var js = ReadVisionResource("app.js");
    Assert.Contains("re.modeSwitch = $(\"reconstruct-mode-radios\");", js);
    Assert.Contains("function setReconstructMode(", js);
    Assert.Contains("let reconstructMode = \"i3d\";", js);
}
```

- [ ] **Step 2: Run to verify fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructScaffoldSourceTests"`
Expected: FAIL (ids/strings absent).

- [ ] **Step 3: Add the HTML**

In `index.html`, set the form panel container to carry the mode: change `<div class="panel reconstruct-form-panel">` (line ~666) to `<div class="panel reconstruct-form-panel" data-mode="i3d">`. Inside `reconstruct-form` (after the Model field, before Output), add the mode switcher + prompt:
```html
<div class="reconstruct-field">
  <label class="reconstruct-label">Mode</label>
  <div id="reconstruct-mode-radios" class="reconstruct-segmented" role="radiogroup" aria-label="Reconstruction mode">
    <button type="button" class="seg-btn" data-mode="t3d" role="radio" aria-checked="false" title="Text to 3D: generate a model from a text prompt.">T3D</button>
    <button type="button" class="seg-btn active" data-mode="i3d" role="radio" aria-checked="true" title="Image to 3D: reconstruct from one source image.">I3D</button>
    <button type="button" class="seg-btn" data-mode="mv3d" role="radio" aria-checked="false" title="Multi-view 3D: reconstruct from labeled front/side/back images.">MV3D</button>
  </div>
</div>
<div class="reconstruct-field">
  <label class="reconstruct-label" for="reconstruct-prompt">Prompt</label>
  <textarea id="reconstruct-prompt" class="reconstruct-prompt" rows="2" placeholder="Describe the object…"></textarea>
  <span id="reconstruct-prompt-hint" class="option-hint">Optional for image modes.</span>
</div>
```

- [ ] **Step 4: Add the app.js state + gating**

In the Reconstruct IIFE: add cached els (in the `cacheEls`/`re.*` block ~3344) `re.modeSwitch = $("reconstruct-mode-radios");`, `re.prompt = $("reconstruct-prompt");`, `re.promptHint = $("reconstruct-prompt-hint");`. Add module state `let reconstructMode = "i3d";` and:
```js
const RECONSTRUCT_PROMPT_HINT = {
    t3d: "Required for text-to-3D.",
    i3d: "Optional for image modes.",
    mv3d: "Optional for image modes.",
};
function setReconstructMode(mode) {
    reconstructMode = mode;
    re.formPanel.setAttribute("data-mode", mode);
    re.modeSwitch.querySelectorAll(".seg-btn").forEach(b => {
        const on = b.dataset.mode === mode;
        b.classList.toggle("active", on);
        b.setAttribute("aria-checked", on ? "true" : "false");
    });
    re.promptHint.textContent = RECONSTRUCT_PROMPT_HINT[mode] || "";
    // later tasks extend: gate source/slots, model placeholder, action label/enablement
}
```
Cache `re.formPanel = document.querySelector(".reconstruct-form-panel");` (not an id — a class query is fine, not panel-dark-relevant). In `wireEvents`, wire the switcher: `re.modeSwitch.querySelectorAll(".seg-btn").forEach(b => b.addEventListener("click", () => setReconstructMode(b.dataset.mode)));`. In `onEnter`, call `setReconstructMode(reconstructMode);` once after model load so the default renders.

- [ ] **Step 5: Add minimal styles**

In `styles.css`, the mode switcher reuses the existing `.reconstruct-segmented`/`.seg-btn` rules (already present for Output) — no new rule needed unless spacing differs; add a `.reconstruct-prompt { width:100%; }` if the textarea needs it. Keep it minimal.

- [ ] **Step 6: Run the source assertions green**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructScaffoldSourceTests"`
Expected: PASS.

- [ ] **Step 7: Panel-dark gate**

Run the three gate commands (from `src/Rook/UI/Vision/Resources/`). All three empty/clean. Fix any cached-id-without-HTML before proceeding.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat(vision): Reconstruct mode switcher + prompt + mode-gating (T1)"
```

---

## Task 2: Enlarged front/source pane + in-place pick/clear + Send-to-3D invariant

Enlarge the source pane to Video frame-pane language, make the existing `reconstruct-choose-source` the in-place `Pick` (opens a picker scoped to `front`), add `reconstruct-source-clear`, move source into the `slots.front` state, and pin the Send-to-3D invariant. (The picker *modal* itself lands in Task 3 with the slots; for Task 2, `Pick` may route through the existing Gallery handoff as an interim — but the spec's end state is the modal. **Decision for this plan:** introduce the Reconstruct picker modal here in Task 2, since the front pane needs it; Task 3 reuses it for the secondary slots.)

**Files:** `index.html`, `app.js`, `styles.css`, `ReconstructScaffoldSourceTests.cs`

**Interfaces (produced):**
- `slots.front = { artifact_id, role, previewSrc, label, kind } | null`; `function fillSlot(slot, artifact)`, `function clearSlot(slot)`, `function renderSlot(slot)`.
- Reconstruct picker modal: `re.pickerModal = $("reconstruct-picker-modal")`, `re.pickerGrid = $("reconstruct-picker-grid")`, `re.pickerClose = $("reconstruct-picker-close")`; `function openReconstructPicker(slot)`, `function closeReconstructPicker()`.
- `presetSource(artifact)` updated per the invariant.

- [ ] **Step 1: Write failing assertions**

```csharp
[Fact]
public void IndexHtml_FrontPane_HasSingleClearAndReusesChooseSourceAsPick()
{
    var html = ReadVisionResource("index.html");
    Assert.Contains("id=\"reconstruct-choose-source\"", html);   // repurposed to Pick
    Assert.Contains("id=\"reconstruct-source-clear\"", html);     // new
    Assert.DoesNotContain("id=\"reconstruct-source-pick\"", html); // no competing control
}

[Fact]
public void IndexHtml_ReconstructPickerModal_Present()
{
    var html = ReadVisionResource("index.html");
    Assert.Contains("id=\"reconstruct-picker-modal\"", html);
    Assert.Contains("id=\"reconstruct-picker-grid\"", html);
    Assert.Contains("id=\"reconstruct-picker-close\"", html);
}

[Fact]
public void AppJs_SlotStateCarriesRenderFields_AndSendTo3dLandsInFront()
{
    var js = ReadVisionResource("app.js");
    Assert.Contains("function fillSlot(", js);
    Assert.Contains("function clearSlot(", js);
    Assert.Contains("previewSrc:", js);
    // Send-to-3D invariant: presetSource populates slots.front and large pane
    var s = js.IndexOf("function presetSource(", StringComparison.Ordinal);
    var e = js.IndexOf("return {", s, StringComparison.Ordinal);
    var body = js.Substring(s, e - s);
    Assert.Contains("fillSlot(\"front\"", body);
    Assert.Contains("if (reconstructMode === \"t3d\") setReconstructMode(\"i3d\");", body);
}
```

- [ ] **Step 2: Run to verify fail**

Run: `dotnet test … --filter "FullyQualifiedName~ReconstructScaffoldSourceTests"` → FAIL.

- [ ] **Step 3: HTML — enlarge front pane + picker modal**

Replace the current source field (lines ~672-679) with the enlarged pane (Video frame-pane language), relabeling the existing button to "Pick" and adding Clear:
```html
<div class="reconstruct-field" id="reconstruct-source-field">
  <label class="reconstruct-label" id="reconstruct-source-heading">Source image</label>
  <div class="reconstruct-source-pane">
    <img id="reconstruct-source-thumb" class="reconstruct-source-thumb hidden" alt="source" />
    <span id="reconstruct-source-label" class="reconstruct-source-label">No image selected</span>
    <div class="reconstruct-source-actions">
      <button id="reconstruct-choose-source" class="btn btn-secondary">Pick</button>
      <button id="reconstruct-source-clear" class="btn-text">Clear</button>
    </div>
  </div>
</div>
```
Add the picker modal near the end of `reconstruct-view` (before `</section>`), mirroring Video's picker modal markup:
```html
<div id="reconstruct-picker-modal" class="modal hidden">
  <div class="modal-backdrop"></div>
  <div class="modal-content">
    <div class="modal-header">
      <span id="reconstruct-picker-title">Pick a Gallery image</span>
      <button id="reconstruct-picker-close" class="btn-icon" aria-label="Close">×</button>
    </div>
    <div id="reconstruct-picker-grid" class="reconstruct-picker-grid"></div>
  </div>
</div>
```

- [ ] **Step 4: app.js — slots state, fill/clear/render, picker, presetSource**

Cache `re.sourceClear = $("reconstruct-source-clear");`, `re.pickerModal = $("reconstruct-picker-modal");`, `re.pickerGrid = $("reconstruct-picker-grid");`, `re.pickerClose = $("reconstruct-picker-close");`. Replace the single `source` var with `const slots = { front:null, left:null, right:null, back:null, top:null, three_quarter:null };` and a `let pickerTargetSlot = null;`. Implement:
```js
function fillSlot(slot, artifact) {
    slots[slot] = {
        artifact_id: artifact.artifact_id,
        role: "image",
        previewSrc: `/blob/${encodeURIComponent(artifact.artifact_id)}/image?ts=${Date.now()}`,
        label: (artifact.metadata && artifact.metadata.prompt) || artifact.kind || artifact.artifact_id,
        kind: artifact.kind,
    };
    renderSlot(slot);
}
function clearSlot(slot) { slots[slot] = null; renderSlot(slot); }
function renderSlot(slot) {
    if (slot === "front") {  // the hero pane reuses the existing source thumb/label
        const v = slots.front;
        if (v) { re.sourceThumb.src = v.previewSrc; re.sourceThumb.classList.remove("hidden"); }
        else { re.sourceThumb.removeAttribute("src"); re.sourceThumb.classList.add("hidden"); }
        re.sourceLabel.textContent = v ? v.label : "No image selected";
        return;
    }
    // secondary slots rendered in Task 3 (query by [data-slot])
}
const RECONSTRUCT_SOURCE_KINDS = ["generated_image","imported_image","captured_viewport","preprocessed_image"];
let pickerArtifactsById = {};
async function openReconstructPicker(slot) {
    pickerTargetSlot = slot;
    // The shared Gallery helper is `bridgeCall`; list_artifacts filters by a
    // SINGLE `kind`, so fan out one call per allowed kind and merge (mirrors
    // the Gallery's own multi-kind load).
    const results = await Promise.all(RECONSTRUCT_SOURCE_KINDS.map(
        k => bridgeCall("list_artifacts", { kind: k, limit: 100 }).catch(() => ({ artifacts: [] }))));
    const artifacts = results.flatMap(r => (r && r.artifacts) || []);
    pickerArtifactsById = {};
    artifacts.forEach(a => { pickerArtifactsById[a.artifact_id] = a; });
    re.pickerGrid.innerHTML = artifacts.map(a =>
        `<button class="reconstruct-picker-cell" data-artifact-id="${a.artifact_id}"><img src="/blob/${encodeURIComponent(a.artifact_id)}/image" alt="${escapeAttr(a.kind)}"/></button>`).join("");
    re.pickerModal.classList.remove("hidden");
}
function closeReconstructPicker() { re.pickerModal.classList.add("hidden"); pickerTargetSlot = null; }
```
Wire: `re.chooseSourceBtn` → `openReconstructPicker("front")`; `re.sourceClear` → `clearSlot("front")`; picker grid cells (delegated click) → `const a = pickerArtifactsById[cell.dataset.artifactId]; fillSlot(pickerTargetSlot, a); closeReconstructPicker();` (passing the full artifact object preserves `metadata.prompt` for the slot label); picker close + backdrop → `closeReconstructPicker()`; Escape closes it. Update `presetSource`:
```js
function presetSource(artifact) {
    if (!artifact) return;
    if (reconstructMode === "t3d") setReconstructMode("i3d"); // no-mode/T3D → I3D; MV3D stays
    fillSlot("front", artifact);   // ALWAYS lands in the large pane
    switchView("reconstruct");
}
```
Update the existing submit path to read `slots.front` instead of the old `source` (preserve I3D behavior: `slots.front.artifact_id` / `.role`).

- [ ] **Step 5: styles** — `.reconstruct-source-pane` (large, Video frame-pane look), `.reconstruct-source-actions`, `.reconstruct-picker-grid` (grid of thumbnails), reusing `.modal`/`.modal-backdrop`/`.modal-content` from Video.

- [ ] **Step 6: source assertions green** — `dotnet test … --filter "…ReconstructScaffoldSourceTests"` → PASS.

- [ ] **Step 7: Panel-dark gate** — three commands clean.

- [ ] **Step 8: Commit** — `git commit -m "feat(vision): enlarged front pane + in-place pick/clear + reconstruct picker + Send-to-3D invariant (T2)"`

---

## Task 3: MV3D secondary slots + slot state

Add the secondary slot strip (`left｜right｜back` + optional `top｜three_quarter`), rendered/queried by `[data-slot]`, fillable via the Task-2 picker. Only visible in MV3D.

**Files:** `index.html`, `app.js`, `styles.css`, `ReconstructScaffoldSourceTests.cs`

- [ ] **Step 1: Failing assertions**
```csharp
[Fact]
public void IndexHtml_Mv3dSlots_PresentWithDataSlots()
{
    var html = ReadVisionResource("index.html");
    Assert.Contains("id=\"reconstruct-mv-slots\"", html);
    foreach (var s in new[] { "left","right","back","top","three_quarter" })
        Assert.Contains($"data-slot=\"{s}\"", html);
    Assert.Contains("reconstruct-slot-optional", html); // top/¾ marked optional
}

[Fact]
public void AppJs_Mv3dSlots_WiredByDataSlot()
{
    var js = ReadVisionResource("app.js");
    Assert.Contains("re.mvSlots = $(\"reconstruct-mv-slots\");", js);
    Assert.Contains("re.mvSlots.querySelectorAll(\"[data-slot]\")", js);
    Assert.Contains("openReconstructPicker(", js);
}
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: HTML** — after the front pane field, add the MV3D section (gated visible only in MV3D via CSS on `[data-mode]`):
```html
<div class="reconstruct-field" id="reconstruct-mv-slots-field">
  <label class="reconstruct-label">Additional views</label>
  <div id="reconstruct-mv-slots" class="reconstruct-mv-slots">
    <div class="reconstruct-slot" data-slot="left"><span class="reconstruct-slot-label">left</span><div class="reconstruct-slot-thumb"></div><div class="reconstruct-slot-actions"><button class="btn-text btn-slot-pick" data-slot="left">Pick</button><button class="btn-text btn-slot-clear" data-slot="left">Clear</button></div></div>
    <div class="reconstruct-slot" data-slot="right">…</div>
    <div class="reconstruct-slot" data-slot="back">…</div>
    <div class="reconstruct-slot reconstruct-slot-optional" data-slot="top"><span class="reconstruct-slot-label">top · optional</span>…</div>
    <div class="reconstruct-slot reconstruct-slot-optional" data-slot="three_quarter"><span class="reconstruct-slot-label">¾ · optional</span>…</div>
  </div>
</div>
```
(Repeat the `left` inner structure for `right`/`back`/`top`/`three_quarter`; show the full markup for each — no "similar to" placeholders.)

- [ ] **Step 4: app.js** — cache `re.mvSlots = $("reconstruct-mv-slots");`. Extend `renderSlot(slot)` to render secondary slots by `[data-slot]` (set the slot's `.reconstruct-slot-thumb` background to `previewSrc` or empty). Wire each slot's Pick/Clear: `re.mvSlots.querySelectorAll(".btn-slot-pick").forEach(b => b.addEventListener("click", () => openReconstructPicker(b.dataset.slot)));` and the same for `.btn-slot-clear` → `clearSlot`. In `setReconstructMode`, the `[data-mode]` CSS handles show/hide of `#reconstruct-mv-slots-field` (no JS display toggling needed beyond the attribute).

- [ ] **Step 5: styles** — `.reconstruct-mv-slots` (grid), `.reconstruct-slot`, `.reconstruct-slot-thumb`, `.reconstruct-slot-optional` (dimmed/dashed), and `[data-mode="i3d"] #reconstruct-mv-slots-field, [data-mode="t3d"] #reconstruct-mv-slots-field { display:none; }` plus `[data-mode="t3d"] #reconstruct-source-field { display:none; }`.

- [ ] **Step 6: source assertions green.**
- [ ] **Step 7: Panel-dark gate** — clean (this task adds `reconstruct-mv-slots` only; per-slot DOM is `[data-slot]`, not cached).
- [ ] **Step 8: Commit** — `git commit -m "feat(vision): MV3D secondary slots + slot state via data-slot (T3)"`

---

## Task 4: Mode-driven model/action/honesty states + verification

Wire the model-select filtering, the mode-driven action button label/enablement, the honesty notes, and final polish. Then deploy + live smoke.

**Files:** `index.html`, `app.js`, `styles.css`, `ReconstructScaffoldSourceTests.cs`

- [ ] **Step 1: Failing assertions**
```csharp
[Fact]
public void IndexHtml_ActionNote_Present()
{
    var html = ReadVisionResource("index.html");
    Assert.Contains("id=\"reconstruct-action-note\"", html);
}

[Fact]
public void AppJs_ModeDrivenActionAndModelPlaceholder()
{
    var js = ReadVisionResource("app.js");
    Assert.Contains("function updateReconstructActionForMode", js);
    Assert.Contains("Assemble view set", js);
    Assert.Contains("Text-to-3D arrives when a provider lands.", js);
    Assert.Contains("Slot assembly wires next.", js);
    Assert.Contains("No models available for this mode yet", js);
}
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: HTML** — add `<span id="reconstruct-action-note" class="option-hint"></span>` beside `reconstruct-submit-btn` in the actions row.

- [ ] **Step 4: app.js** — cache `re.actionNote = $("reconstruct-action-note");`. Add `updateReconstructActionForMode(mode)` called from `setReconstructMode`:
```js
function updateReconstructActionForMode(mode) {
    if (mode === "i3d") {
        re.submitBtn.textContent = "Reconstruct";
        re.submitBtn.disabled = false;
        re.actionNote.textContent = "";
    } else if (mode === "t3d") {
        re.submitBtn.textContent = "Reconstruct";
        re.submitBtn.disabled = true;
        re.actionNote.textContent = "Text-to-3D arrives when a provider lands.";
    } else { // mv3d
        re.submitBtn.textContent = "Assemble view set";
        re.submitBtn.disabled = true;
        re.actionNote.textContent = "Slot assembly wires next.";
    }
}
```
Add mode-driven model filtering: the existing `loadModels` filters by `m.task` — for I3D keep `single_image_to_3d`; for T3D/MV3D the filtered list is empty → set `re.modelSelect.innerHTML = '<option value="" disabled selected>No models available for this mode yet</option>'`. Call the model refresh from `setReconstructMode`. Ensure the submit handler still no-ops/guards when disabled (defensive).

- [ ] **Step 5: styles** — final polish only (spacing, disabled affordance). No new ids.

- [ ] **Step 6: source assertions green** + **full suite**: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug` (no regressions).

- [ ] **Step 7: Panel-dark gate** — clean.

- [ ] **Step 8: Commit** — `git commit -m "feat(vision): mode-driven model/action/honesty states (T4)"`

- [ ] **Step 9: Deploy + live smoke (merge gate)**

Vision assets are embedded → **managed Release deploy** surfaces them; no native/MCP reload. Close Rhino, then:
`dotnet build src/Rook/Rook.csproj -c Release` (→ DeployToRhino), copy `src/Rook/bin/Release/net8.0/Rook.rhp` over `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rhp`, relaunch Rhino.
**Smoke:** open Vision → Reconstruct; confirm the tab loads (not dark); switch T3D/I3D/MV3D and verify body, action label/enablement, prompt hint, and model placeholder change correctly; I3D submit still works and "Send to 3D" lands in the large pane; MV3D: fill `front` + a couple secondary slots from the picker, clear one, confirm previews/persistence and the disabled "Assemble view set" + note.

- [ ] **Step 10: Finish the branch**

**REQUIRED SUB-SKILL:** Use superpowers:finishing-a-development-branch (verify tests, push, PR non-squash, smoke marked passed).

---

## Self-Review Notes

- **Spec coverage:** §2 chrome/gating → T1; §2 front pane + §4 fill + Send-to-3D invariant → T2; §2 MV3D slots + §3 uniform slot state → T3; §2 mode table (model/action/honesty) + §8 verification → T4. §3 panel-dark strategy → the gate runs every task; §6 single-pick-control → T2 assertion `DoesNotContain reconstruct-source-pick`.
- **No placeholders:** Task 3's repeated slot markup must be written out per slot in the implementation (the plan says so explicitly — no "similar to").
- **Bridge facts (confirmed):** the shared Gallery helper is `bridgeCall(op, args)` ([app.js:22](../../../src/Rook/UI/Vision/Resources/app.js)); `list_artifacts` filters by a single `kind`, so the picker fans out one call per allowed source kind and merges. `re.submitBtn` = `$("reconstruct-submit-btn")`; `re.chooseSourceBtn`/`re.modelSelect`/`re.sourceThumb`/`re.sourceLabel` already cached. The picker modal lands in T2 (front needs it) and is reused by T3's secondary slots — noted to avoid a T3 surprise.
- **Type/name consistency:** `slots`, `fillSlot`/`clearSlot`/`renderSlot`, `setReconstructMode`/`updateReconstructActionForMode`, `openReconstructPicker`/`closeReconstructPicker`, and the cached ids (`reconstruct-mode-radios`, `-prompt`, `-prompt-hint`, `-source-clear`, `-picker-modal`/`-grid`/`-close`, `-mv-slots`, `-action-note`) are stable across tasks and all have HTML homes in the task that introduces them.
