using System;
using Rhino;

namespace Rook
{
    /// <summary>
    /// Disposable wrapper around RhinoDoc.BeginUndoRecord / EndUndoRecord.
    /// Use with 'using var' to ensure undo records are always closed,
    /// even on exceptions or early returns.
    /// </summary>
    /// <example>
    /// using var undo = new UndoScope(doc, "My Operation");
    /// // ... modify document ...
    /// // EndUndoRecord called automatically when scope exits
    /// </example>
    internal struct UndoScope : IDisposable
    {
        private readonly RhinoDoc _doc;
        private readonly uint _recordId;
        private bool _disposed;

        public UndoScope(RhinoDoc doc, string name)
        {
            _doc = doc;
            _recordId = doc.BeginUndoRecord(name);
            _disposed = false;
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                _disposed = true;
                _doc.EndUndoRecord(_recordId);
            }
        }
    }
}
