# Reconstruct Tab — Video-Layout / Queue Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the Reconstruct tab into a two-column Video-style layout with a right-hand queue rail (filter chips + counts + summary, per-row Open/Cancel), keeping the result/import panel in the main column and preserving all existing image-to-3D behavior.

**Architecture:** Pure front-end refactor of embedded WebView resources (`index.html`, `app.js`, `styles.css`). The Reconstruct JS module gains filter state + a queue renderer; no backend, native, or host/panel-lifecycle changes. Pattern A only (WebView bridge calls).

**Tech Stack:** Vanilla JS WebView module, HTML, CSS (existing design tokens). No JS unit harness — verification is the panel-dark gate + C# regression suite + live smoke.

## Global Constraints

- Base: origin/main `655ef4e5`. Worktree `.worktrees/reconstruct-layout-parity`, branch `feature/reconstruct-video-layout-parity`.
- Layout mirrors `.video-layout` (grid `minmax(0,1.4fr) minmax(0,1fr)`, collapses <1024px). Result/import panel stays in the **main (left) column**.
- Filter buckets: **Active** = `queued|running|cancellation_requested`; **Complete** = `complete`; **Failed** = `error|interrupted`; **All** = everything incl. `cancelled`. `cancelled` is **All-only**; no Cancelled chip.
- Cancel: only `queued|running`; **`window.confirm("Cancel this job?")`** first; disable, call `cancel_job`, then `loadJobs`; **no optimistic removal**. `cancellation_requested` → disabled "Canceling…".
- Queue-row model label derives from **`j.model_id`** (no `model` field exists).
- Poll: `cancelled` → `showReconstructStatus("Reconstruction cancelled.", "info")` (neutral); `{error, interrupted}` → error copy.
- Filter state persists across refresh/poll; **submit switches filter to Active**; view-enter defaults to Active.
- Exactly **2 new cached IDs**: `reconstruct-queue-filters`, `reconstruct-queue-filter-summary`. Everything else via data-attributes + event delegation + scoped `querySelector`.
- **No** prompt scaffold, provider/text-to-3D/multi-view wiring, backend/native/host-lifecycle changes, second importer, or WebView HTTP.
- **Panel-dark gate is mandatory and BLOCKING after every JS checkpoint.** A failed gate stops the task.
- **Gate shell:** gate commands below are written in **PowerShell** (the repo's primary shell). `node --check` is shell-agnostic. (Git Bash equivalents are fine too, but avoid Bash-only `comm <(...)` process substitution in PowerShell.)

---

### Task 1: HTML — two-column layout + queue rail markup

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/index.html:664-708` (the `.reconstruct-body` block inside `#reconstruct-view`)

**Interfaces:**
- Produces: the DOM structure the JS module caches. New IDs: `reconstruct-queue-filters`, `reconstruct-queue-filter-summary`. Preserves all existing reconstruct IDs. Changes `#reconstruct-jobs-list` from `<ul>` to `<div class="reconstruct-queue-list">`. Refresh button keeps id `reconstruct-refresh-jobs`, restyled to `btn-icon`.

- [ ] **Step 1: Replace the `.reconstruct-body` block**

Replace lines 664–708 (`<div class="reconstruct-body"> … </div>`) with:

```html
                <div class="reconstruct-layout">
                    <div class="reconstruct-main">
                        <div class="panel reconstruct-form-panel">
                            <div class="panel-header">
                                <span class="panel-number">01</span>
                                <h2 class="panel-title">Generate</h2>
                            </div>
                            <div class="reconstruct-form">
                                <div class="reconstruct-field">
                                    <label class="reconstruct-label">Source image</label>
                                    <div class="reconstruct-source">
                                        <img id="reconstruct-source-thumb" class="reconstruct-source-thumb hidden" alt="source" />
                                        <span id="reconstruct-source-label" class="reconstruct-source-label">No image selected</span>
                                        <button id="reconstruct-choose-source" class="btn btn-secondary">Choose in Gallery…</button>
                                    </div>
                                </div>
                                <div class="reconstruct-field">
                                    <label class="reconstruct-label" for="reconstruct-model-select">Model</label>
                                    <select id="reconstruct-model-select" class="select"></select>
                                </div>
                                <div class="reconstruct-field">
                                    <label class="reconstruct-label">Output</label>
                                    <div class="reconstruct-segmented" role="radiogroup" aria-label="Output type">
                                        <button type="button" id="reconstruct-mode-textured" class="seg-btn active" data-mode="textured" role="radio" aria-checked="true">Textured</button>
                                        <button type="button" id="reconstruct-mode-geometry" class="seg-btn" data-mode="geometry" role="radio" aria-checked="false">Geometry only</button>
                                    </div>
                                </div>
                                <div class="reconstruct-actions">
                                    <button id="reconstruct-submit-btn" class="btn btn-primary">Reconstruct</button>
                                </div>
                                <div id="reconstruct-status-message" class="status-message hidden"></div>
                            </div>
                        </div>
                        <div id="reconstruct-result-panel" class="panel reconstruct-result-panel hidden">
                            <div class="panel-header">
                                <span class="panel-number">02</span>
                                <h2 class="panel-title">Result</h2>
                            </div>
                            <div class="reconstruct-result">
                                <div class="reconstruct-result-head">
                                    <img id="reconstruct-result-thumb" class="reconstruct-result-thumb hidden" alt="result" />
                                    <div id="reconstruct-result-meta" class="reconstruct-result-meta"></div>
                                </div>
                                <ul id="reconstruct-result-warnings" class="reconstruct-warnings hidden"></ul>
                                <div class="reconstruct-import">
                                    <button id="reconstruct-import-btn" class="btn btn-primary" disabled>Import to Rhino</button>
                                    <span id="reconstruct-import-status" class="reconstruct-import-status"></span>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="panel reconstruct-queue-panel">
                        <div class="panel-header">
                            <span class="panel-number">03</span>
                            <h2 class="panel-title">Queue</h2>
                            <button id="reconstruct-refresh-jobs" class="btn btn-icon" title="Refresh queue" aria-label="Refresh queue">
                                <svg viewBox="0 0 24 24" fill="none">
                                    <path d="M4 4V9H9M20 20V15H15M20.49 9A9 9 0 005.64 5.64L4 9M3.51 15A9 9 0 0018.36 18.36L20 15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                                </svg>
                            </button>
                        </div>
                        <div id="reconstruct-queue-filters" class="reconstruct-queue-filters" role="group" aria-label="Filter reconstruction queue">
                            <button type="button" class="reconstruct-queue-filter active" data-queue-filter="active" aria-pressed="true">Active <span class="reconstruct-queue-filter-count">0</span></button>
                            <button type="button" class="reconstruct-queue-filter" data-queue-filter="complete" aria-pressed="false">Complete <span class="reconstruct-queue-filter-count">0</span></button>
                            <button type="button" class="reconstruct-queue-filter" data-queue-filter="failed" aria-pressed="false">Failed <span class="reconstruct-queue-filter-count">0</span></button>
                            <button type="button" class="reconstruct-queue-filter" data-queue-filter="all" aria-pressed="false">All <span class="reconstruct-queue-filter-count">0</span></button>
                        </div>
                        <div id="reconstruct-queue-filter-summary" class="reconstruct-queue-filter-summary hidden" aria-live="polite"></div>
                        <div id="reconstruct-jobs-list" class="reconstruct-queue-list"></div>
                    </div>
                </div>
```

- [ ] **Step 2: Verify HTML integrity (panel-dark gate — structural portion)**

Run (PowerShell):
```powershell
$idx = "src/Rook/UI/Vision/Resources/index.html"
# Duplicate-id scan across whole file — expect NO output
(Select-String -Path $idx -Pattern 'id="([^"]+)"' -AllMatches).Matches |
  ForEach-Object { $_.Groups[1].Value } | Group-Object | Where-Object Count -gt 1 | Select-Object Name,Count
# The two NEW ids exist exactly once each — expect 1 and 1
(Select-String -Path $idx -Pattern 'id="reconstruct-queue-filters"').Count
(Select-String -Path $idx -Pattern 'id="reconstruct-queue-filter-summary"').Count
# Unique reconstruct id count (this match INCLUDES the section id reconstruct-view) — expect 19
((Select-String -Path $idx -Pattern 'id="(reconstruct-[^"]+)"' -AllMatches).Matches |
  ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique).Count
# Obsolete containers gone — expect NO output
Select-String -Path $idx -Pattern 'reconstruct-body|reconstruct-history|class="reconstruct-jobs"'
```
Expected: duplicate scan empty; both new-id counts `1`; unique reconstruct-id count **19** (17 existing — including `reconstruct-view` — plus the 2 new queue ids); obsolete-container scan empty.

- [ ] **Step 3: Commit**

```bash
git add src/Rook/UI/Vision/Resources/index.html
git commit -m "feat(reconstruct-ui): two-column layout + queue rail markup"
```

---

### Task 2: CSS — layout grid + queue classes; remove obsolete rules

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/styles.css` (reconstruct block starting ~line 2662)

**Interfaces:**
- Consumes: shared `.panel` / `.panel-header` / `.panel-number` / `.panel-title` rules (reused verbatim, not duplicated). Existing design tokens only.
- Produces: `.reconstruct-layout`, `.reconstruct-main`, queue classes. Removes `.reconstruct-body`, `.reconstruct-history*`, `.reconstruct-jobs`, `.reconstruct-job*`.

- [ ] **Step 1: Replace the `.reconstruct-body` rule with layout rules**

Replace line 2662 (`.reconstruct-body { display: flex; flex-direction: column; gap: var(--space-4); }`) with:

```css
.reconstruct-layout {
    display: grid;
    grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
    gap: var(--space-4);
    padding: 0 var(--space-5) var(--space-5);
}
@media (max-width: 1024px) {
    .reconstruct-layout { grid-template-columns: 1fr; }
}
.reconstruct-main { display: flex; flex-direction: column; gap: var(--space-4); min-width: 0; }
.reconstruct-form-panel,
.reconstruct-result-panel { background: var(--paper-card); border: 1px solid var(--rule); }
.reconstruct-form-panel .reconstruct-form { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-4); }
.reconstruct-result-panel .reconstruct-result { border: 0; }
.reconstruct-queue-panel {
    background: var(--paper-card);
    border: 1px solid var(--rule);
    align-self: start;
    min-width: 0;
}
```

(The existing `.reconstruct-form` rule at line 2663 is superseded by the scoped `.reconstruct-form-panel .reconstruct-form` above; delete the old line 2663 `.reconstruct-form { … }`.)

- [ ] **Step 2: Remove obsolete history/job rules and add queue rules**

Delete the `.reconstruct-history`, `.reconstruct-history-head`, `.reconstruct-history-title`, `.reconstruct-jobs`, and every `.reconstruct-job*` rule (the block from `.reconstruct-history {` through the end of the `.reconstruct-job*` rules — originally lines ~2752 onward). Replace them with the queue rules below:

```css
.reconstruct-queue-filters {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(104px, 100%), 1fr));
    gap: 4px;
    margin: var(--space-2) var(--space-4);
    padding: 4px;
    border: 1px solid var(--rule);
    background: var(--paper-tone);
}
.reconstruct-queue-filter {
    border: 0;
    background: transparent;
    color: var(--ink-soft);
    cursor: pointer;
    font-family: var(--type-mono);
    font-size: 12px;
    letter-spacing: 0.04em;
    line-height: 1.2;
    min-width: 0;
    padding: 6px 4px;
    text-transform: uppercase;
    white-space: nowrap;
}
.reconstruct-queue-filter:focus-visible { outline: 2px solid var(--accent-brass); outline-offset: 2px; }
.reconstruct-queue-filter:hover,
.reconstruct-queue-filter.active { background: var(--ink); color: var(--paper-bright); }
.reconstruct-queue-filter-count { font-feature-settings: var(--tabular); margin-left: 2px; }
.reconstruct-queue-filter-summary {
    margin: 0 var(--space-4) var(--space-2);
    padding: 6px var(--space-2);
    border: 1px solid color-mix(in srgb, var(--accent-amber) 70%, var(--rule));
    background: color-mix(in srgb, var(--accent-amber) 16%, var(--paper));
    color: var(--ink);
    font-size: 13px;
}
.reconstruct-queue-list {
    display: flex;
    flex-direction: column;
    gap: 1px;
    margin: 0 var(--space-4) var(--space-4);
    background: var(--rule);
    border: 1px solid var(--rule);
    max-height: clamp(220px, 42vh, 420px);
    min-height: 180px;
    overflow-y: auto;
    scrollbar-gutter: stable;
}
.reconstruct-queue-empty {
    padding: var(--space-5) var(--space-3);
    background: var(--paper-tone);
    text-align: center;
    color: var(--ink-soft);
}
.reconstruct-queue-empty span {
    display: block;
    font-family: var(--type-mono);
    font-size: 14.5px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: var(--space-1);
}
.reconstruct-queue-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    background: var(--paper);
    align-items: center;
}
.reconstruct-queue-row-state {
    font-family: var(--type-mono);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 2px 6px;
    background: var(--ink);
    color: var(--paper-bright);
    display: inline-block;
    margin-bottom: 4px;
}
.reconstruct-queue-row.state-complete .reconstruct-queue-row-state { background: var(--accent-green); }
.reconstruct-queue-row.state-error .reconstruct-queue-row-state,
.reconstruct-queue-row.state-interrupted .reconstruct-queue-row-state { background: var(--accent-red); }
.reconstruct-queue-row.state-cancelled .reconstruct-queue-row-state { background: var(--ink-soft); }
.reconstruct-queue-row.state-queued .reconstruct-queue-row-state,
.reconstruct-queue-row.state-running .reconstruct-queue-row-state,
.reconstruct-queue-row.state-cancellation_requested .reconstruct-queue-row-state { background: var(--accent-brass); }
.reconstruct-queue-row-id { font-family: var(--type-mono); font-size: 12px; color: var(--ink-soft); margin-left: var(--space-1); }
.reconstruct-queue-row-summary { font-size: 14.5px; color: var(--ink-soft); margin-top: 2px; }
.reconstruct-queue-row-error { color: var(--accent-red); font-size: 13px; line-height: 1.35; margin-top: 4px; word-break: break-word; }
.reconstruct-queue-row-actions { display: flex; gap: var(--space-1); }
.reconstruct-queue-canceling { font-family: var(--type-mono); font-size: 12px; color: var(--ink-soft); text-transform: uppercase; }
```

(Note: `cancelled` gets the neutral `--ink-soft` chip, NOT red — terminal-but-not-failed, consistent with the cancellation-copy pin.)

- [ ] **Step 2.5: Verify the seg-btn / result / warning / import rules were NOT touched**

The reconstruct result/warning/import/segmented rules (`.reconstruct-result*`, `.reconstruct-warning*`, `.reconstruct-import*`, `.reconstruct-segmented`, `.seg-btn*`, `.reconstruct-field`, `.reconstruct-label`, `.reconstruct-source*`, `.reconstruct-actions`) must remain. Confirm they still exist:
```bash
grep -cE '\.reconstruct-result-meta|\.reconstruct-import \{|\.seg-btn\.active|\.reconstruct-source-thumb' src/Rook/UI/Vision/Resources/styles.css
```
Expected: `4`.

- [ ] **Step 3: Verify no undefined CSS tokens + obsolete rules gone (gate — CSS portion)**

```powershell
$css = "src/Rook/UI/Vision/Resources/styles.css"
# Tokens referenced in the styles diff — confirm each is defined in :root (all are tokens .video-* already use)
git diff --unified=0 $css | Select-String -Pattern 'var\((--[a-z0-9-]+)\)' -AllMatches |
  ForEach-Object { $_.Matches } | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
