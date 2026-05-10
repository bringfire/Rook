// Rook Vision — Pattern A WebUI
//
// All network-style calls leave this file through `bridgeCall()`, which
// goes through `window.rookBridge.invoke("vision", {op, ...})`. There
// are no `fetch()` calls, no XHR, no localhost — the CSP enforces
// `connect-src 'none'`. The Vision WebSurface routes each op to the
// correct VisionHandler dispatcher (async / UI-thread / off-UI).
//
// Lifted and trimmed from SA_Banana's WebUI (image track only). Video
// functionality — Veo client, job manager, interpolation modes, cost
// confirmation, NLE handoffs — is intentionally absent. See PR-7b for
// the lift scope.

// ─── Bridge ───────────────────────────────────────────────────────

/**
 * Invoke a Vision op over the JS↔C# bridge. Returns the dispatcher's
 * response data on success (`success: true`) or throws with the
 * failure message on `success: false`. Every call site should
 * `try/catch` and surface the error via the local status area.
 */
async function bridgeCall(op, args) {
    if (!window.rookBridge || !window.rookBridge.invoke) {
        throw new Error("Bridge unavailable — is this running inside Rook?");
    }
    const payload = Object.assign({ op }, args || {});
    const response = await window.rookBridge.invoke("vision", payload);
    if (!response || typeof response !== "object") {
        throw new Error("Vision response was not an object.");
    }
    if (response.success === true) {
        return response.data;
    }
    // PR-V3: surface structured errors from VideoOpHandler.FailWithError —
    // the response data carries {code, message, retryable, field} so the
    // UI can show typed, field-specific feedback. The thrown error keeps
    // backward compatibility (string-y `.message` still works for callers
    // that only display it) but adds .code/.field/.retryable so video
    // forms can highlight the offending input.
    const data = response.data;
    let err;
    if (typeof data === "string") {
        err = new Error(data);
    } else if (data && typeof data === "object" && typeof data.message === "string") {
        err = new Error(data.message);
        err.code = data.code;
        err.field = data.field;
        err.retryable = data.retryable;
    } else {
        err = new Error("Vision op failed.");
    }
    throw err;
}

// Helper for status strips: render a structured error's user-facing
// text. Includes the offending field where present so the user can
// see "options.person_generation: ..." rather than just the message.
function errorToText(e) {
    if (!e) return "Vision op failed.";
    if (e.field) return `${e.field}: ${e.message}`;
    return e.message || "Vision op failed.";
}

// ─── State ────────────────────────────────────────────────────────

let currentView = "generate";
let generateReferences = [];          // [{ path, thumbnail_base64, thumbnail_mime_type }]
// `studioSource` carries what Generate calls `input_image_path`.
// Two entry paths produce it — the OS file picker (path + inline
// thumbnail base64) and an in-process depth-map capture (path +
// artifact id, preview served via /blob/{id}/image). Shape:
//   { path, previewSrc, label, source: "picker" | "depth" }
let studioSource = null;
let studioReferences = [];
let latestArtifactId = null;          // id of the most-recently generated image (Generate view)
let latestStudioArtifactId = null;    // same, Studio view
let galleryItems = [];                // cached list for modal lookup
let modalArtifact = null;             // currently-open gallery item
let modalDisplayRole = null;          // blob role currently rendered in the modal image
let modelCatalog = [];                 // [{ short_name, supported_resolutions, ... }]
const sessionValidationBySecret = new Map();
const providerSecretKeyByProvider = new Map();

// Viewport capture output (artifact envelope, keyed by view so we can
// re-feed its file_path into `generate` as `input_image_path`).
let capturedViewport = null;          // { artifact_id, file_path, ... } | null
let isCapturingViewport = false;
let viewportOptionsByValue = new Map(); // select value -> { width, height }

// ─── DOM ──────────────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);
const $$ = (sel) => document.querySelectorAll(sel);

const el = {};
document.addEventListener("DOMContentLoaded", init);

// ─── Navigation ───────────────────────────────────────────────────

function switchView(view) {
    currentView = view;
    $$(".nav-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.view === view);
    });
    $$(".view").forEach(v => {
        v.classList.toggle("active", v.id === `${view}-view`);
    });

    if (view === "gallery") loadGallery();
    if (view === "settings") loadSettingsOverview();
    if (view === "video") loadVideoView();
}

// ─── Generate View ────────────────────────────────────────────────

async function loadViewports() {
    try {
        const data = await bridgeCall("list_views");
        viewportOptionsByValue = new Map();
        const views = data.views || [];
        const activeViewport = views.find(v => v && v.is_active) || views[0] || null;
        const activeCaptureSize = activeViewport
            && Number.isFinite(Number(activeViewport.width))
            && Number.isFinite(Number(activeViewport.height))
            && Number(activeViewport.width) > 0
            && Number(activeViewport.height) > 0
            ? {
                width: Number(activeViewport.width),
                height: Number(activeViewport.height),
            }
            : null;
        if (activeCaptureSize) {
            viewportOptionsByValue.set("", activeCaptureSize);
        }
        // First entry is the "capture whatever is currently on screen"
        // sentinel. Open viewport entries use a stable RhinoView id so
        // the backend captures that exact view's live camera/framing;
        // named views keep using `view_name` because they are saved
        // cameras, not open UI panels with their own pixel size.
        const options = ['<option value="" selected>Active view (live)</option>'];
        views.forEach(v => {
            const label = `${v.name} (${v.width}×${v.height})`;
            const hasSize = Number.isFinite(Number(v.width))
                && Number.isFinite(Number(v.height))
                && Number(v.width) > 0
                && Number(v.height) > 0;
            const optionValue = `view:${v.id}`;
            if (v.id && hasSize) {
                viewportOptionsByValue.set(optionValue, {
                    width: Number(v.width),
                    height: Number(v.height),
                    viewId: v.id,
                });
                options.push(`<option value="${escapeAttr(optionValue)}">${escapeHtml(label)}</option>`);
            }
        });
        (data.named_views || []).forEach(v => {
            const optionValue = `named:${v.name}`;
            if (activeCaptureSize) {
                viewportOptionsByValue.set(optionValue, {
                    width: activeCaptureSize.width,
                    height: activeCaptureSize.height,
                    viewName: v.name,
                });
            }
            options.push(`<option value="${escapeAttr(optionValue)}">${escapeHtml(v.name)} (named)</option>`);
        });
        el.viewportSelect.innerHTML = options.join("");
    } catch (e) {
        el.viewportSelect.innerHTML = `<option value="">${escapeHtml(e.message)}</option>`;
    }
}

async function captureViewport() {
    if (isPromptOnlyAsyncImageModel(selectedImageModel(el.modelSelect))) {
        return;
    }
    if (isCapturingViewport) {
        return;
    }

    const selectedKey = el.viewportSelect.value || "";
    isCapturingViewport = true;
    showStatus("Capturing viewport...", "info");
    el.captureBtn.disabled = true;
    // Hide stale dims caption — the `load` handler re-shows it with
    // the new image's dimensions on success.
    if (el.viewportDimsCaption) el.viewportDimsCaption.classList.add("hidden");

    try {
        const args = {};
        const selectedViewport = viewportOptionsByValue.get(selectedKey);
        if (selectedViewport) {
            if (selectedViewport.viewId) args.view_id = selectedViewport.viewId;
            if (selectedViewport.viewName) args.view_name = selectedViewport.viewName;
        }
        const capture = await bridgeCall("preview_viewport", args);

        capturedViewport = capture;
        if (capture.preview_url) {
            el.previewImage.src = `${capture.preview_url}?ts=${Date.now()}`;
            el.previewImage.style.display = "";
            el.previewPlaceholder.classList.add("hidden");
            // Aspect + dims caption get set by the `load` event handler,
            // where naturalWidth/Height are known.
            hideStatus();
        } else {
            showStatus("Capture produced no preview.", "error");
        }
    } catch (e) {
        showStatus(e.message, "error");
    } finally {
        isCapturingViewport = false;
        updateGenerateInputMode();
    }
}

async function enhancePrompt() {
    const prompt = el.prompt.value.trim();
    if (!prompt) { showStatus("Please enter a prompt to enhance.", "error"); return; }
    setEnhancing(el.enhanceBtn, el.enhanceText, el.enhanceSpinner, true);
    el.enhanceHint.textContent = "Enhancing...";
    try {
        const artifact = await bridgeCall("enhance_prompt", {
            prompt,
            context: "Rhino 3D architectural/design viewport render"
        });
        const text = readEnhancedPromptFromArtifact(artifact);
        if (text) {
            el.prompt.dataset.originalPrompt = prompt;
            el.prompt.value = text;
            if (tryRenderEnhancedPromptAsJson(text)) {
                el.enhanceHint.textContent = "Prompt enhanced. Click Edit to modify.";
            } else {
                showPromptAsTextarea();
                el.enhanceHint.textContent = "Prompt enhanced. Original saved.";
            }
        } else {
            el.enhanceHint.textContent = "Enhancement returned no text.";
        }
    } catch (e) {
        el.enhanceHint.textContent = "Enhancement failed.";
        showStatus(e.message, "error");
    } finally {
        setEnhancing(el.enhanceBtn, el.enhanceText, el.enhanceSpinner, false);
    }
}

// ─── Enhanced-prompt rendering ─────────────────────────────────────
// After a successful enhance, Gemini returns a JSON string. Render it
// as an indented, syntax-highlighted <pre> and hide the textarea. The
// textarea still holds the raw text — it's the source-of-truth that
// `generate` reads — so the swap is visual only.

function tryRenderEnhancedPromptAsJson(text) {
    if (!el.promptJsonPreview) return false;
    let parsed;
    try { parsed = JSON.parse(text); }
    catch { return false; }
    if (parsed === null || typeof parsed !== "object") return false;
    el.promptJsonPreview.innerHTML = syntaxHighlightJson(parsed);
    el.prompt.classList.add("hidden");
    el.promptJsonPreview.classList.remove("hidden");
    if (el.editPromptBtn) el.editPromptBtn.classList.remove("hidden");
    return true;
}

function showPromptAsTextarea() {
    if (el.promptJsonPreview) {
        el.promptJsonPreview.classList.add("hidden");
        el.promptJsonPreview.textContent = "";
    }
    el.prompt.classList.remove("hidden");
    if (el.editPromptBtn) el.editPromptBtn.classList.add("hidden");
}

