using Rook.Bim;

namespace RookBim.Revit
{
    public sealed class RevitRookBimRuntime : IRookBimRuntime
    {
        private readonly IRookBimRuntime fallback = new RookBimUnavailableRuntime(
            "not_rhino_inside",
            "RookBIM is loaded, but Rhino is not running inside Revit.");

        public BimStatusResponse Status()
        {
            return fallback.Status();
        }

        public BimApiResponse ActiveDocument()
        {
            return fallback.ActiveDocument();
        }

        public BimApiResponse QueryElements(BimQueryElementsRequest request)
        {
            return fallback.QueryElements(request);
        }

        public BimApiResponse ElementInfo(BimElementRequest request)
        {
            return fallback.ElementInfo(request);
        }

        public BimApiResponse ElementParameters(BimElementRequest request)
        {
            return fallback.ElementParameters(request);
        }

        public BimApiResponse SelectElements(BimSelectElementsRequest request)
        {
            return fallback.SelectElements(request);
        }

        public BimApiResponse ClearSelection()
        {
            return fallback.ClearSelection();
        }
    }
}