# Obsolete rules removed — expect NO output
Select-String -Path $css -Pattern '\.reconstruct-body|\.reconstruct-history|\.reconstruct-jobs|\.reconstruct-job[ .{]'
```
Expected: every token in the diff is already defined in `:root` (all are tokens the `.video-*` rules already use — `--paper-card`, `--rule`, `--paper-tone`, `--ink`, `--ink-soft`, `--paper`, `--paper-bright`, `--accent-brass`, `--accent-green`, `--accent-red`, `--accent-amber`, `--space-*`, `--type-mono`, `--tabular`); obsolete-rule grep empty.

- [ ] **Step 4: Commit**

```bash
git add src/Rook/UI/Vision/Resources/styles.css
git commit -m "feat(reconstruct-ui): layout grid + queue-rail styles; drop history styles"
```

---

### Task 3: JS — filter state, queue renderer, counts/summary, Cancel/Open, cancelled copy

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/app.js` (the `Reconstruct` module, lines ~3323–3666)

**Interfaces:**
- Consumes: existing helpers `escapeHtml`, `escapeAttr`, `errorToText`, `delay`, `reconstructionBridgeCall`, `showReconstructStatus`, `renderResult`, `openJobResult`. New cached els `re.queueFilters`, `re.queueFilterSummary`.
- Produces: queue rendering driven by `currentJobs` + `queueFilter`; delegated chip/row handlers. No exported-surface change (`{ cacheEls, wireEvents, onEnter, presetSource }` unchanged).

