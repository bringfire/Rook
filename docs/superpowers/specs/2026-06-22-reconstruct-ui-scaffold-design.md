# Reconstruct UI Scaffold — Design Spec

**Date:** 2026-06-22
**Status:** Approved for planning
**Base:** `origin/main` @ `c560ee88` (post PR #331, view-set assembly merged)
**Worktree:** `.worktrees/reconstruct-ui-scaffold`
**Surface:** Vision panel web UI — `src/Rook/UI/Vision/Resources/{index.html, app.js, styles.css}` (embedded resources)

---

## 1. Purpose

Bring the **Reconstruct tab's Generate panel** into structural parity with the Video tab by adding the human input surface for the three reconstruction modes — **T3D** (text→3D), **I3D** (single image→3D), **MV3D** (multi-view set→3D) — as a real, honest scaffold. This is the human-facing workflow shell that future backend slices wire into incrementally.

This is **Slice B** of a deliberate sequence:
- **B (this slice):** the UI input surface. Mode switching, prompt, large source pane, and MV3D labeled slots are all real. The only deferred step is turning filled MV3D slots into a `reconstruction_view_set` artifact.
- **C (the named, immediate next slice):** wire the filled MV3D slot state to `rhino_2d_to_3d_assemble_view_set` (which is already merged). The UI/state boundaries here are designed so C wires in **without restructuring** anything.
- Later: MV3D provider submit (once a multi-view provider exists); T3D generation (once a text-to-3D provider/catalog entry exists).

**Not in scope:** any backend, native, or MCP change; calling `assemble_view_set`; provider submit for MV3D or T3D; new providers/catalog entries. UI-only, **Pattern A** (WebView bridge only, no direct HTTP from JS).

### What already exists (audit)
The two-column + queue-rail parity shipped in #321: `reconstruct-view` already has `reconstruct-main` (form panel `01 Generate` + result `02`) and `reconstruct-queue-panel` `03` with filter chips. The current Generate form has a small source thumb + "Choose in Gallery…", model select+hint, an Output segmented (Textured/Geometry-only), submit, and status. **This slice fills the Generate-panel internals** — precisely the items #321 deferred: mode selector, prompt, enlarged source pane, and the MV3D slot grid. Video already provides every needed pattern: a compact mode radio group (`video-mode-radios`), a mode-gated body (`video-frames-section`), per-slot in-place `Pick`/`Clear`, and a reusable picker modal (`openPicker(slot)`/`closePicker()`/`pickerModal`).

---

## 2. Layout & mode-gating

### Constant Generate chrome (always visible, Video grammar)
Inside the existing `reconstruct-form-panel` (`01 Generate`), in order:
1. **Model** select + hint (existing `reconstruct-model-select`/`-model-hint`).
2. **Mode** switcher — compact segmented `T3D ｜ I3D ｜ MV3D`, reusing the existing `seg-btn` style (as the current Output control does). Each segment carries a `title` tooltip (new paradigm). Buttons carry `data-mode="t3d|i3d|mv3d"`.
3. **Prompt** — always present (text-to-3D will use it). A `<textarea>` + a hint whose text is mode-driven.
4. **Output** — the existing Textured/Geometry-only segmented control, retained.

### Mode-gated body (below the chrome)
A `data-mode`-driven gate shows/hides body regions, mirroring Video's mode-gated frames. The active mode is reflected on a container attribute (e.g. `reconstruct-form-panel[data-mode]`) and CSS shows/hides regions by class/attribute toggling — the same established pattern the panel already uses (e.g. the `hidden` class on `reconstruct-result-panel`). Gating is applied by JS on mode change.

| Mode | Body | Prompt hint | Model select | Primary action |
|---|---|---|---|---|
| **T3D** | source pane + slots **hidden** | "Required for text-to-3D" | disabled placeholder "No models for this mode yet" | `Reconstruct` **disabled** + note "Text-to-3D arrives when a provider lands." |
| **I3D** (default, functional) | the **one large source pane** | "Optional" | `single_image_to_3d` models (current behavior) | `Reconstruct` **enabled** — submits exactly as today |
| **MV3D** | the **same large pane** (now labeled `front`, hero) **+ secondary slot strip** below | "Optional" | disabled placeholder "No multi-view models yet" | `Assemble view set` **disabled** + note "Slot assembly wires next." |

**Default mode = I3D** — preserves the working path with no regression.

### MV3D arrangement (chosen: B — front hero + secondary slots)
- The large pane is the **same element** I3D uses for its source; in MV3D it is the `front` view (the hero).
- Below it, a labeled secondary slot strip: `left ｜ right ｜ back` always shown, plus `top ｜ three_quarter` always shown but **visually marked optional** (dimmed/dashed). No hidden controls.
- Every pane/slot (including the front hero pane) has in-place `Pick` / `Clear`.

---

## 3. State model (the Slice-C protection)

A single uniform slot map drives both render and the future assemble payload:

```js
// Reconstruct module state
slots = {
  front:         { artifact_id, role, previewSrc, label, kind } | null,
  left:          { … } | null,
  right:         { … } | null,
  back:          { … } | null,
  top:           { … } | null,   // optional
  three_quarter: { … } | null,   // optional
}
```

- `artifact_id` + `role` are the **future `assemble_view_set` payload** (`views[{ slot, artifact_id, role }]`). `role` defaults to `"image"`.
- `previewSrc` + `label` (+ optional `kind`) are **UI-only render fields** so the renderer stays clean and never re-derives blob URLs ad hoc.
- **`front` is hero only in the view; in state it is just another slot.** No special-casing.
- I3D's single source is `slots.front` (the same pane). Switching I3D↔MV3D never moves or restructures `front` — MV3D simply reveals the secondary strip.

**Slice C becomes**, with zero UI restructuring:
```js
const views = Object.entries(slots)
  .filter(([, v]) => v)
  .map(([slot, v]) => ({ slot, artifact_id: v.artifact_id, role: v.role }));
// → reconstructionBridgeCall("assemble_view_set", { views, slots_expected, … })
```

### Panel-dark gate strategy
Per-slot DOM is **queried by `[data-slot]`**, not individually `$("id")`-cached (mirrors Video's frames), so the panel-dark surface stays small. Only **section/container ids** are cached. Every newly cached `$("reconstruct-…")` id **must** exist in `index.html` or the panel inits null and goes dark.

New cached ids (final list confirmed against the gate at implementation):
- `reconstruct-mode-radios` (the mode switcher container; segments queried by `[data-mode]`)
- `reconstruct-prompt`, `reconstruct-prompt-hint`
- front pane in-place controls: `reconstruct-source-pick`, `reconstruct-source-clear` (the existing `reconstruct-source-thumb`/`-label` are reused; the existing `reconstruct-choose-source` is repurposed to open the in-place picker)
- `reconstruct-mv-slots` (the MV3D secondary-slot section container)
- `reconstruct-action-note` (the mode-driven why/when note beside the action button)
- reconstruct picker modal: `reconstruct-picker-modal`, `reconstruct-picker-close`, `reconstruct-picker-grid` (+ `reconstruct-picker-title`)

The single primary action stays `reconstruct-submit-btn`, with **mode-driven label, handler, and enablement** (I3D: "Reconstruct"/enabled; T3D: "Reconstruct"/disabled; MV3D: "Assemble view set"/disabled).

---

## 4. Slot-fill interaction

Two complementary, established patterns — **pattern reuse, isolated state** (a parallel Reconstruct picker modal; do **not** share Video's exact module — sharing two already-complex panels too early couples them):

1. **In-place `Pick` / `Clear` on every pane/slot, including the front hero pane.** `Pick` opens a Reconstruct-owned picker modal (parallel to Video's `openPicker(slot)`), scoped to the clicked `data-slot`; choosing a Gallery artifact fills `slots[slot]` and renders its preview in place. `Clear` empties `slots[slot]`. This makes filling `left` symmetric with filling `front`, and lets the user pick **without leaving the Reconstruct tab**.

2. **Gallery "Send to 3D" shortcut (retained).** `presetSource(artifact)` continues to exist. Explicit behavior:
   - It **always populates the large front/source pane** (`slots.front`) and routes to the Reconstruct view.
   - If no Reconstruct mode is active when invoked, it **defaults to I3D**.
   - If **MV3D is already active**, it fills the **front** slot **without leaving MV3D** (no forced mode change).
   - **Invariant:** "Send to 3D" always lands in the large pane — never just a small hidden source thumbnail.

---

## 5. Honesty (no dead controls)

- **I3D** submits for real (unchanged behavior).
- **T3D** and **MV3D** primary actions are **visibly disabled** with plain-language notes stating *why* and *when* (T3D: provider pending; MV3D: assembly wires next slice). Disabled is honest; a button that silently does nothing is not.
- Optional slots (`top`, `three_quarter`) are **visually marked optional**.
- Model select shows an explicit disabled placeholder for modes with no provider entries yet, rather than an empty or misleading list.
- MV3D slot fill is **fully real** (pick, preview, clear, persistent form state) — the only deferred thing is consuming that state via `assemble_view_set`.

---

## 6. Components / files

All under `src/Rook/UI/Vision/Resources/` (embedded resources):
- **`index.html`** — extend the `reconstruct-view` Generate panel with: the mode switcher, prompt + hint, enlarged source/front pane with in-place `Pick`/`Clear`, the `reconstruct-mv-slots` secondary-slot section, the action note, and the reconstruct picker modal markup. Every new cached id present here.
- **`app.js`** — the Reconstruct module gains: mode state + `data-mode` gating, the `slots` map (§3) with render fields, in-place pick/clear handlers (`[data-slot]`), a Reconstruct-owned picker modal (`openPicker`/`closePicker` parallel to Video's), mode-driven model-select filtering + action label/enablement, prompt hint per mode, and the updated `presetSource`/Send-to-3D behavior (§4). No backend calls beyond the existing `models` query.
- **`styles.css`** — styles for the mode switcher (reuse `seg-btn`), the enlarged source/front pane (Video frame-pane language), the secondary slot strip + optional-slot affordance, and the reconstruct picker modal (reuse Video modal styling).

No C#, native, or Python changes.

---

## 7. Testing

UI-only, so tests are the established Vision-panel static gates plus structural assertions (run via the project's JS checks / `node --check` and the repo's panel-dark tooling):

- **Panel-dark gate (blocking):** `node --check app.js`; every cached `$("reconstruct-…")` id exists in `index.html`; duplicate-id scan; dangling-symbol scan; undefined-CSS-token scan. (This is the gate that has bitten prior Vision slices; it is mandatory after every JS change.)
- **Mode-gating assertions:** for each mode (`t3d`/`i3d`/`mv3d`), the correct body regions are shown/hidden, the action button has the correct label + enablement, and the model-select placeholder state matches.
- **Slot-state assertions:** filling/clearing a slot updates `slots[slot]` with `{ artifact_id, role, previewSrc, label }`; `front` is uniform with the others; the (future) `views` projection over `slots` yields the expected `{ slot, artifact_id, role }[]` (a pure projection test that pre-validates the Slice-C wiring contract without calling the backend).
- **Send-to-3D invariant:** `presetSource(artifact)` populates `slots.front` + renders the large pane; defaults to I3D when no mode active; fills front without leaving MV3D when MV3D active.

---

## 8. Verification

- **Managed Release deploy** is the light deploy for this slice — Vision web assets are **embedded resources**, so `dotnet build src/Rook/Rook.csproj -c Release` (→ DeployToRhino) plus a Rhino restart surfaces the new UI. No native rebuild, no MCP reload needed (no tool/route change).
- **Panel-dark gate is the blocking pre-merge gate** (no UI change ships without it green).
- **Live smoke (merge gate):** open the Vision panel → Reconstruct tab; confirm it loads (not dark); switch T3D/I3D/MV3D and confirm the body, action label/enablement, prompt hint, and model placeholder change correctly; in I3D, confirm existing submit still works and "Send to 3D" lands in the large pane; in MV3D, fill `front` + a couple of secondary slots from the Gallery picker, clear one, confirm previews + persistence, and confirm the disabled `Assemble view set` button + note read honestly.

---

## 9. Slice C handoff (the immediate next slice)

C wires the filled MV3D slots to `assemble_view_set`. Because of §3, C needs **no UI restructuring**: it adds the `views` projection (already shape-tested here), enables the MV3D action button, calls `reconstructionBridgeCall("assemble_view_set", …)`, and renders the resulting `reconstruction_view_set` in the existing Result panel. This spec deliberately leaves that the only missing piece.
