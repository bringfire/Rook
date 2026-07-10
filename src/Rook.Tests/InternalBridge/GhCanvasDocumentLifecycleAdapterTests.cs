using System;
using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.InternalBridge
{
    public sealed class GhCanvasDocumentLifecycleAdapterTests
    {
        public delegate void DocumentChangedHandler(FakeCanvas sender, DocumentChangedEventArgs args);
        public delegate void IncompatibleDocumentChangedHandler(object sender, IncompatibleDocumentChangedEventArgs args);

        public sealed class DocumentChangedEventArgs : EventArgs
        {
            public DocumentChangedEventArgs(object? oldDocument, object? newDocument)
            {
                OldDocument = oldDocument;
                NewDocument = newDocument;
            }

            public object? OldDocument { get; }
            public object? NewDocument { get; }
        }

        public sealed class IncompatibleDocumentChangedEventArgs : EventArgs
        {
        }

        public sealed class FakeDocument
        {
        }

        public sealed class FakeCanvas
        {
            public FakeCanvas(object? document)
            {
                Document = document;
            }

            public object? Document { get; }
            public event DocumentChangedHandler? DocumentChanged;

            public void RaiseDocumentChanged(object? oldDocument, object? newDocument) =>
                DocumentChanged?.Invoke(this, new DocumentChangedEventArgs(oldDocument, newDocument));
        }

        public sealed class IncompatibleCanvas
        {
            public event IncompatibleDocumentChangedHandler? DocumentChanged;

            public void RaiseDocumentChanged() =>
                DocumentChanged?.Invoke(this, new IncompatibleDocumentChangedEventArgs());
        }

        [Fact]
        public void AttachCanvasDocumentChanged_ForwardsOldAndNewDocuments()
        {
            var ambientDocument = new FakeDocument();
            var oldDocument = new FakeDocument();
            var newDocument = new FakeDocument();
            var canvas = new FakeCanvas(ambientDocument);
            (object? Old, object? New)? observed = null;

            using var subscription = new GhCanvasDocumentLifecycleAdapter().Attach(
                canvas,
                (prior, current) => observed = (prior, current));

            canvas.RaiseDocumentChanged(oldDocument, newDocument);

            Assert.True(subscription.IsAvailable);
            Assert.True(observed.HasValue);
            Assert.NotSame(ambientDocument, oldDocument);
            Assert.NotSame(ambientDocument, newDocument);
            Assert.NotSame(oldDocument, newDocument);
            Assert.Same(oldDocument, observed.Value.Old);
            Assert.Same(newDocument, observed.Value.New);
        }

        [Fact]
        public void AttachCanvasDocumentChanged_IncompatibleDelegate_FailsClosed()
        {
            using var subscription = new GhCanvasDocumentLifecycleAdapter().Attach(
                new IncompatibleCanvas(),
                (_, _) => { });

            Assert.False(subscription.IsAvailable);
            Assert.Equal("canvas_document_changed_delegate_incompatible", subscription.Reason);
        }

        [Fact]
        public void Dispose_CanvasSubscription_PreventsFurtherCallbacks()
        {
            var canvas = new FakeCanvas(new FakeDocument());
            var callbackCount = 0;
            var subscription = new GhCanvasDocumentLifecycleAdapter().Attach(canvas, (_, _) => callbackCount++);

            subscription.Dispose();
            subscription.Dispose();
            canvas.RaiseDocumentChanged(new FakeDocument(), new FakeDocument());

            Assert.Equal(0, callbackCount);
        }
    }
}
