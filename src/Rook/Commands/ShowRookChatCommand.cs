using Rhino;
using Rhino.Commands;
using Rhino.UI;
using Rook.UI.Chat;

namespace Rook.Commands
{
    /// <summary>
    /// Command to toggle the Rook Chat panel visibility.
    /// </summary>
    public class ShowRookChatCommand : Command
    {
        /// <summary>
        /// Gets the command name as it appears in Rhino.
        /// </summary>
        public override string EnglishName => "ShowRookChat";

        /// <summary>
        /// Executes the command to toggle the Rook Chat panel.
        /// </summary>
        protected override Result RunCommand(RhinoDoc doc, RunMode mode)
        {
            var panelId = RookChatPanel.PanelId;

            // Check visibility, not instance existence.  Rhino keeps panel
            // instances alive after close, so GetPanels returns non-empty
            // even when the panel is hidden.
            var openPanels = Panels.GetOpenPanelIds();
            var isVisible = false;
            foreach (var id in openPanels)
            {
                if (id == panelId) { isVisible = true; break; }
            }

            if (isVisible)
            {
                Panels.ClosePanel(panelId, doc);
                RhinoApp.WriteLine($"Rook Chat panel closed for document {doc.RuntimeSerialNumber}.");
            }
            else
            {
                Panels.OpenPanel(panelId);
                RhinoApp.WriteLine($"Rook Chat panel opened for document {doc.RuntimeSerialNumber}.");
            }

            return Result.Success;
        }
    }
}
