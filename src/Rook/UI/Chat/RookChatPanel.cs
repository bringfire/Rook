using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Eto.Forms;
using Eto.Drawing;
using Rhino;
using Rhino.UI;
using Rook.UI.Panels;
using Rook.UI.Vision;

namespace Rook.UI.Chat
{
    /// <summary>
    /// Eto panel hosting a tabbed collection of chat sessions. Each tab is either a
    /// <see cref="ClaudeCodeTab"/> (persistent CLI subprocess) or an
    /// <see cref="AgentChatTab"/> (agent persona via the Python chat server).
    /// A toolbar with a "+" button opens a <see cref="PersonaPicker"/> dialog to
    /// create new tabs.
    /// </summary>
    [System.Runtime.InteropServices.Guid("A1B2C3D4-E5F6-7890-ABCD-EF1234567890")]
    public class RookChatPanel : Panel, IPanel
    {
        private uint _documentSerialNumber;
        private readonly Panel _tabHost;
        private readonly Dictionary<uint, TabControl> _tabControlsByDocument = new();
        private readonly HostedPanelLifecycleAdapter _lifecycle =
            new(typeof(RookChatPanel));

        /// <summary>
        /// Per-TabPage disposal callback registry. Lets the panel run
        /// cleanup for non-ChatTab tabs (e.g. VisionTab) without
        /// type-checking the page content. Fire-once invariants live
        /// in <see cref="TabCleanupRegistry"/> for unit-testability.
        /// </summary>
        private readonly TabCleanupRegistry _cleanup = new(
            msg => RhinoApp.WriteLine(msg));

        /// <summary>
        /// Panel unique identifier.
        /// </summary>
        public static Guid PanelId => typeof(RookChatPanel).GUID;

        /// <summary>
        /// Constructor called by Rhino.
        /// </summary>
        public RookChatPanel(uint documentSerialNumber)
        {
            _documentSerialNumber = NormalizeDocumentSerialNumber(documentSerialNumber);
            _tabHost = new Panel();

            // ── Toolbar ───────────────────────────────────────────────────
            var addButton = new Button { Text = "+", Width = 36, Height = 28 };
            addButton.Click += OnAddTabClicked;
            var restartButton = new Button { Text = "Restart Chat", Height = 28 };
            restartButton.Click += OnRestartChatClicked;

            var toolbar = new TableLayout
            {
                Padding = new Padding(4, 2),
                Spacing = new Size(4, 0),
                Rows = { new TableRow(addButton, restartButton, null) }
            };

            // ── Main layout ───────────────────────────────────────────────
            Content = new TableLayout
            {
                Spacing = new Size(0, 0),
                Rows =
                {
                    new TableRow(toolbar),
                    new TableRow(_tabHost) { ScaleHeight = true }
                }
            };
        }

        // ─── Tab creation helpers ────────────────────────────────────────

        private uint NormalizeDocumentSerialNumber(uint documentSerialNumber)
        {
            if (documentSerialNumber != 0)
            {
                return documentSerialNumber;
            }

            return RhinoDoc.ActiveDoc?.RuntimeSerialNumber ?? 0;
        }

        private TabControl GetOrCreateTabControl(uint documentSerialNumber)
        {
            documentSerialNumber = NormalizeDocumentSerialNumber(documentSerialNumber);
            if (_tabControlsByDocument.TryGetValue(documentSerialNumber, out var existing))
            {
                return existing;
            }

            var created = new TabControl();
            created.SelectedIndexChanged += OnTabSelectedIndexChanged;
            _tabControlsByDocument[documentSerialNumber] = created;
            return created;
        }

        private TabControl GetCurrentTabControl()
        {
            return GetOrCreateTabControl(_documentSerialNumber);
        }

        private void ShowDocumentTabs(uint documentSerialNumber)
        {
            _documentSerialNumber = NormalizeDocumentSerialNumber(documentSerialNumber);
            var tabs = GetCurrentTabControl();
            if (!ReferenceEquals(_tabHost.Content, tabs))
            {
                _tabHost.Content = tabs;
            }
        }

