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
                var hasActiveDocument = Dispatch(
                    diagnostics,
                    uiapp =>
                    {
                        var document = AcquireActiveDocument(uiapp, diagnostics);
                        if (document == null)
                        {
                            return false;
                        }

                        RevitDocumentIdentityResolver.Capture(document, diagnostics);
                        return true;
                    });
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
                diagnostics,
                "active_document",
                (uidoc, document, evidence) =>
                {
                    return BimApiResponse.Ok(new ActiveDocumentResult
                    {
                        Document = RevitDocumentIdentityResolver.ProjectDocument(evidence),
                        View = SerializeActiveView(uidoc, diagnostics)
                    });
                });
        }

        public BimApiResponse QueryElements(BimDiagnosticContext diagnostics, BimQueryElementsRequest request)
        {
            var effectiveRequest = request ?? new BimQueryElementsRequest();
            return ExecuteInDocumentContext(
                diagnostics,
                "query_elements",
                (uidoc, document, evidence) =>
                {
                    var view = ResolveActiveGraphicalView(
                        uidoc, effectiveRequest.EffectiveScope, diagnostics);
                    return query.Execute(
                        document,
                        view,
                        effectiveRequest,
                        evidence,
                        diagnostics).Response;
                });
        }

        public BimApiResponse ListCategories(BimDiagnosticContext diagnostics)
        {
            return ExecuteInDocumentContext(
                diagnostics,
                "list_categories",
                (_uidoc, document, evidence) =>
                    BimApiResponse.Ok(categories.List(document, evidence, diagnostics)));
        }

        public BimApiResponse ElementInfo(BimDiagnosticContext diagnostics, BimElementRequest request)
        {
            return ExecuteInDocumentContext(
                diagnostics,
                "element_info",
                (_uidoc, document, evidence) =>
                {
                    var resolved = ResolveElementOrFailure(
                        evidence,
                        request?.Identity,
                        diagnostics);
                    if (!resolved.Success)
                    {
                        return BimApiResponse.Fail(
                            resolved.ErrorCode,
                            resolved.Message ?? "Element identity did not resolve in the active Revit document.",
                            RevitDocumentIdentityResolver.HttpStatusFor(resolved.ErrorCode));
                    }

                    return BimApiResponse.Ok(
                        BuildElementInfo(document, evidence, resolved.Element!));
                });
        }

        public BimApiResponse ElementParameters(BimDiagnosticContext diagnostics, BimElementRequest request)
        {
            return ExecuteInDocumentContext(
                diagnostics,
                "element_parameters",
                (_uidoc, _document, evidence) =>
                {
                    var resolved = ResolveElementOrFailure(
                        evidence,
                        request?.Identity,
                        diagnostics);
                    if (!resolved.Success)
                    {
                        return BimApiResponse.Fail(
                            resolved.ErrorCode,
                            resolved.Message ?? "Element identity did not resolve in the active Revit document.",
                            RevitDocumentIdentityResolver.HttpStatusFor(resolved.ErrorCode));
                    }

                    return BimApiResponse.Ok(new
                    {
                        identity = RevitDocumentIdentityResolver.ProjectElement(
                            evidence,
                            resolved.Element!),
                        parameters = RevitParameterSerializer.Serialize(resolved.Element!)
                    });
                });
        }

        public BimApiResponse SelectElements(BimDiagnosticContext diagnostics, BimSelectElementsRequest request)
        {
            return ExecuteInDocumentContext(
                diagnostics,
                "select_elements",
                (uidoc, _document, evidence) =>
                    selection.Select(uidoc, evidence, request, diagnostics));
        }

        public BimApiResponse ClearSelection(BimDiagnosticContext diagnostics)
        {
            return ExecuteInDocumentContext(
                diagnostics,
                "clear_selection",
                (uidoc, _document, evidence) => selection.Clear(uidoc, evidence));
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

            return ExecuteInDocumentContext(
                diagnostics,
                "export_preset",
                (uidoc, document, evidence) =>
                {
                    try
                    {
                        var view = ResolveActiveGraphicalView(
                            uidoc, request.EffectiveScope, diagnostics);
                        var resolution = presetResolver.Resolve(
                            document,
                            view,
                            request,
                            evidence,
                            diagnostics);
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
                            evidence,
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
                },
                ExportDispatchTimeout);
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

            return ExecuteInDocumentContext(
                diagnostics,
                "export_elements",
                (uidoc, document, evidence) =>
                {
                    try
                    {
                        var view = request.HasSelector
                            ? ResolveActiveGraphicalView(
                                uidoc, request.Selector!.EffectiveScope, diagnostics)
                            : null;
                        return export.Export(
                            document,
                            view,
                            request,
                            evidence,
                            diagnostics);
                    }
                    catch (Exception ex)
                    {
                        return BimApiResponse.Fail(
                            BimErrorCode.ExportFailed,
                            $"RookBIM export failed inside the Revit document context: {DescribeDispatchException(ex)}",
                            500);
                    }
                },
                ExportDispatchTimeout);
        }

        private T Dispatch<T>(
            BimDiagnosticContext diagnostics,
            Func<UIApplication, T> work)
        {
            var capturedDiagnostics = diagnostics;
            var dispatch = dispatcher.InvokeAbandonable(capturedDiagnostics, work);
            if (Task.WaitAny(new Task[] { dispatch.Task }, DispatchTimeout) < 0)
            {
                dispatch.Abandon();
                throw new TimeoutException("Timed out waiting for RhinoInside Revit idling-queue execution.");
            }

            return dispatch.Task.GetAwaiter().GetResult();
        }

        private T DispatchWithTimeout<T>(
            BimDiagnosticContext diagnostics,
            Func<UIApplication, T> work,
            TimeSpan timeout)
        {
            var capturedDiagnostics = diagnostics;
            var dispatch = dispatcher.InvokeAbandonable(capturedDiagnostics, work);
            if (Task.WaitAny(new Task[] { dispatch.Task }, timeout) < 0)
            {
                dispatch.Abandon();
                throw new TimeoutException("Timed out waiting for RhinoInside Revit idling-queue execution.");
            }

            return dispatch.Task.GetAwaiter().GetResult();
        }

        private BimApiResponse ExecuteInDocumentContext(
            BimDiagnosticContext diagnostics,
            string operation,
            Func<UIDocument, Document, RevitDocumentIdentityEvidence, BimApiResponse> work,
            TimeSpan? timeout = null)
        {
            try
            {
                Func<UIApplication, BimApiResponse> callback = uiapp =>
                {
                    var uidoc = AcquireActiveUiDocument(uiapp, diagnostics);
                    var document = uidoc == null
                        ? null
                        : AcquireDocument(uidoc, diagnostics);
                    if (uidoc == null || document == null)
                    {
                        return BimApiResponse.Fail(
                            BimErrorCode.NoActiveDocument,
                            "No active Revit document is open.",
                            409);
                    }

                    var evidence = RevitDocumentIdentityResolver.Capture(
                        document,
                        diagnostics);
                    try
                    {
                        return work(uidoc, document, evidence);
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
                };

                return timeout.HasValue
                    ? DispatchWithTimeout(diagnostics, callback, timeout.Value)
                    : Dispatch(diagnostics, callback);
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

        private static View? ResolveActiveGraphicalView(
            UIDocument uidoc,
            BimQueryScope scope,
            BimDiagnosticContext diagnostics)
        {
            if (scope != BimQueryScope.ActiveView)
            {
                return null;
            }

            return diagnostics.Enabled
                ? BimDiagnosticProbe.Production(
                    diagnostics,
                    BimDiagnosticStage.RevitViewActiveGraphical,
                    () => uidoc.ActiveGraphicalView,
                    BimDiagnosticFields.None,
                    view => view == null
                        ? BimDiagnosticDetailCode.NoActiveView
                        : BimDiagnosticDetailCode.True)
                : uidoc.ActiveGraphicalView;
        }

        private static BimViewIdentity? SerializeActiveView(
            UIDocument uidoc,
            BimDiagnosticContext diagnostics)
        {
            var view = ResolveActiveGraphicalView(
                uidoc, BimQueryScope.ActiveView, diagnostics);
            return view == null ? null : RevitViewIdentitySerializer.ViewIdentity(view);
        }

        private static UIDocument? AcquireActiveUiDocument(
            UIApplication uiapp,
            BimDiagnosticContext diagnostics)
        {
            return diagnostics.Enabled
                ? BimDiagnosticProbe.Production(
                    diagnostics,
                    BimDiagnosticStage.RevitDocumentAcquire,
                    () => RevitContext.ActiveUiDocument(uiapp),
                    BimDiagnosticFields.None,
                    value => value == null
                        ? BimDiagnosticDetailCode.Null
                        : BimDiagnosticDetailCode.True)
                : RevitContext.ActiveUiDocument(uiapp);
        }

        private static Document? AcquireDocument(
            UIDocument uidoc,
            BimDiagnosticContext diagnostics)
        {
            return diagnostics.Enabled
                ? BimDiagnosticProbe.Production(
                    diagnostics,
                    BimDiagnosticStage.RevitDocumentAcquire,
                    () => uidoc.Document,
                    BimDiagnosticFields.None,
                    value => value == null
                        ? BimDiagnosticDetailCode.Null
                        : BimDiagnosticDetailCode.True)
                : uidoc.Document;
        }

        private static Document? AcquireActiveDocument(
            UIApplication uiapp,
            BimDiagnosticContext diagnostics)
        {
            return diagnostics.Enabled
                ? BimDiagnosticProbe.Production(
                    diagnostics,
                    BimDiagnosticStage.RevitDocumentAcquire,
                    () => RevitContext.ActiveDocument(uiapp),
                    BimDiagnosticFields.None,
                    value => value == null
                        ? BimDiagnosticDetailCode.Null
                        : BimDiagnosticDetailCode.True)
                : RevitContext.ActiveDocument(uiapp);
        }

        private static BimElementResolveResult ResolveElementOrFailure(
            RevitDocumentIdentityEvidence evidence,
            BimElementIdentity? identity,
            BimDiagnosticContext diagnostics)
        {
            var preflight = RevitDocumentIdentityResolver.PreflightBatch(
                evidence,
                new BimElementIdentity?[] { identity },
                diagnostics);
            return preflight.Success
                ? RevitDocumentIdentityResolver.ResolveAfterPreflight(evidence, identity!)
                : preflight;
        }

        private static object BuildElementInfo(
            Document document,
            RevitDocumentIdentityEvidence evidence,
            Element element)
        {
            return new
            {
                identity = RevitDocumentIdentityResolver.ProjectElement(evidence, element),
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
