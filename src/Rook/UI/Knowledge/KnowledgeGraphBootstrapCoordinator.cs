using System;
using System.Threading;
using System.Threading.Tasks;
using Rook.UI.Chat;
using Rook.UI.Web;

namespace Rook.UI.Knowledge
{
    internal sealed class KnowledgeGraphBootstrapCoordinator
    {
        private readonly Func<CancellationToken, Task<ChatServiceHealth>> _ensureStartedAsync;
        private readonly Func<string?> _sessionNonceProvider;
        private readonly Action<string> _executeScript;
        private readonly Action<string> _log;
        private readonly object _sync = new();

        private bool _webViewReady;
        private bool _requestStarted;
        private bool _bootstrapSucceeded;
        private Task? _inFlight;
        private string? _latestScript;

        public KnowledgeGraphBootstrapCoordinator(
            Func<CancellationToken, Task<ChatServiceHealth>> ensureStartedAsync,
            Func<string?> sessionNonceProvider,
            Action<string> executeScript,
            Action<string> log)
        {
            _ensureStartedAsync = ensureStartedAsync ?? throw new ArgumentNullException(nameof(ensureStartedAsync));
            _sessionNonceProvider = sessionNonceProvider ?? throw new ArgumentNullException(nameof(sessionNonceProvider));
            _executeScript = executeScript ?? throw new ArgumentNullException(nameof(executeScript));
            _log = log ?? throw new ArgumentNullException(nameof(log));
        }

        public async Task MarkWebViewReadyAsync(CancellationToken ct)
        {
            string? scriptToReplay;
            bool shouldStart;

            lock (_sync)
            {
                _webViewReady = true;
                scriptToReplay = _latestScript;
                shouldStart = !_requestStarted && _inFlight == null;
            }

            if (!string.IsNullOrEmpty(scriptToReplay))
            {
                _executeScript(scriptToReplay!);
            }

            if (shouldStart)
            {
                await RequestBootstrapAsync(ct);
            }
        }

        public Task RequestBootstrapAsync(CancellationToken ct)
        {
            string? scriptToReplay = null;

            lock (_sync)
            {
                if (_inFlight != null)
                {
                    return _inFlight;
                }

                if (_bootstrapSucceeded)
                {
                    if (_webViewReady && !string.IsNullOrEmpty(_latestScript))
                    {
                        scriptToReplay = _latestScript;
                    }
                }
                else
                {
                    _requestStarted = true;
                    var task = RunBootstrapAsync(ct);
                    _inFlight = task.IsCompleted ? null : task;
                    return task;
                }
            }

            if (!string.IsNullOrEmpty(scriptToReplay))
            {
                _executeScript(scriptToReplay!);
            }

            return Task.CompletedTask;
        }

        private async Task RunBootstrapAsync(CancellationToken ct)
        {
            try
            {
                var health = await _ensureStartedAsync(ct);
                var script = BuildScriptForHealth(health, _sessionNonceProvider());
                var success = health.ServiceAvailable && health.BaseUri != null;

                if (!success)
                {
                    var message = string.IsNullOrWhiteSpace(health.ServiceMessage)
                        ? "Chat service is unavailable."
                        : health.ServiceMessage;
                    _log($"Rook: Knowledge Graph panel — {message}");
                }

                CompleteBootstrap(script, success);
            }
            catch (Exception ex)
            {
                var message = $"Knowledge Graph bootstrap failed: {ex.Message}";
                _log($"Rook: {message}");
                CompleteBootstrap(BuildFailureScript(message), success: false);
            }
        }

        private void CompleteBootstrap(string script, bool success)
        {
            bool shouldExecute;

            lock (_sync)
            {
                _latestScript = script;
                _bootstrapSucceeded = success;
                _inFlight = null;
                shouldExecute = _webViewReady;
            }

            if (shouldExecute)
            {
                _executeScript(script);
            }
        }

        private static string BuildScriptForHealth(ChatServiceHealth health, string? nonce)
        {
            if (!health.ServiceAvailable || health.BaseUri == null)
            {
                var message = string.IsNullOrWhiteSpace(health.ServiceMessage)
                    ? "Chat service is unavailable."
                    : health.ServiceMessage;
                return BuildFailureScript(message);
            }

            var host = RookWebSurface.EscapeForJavaScript(health.BaseUri.Host);
            var escapedNonce = RookWebSurface.EscapeForJavaScript(nonce ?? "");
            var port = health.BaseUri.Port;

            return
                $"window.__rookServiceHost = '{host}';" +
                $"window.__rookServicePort = {port};" +
                $"window.__rookSessionNonce = '{escapedNonce}';" +
                "if (window.rookKnowledgeGraphBootstrap) {" +
                    $"window.rookKnowledgeGraphBootstrap({{ host: '{host}', port: {port}, nonce: '{escapedNonce}' }});" +
                "} else {" +
                    $"window.dispatchEvent(new CustomEvent('rook-knowledge-bootstrap', {{ detail: {{ host: '{host}', port: {port}, nonce: '{escapedNonce}' }} }}));" +
                "}";
        }

        private static string BuildFailureScript(string message)
        {
            var escapedMessage = RookWebSurface.EscapeForJavaScript(message);
            return
                $"window.__rookKnowledgeGraphBootstrapError = '{escapedMessage}';" +
                "if (window.rookKnowledgeGraphBootstrapFailed) {" +
                    $"window.rookKnowledgeGraphBootstrapFailed('{escapedMessage}');" +
                "} else {" +
                    $"window.dispatchEvent(new CustomEvent('rook-knowledge-bootstrap-failed', {{ detail: {{ message: '{escapedMessage}' }} }}));" +
                "}";
        }
    }
}