// Security invariant: matched content is entity-escaped before token
// wrapping, so `<`, `>`, `&` in Gemini-emitted keys/values can never
// break out of the span's text context. Never interpolate matched
// content into an HTML *attribute* (e.g. `data-foo="${match}"`) — `"`
// and `'` are not escaped here because tokens only land inside span
// text, never inside attributes.
function syntaxHighlightJson(obj) {
    const json = JSON.stringify(obj, null, 2)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    const highlighted = json.replace(
        /("(\\u[0-9A-Fa-f]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
        (match) => {
            let cls = "json-number";
            if (/^"/.test(match)) {
                cls = /:$/.test(match) ? "json-key" : "json-string";
            } else if (/true|false/.test(match)) {
                cls = "json-boolean";
            } else if (/null/.test(match)) {
                cls = "json-null";
            }
            return `<span class="${cls}">${match}</span>`;
        }
    );
    // Promote keys whose value is an object or array to a parent-key
    // class so structural headers visually outrank leaf keys. The
    // tokenizer above can't see across tokens, so this is a second
    // pass: any `json-key` span immediately followed by whitespace +
    // `{` or `[` is rewrapped with the additional class.
    const withHierarchy = highlighted.replace(
        /<span class="json-key">("[^"]+":)<\/span>(\s+[{[])/g,
        '<span class="json-key json-key-parent">$1</span>$2'
    );
    // Wrap each logical line in a block with its JSON depth as a CSS
    // custom property, then strip the leading whitespace.
    //
    // Key-value lines split into <key-prefix> + <value-block> so CSS
    // can use flex layout to align wrapped value text under the
    // value's first character (the prefix stays inline with
    // white-space: nowrap; the value-block wraps within its own flex
    // item width). Non-KV lines (bare brackets, array elements) keep
    // the simpler hanging indent on .json-line itself.
    return withHierarchy.split("\n").map(line => {
        const leading = (line.match(/^ */) || [""])[0].length;
        const depth = Math.floor(leading / 2);
        const content = line.slice(leading);
        const kvMatch = content.match(/^(<span class="json-key[^"]*">"[^"]+":<\/span>\s+)(.+)$/);
        if (kvMatch) {
            return `<div class="json-line json-line-kv" style="--json-depth:${depth}">` +
                   `<span class="json-key-prefix">${kvMatch[1]}</span>` +
                   `<span class="json-value-block">${kvMatch[2]}</span>` +
                   `</div>`;
        }
        return `<div class="json-line" style="--json-depth:${depth}">${content}</div>`;
    }).join("");
}

function updateViewportDimsCaption() {
    if (!el.viewportDimsCaption) return;
    const w = el.previewImage && el.previewImage.naturalWidth;
    const h = el.previewImage && el.previewImage.naturalHeight;
    if (w && h) {
        el.viewportDimsCaption.textContent = `${w} × ${h}`;
        el.viewportDimsCaption.classList.remove("hidden");
    } else {
        el.viewportDimsCaption.classList.add("hidden");
    }
}

function readEnhancedPromptFromArtifact(artifact) {
    // CSP `connect-src 'none'` blocks fetch/XHR against the virtual
    // host, so the blob under role "prompt" isn't reachable from JS.
    // VisionHandler.EnhancePromptAsync copies the enhanced text into
    // the artifact metadata (`metadata.enhanced_prompt`) specifically
    // so bridge consumers can read it without a secondary request.
    if (!artifact || !artifact.metadata) return null;
    const text = artifact.metadata.enhanced_prompt;
    return typeof text === "string" && text.length > 0 ? text : null;
}

async function generateImage() {
    const prompt = el.prompt.value.trim();
    if (!prompt) { showStatus("Please enter a prompt.", "error"); return; }

    const model = selectedImageModel(el.modelSelect);
    const modelError = validateGenerateModelForSubmit(el.modelSelect);
    if (modelError) {
        showStatus(modelError, "error");
        return;
    }

    if (isAsyncImageJobModel(model)) {
        const sourcePath = capturedViewport && capturedViewport.file_path;
        await generateImageJob(prompt, model, sourcePath);
        return;
    }

    await generateSyncImage(prompt, model);
}

async function generateSyncImage(prompt, model) {
    const sourcePath = capturedViewport && capturedViewport.file_path;
    if (!sourcePath) {
        showStatus("Capture a viewport first.", "error");
        return;
    }
    setGenerating(el.generateBtn, el.generateText, el.generateSpinner, true);
    showStatus("Generating image...", "info");
    try {
        const args = {
            prompt,
            input_image_path: sourcePath,
            resolution: el.resolutionSelect.value,
        };
        const aspectRatio = selectedAspectRatio(el.aspectSelect);
        if (aspectRatio) args.aspect_ratio = aspectRatio;
        if (el.modelSelect.value) args.model = el.modelSelect.value;
        if (generateReferences.length > 0) {
            args.reference_image_paths = generateReferences.map(r => r.path);
        }

        const artifact = await bridgeCall("generate", args);
        renderGeneratedArtifact(artifact, "Image generated.");
    } catch (e) {
        if (model && isCredentialFailureMessage(e.message)) {
            markProviderCredentialInvalid(model.provider_name);
        }
        showStatus(e.message, "error");
    } finally {
        setGenerating(el.generateBtn, el.generateText, el.generateSpinner, false);
    }
}

function renderGeneratedArtifact(artifact, successMessage) {
    latestArtifactId = artifact && artifact.artifact_id;
    if (latestArtifactId) {
        el.resultImage.src = `/blob/${encodeURIComponent(latestArtifactId)}/image?ts=${Date.now()}`;
        el.resultPanel.classList.remove("hidden");
        showStatus(successMessage || "Image generated.", "success");
    } else {
        showStatus("Generation returned no artifact.", "error");
    }
}

async function generateImageJob(prompt, model, sourcePath) {
    setGenerating(el.generateBtn, el.generateText, el.generateSpinner, true);
    showStatus("Starting image job...", "info");
    try {
        const args = {
            prompt,
            resolution: el.resolutionSelect.value,
        };
        if (isPromptOnlyAsyncImageModel(model)) {
            const aspectRatio = selectedAspectRatio(el.aspectSelect);
            if (aspectRatio) args.aspect_ratio = aspectRatio;
        }
        if (el.modelSelect.value) args.model = el.modelSelect.value;
        if (sourcePath && isSourceImageAsyncImageModel(model)) args.input_image_path = sourcePath;
        if (sourcePath && isSourceImageAsyncImageModel(model)) args.aspect_ratio = "match_input_image";

        const result = await awaitImageJobResult(args, showImageJobStatus);
        renderGeneratedArtifact({ artifact_id: result.result_artifact_id }, "Image generated.");
    } catch (e) {
        if (model && isCredentialFailureMessage(e.message)) {
            markProviderCredentialInvalid(model.provider_name);
        }
        showStatus(e.message, "error");
    } finally {
        setGenerating(el.generateBtn, el.generateText, el.generateSpinner, false);
    }
}

async function awaitImageJobResult(args, statusHandler) {
    const start = await bridgeCall("image_generate_start", args);
    if (!start || typeof start.job_id !== "string" || start.job_id.length === 0) {
        throw new Error("Image job did not return a job id.");
    }
    const jobId = start.job_id;
    let terminal = null;
    for (let attempt = 0; attempt < 180; attempt++) {
        const status = await bridgeCall("image_job_status", { job_id: jobId });
        if (!status || typeof status.state !== "string" || status.state.length === 0) {
            throw new Error("Image job returned an invalid status.");
        }
        statusHandler(status);
        if (["complete", "error", "cancelled", "interrupted"].includes(status.state)) {
            terminal = status;
            break;
        }
        await delay(1000);
    }
    if (!terminal) throw new Error("Image job did not finish before the UI timeout.");
    if (terminal.state !== "complete") {
        const err = terminal.error && terminal.error.message;
        throw new Error(err || `Image job ended with state ${terminal.state}.`);
    }
    const result = await bridgeCall("image_job_result", { job_id: jobId });
    if (!result || !result.result_artifact_id) {
        throw new Error("Image job completed without an artifact.");
    }
    return result;
}

function showImageJobStatus(status) {
    const state = status && status.state || "unknown";
    if (state === "queued") showStatus("Image job queued...", "info");
    else if (state === "submitting") showStatus("Submitting image job...", "info");
    else if (state === "polling") showStatus("Image job running...", "info");
    else if (state === "materializing") showStatus("Saving generated image...", "info");
    else if (state === "complete") showStatus("Image job complete.", "success");
    else if (state === "cancelled") showStatus("Image job cancelled.", "error");
    else if (state === "error") showStatus("Image job failed.", "error");
    else showStatus(`Image job ${state}...`, "info");
}

function delay(ms) {
    return new Promise(resolve => window.setTimeout(resolve, ms));
}

async function pickReferenceImages(intoList, previewEl, multi) {
    try {
        const data = await bridgeCall("open_image_picker", { multi });
        const paths = data.paths || [];
        paths.forEach(p => intoList.push(p));
        renderReferencePreview(intoList, previewEl);
    } catch (e) {
        showStatus(e.message, "error");
    }
}

function renderReferencePreview(list, container) {
    container.innerHTML = list.map((ref, index) => {
        const mime = ref.thumbnail_mime_type || ref.mime_type || "image/jpeg";
        const src = ref.thumbnail_base64
            ? `data:${mime};base64,${ref.thumbnail_base64}`
            : "";
        return `
            <div class="reference-thumb" title="${escapeAttr(ref.path || "")}">
                ${src ? `<img src="${src}" alt="reference">` : '<div class="reference-thumb-stub">no preview</div>'}
                <button class="remove-ref" data-index="${index}" title="Remove">&times;</button>
            </div>
        `;
    }).join("");
    container.querySelectorAll(".remove-ref").forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            list.splice(parseInt(btn.dataset.index, 10), 1);
            renderReferencePreview(list, container);
        });
    });
}

// ─── Framing helpers ───────────────────────────────────────────────

function selectedAspectRatio(selectEl) {
    if (!selectEl) return null;
    const value = selectEl.value || "auto";
    return value === "auto" ? null : value;
}

function parseRatio(value) {
    if (!value || value === "auto") return null;
    const parts = String(value).split(":");
    if (parts.length !== 2) return null;
    const width = Number(parts[0]);
    const height = Number(parts[1]);
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
        return null;
    }
    return {
        aspect: `${width} / ${height}`,
        widthCap: `${Math.max(1, (width / height) * 520)}px`,
    };
}

function setPreviewAspect(container, ratio) {
    container.style.setProperty("--preview-aspect", ratio.aspect);
    container.style.setProperty("--preview-width-cap", ratio.widthCap);
}

function applyImageAspect(container, imageEl) {
    if (!container || !imageEl || !imageEl.naturalWidth || !imageEl.naturalHeight) return;
    setPreviewAspect(container, {
        aspect: `${imageEl.naturalWidth} / ${imageEl.naturalHeight}`,
        widthCap: `${Math.max(1, (imageEl.naturalWidth / imageEl.naturalHeight) * 520)}px`,
    });
}

function applySelectedOutputAspect(container, imageEl, selectEl) {
    if (!container) return;
    const explicit = parseRatio(selectedAspectRatio(selectEl));
    if (explicit) {
        setPreviewAspect(container, explicit);
        return;
    }
    applyImageAspect(container, imageEl);
}

function refreshPreviewFraming() {
    // Generate-preview tracks the SOURCE viewport's aspect (set on image
    // load). The output-aspect dropdown drives the RESULT panel only —
    // changing it should not reshape the captured source preview.
    applySelectedOutputAspect(
        el.studioSourceContainer,
        el.studioSourceImage,
        el.studioAspectSelect);
}

function supportedResolutionsForSelectedModel(selectEl) {
    const selected = selectEl && selectEl.value;
    const entry = modelCatalog.find(m => imageModelOptionValue(m) === selected);
    if (entry && Array.isArray(entry.supported_resolutions) && entry.supported_resolutions.length > 0) {
        return entry.supported_resolutions;
    }
    return ["1K", "2K", "4K"];
}

function populateResolutionSelect(selectEl, values) {
    if (!selectEl) return;
    const previous = selectEl.value || "1K";
    selectEl.innerHTML = values
        .map(r => `<option value="${escapeAttr(r)}">${escapeHtml(r)}</option>`)
        .join("");
    const fallback = values.length > 0 ? values[0] : "";
    selectEl.value = values.includes(previous) ? previous : fallback;
}

function syncResolutionOptions() {
    populateResolutionSelect(
        el.resolutionSelect,
        supportedResolutionsForSelectedModel(el.modelSelect));
    populateResolutionSelect(
        el.studioResolutionSelect,
        supportedResolutionsForSelectedModel(el.studioModelSelect));
}

function imageModelOptionValue(model) {
    return model && (model.short_name || model.model_id) || "";
}

function selectedImageModel(selectEl) {
    const selected = selectEl && selectEl.value;
    if (!selected) return null;
    return modelCatalog.find(m => imageModelOptionValue(m) === selected) || null;
}

function modelMaxReferenceImages(model) {
    return model ? Number(model.max_reference_images || 0) : 0;
}

function normalizeImageModelDescriptor(m) {
    const cap = m.capability || {};
    return {
        model_id: m.model_id || "",
        short_name: m.short_name || m.model_id || "",
        label: cap.name || m.label || m.model_id || "",
        provider_name: m.provider_name || "",
        pricing_source: m.pricing_source || "",
        pricing_kind: m.pricing_kind || null,
        credential_availability: m.credential_availability || "available_but_unverified",
        credential_message: m.credential_message || "",
        credential_secret_key: m.credential_secret_key || "",
        submission_mode: m.submission_mode || "sync",
        supported_resolutions: cap.resolutions || m.supported_resolutions || [],
        aspect_ratios: cap.aspect_ratios || [],
        supports_image_to_image: cap.supports_image_to_image !== false,
        supports_text_to_image: cap.supports_text_to_image !== false,
        max_reference_images: Number(cap.max_reference_images || m.max_reference_images || 0),
    };
}

function normalizeLegacyAvailableModel(m) {
    return {
        model_id: m.model_id || m.short_name || "",
        short_name: m.short_name || m.model_id || "",
        label: m.label || m.short_name || m.model_id || "",
        provider_name: m.provider_name || "gemini",
        pricing_source: m.pricing_source || "",
        pricing_kind: m.pricing_kind || null,
        credential_availability: m.credential_availability || "available_but_unverified",
        credential_message: m.credential_message || "",
        credential_secret_key: m.credential_secret_key || "",
        submission_mode: m.submission_mode || "sync",
        supported_resolutions: m.supported_resolutions || [],
        aspect_ratios: m.aspect_ratios || [],
        supports_image_to_image: m.supports_image_to_image !== false,
        supports_text_to_image: m.supports_text_to_image !== false,
        max_reference_images: Number(m.max_reference_images || 0),
    };
}

function isAsyncImageJobModel(model) {
    return !!model && model.submission_mode === "async_image_job";
}

function isPromptOnlyAsyncImageModel(model) {
    return isAsyncImageJobModel(model)
        && model.supports_text_to_image !== false
        && model.supports_image_to_image === false;
}

function isSourceImageAsyncImageModel(model) {
    return isAsyncImageJobModel(model)
        && model.supports_image_to_image !== false;
}

function rememberProviderSecretKeys(providers) {
    providerSecretKeyByProvider.clear();
    const list = Array.isArray(providers) ? providers : [];
    list.forEach(provider => {
        const providerName = provider.provider_name || "";
        const secrets = Array.isArray(provider.secrets) ? provider.secrets : [];
        const primary = secrets.find(s => s && s.is_required !== false) || secrets[0];
        if (providerName && primary && primary.key) {
            providerSecretKeyByProvider.set(providerName, primary.key);
        }
    });
}

function effectiveCredentialAvailability(model) {
    const base = model.credential_availability || "available_but_unverified";
    if (base === "missing_required_secret") return base;

    const providerName = model.provider_name || "";
    const secretKey = model.credential_secret_key || providerSecretKeyByProvider.get(providerName);
    if (!providerName || !secretKey) return base;

    const overlay = sessionValidationBySecret.get(secretOverlayKey(providerName, secretKey));
    if (overlay === "invalid") return "invalid_credential";
    if (overlay === "valid") return "available";
    if (overlay === "inconclusive" && base !== "missing_required_secret") {
        return "available_with_inconclusive_validation";
    }
    return base;
}

function markProviderCredentialInvalid(providerName) {
    const secretKey = providerSecretKeyByProvider.get(providerName || "");
    if (!providerName || !secretKey) return;
    sessionValidationBySecret.set(secretOverlayKey(providerName, secretKey), "invalid");
    populateImageModelDropdowns(modelCatalog);
}

function isCredentialFailureMessage(message) {
    const text = String(message || "").toLowerCase();
    return text.includes("api key")
        || text.includes("credential")
        || text.includes("auth")
        || text.includes("unauthorized")
        || text.includes("forbidden")
        || text.includes("permission denied");
}

function validateGenerateModelForSubmit(selectEl) {
    const model = selectedImageModel(selectEl);
    if (!model) return null;
    const availability = effectiveCredentialAvailability(model);
    if (availability === "missing_required_secret") {
        return `${providerDisplayName(model.provider_name)} key is required before using this model.`;
    }
    if (!isPromptOnlyAsyncImageModel(model) && !(capturedViewport && capturedViewport.file_path)) {
        return "Capture a viewport first.";
    }
    return null;
}

