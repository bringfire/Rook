// Knowledge Graph Visualizer
(function () {
    'use strict';

    // ─── DOM references ───────────────────────────────────────────
    var graphContainer = document.getElementById('graph-container');
    var loadingEl = document.getElementById('loading');
    var statusText = document.getElementById('status-text');
    var statusCounts = document.getElementById('status-counts');
    var searchInput = document.getElementById('search');
    var typeFilter = document.getElementById('type-filter');
    var categoryFilter = document.getElementById('category-filter');
    var btnFit = document.getElementById('btn-fit');
    var btnReset = document.getElementById('btn-reset');
    var sidebar = document.getElementById('sidebar');
    var sidebarTitle = document.getElementById('sidebar-title');
    var sidebarContent = document.getElementById('sidebar-content');
    var sidebarClose = document.getElementById('sidebar-close');
    var tooltipEl = document.getElementById('tooltip');
    var btnSimilar = document.getElementById('btn-similar');

    // ─── State ────────────────────────────────────────────────────
    var cy = null;
    var graphData = null;
    var selectedNodeId = null;
    var focusedNodeId = null;
    var sidebarFetchId = 0;  // guards against stale sidebar renders
    var similarEdgesData = [];  // stored separately, not in cytoscape
    var similarVisible = false;

    // ─── Node colors by type ──────────────────────────────────────
    var TYPE_COLORS = {
        component: '#3b82f6',
        recipe: '#22c55e',
        struggle: '#ef4444',
        teaching: '#f59e0b',
        command: '#a855f7'
    };

    // ─── Helpers ──────────────────────────────────────────────────
    function setStatus(text) {
        if (statusText) statusText.textContent = text;
    }

    function setCounts(nodes, edges) {
        if (statusCounts) statusCounts.textContent = nodes + ' nodes, ' + edges + ' edges';
    }

    function escapeHtml(text) {
        if (typeof text !== 'string') text = String(text);
        return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // ─── Tooltip ──────────────────────────────────────────────────
    function truncateBrief(text, maxLen) {
        if (!text || text.length <= maxLen) return text || '';
        var truncated = text.substring(0, maxLen);
        var lastSpace = truncated.lastIndexOf(' ');
        if (lastSpace > maxLen * 0.6) truncated = truncated.substring(0, lastSpace);
        return truncated + '...';
    }

    function showTooltip(node, clientX, clientY) {
        // Suppress when sidebar is open, unless in neighborhood focus mode
        // (user is exploring the neighborhood, not just inspecting one node)
        if (selectedNodeId && !focusedNodeId) return;
        // Don't show tooltip for dimmed/hidden nodes
        if (node.hasClass('dimmed') || node.hasClass('category-dimmed')) return;
        var d = node.data();
        tooltipEl.innerHTML =
            '<div class="tooltip-header">' +
                '<span class="tooltip-name">' + escapeHtml(d.label) + '</span>' +
                '<span class="tooltip-type ' + escapeHtml(d.noteType) + '">' + escapeHtml(d.noteType) + '</span>' +
            '</div>' +
            '<div class="tooltip-meta">' + escapeHtml(d.category) + '  &middot;  ' +
                d.inDegree + ' in / ' + d.outDegree + ' out</div>' +
            (d.brief ? '<div class="tooltip-brief">' + escapeHtml(truncateBrief(d.brief, 80)) + '</div>' : '');
        tooltipEl.classList.remove('hidden');
        positionTooltip(clientX, clientY);
    }

    function positionTooltip(cx, cy_) {
        var x = cx + 14;
        var y = cy_ + 14;
        var w = tooltipEl.offsetWidth;
        var h = tooltipEl.offsetHeight;
        var vw = window.innerWidth;
        var vh = window.innerHeight;
        if (x + w > vw - 8) x = cx - w - 14;
        if (y + h > vh - 8) y = cy_ - h - 14;
        x = Math.max(8, Math.min(x, vw - w - 8));
        y = Math.max(8, Math.min(y, vh - h - 8));
        tooltipEl.style.left = x + 'px';
        tooltipEl.style.top = y + 'px';
    }

    function hideTooltip() {
        tooltipEl.classList.add('hidden');
    }

    function buildFetchHeaders() {
        var headers = {};
        if (window.__rookSessionNonce) {
            headers['X-Rook-Session'] = window.__rookSessionNonce;
        }
        return headers;
    }

    function serviceUrl(path) {
        // Always use 127.0.0.1 to match CSP connect-src.  The chat server
        // binds to CHAT_SERVER_BIND_HOST = "127.0.0.1" and discovery files
        // record that literal.  Using the discovered host could yield
        // "localhost" which CSP would block.
        var port = window.__rookServicePort || '0';
        return 'http://127.0.0.1:' + port + path;
    }

    // ─── Register layout extensions ─────────────────────────────────
    // fcose: batch layout for initial positioning
    // cola: continuous force simulation for real-time physics
    var layoutsReady = (function registerLayouts() {
        var missing = [];
        if (typeof cytoscape === 'undefined') missing.push('cytoscape');
        if (typeof layoutBase === 'undefined') missing.push('layout-base');
        if (typeof coseBase === 'undefined') missing.push('cose-base');
        if (typeof cytoscapeFcose === 'undefined') missing.push('cytoscape-fcose');

        if (missing.length > 0) {
            var msg = 'Missing vendor libraries: ' + missing.join(', ');
            setStatus('Error: ' + msg);
            if (loadingEl) loadingEl.textContent = msg + '. Check embedded resources.';
            return false;
        }

        try { cytoscape.use(cytoscapeFcose); } catch (e) { /* already registered */ }

        // cola is optional — degrade to fcose-only if missing
        if (typeof cytoscapeCola !== 'undefined') {
            try { cytoscape.use(cytoscapeCola); } catch (e) { /* already registered */ }
        }

        return true;
    })();

    if (!layoutsReady) return;

    var colaAvailable = typeof cytoscapeCola !== 'undefined';
    var activeColaLayout = null;  // reference to running cola simulation

    // ─── Bootstrap with timeout ───────────────────────────────────
    var BOOTSTRAP_TIMEOUT_MS = 15000;

    function waitForBootstrap() {
        var start = Date.now();
        function poll() {
            if (window.__rookServiceHost && window.__rookServicePort) {
                setStatus('Connected');
                loadGraph();
                return;
            }
            if (Date.now() - start > BOOTSTRAP_TIMEOUT_MS) {
                setStatus('Service unavailable');
                if (loadingEl) loadingEl.textContent =
                    'Could not connect to Rook service. Try restarting the chat service or reopening this panel.';
                return;
            }
            setTimeout(poll, 100);
        }
        poll();
    }

    // ─── Graph loading ────────────────────────────────────────────
    function loadGraph() {
        setStatus('Loading graph...');
        fetch(serviceUrl('/knowledge/graph'), { headers: buildFetchHeaders() })
            .then(function (resp) {
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.json();
            })
            .then(function (data) {
                graphData = data;
                populateCategoryFilter(data.nodes);
                renderGraph(data);
                updateStatusBar();
                if (loadingEl) loadingEl.style.display = 'none';
            })
            .catch(function (err) {
                setStatus('Error: ' + err.message);
                if (loadingEl) loadingEl.textContent = 'Failed to load graph: ' + err.message;
            });
    }

    // ─── Category filter population ───────────────────────────────
    function populateCategoryFilter(nodes) {
        var categories = {};
        for (var i = 0; i < nodes.length; i++) {
            var cat = nodes[i].category;
            if (cat) categories[cat] = (categories[cat] || 0) + 1;
        }
        var sorted = Object.keys(categories).sort();
        for (var j = 0; j < sorted.length; j++) {
            var opt = document.createElement('option');
            opt.value = sorted[j];
            opt.textContent = sorted[j] + ' (' + categories[sorted[j]] + ')';
            categoryFilter.appendChild(opt);
        }
    }

    // ─── Cytoscape rendering ──────────────────────────────────────
    function renderGraph(data) {
        var elements = [];

        for (var i = 0; i < data.nodes.length; i++) {
            var n = data.nodes[i];
            elements.push({
                group: 'nodes',
                data: {
                    id: n.id,
                    label: n.label || n.id,
                    noteType: n.noteType,
                    category: n.category,
                    tags: n.tags,
                    components: n.components,
                    brief: n.brief,
                    degree: n.degree,
                    inDegree: n.inDegree,
                    outDegree: n.outDegree,
                    componentGuid: n.componentGuid,
                    created: n.created
                }
            });
        }

        for (var j = 0; j < data.edges.length; j++) {
            var e = data.edges[j];
            elements.push({
                group: 'edges',
                data: {
                    id: e.id,
                    source: e.source,
                    target: e.target,
                    linkType: e.linkType || 'related'
                }
            });
        }

        // Store similar edges for lazy toggle (not in cytoscape yet)
        similarEdgesData = data.similarEdges || [];

        cy = cytoscape({
            container: graphContainer,
            elements: elements,
            style: [
                {
                    selector: 'node',
                    style: {
                        'label': 'data(label)',
                        'font-size': '10px',
                        'color': '#ccc',
                        'text-valign': 'bottom',
                        'text-margin-y': 4,
                        'text-max-width': '80px',
                        'text-wrap': 'ellipsis',
                        'width': function (ele) { return Math.max(12, Math.min(40, 8 + ele.data('degree') * 1.5)); },
                        'height': function (ele) { return Math.max(12, Math.min(40, 8 + ele.data('degree') * 1.5)); },
                        'background-color': function (ele) { return TYPE_COLORS[ele.data('noteType')] || '#888'; },
                        'border-width': 0,
                        'opacity': 1
                    }
                },
                {
                    selector: 'node:selected',
                    style: {
                        'border-width': 3,
                        'border-color': '#fff',
                        'font-size': '12px',
                        'font-weight': 'bold',
                        'color': '#fff'
                    }
                },
                {
                    selector: 'node.dimmed',
                    style: { 'opacity': 0.15 }
                },
                {
                    selector: 'node.highlighted',
                    style: { 'border-width': 2, 'border-color': '#fff', 'opacity': 1 }
                },
                {
                    selector: 'node.category-spotlight',
                    style: {
                        'border-width': 3,
                        'border-color': function (ele) { return TYPE_COLORS[ele.data('noteType')] || '#fff'; },
                        'border-opacity': 0.9,
                        'opacity': 1,
                        'font-size': '11px',
                        'font-weight': 'bold',
                        'color': '#fff'
                    }
                },
                {
                    selector: 'node.category-dimmed',
                    style: {
                        'opacity': 0.1,
                        'label': ''
                    }
                },
                {
                    selector: 'edge',
                    style: {
                        'width': 1,
                        'line-color': '#444',
                        'target-arrow-color': '#444',
                        'target-arrow-shape': 'triangle',
                        'arrow-scale': 0.6,
                        'curve-style': 'bezier',
                        'opacity': 0.5
                    }
                },
                {
                    selector: 'edge.dimmed',
                    style: { 'opacity': 0.05 }
                },
                {
                    selector: 'edge.highlighted',
                    style: { 'line-color': '#888', 'target-arrow-color': '#888', 'opacity': 0.8, 'width': 1.5 }
                },
                {
                    selector: 'edge[linkType = "similar"]',
                    style: {
                        'line-style': 'dashed',
                        'line-color': '#a78bfa',
                        'target-arrow-shape': 'none',
                        'width': 0.8,
                        'opacity': 0.4,
                        'events': 'no'
                    }
                }
            ],
            // Start with fcose for initial positioning, then switch to
            // cola for continuous physics.  If cola is unavailable, fcose
            // is the final layout.
            layout: {
                name: 'fcose',
                animate: false,
                quality: 'default',
                nodeDimensionsIncludeLabels: false,
                idealEdgeLength: 80,
                nodeRepulsion: 8000,
                edgeElasticity: 0.45
            },
            minZoom: 0.1,
            maxZoom: 5,
            wheelSensitivity: 0.3
        });

        // After fcose finishes, run a bounded cola settle pass to
        // resolve any remaining overlaps, then freeze.
        if (colaAvailable) {
            settleColaPhysics();
        }

        cy.on('tap', 'node', function (evt) {
            hideTooltip();
            selectNode(evt.target.id());
        });

        cy.on('tap', function (evt) {
            if (evt.target === cy) clearSelection();
        });

        // Tooltip events — simple show/move/hide, no state tracking
        cy.on('mouseover', 'node', function (evt) {
            showTooltip(evt.target, evt.originalEvent.clientX, evt.originalEvent.clientY);
        });

        cy.on('mousemove', 'node', function (evt) {
            if (!tooltipEl.classList.contains('hidden')) {
                positionTooltip(evt.originalEvent.clientX, evt.originalEvent.clientY);
            }
        });

        cy.on('mouseout', 'node', function () {
            hideTooltip();
        });

    }

    // ─── Cola physics — bounded settle only ──────────────────────
    // Cola runs once after initial layout and after topology changes
    // (edge toggle, reset) to resolve overlaps, then stops.  After
    // that, dragging is plain cytoscape grab-and-move — no physics.

    var SETTLE_MS = 2500;

    function settleColaPhysics() {
        if (!cy || !colaAvailable) return;
        stopColaPhysics();

        activeColaLayout = cy.layout({
            name: 'cola',
            animate: true,
            refresh: 3,
            infinite: false,
            maxSimulationTime: SETTLE_MS,
            fit: false,
            randomize: false,
            centerGraph: false,
            avoidOverlap: true,
            ungrabifyWhileSimulating: false,
            handleDisconnected: true,
            nodeDimensionsIncludeLabels: false,
            nodeSpacing: function () { return 12; },
            edgeLength: function (edge) {
                return edge.data('linkType') === 'similar' ? 200 : 100;
            },
            convergenceThreshold: 0.001
        });

        activeColaLayout.run();
    }

    function stopColaPhysics() {
        if (activeColaLayout) {
            activeColaLayout.stop();
            activeColaLayout = null;
        }
    }

    // ─── Node selection + sidebar ─────────────────────────────────
    function selectNode(nodeId) {
        hideTooltip();
        selectedNodeId = nodeId;
        cy.nodes().unselect();
        cy.getElementById(nodeId).select();
        showSidebar(nodeId);
    }

    function clearSelection() {
        hideTooltip();
        selectedNodeId = null;
        if (cy) cy.nodes().unselect();
        sidebar.classList.add('hidden');
    }

    function showSidebar(nodeId) {
        sidebar.classList.remove('hidden');
        sidebarTitle.textContent = 'Loading...';
        sidebarContent.innerHTML = '';

        // Guard: increment fetch ID so stale responses are discarded
        var thisFetchId = ++sidebarFetchId;

        fetch(serviceUrl('/knowledge/note/' + nodeId), { headers: buildFetchHeaders() })
            .then(function (resp) {
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.json();
            })
            .then(function (data) {
                // Discard if user clicked a different node while loading
                if (thisFetchId !== sidebarFetchId) return;
                renderNoteDetail(data);
            })
            .catch(function (err) {
                if (thisFetchId !== sidebarFetchId) return;
                sidebarTitle.textContent = nodeId;
                sidebarContent.innerHTML = '<p style="color:#f87171">Failed to load note: ' + escapeHtml(err.message) + '</p>';
            });
    }

    function renderNoteDetail(data) {
        var note = data.note;
        var related = data.related;

        sidebarTitle.textContent = note.name || note.note_id;

        var html = '';

        html += '<div class="field"><span class="type-badge ' + escapeHtml(note.note_type) + '">' +
                escapeHtml(note.note_type) + '</span></div>';

        if (note.brief) {
            html += '<div class="field"><div class="field-label">Brief</div>' +
                    '<div class="field-value">' + escapeHtml(note.brief) + '</div></div>';
        }

        if (note.context) {
            html += '<div class="field"><div class="field-label">Context</div>' +
                    '<div class="field-value">' + escapeHtml(note.context) + '</div></div>';
        }

        html += '<div class="field"><div class="field-label">Category</div>' +
                '<div class="field-value">' + escapeHtml(note.category) + '</div></div>';

        if (note.tags && note.tags.length > 0) {
            html += '<div class="field"><div class="field-label">Tags</div><div class="field-value">';
            for (var i = 0; i < note.tags.length; i++) {
                html += '<span class="tag">' + escapeHtml(note.tags[i]) + '</span>';
            }
            html += '</div></div>';
        }

        if (note.components && note.components.length > 0) {
            html += '<div class="field"><div class="field-label">Components</div><div class="field-value">';
            for (var j = 0; j < note.components.length; j++) {
                html += '<span class="tag">' + escapeHtml(note.components[j]) + '</span>';
            }
            html += '</div></div>';
        }

        var guid = (note.type_data || {}).guid;
        if (guid) {
            html += '<div class="field"><div class="field-label">GUID</div>' +
                    '<div class="field-value" style="font-family:var(--font-mono);font-size:11px">' +
                    escapeHtml(guid) + '</div></div>';
        }

        if (note.solution_principle) {
            html += '<div class="field"><div class="field-label">Solution</div>' +
                    '<div class="field-value">' + escapeHtml(note.solution_principle) + '</div></div>';
        }

        if (related.linksFrom && related.linksFrom.length > 0) {
            html += '<div class="field links-section"><div class="field-label">Links to (' + related.linksFrom.length + ')</div>';
            for (var k = 0; k < related.linksFrom.length; k++) {
                var targetId = related.linksFrom[k];
                var targetNode = cy.getElementById(targetId);
                var targetLabel = targetNode.length > 0 ? targetNode.data('label') : targetId;
                html += '<div class="link-item" data-node-id="' + escapeHtml(targetId) + '">' +
                        escapeHtml(targetLabel) + '</div>';
            }
            html += '</div>';
        }

        if (related.linksTo && related.linksTo.length > 0) {
            html += '<div class="field links-section"><div class="field-label">Linked from (' + related.linksTo.length + ')</div>';
            for (var m = 0; m < related.linksTo.length; m++) {
                var srcId = related.linksTo[m];
                var srcNode = cy.getElementById(srcId);
                var srcLabel = srcNode.length > 0 ? srcNode.data('label') : srcId;
                html += '<div class="link-item" data-node-id="' + escapeHtml(srcId) + '">' +
                        escapeHtml(srcLabel) + '</div>';
            }
            html += '</div>';
        }

        html += '<div class="field"><div class="field-label">ID</div>' +
                '<div class="field-value" style="font-family:var(--font-mono);font-size:11px">' +
                escapeHtml(note.note_id) + '</div></div>';

        if (note.created) {
            html += '<div class="field"><div class="field-label">Created</div>' +
                    '<div class="field-value">' + escapeHtml(note.created) + '</div></div>';
        }

        sidebarContent.innerHTML = html;

        var linkItems = sidebarContent.querySelectorAll('.link-item');
        for (var n = 0; n < linkItems.length; n++) {
            linkItems[n].addEventListener('click', function () {
                var nid = this.getAttribute('data-node-id');
                if (cy.getElementById(nid).length > 0) {
                    selectNode(nid);
                    cy.animate({ center: { eles: cy.getElementById(nid) }, duration: 300 });
                }
            });
        }
    }

    // ─── Unified visibility recompute ─────────────────────────────
    // Single pass that ANDs all active constraints: search, type
    // filter, category filter, and neighborhood focus.  No control
    // overrides another.
    var ALL_VIS_CLASSES = 'dimmed highlighted category-spotlight category-dimmed';

    function recomputeVisibility() {
        if (!cy) return;

        var searchQuery = (searchInput.value || '').toLowerCase();
        var typeVal = typeFilter.value;
        var catVal = categoryFilter.value;
        var hasConstraint = searchQuery || typeVal || catVal || focusedNodeId;

        // Category spotlight activates when category filter is set AND
        // neighborhood focus is NOT active.  Neighborhood focus is a
        // different mode that overrides the spotlight treatment.
        var useCategorySpotlight = !!catVal && !focusedNodeId;

        if (!hasConstraint) {
            cy.batch(function () {
                cy.nodes().removeClass(ALL_VIS_CLASSES);
                cy.edges().removeClass('dimmed highlighted');
            });
            updateStatusBar();
            return;
        }

        // Neighborhood set (if focused)
        var neighborhoodSet = null;
        if (focusedNodeId) {
            var focusNode = cy.getElementById(focusedNodeId);
            if (focusNode.length > 0) {
                neighborhoodSet = new Set();
                neighborhoodSet.add(focusNode.id());
                // Use structural edges only (not similar) for neighborhood
                focusNode.connectedEdges('[linkType = "related"]').connectedNodes().forEach(function (n) {
                    neighborhoodSet.add(n.id());
                });
            }
        }

        var visibleCount = 0;

        // Wrap all class changes in cy.batch() to prevent synthetic
        // mouseout events during filter recompute.  Cytoscape defers
        // event emission until the batch completes.
        cy.batch(function () {
            cy.nodes().forEach(function (node) {
                var d = node.data();
                var visible = true;

                // Type filter
                if (typeVal && d.noteType !== typeVal) visible = false;

                // Category filter
                if (visible && catVal && d.category !== catVal) visible = false;

                // Search filter
                if (visible && searchQuery) {
                    var match = false;
                    if (d.id.toLowerCase().indexOf(searchQuery) !== -1) match = true;
                    else if (d.label.toLowerCase().indexOf(searchQuery) !== -1) match = true;
                    else if (d.category && d.category.toLowerCase().indexOf(searchQuery) !== -1) match = true;
                    else if (d.tags) {
                        for (var i = 0; i < d.tags.length; i++) {
                            if (d.tags[i].toLowerCase().indexOf(searchQuery) !== -1) { match = true; break; }
                        }
                    }
                    if (!match && d.components) {
                        for (var j = 0; j < d.components.length; j++) {
                            if (d.components[j].toLowerCase().indexOf(searchQuery) !== -1) { match = true; break; }
                        }
                    }
                    if (!match) visible = false;
                }

                // Neighborhood filter
                if (visible && neighborhoodSet && !neighborhoodSet.has(d.id)) visible = false;

                // Apply classes
                node.removeClass(ALL_VIS_CLASSES);
                if (visible) {
                    visibleCount++;
                    if (useCategorySpotlight) {
                        node.addClass('category-spotlight');
                    } else {
                        node.addClass('highlighted');
                    }
                } else {
                    if (useCategorySpotlight) {
                        node.addClass('category-dimmed');
                    } else {
                        node.addClass('dimmed');
                    }
                }
            });

            cy.edges().forEach(function (edge) {
                if (edge.source().hasClass('dimmed') || edge.source().hasClass('category-dimmed') ||
                    edge.target().hasClass('dimmed') || edge.target().hasClass('category-dimmed')) {
                    edge.addClass('dimmed').removeClass('highlighted');
                } else {
                    edge.removeClass('dimmed').addClass('highlighted');
                }
            });
        });

        // Auto-fit to visible nodes when neighborhood is active
        if (focusedNodeId) {
            var visibleNodes = cy.nodes().not('.dimmed').not('.category-dimmed');
            if (visibleNodes.length > 0) {
                cy.animate({ fit: { eles: visibleNodes, padding: 40 }, duration: 400 });
            }
        }

        updateStatusBar(visibleCount);
    }

    // ─── Unified status bar ──────────────────────────────────────
    function updateStatusBar(visibleCount) {
        if (!graphData) return;

        // Right side: counts
        var counts = graphData.meta.noteCount + ' nodes, ' + graphData.meta.edgeCount + ' edges';
        if (similarVisible && graphData.meta.similarEdgeCount) {
            counts += ' + ' + graphData.meta.similarEdgeCount + ' similar';
        }
        if (statusCounts) statusCounts.textContent = counts;

        // Left side: contextual status.
        // Priority: neighborhood > category > search > default.
        // Neighborhood is most specific (user double-clicked a node).
        var catVal = categoryFilter.value;
        var searchQuery = searchInput.value;
        var text = 'Ready';

        if (focusedNodeId) {
            var focusNode = cy ? cy.getElementById(focusedNodeId) : null;
            var label = focusNode && focusNode.length > 0 ? focusNode.data('label') : focusedNodeId;
            text = "Neighborhood of '" + label + "'";
            if (visibleCount !== undefined) text += ' (' + visibleCount + ' nodes)';
        } else if (catVal && visibleCount !== undefined) {
            text = 'Showing ' + visibleCount + " nodes in '" + catVal + "'";
        } else if (searchQuery && visibleCount !== undefined) {
            text = visibleCount + ' matches';
        }

        if (statusText) statusText.textContent = text;
    }

    // ─── Focus neighborhood ───────────────────────────────────────
    function focusNeighborhood(nodeId) {
        focusedNodeId = nodeId;
        recomputeVisibility();
    }

    // ─── Similar edge toggle ─────────────────────────────────────
    function toggleSimilarEdges() {
        if (!cy) return;
        similarVisible = !similarVisible;

        cy.batch(function () {
            if (similarVisible) {
                // Add similar edges to cytoscape
                var edgesToAdd = [];
                for (var i = 0; i < similarEdgesData.length; i++) {
                    var e = similarEdgesData[i];
                    edgesToAdd.push({
                        group: 'edges',
                        data: {
                            id: e.id,
                            source: e.source,
                            target: e.target,
                            linkType: 'similar'
                        }
                    });
                }
                cy.add(edgesToAdd);
            } else {
                // Remove similar edges from cytoscape
                cy.edges('[linkType = "similar"]').remove();
            }
        });

        btnSimilar.classList.toggle('active', similarVisible);
        // Bounded settle to account for the changed edge set
        settleColaPhysics();
        recomputeVisibility();
    }

    // ─── Reset ────────────────────────────────────────────────────
    function resetAll() {
        if (!cy) return;
        searchInput.value = '';
        typeFilter.value = '';
        categoryFilter.value = '';
        focusedNodeId = null;
        // Clear selection state so tooltips aren't permanently suppressed
        selectedNodeId = null;
        cy.nodes().unselect();
        sidebar.classList.add('hidden');
        hideTooltip();
        // Remove similar edges if active
        if (similarVisible) {
            similarVisible = false;
            btnSimilar.classList.remove('active');
        }
        cy.batch(function () {
            cy.edges('[linkType = "similar"]').remove();
            cy.nodes().removeClass(ALL_VIS_CLASSES);
            cy.edges().removeClass('dimmed highlighted');
        });
        updateStatusBar();
        cy.fit(undefined, 40);
        // Bounded settle after reset — don't restart perpetual physics
        settleColaPhysics();
    }

    // ─── Event wiring ─────────────────────────────────────────────
    searchInput.addEventListener('input', function () {
        recomputeVisibility();
    });

    typeFilter.addEventListener('change', recomputeVisibility);
    categoryFilter.addEventListener('change', recomputeVisibility);

    btnSimilar.addEventListener('click', toggleSimilarEdges);

    btnFit.addEventListener('click', function () {
        if (cy) cy.fit(undefined, 40);
    });

    btnReset.addEventListener('click', resetAll);

    sidebarClose.addEventListener('click', function () {
        clearSelection();
    });

    // Double-click to focus neighborhood
    if (graphContainer) {
        graphContainer.addEventListener('dblclick', function () {
            if (selectedNodeId) focusNeighborhood(selectedNodeId);
        });
    }

    // ─── Start ────────────────────────────────────────────────────
    setStatus('Waiting for service...');
    waitForBootstrap();
})();
