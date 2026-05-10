using System;
using Rhino;
using Rhino.Commands;
using Rhino.UI;
using Rook.UI.Vision;

namespace Rook.Commands
{
    /// <summary>
    /// Command to open (or focus) the native Rook Vision panel.
    /// </summary>
    public class ShowRookVisionCommand : Command
    {
        public override string EnglishName => "ShowRookVision";

        internal static Guid TargetPanelId => RookVisionPanel.PanelId;

        protected override Result RunCommand(RhinoDoc doc, RunMode mode)
        {
            Panels.OpenPanel(TargetPanelId);
            return Result.Success;
        }
    }
}
