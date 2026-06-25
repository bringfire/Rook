# Reconstruct Meshy Options UI Design

Date: 2026-06-25
Worktree: C:/Users/aryan/source/repos/Rook/.worktrees/mesh-smart-topology
Branch: feature/mesh-smart-topology

## Goal

Expose catalog-described reconstruction options in the RookVision Reconstruct UI so Meshy v6 image-to-3D can be selected and configured without hard-coded Hunyuan-only controls.

The UI must preserve the backend safety model:

- stable reconstruction models are visible by default
- experimental reconstruction models are visible only after an explicit UI opt-in
- submitting an experimental model must explicitly send `allow_experimental_model: true`

## Current State

`ReconstructionOpHandler.Models` already accepts `include_experimental` and returns generic option descriptors for each model. The serialized descriptor includes:

- `key`
- `label`
- `kind`
- `default`
- `allowed_values`
- `min`, `max`, `step`
- `ignored_when`

`ReconstructionOptionsValidator` already validates descriptor-shaped option objects, fills defaults, and omits ignored options. It handles both current Hunyuan Pro behavior and Meshy texture-dependent options.

The UI currently falls short:

- `loadModels()` calls `reconstructionBridgeCall("models", {})`, so Meshy is excluded.
- `renderModelOptions()` assumes fixed controls for `generate_type`, `enable_pbr`, and `face_count`.
- `optionsForMode()` serializes those same fixed controls instead of walking descriptors.
- `index.html` contains fixed option controls instead of a dynamic option body.
- `submit()` does not send `allow_experimental_model`, so a visible experimental model would still fail submission.

## Model Loading And Experimental Visibility

Add an inline `Experimental models` toggle near the Reconstruct model selector. The toggle is off by default.

When off:

- call `reconstructionBridgeCall("models", {})`
- show only stable models returned by the backend
- do not submit `allow_experimental_model`

When on:

- call `reconstructionBridgeCall("models", { include_experimental: true })`
- include experimental catalog entries such as `fal-ai/meshy/v6/image-to-3d`
- preserve the previously selected model if it remains available
- otherwise select the first available model for the current mode

On submit, include `allow_experimental_model: true` only when both are true:

- the experimental toggle is enabled
- the selected model has a non-stable status, such as `experimental`

This condition is intentional. The submit gate should be explicit and directly tied to the same UI opt-in that made the model visible.

The model hint should include non-stable status so Meshy is visibly marked as experimental, for example:

`fal · single image to 3d · experimental · PBR`

## Generic Option Rendering

Replace fixed option element assumptions with a descriptor-driven renderer.

HTML should keep the `#reconstruct-options` section but replace fixed option rows with a dynamic body:

```html
<div class="reconstruct-field hidden" id="reconstruct-options">
  <label class="reconstruct-label">Options</label>
  <div id="reconstruct-options-body"></div>
  <span id="reconstruct-options-hint" class="option-hint hidden"></span>
</div>
```

`cacheEls()` should cache:

- `re.options`
- `re.optionsBody`
- `re.optionsHint`
- `re.optionControls = new Map()`

It should stop depending on:

- `re.optGenerateType`
- `re.optEnablePbr`
- `re.optFaceCount`

`renderModelOptions()` should:

- read `selectedModel().options`
- hide `#reconstruct-options` when no descriptor list exists or the list is empty
- show the legacy Output selector only for models with no catalog options
- hide the legacy Output selector for descriptor-driven models
- clear `re.optionsBody`
- clear `re.optionControls`
- render one row per descriptor
- store each generated control in `re.optionControls` by descriptor key
- attach one shared `change` or `input` listener that recomputes option dependencies

Descriptor kind mapping:

- `enum`: `select` with `allowed_values`
- `boolean`: checkbox input
- `integer`: number input using `min`, `max`, and `step` when present
- `string`: text input by default; use a textarea for `texture_prompt`

Defaults should be applied from each descriptor when a control is created. Missing string defaults should render as an empty string. Missing boolean defaults should render unchecked.

Unknown option kinds are not expected from the current catalog. If an unknown kind appears, render no editable control for it and show a concise inline options hint that the option kind is unsupported.

## Dependency Handling

Use one shared value path for both UI dependency state and submit serialization:

```js
collectOptionValues({ includeIgnored })
isOptionIgnored(descriptor, values)
```

`collectOptionValues({ includeIgnored: true })` reads current control values from `re.optionControls` by descriptor key. It must preserve explicit boolean `false` values. This is required because Meshy `should_texture=false` and `should_remesh=false` are meaningful provider options.

`isOptionIgnored(descriptor, values)` evaluates `descriptor.ignored_when` against the collected values. It should support the current catalog's string and boolean comparisons:

- Hunyuan Pro: `enable_pbr` ignored when `generate_type == "Geometry"`
- Meshy: `enable_pbr` and `texture_prompt` ignored when `should_texture == false`

`applyOptionDependencies()` should:

- collect all values with ignored controls included
- hide rows whose descriptors are currently ignored
- disable controls for hidden rows as defense in depth
- preserve current hidden-control values while the same model remains selected
- update a short hint only when controls disappear because of a dependency

Recommended hint copy:

