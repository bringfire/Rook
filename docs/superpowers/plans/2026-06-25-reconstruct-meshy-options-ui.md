# Reconstruct Meshy Options UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose Meshy v6 image-to-3D in the Reconstruct UI through an explicit experimental-model opt-in and render reconstruction catalog options generically.

**Architecture:** Keep the change inside the managed Vision web surface resources and source-level UI tests. The backend catalog, handler, and reconstruction option validator already expose and validate the required model/option metadata, so the UI should consume those descriptors rather than hard-code provider-specific options. Preserve the existing dark-panel mitigations by maintaining cached id integrity, using `.hidden`, and avoiding layout/host rewrites.

**Tech Stack:** C# xUnit source tests (`src/Rook.Tests`), embedded HTML/CSS/JS resources under `src/Rook/UI/Vision/Resources`, WebView-hosted vanilla JavaScript.

---

## Scope And File Map

Modify only these files:

- `src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs`
  - Source-assertion tests for Reconstruct HTML/JS/CSS contracts.
  - Replace fixed Hunyuan option tests with generic descriptor-driven tests.
- `src/Rook/UI/Vision/Resources/index.html`
  - Add the `Experimental models` toggle.
  - Replace fixed option controls with `#reconstruct-options-body` and `#reconstruct-options-hint`.
- `src/Rook/UI/Vision/Resources/app.js`
  - Cache new Reconstruct ids.
  - Load models with `include_experimental` only when the toggle is enabled.
  - Render option controls from model descriptors into a keyed `Map`.
  - Collect/serialize option values generically.
  - Apply `ignored_when` dependencies using the same value collector used for submit serialization.
  - Add `allow_experimental_model` to submit only for non-stable selected models visible through the toggle.
- `src/Rook/UI/Vision/Resources/styles.css`
  - Add small, bounded styles for dynamically rendered option rows and the experimental toggle if existing styles do not cover them.

Do not modify native code, reconstruction backend code, catalog JSON, WebView host/reconciler code, or project files.

## Test Commands

Use targeted source tests while iterating:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructScaffoldSourceTests" -v minimal
```

Use the broader Vision UI source sweep before completion:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.UI.Vision" -v minimal
```

Use the existing reconstruction backend contracts as a final guard:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionOpHandlerTests|FullyQualifiedName~ReconstructionModelCatalogTests|FullyQualifiedName~ReconstructionOptionsValidatorTests" -v minimal
```

`dotnet test` on `src/Rook.Tests` may deploy `Rook.rhp` into `%AppData%`; run with Rhino closed.

---

### Task 1: Experimental Toggle Loads Experimental Catalog

**Files:**
- Modify: `src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs`
- Modify: `src/Rook/UI/Vision/Resources/index.html`
- Modify: `src/Rook/UI/Vision/Resources/app.js`

- [ ] **Step 1: Write failing tests for the experimental toggle and catalog load**

In `src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs`, add these tests near the existing Pro options section, before serialization/dependency tests:

```csharp
[Fact]
public void IndexHtml_ReconstructExperimentalToggle_Present()
{
    var html = ReadVisionResource("index.html");
    Assert.Contains("id=\"reconstruct-include-experimental\"", html);
    Assert.Contains("Experimental models", html);
}

