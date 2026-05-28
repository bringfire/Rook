namespace Rook.Bim
{
    public interface IRookBimRuntime
    {
        BimStatusResponse Status();

        BimApiResponse ActiveDocument();

        BimApiResponse QueryElements(BimQueryElementsRequest request);

        BimApiResponse ElementInfo(BimElementRequest request);

        BimApiResponse ElementParameters(BimElementRequest request);

        BimApiResponse SelectElements(BimSelectElementsRequest request);

        BimApiResponse ClearSelection();
    }
}
