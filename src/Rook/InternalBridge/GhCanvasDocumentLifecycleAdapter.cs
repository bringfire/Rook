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

            var callbackGate = new CallbackGate(onDocumentChanged);
            if (!TryCreateHandler(documentChanged, callbackGate.Invoke, out var handler))
            {
                return GhCanvasDocumentLifecycleSubscription.Unavailable("canvas_document_changed_delegate_incompatible");
            }

            try
            {
                documentChanged.AddEventHandler(canvas, handler);
                return GhCanvasDocumentLifecycleSubscription.Available(canvas, documentChanged, handler, callbackGate.Disable);
            }
            catch
            {
                callbackGate.Disable();
                return GhCanvasDocumentLifecycleSubscription.Unavailable("canvas_document_changed_subscribe_failed");
            }
        }

        private sealed class CallbackGate
        {
            private Action<object?, object?>? _callback;

            internal CallbackGate(Action<object?, object?> callback)
            {
                _callback = callback;
            }

            internal void Invoke(object? oldDocument, object? newDocument) =>
                Volatile.Read(ref _callback)?.Invoke(oldDocument, newDocument);

            internal void Disable() => Interlocked.Exchange(ref _callback, null);
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
        private readonly Action? _disableCallbacks;
        private int _disposed;

        private GhCanvasDocumentLifecycleSubscription(
            bool isAvailable,
            string? reason,
            object? canvas = null,
            EventInfo? documentChanged = null,
            Delegate? handler = null,
            Action? disableCallbacks = null)
        {
            IsAvailable = isAvailable;
            Reason = reason;
            _canvas = canvas;
            _documentChanged = documentChanged;
            _handler = handler;
            _disableCallbacks = disableCallbacks;
        }

        internal bool IsAvailable { get; }
        internal string? Reason { get; }

        internal static GhCanvasDocumentLifecycleSubscription Unavailable(string reason) => new(false, reason);

        internal static GhCanvasDocumentLifecycleSubscription Available(
            object canvas,
            EventInfo documentChanged,
            Delegate handler,
            Action disableCallbacks) =>
            new(true, null, canvas, documentChanged, handler, disableCallbacks);

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _disposed, 1) != 0)
            {
                return;
            }

            _disableCallbacks?.Invoke();
            if (_canvas is not null && _documentChanged is not null && _handler is not null)
            {
                RemoveEventHandlerBestEffort(_documentChanged, _canvas, _handler);
            }
        }

        private static void RemoveEventHandlerBestEffort(EventInfo eventInfo, object target, Delegate handler)
        {
            try
            {
                eventInfo.RemoveEventHandler(target, handler);
            }
            catch
            {
            }
        }
    }
}
