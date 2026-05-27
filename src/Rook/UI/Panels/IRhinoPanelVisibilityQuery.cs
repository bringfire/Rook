using System;

namespace Rook.UI.Panels
{
    internal interface IRhinoPanelVisibilityQuery
    {
        bool IsPanelVisibleAnyTab(Type panelType);
        bool IsSelectedPanelVisible(Type panelType);
    }
}
