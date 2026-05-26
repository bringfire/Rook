using System;
using Rhino.UI;

namespace Rook.UI.Panels
{
    internal sealed class RhinoPanelVisibilityQuery : IRhinoPanelVisibilityQuery
    {
        public bool IsPanelVisibleAnyTab(Type panelType)
        {
            return Rhino.UI.Panels.IsPanelVisible(panelType, isSelectedTab: false);
        }

        public bool IsSelectedPanelVisible(Type panelType)
        {
            return Rhino.UI.Panels.IsPanelVisible(panelType, isSelectedTab: true);
        }
    }
}