function validateStudioModelForSubmit(selectEl) {
    const model = selectedImageModel(selectEl);
    if (!model) return null;
    const availability = effectiveCredentialAvailability(model);
    if (availability === "missing_required_secret") {
        return `${providerDisplayName(model.provider_name)} key is required before using this model.`;
    }
    if (model.supports_image_to_image === false) {
        return "Selected model is incompatible with Studio source-image editing.";
    }
    return null;
}

function restoreSelectValueIfSelectable(selectEl, value) {
    if (!selectEl || !value) return;
    for (const option of selectEl.options) {
        if (option.value === value && !option.disabled) {
            selectEl.value = value;
            return;
        }
    }
}

function shouldDisableGenerateModel(model) {
    return effectiveCredentialAvailability(model) === "missing_required_secret";
}

function shouldDisableStudioModel(model) {
    return shouldDisableGenerateModel(model)
        || model.supports_image_to_image === false;
}

function buildImageModelOption(model, disabled) {
    const availability = effectiveCredentialAvailability(model);
    const provider = model.provider_name ? ` · ${providerDisplayName(model.provider_name)}` : "";
    const warning = availability === "invalid_credential" ? " · credential warning" : "";
    const blocker = availability === "missing_required_secret" ? " · configure key" : "";
    return `<option value="${escapeAttr(imageModelOptionValue(model))}"${disabled ? " disabled" : ""}>${escapeHtml(model.label || model.model_id)}${escapeHtml(provider + warning + blocker)}</option>`;
}

function applyStudioModelCompatibility() {
    if (!el.studioModelSelect) return;
    for (const option of el.studioModelSelect.options) {
        const model = modelCatalog.find(m => imageModelOptionValue(m) === option.value);
        if (model && model.supports_image_to_image === false) {
            option.disabled = true;
            if (!option.textContent.includes("incompatible with Studio")) {
                option.textContent += " - incompatible with Studio";
            }
        }
    }
}

function updateGenerateInputMode() {
    const model = selectedImageModel(el.modelSelect);
    const promptOnlyAsync = isPromptOnlyAsyncImageModel(model);
    const maxReferences = model ? Number(model.max_reference_images || 0) : 0;
    const disableReferenceControls = promptOnlyAsync || maxReferences === 0;
    const generateView = document.getElementById("generate-view");
    if (generateView) {
        generateView.classList.toggle("generate-input-disabled", promptOnlyAsync);
    }

    const disableCaptureControls = promptOnlyAsync || isCapturingViewport;
    if (el.captureBtn) el.captureBtn.disabled = disableCaptureControls;
    if (el.viewportSelect) el.viewportSelect.disabled = disableCaptureControls;
    if (el.addReferenceBtn) el.addReferenceBtn.disabled = disableReferenceControls;
    if (el.clearReferencesBtn) el.clearReferencesBtn.disabled = disableReferenceControls;

    if (disableReferenceControls && generateReferences.length > 0) {
        generateReferences = [];
        renderReferencePreview(generateReferences, el.referencePreview);
    }
}

function updateStudioInputMode() {
    const model = selectedImageModel(el.studioModelSelect);
    const maxReferences = model ? Number(model.max_reference_images || 0) : 0;
    const disableReferenceControls = maxReferences === 0;
    if (el.studioAddReferenceBtn) el.studioAddReferenceBtn.disabled = disableReferenceControls;
    if (el.studioClearReferencesBtn) el.studioClearReferencesBtn.disabled = disableReferenceControls;

    if (disableReferenceControls && studioReferences.length > 0) {
        studioReferences = [];
        renderReferencePreview(studioReferences, el.studioReferencePreview);
    }
}

function populateImageModelDropdowns(models) {
    const generateModelValue = el.modelSelect && el.modelSelect.value;
    const studioModelValue = el.studioModelSelect && el.studioModelSelect.value;
    const generateOptions = models.map(m => buildImageModelOption(m, shouldDisableGenerateModel(m))).join("");
    const studioOptions = models.map(m => buildImageModelOption(m, shouldDisableStudioModel(m))).join("");
    if (el.modelSelect) el.modelSelect.innerHTML = generateOptions;
    if (el.studioModelSelect) el.studioModelSelect.innerHTML = studioOptions;
    applyStudioModelCompatibility();
    restoreSelectValueIfSelectable(el.modelSelect, generateModelValue);
    restoreSelectValueIfSelectable(el.studioModelSelect, studioModelValue);
    syncResolutionOptions();
    updateGenerateInputMode();
    updateStudioInputMode();
}

async function loadImageModels() {
    try {
        const data = await bridgeCall("list_image_models");
        if (Array.isArray(data.models) && data.models.length > 0) {
            modelCatalog = data.models.map(normalizeImageModelDescriptor);
            populateImageModelDropdowns(modelCatalog);
            return true;
        }
    } catch (e) {
        // Legacy fallback remains below via get_settings_overview.available_models.
    }
    return false;
}

// ─── Studio View ──────────────────────────────────────────────────

async function studioLoadImage() {
    try {
        const data = await bridgeCall("open_image_picker", { multi: false });
        const picked = (data.paths || [])[0];
        if (!picked || !picked.path) return;
        const mime = picked.thumbnail_mime_type || picked.mime_type || "image/jpeg";
        const previewSrc = picked.thumbnail_base64
            ? `data:${mime};base64,${picked.thumbnail_base64}`
            : "";
        applyStudioSource({
            source: "picker",
            path: picked.path,
            previewSrc,
            label: basename(picked.path),
        });
    } catch (e) {
        showStudioStatus(e.message, "error");
    }
}

async function studioCaptureDepth() {
    showStudioStatus("Capturing depth map...", "info");
    el.studioCaptureDepthBtn.disabled = true;
    try {
        const artifact = await bridgeCall("capture_depth", {});
        if (!artifact || !artifact.artifact_id || !artifact.file_path) {
            showStudioStatus("Depth capture returned no artifact.", "error");
            return;
        }
        const previewSrc = `/blob/${encodeURIComponent(artifact.artifact_id)}/image?ts=${Date.now()}`;
        const mode = artifact.metadata && artifact.metadata.resolved_mode;
        applyStudioSource({
            source: "depth",
            path: artifact.file_path,
            previewSrc,
            label: mode ? `depth map (${mode})` : "depth map",
        });
        hideStudioStatus();
    } catch (e) {
        showStudioStatus(e.message, "error");
    } finally {
        el.studioCaptureDepthBtn.disabled = false;
    }
}

function applyStudioSource(src) {
    studioSource = src;
    if (src.previewSrc) {
        el.studioSourceImage.src = src.previewSrc;
        el.studioSourcePlaceholder.classList.add("hidden");
        applySelectedOutputAspect(
            el.studioSourceContainer,
            el.studioSourceImage,
            el.studioAspectSelect);
    } else {
        el.studioSourceImage.src = "";
        el.studioSourcePlaceholder.classList.remove("hidden");
        if (el.studioSourceContainer) {
            el.studioSourceContainer.style.removeProperty("--preview-aspect");
            el.studioSourceContainer.style.removeProperty("--preview-width-cap");
        }
    }
    if (el.studioSourceLabel) {
        if (src.label) {
            el.studioSourceLabel.textContent = src.label;
            el.studioSourceLabel.classList.remove("hidden");
        } else {
            el.studioSourceLabel.classList.add("hidden");
        }
    }
}

function clearStudioSource() {
    studioSource = null;
    el.studioSourceImage.src = "";
    el.studioSourcePlaceholder.classList.remove("hidden");
    if (el.studioSourceContainer) {
        el.studioSourceContainer.style.removeProperty("--preview-aspect");
        el.studioSourceContainer.style.removeProperty("--preview-width-cap");
    }
    if (el.studioSourceLabel) {
        el.studioSourceLabel.textContent = "";
        el.studioSourceLabel.classList.add("hidden");
    }
}

function basename(path) {
    if (!path) return "";
    const parts = String(path).split(/[\\/]/);
    return parts[parts.length - 1] || path;
}

async function studioEnhancePrompt() {
    const prompt = el.studioPrompt.value.trim();
    if (!prompt) { showStudioStatus("Please enter a prompt.", "error"); return; }
    setEnhancing(el.studioEnhanceBtn, el.studioEnhanceText, el.studioEnhanceSpinner, true);
    el.studioEnhanceHint.textContent = "Enhancing...";
    try {
        const artifact = await bridgeCall("enhance_prompt", {
            prompt,
            context: "Image transformation and generation"
        });
        const text = readEnhancedPromptFromArtifact(artifact);
        if (text) {
            el.studioPrompt.dataset.originalPrompt = prompt;
            el.studioPrompt.value = text;
            el.studioEnhanceHint.textContent = "Prompt enhanced.";
        } else {
            el.studioEnhanceHint.textContent = "Enhancement returned no text.";
        }
    } catch (e) {
        el.studioEnhanceHint.textContent = "Enhancement failed.";
        showStudioStatus(e.message, "error");
    } finally {
        setEnhancing(el.studioEnhanceBtn, el.studioEnhanceText, el.studioEnhanceSpinner, false);
    }
}

async function studioGenerate() {
    const prompt = el.studioPrompt.value.trim();
    if (!prompt) { showStudioStatus("Please enter a prompt.", "error"); return; }
    if (!studioSource || !studioSource.path) {
        showStudioStatus("Load a source image first.", "error");
        return;
    }
    const modelError = validateStudioModelForSubmit(el.studioModelSelect);
    if (modelError) {
        showStudioStatus(modelError, "error");
        return;
    }
    const model = selectedImageModel(el.studioModelSelect);
    setGenerating(el.studioGenerateBtn, el.studioGenerateText, el.studioGenerateSpinner, true);
    showStudioStatus("Generating image...", "info");

    try {
        const args = {
            prompt,
            input_image_path: studioSource.path,
            resolution: el.studioResolutionSelect.value,
        };
        const aspectRatio = selectedAspectRatio(el.studioAspectSelect);
        if (aspectRatio) args.aspect_ratio = aspectRatio;
        if (el.studioModelSelect.value) args.model = el.studioModelSelect.value;
        if (modelMaxReferenceImages(model) > 0 && studioReferences.length > 0) {
            args.reference_image_paths = studioReferences.map(r => r.path);
        }

        if (isAsyncImageJobModel(model)) {
            await studioGenerateImageJob(args, model);
            return;
        }

        const artifact = await bridgeCall("generate", args);
        latestStudioArtifactId = artifact.artifact_id;
        if (artifact.artifact_id) {
            el.studioResultImage.src = `/blob/${encodeURIComponent(artifact.artifact_id)}/image?ts=${Date.now()}`;
            el.studioResultPanel.classList.remove("hidden");
            showStudioStatus("Image generated.", "success");
        } else {
            showStudioStatus("Generation returned no artifact.", "error");
        }
    } catch (e) {
        const model = selectedImageModel(el.studioModelSelect);
        if (model && isCredentialFailureMessage(e.message)) {
            markProviderCredentialInvalid(model.provider_name);
        }
        showStudioStatus(e.message, "error");
    } finally {
        setGenerating(el.studioGenerateBtn, el.studioGenerateText, el.studioGenerateSpinner, false);
    }
}

function showStudioImageJobStatus(status) {
    const state = status && status.state || "unknown";
    if (state === "queued") showStudioStatus("Image job queued...", "info");
    else if (state === "submitting") showStudioStatus("Submitting image job...", "info");
    else if (state === "polling") showStudioStatus("Image job running...", "info");
    else if (state === "materializing") showStudioStatus("Saving generated image...", "info");
    else if (state === "complete") showStudioStatus("Image job complete.", "success");
    else if (state === "cancelled") showStudioStatus("Image job cancelled.", "error");
    else if (state === "error") showStudioStatus("Image job failed.", "error");
    else showStudioStatus(`Image job ${state}...`, "info");
}

async function studioGenerateImageJob(args, model) {
    if (model && isSourceImageAsyncImageModel(model)) args.aspect_ratio = "match_input_image";
    const result = await awaitImageJobResult(args, showStudioImageJobStatus);
    latestStudioArtifactId = result.result_artifact_id;
    if (result.result_artifact_id) {
        el.studioResultImage.src = `/blob/${encodeURIComponent(result.result_artifact_id)}/image?ts=${Date.now()}`;
        el.studioResultPanel.classList.remove("hidden");
        showStudioStatus("Image generated.", "success");
    } else {
        showStudioStatus("Generation returned no artifact.", "error");
    }
}

// ─── Gallery View ─────────────────────────────────────────────────

