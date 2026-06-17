namespace Rook.Bim
{
    public sealed class RookBimUnavailableRuntime : IRookBimRuntime
    {
        private readonly string statusCode;
        private readonly string statusMessage;
        private readonly string module;

        public RookBimUnavailableRuntime(
            string statusCode,
            string statusMessage,
            string module = "core")
        {
            this.statusCode = statusCode;
            this.statusMessage = statusMessage;
            this.module = module;
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
                Module = module
            };
        }

        public BimApiResponse ActiveDocument()
        {
            return Unavailable();
        }

        public BimApiResponse ListCategories()
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

        public BimApiResponse ExportElements(BimExportElementsRequest request)
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
