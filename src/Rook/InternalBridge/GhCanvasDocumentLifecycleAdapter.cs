using System;
using System.Linq.Expressions;
using System.Reflection;
using System.Threading;

namespace Rook.InternalBridge
{
    internal sealed class GhCanvasDocumentLifecycleAdapter
    {
        internal GhCanvasDocumentLifecycleSubscription Attach(object canvas, Action<object?, object?> onDocumentChanged)
        {
            if (canvas is null)
            {
                return GhCanvasDocumentLifecycleSubscription.Unavailable("canvas_missing");
            }

            if (onDocumentChanged is null)
            {
                return GhCanvasDocumentLifecycleSubscription.Unavailable("canvas_document_changed_callback_missing");
            }

            var documentChanged = canvas.GetType().GetEvent("DocumentChanged", BindingFlags.Instance | BindingFlags.Public);
            if (documentChanged is null)
            {
                return GhCanvasDocumentLifecycleSubscription.Unavailable("canvas_document_changed_event_missing");
            }

            if (!TryCreateHandler(documentChanged, onDocumentChanged, out var handler))
            {
                return GhCanvasDocumentLifecycleSubscription.Unavailable("canvas_document_changed_delegate_incompatible");
            }

            try
            {
                documentChanged.AddEventHandler(canvas, handler);
                return GhCanvasDocumentLifecycleSubscription.Available(canvas, documentChanged, handler);
            }
            catch
            {
                return GhCanvasDocumentLifecycleSubscription.Unavailable("canvas_document_changed_subscribe_failed");
            }
        }

        private static bool TryCreateHandler(EventInfo eventInfo, Action<object?, object?> callback, out Delegate handler)
        {
            handler = null!;
            var delegateType = eventInfo.EventHandlerType;
            var invoke = delegateType?.GetMethod("Invoke", BindingFlags.Instance | BindingFlags.Public);
            var parameters = invoke?.GetParameters();
            if (invoke is null ||
                parameters is null ||
                invoke.ReturnType != typeof(void) ||
                parameters.Length != 2 ||
                !typeof(EventArgs).IsAssignableFrom(parameters[1].ParameterType))
            {
                return false;
            }

            var oldDocument = parameters[1].ParameterType.GetProperty("OldDocument", BindingFlags.Instance | BindingFlags.Public);
            var newDocument = parameters[1].ParameterType.GetProperty("NewDocument", BindingFlags.Instance | BindingFlags.Public);
            if (oldDocument?.CanRead != true || oldDocument.GetMethod is null ||
                newDocument?.CanRead != true || newDocument.GetMethod is null)
            {
                return false;
            }

            try
            {
                var sender = Expression.Parameter(parameters[0].ParameterType, "sender");
                var eventArgs = Expression.Parameter(parameters[1].ParameterType, "eventArgs");
                var invokeCallback = Expression.Call(
                    Expression.Constant(callback),
                    typeof(Action<object?, object?>).GetMethod(nameof(Action<object?, object?>.Invoke))!,
                    Expression.Convert(Expression.Property(eventArgs, oldDocument), typeof(object)),
                    Expression.Convert(Expression.Property(eventArgs, newDocument), typeof(object)));

                handler = Expression.Lambda(delegateType!, invokeCallback, sender, eventArgs).Compile();
                return true;
            }
            catch
            {
                return false;
            }
        }
    }

    internal sealed class GhCanvasDocumentLifecycleSubscription : IDisposable
    {
        private readonly object? _canvas;
        private readonly EventInfo? _documentChanged;
        private readonly Delegate? _handler;
        private int _disposed;

        private GhCanvasDocumentLifecycleSubscription(
            bool isAvailable,
            string? reason,
            object? canvas = null,
            EventInfo? documentChanged = null,
            Delegate? handler = null)
        {
            IsAvailable = isAvailable;
            Reason = reason;
            _canvas = canvas;
            _documentChanged = documentChanged;
            _handler = handler;
        }

        internal bool IsAvailable { get; }
        internal string? Reason { get; }

        internal static GhCanvasDocumentLifecycleSubscription Unavailable(string reason) => new(false, reason);

        internal static GhCanvasDocumentLifecycleSubscription Available(object canvas, EventInfo documentChanged, Delegate handler) =>
            new(true, null, canvas, documentChanged, handler);

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _disposed, 1) != 0 ||
                _canvas is null ||
                _documentChanged is null ||
                _handler is null)
            {
                return;
            }

            _documentChanged.RemoveEventHandler(_canvas, _handler);
        }
    }
}