[Fact]
public void AppJs_ReconstructExperimentalToggle_LoadsModelsWithIncludeExperimental()
{
    var js = ReadVisionResource("app.js");
    Assert.Contains("re.includeExperimental = $(\"reconstruct-include-experimental\");", js);
    Assert.Contains("let includeExperimentalModels = false;", js);
    Assert.Contains("include_experimental: true", js);
    Assert.Contains("loadModels(true)", js);
    Assert.Contains("re.includeExperimental.checked", js);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~IndexHtml_ReconstructExperimentalToggle_Present|FullyQualifiedName~AppJs_ReconstructExperimentalToggle_LoadsModelsWithIncludeExperimental" -v minimal
```

Expected: FAIL because the HTML id, cached JS field, toggle state, and `include_experimental` request are not present.

- [ ] **Step 3: Add the experimental toggle HTML**

In `src/Rook/UI/Vision/Resources/index.html`, inside the Reconstruct `Model` field, immediately after `#reconstruct-model-hint`, add:

```html
<label class="reconstruct-option-row reconstruct-experimental-toggle" for="reconstruct-include-experimental">
  <span class="reconstruct-option-label">Experimental models</span>
  <input type="checkbox" id="reconstruct-include-experimental" />
</label>
```

Do not add a modal or a global experimental model panel.

- [ ] **Step 4: Cache and wire the experimental toggle**

In `src/Rook/UI/Vision/Resources/app.js`, add state near the existing Reconstruct state:

```js
let includeExperimentalModels = false;
```

In `cacheEls()`, add:

```js
re.includeExperimental = $("reconstruct-include-experimental");
```

In `wireEvents()`, after the model-select listener, add:

```js
re.includeExperimental.addEventListener("change", async () => {
    includeExperimentalModels = !!re.includeExperimental.checked;
    modelsLoaded = false;
    await loadModels(true);
    updateReconstructModelForMode(reconstructMode);
    renderModelOptions();
});
```

Change `loadModels()` to accept a force flag and build request args from the toggle:

```js
async function loadModels(force) {
    if (modelsLoaded && !force) return;
    const previousModelId = selectedModelId();
    try {
        const args = includeExperimentalModels ? { include_experimental: true } : {};
        const data = await reconstructionBridgeCall("models", args);
        models = Array.isArray(data.models) ? data.models : [];
    } catch (e) {
        models = [];
    }
    updateReconstructModelForMode(reconstructMode, previousModelId);
    renderModelOptions();
    modelsLoaded = true;
}
```

Update `updateReconstructModelForMode` to accept `preferredModelId` and preserve it if still available:

```js
function updateReconstructModelForMode(mode, preferredModelId) {
    if (mode === "t3d") {
        re.modelSelect.innerHTML = "<option value=\"\" disabled selected>No models available for this mode yet</option>";
    } else if (mode === "mv3d") {
        const mv = models.filter(m => m.supports_multi_view);
        if (mv.length === 0) {
            re.modelSelect.innerHTML = "<option value=\"\" disabled selected>No models available for this mode yet</option>";
        } else {
            re.modelSelect.innerHTML = mv.map(buildModelOption).join("");
            re.modelSelect.value = mv.some(m => m.model_id === preferredModelId) ? preferredModelId : mv[0].model_id;
        }
        updateModelHint();
    } else {
        if (models.length === 0) {
            re.modelSelect.innerHTML = "<option value=\"\" disabled selected>No models available</option>";
        } else {
            re.modelSelect.innerHTML = models.map(buildModelOption).join("");
            re.modelSelect.value = models.some(m => m.model_id === preferredModelId) ? preferredModelId : models[0].model_id;
        }
        updateModelHint();
    }
}
```

Leave existing `setReconstructMode(reconstructMode)` calls intact, but allow them to call `updateReconstructModelForMode(mode)` without a preferred id.

- [ ] **Step 5: Run test to verify it passes**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~IndexHtml_ReconstructExperimentalToggle_Present|FullyQualifiedName~AppJs_ReconstructExperimentalToggle_LoadsModelsWithIncludeExperimental" -v minimal
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs src/Rook/UI/Vision/Resources/index.html src/Rook/UI/Vision/Resources/app.js
git commit -m "feat: load experimental reconstruct models by opt-in"
```

---

### Task 2: Dynamic Option Container And Id Integrity

**Files:**
- Modify: `src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs`
- Modify: `src/Rook/UI/Vision/Resources/index.html`
- Modify: `src/Rook/UI/Vision/Resources/app.js`
- Modify: `src/Rook/UI/Vision/Resources/styles.css`

- [ ] **Step 1: Replace fixed-control tests with failing dynamic-container tests**

In `src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs`, replace `IndexHtml_ReconstructOptions_ExposeGenerateTypePbrFaceCount` with:

```csharp
[Fact]
public void IndexHtml_ReconstructOptions_UsesDynamicOptionsBody()
{
    var html = ReadVisionResource("index.html");
    Assert.Contains("id=\"reconstruct-options\"", html);
    Assert.Contains("id=\"reconstruct-options-body\"", html);
    Assert.Contains("id=\"reconstruct-options-hint\"", html);
    Assert.DoesNotContain("id=\"reconstruct-opt-generate-type\"", html);
    Assert.DoesNotContain("id=\"reconstruct-opt-enable-pbr\"", html);
    Assert.DoesNotContain("id=\"reconstruct-opt-face-count\"", html);
}
```

Add this id-integrity guard near the existing helper section:

```csharp
[Theory]
[InlineData("reconstruct-include-experimental")]
[InlineData("reconstruct-options")]
[InlineData("reconstruct-options-body")]
[InlineData("reconstruct-options-hint")]
public void EveryCachedReconstructOptionsId_ExistsInIndexHtml(string id)
{
    var js = ReadVisionResource("app.js");
    var html = ReadVisionResource("index.html");
    Assert.Contains($"$(\"{id}\")", js);
    Assert.Contains($"id=\"{id}\"", html);
}
```

Replace `AppJs_RendersCatalogOptions_AndGatesPbrUnderGeometry` with:

```csharp
[Fact]
public void AppJs_RendersCatalogOptions_FromDescriptorMap()
{
    var js = ReadVisionResource("app.js");
    Assert.Contains("re.optionsBody = $(\"reconstruct-options-body\");", js);
    Assert.Contains("re.optionsHint = $(\"reconstruct-options-hint\");", js);
    Assert.Contains("re.optionControls = new Map();", js);
    Assert.Contains("function renderOptionControl(", js);
    Assert.Contains("re.optionControls.set(d.key", js);
    Assert.Contains("case \"enum\":", js);
    Assert.Contains("case \"boolean\":", js);
    Assert.Contains("case \"integer\":", js);
    Assert.Contains("case \"string\":", js);
    Assert.Contains("texture_prompt", js);
    Assert.DoesNotContain("re.optGenerateType", js);
    Assert.DoesNotContain("re.optEnablePbr", js);
    Assert.DoesNotContain("re.optFaceCount", js);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~IndexHtml_ReconstructOptions_UsesDynamicOptionsBody|FullyQualifiedName~EveryCachedReconstructOptionsId_ExistsInIndexHtml|FullyQualifiedName~AppJs_RendersCatalogOptions_FromDescriptorMap" -v minimal
```

Expected: FAIL because fixed controls still exist and `re.optionControls` / `renderOptionControl` do not.

- [ ] **Step 3: Replace fixed options HTML with a dynamic body**

In `src/Rook/UI/Vision/Resources/index.html`, replace the current `#reconstruct-options` block with:

```html
<div class="reconstruct-field hidden" id="reconstruct-options">
  <label class="reconstruct-label">Options</label>
  <div id="reconstruct-options-body"></div>
  <span id="reconstruct-options-hint" class="option-hint hidden"></span>
</div>
```

- [ ] **Step 4: Replace fixed option caches with dynamic caches**

In `cacheEls()`, remove:

```js
re.optGenerateType = $("reconstruct-opt-generate-type");
re.optEnablePbr = $("reconstruct-opt-enable-pbr");
re.optFaceCount = $("reconstruct-opt-face-count");
```

Add:

```js
re.optionsBody = $("reconstruct-options-body");
re.optionsHint = $("reconstruct-options-hint");
re.optionControls = new Map();
```

In `wireEvents()`, remove:

```js
re.optGenerateType.addEventListener("change", applyGenerateTypeGating);
```

- [ ] **Step 5: Add generic option rendering helpers**

In `app.js`, replace the fixed-control body of `renderModelOptions()` and remove `applyGenerateTypeGating()`. Add these helpers in the Reconstruct module near `renderModelOptions()`:

```js
function optionInputId(key) {
    return "reconstruct-option-" + String(key || "").replace(/[^a-zA-Z0-9_-]/g, "-");
}

function renderOptionControl(d) {
    const id = optionInputId(d.key);
    const def = d.default;
    switch (d.kind) {
        case "enum": {
            const values = Array.isArray(d.allowed_values) ? d.allowed_values : [];
            const value = def != null ? String(def) : (values[0] || "");
            return `
                <div class="select-wrapper">
                  <select id="${escapeAttr(id)}" data-option-key="${escapeAttr(d.key)}">
                    ${values.map(v => `<option value="${escapeAttr(v)}">${escapeHtml(v)}</option>`).join("")}
                  </select>
                </div>`;
        }
        case "boolean":
            return `<input type="checkbox" id="${escapeAttr(id)}" data-option-key="${escapeAttr(d.key)}"${def === true ? " checked" : ""} />`;
        case "integer": {
            const attrs = [
                `id="${escapeAttr(id)}"`,
                `data-option-key="${escapeAttr(d.key)}"`,
                "type=\"number\"",
                d.min != null ? `min="${escapeAttr(d.min)}"` : "",
                d.max != null ? `max="${escapeAttr(d.max)}"` : "",
                d.step != null ? `step="${escapeAttr(d.step)}"` : "",
                def != null ? `value="${escapeAttr(def)}"` : "",
            ].filter(Boolean).join(" ");
            return `<input ${attrs} />`;
        }
        case "string": {
            if (d.key === "texture_prompt") {
                return `<textarea id="${escapeAttr(id)}" data-option-key="${escapeAttr(d.key)}" rows="2">${escapeHtml(def == null ? "" : String(def))}</textarea>`;
            }
            return `<input type="text" id="${escapeAttr(id)}" data-option-key="${escapeAttr(d.key)}" value="${escapeAttr(def == null ? "" : String(def))}" />`;
        }
        default:
            return `<span class="option-hint">Unsupported option kind: ${escapeHtml(d.kind || "")}</span>`;
    }
}

function renderModelOptions() {
    if (!re.options) return;
    const model = selectedModel();
    const opts = (model && Array.isArray(model.options)) ? model.options : null;
    re.optionControls.clear();
    if (re.optionsBody) re.optionsBody.innerHTML = "";
    if (re.optionsHint) {
        re.optionsHint.textContent = "";
        re.optionsHint.classList.add("hidden");
    }
    if (!opts || opts.length === 0) {
        re.options.classList.add("hidden");
        if (re.outputField) re.outputField.classList.remove("hidden");
        return;
    }
    re.options.classList.remove("hidden");
    if (re.outputField) re.outputField.classList.add("hidden");
    re.optionsBody.innerHTML = opts.map(d => {
        const id = optionInputId(d.key);
        return `
          <div class="reconstruct-option-row" data-option-row="${escapeAttr(d.key)}">
            <label class="reconstruct-option-label" for="${escapeAttr(id)}">${escapeHtml(d.label || d.key)}</label>
            ${renderOptionControl(d)}
          </div>`;
    }).join("");
    for (const d of opts) {
        const control = re.optionsBody.querySelector(`[data-option-key="${cssEscape(d.key)}"]`);
        if (!control) continue;
        if (d.kind === "enum" && d.default != null) control.value = String(d.default);
        re.optionControls.set(d.key, { descriptor: d, control, row: control.closest(".reconstruct-option-row") });
        control.addEventListener(d.kind === "string" ? "input" : "change", applyOptionDependencies);
    }
    applyOptionDependencies();
}
```

Add a small selector escaping helper if the file does not already have one:

```js
function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(String(value));
    return String(value).replace(/["\\]/g, "\\$&");
}
```

Add these temporary no-op helpers in the same area so the UI remains bootable before Tasks 3 and 4 replace them with real behavior:

```js
function isOptionIgnored(descriptor, values) {
    return false;
}

function applyOptionDependencies() {
}
```

- [ ] **Step 6: Add bounded dynamic-option styles**

In `src/Rook/UI/Vision/Resources/styles.css`, near existing Reconstruct option styles, add:

```css
.reconstruct-options-body,
#reconstruct-options-body {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
}

.reconstruct-option-row input[type="text"],
.reconstruct-option-row input[type="number"],
.reconstruct-option-row textarea {
    width: min(100%, 260px);
    padding: 8px 10px;
    background: var(--paper);
    border: 1px solid var(--rule);
    color: var(--ink);
    font-family: var(--type-mono);
    font-size: 13px;
}

.reconstruct-option-row textarea {
    resize: vertical;
    min-height: 52px;
}

.reconstruct-option-row.hidden {
    display: none !important;
}

.reconstruct-experimental-toggle {
    justify-content: flex-start;
}
```

Do not add dark backgrounds, overlays, blend modes, or global panel restyling.

- [ ] **Step 7: Run test to verify it passes**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~IndexHtml_ReconstructOptions_UsesDynamicOptionsBody|FullyQualifiedName~EveryCachedReconstructOptionsId_ExistsInIndexHtml|FullyQualifiedName~AppJs_RendersCatalogOptions_FromDescriptorMap" -v minimal
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs src/Rook/UI/Vision/Resources/index.html src/Rook/UI/Vision/Resources/app.js src/Rook/UI/Vision/Resources/styles.css
git commit -m "feat: render reconstruct options from descriptors"
```

---

### Task 3: Descriptor Serialization Preserves Explicit False

**Files:**
- Modify: `src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs`
- Modify: `src/Rook/UI/Vision/Resources/app.js`

- [ ] **Step 1: Write failing serialization test**

Add this test to `ReconstructScaffoldSourceTests.cs` after `AppJs_RendersCatalogOptions_FromDescriptorMap`:

```csharp
[Fact]
public void AppJs_SerializesDescriptorOptions_AndPreservesExplicitFalseBooleans()
{
    var js = ReadVisionResource("app.js");
    Assert.Contains("function collectOptionValues({ includeIgnored })", js);
    Assert.Contains("control.checked", js);
    Assert.Contains("values[d.key] = control.checked;", js);
    Assert.Contains("Number.isNaN", js);
    Assert.Contains("collectOptionValues({ includeIgnored: false })", js);
    Assert.DoesNotContain("if (re.optEnablePbr.checked) o.enable_pbr = true;", js);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~AppJs_SerializesDescriptorOptions_AndPreservesExplicitFalseBooleans" -v minimal
```

Expected: FAIL because `collectOptionValues` does not exist and old fixed serialization remains.

- [ ] **Step 3: Implement descriptor value collection and serialization**

In `app.js`, add this helper near the option rendering helpers:

```js
function collectOptionValues({ includeIgnored }) {
    const model = selectedModel();
    const opts = (model && Array.isArray(model.options)) ? model.options : [];
    const values = {};
    const allValues = {};

    for (const d of opts) {
        const entry = re.optionControls.get(d.key);
        if (!entry || !entry.control) continue;
        const control = entry.control;
        let value;
        if (d.kind === "boolean") {
            value = control.checked;
        } else if (d.kind === "integer") {
            if (control.value === "") {
                continue;
            }
            const parsed = parseInt(control.value, 10);
            if (Number.isNaN(parsed)) {
                continue;
            }
            value = parsed;
        } else if (d.kind === "string") {
            const text = control.value.trim();
            if (!text) {
                continue;
            }
            value = text;
        } else if (d.kind === "enum") {
            if (!control.value) {
                continue;
            }
            value = control.value;
        } else {
            continue;
        }
        allValues[d.key] = value;
    }

    for (const d of opts) {
        if (!Object.prototype.hasOwnProperty.call(allValues, d.key)) continue;
        if (!includeIgnored && isOptionIgnored(d, allValues)) continue;
        values[d.key] = allValues[d.key];
    }

    return values;
}
```

Keep the no-op `isOptionIgnored(descriptor, values)` from Task 2 for now. Task 4 will replace it with descriptor-driven `ignored_when` handling. This keeps `optionsForMode()` callable after Task 3 without introducing dependency behavior before its red test exists.

Update `optionsForMode()` descriptor path to:

```js
function optionsForMode() {
    const model = selectedModel();
    if (model && Array.isArray(model.options) && model.options.length > 0) {
        return collectOptionValues({ includeIgnored: false });
    }
    if (outputMode === "geometry") return { enable_geometry: true };
    return model && model.supports_pbr ? { enable_pbr: true } : {};
}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~AppJs_SerializesDescriptorOptions_AndPreservesExplicitFalseBooleans" -v minimal
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs src/Rook/UI/Vision/Resources/app.js
git commit -m "feat: serialize reconstruct descriptor options"
```

---

### Task 4: ignored_when Dependency Behavior Preserves Hidden Values

**Files:**
- Modify: `src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs`
- Modify: `src/Rook/UI/Vision/Resources/app.js`

- [ ] **Step 1: Write failing dependency test**

Add this test to `ReconstructScaffoldSourceTests.cs` after the serialization test:

```csharp
[Fact]
public void AppJs_AppliesIgnoredWhenDependencies_WithoutClearingHiddenValues()
{
    var js = ReadVisionResource("app.js");
    Assert.Contains("function isOptionIgnored(descriptor, values)", js);
    Assert.Contains("descriptor.ignored_when", js);
    Assert.Contains("function applyOptionDependencies()", js);
    Assert.Contains("entry.row.classList.toggle(\"hidden\", ignored);", js);
    Assert.Contains("entry.control.disabled = ignored;", js);
    Assert.Contains("Texture-specific options are hidden while texturing is off.", js);
    Assert.Contains("PBR is hidden for geometry-only output.", js);
    Assert.DoesNotContain("entry.control.value = \"\";", js);
    Assert.DoesNotContain("entry.control.checked = false;", js);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~AppJs_AppliesIgnoredWhenDependencies_WithoutClearingHiddenValues" -v minimal
```

Expected: FAIL because dependency helpers are not complete.

- [ ] **Step 3: Implement dependency helpers**

In `app.js`, add these helpers near `collectOptionValues`:

```js
function optionValuesEqual(actual, expected) {
    return actual === expected;
}

function isOptionIgnored(descriptor, values) {
    if (!descriptor || !descriptor.ignored_when) return false;
    const gate = descriptor.ignored_when;
    if (!gate || !gate.key) return false;
    if (!Object.prototype.hasOwnProperty.call(values, gate.key)) return false;
    return optionValuesEqual(values[gate.key], gate.equals);
}

function dependencyHintForIgnored(ignoredDescriptors) {
    if (ignoredDescriptors.some(d => d.ignored_when && d.ignored_when.key === "should_texture")) {
        return "Texture-specific options are hidden while texturing is off.";
    }
    if (ignoredDescriptors.some(d => d.ignored_when && d.ignored_when.key === "generate_type")) {
        return "PBR is hidden for geometry-only output.";
    }
    return "Some options are hidden because they are not used by the current selection.";
}

function applyOptionDependencies() {
    const model = selectedModel();
    const opts = (model && Array.isArray(model.options)) ? model.options : [];
    const values = collectOptionValues({ includeIgnored: true });
    const ignoredDescriptors = [];

    for (const d of opts) {
        const entry = re.optionControls.get(d.key);
        if (!entry || !entry.row || !entry.control) continue;
        const ignored = isOptionIgnored(d, values);
        entry.row.classList.toggle("hidden", ignored);
        entry.control.disabled = ignored;
        if (ignored) ignoredDescriptors.push(d);
    }

    if (re.optionsHint) {
        if (ignoredDescriptors.length > 0) {
            re.optionsHint.textContent = dependencyHintForIgnored(ignoredDescriptors);
            re.optionsHint.classList.remove("hidden");
        } else {
            re.optionsHint.textContent = "";
            re.optionsHint.classList.add("hidden");
        }
    }
}
```

Do not clear hidden controls in this helper. Values reset only when `renderModelOptions()` rebuilds the descriptor set on model change/catalog reload.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~AppJs_AppliesIgnoredWhenDependencies_WithoutClearingHiddenValues" -v minimal
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs src/Rook/UI/Vision/Resources/app.js
git commit -m "feat: apply reconstruct option dependencies"
```

---

### Task 5: Submit Experimental Authorization Gate

**Files:**
- Modify: `src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs`
- Modify: `src/Rook/UI/Vision/Resources/app.js`

- [ ] **Step 1: Write failing submit-gate test**

Add this test to `ReconstructScaffoldSourceTests.cs` after the dependency test:

```csharp
[Fact]
public void AppJs_Submit_AllowsExperimentalOnlyWhenToggleExposesNonStableModel()
{
    var js = ReadVisionResource("app.js");
    Assert.Contains("function shouldAllowExperimentalModel(model)", js);
    Assert.Contains("includeExperimentalModels && model && model.status !== \"stable\"", js);
    Assert.Contains("allow_experimental_model", js);
    Assert.Contains("if (shouldAllowExperimentalModel(mvModel)) submitArgs.allow_experimental_model = true;", js);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~AppJs_Submit_AllowsExperimentalOnlyWhenToggleExposesNonStableModel" -v minimal
```

Expected: FAIL because submit does not include `allow_experimental_model`.

- [ ] **Step 3: Implement submit gate**

In `app.js`, add this helper near `selectedModel()`:

```js
function shouldAllowExperimentalModel(model) {
    return includeExperimentalModels && model && model.status !== "stable";
}
```

In `submit()`, replace the inline object passed to `reconstructionBridgeCall("submit_job", ...)` with a named `submitArgs`:

```js
const submitArgs = {
    source_artifact_id: frontSlot.artifact_id,
    source_role: frontSlot.role || "image",
    model_id: modelId,
    preprocessing_chain: [],
    options: optionsForMode(),
    views: views,
    estimate_requested: false,
};
if (shouldAllowExperimentalModel(mvModel)) submitArgs.allow_experimental_model = true;
const job = await reconstructionBridgeCall("submit_job", submitArgs);
```

Use the existing `mvModel` variable, which already holds `selectedModel()` for submit mode filtering. Do not send `allow_experimental_model: false`; omit the field unless the opt-in condition is true.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~AppJs_Submit_AllowsExperimentalOnlyWhenToggleExposesNonStableModel" -v minimal
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs src/Rook/UI/Vision/Resources/app.js
git commit -m "feat: authorize experimental reconstruct submit"
```

---

### Task 6: Full Reconstruct Source Sweep And Dark-Panel Guard

**Files:**
- Modify only if tests reveal a gap:
  - `src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs`
  - `src/Rook/UI/Vision/Resources/index.html`
  - `src/Rook/UI/Vision/Resources/app.js`
  - `src/Rook/UI/Vision/Resources/styles.css`

- [ ] **Step 1: Run all Reconstruct source tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructScaffoldSourceTests" -v minimal
```

Expected: PASS. If any old fixed-control assertion still fails, update the test to assert the new generic descriptor contract rather than reintroducing fixed option ids.

- [ ] **Step 2: Run broader Vision UI tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.UI.Vision" -v minimal
```

Expected: PASS. Pay special attention to tests that guard:

- cached id integrity
- CSP/resource loading
- queue/layout boundedness
- modal action wrapping
- media preview/result presentation
- panel host desired-visibility behavior

- [ ] **Step 3: Run reconstruction backend contract tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionOpHandlerTests|FullyQualifiedName~ReconstructionModelCatalogTests|FullyQualifiedName~ReconstructionOptionsValidatorTests" -v minimal
```

Expected: PASS. These tests confirm the backend still owns Meshy option-key coverage and option validation.

- [ ] **Step 4: Inspect source for forbidden regressions**

Run:

```powershell
rg -n "reconstruct-opt-generate-type|reconstruct-opt-enable-pbr|reconstruct-opt-face-count|re\\.optGenerateType|re\\.optEnablePbr|re\\.optFaceCount" src/Rook/UI/Vision/Resources src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs
```

Expected: no matches.

Run:

```powershell
rg -n "mix-blend-mode|\\.grain\\s*\\{|background:\\s*#000|filter:\\s*blur|backdrop-filter" src/Rook/UI/Vision/Resources/styles.css
```

Expected: existing known matches only. Do not add any new media-affecting overlay, grain, dark panel, or blur rule for this feature.

- [ ] **Step 5: Commit final test/cleanup changes if any**

If Task 6 required edits:

```powershell
git add src/Rook.Tests/UI/Vision/ReconstructScaffoldSourceTests.cs src/Rook/UI/Vision/Resources/index.html src/Rook/UI/Vision/Resources/app.js src/Rook/UI/Vision/Resources/styles.css
git commit -m "test: verify reconstruct options ui contracts"
```

If Task 6 required no edits, do not create an empty commit.

---

## Completion Criteria

The implementation is complete when:

- Stable models remain the default Reconstruct model list.
- The `Experimental models` toggle calls `models` with `include_experimental: true`.
- Meshy appears only through that explicit toggle.
- Descriptor options render dynamically from `model.options`.
- Fixed Hunyuan-only option ids and cached fields are gone.
- Explicit boolean `false` values are serialized for descriptor-driven options.
- `ignored_when` rows are hidden/disabled, omitted from serialization, and preserve values while the same model remains selected.
- Submit includes `allow_experimental_model: true` only for non-stable selected models visible through the experimental toggle.
- Reconstruct source tests, broader Vision UI tests, and reconstruction backend contract tests pass.
- No Vision dark-panel mitigations are weakened.
