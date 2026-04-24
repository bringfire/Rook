using System;
using Eto.Forms;
using Rook.UI.Web;

namespace Rook.UI.Vision
{
    /// <summary>
    /// Pattern A Vision tab, hosted as a bare Eto <see cref="Panel"/> in
    /// the Rook chat panel's tab strip. Deliberately NOT a
    /// <c>ChatTab</c> — there is no shared chat lifecycle, no
    /// Send/Stop/Clear controls, no streaming assistant message pipe.
    /// The entire UI is HTML/JS inside a <see cref="VisionWebSurface"/>;
    /// the panel's only Eto responsibility is to own the WebView control
    /// and the disposal hook.
    ///
    /// Added to the tab strip via
    /// <c>RookChatPanel.AddPanelTab("Vision", tab, tab.OnTabClosed)</c>.
    /// The <see cref="OnTabClosed"/> callback fires exactly once —
    /// either when the user closes the tab via its context menu or when
    /// the owning panel disposes.
    /// </summary>
    public sealed class VisionTab : Panel
    {
        private readonly VisionWebSurface _surface;
        private bool _closed;

        public VisionTab() : this(new VisionWebSurface()) { }

        internal VisionTab(VisionWebSurface surface)
        {
            _surface = surface ?? throw new ArgumentNullException(nameof(surface));
            // Use the WebView directly as the tab content. Wrapping in
            // TableLayout caused the WebView to lose its content on
            // Rhino panel redraw in the Knowledge Graph shakedown (#5);
            // the same hazard applies here — keep the tree shallow.
            Content = _surface.CreateWebContent();
        }

        /// <summary>
        /// Cleanup callback passed to <c>RookChatPanel.AddPanelTab</c>.
        /// Fires exactly once thanks to
        /// <c>TabCleanupRegistry</c>'s fire-once invariant on the owning
        /// panel. Safe to call multiple times defensively.
        /// </summary>
        public void OnTabClosed()
        {
            if (_closed) return;
            _closed = true;
            Content = null;
            _surface.Dispose();
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                OnTabClosed();
            }
            base.Dispose(disposing);
        }
    }
}
