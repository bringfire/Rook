const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, "Fixtures/image-fallback-bridge.json"), "utf8"));
const source = fs.readFileSync(path.resolve(__dirname, "../../../Rook/UI/Vision/Resources/app.js"), "utf8");
class Element {
    constructor() {
        this.value = ""; this.disabled = false; this.textContent = ""; this.options = [];
        this.dataset = {}; this.style = { setProperty() {} };
        const classes = new Set();
        this.classList = { add: v => classes.add(v), remove: v => classes.delete(v),
            contains: v => classes.has(v), toggle(v, on) { if (on) classes.add(v); else classes.delete(v); } };
    }
    set innerHTML(value) {
        this._html = value;
        this.options = [...value.matchAll(/<option value="([^"]*)"([^>]*)>(.*?)<\/option>/g)]
            .map(m => ({ value: m[1], disabled: m[2].includes("disabled"), textContent: m[3] }));
        this.value = this.options.find(o => !o.disabled)?.value || "";
    }
    get innerHTML() { return this._html || ""; }
    querySelectorAll() { return []; }
    addEventListener() {}
}
function harness(catalog = "catalog_fal_only", selected = "gemini-3.1-flash-image-preview", responses = {}) {
    const nodes = Object.fromEntries([...new Set([...source.matchAll(/\bel\.([A-Za-z]\w*)/g)].map(m => m[1]))]
        .map(key => [key, new Element()]));
    const calls = []; let confirms = 0;
    const context = vm.createContext({
        console, setTimeout, clearTimeout, URL, nodes, fixture,
        document: { addEventListener() {}, getElementById() { return null; }, querySelectorAll() { return []; } },
        window: { confirm() { confirms++; return true; }, rookBridge: { async invoke(domain, args) {
            assert.equal(domain, "vision"); calls.push(args);
            const value = responses[args.op];
            assert.ok(value, "Unexpected bridge operation: " + args.op);
            return JSON.parse(JSON.stringify(typeof value === "function" ? value(args) : fixture[value] || value));
        } } }
    });
    vm.runInContext(source, context, { filename: "app.js" });
    context.selected = selected; context.catalog = catalog;
    vm.runInContext([
        'Object.assign(el, nodes);',
        'providerSecretKeyByProvider.set("gemini", "gemini.api_key"); providerSecretKeyByProvider.set("fal", "fal.api_key");',
        'modelCatalog = fixture[catalog].data.models.map(normalizeImageModelDescriptor);',
        'el.modelSelect.value = selected; el.studioModelSelect.value = selected;',
        'el.resolutionSelect.value = "1K"; el.studioResolutionSelect.value = "1K";',
        'el.aspectSelect.value = "auto"; el.studioAspectSelect.value = "auto";',
        'el.prompt.value = "test prompt"; el.studioPrompt.value = "test prompt";',
        'capturedViewport = { file_path: "/synthetic/source.png" }; studioSource = { source: "path", path: "/synthetic/source.png" };'
    ].join("\n"), context);
    return { context, nodes, calls, run: code => vm.runInContext(code, context), get confirms() { return confirms; } };
}
test("fal-only Gemini is selectable without declaring its key valid", () => {
    const h = harness();
    assert.equal(h.run("selectedImageModel(el.modelSelect).credential_availability"), "missing_required_secret");
    assert.equal(h.run("shouldDisableGenerateModel(selectedImageModel(el.modelSelect))"), false);
    assert.equal(h.run("shouldDisableStudioModel(selectedImageModel(el.studioModelSelect))"), false);
    assert.equal(h.run("validateGenerateModelForSubmit(el.modelSelect)"), null);
    assert.equal(h.run("validateStudioModelForSubmit(el.studioModelSelect)"), null);
    assert.ok(h.run("normalizeLegacyAvailableModel(fixture.catalog_fal_only.data.models[0]).fallback_available"));
});
for (const surface of ["generateImage()", "studioGenerate()"]) {
    test(surface + ": neither key blocks submissions", async () => {
        const h = harness("catalog_neither"); await h.run(surface);
        assert.equal(h.calls.length, 0);
        assert.equal(h.run("shouldDisableGenerateModel(selectedImageModel(el.modelSelect))"), true);
    });
    for (const [response, selected, expected] of [
        ["fallback_403", "gemini-3.1-flash-image-preview", null],
        ["fallback_401", "gemini-3.1-flash-image-preview", "invalid"],
        ["fallback_missing", "gemini-3.1-flash-image-preview", null],
        ["direct_missing", "fal-ai/nano-banana-2", null],
        ["direct_401", "fal-ai/nano-banana-2", "invalid"],
        ["direct_403", "fal-ai/nano-banana-2", null],
        ["incompatible", "gemini-3.1-flash-image-preview", null],
        ["materialization_failed", "gemini-3.1-flash-image-preview", null]
    ]) {
        test(surface + ": " + response + " warns only explicitly rejected fal", async () => {
            const h = harness("catalog_fal_only", selected, { generate: response }); await h.run(surface);
            assert.equal(h.calls.length, 1);
            assert.equal(h.run('sessionValidationBySecret.get(secretOverlayKey("fal", "fal.api_key"))') || null, expected);
            assert.equal(h.run('sessionValidationBySecret.has(secretOverlayKey("gemini", "gemini.api_key"))'), false);
            if (!expected) assert.equal(h.run("sessionValidationBySecret.size"), 0);
            const status = surface.startsWith("studio") ? h.nodes.studioStatusMessage : h.nodes.statusMessage;
            if (response.endsWith("missing")) assert.match(status.textContent, /fal.*(configure|settings)|configure.*fal/i);
            assert.doesNotMatch(status.textContent, /Generated with fal.ai/);
            assert.equal(h.confirms, 0);
        });
    }
    test(surface + ": fallback success displays attribution", async () => {
        const h = harness("catalog_fal_only", undefined, { generate: "fallback_success" }); await h.run(surface);
        const status = surface.startsWith("studio") ? h.nodes.studioStatusMessage : h.nodes.statusMessage;
        assert.equal(status.textContent, "Generated with fal.ai"); assert.equal(h.calls.length, 1);
    });
    test(surface + ": Google success keeps its existing notice", async () => {
        const h = harness("catalog_google", undefined, { generate: "primary_success" }); await h.run(surface);
        assert.equal((surface.startsWith("studio") ? h.nodes.studioStatusMessage : h.nodes.statusMessage).textContent, "Image generated.");
    });
}
test("bridge preserves direct fal evidence without a receipt", async () => {
    const h = harness("catalog_fal_only", "fal-ai/nano-banana-2", { generate: "direct_missing" }); let error;
    try { await h.run('bridgeCall("generate", {})'); } catch (e) { error = e; }
    assert.ok(error); assert.equal(error.provider, "fal"); assert.equal(error.image_route == null, true);
    assert.equal(error.credential_failure.kind, "missing"); assert.equal(error.fal_dispatch_state, "not_started");
});
test("restored intent survives job errors without retry or confirmation", async () => {
    const h = harness("catalog_fal_only", undefined, {
        image_generate_start: { success: true, data: { job_id: "11111111-1111-1111-1111-111111111111" } },
        image_job_status: "restored_intent_status"
    }); let error;
    try { await h.run("awaitImageJobResult({}, () => {})"); } catch (e) { error = e; }
    assert.equal(error.fal_dispatch_state, "intent_recorded");
    assert.equal(error.image_route.generation_dispatch_attempted, false);
    assert.match(error.message, /submission outcome is unknown/); assert.equal(error.retryable, false);
    h.context.restoredError = error;
    assert.match(h.run("imageErrorMessage(restoredError)"), /fal\.ai.*submission outcome is unknown/);
    assert.doesNotMatch(h.run("imageErrorMessage(restoredError)"), /before sending|not sent/i);
    assert.equal(h.calls.length, 2); assert.equal(h.confirms, 0);
});
test("job receipt drives fallback notice; provider alone does not", () => {
    const h = harness();
    assert.equal(h.run("imageResultNotice(fixture.job_fallback_result.data)"), "Generated with fal.ai");
    assert.equal(h.run('imageResultNotice({metadata:{provider:"fal"}})'), "Image generated.");
});
test("fresh missing fal stays disabled; refresh preserves selection", () => {
    const h = harness("catalog_neither", "fal-ai/nano-banana-2");
    assert.equal(h.run("shouldDisableGenerateModel(selectedImageModel(el.modelSelect))"), true);
    h.run("modelCatalog = fixture.catalog_fal_only.data.models.map(normalizeImageModelDescriptor); populateImageModelDropdowns(modelCatalog)");
    assert.equal(h.nodes.modelSelect.value, "fal-ai/nano-banana-2");
    h.run('markProviderCredentialInvalid("fal")'); assert.equal(h.nodes.modelSelect.value, "fal-ai/nano-banana-2");
    h.run('clearSecretOverlay("fal", "fal.api_key")'); assert.equal(h.run("sessionValidationBySecret.size"), 0);
});
for (const [fixtureKey, kind] of [["direct_job_missing", "missing"], ["direct_job_401", "rejected"], ["direct_job_403", null]]) {
    test(fixtureKey + " preserves evidence through the job error consumer", async () => {
        const h = harness("catalog_fal_only", "fal-ai/nano-banana-2", {
            image_generate_start: { success: true, data: { job_id: "11111111-1111-1111-1111-111111111111" } },
            image_job_status: fixtureKey
        }); let error;
        try { await h.run("awaitImageJobResult({}, () => {})"); } catch (e) { error = e; }
        assert.equal(error.provider, "fal"); assert.equal(error.image_route == null, true);
        assert.equal(error.credential_failure?.kind || null, kind);
        h.context.jobError = error;
        h.run("applyImageCredentialWarning(jobError, selectedImageModel(el.modelSelect))");
        assert.equal(h.run('sessionValidationBySecret.get(secretOverlayKey("fal", "fal.api_key"))') || null,
            kind === "rejected" ? "invalid" : null);
        assert.equal(h.run('sessionValidationBySecret.has(secretOverlayKey("gemini", "gemini.api_key"))'), false);
        assert.equal(h.calls.length, 2);
    });
}
test("text credential warnings cannot disable a mapped image fallback", () => {
    const h = harness();
    h.run('markProviderCredentialInvalid("gemini")');
    assert.equal(h.run("shouldDisableGenerateModel(selectedImageModel(el.modelSelect))"), false);
    assert.equal(h.run("selectedImageModel(el.modelSelect).credential_availability"), "missing_required_secret");
});
test("model and settings displays disclose configured automatic fallback", () => {
    const h = harness();
    const rendered = h.run("buildImageModelOption(selectedImageModel(el.modelSelect), false)");
    assert.match(rendered, /fal\.ai fallback/i);
    assert.match(rendered, /configured/i);
    assert.match(h.run('providerHelpText("gemini")'), /Nano Banana.*fal\.ai.*automatically/i);
    h.run("modelCatalog = fixture.catalog_neither.data.models.map(normalizeImageModelDescriptor)");
    assert.match(h.run("validateGenerateModelForSubmit(el.modelSelect)"), /Gemini or fal\.ai key/);
    assert.match(h.run("validateStudioModelForSubmit(el.studioModelSelect)"), /Gemini or fal\.ai key/);
});
for (const response of ["incompatible", "materialization_failed"]) {
    for (const surface of ["generateImage()", "studioGenerate()"]) {
        test(surface + ": " + response + " displays effective fal attribution without claiming a send", async () => {
            const h = harness("catalog_fal_only", undefined, { generate: response }); await h.run(surface);
            const status = surface.startsWith("studio") ? h.nodes.studioStatusMessage : h.nodes.statusMessage;
            assert.match(status.textContent, /fal\.ai/i);
            if (response === "incompatible") assert.match(status.textContent, /before (sending|dispatch)/i);
            assert.doesNotMatch(status.textContent, /Generated with fal.ai/);
            assert.equal(h.run("sessionValidationBySecret.size"), 0);
        });
    }
}
