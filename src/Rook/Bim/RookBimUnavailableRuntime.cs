namespace Rook.Bim
{
    public sealed class RookBimUnavailableRuntime : IRookBimRuntime
    {
        private readonly string statusCode;
        private readonly string statusMessage;

        public RookBimUnavailableRuntime(string statusCode, string statusMessage)
        {
            this.statusCode = statusCode;
            this.statusMessage = statusMessage;
        }

        public BimStatusResponse Status()
        {
            return new BimStatusResponse
            {
                Available = false,
                Runtime = "unavailable",
                ErrorCode = statusCode,
                Message = statusMessage,
                Host = "unknown",
                Module = "core"
            };
        }

        public BimApiResponse ActiveDocument()
        {
            return Unavailable();
        }

        public BimApiResponse QueryElements(BimQueryElementsRequest request)
        {
            return Unavailable();
        }

        public BimApiResponse ElementInfo(BimElementRequest request)
        {
            return Unavailable();
        }

        public BimApiResponse ElementParameters(BimElementRequest request)
        {
            return Unavailable();
        }

        public BimApiResponse SelectElements(BimSelectElementsRequest request)
        {
            return Unavailable();
        }

        public BimApiResponse ClearSelection()
        {
            return Unavailable();
        }

        private BimApiResponse Unavailable()
        {
            return BimApiResponse.Fail(
                BimErrorCode.RookBimUnavailable,
                statusMessage,
                503);
        }
    }
}
