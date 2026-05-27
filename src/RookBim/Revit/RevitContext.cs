using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace RookBim.Revit
{
    public static class RevitContext
    {
        public static UIDocument? ActiveUiDocument(UIApplication uiapp)
        {
            return uiapp?.ActiveUIDocument;
        }

        public static Document? ActiveDocument(UIApplication uiapp)
        {
            return ActiveUiDocument(uiapp)?.Document;
        }
    }
}