- [ ] **Step 1: Update module constants + state**

Replace line 3326:
```javascript
    const TERMINAL_FAIL = new Set(["error", "cancelled", "interrupted"]);
```
with:
```javascript
    // cancelled is terminal-but-not-failed (All-only bucket); handled separately, NOT a failure.
    const TERMINAL_FAIL = new Set(["error", "interrupted"]);
    const ACTIVE_STATES = new Set(["queued", "running", "cancellation_requested"]);
    const FAILED_STATES = new Set(["error", "interrupted"]);
    const QUEUE_FILTERS = ["active", "complete", "failed", "all"];
```

Add to the state block (after line 3333 `let currentResultAvailable = false;`):
```javascript
    let currentJobs = [];         // last-loaded job list (queue source of truth)
    let queueFilter = "active";   // active | complete | failed | all
```

- [ ] **Step 2: Cache the two new IDs**

In `cacheEls()`, after line 3353 (`re.refreshJobsBtn = $("reconstruct-refresh-jobs");`) add:
```javascript
        re.queueFilters = $("reconstruct-queue-filters");
        re.queueFilterSummary = $("reconstruct-queue-filter-summary");
```

- [ ] **Step 3: Wire delegated chip + row handlers**

Replace the `wireEvents()` body's job-list listener (lines 3363–3367) with delegated chip + row handling:
```javascript
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
```