async function loadGallery() {
    el.galleryGrid.innerHTML = '<div class="gallery-empty"><span>Loading…</span></div>';
    try {
        // PR-V3: gallery shows both generated_image AND generated_video.
        // list_artifacts takes a single `kind` filter, so we issue both
        // calls in parallel and merge on the client. Sort: created_at
        // desc with artifact_id desc as the deterministic tie-breaker
        // (Codex sign-off note — equal-timestamp items must not jitter
        // between reloads).
        const [imgData, vidData] = await Promise.all([
            bridgeCall("list_artifacts", { kind: "generated_image", limit: 100 }),
            bridgeCall("list_artifacts", { kind: "generated_video", limit: 100 }),
        ]);
        galleryItems = [
            ...(imgData.artifacts || []),
            ...(vidData.artifacts || []),
        ].sort((a, b) => {
            const tA = a.created_at || "";
            const tB = b.created_at || "";
            const byTime = tB.localeCompare(tA);
            if (byTime !== 0) return byTime;
            const idA = a.artifact_id || "";
            const idB = b.artifact_id || "";
            return idB.localeCompare(idA);
        });

        if (galleryItems.length === 0) {
            el.galleryGrid.innerHTML = `
                <div class="gallery-empty">
                    <span>No images yet</span>
                    <p>Generate your first creation to see it here</p>
                </div>`;
            return;
        }

        el.galleryGrid.innerHTML = galleryItems.map(item => {
            const id = item.artifact_id;
            const approved = item.flags && item.flags.approved;
            const isVideo = item.kind === "generated_video";
            const role = pickDisplayRole(item);
            const thumbUrl = role
                ? `/blob/${encodeURIComponent(id)}/${encodeURIComponent(role)}`
                : "";
            // PR-V3 Codex review: video gallery tiles MUST NOT eagerly
            // preload N MP4s when the user opens Gallery. Use the poster
            // image for the tile if the artifact has one; only fall back
            // to <video preload="none"> if no poster exists, and even
            // then the actual playback only happens in the modal.
            const posterRole = isVideo
                ? (item.files || []).find(f => f.role === "poster")?.role
                : null;
            const posterUrl = posterRole
                ? `/blob/${encodeURIComponent(id)}/${encodeURIComponent(posterRole)}`
                : "";
            let thumbMarkup;
            if (isVideo) {
                if (posterUrl) {
                    thumbMarkup = `<img src="${posterUrl}" alt="Video poster">`;
                } else if (thumbUrl) {
                    thumbMarkup = `<video src="${thumbUrl}" muted preload="none"></video>`;
                } else {
                    thumbMarkup = '<div class="gallery-thumb-stub">no video</div>';
                }
            } else {
                thumbMarkup = thumbUrl
                    ? `<img src="${thumbUrl}" alt="Artifact thumbnail">`
                    : '<div class="gallery-thumb-stub">no image</div>';
            }
            return `
                <div class="gallery-item ${approved ? "is-approved" : ""} ${isVideo ? "gallery-item-video" : ""}" data-id="${escapeAttr(id)}">
                    <div class="gallery-thumb-wrap">
                        ${thumbMarkup}
                        ${isVideo ? '<div class="gallery-kind-badge">VIDEO</div>' : ""}
                        ${approved ? '<div class="gallery-type-badge">APPROVED</div>' : ""}
                    </div>
                    <div class="gallery-item-info">
                        <p>${escapeHtml(formatTimestamp(item.created_at))}</p>
                        <p>${escapeHtml(item.kind || "")}</p>
                    </div>
                </div>
            `;
        }).join("");

        el.galleryGrid.querySelectorAll(".gallery-item").forEach(item => {
            item.addEventListener("click", () => openArtifactModal(item.dataset.id));
        });
    } catch (e) {
        el.galleryGrid.innerHTML = `<div class="gallery-empty"><span>Error: ${escapeHtml(e.message)}</span></div>`;
    }
}

async function openArtifactsFolder() {
    try {
        await bridgeCall("open_artifacts_folder", {});
    } catch (e) {
        window.alert(`Could not open artifacts folder: ${e.message}`);
    }
}

function pickDisplayRole(summary) {
    // Gallery summary embeds the `files[]` list. PR-V3: pick the
    // playback-or-image role appropriate to the artifact kind.
    if (!summary || !Array.isArray(summary.files)) return null;
    const isVideo = summary.kind === "generated_video";
    const preferred = isVideo
        ? ["video", "primary", "media"]
        : ["image", "thumbnail", "preview"];
    for (const role of preferred) {
        if (summary.files.some(f => f.role === role)) return role;
    }
    // Fall back to the first file whose extension matches the kind.
    const re = isVideo
        ? /\.(mp4|webm|mov)$/i
        : /\.(png|jpe?g|webp|gif|bmp)$/i;
    for (const f of summary.files) {
        if (re.test(f.path || "")) return f.role;
    }
    return null;
}

async function openArtifactModal(id) {
    try {
        modalArtifact = await bridgeCall("get_artifact", { artifact_id: id });
    } catch (e) {
        showStatus(e.message, "error");
        return;
    }
    modalDisplayRole = pickDisplayRole(modalArtifact);
    const src = modalDisplayRole
        ? `/blob/${encodeURIComponent(id)}/${encodeURIComponent(modalDisplayRole)}?ts=${Date.now()}`
        : "";

    // PR-V3: kind-aware render. Image artifacts use <img>; video
    // artifacts use <video controls>. Both elements live in the modal
    // markup; we toggle the inactive one.
    const isVideo = modalArtifact.kind === "generated_video";
    if (isVideo) {
        el.modalImage.classList.add("hidden");
        el.modalImage.src = "";
        if (el.modalVideo) {
            el.modalVideo.classList.remove("hidden");
            el.modalVideo.src = src;
            // Try to autoplay muted as a preview affordance — controls
            // remain available so the user can pause / unmute.
            try { el.modalVideo.load(); } catch { /* ignore */ }
        }
    } else {
        if (el.modalVideo) {
            el.modalVideo.pause?.();
            el.modalVideo.removeAttribute("src");
            el.modalVideo.load?.();
            el.modalVideo.classList.add("hidden");
        }
        el.modalImage.classList.remove("hidden");
        el.modalImage.src = src;
    }

    el.modalPrompt.textContent = (modalArtifact.metadata && modalArtifact.metadata.prompt) || "";
    const model = (modalArtifact.metadata && modalArtifact.metadata.model) || "";
    const when = formatTimestamp(modalArtifact.created_at);
    el.modalMeta.textContent = [modalArtifact.kind, model, when].filter(Boolean).join(" · ");
    el.modalApproveBtn.disabled = false;
    el.modalDeleteBtn.disabled = false;
    el.modal.classList.remove("hidden");
}

function closeModal() {
    el.modal.classList.add("hidden");
    el.modalImage.src = "";
    if (el.modalVideo) {
        el.modalVideo.pause?.();
        el.modalVideo.removeAttribute("src");
        el.modalVideo.load?.();
        el.modalVideo.classList.add("hidden");
    }
    modalArtifact = null;
    modalDisplayRole = null;
}

async function approveCurrentArtifact(id) {
    if (!id) return;
    try {
        await bridgeCall("approve_artifact", { artifact_id: id });
        showStatus("Artifact approved.", "success");
        if (currentView === "gallery") loadGallery();
    } catch (e) {
        showStatus(e.message, "error");
    }
}

async function revealCurrentArtifact() {
    if (!modalArtifact || !modalDisplayRole) return;
    try {
        await bridgeCall("reveal_artifact_file", {
            artifact_id: modalArtifact.artifact_id,
            role: modalDisplayRole,
        });
    } catch (e) {
        showStatus(e.message, "error");
    }
}

async function deleteCurrentArtifact(id) {
    if (!id) return;
    if (!window.confirm("Delete this artifact? This cannot be undone.")) return;
    try {
        await bridgeCall("delete_artifact", { artifact_id: id });
        closeModal();
        if (currentView === "gallery") loadGallery();
    } catch (e) {
        showStatus(e.message, "error");
    }
}

// ─── Settings View ────────────────────────────────────────────────

async function loadSettingsOverview() {
    try {
        const data = await bridgeCall("get_settings_overview");
        const formatCount = value =>
            (typeof value === "number") ? String(value) : "—";
        // Show the friendly label in the Settings overview, falling
        // back to the short name if the catalog is missing the match.
        const defaultEntry = Array.isArray(data.available_models)
            ? data.available_models.find(m => m.short_name === data.default_model)
            : null;
        el.overviewDefaultModel.textContent =
            (defaultEntry && defaultEntry.label) || data.default_model || "—";
        const artifactCounts = data.artifact_counts_by_kind || {};
        el.overviewGeneratedImageCount.textContent = formatCount(artifactCounts.generated_image);
        el.overviewCapturedViewportCount.textContent = formatCount(artifactCounts.captured_viewport);
        el.overviewEnhancedPromptCount.textContent = formatCount(artifactCounts.enhanced_prompt);
        el.overviewDepthMapCount.textContent = formatCount(artifactCounts.depth_map);
        el.overviewArtifactCount.textContent = formatCount(data.artifact_count);
        el.overviewKeyStatus.textContent = data.has_api_key ? "Configured" : "Not configured";
        rememberProviderSecretKeys(data.provider_credentials);
        renderProviderCredentials(data.provider_credentials);
        if (el.apiKey && el.apiKeyStatus && data.has_api_key) {
            // Show the truncated preview in the input placeholder so
            // it's visibly clear the key persists across sessions —
            // matches SA_Banana's "AIza…xyz1" affordance. The input
            // value stays empty; re-saving is only needed to replace.
            const preview = data.api_key_preview || "API key configured";
            el.apiKey.placeholder = preview;
            el.apiKeyStatus.textContent = `API key configured (${preview}).`;
            el.apiKeyStatus.className = "status-indicator success";
        } else if (el.apiKey && el.apiKeyStatus) {
            el.apiKey.placeholder = "Enter your API key";
            el.apiKeyStatus.textContent = "No API key configured.";
            el.apiKeyStatus.className = "status-indicator error";
        }

        const loadedImageModels = await loadImageModels();
        if (!loadedImageModels) {
            // Populate model dropdowns from the legacy server-side alias
            // when the canonical image catalog op is absent or fails. If
            // `available_models` is absent (e.g. an older companion),
            // leave the HTML-embedded defaults in place rather than
            // wiping them — that mistake was PR-7b's original "only one
            // option" bug.
            if (Array.isArray(data.available_models) && data.available_models.length > 0) {
                modelCatalog = data.available_models.map(normalizeLegacyAvailableModel);
                populateImageModelDropdowns(modelCatalog);
                if (data.default_model) {
                    if (el.modelSelect) el.modelSelect.value = data.default_model;
                    if (el.studioModelSelect) el.studioModelSelect.value = data.default_model;
                    syncResolutionOptions();
                }
            } else if (data.default_model) {
                // Server returned no catalog but did give a default —
                // select that option in the existing dropdown if it's
                // there, else leave the HTML defaults alone.
                const pickDefault = (sel) => {
                    if (!sel) return;
                    for (const opt of sel.options) {
                        if (opt.value === data.default_model) {
                            sel.value = data.default_model;
                            break;
                        }
                    }
                };
                pickDefault(el.modelSelect);
                pickDefault(el.studioModelSelect);
                syncResolutionOptions();
            }
        }

        if (modelCatalog.length === 0) {
            const allowed = data.allowed_resolutions || ["1K", "2K", "4K"];
            populateResolutionSelect(el.resolutionSelect, allowed);
            populateResolutionSelect(el.studioResolutionSelect, allowed);
        }
    } catch (e) {
        if (el.apiKeyStatus) {
            el.apiKeyStatus.textContent = e.message;
            el.apiKeyStatus.className = "status-indicator error";
        }
    }
}

async function saveApiKey() {
    if (!el.apiKey || !el.apiKeyStatus || !el.saveApiKeyBtn) return;
    const key = el.apiKey.value.trim();
    if (!key) {
        el.apiKeyStatus.textContent = "Enter a key first.";
        el.apiKeyStatus.className = "status-indicator error";
        return;
    }
    el.saveApiKeyBtn.disabled = true;
    el.apiKeyStatus.textContent = "Saving...";
    el.apiKeyStatus.className = "status-indicator";
    try {
        const data = await bridgeCall("set_api_key", { api_key: key });
        el.apiKey.value = "";
        el.apiKey.placeholder = data.api_key_preview || "API key configured";
        el.apiKeyStatus.textContent = "Saved.";
        el.apiKeyStatus.className = "status-indicator success";
        loadSettingsOverview();
    } catch (e) {
        el.apiKeyStatus.textContent = e.message;
        el.apiKeyStatus.className = "status-indicator error";
    } finally {
        el.saveApiKeyBtn.disabled = false;
    }
}

async function testApiKey() {
    if (!el.apiKey || !el.apiKeyStatus || !el.testApiKeyBtn) return;
    const inline = el.apiKey.value.trim();
    el.testApiKeyBtn.disabled = true;
    el.apiKeyStatus.textContent = "Testing...";
    el.apiKeyStatus.className = "status-indicator";
    try {
        const args = {};
        if (inline) args.api_key = inline;
        await bridgeCall("test_api_key", args);
        el.apiKeyStatus.textContent = "Test passed.";
        el.apiKeyStatus.className = "status-indicator success";
    } catch (e) {
        el.apiKeyStatus.textContent = e.message;
        el.apiKeyStatus.className = "status-indicator error";
    } finally {
        el.testApiKeyBtn.disabled = false;
    }
}

function secretOverlayKey(providerName, secretKey) {
    return `${providerName}::${secretKey}`;
}

function clearSecretOverlay(providerName, secretKey) {
    sessionValidationBySecret.delete(secretOverlayKey(providerName, secretKey));
}

function providerDisplayName(name) {
    if (name === "gemini") return "Google AI";
    if (name === "fal") return "fal.ai";
    return name || "Provider";
}

function providerHelpText(name) {
    if (name === "gemini") {
        return "Get your key from Google AI Studio. Stored encrypted under your Windows profile.";
    }
    if (name === "fal") {
        return "Get your key from fal.ai. Settings tests avoid generation work by default.";
    }
    return "Stored encrypted under your Windows profile.";
}

function credentialStatusClass(validation) {
    if (validation === "valid") return "success";
    if (validation === "invalid") return "error";
    if (validation === "inconclusive") return "warning";
    return "";
}

function credentialStatusText(secret, validation) {
    if (validation === "valid") return "Credential test passed.";
    if (validation === "invalid") return secret.message || "Credential test failed.";
    if (validation === "inconclusive") return secret.message || "Credential test was inconclusive.";
    if (secret.presence === "present") {
        return secret.preview ? `Configured (${secret.preview}).` : "Configured.";
    }
    return "Not configured.";
}

