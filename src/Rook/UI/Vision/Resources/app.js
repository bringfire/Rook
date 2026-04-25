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
    const msg = typeof response.data === "string"
        ? response.data
        : "Vision op failed.";
    throw new Error(msg);
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

// Viewport capture output (artifact envelope, keyed by view so we can
// re-feed its file_path into `generate` as `input_image_path`).
let capturedViewport = null;          // { artifact_id, file_path, ... } | null
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
    const selectedKey = el.viewportSelect.value || "";
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
        el.captureBtn.disabled = false;
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
        latestArtifactId = artifact.artifact_id;
        if (artifact.artifact_id) {
            el.resultImage.src = `/blob/${encodeURIComponent(artifact.artifact_id)}/image?ts=${Date.now()}`;
            el.resultPanel.classList.remove("hidden");
            showStatus("Image generated.", "success");
        } else {
            showStatus("Generation returned no artifact.", "error");
        }
    } catch (e) {
        showStatus(e.message, "error");
    } finally {
        setGenerating(el.generateBtn, el.generateText, el.generateSpinner, false);
    }
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
    const entry = modelCatalog.find(m => m.short_name === selected);
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
    selectEl.value = values.includes(previous) ? previous : "1K";
}

function syncResolutionOptions() {
    populateResolutionSelect(
        el.resolutionSelect,
        supportedResolutionsForSelectedModel(el.modelSelect));
    populateResolutionSelect(
        el.studioResolutionSelect,
        supportedResolutionsForSelectedModel(el.studioModelSelect));
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
        if (studioReferences.length > 0) {
            args.reference_image_paths = studioReferences.map(r => r.path);
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
        showStudioStatus(e.message, "error");
    } finally {
        setGenerating(el.studioGenerateBtn, el.studioGenerateText, el.studioGenerateSpinner, false);
    }
}

// ─── Gallery View ─────────────────────────────────────────────────

async function loadGallery() {
    el.galleryGrid.innerHTML = '<div class="gallery-empty"><span>Loading…</span></div>';
    try {
        const data = await bridgeCall("list_artifacts", {
            kind: "generated_image",
            limit: 100,
        });
        galleryItems = data.artifacts || [];

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
            const role = pickDisplayRole(item);
            const thumbUrl = role
                ? `/blob/${encodeURIComponent(id)}/${encodeURIComponent(role)}`
                : "";
            return `
                <div class="gallery-item ${approved ? "is-approved" : ""}" data-id="${escapeAttr(id)}">
                    <div class="gallery-thumb-wrap">
                        ${thumbUrl ? `<img src="${thumbUrl}" alt="Artifact thumbnail">` : '<div class="gallery-thumb-stub">no image</div>'}
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
    // Gallery summary embeds the `files[]` list. Pick an image-role
    // blob for the thumbnail.
    if (!summary || !Array.isArray(summary.files)) return null;
    const preferred = ["image", "thumbnail", "preview"];
    for (const role of preferred) {
        if (summary.files.some(f => f.role === role)) return role;
    }
    // Fall back to the first file whose extension looks like an image.
    for (const f of summary.files) {
        if (/\.(png|jpe?g|webp|gif|bmp)$/i.test(f.path || "")) return f.role;
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
    el.modalImage.src = src;
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
        if (data.has_api_key) {
            // Show the truncated preview in the input placeholder so
            // it's visibly clear the key persists across sessions —
            // matches SA_Banana's "AIza…xyz1" affordance. The input
            // value stays empty; re-saving is only needed to replace.
            const preview = data.api_key_preview || "API key configured";
            el.apiKey.placeholder = preview;
            el.apiKeyStatus.textContent = `API key configured (${preview}).`;
            el.apiKeyStatus.className = "status-indicator success";
        } else {
            el.apiKey.placeholder = "Enter your API key";
            el.apiKeyStatus.textContent = "No API key configured.";
            el.apiKeyStatus.className = "status-indicator error";
        }

        // Populate model dropdowns from the server-side catalog when
        // provided. If `available_models` is absent (e.g. an older
        // companion), leave the HTML-embedded defaults in place rather
        // than wiping them — that mistake was PR-7b's original "only
        // one option" bug.
        if (Array.isArray(data.available_models) && data.available_models.length > 0) {
            modelCatalog = data.available_models;
            const modelOptions = data.available_models.map(m => {
                const shortName = m.short_name || "";
                const label = m.label || shortName;
                const selected = shortName === data.default_model ? " selected" : "";
                const title = m.description ? ` title="${escapeAttr(m.description)}"` : "";
                return `<option value="${escapeAttr(shortName)}"${selected}${title}>${escapeHtml(label)}</option>`;
            }).join("");
            if (el.modelSelect) el.modelSelect.innerHTML = modelOptions;
            if (el.studioModelSelect) el.studioModelSelect.innerHTML = modelOptions;
            syncResolutionOptions();
        } else if (data.default_model) {
            // Server returned no catalog but did give a default — select
            // that option in the existing dropdown if it's there, else
            // leave the HTML defaults alone.
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

        if (modelCatalog.length === 0) {
            const allowed = data.allowed_resolutions || ["1K", "2K", "4K"];
            populateResolutionSelect(el.resolutionSelect, allowed);
            populateResolutionSelect(el.studioResolutionSelect, allowed);
        }
    } catch (e) {
        el.apiKeyStatus.textContent = e.message;
        el.apiKeyStatus.className = "status-indicator error";
    }
}

async function saveApiKey() {
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
    el.modalPrompt = $("modal-prompt");
    el.modalMeta = $("modal-meta");
    el.modalApproveBtn = $("modal-approve-btn");
    el.modalRevealBtn = $("modal-reveal-btn");
    el.modalDeleteBtn = $("modal-delete-btn");
    el.modalClose = document.querySelector(".modal-close");

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
    el.modelSelect.addEventListener("change", syncResolutionOptions);
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
    el.studioModelSelect.addEventListener("change", syncResolutionOptions);
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

    el.toggleKeyBtn.addEventListener("click", () => {
        const isPassword = el.apiKey.type === "password";
        el.apiKey.type = isPassword ? "text" : "password";
    });
    el.saveApiKeyBtn.addEventListener("click", saveApiKey);
    el.testApiKeyBtn.addEventListener("click", testApiKey);

    el.modalClose.addEventListener("click", closeModal);
    el.modal.addEventListener("click", (e) => { if (e.target === el.modal) closeModal(); });
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

    // Initial loads.
    loadViewports().then(captureViewport).catch(() => {});
    loadSettingsOverview();
}