- [ ] **Step 4: Default filter on view-enter**

Replace `onEnter()` (lines 3370–3374) with:
```javascript
    async function onEnter() {
        await loadModels();
        renderSource();
        setQueueFilter("active");   // default view-enter filter
        await loadJobs();
    }
```

- [ ] **Step 5: Surface the new job + switch to Active on submit**

In `submit()`, replace the success path (lines 3420–3423):
```javascript
            if (!job || !job.job_id) {
                throw new Error("Reconstruction submit did not return a job id.");
            }
            await poll(job.job_id);
```
with:
```javascript
            if (!job || !job.job_id) {
                throw new Error("Reconstruction submit did not return a job id.");
            }
            setQueueFilter("active");   // surface the just-submitted job in the rail
            await loadJobs();
            await poll(job.job_id);
```

- [ ] **Step 6: Poll — cancelled reads as neutral, refresh rail on terminal**

Replace the `poll()` terminal handling (lines 3436–3446) with:
```javascript
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
```

- [ ] **Step 7: Replace loadJobs/renderJobs with the queue renderer**

Replace `loadJobs()` + `renderJobs()` (lines 3615–3639) with:
```javascript
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
```

- [ ] **Step 8: Run the panel-dark gate (FULL — blocking)**

```powershell
$app = "src/Rook/UI/Vision/Resources/app.js"
$idx = "src/Rook/UI/Vision/Resources/index.html"
# 1. Syntax
node --check $app; if ($LASTEXITCODE -eq 0) { "OK: app.js valid" }
# 2. Duplicate-id scan in index.html — expect NO output
(Select-String -Path $idx -Pattern 'id="([^"]+)"' -AllMatches).Matches |
  ForEach-Object { $_.Groups[1].Value } | Group-Object | Where-Object Count -gt 1 | Select-Object Name,Count
# 3. Every reconstruct $("id") cached in the module exists in index.html — expect NO output
$src = Get-Content -Raw $app
$mod = $src.Substring($src.IndexOf('Reconstruct module (image'))
$js = [regex]::Matches($mod, '\$\("(reconstruct-[^"]+)"\)') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
$html = (Select-String -Path $idx -Pattern 'id="(reconstruct-[^"]+)"' -AllMatches).Matches |
  ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
$js | Where-Object { $_ -notin $html }
# 4. Dangling references to removed symbols — expect NO output
Select-String -Path $app -Pattern 'renderJobs|reconstruct-job\b|reconstruct-jobs"|reconstruct-history|reconstruct-body'
# 5. The exactly-two new cached ids are referenced — expect >= 1 each
(Select-String -Path $app -Pattern 'reconstruct-queue-filters"').Count
(Select-String -Path $app -Pattern 'reconstruct-queue-filter-summary"').Count
```
Expected: `OK: app.js valid`; duplicate scan empty; missing-id check (3) empty; dangling-ref scan (4) empty; both new-id counts ≥ `1`. **Any non-empty result on checks 2/3/4 is a blocker — fix before commit.**

