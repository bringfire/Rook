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

async function reconstructionBridgeCall(op, args) {
    if (!window.rookBridge || !window.rookBridge.invoke) {
        throw new Error("Bridge unavailable — is this running inside Rook?");
    }
    const response = await window.rookBridge.invoke(
        "reconstruction",
        Object.assign({ op }, args || {}));
    if (response && response.success === true) return response.data;
    const data = response && response.data;
    let err;
    if (typeof data === "string") {
        err = new Error(data);
    } else if (data && typeof data === "object" && typeof data.message === "string") {
        err = new Error(data.message);
        err.code = data.code;
        err.field = data.field;
        err.retryable = data.retryable;
    } else {
        err = new Error("Reconstruction op failed.");
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
let generateReferences = [];          // [{ source: "artifact", artifact_id, role, previewSrc, label }]
// `studioSource` carries Studio's source image. New selections are
// durable artifact refs:
//   { source: "artifact", artifact_id, role, previewSrc, label }
// Legacy in-memory states may still carry `{ path, previewSrc, label }`
// and are translated to `input_image_path` until those states disappear.
let studioSource = null;
let studioReferences = [];
let latestArtifactId = null;          // id of the most-recently generated image (Generate view)
let latestStudioArtifactId = null;    // same, Studio view
let galleryItems = [];                // cached list for modal lookup
let mediaImportJobs = new Map();      // job_id -> latest media import job snapshot
let mediaImportPollers = new Map();   // job_id -> timeout id
let isStartingMediaImport = false;
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

    if (view === "gallery") {
        loadGallery();
        loadMediaImportJobs();
    }
    if (view === "settings") loadSettingsOverview();
    if (view === "video") loadVideoView();
    if (view === "reconstruct") loadReconstructView();
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
            applyImageReferenceArgs(args, generateReferences);
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
        if (shouldSubmitPromptOnlyAsyncImageJob(model, sourcePath)) {
            const aspectRatio = selectedAspectRatio(el.aspectSelect);
            if (aspectRatio) args.aspect_ratio = aspectRatio;
        }
        if (el.modelSelect.value) args.model = el.modelSelect.value;
        if (sourcePath && isSourceImageAsyncImageModel(model)) args.input_image_path = sourcePath;
        if (sourcePath && isSourceImageAsyncImageModel(model)) args.aspect_ratio = "match_input_image";
        if (generateReferences.length > 0) {
            applyImageReferenceArgs(args, generateReferences);
        }

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

async function pickReferenceImages(intoList, previewEl, multi, statusHandler, hideHandler) {
    const isStudio = previewEl === el.studioReferencePreview;
    const button = isStudio ? el.studioAddReferenceBtn : el.addReferenceBtn;
    const show = statusHandler || showStatus;
    const hide = hideHandler || hideStatus;
    if (button && button.disabled) return;
    if (button) button.disabled = true;
    show(multi ? "Importing reference images..." : "Importing reference image...", "info");
    try {
        const job = await bridgeCall("start_media_import", {
            picker_mode: multi ? "image_multi" : "image_single",
        });
        if (job && job.created === false) {
            hide();
            return;
        }
        if (!job || job.created !== true || !job.job_id) {
            show("Media import did not create a job.", "error");
            return;
        }
        rememberMediaImportJob(job);
        renderMediaImportJobs();

        const completed = job.state === "complete"
            ? job
            : await awaitMediaImportJob(job.job_id);
        const importedImages = ((completed && completed.files) || [])
            .filter(file => file.artifact_kind === "imported_image" && file.artifact_id)
            .map(referenceFromImportedImage);

        if (importedImages.length === 0) {
            show("Import completed, but no image references were created.", "error");
            return;
        }
        importedImages.forEach(ref => intoList.push(ref));
        renderReferencePreview(intoList, previewEl);
        show(importedImages.length === 1
            ? "Reference image imported."
            : `${importedImages.length} reference images imported.`, "success");
    } catch (e) {
        show(errorToText(e), "error");
    } finally {
        if (button) button.disabled = false;
        if (isStudio) updateStudioInputMode();
        else updateGenerateInputMode();
    }
}

function referenceFromImportedImage(file) {
    return {
        source: "artifact",
        artifact_id: file.artifact_id,
        role: "image",
        previewSrc: `/blob/${encodeURIComponent(file.artifact_id)}/image?ts=${Date.now()}`,
        label: file.basename || "reference image",
    };
}

function renderReferencePreview(list, container) {
    container.innerHTML = list.map((ref, index) => {
        const mime = ref.thumbnail_mime_type || ref.mime_type || "image/jpeg";
        const src = ref.previewSrc || (ref.thumbnail_base64
            ? `data:${mime};base64,${ref.thumbnail_base64}`
            : "");
        const label = ref.label || basename(ref.path) || "reference image";
        return `
            <div class="reference-thumb" title="${escapeAttr(label)}">
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

function canRunPromptOnlyAsyncImageJob(model) {
    return isAsyncImageJobModel(model)
        && model.supports_text_to_image !== false;
}

function shouldSubmitPromptOnlyAsyncImageJob(model, sourcePath) {
    return canRunPromptOnlyAsyncImageJob(model)
        && (!sourcePath || model.supports_image_to_image === false);
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
    if (!(capturedViewport && capturedViewport.file_path)
        && !canRunPromptOnlyAsyncImageJob(model)) {
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
    showStudioStatus("Importing source image...", "info");
    el.studioUploadBtn.disabled = true;
    try {
        const job = await bridgeCall("start_media_import", {
            picker_mode: "image_single",
        });
        if (job && job.created === false) {
            hideStudioStatus();
            return;
        }
        if (!job || job.created !== true || !job.job_id) {
            showStudioStatus("Media import did not create a job.", "error");
            return;
        }
        rememberMediaImportJob(job);
        renderMediaImportJobs();

        const completed = job.state === "complete"
            ? job
            : await awaitMediaImportJob(job.job_id);
        const imported = ((completed && completed.files) || [])
            .find(file => file.artifact_kind === "imported_image" && file.artifact_id);

        if (!imported) {
            showStudioStatus("Import completed, but no image artifact was created.", "error");
            return;
        }

        applyStudioSource({
            source: "artifact",
            artifact_id: imported.artifact_id,
            role: "image",
            previewSrc: `/blob/${encodeURIComponent(imported.artifact_id)}/image?ts=${Date.now()}`,
            label: imported.basename || "imported image",
        });
        hideStudioStatus();
    } catch (e) {
        showStudioStatus(e.message, "error");
    } finally {
        el.studioUploadBtn.disabled = false;
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
            source: "artifact",
            artifact_id: artifact.artifact_id,
            role: "image",
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
    if (!hasStudioSourceImage()) {
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
            resolution: el.studioResolutionSelect.value,
        };
        applyStudioSourceArgs(args);
        const aspectRatio = selectedAspectRatio(el.studioAspectSelect);
        if (aspectRatio) args.aspect_ratio = aspectRatio;
        if (el.studioModelSelect.value) args.model = el.studioModelSelect.value;
        if (modelMaxReferenceImages(model) > 0 && studioReferences.length > 0) {
            applyStudioReferenceArgs(args);
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

function isVideoArtifactKind(kind) {
    return kind === "generated_video" || kind === "imported_video";
}

function hasStudioSourceImage() {
    return !!(studioSource && (
        (studioSource.source === "artifact" && studioSource.artifact_id) ||
        studioSource.path));
}

function artifactImageRef(src) {
    return {
        kind: "artifact_id",
        artifact_id: src.artifact_id,
        role: src.role || "image",
    };
}

function applyStudioSourceArgs(args) {
    if (studioSource.source === "artifact" && studioSource.artifact_id) {
        Object.assign(args, { input_image: artifactImageRef(studioSource) });
    } else if (studioSource.path) {
        args.input_image_path = studioSource.path;
    }
}

function applyStudioReferenceArgs(args) {
    applyImageReferenceArgs(args, studioReferences);
}

function applyImageReferenceArgs(args, references) {
    const artifactRefs = references
        .filter(r => r && r.artifact_id)
        .map(artifactImageRef);
    const pathRefs = references
        .filter(r => r && r.path)
        .map(r => r.path);
    if (artifactRefs.length > 0 && pathRefs.length > 0) {
        throw new Error("Reference images must come from the same source type. Clear references and add them again.");
    }
    if (artifactRefs.length > 0) args.reference_images = artifactRefs;
    if (pathRefs.length > 0) args.reference_image_paths = pathRefs;
}

async function loadGallery() {
    el.galleryGrid.innerHTML = '<div class="gallery-empty"><span>Loading…</span></div>';
    try {
        // Gallery shows generated and imported media together. The
        // list_artifacts takes a single `kind` filter, so we issue the
        // calls in parallel and merge on the client. Sort: created_at
        // desc with artifact_id desc as the deterministic tie-breaker
        // (Codex sign-off note — equal-timestamp items must not jitter
        // between reloads).
        const [imgData, vidData, importedImageData, importedVideoData] = await Promise.all([
            bridgeCall("list_artifacts", { kind: "generated_image", limit: 100 }),
            bridgeCall("list_artifacts", { kind: "generated_video", limit: 100 }),
            bridgeCall("list_artifacts", { kind: "imported_image", limit: 100 }),
            bridgeCall("list_artifacts", { kind: "imported_video", limit: 100 }),
        ]);
        galleryItems = [
            ...(imgData.artifacts || []),
            ...(vidData.artifacts || []),
            ...(importedImageData.artifacts || []),
            ...(importedVideoData.artifacts || []),
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
                    <span>No media yet</span>
                    <p>Generate or import media to see it here</p>
                </div>`;
            return;
        }

        el.galleryGrid.innerHTML = galleryItems.map(item => {
            const id = item.artifact_id;
            const approved = item.flags && item.flags.approved;
            const isVideo = isVideoArtifactKind(item.kind);
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

async function startMediaImport() {
    if (isStartingMediaImport) return;
    isStartingMediaImport = true;
    if (el.addMediaGalleryBtn) el.addMediaGalleryBtn.disabled = true;
    try {
        const job = await bridgeCall("start_media_import", {});
        if (job && job.created === false && job.reason === "empty_selection") {
            return;
        }
        if (!job || job.created !== true || !job.job_id) {
            window.alert("Media import did not create a job.");
            return;
        }
        rememberMediaImportJob(job);
        renderMediaImportJobs();
        if (job.state === "complete") {
            if (currentView === "gallery") loadGallery();
        } else {
            pollMediaImportJob(job.job_id);
        }
    } catch (e) {
        window.alert(`Could not start media import: ${errorToText(e)}`);
    } finally {
        isStartingMediaImport = false;
        if (el.addMediaGalleryBtn) el.addMediaGalleryBtn.disabled = false;
    }
}

async function loadMediaImportJobs() {
    if (!el.mediaImportList) return;
    try {
        const data = await bridgeCall("list_media_import_jobs", {});
        mediaImportJobs = new Map();
        for (const job of (data.jobs || [])) {
            rememberMediaImportJob(job);
        }
        renderMediaImportJobs();
        for (const job of mediaImportJobs.values()) {
            if (job.state !== "complete") pollMediaImportJob(job.job_id);
        }
    } catch (e) {
        el.mediaImportPanel?.classList.remove("hidden");
        el.mediaImportList.innerHTML =
            `<div class="media-import-empty">Could not load media imports: ${escapeHtml(errorToText(e))}</div>`;
    }
}

function rememberMediaImportJob(job) {
    if (!job || !job.job_id) return null;
    mediaImportJobs.set(job.job_id, job);
    return job;
}

function renderMediaImportJobs() {
    if (!el.mediaImportPanel || !el.mediaImportList) return;
    const jobs = [...mediaImportJobs.values()]
        .sort((a, b) => (b.updated_at || b.created_at || "").localeCompare(a.updated_at || a.created_at || ""));

    if (jobs.length === 0) {
        el.mediaImportPanel.classList.add("hidden");
        el.mediaImportList.innerHTML = "";
        return;
    }

    el.mediaImportPanel.classList.remove("hidden");
    const rows = [];
    for (const job of jobs) {
        for (const file of (job.files || [])) {
            const message = file.message || file.failure_code || "";
            const openButton = file.artifact_id
                ? `<button class="btn btn-secondary media-import-open" data-id="${escapeAttr(file.artifact_id)}">Open</button>`
                : "";
            rows.push(`
                <div class="media-import-row state-${escapeAttr(file.status || job.state || "")}">
                    <div class="media-import-main">
                        <span class="media-import-name">${escapeHtml(file.basename || "media")}</span>
                        <span class="media-import-status">${escapeHtml(file.status || job.state || "")}</span>
                        ${message ? `<span class="media-import-message" title="${escapeAttr(message)}">${escapeHtml(message)}</span>` : ""}
                    </div>
                    <div class="media-import-actions">${openButton}</div>
                </div>`);
        }
    }

    el.mediaImportList.innerHTML = rows.length
        ? rows.join("")
        : '<div class="media-import-empty">No files in recent import jobs.</div>';

    el.mediaImportList.querySelectorAll(".media-import-open").forEach(btn => {
        btn.addEventListener("click", async () => {
            switchView("gallery");
            await loadGallery();
            openArtifactModal(btn.dataset.id);
        });
    });
}

async function awaitMediaImportJob(jobId) {
    const maxAttempts = 150;
    const reservedPollerSlot = jobId && !mediaImportPollers.has(jobId);
    if (reservedPollerSlot) mediaImportPollers.set(jobId, null);
    try {
        for (let attempt = 0; attempt < maxAttempts; attempt++) {
            const job = await bridgeCall("get_media_import_job", { job_id: jobId });
            rememberMediaImportJob(job);
            renderMediaImportJobs();
            if (job && job.state === "complete") return job;
            await delay(1200);
        }
    } finally {
        if (reservedPollerSlot) mediaImportPollers.delete(jobId);
    }
    throw new Error("Media import did not finish within 3 minutes.");
}

function pollMediaImportJob(jobId) {
    if (!jobId || mediaImportPollers.has(jobId)) return;
    const current = mediaImportJobs.get(jobId);
    if (current && current.state === "complete") return;
    const tick = async () => {
        try {
            const previous = mediaImportJobs.get(jobId);
            const previousArtifacts = new Set(
                ((previous && previous.files) || [])
                    .map(file => file.artifact_id)
                    .filter(Boolean));
            const job = await bridgeCall("get_media_import_job", { job_id: jobId });
            rememberMediaImportJob(job);
            renderMediaImportJobs();

            const currentArtifacts = ((job && job.files) || [])
                .map(file => file.artifact_id)
                .filter(Boolean);
            const hasNewArtifact = currentArtifacts.some(id => !previousArtifacts.has(id));
            if (hasNewArtifact && currentView === "gallery") {
                loadGallery();
            }

            if (job && job.state === "complete") {
                mediaImportPollers.delete(jobId);
                if (currentView === "gallery") loadGallery();
                return;
            }
        } catch (e) {
            mediaImportPollers.delete(jobId);
            if (el.mediaImportPanel && el.mediaImportList) {
                el.mediaImportPanel.classList.remove("hidden");
                el.mediaImportList.insertAdjacentHTML(
                    "afterbegin",
                    `<div class="media-import-empty">Import poll failed: ${escapeHtml(errorToText(e))}</div>`);
            }
            return;
        }

        const timeoutId = setTimeout(tick, 1200);
        mediaImportPollers.set(jobId, timeoutId);
    };

    const timeoutId = setTimeout(tick, 0);
    mediaImportPollers.set(jobId, timeoutId);
}

function pickDisplayRole(summary) {
    // Gallery summary embeds the `files[]` list. PR-V3: pick the
    // playback-or-image role appropriate to the artifact kind.
    if (!summary || !Array.isArray(summary.files)) return null;
    const isVideo = isVideoArtifactKind(summary.kind);
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
    const isVideo = isVideoArtifactKind(modalArtifact.kind);
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
    const canReconstruct = canReconstructArtifact(modalArtifact);
    el.modalReconstructBtn?.classList.toggle("hidden", !canReconstruct);
    if (el.modalReconstructBtn) el.modalReconstructBtn.disabled = false;
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

function canReconstructArtifact(artifact) {
    return !!artifact
        && (artifact.kind === "generated_image"
            || artifact.kind === "imported_image"
            || artifact.kind === "captured_viewport")
        && Array.isArray(artifact.files)
        && artifact.files.some(f => f.role === "image");
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
    el.addMediaGalleryBtn = $("add-media-gallery");
    el.mediaImportPanel = $("media-import-panel");
    el.mediaImportList = $("media-import-list");
    el.refreshMediaImportsBtn = $("refresh-media-imports");
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
    el.modalReconstructBtn = $("modal-reconstruct-btn");
    el.modalRevealBtn = $("modal-reveal-btn");
    el.modalDeleteBtn = $("modal-delete-btn");
    // PR-V3: scope by the modal container — three modals now have a
    // .modal-close button (image artifact, video cost, video picker)
    // and the global selector returns whichever sits first in DOM
    // order. Each modal owns its own close.
    el.modalClose = el.modal.querySelector(".modal-close");

    // Video view (PR-V3)
    Video.cacheEls();
    Reconstruct.cacheEls();

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
        pickReferenceImages(generateReferences, el.referencePreview, true, showStatus, hideStatus));
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
        pickReferenceImages(studioReferences, el.studioReferencePreview, true, showStudioStatus, hideStudioStatus));
    el.studioClearReferencesBtn.addEventListener("click", () => {
        studioReferences = [];
        renderReferencePreview(studioReferences, el.studioReferencePreview);
    });

    if (el.refreshGalleryBtn) el.refreshGalleryBtn.addEventListener("click", loadGallery);
    if (el.addMediaGalleryBtn) el.addMediaGalleryBtn.addEventListener("click", startMediaImport);
    if (el.refreshMediaImportsBtn) el.refreshMediaImportsBtn.addEventListener("click", loadMediaImportJobs);
    if (el.openArtifactsFolderBtn) el.openArtifactsFolderBtn.addEventListener("click", openArtifactsFolder);

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
    el.modalReconstructBtn?.addEventListener("click", () => {
        if (modalArtifact && canReconstructArtifact(modalArtifact)) {
            const artifact = modalArtifact;
            closeModal();
            Reconstruct.presetSource(artifact);
        }
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
    Reconstruct.wireEvents();

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

    const GENERATED_VIDEO_FRAME_PICKER_ROLES = new Set(["start_frame", "end_frame"]);

    function isGeneratedVideoFramePickerRole(role) {
        return GENERATED_VIDEO_FRAME_PICKER_ROLES.has(role);
    }

    function buildFramePickerChoices(artifact) {
        if (!artifact || !artifact.artifact_id || !Array.isArray(artifact.files)) {
            return [];
        }

        if (isVideoArtifactKind(artifact.kind)) {
            return artifact.files
                .filter(file => file && isGeneratedVideoFramePickerRole(file.role))
                .map(file => ({
                    artifact,
                    role: file.role,
                    thumbRole: file.role,
                    label: file.role === "start_frame" ? "Start frame" : "End frame",
                }));
        }

        const role = pickDisplayRole(artifact) || "image";
        return [{
            artifact,
            role,
            thumbRole: role,
            label: artifact.kind || "",
        }];
    }

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
            // Image artifacts are direct frame inputs. Video artifacts
            // are role-level candidates only when they already carry
            // frame-exact sidecars. `poster` stays display-only and
            // `video` stays playback-only.
            const [genData, capData, depthData, vidData, importedImageData, importedVideoData] = await Promise.all([
                bridgeCall("list_artifacts", { kind: "generated_image", limit: 100 }),
                bridgeCall("list_artifacts", { kind: "captured_viewport", limit: 100 }),
                bridgeCall("list_artifacts", { kind: "depth_map", limit: 100 }),
                bridgeCall("list_artifacts", { kind: "generated_video", limit: 100 }),
                bridgeCall("list_artifacts", { kind: "imported_image", limit: 100 }),
                bridgeCall("list_artifacts", { kind: "imported_video", limit: 100 }),
            ]);
            const items = [
                ...(genData.artifacts || []),
                ...(capData.artifacts || []),
                ...(depthData.artifacts || []),
                ...(vidData.artifacts || []),
                ...(importedImageData.artifacts || []),
                ...(importedVideoData.artifacts || []),
            ]
                .flatMap(buildFramePickerChoices)
                .sort((a, b) => {
                    const t = (b.artifact.created_at || "").localeCompare(a.artifact.created_at || "");
                    if (t !== 0) return t;
                    const idCompare = (b.artifact.artifact_id || "").localeCompare(a.artifact.artifact_id || "");
                    if (idCompare !== 0) return idCompare;
                    return (a.role || "").localeCompare(b.role || "");
                });
            if (items.length === 0) {
                ve.pickerGrid.innerHTML = `
                    <div class="gallery-empty">
                        <span>No image artifacts</span>
                        <p>Generate, capture, or import media. Videos need start/end frame sidecars.</p>
                    </div>`;
                return;
            }
            ve.pickerGrid.innerHTML = items.map(choice => {
                const artifact = choice.artifact;
                const url = `/blob/${encodeURIComponent(artifact.artifact_id)}/${encodeURIComponent(choice.thumbRole)}`;
                const when = formatTimestamp(artifact.created_at);
                const kind = artifact.kind || "";
                const label = choice.label || kind;
                return `
                    <div class="video-picker-item" data-id="${escapeAttr(choice.artifact.artifact_id)}" data-role="${escapeAttr(choice.role)}">
                        <div class="video-picker-thumb"><img src="${url}" alt="Picker thumbnail"></div>
                        <span class="video-picker-meta">${escapeHtml(kind)}</span>
                        <span class="video-picker-meta">${escapeHtml(label)}</span>
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

// ─── Reconstruct module (image → 3D package) ────────────────────────
//
// Self-contained like `Video`: own state namespace, own DOM cache,
// driven on view-enter. All bridge calls go through
// `reconstructionBridgeCall(op, args)` on the dedicated "reconstruction"
// channel; op names match ReconstructionOpHandler constants.

function loadReconstructView() { Reconstruct.onEnter(); }

const Reconstruct = (() => {
    const POLL_INTERVAL_MS = 1500;
    const POLL_MAX_ATTEMPTS = 180;
    // cancelled is terminal-but-not-failed (All-only bucket); handled separately, NOT a failure.
    const TERMINAL_FAIL = new Set(["error", "interrupted"]);
    const ACTIVE_STATES = new Set(["queued", "running", "cancellation_requested"]);
    const FAILED_STATES = new Set(["error", "interrupted"]);
    const QUEUE_FILTERS = ["active", "complete", "failed", "all"];

    let models = [];
    let modelsLoaded = false;
    // Uniform slot state — each filled entry: { artifact_id, role, previewSrc, label, kind }
    const slots = { front: null, left: null, right: null, back: null, top: null, three_quarter: null };
    let pickerTargetSlot = null;
    let pickerArtifactsById = {};
    let outputMode = "textured";  // "textured" | "geometry"
    let reconstructMode = "i3d";  // "t3d" | "i3d" | "mv3d"
    let currentPackageId = null;
    let currentResultAvailable = false;
    let currentJobs = [];         // last-loaded job list (queue source of truth)
    let queueFilter = "active";   // active | complete | failed | all

    const re = {};                // DOM cache

    function cacheEls() {
        re.sourceThumb = $("reconstruct-source-thumb");
        re.sourceLabel = $("reconstruct-source-label");
        re.chooseSourceBtn = $("reconstruct-choose-source");
        re.sourceClear = $("reconstruct-source-clear");
        re.pickerModal = $("reconstruct-picker-modal");
        re.pickerGrid = $("reconstruct-picker-grid");
        re.pickerClose = $("reconstruct-picker-close");
        re.modelSelect = $("reconstruct-model-select");
        re.modelHint = $("reconstruct-model-hint");
        re.modeSwitch = $("reconstruct-mode-radios");
        re.mvSlots = $("reconstruct-mv-slots");
        re.prompt = $("reconstruct-prompt");
        re.promptHint = $("reconstruct-prompt-hint");
        re.formPanel = document.querySelector(".reconstruct-form-panel");
        re.modeTextured = $("reconstruct-mode-textured");
        re.modeGeometry = $("reconstruct-mode-geometry");
        re.submitBtn = $("reconstruct-submit-btn");
        re.statusMessage = $("reconstruct-status-message");
        re.resultPanel = $("reconstruct-result-panel");
        re.resultThumb = $("reconstruct-result-thumb");
        re.resultMeta = $("reconstruct-result-meta");
        re.resultWarnings = $("reconstruct-result-warnings");
        re.importBtn = $("reconstruct-import-btn");
        re.importStatus = $("reconstruct-import-status");
        re.jobsList = $("reconstruct-jobs-list");
        re.refreshJobsBtn = $("reconstruct-refresh-jobs");
        re.queueFilters = $("reconstruct-queue-filters");
        re.queueFilterSummary = $("reconstruct-queue-filter-summary");
    }

    function wireEvents() {
        re.modeSwitch.querySelectorAll(".seg-btn").forEach(b => b.addEventListener("click", () => setReconstructMode(b.dataset.mode)));
        re.chooseSourceBtn.addEventListener("click", () => openReconstructPicker("front"));
        re.sourceClear.addEventListener("click", () => clearSlot("front"));
        re.mvSlots.querySelectorAll("[data-slot]").forEach(slotDiv => {
            var s = slotDiv.dataset.slot;
            var pick = slotDiv.querySelector(".btn-slot-pick");
            var clear = slotDiv.querySelector(".btn-slot-clear");
            if (pick) pick.addEventListener("click", () => openReconstructPicker(s));
            if (clear) clear.addEventListener("click", () => clearSlot(s));
        });
        re.pickerClose.addEventListener("click", closeReconstructPicker);
        re.pickerModal.querySelector(".modal-backdrop").addEventListener("click", closeReconstructPicker);
        re.pickerGrid.addEventListener("click", (e) => {
            if (!(e.target instanceof Element)) return;
            const cell = e.target.closest(".reconstruct-picker-cell");
            if (!cell) return;
            const a = pickerArtifactsById[cell.dataset.artifactId];
            if (a) { fillSlot(pickerTargetSlot, a); closeReconstructPicker(); }
        });
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && re.pickerModal && !re.pickerModal.classList.contains("hidden")) {
                closeReconstructPicker();
            }
        });
        re.modeTextured.addEventListener("click", () => setOutputMode("textured"));
        re.modeGeometry.addEventListener("click", () => setOutputMode("geometry"));
        re.submitBtn.addEventListener("click", submit);
        re.modelSelect.addEventListener("change", updateModelHint);
        re.importBtn.addEventListener("click", importPackage);
        re.refreshJobsBtn.addEventListener("click", loadJobs);
        re.jobsList.addEventListener("click", (e) => {
            if (!(e.target instanceof Element)) return;
            const cancelBtn = e.target.closest(".reconstruct-queue-cancel");
            if (cancelBtn) {
                // Disable immediately so the in-flight button cannot be double-clicked.
                cancelBtn.disabled = true;
                cancelBtn.textContent = "Canceling…";
                cancelQueueJob(cancelBtn.dataset.id, cancelBtn);
                return;
            }
            const openBtn = e.target.closest(".reconstruct-queue-open");
            if (openBtn) { openJobResult(openBtn.dataset.id); return; }
        });
        re.queueFilters.addEventListener("click", (e) => {
            if (!(e.target instanceof Element)) return;
            const btn = e.target.closest(".reconstruct-queue-filter");
            if (btn && btn.dataset.queueFilter) setQueueFilter(btn.dataset.queueFilter);
        });
    }

    async function onEnter() {
        await loadModels();
        setReconstructMode(reconstructMode);
        renderSlot("front");
        setQueueFilter("active");   // default view-enter filter
        await loadJobs();
    }

    function showReconstructStatus(message, type) {
        re.statusMessage.textContent = message;
        re.statusMessage.className = `status-message ${type || "info"}`;
        re.statusMessage.classList.remove("hidden");
    }

    function setOutputMode(mode) {
        outputMode = mode === "geometry" ? "geometry" : "textured";
        const textured = outputMode === "textured";
        re.modeTextured.classList.toggle("active", textured);
        re.modeGeometry.classList.toggle("active", !textured);
        re.modeTextured.setAttribute("aria-checked", String(textured));
        re.modeGeometry.setAttribute("aria-checked", String(!textured));
    }

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

    function optionsForMode() {
        // Mutually exclusive — never emit both (backend D1 guard rejects it).
        if (outputMode === "geometry") return { enable_geometry: true };
        const model = selectedModel();
        return model && model.supports_pbr ? { enable_pbr: true } : {};
    }

    async function submit() {
        const frontSlot = slots.front;
        if (!frontSlot || !frontSlot.artifact_id) {
            showReconstructStatus("Choose a source image first.", "error");
            return;
        }
        const modelId = selectedModelId();
        if (!modelId) {
            showReconstructStatus("Select a model first.", "error");
            return;
        }
        resetResultForNewRun();   // hide stale result/import state while the new job runs
        try {
            re.submitBtn.disabled = true;
            showReconstructStatus("Submitting reconstruction…", "info");
            const job = await reconstructionBridgeCall("submit_job", {
                source_artifact_id: frontSlot.artifact_id,
                source_role: frontSlot.role || "image",
                model_id: modelId,
                preprocessing_chain: [],
                options: optionsForMode(),
                estimate_requested: false,
            });
            if (!job || !job.job_id) {
                throw new Error("Reconstruction submit did not return a job id.");
            }
            setQueueFilter("active");   // surface the just-submitted job in the rail
            await loadJobs();
            await poll(job.job_id);
        } catch (e) {
            showReconstructStatus(errorToText(e), "error");
        } finally {
            re.submitBtn.disabled = false;
        }
    }

    async function poll(jobId) {
        for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt++) {
            const status = await reconstructionBridgeCall("job_status", { job_id: jobId });
            const job = status.job || status;
            showReconstructStatus(`3D ${job.stage || job.state || "working"} · ${jobId}`, "info");
            if (job.state === "complete") {
                const result = await reconstructionBridgeCall("job_result", { job_id: jobId });
                renderResult(result);
                showReconstructStatus("Reconstruction complete.", "success");
                loadJobs();   // refresh queue
                return;
            }
            if (job.state === "cancelled") {
                // Terminal-but-not-failed: calm, neutral copy (not error styling).
                showReconstructStatus("Reconstruction cancelled.", "info");
                loadJobs();
                return;
            }
            if (TERMINAL_FAIL.has(job.state)) {
                showReconstructStatus(`Reconstruction ${job.state}.`, "error");
                loadJobs();
                return;
            }
            await delay(POLL_INTERVAL_MS);
        }
        showReconstructStatus("Reconstruction polling timed out.", "error");
    }

    function selectedModelId() {
        return re.modelSelect && re.modelSelect.value ? re.modelSelect.value : null;
    }

    function selectedModel() {
        const id = selectedModelId();
        return id ? models.find(x => x.model_id === id) || null : null;
    }

    function buildModelOption(model) {
        const pbr = model.supports_pbr ? "" : " · no PBR";
        return `<option value="${escapeAttr(model.model_id)}">${escapeHtml(shortModelLabel(model.model_id))}${escapeHtml(pbr)}</option>`;
    }

    function updateModelHint() {
        if (!re.modelHint) return;
        const m = selectedModel();
        re.modelHint.textContent = m
            ? `${m.provider} · ${String(m.task || "").replace(/_/g, " ")}${m.supports_pbr ? " · PBR" : ""}`
            : "";
    }

    async function loadModels() {
        if (modelsLoaded) return;
        try {
            const data = await reconstructionBridgeCall("models", {});
            models = Array.isArray(data.models) ? data.models : [];
        } catch (e) {
            models = [];
        }
        if (models.length === 0) {
            re.modelSelect.innerHTML = `<option value="" disabled selected>No models available</option>`;
        } else {
            // Default to the first model (like the Video tab); model_id stays explicit + required.
            re.modelSelect.innerHTML = models.map(buildModelOption).join("");
            re.modelSelect.value = models[0].model_id;
        }
        updateModelHint();
        modelsLoaded = true;
    }

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
        // secondary slots: query container by [data-slot], set thumb background
        if (!re.mvSlots) return;
        var slotEl = re.mvSlots.querySelector('[data-slot="' + slot + '"]');
        if (!slotEl) return;
        var thumb = slotEl.querySelector(".reconstruct-slot-thumb");
        if (!thumb) return;
        var v = slots[slot];
        thumb.style.backgroundImage = v ? 'url("' + v.previewSrc + '")' : "";
    }

    const RECONSTRUCT_SOURCE_KINDS = ["generated_image", "imported_image", "captured_viewport", "preprocessed_image"];

    async function openReconstructPicker(slot) {
        pickerTargetSlot = slot;
        // The shared Gallery helper is `bridgeCall`; list_artifacts filters by a
        // SINGLE `kind`, so fan out one call per allowed kind and merge.
        const results = await Promise.all(RECONSTRUCT_SOURCE_KINDS.map(
            k => bridgeCall("list_artifacts", { kind: k, limit: 100 }).catch(() => ({ artifacts: [] }))));
        const artifacts = results.flatMap(r => (r && r.artifacts) || []);
        pickerArtifactsById = {};
        artifacts.forEach(a => { pickerArtifactsById[a.artifact_id] = a; });
        re.pickerGrid.innerHTML = artifacts.map(a =>
            `<button class="reconstruct-picker-cell" data-artifact-id="${escapeAttr(a.artifact_id)}"><img src="/blob/${encodeURIComponent(a.artifact_id)}/image" alt="${escapeAttr(a.kind)}"/></button>`).join("");
        re.pickerModal.classList.remove("hidden");
    }

    function closeReconstructPicker() { re.pickerModal.classList.add("hidden"); pickerTargetSlot = null; }

    // Friendly headline per known warning code. Unknown codes fall back to
    // the backend message verbatim (forward-compatible). Read by CODE, never
    // inferred from asset_roles.
    const WARNING_COPY = {
        result_artifact_missing: {
            severity: "error",
            text: "The reconstruction completed but its package could not be found. The result may be unavailable; try re-running.",
        },
        pbr_unsupported_by_model: {
            severity: "warning",
            text: "Textured output was requested, but this model isn't catalogued as supporting textured/PBR output. The result may have no materials.",
        },
        result_missing_texture: {
            severity: "warning",
            text: "Textured output was expected and this model supports it, but the delivered package contains no material or texture assets.",
        },
    };

    function renderWarnings(warnings) {
        const list = Array.isArray(warnings) ? warnings : [];
        if (list.length === 0) {
            re.resultWarnings.innerHTML = "";
            re.resultWarnings.classList.add("hidden");
            return;
        }
        re.resultWarnings.innerHTML = list.map(w => {
            const known = WARNING_COPY[w.code];
            const severity = known ? known.severity : "warning";
            const headline = known ? known.text : (w.message || w.code || "Unknown warning.");
            const detail = known && w.message
                ? `<span class="reconstruct-warning-detail">${escapeHtml(w.message)}</span>`
                : "";
            return `<li class="reconstruct-warning ${severity}"><span class="reconstruct-warning-code">${escapeHtml(w.code || "warning")}</span>${escapeHtml(headline)}${detail}</li>`;
        }).join("");
        re.resultWarnings.classList.remove("hidden");
    }

    function renderResult(result) {
        const pkg = result.package || {};
        const packageId = result.result_artifact_id || "";
        const roles = Array.isArray(pkg.asset_roles) ? pkg.asset_roles : [];
        const preferred = pkg.preferred_asset_role || "";

        if (packageId && result.result_available) {
            re.resultThumb.src = `/blob/${encodeURIComponent(packageId)}/thumbnail?ts=${Date.now()}`;
            re.resultThumb.classList.remove("hidden");
        } else {
            re.resultThumb.removeAttribute("src");
            re.resultThumb.classList.add("hidden");
        }
        re.resultThumb.onerror = () => re.resultThumb.classList.add("hidden");

        const resolvedRole = pkg.resolved_import_role || "";
        re.resultMeta.innerHTML = [
            `<div class="reconstruct-result-id">Package ${escapeHtml(packageId || "—")}</div>`,
            roles.length
                ? `<div class="reconstruct-result-roles">Available assets: ${escapeHtml(roles.join(", "))}</div>`
                : "",
            preferred
                ? `<div class="reconstruct-result-preferred">Catalog preferred: ${escapeHtml(preferred)}</div>`
                : "",
            resolvedRole
                ? `<div class="reconstruct-result-resolved">Import will use: ${escapeHtml(resolvedRole)}</div>`
                : `<div class="reconstruct-result-resolved unavailable">Import unavailable: no importable model asset</div>`,
        ].join("");

        renderWarnings(result.warnings);

        // Import is possible only when the package is available AND the resolver names a role.
        // Recomputed every render, so a later valid result re-enables a button left disabled by a
        // prior null result.
        const importable = !!(packageId && result.result_available && resolvedRole);
        currentPackageId = packageId || null;
        currentResultAvailable = importable;
        re.importBtn.disabled = !importable;
        re.importBtn.textContent = "Import to Rhino";
        setImportStatus("", "");

        re.resultPanel.classList.remove("hidden");
    }

    function setImportStatus(message, type) {
        if (!re.importStatus) return;
        re.importStatus.textContent = message || "";
        re.importStatus.className = `reconstruct-import-status ${type || ""}`;
    }

    function resetResultForNewRun() {
        // Hide stale package metadata + import state while a new job runs.
        currentPackageId = null;
        currentResultAvailable = false;
        if (re.importBtn) {
            re.importBtn.disabled = true;
            re.importBtn.textContent = "Import to Rhino";
        }
        setImportStatus("", "");
        if (re.resultPanel) re.resultPanel.classList.add("hidden");
    }

    async function importPackage() {
        // Match the UI state invariant: never import an unavailable/unimportable result, even if the
        // call somehow fires while the button is disabled.
        if (!currentPackageId || !currentResultAvailable) return;
        try {
            re.importBtn.disabled = true;
            re.importBtn.textContent = "Importing…";
            setImportStatus("", "");
            const data = await reconstructionBridgeCall("import_package", { package_id: currentPackageId });
            const ids = Array.isArray(data && data.imported_ids) ? data.imported_ids : [];
            const role = (data && data.asset_role) || "model";
            const n = ids.length;
            setImportStatus(`Imported ${n} object${n === 1 ? "" : "s"} as ${role}`, "success");
        } catch (e) {
            // Route through the existing structured-error path (field: message) — no new formatter.
            setImportStatus(errorToText(e), "error");
        } finally {
            re.importBtn.textContent = "Import to Rhino";
            re.importBtn.disabled = !currentResultAvailable;
        }
    }

    async function loadJobs() {
        try {
            const data = await reconstructionBridgeCall("list_jobs", {});
            currentJobs = Array.isArray(data.jobs) ? data.jobs : [];
        } catch (e) {
            currentJobs = [];
            re.jobsList.innerHTML =
                `<div class="reconstruct-queue-empty"><p>${escapeHtml(errorToText(e))}</p></div>`;
            updateFilterCounts([]);
            // Don't leave a stale "Showing N …" line above an error list.
            if (re.queueFilterSummary) {
                re.queueFilterSummary.textContent = "";
                re.queueFilterSummary.classList.add("hidden");
            }
            return;
        }
        renderQueue();
    }

    function setQueueFilter(filter) {
        if (!QUEUE_FILTERS.includes(filter)) return;
        queueFilter = filter;
        if (re.queueFilters) {
            re.queueFilters.querySelectorAll(".reconstruct-queue-filter").forEach(btn => {
                const on = btn.dataset.queueFilter === filter;
                btn.classList.toggle("active", on);
                btn.setAttribute("aria-pressed", String(on));
            });
        }
        renderQueue();
    }

    function inBucket(job, filter) {
        switch (filter) {
            case "active": return ACTIVE_STATES.has(job.state);
            case "complete": return job.state === "complete";
            case "failed": return FAILED_STATES.has(job.state);
            default: return true;   // "all"
        }
    }

    function updateFilterCounts(jobs) {
        if (!re.queueFilters) return;
        re.queueFilters.querySelectorAll(".reconstruct-queue-filter").forEach(btn => {
            const f = btn.dataset.queueFilter;
            const countEl = btn.querySelector(".reconstruct-queue-filter-count");
            if (countEl) countEl.textContent = String(jobs.filter(j => inBucket(j, f)).length);
        });
    }

    function renderQueueFilterSummary(visibleCount) {
        if (!re.queueFilterSummary) return;
        const noun = queueFilter === "all" ? "job" : queueFilter;
        re.queueFilterSummary.textContent =
            `Showing ${visibleCount} ${noun}${queueFilter === "all" && visibleCount !== 1 ? "s" : ""}`;
        re.queueFilterSummary.classList.remove("hidden");
    }

    function shortModelLabel(modelId) {
        if (!modelId) return "";
        // Pinned data source: j.model_id. Drop the provider prefix for a readable label.
        const parts = String(modelId).split("/");
        return parts.length > 1 ? parts.slice(1).join("/") : modelId;
    }

    function renderQueue() {
        updateFilterCounts(currentJobs);
        const visible = currentJobs.filter(j => inBucket(j, queueFilter));
        renderQueueFilterSummary(visible.length);
        if (visible.length === 0) {
            re.jobsList.innerHTML =
                `<div class="reconstruct-queue-empty"><span>No jobs</span><p>Nothing ${queueFilter === "all" ? "in the queue" : queueFilter} yet.</p></div>`;
            return;
        }
        re.jobsList.innerHTML = visible.map(j => {
            const cancelable = j.state === "queued" || j.state === "running";
            const canceling = j.state === "cancellation_requested";
            const openable = j.state === "complete" && j.result_available;
            const subtitle = [shortModelLabel(j.model_id), j.stage].filter(Boolean).join(" · ");
            const errMsg = j.error && j.error.message ? j.error.message : "";
            const actions = [];
            if (cancelable) {
                actions.push(`<button class="btn btn-secondary reconstruct-queue-cancel" data-id="${escapeAttr(j.job_id)}">Cancel</button>`);
            } else if (canceling) {
                actions.push(`<span class="reconstruct-queue-canceling">Canceling…</span>`);
            }
            if (openable) {
                actions.push(`<button class="btn btn-primary reconstruct-queue-open" data-id="${escapeAttr(j.job_id)}">Open</button>`);
            }
            return `
                <div class="reconstruct-queue-row state-${escapeAttr(j.state)}">
                    <div class="reconstruct-queue-row-main">
                        <div class="reconstruct-queue-row-state">${escapeHtml(j.state || "")}</div>
                        <span class="reconstruct-queue-row-id" title="${escapeAttr(j.job_id)}">${escapeHtml((j.job_id || "").slice(0, 8))}</span>
                        <div class="reconstruct-queue-row-summary">${escapeHtml(subtitle)}</div>
                        ${errMsg ? `<div class="reconstruct-queue-row-error" title="${escapeAttr(errMsg)}">${escapeHtml(errMsg)}</div>` : ""}
                    </div>
                    <div class="reconstruct-queue-row-actions">${actions.join("")}</div>
                </div>`;
        }).join("");
    }

    function restoreCancelButton(button) {
        if (!button) return;
        button.disabled = false;
        button.textContent = "Cancel";
    }

    async function cancelQueueJob(jobId, button) {
        if (!jobId) { restoreCancelButton(button); return; }
        if (!window.confirm("Cancel this job?")) {   // parity with Video tab
            restoreCancelButton(button);             // declined — re-enable the button
            return;
        }
        try {
            await reconstructionBridgeCall("cancel_job", { job_id: jobId });
            // No optimistic removal — the authoritative state surfaces on refresh,
            // which re-renders the row set (replacing this button).
            await loadJobs();
        } catch (e) {
            restoreCancelButton(button);             // failed — re-enable so the user can retry
            showReconstructStatus(`Cancel failed: ${errorToText(e)}`, "error");
        }
    }

    async function openJobResult(jobId) {
        try {
            showReconstructStatus(`Loading package for ${jobId}…`, "info");
            const result = await reconstructionBridgeCall("job_result", { job_id: jobId });
            renderResult(result);
            showReconstructStatus("Package loaded.", "success");
        } catch (e) {
            showReconstructStatus(errorToText(e), "error");
        }
    }

    // Source handoff from the Gallery "Send to 3D" shortcut: preselect the
    // chosen image artifact and navigate to this view. Single source path.
    function presetSource(artifact) {
        if (!artifact) return;
        if (reconstructMode === "t3d") setReconstructMode("i3d"); // no-mode/T3D → I3D; MV3D stays
        fillSlot("front", artifact);   // ALWAYS lands in the large pane
        switchView("reconstruct");
    }

    return { cacheEls, wireEvents, onEnter, presetSource };
})();

