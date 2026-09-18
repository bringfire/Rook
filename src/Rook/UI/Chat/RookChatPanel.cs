using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
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
    /// Eto panel hosting Prime ACP conversations through the Python product service.
    /// </summary>
    [System.Runtime.InteropServices.Guid("A1B2C3D4-E5F6-7890-ABCD-EF1234567890")]
    public class RookChatPanel : Panel, IPanel
    {
        private uint _documentSerialNumber;
        private readonly Panel _tabHost;
        private bool _configurationOpen, _panelDisposed;
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
            var settingsButton = new Button { Text = "Settings", Height = 28 };
            settingsButton.Click += OnConfigurationClicked;
            var toolbar = new TableLayout
            {
                Padding = new Padding(4, 2),
                Spacing = new Size(4, 0),
                Rows = { new TableRow(addButton, null, settingsButton) }
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

        private async Task AddAgentTabAsync(AgentChatTab tab)
        {
            try
            {
                var documentSerialNumber = _documentSerialNumber;
                var tabControl = GetOrCreateTabControl(documentSerialNumber);
                var page = CreateTabPage(tab.TabLabel, tab, tab.OnTabClosed, tabControl);
                tabControl.Pages.Add(page);
                tabControl.SelectedPage = page;

                await tab.InitializeAsync();
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"[RookChatPanel] Failed to add Prime tab: {ex.Message}");
            }
        }

        private CreateConversationRequest BuildCreateRequest(string? model, string? reasoning)
        {
            var document = RhinoDoc.FromRuntimeSerialNumber(_documentSerialNumber)
                ?? throw new InvalidOperationException("The bound Rhino document is no longer available.");
            var processId = Process.GetCurrentProcess().Id;
            var hostGenerationId = ResolveHostGenerationId(processId)
                ?? throw new InvalidOperationException("Rook host identity is unavailable. Wait for the native plugin to finish starting.");
            string? savedDirectory = null;
            if (!string.IsNullOrWhiteSpace(document.Path))
            {
                var parent = Path.GetDirectoryName(document.Path);
                if (!string.IsNullOrWhiteSpace(parent)) savedDirectory = Path.GetFullPath(parent!);
            }
            return new CreateConversationRequest
            {
                HostGenerationId = hostGenerationId,
                DocumentSerialNumber = document.RuntimeSerialNumber,
                RouteProcessId = processId,
                SavedDocumentDirectory = savedDirectory,
                Model = model,
                Reasoning = reasoning,
            };
        }

        internal static string? ResolveHostGenerationId(int processId)
        {
            var values = new HashSet<string>(StringComparer.Ordinal);
            foreach (var folder in new[] { RookPaths.SharedDiscoveryFolder, RookPaths.DiscoveryFolder })
            {
                if (string.IsNullOrEmpty(folder) || !Directory.Exists(folder)) continue;
                foreach (var path in Directory.EnumerateFiles(folder, "*.json"))
                {
                    try
                    {
                        using var document = JsonDocument.Parse(File.ReadAllText(path));
                        var value = ReadNativeHostGenerationId(document.RootElement, processId);
                        if (value != null) values.Add(value);
                    }
                    catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException)
                    {
                    }
                }
            }
            return values.Count == 1 ? values.Single() : null;
        }

        internal static string? ReadNativeHostGenerationId(JsonElement root, int processId)
        {
            if (root.ValueKind != JsonValueKind.Object ||
                !root.TryGetProperty("pluginType", out var pluginType) ||
                pluginType.ValueKind != JsonValueKind.String ||
                pluginType.GetString() != "native" ||
                !root.TryGetProperty("processId", out var pid) ||
                pid.ValueKind != JsonValueKind.Number ||
                !pid.TryGetInt32(out var actualProcessId) ||
                actualProcessId != processId ||
                !root.TryGetProperty("hostGenerationId", out var generation) ||
                generation.ValueKind != JsonValueKind.String)
                return null;
            var raw = generation.GetString();
            return raw != null && Guid.TryParseExact(raw, "D", out var parsed) &&
                   string.Equals(raw, parsed.ToString("D"), StringComparison.Ordinal)
                ? raw
                : null;
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
            if (content is AgentChatTab agentTab)
            {
                var deleteItem = new ButtonMenuItem { Text = "Delete Conversation" };
                deleteItem.Click += async (s, e) =>
                {
                    var confirmation = MessageBox.Show(
                        this,
                        "Permanently delete this Prime conversation and its product-owned artifacts?",
                        "Delete Conversation",
                        MessageBoxButtons.YesNo,
                        MessageBoxType.Warning);
                    if (confirmation != DialogResult.Yes) return;
                    try
                    {
                        var result = await agentTab.DeleteConversationAsync();
                        RemoveTab(owner, page);
                        if (!result.ArtifactsRemoved)
                        {
                            MessageBox.Show(
                                this,
                                "The conversation was deleted, but some product-owned artifacts could not be removed.",
                                "Delete Conversation");
                        }
                    }
                    catch (Exception ex)
                    {
                        MessageBox.Show(this, ex.Message, "Delete Conversation");
                    }
                };
                menu.Items.Add(deleteItem);
            }

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

        private async void OnConfigurationClicked(object? sender, EventArgs e)
        {
            if (_configurationOpen || _panelDisposed) return;
            _configurationOpen = true;
            try
            {
                using var client = new AgentChatClient();
                var health = await client.GetHealthAsync(startIfNeeded: true);
                if (_panelDisposed) return;
                if (!health.ServiceAvailable)
                {
                    MessageBox.Show(this, "Chat configuration service is unavailable.", "RookChat Settings");
                    return;
                }
                client.SetSessionNonce(ChatServiceManager.Instance.SessionNonce);
                using var dialog = new RookChatConfigurationDialog(client);
                dialog.Shown += async (_, _) => await dialog.InitializeAsync();
                dialog.ShowModal(this);
                await dialog.PendingOperation;
            }
            catch
            {
                if (!_panelDisposed) MessageBox.Show(this, "Configuration could not complete. A saved change is not rolled back by a communication failure.", "RookChat Settings");
            }
            finally { _configurationOpen = false; }
        }

        private async void OnAddTabClicked(object? sender, EventArgs e)
        {
            try
            {
                using var client = new AgentChatClient();
                var health = await client.GetHealthAsync(startIfNeeded: true);
                if (!health.ServiceAvailable)
                    throw new InvalidOperationException(health.ServiceMessage);
                client.SetSessionNonce(ChatServiceManager.Instance.SessionNonce);
                var conversations = await client.ListAsync();
                var dialog = new PrimeConversationDialog(conversations);
                var selection = dialog.ShowModal(this);
                if (selection == null) return;
                if (!string.IsNullOrEmpty(selection.ReopenConversationId))
                {
                    var association = conversations.First(
                        item => item.ConversationId == selection.ReopenConversationId);
                    await AddAgentTabAsync(new AgentChatTab(association));
                }
                else
                {
                    await AddAgentTabAsync(new AgentChatTab(
                        BuildCreateRequest(selection.RequestedModel, selection.RequestedReasoning)));
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, ex.Message, "Prime Conversation");
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

            var tabControl = GetCurrentTabControl();
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
                _panelDisposed = true;
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

        internal static bool IsQualifiedRequestedModel(string model)
            => model.IndexOf('/') >= 0 && !model.Split(new[] { '/' }, 2).Any(string.IsNullOrWhiteSpace);

        private sealed class PrimeConversationDialogResult
        {
            public string? ReopenConversationId { get; set; }
            public string? RequestedModel { get; set; }
            public string? RequestedReasoning { get; set; }
        }

        private sealed class PrimeConversationDialog : Dialog<PrimeConversationDialogResult?>
        {
            private static readonly string[] ReasoningValues =
                { "", "off", "minimal", "low", "medium", "high", "xhigh", "max" };

            private readonly DropDown _conversation = new();
            private readonly TextBox _model = new();
            private readonly DropDown _reasoning = new();

            public PrimeConversationDialog(IReadOnlyList<ConversationSummary> conversations)
            {
                Title = "Prime Conversation";
                MinimumSize = new Size(440, 230);
                Padding = new Padding(12);
                _conversation.Items.Add(new ListItem { Text = "New conversation", Key = "" });
                foreach (var item in conversations)
                {
                    var disclosure = string.IsNullOrEmpty(item.RequestedInitialModel)
                        ? "Prime default"
                        : item.RequestedInitialModel;
                    _conversation.Items.Add(new ListItem
                    {
                        Text = $"{item.ConversationId.Substring(0, Math.Min(8, item.ConversationId.Length))}  {disclosure}",
                        Key = item.ConversationId,
                    });
                }
                _conversation.SelectedIndex = 0;
                foreach (var value in ReasoningValues)
                    _reasoning.Items.Add(new ListItem { Text = value.Length == 0 ? "Prime default" : value, Key = value });
                _reasoning.SelectedIndex = 0;
                _conversation.SelectedValueChanged += (s, e) => UpdateCreationControls();

                var open = new Button { Text = "Open" };
                open.Click += (s, e) =>
                {
                    var result = BuildResult();
                    if (result != null) Close(result);
                };
                var cancel = new Button { Text = "Cancel" };
                cancel.Click += (s, e) => Close(null);
                Content = new TableLayout
                {
                    Spacing = new Size(6, 6),
                    Rows =
                    {
                        new TableRow(new Label { Text = "Conversation" }, _conversation),
                        new TableRow(new Label { Text = "Requested model" }, _model),
                        new TableRow(new Label { Text = "Reasoning" }, _reasoning),
                        new TableRow(null, open, cancel),
                    },
                };
                UpdateCreationControls();
            }

            private void UpdateCreationControls()
            {
                var creating = string.IsNullOrEmpty(_conversation.SelectedKey);
                _model.Enabled = creating;
                _reasoning.Enabled = creating;
            }

            private PrimeConversationDialogResult? BuildResult()
            {
                var reopen = _conversation.SelectedKey;
                if (!string.IsNullOrEmpty(reopen))
                    return new PrimeConversationDialogResult { ReopenConversationId = reopen };
                var model = _model.Text?.Trim();
                if (!string.IsNullOrEmpty(model) && !IsQualifiedRequestedModel(model))
                {
                    MessageBox.Show(this, "Use a fully qualified provider/model name.", "Prime Conversation");
                    return null;
                }
                return new PrimeConversationDialogResult
                {
                    RequestedModel = string.IsNullOrEmpty(model) ? null : model,
                    RequestedReasoning = string.IsNullOrEmpty(_reasoning.SelectedKey) ? null : _reasoning.SelectedKey,
                };
            }
        }
    }
}
