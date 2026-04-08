using System;
using System.Threading;
using Rhino;

namespace Rook
{
    /// <summary>
    /// Provides thread-local context for the target document during request handling.
    /// This allows handlers to operate on a pinned document rather than ActiveDoc
    /// when requests come from a chat panel opened in a specific document.
    /// </summary>
    public static class DocumentContext
    {
        private static readonly AsyncLocal<uint?> _targetDocumentSerialNumber = new();

        /// <summary>
        /// Gets or sets the target document serial number for the current async context.
        /// When set, GetDocument() will return this document instead of ActiveDoc.
        /// </summary>
        public static uint? TargetDocumentSerialNumber
        {
            get => _targetDocumentSerialNumber.Value;
            set => _targetDocumentSerialNumber.Value = value;
        }

        /// <summary>
        /// Gets the document to use for the current operation.
        /// Returns the pinned document if set, otherwise falls back to ActiveDoc.
        /// </summary>
        public static RhinoDoc? GetDocument()
        {
            var serial = _targetDocumentSerialNumber.Value;
            if (serial.HasValue && serial.Value != 0)
            {
                var doc = RhinoDoc.FromRuntimeSerialNumber(serial.Value);
                if (doc != null)
                {
                    return doc;
                }
                // Fall back to ActiveDoc if the pinned document no longer exists
            }
            return RhinoDoc.ActiveDoc;
        }

        /// <summary>
        /// Executes an action with a specific document context.
        /// Restores the previous context after the action completes.
        /// </summary>
        public static void WithDocument(uint? documentSerialNumber, Action action)
        {
            var previous = _targetDocumentSerialNumber.Value;
            try
            {
                _targetDocumentSerialNumber.Value = documentSerialNumber;
                action();
            }
            finally
            {
                _targetDocumentSerialNumber.Value = previous;
            }
        }

        /// <summary>
        /// Executes a function with a specific document context.
        /// Restores the previous context after the function completes.
        /// </summary>
        public static T WithDocument<T>(uint? documentSerialNumber, Func<T> func)
        {
            var previous = _targetDocumentSerialNumber.Value;
            try
            {
                _targetDocumentSerialNumber.Value = documentSerialNumber;
                return func();
            }
            finally
            {
                _targetDocumentSerialNumber.Value = previous;
            }
        }
    }
}
