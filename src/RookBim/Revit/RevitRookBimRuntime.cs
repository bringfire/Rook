using System;
using System.Collections.Generic;
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
        // run_transaction waits in two phases so a blocked Revit is reported
        // quickly instead of after the whole script budget.
        // How long any queued work may wait for Revit's idle queue to pick it
        // up. A queue that does not move this long is blocked (a dialog or an
        // active command), whatever the work's own time budget is.
        private static readonly TimeSpan QueuePickupTimeout = TimeSpan.FromSeconds(10);
        // Between pickup and the script being entered: document checks and
        // starting the transaction.
        private static readonly TimeSpan TransactionSetupTimeout = TimeSpan.FromSeconds(4);
        // Between the script's budget ending and the host thread saying so.
        private static readonly TimeSpan ScriptReturnAllowance = TimeSpan.FromSeconds(1);
        private static readonly TimeSpan TransactionCommitGrace = TimeSpan.FromSeconds(8);
        private readonly RevitApiDispatcher dispatcher;
        private readonly RevitCategoryResolver categories;
        private readonly RevitQueryService query;
        private readonly RevitSelectionService selection;
        private readonly RevitExportService export;
        private readonly RevitPresetResolver presetResolver;
        private readonly RevitTransactionService transactions;

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
            this.transactions = new RevitTransactionService();
        }

        public BimStatusResponse Status(BimDiagnosticContext diagnostics)
        {
            try
            {
                string? failureInsideRevit = null;
                var hasActiveDocument = Dispatch(
                    diagnostics,
                    uiapp =>
                    {
                        try
                        {
                            var document = AcquireActiveDocument(uiapp, diagnostics);
                            if (document == null)
                            {
                                return false;
                            }

                            RevitDocumentIdentityResolver.Capture(document, diagnostics);
                            return true;
                        }
                        catch (Exception ex)
                        {
                            // Revit ran this callback, so the host is present.
                            failureInsideRevit = DescribeDispatchException(ex);
                            return false;
                        }
                    });
                if (failureInsideRevit != null)
                {
                    return new BimStatusResponse
                    {
                        Available = false,
                        Runtime = "rookbim",
                        ErrorCode = "internal_error",
                        Message = "RookBIM reached Revit, but reading the active document failed: " +
                            failureInsideRevit,
                        Host = "revit",
                        Module = ModuleName
                    };
                }

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
            catch (RevitDispatchTimeoutException ex)
            {
                // RhinoInside.Revit is loaded and accepted the work; Revit just
                // never ran it. That is not a missing host.
                return new BimStatusResponse
                {
                    Available = false,
                    Runtime = "rookbim",
                    ErrorCode = ex.WorkStarted ? "revit_operation_timeout" : "revit_not_idle",
                    Message = DescribeDispatchTimeout(ex, "status"),
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

        public BimApiResponse RunTransaction(BimDiagnosticContext diagnostics, BimRunTransactionRequest request)
        {
            if (request == null)
            {
                return BimApiResponse.Fail(BimErrorCode.InvalidRequest, "run-transaction request is required.", 400);
            }

            var validation = request.Validate();
            if (!validation.Success)
            {
                return BimApiResponse.Fail(
                    validation.ErrorCode, validation.Message ?? "run-transaction validation failed.", 400);
            }

            // The receipt exists before anything is queued, so every way this
            // call can end is reported from the same record.
            var call = BimTransactionCall.Begin(
                request.EffectiveName,
                TimeSpan.FromSeconds(request.EffectiveTimeoutSeconds));
            var response = ExecuteInDocumentContext(
                diagnostics,
                "run_transaction",
                (uidoc, document, evidence) =>
                    transactions.Run(uidoc, document, evidence, request, call),
                null,
                call);

            // A refusal issued before the executor ran (no active document,
            // Revit not idle, host missing) never reached the receipt. Record
            // it, and answer from the receipt like every other outcome, so the
            // caller gets the transaction id and a lookup does not read as
            // "still queued".
            if (!response.Success && call.Receipt.Snapshot().IsQueued)
            {
                call.Receipt.Refuse(response.ErrorCode, response.Message ?? "The write was refused.");
                call.Receipt.EndObservation();
                return BimTransactionReport.Build(
                    call.Receipt.Snapshot(),
                    new Dictionary<string, object?> { ["dispatch"] = response.Data });
            }

            return response;
        }

        private T Dispatch<T>(
            BimDiagnosticContext diagnostics,
            Func<UIApplication, T> work)
        {
            var capturedDiagnostics = diagnostics;
            var dispatch = dispatcher.InvokeAbandonable(capturedDiagnostics, work);
            if (Task.WaitAny(new Task[] { dispatch.Task }, DispatchTimeout) < 0)
            {
                // Abandon() succeeds only while the work is still queued, so its
                // answer says whether Revit ever became idle.
                var neverStarted = dispatch.Abandon();
                throw new RevitDispatchTimeoutException(!neverStarted, DispatchTimeout);
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
            // Phase 1: the queue. However long the work may take, a queue that
            // does not pick it up within QueuePickupTimeout is blocked, and the
            // caller should hear that now, not after the whole work budget.
            var pickup = timeout < QueuePickupTimeout ? timeout : QueuePickupTimeout;
            var waited = System.Diagnostics.Stopwatch.StartNew();
            var first = Task.WaitAny(new Task[] { dispatch.Task, dispatch.Started }, pickup);
            if (first == 0)
            {
                return dispatch.Task.GetAwaiter().GetResult();
            }

            if (first < 0 && dispatch.Abandon())
            {
                throw new RevitDispatchTimeoutException(false, pickup);
            }

            // Phase 2: the work is running; it gets the rest of its budget.
            var remaining = timeout - waited.Elapsed;
            if (remaining < TimeSpan.Zero)
            {
                remaining = TimeSpan.Zero;
            }

            if (Task.WaitAny(new Task[] { dispatch.Task }, remaining) < 0)
            {
                throw new RevitDispatchTimeoutException(true, timeout);
            }

            return dispatch.Task.GetAwaiter().GetResult();
        }

        private BimApiResponse DispatchTransaction(
            BimDiagnosticContext diagnostics,
            Func<UIApplication, BimApiResponse> work,
            BimTransactionCall call)
        {
            var capturedDiagnostics = diagnostics;
            var dispatch = dispatcher.InvokeAbandonable(capturedDiagnostics, work);
            var gate = call.Gate;

            // Phase 1: the queue.
            var first = Task.WaitAny(
                new Task[] { dispatch.Task, dispatch.Started },
                QueuePickupTimeout);
            if (first == 0)
            {
                return dispatch.Task.GetAwaiter().GetResult();
            }

            if (first < 0 && dispatch.Abandon())
            {
                throw new RevitDispatchTimeoutException(false, QueuePickupTimeout);
            }

            // Phase 2: setup, until the host thread enters the script.
            var entered = Task.WaitAny(
                new Task[] { dispatch.Task, gate.ScriptEntered },
                TransactionSetupTimeout);
            if (entered == 0)
            {
                return dispatch.Task.GetAwaiter().GetResult();
            }

            // Phase 3: the script. Its budget is counted from the entry signal,
            // the same instant the host thread counts from, and is enforced on
            // that thread; this wait only has to outlast it.
            if (entered == 1 &&
                Task.WaitAny(new Task[] { dispatch.Task }, gate.ScriptTimeout + ScriptReturnAllowance) >= 0)
            {
                return dispatch.Task.GetAwaiter().GetResult();
            }

            // This thread stops waiting. It does not decide what happened: it
            // withdraws permission to commit if it still can, records why, and
            // reports whatever the receipt says the host has observed.
            switch (gate.Cancel())
            {
                case BimTransactionCancelOutcome.BeforeScript:
                    call.Receipt.ProhibitCommit(
                        BimErrorCode.TransactionTimeout,
                        "RookBIM was still preparing the transaction after " +
                        $"{RevitDispatchTimeoutException.Seconds(TransactionSetupTimeout)} s, so the script was not " +
                        "started and will not be.");
                    break;
                case BimTransactionCancelOutcome.DuringScript:
                    call.Receipt.ProhibitCommit(
                        BimErrorCode.TransactionTimeout,
                        "The script did not finish within " +
                        $"{RevitDispatchTimeoutException.Seconds(gate.ScriptTimeout)} s.");
                    break;
                default:
                    // The host thread already owns the outcome: it is
                    // committing, or has refused the commit and is rolling
                    // back. Give it a moment to finish and answer itself.
                    if (Task.WaitAny(new Task[] { dispatch.Task }, TransactionCommitGrace) >= 0)
                    {
                        return dispatch.Task.GetAwaiter().GetResult();
                    }

                    break;
            }

            return BimTransactionReport.Build(
                call.Receipt.Snapshot(),
                new Dictionary<string, object?>
                {
                    // Observed: Revit's API thread had not finished this call
                    // when the wait ended.
                    ["revitStillBusy"] = !dispatch.Task.IsCompleted,
                });
        }

        private BimApiResponse ExecuteInDocumentContext(
            BimDiagnosticContext diagnostics,
            string operation,
            Func<UIDocument, Document, RevitDocumentIdentityEvidence, BimApiResponse> work,
            TimeSpan? timeout = null,
            BimTransactionCall? transactionCall = null)
        {
            try
            {
                Func<UIApplication, BimApiResponse> callback = uiapp =>
                {
                    UIDocument? uidoc;
                    Document? document;
                    RevitDocumentIdentityEvidence evidence;
                    try
                    {
                        uidoc = AcquireActiveUiDocument(uiapp, diagnostics);
                        document = uidoc == null
                            ? null
                            : AcquireDocument(uidoc, diagnostics);
                        if (uidoc == null || document == null)
                        {
                            return BimApiResponse.Fail(
                                BimErrorCode.NoActiveDocument,
                                "No active Revit document is open.",
                                409);
                        }

                        evidence = RevitDocumentIdentityResolver.Capture(
                            document,
                            diagnostics);
                    }
                    catch (Exception ex)
                    {
                        // This runs inside Revit's API context: the host is
                        // present. Letting it escape would report not_rhino_inside.
                        return BimApiResponse.Fail(
                            BimErrorCode.InternalError,
                            $"RookBIM operation '{operation}' could not read the active Revit document: " +
                            $"{DescribeDispatchException(ex)}. Nothing was changed.",
                            500);
                    }

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

                if (transactionCall != null)
                {
                    return DispatchTransaction(diagnostics, callback, transactionCall);
                }

                return timeout.HasValue
                    ? DispatchWithTimeout(diagnostics, callback, timeout.Value)
                    : Dispatch(diagnostics, callback);
            }
            catch (RevitDispatchTimeoutException ex)
            {
                // The host is present and took the work; what failed is Revit's
                // idle queue. Reporting not_rhino_inside here sent callers after
                // the wrong cause.
                var response = BimApiResponse.Fail(
                    ex.WorkStarted ? BimErrorCode.RevitOperationTimeout : BimErrorCode.RevitNotIdle,
                    DescribeDispatchTimeout(ex, operation),
                    503);
                response.Data = new
                {
                    operation = operation,
                    waitedSeconds = (int)Math.Round(ex.Waited.TotalSeconds),
                    workStarted = ex.WorkStarted
                };
                return response;
            }
            catch (Exception ex)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NotRhinoInside,
                    $"RookBIM could not enter the Revit API context: {DescribeDispatchException(ex)}",
                    503);
            }
        }

        private static string DescribeDispatchTimeout(
            RevitDispatchTimeoutException ex,
            string operation)
        {
            var seconds = RevitDispatchTimeoutException.Seconds(ex.Waited);
            if (ex.WorkStarted)
            {
                return $"RookBIM operation '{operation}' started on Revit's API thread but did not finish within " +
                    $"{seconds} s. It is still running and its result is discarded; Revit is busy, not blocked. " +
                    "Wait for Revit to finish, then retry (narrow the request if it is a large query or export).";
            }

            return $"Revit did not become idle within {seconds} s, so RookBIM operation '{operation}' never ran " +
                "and nothing was read or changed. The likely cause is an open dialog or an active command in Revit " +
                "(a modal window, an unfinished sketch or edit mode, a tool waiting for a pick). Ask the user to " +
                "close the dialog or finish or cancel the command in Revit, then retry.";
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