- [ ] **Step 9: Commit**

```bash
git add src/Rook/UI/Vision/Resources/app.js
git commit -m "feat(reconstruct-ui): queue filters/counts, Cancel/Open rows, cancelled neutral copy"
```

---

### Task 4: Full gate + C# regression + Release deploy + live smoke

**Files:** none (verification only).

- [ ] **Step 1: Re-run the full panel-dark gate** (all five checks from Task 3 Step 8) — all clean.

- [ ] **Step 2: C# regression suite (backend untouched — guard)**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug`
Expected: green (no backend change; confirm zero failures).

- [ ] **Step 3: Managed Release build + deploy (Rhino closed)**

```bash
dotnet build-server shutdown
dotnet build src/Rook/Rook.csproj -c Release
```
Expected: 0 errors; `DeployToRhino` copies `Rook.rhp` into `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\{net48,net7.0,net8.0}`. Confirm the deployed `net48\Rook.rhp` embeds `reconstruct-queue-filters` (grep the rhp).

- [ ] **Step 4: Live smoke (merge gate)**

Open Rhino → Vision → Reconstruct. Verify:
- Two-column layout; result/import panel in the main (left) column; queue rail on the right.
- Filter chips show correct counts; switching Active/Complete/Failed/All filters the rows; a `cancelled` job appears only under **All** (neutral chip, not red).
- Submit a textured Hunyuan run (Gallery → Send to 3D → Textured) → filter auto-switches to **Active**, the new job is visible; **Cancel** prompts a confirm, then (on confirm) disables and the job resolves to `cancelled` with neutral "Reconstruction cancelled." copy (no failure styling); no optimistic removal.
- Let a run complete → its row shows **Open** → click loads the result into the main-column panel (Available assets / Catalog preferred / Import will use) → **Import to Rhino** works with response-driven copy.

