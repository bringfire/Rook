using Rhino;
using Rhino.Commands;
using Rhino.UI;
using Rook.UI.Knowledge;

namespace Rook.Commands
{
    /// <summary>
    /// Command to toggle the Knowledge Graph panel visibility.
    /// </summary>
    public class ShowRookKnowledgeGraphCommand : Command
    {
        public override string EnglishName => "ShowRookKnowledgeGraph";

        protected override Result RunCommand(RhinoDoc doc, RunMode mode)
        {
            var panelId = KnowledgeGraphPanel.PanelId;

            var openPanels = Panels.GetOpenPanelIds();
            var isVisible = false;
            foreach (var id in openPanels)
            {
                if (id == panelId) { isVisible = true; break; }
            }

            if (isVisible)
            {
                Panels.ClosePanel(panelId, doc);
            }
            else
            {
                Panels.OpenPanel(panelId);
            }

            return Result.Success;
        }
    }
}