- Meshy texture gate: `Texture-specific options are hidden while texturing is off.`
- Hunyuan geometry gate: `PBR is hidden for geometry-only output.`

The hint should be hidden when no descriptor is currently ignored. The hint is not a modal and should not add a global list of unavailable options.

Ignored controls are hidden and disabled, but their current UI values are preserved while the same model remains selected. Serialization omits ignored keys. Values reset only when the model/options descriptor set is rebuilt, such as on model change or catalog reload.

## Submit Option Serialization

`optionsForMode()` should serialize from model descriptors, not fixed DOM IDs.

For descriptor-driven models:

- call `collectOptionValues({ includeIgnored: false })`
- return only non-ignored descriptor keys
- include explicit boolean `false`
- include explicit boolean `true`
- parse integer controls as numbers and omit empty integer fields
- omit empty string fields
- include selected enum values when non-empty

For models with no catalog options:

- preserve the existing legacy Output behavior
- `geometry` returns `{ enable_geometry: true }`
- textured output returns `{ enable_pbr: true }` only for models with `supports_pbr`

The backend validator will still fill descriptor defaults. The UI should nevertheless submit explicit user-visible values so the request matches what the user selected, especially for Meshy booleans.

## Mode Interaction

The model filtering behavior by reconstruction mode stays unchanged:

- T3D remains disabled until a provider lands
- I3D uses the loaded model list
- MV3D filters to `supports_multi_view`

If the experimental toggle changes the loaded model set, the current mode's existing model selection path should run again. This keeps I3D and MV3D behavior consistent with the current code.

Meshy is single-image only, so it should appear in I3D when experimental models are enabled and should not appear in MV3D.

## Vision Panel Safeguards

This change must respect the existing Vision dark-panel mitigations.

The implementation should preserve the current resource-loading and panel-stability patterns:

- every id cached with `$("...")` in `app.js` must have a matching element in `index.html`
- new dynamic controls should be created under an existing cached container, not by adding many hard-coded cached ids
- use the existing `.hidden` class for section and row hiding because it is the established `display: none !important` primitive in this WebView
- do not introduce overlay effects, grain layers, blend modes, or dark backgrounds that affect preview, result, gallery, modal, or Reconstruct media inspection
- do not restructure the top-level Vision panel, WebView host, or presentation reconciler behavior
- keep Reconstruct layout bounded with existing `minmax(0, ...)`, `min-width: 0`, and panel background conventions

Tests should keep or extend id-integrity coverage for newly cached Reconstruct ids. The goal is to prevent the class of regressions where a missing HTML id nulls a cached element and blanks the Vision panel during initialization.

## Tests

Add or update source-level UI tests in `src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs`.

Required tests:

- HTML contains `#reconstruct-options-body`.
- HTML contains the experimental model toggle.
- JS no longer depends on fixed cached fields `re.optGenerateType`, `re.optEnablePbr`, or `re.optFaceCount`.
- JS stores option controls by descriptor key, for example `re.optionControls = new Map()`.
- JS calls the models op with `include_experimental` when the toggle is enabled.
- JS submit payload includes `allow_experimental_model` for selected non-stable models visible through the experimental toggle.
- JS has a shared `collectOptionValues` path.
- JS has a shared `isOptionIgnored` path.
- JS preserves explicit `false` booleans during option serialization.
- Catalog/backend tests continue to assert Meshy option keys; UI tests assert descriptor-driven rendering by kind and dependency metadata rather than hard-coding Meshy keys in `app.js`.
- UI source tests may assert `texture_prompt` only as the deliberate textarea special case.
- JS dependency handling references `ignored_when`.
- Newly cached Reconstruct ids exist in `index.html`.

Backend tests are already mostly in place:

- `ReconstructionOpHandlerTests.DispatchAsync_Models_ReturnsDefaultStableCatalog` verifies Meshy is excluded by default.
- `ReconstructionOpHandlerTests.Models_ExposesOptionsAndCapabilityFlags_ForPro` covers option descriptor serialization.
- `ReconstructionModelCatalogTests.ProductionCatalog_Meshy_StaysExperimental_WithOptionKeys` covers Meshy catalog keys.
- `ReconstructionOptionsValidatorTests` covers string options, Meshy defaults, boolean ignored gates, and Hunyuan geometry gating.

Only add backend tests if implementation discovers an untested backend contract. The expected implementation should be UI-only.

## Risks

- The UI tests are source-string oriented. Keep helper names stable and explicit enough for the tests to assert the important contracts without becoming brittle around layout details.
- Experimental visibility and submit authorization can drift if `include_experimental` and `allow_experimental_model` are handled separately. The design prevents this by tying both to the same toggle and selected model status.
- Hiding ignored rows can feel surprising if done without context. A short inline hint should appear only while dependency-hidden rows exist.
- Do not rely on the backend validator alone for UX dependency behavior. The validator is still the final authority, but the UI should not present options that will be ignored.

## Non-Goals

- Do not show every possible reconstruction option globally.
- Do not add a modal.
- Do not change reconstruction catalog schema.
- Do not change provider request semantics.
- Do not change native plugin code.
- Do not move behavior across the native/managed boundary.
- Do not add external dependencies.
- Do not build or claim Rhino/MFC verification for this UI-only spec.