        /// <summary>
        /// Create and add a <see cref="ClaudeCodeTab"/>, passing through the
        /// document serial number for Rhino tool context.
        /// </summary>
        private async void AddClaudeCodeTab()
        {
            try
            {
                var documentSerialNumber = _documentSerialNumber;
                var tabControl = GetOrCreateTabControl(documentSerialNumber);
                var tab = new ClaudeCodeTab(documentSerialNumber);
                var page = CreateTabPage(tab.TabLabel, tab, tab.OnTabClosed, tabControl);
                tabControl.Pages.Add(page);
                tabControl.SelectedPage = page;

                await tab.InitializeAsync();
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"[RookChatPanel] Failed to add Claude Code tab: {ex.Message}");
            }
        }

        /// <summary>
        /// Create and add an <see cref="AgentChatTab"/> for the given persona.
        /// </summary>
        private async void AddAgentTab(string persona, string label, Color color)
        {
            try
            {
                var documentSerialNumber = _documentSerialNumber;
                var tabControl = GetOrCreateTabControl(documentSerialNumber);
                var tab = new AgentChatTab(
                    persona,
                    label,
                    color,
                    documentSerialNumber: documentSerialNumber);
                var page = CreateTabPage(tab.TabLabel, tab, tab.OnTabClosed, tabControl);
                tabControl.Pages.Add(page);
                tabControl.SelectedPage = page;

                await tab.InitializeAsync();
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"[RookChatPanel] Failed to add agent tab: {ex.Message}");
            }
        }

        /// <summary>
        /// Add a pre-built <see cref="Panel"/> as a tab in the current
        /// document's tab control. Non-ChatTab consumers (e.g. VisionTab)
        /// use this path; the <paramref name="onClosed"/> callback is
        /// invoked when the tab is removed OR when the panel is disposed,
        /// symmetric with <c>ChatTab.OnTabClosed</c>.
        /// </summary>
        internal TabPage AddPanelTab(string label, Panel content, Action? onClosed)
        {
            var documentSerialNumber = _documentSerialNumber;
            var tabControl = GetOrCreateTabControl(documentSerialNumber);
            var page = CreateTabPage(label, content, onClosed, tabControl);
            tabControl.Pages.Add(page);
            tabControl.SelectedPage = page;
            return page;
        }

        // ─── Legacy Vision tab entry point ──────────────────────────────

        /// <summary>
        /// Tab label used for the legacy Vision surface. The public
        /// <c>ShowRookVisionCommand</c> now opens the native
        /// <see cref="Rook.UI.Vision.RookVisionPanel"/> host; this path
        /// remains only for older in-process callers that may already have
        /// a Vision tab inside the chat panel.
        /// </summary>
        public const string VisionTabLabel = "Vision";

        /// <summary>
        /// Open the legacy Vision tab for the current document, or focus
        /// the existing one if already present. Deduplication is by
        /// tab-label equality — the panel owns at most one Vision tab per
        /// document.
        /// </summary>
        public void OpenOrFocusVisionTab()
        {
            var tabControl = GetCurrentTabControl();

            foreach (var existing in tabControl.Pages)
            {
                if (string.Equals(existing.Text, VisionTabLabel, StringComparison.Ordinal))
                {
                    tabControl.SelectedPage = existing;
                    return;
                }
            }

            var tab = new VisionTab();
            AddPanelTab(VisionTabLabel, tab, tab.OnTabClosed);
        }

        private void ReconcileHostedWebSurfaces(
            TabControl tabControl,
            string reason)
        {
            for (var i = 0; i < tabControl.Pages.Count; i++)
            {
                var page = tabControl.Pages[i];
                var selected = i == tabControl.SelectedIndex;

                if (page.Content is ChatTab chatTab)
                {
                    var surfaceId = BuildSurfaceId(chatTab.HostedSurfaceId);
                    _lifecycle.Reconcile(
                        surfaceId,
                        selected,
                        chatTab,
                        decision => ApplyHostedSurfaceDecision(chatTab, decision, reason));
                }
                else if (page.Content is VisionTab visionTab)
                {
                    var surfaceId = BuildSurfaceId(visionTab.HostedSurfaceId);
                    _lifecycle.Reconcile(
                        surfaceId,
                        selected,
                        visionTab,
                        decision => ApplyHostedSurfaceDecision(visionTab, decision, reason));
                }
            }
        }

        private string BuildSurfaceId(string tabSurfaceId)
        {
            return _documentSerialNumber.ToString() + ":" + tabSurfaceId;
        }

        private void ApplyHostedSurfaceDecision(
            ChatTab tab,
            HostedSurfaceDecision decision,
            string sourceReason)
        {
            switch (decision.Action)
            {
                case HostedSurfaceAction.Show:
                    // Selected tab: durable desired-visible true, then a
                    // level-triggered reconcile toward that state.
                    tab.SetPresentationDesiredVisible(true, sourceReason + ":" + decision.Reason);
                    tab.RequestPresentationReconcile(sourceReason + ":" + decision.Reason);
                    break;
                case HostedSurfaceAction.Hide:
                    // Unselected tab: per-tab-durable hide — Chat's own
                    // TabControl selection is authoritative here.
                    tab.SetPresentationDesiredVisible(false, sourceReason + ":" + decision.Reason);
                    break;
                case HostedSurfaceAction.Close:
                    tab.OnTabClosed();
                    _lifecycle.ForgetSurface(BuildSurfaceId(tab.HostedSurfaceId));
                    break;
            }
        }

        private void ApplyHostedSurfaceDecision(
            VisionTab tab,
            HostedSurfaceDecision decision,
            string sourceReason)
        {
            switch (decision.Action)
            {
                case HostedSurfaceAction.Show:
                    // Selected tab: durable desired-visible true, then a
                    // level-triggered reconcile toward that state.
                    tab.SetPresentationDesiredVisible(true, sourceReason + ":" + decision.Reason);
                    tab.RequestPresentationReconcile(sourceReason + ":" + decision.Reason);
                    break;
                case HostedSurfaceAction.Hide:
                    // Unselected tab: per-tab-durable hide — Chat's own
                    // TabControl selection is authoritative here.
                    tab.SetPresentationDesiredVisible(false, sourceReason + ":" + decision.Reason);
                    break;
                case HostedSurfaceAction.Close:
                    tab.OnTabClosed();
                    _lifecycle.ForgetSurface(BuildSurfaceId(tab.HostedSurfaceId));
                    break;
            }
        }

        /// <summary>
        /// Build a <see cref="TabPage"/> wrapping an arbitrary <see cref="Panel"/>
        /// with an optional cleanup callback. The callback is invoked
        /// exactly once — either when the user closes the tab via the
        /// context menu, or when the panel itself is disposed (whichever
        /// happens first). ChatTab callers pass <c>tab.OnTabClosed</c>;
        /// other panels supply their own disposal hook.
        ///
        /// <see cref="_cleanup"/> (a <see cref="TabCleanupRegistry"/>)
        /// holds the callbacks so <see cref="Dispose"/> can reach them
        /// without type-checking the page content. The registry owns
        /// the fire-once invariant.
        /// </summary>
        private TabPage CreateTabPage(string label, Panel content, Action? onClosed, TabControl owner)
        {
            var page = new TabPage
            {
                Text = label,
                Content = content
            };

            _cleanup.Register(page, onClosed);

            // Eto TabPage does not expose a Closable property on all platforms.
            // We use a context menu on the tab header as the universal close
            // mechanism.
            var menu = new ContextMenu();
            var closeItem = new ButtonMenuItem { Text = "Close Tab" };
            closeItem.Click += (s, e) => RemoveTab(owner, page);
            menu.Items.Add(closeItem);

            // Attach context menu to the page content so right-click works
            // anywhere inside the tab (Eto does not expose a per-tab-header
            // context menu, but this is the next best thing).
            page.ContextMenu = menu;

            return page;
        }

        /// <summary>
        /// Remove a tab page and fire its cleanup callback exactly once.
        /// Callback runs BEFORE the page is removed from the TabControl so
        /// subscribers can still read page state if needed.
        /// </summary>
        private void RemoveTab(TabControl owner, TabPage page)
        {
            if (page.Content is ChatTab chatTab)
            {
                _lifecycle.ForgetSurface(BuildSurfaceId(chatTab.HostedSurfaceId));
            }
            else if (page.Content is VisionTab visionTab)
            {
                _lifecycle.ForgetSurface(BuildSurfaceId(visionTab.HostedSurfaceId));
            }

            _cleanup.FireAndRemove(page);
            owner.Pages.Remove(page);
            ReconcileHostedWebSurfaces(owner, "TabRemoved");
        }

        // ─── "+" button handler ─────────────────────────────────────────

        private void OnAddTabClicked(object? sender, EventArgs e)
        {
            var picker = new PersonaPicker();
            var result = picker.ShowModal(this);

            if (result == null) return;

            if (result.IsClaudeCode)
            {
                AddClaudeCodeTab();
            }
            else
            {
                AddAgentTab(result.Persona, result.Label, result.Color);
            }
        }

        private async void OnRestartChatClicked(object? sender, EventArgs e)
        {
            try
            {
                await ChatServiceManager.Instance.RestartAsync();

                foreach (var tabControl in _tabControlsByDocument.Values)
                {
                    foreach (var page in tabControl.Pages)
                    {
                        if (page.Content is AgentChatTab agentTab)
                        {
                            await agentTab.ReconnectToServiceAsync();
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"[RookChatPanel] Failed to restart chat service: {ex.Message}");
            }
        }

        private void OnTabSelectedIndexChanged(object? sender, EventArgs e)
        {
            if (sender is TabControl tabControl)
            {
                ReconcileHostedWebSurfaces(tabControl, "TabSelectionChanged");
            }
        }

        #region IPanel Implementation

        /// <summary>
        /// Called when panel is shown.
        /// </summary>
        public void PanelShown(uint documentSerialNumber, ShowPanelReason reason)
        {
            documentSerialNumber = NormalizeDocumentSerialNumber(documentSerialNumber);
            _documentSerialNumber = documentSerialNumber;
            _lifecycle.PanelShown(documentSerialNumber, reason);
            ShowDocumentTabs(documentSerialNumber);

            // Auto-open Agent Chat on first show so the tab captures the active
            // Rhino document at display time, not constructor time.
            var tabControl = GetCurrentTabControl();
            if (tabControl.Pages.Count == 0)
            {
                AddAgentTab("architect", "Architect", Color.FromArgb(0xc0, 0x84, 0xfc));
            }

            ReconcileHostedWebSurfaces(tabControl, "PanelShown:" + reason);

        }

        /// <summary>
        /// Called when panel is hidden.
        /// </summary>
        public void PanelHidden(uint documentSerialNumber, ShowPanelReason reason)
        {
            documentSerialNumber = NormalizeDocumentSerialNumber(documentSerialNumber);
            _documentSerialNumber = documentSerialNumber;
            _lifecycle.PanelHidden(documentSerialNumber, reason);
            if (_tabControlsByDocument.TryGetValue(documentSerialNumber, out var tabControl))
            {
                ReconcileHostedWebSurfaces(tabControl, "PanelHidden:" + reason);
            }
        }

        /// <summary>
        /// Called when panel is closing.
        /// </summary>
        public void PanelClosing(uint documentSerialNumber, bool onCloseDocument)
        {
            documentSerialNumber = NormalizeDocumentSerialNumber(documentSerialNumber);
            _documentSerialNumber = documentSerialNumber;
            _lifecycle.PanelClosing(documentSerialNumber, onCloseDocument);
            if (_tabControlsByDocument.TryGetValue(documentSerialNumber, out var tabControl))
            {
                ReconcileHostedWebSurfaces(tabControl, "PanelClosing");
            }
        }

        #endregion

        /// <summary>
        /// Cleanup when panel is disposed. Drain every registered
        /// onClosed callback so both ChatTab and non-ChatTab tabs
        /// release their resources uniformly. Callbacks that already
        /// fired via <see cref="RemoveTab"/> have been removed from
        /// the registry, so Dispose does not double-fire them.
        /// </summary>
        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                _cleanup.DrainAll();
                foreach (var tabControl in _tabControlsByDocument.Values)
                {
                    tabControl.SelectedIndexChanged -= OnTabSelectedIndexChanged;
                    tabControl.Pages.Clear();
                }
                _tabControlsByDocument.Clear();
            }

            base.Dispose(disposing);
        }
    }
}