function renderProviderCredentials(providers) {
    if (!el.providerCredentials) return;
    const list = Array.isArray(providers) ? providers : [];
    if (list.length === 0) {
        el.providerCredentials.innerHTML = `<p class="provider-credential-empty">No provider credentials are configured for this build.</p>`;
        return;
    }

    el.providerCredentials.innerHTML = list.map(provider => {
        const providerName = provider.provider_name || "";
        const providerAvailability = provider.availability || "";
        const secrets = Array.isArray(provider.secrets) ? provider.secrets : [];
        const fields = secrets.map(secret => {
            const key = secret.key || "";
            const overlay = sessionValidationBySecret.get(secretOverlayKey(providerName, key));
            const validation = overlay || secret.validation_state || "not_attempted";
            const preview = secret.preview || "";
            const placeholder = preview || `Enter ${secret.display_name || "credential"}`;
            return `
                <div class="provider-secret" data-provider="${escapeAttr(providerName)}" data-secret-key="${escapeAttr(key)}">
                    <label>${escapeHtml(secret.display_name || key)}</label>
                    <div class="input-group">
                        <input type="password" class="provider-secret-input" placeholder="${escapeAttr(placeholder)}">
                    </div>
                    <span class="input-hint">${escapeHtml(providerHelpText(providerName))}</span>
                    <div class="settings-actions">
                        <button class="btn btn-secondary provider-secret-test" type="button">Test</button>
                        <button class="btn btn-primary provider-secret-save" type="button">Save Key</button>
                        <button class="btn btn-secondary provider-secret-clear" type="button">Clear</button>
                    </div>
                    <div class="status-indicator provider-secret-status ${credentialStatusClass(validation)}">${escapeHtml(credentialStatusText(secret, validation))}</div>
                </div>`;
        }).join("");
        return `
            <section class="provider-credential-card" data-provider="${escapeAttr(providerName)}">
                <div class="provider-credential-header">
                    <h4>${escapeHtml(providerDisplayName(providerName))}</h4>
                    <span>${escapeHtml(providerAvailability.replace(/_/g, " "))}</span>
                </div>
                ${fields}
            </section>`;
    }).join("");
}

function providerSecretContext(target) {
    const row = target.closest(".provider-secret");
    if (!row) return null;
    return {
        row,
        providerName: row.dataset.provider || "",
        secretKey: row.dataset.secretKey || "",
        input: row.querySelector(".provider-secret-input"),
        status: row.querySelector(".status-indicator"),
    };
}

function handleProviderCredentialInput(e) {
    if (!e.target.classList.contains("provider-secret-input")) return;
    const ctx = providerSecretContext(e.target);
    if (!ctx) return;
    clearSecretOverlay(ctx.providerName, ctx.secretKey);
    populateImageModelDropdowns(modelCatalog);
    if (ctx.input.value.length > 0) {
        setProviderSecretStatus(ctx, "Unsaved edits.", "warning");
    }
}

function handleProviderCredentialClick(e) {
    const button = e.target.closest("button");
    if (!button) return;
    const ctx = providerSecretContext(button);
    if (!ctx) return;

    if (button.classList.contains("provider-secret-save")) {
        saveProviderSecret(ctx);
    } else if (button.classList.contains("provider-secret-test")) {
        testProviderSecret(ctx);
    } else if (button.classList.contains("provider-secret-clear")) {
        clearProviderSecret(ctx);
    }
}

function setProviderSecretStatus(ctx, message, type) {
    if (!ctx || !ctx.status) return;
    ctx.status.textContent = message;
    ctx.status.className = `status-indicator provider-secret-status ${type || ""}`.trim();
}

async function saveProviderSecret(ctx) {
    if (!ctx || !ctx.input) return;
    const value = ctx.input.value.trim();
    if (!value) {
        setProviderSecretStatus(ctx, "Enter a key first.", "error");
        return;
    }
    const saveBtn = ctx.row.querySelector(".provider-secret-save");
    if (saveBtn) saveBtn.disabled = true;
    setProviderSecretStatus(ctx, "Saving...", "");
    try {
        await bridgeCall("set_provider_secret", {
            provider_name: ctx.providerName,
            secret_key: ctx.secretKey,
            value,
        });
        clearSecretOverlay(ctx.providerName, ctx.secretKey);
        ctx.input.value = "";
        setProviderSecretStatus(ctx, "Saved.", "success");
        loadSettingsOverview();
    } catch (e) {
        setProviderSecretStatus(ctx, e.message, "error");
    } finally {
        if (saveBtn) saveBtn.disabled = false;
    }
}

async function testProviderSecret(ctx) {
    if (!ctx || !ctx.input) return;
    const testBtn = ctx.row.querySelector(".provider-secret-test");
    if (testBtn) testBtn.disabled = true;
    setProviderSecretStatus(ctx, "Testing...", "");
    try {
        const args = {
            provider_name: ctx.providerName,
            secret_key: ctx.secretKey,
        };
        const rawValue = ctx.input.value;
        const value = rawValue.trim();
        if (rawValue.length > 0) args.candidate_value = value;
        const data = await bridgeCall("test_provider_secret", args);
        const validation = data.validation_state || "inconclusive";
        sessionValidationBySecret.set(secretOverlayKey(ctx.providerName, ctx.secretKey), validation);
        populateImageModelDropdowns(modelCatalog);
        setProviderSecretStatus(
            ctx,
            data.message || credentialStatusText({ presence: "present" }, validation),
            credentialStatusClass(validation));
    } catch (e) {
        setProviderSecretStatus(ctx, e.message, "error");
    } finally {
        if (testBtn) testBtn.disabled = false;
    }
}

async function clearProviderSecret(ctx) {
    if (!ctx) return;
    const clearBtn = ctx.row.querySelector(".provider-secret-clear");
    if (clearBtn) clearBtn.disabled = true;
    setProviderSecretStatus(ctx, "Clearing...", "");
    try {
        await bridgeCall("clear_provider_secret", {
            provider_name: ctx.providerName,
            secret_key: ctx.secretKey,
        });
        clearSecretOverlay(ctx.providerName, ctx.secretKey);
        if (ctx.input) ctx.input.value = "";
        setProviderSecretStatus(ctx, "Cleared.", "success");
        loadSettingsOverview();
    } catch (e) {
        setProviderSecretStatus(ctx, e.message, "error");
    } finally {
        if (clearBtn) clearBtn.disabled = false;
    }
}

// ─── UI helpers ───────────────────────────────────────────────────

function showStatus(message, type) {
    el.statusMessage.textContent = message;
    el.statusMessage.className = `status-message ${type || "info"}`;
    el.statusMessage.classList.remove("hidden");
}
function hideStatus() { el.statusMessage.classList.add("hidden"); }

function showStudioStatus(message, type) {
    el.studioStatusMessage.textContent = message;
    el.studioStatusMessage.className = `status-message ${type || "info"}`;
    el.studioStatusMessage.classList.remove("hidden");
}
function hideStudioStatus() { el.studioStatusMessage.classList.add("hidden"); }

function setEnhancing(btn, textEl, spinnerEl, busy) {
    btn.disabled = busy;
    textEl.classList.toggle("hidden", busy);
    spinnerEl.classList.toggle("hidden", !busy);
}
function setGenerating(btn, textEl, spinnerEl, busy) {
    btn.disabled = busy;
    textEl.classList.toggle("hidden", busy);
    spinnerEl.classList.toggle("hidden", !busy);
}

function escapeHtml(s) {
    return String(s == null ? "" : s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}
function escapeAttr(s) { return escapeHtml(s); }

function formatTimestamp(iso) {
    if (!iso) return "";
    try { return new Date(iso).toLocaleString(); }
    catch { return iso; }
}

// ─── Init ─────────────────────────────────────────────────────────

function init() {
    // Cache all DOM refs once the document is ready.
    el.navBtns = $$(".nav-btn");
    el.views = $$(".view");

    // Generate
    el.viewportSelect = $("viewport-select");
    el.previewContainer = document.querySelector(".preview-container");
    el.previewImage = $("preview-image");
    el.previewPlaceholder = $("preview-placeholder");
    el.captureBtn = $("capture-btn");
    el.prompt = $("prompt");
    el.modelSelect = $("model-select");
    el.resolutionSelect = $("resolution-select");
    el.aspectSelect = $("aspect-select");
    el.generateBtn = $("generate-btn");
    el.generateText = $("generate-text");
    el.generateSpinner = $("generate-spinner");
    el.statusMessage = $("status-message");
    el.resultPanel = $("result-panel");
    el.resultImage = $("result-image");
    el.approveBtn = $("approve-btn");
    el.newBtn = $("new-btn");
    el.enhanceBtn = $("enhance-btn");
    el.enhanceText = $("enhance-text");
    el.enhanceSpinner = $("enhance-spinner");
    el.enhanceHint = $("enhance-hint");
    el.promptJsonPreview = $("prompt-json-preview");
    el.editPromptBtn = $("edit-prompt-btn");
    el.viewportDimsCaption = $("viewport-dims-caption");
    el.referencePreview = $("reference-preview");
    el.addReferenceBtn = $("add-reference-btn");
    el.clearReferencesBtn = $("clear-references");

    // Studio
    el.studioSourceContainer = document.querySelector(".source-preview-container");
    el.studioSourceImage = $("studio-source-image");
    el.studioSourcePlaceholder = $("studio-source-placeholder");
    el.studioSourceLabel = $("studio-source-label");
    el.studioUploadBtn = $("studio-upload-btn");
    el.studioCaptureDepthBtn = $("studio-capture-depth-btn");
    el.studioClearSourceBtn = $("studio-clear-source");
    el.studioPrompt = $("studio-prompt");
    el.studioEnhanceBtn = $("studio-enhance-btn");
    el.studioEnhanceText = $("studio-enhance-text");
    el.studioEnhanceSpinner = $("studio-enhance-spinner");
    el.studioEnhanceHint = $("studio-enhance-hint");
    el.studioReferencePreview = $("studio-reference-preview");
    el.studioAddReferenceBtn = $("studio-add-reference-btn");
    el.studioClearReferencesBtn = $("studio-clear-references");
    el.studioModelSelect = $("studio-model-select");
    el.studioResolutionSelect = $("studio-resolution-select");
    el.studioAspectSelect = $("studio-aspect-select");
    el.studioGenerateBtn = $("studio-generate-btn");
    el.studioGenerateText = $("studio-generate-text");
    el.studioGenerateSpinner = $("studio-generate-spinner");
    el.studioStatusMessage = $("studio-status-message");
    el.studioResultPanel = $("studio-result-panel");
    el.studioResultImage = $("studio-result-image");
    el.studioApproveBtn = $("studio-approve-btn");
    el.studioNewBtn = $("studio-new-btn");

    // Gallery
    el.galleryGrid = $("gallery-grid");
    el.refreshGalleryBtn = $("refresh-gallery");
    el.openArtifactsFolderBtn = $("open-artifacts-folder");

    // Settings
    el.apiKey = $("api-key");
    el.toggleKeyBtn = $("toggle-key");
    el.saveApiKeyBtn = $("save-api-key");
    el.testApiKeyBtn = $("test-api-key");
    el.apiKeyStatus = $("api-key-status");
    el.providerCredentials = $("provider-credentials");
    el.overviewDefaultModel = $("overview-default-model");
    el.overviewGeneratedImageCount = $("overview-generated-image-count");
    el.overviewCapturedViewportCount = $("overview-captured-viewport-count");
    el.overviewEnhancedPromptCount = $("overview-enhanced-prompt-count");
    el.overviewDepthMapCount = $("overview-depth-map-count");
    el.overviewArtifactCount = $("overview-artifact-count");
    el.overviewKeyStatus = $("overview-key-status");

    // Modal
    el.modal = $("image-modal");
    el.modalImage = $("modal-image");
    el.modalVideo = $("modal-video"); // PR-V3 — kind-aware playback
    el.modalPrompt = $("modal-prompt");
    el.modalMeta = $("modal-meta");
    el.modalApproveBtn = $("modal-approve-btn");
    el.modalRevealBtn = $("modal-reveal-btn");
    el.modalDeleteBtn = $("modal-delete-btn");
    // PR-V3: scope by the modal container — three modals now have a
    // .modal-close button (image artifact, video cost, video picker)
    // and the global selector returns whichever sits first in DOM
    // order. Each modal owns its own close.
    el.modalClose = el.modal.querySelector(".modal-close");

    // Video view (PR-V3)
    Video.cacheEls();

    // ── Wire events ────────────────────────────────────────────

    el.navBtns.forEach(btn => btn.addEventListener("click", () => switchView(btn.dataset.view)));

    el.captureBtn.addEventListener("click", captureViewport);
    el.viewportSelect.addEventListener("change", captureViewport);
    el.previewImage.addEventListener("load", () => {
        // Generate preview box stays fixed; the captured bitmap uses
        // `object-fit: contain` so the full viewport letterboxes inside
        // the existing frame instead of resizing the surrounding layout.
        updateViewportDimsCaption();
    });
    el.previewImage.addEventListener("error", () => {
        if (el.viewportDimsCaption) el.viewportDimsCaption.classList.add("hidden");
        showStatus("Preview image failed to load.", "error");
    });
    // Aspect dropdown drives the RESULT panel's output shape at generate
    // time; it no longer reshapes the source preview. No change listener
    // needed on this view — the value is read in `generateImage`.
    el.modelSelect.addEventListener("change", () => {
        syncResolutionOptions();
        updateGenerateInputMode();
    });
    el.enhanceBtn.addEventListener("click", enhancePrompt);
    if (el.editPromptBtn) {
        el.editPromptBtn.addEventListener("click", () => {
            showPromptAsTextarea();
            el.prompt.focus();
        });
    }
    el.generateBtn.addEventListener("click", generateImage);
    el.newBtn.addEventListener("click", () => {
        el.resultPanel.classList.add("hidden");
        el.prompt.value = "";
        delete el.prompt.dataset.originalPrompt;
        el.enhanceHint.textContent = "AI-powered prompt optimization";
        showPromptAsTextarea();
        latestArtifactId = null;
        hideStatus();
    });
    el.approveBtn.addEventListener("click", () => approveCurrentArtifact(latestArtifactId));
    el.addReferenceBtn.addEventListener("click", () =>
        pickReferenceImages(generateReferences, el.referencePreview, true));
    el.clearReferencesBtn.addEventListener("click", () => {
        generateReferences = [];
        renderReferencePreview(generateReferences, el.referencePreview);
    });

    el.studioUploadBtn.addEventListener("click", studioLoadImage);
    el.studioCaptureDepthBtn.addEventListener("click", studioCaptureDepth);
    el.studioClearSourceBtn.addEventListener("click", clearStudioSource);
    el.studioSourceImage.addEventListener("load", () =>
        applySelectedOutputAspect(
            el.studioSourceContainer,
            el.studioSourceImage,
            el.studioAspectSelect));
    el.studioAspectSelect.addEventListener("change", refreshPreviewFraming);
    el.studioModelSelect.addEventListener("change", () => {
        syncResolutionOptions();
        updateStudioInputMode();
    });
    el.studioEnhanceBtn.addEventListener("click", studioEnhancePrompt);
    el.studioGenerateBtn.addEventListener("click", studioGenerate);
    el.studioApproveBtn.addEventListener("click", () => approveCurrentArtifact(latestStudioArtifactId));
    el.studioNewBtn.addEventListener("click", () => {
        el.studioResultPanel.classList.add("hidden");
        el.studioPrompt.value = "";
        latestStudioArtifactId = null;
        hideStudioStatus();
    });
    el.studioAddReferenceBtn.addEventListener("click", () =>
        pickReferenceImages(studioReferences, el.studioReferencePreview, true));
    el.studioClearReferencesBtn.addEventListener("click", () => {
        studioReferences = [];
        renderReferencePreview(studioReferences, el.studioReferencePreview);
    });

    el.refreshGalleryBtn.addEventListener("click", loadGallery);
    el.openArtifactsFolderBtn.addEventListener("click", openArtifactsFolder);

    if (el.providerCredentials) {
        el.providerCredentials.addEventListener("click", handleProviderCredentialClick);
        el.providerCredentials.addEventListener("input", handleProviderCredentialInput);
    }

    if (el.toggleKeyBtn && el.apiKey) {
        el.toggleKeyBtn.addEventListener("click", () => {
            const isPassword = el.apiKey.type === "password";
            el.apiKey.type = isPassword ? "text" : "password";
        });
    }
    if (el.saveApiKeyBtn && el.apiKey) el.saveApiKeyBtn.addEventListener("click", saveApiKey);
    if (el.testApiKeyBtn && el.apiKey) el.testApiKeyBtn.addEventListener("click", testApiKey);

    el.modalClose.addEventListener("click", closeModal);
    el.modal.addEventListener("click", (e) => {
        // Close on click on the modal container OR the backdrop child;
        // ignore clicks on the .modal-content (where interactive
        // elements live).
        if (e.target === el.modal || e.target.classList.contains("modal-backdrop")) {
            closeModal();
        }
    });
    el.modalApproveBtn.addEventListener("click", () => {
        if (modalArtifact) approveCurrentArtifact(modalArtifact.artifact_id);
    });
    el.modalRevealBtn.addEventListener("click", revealCurrentArtifact);
    el.modalDeleteBtn.addEventListener("click", () => {
        if (modalArtifact) deleteCurrentArtifact(modalArtifact.artifact_id);
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !el.modal.classList.contains("hidden")) closeModal();
    });
    document.addEventListener("contextmenu", (e) => {
        if (e.target instanceof Element && e.target.closest("img")) e.preventDefault();
    });

    // Video view event wiring (PR-V3).
    Video.wireEvents();

    // Initial loads.
    loadViewports().then(captureViewport).catch(() => {});
    loadSettingsOverview();
}

