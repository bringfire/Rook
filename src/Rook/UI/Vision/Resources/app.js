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

// Viewport capture output (artifact envelope, keyed by view so we can
// re-feed its file_path into `generate` as `input_image_path`).
let capturedViewport = null;          // { artifact_id, file_path, ... } | null

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
        const options = [];
        (data.views || []).forEach(v => {
            const label = `${v.name} (${v.width}×${v.height})`;
            options.push(`<option value="${escapeAttr(v.name)}"${v.is_active ? " selected" : ""}>${escapeHtml(label)}</option>`);
        });
        (data.named_views || []).forEach(v => {
            options.push(`<option value="${escapeAttr(v.name)}">${escapeHtml(v.name)} (named)</option>`);
        });
        if (options.length === 0) {
            options.push('<option value="">No views available</option>');
        }
        el.viewportSelect.innerHTML = options.join("");
    } catch (e) {
        el.viewportSelect.innerHTML = `<option value="">${escapeHtml(e.message)}</option>`;
    }
}

async function captureViewport() {
    const viewName = el.viewportSelect.value || null;
    showStatus("Capturing viewport...", "info");
    el.captureBtn.disabled = true;

    try {
        const args = {};
        if (viewName) args.view_name = viewName;
        const artifact = await bridgeCall("capture_viewport", args);

        capturedViewport = artifact;
        if (artifact.artifact_id) {
            el.previewImage.src = `/blob/${encodeURIComponent(artifact.artifact_id)}/image?ts=${Date.now()}`;
            el.previewImage.style.display = "";
            el.previewPlaceholder.classList.add("hidden");
            hideStatus();
        } else {
            showStatus("Capture produced no artifact.", "error");
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
            el.enhanceHint.textContent = "Prompt enhanced. Original saved.";
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
            aspect_ratio: el.aspectSelect.value,
        };
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
    } else {
        el.studioSourceImage.src = "";
        el.studioSourcePlaceholder.classList.remove("hidden");
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
            aspect_ratio: el.studioAspectSelect.value,
        };
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
    const role = pickDisplayRole(modalArtifact);
    const src = role
        ? `/blob/${encodeURIComponent(id)}/${encodeURIComponent(role)}?ts=${Date.now()}`
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
        el.overviewDefaultModel.textContent = data.default_model || "—";
        el.overviewArtifactCount.textContent =
            (typeof data.artifact_count === "number") ? String(data.artifact_count) : "—";
        el.overviewKeyStatus.textContent = data.has_api_key ? "Configured" : "Not configured";
        if (data.has_api_key) {
            el.apiKeyStatus.textContent = "API key configured.";
            el.apiKeyStatus.className = "status-indicator success";
        } else {
            el.apiKeyStatus.textContent = "No API key configured.";
            el.apiKeyStatus.className = "status-indicator error";
        }

        // Populate model dropdowns with the default option.
        const modelOption = `<option value="" selected>${escapeHtml(data.default_model || "Default")}</option>`;
        if (el.modelSelect) el.modelSelect.innerHTML = modelOption;
        if (el.studioModelSelect) el.studioModelSelect.innerHTML = modelOption;

        // Populate resolution dropdowns with allowed values.
        const allowed = data.allowed_resolutions || ["1K", "2K", "4K"];
        const resOptions = allowed.map(r => `<option value="${escapeAttr(r)}">${escapeHtml(r)}</option>`).join("");
        if (el.resolutionSelect) el.resolutionSelect.innerHTML = resOptions;
        if (el.studioResolutionSelect) el.studioResolutionSelect.innerHTML = resOptions;
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
    el.referencePreview = $("reference-preview");
    el.addReferenceBtn = $("add-reference-btn");
    el.clearReferencesBtn = $("clear-references");

    // Studio
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

    // Settings
    el.apiKey = $("api-key");
    el.toggleKeyBtn = $("toggle-key");
    el.saveApiKeyBtn = $("save-api-key");
    el.testApiKeyBtn = $("test-api-key");
    el.apiKeyStatus = $("api-key-status");
    el.overviewDefaultModel = $("overview-default-model");
    el.overviewArtifactCount = $("overview-artifact-count");
    el.overviewKeyStatus = $("overview-key-status");

    // Modal
    el.modal = $("image-modal");
    el.modalImage = $("modal-image");
    el.modalPrompt = $("modal-prompt");
    el.modalMeta = $("modal-meta");
    el.modalApproveBtn = $("modal-approve-btn");
    el.modalDeleteBtn = $("modal-delete-btn");
    el.modalClose = document.querySelector(".modal-close");

    // ── Wire events ────────────────────────────────────────────

    el.navBtns.forEach(btn => btn.addEventListener("click", () => switchView(btn.dataset.view)));

    el.captureBtn.addEventListener("click", captureViewport);
    el.viewportSelect.addEventListener("change", captureViewport);
    el.enhanceBtn.addEventListener("click", enhancePrompt);
    el.generateBtn.addEventListener("click", generateImage);
    el.newBtn.addEventListener("click", () => {
        el.resultPanel.classList.add("hidden");
        el.prompt.value = "";
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
    el.modalDeleteBtn.addEventListener("click", () => {
        if (modalArtifact) deleteCurrentArtifact(modalArtifact.artifact_id);
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !el.modal.classList.contains("hidden")) closeModal();
    });

    // Initial loads.
    loadViewports().then(captureViewport).catch(() => {});
    loadSettingsOverview();
}
