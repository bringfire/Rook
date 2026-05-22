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

            if (IsRookChatPanelVisible())
            {
                Panels.ClosePanel(panelId, doc);
                RhinoApp.WriteLine($"Rook Chat panel closed for document {doc.RuntimeSerialNumber}.");
            }
            else
            {
                try
                {
                    Panels.OpenPanel(panelId);
                }
                catch (System.Exception ex)
                {
                    RhinoApp.WriteLine($"Rook Chat panel could not be shown: {ex.Message}");
                    return Result.Failure;
                }

                if (!IsRookChatPanelVisible())
                {
                    RhinoApp.WriteLine(
                        "Rook Chat panel could not be shown. " +
                        "The panel may not be registered or this host may not expose Rhino panels.");
                    return Result.Failure;
                }

                RhinoApp.WriteLine($"Rook Chat panel opened for document {doc.RuntimeSerialNumber}.");
            }

            return Result.Success;
        }

        private static bool IsRookChatPanelVisible()
        {
            var panelId = RookChatPanel.PanelId;

            // Check visibility, not instance existence. Rhino keeps panel
            // instances alive after close, so GetPanels can be non-empty even
            // when the panel is hidden.
            var openPanels = Panels.GetOpenPanelIds();
            foreach (var id in openPanels)
            {
                if (id == panelId)
                    return true;
            }

            try
            {
                return Panels.IsPanelVisible(typeof(RookChatPanel), isSelectedTab: true) ||
                       Panels.IsPanelVisible(typeof(RookChatPanel), isSelectedTab: false);
            }
            catch
            {
                return false;
            }
        }
    }
}
