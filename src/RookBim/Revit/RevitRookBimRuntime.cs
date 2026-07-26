using System;
using System.Linq;
using System.Threading.Tasks;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Rook.Bim;

namespace RookBim.Revit
{
    public sealed class RevitRookBimRuntime : IRookBimRuntime
    {
        private const string ModuleName = "RookBim.dll";
        private static readonly TimeSpan DispatchTimeout = TimeSpan.FromSeconds(5);
        private static readonly TimeSpan ExportDispatchTimeout = TimeSpan.FromSeconds(120);
        private readonly RevitApiDispatcher dispatcher;
        private readonly RevitCategoryResolver categories;
        private readonly RevitQueryService query;
        private readonly RevitSelectionService selection;
        private readonly RevitExportService export;
        private readonly RevitPresetResolver presetResolver;

        public RevitRookBimRuntime()
            : this(new RevitApiDispatcher())
        {
        }

        internal RevitRookBimRuntime(RevitApiDispatcher dispatcher)
        {
            this.dispatcher = dispatcher ?? throw new ArgumentNullException(nameof(dispatcher));
            this.categories = new RevitCategoryResolver();
            this.query = new RevitQueryService();
            this.selection = new RevitSelectionService();
            this.export = new RevitExportService();
            this.presetResolver = new RevitPresetResolver();
        }

        public BimStatusResponse Status(BimDiagnosticContext diagnostics)
        {
            try
            {
                var hasActiveDocument = Dispatch(uiapp => RevitContext.ActiveDocument(uiapp) != null);
                if (!hasActiveDocument)
                {
                    return new BimStatusResponse
                    {
                        Available = false,
                        Runtime = "rookbim",
                        ErrorCode = "no_active_document",
                        Message = "RookBIM is connected to Revit, but no active document is open.",
                        Host = "revit",
                        Module = ModuleName
                    };
                }

                return new BimStatusResponse
                {
                    Available = true,
                    Runtime = "rookbim",
                    Host = "revit",
                    Module = ModuleName
                };
            }
            catch (Exception ex)
            {
                return new BimStatusResponse
                {
                    Available = false,
                    Runtime = "rookbim",
                    ErrorCode = "not_rhino_inside",
                    Message = $"RookBIM could not enter the Revit API context: {DescribeDispatchException(ex)}",
                    Host = "unknown",
                    Module = ModuleName
                };
            }
        }

        public BimApiResponse ActiveDocument(BimDiagnosticContext diagnostics)
        {
            return ExecuteInDocumentContext(
                "active_document",
                (uidoc, document) =>
                {
                    return BimApiResponse.Ok(new ActiveDocumentResult
                    {
                        Document = RevitIdentitySerializer.DocumentIdentity(document),
                        View = SerializeActiveView(uidoc)
                    });
                });
        }

        public BimApiResponse QueryElements(BimDiagnosticContext diagnostics, BimQueryElementsRequest request)
        {
            return ExecuteInDocumentContext(
                "query_elements",
                (uidoc, document) =>
                {
                    var view = ResolveActiveGraphicalView(uidoc, request.EffectiveScope);
                    return query.Query(document, view, request);
                });
        }

        public BimApiResponse ListCategories(BimDiagnosticContext diagnostics)
        {
            return ExecuteInDocumentContext(
                "list_categories",
                (_uidoc, document) => BimApiResponse.Ok(categories.List(document)));
        }