- [ ] **Step 5: Finish the branch**

Use superpowers:finishing-a-development-branch — verify tests, then push + open PR (non-squash, smoke marked passed), per user direction.

---

## Self-Review

**Spec coverage:** two-column layout (T1/T2); result in main column (T1); queue filters/counts/summary (T1/T3); per-row Open + Cancel-with-confirm, no optimistic removal (T3); `cancellation_requested` → Canceling… (T3); `cancelled` All-only + neutral copy + neutral chip (T2/T3); `model_id` source via `shortModelLabel` (T3); filter persists / submit→Active / view-enter Active (T3); 2 new IDs only + delegation (T1/T3); panel-dark gate after every JS checkpoint (T1/T2/T3); live smoke (T4). All covered.

**Placeholder scan:** none — every step has exact code and exact commands with expected output.

**Type/symbol consistency:** `currentJobs`, `queueFilter`, `ACTIVE_STATES`/`FAILED_STATES`/`QUEUE_FILTERS`, `re.queueFilters`/`re.queueFilterSummary`, `setQueueFilter`/`renderQueue`/`updateFilterCounts`/`renderQueueFilterSummary`/`inBucket`/`shortModelLabel`/`cancelQueueJob` are defined once and referenced consistently. `renderJobs` fully removed (dangling-ref check guards it). Row classes (`reconstruct-queue-cancel`/`-open`/`-row`/`-row-*`) match between JS (Task 3) and CSS (Task 2). New IDs match between HTML (Task 1) and JS cache (Task 3).