// Trigger called by switchView when entering the Video tab.
function loadVideoView() {
    Video.onEnter();
}

// ─── Video module (PR-V3) ───────────────────────────────────────────
//
// Video state lives in its own namespace to keep it cleanly separated
// from the image-side `modelCatalog` / `currentView` globals (Codex
// sign-off note: video uses full model_id and capability matrices, not
// the image side's short_name + supported_resolutions shape — sharing
// state would risk dropdown-sync breakage).
//
// All bridge calls go through the same `bridgeCall(op, args)` helper
// the image side uses; video op names match VideoOpHandler constants.

const Video = (() => {
    // Catalog + form state.
    let catalog = [];                 // VideoModelDescriptor projections.
    let catalogLoaded = false;
    let selectedCapability = null;
    let userPersonGenOverride = null;  // null = follow defaults; else sticky.
    let estimateTimer = null;
    let estimatePending = null;

    // Frame-picker state.
    let pickerSlot = null;             // "start" | "end" | "reference"
    let startFrame = null;             // {kind, artifact_id, role, thumb_url?}
    let endFrame = null;
    let referenceFrames = [];

    // Queue state.
    /** @type {Map<string, {entry: object, pollerId?: number, polling: boolean}>} */
    const queue = new Map();
    const POLL_INTERVAL_MS = 1500;
    const TERMINAL_STATES = new Set([
        "complete", "error", "cancelled", "interrupted",
    ]);
    const IN_FLIGHT_STATES = new Set([
        "queued", "submitting", "polling", "downloading", "saving",
    ]);
    const FAILED_STATES = new Set(["error", "cancelled", "interrupted"]);
    let queueFilter = "active";

    // DOM cache (filled by cacheEls()).
    const ve = {};

    function cacheEls() {
        ve.modelSelect = $("video-model-select");
        ve.modelHint = $("video-model-hint");
        ve.durationSelect = $("video-duration-select");
        ve.durationHint = $("video-duration-hint");
        ve.resolutionSelect = $("video-resolution-select");
        ve.aspectSelect = $("video-aspect-select");
        ve.personGenSelect = $("video-person-gen-select");
        ve.modeRadios = document.querySelectorAll('input[name="video-mode"]');
        ve.prompt = $("video-prompt");
        ve.promptHint = $("video-prompt-hint");
        ve.framesSection = $("video-frames-section");
        ve.startSlot = $("video-start-frame-slot");
        ve.startThumb = $("video-start-frame-thumb");
        ve.endSlot = $("video-end-frame-slot");
        ve.endThumb = $("video-end-frame-thumb");
        ve.referencesSlot = $("video-references-slot");
        ve.referencesPreview = $("video-references-preview");
        ve.referencesLabel = $("video-references-label");
        ve.addReferenceBtn = $("video-add-reference-btn");
        ve.clearFramesBtn = $("video-clear-frames");
        ve.costStrip = $("video-cost-strip");
        ve.costAmount = $("video-cost-amount");
        ve.costDetail = $("video-cost-detail");
        ve.generateBtn = $("video-generate-btn");
        ve.generateText = $("video-generate-text");
        ve.generateSpinner = $("video-generate-spinner");
        ve.statusMessage = $("video-status-message");
        ve.refreshQueueBtn = $("video-refresh-queue");
        ve.queueFilterButtons = document.querySelectorAll("[data-queue-filter]");
        ve.queueFilterSummary = $("video-queue-filter-summary");
        ve.queueList = $("video-queue-list");
        ve.queueWarnings = $("video-queue-warnings");

        // Cost-confirm modal.
        ve.costModal = $("video-cost-modal");
        ve.costModalClose = $("video-cost-modal-close");
        ve.costModalAmount = $("video-cost-modal-amount");
        ve.costModalModel = $("video-cost-modal-model");
        ve.costModalResolution = $("video-cost-modal-resolution");
        ve.costModalDuration = $("video-cost-modal-duration");
        ve.costModalSource = $("video-cost-modal-source");
        ve.costBreakdownBody = $("video-cost-breakdown-body");
        ve.costCancelBtn = $("video-cost-cancel-btn");
        ve.costConfirmBtn = $("video-cost-confirm-btn");

        // Picker modal.
        ve.pickerModal = $("video-picker-modal");
        ve.pickerModalClose = $("video-picker-modal-close");
        ve.pickerTitle = $("video-picker-modal-title");
        ve.pickerGrid = $("video-picker-grid");
    }

    function wireEvents() {
        ve.modelSelect.addEventListener("change", onModelChange);
        ve.modeRadios.forEach(r => r.addEventListener("change", onModeChange));
        ve.durationSelect.addEventListener("change", scheduleEstimate);
        ve.resolutionSelect.addEventListener("change", () => {
            applyMust8sLock();
            scheduleEstimate();
        });
        ve.aspectSelect.addEventListener("change", scheduleEstimate);
        ve.personGenSelect.addEventListener("change", () => {
            // User override is sticky until model/mode/refs change.
            userPersonGenOverride = ve.personGenSelect.value;
            scheduleEstimate();
        });
        ve.prompt.addEventListener("input", () => {
            updateGenerateEnablement();
            scheduleEstimate();
        });
        ve.addReferenceBtn.addEventListener("click", () => openPicker("reference"));
        ve.clearFramesBtn.addEventListener("click", clearAllFrames);
        ve.framesSection.querySelectorAll(".btn-pick-frame").forEach(btn => {
            btn.addEventListener("click", () => openPicker(btn.dataset.slot));
        });
        ve.framesSection.querySelectorAll(".btn-clear-frame").forEach(btn => {
            btn.addEventListener("click", () => clearFrame(btn.dataset.slot));
        });
        ve.generateBtn.addEventListener("click", onGenerateClicked);
        ve.refreshQueueBtn.addEventListener("click", refreshQueue);
        ve.queueFilterButtons.forEach(btn => {
            btn.addEventListener("click", () => setQueueFilter(btn.dataset.queueFilter));
        });

        // Cost modal.
        ve.costModalClose.addEventListener("click", closeCostModal);
        ve.costCancelBtn.addEventListener("click", closeCostModal);
        ve.costConfirmBtn.addEventListener("click", submitJob);
        ve.costModal.addEventListener("click", e => {
            if (e.target === ve.costModal
                || e.target.classList.contains("modal-backdrop")) {
                closeCostModal();
            }
        });

        // Picker modal.
        ve.pickerModalClose.addEventListener("click", closePicker);
        ve.pickerModal.addEventListener("click", e => {
            if (e.target === ve.pickerModal
                || e.target.classList.contains("modal-backdrop")) {
                closePicker();
            }
        });

        document.addEventListener("keydown", e => {
            if (e.key !== "Escape") return;
            if (!ve.costModal.classList.contains("hidden")) closeCostModal();
            else if (!ve.pickerModal.classList.contains("hidden")) closePicker();
        });
    }

    async function onEnter() {
        if (!catalogLoaded) {
            await hydrateCatalog();
        }
        await refreshQueue();
    }

    async function hydrateCatalog() {
        try {
            const data = await bridgeCall("list_video_models");
            catalog = data.models || [];
            catalogLoaded = true;
            populateModelDropdown();
            if (catalog.length > 0) {
                ve.modelSelect.value = catalog[0].model_id;
                onModelChange();
            } else {
                showVideoStatus("No video models registered.", "error");
            }
        } catch (e) {
            showVideoStatus(`Could not load models: ${errorToText(e)}`, "error");
        }
    }

    function populateModelDropdown() {
        ve.modelSelect.innerHTML = catalog.map(m => {
            const cap = m.capability || {};
            const label = cap.name || m.model_id;
            const status = cap.status ? ` (${cap.status})` : "";
            return `<option value="${escapeAttr(m.model_id)}">${escapeHtml(label)}${escapeHtml(status)}</option>`;
        }).join("");
    }

    function currentModel() {
        const id = ve.modelSelect.value;
        return catalog.find(m => m.model_id === id) || null;
    }

    function onModelChange() {
        const m = currentModel();
        selectedCapability = m ? m.capability : null;
        ve.modelHint.textContent = m
            ? `${m.provider_name} · ${m.pricing_kind.replace("_", " ")} · ${m.pricing_source}`
            : "";

        if (!selectedCapability) {
            disableForm();
            return;
        }

        // Reset user override on model change so the new model's
        // per-mode default applies (Codex sign-off table).
        userPersonGenOverride = null;
        // Frames may not be supported on the new model — drop them.
        if (!selectedCapability.supports_reference_images) {
            referenceFrames = [];
            renderReferenceFrames();
        }

        repopulateModeRadios();
        repopulateDurationSelect();
        repopulateResolutionSelect();
        repopulateAspectSelect();
        applyModeGating();
        applyMust8sLock();
        applyPersonGenDefault();
        updateGenerateEnablement();
        scheduleEstimate();
    }

    function disableForm() {
        ve.durationSelect.innerHTML = '<option value="">—</option>';
        ve.resolutionSelect.innerHTML = '<option value="">—</option>';
        ve.aspectSelect.innerHTML = '<option value="">—</option>';
        ve.generateBtn.disabled = true;
    }

    function repopulateModeRadios() {
        const supported = new Set(selectedCapability.modes || ["t2v"]);
        ve.modeRadios.forEach(r => {
            const ok = supported.has(r.value);
            r.disabled = !ok;
            // Switch to a supported mode if the previously-selected one
            // isn't in the new model's set.
            if (r.checked && !ok) r.checked = false;
        });
        if (![...ve.modeRadios].some(r => r.checked)) {
            const firstOk = [...ve.modeRadios].find(r => !r.disabled);
            if (firstOk) firstOk.checked = true;
        }
    }

    function repopulateDurationSelect() {
        const durations = selectedCapability.durations || [];
        const previous = parseInt(ve.durationSelect.value, 10);
        ve.durationSelect.innerHTML = durations
            .map(d => `<option value="${d}">${d}s</option>`).join("");
        const preferred = durations.includes(previous) ? previous : durations[durations.length - 1];
        if (preferred !== undefined) ve.durationSelect.value = String(preferred);
    }

    function repopulateResolutionSelect() {
        const resolutions = selectedCapability.resolutions || [];
        const previous = ve.resolutionSelect.value;
        ve.resolutionSelect.innerHTML = resolutions
            .map(r => `<option value="${escapeAttr(r)}">${escapeHtml(r)}</option>`).join("");
        ve.resolutionSelect.value = resolutions.includes(previous) ? previous : resolutions[0] || "";
    }

    function repopulateAspectSelect() {
        const aspects = selectedCapability.aspect_ratios || [];
        const previous = ve.aspectSelect.value;
        ve.aspectSelect.innerHTML = aspects
            .map(a => `<option value="${escapeAttr(a)}">${escapeHtml(a)}</option>`).join("");
        ve.aspectSelect.value = aspects.includes(previous) ? previous : aspects[0] || "";
    }

    function currentMode() {
        const checked = [...ve.modeRadios].find(r => r.checked);
        return checked ? checked.value : "t2v";
    }

    function onModeChange() {
        userPersonGenOverride = null; // Re-derive default for the new mode.
        applyModeGating();
        applyPersonGenDefault();
        updateGenerateEnablement();
        scheduleEstimate();
    }

    function applyModeGating() {
        const mode = currentMode();
        // T2V: no frame slots; I2V: start only; Interp: start + end.
        const allowStart = mode === "i2v" || mode === "interp";
        const allowEnd = mode === "interp";
        const allowRefs = !!(selectedCapability && selectedCapability.supports_reference_images);

        // PR-V3 implementation review: slots use a .disabled class +
        // pointer-events:none rather than the [hidden] attribute. CSS
        // specificity on .video-frame-slot { display:flex } beats the
        // user-agent [hidden] { display:none } rule, so setting
        // hidden=true left the slot visually present and clickable —
        // the user could pick a start frame in T2V mode and submit a
        // request that the provider rejected. The .disabled class
        // gives a discoverable greyed-out treatment AND blocks
        // interaction at the CSS level, plus we disable the buttons
        // explicitly as defense-in-depth.
        applySlotEnablement(ve.startSlot, allowStart);
        applySlotEnablement(ve.endSlot, allowEnd);
        applySlotEnablement(ve.referencesSlot, allowRefs);
        if (selectedCapability) {
            ve.referencesLabel.textContent = `References (max ${selectedCapability.max_reference_images})`;
        }

        // The frames section is shown whenever ANY slot is allowed; if
        // the current model + mode combination has none, hide the
        // entire region (uses the codebase's .hidden class for
        // !important display:none — same trap as above otherwise).
        const anyAllowed = allowStart || allowEnd || allowRefs;
        ve.framesSection.classList.toggle("hidden", !anyAllowed);

        // Drop frames that don't apply to the new mode (data hygiene
        // even if the user never re-clicks Pick).
        if (!allowStart) startFrame = null;
        if (!allowEnd) endFrame = null;
        renderFrameThumb("start");
        renderFrameThumb("end");

        const promptRequired = isPromptRequiredForVideo(currentModel(), mode);
        if (promptRequired && mode === "t2v") {
            ve.promptHint.textContent = "Required for T2V.";
        } else if (promptRequired) {
            ve.promptHint.textContent = "Required for this fal model.";
        } else {
            ve.promptHint.textContent = "Optional for I2V/Interp.";
        }
    }

    function applySlotEnablement(slot, allowed) {
        if (!slot) return;
        slot.classList.toggle("disabled", !allowed);
        // Defense-in-depth: even if a future CSS rule un-blocks pointer
        // events on the slot, the buttons themselves stay disabled.
        slot.querySelectorAll("button").forEach(btn => {
            btn.disabled = !allowed;
        });
    }

    function isSlotAllowedNow(slot) {
        const mode = currentMode();
        if (slot === "start") return mode === "i2v" || mode === "interp";
        if (slot === "end") return mode === "interp";
        if (slot === "reference") {
            return !!(selectedCapability && selectedCapability.supports_reference_images);
        }
        return false;
    }

    function applyMust8sLock() {
        const tokens = (selectedCapability && selectedCapability.must_8s_with) || [];
        const res = ve.resolutionSelect.value;
        const hasRefs = referenceFrames.length > 0;
        const triggers = tokens.some(t =>
            (t === "1080p" && res === "1080p") ||
            (t === "4k" && res === "4k") ||
            (t === "referenceImages" && hasRefs));

        if (triggers && [...ve.durationSelect.options].some(o => o.value === "8")) {
            ve.durationSelect.value = "8";
            ve.durationSelect.disabled = true;
            ve.durationHint.textContent = "Locked to 8 s by capability.";
        } else {
            ve.durationSelect.disabled = false;
            ve.durationHint.textContent = "";
        }
    }

    // PR-V3 sign-off table: defaults vary by model family + mode + refs.
    //   Veo 2.x:  any                  → allow_adult
    //   Veo 3.x:  T2V w/o refs         → allow_all
    //   Veo 3.x:  T2V w/ refs          → allow_adult  (image-based)
    //   Veo 3.x:  I2V or Interp        → allow_adult
    function applyPersonGenDefault() {
        if (userPersonGenOverride !== null) {
            ve.personGenSelect.value = userPersonGenOverride;
            return;
        }
        const m = currentModel();
        if (!m) return;
        const isVeo2 = m.model_id.startsWith("veo-2");
        const mode = currentMode();
        const hasRefs = referenceFrames.length > 0;

        let def;
        if (isVeo2) {
            def = "allow_adult";
        } else if (mode === "t2v" && !hasRefs) {
            def = "allow_all";
        } else {
            def = "allow_adult";
        }
        ve.personGenSelect.value = def;
    }

    // ─── Frame picker ───────────────────────────────────────────────

    async function openPicker(slot) {
        // Defense-in-depth: refuse to open the picker for a slot that's
        // not allowed in the current mode + capability combination.
        // applyModeGating already disables the slot's buttons, but a
        // keyboard-triggered click or a future bug-induced direct call
        // shouldn't be able to bypass the contract.
        if (!isSlotAllowedNow(slot)) {
            showVideoStatus(
                `'${slot}' is not available in the current mode.`,
                "error");
            return;
        }
        pickerSlot = slot;
        ve.pickerTitle.textContent = slot === "reference"
            ? "Pick a reference frame"
            : `Pick the ${slot} frame`;
        ve.pickerGrid.innerHTML = '<div class="gallery-empty"><span>Loading…</span></div>';
        ve.pickerModal.classList.remove("hidden");

        try {
            // PR-V3: image-kind artifacts only (videos cannot serve as
            // input frames). list_artifacts takes a single `kind`, so
            // we issue parallel calls for the three image-bearing kinds
            // — generated_image, captured_viewport, depth_map — and
            // merge by created_at desc with artifact_id desc as the
            // deterministic tie-breaker.
            const [genData, capData, depthData] = await Promise.all([
                bridgeCall("list_artifacts", { kind: "generated_image", limit: 100 }),
                bridgeCall("list_artifacts", { kind: "captured_viewport", limit: 100 }),
                bridgeCall("list_artifacts", { kind: "depth_map", limit: 100 }),
            ]);
            const items = [
                ...(genData.artifacts || []),
                ...(capData.artifacts || []),
                ...(depthData.artifacts || []),
            ].sort((a, b) => {
                const t = (b.created_at || "").localeCompare(a.created_at || "");
                if (t !== 0) return t;
                return (b.artifact_id || "").localeCompare(a.artifact_id || "");
            });
            if (items.length === 0) {
                ve.pickerGrid.innerHTML = `
                    <div class="gallery-empty">
                        <span>No image artifacts</span>
                        <p>Generate an image, capture a viewport, or capture depth to use it as a frame.</p>
                    </div>`;
                return;
            }
            ve.pickerGrid.innerHTML = items.map(a => {
                const role = pickDisplayRole(a) || "image";
                const url = `/blob/${encodeURIComponent(a.artifact_id)}/${encodeURIComponent(role)}`;
                const when = formatTimestamp(a.created_at);
                const kind = a.kind || "";
                return `
                    <div class="video-picker-item" data-id="${escapeAttr(a.artifact_id)}" data-role="${escapeAttr(role)}">
                        <div class="video-picker-thumb"><img src="${url}" alt="Picker thumbnail"></div>
                        <span class="video-picker-meta">${escapeHtml(kind)}</span>
                        <span class="video-picker-meta">${escapeHtml(when)}</span>
                    </div>`;
            }).join("");
            ve.pickerGrid.querySelectorAll(".video-picker-item").forEach(item => {
                item.addEventListener("click", () => {
                    onArtifactPicked(item.dataset.id, item.dataset.role);
                });
            });
        } catch (e) {
            ve.pickerGrid.innerHTML =
                `<div class="gallery-empty"><span>${escapeHtml(e.message)}</span></div>`;
        }
    }

    function closePicker() {
        ve.pickerModal.classList.add("hidden");
        pickerSlot = null;
    }

    function onArtifactPicked(artifactId, role) {
        const ref = {
            kind: "artifact_id",
            artifact_id: artifactId,
            role,
            // Cached display URL. Not sent to the server — it's the
            // wire ref (kind/artifact_id/role) the C# parser accepts.
            thumb_url: `/blob/${encodeURIComponent(artifactId)}/${encodeURIComponent(role)}`,
        };
        if (pickerSlot === "start") {
            startFrame = ref;
            renderFrameThumb("start");
        } else if (pickerSlot === "end") {
            endFrame = ref;
            renderFrameThumb("end");
        } else if (pickerSlot === "reference") {
            const max = selectedCapability ? selectedCapability.max_reference_images : 0;
            if (referenceFrames.length >= max) {
                showVideoStatus(`Max ${max} reference frames for this model.`, "error");
                closePicker();
                return;
            }
            referenceFrames.push(ref);
            renderReferenceFrames();
            // Codex v3 review: reference-frame count changes recompute
            // the person_generation default (Veo 3.x T2V flips
            // allow_all → allow_adult once any reference is present).
            // Clear the sticky override so the new default applies.
            userPersonGenOverride = null;
            applyMust8sLock();
            applyPersonGenDefault();
        }
        closePicker();
        updateGenerateEnablement();
        scheduleEstimate();
    }

    function clearFrame(slot) {
        if (slot === "start") { startFrame = null; renderFrameThumb("start"); }
        if (slot === "end") { endFrame = null; renderFrameThumb("end"); }
        applyMust8sLock();
        applyPersonGenDefault();
        updateGenerateEnablement();
        scheduleEstimate();
    }

    function clearAllFrames() {
        startFrame = null;
        endFrame = null;
        referenceFrames = [];
        // Reference count just dropped to zero; flip back to the no-refs
        // default for the current model+mode.
        userPersonGenOverride = null;
        renderFrameThumb("start");
        renderFrameThumb("end");
        renderReferenceFrames();
        applyMust8sLock();
        applyPersonGenDefault();
        updateGenerateEnablement();
        scheduleEstimate();
    }

    function renderFrameThumb(slot) {
        const ref = slot === "start" ? startFrame : endFrame;
        const target = slot === "start" ? ve.startThumb : ve.endThumb;
        if (!target) return;
        if (ref && ref.thumb_url) {
            target.innerHTML = `<img src="${escapeAttr(ref.thumb_url)}" alt="${slot} frame thumbnail">`;
        } else {
            target.innerHTML = '<div class="video-frame-empty">none</div>';
        }
    }

    function renderReferenceFrames() {
        if (!ve.referencesPreview) return;
        ve.referencesPreview.innerHTML = referenceFrames.map((ref, i) => `
            <div class="reference-thumb">
                <img src="${escapeAttr(ref.thumb_url)}" alt="Reference">
                <button class="remove-ref" data-index="${i}" title="Remove">&times;</button>
            </div>`).join("");
        ve.referencesPreview.querySelectorAll(".remove-ref").forEach(btn => {
            btn.addEventListener("click", () => {
                referenceFrames.splice(parseInt(btn.dataset.index, 10), 1);
                renderReferenceFrames();
                // Reference removal also flips the person_generation
                // default (T2V w/ refs → T2V w/o refs on Veo 3.x).
                userPersonGenOverride = null;
                applyMust8sLock();
                applyPersonGenDefault();
                updateGenerateEnablement();
                scheduleEstimate();
            });
        });
    }

    // ─── Estimate / submit ──────────────────────────────────────────

    function buildProviderOptions(m) {
        if (m && m.provider_name === "fal") {
            return {};
        }
        return { person_generation: ve.personGenSelect.value };
    }

    function isPromptRequiredForVideo(m, mode) {
        return mode === "t2v" || !!(m && m.provider_name === "fal");
    }

    function buildSubmitArgs() {
        if (!selectedCapability) return null;
        const m = currentModel();
        const mode = currentMode();
        const args = {
            model: m.model_id,
            mode,
            duration_seconds: parseInt(ve.durationSelect.value, 10),
            resolution: ve.resolutionSelect.value,
            aspect_ratio: ve.aspectSelect.value,
            options: buildProviderOptions(m),
            // PR-V3: number_of_videos locked to 1 — domain
            // CapabilityValidator rejects everything else.
            number_of_videos: 1,
        };
        const prompt = ve.prompt.value.trim();
        if (prompt) args.prompt = prompt;
        if (startFrame) args.start_frame = stripThumbUrl(startFrame);
        if (endFrame) args.end_frame = stripThumbUrl(endFrame);
        if (referenceFrames.length > 0) {
            args.reference_frames = referenceFrames.map(stripThumbUrl);
        }
        return args;
    }

    function stripThumbUrl(ref) {
        const { thumb_url, ...wire } = ref;
        return wire;
    }

    function isFormReady() {
        if (!selectedCapability) return false;
        if (!ve.durationSelect.value) return false;
        if (!ve.resolutionSelect.value) return false;
        if (!ve.aspectSelect.value) return false;
        const mode = currentMode();
        if (isPromptRequiredForVideo(currentModel(), mode) && !ve.prompt.value.trim()) return false;
        if (mode === "i2v" && !startFrame) return false;
        if (mode === "interp" && (!startFrame || !endFrame)) return false;
        return true;
    }

    function updateGenerateEnablement() {
        ve.generateBtn.disabled = !isFormReady();
    }

    function scheduleEstimate() {
        if (estimateTimer) clearTimeout(estimateTimer);
        // Codex review: any price-bearing field change MUST invalidate
        // the cached estimate immediately, regardless of whether the
        // form is currently valid. Otherwise the user can change inputs,
        // hit a debounce/error window, and confirm a modal showing the
        // PREVIOUS price while submitJob() sends the NEW request.
        clearCachedEstimate();
        if (!isFormReady()) {
            ve.costAmount.textContent = "—";
            ve.costDetail.textContent = "";
            return;
        }
        estimateTimer = setTimeout(runEstimate, 250);
    }

    function clearCachedEstimate() {
        delete ve.costStrip.dataset.lastEstimate;
        delete ve.costStrip.dataset.lastEstimateArgs;
        // PR-V3 Codex review: also invalidate the in-flight estimate
        // token. Without this, an in-flight runEstimate that started
        // BEFORE the field change can resolve AFTER scheduleEstimate
        // ran, pass its `estimatePending === token` check, and write
        // stale numbers back into the cache. Setting pending to a fresh
        // sentinel ensures any prior in-flight response no longer
        // matches.
        estimatePending = {};
    }

    async function runEstimate() {
        const args = buildSubmitArgs();
        if (!args) return;
        const argsJson = JSON.stringify(args);
        const token = {};
        estimatePending = token;
        try {
            const data = await bridgeCall("estimate_video_job", args);
            if (estimatePending !== token) return;
            ve.costAmount.textContent = `$${formatDollars(data.dollars_usd)}`;
            ve.costDetail.textContent =
                `${data.resolution} · ${data.duration_seconds}s · ${data.number_of_videos}×`;
            // Cache BOTH the estimate response AND the args it was
            // computed against. submitJob() rejects if the cached args
            // don't match the args it's about to submit.
            ve.costStrip.dataset.lastEstimate = JSON.stringify(data);
            ve.costStrip.dataset.lastEstimateArgs = argsJson;
        } catch (e) {
            if (estimatePending !== token) return;
            ve.costAmount.textContent = "—";
            ve.costDetail.textContent = errorToText(e);
            // Estimate failed → cached estimate is stale by definition.
            clearCachedEstimate();
        }
    }

    function formatDollars(n) {
        if (typeof n !== "number" || !Number.isFinite(n)) return "0.00";
        return n.toFixed(2);
    }

    function onGenerateClicked() {
        if (!isFormReady()) {
            showVideoStatus("Fill in the required fields first.", "error");
            return;
        }
        // Re-run estimate one more time before showing the modal so the
        // breakdown reflects the latest form state regardless of debounce.
        runEstimate().then(openCostModalIfHaveEstimate);
    }

    function openCostModalIfHaveEstimate() {
        const raw = ve.costStrip.dataset.lastEstimate;
        const cachedArgs = ve.costStrip.dataset.lastEstimateArgs;
        const currentArgs = JSON.stringify(buildSubmitArgs() || {});
        if (!raw || cachedArgs !== currentArgs) {
            // The cached estimate doesn't match the form right now —
            // either it never ran, or the user changed something between
            // the debounced runEstimate and the click. Refuse to open
            // the modal with potentially stale numbers.
            showVideoStatus(
                "Cost estimate is out of date — adjust a field to retry.",
                "error");
            return;
        }
        const data = JSON.parse(raw);
        ve.costModalAmount.textContent = `$${formatDollars(data.dollars_usd)}`;
        ve.costModalModel.textContent = data.model || "—";
        ve.costModalResolution.textContent = data.resolution || "—";
        ve.costModalDuration.textContent =
            data.duration_seconds ? `${data.duration_seconds} s` : "—";
        ve.costModalSource.textContent =
            (data.pricing && data.pricing.pricing_source) || "—";
        ve.costBreakdownBody.innerHTML = (data.breakdown || []).map(row => `
            <tr>
                <td>${escapeHtml(row.label || "")}</td>
                <td class="video-cost-breakdown-amount">$${formatDollars(row.dollars_usd)}</td>
            </tr>`).join("");
        ve.costModal.classList.remove("hidden");
    }

    function closeCostModal() {
        ve.costModal.classList.add("hidden");
    }

    async function submitJob() {
        const args = buildSubmitArgs();
        if (!args) return;
        // Defense-in-depth: even though openCostModalIfHaveEstimate gates
        // before opening, recheck right before the bridge call. If the
        // user changed a field while the modal was open, fail closed.
        const cachedArgs = ve.costStrip.dataset.lastEstimateArgs;
        if (cachedArgs !== JSON.stringify(args)) {
            closeCostModal();
            showVideoStatus(
                "Form changed since estimate — re-running estimate.",
                "error");
            scheduleEstimate();
            return;
        }
        ve.costConfirmBtn.disabled = true;
        ve.costConfirmBtn.textContent = "Submitting…";
        try {
            const data = await bridgeCall("submit_video_job", args);
            closeCostModal();
            showVideoStatus(`Job ${data.job_id.slice(0, 8)}… queued.`, "success");
            // Optimistically add to the queue and start polling. The
            // first poll will replace the optimistic record with a
            // real one carrying request_summary etc.
            const optimistic = {
                job_id: data.job_id,
                state: data.state,
                updated_at: new Date().toISOString(),
                request_summary: {
                    model: args.model,
                    mode: args.mode,
                    duration_seconds: args.duration_seconds,
                    resolution: args.resolution,
                    aspect_ratio: args.aspect_ratio,
                },
                result_artifact_id: null,
                error: null,
            };
            queue.set(data.job_id, { entry: optimistic, polling: false });
            renderQueue();
            startPolling(data.job_id);
        } catch (e) {
            // PR-V3 Codex review: surface the typed `field` from
            // structured server errors so the user sees e.g.
            // "options.person_generation: ..." not just the bare message.
            showVideoStatus(`Submit failed: ${errorToText(e)}`, "error");
        } finally {
            ve.costConfirmBtn.disabled = false;
            ve.costConfirmBtn.textContent = "Confirm & generate";
        }
    }

    // ─── Queue ──────────────────────────────────────────────────────

    async function refreshQueue() {
        try {
            const data = await bridgeCall("list_video_jobs", { limit: 50 });
            // Reconcile: replace queue-state with fresh server state but
            // preserve in-flight pollers.
            const serverIds = new Set();
            (data.jobs || []).forEach(j => {
                serverIds.add(j.job_id);
                const existing = queue.get(j.job_id);
                queue.set(j.job_id, {
                    entry: j,
                    polling: existing ? existing.polling : false,
                });
            });
            // Drop optimistic-only entries the server didn't return
            // (would only happen if list ran before ledger saw the
            // submit, which the V1c ordering rules out).
            for (const id of [...queue.keys()]) {
                if (!serverIds.has(id)) queue.delete(id);
            }
            renderWarnings(data.warnings || []);
            renderQueue();
            // Resume polling for any in-flight jobs that lost their poller
            // (fresh page load, or the prior poller errored out).
            for (const [id, st] of queue) {
                if (IN_FLIGHT_STATES.has(st.entry.state) && !st.polling) {
                    startPolling(id);
                }
            }
        } catch (e) {
            showVideoStatus(`Queue refresh failed: ${errorToText(e)}`, "error");
        }
    }

    function startPolling(jobId) {
        const st = queue.get(jobId);
        if (!st || st.polling) return;
        st.polling = true;
        const tick = async () => {
            const cur = queue.get(jobId);
            if (!cur) return; // disappeared from queue
            try {
                const data = await bridgeCall("get_video_job", { job_id: jobId });
                cur.entry = {
                    ...cur.entry,
                    state: data.state,
                    updated_at: new Date().toISOString(),
                    result_artifact_id: data.result_artifact_id || null,
                    error: data.error || null,
                };
                renderQueue();
                if (TERMINAL_STATES.has(data.state)) {
                    cur.polling = false;
                    if (data.state === "complete") {
                        // Refresh gallery if user is on Gallery view.
                        if (currentView === "gallery") loadGallery();
                    }
                    return;
                }
            } catch (e) {
                cur.polling = false;
                showVideoStatus(`Poll failed for ${jobId.slice(0, 8)}: ${errorToText(e)}`, "error");
                return;
            }
            // Schedule next tick with small jitter to avoid herding.
            const jitter = Math.floor(Math.random() * 400) - 200;
            setTimeout(tick, POLL_INTERVAL_MS + jitter);
        };
        tick();
    }

    async function cancelJob(jobId) {
        if (!window.confirm("Cancel this job?")) return;
        try {
            await bridgeCall("cancel_video_job", { job_id: jobId });
            // Server has flipped state; let the next poll surface it.
            // No optimistic write — the cancel race is handled domain-
            // side and we want to display the authoritative outcome.
        } catch (e) {
            showVideoStatus(`Cancel failed: ${errorToText(e)}`, "error");
        }
    }

    function setQueueFilter(filter) {
        if (!["active", "complete", "error", "all"].includes(filter)) return;
        queueFilter = filter;
        ve.queueFilterButtons.forEach(btn => {
            const isActive = btn.dataset.queueFilter === filter;
            btn.classList.toggle("active", isActive);
            btn.setAttribute("aria-pressed", isActive ? "true" : "false");
        });
        renderQueue();
    }

    function filterQueueEntries(entries) {
        switch (queueFilter) {
            case "active":
                return entries.filter(j => IN_FLIGHT_STATES.has(j.state));
            case "complete":
                return entries.filter(j => j.state === "complete");
            case "error":
                return entries.filter(j => FAILED_STATES.has(j.state));
            case "all":
            default:
                return entries;
        }
    }

    function updateQueueFilterCounts(entries) {
        const counts = {
            active: entries.filter(j => IN_FLIGHT_STATES.has(j.state)).length,
            complete: entries.filter(j => j.state === "complete").length,
            error: entries.filter(j => FAILED_STATES.has(j.state)).length,
            all: entries.length,
        };

        ve.queueFilterButtons.forEach(btn => {
            const count = btn.querySelector(".video-queue-filter-count");
            if (count) count.textContent = String(counts[btn.dataset.queueFilter] || 0);
        });
    }

    function renderQueueFilterSummary(entries) {
        const failedCount = entries.filter(j => FAILED_STATES.has(j.state)).length;
        if (!failedCount || queueFilter === "error" || queueFilter === "all") {
            ve.queueFilterSummary.classList.add("hidden");
            ve.queueFilterSummary.textContent = "";
            return;
        }

        ve.queueFilterSummary.classList.remove("hidden");
        ve.queueFilterSummary.textContent =
            `${failedCount} failed job${failedCount === 1 ? "" : "s"} hidden. Open Failed to inspect.`;
    }

    function applyQueueFilterClasses() {
        ve.queueList.classList.toggle("filter-error", queueFilter === "error");
        ve.queueList.classList.toggle("filter-all", queueFilter === "all");
    }

    function queueEmptyCopy() {
        switch (queueFilter) {
            case "active":
                return ["No active jobs", "Queued and running videos appear here."];
            case "complete":
                return ["No completed jobs", "Finished videos appear here."];
            case "error":
                return ["No failed jobs", "Failed, cancelled, and interrupted videos appear here."];
            case "all":
            default:
                return ["No jobs yet", "Generate a video to see it tracked here."];
        }
    }

    function renderQueue() {
        const entries = [...queue.values()]
            .map(st => st.entry)
            .sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
        const visibleEntries = filterQueueEntries(entries);

        updateQueueFilterCounts(entries);
        renderQueueFilterSummary(entries);
        applyQueueFilterClasses();

        if (visibleEntries.length === 0) {
            const [headline, detail] = queueEmptyCopy();
            ve.queueList.innerHTML = `
                <div class="video-queue-empty">
                    <span>${escapeHtml(headline)}</span>
                    <p>${escapeHtml(detail)}</p>
                </div>`;
            return;
        }

        ve.queueList.innerHTML = visibleEntries.map(j => {
            const inFlight = IN_FLIGHT_STATES.has(j.state);
            const summary = j.request_summary || {};
            const subtitle = [
                summary.model || "",
                summary.mode || "",
                summary.resolution ? `${summary.resolution} · ${summary.duration_seconds || "?"}s` : "",
            ].filter(Boolean).join(" · ");
            const errMsg = j.error && j.error.message ? j.error.message : "";

            const actions = [];
            if (inFlight) {
                actions.push(`<button class="btn btn-secondary btn-cancel-job" data-id="${escapeAttr(j.job_id)}">Cancel</button>`);
            }
            if (j.state === "complete" && j.result_artifact_id) {
                actions.push(`<button class="btn btn-primary btn-open-job" data-id="${escapeAttr(j.result_artifact_id)}">Open</button>`);
            }

            return `
                <div class="video-queue-row state-${escapeAttr(j.state)}">
                    <div class="video-queue-row-main">
                        <div class="video-queue-row-state">${escapeHtml(j.state)}</div>
                        <div class="video-queue-row-id" title="${escapeAttr(j.job_id)}">${escapeHtml(j.job_id.slice(0, 8))}</div>
                        <div class="video-queue-row-summary">${escapeHtml(subtitle)}</div>
                        ${errMsg ? `<div class="video-queue-row-error" title="${escapeAttr(errMsg)}">${escapeHtml(errMsg)}</div>` : ""}
                    </div>
                    <div class="video-queue-row-actions">${actions.join("")}</div>
                </div>`;
        }).join("");

        ve.queueList.querySelectorAll(".btn-cancel-job").forEach(btn => {
            btn.addEventListener("click", () => cancelJob(btn.dataset.id));
        });
        ve.queueList.querySelectorAll(".btn-open-job").forEach(btn => {
            btn.addEventListener("click", async () => {
                // Switching to Gallery and opening the modal gives
                // unified playback + approve/delete controls.
                switchView("gallery");
                await loadGallery();
                openArtifactModal(btn.dataset.id);
            });
        });
    }

    function renderWarnings(warnings) {
        if (!warnings.length) {
            ve.queueWarnings.classList.add("hidden");
            ve.queueWarnings.textContent = "";
            return;
        }
        ve.queueWarnings.classList.remove("hidden");
        ve.queueWarnings.textContent =
            `Ledger warnings: ${warnings.length}. Some records may be omitted.`;
    }

    function showVideoStatus(message, type) {
        ve.statusMessage.textContent = message;
        ve.statusMessage.className = `status-message ${type || "info"}`;
        ve.statusMessage.classList.remove("hidden");
    }

    return {
        cacheEls,
        wireEvents,
        onEnter,
    };
})();

