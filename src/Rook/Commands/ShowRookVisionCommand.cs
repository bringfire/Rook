using Rhino;
using Rhino.Commands;
using Rhino.UI;
using Rook.UI.Chat;

namespace Rook.Commands
{
    /// <summary>
    /// Command to open (or focus) the Vision tab inside the Rook Chat
    /// panel. The Vision UI is a tab-within-a-panel rather than its own
    /// Rhino panel, so this command ensures the chat panel is visible
    /// first and then delegates to <c>RookChatPanel.OpenOrFocusVisionTab</c>
    /// on the doc-scoped panel instance. No-op if the chat panel cannot
    /// be resolved — the command never throws at the user.
    /// </summary>
    public class ShowRookVisionCommand : Command
    {
        public override string EnglishName => "ShowRookVision";

        protected override Result RunCommand(RhinoDoc doc, RunMode mode)
        {
            var panelId = RookChatPanel.PanelId;

            // Make the chat panel visible before locating the instance —
            // GetPanel<T> returns null for docs that have never shown the
            // panel, and the Vision tab has nowhere to live without it.
            var openPanels = Panels.GetOpenPanelIds();
            var alreadyVisible = false;
            foreach (var id in openPanels)
            {
                if (id == panelId) { alreadyVisible = true; break; }
            }

            if (!alreadyVisible)
            {
                Panels.OpenPanel(panelId);
            }

            var chatPanel = Panels.GetPanel<RookChatPanel>(doc);
            if (chatPanel == null)
            {
                RhinoApp.WriteLine(
                    "Rook: Vision tab cannot be opened — chat panel instance not available. " +
                    "Try running /ShowRookChat first, then retry.");
                return Result.Failure;
            }

            chatPanel.OpenOrFocusVisionTab();
            return Result.Success;
        }
    }
}
