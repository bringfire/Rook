using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.UI.Chat
{
    public sealed class ConversationCloseRequest
    {
        public ConversationCloseRequest(Uri baseUri, string conversationId, string? sessionNonce)
        {
            BaseUri = baseUri ?? throw new ArgumentNullException(nameof(baseUri));
            ConversationId = string.IsNullOrWhiteSpace(conversationId)
                ? throw new ArgumentException("Conversation ID is required.", nameof(conversationId))
                : conversationId;
            SessionNonce = sessionNonce;
        }

        public Uri BaseUri { get; }
        public string ConversationId { get; }
        public string? SessionNonce { get; }
    }

    /// <summary>
    /// Service-lifetime owner for bounded conversation-close delivery. A tab may
    /// disappear without cancelling the close request it already enqueued.
    /// </summary>
    public sealed class ConversationCloseCoordinator : IDisposable
    {
        private static readonly Lazy<ConversationCloseCoordinator> LazyInstance =
            new(() => new ConversationCloseCoordinator(DefaultCloseAsync));

        private static readonly TimeSpan CloseDeadline = TimeSpan.FromSeconds(20);
        private readonly object _gate = new();
        private readonly Dictionary<string, Task> _pending = new(StringComparer.Ordinal);
        private readonly Func<Uri, string, string?, CancellationToken, Task> _closeAsync;
        private bool _disposed;

        private ConversationCloseCoordinator(
            Func<Uri, string, string?, CancellationToken, Task> closeAsync)
        {
            _closeAsync = closeAsync;
        }

        public static ConversationCloseCoordinator Instance => LazyInstance.Value;

        internal static ConversationCloseCoordinator ForTests(
            Func<Uri, string, string?, CancellationToken, Task> closeAsync)
            => new(closeAsync);

        public void Enqueue(ConversationCloseRequest request)
        {
            if (request == null) throw new ArgumentNullException(nameof(request));
            lock (_gate)
            {
                if (_disposed || _pending.ContainsKey(request.ConversationId)) return;
                var task = Task.Run(() => DeliverAsync(request));
                _pending.Add(request.ConversationId, task);
            }
        }

        public async Task<bool> DrainAsync(TimeSpan deadline)
        {
            Task[] snapshot;
            lock (_gate) snapshot = _pending.Values.ToArray();
            if (snapshot.Length == 0) return true;
            var all = Task.WhenAll(snapshot);
            var timeout = Task.Delay(deadline);
            return ReferenceEquals(await Task.WhenAny(all, timeout).ConfigureAwait(false), all);
        }

        private async Task DeliverAsync(ConversationCloseRequest request)
        {
            try
            {
                using var cts = new CancellationTokenSource(CloseDeadline);
                await _closeAsync(request.BaseUri, request.ConversationId, request.SessionNonce, cts.Token);
            }
            catch
            {
                // The service reports clean versus unclean closure. Tab disposal has
                // no retry authority and cannot turn a failed close into success.
            }
            finally
            {
                lock (_gate) _pending.Remove(request.ConversationId);
            }
        }

        private static async Task DefaultCloseAsync(
            Uri baseUri,
            string conversationId,
            string? sessionNonce,
            CancellationToken ct)
        {
            using var client = new AgentChatClient();
            client.SetSessionNonce(sessionNonce);
            await client.CloseAsync(baseUri, conversationId, ct);
        }

        public void Dispose()
        {
            lock (_gate) _disposed = true;
        }
    }
}
