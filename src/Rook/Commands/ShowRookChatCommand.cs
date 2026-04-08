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
            var documentPanels = Panels.GetPanels(panelId, doc);
            var hasDocumentPanel = documentPanels != null && documentPanels.Length > 0;

            if (hasDocumentPanel)
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