        public BimApiResponse ElementInfo(BimDiagnosticContext diagnostics, BimElementRequest request)
        {
            try
            {
                return Dispatch(uiapp =>
                {
                    var uidoc = RevitContext.ActiveUiDocument(uiapp);
                    if (uidoc == null || uidoc.Document == null)
                    {
                        return BimApiResponse.Fail(
                            BimErrorCode.NoActiveDocument,
                            "No active Revit document is open.",
                            409);
                    }

                    var document = uidoc.Document;
                    var resolved = ResolveElementOrFailure(document, request?.Identity);
                    if (!resolved.Success)
                    {
                        return BimApiResponse.Fail(
                            resolved.ErrorCode,
                            resolved.Message ?? "Element identity did not resolve in the active Revit document.",
                            ResolveHttpStatus(resolved.ErrorCode));
                    }

                    return BimApiResponse.Ok(BuildElementInfo(document, resolved.Element!));
                });
            }
            catch (Exception ex)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NotRhinoInside,
                    $"RookBIM could not enter the Revit API context: {DescribeDispatchException(ex)}",
                    503);
            }
        }

        public BimApiResponse ElementParameters(BimDiagnosticContext diagnostics, BimElementRequest request)
        {
            try
            {
                return Dispatch(uiapp =>
                {
                    var uidoc = RevitContext.ActiveUiDocument(uiapp);
                    if (uidoc == null || uidoc.Document == null)
                    {
                        return BimApiResponse.Fail(
                            BimErrorCode.NoActiveDocument,
                            "No active Revit document is open.",
                            409);
                    }

                    var document = uidoc.Document;
                    var resolved = ResolveElementOrFailure(document, request?.Identity);
                    if (!resolved.Success)
                    {
                        return BimApiResponse.Fail(
                            resolved.ErrorCode,
                            resolved.Message ?? "Element identity did not resolve in the active Revit document.",
                            ResolveHttpStatus(resolved.ErrorCode));
                    }

                    return BimApiResponse.Ok(new
                    {
                        identity = RevitIdentitySerializer.ElementIdentity(resolved.Element!),
                        parameters = RevitParameterSerializer.Serialize(resolved.Element!)
                    });
                });
            }
            catch (Exception ex)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NotRhinoInside,
                    $"RookBIM could not enter the Revit API context: {DescribeDispatchException(ex)}",
                    503);
            }
        }

        public BimApiResponse SelectElements(BimDiagnosticContext diagnostics, BimSelectElementsRequest request)
        {
            try
            {
                return Dispatch(uiapp =>
                {
                    var uidoc = RevitContext.ActiveUiDocument(uiapp);
                    if (uidoc == null || uidoc.Document == null)
                    {
                        return BimApiResponse.Fail(
                            BimErrorCode.NoActiveDocument,
                            "No active Revit document is open.",
                            409);
                    }

                    return selection.Select(uidoc, request);
                });
            }
            catch (Exception ex)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NotRhinoInside,
                    $"RookBIM could not enter the Revit API context: {DescribeDispatchException(ex)}",
                    503);
            }
        }

        public BimApiResponse ClearSelection(BimDiagnosticContext diagnostics)
        {
            try
            {
                return Dispatch(uiapp =>
                {
                    var uidoc = RevitContext.ActiveUiDocument(uiapp);
                    if (uidoc == null || uidoc.Document == null)
                    {
                        return BimApiResponse.Fail(
                            BimErrorCode.NoActiveDocument,
                            "No active Revit document is open.",
                            409);
                    }

                    return selection.Clear(uidoc);
                });
            }
            catch (Exception ex)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NotRhinoInside,
                    $"RookBIM could not enter the Revit API context: {DescribeDispatchException(ex)}",
                    503);
            }
        }

        public BimApiResponse ExportPreset(BimDiagnosticContext diagnostics, BimExportPresetRequest request)
        {
            if (request == null)
            {
                return BimApiResponse.Fail(BimErrorCode.InvalidScope, "export-preset request is required.", 400);
            }

            var validation = request.Validate();
            if (!validation.Success)
            {
                return BimApiResponse.Fail(
                    validation.ErrorCode, validation.Message ?? "export-preset validation failed.", 400);
            }

            try
            {
                return DispatchWithTimeout(uiapp =>
                {
                    var uidoc = RevitContext.ActiveUiDocument(uiapp);
                    if (uidoc == null || uidoc.Document == null)
                    {
                        return BimApiResponse.Fail(BimErrorCode.NoActiveDocument, "No active Revit document is open.", 409);
                    }

                    var document = uidoc.Document;
                    try
                    {
                        var view = ResolveActiveGraphicalView(uidoc, request.EffectiveScope);
                        var resolution = presetResolver.Resolve(document, view, request);
                        if (resolution.Failure != null)
                        {
                            return resolution.Failure;
                        }

                        // Build the inner export request that the resolved core consumes (identities path
                        // semantics; rooms come from the resolved preset context).
                        var innerRequest = new BimExportElementsRequest
                        {
                            Output = request.Output,
                            Rooms = resolution.Context.EffectiveRooms,
                            AllowTruncated = request.AllowTruncated,
                            AllowBboxProxy = request.AllowBboxProxy,
                        };

                        return export.ExportResolved(
                            document,
                            resolution.Elements,
                            resolution.Truncated,
                            resolution.RequestedCount,
                            innerRequest,
                            resolution.Context.Policy,
                            resolution.Context);
                    }
                    catch (Exception ex)
                    {
                        return BimApiResponse.Fail(
                            BimErrorCode.ExportFailed,
                            $"RookBIM preset export failed inside the Revit document context: {DescribeDispatchException(ex)}",
                            500);
                    }
                }, ExportDispatchTimeout);
            }
            catch (Exception ex)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NotRhinoInside,
                    $"RookBIM could not enter the Revit API context: {DescribeDispatchException(ex)}",
                    503);
            }
        }

        public BimApiResponse ExportElements(BimDiagnosticContext diagnostics, BimExportElementsRequest request)
        {
            if (request == null)
            {
                return BimApiResponse.Fail(BimErrorCode.InvalidScope, "export-elements request is required.", 400);
            }

            var validation = request.Validate();
            if (!validation.Success)
            {
                return BimApiResponse.Fail(
                    validation.ErrorCode, validation.Message ?? "export-elements validation failed.", 400);
            }

            try
            {
                return DispatchWithTimeout(uiapp =>
                {
                    var uidoc = RevitContext.ActiveUiDocument(uiapp);
                    if (uidoc == null || uidoc.Document == null)
                    {
                        return BimApiResponse.Fail(BimErrorCode.NoActiveDocument, "No active Revit document is open.", 409);
                    }

                    var document = uidoc.Document;
                    try
                    {
                        var view = request.HasSelector
                            ? ResolveActiveGraphicalView(uidoc, request.Selector!.EffectiveScope)
                            : null;
                        return export.Export(document, view, request);
                    }
                    catch (Exception ex)
                    {
                        return BimApiResponse.Fail(
                            BimErrorCode.ExportFailed,
                            $"RookBIM export failed inside the Revit document context: {DescribeDispatchException(ex)}",
                            500);
                    }
                }, ExportDispatchTimeout);
            }
            catch (Exception ex)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NotRhinoInside,
                    $"RookBIM could not enter the Revit API context: {DescribeDispatchException(ex)}",
                    503);
            }
        }

        private T Dispatch<T>(Func<UIApplication, T> work)
        {
            var dispatch = dispatcher.InvokeAbandonable(work);
            if (Task.WaitAny(new Task[] { dispatch.Task }, DispatchTimeout) < 0)
            {
                dispatch.Abandon();
                throw new TimeoutException("Timed out waiting for RhinoInside Revit idling-queue execution.");
            }

            return dispatch.Task.GetAwaiter().GetResult();
        }

        private T DispatchWithTimeout<T>(Func<UIApplication, T> work, TimeSpan timeout)
        {
            var dispatch = dispatcher.InvokeAbandonable(work);
            if (Task.WaitAny(new Task[] { dispatch.Task }, timeout) < 0)
            {
                dispatch.Abandon();
                throw new TimeoutException("Timed out waiting for RhinoInside Revit idling-queue execution.");
            }

            return dispatch.Task.GetAwaiter().GetResult();
        }

        private BimApiResponse ExecuteInDocumentContext(
            string operation,
            Func<UIDocument, Document, BimApiResponse> work)
        {
            try
            {
                return Dispatch(uiapp =>
                {
                    var uidoc = RevitContext.ActiveUiDocument(uiapp);
                    if (uidoc == null || uidoc.Document == null)
                    {
                        return BimApiResponse.Fail(
                            BimErrorCode.NoActiveDocument,
                            "No active Revit document is open.",
                            409);
                    }

                    try
                    {
                        return work(uidoc, uidoc.Document);
                    }
                    catch (Exception ex)
                    {
                        var response = BimApiResponse.Fail(
                            BimErrorCode.InternalError,
                            $"RookBIM operation '{operation}' failed inside the active Revit document context: {DescribeDispatchException(ex)}",
                            500);
                        response.Data = new
                        {
                            operation = operation,
                            exception = DescribeDispatchException(ex)
                        };
                        return response;
                    }
                });
            }
            catch (Exception ex)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NotRhinoInside,
                    $"RookBIM could not enter the Revit API context: {DescribeDispatchException(ex)}",
                    503);
            }
        }

        private static string DescribeDispatchException(Exception ex)
        {
            var root = ex is AggregateException aggregate
                ? aggregate.Flatten().InnerExceptions.FirstOrDefault() ?? ex
                : ex;
            return $"{root.GetType().Name}: {root.Message}";
        }

        private static View? ResolveActiveGraphicalView(UIDocument uidoc, BimQueryScope scope)
        {
            return scope == BimQueryScope.ActiveView
                ? uidoc.ActiveGraphicalView
                : null;
        }

        private static BimViewIdentity? SerializeActiveView(UIDocument uidoc)
        {
            var view = ResolveActiveGraphicalView(uidoc, BimQueryScope.ActiveView);
            return view == null ? null : RevitIdentitySerializer.ViewIdentity(view);
        }

        private static BimElementResolveResult ResolveElementOrFailure(
            Document document,
            BimElementIdentity? identity)
        {
            return RevitIdentitySerializer.Resolve(document, identity);
        }

        private static object BuildElementInfo(Document document, Element element)
        {
            return new
            {
                identity = RevitIdentitySerializer.ElementIdentity(element),
                name = NullIfWhiteSpace(element.Name),
                category = new BimCategorySummary
                {
                    Id = ToInt32OrNull(element.Category?.Id),
                    Name = NullIfWhiteSpace(element.Category?.Name)
                },
                type = BuildElementTypeSummary(document, element),
                className = element.GetType().Name,
                location = element.Location?.GetType().Name
            };
        }

        private static BimElementTypeSummary BuildElementTypeSummary(Document document, Element element)
        {
            var typeId = element.GetTypeId();
            var type = typeId == ElementId.InvalidElementId ? null : document.GetElement(typeId);
            if (type == null)
            {
                return new BimElementTypeSummary();
            }

            return new BimElementTypeSummary
            {
                Id = ToInt32OrNull(type.Id),
                UniqueId = NullIfWhiteSpace(type.UniqueId),
                FamilyName = NullIfWhiteSpace(
                    type.get_Parameter(BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)?.AsString()),
                Name = NullIfWhiteSpace(type.Name)
            };
        }

        private static int ResolveHttpStatus(BimErrorCode code)
        {
            switch (code)
            {
                case BimErrorCode.DocumentMismatch:
                case BimErrorCode.LinkedElementUnsupported:
                    return 409;
                case BimErrorCode.ElementNotFound:
                    return 404;
                default:
                    return 400;
            }
        }

        private static string? NullIfWhiteSpace(string? value)
        {
            return string.IsNullOrWhiteSpace(value) ? null : value;
        }

        private static int? ToInt32OrNull(ElementId? id)
        {
            if (id == null)
            {
                return null;
            }

            var value = id.Value;
            if (value < int.MinValue || value > int.MaxValue)
            {
                return null;
            }

            return (int)value;
        }

        private sealed class ActiveDocumentResult
        {
            public BimDocumentIdentity Document { get; set; } = new BimDocumentIdentity();

            public BimViewIdentity? View { get; set; }
        }
    }
}
