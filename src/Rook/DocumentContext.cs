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
        private static readonly AsyncLocal<RhinoDoc?> _requiredDocument = new();

        /// <summary>
        /// Gets or sets the target document serial number for the current async context.
        /// When set, GetDocument() will return this document instead of ActiveDoc.
        /// </summary>
        public static uint? TargetDocumentSerialNumber
        {
            get => _targetDocumentSerialNumber.Value;
            set
            {
                _targetDocumentSerialNumber.Value = value;
                _requiredDocument.Value = null;
            }
        }

        /// <summary>
        /// Gets the document to use for the current operation.
        /// Returns the pinned document if set, otherwise falls back to ActiveDoc.
        /// </summary>
        public static RhinoDoc? GetDocument()
        {
            var required = _requiredDocument.Value;
            if (required != null)
            {
                return required;
            }
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
            var previousRequired = _requiredDocument.Value;
            try
            {
                _targetDocumentSerialNumber.Value = documentSerialNumber;
                _requiredDocument.Value = null;
                action();
            }
            finally
            {
                _targetDocumentSerialNumber.Value = previous;
                _requiredDocument.Value = previousRequired;
            }
        }

        /// <summary>
        /// Executes a function with a specific document context.
        /// Restores the previous context after the function completes.
        /// </summary>
        public static T WithDocument<T>(uint? documentSerialNumber, Func<T> func)
        {
            var previous = _targetDocumentSerialNumber.Value;
            var previousRequired = _requiredDocument.Value;
            try
            {
                _targetDocumentSerialNumber.Value = documentSerialNumber;
                _requiredDocument.Value = null;
                return func();
            }
            finally
            {
                _targetDocumentSerialNumber.Value = previous;
                _requiredDocument.Value = previousRequired;
            }
        }

        /// <summary>
        /// Executes against one required Rhino document. A missing bound serial is
        /// refused before the operation and never falls back to ActiveDoc.
        /// </summary>
        public static T WithRequiredDocument<T>(
            uint documentSerialNumber,
            Func<T> func)
        {
            return WithRequiredDocument(
                documentSerialNumber,
                RhinoDoc.FromRuntimeSerialNumber,
                func);
        }

        internal static T WithRequiredDocument<T>(
            uint documentSerialNumber,
            Func<uint, RhinoDoc?> resolver,
            Func<T> func)
        {
            if (documentSerialNumber == 0)
                throw new ArgumentOutOfRangeException(nameof(documentSerialNumber));
            if (resolver == null)
                throw new ArgumentNullException(nameof(resolver));
            if (func == null)
                throw new ArgumentNullException(nameof(func));

            var document = resolver(documentSerialNumber);
            if (document == null)
            {
                throw new InvalidOperationException(
                    $"Required Rhino document {documentSerialNumber} is unavailable.");
            }

            var previous = _targetDocumentSerialNumber.Value;
            var previousRequired = _requiredDocument.Value;
            try
            {
                _targetDocumentSerialNumber.Value = documentSerialNumber;
                _requiredDocument.Value = document;
                return func();
            }
            finally
            {
                _targetDocumentSerialNumber.Value = previous;
                _requiredDocument.Value = previousRequired;
            }
        }
    }
}
