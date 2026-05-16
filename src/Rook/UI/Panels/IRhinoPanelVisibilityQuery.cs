using System;

namespace Rook.UI.Panels
{
    internal interface IRhinoPanelVisibilityQuery
    {
        bool IsSelectedPanelVisible(Type panelType);
    }
}
