namespace Rook.Bim
{
    public interface IRookBimRuntime
    {
        BimStatusResponse Status(BimDiagnosticContext diagnostics);

        BimApiResponse ActiveDocument(BimDiagnosticContext diagnostics);

        BimApiResponse ListCategories(BimDiagnosticContext diagnostics);

        BimApiResponse QueryElements(BimDiagnosticContext diagnostics, BimQueryElementsRequest request);

        BimApiResponse ElementInfo(BimDiagnosticContext diagnostics, BimElementRequest request);

        BimApiResponse ElementParameters(BimDiagnosticContext diagnostics, BimElementRequest request);

        BimApiResponse SelectElements(BimDiagnosticContext diagnostics, BimSelectElementsRequest request);

        BimApiResponse ClearSelection(BimDiagnosticContext diagnostics);

        BimApiResponse ExportElements(BimDiagnosticContext diagnostics, BimExportElementsRequest request);

        BimApiResponse ExportPreset(BimDiagnosticContext diagnostics, BimExportPresetRequest request);
    }
}
