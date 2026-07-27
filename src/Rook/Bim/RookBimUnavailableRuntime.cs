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

        public BimStatusResponse Status(BimDiagnosticContext diagnostics)
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

        public BimApiResponse ActiveDocument(BimDiagnosticContext diagnostics)
        {
            return Unavailable();
        }

        public BimApiResponse ListCategories(BimDiagnosticContext diagnostics)
        {
            return Unavailable();
        }

        public BimApiResponse QueryElements(BimDiagnosticContext diagnostics, BimQueryElementsRequest request)
        {
            return Unavailable();
        }

        public BimApiResponse ElementInfo(BimDiagnosticContext diagnostics, BimElementRequest request)
        {
            return Unavailable();
        }

        public BimApiResponse ElementParameters(BimDiagnosticContext diagnostics, BimElementRequest request)
        {
            return Unavailable();
        }

        public BimApiResponse SelectElements(BimDiagnosticContext diagnostics, BimSelectElementsRequest request)
        {
            return Unavailable();
        }

        public BimApiResponse ClearSelection(BimDiagnosticContext diagnostics)
        {
            return Unavailable();
        }

        public BimApiResponse ExportElements(BimDiagnosticContext diagnostics, BimExportElementsRequest request)
        {
            return Unavailable();
        }

        public BimApiResponse ExportPreset(BimDiagnosticContext diagnostics, BimExportPresetRequest request)
        {
            return Unavailable();
        }

        public BimApiResponse CreationGuidProbe(
            BimDiagnosticContext diagnostics,
            BimCreationGuidProbeRequest request)
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
