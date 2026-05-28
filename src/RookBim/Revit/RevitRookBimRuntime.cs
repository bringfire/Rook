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
        private readonly RevitApiDispatcher dispatcher;
        private readonly RevitQueryService query;

        public RevitRookBimRuntime()
            : this(new RevitApiDispatcher())
        {
        }

        internal RevitRookBimRuntime(RevitApiDispatcher dispatcher)
        {
            this.dispatcher = dispatcher ?? throw new ArgumentNullException(nameof(dispatcher));
            this.query = new RevitQueryService();
        }

        public BimStatusResponse Status()
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

        public BimApiResponse ActiveDocument()
        {
            try
            {
                var result = Dispatch(uiapp =>
                {
                    var uidoc = RevitContext.ActiveUiDocument(uiapp);
                    if (uidoc == null || uidoc.Document == null)
                    {
                        return null;
                    }

                    var document = uidoc.Document;
                    return new ActiveDocumentResult
                    {
                        Document = RevitIdentitySerializer.DocumentIdentity(document),
                        View = SerializeActiveView(uidoc, document)
                    };
                });

                if (result == null)
                {
                    return BimApiResponse.Fail(
                        BimErrorCode.NoActiveDocument,
                        "No active Revit document is open.",
                        409);
                }

                return BimApiResponse.Ok(result);
            }
            catch (Exception ex)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NotRhinoInside,
                    $"RookBIM could not enter the Revit API context: {DescribeDispatchException(ex)}",
                    503);
            }
        }

        public BimApiResponse QueryElements(BimQueryElementsRequest request)
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
                    var view = uidoc.ActiveView ?? document.ActiveView;
                    return query.Query(document, view, request);
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

        public BimApiResponse ElementInfo(BimElementRequest request)
        {
            return LaterToolUnavailable();
        }

        public BimApiResponse ElementParameters(BimElementRequest request)
        {
            return LaterToolUnavailable();
        }

        public BimApiResponse SelectElements(BimSelectElementsRequest request)
        {
            return LaterToolUnavailable();
        }

        public BimApiResponse ClearSelection()
        {
            return LaterToolUnavailable();
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

        private static string DescribeDispatchException(Exception ex)
        {
            var root = ex is AggregateException aggregate
                ? aggregate.Flatten().InnerExceptions.FirstOrDefault() ?? ex
                : ex;
            return $"{root.GetType().Name}: {root.Message}";
        }

        private static BimViewIdentity? SerializeActiveView(UIDocument uidoc, Document document)
        {
            var view = uidoc.ActiveView ?? document.ActiveView;
            return view == null ? null : RevitIdentitySerializer.ViewIdentity(view);
        }

        private static BimApiResponse LaterToolUnavailable()
        {
            return BimApiResponse.Fail(
                BimErrorCode.CapabilityUnavailable,
                "This RookBIM Revit capability is not implemented in Task 7.",
                501);
        }

        private sealed class ActiveDocumentResult
        {
            public BimDocumentIdentity Document { get; set; } = new BimDocumentIdentity();

            public BimViewIdentity? View { get; set; }
        }
    }
}
