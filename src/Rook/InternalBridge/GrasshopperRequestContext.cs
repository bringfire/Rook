using System;
using System.Reflection;
using System.Threading;

namespace Rook.InternalBridge
{
    internal sealed class CapturedGrasshopperRequestContext
    {
        internal CapturedGrasshopperRequestContext(
            Assembly assembly,
            object canvas,
            object document,
            Guid documentId)
        {
            Assembly = assembly;
            Canvas = canvas;
            Document = document;
            DocumentId = documentId;
        }

        internal Assembly Assembly { get; }
        internal object Canvas { get; }
        internal object Document { get; }
        internal Guid DocumentId { get; }
    }

    internal static class GrasshopperRequestContext
    {
        private static readonly AsyncLocal<CapturedGrasshopperRequestContext?> CurrentContext = new();

        internal static CapturedGrasshopperRequestContext? Current => CurrentContext.Value;

        internal static T CaptureAndRun<T>(
            Assembly assembly,
            Func<object?> activeCanvas,
            string boundDocumentId,
            Func<T> operation)
        {
            return Run(Capture(assembly, activeCanvas, boundDocumentId), operation);
        }

        internal static CapturedGrasshopperRequestContext Capture(
            Assembly assembly,
            Func<object?> activeCanvas,
            string boundDocumentId)
        {
            if (assembly == null)
                throw new ArgumentNullException(nameof(assembly));
            if (activeCanvas == null)
                throw new ArgumentNullException(nameof(activeCanvas));
            if (!Guid.TryParseExact(boundDocumentId, "D", out var expectedId) ||
                expectedId == Guid.Empty ||
                !string.Equals(expectedId.ToString("D"), boundDocumentId, StringComparison.Ordinal))
            {
                throw new InvalidOperationException(
                    "The bound Grasshopper document id must be a canonical nonempty GUID.");
            }

            var canvas = activeCanvas();
            if (canvas == null)
                throw new InvalidOperationException("No active Grasshopper canvas is available.");

            var document = canvas.GetType()
                .GetProperty("Document", BindingFlags.Instance | BindingFlags.Public)
                ?.GetValue(canvas);
            if (document == null)
                throw new InvalidOperationException("No active Grasshopper document is available.");

            var documentIdValue = document.GetType()
                .GetProperty("DocumentID", BindingFlags.Instance | BindingFlags.Public)
                ?.GetValue(document);
            if (documentIdValue is not Guid documentId || documentId == Guid.Empty)
            {
                throw new InvalidOperationException(
                    "The active Grasshopper document does not expose a nonempty DocumentID.");
            }
            if (documentId != expectedId)
            {
                throw new InvalidOperationException(
                    "The active Grasshopper document does not match the bound document id.");
            }

            var isClosed = document.GetType()
                .GetProperty("IsClosed", BindingFlags.Instance | BindingFlags.Public)
                ?.GetValue(document);
            if (isClosed is bool closed && closed)
                throw new InvalidOperationException("The bound Grasshopper document is closed.");

            return new CapturedGrasshopperRequestContext(
                assembly,
                canvas,
                document,
                documentId);
        }

        internal static T Run<T>(
            CapturedGrasshopperRequestContext context,
            Func<T> operation)
        {
            if (context == null)
                throw new ArgumentNullException(nameof(context));
            if (operation == null)
                throw new ArgumentNullException(nameof(operation));

            var previous = CurrentContext.Value;
            try
            {
                CurrentContext.Value = context;
                return operation();
            }
            finally
            {
                CurrentContext.Value = previous;
            }
        }
    }
}
